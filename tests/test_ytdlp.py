import os
import stat
from pathlib import Path

from conftest import wait_for
from downloader import ytdlp
from downloader.manager import Manager
from downloader.store import DONE, FAILED, Store


def test_video_sites_are_recognised():
    assert ytdlp.is_video_site("https://www.youtube.com/watch?v=x")
    assert ytdlp.is_video_site("https://youtu.be/x")
    assert ytdlp.is_video_site("https://m.facebook.com/watch/?v=1")
    assert ytdlp.is_video_site("https://xhamster.com/videos/a")
    assert not ytdlp.is_video_site("https://notyoutube.com/a.zip")
    assert not ytdlp.is_video_site("https://example.com/youtube.com/a.zip")


def test_parse_path_and_error():
    assert ytdlp.parse_path("DL-FILE:/d/a.mp4") == "/d/a.mp4"
    assert ytdlp.parse_path("DL-DONE:/d/a.mp4") == "/d/a.mp4"
    assert ytdlp.parse_path("[youtube] x") is None
    assert ytdlp.parse_size("DL-SIZE:475961") == 475961
    assert ytdlp.parse_size("DL-SIZE:1234.0") == 1234
    assert ytdlp.parse_size("DL-SIZE:NA") is None
    assert ytdlp.error_text(["a", "ERROR: [x] boom"]) == "yt-dlp: [x] boom"


def test_size_on_disk_counts_parts(tmp_path):
    (tmp_path / "A-1.f137.mp4.part").write_bytes(b"x" * 10)
    (tmp_path / "A-1.f251.webm").write_bytes(b"x" * 5)
    (tmp_path / "B-2.mp4").write_bytes(b"x" * 99)
    assert ytdlp.size_on_disk(str(tmp_path / "A-1.mp4")) == 15


async def test_estimated_size_is_used_while_downloading(tmp_path, monkeypatch):
    out = tmp_path / "dl"
    path = fake_ytdlp(tmp_path, f'mkdir -p {out}; echo "DL-SIZE:12345"; echo "DL-FILE:{out}/Clip-abc.mp4"; exec sleep 30\n')
    monkeypatch.setenv("PATH", path + os.pathsep + os.environ["PATH"])
    m = Manager(out, Store(tmp_path / "q.json"))
    item = m.add("https://www.youtube.com/watch?v=abc")
    await wait_for(lambda: item.total == 12345)
    m.pause(item)
    await wait_for(lambda: not m._procs)


def fake_ytdlp(tmp_path, script):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool = bin_dir / "yt-dlp"
    tool.write_text("#!/bin/sh\n" + script)
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    return str(bin_dir)


async def test_video_site_uses_ytdlp(tmp_path, monkeypatch):
    out = tmp_path / "dl"
    path = fake_ytdlp(tmp_path, f'mkdir -p {out}; echo data > {out}/Clip-abc.mp4\n'
                                f'echo "DL-SIZE:12345"; echo "DL-FILE:{out}/Clip-abc.mp4"; echo "DL-DONE:{out}/Clip-abc.mp4"\n')
    monkeypatch.setenv("PATH", path + os.pathsep + os.environ["PATH"])
    m = Manager(out, Store(tmp_path / "q.json"))
    item = m.add("https://www.youtube.com/watch?v=abc")
    assert item.tool == "yt-dlp"
    await wait_for(lambda: item.state == DONE)
    assert item.name == "Clip-abc.mp4"
    assert item.downloaded == 5
    assert item.total == 5  # the estimate is replaced by the real size when done


async def test_wget_failure_falls_back_to_ytdlp(server, tmp_path, monkeypatch):
    out = tmp_path / "dl"
    path = fake_ytdlp(tmp_path, f'mkdir -p {out}; echo data > {out}/Page-1.mp4\n'
                                f'echo "DL-DONE:{out}/Page-1.mp4"\n')
    monkeypatch.setenv("PATH", path + os.pathsep + os.environ["PATH"])
    m = Manager(out, Store(tmp_path / "q.json"))
    item = m.add("http://127.0.0.1:1/page")  # connection refused: wget fails
    assert item.tool == "wget"
    await wait_for(lambda: item.state == DONE)
    assert item.tool == "yt-dlp" and item.name == "Page-1.mp4"


async def test_both_fail_keeps_wget_and_shows_both_errors(tmp_path, monkeypatch):
    path = fake_ytdlp(tmp_path, 'echo "ERROR: Unsupported URL" >&2; exit 1\n')
    monkeypatch.setenv("PATH", path + os.pathsep + os.environ["PATH"])
    m = Manager(tmp_path / "dl", Store(tmp_path / "q.json"))
    item = m.add("http://127.0.0.1:1/page")
    await wait_for(lambda: item.state == FAILED)
    assert item.tool == "wget"
    assert "yt-dlp: Unsupported URL" in item.error
