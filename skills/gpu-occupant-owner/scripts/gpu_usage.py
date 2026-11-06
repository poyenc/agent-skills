#!/usr/bin/env python3
"""GPU usage report with real-owner tracing, local or over SSH.

Orchestrates ``gpu_collector.py`` (read-only, stdlib-only) locally and/or on
remote hosts, then renders a per-host occupancy table plus a decision-aid
verdict: is the GPU free / intermittently / continuously used, who really
owns the occupant, and what the options are. This script never signals or
otherwise touches anyone else's process -- it only reads.

Every run, local or ``--host``, is KFD/sysfs-only by default: rocm-smi/amd-smi are
NEVER invoked unless ``--rocm-smi`` is passed explicitly. Attribution
(owner/container/ancestry) and duty cycle never depended on rocm-smi; only
live util/clock/power/temp do, and those show as n/a in KFD-only mode.

Linux-only. Python 3.8+ stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COLLECTOR_PATH = os.path.join(SCRIPT_DIR, "gpu_collector.py")

SSH_OPTS = [
    "-o", "ConnectTimeout=8",
    "-o", "BatchMode=yes",
    "-o", "ServerAliveInterval=5",
    "-o", "ServerAliveCountMax=2",
]

DUTY_CONTINUOUS = 0.8
DUTY_IDLE = 0.0


# ---------------------------------------------------------------------------
# Collection: run the collector locally or over ssh, one round trip per host
# ---------------------------------------------------------------------------


def _extract_marked_json(stdout: str, marker: str) -> Tuple[Optional[dict], str]:
    """Pull the JSON blob framed by {marker}_START / {marker}_END out of
    stdout that may be contaminated by a login banner before or after it."""
    start_tag, end_tag = f"{marker}_START", f"{marker}_END"
    si = stdout.find(start_tag)
    ei = stdout.find(end_tag)
    if si == -1 or ei == -1 or ei < si:
        return None, stdout[-2000:]
    blob = stdout[si + len(start_tag) : ei].strip()
    try:
        return json.loads(blob), ""
    except json.JSONDecodeError as exc:
        return None, f"malformed JSON from collector: {exc}"


def _use_rocm_smi_for_host(host: Optional[str], opt_in: bool) -> bool:
    """Default: KFD-only (no rocm-smi/amd-smi invocation at all) on every
    host, local or remote -- rocm-smi/amd-smi have been observed to wedge
    or stall some hosts (a local run on a heliosr node hung ~30 s
    intermittently and reported "unreachable"), so they are called only when
    the caller explicitly opts in with --rocm-smi. ``host`` is kept so the
    callers need no change."""
    return opt_in


def _build_collector_args(samples: int, interval: float, marker: str, use_rocm_smi: bool) -> List[str]:
    args = ["--samples", str(samples), "--interval", str(interval), "--marker", marker]
    if use_rocm_smi:
        args.append("--rocm-smi")
    return args


def _build_remote_cmd(host: str, collector_args: List[str]) -> List[str]:
    return ["ssh"] + SSH_OPTS + [host, "python3", "-"] + collector_args


def collect_host(
    host: Optional[str], samples: int, interval: float, deadline: float, use_rocm_smi: bool
) -> Dict:
    """host=None means local. Returns a dict always containing 'host' and
    'status' ('ok' | 'unreachable' | 'error'), plus 'data' on success."""
    marker = f"GPUUSAGE_{uuid.uuid4().hex}"
    label = host or "local"
    args = _build_collector_args(samples, interval, marker, use_rocm_smi)

    try:
        with open(COLLECTOR_PATH, "r") as f:
            collector_src = f.read()
    except OSError as exc:
        return {"host": label, "status": "error", "message": f"cannot read collector script: {exc}"}

    try:
        if host is None:
            proc = subprocess.run(
                [sys.executable, COLLECTOR_PATH] + args,
                capture_output=True,
                text=True,
                timeout=deadline,
            )
        else:
            proc = subprocess.run(
                _build_remote_cmd(host, args),
                input=collector_src,
                capture_output=True,
                text=True,
                timeout=deadline,
            )
    except subprocess.TimeoutExpired:
        return {
            "host": label,
            "status": "unreachable",
            "message": f"unreachable/hung: no response within {deadline:.0f}s deadline",
        }
    except FileNotFoundError:
        return {"host": label, "status": "error", "message": "ssh not found on PATH"}

    data, tail = _extract_marked_json(proc.stdout, marker)
    if data is None:
        detail = tail or proc.stderr[-500:] or "(no output)"
        return {
            "host": label,
            "status": "unreachable" if proc.returncode != 0 else "error",
            "message": f"no parseable collector output (rc={proc.returncode}): {detail}",
        }
    return {"host": label, "status": "ok", "data": data}


def collect_all(
    hosts: List[Optional[str]], samples: int, interval: float, deadline: float, rocm_smi_opt_in: bool
) -> List[Dict]:
    if len(hosts) == 1:
        h = hosts[0]
        return [collect_host(h, samples, interval, deadline, _use_rocm_smi_for_host(h, rocm_smi_opt_in))]
    with ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        futures = [
            ex.submit(
                collect_host, h, samples, interval, deadline, _use_rocm_smi_for_host(h, rocm_smi_opt_in)
            )
            for h in hosts
        ]
        return [f.result() for f in futures]


# ---------------------------------------------------------------------------
# "Ours" classification
# ---------------------------------------------------------------------------


def classify_ours(pid: str, pinfo: dict, container_name: Optional[str], ours_patterns: List[str]) -> bool:
    for pat in ours_patterns:
        if container_name and pat == container_name:
            return True
        try:
            if re.search(pat, pid):
                return True
        except re.error:
            pass
    return False


# ---------------------------------------------------------------------------
# History (append-only; the caller schedules repeated runs, no daemon here)
# ---------------------------------------------------------------------------


def append_history(path: str, host: str, gpu_id: int, owner: str, foreign: bool) -> None:
    rec = {
        "ts": time.time(),
        "host": host,
        "gpu_id": gpu_id,
        "owner": owner,
        "foreign": foreign,
    }
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def read_history(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    recs = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return recs


def continuous_run(history: List[dict], host: str, gpu_id: int) -> Optional[Dict]:
    """For (host, gpu_id), find the run of most-recent entries sharing the
    same owner (a simple backward scan; a change of owner or an idle gap
    ends the run). Returns {owner, first_seen, last_seen, duration_s} or
    None if there's no history for this key."""
    entries = sorted(
        (r for r in history if r["host"] == host and r["gpu_id"] == gpu_id),
        key=lambda r: r["ts"],
    )
    if not entries:
        return None
    last = entries[-1]
    owner = last["owner"]
    first_seen = last["ts"]
    for r in reversed(entries[:-1]):
        if r["owner"] != owner:
            break
        first_seen = r["ts"]
    return {
        "owner": owner,
        "first_seen": first_seen,
        "last_seen": last["ts"],
        "duration_s": last["ts"] - first_seen,
        "sample_count": sum(1 for r in entries if r["ts"] >= first_seen),
    }


