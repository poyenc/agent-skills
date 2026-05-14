---
name: ck-ci-report
description: >
  Analyze CI build failures for Composable Kernel pull requests or branches on the Jenkins dashboard.
  Use this skill whenever the user asks about CI failures, build errors, Jenkins build status,
  or wants to investigate why a CK PR or branch build failed. Trigger on phrases like "check CI",
  "why did the build fail", "CI report for PR", "CI report for branch", "check Jenkins",
  "what failed in PR-XXXX", "what failed on branch X", "build status", "CI dashboard",
  or "analyze build failure".
---

# Analyze CK CI Build Failures

Investigate Jenkins CI build failures for Composable Kernel PRs or branches and produce a concise failure report.

## Prerequisites

- **`curl`**: With Kerberos auth support (`--negotiate`)
- **`python3`**: Required for JSON parsing
- **Script**: `scripts/ci-report.sh` (bundled with this skill, no setup needed)

## Step 1: Get the PR number or branch name

The user can provide either:
- A **PR number** (e.g., `6983` from `ROCm/rocm-libraries/pull/6983`)
- A **branch name** (e.g., `ck/user/feature-name`)

The user may also provide a full Jenkins URL like:
- PR: `http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/view/change-requests/job/PR-6983/`
- Branch: `http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/job/ck%252Fuser%252Ffeature/`

Extract the PR number or branch name from the URL. For branch URLs, decode `%252F` → `/`.

If neither is provided, ask the user what they want to check.

## Step 2: Run the ci-report script

Run the script to extract and analyze the console output. The script handles browser automation,
console extraction, and initial parsing — saving tokens by doing the heavy lifting in bash.

```bash
bash <skill-dir>/scripts/ci-report.sh <PR_NUMBER_OR_BRANCH> [BUILD_SELECTOR]
```

Arguments:
- `PR_NUMBER_OR_BRANCH` (required): PR number (e.g., `6983`) or branch name (e.g., `ck/user/feature`)
  - If all digits → treated as PR number
  - Otherwise → treated as branch name
- `BUILD_SELECTOR` (optional): Which build to analyze. Defaults to `lastBuild`.
  Other options: `lastFailedBuild`, `lastSuccessfulBuild`, or a specific build number like `4`.

The script outputs:
- A markdown report to stdout (and saves to `/tmp/ci-report-<ID>.md`)
- Full console log saved to `/tmp/ci-console-<ID>.txt`
- For build/test failures (non-infra): stage log saved to `/tmp/ci-stage-log-<ID>.txt`

Where `<ID>` is `PR-<N>` for PRs or the branch name with `/` replaced by `__`.

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
CI Report: PR #<N>          (or: CI Report: Branch: <name>)
Result: NO BUILDS

No CI builds found. The build may not have been triggered yet.
```

No further analysis needed.

### If the build is IN PROGRESS:

```
CI Report: PR #<N> (Build #<BUILD_NUMBER>)
Result: IN PROGRESS
Build at: <DATE> <TIME>

Currently running: <STAGE_NAMES>
Progress: X/Y stages completed
```

No failure analysis needed. Just relay the progress to the user.

### If the build SUCCEEDED:

```
CI Report: Branch: <name> (Build #<BUILD_NUMBER>)
Result: SUCCESS
Build at: <DATE> <TIME>

The latest build completed successfully. All stages passed.
```

No further analysis needed for successful builds.

### If the build FAILED:

```
CI Report: PR #<N> (Build #<BUILD_NUMBER>)
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

- `/tmp/ci-console-<ID>.txt` — top-level Jenkins console log
- `/tmp/ci-stage-log-<ID>.txt` — stage-specific build/test log (from deep dive)

Use `grep` to search for specific patterns:

```bash
# Find compilation errors in stage log
grep -n 'error:' /tmp/ci-stage-log-<ID>.txt | head -20

# Find test failures in stage log
grep -n 'FAILED\|FAIL\|assertion' /tmp/ci-stage-log-<ID>.txt | head -20

# Get context around a specific error line
sed -n '<LINE-5>,<LINE+5>p' /tmp/ci-stage-log-<ID>.txt
```

## Notes

- Jenkins URL patterns:
  - PR: `http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/job/PR-<N>/`
  - Branch: `http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/job/<encoded-branch>/`
  - Branch names have `/` encoded as `%2F`, then double-encoded in URLs as `%252F`
- The script uses `curl --negotiate` with Kerberos auth (no browser needed)
- Uses Blue Ocean REST API for structured stage/step/log data instead of parsing full consoleText
- Full consoleText is downloaded in the background as a saved artifact for manual review
