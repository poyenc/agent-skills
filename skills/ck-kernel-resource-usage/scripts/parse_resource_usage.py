#!/usr/bin/env python3
"""Parse -Rpass-analysis=kernel-resource-usage remarks from a CK build log.

Produces:
  <log_stem>_report.md  — markdown report with spill/scratch summary
  <log_stem>_report.csv — machine-readable CSV of all kernels

Usage:
  python3 parse_resource_usage.py <build_log> [--target NAME] [--arch ARCH]

The compiler emits one block of remarks per kernel, each line tagged with
[-Rpass-analysis=kernel-resource-usage]. Lines may contain ANSI color codes.
A typical block looks like (after stripping ANSI):

  <file>:<line>:<col>: remark: Function Name: <mangled> [-Rpass-analysis=...]
  <file>:<line>:<col>: remark:     TotalSGPRs: 58 [-Rpass-analysis=...]
  <file>:<line>:<col>: remark:     VGPRs: 256 [-Rpass-analysis=...]
  <file>:<line>:<col>: remark:     AGPRs: 143 [-Rpass-analysis=...]
  <file>:<line>:<col>: remark:     ScratchSize [bytes/lane]: 0 [-Rpass-analysis=...]
  <file>:<line>:<col>: remark:     Dynamic Stack: False [-Rpass-analysis=...]
  <file>:<line>:<col>: remark:     Occupancy [waves/SIMD]: 1 [-Rpass-analysis=...]
  <file>:<line>:<col>: remark:     SGPRs Spill: 0 [-Rpass-analysis=...]
  <file>:<line>:<col>: remark:     VGPRs Spill: 0 [-Rpass-analysis=...]
  <file>:<line>:<col>: remark:     LDS Size [bytes/block]: 17408 [-Rpass-analysis=...]
"""

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Strip ANSI CSI escape sequences (colors, cursor movement, erase, etc.)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# Match a remark line with the resource-usage tag
REMARK_RE = re.compile(
    r"^(.+?:\d+:\d+):\s*remark:\s*(.*?)\s*\[-Rpass-analysis=kernel-resource-usage\]"
)


@dataclass
class KernelInfo:
    source: str
    kernel: str
    total_sgprs: int = 0
    vgprs: int = 0
    agprs: int = 0
    scratch_size: int = 0
    occupancy: int = 0
    sgpr_spill: int = 0
    vgpr_spill: int = 0
    lds_size: int = 0
    dynamic_stack: bool = False


# Map remark field labels (lowercase) to KernelInfo int attributes
FIELD_MAP = {
    "totalsgprs": "total_sgprs",
    "vgprs": "vgprs",
    "agprs": "agprs",
    "scratchsize [bytes/lane]": "scratch_size",
    "scratchsize": "scratch_size",
    "occupancy [waves/simd]": "occupancy",
    "occupancy": "occupancy",
    "sgprs spill": "sgpr_spill",
    "vgprs spill": "vgpr_spill",
    "lds size [bytes/block]": "lds_size",
    "lds size": "lds_size",
}

# Map remark field labels (lowercase) to KernelInfo bool attributes
BOOL_FIELD_MAP = {
    "dynamic stack": "dynamic_stack",
}

# Extract "Key: Value" where Value is an integer
KV_RE = re.compile(r"^\s*(.+?):\s*(\d+)\s*$")

# Extract "Key: Value" where Value is True/False
BOOL_KV_RE = re.compile(r"^\s*(.+?):\s*(True|False)\s*$")

# Extract "Function Name: <name>"
FUNC_RE = re.compile(r"^Function Name:\s*(.+)$")


def compute_effective_vgprs(k: KernelInfo, arch: str) -> int:
    """Compute effective VGPRs for occupancy based on architecture.

    CDNA3 (gfx94x): max(ArchVGPRs, AGPRs) — separate register files
    CDNA4 (gfx95x): ArchVGPRs + AGPRs — unified register file
    """
    if arch.startswith("gfx95"):  # CDNA4
        return k.vgprs + k.agprs
    # CDNA3 and earlier/unknown: max() rule
    return max(k.vgprs, k.agprs)


