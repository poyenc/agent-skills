#!/usr/bin/env python3
"""Self-contained, read-only GPU/process fact collector.

Runs IDENTICALLY on the local machine or piped over ``ssh host python3 -``
(no install, no files written on the remote). Takes a short burst of
samples and resolves every occupant PID's real identity (user, ancestry,
container, lock file), then prints ONE JSON blob to stdout, framed by
caller-supplied start/end markers so a login-banner or other stray output
around it can be stripped by the caller.

Default mode is KFD-only: per-GPU attribution and the duty cycle come
from /sys/class/kfd and /proc; rocm-smi/amd-smi are NEVER invoked unless
``--rocm-smi`` is passed. This is a deliberate default, not a fallback --
on some hosts rocm-smi/amd-smi invocations have been observed to wedge
the node (hung command, D-state children), so callers that don't need
live util/clock/power/temp should never pay that risk. When KFD-only,
those four fields come from plain sysfs reads under
``/sys/class/drm/card*/device`` (gpu_busy_percent, mem_info_vram_used,
hwmon temp/power) where available, else null ("n/a").

Read-only: never signals or modifies any process. Python 3.8+ stdlib only.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

HZ = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
CMD_TRUNCATE = 500
KFD_PROC = "/sys/class/kfd/kfd/proc"
UNSET_LOGINUID = 4294967295

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _run(cmd: List[str], timeout: float = 10.0) -> Tuple[str, int]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "", -1


# One wall-clock budget for ALL privileged (``sudo -n``) lookups in a collect():
# a sudo call occasionally takes 2-4 s (PAM/sssd latency, ~6% of calls observed on
# a heliosr node), and a burst of new foreign pids multiplied that past the
# caller's 30 s deadline. Once the budget is spent every further privileged call
# is skipped, so the GPU -> pid -> user attribution (KFD/sysfs, no sudo) is
# always reported; only the sudo-only enrichment (cwd, fds, environ, journal) is lost.
_SUDO_BUDGET_S = 8.0
_sudo_deadline: Optional[float] = None
_sudo_budget_spent = False


def _start_sudo_budget() -> None:
    global _sudo_deadline, _sudo_budget_spent
    _sudo_deadline = time.monotonic() + _SUDO_BUDGET_S
    _sudo_budget_spent = False


def _run_sudo(cmd: List[str], timeout: float = 10.0) -> Tuple[str, int]:
    """``_run`` for a ``sudo -n`` command, bounded by the per-collect budget."""
    global _sudo_budget_spent
    if _sudo_deadline is not None:
        remaining = _sudo_deadline - time.monotonic()
        if remaining <= 0:
            _sudo_budget_spent = True
            return "", -1
        timeout = min(timeout, remaining)
    return _run(cmd, timeout=timeout)


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "r") as f:
            return f.read()
    except (OSError, PermissionError):
        return None


def _read_privileged(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Read a /proc file, falling back to ``sudo -n cat`` on EACCES.

    Returns (content, error). error is None on success, else a short
    human-readable reason (never raises)."""
    try:
        with open(path, "r") as f:
            return f.read(), None
    except PermissionError:
        pass
    except OSError as exc:
        return None, str(exc)
    out, rc = _run_sudo(["sudo", "-n", "cat", path], timeout=5.0)
    if rc == 0:
        return out, None
    return None, "permission denied (sudo -n also failed or unavailable)"


def _readlink_privileged(path: str) -> Optional[str]:
    try:
        return os.readlink(path)
    except PermissionError:
        out, rc = _run_sudo(["sudo", "-n", "readlink", "-f", path], timeout=5.0)
        if rc == 0 and out.strip():
            return out.strip()
        return None
    except OSError:
        return None


def _listdir_privileged(path: str) -> Optional[List[str]]:
    """Entries of ``path``; None if it exists but can be read neither directly nor with ``sudo -n``."""
    try:
        return os.listdir(path)
    except PermissionError:
        # Not budgeted: this lists a pid's KFD queues, which is the GPU attribution itself.
        out, rc = _run(["sudo", "-n", "ls", "-A", path], timeout=5.0)
        if rc == 0:
            return [l for l in out.splitlines() if l]
        return None
    except OSError:
        return []


def _pid_file(pid: int, name: str, live: bool = False) -> Optional[str]:
    """/proc/<pid>/<name>; if permissions hide it (hidepid, another user's file) read it with ``sudo -n cat``.
    A pid that exited stays None: only a stat that is denied, an absent entry of a pid KFD still lists, or a
    caller that knows the pid is live (``live``: hidepid=2 shows live pids as absent) counts as live."""
    path = f"/proc/{pid}/{name}"
    raw = _read(path)
    if raw is not None:
        return raw
    try:
        os.stat(path)
        live = True  # present but unreadable
    except PermissionError:
        live = True
    except OSError:
        live = live or os.path.isdir(f"{KFD_PROC}/{pid}")
    if not live:
        return None
    out, rc = _run_sudo(["sudo", "-n", "cat", path], timeout=5.0)
    return out if rc == 0 else None


def _find_rocm_smi() -> Optional[str]:
    found = shutil.which("rocm-smi")
    if found and os.path.exists(os.path.realpath(found)):
        return found
    candidates = ["/opt/rocm/bin/rocm-smi"] + sorted(
        glob.glob("/opt/rocm-*/bin/rocm-smi")
    )
    for c in candidates:
        if os.path.exists(os.path.realpath(c)):
            return c
    return None


