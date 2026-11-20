import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from prwatch import cli, config, record, team

TAB_CREATE = {"match": ["tab", "create"], "stdout": json.dumps({"result": {
    "tab": {"tab_id": "w7:t2"}, "root_pane": {"pane_id": "w7:p2"}}})}


def seed_record(write_config, **entry):
    write_config(persona_dir="/personas")
    cfg = config.load("fmha")
    rec = record.load(cfg)
    rec["prs"][42] = {"reason": "r", "status": "new", "updated_at": None, "head_sha": None,
                      "last_run_at": None, **entry}
    record.save(cfg, rec)
    return cfg


def herdr_prefixes(calls, n=2):
    return [a[:n] for a in calls.of("herdr")]


def test_claude_argv():
    role = {"harness": "claude", "model": "opus", "effort": "high"}
    assert team.harness_argv(role, Path("/p/f.md")) == [
        "--system-prompt-file", "/p/f.md", "--model", "opus", "--effort", "high",
        "--dangerously-skip-permissions",
    ]


def test_pi_argv():
    role = {"harness": "pi", "model": "prov/m", "effort": "high"}
    assert team.harness_argv(role, Path("/p/f.md")) == [
        "--system-prompt-file", "/p/f.md", "--model", "prov/m:high",
    ]


def test_tab_open_in_supervisor_workspace(write_config, fake):
    cfg = seed_record(write_config)
    calls = fake({"herdr": [TAB_CREATE]})
    assert cli.main(["tab-open", "fmha", "42"]) == 0
    herdr = calls.of("herdr")
    assert herdr_prefixes(calls) == [["tab", "create"], ["agent", "start"], ["agent", "prompt"]]
    assert not [a for a in herdr if a[0] == "workspace"]  # the supervisor's own workspace is used
    create = herdr[0]
    assert create[create.index("--workspace") + 1] == "w7"  # $HERDR_WORKSPACE_ID
    assert create[create.index("--label") + 1] == "PR 42"
    assert create[create.index("--cwd") + 1] == cfg["checkout"]
    assert "--no-focus" in create
    start = herdr[1]
    assert start[:7] == ["agent", "start", "prw-fmha-lead", "--kind", "claude", "--pane", "w7:p2"]
    sep = start.index("--")
    assert start[sep + 1:] == [
        "--system-prompt-file", "/personas/orchestrator/system-prompt.md",
        "--model", "opus", "--effort", "high", "--dangerously-skip-permissions"]
    entry = record.load(cfg)["prs"][42]
    assert entry["tab_id"] == "w7:t2"
    assert datetime.fromisoformat(entry["run_started_at"]).tzinfo is not None


def test_tab_open_start_message(write_config, fake, monkeypatch):
    seed_record(write_config)
    calls = fake({"herdr": [TAB_CREATE]})
    monkeypatch.setenv("HERDR_PANE_ID", "w7:p0")
    assert cli.main(["tab-open", "fmha", "42"]) == 0
    prompt = calls.of("herdr")[-1]
    checkout = config.load("fmha")["checkout"]
    assert prompt == ["agent", "prompt", "prw-fmha-lead",
                      f"/pr-review-auto o/r 42 --checkout {checkout} --supervisor w7:p0 --interest x"]


def test_tab_open_start_message_pi_with_decision(write_config, fake):
    cfg = seed_record(write_config, status="escalated", decision="use the author's view")
    rec = record.load(cfg)
    write_config(team={"supervisor": {"harness": "claude", "model": "m", "effort": "low"},
                       "scanner": {"model": "haiku"},
                       "lead": {"harness": "pi", "model": "p/m", "effort": "high"}},
                 interest="FMHA kernels, not docs")
    record.save(config.load("fmha"), rec)
    calls = fake({"herdr": [TAB_CREATE]})
    assert cli.main(["tab-open", "fmha", "42"]) == 0
    herdr = calls.of("herdr")
    assert herdr[1][4] == "pi" and herdr[1][herdr[1].index("--") + 3:] == ["--model", "p/m:high"]
    checkout = config.load("fmha")["checkout"]
    assert herdr[-1][3] == (f"/skill:pr-review-auto o/r 42 --checkout {checkout} --supervisor w7:p0 "
                            "--interest 'FMHA kernels, not docs' --decision 'use the author'\"'\"'s view'")


