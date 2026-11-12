"""Composable, loop-seamless procedural motion primitives for static images."""
from __future__ import annotations

import math
from typing import Any
import numpy as np
from PIL import Image, ImageFilter

from mask_refiner import build_region_mask, build_synthetic_depth, infer_shoreline_from_mask, rasterize_polygons


def _normalize_region_args(cfg: dict[str, Any]) -> tuple[list, list, list, list]:
    polys = list(cfg.get("polygons", ()))
    if "polygon" in cfg:
        polys.append(cfg["polygon"])
    rects = list(cfg.get("rects", ()))
    if "rect" in cfg:
        rects.append(cfg["rect"])
    exc_polys = list(cfg.get("exclude_polygons", ()))
    if "exclude_polygon" in cfg:
        exc_polys.append(cfg["exclude_polygon"])
    exc_rects = list(cfg.get("exclude_rects", ()))
    if "exclude_rect" in cfg:
        exc_rects.append(cfg["exclude_rect"])
    return polys, rects, exc_polys, exc_rects


def bilinear_sample(img: np.ndarray, sample_x: np.ndarray, sample_y: np.ndarray) -> np.ndarray:
    """Vectorized bilinear interpolation for HxWxC float32 images."""
    h, w = img.shape[:2]
    x = np.clip(sample_x, 0.0, float(w - 1))
    y = np.clip(sample_y, 0.0, float(h - 1))

    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)

    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]

    c00 = img[y0, x0]
    c10 = img[y0, x1]
    c01 = img[y1, x0]
    c11 = img[y1, x1]

    top = c00 * (1.0 - fx) + c10 * fx
    bot = c01 * (1.0 - fx) + c11 * fx
    return top * (1.0 - fy) + bot * fy


def extend_masked_pixels(img: np.ndarray, mask: np.ndarray, pad_px: int, threshold: float = 0.05) -> np.ndarray:
    """Propagate masked foreground RGB values outward so shifts never sample across rigid edges."""
    if pad_px <= 0:
        return img
    valid = mask > threshold
    if not np.any(valid):
        return img
    out = img.copy()
    filled = valid.copy()
    for _ in range(pad_px):
        new_out = out.copy()
        new_filled = filled.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sy_dst = slice(max(0, dy), out.shape[0] + min(0, dy))
            sx_dst = slice(max(0, dx), out.shape[1] + min(0, dx))
            sy_src = slice(max(0, -dy), out.shape[0] + min(0, -dy))
            sx_src = slice(max(0, -dx), out.shape[1] + min(0, -dx))
            take = (~new_filled[sy_dst, sx_dst]) & filled[sy_src, sx_src]
            if np.any(take):
                dst_slice = new_out[sy_dst, sx_dst]
                src_slice = out[sy_src, sx_src]
                dst_slice[take] = src_slice[take]
                new_filled[sy_dst, sx_dst][take] = True
        out = new_out
        filled = new_filled
        if np.all(filled):
            break
    return out


class MotionEffect:
    """Base interface for a pre-initialized, loop-seamless motion effect."""

    def apply(self, frame: np.ndarray, u: float, duration: float) -> np.ndarray:
        """Apply effect at normalized loop phase u in [0, 1)."""
        return frame


class WaterRippleEffect(MotionEffect):
    """Multi-directional perspective capillary water ripples with subtle reflection shimmer."""

    def __init__(self, base_rgb: np.ndarray, cfg: dict[str, Any]):
        h, w, _ = base_rgb.shape
        polys, rects, exc_polys, exc_rects = _normalize_region_args(cfg)
        self.mask = build_region_mask(
            base_rgb,
            polygons=polys,
            rects=rects,
            exclude_polygons=exc_polys,
            exclude_rects=exc_rects,
            edge_snap=cfg.get("edge_snap", True),
            snap_radius=float(cfg.get("snap_radius", 0.025)),
            feather_px=float(cfg.get("feather_px", 2.0)),
        )
        ys, _ = np.where(self.mask > 0.01)
        if len(ys) == 0:
            self.active = False
            return
        self.active = True

        shore_y = infer_shoreline_from_mask(self.mask)
        # Derive crop top from full mask extent so narrow inlets above smoothed shore_y aren't cropped
        self.y_start = max(0, int(ys.min()) - 4)

        yy, xx = np.mgrid[self.y_start:h, 0:w].astype(np.float32)
        shore_sub = shore_y[:, :]
        denom = np.maximum(h - shore_sub, 1.0)
        depth = np.clip((yy - shore_sub) / denom, 0.0, 1.0)

        scale_ref = h / 772.0
        self.persp_y = np.power(depth + 0.045, 0.42) * (320.0 * scale_ref)
        self.persp_x = (xx - w * 0.5) / (0.35 + 0.65 * depth)
        amp_scale = float(cfg.get("amplitude", 1.0)) * scale_ref
        mask_sub = self.mask[self.y_start:]
        # Smoothly damp wave amplitude near shore/obstacle boundaries so waves don't shear against static rocks
        core_u8 = ((mask_sub > 0.65).astype(np.uint8)) * 255
        damp_r = max(3.0, min(w, h) * 0.014)
        edge_damp = (
            np.array(Image.fromarray(core_u8).filter(ImageFilter.GaussianBlur(radius=damp_r)), dtype=np.float32)
            / 255.0
        )
        self.amp_sub = mask_sub * (0.25 + 0.75 * edge_damp) * (0.28 + 0.72 * np.power(depth, 0.55)) * amp_scale
        self.xx_sub = xx
        self.yy_sub = yy - float(self.y_start)
        self.m_sub = mask_sub[:, :, None]
        self.valid_sub = (mask_sub > 0.05)[..., None]
        pad_px = max(6, int(math.ceil(max(abs(amp_scale) * 9.5, 4.0))) + 2)
        self.ext_water = extend_masked_pixels(base_rgb[self.y_start:], self.mask[self.y_start:], pad_px)
        self.shimmer = float(cfg.get("shimmer", 0.7))
        self.speed = max(1, int(round(float(cfg.get("speed", 1.0)))))
        self.waves = [
            (0.032 / scale_ref, 0.240 / scale_ref, 2, 2.7, 0.90, 0.2),
            (-0.041 / scale_ref, 0.310 / scale_ref, 3, 1.85, -0.75, 1.4),
            (0.068 / scale_ref, 0.450 / scale_ref, 2, 1.20, 0.55, 2.7),
            (-0.085 / scale_ref, 0.560 / scale_ref, 4, 0.80, -0.42, 4.1),
            (0.018 / scale_ref, 0.145 / scale_ref, 1, 3.10, 0.50, 0.9),
        ]

    def apply(self, frame: np.ndarray, u: float, duration: float) -> np.ndarray:
        if not self.active:
            return frame
        tau = 2.0 * math.pi * u * self.speed
        dy = np.zeros_like(self.persp_x)
        dx = np.zeros_like(self.persp_x)
        slope = np.zeros_like(self.persp_x)

        for kx, ky, cyc, ay, ax, p0 in self.waves:
            phase = kx * self.persp_x + ky * self.persp_y - cyc * tau + p0
            s = np.sin(phase)
            c = np.cos(phase)
            dy += ay * s
            dx += ax * c
            slope += ay * ky * c

        sx = self.xx_sub + dx * self.amp_sub
        sy = self.yy_sub + dy * self.amp_sub
        sub = frame[self.y_start:]
        src = np.where(self.valid_sub, sub, self.ext_water)
        sampled = bilinear_sample(src, sx, sy)

        if self.shimmer > 0.0:
            luma = (0.299 * sub[..., 0] + 0.587 * sub[..., 1] + 0.114 * sub[..., 2]) / 255.0
            glint = np.clip(slope * 0.55, -0.35, 1.0)
            glint_strength = np.maximum(glint, 0.0) * (0.25 + 0.75 * luma) * self.amp_sub
            sampled = np.clip(sampled + glint_strength[..., None] * (16.0 * self.shimmer), 0.0, 255.0)

        out = frame.copy()
        out[self.y_start:] = sub * (1.0 - self.m_sub) + sampled * self.m_sub
        return out


