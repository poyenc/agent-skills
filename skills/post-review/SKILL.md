---
name: post-review
description: >
  Validate and post inline PR comments from a prior /review output, OR from
  a finished evidence-backed review-report.md (e.g. from a multi-agent PR
  review process). Spawns a subagent to verify each claim against actual
  code, drops wrong items, formats confirmed findings as comment drafts
  with GitHub blob-permalink hyperlinks to any referenced source, and
  optionally posts each approved one individually to GitHub — as an inline
  comment when its line is part of the diff, or a standalone PR comment
  otherwise. Works with both PR and local branch reviews. Trigger on: "post review", "post
  comments", "post inline comments", "format review as comments", "post
  these findings to the PR", "turn the review report into PR comments", or
  "/post-review".
---

# Post Review

Turn review findings — from `/review` output or a review-report.md — into comments the author can act on quickly, and optionally post each approved one to GitHub individually (inline if its line is in the diff, standalone otherwise).

**Why this exists**: a review is only useful to the extent it saves the author time. Whoever wrote the finding already spent time locating the exact line, understanding the mechanism, and figuring out a fix — a good comment transfers all of that so the author doesn't have to redo the investigation. Treat this as collaborative, not adversarial: the goal is that both the author and the reviewer come away understanding the code better, not just "you got flagged."

## Prerequisites

This skill needs a finished set of findings to work from — one of:
- `/review` output already present in the conversation, or
- a path to a review-report.md (e.g. produced by an evidence-backed multi-agent review process) with structured findings (problem statement, location, severity/confidence, fix suggestion).

If neither is available, tell the user to run `/review` (or the relevant review process) first.

## Argument Parsing

Parse the skill arguments to extract:
- `REPORT_PATH`: path to a review-report.md file (optional — if absent, scan the conversation for `/review` output instead)
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

Store: `PR_TITLE` = current branch name, `HEAD_COMMIT_SHA=$(git rev-parse HEAD)`.

Also try to resolve `REPO_OWNER`/`REPO_NAME` even in local mode (needed for hyperlinks — see Comment Style below), e.g. via `gh repo view --json owner,name` or by parsing `git remote get-url origin`. If the repo has no GitHub remote at all, there's nothing to link to — fall back to plain `path:line` text in drafted comments instead of a hyperlink, and skip Step 5 (posting) entirely since there's no PR to post to anyway.

### Split diff into chunks

```bash
csplit -z -f {REVIEW_DIR}/chunk- {REVIEW_DIR}/diff.txt '/^diff --git/' '{*}'
```

Discard any resulting chunk whose first line doesn't start with `diff --git` (a PR diff can have leading header text before the first real hunk, which `csplit` will capture as its own chunk and which isn't a valid file entry). Build a map of `{file_path: chunk_file}` from the first line of each remaining chunk.

## Step 2: Extract Review Items

**From `/review` output**: scan the conversation for it. Extract each finding as a structured item:
- File path and line number (if present)
- Issue description
- Severity and confidence (if present — carry both through even if only one is stated)
- Suggested fix (if present)

**From a review-report.md**: read the file at `{REPORT_PATH}`. Each finding typically already has file/symbol/location, severity/confidence, a problem statement, a causal trace, a fix suggestion, and a verification packet. Pull all of that through rather than summarizing it away — the whole point of that format is to carry enough evidence that this skill's validation step (Step 3) can check it, and that the eventual comment doesn't lose it. Also carry forward the report's reviewed commit SHA as `HEAD_COMMIT_SHA` — a review-report.md always states it explicitly near the top, typically on a line like "Reviewed head commit: `<sha>`"; search for that phrasing first and only fall back to a bare 40-character-hex-string grep if it isn't found, since the file may cite other SHAs too (a base commit, examples) that a plain grep can't distinguish. Note this report's title/identifier too, to use as `PR_TITLE` context for the validation subagent if there's no real PR.

