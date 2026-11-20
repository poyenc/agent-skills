"""Per-PR state under `<repo dir>/<PR>/` (`<repo>-dry-run` when dry_run): notes.md, reports/, runs/.
Writes are atomic."""
import json
import os
import re
import tempfile
from pathlib import Path

from . import config

DECISION_HEADING = "## Decision"
REVIEW_STATE_HEADING = "## Review state"
REVIEW_STATE_FIELDS = {"Last reviewed head": "last_reviewed_head", "Saved reports": "saved_reports",
                       "Status": "status"}


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def pr_dir(cfg: dict, repo: str, pr: int) -> Path:
    base = config.repo_dir(repo)
    if cfg["dry_run"]:
        base = base.with_name(f"{base.name}-dry-run")
    return base / str(pr)


def notes_path(cfg: dict, repo: str, pr: int) -> Path:
    return pr_dir(cfg, repo, pr) / "notes.md"


def runs_dir(cfg: dict, repo: str, pr: int) -> Path:
    return pr_dir(cfg, repo, pr) / "runs"


def reports_dir(cfg: dict, repo: str, pr: int, sha: str) -> Path:
    return pr_dir(cfg, repo, pr) / "reports" / sha


def _read_notes(cfg: dict, repo: str, pr: int) -> str:
    path = notes_path(cfg, repo, pr)
    return path.read_text() if path.exists() else ""


def _write_notes(cfg: dict, repo: str, pr: int, lines: list[str]) -> None:
    _atomic_write(notes_path(cfg, repo, pr), "\n".join(lines).rstrip("\n") + "\n")


def _section_span(lines: list[str], heading: str) -> tuple[int, int] | None:
    """Line range [start, end) of a `## ` section, heading included."""
    start = next((i for i, line in enumerate(lines) if line.rstrip() == heading), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def decision(cfg: dict, repo: str, pr: int) -> str:
    lines = _read_notes(cfg, repo, pr).splitlines()
    span = _section_span(lines, DECISION_HEADING)
    return "\n".join(lines[span[0] + 1:span[1]]).strip() if span else ""


def set_decision(cfg: dict, repo: str, pr: int, text: str) -> None:
    lines = _read_notes(cfg, repo, pr).splitlines()
    section = [DECISION_HEADING, "", *text.strip().splitlines(), ""]
    span = _section_span(lines, DECISION_HEADING)
    if span:
        lines[span[0]:span[1]] = section
    else:
        lines += ([""] if lines and lines[-1].strip() else []) + section
    _write_notes(cfg, repo, pr, lines)


def clear_decision(cfg: dict, repo: str, pr: int) -> None:
    lines = _read_notes(cfg, repo, pr).splitlines()
    span = _section_span(lines, DECISION_HEADING)
    if span:
        del lines[span[0]:span[1]]
        _write_notes(cfg, repo, pr, lines)


def append_notes(cfg: dict, repo: str, pr: int, heading: str, body: str) -> None:
    existing = _read_notes(cfg, repo, pr).rstrip("\n")
    prefix = existing + "\n\n" if existing else ""
    _atomic_write(notes_path(cfg, repo, pr), f"{prefix}## {heading}\n\n{body.strip()}\n")


def append_to_section(cfg: dict, repo: str, pr: int, heading: str, body: str) -> None:
    """Append body at the end of the `## heading` section, creating the section if absent."""
    lines = _read_notes(cfg, repo, pr).splitlines()
    span = _section_span(lines, f"## {heading}")
    if span is None:
        return append_notes(cfg, repo, pr, heading, body)
    end = span[1]
    while end > span[0] + 1 and not lines[end - 1].strip():
        end -= 1
    lines[end:span[1]] = ["", *body.strip().splitlines(), ""]
    _write_notes(cfg, repo, pr, lines)


def review_state(cfg: dict, repo: str, pr: int) -> dict:
    """`- <Field>: <value>` lines of the notes' `## Review state` section; None when absent.
    `Last reviewed head` is the SHA only; a `Saved reports` of `none` is None."""
    lines = _read_notes(cfg, repo, pr).splitlines()
    span = _section_span(lines, REVIEW_STATE_HEADING)
    found = dict.fromkeys(REVIEW_STATE_FIELDS.values())
    for line in lines[span[0] + 1:span[1]] if span else []:
        match = re.match(r"-\s*([^:]+):\s*(.*\S)\s*$", line)
        if match and match[1] in REVIEW_STATE_FIELDS:
            found[REVIEW_STATE_FIELDS[match[1]]] = match[2]
    if found["last_reviewed_head"]:
        found["last_reviewed_head"] = found["last_reviewed_head"].split()[0]
    if found["saved_reports"] == "none":
        found["saved_reports"] = None
    return found


def _paths(args) -> int:
    cfg = config.load(args.repo)
    out = {"pr_dir": pr_dir(cfg, args.repo, args.pr), "notes": notes_path(cfg, args.repo, args.pr),
           "runs": runs_dir(cfg, args.repo, args.pr), "reports": pr_dir(cfg, args.repo, args.pr) / "reports"}
    out["runs"].mkdir(parents=True, exist_ok=True)
    out["reports"].mkdir(parents=True, exist_ok=True)
    print(json.dumps({k: str(v) for k, v in out.items()}))
    return 0


def _decide(args) -> int:
    set_decision(config.load(args.repo), args.repo, args.pr, args.text)
    return 0


def _review_state(args) -> int:
    print(json.dumps(review_state(config.load(args.repo), args.repo, args.pr)))
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("paths", help="print a PR's state paths as JSON, creating runs/ and reports/")
    p.add_argument("repo")
    p.add_argument("pr", type=int)
    p.set_defaults(func=_paths)

    p = subparsers.add_parser("decide", help="write the user's decision into a PR's notes")
    p.add_argument("repo")
    p.add_argument("pr", type=int)
    p.add_argument("text")
    p.set_defaults(func=_decide)

    p = subparsers.add_parser("review-state", help="print the notes' review state as JSON")
    p.add_argument("repo")
    p.add_argument("pr", type=int)
    p.set_defaults(func=_review_state)
