"""A small server-side snapshot ring buffer backing preview-app's Undo
button — see docs/specs/ai-assisted-editing-and-conversational-control.md
sections 19/31, which require AI edits to integrate with "the same undo
system as manual edits."

The undoable unit is deliberately "every file a write endpoint touched,"
not just scene-plan.json — restoring only scene-plan.json while leaving a
companion source file (moments.json/emphasis.json/title_scenes.json)
un-restored would let that companion file's own save path silently
resurrect the undone change on its next write, the same bug class #33
already fixed once (a chat-removed moment getting resurrected by a stale
moments.json). Each checkpoint therefore snapshots the exact set of files
one write endpoint was about to touch, atomically, and undo restores that
whole set together.

Checkpoints live in processing/.undo/<timestamp>-<label>/ as plain copies
of whatever files existed right before the write (a file that didn't
exist yet has nothing to snapshot — restoring it later means deleting it,
handled explicitly in restore_latest). Bounded to UNDO_HISTORY_LIMIT
checkpoints per episode; this is local recovery scratch state; not
history a user is expected to browse or that needs unbounded retention.
"""

import json
import re
import shutil
import time
from pathlib import Path

UNDO_DIR_NAME = ".undo"
UNDO_HISTORY_LIMIT = 20


def _sanitize_for_dirname(label: str) -> str:
    """Labels can be arbitrary user-typed text (e.g. a chat instruction
    like "remove the third title card" or, in principle, anything a user
    types — including "/", very long text, or unicode) — never safe to
    embed directly into a filesystem directory name. The full,
    unsanitized label is still preserved in the checkpoint's manifest.json
    content (safe there, it's just JSON text, not a path); this is only
    for the directory name itself."""

    safe = re.sub(r"[^a-zA-Z0-9 _-]", "", label).strip()
    return safe[:60] or "edit"


def _undo_dir(processing: Path) -> Path:
    return processing / UNDO_DIR_NAME


def _checkpoint_dirs(processing: Path) -> list[Path]:
    """Existing checkpoints, oldest first — directory names are
    "<unix-ms-timestamp>-<label>" so lexicographic sort is also
    chronological sort, no need to parse/stat each one."""

    undo_dir = _undo_dir(processing)

    if not undo_dir.exists():
        return []

    return sorted(d for d in undo_dir.iterdir() if d.is_dir())


def _prune_to_limit(processing: Path):
    dirs = _checkpoint_dirs(processing)

    excess = len(dirs) - UNDO_HISTORY_LIMIT

    for old_dir in dirs[:max(0, excess)]:
        shutil.rmtree(old_dir, ignore_errors=True)


def save_checkpoint(processing: Path, files: list[Path], label: str):
    """Snapshots whichever of `files` currently exist into a new
    checkpoint directory, before the caller goes on to overwrite them.
    Call this BEFORE the write, inside the same episode_lock the write
    itself already holds — see wrap_with_checkpoint below, which is what
    every write endpoint actually uses; this function is the primitive it
    wraps. A no-op (no checkpoint written) if none of `files` currently
    exist, since there is nothing meaningful to restore to.

    Every path in `files` is recorded in the manifest, not just the ones
    that existed — a file the write is about to CREATE (e.g. moments.json
    on an episode's first-ever moment edit) has "existed": false and no
    snapshot, so restore_latest knows to delete it on undo rather than
    leaving it behind. Restoring only the files that had prior content
    while silently leaving a newly-created file in place would let that
    file's own next save path resurrect the "undone" state — the same
    #33 bug class this whole module exists to avoid, just via a file that
    didn't exist yet instead of one that did."""

    existing = [f for f in files if f.exists()]
    missing = [f for f in files if not f.exists()]

    if not existing:
        return

    undo_dir = _undo_dir(processing)
    checkpoint_dir = undo_dir / f"{int(time.time() * 1000)}-{_sanitize_for_dirname(label)}"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"label": label, "files": []}

    for f in existing:
        # Relative to `processing`, not absolute — restore_latest resolves
        # this back against whatever `processing` it's given, so the same
        # checkpoint format works regardless of the episode's absolute
        # path (e.g. an episode folder later moved/renamed on disk).
        relative = f.relative_to(processing)
        snapshot_path = checkpoint_dir / relative.name
        shutil.copy2(f, snapshot_path)
        manifest["files"].append({"relative": str(relative), "snapshot": snapshot_path.name, "existed": True})

    for f in missing:
        manifest["files"].append({"relative": str(f.relative_to(processing)), "snapshot": None, "existed": False})

    with (checkpoint_dir / "manifest.json").open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    _prune_to_limit(processing)


def wrap_with_checkpoint(processing: Path, files: list[Path], label: str, write_fn):
    """Snapshots `files`, then calls write_fn() — the checkpoint is saved
    unconditionally before the write attempt (not only on success), same
    as a normal "back up before touching it" discipline: if write_fn
    itself raises partway through writing multiple files, the checkpoint
    still reflects the true pre-write state to restore to, rather than a
    checkpoint that's silently skipped and leaves nothing to undo a
    partial write with."""

    save_checkpoint(processing, files, label)
    return write_fn()


def restore_latest(processing: Path) -> dict | None:
    """Pops (restores and deletes) the most recent checkpoint. Returns the
    checkpoint's manifest (label + which files were restored) or None if
    there's no history to undo — callers treat None as a no-op, not an
    error, since "nothing to undo yet" is a normal state, not a failure."""

    dirs = _checkpoint_dirs(processing)

    if not dirs:
        return None

    latest = dirs[-1]

    with (latest / "manifest.json").open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    for entry in manifest["files"]:
        target = processing / entry["relative"]

        if entry["existed"]:
            snapshot = latest / entry["snapshot"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot, target)
        else:
            # The write created this file where none existed before —
            # undo means it goes back to not existing, not "restored to
            # empty" or left alone (see save_checkpoint's own docstring
            # for why leaving it would silently defeat the undo).
            target.unlink(missing_ok=True)

    shutil.rmtree(latest, ignore_errors=True)

    return manifest
