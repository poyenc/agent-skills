#!/usr/bin/env bats

load test_helper

# --- setup tests --------------------------------------------------------------

setup() {
    create_monorepo "projects/mylib"
}

teardown() {
    cleanup_fixtures
}

@test "setup: shows help with --help" {
    run "${MONOREPO_BRIDGE}" setup --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Set up the bridge"* ]]
}

@test "setup: configures bridge with explicit path and prefix" {
    create_submodule "projects/mylib"
    cd "${SUBMODULE_DIR}"

    run "${MONOREPO_BRIDGE}" setup --prefix=projects/mylib "${MONOREPO_DIR}"
    [ "$status" -eq 0 ]

    # Verify git config was written
    [ "$(git config --local --get bridge.prefix)" = "projects/mylib" ]
    [ "$(git config --local --get bridge.remote)" = "bridge-upstream" ]
    [ "$(git config --local --get bridge.monorepo-path)" = "${MONOREPO_DIR}" ]
    [ "$(git config --local --get bridge.split-prefix)" = "bridge-split" ]
}

@test "setup: custom remote and split-prefix" {
    create_submodule "projects/mylib"
    cd "${SUBMODULE_DIR}"

    run "${MONOREPO_BRIDGE}" setup --prefix=projects/mylib --remote=rocm-ck --split-prefix=ck-split "${MONOREPO_DIR}"
    [ "$status" -eq 0 ]
    [ "$(git config --local --get bridge.remote)" = "rocm-ck" ]
    [ "$(git config --local --get bridge.split-prefix)" = "ck-split" ]
}

@test "setup: fails when not in a git repo" {
    local tmpdir
    tmpdir="$(mktemp -d)"
    cd "${tmpdir}"

    run "${MONOREPO_BRIDGE}" setup "${MONOREPO_DIR}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Not inside a git repository"* ]]

    rm -rf "${tmpdir}"
}

@test "setup: fails when monorepo path is invalid" {
    create_submodule "projects/mylib"
    cd "${SUBMODULE_DIR}"

    run "${MONOREPO_BRIDGE}" setup --prefix=projects/mylib /nonexistent/path
    [ "$status" -ne 0 ]
    [[ "$output" == *"not a git repository"* ]]
}

@test "setup: fails when prefix doesn't exist in monorepo" {
    create_submodule "projects/mylib"
    cd "${SUBMODULE_DIR}"

    run "${MONOREPO_BRIDGE}" setup --prefix=nonexistent/path "${MONOREPO_DIR}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"not found"* ]]
}

@test "setup: updates existing remote URL" {
    create_submodule "projects/mylib"
    cd "${SUBMODULE_DIR}"

    # First setup
    run "${MONOREPO_BRIDGE}" setup --prefix=projects/mylib "${MONOREPO_DIR}"
    [ "$status" -eq 0 ]

    # Second setup with same path (should update, not fail)
    run "${MONOREPO_BRIDGE}" setup --prefix=projects/mylib "${MONOREPO_DIR}"
    [ "$status" -eq 0 ]
    [[ "$output" == *"already exists"* ]]
}

# --- split tests --------------------------------------------------------------

@test "split: shows help with --help" {
    run "${MONOREPO_BRIDGE}" split --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Split a monorepo subdirectory"* ]]
}

@test "split: splits prefix into standalone branch" {
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "projects/mylib"

    run "${MONOREPO_BRIDGE}" split
    [ "$status" -eq 0 ]
    [[ "$output" == *"Done. Branch 'bridge-split/main'"* ]]

    # Verify the split branch exists and has the right content
    git log bridge-split/main --oneline -1
    run git ls-tree --name-only bridge-split/main
    [[ "$output" == *"README.md"* ]]
}

@test "split: uses custom split-prefix" {
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "projects/mylib"

    run "${MONOREPO_BRIDGE}" split --split-prefix=ck-split
    [ "$status" -eq 0 ]

    # Verify branch uses custom prefix
    run git rev-parse --verify ck-split/main
    [ "$status" -eq 0 ]
}

@test "split: splits a named source branch" {
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "projects/mylib"

    # Create a feature branch with a commit
    git checkout -b feature-x
    monorepo_commit "projects/mylib" "feature.txt" "new feature" "feat: add feature X"
    git checkout main

    run "${MONOREPO_BRIDGE}" split feature-x
    [ "$status" -eq 0 ]
    [[ "$output" == *"bridge-split/feature-x"* ]]
}

@test "split: --rejoin makes subsequent splits incremental" {
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "projects/mylib"

    # First split with --rejoin
    run "${MONOREPO_BRIDGE}" split --rejoin
    [ "$status" -eq 0 ]

    # Add another commit
    monorepo_commit "projects/mylib" "second.txt" "second" "feat: second commit"

    # Second split should be incremental
    run "${MONOREPO_BRIDGE}" split --rejoin
    [ "$status" -eq 0 ]
}

@test "split: fails when prefix directory doesn't exist" {
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "nonexistent"

    run "${MONOREPO_BRIDGE}" split
    [ "$status" -ne 0 ]
    [[ "$output" == *"not found"* ]]
}

# --- pick tests ---------------------------------------------------------------

@test "pick: shows help with --help" {
    run "${MONOREPO_BRIDGE}" pick --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Cherry-pick a monorepo commit"* ]]
}

