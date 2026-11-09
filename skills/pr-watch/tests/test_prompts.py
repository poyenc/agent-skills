"""Static checks on the supervisor, scanner and configure prompts, SKILL.md and the example config."""
import re
from pathlib import Path

from prwatch import cli, config

SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPTS = SKILL_DIR / "prompts"
OWN_PROMPTS = {"supervisor.md", "scanner.md", "configure.md"}
COMMAND_RE = re.compile(r"\bpr-watch ([a-z][a-z-]*)")
RESULTS = ("reviewed", "approved", "escalated", "no-action", "not-interesting", "merged", "closed",
           "needs-config", "busy")
DONE_HEADING = ("## Message: `done <PR> <result> head=<sha|none> dry_run=<true|false> [summary]` "
                "(from a lead)")


def _prompts() -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(PROMPTS.glob("*.md"))}


def _flat(text: str) -> str:
    return " ".join(text.split())


def _supervisor() -> str:
    return _flat(_prompts()["supervisor.md"])


def _skill_md() -> str:
    return (SKILL_DIR / "SKILL.md").read_text()


def _section(text: str, start: str, end: str | None) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start)) if end else None]


def _done_section() -> str:
    return _section(_supervisor(), _flat(DONE_HEADING), "## The user writes")


def test_prompt_files_are_the_supervisors_own():
    # lead, reviewer-task, architect-task and comment-style moved to the pr-review skill.
    assert set(_prompts()) == OWN_PROMPTS


def test_prompts_reference_only_real_subcommands():
    real = set(cli.subcommand_names(cli.build_parser()))
    texts = {**_prompts(), "SKILL.md": _skill_md()}
    unknown = {(name, word) for name, text in texts.items()
               for word in COMMAND_RE.findall(text) if word not in real}
    assert not unknown


def test_command_check_finds_each_prompts_calls():
    found = {name: set(COMMAND_RE.findall(text)) for name, text in _prompts().items()}
    assert {"running", "set-status", "tab-open", "tab-close", "finish", "decide", "queue",
            "forget-dry-run", "record"} <= found["supervisor.md"]
    assert {"pending", "commit-classified", "queue"} <= found["scanner.md"]
    assert {"validate", "clear-scan-mark"} <= found["configure.md"]
    assert COMMAND_RE.findall("run `pr-watch bogus <name>`") == ["bogus"]


def test_skill_md_lists_every_subcommand():
    text = _skill_md()
    missing = [n for n in cli.subcommand_names(cli.build_parser()) if f"`pr-watch {n}" not in text]
    assert not missing, f"SKILL.md lacks: {missing}"


def test_skill_md_makes_session_the_supervisor():
    text = _flat(_skill_md())
    assert "`/pr-watch <name>`" in text
    assert "This session becomes the supervisor" in text
    assert "`prompts/supervisor.md`" in text
    assert "`/loop <every> pr-watch-fire <name> cli=<path>`" in text
    assert text.index("`prompts/supervisor.md`") < text.index("`/loop <every> pr-watch-fire")
    stop = _section(text, "## Stop", "## ")
    assert "CronDelete" in stop and "loop job" in stop
    for removed in ("pr-watch start", "pr-watch stop", "pr-watch close", "workspace create"):
        assert removed not in text, removed


def test_skill_md_reminds_pr_review_setup_first():
    text = _flat(_skill_md())
    assert "the `pr-review` skill" in text
    assert "run `/pr-review <owner>/<repo> <PR>` once per repository" in text
    assert "`needs-config`" in text


def test_skill_md_keeps_pending_output_cap():
    # Claude Code truncates a Bash result near 30K characters; pending stays under it.
    assert "at most 20000 printed characters" in _flat(_skill_md())


def test_skill_md_documents_forget_dry_run():
    text = _flat(_skill_md())
    assert "turns dry run off" in text and "`pr-watch forget-dry-run <name>`" in text


