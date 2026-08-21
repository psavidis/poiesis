from style import load_style


def find_monotony_eligible_windows(scene_plan, threshold_seconds=None):
    """Find timeline windows where too long has passed since the last visual
    change (title/emphasis scene), within presenter scenes only.

    Returns a list of dicts: sceneId (the parent presenter scene), videoId,
    offsetInParentFrames (start of the eligible range, relative to the
    parent scene's own start), maxDurationInParentFrames (how much room is
    left in the parent scene from that offset to its end) — both expressed
    relative to the parent scene, not as absolute timeline frames, so
    overlays built from this stay correctly positioned if the parent scene
    later moves — plus sourceStartFrame, sourceEndFrame.
    """

    if threshold_seconds is None:
        threshold_seconds = load_style()["monotonyThresholdSeconds"]

    fps = scene_plan["fps"]
    threshold_frames = threshold_seconds * fps

    # Only scenes with an absolute timelineStartFrame (presenter/title) can
    # be sorted this way — overlay scenes (moment/caption/image) position
    # themselves relative to a parent via offsetInParentFrames and have no
    # such field. Filtering here (rather than assuming the plan never has
    # overlays yet) keeps this safe to call on a --force re-run against an
    # already-processed scene-plan.json, not just a freshly-analyzed one.
    scenes = sorted(
        (s for s in scene_plan["scenes"] if "timelineStartFrame" in s),
        key=lambda s: s["timelineStartFrame"]
    )

    windows = []

    frames_since_change = 0

    for scene in scenes:

        if scene["type"] != "presenter":
            frames_since_change = 0
            continue

        crosses_threshold = (
            frames_since_change + scene["durationInFrames"] >= threshold_frames
        )

        if crosses_threshold:

            eligible_start = max(0, threshold_frames - frames_since_change)

            windows.append(
                {
                    "sceneId": scene["id"],
                    "videoId": scene["videoId"],
                    "offsetInParentFrames": eligible_start,
                    "maxDurationInParentFrames": scene["durationInFrames"] - eligible_start,
                    "sourceStartFrame": scene["sourceStartFrame"] + eligible_start,
                    "sourceEndFrame": scene["sourceEndFrame"],
                }
            )

            # An overlay was flagged as eligible within this scene; treat
            # this as a visual change going forward so later scenes don't
            # keep compounding the same monotony debt indefinitely.
            frames_since_change = 0

        else:
            frames_since_change += scene["durationInFrames"]

    return windows


def source_frame_to_seconds(frame, fps):
    return frame / fps


def filter_segments_in_window(segments, window, fps):
    """Return transcript segments (clip-native seconds) whose start falls
    within the eligible source-frame window."""

    start_seconds = source_frame_to_seconds(window["sourceStartFrame"], fps)
    end_seconds = source_frame_to_seconds(window["sourceEndFrame"], fps)

    return [
        segment
        for segment in segments
        if start_seconds <= segment["start"] < end_seconds
    ]
