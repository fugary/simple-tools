"""Check an untimed bilingual cue array and export selected study materials."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

ANNOTATIONS = ("highlight_en", "highlight_zh", "notes")
BAD_COLLOC_TAILS = {
    "is located", "located in", "made up of", "is made up", "borders with",
    "covered by", "famous for", "popular for", "known for", "surrounded",
    "half of the world",
}
DANGLING_TAIL_RE = re.compile(r"(?:\b(?:a|an|the)|\bone of|\bmade up|\bis made up|\bmost of)$")
POS_TOKENS = ("名词", "动词", "形容词", "副词", "专有名词", "介词", "分词", "短语", "代词", "数词", "连词")


def occurrences(text, phrase):
    """Match like the subtitle skill, retaining the original document's spacing."""
    expression = r"\s+".join(re.escape(word) for word in phrase.split())
    if re.match(r"[A-Za-z0-9]", phrase):
        expression = r"(?<![A-Za-z0-9])" + expression
    if re.search(r"[A-Za-z0-9]$", phrase):
        expression += r"(?![A-Za-z0-9])"
    return [match.span() for match in re.finditer(expression, text, re.IGNORECASE)]


def is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _has_overlap(spans):
    ordered = sorted(spans)
    return any(b[0] < a[1] for a, b in zip(ordered, ordered[1:]))


def _lemma_stems(word):
    low = word.lower()
    stems = {low}
    for suf in ("ies", "ves", "es", "ed", "ing", "s", "d"):
        if low.endswith(suf) and len(low) - len(suf) >= 3:
            stem = low[:-len(suf)]
            stems.add(stem)
            if suf == "ies":
                stems.add(stem + "y")
            elif suf == "ves":
                stems.add(stem + "f")
                stems.add(stem + "fe")
            elif suf == "ing":
                stems.add(stem + "e")
            if suf in ("ed", "ing") and len(stem) >= 3 and stem[-1] == stem[-2]:
                stems.add(stem[:-1])
    return stems


def validate(rows, strict=False):
    if not isinstance(rows, list) or not rows:
        raise ValueError("需要非空的中英条目数组。")
    review = []
    for index, cue in enumerate(rows, 1):
        if not isinstance(cue, dict):
            raise ValueError(f"第 {index} 条应为对象。")
        for key in ("en", "zh"):
            if not is_text(cue.get(key)):
                raise ValueError(f"第 {index} 条缺少有效的 {key} 正文。")
            if len(cue[key].splitlines()) != 1:
                raise ValueError(f"第 {index} 条 {key} 含有手工换行，请按语义拆条或合并成一行。")
            if strict and cue[key] != cue[key].strip():
                raise ValueError(f"第 {index} 条 {key} 首尾含有多余空白。")
        if strict:
            for field in ("en", "zh", "spoken"):
                val = cue.get(field) or ""
                if "..." in val or "…" in val:
                    raise ValueError(f"第 {index} 条 {field} 含有省略号，请写完整句式。")
                if "flag icon overlay" in val.lower() or re.search(r"\bTODO\b", val):
                    raise ValueError(f"第 {index} 条 {field} 残留开发标注字样。")
            for field in ("en", "spoken"):
                val = cue.get(field) or ""
                if "’" in val:
                    raise ValueError(f"第 {index} 条 {field} 含有弯撇号 ’，请统一为直撇号 '。")
        for key in ANNOTATIONS:
            values = cue.get(key, [])
            if not isinstance(values, list) or not all(is_text(v) for v in values):
                raise ValueError(f"第 {index} 条 {key} 应为非空字符串组成的数组。")
            if strict and key == "notes":
                for v in values:
                    if "flag icon overlay" in v.lower() or re.search(r"\bTODO\b", v):
                        raise ValueError(f"第 {index} 条 notes 残留开发标注字样。")

        hl_en = cue.get("highlight_en", [])
        hl_zh = cue.get("highlight_zh", [])
        if strict and len(hl_en) != len(hl_zh):
            raise ValueError(f"第 {index} 条英中高亮数量不对等：en={hl_en} vs zh={hl_zh}。")

        inspect = bool(hl_en) != bool(hl_zh)
        per_lang_spans = {"en": [], "zh": []}
        for lang, terms in (("en", hl_en), ("zh", hl_zh)):
            for term in terms:
                if strict and term != term.strip():
                    raise ValueError(f"第 {index} 条 {lang} 高亮词 {term!r} 首尾含多余空格。")
                if strict and lang == "en" and (term.lower() in BAD_COLLOC_TAILS or DANGLING_TAIL_RE.search(term)):
                    raise ValueError(f"第 {index} 条高亮 {term!r} 属于不完整截断搭配，请包含完整动词/介词结构或宾语成分。")
                spans = occurrences(cue[lang], term.strip())
                if not spans:
                    raise ValueError(f"第 {index} 条 {lang} 正文找不到完整高亮 {term!r}。")
                per_lang_spans[lang].append(spans)
            flat = [sp for group in per_lang_spans[lang] for sp in group]
            if _has_overlap(flat):
                raise ValueError(f"第 {index} 条 {lang} 正文内存在重叠的高亮区间，请拆分或合并短语。")
            inspect = inspect or len(flat) > 1

        if strict:
            for he, hz, sp_e, sp_z in zip(hl_en, hl_zh, per_lang_spans["en"], per_lang_spans["zh"]):
                if len(sp_e) != len(sp_z):
                    raise ValueError(
                        f"第 {index} 条高亮在句中出现次数不一致：{he!r}({len(sp_e)}次) vs {hz!r}({len(sp_z)}次)。"
                    )
        if inspect:
            review.append(index)
    return review


