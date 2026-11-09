"""pr-watch shares no code or files with pr-review, writes nothing to GitHub and runs no repository
git commands. Scans the pr-watch scripts, and the prompts, SKILL.md and examples."""
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
FORBIDDEN = ("prreview", "pr-review/", "notes.md", "gh api", "gh pr review", "git ")
# Only the scanner's read-only GitHub listing (gh pr list/view, the GraphQL activity query, the
# gh account's login) lives in scan.py; config.py's validate probes the repo and the checkout;
# proc.py is the subprocess wrapper.
READ_ONLY_FILES = {"scan.py", "config.py", "proc.py"}
GITHUB_OR_GIT_ARGV = re.compile(r'"(?:gh|git)"')
# The only mentions of pr-review allowed in the prompts, SKILL.md and examples: the lead's
# invocation prefix (`/pr-review`, `/skill:pr-review`, which also covers the user's one-time
# `/pr-review <owner>/<repo> <PR>`), and plain statements about "the `pr-review` skill".
ALLOWED_PR_REVIEW = re.compile(r"/(?:skill:)?pr-review\b(?!/)|`pr-review` skill")


def sources():
    return [p for p in SCRIPTS.rglob("*") if p.is_file() and "__pycache__" not in p.parts]


def docs():
    return ([SKILL_DIR / "SKILL.md"] + sorted((SKILL_DIR / "prompts").glob("*"))
            + sorted((SKILL_DIR / "examples").glob("*")))


def test_no_overlap():
    offenders = [(p.name, token) for p in sources() for token in FORBIDDEN
                 if token in p.read_text() and not (p.name == "scan.py" and token == "gh api")]
    assert offenders == []


def test_no_overlap_argv_calls_stay_in_read_only_modules():
    offenders = [p.name for p in sources()
                 if p.suffix == ".py" and p.name not in READ_ONLY_FILES
                 and GITHUB_OR_GIT_ARGV.search(p.read_text())]
    assert offenders == []


def test_no_github_writes():
    for path in sources():
        text = path.read_text()
        assert not re.search(r"\b(?:--method|-X)\s+(?:POST|PUT|PATCH|DELETE)\b", text), path
        assert "mutation" not in text, path


def test_docs_cover_prompts_skill_md_and_examples():
    names = {p.name for p in docs()}
    assert {"SKILL.md", "supervisor.md", "scanner.md", "configure.md", "fmha.yaml"} <= names


def test_no_overlap_in_docs():
    offenders = [(p.name, token) for p in docs() for token in FORBIDDEN if token in p.read_text()]
    assert offenders == []


def test_docs_mention_pr_review_only_as_allowed():
    offenders = []
    for path in docs():
        rest = ALLOWED_PR_REVIEW.sub("", " ".join(path.read_text().split()))
        offenders += [(path.name, rest[max(0, m.start() - 40):m.end() + 40])
                      for m in re.finditer("pr-review", rest)]
    assert offenders == []


def test_allowance_rejects_pr_review_commands_and_paths():
    for bad in ("run `pr-review validate o/r`", "pr-review cleanup o/r", "~/.claude/pr-review/o/r",
                "/pr-review/9187", "the pr-review config"):
        assert "pr-review" in ALLOWED_PR_REVIEW.sub("", bad), bad
    for good in ("`/pr-review o/r 1 --checkout p`", "`/skill:pr-review`",
                 "run `/pr-review <owner>/<repo> <PR>` once", "leads use the `pr-review` skill"):
        assert "pr-review" not in ALLOWED_PR_REVIEW.sub("", good), good
