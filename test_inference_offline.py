"""Offline inference smoke test for the trained SO-101 ACT policy.

Loads a trained checkpoint and runs it on real frames from the local dataset,
comparing predicted actions against ground-truth actions. This validates the
full inference pipeline (preprocess -> policy -> postprocess) WITHOUT needing
the physical arm.

Usage:
    uv run python test_inference_offline.py
"""

import argparse

import numpy as np
import torch

from lerobot.common.control_utils import predict_action
from lerobot.configs import PreTrainedConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies import make_policy, make_pre_post_processors

JOINT_NAMES = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]


def frame_to_robot_observation(frame: dict) -> dict[str, np.ndarray]:
    """Convert a LeRobotDataset frame into the raw robot-style observation dict
    that `predict_action` expects (images as HWC uint8, state as 1D float32)."""
    obs: dict[str, np.ndarray] = {}
    for key, value in frame.items():
        if not key.startswith("observation."):
            continue
        if "image" in key:
            # dataset stores CHW float in [0,1]; robot path expects HWC uint8
            img = (value.numpy() * 255).clip(0, 255).astype(np.uint8)
            img = np.transpose(img, (1, 2, 0))
            obs[key] = img
        else:
            obs[key] = value.numpy().astype(np.float32)
    return obs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        default="outputs/train/so101_act_screwdriver/checkpoints/010000/pretrained_model",
    )
    parser.add_argument("--repo-id", default="local/so101-screwdriver-above")
    parser.add_argument("--root", default="./hf_data/so101-pick-place-dataset/view_above")
    parser.add_argument("--device", default="cpu", help="cpu or cuda")
    parser.add_argument("--num-frames", type=int, default=5)
    args = parser.parse_args()

    device = torch.device(args.device)

    print(f"Loading dataset {args.repo_id} from {args.root}")
    dataset = LeRobotDataset(args.repo_id, root=args.root)

    print(f"Loading policy config from {args.checkpoint}")
    cfg = PreTrainedConfig.from_pretrained(args.checkpoint)
    cfg.pretrained_path = args.checkpoint
    cfg.device = args.device

    policy = make_policy(cfg, ds_meta=dataset.meta)
    policy.eval()

    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=cfg,
        pretrained_path=cfg.pretrained_path,
        dataset_stats=dataset.meta.stats,
        preprocessor_overrides={"device_processor": {"device": args.device}},
    )

    # Sample a few frames spread across the dataset.
    n = len(dataset)
    idxs = np.linspace(0, n - 1, args.num_frames).astype(int)
    print(f"\nDataset has {n} frames across {dataset.meta.total_episodes} episodes.")
    print(f"Running inference on frames: {idxs.tolist()}\n")

    errors = []
    for i in idxs:
        # ACT predicts a 100-step action chunk and queues it; reset before each
        # frame so every prediction is a fresh open-loop inference from that obs.
        policy.reset()
        frame = dataset[int(i)]
        obs = frame_to_robot_observation(frame)
        task = frame.get("task", "Grab the screwdriver")
        if isinstance(task, (list, tuple)):
            task = task[0]

        action = predict_action(
            observation=obs,
            policy=policy,
            device=device,
            preprocessor=preprocessor,
            postprocessor=postprocessor,
            use_amp=False,
            task=task,
            robot_type=dataset.meta.robot_type,
        )
        pred = np.asarray(action.numpy(), dtype=np.float32).reshape(-1)
        gt = np.asarray(frame["action"].numpy(), dtype=np.float32).reshape(-1)
        err = np.abs(pred - gt)
        errors.append(err)

        print(f"frame {int(i):5d} | task='{task}'")
        print("  joint        pred      gt       |err|")
        for j, name in enumerate(JOINT_NAMES):
            print(f"  {name:12s} {float(pred[j]):8.2f} {float(gt[j]):8.2f} {float(err[j]):8.2f}")
        print()

    errors = np.stack(errors)
    print("=" * 50)
    print("Mean absolute error per joint (pred vs ground-truth):")
    for j, name in enumerate(JOINT_NAMES):
        print(f"  {name:12s} {errors[:, j].mean():8.3f}")
    print(f"\nOverall MAE: {errors.mean():.3f}")
    print("\nInference pipeline OK: policy produced valid 6-D actions for every frame.")


if __name__ == "__main__":
    main()
