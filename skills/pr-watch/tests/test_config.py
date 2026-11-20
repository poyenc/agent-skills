import datetime
import subprocess
from pathlib import Path

import pytest

from prwatch import cli, config

PERMISSION_OK = {"match": ["api", "graphql"], "stdout": "WRITE\n"}
TOOL_OK = {"gh": [{"match": ["repo", "view"], "stdout": '{"name": "r"}', "exit": 0}, PERMISSION_OK]}


@pytest.fixture
def real_paths(tmp_path, monkeypatch):
    """Satisfy the persona file check and harness lookups."""
    personas = tmp_path / "agents"
    (personas / "orchestrator").mkdir(parents=True)
    (personas / "orchestrator" / "system-prompt.md").write_text("x")
    monkeypatch.setattr(config.shutil, "which", lambda b: f"/usr/bin/{b}")
    return {"persona_dir": str(personas)}


def git_checkout(path, origin):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin], check=True)


def test_load_applies_defaults(write_config):
    write_config()
    cfg = config.load("fmha")
    assert cfg["prefilter"]["include_own_prs"] is False
    assert cfg["max_pr_duration"] == "3h"
    assert cfg["schedule"] == {"every": "24h", "until": None}
    assert "~" not in cfg["persona_dir"]


def test_max_reviews_per_fire_default_is_4(write_config):
    write_config()
    assert config.load("fmha")["max_reviews_per_fire"] == 4
    write_config(max_reviews_per_fire=None)  # an empty key keeps the default
    assert config.load("fmha")["max_reviews_per_fire"] == 4
    write_config(max_reviews_per_fire=2)
    assert config.load("fmha")["max_reviews_per_fire"] == 2


def test_load_expands_tilde(write_config, monkeypatch):
    monkeypatch.setenv("HOME", "/home/someone")
    write_config(checkout="~/co")
    assert config.load("fmha")["checkout"] == "/home/someone/co"


def test_removed_keys_get_no_defaults(write_config):
    write_config()
    cfg = config.load("fmha")
    for key in ("dry_run", "blocking_threshold", "max_files_per_reviewer", "skip_paths",
                "unrelated_change_lines", "herdr_message", "local_checkout"):
        assert key not in cfg


def test_state_dir_is_named_directory_under_home(write_config, config_dir):
    write_config()
    path = config.state_dir(config.load("fmha"))
    assert path == config_dir / "fmha"
    assert path.is_dir()


def test_home_defaults_to_claude_pr_watch(monkeypatch):
    monkeypatch.delenv("PR_WATCH_HOME")
    monkeypatch.setenv("HOME", "/home/someone")
    assert config.config_dir() == Path("/home/someone/.claude/pr-watch")


@pytest.mark.parametrize("harness, invoke, expected", [
    ("claude", None, "/pr-review-auto"),
    ("pi", None, "/skill:pr-review-auto"),
    ("pi", "/custom", "/custom"),
])
def test_lead_invoke(harness, invoke, expected):
    lead = {"harness": harness, "model": "m", "effort": "high"}
    if invoke:
        lead["invoke"] = invoke
    assert config.lead_invoke({"team": {"lead": lead}}) == expected


@pytest.mark.parametrize("name, ok", [
    ("fmha", True), ("ck-attn", True), ("FMHA", False), ("1abc", False), ("abcdefghijk", False),
])
def test_name_rule(write_config, tmp_path, fake, real_paths, name, ok):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    write_config(name=name, **real_paths)
    errors = config.validate(config.load(name), name)
    assert any(e.startswith("name") for e in errors) is (not ok)
    assert (errors == []) is ok


def team_with_supervisor(harness):
    return {
        "supervisor": {"harness": harness, "model": "m", "effort": "high"},
        "scanner": {"model": "haiku"},
        "lead": {"harness": "claude", "model": "m", "effort": "high"},
    }