def test_supervisor_prompt_lean():
    text = _prompts()["supervisor.md"]
    assert len(text.splitlines()) <= 120
    for forbidden in ("gh pr diff", "gh api"):
        assert forbidden not in text


def test_no_runtime_commands_in_prompts():
    for name, text in _prompts().items():
        for forbidden in ("cmake", "make ", "ctest", "rocprof", "hipcc"):
            assert forbidden not in text.lower(), f"{name} contains {forbidden!r}"


def test_supervisor_takes_setup_from_fire_message():
    text = _supervisor()
    assert "## Message: `pr-watch-fire <name> cli=<CLI path>` (your loop fired)" in text
    assert "the fire message wins" in text
    assert "`prompts/scanner.md`" in text
    assert "`~/.claude/pr-watch/<name>.yaml`" in text


def test_supervisor_renews_loop_every_fire():
    text = _supervisor()
    renew = _section(text, "Renew the loop", "4. Run `pr-watch running")
    assert "CronList" in renew and "CronDelete" in renew and "CronCreate" in renew
    assert "7-day expiry" in renew


def test_supervisor_creates_missing_loop_job():
    text = _supervisor()
    assert "If CronList finds no such job, CronCreate one" in text
    assert "never minute 0 or 30" in text


def test_supervisor_shows_stall_in_its_pane():
    text = _supervisor()
    step = _section(text, "`over_limit` is true", "5. Scan.")
    for needed in ("STALLED: PR <pr>", "<elapsed_minutes>", "close and continue", "retry"):
        assert needed in step, needed


def test_supervisor_scanner_failure_reports_and_ends_fire():
    step = _section(_supervisor(), "5. Scan.", "6. ")
    for needed in ("errors", "`ERROR:`", "malformed JSON", "watcher name", "error text as returned",
                   "did not run", "next fire will retry", "End this fire",
                   "do not retry with a different model or inspect the environment"):
        assert needed in step, needed
    assert '`{"process": [...]}`' in step


def test_supervisor_opens_tabs_in_its_own_workspace():
    text = _supervisor()
    assert "in its own tab of your herdr workspace" in text
    assert "`pr-watch tab-open <name> <first pr>`" in text


def test_supervisor_done_parsing():
    text = _supervisor()
    assert _flat(DONE_HEADING) in text
    done = _done_section()
    for result in RESULTS:
        assert f"`{result}`" in done, result
    assert ("`pr-watch finish <name> <PR> <result> --head <sha|none> --dry-run <true|false>`, "
            "copying `head=` and `dry_run=` from the message") in done


def test_supervisor_closes_tab_before_finish():
    # Ruling R4: `finish` drops the tab from the record, so `tab-close` must run first.
    done = _done_section()
    assert done.index("`pr-watch tab-close <name> <PR>`") < done.index("`pr-watch finish <name>")
    assert "This order matters" in done
    assert "If `tab-close` fails, print its error and still run `finish`" in done


def test_supervisor_done_ends_stall():
    assert "stall is over" in _done_section()


def test_supervisor_handles_needs_config():
    done = _done_section()
    item = _section(done, "- `needs-config`", "- `busy`")
    assert "run /pr-review once for <repo>" in item
    assert "the next fire retries" in item
    assert "Open no further PR this fire" in item


def test_supervisor_handles_busy():
    done = _done_section()
    item = _section(done, "- `busy`", "3. ")
    assert "another run holds the PR" in item
    assert "the next fire retries" in item
    assert "Open the next PR in the queue" in done


def test_supervisor_never_reopens_a_pr_tried_this_fire():
    # `finish ... busy|needs-config` leaves the PR in `queue`, so a rebuilt queue would relaunch it.
    step = _section(_done_section(), "3. Open the next PR", None)
    for needed in ("Keep the PRs you have opened or got a `done` for since this fire started",
                   "never open one of them again in this fire",
                   "a `busy` or `needs-config` PR stays in `queue` until the next fire",
                   "use its `process` list without those PRs",
                   "if you lost track of those PRs too, open nothing until the next fire"):
        assert needed in step, needed
    assert "Your memory of the queue is a convenience" not in _supervisor()
    assert "your memory adds only this fire's queue and tried PRs" in _supervisor()


