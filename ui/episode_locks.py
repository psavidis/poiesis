"""Per-episode locking so two browser tabs (or a forgotten stale tab) can't
both mutate the same episode's files at once — a long-running pipeline/
stage/render run writing scene-plan.json (or manifest.json, transcripts,
etc.) at the same moment a second tab edits scene-plan.json through one of
the quick edit endpoints has no coordination otherwise, and either write
can silently clobber the other's.

Scope is deliberately narrow: one lock per resolved episode path, held only
for the duration of whichever operation is actually touching that episode's
files. Two different episodes never contend with each other over THIS
lock — quick file edits on episode B are never blocked by a long-running
pipeline/stage/render run on episode A. machine_lock below is a second,
separate, deliberately coarser lock for exactly those long-running run
kinds (#85), where two different episodes SHOULD contend.

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

# One machine-wide slot for the long-running pipeline/stage/render
# subprocesses specifically (#85) — the per-episode lock above only ever
# prevented two runs against the SAME episode from racing; nothing stopped
# a pipeline run on episode A and a render on episode B from executing
# concurrently, competing for the same CPU/GPU/ffmpeg resources. Deliberately
# separate from _locks: the quick-edit endpoints (update_title_scenes etc.)
# are fast, in-process file edits, not subprocess runs, and must NOT be
# blocked by an unrelated episode's multi-minute pipeline run — only
# machine_lock() call sites (the three ws_run_* subprocess paths) contend
# for this one.
_machine_lock = threading.Lock()


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


def is_episode_locked(episode: Path) -> bool:
    """Non-blocking peek at whether an operation is currently in flight for
    this episode — used by a status-only GET endpoint (server.py's
    render_status, #65's sibling render-progress-recovery request) that
    just wants to know "is something running right now," not to actually
    hold the lock itself. Acquire-then-immediately-release is the standard
    safe pattern for this: the result can be stale by the time the caller
    reads it (a render could start or finish microseconds later), which is
    fine for a UI status display, but would NOT be fine for anything that
    needs the lock held across a check-then-act — those call sites must
    keep using episode_lock() as a context manager, never this."""

    lock = _lock_for(episode)

    acquired = lock.acquire(blocking=False)

    if acquired:
        lock.release()

    return not acquired


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


def is_machine_locked() -> bool:
    """Non-blocking peek at whether a pipeline/stage/render run is
    currently in flight ANYWHERE on this machine — same acquire-then-
    release pattern as is_episode_locked, same staleness caveat, used by a
    status-only endpoint rather than a check-then-act call site."""

    acquired = _machine_lock.acquire(blocking=False)

    if acquired:
        _machine_lock.release()

    return not acquired


@contextmanager
def machine_lock(*, wait: bool = False):
    """Acquires the machine-wide run slot for the duration of the `with`
    block (#85). wait=False (the default) fails fast with EpisodeBusyError
    instead of blocking — matches episode_lock's own wait=False behavior
    for the same reason: silently queueing a second multi-minute run behind
    a first, with no explanation, is worse than telling the caller
    immediately that one is already running (elsewhere, in this case, not
    necessarily this episode).

    Callers acquire this AFTER the per-episode lock (see server.py's
    _run_websocket) — the more common same-episode race gets the more
    specific EpisodeBusyError message from episode_lock first; either way,
    two different episodes now genuinely cannot run a pipeline/stage/
    render simultaneously, on top of the existing per-episode exclusion
    above."""

    if not wait:
        acquired = _machine_lock.acquire(blocking=False)

        if not acquired:
            raise EpisodeBusyError("Another pipeline/stage/render run is already in progress on this machine")

        try:
            yield
        finally:
            _machine_lock.release()

        return

    with _machine_lock:
        yield
