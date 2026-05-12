# FMHA PR Scan Fixes

**Date:** 2026-05-12
**Status:** Draft
**Skill:** `ck-list-fmha-prs`

## Problem

The first live run of the state-persistence feature exposed 9 issues across the shell script and SKILL.md. The most impactful: the agent skipped saving state after the scan (requiring manual prompting), and all ~70 ambiguous PRs were sent to subagents when only ~5 actually touch FMHA files.

## Fixes

### Script: `skills/ck-list-fmha-prs/scripts/fmha-pr-scan.sh`

#### Fix 1: File-path pre-filter for ambiguous PRs (#4-5)

Add a function `filter_ambiguous_by_files()` that uses `gh api graphql` to batch-query changed file paths for ambiguous PRs. Only PRs with at least one file matching FMHA path patterns are kept in the `ambiguous` output.

GraphQL batching: query 25 PRs per request (GraphQL has complexity limits). For each PR, fetch `files(first: 100) { nodes { path } }` and check if any path matches `fmha|flash_attn|attention|block_fmha|mask_info` (case-insensitive).

This runs inside `list_pending()` after the jq triage step, before outputting YAML. The `obvious_fmha` bucket is not filtered — those already matched by title.

#### Fix 2: Replace jq `index()` with `any()` (#7)

In the main `jq` expression in `list_pending()`, replace all occurrences of:
```
$conf_nums | index($n)
```
with:
```
$conf_nums | any(. == $n)
```

And similarly for `$open_nums | index($n)`. The `index()` function returns null (falsy) when not found, which works but is semantically wrong (it's meant for finding position, not testing membership). `any()` is clearer and avoids O(n) position scanning.

#### Fix 3: gh API error handling (#8)

In `fetch_open_prs()`, check `gh api` exit code. If non-zero, print the error to stderr and exit 1.

In the new `filter_ambiguous_by_files()` GraphQL function, similarly check `gh api graphql` exit code.

#### Fix 4: Reject `--full-scan` with `commit-results` (#9)

After arg parsing, add validation:
```bash
if [[ "$FULL_SCAN" == "true" ]] && [[ "$SUBCOMMAND" == "commit-results" ]]; then
    echo "Error: --full-scan is only valid with list-pending" >&2
    exit 1
fi
```

### SKILL.md: `skills/ck-list-fmha-prs/SKILL.md`

#### Fix 5: Make Step 3 mandatory (#1-2)

Change Step 1's skip instruction from:
> "If both `to_verify.obvious_fmha` and `to_verify.ambiguous` are empty, skip to Step 3"

To:
> "If both `to_verify.obvious_fmha` and `to_verify.ambiguous` are empty, skip to Step 3 (do NOT skip Step 3 itself)."

Add a bold callout at the top of Step 3:
> **Always run this step, even if Step 2 was skipped.** The `confirmed_open` list may have changed (closed/merged PRs removed), and this step persists that update.

#### Fix 6: Resolve `<skill-dir>` concretely (#3)

Replace the ambiguous `<skill-dir>` instruction with a concrete resolution. At the top of Step 1, add:

> Resolve the skill directory by finding the directory containing this SKILL.md:
> ```bash
> SKILL_DIR=$(cd "$(dirname "$(readlink -f ~/.claude/skills/ck-list-fmha-prs/SKILL.md)")" && pwd)
> ```
> Use `$SKILL_DIR` in all script paths below.

Then replace all `<skill-dir>` references with `$SKILL_DIR`.

#### Fix 7: Fix heredoc placeholder (#6)

In Step 3, replace the `<the YAML content>` placeholder in the heredoc example with a concrete example:

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

### Test script: `skills/ck-list-fmha-prs/tests/test-fmha-pr-scan.sh`

#### New test cases

**Test 7: `--full-scan` with `commit-results` should error.** Run `echo "..." | bash $SCRIPT --state-file ... --full-scan commit-results` and assert exit code 1.

**Test 8: `gh api` failure handling.** Create a mock `gh` that returns exit code 1. Run `list-pending` and assert exit code 1 with an error message.

**Test 9: Ambiguous file-path pre-filter.** This requires mocking the GraphQL endpoint. The mock `gh` needs to handle both `gh api repos/...` (REST, returns PR list) and `gh api graphql` (returns file paths). Extend the mock to check `$1` for `graphql` vs `api`:
- `api` with no `graphql`: return canned REST PR data (existing behavior)
- `graphql`: return canned file-path responses where only specific PRs have FMHA paths

Test that an ambiguous PR with FMHA file paths appears in `to_verify.ambiguous`, and one without FMHA paths is excluded.
