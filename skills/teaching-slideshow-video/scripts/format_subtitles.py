"""Apply the 1080p teaching subtitle preset."""
import argparse
import json
from functools import lru_cache
from pathlib import Path
import re
import subprocess
import tempfile

from PIL import Image
import pysubs2 as ass


def compact(note):
    # Older ASS files may carry a display break in the middle of a Chinese word.
    return re.sub(r'(?<=[A-Za-z0-9])\\N(?=[A-Za-z0-9])', ' ', note).replace(r'\N', '').strip()


def approved_notes(build):
    timeline = build / 'timeline.json'
    layout = build / '顶部提示分行.json'
    if not timeline.exists():
        if layout.exists():
            raise ValueError('核对顶部提示分行需要同目录的 timeline.json。')
        return {}
    cues = json.loads(timeline.read_text(encoding='utf-8'))
    reviewed = {}
    if layout.exists():
        for row in json.loads(layout.read_text(encoding='utf-8')):
            index, lines = row['条目'], row['显示行']
            if (type(index) is not int or not 1 <= index <= len(cues) or index in reviewed
                    or not isinstance(lines, list) or not 1 <= len(lines) <= 3
                    or not all(isinstance(line, str) and line and line == ' '.join(line.split())
                               and line[0] not in '。，、！？；：）】”’' for line in lines)):
                raise ValueError(f'请核对顶部提示分行的条目和显示行：{index}')
            pattern = ' ?'.join(re.escape(line) for line in lines)
            if not re.fullmatch(pattern, ' '.join(cues[index-1].get('notes', []))):
                raise ValueError(f'第 {index} 条提示已改稿，请更新对应的显示行。')
            reviewed[index] = lines

    escape = str.maketrans('\\{}', '＼｛｝')
    notes = {}
    for index, cue in enumerate(cues, 1):
        if cue.get('notes'):
            # Use the same whitespace handling and ASS escaping as the base writer.
            parts = [' '.join(part.split()).translate(escape) for part in cue['notes']]
            lines = [line.translate(escape) for line in reviewed.get(index, [])]
            notes[round(cue['start'] * 100)] = parts, lines
    return notes


def meaning_chunks(parts, allow_comma=False):
    # An authored note boundary always separates complete teaching points.
    pairs = {'“': '”', '‘': '’', '（': '）', '(': ')', '【': '】', '《': '》', '"': '"'}
    chunks = []
    for part in parts:
        start = 0
        closing = []
        for i, char in enumerate(part):
            if closing and char == closing[-1]:
                closing.pop()
            elif char in pairs:
                closing.append(pairs[char])
            elif not closing and char in ('。！？；;' + ('，' if allow_comma else '')):
                if i + 1 < len(part) and part[i + 1] in '。！？；，、：!?;,.…':
                    continue
                chunks.append(part[start:i+1])
                start = i+1
        if start < len(part):
            chunks.append(part[start:])
        if chunks:
            chunks[-1] += ' '
    return chunks


def fit_hint(parts, font_size, fits, reviewed_lines=()):
    full = ' '.join(parts)
    minimum = round(font_size * .76)
    for size in [*range(font_size, minimum, -2), minimum]:
        if reviewed_lines:
            if all(fits(line, size) for line in reviewed_lines):
                return reviewed_lines, size
            continue
        if fits(full, size):
            return [full], size
        for allow_comma in (False, True):
            lines = []
            current = ''
            for chunk in meaning_chunks(parts, allow_comma):
                combined = current + chunk
                if fits(combined.strip(), size):
                    current = combined
                elif current and fits(chunk.strip(), size):
                    lines.append(current.strip())
                    current = chunk
                else:
                    break
            else:
                if current and len(lines) < 3:
                    return lines + [current.strip()], size
    raise ValueError('请将提示按意思分成短句或多个 notes 项，再生成字幕：' + full)


def lettering(note, english_font, chinese_font):
    # Only language terms take the accent. Explanatory text stays white.
    chunks = re.split(r"([A-Za-z0-9][A-Za-z0-9.,’'-]*(?: [A-Za-z0-9][A-Za-z0-9.,’'-]*)*)", note)
    styles = [rf'{{\fn{chinese_font}\1c&HFFFFFF&}}', rf'{{\fn{english_font}\1c&H1C53FD&}}']
    return ''.join(styles[i % 2] + chunk for i, chunk in enumerate(chunks) if chunk)


def rounded_box(w, h, r):
    return (f'm {r} 0 l {w-r} 0 b {w-8} 0 {w} 8 {w} {r} l {w} {h-r} '
            f'b {w} {h-8} {w-8} {h} {w-r} {h} l {r} {h} b 8 {h} 0 {h-8} 0 {h-r} '
            f'l 0 {r} b 0 8 8 0 {r} 0')


