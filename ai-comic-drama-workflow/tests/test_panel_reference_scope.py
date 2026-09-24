"""Panel reference scope excludes offscreen identities without losing listed props."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch,PropertyMock
from ai_comic_drama_workflow.v5 import V5Kernel

class PanelReferenceScopeTests(TestCase):
 def test_explicit_panel_subjects_and_legacy_fallback(self):
  k=object.__new__(V5Kernel);k.root=Path('/unused')
  ir={'shots':[{'state_start':{'GIRL':{},'OTHER':{},'COAST':{},'HAT':{}},'panels':[{'subject_ids':['GIRL','COAST','HAT']},{}]}]}
  media={eid:dict(key=eid,uri=eid+'.png',sha256=eid,entity_id=eid,stage=5,role='identity' if eid in ('GIRL','OTHER') else 'prop') for eid in ir['shots'][0]['state_start']}
  briefs=[dict(id=str(i),kind='board',shot_id='S1',source_pointer=f'/shots/0/panels/{i}',dependency_paths=[f'/shots/0/panels/{i}']) for i in range(2)]
  with patch.object(V5Kernel,'state',new_callable=PropertyMock,return_value={'artifacts':{},'media':media}),patch.object(V5Kernel,'data',return_value=ir),patch.object(V5Kernel,'dependency',return_value={}),patch.object(V5Kernel,'media_valid',return_value=True),patch.object(V5Kernel,'portable_content',side_effect=lambda x:x),patch('ai_comic_drama_workflow.v5.image_briefs',return_value=briefs),patch('ai_comic_drama_workflow.v5.read',return_value={'modules':{'image-prompt-optimizer':{'sha256':'test'}}}):
   jobs=k.image_jobs(7)
  self.assertEqual({r['entity_id'] for r in jobs[0]['references']},{'GIRL','COAST','HAT'})
  self.assertEqual({r['entity_id'] for r in jobs[1]['references']},set(media))
