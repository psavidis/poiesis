"""Shared helpers for inserting overlay scenes (caption/moment/image) into
scene_plan["scenes"] at the correct chronological position, keeping the
list ordered by absolute timeline position even though overlay scenes only
carry a parent-relative offset."""


def absolute_position(scene, scenes_by_id):
    """Resolve a scene's absolute timelineStartFrame. Track scenes carry
    this directly; overlay scenes resolve it via their parent."""

    if "timelineStartFrame" in scene:
        return scene["timelineStartFrame"]

    parent = scenes_by_id[scene["parentSceneId"]]

    return parent["timelineStartFrame"] + scene["offsetInParentFrames"]


def insert_overlay_scene(merged_scenes, scenes_by_id, overlay_scene, absolute_position_value):

    insert_at = len(merged_scenes)

    for i, scene in enumerate(merged_scenes):
        if absolute_position(scene, scenes_by_id) > absolute_position_value:
            insert_at = i
            break

    merged_scenes.insert(insert_at, overlay_scene)
