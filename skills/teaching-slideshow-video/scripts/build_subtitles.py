#!/usr/bin/env python3
"""Use the bundled subtitle skill with balanced wrapping and the build's mobile style."""
import argparse
import importlib.util
from pathlib import Path
import re
import sys
import unicodedata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', required=True)
    p.add_argument('--font-zh', required=True, help='Installed Chinese font family; verify visually.')
    p.add_argument('--font-en', default='Arial')
    p.add_argument('--ffprobe', default='ffprobe')
    p.add_argument('--subtitle-skill', default=str(Path(__file__).resolve().parents[2]/'bilingual-study-subtitles'))
    a = p.parse_args(); root = Path(a.build).resolve()
    module_path = Path(a.subtitle_skill)/'scripts/subtitle_tool.py'
    if not module_path.is_file(): p.error('Install the sibling bilingual-study-subtitles skill or pass --subtitle-skill.')
    spec = importlib.util.spec_from_file_location('subtitle_tool',module_path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    original = m.wrapped
    def weight(text):
        return sum(2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in text)
    def balanced(text, columns):
        if weight(text)<=columns:
            yield 0,len(text); return
        chinese=bool(re.search('[\u4e00-\u9fff]',text)); candidates=[]
        for i in range(1,len(text)):
            if not chinese and not text[i].isspace(): continue
            if chinese and text[i] in '，。！？；、）】”': continue
            left=text[:i].rstrip();right=text[i:].lstrip()
            if not left or not right or max(weight(left),weight(right))>columns: continue
            score=abs(weight(left)-weight(right))
            if left[-1] in ',，;；?？!！.。': score-=12
            if right.startswith(('because ','with ','and ','to ','from ','因为','并','让','把')): score-=5
            candidates.append((score,len(left),len(text)-len(right)))
        if candidates:
            _,left,right=min(candidates);yield 0,left;yield right,len(text)
        else: yield from original(text,columns)
    m.wrapped=balanced
    sys.argv=['subtitle_tool','build','--video',str(root/'layout-reference.mp4'),'--timeline',str(root/'timeline.json'),'--out-prefix',str(root/'study'),'--style',str(root/'mobile-style.json'),'--font-zh',a.font_zh,'--font-en',a.font_en,'--ffprobe',a.ffprobe]
    m.main()

if __name__ == '__main__': main()
