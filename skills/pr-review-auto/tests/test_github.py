"""Tests for `pr-review-auto gh <owner/repo> <pr> <action>`.

Fake `gh` matching scheme (prefix match, first wins):
- `gh api user ...`        -> ["api", "user"]
- `gh pr view <N> ...`     -> ["pr", "view", "<N>"]
- thread/metadata query    -> ["api", "graphql", "-F", "number=<N>"] (production puts it first)
- REST writes              -> ["api", "-X", "POST", "repos/o/r/pulls/7/reviews"] etc.
- PR state lookup (live)   -> ["api", "repos/o/r/pulls/7", "--jq"]
"""
import io
import json

import pytest

from prreview import cli, config, github, state

PR = 7
REPO = "o/r"
HEAD = "abc123"
HEADER = "[Automated review by me's review agent]\n\n"
REVIEWS_URL = f"repos/o/r/pulls/{PR}/reviews"
COMMENTS_URL = f"repos/o/r/pulls/{PR}/comments"
ISSUE_URL = f"repos/o/r/issues/{PR}/comments"
STATE_LOOKUP = ["api", f"repos/o/r/pulls/{PR}", "--jq"]


def comment_node(db_id, review_id, body="b", author="me"):
    return {"databaseId": db_id, "author": {"login": author}, "body": body,
            "createdAt": "2026-11-01T00:00:00Z", "pullRequestReview": {"databaseId": review_id},
            "url": f"https://github.com/o/r/pull/{PR}#discussion_r{db_id}"}


def threads_response(*threads):
    nodes = [{"id": tid, "isResolved": False, "isOutdated": False, "path": "a.py", "line": 3,
              "comments": {"nodes": comments}} for tid, comments in threads]
    return json.dumps({"data": {"repository": {"pullRequest": {
        "reviewThreads": {"nodes": nodes},
        "comments": {"nodes": [{"author": {"login": "bob"}, "body": "hi",
                                "createdAt": "2026-11-01T00:00:00Z"}]},
        "reviews": {"nodes": [{"author": {"login": "bob"}, "body": "rv", "state": "COMMENTED",
                               "submittedAt": "2026-11-01T00:00:00Z"}]},
    }}}})


def base_responses(pr_author="alice", threads=None, pr_state="OPEN", **extra):
    gh = [
        {"match": ["api", "user"], "stdout": "me\n"},
        {"match": STATE_LOOKUP, "stdout": f"{pr_state}\n"},
        {"match": ["pr", "view", str(PR)],
         "stdout": json.dumps({"headRefOid": HEAD, "author": {"login": pr_author}})},
        {"match": ["api", "graphql", "-F", f"number={PR}"],
         "stdout": threads or threads_response()},
        {"match": ["api", "-X", "POST", REVIEWS_URL], "stdout": json.dumps({"id": 900})},
        {"match": ["api", "-X", "POST", COMMENTS_URL], "stdout": json.dumps({"id": 901})},
    ]
    return {"gh": gh, **extra}


@pytest.fixture
def live(write_config):
    write_config(dry_run=False)
    return config.load(REPO)


@pytest.fixture
def dry(write_config):
    write_config(dry_run=True)
    return config.load(REPO)


def run(capsys, monkeypatch, *argv, stdin=""):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    code = cli.main(["gh", REPO, str(PR), *argv])
    return code, capsys.readouterr().out


LINE = {"path": "a.py", "line": 3, "side": "RIGHT", "body": "bug one"}
LINE2 = {"path": "b.py", "line": 9, "side": "RIGHT", "body": "bug two"}
FILE = {"path": "c.py", "subject_type": "file", "body": "file note"}


def post_stdin(*comments):
    return json.dumps({"comments": list(comments)})


def writes(calls):
    return [a for a in calls.of("gh") if github.is_write(a)]


def payloads(calls):
    """JSON payloads sent on stdin (`--input -`), in call order."""
    return [json.loads(c["stdin"]) for c in calls.all if "stdin" in c]


# --- post-review -------------------------------------------------------------

