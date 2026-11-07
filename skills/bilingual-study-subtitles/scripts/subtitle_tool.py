#!/usr/bin/env python3
"""Build styled bilingual subtitles from reviewed timings; burn ordinary SDR video."""
import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
import unicodedata
from fractions import Fraction
from pathlib import Path

import pysubs2

ROOT = Path(__file__).resolve().parents[1]
COLORS = ('en_color', 'zh_color', 'highlight_color', 'hint_color', 'outline_color', 'hint_background')
RATIOS = ('en_size_ratio', 'zh_size_ratio', 'hint_size_ratio', 'bottom_margin_ratio', 'top_margin_ratio', 'side_margin_ratio')


def run(argv, **kwargs):
    return subprocess.run([str(a) for a in argv], check=True, **kwargs)


def probe(path, executable):
    data = json.loads(run([executable, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path], capture_output=True, text=True).stdout)
    videos = [s for s in data['streams'] if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')]
    if len(videos) != 1:
        raise ValueError('Expected one video stream; select the intended stream before using this helper.')
    v = videos[0]
    duration = float(v.get('duration', data['format'].get('duration', 0)))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Video duration is missing or invalid.')
    return data, v, duration


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError(f'Color must be #RRGGBB: {value!r}')
    return pysubs2.Color(*[int(value[i:i+2], 16) for i in (1, 3, 5)])


def tag_color(value):
    c = color(value)
    return f'&H{c.b:02X}{c.g:02X}{c.r:02X}&'


def literal(s):
    # Keep arbitrary manuscript text out of the ASS override language.
    return s.replace('\\', '＼').replace('{', '｛').replace('}', '｝')


def normal(s):
    return ' '.join(s.split())


def wrapped(text, columns):
    """Return source spans, retaining character positions for phrase highlighting."""
    tokens = list(re.finditer(r'[\u2e80-\uffff]|[^\s\u2e80-\uffff]+|\s+', text))
    start = 0
    used = 0
    for t in tokens:
        weight = sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in t.group())
        if used and used + weight > columns and t.group() not in '，。！？；、）】”':
            a, b = start, t.start()
            while a < b and text[a].isspace(): a += 1
            while b > a and text[b-1].isspace(): b -= 1
            if a < b: yield a, b
            start = t.start()
            used = 0
        used += weight
    a, b = start, len(text)
    while a < b and text[a].isspace(): a += 1
    while b > a and text[b-1].isspace(): b -= 1
    if a < b: yield a, b


def styled_text(text, columns, terms, base, highlight):
    text = normal(text)
    if not isinstance(terms, list) or not all(isinstance(t, str) and t.strip() for t in terms):
        raise ValueError('Highlight terms must be a list of nonempty strings.')
    spans = []
    for term in terms:
        term = normal(term)
        pattern = re.escape(term)
        if re.match(r'[A-Za-z0-9]', term): pattern = r'(?<![A-Za-z0-9])' + pattern
        if re.search(r'[A-Za-z0-9]$', term): pattern += r'(?![A-Za-z0-9])'
        spans.extend((m.start(), m.end()) for m in re.finditer(pattern, text, re.I))
    lines = []
    for a, b in wrapped(text, columns):
        points = sorted({a, b} | {max(a, min(b, x)) for pair in spans for x in pair})
        parts = []
        for left, right in zip(points, points[1:]):
            chunk = literal(text[left:right])
            if any(s <= left < e for s, e in spans):
                chunk = '{\\c' + tag_color(highlight) + r'\b1}' + chunk + '{\\c' + tag_color(base) + r'\b0}'
            parts.append(chunk)
        lines.append(''.join(parts))
    return r'\N'.join(lines)


