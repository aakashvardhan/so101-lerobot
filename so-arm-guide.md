# SO-101 Arm Guide

Hardware: SO-101 follower + SO-101 leader · Feetech STS3215 servos · Mac M1

---

## First-Time Install

Clone and install dependencies (one-time):

```bash
cd ~/Documents/GitHub
git clone https://github.com/ayushgawai/so101-lerobot.git
cd so101-lerobot
uv sync --extra feetech --extra viz --extra dataset
```

---

## Environment

Run from inside the repo directory. Activate the venv once per terminal session:

```bash
cd ~/Documents/GitHub/so101-lerobot
source .venv/bin/activate
```

To make it permanent (never think about it again):

```bash
echo 'source ~/Documents/GitHub/so101-lerobot/.venv/bin/activate' >> ~/.zshrc
```

---

## Ports

Ports can change on reboot. Always check first:

```bash
ls /dev/cu.usbmodem*
```

Current known ports (verify before use):

| Arm      | Port                            |
|----------|---------------------------------|
| Follower | `/dev/cu.usbmodem5B3E1225231`   |
| Leader   | `/dev/cu.usbmodem5B3E1218771`   |

---

## Motor ID Map

| Joint         | ID |
|---------------|----|
| shoulder_pan  | 1  |
| shoulder_lift | 2  |
| elbow_flex    | 3  |
| wrist_flex    | 4  |
| wrist_roll    | 5  |
| gripper       | 6  |

Same mapping applies to both follower and leader arms.
On the leader arm, "gripper" = the trigger handle you squeeze.

---

## Setup Motors

Only needed once per arm, or after replacing a servo.
Connect **one motor at a time** when prompted.

```bash
# Follower
lerobot-setup-motors --robot.type=so101_follower --robot.port=/dev/cu.usbmodem5B3E1225231 --robot.id=my_so_arm

# Leader
lerobot-setup-motors --teleop.type=so101_leader --teleop.port=/dev/cu.usbmodem5B3E1218771 --teleop.id=my_so_arm
```

---

## Calibrate

Calibrate each arm **separately** — only that arm's USB plugged in.

**Follower:**
```bash
lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/cu.usbmodem5B3E1225231 --robot.id=my_so_arm
```

**Leader:**
```bash
lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/cu.usbmodem5B3E1218771 --teleop.id=my_so_arm
```

**During calibration:**
1. Move arm to middle of range → press Enter
2. Move joints through full range, slowly — **both arms:** all six including `wrist_roll` (joint table is printed by the script)
3. Open and close the gripper/trigger fully
4. Press Enter to save

Calibration files are saved in two places:
- **Repo (committed to git):** `./calibration/robots/so_follower/my_so_arm.json` and `./calibration/teleoperators/so_leader/my_so_arm.json`
- **HF cache:** `~/.cache/huggingface/lerobot/calibration/...`

The commands below use the repo-local calibration files so they work on any machine that clones this repo.

---

## Cameras

### Find camera indices

```bash
python -c "
import cv2
for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        ret, _ = cap.read()
        print(f'Camera {i}:', 'OK' if ret else 'no frame')
        cap.release()
"
```

Current setup:

| Camera      | Index | Position                              |
|-------------|-------|---------------------------------------|
| gripper_cam | 0     | Mounted on wrist, faces workspace     |
| top_cam     | 1     | Fixed above/behind arm, sees full workspace |

### Preview both cameras live

```bash
python -c "
import cv2
cap0 = cv2.VideoCapture(0)
cap1 = cv2.VideoCapture(1)
while True:
    ret0, f0 = cap0.read()
    ret1, f1 = cap1.read()
    if ret0: cv2.imshow('Gripper Cam', f0)
    if ret1: cv2.imshow('Top Cam', f1)
    if cv2.waitKey(1) & 0xFF == ord('q'): break
cap0.release()
cap1.release()
cv2.destroyAllWindows()
"
```

### Top cam positioning guide

- Height: 40–60cm above the table, behind or to the side of the follower
- Angle: tilted ~30–45° down to capture the full table surface
- Must be **rigidly fixed** — any movement contaminates the dataset
- Should see: full follower arm, entire reach area, objects on table
- Should NOT see: leader arm, your hands, backlighting behind the arm

### Camera rotation

If the camera is 90° off, use `rotation: 90` or `rotation: -90` in the config.
When using rotation, swap width and height (e.g. `width: 480, height: 640` for a 640×480 sensor).

---

## Teleoperate

Both arms plugged in. Move the leader — the follower mirrors it.

### Without cameras

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/cu.usbmodem5B3E1225231 \
  --robot.id=my_so_arm \
  --robot.calibration_dir=./calibration/robots/so_follower \
  --teleop.type=so101_leader \
  --teleop.port=/dev/cu.usbmodem5B3E1218771 \
  --teleop.id=my_so_arm \
  --teleop.calibration_dir=./calibration/teleoperators/so_leader
```

### With both cameras + live Rerun viewer

```bash
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/cu.usbmodem5B3E1225231 \
  --robot.id=my_so_arm \
  --robot.calibration_dir=./calibration/robots/so_follower \
  --robot.cameras="{gripper_cam: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, top_cam: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader \
  --teleop.port=/dev/cu.usbmodem5B3E1218771 \
  --teleop.id=my_so_arm \
  --teleop.calibration_dir=./calibration/teleoperators/so_leader \
  --display_data=true
