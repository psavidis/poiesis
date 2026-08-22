#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_footage import generate_episode_props_ts, get_video_metadata, load_backgrounds_for_codegen


IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
}

# Animated graphics (e.g. a logo/bumper animation, possibly alpha-
# transparent) placed in graphics/ alongside images — indexed the same way,
# just tagged with mediaType "video" so the renderer knows to mount an
# <OffthreadVideo> instead of an <Img> for that asset (see Episode.tsx /
# MomentTreatments.tsx / EpisodeImage.tsx). Not the same set as
# prepare_footage.py's VIDEO_EXTENSIONS: original_footage/ only ever holds
# camera output, so its list doesn't need webm; graphics/ is far more likely
# to hold an exported/alpha-encoded web-style asset.
VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".webm",
}

MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

IGNORED_FILES = {
    ".DS_Store",
    "Thumbs.db",
}

# Folder-as-authoring-hint (see docs/specs/content-types-and-presentation-
# editing.md's "Asset Folders as Authoring Metadata"): an image placed
# directly under one of these subfolder names hints that its initial
# presentation should default to Full Screen — a suggestion the AI
# (generate_moments.py) and the user can both override, never a permanent
# constraint. Kept as a small, explicit set (not a fuzzy match) rather than
# inferring intent from arbitrary folder names — an unrecognized subfolder
# name is just organizational to the user (no different from images nested
# for any other reason) and gets no hint, same as the flat-root case.
FULL_SCREEN_HINT_FOLDERS = {"full-screen", "full"}


def default_display_hint(file: Path, graphics_dir: Path) -> str | None:
    """The hint is read from the file's immediate parent folder name,
    relative to graphics/ — graphics/full-screen/x.png hints "full",
    graphics/full-screen/nested/x.png does NOT (nested is the immediate
    parent, not full-screen), and graphics/x.png (flat root, today's only
    existing convention) hints nothing. Only one level deep is
    intentional: this is meant to read as "this image lives in the
    full-screen bucket," not to walk an arbitrary folder hierarchy
    guessing intent from any ancestor."""

    relative = file.relative_to(graphics_dir)

    if len(relative.parts) < 2:
        return None

    immediate_parent = relative.parts[-2]

    if immediate_parent in FULL_SCREEN_HINT_FOLDERS:
        return "full"

    return None


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# Reference key colors for chroma/luma keying a video asset's background —
# see Episode.tsx's KEY_COLOR_FILTERS (rendering) and detect_key_color below
# (detection). Only the two most common static-background colors creators
# actually export animated graphics against (per the user) — not an
# open-ended palette, since each one needs its own hand-tuned SVG filter on
# the rendering side, not just a detection rule here.
KEY_COLOR_BLACK = (0, 0, 0)
KEY_COLOR_GREEN = (0, 177, 64)  # a common "chroma key green" reference

# How close a sampled corner's average color must be to a reference key
# color (per-channel, out of 255) to count as a match — loose enough to
# absorb compression artifacts and slight export variance, tight enough
# that a genuinely colorful/bright graphic corner won't false-positive.
KEY_COLOR_TOLERANCE = 40


def _color_distance(a, b):
    return max(abs(a[i] - b[i]) for i in range(3))


# How many samples down a thin center-frame strip _sample_column looks at
# to find letterbox bars — coarse enough to be cheap, fine enough that a
# thin bar isn't missed entirely.
LETTERBOX_SCAN_SAMPLES = 64

# A run of at least this many consecutive near-black samples from an edge
# counts as a letterbox bar, not just a coincidentally dark few pixels of
# real content (e.g. a dark hairline at the very top of a frame).
LETTERBOX_MIN_RUN_FRACTION = 0.05  # 5% of the frame's dimension


def _sample_column(video_path: Path, width: int, height: int):
    """A thin (4px) vertical strip down the frame's horizontal center,
    downsampled to LETTERBOX_SCAN_SAMPLES points top-to-bottom — used to
    find where real content starts/ends vertically (see
    _trim_letterbox_bounds). Returns None on any ffmpeg failure."""

    strip_width = min(4, width)
    x = max(0, width // 2 - strip_width // 2)

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", f"crop={strip_width}:{height}:{x}:0,scale=1:{LETTERBOX_SCAN_SAMPLES}",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-",
        ],
        capture_output=True,
    )

    expected_bytes = LETTERBOX_SCAN_SAMPLES * 3

    if result.returncode != 0 or len(result.stdout) != expected_bytes:
        return None

    return [tuple(result.stdout[i:i + 3]) for i in range(0, expected_bytes, 3)]


