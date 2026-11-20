"""Per-PR lock `<pr dir>/lock`: one run at a time on a PR.

The file is created with O_CREAT|O_EXCL and holds `{"holder", "since"}`. A lock older
than `lock_stale_after` is abandoned and replaced; a lock file that cannot be read
(its holder died between create and write) ages by its modification time.
"""
import datetime
import json
import os
from pathlib import Path

from . import config, state


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _path(cfg: dict, repo: str, pr: int) -> Path:
    return state.pr_dir(cfg, repo, pr) / "lock"


def _read(path: Path) -> dict:
    """The lock's holder and since; since falls back to the file's mtime when unreadable."""
    try:
        data = json.loads(path.read_text())
        since = datetime.datetime.fromisoformat(data["since"])
        if since.tzinfo is None:
            since = since.replace(tzinfo=datetime.timezone.utc)
        return {"holder": str(data["holder"]), "since": since}
    except (ValueError, KeyError, TypeError):
        since = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)
        return {"holder": "unknown", "since": since}


def _create(path: Path, holder: str) -> bool:
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as f:
        json.dump({"holder": holder, "since": _now().isoformat()}, f)
    return True


def acquire(cfg: dict, repo: str, pr: int, holder: str) -> dict:
    path = _path(cfg, repo, pr)
    path.parent.mkdir(parents=True, exist_ok=True)
    stale_after = config.parse_duration(cfg["lock_stale_after"])
    while True:
        if _create(path, holder):
            return {"locked": True}
        try:
            current = _read(path)
        except FileNotFoundError:  # released between our create and read: try again
            continue
        if _now() - current["since"] <= stale_after:
            return {"busy": True, "holder": current["holder"], "since": current["since"].isoformat()}
        try:
            if _read(path) == current:  # still the stale lock we saw, not a fresh takeover
                path.unlink()
        except FileNotFoundError:
            pass


def release(cfg: dict, repo: str, pr: int, holder: str) -> dict:
    path = _path(cfg, repo, pr)
    try:
        if _read(path)["holder"] != holder:
            return {"unlocked": False}
        path.unlink()
    except FileNotFoundError:
        return {"unlocked": False}
    return {"unlocked": True}


def _lock(args) -> int:
    print(json.dumps(acquire(config.load(args.repo), args.repo, args.pr, args.holder)))
    return 0


def _unlock(args) -> int:
    print(json.dumps(release(config.load(args.repo), args.repo, args.pr, args.holder)))
    return 0


def register(subparsers) -> None:
    for name, handler, help_text in (
            ("lock", _lock, "take a PR's lock: {locked} or {busy, holder, since}"),
            ("unlock", _unlock, "release a PR's lock if --holder owns it")):
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("repo")
        p.add_argument("pr", type=int)
        p.add_argument("--holder", required=True)
        p.set_defaults(func=handler)
