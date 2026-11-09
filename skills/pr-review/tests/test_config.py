import datetime

import pytest

from prreview import cli, config

REPO = "o/r"
PERMISSION_OK = {"match": ["api", "graphql"], "stdout": "WRITE\n"}
TOOL_OK = {"gh": [{"match": ["repo", "view"], "stdout": '{"name": "r"}', "exit": 0}, PERMISSION_OK]}


@pytest.fixture
def real_paths(tmp_path, monkeypatch):
    """Satisfy the persona file checks and harness lookups."""
    personas = tmp_path / "agents"
    for role in ("orchestrator", "reviewer", "architect"):
        (personas / role).mkdir(parents=True)
        (personas / role / "system-prompt.md").write_text("x")
    monkeypatch.setattr(config.shutil, "which", lambda b: f"/usr/bin/{b}")
    return {"persona_dir": str(personas)}


@pytest.fixture
def valid_env(fake, real_paths):
    """A gh that reaches o/r with write access; returns real_paths."""
    fake(TOOL_OK)
    return real_paths


def errors_for(write_config, repo=REPO, **overrides):
    write_config(repo, **overrides)
    return config.validate(config.load(repo), repo)


def test_load_defaults(write_config):
    write_config()
    cfg = config.load(REPO)
    assert cfg["dry_run"] is True
    assert cfg["blocking_threshold"] == "medium"
    assert cfg["skip_paths"] == []
    assert cfg["unrelated_change_lines"] == 200
    assert cfg["lock_stale_after"] == "3h"
    assert cfg["persona_dir"].endswith("/workspace/repo/claude-code-setting/agents")
    assert "~" not in cfg["persona_dir"]
    assert cfg["team"]["reviewer"]["harness"] == "pi"


def test_load_overrides_defaults(write_config):
    write_config(dry_run=False, blocking_threshold="high", skip_paths=["docs/"])
    cfg = config.load(REPO)
    assert (cfg["dry_run"], cfg["blocking_threshold"], cfg["skip_paths"]) == (False, "high", ["docs/"])


def test_load_expands_tilde(write_config, monkeypatch):
    monkeypatch.setenv("HOME", "/home/someone")
    write_config(persona_dir="~/agents")
    assert config.load(REPO)["persona_dir"] == "/home/someone/agents"


def test_repo_dir(review_home):
    assert config.repo_dir("ROCm/rocm-libraries") == review_home / "ROCm" / "rocm-libraries"


def test_load_missing_raises_file_not_found(review_home):
    with pytest.raises(FileNotFoundError) as exc:
        config.load(REPO)
    assert exc.value.filename == str(review_home / "o" / "r" / "config.yaml")


@pytest.mark.parametrize("repo", ["justname", "a/b/c", "../x", "o/..", "o/ r"])
def test_repo_dir_rejects_bad_repo(repo):
    with pytest.raises(ValueError):
        config.repo_dir(repo)


def test_validate_ok(write_config, valid_env):
    assert errors_for(write_config, **valid_env) == []


def test_validate_rejects_bad_harness(write_config, valid_env):
    team = {"reviewer": {"harness": "codex", "model": "m"}}
    errors = errors_for(write_config, team=team, **valid_env)
    assert any("team.reviewer.harness" in e for e in errors)
    assert not any("team.architect" in e for e in errors)


REVIEWER_DEFAULT = {"harness": "pi", "model": "amd-gateway/gpt-6.1-sol", "effort": "high"}
ARCHITECT_DEFAULT = {"harness": "claude", "model": "Claude-Opus-5.5[1m]", "effort": "high"}


def test_load_team_defaults_without_team(write_config):
    write_config(drop=("team",))
    cfg = config.load(REPO)
    assert cfg["team"] == {"reviewer": REVIEWER_DEFAULT, "architect": ARCHITECT_DEFAULT}


def test_validate_ok_without_team(write_config, valid_env):
    assert errors_for(write_config, drop=("team",), **valid_env) == []


def test_load_partial_override_merges_per_key(write_config):
    write_config(team={"reviewer": {"effort": "medium"}, "architect": {"model": "other"}})
    team = config.load(REPO)["team"]
    assert team["reviewer"] == {**REVIEWER_DEFAULT, "effort": "medium"}
    assert team["architect"] == {**ARCHITECT_DEFAULT, "model": "other"}


def test_load_role_missing_or_empty_is_full_default(write_config):
    write_config(team={"reviewer": None})
    assert config.load(REPO)["team"] == {"reviewer": REVIEWER_DEFAULT, "architect": ARCHITECT_DEFAULT}