def collect_readability_warnings(rows, max_words=25):
    """Flag unusually long English sentences that may exceed target student readability."""
    warnings = []
    for index, cue in enumerate(rows, 1):
        words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", cue["en"])
        if len(words) > max_words:
            warnings.append(f"第 {index} 句共 {len(words)} 词（>{max_words} 词），建议核对学生水平或按分句拆分：{cue['en']}")
    return warnings


def validate_front_matter(rows, meta, strict=False):
    """Cross-check front-matter quick references, IPA vocab table, and chapter map against cues."""
    warnings = []
    vocab_errors = []
    n = len(rows)
    for idx_q, entry in enumerate(meta.get("quick_refs", []), 1):
        q_idx, q_en, q_zh = entry
        if not isinstance(q_idx, int) or not 1 <= q_idx <= n:
            raise ValueError(f"quick_refs 第 {idx_q} 项条目编号 {q_idx} 越界 (1..{n})。")
        target = rows[q_idx - 1]
        if not occurrences(target["en"], q_en):
            raise ValueError(f"quick_refs (#{q_idx}) 英文 {q_en!r} 未在原文词边界匹配。")
        if q_zh not in target["zh"]:
            raise ValueError(f"quick_refs (#{q_idx}) 中文 {q_zh!r} 未在译文中找到。")
        if q_en not in (target.get("highlight_en") or []):
            warnings.append(f"quick_refs (#{q_idx}) {q_en!r} 未列入该句 highlight_en。")

    for item in meta.get("vocab_table", []):
        v_idx = item["cue_idx"]
        word = item["word"]
        ipa = item["ipa"]
        pos = item["pos"]
        meaning = item["meaning"]
        if not isinstance(v_idx, int) or not 1 <= v_idx <= n:
            raise ValueError(f"vocab_table {word!r} 所在句 #{v_idx} 越界 (1..{n})。")
        target = rows[v_idx - 1]
        if not occurrences(target["en"], word):
            raise ValueError(f"vocab_table 词汇 {word!r} 未在第 {v_idx} 句原词边界出现。")
        if not (isinstance(ipa, str) and ipa.startswith("/") and ipa.endswith("/") and len(ipa) >= 3):
            raise ValueError(f"vocab_table 词汇 {word!r} IPA 格式无效: {ipa!r}。")
        if not is_text(pos) or not is_text(meaning):
            raise ValueError(f"vocab_table 词汇 {word!r} 缺少词性或释义。")
        stems = _lemma_stems(word)
        cue_notes = target.get("notes", [])
        matched = [note for note in cue_notes if any(st in note.lower() for st in stems)]
        if not matched:
            vocab_errors.append(f"vocab_table 词汇 {word!r} 在首现第 {v_idx} 句 notes 中缺少对应提示。")
        elif not any(re.search(r"/[^/\n]{2,}/", note) for note in matched):
            vocab_errors.append(f"vocab_table 词汇 {word!r} 在首现第 {v_idx} 句 notes 中缺少内嵌美式音标。")
        elif not any(any(tok in note for tok in POS_TOKENS) for note in matched):
            vocab_errors.append(f"vocab_table 词汇 {word!r} 在首现第 {v_idx} 句 notes 中缺少词性说明。")

    if strict and vocab_errors:
        raise ValueError("严格模式下难词首现注释联动未通过：\n- " + "\n- ".join(vocab_errors))
    warnings.extend(vocab_errors)

    chap_keys = sorted(int(k) for k in meta.get("chapter_map", {}))
    if chap_keys and (chap_keys[0] < 1 or chap_keys[-1] > n):
        raise ValueError(f"chapter_map 章节起始下标 {chap_keys} 超出正文条目范围 1..{n}。")
    return warnings


