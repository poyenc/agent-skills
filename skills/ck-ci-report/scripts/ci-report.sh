#!/bin/bash
# ci-report.sh - Analyze Jenkins CI build failures for Composable Kernel PRs/branches
# Usage: ci-report.sh <PR_NUMBER_OR_BRANCH> [BUILD_SELECTOR]
#   PR_NUMBER_OR_BRANCH: PR number (e.g. 6983) or branch name (e.g. ck/user/feature)
#   BUILD_SELECTOR: "lastBuild" (default), "lastFailedBuild", or a build number like "4"
#
# Output: prints a markdown report to stdout, saves stage log to ${CLAUDE_CODE_TMPDIR:-/tmp}/ci-stage-log-<ID>.txt
#
# Uses Blue Ocean REST API for structured stage/step/log data instead of parsing
# the full consoleText. The consoleText is downloaded in background as a saved artifact only.

set -euo pipefail

INPUT="${1:?Usage: ci-report.sh <PR_NUMBER_OR_BRANCH> [BUILD_SELECTOR]}"
BUILD="${2:-lastBuild}"
CURL="curl -sfg --negotiate -u :"

if [[ "${INPUT}" =~ ^[0-9]+$ ]]; then
    MODE="pr"
    PR="${INPUT}"
    JOB_NAME="PR-${PR}"
    BO_BRANCH="PR-${PR}"
    LABEL="PR #${PR}"
    FILE_ID="PR-${PR}"
else
    MODE="branch"
    BRANCH="${INPUT}"
    JOB_NAME=$(echo "${BRANCH}" | sed 's|/|%2F|g')
    BO_BRANCH="${JOB_NAME}"
    LABEL="Branch: ${BRANCH}"
    FILE_ID=$(echo "${BRANCH}" | sed 's|/|__|g')
fi

URL_ENCODED_JOB=$(echo "${JOB_NAME}" | sed 's|%2F|%252F|g')
BASE="http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/job/${URL_ENCODED_JOB}"
_tmp="${CLAUDE_CODE_TMPDIR:-/tmp}"
CONSOLE="${_tmp}/ci-console-${FILE_ID}.txt"
REPORT="${_tmp}/ci-report-${FILE_ID}.md"
STAGE_LOG="${_tmp}/ci-stage-log-${FILE_ID}.txt"
STAGE_ERRORS="${_tmp}/ci-stage-errors-${FILE_ID}.txt"

# ---------- 1. Get build metadata ----------
echo "Fetching ${LABEL} build ${BUILD}..." >&2
BUILD_JSON=$(${CURL} "${BASE}/${BUILD}/api/json?tree=number,result,timestamp" 2>/dev/null || echo "")

if [ -z "${BUILD_JSON}" ]; then
    echo "No builds found." >&2
    {
        echo "## CI Report: ${LABEL}"
        echo "**Result:** NO BUILDS"
        echo ""
        echo "No CI builds found. The build may not have been triggered yet."
    } > "${REPORT}"
    echo "Report saved to: ${REPORT}" >&2
    cat "${REPORT}"
    exit 0
fi

BUILD_VARS="${_tmp}/ci-build-vars-${FILE_ID}.sh"
python3 - "${BUILD_JSON}" "${BUILD_VARS}" <<'PYEOF'
import json, sys, datetime
d = json.loads(sys.argv[1])
ts = d.get('timestamp', 0)
dt = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc)
out = open(sys.argv[2], 'w')
out.write(f'BUILD_NUM={d["number"]}\n')
out.write(f'BUILD_RESULT={d.get("result") or ""}\n')
out.write(f'BUILD_TIMESTAMP="{dt.strftime("%Y-%m-%d  %H:%M:%S")}"\n')
PYEOF
source "${BUILD_VARS}"

echo "Build #${BUILD_NUM} (${BUILD_RESULT:-in progress})." >&2

