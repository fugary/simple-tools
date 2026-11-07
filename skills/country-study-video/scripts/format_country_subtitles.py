"""Add the country series cover and review topics to a teaching subtitle build."""
import argparse
import json
from pathlib import Path
import re
import sys

import pysubs2 as ass

teaching_scripts = Path(__file__).resolve().parents[2] / 'teaching-slideshow-video' / 'scripts'
sys.path.insert(0, str(teaching_scripts))
from format_subtitles import gradient, load_subtitles, save_styled_subtitles


def add_country_layout(doc, timeline, topics, english, chinese):
    # prepare and render both target 1920 x 1080. Coordinates match the series master.
    if len(timeline) < 2:
        raise ValueError('Country episodes need a title followed by narration.')
    starts = [round(cue['start'] * 100) * 10 for cue in timeline]
    title_end = starts[1]
    doc.events = [event for event in doc if event.start >= title_end]
    gradient(doc, 380, 930, .53, 0, title_end)
    title = timeline[0]
    country, _, theme = title['en'].partition('—')
    labels = [('CoverName', country, english, 100, 108, 628),
              ('CoverLine', theme, english, 51, 112, 759),
              ('CoverChinese', re.sub(r'\s*—+\s*', ' · ', title['zh']), chinese, 46, 112, 850)]
    for style, label, font, size, x, y in labels:
        if label.strip():
            doc.styles[style] = ass.SSAStyle(fontname=font, fontsize=size, bold=(style == 'CoverName'),
                                            alignment=7, outline=1.4, shadow=.8,
                                            outlinecolor=ass.Color(18, 24, 29, 125))
            event = ass.SSAEvent(style=style, layer=4, start=0, end=title_end)
            event.plaintext = label.strip().replace('{', '｛').replace('}', '｝').replace('\\', '＼')
            event.text = rf'{{\an7\pos({x},{y})}}' + event.text
            doc.append(event)
    doc.styles['ReviewTopic'] = ass.SSAStyle(fontname=english, fontsize=38, bold=True, borderstyle=3,
                                            outline=6, shadow=0, outlinecolor=ass.Color(16, 25, 39, 48),
                                            alignment=7, marginl=62, marginv=238)
    next_index = len(timeline) - 1  # The final cue returns to the cover for the outro.
    for topic in reversed(topics):
        index = topic['cue']
        if type(index) is not int or not 0 < index < next_index:
            raise ValueError('Review cue indices must increase and precede the outro.')
        label = topic['topic'].strip()
        if not label or any(char in label for char in '{}\\\n'):
            raise ValueError('Review topics need plain single-line labels.')
        doc.append(ass.SSAEvent(style='ReviewTopic', layer=3, start=starts[index], end=starts[next_index],
                                text='Review  |  ' + label))
        next_index = index
    return title_end


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--review-topics', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    doc = load_subtitles(args.build)
    timeline = json.loads((args.build / 'timeline.json').read_text(encoding='utf-8'))
    topics = json.loads(args.review_topics.read_text(encoding='utf-8'))
    start = add_country_layout(doc, timeline, topics, doc.styles['Default'].fontname, doc.styles['Hint'].fontname)
    save_styled_subtitles(doc, args.build, args.ffmpeg, body_start=start)


if __name__ == '__main__':
    main()
