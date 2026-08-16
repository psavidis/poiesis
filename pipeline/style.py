import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"

# Falls back to these if config.json has no "style" section (or is missing
# a specific key) — keeps every call site working on a repo checkout that
# predates this file, rather than raising a KeyError mid-pipeline.
DEFAULTS = {
    "monotonyThresholdSeconds": 18.0,
    "moments": {
        "maxPer1000Frames": 1,
        "durationFrames": {
            "bottomCallout": 90,
            "sideText": 150,
            "sideImage": 150,
            "sideCode": 240,
            "sideDiagram": 180,
            # A stack of several staggered-reveal terms needs enough time
            # for the last one to finish revealing and still be readable —
            # closer to sideDiagram's reveal-heavy duration than a single
            # static phrase.
            "sideTerms": 180,
            # Two short flanking labels, comparable read time to a single
            # sideText phrase — the presenter doesn't move for this one, so
            # there's no slide-aside animation eating into the window.
            "comparison": 150,
            "fullVisual": 300,
            # Same read-time budget as sideCode (#48's "content-dominant-code"
            # is the same content at a larger, more prominent scale, not a
            # different amount of code to read) — not fullVisual's longer
            # window, since the presenter stays visible here rather than
            # hidden, so there's less pressure to linger than a true
            # full-visual moment.
            "contentDominantCode": 240,
        },
        # A full-visual moment hides the presenter entirely, so it should
        # be noticeably rarer than the side treatments (which keep the
        # presenter on screen) — expressed as a ratio of already-kept side
        # moments rather than its own absolute density cap, so it scales
        # naturally with however many side moments an episode ends up
        # with. See propose_moments's full-visual cap.
        "fullVisualMaxRatioToSideMoments": 0.25,
    },
    "titles": {
        "minSpacingSeconds": 20,
        "durationFrames": 60,
    },
    "emphasis": {
        # Beats are meant to be a constant light rhythm, much more frequent
        # than moments (which are gated by an 18s monotony threshold) — this
        # is a minimum spacing floor per presenter scene, not a density cap
        # tied to total episode length, since a beat's value comes from
        # firing on the actual words worth emphasizing, not from hitting a
        # target count.
        "minSecondsBetweenBeats": 4.0,
        # 2s at 30fps (was 24 = 0.8s) — the original value left only ~0.63s
        # actually held at full opacity after BeatOverlay.tsx's fade
        # in/out, not enough time to read a 2-3 word phrase and connect it
        # to what's being said (see #37). Well under minSecondsBetweenBeats
        # above, so beats still never run into each other.
        "defaultDurationFrames": 60,
    },
}


def _merged(defaults, overrides):
    if not isinstance(overrides, dict):
        return defaults

    merged = dict(defaults)

    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(defaults.get(key), dict):
            merged[key] = _merged(defaults[key], value)
        else:
            merged[key] = value

    return merged


def load_style(config_path: Path = CONFIG_PATH):
    """Loads the "style" section of config.json, merged over DEFAULTS so a
    config file missing the section entirely (or missing individual keys
    within it) still yields a complete, usable dict. This is the single
    source of pacing/density/duration knobs referenced across
    visual_placement.py, generate_moments.py, and generate_title_scenes.py
    — editing config.json's "style" section is the intended way to retune
    the channel's pacing without touching Python."""

    if not config_path.exists():
        return dict(DEFAULTS)

    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    return _merged(DEFAULTS, config.get("style"))
