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

echo "PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
