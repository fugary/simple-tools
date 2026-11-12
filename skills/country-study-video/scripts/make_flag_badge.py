#!/usr/bin/env python3
"""Rasterize a statutory SVG (or raster) flag into a rounded dark-bordered RGBA PNG badge."""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

UA = "MyLessionsBilingualCourseBuilder/1.0 (educational; macos)"
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)


def _parse_dim(val: str | None) -> float | None:
    if not val:
        return None
    s = val.strip()
    if s.endswith("%"):
        return None
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)(?:px|pt|mm|cm|in)?$", s, re.IGNORECASE)
    return float(m.group(1)) if m else None


def parse_svg_aspect(svg_path: pathlib.Path) -> tuple[float, float]:
    """Return (width, height) aspect units parsed from SVG viewBox or width/height."""
    try:
        root = ET.fromstring(svg_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return (3.0, 2.0)

    w = _parse_dim(root.attrib.get("width"))
    h = _parse_dim(root.attrib.get("height"))
    if w and h and w > 0 and h > 0:
        return (w, h)

    vb = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    if vb:
        parts = re.split(r"[\s,]+", vb.strip())
        if len(parts) == 4:
            try:
                vw, vh = float(parts[2]), float(parts[3])
                if vw > 0 and vh > 0:
                    return (vw, vh)
            except ValueError:
                pass
    return (3.0, 2.0)


def download_wikimedia_flag_svg(flag_name: str, dest_svg: pathlib.Path) -> pathlib.Path:
    """Download a Wikimedia Commons flag SVG file cleanly (verifying strict CC0/PD when available)."""
    title = flag_name.strip().replace(" ", "_")
    if not title.startswith("File:"):
        title = f"File:{title}"
    api_url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "format": "json",
    })
    req = urllib.request.Request(api_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    pages = list((data.get("query") or {}).get("pages", {}).values())
    if not pages or "imageinfo" not in pages[0]:
        raise RuntimeError(f"Wikimedia flag SVG not found: {title}")
    ii = pages[0]["imageinfo"][0]
    file_url = ii.get("url")
    if not file_url:
        raise RuntimeError(f"Missing imageinfo url for {title}")
    req_svg = urllib.request.Request(file_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req_svg, timeout=25) as resp:
        dest_svg.parent.mkdir(parents=True, exist_ok=True)
        dest_svg.write_bytes(resp.read())
    return dest_svg


def _find_chrome(override: str | None) -> str | None:
    if override and pathlib.Path(override).is_file():
        return override
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    for cand in CHROME_CANDIDATES:
        if pathlib.Path(cand).is_file():
            return cand
    return None


def rasterize_svg(
    svg_path: pathlib.Path,
    target_w: int,
    target_h: int,
    chrome_bin: str | None = None,
) -> Image.Image:
    """Rasterize an SVG at exact target_w x target_h RGBA without clipping or white margins."""
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        with tempfile.TemporaryDirectory() as td:
            out_png = pathlib.Path(td) / "flag.png"
            subprocess.run(
                [rsvg, "-w", str(target_w), "-h", str(target_h), "-o", str(out_png), str(svg_path)],
                check=True,
            )
            return Image.open(out_png).convert("RGBA")

    try:
        import cairosvg  # type: ignore

        png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=target_w, output_height=target_h)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except ImportError:
        pass

    chrome = _find_chrome(chrome_bin)
    if chrome:
        with tempfile.TemporaryDirectory() as td:
            td_path = pathlib.Path(td)
            html_path = td_path / "wrap.html"
            shot_path = td_path / "shot.png"
            svg_uri = svg_path.resolve().as_uri()
            html_path.write_text(
                "<!doctype html><html><body style='margin:0;padding:0;overflow:hidden;background:#0f172a;'>"
                f"<img src='{svg_uri}' style='display:block;width:{target_w}px;height:{target_h}px;object-fit:fill;'>"
                "</body></html>",
                encoding="utf-8",
            )
            win_w = max(target_w + 100, 400)
            win_h = max(target_h + 220, 400)
            subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--force-device-scale-factor=1",
                    f"--window-size={win_w},{win_h}",
                    f"--screenshot={shot_path}",
                    html_path.as_uri(),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with Image.open(shot_path) as im:
                return im.convert("RGBA").crop((0, 0, target_w, target_h))

    raise RuntimeError(
        "No lossless vector SVG rasterizer found (checked rsvg-convert, cairosvg, and Chrome/Chromium). "
        "Install librsvg/cairosvg or provide a raster flag PNG."
    )


