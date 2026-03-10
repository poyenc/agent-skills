---
name: ck-kernel-resource-usage
description: >
  Analyze GPU kernel resource usage — VGPRs, AGPRs, SGPRs, occupancy, scratch
  memory, LDS, and register spills — by building a CK target with
  -Rpass-analysis=kernel-resource-usage and parsing the build log.
  Use this skill whenever the user wants to: check kernel register allocation,
  find scratch memory or spill usage, analyze VGPR/SGPR/AGPR counts, identify
  occupancy issues in a CK build target, or run a "resource usage analysis" /
  "kernel resource report" on a composable kernel target. Also trigger when the
  user says things like "check register pressure for <target>", "which kernels
  have spills", "build with resource usage remarks", "kernel resource report",
  "check occupancy", "how many VGPRs does <target> use", or "ck resource usage".
---

# Kernel Resource Analysis

Build a CK (Composable Kernel) target with LLVM's `-Rpass-analysis=kernel-resource-usage`
flag, parse the build log, and report kernels with register spills or non-zero scratch size.

## Required inputs

| Input | Description | Example |
|-------|-------------|---------|
| **container** | Docker container name | `spill_check_poyechen` |
| **target** | CMake build target name | `tile_example_fmha_fwd` |

If the user doesn't provide a container name, default to
`spill_check_<username>` (e.g., `spill_check_poyechen`), where `<username>`
comes from `$USER`. This avoids collision on shared machines and clearly
identifies the container's purpose.

The CK workspace path inside the container is auto-resolved from volume mounts
(see Step 1). Do **not** ask the user for it.

## Where work happens

