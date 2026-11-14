#!/usr/bin/env python3
"""
GOP-aligned incremental patch renderer for Remotion MP4 outputs.

Instead of re-rendering an entire long video when fixing localized typos, overlays,
spotlights, or styling inside a few seconds, this tool:
1. Inspects existing MP4 keyframes via ffprobe.
2. Expands requested dirty windows (--ranges / --scenes) to enclosing GOP keyframes.
3. Splits untouched video segments cleanly via `ffmpeg -f segment -c:v copy`.
4. Re-renders ONLY the dirty frame spans via `npx remotion render --frames=A-B --muted`.
5. Splices kept + patched video chunks with the intact audio track (`-c:v copy -c:a copy`),
   verifies total frame conservation and decode health, and atomically replaces output.

Note: Requires total duration and segment timestamps to remain unchanged.
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=check,
    )


def probe_video_packets(video_path: Path) -> dict:
    res = run([
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,r_frame_rate,avg_frame_rate,time_base,nb_frames",
        "-show_entries", "packet=pts,pts_time,dts,flags",
        "-of", "json",
        str(video_path),
    ])
    data = json.loads(res.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError(f"No video stream found in {video_path}")
    stream = streams[0]
    packets = data.get("packets") or []
    fps_frac = Fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "30/1")
    fps = float(fps_frac)
    total_frames = len(packets)

    keyframes: list[tuple[int, float]] = []
    for idx, pkt in enumerate(packets):
        flags = pkt.get("flags", "")
        if "K" not in flags:
            continue
        pts_time_raw = pkt.get("pts_time")
        if pts_time_raw is None:
            continue
        pts_t = float(pts_time_raw)
        frame_idx = int(round(pts_t * fps))
        keyframes.append((frame_idx, pts_t))

    # Deduplicate and sort by display frame index
    kf_map: dict[int, float] = {}
    for fidx, pt in keyframes:
        if fidx not in kf_map or pt < kf_map[fidx]:
            kf_map[fidx] = pt
    sorted_kfs = sorted(kf_map.items())
    if not sorted_kfs or sorted_kfs[0][0] != 0:
        raise RuntimeError("Could not detect keyframe at frame 0; aborting incremental patch.")

    return {
        "stream": stream,
        "fps": fps,
        "fps_frac": fps_frac,
        "total_frames": total_frames,
        "keyframes": sorted_kfs,
    }


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def count_video_packets(video_path: Path) -> int:
    res = run([
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-count_packets",
        "-show_entries", "stream=nb_read_packets",
        "-of", "csv=p=0",
        str(video_path),
    ])
    val = res.stdout.strip().rstrip(",")
    return int(val)


def parse_range_token(token: str, fps: float) -> tuple[int, int]:
    token = token.strip()
    if "-" not in token:
        raise ValueError(f"Invalid range '{token}'. Expected 'start-end' (seconds) or 'f100-f200' (frames).")
    left, right = token.split("-", 1)
    left = left.strip()
    right = right.strip()

    def to_frame(part: str) -> int:
        if part.lower().startswith("f"):
            return int(part[1:])
        return int(round(float(part) * fps))

    s_f = to_frame(left)
    e_f = to_frame(right)
    if e_f < s_f:
        s_f, e_f = e_f, s_f
    return s_f, e_f


def collect_dirty_frames(
    ranges_str: str | None,
    scenes_str: str | None,
    project_json: Path,
    fps: float,
    total_frames: int,
    pad_seconds: float,
) -> list[tuple[int, int]]:
    pad_frames = max(0, int(round(pad_seconds * fps)))
    raw_spans: list[tuple[int, int]] = []

    if ranges_str:
        for tok in ranges_str.split(","):
            if tok.strip():
                s_f, e_f = parse_range_token(tok, fps)
                raw_spans.append((max(0, s_f - pad_frames), min(total_frames, e_f + pad_frames)))

    if scenes_str:
        proj = json.loads(project_json.read_text(encoding="utf-8"))
        scenes = proj.get("scenes", [])
        scene_by_id = {str(sc.get("id", "")): sc for sc in scenes}
        for tok in scenes_str.split(","):
            tok = tok.strip()
            if not tok:
                continue
            sc = None
            if tok.isdigit() and 0 <= int(tok) < len(scenes):
                sc = scenes[int(tok)]
            elif tok in scene_by_id:
                sc = scene_by_id[tok]
            if not sc:
                raise ValueError(f"Scene '{tok}' not found in {project_json}")
            s_f = int(round(float(sc["start"]) * fps)) - pad_frames
            e_f = int(round(float(sc["end"]) * fps)) + pad_frames
            raw_spans.append((max(0, s_f), min(total_frames, e_f)))

    if not raw_spans:
        raise ValueError("Provide at least one --ranges or --scenes target to patch.")
    return raw_spans


def snap_and_merge_gops(
    raw_spans: list[tuple[int, int]],
    keyframes: list[tuple[int, float]],
    total_frames: int,
) -> list[tuple[int, int]]:
    kf_frames = [f for f, _ in keyframes]
    snapped: list[tuple[int, int]] = []
    for s_f, e_f in raw_spans:
        s_clamped = max(0, min(total_frames - 1, s_f))
        e_clamped = max(s_clamped + 1, min(total_frames, e_f))

        # Largest keyframe <= s_clamped
        left_pos = bisect.bisect_right(kf_frames, s_clamped) - 1
        k_left = kf_frames[max(0, left_pos)]

        # Smallest keyframe >= e_clamped (exclusive upper bound), or total_frames
        right_pos = bisect.bisect_left(kf_frames, e_clamped)
        k_right = kf_frames[right_pos] if right_pos < len(kf_frames) else total_frames

        if k_right <= k_left:
            next_pos = right_pos + 1
            k_right = kf_frames[next_pos] if next_pos < len(kf_frames) else total_frames

        snapped.append((k_left, k_right))

    snapped.sort()
    merged: list[tuple[int, int]] = []
    for k_l, k_r in snapped:
        if not merged or k_l > merged[-1][1]:
            merged.append((k_l, k_r))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], k_r))
    return merged


def build_partition(patch_spans: list[tuple[int, int]], total_frames: int) -> list[tuple[str, int, int]]:
    parts: list[tuple[str, int, int]] = []
    cursor = 0
    for p_l, p_r in patch_spans:
        if p_l > cursor:
            parts.append(("keep", cursor, p_l))
        parts.append(("patch", p_l, p_r))
        cursor = p_r
    if cursor < total_frames:
        parts.append(("keep", cursor, total_frames))
    return parts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GOP-aligned incremental FFmpeg + Remotion partial patch renderer"
    )
    parser.add_argument("--studio", required=True, help="Remotion studio directory (contains package.json & src/data/project.json)")
    parser.add_argument("--input", required=True, help="Existing full rendered MP4 path")
    parser.add_argument("--output", help="Patched MP4 output path (default: overwrite --input atomically)")
    parser.add_argument("--ranges", help="Dirty windows: '5.3-8.2,48-55' (seconds) or 'f159-f246' (frames)")
    parser.add_argument("--scenes", help="Dirty scene indices or IDs from project.json: e.g. '0,7'")
    parser.add_argument("--pad", type=float, default=0.25, help="Padding seconds around each dirty range (default: 0.25)")
    parser.add_argument("--composition", default="StudyVideo", help="Remotion composition ID (default: StudyVideo)")
    parser.add_argument("--concurrency", default="4", help="Remotion concurrency (default: 4)")
    parser.add_argument("--audio", help="Optional replacement audio file (.wav/.mp3/.aac) of identical total duration")
    parser.add_argument("--mirror-copy", help="Optional mirror destination MP4 path to overwrite after verification")
    parser.add_argument("--dry-run", action="store_true", help="Print GOP-snapped intervals without rendering")
    args = parser.parse_args()

    studio_dir = Path(args.studio).resolve()
    project_json = studio_dir / "src" / "data" / "project.json"
    input_mp4 = Path(args.input).resolve()
    output_mp4 = Path(args.output).resolve() if args.output else input_mp4

    if not input_mp4.exists():
        print(f"ERROR: Input MP4 not found: {input_mp4}", file=sys.stderr)
        return 1
    if not studio_dir.exists() or not (studio_dir / "package.json").exists():
        print(f"ERROR: Invalid Remotion studio directory: {studio_dir}", file=sys.stderr)
        return 1

    info = probe_video_packets(input_mp4)
    fps = info["fps"]
    total_frames = info["total_frames"]
    keyframes: list[tuple[int, float]] = info["keyframes"]
    kf_pts_by_frame = {f: pt for f, pt in keyframes}

    raw_spans = collect_dirty_frames(
        args.ranges,
        args.scenes,
        project_json,
        fps,
        total_frames,
        args.pad,
    )
    patch_spans = snap_and_merge_gops(raw_spans, keyframes, total_frames)
    partition = build_partition(patch_spans, total_frames)

    patch_frames_total = sum(r - l for kind, l, r in partition if kind == "patch")
    pct = (patch_frames_total / max(1, total_frames)) * 100.0
    print(f"Input MP4   : {input_mp4.name} ({total_frames} frames @ {fps:.3f} fps, {len(keyframes)} GOP keyframes)")
    print(f"Dirty render: {patch_frames_total}/{total_frames} frames ({pct:.1f}%) across {len(patch_spans)} patch window(s)")
    for kind, l, r in partition:
        tag = "PATCH (Remotion)" if kind == "patch" else "KEEP  (StreamCopy)"
        print(f"  - [{tag}] frames {l}..{r - 1} ({r - l} frames, {l / fps:.2f}s..{r / fps:.2f}s)")

    if args.dry_run:
        return 0

    if patch_frames_total >= total_frames:
        print("Patch spans cover 100% of video; run a normal full render instead.", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="remotion_patch_") as tmp_str:
        tmp_dir = Path(tmp_str)
        # All interior boundary frames where partition changes
        cut_frames = sorted({f for _, l, r in partition for f in (l, r) if 0 < f < total_frames})
        split_times = [f"{max(0.0, kf_pts_by_frame[cf] - 0.002):.6f}" for cf in cut_frames]

        keep_chunks: dict[tuple[int, int], Path] = {}
        if split_times:
            seg_pattern = str(tmp_dir / "orig_seg_%03d.mp4")
            print("Splitting untouched GOP segments (stream copy)...")
            res = run([
                "ffmpeg", "-y", "-v", "error",
                "-i", str(input_mp4),
                "-an", "-c:v", "copy",
                "-f", "segment",
                "-segment_times", ",".join(split_times),
                "-reset_timestamps", "1",
                seg_pattern,
            ], check=False)
            if res.returncode != 0:
                print(f"ERROR: ffmpeg segment failed:\n{res.stderr}", file=sys.stderr)
                return 1
            seg_files = sorted(tmp_dir.glob("orig_seg_*.mp4"))
            if len(seg_files) != len(partition):
                print(
                    f"ERROR: Segment count mismatch: got {len(seg_files)} files, expected {len(partition)}.",
                    file=sys.stderr,
                )
                return 1
            for (kind, l, r), seg_file in zip(partition, seg_files):
                if kind == "keep":
                    actual = count_video_packets(seg_file)
                    expected = r - l
                    if actual != expected:
                        print(
                            f"ERROR: Keep segment {l}..{r - 1} packet mismatch: expected {expected}, got {actual}.",
                            file=sys.stderr,
                        )
                        return 1
                    keep_chunks[(l, r)] = seg_file

        # Render only dirty spans via Remotion
        final_chunks: list[Path] = []
        for idx, (kind, l, r) in enumerate(partition):
            if kind == "keep":
                final_chunks.append(keep_chunks[(l, r)])
                continue
            patch_file = tmp_dir / f"patch_{idx:03d}.mp4"
            render_port = find_free_port()
            print(f"Rendering patch {idx}: --frames={l}-{r - 1} ({r - l} frames, port {render_port})...")
            cmd = [
                "npx", "remotion", "render",
                args.composition,
                str(patch_file),
                f"--frames={l}-{r - 1}",
                "--muted",
                f"--port={render_port}",
                f"--concurrency={args.concurrency}",
            ]
            ren = subprocess.run(cmd, cwd=str(studio_dir))
            if ren.returncode != 0 or not patch_file.exists():
                print(f"ERROR: Remotion partial render failed on frames {l}-{r - 1}", file=sys.stderr)
                return 1
            actual_patch = count_video_packets(patch_file)
            if actual_patch != (r - l):
                print(
                    f"ERROR: Patch segment {l}..{r - 1} frame mismatch: expected {r - l}, got {actual_patch}.",
                    file=sys.stderr,
                )
                return 1
            final_chunks.append(patch_file)

        concat_txt = tmp_dir / "concat.txt"
        concat_txt.write_text(
            "".join(f"file '{p}'\n" for p in final_chunks),
            encoding="utf-8",
        )

        audio_input = Path(args.audio).resolve() if args.audio else input_mp4
        audio_map = "1:a:0"
        audio_codec_args = ["-c:a", "aac", "-b:a", "192k"] if args.audio else ["-c:a", "copy"]

        staged_out = tmp_dir / "patched_staged.mp4"
        print("Concatenating video chunks + muxing audio...")
        mux = run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-i", str(audio_input),
            "-map", "0:v:0",
            "-map", audio_map,
            "-c:v", "copy",
            *audio_codec_args,
            "-movflags", "+faststart",
            str(staged_out),
        ], check=False)
        if mux.returncode != 0 or not staged_out.exists():
            print(f"ERROR: FFmpeg concat/mux failed:\n{mux.stderr}", file=sys.stderr)
            return 1

        # Verify decode integrity & exact packet count before replacing deliverable
        dec = run(["ffmpeg", "-v", "error", "-i", str(staged_out), "-f", "null", "-"], check=False)
        if dec.returncode != 0 or dec.stderr.strip():
            print(f"ERROR: Patched MP4 decode validation reported issues:\n{dec.stderr}", file=sys.stderr)
            return 1

        final_packets = count_video_packets(staged_out)
        if final_packets != total_frames:
            print(
                f"ERROR: Total frame count drifted ({final_packets} != {total_frames}). Aborting swap.",
                file=sys.stderr,
            )
            return 1

        verify_script = Path(__file__).resolve().parent / "verify_render.py"
        if verify_script.exists():
            expected_dur = total_frames / fps
            ver = subprocess.run([
                sys.executable,
                str(verify_script),
                str(staged_out),
                "--expected-duration",
                f"{expected_dur:.3f}",
            ])
            if ver.returncode != 0:
                print("ERROR: verify_render.py rejected patched output.", file=sys.stderr)
                return 1

        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        atomic_tmp = output_mp4.with_name(f".{output_mp4.name}.tmp")
        shutil.copy2(staged_out, atomic_tmp)
        os.replace(atomic_tmp, output_mp4)
        print(f"✓ Patched MP4 written atomically: {output_mp4}")

        if args.mirror_copy:
            mirror_dst = Path(args.mirror_copy).resolve()
            mirror_dst.parent.mkdir(parents=True, exist_ok=True)
            mirror_tmp = mirror_dst.with_name(f".{mirror_dst.name}.tmp")
            shutil.copy2(output_mp4, mirror_tmp)
            os.replace(mirror_tmp, mirror_dst)
            print(f"✓ Mirror copy updated: {mirror_dst}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
