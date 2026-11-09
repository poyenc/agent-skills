import json
import subprocess
from pathlib import Path

import pytest

from prreview import cli, gitops

REPO = "o/r"
GIT_ENV = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *GIT_ENV, "-C", str(repo), *args],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def commit(repo: Path, name: str, text: str) -> str:
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-m", text)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def origin(tmp_path) -> Path:
    """Bare origin with main and refs/pull/7/head; a clone sits at tmp_path/checkout.

    The origin path ends in `<owner>/<repo>.git` (REPO), so the checkout's origin names REPO."""
    bare = tmp_path / REPO.split("/")[0] / (REPO.split("/")[1] + ".git")
    bare.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    commit(seed, "base.txt", "base")
    git(seed, "remote", "add", "origin", str(bare))
    git(seed, "push", "-q", "origin", "main")
    pr_head = commit(seed, "pr.txt", "pr")
    git(seed, "push", "-q", "origin", f"{pr_head}:refs/pull/7/head")
    subprocess.run(["git", "clone", "-q", str(bare), str(tmp_path / "checkout")], check=True)
    return bare


def set_pr_head(tmp_path: Path, origin: Path, text: str) -> str:
    """Point origin's refs/pull/7/head at a new commit unrelated to the old one."""
    other = tmp_path / f"other-{text}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(other)], check=True)
    sha = commit(other, "x.txt", text)
    git(other, "push", "-q", "-f", str(origin), f"{sha}:refs/pull/7/head")
    return sha


def checkout_args(tmp_path: Path) -> list[str]:
    return ["--checkout", str(tmp_path / "checkout")]


def branches(checkout: Path) -> list[str]:
    return sorted(git(checkout, "branch", "--format=%(refname:short)").split())


def pr_view(state: str, head: str = "h" * 40, author: str = "someone", number: str = "") -> dict:
    return {"match": ["pr", "view", *([number] if number else [])], "stdout": json.dumps(
        {"state": state, "headRefOid": head, "author": {"login": author}})}


def test_checkout_creates_branch(tmp_path, origin, write_config, capsys):
    write_config()
    checkout = tmp_path / "checkout"
    expected = git(origin, "rev-parse", "refs/pull/7/head")
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    assert git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"  # detached
    assert git(checkout, "rev-parse", "pr-review/7") == expected
    assert git(checkout, "rev-parse", "HEAD") == expected
    assert capsys.readouterr().out.strip() == expected


def test_sibling_worktree_can_reuse_the_pr_branch(tmp_path, origin, write_config, fake, capsys):
    """Linked worktrees share refs/heads: a checkout in one must not hold pr-review/<N>."""
    write_config()
    checkout = tmp_path / "checkout"
    sibling = tmp_path / "sibling"
    git(checkout, "worktree", "add", "-q", "--detach", str(sibling))
    sibling_args = ["--checkout", str(sibling)]
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    new_head = set_pr_head(tmp_path, origin, "forced")
    assert cli.main(["checkout", REPO, "7", *sibling_args]) == 0
    assert git(sibling, "rev-parse", "HEAD") == new_head
    assert cli.main(["drop-branch", REPO, "7", *sibling_args]) == 0
    assert git(checkout, "branch", "--list", "pr-review/*") == ""
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    fake({"gh": [pr_view("MERGED")]})
    capsys.readouterr()
    assert cli.main(["cleanup", REPO, *sibling_args]) == 0
    assert json.loads(capsys.readouterr().out) == [7]
    assert git(checkout, "branch", "--list", "pr-review/*") == ""


def test_checkout_force_pushed_current_branch(tmp_path, origin, write_config, capsys):
    write_config()
    checkout = tmp_path / "checkout"
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    new_head = set_pr_head(tmp_path, origin, "forced")
    capsys.readouterr()
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    assert git(checkout, "rev-parse", "HEAD") == new_head
    assert git(checkout, "rev-parse", "pr-review/7") == new_head
    assert capsys.readouterr().out.strip() == new_head


def test_checkout_discards_leftovers(tmp_path, origin, write_config):
    write_config()
    checkout = tmp_path / "checkout"
    (checkout / "base.txt").write_text("dirty")
    (checkout / "untracked.txt").write_text("junk")
    (checkout / ".git" / "info" / "exclude").write_text("ignored.bin\n")
    (checkout / "ignored.bin").write_text("junk")
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    assert git(checkout, "status", "--porcelain", "--ignored") == ""


