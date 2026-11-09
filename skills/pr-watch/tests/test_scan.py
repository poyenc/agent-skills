"""Tests for pending / commit-classified / queue / finish.

Fake `gh` matching scheme (the fake matches argv prefixes only):
- `gh pr list ...`            -> ["pr", "list"]
- `gh pr view <N> ...`        -> ["pr", "view", "<N>"]
- `gh api user ...`           -> ["api", "user"]
- `gh api graphql ...`        -> the production code puts `-F number=<N>` first,
  so a PR's response matches ["api", "graphql", "-F", "number=<N>"].
"""
import io
import json

import pytest

from prwatch import cli, config, record, scan

LAST_RUN = "2026-11-01T00:00:00Z"
OLD = "2026-10-30T00:00:00Z"
NEWER = "2026-11-02T00:00:00Z"
NEWEST = "2026-11-03T00:00:00Z"


@pytest.fixture
def cfg(write_config):
    write_config()
    return config.load("fmha")


def run(capsys, *argv) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def run_json(capsys, *argv):
    code, out = run(capsys, *argv)
    assert code == 0
    return json.loads(out)


def pr_list_response(*numbers, author="alice"):
    prs = [
        {"number": n, "title": f"t{n}", "body": f"b{n}", "isDraft": False,
         "author": {"login": author}, "labels": [], "baseRefName": "develop"}
        for n in numbers
    ]
    return {"match": ["pr", "list"], "stdout": json.dumps(prs)}


NO_FILES = {"match": ["pr", "view"], "stdout": '{"files": []}'}


def files_response(number, *paths):
    return {"match": ["pr", "view", str(number)],
            "stdout": json.dumps({"files": [{"path": p} for p in paths]})}


def gql_response(number, state="OPEN", draft=False, author="alice", updated=NEWER,
                 head="h1", comments=(), reviews=(), thread_comments=(), exit=0):
    def node(login, typename, when, key):
        return {"author": {"login": login, "__typename": typename}, key: when}

    pull_request = {
        "state": state, "isDraft": draft, "author": {"login": author},
        "updatedAt": updated, "headRefOid": head,
        "comments": {"nodes": [node(*c, "createdAt") for c in comments]},
        "reviews": {"nodes": [node(*r, "submittedAt") for r in reviews]},
        "reviewThreads": {"nodes": [
            {"comments": {"nodes": [node(*c, "createdAt") for c in thread_comments]}}
        ]},
    }
    return {
        "match": ["api", "graphql", "-F", f"number={number}"],
        "stdout": json.dumps({"data": {"repository": {"pullRequest": pull_request}}}),
        "exit": exit,
    }


USER = {"match": ["api", "user"], "stdout": "me\n"}


def seed(cfg, prs, mark=None):
    """prs: {number: dict of record fields overriding a first-run-done default}."""
    base = {"reason": "r", "status": "reviewed", "updated_at": OLD,
            "head_sha": "h1", "last_run_at": LAST_RUN}
    record.save(cfg, {"last_scanned_pr": mark, "prs": {n: {**base, **o} for n, o in prs.items()}})


# --- pending -----------------------------------------------------------------

def test_pending_only_above_mark(cfg, fake, capsys):
    seed(cfg, {}, mark=100)
    fake({"gh": [pr_list_response(99, 101, 102), NO_FILES]})
    out = run_json(capsys, "pending", "fmha")
    assert [p["number"] for p in out["to_classify"]] == [101, 102]
    assert out["max_pr"] == 102


def test_pending_no_new_prs_keeps_mark(cfg, fake, capsys):
    seed(cfg, {}, mark=100)
    fake({"gh": [pr_list_response(99)]})
    assert run_json(capsys, "pending", "fmha") == {"max_pr": 100, "to_classify": [], "more": False}


def test_pending_batch_is_lowest_numbers_and_caps_max_pr(cfg, fake, capsys):
    seed(cfg, {}, mark=100)
    calls = fake({"gh": [pr_list_response(*range(130, 100, -1)), NO_FILES]})
    out = run_json(capsys, "pending", "fmha")
    assert [p["number"] for p in out["to_classify"]] == list(range(101, 111))
    assert out["max_pr"] == 110 and out["more"] is True
    # only the batch's file lists are fetched
    assert len([a for a in calls.of("gh") if a[:2] == ["pr", "view"]]) == 10