def load_style(args):
    style = json.loads((ROOT / 'assets/style.example.json').read_text())
    style.update(json.loads((ROOT / 'assets/themes.json').read_text())[args.preset])
    if args.style:
        overrides = json.loads(Path(args.style).read_text())
        if not isinstance(overrides, dict) or set(overrides) - set(style):
            raise ValueError('Unknown style keys; see style.example.json.')
        style.update(overrides)
    for key in COLORS + ('font_en', 'font_zh'):
        value = getattr(args, key, None)
        if value is not None: style[key] = value
    for key in COLORS: color(style[key])
    if len({style[k].upper() for k in COLORS[:3]}) != 3:
        raise ValueError('English, Chinese and highlight colors must be distinct.')
    for key in RATIOS:
        value = style[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.005 <= value <= 0.2:
            raise ValueError(f'Invalid proportional size or margin: {key}')
    for key in ('font_en', 'font_zh'):
        if not isinstance(style[key], str) or not style[key].strip() or re.search(r'[,{}\\\n\r]', style[key]):
            raise ValueError(f'Invalid font family: {key}')
    return style


def build(args):
    _, video, duration = probe(args.video, args.ffprobe)
    cues = json.loads(Path(args.timeline).read_text())
    if not isinstance(cues, list) or not cues: raise ValueError('Timeline must be a nonempty list.')
    style = load_style(args)
    width, height = video['width'], video['height']
    end_ms = round(duration * 100) * 10
    starts = []
    for cue in cues:
        value = cue.get('start')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Every cue needs a finite nonnegative start in seconds.')
        starts.append(round(value * 100) * 10)
        for key in ('en', 'zh'):
            if not isinstance(cue.get(key), str) or not cue[key].strip(): raise ValueError(f'Empty {key} text.')
        notes = cue.get('notes', [])
        if not isinstance(notes, list) or not all(isinstance(n, str) and n.strip() for n in notes): raise ValueError('notes must be a string list.')
    ends = starts[1:] + [end_ms]
    if any(a >= b for a, b in zip(starts, ends)):
        raise ValueError('Starts must increase strictly after centisecond rounding and precede video end.')
    prefix = Path(args.out_prefix).resolve()
    paths = {ext: Path(str(prefix) + '.' + ext) for ext in ('ass', 'srt', 'style.json', 'validation.json')}
    if any(p.exists() for p in paths.values()): raise FileExistsError('Output exists; use a new prefix.')
    ass = pysubs2.SSAFile()
    ass.info.update({'Title': literal(prefix.name), 'PlayResX': str(width), 'PlayResY': str(height), 'WrapStyle': '2', 'ScaledBorderAndShadow': 'yes'})
    en_size = round(height * style['en_size_ratio'], 2)
    zh_size = round(height * style['zh_size_ratio'], 2)
    hint_size = round(height * style['hint_size_ratio'], 2)
    side = round(width * style['side_margin_ratio'])
    ass.styles['Default'] = pysubs2.SSAStyle(fontname=style['font_en'], fontsize=en_size, primarycolor=color(style['en_color']), outlinecolor=color(style['outline_color']), outline=max(1, height * .003), shadow=height * .001, alignment=2, marginl=side, marginr=side, marginv=round(height * style['bottom_margin_ratio']))
    ass.styles['Hint'] = pysubs2.SSAStyle(fontname=style['font_zh'], fontsize=hint_size, primarycolor=color(style['hint_color']), outlinecolor=color(style['hint_background']), backcolor=color(style['hint_background']), bold=True, borderstyle=3, outline=max(2, height * .004), shadow=0, alignment=8, marginl=side, marginr=side, marginv=round(height * style['top_margin_ratio']))
    plain = pysubs2.SSAFile()
    hints = 0
    for cue, start, end in zip(cues, starts, ends):
        en = styled_text(cue['en'], max(10, int((width - 2*side) / (en_size * .57))), cue.get('highlight_en', []), style['en_color'], style['highlight_color'])
        zh = styled_text(cue['zh'], max(10, int((width - 2*side) / (zh_size * .52))), cue.get('highlight_zh', []), style['zh_color'], style['highlight_color'])
        text = en + r'\N{\fn' + style['font_zh'] + '\\fs' + str(zh_size) + '\\c' + tag_color(style['zh_color']) + r'\b0}' + zh
        ass.events.append(pysubs2.SSAEvent(start=start, end=end, text=text))
        plain.events.append(pysubs2.SSAEvent(start=start, end=end, text=normal(cue['en']) + r'\N' + normal(cue['zh'])))
        if cue.get('notes'):
            note = styled_text('  '.join(cue['notes']), max(10, int((width - 2*side) / (hint_size * .55))), [], style['hint_color'], style['highlight_color'])
            ass.events.append(pysubs2.SSAEvent(start=start, end=end, text=note, style='Hint', layer=1))
            hints += 1
    prefix.parent.mkdir(parents=True, exist_ok=True)
    ass.save(str(paths['ass']))
    plain.save(str(paths['srt']))
    main = [e for e in pysubs2.load(str(paths['ass'])) if e.style == 'Default']
    if len(main) != len(cues) or any(a.end != b.start for a, b in zip(main, main[1:])):
        raise ValueError('Export verification failed.')
    report = {'cues': len(cues), 'hint_events': hints, 'width': width, 'height': height, 'duration_seconds': duration, 'continuous': True, 'first_start_ms': starts[0], 'last_end_ms': end_ms, 'preset': args.preset, 'short_cues_under_1s': [i+1 for i,(a,b) in enumerate(zip(starts,ends)) if b-a<1000], 'review': 'Timing is supplied by caller; alignment accuracy and visual layout require review.'}
    paths['style.json'].write_text(json.dumps(style, ensure_ascii=False, indent=2) + '\n')
    paths['validation.json'].write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


def burn(args):
    args.ffmpeg = str(Path(shutil.which(args.ffmpeg) or args.ffmpeg).resolve())
    source = Path(args.video).resolve()
    output = Path(args.output).resolve()
    ass_path = Path(args.ass).resolve()
    if output.exists() or output == source: raise FileExistsError('Use a new output path.')
    data, video, duration = probe(source, args.ffprobe)
    rotation = float(video.get('tags', {}).get('rotate', 0))
    rotation = next((float(s['rotation']) for s in video.get('side_data_list', []) if 'rotation' in s), rotation)
    if rotation % 360:
        raise ValueError('Rotated video needs a tailored filter plan; see SKILL.md.')
    if video.get('color_transfer') in ('smpte2084', 'arib-std-b67') or video.get('color_primaries') == 'bt2020':
        raise ValueError('HDR/wide-gamut video needs a color-preserving encoding plan; see SKILL.md.')
    if abs(float(video.get('start_time', 0))) > .1:
        raise ValueError('Nonzero video start needs explicit audio/video timestamp handling.')
    loaded = pysubs2.load(str(ass_path))
    if (int(loaded.info.get('PlayResX', 0)), int(loaded.info.get('PlayResY', 0))) != (video['width'], video['height']):
        raise ValueError('ASS canvas must match source resolution. Rebuild for this video.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bilingual-burn-') as temp:
        shutil.copyfile(ass_path, Path(temp) / 'subtitles.ass')
        command = [args.ffmpeg, '-hide_banner', '-nostdin', '-n', '-i', source, '-map', f"0:{video['index']}", '-map', '0:a?', '-map_metadata', '0', '-map_chapters', '0', '-vf', 'ass=subtitles.ass', '-c:v', 'libx264', '-crf', str(args.crf), '-preset', 'medium', '-c:a', args.audio_codec, '-fps_mode', 'passthrough']
        if output.suffix.lower() in ('.mp4', '.mov'): command += ['-movflags', '+faststart']
        command.append(output)
        run(command, cwd=temp)
    result, encoded, out_duration = probe(output, args.ffprobe)
    if (encoded['width'], encoded['height']) != (video['width'], video['height']): raise ValueError('Output resolution changed.')
    source_sar = video.get('sample_aspect_ratio', '1:1')
    target_sar = encoded.get('sample_aspect_ratio', '1:1')
    if source_sar not in ('N/A', '0:1') and Fraction(source_sar.replace(':', '/')) != Fraction(target_sar.replace(':', '/')):
        raise ValueError('Output sample aspect ratio changed.')
    if abs(duration - out_duration) > .15: raise ValueError('Output duration changed unexpectedly.')
    if sum(s['codec_type']=='audio' for s in result['streams']) != sum(s['codec_type']=='audio' for s in data['streams']): raise ValueError('Audio stream count changed.')
    # Full decode, including all audio tracks; any decode failure is reported.
    run([args.ffmpeg, '-v', 'error', '-xerror', '-i', output, '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'])
    print(json.dumps({'output': str(output), 'width': encoded['width'], 'height': encoded['height'], 'duration_seconds': out_duration, 'sample_aspect_ratio': target_sar, 'full_decode': 'passed'}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('build', help='Export ASS/SRT from a reviewed aligned JSON timeline.')
    p.add_argument('--video', required=True)
    p.add_argument('--timeline', required=True)
    p.add_argument('--out-prefix', required=True)
    p.add_argument('--ffprobe', default='ffprobe')
    p.add_argument('--preset', choices=('classic', 'soft', 'contrast'), default='classic')
    p.add_argument('--style', help='Partial style JSON overrides.')
    for key in COLORS + ('font_en', 'font_zh'): p.add_argument('--' + key.replace('_', '-'))
    p.set_defaults(action=build)
    p = subs.add_parser('burn', help='Burn ASS into an ordinary SDR video without scaling.')
    for arg in ('video', 'ass', 'output'): p.add_argument('--'+arg, required=True)
    p.add_argument('--ffprobe', default='ffprobe')
    p.add_argument('--ffmpeg', default='ffmpeg')
    p.add_argument('--audio-codec', default='copy')
    p.add_argument('--crf', type=int, choices=range(0,52), default=20, metavar='0..51')
    p.set_defaults(action=burn)
    args = parser.parse_args()
    try:
        args.action(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
