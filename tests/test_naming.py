from downloader.naming import distinctive_name, is_meaningful, unique_name


def test_includes_meaningful_parent_folder():
    name = distinctive_name("https://archive.org/details/attila-verona/DVDVideo.rar")
    assert name == "attila-verona-DVDVideo.rar"


def test_unique_name_adds_counter_before_extension():
    taken = {"file.tar.gz", "file-2.tar.gz"}
    assert unique_name("file.tar.gz", taken.__contains__) == "file-3.tar.gz"
    assert unique_name("other.zip", taken.__contains__) == "other.zip"


def test_same_url_is_stable():
    url = "https://example.com/x/file.zip?token=1"
    assert distinctive_name(url) == distinctive_name(url)


def test_generic_and_id_folders_are_skipped():
    assert distinctive_name("https://x.com/download/file.zip") == "file.zip"
    assert distinctive_name("https://x.com/files/12345/file.zip") == "file.zip"
    assert distinctive_name("https://x.com/file.zip") == "file.zip"
    # skips the version folder and takes the next meaningful one
    name = distinctive_name("https://x.com/pub/kernel/v6.x/patch.xz")
    assert name == "kernel-patch.xz"


def test_folder_already_in_filename_is_not_repeated():
    name = distinctive_name("https://x.com/ubuntu/ubuntu-24.04.iso")
    assert name == "ubuntu-24.04.iso"


def test_double_extension_and_decoding():
    assert distinctive_name("https://x.com/my%20app.tar.gz") == "my_app.tar.gz"


def test_no_filename_and_unsafe_chars():
    assert distinctive_name("https://x.com/") == "download"
    name = distinctive_name("https://x.com/a/..%2F..%2Fetc%2Fpasswd")
    assert "/" not in name and not name.startswith(".")


def test_is_meaningful():
    assert is_meaningful("attila-verona")
    assert not is_meaningful("details")
    assert not is_meaningful("deadbeef1234")
    assert not is_meaningful("ab")
