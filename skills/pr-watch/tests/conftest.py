"""Shared pytest fixtures for pr-watch. Later test modules rely on these names.

- `config_dir` (autouse): temp dir; PR_WATCH_HOME points at it (configs live in it,
  state in `<config_dir>/<name>/`).
- `write_config(name="fmha", **overrides) -> pathlib.Path`: writes
  `<config_dir>/<name>.yaml` from a minimal valid base (`name`, `repo: o/r`,
  `checkout`, `interest`, `schedule`, `team`); overrides replace top-level
  keys; `drop=("key", ...)` omits top-level keys.
- `fake(tool_responses: dict[str, list]) -> Calls`: installs `gh` and `herdr` as
  symlinks to tests/fakes/fake_cli.py first on PATH, and sets HERDR_ENV=1,
  HERDR_WORKSPACE_ID=w7 and HERDR_PANE_ID=w7:p0 as inside the supervisor's herdr pane
  (delete them to test outside one).
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
def config_dir(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "config"
    path.mkdir()
    monkeypatch.setenv("PR_WATCH_HOME", str(path))
    return path


@pytest.fixture
def write_config(config_dir, tmp_path):
    def write(name: str = "fmha", drop: tuple = (), **overrides) -> Path:
        cfg = {
            "name": name,
            "repo": "o/r",
            "checkout": str(tmp_path / "checkout"),
            "interest": "x",
            "schedule": {"every": "24h"},
            "team": {
                "supervisor": {"harness": "claude", "model": "sonnet", "effort": "medium"},
                "scanner": {"model": "haiku"},
                "lead": {"harness": "claude", "model": "opus", "effort": "high"},
            },
        }
        cfg.update(overrides)
        for key in drop:
            cfg.pop(key, None)
        path = config_dir / f"{name}.yaml"
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
    monkeypatch.setenv("HERDR_WORKSPACE_ID", "w7")
    monkeypatch.setenv("HERDR_PANE_ID", "w7:p0")

    def install(tool_responses: dict[str, list] | None = None) -> Calls:
        entries = [
            {**r, "tool": tool}
            for tool, responses in (tool_responses or {}).items()
            for r in responses
        ]
        monkeypatch.setenv("FAKE_RESPONSES", json.dumps(entries))
        return Calls(calls_path)

    return install