def test_pending_limit_flag_and_last_batch(cfg, fake, capsys):
    seed(cfg, {}, mark=100)
    fake({"gh": [pr_list_response(101, 102, 103), NO_FILES]})
    out = run_json(capsys, "pending", "fmha", "--limit", "2")
    assert [p["number"] for p in out["to_classify"]] == [101, 102]
    assert out["max_pr"] == 102 and out["more"] is True
    out = run_json(capsys, "pending", "fmha", "--limit", "3")
    assert out["max_pr"] == 103 and out["more"] is False


def test_pending_loop_covers_every_pr(cfg, fake, capsys, monkeypatch):
    numbers = [3, 8, 9, 15, 16, 17, 21, 40, 41, 42, 43, 50]
    fake({"gh": [pr_list_response(*numbers), NO_FILES]})
    seen = []
    for _ in range(10):
        out = run_json(capsys, "pending", "fmha", "--limit", "5")
        batch = [p["number"] for p in out["to_classify"]]
        assert out["max_pr"] == max(batch, default=out["max_pr"])
        seen += batch
        payload = {"max_pr": out["max_pr"], "interesting": [{"number": n, "reason": "r"} for n in batch]}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert cli.main(["commit-classified", "fmha"]) == 0
        if not out["more"]:
            break
    assert seen == numbers
    rec = record.load(cfg)
    assert rec["last_scanned_pr"] == 50 and sorted(rec["prs"]) == numbers


def test_pending_dir_counts(cfg, fake, capsys):
    fake({"gh": [pr_list_response(101), files_response(101, "a/b/x.cpp", "a/b/y.cpp", "c/z.py")]})
    out = run_json(capsys, "pending", "fmha")
    assert out["to_classify"][0]["dir_counts"] == {"a/b": 2, "c/z.py": 1}


def test_pending_truncates_body_and_passes_prefilter(write_config, fake, capsys):
    write_config(prefilter={"labels": ["l1", "l2"], "base": "develop"})
    long_body = "x" * 3000
    calls = fake({"gh": [{"match": ["pr", "list"], "stdout": json.dumps([
        {"number": 5, "title": "t", "body": long_body, "isDraft": False,
         "author": {"login": "a"}, "labels": [], "baseRefName": "develop"}])}, NO_FILES]})
    out = run_json(capsys, "pending", "fmha")
    assert len(out["to_classify"][0]["body"]) == 2000
    listing = calls.of("gh")[0]
    assert listing[:6] == ["pr", "list", "--repo", "o/r", "--state", "open"]
    assert listing[listing.index("--base") + 1] == "develop"
    assert [listing[i + 1] for i, a in enumerate(listing) if a == "--label"] == ["l1", "l2"]


def pr_with_body(number, body):
    return {"number": number, "title": f"t{number}", "body": body, "isDraft": False,
            "author": {"login": "alice"}, "labels": [], "baseRefName": "develop"}


def test_pending_batch_stops_at_output_budget(cfg, monkeypatch, capsys):
    # "é" is 6 characters once json.dumps escapes it: ten 2000-char bodies print ~120K.
    # Answered in-process: the fake gh passes responses through an environment variable,
    # which is too small for this much text.
    prs = [pr_with_body(n, "é" * 2000) for n in range(101, 111)]
    monkeypatch.setattr(scan.proc, "gh_json",
                        lambda *a: prs if a[:2] == ("pr", "list") else {"files": []})
    code, printed = run(capsys, "pending", "fmha")
    assert code == 0 and len(printed) <= 20000
    out = json.loads(printed)
    numbers = [p["number"] for p in out["to_classify"]]
    assert 1 <= len(numbers) < 10 and numbers == list(range(101, 101 + len(numbers)))
    assert out["more"] is True and out["max_pr"] == numbers[-1]


def test_pending_dir_counts_keep_the_largest_fifty(cfg, fake, capsys):
    paths = [f"d{i:03d}/sub/f{j}.c" for i in range(400) for j in range(1 + (i < 5))]
    fake({"gh": [pr_list_response(101), files_response(101, *paths)]})
    entry = run_json(capsys, "pending", "fmha")["to_classify"][0]
    assert len(entry["dir_counts"]) == 50 and entry["dir_counts_truncated"] == 350
    assert sorted(entry["dir_counts"].values(), reverse=True)[:5] == [2] * 5