# ---------- 2. Handle IN PROGRESS ----------
if [ -z "${BUILD_RESULT}" ]; then
    # Build is still running — gather stage progress from Blue Ocean API
    BO_URL_BRANCH=$(echo "${BO_BRANCH}" | sed 's|%2F|%252F|g')
    BO_BASE="http://micimaster.amd.com/blue/rest/organizations/jenkins/pipelines/rocm-libraries-folder/pipelines/Composable%20Kernel/branches/${BO_URL_BRANCH}/runs/${BUILD_NUM}"
    BO_NODES_RAW="${_tmp}/ci-nodes-${FILE_ID}.json"
    ${CURL} "${BO_BASE}/nodes/?limit=200" > "${BO_NODES_RAW}" 2>/dev/null || echo "[]" > "${BO_NODES_RAW}"

    PROGRESS=$(python3 - "${BO_NODES_RAW}" <<'PYEOF'
import json, sys
nodes = json.load(open(sys.argv[1]))
running = [n for n in nodes if n.get('state') == 'RUNNING']
finished = [n for n in nodes if n.get('state') == 'FINISHED']
queued = [n for n in nodes if n.get('state') in ('QUEUED', 'NOT_BUILT', None)]
total = len(nodes)
if running:
    names = ', '.join(n['displayName'] for n in running)
    print(f'RUNNING_STAGES="{names}"')
else:
    print('RUNNING_STAGES=""')
print(f'FINISHED_COUNT={len(finished)}')
print(f'TOTAL_COUNT={total}')
PYEOF
    )
    eval "${PROGRESS}"

    {
        echo "## CI Report: ${LABEL} (Build #${BUILD_NUM})"
        echo "**Result:** IN PROGRESS"
        echo "**Build at:** ${BUILD_TIMESTAMP}"
        echo ""
        if [ -n "${RUNNING_STAGES}" ]; then
            echo "**Currently running:** ${RUNNING_STAGES}"
        else
            echo "**Status:** Build is starting up (no stages running yet)"
        fi
        echo "**Progress:** ${FINISHED_COUNT}/${TOTAL_COUNT} stages completed"
    } > "${REPORT}"
    echo "Report saved to: ${REPORT}" >&2
    cat "${REPORT}"
    exit 0
fi

# ---------- 2b. Handle SUCCESS ----------
if [ "${BUILD_RESULT}" = "SUCCESS" ]; then
    {
        echo "## CI Report: ${LABEL} (Build #${BUILD_NUM})"
        echo "**Result:** SUCCESS"
        echo "**Build at:** ${BUILD_TIMESTAMP}"
        echo ""
        echo "The latest build completed successfully. All stages passed."
    } > "${REPORT}"
    echo "Report saved to: ${REPORT}" >&2
    cat "${REPORT}"
    exit 0
fi

# ---------- 3. Get stage info from Blue Ocean API ----------
BO_URL_BRANCH=$(echo "${BO_BRANCH}" | sed 's|%2F|%252F|g')
BO_BASE="http://micimaster.amd.com/blue/rest/organizations/jenkins/pipelines/rocm-libraries-folder/pipelines/Composable%20Kernel/branches/${BO_URL_BRANCH}/runs/${BUILD_NUM}"

echo "Fetching stage info..." >&2
BO_NODES_RAW="${_tmp}/ci-nodes-${FILE_ID}.json"
${CURL} "${BO_BASE}/nodes/?limit=200" > "${BO_NODES_RAW}" 2>/dev/null || echo "[]" > "${BO_NODES_RAW}"

# Parse nodes: get failed stage, skipped stages
NODES_VARS="${_tmp}/ci-nodes-vars-${FILE_ID}.sh"
python3 - "${BO_NODES_RAW}" "${NODES_VARS}" <<'PYEOF'
import json, sys

nodes = json.load(open(sys.argv[1]))
out = open(sys.argv[2], 'w')
failed = [n for n in nodes if n.get('result') in ('FAILURE', 'ABORTED')]
skipped = [n for n in nodes if n.get('state') in ('SKIPPED', 'NOT_BUILT')]

if not failed:
    out.write('FAILING_STAGE=Unknown\nFAILED_NODE_ID=\nSKIP_COUNT=0\n')
    sys.exit(0)

# Among failed nodes with real build/test work (duration > 60s), pick the one with
# the shortest duration — it failed first, causing cascade aborts on the others.
real_failed = [n for n in failed if n.get('durationInMillis', 0) > 60000]
pick = min(real_failed, key=lambda n: n.get('durationInMillis', float('inf'))) if real_failed else failed[0]

