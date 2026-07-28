#!/usr/bin/env bash
# Usage: ntfy.sh "Your message here"
# Reads NTFY_TOPIC, NTFY_TITLE, NTFY_PRIORITY, NTFY_URL, NTFY_TOKEN from env.
set -euo pipefail

MESSAGE="${1:-}"
if [[ -z "$MESSAGE" ]]; then
    echo "Usage: ntfy.sh <message>" >&2
    exit 1
fi

TOPIC="${NTFY_TOPIC:-agent-notify-topic}"
TITLE="${NTFY_TITLE:-Agent needs input}"
PRIORITY="${NTFY_PRIORITY:-default}"
BASE_URL="${NTFY_URL:-https://ntfy.sh}"

CURL_ARGS=(-s -H "Title: ${TITLE}" -H "Priority: ${PRIORITY}" -H "Tags: bell")
[[ -n "${NTFY_TOKEN:-}" ]] && CURL_ARGS+=(-H "Authorization: Bearer ${NTFY_TOKEN}")

curl "${CURL_ARGS[@]}" -d "$MESSAGE" "${BASE_URL}/${TOPIC}"
