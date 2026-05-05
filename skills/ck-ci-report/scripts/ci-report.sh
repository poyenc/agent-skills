#!/bin/bash
# ci-report.sh - Analyze Jenkins CI build failures for Composable Kernel PRs
# Usage: ci-report.sh <PR_NUMBER> [BUILD_SELECTOR]
#   PR_NUMBER: the PR number (e.g. 6983)
#   BUILD_SELECTOR: "lastBuild" (default), "lastFailedBuild", or a build number like "4"
#
# Output: prints a markdown report to stdout, saves full console to /tmp/ci-console-PR-<N>.txt
#
# Uses curl with Kerberos auth (--negotiate) instead of a browser for all HTTP requests.
# Jenkins consoleText endpoint returns plain text; Blue Ocean REST API returns JSON.

set -euo pipefail

PR="${1:?Usage: ci-report.sh <PR_NUMBER> [BUILD_SELECTOR]}"
BUILD="${2:-lastBuild}"
BASE="http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/view/change-requests/job/PR-${PR}"
CURL="curl -sf --negotiate -u :"
CONSOLE="/tmp/ci-console-PR-${PR}.txt"
REPORT="/tmp/ci-report-PR-${PR}.md"
STAGE_LOG="/tmp/ci-stage-log-${PR}.txt"
STAGE_ERRORS="/tmp/ci-stage-errors-${PR}.txt"

# ---------- 1. Get build metadata ----------
echo "Fetching PR-${PR} build ${BUILD}..." >&2
BUILD_JSON=$(${CURL} "${BASE}/${BUILD}/api/json?tree=number,result" 2>/dev/null || echo "")

if [ -z "${BUILD_JSON}" ]; then
    echo "No builds found." >&2
    {
        echo "## CI Report: PR #${PR}"
        echo "**Result:** NO BUILDS"
        echo ""
        echo "No CI builds found for this PR. The build may not have been triggered yet."
    } > "${REPORT}"
    echo "Report saved to: ${REPORT}" >&2
    cat "${REPORT}"
    exit 0
fi

BUILD_NUM=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['number'])" "${BUILD_JSON}" 2>/dev/null || echo "unknown")
BUILD_RESULT=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('result',''))" "${BUILD_JSON}" 2>/dev/null || echo "")
echo "Build #${BUILD_NUM} (${BUILD_RESULT:-in progress}). Fetching console..." >&2

# ---------- 2. Get console text ----------
${CURL} "${BASE}/${BUILD_NUM}/consoleText" > "${CONSOLE}" 2>/dev/null || {
    echo "Failed to fetch console text." >&2
    exit 1
}
echo "Processing log..." >&2

# ---------- 3. Analyze the console log ----------
RESULT_LINE=$(tail -5 "${CONSOLE}" | grep -i "Finished:" | tail -1 || echo "Unknown")

grep -n -i 'error\|exception\|FAILURE\|fatal\|abort' "${CONSOLE}" \
    | grep -v '^\s*at ' \
    | grep -v 'PluginClassLoader' \
    | grep -v 'java\.base/' \
    | grep -v 'jdk\.internal' \
    | grep -v 'groovy\.lang\.' \
    | grep -v 'org\.codehaus\.groovy' \
    | grep -v 'com\.cloudbees\.groovy' \
    | grep -v 'jenkins\.util\.' \
    | grep -v 'hudson\.remoting\.' \
    | grep -v 'java\.util\.concurrent' \
    | grep -v '\[Pipeline\] }' \
    | grep -v 'ErrorLoggingExecutorService' \
    | grep -v 'skipped due to earlier failure' \
    | grep -v 'build errors in the future' \
    | head -30 \
    > /tmp/ci-errors-${PR}.txt 2>/dev/null || true

grep 'skipped due to' "${CONSOLE}" \
    | sed 's/.*Stage "/  - /; s/" skipped.*//' \
    > /tmp/ci-skipped-${PR}.txt 2>/dev/null || true
SKIP_COUNT=$(wc -l < /tmp/ci-skipped-${PR}.txt | tr -d ' ')

KEY_EXCEPTION=$(grep -i 'HttpException\|AbortException\|IOException\|FlowInterruptedException\|RuntimeException\|CompilationFailedException\|CMake Error\|make.*Error\|ninja.*error\|FAILED:' \
    "${CONSOLE}" \
    | grep -v '^\s*at ' \
    | head -5 || echo "")

