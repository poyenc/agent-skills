---
name: deep-review
description: >
  Use when the user wants a thorough code review of a PR or local branch changes.
  Goes beyond diff-based review by reading all touched files and related code.
  Supports three modes: summary (quick overview), walkthrough (file-by-file
  explanation for onboarding), and review (3+1 subagent issue-hunting pipeline).
  Trigger on: "deep review", "thorough review", "review PR thoroughly",
  "explain this PR", "walk me through this PR", "what does this PR do",
  "find issues in PR", or "/deep-review".
---

# Deep Review

Thorough code review that reads full files, spawns scoped subagents for issue discovery, and produces inline comment drafts with fix suggestions.

## Argument Parsing

Parse the skill arguments to extract:
- `PR_NUMBER`: numeric PR number (optional — if absent, review local branch diff)
- `--summary`: brief summary mode
- `--walkthrough`: annotated file-by-file explanation mode
- `--review`: full 3+1 pass issue hunting mode

If no mode flag is given, ask the user via AskUserQuestion:
- Summary — quick overview of what changed
- Walkthrough — file-by-file explanation for studying the code
- Review — full issue-hunting with subagent passes

## Step 1: Gather Context

### PR Mode (PR number provided)

Run these in parallel via Bash:

1. Fetch PR metadata:
   ```bash
   gh pr view {PR_NUMBER} --json title,body,author,baseRefName,headRefName,files,additions,deletions,changedFiles
   ```

2. Save the diff:
   ```bash
   gh pr diff {PR_NUMBER} > /tmp/deep-review-diff.txt
   ```

Store: `PR_TITLE`, `PR_BODY`, `CHANGED_FILES` (list of file paths), `BASE_BRANCH`, `HEAD_BRANCH`, `REPO_OWNER`, `REPO_NAME`.

Detect `REPO_OWNER` and `REPO_NAME` from `gh pr view --json url`.

### Local Mode (no PR number)

1. Detect base branch:
   ```bash
   BASE=$(git merge-base HEAD $(git rev-parse --abbrev-ref @{upstream} 2>/dev/null || echo develop))
   ```

2. Get changed files and diff:
   ```bash
   git diff --name-only $BASE..HEAD
   git diff $BASE..HEAD > /tmp/deep-review-diff.txt
   ```

Store the same variables. `PR_TITLE` = current branch name, `PR_BODY` = empty.
