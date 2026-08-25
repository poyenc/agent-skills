#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/../scripts/rotate-common.sh"
PASS=0; FAIL=0
assert_eq(){ if [[ "$2" == "$3" ]]; then echo "  PASS: $1"; PASS=$((PASS+1)); else echo "  FAIL: $1"; echo "    exp:[$2] act:[$3]"; FAIL=$((FAIL+1)); fi; }
rc(){ if "$@"; then echo 0; else echo 1; fi; }

assert_eq "derive wG:p4"     "claude-wgp4" "$(rotate_derive_name claude wG:p4)"
assert_eq "derive w9:p12 pi" "pi-w9p12"    "$(rotate_derive_name pi w9:p12)"
assert_eq "valid name ok"    "0" "$(rc rotate_valid_name claude-wgp4)"
assert_eq "valid name upper" "1" "$(rc rotate_valid_name Bad)"
assert_eq "valid name slash" "1" "$(rc rotate_valid_name a/b)"
assert_eq "valid name empty" "1" "$(rc rotate_valid_name '')"
HERDR_ENV=1; assert_eq "guard in"  "0" "$(rc rotate_guard)"
HERDR_ENV=0; assert_eq "guard out" "1" "$(rc rotate_guard)"

mapfile -d '' -t k < <(rotate_strip_context_flags --model opus --continue --verbose)
assert_eq "strip --continue" "--model opus --verbose" "${k[*]}"
mapfile -d '' -t k < <(rotate_strip_context_flags --session abc --add-dir /x)
assert_eq "strip --session+val" "--add-dir /x" "${k[*]}"
mapfile -d '' -t k < <(rotate_strip_context_flags --resume=zzz --model haiku)
assert_eq "strip --resume= inline" "--model haiku" "${k[*]}"

arr=(--model opus --verbose); replace_or_append_flag arr --model sonnet
assert_eq "replace space form" "--model sonnet --verbose" "${arr[*]}"
arr=(--model=opus --verbose); replace_or_append_flag arr --model sonnet
assert_eq "replace inline form" "--model=sonnet --verbose" "${arr[*]}"
arr=(--verbose); replace_or_append_flag arr --effort high
assert_eq "append flag" "--verbose --effort high" "${arr[*]}"

arr=(-m glm-5.2 -c model_reasoning_effort=none); replace_or_append_kv arr model_reasoning_effort low
assert_eq "replace kv" "-m glm-5.2 -c model_reasoning_effort=low" "${arr[*]}"
arr=(-m glm-5.2); replace_or_append_kv arr model_reasoning_effort high
assert_eq "append kv" "-m glm-5.2 -c model_reasoning_effort=high" "${arr[*]}"

# shared apply_override via descriptors
MODEL_FLAG=--model EFFORT_FLAG=--effort EFFORT_STYLE=flag
BASE_FLAGS=(--verbose); rotate_apply_override sonnet high
assert_eq "claude-style override" "--verbose --model sonnet --effort high" "${BASE_FLAGS[*]}"
MODEL_FLAG=-m EFFORT_FLAG=model_reasoning_effort EFFORT_STYLE=kv
BASE_FLAGS=(--verbose); rotate_apply_override glm-5.2 low
assert_eq "codex-style override" "--verbose -m glm-5.2 -c model_reasoning_effort=low" "${BASE_FLAGS[*]}"
BASE_FLAGS=(--verbose); rotate_apply_override "" ""
assert_eq "no override unchanged" "--verbose" "${BASE_FLAGS[*]}"

echo "PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
