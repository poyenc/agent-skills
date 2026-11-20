"""Static checks on the agent prompts in prompts/, SKILL.md and examples/."""
import re
from pathlib import Path

from prreview import cli, config, team

SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPTS = SKILL_DIR / "prompts"
REQUIRED = ("lead.md", "reviewer-task.md", "architect-task.md", "comment-style.md", "configure.md")
# Task templates: the values the lead fills in (lead.md names each key). lead.md itself is
# read as is by the invoking session, so it has no placeholders.
KEYS = {
    "reviewer-task.md": {"PR", "REPO", "CHECKOUT", "BASE", "HEAD", "FILES", "FOCUS", "THRESHOLD",
                         "MODE", "THREADS", "SAVED_REPORTS", "REPORT_PATH", "LEAD", "CLI"},
    "architect-task.md": {"PR", "REPO", "CHECKOUT", "BASE", "HEAD", "FILES", "SUMMARY",
                          "MODE", "THREADS", "SAVED_REPORTS", "REPORT_PATH", "LEAD", "CLI"},
}
COMMAND_RE = re.compile(r"(?:\bpr-review-auto|\{\{CLI\}\}) ([a-z][a-z-]*)")
RESULTS = ("reviewed", "approved", "escalated", "no-action", "not-interesting", "merged", "closed",
           "needs-config", "busy")
DONE = 'pr-review-auto notify <supervisor> "done <PR> <result> head=<sha|none> dry_run=<true|false> [summary]"'


def _prompts() -> dict[str, str]:
    found = {p.name: p.read_text() for p in sorted(PROMPTS.glob("*.md"))}
    missing = [name for name in REQUIRED if name not in found]
    assert not missing, f"missing prompts: {missing}"
    return found


def _skill_md() -> str:
    return (SKILL_DIR / "SKILL.md").read_text()


def _flat(text: str) -> str:
    return " ".join(text.split())


def _lead_section(title: str) -> str:
    """The lead.md section whose heading is `## <n>. <title>` (or `## <title>`), up to the next
    `## ` heading, whitespace collapsed."""
    text = _prompts()["lead.md"]
    start = re.search(rf"^## (?:\d+\. )?{re.escape(title)}$", text, re.MULTILINE)
    assert start, f"lead.md has no section {title!r}"
    end = text.find("\n## ", start.end())
    return _flat(text[start.start():end if end != -1 else None])


# --- commands ----------------------------------------------------------------

def test_prompts_reference_only_real_subcommands():
    real = set(cli.subcommand_names(cli.build_parser()))
    texts = {**_prompts(), "SKILL.md": _skill_md()}
    unknown = {(name, word) for name, text in texts.items()
               for word in COMMAND_RE.findall(text) if word not in real}
    assert not unknown


def test_command_check_covers_cli_calls():
    found = {name: set(COMMAND_RE.findall(text)) for name, text in _prompts().items()}
    assert {"paths", "validate", "lock", "unlock", "decide", "pr-state", "review-state", "checkout",
            "drop-branch", "cleanup", "gh", "spawn", "notify", "member-close"} <= found["lead.md"]
    assert "notify" in found["reviewer-task.md"] and "notify" in found["architect-task.md"]
    assert "validate" in found["configure.md"]
    assert COMMAND_RE.findall("run `{{CLI}} bogus x`") == ["bogus"]
    assert COMMAND_RE.findall("run `pr-review-auto bogus x`") == ["bogus"]


def test_skill_md_lists_every_subcommand():
    text = _skill_md()
    missing = [n for n in cli.subcommand_names(cli.build_parser()) if f"`pr-review-auto {n}" not in text]
    assert not missing, f"SKILL.md lacks: {missing}"


def test_skill_md_invocation_and_checkout_warning():
    text = _flat(_skill_md())
    assert ("/pr-review-auto <owner>/<repo> <PR> [--checkout <path>] [--supervisor <target>] "
            "[--interest <text>] [--decision <text>]") in text
    assert "follow `prompts/lead.md`" in text
    assert "deletes every uncommitted and untracked file" in text
    assert "whose `origin` is `<owner>/<repo>`" in text
    assert "`pr-review-auto checkout` refuses any other path and changes nothing there" in text
    assert "`pr-review-auto cleanup <owner>/<repo> --checkout <path>`" in text
    assert "checks that commit out, detached" in text
    assert "checks that commit out, detached" in _lead_section("Prepare")


