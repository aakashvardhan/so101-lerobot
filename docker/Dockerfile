# SO-101 LeRobot — CPU dev image (feetech + viz + dataset extras)
# Build: docker compose build lerobot
# Run:   docker compose run --rm lerobot

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    MUJOCO_GL=egl \
    PATH=/lerobot/.venv/bin:$PATH

# System dependencies for LeRobot, OpenCV, Feetech serial, and audio/video
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    ca-certificates \
    socat \
    libglib2.0-0 \
    libegl1-mesa-dev \
    libgl1-mesa-glx \
    ffmpeg \
    libusb-1.0-0-dev \
    speech-dispatcher \
    libgeos-dev \
    portaudio19-dev \
    cmake \
    pkg-config \
    ninja-build \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && useradd --create-home --shell /bin/bash user_lerobot \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /lerobot
RUN chown -R user_lerobot:user_lerobot /lerobot

# Layer cache: dependency install before full source tree
COPY --chown=user_lerobot:user_lerobot pyproject.toml uv.lock README.md ./
COPY --chown=user_lerobot:user_lerobot src/ src/

USER user_lerobot

ENV HOME=/home/user_lerobot \
    HF_HOME=/home/user_lerobot/.cache/huggingface \
    HF_LEROBOT_HOME=/home/user_lerobot/.cache/huggingface/lerobot \
    TORCH_HOME=/home/user_lerobot/.cache/torch

RUN uv venv && uv sync --locked \
    --extra feetech \
    --extra viz \
    --extra dataset

# Application code (calibration, scripts, docker helpers)
COPY --chown=user_lerobot:user_lerobot . .

RUN chmod +x /lerobot/docker/entrypoint.sh

ENTRYPOINT ["/lerobot/docker/entrypoint.sh"]
CMD ["bash"]
