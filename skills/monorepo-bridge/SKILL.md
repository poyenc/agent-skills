---
name: monorepo-bridge
description: Bidirectional commit transfer between monorepos and standalone submodule repos. Use when the user wants to export, split, sync, reset, or update commits between a monorepo and a submodule, or when they ask how the monorepo/submodule workflow works. Also trigger on mentions of "monorepo bridge", "subtree bridge", "subtree split", "update the monorepo branch", "sync from monorepo", "pull monorepo changes", "reset bridge", "undo export", porting commits between mono and sub repos, or setting up a bridge.
---

# Monorepo Bridge

Help users move commits bidirectionally between a monorepo (a repo containing multiple projects in subdirectories) and standalone submodule repos that mirror one of those subdirectories.

## Scope

This skill operates in **two contexts only**:

1. **Inside a submodule directory** — where `.git` is a file (not a directory) and `git rev-parse --show-toplevel` resolves to the submodule root.
2. **Inside the monorepo directory** — for `split` operations only.

**NEVER run bridge operations from a parent repo that contains a submodule.** A parent repo is NOT a submodule. Bridge config (`[bridge]` in git config) is only valid inside a real submodule. If you find bridge config or bridge remotes in a parent repo, they are stale/erroneous — ignore them and clean them up.

### Pre-flight Check (mandatory before any operation)

Before executing any bridge operation, verify your working directory:

```bash
# Are we in a submodule?
TOP=$(git rev-parse --show-toplevel)
GIT_FILE=$(cat .git 2>/dev/null)
if [[ -f .git ]] && [[ "${TOP}" == "$(pwd)" ]]; then
    echo "OK: inside submodule at ${TOP}"
else
    echo "WARNING: not inside a submodule — do NOT run bridge operations here"
fi
```

If the check fails and the user asked for a sync/export, **ask the user** which directory to operate in. Do not guess.

## Concepts

A **monorepo** contains a subdirectory (the **prefix**) whose content is also maintained as a standalone repo used as a **submodule** in other projects. Commits need to flow in both directions:

- **Downstream** (mono -> sub): A fix lands in the monorepo and needs to be applied to the submodule.
- **Upstream** (sub -> mono): A fix developed in the submodule needs to go back to the monorepo.

The bridge works via `git subtree split`, which extracts the prefix subdirectory into a standalone branch where the prefix directory becomes the root. This split branch is compatible with the submodule's history.

## CLI Tool

The `monorepo-bridge` CLI tool is bundled at `bin/monorepo-bridge` relative to this skill file. Check if it's available:

```bash
SKILL_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]:-$0}")")"
BRIDGE="${SKILL_DIR}/bin/monorepo-bridge"
if [[ ! -x "${BRIDGE}" ]]; then
    # Fall back to PATH
    BRIDGE="monorepo-bridge"
fi
```

If the tool is not available, use the fallback git commands described in each operation below.

## Behavior Modes

### Mode A: Explain the Workflow

When the user asks how the workflow works, explain:

1. **The setup**: A monorepo has a subdirectory (e.g., `projects/mylib/`) that is also used as a standalone submodule in other repos.

2. **The bridge mechanism**: `git subtree split` extracts the subdirectory into a standalone branch where files are at the root (not nested under the prefix). This branch is compatible with the submodule's git history.

3. **The six operations:**

   | Operation | Runs from | Purpose |
   |-----------|-----------|---------|
   | `setup` | submodule | Add monorepo as remote, configure fetch |
   | `split` | monorepo | Extract prefix into standalone branch |
   | `export` | submodule | Send submodule commits back to monorepo |
   | `sync` | submodule | Pull all new monorepo changes into submodule |
   | `reset` | submodule | Reset all three branches to the same HEAD commit |
   | `verify` | submodule | Verify all three branches are in sync |

4. **Typical sequences:**
   - **First-time setup:** `split` (monorepo) -> `setup` (submodule)
   - **Pulling all changes downstream:** `sync` (re-splits, fetches, rebases local work onto updated split tip)
   - **Pushing changes upstream:** `export` (fetch + update split + subtree merge into monorepo)
   - **Undoing an export:** `reset` (same direction as export: submodule -> split branch -> monorepo branch)

Use concrete examples from the user's repo when possible (actual branch names, paths, commits).

### Mode B: Execute an Operation

**CRITICAL RULE: Never assume — always ask the user.** Do not guess monorepo paths, branch names, remote names, or target branches. If information is missing, ask. Do not infer values from a parent repo's config — only read config from the current submodule.

