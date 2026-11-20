import json
from pathlib import Path

import pytest

from prreview import cli, config, team

REPO = "o/r"
PR = 9187
CALLER_PANE = "w7:p2"

PANE_SPLIT = {"match": ["pane", "split"], "stdout": json.dumps({"result": {"pane": {"pane_id": "w7:p5"}}})}
AGENT_GET = {"match": ["agent", "get", "prr-9187-rev"], "stdout": json.dumps(
    {"result": {"agent": {"name": "prr-9187-rev", "pane_id": "w7:p5"}}})}
SKILL_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def caller_pane(monkeypatch):
    monkeypatch.setenv("HERDR_PANE_ID", CALLER_PANE)


def load_cfg(write_config, **overrides):
    write_config(**overrides)
    return config.load(REPO)


# --- launch helpers ----------------------------------------------------------

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


def test_unsupported_harness():
    with pytest.raises(ValueError):
        team.harness_argv({"harness": "x", "model": "m", "effort": "e"}, Path("/p/f.md"))


def test_agent_names():
    assert team.agent_name(PR, "reviewer") == "prr-9187-rev"
    assert team.agent_name(PR, "architect") == "prr-9187-arch"
    with pytest.raises(ValueError):
        team.agent_name(PR, "lead")


def test_system_prompt_files(write_config):
    cfg = load_cfg(write_config, persona_dir="/personas")
    assert team.system_prompt_file(cfg, "reviewer") == Path("/personas/reviewer/system-prompt.md")
    assert team.system_prompt_file(cfg, "architect") == Path("/personas/architect/system-prompt.md")


def test_start_agent_calls_herdr(write_config, fake):
    calls = fake()
    cfg = load_cfg(write_config, persona_dir="/personas")
    assert team.start_agent(cfg, "reviewer", PR, "w1:p3") == "prr-9187-rev"
    (argv,) = calls.of("herdr")
    assert argv[:7] == ["agent", "start", "prr-9187-rev", "--kind", "pi", "--pane", "w1:p3"]
    assert argv[7:9] == ["--timeout", "120000"]
    sep = argv.index("--")
    assert argv[sep + 1:] == [
        "--system-prompt-file", "/personas/reviewer/system-prompt.md", "--model", "p/m:high",
    ]


def test_render_replaces_placeholders(tmp_path):
    template = tmp_path / "t.md"
    template.write_text("PR {{PR}} in {{REPO}}; again {{PR}}")
    assert team.render(template, {"PR": "7", "REPO": "o/r"}) == "PR 7 in o/r; again 7"


def test_render_does_not_rescan_substituted_values(tmp_path):
    template = tmp_path / "t.md"
    template.write_text("diff: {{DIFF}}")
    assert team.render(template, {"DIFF": "use {{braces}}"}) == "diff: use {{braces}}"


def test_render_rejects_leftover_placeholder(tmp_path):
    template = tmp_path / "t.md"
    template.write_text("{{PR}} {{X}}")
    with pytest.raises(ValueError, match="X"):
        team.render(template, {"PR": "1"})


# --- spawn -------------------------------------------------------------------

def test_spawn_single_reviewer_name(write_config, fake, capsys):
    write_config()
    fake({"herdr": [PANE_SPLIT]})
    assert cli.main(["spawn", REPO, str(PR), "reviewer"]) == 0
    assert capsys.readouterr().out.strip() == "prr-9187-rev"


def test_spawn_architect_name(write_config, fake, capsys):
    write_config()
    fake({"herdr": [PANE_SPLIT]})
    assert cli.main(["spawn", REPO, str(PR), "architect"]) == 0
    assert capsys.readouterr().out.strip() == "prr-9187-arch"


def test_spawn_rejects_group_flag(write_config, fake):
    write_config()
    calls = fake({"herdr": [PANE_SPLIT]})
    with pytest.raises(SystemExit) as exc:
        cli.main(["spawn", REPO, str(PR), "reviewer", "--group", "2"])
    assert exc.value.code == 2
    assert calls.of("herdr") == []


