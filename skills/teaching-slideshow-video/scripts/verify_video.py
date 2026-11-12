#!/usr/bin/env python3
"""Verify rendered 1080p teaching MP4 streams, decode integrity, mirror parity, and visual contact sheets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(str(c) for c in cmd)}\n{proc.stderr.strip()}")
    return proc


def check_media(mp4_path: Path, ffmpeg: str, ffprobe: str, expected_duration: float | None = None) -> dict:
    """Validate 1920x1080 H.264 30fps + single audio stream and pass a full FFmpeg decode check."""
    info = json.loads(
        _run([
            ffprobe, "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,sample_rate,channels",
            "-show_entries", "format=duration,size",
            "-of", "json", str(mp4_path),
        ]).stdout
    )
    v_streams = [s for s in info["streams"] if s["codec_type"] == "video"]
    a_streams = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if len(v_streams) != 1 or len(a_streams) != 1:
        raise ValueError(f"Expected 1 video and 1 audio stream in {mp4_path}, got v={len(v_streams)} a={len(a_streams)}")
    v = v_streams[0]
    a = a_streams[0]
    if v.get("codec_name") != "h264" or (v.get("width"), v.get("height")) != (1920, 1080) or v.get("r_frame_rate") != "30/1":
        raise ValueError(f"Unexpected video stream properties in {mp4_path}: {v}")
    if v.get("pix_fmt") != "yuv420p" or a.get("codec_name") != "aac":
        raise ValueError(f"Unexpected pixel/audio codec in {mp4_path}: pix_fmt={v.get('pix_fmt')} audio={a.get('codec_name')}")

    dur = float(info["format"]["duration"])
    if expected_duration is not None and abs(dur - expected_duration) > 0.2:
        raise ValueError(f"Duration mismatch in {mp4_path}: actual={dur:.3f}s expected={expected_duration:.3f}s")

    _run([ffmpeg, "-v", "error", "-xerror", "-i", str(mp4_path), "-f", "null", "-"])
    return {
        "duration": round(dur, 3),
        "size_bytes": mp4_path.stat().st_size,
        "video": v,
        "audio": a,
    }


def check_mirror(primary: Path, mirror: Path) -> str:
    if not mirror.is_file():
        raise FileNotFoundError(f"Missing mirror MP4: {mirror}")
    if primary.stat().st_size != mirror.stat().st_size:
        raise ValueError(f"Mirror size mismatch: {primary} ({primary.stat().st_size}) vs {mirror} ({mirror.stat().st_size})")
    h1 = hashlib.sha256(primary.read_bytes()).hexdigest()
    h2 = hashlib.sha256(mirror.read_bytes()).hexdigest()
    if h1 != h2:
        raise ValueError(f"Mirror SHA-256 mismatch: {h1} != {h2}")
    return h1[:16]


def pick_keyframes(build_dir: Path | None, dur: float, review_topics_path: Path | None) -> list[tuple[str, float]]:
    if build_dir is None or not (build_dir / "timeline.json").is_file():
        return [
            ("01_start", min(1.0, max(0.2, dur * 0.05))),
            ("02_quarter", dur * 0.25),
            ("03_mid", dur * 0.50),
            ("04_three_quarter", dur * 0.75),
            ("05_end", max(0.0, dur - 2.0)),
        ]

    timeline = json.loads((build_dir / "timeline.json").read_text(encoding="utf-8"))
    picks: list[tuple[str, float]] = [("01_cover", min(max(timeline[0]["start"] + 0.5, 0.8), max(0.8, dur - 1.0)))]

    # Pick longest bilingual cue to inspect line wrapping and bottom subtitle spacing.
    longest_idx = max(range(len(timeline)), key=lambda i: len(timeline[i].get("en", "")) + len(timeline[i].get("zh", "")))
    picks.append(("02_longest", min(timeline[longest_idx]["start"] + 0.6, max(0.5, dur - 0.5))))

    # First foreground overlay window (if overlay_plan.json exists), else early body scene.
    ov_plan_path = build_dir / "overlay_plan.json"
    if ov_plan_path.is_file():
        overlays = json.loads(ov_plan_path.read_text(encoding="utf-8"))
        if overlays:
            ov = overlays[0]
            picks.append(("03_overlay", ov["t_start"] + (ov["t_end"] - ov["t_start"]) * 0.35))
    elif len(timeline) > 4:
        picks.append(("03_scene", timeline[min(4, len(timeline) - 1)]["start"] + 0.6))

    # Hint cue sample if not already covered by longest/overlay.
    hint_cues = [i for i, c in enumerate(timeline) if c.get("notes")]
    if hint_cues:
        h_idx = hint_cues[len(hint_cues) // 2]
        picks.append(("04_hint", timeline[h_idx]["start"] + 0.6))

    # Q&A question and reveal answer (if questions exist).
    qa_indices = [i for i, t in enumerate(timeline) if "?" in t.get("en", "")]
    if qa_indices:
        q_idx = qa_indices[-1]
        picks.append(("05_qa_q", timeline[q_idx]["start"] + 0.6))
        if q_idx + 1 < len(timeline):
            picks.append(("06_qa_ans", timeline[q_idx + 1]["start"] + 0.6))

    # Review topic anchor if supplied.
    if review_topics_path and review_topics_path.is_file():
        topics = json.loads(review_topics_path.read_text(encoding="utf-8"))
        if topics and isinstance(topics[0].get("cue"), int) and topics[0]["cue"] < len(timeline):
            picks.append(("07_review", timeline[topics[0]["cue"]]["start"] + 0.8))

    picks.append(("08_outro", max(0.0, timeline[-1]["start"] + 0.6)))
    return picks


def export_inspection_images(
    mp4_path: Path,
    picks: list[tuple[str, float]],
    out_dir: Path,
    prefix: str,
    ffmpeg: str,
) -> tuple[Path, Path]:
    frames_dir = out_dir / f"{prefix}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    thumbs: list[tuple[str, float, Image.Image]] = []
    mobile_src: Path | None = None

    for label, ts in picks:
        jpg = frames_dir / f"{label}.jpg"
        _run([ffmpeg, "-v", "error", "-i", str(mp4_path), "-ss", f"{ts:.3f}", "-frames:v", "1", "-y", str(jpg)])
        if mobile_src is None or label in ("03_overlay", "04_hint", "02_longest"):
            mobile_src = jpg
        with Image.open(jpg) as im:
            thumbs.append((label, ts, im.resize((640, 360), Image.Resampling.LANCZOS)))

    cols = 2
    rows = (len(thumbs) + 1) // 2
    sheet = Image.new("RGB", (cols * 640, rows * 360), (20, 24, 32))
    draw = ImageDraw.Draw(sheet)
    for idx, (lbl, ts, im) in enumerate(thumbs):
        x = (idx % cols) * 640
        y = (idx // cols) * 360
        sheet.paste(im, (x, y))
        draw.rectangle([x + 6, y + 6, x + 225, y + 28], fill=(0, 0, 0))
        draw.text((x + 12, y + 10), f"{lbl} @{ts:.1f}s", fill=(255, 220, 100))

    grid_path = out_dir / f"{prefix}_grid.jpg"
    sheet.save(grid_path, "JPEG", quality=90)

    mobile_path = out_dir / f"{prefix}_mobile480p.jpg"
    if mobile_src and mobile_src.is_file():
        with Image.open(mobile_src) as im:
            im.resize((854, 480), Image.Resampling.LANCZOS).save(mobile_path, "JPEG", quality=92)
    return grid_path, mobile_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mp4", type=Path, required=True, help="Final rendered MP4 path")
    parser.add_argument("--build", type=Path, help="Build directory containing timeline.json/timing.json/overlay_plan.json")
    parser.add_argument("--review-topics", type=Path, help="Optional 复习主题.json for review-segment screenshot")
    parser.add_argument("--mirror", type=Path, help="Optional published mirror MP4 to verify size and SHA-256 parity")
    parser.add_argument("--out-dir", type=Path, help="Directory to export inspection keyframe grid and 854x480 preview")
    parser.add_argument("--prefix", help="Output filename prefix inside --out-dir (defaults to MP4 stem)")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()

    mp4_abs = args.mp4.resolve()
    if not mp4_abs.is_file():
        raise FileNotFoundError(f"Missing MP4 file: {mp4_abs}")

    expected_dur = None
    if args.build and (args.build / "timing.json").is_file():
        expected_dur = float(json.loads((args.build / "timing.json").read_text(encoding="utf-8"))["duration"])

    media = check_media(mp4_abs, args.ffmpeg, args.ffprobe, expected_duration=expected_dur)
    report: dict = {"mp4": str(mp4_abs), "full_decode": "passed", **media}

    if args.mirror:
        report["mirror_sha256_16"] = check_mirror(mp4_abs, args.mirror.resolve())
        report["mirror_parity"] = "OK"

    if args.out_dir:
        out_dir = args.out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        picks = pick_keyframes(args.build.resolve() if args.build else None, media["duration"], args.review_topics)
        grid_path, mobile_path = export_inspection_images(
            mp4_abs, picks, out_dir, args.prefix or mp4_abs.stem, args.ffmpeg
        )
        report["grid_image"] = str(grid_path)
        report["mobile_480p_preview"] = str(mobile_path)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        sys.exit(str(exc))
