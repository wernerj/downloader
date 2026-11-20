"""Start yt-dlp processes (video sites, and the fallback when wget fails)."""

from __future__ import annotations

import asyncio
import glob
import os
import shutil
from urllib.parse import urlsplit

TOOL = "yt-dlp"
FILE_PREFIX = "DL-FILE:"  # printed when the output file name is known
DONE_PREFIX = "DL-DONE:"  # printed when the final file is in place

# Sites wget cannot handle: the URL is a web page, not a file.
VIDEO_DOMAINS = (
    "youtube.com", "youtu.be", "facebook.com", "fb.watch", "xvideos.com",
    "xhamster.com", "xnxx.com", "pornhub.com", "redtube.com", "youporn.com",
    "spankbang.com", "vimeo.com", "dailymotion.com", "twitch.tv",
    "tiktok.com", "instagram.com", "twitter.com", "x.com",
)


def ytdlp_path() -> str | None:
    return shutil.which("yt-dlp")


def is_video_site(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in VIDEO_DOMAINS)


def build_command(url: str, dest_dir: str) -> list[str]:
    return [
        "yt-dlp",
        "--no-playlist",  # one URL, one file
        "--no-update", "--no-progress", "--newline",
        "--restrict-filenames",
        "--no-simulate",  # --print would otherwise skip the download
        "-P", dest_dir,
        "-o", "%(title).80B-%(id)s.%(ext)s",
        "--print", f"before_dl:{FILE_PREFIX}%(filename)s",
        "--print", f"after_move:{DONE_PREFIX}%(filepath)s",
        "--", url,
    ]


def parse_path(line: str) -> str | None:
    """File path from a 'DL-FILE:' or 'DL-DONE:' line."""
    for prefix in (FILE_PREFIX, DONE_PREFIX):
        if line.startswith(prefix):
            return line[len(prefix):].strip() or None
    return None


def error_text(lines: list[str]) -> str:
    for line in reversed(lines):
        if line.startswith("ERROR:"):
            return "yt-dlp: " + line[len("ERROR:"):].strip()
    return "yt-dlp failed"


def placeholder_name(url: str, item_id: str) -> str:
    """Name shown until yt-dlp reports the real one."""
    host = (urlsplit(url).hostname or "video").removeprefix("www.")
    return f"{host.replace('.', '_')}-{item_id}"  # no dot: it must not look like an extension


def size_on_disk(dest: str) -> int:
    """Bytes of the file plus its .part and per-format pieces (video/audio are fetched separately)."""
    stem = os.path.splitext(dest)[0]
    total = 0
    for path in glob.glob(glob.escape(stem) + ".*"):
        try:
            total += os.path.getsize(path)
        except OSError:
            pass
    return total


async def start(url: str, dest_dir: str) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *build_command(url, dest_dir),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,  # one stream: file names and errors
    )
