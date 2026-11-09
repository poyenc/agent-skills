"""Branch lifecycle of the local PR branches `pr-review/<N>`, and PR state.

`--checkout` is a worktree dedicated to pr-review, so leftovers from a previous run are
discarded without asking. Every git call is `git -C <checkout>`, and only after
`_worktree` confirmed the path is the root of a git worktree whose `origin` is the
requested repository: `reset --hard` and `clean -fdx` must never reach a repository the
user did not point us at. Only branches
named exactly `pr-review/<N>` (N decimal digits) are ever deleted.
"""
import json
import re
import sys
from pathlib import Path

from . import config, proc, state

BRANCH_RE = re.compile(r"pr-review/([1-9][0-9]*)")
FINISHED_STATES = ("MERGED", "CLOSED")


class CheckoutError(Exception):
    """The --checkout path is not the root of a git worktree."""


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise ValueError(text)
    return value


def _branch(pr: int) -> str:
    return f"pr-review/{pr}"


def origin_names_repo(url: str, repo: str) -> bool:
    """True when the remote URL is GitHub's https, scp-style or ssh URL of `repo`
    (`owner/name`, any case, optional `.git` and trailing slash), or a local path ending
    in `<owner>/<name>[.git]`."""
    pattern = (r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/|/(?:.*/)?)"
               + re.escape(repo) + r"(?:\.git)?/?")
    return re.fullmatch(pattern, url.strip(), re.IGNORECASE) is not None


def _worktree(path: str, repo: str) -> str:
    """The checkout path, verified to be a git worktree root whose origin is `repo`."""
    root = proc.run(["git", "-C", path, "rev-parse", "--show-toplevel"]).stdout.strip()
    if Path(root).resolve() != Path(path).resolve():
        raise CheckoutError(f"{path} is not the root of a git worktree (root: {root})")
    result = _git(path, "remote", "get-url", "origin", check=False)
    if result.returncode != 0:
        raise CheckoutError(f"{path} has no origin remote; expected the origin of {repo}")
    url = result.stdout.strip()
    if not origin_names_repo(url, repo):
        raise CheckoutError(f"{path} has origin {url}, not {repo}; refusing to touch it")
    return path


def _git(path: str, *args: str, check: bool = True):
    return proc.run(["git", "-C", path, *args], check=check)


def _has_branch(path: str, branch: str) -> bool:
    return _git(path, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False).returncode == 0


def _delete_branch(path: str, branch: str) -> bool:
    """Detach when `branch` is current, then delete it; False when it does not exist."""
    if not _has_branch(path, branch):
        return False
    if _git(path, "symbolic-ref", "--short", "-q", "HEAD", check=False).stdout.strip() == branch:
        _git(path, "checkout", "--detach")
    _git(path, "branch", "-D", branch)
    return True


def pr_state(repo: str, pr: int) -> dict:
    info = proc.gh_json("pr", "view", str(pr), "--repo", repo, "--json", "state,headRefOid,author")
    login = proc.run(["gh", "api", "user", "--jq", ".login"]).stdout.strip()
    author = (info.get("author") or {}).get("login", "")
    return {"state": info["state"], "head": info["headRefOid"], "author": author,
            "is_own": bool(author) and author == login}


def _checkout(args) -> int:
    config.load(args.repo)
    path = _worktree(args.checkout, args.repo)
    branch = _branch(args.pr)
    # Detach first: fetch refuses to update a branch checked out in any worktree of the
    # clone. The PR is checked out detached too, so no worktree ever holds pr-review/<N>
    # and a sibling worktree of the same clone can fetch, check out or delete it.
    _git(path, "checkout", "--detach")
    _git(path, "reset", "--hard")
    _git(path, "clean", "-fdx")
    _git(path, "fetch", "origin", f"+pull/{args.pr}/head:{branch}")
    _git(path, "checkout", "--detach", branch)
    print(_git(path, "rev-parse", "HEAD").stdout.strip())
    return 0


def _drop_branch(args) -> int:
    config.load(args.repo)
    _delete_branch(_worktree(args.checkout, args.repo), _branch(args.pr))
    return 0


def _is_approved(cfg: dict, repo: str, pr: int) -> bool:
    status = state.review_state(cfg, repo, pr)["status"]
    return bool(status) and status.split()[0].lower() == "approved"


def _cleanup(args) -> int:
    cfg = config.load(args.repo)
    path = _worktree(args.checkout, args.repo)
    names = _git(path, "for-each-ref", "--format=%(refname:short)", "refs/heads/pr-review/").stdout.split()
    deleted, failed = [], False
    for name in names:
        match = BRANCH_RE.fullmatch(name)
        if not match:
            continue
        pr = int(match[1])
        try:
            finished = _is_approved(cfg, args.repo, pr) or pr_state(args.repo, pr)["state"] in FINISHED_STATES
            if finished and _delete_branch(path, name):
                deleted.append(pr)
        except (proc.CommandError, KeyError, ValueError) as e:
            print(f"pr-review: keeping {name}: {e}", file=sys.stderr)
            failed = True
    print(json.dumps(sorted(deleted)))
    return 1 if failed else 0


def _pr_state(args) -> int:
    config.load(args.repo)
    print(json.dumps(pr_state(args.repo, args.pr)))
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("pr-state", help="print a PR's state, head, author and is_own as JSON")
    p.add_argument("repo")
    p.add_argument("pr", type=positive_int)
    p.set_defaults(func=_pr_state)

    p = subparsers.add_parser("checkout", help="fetch PR <pr> into pr-review/<pr>, check it out detached; prints head SHA")
    p.add_argument("repo")
    p.add_argument("pr", type=positive_int)
    p.add_argument("--checkout", required=True, help="the dedicated worktree to prepare")
    p.set_defaults(func=_checkout)

    p = subparsers.add_parser("drop-branch", help="delete the local pr-review/<pr> branch if present")
    p.add_argument("repo")
    p.add_argument("pr", type=positive_int)
    p.add_argument("--checkout", required=True)
    p.set_defaults(func=_drop_branch)

    p = subparsers.add_parser("cleanup", help="delete pr-review/<N> branches of merged, closed or approved PRs")
    p.add_argument("repo")
    p.add_argument("--checkout", required=True)
    p.set_defaults(func=_cleanup)
