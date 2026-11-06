---
name: gpu-occupant-owner
description: >
  Name the PERSON (login username) who owns each process occupying or contending
  for a GPU on any shared AMD/ROCm GPU server, local or remote over SSH -- through
  containers (root inside someone's container maps to that container's user),
  cgroups and process ancestry, and, for a process that already exited, through
  the host's login journal. Prints one line per GPU: free, or user, container,
  PID, elapsed time and command. The answer is a username, never "unknown" or a
  bare PID/root. Use it whenever anyone asks or needs: "who is contending the
  GPU with us", "who is on my GPU", "who's using GPU N", "whose process is
  this", "who owns PID X", "find out who runs the GPU", "a foreign/unknown PID
  showed up on my GPU or in a run log", "someone's job disturbed my benchmark or
  trace", "is this GPU free", "check GPU usage on <host>", "can I profile now".
  Use it BEFORE reporting a foreign GPU process to the user, so the report names
  who it is.
allowed-tools: Bash(python3 * gpu_usage.py *)
---

# GPU occupant owner: who is on which GPU

Shared GPU servers run many users' containers plus root-owned automation, so a GPU process's
owner is often just `root`. This skill resolves every GPU process to the login account of the
person behind it, and shows which process it is.

## Prerequisites

- Python 3.8+ on the target host. Remote hosts need passwordless SSH (`ssh <host>` works);
  nothing is installed there, the collector is piped over stdin.
- AMD GPUs with the ROCm KFD driver (`/sys/class/kfd`). NVIDIA hosts are out of scope; hosts
  without KFD report "No GPUs found".
- `docker` and `sudo -n` improve attribution (container metadata, other users' `/proc` entries,
  the login journal); without them the script still runs and says what it could not read.

## Who occupies which GPU (default output)

```
python3 <skill-dir>/scripts/gpu_usage.py --host <host>          # repeat --host, or omit for the local host
<host>
  GPU 0 (gpu_id 56179): free
  GPU 1 (gpu_id 9367): alice [container alice-dev, pid 4105420, 30s] ./bench -n 100
  GPU 2 (gpu_id 45514): bob (ours) [pid 2210, 812s] python3 train.py
```

- GPU numbers are the host's KFD topology order (the order `amd-smi list` uses), read on every run.
- `--ours <container name or pid regex>` (repeatable) tags our own processes `(ours)`.
- Answer the user from these lines: GPU, user, process.

Other outputs: `--format markdown` (per-GPU utilization, VRAM, foreign duty cycle over the sample
burst, verdict with the owner's evidence and options), `--format json` (raw per-PID evidence).
`--history <file>` accumulates first/last-seen per host, GPU and owner across repeated runs.
`--samples N --interval S` set the sampling burst (default 5 x 1 s); `--deadline S` the per-host
SSH deadline (default 30 s).

## How the owner is resolved

A PID occupies only the GPUs named by its live KFD queue `gpuid`; exposed/open GPUs do not count, and
unreadable queues are never reported free: the PID is listed on every GPU, tagged "KFD queues not
readable", with its owner.

On the host itself, every candidate is checked against the host's login accounts, strongest evidence first:

- **Process in a container:** the `loginuid` of the GPU process (the kernel audit uid set at login, also
  inside containers, so a root process maps to the person), then the `loginuid` of the container's init
  process, then the user of a live `docker exec/run` into it, then an `owner`/`user` container label.
  Only without any of these, the hints: the owner of a `/home` bind mount, a `/home/<user>` path,
  `USER`/`LOGNAME`/`HOME` in the container env, a container-name token, then the one user who logged
  in within 60 s of the container's creation and still has a session (journal, `who`).
- **Host process:** the `loginuid`, then the first non-root user among the process and its ancestors,
  then the journal's `_AUDIT_LOGINUID` for the pid, then the one login near its start that still has a session.

If no evidence names exactly one login account, the line says "could not determine the owner" with the
reason; it never lists candidate names, a bare PID, `root` or a name guessed from a container name.
The markdown verdict prints the evidence used.

## A PID that already exited

A PID from a run log or an earlier check is no longer in `/proc`. The collector already tries the journal's
`_AUDIT_LOGINUID` for that pid; if it has none, resolve it by hand from the journal:

1. Find its spawn time from neighbouring live PIDs
   (`ps -eo pid=,lstart= | awk '$1>=<pid-500> && $1<=<pid+500>'`) or `sudo -n journalctl _PID=<pid>`.
2. List the logins at that time:
   `sudo -n journalctl --since '<t-5s>' --until '<t+5s>' -o short-iso | grep -E 'session opened|New session'`.
3. Read each candidate session's lifetime: `sudo -n journalctl | grep -E 'session-<N>.scope|Session <N>'`;
   the "Consumed ... CPU time over ... wall clock" line gives its span.
4. The owner is the user whose session (or `user-<uid>.slice`) stayed alive, with CPU time, across
   the whole window in which the PID held the GPU. Sessions that close within a second are polling,
   not the holder.

Example: PID 76113 held a GPU during a run at 05:07:39. Neighbouring PIDs put its spawn at 05:05:25.
At that second user A opened session 48205 and user B opened several sessions that closed within 1 s.
Session 48205 logged out at 05:05:40 but its processes ran until 05:08:43 with 3 min 18 s of CPU,
covering the run. Owner: user A.

## Rules

- **Read-only.** The skill only inspects `/proc`, `/sys`, `docker ps/inspect`, `journalctl` and
  `who`; it never signals or kills a process. Freeing a GPU is a separate action that needs the
  user's explicit direction.
- **No `rocm-smi`/`amd-smi` unless asked** (`--rocm-smi`), in local and remote runs alike: on some
  hosts these tools have wedged or stalled the node. Runs read KFD and sysfs files only; utilization and VRAM come from
  `/sys/class/drm/card*/device` when present.
- **One shot per invocation**, no daemon; repeat it yourself if `--history` should accumulate.
- **Per-host deadline**, never a shell `timeout` around `ssh`: each host gets
  `ssh -o ConnectTimeout=8 -o BatchMode=yes` plus a subprocess deadline, hosts run concurrently,
  and an unreachable or hung host is reported, not retried.
