"""Swap two camera keys in a LeRobot v3.0 dataset (fixes mislabeled cameras).

The video content under `observation.images.gripper_cam` and
`observation.images.top_cam` was swapped at recording time. This relabels
everything consistently:
  - video folder names
  - episodes parquet columns (videos/<key>/* and stats/observation.images.<key>/*)
  - meta/info.json features
  - meta/stats.json entries

The operation is a pure swap and is self-inverse (running twice = no-op).

Usage:
  python scripts/swap_camera_keys.py --root hf_data/so101-pick-cube            # dry run
  python scripts/swap_camera_keys.py --root hf_data/so101-pick-cube --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

KEY_A = "observation.images.gripper_cam"
KEY_B = "observation.images.top_cam"


def swap_in_str(s: str) -> str:
    sentinel = "\x00SWAP\x00"
    return s.replace(KEY_A, sentinel).replace(KEY_B, KEY_A).replace(sentinel, KEY_B)


def swap_video_folders(root: Path, apply: bool) -> None:
    vroot = root / "videos"
    a, b = vroot / KEY_A, vroot / KEY_B
    tmp = vroot / "__tmp_swap__"
    print(f"[videos] rename {a.name} <-> {b.name}")
    if apply:
        a.rename(tmp)
        b.rename(a)
        tmp.rename(b)


def swap_info(root: Path, apply: bool) -> None:
    p = root / "meta" / "info.json"
    info = json.loads(p.read_text(encoding="utf-8"))
    feats = info["features"]
    feats[KEY_A], feats[KEY_B] = feats[KEY_B], feats[KEY_A]
    print("[info.json] swapped features entries")
    if apply:
        p.write_text(json.dumps(info, indent=4), encoding="utf-8")


def swap_stats_json(root: Path, apply: bool) -> None:
    p = root / "meta" / "stats.json"
    if not p.exists():
        return
    stats = json.loads(p.read_text(encoding="utf-8"))
    if KEY_A in stats and KEY_B in stats:
        stats[KEY_A], stats[KEY_B] = stats[KEY_B], stats[KEY_A]
        print("[stats.json] swapped entries")
        if apply:
            p.write_text(json.dumps(stats, indent=4), encoding="utf-8")


def swap_episodes_parquet(root: Path, apply: bool) -> None:
    files = sorted((root / "meta" / "episodes").rglob("*.parquet"))
    for f in files:
        df = pd.read_parquet(f)
        rename = {c: swap_in_str(c) for c in df.columns if (KEY_A in c or KEY_B in c)}
        if not rename:
            continue
        print(f"[episodes] {f.name}: renaming {len(rename)} columns")
        df = df.rename(columns=rename)
        if apply:
            df.to_parquet(f, index=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="hf_data/so101-pick-cube")
    ap.add_argument("--apply", action="store_true", help="actually write changes")
    args = ap.parse_args()
    root = Path(args.root)

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"=== Swapping {KEY_A} <-> {KEY_B}  [{mode}] ===")
    swap_video_folders(root, args.apply)
    swap_info(root, args.apply)
    swap_stats_json(root, args.apply)
    swap_episodes_parquet(root, args.apply)
    print("Done." + ("" if args.apply else "  (re-run with --apply to write)"))


if __name__ == "__main__":
    main()