def test_supervisor_handles_escalation_with_decide():
    done = _done_section()
    item = _section(done, "- `escalated`", "- `needs-config`")
    for needed in ("ESCALATION: PR <PR>", "the lead's summary", "Reply here with your decision"):
        assert needed in item, needed
    user = _section(_supervisor(), "## The user writes", "## Rules")
    assert "`pr-watch decide <name> <pr> '<decision text>'`" in user
    assert "next lead for that PR gets it" in user


def test_supervisor_handles_stop_and_forget_dry_run():
    user = _section(_supervisor(), "## The user writes", "## Rules")
    stop = _section(user, "**stop**", "- **")
    assert "CronDelete" in stop and "open no further PR" in stop
    assert "`pr-watch forget-dry-run <name>`" in user


def test_supervisor_no_branch_or_notes_handling():
    text = _supervisor()
    for forbidden in ("cleanup", "branch", "notes", "Decision section", "pr-watch/<pr>",
                      "pr-watch/<N>"):
        assert forbidden not in text, forbidden
    assert ("never run the `pr-review` skill's commands or read or write its files"
            in text)


def test_supervisor_config_is_read_only():
    text = _supervisor()
    assert "The config file is read-only for you: never edit, rewrite or create it;" in text
    assert "configure mode" in text


def test_supervisor_never_prints_environment_or_credentials():
    text = _supervisor()
    assert "Never print environment variables, settings files, credentials or tokens" in text
    for command in ("`env`", "`printenv`", "`set`", "`cat`"):
        assert command in text


def test_scanner_loops_until_no_more_batches():
    text = _flat(_prompts()["scanner.md"])
    assert '"more": true|false' in text
    assert "If `more` was true, go back to step 2 for the next batch." in text


def test_scanner_returns_process_list_only():
    text = _flat(_prompts()["scanner.md"])
    assert 'It prints `{"process": [...]}`' in text
    assert "cleanup" not in text


def test_configure_asks_watcher_fields_only():
    text = _flat(_prompts()["configure.md"])
    for needed in ("`checkout`", "`team.lead`", "`team.scanner`", "`team.supervisor`", "`interest`",
                   "`prefilter`", "`schedule.every`", "`persona_dir`", "`max_pr_duration`"):
        assert needed in text, needed
    for removed in ("`local_checkout`", "`blocking_threshold`", "`max_files_per_reviewer`",
                    "`skip_paths`", "`unrelated_change_lines`", "`herdr_message`", "`dry_run`",
                    "PR_WATCH_CONFIG_DIR", "~/.config/pr-watch", "pr-watch start", "pr-watch stop"):
        assert removed not in text, removed
    assert "`~/.claude/pr-watch`" in text


def test_configure_validates_candidate_before_moving_it():
    text = _flat(_prompts()["configure.md"])
    step = _section(text, "## 4. Validate the candidate", "## 5.")
    validate = step.index("`PR_WATCH_HOME=<tmpdir> pr-watch validate <name>`")
    assert validate < step.index("move the candidate to `<home>/<name>.yaml`")
    assert "The real config file stays untouched meanwhile" in step


def test_configure_states_lead_default_and_asks_only_to_override():
    text = _flat(_prompts()["configure.md"])
    for value in config.LEAD_DEFAULTS.values():
        assert value in text, value
    assert "ask only whether to override" in text


def test_example_config_shows_lead_default_as_comment():
    text = (SKILL_DIR / "examples" / "fmha.yaml").read_text()
    line = next(l for l in text.splitlines() if l.lstrip().startswith("# lead:"))
    for value in config.LEAD_DEFAULTS.values():
        assert value in line, value
    assert not any(l.startswith("  lead:") for l in text.splitlines())


