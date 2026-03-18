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

    # Export to monorepo, explicitly targeting 'main' branch
    run "${MONOREPO_BRIDGE}" export "${base_sha}" main
    [ "$status" -eq 0 ]
    [[ "$output" == *"1 commit(s) applied"* ]]

    # Verify the commit landed in monorepo under prefix
    run git -C "${MONOREPO_DIR}" show main:"${prefix}/fix.txt"
    [ "$status" -eq 0 ]
    [ "$output" = "fix content" ]
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
    "${MONOREPO_BRIDGE}" export "${base_sha}" main

    # Export again — should skip
    run "${MONOREPO_BRIDGE}" export "${base_sha}" main
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

@test "export: restores monorepo to original branch" {
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

    # Monorepo is on 'main' before export
    local mono_branch_before
    mono_branch_before=$(git -C "${MONOREPO_DIR}" rev-parse --abbrev-ref HEAD)

    run "${MONOREPO_BRIDGE}" export "${base_sha}" export-target
    [ "$status" -eq 0 ]

    # Verify monorepo is back on original branch
    local mono_branch_after
    mono_branch_after=$(git -C "${MONOREPO_DIR}" rev-parse --abbrev-ref HEAD)
    [ "${mono_branch_after}" = "${mono_branch_before}" ]
}

# --- sync tests ---------------------------------------------------------------

@test "sync: shows help with --help" {
    run "${MONOREPO_BRIDGE}" sync --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Pull latest changes"* ]]
}

@test "sync: pulls new monorepo commits into submodule" {
    local prefix="projects/mylib"

    # Create a remote for the monorepo so sync can fetch from it
    create_monorepo_remote

    # Split and create submodule
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Add a new commit to monorepo and push to remote
    monorepo_commit "${prefix}" "sync-test.txt" "synced content" "feat: sync test commit"
    monorepo_push

    # Sync: split + fetch + cherry-pick
    run "${MONOREPO_BRIDGE}" sync main
    [ "$status" -eq 0 ]
    [[ "$output" == *"Sync complete"* ]]
    [[ "$output" == *"1 new commit(s)"* ]]

    # Verify the file arrived
    [ -f "sync-test.txt" ]
    [ "$(cat sync-test.txt)" = "synced content" ]
}

@test "sync: reports up to date when no new commits" {
    local prefix="projects/mylib"
    create_monorepo_remote
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    run "${MONOREPO_BRIDGE}" sync main
    [ "$status" -eq 0 ]
    [[ "$output" == *"Already up to date"* ]]
}

@test "sync: saves branch tracking on first run" {
    local prefix="projects/mylib"
    create_monorepo_remote
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Explicit branch saves tracking
    "${MONOREPO_BRIDGE}" sync main

    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    local tracked
    tracked=$(git config --local --get "branch.${current_branch}.bridge-tracks")
    [ "${tracked}" = "main" ]
}

@test "sync: reuses saved branch tracking on subsequent runs" {
    local prefix="projects/mylib"
    create_monorepo_remote
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # First sync saves tracking
    "${MONOREPO_BRIDGE}" sync main

    # Add a new commit and push
    monorepo_commit "${prefix}" "second.txt" "second" "feat: second"
    monorepo_push

    # Second sync should use saved tracking (no branch arg needed)
    run "${MONOREPO_BRIDGE}" sync
    [ "$status" -eq 0 ]
    [[ "$output" == *"Using tracked monorepo branch: main"* ]]
    [ -f "second.txt" ]
}

@test "sync: cherry-picks multiple commits in order" {
    local prefix="projects/mylib"
    create_monorepo_remote
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Add multiple commits to monorepo and push
    monorepo_commit "${prefix}" "first.txt" "1" "feat: first"
    monorepo_commit "${prefix}" "second.txt" "2" "feat: second"
    monorepo_commit "${prefix}" "third.txt" "3" "feat: third"
    monorepo_push

    run "${MONOREPO_BRIDGE}" sync main
    [ "$status" -eq 0 ]
    [[ "$output" == *"3 new commit(s)"* ]]

    # Verify all files arrived and commit order is correct
    [ -f "first.txt" ]
    [ -f "second.txt" ]
    [ -f "third.txt" ]

    # Verify order: first should come before second in log
    local log
    log=$(git log --oneline --format="%s")
    local first_pos second_pos third_pos
    first_pos=$(echo "${log}" | grep -n "feat: first" | cut -d: -f1)
    second_pos=$(echo "${log}" | grep -n "feat: second" | cut -d: -f1)
    third_pos=$(echo "${log}" | grep -n "feat: third" | cut -d: -f1)
    # Most recent (third) should be at line 1
    [ "${third_pos}" -lt "${second_pos}" ]
    [ "${second_pos}" -lt "${first_pos}" ]
}