def style_hints(doc, ffmpeg, english_font, chinese_font, source_notes=None):
    width, height = int(doc.info['PlayResX']), int(doc.info['PlayResY'])
    top = round(height * .10)
    hints = [e for e in doc if e.style == 'Hint']
    if not hints:
        return
    scale = height / 1080
    font_size = round(49 * scale)
    pad_x, pad_y = round(50 * scale), round(20 * scale)
    style = ass.SSAStyle(fontname=english_font, fontsize=font_size, alignment=7, outline=0, shadow=0, bold=True)
    doc.styles['StudyHintLabel'] = style
    doc.styles['StudyHintPlate'] = style.copy()
    probe = ass.SSAFile()
    probe.info.update(doc.info)
    probe.styles['StudyHintLabel'] = style

    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)

        @lru_cache(maxsize=None)
        def ink(text, size):
            probe.events = [ass.SSAEvent(start=0, end=1000, style='StudyHintLabel',
                           text=rf'{{\an7\q2\pos(0,0)\fs{size}}}'+text)]
            probe.save(str(work/'ink.ass'))
            # Use the same libass font shaping as the MP4 for centring and sizing.
            subprocess.run([ffmpeg, '-v','error','-y','-f','lavfi','-i',
                f'color=black:s={width}x{height}', '-vf','ass=ink.ass','-frames:v','1','ink.png'],
                cwd=work, check=True)
            with Image.open(work/'ink.png') as pic:
                box = pic.convert('L').point(lambda p: 255 if p > 40 else 0).getbbox()
            if not box:
                raise ValueError('Empty note: '+text)
            return box

        def fits(line, size):
            left, _, right, _ = ink(lettering(line, english_font, chinese_font), size)
            return right - left + 2 * pad_x <= width * .90

        for cue in hints:
            plain = compact(cue.text)
            parts, reviewed_lines = (source_notes or {}).get(cue.start // 10, ([], []))
            # A manually edited ASS hint takes precedence over a stale timeline.
            if not parts or ''.join(''.join(parts).split()) != ''.join(plain.split()):
                if reviewed_lines:
                    raise ValueError(f'请核对 {cue.start / 1000:.2f}s 的基础字幕与已审核提示。')
                parts = [plain]
            try:
                lines, size = fit_hint(parts, font_size, fits, reviewed_lines)
            except ValueError as exc:
                raise ValueError(f'{cue.start / 1000:.2f}s: {exc}') from exc
            text = r'\N'.join(lettering(line, english_font, chinese_font) for line in lines)
            l,t,r,b = ink(text, size)
            w,h = r-l+2*pad_x,b-t+2*pad_y
            x,y=(width-w)//2,top
            plate = cue.copy()
            plate.style='StudyHintPlate'
            plate.text=rf'{{\an7\pos({x},{y})\p1\bord0\shad0\1c&H050505&\1a&H66&}}'+rounded_box(w,h,round(27*scale))
            doc.events.append(plate)
            cue.style='StudyHintLabel'
            cue.layer+=1
            cue.text=rf'{{\an7\q2\pos({x+pad_x-l},{y+pad_y-t})\fs{size}\bord0\shad0\b1}}'+text


def gradient(doc, top, solid, opacity, start, end):
    width = int(doc.info['PlayResX'])
    height = int(doc.info['PlayResY'])
    first = top
    previous = 0
    for y in range(top, height + 1):
        fraction = min(1, (y - top) / (solid - top))
        alpha = round(255 * opacity * fraction ** 2 * (3 - 2 * fraction))
        if alpha == previous and y != height:
            continue
        if previous:
            tags = r'{\an7\pos(0,0)\p1\bord0\shad0\1c&H000000&\1a&H' + f'{255-previous:02X}&}}'
            box = f'm 0 {first} l {width} {first} {width} {y} 0 {y}'
            doc.append(ass.SSAEvent(style='Backdrop', start=start, end=end, text=tags + box))
        first, previous = y, alpha


def load_subtitles(build):
    doc = ass.load(str(build / 'study.ass'))
    if (doc.info['PlayResX'], doc.info['PlayResY']) != ('1920', '1080'):
        raise ValueError('This preset is designed for a 1920x1080 teaching video.')
    english = doc.styles['Default'].fontname
    for event in doc:
        event.layer += 3
    doc.styles['Backdrop'] = ass.SSAStyle(fontname=english, alignment=7, outline=0, shadow=0)
    return doc


def save_styled_subtitles(doc, build, ffmpeg, body_start=0):
    duration = max(event.end for event in doc)
    gradient(doc, 713, 972, .26, body_start, duration)
    style_hints(doc, ffmpeg, doc.styles['Default'].fontname, doc.styles['Hint'].fontname, approved_notes(build))
    with tempfile.TemporaryDirectory(dir=build) as work:
        output = Path(work) / 'styled.ass'
        doc.save(str(output))
        output.replace(build / 'styled.ass')


def main():
    parser = argparse.ArgumentParser(description='Apply the series layout to a fresh study.ass in a 1080p build.')
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    build = args.build
    doc = load_subtitles(build)
    save_styled_subtitles(doc, build, args.ffmpeg)


if __name__ == '__main__':
    main()