**Phase 0: Verify Working Directory**

Run the pre-flight check (see Scope section). If you are not inside a real submodule, STOP and ask the user which directory to use.

**Phase 1: Gather Required Information**

Ask the user for any information you don't already have. Do NOT proceed without it.

1. **Monorepo branch**: Ask which monorepo branch to sync from / export to. This is the FIRST question.
2. **Monorepo path**: If not configured (`git config --local --get bridge.monorepo-path`), ask the user.
3. **Local target branch**: Ask which local submodule branch to sync into — create from the split remote branch, or use an existing one. Ask the user for the name.
4. **Remote name**: Ask which remote name to use for fetching split branches. Do not assume a default name. Offer existing remotes if any match, or ask the user what name to create.

**Phase 2: Context Detection**

1. Check if the CLI tool is available (see CLI Tool section above).
2. Check if bridge is configured: `git config --local --get bridge.prefix`
3. Determine if you're in the monorepo or submodule:
   - Monorepo: has the prefix subdirectory, not a submodule itself
   - Submodule: has `bridge.remote` configured, or `.git` is a file (not directory)
4. **Check for existing split branches** in the monorepo before creating new ones:
   ```bash
   git -C /path/to/monorepo branch --list '*split*'
   ```
   If a matching split branch already exists, ask the user whether to use it or create a fresh one.
5. **Detect partial/sparse clones** before fetching:
   ```bash
   git -C /path/to/monorepo config --get remote.origin.promisor 2>/dev/null
   git -C /path/to/monorepo config --get remote.origin.partialclonefilter 2>/dev/null
   ```
   If the monorepo is a partial clone, use `file://` URL and `--filter=blob:none` for remotes and fetches. A direct path fetch will fail on partial clones.
6. If not configured, the CLI auto-detects config from existing remotes that have split-branch refspecs. If that also fails, guide through `monorepo-bridge setup`.

**Phase 3: Intent Mapping**

| User wants to... | Command | Direction |
|---|---|---|
| Update/sync from monorepo | `sync [monorepo-branch]` | mono -> sub |
| Push submodule changes to monorepo | `export` | sub -> mono |
| Undo export / reset all branches | `reset` | sub -> split -> mono |
| Verify branches are in sync | `verify` | check all three |
| Prepare monorepo for consumption | `split` | mono side |
| Set up the bridge | `setup <path>` | sub side |

**Phase 4: Execution**

Run the appropriate command. If the CLI tool is not available, use fallback commands:

**setup fallback:**
```bash
REMOTE_NAME="bridge-upstream"  # ask user for remote name
MONO="/path/to/monorepo"       # ask user for monorepo path

# Detect partial clone — use file:// URL if so
IS_PARTIAL=$(git -C "${MONO}" config --get remote.origin.partialclonefilter 2>/dev/null)
if [[ -n "${IS_PARTIAL}" ]]; then
    REMOTE_URL="file://${MONO}"
    FETCH_OPTS="--filter=blob:none"
else
    REMOTE_URL="${MONO}"
    FETCH_OPTS=""
fi

git remote add "${REMOTE_NAME}" "${REMOTE_URL}"
git config "remote.${REMOTE_NAME}.fetch" "+refs/heads/bridge-split/*:refs/remotes/${REMOTE_NAME}/*"
git fetch ${FETCH_OPTS} "${REMOTE_NAME}"
git config --local bridge.prefix "<prefix>"
git config --local bridge.remote "${REMOTE_NAME}"
git config --local bridge.monorepo-path "${MONO}"
git config --local bridge.split-prefix "bridge-split"
```

**split fallback:**
```bash
git subtree split --prefix=<prefix> --branch=bridge-split/<branch> <branch>
```

**export fallback:**

Export lands changes in two steps:
1. Fetch submodule commits into monorepo and update split branch (exact same hashes)
2. Subtree-merge split branch into monorepo tracking branch (auto-remaps paths)

This avoids `git am` entirely — no patches, no committer timestamp drift.
The split branch and submodule share identical commit hashes because the
commit objects are fetched directly. `git fetch <path>` does NOT add a remote.

