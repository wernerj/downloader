import os
from pathlib import Path

import pytest

from conftest import wait_for
from downloader.manager import Manager
from downloader.store import DONE, DOWNLOADING, FAILED, PAUSED, QUEUED, Store


def make(tmp_path, jobs=3):
    return Manager(tmp_path / "dl", Store(tmp_path / "queue.json"), max_parallel=jobs)


async def test_same_name_downloads_to_two_correct_files(server, tmp_path):
    m = make(tmp_path)
    a = m.add(f"{server.base}/a/file.bin")
    b = m.add(f"{server.base}/b/file.bin")
    assert a.dest != b.dest
    await wait_for(lambda: a.state == DONE and b.state == DONE)
    assert Path(a.dest).read_bytes() == server.expected("/a/file.bin")
    assert Path(b.dest).read_bytes() == server.expected("/b/file.bin")
    assert a.total == a.downloaded == 300_000


async def test_pause_stops_and_resume_continues(server, tmp_path):
    m = make(tmp_path)
    item = m.add(f"{server.base}/a/file.bin")
    await wait_for(lambda: os.path.exists(item.dest) and os.path.getsize(item.dest) > 50_000)
    m.pause(item)
    assert item.state == PAUSED
    await wait_for(lambda: not m._procs)  # wget process is gone
    partial = os.path.getsize(item.dest)
    assert 0 < partial < 300_000
    m.tick()
    assert os.path.getsize(item.dest) == partial

    m.resume(item)
    assert item.state == DOWNLOADING
    await wait_for(lambda: item.state == DONE)
    # Correct content proves it continued instead of corrupting or restarting badly.
    assert Path(item.dest).read_bytes() == server.expected("/a/file.bin")


async def test_parallel_limit(server, tmp_path):
    m = make(tmp_path, jobs=2)
    items = [m.add(f"{server.base}/{n}/file.bin") for n in "abcd"]
    assert [i.state for i in items] == [DOWNLOADING, DOWNLOADING, QUEUED, QUEUED]
    m.pause(items[0])  # frees a slot
    assert [i.state for i in items] == [PAUSED, DOWNLOADING, DOWNLOADING, QUEUED]
    await wait_for(lambda: all(i.state == DONE for i in items[1:]))
    await m.shutdown()


async def test_failed_download_and_retry(server, tmp_path):
    m = make(tmp_path)
    item = m.add(f"{server.base}/missing/file.bin")
    await wait_for(lambda: item.state == FAILED)
    assert "404" in item.error
    assert not os.path.exists(item.dest)  # no empty leftover file
    m.resume(item)
    assert item.state == DOWNLOADING and item.error == ""
    await wait_for(lambda: item.state == FAILED)


async def test_rejects_bad_and_duplicate_urls(server, tmp_path):
    m = make(tmp_path)
    for bad in ("", "not a url", "file:///etc/passwd", "--post-file=/etc/passwd"):
        with pytest.raises(ValueError):
            m.add(bad)
    item = m.add(f"{server.base}/a/file.bin")
    with pytest.raises(ValueError):
        m.add(f"{server.base}/a/file.bin")
    m.remove(item)
    assert m.items == []
    await wait_for(lambda: not m._procs)


async def test_quit_and_restart_resumes(server, tmp_path):
    m = make(tmp_path)
    item = m.add(f"{server.base}/a/file.bin")
    await wait_for(lambda: os.path.exists(item.dest) and os.path.getsize(item.dest) > 50_000)
    await m.shutdown()
    assert not m._procs

    m2 = make(tmp_path)
    (restored,) = m2.items
    assert restored.state == PAUSED and 0 < restored.downloaded < 300_000
    m2.resume(restored)
    await wait_for(lambda: restored.state == DONE)
    assert Path(restored.dest).read_bytes() == server.expected("/a/file.bin")


async def test_move_done_files_into_folder(server, tmp_path):
    m = make(tmp_path)
    a = m.add(f"{server.base}/a/file.bin")
    b = m.add(f"{server.base}/b/file.bin")
    await wait_for(lambda: a.state == DONE and b.state == DONE)

    for bad in ("", "..", "a/b", "../x"):
        with pytest.raises(ValueError):
            m.move_done([a], bad)

    moved, problems = m.move_done([a, b], "videos")
    assert (moved, problems) == (2, [])
    assert Path(a.dest).parent == m.dest_dir / "videos"
    assert Path(a.dest).read_bytes() == server.expected("/a/file.bin")
    assert [i.dest for i in Store(tmp_path / "queue.json").load()] == [a.dest, b.dest]

    # moving again: files are in the folder already -> reported, not overwritten
    moved, problems = m.move_done([a], "videos")
    assert moved == 0 and "already exists" in problems[0]


async def test_move_skips_unfinished(server, tmp_path):
    m = make(tmp_path)
    item = m.add(f"{server.base}/a/file.bin")
    moved, problems = m.move_done([item], "x")
    assert moved == 0 and "not finished" in problems[0]
    assert not (m.dest_dir / "x").exists()  # no empty folder left behind
    await m.shutdown()


async def test_clashing_names_get_counter(tmp_path):
    m = make(tmp_path)
    m.dest_dir.mkdir()
    (m.dest_dir / "file.zip").write_bytes(b"old")
    a = m.add("https://one.example/1/file.zip")
    b = m.add("https://y.com/2/file.zip")
    m.pause(a)
    m.pause(b)
    assert Path(a.dest).name == "file-2.zip"
    assert Path(b.dest).name == "file-3.zip"