def test_pending_dir_counts_not_truncated_when_small(cfg, fake, capsys):
    fake({"gh": [pr_list_response(101), files_response(101, "a/b/x.cpp")]})
    assert "dir_counts_truncated" not in run_json(capsys, "pending", "fmha")["to_classify"][0]


def test_pending_single_oversized_pr_is_returned_within_budget(cfg, fake, capsys):
    seed(cfg, {}, mark=100)
    paths = [f"{'q' * 100}{i:03d}/{'w' * 100}/f.c" for i in range(400)]
    fake({"gh": [{"match": ["pr", "list"],
                  "stdout": json.dumps([pr_with_body(105, "é" * 2000), pr_with_body(106, "x")])},
                 files_response(105, *paths), NO_FILES]})
    code, printed = run(capsys, "pending", "fmha")
    assert code == 0 and len(printed) <= 20000
    out = json.loads(printed)
    assert [p["number"] for p in out["to_classify"]] == [105]
    assert 0 < len(out["to_classify"][0]["body"]) < 2000
    assert out["max_pr"] == 105 and out["more"] is True


def test_pending_filters_authors_locally(write_config, fake, capsys):
    write_config(prefilter={"authors": ["bob"]})
    fake({"gh": [{"match": ["pr", "list"], "stdout": json.dumps([
        {"number": 1, "title": "", "body": "", "author": {"login": "bob"}},
        {"number": 2, "title": "", "body": "", "author": {"login": "eve"}}])}, NO_FILES]})
    out = run_json(capsys, "pending", "fmha")
    assert [p["number"] for p in out["to_classify"]] == [1]


# --- commit-classified -------------------------------------------------------

def test_commit_classified_records_only_interesting(cfg, fake, capsys, monkeypatch):
    seed(cfg, {}, mark=100)
    payload = {"max_pr": 102, "interesting": [{"number": 101, "reason": "fmha kernel"}]}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert cli.main(["commit-classified", "fmha"]) == 0
    rec = record.load(cfg)
    assert rec["last_scanned_pr"] == 102
    assert rec["prs"] == {101: {"reason": "fmha kernel", "status": "new", "updated_at": None,
                                "head_sha": None, "last_run_at": None}}


def test_commit_classified_keeps_existing_entry(cfg, capsys, monkeypatch):
    seed(cfg, {101: {}}, mark=None)
    payload = {"max_pr": 101, "interesting": [{"number": 101, "reason": "again"}]}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert cli.main(["commit-classified", "fmha"]) == 0
    assert record.load(cfg)["prs"][101]["reason"] == "r"


# --- queue -------------------------------------------------------------------

def queue(cfg, fake, capsys, *responses):
    fake({"gh": [USER, *responses]})
    return run_json(capsys, "queue", "fmha")


def test_queue_first_seen(cfg, fake, capsys):
    seed(cfg, {7: {"status": "new", "updated_at": None, "head_sha": None, "last_run_at": None}})
    assert queue(cfg, fake, capsys, gql_response(7)) == {"process": [7]}


def test_queue_process_sorted_ascending(cfg, fake, capsys):
    new = {"status": "new", "updated_at": None, "head_sha": None, "last_run_at": None}
    seed(cfg, {9: new, 3: new, 5: new})
    out = queue(cfg, fake, capsys, gql_response(3), gql_response(5), gql_response(9))
    assert out["process"] == [3, 5, 9]


def test_queue_label_only_update_skipped(cfg, fake, capsys):
    seed(cfg, {7: {}})
    bot = gql_response(7, comments=[("ci", "Bot", NEWER)])
    assert queue(cfg, fake, capsys, bot)["process"] == []


def test_queue_bot_login_suffix_is_bot(cfg, fake, capsys):
    seed(cfg, {7: {}})
    bot = gql_response(7, reviews=[("dependabot[bot]", "User", NEWER)])
    assert queue(cfg, fake, capsys, bot)["process"] == []


def test_queue_unchanged_updated_at_skipped(cfg, fake, capsys):
    seed(cfg, {7: {}})
    same = gql_response(7, updated=OLD, comments=[("bob", "User", NEWEST)])
    assert queue(cfg, fake, capsys, same)["process"] == []


def test_queue_new_head_counts_before_updated_at(cfg, fake, capsys):
    # updated_at is stored after the run; a push during the run leaves it equal to GitHub's.
    seed(cfg, {7: {}})
    assert queue(cfg, fake, capsys, gql_response(7, updated=OLD, head="h2"))["process"] == [7]


