import json
import os

import pytest

from prreview import cli, config, state

REPO = "o/r"


@pytest.fixture
def cfg(write_config):
    write_config()
    return config.load(REPO)


@pytest.mark.parametrize("dry_run, suffix", [(True, "r-dry-run"), (False, "r")])
def test_pr_dir_dry_run_suffix(write_config, review_home, dry_run, suffix):
    write_config(dry_run=dry_run)
    assert state.pr_dir(config.load(REPO), REPO, 7) == review_home / "o" / suffix / "7"


def test_pr_dir_dry_run_suffix_rocm(write_config, review_home):
    write_config("ROCm/rocm-libraries")
    path = state.pr_dir(config.load("ROCm/rocm-libraries"), "ROCm/rocm-libraries", 9187)
    assert path == review_home / "ROCm" / "rocm-libraries-dry-run" / "9187"


def test_paths_layout(cfg):
    pr_dir = state.pr_dir(cfg, REPO, 7)
    assert state.notes_path(cfg, REPO, 7) == pr_dir / "notes.md"
    assert state.runs_dir(cfg, REPO, 7) == pr_dir / "runs"
    assert state.reports_dir(cfg, REPO, 7, "abc123") == pr_dir / "reports" / "abc123"


def test_paths_json(cfg, capsys, review_home):
    assert cli.main(["paths", REPO, "7"]) == 0
    pr_dir = review_home / "o" / "r-dry-run" / "7"
    assert json.loads(capsys.readouterr().out) == {
        "pr_dir": str(pr_dir), "notes": str(pr_dir / "notes.md"),
        "runs": str(pr_dir / "runs"), "reports": str(pr_dir / "reports"),
    }
    assert (pr_dir / "runs").is_dir() and (pr_dir / "reports").is_dir()


def test_decision_empty_until_set(cfg):
    assert state.decision(cfg, REPO, 7) == ""
    state.append_notes(cfg, REPO, 7, "Threads", "t1")
    assert state.decision(cfg, REPO, 7) == ""


def test_set_decision_replaces_section(cfg):
    state.append_notes(cfg, REPO, 7, "Head", "abc")
    state.set_decision(cfg, REPO, 7, "first")
    state.append_notes(cfg, REPO, 7, "Later", "after")
    assert state.decision(cfg, REPO, 7) == "first"
    state.set_decision(cfg, REPO, 7, "second\nline two")
    assert state.decision(cfg, REPO, 7) == "second\nline two"
    text = state.notes_path(cfg, REPO, 7).read_text()
    assert "first" not in text
    assert "## Head\n\nabc" in text and "## Later\n\nafter" in text
    assert text.count("## Decision") == 1


def test_set_decision_creates_notes_file(cfg):
    state.set_decision(cfg, REPO, 9, "go")
    assert state.notes_path(cfg, REPO, 9) == state.pr_dir(cfg, REPO, 9) / "notes.md"
    assert state.decision(cfg, REPO, 9) == "go"


def test_clear_decision_removes_only_that_section(cfg):
    state.append_notes(cfg, REPO, 7, "Head", "abc")
    state.set_decision(cfg, REPO, 7, "go")
    state.clear_decision(cfg, REPO, 7)
    assert state.decision(cfg, REPO, 7) == ""
    assert state.notes_path(cfg, REPO, 7).read_text() == "## Head\n\nabc\n"


def test_write_is_atomic(cfg, monkeypatch):
    state.append_notes(cfg, REPO, 7, "Head", "abc")
    path = state.notes_path(cfg, REPO, 7)
    before = path.read_text()

    def boom(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        state.set_decision(cfg, REPO, 7, "go")
    assert path.read_text() == before
    assert [p.name for p in path.parent.iterdir()] == ["notes.md"]


def test_decide_cli(cfg):
    assert cli.main(["decide", REPO, "5", "ship it"]) == 0
    assert state.decision(cfg, REPO, 5) == "ship it"


def test_append_to_section_reuses_heading(cfg):
    state.append_to_section(cfg, REPO, 7, "Dry run actions", "one")
    state.append_notes(cfg, REPO, 7, "Later", "after")
    state.append_to_section(cfg, REPO, 7, "Dry run actions", "two")
    text = state.notes_path(cfg, REPO, 7).read_text()
    assert text == "## Dry run actions\n\none\n\ntwo\n\n## Later\n\nafter\n"


NOTES = """# PR 7 notes

## Review state
- Last reviewed head: 0123abc (base 9999fff) at 2026-11-09T10:00Z
- Saved reports: 0123abc
- Status: approved at 0123abc

## Threads
- Last reviewed head: not this one
"""


def test_review_state_parses_lines(cfg):
    path = state.notes_path(cfg, REPO, 7)
    path.parent.mkdir(parents=True)
    path.write_text(NOTES)
    assert state.review_state(cfg, REPO, 7) == {
        "last_reviewed_head": "0123abc", "saved_reports": "0123abc", "status": "approved at 0123abc",
    }


def test_review_state_missing_values_are_none(cfg):
    assert state.review_state(cfg, REPO, 7) == {"last_reviewed_head": None, "saved_reports": None, "status": None}
    state.append_notes(cfg, REPO, 7, "Review state", "- Saved reports: none")
    assert state.review_state(cfg, REPO, 7) == {"last_reviewed_head": None, "saved_reports": None, "status": None}


def test_review_state_cli(cfg, capsys):
    state.append_notes(cfg, REPO, 7, "Review state", "- Last reviewed head: abc (base def) at now")
    assert cli.main(["review-state", REPO, "7"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "last_reviewed_head": "abc", "saved_reports": None, "status": None,
    }
