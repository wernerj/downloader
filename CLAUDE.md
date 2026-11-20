# downloader

TUI download queue wrapping `wget`, for personal use. Python + Textual.

## Layout
- `src/downloader/naming.py` URL → distinctive file name (parent folder + name, -2/-3 suffix on clash)
- `src/downloader/wget.py` builds/starts the wget process, parses its output
- `src/downloader/ytdlp.py` yt-dlp command, video-site list, file-name/size handling
- `src/downloader/manager.py` queue, states, parallel limit, pause/resume
- `src/downloader/store.py` queue persistence (`~/.downloader/queue.json`)
- `src/downloader/app.py` Textual UI and key bindings
- `tests/slow_server.py` throttled local HTTP server used by tests and manual checks

## How we work
- Run: `.venv/bin/downloader -d DIR URL...`; tests: `.venv/bin/pytest` (they use real wget).
- wget is always started with an argument list and `LC_ALL=C` (its messages are localized).
- Progress comes from the size of the file on disk, not from parsing wget's progress output.
- Video-site domains (`ytdlp.VIDEO_DOMAINS`) use yt-dlp from the start; if wget fails, the item is retried once with yt-dlp. yt-dlp picks the file name; `Download.tool` records which one runs.
- Pause = terminate wget, resume = `wget -c`. Keep one wget per destination file.
- Commit and push only when asked.
