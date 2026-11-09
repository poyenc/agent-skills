"""PR tabs in the supervisor's own herdr workspace: tab-open, tab-close, running.

The supervisor is the invoking session, so its herdr environment names the workspace
(`HERDR_WORKSPACE_ID`) and the pane leads report to (`HERDR_PANE_ID`). Each PR run owns one tab
there, recorded in the PR's entry as `tab_id` and `run_started_at`. The lead started in the tab
runs the pr-review skill; `tab-open` hands it the start message and nothing else.
"""
import json
import os
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config, proc, record

GONE_TAB_ERRORS = ("tab_not_found", "workspace_not_found")
LEAD_AGENT_SUFFIX = "lead"


def lead_agent_name(cfg: dict) -> str:
    return f"prw-{cfg['name']}-{LEAD_AGENT_SUFFIX}"


def harness_argv(role_cfg: dict, prompt_file: Path) -> list[str]:
    harness, model, effort = role_cfg["harness"], role_cfg["model"], role_cfg["effort"]
    argv = ["--system-prompt-file", str(prompt_file)]
    if harness == "claude":
        return argv + ["--model", model, "--effort", effort, "--dangerously-skip-permissions"]
    if harness == "pi":
        return argv + ["--model", f"{model}:{effort}"]
    raise ValueError(f"unsupported harness {harness!r}")


def start_lead(cfg: dict, pane_id: str) -> str:
    name = lead_agent_name(cfg)
    lead = cfg["team"]["lead"]
    persona = Path(cfg["persona_dir"]) / "orchestrator" / "system-prompt.md"
    proc.run(["herdr", "agent", "start", name, "--kind", lead["harness"],
              "--pane", pane_id, "--timeout", "120000", "--", *harness_argv(lead, persona)])
    return name


def start_message(cfg: dict, pr: int, entry: dict, supervisor_pane: str) -> str:
    """`<invoke> <owner>/<repo> <PR> --checkout <path> --supervisor <pane> [--interest ..] [--decision ..]`."""
    parts = [config.lead_invoke(cfg), cfg["repo"], str(pr), "--checkout", cfg["checkout"],
             "--supervisor", supervisor_pane]
    for flag, text in (("--interest", cfg.get("interest")), ("--decision", entry.get("decision"))):
        text = " ".join(str(text or "").split())  # one line: the message is a typed prompt
        if text:
            parts += [flag, text]
    return " ".join(shlex.quote(p) for p in parts)  # a no-op for plain words, quotes free text


def _entry(rec: dict, pr: int) -> dict:
    if pr not in rec["prs"]:
        raise proc.CommandError(["pr-watch"], 1, f"PR {pr} is not in the record")
    return rec["prs"][pr]


def _supervisor_env(command: str) -> tuple[str, str] | None:
    missing = [v for v in ("HERDR_WORKSPACE_ID", "HERDR_PANE_ID") if not os.environ.get(v)]
    if missing:
        print(f"pr-watch {command}: {' and '.join(missing)} not set; run it from the supervisor's "
              "herdr pane", file=sys.stderr)
        return None
    return os.environ["HERDR_WORKSPACE_ID"], os.environ["HERDR_PANE_ID"]


def _tab_open(args) -> int:
    cfg = config.load(args.name)
    rec = record.load(cfg)
    entry = _entry(rec, args.pr)
    env = _supervisor_env("tab-open")
    if env is None:
        return 1
    workspace, supervisor_pane = env
    if not args.ignore_cap:
        cap = cfg["max_reviews_per_fire"]
        if len(record.fire_started(rec)) >= cap:
            print(f"tab-open: cap reached ({cap} of {cap} reviews started this fire); "
                  f"PR {args.pr} stays queued for the next fire", file=sys.stderr)
            return 1
    message = start_message(cfg, args.pr, entry, supervisor_pane)
    tab = proc.herdr_json("tab", "create", "--workspace", workspace, "--cwd", cfg["checkout"],
                          "--label", f"PR {args.pr}", "--no-focus")["result"]
    record.end_stall(entry)  # a retry runs as the original run
    # Save before starting the lead so a failed start still leaves the tab findable by tab-close.
    now = record.now()
    entry.update(tab_id=tab["tab"]["tab_id"], run_started_at=now)
    if not args.ignore_cap:
        record.note_started(rec, args.pr, now)
    record.save(cfg, rec)
    lead = start_lead(cfg, tab["root_pane"]["pane_id"])
    proc.run(["herdr", "agent", "prompt", lead, message])
    return 0


def _tab_close(args) -> int:
    cfg = config.load(args.name)
    rec = record.load(cfg)
    entry = _entry(rec, args.pr)
    if "tab_id" not in entry:
        print(f"tab-close: PR {args.pr} has no open tab")
        return 1
    try:
        proc.run(["herdr", "tab", "close", entry["tab_id"]])
    except proc.CommandError as e:
        if not any(code in e.stderr for code in GONE_TAB_ERRORS):
            raise
        print(f"tab-close: herdr does not know tab {entry['tab_id']}; treating it as already closed",
              file=sys.stderr)
    entry.pop("tab_id")
    record.save(cfg, rec)
    return 0


def _running(args) -> int:
    cfg = config.load(args.name)
    rec = record.load(cfg)
    pr = next((n for n, e in sorted(rec["prs"].items()) if e.get("tab_id")), None)
    out = {"pr": pr, "tab_id": None, "elapsed_minutes": None, "over_limit": False}
    if pr is not None:
        entry = rec["prs"][pr]
        started = datetime.fromisoformat(entry["run_started_at"])
        elapsed = datetime.now(timezone.utc) - started
        out.update(tab_id=entry["tab_id"], elapsed_minutes=int(elapsed.total_seconds() // 60),
                   over_limit=elapsed > config.parse_duration(cfg["max_pr_duration"]))
    print(json.dumps(out))
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("running", help="the PR run in progress, its elapsed minutes and "
                                              "whether it is over the limit (JSON)")
    p.add_argument("name")
    p.set_defaults(func=_running)

    for command, handler, help_text in (
        ("tab-open", _tab_open, "open a PR tab in this workspace and start its lead"),
        ("tab-close", _tab_close, "close a PR tab"),
    ):
        p = subparsers.add_parser(command, help=help_text)
        p.add_argument("name")
        p.add_argument("pr", type=int)
        if command == "tab-open":
            p.add_argument("--ignore-cap", action="store_true",
                           help="skip the per-fire cap and do not count the PR (user-ordered retry)")
        p.set_defaults(func=handler)
