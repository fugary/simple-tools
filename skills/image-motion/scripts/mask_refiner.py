"""Mask rasterization, edge-aware boundary snapping, and depth-field helpers."""
from __future__ import annotations

from typing import Iterable, Sequence
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _clamp_even_odd(val: int) -> int:
    return val if val % 2 == 1 else val + 1


def _to_pixel_poly(poly: Sequence[Sequence[float]], w: int, h: int) -> list[tuple[float, float]]:
    return [(float(x) * w, float(y) * h) for x, y in poly]


def _to_pixel_rect(rect: Sequence[float], w: int, h: int) -> list[float]:
    rx1, ry1, rx2, ry2 = rect
    x0, x1 = sorted((float(rx1) * w, float(rx2) * w))
    y0, y1 = sorted((float(ry1) * h, float(ry2) * h))
    return [x0, y0, x1, y1]


def _normalize_polygons(polygons: Iterable) -> list[Sequence[Sequence[float]]]:
    polys = list(polygons or ())
    if (
        polys
        and isinstance(polys[0], (list, tuple))
        and len(polys[0]) == 2
        and isinstance(polys[0][0], (int, float))
    ):
        # Gracefully accept a single flat polygon [[x, y], ...] passed to polygons
        return [polys]
    return polys


def rasterize_polygons(
    w: int,
    h: int,
    polygons: Iterable[Sequence[Sequence[float]]] = (),
    rects: Iterable[Sequence[float]] = (),
) -> Image.Image:
    """Rasterize normalized polygons/rects in [0..1] into an L-mode mask image."""
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for poly in _normalize_polygons(polygons):
        if len(poly) >= 3:
            draw.polygon(_to_pixel_poly(poly, w, h), fill=255)
    for rect in rects or ():
        if len(rect) == 4:
            draw.rectangle(_to_pixel_rect(rect, w, h), fill=255)
    return mask


def _edge_weights(img_rgb: np.ndarray, sigma_color: float) -> tuple[np.ndarray, np.ndarray]:
    inv_2s2 = 1.0 / (2.0 * max(sigma_color, 1.0) ** 2)
    diff_x = img_rgb[:, 1:, :] - img_rgb[:, :-1, :]
    diff_y = img_rgb[1:, :, :] - img_rgb[:-1, :, :]
    wx = np.exp(-np.sum(diff_x * diff_x, axis=-1) * inv_2s2).astype(np.float32)
    wy = np.exp(-np.sum(diff_y * diff_y, axis=-1) * inv_2s2).astype(np.float32)
    return wx, wy


def _solve_edge_diffusion(
    wx: np.ndarray,
    wy: np.ndarray,
    hard_one: np.ndarray,
    hard_zero: np.ndarray,
    init_mask: np.ndarray,
    iterations: int,
    omega: float = 1.65,
) -> np.ndarray:
    """Solve edge-stopped Laplace diffusion inside free = ~(hard_one | hard_zero) via Red-Black SOR."""
    h, w = hard_one.shape
    w_r = np.zeros((h, w), dtype=np.float32)
    w_l = np.zeros((h, w), dtype=np.float32)
    w_d = np.zeros((h, w), dtype=np.float32)
    w_u = np.zeros((h, w), dtype=np.float32)
    w_r[:, :-1] = wx
    w_l[:, 1:] = wx
    w_d[:-1, :] = wy
    w_u[1:, :] = wy
    w_sum = np.maximum(w_r + w_l + w_d + w_u, 1e-4)

    m = init_mask.copy()
    m[hard_one] = 1.0
    m[hard_zero] = 0.0
    free = (~hard_one) & (~hard_zero)

    yy, xx = np.ogrid[0:h, 0:w]
    red = ((yy + xx) & 1) == 0
    red_free = free & red
    blk_free = free & (~red)

    acc = np.zeros_like(m)
    for _ in range(iterations):
        acc.fill(0.0)
        acc[:, :-1] += w_r[:, :-1] * m[:, 1:]
        acc[:, 1:] += w_l[:, 1:] * m[:, :-1]
        acc[:-1, :] += w_d[:-1, :] * m[1:, :]
        acc[1:, :] += w_u[1:, :] * m[:-1, :]
        upd = acc / w_sum
        m[red_free] = np.clip((1.0 - omega) * m[red_free] + omega * upd[red_free], 0.0, 1.0)

        acc.fill(0.0)
        acc[:, :-1] += w_r[:, :-1] * m[:, 1:]
        acc[:, 1:] += w_l[:, 1:] * m[:, :-1]
        acc[:-1, :] += w_d[:-1, :] * m[1:, :]
        acc[1:, :] += w_u[1:, :] * m[:-1, :]
        upd = acc / w_sum
        m[blk_free] = np.clip((1.0 - omega) * m[blk_free] + omega * upd[blk_free], 0.0, 1.0)
    return m


