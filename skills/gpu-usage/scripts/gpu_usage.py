#!/usr/bin/env python3
"""GPU usage report — shows which processes occupy each GPU.

Runs rocm-smi and system commands, parses outputs, and produces a concise
table (markdown or JSON) so you can decide whether to proceed with profiling
or contact the process owner.

Linux-only.  Stdlib only.  Requires ``rocm-smi`` on PATH.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: List[str], *, check: bool = False) -> Tuple[str, int]:
    """Run *cmd*, return (stdout, returncode).  Never raises on non-zero rc
    unless *check* is True."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return r.stdout, r.returncode
    except FileNotFoundError:
        return "", -1
    except subprocess.CalledProcessError as exc:
        return exc.stdout or "", exc.returncode


def _elapsed_human(seconds: int) -> str:
    """Convert elapsed seconds to compact human-readable form."""
    if seconds < 0:
        return "-"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d{h}h" if h else f"{d}d"
    if h:
        return f"{h}h{m}m" if m else f"{h}h"
    if m:
        return f"{m}m{s}s" if s else f"{m}m"
    return f"{s}s"


# ---------------------------------------------------------------------------
# Step 1 — Gather GPU state
# ---------------------------------------------------------------------------

def _parse_vram(output: str) -> Dict[int, Tuple[int, int]]:
    """Return {gpu_id: (used_bytes, total_bytes)}."""
    total: Dict[int, int] = {}
    used: Dict[int, int] = {}
    for line in output.splitlines():
        m = re.match(r"GPU\[(\d+)\]\s*:\s*VRAM Total Memory \(B\):\s*(\d+)", line)
        if m:
            total[int(m.group(1))] = int(m.group(2))
            continue
        m = re.match(r"GPU\[(\d+)\]\s*:\s*VRAM Total Used Memory \(B\):\s*(\d+)", line)
        if m:
            used[int(m.group(1))] = int(m.group(2))
    return {gid: (used.get(gid, 0), total[gid]) for gid in total}


def _parse_use(output: str) -> Dict[int, int]:
    """Return {gpu_id: utilisation_percent}."""
    result: Dict[int, int] = {}
    for line in output.splitlines():
        m = re.match(r"GPU\[(\d+)\]\s*:\s*GPU use \(%\):\s*(\d+)", line)
        if m:
            result[int(m.group(1))] = int(m.group(2))
    return result


def _parse_pidgpus(output: str) -> Dict[int, List[int]]:
    """Return {gpu_id: [pid, ...]} from ``--showpidgpus`` output.

    Filters out PIDs with ``0 DRM device(s)``."""
    # Output looks like:
    #   PID 12345 is using 2 DRM device(s):
    #   0 1
    #   PID 99999 is using 0 DRM device(s):
    gpu_pids: Dict[int, List[int]] = defaultdict(list)
    current_pid: Optional[int] = None
    skip = False
    for line in output.splitlines():
        m = re.match(r"PID\s+(\d+)\s+is using\s+(\d+)\s+DRM device", line)
        if m:
            current_pid = int(m.group(1))
            skip = int(m.group(2)) == 0
            continue
        if current_pid is not None and not skip:
            for tok in line.split():
                if tok.isdigit():
                    gpu_pids[int(tok)].append(current_pid)
    return dict(gpu_pids)


def _parse_showpids(output: str) -> Dict[int, List[int]]:
    """Fallback parser for ``--showpids``.

    Output format varies; typical lines:
        <pid>  <gpu_id>  ...
    or table rows with PID and GPU columns."""
    gpu_pids: Dict[int, List[int]] = defaultdict(list)
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            pid, gid = int(parts[0]), int(parts[1])
            gpu_pids[gid].append(pid)
    return dict(gpu_pids)


def gather_gpu_state() -> Tuple[
    Dict[int, Tuple[int, int]],  # vram: {gpu: (used, total)}
    Dict[int, int],              # util: {gpu: pct}
    Dict[int, List[int]],        # pids: {gpu: [pid, ...]}
]:
    """Run rocm-smi commands and return parsed data."""
    if not shutil.which("rocm-smi"):
        print("Error: rocm-smi not found on PATH.", file=sys.stderr)
        sys.exit(1)

    vram_out, _ = _run(["rocm-smi", "--showmeminfo", "vram"], check=True)
    use_out, _ = _run(["rocm-smi", "--showuse"], check=True)

    pidgpu_out, rc = _run(["rocm-smi", "--showpidgpus"])
    if rc != 0:
        pidgpu_out, _ = _run(["rocm-smi", "--showpids"])
        gpu_pids = _parse_showpids(pidgpu_out)
    else:
        gpu_pids = _parse_pidgpus(pidgpu_out)

    return _parse_vram(vram_out), _parse_use(use_out), gpu_pids