class SkyDriftEffect(MotionEffect):
    """Dual-phase continuous unidirectional sky/cloud drift with mountain-edge protection."""

    def __init__(self, base_rgb: np.ndarray, cfg: dict[str, Any]):
        h, w, _ = base_rgb.shape
        polys, rects, exc_polys, exc_rects = _normalize_region_args(cfg)
        self.mask = build_region_mask(
            base_rgb,
            polygons=polys,
            rects=rects,
            exclude_polygons=exc_polys,
            exclude_rects=exc_rects,
            edge_snap=cfg.get("edge_snap", True),
            snap_radius=float(cfg.get("snap_radius", 0.03)),
            feather_px=float(cfg.get("feather_px", 3.0)),
        )
        self.shift_px = float(cfg.get("drift_x", 0.024)) * w
        self.shift_py = float(cfg.get("drift_y", 0.0)) * h
        ys, xs = np.where(self.mask > 0.01)
        if len(ys) == 0:
            self.active = False
            return
        self.active = True
        self.y_end = min(h, int(ys.max()) + 4)
        pad_px = max(6, int(math.ceil(max(abs(self.shift_px), abs(self.shift_py)) * 0.6)) + 4)
        mask_sub = self.mask[:self.y_end]
        self.valid_sub = (mask_sub > 0.05)[..., None]
        self.ext_sky = extend_masked_pixels(base_rgb[:self.y_end], mask_sub, pad_px)
        self.yy, self.xx = np.mgrid[0:self.y_end, 0:w].astype(np.float32)
        # Taper drift amplitude near mountain ridges / lower mask boundary to prevent double-edge ghosting
        core_u8 = ((mask_sub > 0.70).astype(np.uint8)) * 255
        damp_r = max(5.0, min(w, h) * 0.022)
        ridge_damp = (
            np.array(Image.fromarray(core_u8).filter(ImageFilter.GaussianBlur(radius=damp_r)), dtype=np.float32)
            / 255.0
        )
        self.drift_env = np.minimum(mask_sub, ridge_damp)
        self.phase_map = (0.35 * (self.xx / max(float(w), 1.0)) + 0.20 * (self.yy / max(float(self.y_end), 1.0))).astype(
            np.float32
        )
        self.m_sub = mask_sub[:, :, None]

    def apply(self, frame: np.ndarray, u: float, duration: float) -> np.ndarray:
        if not self.active:
            return frame
        u1 = np.mod(u + self.phase_map, 1.0)
        u2 = np.mod(u1 + 0.5, 1.0)
        w1 = (0.5 * (1.0 - np.cos(2.0 * math.pi * u1)))[..., None]
        w2 = 1.0 - w1

        sub = frame[:self.y_end]
        src = np.where(self.valid_sub, sub, self.ext_sky)
        env = self.drift_env
        s1 = bilinear_sample(
            src,
            self.xx - (u1 - 0.5) * (self.shift_px * env),
            self.yy - (u1 - 0.5) * (self.shift_py * env),
        )
        s2 = bilinear_sample(
            src,
            self.xx - (u2 - 0.5) * (self.shift_px * env),
            self.yy - (u2 - 0.5) * (self.shift_py * env),
        )
        drifted = s1 * w1 + s2 * w2
        out = frame.copy()
        out[:self.y_end] = sub * (1.0 - self.m_sub) + drifted * self.m_sub
        return out


class FoliageSwayEffect(MotionEffect):
    """Gentle periodic wind gusts across grass/trees/foliage masks."""

    def __init__(self, base_rgb: np.ndarray, cfg: dict[str, Any]):
        h, w, _ = base_rgb.shape
        polys, rects, exc_polys, exc_rects = _normalize_region_args(cfg)
        self.mask = build_region_mask(
            base_rgb,
            polygons=polys,
            rects=rects,
            exclude_polygons=exc_polys,
            exclude_rects=exc_rects,
            edge_snap=cfg.get("edge_snap", True),
            snap_radius=float(cfg.get("snap_radius", 0.025)),
            feather_px=float(cfg.get("feather_px", 3.5)),
        )
        ys, xs = np.where(self.mask > 0.01)
        if len(ys) == 0:
            self.active = False
            return
        self.active = True
        self.y0 = max(0, int(ys.min()) - 4)
        self.y1 = min(h, int(ys.max()) + 4)
        self.x0 = max(0, int(xs.min()) - 4)
        self.x1 = min(w, int(xs.max()) + 4)
        yy, xx = np.mgrid[self.y0:self.y1, self.x0:self.x1].astype(np.float32)
        self.xx_rel = xx - float(self.x0)
        self.yy_rel = yy - float(self.y0)
        self.xx = xx
        self.yy = yy
        self.amp = float(cfg.get("amplitude", 2.2)) * (min(w, h) / 772.0)
        self.cycles = max(1, int(round(float(cfg.get("speed", 1.0)))))
        mask_crop = self.mask[self.y0:self.y1, self.x0:self.x1]
        self.m_sub = mask_crop[..., None]
        self.valid_sub = (mask_crop > 0.05)[..., None]
        pad_px = max(4, int(math.ceil(abs(self.amp) * 1.5)) + 2)
        self.ext_foliage = extend_masked_pixels(base_rgb[self.y0:self.y1, self.x0:self.x1], mask_crop, pad_px)

    def apply(self, frame: np.ndarray, u: float, duration: float) -> np.ndarray:
        if not self.active:
            return frame
        tau = 2.0 * math.pi * u * self.cycles
        dx = self.amp * (
            0.65 * np.sin(0.035 * self.xx + 0.045 * self.yy - tau)
            + 0.35 * np.sin(-0.070 * self.xx + 0.060 * self.yy - 2.0 * tau + 1.1)
        )
        dy = (self.amp * 0.35) * np.cos(0.045 * self.xx - 0.030 * self.yy - tau + 0.7)
        m2 = self.m_sub[..., 0]
        sub = frame[self.y0:self.y1, self.x0:self.x1]
        src = np.where(self.valid_sub, sub, self.ext_foliage)
        sampled = bilinear_sample(src, self.xx_rel + dx * m2, self.yy_rel + dy * m2)
        out = frame.copy()
        out[self.y0:self.y1, self.x0:self.x1] = sub * (1.0 - self.m_sub) + sampled * self.m_sub
        return out


