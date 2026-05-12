#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$SCRIPT_DIR/../scripts/fmha-pr-scan.sh"
TEST_DIR=$(mktemp -d)
MOCK_DIR="$TEST_DIR/mock-bin"
PASS=0
FAIL=0

cleanup() { rm -rf "$TEST_DIR"; }
trap cleanup EXIT

assert_eq() {
    local label="$1" expected="$2" actual="$3"
    if [[ "$expected" == "$actual" ]]; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label"
        echo "    expected: $expected"
        echo "    actual:   $actual"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local label="$1" pattern="$2" actual="$3"
    if echo "$actual" | grep -qE "$pattern"; then
        echo "  PASS: $label"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $label"
        echo "    expected pattern: $pattern"
        echo "    actual: $actual"
        FAIL=$((FAIL + 1))
    fi
}

# --- Mock gh setup ---
mkdir -p "$MOCK_DIR"
cat > "$MOCK_DIR/gh" << 'MOCK_GH'
#!/usr/bin/env bash
# Mock gh: returns canned PR data from GH_MOCK_DATA_FILE
cat "$GH_MOCK_DATA_FILE"
MOCK_GH
chmod +x "$MOCK_DIR/gh"

# --- Canned API response (raw GitHub API format) ---
cat > "$TEST_DIR/mock-prs.json" << 'MOCK_DATA'
[
  {
    "number": 100,
    "title": "[CK_TILE] FMHA forward kernel",
    "labels": [{"name": "project: composablekernel"}],
    "user": {"login": "alice"},
    "html_url": "https://github.com/ROCm/rocm-libraries/pull/100",
    "created_at": "2026-01-01T00:00:00Z"
  },
  {
    "number": 101,
    "title": "[CK_TILE] Update GEMM pipeline",
    "labels": [{"name": "project: composablekernel"}],
    "user": {"login": "bob"},
    "html_url": "https://github.com/ROCm/rocm-libraries/pull/101",
    "created_at": "2026-01-02T00:00:00Z"
  },
  {
    "number": 102,
    "title": "[CK_TILE] Flash attention backward",
    "labels": [{"name": "project: composablekernel"}],
    "user": {"login": "carol"},
    "html_url": "https://github.com/ROCm/rocm-libraries/pull/102",
    "created_at": "2026-01-03T00:00:00Z"
  },
  {
    "number": 103,
    "title": "[CK_TILE] Add MHA test suite",
    "labels": [{"name": "project: composablekernel"}],
    "user": {"login": "dave"},
    "html_url": "https://github.com/ROCm/rocm-libraries/pull/103",
    "created_at": "2026-01-04T00:00:00Z"
  },
  {
    "number": 104,
    "title": "[CK_TILE] Fix build on gfx942",
    "labels": [{"name": "project: composablekernel"}],
    "user": {"login": "eve"},
    "html_url": "https://github.com/ROCm/rocm-libraries/pull/104",
    "created_at": "2026-01-05T00:00:00Z"
  }
]
MOCK_DATA

run_script() {
    GH_MOCK_DATA_FILE="$TEST_DIR/mock-prs.json" PATH="$MOCK_DIR:$PATH" \
        bash "$SCRIPT" "$@"
}

# =============================================================
echo "=== Test 1: list-pending with no state file (fresh scan) ==="
# =============================================================
STATE="$TEST_DIR/test1-state.yaml"
OUTPUT=$(run_script --state-file "$STATE" list-pending)

assert_eq "max_pr_number is 104" \
    "104" \
    "$(echo "$OUTPUT" | yq '.max_pr_number')"

assert_eq "obvious_fmha count is 3" \
    "3" \
    "$(echo "$OUTPUT" | yq '.to_verify.obvious_fmha | length')"

assert_eq "ambiguous count is 2" \
    "2" \
    "$(echo "$OUTPUT" | yq '.to_verify.ambiguous | length')"