# ---------------------------------------------------------------------------
# Step 2 — Process details
# ---------------------------------------------------------------------------

def _get_process_details(pids: List[int]) -> Dict[int, Tuple[str, int, str]]:
    """Return {pid: (user, elapsed_seconds, full_args)}.

    Missing PIDs (process exited) get ("(exited)", -1, "(exited)")."""
    if not pids:
        return {}

    pid_str = ",".join(str(p) for p in pids)
    out, _ = _run(["ps", "-o", "pid,user,etimes,args", "-p", pid_str, "--no-headers"])

    result: Dict[int, Tuple[str, int, str]] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid = int(parts[0])
        user = parts[1]
        try:
            etimes = int(parts[2])
        except ValueError:
            etimes = -1
        args = parts[3]
        result[pid] = (user, etimes, args)

    # Mark missing PIDs
    for pid in pids:
        if pid not in result:
            result[pid] = ("-", -1, "(exited)")

    return result


# ---------------------------------------------------------------------------
# Step 3 — Container detection
# ---------------------------------------------------------------------------

def _detect_containers(
    proc_details: Dict[int, Tuple[str, int, str]],
) -> Dict[int, Tuple[str, str]]:
    """Return {pid: (resolved_user, container_name)}.

    Only attempts detection for root-owned processes.  Returns ("-", "-")
    for non-root processes."""
    has_docker = shutil.which("docker") is not None
    root_pids = {p for p, (u, _, __) in proc_details.items() if u == "root"}

    if not root_pids or not has_docker:
        return {p: (u, "-") for p, (u, _, __) in proc_details.items()}

    result: Dict[int, Tuple[str, str]] = {}

    # Cache: command_keyword -> (host_user, container_name)
    cache: Dict[str, Tuple[str, str]] = {}

    for pid, (user, _, args) in proc_details.items():
        if pid not in root_pids:
            result[pid] = (user, "-")
            continue

        # Extract a keyword from the command for pgrep matching
        keyword = _extract_keyword(args)
        if keyword and keyword in cache:
            host_user, container = cache[keyword]
            result[pid] = (host_user, container)
            continue

        host_user, container = _resolve_container(keyword)
        if keyword:
            cache[keyword] = (host_user, container)
        result[pid] = (host_user, container)

    return result


def _extract_keyword(args: str) -> str:
    """Pick a useful keyword from a command line for pgrep matching."""
    if args == "(exited)":
        return ""
    # Take the basename of the first token that looks like a command/script
    parts = args.split()
    for part in parts:
        # Skip interpreters
        if part in ("python", "python3", "bash", "sh"):
            continue
        # Skip flags
        if part.startswith("-"):
            continue
        # Use basename
        base = part.rsplit("/", 1)[-1]
        if base:
            return base
    return parts[0].rsplit("/", 1)[-1] if parts else ""


def _resolve_container(keyword: str) -> Tuple[str, str]:
    """Try to find the container name and host user for a root GPU process."""
    if keyword:
        pgrep_out, rc = _run(["pgrep", "-a", "-f", f"docker.*(exec|run).*{re.escape(keyword)}"])
        if rc == 0 and pgrep_out.strip():
            return _parse_docker_pgrep(pgrep_out)

    # Fallback: list containers and try matching
    docker_out, rc = _run(["docker", "ps", "--no-trunc", "--format", "{{.ID}} {{.Names}}"])
    if rc != 0 or not docker_out.strip():
        return ("(container)", "-")

    for line in docker_out.strip().splitlines():
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        container_name = parts[1]
        # Skip infra containers
        if any(infra in container_name.lower() for infra in ("exporter", "monitor", "grafana", "prometheus")):
            continue
        if keyword:
            pgrep_out2, rc2 = _run(["pgrep", "-a", "-f", f"docker.*(exec|run).*{re.escape(container_name)}"])
            if rc2 == 0 and pgrep_out2.strip():
                user, _ = _parse_docker_pgrep(pgrep_out2)
                return user, container_name

    return ("(container)", "-")