def test_queue_new_head(cfg, fake, capsys):
    seed(cfg, {7: {}})
    assert queue(cfg, fake, capsys, gql_response(7, head="h2"))["process"] == [7]


def test_queue_human_reply(cfg, fake, capsys):
    seed(cfg, {7: {}})
    reply = gql_response(7, thread_comments=[("bob", "User", NEWEST)])
    assert queue(cfg, fake, capsys, reply)["process"] == [7]


def test_queue_old_human_comment_skipped(cfg, fake, capsys):
    seed(cfg, {7: {}})
    old = gql_response(7, comments=[("bob", "User", OLD)], reviews=[("bob", "User", LAST_RUN)])
    assert queue(cfg, fake, capsys, old)["process"] == []


def test_queue_merged_is_recorded_never_processed(cfg, fake, capsys):
    seed(cfg, {7: {}})
    out = queue(cfg, fake, capsys, gql_response(7, state="MERGED", head="h2"))
    assert out == {"process": []}
    assert record.load(cfg)["prs"][7]["status"] == "merged"


def test_queue_closed_is_recorded_never_processed(cfg, fake, capsys):
    seed(cfg, {7: {}})
    out = queue(cfg, fake, capsys, gql_response(7, state="CLOSED"))
    assert out == {"process": []}
    assert record.load(cfg)["prs"][7]["status"] == "closed"


def test_queue_already_merged_is_not_queried_again(cfg, fake, capsys):
    seed(cfg, {7: {"status": "merged"}})
    calls = fake({"gh": [USER]})
    assert run_json(capsys, "queue", "fmha") == {"process": []}
    assert not any(a[:2] == ["api", "graphql"] for a in calls.of("gh"))


def test_queue_approved_never_processed(cfg, fake, capsys):
    seed(cfg, {7: {"status": "approved"}})
    out = queue(cfg, fake, capsys, gql_response(7, head="h2"))
    assert out == {"process": []}
    assert record.load(cfg)["prs"][7]["status"] == "approved"


def test_queue_stalled_skipped(cfg, fake, capsys):
    seed(cfg, {7: {"status": "stalled"}})
    assert queue(cfg, fake, capsys, gql_response(7, head="h2")) == {"process": []}


def test_queue_escalated_needs_decision(cfg, fake, capsys):
    seed(cfg, {7: {"status": "escalated"}})
    responses = [gql_response(7, updated=OLD)]
    assert queue(cfg, fake, capsys, *responses)["process"] == []
    assert cli.main(["decide", "fmha", "7", "go with the author's view"]) == 0
    assert queue(cfg, fake, capsys, *responses)["process"] == [7]


def test_queue_escalated_on_activity(cfg, fake, capsys):
    seed(cfg, {7: {"status": "escalated"}})
    quiet = gql_response(7, updated=OLD, comments=[("bob", "User", NEWEST)])
    assert queue(cfg, fake, capsys, quiet)["process"] == []
    reply = gql_response(7, thread_comments=[("bob", "User", NEWEST)])
    assert queue(cfg, fake, capsys, reply)["process"] == [7]
    assert queue(cfg, fake, capsys, gql_response(7, head="h2"))["process"] == [7]


def test_queue_draft_and_own_filters(write_config, fake, capsys):
    new = {"status": "new", "updated_at": None, "head_sha": None, "last_run_at": None}
    responses = [gql_response(1, draft=True), gql_response(2, author="me")]

    write_config()
    cfg = config.load("fmha")
    seed(cfg, {1: new, 2: new})
    fake({"gh": [USER, *responses]})
    assert run_json(capsys, "queue", "fmha")["process"] == []

    write_config(prefilter={"include_drafts": True, "include_own_prs": True})
    fake({"gh": [USER, *responses]})
    assert run_json(capsys, "queue", "fmha")["process"] == [1, 2]


def test_queue_gh_failure_leaves_record_unchanged(cfg, fake, capsys):
    seed(cfg, {1: {}, 2: {}})
    path = config.state_dir(cfg) / "record.yaml"
    before = path.read_bytes()
    fake({"gh": [USER, gql_response(1, state="MERGED"), gql_response(2, exit=1)]})
    assert cli.main(["queue", "fmha"]) != 0
    assert path.read_bytes() == before


# --- finish ------------------------------------------------------------------

