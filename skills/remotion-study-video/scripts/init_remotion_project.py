#!/usr/bin/env python3
"""
init_remotion_project.py
从上游教学视频工程（成片工程/timeline.json + scenes.json + narration.wav + 复习主题.json）
一键生成可运行的 Remotion (React + TypeScript) 视频工程。
"""
from __future__ import annotations
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path


def probe_duration(audio_path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not audio_path.exists():
        return None
    try:
        res = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        return None
    return None


def resolve_image(raw_path: str, search_dirs: list[Path]) -> Path | None:
    p = Path(raw_path)
    if p.exists():
        return p
    basename = p.name
    for d in search_dirs:
        if not d.exists():
            continue
        candidate = d / basename
        if candidate.exists():
            return candidate
    return None


def build_review_map(review_topics: list[dict], num_cues: int, cues: list[dict]) -> dict[int, str]:
    if not review_topics:
        return {}
    sorted_topics = sorted(review_topics, key=lambda x: int(x["cue"]))
    out: dict[int, str] = {}
    for idx, item in enumerate(sorted_topics):
        start_cue = int(item["cue"])
        topic = str(item["topic"]).strip()
        next_cue = int(sorted_topics[idx + 1]["cue"]) if idx + 1 < len(sorted_topics) else num_cues
        for c_idx in range(start_cue, min(next_cue, num_cues)):
            en_text = cues[c_idx].get("en", "")
            if c_idx == num_cues - 1 and "thanks for exploring" in en_text.lower():
                continue
            out[c_idx] = topic
    return out


ASS_TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{2})")
ASS_TAG_RE = re.compile(r"(\{[^}]*\})")


def parse_ass_time(ts: str) -> float:
    """Parse H:MM:SS.cc timestamp from an ASS Dialogue row into seconds."""
    m = ASS_TIME_RE.match(ts.strip())
    if not m:
        return 0.0
    h, mnt, s, cs = map(int, m.groups())
    return h * 3600 + mnt * 60 + s + cs / 100.0


def _append_segment(segments: list[dict], text: str, highlight: bool) -> None:
    if not text:
        return
    if segments and bool(segments[-1].get("highlight")) == highlight:
        segments[-1]["text"] += text
    else:
        segments.append({"text": text, "highlight": highlight})


def ass_inline_to_segment_lines(text: str, allow_breaks: bool = False) -> list[list[dict]]:
    """
    Convert ASS override tags ({\\c&H257BFF&...} / {\\c&HFFFFFF&} / {\\r})
    into structured lines of {text, highlight} segments for React rendering.
    """
    parts = ASS_TAG_RE.split(text)
    lines: list[list[dict]] = [[]]
    highlighted = False

    for p in parts:
        if not p:
            continue
        if p.startswith("{") and p.endswith("}"):
            up = p.upper()
            is_base_reset = ("\\R" in up) or ("FFFFFF" in up) or ("00BCFF" in up)
            is_color = ("\\C&H" in up) or ("\\1C&H" in up)
            if is_base_reset:
                highlighted = False
            elif is_color:
                highlighted = True
            continue

        normalized = p.replace("\\n", "\\N")
        if allow_breaks:
            chunks = normalized.split("\\N")
            for i, chunk in enumerate(chunks):
                if i > 0:
                    lines.append([])
                cleaned = re.sub(r"  +", " ", chunk)
                _append_segment(lines[-1], cleaned, highlighted)
        else:
            cleaned = re.sub(r"  +", " ", normalized.replace("\\N", " "))
            _append_segment(lines[-1], cleaned, highlighted)

    cleaned_lines: list[list[dict]] = []
    for line in lines:
        if not line:
            continue
        line[0]["text"] = line[0]["text"].lstrip()
        line[-1]["text"] = line[-1]["text"].rstrip()
        line = [seg for seg in line if seg["text"]]
        if line:
            cleaned_lines.append(line)
    return cleaned_lines


