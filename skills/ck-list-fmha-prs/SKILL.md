---
name: ck-list-fmha-prs
description: >
  List open pull requests from ROCm/rocm-libraries that are labeled "project: composablekernel"
  and focused on fused multi-head attention (FMHA) — including kernel code, tests, and CI/infrastructure.
  Use this skill whenever the user asks about open FMHA PRs, CK attention PRs, composable kernel
  flash attention pull requests, FMHA test PRs, FMHA CI changes, or wants to see what FMHA-related
  work is in progress on the rocm-libraries repo. Also trigger when the user asks things like
  "what PRs touch the attention kernel", "show me open CK FMHA changes", "list MHA pull requests",
  "what's being worked on for flash attention in CK", "FMHA test PRs", or "FMHA CI changes".
  Pass `--full-scan` to ignore saved state and re-scan all PRs from scratch.
---

# List FMHA-Focused PRs in ROCm/rocm-libraries

Find and present all open pull requests in `ROCm/rocm-libraries` labeled `"project: composablekernel"` that primarily modify fused multi-head attention (FMHA) code — including kernel implementations, tests, and CI/infrastructure.

## Prerequisites

- **`gh` CLI**: Installed and authenticated. The required commands (`gh pr view`, `gh pr diff`, `gh api repos/*/pulls?*`) must be pre-approved in settings.
- **`jq`**: For JSON processing.
- **`yq`** (v4+): For YAML state file I/O.

## Why this skill exists

PR titles in this repo are often vague or misleading — a PR titled "enable sequence paddings for all types" might actually be adding MX FP8/FP4 support to the FMHA kernel. Titles alone are not reliable for filtering. This skill reads diffs and changed file paths to determine the real focus of each PR.

## How state works

This skill maintains a state file to avoid re-scanning PRs that have already been classified:

- **State file:** `~/.claude/projects/-mnt-c-Users-poyechen-workspace-repo-rocm-libraries/fmha-pr-state.yaml`
- **High-water mark:** The highest PR number that has been scanned. Only PRs with numbers above this are verified on subsequent runs.
- **Confirmed list:** PRs previously verified as FMHA-focused. On each run, closed/merged PRs are automatically removed.
- **Full reset:** Pass `--full-scan` as a skill argument to ignore saved state and re-scan everything.

## Step 1: Load pending work

Resolve the skill directory first:

```bash
SKILL_DIR=$(cd "$(dirname "$(readlink -f ~/.claude/skills/ck-list-fmha-prs/SKILL.md)")" && pwd)
```

Run the companion script:

```bash
bash $SKILL_DIR/scripts/fmha-pr-scan.sh \
    --state-file ~/.claude/projects/-mnt-c-Users-poyechen-workspace-repo-rocm-libraries/fmha-pr-state.yaml \
    list-pending [--full-scan]
```

Include `--full-scan` only if the user passed it as a skill argument.

Parse the YAML output. It contains:
- `max_pr_number` — highest PR number seen (used later to update the high-water mark)
- `to_verify.obvious_fmha` — new PRs whose titles match FMHA keywords
- `to_verify.ambiguous` — new PRs with non-matching titles
- `confirmed_open` — previously confirmed FMHA PRs still open

If both `to_verify.obvious_fmha` and `to_verify.ambiguous` are empty, skip to Step 3 (do NOT skip Step 3 itself — it must always run).

## Step 2: Verify new PRs via subagents

For **every** PR in `to_verify` (both `obvious_fmha` and `ambiguous`), verify whether FMHA is the primary focus by examining changed files and diffs. Launch subagents in parallel for efficiency.

### Subagent prompt template

For each PR, spawn a Task subagent (type: `general-purpose`) with this prompt:

```
Determine whether PR #<NUMBER> in ROCm/rocm-libraries is primarily focused on FMHA (fused multi-head attention) code — including kernel implementations, tests, or CI/infrastructure.

Run these commands:
1. gh pr view <NUMBER> --repo ROCm/rocm-libraries --json title,body,url,author,number,files 2>&1
2. gh pr diff <NUMBER> --repo ROCm/rocm-libraries 2>&1 | head -500

Analyze the results and answer:
1. Does this PR primarily modify FMHA/attention code? (Yes/No)
   - Look for file paths containing "fmha", "attention", "flash_attn"
   - Check if the changes are in FMHA pipeline, kernel, mask, or codegen files
2. Does this PR primarily modify FMHA tests or CI/infrastructure? (Yes/No)
   - Look for FMHA test files (gtest, pytest, test runners, test configs)
   - Look for CI pipeline/workflow changes that specifically target FMHA builds or tests
   - Look for CMakeLists.txt or build script changes in FMHA test directories
   - Look for test data, fixtures, or validation scripts for FMHA
3. If Yes to either, write a 1-2 sentence summary of what the FMHA change does.
4. If the PR only incidentally touches FMHA files (e.g., adding a shared #include,
   modifying a common utility header that happens to be included by FMHA code,
   or a repo-wide CI change that happens to include FMHA jobs),
   answer No — only count PRs where FMHA is the main purpose.

Format your final answer exactly as:
FMHA_FOCUSED: Yes|No
CATEGORY: Kernel|Test/CI|Both|N/A
SUMMARY: <1-2 sentence summary or "N/A">
```

