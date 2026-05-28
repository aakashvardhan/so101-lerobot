# Docker setup (SO-101 LeRobot)

Reproducible Linux environment with the same dependencies as local install:

```bash
uv sync --extra feetech --extra viz --extra dataset
```

Works on **macOS (Apple Silicon)**, **Windows (Docker Desktop + WSL2)**, and **Linux**. USB arms and webcams inside the container are **best on native Linux**; Mac/Windows use a **hybrid** workflow (see below).

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 4.x+ (Mac / Windows) or Docker Engine (Linux)
- Docker Compose v2 (`docker compose version`)
- **GPU profile only:** NVIDIA driver + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) on Linux

## Quick start

```bash
cp .env.example .env
docker compose build
docker compose run --rm lerobot lerobot-info
```

Interactive shell:

```bash
docker compose run --rm lerobot
# or
bash docker/scripts/shell.sh
```

## Services

| Service | Profile | Purpose |
|---------|---------|---------|
| `lerobot` | (default) | Dev shell, dataset tools, diagnostics |
| `lerobot-hw` | `hardware` | Teleop / calibrate / record with USB + cameras |
| `lerobot-gpu` | `gpu` | Training and eval on NVIDIA GPUs |

## Platform matrix

| Host | Dev shell | USB arms in container | Webcams in container |
|------|-----------|----------------------|----------------------|
| Linux | Yes | Yes — map `/dev/ttyACM*` | Yes — map `/dev/video*` |
| macOS (M-series) | Yes | **Unreliable** — use hybrid (below) | **No** — use hybrid |
| Windows + WSL2 | Yes | Possible via [usbipd-win](https://github.com/dorssel/usbipd-win) → WSL device | Same as USB |

### Hybrid workflow (Mac / Windows)

1. **Dependencies in Docker:** `docker compose run --rm lerobot` for scripts, dataset editing, `fix_motor_ids.py`, etc.
2. **Hardware on the host:** same lockfile install locally:

   ```bash
   uv sync --extra feetech --extra viz --extra dataset
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   lerobot-teleoperate ...     # use host ports: /dev/cu.usbmodem* or COM*
   ```

The image still gives teammates and CI an identical dependency tree.

## Configuration

Copy [`.env.example`](../.env.example) to `.env` and set:

- `ROBOT_PORT` / `LEADER_PORT` — serial paths **inside the container** (e.g. `/dev/ttyACM0`), not macOS `cu.usbmodem` paths
- `ROBOT_DEVICE` / `LEADER_DEVICE` — host nodes to pass through (hardware profile)
- `HF_TOKEN` — optional, for `lerobot-record` / Hub push
- `RERUN_HOST` — default `host.docker.internal` for Rerun viewer on the host

## Hardware profile (Linux)

1. Plug in follower and leader; find ports on the host:

   ```bash
   ls /dev/ttyACM*
   ```

2. Set `.env` to match (example):

   ```env
   ROBOT_DEVICE=/dev/ttyACM0
   LEADER_DEVICE=/dev/ttyACM1
   ROBOT_PORT=/dev/ttyACM0
   LEADER_PORT=/dev/ttyACM1
   ```

3. Teleoperate (both cameras + Rerun):

   ```bash
   docker compose --profile hardware run --rm lerobot-hw bash docker/scripts/teleop.sh
   ```

   Or find ports inside the container:

   ```bash
   bash docker/scripts/find-port.sh
   ```

4. Record a dataset:

   ```bash
   export DATASET_REPO_ID=youruser/so101-pick-cube
   docker compose --profile hardware run --rm lerobot-hw bash docker/scripts/record.sh
   ```

### Windows + WSL2 USB (optional)

1. Install [usbipd-win](https://github.com/dorssel/usbipd-win) on Windows.
2. Attach each arm to WSL: `usbipd bind`, `usbipd attach --wsl --busid ...`
3. In WSL, confirm `/dev/ttyACM*` and set `.env` accordingly.
4. Run compose from the WSL checkout (not PowerShell on `C:\` unless using WSL paths).

## Rerun visualization

With `--display_data=true`, start the [Rerun viewer](https://www.rerun.io/) on the **host**. Compose forwards ports `9876` and `8812`. Set `RERUN_HOST=host.docker.internal` (default on Docker Desktop).

## GPU profile

Linux host with NVIDIA GPU only (not Mac M-series GPU passthrough).

```bash
docker compose --profile gpu build lerobot-gpu
docker compose --profile gpu run --rm lerobot-gpu nvidia-smi
docker compose --profile gpu run --rm lerobot-gpu lerobot-train --help
```

Optional policy extras at build time:

```bash
LEROBOT_EXTRAS=training,pi docker compose --profile gpu build lerobot-gpu
```

## Volumes

- **Repo bind mount** `.:/lerobot` — live code and `calibration/`
- **`lerobot-venv`** — preserves the image-built `.venv` (host mount does not wipe it)
- **`hf-cache`** — Hugging Face Hub cache across runs

## Notes

- **torchcodec** is not installed on `linux/arm64` (Apple Silicon Docker VM). Dataset recording uses `av` from the dataset extra.
- **Do not** use `lerobot[all]` in the image — simulation extras conflict with the base numpy pin (see `pyproject.toml`).
- Rebuild after dependency changes: `docker compose build --no-cache`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `lerobot: command not found` | Use `docker compose run --rm lerobot bash` — PATH includes `/lerobot/.venv/bin` |
| Empty `.venv` after mount | Ensure `lerobot-venv` volume is defined (see `docker-compose.yml`) |
| Permission denied on `/dev/ttyACM*` | Add user to `dialout` on host, or use `privileged: true` (already set on `lerobot-hw`) |
| Rerun does not connect | Open Rerun on host; check `RERUN_HOST` and published ports |
| Build fails on GPU image | Confirm NVIDIA toolkit; try building CPU image first |

See also [so-arm-guide.md](../so-arm-guide.md) for arm-specific commands and calibration paths.