# Identify failing stage: "Failed in branch" is the authoritative signal for parallel stages.
# Fall back to "Stage ..." markers or "Exception occurred:" if no branch failure found.
FAILING_STAGE=""
# Primary: look for "Failed in branch" (always present for parallel stage failures)
FAILING_STAGE=$(grep -o 'Failed in branch .*' "${CONSOLE}" \
    | head -1 \
    | sed 's/Failed in branch //' || echo "")
# Fallback: find stage-level error markers (not build/test output)
if [ -z "${FAILING_STAGE}" ]; then
    FIRST_ERROR_LINE=$(grep -n -i 'throwing error exception for the stage\|throwing error exception while building CK\|Exception occurred:' \
        "${CONSOLE}" | head -1 | cut -d: -f1 || echo "")
    if [ -n "${FIRST_ERROR_LINE}" ]; then
        FAILING_STAGE=$(head -n "${FIRST_ERROR_LINE}" "${CONSOLE}" \
            | grep -o 'Stage "[^"]*"' \
            | tail -1 \
            | sed 's/Stage "//;s/"//' || echo "")
    fi
fi
FAILING_STAGE="${FAILING_STAGE:-Unknown}"

tail -50 "${CONSOLE}" > /tmp/ci-tail-${PR}.txt 2>/dev/null || true

# ---------- 4. Detect success vs failure ----------
IS_SUCCESS=false
if echo "${RESULT_LINE}" | grep -qi 'SUCCESS'; then
    IS_SUCCESS=true
fi

BUILD_TIMESTAMP=$(echo "${RESULT_LINE}" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}' | head -1 \
    | sed 's/T/  /' || echo "")
if [ -z "${BUILD_TIMESTAMP}" ]; then
    BUILD_TIMESTAMP=$(grep -oE '^\[?[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}' "${CONSOLE}" | tail -1 \
        | sed 's/^\[//;s/T/  /' || echo "Unknown")
fi

# ---------- 5. Generate report ----------
{
    if [ "${IS_SUCCESS}" = true ]; then
        echo "## CI Report: PR #${PR} (Build #${BUILD_NUM})"
        echo "**Result:** SUCCESS"
        echo "**Build at:** ${BUILD_TIMESTAMP}"
        echo ""
        echo "The latest build completed successfully. All stages passed."
    else
        echo "## CI Report: PR #${PR} (Build #${BUILD_NUM})"
        echo "**Failed stage:** ${FAILING_STAGE}"
        echo "**Category:** (see analysis below)"
        echo "**Build at:** ${BUILD_TIMESTAMP}"
        echo ""

        echo "### Root Cause"
        echo '```'
        if [ -n "${KEY_EXCEPTION}" ]; then
            echo "${KEY_EXCEPTION}"
        else
            cat /tmp/ci-errors-${PR}.txt 2>/dev/null | head -10
        fi
        echo '```'
        echo ""

        ERROR_COUNT=$(wc -l < /tmp/ci-errors-${PR}.txt 2>/dev/null | tr -d ' ')
        if [ "${ERROR_COUNT}" -gt 0 ]; then
            echo "### All Error Lines (${ERROR_COUNT} matches)"
            echo '```'
            cat /tmp/ci-errors-${PR}.txt
            echo '```'
            echo ""
        fi

        if [ "${SKIP_COUNT}" -gt 0 ]; then
            echo "### Skipped Stages (${SKIP_COUNT} stages skipped due to earlier failure)"
            cat /tmp/ci-skipped-${PR}.txt
            echo ""
        fi

        echo "### Console Tail (last 50 lines)"
        echo '```'
        cat /tmp/ci-tail-${PR}.txt
        echo '```'
    fi
} > "${REPORT}"

# ---------- 6. Deep dive via Blue Ocean REST API ----------
IS_INFRA=false
if [ -n "${KEY_EXCEPTION}" ]; then
    echo "${KEY_EXCEPTION}" | grep -qi 'HttpException\|credential\|token\|forbids access\|GitHub' && IS_INFRA=true
fi

BO_BASE="http://micimaster.amd.com/blue/rest/organizations/jenkins/pipelines/rocm-libraries-folder/pipelines/Composable%20Kernel/branches/PR-${PR}/runs/${BUILD_NUM}"