def split_ass_bilingual(text: str) -> tuple[str, str]:
    """Split a Default ASS line into (en_raw, zh_raw), keeping multi-line wrapped EN together."""
    zh_marker = re.search(r"\\N(\{[^}]*00BCFF[^}]*\})", text, re.IGNORECASE)
    if zh_marker:
        idx = zh_marker.start()
        return text[:idx], text[idx + 2:]
    parts = text.split("\\N")
    for i, part in enumerate(parts):
        if i > 0 and re.search(r"[\u4e00-\u9fff]", part):
            return " ".join(parts[:i]), "\\N".join(parts[i:])
    if len(parts) >= 2:
        return parts[0], "\\N".join(parts[1:])
    return text, ""


def parse_styled_ass(ass_path: Path) -> tuple[list[dict], list[dict]]:
    """Extract Default bilingual cues and StudyHintLabel cues from styled.ass."""
    defaults: list[dict] = []
    hints: list[dict] = []
    for raw in ass_path.read_text(encoding="utf-8").splitlines():
        if not raw.startswith("Dialogue:"):
            continue
        fields = raw[len("Dialogue:"):].strip().split(",", 9)
        if len(fields) < 10:
            continue
        start = parse_ass_time(fields[1])
        end = parse_ass_time(fields[2])
        style = fields[3].strip()
        text = fields[9].strip()
        if style == "Default":
            en_raw, zh_raw = split_ass_bilingual(text)
            en_segs = (ass_inline_to_segment_lines(en_raw, allow_breaks=False) or [[]])[0]
            zh_segs = (ass_inline_to_segment_lines(zh_raw, allow_breaks=False) or [[]])[0]
            defaults.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "en": "".join(s["text"] for s in en_segs),
                "zh": "".join(s["text"] for s in zh_segs),
                "richEn": en_segs,
                "richZh": zh_segs,
            })
        elif style == "StudyHintLabel":
            note_lines = ass_inline_to_segment_lines(text, allow_breaks=True)
            hints.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "notes": ["".join(s["text"] for s in line) for line in note_lines],
                "richNotes": note_lines,
            })
    return defaults, hints


def apply_ass_to_cues(
    cues_out: list[dict],
    ass_path: Path,
    total_duration: float,
) -> list[dict]:
    """
    Merge parsed styled.ass cues & StudyHintLabel highlights into project cues.
    Uses ASS timing as ground truth when Default dialogue rows exist while inheriting
    chapter/notes/reviewTopic metadata from overlapping timeline cues.
    """
    defaults, hints = parse_styled_ass(ass_path)
    if not defaults and not hints:
        return cues_out

    def find_base_cue(t_mid: float) -> dict | None:
        for c in cues_out:
            if float(c.get("start", 0.0)) - 0.05 <= t_mid <= float(c.get("end", 0.0)) + 0.05:
                return c
        return cues_out[-1] if cues_out else None

    def find_hint(t_mid: float) -> dict | None:
        for h in hints:
            if h["start"] - 0.1 <= t_mid <= h["end"] + 0.1:
                return h
        return None

    if defaults:
        merged: list[dict] = []
        filtered = [d for d in defaults if d["start"] < total_duration]
        for idx, d in enumerate(filtered):
            t_mid = (d["start"] + d["end"]) / 2.0
            base = find_base_cue(t_mid) or {}
            hint = find_hint(t_mid)
            cue_end = min(float(d["end"]), total_duration)
            cue_item = {
                "index": idx,
                "en": d["en"],
                "zh": d["zh"],
                "start": d["start"],
                "speechEnd": min(float(base.get("speechEnd", cue_end)), cue_end),
                "end": cue_end,
                "notes": hint["notes"] if hint else base.get("notes", []),
                "highlightEn": base.get("highlightEn", []),
                "highlightZh": base.get("highlightZh", []),
                "richEn": d["richEn"],
                "richZh": d["richZh"],
                "reviewTopic": base.get("reviewTopic"),
            }
            if base.get("chapter"):
                cue_item["chapter"] = base["chapter"]
            if hint:
                cue_item["richNotes"] = hint["richNotes"]
            merged.append(cue_item)
        return merged

    # Only StudyHintLabel rows existed: enrich existing timeline cues by midpoint
    for cue in cues_out:
        t_mid = (float(cue["start"]) + float(cue["end"])) / 2.0
        hint = find_hint(t_mid)
        if hint:
            cue["notes"] = hint["notes"]
            cue["richNotes"] = hint["richNotes"]
    return cues_out