# --- no reviewer groups, no outside dependencies -------------------------------

def _skill_texts() -> dict[str, str]:
    texts = {f"prompts/{k}": v for k, v in _prompts().items()}
    texts["SKILL.md"] = _skill_md()
    texts.update({f"examples/{p.name}": p.read_text() for p in (SKILL_DIR / "examples").iterdir()})
    return texts


def test_no_group_text():
    for name, text in _skill_texts().items():
        for forbidden in ("group", "max_files_per_reviewer"):
            assert forbidden not in text.lower(), f"{name} contains {forbidden!r}"


def test_prompts_do_not_assume_a_watcher():
    for name, text in _skill_texts().items():
        for forbidden in ("pr-watch", "watcher", "{{NAME}}"):
            assert forbidden not in text, f"{name} contains {forbidden!r}"


def test_no_runtime_commands_in_prompts():
    for name, text in _prompts().items():
        for forbidden in ("cmake", "make ", "ctest", "rocprof", "hipcc", "sleep"):
            assert forbidden not in text.lower(), f"{name} contains {forbidden!r}"


# --- lead: start of a run ------------------------------------------------------

def test_lead_reports_needs_config_when_started_by_supervisor():
    prepare = _lead_section("Prepare")
    assert "pr-review-auto paths <repo> <PR>" in prepare
    assert "exits 3" in prepare
    assert "With `--supervisor`: report `needs-config`" in prepare
    assert "never ask the user anything and never follow `configure.md`" in prepare
    assert "Without `--supervisor`: follow `<prompts>/configure.md` with the user" in prepare
    assert "pr-review-auto validate <repo>" in prepare
    # the config is settled before anything else happens
    needs_config = prepare.index("report `needs-config`")
    for later in ("pr-review-auto lock ", "pr-review-auto checkout ", "pr-review-auto spawn", "pr-review-auto gh "):
        assert later not in prepare or needs_config < prepare.index(later), later


def test_lead_reports_busy_and_stops():
    prepare = _lead_section("Prepare")
    assert "pr-review-auto lock <repo> <PR> --holder <holder>" in prepare
    assert '`{"busy": true, ...}`' in prepare
    assert ("report `busy` (**Report**; you do not hold the lock, so **Report** item 1 does "
            "nothing) and stop") in prepare
    # Report item 1 releases the lock only when this run took it
    assert 'If you hold the lock (step 1 item 5 printed `{"locked": true}`), release it' in (
        _lead_section("Report"))
    lock = prepare.index("pr-review-auto lock ")
    for later in ("pr-review-auto decide ", "pr-review-auto pr-state ", "pr-review-auto checkout ",
                  "pr-review-auto gh "):
        assert lock < prepare.index(later), later


def test_lead_merged_closed_drops_branch():
    prepare = _lead_section("Prepare")
    state = prepare.index("pr-review-auto pr-state <repo> <PR>")
    drop = prepare.index("pr-review-auto drop-branch <repo> <PR> --checkout <checkout>")
    assert "`MERGED` or `CLOSED`" in prepare
    assert "report `merged` or `closed`" in prepare
    assert state < drop < prepare.index("pr-review-auto checkout <repo> <PR> --checkout <checkout>")


def test_lead_stops_when_checkout_refuses_the_path():
    lead = _flat(_prompts()["lead.md"])
    assert "root of a git worktree whose `origin` is `<repo>`" in lead
    prepare = _lead_section("Prepare")
    checkout = prepare.index("pr-review-auto checkout <repo> <PR> --checkout <checkout>")
    refusal = prepare.index("its `origin` is not `<repo>`")
    assert checkout < refusal < prepare.index("gh pr view")
    assert ("Then do not retry: stop as in **When you cannot continue**, showing its message to "
            "the user") in prepare


