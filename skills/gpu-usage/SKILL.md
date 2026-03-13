---
name: gpu-usage
description: >
  Report GPU usage on shared servers — shows which processes occupy each GPU,
  VRAM percentage, GPU utilization, process owner, elapsed time, and Docker
  container name. Use this skill when the user asks: "who's using the GPU",
  "check GPU usage", "is the GPU free", "can I profile", "GPU contention",
  "VRAM usage", "show GPU processes", "gpu-usage", or any question about
  GPU availability before profiling.
allowed-tools: Bash(python3 * gpu_usage.py *)
---

# GPU Usage Report

## Prerequisites
- `rocm-smi` installed and on PATH
- Python 3.8+

## Workflow

Run the script:

```
python3 <skill-dir>/scripts/gpu_usage.py --format markdown
```

Present the output directly — it's a ready-to-display markdown table.

If all GPUs are idle, the script prints "All GPUs are idle."

Use `--format json` if structured data is needed downstream.
