import copy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import storyboard as sb
import package_skill as pkg
from jsonschema import Draft202012Validator


class StoryboardTests(unittest.TestCase):
    def setUp(self):
        self.base = sb.ROOT / 'examples'
        self.ir = sb.read(self.base / 'cafe.ir.json')

    def report(self):
        return sb.validate(self.ir, self.base)

    def rejects(self, code):
        report = self.report()
        self.assertEqual(report['status'], 'INVALID', report)
        self.assertIn(code, [d['code'] for d in report['diagnostics']], report)

    def test_cafe_complete(self):
        self.assertEqual(self.report()['status'], 'VALID')
        self.assertEqual(sum(len(s['panels']) for s in self.ir['shots']), 8)

    def test_product_without_people_or_dialogue(self):
        self.ir = sb.read(self.base / 'product.ir.json')
        self.assertEqual(self.report()['status'], 'VALID')
        self.assertEqual(self.ir['audio']['utterances'], [])
        self.assertEqual(self.ir['shots'][0]['performance'], [])

    def test_trigger_event_must_finish_first(self):
        self.ir['shots'][2]['events'][2]['depends_on'] = ['EV_GRASP']
        self.rejects('E_EVENT_DEPENDENCY')

    def test_panel_state_distinguishes_in_progress_from_completed(self):
        self.ir = sb.read(self.base / 'product.ir.json')
        shot = self.ir['shots'][0]
        during = sb.panel_state(shot, 60)
        after = sb.panel_state(shot, 143)
        self.assertEqual(during['active_event_ids'], ['EV_ROTATE'])
        self.assertFalse(during['interpolated'])
        self.assertEqual(during['completed_state']['PRODUCT']['yaw_deg'], 0)
        self.assertEqual(after['completed_state']['PRODUCT']['yaw_deg'], 60)

    def test_static_pass_never_media_pass(self):
        report = self.report()
        self.assertFalse(report['submitted'])
        self.assertFalse(report['execution_ready'])
        self.assertEqual(report['visual'], 'NOT_RUN')
        for c in report['contract_results']:
            for a in c['acceptance']:
                if a['phase'] != 'structure':
                    self.assertEqual(a['status'], 'NOT_RUN')

    def test_all_schemas_are_valid(self):
        for path in (sb.ROOT / 'schemas').glob('*.json'):
            Draft202012Validator.check_schema(sb.read(path))

    def test_typo_field_rejected(self):
        self.ir['shots'][0]['camra'] = {}
        self.rejects('E_SCHEMA')

    def test_boolean_is_not_frame(self):
        self.ir['shots'][0]['start_frame'] = False
        self.rejects('E_SCHEMA')

    def test_unknown_source_reference(self):
        self.ir['shots'][0]['source_refs'] = ['MISSING']
        self.rejects('E_SOURCE_REF')

    def test_duplicate_entity(self):
        self.ir['entities'].append(copy.deepcopy(self.ir['entities'][0]))
        self.rejects('E_DUPLICATE_ID')

    def test_excerpt_hash_changed(self):
        self.ir['sources'][0]['excerpt'] += '改动'
        self.rejects('E_EXCERPT_HASH')

    def test_source_file_hash_changed(self):
        self.ir['sources'][0]['file_sha256'] = '0' * 64
        self.rejects('E_SOURCE_HASH')

    def test_source_excerpt_not_in_original(self):
        source = self.ir['sources'][0]
        source['excerpt'] = '另一份脚本'
        source['excerpt_sha256'] = sha256(source['excerpt'].encode()).hexdigest()
        self.rejects('E_EXCERPT_CONTENT')

    def test_source_span_changed(self):
        self.ir['sources'][0]['utterances'][0]['span']['start'] += 1
        self.rejects('E_SOURCE_SPAN')

    def test_duplicate_source_line(self):
        self.ir['sources'][1]['utterances'] = copy.deepcopy(self.ir['sources'][0]['utterances'])
        self.rejects('E_DUPLICATE_UTTERANCE')

    def test_scope_order_is_exact(self):
        self.ir['scope']['shot_ids'].reverse()
        self.rejects('E_SCOPE_SHOTS')

    def test_missing_required_beat(self):
        beat = copy.deepcopy(self.ir['beats'][-1]);beat['id']='BEAT4'
        self.ir['beats'].append(beat)
        self.rejects('E_BEAT_COVERAGE')

    def test_causal_order(self):
        self.ir['beats'][0]['depends_on']=['BEAT3']
        self.rejects('E_BEAT_ORDER')

    def test_excluded_beat_needs_reason(self):
        self.ir['beats'][0]['required']=False
        self.rejects('E_BEAT_EXCLUSION')

    def test_shot_timeline_gap(self):
        self.ir['shots'][1]['start_frame'] += 1
        self.rejects('E_TIMELINE')

    def test_total_duration(self):
        self.ir['delivery']['total_frames'] += 1
        self.rejects('E_DURATION')

    def test_unknown_scene(self):
        self.ir['shots'][0]['scene_id']='NOWHERE'
        self.rejects('E_SHOT_SCENE')

    def test_world_state_keeps_offscreen_entity(self):
        del self.ir['shots'][1]['state_start']['A']
        self.rejects('E_STATE_SET')

    def test_position_outside_scene(self):
        self.ir['shots'][1]['state_start']['A']['position_m']=[99,0,0]
        self.rejects('E_POSITION_BOUNDS')

    def test_gaze_target_missing(self):
        self.ir['shots'][0]['state_start']['A']['gaze_target']='GHOST'
        self.rejects('E_GAZE')

    def test_world_teleport(self):
        self.ir['shots'][1]['state_start']['A']['position_m']=[-1,0,0]
        self.rejects('E_CONTINUITY')

    def test_unexplained_end_state(self):
        self.ir['shots'][0]['state_end']['A']['yaw_deg']=30
        self.rejects('E_EVENT_REPLAY')

    def test_before_state_must_match(self):
        self.ir['shots'][0]['events'][0]['changes'][0]['before']=[9,9,9]
        self.rejects('E_EVENT_PRECONDITION')

    def test_event_state_type(self):
        self.ir['shots'][0]['events'][0]['changes'][0]['after']='移到桌上'
        self.rejects('E_STATE_TYPE')

    def test_event_outside_shot(self):
        self.ir['shots'][0]['events'][0]['end_frame']=100
        self.rejects('E_EVENT_TIME')

    def test_overlapping_same_state_writes(self):
        self.ir['shots'][0]['events'][1]['start_frame']=20
        self.rejects('E_EVENT_OVERLAP')

    def test_custody_cannot_use_generic_state_change(self):
        self.ir['shots'][2]['events'][-1]['kind']='state'
        self.rejects('E_CUSTODY_EVENT')

    def test_grasp_requires_touch(self):
        touch=self.ir['shots'][2]['events'][2]
        touch['changes'][0]['after']=['TABLE.top']
        self.ir['shots'][2]['events'][3]['changes'][1]['before']=['TABLE.top']
        self.rejects('E_GRASP_PRECONDITION')

    def test_release_by_wrong_hand(self):
        self.ir['shots'][0]['events'][1]['effector']='left_hand'
        self.rejects('E_RELEASE_PRECONDITION')

    def test_holder_without_contact(self):
        self.ir['shots'][0]['state_start']['ENVELOPE']['contacts']=[]
        self.rejects('E_HOLDER_CONTACT')

    def test_duplicate_event(self):
        self.ir['shots'][2]['events'][0]['id']='EV_PLACE'
        self.rejects('E_EVENT_DUPLICATE')

    def test_panel_end_boundary_excluded(self):
        self.ir['shots'][0]['panels'][-1]['frame']=96
        self.rejects('E_PANEL_TIME')

    def test_duplicate_panel(self):
        self.ir['shots'][1]['panels'][0]['id']='P1'
        self.rejects('E_PANEL_DUPLICATE')

    def test_panel_cannot_reference_future_event(self):
        self.ir['shots'][0]['panels'][0]['event_ids']=['EV_RELEASE']
        self.rejects('E_PANEL_EVENT')

    def test_box_outside_frame(self):
        self.ir['shots'][0]['composition']['subjects'][0]['box']=[.9,.1,.3,.5]
        self.rejects('E_COMPOSITION')

    def test_performance_parts_not_visible(self):
        self.ir['shots'][1]['composition']['subjects'][0]['visible_parts']=['face']
        self.rejects('E_PERFORMANCE_VISIBILITY')

    def test_micro_expression_in_wide_shot(self):
        self.ir['shots'][1]['camera']['size']='wide'
        self.rejects('E_MICRO_SCALE')

    def test_declared_axis_must_match_geometry(self):
        self.ir['shots'][1]['camera']['axis_side']='positive'
        self.rejects('E_AXIS_SIDE')

    def test_cut_crossing_axis(self):
        cam=self.ir['shots'][1]['camera']
        cam['start_m'][2]=1.4;cam['end_m'][2]=1.4;cam['axis_side']='positive'
        self.rejects('E_AXIS_CUT')

    def test_in_shot_crossing_needs_visible_path(self):
        self.ir['shots'][0]['camera']['end_m'][2]=3
        self.rejects('E_AXIS_CROSS')

    def test_degenerate_axis(self):
        self.ir['scenes'][0]['axis']['end_m']=self.ir['scenes'][0]['axis']['start_m']
        self.rejects('E_AXIS_DEGENERATE')

    def test_relative_position_checked(self):
        self.ir['shots'][0]['relations'][0]['relation']='world_right_of'
        self.rejects('E_RELATION')

    def test_continuous_time_cannot_mask_state_exception(self):
        self.ir['shots'][1]['transition']['state_exceptions']=[dict(entity_id='A',field='pose',reason='想换姿态',source_refs=['DESIGN'])]
        self.rejects('E_STATE_EXCEPTION')

    def test_dialogue_word_changed(self):
        self.ir['audio']['utterances'][0]['text']='我确定。'
        self.rejects('E_DIALOGUE_FIDELITY')

    def test_dialogue_outside_source_scope(self):
        self.ir['scope']['source_ids']=['DESIGN']
        self.rejects('E_DIALOGUE_SCOPE')

    def test_release_cannot_keep_hand_as_support(self):
        self.ir['shots'][0]['events'][0]['changes'][1]['after']='A.right_hand'
        self.rejects('E_RELEASE_SUPPORT')

    def test_dialogue_speaker_changed(self):
        self.ir['audio']['utterances'][0]['speaker_id']='A'
        self.rejects('E_DIALOGUE_FIDELITY')

    def test_dialogue_deleted(self):
        self.ir['audio']['utterances']=[]
        self.rejects('E_DIALOGUE_COVERAGE')

    def test_dialogue_duplicated(self):
        line=copy.deepcopy(self.ir['audio']['utterances'][0]);line['id']='D_DUP'
        self.ir['audio']['utterances'].append(line)
        self.rejects('E_DIALOGUE_COVERAGE')

    def test_accidental_overlap(self):
        line=copy.deepcopy(self.ir['audio']['utterances'][0]);line['id']='D_DUP'
        self.ir['audio']['utterances'].append(line)
        self.rejects('E_DIALOGUE_OVERLAP')

    def test_narration_cannot_lipsync(self):
        self.ir['audio']['utterances'][0]['kind']='narration'
        self.rejects('E_VOICE_ROLE')

    def test_offscreen_cannot_lipsync(self):
        self.ir['audio']['utterances'][0]['placement']='off_screen'
        self.rejects('E_OFFSCREEN_LIPS')

    def test_silent_psychology_cannot_emit_voice(self):
        self.ir['shots'][1]['performance'][0]['psychology']['utterance_id']='D_B'
        self.rejects('E_SILENT_PSYCHOLOGY')

    def test_inner_voice_requires_owned_line(self):
        self.ir['shots'][1]['performance'][0]['psychology']['audibility']='internal_voice'
        self.rejects('E_INNER_VOICE')

    def test_audio_cue_sync(self):
        self.ir['audio']['cues'][1]['sync_frame']=30
        self.rejects('E_AUDIO_SYNC')

    def test_audio_cross_shot_range(self):
        self.ir['audio']['cues'][0]['shot_ids']=['S1']
        self.rejects('E_CUE_SHOTS')

    def test_hard_contract_violation(self):
        self.ir['contract'][1]['checks'][0]['value']='A.left_hand'
        self.rejects('E_CONTRACT')

    def test_hard_cannot_be_warning(self):
        self.ir['contract'][0]['fallback']='warn'
        self.rejects('E_HARD_FALLBACK')

    def test_soft_failure_is_recorded(self):
        c=self.ir['contract'][1];c['strength']='soft';c['fallback']='warn';c['checks'][0]['value']='A.left_hand'
        report=self.report()
        self.assertEqual(report['status'],'VALID')
        self.assertIn('W_CONTRACT',[d['code'] for d in report['diagnostics']])
        self.assertEqual(report['contract_results'][1]['structure'],'FAIL')

    def test_unverified_hard_source(self):
        self.ir['sources'][0]['verification']='unverified'
        self.rejects('E_HARD_SOURCE')

    def test_unknown_style(self):
        self.ir['style']['primary']='master_magic'
        self.rejects('E_STYLE_UNKNOWN')

    def test_forbidden_style(self):
        self.ir['style']['forbidden']=['transparent']
        self.rejects('E_STYLE_FORBIDDEN')

    def test_incompatible_global_styles(self):
        self.ir['style']['primary']='action';self.ir['style']['modifiers']=['subjective']
        self.rejects('E_STYLE_CONFLICT')

    def test_route_explains_and_obeys_exclusions(self):
        result=sb.route('悬疑 人物对话',['suspense'])
        self.assertNotEqual(result['suggested'],'suspense')
        self.assertFalse(result['quality_prediction'])
        self.assertTrue(any(x['matched_tags'] for x in result['candidates']))

    def test_required_reference_blocks_without_claiming_generation(self):
        self.ir=sb.read(self.base/'missing-reference.ir.json')
        report=self.report()
        self.assertEqual(report['status'],'BLOCKED')
        self.assertEqual(report['structure'],'PASS')

    def test_optional_reference_does_not_block(self):
        self.ir=sb.read(self.base/'missing-reference.ir.json')
        self.ir['bindings'][0]['required']=False
        self.assertEqual(self.report()['status'],'VALID')

    def test_missing_asset_cannot_be_available(self):
        self.ir=sb.read(self.base/'missing-reference.ir.json')
        self.ir['assets'][0]['status']='available'
        self.rejects('E_ASSET_FILE')

    def test_conflicting_asset_versions(self):
        self.ir=sb.read(self.base/'missing-reference.ir.json')
        a=copy.deepcopy(self.ir['assets'][0]);a['id']='REF_A2';a['revision']='2';self.ir['assets'].append(a)
        b=copy.deepcopy(self.ir['bindings'][0]);b['id']='BIND_A2';b['asset_id']='REF_A2';self.ir['bindings'].append(b)
        self.rejects('E_ASSET_CONFLICT')

    def test_hard_geometry_requires_execution_evidence(self):
        self.ir['shots'][0]['camera']['precision']='controlled_previs'
        self.assertEqual(self.report()['status'],'BLOCKED')

    def test_json_pointer_escaping_and_strict_indices(self):
        self.assertEqual(sb.pointer({'a/b':{'~':[3]}},'/a~1b/~0/0'),3)
        for path in ('/-1','/01','/x~2'):
            with self.assertRaises((KeyError,IndexError)):
                sb.pointer([1,2],path)
        self.assertFalse(sb.assertion({'v':True},dict(path='/v',op='equals',value=1)))

    def test_upstream_lock_and_hash(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'director.json'
            # Small transport fixture, not a claimed complete DirectorIR.
            original={'schema_version':'1.0','project_id':self.ir['project_id'],'revision':1,'canon_ref':self.ir['canon_ref']}
            p.write_bytes(sb.encoded(original))
            self.ir['upstreams']=[dict(id='UP_DIR',kind='director',uri=str(p),sha256=sha256(p.read_bytes()).hexdigest(),schema_version='1.0',project_id=self.ir['project_id'],revision='1',locks=[dict(source_pointer='/canon_ref',source_value=self.ir['canon_ref'],target_pointer='/canon_ref',target_value=self.ir['canon_ref'],mode='equal',reason='测试只读字段绑定')])]
            self.assertEqual(self.report()['status'],'VALID')
            self.ir['canon_ref']='other://canon'
            self.rejects('E_UPSTREAM_LOCK')
            p.write_text('{}')
            self.rejects('E_UPSTREAM_HASH')

    def test_compile_is_deterministic_and_retains_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            a,b=Path(td)/'a',Path(td)/'b'
            sb.compile_package(self.ir,self.base,a);sb.compile_package(self.ir,self.base,b)
            self.assertEqual({p.name:p.read_bytes() for p in a.iterdir()},{p.name:p.read_bytes() for p in b.iterdir()})
            self.assertEqual(sb.verify(a)['status'],'VERIFIED')
            self.assertEqual(sb.read(a/'storyboard.ir.json'),self.ir)
            text=(a/'storyboard.md').read_text()
            self.assertIn('B：“你确定？”',text)
            self.assertIn(self.ir['shots'][1]['performance'][0]['micro_expression'],text)
            handoff=sb.read(a/'compiler-handoff.json')
            self.assertEqual(handoff['target']['negotiation'],'REQUIRED')
            self.assertFalse(handoff['submitted'])

    def test_invalid_compile_has_no_handoff(self):
        self.ir['audio']['utterances'][0]['text']='改变原词'
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'invalid'
            sb.compile_package(self.ir,self.base,out)
            self.assertEqual([p.name for p in out.iterdir()],['qa.report.json'])

    def test_blocked_compile_is_reviewable(self):
        self.ir=sb.read(self.base/'missing-reference.ir.json')
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'blocked'
            sb.compile_package(self.ir,self.base,out)
            self.assertEqual(sb.read(out/'compiler-handoff.json')['status'],'BLOCKED')
            self.assertIn('A参考图.png',(out/'storyboard.md').read_text())
            self.assertEqual(sb.verify(out)['status'],'VERIFIED')

    def test_nonempty_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'user.txt';p.write_text('keep')
            with self.assertRaises(ValueError):
                sb.compile_package(self.ir,self.base,td)
            self.assertEqual(p.read_text(),'keep')

    def test_tampering_detected(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'build';sb.compile_package(self.ir,self.base,out)
            (out/'storyboard.md').write_text('altered')
            with self.assertRaisesRegex(ValueError,'E_PACKAGE_HASH'):
                sb.verify(out)

    def test_unlisted_file_detected(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'build';sb.compile_package(self.ir,self.base,out)
            (out/'unlisted.txt').write_text('extra')
            with self.assertRaisesRegex(ValueError,'E_PACKAGE_MEMBERS'):
                sb.verify(out)

    def test_cli_exit_and_malformed_json(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.json';p.write_text('{bad json')
            proc=subprocess.run([sys.executable,str(sb.ROOT/'scripts/storyboard.py'),'inspect',str(p)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,2)
            self.assertEqual(json.loads(proc.stdout)['status'],'ERROR')

    def test_release_repeatable_single_root(self):
        with tempfile.TemporaryDirectory() as td:
            a,b=Path(td)/'a',Path(td)/'b'
            first,second=pkg.build(a),pkg.build(b)
            self.assertEqual(first['sha256'],second['sha256'])
            self.assertEqual((a/'storyboard-grammar.skill-manifest.json').read_bytes(),(b/'storyboard-grammar.skill-manifest.json').read_bytes())
            manifest=json.loads((a/'storyboard-grammar.skill-manifest.json').read_text())
            self.assertTrue(all(p.startswith('storyboard-grammar/') for p in manifest['files']))
            self.assertFalse(any('/outputs/' in p or '__pycache__' in p for p in manifest['files']))

    def test_release_archive_corruption(self):
        with tempfile.TemporaryDirectory() as td:
            pkg.build(td)
            archive=Path(td)/'storyboard-grammar.skill'
            archive.write_bytes(archive.read_bytes()+b'altered')
            with self.assertRaisesRegex(ValueError,'Archive checksum'):
                pkg.verify(td)

    def test_release_manifest_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            pkg.build(td)
            path=Path(td)/'storyboard-grammar.skill-manifest.json'
            manifest=json.loads(path.read_text());manifest['file_count']+=1;path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'member list'):
                pkg.verify(td)


if __name__=='__main__':
    unittest.main()
