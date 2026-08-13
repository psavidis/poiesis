"""Runs a subprocess and yields its combined stdout/stderr line by line.

Used to stream pipeline script output to the UI without changing any
pipeline script's own behavior — this only observes what the process prints,
the same as running it in a terminal.
"""

import subprocess


def stream_process(command, cwd=None):
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        for line in process.stdout:
            yield line.rstrip("\n")
    finally:
        process.stdout.close()
        process.wait()

    yield f"__EXIT_CODE__{process.returncode}"
