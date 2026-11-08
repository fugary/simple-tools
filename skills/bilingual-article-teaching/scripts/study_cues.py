"""Check an untimed bilingual cue array and export selected study materials."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

ANNOTATIONS = ("highlight_en", "highlight_zh", "notes")


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


def validate(rows):
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
        for key in ANNOTATIONS:
            values = cue.get(key, [])
            if not isinstance(values, list) or not all(is_text(v) for v in values):
                raise ValueError(f"第 {index} 条 {key} 应为非空字符串组成的数组。")
        inspect = bool(cue.get("highlight_en")) != bool(cue.get("highlight_zh"))
        for lang in ("en", "zh"):
            terms = cue.get("highlight_" + lang, [])
            all_spans = []
            for term in terms:
                spans = occurrences(cue[lang], term.strip())
                if not spans:
                    raise ValueError(f"第 {index} 条 {lang} 正文找不到完整高亮 {term!r}。")
                all_spans.extend(spans)
            inspect = inspect or len(all_spans) > 1
        if inspect:
            review.append(index)
    return review


def annotated_text(rows):
    blocks = []
    for cue in rows:
        lines = [cue["en"], cue["zh"]]
        annotation = {key: cue[key] for key in ANNOTATIONS if cue.get(key)}
        if annotation:
            lines.append("【字幕标注】" + json.dumps(annotation, ensure_ascii=False))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def marked_runs(paragraph, text, terms, color):
    spans = sorted(span for term in terms for span in occurrences(text, term.strip()))
    start = 0
    merged = []
    for left, right in spans:
        if merged and left < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    for left, right in merged:
        if start < left:
            paragraph.add_run(text[start:left])
        run = paragraph.add_run(text[left:right])
        run.bold = True
        run.font.highlight_color = color
        start = right
    if start < len(text):
        paragraph.add_run(text[start:])


def write_word(rows, path):
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2.4)
    section.top_margin = section.bottom_margin = Cm(2)
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    style.font.size = Pt(12)
    style.paragraph_format.space_after = Pt(9)
    style.paragraph_format.line_spacing = 1.22
    for cue in rows:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.keep_together = True
        marked_runs(paragraph, cue["en"], cue.get("highlight_en", []), WD_COLOR_INDEX.YELLOW)
        paragraph.add_run().add_break()
        marked_runs(paragraph, cue["zh"], cue.get("highlight_zh", []), WD_COLOR_INDEX.YELLOW)
        for note in cue.get("notes", []):
            paragraph.add_run().add_break()
            tip = paragraph.add_run("要点　" + note)
            tip.font.size = Pt(10.5)
            tip.font.color.rgb = RGBColor.from_string("36536D")
    doc.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cues", type=Path)
    parser.add_argument("--word", type=Path, help="输出带高亮的 .docx")
    parser.add_argument("--text", type=Path, help="输出含字幕标注的 .txt")
    args = parser.parse_args()
    rows = json.loads(args.cues.read_text(encoding="utf-8-sig"))
    review = validate(rows)
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
                write_word(rows, tmp)
            else:
                tmp.write_text(annotated_text(rows), encoding="utf-8")
            ready.append((tmp, path))
        for tmp, path in ready:
            tmp.replace(path)
    print(f"已核对 {len(rows)} 条双语正文，{sum(bool(c.get('notes')) for c in rows)} 条含顶部提示。")
    if review:
        print("请核对同句多处高亮或单边高亮的对应关系（条目从 1 开始）：" + ", ".join(map(str, review)))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, ImportError) as error:
        sys.exit(str(error))
