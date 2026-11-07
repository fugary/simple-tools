#!/usr/bin/env python3
"""Read-only dependency and capability discovery. Does not install software."""
import argparse
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def inspect_executable(name, args):
    found = shutil.which(name)
    if not found and Path(name).is_file(): found = str(Path(name).resolve())
    if not found: return None, ''
    try:
        r = subprocess.run([found]+args, capture_output=True, text=True, timeout=20)
        return found, r.stdout+'\n'+r.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return found, str(exc)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ffmpeg', default='ffmpeg'); p.add_argument('--ffprobe', default='ffprobe')
    p.add_argument('--whisper', default='whisper-cli'); a = p.parse_args()
    ff, filters = inspect_executable(a.ffmpeg, ['-hide_banner','-filters'])
    _, encoders = inspect_executable(a.ffmpeg, ['-hide_banner','-encoders'])
    probe, probe_text = inspect_executable(a.ffprobe, ['-version'])
    wh, _ = inspect_executable(a.whisper, ['--help'])
    packages = {}
    for package in ['edge-tts','pysubs2']:
        try: packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: packages[package] = None
    fc, fonts = inspect_executable('fc-list', [':lang=zh','family'])
    subtitle = Path(__file__).resolve().parents[2]/'bilingual-study-subtitles/scripts/subtitle_tool.py'
    caps = dict(ass_filter=any(' ass ' in line for line in filters.splitlines()),
                h264_encoder='libx264' in encoders, aac_encoder=any(' aac ' in line for line in encoders.splitlines()),
                ffprobe=bool(probe and 'ffprobe version' in probe_text), subtitle_skill=subtitle.is_file())
    report = dict(python=sys.version.split()[0], platform=platform.platform(), packages=packages,
                  executables=dict(ffmpeg=ff,ffprobe=probe,whisper=wh), capabilities=caps,
                  chinese_font_candidates=sorted(set(fonts.strip().splitlines()))[:20] if fc else [],
                  notes=['Font list may be unavailable; inspect actual rendering.',
                         'Network access, TTS availability and ASR model files are not tested.',
                         'edge-tts is optional when all narration audio is supplied.'])
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if sys.version_info >= (3,9) and all(caps.values()) and packages['pysubs2'] else 1

if __name__ == '__main__': sys.exit(main())
