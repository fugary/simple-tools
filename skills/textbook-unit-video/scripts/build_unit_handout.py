#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate Singapore-V2-styled printable Word (.docx) & PDF handouts for textbook units via bilingual-article-teaching."""

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILLS_ROOT = SKILL_DIR.parent
BILINGUAL_SCRIPTS = SKILLS_ROOT / "bilingual-article-teaching/scripts"

sys.path.insert(0, str(BILINGUAL_SCRIPTS))
from study_cues import group_links, validate_front_matter, write_word  # noqa: E402
from verify_pdf_handout import export_pdf_via_word, verify_pdf_pagination  # noqa: E402


def detect_default_root() -> Path:
    """Resolve workspace root containing 课文视频制作/ from cwd or script ancestors."""
    cwd = Path.cwd().resolve()
    for base in [cwd, *cwd.parents]:
        if (base / "课文视频制作").is_dir():
            return base
    for parent in Path(__file__).resolve().parents:
        if (parent / "课文视频制作").is_dir():
            return parent
    return cwd


def discover_units(make_base: Path) -> list[str]:
    """Return sorted unit directory names that already contain lesson.json and front_matter.json."""
    if not make_base.is_dir():
        return []
    return [
        d.name
        for d in sorted(make_base.iterdir())
        if d.is_dir() and (d / "lesson.json").is_file() and (d / "front_matter.json").is_file()
    ]


def build_unit_handout(
    make_dir: Path,
    out_dir: Path,
    unit_name: str,
    *,
    export_pdf: bool = True,
) -> dict:
    """Build printable Word & PDF handout for a textbook unit using shared study_cues.write_word."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lesson = json.loads((make_dir / "lesson.json").read_text(encoding="utf-8"))
    rows = lesson["cues"]
    groups_path = make_dir / "打印同页对照.json"
    groups = json.loads(groups_path.read_text(encoding="utf-8")) if groups_path.exists() else []
    timeline_path = make_dir / "成片工程" / "timeline.json"
    if not timeline_path.exists():
        timeline_path = make_dir / "实测时间轴.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf-8")) if timeline_path.exists() else None
    meta = json.loads((make_dir / "front_matter.json").read_text(encoding="utf-8"))

    validate_front_matter(rows, meta, strict=False)
    linked = group_links(rows, groups) if groups else set()

    docx_path = out_dir / f"{unit_name} 双语学习讲义（打印版）.docx"
    pdf_path = out_dir / f"{unit_name} 双语学习讲义（打印版）.pdf"
    write_word(rows, docx_path, linked=linked, front_matter=meta, timeline=timeline)

    result = {"unit": unit_name, "docx": str(docx_path)}
    if export_pdf:
        export_pdf_via_word(docx_path, pdf_path)
        idx_digits = 3 if len(rows) >= 100 else 2
        audit = verify_pdf_pagination(
            pdf_path,
            total_cues=len(rows),
            groups=groups,
            cue_pattern=rf"(?:^|\n)(\d{{{idx_digits}}})(?:\t| +[^\s])",
            expect_front_pages=1,
            no_single_cue_tail=True,
            require_ipa=True,
            required_texts=[meta["title"], "要点"],
        )
        result["pdf_audit"] = audit
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=detect_default_root())
    parser.add_argument("--unit", help="Single unit folder name under 课文视频制作/ and 课文视频输出/")
    parser.add_argument("--no-pdf", action="store_true", help="Only build .docx without exporting/auditing PDF")
    args = parser.parse_args()

    make_base = args.root / "课文视频制作"
    out_base = args.root / "课文视频输出"
    targets = [args.unit] if args.unit else discover_units(make_base)
    if not targets:
        parser.error(f"No unit directories with lesson.json + front_matter.json found under {make_base}")

    all_ok = True
    for unit_name in targets:
        res = build_unit_handout(
            make_base / unit_name,
            out_base / unit_name,
            unit_name,
            export_pdf=not args.no_pdf,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        if res.get("pdf_audit", {}).get("issues"):
            all_ok = False
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
