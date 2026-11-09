"""pending, commit-classified, queue and finish: the supervisor's scan-and-record steps.

Every command prints JSON (or nothing) to stdout. `queue` and `finish` compute
everything first and save the record once at the end, so a gh failure halfway
leaves the record file untouched. The only GitHub calls are read-only.
"""
import argparse
import json
import sys
from datetime import datetime

from . import config, proc, record

BODY_LIMIT = 2000
# Claude Code truncates a Bash result above ~30K characters, and the scanner would then commit
# `max_pr` past PRs it never saw. A batch therefore stops growing at PENDING_BUDGET printed
# characters (long bodies, \uXXXX-escaped non-ASCII text and many directories all count);
# PENDING_LIMIT caps the number of PRs.
PENDING_LIMIT = 10
PENDING_BUDGET = 20000
DIR_COUNTS_LIMIT = 50
RESULTS = ("reviewed", "approved", "escalated", "no-action", "not-interesting", "merged", "closed",
           "needs-config", "busy")
RETRY_RESULTS = ("needs-config", "busy")  # the lead did not run: keep the entry as it was

# `-F number=<N>` comes first in argv so tests can tell PRs apart by argv prefix.
QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      state isDraft author { login } updatedAt headRefOid
      comments(last: 50) { nodes { author { login __typename } createdAt } }
      reviews(last: 50) { nodes { author { login __typename } submittedAt } }
      reviewThreads(last: 100) {
        nodes { comments(last: 20) { nodes { author { login __typename } createdAt } } }
      }
    }
  }
}
"""


def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _prefilter(cfg: dict) -> dict:
    return cfg.get("prefilter") or {}


# --- pending -----------------------------------------------------------------

def _dir_counts(repo: str, number: int) -> dict:
    """The DIR_COUNTS_LIMIT largest directories; `dir_counts_truncated` counts the omitted ones."""
    files = proc.gh_json("pr", "view", str(number), "--repo", repo, "--json", "files")["files"]
    counts: dict[str, int] = {}
    for f in files:
        key = "/".join(f["path"].split("/")[:2])
        counts[key] = counts.get(key, 0) + 1
    largest = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    out: dict = {"dir_counts": dict(largest[:DIR_COUNTS_LIMIT])}
    if len(largest) > DIR_COUNTS_LIMIT:
        out["dir_counts_truncated"] = len(largest) - DIR_COUNTS_LIMIT
    return out


def _batch_text(mark: int, batch: list[dict], more: bool) -> str:
    """Exactly what `pending` prints, so the budget is measured on the real output."""
    max_pr = max([mark, *(p["number"] for p in batch)])
    return json.dumps({"max_pr": max_pr, "to_classify": batch, "more": more})


def _pending(args) -> int:
    cfg = config.load(args.name)
    rec = record.load(cfg)
    mark = rec["last_scanned_pr"] or 0
    pre = _prefilter(cfg)
    argv = ["pr", "list", "--repo", cfg["repo"], "--state", "open", "--limit", "1000",
            "--json", "number,title,body,isDraft,author,labels,baseRefName"]
    for label in pre.get("labels") or []:
        argv += ["--label", label]
    if pre.get("base"):
        argv += ["--base", pre["base"]]
    authors = pre.get("authors") or []
    candidates = [pr for pr in sorted(proc.gh_json(*argv), key=lambda p: p["number"])
                  if pr["number"] > mark and not (authors and pr["author"]["login"] not in authors)]
    # One batch of the lowest numbers, cut at the output budget: max_pr is the highest PR in
    # the batch, so it never passes a PR the scanner has not seen.
    batch: list[dict] = []
    text = _batch_text(mark, batch, bool(candidates))
    for pr in candidates[:args.limit]:
        entry = {"number": pr["number"], "title": pr["title"],
                 "body": (pr["body"] or "")[:BODY_LIMIT], **_dir_counts(cfg["repo"], pr["number"])}
        trial = _batch_text(mark, [*batch, entry], len(candidates) > len(batch) + 1)
        if not batch:
            # A lone PR is always returned; its body gives way until the output fits. A body
            # character prints as 1 to 6 characters, so cut a sixth of the excess at a time.
            while len(trial) + 1 > PENDING_BUDGET and entry["body"]:
                cut = max(1, (len(trial) + 1 - PENDING_BUDGET) // 6)
                entry["body"] = entry["body"][:-cut]
                trial = _batch_text(mark, [entry], len(candidates) > 1)
        elif len(trial) + 1 > PENDING_BUDGET:
            break
        batch.append(entry)
        text = trial
    print(text)
    return 0


# --- commit-classified -------------------------------------------------------

def _commit_classified(args) -> int:
    cfg = config.load(args.name)
    data = json.load(sys.stdin)
    rec = record.load(cfg)
    for item in data["interesting"]:
        rec["prs"].setdefault(item["number"], {
            "reason": item["reason"], "status": "new",
            "updated_at": None, "head_sha": None, "last_run_at": None,
        })
    rec["last_scanned_pr"] = data["max_pr"]
    record.save(cfg, rec)
    return 0


# --- queue -------------------------------------------------------------------

def _query_pr(repo: str, number: int) -> dict:
    owner, name = repo.split("/", 1)
    # -f (raw string) for owner/name: -F would coerce a numeric repo name to an int.
    out = proc.gh_json("api", "graphql", "-F", f"number={number}", "-f", f"owner={owner}",
                       "-f", f"name={name}", "-f", f"query={QUERY}")
    return out["data"]["repository"]["pullRequest"]


def _is_bot(author: dict | None) -> bool:
    return bool(author) and (author.get("__typename") == "Bot" or author["login"].endswith("[bot]"))


def _human_activity_times(pr: dict) -> list[datetime]:
    nodes = [(n, "createdAt") for n in pr["comments"]["nodes"]]
    nodes += [(n, "submittedAt") for n in pr["reviews"]["nodes"]]
    for thread in pr["reviewThreads"]["nodes"]:
        nodes += [(n, "createdAt") for n in thread["comments"]["nodes"]]
    return [_ts(n[key]) for n, key in nodes if n.get(key) and not _is_bot(n["author"])]


def _has_real_activity(entry: dict, pr: dict) -> bool:
    # Head first: head_sha is the head we reviewed, while updated_at is stored after the run,
    # so a push during the run leaves updatedAt unchanged.
    if pr["headRefOid"] != entry.get("head_sha"):
        return True
    if _ts(pr["updatedAt"]) <= _ts(entry["updated_at"]):
        return False
    last_run = _ts(entry.get("last_run_at"))
    return any(last_run is None or t > last_run for t in _human_activity_times(pr))


def _queue(args) -> int:
    cfg = config.load(args.name)
    rec = record.load(cfg)
    pre = _prefilter(cfg)
    login = None if pre.get("include_own_prs") else proc.run(
        ["gh", "api", "user", "--jq", ".login"]).stdout.strip()
    process, new_status = [], {}
    for number in sorted(rec["prs"]):
        entry = rec["prs"][number]
        if entry["status"] in ("merged", "closed"):
            continue
        pr = _query_pr(cfg["repo"], number)
        if pr["state"] in ("MERGED", "CLOSED"):
            new_status[number] = pr["state"].lower()
        elif entry["status"] in ("approved", "stalled"):
            continue
        elif pr["isDraft"] and not pre.get("include_drafts"):
            continue
        elif login is not None and (pr["author"] or {}).get("login") == login:
            continue
        elif entry["status"] == "escalated" and entry.get("decision"):
            process.append(number)
        elif entry["updated_at"] is None or _has_real_activity(entry, pr):
            process.append(number)
    if new_status:
        for number, status in new_status.items():
            rec["prs"][number]["status"] = status
        record.save(cfg, rec)
    print(json.dumps({"process": process}))
    return 0


# --- finish ------------------------------------------------------------------

def _bool(text: str) -> bool:
    if text not in ("true", "false"):
        raise argparse.ArgumentTypeError(f"{text!r} must be true or false")
    return text == "true"


def _finish(args) -> int:
    cfg = config.load(args.name)
    rec = record.load(cfg)
    if args.pr not in rec["prs"]:
        print(f"finish: PR {args.pr} is not in the record")
        return 1
    entry = rec["prs"][args.pr]
    record.end_stall(entry)  # a stalled team that reports done ends its stall
    if args.result == "not-interesting":
        del rec["prs"][args.pr]
    else:
        entry.pop("tab_id", None)
        entry.pop("run_started_at", None)
        if args.result in RETRY_RESULTS:
            record.release_slot(rec, args.pr)  # it spent almost nothing: the slot is free again
        else:
            now = proc.gh_json("pr", "view", str(args.pr), "--repo", cfg["repo"],
                               "--json", "updatedAt,headRefOid")
            # head_sha is the head the lead reviewed, so a push during the run is new activity;
            # updated_at and last_run_at are post-run, so the lead's own comments are not.
            head = now["headRefOid"] if args.head == "none" else args.head
            entry.update(updated_at=now["updatedAt"], head_sha=head, dry_run=args.dry_run,
                         last_run_at=record.now())
            entry.pop("decision", None)  # this run applied it; a new escalation needs a new one
            if args.result != "no-action":
                entry["status"] = args.result
    record.save(cfg, rec)
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("pending", help="next batch of new open PRs to classify (JSON)")
    p.add_argument("name")
    p.add_argument("--limit", type=int, default=PENDING_LIMIT,
                   help=f"batch size (default {PENDING_LIMIT}); lowest PR numbers first")
    p.set_defaults(func=_pending)

    p = subparsers.add_parser("commit-classified",
                              help="read classification JSON on stdin; record interesting PRs")
    p.add_argument("name")
    p.set_defaults(func=_commit_classified)

    p = subparsers.add_parser("queue", help="PR numbers to process (JSON); records merged and closed PRs")
    p.add_argument("name")
    p.set_defaults(func=_queue)

    p = subparsers.add_parser("finish", help="record the outcome of a PR run")
    p.add_argument("name")
    p.add_argument("pr", type=int)
    p.add_argument("result", choices=RESULTS)
    p.add_argument("--head", required=True, help="head SHA the lead reviewed, or none "
                   "(then the PR's current head is recorded)")
    p.add_argument("--dry-run", required=True, type=_bool, metavar="{true,false}",
                   help="whether the lead's result was a dry run")
    p.set_defaults(func=_finish)
