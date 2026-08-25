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


# Transient error must NOT count as gone.
herdr(){ case "$1 $2" in "agent get") echo '{"error":{"code":"transport_error"}}' >&2; return 1;; esac; echo "{}"; }
assert_eq "transient != gone" "1" "$(rc rotate_gone wG:p4)"

# agent_not_found + shell prompt = gone.
herdr(){
  case "$1 $2" in
    "agent get") echo '{"error":{"code":"agent_not_found"}}' >&2; return 1 ;;
    "pane read") printf 'poyechen@host:~/x$ \n' ;;
    *) echo "{}" ;;
  esac
}
assert_eq "not_found+prompt = gone" "0" "$(rc rotate_gone wG:p4)"

# agent_not_found but NO shell prompt yet = not gone.
herdr(){
  case "$1 $2" in
    "agent get") echo '{"error":{"code":"agent_not_found"}}' >&2; return 1 ;;
    "pane read") printf 'still drawing agent ui\n' ;;
    *) echo "{}" ;;
  esac
}
assert_eq "not_found no-prompt = not gone" "1" "$(rc rotate_gone wG:p4)"

# rotate_exit: present twice, then gone.
CNT=$(mktemp); echo 2 > "$CNT"
herdr(){
  case "$1 $2" in
    "agent prompt") echo '{"result":{}}' ;;
    "agent get")
      local n; n=$(cat "$CNT")
      if [ "$n" -le 0 ]; then echo '{"error":{"code":"agent_not_found"}}' >&2; return 1; fi
      echo $((n-1)) > "$CNT"; echo '{"result":{"agent":{"agent_status":"working"}}}' ;;
    "pane read") printf 'user@host:~$ \n' ;;
    *) echo "{}" ;;
  esac
}
ROTATE_EXIT_POLL_SECS=6
assert_eq "exit succeeds when gone" "0" "$(rc rotate_exit wG:p4)"

STARTLOG=$(mktemp)
herdr(){ case "$1 $2" in "agent start") shift; printf '%s\n' "$*" > "$STARTLOG"; echo '{"result":{"agent":{}}}';; esac; echo '{"result":{}}'; }
rotate_relaunch lead claude wG:p4 --model opus --verbose
assert_eq "start kind+pane" "0" "$(rc grep -q -- '--kind claude --pane wG:p4' "$STARTLOG")"
assert_eq "start replays flags" "0" "$(rc grep -q -- '-- --model opus --verbose' "$STARTLOG")"

# verify: ready + exact argv match (incl a spaced element)
mkproc(){ jq -nc --args '{result:{process_info:{foreground_processes:[{name:"claude",argv:$ARGS.positional}]}}}' -- "$@"; }
herdr(){
  case "$1 $2" in
    "agent get") echo '{"result":{"agent":{"agent_status":"idle"}}}' ;;
    "pane process-info") printf '%s' "$PROC" ;;
    *) echo "{}" ;;
  esac
}
PROC=$(mkproc claude --model "opus a" --verbose)
assert_eq "verify match (spaced arg)" "0" "$(rc rotate_verify lead wG:p4 claude -- --model "opus a" --verbose)"
# ambiguous split must NOT compare equal
PROC=$(mkproc claude --model opus --verbose)
assert_eq "verify rejects split diff" "1" "$(rc rotate_verify lead wG:p4 claude -- --model "opus --verbose")"
# not ready -> fail
herdr(){ case "$1 $2" in "agent get") echo '{"result":{"agent":{"agent_status":"working"}}}';; *) echo "{}";; esac; }
ROTATE_VERIFY_POLL_SECS=2
assert_eq "verify not-ready fails" "1" "$(rc rotate_verify lead wG:p4 claude -- --model opus)"

# kickoff
KOLOG=$(mktemp)
herdr(){ case "$1 $2" in "agent prompt") shift; printf '%s\n' "$*" >> "$KOLOG";; esac; echo '{"result":{}}'; }
: > "$KOLOG"; NO_KICKOFF=0; rotate_kickoff wG:p4 /tmp/h/x.md
assert_eq "kickoff cites path" "1" "$(grep -c '/tmp/h/x.md' "$KOLOG")"
: > "$KOLOG"; rotate_kickoff wG:p4 /tmp/h/x.md "custom go"
assert_eq "kickoff override" "1" "$(grep -c 'custom go' "$KOLOG")"
: > "$KOLOG"; NO_KICKOFF=1; rotate_kickoff wG:p4 /tmp/h/x.md
assert_eq "no-kickoff sends nothing" "0" "$(wc -l < "$KOLOG" | tr -d ' ')"
NO_KICKOFF=0

# rotate_main early-exit paths (no herdr contact needed; guard/parse fail first)
MODEL_FLAG=--model EFFORT_FLAG=--effort EFFORT_STYLE=flag
( HERDR_ENV=0; rotate_main claude foo >/dev/null 2>&1 ); assert_eq "no-op outside herdr" "0" "$?"
( HERDR_ENV=1; herdr(){ :;}; rotate_main claude --bogus x >/dev/null 2>&1 ); assert_eq "unknown option dies" "1" "$?"
( HERDR_ENV=1; herdr(){ :;}; rotate_main claude --model >/dev/null 2>&1 ); assert_eq "missing value dies" "1" "$?"
( HERDR_ENV=1; herdr(){ :;}; rotate_main claude a b >/dev/null 2>&1 ); assert_eq "extra positional dies" "1" "$?"

echo "PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
