"""Probe whether the camera honors MJPG when FOURCC is set BEFORE resolution.

Usage: uv run python probe_mjpg.py --index 0
"""

import argparse
import os
import platform
import time

if platform.system() == "Windows":
    os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

import cv2


def fourcc_to_str(v: float) -> str:
    n = int(v)
    return "".join(chr((n >> 8 * i) & 0xFF) for i in range(4))


def run(index: int, fourcc_first: bool, w: int, h: int, fps: int, n: int):
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"  [fourcc_first={fourcc_first}] could not open index {index}")
        return
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if fourcc_first:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, fps)
    else:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FPS, fps)

    afourcc = fourcc_to_str(cap.get(cv2.CAP_PROP_FOURCC))
    aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    afps = cap.get(cv2.CAP_PROP_FPS)

    for _ in range(10):
        cap.read()

    read_ms = []
    t0 = time.perf_counter()
    for _ in range(n):
        s = time.perf_counter()
        cap.read()
        read_ms.append((time.perf_counter() - s) * 1e3)
    total = time.perf_counter() - t0
    cap.release()

    read_ms.sort()
    mean = sum(read_ms) / len(read_ms)
    eff = n / total if total > 0 else 0
    print(
        f"  [fourcc_first={str(fourcc_first):5s}] negotiated fourcc={afourcc} {aw}x{ah}@{afps:.0f} | "
        f"read mean={mean:6.1f}ms | eff_fps={eff:5.1f}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--frames", type=int, default=120)
    args = ap.parse_args()

    print(f"OpenCV {cv2.__version__}, index {args.index}, target {args.width}x{args.height}@{args.fps}\n")
    run(args.index, True, args.width, args.height, args.fps, args.frames)
    run(args.index, False, args.width, args.height, args.fps, args.frames)


if __name__ == "__main__":
    main()