def batch_demangle(names: list[str]) -> dict[str, str]:
    """Demangle all kernel names in a single c++filt invocation."""
    import shutil
    import subprocess

    mangled = [n for n in names if n.startswith("_Z")]
    result: dict[str, str] = {}

    if mangled and shutil.which("c++filt"):
        try:
            r = subprocess.run(
                ["c++filt"],
                input="\n".join(mangled),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode == 0:
                demangled_lines = r.stdout.strip().splitlines()
                for orig, dem in zip(mangled, demangled_lines):
                    if len(dem) > 120:
                        dem = dem[:117] + "..."
                    result[orig] = dem
        except Exception:
            pass

    # Fill in any missing (non-mangled or failed demangling)
    for n in names:
        if n not in result:
            result[n] = n[:77] + "..." if len(n) > 80 else n

    return result


def parse_log(log_path: str) -> list[KernelInfo]:
    """Parse a build log and extract kernel resource usage entries."""
    path = Path(log_path)
    if not path.exists():
        print(f"Error: log file not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(errors="replace")
    kernels: list[KernelInfo] = []
    current: KernelInfo | None = None

    for raw_line in text.splitlines():
        # Strip ANSI escape codes
        line = ANSI_RE.sub("", raw_line)

        m = REMARK_RE.match(line)
        if not m:
            continue

        source = m.group(1)
        body = m.group(2).strip()

        # Check if this is a "Function Name:" line (starts a new block)
        fm = FUNC_RE.match(body)
        if fm:
            # Save previous kernel if any
            if current is not None:
                kernels.append(current)
            current = KernelInfo(source=source, kernel=fm.group(1).strip())
            continue

        # Otherwise it's a field line — parse "Key: Value"
        if current is None:
            continue

        # Try integer field
        kv = KV_RE.match(body)
        if kv:
            key = kv.group(1).strip().lower()
            value = int(kv.group(2))
            attr = FIELD_MAP.get(key)
            if attr:
                setattr(current, attr, value)
            continue

        # Try boolean field
        bkv = BOOL_KV_RE.match(body)
        if bkv:
            key = bkv.group(1).strip().lower()
            value = bkv.group(2) == "True"
            attr = BOOL_FIELD_MAP.get(key)
            if attr:
                setattr(current, attr, value)

    # Don't forget the last kernel
    if current is not None:
        kernels.append(current)

    return kernels


def has_spill(k: KernelInfo) -> bool:
    """Return True if this kernel has any spill or non-zero scratch."""
    return k.scratch_size > 0 or k.sgpr_spill > 0 or k.vgpr_spill > 0


def write_report(
    kernels: list[KernelInfo],
    output_path: str,
    target: str = "",
    arch: str = "",
) -> None:
    """Write a markdown report."""
    spill_kernels = [k for k in kernels if has_spill(k)]
    spill_kernels.sort(key=lambda k: (k.scratch_size, k.vgpr_spill), reverse=True)
    dynstack_kernels = [k for k in kernels if k.dynamic_stack]
    all_sorted = sorted(kernels, key=lambda k: (k.scratch_size, k.vgprs), reverse=True)

    # Batch demangle all kernel names
    all_names = [k.kernel for k in kernels]
    demangled = batch_demangle(all_names)

    with open(output_path, "w") as f:
        f.write("# Kernel Resource Usage Report\n\n")
        if target:
            f.write(f"**Target:** `{target}`\n")
        if arch:
            f.write(f"**GPU Architecture:** `{arch}`\n")
        f.write(f"**Date:** {date.today().isoformat()}\n")
        f.write(f"**Total kernels analyzed:** {len(kernels)}\n")
        f.write(f"**Kernels with spills (ScratchSize > 0 or Spill > 0):** {len(spill_kernels)}\n")
        if dynstack_kernels:
            f.write(f"**Kernels with Dynamic Stack:** {len(dynstack_kernels)}\n")
        f.write("\n")

        if dynstack_kernels:
            f.write("## WARNING: Kernels with Dynamic Stack\n\n")
            f.write(
                "These kernels use dynamic stack allocation (alloca on GPU), "
                "which causes unpredictable scratch memory usage.\n\n"
            )
            _write_table(f, dynstack_kernels, demangled, arch)
            f.write("\n")

        if spill_kernels:
            f.write("## Kernels with Register Spills\n\n")
            _write_table(f, spill_kernels, demangled, arch)
            f.write("\n")

        f.write("## Full Resource Usage Summary\n\n")
        _write_table(f, all_sorted, demangled, arch)
        f.write("\n")


def _write_table(
    f,
    kernels: list[KernelInfo],
    demangled: dict[str, str],
    arch: str = "",
) -> None:
    """Write a markdown table of kernel resource usage."""
    headers = [
        "Kernel",
        "VGPRs",
        "AGPRs",
        "EffVGPRs",
        "TotalSGPRs",
        "ScratchSize",
        "Occupancy",
        "SGPR Spill",
        "VGPR Spill",
        "LDS Size",
        "DynStack",
    ]
    f.write("| " + " | ".join(headers) + " |\n")
    f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")

    for k in kernels:
        kernel_display = demangled.get(k.kernel, k.kernel)
        kernel_display = kernel_display.replace("|", "\\|")
        eff = compute_effective_vgprs(k, arch)
        row = [
            kernel_display,
            str(k.vgprs),
            str(k.agprs),
            str(eff),
            str(k.total_sgprs),
            str(k.scratch_size),
            str(k.occupancy),
            str(k.sgpr_spill),
            str(k.vgpr_spill),
            str(k.lds_size),
            "YES" if k.dynamic_stack else "",
        ]
        f.write("| " + " | ".join(row) + " |\n")


def write_csv(kernels: list[KernelInfo], output_path: str, arch: str = "") -> None:
    """Write a CSV of all kernel resource usage."""
    csv_fields = [
        "source",
        "kernel",
        "vgprs",
        "agprs",
        "effective_vgprs",
        "total_sgprs",
        "scratch_size",
        "occupancy",
        "sgpr_spill",
        "vgpr_spill",
        "lds_size",
        "dynamic_stack",
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for k in kernels:
            row = {
                "source": k.source,
                "kernel": k.kernel,
                "vgprs": k.vgprs,
                "agprs": k.agprs,
                "effective_vgprs": compute_effective_vgprs(k, arch),
                "total_sgprs": k.total_sgprs,
                "scratch_size": k.scratch_size,
                "occupancy": k.occupancy,
                "sgpr_spill": k.sgpr_spill,
                "vgpr_spill": k.vgpr_spill,
                "lds_size": k.lds_size,
                "dynamic_stack": k.dynamic_stack,
            }
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description="Parse -Rpass-analysis=kernel-resource-usage from CK build logs"
    )
    parser.add_argument("log_file", help="Path to the build log file")
    parser.add_argument("--target", default="", help="CMake target name (for report header)")
    parser.add_argument("--arch", default="", help="GPU architecture (for report header)")
    args = parser.parse_args()

    log_path = Path(args.log_file)
    stem = log_path.stem
    out_dir = log_path.parent

    kernels = parse_log(args.log_file)

    if not kernels:
        print(f"No kernel-resource-usage remarks found in {args.log_file}", file=sys.stderr)
        print("Check that the target was built with -Rpass-analysis=kernel-resource-usage", file=sys.stderr)
        sys.exit(0)

    md_path = out_dir / f"{stem}_report.md"
    csv_path = out_dir / f"{stem}_report.csv"

    write_report(kernels, str(md_path), target=args.target, arch=args.arch)
    write_csv(kernels, str(csv_path), arch=args.arch)

    spill_count = sum(1 for k in kernels if has_spill(k))
    dynstack_count = sum(1 for k in kernels if k.dynamic_stack)
    print(f"Parsed {len(kernels)} kernels from {args.log_file}")
    print(f"  Kernels with spills/scratch: {spill_count}")
    if dynstack_count:
        print(f"  Kernels with dynamic stack: {dynstack_count}")
    print(f"  Report: {md_path}")
    print(f"  CSV:    {csv_path}")


if __name__ == "__main__":
    main()