def annotated_text(rows):
    blocks = []
    for cue in rows:
        lines = [cue["en"], cue["zh"]]
        annotation = {key: cue[key] for key in ANNOTATIONS if cue.get(key)}
        if annotation:
            lines.append("【字幕标注】" + json.dumps(annotation, ensure_ascii=False))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def _merged_spans(text, terms):
    spans = sorted(span for term in terms for span in occurrences(text, term.strip()))
    merged = []
    for left, right in spans:
        if merged and left < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    return merged


def marked_runs(paragraph, text, terms, color):
    start = 0
    for left, right in _merged_spans(text, terms):
        if start < left:
            paragraph.add_run(text[start:left])
        run = paragraph.add_run(text[left:right])
        run.bold = True
        run.font.highlight_color = color
        start = right
    if start < len(text):
        paragraph.add_run(text[start:])


def group_links(rows, groups):
    """Return the one-based paragraph numbers that must stay with the next."""
    if not isinstance(groups, list):
        raise ValueError("同页对照文件应为数组。")
    linked = set()
    covered = set()
    for number, group in enumerate(groups, 1):
        if not isinstance(group, dict):
            raise ValueError(f"同页组 {number} 应为对象。")
        first, last = group.get("起始条目"), group.get("末尾条目")
        if type(first) is not int or type(last) is not int or not 1 <= first < last <= len(rows):
            raise ValueError(f"同页组 {number} 需要有效的首末编号，从 1 开始，至少包含两条。")
        for label, index in (("首条", first), ("末条", last)):
            if label in group and group[label] != rows[index - 1]["en"]:
                raise ValueError(f"同页组 {number} 的{label}与第 {index} 条英文不符，请核对排序。")
        span = range(first, last + 1)
        if not covered.isdisjoint(span):
            raise ValueError(f"同页组 {number} 与其他组重叠，请合并或重新划分。")
        covered.update(span)
        linked.update(range(first, last))
    return linked


# Empty answer slots, including full-width forms. Parenthesised content
# such as (to), (am, is, are) or (1) is handled by the lesson author.
SLOT = re.compile(r"[_＿]+|[（(]\s*[)）]|\[\s*\]|[□▢]")


def check_narration(rows):
    review = []
    for index, cue in enumerate(rows, 1):
        if not SLOT.search(cue["en"]):
            continue
        review.append(index)
        if "spoken" not in cue and is_text(cue.get("audio")):
            continue  # Existing audio is checked by listening, including its pauses.
        spoken = cue.get("spoken")
        if not is_text(spoken) or SLOT.search(spoken):
            raise ValueError(f"第 {index} 条含作答空位，请准备保留题干、略去占位符的 spoken 或逐句音频。")
        for word in ("blank", "underscore", "parenthesis", "parentheses", "bracket"):
            pattern = rf"\b{word}s?\b"
            if len(re.findall(pattern, spoken, re.I)) > len(re.findall(pattern, cue["en"], re.I)):
                raise ValueError(f"第 {index} 条朗读稿多出了占位符读法 {word}，请核对。")
    return review


def _apply_font(run, size_pt, bold=False, color=None):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    run.font.name = "Arial"
    run.font.size = Pt(size_pt)
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rFonts.set(qn(attr), "Arial")
    rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")


def _style_table_row(row, is_header=False):
    from docx.oxml import OxmlElement

    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))
    if is_header:
        trPr.append(OxmlElement("w:tblHeader"))


def _format_cell(cell, text, *, size_pt=9.0, bold=False, color=None, bg_hex=None, width=None, pad_v=30, pad_h=85):
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import nsdecls, qn
    from docx.shared import Pt

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
    r = p.add_run(text)
    _apply_font(r, size_pt, bold=bold, color=color)


