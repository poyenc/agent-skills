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

# --- export tests (fetch + subtree merge) -------------------------------------

@test "export: shows help with --help" {
    run "${MONOREPO_BRIDGE}" export --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Export commits from the submodule"* ]]
}

@test "export: exports submodule commits to monorepo via fetch + subtree merge" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Add commits in submodule
    echo "fix content" > fix.txt
    git add fix.txt
    git commit -m "fix: patch in submodule"

    # Export to monorepo, explicitly targeting 'main' branch
    run "${MONOREPO_BRIDGE}" export main
    [ "$status" -eq 0 ]

    # Verify the commit landed in monorepo under prefix
    run git -C "${MONOREPO_DIR}" show main:"${prefix}/fix.txt"
    [ "$status" -eq 0 ]
    [ "$output" = "fix content" ]

    # Verify split branch has same hash as submodule HEAD
    local split_sha sub_sha
    split_sha=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main")
    sub_sha=$(git rev-parse HEAD)
    [ "${split_sha}" = "${sub_sha}" ]

    # Verify monorepo subtree tree matches split tree
    local mono_subtree split_tree
    mono_subtree=$(git -C "${MONOREPO_DIR}" rev-parse "main:${prefix}")
    split_tree=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main^{tree}")
    [ "${mono_subtree}" = "${split_tree}" ]
}

@test "export: handles empty commit range" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Export with no new commits — split branch already matches submodule
    run "${MONOREPO_BRIDGE}" export main
    [ "$status" -eq 0 ]
    [[ "$output" == *"up to date"* ]] || [[ "$output" == *"No commits to export"* ]] || [[ "$output" == *"Already"* ]]
}

@test "export: preserves identical commit hashes on split branch" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Make two commits
    echo "first" > first.txt
    git add first.txt
    git commit -m "feat: first"
    local first_sha
    first_sha=$(git rev-parse HEAD)

    echo "second" > second.txt
    git add second.txt
    git commit -m "feat: second"
    local second_sha
    second_sha=$(git rev-parse HEAD)

    # Export
    run "${MONOREPO_BRIDGE}" export main
    [ "$status" -eq 0 ]

    # Split branch tip must be the same SHA as submodule HEAD
    local split_sha
    split_sha=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main")
    [ "${split_sha}" = "${second_sha}" ]

    # The first commit should also be present with the same SHA
    run git -C "${MONOREPO_DIR}" log --format="%H" "bridge-split/main" --grep="feat: first" -1
    [ "$output" = "${first_sha}" ]
}

@test "export: restores monorepo to original branch" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    echo "fix" > fix.txt
    git add fix.txt
    git commit -m "fix: patch"

    # Monorepo is on 'main' before export
    local mono_branch_before
    mono_branch_before=$(git -C "${MONOREPO_DIR}" rev-parse --abbrev-ref HEAD)

    run "${MONOREPO_BRIDGE}" export main
    [ "$status" -eq 0 ]

    # Verify monorepo is back on original branch
    local mono_branch_after
    mono_branch_after=$(git -C "${MONOREPO_DIR}" rev-parse --abbrev-ref HEAD)
    [ "${mono_branch_after}" = "${mono_branch_before}" ]
}

# --- sync tests (rebase) -----------------------------------------------------

@test "sync: shows help with --help" {
    run "${MONOREPO_BRIDGE}" sync --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Pull latest changes"* ]]
}