def test_configure_reminds_pr_review_setup_first():
    text = _flat(_prompts()["configure.md"])
    assert "run `/pr-review <owner>/<repo> <PR>` once" in text
    assert "`needs-config`" in text


def test_example_config_validates_shape(config_dir, monkeypatch):
    for check in ("_check_repo", "_check_checkout", "_check_persona"):
        monkeypatch.setattr(config, check, lambda cfg: [])
    monkeypatch.setattr(config.shutil, "which", lambda name: f"/usr/bin/{name}")
    (config_dir / "fmha.yaml").write_text((SKILL_DIR / "examples" / "fmha.yaml").read_text())
    cfg = config.load("fmha")
    assert config.validate(cfg, "fmha") == []
    assert cfg["name"] == "fmha" and cfg["checkout"]
    assert set(cfg["team"]) == {"supervisor", "scanner", "lead"}
    assert cfg["team"]["supervisor"]["harness"] == "claude"
    assert cfg["team"]["lead"] == config.LEAD_DEFAULTS
    for removed in ("local_checkout", "dry_run", "blocking_threshold", "max_files_per_reviewer",
                    "skip_paths", "unrelated_change_lines", "herdr_message"):
        assert removed not in cfg, removed


def test_supervisor_runs_fire_start_before_scan():
    text = _supervisor()
    steps = _section(text, "Do these steps in order.", "## Message: `done")
    assert steps.count("`pr-watch fire-start <name>`") == 1
    assert "`pr-watch fire-start <name>`" not in text.replace(steps, "")
    assert steps.index("`pr-watch running <name>`") < steps.index("`pr-watch fire-start <name>`")
    assert steps.index("`pr-watch fire-start <name>`") < steps.index("start one subagent")
    assert "once per fire" in steps


def test_supervisor_cap_reached_ends_fire():
    text = _supervisor()
    for needed in ("Exception: `tab-open` exiting 1 with `cap reached` in its error",
                   "Open nothing else", "how many reviews started this fire",
                   "the `N of N` in the error", "the other queued PRs wait for the next fire"):
        assert needed in text, needed
    step6 = _section(text, "6. The `process` list", "## Message: `done")
    assert "cap reached" in step6
    assert "cap reached" in _section(_done_section(), "3. Open the next PR", None)


def test_supervisor_retry_uses_ignore_cap():
    user = _section(_supervisor(), "## The user writes", "## Rules")
    retry = _section(user, '**"retry"**', "- **")
    assert "`pr-watch tab-open <name> <pr> --ignore-cap`" in retry
    assert _supervisor().count("--ignore-cap") == 1  # only the user-ordered retry bypasses the cap


def test_skill_md_documents_cap():
    text = _flat(_skill_md())
    assert "`max_reviews_per_fire`" in text and "default 4" in text
    assert "`pr-watch fire-start <name>`" in text
    assert "`pr-watch tab-open <name> <pr> [--ignore-cap]`" in text
    assert "`--ignore-cap`" in text
    assert "while a watcher runs" in text


def test_configure_asks_review_cap():
    text = _flat(_prompts()["configure.md"])
    assert "`max_reviews_per_fire`" in text and "Recommend `4`" in text
    assert text.index("`max_reviews_per_fire`:") < text.index("`persona_dir`: do not ask")


def test_example_config_mentions_cap_and_validates(config_dir, monkeypatch):
    text = (SKILL_DIR / "examples" / "fmha.yaml").read_text()
    line = next(l for l in text.splitlines() if "max_reviews_per_fire" in l)
    assert line.lstrip().startswith("# max_reviews_per_fire: 4") and "default" in line
    for check in ("_check_repo", "_check_checkout", "_check_persona"):
        monkeypatch.setattr(config, check, lambda cfg: [])
    monkeypatch.setattr(config.shutil, "which", lambda name: f"/usr/bin/{name}")
    (config_dir / "fmha.yaml").write_text(text)
    cfg = config.load("fmha")
    assert config.validate(cfg, "fmha") == []
    assert cfg["max_reviews_per_fire"] == 4
