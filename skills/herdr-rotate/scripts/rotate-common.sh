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
