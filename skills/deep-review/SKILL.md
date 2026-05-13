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

## Summary Mode

Read the diff at `/tmp/deep-review-diff.txt`. Produce:

1. **Overview** (2-3 paragraphs): What the PR does, why, and the approach taken.
2. **Changed files table**:

| File | Change |
|------|--------|
| `path/to/file.hpp` | One-line description of what changed |

No subagents. No issue hunting. Done after presenting.

## Walkthrough Mode

Spawn one subagent (general-purpose) with this prompt:

> You are explaining a code change to an engineer who is new to this codebase.
>
> **PR:** {PR_TITLE}
> **Description:** {PR_BODY}
> **Changed files:** {CHANGED_FILES}
> **Diff:** saved at /tmp/deep-review-diff.txt
>
> For each changed file:
> 1. Read the FULL file (not just the diff)
> 2. Explain what the file does in the project
> 3. Explain what changed and why
> 4. Explain how it connects to the other changed files
>
> Write as a senior engineer onboarding a new hire. Be thorough but not condescending.
> Structure your response file-by-file. Read /tmp/deep-review-diff.txt for the diff.

Present the subagent's output directly to the user. Done.

## Review Mode

### Step 2: Scoped Parallel Review

Spawn 3 subagents in parallel using the Agent tool. All three share the same prompt structure but differ in SCOPE.

**Shared prompt template:**

> You are reviewing PR "{PR_TITLE}" for **{SCOPE_NAME}** issues.
>
> **PR Description:** {PR_BODY}
> **Changed files:** {CHANGED_FILES}
> **Diff:** saved at /tmp/deep-review-diff.txt
>
> **READING MANDATE:**
> 1. Read ALL touched files end-to-end (not just the diff). File list: {CHANGED_FILES}
> 2. Discover and read related files as needed — follow imports/includes, grep for callers of changed functions, find construction sites for changed types.
> 3. Read the diff at /tmp/deep-review-diff.txt LAST — understand the codebase first, then the change.
>
> **SCOPE — {SCOPE_NAME}:**
> {SCOPE_DETAILS}
>
> **SELF-VALIDATION:**
> Before reporting any issue, verify your claim against the actual code. If you cannot point to a specific file:line, drop the claim. Do not fabricate issues.
>
> **OUTPUT FORMAT:** For each issue found, report:
> - **File:line** — exact location
> - **Issue** — 1-2 sentence description
> - **Confidence** — 0-100%
> - **Severity** — High / Medium / Low
> - **Fix** — concrete code snippet or description
>
> If you find no issues in your scope, say so explicitly. Do not fabricate issues to fill the list.

**Agent A — Correctness:**
SCOPE_DETAILS = "Race conditions, use-after-free, off-by-one errors, wrong buffer sizes, stream/thread ordering violations, data races, memory safety, null pointer dereferences, integer overflow."

**Agent B — Design & API:**
SCOPE_DETAILS = "Object lifetime management, error handling paths, API-breaking changes, missing abstractions, ownership semantics, exception safety, missing validation at system boundaries, inconsistent state after partial failure."

**Agent C — Performance & Resource:**
SCOPE_DETAILS = "Unnecessary copies or allocations, missed async/parallel opportunities, cache-unfriendly patterns, redundant computation, resource leaks, suboptimal data structures."

Launch all three in a single message with three Agent tool calls so they run concurrently.

### Step 3: Catch-All Validation

After all 3 scoped agents return, collect their findings into a combined list. Then spawn 1 validation subagent:

> You are independently reviewing PR "{PR_TITLE}" and validating findings from three prior reviewers.
>
> **PR Description:** {PR_BODY}
> **Changed files:** {CHANGED_FILES}
> **Diff:** saved at /tmp/deep-review-diff.txt
>
> **READING MANDATE:** (same as scoped agents — read ALL touched files, follow imports, read diff last)
>
> **PRIOR FINDINGS:**
> {COMBINED_ISSUE_LIST_FROM_ALL_3_AGENTS}
>
> **YOUR TASKS:**
> 1. Read all touched files yourself. Do NOT trust the prior reviewers — verify everything.
> 2. For each prior finding, give a verdict:
>    - **Confirmed** — the issue is real and correctly described
>    - **Wrong** — the claim is incorrect; explain why with evidence from the code
>    - **Overstated** — the issue exists but severity or description is exaggerated; explain
> 3. Find NEW issues the prior reviewers missed. Use the same output format (file:line, issue, confidence, severity, fix).
>
> Report your verdicts first, then any new issues.

### Step 4: Consolidation

After the validation agent returns:

1. **Apply verdicts:** Drop items marked "Wrong". For "Overstated" items, adjust the severity/description per the validator's feedback.
2. **Merge new issues:** Add any new issues the validator found to the list.
3. **Deduplicate:** If multiple agents reported the same issue (same file:line, same root cause), merge them into one item. Use the highest confidence and most detailed description.
4. **Sort:** By severity (High > Medium > Low), then by confidence (highest first).
5. **Number sequentially:** Starting from #1.

### Step 5: Present Results

Present in two separate sections. Do NOT interleave explanations with comment drafts.

**Section A: Issue Analysis**

First, show the summary table:

```
| # | Severity | Confidence | Issue | Location | Action |
|---|----------|-----------|-------|----------|--------|
```

Then, for each item, show the detailed explanation:

```
### #N (Severity, Confidence%) — Short title

📍 `file/path.hpp:123` — [View in PR](https://github.com/{REPO_OWNER}/{REPO_NAME}/pull/{PR_NUMBER}/files#diff-{SHA256}R{LINE})

2-3 sentence explanation with reasoning.
```

Compute the GitHub diff anchor via Bash:
```bash
echo -n "path/to/file.hpp" | sha256sum | cut -c1-64
```

**Section B: Inline Comment Drafts**

For each item, show the draft comment:

```
**#N** — on `file/path.hpp:123`:
​```cpp
the code line this comment attaches to
​```

> Comment text here with code block showing the fix:
> ​```cpp
> fixed code here
> ​```
```

After presenting all drafts, ask the user:
"Want me to post these as inline comments to the PR? You can also ask me to edit or drop specific items."

Use AskUserQuestion with options: "Post all", "Let me edit first", "Don't post".