Launch subagents in parallel (batch 6-8 at a time). Use `run_in_background: true` for all of them.

### Classification rules

A PR is FMHA-focused if **most** of its changed files are in FMHA-related paths, such as:
- `ops/fmha/` — FMHA operator code (pipelines, kernels, problems)
- `example/ck_tile/01_fmha/` — FMHA examples, runners, codegen
- Files named with `fmha_fwd`, `fmha_bwd`, `flash_attn`, `block_fmha`, `mask_info`
- FMHA codegen scripts (`fmha_fwd.py`, `fmha_fwd_splitkv.py`, `fmha_pagedkv_prefill.py`)
- FMHA test files (gtests, test runners, test scripts under FMHA directories)
- FMHA CI/workflow files (GitHub Actions, Jenkinsfiles, or build scripts specifically for FMHA testing)
- FMHA CMakeLists.txt or build configuration in test directories
- Test data, fixtures, reference outputs, or validation scripts for FMHA

A PR is **NOT** FMHA-focused if it only:
- Adds a shared `#include` to an umbrella header that FMHA happens to use
- Modifies core utilities (sequence, tuple, type traits) used across all ops
- Changes GEMM infrastructure that FMHA happens to build on
- Touches an FMHA file with a trivial 1-2 line change while the bulk of changes are elsewhere
- Makes repo-wide CI changes that happen to include FMHA jobs among many others

## Step 3: Commit results

**Always run this step, even if Step 2 was skipped.** The `confirmed_open` list may have changed (closed/merged PRs removed), and this step persists that update.

Merge the verified FMHA PRs from Step 2 (if any) with the `confirmed_open` PRs from Step 1. For each newly confirmed PR, include: `number`, `title`, `author`, `url`, `category`, `summary`, `created_at`.

Build a YAML document with this structure and pipe it to the script:

```yaml
last_scanned_pr: <max_pr_number from Step 1>
confirmed_fmha_prs:
  - number: ...
    title: "..."
    author: ...
    url: ...
    category: ...
    summary: "..."
    created_at: "..."
```

```bash
cat <<'EOF' | bash $SKILL_DIR/scripts/fmha-pr-scan.sh \
    --state-file ~/.claude/projects/-mnt-c-Users-poyechen-workspace-repo-rocm-libraries/fmha-pr-state.yaml \
    commit-results
last_scanned_pr: 7312
confirmed_fmha_prs:
  - number: 7016
    title: "[CK] Fix RDNA3/RDNA4 FMHA tile-load paths"
    author: jammm
    url: https://github.com/ROCm/rocm-libraries/pull/7016
    category: Kernel
    summary: "Fixes RDNA3/RDNA4 tile-load paths for FMHA."
    created_at: "2026-05-02T07:21:10Z"
EOF
```

## Step 4: Present results

Compile **all** confirmed FMHA PRs (both previously confirmed and newly verified) into a markdown table, sorted by creation date descending (newest first):

```markdown
| # | PR | Author | Category | Age | Summary |
|---|-----|--------|----------|-----|---------|
| 1 | [#NNNN](url) — **Title** | author | Kernel | 3d | Summary of FMHA changes |
| 2 | [#NNNN](url) — **Title** | author | Test/CI | 2w | Summary of test/CI changes |
| 3 | ... | ... | Both | 1mo | ... |
```

The "Age" column shows how long ago the PR was created. Use the largest fitting unit: `Xd` (days) for < 14 days, `Xw` (weeks) for < 8 weeks, `Xmo` (months) otherwise.

After the table, add:
- An "Excluded" section listing any PRs from `to_verify` that had FMHA keywords in the title but were determined NOT to be FMHA-focused after diff inspection, with a short reason why.
- A note saying how many PRs were scanned in this run vs. loaded from state, so the user knows what was incremental.

## Performance notes

- With state, typical incremental runs only verify 0-5 new PRs instead of 40-80 — completing in seconds rather than minutes.
- Use `--full-scan` periodically (e.g., weekly) to catch any PRs that may have changed scope since initial classification.
- If the total PRs to verify is small (< 10), you can examine diffs inline instead of using subagents.