def test_checkout_refuses_a_subdirectory_of_a_repository(tmp_path, origin, write_config, capsys):
    write_config()
    sub = tmp_path / "checkout" / "sub"
    sub.mkdir()
    (tmp_path / "checkout" / "base.txt").write_text("dirty")
    assert cli.main(["checkout", REPO, "7", "--checkout", str(sub)]) == 1
    assert "not the root of a git worktree" in capsys.readouterr().err
    assert (tmp_path / "checkout" / "base.txt").read_text() == "dirty"


def test_checkout_refuses_a_directory_outside_any_repository(tmp_path, write_config):
    write_config()
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "keep.txt").write_text("keep")
    assert cli.main(["checkout", REPO, "7", "--checkout", str(plain)]) == 1
    assert (plain / "keep.txt").read_text() == "keep"


@pytest.mark.parametrize("url", [
    "https://github.com/o/r", "https://github.com/o/r.git", "https://github.com/o/r/",
    "https://github.com/O/R.git", "git@github.com:o/r", "git@github.com:o/r.git",
    "git@github.com:O/r.git/", "ssh://git@github.com/o/r", "ssh://git@github.com/o/r.git",
    "ssh://git@github.com/o/R/", "/tmp/x/o/r.git", "/tmp/x/o/r",
])
def test_origin_names_repo_accepts(url):
    assert gitops.origin_names_repo(url, REPO)


@pytest.mark.parametrize("url", [
    "https://github.com/o/other", "https://github.com/x/r.git", "https://github.com/xo/r",
    "https://gitlab.com/o/r.git", "git@github.com:o/r2.git", "git@gitlab.com:o/r.git",
    "ssh://git@github.com/o/r/extra", "https://github.com/o/r.git.bak", "/tmp/xo/r.git",
    "/tmp/o/other.git", "", "o/r",
])
def test_origin_names_repo_rejects(url):
    assert not gitops.origin_names_repo(url, REPO)


def test_checkout_refuses_an_origin_of_another_repository(tmp_path, origin, write_config, capsys):
    write_config()
    checkout = tmp_path / "checkout"
    git(checkout, "remote", "set-url", "origin", "https://github.com/someone/else.git")
    head = git(checkout, "rev-parse", "HEAD")
    (checkout / "base.txt").write_text("dirty")
    (checkout / "untracked.txt").write_text("keep")
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert REPO in err and "https://github.com/someone/else.git" in err
    assert (checkout / "base.txt").read_text() == "dirty"
    assert (checkout / "untracked.txt").read_text() == "keep"
    assert git(checkout, "rev-parse", "HEAD") == head
    assert git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert branches(checkout) == ["main"]


def test_checkout_refuses_a_worktree_without_origin(tmp_path, origin, write_config, capsys):
    write_config()
    checkout = tmp_path / "checkout"
    git(checkout, "remote", "remove", "origin")
    (checkout / "base.txt").write_text("dirty")
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 1
    assert "no origin" in capsys.readouterr().err
    assert (checkout / "base.txt").read_text() == "dirty"
    assert branches(checkout) == ["main"]


def test_drop_branch_and_cleanup_refuse_an_origin_of_another_repository(tmp_path, origin,
                                                                        write_config):
    write_config()
    checkout = tmp_path / "checkout"
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    git(checkout, "remote", "set-url", "origin", "git@github.com:someone/else.git")
    assert cli.main(["drop-branch", REPO, "7", *checkout_args(tmp_path)]) == 1
    assert cli.main(["cleanup", REPO, *checkout_args(tmp_path)]) == 1
    assert "pr-review/7" in branches(checkout)


def test_checkout_requires_the_checkout_path(write_config):
    write_config()
    with pytest.raises(SystemExit):
        cli.main(["checkout", REPO, "7"])


def test_checkout_without_config_exits_3(tmp_path, origin):
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 3


@pytest.mark.parametrize("pr", ["0", "-1", "abc"])
def test_pr_number_must_be_positive_integer(write_config, pr):
    write_config()
    with pytest.raises(SystemExit):
        cli.main(["drop-branch", REPO, pr, "--checkout", "/nonexistent"])


def test_drop_branch_current_and_missing(tmp_path, origin, write_config):
    write_config()
    checkout = tmp_path / "checkout"
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    assert cli.main(["drop-branch", REPO, "7", *checkout_args(tmp_path)]) == 0  # detached
    assert git(checkout, "branch", "--list", "pr-review/*") == ""
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    git(checkout, "checkout", "-q", "pr-review/7")  # left current by an older version
    assert cli.main(["drop-branch", REPO, "7", *checkout_args(tmp_path)]) == 0
    assert git(checkout, "branch", "--list", "pr-review/*") == ""
    assert cli.main(["drop-branch", REPO, "8", *checkout_args(tmp_path)]) == 0


