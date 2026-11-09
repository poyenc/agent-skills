"""Subprocess wrapper shared by every module."""
import json
import subprocess
from typing import Any


class CommandError(Exception):
    def __init__(self, argv: list[str], returncode: int, stderr: str):
        super().__init__(f"{' '.join(argv)} exited {returncode}: {stderr.strip()}")
        self.argv = argv
        self.returncode = returncode
        self.stderr = stderr


def run(argv: list[str], check: bool = True, input: str | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, capture_output=True, text=True, input=input)
    if check and result.returncode != 0:
        raise CommandError(argv, result.returncode, result.stderr)
    return result


def gh_json(*args: str) -> Any:
    return json.loads(run(["gh", *args]).stdout)


def herdr_json(*args: str) -> dict:
    return json.loads(run(["herdr", *args]).stdout)