@test "sync: skips commits already in submodule" {
    local prefix="projects/mylib"
    create_monorepo_remote
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Add commit to monorepo and push
    monorepo_commit "${prefix}" "first.txt" "1" "feat: first"
    monorepo_push

    # Sync once
    "${MONOREPO_BRIDGE}" sync main

    # Add another commit and push
    monorepo_commit "${prefix}" "second.txt" "2" "feat: second"
    monorepo_push

    # Sync again — should only pick the new one
    run "${MONOREPO_BRIDGE}" sync main
    [ "$status" -eq 0 ]
    [[ "$output" == *"1 new commit(s)"* ]]
    [ -f "second.txt" ]
}

# --- auto-detect tests --------------------------------------------------------

@test "auto-detect: normalize_name matches composable_kernel to composablekernel" {
    # Test via setup --prefix auto-detection: create a monorepo with 'composablekernel' dir
    # and a submodule with origin URL containing 'composable_kernel'
    local mono_dir
    mono_dir="$(mktemp -d)"
    git -C "${mono_dir}" init -b main
    git -C "${mono_dir}" config user.email "test@test.com"
    git -C "${mono_dir}" config user.name "Test"
    mkdir -p "${mono_dir}/projects/composablekernel"
    echo "ck" > "${mono_dir}/projects/composablekernel/README.md"
    git -C "${mono_dir}" add .
    git -C "${mono_dir}" commit -m "init"

    local sub_dir
    sub_dir="$(mktemp -d)"
    git -C "${sub_dir}" init -b main
    git -C "${sub_dir}" config user.email "test@test.com"
    git -C "${sub_dir}" config user.name "Test"
    echo "ck" > "${sub_dir}/README.md"
    git -C "${sub_dir}" add .
    git -C "${sub_dir}" commit -m "init"
    # Set origin URL with underscored name
    git -C "${sub_dir}" remote add origin "https://github.com/ROCm/composable_kernel.git"

    cd "${sub_dir}"
    # Run setup which internally calls auto_detect_prefix
    # It should fuzzy-match composable_kernel -> composablekernel
    run "${MONOREPO_BRIDGE}" setup "${mono_dir}"
    [ "$status" -eq 0 ]
    [ "$(git config --local --get bridge.prefix)" = "projects/composablekernel" ]

    rm -rf "${mono_dir}" "${sub_dir}"
}

@test "auto-detect: bridge_config_auto_detect from existing remote" {
    local prefix="projects/mylib"
    create_monorepo_remote
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"

    # Manually set up the remote with split-branch refspec (like rocm-ck)
    git remote add mono-remote "${MONOREPO_DIR}"
    git config "remote.mono-remote.fetch" "+refs/heads/bridge-split/*:refs/remotes/mono-remote/*"
    git fetch mono-remote

    # Also set origin URL to a matching name for prefix detection
    git remote set-url origin "https://github.com/test/mylib.git"

    # Run a command that triggers auto-detect (non-interactive, will auto-confirm)
    run "${MONOREPO_BRIDGE}" sync main
    [ "$status" -eq 0 ]

    # Verify config was saved
    [ "$(git config --local --get bridge.remote)" = "mono-remote" ]
    [ "$(git config --local --get bridge.prefix)" = "projects/mylib" ]
    [ "$(git config --local --get bridge.split-prefix)" = "bridge-split" ]
}

@test "require_bridge_config: fails when only partial config exists" {
    create_submodule "projects/mylib"
    cd "${SUBMODULE_DIR}"

    # Set only remote, missing monorepo-path and prefix
    git config --local bridge.remote "some-remote"

    run "${MONOREPO_BRIDGE}" pick abc123
    [ "$status" -ne 0 ]
    # Should fail because monorepo-path and prefix are missing
}

# --- pick: exact subject matching tests ---------------------------------------

@test "pick: matches exact subject, not substring" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"

    # Create two commits with similar subjects
    monorepo_commit "${prefix}" "update-config.txt" "config" "fix: update config"
    monorepo_commit "${prefix}" "update.txt" "update" "fix: update"
    local target_sha
    target_sha=$(git rev-parse HEAD)

    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Reset to before both commits
    git reset --hard HEAD~2

    # Pick the "fix: update" commit — should NOT pick "fix: update config"
    run "${MONOREPO_BRIDGE}" pick "${target_sha}"
    [ "$status" -eq 0 ]

    # Should have the "update.txt" file but NOT "update-config.txt"
    [ -f "update.txt" ]
    [ ! -f "update-config.txt" ]
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

    # 5. Export submodule commit to monorepo, targeting 'main'
    "${MONOREPO_BRIDGE}" export "${sub_base}" main

    # Verify it landed in monorepo on the main branch
    run git -C "${MONOREPO_DIR}" show main:"${prefix}/subfix.txt"
    [ "$status" -eq 0 ]

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
