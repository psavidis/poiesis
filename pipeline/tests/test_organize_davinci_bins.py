import pytest

from organize_davinci_bins import (
    BIN_NAMES,
    bin_name_for_clip,
    group_clips_by_bin,
    organize_active_project,
)


def test_bin_name_for_clip_matches_each_known_prefix():
    for scene_type, bin_name in BIN_NAMES.items():
        assert bin_name_for_clip(f"{scene_type}-scene-042.mov") == bin_name


def test_bin_name_for_clip_returns_none_for_unrecognized_filename():
    assert bin_name_for_clip("some-random-clip.mov") is None
    assert bin_name_for_clip("intro.mp4") is None


def test_group_clips_by_bin_groups_matching_clips_together():
    grouped = group_clips_by_bin(
        [
            "presenter-scene-001.mov",
            "presenter-scene-002.mov",
            "title-scene-title-000.mov",
            "caption-scene-caption-5.mov",
        ]
    )

    assert grouped == {
        "Presenter": ["presenter-scene-001.mov", "presenter-scene-002.mov"],
        "Titles": ["title-scene-title-000.mov"],
        "Captions": ["caption-scene-caption-5.mov"],
    }


def test_group_clips_by_bin_omits_unrecognized_clips():
    grouped = group_clips_by_bin(["presenter-scene-001.mov", "not-ours.mov"])

    assert grouped == {"Presenter": ["presenter-scene-001.mov"]}
    assert "not-ours.mov" not in [name for names in grouped.values() for name in names]


def test_group_clips_by_bin_empty_input_returns_empty_dict():
    assert group_clips_by_bin([]) == {}


class FakeClip:
    def __init__(self, name):
        self._name = name

    def GetName(self):
        return self._name


class FakeFolder:
    def __init__(self, name="Master"):
        self.name = name
        self.clips = []
        self.subfolders = []

    def GetClipList(self):
        return list(self.clips)

    def GetSubFolderList(self):
        return list(self.subfolders)

    def GetName(self):
        return self.name


class FakeMediaPool:
    def __init__(self, root_folder):
        self._root_folder = root_folder
        self.moves = []  # [(target_folder_name, [clip_names])]

    def GetRootFolder(self):
        return self._root_folder

    def AddSubFolder(self, parent, name):
        folder = FakeFolder(name)
        parent.subfolders.append(folder)
        return folder

    def MoveClips(self, clips, target_folder):
        self.moves.append((target_folder.GetName(), [c.GetName() for c in clips]))
        for clip in clips:
            if clip in self._root_folder.clips:
                self._root_folder.clips.remove(clip)


class FakeProject:
    def __init__(self, media_pool):
        self._media_pool = media_pool

    def GetMediaPool(self):
        return self._media_pool


class FakeProjectManager:
    def __init__(self, project):
        self._project = project

    def GetCurrentProject(self):
        return self._project


class FakeResolve:
    def __init__(self, project_manager):
        self._project_manager = project_manager

    def GetProjectManager(self):
        return self._project_manager


def _make_fake_resolve(clip_names, project=True):
    root_folder = FakeFolder()
    root_folder.clips = [FakeClip(name) for name in clip_names]
    media_pool = FakeMediaPool(root_folder)
    fake_project = FakeProject(media_pool) if project else None
    project_manager = FakeProjectManager(fake_project)
    return FakeResolve(project_manager), media_pool, root_folder


def test_organize_active_project_moves_clips_into_new_bins():
    resolve, media_pool, root_folder = _make_fake_resolve(
        [
            "presenter-scene-001.mov",
            "presenter-scene-002.mov",
            "title-scene-title-000.mov",
        ]
    )

    organize_active_project(resolve)

    assert len(root_folder.subfolders) == 2
    subfolder_names = {f.GetName() for f in root_folder.subfolders}
    assert subfolder_names == {"Presenter", "Titles"}

    moves_by_bin = dict(media_pool.moves)
    assert set(moves_by_bin["Presenter"]) == {"presenter-scene-001.mov", "presenter-scene-002.mov"}
    assert moves_by_bin["Titles"] == ["title-scene-title-000.mov"]


def test_organize_active_project_reuses_existing_subfolder_on_second_run():
    resolve, media_pool, root_folder = _make_fake_resolve(["presenter-scene-001.mov"])

    organize_active_project(resolve)
    assert len(root_folder.subfolders) == 1

    # Simulate a second import cycle adding one more presenter clip to the
    # root bin — the already-sorted clip from the first run is gone from
    # root_folder.clips (MoveClips removed it), so only the new one should
    # be regrouped, into the SAME "Presenter" folder rather than a
    # duplicate.
    root_folder.clips.append(FakeClip("presenter-scene-003.mov"))

    organize_active_project(resolve)

    assert len(root_folder.subfolders) == 1
    presenter_folder = root_folder.subfolders[0]
    assert presenter_folder.GetName() == "Presenter"


def test_organize_active_project_ignores_clips_not_from_export_davinci():
    resolve, media_pool, root_folder = _make_fake_resolve(
        ["presenter-scene-001.mov", "some_other_media.mp4"]
    )

    organize_active_project(resolve)

    assert len(root_folder.subfolders) == 1
    assert root_folder.subfolders[0].GetName() == "Presenter"
    # The unrecognized clip is never moved, so it's still sitting in root.
    assert any(c.GetName() == "some_other_media.mp4" for c in root_folder.clips)


def test_organize_active_project_no_op_when_no_matching_clips():
    resolve, media_pool, root_folder = _make_fake_resolve(["random.mov"])

    organize_active_project(resolve)

    assert root_folder.subfolders == []
    assert media_pool.moves == []


def test_organize_active_project_raises_without_resolve_connection():
    with pytest.raises(RuntimeError, match="No Resolve connection"):
        organize_active_project(None)


def test_organize_active_project_raises_without_open_project():
    project_manager = FakeProjectManager(None)
    resolve = FakeResolve(project_manager)

    with pytest.raises(RuntimeError, match="No project is currently open"):
        organize_active_project(resolve)
