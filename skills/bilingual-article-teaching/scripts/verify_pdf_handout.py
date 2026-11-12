#!/usr/bin/env python3
"""Export a Word (.docx) handout to PDF on macOS Microsoft Word and audit PDF layout/pagination."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

# Default regex matches numbered cue lines rendered with hanging indent (e.g. "01\tHello...").
DEFAULT_CUE_PATTERN = r'(?:^|\n)(\d{2,3})(?:\t| +[A-Za-z"\'])'


def export_pdf_via_word(docx_path: Path, pdf_path: Path) -> None:
    """Export PDF using local Microsoft Word via AppleScript from the latest saved .docx."""
    if sys.platform != "darwin":
        raise RuntimeError("Word AppleScript export is only supported on macOS; pass an exported PDF to verify.")
    docx_abs = docx_path.resolve()
    pdf_abs = pdf_path.resolve()
    if not docx_abs.is_file():
        raise FileNotFoundError(f"Missing .docx input: {docx_abs}")
    pdf_abs.parent.mkdir(parents=True, exist_ok=True)
    if pdf_abs.exists():
        pdf_abs.unlink()

    def _quote(path: Path) -> str:
        return str(path).replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
tell application "Microsoft Word"
    set doc to open file name "{_quote(docx_abs)}"
    save as doc file name "{_quote(pdf_abs)}" file format format PDF
    close doc saving no
end tell
'''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if proc.returncode != 0 or not pdf_abs.is_file():
        raise RuntimeError(f"Microsoft Word PDF export failed for {docx_abs}: {proc.stderr.strip()}")


def verify_pdf_pagination(
    pdf_path: Path,
    *,
    total_cues: int | None = None,
    groups: list[dict] | None = None,
    cue_pattern: str = DEFAULT_CUE_PATTERN,
    expect_front_pages: int = 0,
    no_single_cue_tail: bool = False,
    require_ipa: bool = False,
    required_texts: list[str] | None = None,
) -> dict:
    """Audit extracted PDF text for Chinese encoding, Kangxi radical glitches, cue completeness, and page grouping."""
    try:
        import pypdf
    except ImportError as exc:
        raise ImportError("Verifying PDF pagination requires pypdf (`pip install pypdf`).") from exc

    reader = pypdf.PdfReader(str(pdf_path))
    if not reader.pages:
        raise ValueError(f"Empty PDF: {pdf_path}")

    pat = re.compile(cue_pattern)
    cue_to_pages: dict[int, set[int]] = {}
    page_nums_list: list[list[int]] = []
    page_ranges: list[str] = []
    all_pages_text: list[str] = []

    for page_idx, page in enumerate(reader.pages, 1):
        txt = page.extract_text() or ""
        all_pages_text.append(txt)
        found = []
        for match in pat.findall(txt):
            num = int(match)
            if total_cues is None or 1 <= num <= total_cues:
                found.append(num)
                cue_to_pages.setdefault(num, set()).add(page_idx)
        page_nums_list.append(found)
        page_ranges.append(f"P{page_idx}:{found[0]:02d}-{found[-1]:02d}" if found else f"P{page_idx}:[Front/Ref]")

    full_txt = "\n".join(all_pages_text)
    issues: list[str] = []

    if not re.search(r"[\u4e00-\u9fff]", full_txt):
        issues.append("PDF 未检测到常用汉字（可能发生字体嵌入/编码丢失）")

    kangxi = [ch for ch in full_txt if "\u2f00" <= ch <= "\u2fdf"]
    if kangxi:
        issues.append(f"PDF 存在康熙部首伪字乱码 ({len(kangxi)} 个，示例={''.join(kangxi[:10])!r})")

    if require_ipa and not re.search(r"/[^/\n]{2,}/", full_txt):
        issues.append("PDF 未检测到 IPA 美式音标文本")

    for req in required_texts or []:
        if req and req not in full_txt:
            issues.append(f"PDF 缺少预期文本: {req!r}")

    if expect_front_pages > 0:
        for fp in range(1, min(expect_front_pages, len(reader.pages)) + 1):
            if page_nums_list[fp - 1]:
                issues.append(f"第 {fp} 页应为首页参考区，但出现了正文条目: {page_nums_list[fp - 1]}")
        if len(reader.pages) > expect_front_pages and not page_nums_list[expect_front_pages]:
            issues.append(f"第 {expect_front_pages + 1} 页未见正文起始条目，疑似首页表格溢出跨页")

    if no_single_cue_tail and len(reader.pages) >= 2 and len(page_nums_list[-1]) == 1:
        issues.append(f"末页仅剩单条尾巴条目 (#{page_nums_list[-1][0]:02d})，建议微调分页避免孤儿尾条")

    if total_cues is not None:
        missing = [i for i in range(1, total_cues + 1) if i not in cue_to_pages]
        if missing:
            issues.append(f"PDF 正文漏提条目编号: {missing}")

    broken_groups: list[str] = []
    for g_idx, g in enumerate(groups or [], 1):
        s, e = g.get("起始条目"), g.get("末尾条目")
        if type(s) is not int or type(e) is not int:
            continue
        pages = set()
        for c_idx in range(s, e + 1):
            pages |= cue_to_pages.get(c_idx, set())
        label = g.get("主题") or f"组{g_idx}"
        if len(pages) != 1:
            detail = {c_idx: sorted(cue_to_pages.get(c_idx, set())) for c_idx in range(s, e + 1)}
            broken_groups.append(f"同页组 ({s:02d}-{e:02d} {label}) 跨页或缺失 {sorted(pages)}: {detail}")
    issues.extend(broken_groups)

    return {
        "pdf": str(pdf_path),
        "num_pages": len(reader.pages),
        "page_ranges": page_ranges,
        "broken_groups": broken_groups,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="要生成并/或核验的 PDF 路径")
    parser.add_argument("--export-from", type=Path, help="先用本机 Microsoft Word 从指定 .docx 导出最新 PDF")
    parser.add_argument("--cues", type=Path, help="对应的 cues.json（或含 cues 的清单 JSON），用于核对总条数")
    parser.add_argument("--groups", type=Path, help="同页对照 JSON，核对每组条目全部落在同一 PDF 页")
    parser.add_argument("--expect-front-pages", type=int, default=0, help="前置速查/封面页数（检验正文不提前溢出且不推迟）")
    parser.add_argument("--no-single-cue-tail", action="store_true", help="将末页仅剩 1 条正文条目视为告警/问题")
    parser.add_argument("--require-ipa", action="store_true", help="要求 PDF 包含 /.../ 音标符号")
    parser.add_argument("--require-text", action="append", default=[], help="要求 PDF 必须包含的关键文本（可多次传入）")
    args = parser.parse_args()

    if args.export_from:
        export_pdf_via_word(args.export_from, args.pdf)

    total_cues = None
    if args.cues:
        raw = json.loads(args.cues.read_text(encoding="utf-8-sig"))
        rows = raw["cues"] if isinstance(raw, dict) and "cues" in raw else raw
        total_cues = len(rows)

    groups = json.loads(args.groups.read_text(encoding="utf-8-sig")) if args.groups else None
    result = verify_pdf_pagination(
        args.pdf,
        total_cues=total_cues,
        groups=groups,
        expect_front_pages=args.expect_front_pages,
        no_single_cue_tail=args.no_single_cue_tail,
        require_ipa=args.require_ipa,
        required_texts=args.require_text,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, ImportError, RuntimeError) as exc:
        sys.exit(str(exc))
