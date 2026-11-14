"""Command line entry point: downloader [-d DIR] [-j N] [URL ...]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import wget
from .app import DownloaderApp
from .manager import Manager
from .store import Store


def main() -> None:
    parser = argparse.ArgumentParser(prog="downloader", description="TUI download queue that wraps wget.")
    parser.add_argument("urls", nargs="*", metavar="URL", help="URLs to queue right away")
    parser.add_argument("-d", "--dir", default=".", help="folder to save into (default: current folder)")
    parser.add_argument("-j", "--jobs", type=int, default=3, help="downloads running at once (default: 3)")
    parser.add_argument("--state", help="queue file (default: ~/.downloader/queue.json)")
    args = parser.parse_args()

    if not wget.wget_path():
        sys.exit("downloader: wget was not found on PATH. Install it first (e.g. brew install wget).")
    dest = Path(args.dir).expanduser()
    if dest.exists() and not dest.is_dir():
        sys.exit(f"downloader: {dest} is not a folder")

    manager = Manager(dest, Store(args.state), max_parallel=args.jobs)
    DownloaderApp(manager, args.urls).run()


if __name__ == "__main__":
    main()