```bash
MONO="/path/to/monorepo"       # from bridge.monorepo-path
SUB="$(git rev-parse --show-toplevel)"  # submodule path
SPLIT_PREFIX="bridge-split"    # from bridge.split-prefix
MONO_BRANCH="users/dev/feature"  # ask the user for monorepo branch
SPLIT_BRANCH="${SPLIT_PREFIX}/${MONO_BRANCH}"
SUB_BRANCH="$(git branch --show-current)"  # current submodule branch

# 1. Fetch submodule commits into monorepo object store (no remote added)
git -C "${MONO}" fetch "${SUB}" "${SUB_BRANCH}"

# 2. Update split branch to point at fetched commits (identical hashes)
git -C "${MONO}" branch -f "${SPLIT_BRANCH}" FETCH_HEAD

# 3. Subtree-merge split branch into monorepo tracking branch
git -C "${MONO}" checkout "${MONO_BRANCH}"
git -C "${MONO}" merge -s subtree --allow-unrelated-histories \
    "${SPLIT_BRANCH}" -m "<commit message>"

# 4. Restore original branch if different
ORIGINAL_BRANCH=$(git -C "${MONO}" branch --show-current)
if [[ "${ORIGINAL_BRANCH}" != "${MONO_BRANCH}" ]]; then
    git -C "${MONO}" checkout "${ORIGINAL_BRANCH}"
fi
```

**reset fallback:**

Reset undoes an export by resetting all three branches to the same HEAD commit.
The user typically runs this when they want to undo changes they just exported.
Direction follows export: submodule → split branch → monorepo tracking branch.

Ask the user which commit should be the new HEAD on the **submodule branch**
(since development happens here). The split branch and monorepo branch are then
reset to the corresponding commits.

```bash
MONO="/path/to/monorepo"       # from bridge.monorepo-path
PREFIX="projects/mylib"        # from bridge.prefix
SPLIT_PREFIX="bridge-split"    # from bridge.split-prefix
MONO_BRANCH="users/dev/feature"  # ask the user
SPLIT_BRANCH="${SPLIT_PREFIX}/${MONO_BRANCH}"

# Step 0: Show recent submodule commits and ASK the user for the new HEAD
git log --oneline -5
# (mandatory user checkpoint — wait for user to pick the new HEAD)
TARGET_SHA="<user-chosen-sha>"

# Step 1: Reset submodule branch
git reset --hard "${TARGET_SHA}"

# Step 2: Reset split branch to the same commit
#   The split branch shares the same commit hashes as the submodule branch,
#   so use the same SHA directly.
ORIGINAL_BRANCH=$(git -C "${MONO}" branch --show-current)
git -C "${MONO}" checkout "${SPLIT_BRANCH}"
git -C "${MONO}" reset --hard "${TARGET_SHA}"

# Step 3: Reset monorepo tracking branch
#   Find the monorepo commit whose subtree tree matches the target.
#   Walk back through monorepo commits to find the one where
#   <commit>:<prefix> matches the target's tree.
TARGET_TREE=$(git rev-parse "${TARGET_SHA}^{tree}")
MONO_TARGET=$(git -C "${MONO}" log --format="%H" "${MONO_BRANCH}" | while read sha; do
    SUBTREE=$(git -C "${MONO}" rev-parse "${sha}:${PREFIX}" 2>/dev/null)
    if [[ "${SUBTREE}" == "${TARGET_TREE}" ]]; then
        echo "${sha}"
        break
    fi
done)
git -C "${MONO}" checkout "${MONO_BRANCH}"
git -C "${MONO}" reset --hard "${MONO_TARGET}"

# Step 4: Restore original monorepo branch if needed
if [[ "${ORIGINAL_BRANCH}" != "${MONO_BRANCH}" ]]; then
    git -C "${MONO}" checkout "${ORIGINAL_BRANCH}"
fi

# Step 5: Run verify to confirm all branches are in sync
```

**verify fallback:**

Verify that all three branches (monorepo, split, submodule) are in sync by comparing tree objects.

