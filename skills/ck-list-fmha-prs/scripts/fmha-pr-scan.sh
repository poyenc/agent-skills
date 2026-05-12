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

REPO="ROCm/rocm-libraries"
LABEL="project: composablekernel"

fetch_open_prs() {
    gh api "repos/$REPO/pulls?state=open&per_page=100" --paginate \
    | jq -s 'add | [.[] | select(.labels[]?.name == "'"$LABEL"'") | {number, title, author: .user.login, url: .html_url, created_at}]'
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

    jq -n \
        --argjson all "$all_prs_json" \
        --argjson confirmed "$confirmed_json" \
        --argjson last_scanned "$last_scanned" \
        '
        ($confirmed | map(.number)) as $conf_nums |
        ($all | map(.number)) as $open_nums |
        {
            max_pr_number: ([$all[].number] | if length == 0 then 0 else max end),
            to_verify: {
                obvious_fmha: [
                    $all[] |
                    select(.number > $last_scanned) |
                    select(.number as $n | $conf_nums | index($n) | not) |
                    select(.title | test("fmha|attention|flash|multi-?head|\\bmha\\b"; "i"))
                ],
                ambiguous: [
                    $all[] |
                    select(.number > $last_scanned) |
                    select(.number as $n | $conf_nums | index($n) | not) |
                    select(.title | test("fmha|attention|flash|multi-?head|\\bmha\\b"; "i") | not)
                ]
            },
            confirmed_open: [
                $confirmed[] |
                select(.number as $n | $open_nums | index($n))
            ]
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
