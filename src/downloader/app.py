"""The terminal UI."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Label

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
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds}s"


def row_cells(item: Download) -> dict[str, str]:
    style = STATE_STYLE[item.state]
    state = f"[{style}]{item.state}[/]"
    if item.state == FAILED and item.error:
        state += f" [dim]{item.error[:40].replace('[', '(')}[/]"
    if item.total:
        fraction = min(1.0, item.downloaded / item.total)
        filled = int(fraction * BAR_WIDTH)
        progress = f"[{style}]{'█' * filled}[/][dim]{'░' * (BAR_WIDTH - filled)}[/] {fraction * 100:3.0f}%"
        size = f"{human_size(item.downloaded)} / {human_size(item.total)}"
    else:
        progress = ""
        size = human_size(item.downloaded) if item.downloaded else ""
    speed = eta = ""
    if item.state == DOWNLOADING and item.speed > 0:
        speed = f"{human_size(item.speed)}/s"
        if item.total:
            eta = human_time((item.total - item.downloaded) / item.speed)
    return {"name": item.name, "state": state, "progress": progress,
            "size": size, "speed": speed, "eta": eta}


class AddUrlScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    AddUrlScreen { align: center middle; }
    AddUrlScreen > Vertical { width: 80%; max-width: 100; height: auto;
        border: round $accent; padding: 1 2; background: $surface; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Add URL  [dim](Enter to add, Esc to cancel)[/]")
            yield Input(placeholder="https://example.com/file.zip")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

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


class DownloaderApp(App):
    TITLE = "downloader"
    BINDINGS = [
        Binding("a", "add", "Add URL"),
        Binding("p,space", "toggle", "Pause/Resume"),
        Binding("r", "retry", "Retry"),
        Binding("d", "remove", "Remove"),
        Binding("D", "remove_now", "Remove (no confirm)"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, manager: Manager, urls: list[str] | None = None):
        super().__init__()
        self.manager = manager
        self.initial_urls = urls or []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = str(self.manager.dest_dir)
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
        if isinstance(self.screen, ModalScreen) and action in ("add", "toggle", "retry", "remove", "remove_now", "quit"):
            return False
        return True

    # ---- table ---------------------------------------------------------

    def refresh_table(self) -> None:
        self.manager.tick()
        table = self.table
        wanted = {item.id for item in self.manager.items}
        for row_key in list(table.rows):
            if row_key.value not in wanted:
                table.remove_row(row_key)
        present = {row_key.value for row_key in table.rows}
        for item in self.manager.items:
            cells = row_cells(item)
            if item.id not in present:
                table.add_row(*(cells[key] for key, _ in COLUMNS), key=item.id)
            else:
                for key, _ in COLUMNS:
                    if table.get_cell(item.id, key) != cells[key]:
                        table.update_cell(item.id, key, cells[key], update_width=True)

    def selected(self) -> Download | None:
        table = self.table
        if not table.row_count:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return next((item for item in self.manager.items if item.id == row_key.value), None)

    def _add(self, url: str, select: bool = False) -> None:
        try:
            item = self.manager.add(url)
        except ValueError as exc:
            self.notify(f"{exc}: {url}", severity="error")
            return
        self.refresh_table()
        if select:
            self.table.move_cursor(row=self.table.get_row_index(item.id))

    # ---- keys ----------------------------------------------------------

    def action_add(self) -> None:
        def done(url: str | None) -> None:
            if url:
                self._add(url, select=True)

        self.push_screen(AddUrlScreen(), done)

    def action_toggle(self) -> None:
        item = self.selected()
        if item:
            self.manager.toggle(item)
            self.refresh_table()

    def action_retry(self) -> None:
        item = self.selected()
        if item and item.state == FAILED:
            self.manager.resume(item)
            self.refresh_table()

    def action_remove(self) -> None:
        item = self.selected()
        if not item:
            return

        def done(confirmed: bool | None) -> None:
            if confirmed:
                self.manager.remove(item)
                self.refresh_table()

        self.push_screen(ConfirmScreen(f"Remove [b]{item.name}[/] from the queue? The file on disk is kept."), done)

    def action_remove_now(self) -> None:
        item = self.selected()
        if item:
            self.manager.remove(item)
            self.refresh_table()

    async def action_quit(self) -> None:
        await self.manager.shutdown()
        self.exit()