**Line numbers always mean the current (head-commit) file, not the pre-change one.** Whichever source you're extracting from, a finding's cited line is the line in the file *as it exists at the reviewed commit* — Check B in Step 3 re-verifies this by re-reading current source, not a diff. Keep this in mind for Step 5: it's what makes matching against a diff hunk's `+new_start,new_count` range (rather than its `-old_start,old_count` range) the correct comparison.

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
> 4. Budget: roughly 2-3 tool calls per finding (a source read plus a diff-chunk read, sometimes a second file for cross-file findings) — scale with {NUMBER_OF_FINDINGS}, don't force a fixed total that gets tighter as findings grow.
>
> **YOUR TASK — two separate checks per finding, not one:**
>
> **Check A — is the claim TRUE?** Give a verdict:
> - **Confirmed** — the issue is real and correctly described
> - **Wrong** — the claim is incorrect; explain why with evidence
> - **Overstated** — the issue exists but description is exaggerated; explain
>
> **Check B — is the EVIDENCE good enough to post as-is?** A claim can be true and still not be ready to hand to an author — that's a separate failure mode, and posting an underspecified comment just pushes the investigation work onto the author instead of saving them from it. For every claim that passes Check A, verify all four of:
> 1. **Location accuracy** — does the cited file/line still point to exactly the described code? (Don't assume the finding is fresh — re-grep/re-read it; line numbers drift.)
> 2. **Factual accuracy** — does the code snippet / causal trace in the finding still match current source?
> 3. **Fix completeness** — is the suggested fix concrete enough that the author can apply it directly, with no judgment call or further investigation required? If something is ambiguous or underspecified, say exactly what's missing.
> 4. **Reproducibility** — could someone reproduce or confirm this finding from what's written, without asking a follow-up question?
>
> Mark each claim **Ready** (passes A and B) or **Needs more work** (passes A but fails one or more of B's checks — say which, and what's missing). Only **Ready** items become posted comments; **Needs more work** items get reported back to the user as "confirmed but not comment-ready" rather than silently dropped or posted half-baked.
>
> For Ready items, provide:
> - Exact file:line in the current source
> - A concise inline comment (2-4 sentences) explaining the issue and showing a fix
> - Use the comment style below
>
> **COMMENT STYLE — this is the body text that will eventually be posted for the AUTHOR to read, so it must stand on its own:**
> - Explain the *why* (the mechanism, not just "this is wrong"), show the *what* — the goal is the author (and you) understanding the code better, not a gotcha
> - Any reference to a source file/line OTHER than the line this comment is anchored to (another function, a related test, a call site) must be a markdown hyperlink to the GitHub blob permalink at the exact reviewed commit SHA: `[label](https://github.com/{owner}/{repo}/blob/{commit_sha}/{path}#L{line})` (use `#L{start}-L{end}` for a range) — never a bare `file.py:123` reference in posted text. If {REPO_OWNER}/{REPO_NAME} couldn't be resolved (no GitHub remote), fall back to plain `path:line` text instead.
> - Any code snippet, example, or suggested fix goes in its own fenced code block with a language tag, on its own lines, separated from the explanation by blank lines — never inlined into a sentence
> - For direct fixes, show a code snippet the author can copy-paste
> - For conceptual fixes, show before/after key statements
> - Keep it concise — no walls of text
> - Do **not** mention severity or confidence inside this body text — those numbers are for the human reviewer's own triage (deciding which findings to post at all), not something the author needs to see. Report them separately, alongside the comment, not inside it.
>
> Report verdicts in order, including Wrong ones — a claim you disproved with evidence is worth reporting too, not just silently discarding; state briefly why it's wrong so the user knows what was checked. For Needs-more-work items, state exactly what evidence is missing.

## Step 4: Present Results

After the subagent returns, every item gets shown to the user in the summary table below — nothing is hidden, including Wrong ones (the user should see what was checked and ruled out, not just what survived). Only the *drafting* step is selective:

1. **Wrong** items: not drafted as comments, but still listed in the summary table with the subagent's reason.
2. **Overstated** items: use the subagent's adjusted/scoped description, then treat them exactly like a Ready item (draft + list) if they also pass Check B — an overstated-but-corrected claim can still be comment-ready.
3. **Needs more work** items: not drafted as comments yet. List them with exactly what's missing (per Check B) so the user can decide whether to dig up the missing evidence before posting, or post without it and accept the gap.
4. **Ready** items (any confidence ≥60%, or every Confirmed/Ready item if the source has no numeric confidence): draft all of them. Don't quietly omit ones you personally judge as minor — severity and confidence are exactly the information the user needs to make that call themselves; deciding it for them defeats the point of surfacing both.

### Summary Table

Show an overview of everything found, sorted by severity then confidence (highest first) among Ready/Overstated items, before drafting full comments. Severity/confidence are for the user's eyes here — this table, not the eventual GitHub comment:

```
| # | Severity | Confidence | File:Line | Issue | Verdict |
|---|----------|------------|-----------|-------|---------|
```

Verdict is one of: Ready, Needs more work (+ what's missing), Wrong (+ why). Include every item the subagent evaluated, Wrong ones included — this table is the user's full decision surface, not a pre-filtered shortlist.

### Comment Drafts

For each Ready/Overstated-and-passing item, show the draft — most will end up posted inline, but whether a given one lands inline or standalone isn't decided until Step 5 checks it against the diff. The `[Severity, Confidence%]` tag here is for the user's triage view only — it does **not** belong in the comment body itself (see Step 5):

```
**#N** — [Severity, Confidence%] on `file/path.hpp:123`:
​```cpp
the code line this comment attaches to
​```

> Comment text with fix suggestion (no severity/confidence inside this part — that's what actually gets posted)
```

All inline comments use normal fenced code blocks. NEVER use GitHub `suggestion` blocks.

After presenting all drafts, ask in plain text (do NOT use AskUserQuestion):

"Here are all N findings ≥60% confidence, with severity/confidence shown above — which do you want posted? Say 'all' or list the ones you want (e.g. '1, 3, 4'). You can also ask me to edit specific ones first."

Wait for the user to respond before proceeding. Each item they approve gets posted as its own independent GitHub action in Step 5 — there is no combined "review" object bundling multiple findings. This matters for how the user should think about it: approving 3 findings means 3 separate visible posts (each immediately live the moment it's posted), not one batch that appears all at once after a final submit.

## Step 5: Post to GitHub (if approved)

Only for PR mode (there's no PR to post to in local mode — presenting drafts is as far as that path goes). Only for the specific items the user approved in Step 4.

For each approved item, independently:

1. Strip the `[Severity, Confidence%]` triage tag from the drafted text before building its `body` below — that tag was for the user's decision-making in Step 4, not for the author to see.

2. Determine whether its line is part of the diff. The GitHub Reviews API (`line` + `side: "RIGHT"`) wants the 1-based line number in the file *as of the head commit* — not a v3-style diff "position" offset, and (per the head-commit note in Step 2) the same number the finding already cites, with no arithmetic needed. What you're checking is coverage, not conversion: scan the hunk headers (`@@ -old_start,old_count +new_start,new_count @@`) in `{REVIEW_DIR}/diff.txt` for the target file, and check whether the cited line falls within some hunk's **`+new_start,new_count`** range (the new-file side — not `-old_start,old_count`, which describes the pre-change file and isn't what the finding's line number refers to).

3a. **If the line is diff-covered** — post it as its own inline review comment:
```bash
cat > {REVIEW_DIR}/comment-{N}.json << 'EOF'
{
  "commit_id": "{HEAD_COMMIT_SHA}",
  "path": "path/to/file.hpp",
  "line": 123,
  "side": "RIGHT",
  "body": "Comment text with fenced code blocks, no severity/confidence tag"
}
EOF
gh api repos/{REPO_OWNER}/{REPO_NAME}/pulls/{PR_NUMBER}/comments --input {REVIEW_DIR}/comment-{N}.json
```
Each call like this is immediately visible to the author on its own — it is not held in a draft or pending state waiting on a separate submit step, so only run it once you actually intend that comment to go live.

3b. **If the line is not diff-covered** (an unchanged line the PR doesn't touch — GitHub would reject an inline comment there with a 422) — post it as a standalone PR comment instead. The drafted body from Step 4 was written assuming an inline anchor (it doesn't name its own location), so prepend an explicit self-referencing hyperlink line before it — this is the one piece of rewiring a standalone comment needs that an inline one doesn't:
```bash
cat > {REVIEW_DIR}/comment-{N}.md << 'EOF'
**Re: [`path/to/file.hpp:123`](https://github.com/{owner}/{repo}/blob/{commit_sha}/path/to/file.hpp#L123)**

Comment text with fenced code blocks, no severity/confidence tag
EOF
gh pr comment {PR_NUMBER} --body-file {REVIEW_DIR}/comment-{N}.md
```

4. Report that item's resulting comment URL to the user right after posting it, before moving to the next approved item — don't silently batch all the URLs until the end.