def _run_edge_diffusion(
    img_rgb: np.ndarray,
    hard_one: np.ndarray,
    hard_zero: np.ndarray,
    init_mask: np.ndarray,
    sigma_color: float,
    iterations: int,
) -> np.ndarray:
    wx, wy = _edge_weights(img_rgb, sigma_color)
    return _solve_edge_diffusion(wx, wy, hard_one, hard_zero, init_mask, iterations)


def _quantile_rgb_centroids(pixels: np.ndarray) -> np.ndarray:
    """Compute 3 representative RGB centroids (dark/mid/bright luma quantiles) for a pixel set."""
    if len(pixels) == 0:
        return np.zeros((1, 3), dtype=np.float32)
    luma = 0.299 * pixels[:, 0] + 0.587 * pixels[:, 1] + 0.114 * pixels[:, 2]
    qs = np.percentile(luma, [20, 50, 80])
    centroids = []
    for q_lo, q_hi in ((0.0, qs[0] + 1.0), (qs[0] - 1.0, qs[2] + 1.0), (qs[2] - 1.0, 256.0)):
        sel = pixels[(luma >= q_lo) & (luma <= q_hi)]
        if len(sel) == 0:
            sel = pixels
        centroids.append(np.median(sel, axis=0))
    return np.asarray(centroids, dtype=np.float32)