def test_drop_branch_leaves_head_when_not_the_target(tmp_path, origin, write_config):
    write_config()
    checkout = tmp_path / "checkout"
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    git(checkout, "checkout", "-q", "main")
    assert cli.main(["drop-branch", REPO, "7", *checkout_args(tmp_path)]) == 0
    assert git(checkout, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert git(checkout, "branch", "--list", "pr-review/*") == ""


def test_drop_branch_never_touches_other_branches(tmp_path, origin, write_config):
    write_config()
    checkout = tmp_path / "checkout"
    for name in ("feature/x", "pr-review/70", "pr-watch/7"):
        git(checkout, "branch", name)
    assert cli.main(["drop-branch", REPO, "7", *checkout_args(tmp_path)]) == 0
    assert branches(checkout) == ["feature/x", "main", "pr-review/70", "pr-watch/7"]


def test_cleanup_deletes_only_finished_pr_branches(tmp_path, origin, write_config, fake, capsys):
    write_config()
    checkout = tmp_path / "checkout"
    for name in ("pr-review/1", "pr-review/2", "pr-review/3", "feature/x"):
        git(checkout, "branch", name)
    notes = tmp_path / "home" / "o" / "r-dry-run" / "2" / "notes.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("## Review state\n\n- Status: approved\n")
    calls = fake({"gh": [pr_view("MERGED", number="1"), pr_view("OPEN", number="3")]})
    assert cli.main(["cleanup", REPO, *checkout_args(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == [1, 2]
    assert branches(checkout) == ["feature/x", "main", "pr-review/3"]
    assert not any(argv[2:3] == ["2"] for argv in calls.of("gh"))  # approved needs no gh call


def test_cleanup_closed_pr_and_detaches_current(tmp_path, origin, write_config, fake, capsys):
    write_config()
    checkout = tmp_path / "checkout"
    assert cli.main(["checkout", REPO, "7", *checkout_args(tmp_path)]) == 0
    fake({"gh": [pr_view("CLOSED")]})
    capsys.readouterr()
    assert cli.main(["cleanup", REPO, *checkout_args(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == [7]
    assert git(checkout, "branch", "--list", "pr-review/*") == ""


def test_cleanup_ignores_non_numeric_pr_review_branches(tmp_path, origin, write_config, fake, capsys):
    write_config()
    checkout = tmp_path / "checkout"
    for name in ("pr-review/abc", "pr-review/01x", "pr-review/-1"):
        git(checkout, "branch", name)
    fake({"gh": [pr_view("MERGED")]})
    assert cli.main(["cleanup", REPO, *checkout_args(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert branches(checkout) == ["main", "pr-review/-1", "pr-review/01x", "pr-review/abc"]


def test_cleanup_continues_past_an_undeletable_branch(tmp_path, origin, write_config, fake, capsys):
    write_config()
    checkout = tmp_path / "checkout"
    for name in ("pr-review/1", "pr-review/2"):
        git(checkout, "branch", name)
    git(checkout, "worktree", "add", "-q", str(tmp_path / "holder"), "pr-review/1")  # holds it
    fake({"gh": [pr_view("MERGED")]})
    assert cli.main(["cleanup", REPO, *checkout_args(tmp_path)]) == 1
    out, err = capsys.readouterr()
    assert json.loads(out) == [2]
    assert "keeping pr-review/1" in err
    assert branches(checkout) == ["main", "pr-review/1"]


def test_cleanup_keeps_branch_when_gh_fails(tmp_path, origin, write_config, fake, capsys):
    write_config()
    checkout = tmp_path / "checkout"
    git(checkout, "branch", "pr-review/4")
    fake({"gh": [{"match": ["pr", "view"], "exit": 1, "stderr": "boom"}]})
    assert cli.main(["cleanup", REPO, *checkout_args(tmp_path)]) == 1
    assert "pr-review/4" in branches(checkout)
    assert json.loads(capsys.readouterr().out) == []


def test_pr_state_is_own(write_config, fake, capsys):
    write_config()
    calls = fake({"gh": [pr_view("OPEN", head="abc123", author="me"),
                         {"match": ["api", "user"], "stdout": "me\n"}]})
    assert cli.main(["pr-state", REPO, "7"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "state": "OPEN", "head": "abc123", "author": "me", "is_own": True}
    assert calls.of("gh")[0][:5] == ["pr", "view", "7", "--repo", REPO]


def test_pr_state_other_author(write_config, fake, capsys):
    write_config()
    fake({"gh": [pr_view("MERGED", head="abc123", author="them"),
                 {"match": ["api", "user"], "stdout": "me\n"}]})
    assert cli.main(["pr-state", REPO, "7"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "MERGED" and out["is_own"] is False
