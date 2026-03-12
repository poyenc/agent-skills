---
name: gpu-usage
description: >
  Report GPU usage on shared servers — shows which processes occupy each GPU,
  VRAM percentage, GPU utilization, process owner, elapsed time, and Docker
  container name. Use this skill when the user asks: "who's using the GPU",
  "check GPU usage", "is the GPU free", "can I profile", "GPU contention",
  "VRAM usage", "show GPU processes", "gpu-usage", or any question about
  GPU availability before profiling.
allowed-tools: >
  Bash(rocm-smi --show*),
  Bash(ps *),
  Bash(pgrep *),
  Bash(docker ps *)
---

# GPU Usage Report

Check GPU contention on shared servers. Runs `rocm-smi` and system commands,
then presents a concise table so you can decide whether to proceed with
profiling or contact the process owner.

## Output Table

| GPU | VRAM% | GPU Util% | PID | User | Elapsed | Command | Container |
|-----|-------|-----------|-----|------|---------|---------|-----------|
| 0   | 65%   | 95%       | 12345 | alice | 2d3h | python3 train_llama.py --model-size 70b --data /mnt/d... | train-llm |
| 3   | 8%    | 0%        | 54321 | carol | 5h12m | python3 eval.py --checkpoint /data/ckpt/epoch42 | - |

- GPUs with 0% utilization AND 0% VRAM are **omitted** (idle GPUs not shown)
- Container column shows Docker container name, or `-` if running on host
- VRAM shown as percentage of total
- Command shows full command line args, **truncated to 60 chars**
- **User column shows the host user**, not the in-container user. For
  containerized processes, the host user is resolved via `pgrep` searching
  for `docker exec`/`docker run` commands targeting the container (see
  Step 2b).

## Workflow

**Minimize tool calls.** Batch all per-PID and per-container operations into
single Bash calls using comma-separated args or shell loops. Never issue
separate tool calls for each PID or container — that triggers repeated
permission prompts. Aim for **at most 5-6 total Bash calls** for the entire
workflow.

### Step 1: Gather GPU state

Run these three commands **in parallel** (use parallel Bash tool calls):

**1a. VRAM per GPU:**
```bash
rocm-smi --showmeminfo vram
```
Parse output lines like:
```
GPU[N] : VRAM Total Memory (B): <total>
GPU[N] : VRAM Total Used Memory (B): <used>
```
Compute `VRAM% = round(used / total * 100)` for each GPU N.

**1b. GPU utilization:**
```bash
rocm-smi --showuse
```
Parse output lines like:
```
GPU[N] : GPU use (%): <util>
```

**1c. Process list with GPU assignment:**
```bash
rocm-smi --showpidgpus
```
This lists PIDs and which GPU(s) they use. **Filter out PIDs with
`0 DRM device(s)`** — these are background agents (e.g. `gpuagent`) that
hold no GPU compute resources and should not appear in the table.

If `--showpidgpus` fails (may require root), fall back to:
```bash
rocm-smi --showpids
```

### Step 2: Gather process and container details

For each PID from Step 1c:

**2a. Get process details:**
```bash
ps -o pid,user,etimes,args -p <pid1>,<pid2>,... --no-headers
```
This gives owner, elapsed time **in seconds** (`etimes`, not `etime`), and
full command line for all PIDs in one call.

Convert the elapsed seconds to human-readable `XdYhZm` format:
- `>= 86400`: show days+hours, e.g. `2d3h`
- `>= 3600`: show hours+minutes, e.g. `5h12m`
- `>= 60`: show minutes+seconds, e.g. `3m45s`
- `< 60`: show seconds, e.g. `42s`
- Omit zero components (e.g. `2d` not `2d0h`, `5h` not `5h0m`).

Truncate the `args` column to 60 characters in the final table.

**2b. Detect containers and resolve host users:**

**Skip entirely if no GPU process has user `root`.** Non-root users are host
users — no container detection needed. Set Container to `-` and proceed to
Step 3.

**Session cache:** If a container name and host user were already resolved
for the same GPU command pattern earlier in this session, reuse that mapping
without re-running docker/pgrep calls.

If any GPU process shows user `root`, it is likely containerized. Resolve
the container name and host user:

**Call 1 — identify which container owns the GPU process:**
Use `pgrep` to search for `docker exec` or `docker run` commands whose
arguments contain the GPU process's command name (e.g. `bench_fmha`,
`python train`, `vllm`). This narrows the search without needing to check
all 14+ containers:
```bash
pgrep -a -f 'docker.*(exec|run).*<keyword_from_gpu_command>'
```
The output shows host PIDs + full command lines, which include the container
name or ID. Extract the container name from the matched `docker exec/run`
command arguments.

If no match by command keyword, broaden the search — list containers first:
```bash
docker ps --no-trunc --format '{{.ID}} {{.Names}}'
```
Then try `pgrep` for each likely container name (pick containers whose names
suggest GPU workloads, not infra like `node-exporter`).

**Note:** `pgrep` returns **exit code 1** when no processes match. This is
normal (not an error) — it means no docker commands were found for that
pattern. Handle silently.

**Call 2 — resolve the host user from matched PIDs:**
```bash
ps -o user --no-headers -p <pgrep_pid1>,<pgrep_pid2>,...
```
Do NOT chain with `;` — that breaks `allowed-tools` pattern matching. Use a
**separate** Bash tool call.

From the results, determine the host user:
1. If a `docker run` command is found, its user is the **container owner**.
2. If `docker exec` commands are found, their users are **active users** of
   the container.
3. If both exist and differ, prefer the `docker exec` user actively running
   workloads (not IDE/tail/sh processes).
4. If only one distinct user appears, use that user.

Use the resolved host user in the **User** column for the in-container GPU
process row.

If no docker commands are found on the host (e.g., the launching shell has
exited and no active sessions remain), show `(container)` as user fallback.

### Step 3: Format and display

1. **Compute VRAM%** for each GPU: `round(used / total * 100)`
2. **Filter idle GPUs:** Skip GPUs where VRAM% rounds to 0% AND GPU util
   is 0% AND no PIDs are assigned to that GPU
3. **Build the markdown table** sorted by GPU ID (ascending), then PID
4. **Render the table** with the columns:
   `| GPU | VRAM% | GPU Util% | PID | User | Elapsed | Command | Container |`
5. If **no GPUs are occupied** (all filtered out), display:
   `All GPUs are idle.`

## Edge Cases

- `rocm-smi --showpidgpus` may require root — fall back to `--showpids`
- Docker daemon may not be running — skip container detection if `docker`
  command fails
- **Process exited between rocm-smi and ps:** If `ps` returns no data for a
  PID that rocm-smi reported, still show the row using data from rocm-smi
  (GPU, VRAM%, GPU Util%) with `(exited)` for Command, `-` for User and
  Elapsed. Do NOT silently omit — the GPU may still show utilization.
- Container user tracing may fail — show `(container)` as user fallback
- If `rocm-smi` is not installed, stop and tell the user
