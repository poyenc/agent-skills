#!/bin/bash
# ck-ci-build.sh - Trigger Jenkins CI builds for Composable Kernel PRs or branches
#
# Uses curl for status checks + playwright-cli for triggering builds.
# No extra auth — curl uses Kerberos, playwright reuses your browser session.
#
# Usage:
#   ./ck-ci-build.sh -pr <PR_NUMBER> [-option KEY=VALUE]... [-dry-run] [-list-params]
#   ./ck-ci-build.sh -branch <BRANCH_NAME> [-option KEY=VALUE]... [-dry-run] [-list-params]
#
# Examples:
#   ./ck-ci-build.sh -pr 6498
#   ./ck-ci-build.sh -branch ck/user/feature
#   ./ck-ci-build.sh -pr 6498 -option RUN_CK_TILE_FMHA_TESTS=ON
#   ./ck-ci-build.sh -branch ck/user/feature -option RUN_CK_TILE_FMHA_TESTS=ON
#   ./ck-ci-build.sh -pr 6498 -dry-run
#   ./ck-ci-build.sh -pr 6498 -list-params
#   ./ck-ci-build.sh -pr 6498 -no-saved          # ignore saved settings, use defaults
#
# Parameter persistence:
#   When you trigger a build with -option flags, those settings are saved to
#   ~/.claude/ck-ci-build/saved-params-<ID>.conf. Next time you run without -option,
#   the saved settings are loaded automatically. Use -no-saved to ignore them.

set -euo pipefail

CURL="curl -sfg --negotiate -u :"
SESSION="ck-ci"
PW="playwright-cli -s=${SESSION}"

SAVED_DIR="${HOME}/.claude/ck-ci-build"
BROWSER="msedge"

# Load config (browser preference)
CONFIG_FILE="${SAVED_DIR}/config"
if [ -f "${CONFIG_FILE}" ]; then
    _cfg_browser=$(grep '^BROWSER=' "${CONFIG_FILE}" | head -1 | cut -d= -f2)
    [ -n "${_cfg_browser}" ] && BROWSER="${_cfg_browser}"
fi

PR=""
BRANCH=""
DRY_RUN=false
LIST_PARAMS=false
NO_SAVED=false
HAS_EXPLICIT_OPTIONS=false
declare -a OPTION_KEYS=()
declare -a OPTION_VALS=()

# ---------- Parse arguments ----------
usage() {
    cat <<EOF
Usage: $0 (-pr <PR_NUMBER> | -branch <BRANCH_NAME>) [-option KEY=VALUE]... [-dry-run] [-list-params]

Options:
  -pr <N>              PR number (e.g. 6498)
  -branch <name>       Branch name (e.g. ck/user/feature)
                       Exactly one of -pr or -branch is required
  -option KEY=VALUE    Override a build parameter (repeatable)
                       Booleans: ON/true/1 or OFF/false/0
  -dry-run             Show what would happen without triggering
  -list-params         List available build parameters and exit
  -no-saved            Ignore saved settings, use Jenkins defaults
  -browser <name>      Browser for playwright (msedge, chrome, firefox, webkit)
                       Overrides config for this run only
  -h, --help           Show this help
EOF
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -pr)
            PR="${2:?Error: -pr requires a PR number}"
            shift 2
            ;;
        -branch)
            BRANCH="${2:?Error: -branch requires a branch name}"
            shift 2
            ;;
        -option)
            kv="${2:?Error: -option requires KEY=VALUE}"
            key="${kv%%=*}"
            val="${kv#*=}"
            case "${val}" in
                ON|on|TRUE|1)   val="true" ;;
                OFF|off|FALSE|0) val="false" ;;
            esac
            OPTION_KEYS+=("${key}")
            OPTION_VALS+=("${val}")
            HAS_EXPLICIT_OPTIONS=true
            shift 2
            ;;
        -dry-run)
            DRY_RUN=true
            shift
            ;;
        -list-params)
            LIST_PARAMS=true
            shift
            ;;
        -no-saved)
            NO_SAVED=true
            shift
            ;;
        -browser)
            BROWSER="${2:?Error: -browser requires a browser name}"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Error: Unknown argument: $1" >&2
            usage
            ;;
    esac
