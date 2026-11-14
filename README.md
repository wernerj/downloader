# downloader

A terminal UI download queue. Every download is a real `wget` process.

## Install

Needs Python 3.11+ and `wget` on PATH (`brew install wget`).

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Use

```
.venv/bin/downloader [-d DIR] [-j N] [URL ...]
```

- `-d DIR` folder to save into (default: current folder)
- `-j N` downloads running at once (default: 3); the rest wait as `queued`
- `URL ...` URLs to queue right away

| Key | Action |
|---|---|
| `↑` / `↓` | move selection |
| `a` | add URL |
| `p` or `Space` | pause / resume selected |
| `r` | retry a failed download |
| `d` | remove from queue (asks first; the file on disk is kept) |
| `D` | remove from queue immediately, no confirmation (file on disk is kept) |
| `q` | quit (running downloads are paused and saved) |

## File names

`https://archive.org/details/attila-verona/DVDVideo.rar` is saved as
`attila-verona-DVDVideo-3fa9c1.rar`:

- the nearest meaningful folder from the URL path (generic ones like `details`,
  `download`, `files`, plain numbers, IDs and versions are skipped),
- the remote file name,
- a 6-character hash of the full URL, so two different URLs never share a file
  and the same URL always maps to the same file (needed for resume).

## Good to know

- Pause stops the `wget` process; resume starts it again with `wget -c`, which
  continues the partial file. If a server does not support range requests, the
  file starts again from zero.
- The queue is stored in `~/.downloader/queue.json` (change with `--state`).
  After a restart, unfinished downloads come back as `paused`.
- The file name is fixed before the download starts, so a name suggested by the
  server (Content-Disposition) is not used.

## Tests

```
.venv/bin/pytest
```

The tests run real `wget` against a small throttled local server
(`tests/slow_server.py`, also usable by hand: `python tests/slow_server.py`).