def finish_state(cfg, fake, capsys, pr, result, head="h1", dry_run="false"):
    fake({"gh": [{"match": ["pr", "view", str(pr)],
                  "stdout": json.dumps({"updatedAt": NEWEST, "headRefOid": "h9"})}]})
    code, _ = run(capsys, "finish", "fmha", str(pr), result, "--head", head, "--dry-run", dry_run)
    assert code == 0
    return record.load(cfg)["prs"]


def test_finish_parses_head_and_dry_run(cfg, fake, capsys):
    seed(cfg, {7: {"status": "new"}, 8: {"status": "new"}, 9: {"status": "new"}})
    prs = finish_state(cfg, fake, capsys, 7, "reviewed", head="abc123", dry_run="true")
    assert (prs[7]["head_sha"], prs[7]["dry_run"]) == ("abc123", True)
    prs = finish_state(cfg, fake, capsys, 8, "approved", head="def456", dry_run="false")
    assert (prs[8]["head_sha"], prs[8]["dry_run"]) == ("def456", False)
    # head=none: nothing was reviewed, so the PR's current head is recorded (no endless requeue)
    prs = finish_state(cfg, fake, capsys, 9, "no-action", head="none", dry_run="false")
    assert prs[9]["head_sha"] == "h9"
    assert (prs[7]["updated_at"], prs[7]["last_run_at"] > LAST_RUN) == (NEWEST, True)


def test_finish_rejects_bad_head_and_dry_run_arguments(cfg, fake, capsys):
    seed(cfg, {7: {}})
    fake()
    with pytest.raises(SystemExit):
        cli.main(["finish", "fmha", "7", "reviewed", "--head", "h1", "--dry-run", "maybe"])
    with pytest.raises(SystemExit):
        cli.main(["finish", "fmha", "7", "reviewed"])
    with pytest.raises(SystemExit):
        cli.main(["finish", "fmha", "7", "bogus", "--head", "h1", "--dry-run", "true"])


@pytest.mark.parametrize("result", ["reviewed", "approved", "escalated", "merged", "closed"])
def test_finish_sets_status(cfg, fake, capsys, result):
    seed(cfg, {7: {"status": "new"}})
    assert finish_state(cfg, fake, capsys, 7, result)[7]["status"] == result


def test_finish_no_action_keeps_status(cfg, fake, capsys):
    seed(cfg, {7: {"status": "reviewed", "tab_id": "t1", "run_started_at": "x"}})
    entry = finish_state(cfg, fake, capsys, 7, "no-action")[7]
    assert entry["status"] == "reviewed"
    assert (entry["updated_at"], entry["head_sha"]) == (NEWEST, "h1")
    assert entry["last_run_at"].endswith("Z") and entry["last_run_at"] > LAST_RUN
    assert "tab_id" not in entry and "run_started_at" not in entry


def test_finish_not_interesting_removes(cfg, fake, capsys):
    seed(cfg, {7: {}, 8: {}})
    calls = fake()
    assert cli.main(["finish", "fmha", "7", "not-interesting", "--head", "none", "--dry-run", "false"]) == 0
    assert list(record.load(cfg)["prs"]) == [8]
    assert calls.of("gh") == []


def test_finish_unknown_pr_fails(cfg, fake, capsys):
    seed(cfg, {})
    fake()
    assert cli.main(["finish", "fmha", "7", "reviewed", "--head", "h1", "--dry-run", "false"]) == 1


def test_finish_needs_config_and_busy_retry_next_fire(cfg, fake, capsys):
    before = {"status": "reviewed", "updated_at": OLD, "head_sha": "h1", "last_run_at": LAST_RUN,
              "dry_run": True, "decision": "keep me", "tab_id": "t1", "run_started_at": "x"}
    for result in ("needs-config", "busy"):
        seed(cfg, {7: before, 8: {**before, "status": "new", "updated_at": None}})
        calls = fake()
        for pr in (7, 8):
            assert cli.main(["finish", "fmha", str(pr), result, "--head", "none", "--dry-run", "false"]) == 0
        # no post-run updatedAt is fetched: the PR must look changed next fire
        assert not [c for c in calls.of("gh") if c[:2] == ["pr", "view"]]
        prs = record.load(cfg)["prs"]
        kept = {"reason": "r", **{k: v for k, v in before.items() if k not in ("tab_id", "run_started_at")}}
        assert prs[7] == kept
        assert prs[8]["status"] == "new" and prs[8]["updated_at"] is None
        # human activity older than any retry marker is still seen next fire
        reply = gql_response(7, thread_comments=[("bob", "User", NEWEST)])
        reply8 = gql_response(8, updated=OLD)
        assert queue(cfg, fake, capsys, reply, reply8)["process"] == [7, 8]


