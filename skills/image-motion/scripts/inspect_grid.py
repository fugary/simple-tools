#!/usr/bin/env python3
"""Overlay a 0.0-1.0 normalized coordinate grid on an image for visual inspection."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def _load_grid_font(px_size: int):
    try:
        return ImageFont.load_default(size=px_size)
    except TypeError:
        return ImageFont.load_default()


def draw_normalized_grid(image_path: Path, out_path: Path, step: float = 0.1, minor: float = 0.05) -> tuple[int, int]:
    """Save a copy of image_path with normalized [0..1] grid lines and coordinate labels."""
    if step <= 0 or step > 1.0:
        raise ValueError(f"step must be in (0, 1], got {step}")
    if minor < 0 or minor > 1.0:
        raise ValueError(f"minor must be in [0, 1], got {minor}")

    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    scale = max(1.0, max(w, h) / 1100.0)
    line_w = max(1, int(round(scale)))
    font = _load_grid_font(max(11, int(round(11 * scale))))
    pad = max(2, int(round(2 * scale)))

    # Minor grid lines
    if minor > 0:
        n_minor = int(round(1.0 / minor))
        for i in range(1, n_minor):
            t = i * minor
            if abs((t / step) - round(t / step)) < 1e-4:
                continue
            x = int(round(t * w))
            y = int(round(t * h))
            draw.line([(x, 0), (x, h)], fill=(255, 255, 255, 70), width=line_w)
            draw.line([(0, y), (w, y)], fill=(255, 255, 255, 70), width=line_w)

    # Major grid lines + labels
    n_major = int(round(1.0 / step))
    for i in range(1, n_major):
        t = i * step
        label = f"{t:.1f}"
        x = int(round(t * w))
        y = int(round(t * h))
        draw.line([(x, 0), (x, h)], fill=(255, 220, 60, 175), width=line_w)
        draw.line([(0, y), (w, y)], fill=(80, 240, 255, 175), width=line_w)
        try:
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = int(round(20 * scale)), int(round(11 * scale))
        bx_w = tw + pad * 2
        bx_h = th + pad * 2
        draw.rectangle([x + pad, pad, x + pad + bx_w, pad + bx_h], fill=(0, 0, 0, 160))
        draw.text((x + pad * 2, pad + 1), label, font=font, fill=(255, 230, 80, 255))
        draw.rectangle([pad, y + pad, pad + bx_w, y + pad + bx_h], fill=(0, 0, 0, 160))
        draw.text((pad * 2, y + pad + 1), label, font=font, fill=(100, 245, 255, 255))

    combined = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.save(out_path)
    return w, h


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--step", type=float, default=0.1)
    parser.add_argument("--minor", type=float, default=0.05)
    args = parser.parse_args()
    w, h = draw_normalized_grid(args.image, args.out, args.step, args.minor)
    print(f"Grid image saved: {args.out} ({w}x{h})")


if __name__ == "__main__":
    main()
