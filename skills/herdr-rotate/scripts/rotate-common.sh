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