def test_tab_open_invoke_override_and_no_interest_or_decision(write_config, fake):
    seed_record(write_config)
    write_config(interest="", team={
        "supervisor": {"harness": "claude", "model": "m", "effort": "low"},
        "scanner": {"model": "haiku"},
        "lead": {"harness": "claude", "model": "m", "effort": "high", "invoke": "/custom:review"}})
    calls = fake({"herdr": [TAB_CREATE]})
    assert cli.main(["tab-open", "fmha", "42"]) == 0
    checkout = config.load("fmha")["checkout"]
    assert calls.of("herdr")[-1][3] == f"/custom:review o/r 42 --checkout {checkout} --supervisor w7:p0"


def test_start_message_collapses_whitespace_in_free_text(write_config):
    cfg = seed_record(write_config)
    cfg["interest"] = "FMHA kernels,\n  not docs\t"
    message = team.start_message(cfg, 42, {"decision": "re-review\n\nthe new commits"}, "w7:p0")
    assert "\n" not in message and "\t" not in message
    assert message.endswith("--interest 'FMHA kernels, not docs' --decision 're-review the new commits'")
    cfg["interest"] = " \n "
    assert "--interest" not in team.start_message(cfg, 42, {}, "w7:p0")


@pytest.mark.parametrize("missing", ["HERDR_WORKSPACE_ID", "HERDR_PANE_ID"])
def test_tab_open_outside_supervisor_pane_fails(write_config, fake, monkeypatch, capsys, missing):
    seed_record(write_config)
    calls = fake({"herdr": [TAB_CREATE]})
    monkeypatch.delenv(missing)
    assert cli.main(["tab-open", "fmha", "42"]) == 1
    assert missing in capsys.readouterr().err
    assert calls.of("herdr") == []


def test_tab_open_restores_status_after_stall(write_config, fake):
    cfg = seed_record(write_config, status="escalated", decision="use the author's view")
    assert cli.main(["set-status", "fmha", "42", "stalled"]) == 0
    fake({"herdr": [TAB_CREATE]})
    assert cli.main(["tab-open", "fmha", "42"]) == 0
    entry = record.load(cfg)["prs"][42]
    assert entry["status"] == "escalated" and "stalled_from" not in entry
    assert entry["decision"] == "use the author's view"  # kept until the lead's run finishes


def test_finish_ends_stall_without_retry(write_config, fake):
    cfg = seed_record(write_config, status="escalated", tab_id="w7:t2", decision="use the author's view")
    assert cli.main(["set-status", "fmha", "42", "stalled"]) == 0
    fake({"gh": [{"match": ["pr", "view", "42"],
                  "stdout": json.dumps({"updatedAt": "2026-11-09T00:00:00Z", "headRefOid": "h1"})}]})
    assert cli.main(["finish", "fmha", "42", "no-action", "--head", "none", "--dry-run", "false"]) == 0
    entry = record.load(cfg)["prs"][42]
    assert entry["status"] == "escalated" and "stalled_from" not in entry
    assert "decision" not in entry


def seed_prs(write_config, numbers, **config_overrides):
    write_config(persona_dir="/personas", **config_overrides)
    cfg = config.load("fmha")
    rec = record.load(cfg)
    for n in numbers:
        rec["prs"][n] = {"reason": "r", "status": "new", "updated_at": None, "head_sha": None,
                         "last_run_at": None}
    record.save(cfg, rec)
    return cfg


def refusal(cap, pr):
    return (f"tab-open: cap reached ({cap} of {cap} reviews started this fire); "
            f"PR {pr} stays queued for the next fire\n")


def test_tab_open_default_cap_is_4(write_config, fake, capsys):
    cfg = seed_prs(write_config, [1, 2, 3, 4, 5])
    calls = fake({"herdr": [TAB_CREATE]})
    for pr in (1, 2, 3, 4):
        assert cli.main(["tab-open", "fmha", str(pr)]) == 0
    capsys.readouterr()
    assert cli.main(["tab-open", "fmha", "5"]) == 1
    assert "(4 of 4 reviews started this fire)" in capsys.readouterr().err
    assert record.fire_started(record.load(cfg)) == [1, 2, 3, 4]
    assert len(calls.of("herdr")) == 4 * 3


def test_tab_open_counts_and_refuses_at_cap(write_config, fake, capsys):
    cfg = seed_prs(write_config, [1, 2, 3], max_reviews_per_fire=2)
    calls = fake({"herdr": [TAB_CREATE]})
    assert cli.main(["tab-open", "fmha", "1"]) == 0
    assert cli.main(["tab-open", "fmha", "2"]) == 0
    assert record.load(cfg)["fire"]["started"] == [1, 2]
    path = config.state_dir(cfg) / "record.yaml"
    before, herdr_calls = path.read_bytes(), len(calls.of("herdr"))
    capsys.readouterr()
    assert cli.main(["tab-open", "fmha", "3"]) == 1
    assert capsys.readouterr().err == refusal(2, 3)
    assert len(calls.of("herdr")) == herdr_calls
    assert path.read_bytes() == before