```bash
MONO="/path/to/monorepo"       # from bridge.monorepo-path
PREFIX="projects/mylib"        # from bridge.prefix
SPLIT_PREFIX="bridge-split"    # from bridge.split-prefix
MONO_BRANCH="users/dev/feature"
SPLIT_BRANCH="${SPLIT_PREFIX}/${MONO_BRANCH}"

# Check 1: Split branch commit == Submodule branch commit (same hash)
SPLIT_SHA=$(git -C "${MONO}" rev-parse "${SPLIT_BRANCH}")
SUB_SHA=$(git rev-parse HEAD)
echo "Split branch:     ${SPLIT_SHA}"
echo "Submodule branch: ${SUB_SHA}"
if [[ "${SPLIT_SHA}" == "${SUB_SHA}" ]]; then
    echo "CHECK 1 PASS: same commit hash"
else
    echo "CHECK 1 FAIL: commit hashes differ"
fi

# Check 2: Monorepo subtree tree == Split branch tree (same tree object)
MONO_SUBTREE=$(git -C "${MONO}" rev-parse "${MONO_BRANCH}:${PREFIX}")
SPLIT_TREE=$(git -C "${MONO}" rev-parse "${SPLIT_BRANCH}^{tree}")
echo "Monorepo subtree tree: ${MONO_SUBTREE}"
echo "Split branch tree:     ${SPLIT_TREE}"
if [[ "${MONO_SUBTREE}" == "${SPLIT_TREE}" ]]; then
    echo "CHECK 2 PASS: same tree object"
else
    echo "CHECK 2 FAIL: tree objects differ"
fi
```

**sync fallback:**

Sync pulls monorepo changes (including merge commits) into the submodule by
rebasing local work onto the updated split branch tip. The split branch is
produced by `git subtree split`, which flattens all monorepo history (including
merges) into the correct tree. Rebasing onto it is simpler and more correct
than cherry-picking individual commits (which would skip merge commits).

```bash
REMOTE="rocm-ck"  # ask the user for remote name
MONO="/path/to/monorepo"  # ask the user for monorepo path
PREFIX="projects/mylib"
SPLIT_PREFIX="bridge-split"
MONO_BRANCH="users/dev/feature"  # ask the user for monorepo branch

# 1. Fetch monorepo branch from its remote
git -C "${MONO}" fetch origin "${MONO_BRANCH}"

# 2. Fast-forward monorepo's local branch
#    IMPORTANT: `branch -f` fails if the branch is checked out.
#    Check first and use `merge --ff-only` if checked out.
CHECKED_OUT=$(git -C "${MONO}" branch --show-current)
if [[ "${CHECKED_OUT}" == "${MONO_BRANCH}" ]]; then
    git -C "${MONO}" merge --ff-only "origin/${MONO_BRANCH}"
else
    git -C "${MONO}" branch -f "${MONO_BRANCH}" "origin/${MONO_BRANCH}"
fi

# 3. Check for existing split branches before re-splitting
git -C "${MONO}" branch --list '*split*/*'"${MONO_BRANCH}"
# Ask user: use existing split branch or create a fresh one?

# 4. Re-split the updated branch (if user chose to create fresh)
git -C "${MONO}" subtree split --prefix="${PREFIX}" \
    --branch="${SPLIT_PREFIX}/${MONO_BRANCH}" "${MONO_BRANCH}"

# 5. Add remote in submodule (detect partial clone first)
#    If monorepo is a partial clone, use file:// URL
IS_PARTIAL=$(git -C "${MONO}" config --get remote.origin.partialclonefilter 2>/dev/null)
if [[ -n "${IS_PARTIAL}" ]]; then
    REMOTE_URL="file://${MONO}"
    FETCH_OPTS="--filter=blob:none"
else
    REMOTE_URL="${MONO}"
    FETCH_OPTS=""
fi
git remote add "${REMOTE}" "${REMOTE_URL}" 2>/dev/null || true
git config "remote.${REMOTE}.fetch" "+refs/heads/${SPLIT_PREFIX}/*:refs/remotes/${REMOTE}/*"

# 6. Fetch updated split into submodule
git fetch ${FETCH_OPTS} "${REMOTE}"

# 7. Rebase local work onto the updated split branch tip
#    The split branch already contains the correct flattened result of all
#    monorepo commits including merges. Rebasing puts local (unexported)
#    commits on top.
git rebase "${REMOTE}/${MONO_BRANCH}"
```

## User Checkpoints

These are mandatory confirmation points — always ask, never skip.

### Before sync: check monorepo branch freshness

Before splitting, compare the local monorepo branch with its remote tracking branch:

```bash
git -C "${MONO}" fetch origin "${MONO_BRANCH}"
git -C "${MONO}" rev-list --left-right --count \
    "${MONO_BRANCH}...origin/${MONO_BRANCH}"
```

If the local branch is behind, **ask the user** if they want to pull (fast-forward) the monorepo branch first before splitting. Do not silently split a stale branch.

### After export: offer to push

After exporting submodule commits to the monorepo's local branch, **ask the user** if they want to push the updated monorepo branch to its remote. Do not push without asking.