# ---------------------------------------------------------------------------
# rocm-smi text parsing (one combined invocation per sample)
# ---------------------------------------------------------------------------


def parse_rocm_smi_sample(text: str) -> Dict[int, Dict[str, Optional[float]]]:
    """Parse one combined --showuse/--showmeminfo/--showtemp/--showpower/
    --showclocks rocm-smi invocation. Returns {rocm_index: {metric: value}}."""
    out: Dict[int, Dict[str, Optional[float]]] = {}

    def cell(idx: int) -> Dict[str, Optional[float]]:
        return out.setdefault(
            idx,
            {
                "util_pct": None,
                "vram_used_bytes": None,
                "vram_total_bytes": None,
                "temp_c": None,
                "power_w": None,
                "sclk_mhz": None,
            },
        )

    patterns = [
        (r"GPU\[(\d+)\]\s*:\s*GPU use \(%\):\s*(\d+)", "util_pct", int),
        (r"GPU\[(\d+)\]\s*:\s*VRAM Total Memory \(B\):\s*(\d+)", "vram_total_bytes", int),
        (r"GPU\[(\d+)\]\s*:\s*VRAM Total Used Memory \(B\):\s*(\d+)", "vram_used_bytes", int),
        (r"GPU\[(\d+)\]\s*:\s*Temperature \(Sensor junction\)[^:]*:\s*([\d.]+)", "temp_c", float),
        (r"GPU\[(\d+)\]\s*:\s*Current Socket Graphics Package Power \(W\):\s*([\d.]+)", "power_w", float),
        (r"GPU\[(\d+)\]\s*:\s*sclk clock level:\s*\d+:\s*\((\d+)Mhz\)", "sclk_mhz", int),
    ]
    for line in text.splitlines():
        for pat, key, conv in patterns:
            m = re.match(pat, line)
            if m:
                cell(int(m.group(1)))[key] = conv(m.group(2))
                break
    return out


def parse_rocm_smi_uniqueid(text: str) -> Dict[int, str]:
    """{rocm_index: '0x...' lowercase hex}."""
    out: Dict[int, str] = {}
    for line in text.splitlines():
        m = re.match(r"GPU\[(\d+)\]\s*:\s*Unique ID:\s*(0x[0-9a-fA-F]+)", line)
        if m:
            out[int(m.group(1))] = m.group(2).lower()
    return out


# ---------------------------------------------------------------------------
# KFD-only metrics: plain sysfs reads under /sys/class/drm/card*/device,
# never a rocm-smi/amd-smi invocation. Each field is an independent,
# bounded single open+read and is skipped (left None / "n/a") on any error.
# ---------------------------------------------------------------------------


def _parse_active_sclk_mhz(pp_dpm_sclk_text: str) -> Optional[int]:
    """Parse ``pp_dpm_sclk`` text; the line marked with ``*`` is the active
    clock, e.g. ``1: 1200Mhz *``."""
    for line in pp_dpm_sclk_text.splitlines():
        if "*" in line:
            m = re.search(r"(\d+)Mhz", line)
            if m:
                return int(m.group(1))
    return None


def read_card_sysfs_metrics(card: str) -> Dict[str, Optional[float]]:
    """{util_pct, vram_used_bytes, vram_total_bytes, temp_c, power_w,
    sclk_mhz} for one GPU's DRM card, via plain sysfs reads only. Never
    calls rocm-smi or amd-smi. Missing/unreadable fields stay None."""
    device_dir = f"/sys/class/drm/{card}/device"
    out: Dict[str, Optional[float]] = {
        "util_pct": None,
        "vram_used_bytes": None,
        "vram_total_bytes": None,
        "temp_c": None,
        "power_w": None,
        "sclk_mhz": None,
    }

    busy = _read(f"{device_dir}/gpu_busy_percent")
    if busy is not None:
        try:
            out["util_pct"] = int(busy.strip())
        except ValueError:
            pass

    vram_used = _read(f"{device_dir}/mem_info_vram_used")
    if vram_used is not None:
        try:
            out["vram_used_bytes"] = int(vram_used.strip())
        except ValueError:
            pass

    vram_total = _read(f"{device_dir}/mem_info_vram_total")
    if vram_total is not None:
        try:
            out["vram_total_bytes"] = int(vram_total.strip())
        except ValueError:
            pass

    try:
        hwmon_dirs = sorted(glob.glob(f"{device_dir}/hwmon/hwmon*"))
    except OSError:
        hwmon_dirs = []
    if hwmon_dirs:
        temp_raw = _read(f"{hwmon_dirs[0]}/temp1_input")
        if temp_raw is not None:
            try:
                out["temp_c"] = int(temp_raw.strip()) / 1000.0
            except ValueError:
                pass
        power_raw = _read(f"{hwmon_dirs[0]}/power1_average")
        if power_raw is not None:
            try:
                out["power_w"] = int(power_raw.strip()) / 1_000_000.0
            except ValueError:
                pass

    sclk_raw = _read(f"{device_dir}/pp_dpm_sclk")
    if sclk_raw is not None:
        out["sclk_mhz"] = _parse_active_sclk_mhz(sclk_raw)

    return out