def test_post_review_one_review_event_comment(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    code, out = run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, LINE2))
    assert code == 0
    reviews = [a for a in calls.of("gh") if REVIEWS_URL in a]
    assert len(reviews) == 1 and reviews[0][:3] == ["api", "-X", "POST"]
    assert "--input" in reviews[0]
    payload = payloads(calls)[-1]
    assert payload["event"] == "COMMENT" and payload["body"] == ""
    assert payload["commit_id"] == HEAD
    assert len(payload["comments"]) == 2
    assert all(c["body"].startswith(HEADER) for c in payload["comments"])
    assert [(c["path"], c["line"], c["side"]) for c in payload["comments"]] == [
        ("a.py", 3, "RIGHT"), ("b.py", 9, "RIGHT")]
    assert [a for a in calls.of("gh") if COMMENTS_URL in a] == []


def test_post_review_file_level_separate(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    code, _ = run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(FILE))
    assert code == 0
    posts = [a for a in calls.of("gh") if COMMENTS_URL in a]
    assert len(posts) == 1 and posts[0][:3] == ["api", "-X", "POST"]
    # only a file-level comment: no (empty) review is created
    assert [a for a in calls.of("gh") if REVIEWS_URL in a] == []
    payload = payloads(calls)[-1]
    assert payload["subject_type"] == "file" and payload["commit_id"] == HEAD
    assert payload["path"] == "c.py" and payload["body"] == HEADER + "file note"


def test_post_review_line_and_file_levels(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, FILE))
    urls = [a[3] for a in calls.of("gh") if github.is_write(a)]
    assert urls == [REVIEWS_URL, COMMENTS_URL]


def test_post_review_prints_created_thread_ids(live, fake, capsys, monkeypatch):
    threads = threads_response(
        ("T_old", [comment_node(1, 100)]),
        ("T_line", [comment_node(2, 900), comment_node(3, 5)]),
        ("T_file", [comment_node(901, 901)]),
        ("T_reply_only", [comment_node(4, 100), comment_node(5, 900)]),  # not first comment
    )
    fake(base_responses(threads=threads))
    code, out = run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, FILE))
    assert code == 0
    assert json.loads(out) == {"thread_ids": ["T_line", "T_file"]}


def test_post_review_file_comment_fails_after_review_posted(live, fake, capsys, monkeypatch):
    responses = base_responses(threads=threads_response(("T_line", [comment_node(2, 900)])))
    responses["gh"].insert(0, {"match": ["api", "-X", "POST", COMMENTS_URL], "exit": 1})
    fake(responses)
    code, out = run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, FILE))
    assert code == 1
    report = json.loads(out)
    assert report["review_id"] == 900 and report["comment_ids"] == []
    assert report["thread_ids"] == ["T_line"]
    assert "exited 1" in report["error"]


def test_post_review_thread_refetch_fails_after_writes(live, fake, capsys, monkeypatch):
    responses = base_responses()
    responses["gh"].insert(0, {"match": ["api", "graphql", "-F", f"number={PR}"], "exit": 1})
    calls = fake(responses)
    code, out = run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, FILE))
    assert code == 1
    report = json.loads(out)
    assert report["review_id"] == 900 and report["comment_ids"] == [901]
    assert report["thread_ids"] is None and "exited 1" in report["error"]
    assert len(writes(calls)) == 2


def test_post_review_first_write_fails_keeps_plain_error(live, fake, capsys, monkeypatch):
    responses = base_responses()
    responses["gh"].insert(0, {"match": ["api", "-X", "POST", REVIEWS_URL], "exit": 1})
    fake(responses)
    code, out = run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, FILE))
    assert code == 1 and out == ""


@pytest.mark.parametrize("stdin", [
    "not json", "{}", post_stdin(), post_stdin({"path": "a.py", "body": "x"}),
    post_stdin({"path": "a.py", "line": 1, "body": ""}),
])
def test_post_review_invalid_input_writes_nothing(live, fake, capsys, monkeypatch, stdin):
    calls = fake(base_responses())
    code, _ = run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=stdin)
    assert code == 1
    assert writes(calls) == []


# --- other write actions -----------------------------------------------------