def test_lead_does_not_reapprove_same_head():
    prepare = _lead_section("Prepare")
    check = prepare.index("pr-review-auto review-state <repo> <PR>")
    assert "`status` is `approved` and `last_reviewed_head` equals the PR's `head`" in prepare
    assert "report `no-action`" in prepare
    assert check < prepare.index("pr-review-auto checkout <repo> <PR> --checkout <checkout>")
    lead = _prompts()["lead.md"]
    assert "Never approve a head the notes already show approved" in _flat(lead)
    notes_format = lead[lead.index("## Notes file format"):]
    assert "- Status: <result>" in notes_format
    assert "set `Status:` to this run's result" in _lead_section("Finish")


def test_lead_records_and_applies_decision():
    prepare = _lead_section("Prepare")
    assert 'pr-review-auto decide <repo> <PR> "<decision text>"' in prepare
    follow_up = _lead_section("Act on GitHub: follow-up")
    assert "A `## Decision` in the notes" in follow_up
    finish = _lead_section("Finish")
    assert "remove the `## Decision` section" in finish


def test_lead_spot_check_only_with_interest():
    lead = _prompts()["lead.md"]
    assert "## 3. Spot-check (only with `--interest`)" in lead
    spot = _lead_section("Spot-check (only with `--interest`)")
    assert "Without `--interest`, skip this step" in spot
    assert "report `not-interesting`" in spot


def test_lead_spawns_from_checkout_reviewer_first():
    team_section = _lead_section("Start the team")
    reviewer = team_section.index("cd <checkout> && pr-review-auto spawn <repo> <PR> reviewer")
    architect = team_section.index("cd <checkout> && pr-review-auto spawn <repo> <PR> architect")
    assert reviewer < architect
    assert "Spawn the reviewer first" in team_section
    assert "one reviewer and one architect" in team_section


# --- lead: end of a run --------------------------------------------------------

def test_lead_done_format():
    report = _lead_section("Report")
    assert DONE in report
    for result in RESULTS:
        assert f"`{result}`" in report, result
    assert "`head=none`" in report
    assert "the config's `dry_run`" in report
    assert "Without `--supervisor`" in report


def test_lead_unlocks_on_every_exit():
    report = _lead_section("Report")
    unlock = report.index("pr-review-auto unlock <repo> <PR> --holder <holder>")
    assert unlock < report.index(DONE)
    assert "every exit after `lock` succeeded goes through this section" in report
    assert "pr-review-auto unlock <repo> <PR> --holder <holder>" in _lead_section("When you cannot continue")
    prepare = _lead_section("Prepare")
    assert "From here on, every exit ends with **Report**, which releases the lock" in prepare
    assert "Go to **Report**" in _lead_section("Finish")


def test_every_reported_result_points_to_report():
    """Each `report `<result>`` before the Report section names **Report** in its sentence."""
    lead = _prompts()["lead.md"]
    before = _flat(lead[:lead.index("\n## Report\n")])
    found = 0
    for match in re.finditer(r"\breport `([a-z-]+)`", before):
        assert match[1] in RESULTS, match[1]
        sentence = before[match.start():before.find(". ", match.end())]
        assert "(**Report**" in sentence, sentence
        found += 1
    reported = set(re.findall(r"\breport `([a-z-]+)`", before))
    assert {"needs-config", "busy", "merged", "no-action", "not-interesting"} <= reported
    assert found >= 6


def test_lead_cleans_up_after_a_checked_out_run():
    report = _lead_section("Report")
    cleanup = report.index("pr-review-auto cleanup <repo> --checkout <checkout>")
    assert "If this run checked out the PR (step 1 item 9)" in report
    assert "This step is not fatal" in report
    assert "do not retry it, and do not change the result" in report
    assert report.index("pr-review-auto unlock ") < cleanup < report.index(DONE)
    stuck = _lead_section("When you cannot continue")
    assert ("If this run checked out the PR, run `pr-review-auto cleanup <repo> --checkout <checkout>` "
            "as in **Report** item 2") in stuck
    branches = _flat(_skill_md().split("## Branches")[1].split("\n## ")[0])
    assert "Every run that checked out its PR also runs `cleanup`" in branches
    assert "a failure there does not change the run's result" in branches


