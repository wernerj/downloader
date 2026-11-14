# downloader

TUI download queue wrapping `wget`, for personal use. Python + Textual.

## Layout
- `src/downloader/naming.py` URL → distinctive file name (parent folder + name + URL hash)
- `src/downloader/wget.py` builds/starts the wget process, parses its output
- `src/downloader/manager.py` queue, states, parallel limit, pause/resume
- `src/downloader/store.py` queue persistence (`~/.downloader/queue.json`)
- `src/downloader/app.py` Textual UI and key bindings
- `tests/slow_server.py` throttled local HTTP server used by tests and manual checks

## How we work
- Run: `.venv/bin/downloader -d DIR URL...`; tests: `.venv/bin/pytest` (they use real wget).
- wget is always started with an argument list and `LC_ALL=C` (its messages are localized).
- Progress comes from the size of the file on disk, not from parsing wget's progress output.
- Pause = terminate wget, resume = `wget -c`. Keep one wget per destination file.
- Commit and push only when asked.