def find_episode_ass(build_dir: Path | None) -> Path | None:
    """Locate styled.ass or renamed final <num> <name>.ass inside 成片工程/."""
    if not build_dir or not build_dir.exists():
        return None
    direct = build_dir / "styled.ass"
    if direct.exists():
        return direct
    ignored = {"study.ass", "render.ass"}
    candidates = sorted(p for p in build_dir.glob("*.ass") if p.name not in ignored)
    return candidates[0] if candidates else None


def load_lesson_cues(episode_dir: Path | None) -> tuple[list[dict], list[dict]]:
    """Load (cues, scenes) metadata from episode_dir/lesson.json or 分镜.json."""
    if not episode_dir or not episode_dir.exists():
        return [], []
    lesson_path = episode_dir / "lesson.json"
    lesson_data = json.loads(lesson_path.read_text(encoding="utf-8")) if lesson_path.exists() else {}
    lesson_cues = lesson_data.get("cues") or []
    lesson_scenes = lesson_data.get("scenes") or []
    storyboard_path = episode_dir / "分镜.json"
    if not lesson_scenes and storyboard_path.exists():
        sb = json.loads(storyboard_path.read_text(encoding="utf-8"))
        lesson_scenes = sb.get("scenes", sb) if isinstance(sb, dict) else sb
    return lesson_cues, lesson_scenes


def reconstruct_scenes(scene_defs: list[dict], timeline_raw: list[dict], fallback_end: float) -> list[dict]:
    """Rebuild timed scenes list from lesson.json/分镜.json + timeline.json when scenes.json was cleaned."""
    if not scene_defs or not timeline_raw:
        return []
    rebuilt: list[dict] = []
    for idx, sc in enumerate(scene_defs):
        cue_idx = max(0, min(len(timeline_raw) - 1, int(sc.get("cue", 0))))
        start_t = 0.0 if idx == 0 else float(timeline_raw[cue_idx].get("start", 0.0))
        if idx + 1 < len(scene_defs):
            next_idx = max(0, min(len(timeline_raw) - 1, int(scene_defs[idx + 1].get("cue", cue_idx + 1))))
            end_t = float(timeline_raw[next_idx].get("start", start_t + 3.0))
        else:
            last_speech = float(timeline_raw[-1].get("speech_end", timeline_raw[-1].get("start", start_t)))
            end_t = max(fallback_end, last_speech + 1.5, start_t + 2.0)
        rebuilt.append({
            "image": sc.get("image", ""),
            "title": sc.get("title", Path(str(sc.get("image", ""))).stem or f"Scene {idx + 1}"),
            "start": round(start_t, 2),
            "end": round(max(end_t, start_t + 0.5), 2),
        })
    return rebuilt