def test_tab_open_without_fire_start_counts_from_zero(write_config, fake, capsys):
    cfg = seed_prs(write_config, [1, 2], max_reviews_per_fire=1)
    assert "fire" not in record.load(cfg)
    fake({"herdr": [TAB_CREATE]})
    assert cli.main(["tab-open", "fmha", "1"]) == 0
    fire = record.load(cfg)["fire"]
    assert fire["started"] == [1] and datetime.fromisoformat(fire["started_at"]).tzinfo is not None
    capsys.readouterr()
    assert cli.main(["tab-open", "fmha", "2"]) == 1
    assert capsys.readouterr().err == refusal(1, 2)
    assert cli.main(["fire-start", "fmha"]) == 0  # a new fire frees the slot
    assert cli.main(["tab-open", "fmha", "2"]) == 0


def test_tab_open_ignore_cap_neither_checks_nor_counts(write_config, fake):
    cfg = seed_prs(write_config, [1, 2], max_reviews_per_fire=1)
    rec = record.load(cfg)
    record.note_started(rec, 1, "2026-11-10T00:00:00Z")
    record.save(cfg, rec)
    calls = fake({"herdr": [TAB_CREATE]})
    assert cli.main(["tab-open", "fmha", "2", "--ignore-cap"]) == 0
    assert herdr_prefixes(calls) == [["tab", "create"], ["agent", "start"], ["agent", "prompt"]]
    rec = record.load(cfg)
    assert rec["fire"] == {"started_at": "2026-11-10T00:00:00Z", "started": [1]}
    assert rec["prs"][2]["tab_id"] == "w7:t2"


def test_tab_open_requires_recorded_pr(write_config, fake, capsys):
    write_config()
    calls = fake({"herdr": [TAB_CREATE]})
    assert cli.main(["tab-open", "fmha", "42"]) != 0
    assert calls.of("herdr") == []


def started(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_running_over_limit(write_config, capsys):
    seed_record(write_config, tab_id="w7:t2", run_started_at=started(4))
    assert cli.main(["running", "fmha"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["pr"] == 42 and out["tab_id"] == "w7:t2" and out["over_limit"] is True
    assert 239 <= out["elapsed_minutes"] <= 241


def test_running_under_limit(write_config, capsys):
    seed_record(write_config, tab_id="w7:t2", run_started_at=started(1))
    assert cli.main(["running", "fmha"]) == 0
    assert json.loads(capsys.readouterr().out)["over_limit"] is False


def test_running_idle(write_config, capsys):
    seed_record(write_config)
    assert cli.main(["running", "fmha"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "pr": None, "tab_id": None, "elapsed_minutes": None, "over_limit": False}


def test_tab_close_clears_tab_id(write_config, fake):
    cfg = seed_record(write_config, tab_id="w7:t2", run_started_at=started(1))
    calls = fake()
    assert cli.main(["tab-close", "fmha", "42"]) == 0
    assert calls.of("herdr") == [["tab", "close", "w7:t2"]]
    assert "tab_id" not in record.load(cfg)["prs"][42]


def test_subcommands_registered_and_removed():
    names = cli.subcommand_names(cli.build_parser())
    assert sorted(names) == sorted([
        "validate", "record", "set-status", "decide", "forget-dry-run", "clear-scan-mark", "fire-start",
        "pending", "commit-classified", "queue", "finish", "tab-open", "tab-close", "running"])


TAB_GONE = {"match": ["tab", "close"], "exit": 1,
            "stderr": json.dumps({"id": "", "error": {"code": "tab_not_found",
                                                      "message": "tab not found: w1:t2"}})}


def test_tab_close_unknown_tab_counts_as_closed(write_config, fake, capsys):
    cfg = seed_record(write_config, tab_id="w1:t2")
    fake({"herdr": [TAB_GONE]})
    assert cli.main(["tab-close", "fmha", "42"]) == 0
    assert "tab_id" not in record.load(cfg)["prs"][42]
    assert "already closed" in capsys.readouterr().err


def test_tab_close_other_herdr_error_fails(write_config, fake):
    cfg = seed_record(write_config, tab_id="w1:t2")
    fake({"herdr": [{"match": ["tab", "close"], "exit": 1,
                     "stderr": json.dumps({"error": {"code": "internal_error", "message": "x"}})}]})
    assert cli.main(["tab-close", "fmha", "42"]) == 1
    assert record.load(cfg)["prs"][42]["tab_id"] == "w1:t2"