def test_comment_posts_issue_comment_with_header(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    code, _ = run(capsys, monkeypatch, "comment", stdin="non-blocking\n- one\n")
    assert code == 0
    (w,) = writes(calls)
    assert w[:4] == ["api", "-X", "POST", ISSUE_URL] and "--input" in w
    assert payloads(calls)[-1] == {"body": HEADER + "non-blocking\n- one"}


def test_reply_uses_graphql_with_header(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    code, _ = run(capsys, monkeypatch, "reply", "T_1", stdin="still open")
    assert code == 0
    (w,) = writes(calls)
    assert w[:2] == ["api", "graphql"]
    assert "thread=T_1" in w and f"body={HEADER}still open" in w
    query = next(a for a in w if a.startswith("query="))
    assert query.split("=", 1)[1].lstrip().startswith("mutation")
    assert "addPullRequestReviewThreadReply" in query
    assert not any(a == "-F" for a in w)


@pytest.mark.parametrize("action,mutation", [("resolve", "resolveReviewThread"),
                                              ("unresolve", "unresolveReviewThread")])
def test_resolve_unresolve(live, fake, capsys, monkeypatch, action, mutation):
    calls = fake(base_responses())
    code, _ = run(capsys, monkeypatch, action, "T_1")
    assert code == 0
    (w,) = writes(calls)
    query = next(a for a in w if a.startswith("query="))
    assert mutation in query and "thread=T_1" in w


@pytest.mark.parametrize("action", ["reply", "resolve", "unresolve"])
def test_thread_actions_need_thread_id(live, fake, capsys, monkeypatch, action):
    calls = fake(base_responses())
    code, _ = run(capsys, monkeypatch, action, stdin="x")
    assert code == 1 and writes(calls) == []


def test_approve_runs_gh_pr_review_empty_body(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    code, _ = run(capsys, monkeypatch, "approve", "--commit", HEAD)
    assert code == 0
    assert writes(calls) == [["pr", "review", str(PR), "--repo", "o/r", "--approve", "--body", ""]]


@pytest.mark.parametrize("dry_run", [False, True])
def test_approve_own_pr_skipped(write_config, fake, capsys, monkeypatch, dry_run):
    write_config(dry_run=dry_run)
    calls = fake(base_responses(pr_author="me"))
    code, out = run(capsys, monkeypatch, "approve", "--commit", HEAD)
    assert code == 0 and json.loads(out) == {"skipped": "own-pr"}
    assert writes(calls) == []
    assert not state.notes_path(config.load(REPO), REPO, PR).exists()


def test_header_not_doubled(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    already = HEADER + "text"
    run(capsys, monkeypatch, "comment", stdin=already)
    assert payloads(calls)[-1]["body"] == already
    run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin({**LINE, "body": already}))
    assert payloads(calls)[-1]["comments"][0]["body"] == already


def test_login_read_once_per_command(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, LINE2, FILE))
    assert calls.of("gh").count(["api", "user", "--jq", ".login"]) == 1


def test_never_request_changes(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, FILE))
    run(capsys, monkeypatch, "comment", stdin="x")
    run(capsys, monkeypatch, "reply", "T_1", stdin="x")
    run(capsys, monkeypatch, "resolve", "T_1")
    run(capsys, monkeypatch, "unresolve", "T_1")
    run(capsys, monkeypatch, "approve", "--commit", HEAD)
    assert calls.of("gh")
    assert not any("REQUEST_CHANGES" in a for argv in calls.of("gh") for a in argv)
    sent = payloads(calls)
    assert sent and not any("REQUEST_CHANGES" in json.dumps(p) for p in sent)


# --- threads -----------------------------------------------------------------

def test_threads_output_and_reads_in_dry_run(dry, fake, capsys, monkeypatch):
    threads = threads_response(("T_1", [comment_node(1, 100, body="hello"),
                                        comment_node(2, 101, body="reply", author="bob")]),
                               ("T_empty", []))
    calls = fake(base_responses(threads=threads))
    code, out = run(capsys, monkeypatch, "threads")
    assert code == 0
    data = json.loads(out)
    assert data["threads"] == [{
        "id": "T_1", "isResolved": False, "isOutdated": False, "path": "a.py", "line": 3,
        "url": f"https://github.com/o/r/pull/{PR}#discussion_r1",
        "comments": [{"author": "me", "body": "hello", "createdAt": "2026-11-01T00:00:00Z"},
                     {"author": "bob", "body": "reply", "createdAt": "2026-11-01T00:00:00Z"}]},
        {"id": "T_empty", "isResolved": False, "isOutdated": False, "path": "a.py", "line": 3,
         "url": None, "comments": []}]
    assert [c["body"] for c in data["issue_comments"]] == ["hi"]
    assert [r["body"] for r in data["reviews"]] == ["rv"]
    assert calls.of("gh")


# --- dry run -----------------------------------------------------------------

def test_dry_run_makes_no_writes(dry, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    outs = [
        run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, FILE)),
        run(capsys, monkeypatch, "comment", stdin="note"),
        run(capsys, monkeypatch, "reply", "T_1", stdin="r"),
        run(capsys, monkeypatch, "resolve", "T_1"),
        run(capsys, monkeypatch, "approve", "--commit", HEAD),
    ]
    assert all(code == 0 and json.loads(out) == {"dry_run": True} for code, out in outs)
    assert calls.of("gh")
    for argv in calls.of("gh"):
        assert argv[:2] in (["api", "user"], ["pr", "view"]) or (
            argv[:2] == ["api", "graphql"] and not github.is_write(argv))
    assert writes(calls) == []
    text = state.notes_path(dry, REPO, PR).read_text()
    assert text.count("## Dry run actions") == 1
    blocks = [json.loads(b.split("```", 1)[0]) for b in text.split("```json\n")[1:]]
    assert [b["action"] for b in blocks] == ["post-review", "comment", "reply", "resolve", "approve"]
    assert blocks[0]["target"] == "o/r#7"
    assert [c["body"] for c in blocks[0]["body"]] == [HEADER + "bug one", HEADER + "file note"]
    assert blocks[1]["body"] == HEADER + "note"
    assert blocks[2]["target"] == "o/r#7 thread T_1" and blocks[2]["body"] == HEADER + "r"
    assert blocks[4]["body"] == ""


