# Current Issues in ACT Model Inference
*Model: `outputs/train/act_so101_pick_cube/checkpoints/030000/pretrained_model`*
*Last updated: 2026-06-26*

---

## Issue 1 — Inference frames drop to ~17 Hz (target: 30 Hz)

### Root cause
ACT uses an internal action queue (`_action_queue`, `modeling_act.py:98`). When the queue is empty — once every 100 steps (`n_action_steps=100`) — it calls `predict_action_chunk`, which runs the full forward pass:

1. ResNet18 backbone encodes **two** 640×480 images (gripper_cam + top_cam)
2. VAE encoder forward pass (`n_vae_encoder_layers=4`)
3. Transformer encoder+decoder (`n_encoder_layers=4`, `n_decoder_layers=1`, `dim_model=512`)

All of this runs in **FP32** (`use_amp: false` in `config.json:37`). On the current GPU, this takes ~58 ms, which blows past the 33 ms target. `precise_sleep` gets a negative sleep time and the loop runs as fast as hardware allows: **~17 Hz**.

### AMP result (2026-06-26) — counterproductive on this GPU

`--policy.use_amp=true` was tested and made inference frames **slower** (11–15 Hz, down from 17 Hz). This GPU likely lacks FP16 tensor cores sized for ResNet18 matrix shapes; the `torch.autocast` context-switch overhead exceeds the arithmetic gain on a small model. **Do not use `--policy.use_amp=true`.**

### Fix applied — Strategy 1b: `torch.compile(mode="reduce-overhead")`

`torch.compile` fuses the ResNet18 + VAE encoder + transformer into an optimized kernel graph at FP32, eliminating per-operator launch overhead. This is the correct path for a small model on CUDA.

Added to `lerobot_record.py`:
- `RecordConfig.compile_policy: bool = False` — new CLI flag `--compile_policy=true`
- After `make_policy()`, applies `torch.compile(policy.model, mode="reduce-overhead")`
- `_warmup_policy` bumped to 5 passes when `compile_policy=True` so the graph is fully compiled before episode 0

**Expected result**: inference frames improve from 11–15 Hz to 25–30 Hz. First warmup will take 10–30 s while the graph is captured.

**Windows caveat (resolved)**: `mode="reduce-overhead"` uses the `inductor` backend which requires Triton — Linux only. On Windows, the code now automatically uses `backend="cudagraphs"` instead. CUDA Graphs capture the GPU execution sequence and replay it without per-op Python dispatch overhead; no Triton required. On Linux/Mac, `mode="reduce-overhead"` (Triton/inductor) is used for additional kernel fusion.

**Risk**: `torch.compile` is PyTorch 2.0+ only (already required by lerobot). CUDA Graphs require static input shapes — ACT with fixed 480×640 images and 6-dim state qualifies. On rare graph-break inputs it can fall back to eager mode silently — check for `torch._dynamo` warnings if Hz doesn't improve.

### Updated inference command (with torch.compile)

```powershell
lerobot-record `
  --robot.type=so101_follower `
  --robot.port=COM3 `
  --robot.id=my_so_arm `
  --robot.calibration_dir=./calibration/robots/so_follower `
  --robot.cameras="{gripper_cam: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30, fourcc: MJPG}, top_cam: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30, fourcc: MJPG}}" `
  --policy.path=outputs/train/act_so101_pick_cube/checkpoints/030000/pretrained_model `
  --compile_policy=true `
  --dataset.repo_id=aakashv100/eval_so101-pick-cube `
  --dataset.num_episodes=10 `
  --dataset.single_task="Pick up the cube and place it in the bowl" `
  --display_cameras=true
