import os
from pathlib import Path

from textual.widgets import DataTable, Input

from conftest import wait_for
from downloader.app import DownloaderApp, human_size, human_time
from downloader.manager import Manager
from downloader.store import DONE, DOWNLOADING, PAUSED, Store


def test_formatting():
    assert human_size(512) == "512B"
    assert human_size(1536) == "1.5K"
    assert human_size(None) == "?"
    assert human_time(75) == "1m15s"


async def test_keys_drive_the_queue(server, tmp_path):
    manager = Manager(tmp_path / "dl", Store(tmp_path / "queue.json"), max_parallel=3)
    app = DownloaderApp(manager, [f"{server.base}/a/file.bin"])
    async with app.run_test(size=(120, 30)) as pilot:
        table = app.query_one(DataTable)
        assert table.row_count == 1

        # "a" opens the dialog; typing a URL and Enter adds it
        await pilot.press("a")
        assert isinstance(app.focused, Input)
        await pilot.press(*f"{server.base}/b/file.bin", "enter")
        assert table.row_count == 2
        first, second = manager.items
        assert first.name != second.name
        assert table.cursor_row == 1  # cursor jumps to the new row

        # arrows move the selection; "p" pauses the selected one
        await pilot.press("up")
        assert app.selected() is first
        await wait_for(lambda: os.path.exists(first.dest))
        await pilot.press("p")
        assert first.state == PAUSED and second.state == DOWNLOADING
        await pilot.press("space")
        assert first.state == DOWNLOADING

        # "d" asks first; "n" keeps, "y" removes
        await pilot.press("down", "d", "n")
        assert len(manager.items) == 2
        await pilot.press("d", "y")
        assert manager.items == [first] and table.row_count == 1

        await wait_for(lambda: first.state == DONE)
        assert Path(first.dest).read_bytes() == server.expected("/a/file.bin")
        await pilot.press("q")
    assert Store(tmp_path / "queue.json").load()[0].state == DONE