def test_load_does_not_mutate_defaults(write_config):
    write_config(team={"reviewer": {"effort": "medium"}})
    config.load(REPO)
    write_config(drop=("team",))
    assert config.load(REPO)["team"]["reviewer"] == REVIEWER_DEFAULT


def test_validate_harness_override_without_model_is_error(write_config, valid_env):
    errors = errors_for(write_config, team={"reviewer": {"harness": "claude"}}, **valid_env)
    assert errors == ["team.reviewer: model is required when harness is overridden"]


def test_validate_harness_override_with_model_is_fine(write_config, valid_env):
    team = {"reviewer": {"harness": "claude", "model": "Claude-Sonnet-5.5"}}
    assert errors_for(write_config, team=team, **valid_env) == []
    assert config.load(REPO)["team"]["reviewer"] == {"harness": "claude", "model": "Claude-Sonnet-5.5",
                                                     "effort": "high"}


def test_validate_same_harness_as_default_without_model_is_fine(write_config, valid_env):
    assert errors_for(write_config, team={"reviewer": {"harness": "pi"}}, **valid_env) == []


def test_validate_missing_harness_binary(write_config, valid_env, monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda b: None if b == "pi" else f"/usr/bin/{b}")
    errors = errors_for(write_config, **valid_env)
    assert len(errors) == 1 and "pi" in errors[0] and "reviewer" in errors[0]


def test_validate_blocking_threshold(write_config, valid_env):
    errors = errors_for(write_config, blocking_threshold="severe", **valid_env)
    assert len(errors) == 1 and errors[0].startswith("blocking_threshold")


@pytest.mark.parametrize("value, ok", [("3h", True), ("90m", True), ("1d", True), ("3 hours", False), (3, False)])
def test_validate_lock_stale_after(write_config, valid_env, value, ok):
    errors = errors_for(write_config, lock_stale_after=value, **valid_env)
    assert (errors == []) is ok, errors
    if not ok:
        assert len(errors) == 1 and errors[0].startswith("lock_stale_after")


def test_validate_missing_persona_files(write_config, tmp_path, fake):
    fake(TOOL_OK)
    errors = errors_for(write_config, persona_dir=str(tmp_path / "gone"))
    assert any(e.startswith("persona_dir") and role in e
               for role in ("orchestrator", "reviewer", "architect") for e in errors)
    assert sum(e.startswith("persona_dir") for e in errors) == 3


def test_validate_repo_unreachable(write_config, fake, real_paths):
    fake({"gh": [{"match": ["repo", "view"], "stdout": "", "exit": 1}]})
    errors = errors_for(write_config, **real_paths)
    assert len(errors) == 1 and errors[0].startswith("repo")


def test_validate_bad_repo_format(write_config, valid_env):
    write_config("o/r", **valid_env)
    errors = config.validate(config.load("o/r"), "not-a-repo")
    assert len(errors) == 1 and errors[0].startswith("repo")


@pytest.mark.parametrize("stdout, code, ok", [
    ("WRITE\n", 0, True), ("MAINTAIN\n", 0, True), ("ADMIN\n", 0, True),
    ("READ\n", 0, False), ("TRIAGE\n", 0, False), ("", 1, False),
])
def test_validate_write_access(write_config, fake, real_paths, stdout, code, ok):
    calls = fake({"gh": [{"match": ["repo", "view"], "stdout": '{"name": "r"}'},
                         {"match": ["api", "graphql"], "stdout": stdout, "exit": code}]})
    errors = errors_for(write_config, **real_paths)
    assert (errors == []) is ok, errors
    if not ok:
        assert len(errors) == 1 and errors[0].startswith("repo")
    query = next(a for a in calls.of("gh") if a[:2] == ["api", "graphql"])
    assert "owner=o" in query and "name=r" in query
    assert any("viewerPermission" in a for a in query)


def test_parse_duration():
    assert config.parse_duration("3h") == datetime.timedelta(hours=3)
    assert config.parse_duration("2d") == datetime.timedelta(hours=48)
    assert config.parse_duration("30m") == datetime.timedelta(minutes=30)
    with pytest.raises(ValueError):
        config.parse_duration("bad")


def test_cli_validate_prints_errors_and_exits_1(write_config, fake, capsys):
    fake({"gh": [{"match": ["repo", "view"], "stdout": "", "exit": 1}]})
    write_config()
    assert cli.main(["validate", REPO]) == 1
    assert "repo" in capsys.readouterr().out


def test_cli_validate_ok_exits_0(write_config, valid_env, capsys):
    write_config(**valid_env)
    assert cli.main(["validate", REPO]) == 0
    assert capsys.readouterr().out == ""


