#!/usr/bin/env bash
set -euo pipefail

for cmd in yq gh jq; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "Error: $cmd is required but not found." >&2; exit 1; }
done

STATE_FILE=""
SUBCOMMAND=""
FULL_SCAN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --state-file) STATE_FILE="$2"; shift 2 ;;
        --full-scan) FULL_SCAN=true; shift ;;
        list-pending|commit-results) SUBCOMMAND="$1"; shift ;;
        *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -n "$STATE_FILE" ]] || { echo "Error: --state-file is required" >&2; exit 1; }
[[ -n "$SUBCOMMAND" ]] || { echo "Error: subcommand (list-pending|commit-results) is required" >&2; exit 1; }

# Fix 4: --full-scan is only valid with list-pending
if [[ "$FULL_SCAN" == "true" ]] && [[ "$SUBCOMMAND" == "commit-results" ]]; then
    echo "Error: --full-scan is only valid with list-pending" >&2
    exit 1
fi

REPO="ROCm/rocm-libraries"
LABEL="project: composablekernel"
FMHA_PATH_PATTERN="fmha|flash_attn|attention|block_fmha|mask_info"

fetch_open_prs() {
    local result
    result=$(gh api "repos/$REPO/pulls?state=open&per_page=100" --paginate 2>&1) \
        || { echo "Error: gh api failed: $result" >&2; exit 1; }
    echo "$result" \
    | jq -s 'add | [.[] | select(.labels[]?.name == "'"$LABEL"'") | {number, title, author: .user.login, url: .html_url, created_at}]'
}

filter_ambiguous_by_files() {
    local ambiguous_json="$1"
    local nums
    nums=$(echo "$ambiguous_json" | jq -r '.[].number')
    [[ -z "$nums" ]] && { echo "$ambiguous_json"; return; }

    local nums_array
    mapfile -t nums_array <<< "$nums"
    local fmha_nums="[]"

    # Batch 25 PRs per GraphQL request
    local i
    for ((i=0; i<${#nums_array[@]}; i+=25)); do
        local batch=("${nums_array[@]:i:25}")
        local query="query {"
        for n in "${batch[@]}"; do
            query+=" pr_${n}: repository(owner: \"ROCm\", name: \"rocm-libraries\") { pullRequest(number: ${n}) { number files(first: 100) { nodes { path } } } }"
        done
        query+=" }"

        local result
        result=$(gh api graphql -f query="$query" 2>&1) \
            || { echo "Error: gh api graphql failed: $result" >&2; exit 1; }

        local batch_fmha
        batch_fmha=$(echo "$result" | jq '[.data | to_entries[] | select(.value.pullRequest.files.nodes | map(.path) | map(test("'"$FMHA_PATH_PATTERN"'"; "i")) | any) | .value.pullRequest.number]')
        fmha_nums=$(jq -n --argjson a "$fmha_nums" --argjson b "$batch_fmha" '$a + $b')
    done

    echo "$ambiguous_json" | jq --argjson fmha "$fmha_nums" '[.[] | select(.number as $n | $fmha | any(. == $n))]'
}

list_pending() {
    local last_scanned=0
    local confirmed_json="[]"

    if [[ -f "$STATE_FILE" ]] && [[ "$FULL_SCAN" != "true" ]]; then
        last_scanned=$(yq -o json -r '.last_scanned_pr // 0' "$STATE_FILE")
        confirmed_json=$(yq -o json '.confirmed_fmha_prs // []' "$STATE_FILE")
    fi

    local all_prs_json
    all_prs_json=$(fetch_open_prs)

    # Phase 1: triage by title + filter confirmed
    local triage_json
    triage_json=$(jq -n \
        --argjson all "$all_prs_json" \
        --argjson confirmed "$confirmed_json" \
        --argjson last_scanned "$last_scanned" \
        '
        ($confirmed | map(.number)) as $conf_nums |
        ($all | map(.number)) as $open_nums |
        {
            max_pr_number: ([$all[].number] | if length == 0 then 0 else max end),
            obvious_fmha: [
                $all[] |
                select(.number > $last_scanned) |
                select(.number as $n | $conf_nums | any(. == $n) | not) |
                select(.title | test("fmha|attention|flash|multi-?head|\\bmha\\b"; "i"))
            ],
            ambiguous: [
                $all[] |
                select(.number > $last_scanned) |
                select(.number as $n | $conf_nums | any(. == $n) | not) |
                select(.title | test("fmha|attention|flash|multi-?head|\\bmha\\b"; "i") | not)
            ],
            confirmed_open: [
                $confirmed[] |
                select(.number as $n | $open_nums | any(. == $n))
            ]
        }
        ')

    # Phase 2: pre-filter ambiguous PRs by file paths
    local ambiguous_json
    ambiguous_json=$(echo "$triage_json" | jq '.ambiguous')
    local filtered_ambiguous
    filtered_ambiguous=$(filter_ambiguous_by_files "$ambiguous_json")

    # Phase 3: assemble final output
    echo "$triage_json" | jq --argjson filtered "$filtered_ambiguous" '
        {
            max_pr_number: .max_pr_number,
            to_verify: {
                obvious_fmha: .obvious_fmha,
                ambiguous: $filtered
            },
            confirmed_open: .confirmed_open
        }
    ' | yq -P -p json
}

commit_results() {
    local input
    input=$(cat)

    # Validate required keys
    echo "$input" | yq -e '.last_scanned_pr' > /dev/null 2>&1 \
        || { echo "Error: input missing 'last_scanned_pr'" >&2; exit 1; }
    echo "$input" | yq -e '.confirmed_fmha_prs' > /dev/null 2>&1 \
        || { echo "Error: input missing 'confirmed_fmha_prs'" >&2; exit 1; }

    mkdir -p "$(dirname "$STATE_FILE")"
    echo "$input" > "$STATE_FILE"
}

case "$SUBCOMMAND" in
    list-pending) list_pending ;;
    commit-results) commit_results ;;
esac