def test_lead_finish_drops_branch_when_approved_and_closes_members():
    finish = _lead_section("Finish")
    assert "pr-review-auto member-close <agent>" in finish
    assert "pr-review-auto drop-branch <repo> <PR> --checkout <checkout>" in finish
    assert finish.index("member-close") < finish.index("drop-branch")


# --- lead: carried rules -------------------------------------------------------

def test_lead_names_every_template_key():
    prompts = _prompts()
    for name, keys in KEYS.items():
        assert set(team.PLACEHOLDER_RE.findall(prompts[name])) == keys, name
        rendered = team.render(PROMPTS / name, {k: f"<{k}>" for k in keys})
        assert "{{" not in rendered, name
    lead = prompts["lead.md"]
    assert "{{" not in lead
    for task in KEYS:
        assert task in lead
        for key in KEYS[task]:
            assert re.search(rf"\b{key}\b", lead), f"lead.md does not say how to fill {key}"


def test_lead_uses_cli_for_github():
    for name in ("lead.md", "reviewer-task.md", "architect-task.md"):
        text = _prompts()[name]
        for forbidden in ("gh api", "gh pr review", "gh pr comment"):
            assert forbidden not in text, f"{name} contains {forbidden!r}"


def test_lead_states_never_request_changes():
    text = _prompts()["lead.md"]
    assert "COMMENT" in text
    assert "REQUEST_CHANGES" not in text


def test_lead_has_no_supervisor_commands():
    text = _prompts()["lead.md"]
    for supervisor_only in ("tab-close", "tab-open", "set-status"):
        assert supervisor_only not in text


def test_task_templates_report_by_file():
    for name in KEYS:
        text = _prompts()[name]
        assert '{{CLI}} notify {{LEAD}} "report {{REPORT_PATH}}"' in text, name


def test_lead_rechecks_open_threads_on_new_commits():
    text = _flat(_prompts()["lead.md"])
    assert ("when HEAD differs from the last reviewed head, every thread whose state is not "
            "`addressed` or `accepted-author-view`") in text


def test_lead_has_one_follow_up_approval_rule():
    text = _flat(_prompts()["lead.md"])
    assert text.count("as in step 8 items 1-3; approval follows step 9's rule only") == 2
    assert "4. First review only: if there are no blocking findings, approve" in text
    assert "as in step 8 and" not in text and "posted as in step 8;" not in text


def test_lead_anchors_writes_on_reviewed_head():
    text = _flat(_prompts()["lead.md"])
    assert "post-review --commit <HEAD>" in text
    assert text.count("approve --commit <HEAD>") == 2
    assert '`{"skipped": "head-moved"}`' in text


def test_lead_reverifies_unposted_at_head():
    text = _flat(_prompts()["lead.md"])
    unposted = text[text.index("notes have an `## Unposted` section"):text.index("## 3. Spot-check")]
    assert "re-verify each finding against the code at HEAD" in unposted
    assert "re-anchor" in unposted
    assert unposted.index("re-verify") < unposted.index("post those that hold")


def test_example_config_shows_team_defaults_as_comments(review_home):
    text = (SKILL_DIR / "examples" / "config.yaml").read_text()
    for role, spec in (("reviewer", config.TEAM_DEFAULTS["reviewer"]),
                       ("architect", config.TEAM_DEFAULTS["architect"])):
        line = next(l for l in text.splitlines() if l.startswith(f"#   {role}:"))
        for value in spec.values():
            assert value in line, (role, value)
    assert not any(l.startswith("team:") for l in text.splitlines())


def test_example_config_validates_shape(write_config, review_home, monkeypatch):
    for check in ("_check_repo", "_check_team", "_check_files"):
        monkeypatch.setattr(config, check, lambda *args: [])
    path = review_home / "o" / "r" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text((SKILL_DIR / "examples" / "config.yaml").read_text())
    cfg = config.load("o/r")
    assert config.validate(cfg, "o/r") == []
    assert cfg["dry_run"] is True
    assert cfg["team"] == config.TEAM_DEFAULTS


