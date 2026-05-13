---
name: post-review
description: >
  Validate and post inline PR comments from a prior /review output.
  Spawns a subagent to verify each claim against actual code, drops
  wrong items, formats confirmed findings as inline comment drafts,
  and optionally posts them to GitHub. Works with both PR and local
  branch reviews. Trigger on: "post review", "post comments",
  "post inline comments", "format review as comments", or "/post-review".
---

# Post Review

Verify `/review` output, format as inline comment drafts, and optionally post to GitHub.

## Prerequisites

This skill expects `/review` output to already be present in the conversation. If not, tell the user to run `/review` or `/review <PR_NUMBER>` first.

## Argument Parsing

Parse the skill arguments to extract:
- `PR_NUMBER`: numeric PR number (optional — if absent, operate in local-branch mode)

## Step 1: Gather Context

**Create a unique temp directory:**
```bash
REVIEW_DIR=$(mktemp -d /tmp/post-review-XXXXXXXX)
```

### PR Mode (PR number provided)

Run in parallel:

1. Fetch PR metadata:
   ```bash
   gh pr view {PR_NUMBER} --json title,body,headRefName,headRefOid,url,files
   ```

2. Save the diff:
   ```bash
   gh pr diff {PR_NUMBER} > {REVIEW_DIR}/diff.txt
   ```

Store: `PR_TITLE`, `HEAD_COMMIT_SHA`, `CHANGED_FILES`, `REPO_OWNER`, `REPO_NAME` (from the url field).

### Local Mode (no PR number)

1. Detect base:
   ```bash
   BASE=$(git merge-base HEAD $(git rev-parse --abbrev-ref @{upstream} 2>/dev/null || echo develop))
   ```

2. Get diff:
   ```bash
   git diff $BASE..HEAD > {REVIEW_DIR}/diff.txt
   git diff --name-only $BASE..HEAD
   ```

Store: `PR_TITLE` = current branch name.

### Split diff into chunks

```bash
csplit -z -f {REVIEW_DIR}/chunk- {REVIEW_DIR}/diff.txt '/^diff --git/' '{*}'
```

Build a map of `{file_path: chunk_file}` from the first line of each chunk.

## Step 2: Extract Review Items

Scan the conversation for the `/review` output. Extract each finding as a structured item:
- File path and line number (if present)
- Issue description
- Severity (if present)
- Suggested fix (if present)

Collect these into a numbered list: `REVIEW_ITEMS`.

## Step 3: Validation Subagent

Spawn one subagent (general-purpose) to verify claims:

> You are validating code review findings against actual source code.
>
> **PR/Branch:** {PR_TITLE}
> **Changed files:** {CHANGED_FILES}
>
> **REVIEW FINDINGS TO VALIDATE:**
> {REVIEW_ITEMS}
>
> **READING STRATEGY:**
> 1. For each finding, read the cited file region (use offset/limit, ~50 lines around the reported line). Verify the claim against the actual code.
> 2. If a finding references interactions between files, read the relevant regions in both files.
> 3. Read the diff chunk for context on what changed. Diff chunks: {LIST_OF_CHUNK_FILES_WITH_CORRESPONDING_SOURCE_PATHS}
> 4. Budget: aim for ≤15 tool calls total.
>
> **YOUR TASK:**
> For each finding, give a verdict:
> - **Confirmed** — the issue is real and correctly described
> - **Wrong** — the claim is incorrect; explain why with evidence
> - **Overstated** — the issue exists but description is exaggerated; explain
>
> For confirmed/overstated items, provide:
> - Exact file:line in the current source
> - A concise inline comment (2-4 sentences) explaining the issue and showing a fix
> - Use the comment style below
>
> **COMMENT STYLE:**
> - Explain the *why*, show the *what*
> - For direct fixes, show a code snippet the author can copy-paste
> - For conceptual fixes, show before/after key statements
> - Keep it concise — no walls of text
>
> Report verdicts in order. For wrong items, briefly state why so the user knows.

## Step 4: Present Results

After the subagent returns:

1. **Drop** items marked "Wrong".
2. **Adjust** items marked "Overstated" per the validator's feedback.
3. **Keep** items marked "Confirmed" as-is.

### Summary Table

First show an overview of what changed and what was kept/dropped:

```
| # | Verdict | File:Line | Issue |
|---|---------|-----------|-------|
```

### Inline Comment Drafts

For each confirmed/overstated item, show the draft:

```
**#N** — on `file/path.hpp:123`:
​```cpp
the code line this comment attaches to
​```

> Comment text with fix suggestion
```

All inline comments use normal fenced code blocks. NEVER use GitHub `suggestion` blocks.

After presenting all drafts, ask in plain text (do NOT use AskUserQuestion):

"Want me to post these as inline comments to the PR? You can also ask me to edit or drop specific items."

Wait for the user to respond before proceeding.

## Step 5: Post to GitHub (if approved)

Only for PR mode. Only if user approved.

1. Compute the exact new-file line number for each comment by parsing diff hunks in `{REVIEW_DIR}/diff.txt`. For each item:
   - Find the hunk containing the target file and line
   - Count non-minus lines from the hunk start to determine the new-file line number

2. Compute GitHub diff anchors:
   ```bash
   echo -n "path/to/file.hpp" | sha256sum | cut -c1-64
   ```

3. Build the review JSON and save to `{REVIEW_DIR}/post.json`:

```json
{
  "commit_id": "{HEAD_COMMIT_SHA}",
  "event": "COMMENT",
  "body": "Code review — suggestions from `/review` validation.",
  "comments": [
    {
      "path": "path/to/file.hpp",
      "line": 123,
      "side": "RIGHT",
      "body": "Comment text with fenced code blocks"
    }
  ]
}
```

4. Post:
```bash
gh api repos/{REPO_OWNER}/{REPO_NAME}/pulls/{PR_NUMBER}/reviews --method POST --input {REVIEW_DIR}/post.json
```

5. Report the review URL to the user.
