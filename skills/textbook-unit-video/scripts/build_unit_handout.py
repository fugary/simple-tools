#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate Singapore-V2-styled printable Word (.docx) & PDF handouts for textbook units."""

import argparse
import json
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILLS_ROOT = SKILL_DIR.parent
BILINGUAL_SCRIPTS = SKILLS_ROOT / "bilingual-article-teaching/scripts"

sys.path.insert(0, str(BILINGUAL_SCRIPTS))
from study_cues import _merged_spans, group_links, occurrences  # noqa: E402
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
    """Return sorted unit directory names that already contain lesson.json."""
    if not make_base.is_dir():
        return []
    return [
        d.name
        for d in sorted(make_base.iterdir())
        if d.is_dir() and (d / "lesson.json").is_file() and (d / "front_matter.json").is_file()
    ]

# Singapore V2 palette
COLOR_NAVY = RGBColor(0x1E, 0x3A, 0x5F)
COLOR_BLUE = RGBColor(0x1D, 0x4E, 0xD8)
COLOR_BRICK = RGBColor(0x9A, 0x34, 0x12)
COLOR_DARK = RGBColor(0x1F, 0x29, 0x37)
COLOR_MUTED = RGBColor(0x64, 0x74, 0x8B)
COLOR_WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def apply_font(run, size_pt: float, *, bold: bool = False, color: RGBColor = COLOR_DARK) -> None:
    run.font.name = "Arial"
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rFonts.set(qn(attr), "Arial")
    rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")


def style_table_row(row, *, is_header: bool = False) -> None:
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))
    if is_header:
        trPr.append(OxmlElement("w:tblHeader"))


def format_cell(
    cell,
    text: str,
    *,
    size_pt: float = 9.0,
    bold: bool = False,
    color: RGBColor = COLOR_DARK,
    bg_hex: str | None = None,
    width=None,
    pad_v: int = 30,
    pad_h: int = 85,
) -> None:
    if width is not None:
        cell.width = width
    tcPr = cell._tc.get_or_add_tcPr()
    if bg_hex:
        tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:fill="{bg_hex}"/>'))
    tcMar = OxmlElement("w:tcMar")
    for side, val in (("top", pad_v), ("bottom", pad_v), ("left", pad_h), ("right", pad_h)):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.06
    apply_font(p.add_run(text), size_pt, bold=bold, color=color)


def add_table_borders(table, border_color: str = "CBD5E1") -> None:
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:left w:val="none"/><w:right w:val="none"/><w:insideV w:val="none"/>'
        f"</w:tblBorders>"
    )
    table._tbl.tblPr.append(borders)


def add_bottom_border(paragraph, *, color: str = "CBD5E1", sz: str = "6") -> None:
    pBdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="{sz}" w:space="3" w:color="{color}"/></w:pBdr>'
    )
    paragraph._p.get_or_add_pPr().append(pBdr)


def validate_meta(rows: list[dict], meta: dict) -> None:
    n = len(rows)
    for idx_q, entry in enumerate(meta.get("quick_refs", []), 1):
        q_idx, q_en, q_zh = entry
        if not 1 <= q_idx <= n:
            raise ValueError(f"quick_refs #{idx_q} out of bounds: {q_idx}")
        target = rows[q_idx - 1]
        if not occurrences(target["en"], q_en):
            raise ValueError(f"quick_refs #{idx_q} EN {q_en!r} not found in cue {q_idx}: {target['en']!r}")
        if q_zh not in target["zh"]:
            raise ValueError(f"quick_refs #{idx_q} ZH {q_zh!r} not found in cue {q_idx}: {target['zh']!r}")
    for item in meta.get("vocab_table", []):
        v_idx = item["cue_idx"]
        word = item["word"]
        if not 1 <= v_idx <= n:
            raise ValueError(f"vocab_table {word!r} out of bounds: {v_idx}")
        target = rows[v_idx - 1]
        if not occurrences(target["en"], word):
            raise ValueError(f"vocab_table {word!r} not found in cue {v_idx}: {target['en']!r}")
        ipa = item["ipa"]
        if not (ipa.startswith("/") and ipa.endswith("/") and len(ipa) >= 3):
            raise ValueError(f"Invalid IPA for {word!r}: {ipa!r}")