# --- configure -----------------------------------------------------------------

def test_configure_asks_repository_fields_and_validates_candidate():
    text = _flat(_prompts()["configure.md"])
    for field in ("team.reviewer", "team.architect", "blocking_threshold", "dry_run", "skip_paths",
                  "unrelated_change_lines", "persona_dir", "lock_stale_after"):
        assert f"`{field}`" in text, field
    assert "Ask one question at a time" in text
    assert "Ask for `persona_dir` only when the default does not exist" in text
    assert "PR_REVIEW_AUTO_HOME=<tmpdir> pr-review-auto validate <owner>/<repo>" in text
    assert "<tmpdir>/<owner>/<repo>/config.yaml" in text
    assert text.index("pr-review-auto validate") < text.index("move the candidate")


def test_configure_states_team_defaults_and_asks_only_to_override():
    text = _flat(_prompts()["configure.md"])
    for spec in config.TEAM_DEFAULTS.values():
        for value in spec.values():
            assert value in text, value
    assert "ask only whether to override" in text


def test_configure_changes_dry_run_only_without_a_run():
    text = _flat(_prompts()["configure.md"])
    assert "`dry_run` cannot change while a run holds a lock on this repository" in text
    assert "separate, clean state directory" in text


# --- comment style -------------------------------------------------------------

def test_comment_style_exists_and_lead_uses_it():
    assert "comment-style.md" in _prompts()
    ref = "`<prompts>/comment-style.md`"
    assert ref in _lead_section("Draft")
    assert ref in _lead_section("Act on GitHub: follow-up")


def test_comment_style_has_no_posting():
    text = _flat(_prompts()["comment-style.md"])
    for forbidden in ("gh api", "gh pr", "post-review", "{{CLI}}", "post each",
                      "inline comment when its line"):
        assert forbidden not in text.lower() and forbidden not in text, forbidden
    assert "placement and posting follow the lead's policy" in text


def test_comment_style_is_self_contained():
    text = _prompts()["comment-style.md"]
    assert "{{" not in text
    for other_skill in ("skills/", "SKILL.md", "~/"):
        assert other_skill not in text, other_skill


# --- cross-review exchange -----------------------------------------------------

CROSS_REVIEW = "Cross-review (first review only)"
TASKS = ("reviewer-task.md", "architect-task.md")


def _task_section(name: str, heading: str) -> str:
    """The task template section starting at `## <heading>`, up to the next `## ` heading."""
    text = _prompts()[name]
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)
    return _flat(text[start:end if end != -1 else None])


def test_lead_starts_exchange_after_all_reports():
    section = _lead_section(CROSS_REVIEW)
    assert "after every member has sent `report <path>`" in section
    assert "only after every member has replied `critique <path>`" in section
    assert section.index('"critique ') < section.index('"revise ') < section.index("<reports>/")
    assert "after every member has replied `revised <path>`" in section


def test_exchange_is_first_review_only_and_once():
    lead = _prompts()["lead.md"]
    assert (lead.index("## 4. Start the team") < lead.index(f"## 5. {CROSS_REVIEW}")
            < lead.index("## 6. Verify"))
    section = _lead_section(CROSS_REVIEW)
    assert "A follow-up skips this step" in section
    assert "one critique and one revision per member" in section


def test_exchange_pairs_reviewer_and_architect():
    section = _lead_section(CROSS_REVIEW)
    assert "the reviewer reads the architect's report and the architect reads the reviewer's" in section


def test_exchange_messages_match_templates():
    section = _lead_section(CROSS_REVIEW)
    assert 'pr-review-auto notify <agent> "critique <report path> into <runs>/<agent>-critique.md"' in section
    assert 'pr-review-auto notify <agent> "revise <critique path>"' in section
    for name in TASKS:
        exchange = _task_section(name, CROSS_REVIEW)
        assert "`critique <report path> into <critique path>`" in exchange, name
        assert '{{CLI}} notify {{LEAD}} "critique <critique path>"' in exchange, name
        assert "`revise <critique path>`" in exchange, name
        assert '{{CLI}} notify {{LEAD}} "revised {{REPORT_PATH}}"' in exchange, name


