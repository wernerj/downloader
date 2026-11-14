import asyncio
import shutil
import threading

import pytest

from slow_server import content_for, make_server

SIZE = 300_000


@pytest.fixture
def server():
    """Throttled local server: a 300 KB file takes about 3 seconds."""
    if not shutil.which("wget"):
        pytest.skip("wget is not installed")
    srv = make_server(0, SIZE, 100_000)
    srv.handle_error = lambda *args: None  # dropped connections are expected
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.base = f"http://127.0.0.1:{srv.server_address[1]}"
    srv.expected = lambda path: content_for(path, SIZE)
    yield srv
    srv.shutdown()
    srv.server_close()


async def wait_for(condition, timeout=20.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not condition():
        assert loop.time() < end, "timed out waiting"
        await asyncio.sleep(0.05)