- **Host (Claude's tools):** All file reading, editing, searching.
  Use Grep/Glob/Read/Edit tools directly on the host filesystem.
- **Container (docker exec):** GPU arch detection, cmake configure, cmake
  build, and log parsing (the parser needs `c++filt` for demangling).

The container sees host files through its volume mount, so edits on the host
are immediately visible inside the container.

## Workflow

### Step 0: Verify CK repository

Before anything else, confirm the current working directory is a CK repo.
Check for the `.ck-project-root` marker file at pwd or any parent:

```
Glob for '.ck-project-root' in pwd
```

If not found, also check `script/cmake-ck-dev.sh` exists. If neither is
present, **stop and tell the user** that pwd does not appear to be a CK
repository. Ask them to `cd` to the correct directory and retry.

Save the directory containing `.ck-project-root` as `$HOST_CK_ROOT`.

### Step 1: Resolve the container and workspace

The goal: (a) a running container with GPU access, and (b) the path inside
that container that corresponds to the CK source tree on the host.

**Host CK root** = `$HOST_CK_ROOT` from Step 0.

#### 1a. Check if the container exists and is running

```bash
# Check existence and state in one command
docker ps -a --filter "name=^<container>$" --format '{{.Names}} {{.State}}'
```

| State | Action |
|-------|--------|
| Running | Proceed to 1b |
| Exists but stopped | `docker start <container>`, then proceed to 1b |
| Does not exist | Go to 1c |

#### 1b. Resolve CK directory from volume mounts

Inspect the container's bind mounts:

```bash
docker inspect <container> --format '{{json .Mounts}}'
```

Returns JSON like:
```json
[{"Type":"bind","Source":"/home/user/workspace","Destination":"/workspace",...}]
```

Find the mount whose `Source` is a prefix of the host CK root (pwd).
The container-side path is:
```
<Destination> + <suffix of pwd after Source>
```

Example: `Source=/home/user/workspace`, `Destination=/workspace`,
pwd=`/home/user/workspace/worktree/ck-develop`
=> container path = `/workspace/worktree/ck-develop`

If no mount matches, ask the user for the container-side path.

Save as `$CK_DIR`.

#### 1c. Container does not exist — create it

Ask the user for a Docker image (suggest default:
`rocm/composable_kernel:ck_ub24.04_rocm7.1.1_develop`).

Create the container mounting the host pwd:

```bash
docker run -d \
  --name <container> \
  --device=/dev/kfd --device=/dev/dri \
  --security-opt seccomp=unconfined \
  --group-add video \
  -v <host_pwd>:/workspace \
  -w /workspace \
  <docker_image> \
  tail -f /dev/null
```

Here `$CK_DIR=/workspace`.

### Step 2: Detect GPU architecture

**In container:**
```bash
docker exec <container> bash -c \
  "rocminfo 2>/dev/null | grep -oE 'gfx[0-9a-z]+' | head -1 || echo gfx942"
```

Save as `$GPU_ARCH`.

### Step 3: Add the resource-usage remark flag to the target

**On host** — use Grep to find and Read/Edit to modify.

Find the CMakeLists.txt that **defines** the target. Search for the defining
pattern, not just any mention:

```
Grep for 'add_executable\s*\(\s*<target>' or 'add_library\s*\(\s*<target>'
in CMakeLists.txt files under the host CK root
```

If no direct match, also try these CK-specific patterns (the project uses
wrapper functions):
- `add_example_executable(<target> ...)`
- `add_test_executable(<target> ...)`
- `add_gtest_executable(<target> ...)`
- `set(... <target>)` followed by `add_executable(${...} ...)`

**Important:** A target may appear in many CMakeLists.txt files (as a
dependency, in `add_dependencies()`, or `target_link_libraries()`). Only
modify the file that **creates** the target (the one with `add_executable`
or `add_library`).

Read the matching file and insert the flag near existing
`target_compile_options` calls for that target, or right after the target
creation if none exist:

```cmake
target_compile_options(<target> PRIVATE -Rpass-analysis=kernel-resource-usage)
```

If the flag is already present for this target, skip this step.

**Remember the exact line you added and the file path** — you will need to
revert this in Step 7.

**Note:** The `-Rpass-analysis` flag only applies to compilation units built
as part of this target. If the actual GPU device code is compiled in a
**library dependency** (e.g., a CK static library that the target links
against), those compilation units won't get the flag. In CK's architecture,
kernel template instantiations are typically compiled as part of the target
itself, so this usually works. If the report shows 0 kernels, check whether
the device code lives in a linked library instead.

### Step 4: Configure the project

**In container.** The build directory goes under `/tmp` to avoid polluting
the source tree. Include the GPU arch in the directory name so that
switching architectures doesn't reuse a stale configuration:

```
$BUILD_DIR = /tmp/build-<target>-$GPU_ARCH
```

Do **not** use `cmake-ck-dev.sh` — it uses `--preset dev` which hardcodes
`binaryDir` to `${sourceDir}/build` and cannot be overridden. Instead,
call `cmake` directly with the equivalent settings from the `dev` preset:

```bash
docker exec <container> bash -c \
  "cmake -S $CK_DIR -B /tmp/build-<target>-$GPU_ARCH -GNinja \
   -DCMAKE_PREFIX_PATH=/opt/rocm/ \
   -DCMAKE_CXX_COMPILER=/opt/rocm/llvm/bin/clang++ \
   -DCMAKE_HIP_COMPILER=/opt/rocm/llvm/bin/clang++ \
   '-DCMAKE_CXX_FLAGS=-ftemplate-backtrace-limit=0 -fPIE -Wno-gnu-line-marker -fbracket-depth=1024' \
   -DCMAKE_BUILD_TYPE=Release \
   -DBUILD_DEV=ON \
   -DGPU_TARGETS=$GPU_ARCH"
```

The configure step is fast (< 1 minute). Tell the user it's configuring.

If `/tmp/build-<target>-$GPU_ARCH` already exists from a previous run,
reconfiguration can be skipped unless the CMakeLists.txt was modified in
Step 3.

### Step 5: Build the target and capture the log

**In container.** Resource-usage remarks go to stderr. Capture both streams
into a log file inside the container.

This is the slow step — CK builds with many template instantiations can
take 10-60 minutes. Use `run_in_background: true` on the Bash tool so
Claude doesn't block, and tell the user the build is running.

**Important:** CK template-heavy builds use significant memory per
compilation unit. Using all cores can cause OOM kills. Use half the
available cores as a safe default:

```bash
docker exec <container> bash -c \
  "cmake --build /tmp/build-<target>-\$GPU_ARCH --target <target> \
   -j\$(( \$(nproc) / 2 )) \
   > /tmp/ck_build_<target>_\$GPU_ARCH.log 2>&1"
```

When the build finishes (or fails), proceed to Step 6. Partial logs still
contain resource data for files that compiled successfully.

### Step 6: Parse the build log for resource usage

**In container** — pipe the parser script from the host into the container
via stdin. This avoids needing the skill directory to be inside a mounted
volume. The container has `c++filt` for demangling kernel names.

`<skill-dir>` = the host path to this skill's directory (the directory
containing this SKILL.md).

