#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge/dedup supplementary bilingual textbook lists and flag blanks/tricky pronunciations before TTS."""

import argparse
import json
import re
from pathlib import Path

SLOT_RE = re.compile(r"[_＿]+|[（(]\s*[)）]|\[\s*\]|[□▢]")
ABBREV_RE = re.compile(r"\b(?:sb|sth|e\.g|i\.e|etc|Mr|Mrs|Ms|Dr|a\.m|p\.m)\.", re.I)
PINYIN_OR_NUMBER_RE = re.compile(r"\b(?:\d+(?:[.,]\d+)?(?:st|nd|rd|th)?|[A-Z][a-z]{1,4}[a-z]{2,})\b")

COMMON_PROPER_WORDS = {
    "Unit", "Lesson", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday", "January", "February", "March", "April", "June", "July",
    "August", "September", "October", "November", "December", "China", "Chinese",
    "English", "France", "Paris", "Egypt", "Britain", "London", "Europe", "West",
    "National", "Phonics", "Grammar", "Before", "Reading", "Group", "Annual",
    "Sports", "Meet", "Little", "Bear", "Tomato", "Soybean", "Science", "Diary",
}


def norm_en(text: str) -> str:
    """Normalize English sentence/phrase for exact-duplicate comparison."""
    s = text.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^a-z0-9'\s]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_cues(path: Path) -> list[dict]:
    """Load cues from lesson.json, cues array JSON, or bilingual text lines."""
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        return raw["cues"] if isinstance(raw, dict) and "cues" in raw else raw

    lines = [ln.strip() for ln in path.read_text(encoding="utf-8-sig").splitlines()]
    cues = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if not cur or re.fullmatch(r"(?:\d*=+|[-*_]{3,})", cur):
            i += 1
            continue
        cur = re.sub(r"^#{1,6}\s+", "", cur)
        cur = re.sub(r"^[-*]\s+", "", cur)
        if cur.startswith(("要点", "【字幕标注】")):
            i += 1
            continue
        en = cur
        zh = ""
        if i + 1 < len(lines):
            nxt = re.sub(r"^#{1,6}\s+", "", re.sub(r"^[-*]\s+", "", lines[i + 1]))
            if nxt and not re.fullmatch(r"(?:\d*=+|[-*_]{3,})", nxt) and not nxt.startswith(("要点", "【字幕标注】")):
                zh = nxt
                i += 2
            else:
                i += 1
        else:
            i += 1
        cues.append({"en": en, "zh": zh})
    return cues


def load_supplementary_items(paths: list[Path]) -> list[str]:
    """Extract English candidate phrases/sentences from supplementary text/markdown files."""
    items = []
    for p in paths:
        for raw in p.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or re.fullmatch(r"[-|=]+", line):
                continue
            # Support markdown table row `| ... | ... |` or plain line
            if line.startswith("|"):
                cols = [c.strip() for c in line.strip("|").split("|")]
                for col in cols:
                    if re.search(r"[A-Za-z]{2,}", col) and not re.search(r"[\u4e00-\u9fff]", col):
                        items.append(col)
                        break
            elif re.search(r"[A-Za-z]{2,}", line):
                # Strip trailing Chinese explanation if separated by tab or fullwidth space
                en_part = re.split(r"[\t\u3000]", line, maxsplit=1)[0].strip()
                if en_part:
                    items.append(en_part)
    return items


def audit_materials(primary: list[dict], supp_items: list[str]) -> dict:
    """Classify supplementary items against primary cues and detect TTS/blank risks."""
    norm_index: dict[str, list[int]] = {}
    for idx, c in enumerate(primary, 1):
        norm_index.setdefault(norm_en(c["en"]), []).append(idx)

    exact_dups = []
    variants = []
    missing = []

    for item in supp_items:
        n_item = norm_en(item)
        if not n_item:
            continue
        if n_item in norm_index:
            exact_dups.append({"item": item, "matched_cues": norm_index[n_item]})
            continue
        # Substring / shared core match
        hits = [
            idx
            for idx, c in enumerate(primary, 1)
            if len(n_item) >= 4 and (n_item in norm_en(c["en"]) or norm_en(c["en"]) in n_item)
        ]
        if hits:
            variants.append({"item": item, "related_cues": hits[:5]})
        else:
            missing.append(item)

    blanks = []
    tricky_spoken = []
    for idx, c in enumerate(primary, 1):
        en = c["en"]
        if SLOT_RE.search(en):
            blanks.append({"cue": idx, "en": en, "has_spoken": bool(c.get("spoken"))})
        abbrevs = ABBREV_RE.findall(en)
        nums_or_names = [
            tok for tok in PINYIN_OR_NUMBER_RE.findall(en)
            if tok not in COMMON_PROPER_WORDS and (any(ch.isdigit() for ch in tok) or re.search(r"(xiao|lan|wen|hao|sui)", tok, re.I))
        ]
        if (abbrevs or nums_or_names) and not c.get("spoken"):
            tricky_spoken.append({
                "cue": idx,
                "en": en,
                "tokens": abbrevs + nums_or_names,
            })

    return {
        "primary_count": len(primary),
        "supplementary_count": len(supp_items),
        "exact_duplicates": exact_dups,
        "variants_or_contained": variants,
        "new_items_not_in_primary": missing,
        "blank_slots_needing_spoken_or_pause": blanks,
        "tricky_pronunciation_candidates": tricky_spoken,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary", type=Path, help="Primary lesson.json or bilingual TXT/MD draft")
    parser.add_argument("--supp", type=Path, nargs="*", default=[], help="Optional supplementary list files")
    parser.add_argument("--out", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    primary = load_cues(args.primary)
    supp_items = load_supplementary_items(args.supp) if args.supp else []
    report = audit_materials(primary, supp_items)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
