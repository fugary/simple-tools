#!/usr/bin/env python3
"""Search, contact-sheet review, download, and focal-crop strictly CC0 1.0 / Public Domain photos."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageOps

UA = "MyLessionsBilingualCourseBuilder/1.0 (https://localhost; educational; macos)"

BAD_TITLE_WORDS = (
    "map", "locator", "flag_of", "coat_of_arms", "emblem", "stamp", "postcard",
    "coin", "banknote", "chart", "diagram", "graph", "signature", "logo",
    "cover", "page_", ".pdf", ".svg", ".tif", ".djvu", "banner", "icon",
    "blank", "plan_of", "floorplan", "passport", "newspaper", "ticket",
    "stereoscop", "glass_negative", "lantern_slide", "peter_elfelt",
    "unsplash", "pexels", "pixabay",
)

FORBIDDEN_LICENSE_TOKENS = (
    "by-sa", "by-nc", "by-nd", "cc-by", "cc by", "gfdl", "fair use", "non-free", "all rights reserved",
)

FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def http_get_bytes(url: str, timeout: int = 25, retries: int = 4) -> bytes:
    """GET URL bytes with exponential backoff on transient HTTP/network errors."""
    delay = 0.8
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 502, 503, 504) and attempt < retries - 1:
                ra = exc.headers.get("Retry-After")
                wait_s = float(ra) if ra and ra.replace(".", "", 1).isdigit() else delay
                time.sleep(min(max(wait_s, delay), 12.0))
                delay *= 2
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError(f"Failed GET {url}")


def http_get_json(url: str, timeout: int = 25) -> dict | list:
    return json.loads(http_get_bytes(url, timeout=timeout).decode("utf-8"))


def is_strict_pd_cc0_wmc(page: dict, *, min_width: int = 1200, min_height: int = 675) -> tuple[bool, str, str]:
    """Verify Wikimedia Commons candidate has landscape photo dimensions and unambiguous CC0/PD status."""
    title = page.get("title", "")
    tl = title.lower()
    if any(bad in tl for bad in BAD_TITLE_WORDS):
        return False, "", ""

    ii = (page.get("imageinfo") or [{}])[0]
    w, h = int(ii.get("width") or 0), int(ii.get("height") or 0)
    if w < min_width or h < min_height:
        return False, "", ""
    ratio = w / max(h, 1)
    if ratio < 1.25 or ratio > 2.65:
        return False, "", ""
    if ii.get("mime") not in ("image/jpeg", "image/png"):
        return False, "", ""

    ext = ii.get("extmetadata") or {}
    lic_short = re.sub(r"<[^>]+>", "", (ext.get("LicenseShortName") or {}).get("value", "")).strip()
    lic_url = (ext.get("LicenseUrl") or {}).get("value", "").strip()
    usage = re.sub(r"<[^>]+>", "", (ext.get("UsageTerms") or {}).get("value", "")).strip()
    restr = re.sub(r"<[^>]+>", "", (ext.get("Restrictions") or {}).get("value", "")).strip()

    ll, ul, usl, rl = lic_short.lower(), lic_url.lower(), usage.lower(), restr.lower()
    if any(bad in rl for bad in ("trademark", "personality", "fop", "dwel", "nazi", "insignia")):
        return False, "", ""
    if any(forbid in ll or forbid in usl for forbid in FORBIDDEN_LICENSE_TOKENS):
        return False, "", ""

    ok_cc0 = (
        ll in ("cc0", "cc-zero", "cc0 1.0")
        or ll.startswith("cc0 ")
        or "creativecommons.org/publicdomain/zero/1.0" in ul
    )
    ok_pd = (
        "public domain" in ll
        or ll in ("pd", "pd-self", "pd-author", "pd-usgov", "pd-old", "pd-old-100", "pd-ineligible")
        or "creativecommons.org/publicdomain/mark/1.0" in ul
    ) and "pd-old-70" not in ll

    if not (ok_cc0 or ok_pd):
        return False, "", ""

    clean_lic = "CC0 1.0" if ok_cc0 else ("Public Domain" if "public domain" in ll else lic_short)
    default_url = "https://creativecommons.org/publicdomain/zero/1.0/" if ok_cc0 else ""
    return True, clean_lic, lic_url or default_url


def search_wmc(query: str, *, limit: int = 8) -> list[dict]:
    """Search Wikimedia Commons strictly for verified CC0/Public Domain landscape photos."""
    out: list[dict] = []
    search_variants = (
        f'{query} filetype:bitmap filewidth:>1199 fileheight:>674 hastemplate:"Cc-zero|PD-self|PD-author|PD-USGov|CC0"',
        f"{query} filetype:bitmap filewidth:>1199 fileheight:>674",
    )
    seen_titles: set[str] = set()
    for gsr in search_variants:
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query",
            "generator": "search",
            "gsrsearch": gsr,
            "gsrnamespace": 6,
            "gsrlimit": 35,
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 500,
            "format": "json",
        })
        try:
            data = http_get_json(url, timeout=20)
        except Exception as exc:
            print(f"  [WARN WMC] {query}: {exc}")
            continue

        pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 999))
        for p in pages:
            title = p.get("title", "")
            if title in seen_titles:
                continue
            ok, lic_name, lic_url = is_strict_pd_cc0_wmc(p)
            if not ok:
                continue
            ii = p["imageinfo"][0]
            ext = ii.get("extmetadata") or {}
            artist = re.sub(r"<[^>]+>", "", (ext.get("Artist") or {}).get("value", "Unknown")).strip()
            artist = re.sub(r"\s+", " ", artist)[:120]
            seen_titles.add(title)
            out.append({
                "id": "wmc:" + hashlib.md5(title.encode("utf-8")).hexdigest()[:12],
                "source": "Wikimedia Commons",
                "title": title.removeprefix("File:"),
                "page_url": ii.get("descriptionurl")
                or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                "file_url": ii.get("url", ""),
                "thumb_url": ii.get("thumburl") or ii.get("url", ""),
                "license_short": lic_name,
                "license_url": lic_url,
                "artist": artist,
                "width": int(ii["width"]),
                "height": int(ii["height"]),
            })
        time.sleep(0.15)
        if len(out) >= limit:
            break
    return out[:limit]


def search_wp_photos(query: str, *, limit: int = 6) -> list[dict]:
    """Search WordPress Photo Directory (all entries are verified CC0 1.0)."""
    out: list[dict] = []
    url = "https://wordpress.org/photos/wp-json/wp/v2/photos?" + urllib.parse.urlencode({
        "search": query,
        "per_page": 10,
        "_embed": 1,
    })
    try:
        items = http_get_json(url, timeout=20)
    except Exception as exc:
        print(f"  [WARN WP] {query}: {exc}")
        return out
    if not isinstance(items, list):
        return out
    for it in items:
        emb = it.get("_embedded") or {}
        fmedia = (emb.get("wp:featuredmedia") or [{}])[0]
        md = fmedia.get("media_details") or {}
        w, h = int(md.get("width") or 0), int(md.get("height") or 0)
        ratio = w / max(h, 1)
        if w < 1200 or h < 675 or ratio < 1.25 or ratio > 2.65:
            continue
        src = fmedia.get("source_url", "")
        sizes = md.get("sizes") or {}
        thumb = (sizes.get("medium_large") or sizes.get("large") or {}).get("source_url") or src
        author = ((emb.get("author") or [{}])[0]).get("name", "WordPress Photo Contributor")
        alt = re.sub(r"\s+", " ", fmedia.get("alt_text") or it.get("slug", "")).strip()[:100]
        out.append({
            "id": f"wp:{it['id']}",
            "source": "WordPress Photo Directory",
            "title": alt or f"WP Photo {it['id']}",
            "page_url": it.get("link", ""),
            "file_url": src,
            "thumb_url": thumb,
            "license_short": "CC0 1.0",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "artist": author,
            "width": w,
            "height": h,
        })
        if len(out) >= limit:
            break
    time.sleep(0.12)
    return out


def search_nasa(query: str, *, limit: int = 6) -> list[dict]:
    """Search NASA Image and Video Library (Public Domain)."""
    out: list[dict] = []
    url = "https://images-api.nasa.gov/search?" + urllib.parse.urlencode({"q": query, "media_type": "image"})
    try:
        data = http_get_json(url, timeout=20)
    except Exception as exc:
        print(f"  [WARN NASA] {query}: {exc}")
        return out
    for item in (data.get("collection") or {}).get("items", [])[:10]:
        d = (item.get("data") or [{}])[0]
        nasa_id = d.get("nasa_id", "")
        links = item.get("links") or []
        thumb = next((l["href"] for l in links if l.get("rel") == "preview"), "")
        asset_href = item.get("href", "")
        if not nasa_id or not thumb or not asset_href:
            continue
        try:
            assets = http_get_json(asset_href, timeout=15)
            orig = next((u for u in assets if ("~orig." in u or "~large." in u) and u.lower().endswith((".jpg", ".jpeg", ".png"))), "")
            if not orig:
                orig = next((u for u in assets if u.lower().endswith((".jpg", ".jpeg", ".png"))), "")
        except Exception:
            orig = ""
        if not orig:
            continue
        out.append({
            "id": f"nasa:{nasa_id}",
            "source": "NASA Image Library",
            "title": d.get("title", nasa_id)[:80],
            "page_url": f"https://images.nasa.gov/details/{nasa_id}",
            "file_url": orig,
            "thumb_url": thumb,
            "license_short": "Public Domain (NASA)",
            "license_url": "https://www.nasa.gov/nasa-brand-center/images-and-media/",
            "artist": d.get("center", "NASA"),
            "width": 1920,
            "height": 1080,
        })
        if len(out) >= limit:
            break
    return out


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for fp in FONT_CANDIDATES:
        if pathlib.Path(fp).is_file():
            try:
                return ImageFont.truetype(fp, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _fetch_thumb_cached(cand: dict, thumbs_dir: pathlib.Path) -> pathlib.Path | None:
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    p_jpg = thumbs_dir / f"{cand['id'].replace(':', '_')}.jpg"
    if p_jpg.is_file() and p_jpg.stat().st_size > 2000:
        return p_jpg
    try:
        raw = http_get_bytes(cand["thumb_url"], timeout=20)
        with Image.open(io.BytesIO(raw)) as im:
            im.convert("RGB").save(p_jpg, "JPEG", quality=88)
        return p_jpg
    except Exception as exc:
        print(f"  [WARN THUMB] {cand['thumb_url']}: {exc}")
        return None


def render_contact_sheet(title: str, rows: list[dict], thumbs_dir: pathlib.Path, out_path: pathlib.Path) -> pathlib.Path:
    """Render a 16:9 labeled contact sheet (A..D per slot) for visual review before download."""
    all_cands = [c for row in rows for c in row["candidates"][:4]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        thumb_paths = list(pool.map(lambda c: _fetch_thumb_cached(c, thumbs_dir), all_cands))
    thumb_map = {c["id"]: tp for c, tp in zip(all_cands, thumb_paths)}

    cols = 4
    cell_w, cell_h = 440, 310
    thumb_w, thumb_h = 420, 236
    margin_x, row_gap, header_h, left_label_h = 20, 20, 54, 54

    width = margin_x * 2 + cols * cell_w + (cols - 1) * 14
    height = header_h + max(len(rows), 1) * (left_label_h + cell_h + row_gap) + 20
    canvas = Image.new("RGB", (width, height), (20, 24, 34))
    draw = ImageDraw.Draw(canvas)
    f_title = _load_font(24)
    f_row = _load_font(18)
    f_meta = _load_font(14)

    draw.text((margin_x, 12), title, fill=(255, 225, 130), font=f_title)
    y = header_h
    labels = ("A", "B", "C", "D")
    for r_i, row in enumerate(rows, 1):
        draw.rectangle([margin_x, y, width - margin_x, y + 44], fill=(35, 42, 58))
        draw.text((margin_x + 12, y + 11), f"#{r_i} {row['slot']} | {row.get('description', '')[:58]}", fill=(240, 246, 255), font=f_row)
        y += left_label_h

        cands = row["candidates"][:4]
        for ci in range(cols):
            cx = margin_x + ci * (cell_w + 14)
            draw.rectangle([cx, y, cx + cell_w, y + cell_h], fill=(30, 35, 48), outline=(70, 82, 108), width=2)
            if ci < len(cands):
                c = cands[ci]
                tp = thumb_map.get(c["id"])
                if tp and tp.is_file():
                    with Image.open(tp) as tim:
                        fitted = ImageOps.fit(tim.convert("RGB"), (thumb_w, thumb_h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                    canvas.paste(fitted, (cx + 10, y + 8))
                badge_col = (80, 220, 140) if "CC0" in c["license_short"] else (120, 195, 255)
                src_short = "WMC" if "Wikimedia" in c["source"] else ("WP" if "WordPress" in c["source"] else "NASA")
                draw.text((cx + 10, y + 250), f"[{labels[ci]}] {src_short} | {c['license_short']} | {c['width']}x{c['height']}", fill=badge_col, font=f_meta)
                draw.text((cx + 10, y + 274), c["title"][:46], fill=(215, 222, 235), font=f_meta)
            else:
                draw.text((cx + 140, y + 135), "NO CANDIDATE", fill=(235, 110, 110), font=f_row)
        y += cell_h + row_gap

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=90)
    return out_path


def search_slot(slot_name: str, description: str, wmc_qs: list[str], wp_qs: list[str], nasa_qs: list[str], *, limit: int = 6) -> dict:
    """Collect and rank strict PD/CC0 candidates across WMC, WordPress Photo Directory, and NASA."""
    collected: list[dict] = []
    seen_ids: set[str] = set()

    def _extend(items: list[dict]) -> None:
        for item in items:
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                collected.append(item)

    for q in wmc_qs:
        _extend(search_wmc(q, limit=limit))
        if len(collected) >= limit:
            break
    if len(collected) < 4:
        for q in wp_qs:
            _extend(search_wp_photos(q, limit=limit))
            if len(collected) >= limit:
                break
    for q in nasa_qs:
        _extend(search_nasa(q, limit=limit))

    collected.sort(key=lambda x: (0 if x["width"] >= 1920 else 1, 0 if 1.4 <= (x["width"] / max(x["height"], 1)) <= 2.1 else 1))
    return {"slot": slot_name, "description": description, "candidates": collected[:limit]}


def fetch_and_crop_candidate(
    cand: dict,
    dest: pathlib.Path,
    *,
    sources_json: pathlib.Path | None = None,
    crop_x: float = 0.5,
    crop_y: float = 0.5,
    target_w: int = 1920,
    target_h: int = 1080,
) -> pathlib.Path:
    """Download candidate full image, focal-crop to 1920x1080 JPEG, and record metadata in sources.json."""
    if any(tok in cand.get("license_short", "").lower() for tok in FORBIDDEN_LICENSE_TOKENS):
        raise ValueError(f"Refusing restricted license candidate: {cand.get('license_short')}")

    raw = http_get_bytes(cand["file_url"], timeout=45)
    Image.MAX_IMAGE_PIXELS = 400_000_000
    with Image.open(io.BytesIO(raw)) as im:
        im = ImageOps.exif_transpose(im)
        orig_w, orig_h = im.size
        out_im = ImageOps.fit(
            im.convert("RGB"),
            (target_w, target_h),
            Image.Resampling.LANCZOS,
            centering=(crop_x, crop_y),
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        out_im.save(dest, "JPEG", quality=95)

    src_path = sources_json or (dest.parent / "sources.json")
    sources = json.loads(src_path.read_text(encoding="utf-8")) if src_path.is_file() else {}
    sources[dest.name] = {
        "source_type": "public_domain_cc0",
        "source_name": cand["source"],
        "title": cand.get("title", dest.stem),
        "license_short": cand["license_short"],
        "license_url": cand.get("license_url", ""),
        "page_url": cand.get("page_url", ""),
        "file_url": cand["file_url"],
        "artist": cand.get("artist", ""),
        "orig_size": f"{orig_w}x{orig_h}",
        "sha256_16": hashlib.sha256(dest.read_bytes()).hexdigest()[:16],
    }
    src_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def cmd_search(args: argparse.Namespace) -> int:
    rows: list[dict] = []
    if args.slots_json:
        spec = json.loads(args.slots_json.read_text(encoding="utf-8"))
        items = spec.get("slots", spec) if isinstance(spec, dict) else spec
        for item in items:
            row = search_slot(
                item["slot"],
                item.get("description", ""),
                item.get("wmc", []),
                item.get("wp", []),
                item.get("nasa", []),
                limit=args.limit,
            )
            rows.append(row)
            print(f"[{row['slot']}] -> {len(row['candidates'])} strict PD/CC0 candidates")
    else:
        slot = args.slot or "01_scene.jpg"
        row = search_slot(slot, args.description, args.query or [], args.wp_query or [], args.nasa_query or [], limit=args.limit)
        rows.append(row)
        print(f"[{row['slot']}] -> {len(row['candidates'])} strict PD/CC0 candidates")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "candidates_manifest.json"
    manifest = {r["slot"]: r for r in rows}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    sheet_path = args.out_dir / "candidates_sheet.jpg"
    render_contact_sheet(args.title or f"Strict CC0 / Public Domain Candidates ({len(rows)} slots)", rows, args.out_dir / "thumbs", sheet_path)
    print(f"Manifest -> {manifest_path}")
    print(f"Sheet -> {sheet_path}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.slot not in manifest:
        raise KeyError(f"Slot {args.slot!r} not in {args.manifest}")
    idx_map = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
    cands = manifest[args.slot]["candidates"]
    idx = idx_map[args.choice.upper()]
    if idx >= len(cands):
        raise IndexError(f"Choice {args.choice} out of range for {args.slot} ({len(cands)} candidates)")
    dest = fetch_and_crop_candidate(
        cands[idx],
        args.dest,
        sources_json=args.sources_json,
        crop_x=args.crop_x,
        crop_y=args.crop_y,
    )
    print(f"Saved {dest} <- {cands[idx]['source']} ({cands[idx]['license_short']})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Search & download strictly CC0 1.0 / Public Domain images with visual contact sheets.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="Search Wikimedia Commons / WordPress Photos / NASA and build contact sheet.")
    p_search.add_argument("--slots-json", type=pathlib.Path, help="Batch JSON: list of {slot, description, wmc, wp, nasa}.")
    p_search.add_argument("--slot", help="Single slot filename/label when not using --slots-json.")
    p_search.add_argument("--description", default="", help="Optional scene description for contact sheet.")
    p_search.add_argument("-q", "--query", action="append", help="Wikimedia Commons search query (repeatable).")
    p_search.add_argument("-w", "--wp-query", action="append", help="WordPress Photo Directory query (repeatable).")
    p_search.add_argument("--nasa", "--nasa-query", dest="nasa_query", action="append", help="NASA Image Library query (repeatable).")
    p_search.add_argument("--title", help="Optional title on the contact sheet header.")
    p_search.add_argument("--limit", type=int, default=6, help="Max candidates stored per slot (default: 6).")
    p_search.add_argument("--out-dir", required=True, type=pathlib.Path, help="Output directory for manifest & sheet.")

    p_fetch = sub.add_parser("fetch", help="Download selected candidate (A..F), focal-crop 1920x1080, update sources.json.")
    p_fetch.add_argument("--manifest", required=True, type=pathlib.Path, help="candidates_manifest.json from search.")
    p_fetch.add_argument("--slot", required=True, help="Slot key in candidates_manifest.json.")
    p_fetch.add_argument("--choice", required=True, help="Candidate label A..F from contact sheet.")
    p_fetch.add_argument("--dest", required=True, type=pathlib.Path, help="Destination .jpg file under 配图/.")
    p_fetch.add_argument("--sources-json", type=pathlib.Path, help="Optional sources.json path (defaults to dest.parent/sources.json).")
    p_fetch.add_argument("--crop-x", type=float, default=0.5, help="Horizontal focal center 0.0..1.0 (default: 0.5).")
    p_fetch.add_argument("--crop-y", type=float, default=0.5, help="Vertical focal center 0.0..1.0 (default: 0.5).")

    args = parser.parse_args()
    if args.cmd == "search":
        if not args.slots_json and not (args.query or args.wp_query or args.nasa_query):
            parser.error("search requires --slots-json or at least one -q / -w / --nasa query")
        return cmd_search(args)
    return cmd_fetch(args)


if __name__ == "__main__":
    raise SystemExit(main())