# ---------------------------------------------------------------------------
# Per-GPU occupant summarisation
# ---------------------------------------------------------------------------


def summarize_gpu(gpu: dict, pids: dict, containers: dict, ours_patterns: List[str]) -> dict:
    samples = gpu["samples"]
    n = len(samples) or 1
    occupant_pids: Dict[str, dict] = {}
    foreign_sample_count = 0
    unreadable_pids = [p for p in gpu.get("queue_unreadable_pids", []) if p in pids]

    def occupant(pid: str, queues_unreadable: bool) -> dict:
        pinfo = pids.get(pid, {})
        docker_id = pinfo.get("docker_id")
        container_name = containers.get(docker_id, {}).get("name") if docker_id else None
        return {
            "pid": pid,
            "user": pinfo.get("user", "(unknown)"),
            "cmd": pinfo.get("cmd", "(unreadable)"),
            "container": container_name,
            "docker_id": docker_id,
            "elapsed_s": pinfo.get("elapsed_s"),
            "ours": classify_ours(pid, pinfo, container_name, ours_patterns),
            "lock_files": pinfo.get("lock_files", []),
            "notes": pinfo.get("notes", []),
            "ancestors": pinfo.get("ancestors", []),
            "owner_user": pinfo.get("owner_user"),
            "owner_evidence": pinfo.get("owner_evidence"),
            "owner_error": pinfo.get("owner_error"),
            "queues_unreadable": queues_unreadable,
            "sample_hits": 0,
        }

    for s in samples:
        sample_had_foreign = False
        for pid in s["pids"]:
            if pid not in occupant_pids:
                occupant_pids[pid] = occupant(pid, False)
            if not occupant_pids[pid]["ours"]:
                sample_had_foreign = True
            occupant_pids[pid]["sample_hits"] += 1
        if sample_had_foreign:
            foreign_sample_count += 1
    # A pid whose queues cannot be read may occupy this GPU: list it, never report the GPU free.
    for pid in unreadable_pids:
        if pid not in occupant_pids:
            occupant_pids[pid] = occupant(pid, True)

    foreign_duty = foreign_sample_count / n
    any_foreign = any(not o["ours"] for o in occupant_pids.values())
    if unreadable_pids and gpu["duty_cycle"] == DUTY_IDLE:
        state = "occupancy unreadable (KFD queues of a process not readable)"
    elif gpu["duty_cycle"] == DUTY_IDLE:
        state = "free"
    elif foreign_duty >= DUTY_CONTINUOUS:
        state = "continuously used (foreign)" if any_foreign else "continuously used (ours)"
    elif foreign_duty > DUTY_IDLE:
        state = "intermittently used (foreign)" if any_foreign else "intermittently used (ours)"
    else:
        state = "used (ours only)"

    return {
        "gpu_id": gpu["gpu_id"],
        "kfd_index": gpu.get("kfd_index"),
        "rocm_index": gpu["rocm_index"],
        "rocm_index_assumed": gpu["rocm_index_assumed"],
        "render_minor": gpu["render_minor"],
        "card": gpu["card"],
        "duty_cycle": gpu["duty_cycle"],
        "foreign_duty_cycle": foreign_duty,
        "state": state,
        "occupants": sorted(occupant_pids.values(), key=lambda o: -o["sample_hits"]),
        "last_sample": samples[-1] if samples else {},
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _owner_label(occ: dict, containers: dict) -> str:
    owner, _ = _infer_owner_contact(occ, containers)
    return f"{owner} [{occ['container']}]" if occ["container"] else owner


def _infer_owner_contact(occ: dict, containers: dict) -> Tuple[str, bool]:
    """Returns (best-guess human-readable owner/contact string, is_inferred)."""
    docker_id = occ.get("docker_id")
    meta = containers.get(docker_id, {}) if docker_id else {}
    # The collector resolves a login account on the host itself, strongest evidence first (loginuid, docker exec, ...);
    # the process's own loginuid beats the container-level answer.
    for src in (occ, meta):
        if src.get("owner_user"):
            return src["owner_user"], src.get("owner_evidence") != "process uid"
    error = occ.get("owner_error") or meta.get("owner_error")
    if error:
        # The collector tried every evidence and validated each name: do not guess from container names or paths here.
        return f"(could not determine the owner: {error})", True
    # Data without collector verdicts (older collector output).
    home_mounts = meta.get("home_mounts") or []
    if home_mounts:
        # Matches both /home/<user>/... and /home/<domain>/<user>/...
        # (e.g. this environment's /home/AMD/<user>/...).
        m = re.search(r"/home/(?:[A-Z]+/)?([^/]+)", home_mounts[0])
        if m:
            return m.group(1), True
    if occ["user"] not in ("root", "(unknown)") and not occ["user"].isdigit():
        return occ["user"], False
    return "(could not determine -- root process, no container home mount)", True


def format_who(host_results: List[Dict], ours_patterns: List[str]) -> str:
    """One line per GPU: who occupies it (login user, container, pid, elapsed), or free."""
    lines: List[str] = []
    for hr in host_results:
        lines.append(hr["host"])
        if hr["status"] != "ok":
            lines.append(f"  {hr['status']}: {hr['message']}")
            continue
        data = hr["data"]
        summaries = [summarize_gpu(g, data["pids"], data["containers"], ours_patterns) for g in data["gpus"]]
        for s in sorted(summaries, key=lambda s: (s["kfd_index"] is None, s["kfd_index"], s["gpu_id"])):
            who = []
            for o in s["occupants"]:
                owner, _ = _infer_owner_contact(o, data["containers"])
                where = f"container {o['container']}, " if o["container"] else ""
                age = f", {o['elapsed_s']:.0f}s" if o["elapsed_s"] is not None else ""
                unreadable = " (KFD queues not readable: may occupy this GPU)" if o["queues_unreadable"] else ""
                who.append(f"{owner}{' (ours)' if o['ours'] else ''} [{where}pid {o['pid']}{age}]{unreadable} {o['cmd'][:100]}")
            index = s["kfd_index"] if s["kfd_index"] is not None else "?"
            lines.append(f"  GPU {index} (gpu_id {s['gpu_id']}): {'; '.join(who) if who else 'free'}")
    return "\n".join(lines)


def format_markdown(host_results: List[Dict], ours_patterns: List[str], history_path: Optional[str]) -> str:
    lines: List[str] = []
    for hr in host_results:
        host = hr["host"]
        lines.append(f"## {host}")
        if hr["status"] != "ok":
            lines.append(f"**{hr['status']}**: {hr['message']}")
            lines.append("")
            continue
        data = hr["data"]
        if data.get("errors"):
            for e in data["errors"]:
                lines.append(f"> note: {e}")
        gpus = data["gpus"]
        if not gpus:
            lines.append("No GPUs/rocm-smi found on this host.")
            lines.append("")
            continue

        pids, containers = data["pids"], data["containers"]
        summaries = [summarize_gpu(g, pids, containers, ours_patterns) for g in gpus]

        lines.append("| GPU | Render | Util | VRAM | Duty(foreign) | Occupants (user/container, elapsed) |")
        lines.append("|-----|--------|------|------|---------------|--------------------------------------|")
        for s in summaries:
            last = s["last_sample"]
            util = f"{last.get('util_pct')}%" if last.get("util_pct") is not None else "-"
            if last.get("vram_used_bytes") and last.get("vram_total_bytes"):
                vram = f"{round(100*last['vram_used_bytes']/last['vram_total_bytes'])}%"
            else:
                vram = "-"
            occ_str = "-"
            if s["occupants"]:
                occ_str = "; ".join(
                    f"{_owner_label(o, containers)} "
                    f"({o['elapsed_s']:.0f}s)" if o["elapsed_s"] is not None else _owner_label(o, containers)
                    for o in s["occupants"][:4]
                )
            idx = s["rocm_index"]
            # KFD-only mode has no rocm-smi index: identify the GPU by its
            # KFD render node instead (renderDNNN), never "?".
            idx_s = (
                f"{idx}{'~' if s['rocm_index_assumed'] else ''}"
                if idx is not None
                else f"renderD{s['render_minor']}"
            )
            render = f"renderD{s['render_minor']}/{s['card']}" if s["card"] else f"renderD{s['render_minor']}"
            lines.append(
                f"| {idx_s} (gpu_id {s['gpu_id']}) | {render} | {util} | {vram} "
                f"| {s['foreign_duty_cycle']:.0%} | {occ_str} |"
            )
        lines.append("")

        lines.append("### Verdict")
        idle_gpus = [s for s in summaries if s["state"] == "free"]
        for s in summaries:
            idx = (
                s["rocm_index"]
                if s["rocm_index"] is not None
                else f"renderD{s['render_minor']} (gpu_id {s['gpu_id']})"
            )
            lines.append(f"**GPU {idx}** -- {s['state']}, foreign duty cycle {s['foreign_duty_cycle']:.0%}.")
            foreign_occ = [o for o in s["occupants"] if not o["ours"]]
            if not foreign_occ:
                lines.append("  No foreign occupant detected (free, or only our own processes).")
                continue
            lead = foreign_occ[0]
            owner, inferred = _infer_owner_contact(lead, containers)
            tag = "inferred" if inferred else "confirmed"
            evidence = containers.get(lead["docker_id"], {}).get("owner_evidence") or lead.get("owner_evidence")
            lines.append(
                f"  - Real owner ({tag}): **{owner}**" + (f" (evidence: {evidence})" if evidence else "") + f", host `{host}`"
                + (f", container `{lead['container']}`" if lead["container"] else "")
                + f". Command: `{lead['cmd'][:120]}`"
            )
            if lead["lock_files"]:
                lines.append(f"  - Lock file(s) held: {', '.join(lead['lock_files'])}")
            if lead["notes"]:
                lines.append(f"  - Could not determine: {'; '.join(lead['notes'])}")
            elapsed = f"{lead['elapsed_s']:.0f}s" if lead["elapsed_s"] is not None else "unknown"
            cont_info = ""
            if history_path:
                hist = read_history(history_path)
                run = continuous_run(hist, host, s["gpu_id"])
                if run:
                    cont_info = f", continuous foreign-use run so far (history): {run['duration_s']:.0f}s over {run['sample_count']} recorded checks"
            lines.append(f"  - Options, ranked (advice only -- never kill or signal their process):")
            msg_template = (
                f"    1. Coordinate: message them -- \"Hi, I need GPU {idx} on {host} for a timing run; "
                f"you've been running there for ~{elapsed}{cont_info}. Can we coordinate a window, "
                f"or do you have a few minutes free soon?\""
            )
            lines.append(msg_template)
            if lead["lock_files"]:
                lines.append(f"    2. Join their lock before running: flock on {lead['lock_files'][0]}.")
            if idle_gpus:
                other_idx = [
                    str(o["rocm_index"]) if o["rocm_index"] is not None else f"renderD{o['render_minor']}"
                    for o in idle_gpus
                ]
                lines.append(f"    3. Use a free GPU on this host instead: {', '.join(other_idx)}.")
            if history_path and cont_info:
                lines.append("    4. Wait-window estimate: see continuous-run duration above; re-run with --history to refine.")
            else:
                lines.append("    4. Wait-window estimate: no --history yet -- pass the same --history file on repeated runs to build a duty-cycle estimate.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_json(host_results: List[Dict], ours_patterns: List[str]) -> str:
    out = []
    for hr in host_results:
        if hr["status"] != "ok":
            out.append({"host": hr["host"], "status": hr["status"], "message": hr.get("message")})
            continue
        data = hr["data"]
        pids, containers = data["pids"], data["containers"]
        summaries = [summarize_gpu(g, pids, containers, ours_patterns) for g in data["gpus"]]
        out.append(
            {
                "host": hr["host"],
                "status": "ok",
                "collected_at": data.get("collected_at"),
                "rocm_smi_path": data.get("rocm_smi_path"),
                "errors": data.get("errors", []),
                "gpus": summaries,
                "raw_pids": pids,
                "raw_containers": containers,
                "slurm_jobs": data.get("slurm_jobs", {}),
            }
        )
    return json.dumps(out, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _split_hosts(values: List[str]) -> List[str]:
    hosts: List[str] = []
    for v in values:
        hosts.extend(h.strip() for h in v.split(",") if h.strip())
    return hosts


def main() -> None:
    ap = argparse.ArgumentParser(description="GPU usage + real-owner report, local or over SSH")
    ap.add_argument("--host", action="append", default=[], help="SSH host; repeatable or comma-separated")
    ap.add_argument("--format", choices=["who", "markdown", "json"], default="who",
                    help="who (default): one line per GPU with its occupants' login users; markdown: full report")
    ap.add_argument("--samples", type=int, default=5, help="samples per host in the burst (default 5)")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between samples (default 1.0)")
    ap.add_argument("--deadline", type=float, default=30.0, help="hard per-host deadline in seconds")
    ap.add_argument("--ours", action="append", default=[], help="container name or pid regex to label 'ours'; repeatable")
    ap.add_argument("--history", default=None, help="append-only history file; accumulates first/last-seen per (host,gpu,owner)")
    ap.add_argument(
        "--rocm-smi",
        action="store_true",
        help="opt in to rocm-smi for util/clock/power/temp. Default is KFD/sysfs-only "
        "on every --host (no rocm-smi or amd-smi invocation at all -- they have been "
        "observed to wedge some hosts); local-only runs may still use rocm-smi by default.",
    )
    args = ap.parse_args()

    hosts: List[Optional[str]] = _split_hosts(args.host) if args.host else [None]
    results = collect_all(hosts, args.samples, args.interval, args.deadline, args.rocm_smi)

    if args.history:
        for hr in results:
            if hr["status"] != "ok":
                continue
            data = hr["data"]
            summaries = [
                summarize_gpu(g, data["pids"], data["containers"], args.ours) for g in data["gpus"]
            ]
            for s in summaries:
                foreign_occ = [o for o in s["occupants"] if not o["ours"]]
                owner, _ = _infer_owner_contact(foreign_occ[0], data["containers"]) if foreign_occ else ("(idle/ours)", False)
                append_history(args.history, hr["host"], s["gpu_id"], owner, bool(foreign_occ))

    if args.format == "json":
        print(format_json(results, args.ours))
    elif args.format == "who":
        print(format_who(results, args.ours))
    else:
        print(format_markdown(results, args.ours, args.history))


if __name__ == "__main__":
    main()
