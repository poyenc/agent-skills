"""Shared pytest fixtures for pr-review-auto. Later test modules rely on these names.

- `review_home` (autouse): temp dir; PR_REVIEW_AUTO_HOME points at it.
- `write_config(repo="o/r", **overrides) -> pathlib.Path`: writes
  `<review_home>/<owner>/<name>/config.yaml` from a minimal valid base (`team.reviewer`,
  `team.architect`); overrides replace top-level keys; `drop=("key", ...)` omits
  top-level keys.
- `fake(tool_responses: dict[str, list]) -> Calls`: installs `gh` and `herdr`
  as symlinks to tests/fakes/fake_cli.py first on PATH, and sets
  HERDR_ENV=1 as inside a herdr session (delete it to test outside one).
  `tool_responses` maps tool name -> list of {"match": [argv prefix...],
  "stdout": str, "exit": int}; first match wins, unmatched prints `{}` exit 0.
  Call it again to replace responses. Returns `Calls`.
- `Calls.of(tool) -> list[list[str]]`: argv lists logged for that tool, in order.
  `Calls.all` -> list of {"tool", "argv"} dicts.
"""
import json
import os
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
FAKE_CLI = Path(__file__).resolve().parent / "fakes" / "fake_cli.py"
FAKE_TOOLS = ("gh", "herdr")

sys.path.insert(0, str(SCRIPTS_DIR))


class Calls:
    def __init__(self, path: Path):
        self.path = path

    @property
    def all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]

    def of(self, tool: str) -> list[list[str]]:
        return [c["argv"] for c in self.all if c["tool"] == tool]


@pytest.fixture(autouse=True)
def review_home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("PR_REVIEW_AUTO_HOME", str(path))
    return path


@pytest.fixture
def write_config(review_home):
    def write(repo: str = "o/r", drop: tuple = (), **overrides) -> Path:
        cfg = {
            "team": {
                "reviewer": {"harness": "pi", "model": "p/m", "effort": "high"},
                "architect": {"harness": "claude", "model": "opus", "effort": "high"},
            },
        }
        cfg.update(overrides)
        for key in drop:
            cfg.pop(key, None)
        path = review_home / repo / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(cfg))
        return path

    return write


@pytest.fixture
def fake(tmp_path, monkeypatch):
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    for tool in FAKE_TOOLS:
        (bin_dir / tool).symlink_to(FAKE_CLI)
    calls_path = tmp_path / "fake_calls.jsonl"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CALLS", str(calls_path))
    monkeypatch.setenv("HERDR_ENV", "1")

    def install(tool_responses: dict[str, list] | None = None) -> Calls:
        entries = [
            {**r, "tool": tool}
            for tool, responses in (tool_responses or {}).items()
            for r in responses
        ]
        monkeypatch.setenv("FAKE_RESPONSES", json.dumps(entries))
        return Calls(calls_path)

    return install