assert_eq "confirmed_open count is 0" \
    "0" \
    "$(echo "$OUTPUT" | yq '.confirmed_open | length')"

# Check specific PRs in obvious bucket (100=FMHA, 102=Flash, 103=MHA)
assert_contains "obvious contains PR 100" "100" \
    "$(echo "$OUTPUT" | yq '.to_verify.obvious_fmha[].number')"
assert_contains "obvious contains PR 102" "102" \
    "$(echo "$OUTPUT" | yq '.to_verify.obvious_fmha[].number')"
assert_contains "obvious contains PR 103" "103" \
    "$(echo "$OUTPUT" | yq '.to_verify.obvious_fmha[].number')"

# Check ambiguous bucket (101=GEMM, 104=build fix)
assert_contains "ambiguous contains PR 101" "101" \
    "$(echo "$OUTPUT" | yq '.to_verify.ambiguous[].number')"
assert_contains "ambiguous contains PR 104" "104" \
    "$(echo "$OUTPUT" | yq '.to_verify.ambiguous[].number')"

# =============================================================
echo ""
echo "=== Test 2: list-pending with existing state (incremental) ==="
# =============================================================
STATE="$TEST_DIR/test2-state.yaml"
cat > "$STATE" << 'STATE_YAML'
last_scanned_pr: 102
confirmed_fmha_prs:
  - number: 100
    title: "[CK_TILE] FMHA forward kernel"
    author: alice
    url: https://github.com/ROCm/rocm-libraries/pull/100
    category: Kernel
    summary: "Adds FMHA forward kernel."
    created_at: "2026-01-01T00:00:00Z"
STATE_YAML

OUTPUT=$(run_script --state-file "$STATE" list-pending)

assert_eq "max_pr_number is 104" \
    "104" \
    "$(echo "$OUTPUT" | yq '.max_pr_number')"

# Only PRs 103 and 104 are new (> 102)
# PR 103 (MHA test) -> obvious; PR 104 (build fix) -> ambiguous
assert_eq "obvious_fmha count is 1" \
    "1" \
    "$(echo "$OUTPUT" | yq '.to_verify.obvious_fmha | length')"

assert_eq "ambiguous count is 1" \
    "1" \
    "$(echo "$OUTPUT" | yq '.to_verify.ambiguous | length')"

assert_eq "obvious is PR 103" \
    "103" \
    "$(echo "$OUTPUT" | yq '.to_verify.obvious_fmha[0].number')"

assert_eq "ambiguous is PR 104" \
    "104" \
    "$(echo "$OUTPUT" | yq '.to_verify.ambiguous[0].number')"

# PR 100 is still open (in mock data) -> confirmed_open
assert_eq "confirmed_open count is 1" \
    "1" \
    "$(echo "$OUTPUT" | yq '.confirmed_open | length')"

assert_eq "confirmed_open is PR 100" \
    "100" \
    "$(echo "$OUTPUT" | yq '.confirmed_open[0].number')"

# =============================================================
echo ""
echo "=== Test 3: list-pending with --full-scan ignores state ==="
# =============================================================
STATE="$TEST_DIR/test3-state.yaml"
cat > "$STATE" << 'STATE_YAML'
last_scanned_pr: 102
confirmed_fmha_prs:
  - number: 100
    title: "[CK_TILE] FMHA forward kernel"
    author: alice
    url: https://github.com/ROCm/rocm-libraries/pull/100
    category: Kernel
    summary: "Adds FMHA forward kernel."
    created_at: "2026-01-01T00:00:00Z"
STATE_YAML

OUTPUT=$(run_script --state-file "$STATE" list-pending --full-scan)

# All 5 PRs should be in to_verify, none in confirmed_open
assert_eq "obvious_fmha count is 3" \
    "3" \
    "$(echo "$OUTPUT" | yq '.to_verify.obvious_fmha | length')"

