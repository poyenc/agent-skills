---
name: monorepo-bridge
description: Bidirectional commit transfer between monorepos and standalone submodule repos. Use when the user wants to cherry-pick, export, split, sync, or update commits between a monorepo and a submodule, or when they ask how the monorepo/submodule workflow works. Also trigger on mentions of "monorepo bridge", "subtree bridge", "subtree split", "update the monorepo branch", "sync from monorepo", "pull monorepo changes", porting commits between mono and sub repos, or setting up a bridge.
---

# Monorepo Bridge

Help users move commits bidirectionally between a monorepo (a repo containing multiple projects in subdirectories) and standalone submodule repos that mirror one of those subdirectories.

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

3. **The five operations:**

   | Operation | Runs from | Purpose |
   |-----------|-----------|---------|
   | `setup` | submodule | Add monorepo as remote, configure fetch |
   | `split` | monorepo | Extract prefix into standalone branch |
   | `pick` | submodule | Cherry-pick a monorepo commit (translated) |
   | `export` | submodule | Send submodule commits back to monorepo |
   | `sync` | submodule | Pull all new monorepo changes into submodule |

4. **Typical sequences:**
   - **First-time setup:** `split` (monorepo) -> `setup` (submodule)
   - **Pulling all changes downstream:** `sync` (fetches monorepo remote, re-splits, cherry-picks new commits)
   - **Pulling a specific commit:** `pick <commit>`
   - **Pushing changes upstream:** `export <base-ref>`

Use concrete examples from the user's repo when possible (actual branch names, paths, commits).

### Mode B: Execute an Operation

**Phase 1: Context Detection**

1. Check if the CLI tool is available (see CLI Tool section above).
2. Check if bridge is configured: `git config --local --get bridge.prefix`
3. Determine if you're in the monorepo or submodule:
   - Monorepo: has the prefix subdirectory, not a submodule itself
   - Submodule: has `bridge.remote` configured, or `.git` is a file (not directory)
4. If not configured, the CLI auto-detects config from existing remotes that have split-branch refspecs. If that also fails, guide through `monorepo-bridge setup`.

**Phase 2: Intent Mapping**

| User wants to... | Command | Direction |
|---|---|---|
| Update/sync from monorepo | `sync [monorepo-branch]` | mono -> sub |
| Pull a specific monorepo commit | `pick <sha>` | mono -> sub |
| Push submodule changes to monorepo | `export <base-ref>` | sub -> mono |
| Prepare monorepo for consumption | `split` | mono side |
| Set up the bridge | `setup <path>` | sub side |

**Phase 3: Execution**

Run the appropriate command. If the CLI tool is not available, use fallback commands:

**setup fallback:**
```bash
git remote add bridge-upstream /path/to/monorepo
git config "remote.bridge-upstream.fetch" "+refs/heads/bridge-split/*:refs/remotes/bridge-upstream/*"
git fetch bridge-upstream
git config --local bridge.prefix "<prefix>"
git config --local bridge.remote "bridge-upstream"
git config --local bridge.monorepo-path "/path/to/monorepo"
git config --local bridge.split-prefix "bridge-split"
```

**split fallback:**
```bash
git subtree split --prefix=<prefix> --branch=bridge-split/<branch> <branch>
```

**pick fallback:**
```bash
# 1. Find the split commit by subject match
SUBJECT=$(git -C /path/to/monorepo log -1 --format="%s" <sha>)
SPLIT_SHA=$(git log bridge-upstream/<branch> --format="%H" --grep="${SUBJECT}" --fixed-strings -1)

# 2. Cherry-pick directly (works even with blobless remotes)
git cherry-pick "${SPLIT_SHA}"
```

**export fallback:**
```bash
# 1. Generate patches
git format-patch <base-ref>..HEAD -o /tmp/patches

# 2. Filter out already-applied patches
for patch in /tmp/patches/*.patch; do
    SUBJECT=$(sed -n 's/^Subject: \(\[PATCH[^]]*\] \)\{0,1\}//p' "${patch}" | head -1)
    if git -C /path/to/monorepo log --format="%s" --fixed-strings --grep="${SUBJECT}" -1 | grep -qF "${SUBJECT}"; then
        rm "${patch}"  # already applied
    fi
done

# 3. Apply remaining under prefix in monorepo
git -C /path/to/monorepo am --directory=<prefix> /tmp/patches/*.patch
```

**sync fallback:**
```bash
REMOTE="bridge-upstream"  # or whatever the bridge remote is named
MONO="/path/to/monorepo"
PREFIX="projects/mylib"
SPLIT_PREFIX="bridge-split"
MONO_BRANCH="users/dev/feature"  # the monorepo branch to sync from

# 1. Fetch monorepo branch from its remote
git -C "${MONO}" fetch origin "${MONO_BRANCH}"

# 2. Fast-forward monorepo's local branch
git -C "${MONO}" branch -f "${MONO_BRANCH}" "origin/${MONO_BRANCH}"

# 3. Re-split the updated branch
git -C "${MONO}" subtree split --prefix="${PREFIX}" \
    --branch="${SPLIT_PREFIX}/${MONO_BRANCH}" "${MONO_BRANCH}"

# 4. Fetch updated split into submodule
git fetch "${REMOTE}"

# 5. Cherry-pick new commits (--cherry-pick filters out already-applied)
SHAS=$(git log --format="%H" --no-merges --right-only --cherry-pick \
    "HEAD...${REMOTE}/${MONO_BRANCH}" | tac)
if [[ -n "${SHAS}" ]]; then
    git cherry-pick ${SHAS}
fi
```

## Auto-Detection

The CLI tool can auto-detect bridge configuration without running `setup` if:
- An existing remote has a refspec that maps split branches (e.g., `+refs/heads/ck-split/*:refs/remotes/rocm-ck/*`)
- The remote URL points to a local monorepo path
- The prefix can be inferred by matching the submodule's origin URL against the monorepo structure

This means `pick`, `export`, and `sync` work immediately if there's already a suitable remote — no explicit `setup` needed.

## Branch Tracking

`sync` saves the mapping between submodule branch and monorepo branch in git config:

```
branch.<sub-branch>.bridge-tracks = <mono-branch>
```

On first run, `sync` auto-detects the closest matching monorepo branch by commit distance and saves the mapping. Subsequent runs reuse the saved mapping. Override with `sync <monorepo-branch>`.

## Edge Cases

- **Blobless/partial clones:** If the monorepo is a partial clone, `setup` uses `file://` URL and `--filter=blob:none`. Cherry-pick generally works fine with blobless remotes (only tree objects needed for diff computation). `pick` falls back to `format-patch/am` only if cherry-pick fails.
- **Commits outside prefix:** `pick` warns and skips commits that don't touch files under the prefix.
- **Already-applied commits:** `export` detects already-applied commits by matching subject lines. `sync` uses `--cherry-pick` flag which filters by patch-id equivalence.
- **Missing split branch:** `pick` will fail if the monorepo branch hasn't been split yet. `sync` handles this automatically by re-splitting before fetching.

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
