"""
Tests for the held-out validation split added to lerobot-train.

Covers the three pieces that can break independently: the episode split
(`resolve_train_val_episodes`), the config validation on `val_episodes`, and the validation pass
itself (`validate_policy`). No dataset, GPU or policy is needed — the pass is exercised with a
fake policy and a hand-built dataloader.
"""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import torch


def _cfg(episodes=None, val_episodes=None):
    """A stand-in for TrainPipelineConfig with only the fields the split reads."""
    return SimpleNamespace(
        dataset=SimpleNamespace(
            repo_id="user/ds",
            root=None,
            revision=None,
            episodes=episodes,
            val_episodes=val_episodes,
        )
    )


# ---------------------------------------------------------------------------
# 1.  resolve_train_val_episodes
# ---------------------------------------------------------------------------


class TestResolveTrainValEpisodes:
    def test_no_val_episodes_passes_config_through(self):
        from lerobot.datasets.factory import resolve_train_val_episodes

        train, val = resolve_train_val_episodes(_cfg(episodes=[0, 1, 2]))
        assert train == [0, 1, 2]
        assert val is None

    def test_val_episodes_are_removed_from_training(self):
        from lerobot.datasets.factory import resolve_train_val_episodes

        train, val = resolve_train_val_episodes(_cfg(episodes=list(range(5)), val_episodes=[3, 4]))
        assert train == [0, 1, 2]
        assert val == [3, 4]

    def test_splits_against_full_dataset_when_no_episode_selection(self):
        from lerobot.datasets.factory import resolve_train_val_episodes

        with patch(
            "lerobot.datasets.factory.LeRobotDatasetMetadata",
            return_value=SimpleNamespace(total_episodes=50),
        ):
            train, val = resolve_train_val_episodes(_cfg(val_episodes=list(range(40, 50))))

        assert train == list(range(40))
        assert val == list(range(40, 50))

    def test_val_episode_outside_dataset_raises(self):
        from lerobot.datasets.factory import resolve_train_val_episodes

        with patch(
            "lerobot.datasets.factory.LeRobotDatasetMetadata",
            return_value=SimpleNamespace(total_episodes=5),
        ):
            with pytest.raises(ValueError, match="not present in the dataset"):
                resolve_train_val_episodes(_cfg(val_episodes=[4, 9]))

    def test_holding_out_every_episode_raises(self):
        from lerobot.datasets.factory import resolve_train_val_episodes

        with pytest.raises(ValueError, match="no episode to train on"):
            resolve_train_val_episodes(_cfg(episodes=[0, 1], val_episodes=[0, 1]))


# ---------------------------------------------------------------------------
# 2.  DatasetConfig / TrainPipelineConfig validation
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def test_val_episodes_defaults_to_none(self):
        from lerobot.configs.default import DatasetConfig

        assert DatasetConfig(repo_id="user/ds").val_episodes is None

    def test_duplicate_val_episodes_raise(self):
        from lerobot.configs.default import DatasetConfig

        with pytest.raises(ValueError, match="Validation episode indices contain duplicates"):
            DatasetConfig(repo_id="user/ds", val_episodes=[1, 1])

    def test_negative_val_episodes_raise(self):
        from lerobot.configs.default import DatasetConfig

        with pytest.raises(ValueError, match="Validation episode indices must be non-negative"):
            DatasetConfig(repo_id="user/ds", val_episodes=[-1])

    def test_val_episode_outside_episode_selection_raises(self):
        from lerobot.configs.default import DatasetConfig

        with pytest.raises(ValueError, match="val_episodes not present in episodes"):
            DatasetConfig(repo_id="user/ds", episodes=[0, 1], val_episodes=[2])

    def test_episode_indices_still_validated(self):
        from lerobot.configs.default import DatasetConfig

        with pytest.raises(ValueError, match="Episode indices must be non-negative"):
            DatasetConfig(repo_id="user/ds", episodes=[-3])

    def test_val_freq_defaults_to_disabled(self):
        from lerobot.configs.train import TrainPipelineConfig

        assert TrainPipelineConfig.__dataclass_fields__["val_freq"].default == 0


