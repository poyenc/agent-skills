---
name: ck-ci-report
description: >
  Analyze CI build failures for Composable Kernel pull requests on the Jenkins dashboard.
  Use this skill whenever the user asks about CI failures, build errors, Jenkins build status,
  or wants to investigate why a CK PR build failed. Trigger on phrases like "check CI",
  "why did the build fail", "CI report for PR", "check Jenkins", "what failed in PR-XXXX",
  "build status", "CI dashboard", or "analyze build failure".
---

# Analyze CK CI Build Failures

Investigate Jenkins CI build failures for Composable Kernel PRs and produce a concise failure report.

## Prerequisites

- **`playwright-cli`**: Must be installed globally (`npm install -g @playwright/cli@latest`)
- **`node`**: Required for JSON decoding
- **Script**: `ci-report.sh` (bundled with this skill)

## Setup

Copy or symlink the script to `~/.claude/scripts/`:

```bash
cp <skill-dir>/ci-report.sh ~/.claude/scripts/ci-report.sh
chmod +x ~/.claude/scripts/ci-report.sh
```

## Step 1: Get the PR number

If the user hasn't provided a PR number, ask for it. The PR number is the GitHub PR number
(e.g., 6983 from `ROCm/rocm-libraries/pull/6983`).

The user may also provide a full Jenkins URL like:
`http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/view/change-requests/job/PR-6983/`
Extract the PR number from the URL.

## Step 2: Run the ci-report script

Run the script to extract and analyze the console output. The script handles browser automation,
console extraction, and initial parsing — saving tokens by doing the heavy lifting in bash.

```bash
bash ~/.claude/scripts/ci-report.sh <PR_NUMBER> [BUILD_SELECTOR]
```

Arguments:
- `PR_NUMBER` (required): The PR number (e.g., `6983`)
- `BUILD_SELECTOR` (optional): Which build to analyze. Defaults to `lastBuild`.
  Other options: `lastFailedBuild`, `lastSuccessfulBuild`, or a specific build number like `4`.

The script outputs:
- A markdown report to stdout (and saves to `/tmp/ci-report-PR-<N>.md`)
- Full console log saved to `/tmp/ci-console-PR-<N>.txt`
- Error lines saved to `/tmp/ci-errors-<N>.txt`
- For build/test failures (non-infra): stage log saved to `/tmp/ci-stage-log-<N>.txt`

For build/test failures, the script automatically performs a **deep dive** via the Blue Ocean REST API:
1. Queries `/blue/rest/.../runs/{BUILD}/nodes/` to find the first stage with `result: "FAILURE"` or `"ABORTED"`
2. Queries `.../nodes/{NODE}/steps/` to find the first failed Shell Script step
3. Queries `.../steps/{STEP}/log/` to extract the actual error log
4. Searches for error patterns, GTest results, and CTest failures
5. Appends a "Stage Log Analysis" section to the report

This approach works for any stage type (Build CK, AITER, FA, Pytorch, FMHA, etc.).

## Step 3: Interpret the report

Read the script output and present to the user in this exact format:

### If no builds exist:

```
CI Report: PR #<PR_NUMBER>
Result: NO BUILDS

No CI builds found for this PR. The build may not have been triggered yet.
```

No further analysis needed.

### If the build SUCCEEDED:

```
CI Report: PR #<PR_NUMBER> (Build #<BUILD_NUMBER>)
Result: SUCCESS
Build at: <DATE> <TIME>

The latest build completed successfully. All stages passed.
```

No further analysis needed for successful builds.

### If the build FAILED:

```
CI Report: PR #<PR_NUMBER> (Build #<BUILD_NUMBER>)
Failed stage: <STAGE_NAME>
Category: <CATEGORY>
Build at: <DATE> <TIME>

<Description of what failed and why, whether it's a code or infra issue,
how many stages were skipped, and suggested next steps.>
```

Determine the **Category** from one of:
- **Infrastructure/credential issue**: GitHub token errors, Jenkins plugin failures, agent connectivity
- **Compilation error**: CMake errors, build failures, missing headers, linker errors
- **Test failure**: Test assertions, segfaults, timeouts during test execution
- **Timeout/resource issue**: Build exceeded time limit, OOM kills
- **Pipeline logic error**: Groovy/Jenkinsfile script errors

Determine if it's a **code issue or infra issue**:
- If the error is in Jenkins plugins, GitHub API, or agent setup — it's infra, not the PR's fault
- If the error is in compilation or tests — it may be related to the PR's changes

For **build/test failures**, the script automatically includes a "Stage Log Analysis" section
with error lines from the actual build/test stage log. Use this to provide a detailed summary:
- For **test failures**: report GTest results (passed/failed counts), identify the failing test
  suite and test names, describe the nature of the errors (numerical correctness, crashes, etc.)
- For **compilation errors**: identify the source file and error message
- If the stage log analysis shows "No error patterns found", the script may have picked the
  wrong node.

## Step 4: Deep dive (if needed)

If the user wants more details, the following files are available:

- `/tmp/ci-console-PR-<N>.txt` — top-level Jenkins console log
- `/tmp/ci-stage-log-<N>.txt` — stage-specific build/test log (from deep dive)

Use `grep` to search for specific patterns:

```bash
# Find compilation errors in stage log
grep -n 'error:' /tmp/ci-stage-log-<N>.txt | head -20

# Find test failures in stage log
grep -n 'FAILED\|FAIL\|assertion' /tmp/ci-stage-log-<N>.txt | head -20

# Get context around a specific error line
sed -n '<LINE-5>,<LINE+5>p' /tmp/ci-stage-log-<N>.txt
```

## Notes

- The Jenkins base URL pattern is:
  `http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/view/change-requests/job/PR-<NUMBER>/`
- The script uses Edge browser (`--browser=msedge`) by default
- Browser is closed automatically after extracting the console output
- For very large console outputs (long compilation logs), extraction may take a few seconds
