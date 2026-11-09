#!/usr/bin/env python3
"""Generic fake CLI used as `gh`, `herdr` and `herdr-message` in tests.

Invoked through a symlink; the symlink name is the tool name.

- $FAKE_RESPONSES: JSON list of {"match": [argv prefix...], "stdout": str,
  "stderr": optional str, "exit": int, "tool": optional tool name}. First entry whose "tool" (when
  present) equals the invoked name and whose "match" is a prefix of argv wins.
  No match: print `{}` and exit 0.
- $FAKE_CALLS: file; each call appends one JSON line {"tool": ..., "argv": [...]}.
  When argv contains `--input -`, stdin is read and logged as "stdin".
"""
import json
import os
import sys


def main() -> int:
    tool = os.path.basename(sys.argv[0])
    argv = sys.argv[1:]
    calls = os.environ.get("FAKE_CALLS")
    if calls:
        entry = {"tool": tool, "argv": argv}
        if "--input" in argv and argv[argv.index("--input") + 1:][:1] == ["-"]:
            entry["stdin"] = sys.stdin.read()
        with open(calls, "a") as f:
            f.write(json.dumps(entry) + "\n")
    for entry in json.loads(os.environ.get("FAKE_RESPONSES", "[]")):
        if entry.get("tool", tool) != tool:
            continue
        prefix = entry.get("match", [])
        if argv[: len(prefix)] == prefix:
            sys.stdout.write(entry.get("stdout", ""))
            sys.stderr.write(entry.get("stderr", ""))
            return entry.get("exit", 0)
    sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