# ---------------------------------------------------------------------------
# KFD topology: gpu_id -> render minor / unique_id (static per boot)
# ---------------------------------------------------------------------------


def read_kfd_topology() -> Dict[int, Dict[str, Optional[int]]]:
    """{gpu_id: {"render_minor": int, "unique_id_dec": int or None, "node": int}}.

    Skips CPU nodes (gpu_id == 0)."""
    out: Dict[int, Dict[str, Optional[int]]] = {}
    base = "/sys/class/kfd/kfd/topology/nodes"
    try:
        nodes = os.listdir(base)
    except OSError:
        return out
    for node in nodes:
        gpu_id_raw = _read(f"{base}/{node}/gpu_id")
        if gpu_id_raw is None:
            continue
        try:
            gpu_id = int(gpu_id_raw.strip())
        except ValueError:
            continue
        if gpu_id == 0:
            continue  # CPU node
        props = _read(f"{base}/{node}/properties") or ""
        render_minor = None
        unique_id_dec = None
        for line in props.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            k, v = parts
            if k == "drm_render_minor":
                render_minor = int(v)
            elif k == "unique_id":
                unique_id_dec = int(v)
        out[gpu_id] = {
            "render_minor": render_minor,
            "unique_id_dec": unique_id_dec,
            "node": int(node) if node.isdigit() else None,
        }
    return out


def gpu_ids_by_index(topology: Dict[int, Dict[str, Optional[int]]]) -> List[int]:
    """gpu_ids in GPU-index order as users and amd-smi number them: by KFD topology node."""
    return sorted(topology, key=lambda g: (topology[g]["node"] is None, topology[g]["node"]))


def render_minor_to_card(render_minor: int) -> Optional[str]:
    """Resolve a DRM render minor to its sibling card<N> via sysfs device realpath."""
    render_path = f"/sys/class/drm/renderD{render_minor}/device"
    try:
        target = os.path.realpath(render_path)
    except OSError:
        return None
    for card_path in sorted(glob.glob("/sys/class/drm/card[0-9]*/device")):
        if os.path.realpath(card_path) == target:
            # card_path looks like /sys/class/drm/card3/device
            return card_path.split("/")[-2]
    return None


def map_gpu_id_to_rocm_index(
    topology: Dict[int, Dict[str, Optional[int]]],
    uniqueid_map: Dict[int, str],
) -> Tuple[Dict[int, int], bool]:
    """Join KFD gpu_id -> rocm-smi index via the Unique ID (hex), which is
    the only value both sides expose unambiguously. Returns (mapping, assumed)
    where assumed=True means the hex join failed and we fell back to sorted
    order (gpu_id order == rocm-smi index order), which is usually but not
    guaranteedly true."""
    hex_to_index = {v: k for k, v in uniqueid_map.items()}
    mapping: Dict[int, int] = {}
    for gpu_id, info in topology.items():
        udec = info.get("unique_id_dec")
        if udec is None:
            continue
        uhex = "0x" + format(udec, "x")
        if uhex in hex_to_index:
            mapping[gpu_id] = hex_to_index[uhex]
    if len(mapping) == len(topology) and topology:
        return mapping, False
    # Fallback: assume ascending gpu_id order matches ascending rocm-smi index.
    assumed: Dict[int, int] = {}
    for i, gpu_id in enumerate(sorted(topology)):
        assumed[gpu_id] = i
    return assumed, True


# ---------------------------------------------------------------------------
# KFD per-pid GPU usage (the box-global /sys/class/kfd/kfd/proc list, scoped
# to the GPUs a process has queues on, so attribution is per-GPU, not per-box)
# ---------------------------------------------------------------------------

def _queue_gpu_ids(pid_dir: str) -> Optional[Set[int]]:
    """gpu_ids of a pid's live KFD queues; None if they exist but cannot be read (direct read and ``sudo -n`` both failed)."""
    queues = _listdir_privileged(f"{pid_dir}/queues")
    if queues is None:
        return None
    gpu_ids: Set[int] = set()
    denied: List[str] = []
    for queue in queues:
        path = f"{pid_dir}/queues/{queue}/gpuid"
        try:
            with open(path, "r") as f:
                raw = f.read().strip()
        except PermissionError:
            denied.append(path)
            continue
        except OSError:
            continue  # the queue closed meanwhile
        if raw.isdigit():
            gpu_ids.add(int(raw))
    if denied:
        # One call for all denied queues; not budgeted, like the listing: this is the GPU attribution itself.
        out, rc = _run(["sudo", "-n", "cat", *denied], timeout=5.0)
        found = {int(w) for w in out.split() if w.isdigit()}
        if not found and rc != 0:
            return None
        gpu_ids |= found
    return gpu_ids