done

if [ -z "${PR}" ] && [ -z "${BRANCH}" ]; then
    echo "Error: -pr or -branch is required" >&2
    usage
fi
if [ -n "${PR}" ] && [ -n "${BRANCH}" ]; then
    echo "Error: -pr and -branch are mutually exclusive" >&2
    usage
fi

if [ -n "${PR}" ]; then
    JOB_NAME="PR-${PR}"
    LABEL="PR #${PR}"
    FILE_ID="PR-${PR}"
else
    JOB_NAME=$(echo "${BRANCH}" | sed 's|/|%2F|g')
    LABEL="Branch: ${BRANCH}"
    FILE_ID=$(echo "${BRANCH}" | sed 's|/|__|g')
fi

URL_ENCODED_JOB=$(echo "${JOB_NAME}" | sed 's|%2F|%252F|g')
JOB_URL="http://micimaster.amd.com/job/rocm-libraries-folder/job/Composable%20Kernel/job/${URL_ENCODED_JOB}"
SAVED_FILE="${SAVED_DIR}/saved-params-${FILE_ID}.conf"

# ---------- Load saved parameters ----------
if [ "${HAS_EXPLICIT_OPTIONS}" = false ] && [ "${NO_SAVED}" = false ] && [ -f "${SAVED_FILE}" ]; then
    echo "Loading saved settings from ${SAVED_FILE}..." >&2
    while IFS='=' read -r key val; do
        [ -z "${key}" ] && continue
        [[ "${key}" =~ ^# ]] && continue
        OPTION_KEYS+=("${key}")
        OPTION_VALS+=("${val}")
    done < "${SAVED_FILE}"
    if [ ${#OPTION_KEYS[@]} -gt 0 ]; then
        echo "  Loaded ${#OPTION_KEYS[@]} saved parameter(s):" >&2
        for i in "${!OPTION_KEYS[@]}"; do
            echo "    ${OPTION_KEYS[$i]} = ${OPTION_VALS[$i]}" >&2
        done
        echo "  (use -no-saved to ignore, or -option to override)" >&2
    fi
fi

# ============================================================
# Phase 1: curl — status checks (fast, no browser)
# ============================================================

echo "Checking ${LABEL}..." >&2
JOB_JSON=$(${CURL} "${JOB_URL}/api/json?tree=lastBuild[number,result,building,timestamp],property[parameterDefinitions[name,type,defaultParameterValue[value],description,choices]]" 2>/dev/null || echo "")

if [ -z "${JOB_JSON}" ]; then
    echo "Error: Could not reach Jenkins job for ${LABEL}." >&2
    echo "  Check that the PR exists and you have Kerberos auth (kinit)." >&2
    exit 1
fi

eval "$(echo "${JOB_JSON}" | python3 -c "
import json, sys, datetime
d = json.load(sys.stdin)
lb = d.get('lastBuild')
if lb:
    print('HAS_BUILDS=yes')
    print(f'LAST_BUILD_NUM={lb[\"number\"]}')
    print(f'LAST_BUILD_RESULT={lb.get(\"result\") or \"IN_PROGRESS\"}')
    print(f'LAST_BUILD_BUILDING={str(lb.get(\"building\", False)).lower()}')
    ts = lb.get('timestamp', 0)
    dt = datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc)
    print(f'LAST_BUILD_TIME=\"{dt.strftime(\"%Y-%m-%d %H:%M:%S UTC\")}\"')
else:
    print('HAS_BUILDS=no')
    print('LAST_BUILD_NUM=')
    print('LAST_BUILD_RESULT=')
    print('LAST_BUILD_BUILDING=false')
    print('LAST_BUILD_TIME=')
")"

echo "  Last build: ${LAST_BUILD_NUM:-none} (${LAST_BUILD_RESULT:-n/a})" >&2

# ---------- List parameters (curl-only, exit early) ----------
if [ "${LIST_PARAMS}" = true ]; then
    if [ "${HAS_BUILDS}" = "no" ]; then
        echo "${LABEL} has no prior builds. Parameters not available until after the first build." >&2
        exit 0
    fi
    echo ""
    echo "Available parameters for ${LABEL}:"
    echo "-----------------------------------"
    echo "${JOB_JSON}" | python3 -c "
import json, sys
data = json.load(sys.stdin)
params = []
for prop in data.get('property', []):
    defs = prop.get('parameterDefinitions', [])
    if defs:
        params.extend(defs)
if not params:
    print('(no parameters defined)')
    sys.exit(0)
for p in params:
    name = p.get('name', '?')
    ptype = p.get('type', '?')
    default = p.get('defaultParameterValue', {}).get('value', '')
    desc = p.get('description', '')
    choices = p.get('choices', [])
    if 'Boolean' in ptype: tl = 'boolean'
    elif 'Choice' in ptype: tl = 'choice'
    elif 'String' in ptype or 'Text' in ptype: tl = 'string'
    else: tl = ptype
    line = f'  {name}={default}  [{tl}]'
    if choices: line += f'  choices: {choices}'
    if desc: line += f'  # {desc}'
    print(line)
"
    exit 0
fi

# ---------- Check for in-progress build ----------
if [ "${LAST_BUILD_BUILDING}" = "true" ]; then
    echo "" >&2
    echo "WARNING: Build #${LAST_BUILD_NUM} is currently in progress (started ${LAST_BUILD_TIME})." >&2
    read -rp "A build is already running. Trigger a new build anyway? (y/N): " ANSWER
    if [[ ! "${ANSWER}" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        echo "Aborted. No build was triggered." >&2
        exit 0
    fi
fi

# ---------- Show what will happen ----------
echo "" >&2
if [ "${HAS_BUILDS}" = "no" ]; then
    echo "=== First Build (Build Now) ===" >&2
    echo "  ${LABEL}" >&2
    if [ ${#OPTION_KEYS[@]} -gt 0 ]; then
        echo "  Note: First build has no parameter form. -option flags ignored." >&2
        echo "        Re-run with -option after this build completes." >&2
    fi
else
    echo "=== Build with Parameters ===" >&2
    echo "  ${LABEL}" >&2
    if [ ${#OPTION_KEYS[@]} -gt 0 ]; then
        echo "  Overrides:" >&2
        for i in "${!OPTION_KEYS[@]}"; do
            echo "    ${OPTION_KEYS[$i]} = ${OPTION_VALS[$i]}" >&2
        done
    else
        echo "  Params: (using defaults)" >&2
    fi
fi

if [ "${DRY_RUN}" = true ]; then
    echo "" >&2
    echo "[DRY RUN] No build was triggered." >&2
    exit 0
fi

# ============================================================
# Phase 2: playwright-cli — open browser, click, fill, submit
# ============================================================

cleanup() {
    ${PW} close 2>/dev/null || true
}
trap cleanup EXIT

echo "" >&2
echo "Opening browser..." >&2
${PW} open "${JOB_URL}/" --browser=${BROWSER} --persistent > /dev/null 2>&1

# Check for login redirect
PAGE_URL=$(${PW} --raw eval "location.href")
if echo "${PAGE_URL}" | grep -qi 'login'; then
    echo "Login page detected. Please log in in the browser window..." >&2
    for i in $(seq 1 120); do
        sleep 1
        PAGE_URL=$(${PW} --raw eval "location.href" 2>/dev/null || echo "login")
        echo "${PAGE_URL}" | grep -qi 'login' || break
    done
    ${PW} goto "${JOB_URL}/" > /dev/null 2>&1
fi

# Get snapshot to find build links
SNAPSHOT=$(${PW} --raw snapshot 2>/dev/null)

BUILD_WITH_PARAMS_REF=$(echo "${SNAPSHOT}" | grep -i 'Build with Parameters' | grep -oE 'ref=[a-z0-9]+' | head -1 | cut -d= -f2 || echo "")
BUILD_NOW_REF=$(echo "${SNAPSHOT}" | grep -i 'Build Now' | grep -oE 'ref=[a-z0-9]+' | head -1 | cut -d= -f2 || echo "")

# ---------- Build with Parameters ----------
if [ -n "${BUILD_WITH_PARAMS_REF}" ]; then
    echo "Clicking \"Build with Parameters\"..." >&2
    ${PW} click "${BUILD_WITH_PARAMS_REF}" > /dev/null 2>&1
    sleep 2

    # Apply parameter overrides via inline JS eval
    for i in "${!OPTION_KEYS[@]}"; do
        key="${OPTION_KEYS[$i]}"
        val="${OPTION_VALS[$i]}"
        is_bool="false"
        if [ "${val}" = "true" ] || [ "${val}" = "false" ]; then
            is_bool="true"
        fi

        RESULT=$(${PW} --raw eval "(function(){var ni=document.querySelectorAll('input[type=\"hidden\"][name=\"name\"]');for(var i=0;i<ni.length;i++){if(ni[i].value!=='${key}')continue;var c=ni[i].closest('.jenkins-form-item,.setting-main,tr,div[name=\"parameter\"]')||ni[i].parentElement;var cb=c.querySelector('input[type=\"checkbox\"][name=\"value\"]');if(cb){var want=(${val}===true||'${val}'==='true');if(cb.checked!==want)cb.click();return'ok';}var sel=c.querySelector('select[name=\"value\"]');if(sel){sel.value='${val}';sel.dispatchEvent(new Event('change',{bubbles:true}));return'ok';}var ta=c.querySelector('textarea[name=\"value\"]');if(ta){ta.value='${val}';ta.dispatchEvent(new Event('input',{bubbles:true}));return'ok';}var t=c.querySelector('input[name=\"value\"]');if(t){t.value='${val}';t.dispatchEvent(new Event('input',{bubbles:true}));return'ok';}return'no_input';}return'notfound';})()" 2>/dev/null || echo "error")

        # Strip quotes from result
        RESULT=$(echo "${RESULT}" | tr -d '"')

        if [ "${RESULT}" = "ok" ]; then
            echo "  Set ${key} = ${val}" >&2
        else
            echo "  WARNING: '${key}' not found on form (${RESULT}). Skipped." >&2
        fi
    done

    # Click Build button
    echo "Clicking \"Build\"..." >&2
    FORM_SNAPSHOT=$(${PW} --raw snapshot 2>/dev/null)
    BUILD_BTN_REF=$(echo "${FORM_SNAPSHOT}" | grep -iE 'button "Build"' | grep -oE 'ref=[a-z0-9]+' | head -1 | cut -d= -f2 || echo "")

    if [ -n "${BUILD_BTN_REF}" ]; then
        ${PW} click "${BUILD_BTN_REF}" > /dev/null 2>&1
    else
        ${PW} eval "document.querySelector('button[name=\"Submit\"],button.jenkins-button--primary,input[type=\"submit\"]').click()" > /dev/null 2>&1
    fi

# ---------- Build Now (first build) ----------
elif [ -n "${BUILD_NOW_REF}" ]; then
    echo "Clicking \"Build Now\"..." >&2
    ${PW} click "${BUILD_NOW_REF}" > /dev/null 2>&1

# ---------- No build link ----------
else
    echo "Error: No build link found on the page." >&2
    echo "Snapshot:" >&2
    echo "${SNAPSHOT}" | head -30 >&2
    exit 1
fi

sleep 2
echo "" >&2
echo "Build triggered successfully!" >&2
echo "View at: ${JOB_URL}/" >&2

# ---------- Save parameters for next run ----------
if [ ${#OPTION_KEYS[@]} -gt 0 ] && [ "${HAS_EXPLICIT_OPTIONS}" = true ]; then
    mkdir -p "${SAVED_DIR}"
    {
        echo "# Saved parameters for ${LABEL} ($(date '+%Y-%m-%d %H:%M'))"
        for i in "${!OPTION_KEYS[@]}"; do
            echo "${OPTION_KEYS[$i]}=${OPTION_VALS[$i]}"
        done
    } > "${SAVED_FILE}"
    echo "Settings saved to ${SAVED_FILE}" >&2
fi
