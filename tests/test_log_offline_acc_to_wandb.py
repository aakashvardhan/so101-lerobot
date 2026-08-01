"""Tests for offline-accuracy W&B summary flattening."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from log_offline_acc_to_wandb import metrics_to_summary  # noqa: E402
from test_inference_offline import JOINT_NAMES  # noqa: E402


def test_metrics_to_summary_flattens_joints():
    metrics = {
        "num_frames": 200,
        "tolerance": 5.0,
        "overall_mae": 1.06,
        "joint_accuracy": 0.978,
        "frame_accuracy": 0.89,
        "latency_mean_ms": 251.0,
        "latency_max_ms": 313.0,
        "joint_mae": {name: 1.0 for name in JOINT_NAMES},
        "joint_accuracy_per_joint": {name: 0.95 for name in JOINT_NAMES},
    }

    summary = metrics_to_summary(metrics, "ckpt/path")

    assert summary["offline/checkpoint"] == "ckpt/path"
    assert summary["offline/overall_mae"] == 1.06
    assert summary["offline/joint_accuracy"] == 0.978
    assert summary["offline/frame_accuracy"] == 0.89
    assert summary["offline/mae/gripper"] == 1.0
    assert summary["offline/accuracy/shoulder_pan"] == 0.95
    assert len([k for k in summary if k.startswith("offline/mae/")]) == 6
    assert summary["offline/episodes"] == "all"


def test_metrics_to_summary_records_episode_scope():
    """Held-out and training numbers share key names, so the scope must be recorded."""
    metrics = {
        "num_frames": 50,
        "tolerance": 5.0,
        "overall_mae": 2.4,
        "joint_accuracy": 0.9,
        "frame_accuracy": 0.6,
        "latency_mean_ms": 251.0,
        "latency_max_ms": 313.0,
        "joint_mae": {name: 2.0 for name in JOINT_NAMES},
        "joint_accuracy_per_joint": {name: 0.9 for name in JOINT_NAMES},
    }

    summary = metrics_to_summary(metrics, "ckpt/path", [4, 14, 24, 34, 44])

    assert summary["offline/episodes"] == "4,14,24,34,44"
