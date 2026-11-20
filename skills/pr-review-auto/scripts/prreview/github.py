"""Every GitHub action an agent takes, under the user's own account.

All `gh` calls go through `gh()`, the single choke point: it classifies the argv
(`is_write`) and refuses any write when `cfg["dry_run"]` is true (or missing), or
when the PR is not OPEN (merged, closed, or its state cannot be read; looked up
once per command). Each action also checks both before building a write and, if
either holds, appends what it would have done to the PR's notes instead. So such
a write is stopped twice.

Rules enforced here, not left to prompts:
- every posted comment/reply body starts with the agent header;
- the review event is always COMMENT (REQUEST_CHANGES never appears);
- approvals have an empty body, and are skipped on the user's own PR;
- comments are anchored on, and approvals given for, the commit the team reviewed
  (`--commit`), never whatever head GitHub has when the command runs.
"""
import json
import re
import sys

from . import config, gitops, proc, state

NOTES_HEADING = "Dry run actions"
ACTIONS = ("threads", "post-review", "comment", "reply", "resolve", "unresolve", "approve")
THREAD_ACTIONS = ("reply", "resolve", "unresolve")
COMMIT_ACTIONS = ("post-review", "approve")
WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
WRITE_PR_COMMANDS = {"review", "comment", "merge", "close", "edit", "reopen", "ready", "create"}
FIELD_FLAGS = {"-f", "-F", "--raw-field", "--field"}
STATE_JQ = 'if .merged then "MERGED" else (.state | ascii_upcase) end'

THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          id isResolved isOutdated path line
          comments(first: 50) {
            nodes { databaseId author { login } body createdAt url pullRequestReview { databaseId } }
          }
        }
      }
      comments(first: 100) { nodes { author { login } body createdAt } }
      reviews(first: 100) { nodes { author { login } body state submittedAt } }
    }
  }
}
"""

REPLY_MUTATION = """
mutation($thread: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $thread, body: $body}) {
    comment { id }
  }
}
"""

THREAD_MUTATION = """
mutation($thread: ID!) {
  %s(input: {threadId: $thread}) { thread { id isResolved } }
}
"""


class DryRunViolation(RuntimeError):
    """A write was attempted while dry_run is on, or to a PR that is not OPEN."""


# --- the choke point ---------------------------------------------------------

def _graphql_query(argv: list[str]) -> str | None:
    for flag, value in zip(argv, argv[1:]):
        if flag in FIELD_FLAGS and value.startswith("query="):
            return value[len("query="):]
    return None


def _http_method(argv: list[str]) -> str | None:
    for i, arg in enumerate(argv):
        if arg in ("-X", "--method") and i + 1 < len(argv):
            return argv[i + 1].upper()
        if arg.startswith("-X") and len(arg) > 2:
            return arg[2:].upper()
        if arg.startswith("--method="):
            return arg.split("=", 1)[1].upper()
    return None


def is_write(argv: list[str]) -> bool:
    """True if this `gh` argv may change GitHub state. Unsure means True."""
    if argv[:1] == ["pr"]:
        return len(argv) < 2 or argv[1] in WRITE_PR_COMMANDS
    if argv[:1] != ["api"]:
        return True
    rest = argv[1:]
    if "--input" in rest:
        return True
    if "graphql" in rest[:1]:
        query = _graphql_query(rest)
        return query is None or re.search(r"\bmutation\b", query) is not None
    method = _http_method(rest)
    if method is not None:
        return method in WRITE_METHODS
    # gh api sends a POST as soon as any field flag is present.
    return any(a in FIELD_FLAGS for a in rest)


def gh(cfg: dict, *argv: str, input: str | None = None) -> str:
    """Run `gh <argv>` and return stdout. The only place github.py calls gh."""
    if is_write(list(argv)):
        if cfg.get("dry_run", True):
            raise DryRunViolation(f"dry run: refusing gh {' '.join(argv)}")
        if (reason := _not_posted(cfg)) is not None:
            raise DryRunViolation(f"{reason}: refusing gh {' '.join(argv)}")
    return proc.run(["gh", *argv], input=input).stdout


def _not_posted(cfg: dict) -> str | None:
    """Why a live write must not reach `cfg["target"]` (repo, PR), or None when the PR is OPEN.

    The state is read once and kept in cfg; no target or a failed read fails closed."""
    if "pr_state" not in cfg:
        try:
            repo, pr = cfg["target"]
            cfg["pr_state"] = gh(cfg, "api", f"repos/{repo}/pulls/{pr}", "--jq", STATE_JQ).strip()
        except (KeyError, proc.CommandError):
            cfg["pr_state"] = None
    if cfg["pr_state"] == "OPEN":
        return None
    return f"PR is {cfg['pr_state']}" if cfg["pr_state"] else "PR state lookup failed"


def _held(cfg: dict) -> bool:
    """True when writes go into the notes instead of GitHub: dry run, or a PR that is not OPEN."""
    return cfg["dry_run"] or _not_posted(cfg) is not None


def _gh_json(cfg: dict, *argv: str):
    return json.loads(gh(cfg, *argv))


# --- helpers -----------------------------------------------------------------

def _login(cfg: dict) -> str:
    return gh(cfg, "api", "user", "--jq", ".login").strip()


def _header(login: str) -> str:
    return f"[Automated review by {login}'s review agent]"


def _with_header(login: str, body: str) -> str:
    body = body.strip()
    return body if body.startswith(_header(login)) else f"{_header(login)}\n\n{body}"


def _pr_info(cfg: dict, repo: str, pr: int) -> dict:
    return _gh_json(cfg, "pr", "view", str(pr), "--repo", repo,
                    "--json", "headRefOid,author")


def _raw_threads(cfg: dict, repo: str, pr: int) -> dict:
    owner, name = repo.split("/", 1)
    # -f (raw string) for owner/name: -F would coerce an all-digit repo name to an int.
    out = _gh_json(cfg, "api", "graphql", "-F", f"number={pr}", "-f", f"owner={owner}",
                   "-f", f"name={name}", "-f", f"query={THREADS_QUERY}")
    return out["data"]["repository"]["pullRequest"]


def _author(node: dict) -> str | None:
    return (node.get("author") or {}).get("login")


def _slim_comments(nodes: list[dict], *extra: str) -> list[dict]:
    return [{"author": _author(n), **{k: n.get(k) for k in (*extra, "body")},
             "createdAt": n.get("createdAt") or n.get("submittedAt")} for n in nodes]


def _dry_run_note(cfg: dict, repo: str, pr: int, action: str, target: str, body) -> None:
    """Record a write in the notes instead of GitHub; mark it when only the PR state held it."""
    marker = {} if cfg["dry_run"] else {"not_posted": _not_posted(cfg)}
    block = json.dumps({"action": action, "target": target, "body": body, **marker}, indent=2)
    state.append_to_section(cfg, repo, pr, NOTES_HEADING, f"```json\n{block}\n```")
    print(json.dumps({"dry_run": True, **marker}))


def _read_text() -> str:
    text = sys.stdin.read().strip()
    if not text:
        raise ValueError("empty body on stdin")
    return text


# --- actions -----------------------------------------------------------------

def _threads(cfg: dict, pr: int, login: str, args) -> int:
    raw = _raw_threads(cfg, args.repo, pr)
    threads = [{
        "id": t["id"], "isResolved": t["isResolved"], "isOutdated": t["isOutdated"],
        "path": t["path"], "line": t["line"],
        "url": (t["comments"]["nodes"] or [{}])[0].get("url"),  # the thread's first comment
        "comments": _slim_comments(t["comments"]["nodes"]),
    } for t in raw["reviewThreads"]["nodes"]]
    print(json.dumps({
        "threads": threads,
        "issue_comments": _slim_comments(raw["comments"]["nodes"]),
        "reviews": _slim_comments(raw["reviews"]["nodes"], "state"),
    }))
    return 0


def _parse_review_input(login: str) -> tuple[list[dict], list[dict]]:
    """Return (line comments, file-level comments) with headers applied."""
    comments = json.loads(sys.stdin.read())["comments"]
    if not comments:
        raise ValueError("no comments")
    line_comments, file_comments = [], []
    for c in comments:
        if not c.get("body", "").strip() or not c.get("path"):
            raise ValueError(f"comment needs path and non-empty body: {c}")
        body = _with_header(login, c["body"])
        if c.get("subject_type") == "file":
            file_comments.append({"path": c["path"], "subject_type": "file", "body": body})
        elif isinstance(c.get("line"), int):
            line_comments.append({"path": c["path"], "line": c["line"],
                                  "side": c.get("side", "RIGHT"), "body": body})
        else:
            raise ValueError(f"comment needs an integer line or subject_type 'file': {c}")
    return line_comments, file_comments


def _post_review(cfg: dict, pr: int, login: str, args) -> int:
    try:
        line_comments, file_comments = _parse_review_input(login)
    except (ValueError, KeyError, TypeError, AttributeError) as e:  # JSONDecodeError is a ValueError
        print(f"post-review: invalid input: {e}", file=sys.stderr)
        return 1
    repo = args.repo
    if _held(cfg):
        _dry_run_note(cfg, repo, pr, "post-review", f"{repo}#{pr}", line_comments + file_comments)
        return 0
    head = args.commit
    posted = {"review_id": None, "comment_ids": []}
    wrote = False
    try:
        if line_comments:
            payload = {"commit_id": head, "event": "COMMENT", "body": "", "comments": line_comments}
            response = gh(cfg, "api", "-X", "POST", f"repos/{repo}/pulls/{pr}/reviews",
                          "--input", "-", input=json.dumps(payload))
            wrote = True
            posted["review_id"] = json.loads(response)["id"]
        for c in file_comments:
            response = gh(cfg, "api", "-X", "POST", f"repos/{repo}/pulls/{pr}/comments",
                          "--input", "-", input=json.dumps({**c, "commit_id": head}))
            wrote = True
            posted["comment_ids"].append(json.loads(response)["id"])
        thread_ids = _created_thread_ids(cfg, repo, pr, posted)
    except Exception as e:
        if not wrote:
            raise
        # Something is already public: report it so a retry does not post duplicates.
        try:
            thread_ids = _created_thread_ids(cfg, repo, pr, posted)
        except Exception:
            thread_ids = None  # null: unknown
        print(json.dumps({"error": str(e), **posted, "thread_ids": thread_ids}))
        return 1
    print(json.dumps({"thread_ids": thread_ids}))
    return 0


def _created_thread_ids(cfg: dict, repo: str, pr: int, posted: dict) -> list[str]:
    """Threads whose FIRST comment belongs to the review or file comments just posted.

    databaseIds are exact, unlike matching on path+line+body.
    """
    created = []
    for t in _raw_threads(cfg, repo, pr)["reviewThreads"]["nodes"]:
        first = (t["comments"]["nodes"] or [{}])[0]
        review = (first.get("pullRequestReview") or {}).get("databaseId")
        if (review is not None and review == posted["review_id"]) \
                or first.get("databaseId") in posted["comment_ids"]:
            created.append(t["id"])
    return created


def _comment(cfg: dict, pr: int, login: str, args) -> int:
    body = _with_header(login, _read_text())
    repo = args.repo
    if _held(cfg):
        _dry_run_note(cfg, repo, pr, "comment", f"{repo}#{pr}", body)
        return 0
    gh(cfg, "api", "-X", "POST", f"repos/{repo}/issues/{pr}/comments", "--input", "-",
       input=json.dumps({"body": body}))
    print(json.dumps({"ok": True}))
    return 0


def _reply(cfg: dict, pr: int, login: str, args) -> int:
    thread_id = args.thread_id
    body = _with_header(login, _read_text())
    if _held(cfg):
        _dry_run_note(cfg, args.repo, pr, "reply", f"{args.repo}#{pr} thread {thread_id}", body)
        return 0
    gh(cfg, "api", "graphql", "-f", f"thread={thread_id}", "-f", f"body={body}",
       "-f", f"query={REPLY_MUTATION}")
    print(json.dumps({"ok": True}))
    return 0


def _set_resolved(action: str, mutation: str):
    def handler(cfg: dict, pr: int, login: str, args) -> int:
        thread_id = args.thread_id
        if _held(cfg):
            _dry_run_note(cfg, args.repo, pr, action, f"{args.repo}#{pr} thread {thread_id}", "")
            return 0
        gh(cfg, "api", "graphql", "-f", f"thread={thread_id}",
           "-f", f"query={THREAD_MUTATION % mutation}")
        print(json.dumps({"ok": True}))
        return 0
    return handler


def _approve(cfg: dict, pr: int, login: str, args) -> int:
    info = _pr_info(cfg, args.repo, pr)
    if _author(info) == login:
        print(json.dumps({"skipped": "own-pr"}))
        return 0
    if info["headRefOid"] != args.commit:  # commits we did not review were pushed
        print(json.dumps({"skipped": "head-moved"}))
        return 0
    repo = args.repo
    if _held(cfg):
        _dry_run_note(cfg, repo, pr, "approve", f"{repo}#{pr}", "")
        return 0
    gh(cfg, "pr", "review", str(pr), "--repo", repo, "--approve", "--body", "")
    print(json.dumps({"ok": True}))
    return 0


HANDLERS = {
    "threads": _threads, "post-review": _post_review, "comment": _comment, "reply": _reply,
    "resolve": _set_resolved("resolve", "resolveReviewThread"),
    "unresolve": _set_resolved("unresolve", "unresolveReviewThread"),
    "approve": _approve,
}


def _run(args) -> int:
    cfg = {**config.load(args.repo), "target": (args.repo, args.pr)}
    if args.action in THREAD_ACTIONS and not args.thread_id:
        print(f"gh {args.action}: thread id required", file=sys.stderr)
        return 1
    if args.action in COMMIT_ACTIONS and not args.commit:
        print(f"gh {args.action}: --commit <reviewed head sha> required", file=sys.stderr)
        return 1
    try:
        return HANDLERS[args.action](cfg, args.pr, _login(cfg), args)
    except ValueError as e:
        print(f"gh {args.action}: {e}", file=sys.stderr)
        return 1


def register(subparsers) -> None:
    p = subparsers.add_parser("gh", help="GitHub action on a PR (body/payload on stdin)")
    p.add_argument("repo")
    p.add_argument("pr", type=gitops.positive_int)
    p.add_argument("action", choices=ACTIONS)
    p.add_argument("thread_id", nargs="?")
    p.add_argument("--commit", help="post-review, approve: the head commit the team reviewed")
    p.set_defaults(func=_run)