class WaterfallFlowEffect(MotionEffect):
    """Directional continuous cascade/stream flow with traveling foam streaks and base mist."""

    def __init__(self, base_rgb: np.ndarray, cfg: dict[str, Any]):
        h, w, _ = base_rgb.shape
        polys, rects, exc_polys, exc_rects = _normalize_region_args(cfg)
        self.mask = build_region_mask(
            base_rgb,
            polygons=polys,
            rects=rects,
            exclude_polygons=exc_polys,
            exclude_rects=exc_rects,
            edge_snap=cfg.get("edge_snap", True),
            snap_radius=float(cfg.get("snap_radius", 0.025)),
            feather_px=float(cfg.get("feather_px", 2.5)),
        )
        ys, xs = np.where(self.mask > 0.01)
        if len(ys) == 0:
            self.active = False
            return
        self.active = True

        self.y0 = max(0, int(ys.min()) - 6)
        self.y1 = min(h, int(ys.max()) + 8)
        self.x0 = max(0, int(xs.min()) - 6)
        self.x1 = min(w, int(xs.max()) + 6)

        angle_rad = math.radians(float(cfg.get("angle", 90.0)))
        self.ux = math.cos(angle_rad)
        self.uy = math.sin(angle_rad)
        self.px = -self.uy
        self.py = self.ux

        yy, xx = np.mgrid[self.y0:self.y1, self.x0:self.x1].astype(np.float32)
        self.xx_rel = xx - float(self.x0)
        self.yy_rel = yy - float(self.y0)
        mask_crop = self.mask[self.y0:self.y1, self.x0:self.x1]

        s_along = self.xx_rel * self.ux + self.yy_rel * self.uy
        s_perp = self.xx_rel * self.px + self.yy_rel * self.py
        active_s = s_along[mask_crop > 0.05]
        s_min = float(active_s.min()) if len(active_s) else float(s_along.min())
        s_max = float(active_s.max()) if len(active_s) else float(s_along.max())
        span_along = max(s_max - s_min, 12.0)

        self.t_along = np.clip((s_along - s_min) / span_along, 0.0, 1.0)
        self.s_along = s_along
        self.s_perp = s_perp

        flow_frac = float(np.clip(cfg.get("flow_distance", 0.16), 0.02, 0.45))
        self.travel_px = span_along * flow_frac
        self.turbulence = float(cfg.get("turbulence", 1.0)) * (min(w, h) / 772.0)
        self.foam_shimmer = float(cfg.get("foam_shimmer", 0.65))
        self.mist = float(cfg.get("mist", 0.40))
        self.speed = max(1, int(round(float(cfg.get("speed", 1.0)))))

        core_u8 = ((mask_crop > 0.55).astype(np.uint8)) * 255
        damp_r = max(3.0, min(w, h) * 0.012)
        bank_damp = (
            np.array(Image.fromarray(core_u8).filter(ImageFilter.GaussianBlur(radius=damp_r)), dtype=np.float32)
            / 255.0
        )
        self.flow_env = mask_crop * (0.25 + 0.75 * bank_damp)
        self.phase_map = (0.55 * self.t_along + 0.18 * np.sin(0.09 * self.s_perp)).astype(np.float32)

        pad_px = max(6, int(math.ceil(self.travel_px * 0.55 + abs(self.turbulence) * 4.0)) + 3)
        self.ext_water = extend_masked_pixels(base_rgb[self.y0:self.y1, self.x0:self.x1], mask_crop, pad_px)
        self.valid_sub = (mask_crop > 0.05)[..., None]
        self.m_sub = mask_crop[..., None]

        if self.mist > 0.0 and self.uy > 0.25:
            mist_zone = np.sin(math.pi * np.clip((self.t_along - 0.70) / 0.30, 0.0, 1.0)) * mask_crop
            mist_u8 = (np.clip(mist_zone, 0.0, 1.0) * 255.0).astype(np.uint8)
            mist_blur = (
                np.array(
                    Image.fromarray(mist_u8).filter(ImageFilter.GaussianBlur(radius=max(4.0, span_along * 0.05))),
                    dtype=np.float32,
                )
                / 255.0
            )
            self.mist_env: np.ndarray | None = mist_blur * mask_crop
        else:
            self.mist_env = None

    def apply(self, frame: np.ndarray, u: float, duration: float) -> np.ndarray:
        if not self.active:
            return frame
        tau = 2.0 * math.pi * u * self.speed
        u1 = np.mod(u * self.speed + self.phase_map, 1.0)
        u2 = np.mod(u1 + 0.5, 1.0)
        w1 = (0.5 * (1.0 - np.cos(2.0 * math.pi * u1)))[..., None]
        w2 = 1.0 - w1

        rip_along = self.turbulence * (
            1.8 * np.sin(0.11 * self.s_along + 0.05 * self.s_perp - 2.0 * tau)
            + 1.1 * np.sin(0.23 * self.s_along - 0.08 * self.s_perp - 3.0 * tau + 1.3)
        )
        rip_perp = self.turbulence * (0.85 * np.cos(0.14 * self.s_along - 0.12 * self.s_perp - 2.0 * tau + 0.6))

        d1 = -(u1 - 0.5) * self.travel_px + rip_along
        d2 = -(u2 - 0.5) * self.travel_px + rip_along
        env = self.flow_env

        sub = frame[self.y0:self.y1, self.x0:self.x1]
        src = np.where(self.valid_sub, sub, self.ext_water)
        s1 = bilinear_sample(
            src,
            self.xx_rel + (d1 * self.ux + rip_perp * self.px) * env,
            self.yy_rel + (d1 * self.uy + rip_perp * self.py) * env,
        )
        s2 = bilinear_sample(
            src,
            self.xx_rel + (d2 * self.ux + rip_perp * self.px) * env,
            self.yy_rel + (d2 * self.uy + rip_perp * self.py) * env,
        )
        flowed = s1 * w1 + s2 * w2

        if self.foam_shimmer > 0.0:
            luma = (0.299 * flowed[..., 0] + 0.587 * flowed[..., 1] + 0.114 * flowed[..., 2]) / 255.0
            crest = np.maximum(np.sin(0.18 * self.s_along + 0.09 * self.s_perp - 2.0 * tau), 0.0)
            foam = crest * np.clip((luma - 0.35) / 0.55, 0.0, 1.0) * env * (18.0 * self.foam_shimmer)
            flowed = np.clip(flowed + foam[..., None], 0.0, 255.0)

        if self.mist_env is not None:
            plume = 0.65 + 0.35 * np.sin(0.06 * self.s_perp - 0.08 * self.s_along + tau)
            m_alpha = np.clip(self.mist_env * plume * (0.32 * self.mist), 0.0, 0.45)[..., None]
            flowed = flowed * (1.0 - m_alpha) + 245.0 * m_alpha

        out = frame.copy()
        out[self.y0:self.y1, self.x0:self.x1] = sub * (1.0 - self.m_sub) + flowed * self.m_sub
        return out


