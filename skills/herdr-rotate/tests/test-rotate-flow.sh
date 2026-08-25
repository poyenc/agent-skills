#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; S="$HERE/../scripts"
PASS=0; FAIL=0
assert_eq(){ if [[ "$2" == "$3" ]]; then echo "  PASS: $1"; PASS=$((PASS+1)); else echo "  FAIL: $1"; echo "    exp:[$2] act:[$3]"; FAIL=$((FAIL+1)); fi; }

setup(){ # $1=kind $2=name  -> exports fresh state + PATH
  export TMPDIR; TMPDIR=$(mktemp -d)
  export MOCK_STATE; MOCK_STATE=$(mktemp -d)
  export MOCK_CALLS="$MOCK_STATE/calls"; : > "$MOCK_CALLS"
  export MOCK_KIND="$1" MOCK_PANE="wG:p4" MOCK_NAME="$2"
  export MOCK_SENT_OK=1; unset MOCK_VERIFY_ARGV
  printf -- '--model\nopus\n--verbose\n' > "$MOCK_STATE/argv"   # original launch flags
  export PATH="$HERE/mock:$PATH"
  export ROTATE_HANDOFF_POLL_SECS=5 ROTATE_EXIT_POLL_SECS=5 ROTATE_VERIFY_POLL_SECS=5
}
run(){ HERDR_ENV=1 bash "$@" ; }   # returns exit code

# 1. happy claude flow
setup claude lead
run "$S/herdr-rotate-claude" lead >/dev/null 2>&1; assert_eq "happy exit 0" "0" "$?"
ho=$(grep -n 'handoff' "$MOCK_CALLS" | head -n1 | cut -d: -f1)
q=$(grep -n '/quit' "$MOCK_CALLS" | head -n1 | cut -d: -f1)
st=$(grep -n 'agent start' "$MOCK_CALLS" | head -n1 | cut -d: -f1)
assert_eq "order handoff<quit" "1" "$([ "$ho" -lt "$q" ] && echo 1 || echo 0)"
assert_eq "order quit<start"  "1" "$([ "$q" -lt "$st" ] && echo 1 || echo 0)"
assert_eq "started argv preserved" $'--model\nopus\n--verbose' "$(cat "$MOCK_STATE/argv")"

# 2. missing handoff -> no /quit, no start, non-zero
setup claude lead; export MOCK_SENT_OK=0
run "$S/herdr-rotate-claude" lead >/dev/null 2>&1; assert_eq "missing handoff non-zero" "1" "$?"
assert_eq "no /quit on missing handoff"  "0" "$(grep -c '/quit' "$MOCK_CALLS")"
assert_eq "no start on missing handoff"  "0" "$(grep -c 'agent start' "$MOCK_CALLS")"

# 3. override propagates into relaunch argv
setup claude lead
run "$S/herdr-rotate-claude" lead --model sonnet --effort high >/dev/null 2>&1
assert_eq "override in started argv" "1" "$(grep -cx 'sonnet' "$MOCK_STATE/argv")"

# 4. verify mismatch -> non-zero
setup claude lead
printf -- '--model\nhaiku\n' > "$MOCK_STATE/wrong"; export MOCK_VERIFY_ARGV="$MOCK_STATE/wrong"
run "$S/herdr-rotate-claude" lead >/dev/null 2>&1; assert_eq "verify mismatch non-zero" "1" "$?"

# 5. pi bare-model override rejected BEFORE destructive steps
setup pi worker
run "$S/herdr-rotate-pi" worker --model bareword >/dev/null 2>&1; assert_eq "pi bare model non-zero" "1" "$?"
assert_eq "pi rejects before /quit"  "0" "$(grep -c '/quit' "$MOCK_CALLS")"
assert_eq "pi rejects before start"  "0" "$(grep -c 'agent start' "$MOCK_CALLS")"

# 6. dispatcher routes by kind + forwards (kind=pi) and succeeds
setup pi worker
run "$S/herdr-rotate" worker --model amd-gateway/gpt-5.6-terra >/dev/null 2>&1; assert_eq "dispatch pi exit 0" "0" "$?"
assert_eq "dispatch forwarded override" "1" "$(grep -cx 'amd-gateway/gpt-5.6-terra' "$MOCK_STATE/argv")"

# 7. no-op via per-kind exec outside herdr (no herdr calls)
setup claude lead
( env -u HERDR_ENV bash "$S/herdr-rotate-claude" lead >/dev/null 2>&1 ); assert_eq "no-op exit 0" "0" "$?"
assert_eq "no-op made no herdr calls" "0" "$(wc -l < "$MOCK_CALLS" | tr -d ' ')"

echo "PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
