import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import console_safe, stdout_supports_unicode


def test_console_safe_ascii_fallback():
    original = sys.stdout
    try:
        import io

        sys.stdout = io.TextIOWrapper(
            io.BytesIO(), encoding="ascii", errors="strict"
        )
        assert not stdout_supports_unicode()
        assert "?" in console_safe("⚡ test") or "test" in console_safe("⚡ test")
    finally:
        sys.stdout = original


def test_human_print_uses_stderr_under_mcp_host(monkeypatch, capsys):
    monkeypatch.setenv("AQUILA_STDIO_MCP_HOST", "1")
    from agent.core import human_print, mcp_stdio_host_active

    assert mcp_stdio_host_active()
    human_print("MCP progress line")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "MCP progress line" in captured.err


def test_safe_stdout_write_with_none_stdout(monkeypatch):
    monkeypatch.delenv("AQUILA_STDIO_MCP_HOST", raising=False)
    monkeypatch.setattr("agent.core.stdio_safe.sys.stdout", None, raising=False)
    monkeypatch.setattr("agent.core.stdio_safe.sys.stderr", None, raising=False)
    from agent.core.stdio_safe import human_output_stream, safe_stdout_write

    stream = human_output_stream()
    assert stream is not None
    safe_stdout_write("hello from packaged gui")


def test_run_logger_console_uses_stderr_under_mcp_host(monkeypatch):
    monkeypatch.setenv("AQUILA_STDIO_MCP_HOST", "1")
    from agent.core import RunLogger
    import sys

    logger = RunLogger()
    assert logger.console.file is sys.stderr