def test_revise_explains_kept_or_dropped():
    for name in TASKS:
        exchange = _task_section(name, CROSS_REVIEW)
        revise = exchange[exchange.index("**Revise.**"):].lower()
        for needed in ("revise your own report, {{report_path}}, in place",
                       "fix what the critique showed, or say why a disputed point stands",
                       "add findings only in your own area",
                       "belongs in your critique",
                       "never edit the other report"):
            assert needed in revise, (name, needed)


def test_reports_saved_per_reviewed_sha():
    section = _lead_section(CROSS_REVIEW)
    assert "<reports>/<reviewed-sha>/" in section
    assert "copy every member's final report and critique" in section
    assert "nothing fetchable from GitHub or derivable from git" in section
    assert "<reports>/<reviewed-sha>/" in _prompts()["lead.md"].split("## Rules")[0]


def test_saved_reports_sha_separate_from_last_reviewed_head():
    lead = _prompts()["lead.md"]
    notes_format = lead[lead.index("## Notes file format"):]
    assert "- Last reviewed head: <sha>" in notes_format
    assert "- Saved reports: <sha>" in notes_format
    team_section = _lead_section("Start the team")
    assert ("SAVED_REPORTS: in a follow-up, `<reports>/<saved-sha>/`, where saved-sha is the "
            "notes' `Saved reports:` line, if that line and directory exist, otherwise `none`") in team_section
    assert "<last reviewed head>/" not in lead
    assert "the notes' `Saved reports:` line" in _lead_section(CROSS_REVIEW)
    assert "a follow-up never changes `Saved reports:`" in _lead_section("Finish")
    for name in TASKS:
        follow_up = _task_section(name, "Mode follow-up")
        assert "from the first review" in follow_up and "directory's name" not in follow_up, name


def test_follow_up_reads_saved_reports_and_new_commits():
    for name in TASKS:
        follow_up = _task_section(name, "Mode follow-up")
        assert "Saved reports: {{SAVED_REPORTS}}." in follow_up, name
        assert "`git -C {{CHECKOUT}} diff <last-reviewed-sha> {{HEAD}}`" in follow_up, name
        assert "other files only where a thread's saved evidence points" in follow_up, name
        assert "a follow-up never raises new issues" in follow_up, name


def test_follow_up_without_saved_reports_reads_files():
    for name in TASKS:
        follow_up = _task_section(name, "Mode follow-up")
        assert "If that is `none`" in follow_up and "read files as needed" in follow_up, name


def test_follow_up_thread_without_saved_evidence_reads_files():
    for name in TASKS:
        follow_up = _task_section(name, "Mode follow-up")
        assert ("Read other files only where a thread's saved evidence points. A thread the saved "
                "reports do not cover: read files as needed for it.") in follow_up, name


def test_draft_checks_diff_coverage_inline():
    draft = _lead_section("Draft")
    assert "inside a hunk of `git -C <checkout> diff BASE HEAD -- <path>`" in draft
    assert "items 1-2" not in draft


def test_follow_up_replies_follow_tone_rules_only():
    act = _lead_section("Act on GitHub: follow-up")
    assert ("Keep each reply short: follow the tone and wording rules of "
            "`<prompts>/comment-style.md`, not its two-paragraph shape for findings") in act


# --- preview of a merged or closed PR (--include-merged) -------------------------

def test_skill_md_documents_include_merged():
    text = _flat(_skill_md())
    assert "[--decision <text>] [--include-merged]" in text
    assert "- `--include-merged`:" in text
    assert "recorded in the PR's notes, never posted" in text


