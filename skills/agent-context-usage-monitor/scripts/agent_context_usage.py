#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Report the context-window usage of live herdr agents against their rotation thresholds (read-only).

For each agent it reads the visible pane text with `herdr agent read` and parses the status line
that Claude Code and pi print at the bottom of the pane, for example
`Sonnet 5.5 xhigh 22.0%/1M . CH99.5%/92%` (context used / context window) and a `215376 tokens`
counter. The rotation thresholds are the ones in the project skill agent-rotation-discipline:
Claude models 55%, gpt tier terra 45%, gpt tier sol 25% (any version: gpt-5.6-sol, gpt-6.1-sol, ...). Nothing is sent to any agent and nothing
is rotated; rotating is the lead's job through the herdr-kit:rotate skill.

Usage:
  agent_context_usage.py                       # every live agent whose name starts with sched-
  agent_context_usage.py --prefix ''           # every named live agent
  agent_context_usage.py --names a,b           # only these agents (name or pane id)
  agent_context_usage.py --json                # machine-readable output
  agent_context_usage.py --rotate-only         # print only agents due for rotation (for cron)
  agent_context_usage.py --threshold NAME=55   # per-agent threshold (name or pane id), repeatable;
                                               # for a model the table below does not know

Exit status: 0 normally; 2 when at least one scanned agent is at or above its threshold
(so a caller can branch on it); 1 if herdr itself fails.
"""

import argparse
import json
import re
import subprocess
import sys

# All patterns and name comparisons ignore case: the status lines print "1M" but "272k", and model ids come as
# "Sonnet 5.5", "Claude-Sonnet-5.5" or "claude-sonnet-5-5" depending on the provider.
# "22.0%/1M" or "46.2%/272k": context used over window size. The cache-hit field "CH99.5%/92%" has no K/M
# suffix after the slash, so it does not match.
CONTEXT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)%/(\d+(?:\.\d+)?)([KM])\b", re.IGNORECASE)
TOKENS_RE = re.compile(r"(\d[\d,]*)\s+tokens\b", re.IGNORECASE)
# Claude Code prints "Sonnet 5.5 xhigh 33.0%/1M ..." (model, effort, then the context figure).
CLAUDE_MODEL_RE = re.compile(r"((?:Sonnet|Opus|Haiku|Fable)[\w .\-]*?)\s+\d+(?:\.\d+)?%/\d+(?:\.\d+)?[KM]\b", re.IGNORECASE)
# pi prints "(provider) gpt-5.6-sol <bullet> medium 30.0%/1M" (U+2022); a model without reasoning has no bullet
# and no effort word: "(provider) gpt-5.6-sol 30.0%/1M". Anchoring on the bullet or the context figure avoids
# matching a model name that merely appears in the conversation text.
_AFTER_PI_MODEL = r"\s*(?:\u2022|\d+(?:\.\d+)?%/)"
GPT_MODEL_RE = re.compile(r"\b(gpt-[\w.]+-[A-Za-z]+)" + _AFTER_PI_MODEL, re.IGNORECASE)
# pi prints the Claude model id as configured: "(provider) Claude-Sonnet-5.5 <bullet> medium 33.0%/1M" (gateway) or
# "claude-sonnet-5-5 ..." (direct).
PI_CLAUDE_MODEL_RE = re.compile(r"\b(claude-(?:sonnet|opus|haiku|fable)[\w.\-]*)" + _AFTER_PI_MODEL, re.IGNORECASE)
# Any other pi model, for example "(amd-gateway) DeepSeek-V4.1-Flash <bullet> high 53.5%/1.0M": the id after the
# "(provider)" tag. It has no threshold of its own (see threshold_for); --threshold NAME=PERCENT supplies one.
# The id must be followed by whitespace, so the "(auto) CH99.8%/98%" cache-hit field after the context figure is not
# read as a model.
PI_ANY_MODEL_RE = re.compile(r"\([\w.\-]+\)\s+([\w.\-/]+)\s+(?:•|\d+(?:\.\d+)?%/)", re.IGNORECASE)

# Percent of the context window at which the lead rotates (skill agent-rotation-discipline, rule 1).
# The gpt tier is the last word of the model name; the version before it does not change the threshold. A tier not
# listed here stays unknown (no threshold is guessed).
GPT_TIER_THRESHOLDS = {"sol": 25.0, "terra": 45.0}
CLAUDE_THRESHOLD = 55.0
CLAUDE_PREFIXES = ("sonnet", "opus", "haiku", "fable", "claude-")


def run_herdr(args: list[str]) -> str:
    out = subprocess.run(["herdr", *args], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)} failed: {out.stderr.strip()[:200]}")
    return out.stdout


def list_agents(names: set[str] | None, prefix: str) -> list[dict]:
    agents = json.loads(run_herdr(["agent", "list"]))["result"]["agents"]
    picked = []
    for agent in agents:
        label = agent.get("name")
        if names is not None:
            if label in names or agent["pane_id"] in names:
                picked.append(agent)
        elif label and label.startswith(prefix):
            picked.append(agent)
    return picked


def threshold_for(model: str | None) -> float | None:
    if not model:
        return None
    gpt = re.fullmatch(r"gpt-[\w.]+-([A-Za-z]+)", model, re.IGNORECASE)
    if gpt:
        return GPT_TIER_THRESHOLDS.get(gpt.group(1).lower())
    if model.lower().startswith(CLAUDE_PREFIXES):
        return CLAUDE_THRESHOLD
    return None


def parse_pane(text: str) -> dict:
    info = {"context_percent": None, "window": None, "tokens": None, "model": None}
    matches = CONTEXT_RE.findall(text)
    if matches:
        percent, size, unit = matches[-1]  # the status line is at the bottom: take the last
        info["context_percent"] = float(percent)
        info["window"] = f"{size}{unit}"
    tokens = TOKENS_RE.findall(text)
    if tokens:
        info["tokens"] = int(tokens[-1].replace(",", ""))
    claude = PI_CLAUDE_MODEL_RE.findall(text) or CLAUDE_MODEL_RE.findall(text)
    gpt = GPT_MODEL_RE.findall(text)
    other = PI_ANY_MODEL_RE.findall(text)
    if claude:
        info["model"] = claude[-1].strip()
    elif gpt:
        info["model"] = gpt[-1]
    elif other:
        info["model"] = other[-1]
    return info


def collect(agent: dict, overrides: dict[str, float]) -> dict:
    target = agent.get("name") or agent["pane_id"]
    row = {
        "agent": target,
        "pane": agent["pane_id"],
        "kind": agent.get("agent"),
        "state": agent.get("agent_status"),
    }
    try:
        text = run_herdr(["agent", "read", target, "--source", "visible", "--lines", "20"])
        row.update(parse_pane(text))
    except Exception as exc:  # an unreadable pane must not hide the other agents
        row.update({"context_percent": None, "window": None, "tokens": None, "model": None})
        row["error"] = str(exc)
    # A --threshold override (by agent name or pane id) wins over the threshold of the model.
    override = overrides.get(str(row["agent"]).lower(), overrides.get(str(row["pane"]).lower()))
    row["threshold"] = override if override is not None else threshold_for(row["model"])
    if row["context_percent"] is None or row["threshold"] is None:
        row["level"] = "unknown"
    else:
        row["level"] = "ROTATE" if row["context_percent"] >= row["threshold"] else "ok"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--names", help="comma-separated agent names or pane ids (overrides --prefix)")
    parser.add_argument("--prefix", default="sched-", help="agent name prefix to scan (default sched-)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    parser.add_argument(
        "--rotate-only",
        action="store_true",
        help="print one line per agent at ROTATE (name, state, usage); nothing when none is due.\n"
        "An agent whose status line cannot be parsed prints as UNKNOWN: look at its pane.",
    )
    parser.add_argument(
        "--threshold",
        action="append",
        default=[],
        metavar="NAME=PERCENT",
        help="rotation threshold for one agent (name or pane id), overriding the threshold of its model; repeatable,\n"
        "for example --threshold NAME=55",
    )
    args = parser.parse_args()

    overrides: dict[str, float] = {}
    for item in args.threshold:
        key, sep, value = item.rpartition("=")
        try:
            percent = float(value)
        except ValueError:
            percent = -1.0
        if not sep or not key.strip() or not 0 < percent <= 100:
            parser.error(f"--threshold expects NAME=PERCENT with 0 < PERCENT <= 100, got {item!r}")
        overrides[key.strip().lower()] = percent

    names = {n.strip() for n in args.names.split(",") if n.strip()} if args.names else None
    rows = [collect(a, overrides) for a in list_agents(names, args.prefix)]
    rows.sort(key=lambda r: -(r["context_percent"] if r["context_percent"] is not None else -1))

    if args.rotate_only:
        for r in rows:
            if r["level"] == "ROTATE":
                print(f"ROTATE {r['agent']} state={r['state']} {r['context_percent']:.1f}%/{r['threshold']:.0f}%")
            elif r["level"] == "unknown":
                model = r.get("model") or "unknown"
                if r["context_percent"] is not None:
                    print(f"UNKNOWN {r['agent']} state={r['state']} model={model} context={r['context_percent']:.1f}%/{r['window']}")
                else:
                    print(f"UNKNOWN {r['agent']} state={r['state']} model={model} context=unknown")
    elif args.json:
        json.dump(rows, sys.stdout, indent=2)
        print()
    else:
        print(f"{'agent':<18}{'state':<9}{'context':>9}{'threshold':>11}{'tokens':>10}  {'level':<8}model")
        for r in rows:
            pct = f"{r['context_percent']:.1f}%" if r["context_percent"] is not None else "n/a"
            thr = f"{r['threshold']:.0f}%" if r["threshold"] is not None else "n/a"
            tok = str(r["tokens"]) if r["tokens"] is not None else "n/a"
            print(f"{r['agent']:<18}{(r['state'] or '?'):<9}{pct:>9}{thr:>11}{tok:>10}  {r['level']:<8}{r.get('model') or ''}")
    return 2 if any(r["level"] == "ROTATE" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
