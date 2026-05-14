---
name: ck-ci-build
description: Trigger Jenkins CI builds for Composable Kernel pull requests or branches with optional parameter overrides. Use this skill whenever the user wants to trigger a CI build, start a build, kick off CI, rebuild, re-run CI, or launch a Jenkins build for a CK or Composable Kernel PR or branch. Also trigger when the user asks to set CI build parameters, enable/disable specific tests (like FMHA, AITER, FA, pytorch), or wants to check what CI parameters are available for a PR or branch.
---

# Trigger CK CI Builds

Trigger Jenkins CI builds for Composable Kernel PRs or branches and optionally override build parameters (test toggles, compiler settings, etc.).

## Prerequisites

- **`curl`**: With Kerberos auth support (`--negotiate`)
- **`playwright-cli`**: For browser-based build triggering (reuses existing browser session)
- **`python3`**: For JSON parsing
- **Script**: `scripts/ci-build.sh` (bundled with this skill)

## Step 1: Check browser preference

Before running the script, check if `~/.claude/ck-ci-build/config` exists.

**If it does NOT exist** (first-time use), ask the user which browser to use:

Use `AskUserQuestion` with these options:
- **Microsoft Edge** (Recommended) — maps to config value `msedge`
- **Google Chrome** — maps to config value `chrome`
- **Firefox** — maps to config value `firefox`
- **Other** — let the user type the playwright-cli browser name (e.g., `webkit`)

**Browser name mapping** — normalize user input to playwright-cli values:

| User says (case-insensitive)      | Config value |
|-----------------------------------|--------------|
| Edge / Microsoft Edge / msedge    | `msedge`     |
| Chrome / Google Chrome            | `chrome`     |
| Firefox                           | `firefox`    |
| Webkit / Safari                   | `webkit`     |
| (anything else)                   | stored as-is |

Then write the config:
```bash
mkdir -p ~/.claude/ck-ci-build
echo "BROWSER=<value>" > ~/.claude/ck-ci-build/config
```

**If it DOES exist:** skip the question. The script reads the config automatically.

To override the browser for a single run, pass `-browser <name>` to the script (ephemeral, does not update config).

## Step 2: Get the PR number or branch name

The user can provide either:
- A **PR number** (e.g., `6498` from `ROCm/rocm-libraries/pull/6498`)
- A **branch name** (e.g., `ck/user/feature-name`)

The user may also provide a full Jenkins URL like:
- PR: `http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/view/change-requests/job/PR-6498/`
- Branch: `http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/job/ck%252Fuser%252Ffeature/`

Extract the PR number or branch name from the URL. For branch URLs, decode `%252F` → `/`.

If neither is provided, ask the user what they want to build.

## Step 3: List available parameters and let the user choose

Once you have the PR number, **always run `-list-params` first** to show what options are
available. This lets the user decide which toggles to change before triggering.

```bash
bash <skill-dir>/scripts/ci-build.sh -pr <PR_NUMBER> -list-params
# or
bash <skill-dir>/scripts/ci-build.sh -branch <BRANCH_NAME> -list-params
```

Present the parameter list to the user and ask which ones they want to override (if any).
Use AskUserQuestion with common toggles as options if appropriate, or let them specify freely.
If the user already specified options in their request, skip the question and proceed directly.

## Step 4: Run the script

```bash
bash <skill-dir>/scripts/ci-build.sh (-pr <PR_NUMBER> | -branch <BRANCH_NAME>) [-option KEY=VALUE]... [-dry-run] [-list-params]
```

Arguments:
- `-pr <N>`: The PR number
- `-branch <name>`: The branch name (e.g., `ck/user/feature`)
- Exactly one of `-pr` or `-branch` is required
- `-option KEY=VALUE` (repeatable): Override a build parameter. Booleans accept ON/OFF/true/false/1/0
- `-dry-run`: Show what would happen without actually triggering
- `-list-params`: List all available build parameters with defaults and exit
- `-browser <name>`: Override browser for this run (msedge, chrome, firefox, webkit). Does not update saved config.

Common parameter overrides:
- `RUN_CK_TILE_FMHA_TESTS=ON` — Enable FMHA tests
- `RUN_AITER_TESTS=ON` — Enable AITER tests
- `RUN_FA_TESTS=ON` — Enable Flash Attention tests
- `RUN_PYTORCH_TESTS=ON` — Enable PyTorch tests
- `BUILD_GFX942=OFF` — Disable gfx942 build
- `RUN_FULL_QA=ON` — Run full QA test suite

## How the script works

The script operates in two phases:

**Phase 1 — curl (fast, no browser):**
- Verifies the PR exists on Jenkins via API
- Checks if a build is currently in progress (prompts user to confirm if so)
- Lists parameters if `-list-params` is used
- Exits early for `-dry-run`

**Phase 2 — playwright-cli (browser automation):**
- Opens the configured browser with a persistent profile (SSO session is reused)
- Detects whether the page shows "Build Now" (first build) or "Build with Parameters"
- Applies parameter overrides by manipulating the Jenkins form DOM
- Clicks the Build button to trigger

## Step 5: Report the result

After the script runs, tell the user:

- Whether the build was triggered successfully
- Which parameters were overridden (if any)
- The Jenkins URL to view the build

If the script fails, check common issues:
- **Kerberos auth**: User may need to run `kinit`
- **PR not found**: Double-check the PR number
- **Login required**: On first run, the browser may need manual login — this is a one-time setup since the profile is persistent

## Notes

- Jenkins URL patterns:
  - PR: `http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/job/PR-<N>/`
  - Branch: `http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/job/<encoded-branch>/`
  - Branch names have `/` encoded as `%2F`, then double-encoded in URLs as `%252F`
- First builds use the "Build Now" button (no parameters available in Jenkins UI)
- Subsequent builds use "Build with Parameters" with all options exposed
- The persistent browser profile is managed by `playwright-cli` (session `ck-ci`)
- Saved build parameters and browser preference are stored in `~/.claude/ck-ci-build/`
- Use `-browser <name>` to override the browser for a single run
- Use the companion `ck-ci-report` skill to check build results after triggering