def test_validate_supervisor_must_be_claude(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    write_config(team=team_with_supervisor("pi"), **real_paths)
    errors = config.validate(config.load("fmha"), "fmha")
    assert any("supervisor" in e for e in errors)


def test_validate_repo_unreachable(write_config, tmp_path, fake, real_paths):
    fake({"gh": [{"match": ["repo", "view"], "stdout": "", "exit": 1}]})
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    write_config(**real_paths)
    errors = config.validate(config.load("fmha"), "fmha")
    assert any("repo" in e for e in errors)


def test_validate_checkout_not_matching_repo(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/x/y")
    write_config(**real_paths)
    errors = config.validate(config.load("fmha"), "fmha")
    assert any("checkout" in e for e in errors)


def test_validate_missing_checkout_and_persona(write_config, tmp_path, fake):
    fake(TOOL_OK)
    gone = tmp_path / "gone"
    write_config(persona_dir=str(gone / "agents"))
    errors = config.validate(config.load("fmha"), "fmha")
    for key in ("checkout", "persona_dir"):
        assert any(key in e for e in errors), key


def test_validate_missing_harness_binary(write_config, tmp_path, fake, real_paths, monkeypatch):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    monkeypatch.setattr(config.shutil, "which", lambda b: None if b == "pi" else f"/usr/bin/{b}")
    team = team_with_supervisor("claude")
    team["lead"] = {"harness": "pi", "model": "p/m", "effort": "high"}
    write_config(team=team, **real_paths)
    errors = config.validate(config.load("fmha"), "fmha")
    assert any("pi" in e and "team.lead" in e for e in errors)


def test_parse_duration():
    assert config.parse_duration("3h") == datetime.timedelta(hours=3)
    assert config.parse_duration("2d") == datetime.timedelta(hours=48)
    assert config.parse_duration("30m") == datetime.timedelta(minutes=30)
    with pytest.raises(ValueError):
        config.parse_duration("bad")


def test_cli_validate_prints_errors_and_exits_1(write_config, fake, capsys):
    fake({"gh": [{"match": ["repo", "view"], "stdout": "", "exit": 1}]})
    write_config()
    assert cli.main(["validate", "fmha"]) == 1
    assert "repo" in capsys.readouterr().out


def test_cli_validate_ok_exits_0(write_config, tmp_path, fake, real_paths, capsys):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    write_config(**real_paths)
    assert cli.main(["validate", "fmha"]) == 0
    assert capsys.readouterr().out == ""


def test_build_parser_registers_validate():
    assert "validate" in cli.subcommand_names(cli.build_parser())


def test_cli_missing_config_is_one_stderr_line(config_dir, capsys):
    assert cli.main(["validate", "nope"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"pr-watch: no config for nope at {config_dir / 'nope.yaml'}\n"


def test_validate_team_roles_need_valid_harness_and_scanner_model(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    team = team_with_supervisor("claude")
    team["lead"] = {"harness": "codex", "model": "m"}
    team["scanner"] = {}
    write_config(team=team, **real_paths)
    errors = config.validate(config.load("fmha"), "fmha")
    assert any("team.lead.harness" in e for e in errors)
    assert any("team.scanner.model" in e for e in errors)
    assert not any("team.supervisor" in e or "team.lead.model" in e or "team.lead.effort" in e for e in errors)


LEAD_DEFAULT = {"harness": "claude", "model": "Claude-Sonnet-5.5[1m]", "effort": "high"}


def valid_team(**lead):
    team = team_with_supervisor("claude")
    if lead:
        team["lead"] = lead
    else:
        del team["lead"]
    return team


def test_load_lead_defaults_without_lead(write_config, real_paths):
    write_config(team=valid_team(), **real_paths)
    assert config.load("fmha")["team"]["lead"] == LEAD_DEFAULT


def test_load_lead_defaults_without_team_block(write_config, real_paths):
    write_config(drop=("team",), **real_paths)
    cfg = config.load("fmha")
    assert cfg["team"]["lead"] == LEAD_DEFAULT
    assert "supervisor" not in cfg["team"] and "scanner" not in cfg["team"]


def test_load_lead_partial_override_merges_per_key(write_config, real_paths):
    write_config(team=valid_team(effort="medium"), **real_paths)
    assert config.load("fmha")["team"]["lead"] == {**LEAD_DEFAULT, "effort": "medium"}


def test_load_lead_none_is_full_default(write_config, real_paths):
    team = valid_team()
    team["lead"] = None
    write_config(team=team, **real_paths)
    assert config.load("fmha")["team"]["lead"] == LEAD_DEFAULT


def test_load_lead_keeps_invoke(write_config, real_paths):
    write_config(team=valid_team(invoke="/x"), **real_paths)
    cfg = config.load("fmha")
    assert cfg["team"]["lead"] == {**LEAD_DEFAULT, "invoke": "/x"}
    assert config.lead_invoke(cfg) == "/x"


def test_load_does_not_mutate_lead_defaults(write_config, real_paths):
    write_config(team=valid_team(effort="medium"), **real_paths)
    config.load("fmha")
    write_config(team=valid_team(), **real_paths)
    assert config.load("fmha")["team"]["lead"] == LEAD_DEFAULT


def test_validate_lead_defaults_are_valid(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    write_config(team=valid_team(), **real_paths)
    assert config.validate(config.load("fmha"), "fmha") == []


def test_validate_lead_harness_override_without_model_is_error(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    write_config(team=valid_team(harness="pi"), **real_paths)
    errors = config.validate(config.load("fmha"), "fmha")
    assert errors == ["team.lead: model is required when harness is overridden"]


def test_validate_lead_harness_override_with_model_is_fine(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    write_config(team=valid_team(harness="pi", model="p/m"), **real_paths)
    cfg = config.load("fmha")
    assert cfg["team"]["lead"] == {"harness": "pi", "model": "p/m", "effort": "high"}
    assert config.validate(cfg, "fmha") == []


def test_validate_supervisor_and_scanner_stay_required(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    write_config(drop=("team",), **real_paths)
    errors = config.validate(config.load("fmha"), "fmha")
    assert any("team.supervisor" in e for e in errors)
    assert any("team.scanner.model" in e for e in errors)
    assert not any("team.lead" in e for e in errors)


def test_validate_non_mapping_lead_is_reported(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    team = team_with_supervisor("claude")
    team["lead"] = "pi"
    write_config(team=team, **real_paths)
    errors = config.validate(config.load("fmha"), "fmha")
    assert any(e.startswith("team.lead") for e in errors)


def test_validate_ignores_reviewer_and_architect_teams(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    team = team_with_supervisor("claude")
    team["reviewer"] = {"harness": "codex"}
    write_config(team=team, **real_paths)
    assert config.validate(config.load("fmha"), "fmha") == []


def test_validate_scanner_needs_only_model(write_config, tmp_path, fake, real_paths):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    write_config(team=team_with_supervisor("claude"), **real_paths)
    assert config.validate(config.load("fmha"), "fmha") == []


# --- schedule, durations, name, origin, permission -------------------------------

@pytest.fixture
def valid_env(tmp_path, fake, real_paths):
    """A checkout of o/r and a gh that reaches it with write access; returns real_paths."""
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    return real_paths


def errors_for(write_config, name="fmha", **overrides):
    write_config(name=name, **overrides)
    return config.validate(config.load(name), name)


@pytest.mark.parametrize("schedule, max_pr_duration, bad", [
    ({"every": "24h"}, "3h", None),
    ({"every": "6d"}, "90m", None),
    ({"every": "7d"}, "3h", "schedule.every"),
    ({"every": "200h"}, "3h", "schedule.every"),
    ({"every": "daily"}, "3h", "schedule.every"),
    ({"every": 24}, "3h", "schedule.every"),
    ({"until": None}, "3h", "schedule.every"),
    (None, "3h", "schedule.every"),
    ("24h", "3h", "schedule"),
    ({"every": "24h"}, "3 hours", "max_pr_duration"),
])
def test_validate_schedule_and_durations(write_config, valid_env, schedule, max_pr_duration, bad):
    errors = errors_for(write_config, schedule=schedule, max_pr_duration=max_pr_duration, **valid_env)
    if bad is None:
        assert errors == []
    else:
        assert len(errors) == 1 and errors[0].startswith(bad), errors


def test_null_prefilter_takes_defaults(write_config, valid_env):
    assert errors_for(write_config, prefilter=None, **valid_env) == []
    assert config.load("fmha")["prefilter"] == {"include_drafts": False, "include_own_prs": False}


def test_validate_name_must_match_file(write_config, config_dir, valid_env):
    write_config(**valid_env)
    (config_dir / "other.yaml").write_text((config_dir / "fmha.yaml").read_text())
    errors = config.validate(config.load("other"), "other")
    assert len(errors) == 1 and errors[0].startswith("name") and "other.yaml" in errors[0]


@pytest.mark.parametrize("origin, ok", [
    ("https://github.com/o/r", True),
    ("https://github.com/o/r.git", True),
    ("https://github.com/o/r/", True),
    ("git@github.com:o/r.git", True),
    ("git@github.com:o/r", True),
    ("ssh://git@github.com/O/R.git", True),
    ("https://github.com/o/r-fork", False),
    ("https://github.com/xo/r", False),
    ("git@github.com:o/r.git.bak", False),
])
def test_validate_origin_matches_repo_exactly(write_config, tmp_path, fake, real_paths, origin, ok):
    fake(TOOL_OK)
    git_checkout(tmp_path / "checkout", origin)
    errors = errors_for(write_config, **real_paths)
    assert (errors == []) is ok, errors
    if not ok:
        assert len(errors) == 1 and errors[0].startswith("checkout")


@pytest.mark.parametrize("stdout, code, ok", [
    ("WRITE\n", 0, True), ("MAINTAIN\n", 0, True), ("ADMIN\n", 0, True),
    ("READ\n", 0, False), ("TRIAGE\n", 0, False), ("", 1, False),
])
def test_validate_needs_write_access(write_config, tmp_path, fake, real_paths, stdout, code, ok):
    calls = fake({"gh": [{"match": ["repo", "view"], "stdout": '{"name": "r"}'},
                         {"match": ["api", "graphql"], "stdout": stdout, "exit": code}]})
    git_checkout(tmp_path / "checkout", "https://github.com/o/r")
    errors = errors_for(write_config, **real_paths)
    assert (errors == []) is ok, errors
    if not ok:
        assert len(errors) == 1 and errors[0].startswith("repo")
    query = next(a for a in calls.of("gh") if a[:2] == ["api", "graphql"])
    assert "owner=o" in query and "name=r" in query
    assert any("viewerPermission" in a for a in query)


@pytest.mark.parametrize("value, ok", [(3, True), (1, True), (0, False), (-1, False), ("3", False),
                                       (3.5, False), (True, False)])
def test_validate_max_reviews_per_fire(write_config, valid_env, value, ok):
    errors = errors_for(write_config, max_reviews_per_fire=value, **valid_env)
    if ok:
        assert errors == []
    else:
        assert errors == [f"max_reviews_per_fire: must be an integer >= 1, got {value!r}"]