out.write(f'FAILING_STAGE="{pick["displayName"]}"\n')
out.write(f'FAILED_NODE_ID={pick["id"]}\n')
out.write(f'SKIP_COUNT={len(skipped)}\n')
PYEOF
source "${NODES_VARS}"

# Extract skipped stages separately
SKIPPED_STAGES=$(python3 - "${BO_NODES_RAW}" <<'PYEOF'
import json, sys
nodes = json.load(open(sys.argv[1]))
for n in nodes:
    if n.get('state') in ('SKIPPED', 'NOT_BUILT'):
        print(f'  - {n["displayName"]}')
PYEOF
)

# ---------- 4. Get failed step details ----------
FAILED_STEP_ID=""
FAILED_STEP_DUR=""
STEP_NAME=""
IS_INFRA=false

if [ -n "${FAILED_NODE_ID}" ]; then
    echo "Failed stage: ${FAILING_STAGE} (node ${FAILED_NODE_ID})" >&2

    BO_STEPS_RAW="${_tmp}/ci-steps-${FILE_ID}.json"
    ${CURL} "${BO_BASE}/nodes/${FAILED_NODE_ID}/steps/?limit=200" > "${BO_STEPS_RAW}" 2>/dev/null || echo "[]" > "${BO_STEPS_RAW}"

    STEPS_VARS="${_tmp}/ci-steps-vars-${FILE_ID}.sh"
    python3 - "${BO_STEPS_RAW}" "${STEPS_VARS}" <<'PYEOF'
import json, sys

steps = json.load(open(sys.argv[1]))
out = open(sys.argv[2], 'w')
shell_failed = [s for s in steps if s.get('result') in ('FAILURE', 'ABORTED') and s.get('displayName') == 'Shell Script']
any_failed = [s for s in steps if s.get('result') in ('FAILURE', 'ABORTED')]

if shell_failed:
    s = shell_failed[0]
elif any_failed:
    s = any_failed[0]
    out.write('IS_INFRA=true\n')
else:
    out.write('FAILED_STEP_ID=\nFAILED_STEP_DUR=\nSTEP_NAME=\n')
    sys.exit(0)

ms = s.get('durationInMillis', 0)
if ms > 3600000:
    dur = f'{round(ms / 3600000)}hr'
elif ms > 60000:
    dur = f'{round(ms / 60000)}min'
else:
    dur = f'{round(ms / 1000)}s'

out.write(f'FAILED_STEP_ID={s["id"]}\n')
out.write(f'FAILED_STEP_DUR={dur}\n')
out.write(f'STEP_NAME="{s["displayName"]}"\n')
PYEOF
    source "${STEPS_VARS}"
fi

# ---------- 5. Get the failed step's log ----------
KEY_EXCEPTION=""
if [ -n "${FAILED_STEP_ID}" ]; then
    echo "Failed step: ${STEP_NAME} ${FAILED_STEP_ID} (${FAILED_STEP_DUR})" >&2
    ${CURL} "${BO_BASE}/nodes/${FAILED_NODE_ID}/steps/${FAILED_STEP_ID}/log/" > "${STAGE_LOG}" 2>/dev/null || true

    # Extract key exceptions from the step log
    KEY_EXCEPTION=$(grep -i 'HttpException\|AbortException\|IOException\|FlowInterruptedException\|RuntimeException\|CompilationFailedException\|CMake Error\|make.*Error\|ninja.*error\|FAILED:' \
        "${STAGE_LOG}" \
        | grep -v '^\s*at ' \
        | head -5 || echo "")

    # Detect infra from exception content
    if [ -n "${KEY_EXCEPTION}" ]; then
        echo "${KEY_EXCEPTION}" | grep -qi 'HttpException\|credential\|token\|forbids access\|GitHub' && IS_INFRA=true
    fi
fi

