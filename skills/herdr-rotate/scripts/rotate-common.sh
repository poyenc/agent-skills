#!/usr/bin/env bash
# rotate-common.sh — shared backbone for herdr-rotate-<kind>. Sourced, not executed.
# The caller sets `set -euo pipefail`. All herdr access is via the `herdr` command.

rotate_note() { printf 'herdr-rotate: %s\n' "$*" >&2; }
rotate_die()  { printf 'herdr-rotate: ERROR: %s\n' "$*" >&2; exit 1; }

rotate_guard() { [ "${HERDR_ENV:-}" = 1 ]; }

# "wG:p4" + "claude" -> "claude-wgp4" (lowercase, keep [a-z0-9], clamp 32).
rotate_derive_name() {
  local kind="$1" pane="$2" suffix
  suffix=$(printf '%s' "$pane" | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9')
  printf '%s' "${kind}-${suffix}" | cut -c1-32
}

# herdr agent-name grammar.
rotate_valid_name() { [[ "$1" =~ ^[a-z][a-z0-9_-]{0,31}$ ]]; }

rotate_strip_context_flags() {
  local skip=0 tok
  for tok in "$@"; do
    if [ "$skip" = 1 ]; then skip=0; continue; fi
    case "$tok" in
      --continue)             ;;
      --resume|-r|--session)  skip=1 ;;
      --resume=*|--session=*) ;;
      *) printf '%s\0' "$tok" ;;
    esac
  done
}

replace_or_append_flag() {
  local -n _arr="$1"; local flag="$2" val="$3" out=() n=${#_arr[@]} j=0 found=0
  while [ "$j" -lt "$n" ]; do
    if [ "${_arr[$j]}" = "$flag" ]; then out+=("$flag" "$val"); j=$((j+2)); found=1
    elif [[ "${_arr[$j]}" == "$flag="* ]]; then out+=("$flag=$val"); j=$((j+1)); found=1
    else out+=("${_arr[$j]}"); j=$((j+1)); fi
  done
  [ "$found" = 1 ] || out+=("$flag" "$val")
  _arr=("${out[@]}")
}

replace_or_append_kv() {
  # shellcheck disable=SC2178
  local -n _arr="$1"; local key="$2" val="$3" out=() n=${#_arr[@]} j=0 found=0
  while [ "$j" -lt "$n" ]; do
    if [ "${_arr[$j]}" = "-c" ] && [ $((j+1)) -lt "$n" ] && [[ "${_arr[$((j+1))]}" == "$key="* ]]; then
      out+=("-c" "$key=$val"); j=$((j+2)); found=1
    else out+=("${_arr[$j]}"); j=$((j+1)); fi
  done
  [ "$found" = 1 ] || out+=("-c" "$key=$val")
  _arr=("${out[@]}")
}

# Shared. Requires globals MODEL_FLAG, EFFORT_FLAG, EFFORT_STYLE (set by per-kind script).
rotate_apply_override() {
  local m="$1" e="$2"
  [ -n "$m" ] && replace_or_append_flag BASE_FLAGS "$MODEL_FLAG" "$m"
  if [ -n "$e" ]; then
    case "$EFFORT_STYLE" in
      flag) replace_or_append_flag BASE_FLAGS "$EFFORT_FLAG" "$e" ;;
      kv)   replace_or_append_kv   BASE_FLAGS "$EFFORT_FLAG" "$e" ;;
      *) rotate_die "unknown EFFORT_STYLE: $EFFORT_STYLE" ;;
    esac
  fi
}

