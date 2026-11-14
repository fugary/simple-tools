#!/usr/bin/env python3
"""Audit country episode visuals for geography-landscape rules, official flag overlays, and zero-copyright provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from PIL import Image

BANNED_HOSTS = ("unsplash.com", "images.unsplash.com", "pexels.com", "pixabay.com")
RESTRICTED_LICENSES = ("cc by", "by-sa", "fal", "free art license", "noncommercial", "no derivatives", "all rights reserved")
ALLOWED_PD_CC0 = {"cc0", "cc0 1.0", "public domain", "public domain (nasa)", "pd"}


def sha256_short(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _is_banned_license(lic: str) -> bool:
    low = lic.strip().lower()
    if any(low == ok or low.startswith(ok) for ok in ALLOWED_PD_CC0) or "ai 原创" in low:
        return False
    return any(tok in low for tok in RESTRICTED_LICENSES)


def audit_unit(unit_dir: Path, *, allow_attribution: bool = False) -> dict:
    unit_abs = unit_dir.resolve()
    lesson_path = unit_abs / "lesson.json"
    sb_path = unit_abs / "分镜.json"
    sources_path = unit_abs / "配图" / "sources.json"
    md_path = unit_abs / "配图来源.md"

    issues: list[str] = []
    warnings: list[str] = []

    if not lesson_path.is_file():
        return {"unit_dir": str(unit_abs), "issues": [f"缺少 lesson.json: {lesson_path}"], "warnings": []}

    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    sb = json.loads(sb_path.read_text(encoding="utf-8")) if sb_path.is_file() else {}
    sources = json.loads(sources_path.read_text(encoding="utf-8")) if sources_path.is_file() else {}
    md_text = md_path.read_text(encoding="utf-8") if md_path.is_file() else ""

    if not sources:
        issues.append(f"缺少或空的配图台账: {sources_path}")
    if not md_path.is_file():
        issues.append(f"缺少配图来源文档: {md_path}")

    # 1. Check natural-landscape policy & unique scene images
    unique_images: dict[str, Path] = {}
    for sc in lesson.get("scenes", []):
        rel = sc["image"]
        if re.search(r"地图|locator|map[_.]", rel, re.IGNORECASE):
            issues.append(f"分镜 Cue {sc['cue']} 涉嫌引用手绘/版图类图片（应改为自然风光实景）: {rel}")
        unique_images[rel] = unit_abs / rel

    # 2. Check official flag overlay metadata & badge image dimensions
    overlays = lesson.get("overlays") or sb.get("overlays") or []
    if not overlays:
        issues.append("缺少独立国旗前景叠加层 overlays 配置")
    for idx_ov, ov in enumerate(overlays, 1):
        badge_rel = ov.get("image", "")
        badge_path = unit_abs / badge_rel
        if not badge_path.is_file():
            issues.append(f"国旗叠加层 #{idx_ov} 缺失图片: {badge_path}")
            continue
        with Image.open(badge_path) as im:
            bw, bh = im.size
            mode = im.mode
        max_w = int(1920 * float(ov.get("max_width_ratio", 0.16)))
        if "A" not in mode:
            warnings.append(f"国旗徽章 {badge_rel} 模式为 {mode}，建议使用带透明圆角边的 RGBA PNG")
        if bw > max_w + 1:
            issues.append(f"国旗徽章 {badge_rel} 宽度 {bw}px 超出安全比例上限 ({max_w}px)")
        if sb.get("overlays") and not ov.get("official_source") and not sb["overlays"][0].get("official_source"):
            warnings.append(f"国旗叠加层 #{idx_ov} 未标注 official_source 法定规范来源")

    # 3. Check zero-copyright-risk provenance & disk SHA-256 parity
    for rel, img_path in unique_images.items():
        name = Path(rel).name
        if not img_path.is_file():
            issues.append(f"缺失分镜图片文件: {img_path}")
            continue
        with Image.open(img_path) as im:
            w, h = im.size
        if (w, h) != (1920, 1080):
            warnings.append(f"配图 {name} 尺寸为 {w}x{h}（建议预归一化为 1920x1080）")
        sha = sha256_short(img_path)

        meta = sources.get(name)
        if not meta:
            issues.append(f"sources.json 缺少配图记录: {name}")
            continue
        meta_blob = json.dumps(meta, ensure_ascii=False).lower()
        for host in BANNED_HOSTS:
            if host in meta_blob:
                issues.append(f"{name} 的来源含禁用聚合图床域 ({host}): {meta.get('page_url', '')}")
        lic = meta.get("license_short", "")
        if not allow_attribution and _is_banned_license(lic):
            issues.append(f"{name} 授权 {lic!r} 不符合默认纯 CC0 / Public Domain / AI 原创零版权风险策略")

        if md_text:
            if name not in md_text or sha not in md_text:
                issues.append(f"配图来源.md 中 {name} 与磁盘最新 SHA-256 ({sha}) 不一致，请重新运行 write_country_sources.py")

    if md_text:
        low_md = md_text.lower()
        for host in BANNED_HOSTS:
            if host in low_md:
                issues.append(f"配图来源.md 仍残留禁用域名引用: {host}")

    return {
        "unit_dir": str(unit_abs),
        "unique_scenes": len(unique_images),
        "overlays": len(overlays),
        "issue_count": len(issues),
        "warning_count": len(warnings),
        "issues": issues,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-dir", action="append", type=Path, required=True, help="Country episode directory (repeatable)")
    parser.add_argument("--allow-attribution", action="store_true", help="Permit CC BY / CC BY-SA licenses when explicitly authorized")
    parser.add_argument("--report", type=Path, help="Optional JSON audit output path")
    args = parser.parse_args()

    results = [audit_unit(d, allow_attribution=args.allow_attribution) for d in args.unit_dir]
    total_issues = sum(r["issue_count"] for r in results)
    payload = {"units": results, "total_issues": total_issues}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if total_issues > 0 else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))