# ---------- 6. Generate report ----------
{
    echo "## CI Report: ${LABEL} (Build #${BUILD_NUM})"
    echo "**Failed stage:** ${FAILING_STAGE}"

    if [ "${IS_INFRA}" = true ]; then
        echo "**Category:** Infrastructure/credential issue"
    fi

    echo "**Build at:** ${BUILD_TIMESTAMP}"
    echo ""

    # Root cause from step log
    if [ -n "${KEY_EXCEPTION}" ]; then
        echo "### Root Cause"
        echo '```'
        echo "${KEY_EXCEPTION}"
        echo '```'
        echo ""
    fi

    if [ "${SKIP_COUNT}" -gt 0 ]; then
        echo "### Skipped Stages (${SKIP_COUNT} stages skipped due to earlier failure)"
        echo "${SKIPPED_STAGES}"
        echo ""
    fi
} > "${REPORT}"

# ---------- 7. Deep dive into stage log (for non-infra failures) ----------
if [ -n "${FAILED_STEP_ID}" ] && [ "${IS_INFRA}" = false ] && [ -f "${STAGE_LOG}" ]; then
    STAGE_LINES=$(wc -l < "${STAGE_LOG}" 2>/dev/null | tr -d ' ')

    grep -n -i 'error[: !]\|\[  FAILED  \]\|fatal error\|undefined reference\|FAILED:\|segfault\|signal [0-9]' "${STAGE_LOG}" \
        | grep -v 'build errors in the future' \
        | head -30 \
        > "${STAGE_ERRORS}" 2>/dev/null || true

    STAGE_ERROR_COUNT=$(wc -l < "${STAGE_ERRORS}" 2>/dev/null | tr -d ' ')

    GTEST_PASSED=$(grep -oE '\[  PASSED  \] [0-9]+ test' "${STAGE_LOG}" | grep -oE '[0-9]+' | head -1 || echo "")
    GTEST_FAILED=$(grep -oE '[0-9]+ FAILED TEST' "${STAGE_LOG}" | grep -oE '[0-9]+' | head -1 || echo "")
    CTEST_FAILED=$(grep -oE 'The following tests FAILED:' "${STAGE_LOG}" | head -1 || echo "")

    {
        echo "### Stage Log Analysis"
        echo "**Failed stage:** ${FAILING_STAGE}"
        echo "**Failed step:** ${STEP_NAME} (${FAILED_STEP_DUR})"
        echo "**Log file:** ${STAGE_LOG}"
        echo "**Log lines:** ${STAGE_LINES}"
        if [ -n "${GTEST_PASSED}" ] || [ -n "${GTEST_FAILED}" ]; then
            echo "**GTest Results:** ${GTEST_PASSED:-0} passed, ${GTEST_FAILED:-0} failed"
        fi
        if [ -n "${CTEST_FAILED}" ]; then
            echo ""
            echo "#### CTest Failures"
            echo '```'
            grep -A 50 'The following tests FAILED:' "${STAGE_LOG}" | head -30
            echo '```'
        fi
        echo ""

        if [ "${STAGE_ERROR_COUNT}" -gt 0 ]; then
            echo "#### Error Lines (${STAGE_ERROR_COUNT} matches)"
            echo '```'
            cat "${STAGE_ERRORS}"
            echo '```'
        else
            echo "No error patterns found in this step's log."
        fi

        echo ""
        echo "#### Log Tail (last 20 lines)"
        echo '```'
        tail -20 "${STAGE_LOG}"
        echo '```'
    } >> "${REPORT}"

    echo "Stage log saved to: ${STAGE_LOG}" >&2
fi

# ---------- 8. Download full console in background (saved artifact only) ----------
${CURL} "${BASE}/${BUILD_NUM}/consoleText" > "${CONSOLE}" 2>/dev/null &
CONSOLE_PID=$!

# ---------- 9. Output report ----------
echo "========================================" >&2
echo "Report saved to: ${REPORT}" >&2
if [ -f "${STAGE_LOG}" ] && [ -s "${STAGE_LOG}" ]; then
    echo "Stage log saved to: ${STAGE_LOG}" >&2
fi
echo "Console downloading in background (PID ${CONSOLE_PID}) to: ${CONSOLE}" >&2
echo "========================================" >&2
echo "" >&2

cat "${REPORT}"
