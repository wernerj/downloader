from downloader.store import DONE, DOWNLOADING, FAILED, PAUSED, QUEUED, Download, Store


def test_round_trip_pauses_unfinished(tmp_path):
    store = Store(tmp_path / "state" / "queue.json")
    store.save([
        Download("1", "http://a/x", "/d/x", DOWNLOADING, total=10, downloaded=4, speed=99.0),
        Download("2", "http://a/y", "/d/y", QUEUED),
        Download("3", "http://a/z", "/d/z", DONE, total=5, downloaded=5),
        Download("4", "http://a/w", "/d/w", FAILED, error="ERROR 404"),
    ])
    items = store.load()
    assert [i.state for i in items] == [PAUSED, PAUSED, DONE, FAILED]
    assert items[0].total == 10 and items[0].downloaded == 4 and items[0].speed == 0.0
    assert items[3].error == "ERROR 404"


def test_missing_or_broken_file_gives_empty_queue(tmp_path):
    assert Store(tmp_path / "nope.json").load() == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert Store(bad).load() == []
