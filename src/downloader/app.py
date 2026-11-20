"""The terminal UI."""

from __future__ import annotations

import math

from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Label, OptionList

from .manager import Manager
from .store import DONE, DOWNLOADING, FAILED, PAUSED, QUEUED, Download

COLUMNS = (("name", "File"), ("state", "State"), ("progress", "Progress"),
           ("size", "Size"), ("speed", "Speed"), ("eta", "ETA"))

STATE_STYLE = {QUEUED: "dim", DOWNLOADING: "cyan", PAUSED: "yellow", DONE: "green", FAILED: "red"}
BAR_WIDTH = 12


def human_size(count: float | None) -> str:
    if count is None:
        return "?"
    for unit in ("B", "K", "M", "G"):
        if count < 1024 or unit == "G":
            return f"{count:.0f}{unit}" if unit == "B" else f"{count:.1f}{unit}"
        count /= 1024
    return "?"


def human_time(seconds: float) -> str:
    if not math.isfinite(seconds):
        return ""
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds}s"


def row_cells(item: Download, marked: bool = False) -> dict[str, str]:
    style = STATE_STYLE[item.state]
    state = f"[{style}]{item.state}[/]"
    if item.state == FAILED and item.error:
        state += f" [dim]{item.error[:40].replace('[', '(')}[/]"
    if item.total:
        fraction = min(1.0, item.downloaded / item.total)
        # Only a completed download shows 100%; otherwise round down and cap at 99%.
        percent = 100 if item.state == DONE else min(99, int(fraction * 100))
        filled = BAR_WIDTH if item.state == DONE else min(BAR_WIDTH - 1, int(fraction * BAR_WIDTH))
        progress = f"[{style}]{'█' * filled}[/][dim]{'░' * (BAR_WIDTH - filled)}[/] {percent:3d}%"
        size = f"{human_size(item.downloaded)} / {human_size(item.total)}"
    else:
        progress = ""
        size = human_size(item.downloaded) if item.downloaded else ""
    speed = eta = ""
    if item.state == DOWNLOADING and item.speed >= 1:
        speed = f"{human_size(item.speed)}/s"
        if item.total:
            eta = human_time(max(0, item.total - item.downloaded) / item.speed)
    name = f"[b]● {item.name}[/]" if marked else f"  {item.name}"
    return {"name": name, "state": state, "progress": progress,
            "size": size, "speed": speed, "eta": eta}


class PasteInput(Input):
    """Input that keeps all lines of a paste (Textual keeps only the first), joined by spaces."""

    def _on_paste(self, event: events.Paste) -> None:
        text = " ".join(event.text.split())
        if text:
            if self.selection.is_empty:
                self.insert_text_at_cursor(text)
            else:
                self.replace(text, *self.selection)
        event.prevent_default()  # skip Input's own first-line-only handling
        event.stop()


class PromptScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    PromptScreen { align: center middle; }
    PromptScreen > Vertical { width: 80%; max-width: 100; height: auto;
        border: round $accent; padding: 1 2; background: $surface; }
    """

    def __init__(self, title: str, placeholder: str = ""):
        super().__init__()
        self.title_text = title
        self.placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"{self.title_text}  [dim](Enter to confirm, Esc to cancel)[/]")
            yield PasteInput(placeholder=self.placeholder)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class FolderScreen(ModalScreen[str | None]):
    """Type a new folder name, or pick an existing one (Down arrow moves into the list)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("down", "to_list", "Existing folders", show=False)]
    DEFAULT_CSS = """
    FolderScreen { align: center middle; }
    FolderScreen > Vertical { width: 80%; max-width: 100; height: auto;
        border: round $accent; padding: 1 2; background: $surface; }
    FolderScreen OptionList { height: auto; max-height: 10; margin-top: 1; }
    """

    def __init__(self, title: str, folders: list[str]):
        super().__init__()
        self.title_text = title
        self.folders = folders

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"{self.title_text}  [dim](Enter to confirm, Esc to cancel)[/]")
            yield Input(placeholder="new folder name, or ↓ to pick an existing one")
            yield OptionList(*self.folders)

    def on_mount(self) -> None:
        self._sync_list("")

    def _sync_list(self, text: str) -> None:
        options = self.query_one(OptionList)
        options.clear_options()
        text = text.strip().lower()
        options.add_options([f for f in self.folders if text in f.lower()])
        options.display = options.option_count > 0
        if options.option_count:
            options.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._sync_list(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(str(event.option.prompt))

    def action_to_list(self) -> None:
        options = self.query_one(OptionList)
        if options.option_count:
            options.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [Binding("y,enter", "answer(True)", "Yes"), Binding("n,escape", "answer(False)", "No")]
    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Vertical { width: auto; max-width: 90%; height: auto;
        border: round $warning; padding: 1 2; background: $surface; }
    """

    def __init__(self, question: str):
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.question)
            yield Label("[dim]y = yes, n = no[/]")

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)


class ErrorScreen(ModalScreen[None]):
    """The full error message of a failed download (the table cuts it short)."""

    BINDINGS = [Binding("escape,enter,q", "close", "Close")]
    DEFAULT_CSS = """
    ErrorScreen { align: center middle; }
    ErrorScreen > Vertical { width: 80%; max-width: 110; height: auto;
        border: round $error; padding: 1 2; background: $surface; }
    """

    def __init__(self, item: Download):
        super().__init__()
        self.item = item

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"[b]{escape(self.item.name)}[/]  [dim]({self.item.tool})[/]")
            yield Label(escape(self.item.url), markup=False)
            yield Label(self.item.error, markup=False)
            yield Label("[dim]Enter or Esc to close[/]")

    def action_close(self) -> None:
        self.dismiss(None)


class QueueTable(DataTable):
    """DataTable where Shift+arrows extend a selection and plain arrows drop it."""

    BINDINGS = [
        Binding("shift+up", "extend(-1)", "Select up", show=False),
        Binding("shift+down", "extend(1)", "Select down", show=False),
        Binding("A", "select_all", "Select all", show=False),
        Binding("alt+up", "shift_items(-1)", "Move up", show=False),
        Binding("alt+down", "shift_items(1)", "Move down", show=False),
    ]

    def action_extend(self, step: int) -> None:
        self.app.extend_selection(step)

    def action_select_all(self) -> None:
        self.app.select_all()

    def action_shift_items(self, step: int) -> None:
        self.app.shift_items(step)

    def action_cursor_up(self) -> None:
        self.app.clear_selection()
        super().action_cursor_up()

    def action_cursor_down(self) -> None:
        self.app.clear_selection()
        super().action_cursor_down()


class DownloaderApp(App):
    TITLE = "downloader"
    BINDINGS = [
        Binding("a", "add", "Add URL"),
        Binding("p,space", "toggle", "Pause/Resume"),
        Binding("r", "retry", "Retry"),
        Binding("d", "remove", "Remove"),
        Binding("f", "move", "Move to folder"),
        Binding("D", "remove_now", "Remove (no confirm)"),
        Binding("plus,equals_sign,kp_plus", "jobs(1)", "Jobs", key_display="+/-"),
        Binding("minus,kp_minus", "jobs(-1)", "Fewer jobs", show=False),
        Binding("q", "quit", "Quit"),
        Binding("escape", "clear_selection", "Clear selection", show=False),
    ]

    def __init__(self, manager: Manager, urls: list[str] | None = None):
        super().__init__()
        self.manager = manager
        self.initial_urls = urls or []
        self._anchor: int | None = None  # where a Shift+arrow selection started

    def compose(self) -> ComposeResult:
        yield Header()
        yield QueueTable(cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.table
        for key, label in COLUMNS:
            table.add_column(label, key=key)
        for url in self.initial_urls:
            self._add(url)
        self.refresh_table()
        table.focus()
        self.set_interval(0.5, self.refresh_table)

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # Queue keys do nothing while a dialog is open.
        if isinstance(self.screen, ModalScreen) and action in ("add", "toggle", "retry", "remove", "remove_now", "move", "jobs", "quit"):
            return False
        return True

    # ---- table ---------------------------------------------------------

    def refresh_table(self) -> None:
        self.manager.tick()
        table = self.table
        marked = {item.id for item in self.selection()} if self._anchor is not None else set()
        count = len(marked)
        self.sub_title = (f"{self.manager.dest_dir}  ·  {self.manager.max_parallel} parallel"
                          + (f"  ·  {count} selected" if count > 1 else ""))
        wanted = {item.id for item in self.manager.items}
        for row_key in list(table.rows):
            if row_key.value not in wanted:
                table.remove_row(row_key)
        present = {row_key.value for row_key in table.rows}
        for item in self.manager.items:
            cells = row_cells(item, item.id in marked)
            if item.id not in present:
                table.add_row(*(cells[key] for key, _ in COLUMNS), key=item.id)
            else:
                for key, _ in COLUMNS:
                    if table.get_cell(item.id, key) != cells[key]:
                        table.update_cell(item.id, key, cells[key], update_width=True)

    def selection(self) -> list[Download]:
        """Items to act on: the Shift+arrow range, or just the row under the cursor."""
        count = self.table.row_count
        if not count:
            return []
        cursor = self.table.cursor_row
        anchor = cursor if self._anchor is None else min(self._anchor, count - 1)
        low, high = sorted((anchor, cursor))
        return self.manager.items[low : high + 1]

    def extend_selection(self, step: int) -> None:
        table = self.table
        if not table.row_count:
            return
        if self._anchor is None:
            self._anchor = table.cursor_row
        table.move_cursor(row=max(0, min(table.row_count - 1, table.cursor_row + step)))
        self.refresh_table()

    def select_all(self) -> None:
        table = self.table
        if not table.row_count:
            return
        self._anchor = 0
        table.move_cursor(row=table.row_count - 1)
        self.refresh_table()

    def shift_items(self, step: int) -> None:
        """Move the selected items one place up or down in the queue."""
        table = self.table
        if not self.manager.reorder(self.selection(), step):
            return
        cursor = table.cursor_row + step
        if self._anchor is not None:
            self._anchor += step
        table.clear()  # rows are keyed by id; rebuild them in the new order
        self.refresh_table()
        table.move_cursor(row=cursor)

    def clear_selection(self) -> None:
        if self._anchor is not None:
            self._anchor = None
            self.refresh_table()

    def action_clear_selection(self) -> None:
        self.clear_selection()

    def selected(self) -> Download | None:
        table = self.table
        if not table.row_count:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return next((item for item in self.manager.items if item.id == row_key.value), None)

    def _add(self, url: str, select: bool = False) -> bool:
        try:
            item = self.manager.add(url)
        except ValueError as exc:
            self.notify(f"{exc}: {url}", severity="error")
            return False
        self._anchor = None
        self.refresh_table()
        if select:
            self.table.move_cursor(row=self.table.get_row_index(item.id))
        return True

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a failed download shows its whole error message."""
        item = next((i for i in self.manager.items if i.id == event.row_key.value), None)
        if item and item.state == FAILED:
            self.push_screen(ErrorScreen(item))

    def on_paste(self, event: events.Paste) -> None:
        """Pasting on the queue itself adds the URLs in the text (dialogs handle their own pastes)."""
        if len(self.screen_stack) > 1:
            return
        self._add_urls([w for w in event.text.split() if "://" in w])

    def _add_urls(self, urls: list[str]) -> None:
        added = [self._add(url, select=(i == 0)) for i, url in enumerate(urls)]
        if len(urls) > 1:
            self.notify(f"Added {sum(added)} of {len(urls)} URLs")

    # ---- keys ----------------------------------------------------------

    def action_add(self) -> None:
        def done(text: str | None) -> None:
            self._add_urls((text or "").split())  # one or many, separated by spaces or new lines

        self.push_screen(PromptScreen("Add URL (or paste several)", "https://example.com/file.zip"), done)

    def action_toggle(self) -> None:
        items = self.selection()
        if any(i.state in (DOWNLOADING, QUEUED) for i in items):
            for item in items:
                self.manager.pause(item)  # pauses the active ones, ignores the rest
        else:
            for item in items:
                self.manager.resume(item)
        self.refresh_table()

    def action_retry(self) -> None:
        for item in self.selection():
            if item.state == FAILED:
                self.manager.resume(item)
        self.refresh_table()

    def action_jobs(self, step: int) -> None:
        before = self.manager.max_parallel
        self.manager.set_max_parallel(before + step)
        now = self.manager.max_parallel
        if now == before:
            self.notify("Minimum is 1 parallel download", severity="warning", timeout=2)
        else:
            self.notify(f"Parallel downloads: {now}", timeout=2)
        self.refresh_table()

    def action_move(self) -> None:
        items = [i for i in self.selection() if i.state == DONE]
        if not items:
            self.notify("Select finished downloads to move", severity="warning")
            return

        def done(folder: str | None) -> None:
            if not folder:
                return
            try:
                moved, problems = self.manager.move_done(items, folder)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            if moved:
                self.notify(f"Moved {moved} file(s) to {folder}/")
            if problems:
                self.notify("\n".join(problems), severity="error")
            self.refresh_table()

        self.push_screen(FolderScreen(f"Move {len(items)} file(s) to folder", self.manager.folders()), done)

    def action_remove(self) -> None:
        items = self.selection()
        if not items:
            return
        what = f"[b]{items[0].name}[/]" if len(items) == 1 else f"[b]{len(items)} items[/]"

        def done(confirmed: bool | None) -> None:
            if confirmed:
                self._remove(items)

        self.push_screen(ConfirmScreen(f"Remove {what} from the queue? Files on disk are kept."), done)

    def action_remove_now(self) -> None:
        self._remove(self.selection())

    def _remove(self, items: list[Download]) -> None:
        self._anchor = None
        for item in items:
            self.manager.remove(item)
        self.refresh_table()

    async def action_quit(self) -> None:
        await self.manager.shutdown()
        self.exit()
