#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../scripts/rotate-common.sh"
PASS=0; FAIL=0
assert_eq(){ if [[ "$2" == "$3" ]]; then echo "  PASS: $1"; PASS=$((PASS+1)); else echo "  FAIL: $1"; echo "    exp:[$2] act:[$3]"; FAIL=$((FAIL+1)); fi; }
rc(){ if "$@"; then echo 0; else echo 1; fi; }

MOCK_AGENTS='{"result":{"agents":[
  {"agent":"claude","pane_id":"wG:p4","name":"lead"},
  {"agent":"pi","pane_id":"wG:p7"}]}}'
herdr(){ case "$1 $2" in "agent list") printf '%s' "$MOCK_AGENTS";; *) echo "{}";; esac; }

rotate_resolve lead
assert_eq "kind by name" "claude" "$ROTATE_KIND"
assert_eq "pane by name" "wG:p4"  "$ROTATE_PANE"
assert_eq "name by name" "lead"   "$ROTATE_NAME"
OVERRIDE_NAME=""; rotate_resolve wG:p7
assert_eq "kind by pane"  "pi"      "$ROTATE_KIND"
assert_eq "derived name"  "pi-wgp7" "$ROTATE_NAME"
OVERRIDE_NAME="profiler"; rotate_resolve wG:p7
assert_eq "override name" "profiler" "$ROTATE_NAME"

# argv with a space AND an embedded newline must survive; argv0 dropped; --continue stripped.
MOCK_PROCINFO=$(jq -nc '{result:{process_info:{foreground_processes:[
  {name:"claude",argv:["claude","--append-system-prompt","line1\nline2","--continue","--model","opus a"]}]}}}')
herdr(){ case "$1 $2" in "pane process-info") printf '%s' "$MOCK_PROCINFO";; *) echo "{}";; esac; }
rotate_capture_argv wG:p4 claude
assert_eq "argv count"       "4" "${#BASE_FLAGS[@]}"
assert_eq "flag0" "--append-system-prompt" "${BASE_FLAGS[0]}"
assert_eq "multiline arg preserved" $'line1\nline2' "${BASE_FLAGS[1]}"
assert_eq "model flag" "--model" "${BASE_FLAGS[2]}"
assert_eq "spaced value preserved" "opus a" "${BASE_FLAGS[3]}"

export TMPDIR; TMPDIR=$(mktemp -d)
HDIR="$TMPDIR/handoff-$(id -un)"; mkdir -p "$HDIR"

# Mock: prompt extracts the sentinel path from the prompt text, writes a handoff file,
# and records that file's path into the sentinel (simulating the agent).
herdr(){
  case "$1 $2" in
    "agent prompt")
      local p="$4" sent; sent=$(printf '%s' "$p" | grep -oE '/[^ ]*rotate-sentinel[^ ]*' | head -n1)
      local f="$HDIR/260825-000000-handoff-real.md"
      printf '# Handoff\nwork\n' > "$f"
      printf '%s\n' "$f" > "$sent"
      echo '{"result":{"type":"agent_prompted"}}' ;;
    *) echo "{}" ;;
  esac
}
# A DECOY newer file from a "concurrent rotation" must be ignored (we use the sentinel).
printf 'decoy\n' > "$HDIR/999999-handoff-decoy.md"
ROTATE_HANDOFF_POLL_SECS=5
rotate_handoff wG:p4
assert_eq "handoff uses sentinel file (not decoy)" "$HDIR/260825-000000-handoff-real.md" "$HANDOFF_PATH"
assert_eq "handoff file nonempty" "1" "$([ -s "$HANDOFF_PATH" ] && echo 1 || echo 0)"

# Failure: agent never writes the sentinel -> abort, no HANDOFF_PATH.
herdr(){ echo '{"result":{}}'; }
ROTATE_HANDOFF_POLL_SECS=2
if ( rotate_handoff wG:p4 ) 2>/dev/null; then r=0; else r=1; fi
assert_eq "handoff aborts when sentinel empty" "1" "$r"

echo "PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
