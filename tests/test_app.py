import os
from pathlib import Path

from textual.screen import ModalScreen
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

        # "D" removes immediately, no dialog
        await pilot.press("a")
        await pilot.press(*f"{server.base}/c/file.bin", "enter")
        assert table.row_count == 2
        await pilot.press("D")
        assert manager.items == [first] and table.row_count == 1
        assert not isinstance(app.screen, ModalScreen)

        await wait_for(lambda: first.state == DONE)
        assert Path(first.dest).read_bytes() == server.expected("/a/file.bin")
        await pilot.press("q")
    assert Store(tmp_path / "queue.json").load()[0].state == DONE


async def test_shift_arrows_select_several(server, tmp_path):
    manager = Manager(tmp_path / "dl", Store(tmp_path / "queue.json"), max_parallel=5)
    urls = [f"{server.base}/{n}/file.bin" for n in "abcd"]
    app = DownloaderApp(manager, urls)
    async with app.run_test(size=(120, 30)) as pilot:
        table = app.query_one(DataTable)
        await pilot.press("home")
        assert table.cursor_row == 0
        await pilot.press("shift+down", "shift+down")
        assert app.selection() == manager.items[0:3]
        assert "3 selected" in app.sub_title
        # extending back shrinks the range
        await pilot.press("shift+up")
        assert app.selection() == manager.items[0:2]
        await pilot.press("shift+down")

        # one key acts on all selected
        await pilot.press("p")
        assert [i.state for i in manager.items] == [PAUSED, PAUSED, PAUSED, DOWNLOADING]
        await pilot.press("space")
        assert [i.state for i in manager.items[:3]] == [DOWNLOADING] * 3

        # a plain arrow drops the selection; escape does too
        await pilot.press("down")
        assert app.selection() == [manager.items[3]]
        await pilot.press("shift+up", "escape")
        assert len(app.selection()) == 1

        # "d" asks once for the whole selection, "D" removes at once
        await pilot.press("up", "shift+up", "d")
        assert isinstance(app.screen, ModalScreen)
        await pilot.press("y")
        assert len(manager.items) == 2
        await pilot.press("shift+down", "D")
        assert manager.items == []
        await pilot.press("q")


async def test_f_moves_finished_files(server, tmp_path):
    manager = Manager(tmp_path / "dl", Store(tmp_path / "queue.json"), max_parallel=3)
    app = DownloaderApp(manager, [f"{server.base}/a/file.bin"])
    async with app.run_test(size=(120, 30)) as pilot:
        (item,) = manager.items
        await pilot.press("f")  # still downloading: no dialog
        assert not isinstance(app.screen, ModalScreen)
        await wait_for(lambda: item.state == DONE)
        await pilot.press("f")
        assert isinstance(app.focused, Input)
        await pilot.press(*"movies", "enter")
        assert Path(item.dest).parent == tmp_path / "dl" / "movies"
        assert Path(item.dest).read_bytes() == server.expected("/a/file.bin")
        await pilot.press("q")


async def test_alt_arrows_reorder(server, tmp_path):
    manager = Manager(tmp_path / "dl", Store(tmp_path / "queue.json"), max_parallel=1)
    urls = [f"{server.base}/{n}/file.bin" for n in "abcd"]
    app = DownloaderApp(manager, urls)
    async with app.run_test(size=(120, 30)) as pilot:
        table = app.query_one(DataTable)
        a, b, c, d = manager.items

        def shown():
            return [row.key.value for row in table.ordered_rows]

        await pilot.press("down", "down")  # cursor on c
        await pilot.press("alt+up")
        assert manager.items == [a, c, b, d] and shown() == [i.id for i in manager.items]
        assert app.selection() == [c] and table.cursor_row == 1

        await pilot.press("alt+up", "alt+up")  # second press stops at the top
        assert manager.items == [c, a, b, d] and table.cursor_row == 0

        # a Shift+arrow selection moves as a block
        await pilot.press("shift+down")
        assert app.selection() == [c, a]
        await pilot.press("alt+down")
        assert manager.items == [b, c, a, d] and shown() == [i.id for i in manager.items]
        assert app.selection() == [c, a]
        await pilot.press("alt+down", "alt+down")
        assert manager.items == [b, d, c, a]  # block stops at the bottom
        assert Store(tmp_path / "queue.json").load()[0].id == b.id
        await pilot.press("q")


async def test_pasting_several_urls_adds_them_all(tmp_path):
    from textual import events

    manager = Manager(tmp_path / "dl", Store(tmp_path / "queue.json"), max_parallel=1)
    app = DownloaderApp(manager, [])
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("a")
        urls = ["http://127.0.0.1:1/a/one.bin", "http://127.0.0.1:1/b/two.bin", "http://127.0.0.1:1/c/three.bin"]
        app.focused.post_message(events.Paste("\n".join(urls) + "\n"))
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert [i.url for i in manager.items] == urls


async def test_pasting_on_the_queue_adds_urls(tmp_path):
    from textual import events

    manager = Manager(tmp_path / "dl", Store(tmp_path / "queue.json"), max_parallel=1)
    app = DownloaderApp(manager, [])
    async with app.run_test(size=(120, 30)) as pilot:
        app.post_message(events.Paste("see:\nhttp://127.0.0.1:1/a/one.bin\nhttp://127.0.0.1:1/b/two.bin\n"))
        await pilot.pause()
        assert [i.url for i in manager.items] == ["http://127.0.0.1:1/a/one.bin", "http://127.0.0.1:1/b/two.bin"]

        # inside a dialog the paste goes to the dialog, not straight to the queue
        await pilot.press("a")
        app.post_message(events.Paste("http://127.0.0.1:1/c/three.bin"))
        await pilot.pause()
        assert len(manager.items) == 2


async def test_enter_on_failed_download_shows_full_error(tmp_path):
    from downloader.app import ErrorScreen
    from downloader.store import FAILED

    manager = Manager(tmp_path / "dl", Store(tmp_path / "queue.json"), max_parallel=1)
    app = DownloaderApp(manager, [])
    async with app.run_test(size=(120, 30)) as pilot:
        item = manager.add("http://127.0.0.1:1/a/one.bin")
        manager.pause(item)
        await pilot.pause()
        await pilot.press("enter")  # not failed: nothing happens
        assert not isinstance(app.screen, ErrorScreen)

        item.state, item.error = FAILED, "ERROR [markup] " + "long message " * 10
        app.refresh_table()
        await pilot.press("enter")
        assert isinstance(app.screen, ErrorScreen)
        await pilot.press("escape")
        assert not isinstance(app.screen, ErrorScreen)
