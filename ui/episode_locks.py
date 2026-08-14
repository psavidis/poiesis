"""Per-episode locking so two browser tabs (or a forgotten stale tab) can't
both mutate the same episode's files at once — a long-running pipeline/
stage/render run writing scene-plan.json (or manifest.json, transcripts,
etc.) at the same moment a second tab edits scene-plan.json through one of
the quick edit endpoints has no coordination otherwise, and either write
can silently clobber the other's.

Scope is deliberately narrow: one lock per resolved episode path, held only
for the duration of whichever operation is actually touching that episode's
files. Two different episodes never contend with each other.

threading.Lock rather than asyncio.Lock: the quick edit endpoints
(update_title_scenes/update_moments/edit_scene_plan) are plain `def` routes
that FastAPI runs in its worker thread pool, and the long-running
pipeline/stage/render runs do their actual work inside a
loop.run_in_executor thread too (see server.py's _stream_command) — an
asyncio.Lock is only safe to await from the event-loop thread itself, so it
can't coordinate across these. A plain threading.Lock works from any
thread, sync or the executor's.

This is a same-process, in-memory lock, not a filesystem lock — sufficient
for a single local control-panel server; it does not protect against a
second, separate `python3 pipeline/*.py` invocation run directly from a
terminal outside the UI.
"""

import threading
from contextlib import contextmanager
from pathlib import Path

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(episode: Path) -> threading.Lock:
    key = str(episode)

    with _locks_guard:
        lock = _locks.get(key)

        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock

        return lock


class EpisodeBusyError(Exception):
    """Raised when a caller asked to fail fast (wait=False) rather than
    block behind an in-progress operation on the same episode."""


@contextmanager
def episode_lock(episode: Path, *, wait: bool = True):
    """Acquires the lock for this episode for the duration of the `with`
    block. wait=True (the default) blocks behind an in-progress operation
    on the same episode, same as a normal lock — appropriate for the quick
    edit endpoints, where waiting a moment for a pipeline run to finish
    writing is preferable to rejecting the edit outright.

    wait=False fails fast with EpisodeBusyError instead of blocking — used
    for the long-running pipeline/stage/render runs, where silently
    queueing a second full pipeline run behind a first (each potentially
    minutes long) would leave the user waiting with no explanation; better
    to tell them immediately that one is already running for this
    episode."""

    lock = _lock_for(episode)

    if not wait:
        acquired = lock.acquire(blocking=False)

        if not acquired:
            raise EpisodeBusyError(f"An operation is already running for this episode: {episode.name}")

        try:
            yield
        finally:
            lock.release()

        return

    with lock:
        yield