@test "pick: cherry-picks a monorepo commit into submodule" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"

    # Split current state
    "${MONOREPO_BRIDGE}" split

    # Add a new commit to monorepo
    monorepo_commit "${prefix}" "new-file.txt" "new content" "feat: add new file"
    local mono_sha
    mono_sha=$(git rev-parse HEAD)

    # Re-split to include the new commit
    "${MONOREPO_BRIDGE}" split

    # Create submodule from the split (before the new commit)
    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"

    # Setup bridge
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Reset to before the new commit to simulate needing to pick it
    git reset --hard HEAD~1

    # Pick the commit
    run "${MONOREPO_BRIDGE}" pick "${mono_sha}"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Done! Commit applied"* ]]

    # Verify the file was added
    [ -f "new-file.txt" ]
    [ "$(cat new-file.txt)" = "new content" ]
}

@test "pick: warns when commit doesn't touch prefix" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"

    # Add commit outside prefix
    echo "other" > "${MONOREPO_DIR}/other-file.txt"
    git -C "${MONOREPO_DIR}" add .
    git -C "${MONOREPO_DIR}" commit -m "feat: unrelated change"
    local mono_sha
    mono_sha=$(git -C "${MONOREPO_DIR}" rev-parse HEAD)

    # Split and create submodule
    "${MONOREPO_BRIDGE}" split
    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Pick commit that doesn't touch prefix
    run "${MONOREPO_BRIDGE}" pick "${mono_sha}"
    [ "$status" -eq 0 ]
    [[ "$output" == *"does not touch any files"* ]]
}

@test "pick: fails when no split commit found" {
    local prefix="projects/mylib"
    create_submodule "${prefix}"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Add a commit to monorepo but don't split
    monorepo_commit "${prefix}" "unsplit.txt" "content" "feat: unsplit commit"
    local mono_sha
    mono_sha=$(git -C "${MONOREPO_DIR}" rev-parse HEAD)

    run "${MONOREPO_BRIDGE}" pick "${mono_sha}"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Could not find a matching subtree-split commit"* ]]
}

# --- export tests -------------------------------------------------------------

@test "export: shows help with --help" {
    run "${MONOREPO_BRIDGE}" export --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Export commits from the submodule"* ]]
}

@test "export: exports submodule commits to monorepo" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Add commits in submodule
    local base_sha
    base_sha=$(git rev-parse HEAD)
    echo "fix content" > fix.txt
    git add fix.txt
    git commit -m "fix: patch in submodule"

    # Export to monorepo
    run "${MONOREPO_BRIDGE}" export "${base_sha}"
    [ "$status" -eq 0 ]
    [[ "$output" == *"1 commit(s) applied"* ]]

    # Verify the commit landed in monorepo under prefix
    [ -f "${MONOREPO_DIR}/${prefix}/fix.txt" ]
}

@test "export: skips already-applied commits" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    local base_sha
    base_sha=$(git rev-parse HEAD)
    echo "fix" > fix.txt
    git add fix.txt
    git commit -m "fix: first patch"

    # Export once
    "${MONOREPO_BRIDGE}" export "${base_sha}"

    # Export again — should skip
    run "${MONOREPO_BRIDGE}" export "${base_sha}"
    [ "$status" -eq 0 ]
    [[ "$output" == *"already applied"* ]]
}

@test "export: handles empty commit range" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    run "${MONOREPO_BRIDGE}" export HEAD
    [ "$status" -eq 0 ]
    [[ "$output" == *"No commits to export"* ]]
}

@test "export: creates target branch in monorepo" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    local base_sha
    base_sha=$(git rev-parse HEAD)
    echo "fix" > fix.txt
    git add fix.txt
    git commit -m "fix: patch"

    run "${MONOREPO_BRIDGE}" export "${base_sha}" my-feature-branch
    [ "$status" -eq 0 ]

    # Verify branch was created in monorepo
    run git -C "${MONOREPO_DIR}" rev-parse --verify my-feature-branch
    [ "$status" -eq 0 ]
}

# --- integration tests --------------------------------------------------------

@test "integration: full round-trip (split -> setup -> pick -> export)" {
    local prefix="projects/mylib"

    # 1. Add a commit in monorepo
    monorepo_commit "${prefix}" "feature.txt" "mono feature" "feat: monorepo feature"
    local mono_feature_sha
    mono_feature_sha=$(git -C "${MONOREPO_DIR}" rev-parse HEAD)

    # 2. Split in monorepo
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    # 3. Create submodule from split and set up bridge
    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Verify the monorepo feature is in the submodule
    [ -f "feature.txt" ]

    # 4. Add a commit in submodule
    local sub_base
    sub_base=$(git rev-parse HEAD)
    echo "submodule fix" > subfix.txt
    git add subfix.txt
    git commit -m "fix: submodule-only fix"

    # 5. Export submodule commit to monorepo
    "${MONOREPO_BRIDGE}" export "${sub_base}"

    # Verify it landed in monorepo
    [ -f "${MONOREPO_DIR}/${prefix}/subfix.txt" ]

    # 6. Add another commit in monorepo on a new branch, split, and pick it
    cd "${MONOREPO_DIR}"
    git checkout main
    git checkout -b feature-y
    monorepo_commit "${prefix}" "second-feature.txt" "second" "feat: second monorepo feature"
    local mono_second_sha
    mono_second_sha=$(git rev-parse HEAD)
    "${MONOREPO_BRIDGE}" split feature-y

    # Pick in submodule
    cd "${SUBMODULE_DIR}"
    git fetch "$(git config --get bridge.remote)"
    "${MONOREPO_BRIDGE}" pick "${mono_second_sha}"
    [ -f "second-feature.txt" ]
}