if [ "${IS_SUCCESS}" = false ] && [ "${IS_INFRA}" = false ]; then
    echo "Deep dive via Blue Ocean API..." >&2

    # Step 1: Get nodes, find FAILURE/ABORTED stage matching FAILING_STAGE
    BO_NODES_RAW="${STAGE_LOG}.nodes.raw"
    ${CURL} "${BO_BASE}/nodes/?limit=200" > "${BO_NODES_RAW}" 2>/dev/null || echo "[]" > "${BO_NODES_RAW}"

    FAILED_NODE=$(python3 -c "
import json, sys
nodes = json.load(open(sys.argv[1]))
stage = sys.argv[2] if len(sys.argv) > 2 else ''
failed = [n for n in nodes if n.get('result') in ('FAILURE', 'ABORTED')]
if not failed:
    sys.exit(0)
pick = failed[0]
if stage:
    match = [n for n in failed if n.get('displayName') == stage]
    if match:
        pick = match[0]
print(str(pick['id']) + '|' + pick['displayName'])
" "${BO_NODES_RAW}" "${FAILING_STAGE}" 2>/dev/null || echo "")

    FAILED_NODE_ID=$(echo "${FAILED_NODE}" | cut -d'|' -f1)
    FAILED_NODE_NAME=$(echo "${FAILED_NODE}" | cut -d'|' -f2-)

    if [ -n "${FAILED_NODE_ID}" ]; then
        echo "Failed stage: ${FAILED_NODE_NAME} (node ${FAILED_NODE_ID})" >&2

        # Step 2: Get steps, find first FAILURE/ABORTED Shell Script
        BO_STEPS_RAW="${STAGE_LOG}.steps.raw"
        ${CURL} "${BO_BASE}/nodes/${FAILED_NODE_ID}/steps/?limit=200" > "${BO_STEPS_RAW}" 2>/dev/null || echo "[]" > "${BO_STEPS_RAW}"

        FAILED_STEP=$(python3 -c "
import json, sys
steps = json.load(open(sys.argv[1]))
failed = [s for s in steps if s.get('result') in ('FAILURE', 'ABORTED') and s.get('displayName') == 'Shell Script']
if not failed:
    failed = [s for s in steps if s.get('result') in ('FAILURE', 'ABORTED')]
if not failed:
    sys.exit(0)
s = failed[0]
ms = s.get('durationInMillis', 0)
if ms > 3600000:
    dur = str(round(ms / 3600000)) + 'hr'
elif ms > 60000:
    dur = str(round(ms / 60000)) + 'min'
else:
    dur = str(round(ms / 1000)) + 's'
print(str(s['id']) + '|' + dur)
" "${BO_STEPS_RAW}" 2>/dev/null || echo "")

        FAILED_STEP_ID=$(echo "${FAILED_STEP}" | cut -d'|' -f1)
        FAILED_STEP_DUR=$(echo "${FAILED_STEP}" | cut -d'|' -f2)

        if [ -n "${FAILED_STEP_ID}" ]; then
            echo "Failed step: ${FAILED_STEP_ID} (${FAILED_STEP_DUR})" >&2

            # Step 3: Get the log
            ${CURL} "${BO_BASE}/nodes/${FAILED_NODE_ID}/steps/${FAILED_STEP_ID}/log/" > "${STAGE_LOG}" 2>/dev/null || true

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
                echo ""
                echo "### Stage Log Analysis"
                echo "**Failed stage:** ${FAILED_NODE_NAME}"
                echo "**Failed step:** Shell Script (${FAILED_STEP_DUR})"
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
        else
            echo "No failed Shell Script step found in node ${FAILED_NODE_ID}." >&2
        fi
    else
        echo "No FAILURE stage found via Blue Ocean API." >&2
    fi
fi

# ---------- 7. Output report ----------
echo "========================================" >&2
echo "Report saved to: ${REPORT}" >&2
echo "Full console saved to: ${CONSOLE}" >&2
if [ -f "${STAGE_LOG}" ] && [ -s "${STAGE_LOG}" ]; then
    echo "Stage log saved to: ${STAGE_LOG}" >&2
fi
echo "========================================" >&2
echo "" >&2

cat "${REPORT}"
