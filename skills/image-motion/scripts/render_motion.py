#!/usr/bin/env python3
"""Render a seamless looping micro-motion video from a still image and motion_plan.json."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from check_environment import resolve_ffmpeg
from estimate_depth import VALID_BACKENDS, estimate_depth
from mask_refiner import rasterize_polygons
from motion_effects import (
    DepthParallaxEffect,
    FlagClothWaveEffect,
    FoliageSwayEffect,
    OverlayFxEffect,
    RotatePartEffect,
    SkyDriftEffect,
    WaterfallFlowEffect,
    WaterRippleEffect,
    build_effect_pipeline,
    collect_static_regions,
)

_EFFECT_TYPE_NAMES = {
    WaterRippleEffect: "water_ripple",
    WaterfallFlowEffect: "waterfall_flow",
    SkyDriftEffect: "sky_drift",
    FoliageSwayEffect: "foliage_sway",
    FlagClothWaveEffect: "flag_cloth_wave",
    RotatePartEffect: "rotate_part",
    DepthParallaxEffect: "depth_parallax",
    OverlayFxEffect: "overlay_fx",
}


def _even_size(w: int, h: int, min_width: int, max_width: int) -> tuple[int, int]:
    if min_width < 2 or max_width < min_width:
        raise ValueError(f"Invalid width bounds: min_width={min_width}, max_width={max_width}")
    target_w = max(min_width, min(w, max_width))
    scale = target_w / w
    if h * scale > max_width:
        scale = max_width / h
    out_w = max(2, int(round(w * scale)) & ~1)
    out_h = max(2, int(round(h * scale)) & ~1)
    return out_w, out_h


def _resolve_path(base_dir: Path, path_str: str) -> Path:
    p = Path(path_str).expanduser()
    return p.resolve() if p.is_absolute() else (base_dir / p).resolve()


def _collect_polygons_and_rects(regions_cfg: Any) -> tuple[list, list, list, list]:
    polys: list = []
    rects: list = []
    lock_polys: list = []
    lock_rects: list = []
    items = regions_cfg if isinstance(regions_cfg, list) else ([regions_cfg] if isinstance(regions_cfg, dict) else [])
    for item in items:
        if not isinstance(item, dict):
            continue
        item_polys = list(item.get("polygons", ()))
        if "polygon" in item:
            item_polys.append(item["polygon"])
        item_rects = list(item.get("rects", ()))
        if "rect" in item:
            item_rects.append(item["rect"])
        polys.extend(item_polys)
        rects.extend(item_rects)
        if item.get("lock_camera", False):
            lock_polys.extend(item_polys)
            lock_rects.extend(item_rects)
    return polys, rects, lock_polys, lock_rects


def _save_debug_visuals(
    base_rgb: np.ndarray,
    pipeline: list,
    out_dir: Path,
    static_mask: np.ndarray | None = None,
    lock_mask: np.ndarray | None = None,
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for idx, eff in enumerate(pipeline):
        if (
            isinstance(
                eff,
                (
                    WaterRippleEffect,
                    WaterfallFlowEffect,
                    SkyDriftEffect,
                    FoliageSwayEffect,
                    FlagClothWaveEffect,
                ),
            )
            and hasattr(eff, "mask")
        ):
            alpha = (eff.mask[..., None] * 0.45)
            tint = np.zeros_like(base_rgb)
            if isinstance(eff, (WaterRippleEffect, WaterfallFlowEffect)):
                tint[..., 1], tint[..., 2] = 220.0, 255.0
            elif isinstance(eff, SkyDriftEffect):
                tint[..., 0], tint[..., 1], tint[..., 2] = 255.0, 200.0, 90.0
            elif isinstance(eff, FlagClothWaveEffect):
                tint[..., 0], tint[..., 1], tint[..., 2] = 255.0, 110.0, 90.0
            else:
                tint[..., 1] = 230.0
            vis = np.clip(base_rgb * (1.0 - alpha) + tint * alpha, 0, 255).astype(np.uint8)
            p = out_dir / f"mask_{idx}_{eff.__class__.__name__}.png"
            Image.fromarray(vis).save(p)
            saved.append(str(p))
        elif isinstance(eff, RotatePartEffect):
            full_mask = np.zeros(base_rgb.shape[:2], dtype=np.float32)
            if eff.mode == "disc" and hasattr(eff, "disc_mask"):
                sub_m = eff.disc_mask
            else:
                sub_m = np.clip(eff.fg_alpha * eff.dest_allow, 0.0, 1.0)
            full_mask[eff.y0:eff.y1, eff.x0:eff.x1] = sub_m
            alpha = (full_mask[..., None] * 0.5)
            tint = np.zeros_like(base_rgb)
            tint[..., 0], tint[..., 2] = 255.0, 210.0
            vis = np.clip(base_rgb * (1.0 - alpha) + tint * alpha, 0, 255).astype(np.uint8)
            p = out_dir / f"mask_{idx}_RotatePartEffect.png"
            Image.fromarray(vis).save(p)
            saved.append(str(p))
        elif isinstance(eff, DepthParallaxEffect):
            p = out_dir / f"depth_{idx}.png"
            Image.fromarray((np.clip(eff.depth, 0.0, 1.0) * 255.0).astype(np.uint8)).save(p)
            saved.append(str(p))
    if static_mask is not None and np.any(static_mask > 0.01):
        alpha = static_mask[..., None] * 0.45
        tint = np.zeros_like(base_rgb)
        tint[..., 0] = 255.0
        vis = np.clip(base_rgb * (1.0 - alpha) + tint * alpha, 0, 255).astype(np.uint8)
        p = out_dir / "static_regions_locked.png"
        Image.fromarray(vis).save(p)
        saved.append(str(p))
    if lock_mask is not None and np.any(lock_mask > 0.01):
        alpha = lock_mask[..., None] * 0.5
        tint = np.zeros_like(base_rgb)
        tint[..., 0], tint[..., 1] = 255.0, 140.0
        vis = np.clip(base_rgb * (1.0 - alpha) + tint * alpha, 0, 255).astype(np.uint8)
        p = out_dir / "camera_locked_regions.png"
        Image.fromarray(vis).save(p)
        saved.append(str(p))
    return saved


def render_motion(
    image_path: Path,
    plan_data: dict[str, Any],
    output_mp4: Path,
    duration: float,
    fps: int,
    min_width: int,
    max_width: int,
    ffmpeg_exe: str,
    webp_out: Path | None = None,
    preview_dir: Path | None = None,
) -> dict[str, Any]:
    """Render seamless micro-motion video and verify decoding."""
    if duration <= 0:
        raise ValueError(f"duration must be > 0, got {duration}")
    if fps <= 0:
        raise ValueError(f"fps must be > 0, got {fps}")

    im = Image.open(image_path).convert("RGB")
    orig_w, orig_h = im.size
    w, h = _even_size(orig_w, orig_h, min_width, max_width)
    if (w, h) != (orig_w, orig_h):
        im = im.resize((w, h), Image.Resampling.LANCZOS)
    base_rgb = np.array(im, dtype=np.float32)

    raw_effects = plan_data.get("effects")
    if raw_effects is None:
        raw_effects = [
            {"type": "depth_parallax", "horizon_y": 0.55, "strength": 0.035, "mode": "loop"}
        ]
    static_cfg = plan_data.get("static_regions")
    static_polys, static_rects, lock_polys, lock_rects = collect_static_regions(static_cfg)

    pipeline = build_effect_pipeline(base_rgb, raw_effects, static_regions=static_cfg)
    has_depth = any(isinstance(e, DepthParallaxEffect) for e in pipeline)
    warp_effects = [e for e in pipeline if not isinstance(e, OverlayFxEffect)]
    overlay_effects = [e for e in pipeline if isinstance(e, OverlayFxEffect)]

    static_mask: np.ndarray | None = None
    static_core: np.ndarray | None = None
    if static_polys or static_rects:
        static_img = rasterize_polygons(w, h, polygons=static_polys, rects=static_rects)
        static_mask = np.array(static_img, dtype=np.float32) / 255.0
        eroded = np.array(static_img.filter(ImageFilter.MinFilter(size=5)), dtype=np.float32) / 255.0
        static_core = eroded > 0.5 if np.any(eroded > 0.5) else (static_mask > 0.5)

    lock_alpha: np.ndarray | None = None
    lock_core: np.ndarray | None = None
    if lock_polys or lock_rects:
        lock_img = rasterize_polygons(w, h, polygons=lock_polys, rects=lock_rects)
        lock_raw = np.array(lock_img, dtype=np.float32) / 255.0
        lock_soft = np.array(lock_img.filter(ImageFilter.GaussianBlur(radius=1.5)), dtype=np.float32) / 255.0
        lock_alpha = np.where(lock_raw > 0.5, 1.0, lock_soft).astype(np.float32)[..., None]
        lock_core = lock_raw > 0.99

    verify_mask: np.ndarray | None = None
    if not has_depth and static_core is not None and np.any(static_core):
        verify_mask = static_core
    elif lock_core is not None and np.any(lock_core):
        verify_mask = lock_core

    debug_files = (
        _save_debug_visuals(
            base_rgb,
            pipeline,
            preview_dir,
            static_mask=static_mask,
            lock_mask=(lock_alpha[..., 0] if lock_alpha is not None else None),
        )
        if preview_dir
        else []
    )

    n_frames = max(2, int(round(duration * fps)))
    check_indices = {n_frames // 2}
    for frac in (0.25, 0.37, 0.50, 0.75):
        idx = int(round(n_frames * frac))
        if 1 <= idx < n_frames:
            check_indices.add(idx)

    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{w}x{h}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-",
        "-an",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "17",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_mp4),
    ]

    first_frame: np.ndarray | None = None
    mid_frame: np.ndarray | None = None
    last_frame: np.ndarray | None = None
    phase_diffs: list[float] = []
    static_warp_max_diff: float | None = None
    webp_frames: list[Image.Image] = []
    webp_step = max(1, fps // 15)

    with tempfile.TemporaryFile(mode="w+b") as stderr_fh:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stderr_fh)
        try:
            for i in range(n_frames):
                # u in [0, 1): at i == n_frames, u wraps back seamlessly to 0.0
                u = i / float(n_frames)
                cur = base_rgb
                for eff in warp_effects:
                    cur = eff.apply(cur, u, duration)
                if lock_alpha is not None:
                    cur = cur * (1.0 - lock_alpha) + base_rgb * lock_alpha

                if i in check_indices and verify_mask is not None:
                    diff_val = float(np.max(np.abs(cur[verify_mask] - base_rgb[verify_mask])))
                    static_warp_max_diff = diff_val if static_warp_max_diff is None else max(static_warp_max_diff, diff_val)

                for eff in overlay_effects:
                    cur = eff.apply(cur, u, duration)

                u8 = np.clip(cur, 0.0, 255.0).astype(np.uint8)
                assert proc.stdin is not None
                proc.stdin.write(u8.tobytes())

                f32: np.ndarray | None = None
                if i == 0:
                    first_frame = u8.astype(np.float32)
                if i in check_indices:
                    f32 = u8.astype(np.float32)
                    if first_frame is not None:
                        phase_diffs.append(float(np.abs(f32 - first_frame).mean()))
                if i == n_frames // 2:
                    mid_frame = f32 if f32 is not None else u8.astype(np.float32)
                if i == n_frames - 1:
                    last_frame = f32 if f32 is not None else u8.astype(np.float32)

                if webp_out is not None and (i % webp_step == 0):
                    img_w = Image.fromarray(u8)
                    if w > 720:
                        wh = max(2, int(round(h * (720.0 / w))) & ~1)
                        img_w = img_w.resize((720, wh), Image.Resampling.BILINEAR)
                    webp_frames.append(img_w)
        finally:
            if proc.stdin:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            proc.wait()

        if proc.returncode != 0:
            stderr_fh.seek(0)
            err_tail = stderr_fh.read().decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"FFmpeg encoding failed (exit {proc.returncode}):\n{err_tail}")

    decode = subprocess.run(
        [ffmpeg_exe, "-v", "error", "-xerror", "-i", str(output_mp4), "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if decode.returncode != 0:
        raise RuntimeError(f"Rendered MP4 failed decode check: {decode.stderr}")

    if webp_out is not None and webp_frames:
        webp_out.parent.mkdir(parents=True, exist_ok=True)
        webp_frames[0].save(
            webp_out,
            save_all=True,
            append_images=webp_frames[1:],
            duration=int(round(1000.0 / (fps / webp_step))),
            loop=0,
            quality=88,
        )

    assert first_frame is not None and mid_frame is not None and last_frame is not None
    mid_diff = float(np.abs(mid_frame - first_frame).mean())
    peak_diff = max(phase_diffs) if phase_diffs else mid_diff
    loop_diff = float(np.abs(last_frame - first_frame).mean())

    report = {
        "source_image": str(image_path),
        "output_mp4": str(output_mp4),
        "width": w,
        "height": h,
        "fps": fps,
        "duration": duration,
        "frames": n_frames,
        "effects": [c.get("type") for c in raw_effects],
        "pipeline_effects": [_EFFECT_TYPE_NAMES.get(type(e), e.__class__.__name__) for e in pipeline],
        "static_regions_locked": bool(static_polys or static_rects),
        "camera_locked_regions": bool(lock_polys or lock_rects),
        "full_decode": "passed",
        "mean_motion_mid_diff": round(mid_diff, 3),
        "mean_motion_peak_diff": round(peak_diff, 3),
        "loop_seam_diff": round(loop_diff, 3),
        "debug_visuals": debug_files,
    }
    if static_warp_max_diff is not None:
        report["static_region_warp_max_diff"] = round(static_warp_max_diff, 4)
    output_mp4.with_suffix(".verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, help="Input image path (optional if plan defines image)")
    parser.add_argument("--plan", type=Path, help="JSON motion plan file")
    parser.add_argument("--output", type=Path, required=True, help="Output MP4 path")
    parser.add_argument("--webp", type=Path, help="Optional animated WebP preview path")
    parser.add_argument("--preview-masks", type=Path, help="Optional folder to save mask/depth debug PNGs")
    parser.add_argument("--depth-map", type=Path, help="Optional external grayscale depth map (Step 2 hook)")
    parser.add_argument("--auto-depth", action="store_true", help="Estimate Depth Anything V2 map before rendering")
    parser.add_argument("--depth-backend", default="auto", choices=VALID_BACKENDS)
    parser.add_argument("--depth-model", default=None, help="Optional HF model ID or ONNX repo ID for --auto-depth")
    parser.add_argument("--onnx-path", type=Path, default=None, help="Optional local Depth Anything ONNX file")
    parser.add_argument("--depth-input-size", type=int, default=518, help="Max ViT input size for ONNX auto-depth")
    parser.add_argument("--depth-out", type=Path, default=None, help="Where to save generated auto-depth PNG")
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--fps", type=int, default=None)
    parser.add_argument("--min-width", type=int, default=1160)
    parser.add_argument("--max-width", type=int, default=1920)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()

    if args.depth_map and args.auto_depth:
        parser.error("Use either --depth-map or --auto-depth, not both.")
    if args.min_width < 2 or args.max_width < args.min_width:
        parser.error(f"Invalid width range: --min-width={args.min_width}, --max-width={args.max_width}")

    plan_data: dict[str, Any] = {}
    base_dir = Path.cwd()
    if args.plan:
        plan_path = args.plan.resolve()
        base_dir = plan_path.parent
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))

    img_arg = args.image or (plan_data.get("image") and _resolve_path(base_dir, plan_data["image"]))
    if not img_arg:
        parser.error("Provide --image or set 'image' in --plan.")
    image_path = Path(img_arg).resolve()
    if not image_path.is_file():
        parser.error(f"Missing image: {image_path}")

    resolved_depth_map: Path | None = args.depth_map.resolve() if args.depth_map else None
    if args.auto_depth:
        depth_target = (args.depth_out or args.output.with_suffix(".depth.png")).resolve()
        estimate_depth(
            image_path=image_path,
            output_path=depth_target,
            backend=args.depth_backend,
            onnx_path=args.onnx_path,
            model_id=args.depth_model,
            input_size=args.depth_input_size,
        )
        resolved_depth_map = depth_target

    # Resolve relative depth_map inside plan effects, or inject CLI --depth-map / --auto-depth
    effects = plan_data.get("effects")
    if effects is None:
        effects = [{"type": "depth_parallax", "horizon_y": 0.55, "strength": 0.035, "mode": "loop"}]
        plan_data["effects"] = effects
    for eff in effects:
        if eff.get("type") == "depth_parallax":
            if resolved_depth_map is not None:
                eff["depth_map"] = str(resolved_depth_map)
            elif eff.get("depth_map"):
                eff["depth_map"] = str(_resolve_path(base_dir, eff["depth_map"]))
    if resolved_depth_map is not None and not any(e.get("type") == "depth_parallax" for e in effects):
        effects.append({"type": "depth_parallax", "depth_map": str(resolved_depth_map), "strength": 0.035, "mode": "loop"})

    ffmpeg_exe, _ = resolve_ffmpeg(args.ffmpeg)
    if not ffmpeg_exe:
        raise RuntimeError("FFmpeg not found in PATH and imageio-ffmpeg is unavailable.")

    duration = float(args.duration if args.duration is not None else plan_data.get("duration", 5.0))
    fps = int(args.fps if args.fps is not None else plan_data.get("fps", 30))
    if duration <= 0:
        parser.error(f"--duration must be > 0, got {duration}")
    if fps <= 0:
        parser.error(f"--fps must be > 0, got {fps}")

    report = render_motion(
        image_path=image_path,
        plan_data=plan_data,
        output_mp4=args.output.resolve(),
        duration=duration,
        fps=fps,
        min_width=args.min_width,
        max_width=args.max_width,
        ffmpeg_exe=ffmpeg_exe,
        webp_out=args.webp.resolve() if args.webp else None,
        preview_dir=args.preview_masks.resolve() if args.preview_masks else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