# --- the choke point ---------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["api", "-X", "POST", "repos/o/r/issues/1/comments"],
    ["api", "--method", "PATCH", "repos/o/r/pulls/1"],
    ["api", "-XDELETE", "repos/o/r/pulls/comments/1"],
    ["api", "-X", "put", "x"],
    ["api", "repos/o/r/pulls/1/reviews", "--input", "-"],
    ["api", "repos/o/r/issues/1/comments", "-f", "body=x"],
    ["api", "graphql", "-f", "query=mutation { x }"],
    ["api", "graphql", "-f", "query=  \n mutation($a: ID!) { x }"],
    ["api", "graphql", "-F", "number=1"],  # no query visible: fail closed
    ["pr", "review", "1", "--approve"],
    ["pr", "comment", "1", "--body", "x"],
    ["pr", "merge", "1"],
])
def test_is_write_true(argv):
    assert github.is_write(argv)


@pytest.mark.parametrize("argv", [
    ["api", "user", "--jq", ".login"],
    ["api", "-X", "GET", "repos/o/r/pulls/1"],
    ["api", "repos/o/r/pulls/1"],
    ["api", "graphql", "-F", "number=1", "-f", "owner=o", "-f", "query=query { x }"],
    ["api", "graphql", "-f", "query=\nquery($a: Int) { mutationCount }"],
    ["pr", "view", "1", "--json", "files"],
    ["pr", "list", "--repo", "o/r"],
])
def test_is_write_false(argv):
    assert not github.is_write(argv)


def test_choke_point_refuses_writes_in_dry_run(dry, fake):
    calls = fake(base_responses())
    for argv in (["api", "-X", "POST", "repos/o/r/issues/1/comments"],
                 ["api", "graphql", "-f", "query=mutation { x }"],
                 ["pr", "review", "1", "--approve"]):
        with pytest.raises(github.DryRunViolation):
            github.gh(dry, *argv, input="{}")
    assert calls.of("gh") == []
    github.gh(dry, "api", "user", "--jq", ".login")
    assert calls.of("gh") == [["api", "user", "--jq", ".login"]]


def test_choke_point_fails_closed_without_dry_run_key(fake):
    calls = fake()
    with pytest.raises(github.DryRunViolation):
        github.gh({}, "pr", "review", "1", "--approve")
    assert calls.of("gh") == []


# --- reviewed commit ---------------------------------------------------------

REVIEWED = "def456"  # the commit the team reviewed; GitHub's head (HEAD) has moved on


