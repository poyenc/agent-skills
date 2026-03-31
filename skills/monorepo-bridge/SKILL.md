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

All operations use the `monorepo-bridge` CLI tool bundled at `bin/monorepo-bridge` relative to this skill file.

```bash
BRIDGE="/home/poyechen/.claude/skills/monorepo-bridge/bin/monorepo-bridge"
```

Run `monorepo-bridge --help` or `monorepo-bridge <command> --help` for usage details.

## Behavior Modes

### Mode A: Explain the Workflow

When the user asks how the workflow works, explain:

1. **The setup**: A monorepo has a subdirectory (e.g., `projects/mylib/`) that is also used as a standalone submodule in other repos.

2. **The bridge mechanism**: `git subtree split` extracts the subdirectory into a standalone branch where files are at the root (not nested under the prefix). This branch is compatible with the submodule's git history.

3. **The six operations:**

   | Operation | Runs from | CLI command | Purpose |
   |-----------|-----------|-------------|---------|
   | `setup` | submodule | `monorepo-bridge setup [--prefix=<path>] <monorepo-path>` | Add monorepo as remote, configure fetch, auto-detect prefix |
   | `split` | monorepo | `monorepo-bridge split [source-branch]` | Extract prefix into standalone branch |
   | `export` | submodule | `monorepo-bridge export [target-branch]` | Send submodule commits back to monorepo (fetch + subtree merge) |
   | `sync` | submodule | `monorepo-bridge sync [monorepo-branch]` | Pull all new monorepo changes into submodule (split + rebase) |
   | `reset` | submodule | `monorepo-bridge reset --target=<sha> [monorepo-branch]` | Reset all three branches to undo an export |
   | `verify` | submodule | `monorepo-bridge verify [monorepo-branch]` | Verify all three branches are in sync |

4. **Typical sequences:**
   - **First-time setup:** `split` (monorepo) -> `setup` (submodule)
   - **Pulling all changes downstream:** `sync` (re-splits, fetches, rebases local work onto updated split tip)
   - **Pushing changes upstream:** `export` (fetch + update split + subtree merge into monorepo)
   - **Undoing an export:** `reset --target=<sha>` (same direction as export: submodule -> split branch -> monorepo branch)

Use concrete examples from the user's repo when possible (actual branch names, paths, commits).

### Mode B: Execute an Operation

**CRITICAL RULE: Never assume — always ask the user.** Do not guess monorepo paths, branch names, or target branches. If information is missing, ask. Do not infer values from a parent repo's config — only read config from the current submodule.

**Phase 0: Verify Working Directory**

Run the pre-flight check (see Scope section). If you are not inside a real submodule, STOP and ask the user which directory to use.

**Phase 1: Gather Required Information**

Ask the user for any information you don't already have. Do NOT proceed without it.

1. **Monorepo branch**: Ask which monorepo branch to sync from / export to. This is the FIRST question.
2. **Monorepo path**: If not configured (`git config --local --get bridge.monorepo-path`), ask the user.
3. **Local target branch**: Ask which local submodule branch to sync into — create from the split remote branch, or use an existing one. Ask the user for the name.
4. **Remote name**: The CLI defaults to `bridge-upstream`. Only ask if the user wants a different name or if existing remotes suggest a better match.

**Phase 2: Context Detection**

1. Check if bridge is configured: `git config --local --get bridge.prefix`
2. Determine if you're in the monorepo or submodule:
   - Monorepo: has the prefix subdirectory, not a submodule itself
   - Submodule: has `bridge.remote` configured, or `.git` is a file (not directory)
3. If not configured, the CLI auto-detects config from existing remotes that have split-branch refspecs. If that also fails, guide through `monorepo-bridge setup`.

**Phase 3: Intent Mapping**

| User wants to... | CLI command | Direction |
|---|---|---|
| Update/sync from monorepo | `monorepo-bridge sync [monorepo-branch]` | mono -> sub |
| Push submodule changes to monorepo | `monorepo-bridge export [target-branch]` | sub -> mono |
| Undo export / reset all branches | `monorepo-bridge reset --target=<sha> [monorepo-branch]` | sub -> split -> mono |
| Verify branches are in sync | `monorepo-bridge verify [monorepo-branch]` | check all three |
| Prepare monorepo for consumption | `monorepo-bridge split [source-branch]` | mono side |
| Set up the bridge | `monorepo-bridge setup [--prefix=<path>] <monorepo-path>` | sub side |

