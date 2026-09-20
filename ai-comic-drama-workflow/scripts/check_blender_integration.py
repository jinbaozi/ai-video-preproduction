"""Explicit live local test; synthetic scene, no creative/user approval implied."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from tests.test_v3_contracts import physical_fixture
from ai_comic_drama_workflow.blender_adapter import render_shot
from ai_comic_drama_workflow.storage import ProjectStore

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--animate', action='store_true')
parser.add_argument('--golden', action='store_true')
args = parser.parse_args()
scene, shot = physical_fixture()
store = ProjectStore(args.output)
if args.golden:
    from tests.golden_director import director_scene
    from ai_comic_drama_workflow.spatial_qa import audit_shot, audit_handoff
    from ai_comic_drama_workflow.editing import execute_edit_plan
    from ai_comic_drama_workflow.utils import canonical_json
    scene, shots = director_scene()
    store.write_text('runtime/golden-input.json', canonical_json({'test_only': True, 'human_approved': False, 'scene': scene, 'shots': shots}))
    media, reports = [], []
    for index, shot in enumerate(shots):
        report = audit_shot(scene, shot)
        if report['errors'] or (index and audit_handoff(scene, shots[index-1], scene, shot)):
            raise ValueError('Golden spatial/continuity checks failed')
        receipt = render_shot(store, scene, shot, folder='stages/09-故事板/blender/' + shot['shot_id'], size=(640, 360), animate=True)
        media.append({'shot_id': shot['shot_id'], **receipt['video']})
        reports.append({'shot_id': shot['shot_id'], 'spatial_qa': report, 'engine': receipt['engine'], 'execution_verified': receipt['execution_verified']})
        print(json.dumps({'rendered': shot['shot_id'], 'path': receipt['video']['path']}, ensure_ascii=False), flush=True)
    plan = {'timeline': [{'shot_id': shot['shot_id'], 'duration_s': shot['duration_s']} for shot in shots], 'dialogue_table': []}
    edit = execute_edit_plan(store, plan, media)
    store.write_text('runtime/golden-result.json', canonical_json({'test_only': True, 'human_approved': False, 'shots': reports, 'edit': edit}))
    print(json.dumps({'golden_edit': edit['path'], 'duration_s': edit['duration_s'], 'human_approved': False}, ensure_ascii=False))
    raise SystemExit(0)
receipt = render_shot(store, scene, shot, folder='stages/09-故事板/blender', size=(320, 180), animate=args.animate)
print(json.dumps({'execution_verified': receipt['execution_verified'], 'engine': receipt['engine'],
                  'file_count': len(receipt['files']), 'video': receipt['video'], 'boundary': receipt['boundary']}, indent=2))