VALID_ANCHOR_SIDES = {"left", "right", "top", "bottom"}


class FlagClothWaveEffect(MotionEffect):
    """Anchored flag, banner, curtain, or cape wave with zero-motion pole edge and 3D fold shading."""

    def __init__(self, base_rgb: np.ndarray, cfg: dict[str, Any]):
        h, w, _ = base_rgb.shape
        self.anchor_side = cfg.get("anchor_side", "left")
        if self.anchor_side not in VALID_ANCHOR_SIDES:
            raise ValueError(f"Unsupported flag_cloth_wave anchor_side: {self.anchor_side}")

        polys, rects, exc_polys, exc_rects = _normalize_region_args(cfg)
        self.mask = build_region_mask(
            base_rgb,
            polygons=polys,
            rects=rects,
            exclude_polygons=exc_polys,
            exclude_rects=exc_rects,
            edge_snap=cfg.get("edge_snap", True),
            snap_radius=float(cfg.get("snap_radius", 0.025)),
            feather_px=float(cfg.get("feather_px", 2.0)),
        )
        ys, xs = np.where(self.mask > 0.01)
        if len(ys) == 0:
            self.active = False
            return
        self.active = True

        self.y0 = max(0, int(ys.min()) - 6)
        self.y1 = min(h, int(ys.max()) + 6)
        self.x0 = max(0, int(xs.min()) - 6)
        self.x1 = min(w, int(xs.max()) + 6)
        sub_h, sub_w = self.y1 - self.y0, self.x1 - self.x0

        yy, xx = np.mgrid[0:sub_h, 0:sub_w].astype(np.float32)
        self.xx_rel = xx
        self.yy_rel = yy
        mask_crop = self.mask[self.y0:self.y1, self.x0:self.x1]
        active = mask_crop > 0.20

        if self.anchor_side in ("left", "right"):
            row_has = np.any(active, axis=1)
            first_x = np.argmax(active, axis=1).astype(np.float32)
            last_x = (sub_w - 1 - np.argmax(active[:, ::-1], axis=1)).astype(np.float32)
            first_x = np.where(row_has, first_x, 0.0)
            last_x = np.where(row_has, last_x, float(sub_w - 1))
            span = np.maximum(last_x - first_x, 8.0)[:, None]
            if self.anchor_side == "left":
                s_along = np.maximum(xx - first_x[:, None], 0.0)
                self.tx, self.ty = 0.18, 1.0
            else:
                s_along = np.maximum(last_x[:, None] - xx, 0.0)
                self.tx, self.ty = -0.18, 1.0
            t_span = np.clip(s_along / span, 0.0, 1.0)
            s_cross = yy
        else:
            col_has = np.any(active, axis=0)
            first_y = np.argmax(active, axis=0).astype(np.float32)
            last_y = (sub_h - 1 - np.argmax(active[::-1, :], axis=0)).astype(np.float32)
            first_y = np.where(col_has, first_y, 0.0)
            last_y = np.where(col_has, last_y, float(sub_h - 1))
            span = np.maximum(last_y - first_y, 8.0)[None, :]
            if self.anchor_side == "top":
                s_along = np.maximum(yy - first_y[None, :], 0.0)
                self.tx, self.ty = 1.0, 0.18
            else:
                s_along = np.maximum(last_y[None, :] - yy, 0.0)
                self.tx, self.ty = 1.0, -0.18
            t_span = np.clip(s_along / span, 0.0, 1.0)
            s_cross = xx

        self.s_along = s_along
        self.s_cross = s_cross
        self.anchor_env = np.power(t_span, 1.15) * mask_crop
        self.amp = float(cfg.get("amplitude", 3.2)) * (min(w, h) / 772.0)
        wl_frac = float(np.clip(cfg.get("wavelength", 0.55), 0.15, 2.0))
        wavelength_px = max(14.0, wl_frac * max(sub_w, sub_h))
        self.k = 2.0 * math.pi / wavelength_px
        self.shade = float(np.clip(cfg.get("shade", 0.65), 0.0, 1.5))
        self.speed = max(1, int(round(float(cfg.get("speed", 1.0)))))

        pad_px = max(5, int(math.ceil(abs(self.amp) * 1.8)) + 3)
        self.ext_cloth = extend_masked_pixels(base_rgb[self.y0:self.y1, self.x0:self.x1], mask_crop, pad_px)
        self.valid_sub = (mask_crop > 0.05)[..., None]
        self.m_sub = mask_crop[..., None]

    def apply(self, frame: np.ndarray, u: float, duration: float) -> np.ndarray:
        if not self.active:
            return frame
        tau = 2.0 * math.pi * u * self.speed
        phase1 = self.k * self.s_along + 0.28 * self.k * self.s_cross - tau
        phase2 = 1.85 * self.k * self.s_along - 0.35 * self.k * self.s_cross - 2.0 * tau + 1.1
        wave = 0.74 * np.sin(phase1) + 0.26 * np.sin(phase2)
        slope = 0.74 * np.cos(phase1) + 0.35 * np.cos(phase2)

        disp = self.amp * self.anchor_env * wave
        dx = disp * self.tx
        dy = disp * self.ty

        sub = frame[self.y0:self.y1, self.x0:self.x1]
        src = np.where(self.valid_sub, sub, self.ext_cloth)
        sampled = bilinear_sample(src, self.xx_rel - dx, self.yy_rel - dy)

        if self.shade > 0.0:
            shade_delta = slope * self.anchor_env * (18.0 * self.shade)
            sampled = np.clip(sampled + shade_delta[..., None], 0.0, 255.0)

        out = frame.copy()
        out[self.y0:self.y1, self.x0:self.x1] = sub * (1.0 - self.m_sub) + sampled * self.m_sub
        return out


