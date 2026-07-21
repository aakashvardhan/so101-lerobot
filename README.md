# SO-101 Robot Arm — LeRobot Setup (Windows)

LeRobot fork for the **SO-101** follower + leader arms (Feetech STS3215 servos), with a fix for motor IDs reverting after power cycle, repo-local calibration files, and helper scripts.

**Platform:** Windows 10/11 · PowerShell · Python 3.12+

---

## What's in this repo

| File / path | Description |
|-------------|-------------|
| `so-arm-guide.md` | Extended reference (commands originally written for macOS; use this README for Windows) |
| `scan_motor_ids.py` | Non-destructive bus scan — lists which motor IDs respond |
| `fix_motor_ids.py` | Interactive fix for wrist_roll (ID 5) and gripper (ID 6) with EEPROM lock |
| `calibration/` | Committed calibration JSON for `my_so_arm` (follower + leader) |
| `src/lerobot/motors/motors_bus.py` | Patched: writes `Lock=1` after ID/baud changes so EEPROM commits |

---

## Hardware

- SO-101 **follower** arm (robot being controlled)
- SO-101 **leader** arm (teleoperator you move by hand)
- USB serial adapter per arm (Waveshare or similar) + 5–7.4 V power per arm
- 2× USB cameras (optional): gripper-mounted + top/overview
- Windows PC with USB ports

### Motor ID map (both arms)

| Joint | ID |
|-------|----|
| shoulder_pan | 1 |
| shoulder_lift | 2 |
| elbow_flex | 3 |
| wrist_flex | 4 |
| wrist_roll | 5 |
| gripper | 6 |

On the **leader**, joint 6 is the trigger handle you squeeze.

---

## Prerequisites