def test_post_review_anchors_on_reviewed_commit(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    code, _ = run(capsys, monkeypatch, "post-review", "--commit", REVIEWED,
                  stdin=post_stdin(LINE, FILE))
    assert code == 0
    assert [p["commit_id"] for p in payloads(calls)] == [REVIEWED, REVIEWED]
    assert not [a for a in calls.of("gh") if a[:2] == ["pr", "view"]]


@pytest.mark.parametrize("action", ["post-review", "approve"])
def test_commit_required(live, fake, capsys, monkeypatch, action):
    calls = fake(base_responses())
    monkeypatch.setattr("sys.stdin", io.StringIO(post_stdin(LINE)))
    assert cli.main(["gh", REPO, str(PR), action]) == 1
    assert writes(calls) == []
    assert "--commit" in capsys.readouterr().err


@pytest.mark.parametrize("dry_run", [False, True])
def test_approve_skips_when_head_moved(write_config, fake, capsys, monkeypatch, dry_run):
    write_config(dry_run=dry_run)
    calls = fake(base_responses())
    code, out = run(capsys, monkeypatch, "approve", "--commit", REVIEWED)
    assert code == 0 and json.loads(out) == {"skipped": "head-moved"}
    assert writes(calls) == []
    assert not state.notes_path(config.load(REPO), REPO, PR).exists()


# --- never write to a non-open PR ----------------------------------------------

def lookups(calls):
    return [a for a in calls.of("gh") if a[:3] == STATE_LOOKUP]


def recorded(cfg):
    text = state.notes_path(cfg, REPO, PR).read_text()
    return [json.loads(b.split("```", 1)[0]) for b in text.split("```json\n")[1:]]


@pytest.mark.parametrize("pr_state", ["MERGED", "CLOSED"])
def test_live_writes_to_finished_pr_are_recorded_not_posted(live, fake, capsys, monkeypatch, pr_state):
    calls = fake(base_responses(pr_state=pr_state))
    outs = [
        run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, FILE)),
        run(capsys, monkeypatch, "comment", stdin="note"),
        run(capsys, monkeypatch, "reply", "T_1", stdin="r"),
        run(capsys, monkeypatch, "resolve", "T_1"),
        run(capsys, monkeypatch, "approve", "--commit", HEAD),
    ]
    reason = f"PR is {pr_state}"
    assert all(code == 0 and json.loads(out) == {"dry_run": True, "not_posted": reason}
               for code, out in outs)
    assert writes(calls) == []
    blocks = recorded(live)  # the live notes, not the dry-run directory
    assert [b["action"] for b in blocks] == ["post-review", "comment", "reply", "resolve", "approve"]
    assert all(b["not_posted"] == reason for b in blocks)
    assert [c["body"] for c in blocks[0]["body"]] == [HEADER + "bug one", HEADER + "file note"]


def test_live_writes_to_open_pr_go_through_after_one_lookup(live, fake, capsys, monkeypatch):
    calls = fake(base_responses())
    code, _ = run(capsys, monkeypatch, "post-review", "--commit", HEAD, stdin=post_stdin(LINE, FILE))
    assert code == 0
    assert len(writes(calls)) == 2 and len(lookups(calls)) == 1
    assert calls.of("gh").index(lookups(calls)[0]) < calls.of("gh").index(writes(calls)[0])
    assert not state.notes_path(live, REPO, PR).exists()


def test_state_lookup_failure_fails_closed(live, fake, capsys, monkeypatch):
    responses = base_responses()
    responses["gh"].insert(0, {"match": STATE_LOOKUP, "exit": 1})
    calls = fake(responses)
    code, out = run(capsys, monkeypatch, "comment", stdin="note")
    assert code == 0 and json.loads(out)["not_posted"] == "PR state lookup failed"
    assert writes(calls) == []
    assert recorded(live)[0]["body"] == HEADER + "note"


def test_dry_run_does_not_look_up_state(dry, fake, capsys, monkeypatch):
    calls = fake(base_responses(pr_state="MERGED"))
    code, out = run(capsys, monkeypatch, "comment", stdin="note")
    assert code == 0 and json.loads(out) == {"dry_run": True}
    assert lookups(calls) == [] and "not_posted" not in recorded(dry)[0]


def test_choke_point_refuses_live_write_to_finished_pr(live, fake):
    calls = fake(base_responses(pr_state="MERGED"))
    with pytest.raises(github.DryRunViolation):
        github.gh({**live, "target": (REPO, PR)}, "api", "-X", "POST", ISSUE_URL, input="{}")
    with pytest.raises(github.DryRunViolation):  # no PR to check: fail closed
        github.gh(live, "pr", "review", str(PR), "--approve")
    assert writes(calls) == []