class RotatePartEffect(MotionEffect):
    """Smooth seamless rotation for windmills, fans, Ferris wheels, or discs."""

    def __init__(self, base_rgb: np.ndarray, cfg: dict[str, Any]):
        h, w, _ = base_rgb.shape
        cx_n, cy_n = cfg.get("center", [0.5, 0.5])
        self.cx = float(cx_n) * w
        self.cy = float(cy_n) * h
        self.radius = float(cfg.get("radius", 0.08)) * min(w, h)
        self.turns = float(cfg.get("turns", 0.25))  # 0.25 loops cleanly for 4-blade windmills
        self.direction = 1.0 if float(cfg.get("direction", 1.0)) >= 0 else -1.0
        self.mode = cfg.get("mode", "blades")
        self.blade_tone = cfg.get("blade_tone", "bright")  # bright | dark | any

        r_pad = int(math.ceil(self.radius)) + 8
        self.x0 = max(0, int(math.floor(self.cx)) - r_pad)
        self.y0 = max(0, int(math.floor(self.cy)) - r_pad)
        self.x1 = min(w, int(math.ceil(self.cx)) + r_pad)
        self.y1 = min(h, int(math.ceil(self.cy)) + r_pad)

        patch = base_rgb[self.y0:self.y1, self.x0:self.x1].copy()
        yy, xx = np.mgrid[self.y0:self.y1, self.x0:self.x1].astype(np.float32)
        self.dx = xx - self.cx
        self.dy = yy - self.cy
        rr = np.sqrt(self.dx * self.dx + self.dy * self.dy)

        _, _, excl_polygons, excl_rects = _normalize_region_args(cfg)
        if excl_polygons or excl_rects:
            raw_exc = np.array(
                rasterize_polygons(w, h, polygons=excl_polygons, rects=excl_rects),
                dtype=np.float32,
            ) / 255.0
            if np.any(raw_exc[self.y0:self.y1, self.x0:self.x1] > 0.01):
                excl_mask = build_region_mask(
                    base_rgb,
                    polygons=excl_polygons,
                    rects=excl_rects,
                    edge_snap=cfg.get("edge_snap", True),
                    snap_radius=float(cfg.get("snap_radius", 0.02)),
                    feather_px=0.5,
                )
                excl_mask = np.where(raw_exc > 0.5, 1.0, excl_mask)
                self.allow_sub = np.clip(1.0 - excl_mask[self.y0:self.y1, self.x0:self.x1], 0.0, 1.0)
            else:
                self.allow_sub = np.ones((self.y1 - self.y0, self.x1 - self.x0), dtype=np.float32)
        else:
            self.allow_sub = np.ones((self.y1 - self.y0, self.x1 - self.x0), dtype=np.float32)

        cutoff_mask = np.ones_like(self.allow_sub)
        if "max_y" in cfg:
            cutoff = float(cfg["max_y"]) * h
            cutoff_mask = np.clip((cutoff - yy) / 4.0, 0.0, 1.0)
        self.dest_allow = self.allow_sub * cutoff_mask

        # Radial soft falloff near rim (keep unoccluded full circle before symmetric completion)
        disc_mask = np.clip((self.radius - rr) / max(self.radius * 0.16, 2.0), 0.0, 1.0)
        self.disc_mask = disc_mask * self.dest_allow

        if self.mode == "disc":
            self.clean_bg = patch
            if np.any(self.dest_allow < 0.99):
                pad_px = max(6, int(math.ceil(self.radius * 0.35)))
                self.fg_rgb = extend_masked_pixels(patch, self.dest_allow, pad_px, threshold=0.5)
            else:
                self.fg_rgb = patch
            self.fg_alpha = disc_mask
        else:
            # Median filter removes thin spinning blades into local sky/hill background
            k_med = max(7, int(round(self.radius * 0.28)) | 1)
            bg_img = Image.fromarray(np.clip(patch, 0, 255).astype(np.uint8)).filter(
                ImageFilter.MedianFilter(size=k_med)
            )
            bg = np.array(bg_img, dtype=np.float32)

            diff_vec = patch - bg
            luma_diff = 0.299 * diff_vec[..., 0] + 0.587 * diff_vec[..., 1] + 0.114 * diff_vec[..., 2]
            dist = np.sqrt(np.sum(diff_vec * diff_vec, axis=-1))

            if self.blade_tone == "bright":
                score = np.maximum(luma_diff, 0.0) * 0.7 + np.where(luma_diff > 4.0, dist * 0.5, 0.0)
            elif self.blade_tone == "dark":
                score = np.maximum(-luma_diff, 0.0) * 0.7 + np.where(luma_diff < -4.0, dist * 0.5, 0.0)
            else:
                score = dist

            valid_ring = (rr < self.radius * 0.9) & (self.dest_allow > 0.5)
            inner_scores = score[valid_ring] if np.any(valid_ring) else score[rr < self.radius * 0.9]
            noise_floor = float(np.percentile(inner_scores, 35)) if len(inner_scores) else 9.0
            low_t = max(14.0, min(noise_floor * 1.6, 24.0))
            high_t = max(low_t + 14.0, min(low_t * 2.1, 42.0))
            raw_alpha = np.clip((score - low_t) / (high_t - low_t), 0.0, 1.0) * disc_mask

            hub = np.clip((self.radius * 0.12 - rr) / 2.0, 0.0, 1.0)
            raw_alpha = np.maximum(raw_alpha, hub * 0.9) * (self.dest_allow > 0.5)

            # Dilate 1px strictly in destination-allowed area for ghost-free background erase
            erase_u8 = (np.clip(raw_alpha, 0.0, 1.0) * 255.0).astype(np.uint8)
            erase_dil = np.array(Image.fromarray(erase_u8).filter(ImageFilter.MaxFilter(3)), dtype=np.float32) / 255.0
            self.bg_erase_alpha = (erase_dil * self.dest_allow)[..., None]
            self.clean_bg = bg

            # Reconstruct blades hidden behind tower (max_y) or static_regions using 180/+90/-90 symmetry
            fg_alpha = raw_alpha.copy()
            fg_rgb = patch.copy()
            filled = self.dest_allow >= 0.85
            if not np.all(filled):
                rel_cx = self.cx - self.x0
                rel_cy = self.cy - self.y0
                for cdx, cdy in ((-self.dx, -self.dy), (-self.dy, self.dx), (self.dy, -self.dx)):
                    need = (~filled) & (disc_mask > 0.01)
                    if not np.any(need):
                        break
                    csx = rel_cx + cdx
                    csy = rel_cy + cdy
                    cand_allow = bilinear_sample(self.dest_allow[..., None], csx, csy)[..., 0]
                    take = need & (cand_allow >= 0.85)
                    if np.any(take):
                        cand_a = bilinear_sample(raw_alpha[..., None], csx, csy)[..., 0]
                        cand_rgb = bilinear_sample(patch, csx, csy)
                        fg_alpha[take] = cand_a[take]
                        fg_rgb[take] = cand_rgb[take]
                        filled[take] = True

            self.fg_rgb = fg_rgb
            self.fg_alpha = fg_alpha

    def apply(self, frame: np.ndarray, u: float, duration: float) -> np.ndarray:
        theta = self.direction * 2.0 * math.pi * self.turns * u
        cos_t = math.cos(-theta)
        sin_t = math.sin(-theta)

        sx = (self.dx * cos_t - self.dy * sin_t) + (self.cx - self.x0)
        sy = (self.dx * sin_t + self.dy * cos_t) + (self.cy - self.y0)

        rot_rgb = bilinear_sample(self.fg_rgb, sx, sy)
        rot_a = bilinear_sample(self.fg_alpha[..., None], sx, sy)[..., 0:1] * self.dest_allow[..., None]

        out = frame.copy()
        if self.mode == "disc":
            a = self.disc_mask[..., None]
            out[self.y0:self.y1, self.x0:self.x1] = (
                frame[self.y0:self.y1, self.x0:self.x1] * (1.0 - a) + rot_rgb * a
            )
        else:
            # Blend cleaned background only where unobstructed blades existed, then draw blades behind locked objects
            bg_blend = (
                frame[self.y0:self.y1, self.x0:self.x1] * (1.0 - self.bg_erase_alpha)
                + self.clean_bg * self.bg_erase_alpha
            )
            out[self.y0:self.y1, self.x0:self.x1] = bg_blend * (1.0 - rot_a) + rot_rgb * rot_a
        return out


