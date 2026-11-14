import re

from downloader.naming import distinctive_name, is_meaningful


def test_includes_meaningful_parent_folder():
    name = distinctive_name("https://archive.org/details/attila-verona/DVDVideo.rar")
    assert re.fullmatch(r"attila-verona-DVDVideo-[0-9a-f]{6}\.rar", name)


def test_same_remote_name_gives_different_files():
    a = distinctive_name("https://example.com/a/file.zip")
    b = distinctive_name("https://example.org/b/file.zip")
    assert a != b
    assert a.endswith(".zip") and b.endswith(".zip")


def test_same_url_is_stable():
    url = "https://example.com/x/file.zip?token=1"
    assert distinctive_name(url) == distinctive_name(url)


def test_generic_and_id_folders_are_skipped():
    assert re.fullmatch(r"file-[0-9a-f]{6}\.zip", distinctive_name("https://x.com/download/file.zip"))
    assert re.fullmatch(r"file-[0-9a-f]{6}\.zip", distinctive_name("https://x.com/files/12345/file.zip"))
    assert re.fullmatch(r"file-[0-9a-f]{6}\.zip", distinctive_name("https://x.com/file.zip"))
    # skips the version folder and takes the next meaningful one
    name = distinctive_name("https://x.com/pub/kernel/v6.x/patch.xz")
    assert name.startswith("kernel-patch-")


def test_folder_already_in_filename_is_not_repeated():
    name = distinctive_name("https://x.com/ubuntu/ubuntu-24.04.iso")
    assert re.fullmatch(r"ubuntu-24\.04-[0-9a-f]{6}\.iso", name)


def test_double_extension_and_decoding():
    assert re.fullmatch(r"my_app-[0-9a-f]{6}\.tar\.gz", distinctive_name("https://x.com/my%20app.tar.gz"))


def test_no_filename_and_unsafe_chars():
    assert re.fullmatch(r"download-[0-9a-f]{6}", distinctive_name("https://x.com/"))
    name = distinctive_name("https://x.com/a/..%2F..%2Fetc%2Fpasswd")
    assert "/" not in name and not name.startswith(".")


def test_is_meaningful():
    assert is_meaningful("attila-verona")
    assert not is_meaningful("details")
    assert not is_meaningful("deadbeef1234")
    assert not is_meaningful("ab")