def _add_table_borders(table, border_color="CBD5E1"):
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:left w:val="none"/><w:right w:val="none"/><w:insideV w:val="none"/>'
        f"</w:tblBorders>"
    )
    table._tbl.tblPr.append(borders)


def _add_bottom_border(paragraph, color="CBD5E1", sz="6"):
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="{sz}" w:space="3" w:color="{color}"/></w:pBdr>')
    paragraph._p.get_or_add_pPr().append(pBdr)


def _write_structured_word(doc, rows, linked, meta, timeline=None):
    """Build Singapore-V2-styled printable A4 handout with optional front reference tables and chapter timestamps."""
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    from docx.shared import Cm, Pt, RGBColor

    navy = RGBColor(0x1E, 0x3A, 0x5F)
    blue = RGBColor(0x1D, 0x4E, 0xD8)
    brick = RGBColor(0x9A, 0x34, 0x12)
    dark = RGBColor(0x1F, 0x29, 0x37)
    muted = RGBColor(0x64, 0x74, 0x8B)
    white = RGBColor(0xFF, 0xFF, 0xFF)

    meta = meta or {}
    is_long_unit = len(rows) >= 100
    idx_digits = 3 if is_long_unit else 2
    indent_cm = Cm(0.95 if is_long_unit else 0.85)

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(1.55)
    sec.left_margin = sec.right_margin = Cm(1.9)
    sec.different_first_page_header_footer = True
    if meta.get("header"):
        hp = sec.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _apply_font(hp.add_run(meta["header"]), 8.5, color=muted)
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _apply_font(fp.add_run("第 "), 8.5, color=muted)
    fp._p.append(parse_xml(r'<w:fldSimple %s w:instr="PAGE"/>' % nsdecls("w")))
    _apply_font(fp.add_run(" 页"), 8.5, color=muted)

    has_front = any(meta.get(k) for k in ("title", "facts", "quick_refs", "vocab_table"))
    if meta.get("kicker"):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1.5)
        _apply_font(p.add_run(meta["kicker"]), 9.0, bold=True, color=blue)
    if meta.get("title"):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1.5)
        _apply_font(p.add_run(meta["title"]), 18.0, bold=True, color=navy)
    if meta.get("subtitle"):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(4.0)
        _apply_font(p.add_run(meta["subtitle"]), 10.0, color=brick)
        _add_bottom_border(p, color="1E3A5F", sz="10")

    def _heading(txt, size=11.0, before=5.0, after=1.5):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(before)
        p.paragraph_format.space_after = Pt(after)
        p.paragraph_format.keep_with_next = True
        _apply_font(p.add_run(txt), size, bold=True, color=navy)
        return p

    if meta.get("facts"):
        default_facts_h = "一、单元小档案（Unit Profile）" if is_long_unit else "一、内容概要（Profile）"
        _heading(meta.get("facts_heading", default_facts_h), before=4.0)
        tbl = doc.add_table(rows=len(meta["facts"]), cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        tbl.columns[0].width = Cm(17.2)
        _add_table_borders(tbl)
        for i, fact in enumerate(meta["facts"]):
            _style_table_row(tbl.rows[i])
            _format_cell(tbl.rows[i].cells[0], fact, size_pt=9.0, color=dark, bg_hex="F8FAFC" if i % 2 == 0 else "F1F5F9", width=Cm(17.2), pad_v=28, pad_h=90)

    if meta.get("quick_refs"):
        _heading(meta.get("quick_refs_heading", "二、首页代表性词组与句型速查（Quick Reference）"), before=5.5)
        q_items = meta["quick_refs"]
        tbl = doc.add_table(rows=1 + len(q_items), cols=4)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        _add_table_borders(tbl)
        widths = [Cm(1.3), Cm(6.5), Cm(7.5), Cm(1.9)]
        for j, w in enumerate(widths):
            tbl.columns[j].width = w
        _style_table_row(tbl.rows[0], is_header=True)
        for j, htxt in enumerate(("序号", "英文重点表达", "对应中文句意", "出处条目")):
            _format_cell(tbl.rows[0].cells[j], htxt, size_pt=8.5, bold=True, color=white, bg_hex="1E3A5F", width=widths[j], pad_v=32, pad_h=80)
        for i, (q_idx, q_en, q_zh) in enumerate(q_items, 1):
            _style_table_row(tbl.rows[i])
            bg = "FFFFFF" if i % 2 == 1 else "F8FAFC"
            for j, val in enumerate((str(i), q_en, q_zh, f"#{q_idx:0{idx_digits}d}")):
                is_hl = j in (1, 2)
                _format_cell(tbl.rows[i].cells[j], val, size_pt=9.0, bold=is_hl, color=blue if is_hl else dark, bg_hex=bg, width=widths[j], pad_v=28, pad_h=80)

    if meta.get("vocab_table"):
        _heading(meta.get("vocab_heading", "三、核心难词学习表（美式音标与句中义）"), before=5.5)
        vocab = meta["vocab_table"]
        tbl = doc.add_table(rows=1 + len(vocab), cols=5)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        _add_table_borders(tbl)
        widths = [Cm(2.4), Cm(2.85), Cm(2.1), Cm(8.35), Cm(1.5)]
        for j, w in enumerate(widths):
            tbl.columns[j].width = w
        _style_table_row(tbl.rows[0], is_header=True)
        for j, htxt in enumerate(("词汇", "美式音标", "词性", "句中义及提示", "所在句")):
            _format_cell(tbl.rows[0].cells[j], htxt, size_pt=8.5, bold=True, color=white, bg_hex="1E3A5F", width=widths[j], pad_v=32, pad_h=72)
        for i, item in enumerate(vocab, 1):
            _style_table_row(tbl.rows[i])
            bg = "FFFFFF" if i % 2 == 1 else "F8FAFC"
            vals = (item["word"], item["ipa"], item["pos"], item["meaning"], f"#{item['cue_idx']:0{idx_digits}d}")
            for j, val in enumerate(vals):
                col = navy if j == 0 else (brick if j == 1 else dark)
                _format_cell(tbl.rows[i].cells[j], val, size_pt=8.5, bold=(j == 0), color=col, bg_hex=bg, width=widths[j], pad_v=26, pad_h=72)

    if has_front:
        doc.add_page_break()
    body_h = meta.get("body_heading", "正文逐句双语精读（含重点提示与关联条目同页编排）" if has_front else None)
    if body_h:
        p = _heading(body_h, size=13.0, before=0.0, after=6.0)
        _add_bottom_border(p, color="1E3A5F", sz="8")

    chap_map = {int(k): v for k, v in (meta.get("chapter_map") or {}).items()}
    for index, cue in enumerate(rows, 1):
        if index in chap_map:
            cp = _heading(chap_map[index], size=11.0, before=9.0 if index > 1 else 4.0, after=4.0)
            cp.paragraph_format.tab_stops.add_tab_stop(Cm(17.2), WD_ALIGN_PARAGRAPH.RIGHT)
            if timeline and index - 1 < len(timeline):
                mm, ss = divmod(int(round(timeline[index - 1]["start"])), 60)
                _apply_font(cp.add_run(f"\t成片 {mm:02d}:{ss:02d}"), 9.0, color=muted)
            _add_bottom_border(cp, color="CBD5E1", sz="4")
        notes = cue.get("notes") or []
        keep_after = index in linked

        p_en = doc.add_paragraph()
        p_en.paragraph_format.left_indent = indent_cm
        p_en.paragraph_format.first_line_indent = -indent_cm
        p_en.paragraph_format.tab_stops.add_tab_stop(indent_cm)
        p_en.paragraph_format.space_before = Pt(3.0)
        p_en.paragraph_format.space_after = Pt(1.2)
        p_en.paragraph_format.line_spacing = 1.15
        p_en.paragraph_format.keep_together = True
        p_en.paragraph_format.keep_with_next = True
        _apply_font(p_en.add_run(f"{index:0{idx_digits}d}\t"), 9.5, bold=True, color=muted)
        en_spans = _merged_spans(cue["en"], cue.get("highlight_en") or [])
        pos = 0
        for l, r in en_spans:
            if pos < l:
                _apply_font(p_en.add_run(cue["en"][pos:l]), 10.5, color=dark)
            _apply_font(p_en.add_run(cue["en"][l:r]), 10.5, bold=True, color=blue)
            pos = r
        if pos < len(cue["en"]):
            _apply_font(p_en.add_run(cue["en"][pos:]), 10.5, color=dark)

        p_zh = doc.add_paragraph()
        p_zh.paragraph_format.left_indent = indent_cm
        p_zh.paragraph_format.space_before = Pt(0)
        p_zh.paragraph_format.space_after = Pt(1.2 if notes else 4.0)
        p_zh.paragraph_format.line_spacing = 1.15
        p_zh.paragraph_format.keep_together = True
        p_zh.paragraph_format.keep_with_next = bool(notes) or keep_after
        zh_spans = _merged_spans(cue["zh"], cue.get("highlight_zh") or [])
        pos = 0
        for l, r in zh_spans:
            if pos < l:
                _apply_font(p_zh.add_run(cue["zh"][pos:l]), 10.0, color=dark)
            _apply_font(p_zh.add_run(cue["zh"][l:r]), 10.0, bold=True, color=blue)
            pos = r
        if pos < len(cue["zh"]):
            _apply_font(p_zh.add_run(cue["zh"][pos:]), 10.0, color=dark)

        if notes:
            p_nt = doc.add_paragraph()
            p_nt.paragraph_format.left_indent = indent_cm
            p_nt.paragraph_format.space_before = Pt(0)
            p_nt.paragraph_format.space_after = Pt(4.0)
            p_nt.paragraph_format.line_spacing = 1.12
            p_nt.paragraph_format.keep_together = True
            p_nt.paragraph_format.keep_with_next = keep_after
            _apply_font(p_nt.add_run("要点　"), 9.0, bold=True, color=brick)
            _apply_font(p_nt.add_run(" ".join(notes)), 9.0, color=brick)


def write_word(rows, path, linked=(), front_matter=None, timeline=None):
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

    _write_structured_word(doc, rows, linked, front_matter or {}, timeline=timeline)
    doc.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cues", type=Path)
    parser.add_argument("--word", type=Path, help="输出带高亮的 .docx")
    parser.add_argument("--text", type=Path, help="输出含字幕标注的 .txt")
    parser.add_argument("--groups", type=Path, help="带首末条目编号的同页对照 JSON")
    parser.add_argument("--front-matter", type=Path, help="可选首页档案、速查表、音标词表与章节配置 JSON")
    parser.add_argument("--timeline", type=Path, help="可选实测时间轴 timeline.json，用于在章节标题旁标注成片起始时间")
    parser.add_argument("--strict", action="store_true", help="启用严格质检（英中高亮 1:1 次数对等、截断搭配与脏字符守卫）")
    parser.add_argument("--check-narration", action="store_true", help="配音交接前核查填空题朗读稿")
    args = parser.parse_args()

    raw = json.loads(args.cues.read_text(encoding="utf-8-sig"))
    rows = raw["cues"] if isinstance(raw, dict) and "cues" in raw else raw
    review = validate(rows, strict=args.strict)
    for w in collect_readability_warnings(rows):
        print("注意：" + w)

    meta = None
    if args.front_matter:
        meta = json.loads(args.front_matter.read_text(encoding="utf-8-sig"))
        for w in validate_front_matter(rows, meta, strict=args.strict):
            print("注意：" + w)

    timeline = None
    if args.timeline and args.timeline.is_file():
        timeline = json.loads(args.timeline.read_text(encoding="utf-8-sig"))

    linked = set()
    if args.groups:
        groups = json.loads(args.groups.read_text(encoding="utf-8-sig"))
        linked = group_links(rows, groups)
        print(f"已核对 {len(groups)} 组打印同页条目。")
    if args.check_narration:
        slots = check_narration(rows)
        if slots:
            print("请听查作答空位及其停顿（条目从 1 开始）：" + ", ".join(map(str, slots)))
    outputs = [(args.word, ".docx"), (args.text, ".txt")]
    for path, extension in outputs:
        if path and (path.resolve() == args.cues.resolve() or path.suffix.lower() != extension):
            raise ValueError(f"请选择独立的 {extension} 输出路径。")
    # Finish both conversions before replacing any existing deliverable.
    from contextlib import ExitStack
    with ExitStack() as stack:
        ready = []
        for path, extension in outputs:
            if path is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=path.parent))) / ("study" + extension)
            if extension == ".docx":
                write_word(rows, tmp, linked, front_matter=meta, timeline=timeline)
            else:
                tmp.write_text(annotated_text(rows), encoding="utf-8")
            ready.append((tmp, path))
        for tmp, path in ready:
            tmp.replace(path)
    print(f"已核对 {len(rows)} 条双语正文，{sum(bool(c.get('notes')) for c in rows)} 条含顶部提示。")
    if review:
        print("请逐条人工核对同句多处高亮的 1:1 语义对应与顶部解释是否到位（条目从 1 开始）：" + ", ".join(map(str, review)))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, ImportError) as error:
        sys.exit(str(error))
