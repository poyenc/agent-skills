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

echo "PASS=$PASS FAIL=$FAIL"; [ "$FAIL" -eq 0 ]