class DepthParallaxEffect(MotionEffect):
    """Gentle 3%-5% 2.5D spatial camera push/orbit from synthetic depth or external depth_map."""

    def __init__(self, base_rgb: np.ndarray, cfg: dict[str, Any]):
        h, w, _ = base_rgb.shape
        depth_path = cfg.get("depth_map")
        if depth_path:
            d_img = Image.open(depth_path).convert("L").resize((w, h), Image.Resampling.BILINEAR)
            self.depth = np.array(d_img, dtype=np.float32) / 255.0
            if cfg.get("invert_depth", False):
                self.depth = 1.0 - self.depth
        else:
            self.depth = build_synthetic_depth(
                base_rgb,
                horizon_y=float(cfg.get("horizon_y", 0.55)),
                sky_depth=float(cfg.get("sky_depth", 0.05)),
                horizon_depth=float(cfg.get("horizon_depth", 0.25)),
                bottom_depth=float(cfg.get("bottom_depth", 0.92)),
                foreground_regions=cfg.get("foreground_regions", ()),
                edge_snap=cfg.get("edge_snap", True),
            )

        self.strength = float(np.clip(cfg.get("strength", 0.04), 0.0, 0.12))
        self.mode = cfg.get("mode", "loop")  # loop | push | orbit
        default_sway = 0.006 if self.mode == "orbit" else 0.0
        self.sway_x = float(np.clip(cfg.get("sway_x", default_sway), 0.0, 0.03))
        self.center_offset = max(abs(float(cfg.get("center_x", 0.5)) - 0.5), abs(float(cfg.get("center_y", 0.55)) - 0.5))
        self.center_x = float(cfg.get("center_x", 0.5)) * w
        self.center_y = float(cfg.get("center_y", 0.55)) * h
        self.yy, self.xx = np.mgrid[0:h, 0:w].astype(np.float32)
        self.w = float(w)

    def apply(self, frame: np.ndarray, u: float, duration: float) -> np.ndarray:
        tau = 2.0 * math.pi * u
        if self.mode == "push":
            # Smooth ease-in-out monotonic push
            p = 0.5 * (1.0 - math.cos(math.pi * u))
            pan = 0.0
        elif self.mode == "orbit":
            p = 0.5 * (1.0 - math.cos(tau))
            pan = math.sin(tau) * self.sway_x * self.w
        else:  # "loop": breathing dolly-in/out + micro parallax sway
            p = 0.5 * (1.0 - math.cos(tau))
            pan = math.sin(tau) * (self.sway_x * 0.5) * self.w

        # Keep scale >= 1 + full orbit/offset margin so sampling never crosses image boundary
        base_pad = 1.0 + self.sway_x * (2.2 + 2.0 * self.center_offset)
        scale = base_pad + p * self.strength * (0.20 + 0.95 * self.depth)
        sx = self.center_x + (self.xx - self.center_x) / scale + pan * (0.15 + 0.85 * self.depth)
        sy = self.center_y + (self.yy - self.center_y) / scale
        return bilinear_sample(frame, sx, sy)


VALID_OVERLAY_KINDS = {"steam", "sun_motes", "warm_glow", "sunbeam", "rain", "snow"}


