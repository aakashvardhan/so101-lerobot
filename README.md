# Imitation Learning on a Physical SO-101 Arm

Training and evaluating manipulation policies on real hardware — 50 teleoperated
demonstrations, two policy architectures, and a 100-trial evaluation protocol
designed to find out where the policy actually fails.

**Task:** *pick up the cube and place it in the bowl* · 6-DoF joint control ·
two 640×480 RGB streams at 30 fps

---

## Headline result

An Action Chunking Transformer trained from scratch on 50 demonstrations,
scored over 100 physical rollouts:

| Protocol | Trials | Success | Grasp rate | Mean placement error |
|---|---|---|---|---|
| **Fixed** cube position | 50 | **92%** (46/50) | 92% | **2.49 cm** (successes only) |
| **Randomized** cube position | 50 | **0%** (0/50) | 0% | — |

All four Fixed failures were no-grasp. Zero were grasped-then-dropped, and zero
were placed in the wrong location — so when the policy closed the gripper, it
finished the task every time.

**The 0% is the interesting number.** It is a dataset property, not a training
failure, and the evaluation was built to be able to tell those apart.

---

## Why randomized position scored zero

Before scoring the Random protocol I template-matched the first frame of all 50
training episodes. Every demonstration starts the cube on the same paper marker,
with under 1 cm of spread across the whole dataset.

So the policy was never shown a cube anywhere else. What it learned is a
near-open-loop trajectory to one location that happens to be where the cube
always is — not a visually-conditioned grasp. It reproduces that trajectory at
92%, and generalizes to a moved cube at 0%.

That distinction only shows up if you evaluate off-distribution. A Fixed-only
protocol would have reported 92% and called the policy solved. The fix is data
collection, not more gradient steps: demonstrations with the cube deliberately
scattered across the workspace.

The same class of problem bit the SmolVLA run from the other direction — a
3-trial sanity check showed it stalling 11–51 s before initiating motion, traced
to objects sitting in the top camera's view that never appear in any
demonstration. The background was out of distribution, and the policy waited.

---

## ACT vs. SmolVLA

Both policies trained on the same 50 demonstrations, scored under one protocol.
SmolVLA finetunes `lerobot/smolvla_base` (99.9M trainable of 450M; the
SmolVLM2-500M backbone stays frozen); ACT trains from scratch on an
ImageNet-pretrained ResNet18 backbone.

| | ACT v2 | SmolVLA |
|---|---|---|
| Initialization | from scratch | finetune of `smolvla_base` |
| Training steps | 60,000 | 20,000 |
| Parameters (trainable) | 51.7M | 99.9M of 450M |
| Wall-clock | ~13 h | 5.7 h |
| Action MAE, 200 frames | 1.49 | **1.06** |
| Joint accuracy (±5) | 94.8% | **97.8%** |
| Frame accuracy (±5) | 72.0% | **89.0%** |
| Inference latency | **18 ms** | 251 ms |
| Fixed-position success | **92%** | not yet scored |

SmolVLA fits the demonstrations substantially better on a third of the gradient
steps. It pays 14× in query latency, which is the main open risk to closed-loop
behaviour and the reason the offline win cannot be reported as a real win yet.

**Its real-robot scoring is not done.** Two attempts were voided — one for the
out-of-distribution scene above, one when a camera dropped out at episode 17 of
50. Voiding a run costs a day; reporting a contaminated one costs the result.

### A holdout run, and a checkpoint-selection surprise