def _trim_letterbox_bounds(video_path: Path, width: int, height: int):
    """Finds the real content's vertical bounds by scanning a center strip
    for a run of near-black samples at the top and/or bottom — a classic
    letterbox signature (padding added to fit an aspect ratio, unrelated to
    whatever the actual content's background color is). Returns (top,
    bottom) as fractions of height, e.g. (0.0, 1.0) when no letterbox is
    detected — the corner-sampling in detect_key_color then samples INSIDE
    these bounds instead of the raw frame, so a letterboxed presenter shot
    (real background: white) doesn't get corner-sampled from the padding
    bars (black) and misclassified as a black-keyed graphic. Only checks
    top/bottom (letterboxing), not left/right (pillarboxing) — every camera
    export this pipeline has seen so far pads vertically, never
    horizontally; add a symmetric horizontal scan if that ever changes."""

    column = _sample_column(video_path, width, height)

    if column is None:
        return 0.0, 1.0

    min_run = max(1, int(len(column) * LETTERBOX_MIN_RUN_FRACTION))

    top_run = 0
    for sample in column:
        if _color_distance(sample, KEY_COLOR_BLACK) > KEY_COLOR_TOLERANCE:
            break
        top_run += 1

    bottom_run = 0
    for sample in reversed(column):
        if _color_distance(sample, KEY_COLOR_BLACK) > KEY_COLOR_TOLERANCE:
            break
        bottom_run += 1

    top_fraction = (top_run / len(column)) if top_run >= min_run else 0.0
    bottom_fraction = (bottom_run / len(column)) if bottom_run >= min_run else 0.0

    # A video that's entirely near-black top-to-bottom (top_run == full
    # column) is a genuine flat-black background, not letterboxing with
    # nothing in between — leave bounds untrimmed so detect_key_color still
    # samples (and correctly matches) the real content.
    if top_run >= len(column):
        return 0.0, 1.0

    return top_fraction, 1.0 - bottom_fraction


def detect_key_color(video_path: Path):
    """Classifies a video's background as "black", "green", or None (no
    match — either a genuinely varied/bright corner, or real alpha already,
    or ffmpeg couldn't sample it) by averaging four corners of the CONTENT
    area (see _trim_letterbox_bounds — excludes any letterbox padding
    first) and comparing each against the two known key colors. Requires
    ALL FOUR corners to agree, not just one — a graphic with a colored logo
    mark tucked into one corner (top-left, say) but a plain black
    background everywhere else should still classify as "black", but a
    genuinely multi-colored/photographic video (no consistent flat
    background at all) should classify as None rather than keying based on
    a single lucky corner."""

    try:
        metadata = get_video_metadata(video_path)
    except (subprocess.CalledProcessError, KeyError, StopIteration):
        return None

    width, height = metadata["width"], metadata["height"]

    top_fraction, bottom_fraction = _trim_letterbox_bounds(video_path, width, height)
    content_top = int(height * top_fraction)
    content_bottom = int(height * bottom_fraction)
    content_height = max(1, content_bottom - content_top)

    crop_size = max(4, min(20, width // 8, content_height // 8))

    corners = [
        (0, content_top),
        (max(0, width - crop_size), content_top),
        (0, max(content_top, content_bottom - crop_size)),
        (max(0, width - crop_size), max(content_top, content_bottom - crop_size)),
    ]

    samples = []

    for x, y in corners:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", f"crop={crop_size}:{crop_size}:{x}:{y},scale=1:1",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-",
            ],
            capture_output=True,
        )

        if result.returncode != 0 or len(result.stdout) != 3:
            return None

        samples.append(tuple(result.stdout))

    for name, reference in (("black", KEY_COLOR_BLACK), ("green", KEY_COLOR_GREEN)):
        if all(_color_distance(sample, reference) <= KEY_COLOR_TOLERANCE for sample in samples):
            return name

    return None