class OverlayFxEffect(MotionEffect):
    """Seamless procedural overlays: steam, sun_motes, warm_glow, sunbeam, rain, snow."""

    def __init__(self, base_rgb: np.ndarray, cfg: dict[str, Any]):
        self.h, self.w, _ = base_rgb.shape
        self.kind = cfg.get("kind", "sun_motes")
        if self.kind not in VALID_OVERLAY_KINDS:
            raise ValueError(f"Unsupported overlay_fx kind: {self.kind}")
        self.opacity = float(cfg.get("opacity", 0.55))
        self.yy, self.xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)

        polys, rects, exc_polys, exc_rects = _normalize_region_args(cfg)
        if polys or rects:
            allow = build_region_mask(
                base_rgb,
                polygons=polys,
                rects=rects,
                exclude_polygons=exc_polys,
                exclude_rects=exc_rects,
                edge_snap=cfg.get("edge_snap", False),
                feather_px=float(cfg.get("feather_px", 2.0)),
            )
            self.allow_mask: np.ndarray | None = allow[..., None]
        elif exc_polys or exc_rects:
            exc_img = rasterize_polygons(self.w, self.h, polygons=exc_polys, rects=exc_rects)
            feather_r = float(cfg.get("feather_px", 2.5))
            if feather_r > 0.2:
                exc_img = exc_img.filter(ImageFilter.GaussianBlur(radius=feather_r))
            exc_raw = np.array(exc_img, dtype=np.float32) / 255.0
            self.allow_mask = np.clip(1.0 - exc_raw, 0.0, 1.0)[..., None]
        else:
            self.allow_mask = None

        if self.kind == "steam":
            self.anchors = cfg.get("anchors", [cfg.get("anchor", [0.5, 0.6])])
            self.scale = float(cfg.get("scale", 1.0)) * (min(self.w, self.h) / 720.0)
        elif self.kind == "warm_glow":
            self.anchors = cfg.get("anchors", [cfg.get("anchor", [0.5, 0.3])])
            self.radius = float(cfg.get("radius", 0.14)) * min(self.w, self.h)
        elif self.kind == "sun_motes":
            rng = np.random.default_rng(int(cfg.get("seed", 42)))
            count = int(cfg.get("count", 22))
            self.motes = [
                (
                    float(rng.uniform(0.05, 0.95) * self.w),
                    float(rng.uniform(0.05, 0.88) * self.h),
                    float(rng.uniform(6.0, 22.0) * (min(self.w, self.h) / 720.0)),
                    float(rng.uniform(8.0, 26.0) * (min(self.w, self.h) / 720.0)),
                    float(rng.uniform(0.0, 2.0 * math.pi)),
                    int(rng.integers(1, 3)),
                    float(rng.uniform(0.35, 1.0)),
                )
                for _ in range(count)
            ]
        elif self.kind in ("rain", "snow"):
            rng = np.random.default_rng(int(cfg.get("seed", 7)))
            count = int(cfg.get("count", 70 if self.kind == "rain" else 48))
            self.particles = [
                (
                    float(rng.uniform(0.0, 1.0) * self.w),
                    float(rng.uniform(0.0, 1.0) * self.h),
                    float(rng.uniform(1.5, 4.5) * (min(self.w, self.h) / 720.0)),
                    int(rng.integers(1, 4)),
                    float(rng.uniform(0.0, 2.0 * math.pi)),
                    float(rng.uniform(0.0, 1.0)),
                )
                for _ in range(count)
            ]

    def apply(self, frame: np.ndarray, u: float, duration: float) -> np.ndarray:
        tau = 2.0 * math.pi * u
        out = frame.copy()

        if self.kind == "sun_motes":
            glow = np.zeros((self.h, self.w), dtype=np.float32)
            for bx, by, rad, drift, phase, cyc, bright in self.motes:
                cx = bx + drift * math.sin(cyc * tau + phase)
                cy = by + (drift * 0.65) * math.cos(cyc * tau + phase * 1.3)
                pulse = 0.55 + 0.45 * math.sin(tau + phase)
                x0 = max(0, int(cx - rad * 2.2))
                x1 = min(self.w, int(cx + rad * 2.2) + 1)
                y0 = max(0, int(cy - rad * 2.2))
                y1 = min(self.h, int(cy + rad * 2.2) + 1)
                if x1 <= x0 or y1 <= y0:
                    continue
                d2 = (self.xx[y0:y1, x0:x1] - cx) ** 2 + (self.yy[y0:y1, x0:x1] - cy) ** 2
                orb = np.exp(-d2 / (2.0 * (rad * 0.55) ** 2)) * bright * pulse
                glow[y0:y1, x0:x1] += orb
            color = np.array([255.0, 240.0, 200.0], dtype=np.float32)
            alpha = np.clip(glow * (0.28 * self.opacity), 0.0, 0.5)[..., None]
            if self.allow_mask is not None:
                alpha *= self.allow_mask
            out = np.clip(out + color * alpha, 0.0, 255.0)

        elif self.kind == "steam":
            steam = np.zeros((self.h, self.w), dtype=np.float32)
            for ax_n, ay_n in self.anchors:
                ax, ay = float(ax_n) * self.w, float(ay_n) * self.h
                plume_h = 150.0 * self.scale
                plume_w = 52.0 * self.scale
                y0 = max(0, int(ay - plume_h))
                y1 = min(self.h, int(ay + 12 * self.scale))
                x0 = max(0, int(ax - plume_w * 2.2))
                x1 = min(self.w, int(ax + plume_w * 2.2))
                if x1 <= x0 or y1 <= y0:
                    continue
                yy_s = self.yy[y0:y1, x0:x1]
                xx_s = self.xx[y0:y1, x0:x1]
                rise = np.clip((ay - yy_s) / plume_h, 0.0, 1.0)
                env_y = np.sin(math.pi * np.power(rise, 0.7)) * (yy_s <= ay)
                spread = plume_w * (0.45 + 0.9 * rise)
                wobble = 14.0 * self.scale * np.sin(rise * 5.2 + tau)
                env_x = np.exp(-((xx_s - (ax + wobble)) ** 2) / (2.0 * spread ** 2))
                curl = (
                    0.5
                    + 0.3 * np.sin(0.07 * (xx_s - ax) + 0.055 * (yy_s - ay) + 2.0 * tau)
                    + 0.2 * np.cos(-0.09 * (xx_s - ax) + 0.08 * (yy_s - ay) + 3.0 * tau)
                )
                steam[y0:y1, x0:x1] += env_y * env_x * np.clip(curl, 0.0, 1.0)
            alpha = np.clip(steam * (0.42 * self.opacity), 0.0, 0.65)[..., None]
            if self.allow_mask is not None:
                alpha *= self.allow_mask
            out = out * (1.0 - alpha) + 245.0 * alpha

        elif self.kind == "warm_glow":
            glow = np.zeros((self.h, self.w), dtype=np.float32)
            reach = self.radius * 2.2
            denom = 2.0 * (self.radius * 0.5) ** 2
            for idx, (ax_n, ay_n) in enumerate(self.anchors):
                ax, ay = float(ax_n) * self.w, float(ay_n) * self.h
                pulse = 0.72 + 0.28 * math.sin(2.0 * tau + idx * 1.7)
                x0 = max(0, int(ax - reach))
                x1 = min(self.w, int(ax + reach) + 1)
                y0 = max(0, int(ay - reach))
                y1 = min(self.h, int(ay + reach) + 1)
                if x1 <= x0 or y1 <= y0:
                    continue
                d2 = (self.xx[y0:y1, x0:x1] - ax) ** 2 + (self.yy[y0:y1, x0:x1] - ay) ** 2
                glow[y0:y1, x0:x1] += np.exp(-d2 / denom) * pulse
            color = np.array([255.0, 210.0, 130.0], dtype=np.float32)
            alpha = np.clip(glow * (0.24 * self.opacity), 0.0, 0.4)[..., None]
            if self.allow_mask is not None:
                alpha *= self.allow_mask
            out = np.clip(out + color * alpha, 0.0, 255.0)

        elif self.kind == "sunbeam":
            ang = (self.xx / self.w) * 0.8 + (self.yy / self.h) * 0.5
            beams = np.power(0.5 + 0.5 * np.sin(ang * 14.0 + 0.4 * math.sin(tau)), 3.0)
            fade = np.clip(1.0 - self.yy / (self.h * 0.85), 0.0, 1.0) * np.clip(1.0 - self.xx / (self.w * 1.1), 0.0, 1.0)
            pulse = 0.7 + 0.3 * math.sin(tau)
            alpha = (beams * fade * pulse * 0.16 * self.opacity)[..., None]
            if self.allow_mask is not None:
                alpha *= self.allow_mask
            out = np.clip(out + np.array([255.0, 242.0, 210.0], dtype=np.float32) * alpha, 0.0, 255.0)

        elif self.kind == "snow":
            snow = np.zeros((self.h, self.w), dtype=np.float32)
            for bx, by, rad, cyc, phase, _ in self.particles:
                cy_base = (by + u * cyc * self.h) % self.h
                cx_base = (bx + 18.0 * math.sin(tau + phase)) % self.w
                r_box = rad * 2.0
                for cy in (cy_base, cy_base - self.h, cy_base + self.h):
                    if cy + r_box < 0 or cy - r_box >= self.h:
                        continue
                    x0, x1 = max(0, int(cx_base - r_box)), min(self.w, int(cx_base + r_box) + 1)
                    y0, y1 = max(0, int(cy - r_box)), min(self.h, int(cy + r_box) + 1)
                    if x1 <= x0 or y1 <= y0:
                        continue
                    d2 = (self.xx[y0:y1, x0:x1] - cx_base) ** 2 + (self.yy[y0:y1, x0:x1] - cy) ** 2
                    snow[y0:y1, x0:x1] += np.exp(-d2 / (2.0 * (rad * 0.6) ** 2))
            alpha = np.clip(snow * (0.75 * self.opacity), 0.0, 0.85)[..., None]
            if self.allow_mask is not None:
                alpha *= self.allow_mask
            out = out * (1.0 - alpha) + 250.0 * alpha

        elif self.kind == "rain":
            rain = np.zeros((self.h, self.w), dtype=np.float32)
            streak_len = max(14.0, self.h * 0.035)
            slant = 0.08
            pad_left = streak_len * slant + 4.0
            for bx, by, _, cyc, _, phase_norm in self.particles:
                # Cycle along slanted fall with smooth fade-in/out so u=1.0 wraps seamlessly to u=0.0
                t_life = (u * cyc + phase_norm) % 1.0
                life_fade = min(1.0, t_life / 0.12, (1.0 - t_life) / 0.12)
                if life_fade <= 0.0:
                    continue
                cy_base = (by + t_life * self.h) % self.h
                cx_base = (bx + t_life * self.h * slant) % self.w
                for cy in (cy_base, cy_base - self.h, cy_base + self.h):
                    if cy + 2 < 0 or cy - streak_len >= self.h:
                        continue
                    x0 = max(0, int(cx_base - pad_left))
                    x1 = min(self.w, int(cx_base + 5))
                    y0 = max(0, int(cy - streak_len))
                    y1 = min(self.h, int(cy + 2))
                    if x1 <= x0 or y1 <= y0:
                        continue
                    yy_s = self.yy[y0:y1, x0:x1]
                    xx_s = self.xx[y0:y1, x0:x1]
                    line_x = cx_base - (cy - yy_s) * slant
                    dist_x = np.abs(xx_s - line_x)
                    tail_t = np.clip((yy_s - (cy - streak_len)) / streak_len, 0.0, 1.0)
                    rain[y0:y1, x0:x1] += life_fade * np.exp(-(dist_x ** 2) / 1.5) * tail_t
            alpha = np.clip(rain * (0.45 * self.opacity), 0.0, 0.6)[..., None]
            if self.allow_mask is not None:
                alpha *= self.allow_mask
            out = np.clip(out + 225.0 * alpha, 0.0, 255.0)

        return out