def build_flag_badge(
    src_path: pathlib.Path,
    out_path: pathlib.Path,
    *,
    width: int = 296,
    inner_pad: int = 10,
    outer_radius: int = 10,
    chrome_bin: str | None = None,
) -> tuple[pathlib.Path, tuple[int, int]]:
    """Build a rounded, white-hairline + dark-slate bordered RGBA flag badge PNG."""
    inner_w = width - 2 * inner_pad
    if inner_w < 40:
        raise ValueError(f"--width {width} is too small for --inner-pad {inner_pad}")

    if src_path.suffix.lower() == ".svg":
        aw, ah = parse_svg_aspect(src_path)
        inner_h = max(20, round(inner_w * ah / aw))
        hi = rasterize_svg(src_path, inner_w * 4, inner_h * 4, chrome_bin=chrome_bin)
        flag_im = hi.resize((inner_w, inner_h), Image.Resampling.LANCZOS)
    else:
        with Image.open(src_path) as im:
            raw = im.convert("RGBA")
        inner_h = max(20, round(inner_w * raw.height / max(raw.width, 1)))
        flag_im = raw.resize((inner_w, inner_h), Image.Resampling.LANCZOS)

    outer_w = width
    outer_h = inner_h + 2 * inner_pad

    canvas = Image.new("RGBA", (outer_w, outer_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [0, 0, outer_w - 1, outer_h - 1],
        radius=outer_radius,
        fill=(255, 255, 255, 220),
    )
    draw.rounded_rectangle(
        [2, 2, outer_w - 3, outer_h - 3],
        radius=max(outer_radius - 2, 2),
        fill=(15, 23, 42, 200),
    )

    inner_mask = Image.new("L", (inner_w, inner_h), 0)
    mask_draw = ImageDraw.Draw(inner_mask)
    mask_draw.rounded_rectangle([0, 0, inner_w - 1, inner_h - 1], radius=3, fill=255)
    canvas.paste(flag_im, (inner_pad, inner_pad), inner_mask)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG")
    return out_path, (outer_w, outer_h)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rasterize a country flag SVG/PNG into a rounded RGBA corner badge.")
    src_group = parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--input", type=pathlib.Path, help="Local flag .svg or .png file.")
    src_group.add_argument("--download-flag", help="Wikimedia Commons flag filename (e.g. Flag_of_Sweden.svg).")
    parser.add_argument("--save-svg", type=pathlib.Path, help="Optional path to save downloaded SVG.")
    parser.add_argument("--output", required=True, type=pathlib.Path, help="Output RGBA badge PNG path.")
    parser.add_argument("--width", type=int, default=296, help="Total outer badge width in px (default: 296).")
    parser.add_argument("--inner-pad", type=int, default=10, help="Frame thickness around flag in px (default: 10).")
    parser.add_argument("--radius", type=int, default=10, help="Outer corner radius in px (default: 10).")
    parser.add_argument("--chrome", help="Optional path to Chrome/Chromium binary.")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as td:
        if args.input:
            src_path = args.input
            if not src_path.is_file():
                raise FileNotFoundError(f"Flag file not found: {src_path}")
        else:
            svg_target = args.save_svg or (pathlib.Path(td) / "flag.svg")
            src_path = download_wikimedia_flag_svg(args.download_flag, svg_target)

        out, size = build_flag_badge(
            src_path,
            args.output,
            width=args.width,
            inner_pad=args.inner_pad,
            outer_radius=args.radius,
            chrome_bin=args.chrome,
        )
    print(f"Saved flag badge -> {out} ({size[0]}x{size[1]} RGBA)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
