from downloader.wget import build_command, error_text, parse_length


def test_parse_length_fresh_and_resumed():
    assert parse_length("Length: 400000 (391K) [application/octet-stream]") == 400000
    assert parse_length("Length: 400000 (391K), 227968 (223K) remaining [application/octet-stream]") == 400000
    assert parse_length("Length: unspecified [text/html]") is None
    assert parse_length("     0K ........ 98%  629K 0s") is None


def test_error_text_picks_the_error_line():
    lines = [
        "--2026-11-14 12:40:17--  http://127.0.0.1:8791/missing/x",
        "Connecting to 127.0.0.1:8791... connected.",
        "HTTP request sent, awaiting response... 404 Not Found",
        "2026-11-14 12:40:17 ERROR 404: Not Found.",
        "",
    ]
    assert error_text(lines) == "ERROR 404: Not Found."
    assert error_text([]) == "wget failed"


def test_url_cannot_become_an_option():
    cmd = build_command("--post-file=/etc/passwd", "/tmp/x")
    assert cmd.index("--") < cmd.index("--post-file=/etc/passwd")
