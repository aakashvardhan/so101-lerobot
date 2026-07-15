# ACT Model Training on SO-ARM 101 from scratch (only 50 demonstration)

**Project:** SO-101 pick-cube imitation learning  
**Date:** June 2026  
**Framework:** [LeRobot](https://github.com/huggingface/lerobot) v3.0  
**Policy:** Action Chunking Transformer (ACT)  
**W&B run:** [act_so101_pick_cube](https://wandb.ai/aakashvardhan-madabhushi-san-jose-state-university/so101-act/runs/3n0nc42f)

---

## Executive summary

An ACT policy was trained **from scratch** (random transformer init; ResNet18 backbone pretrained on ImageNet) on **50 teleoperated demonstrations** of a single task: *pick up the cube and place it in the bowl*. Training ran for **30,000 steps** (~**6.9 hours** on CUDA) and converged to a final training loss of **0.092**. Offline inference validation on held-in dataset frames yielded an overall **mean absolute error (MAE) of 1.54** across 6 joint dimensions, indicating the policy reproduces demonstration actions with reasonable fidelity. **No real-robot rollout evaluation** has been performed yet; that remains the definitive test of task success.

| Metric | Value |
|--------|-------|
| Demonstrations | 50 episodes |
| Total frames | 49,633 (~993 frames/episode) |
| Training steps | 30,000 |
| Effective epochs | ~4.8 (30k × batch 8 / 49,633 frames) |
| Wall-clock time | ~6.9 h |
| Final train loss | 0.092 |
| Model parameters | 51.7M |
| Checkpoint size | ~197 MB (`model.safetensors`) |
| Offline action MAE | 1.54 (overall) |

---

## 1. Task and robot setup

### Task

- **Instruction:** `Pick up the cube and place it in the bowl`
- **Structure:** One direction per episode (pick → place); cube reset manually between episodes
- **Control mode:** Joint position targets on 6 DoF (5 arm joints + gripper)

### Hardware

| Component | Configuration |
|-----------|---------------|
| Robot | SO-101 follower (`so_follower`) |
| Teleop | SO-101 leader arm |
| Cameras | `gripper_cam` (640×480 @ 30 fps), `top_cam` (640×480 @ 30 fps) |
| Recording codec | H.264 (required on Windows) |

### Joint space (6-D action / state)

| Index | Name | Role |
|-------|------|------|
| 0 | `shoulder_pan.pos` | Base rotation |
| 1 | `shoulder_lift.pos` | Shoulder |
| 2 | `elbow_flex.pos` | Elbow |
| 3 | `wrist_flex.pos` | Wrist pitch |
| 4 | `wrist_roll.pos` | Wrist roll |
| 5 | `gripper.pos` | Gripper open/close |

---

## 2. Dataset

### Source

- **Hub:** [aakashv100/so101-pick-cube](https://huggingface.co/datasets/aakashv100/so101-pick-cube)
- **Local path:** `hf_data/so101-pick-cube`
- **Format:** LeRobot v3.0

### Statistics

| Property | Value |
|----------|-------|
| Episodes | 50 |
| Frames | 49,633 |
| FPS | 30 |
| Episode length | min 732 / max 1,208 / mean 993 frames (~24–40 s) |
| Train split | All 50 episodes (`0:50`) — **no held-out validation split** |
| Total size | ~491 MB on Hub |

### Observations and actions

- **State:** 6-D proprioception (joint positions)
- **Images:** Two RGB streams at 480×640 (stored as H.264 video)
- **Action:** 6-D joint position targets (same space as state)

### Data quality checks

Dataset validation (`scripts/validate_dataset.py`) confirms:

- Episode/frame counts consistent with `meta/info.json`
- Videos decodable at expected resolution
- No NaN/Inf in action or state tensors

---

## 3. Model architecture

**Policy type:** ACT (Action Chunking Transformer)

| Hyperparameter | Value | Notes |
|----------------|-------|-------|
| `chunk_size` | 100 | Predicts 100 future actions (~3.3 s @ 30 fps) |
| `n_action_steps` | 100 | Executes full chunk before re-query |
| `n_obs_steps` | 1 | Single-frame observation |
| `vision_backbone` | ResNet18 | ImageNet pretrained |
| `dim_model` | 512 | Transformer width |
| `n_encoder_layers` | 4 | |
| `n_decoder_layers` | 1 | Matches original ACT implementation |
| `n_heads` | 8 | |
| `dim_feedforward` | 3200 | |
| `use_vae` | true | CVAE training objective |
| `kl_weight` | 10.0 | KL regularization strength |
| `latent_dim` | 32 | |
| `dropout` | 0.1 | |

**Inputs:** `observation.state`, `observation.images.gripper_cam`, `observation.images.top_cam`  
**Output:** `action` (6-D)  
**Normalization:** MEAN_STD for VISUAL, STATE, and ACTION; ImageNet stats for images

**Parameter count:** 51,668,614 (~52M learnable parameters)

---

## 4. Training configuration

### Command (via `scripts/train_act.ps1`)

```powershell
.\scripts\train_act.ps1 -Steps 30000 -Wandb -WandbProject so101-act -ReturnUint8
```

### Optimizer and schedule

| Setting | Value |
|---------|-------|
| Optimizer | AdamW |
| Learning rate | 1×10⁻⁵ (transformer + backbone) |
| Weight decay | 1×10⁻⁴ |
| Gradient clip | 10.0 |
| LR scheduler | None (constant LR) |
| Batch size | 8 |
| Seed | 1000 |

### Infrastructure

| Setting | Value |
|---------|-------|
| Device | CUDA (PyTorch 2.10+cu130) |
| GPU VRAM (training) | ~3.5–7.7 GB |
| `num_workers` | 0 (required on Windows — multiprocessing dataloader stalls with video decode) |
| Video backend | pyav (`torchcodec` unavailable on Windows) |
| Mixed precision | Off |
| Data augmentation | Off |

### Logging and checkpointing

| Setting | Value |
|---------|-------|
| W&B project | `so101-act` |
| W&B mode | online |
| Log frequency | every 200 steps |
| Checkpoint frequency | every 5,000 steps |
| Output directory | `outputs/train/act_so101_pick_cube` |

### Checkpoints saved

```
checkpoints/
├── 005000/
├── 010000/
├── 015000/
├── 020000/
├── 025000/
├── 030000/          ← final
└── last/            → symlink/junction to latest
```

Each checkpoint contains:

- `pretrained_model/` — weights, config, normalizer processors
- `training_state/` — optimizer, RNG, step counter (enables resume)

---

## 5. Training results

### Loss curve (from Weights & Biases)

| Step | Train loss |
|------|------------|
| 200 | 6.80 |
| 1,000 | 1.99 |
| 5,000 | 0.38 |
| 10,000 | 0.19 |
| 15,000 | 0.14 |
| 20,000 | 0.12 |
| 25,000 | 0.10 |
| **30,000** | **0.092** |

**Observations:**

- Rapid initial drop (loss 6.8 → 2.0 in first ~1k steps), then gradual refinement
- Loss still decreasing at step 30k — not fully plateaued; longer training or early stopping on a val split could be explored
- Final gradient norm: **7.5** (stable; early training saw norms >1000)

### Throughput

- **~1.2–1.4 steps/s** (~0.7 s/step wall time)
- Bottleneck: CPU-side video decoding (`data_s` ≈ 0.55 s vs `updt_s` ≈ 0.17 s per step)
- GPU utilization: ~33–35% (data-bound, not compute-bound)

### Training duration

- **Wall-clock:** ~6.9 hours (25,001 s per W&B)
- **Effective dataset passes:** ~4.8 epochs

### Simulation evaluation during training

**Not performed.** LeRobot's built-in `eval_freq` rollouts require a simulation environment (`--env`); this run used offline imitation only (`env: null`). Task success must be measured on the physical robot.

---

## 6. Offline evaluation

### Method

Script: `test_inference_offline.py`

Loads the final checkpoint and runs the **full inference pipeline** (preprocess → ACT → postprocess) on 5 frames sampled evenly across the dataset (frames 0, 12,408, 24,816, 37,224, 49,632). Predicted actions are compared to ground-truth demonstration actions.

```powershell
.\.venv\Scripts\python.exe test_inference_offline.py `
  --checkpoint outputs/train/act_so101_pick_cube/checkpoints/last/pretrained_model `
  --repo-id aakashv100/so101-pick-cube `
  --root hf_data/so101-pick-cube `
  --device cuda
```

**Note:** Frames are from the **training set** (all 50 episodes used for training). This measures action reconstruction fidelity, not generalization to unseen scenes.

### Per-frame results

| Frame | shoulder_pan | shoulder_lift | elbow_flex | wrist_flex | wrist_roll | gripper |
|-------|-------------|---------------|------------|------------|------------|---------|
| 0 | 2.76 | 1.67 | 4.18 | 0.34 | 3.48 | 0.10 |
| 12,408 | 3.75 | 6.76 | 1.34 | 0.99 | 0.04 | 2.60 |
| 24,816 | 0.16 | 0.17 | 3.48 | 0.12 | 0.37 | 0.09 |
| 37,224 | 1.51 | 2.46 | 1.65 | 1.47 | 0.36 | 0.19 |
| 49,632 | 0.21 | 1.53 | 3.42 | 0.49 | 0.07 | 0.29 |

*(Absolute error in joint units vs ground truth)*

### Summary metrics

| Joint | Mean absolute error |
|-------|----------------------|
| shoulder_pan | 1.68 |
| shoulder_lift | 2.52 |
| elbow_flex | 2.82 |
| wrist_flex | 0.68 |
| wrist_roll | 0.86 |
| gripper | 0.65 |
| **Overall MAE** | **1.54** |

### Interpretation

- **Pipeline validated:** checkpoint loads, inference runs without errors, outputs valid 6-D actions
- **Best fidelity:** wrist and gripper (MAE < 1.0)
- **Larger errors:** shoulder_lift and elbow_flex (MAE ~2.5–2.8) — may reflect higher variance across demo trajectories or harder-to-fit motion phases (reach vs grasp)
- **Limitation:** offline MAE on training frames does **not** predict real-world task success; closed-loop robot execution can diverge due to compounding error, calibration drift, and visual domain shift

---

## 7. Known issues and mitigations

| Issue | Impact | Mitigation applied |
|-------|--------|-------------------|
| Windows dataloader stall (`num_workers > 0`) | Training appeared frozen at step 0 | Set `num_workers=0` |
| Windows checkpoint junction bug | 2nd+ checkpoint save failed | Fixed in `train_utils.py` (`os.rmdir` for junctions) |
| `torchcodec` unavailable | Slower video decode via pyav | Acceptable; install torchcodec if Windows wheel becomes available |
| Data-bound training (~33% GPU util) | Longer wall-clock time | `-ReturnUint8`, fewer steps (30k vs 100k) |
| No validation split | Cannot measure generalization offline | Optional: hold out 5–10 episodes; real robot eval is definitive |
| Camera label swap | Potential wrong view assignment | `scripts/swap_camera_keys.py` available if needed |

---

## 8. Artifacts

| Artifact | Path |
|----------|------|
| Final model | `outputs/train/act_so101_pick_cube/checkpoints/last/pretrained_model/` |
| Train config | `.../pretrained_model/train_config.json` |
| W&B dashboard | https://wandb.ai/aakashvardhan-madabhushi-san-jose-state-university/so101-act/runs/3n0nc42f |
| Training script | `scripts/train_act.ps1` |
| Offline eval script | `test_inference_offline.py` |
| Dataset (local) | `hf_data/so101-pick-cube` |

---

## 9. Conclusions

1. **Training succeeded:** ACT converged from random init to loss 0.092 over 30k steps on 50 demonstrations, completing in ~7 hours on a single CUDA GPU.
2. **Offline action fidelity is reasonable:** MAE 1.54 on sampled training frames suggests the policy learned to map observations to demonstration-like joint commands.
3. **Real-robot evaluation is pending:** The critical next step is deploying the checkpoint on the SO-101 arm and measuring pick-and-place success rate over multiple cube placements.
4. **Room for improvement:** longer training or early stopping with a held-out episode split; data augmentation; temporal ensembling at inference; more demonstrations for robustness.

---

## 10. Recommended next steps

1. **Deploy on robot** using `lerobot-record` with `--policy.path=outputs/train/act_so101_pick_cube/checkpoints/last/pretrained_model` and the same camera/robot config as recording.
2. **Run 10–20 rollouts** with varied cube starting positions; record success/failure.
3. **Optional:** hold out episodes 40–49, retrain on 0–39, and re-run offline eval on unseen episodes for a stricter generalization estimate.
4. **Optional:** push checkpoint to Hugging Face Hub for sharing and reproducibility (`-PushToHub` in training script).

---

*Report generated from checkpoint `outputs/train/act_so101_pick_cube/checkpoints/030000`, W&B run `3n0nc42f`, and offline evaluation run on the local pick-cube dataset.*
