import json
import os
from datetime import datetime

import pytest
import yaml

from prwatch import cli, config, record


@pytest.fixture
def cfg(write_config):
    write_config()
    return config.load("fmha")


def test_load_missing_is_empty(cfg):
    assert record.load(cfg) == {"last_scanned_pr": None, "prs": {}}


def test_save_roundtrip_int_keys(cfg):
    entry = {"reason": "r", "status": "new", "tab_id": "t1", "future_key": 7}
    rec = {"last_scanned_pr": 12, "prs": {5: entry}}
    record.save(cfg, rec)
    loaded = record.load(cfg)
    assert loaded == rec
    assert all(isinstance(k, int) for k in loaded["prs"])


def test_save_is_atomic(cfg, monkeypatch):
    record.save(cfg, {"last_scanned_pr": 1, "prs": {}})
    path = config.state_dir(cfg) / "record.yaml"
    before = path.read_text()

    def boom(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        record.save(cfg, {"last_scanned_pr": 2, "prs": {}})
    assert path.read_text() == before


def test_record_lives_under_home_name_directory(cfg, config_dir):
    record.save(cfg, {"last_scanned_pr": 1, "prs": {}})
    assert (config_dir / "fmha" / "record.yaml").is_file()


def test_set_status_rejects_unknown(cfg):
    record.save(cfg, {"last_scanned_pr": None, "prs": {5: {"status": "new"}}})
    with pytest.raises(SystemExit) as exc:
        cli.main(["set-status", "fmha", "5", "done"])
    assert exc.value.code != 0
    assert record.load(cfg)["prs"][5]["status"] == "new"


def test_set_status_updates_and_rejects_unknown_pr(cfg):
    record.save(cfg, {"last_scanned_pr": None, "prs": {5: {"status": "new", "tab_id": "t"}}})
    assert cli.main(["set-status", "fmha", "5", "merged"]) == 0
    assert record.load(cfg)["prs"][5] == {"status": "merged", "tab_id": "t"}
    assert cli.main(["set-status", "fmha", "6", "merged"]) != 0


def test_set_status_stalled_remembers_previous(cfg):
    record.save(cfg, {"last_scanned_pr": None, "prs": {5: {"status": "escalated"}}})
    assert cli.main(["set-status", "fmha", "5", "stalled"]) == 0
    assert record.load(cfg)["prs"][5] == {"status": "stalled", "stalled_from": "escalated"}
    assert cli.main(["set-status", "fmha", "5", "stalled"]) == 0  # repeated each fire
    assert record.load(cfg)["prs"][5]["stalled_from"] == "escalated"
    assert cli.main(["set-status", "fmha", "5", "reviewed"]) == 0
    assert record.load(cfg)["prs"][5] == {"status": "reviewed"}

def test_record_prints_yaml(cfg, capsys):
    record.save(cfg, {"last_scanned_pr": 3, "prs": {5: {"status": "new"}}})
    assert cli.main(["record", "fmha"]) == 0
    assert yaml.safe_load(capsys.readouterr().out) == {"last_scanned_pr": 3, "prs": {5: {"status": "new"}}}


def test_decide_stores_decision_in_record(cfg):
    record.save(cfg, {"last_scanned_pr": None, "prs": {5: {"status": "escalated"}}})
    assert cli.main(["decide", "fmha", "5", "ship it"]) == 0
    assert record.load(cfg)["prs"][5] == {"status": "escalated", "decision": "ship it"}
    assert cli.main(["decide", "fmha", "5", "second"]) == 0
    assert record.load(cfg)["prs"][5]["decision"] == "second"


def test_decide_unknown_pr_fails(cfg):
    assert cli.main(["decide", "fmha", "5", "ship it"]) != 0
    assert record.load(cfg)["prs"] == {}


def test_forget_dry_run_clears_only_dry_run_results(cfg):
    done = {"reason": "r", "updated_at": "2026-11-02T00:00:00Z", "head_sha": "h1",
            "last_run_at": "2026-11-02T00:00:01Z"}
    record.save(cfg, {"last_scanned_pr": 9, "prs": {
        1: {**done, "status": "reviewed", "dry_run": True},
        2: {**done, "status": "approved", "dry_run": False},
        3: {**done, "status": "escalated", "dry_run": True, "decision": "go on"},
        4: {**done, "status": "reviewed"},
        5: {**done, "status": "merged", "dry_run": True},
        6: {**done, "status": "closed", "dry_run": True},
        7: {**done, "status": "stalled", "stalled_from": "reviewed", "dry_run": True},
    }})
    assert cli.main(["forget-dry-run", "fmha"]) == 0
    rec = record.load(cfg)
    cleared = {"status": "new", "updated_at": None, "head_sha": None}
    assert rec["prs"][1] == {**done, **cleared, "dry_run": True}
    assert rec["prs"][3] == {**done, **cleared, "dry_run": True, "decision": "go on"}
    assert rec["prs"][2] == {**done, "status": "approved", "dry_run": False}
    assert rec["prs"][4] == {**done, "status": "reviewed"}
    assert rec["prs"][5] == {**done, "status": "merged", "dry_run": True}
    assert rec["prs"][6] == {**done, "status": "closed", "dry_run": True}
    assert rec["prs"][7] == {**done, "status": "stalled", "stalled_from": "reviewed", "dry_run": True}
    assert rec["last_scanned_pr"] == 9


def test_clear_scan_mark(cfg):
    record.save(cfg, {"last_scanned_pr": 3, "prs": {5: {"status": "new"}}})
    assert cli.main(["clear-scan-mark", "fmha"]) == 0
    assert record.load(cfg) == {"last_scanned_pr": None, "prs": {5: {"status": "new"}}}


def test_fire_start_opens_window_and_keeps_prs(cfg, capsys):
    prs = {5: {"status": "new"}, 9: {"status": "reviewed", "tab_id": "t"}}
    record.save(cfg, {"last_scanned_pr": 9, "prs": prs, "fire": {"started_at": "old", "started": [5]}})
    assert cli.main(["fire-start", "fmha"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["max_reviews_per_fire"] == 4
    rec = record.load(cfg)
    assert rec["prs"] == prs and rec["last_scanned_pr"] == 9
    assert rec["fire"] == {"started_at": out["started_at"], "started": []}
    assert datetime.fromisoformat(out["started_at"]).tzinfo is not None


def test_fire_start_resets_started(cfg, capsys):
    record.save(cfg, {"last_scanned_pr": None, "prs": {}, "fire": {"started_at": "old", "started": [5, 6]}})
    assert cli.main(["fire-start", "fmha"]) == 0
    assert record.load(cfg)["fire"]["started"] == []
    assert record.fire_started(record.load(cfg)) == []


def test_note_started_is_idempotent_and_creates_window(cfg):
    rec = {"last_scanned_pr": None, "prs": {}}
    assert record.fire_started(rec) == []
    record.note_started(rec, 5, "T1")
    record.note_started(rec, 5, "T2")
    record.note_started(rec, 6, "T3")
    assert rec["fire"] == {"started_at": "T1", "started": [5, 6]}
    assert record.fire_started(rec) == [5, 6]
    record.start_fire(rec, "T4")
    assert rec["fire"] == {"started_at": "T4", "started": []}


def test_release_slot_missing_pr_is_noop():
    rec = {"prs": {}}
    record.release_slot(rec, 5)
    assert rec == {"prs": {}}
    record.note_started(rec, 5, "T1")
    record.release_slot(rec, 6)
    record.release_slot(rec, 5)
    record.release_slot(rec, 5)
    assert rec["fire"] == {"started_at": "T1", "started": []}