# ---------------------------------------------------------------------------
# 3.  validate_policy
# ---------------------------------------------------------------------------


class _FakePolicy:
    """Records the train/eval mode it was called in and returns scripted losses."""

    def __init__(self, losses: list[float]):
        self.training = True
        self._losses = losses
        self.seen_batches: list[dict] = []
        self.modes: list[bool] = []

    def eval(self):
        self.training = False

    def train(self):
        self.training = True

    def forward(self, batch):
        self.seen_batches.append(batch)
        self.modes.append(self.training)
        return torch.tensor(self._losses[len(self.seen_batches) - 1]), {}


def _fake_accelerator():
    return SimpleNamespace(autocast=nullcontext)


def _batch(n: int, cam_dtype=torch.float32) -> dict:
    return {
        "observation.images.top_cam": torch.zeros(n, 3, 4, 4, dtype=cam_dtype),
        "action": torch.zeros(n, 6),
    }


class TestValidatePolicy:
    def test_loss_is_weighted_by_samples_not_batches(self):
        """A short trailing batch must not count as much as a full one."""
        from lerobot.scripts.lerobot_train import validate_policy

        policy = _FakePolicy([1.0, 4.0])
        info = validate_policy(
            policy=policy,
            dataloader=[_batch(2), _batch(1)],
            preprocessor=lambda b: b,
            camera_keys=["observation.images.top_cam"],
            accelerator=_fake_accelerator(),
            seed=1000,
        )

        assert info["loss"] == pytest.approx((1.0 * 2 + 4.0 * 1) / 3)
        assert info["num_samples"] == 3

    def test_scores_in_eval_mode_and_restores_train_mode(self):
        from lerobot.scripts.lerobot_train import validate_policy

        policy = _FakePolicy([1.0])
        validate_policy(
            policy=policy,
            dataloader=[_batch(2)],
            preprocessor=lambda b: b,
            camera_keys=[],
            accelerator=_fake_accelerator(),
            seed=1000,
        )

        assert policy.modes == [False], "policy must be in eval mode while validating"
        assert policy.training is True, "training mode must be restored afterwards"

    def test_uint8_frames_are_scaled_before_the_forward_pass(self):
        from lerobot.scripts.lerobot_train import validate_policy

        policy = _FakePolicy([1.0])
        batch = _batch(2, cam_dtype=torch.uint8)
        batch["observation.images.top_cam"] += 255

        validate_policy(
            policy=policy,
            dataloader=[batch],
            preprocessor=lambda b: b,
            camera_keys=["observation.images.top_cam"],
            accelerator=_fake_accelerator(),
            seed=1000,
        )

        frames = policy.seen_batches[0]["observation.images.top_cam"]
        assert frames.dtype == torch.float32
        assert frames.max().item() == pytest.approx(1.0)

    def test_repeated_passes_give_the_same_loss_for_a_stochastic_policy(self):
        """The reported loss must reflect the weights, not which noise was sampled."""
        from lerobot.scripts.lerobot_train import validate_policy

        class _NoisyPolicy(_FakePolicy):
            def forward(self, batch):
                self.seen_batches.append(batch)
                self.modes.append(self.training)
                return torch.rand(1).squeeze(), {}

        kwargs = dict(
            dataloader=[_batch(2), _batch(2)],
            preprocessor=lambda b: b,
            camera_keys=[],
            accelerator=_fake_accelerator(),
            seed=1000,
        )
        first = validate_policy(policy=_NoisyPolicy([]), **kwargs)
        second = validate_policy(policy=_NoisyPolicy([]), **kwargs)

        assert first["loss"] == pytest.approx(second["loss"])

    def test_empty_split_raises(self):
        from lerobot.scripts.lerobot_train import validate_policy

        with pytest.raises(ValueError, match="no samples"):
            validate_policy(
                policy=_FakePolicy([]),
                dataloader=[],
                preprocessor=lambda b: b,
                camera_keys=[],
                accelerator=_fake_accelerator(),
                seed=1000,
            )