assert_eq "ambiguous count is 2" \
    "2" \
    "$(echo "$OUTPUT" | yq '.to_verify.ambiguous | length')"

assert_eq "confirmed_open count is 0" \
    "0" \
    "$(echo "$OUTPUT" | yq '.confirmed_open | length')"

# =============================================================
echo ""
echo "=== Test 4: confirmed PR removed when closed ==="
# =============================================================
# Use mock data that does NOT include PR 100 (simulating it was merged/closed)
cat > "$TEST_DIR/mock-prs-closed.json" << 'MOCK_DATA'
[
  {
    "number": 101,
    "title": "[CK_TILE] Update GEMM pipeline",
    "labels": [{"name": "project: composablekernel"}],
    "user": {"login": "bob"},
    "html_url": "https://github.com/ROCm/rocm-libraries/pull/101",
    "created_at": "2026-01-02T00:00:00Z"
  },
  {
    "number": 102,
    "title": "[CK_TILE] Flash attention backward",
    "labels": [{"name": "project: composablekernel"}],
    "user": {"login": "carol"},
    "html_url": "https://github.com/ROCm/rocm-libraries/pull/102",
    "created_at": "2026-01-03T00:00:00Z"
  }
]
MOCK_DATA

STATE="$TEST_DIR/test4-state.yaml"
cat > "$STATE" << 'STATE_YAML'
last_scanned_pr: 102
confirmed_fmha_prs:
  - number: 100
    title: "[CK_TILE] FMHA forward kernel"
    author: alice
    url: https://github.com/ROCm/rocm-libraries/pull/100
    category: Kernel
    summary: "Adds FMHA forward kernel."
    created_at: "2026-01-01T00:00:00Z"
STATE_YAML

OUTPUT=$(GH_MOCK_DATA_FILE="$TEST_DIR/mock-prs-closed.json" PATH="$MOCK_DIR:$PATH" \
    bash "$SCRIPT" --state-file "$STATE" list-pending)

# PR 100 was confirmed but is no longer open -> should NOT appear in confirmed_open
assert_eq "confirmed_open count is 0" \
    "0" \
    "$(echo "$OUTPUT" | yq '.confirmed_open | length')"

# =============================================================
echo ""
echo "=== Test 5: commit-results writes state file ==="
# =============================================================
STATE="$TEST_DIR/test5-state.yaml"
cat <<'INPUT' | run_script --state-file "$STATE" commit-results
last_scanned_pr: 104
confirmed_fmha_prs:
  - number: 100
    title: "[CK_TILE] FMHA forward kernel"
    author: alice
    url: https://github.com/ROCm/rocm-libraries/pull/100
    category: Kernel
    summary: "Adds FMHA forward kernel."
    created_at: "2026-01-01T00:00:00Z"
  - number: 102
    title: "[CK_TILE] Flash attention backward"
    author: carol
    url: https://github.com/ROCm/rocm-libraries/pull/102
    category: Kernel
    summary: "Backward pass for flash attention."
    created_at: "2026-01-03T00:00:00Z"
INPUT

assert_eq "state file exists" "true" "$([[ -f "$STATE" ]] && echo true || echo false)"
assert_eq "last_scanned_pr is 104" \
    "104" \
    "$(yq '.last_scanned_pr' "$STATE")"
assert_eq "confirmed count is 2" \
    "2" \
    "$(yq '.confirmed_fmha_prs | length' "$STATE")"

# =============================================================
echo ""
echo "=== Test 6: commit-results rejects missing keys ==="
# =============================================================
STATE="$TEST_DIR/test6-state.yaml"
if echo "last_scanned_pr: 100" | run_script --state-file "$STATE" commit-results 2>/dev/null; then
    echo "  FAIL: should have rejected missing confirmed_fmha_prs"
    FAIL=$((FAIL + 1))
else
    echo "  PASS: rejected missing confirmed_fmha_prs"
    PASS=$((PASS + 1))
fi

# =============================================================
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]] || exit 1