@test "sync: pulls new monorepo commits into submodule via rebase" {
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

    # Sync
    run "${MONOREPO_BRIDGE}" sync main
    [ "$status" -eq 0 ]
    [[ "$output" == *"Sync complete"* ]]

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

@test "sync: rebases local work on top of new monorepo commits" {
    local prefix="projects/mylib"
    create_monorepo_remote
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Add a local commit in submodule
    echo "local work" > local.txt
    git add local.txt
    git commit -m "feat: local work"

    # Add commits to monorepo and push
    monorepo_commit "${prefix}" "upstream.txt" "upstream" "feat: upstream change"
    monorepo_push

    # Sync — local work should be rebased on top of upstream
    run "${MONOREPO_BRIDGE}" sync main
    [ "$status" -eq 0 ]

    # Both files should exist
    [ -f "local.txt" ]
    [ -f "upstream.txt" ]

    # Local commit should be on top (most recent)
    local top_subject
    top_subject=$(git log --format="%s" -1)
    [ "${top_subject}" = "feat: local work" ]
}

@test "sync: includes merge commit changes from monorepo" {
    local prefix="projects/mylib"
    create_monorepo_remote
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Simulate a merge in monorepo: create a branch, commit, merge back
    cd "${MONOREPO_DIR}"
    git checkout -b develop
    monorepo_commit "${prefix}" "develop-feature.txt" "from develop" "feat: develop feature"
    git checkout main
    git merge --no-ff develop -m "Merge branch 'develop' into main"
    monorepo_push

    # Sync — should bring in the merge commit's file changes
    cd "${SUBMODULE_DIR}"
    run "${MONOREPO_BRIDGE}" sync main
    [ "$status" -eq 0 ]

    # The file from the develop branch should be present
    [ -f "develop-feature.txt" ]
    [ "$(cat develop-feature.txt)" = "from develop" ]
}

# --- reset tests --------------------------------------------------------------

@test "reset: resets all three branches to target commit" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Record the base state
    local base_sha
    base_sha=$(git rev-parse HEAD)
    local base_tree
    base_tree=$(git rev-parse "HEAD^{tree}")

    # Add a commit and export
    echo "to be reset" > reset-me.txt
    git add reset-me.txt
    git commit -m "feat: will be reset"

    "${MONOREPO_BRIDGE}" export main

    # Verify export worked
    [ -f "reset-me.txt" ]

    # Now reset all three branches back to base
    # Step 1: reset submodule
    git reset --hard "${base_sha}"
    [ ! -f "reset-me.txt" ]

    # Step 2: reset split branch (same SHA — shared history)
    git -C "${MONOREPO_DIR}" checkout "bridge-split/main"
    git -C "${MONOREPO_DIR}" reset --hard "${base_sha}"

    # Step 3: reset monorepo (find commit by tree match)
    local mono_target
    mono_target=$(git -C "${MONOREPO_DIR}" log --format="%H" main | while read sha; do
        subtree=$(git -C "${MONOREPO_DIR}" rev-parse "${sha}:${prefix}" 2>/dev/null)
        if [[ "${subtree}" == "${base_tree}" ]]; then
            echo "${sha}"
            break
        fi
    done)
    git -C "${MONOREPO_DIR}" checkout main
    git -C "${MONOREPO_DIR}" reset --hard "${mono_target}"

    # Verify all three branches are in sync
    local split_sha sub_sha
    split_sha=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main")
    sub_sha=$(git rev-parse HEAD)
    [ "${split_sha}" = "${sub_sha}" ]

    local mono_subtree split_tree
    mono_subtree=$(git -C "${MONOREPO_DIR}" rev-parse "main:${prefix}")
    split_tree=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main^{tree}")
    [ "${mono_subtree}" = "${split_tree}" ]

    # File should be gone
    [ ! -f "reset-me.txt" ]
    run git -C "${MONOREPO_DIR}" show "main:${prefix}/reset-me.txt"
    [ "$status" -ne 0 ]
}

# --- verify tests -------------------------------------------------------------

@test "verify: all three branches in sync after export" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Add commit and export
    echo "verify test" > verify.txt
    git add verify.txt
    git commit -m "feat: verify test"

    "${MONOREPO_BRIDGE}" export main

    # Check 1: split branch == submodule (same hash)
    local split_sha sub_sha
    split_sha=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main")
    sub_sha=$(git rev-parse HEAD)
    [ "${split_sha}" = "${sub_sha}" ]

    # Check 2: monorepo subtree tree == split branch tree
    local mono_subtree split_tree
    mono_subtree=$(git -C "${MONOREPO_DIR}" rev-parse "main:${prefix}")
    split_tree=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main^{tree}")
    [ "${mono_subtree}" = "${split_tree}" ]
}