def sample_kfd_proc() -> Tuple[Dict[int, Dict[int, Optional[int]]], Set[int]]:
    """({gpu_id: {pid: vram_bytes_or_None}}, pids whose queues could not be read) for the current instant."""
    result: Dict[int, Dict[int, Optional[int]]] = {}
    unreadable: Set[int] = set()
    try:
        pids = [p for p in os.listdir(KFD_PROC) if p.isdigit()]
    except OSError:
        return result, unreadable
    for pid_s in pids:
        pid = int(pid_s)
        # A process occupies a GPU only if it has a queue on it. The per-GPU stats_/vram_/counters_ entries exist for every
        # GPU a process merely opened (device enumeration creates them on all GPUs), so they are not evidence of use.
        gpu_ids_here = _queue_gpu_ids(f"{KFD_PROC}/{pid_s}")
        if gpu_ids_here is None:
            # Which GPUs it uses is unknown: never let it drop out of the sample (that would print the GPU free).
            if os.path.isdir(f"{KFD_PROC}/{pid_s}"):  # else it exited meanwhile
                unreadable.add(pid)
            continue
        for gpu_id in gpu_ids_here:
            vram_bytes = None
            vram_raw = _read(f"{KFD_PROC}/{pid_s}/vram_{gpu_id}")
            if vram_raw is not None:
                try:
                    vram_bytes = int(vram_raw.strip())
                except ValueError:
                    vram_bytes = None
            result.setdefault(gpu_id, {})[pid] = vram_bytes
    return result, unreadable


# ---------------------------------------------------------------------------
# Process ancestry / identity
# ---------------------------------------------------------------------------


def _boot_time_epoch() -> float:
    stat = _read("/proc/stat") or ""
    for line in stat.splitlines():
        if line.startswith("btime "):
            return float(line.split()[1])
    return time.time()  # degrade gracefully


def _parse_stat(pid: int) -> Optional[Dict]:
    raw = _pid_file(pid, "stat")
    if raw is None:
        return None
    try:
        first_paren = raw.index("(")
        last_paren = raw.rindex(")")
        comm = raw[first_paren + 1 : last_paren]
        rest = raw[last_paren + 2 :].split()
        return {
            "comm": comm,
            "ppid": int(rest[1]),
            "tty_nr": int(rest[4]),
            "starttime_ticks": int(rest[19]),
        }
    except (ValueError, IndexError):
        return None


def _tty_name(tty_nr: int) -> Optional[str]:
    if tty_nr == 0:
        return None
    major, minor = tty_nr >> 8, tty_nr & 0xFF
    # Best-effort common cases; not resolved further to avoid walking /dev.
    if major == 136:
        return f"pts/{minor}"
    if major == 4:
        return f"tty{minor}"
    return f"{major}:{minor}"


def _cmdline(pid: int) -> str:
    raw = _pid_file(pid, "cmdline")
    if raw is None:
        return "(unreadable)"
    parts = raw.split("\0")
    cmd = " ".join(p for p in parts if p)
    if not cmd:
        return "(zombie or kernel thread)"
    return cmd[:CMD_TRUNCATE]


def _user_of(pid: int) -> str:
    st = _pid_file(pid, "status") or ""
    for line in st.splitlines():
        if line.startswith("Uid:"):
            uid = int(line.split()[1])
            try:
                import pwd

                return pwd.getpwuid(uid).pw_name
            except KeyError:
                return str(uid)
    return "(unknown)"


def _cgroup_info(pid: int) -> Dict[str, Optional[str]]:
    raw_opt = _pid_file(pid, "cgroup")
    raw = raw_opt or ""
    if raw_opt is None:
        return {"docker_id": None, "systemd_scope": None, "slurm_job": None, "cgroup_unreadable": True}
    docker_id = None
    systemd_scope = None
    slurm_job = None
    for line in raw.splitlines():
        m = re.search(r"docker-([0-9a-f]{12,64})\.scope", line)
        if m:
            docker_id = m.group(1)[:12]
        m = re.search(r"/docker/([0-9a-f]{12,64})", line)
        if m and not docker_id:
            docker_id = m.group(1)[:12]
        m = re.search(r"/job_(\d+)", line)
        if m:
            slurm_job = m.group(1)
        m = re.search(r"/([\w.@-]+)\.scope\s*$", line)
        if m and not docker_id:
            systemd_scope = m.group(1)
    return {
        "docker_id": docker_id,
        "systemd_scope": systemd_scope,
        "slurm_job": slurm_job,
        "cgroup_unreadable": False,
    }


# Lock file convention learned from GEAK's gpu_lock.sh: `flock` holds the
# lock on an inherited fd (200) across `exec "$@"`, so the GPU-using process
# (and its ancestors up to the gpu_lock.sh shell) keep an fd pointing at
# /tmp/team_gpu_locks/gpu_<id>.lock for the whole command. Match that
# specifically, and fall back to any generic "*lock*" path under /tmp or
# /var/lock so other teams' conventions are still caught.
_SPECIFIC_LOCK_RE = re.compile(r"/team_gpu_locks/gpu_\d+\.lock$")
_GENERIC_LOCK_RE = re.compile(r"^(/tmp/|/var/lock/).*lock")


def _fd_targets(pid: int) -> List[str]:
    """Targets of every open fd of ``pid``.

    A process we cannot read directly (another user's) is listed with ONE
    ``sudo -n ls -l`` call. A per-fd ``sudo readlink`` costs 2-4 s per call, so
    a process with ~500 fds (observed: hipblaslt-test) took 15-18 s and pushed
    the collect past the caller's deadline."""
    fd_dir = f"/proc/{pid}/fd"
    try:
        entries = os.listdir(fd_dir)
    except PermissionError:
        out, rc = _run_sudo(["sudo", "-n", "ls", "-l", fd_dir], timeout=5.0)
        if rc != 0:
            return []
        return [line.split(" -> ", 1)[1] for line in out.splitlines() if " -> " in line]
    except OSError:
        return []
    targets: List[str] = []
    for entry in entries:
        try:
            targets.append(os.readlink(f"{fd_dir}/{entry}"))
        except OSError:
            continue
    return targets


