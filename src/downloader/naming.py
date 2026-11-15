"""Turn a URL into a distinctive local filename.

    https://archive.org/details/attila-verona/DVDVideo.rar
        -> attila-verona-DVDVideo.rar

The name is a meaningful parent folder from the URL path (if there is one)
plus the remote file name. It is not guaranteed unique; use `unique_name`
to add a -2, -3, ... suffix when the name is already taken.
"""

from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlsplit

MAX_PART = 80

DOUBLE_EXTS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst", ".tar.lz", ".tar.z")

# Folder names that say nothing about the content.
GENERIC = {
    "api", "archive", "archives", "asset", "assets", "attachment", "attachments",
    "bin", "blob", "cdn", "content", "data", "details", "dist", "dl", "doc",
    "docs", "download", "downloads", "file", "files", "get", "img", "image",
    "images", "item", "items", "latest", "main", "master", "media", "mirror",
    "mirrors", "out", "pub", "public", "raw", "release", "releases", "repo",
    "res", "resources", "share", "shared", "src", "stable", "static", "storage",
    "tmp", "upload", "uploads", "user", "users", "view", "www",
}

_ID_LIKE = re.compile(r"(\d+|[0-9a-f]{8,}|[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12})", re.I)
_VERSION_LIKE = re.compile(r"v?\d+([._-][\w]+)*", re.I)


def _sanitize(text: str) -> str:
    text = re.sub(r"[^\w.\-+()]+", "_", text)
    return text.strip("._ ")


def _split_ext(name: str) -> tuple[str, str]:
    lower = name.lower()
    for ext in DOUBLE_EXTS:
        if lower.endswith(ext) and len(name) > len(ext):
            return name[: -len(ext)], name[-len(ext):]
    stem, ext = os.path.splitext(name)
    if len(ext) > 10:  # not a real extension, just a dot in the name
        return name, ""
    return stem, ext


def is_meaningful(segment: str, stem: str = "") -> bool:
    """Does this URL path folder tell us something about the file?"""
    if not 3 <= len(segment) <= 60:
        return False
    if segment.lower() in GENERIC:
        return False
    if not re.search(r"[^\W\d_]", segment):  # needs at least one letter
        return False
    if _ID_LIKE.fullmatch(segment) or _VERSION_LIKE.fullmatch(segment):
        return False
    if stem and segment.lower() in stem.lower():  # already part of the file name
        return False
    return True


def distinctive_name(url: str) -> str:
    path = urlsplit(url).path
    parts = [_sanitize(unquote(p)) for p in path.split("/")]
    parts = [p for p in parts if p]
    if parts and not path.endswith("/"):
        filename, parents = parts[-1], parts[:-1]
    else:
        filename, parents = "download", parts

    stem, ext = _split_ext(filename)
    stem = stem or "download"
    context = next((p for p in reversed(parents) if is_meaningful(p, stem)), "")

    pieces = [context[:MAX_PART], stem[:MAX_PART]]
    return "-".join(p for p in pieces if p) + ext


def unique_name(name: str, taken) -> str:
    """Return `name`, or the first free `stem-2.ext`, `stem-3.ext`, ... if it is taken."""
    if not taken(name):
        return name
    stem, ext = _split_ext(name)
    n = 2
    while taken(f"{stem}-{n}{ext}"):
        n += 1
    return f"{stem}-{n}{ext}"
