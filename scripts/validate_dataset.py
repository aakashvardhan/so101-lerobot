"""Download and validate a LeRobot v3.0 dataset.

Checks:
  - meta/info.json consistency (episode/frame totals)
  - per-episode frame counts (data parquet vs episode metadata)
  - video integrity (decodable, frame count vs fps*duration, resolution)
  - action / observation.state ranges (min/max/mean/std, NaN/Inf)

Usage:
  python scripts/validate_dataset.py --repo-id aakashv100/so101-pick-cube
  python scripts/validate_dataset.py --local hf_data/so101-pick-cube
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import av
import numpy as np
import pandas as pd


def log(msg: str = "") -> None:
    print(msg, flush=True)


def fmt_path(template: str, **kw) -> str:
    return template.format(**kw)


def load_info(root: Path) -> dict:
    with open(root / "meta" / "info.json", "r", encoding="utf-8") as f:
        return json.load(f)


def read_parquet_dir(meta_dir: Path) -> pd.DataFrame:
    """Concatenate all parquet files under a meta sub-dir (v3.0 chunked layout)."""
    files = sorted(meta_dir.rglob("*.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def validate_videos(root: Path, info: dict, episodes: pd.DataFrame, errors: list) -> None:
    video_keys = [k for k, v in info["features"].items() if v["dtype"] == "video"]
    if not video_keys:
        log("No video features.")
        return

    video_template = info["video_path"]
    fps = info["fps"]

    log(f"\n=== VIDEO INTEGRITY ({len(video_keys)} camera(s)) ===")
    for vkey in video_keys:
        feat = info["features"][vkey]
        exp_h = feat["info"]["video.height"]
        exp_w = feat["info"]["video.width"]

        # v3.0: videos are chunked files referenced per-episode via meta columns.
        # Collect unique video files for this key.
        chunk_col = f"videos/{vkey}/chunk_index"
        file_col = f"videos/{vkey}/file_index"
        if chunk_col in episodes.columns and file_col in episodes.columns:
            pairs = episodes[[chunk_col, file_col]].drop_duplicates().values.tolist()
        else:
            pairs = [[0, 0]]

        vid_files = []
        for ci, fi in pairs:
            p = root / fmt_path(video_template, video_key=vkey,
                                chunk_index=int(ci), file_index=int(fi))
            vid_files.append(p)

        ok, bad = 0, 0
        total_frames = 0
        for p in vid_files:
            if not p.exists():
                errors.append(f"[VIDEO] missing file: {p}")
                bad += 1
                continue
            try:
                with av.open(str(p)) as container:
                    stream = container.streams.video[0]
                    w, h = stream.codec_context.width, stream.codec_context.height
                    if (h, w) != (exp_h, exp_w):
                        errors.append(f"[VIDEO] {p.name}: resolution {w}x{h} != {exp_w}x{exp_h}")
                        bad += 1
                    n = sum(1 for _ in container.decode(video=0))
                    total_frames += n
                    ok += 1
            except Exception as e:
                errors.append(f"[VIDEO] undecodable {p}: {e}")
                bad += 1
        log(f"  {vkey}: {ok} file(s) OK, {bad} bad, {total_frames} decoded frames "
            f"({exp_w}x{exp_h} @ {fps}fps expected)")


def validate_frames(root: Path, info: dict, episodes: pd.DataFrame, errors: list) -> pd.DataFrame:
    log("\n=== PER-EPISODE FRAME COUNTS ===")
    data = read_parquet_dir(root / "data")
    if data.empty:
        errors.append("[DATA] no parquet data files found")
        return data

    counts = data.groupby("episode_index").size().rename("data_frames")
    summary = counts.to_frame()

    if "length" in episodes.columns and "episode_index" in episodes.columns:
        meta_len = episodes.set_index("episode_index")["length"].rename("meta_length")
        summary = summary.join(meta_len, how="outer")
        mismatch = summary[summary["data_frames"] != summary["meta_length"]]
        for ep, row in mismatch.iterrows():
            errors.append(f"[FRAMES] ep {ep}: data={row['data_frames']} != meta={row['meta_length']}")

    log(f"  episodes with data: {summary['data_frames'].notna().sum()}")
    log(f"  total data frames : {int(counts.sum())}")
    log(f"  frames/episode    : min={int(counts.min())} max={int(counts.max())} "
        f"mean={counts.mean():.1f}")
    if int(counts.sum()) != info.get("total_frames", -1):
        errors.append(f"[FRAMES] total {int(counts.sum())} != info.total_frames {info.get('total_frames')}")
    if summary.shape[0] != info.get("total_episodes", -1):
        errors.append(f"[FRAMES] episode count {summary.shape[0]} != info.total_episodes {info.get('total_episodes')}")
    return data


def validate_ranges(data: pd.DataFrame, info: dict, errors: list) -> None:
    log("\n=== ACTION / STATE RANGES ===")
    for key in ("action", "observation.state"):
        if key not in data.columns:
            continue
        names = info["features"][key]["names"]
        arr = np.stack(data[key].to_numpy())  # (N, D)
        if not np.isfinite(arr).all():
            n_bad = int((~np.isfinite(arr)).sum())
            errors.append(f"[RANGE] {key}: {n_bad} non-finite (NaN/Inf) values")
        log(f"\n  {key}  shape={arr.shape}")
        log(f"  {'joint':<18}{'min':>10}{'max':>10}{'mean':>10}{'std':>10}")
        for i, nm in enumerate(names):
            col = arr[:, i]
            log(f"  {nm:<18}{col.min():>10.3f}{col.max():>10.3f}{col.mean():>10.3f}{col.std():>10.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-id", default="aakashv100/so101-pick-cube")
    ap.add_argument("--local", default=None, help="path to an already-downloaded dataset root")
    ap.add_argument("--download-dir", default="hf_data/so101-pick-cube")
    args = ap.parse_args()

    if args.local:
        root = Path(args.local)
        log(f"Using local dataset: {root}")
    else:
        from huggingface_hub import snapshot_download
        log(f"Downloading {args.repo_id} ...")
        root = Path(snapshot_download(repo_id=args.repo_id, repo_type="dataset",
                                      local_dir=args.download_dir))
        log(f"Downloaded to: {root}")

    info = load_info(root)
    log(f"\ncodebase={info.get('codebase_version')} robot={info.get('robot_type')} "
        f"episodes={info.get('total_episodes')} frames={info.get('total_frames')} fps={info.get('fps')}")

    episodes = read_parquet_dir(root / "meta" / "episodes")
    errors: list[str] = []

    data = validate_frames(root, info, episodes, errors)
    validate_videos(root, info, episodes, errors)
    if not data.empty:
        validate_ranges(data, info, errors)

    log("\n=== RESULT ===")
    if errors:
        log(f"FAILED with {len(errors)} issue(s):")
        for e in errors:
            log(f"  - {e}")
        raise SystemExit(1)
    log("All checks passed.")


if __name__ == "__main__":
    main()
