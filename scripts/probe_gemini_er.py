"""Sandbox smoke-test for Gemini Robotics-ER (not part of train/eval).

Sends one image + prompt to the Gemini API and prints the text response.
Does not connect to the arm, cameras (except optional grab), or any study pipeline.

Public API model id today: gemini-robotics-er-1.6-preview
("ER 2" is announced; if Google publishes a distinct id, pass --model.)

Usage:
    set GEMINI_API_KEY=...
    uv run python scripts/probe_gemini_er.py --image path\to\frame.png
    uv run python scripts/probe_gemini_er.py --webcam 1
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


DEFAULT_MODEL = "gemini-robotics-er-1.6-preview"
DEFAULT_PROMPT = (
    "You are looking at a robot workspace. List the objects you see, "
    "then give a short multi-step plan to pick up the cube and place it in the bowl. "
    "Do not invent motor commands; reason in natural language only."
)


def _read_image_bytes(path: Path) -> tuple[bytes, str]:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    return data, mime


def _grab_webcam(index: int) -> tuple[bytes, str]:
    import cv2

    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open webcam index {index}")
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Failed to read frame from webcam {index}")
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Failed to encode webcam frame as JPEG")
    return buf.tobytes(), "image/jpeg"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", type=Path, help="Path to a still image")
    src.add_argument("--webcam", type=int, help="OpenCV camera index (e.g. 1 for top cam)")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
        help="Or set GEMINI_API_KEY / GOOGLE_API_KEY",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("Set GEMINI_API_KEY (or pass --api-key).", file=sys.stderr)
        return 1

    if args.image is not None:
        image_bytes, mime = _read_image_bytes(args.image)
        source = str(args.image)
    else:
        image_bytes, mime = _grab_webcam(args.webcam)
        source = f"webcam:{args.webcam}"

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=args.api_key)
    print(f"model={args.model}  source={source}  bytes={len(image_bytes)}")
    response = client.models.generate_content(
        model=args.model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            args.prompt,
        ],
        config=types.GenerateContentConfig(
            temperature=0.5,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    print(response.text or "(empty response)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
