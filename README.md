# SO-101 Robot Arm — LeRobot Setup

**by Ayush Gawai** · M1 Mac · SO-101 follower + leader arms · Feetech STS3215 servos

A working setup of HuggingFace LeRobot for the SO-101 robot arm, including a permanent fix for the motor ID revert bug and a full operation guide.

---

## What's in this repo

| File | Description |
|------|-------------|
| `so-arm-guide.md` | Full setup guide — calibration, teleoperation, cameras, recording, and debug reference |
| `docker/README.md` | Docker Compose setup — dev shell, hardware profile, GPU profile |
| `docker-compose.yml` | Cross-platform services (`lerobot`, `lerobot-hw`, `lerobot-gpu`) |
| `fix_motor_ids.py` | Standalone script to diagnose and fix Feetech STS3215 motor ID collisions |
| `src/lerobot/motors/motors_bus.py` | Patched with EEPROM Lock=1 fix to prevent motor IDs reverting after reboot |

---

## The Motor ID Bug (and Fix)

**Problem:** After every power cycle, the gripper (ID=6) and wrist_roll (ID=5) on Feetech STS3215 servos would both revert to ID=5, causing bus collisions and breaking calibration.

**Root cause:** The original LeRobot `setup_motor` code never re-locked EEPROM (`Lock=1`) after writing the ID. Some STS3215 firmware batches require an explicit re-lock to commit the write permanently.

**Fix:** `motors_bus.py` now writes `Lock=1` after every ID and baud-rate assignment, making it permanent across reboots.

---

## Hardware

- SO-101 follower arm
- SO-101 leader arm
- 2x USB cameras (gripper-mounted + top/overview)
- Mac M1

---

## Docker (cross-platform)

Reproducible environment without local Python/torch setup (Mac M-series, Windows, Linux):

```bash
cp .env.example .env
docker compose build
docker compose run --rm lerobot lerobot-info
```

Hardware teleop on **Linux** uses the `hardware` profile; on **Mac/Windows**, use Docker for deps and run `lerobot-*` on the host venv — see [docker/README.md](docker/README.md).

---

## Quick Start

```bash
# Activate environment
source .venv/bin/activate

# Calibrate follower (one arm at a time)
lerobot-calibrate --robot.type=so101_follower --robot.port=/dev/cu.usbmodem5B3E1225231 --robot.id=my_so_arm

# Calibrate leader
lerobot-calibrate --teleop.type=so101_leader --teleop.port=/dev/cu.usbmodem5B3E1218771 --teleop.id=my_so_arm

# Teleoperate with cameras
lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port=/dev/cu.usbmodem5B3E1225231 \
  --robot.id=my_so_arm \
  --robot.cameras="{gripper_cam: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, top_cam: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader \
  --teleop.port=/dev/cu.usbmodem5B3E1218771 \
  --teleop.id=my_so_arm \
  --display_data=true
```

See `so-arm-guide.md` for the full reference including debug commands.

---

## Based on

[HuggingFace LeRobot](https://github.com/huggingface/lerobot) — open-source robotics library.
