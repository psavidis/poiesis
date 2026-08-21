import sys
import time

from process_runner import stream_process


def test_stream_process_yields_output_lines():
    lines = list(
        stream_process([sys.executable, "-c", "print('hello'); print('world')"])
    )

    assert lines[0] == "hello"
    assert lines[1] == "world"


def test_stream_process_yields_exit_code_marker_on_success():
    lines = list(stream_process([sys.executable, "-c", "pass"]))

    assert lines[-1] == "__EXIT_CODE__0"


def test_stream_process_yields_nonzero_exit_code_on_failure():
    lines = list(stream_process([sys.executable, "-c", "import sys; sys.exit(1)"]))

    assert lines[-1] == "__EXIT_CODE__1"


def test_stream_process_captures_stderr_too():
    lines = list(
        stream_process(
            [sys.executable, "-c", "import sys; print('oops', file=sys.stderr)"]
        )
    )

    assert "oops" in lines[0]


def test_stream_process_cancel_terminates_and_yields_cancelled_marker():
    """Mirrors how server.py drives this: a background thread calls
    handle.cancel() shortly after the process starts, while the generator
    is being drained on another thread."""

    import threading

    def cancel_soon(handle):
        def go():
            time.sleep(0.2)
            handle.cancel()

        threading.Thread(target=go, daemon=True).start()

    lines = list(
        stream_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            on_start=cancel_soon,
        )
    )

    assert lines[-1].startswith("__CANCELLED__")
