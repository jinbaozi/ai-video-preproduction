import copy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from shot_control.common import read,write,sha
from shot_control.control_plan import build
from shot_control.package import verify_package,recipe
from shot_control.craft import derive,export,verify,performance_cues,transform,cube,grade_video,verify_grade,validate_look


def look_fixture():
    return {'schema':'look-design/0.1','owner':'production-design-grammar',
        'material_palette':[{'id':'A_COAT','entity_id':'A','shot_ids':['S1'],'source_pointers':['/entities/0/appearance'],
            'color_srgb':'#24364B','basis':'authored_proxy','evidence':'Synthetic navy swatch interpreting source appearance; not a pixel target'},
            {'id':'B_SHIRT','entity_id':'B','shot_ids':['S1'],'source_pointers':['/entities/1/appearance'],
            'color_srgb':'#D6CCB7','basis':'authored_proxy','evidence':'Synthetic beige swatch; not observed from a generated image'}],
        'grading_plan':[{'shot_id':'S1','source_pointers':['/scenes/0/lighting'],'evidence':'Synthetic neutral grade for local executable pipeline test',
            'exposure_stops':0,'contrast':1,'saturation':1}]}


class CraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.ir=read(ROOT/'examples/v52/cafe.avir.json');self.config={'schema':'shot-control-config/0.2','controls':[],
            'lenses':{s['id']:{'vertical_fov_deg':50,'aspect':16/9,'basis':'authored_proxy','evidence':'Synthetic test'} for s in self.ir['shots']},
            'look_design':look_fixture()}
        shutil.copyfile(ROOT/'examples/v52/cafe.source.txt',self.root/'cafe.source.txt')

    def build(self,folder='package'):
        write(self.root/'source.json',self.ir);build(self.root/'source.json',self.root/folder,self.config)
        export(self.root/folder,self.root/(folder+'-craft'))
        return self.root/(folder+'-craft')

    def test_native_rehearsal_preserves_source_and_visibility_gaps(self):
        craft=self.build();data,_=verify(craft)
        self.assertEqual(len(data['performance_cues']),3)
        self.assertTrue(all(c['status']=='REHEARSAL_REQUEST' for c in data['performance_cues']))
        self.assertEqual(data['performance_cues'][1]['performance'],self.ir['timeline']['performances'][1])
        dialogue=next(a['event'] for a in data['performance_cues'][1]['audio_context'] if a['event']['kind']=='dialogue')
        self.assertEqual(dialogue['route'],'post');self.assertTrue(dialogue['lip_sync'])
        self.assertIn('B：“你确定？”',(craft/'rehearsal.md').read_text())
        self.assertEqual(data['lighting_plan'][0]['source_intent'],self.ir['scenes'][0]['lighting'])
        requests=read(self.root/'package/keyframe-requests.json')
        at=next(r for r in requests if r['shot_id']=='S2' and r['at_ms']==4667)
        self.assertEqual(at['craft_state']['performances'],[self.ir['timeline']['performances'][1]])
        self.assertEqual(at['craft_state']['grading_execution'],'POST_PRODUCTION_NOT_MODEL_PARAMETER')
        ET.fromstring((craft/'color-script.svg').read_text())
        # Test the extra interval coverage check independently: a gap must not be unioned away.
        ir=copy.deepcopy(self.ir);ir['timeline']['composition_tracks'][1]['start_ms']=6000
        cue=next(c for c in performance_cues(ir) if c['id']=='PERF2_S2')
        self.assertEqual(cue['status'],'BLOCKED');self.assertEqual(cue['visibility'][0]['start_ms'],4667)
        ir=copy.deepcopy(self.ir);ir['timeline']['performances'][1]['readability']='detail'
        self.assertEqual(next(c for c in performance_cues(ir) if c['id']=='PERF2_S2')['status'],'BLOCKED')

    def test_look_source_semantics_and_resealed_lut_tamper(self):
        bad=look_fixture();bad['material_palette'][0]['source_pointers']=['/output']
        with self.assertRaises(ValueError):validate_look(self.ir,bad)
        bad=look_fixture();bad['grading_plan']*=2
        with self.assertRaises(ValueError):validate_look(self.ir,bad)
        craft=self.build();lut=craft/'grades/grade-000.cube';lut.write_text(lut.read_text().replace('0.000000000','0.100000000',1))
        manifest=read(craft/'craft-manifest.json');manifest['files']['grades/grade-000.cube']=sha(lut);write(craft/'craft-manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'derivation'):verify(craft)

    def test_linear_grade_and_dependency_scope(self):
        grade=self.config['look_design']['grading_plan'][0]
        for got,want in zip(transform([.12,.3,.6],grade),[.12,.3,.6]):self.assertAlmostEqual(got,want,places=8)
        gray=transform([.12,.3,.6],{**grade,'saturation':0});self.assertAlmostEqual(max(gray)-min(gray),0)
        self.assertTrue(all(0<=x<=1 for x in transform([.9,.8,.7],{**grade,'exposure_stops':4})))
        c={'source_pointers':['/entities/0/appearance']}
        a=recipe(self.ir,self.config,c,'S1','clean_keyframe',0,0)
        b=recipe(self.ir,self.config,c,'S2','clean_keyframe',4000,4000)
        master_control={**c,'channel':'image_reference'}
        master=recipe(self.ir,self.config,master_control,'S1','identity',0,4000)
        grade['exposure_stops']=.5
        self.assertNotEqual(recipe(self.ir,self.config,c,'S1','clean_keyframe',0,0),a)
        self.assertEqual(recipe(self.ir,self.config,c,'S2','clean_keyframe',4000,4000),b)
        self.assertEqual(recipe(self.ir,self.config,master_control,'S1','identity',0,4000),master)

    def video(self,path,tagged=True):
        cmd=['ffmpeg','-v','error','-f','lavfi','-i','color=c=0x426A8F:s=320x180:r=24:d=4',
             '-f','lavfi','-i','sine=frequency=440:duration=4','-c:v','libx264','-crf','0','-c:a','aac','-pix_fmt','yuv420p']
        if tagged:cmd+=['-colorspace','bt709','-color_trc','bt709','-color_primaries','bt709','-color_range','tv',
                       '-x264-params','colorprim=bt709:transfer=bt709:colormatrix=bt709']
        subprocess.run(cmd+[str(path)],check=True,capture_output=True)

    def rgb(self,path):
        r=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-vf','scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24',
                          '-frames:v','1','-f','rawvideo','pipe:1'],check=True,capture_output=True)
        return list(r.stdout[(90*320+160)*3:(90*320+160)*3+3])

    def test_real_video_grade_identity_desaturate_audio_and_unknown_color(self):
        craft=self.build();media=self.root/'source.mp4';self.video(media)
        out=self.root/'identity';self.assertEqual(grade_video(craft,'S1',media,out)['status'],'GRADED_LOCAL')
        self.assertEqual(verify_grade(out)['status'],'VERIFIED_LOCAL_GRADE')
        original=self.rgb(media);neutral=self.rgb(out/'graded.mp4')
        self.assertLessEqual(max(abs(a-b) for a,b in zip(original,neutral)),3)
        # Decode audio packets to confirm the pass-through preserves the signal, not only presence.
        def audio(path):return subprocess.run(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-f','s16le','pipe:1'],check=True,capture_output=True).stdout
        self.assertEqual(audio(media),audio(out/'graded.mp4'))
        self.config['look_design']['grading_plan'][0]['saturation']=0
        graycraft=self.build('gray');gray=self.root/'desaturated';grade_video(graycraft,'S1',media,gray)
        pixel=self.rgb(gray/'graded.mp4');self.assertLessEqual(max(pixel)-min(pixel),3)
        self.assertGreater(max(original)-min(original),20)
        unknown=self.root/'unknown.mp4';self.video(unknown,False)
        with self.assertRaisesRegex(ValueError,'Explicit.*BT709'):grade_video(craft,'S1',unknown,self.root/'bad')
        with (out/'graded.mp4').open('ab') as f:f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):verify_grade(out)


if __name__=='__main__':unittest.main()