def test_build_parser_registers_validate():
    assert "validate" in cli.subcommand_names(cli.build_parser())


def test_missing_config_exit_3(review_home, capsys):
    assert cli.main(["paths", REPO, "5"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"pr-review: no config for {REPO} at {review_home / 'o' / 'r' / 'config.yaml'}\n"


@pytest.mark.parametrize("argv", [["decide", REPO, "5", "go"], ["review-state", REPO, "5"]])
def test_missing_config_exit_3_every_command(argv, capsys):
    assert cli.main(argv) == 3
    assert capsys.readouterr().err.startswith(f"pr-review: no config for {REPO} at ")


def test_validate_missing_config_exits_1_not_3(review_home, capsys):
    assert cli.main(["validate", REPO]) == 1
    assert capsys.readouterr().err == f"pr-review: no config for {REPO} at {review_home / 'o' / 'r' / 'config.yaml'}\n"


def test_bad_repository_is_a_value_error():
    with pytest.raises(config.BadRepository):
        config.repo_dir("justname")
    assert issubclass(config.BadRepository, ValueError)


def test_other_value_errors_are_not_reported_as_bad_repository(write_config, monkeypatch):
    write_config()

    def boom(*args, **kwargs):
        raise ValueError("unrelated")

    monkeypatch.setattr(config, "validate", boom)
    with pytest.raises(ValueError, match="unrelated"):
        cli.main(["validate", REPO])


def test_bad_repo_argument_exits_2(capsys):
    assert cli.main(["paths", "justname", "5"]) == 2
    assert capsys.readouterr().err.startswith("pr-review: bad repository 'justname'")


# --- malformed config.yaml ---------------------------------------------------------

def write_raw(review_home, text):
    path = review_home / "o" / "r" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.mark.parametrize("text, message", [
    ("team: [unclosed", "invalid YAML"),
    ("- a\n- b\n", "top level must be a mapping, got list"),
    ("just a string\n", "top level must be a mapping, got str"),
])
def test_load_malformed_raises_config_error(review_home, text, message):
    path = write_raw(review_home, text)
    with pytest.raises(config.ConfigError) as exc:
        config.load(REPO)
    assert message in str(exc.value) and str(path) in str(exc.value)


def test_load_empty_file_gives_defaults(review_home):
    write_raw(review_home, "")
    assert config.load(REPO)["blocking_threshold"] == "medium"


@pytest.mark.parametrize("text, message", [
    ("team: [unclosed", "invalid YAML"),
    ("- a\n", "top level must be a mapping"),
])
@pytest.mark.parametrize("command", [["validate", REPO], ["paths", REPO, "5"], ["review-state", REPO, "5"]])
def test_cli_malformed_config_is_one_stderr_line(review_home, capsys, command, text, message):
    write_raw(review_home, text)
    code = cli.main(command)
    captured = capsys.readouterr()
    assert code == 1  # not 3: 3 means "no config"
    assert captured.out == ""
    assert captured.err.startswith("pr-review: ") and message in captured.err
    assert captured.err.count("\n") >= 1 and "Traceback" not in captured.err


@pytest.mark.parametrize("overrides, key", [
    ({"team": "reviewer"}, "team"),
    ({"team": ["reviewer"]}, "team"),
    ({"team": {"reviewer": "pi", "architect": ["x"]}}, "team.reviewer"),
    ({"team": {"reviewer": "pi", "architect": ["x"]}}, "team.architect"),
    ({"persona_dir": 5}, "persona_dir"),
    ({"persona_dir": ["a"]}, "persona_dir"),
    ({"dry_run": "yes"}, "dry_run"),
    ({"skip_paths": "docs/"}, "skip_paths"),
    ({"skip_paths": [1]}, "skip_paths"),
    ({"unrelated_change_lines": "200"}, "unrelated_change_lines"),
    ({"unrelated_change_lines": True}, "unrelated_change_lines"),
    ({"blocking_threshold": ["high"]}, "blocking_threshold"),
    ({"lock_stale_after": ["3h"]}, "lock_stale_after"),
])
def test_validate_reports_wrong_types_without_raising(write_config, valid_env, overrides, key):
    overrides = {"persona_dir": valid_env["persona_dir"], **overrides}
    errors = errors_for(write_config, **overrides)
    assert any(e.startswith(key) for e in errors), errors


def test_cli_validate_wrong_typed_team_prints_message(write_config, valid_env, capsys):
    write_config(persona_dir=valid_env["persona_dir"], team="reviewer")
    assert cli.main(["validate", REPO]) == 1
    assert capsys.readouterr().out.startswith("team:")
