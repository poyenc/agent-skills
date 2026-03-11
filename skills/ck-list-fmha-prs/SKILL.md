---
name: ck-list-fmha-prs
description: >
  List open pull requests from ROCm/rocm-libraries that are labeled "project: composablekernel"
  and focused on fused multi-head attention (FMHA) kernels. Use this skill whenever the user asks
  about open FMHA PRs, CK attention PRs, composable kernel flash attention pull requests, or wants
  to see what FMHA-related work is in progress on the rocm-libraries repo. Also trigger when the
  user asks things like "what PRs touch the attention kernel", "show me open CK FMHA changes",
  "list MHA pull requests", or "what's being worked on for flash attention in CK".
---

# List FMHA-Focused PRs in ROCm/rocm-libraries

Find and present all open pull requests in `ROCm/rocm-libraries` labeled `"project: composablekernel"` that primarily modify fused multi-head attention (FMHA) kernel code.

## Prerequisites

- **`gh` CLI**: This skill requires the [GitHub CLI](https://cli.github.com/) to be installed and authenticated. All PR fetching, file listing, and diff inspection is done via `gh api`, `gh pr view`, and `gh pr diff` bash commands.

## Why this skill exists

PR titles in this repo are often vague or misleading — a PR titled "enable sequence paddings for all types" might actually be adding MX FP8/FP4 support to the FMHA kernel. Titles alone are not reliable for filtering. This skill reads diffs and changed file paths to determine the real focus of each PR.

## Step 1: Fetch all labeled PRs

Use `gh api` to fetch all open PRs with the label. The GitHub REST API paginates at 100 results per page, so loop through pages until empty.

```bash
PAGE=1
while true; do
  RESULT=$(gh api "repos/ROCm/rocm-libraries/pulls?state=open&per_page=100&page=$PAGE" \
    --jq '.[] | select(.labels[]?.name == "project: composablekernel") | {number, title, user: .user.login, url: .html_url}')
  [ -z "$RESULT" ] && break
  echo "$RESULT"
  PAGE=$((PAGE + 1))
done
```

Collect all results into a list.

## Step 2: Triage PRs by title

Split the PRs into two buckets:

### Obvious FMHA PRs (title match)
If the title (case-insensitive) contains any of these patterns, it is likely FMHA-focused:
- `fmha`
- `attention`
- `flash`
- `multi-head` or `multihead`
- `mha` (as a word boundary, not substring like "emphasis")

These still need diff verification (Step 3) but are high-confidence candidates.

### Ambiguous PRs (no title match)
All other PRs. Many of these will NOT be FMHA-related, but some will — the title just doesn't say so.

## Step 3: Verify via diffs using subagents

For **every** PR (both buckets), verify whether FMHA is the primary focus by examining changed files and diffs. Launch subagents in parallel for efficiency.

### Subagent prompt template

For each PR, spawn a Task subagent (type: `general-purpose`) with this prompt. The required `gh` commands (`gh pr view`, `gh pr diff`, `gh api repos/*/pulls?*`) must be pre-approved in the permissions allow list (either project-level `.claude/settings.json` or user-level `~/.claude/settings.json`) so that background subagents can run them without interactive approval.

```
Determine whether PR #<NUMBER> in ROCm/rocm-libraries is primarily focused on FMHA (fused multi-head attention) kernel code.

Run these commands:
1. gh pr view <NUMBER> --repo ROCm/rocm-libraries --json title,body,url,author,number,files 2>&1
2. gh pr diff <NUMBER> --repo ROCm/rocm-libraries 2>&1 | head -500

Analyze the results and answer:
1. Does this PR primarily modify FMHA/attention code? (Yes/No)
   - Look for file paths containing "fmha", "attention", "flash_attn"
   - Check if the changes are in FMHA pipeline, kernel, mask, or codegen files
2. If Yes, write a 1-2 sentence summary of what the FMHA change does.
3. If the PR only incidentally touches FMHA files (e.g., adding a shared #include,
   modifying a common utility header that happens to be included by FMHA code),
   answer No — only count PRs where FMHA is the main purpose.

Format your final answer exactly as:
FMHA_FOCUSED: Yes|No
SUMMARY: <1-2 sentence summary or "N/A">
```

Launch subagents in parallel (batch 6-8 at a time to avoid overwhelming the system). Use `run_in_background: true` for all of them.

### Classification rules

A PR is FMHA-focused if **most** of its changed files are in FMHA-related paths, such as:
- `ops/fmha/` — FMHA operator code (pipelines, kernels, problems)
- `example/ck_tile/01_fmha/` — FMHA examples, runners, codegen
- Files named with `fmha_fwd`, `fmha_bwd`, `flash_attn`, `block_fmha`, `mask_info`
- FMHA codegen scripts (`fmha_fwd.py`, `fmha_fwd_splitkv.py`, `fmha_pagedkv_prefill.py`)

A PR is **NOT** FMHA-focused if it only:
- Adds a shared `#include` to an umbrella header that FMHA happens to use
- Modifies core utilities (sequence, tuple, type traits) used across all ops
- Changes GEMM infrastructure that FMHA happens to build on
- Touches an FMHA file with a trivial 1-2 line change while the bulk of changes are elsewhere

## Step 4: Present results

Compile the verified FMHA PRs into a markdown table, sorted by PR number descending (newest first):

```markdown
| # | PR | Author | Summary |
|---|-----|--------|---------|
| 1 | [#NNNN](url) — **Title** | author | Summary of FMHA changes |
| 2 | ... | ... | ... |
```

After the table, add a brief "Excluded" section listing any PRs that had FMHA keywords in the title but were determined NOT to be FMHA-focused after diff inspection, with a short reason why.

## Performance notes

- There are typically 40-80 open CK-labeled PRs at any time. Of these, usually 5-15 touch FMHA code.
- Spawning subagents in parallel keeps total wall time reasonable (~1-2 minutes for the full scan).
- If the PR count is small enough (< 10 PRs total), you can examine diffs inline instead of using subagents.