def _find_lock_fds(pid: int) -> List[str]:
    return [t for t in _fd_targets(pid) if _SPECIFIC_LOCK_RE.search(t) or _GENERIC_LOCK_RE.search(t)]


def _loginuid_owner(pid: Optional[int], live: bool = False) -> Optional[str]:
    """Login account recorded in /proc/<pid>/loginuid (kernel audit uid set at login, inherited by every
    child including processes in containers), or None if unset, unreadable or not a login account."""
    raw = _pid_file(pid, "loginuid", live) if pid else None
    try:
        uid = int((raw or "").strip())
    except ValueError:
        return None
    if uid == UNSET_LOGINUID:
        return None
    import pwd

    try:
        return _login_account(pwd.getpwuid(uid).pw_name)
    except KeyError:
        return None


def _ancestor_chain(pid: int, max_depth: int = 25) -> List[Dict]:
    chain: List[Dict] = []
    seen: Set[int] = set()
    cur = pid
    for _ in range(max_depth):
        if cur in seen or cur <= 1:
            break
        seen.add(cur)
        st = _parse_stat(cur)
        if st is None:
            break
        chain.append({"pid": cur, "comm": st["comm"], "cmd": _cmdline(cur), "user": _user_of(cur)})
        comm_lower = st["comm"].lower()
        if "containerd-shim" in comm_lower or st["ppid"] in (0, 1) or cur == st["ppid"]:
            break
        cur = st["ppid"]
    return chain


def collect_pid_info(pid: int, boot_epoch: float) -> Dict:
    info: Dict = {"notes": []}
    st = _parse_stat(pid)
    if st is None:
        info["notes"].append("process exited before it could be inspected")
        info["owner_user"], info["owner_evidence"], info["owner_error"] = process_owner(info, pid)
        return info

    info["user"] = _user_of(pid)
    info["loginuid_user"] = _loginuid_owner(pid)
    info["cmd"] = _cmdline(pid)
    info["ppid"] = st["ppid"]
    info["tty"] = _tty_name(st["tty_nr"])
    start_epoch = boot_epoch + st["starttime_ticks"] / HZ
    info["start_epoch"] = start_epoch
    info["elapsed_s"] = max(0.0, time.time() - start_epoch)

    cwd = _readlink_privileged(f"/proc/{pid}/cwd")
    if cwd is None:
        info["cwd"] = None
        info["notes"].append("cwd unreadable (different user; sudo -n unavailable or denied)")
    else:
        info["cwd"] = cwd

    environ_raw, environ_err = _read_privileged(f"/proc/{pid}/environ")
    if environ_err:
        info["environ_readable"] = False
        info["notes"].append(f"environ unreadable: {environ_err}")
        info["env_user"] = None
        info["env_home"] = None
        info["env_slurm_job_id"] = None
    else:
        info["environ_readable"] = True
        env_vars = dict(
            kv.split("=", 1) for kv in (environ_raw or "").split("\0") if "=" in kv
        )
        info["env_user"] = env_vars.get("USER")
        info["env_home"] = env_vars.get("HOME")
        info["env_slurm_job_id"] = env_vars.get("SLURM_JOB_ID")
        info["env_gpu_visible"] = {
            k: env_vars[k]
            for k in ("HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES")
            if k in env_vars
        }

    cg = _cgroup_info(pid)
    info.update(cg)
    if cg.get("cgroup_unreadable"):
        info["notes"].append("cgroup/container unreadable (process likely exited mid-trace)")

    info["ancestors"] = _ancestor_chain(pid)
    ssh_tmux_ancestry = [
        a["comm"] for a in info["ancestors"] if a["comm"].lower() in ("sshd", "tmux", "screen", "tmux: server")
    ]
    info["session_ancestry"] = ssh_tmux_ancestry

    locks: List[str] = _find_lock_fds(pid)
    for anc in info["ancestors"][1:]:
        locks.extend(_find_lock_fds(anc["pid"]))
    info["lock_files"] = sorted(set(locks))
    if not locks and any("gpu_lock.sh" in a["cmd"] for a in info["ancestors"]):
        info["notes"].append("gpu_lock.sh seen in ancestry but no lock fd could be read")

    if not info.get("docker_id"):
        info["owner_user"], info["owner_evidence"], info["owner_error"] = process_owner(info, pid)
    elif info["loginuid_user"]:
        # Container processes: the in-container uid and env are the container's, only the loginuid names the host person.
        info["owner_user"], info["owner_evidence"], info["owner_error"] = info["loginuid_user"], "process loginuid", None
    return info


# ---------------------------------------------------------------------------
# Docker container details
# ---------------------------------------------------------------------------


def docker_ps_map() -> Dict[str, Dict]:
    """{12-hex container id: {name, image, created}}."""
    out, rc = _run(
        ["docker", "ps", "--no-trunc", "--format", "{{.ID}} {{.Names}} {{.Image}} {{.CreatedAt}}"]
    )
    result: Dict[str, Dict] = {}
    if rc != 0:
        return result
    for line in out.strip().splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        full_id, name, image = parts[0], parts[1], parts[2]
        created = parts[3] if len(parts) > 3 else None
        result[full_id[:12]] = {"name": name, "image": image, "created": created, "full_id": full_id}
    return result


