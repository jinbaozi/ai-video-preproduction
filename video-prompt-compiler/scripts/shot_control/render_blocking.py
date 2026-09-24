"""Review SVG/HTML only. Labels and paths must never enter image reference slots."""
import html
import json
from pathlib import Path

PALETTE = ('#67d5ff', '#ffa774', '#bba2ff', '#8fe3a0', '#ff83b5')


def svg(frame, view, extent, frames=()):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360">',
             '<rect width="640" height="360" fill="#101a2b"/>']
    if view in ('top', 'side'):
        for i, point in enumerate(frame['points']):
            segments = []; run = []
            for sample in frames:
                if sample['shot_id'] != frame['shot_id']:
                    continue
                p = next((p['position'] for p in sample['points'] if p['id'] == point['id']), None)
                if p is None:
                    if run: segments.append(run)
                    run = []; continue
                run.append(f'{320+p[0]/extent*250:.3f},{180+(p[2] if view == "top" else -p[1])/extent*140:.3f}')
            if run: segments.append(run)
            for run in segments:
                parts.append(f'<polyline points="{" ".join(run)}" fill="none" stroke="{PALETTE[i % len(PALETTE)]}" stroke-opacity=".35" stroke-width="2"/>')
    for i, point in enumerate(frame['points']):
        p = point['position']
        if p is None:
            continue
        if view == 'camera':
            projection = point['projection']
            if projection['status'] != 'IN_FRAME' or point['kind'] == 'camera':
                continue
            x, y = projection['xy'][0]*640, projection['xy'][1]*360
        else:
            x = 320+p[0]/extent*250
            y = 180+(p[2] if view == 'top' else -p[1])/extent*140
        color = PALETTE[i % len(PALETTE)]
        parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="7" fill="{color}"/>')
        parts.append(f'<text x="{x+10:.3f}" y="{y:.3f}" fill="{color}" font-size="13">{html.escape(point["label"])}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def export_review(out, frames):
    extent = max([1]+[abs(x) for f in frames for p in f['points'] if p['position'] for x in p['position']])*1.15
    slides = []
    for f in frames:
        slides.append({'shot_id': f['shot_id'], 'at_ms': f['at_ms'],
                       'top': svg(f, 'top', extent, frames), 'side': svg(f, 'side', extent, frames), 'camera': svg(f, 'camera', extent),
                       'details': {'camera': f['camera'], 'state_status': f['state']['status'],
                                   'unknown_nodes': [p['id'] for p in f['points'] if p['position'] is None]}})
    data = json.dumps(slides, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    template = Path(__file__).with_name('review.html').read_text()
    (out/'review/index.html').write_text(template.replace('__DATA__', data), encoding='utf-8')
    for f in frames:
        if not any(x['shot_id'] == f['shot_id'] and x['at_ms'] < f['at_ms'] for x in frames):
            # Filenames use an ordinal rather than untrusted source IDs.
            index = len(list((out/'review').glob('blocking-*.svg')))+1
            (out/'review'/f'blocking-{index:03d}.svg').write_text(svg(f, 'top', extent, frames), encoding='utf-8')
