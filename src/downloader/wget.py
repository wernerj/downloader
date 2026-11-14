"""Start wget processes and read what they report."""

from __future__ import annotations

import asyncio
import os
import re
import shutil

_LENGTH = re.compile(r"^Length: (\d+)")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")
_NOISE = re.compile(r"^(--\d{4}-|Connecting to|Resolving|HTTP request sent|Saving to|Length:|\s*\d+[KMG] )")


def wget_path() -> str | None:
    return shutil.which("wget")


def build_command(url: str, dest: str) -> list[str]:
    # "--" ends the options, so a URL can never be read as a wget option.
    return ["wget", "-c", "--progress=dot:mega", "-O", dest, "--", url]


def parse_length(line: str) -> int | None:
    """Total file size from wget's 'Length: 400000 (391K) ...' line."""
    match = _LENGTH.match(line)
    return int(match.group(1)) if match else None


def error_text(lines: list[str]) -> str:
    """Pick the most useful line of wget's output to show as the error."""
    for line in reversed(lines):
        line = line.strip()
        if line and not _NOISE.match(line):
            return _TIMESTAMP.sub("", line)
    return "wget failed"


def is_ssl_failure(lines: list[str]) -> bool:
    return any("Unable to establish SSL connection" in line for line in lines)


async def start(url: str, dest: str) -> asyncio.subprocess.Process:
    # LC_ALL=C: wget translates its messages; we parse the English ones.
    env = dict(os.environ, LC_ALL="C")
    return await asyncio.create_subprocess_exec(
        *build_command(url, dest),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
