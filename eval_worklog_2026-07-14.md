# ACT v2 Evaluation — Work Log (2026-07-14 → 2026-07-15)

Everything set up and fixed for evaluating the new ACT model against
`ACT_eval_scoresheet.xlsx` (50-trial Fixed + 50-trial Random protocol).

## Model under evaluation

- **`act_so101_pick_cube_v2`** — 60k steps, chunk_size 100, finished 2026-07-14.
  Eval checkpoint (locked for both tabs): `outputs/train/act_so101_pick_cube_v2/checkpoints/060000/pretrained_model`
- Training dataset: `aakashv100/so101-pick-cube-v2` (50 episodes, task
  "Pick up the cube and place it in the bowl", gripper_cam + top_cam)
- W&B training run: `55h5xmgg` in project `so101-act`

## Key findings

- **Camera change**: top_cam is now the wide-angle **USB cam on OpenCV index 1**
  (not the RealSense). Verified v2 training frames match this camera's live view.
  Index 0 = gripper_cam, index 2 = OBS virtual cam (ignore).
- **Zero position randomization in training**: template-matching over all 50
  v2 first frames showed every episode starts the cube on the **"A" paper
  marker** (spread < 1 cm). The A marker IS the Fixed-tab reference position.
  Expect high Fixed / low Random (data-coverage limit, not training failure).
- v2 was trained with the fixed wrist_roll calibration (train mean −99.6°,
  σ 14.4 — live reading −91.6° is in-distribution).
- Bowl outer rim = **11.5 cm** (scale reference for placement-error measurement,
  ≈ 0.095 cm/px on top_cam).

## Scripts created

| Script | Purpose |
|---|---|
| `scripts/run_eval.ps1` | Eval inference wrapper: `-Mode fixed\|random`, `-ClearCache`, `-Resume`, `-NumEpisodes`, `-Checkpoint`, `-NoReturnToStart`… Refuses stale eval cache; datasets `aakashv100/eval_so101-pick-cube-v2-{fixed,random}` |
| `scripts/measure_placement_error.py` | Click-to-measure placement error (column F) from recorded top_cam final frames. Calibrate once with 2 bowl-rim clicks (`--calib-cm 11.5`). Keys: s save, n skip, r redo, a/d scrub frames, q quit. Writes `placement_errors_<dataset>.csv`. Also `--measure gripper` (Random tab column C): auto-seeks each episode's first grasp attempt via the recorded gripper.pos signal, one click on the fingertip midpoint → signed (x, y) cm from workspace center, same frame as column B. One-time axis calibration from ≥2 known cube positions: `--ref 1:1.4,-4.7 --ref 3:2.4,1.8` (click A-marker center + cube center on each ref trial's first frame); stored in `gripper_positions_<dataset>.axes.json`. Writes `gripper_positions_<dataset>.csv` |
| `scripts/make_position_template.py` | Printable cube-position templates from the xlsx Random tab. Default → `eval_position_template.html` (annotated); `--minimal` → `eval_position_grid.html` (bare 1 cm graph grid + axes + 50 numbered dots + red center cross). Both print on one sheet of Letter/A4 at 100% scale |

Also updated `scripts/verify_calib.py` to compare joints against **v2** normalizer stats.

## lerobot_record.py changes

- **`--return_to_start_pose`** (on by default in run_eval.ps1): captures arm pose
  at connect, smoothly returns to it after every episode (replaces re-running
  `goto_start_pose.py` each reset).
- **Stale `exit_early` fix**: arrow key pressed while no loop is listening no
  longer instantly kills the next episode (was causing zero-frame episodes).
- **Empty-episode guard**: zero-frame episodes are skipped with a warning
  instead of crashing `save_episode`.
- **Cleanup guard**: `push_to_hub` in the finally-block no longer masks the real
  error when the dataset failed to open.
- **Resume fix (run_eval.ps1)**: `-Resume` passes `--dataset.root=<cache dir>`
  (required by `LeRobotDataset.resume()`).
- Tests: `tests/test_lerobot_record.py` — 26 passing (3 new for return-to-start-pose).

## Fixed run status

- **COMPLETE: 50/50 episodes** in `aakashv100/eval_so101-pick-cube-v2-fixed`
  (auto-pushed to Hub). Episode index + 1 = sheet trial number.
- Survived two crashes en route (both diagnosed & fixed): stale-exit_early
  empty episode at trial ~24, and a motor-5 overload latch at trial ~26
  (cleared by 15 s power-cycle; `test_servos.py` confirmed healthy after).
- Remaining: fill column F (`measure_placement_error.py --calib-cm 11.5`),
  then `log_eval_to_wandb.py --dry-run` →
  `log_eval_to_wandb.py --run-id 55h5xmgg --checkpoint checkpoints/060000`.

## Random run setup (in progress)

1. Print `eval_position_grid.html` (Letter, Scale=Default/100%, verify 10
   squares = 10 cm). Red cross on workspace center (zone centered on the A
   marker), +y away from robot base.
2. Mark all 50 dots through the paper onto the table, then **remove the paper**
   (training scenes have bare wood there — sheet in view = distribution shift).
3. Keep the A paper and white "B" bowl paper exactly as in training.
4. Sanity: 3 throwaway episodes
   (`run_eval.ps1 -Mode random -NumEpisodes 3 -RepoId aakashv100/eval_sanity-random -ClearCache`)
   with cube near-A / mid / far-corner before committing to 50.
5. Real run: `run_eval.ps1 -Mode random -ClearCache`, trial N = dot N.
6. Same 50 positions must be reused for the SmolVLA comparison.

## Published to Hugging Face Hub

- Model: <https://huggingface.co/aakashv100/act_so101_pick_cube_v2>
  (checkpoint 060000 + processors + model card)
- Training dataset: <https://huggingface.co/datasets/aakashv100/so101-pick-cube-v2> (1.7 GB, 50 episodes)
- Fixed eval dataset: <https://huggingface.co/datasets/aakashv100/eval_so101-pick-cube-v2-fixed> (50 episodes)

## Protocol reminders

- Same checkpoint (060000) for both tabs; no manual assist (touch = fail);
  → ends episode, ← discards & re-records, Esc stops the run; retries within
  an episode are allowed (success = autonomous grasp + release in bowl).
- Failure modes: `no-grasp` (never lifted) / `grasped-dropped` (lost in
  transit) / `wrong-placement` (released outside bowl) / `other` (+ note).
  Score the event that ended the trial's chance of success.
- If motor 5 latches: power-cycle 15 s → `goto_start_pose.py` →
  `run_eval.ps1 -Mode <tab> -Resume -NumEpisodes <remaining>`.