A third run held out 5 of the 50 episodes (every tenth index, so operator and
lighting drift late in a session doesn't get confounded with generalization).

Validation loss bottomed at 0.122 around steps 5,000–7,500 and rose to 0.153 by
step 20,000 while training loss kept falling — textbook overfitting. But the
final checkpoint still beat the best-`val/loss` checkpoint on held-out action
accuracy, MAE 1.20 vs 2.01.

Flow-matching validation loss and teacher-forced action accuracy do not pick the
same checkpoint. Selecting on validation loss alone would have shipped the worse
policy.

---

## The evaluation harness

Most of the engineering here is in measurement, not in training.

- **Resumable rollouts.** `scripts/run_eval.ps1` resumes mid-protocol, refuses a
  stale eval cache, and returns the arm to a known start pose between trials —
  so a 50-trial run surviving a camera dropout doesn't mean rescoring from zero.
- **Placement error from video, not eyeballing.** `measure_placement_error.py`
  calibrates cm-per-pixel from two clicks on the bowl rim (11.5 cm known
  diameter), then measures cube-to-bowl offset on each trial's final frame.
  That's where 2.49 cm comes from, and why the failures are separable: the four
  no-grasp trials sit at 13–16 cm while every success is under 5 cm.
- **A locked scoresheet.** Task spec, trial count, and success definition
  (autonomous grasp **and** release in the bowl) are fixed before scoring
  starts, with a failure-mode taxonomy — no-grasp / grasped-dropped /
  wrong-placement — so failures are counted, not summarized.
- **Dataset validation before GPU time.** `validate_dataset.py` checks
  episode/frame alignment, H.264 decodability, resolution, and that action and
  proprioceptive tensors are finite. All 50 episodes and 49,633 frames passed
  with zero integrity failures before any training started.
- **Reproducible long runs.** Configurable augmentation, W&B tracking,
  5,000-step checkpointing, and resume support, so a 13-hour run survives a
  restart.

---

## Artifacts

Everything below is public and inspectable.

| | |
|---|---|
| Training data (v2, 50 episodes) | [`aakashv100/so101-pick-cube-v2`](https://huggingface.co/datasets/aakashv100/so101-pick-cube-v2) |
| Training data (v1, 49,633 frames) | [`aakashv100/so101-pick-cube`](https://huggingface.co/datasets/aakashv100/so101-pick-cube) |
| ACT policy | [`aakashv100/act_so101_pick_cube_v2`](https://huggingface.co/aakashv100/act_so101_pick_cube_v2) |
| SmolVLA policy (holdout) | [`aakashv100/smolvla_so101_pick_cube_holdout`](https://huggingface.co/aakashv100/smolvla_so101_pick_cube_holdout) |
| Fixed-protocol rollouts | [`eval_so101-pick-cube-v2-fixed`](https://huggingface.co/datasets/aakashv100/eval_so101-pick-cube-v2-fixed) |
| Random-protocol rollouts | [`eval_so101-pick-cube-v2-random`](https://huggingface.co/datasets/aakashv100/eval_so101-pick-cube-v2-random) |
| Training runs | W&B [`so101-act`](https://wandb.ai/aakashvardhan-madabhushi-san-jose-state-university/so101-act) · [`so101-smolvla`](https://wandb.ai/aakashvardhan-madabhushi-san-jose-state-university/so101-smolvla) |

---

## Full write-ups

| Document | What's in it |
|---|---|
| [`ACT_training_report.md`](ACT_training_report.md) | ACT training, offline validation, and limitations |
| [`SmolVLA_training_report.md`](SmolVLA_training_report.md) | SmolVLA finetune, head-to-head protocol, voided-run post-mortems |
| [`SmolVLA_holdout_training_report.md`](SmolVLA_holdout_training_report.md) | 45/5 holdout, generalization metrics, checkpoint-selection analysis |
| [`eval_worklog_2026-07-14.md`](eval_worklog_2026-07-14.md) | Evaluation setup, camera identification, position-randomization finding |
| [`docs/windows-setup.md`](docs/windows-setup.md) | Hardware bring-up, calibration, teleoperation, recording |

Scored trials live in `ACT_eval_scoresheet.xlsx` and `SmolVLA_eval_scoresheet.xlsx`;
per-trial placement measurements in `placement_errors_eval_so101-pick-cube-v2-fixed.csv`.

---

## What's mine in this repo

This is a fork of [LeRobot](https://github.com/huggingface/lerobot); `src/lerobot/`
is upstream except where noted.

| Path | |
|---|---|
| `scripts/` | Training, evaluation, scoring, and measurement tooling — the harness described above |
| `*_training_report.md`, `eval_worklog_*.md` | Experiment write-ups |
| `*_eval_scoresheet.xlsx`, `placement_errors_*.csv` | Scored trials and measurements |
| `calibration/` | Committed calibration for this pair of arms |
| `src/lerobot/motors/motors_bus.py` | Patched to re-lock STS3215 EEPROM after ID/baud writes |
| `scan_motor_ids.py`, `fix_motor_ids.py`, `burn_motor_eeprom.py` | Motor-ID diagnosis and repair |
| `docs/windows-setup.md` | Windows bring-up guide |

**The motor-ID patch:** after a power cycle, the gripper (ID 6) and wrist_roll
(ID 5) could both come back as ID 5 — a bus collision that reads as
`Missing motor IDs: 5, 6`. STS3215 EEPROM has to be unlocked, written, then
*re-locked* to commit; upstream did not always re-lock, so on some firmware
batches the write silently reverted. Details in
[`docs/windows-setup.md`](docs/windows-setup.md#motor-id-bug-and-fix).

---

## Running it

Hardware bring-up, calibration, and teleoperation:
**[`docs/windows-setup.md`](docs/windows-setup.md)**.

Training and evaluation entry points once the arms are calibrated:

```powershell
.\.venv\Scripts\Activate.ps1

.\scripts\train_act.ps1                          # ACT from scratch
.\scripts\train_smolvla.ps1                      # SmolVLA finetune

.\scripts\run_eval.ps1 -Mode fixed  -NumEpisodes 50
.\scripts\run_eval.ps1 -Mode random -NumEpisodes 50 -Resume

python scripts/measure_placement_error.py --calib-cm 11.5
```

---

## Status

ACT is trained and fully scored on both protocols. SmolVLA is trained, offline
metrics are measured, and its 100 physical trials are pending — the handover is
in [`SmolVLA_training_report.md` §8](SmolVLA_training_report.md).

The next experiment is the one the 0% points at: re-record demonstrations with
randomized cube placement and re-run both protocols. Until that exists, the
honest summary of this work is *92% at one position, and a measurement setup
good enough to prove that's the ceiling.*

---

## License

Apache 2.0, inherited from [LeRobot](https://github.com/huggingface/lerobot).
