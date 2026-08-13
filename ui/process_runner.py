"""Runs a subprocess and yields its combined stdout/stderr line by line.

Used to stream pipeline script output to the UI without changing any
pipeline script's own behavior — this only observes what the process prints,
the same as running it in a terminal.
"""

import os
import signal
import subprocess


class ProcessHandle:
    """Wraps a running Popen so a caller on another thread can cancel it.

    Pipeline/render scripts (e.g. render_episode.sh) spawn their own child
    processes (npx, remotion, ffmpeg). Killing just the shell wrapper leaves
    those running, so the process is started in its own session and
    cancellation signals the whole group.
    """

    def __init__(self, process: subprocess.Popen):
        self._process = process

    def cancel(self):
        if self._process.poll() is not None:
            return

        try:
            os.killpg(self._process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def stream_process(command, cwd=None, on_start=None):
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    if on_start is not None:
        on_start(ProcessHandle(process))

    try:
        for line in process.stdout:
            yield line.rstrip("\n")
    finally:
        process.stdout.close()
        process.wait()

    if process.returncode < 0:
        yield f"__CANCELLED__{-process.returncode}"
    else:
        yield f"__EXIT_CODE__{process.returncode}"
