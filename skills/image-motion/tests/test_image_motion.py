#!/usr/bin/env python3
"""Unit and integration tests for image-motion skill."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_environment import detect_step2_depth_backends, resolve_ffmpeg  # noqa: E402
from estimate_depth import (  # noqa: E402
    estimate_depth,
    normalize_depth_to_uint8,
    prepare_vit_input,
    resolve_onnx_providers,
)
from inspect_grid import draw_normalized_grid  # noqa: E402
from mask_refiner import (  # noqa: E402
    build_region_mask,
    build_synthetic_depth,
    infer_shoreline_from_mask,
    rasterize_polygons,
)
from motion_effects import (  # noqa: E402
    DepthParallaxEffect,
    FlagClothWaveEffect,
    OverlayFxEffect,
    RotatePartEffect,
    WaterfallFlowEffect,
    build_effect_pipeline,
)
from render_motion import _even_size, render_motion  # noqa: E402


def _make_synthetic_landscape(path: Path, w: int = 320, h: int = 240) -> np.ndarray:
    """Create a synthetic scene with crisp sky, mountain, lake, boat, and windmill."""
    im = Image.new("RGB", (w, h), (165, 205, 240))
    d = ImageDraw.Draw(im)
    # Mountain ridge around y = 0.55*h
    d.polygon([(0, int(0.58 * h)), (int(0.35 * w), int(0.32 * h)), (int(0.7 * w), int(0.45 * h)), (w, int(0.52 * h)), (w, int(0.6 * h)), (0, int(0.6 * h))], fill=(75, 95, 80))
    # Lake below y = 0.60*h
    d.rectangle([0, int(0.60 * h), w, h], fill=(28, 95, 130))
    # Bright reflection stripe on lake
    d.polygon([(int(0.42 * w), int(0.60 * h)), (int(0.49 * w), int(0.60 * h)), (int(0.53 * w), h), (int(0.39 * w), h)], fill=(195, 225, 235))
    # Yellow boat on right side of lake
    d.rectangle([int(0.72 * w), int(0.72 * h), int(0.92 * w), int(0.82 * h)], fill=(235, 195, 45))
    # White windmill blades in sky on left
    cx, cy = int(0.16 * w), int(0.28 * h)
    d.line([(cx - 18, cy - 18), (cx + 18, cy + 18)], fill=(250, 250, 250), width=3)
    d.line([(cx - 18, cy + 18), (cx + 18, cy - 18)], fill=(250, 250, 250), width=3)
    im.save(path)
    return np.array(im, dtype=np.float32)


class TestImageMotion(unittest.TestCase):
    def test_edge_snap_respects_shoreline_and_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "scene.png"
            rgb = _make_synthetic_landscape(img_path)
            # Coarse polygon intentionally overshoots 8px above real shoreline y=0.60 into mountain
            mask = build_region_mask(
                rgb,
                polygons=[[[0.0, 0.56], [1.0, 0.56], [1.0, 1.0], [0.0, 1.0]]],
                exclude_rects=[[0.71, 0.71, 0.93, 0.83]],
                edge_snap=True,
                snap_radius=0.05,
                feather_px=1.0,
            )
            # Mountain area above real shore (y=0.58) should stay near 0 after snapping
            self.assertLess(float(mask[int(0.57 * 240), 100]), 0.2)
            # Core lake should stay near 1
            self.assertGreater(float(mask[int(0.80 * 240), 100]), 0.9)
            # Excluded boat interior should remain 0
            self.assertLess(float(mask[int(0.77 * 240), int(0.82 * 320)]), 0.05)

            shore = infer_shoreline_from_mask(mask)
            self.assertAlmostEqual(float(shore[0, 120]) / 240.0, 0.60, delta=0.04)

    def test_all_effects_loop_continuity(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "scene.png"
            rgb = _make_synthetic_landscape(img_path)
            depth_path = Path(tmp) / "depth.png"
            Image.new("L", (320, 240), 128).save(depth_path)

            effects_cfg = [
                {
                    "type": "water_ripple",
                    "polygons": [[[0.0, 0.60], [1.0, 0.60], [1.0, 1.0], [0.0, 1.0]]],
                    "exclude_rects": [[0.71, 0.71, 0.93, 0.83]],
                    "amplitude": 1.0,
                },
                {
                    "type": "sky_drift",
                    "polygons": [[[0.0, 0.0], [1.0, 0.0], [1.0, 0.48], [0.0, 0.48]]],
                    "drift_x": 0.03,
                },
                {"type": "foliage_sway", "rects": [[0.0, 0.38, 0.7, 0.58]], "amplitude": 1.5},
                {"type": "rotate_part", "center": [0.16, 0.28], "radius": 0.10, "turns": 0.25},
                {"type": "depth_parallax", "depth_map": str(depth_path), "strength": 0.03, "mode": "loop"},
                {"type": "overlay_fx", "kind": "steam", "anchors": [[0.5, 0.7]], "opacity": 0.4},
                {"type": "overlay_fx", "kind": "sun_motes", "count": 8, "opacity": 0.4},
            ]
            pipeline = build_effect_pipeline(rgb, effects_cfg)

            def eval_at(u: float) -> np.ndarray:
                cur = rgb
                for eff in pipeline:
                    cur = eff.apply(cur, u, 4.0)
                return cur

            f0 = eval_at(0.0)
            f_mid = eval_at(0.5)
            f_end = eval_at(1.0)
            # Exact periodic return at u = 1.0 vs u = 0.0
            self.assertLess(float(np.abs(f_end - f0).mean()), 0.2)
            # Midpoint genuinely differs from start
            self.assertGreater(float(np.abs(f_mid - f0).mean()), 0.5)

    def test_grid_and_mp4_render(self):
        ffmpeg_exe, _ = resolve_ffmpeg("ffmpeg")
        if not ffmpeg_exe:
            self.skipTest("FFmpeg not available")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            img_path = tmp_p / "scene.png"
            _make_synthetic_landscape(img_path)
            grid_path = tmp_p / "grid.png"
            w, h = draw_normalized_grid(img_path, grid_path)
            self.assertEqual((w, h), (320, 240))
            self.assertTrue(grid_path.is_file())

            out_mp4 = tmp_p / "out.mp4"
            out_webp = tmp_p / "out.webp"
            plan = {
                "static_regions": {
                    "rects": [[0.71, 0.71, 0.93, 0.83]],
                },
                "effects": [
                    {
                        "type": "water_ripple",
                        "polygons": [[[0.0, 0.60], [1.0, 0.60], [1.0, 1.0], [0.0, 1.0]]],
                    },
                    {"type": "rotate_part", "center": [0.16, 0.28], "radius": 0.10, "turns": 0.25},
                ],
            }
            report = render_motion(
                image_path=img_path,
                plan_data=plan,
                output_mp4=out_mp4,
                duration=1.0,
                fps=15,
                min_width=480,
                max_width=640,
                ffmpeg_exe=ffmpeg_exe,
                webp_out=out_webp,
                preview_dir=tmp_p / "masks",
            )
            self.assertEqual(report["full_decode"], "passed")
            self.assertTrue(report["static_regions_locked"])
            self.assertLessEqual(report["static_region_warp_max_diff"], 0.05)
            self.assertTrue((tmp_p / "masks" / "static_regions_locked.png").is_file())
            self.assertTrue(out_mp4.is_file() and out_mp4.stat().st_size > 1000)
            self.assertTrue(out_webp.is_file() and out_webp.stat().st_size > 1000)
            self.assertTrue(out_mp4.with_suffix(".verification.json").is_file())

    def test_static_regions_lock_and_no_earthquake_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "scene.png"
            rgb = _make_synthetic_landscape(img_path)
            dp_loop = DepthParallaxEffect(rgb, {"mode": "loop"})
            dp_push = DepthParallaxEffect(rgb, {"mode": "push"})
            dp_orbit = DepthParallaxEffect(rgb, {"mode": "orbit"})
            self.assertEqual(dp_loop.sway_x, 0.0)
            self.assertEqual(dp_push.sway_x, 0.0)
            self.assertGreater(dp_orbit.sway_x, 0.0)

            ffmpeg_exe, _ = resolve_ffmpeg("ffmpeg")
            if not ffmpeg_exe:
                return
            tmp_p = Path(tmp)
            # Protect half of windmill blade disk + yellow boat via top-level static_regions
            out_mp4 = tmp_p / "locked.mp4"
            plan = {
                "static_regions": {"rects": [[0.71, 0.71, 0.93, 0.83], [0.16, 0.18, 0.28, 0.38]]},
                "effects": [
                    {"type": "water_ripple", "polygons": [[[0.0, 0.60], [1.0, 0.60], [1.0, 1.0], [0.0, 1.0]]]},
                    {"type": "foliage_sway", "rects": [[0.0, 0.35, 1.0, 0.60]]},
                    {"type": "rotate_part", "center": [0.16, 0.28], "radius": 0.10, "turns": 0.25},
                ],
            }
            report = render_motion(
                image_path=img_path,
                plan_data=plan,
                output_mp4=out_mp4,
                duration=0.6,
                fps=10,
                min_width=320,
                max_width=480,
                ffmpeg_exe=ffmpeg_exe,
            )
            self.assertTrue(report["static_regions_locked"])
            self.assertLessEqual(report["static_region_warp_max_diff"], 0.05)

    def test_top_aligned_snap_inverted_rect_and_inward_feather(self):
        # Height not divisible by 3 inside cropped sub-region (e.g. top sky down to y=0.52 -> 125px)
        w, h = 200, 241
        im = Image.new("RGB", (w, h), (160, 200, 245))
        draw = ImageDraw.Draw(im)
        # Sharp dark mountain ridge below y = 100 (0.415)
        draw.rectangle([0, 100, w, h], fill=(35, 50, 40))
        rgb = np.array(im, dtype=np.float32)

        # Inverted rectangle coords + single 2D polygon list format should normalize cleanly
        ras = rasterize_polygons(w, h, rects=[[0.9, 0.8, 0.2, 0.3]], polygons=[[[0.1, 0.1], [0.4, 0.1], [0.4, 0.3]]])
        ras_arr = np.array(ras)
        self.assertGreater(int(ras_arr[int(0.55 * h), int(0.55 * w)]), 200)
        self.assertGreater(int(ras_arr[int(0.15 * h), int(0.25 * w)]), 200)

        # Coarse sky box intentionally overshoots 6px below mountain ridge (within snap_radius=0.04 -> 8px)
        mask = build_region_mask(
            rgb,
            rects=[[0.0, 0.0, 1.0, 106.0 / h]],
            edge_snap=True,
            snap_radius=0.04,
            feather_px=2.5,
        )
        # Deep inside sky remains ~1.0
        self.assertGreater(float(mask[30, 100]), 0.95)
        # Outside sharp ridge (in dark mountain at y=102), inward-only feather keeps mask near 0.0
        self.assertLess(float(mask[102, 100]), 0.02)

    def test_overlay_variants_and_loop_continuity(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "scene.png"
            rgb = _make_synthetic_landscape(img_path)

            with self.assertRaises(ValueError):
                OverlayFxEffect(rgb, {"kind": "unknown_fx"})

            for kind, extra in (
                ("rain", {"count": 40, "opacity": 0.6}),
                ("snow", {"count": 30, "opacity": 0.6}),
                ("warm_glow", {"anchors": [[0.2, 0.3]], "radius": 0.15, "opacity": 0.6}),
                ("sunbeam", {"opacity": 0.5}),
            ):
                eff = OverlayFxEffect(rgb, {"kind": kind, **extra})
                f0 = eff.apply(rgb, 0.0, 5.0)
                f1 = eff.apply(rgb, 1.0, 5.0)
                peak = max(float(np.abs(eff.apply(rgb, u_test, 5.0) - f0).max()) for u_test in (0.125, 0.25, 0.375))
                self.assertLess(float(np.abs(f1 - f0).mean()), 0.1, f"{kind} loop seam failed")
                self.assertGreater(peak, 1.0, f"{kind} showed no motion")

    def test_rotate_part_max_y_and_static_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "mill.png"
            rgb = _make_synthetic_landscape(img_path)
            rot = RotatePartEffect(
                rgb,
                {
                    "center": [0.16, 0.28],
                    "radius": 0.10,
                    "turns": 0.25,
                    "max_y": 0.35,
                    "exclude_rects": [[0.16, 0.18, 0.30, 0.38]],
                },
            )
            f0 = rot.apply(rgb, 0.0, 5.0)
            f_mid = rot.apply(rgb, 0.5, 5.0)
            f1 = rot.apply(rgb, 1.0, 5.0)
            self.assertLess(float(np.abs(f1 - f0).mean()), 0.2)
            # Lower pixels below max_y=0.35 remain locked (allow feather tail ~0.04*240 => y>=95 untouched)
            self.assertLess(float(np.max(np.abs(f_mid[96:110, 20:80] - rgb[96:110, 20:80]))), 0.5)
            # Explicitly excluded static rect interior stays locked
            self.assertLess(float(np.max(np.abs(f_mid[50:80, 62:92] - rgb[50:80, 62:92]))), 0.5)

    def test_synthetic_depth_planar_foreground_order(self):
        rgb = np.zeros((100, 100, 3), dtype=np.float32)
        depth = build_synthetic_depth(
            rgb,
            horizon_y=0.4,
            sky_depth=0.05,
            horizon_depth=0.2,
            bottom_depth=0.95,
            foreground_regions=[
                {"rect": [0.2, 0.7, 0.5, 0.98], "depth": 0.60},
                {"rect": [0.3, 0.75, 0.45, 0.95], "depth": 0.85},
            ],
            edge_snap=False,
        )
        # Even where bottom ramp is ~0.90, explicit lower depth=0.60 must NOT be overwritten by np.maximum
        self.assertAlmostEqual(float(depth[85, 22]), 0.60, delta=0.03)
        # Closer nested region depth=0.85 overrides 0.60
        self.assertAlmostEqual(float(depth[85, 38]), 0.85, delta=0.03)

    def test_portrait_even_size_sky_drift_peak_and_lock_camera(self):
        self.assertEqual(_even_size(500, 1500, 1160, 1920), (640, 1920))
        ffmpeg_exe, _ = resolve_ffmpeg("ffmpeg")
        if not ffmpeg_exe:
            self.skipTest("FFmpeg not available")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            img_path = tmp_p / "scene.png"
            im = Image.new("RGB", (320, 240), (160, 205, 245))
            d = ImageDraw.Draw(im)
            # Textured clouds in upper sky so horizontal drift produces visible change
            d.ellipse([40, 20, 120, 60], fill=(250, 252, 255))
            d.ellipse([150, 15, 240, 55], fill=(240, 246, 255))
            # Watermark / corner logo region
            d.rectangle([220, 200, 315, 235], fill=(255, 255, 255))
            im.save(img_path)

            # Test sky_drift alone (phase-symmetric at u=0.5, peak diff > 0 at u=0.25/0.75)
            sky_mp4 = tmp_p / "sky.mp4"
            sky_report = render_motion(
                image_path=img_path,
                plan_data={
                    "static_regions": {"rects": [[0.0, 0.55, 1.0, 1.0]]},
                    "effects": [{"type": "sky_drift", "polygons": [[[0.0, 0.0], [1.0, 0.0], [1.0, 0.50], [0.0, 0.50]]], "drift_x": 0.06}],
                },
                output_mp4=sky_mp4,
                duration=0.8,
                fps=8,
                min_width=320,
                max_width=480,
                ffmpeg_exe=ffmpeg_exe,
            )
            self.assertGreater(sky_report["mean_motion_peak_diff"], 0.2)
            self.assertLessEqual(sky_report["static_region_warp_max_diff"], 0.05)

            # Test lock_camera watermark pinning alongside depth_parallax + explicit empty effects preservation
            cam_mp4 = tmp_p / "cam_lock.mp4"
            cam_report = render_motion(
                image_path=img_path,
                plan_data={
                    "static_regions": [{"rect": [0.70, 0.85, 0.98, 0.98], "lock_camera": True}],
                    "effects": [{"type": "depth_parallax", "horizon_y": 0.5, "strength": 0.04, "mode": "loop"}],
                },
                output_mp4=cam_mp4,
                duration=0.6,
                fps=8,
                min_width=320,
                max_width=480,
                ffmpeg_exe=ffmpeg_exe,
                preview_dir=tmp_p / "masks",
            )
            self.assertTrue(cam_report["camera_locked_regions"])
            self.assertLessEqual(cam_report["static_region_warp_max_diff"], 0.01)
            self.assertTrue((tmp_p / "masks" / "camera_locked_regions.png").is_file())

            empty_mp4 = tmp_p / "empty.mp4"
            empty_report = render_motion(
                image_path=img_path,
                plan_data={"effects": []},
                output_mp4=empty_mp4,
                duration=0.4,
                fps=5,
                min_width=320,
                max_width=480,
                ffmpeg_exe=ffmpeg_exe,
            )
            self.assertEqual(empty_report["effects"], [])
            self.assertEqual(empty_report["mean_motion_peak_diff"], 0.0)

    def test_step2_estimate_depth_and_cli_auto_depth(self):
        # 1) Preprocessing shape multiples of 14 + normalization edge cases
        img = Image.new("RGB", (640, 360), (90, 140, 210))
        tensor, orig_size = prepare_vit_input(img, max_size=518)
        self.assertEqual(orig_size, (640, 360))
        self.assertEqual(tensor.ndim, 4)
        self.assertEqual(tensor.dtype, np.float32)
        self.assertEqual(tensor.shape[2] % 14, 0)
        self.assertEqual(tensor.shape[3] % 14, 0)

        # Depth normalization handles constant & non-finite arrays + invert
        const_depth = normalize_depth_to_uint8(np.full((14, 28), np.nan, dtype=np.float32), (100, 60))
        self.assertEqual(const_depth.size, (100, 60))
        self.assertEqual(int(np.asarray(const_depth)[0, 0]), 128)

        grad = np.broadcast_to(np.linspace(0.0, 10.0, 28, dtype=np.float32), (1, 14, 28))
        d_norm = np.asarray(normalize_depth_to_uint8(grad, (64, 32), invert=False))
        d_inv = np.asarray(normalize_depth_to_uint8(grad, (64, 32), invert=True))
        self.assertLess(int(d_norm[16, 2]), 20)
        self.assertGreater(int(d_norm[16, 61]), 235)
        self.assertAlmostEqual(int(d_norm[16, 2]) + int(d_inv[16, 2]), 255, delta=2)

        # 2) Mocked ONNXRuntime session + estimate_depth() end-to-end
        class FakeInput:
            name = "pixel_values"
            shape = [1, 3, 28, 42]

        class FakeSession:
            def __init__(self, path, providers=None):
                self.path = path
                self.providers = providers

            def get_inputs(self):
                return [FakeInput()]

            def run(self, _outputs, feed):
                arr = feed["pixel_values"]
                self.seen_shape = arr.shape
                h, w = arr.shape[2], arr.shape[3]
                y_ramp = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None] * np.ones((1, w), dtype=np.float32)
                return [y_ramp[None, ...]]

        fake_ort = types.SimpleNamespace(
            get_available_providers=lambda: ["CPUExecutionProvider", "CoreMLExecutionProvider"],
            InferenceSession=FakeSession,
        )
        self.assertEqual(resolve_onnx_providers(fake_ort), ["CoreMLExecutionProvider", "CPUExecutionProvider"])

        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            src_img = tmp_p / "src.png"
            _make_synthetic_landscape(src_img, w=160, h=120)
            dummy_onnx = tmp_p / "dummy.onnx"
            dummy_onnx.write_bytes(b"onnx-placeholder")
            depth_out = tmp_p / "depth.png"

            with mock.patch.dict(sys.modules, {"onnxruntime": fake_ort}):
                depth_img = estimate_depth(src_img, depth_out, backend="onnx", onnx_path=dummy_onnx)
                self.assertTrue(depth_out.is_file())
                self.assertEqual(depth_img.size, (160, 120))
                d_arr = np.asarray(depth_img)
                self.assertLess(int(d_arr[2, 80]), 25)
                self.assertGreater(int(d_arr[117, 80]), 230)

        # 3) render_motion CLI --auto-depth subprocess wiring check (without requiring HF download)
        info = detect_step2_depth_backends()
        self.assertIn("backends_available", info)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            src_img = tmp_p / "src.png"
            _make_synthetic_landscape(src_img, w=160, h=120)
            dummy_onnx = tmp_p / "dummy.onnx"
            dummy_onnx.write_bytes(b"onnx-placeholder")
            # Inject a tiny sitecustomize in tmpdir to provide fake onnxruntime to subprocess CLI
            (tmp_p / "onnxruntime.py").write_text(
                "import numpy as np\n"
                "class _In:\n"
                "    name = 'pixel_values'\n"
                "    shape = [1, 3, 'h', 'w']\n"
                "class InferenceSession:\n"
                "    def __init__(self, p, providers=None): pass\n"
                "    def get_inputs(self): return [_In()]\n"
                "    def run(self, _, feed):\n"
                "        x = feed['pixel_values']\n"
                "        h, w = x.shape[2], x.shape[3]\n"
                "        return [np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None] * np.ones((1, w), dtype=np.float32)]\n"
                "def get_available_providers(): return ['CPUExecutionProvider']\n",
                encoding="utf-8",
            )
            out_mp4 = tmp_p / "auto_depth.mp4"
            env_copy = os.environ.copy()
            old_pp = env_copy.get("PYTHONPATH", "")
            env_copy["PYTHONPATH"] = f"{tmp_p}{os.pathsep}{old_pp}" if old_pp else str(tmp_p)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "render_motion.py"),
                    "--image",
                    str(src_img),
                    "--auto-depth",
                    "--depth-backend",
                    "onnx",
                    "--onnx-path",
                    str(dummy_onnx),
                    "--output",
                    str(out_mp4),
                    "--duration",
                    "0.4",
                    "--fps",
                    "5",
                    "--min-width",
                    "160",
                    "--max-width",
                    "320",
                ],
                env=env_copy,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            cli_report = json.loads(proc.stdout)
            self.assertEqual(cli_report["full_decode"], "passed")
            self.assertIn("depth_parallax", cli_report["pipeline_effects"])
            self.assertTrue(out_mp4.with_suffix(".depth.png").is_file())

    def test_waterfall_flow_and_flag_cloth_wave(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            img_path = tmp_p / "waterfall_flag.png"
            w, h = 320, 240
            im = Image.new("RGB", (w, h), (65, 80, 70))
            d = ImageDraw.Draw(im)
            # Textured vertical waterfall chute at x = [0.20, 0.36], y = [0.15, 0.85]
            for y_pos in range(int(0.15 * h), int(0.85 * h), 4):
                tone = 210 if (y_pos // 4) % 2 == 0 else 145
                d.rectangle([int(0.20 * w), y_pos, int(0.36 * w), y_pos + 3], fill=(tone - 20, tone, 245))
            # Flagpole at x = 0.60 and textured red-gold flag at x = [0.60, 0.88], y = [0.20, 0.42]
            d.rectangle([int(0.58 * w), int(0.15 * h), int(0.60 * w), int(0.75 * h)], fill=(90, 90, 95))
            for x_pos in range(int(0.60 * w), int(0.88 * w), 5):
                c_r = 230 if (x_pos // 5) % 2 == 0 else 190
                d.rectangle([x_pos, int(0.20 * h), x_pos + 4, int(0.42 * h)], fill=(c_r, 55, 45))
            im.save(img_path)
            rgb = np.array(im, dtype=np.float32)

            with self.assertRaises(ValueError):
                FlagClothWaveEffect(rgb, {"rects": [[0.60, 0.20, 0.88, 0.42]], "anchor_side": "diagonal"})

            wf = WaterfallFlowEffect(
                rgb,
                {
                    "rects": [[0.20, 0.15, 0.36, 0.85]],
                    "edge_snap": False,
                    "angle": 90.0,
                    "flow_distance": 0.20,
                    "mist": 0.5,
                },
            )
            wf0 = wf.apply(rgb, 0.0, 5.0)
            wf_q = wf.apply(rgb, 0.25, 5.0)
            wf1 = wf.apply(rgb, 1.0, 5.0)
            self.assertLess(float(np.abs(wf1 - wf0).mean()), 0.1)
            self.assertGreater(float(np.abs(wf_q - wf0).mean()), 0.3)

            for side in ("left", "right", "top", "bottom"):
                flag = FlagClothWaveEffect(
                    rgb,
                    {
                        "rects": [[0.60, 0.20, 0.88, 0.42]],
                        "edge_snap": False,
                        "feather_px": 0.0,
                        "anchor_side": side,
                        "amplitude": 4.0,
                    },
                )
                fl0 = flag.apply(rgb, 0.0, 5.0)
                fl_q = flag.apply(rgb, 0.25, 5.0)
                fl1 = flag.apply(rgb, 1.0, 5.0)
                self.assertLess(float(np.abs(fl1 - fl0).mean()), 0.05)
                self.assertGreater(float(np.abs(fl_q - fl0).max()), 2.0)
                if side == "left":
                    # Leftmost anchored column x = int(0.60 * w) stays completely pinned while right tip moves
                    anchor_x = int(0.60 * w)
                    tip_x = int(0.85 * w)
                    y_slice = slice(int(0.22 * h), int(0.40 * h))
                    self.assertLess(float(np.max(np.abs(fl_q[y_slice, anchor_x] - fl0[y_slice, anchor_x]))), 0.05)
                    self.assertGreater(float(np.max(np.abs(fl_q[y_slice, tip_x] - fl0[y_slice, tip_x]))), 2.0)

            ffmpeg_exe, _ = resolve_ffmpeg("ffmpeg")
            if ffmpeg_exe:
                out_mp4 = tmp_p / "wf_flag.mp4"
                rep = render_motion(
                    image_path=img_path,
                    plan_data={
                        "static_regions": {"rects": [[0.56, 0.14, 0.60, 0.76]]},
                        "effects": [
                            {"type": "waterfall_flow", "rects": [[0.20, 0.15, 0.36, 0.85]], "edge_snap": False},
                            {
                                "type": "flag_cloth_wave",
                                "rects": [[0.59, 0.20, 0.88, 0.42]],
                                "anchor_side": "left",
                                "edge_snap": False,
                            },
                        ],
                    },
                    output_mp4=out_mp4,
                    duration=0.6,
                    fps=10,
                    min_width=320,
                    max_width=480,
                    ffmpeg_exe=ffmpeg_exe,
                    preview_dir=tmp_p / "masks",
                )
                self.assertEqual(rep["full_decode"], "passed")
                self.assertLessEqual(rep["static_region_warp_max_diff"], 0.05)
                self.assertTrue((tmp_p / "masks" / "mask_0_FlagClothWaveEffect.png").is_file())
                self.assertTrue((tmp_p / "masks" / "mask_1_WaterfallFlowEffect.png").is_file())


if __name__ == "__main__":
    unittest.main()
