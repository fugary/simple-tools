#!/usr/bin/env python3
"""
verify_render.py
校验 Remotion 输出 MP4 的分辨率、帧率、音视频流、时长误差，并抽取 6 帧关键帧拼图供目视验收。
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_ffprobe(video_path: str) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found in PATH")
    res = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,r_frame_rate,duration",
            "-of",
            "json",
            video_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {res.stderr}")
    return json.loads(res.stdout)


def make_contact_sheet(video_path: str, duration: float, out_path: str) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or duration <= 0:
        return False

    ratios = [0.01, 0.14, 0.35, 0.58, 0.80, 0.96]
    timestamps = [max(0.1, min(duration - 0.2, duration * r)) for r in ratios]

    with tempfile.TemporaryDirectory() as tmp:
        frame_files = []
        for i, ts in enumerate(timestamps):
            fp = os.path.join(tmp, f"f_{i}.jpg")
            subprocess.run(
                [ffmpeg, "-y", "-ss", f"{ts:.2f}", "-i", video_path, "-frames:v", "1", "-q:v", "3", fp],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if os.path.exists(fp):
                frame_files.append(fp)

        if not frame_files:
            return False

        inputs = []
        for f in frame_files:
            inputs.extend(["-i", f])

        cols = 3
        rows = 2
        filter_str = f"xstack=inputs={len(frame_files)}:layout=" + "|".join(
            f"{(i % cols) * 640}_{(i // cols) * 360}" for i in range(len(frame_files))
        )
        scale_inputs = "".join(f"[{i}:v]scale=640:360[v{i}];" for i in range(len(frame_files)))
        xstack_in = "".join(f"[v{i}]" for i in range(len(frame_files)))
        full_filter = f"{scale_inputs}{xstack_in}{filter_str}"

        cmd = [ffmpeg, "-y", *inputs, "-filter_complex", full_filter, "-q:v", "3", out_path]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0 and os.path.exists(out_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Remotion study video MP4 output")
    parser.add_argument("mp4", help="Path to rendered MP4 file")
    parser.add_argument("--expected-duration", type=float, default=None, help="Expected duration in seconds")
    parser.add_argument("--tolerance", type=float, default=1.5, help="Duration tolerance in seconds")
    parser.add_argument("--contact-sheet", help="Optional output path for 6-frame verification contact sheet JPG")
    args = parser.parse_args()

    if not os.path.exists(args.mp4):
        print(f"[FAIL] File does not exist: {args.mp4}", file=sys.stderr)
        return 1

    info = run_ffprobe(args.mp4)
    streams = info.get("streams", [])
    fmt = info.get("format", {})

    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not v_stream:
        print("[FAIL] No video stream found!")
        return 1

    width = int(v_stream.get("width", 0))
    height = int(v_stream.get("height", 0))
    duration = float(fmt.get("duration", 0))
    fps_raw = v_stream.get("r_frame_rate", "0/1")

    print(f"=== Remotion Render Verification: {args.mp4} ===")
    print(f"Resolution : {width}x{height} (Expected: 1920x1080)")
    print(f"Frame Rate : {fps_raw}")
    print(f"Duration   : {duration:.2f}s")
    print(f"Video Codec: {v_stream.get('codec_name')}")
    print(f"Audio Codec: {a_stream.get('codec_name') if a_stream else 'None'}")

    passed = True
    if width != 1920 or height != 1080:
        print("[FAIL] Resolution mismatch (expected 1920x1080)!")
        passed = False
    if not a_stream:
        print("[FAIL] Missing audio stream!")
        passed = False
    if args.expected_duration is not None and abs(duration - args.expected_duration) > args.tolerance:
        print(f"[FAIL] Duration {duration:.2f}s exceeds expected {args.expected_duration:.2f}s ± {args.tolerance}s")
        passed = False

    if args.contact_sheet:
        Path(args.contact_sheet).parent.mkdir(parents=True, exist_ok=True)
        if make_contact_sheet(args.mp4, duration, args.contact_sheet):
            print(f"Contact Sheet: {args.contact_sheet}")
        else:
            print("[WARN] Failed to generate contact sheet")

    if passed:
        print("\nVerification PASSED.")
        return 0
    print("\nVerification FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
