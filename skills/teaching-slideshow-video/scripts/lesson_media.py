#!/usr/bin/env python3
"""Reusable narration, sample-based timing and still-image video composition."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def run(args, **kw):
    return subprocess.run([str(x) for x in args], check=True, **kw)


def resolve(base, path):
    p = Path(path).expanduser()
    return (base / p).resolve() if not p.is_absolute() else p.resolve()


def manifest(path):
    p = Path(path).resolve(); data = read(p)
    if not data.get('cues') or not data.get('scenes'):
        raise ValueError('Nonempty cues and scenes are required.')
    cue_count = len(data['cues'])
    for cue in data['cues']:
        if not all(isinstance(cue.get(k), str) and cue[k].strip() for k in ('en', 'zh')):
            raise ValueError('Each cue needs nonempty en and zh.')
        pause = cue.get('pause', data.get('pause', 2.0))
        if not isinstance(pause, (int, float)) or not math.isfinite(pause) or pause < 0:
            raise ValueError('Pause must be finite and nonnegative.')
        if cue.get('audio'):
            cue['audio'] = str(resolve(p.parent, cue['audio']))
            if not Path(cue['audio']).is_file(): raise ValueError('Missing audio: '+cue['audio'])
    indices = [s['cue'] for s in data['scenes']]
    if any(type(i) is not int for i in indices) or indices[0] != 0 or indices != sorted(set(indices)) or indices[-1] >= cue_count:
        raise ValueError('Scene cue indices must begin at zero and strictly increase within cue count.')
    for scene in data['scenes']:
        scene['image'] = str(resolve(p.parent, scene['image']))
        if not Path(scene['image']).is_file(): raise ValueError('Missing image: '+scene['image'])
    for ov in data.get('overlays', []):
        cs, ce = ov.get('cue_start'), ov.get('cue_end')
        if type(cs) is not int or type(ce) is not int or not (0 <= cs <= ce < cue_count):
            raise ValueError(f'Invalid overlay cue range [{cs}, {ce}] for {cue_count} cues.')
        if not ov.get('image'):
            raise ValueError('Overlay entry requires an image path.')
        ov['image'] = str(resolve(p.parent, ov['image']))
        if not Path(ov['image']).is_file(): raise ValueError('Missing overlay image: '+ov['image'])
    return data


async def narrate(args):
    data = manifest(args.manifest)
    out = Path(args.out).resolve()
    if out.exists(): raise FileExistsError(out)
    cache = Path(args.cache).resolve(); cache.mkdir(parents=True, exist_ok=True)
    lily_jobs = []
    jobs = {}
    for cue in data['cues']:
        if cue.get('audio'): continue
        voice = cue.get('voice', data.get('voice'))
        provider = cue.get('provider', data.get('provider'))
        is_lily = voice in ('Lily', 'CG02 Lily', 'CG02 Lily · Qwen3-TTS Base')
        if provider is None:
            explicit_edge_rate = cue.get('rate', data.get('rate')) not in (None, 'native', '+0%', '0%')
            provider = 'lily' if is_lily or (voice is None and not explicit_edge_rate) else 'edge-tts'
        if provider == 'lily':
            if voice is not None and not is_lily:
                raise ValueError(f'Unknown Lily voice: {voice}')
            if cue.get('rate', data.get('rate', 'native')) not in ('native', '+0%', '0%'):
                raise ValueError('The Lily preset uses its confirmed natural speed.')
            lily_jobs.append((cue, cue.get('spoken', cue['en'])))
            continue
        if provider != 'edge-tts':
            raise ValueError(f'Unknown narration provider: {provider}')
        config = dict(provider='edge-tts', version=importlib.metadata.version('edge-tts'),
                      text=cue.get('spoken', cue['en']),
                      voice=cue.get('voice', data.get('voice', 'en-US-JennyNeural')),
                      rate=cue.get('rate', data.get('rate', '-15%')))
        key = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        dest = cache / (key+'.mp3'); cue['audio'] = str(dest)
        jobs[key] = (config, dest)
    if lily_jobs:
        from lily_voice import generate_missing
        generate_missing(lily_jobs, cache)
    if jobs:
        import edge_tts
    sem = asyncio.Semaphore(3)
    async def generate(config, dest):
        metadata = dest.with_suffix('.json')
        if dest.is_file() and dest.stat().st_size > 500 and metadata.is_file() and read(metadata) == config:
            return
        async with sem:
            part = dest.with_suffix('.part.mp3')
            for attempt in range(3):
                try:
                    await asyncio.wait_for(edge_tts.Communicate(config['text'], config['voice'], rate=config['rate']).save(str(part)), 90)
                    if part.stat().st_size <= 500: raise ValueError('Empty speech response')
                    part.replace(dest); save(metadata, config)
                    return
                except Exception:
                    part.unlink(missing_ok=True)
                    if attempt == 2: raise
                    await asyncio.sleep(2)
    await asyncio.gather(*(generate(*job) for job in jobs.values()))
    out.parent.mkdir(parents=True, exist_ok=True); save(out, data)
    print('Narration manifest:', out)


def prepare(args):
    data = manifest(args.manifest); out = Path(args.out_dir).resolve()
    if out.exists(): raise FileExistsError('Use a new build directory: '+str(out))
    if any(not c.get('audio') for c in data['cues']): raise ValueError('Run narrate or supply each cue audio first.')
    out.mkdir(parents=True)
    timeline = []; sample_count = 12000; sr = 24000
    with wave.open(str(out/'narration.wav'), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(sr)
        wav.writeframes(b'\0' * sample_count * 2)
        for cue in data['cues']:
            pcm = subprocess.check_output([args.ffmpeg, '-v', 'error', '-i', cue['audio'], '-ar', str(sr), '-ac', '1', '-f', 's16le', '-'])
            if not pcm or len(pcm) % 2: raise ValueError('Invalid audio: '+cue['audio'])
            item = {k: cue[k] for k in ('en', 'zh', 'notes', 'highlight_en', 'highlight_zh') if k in cue}
            item['start'] = sample_count/sr
            item['speech_end'] = (sample_count+len(pcm)//2)/sr
            timeline.append(item)
            pause = round(cue.get('pause', data.get('pause', 2.0))*sr)
            wav.writeframes(pcm); wav.writeframes(b'\0'*pause*2)
            sample_count += len(pcm)//2 + pause
        duration = math.ceil(sample_count/sr)
        wav.writeframes(b'\0'*(duration*sr-sample_count)*2)
    scenes = []
    for i, s in enumerate(data['scenes']):
        start = timeline[s['cue']]['start'] if i else 0
        end = timeline[data['scenes'][i+1]['cue']]['start'] if i+1 < len(data['scenes']) else duration
        scenes.append(dict(s, start=start, end=end))
    save(out/'timeline.json', timeline); save(out/'scenes.json', scenes); save(out/'manifest.json', data)
    save(out/'timing.json', dict(duration=duration, cues=len(timeline), scenes=len(scenes)))
    save(out/'mobile-style.json', dict(en_size_ratio=.054, zh_size_ratio=.048, hint_size_ratio=.040, bottom_margin_ratio=.045, top_margin_ratio=.04, side_margin_ratio=.05))
    run([args.ffmpeg, '-v', 'error', '-n', '-f', 'lavfi', '-i', 'color=c=black:s=1920x1080:r=1', '-t', duration, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '40', out/'layout-reference.mp4'])
    print(json.dumps(dict(duration=duration, cues=len(timeline), scenes=len(scenes))))


def concat_quote(path):
    # FFmpeg concat uses its own escaping, not shell quoting.
    s = str(path)
    if '\n' in s or '\r' in s: raise ValueError('Newlines in image paths are not supported.')
    return "'" + s.replace("'", "'\\''") + "'"


def _ass_time_to_seconds(ts):
    h, m, s = ts.strip().split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def _parse_hint_plates(ass_path):
    plates = []
    for raw in ass_path.read_text(encoding='utf-8').splitlines():
        if not raw.startswith('Dialogue:'):
            continue
        parts = raw.split(',', 9)
        if len(parts) < 10 or parts[3].strip() != 'StudyHintPlate':
            continue
        m_pos = re.search(r'\\pos\((\d+(?:\.\d+)?),(\d+(?:\.\d+)?)\)', parts[9])
        if not m_pos:
            continue
        hx, hy = float(m_pos.group(1)), float(m_pos.group(2))
        nums = [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', parts[9].split('}', 1)[-1])]
        pw = max(nums[0::2]) if nums[0::2] else 0.0
        ph = max(nums[1::2]) if nums[1::2] else 0.0
        plates.append(dict(
            start=_ass_time_to_seconds(parts[1]),
            end=_ass_time_to_seconds(parts[2]),
            left=hx, top=hy, right=hx+pw, bottom=hy+ph,
        ))
    return plates


def _compute_overlay_windows(manifest_data, build, ass_path, duration):
    from PIL import Image

    overlays = manifest_data.get('overlays') or []
    if not overlays:
        return []
    timeline = read(build / 'timeline.json')
    hint_plates = _parse_hint_plates(ass_path)
    windows = []
    for ov in overlays:
        cs, ce = int(ov['cue_start']), int(ov['cue_end'])
        t_start = float(timeline[cs]['start'])
        t_end = float(timeline[ce + 1]['start']) if (ce + 1) < len(timeline) else float(duration)
        badge_path = resolve(build.parent, ov['image'])
        with Image.open(badge_path) as im:
            bw, bh = im.size
        max_w = 1920 * float(ov.get('max_width_ratio', 0.16))
        if bw > max_w + 1:
            raise ValueError(f'Overlay {badge_path.name} width {bw} exceeds max_width_ratio {max_w:.0f}')
        right_margin = int(ov.get('right_margin', 54))
        min_y = float(ov.get('min_y', 268))
        hint_gap = float(ov.get('hint_gap', 24))
        max_bottom = int(ov.get('max_bottom', 730))
        bx = 1920 - right_margin - bw
        active = [hp for hp in hint_plates if hp['end'] > t_start + 1e-3 and hp['start'] < t_end - 1e-3]
        max_hint_bottom = max((hp['bottom'] for hp in active), default=0.0)
        by = int(round(max(min_y, max_hint_bottom + hint_gap)))
        if by + bh > max_bottom:
            raise ValueError(f'Overlay bottom {by + bh} exceeds safe subtitle zone ({max_bottom}) at [{t_start:.2f}s, {t_end:.2f}s]')
        windows.append(dict(
            cue_start=cs, cue_end=ce, t_start=round(t_start, 3), t_end=round(t_end, 3),
            x=bx, y=by, w=bw, h=bh, badge_path=str(badge_path),
            active_hint_bottom=round(max_hint_bottom, 1),
        ))
    return windows


def _stage_concat_frames(build, scenes, windows):
    """Pre-normalize unique scene images to 1920x1080 RGB PNGs and bake any RGBA overlay segments."""
    from PIL import Image, ImageOps

    stage_dir = build / 'stage_frames'
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)
    Image.MAX_IMAGE_PIXELS = 400_000_000

    base_frames = {}
    for sc in scenes:
        src = sc['image']
        if src not in base_frames:
            dst = stage_dir / f'base_{len(base_frames):02d}.png'
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im).convert('RGB')
                if im.size != (1920, 1080):
                    im = ImageOps.fit(im, (1920, 1080), Image.Resampling.LANCZOS)
                im.save(dst, 'PNG')
            base_frames[src] = dst

    ov_frames = {}
    lines = ['ffconcat version 1.0']
    last_frame = None
    for sc in scenes:
        s_start, s_end = float(sc['start']), float(sc['end'])
        if s_end <= s_start + 1e-6:
            continue
        cuts = {s_start, s_end}
        for w in windows:
            if s_start + 1e-4 < w['t_start'] < s_end - 1e-4:
                cuts.add(float(w['t_start']))
            if s_start + 1e-4 < w['t_end'] < s_end - 1e-4:
                cuts.add(float(w['t_end']))
        pts = sorted(cuts)
        base_path = base_frames[sc['image']]
        for a, b in zip(pts, pts[1:]):
            if b - a <= 1e-4:
                continue
            mid = 0.5 * (a + b)
            active_w = next((w for w in windows if w['t_start'] <= mid <= w['t_end']), None)
            if active_w is None:
                frame_path = base_path
            else:
                fkey = (str(base_path), active_w['badge_path'], active_w['x'], active_w['y'])
                if fkey not in ov_frames:
                    fdst = stage_dir / f'overlay_{len(ov_frames):02d}.png'
                    with Image.open(base_path) as bim, Image.open(active_w['badge_path']) as fim:
                        canvas = bim.convert('RGBA')
                        canvas.alpha_composite(fim.convert('RGBA'), (int(active_w['x']), int(active_w['y'])))
                        canvas.convert('RGB').save(fdst, 'PNG')
                    ov_frames[fkey] = fdst
                frame_path = ov_frames[fkey]
            lines.append('file ' + concat_quote(frame_path))
            lines.append(f'duration {b - a:.8f}')
            last_frame = frame_path
    if last_frame is not None:
        lines.append('file ' + concat_quote(last_frame))
    (build / 'images.ffconcat').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def render(args):
    build = Path(args.build).resolve(); output = Path(args.output).resolve(); ass = Path(args.ass).resolve()
    if output.exists() and not args.overwrite: raise FileExistsError(output)
    if not ass.is_file(): raise ValueError('Missing ASS file')
    scenes = read(build/'scenes.json'); duration = read(build/'timing.json')['duration']
    manifest_data = read(build/'manifest.json') if (build/'manifest.json').is_file() else {}
    # Work from the build directory with a fixed ASS filename to avoid filter-path escaping.
    subtitle = build/'render.ass'
    if subtitle.exists() and not args.overwrite: raise FileExistsError(subtitle)
    subtitle.write_bytes(ass.read_bytes())

    windows = _compute_overlay_windows(manifest_data, build, ass, duration)
    if windows:
        save(build/'overlay_plan.json', windows)
    _stage_concat_frames(build, scenes, windows)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        tmp_out = Path(staging) / 'render.tmp.mp4'
        run([args.ffmpeg, '-v', 'warning', '-y', '-f', 'concat', '-safe', '0', '-i', 'images.ffconcat', '-i', 'narration.wav', '-map', '0:v:0', '-map', '1:a:0', '-vf', 'fps=30,setsar=1,format=yuv420p,ass=render.ass', '-t', duration, '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', tmp_out], cwd=build)
        run([args.ffmpeg, '-v', 'error', '-xerror', '-i', tmp_out, '-f', 'null', '-'])
        info = json.loads(subprocess.check_output([args.ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(tmp_out)]))
        v = [s for s in info['streams'] if s['codec_type'] == 'video']; a = [s for s in info['streams'] if s['codec_type'] == 'audio']
        if len(v)!=1 or len(a)!=1 or (v[0]['width'],v[0]['height'])!=(1920,1080) or v[0]['r_frame_rate']!='30/1' or abs(float(info['format']['duration'])-duration)>.1:
            raise ValueError('Unexpected output media properties')
        tmp_out.replace(output)
    save(output.with_suffix('.verification.json'), dict(full_decode='passed', overlays=len(windows), media=info, pending='ASR, semantic and visual review, physical phone playback'))
    print('Created:', output)


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='cmd', required=True)
    n = sub.add_parser('narrate')
    for name in ('manifest', 'out', 'cache'): n.add_argument('--'+name, required=True)
    b = sub.add_parser('prepare'); b.add_argument('--manifest', required=True); b.add_argument('--out-dir', required=True); b.add_argument('--ffmpeg', default='ffmpeg')
    r = sub.add_parser('render')
    for name in ('build', 'ass', 'output'): r.add_argument('--'+name, required=True)
    r.add_argument('--ffmpeg', default='ffmpeg'); r.add_argument('--ffprobe', default='ffprobe')
    r.add_argument('--overwrite', action='store_true', help='Replace existing render.ass and final output if decode succeeds')
    args = p.parse_args()
    if args.cmd == 'narrate': asyncio.run(narrate(args))
    elif args.cmd == 'prepare': prepare(args)
    else: render(args)

if __name__ == '__main__': main()