EFFECT_FACTORIES = {
    "water_ripple": WaterRippleEffect,
    "waterfall_flow": WaterfallFlowEffect,
    "sky_drift": SkyDriftEffect,
    "foliage_sway": FoliageSwayEffect,
    "flag_cloth_wave": FlagClothWaveEffect,
    "rotate_part": RotatePartEffect,
    "depth_parallax": DepthParallaxEffect,
    "overlay_fx": OverlayFxEffect,
}


def collect_static_regions(regions_cfg: Any) -> tuple[list, list, list, list]:
    """Extract (static_polys, static_rects, camera_lock_polys, camera_lock_rects) from static_regions."""
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


def build_effect_pipeline(
    base_rgb: np.ndarray,
    effects_cfg: list[dict[str, Any]],
    static_regions: Any = None,
) -> list[MotionEffect]:
    """Instantiate effects ordered cleanly: local surface -> camera 2.5D -> atmospheric overlays."""
    static_polys, static_rects, lock_polys, lock_rects = collect_static_regions(static_regions)
    warp_protected = {
        "water_ripple",
        "waterfall_flow",
        "sky_drift",
        "foliage_sway",
        "flag_cloth_wave",
        "rotate_part",
    }

    prepared_cfg: list[dict[str, Any]] = []
    for raw in effects_cfg:
        cfg = dict(raw)
        etype = cfg.get("type")
        if etype in warp_protected and (static_polys or static_rects):
            if static_polys:
                cfg["exclude_polygons"] = list(cfg.get("exclude_polygons", ())) + static_polys
            if static_rects:
                cfg["exclude_rects"] = list(cfg.get("exclude_rects", ())) + static_rects
        elif etype == "overlay_fx":
            if cfg.get("respect_static_regions", False) and (static_polys or static_rects):
                if static_polys:
                    cfg["exclude_polygons"] = list(cfg.get("exclude_polygons", ())) + static_polys
                if static_rects:
                    cfg["exclude_rects"] = list(cfg.get("exclude_rects", ())) + static_rects
            elif not cfg.get("ignore_static_regions", False) and (lock_polys or lock_rects):
                if lock_polys:
                    cfg["exclude_polygons"] = list(cfg.get("exclude_polygons", ())) + lock_polys
                if lock_rects:
                    cfg["exclude_rects"] = list(cfg.get("exclude_rects", ())) + lock_rects
        prepared_cfg.append(cfg)

    order_rank = {
        "sky_drift": 1,
        "foliage_sway": 2,
        "flag_cloth_wave": 2,
        "water_ripple": 3,
        "waterfall_flow": 3,
        "rotate_part": 4,
        "depth_parallax": 5,
        "overlay_fx": 6,
    }
    sorted_cfg = sorted(prepared_cfg, key=lambda c: order_rank.get(c.get("type", ""), 9))
    pipeline: list[MotionEffect] = []
    for cfg in sorted_cfg:
        etype = cfg.get("type")
        if etype not in EFFECT_FACTORIES:
            raise ValueError(f"Unsupported motion effect type: {etype}")
        pipeline.append(EFFECT_FACTORIES[etype](base_rgb, cfg))
    return pipeline
