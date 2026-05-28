#!/usr/bin/env bash
# Teleoperate SO-101 follower + leader (hardware profile)
# Requires .env with ROBOT_PORT, LEADER_PORT (Linux device paths inside container)
set -euo pipefail
cd "$(dirname "$0")/../.."

ROBOT_PORT="${ROBOT_PORT:-/dev/ttyACM0}"
LEADER_PORT="${LEADER_PORT:-/dev/ttyACM1}"
ROBOT_ID="${ROBOT_ID:-my_so_arm}"
DISPLAY_DATA="${DISPLAY_DATA:-true}"

exec docker compose --profile hardware run --rm lerobot-hw \
  lerobot-teleoperate \
  --robot.type=so101_follower \
  --robot.port="${ROBOT_PORT}" \
  --robot.id="${ROBOT_ID}" \
  --robot.calibration_dir=./calibration/robots/so_follower \
  --robot.cameras="{gripper_cam: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, top_cam: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader \
  --teleop.port="${LEADER_PORT}" \
  --teleop.id="${ROBOT_ID}" \
  --teleop.calibration_dir=./calibration/teleoperators/so_leader \
  --display_data="${DISPLAY_DATA}" \
  "$@"