def test_spawn_uses_caller_pane(write_config, fake):
    write_config()
    calls = fake({"herdr": [PANE_SPLIT]})
    assert cli.main(["spawn", REPO, str(PR), "reviewer"]) == 0
    assert cli.main(["spawn", REPO, str(PR), "architect"]) == 0
    herdr = calls.of("herdr")
    splits = [a for a in herdr if a[:2] == ["pane", "split"]]
    assert [s[s.index("--pane") + 1] for s in splits] == [CALLER_PANE, CALLER_PANE]
    assert [s[s.index("--direction") + 1] for s in splits] == ["right", "down"]
    assert all("--no-focus" in s for s in splits)
    starts = [a for a in herdr if a[:2] == ["agent", "start"]]
    assert [s[2] for s in starts] == ["prr-9187-rev", "prr-9187-arch"]
    assert all(s[s.index("--pane") + 1] == "w7:p5" for s in starts)


def test_spawn_starts_agent_from_repo_config(write_config, fake):
    write_config(persona_dir="/personas")
    calls = fake({"herdr": [PANE_SPLIT]})
    assert cli.main(["spawn", REPO, str(PR), "architect"]) == 0
    (start,) = [a for a in calls.of("herdr") if a[:2] == ["agent", "start"]]
    assert start[start.index("--kind") + 1] == "claude"
    assert start[start.index("--") + 1:] == [
        "--system-prompt-file", "/personas/architect/system-prompt.md", "--model", "opus",
        "--effort", "high", "--dangerously-skip-permissions",
    ]


def test_spawn_needs_caller_pane(write_config, fake, monkeypatch, capsys):
    write_config()
    calls = fake()
    monkeypatch.delenv("HERDR_PANE_ID")
    assert cli.main(["spawn", REPO, str(PR), "reviewer"]) == 1
    assert "HERDR_PANE_ID" in capsys.readouterr().err
    assert calls.of("herdr") == []


def test_spawn_without_config_exits_3(fake):
    calls = fake()
    assert cli.main(["spawn", REPO, str(PR), "reviewer"]) == 3
    assert calls.of("herdr") == []


# --- member-close ------------------------------------------------------------

def test_member_close_closes_pane(fake):
    calls = fake({"herdr": [AGENT_GET]})
    assert cli.main(["member-close", "prr-9187-rev"]) == 0
    assert calls.of("herdr")[-1] == ["pane", "close", "w7:p5"]


# --- notify ------------------------------------------------------------------

def test_notify_is_plain_agent_prompt(fake):
    calls = fake()
    assert cli.main(["notify", "prr-9187-rev", "hello there"]) == 0
    assert calls.of("herdr") == [["agent", "prompt", "prr-9187-rev", "hello there"]]


@pytest.mark.parametrize("value", [None, "0", ""])
def test_notify_outside_herdr_fails(fake, monkeypatch, capsys, value):
    calls = fake()
    if value is None:
        monkeypatch.delenv("HERDR_ENV")
    else:
        monkeypatch.setenv("HERDR_ENV", value)
    assert cli.main(["notify", "prr-9187-rev", "go"]) == 1
    assert "HERDR_ENV" in capsys.readouterr().err
    assert calls.of("herdr") == []


def test_notify_needs_no_config(fake, review_home):
    calls = fake()
    assert not any(review_home.iterdir())
    assert cli.main(["notify", "w7:p2", "needs-config"]) == 0
    assert calls.of("herdr") == [["agent", "prompt", "w7:p2", "needs-config"]]


def test_notify_without_herdr_binary_is_not_a_config_error(monkeypatch, tmp_path):
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        cli.main(["notify", "w7:p2", "x"])


def test_subcommands_registered():
    names = cli.subcommand_names(cli.build_parser())
    for name in ("gh", "spawn", "member-close", "notify"):
        assert name in names


# --- no plugin dependency ----------------------------------------------------

FORBIDDEN = ("herdr" + "-kit", "herdr" + "-message", "agent" + "-plugins", "guard" + "rails")
SKIPPED_DIRS = {"__pycache__", ".pytest_cache"}


def test_no_plugin_dependency():
    offenders = []
    for path in SKILL_DIR.rglob("*"):
        if not path.is_file() or SKIPPED_DIRS & set(path.relative_to(SKILL_DIR).parts):
            continue
        text = path.read_text(errors="ignore")
        offenders += [f"{path.relative_to(SKILL_DIR)}: {word}" for word in FORBIDDEN if word in text]
    assert offenders == []