def synthesize_narration_from_cues(
    episode_dir: Path,
    lesson_cues: list[dict],
    timeline_raw: list[dict],
    out_wav: Path,
    max_seconds: float | None = None,
) -> bool:
    """
    Reconstruct timed narration.wav from episode_dir/配音/*.wav + timeline.json
    when 成片工程/narration.wav was pruned per country-study-video slim spec.
    """
    if not lesson_cues or not timeline_raw:
        return False
    clips: list[tuple[float, Path]] = []
    for idx, tc in enumerate(timeline_raw):
        if max_seconds and float(tc.get("start", 0.0)) >= max_seconds:
            break
        lc = lesson_cues[idx] if idx < len(lesson_cues) else {}
        rel_audio = lc.get("audio")
        if not rel_audio:
            continue
        wav_path = (episode_dir / str(rel_audio)).resolve()
        if wav_path.exists():
            clips.append((float(tc.get("start", 0.0)), wav_path))
    if not clips:
        return False

    try:
        with wave.open(str(clips[0][1]), "rb") as w0:
            nchannels, sampwidth, framerate, _, _, _ = w0.getparams()
        frame_bytes = nchannels * sampwidth
        written_frames = 0
        max_frames = int(max_seconds * framerate) if max_seconds else None

        with wave.open(str(out_wav), "wb") as out_w:
            out_w.setnchannels(nchannels)
            out_w.setsampwidth(sampwidth)
            out_w.setframerate(framerate)
            for start_t, wav_p in clips:
                with wave.open(str(wav_p), "rb") as cw:
                    if cw.getnchannels() != nchannels or cw.getsampwidth() != sampwidth or cw.getframerate() != framerate:
                        return False
                    pcm = cw.readframes(cw.getnframes())
                target_frame = int(round(start_t * framerate))
                if target_frame > written_frames:
                    pad_frames = target_frame - written_frames
                    if max_frames is not None:
                        pad_frames = min(pad_frames, max(0, max_frames - written_frames))
                    if pad_frames > 0:
                        out_w.writeframes(b"\x00" * (pad_frames * frame_bytes))
                        written_frames += pad_frames
                if max_frames is not None and written_frames >= max_frames:
                    break
                if max_frames is not None:
                    keep_frames = min(len(pcm) // frame_bytes, max_frames - written_frames)
                    pcm = pcm[: keep_frames * frame_bytes]
                out_w.writeframes(pcm)
                written_frames += len(pcm) // frame_bytes
            # Pad small trailing breath if total_end exceeds last clip
            if max_frames is None:
                out_w.writeframes(b"\x00" * (int(1.2 * framerate) * frame_bytes))
        return out_wav.exists() and out_wav.stat().st_size > 100
    except Exception:
        return False


def copy_template_tree(template_dir: Path, dest_dir: Path) -> None:
    for root, _, files in os.walk(template_dir):
        rel = Path(root).relative_to(template_dir)
        target_root = dest_dir / rel
        target_root.mkdir(parents=True, exist_ok=True)
        for fname in files:
            src_file = Path(root) / fname
            dst_file = target_root / fname
            if not dst_file.exists():
                shutil.copy2(src_file, dst_file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a Remotion bilingual study video project")
    parser.add_argument("--dest", required=True, help="Target Remotion studio directory")
    parser.add_argument("--episode-dir", help="Latest country-study-video episode directory (auto-discovers 成片工程/, lesson.json, 分镜.json, 配图/, 配音/, 复习主题.json)")
    parser.add_argument("--build-dir", help="Upstream 成片工程 directory (auto-discovers timeline.json, *.ass, scenes.json, narration.wav)")
    parser.add_argument("--timeline", help="Path to timeline.json")
    parser.add_argument("--ass", help="Optional path to styled.ass (preserves exact bilingual highlights & StudyHintLabel)")
    parser.add_argument("--scenes", help="Path to scenes.json")
    parser.add_argument("--audio", help="Path to narration audio (.wav or .mp3)")
    parser.add_argument("--images-dir", help="Fallback directory containing scene images")
    parser.add_argument("--review-topics", help="Optional path to 复习主题.json")
    parser.add_argument("--title", default="", help="Cover title (defaults to cue 0 English text)")
    parser.add_argument("--subtitle", default="Bilingual Study Video", help="Cover eyebrow subtitle")
    parser.add_argument("--fps", type=int, default=30, help="Video FPS (default: 30)")
    parser.add_argument("--max-seconds", type=float, default=None, help="Optional clip duration in seconds for 1-min sample demos")
    parser.add_argument("--install", action="store_true", help="Run npm install after scaffolding")
    args = parser.parse_args()

    dest_dir = Path(args.dest).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    episode_dir = Path(args.episode_dir).resolve() if args.episode_dir else None
    build_dir = Path(args.build_dir).resolve() if args.build_dir else (episode_dir / "成片工程" if episode_dir else None)
    if not episode_dir and build_dir:
        episode_dir = build_dir.parent

    timeline_path = Path(args.timeline).resolve() if args.timeline else (build_dir / "timeline.json" if build_dir else None)
    ass_path = Path(args.ass).resolve() if args.ass else find_episode_ass(build_dir)
    if ass_path and not ass_path.exists():
        ass_path = None
    scenes_path = Path(args.scenes).resolve() if args.scenes else (build_dir / "scenes.json" if build_dir else None)

    audio_path = Path(args.audio).resolve() if args.audio else None
    if not audio_path and build_dir:
        for cand in ["narration.wav", "narration.mp3", "narration.m4a"]:
            p = build_dir / cand
            if p.exists():
                audio_path = p
                break

    review_path = Path(args.review_topics).resolve() if args.review_topics else None
    if not review_path and episode_dir:
        cand = episode_dir / "复习主题.json"
        if cand.exists():
            review_path = cand

    search_dirs: list[Path] = []
    if args.images_dir:
        search_dirs.append(Path(args.images_dir).resolve())
    if episode_dir:
        search_dirs.extend([
            episode_dir / "配图",
            episode_dir / "images",
        ])

    if (not timeline_path or not timeline_path.exists()) and not ass_path:
        print(f"[ERROR] Neither timeline.json ({timeline_path}) nor .ass found.", file=sys.stderr)
        return 1

    timeline_raw = json.loads(timeline_path.read_text(encoding="utf-8")) if timeline_path and timeline_path.exists() else []
    lesson_cues, lesson_scenes = load_lesson_cues(episode_dir)
    if scenes_path and scenes_path.exists():
        scenes_raw = json.loads(scenes_path.read_text(encoding="utf-8"))
    elif lesson_scenes and timeline_raw:
        timing_path = build_dir / "timing.json" if build_dir else None
        fallback_dur = 0.0
        if timing_path and timing_path.exists():
            fallback_dur = float(json.loads(timing_path.read_text(encoding="utf-8")).get("duration", 0.0))
        scenes_raw = reconstruct_scenes(lesson_scenes, timeline_raw, fallback_dur)
        print(f"✓ Reconstructed {len(scenes_raw)} scenes from lesson.json/分镜.json + timeline.json")
    else:
        print(f"[ERROR] scenes.json not found ({scenes_path}) and could not reconstruct from lesson.json/分镜.json.", file=sys.stderr)
        return 1

    review_raw = json.loads(review_path.read_text(encoding="utf-8")) if review_path and review_path.exists() else []

    skill_root = Path(__file__).resolve().parent.parent
    template_dir = skill_root / "templates"
    copy_template_tree(template_dir, dest_dir)

    public_images = dest_dir / "public" / "images"
    public_audio = dest_dir / "public" / "audio"
    public_vfx = dest_dir / "public" / "vfx"
    data_dir = dest_dir / "src" / "data"
    for d in [public_images, public_audio, public_vfx, data_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Copy or slice audio
    audio_rel = ""
    audio_duration = None
    if audio_path and audio_path.exists():
        audio_ext = audio_path.suffix or ".wav"
        target_audio = public_audio / f"narration{audio_ext}"
        src_dur = probe_duration(audio_path)
        if args.max_seconds and src_dur and src_dur > args.max_seconds + 0.5:
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                fade_start = max(0.0, args.max_seconds - 0.4)
                subprocess.run(
                    [
                        ffmpeg, "-y", "-i", str(audio_path),
                        "-t", f"{args.max_seconds:.3f}",
                        "-af", f"afade=t=out:st={fade_start:.3f}:d=0.4",
                        str(target_audio),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
            else:
                shutil.copy2(audio_path, target_audio)
        else:
            shutil.copy2(audio_path, target_audio)
        audio_rel = f"audio/narration{audio_ext}"
        audio_duration = probe_duration(target_audio)
    elif episode_dir and lesson_cues and timeline_raw:
        synth_wav = public_audio / "narration.wav"
        if synthesize_narration_from_cues(episode_dir, lesson_cues, timeline_raw, synth_wav, args.max_seconds):
            audio_rel = "audio/narration.wav"
            audio_duration = probe_duration(synth_wav)
            print("✓ Synthesized narration.wav from 配音/*.wav + timeline.json")

    if ass_path and not timeline_raw:
        ass_defaults, _ = parse_styled_ass(ass_path)
        max_ass_end = max((d["end"] for d in ass_defaults), default=0.0)
    else:
        max_ass_end = 0.0

    if args.max_seconds:
        limit = args.max_seconds
        timeline_raw = [c for c in timeline_raw if float(c.get("start", 0.0)) < limit]
        scenes_raw = [s for s in scenes_raw if float(s.get("start", 0.0)) < limit]
        total_duration = min(limit, audio_duration) if audio_duration else limit
    else:
        max_scene_end = max((float(s.get("end", 0)) for s in scenes_raw), default=0.0)
        max_cue_end = max(
            max((float(c.get("speech_end", c.get("start", 0))) for c in timeline_raw), default=0.0),
            max_ass_end,
        )
        total_duration = max(audio_duration or 0.0, max_scene_end, max_cue_end + 1.5, 1.0)

    fps = args.fps
    duration_frames = int(math.ceil(total_duration * fps))

    # Resolve & copy scene images
    copied_images: dict[str, str] = {}
    scenes_out = []
    missing_images = []

    for idx, s in enumerate(scenes_raw):
        raw_img = str(s.get("image", ""))
        resolved = resolve_image(raw_img, search_dirs)
        if resolved:
            if str(resolved) not in copied_images:
                safe_name = f"scene_{len(copied_images):02d}_{resolved.name}"
                shutil.copy2(resolved, public_images / safe_name)
                copied_images[str(resolved)] = f"images/{safe_name}"
            image_rel = copied_images[str(resolved)]
        else:
            missing_images.append(raw_img)
            image_rel = f"images/{Path(raw_img).name}"

        scenes_out.append({
            "id": f"scene-{idx}",
            "title": s.get("title", f"Scene {idx + 1}"),
            "imageFile": image_rel,
            "start": float(s.get("start", 0.0)),
            "end": min(float(s.get("end", total_duration)), total_duration),
            "transition": "fade",
            "transitionDurationFrames": 18,
            "vfx": {"kind": "none"},
        })

    # Optional flag badge copy
    hud_items = []
    for d in search_dirs:
        flag_cand = d / "flag_badge.png"
        if flag_cand.exists():
            shutil.copy2(flag_cand, public_images / "flag_badge.png")
            break

    review_map = build_review_map(review_raw, len(timeline_raw), timeline_raw)
    cues_out = []
    for idx, c in enumerate(timeline_raw):
        start_t = float(c.get("start", 0.0))
        speech_end = float(c.get("speech_end", start_t + 2.0))
        next_start = float(timeline_raw[idx + 1]["start"]) if idx + 1 < len(timeline_raw) else total_duration
        cue_end = min(max(speech_end, next_start), total_duration)
        cues_out.append({
            "index": idx,
            "en": c.get("en", ""),
            "zh": c.get("zh", ""),
            "start": start_t,
            "speechEnd": speech_end,
            "end": cue_end,
            "notes": c.get("notes", []),
            "highlightEn": c.get("highlight_en", []),
            "highlightZh": c.get("highlight_zh", []),
            "reviewTopic": review_map.get(idx),
        })

    if ass_path:
        cues_out = apply_ass_to_cues(cues_out, ass_path, total_duration)
        print(f"✓ Applied styled ASS highlights & hints from: {ass_path.name}")

    cover_title = args.title.strip() or (
        cues_out[0].get("en", "Study Video") if cues_out else "Study Video"
    )
    project_json = {
        "meta": {
            "title": cover_title,
            "subtitle": args.subtitle,
            "fps": fps,
            "width": 1920,
            "height": 1080,
            "durationInSeconds": round(total_duration, 3),
            "durationInFrames": duration_frames,
            "audioFile": audio_rel,
        },
        "scenes": scenes_out,
        "cues": cues_out,
        "spotlights": [],
        "hud": hud_items,
        "overlays": [],
    }

    project_path = data_dir / "project.json"
    project_path.write_text(json.dumps(project_json, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✓ Scaffolded Remotion project at: {dest_dir}")
    print(f"✓ Wrote project data: {project_path} ({len(scenes_out)} scenes, {len(cues_out)} cues, {total_duration:.2f}s)")
    if missing_images:
        print(f"[WARN] {len(missing_images)} scene image(s) not found on disk; check paths or pass --images-dir:")
        for m in missing_images[:5]:
            print(f"  - {m}")

    if args.install:
        print("Installing npm dependencies...")
        res = subprocess.run(["npm", "install"], cwd=str(dest_dir))
        if res.returncode != 0:
            print("[ERROR] npm install failed.", file=sys.stderr)
            return res.returncode

    print("\nNext steps:")
    if not args.install:
        print(f"  1. cd \"{dest_dir}\" && npm install")
        print("  2. npm run studio         # 实时预览与拖拽时间轴")
        print("  3. npm run render:sample  # 先渲染前 15 秒样片 (0-450 帧)")
        print("  4. npm run render         # 渲染全片 out/final_remotion.mp4")
    else:
        print(f"  1. cd \"{dest_dir}\" && npm run studio")
        print("  2. npm run render:sample")
        print("  3. npm run render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