def build_unit_handout(
    make_dir: Path,
    out_dir: Path,
    unit_name: str,
    *,
    export_pdf: bool = True,
) -> dict:
    """Build printable Word & PDF handout for a textbook unit."""
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

    validate_meta(rows, meta)
    linked = group_links(rows, groups) if groups else set()

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(1.55)
    sec.left_margin = sec.right_margin = Cm(1.9)
    sec.different_first_page_header_footer = True

    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    apply_font(hp.add_run(meta["header"]), 8.5, color=COLOR_MUTED)

    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    apply_font(fp.add_run("第 "), 8.5, color=COLOR_MUTED)
    fp._p.append(parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls("w")))
    apply_font(fp.add_run(" 页"), 8.5, color=COLOR_MUTED)

    p_kicker = doc.add_paragraph()
    p_kicker.paragraph_format.space_before = Pt(0)
    p_kicker.paragraph_format.space_after = Pt(1.5)
    apply_font(p_kicker.add_run(meta["kicker"]), 9.0, bold=True, color=COLOR_BLUE)

    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(1.5)
    apply_font(p_title.add_run(meta["title"]), 18.0, bold=True, color=COLOR_NAVY)

    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(4.0)
    apply_font(p_sub.add_run(meta["subtitle"]), 10.0, color=COLOR_BRICK)
    add_bottom_border(p_sub, color="1E3A5F", sz="10")

    def add_heading(text: str, *, size: float = 11.0, before: float = 5.0, after: float = 1.5):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(before)
        p.paragraph_format.space_after = Pt(after)
        p.paragraph_format.keep_with_next = True
        apply_font(p.add_run(text), size, bold=True, color=COLOR_NAVY)
        return p

    add_heading("一、单元小档案（Unit Profile）", before=4.0)
    tbl_p = doc.add_table(rows=len(meta["facts"]), cols=1)
    tbl_p.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_p.autofit = False
    tbl_p.columns[0].width = Cm(17.2)
    add_table_borders(tbl_p)
    for i, fact in enumerate(meta["facts"]):
        style_table_row(tbl_p.rows[i])
        format_cell(
            tbl_p.rows[i].cells[0],
            fact,
            size_pt=9.0,
            color=COLOR_DARK,
            bg_hex="F8FAFC" if i % 2 == 0 else "F1F5F9",
            width=Cm(17.2),
            pad_v=28,
            pad_h=90,
        )

    add_heading("二、首页代表性词组与句型速查（Quick Reference）", before=5.5)
    q_items = meta["quick_refs"]
    tbl_q = doc.add_table(rows=1 + len(q_items), cols=4)
    tbl_q.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_q.autofit = False
    add_table_borders(tbl_q)
    q_widths = [Cm(1.3), Cm(6.5), Cm(7.5), Cm(1.9)]
    for j, w in enumerate(q_widths):
        tbl_q.columns[j].width = w
    style_table_row(tbl_q.rows[0], is_header=True)
    for j, htxt in enumerate(("序号", "英文重点表达", "对应中文句意", "出处条目")):
        format_cell(
            tbl_q.rows[0].cells[j],
            htxt,
            size_pt=8.5,
            bold=True,
            color=COLOR_WHITE,
            bg_hex="1E3A5F",
            width=q_widths[j],
            pad_v=32,
            pad_h=80,
        )
    for i, (q_idx, q_en, q_zh) in enumerate(q_items, 1):
        style_table_row(tbl_q.rows[i])
        bg = "FFFFFF" if i % 2 == 1 else "F8FAFC"
        for j, val in enumerate((str(i), q_en, q_zh, f"#{q_idx:03d}")):
            is_hl = j in (1, 2)
            format_cell(
                tbl_q.rows[i].cells[j],
                val,
                size_pt=9.0,
                bold=is_hl,
                color=COLOR_BLUE if is_hl else COLOR_DARK,
                bg_hex=bg,
                width=q_widths[j],
                pad_v=28,
                pad_h=80,
            )

    add_heading("三、核心难词学习表（美式音标与句中义）", before=5.5)
    vocab = meta["vocab_table"]
    tbl_v = doc.add_table(rows=1 + len(vocab), cols=5)
    tbl_v.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_v.autofit = False
    add_table_borders(tbl_v)
    v_widths = [Cm(2.4), Cm(2.85), Cm(2.1), Cm(8.35), Cm(1.5)]
    for j, w in enumerate(v_widths):
        tbl_v.columns[j].width = w
    style_table_row(tbl_v.rows[0], is_header=True)
    for j, htxt in enumerate(("词汇", "美式音标", "词性", "句中义及提示", "所在句")):
        format_cell(
            tbl_v.rows[0].cells[j],
            htxt,
            size_pt=8.5,
            bold=True,
            color=COLOR_WHITE,
            bg_hex="1E3A5F",
            width=v_widths[j],
            pad_v=32,
            pad_h=72,
        )
    for i, item in enumerate(vocab, 1):
        style_table_row(tbl_v.rows[i])
        bg = "FFFFFF" if i % 2 == 1 else "F8FAFC"
        vals = (item["word"], item["ipa"], item["pos"], item["meaning"], f"#{item['cue_idx']:03d}")
        for j, val in enumerate(vals):
            col = COLOR_NAVY if j == 0 else (COLOR_BRICK if j == 1 else COLOR_DARK)
            format_cell(
                tbl_v.rows[i].cells[j],
                val,
                size_pt=8.5,
                bold=(j == 0),
                color=col,
                bg_hex=bg,
                width=v_widths[j],
                pad_v=26,
                pad_h=72,
            )

    doc.add_page_break()

    p_body = add_heading("正文逐句双语精读（含重点提示与关联条目同页编排）", size=13.0, before=0.0, after=6.0)
    add_bottom_border(p_body, color="1E3A5F", sz="8")

    chap_map = {int(k): v for k, v in meta["chapter_map"].items()}

    for idx, cue in enumerate(rows, 1):
        if idx in chap_map:
            cp = doc.add_paragraph()
            cp.paragraph_format.space_before = Pt(9.0 if idx > 1 else 4.0)
            cp.paragraph_format.space_after = Pt(4.0)
            cp.paragraph_format.keep_with_next = True
            cp.paragraph_format.tab_stops.add_tab_stop(Cm(17.2), WD_ALIGN_PARAGRAPH.RIGHT)
            apply_font(cp.add_run(chap_map[idx]), 11.0, bold=True, color=COLOR_NAVY)
            if timeline and idx - 1 < len(timeline):
                mm, ss = divmod(int(round(timeline[idx - 1]["start"])), 60)
                apply_font(cp.add_run(f"\t成片 {mm:02d}:{ss:02d}"), 9.0, color=COLOR_MUTED)
            add_bottom_border(cp, color="CBD5E1", sz="4")

        notes = cue.get("notes") or []
        keep_after = idx in linked

        p_en = doc.add_paragraph()
        p_en.paragraph_format.left_indent = Cm(0.95)
        p_en.paragraph_format.first_line_indent = Cm(-0.95)
        p_en.paragraph_format.tab_stops.add_tab_stop(Cm(0.95))
        p_en.paragraph_format.space_before = Pt(3.0)
        p_en.paragraph_format.space_after = Pt(1.2)
        p_en.paragraph_format.line_spacing = 1.15
        p_en.paragraph_format.keep_together = True
        p_en.paragraph_format.keep_with_next = True
        apply_font(p_en.add_run(f"{idx:03d}\t"), 9.5, bold=True, color=COLOR_MUTED)

        en_spans = _merged_spans(cue["en"], cue.get("highlight_en") or [])
        pos = 0
        for l, r in en_spans:
            if pos < l:
                apply_font(p_en.add_run(cue["en"][pos:l]), 10.5, color=COLOR_DARK)
            apply_font(p_en.add_run(cue["en"][l:r]), 10.5, bold=True, color=COLOR_BLUE)
            pos = r
        if pos < len(cue["en"]):
            apply_font(p_en.add_run(cue["en"][pos:]), 10.5, color=COLOR_DARK)

        p_zh = doc.add_paragraph()
        p_zh.paragraph_format.left_indent = Cm(0.95)
        p_zh.paragraph_format.space_before = Pt(0)
        p_zh.paragraph_format.space_after = Pt(1.2 if notes else 4.0)
        p_zh.paragraph_format.line_spacing = 1.15
        p_zh.paragraph_format.keep_together = True
        p_zh.paragraph_format.keep_with_next = bool(notes) or keep_after

        zh_spans = _merged_spans(cue["zh"], cue.get("highlight_zh") or [])
        pos = 0
        for l, r in zh_spans:
            if pos < l:
                apply_font(p_zh.add_run(cue["zh"][pos:l]), 10.0, color=COLOR_DARK)
            apply_font(p_zh.add_run(cue["zh"][l:r]), 10.0, bold=True, color=COLOR_BLUE)
            pos = r
        if pos < len(cue["zh"]):
            apply_font(p_zh.add_run(cue["zh"][pos:]), 10.0, color=COLOR_DARK)

        if notes:
            p_nt = doc.add_paragraph()
            p_nt.paragraph_format.left_indent = Cm(0.95)
            p_nt.paragraph_format.space_before = Pt(0)
            p_nt.paragraph_format.space_after = Pt(4.0)
            p_nt.paragraph_format.line_spacing = 1.12
            p_nt.paragraph_format.keep_together = True
            p_nt.paragraph_format.keep_with_next = keep_after
            apply_font(p_nt.add_run("要点\u3000"), 9.0, bold=True, color=COLOR_BRICK)
            apply_font(p_nt.add_run(" ".join(notes)), 9.0, color=COLOR_BRICK)

    docx_path = out_dir / f"{unit_name} 双语学习讲义（打印版）.docx"
    pdf_path = out_dir / f"{unit_name} 双语学习讲义（打印版）.pdf"
    doc.save(str(docx_path))

    result = {"unit": unit_name, "docx": str(docx_path)}
    if export_pdf:
        export_pdf_via_word(docx_path, pdf_path)
        audit = verify_pdf_pagination(
            pdf_path,
            total_cues=len(rows),
            groups=groups,
            cue_pattern=r"(?:^|\n)(\d{3})(?:\t| +[^\s])",
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