def write_json_atomic(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix(".tmp.json")

    try:
        with temp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        temp.replace(path)

    finally:
        if temp.exists():
            temp.unlink()


def caption_from_filename(filename):

    stem = Path(filename).stem

    words = re.sub(r"[_\-]+", " ", stem)
    words = re.sub(r"[^a-zA-Z0-9 ]", " ", words)
    words = re.sub(r"\s+", " ", words).strip()

    return words


def list_asset_files(graphics_dir: Path):
    """Recursive (rglob), matching index_code.py's list_code_files —
    subfolders under graphics/ are meaningful both for plain organization
    (a user grouping related images together) and, for FULL_SCREEN_HINT_FOLDERS
    specifically, as a presentation hint (see default_display_hint above).
    A flat graphics/ folder (no subfolders — every existing real episode's
    convention as of this change) indexes identically to the old
    non-recursive iterdir() scan, since rglob("*") includes the root's own
    direct children."""

    if not graphics_dir.exists():
        return []

    files = sorted(
        f
        for f in graphics_dir.rglob("*")
        if f.is_file()
           and f.name not in IGNORED_FILES
           and f.suffix.lower() in MEDIA_EXTENSIONS
    )

    return files


def index_assets(episode: Path):

    graphics_dir = episode / "graphics"
    processing = episode / "processing"
    output_path = processing / "assets.json"

    existing_captions = {}
    # Keyed by filename, not recomputed positionally — an asset's id used
    # to be purely positional (see next_index_by_media_type below), so
    # deleting or adding any OTHER file of the same media type shifted
    # every later id and silently reattached an existing id (and thus, via
    # moments.json's own assetId, a moment's rendered image) to a
    # different file (see #80's real-world case for the equivalent
    # backgrounds bug, and #93's own delete feature, which would trigger
    # this on every delete of a non-last file). Same "keyed by filename,
    # never by position" fix already applied to backgrounds
    # (index_backgrounds.py) — reused here for the id itself, not just
    # the caption.
    existing_ids_by_filename = {}

    if output_path.exists():

        existing = load_json(output_path)

        # Keyed by filename, not id — see existing_ids_by_filename above
        # for why (see #80's real-world case: removing one video file
        # shifted every later id by one, and the previous asset's caption
        # followed the id, not the file).
        for asset in existing.get("assets", []):
            existing_captions[asset["filename"]] = asset["caption"]
            existing_ids_by_filename[asset["filename"]] = asset["id"]

    files = list_asset_files(graphics_dir)

    assets = []

    # Separate id sequences per media type ("img-001", "vid-001", ...) —
    # not one running index across both — so adding/removing a video never
    # renumbers (and thus never re-anchors, since ids are what moments.json
    # references) an existing image's id, and vice versa. Seeded from the
    # highest number already in use for each type (not always 1), so a
    # freshly added file gets a number that's never been used before
    # rather than reusing one an existing (possibly reordered) file still
    # holds.
    next_index_by_media_type = {"image": 1, "video": 1}
    for prefix, media_type in (("img", "image"), ("vid", "video")):
        used_numbers = [
            int(match.group(1))
            for existing_id in existing_ids_by_filename.values()
            if (match := re.match(rf"^{prefix}-(\d+)$", existing_id))
        ]
        if used_numbers:
            next_index_by_media_type[media_type] = max(used_numbers) + 1

    for file in files:

        is_video = file.suffix.lower() in VIDEO_EXTENSIONS
        media_type = "video" if is_video else "image"
        id_prefix = "vid" if is_video else "img"

        existing_id = existing_ids_by_filename.get(file.name)

        if existing_id and re.match(rf"^{id_prefix}-\d+$", existing_id):
            asset_id = existing_id
        else:
            asset_id = f"{id_prefix}-{next_index_by_media_type[media_type]:03d}"
            next_index_by_media_type[media_type] += 1

        caption = existing_captions.get(
            file.name,
            caption_from_filename(file.name)
        )

        asset = {
            "id": asset_id,
            "filename": file.name,
            "path": str(file.relative_to(episode)),
            "renderPath": str(Path("episodes") / episode.name / "graphics" / file.relative_to(graphics_dir)),
            "caption": caption,
            "mediaType": media_type,
        }

        if is_video:
            key_color = detect_key_color(file)
            if key_color:
                asset["keyColor"] = key_color

        hint = default_display_hint(file, graphics_dir)

        if hint:
            asset["defaultDisplay"] = hint

        assets.append(asset)

    write_json_atomic(output_path, {"assets": assets})

    return assets


def main():

    parser = argparse.ArgumentParser(
        description="Index episode graphics/ folder into an asset manifest"
    )

    parser.add_argument("episode_folder")

    args = parser.parse_args()

    episode = Path(args.episode_folder).resolve()

    assets = index_assets(episode)

    print(f"Indexed {len(assets)} asset(s).")

    for asset in assets:
        print(f"  [{asset['id']}] {asset['filename']}: {asset['caption']}")

    manifest_path = episode / "processing" / "manifest.json"

    if manifest_path.exists():

        project_root = Path(__file__).resolve().parent.parent
        renderer_folder = project_root / "video-renderer"

        manifest = load_json(manifest_path)

        code_assets_path = episode / "processing" / "code_assets.json"
        code_assets = load_json(code_assets_path)["codeAssets"] if code_assets_path.exists() else []

        generate_episode_props_ts(
            manifest,
            renderer_folder,
            assets=assets,
            code_assets=code_assets,
            backgrounds=load_backgrounds_for_codegen(episode)
        )


if __name__ == "__main__":
    main()
