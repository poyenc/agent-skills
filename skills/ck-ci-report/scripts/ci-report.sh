#!/bin/bash
# ci-report.sh - Analyze Jenkins CI build failures for Composable Kernel PRs
# Usage: ci-report.sh <PR_NUMBER> [BUILD_SELECTOR]
#   PR_NUMBER: the PR number (e.g. 6983)
#   BUILD_SELECTOR: "lastBuild" (default), "lastFailedBuild", or a build number like "4"
#
# Output: prints a markdown report to stdout, saves full console to /tmp/ci-console-PR-<N>.txt
#
# Optimizations over naive approach:
#   - Single browser session reused for both console extraction and Blue Ocean API deep dive
#   - No sleep waits between page navigations
#   - Blue Ocean REST API for structured stage/step/log access (no DOM heuristics)

set -euo pipefail

PR="${1:?Usage: ci-report.sh <PR_NUMBER> [BUILD_SELECTOR]}"
BUILD="${2:-lastBuild}"
BASE="http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/view/change-requests/job/PR-${PR}"
SESSION="ci-${PR}-$$"
CONSOLE_RAW="/tmp/ci-console-raw-PR-${PR}.txt"
CONSOLE="/tmp/ci-console-PR-${PR}.txt"
REPORT="/tmp/ci-report-PR-${PR}.md"
STAGE_LOG="/tmp/ci-stage-log-${PR}.txt"
STAGE_ERRORS="/tmp/ci-stage-errors-${PR}.txt"

cleanup() {
    playwright-cli -s="${SESSION}" close 2>/dev/null || true
}
trap cleanup EXIT

# ---------- 1. Open browser and navigate to console output ----------
echo "Opening PR-${PR} build ${BUILD} console..." >&2
playwright-cli -s="${SESSION}" open --browser=msedge \
    "${BASE}/${BUILD}/console" >/dev/null 2>&1

# ---------- 2. Check page loaded correctly ----------
PAGE_TITLE=$(playwright-cli -s="${SESSION}" --raw eval "document.title" 2>/dev/null || echo '"Error"')

if echo "${PAGE_TITLE}" | grep -qi "Error\|404\|not found\|Problem"; then
    playwright-cli -s="${SESSION}" close 2>/dev/null || true
    trap - EXIT
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

# ---------- 3. Extract build number and console text ----------
BUILD_NUM=$(echo "${PAGE_TITLE}" | sed -n 's/.*#\([0-9]*\).*/\1/p' | head -1)
BUILD_NUM="${BUILD_NUM:-unknown}"
echo "Build #${BUILD_NUM}. Extracting console..." >&2

playwright-cli -s="${SESSION}" --raw eval \
    "document.querySelector('pre.console-output')?.textContent || ''" \
    > "${CONSOLE_RAW}" 2>/dev/null

node -e "
var fs = require('fs');
var raw = fs.readFileSync(process.argv[1], 'utf8').trim();
try { fs.writeFileSync(process.argv[2], JSON.parse(raw)); }
catch(e) { fs.writeFileSync(process.argv[2], raw); }
" -- "${CONSOLE_RAW}" "${CONSOLE}"

# NOTE: Browser session kept open for Phase 2 deep dive (no close here)
echo "Processing log..." >&2

# ---------- 4. Analyze the console log ----------
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

FIRST_ERROR_LINE=$(grep -n -i 'throwing error exception for the stage\|Exception occurred:\|FAILED:\|CMake Error\|make.*Error\|ninja.*error' \
    "${CONSOLE}" | head -1 | cut -d: -f1 || echo "")
FAILING_STAGE=""
if [ -n "${FIRST_ERROR_LINE}" ]; then
    FAILING_STAGE=$(head -n "${FIRST_ERROR_LINE}" "${CONSOLE}" \
        | grep -o 'Stage "[^"]*"' \
        | tail -1 \
        | sed 's/Stage "//;s/"//' || echo "")
    if [ -z "${FAILING_STAGE}" ]; then
        FAILING_STAGE=$(head -n "${FIRST_ERROR_LINE}" "${CONSOLE}" \
            | grep '\[Pipeline\] stage' \
            | grep -v 'hide' \
            | tail -1 \
            | sed 's/.*stage (\(.*\))/\1/' || echo "")
    fi
fi
if [ -z "${FAILING_STAGE}" ] && [ -n "${FIRST_ERROR_LINE}" ]; then
    SEARCH_END=$((FIRST_ERROR_LINE + 20))
    FAILING_STAGE=$(sed -n "${FIRST_ERROR_LINE},${SEARCH_END}p" "${CONSOLE}" \
        | grep -o 'Failed in branch .*' \
        | head -1 \
        | sed 's/Failed in branch //' || echo "")
fi
FAILING_STAGE="${FAILING_STAGE:-Unknown}"

tail -50 "${CONSOLE}" > /tmp/ci-tail-${PR}.txt 2>/dev/null || true

# ---------- 5. Detect success vs failure ----------
IS_SUCCESS=false
if echo "${RESULT_LINE}" | grep -qi 'SUCCESS'; then
    IS_SUCCESS=true
fi

BUILD_TIMESTAMP=$(echo "${RESULT_LINE}" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}  +[0-9]{2}:[0-9]{2}:[0-9]{2}' | head -1 || echo "")
if [ -z "${BUILD_TIMESTAMP}" ]; then
    BUILD_TIMESTAMP=$(grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}  +[0-9]{2}:[0-9]{2}:[0-9]{2}' "${CONSOLE}" | tail -1 || echo "Unknown")
fi

# ---------- 6. Generate report ----------
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

