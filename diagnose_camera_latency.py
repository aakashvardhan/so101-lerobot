"""Quick camera latency diagnostic for Windows / OpenCV.

Measures, per backend (MSMF vs DSHOW) and per FOURCC (default vs MJPG):
  - negotiated fourcc / resolution / fps
  - mean grab->retrieve read latency
  - effective throughput (fps) and frame staleness

Usage:
    uv run python diagnose_camera_latency.py --index 0
"""

import argparse
import os
import platform
import time

if platform.system() == "Windows":
    os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

import cv2

BACKENDS = {"MSMF": cv2.CAP_MSMF, "DSHOW": cv2.CAP_DSHOW, "ANY": cv2.CAP_ANY}


def fourcc_to_str(v: float) -> str:
    n = int(v)
    return "".join(chr((n >> 8 * i) & 0xFF) for i in range(4))


def bench(index: int, backend_name: str, backend_id: int, use_mjpg: bool, w: int, h: int, fps: int, n: int):
    cap = cv2.VideoCapture(index, backend_id)
    if not cap.isOpened():
        print(f"  [{backend_name:5s} mjpg={use_mjpg}] could not open index {index}")
        return
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if use_mjpg:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)

    aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    afps = cap.get(cv2.CAP_PROP_FPS)
    afourcc = fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))

    for _ in range(10):  # warmup
        cap.read()

    read_ms = []
    t0 = time.perf_counter()
    ok_count = 0
    for _ in range(n):
        s = time.perf_counter()
        ok, _frame = cap.read()
        read_ms.append((time.perf_counter() - s) * 1e3)
        ok_count += int(ok)
    total = time.perf_counter() - t0
    cap.release()

    read_ms.sort()
    mean = sum(read_ms) / len(read_ms)
    p95 = read_ms[int(0.95 * len(read_ms)) - 1]
    eff_fps = ok_count / total if total > 0 else 0
    print(
        f"  [{backend_name:5s} mjpg={str(use_mjpg):5s}] "
        f"fourcc={afourcc} {aw}x{ah}@{afps:.0f} | "
        f"read mean={mean:6.1f}ms p95={p95:6.1f}ms | eff_fps={eff_fps:5.1f}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--frames", type=int, default=120)
    args = ap.parse_args()

    print(f"OpenCV {cv2.__version__} on {platform.system()}")
    print(f"Camera index {args.index}, target {args.width}x{args.height}@{args.fps}, {args.frames} frames/run\n")

    for bname in ("MSMF", "DSHOW"):
        bid = BACKENDS[bname]
        for mjpg in (False, True):
            bench(args.index, bname, bid, mjpg, args.width, args.height, args.fps, args.frames)


if __name__ == "__main__":
    main()