```

---

## Issue 2 — Cached (queue-pop) frames run at ~25 Hz instead of 30 Hz

### Root cause
Even when ACT just pops an action from its queue (no GPU work), the loop runs at ~25 Hz, not 30 Hz. The overhead comes from the critical path of every frame regardless of inference:

| Step | Estimated cost |
|---|---|
| `robot.get_observation()` — read 2 cameras over USB + joint state over COM3 | ~15–20 ms |
| `robot_observation_processor` + `build_dataset_frame` | ~3–5 ms |
| `dataset.add_frame` (PNG write queue) | ~2–4 ms |
| `robot.send_action()` over COM3 serial | ~5–8 ms |
| **Total** | ~25–37 ms |

USB camera reads are synchronous and blocking. With two 640×480 MJPG cameras on the same USB controller, each `get_observation()` call waits for both frames serially. This alone consumes ~15–20 ms per loop, leaving insufficient headroom for the 33 ms target.

### Fix — Strategy 2: Async camera capture (not yet implemented)

Move camera reads into a background thread that continuously grabs frames. The main loop fetches the latest buffered frame non-blocking instead of waiting for a fresh capture. Typical implementation:

```python
# In each camera: thread calls cap.grab() in a loop; main thread calls cap.retrieve()
# ~1 frame of latency added (~33 ms), acceptable for control
```

This recovers ~15 ms from the critical path, bringing cached-frame overhead to ~10–22 ms and allowing the 33 ms budget to be met with room for `precise_sleep`.

**Risk**: Frames used for inference are 1 capture interval (~33 ms) stale. This is already the case in practice with USB buffering; no behavioral change expected.

---

## Issue 3 — No graceful recovery when eval cache dir exists from a failed run

### Root cause
`LeRobotDataset.create()` fails if the local cache directory already exists for the `repo_id`. A crashed or interrupted eval session leaves a partial cache at:

```
%USERPROFILE%\.cache\huggingface\lerobot\aakashv100\eval_so101-pick-cube
```

The error message does not tell you this; the process just raises on dataset creation.

### Current workaround

```powershell
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\huggingface\lerobot\aakashv100\eval_so101-pick-cube"
```

### Fix — Strategy 3: Auto-detect and prompt (not yet implemented)

In `record()` (`lerobot_record.py:593`), before `LeRobotDataset.create()`, check if the cache dir exists and either auto-delete with a warning or raise a clear error with the exact `Remove-Item` command embedded in the message.

---

## Issue 4 — Uneven loop timing produces inconsistent dataset frame timestamps

### Root cause
Because of Issues 1 and 2, the actual frame interval alternates between:
- ~58 ms on inference frames (once per 100 steps)
- ~40 ms on cached frames (99 out of 100 steps)

The dataset is declared at `fps=30` (33 ms target), but timestamps are recorded by wall clock (`time.perf_counter()`). The mismatch means frame intervals in the saved dataset vary by ±25 ms, which can degrade any future retraining on eval data.

### Fix dependency
Issues 1 and 2 must be resolved first. Once the loop runs consistently at ≥28 Hz, actual and declared fps will align.

---

## Summary table

| # | Issue | Severity | Fix | Status |
|---|---|---|---|---|
| 1 | Inference frames at 11–17 Hz (full FP32 forward pass) | High | `--compile_policy=true` (torch.compile, FP32 kernel fusion) | **Applied — add flag to command** |
| 2 | Cached frames at ~25 Hz (blocking USB camera reads) | Medium | Async camera capture in background thread | Pending |
| 3 | No graceful recovery from stale eval cache dir | Low | Check + clear cache dir before dataset create | Pending |
| 4 | Inconsistent frame timestamps in eval dataset | Low | Downstream of Issues 1 & 2 | Blocked on 1 & 2 |

---

## What to try next

1. **Run with `--compile_policy=true`** (replacing the removed `--policy.use_amp=true`). Warmup will take 10–30 s on first run while the graph compiles; subsequent episodes should show inference frames at ≥25 Hz instead of 11–17 Hz. Watch the warning log: `"Record loop is running slower (X Hz) than the target FPS"`.
2. If cached frames are still at ~25 Hz after compile, the USB camera read bottleneck (Issue 2) is confirmed — implement async capture next.
3. If both are resolved, recheck dataset frame timestamp variance (Issue 4).

## Notes

- **AMP (`--policy.use_amp=true`) is counterproductive on this setup** — tested 2026-06-26, slowed inference from ~17 Hz to 11–15 Hz. The GPU lacks FP16 tensor cores sized for ResNet18. Do not use.
- **Shoulder-lift motor fault** on disconnect (`Failed to disable torque on motor 'shoulder_lift'`) is a servo hardware fault (latched position error or overload). Not related to software. Power-cycle the arm and check for mechanical binding if it recurs.
