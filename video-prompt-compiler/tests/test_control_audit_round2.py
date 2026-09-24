"""Reproduce external round-2 findings against native AVIR and decoded media."""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
import test_shot_control as fixtures
import spatial_runtime as spatial
from shot_control.common import read, write, sha, digest, schema_check
from shot_control.control_plan import build
from shot_control.control_lowering import lower
from shot_control.package import recipe, verify_package, validate_config, validate_source
from shot_control.control_plan import frame
from shot_control.joint_compile import compile_package


class AuditRound2Tests(unittest.TestCase):
    setUp = fixtures.ShotControlTests.setUp
    artifact = fixtures.ShotControlTests.artifact
    manifest = fixtures.ShotControlTests.manifest

    def source_file(self):
        self.ir['timeline']['semantic_review']['input_sha256'] = spatial.content_hash(self.ir)
        path = Path(self.tmp.name)/'source.json'
        write(path, self.ir)
        shutil.copyfile(self.source.parent/'cafe.source.txt', path.parent/'cafe.source.txt')
        return path

    def config(self, channel='image_reference', ids=None, requirement='REQ_CAST'):
        c = {'id':'C','requirement_id':requirement,'source_pointers':['/entities'], 'shot_ids':['S2'],
             'channel':channel,'artifact_ids':ids or ['A'],'hardness':'hard','fallback_policy':'block','purpose':'supplement'}
        return {'schema':'shot-control-config/0.2','lenses':{s['id']:self.lens for s in self.ir['shots']},'controls':[c]}, c

    def test_native_reference_contract_has_typed_obligation_and_joint_mapping(self):
        config,c = self.config(requirement='REF_B');c['source_pointers']=['/bindings']
        a = self.artifact(config,c,role='identity')
        # The artifact helper defaults to K1; preserve stable native and media IDs.
        c['artifact_ids']=[a['id']]
        self.ir['assets']=[{'id':a['id'],'kind':'image','filename':a['path'],'path':a['path'],'sha256':a['sha256'],
                            'public_url':None,'inspection':'observed','source_refs':['DESIGN']}]
        self.ir['bindings']=[{'id':'REF_BIND','asset_id':a['id'],'target_id':'B','shot_ids':['S2'],
                             'roles':['identity'],'negative_roles':[],'source_refs':['DESIGN']}]
        clause=deepcopy(next(x for x in self.ir['contract'] if x['id']=='REQ_CAST'))
        clause.update(id='REF_B',channel='reference',shot_ids=['S2'],requirement='Keep the observed B identity reference',
                      checks=[{'op':'exists','path':'/bindings','value':None}])
        self.ir['contract'].append(clause)
        for u in a['uses']:u['recipe_sha256']=recipe(self.ir,config,c,u['shot_id'],a['role'],u['start_ms'],u['end_ms'])
        a['review']['uses_sha256']=digest(a['uses'])
        build(self.source_file(),self.out,config);manifest=self.manifest(a)
        result=lower(self.out,'agnes-video-2.5','reference',manifest,{'start_ms':4000,'end_ms':8000})
        self.assertEqual(result['status'],'BOUND_DRAFT')
        obligation=next(x for x in result['primary_obligations'] if x['requirement_id']=='REF_B')
        self.assertEqual((obligation['type'],obligation['status']),('visual_reference','NOT_COMPILED'))
        compiled=compile_package(self.out,'agnes-video-2.5','reference',manifest,['S2'])
        self.assertEqual(compiled['status'],'COMPILED_DRAFT',compiled['reasons'])
        row=next(x for x in compiled['requests'][0]['primary_obligations'] if x['requirement_id']=='REF_B')
        self.assertEqual(row['status'],'REFERENCES_MAPPED')
        self.assertEqual(row['evidence'][0]['label'],'<Picture 1>')
        without=deepcopy(config);without['controls']=[]
        other=Path(self.tmp.name)/'no-media-control';build(self.source_file(),other,without)
        pending=lower(other,'agnes-video-2.5','text',manifest,{'start_ms':4000,'end_ms':8000})
        self.assertEqual(next(x for x in pending['primary_obligations'] if x['requirement_id']=='REF_B')['status'],'NOT_COMPILED')

    def test_video_role_cannot_escape_temporal_dependency(self):
        config,c=self.config('clay_video_reference',['V'])
        path=Path(self.tmp.name)/'V.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=256x256:r=24','-t','4','-pix_fmt','yuv420p',str(path)],check=True)
        build(self.source,self.out,config)
        for role in ['clay','identity','appearance','style','scene']:
            uses=[{'control_id':'C','shot_id':'S2','start_ms':4000,'end_ms':8000,'recipe_sha256':recipe(self.ir,config,c,'S2',role,4000,8000)}]
            a={'id':'V','path':path.name,'sha256':sha(path),'source_sha256':sha(self.source),'kind':'video','role':role,'uses':uses,
               'review':{'sha256':sha(path),'uses_sha256':digest(uses),'reviewer':'synthetic test','result':'PASS','checks':['Fixture only']},
               'binding':{'sha256':sha(path),'url':'https://example.com/video.mp4','receipt':'fixture only'}}
            result=lower(self.out,'agnes-video-2.5','reference',self.manifest(a),{'start_ms':4000,'end_ms':8000})
            self.assertEqual(result['status'],'BOUND_DRAFT' if role=='clay' else 'BLOCKED',role)
            changed=deepcopy(config);changed['lenses']['S2']['vertical_fov_deg']=60
            self.assertNotEqual(uses[0]['recipe_sha256'],recipe(self.ir,changed,c,'S2',role,4000,8000))

    def test_url_fragment_rejected_but_distinct_queries_preserved(self):
        config,c=self.config(ids=['A','B']);build(self.source,self.out,config)
        for suffix,expected in [('#','BLOCKED'),('?v=','BOUND_DRAFT')]:
            a=self.artifact(config,c,'A',content=100,url='https://example.com/shared.png'+suffix+'a')
            b=self.artifact(config,c,'B',content=200,url='https://example.com/shared.png'+suffix+'b')
            result=lower(self.out,'agnes-video-2.5','reference',self.manifest(a,b),{'start_ms':4000,'end_ms':8000})
            self.assertEqual(result['status'],expected,result['reasons'])
            if expected=='BOUND_DRAFT':self.assertEqual(len(result['media_fields_draft']['images']),2)

    def test_resealed_review_html_and_svg_are_rederived(self):
        config,c=self.config();build(self.source,self.out,config)
        for name in ['review/index.html','review/blocking-001.svg']:
            path=self.out/name;original=path.read_text();manifest=read(self.out/'package-manifest.json')
            path.write_text(original.replace('N_A','MISLABELED_ACTOR') if name.endswith('html') else original.replace('>A<','>MISLABELED_ACTOR<'))
            self.assertNotEqual(path.read_text(),original)
            manifest['files'][name]=sha(path);write(self.out/'package-manifest.json',manifest)
            with self.assertRaisesRegex(ValueError,'Derived review'):verify_package(self.out)
            path.write_text(original);manifest['files'][name]=sha(path);write(self.out/'package-manifest.json',manifest)
        verify_package(self.out)

    def test_delivery_aspect_matches_explicit_crop_and_missing_lens_preview(self):
        config,c=self.config()
        self.ir['output']['aspect_ratio']='9:16'
        with self.assertRaisesRegex(ValueError,'native delivery aspect'):validate_config(self.ir,config)
        for lens in config['lenses'].values():lens.update(crop=[0,0,(9/16)/(16/9),1])
        validate_config(self.ir,config)
        self.assertEqual(frame(self.ir,self.ir['shots'][0],0,{})['camera']['output_aspect'],9/16)
        for ratio,value in [('16:9',16/9),('9:16',9/16),('1:1',1)]:
            self.ir['output']['aspect_ratio']=ratio
            for lens in config['lenses'].values():lens.update(aspect=value,crop=[0,0,1,1])
            validate_config(self.ir,config)

    def test_degenerate_camera_is_not_ready_for_projection(self):
        shot=self.ir['shots'][0]
        for target in [[0,2.3,-3],[0,.3,-3]]:
            shot['camera']['look_at']=target
            camera=frame(self.ir,shot,0,self.lens)['camera']
            self.assertEqual(camera['status'],'UNDETERMINED')
            self.assertEqual(camera['reason'],'Degenerate camera basis')

    def test_fractional_events_preserved_and_failed_build_not_published(self):
        config,c=self.config()
        self.ir['timeline']['performances'][0]['start_ms']=500.5
        source=self.source_file();build(source,self.out,config)
        bundle=verify_package(self.out)
        self.assertIn(500.5,[r['at_ms'] for r in bundle['requests']])
        review={'schema':'control-media-review/0.2','media_sha256':'0'*64,'reviewer':'Synthetic test',
                'evaluation_plan_sha256':digest(bundle['evaluation']),'observed_points':[],
                'events':[{'id':'performances:PERF1:start','observed_ms':500.5}], 'findings':[]}
        schema_check(review,'control-media-review')
        failed=Path(self.tmp.name)/'failed-build'
        with patch('shot_control.render_blocking.export_review',side_effect=ValueError('injected render failure')):
            with self.assertRaisesRegex(ValueError,'injected'):build(source,failed,config)
        self.assertFalse(failed.exists())
        self.assertEqual(list(failed.parent.glob('.control-build-*')),[])

    def test_first_frame_ignores_unused_entity_and_future_feedback(self):
        config,c=self.config('first_frame',['K']);c['shot_ids']=['S1']
        unused=deepcopy(self.ir['entities'][0]);unused.update(id='UNUSED',label='Unused offscreen person')
        self.ir['entities'].append(unused)
        cast=next(c for c in self.ir['contract'] if c['id']=='REQ_CAST')['checks'][0]
        cast['value']=deepcopy(self.ir['entities'])
        validate_source(self.ir)
        initial=recipe(self.ir,config,c,'S1','clean_keyframe',0,0)
        unused['appearance']='Different unused wardrobe'
        self.assertEqual(recipe(self.ir,config,c,'S1','clean_keyframe',0,0),initial)
        self.ir['timeline']['actions'][1]['feedback']='Future feedback revised without changing the first-frame pose'
        cast['value']=deepcopy(self.ir['entities'])
        validate_source(self.ir)
        self.assertEqual(recipe(self.ir,config,c,'S1','clean_keyframe',0,0),initial)
        self.ir['entities'][0]['appearance']+=' visible identity change'
        self.assertNotEqual(recipe(self.ir,config,c,'S1','clean_keyframe',0,0),initial)
        current=recipe(self.ir,config,c,'S1','clean_keyframe',0,0)
        self.ir['timeline']['motion_tracks'][0]['path']+=' revised active motion intent'
        self.assertNotEqual(recipe(self.ir,config,c,'S1','clean_keyframe',0,0),current)
        end=recipe(self.ir,config,c,'S1','clean_keyframe',4000,4000)
        track=next(t for t in self.ir['timeline']['motion_tracks'] if t['id']=='POS_S1_ENVELOPE')
        track['keyframes'][-1]['value']['value'][0]+=.1
        self.assertNotEqual(recipe(self.ir,config,c,'S1','clean_keyframe',4000,4000),end)

    def test_edge_labels_stay_inside_without_moving_projected_points(self):
        from shot_control.render_blocking import svg
        for aspect in (9/16,1,16/9):
            state=frame(self.ir,self.ir['shots'][0],0,{**self.lens,'aspect':aspect})
            state['points']=state['points'][:4]
            corners=[(0,0),(1,0),(0,1),(1,1)]
            for point,xy in zip(state['points'],corners):
                point['projection']={'status':'IN_FRAME','xy':xy};point['label']='超长角色标记_'+('long_ID_'*30)
            tree=ET.fromstring(svg(state,'camera',1));ns={'s':'http://www.w3.org/2000/svg'}
            for circle,xy in zip(tree.findall('s:circle',ns),corners):
                self.assertAlmostEqual(float(circle.attrib['cx']),xy[0]*360*aspect,places=3)
                self.assertAlmostEqual(float(circle.attrib['cy']),xy[1]*360,places=3)
            for text in tree.findall('s:text',ns):
                self.assertGreaterEqual(float(text.attrib['x']),0)
                self.assertLessEqual(float(text.attrib['x'])+float(text.attrib['textLength']),360*aspect)
                self.assertTrue(13<=float(text.attrib['y'])<=347)
                self.assertEqual(text.find('s:title',ns).text,state['points'][0]['label'])


if __name__=='__main__':unittest.main()