@test "verify: detects mismatch when branches diverge" {
    local prefix="projects/mylib"
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Add commit to submodule WITHOUT exporting
    echo "diverged" > diverged.txt
    git add diverged.txt
    git commit -m "feat: diverged"

    # Check 1 should fail — split branch doesn't have this commit
    local split_sha sub_sha
    split_sha=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main")
    sub_sha=$(git rev-parse HEAD)
    [ "${split_sha}" != "${sub_sha}" ]
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

# --- integration tests --------------------------------------------------------

@test "integration: full export-reset cycle" {
    local prefix="projects/mylib"

    # 1. Split in monorepo
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    # 2. Create submodule from split and set up bridge
    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # Record base state
    local base_sha
    base_sha=$(git rev-parse HEAD)

    # 3. Add a commit in submodule
    echo "submodule fix" > subfix.txt
    git add subfix.txt
    git commit -m "fix: submodule-only fix"
    local fix_sha
    fix_sha=$(git rev-parse HEAD)

    # 4. Export to monorepo
    run "${MONOREPO_BRIDGE}" export main
    [ "$status" -eq 0 ]

    # Verify it landed in monorepo under prefix
    run git -C "${MONOREPO_DIR}" show main:"${prefix}/subfix.txt"
    [ "$status" -eq 0 ]
    [ "$output" = "submodule fix" ]

    # Verify all three branches are in sync
    local split_sha sub_sha
    split_sha=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main")
    sub_sha=$(git rev-parse HEAD)
    [ "${split_sha}" = "${sub_sha}" ]

    local mono_subtree split_tree
    mono_subtree=$(git -C "${MONOREPO_DIR}" rev-parse "main:${prefix}")
    split_tree=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main^{tree}")
    [ "${mono_subtree}" = "${split_tree}" ]

    # 5. Reset back to base
    local base_tree
    base_tree=$(git rev-parse "${base_sha}^{tree}")

    # Reset submodule
    git reset --hard "${base_sha}"

    # Reset split branch
    git -C "${MONOREPO_DIR}" checkout "bridge-split/main"
    git -C "${MONOREPO_DIR}" reset --hard "${base_sha}"

    # Reset monorepo (find by tree match)
    local mono_target
    mono_target=$(git -C "${MONOREPO_DIR}" log --format="%H" main | while read sha; do
        subtree=$(git -C "${MONOREPO_DIR}" rev-parse "${sha}:${prefix}" 2>/dev/null)
        if [[ "${subtree}" == "${base_tree}" ]]; then
            echo "${sha}"
            break
        fi
    done)
    git -C "${MONOREPO_DIR}" checkout main
    git -C "${MONOREPO_DIR}" reset --hard "${mono_target}"

    # 6. Verify reset — all three in sync, file gone
    split_sha=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main")
    sub_sha=$(git rev-parse HEAD)
    [ "${split_sha}" = "${sub_sha}" ]
    [ "${sub_sha}" = "${base_sha}" ]

    mono_subtree=$(git -C "${MONOREPO_DIR}" rev-parse "main:${prefix}")
    split_tree=$(git -C "${MONOREPO_DIR}" rev-parse "bridge-split/main^{tree}")
    [ "${mono_subtree}" = "${split_tree}" ]

    [ ! -f "subfix.txt" ]
}

@test "integration: export + sync round-trip with merge commits" {
    local prefix="projects/mylib"
    create_monorepo_remote

    # 1. Split and create submodule
    cd "${MONOREPO_DIR}"
    git config --local bridge.prefix "${prefix}"
    "${MONOREPO_BRIDGE}" split

    create_submodule_from_split "bridge-split/main"
    cd "${SUBMODULE_DIR}"
    "${MONOREPO_BRIDGE}" setup --prefix="${prefix}" "${MONOREPO_DIR}"

    # 2. Add a commit in submodule and export
    echo "feature" > feature.txt
    git add feature.txt
    git commit -m "feat: submodule feature"

    "${MONOREPO_BRIDGE}" export main

    # Push monorepo to remote
    git -C "${MONOREPO_DIR}" push origin main 2>/dev/null

    # 3. Simulate merge in monorepo (someone merges develop)
    cd "${MONOREPO_DIR}"
    git checkout -b develop
    monorepo_commit "${prefix}" "develop.txt" "from develop" "feat: develop work"
    git checkout main
    git merge --no-ff develop -m "Merge branch 'develop'"
    monorepo_push

    # 4. Add another local commit in submodule
    cd "${SUBMODULE_DIR}"
    echo "local" > local.txt
    git add local.txt
    git commit -m "feat: local work"

    # 5. Sync — should bring in merge commit changes and rebase local work
    run "${MONOREPO_BRIDGE}" sync main
    [ "$status" -eq 0 ]

    # Both files should exist: develop.txt from merge, local.txt from local work
    [ -f "develop.txt" ]
    [ -f "local.txt" ]
    [ -f "feature.txt" ]
}
