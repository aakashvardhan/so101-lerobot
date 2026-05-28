#!/usr/bin/env bash
# Record a dataset (hardware profile). Set DATASET_REPO_ID and NUM_EPISODES in env or pass flags.
set -euo pipefail
cd "$(dirname "$0")/../.."

ROBOT_PORT="${ROBOT_PORT:-/dev/ttyACM0}"
LEADER_PORT="${LEADER_PORT:-/dev/ttyACM1}"
ROBOT_ID="${ROBOT_ID:-my_so_arm}"
DATASET_REPO_ID="${DATASET_REPO_ID:-}"
NUM_EPISODES="${NUM_EPISODES:-30}"
SINGLE_TASK="${SINGLE_TASK:-Pick up the cube and place it in the bowl}"

if [ -z "${DATASET_REPO_ID}" ]; then
  echo "Set DATASET_REPO_ID (e.g. username/so101-pick-cube) in .env or the environment." >&2
  exit 1
fi

exec docker compose --profile hardware run --rm lerobot-hw \
  lerobot-record \
  --robot.type=so101_follower \
  --robot.port="${ROBOT_PORT}" \
  --robot.id="${ROBOT_ID}" \
  --robot.calibration_dir=./calibration/robots/so_follower \
  --robot.cameras="{gripper_cam: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, top_cam: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader \
  --teleop.port="${LEADER_PORT}" \
  --teleop.id="${ROBOT_ID}" \
  --teleop.calibration_dir=./calibration/teleoperators/so_leader \
  --dataset.repo_id="${DATASET_REPO_ID}" \
  --dataset.num_episodes="${NUM_EPISODES}" \
  --dataset.single_task="${SINGLE_TASK}" \
  "$@"