```

The Rerun window opens **automatically** when `--display_data=true` is set.
Press `Ctrl+C` to stop.

---

## Record a Dataset

Login to Hugging Face (one-time):

```bash
huggingface-cli login
```

Get your token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

Then record:

```bash
lerobot-record \
  --robot.type=so101_follower \
  --robot.port=/dev/cu.usbmodem5B3E1225231 \
  --robot.id=my_so_arm \
  --robot.calibration_dir=./calibration/robots/so_follower \
  --robot.cameras="{gripper_cam: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, top_cam: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader \
  --teleop.port=/dev/cu.usbmodem5B3E1218771 \
  --teleop.id=my_so_arm \
  --teleop.calibration_dir=./calibration/teleoperators/so_leader \
  --dataset.repo_id=ayushgawai/so101-pick-cube \
  --dataset.num_episodes=30 \
  --dataset.single_task="Pick up the cube and place it in the bowl"
```

- `repo_id` format: `<hf_username>/<dataset_name>` — dataset is created automatically on HF
- `num_episodes`: number of demonstrations to record
- `single_task`: plain text description of what the arm is doing
- Press **Space** to start/stop each episode, **Ctrl+C** to finish early

---

---

# Debug Reference

---

## Scan All Motors on a Port

Shows every motor ID currently responding on the bus.
Connect all motors for the arm first.

```bash
python -c "
import scservo_sdk as scs
ph = scs.PortHandler('/dev/cu.usbmodem5B3E1225231')
ph.openPort(); ph.setBaudRate(1_000_000)
pkt = scs.PacketHandler(0)
for id_ in range(1, 10):
    model, comm, err = pkt.ping(ph, id_)
    if comm == scs.COMM_SUCCESS:
        print(f'ID={id_}  model={model}')
ph.closePort()
"
```

Expected output — all 6 present:
```
ID=1  model=777
ID=2  model=777
...
ID=6  model=777
```

---

## Diagnose Duplicate / Missing IDs

**Symptom:** calibration or teleoperate throws `Missing motor IDs: 5, 6`

**Cause:** Two motors share the same ID (usually both `wrist_roll` and `gripper` are on ID=5).
When two motors share an ID they jam each other — neither appears in the scan.

**Diagnose:** disconnect `wrist_roll` from the bus, scan again. If the gripper now appears at ID=5 instead of 6, it has reverted.

---

## Fix a Wrong Motor ID

Connect **only the problem motor** to the board, then run:

```bash
# Example: motor is currently at ID=5, needs to be ID=6
python -c "
import time, scservo_sdk as scs
CURRENT_ID = 5
TARGET_ID  = 6
ph = scs.PortHandler('/dev/cu.usbmodem5B3E1225231')
ph.openPort(); ph.setBaudRate(1_000_000)
pkt = scs.PacketHandler(0)
pkt.write1ByteTxRx(ph, CURRENT_ID, 40, 0); time.sleep(0.05)   # torque off
pkt.write1ByteTxRx(ph, CURRENT_ID, 55, 0); time.sleep(0.05)   # Lock=0 unlock EEPROM
pkt.write1ByteTxRx(ph, CURRENT_ID,  5, TARGET_ID); time.sleep(0.05)  # write new ID
pkt.write1ByteTxRx(ph, TARGET_ID,  55, 1); time.sleep(0.05)   # Lock=1 commit EEPROM
_, comm, _ = pkt.ping(ph, TARGET_ID)
print('OK' if comm == scs.COMM_SUCCESS else 'FAILED')
ph.closePort()
"
```

Then **power-cycle that motor** (unplug power, wait 3 sec, replug) and verify:

```bash
python -c "
import scservo_sdk as scs
ph = scs.PortHandler('/dev/cu.usbmodem5B3E1225231')
ph.openPort(); ph.setBaudRate(1_000_000)
pkt = scs.PacketHandler(0)
_, comm, _ = pkt.ping(ph, 6)
print('BURNED IN' if comm == scs.COMM_SUCCESS else 'STILL REVERTING')
ph.closePort()
"
```

---

## Re-burn IDs 5 and 6 (with all motors connected)

Use after full setup to commit both IDs to EEPROM in one shot:

```bash
python -c "
import time, scservo_sdk as scs
ph = scs.PortHandler('/dev/cu.usbmodem5B3E1225231')
ph.openPort(); ph.setBaudRate(1_000_000)
pkt = scs.PacketHandler(0)
for id_ in [5, 6]:
    pkt.write1ByteTxRx(ph, id_, 40, 0); time.sleep(0.05)
    pkt.write1ByteTxRx(ph, id_, 55, 0); time.sleep(0.05)
    pkt.write1ByteTxRx(ph, id_,  5, id_); time.sleep(0.05)
    pkt.write1ByteTxRx(ph, id_, 55, 1); time.sleep(0.05)
    _, comm, _ = pkt.ping(ph, id_)
    print(f'ID={id_}:', 'BURNED IN' if comm == scs.COMM_SUCCESS else 'FAILED')
ph.closePort()
"
```

---

## Why IDs Reset After Reboot

STS3215 servos store their ID in EEPROM (permanent) but require the `Lock` register (SRAM, addr 55) to be `0` before writing. The original LeRobot `setup_motor` code never re-locked (`Lock=1`) after writing, leaving some servo firmware batches with uncommitted EEPROM writes that revert on power cycle.

**Fix is already applied** in `src/lerobot/motors/motors_bus.py` — `setup_motor` now writes `Lock=1` after every ID assignment. Running `lerobot-setup-motors` will be permanent going forward.

---

## If a Motor Still Reverts After the Fix

The EEPROM on that servo may be worn or have a firmware bug.

Options in order of effort:
1. Re-run the fix command above (with `Lock=1`) and power-cycle to verify
2. Update servo firmware using **Feetech FD tool** (Windows — use Parallels on Mac)
3. Replace the servo
