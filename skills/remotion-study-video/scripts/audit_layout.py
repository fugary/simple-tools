#!/usr/bin/env python3
"""
audit_layout.py
Pre-render full-timeline layout, collision, viewport-bounds, and text-overflow gate
for remotion-study-video `project.json` (steps across the timeline every 0.25s).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


WIDTH = 1920.0
HEIGHT = 1080.0
SUBTITLE_SAFE_Y = 825.0


@dataclass
class RectBox:
    tag: str
    kind: str
    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    def intersects(self, other: "RectBox", pad: float = 0.0) -> bool:
        return (
            self.x < other.x2 - pad
            and self.x2 > other.x + pad
            and self.y < other.y2 - pad
            and self.y2 > other.y + pad
        )


def estimate_text_px(text: str, font_size: float) -> float:
    """Approximate rendered text width in pixels for mixed EN/CJK strings."""
    total = 0.0
    for ch in text:
        if ord(ch) > 127:
            total += font_size * 1.02
        elif ch.isupper():
            total += font_size * 0.68
        elif ch in "ilIjtf.,:;'|! ":
            total += font_size * 0.34
        elif ch in "mwMW@#%":
            total += font_size * 0.84
        else:
            total += font_size * 0.56
    return total


def cue_note_texts(cue: dict) -> list[str]:
    rich_notes = cue.get("richNotes") or []
    if rich_notes:
        return ["".join(seg.get("text", "") for seg in line) for line in rich_notes if line]
    return [str(n) for n in (cue.get("notes") or []) if str(n).strip()]


def build_study_hint_box(cue: dict) -> RectBox | None:
    lines = cue_note_texts(cue)
    if not lines:
        return None
    max_w = 0.0
    total_lines = 0
    for line in lines:
        fs = 30.0 if len(line) > 48 else 36.0
        px = estimate_text_px(line, fs)
        max_w = max(max_w, min(1620.0, px + 72.0))
        wrapped = max(1, int((px + 1547.0) // 1548.0))
        total_lines += wrapped
    box_w = max(320.0, min(1620.0, max_w))
    box_h = 28.0 + total_lines * 46.0
    return RectBox(
        tag="StudyHint",
        kind="chrome_hint",
        x=(WIDTH - box_w) / 2.0,
        y=90.0,
        w=box_w,
        h=box_h,
    )


def build_subtitle_box(cue: dict) -> RectBox:
    en = str(cue.get("en", ""))
    zh = str(cue.get("zh", ""))
    en_fs = 38.0 if len(en) > 105 else (44.0 if len(en) > 76 else 52.0)
    zh_fs = 36.0 if len(zh) > 36 else (42.0 if len(zh) > 26 else 46.0)
    en_lines = max(1, int((estimate_text_px(en, en_fs) + 1719.0) // 1720.0)) if en else 0
    zh_lines = max(1, int((estimate_text_px(zh, zh_fs) + 1719.0) // 1720.0)) if zh else 0
    content_h = en_lines * en_fs * 1.28 + zh_lines * zh_fs * 1.3 + (8.0 if en and zh else 0.0)
    bottom_edge = HEIGHT - 42.0
    top_edge = bottom_edge - content_h
    box_w = min(1720.0, max(estimate_text_px(en, en_fs), estimate_text_px(zh, zh_fs), 320.0))
    return RectBox(
        tag=f"Subtitle#{cue.get('index', '?')}",
        kind="subtitle",
        x=(WIDTH - box_w) / 2.0,
        y=top_edge,
        w=box_w,
        h=content_h,
    )


def hud_boxes_for_item(item: dict, has_top_note: bool) -> list[RectBox]:
    pos = item.get("position", "top-right")
    top_offset = 136.0 if has_top_note else 44.0
    w = 390.0
    h = 190.0
    if pos == "top-left":
        return [RectBox(item.get("id", "hud"), f"hud:{item.get('kind')}", 48.0, top_offset, w, h)]
    if pos == "bottom-right":
        return [RectBox(item.get("id", "hud"), f"hud:{item.get('kind')}", WIDTH - 48.0 - w, HEIGHT - 250.0 - h, w, h)]
    return [RectBox(item.get("id", "hud"), f"hud:{item.get('kind')}", WIDTH - 48.0 - w, top_offset, w, h)]


def overlay_boxes_for_item(item: dict, has_top_note: bool) -> list[RectBox]:
    kind = item.get("kind", "")
    oid = item.get("id", kind)

    if kind == "cover_hero":
        boxes = [RectBox(f"{oid}:title", kind, 104.0, 560.0, 960.0, 250.0)]
        if item.get("showSeal", True):
            boxes.append(RectBox(f"{oid}:seal", kind, WIDTH - 120.0 - 122.0, 130.0, 122.0, 122.0))
        return boxes

    if kind == "globe_fact_card":
        boxes = [RectBox(f"{oid}:card", kind, 100.0, 175.0, 700.0, 540.0)]
        if item.get("showGlobe", True):
            boxes.append(RectBox(f"{oid}:globe", kind, WIDTH - 96.0 - 520.0, 210.0, 520.0, 520.0))
        return boxes

    if kind == "area_infographic":
        top_y = 228.0 if has_top_note else 160.0
        bars = item.get("items") or item.get("bars") or []
        bars_h = 150.0 + len(bars) * 92.0
        return [
            RectBox(f"{oid}:hero", kind, 88.0, top_y + 25.0, 560.0, 460.0),
            RectBox(f"{oid}:bars", kind, 710.0, top_y, WIDTH - 88.0 - 710.0, bars_h),
        ]

    if kind == "blueprint_callout":
        boxes = [RectBox(f"{oid}:card", kind, 96.0, 230.0, 600.0, 340.0)]
        if item.get("svgPreset") == "temple_of_heaven":
            boxes.append(RectBox(f"{oid}:svg", kind, 880.0, 120.0, 850.0, 650.0))
        return boxes

    if kind == "calligraphy_bubbles":
        boxes = [
            RectBox(f"{oid}:card", kind, 96.0, 215.0, 600.0, 340.0),
            RectBox(f"{oid}:medallion", kind, 1290.0, 220.0, 280.0, 280.0),
        ]
        for idx, b in enumerate(item.get("bubbles") or []):
            boxes.append(RectBox(f"{oid}:bubble[{idx}]", kind, float(b.get("x", 1000.0)), float(b.get("y", 230.0)), 260.0, 68.0))
        return boxes

    if kind == "waving_flag_showcase":
        return [RectBox(f"{oid}:story", kind, 120.0, 210.0, 720.0, 480.0)]

    if kind == "terrain_profile":
        # Open-canvas vector ridge line: only header pill & floating step labels occupy boxes.
        boxes = [RectBox(f"{oid}:pill", kind, (WIDTH - 820.0) / 2.0, 186.0, 820.0, 62.0)]
        for idx, st in enumerate(item.get("steps") or []):
            boxes.append(RectBox(f"{oid}:step[{idx}]", kind, float(st.get("x", 0.0)), float(st.get("y", 0.0)), 380.0, 98.0))
        return boxes

    if kind == "elevation_ruler":
        return [RectBox(f"{oid}:card", kind, WIDTH - 76.0 - 600.0, 210.0, 600.0, 580.0)]

    if kind == "river_course_hud":
        return [RectBox(f"{oid}:card", kind, 96.0, 228.0, 580.0, 460.0)]

    if kind == "qa_quiz":
        x = float(item.get("x", 1060.0))
        y = float(item.get("y", 228.0))
        w = float(item.get("w", 780.0))
        return [RectBox(f"{oid}:quiz", kind, x, y, w, 310.0)]

    return []


def audit_project(project: dict, step_sec: float = 0.25) -> list[dict]:
    """Audit full timeline for collisions, out-of-bounds widgets, and text overflow."""
    issues: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()

    def record(key: tuple[str, str], issue: dict) -> None:
        if key not in seen_keys:
            seen_keys.add(key)
            issues.append(issue)

    meta = project.get("meta") or {}
    duration = float(meta.get("durationInSeconds", 0.0))
    cues = project.get("cues") or []
    huds = project.get("hud") or []
    overlays = project.get("overlays") or []

    if duration <= 0:
        record(("meta", "duration"), {"time": 0.0, "rule": "invalid_duration", "detail": f"durationInSeconds={duration}"})
        return issues

    # Static structural & overflow checks on cues and qa_quiz items
    for cue in cues:
        idx = cue.get("index", "?")
        en = str(cue.get("en", ""))
        zh = str(cue.get("zh", ""))
        en_fs = 38.0 if len(en) > 105 else (44.0 if len(en) > 76 else 52.0)
        zh_fs = 36.0 if len(zh) > 36 else (42.0 if len(zh) > 26 else 46.0)
        if estimate_text_px(en, en_fs) > 1720.0 * 2.15:
            record(
                ("cue_en_wrap", str(idx)),
                {"time": float(cue.get("start", 0.0)), "rule": "subtitle_en_overflow", "detail": f"Cue#{idx} EN exceeds 2 lines ({len(en)} chars)"},
            )
        if estimate_text_px(zh, zh_fs) > 1720.0 * 2.05:
            record(
                ("cue_zh_wrap", str(idx)),
                {"time": float(cue.get("start", 0.0)), "rule": "subtitle_zh_overflow", "detail": f"Cue#{idx} ZH exceeds 2 lines ({len(zh)} chars)"},
            )

    for ov in overlays:
        if ov.get("kind") == "qa_quiz":
            oid = ov.get("id", "qa_quiz")
            inner_w = float(ov.get("w", 780.0)) - 108.0
            for q_idx, q in enumerate(ov.get("items") or []):
                qs, as_, qe = float(q.get("qStart", 0)), float(q.get("aStart", 0)), float(q.get("end", 0))
                if not (qs < as_ < qe):
                    record(
                        ("qa_timing", f"{oid}:{q_idx}"),
                        {"time": qs, "rule": "qa_quiz_timing", "detail": f"{oid}[{q_idx}] invalid qStart({qs}) < aStart({as_}) < end({qe})"},
                    )
                a_en = f"✓ {q.get('aEn', '')}"
                a_zh = str(q.get("aZh", ""))
                a_en_fs = 21.0 if len(str(q.get("aEn", ""))) > 46 else 24.0
                if estimate_text_px(a_en, a_en_fs) > inner_w * 1.95:
                    record(
                        ("qa_en_ov", f"{oid}:{q_idx}"),
                        {"time": as_, "rule": "qa_answer_en_overflow", "detail": f"{oid}[{q_idx}] aEn overflows green card: '{a_en}'"},
                    )
                if estimate_text_px(a_zh, 20.0) > inner_w * 1.95:
                    record(
                        ("qa_zh_ov", f"{oid}:{q_idx}"),
                        {"time": as_, "rule": "qa_answer_zh_overflow", "detail": f"{oid}[{q_idx}] aZh overflows green card: '{a_zh}'"},
                    )

    # Full timeline sweep
    t = 0.0
    while t <= duration + 1e-6:
        active_cue = next((c for c in cues if float(c.get("start", 0.0)) <= t < float(c.get("end", 0.0))), None)
        chapter_box = RectBox("ChapterPill", "chrome_chapter", 48.0, 24.0, 320.0, 48.0)
        hint_box = build_study_hint_box(active_cue) if active_cue else None
        has_note = hint_box is not None
        sub_box = build_subtitle_box(active_cue) if active_cue else None

        if hint_box and hint_box.intersects(chapter_box, pad=2.0):
            record(
                ("hint_vs_chapter", str(round(t, 1))),
                {"time": round(t, 2), "rule": "hint_vs_chapter", "detail": "StudyHint overlaps ChapterPill"},
            )

        active_boxes: list[RectBox] = []
        for h in huds:
            if float(h.get("start", 0.0)) <= t <= float(h.get("end", 0.0)):
                active_boxes.extend(hud_boxes_for_item(h, has_note))
        for ov in overlays:
            if float(ov.get("start", 0.0)) <= t <= float(ov.get("end", 0.0)):
                active_boxes.extend(overlay_boxes_for_item(ov, has_note))

        for box in active_boxes:
            if box.x < 0 or box.y < 0 or box.x2 > WIDTH or box.y2 > HEIGHT:
                record(
                    ("bounds", box.tag),
                    {"time": round(t, 2), "rule": "out_of_bounds", "detail": f"{box.tag} ({box.x:.0f},{box.y:.0f}..{box.x2:.0f},{box.y2:.0f}) outside 1920x1080"},
                )
            if hint_box and box.intersects(hint_box, pad=4.0):
                record(
                    ("hint_vs_card", box.tag),
                    {"time": round(t, 2), "rule": "hint_vs_overlay", "detail": f"{box.tag} (y={box.y:.0f}..{box.y2:.0f}) overlaps StudyHint (y={hint_box.y:.0f}..{hint_box.y2:.0f})"},
                )
            if sub_box and box.y2 > sub_box.y - 6.0 and box.intersects(sub_box, pad=2.0):
                record(
                    ("card_vs_sub", box.tag),
                    {"time": round(t, 2), "rule": "overlay_vs_subtitle", "detail": f"{box.tag} (y2={box.y2:.0f}) invades {sub_box.tag} (y={sub_box.y:.0f})"},
                )
            elif box.y2 > SUBTITLE_SAFE_Y and box.kind != "hud:metric_climb":
                record(
                    ("safe_y", box.tag),
                    {"time": round(t, 2), "rule": "subtitle_lane_intrusion", "detail": f"{box.tag} bottom ({box.y2:.0f}) exceeds safe ceiling ({SUBTITLE_SAFE_Y:.0f})"},
                )

        # Pairwise collision between simultaneous overlays/HUDs (excluding sibling sub-boxes of same item)
        for i in range(len(active_boxes)):
            for j in range(i + 1, len(active_boxes)):
                a, b = active_boxes[i], active_boxes[j]
                if a.tag.split(":")[0] == b.tag.split(":")[0]:
                    continue
                if a.intersects(b, pad=6.0):
                    pair_id = tuple(sorted([a.tag, b.tag]))
                    record(
                        ("pair", f"{pair_id[0]}|{pair_id[1]}"),
                        {"time": round(t, 2), "rule": "card_collision", "detail": f"{a.tag} collides with {b.tag}"},
                    )

        t += step_sec

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-render timeline layout & collision audit for remotion-study-video")
    parser.add_argument("--project", default="src/data/project.json", help="Path to project.json (default: src/data/project.json)")
    parser.add_argument("--step", type=float, default=0.25, help="Sweep step in seconds (default: 0.25)")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    if not project_path.exists():
        print(f"[ERROR] project.json not found: {project_path}", file=sys.stderr)
        return 1

    data = json.loads(project_path.read_text(encoding="utf-8"))
    issues = audit_project(data, step_sec=args.step)

    if args.json:
        print(json.dumps({"project": str(project_path), "issueCount": len(issues), "issues": issues}, ensure_ascii=False, indent=2))
    else:
        dur = float((data.get("meta") or {}).get("durationInSeconds", 0.0))
        if not issues:
            print(f"✓ Layout audit PASSED ({project_path.name}, 0..{dur:.2f}s @ {args.step}s steps, 0 issues)")
        else:
            print(f"✗ Layout audit FAILED ({len(issues)} issue(s) found in {project_path.name}):")
            for item in issues:
                print(f"  [{item['time']:6.2f}s] {item['rule']}: {item['detail']}")

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