def _parse_docker_pgrep(pgrep_out: str) -> Tuple[str, str]:
    """Extract host user and container name from pgrep output matching docker
    exec/run commands."""
    pids: List[int] = []
    container_name = "-"
    has_run = False
    has_exec = False

    for line in pgrep_out.strip().splitlines():
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            pids.append(int(parts[0]))
        except ValueError:
            continue
        cmdline = parts[1]
        # Try to extract container name from the command
        name = _extract_container_name(cmdline)
        if name:
            container_name = name
        if "docker run" in cmdline:
            has_run = True
        if "docker exec" in cmdline:
            has_exec = True

    if not pids:
        return "(container)", container_name if container_name != "-" else "-"

    # Resolve host user from the pgrep PIDs
    pid_str = ",".join(str(p) for p in pids)
    user_out, _ = _run(["ps", "-o", "user", "--no-headers", "-p", pid_str])
    users = list(dict.fromkeys(u.strip() for u in user_out.splitlines() if u.strip()))

    if len(users) == 1:
        return users[0], container_name
    if len(users) > 1:
        # Prefer exec user (active workload user) over run user (container owner)
        # but this heuristic is simple — just pick the non-root user
        non_root = [u for u in users if u != "root"]
        return non_root[0] if non_root else users[0], container_name

    return "(container)", container_name


def _extract_container_name(cmdline: str) -> str:
    """Try to extract a container name from a docker exec/run command line."""
    # docker exec [options] <container> <command>
    # docker run [options] --name <name> ...
    parts = cmdline.split()
    try:
        idx = parts.index("exec") if "exec" in parts else -1
        if idx >= 0:
            # Skip options (start with -)
            for i in range(idx + 1, len(parts)):
                if not parts[i].startswith("-"):
                    return parts[i]

        idx = parts.index("run") if "run" in parts else -1
        if idx >= 0:
            # Look for --name
            for i in range(idx + 1, len(parts)):
                if parts[i] == "--name" and i + 1 < len(parts):
                    return parts[i + 1]
    except (ValueError, IndexError):
        pass
    return ""


# ---------------------------------------------------------------------------
# Step 4/5 — Filter idle GPUs and format output
# ---------------------------------------------------------------------------

def build_rows(
    vram: Dict[int, Tuple[int, int]],
    util: Dict[int, int],
    gpu_pids: Dict[int, List[int]],
    proc_details: Dict[int, Tuple[str, int, str]],
    containers: Dict[int, Tuple[str, str]],
) -> List[dict]:
    """Build the final list of row dicts, filtering idle GPUs."""
    all_gpus = sorted(set(vram) | set(util) | set(gpu_pids))
    rows: List[dict] = []

    for gid in all_gpus:
        used, total = vram.get(gid, (0, 1))
        vram_pct = round(used / total * 100) if total else 0
        util_pct = util.get(gid, 0)
        pids = gpu_pids.get(gid, [])

        # Filter idle GPUs
        if vram_pct == 0 and util_pct == 0 and not pids:
            continue

        if not pids:
            rows.append({
                "gpu": gid,
                "vram_pct": vram_pct,
                "util_pct": util_pct,
                "pid": "-",
                "user": "-",
                "elapsed": "-",
                "command": "-",
                "container": "-",
            })
            continue

        for pid in sorted(pids):
            user, etimes, args = proc_details.get(pid, ("-", -1, "(exited)"))
            resolved_user, container = containers.get(pid, (user, "-"))
            rows.append({
                "gpu": gid,
                "vram_pct": vram_pct,
                "util_pct": util_pct,
                "pid": pid,
                "user": resolved_user,
                "elapsed": _elapsed_human(etimes),
                "command": args[:60],
                "container": container,
            })

    return rows


def format_markdown(rows: List[dict]) -> str:
    """Render rows as a markdown table."""
    if not rows:
        return "All GPUs are idle."

    header = "| GPU | VRAM% | GPU Util% | PID | User | Elapsed | Command | Container |"
    sep = "|-----|-------|-----------|-----|------|---------|---------|-----------|"
    lines = [header, sep]
    for r in rows:
        lines.append(
            f"| {r['gpu']} "
            f"| {r['vram_pct']}% "
            f"| {r['util_pct']}% "
            f"| {r['pid']} "
            f"| {r['user']} "
            f"| {r['elapsed']} "
            f"| {r['command']} "
            f"| {r['container']} |"
        )
    return "\n".join(lines)


def format_json(rows: List[dict]) -> str:
    """Render rows as JSON."""
    if not rows:
        return json.dumps({"status": "idle", "gpus": []}, indent=2)
    return json.dumps({"status": "active", "gpus": rows}, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="GPU usage report (rocm-smi)")
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    args = parser.parse_args()

    vram, util, gpu_pids = gather_gpu_state()

    # Collect all unique PIDs
    all_pids = sorted({p for pids in gpu_pids.values() for p in pids})

    proc_details = _get_process_details(all_pids)
    containers = _detect_containers(proc_details)
    rows = build_rows(vram, util, gpu_pids, proc_details, containers)

    if args.format == "json":
        print(format_json(rows))
    else:
        print(format_markdown(rows))


if __name__ == "__main__":
    main()