1. **Windows 10 or 11** with administrator access (for USB drivers if needed).
2. **Python 3.12+** — [python.org/downloads](https://www.python.org/downloads/) (check “Add python.exe to PATH” during install).
3. **[uv](https://docs.astral.sh/uv/)** package manager (recommended):

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

4. **USB serial driver** — If Device Manager shows an unknown device when you plug in an arm, install **CH340** or **CP210x** drivers from your board vendor (common on clone servo controllers).
5. **Git** — [git-scm.com/download/win](https://git-scm.com/download/win)

---

## Step 1 — Clone and install dependencies

Open **PowerShell** and run:

```powershell
cd $env:USERPROFILE\Desktop
git clone https://github.com/ayushgawai/so101-lerobot.git
cd so101-lerobot
uv sync --extra so101
```

This creates `.venv` and installs LeRobot CLI tools (`lerobot-calibrate`, `lerobot-teleoperate`, etc.).

**Note:** `pyproject.toml` pins CUDA PyTorch via `uv`. For CPU-only, comment out the `[[tool.uv.index]]` / `[tool.uv.sources]` blocks for `pytorch-cu130` before `uv sync`, or install per [LeRobot docs](https://huggingface.co/docs/lerobot).

---

## Step 2 — Activate the environment (every new terminal)

```powershell
cd $env:USERPROFILE\Desktop\so101-lerobot   # adjust path if you cloned elsewhere
.\.venv\Scripts\Activate.ps1
```

If activation is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Optional: add activation to your PowerShell profile so you do not repeat it:

```powershell
Add-Content $PROFILE "`n# LeRobot SO-101`ncd '$PWD'; .\.venv\Scripts\Activate.ps1"
```

(Replace `$PWD` with your actual repo path after `cd` into the repo once.)

---

## Step 3 — Find serial ports (COM)

Ports change when you reboot or swap USB sockets. **Label each cable** after you identify it.

### Method A — `lerobot-find-port` (recommended)

Plug in **one** arm (USB + motor power). Run:

```powershell
lerobot-find-port
```

1. Note the listed ports.
2. When prompted, **unplug only that arm’s USB** and press Enter.
3. The script prints the port for that arm.
4. Replug USB and repeat for the other arm.

### Method B — Device Manager

1. Win + X → **Device Manager** → **Ports (COM & LPT)**.
2. Unplug/replug one arm and see which **COM** number appears or disappears.

**This setup (verify after reboot or if you swap USB ports):**

| Arm | Port |
|-----|------|
| Follower | `COM3` |
| Leader | `COM4` |

If Windows assigns different numbers, update the commands below accordingly.

---

## Step 4 — Scan motor IDs (sanity check)

With **all six motors** on one arm powered and daisy-chained, and only that arm’s USB connected:

```powershell
# Follower (COM3)
python scan_motor_ids.py --port COM3

# Leader (COM4) — run separately with only leader plugged in
python scan_motor_ids.py --port COM4
```

Expected: IDs `1` through `6` listed, ending with `OK: all expected IDs 1..6 present.`

If IDs **5** or **6** are missing, or two joints share ID 5, see [Motor ID bug](#motor-id-bug-and-fix) and [Step 4b](#step-4b--fix-motor-ids-optional).

---

## Step 5 — Set up motor IDs (first time or new servos)

Only needed **once per arm** (or after replacing a servo). Connect **one motor at a time** when the script asks.

**Follower:**

```powershell
lerobot-setup-motors --robot.type=so101_follower --robot.port=COM3 --robot.id=my_so_arm
```

**Leader:**

```powershell
lerobot-setup-motors --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=my_so_arm
```

Follow prompts: gripper → wrist_roll → … → shoulder_pan. The patched `motors_bus.py` locks EEPROM after each write so IDs should survive reboot.

---

## Step 4b — Fix motor IDs (optional)

If wrist_roll and gripper both revert to ID 5 after power cycle, use the standalone script (connect **one** motor at a time when prompted):

```powershell
# Follower
python fix_motor_ids.py --port COM3

# Leader (if needed)
python fix_motor_ids.py --port COM4
```

Default targets: `wrist_roll` → 5, `gripper` → 6. Power-cycle each motor when asked to confirm EEPROM persistence.

---

## Step 6 — Calibrate each arm separately

**Only plug in the arm you are calibrating** (one USB cable).

Calibration is saved to:

- `./calibration/robots/so_follower/my_so_arm.json`
- `./calibration/teleoperators/so_leader/my_so_arm.json`

### Follower

```powershell
lerobot-calibrate --robot.type=so101_follower --robot.port=COM3 --robot.id=my_so_arm
```

### Leader

```powershell
lerobot-calibrate --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=my_so_arm
```

**During calibration:**

1. Move the arm to the **middle** of each joint’s range → press Enter.
2. Move every joint through its **full range slowly** (all six, including wrist_roll).
3. Open and close the gripper (follower) or trigger (leader) fully.
4. Press Enter to save.

---

## Step 7 — Find camera indices

Plug in both USB cameras, then either:

```powershell
lerobot-find-cameras
```

Or a quick OpenCV scan:

```powershell
python -c "import cv2
for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        ret, _ = cap.read()
        print(f'Camera {i}:', 'OK' if ret else 'no frame')
        cap.release()"
```

Typical mapping (verify on your machine):

| Name | Index | Role |
|------|-------|------|
| gripper_cam | 0 | On wrist, faces workspace |
| top_cam | 1 | Fixed above table, full workspace |

**Top camera:** mount rigidly 40–60 cm above the table, ~30–45° down; avoid seeing the leader arm or your hands.

Preview (press **q** to quit):

```powershell
python -c "import cv2
cap0, cap1 = cv2.VideoCapture(0), cv2.VideoCapture(1)
while True:
    r0, f0 = cap0.read(); r1, f1 = cap1.read()
    if r0: cv2.imshow('Gripper Cam', f0)
    if r1: cv2.imshow('Top Cam', f1)
    if cv2.waitKey(1) & 0xFF == ord('q'): break
cap0.release(); cap1.release(); cv2.destroyAllWindows()"
```

If a feed is black on Windows, try another index or close apps that lock the camera (Teams, Camera app).

---

## Step 8 — Teleoperate

Plug in **both** arms (follower + leader). Move the leader; the follower mirrors it.

### Without cameras

```powershell
lerobot-teleoperate `
  --robot.type=so101_follower `
  --robot.port=COM3 `
  --robot.id=my_so_arm `
  --robot.calibration_dir=./calibration/robots/so_follower `
  --teleop.type=so101_leader `
  --teleop.port=COM4 `
  --teleop.id=my_so_arm `
  --teleop.calibration_dir=./calibration/teleoperators/so_leader
```

### With cameras + Rerun viewer

```powershell
lerobot-teleoperate `
  --robot.type=so101_follower `
  --robot.port=COM3 `
  --robot.id=my_so_arm `
  --robot.calibration_dir=./calibration/robots/so_follower `
  --robot.cameras="{gripper_cam: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, top_cam: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" `
  --teleop.type=so101_leader `
  --teleop.port=COM4 `
  --teleop.id=my_so_arm `
  --teleop.calibration_dir=./calibration/teleoperators/so_leader `
  --display_data=true
```

Press **Ctrl+C** to stop. Rerun opens automatically when `--display_data=true`.

---

## Step 9 — Record a dataset (Hugging Face)

One-time login:

```powershell
huggingface-cli login
```

Create a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

Record demonstrations (both arms + cameras):

```powershell
lerobot-record `
  --robot.type=so101_follower `
  --robot.port=COM3 `
  --robot.id=my_so_arm `
  --robot.calibration_dir=./calibration/robots/so_follower `
  --robot.cameras="{gripper_cam: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, top_cam: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" `
  --teleop.type=so101_leader `
  --teleop.port=COM4 `
  --teleop.id=my_so_arm `
  --teleop.calibration_dir=./calibration/teleoperators/so_leader `
  --dataset.repo_id=YOUR_USERNAME/so101-pick-cube `
  --dataset.num_episodes=30 `
  --dataset.single_task="Pick up the cube and place it in the bowl"
```

- **Space** — start/stop each episode  
- **Ctrl+C** — finish recording early  
- Replace `YOUR_USERNAME/so101-pick-cube` with your Hub repo id  

**Windows note:** Some dataset video features depend on `torchcodec`, which has limited Windows support in this repo’s pins. If recording fails on video encoding, check LeRobot issues or record without cameras first to isolate the problem.

---

## Motor ID bug and fix

**Problem:** After power cycle, gripper (ID 6) and wrist_roll (ID 5) can both appear as ID 5 → bus collision → `Missing motor IDs: 5, 6` during calibrate/teleop.

**Cause:** STS3215 EEPROM must be unlocked (`Lock=0`), ID written, then **re-locked** (`Lock=1`). Stock LeRobot did not always re-lock, so some firmware batches did not commit ID 6.

**Fix in this repo:** `src/lerobot/motors/motors_bus.py` writes `Lock=1` after ID and baud-rate assignment. `lerobot-setup-motors` and `fix_motor_ids.py` follow the same sequence.

**Diagnose:** Run `python scan_motor_ids.py --port COM3`. If 5 and 6 are missing, disconnect wrist_roll only and scan again; if ID 5 appears alone, gripper likely reverted from 6 → 5.

**If a servo still reverts:** Re-run `fix_motor_ids.py`, ensure stable power, then use **Feetech FD** tool (Windows) to update firmware, or replace the servo.

---

## Troubleshooting (Windows)

| Issue | What to try |
|-------|-------------|
| `Access is denied` on COM port | Close other apps using the port; unplug/replug; Device Manager → uninstall port → replug |
| Port not listed | Install CH340/CP210x driver; try another USB port (USB 2.0 often more reliable) |
| `Missing motor IDs: 5, 6` | [Step 4b](#step-4b--fix-motor-ids-optional) + [scan](#step-4--scan-motor-ids-sanity-check) |
| Wrong arm moves / jitter | Re-calibrate with only one arm connected; confirm `COM` ports |
| Camera index wrong | `lerobot-find-cameras`; swap `index_or_path` 0 and 1 in `--robot.cameras` |
| `lerobot-*` not found | Activate `.venv` ([Step 2](#step-2--activate-the-environment-every-new-terminal)) |
| PowerShell line breaks | Use backtick `` ` `` at end of line, or paste as one line |

List all COM ports quickly:

```powershell
python -c "from serial.tools import list_ports; print([p.device for p in list_ports.comports()])"
```

---

## Upstream docs

- [HuggingFace LeRobot](https://github.com/huggingface/lerobot)
- Official SO-101 assembly: `src/lerobot/robots/so_follower/so101.md`
- Extended notes: `so-arm-guide.md` (replace `/dev/cu.*` with `COMx` and `source .venv` with `.\.venv\Scripts\Activate.ps1`)

---

## Quick reference

```powershell
.\.venv\Scripts\Activate.ps1
python scan_motor_ids.py --port COM3
lerobot-calibrate --robot.type=so101_follower --robot.port=COM3 --robot.id=my_so_arm
lerobot-calibrate --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=my_so_arm
lerobot-teleoperate --robot.type=so101_follower --robot.port=COM3 --robot.id=my_so_arm --robot.calibration_dir=./calibration/robots/so_follower --teleop.type=so101_leader --teleop.port=COM4 --teleop.id=my_so_arm --teleop.calibration_dir=./calibration/teleoperators/so_leader --display_data=true
```