**Phase 4: Execution**

Run the appropriate CLI command. The CLI handles:
- Partial/blobless clone detection (uses `file://` URL automatically)
- Branch checkout conflicts (`branch -f` vs `merge --ff-only`)
- Post-export split branch ancestry issues (splits without `--branch`, then force-updates)
- Auto-detection of prefix, remote, and split-prefix from existing config or remotes
- Post-export verification and optional push

## User Checkpoints

These are mandatory confirmation points — always ask, never skip.

### Before reset: ask for new HEAD

The reset operation uses `git reset --hard`, which is destructive. **Always ask the user** which commit should be the new HEAD on the **submodule branch** (since that's where development happens). Show the recent commit log (`git log --oneline -10`) and wait for the user's choice before proceeding. Then pass it via `--target=<sha>`.

### After export: offer to push

The CLI automatically offers to push after export. If running non-interactively, ask the user separately whether to push.

### After reset: verify sync

The CLI automatically runs verify after reset. Check the output for PASS/FAIL.

## Auto-Detection

The CLI tool can auto-detect bridge configuration without running `setup` if:
- An existing remote has a refspec that maps split branches (e.g., `+refs/heads/ck-split/*:refs/remotes/rocm-ck/*`)
- The remote URL points to a local monorepo path
- The prefix can be inferred by matching the submodule's origin URL against the monorepo structure (with fuzzy name matching, e.g., `composable_kernel` matches `composablekernel`)

This means `export` and `sync` work immediately if there's already a suitable remote — no explicit `setup` needed.

## Branch Tracking

`sync` saves the mapping between submodule branch and monorepo branch in git config:

```
branch.<sub-branch>.bridge-tracks = <mono-branch>
```

On first run, `sync` auto-detects the closest matching monorepo branch by commit distance and saves the mapping. Subsequent runs reuse the saved mapping. Override with `sync <monorepo-branch>`.

## Edge Cases

- **Blobless/partial clones:** The CLI auto-detects partial clones and uses `file://` URL with `--filter=blob:none`. No manual handling needed.
- **Branch checked out in monorepo:** The CLI handles this — uses `merge --ff-only` when the target branch is checked out, `branch -f` otherwise.
- **Unrelated histories:** If the monorepo's content was imported (not via `git subtree add` from the standalone repo), the split branch will have no common ancestor with the submodule's `origin` history. In this case, **create the local branch directly from the split remote branch** (`git checkout -b <name> <remote>/<split-branch>`), not from the submodule's `origin` HEAD. Rebase will work correctly once the branch is based on the split history.
- **Already-applied commits:** `export` uses subtree merge which handles already-applied changes automatically. `sync` uses rebase which naturally skips commits already in the upstream.
- **Post-export sync:** After an export, `subtree split --branch=<name>` would fail due to ancestry mismatch. The CLI works around this by splitting without `--branch` and then force-updating the branch.
- **Export mechanics:** Export fetches exact commit objects from the submodule (`git fetch <path> <branch>`, no remote added), updates the split branch (`git branch -f`), then subtree-merges into the monorepo branch. This preserves identical commit hashes. Do NOT use `git am` or cherry-pick for export.
- **Reset direction:** Reset follows the same direction as export (submodule -> split -> monorepo). The user picks the new HEAD via `--target`; the split branch uses the same SHA (shared history); the monorepo branch is found by matching the subtree tree object.
- **Sync uses rebase, not cherry-pick:** `sync` rebases local work onto the split branch tip. If the user has local merge commits, use `git rebase --rebase-merges` to preserve them.
- **Recreated monorepo / reconfiguring the bridge:** If the monorepo was recreated (re-cloned, rebased, or restructured), do NOT manually patch the existing remote config in the submodule. The old remote accumulates git state (partial clone filters, promisor pack references) that becomes stale and causes fetch failures like `could not fetch <sha> from promisor remote` or `lazy fetching disabled`. Instead, run the following **inside the submodule directory**: (1) `git remote remove <name>` to remove the old bridge remote, (2) `git config --local --remove-section bridge` to clear stale bridge config, (3) `git config --local --unset branch.<name>.bridge-tracks` for each tracked branch, (4) `monorepo-bridge setup` to create a fresh remote. Then re-add branch tracking and run `sync` for each branch.

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