### After export: verify sync

After export completes, run the **verify** check to confirm all three branches are in sync.

### Before reset: ask for new HEAD

The reset operation uses `git reset --hard`, which is destructive. **Always ask the user** which commit should be the new HEAD on the **submodule branch** (since that's where development happens). Show the recent commit log and wait for the user's choice before proceeding. Do not assume the commit to reset to.

### After reset: verify sync

After reset completes, run the **verify** check to confirm all three branches are in sync.

## Auto-Detection

The CLI tool can auto-detect bridge configuration without running `setup` if:
- An existing remote has a refspec that maps split branches (e.g., `+refs/heads/ck-split/*:refs/remotes/rocm-ck/*`)
- The remote URL points to a local monorepo path
- The prefix can be inferred by matching the submodule's origin URL against the monorepo structure

This means `export` and `sync` work immediately if there's already a suitable remote — no explicit `setup` needed.

## Branch Tracking

`sync` saves the mapping between submodule branch and monorepo branch in git config:

```
branch.<sub-branch>.bridge-tracks = <mono-branch>
```

On first run, `sync` auto-detects the closest matching monorepo branch by commit distance and saves the mapping. Subsequent runs reuse the saved mapping. Override with `sync <monorepo-branch>`.

## Edge Cases

- **Blobless/partial clones:** If the monorepo is a partial clone, use `file://` URL and `--filter=blob:none` for remotes and fetches. Detect with `git config --get remote.origin.partialclonefilter`. Direct path fetches (`/path/to/repo`) will fail on partial clones with "lazy fetching disabled" errors.
- **Branch checked out in monorepo:** `git branch -f` fails if the target branch is currently checked out (in the main worktree or any worktree). Use `git merge --ff-only` instead when the branch is checked out. Check with `git branch --show-current` or `git worktree list`.
- **Existing split branches:** Always check for existing split branches (`git branch --list '*split*'`) before running a new `git subtree split`. Ask the user whether to reuse an existing split or create a fresh one.
- **Unrelated histories:** If the monorepo's content was imported (not via `git subtree add` from the standalone repo), the split branch will have no common ancestor with the submodule's `origin` history. In this case, **create the local branch directly from the split remote branch** (`git checkout -b <name> <remote>/<split-branch>`), not from the submodule's `origin` HEAD. Rebase will work correctly once the branch is based on the split history.
- **Already-applied commits:** `export` uses subtree merge which handles already-applied changes automatically. `sync` uses rebase which naturally skips commits already in the upstream.
- **Missing split branch:** `sync` handles this automatically by re-splitting before fetching.
- **Empty commits:** Export via fetch + subtree merge handles empty commits naturally.
- **Export uses fetch + subtree merge:** Export fetches exact commit objects from the submodule (`git fetch <path> <branch>`, no remote added), updates the split branch (`git branch -f`), then subtree-merges into the monorepo branch (`git merge -s subtree --allow-unrelated-histories`). This preserves identical commit hashes between split and submodule, and auto-remaps paths under the prefix. Do NOT use `git am` or cherry-pick for export.
- **Reset direction:** Reset follows the same direction as export (submodule → split → monorepo). The user picks the new HEAD on the submodule branch; the split branch uses the same SHA (shared history); the monorepo branch is found by matching the subtree tree object.
- **Sync uses rebase, not cherry-pick:** `sync` rebases local work onto the split branch tip. The split branch (from `subtree split`) already contains the correct tree including merge results. Rebasing preserves local commits on top. If the user has local merge commits, use `git rebase --rebase-merges` to preserve them.
- **Do not add remotes in monorepo:** When exporting, do NOT add the submodule as a persistent remote in the monorepo. Use `git fetch <submodule-path> <branch>` to transfer commit objects — this is a one-time fetch by path that does not create a remote.

## Configuration

Bridge config is stored in the repo's local git config under `[bridge]`:

| Key | Description | Default |
|---|---|---|
| `bridge.prefix` | Subdirectory path in monorepo | (auto-detected) |
| `bridge.remote` | Remote name | `bridge-upstream` |
| `bridge.monorepo-path` | Path to monorepo | (from setup) |
| `bridge.split-prefix` | Branch prefix for splits | `bridge-split` |
| `branch.<name>.bridge-tracks` | Monorepo branch tracked by submodule branch | (auto-detected by sync) |

Check current config: `git config --local --get-regexp '^bridge\.'`