# ---------- 7. Deep dive via Blue Ocean REST API (reuses same browser session) ----------
IS_INFRA=false
if [ -n "${KEY_EXCEPTION}" ]; then
    echo "${KEY_EXCEPTION}" | grep -qi 'HttpException\|credential\|token\|forbids access\|GitHub' && IS_INFRA=true
fi

BO_BASE="http://micimaster.amd.com/blue/rest/organizations/jenkins/pipelines/rocm-libraries-folder/pipelines/Composable%20Kernel/branches/PR-${PR}/runs/${BUILD_NUM}"

if [ "${IS_SUCCESS}" = false ] && [ "${IS_INFRA}" = false ]; then
    echo "Deep dive via Blue Ocean API..." >&2

    # Step 1: Get nodes, find first FAILURE/ABORTED stage
    playwright-cli -s="${SESSION}" open --browser=msedge \
        "${BO_BASE}/nodes/?limit=200" >/dev/null 2>&1

    BO_NODES_RAW="${STAGE_LOG}.nodes.raw"
    playwright-cli -s="${SESSION}" --raw eval \
        "(document.querySelector('pre')||document.body).textContent" \
        > "${BO_NODES_RAW}" 2>/dev/null

    FAILED_NODE=$(node -e "
var fs = require('fs');
var raw = fs.readFileSync(process.argv[1], 'utf8').trim();
var stageName = process.argv[2] || '';
var nodes;
try { nodes = JSON.parse(JSON.parse(raw)); } catch(e) { nodes = JSON.parse(raw); }
var failed = nodes.filter(function(n) { return n.result === 'FAILURE' || n.result === 'ABORTED'; });
if (failed.length === 0) process.exit(0);
// Prefer the node matching the stage name identified from console analysis
var pick = failed[0];
if (stageName) {
    var match = failed.filter(function(n) { return n.displayName === stageName; });
    if (match.length > 0) pick = match[0];
}
console.log(pick.id + '|' + pick.displayName);
" -- "${BO_NODES_RAW}" "${FAILING_STAGE}" 2>/dev/null || echo "")

    FAILED_NODE_ID=$(echo "${FAILED_NODE}" | cut -d'|' -f1)
    FAILED_NODE_NAME=$(echo "${FAILED_NODE}" | cut -d'|' -f2-)

    if [ -n "${FAILED_NODE_ID}" ]; then
        echo "Failed stage: ${FAILED_NODE_NAME} (node ${FAILED_NODE_ID})" >&2

        # Step 2: Get steps, find first FAILURE/ABORTED Shell Script
        playwright-cli -s="${SESSION}" open --browser=msedge \
            "${BO_BASE}/nodes/${FAILED_NODE_ID}/steps/?limit=200" >/dev/null 2>&1

        BO_STEPS_RAW="${STAGE_LOG}.steps.raw"
        playwright-cli -s="${SESSION}" --raw eval \
            "(document.querySelector('pre')||document.body).textContent" \
            > "${BO_STEPS_RAW}" 2>/dev/null

        FAILED_STEP=$(node -e "
var fs = require('fs');
var raw = fs.readFileSync(process.argv[1], 'utf8').trim();
var steps;
try { steps = JSON.parse(JSON.parse(raw)); } catch(e) { steps = JSON.parse(raw); }
var failed = steps.filter(function(s) { return (s.result === 'FAILURE' || s.result === 'ABORTED') && s.displayName === 'Shell Script'; });
if (failed.length > 0) {
    var ms = failed[0].durationInMillis;
    var dur = ms > 3600000 ? Math.round(ms/3600000)+'hr' : ms > 60000 ? Math.round(ms/60000)+'min' : Math.round(ms/1000)+'s';
    console.log(failed[0].id + '|' + dur);
} else {
    var a = steps.filter(function(s) { return s.result === 'FAILURE' || s.result === 'ABORTED'; });
    if (a.length > 0) console.log(a[0].id + '|0s');
}
" -- "${BO_STEPS_RAW}" 2>/dev/null || echo "")

        FAILED_STEP_ID=$(echo "${FAILED_STEP}" | cut -d'|' -f1)
        FAILED_STEP_DUR=$(echo "${FAILED_STEP}" | cut -d'|' -f2)

        if [ -n "${FAILED_STEP_ID}" ]; then
            echo "Failed step: ${FAILED_STEP_ID} (${FAILED_STEP_DUR})" >&2

            # Step 3: Get the log
            playwright-cli -s="${SESSION}" open --browser=msedge \
                "${BO_BASE}/nodes/${FAILED_NODE_ID}/steps/${FAILED_STEP_ID}/log/" >/dev/null 2>&1

            playwright-cli -s="${SESSION}" --raw eval \
                "(document.querySelector('pre')||document.body).textContent" \
                > "${STAGE_LOG}.raw" 2>/dev/null

            node -e "
var fs = require('fs');
var raw = fs.readFileSync(process.argv[1], 'utf8').trim();
try { fs.writeFileSync(process.argv[2], JSON.parse(raw)); }
catch(e) { fs.writeFileSync(process.argv[2], raw); }
" -- "${STAGE_LOG}.raw" "${STAGE_LOG}" 2>/dev/null

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

# ---------- 8. Close browser and output report ----------
playwright-cli -s="${SESSION}" close 2>/dev/null || true
trap - EXIT

echo "========================================" >&2
echo "Report saved to: ${REPORT}" >&2
echo "Full console saved to: ${CONSOLE}" >&2
if [ -f "${STAGE_LOG}" ] && [ -s "${STAGE_LOG}" ]; then
    echo "Stage log saved to: ${STAGE_LOG}" >&2
fi
echo "========================================" >&2
echo "" >&2

cat "${REPORT}"
