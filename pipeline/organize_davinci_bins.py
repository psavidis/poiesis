#!/usr/bin/env python3

"""Sorts a DaVinci Resolve project's media pool into per-element-type bins
after importing export_davinci.py's timeline.otio (File -> Import Timeline
-> OpenTimelineIO).

Why this is a separate script, not part of export_davinci.py: DaVinci
Resolve's OTIO importer has no mechanism for a .otio file to specify bin/
folder structure — confirmed against Resolve's own OTIO-import docs and
independent write-ups, none of which describe any bin-driving construct
in the OTIO schema, and one explicitly notes Resolve doesn't even preserve
OTIO *track names* on import ("Video 1", "Audio 1", not our "Video —
Titles" etc.). Every clip lands in whatever bin is active at import time
(the root "Master" bin by default) regardless of what track it came from.
The only way to organize the media pool afterward is Resolve's own Python
Scripting API, run from INSIDE Resolve (Workspace -> Console -> Py3, or
Resolve's own external-script mechanism) — this file is written to be run
that way, not from a normal terminal.

Requires DaVinci Resolve Studio (the scripting API is a Studio-only
feature; the free edition can still import the OTIO, just not run this).

Usage (inside Resolve's Py3 console, after importing timeline.otio and
with that project open):

    exec(open("/path/to/poiesis/pipeline/organize_davinci_bins.py").read())

or, if Resolve's environment has this file's directory on sys.path:

    import organize_davinci_bins
    organize_davinci_bins.organize_active_project()
"""

import re


# Mirrors export_davinci.py's clip filename convention exactly
# (f"{scene_type}-{scene['id']}.mov" / f"presenter-{scene['id']}.mov") —
# the prefix before the first "-" is the scene type, which is also the bin
# this clip belongs in. Kept in sync by hand rather than importing
# export_davinci.py's OVERLAY_TRACK_TYPES, since this script runs inside
# Resolve's embedded Python (a different interpreter/environment than the
# one export_davinci.py runs in — no guarantee Poiesis's own pipeline
# package is importable there). "caption" and "image" are deliberately
# absent — captions are exported as a native captions.srt file (see
# build_srt) and images are placed as their real source media on their own
# OTIO track (see add_native_asset_track), neither ever rendered as a
# clip, so no caption-*.mov/image-*.mov filename is ever produced for this
# to bin.
BIN_NAMES = {
    "presenter": "Presenter",
    "title": "Titles",
    "moment": "Moments",
    "beat": "Beats",
}

CLIP_FILENAME_PATTERN = re.compile(r"^(presenter|title|moment|beat)-")


def bin_name_for_clip(filename: str) -> str | None:
    """Which bin a rendered clip belongs in, from its filename alone —
    None if the filename doesn't match export_davinci.py's convention (a
    clip that isn't one of ours, e.g. something the user already had in
    this project before importing). Pure function, no Resolve API calls,
    so this is unit-testable without a running Resolve instance."""

    match = CLIP_FILENAME_PATTERN.match(filename)
    if not match:
        return None
    return BIN_NAMES[match.group(1)]


def group_clips_by_bin(clip_names: list[str]) -> dict[str, list[str]]:
    """clip_names: media pool item names/filenames. Returns {bin_name:
    [clip_name, ...]} for every clip that matches our naming convention —
    clips that don't match (not ours) are silently omitted, not grouped
    under some catch-all bin, since this script should never move media
    the user didn't get from export_davinci.py."""

    grouped: dict[str, list[str]] = {}

    for name in clip_names:
        bin_name = bin_name_for_clip(name)
        if bin_name is None:
            continue
        grouped.setdefault(bin_name, []).append(name)

    return grouped


def organize_active_project(resolve=None):
    """Finds every clip export_davinci.py rendered (by filename
    convention) in the currently open Resolve project's root media-pool
    folder, creates one subfolder per element type (Presenter/Titles/
    Captions/Moments/Images/Beats — only for types actually present, same
    "skip empty" behavior as export_davinci.py's per-type tracks), and
    moves each clip into its subfolder. Clips already sitting in a
    non-root folder (e.g. a second run against the same project) are left
    alone — GetRootFolder().GetClipList() only sees root-level clips, so
    a clip already sorted into a bin from a prior run of this script isn't
    touched again.

    `resolve` is normally omitted — Resolve's Python console injects a
    global `resolve` object into whatever script it runs, so this reads
    that global by default. Accepting it as a parameter (rather than only
    reading the global) is what makes this testable: tests pass a fake
    object with the same GetProjectManager()/GetMediaPool() shape instead
    of needing a real Resolve process."""

    if resolve is None:
        resolve = globals().get("resolve")
    if resolve is None:
        raise RuntimeError(
            "No Resolve connection available — run this from inside "
            "DaVinci Resolve's Python console (Workspace -> Console -> "
            "Py3), where Resolve injects a `resolve` global automatically."
        )

    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject()
    if project is None:
        raise RuntimeError("No project is currently open in Resolve.")

    media_pool = project.GetMediaPool()
    root_folder = media_pool.GetRootFolder()

    clips = root_folder.GetClipList()
    clip_names = [clip.GetName() for clip in clips]

    grouped = group_clips_by_bin(clip_names)

    if not grouped:
        print(
            "No clips matching export_davinci.py's naming convention "
            "found in the root bin — nothing to organize. Did you import "
            "timeline.otio into this project yet?"
        )
        return

    clips_by_name = {clip.GetName(): clip for clip in clips}
    existing_subfolders = {f.GetName(): f for f in root_folder.GetSubFolderList()}

    for bin_name, names_in_bin in grouped.items():
        target_folder = existing_subfolders.get(bin_name)
        if target_folder is None:
            target_folder = media_pool.AddSubFolder(root_folder, bin_name)
            existing_subfolders[bin_name] = target_folder

        clip_objects = [clips_by_name[name] for name in names_in_bin]
        media_pool.MoveClips(clip_objects, target_folder)

        print(f"Moved {len(clip_objects)} clip(s) into bin '{bin_name}'")


if __name__ == "__main__":
    organize_active_project()
