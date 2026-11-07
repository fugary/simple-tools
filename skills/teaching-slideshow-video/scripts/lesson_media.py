#!/usr/bin/env python3
"""Reusable narration, sample-based timing and still-image video composition."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import subprocess
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
    if any(type(i) is not int for i in indices) or indices[0] != 0 or indices != sorted(set(indices)) or indices[-1] >= len(data['cues']):
        raise ValueError('Scene cue indices must begin at zero and strictly increase within cue count.')
    for scene in data['scenes']:
        scene['image'] = str(resolve(p.parent, scene['image']))
        if not Path(scene['image']).is_file(): raise ValueError('Missing image: '+scene['image'])
    return data


async def narrate(args):
    import edge_tts
    data = manifest(args.manifest)
    out = Path(args.out).resolve()
    if out.exists(): raise FileExistsError(out)
    cache = Path(args.cache).resolve(); cache.mkdir(parents=True, exist_ok=True)
    version = importlib.metadata.version('edge-tts')
    jobs = {}
    for cue in data['cues']:
        if cue.get('audio'): continue
        config = dict(provider='edge-tts', version=version,
                      text=cue.get('spoken', cue['en']),
                      voice=cue.get('voice', data.get('voice', 'en-US-JennyNeural')),
                      rate=cue.get('rate', data.get('rate', '-15%')))
        key = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        dest = cache / (key+'.mp3'); cue['audio'] = str(dest)
        jobs[key] = (config, dest)
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


def render(args):
    build = Path(args.build).resolve(); output = Path(args.output).resolve(); ass = Path(args.ass).resolve()
    if output.exists(): raise FileExistsError(output)
    if not ass.is_file(): raise ValueError('Missing ASS file')
    scenes = read(build/'scenes.json'); duration = read(build/'timing.json')['duration']
    # Work from the build directory with a fixed ASS filename to avoid filter-path escaping.
    subtitle = build/'render.ass'
    if subtitle.exists(): raise FileExistsError(subtitle)
    subtitle.write_bytes(ass.read_bytes())
    concat = 'ffconcat version 1.0\n'
    for s in scenes:
        concat += 'file '+concat_quote(s['image'])+'\nduration %.8f\n'%(s['end']-s['start'])
    concat += 'file '+concat_quote(scenes[-1]['image'])+'\n'
    (build/'images.ffconcat').write_text(concat)
    output.parent.mkdir(parents=True, exist_ok=True)
    run([args.ffmpeg, '-v', 'warning', '-n', '-f', 'concat', '-safe', '0', '-i', 'images.ffconcat', '-i', 'narration.wav', '-map', '0:v:0', '-map', '1:a:0', '-vf', 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30,ass=render.ass', '-t', duration, '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', output], cwd=build)
    run([args.ffmpeg, '-v', 'error', '-xerror', '-i', output, '-f', 'null', '-'])
    info = json.loads(subprocess.check_output([args.ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)]))
    v = [s for s in info['streams'] if s['codec_type'] == 'video']; a = [s for s in info['streams'] if s['codec_type'] == 'audio']
    if len(v)!=1 or len(a)!=1 or (v[0]['width'],v[0]['height'])!=(1920,1080) or v[0]['r_frame_rate']!='30/1' or abs(float(info['format']['duration'])-duration)>.1:
        raise ValueError('Unexpected output media properties')
    save(output.with_suffix('.verification.json'), dict(full_decode='passed', media=info, pending='ASR, semantic and visual review, physical phone playback'))
    print('Created:', output)


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='cmd', required=True)
    n = sub.add_parser('narrate')
    for name in ('manifest', 'out', 'cache'): n.add_argument('--'+name, required=True)
    b = sub.add_parser('prepare'); b.add_argument('--manifest', required=True); b.add_argument('--out-dir', required=True); b.add_argument('--ffmpeg', default='ffmpeg')
    r = sub.add_parser('render')
    for name in ('build', 'ass', 'output'): r.add_argument('--'+name, required=True)
    r.add_argument('--ffmpeg', default='ffmpeg'); r.add_argument('--ffprobe', default='ffprobe')
    args = p.parse_args()
    if args.cmd == 'narrate': asyncio.run(narrate(args))
    elif args.cmd == 'prepare': prepare(args)
    else: render(args)

if __name__ == '__main__': main()
