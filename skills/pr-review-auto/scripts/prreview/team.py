"""Team panes: start the reviewer and architect agents in herdr panes next to the caller,
close them, message any herdr agent, render prompt templates.

`spawn` splits the caller's own pane (`$HERDR_PANE_ID`): the reviewer to the right, the
architect below it. Agent names are `prr-<pr>-rev` and `prr-<pr>-arch`.
"""
import os
import re
import sys
from pathlib import Path

from . import config, gitops, proc

AGENT_SUFFIX = {"reviewer": "rev", "architect": "arch"}
SPLIT_DIRECTION = {"reviewer": "right", "architect": "down"}
PLACEHOLDER_RE = re.compile(r"\{\{([^{}]*)\}\}")


def agent_name(pr: int, role: str) -> str:
    if role not in AGENT_SUFFIX:
        raise ValueError(f"no agent name for role {role!r}")
    return f"prr-{pr}-{AGENT_SUFFIX[role]}"


def system_prompt_file(cfg: dict, role: str) -> Path:
    return Path(cfg["persona_dir"]) / role / "system-prompt.md"


def harness_argv(role_cfg: dict, prompt_file: Path) -> list[str]:
    harness, model, effort = role_cfg["harness"], role_cfg["model"], role_cfg["effort"]
    argv = ["--system-prompt-file", str(prompt_file)]
    if harness == "claude":
        return argv + ["--model", model, "--effort", effort, "--dangerously-skip-permissions"]
    if harness == "pi":
        return argv + ["--model", f"{model}:{effort}"]
    raise ValueError(f"unsupported harness {harness!r}")


def start_agent(cfg: dict, role: str, pr: int, pane_id: str) -> str:
    name = agent_name(pr, role)
    role_cfg = cfg["team"][role]
    argv = harness_argv(role_cfg, system_prompt_file(cfg, role))
    proc.run(["herdr", "agent", "start", name, "--kind", role_cfg["harness"],
              "--pane", pane_id, "--timeout", "120000", "--", *argv])
    return name


def render(template_path: Path, values: dict[str, str]) -> str:
    text = Path(template_path).read_text()
    missing = sorted({k for k in PLACEHOLDER_RE.findall(text) if k not in values})
    if missing:
        raise ValueError(f"{template_path}: unreplaced placeholders: {', '.join(missing)}")
    return PLACEHOLDER_RE.sub(lambda m: values[m[1]], text)


def _spawn(args) -> int:
    cfg = config.load(args.repo)
    caller = os.environ.get("HERDR_PANE_ID")
    if not caller:
        print("pr-review-auto spawn: HERDR_PANE_ID is not set; run it from a pane inside herdr", file=sys.stderr)
        return 1
    pane = proc.herdr_json("pane", "split", "--pane", caller, "--direction", SPLIT_DIRECTION[args.role],
                           "--cwd", os.getcwd(), "--no-focus")["result"]["pane"]["pane_id"]
    print(start_agent(cfg, args.role, args.pr, pane))
    return 0


def _member_close(args) -> int:
    pane = proc.herdr_json("agent", "get", args.agent)["result"]["agent"]["pane_id"]
    proc.run(["herdr", "pane", "close", pane])
    return 0


def _notify(args) -> int:
    if os.environ.get("HERDR_ENV") != "1":
        print("pr-review-auto notify: not inside a herdr session (HERDR_ENV is not 1); nothing was sent",
              file=sys.stderr)
        return 1
    proc.run(["herdr", "agent", "prompt", args.target, args.text])
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("spawn", help="start a reviewer or architect pane next to the caller")
    p.add_argument("repo")
    p.add_argument("pr", type=gitops.positive_int)
    p.add_argument("role", choices=tuple(AGENT_SUFFIX))
    p.set_defaults(func=_spawn)

    p = subparsers.add_parser("member-close", help="close a team member's pane")
    p.add_argument("agent")
    p.set_defaults(func=_member_close)

    p = subparsers.add_parser("notify", help="send a message to a herdr agent or pane (needs no config)")
    p.add_argument("target", help="agent name or pane ID")
    p.add_argument("text")
    p.set_defaults(func=_notify)
