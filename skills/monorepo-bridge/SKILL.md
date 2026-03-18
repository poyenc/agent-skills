---
name: monorepo-bridge
description: Bidirectional commit transfer between monorepos and standalone submodule repos. Use when the user wants to cherry-pick, export, split, or sync commits between a monorepo and a submodule, or when they ask how the monorepo/submodule workflow works. Also trigger on mentions of "monorepo bridge", "subtree bridge", "subtree split", porting commits between mono and sub repos, or setting up a bridge.
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

3. **The four operations:**

   | Operation | Runs from | Purpose |
   |-----------|-----------|---------|
   | `split` | monorepo | Extract prefix into standalone branch |
   | `setup` | submodule | Add monorepo as remote, configure fetch |
   | `pick` | submodule | Cherry-pick a monorepo commit (translated) |
   | `export` | submodule | Send submodule commits back to monorepo |

4. **Typical sequences:**
   - **First-time setup:** `split` (monorepo) -> `setup` (submodule)
   - **Pulling changes downstream:** `split` (update) -> `pick <commit>` or `git merge`
   - **Pushing changes upstream:** `export <base-ref>`

Use concrete examples from the user's repo when possible (actual branch names, paths, commits).

### Mode B: Execute an Operation

**Phase 1: Context Detection**

1. Check if the CLI tool is available (see CLI Tool section above).
2. Check if bridge is configured: `git config --local --get bridge.prefix`
3. Determine if you're in the monorepo or submodule:
   - Monorepo: has the prefix subdirectory, not a submodule itself
   - Submodule: has `bridge.remote` configured, or `.git` is a file (not directory)
4. If not configured, guide through `monorepo-bridge setup`.

**Phase 2: Intent Mapping**

| User wants to... | Command | Direction |
|---|---|---|
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

# 2a. Normal remote — cherry-pick directly
git cherry-pick "${SPLIT_SHA}"

# 2b. Blobless remote (file:// URL) — use format-patch/am instead
#     Generate patch in the monorepo where lazy blob fetch works:
git -C /path/to/monorepo format-patch -1 "${SPLIT_SHA}" --stdout | git am
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

## Edge Cases

- **Blobless/partial clones:** If the monorepo is a partial clone, `setup` uses `file://` URL and `--filter=blob:none`. `pick` uses `format-patch/am` instead of `cherry-pick` because blob objects aren't available locally.
- **Commits outside prefix:** `pick` warns and skips commits that don't touch files under the prefix.
- **Already-applied commits:** `export` detects already-applied commits by matching subject lines and skips them.
- **Missing split branch:** `pick` will fail if the monorepo branch hasn't been split yet. Guide the user to run `split` first.

## Configuration

Bridge config is stored in the repo's local git config under `[bridge]`:

| Key | Description | Default |
|---|---|---|
| `bridge.prefix` | Subdirectory path in monorepo | (auto-detected) |
| `bridge.remote` | Remote name | `bridge-upstream` |
| `bridge.monorepo-path` | Path to monorepo | (from setup) |
| `bridge.split-prefix` | Branch prefix for splits | `bridge-split` |

Check current config: `git config --local --get-regexp '^bridge\.'`
