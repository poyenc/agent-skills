#!/usr/bin/env bash
# Test helper for monorepo-bridge bats tests.
# Provides fixture functions to create temporary monorepo + submodule repos.

MONOREPO_BRIDGE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../bin" && pwd)/monorepo-bridge"

# Create a temporary monorepo with a subdirectory that simulates a submodule.
# Sets MONOREPO_DIR to the path.
# Usage: create_monorepo [prefix]
create_monorepo() {
    local prefix="${1:-projects/mylib}"
    MONOREPO_DIR="$(mktemp -d)"
    git -C "${MONOREPO_DIR}" init -b main
    git -C "${MONOREPO_DIR}" config user.email "test@test.com"
    git -C "${MONOREPO_DIR}" config user.name "Test"
    mkdir -p "${MONOREPO_DIR}/${prefix}"
    echo "initial" > "${MONOREPO_DIR}/${prefix}/README.md"
    git -C "${MONOREPO_DIR}" add .
    git -C "${MONOREPO_DIR}" commit -m "initial commit"
}

# Add a commit to the monorepo under the prefix.
# Usage: monorepo_commit <prefix> <filename> <content> <message>
monorepo_commit() {
    local prefix="$1" filename="$2" content="$3" message="$4"
    echo "${content}" > "${MONOREPO_DIR}/${prefix}/${filename}"
    git -C "${MONOREPO_DIR}" add .
    git -C "${MONOREPO_DIR}" commit -m "${message}"
}

# Create a standalone "submodule" repo that clones the prefix content.
# Sets SUBMODULE_DIR to the path.
# Usage: create_submodule_from_split <split-branch>
create_submodule_from_split() {
    local split_branch="${1:-bridge-split/main}"
    SUBMODULE_DIR="$(mktemp -d)"
    git clone --branch "${split_branch}" "${MONOREPO_DIR}" "${SUBMODULE_DIR}"
    git -C "${SUBMODULE_DIR}" config user.email "test@test.com"
    git -C "${SUBMODULE_DIR}" config user.name "Test"
}

# Create a standalone submodule repo by extracting prefix content directly.
# Simulates a repo that was originally split from the monorepo.
# Sets SUBMODULE_DIR to the path.
# Usage: create_submodule <prefix>
create_submodule() {
    local prefix="${1:-projects/mylib}"
    SUBMODULE_DIR="$(mktemp -d)"
    git -C "${SUBMODULE_DIR}" init -b main
    git -C "${SUBMODULE_DIR}" config user.email "test@test.com"
    git -C "${SUBMODULE_DIR}" config user.name "Test"
    cp -r "${MONOREPO_DIR}/${prefix}/"* "${SUBMODULE_DIR}/"
    git -C "${SUBMODULE_DIR}" add .
    git -C "${SUBMODULE_DIR}" commit -m "initial commit"
}

# Clean up temp dirs
cleanup_fixtures() {
    [[ -n "${MONOREPO_DIR:-}" ]] && rm -rf "${MONOREPO_DIR}" || true
    [[ -n "${SUBMODULE_DIR:-}" ]] && rm -rf "${SUBMODULE_DIR}" || true
    return 0
}
