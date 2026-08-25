#!/usr/bin/env bash
# Manual live smoke test — run inside a herdr session. Rotates a throwaway agent per kind.
# Usage: smoke-live.sh <kind> [-- <launch-args...>]
set -euo pipefail
[ "${HERDR_ENV:-}" = 1 ] || { echo "not in herdr"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"; ROT="$HERE/../scripts/herdr-rotate"
kind="${1:?kind}"; shift || true; [ "${1:-}" = "--" ] && shift
case "$kind" in
  claude) LAUNCH=(--model haiku --effort medium --verbose) ;;
  pi)     LAUNCH=(--model amd-gateway/gpt-5.6-terra --thinking high) ;;
  codex)  LAUNCH=(-m glm-5.2 -c model_reasoning_effort=low) ;;
  *) echo "unknown kind"; exit 1 ;;
esac
[ $# -gt 0 ] && LAUNCH=("$@")
name="smoke-$kind"
tab=$(herdr tab create --cwd "$PWD" --label "$name" --no-focus)
pane=$(printf '%s' "$tab" | jq -r .result.root_pane.pane_id)
tabid=$(printf '%s' "$tab" | jq -r .result.tab.tab_id)
cleanup(){ herdr tab close "$tabid" >/dev/null 2>&1 || true; }
trap cleanup EXIT
herdr agent start "$name" --kind "$kind" --pane "$pane" --timeout 120000 -- "${LAUNCH[@]}" >/dev/null
before=$(herdr pane process-info --pane "$pane" | jq -c --arg k "$kind" '.result.process_info.foreground_processes[]|select(.name==$k).argv')
herdr agent prompt "$name" "Remember the codeword ZEBRA-42. Reply OK." --wait --timeout 60000 >/dev/null
"$ROT" "$name" --no-kickoff                                   # rotate WITHOUT kickoff
after=$(herdr pane process-info --pane "$pane" | jq -c --arg k "$kind" '.result.process_info.foreground_processes[]|select(.name==$k).argv')
recall=$(herdr agent prompt "$name" "What codeword did I ask you to remember? Reply NO_MARKER if none." --wait --timeout 60000; herdr agent read "$name" --source visible --lines 8)
fails=0
[ "$before" = "$after" ] || { echo "FAIL argv: $before != $after"; fails=1; }
printf '%s' "$recall" | grep -q NO_MARKER || { echo "FAIL freshness: recall did not report NO_MARKER"; fails=1; }
ls "${TMPDIR:-/tmp}/handoff-$(id -un)"/*handoff*.md >/dev/null 2>&1 || { echo "FAIL: no handoff file"; fails=1; }
[ "$fails" = 0 ] && echo "SMOKE PASS ($kind)" || { echo "SMOKE FAIL ($kind)"; exit 1; }
