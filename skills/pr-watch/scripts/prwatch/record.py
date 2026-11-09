"""record.yaml (the supervisor's ledger) file I/O and its commands. Writes are atomic."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import config

STATUSES = ("new", "reviewed", "escalated", "approved", "merged", "closed", "stalled")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _record_path(cfg: dict) -> Path:
    return config.state_dir(cfg) / "record.yaml"


def load(cfg: dict) -> dict:
    path = _record_path(cfg)
    data = (yaml.safe_load(path.read_text()) if path.exists() else None) or {}
    prs = {int(k): v for k, v in (data.get("prs") or {}).items()}
    return {**data, "last_scanned_pr": data.get("last_scanned_pr"), "prs": prs}


def save(cfg: dict, rec: dict) -> None:
    _atomic_write(_record_path(cfg), yaml.safe_dump(rec, sort_keys=False))


def end_stall(entry: dict) -> None:
    """Put back the status a stalled entry had before it stalled (see set-status)."""
    if entry["status"] == "stalled" and "stalled_from" in entry:
        entry["status"] = entry.pop("stalled_from")


def start_fire(rec: dict, now: str) -> None:
    """Open a fire window: the leads started since `now` are counted against the per-fire cap."""
    rec["fire"] = {"started_at": now, "started": []}


def fire_started(rec: dict) -> list[int]:
    return rec.get("fire", {}).get("started", [])


def note_started(rec: dict, pr: int, now: str) -> None:
    """Count `pr` in the current window (opened at `now` when there is none); once only."""
    if "fire" not in rec:
        start_fire(rec, now)
    if pr not in rec["fire"]["started"]:
        rec["fire"]["started"].append(pr)


def release_slot(rec: dict, pr: int) -> None:
    """Give back the slot of a lead that spent almost nothing; a no-op when `pr` holds none."""
    if pr in fire_started(rec):
        rec["fire"]["started"].remove(pr)


def _cfg_for(args) -> dict:
    return config.load(args.name)


def _show(args) -> int:
    print(yaml.safe_dump(load(_cfg_for(args)), sort_keys=False), end="")
    return 0


def _set_status(args) -> int:
    cfg = _cfg_for(args)
    rec = load(cfg)
    if args.pr not in rec["prs"]:
        print(f"set-status: PR {args.pr} is not in the record")
        return 1
    entry = rec["prs"][args.pr]
    if args.status == "stalled":
        if entry["status"] != "stalled":  # end_stall restores it
            entry["stalled_from"] = entry["status"]
    else:
        entry.pop("stalled_from", None)
    entry["status"] = args.status
    save(cfg, rec)
    return 0


def _decide(args) -> int:
    cfg = _cfg_for(args)
    rec = load(cfg)
    if args.pr not in rec["prs"]:
        print(f"decide: PR {args.pr} is not in the record")
        return 1
    rec["prs"][args.pr]["decision"] = args.text
    save(cfg, rec)
    return 0


def _forget_dry_run(args) -> int:
    """Drop the stored result of every PR whose last result was a dry run, so each is reviewed
    again. Merged, closed and stalled entries keep theirs, and a pending decision stays."""
    cfg = _cfg_for(args)
    rec = load(cfg)
    for entry in rec["prs"].values():
        if entry.get("dry_run") is True and entry.get("status") not in ("merged", "closed", "stalled"):
            entry.update(status="new", updated_at=None, head_sha=None)
    save(cfg, rec)
    return 0


def _clear_scan_mark(args) -> int:
    cfg = _cfg_for(args)
    rec = load(cfg)
    rec["last_scanned_pr"] = None
    save(cfg, rec)
    return 0


def _fire_start(args) -> int:
    cfg = _cfg_for(args)
    rec = load(cfg)
    start_fire(rec, now())
    save(cfg, rec)
    print(json.dumps({"started_at": rec["fire"]["started_at"],
                      "max_reviews_per_fire": cfg.get("max_reviews_per_fire")}))
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("record", help="print the record as YAML")
    p.add_argument("name")
    p.set_defaults(func=_show)

    p = subparsers.add_parser("set-status", help="set a PR's record status")
    p.add_argument("name")
    p.add_argument("pr", type=int)
    p.add_argument("status", choices=STATUSES)
    p.set_defaults(func=_set_status)

    p = subparsers.add_parser("decide", help="store the user's decision for a PR in the record")
    p.add_argument("name")
    p.add_argument("pr", type=int)
    p.add_argument("text")
    p.set_defaults(func=_decide)

    p = subparsers.add_parser("forget-dry-run", help="clear the stored result of every dry-run PR not merged, closed or stalled")
    p.add_argument("name")
    p.set_defaults(func=_forget_dry_run)

    p = subparsers.add_parser("clear-scan-mark", help="forget last_scanned_pr")
    p.add_argument("name")
    p.set_defaults(func=_clear_scan_mark)

    p = subparsers.add_parser("fire-start", help="open a fire window: reviews started from now count "
                                                 "against max_reviews_per_fire (JSON)")
    p.add_argument("name")
    p.set_defaults(func=_fire_start)
