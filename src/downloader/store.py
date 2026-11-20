"""Save the queue to a JSON file and load it back."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

QUEUED, DOWNLOADING, PAUSED, DONE, FAILED = "queued", "downloading", "paused", "done", "failed"
STATES = {QUEUED, DOWNLOADING, PAUSED, DONE, FAILED}


@dataclass
class Download:
    id: str
    url: str
    dest: str
    state: str = QUEUED
    total: int | None = None
    downloaded: int = 0
    error: str = ""
    tool: str = "wget"  # "wget" or "yt-dlp"
    speed: float = 0.0  # bytes per second, not saved

    @property
    def name(self) -> str:
        return os.path.basename(self.dest)


def default_path() -> Path:
    return Path.home() / ".downloader" / "queue.json"


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_path()

    def load(self) -> list[Download]:
        try:
            raw = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        items = []
        for entry in raw.get("downloads", []):
            try:
                item = Download(
                    id=str(entry["id"]),
                    url=str(entry["url"]),
                    dest=str(entry["dest"]),
                    state=entry.get("state", PAUSED),
                    total=entry.get("total"),
                    downloaded=int(entry.get("downloaded", 0)),
                    error=str(entry.get("error", "")),
                    tool=str(entry.get("tool", "wget")),
                )
            except (KeyError, TypeError, ValueError):
                continue
            # Nothing starts on its own after a restart.
            if item.state in (DOWNLOADING, QUEUED) or item.state not in STATES:
                item.state = PAUSED
            items.append(item)
        return items

    def save(self, items: list[Download]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for item in items:
            entry = asdict(item)
            del entry["speed"]
            data.append(entry)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"downloads": data}, indent=2))
        os.replace(tmp, self.path)  # atomic: never leaves a half-written file