def seed_started(cfg, started):
    seed(cfg, {7: {"status": "new"}, 8: {"status": "new"}, 9: {"status": "new"}})
    rec = record.load(cfg)
    record.start_fire(rec, "2026-11-10T00:00:00Z")
    rec["fire"]["started"] = list(started)
    record.save(cfg, rec)


@pytest.mark.parametrize("result", ["busy", "needs-config"])
def test_finish_busy_and_needs_config_return_the_slot(cfg, fake, capsys, result):
    seed_started(cfg, [7, 8])
    fake()
    assert cli.main(["finish", "fmha", "7", result, "--head", "none", "--dry-run", "false"]) == 0
    assert record.load(cfg)["fire"] == {"started_at": "2026-11-10T00:00:00Z", "started": [8]}


@pytest.mark.parametrize("result", ["reviewed", "no-action", "not-interesting"])
def test_finish_other_results_keep_the_slot(cfg, fake, capsys, result):
    seed_started(cfg, [7, 8])
    fake({"gh": [{"match": ["pr", "view", "7"],
                  "stdout": json.dumps({"updatedAt": NEWEST, "headRefOid": "h9"})}]})
    assert cli.main(["finish", "fmha", "7", result, "--head", "none", "--dry-run", "false"]) == 0
    assert record.load(cfg)["fire"]["started"] == [7, 8]


def test_finish_busy_twice_or_unlisted_is_safe(cfg, fake, capsys):
    seed_started(cfg, [7, 8])
    fake()
    for pr in (7, 7, 9):
        assert cli.main(["finish", "fmha", str(pr), "busy", "--head", "none", "--dry-run", "false"]) == 0
    assert record.load(cfg)["fire"]["started"] == [8]
    seed(cfg, {7: {}})  # a record without a window
    assert cli.main(["finish", "fmha", "7", "busy", "--head", "none", "--dry-run", "false"]) == 0
    assert "fire" not in record.load(cfg)


def test_finish_clears_decision_after_a_run(cfg, fake, capsys):
    seed(cfg, {7: {"status": "escalated", "decision": "use the author's view"}})
    entry = finish_state(cfg, fake, capsys, 7, "escalated", head="h9")[7]
    assert "decision" not in entry
    assert queue(cfg, fake, capsys, gql_response(7, updated=NEWEST, head="h9"))["process"] == []
    assert cli.main(["decide", "fmha", "7", "second decision"]) == 0
    assert queue(cfg, fake, capsys, gql_response(7, updated=NEWEST, head="h9"))["process"] == [7]


def test_finish_no_action_after_decision_clears_decision(cfg, fake, capsys):
    seed(cfg, {7: {"status": "escalated", "decision": "use the author's view"}})
    entry = finish_state(cfg, fake, capsys, 7, "no-action")[7]
    assert entry["status"] == "escalated" and "decision" not in entry


def test_finish_no_action_ends_stall(cfg, fake, capsys):
    seed(cfg, {7: {"status": "stalled", "stalled_from": "reviewed", "tab_id": "t1"}})
    entry = finish_state(cfg, fake, capsys, 7, "no-action")[7]
    assert entry["status"] == "reviewed" and "stalled_from" not in entry


def test_push_during_run_is_queued_next_fire(cfg, fake, capsys):
    seed(cfg, {7: {"status": "new"}})
    finish_state(cfg, fake, capsys, 7, "reviewed", head="h1")
    assert queue(cfg, fake, capsys, gql_response(7, updated=NEWEST, head="h9"))["process"] == [7]


def test_own_comments_after_review_are_not_activity(cfg, fake, capsys):
    seed(cfg, {7: {"status": "new"}})
    fake({"gh": [{"match": ["pr", "view", "7"],
                  "stdout": json.dumps({"updatedAt": NEWEST, "headRefOid": "h1"})}]})
    assert run(capsys, "finish", "fmha", "7", "reviewed", "--head", "h1", "--dry-run", "false")[0] == 0
    ours = gql_response(7, updated=NEWEST, head="h1", thread_comments=[("me", "User", NEWER)])
    assert queue(cfg, fake, capsys, ours)["process"] == []