```bash
cat <skill-dir>/scripts/parse_resource_usage.py | \
  docker exec -i <container> \
  python3 - /tmp/ck_build_<target>_$GPU_ARCH.log --target <target> --arch $GPU_ARCH
```

The parser prints a summary to stdout (kernel count, spill count, dynamic
stack count) and saves detailed reports inside the container:
- `/tmp/ck_build_<target>_$GPU_ARCH_report.md` — human-readable markdown
- `/tmp/ck_build_<target>_$GPU_ARCH_report.csv` — machine-readable CSV

Do **not** copy reports to the host. Use the stdout summary in Step 8 and
tell the user where the files are saved (inside the container) for manual
inspection if needed.

### Step 7: Clean up the CMakeLists.txt change

**On host** — use the Edit tool to remove the `target_compile_options` line
added in Step 3 **before** presenting the report. This keeps the source
tree clean. Remove only the line that was added.

### Step 8: Present the report

Read the CSV from inside the container and use it to build the report.
The CSV columns are: `source,kernel,vgprs,agprs,effective_vgprs,
total_sgprs,scratch_size,occupancy,sgpr_spill,vgpr_spill,lds_size,
dynamic_stack`.

#### Determine report scope: full vs. focused

Check the user's original request for keywords that signal interest in a
**specific aspect** of resource usage. If a keyword matches, produce a
**focused report** for that aspect. Otherwise, produce the **full report**.

| User says (examples) | Focus area | Key CSV columns |
|-----------------------|------------|-----------------|
| "vgpr spill", "register spill" | VGPR spills | vgpr_spill, scratch_size |
| "sgpr spill" | SGPR spills | sgpr_spill |
| "scratch", "scratch memory" | Scratch usage | scratch_size, vgpr_spill, sgpr_spill |
| "occupancy", "waves" | Occupancy | occupancy, effective_vgprs |
| "lds", "shared memory" | LDS usage | lds_size |
| "register pressure", "vgpr count" | Register allocation | vgprs, agprs, effective_vgprs |
| "dynamic stack", "alloca" | Dynamic stack | dynamic_stack |
| "spill check", "resource usage", "kernel report", (no specific keyword) | **Full report** | all columns |

#### Full report (default)

Present a comprehensive summary covering **all** resource dimensions.
Use the CSV to compute aggregate statistics with `awk` or similar, then
present:

1. **Overview table** — total kernels, how many have issues in each
   category:

   | Metric | Count |
   |--------|-------|
   | Total kernels | N |
   | VGPR spills (vgpr_spill > 0) | N |
   | SGPR spills (sgpr_spill > 0) | N |
   | Scratch memory (scratch_size > 0) | N |
   | Dynamic stack | N |

2. **Occupancy distribution** — how many kernels at each wave count
   (group into 1, 2, 3, 4+ waves/SIMD)