def test_lead_continues_past_merged_closed_only_with_include_merged():
    lead = _flat(_prompts()["lead.md"])
    assert "[--decision <text>] [--include-merged]" in lead
    prepare = _lead_section("Prepare")
    without = prepare.index("Without `--include-merged`, run `pr-review-auto drop-branch")
    stop = prepare.index("report `merged` or `closed` (**Report**), and stop")
    with_flag = prepare.index("With `--include-merged`, continue this run as a preview")
    assert prepare.index("`MERGED` or `CLOSED`") < without < stop < with_flag
    assert with_flag < prepare.index("pr-review-auto checkout <repo> <PR> --checkout <checkout>")


def test_lead_preview_reports_dry_run_never_approves_and_drops_branch():
    finish = _lead_section("Finish")
    assert "In a preview, the result is never `approved`" in finish
    assert "never set `Status: approved`" in finish
    drop = finish.index("pr-review-auto drop-branch <repo> <PR> --checkout <checkout>")
    assert "or this run is a preview" in finish[:drop + 200]
    assert finish.index("member-close") < drop < finish.index("Go to **Report**")
    report = _lead_section("Report")
    assert "`true` in a preview" in report
    assert "writes were recorded in `<notes>`, not posted" in report
    rules = _lead_section("Rules")
    assert '`{"dry_run": true, "not_posted": "<reason>"}`' in rules


# --- full first review of a PR that already has review threads (--full-review) ---

REFUSAL = '"--full-review needs dry_run: true (it would duplicate the existing review comments)"'


def test_skill_md_documents_full_review():
    text = _flat(_skill_md())
    assert "[--include-merged] [--full-review]" in text
    assert "- `--full-review`:" in text
    assert "requires `dry_run: true`" in text
    assert "`dry_run=true`" in text[text.index("- `--full-review`:"):]


def test_lead_refuses_full_review_unless_dry_run_before_locking():
    lead = _flat(_prompts()["lead.md"])
    assert "[--include-merged] [--full-review]" in lead
    prepare = _lead_section("Prepare")
    config = prepare.index("Read the repository config file")
    refusal = prepare.index(REFUSAL)
    lock = prepare.index("run `pr-review-auto lock <repo> <PR> --holder <holder>`")
    assert config < refusal < lock
    around = prepare[refusal - 250:refusal]
    assert "With `--full-review`" in around and "`dry_run` is not `true`" in around
    assert "go to **When you cannot continue**" in around
    assert "Nothing is posted or reset" in prepare[refusal:lock]
    assert "If you hold the lock, release it" in _lead_section("When you cannot continue")


def test_lead_full_review_forces_first_review_and_leaves_threads_alone():
    mode = _lead_section("Choose the mode")
    first = mode.index("With `--full-review`")
    assert first < mode.index("The notes file exists")
    section = mode[first:mode.index("The notes file exists")]
    assert "**first review**, whatever the notes or the threads of ours say" in section
    assert "Do not import the existing GitHub threads" in section
    assert "never change or reply to them" in section
    assert "Replace any existing notes file with a fresh one" in section
    assert "only dry-run state is replaced" in section
    assert "`pr-review-auto gh`" in section
    assert "`dry_run=true`" in section
    prepare = _lead_section("Prepare")
    assert "(not with `--full-review`)" in prepare[prepare.index("review-state"):]


# --- reading scope -----------------------------------------------------------

def test_task_rules_bound_reading_to_the_diff_and_one_hop():
    for name in TASKS:
        rules = _task_section(name, "Rules")
        assert "Reading scope:" in rules, name
        assert "full definition on both sides" in rules, name
        assert "direct callers and the direct callees" in rules and "one hop" in rules, name
        assert ("only when a specific finding you are already forming needs it, and name that "
                "finding and why in your report next to the evidence") in rules, name
        assert "Do not read unrelated files" in rules, name
        assert "other tests, docs or history" in rules, name
        assert "This replaces your default instruction to read" in rules, name
        assert "adjacent lifecycle paths" in rules, name


def test_architect_looks_for_reusable_mechanisms_by_targeted_search():
    rules = _task_section("architect-task.md", "Rules")
    assert ("Looking for an existing mechanism the change should reuse is a targeted search: name "
            "the mechanism you are checking for") in rules
    assert "not a general read" in rules
