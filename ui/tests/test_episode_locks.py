from pathlib import Path

import pytest

from episode_locks import EpisodeBusyError, episode_lock, is_episode_locked


def test_episode_lock_allows_sequential_use(tmp_path):
    episode = tmp_path / "My Episode"

    with episode_lock(episode):
        pass

    # lock was released after the first `with` — a second one should not
    # raise even with wait=False
    with episode_lock(episode, wait=False):
        pass


def test_episode_lock_wait_false_raises_when_already_held(tmp_path):
    episode = tmp_path / "My Episode"

    with episode_lock(episode):
        with pytest.raises(EpisodeBusyError):
            with episode_lock(episode, wait=False):
                pass


def test_episode_lock_different_episodes_do_not_contend(tmp_path):
    episode_a = tmp_path / "Episode A"
    episode_b = tmp_path / "Episode B"

    with episode_lock(episode_a):
        # a different episode's lock must be free even though A's is held
        with episode_lock(episode_b, wait=False):
            pass


def test_episode_lock_releases_on_exception(tmp_path):
    episode = tmp_path / "My Episode"

    with pytest.raises(ValueError):
        with episode_lock(episode):
            raise ValueError("boom")

    # lock must have been released despite the exception
    with episode_lock(episode, wait=False):
        pass


def test_episode_lock_same_episode_different_path_objects_share_a_lock(tmp_path):
    # two different Path objects pointing at the same resolved location
    # must contend for the same lock — the lock keys off str(episode), not
    # object identity
    episode_a = Path(str(tmp_path / "My Episode"))
    episode_b = Path(str(tmp_path / "My Episode"))

    with episode_lock(episode_a):
        with pytest.raises(EpisodeBusyError):
            with episode_lock(episode_b, wait=False):
                pass


def test_episode_busy_error_message_includes_episode_name(tmp_path):
    episode = tmp_path / "My Episode"

    with episode_lock(episode):
        try:
            with episode_lock(episode, wait=False):
                pass
        except EpisodeBusyError as e:
            assert "My Episode" in str(e)


def test_is_episode_locked_false_when_unlocked(tmp_path):
    episode = tmp_path / "My Episode"

    assert is_episode_locked(episode) is False


def test_is_episode_locked_true_while_held(tmp_path):
    episode = tmp_path / "My Episode"

    with episode_lock(episode):
        assert is_episode_locked(episode) is True


def test_is_episode_locked_false_again_after_release(tmp_path):
    episode = tmp_path / "My Episode"

    with episode_lock(episode):
        pass

    assert is_episode_locked(episode) is False


def test_is_episode_locked_does_not_itself_hold_the_lock(tmp_path):
    # A peek must not leave the lock acquired — otherwise checking status
    # would itself make every subsequent operation see the episode as busy.
    episode = tmp_path / "My Episode"

    is_episode_locked(episode)

    with episode_lock(episode, wait=False):
        pass


def test_is_episode_locked_different_episodes_are_independent(tmp_path):
    episode_a = tmp_path / "Episode A"
    episode_b = tmp_path / "Episode B"

    with episode_lock(episode_a):
        assert is_episode_locked(episode_a) is True
        assert is_episode_locked(episode_b) is False