rotate_capture_argv() {
  local pane="$1" kind="$2" json
  json=$(herdr pane process-info --pane "$pane" 2>/dev/null) \
    || rotate_die "process-info failed for pane $pane"
  local -a raw
  mapfile -d '' -t raw < <(printf '%s' "$json" | jq -j --arg k "$kind" '
    .result.process_info.foreground_processes[] | select(.name==$k) | .argv[] | . + "\u0000"')
  [ "${#raw[@]}" -gt 0 ] || rotate_die "no $kind process on pane $pane"
  mapfile -d '' -t BASE_FLAGS < <(rotate_strip_context_flags "${raw[@]:1}")
}

rotate_resolve() {
  local target="$1" row
  row=$(herdr agent list 2>/dev/null \
        | jq -r --arg t "$target" '
            first(.result.agents[] | select(.name==$t or .pane_id==$t))
            | [.agent, .pane_id, (.name // "")] | @tsv') || rotate_die "agent list failed"
  [ -n "$row" ] && [ "$row" != $'\t\t' ] || rotate_die "target not found: $target"
  IFS=$'\t' read -r ROTATE_KIND ROTATE_PANE ROTATE_NAME <<<"$row"
  if [ -z "$ROTATE_NAME" ]; then
    if [ -n "${OVERRIDE_NAME:-}" ]; then ROTATE_NAME="$OVERRIDE_NAME"
    else ROTATE_NAME=$(rotate_derive_name "$ROTATE_KIND" "$ROTATE_PANE"); fi
    rotate_note "agent unnamed; assigned name: $ROTATE_NAME"
  fi
}

# Two %s: handoff dir, sentinel path.
ROTATE_HANDOFF_PROMPT='Write a handoff document so a fresh agent can continue this work with full context. Capture: the objective and what "done" looks like; the task list (done / in progress / not started); key files, branch, and build/test/run commands; the operating rules and decisions made this session with their rationale; dead ends already ruled out; and any in-flight work. Keep only what the remaining work needs; strip secrets, keys, and PII. Save it to %s/<YYMMDD-HHMMSS>-handoff-<short-topic>.md (create the directory with mkdir -m 700 -p if needed). When done, write the absolute path of the file you created into %s (overwrite that file with just the path), and also reply with only that path — nothing else.'

rotate_handoff() {
  local pane="$1"
  local dir="${TMPDIR:-/tmp}/handoff-$(id -un)"
  mkdir -p "$dir"; chmod 700 "$dir" 2>/dev/null || true
  local marker sentinel
  marker=$(mktemp "$dir/.rotate-marker.XXXXXX")
  sentinel=$(mktemp "${TMPDIR:-/tmp}/rotate-sentinel.XXXXXX")
  local prompt; printf -v prompt "$ROTATE_HANDOFF_PROMPT" "$dir" "$sentinel"
  herdr agent prompt "$pane" "$prompt" --wait --timeout "${ROTATE_HANDOFF_TIMEOUT_MS:-180000}" >/dev/null 2>&1 || true
  local path="" deadline=$(( SECONDS + ${ROTATE_HANDOFF_POLL_SECS:-90} ))
  while [ "$SECONDS" -lt "$deadline" ]; do
    path=$(head -n1 "$sentinel" 2>/dev/null | tr -d '[:space:]')
    [ -n "$path" ] && break
    command sleep 1
  done
  local err=""
  if   [ -z "$path" ]; then err="handoff sentinel empty (agent reported no path)"
  elif [ "${path#"$dir"/}" = "$path" ]; then err="handoff path not under $dir: $path"
  elif [ ! -f "$path" ] || [ ! -s "$path" ]; then err="handoff file missing/empty: $path"
  elif [ ! "$path" -nt "$marker" ]; then err="handoff file not newer than marker: $path"
  fi
  rm -f "$marker" "$sentinel"
  [ -z "$err" ] || rotate_die "$err"
  HANDOFF_PATH="$path"
  rotate_note "handoff verified: $HANDOFF_PATH"
}

# rc 0 iff the agent is confirmed gone AND the pane is back at a shell prompt.
rotate_gone() {
  local pane="$1" out
  out=$(herdr agent get "$pane" 2>&1) || true
  if printf '%s' "$out" | jq -e '.result.agent' >/dev/null 2>&1; then return 1; fi
  printf '%s' "$out" | jq -e '.error.code=="agent_not_found"' >/dev/null 2>&1 || return 1
  herdr pane read "$pane" --source visible --lines 6 2>/dev/null | grep -qE '[$#❯][[:space:]]*$'
}

rotate_exit() {
  local pane="$1"
  herdr agent prompt "$pane" "/quit" >/dev/null 2>&1 || true
  local deadline=$(( SECONDS + ${ROTATE_EXIT_POLL_SECS:-25} ))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if rotate_gone "$pane"; then rotate_note "agent exited; pane $pane free"; return 0; fi
    command sleep 1
  done
  if declare -F exit_fallback >/dev/null 2>&1; then
    rotate_note "/quit did not settle; trying kind fallback"
    exit_fallback "$pane" && return 0
  fi
  rotate_die "agent did not exit on pane $pane"
}

rotate_relaunch() {
  local name="$1" kind="$2" pane="$3"; shift 3
  herdr agent start "$name" --kind "$kind" --pane "$pane" \
    --timeout "${ROTATE_START_TIMEOUT_MS:-120000}" -- "$@" >/dev/null 2>&1 \
    || rotate_die "relaunch failed for $name"
  rotate_note "relaunched $name ($kind) in $pane"
}

rotate_verify() {
  local name="$1" pane="$2" kind="$3"; shift 3
  [ "${1:-}" = "--" ] && shift
  local -a intended=( "$@" )
  local deadline=$(( SECONDS + ${ROTATE_VERIFY_POLL_SECS:-30} )) st=""
  while [ "$SECONDS" -lt "$deadline" ]; do
    st=$(herdr agent get "$name" 2>/dev/null | jq -r '.result.agent.agent_status // empty')
    case "$st" in idle|done) break ;; esac
    command sleep 1
  done
  case "$st" in idle|done) ;; *) rotate_note "verify: agent not ready ($st)"; return 1 ;; esac
  local -a BASE_FLAGS=()
  rotate_capture_argv "$pane" "$kind"
  if [ "${#BASE_FLAGS[@]}" -ne "${#intended[@]}" ]; then
    rotate_note "verify: argv length ${#BASE_FLAGS[@]} != ${#intended[@]}"; return 1
  fi
  local i
  for i in "${!intended[@]}"; do
    if [ "${BASE_FLAGS[$i]}" != "${intended[$i]}" ]; then
      rotate_note "verify: argv[$i] '${BASE_FLAGS[$i]}' != '${intended[$i]}'"; return 1
    fi
  done
  rotate_note "verify OK"; return 0
}

rotate_kickoff() {
  local pane="$1" path="$2" msg="${3:-}"
  if [ "${NO_KICKOFF:-0}" = 1 ]; then rotate_note "kickoff skipped (--no-kickoff)"; return 0; fi
  local text
  if [ -n "$msg" ]; then text="$msg"
  else text="Continue the work described in the handoff at ${path}. Read it fully first, including every file it references, before doing anything. Then pick up the task list where it leaves off."; fi
  herdr agent prompt "$pane" "$text" >/dev/null 2>&1 \
    || rotate_note "kickoff prompt may not have registered; verify manually"
}

# Single entry. Per-kind scripts set MODEL_FLAG/EFFORT_FLAG/EFFORT_STYLE (+ optional
# validate_override / exit_fallback) then call this.
rotate_main() {
  local expected_kind="$1"; shift
  rotate_guard || { rotate_note "not in herdr (HERDR_ENV != 1); no-op"; exit 0; }
  local target="" OVERRIDE_NAME="" OVERRIDE_MODEL="" OVERRIDE_EFFORT="" KICKOFF="" NO_KICKOFF=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --name)    [ $# -ge 2 ] || rotate_die "--name needs a value";    OVERRIDE_NAME="$2";   shift 2 ;;
      --model)   [ $# -ge 2 ] || rotate_die "--model needs a value";   OVERRIDE_MODEL="$2";  shift 2 ;;
      --effort)  [ $# -ge 2 ] || rotate_die "--effort needs a value";  OVERRIDE_EFFORT="$2"; shift 2 ;;
      --kickoff) [ $# -ge 2 ] || rotate_die "--kickoff needs a value"; KICKOFF="$2";         shift 2 ;;
      --no-kickoff) NO_KICKOFF=1; shift ;;
      --) shift ;;
      -*) rotate_die "unknown option: $1" ;;
      *) [ -z "$target" ] || rotate_die "unexpected extra argument: $1"; target="$1"; shift ;;
    esac
  done
  [ -n "$target" ] || rotate_die "usage: herdr-rotate-$expected_kind <name-or-pane> [--name N] [--model M] [--effort E] [--kickoff MSG] [--no-kickoff]"
  rotate_resolve "$target"
  [ "$ROTATE_KIND" = "$expected_kind" ] || rotate_die "target is $ROTATE_KIND, not $expected_kind"
  rotate_valid_name "$ROTATE_NAME" || rotate_die "invalid agent name: $ROTATE_NAME"
  declare -F validate_override >/dev/null 2>&1 && validate_override "$OVERRIDE_MODEL" "$OVERRIDE_EFFORT"
  rotate_capture_argv "$ROTATE_PANE" "$ROTATE_KIND"
  rotate_apply_override "$OVERRIDE_MODEL" "$OVERRIDE_EFFORT"
  local -a intended=( "${BASE_FLAGS[@]}" )
  rotate_handoff "$ROTATE_PANE"
  rotate_exit "$ROTATE_PANE"
  rotate_relaunch "$ROTATE_NAME" "$ROTATE_KIND" "$ROTATE_PANE" "${BASE_FLAGS[@]}"
  local vrc=0
  rotate_verify "$ROTATE_NAME" "$ROTATE_PANE" "$ROTATE_KIND" -- "${intended[@]}" || vrc=$?
  rotate_kickoff "$ROTATE_PANE" "$HANDOFF_PATH" "$KICKOFF"
  [ "$vrc" -eq 0 ] || rotate_die "relaunched but argv verification FAILED — inspect $ROTATE_NAME"
  rotate_note "rotation complete: $ROTATE_NAME ($ROTATE_KIND) in $ROTATE_PANE"
}