def _min_rgb_dist(img_sub: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """Minimum Euclidean RGB distance from each pixel in img_sub to a small set of centroids."""
    diffs = img_sub[:, :, None, :] - centroids[None, None, :, :]
    dists = np.sqrt(np.sum(diffs * diffs, axis=-1))
    return np.min(dists, axis=-1)


def edge_aware_snap(
    img_rgb: np.ndarray,
    inc_img: Image.Image,
    exc_img: Image.Image | None = None,
    snap_radius: float = 0.025,
    sigma_color: float = 18.0,
    iterations: int = 36,
    feather_px: float = 2.0,
) -> np.ndarray:
    """Snap a coarse mask to actual image color edges via 2-level edge-stopped diffusion.

    Inside flat regions, mask values diffuse freely; across sharp RGB gradients
    (shorelines, people, buildings, boats), diffusion stops at the real boundary.
    Explicit exclusions remain strictly zero inside their contour.
    """
    h, w, _ = img_rgb.shape
    inc_arr = np.array(inc_img, dtype=np.float32) / 255.0
    if not np.any(inc_arr > 0.5):
        return np.zeros((h, w), dtype=np.float32)

    band_px = max(3, int(round(snap_radius * min(w, h))))
    # Full +/- band_px uncertainty zone so coarse polygons off by up to snap_radius still snap cleanly
    k_inc = _clamp_even_odd(max(3, band_px * 2 + 1))

    inner_core = np.array(inc_img.filter(ImageFilter.MinFilter(k_inc)), dtype=np.float32) > 127
    outer_limit = np.array(inc_img.filter(ImageFilter.MaxFilter(k_inc)), dtype=np.float32) > 127
    if not np.any(inner_core):
        # Fallback for very thin regions
        k_small = _clamp_even_odd(max(3, band_px))
        inner_core = np.array(inc_img.filter(ImageFilter.MinFilter(k_small)), dtype=np.float32) > 127
        if not np.any(inner_core):
            inner_core = inc_arr > 0.5

    if exc_img is not None:
        exc_arr = np.array(exc_img, dtype=np.float32) / 255.0
        has_exc = bool(np.any(exc_arr > 0.5))
    else:
        exc_arr = np.zeros((h, w), dtype=np.float32)
        has_exc = False

    if has_exc:
        # Free a generous band outside explicit exclusions so coarse static_regions chords snap outward to real edges
        k_exc_guard = _clamp_even_odd(max(5, int(round(band_px * 2.2)) | 1))
        exc_outer = np.array(exc_img.filter(ImageFilter.MaxFilter(k_exc_guard)), dtype=np.float32) > 127
        hard_one = inner_core & (~exc_outer)
        hard_zero = (~outer_limit) | (exc_arr > 0.5)
    else:
        hard_one = inner_core
        hard_zero = ~outer_limit

    if not np.any(hard_one):
        hard_one = (inc_arr > 0.5) & (exc_arr < 0.5)

    mask = np.clip(inc_arr * (1.0 - exc_arr), 0.0, 1.0).astype(np.float32)

    ys, xs = np.where(outer_limit)
    # Include a 4px pad outside outer_limit so border hard_zero pixels sit inside the solver domain
    y0 = max(0, int(ys.min()) - 4)
    y1 = min(h, int(ys.max()) + 5)
    x0 = max(0, int(xs.min()) - 4)
    x1 = min(w, int(xs.max()) + 5)
    sub_h, sub_w = y1 - y0, x1 - x0

    img_sub = img_rgb[y0:y1, x0:x1]
    h1_sub = hard_one[y0:y1, x0:x1].copy()
    h0_sub = hard_zero[y0:y1, x0:x1]

    # Prune protruding obstacle pixels (e.g. mountain peaks, llama ears, shore rocks) from h1_sub
    # when their color matches the exterior hard_zero border much closer than the deep interior core
    outlier_sub = np.zeros((sub_h, sub_w), dtype=bool)
    if np.any(h1_sub) and np.any(h0_sub):
        deep_erode = np.array(inc_img.filter(ImageFilter.MinFilter(_clamp_even_odd(band_px * 4 + 1))), dtype=np.float32) > 127
        deep_seed = deep_erode[y0:y1, x0:x1] & h1_sub
        if np.sum(deep_seed) < 64:
            deep_seed = h1_sub
        # If hard_zero lies predominantly on one vertical side (e.g. ground below sky), favor the opposite half of deep_seed
        ys_h1, _ = np.where(deep_seed)
        ys_h0, _ = np.where(h0_sub)
        if len(ys_h1) >= 64 and len(ys_h0) >= 16:
            if float(ys_h0.mean()) > float(ys_h1.mean()):
                y_cut = np.percentile(ys_h1, 55)
                top_half = deep_seed & (np.arange(sub_h)[:, None] <= y_cut)
                if np.sum(top_half) >= 32:
                    deep_seed = top_half
            elif float(ys_h0.mean()) < float(ys_h1.mean()):
                y_cut = np.percentile(ys_h1, 45)
                bot_half = deep_seed & (np.arange(sub_h)[:, None] >= y_cut)
                if np.sum(bot_half) >= 32:
                    deep_seed = bot_half

        core_centroids = _quantile_rgb_centroids(img_sub[deep_seed])
        zero_centroids = _quantile_rgb_centroids(img_sub[h0_sub])
        d_core = _min_rgb_dist(img_sub, core_centroids)
        d_zero = _min_rgb_dist(img_sub, zero_centroids)
        outlier_sub = (d_core > max(26.0, sigma_color * 1.25)) & (d_zero * 1.15 < d_core)
        pruned_h1 = h1_sub & (~outlier_sub)
        if np.sum(pruned_h1) >= max(24, int(0.15 * np.sum(h1_sub))):
            h1_sub = pruned_h1

    free_init = np.where(outlier_sub, 0.05, 0.5).astype(np.float32)
    init_sub = np.where(h1_sub, 1.0, np.where(h0_sub, 0.0, free_init)).astype(np.float32)

    wx_fine, wy_fine = _edge_weights(img_sub, sigma_color)

    # Edge-preserving 3x downsampled warm-start (boolean .any pooling preserves thin hard_zero borders)
    if sub_h >= 24 and sub_w >= 24 and band_px >= 6:
        ch = max(8, (sub_h + 2) // 3)
        cw = max(8, (sub_w + 2) // 3)
        pad_h = ch * 3 - sub_h
        pad_w = cw * 3 - sub_w

        wx_pad = np.pad(wx_fine, ((0, pad_h), (0, pad_w + 2)), mode="edge")
        wy_pad = np.pad(wy_fine, ((0, pad_h + 2), (0, pad_w)), mode="edge")
        wx_c = wx_pad[:ch * 3, 1:1 + 3 * (cw - 1)].reshape(ch, 3, cw - 1, 3).min(axis=(1, 3))
        wy_c = wy_pad[1:1 + 3 * (ch - 1), :cw * 3].reshape(ch - 1, 3, cw, 3).min(axis=(1, 3))

        h1_pad = np.pad(h1_sub, ((0, pad_h), (0, pad_w)), mode="edge")
        h0_pad = np.pad(h0_sub, ((0, pad_h), (0, pad_w)), mode="edge")
        out_pad = np.pad(outlier_sub, ((0, pad_h), (0, pad_w)), mode="edge")
        h1_c = h1_pad.reshape(ch, 3, cw, 3).any(axis=(1, 3))
        h0_c = h0_pad.reshape(ch, 3, cw, 3).any(axis=(1, 3))
        out_c = out_pad.reshape(ch, 3, cw, 3).all(axis=(1, 3))
        h1_c &= ~h0_c
        init_c = np.where(h1_c, 1.0, np.where(h0_c, 0.0, np.where(out_c, 0.05, 0.5))).astype(np.float32)
        m_c = _solve_edge_diffusion(wx_c, wy_c, h1_c, h0_c, init_c, iterations=max(60, band_px * 4))
        m_up = np.array(
            Image.fromarray((np.clip(m_c, 0, 1) * 255).astype(np.uint8)).resize((cw * 3, ch * 3), Image.Resampling.BILINEAR),
            dtype=np.float32,
        ) / 255.0
        init_sub = m_up[:sub_h, :sub_w]

    fine_iters = max(iterations, band_px * 4, 48)
    m_sub = _solve_edge_diffusion(wx_fine, wy_fine, h1_sub, h0_sub, init_sub, iterations=fine_iters)
    mask[y0:y1, x0:x1] = m_sub

    if feather_px > 0.2:
        blurred = np.array(
            Image.fromarray((np.clip(mask, 0.0, 1.0) * 255.0).astype(np.uint8)).filter(
                ImageFilter.GaussianBlur(radius=feather_px)
            ),
            dtype=np.float32,
        ) / 255.0
        # Feather strictly inward so edge-stopped zero boundaries never bleed onto rigid neighbors
        mask = np.where(hard_zero, 0.0, np.minimum(mask, blurred))
    return np.clip(mask, 0.0, 1.0)


def build_region_mask(
    img_rgb: np.ndarray,
    polygons: Iterable[Sequence[Sequence[float]]] = (),
    rects: Iterable[Sequence[float]] = (),
    exclude_polygons: Iterable[Sequence[Sequence[float]]] = (),
    exclude_rects: Iterable[Sequence[float]] = (),
    edge_snap: bool = True,
    snap_radius: float = 0.025,
    sigma_color: float = 22.0,
    feather_px: float = 2.0,
) -> np.ndarray:
    """Build a soft [0..1] mask from normalized polygons/rects, optionally snapping to image edges."""
    h, w, _ = img_rgb.shape
    inc_img = rasterize_polygons(w, h, polygons=polygons, rects=rects)
    has_exc = bool(exclude_polygons) or bool(exclude_rects)
    exc_img = rasterize_polygons(w, h, polygons=exclude_polygons, rects=exclude_rects) if has_exc else None

    if edge_snap:
        return edge_aware_snap(
            img_rgb,
            inc_img,
            exc_img,
            snap_radius=snap_radius,
            sigma_color=sigma_color,
            feather_px=feather_px,
        )

    inc_arr = np.array(inc_img, dtype=np.float32) / 255.0
    if exc_img is not None:
        exc_arr = np.array(exc_img, dtype=np.float32) / 255.0
        inc_arr = inc_arr * (1.0 - exc_arr)
    if feather_px > 0.2:
        blur = np.array(
            Image.fromarray((inc_arr * 255.0).astype(np.uint8)).filter(
                ImageFilter.GaussianBlur(radius=feather_px)
            ),
            dtype=np.float32,
        ) / 255.0
        return np.clip(np.minimum(inc_arr, blur), 0.0, 1.0)
    return np.clip(inc_arr, 0.0, 1.0)


def infer_shoreline_from_mask(mask: np.ndarray, threshold: float = 0.25) -> np.ndarray:
    """Infer smoothed upper contour y(x) of a water mask for perspective scaling."""
    h, w = mask.shape
    active = mask >= threshold
    col_has = np.any(active, axis=0)
    if not np.any(col_has):
        return np.full((1, w), h * 0.65, dtype=np.float32)

    first_y = np.argmax(active, axis=0).astype(np.float32)
    xs = np.arange(w, dtype=np.float32)
    y_interp = np.interp(xs, xs[col_has], first_y[col_has])

    # Suppress narrow downward notches caused by coastal rocks/boats along the shoreline
    win = max(5, (w // 30) | 1)
    half = win // 2
    padded_med = np.pad(y_interp, half, mode="edge")
    # Rolling 25th-percentile favors the true upper shore contour over occasional obstructions
    try:
        windows = np.lib.stride_tricks.sliding_window_view(padded_med, win)
        y_env = np.percentile(windows, 25, axis=-1).astype(np.float32)
    except AttributeError:
        y_env = y_interp

    k = max(5, (w // 40) | 1)
    pad = k // 2
    padded = np.pad(y_env, pad, mode="edge")
    kernel = np.ones(k, dtype=np.float32) / k
    smoothed = np.convolve(padded, kernel, mode="valid")
    return smoothed[None, :].astype(np.float32)


def build_synthetic_depth(
    img_rgb: np.ndarray,
    horizon_y: float = 0.55,
    sky_depth: float = 0.05,
    horizon_depth: float = 0.25,
    bottom_depth: float = 0.92,
    foreground_regions: Sequence[dict] = (),
    edge_snap: bool = True,
) -> np.ndarray:
    """Build a smooth [0..1] depth field from horizon tilt plus edge-snapped planar regions."""
    h, w, _ = img_rgb.shape
    y_norm = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]

    hy = float(np.clip(horizon_y, 0.05, 0.95))
    sky_t = np.clip(y_norm / hy, 0.0, 1.0)
    ground_t = np.clip((y_norm - hy) / max(1.0 - hy, 1e-4), 0.0, 1.0)

    depth = np.where(
        y_norm <= hy,
        sky_depth + (horizon_depth - sky_depth) * np.power(sky_t, 1.6),
        horizon_depth + (bottom_depth - horizon_depth) * np.power(ground_t, 0.85),
    )
    depth = np.broadcast_to(depth, (h, w)).copy()

    # Smooth continuous background ramp BEFORE compositing sharp-edged foreground/planar objects
    blur_r = max(4.0, min(w, h) * 0.008)
    depth_u8 = (np.clip(depth, 0.0, 1.0) * 255.0).astype(np.uint8)
    depth = (
        np.array(Image.fromarray(depth_u8).filter(ImageFilter.GaussianBlur(radius=blur_r)), dtype=np.float32)
        / 255.0
    )

    ordered_regs = sorted(foreground_regions or (), key=lambda r: float(r.get("depth", 0.92)))
    for reg in ordered_regs:
        fg_mask = build_region_mask(
            img_rgb,
            polygons=reg.get("polygons", ([reg["polygon"]] if "polygon" in reg else ())),
            rects=reg.get("rects", ([reg["rect"]] if "rect" in reg else ())),
            exclude_polygons=reg.get("exclude_polygons", ()),
            exclude_rects=reg.get("exclude_rects", ()),
            edge_snap=reg.get("edge_snap", edge_snap),
            snap_radius=float(reg.get("snap_radius", 0.025)),
            feather_px=float(reg.get("feather_px", 2.0)),
        )
        fg_val = float(np.clip(reg.get("depth", 0.92), 0.0, 1.0))
        depth = depth * (1.0 - fg_mask) + fg_val * fg_mask

    return np.clip(depth, 0.0, 1.0)