# ---------------------------------------------------------------------------
# Owner resolution: always end at a real login account on this host
# ---------------------------------------------------------------------------


def _login_account(name: Optional[str]) -> Optional[str]:
    """`name` if it is a non-root login account on this host, else None."""
    if not name or name == "root":
        return None
    import pwd

    try:
        return pwd.getpwnam(name).pw_name
    except KeyError:
        return None


def _path_owner(path: str) -> Optional[str]:
    try:
        import pwd

        return _login_account(pwd.getpwuid(os.stat(path).st_uid).pw_name)
    except (OSError, KeyError):
        out, rc = _run_sudo(["sudo", "-n", "stat", "-c", "%U", path])
        return _login_account(out.strip()) if rc == 0 else None


def _logins_near(epoch: Optional[float], window_s: int = 60) -> List[str]:
    """Non-root users whose login session opened within window_s of epoch (journal)."""
    if epoch is None:
        return []
    out, rc = _run_sudo(
        ["sudo", "-n", "journalctl", "--no-pager", "-o", "cat",
         f"--since=@{int(epoch) - window_s}", f"--until=@{int(epoch) + window_s}"],
        timeout=15.0,
    )
    users: List[str] = []
    for u in re.findall(r"session opened for user ([\w.-]+)\(", out if rc == 0 else ""):
        if u != "root" and u not in users:
            users.append(u)
    return users


def _rfc3339_epoch(ts: Optional[str]) -> Optional[float]:
    import calendar

    try:
        return float(calendar.timegm(time.strptime((ts or "")[:19], "%Y-%m-%dT%H:%M:%S")))
    except ValueError:
        return None


def _single_login_near(epoch: Optional[float]) -> Optional[str]:
    """The one user who logged in within 60 s of epoch and still has a session now. Short-lived logins (polling
    scripts) have closed by now, so a process that is still running belongs to a surviving session; with
    several survivors the evidence does not decide and the answer is None, never a list."""
    near = _logins_near(epoch)
    if not near:
        return None
    out, rc = _run(["who"], timeout=5.0)
    online = {line.split()[0] for line in out.splitlines() if line.split()} if rc == 0 else set()
    survivors = [u for u in near if u in online]
    return survivors[0] if len(survivors) == 1 else None


def _journal_pid_user(pid: int) -> Optional[str]:
    """Login account the journal recorded (``_AUDIT_LOGINUID``) for a message of this pid: works after the pid exited."""
    out, rc = _run_sudo(["sudo", "-n", "journalctl", "--no-pager", "-o", "json", "-n", "1", f"_PID={pid}"], timeout=10.0)
    if rc != 0:
        return None
    for line in out.splitlines():
        try:
            uid = int(json.loads(line).get("_AUDIT_LOGINUID", UNSET_LOGINUID))
        except (ValueError, TypeError):
            continue
        if uid != UNSET_LOGINUID:
            import pwd

            try:
                return _login_account(pwd.getpwuid(uid).pw_name)
            except KeyError:
                return None
    return None


def _exec_owner(container: str) -> Optional[str]:
    """The one non-root login running a live ``docker exec/run`` into this container, else None."""
    out, rc = _run(["pgrep", "-a", "-f", f"docker.*(exec|run).*{re.escape(container.lstrip('/'))}"], timeout=5.0)
    pids = [l.split(None, 1)[0] for l in out.splitlines() if rc == 0 and l.split(None, 1)[0].isdigit()]
    if not pids:
        return None
    out, rc = _run(["ps", "-o", "user=", "-p", ",".join(pids)], timeout=5.0)
    users = {_login_account(u.strip()) for u in out.splitlines()} - {None} if rc == 0 else set()
    return users.pop() if len(users) == 1 else None


def container_owner(name: str, labels: Dict[str, str], mounts: List[Dict], env_list: List[str], created: str,
                    init_pid: Optional[int], process_login: Optional[str]) -> Tuple[Optional[str], str]:
    """(login user or None, evidence or error) for a container. Direct evidence of who started it comes first
    (loginuid of the GPU process, loginuid of the container init, a live docker exec/run, an owner label);
    mount, env, name and journal are hints for when none of that is available."""
    if process_login:
        return process_login, "loginuid of the GPU process"
    # docker inspect reports State.Pid > 0 only for a running container, so the init pid is known to be live.
    user = _loginuid_owner(init_pid, live=bool(init_pid and init_pid > 0))
    if user:
        return user, "loginuid of the container init process"
    user = _exec_owner(name)
    if user:
        return user, f"live docker exec/run into {name}"
    for key in ("owner", "user"):
        user = _login_account(labels.get(key))
        if user:
            return user, f"container label {key}={labels[key]}"
    for m in mounts:
        src = m.get("Source", "") if isinstance(m, dict) else ""
        if src.startswith("/home/"):
            user = _path_owner(src)
            if user:
                return user, f"owner of bind mount {src}"
            user = _login_account(re.sub(r"^/home/(?:[A-Z]+/)?([^/]+).*", r"\1", src))
            if user:
                return user, f"bind mount {src}"
    env = dict(kv.split("=", 1) for kv in env_list if "=" in kv)
    for key in ("USER", "LOGNAME", "HOME"):
        user = _login_account(os.path.basename(env.get(key, "")))
        if user:
            return user, f"container env {key}={env[key]}"
    for token in re.split(r"[-_.]", name.lstrip("/")):
        user = _login_account(token)
        if user:
            return user, f"container name {name}"
    user = _single_login_near(_rfc3339_epoch(created))
    if user:
        return user, f"only login still open that logged in within 60 s of container creation {created}"
    return None, f"no login account found for container {name}"