3. **Effective VGPR distribution** — bucket by occupancy cliff boundaries.
   The report includes `effective_vgprs` that accounts for AGPRs per arch:
   - CDNA3 (gfx94x): `EffVGPRs = max(VGPRs, AGPRs)` — separate files
   - CDNA4 (gfx95x): `EffVGPRs = VGPRs + AGPRs` — unified file
   The critical cliff is at **129 effective VGPRs** (128 → 4 waves, 129 →
   3 waves — one extra register costs 25% of wave slots).

4. **Worst offenders** — top 10-15 kernels sorted by scratch_size
   descending, showing all columns

5. **Highlights** — call out any of these that apply:
   - Dynamic Stack kernels (always serious)
   - Non-zero ScratchSize (global memory round-trips)
   - High effective VGPR count crossing occupancy cliffs
   - Low occupancy (<3 waves) — though for MFMA-heavy kernels, 1-2 may
     be acceptable

#### Focused report

When the user asks about a specific aspect, produce a **targeted report**
that filters and sorts by the relevant metric:

- **Show only affected kernels** — e.g., for "vgpr spill", only show
  kernels where `vgpr_spill > 0`
- **Sort by the relevant metric** — e.g., by `vgpr_spill` descending
- **Include context columns** — always include VGPRs, AGPRs, EffVGPRs,
  and Occupancy alongside the focused metric so the user can correlate
- **Provide a count summary** — e.g., "97 of 258 kernels have VGPR
  spills"
- **Skip unrelated sections** — don't show LDS distribution when the
  user asked about spills

#### Common to both report types

If no kernels have issues in the reported area, say so explicitly.

Tell the user the full report and CSV are saved inside the container at
`/tmp/ck_build_<target>_$GPU_ARCH_report.md` and `.csv`. They can inspect
them with `docker exec <container> cat /tmp/...` or copy them out manually.

## Raw remark format reference

The compiler emits a block of remarks per kernel function. **Each field is
on its own line**, each ending with `[-Rpass-analysis=kernel-resource-usage]`.
Lines contain ANSI color codes that must be stripped before parsing.

```
<file>:<line>:<col>: remark: Function Name: <mangled_name> [-Rpass-analysis=...]
<file>:<line>:<col>: remark:     TotalSGPRs: 58 [-Rpass-analysis=...]
<file>:<line>:<col>: remark:     VGPRs: 256 [-Rpass-analysis=...]
<file>:<line>:<col>: remark:     AGPRs: 143 [-Rpass-analysis=...]
<file>:<line>:<col>: remark:     ScratchSize [bytes/lane]: 0 [-Rpass-analysis=...]
<file>:<line>:<col>: remark:     Dynamic Stack: False [-Rpass-analysis=...]
<file>:<line>:<col>: remark:     Occupancy [waves/SIMD]: 1 [-Rpass-analysis=...]
<file>:<line>:<col>: remark:     SGPRs Spill: 0 [-Rpass-analysis=...]
<file>:<line>:<col>: remark:     VGPRs Spill: 0 [-Rpass-analysis=...]
<file>:<line>:<col>: remark:     LDS Size [bytes/block]: 17408 [-Rpass-analysis=...]
```

Key differences from what documentation might suggest:
- `TotalSGPRs` not `SGPRs`
- `LDS Size [bytes/block]` is an additional field
- `Dynamic Stack: True/False` is an additional field
- Each line has its own `[-Rpass-analysis=...]` tag (not one tag at the end)
- ANSI color codes wrap source locations and remark text

## Notes

- Build time is not significantly affected by `-Rpass-analysis` (it's a
  reporting flag, not an optimization change).
- CDNA3 (gfx942): occupancy determined by max(ArchVGPRs, AGPRs)
- CDNA4 (gfx950): occupancy determined by ArchVGPRs + AGPRs (additive)
