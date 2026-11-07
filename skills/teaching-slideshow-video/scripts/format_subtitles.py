"""Apply the 1080p teaching subtitle preset."""
import argparse
from functools import lru_cache
from pathlib import Path
import re
import subprocess
import tempfile

from PIL import Image
import pysubs2 as ass


def compact(note):
    note = note.replace(r'\N', ' ').strip()
    match = re.fullmatch(r'(.+?)\s*表示“([^”]+)”。?', note)
    if match:
        return match[1].rstrip('， ') + '   ' + match[2]
    return note


def lettering(note, english_font, chinese_font):
    # Only language terms take the accent. Explanatory text stays white.
    chunks = re.split(r"([A-Za-z0-9][A-Za-z0-9.,’'-]*(?: [A-Za-z0-9][A-Za-z0-9.,’'-]*)*)", note)
    styles = [rf'{{\fn{chinese_font}\1c&HFFFFFF&}}', rf'{{\fn{english_font}\1c&H1C53FD&}}']
    return ''.join(styles[i % 2] + chunk for i, chunk in enumerate(chunks) if chunk)


def rounded_box(w, h, r):
    return (f'm {r} 0 l {w-r} 0 b {w-8} 0 {w} 8 {w} {r} l {w} {h-r} '
            f'b {w} {h-8} {w-8} {h} {w-r} {h} l {r} {h} b 8 {h} 0 {h-8} 0 {h-r} '
            f'l 0 {r} b 0 8 8 0 {r} 0')


def style_hints(doc, ffmpeg, english_font, chinese_font):
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

        for cue in hints:
            text = lettering(compact(cue.text), english_font, chinese_font)
            size = font_size
            while True:
                l,t,r,b = ink(text, size)
                w,h = r-l+2*pad_x,b-t+2*pad_y
                if w <= width*.90:
                    break
                if size <= round(font_size*.76):
                    # Wrap at a space or CJK character boundary closest to the middle.
                    plain = compact(cue.text)
                    cuts = [i for i in range(1,len(plain)) if plain[i].isspace() or
                            ('\u3400' <= plain[i] <= '\u9fff')]
                    if not cuts:
                        raise ValueError('Split this long note into two phrases: '+plain)
                    cut=min(cuts,key=lambda i:abs(i-len(plain)/2))
                    text=lettering(plain[:cut].strip(), english_font, chinese_font)+r'\N'+lettering(plain[cut:].strip(), english_font, chinese_font)
                    l,t,r,b=ink(text,size)
                    w,h=r-l+2*pad_x,b-t+2*pad_y
                    if w > width*.90:
                        raise ValueError('Shorten note: '+plain)
                    break
                size-=2
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
    style_hints(doc, ffmpeg, doc.styles['Default'].fontname, doc.styles['Hint'].fontname)
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