def process_owner(info: Dict, pid: int) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(login user, evidence, error) for a host process (not in a container); exactly one of user and error is set."""
    candidates = [(info.get("loginuid_user"), "process loginuid"), (info.get("user"), "process uid"),
                  (info.get("env_user"), "process env USER")] + [
        (a.get("user"), f"ancestor {a.get('comm')} (pid {a.get('pid')})") for a in info.get("ancestors", [])
    ]
    for cand, why in candidates:
        user = _login_account(cand)
        if user:
            return user, why, None
    user = _journal_pid_user(pid)
    if user:
        return user, "journal _AUDIT_LOGINUID of the pid", None
    user = _single_login_near(info.get("start_epoch"))
    if user:
        return user, "only login still open that logged in within 60 s of process start", None
    return None, None, "no login account found (root process, no loginuid, no single login session near its start)"


def docker_inspect_details(container_id_or_name: str, process_login: Optional[str] = None) -> Dict:
    fmt = (
        "{{json .Config.Labels}}|||{{json .Config.Env}}|||{{json .Mounts}}|||"
        "{{.Created}}|||{{.State.Pid}}|||{{.State.StartedAt}}|||{{.Name}}"
    )
    out, rc = _run(["docker", "inspect", "--format", fmt, container_id_or_name])
    if rc != 0 or not out.strip():
        return {}
    try:
        labels_s, env_s, mounts_s, created, init_pid, started_at, name = out.strip().split("|||")
        env_list = json.loads(env_s) or []
        gpu_hint = {}
        for kv in env_list:
            if "=" in kv:
                k, v = kv.split("=", 1)
                if k in ("HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES"):
                    gpu_hint[k] = v
        mounts = json.loads(mounts_s) or []
        home_mounts = [
            m.get("Source")
            for m in mounts
            if isinstance(m, dict) and m.get("Source", "").startswith("/home/")
        ]
        labels = json.loads(labels_s) or {}
        init_pid = int(init_pid) if init_pid.strip().lstrip("-").isdigit() else None
        owner_user, owner_note = container_owner(name, labels, mounts, env_list, created, init_pid, process_login)
        return {
            "owner_user": owner_user,
            "owner_evidence": owner_note if owner_user else None,
            "owner_error": None if owner_user else owner_note,
            "labels": labels,
            "env": env_list,
            "gpu_env_hint": gpu_hint,
            "home_mounts": home_mounts,
            "created": created,
            "init_pid": init_pid,
            "started_at": started_at,
        }
    except (ValueError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# SLURM (best-effort; these hosts typically have none)
# ---------------------------------------------------------------------------


def slurm_job_info(job_id: str) -> Optional[Dict]:
    if not shutil.which("scontrol"):
        return None
    out, rc = _run(["scontrol", "show", "job", job_id])
    if rc != 0:
        return None
    info = {}
    for key in ("UserId", "JobName", "TimeLimit", "EndTime", "RunTime"):
        m = re.search(rf"{key}=(\S+)", out)
        if m:
            info[key] = m.group(1)
    return info or None


# ---------------------------------------------------------------------------
# Main collection
# ---------------------------------------------------------------------------


def collect(samples: int, interval: float, use_rocm_smi: bool = False) -> Dict:
    errors: List[str] = []
    _start_sudo_budget()
    rocm_smi = _find_rocm_smi() if use_rocm_smi else None
    if use_rocm_smi and rocm_smi is None:
        errors.append("rocm-smi not found on PATH or under /opt/rocm*/bin")

    topology = read_kfd_topology()
    if not topology:
        errors.append("no GPUs found under /sys/class/kfd/kfd/topology/nodes (no GPUs or no KFD)")

    uniqueid_map: Dict[int, str] = {}
    if rocm_smi:
        out, _ = _run([rocm_smi, "--showuniqueid"])
        uniqueid_map = parse_rocm_smi_uniqueid(out)
    gpu_id_to_index, index_assumed = (
        map_gpu_id_to_rocm_index(topology, uniqueid_map) if rocm_smi else ({}, False)
    )

    # Static per-boot render_minor -> card join, used by the KFD-only metrics
    # path below (never recomputed per sample).
    card_by_gpu_id: Dict[int, Optional[str]] = {
        gid: (render_minor_to_card(info["render_minor"]) if info["render_minor"] is not None else None)
        for gid, info in topology.items()
    }

    per_gpu_samples: Dict[int, List[Dict]] = {gid: [] for gid in topology}
    all_pids: Set[int] = set()
    unreadable_pids: Set[int] = set()  # queues unreadable: they may occupy any GPU

    # Trace every pid's identity THE MOMENT it is first seen, not after the
    # whole burst finishes: occupants are often short-lived (a harness
    # cycling every few seconds), and by the end of a multi-second burst a
    # pid caught in an early sample may have already exited, losing its
    # user/cmd/container/lock evidence for good.
    boot_epoch = _boot_time_epoch()
    containers_seen = docker_ps_map()
    pids_out: Dict[str, Dict] = {}
    containers_out: Dict[str, Dict] = {}
    slurm_jobs: Dict[str, Dict] = {}

    def _trace_new_pids(new_pids: Set[int]) -> None:
        for pid in new_pids:
            if str(pid) in pids_out:
                continue
            pinfo = collect_pid_info(pid, boot_epoch)
            pids_out[str(pid)] = pinfo
            docker_id = pinfo.get("docker_id")
            if docker_id and docker_id not in containers_out:
                meta = dict(containers_seen.get(docker_id, {}))
                name_or_id = meta.get("name") or docker_id
                meta.update(docker_inspect_details(name_or_id, pinfo.get("loginuid_user")))
                containers_out[docker_id] = meta
            job_id = pinfo.get("env_slurm_job_id")
            if job_id and job_id not in slurm_jobs:
                sj = slurm_job_info(job_id)
                if sj:
                    slurm_jobs[job_id] = sj

    for i in range(max(1, samples)):
        metrics_by_index: Dict[int, Dict] = {}
        if rocm_smi:
            out, _ = _run(
                [
                    rocm_smi,
                    "--showuse",
                    "--showmeminfo",
                    "vram",
                    "--showtemp",
                    "--showpower",
                    "--showclocks",
                ]
            )
            metrics_by_index = parse_rocm_smi_sample(out)
        kfd_sample, unreadable = sample_kfd_proc()  # {gpu_id: {pid: vram_bytes}}
        _trace_new_pids(unreadable - unreadable_pids)
        unreadable_pids |= unreadable

        for gpu_id in topology:
            rocm_index = gpu_id_to_index.get(gpu_id)
            if rocm_smi:
                metrics = metrics_by_index.get(rocm_index, {}) if rocm_index is not None else {}
            else:
                card = card_by_gpu_id.get(gpu_id)
                metrics = read_card_sysfs_metrics(card) if card else {}
            pid_vram = kfd_sample.get(gpu_id, {})
            _trace_new_pids(set(pid_vram.keys()) - all_pids)
            all_pids.update(pid_vram.keys())
            per_gpu_samples[gpu_id].append(
                {
                    "util_pct": metrics.get("util_pct"),
                    "vram_used_bytes": metrics.get("vram_used_bytes"),
                    "vram_total_bytes": metrics.get("vram_total_bytes"),
                    "temp_c": metrics.get("temp_c"),
                    "power_w": metrics.get("power_w"),
                    "sclk_mhz": metrics.get("sclk_mhz"),
                    "pids": {str(p): v for p, v in pid_vram.items()},
                }
            )
        if i < samples - 1:
            time.sleep(interval)

    by_node = gpu_ids_by_index(topology)
    gpus = []
    for gpu_id, info in sorted(topology.items()):
        rocm_index = gpu_id_to_index.get(gpu_id)
        card = render_minor_to_card(info["render_minor"]) if info["render_minor"] is not None else None
        occ_samples = sum(1 for s in per_gpu_samples[gpu_id] if s["pids"])
        gpus.append(
            {
                "gpu_id": gpu_id,
                "kfd_index": by_node.index(gpu_id),
                "rocm_index": rocm_index,
                "rocm_index_assumed": index_assumed,
                "unique_id_hex": (
                    "0x" + format(info["unique_id_dec"], "x") if info["unique_id_dec"] else None
                ),
                "render_minor": info["render_minor"],
                "card": card,
                "samples": per_gpu_samples[gpu_id],
                "queue_unreadable_pids": sorted(str(p) for p in unreadable_pids),
                "duty_cycle": occ_samples / len(per_gpu_samples[gpu_id]) if per_gpu_samples[gpu_id] else 0.0,
            }
        )

    if unreadable_pids:
        errors.append(
            f"KFD queues of pid(s) {', '.join(str(p) for p in sorted(unreadable_pids))} are not readable "
            "(permission denied, sudo -n failed): which GPUs they use is unknown, so no GPU is reported free"
        )
    if _sudo_budget_spent:
        errors.append(
            f"privileged lookups skipped after the {_SUDO_BUDGET_S:.0f} s budget "
            "(cwd/fd/journal enrichment incomplete; GPU attribution unaffected)"
        )

    return {
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "samples": samples,
        "interval": interval,
        "mode": "rocm-smi" if rocm_smi else "kfd-only",
        "rocm_smi_path": rocm_smi,
        "gpus": gpus,
        "pids": pids_out,
        "containers": containers_out,
        "slurm_jobs": slurm_jobs,
        "slurm_available": shutil.which("scontrol") is not None,
        "errors": errors,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--marker", required=True, help="unique token to frame stdout with")
    ap.add_argument(
        "--rocm-smi",
        action="store_true",
        help="use rocm-smi for util/clock/power/temp (default: KFD/sysfs-only, "
        "never invokes rocm-smi or amd-smi)",
    )
    args = ap.parse_args()

    data = collect(args.samples, args.interval, args.rocm_smi)
    print(f"{args.marker}_START")
    print(json.dumps(data))
    print(f"{args.marker}_END")


if __name__ == "__main__":
    main()
