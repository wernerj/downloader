"""The download queue: states, parallel limit, pause/resume."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit

from . import wget
from .naming import distinctive_name
from .store import DONE, DOWNLOADING, FAILED, PAUSED, QUEUED, Download, Store

ALLOWED_SCHEMES = {"http", "https", "ftp"}
KILL_AFTER = 3.0  # seconds to wait after SIGTERM before SIGKILL


class Manager:
    def __init__(self, dest_dir: Path | str, store: Store, max_parallel: int = 3):
        self.dest_dir = Path(dest_dir).expanduser().resolve()
        self.store = store
        self.max_parallel = max(1, max_parallel)
        self.items: list[Download] = store.load()
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._runs: dict[str, int] = {}
        self._samples: dict[str, tuple[float, int]] = {}
        for item in self.items:
            self._measure(item)

    # ---- actions -------------------------------------------------------

    def add(self, url: str) -> Download:
        url = url.strip()
        parts = urlsplit(url)
        if parts.scheme.lower() not in ALLOWED_SCHEMES or not parts.netloc:
            raise ValueError("Not a valid http(s) or ftp URL")
        if any(item.url == url for item in self.items):
            raise ValueError("This URL is already in the queue")
        item = Download(
            id=hashlib.sha1(url.encode()).hexdigest()[:12],
            url=url,
            dest=str(self.dest_dir / distinctive_name(url)),
        )
        self.items.append(item)
        self._changed()
        return item

    def pause(self, item: Download) -> None:
        if item.state not in (DOWNLOADING, QUEUED):
            return
        item.state = PAUSED
        item.speed = 0.0
        self._stop(item)
        self._changed()

    def resume(self, item: Download) -> None:
        """Put a paused or failed download back in line."""
        if item.state not in (PAUSED, FAILED):
            return
        item.state = QUEUED
        item.error = ""
        self._changed()

    def toggle(self, item: Download) -> None:
        if item.state in (DOWNLOADING, QUEUED):
            self.pause(item)
        else:
            self.resume(item)

    def remove(self, item: Download) -> None:
        """Drop from the queue. The file on disk is left alone."""
        if item not in self.items:
            return
        item.state = PAUSED
        self._stop(item)
        self.items.remove(item)
        self._changed()

    def reorder(self, items: list[Download], step: int) -> bool:
        """Move items one place up (step=-1) or down (step=1). True if anything moved.

        Waiting downloads start in list order, so this also changes what runs next.
        """
        chosen = {item.id for item in items}
        order = range(len(self.items)) if step < 0 else range(len(self.items) - 1, -1, -1)
        moved = False
        for i in order:
            j = i + step
            if self.items[i].id in chosen and 0 <= j < len(self.items) and self.items[j].id not in chosen:
                self.items[i], self.items[j] = self.items[j], self.items[i]
                moved = True
        if moved:
            self._changed()
        return moved

    def set_max_parallel(self, count: int) -> None:
        """Change the parallel limit. Running downloads are kept; a lower limit only stops new starts."""
        self.max_parallel = max(1, count)
        self._schedule()

    def folders(self) -> list[str]:
        """Names of existing sub-folders of dest_dir (candidates for move_done)."""
        try:
            return sorted((e.name for e in os.scandir(self.dest_dir)
                           if e.is_dir() and not e.name.startswith(".")), key=str.lower)
        except OSError:
            return []

    def move_done(self, items: list[Download], folder: str) -> tuple[int, list[str]]:
        """Move finished files into dest_dir/<folder>. Returns (moved count, problems)."""
        folder = folder.strip()
        if not folder or folder in (".", "..") or any(c in folder for c in "/\\\0"):
            raise ValueError("Folder name must be a single name, without slashes")
        target = self.dest_dir / folder
        moved, problems = 0, []
        for item in items:
            new = target / item.name
            if item.state != DONE:
                problems.append(f"{item.name}: not finished")
            elif not os.path.isfile(item.dest):
                problems.append(f"{item.name}: file not found")
            elif new.exists():
                problems.append(f"{item.name}: already exists in {folder}")
            else:
                try:
                    target.mkdir(exist_ok=True)
                    shutil.move(item.dest, new)
                except OSError as exc:
                    problems.append(f"{item.name}: {exc.strerror or exc}")
                    continue
                item.dest = str(new)
                moved += 1
        if moved:
            self.store.save(self.items)
        return moved, problems

    def tick(self) -> None:
        """Refresh sizes and speeds from the files on disk."""
        now = time.monotonic()
        for item in self.items:
            if item.state != DOWNLOADING:
                continue
            self._measure(item)
            last = self._samples.get(item.id)
            if last and now > last[0]:
                current = max(0.0, (item.downloaded - last[1]) / (now - last[0]))
                item.speed = current if not item.speed else 0.6 * item.speed + 0.4 * current
            self._samples[item.id] = (now, item.downloaded)

    async def shutdown(self) -> None:
        """Stop all running downloads; they come back as paused next time."""
        for item in self.items:
            if item.state == DOWNLOADING:
                item.state = PAUSED
                item.speed = 0.0
                self._stop(item)
        tasks = [t for t in self._tasks.values() if not t.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for item in self.items:
            self._measure(item)
        self.store.save(self.items)

    # ---- internals -----------------------------------------------------

    def _changed(self) -> None:
        self._schedule()
        self.store.save(self.items)

    def _schedule(self) -> None:
        running = sum(1 for item in self.items if item.state == DOWNLOADING)
        for item in self.items:
            if running >= self.max_parallel:
                break
            if item.state == QUEUED:
                item.state = DOWNLOADING
                running += 1
                run = self._runs.get(item.id, 0) + 1
                self._runs[item.id] = run
                previous = self._tasks.get(item.id)
                self._tasks[item.id] = asyncio.create_task(self._run(item, run, previous))

    def _current(self, item: Download, run: int) -> bool:
        return self._runs.get(item.id) == run and item.state == DOWNLOADING and item in self.items

    async def _run(self, item: Download, run: int, previous: asyncio.Task | None) -> None:
        # A just-paused wget may still be shutting down; never have two
        # processes writing to the same file.
        if previous and not previous.done():
            await asyncio.gather(previous, return_exceptions=True)
        if not self._current(item, run):
            return
        lines: list[str] = []
        try:
            os.makedirs(os.path.dirname(item.dest), exist_ok=True)
            self._samples.pop(item.id, None)
            proc = await wget.start(item.url, item.dest)
        except OSError as exc:
            self._finish(item, run, 1, [str(exc)])
            return
        self._procs[item.id] = proc
        if not self._current(item, run):  # paused while wget was starting
            self._terminate(proc)
        try:
            assert proc.stderr is not None
            async for raw in proc.stderr:
                line = raw.decode(errors="replace").rstrip()
                length = wget.parse_length(line)
                if length is not None:
                    item.total = length
                lines.append(line)
                del lines[:-40]
            code = await proc.wait()
        finally:
            if self._procs.get(item.id) is proc:
                del self._procs[item.id]
        self._finish(item, run, code, lines)

    def _finish(self, item: Download, run: int, code: int, lines: list[str]) -> None:
        self._measure(item)
        if not self._current(item, run):
            return  # paused or removed meanwhile; that action already set the state
        item.speed = 0.0
        if code == 0:
            item.state = DONE
            item.total = item.downloaded
        else:
            item.state = FAILED
            item.error = wget.error_text(lines)
            self._drop_empty(item)
        self._changed()

    def _stop(self, item: Download) -> None:
        proc = self._procs.get(item.id)
        if proc:
            self._terminate(proc)

    def _terminate(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        asyncio.get_running_loop().call_later(KILL_AFTER, self._kill, proc)

    @staticmethod
    def _kill(proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    @staticmethod
    def _measure(item: Download) -> None:
        try:
            item.downloaded = os.path.getsize(item.dest)
        except OSError:
            if item.state != DONE:
                item.downloaded = 0

    @staticmethod
    def _drop_empty(item: Download) -> None:
        # wget -O creates the file before it knows the request will fail.
        try:
            if os.path.getsize(item.dest) == 0:
                os.remove(item.dest)
        except OSError:
            pass
