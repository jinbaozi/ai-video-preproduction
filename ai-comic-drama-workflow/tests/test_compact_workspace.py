"""Storage/context regression. Authored fixtures are not LLM or media-quality evidence."""
import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from ai_comic_drama_workflow import workspace, transactions as tx
from ai_comic_drama_workflow.lean import start, step
from ai_comic_drama_workflow.v5 import V5Kernel
from ai_comic_drama_workflow.v5_cli import main
from ai_comic_drama_workflow.v5_modules import ROOT, read, digest_file
sys.path.insert(0, str(ROOT/'tests'))
import test_v5_workflow as native_fixture
from test_v5_workflow import FIXTURE, submit_fixture, result_for, seed_until, save
import test_craft_end_to_end as craft_fixture


def stats(kernel, payloads):
    files=[p for p in kernel.root.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    content=[p for p in files if not any(x in p.parts for x in ('modules','module-archives'))]
    return {'task_bytes':sum(len(json.dumps(t,ensure_ascii=False).encode()) for t in payloads),
            'handoff_bytes':sum(len(json.dumps(t['handoff'],ensure_ascii=False).encode()) for t in payloads),
            'files':len(files),'content_files':len(content),'content_bytes':sum(p.stat().st_size for p in content)}


def fixture_run(base, compact=True):
    author=base/'author';shutil.copytree(FIXTURE,author)
    kernel=V5Kernel.initialize(base/'project',[str(author/'cafe.source.txt')],project_id='CAFE_DEMO',
        delivery='text-only',target='agnes-video-2.5',workflow_profile='lean',
        output_policy=workspace.POLICY if compact else None)
    payloads=[]
    for _ in range(18):
        result=kernel.run()
        if result['status']=='DELIVERED':break
        if 'task' not in result:raise AssertionError(result)
        task=result['task'];payloads.append(task)
        submit_fixture(kernel,author,task)
        # Reopen on every step: continuation cannot depend on process memory.
        kernel=V5Kernel(kernel.root)
    else:raise AssertionError('Fixture did not converge')
    if not kernel.validate(True)['valid']:raise AssertionError(kernel.validate(True))
    return kernel,payloads


class CompactWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'project'

    def kernel(self, **kwargs):
        return V5Kernel.initialize(self.root,['Original source'],workflow_profile='lean',
                                   output_policy=workspace.POLICY,**kwargs)

    def test_default_start_is_ordered_and_lazy(self):
        response=start(self.root,['Example'],delivery='text-only')
        self.assertEqual(read(self.root/'project.json')['output_policy'],workspace.POLICY)
        self.assertTrue((self.root/'01-source').is_dir())
        self.assertFalse((self.root/'02-screenplay').exists())
        self.assertTrue((self.root/'.runtime').is_dir())
        self.assertFalse((self.root/'runtime').exists())
        self.assertFalse((self.root/'manifest.json').exists())
        self.assertFalse((self.root/'phase-index.json').exists())
        self.assertEqual(response['progress']['stage'],1)
        self.assertNotIn('required_reads',response)
        self.assertEqual(step(self.root)['task_file'],response['task_file'])

    def test_audit_output_is_explicit_legacy_compatibility(self):
        start(self.root,['Example'],output_profile='audit')
        self.assertNotIn('output_policy',read(self.root/'project.json'))
        self.assertTrue((self.root/'manifest.json').is_file())
        self.assertTrue((self.root/'runtime').is_dir())

    def test_audited_cannot_silently_discard_evidence(self):
        with self.assertRaisesRegex(ValueError,'Audited'):
            start(self.root,['Example'],profile='audited',output_profile='compact')
        self.assertFalse(self.root.exists())

    def test_existing_init_remains_unchanged(self):
        k=V5Kernel.initialize(self.root,['Example'])
        self.assertNotIn('output_policy',k.project)
        self.assertTrue((self.root/'sources').is_dir())

    def test_policy_removal_and_downgrade_are_rejected(self):
        k=self.kernel();config=read(self.root/'project.json');config.pop('output_policy')
        save(self.root/'project.json',config)
        with self.assertRaisesRegex(ValueError,'Frozen'):k.run()
        with self.assertRaisesRegex(ValueError,'Frozen'):V5Kernel(self.root).run()

    def test_source_tamper_remains_blocker_and_progress_survives_restart(self):
        k=self.kernel();k.run()
        k.path(k.state['sources'][0]['uri']).write_text('tampered')
        self.assertEqual(k.run()['status'],'BLOCKED')
        view=workspace.progress(V5Kernel(self.root))
        self.assertEqual(view['status'],'BLOCKED')
        self.assertIn('Source',view['reason'])
        self.assertIn('BLOCKED',(self.root/'00-progress.md').read_text())

    def test_empty_missing_and_unreadable_task_progress_is_blocked(self):
        k=self.kernel();task=k.run()['task']
        path=k.path('runtime/tasks/'+task['task_id']+'.json')
        for content in ('{}','[]','{invalid',None):
            with self.subTest(content=content):
                if content is None:path.unlink()
                else:path.write_text(content)
                view=workspace.progress(V5Kernel(self.root))
                self.assertEqual(view['status'],'BLOCKED')
                self.assertIn('Task envelope',view['reason'])
                workspace.update_progress(k)
                self.assertIn('BLOCKED',(self.root/'00-progress.md').read_text())

    def test_symlink_escape_remains_rejected(self):
        k=self.kernel();external=self.base/'outside';external.mkdir()
        (self.root/'02-screenplay').symlink_to(external,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'escapes'):k.write('02-screenplay/bad.json',{})
        with self.assertRaises(ValueError):k.path('../bad')

    def test_duplicate_result_hash_gate_unchanged(self):
        k=self.kernel();t=k.run()['task'];p=save(self.base/'canon.json',{'project_id':k.project['project_id'],'content':'Original source','source_refs':[k.state['sources'][0]['id']],'entities':[],'locks':[]})
        result=result_for(t,artifact=str(p),artifact_sha256=digest_file(p))
        k.submit(result)
        self.assertEqual(V5Kernel(self.root).submit(result)['status'],'ALREADY_ACCEPTED')
        with self.assertRaisesRegex(ValueError,'Conflicting duplicate'):k.submit({**result,'complete':False})

    def test_cli_stdin_submission_no_extra_result_file(self):
        k=self.kernel();t=k.run()['task'];p=save(self.base/'canon.json',{'project_id':k.project['project_id'],'content':'Original source','source_refs':[k.state['sources'][0]['id']],'entities':[],'locks':[]})
        result=result_for(t,artifact=str(p),artifact_sha256=digest_file(p))
        with patch('sys.stdin',io.StringIO(json.dumps(result))),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['step',str(self.root),'--result','-']),0)
        reply=json.loads(output.getvalue());self.assertEqual(reply['task']['kind'],'screenplay')
        self.assertEqual(len(list((self.root/'.runtime/results').glob('*.json'))),1)
        self.assertFalse((self.root/'result.json').exists())

    def test_stdin_rejects_duplicate_json_keys(self):
        self.kernel()
        with patch('sys.stdin',io.StringIO('{"task_id":"a","task_id":"b"}')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['step',str(self.root),'--result','-']),1)

    def test_snapshot_reuses_source_and_native_dependency(self):
        k=self.kernel();source=k.path(k.state['sources'][0]['uri'])
        obj={'content':'draft','sources':[{'uri':str(source)}]}
        file=save(self.base/'canon.json',obj);uri,files=k.snapshot('canon',file)
        self.assertIn(k.state['sources'][0]['uri'],files)
        self.assertEqual(read(k.path(uri))['sources'][0]['uri'],str(source))
        self.assertEqual(len(files),2)
        self.assertEqual(k.path(uri).read_bytes(),file.read_bytes())
        self.assertIn('/v001/',uri)
        self.assertFalse((self.root/'.runtime/originals').exists())

    def test_external_import_raw_kept_once_and_author_untouched(self):
        k=self.kernel();source=self.base/'outside.txt';source.write_text('outside')
        file=save(self.base/'canon.json',{'content':'draft','sources':[{'uri':'outside.txt'}]})
        raw=file.read_bytes();uri,files=k.snapshot('canon',file)
        originals=list((self.root/'.runtime/originals').glob('*.json'))
        self.assertEqual(len(originals),1);self.assertEqual(originals[0].read_bytes(),raw)
        self.assertEqual(file.read_bytes(),raw)
        self.assertNotEqual(read(k.path(uri))['sources'][0]['uri'],'outside.txt')
        k.snapshot('canon',file)
        self.assertEqual(len(list((self.root/'.runtime/originals').glob('*.json'))),1)

    def test_same_source_name_different_bytes_not_deduplicated(self):
        k=self.kernel();uris=[]
        for name,body in [('a','one'),('b','two')]:
            folder=self.base/name;folder.mkdir();(folder/'source.txt').write_text(body)
            file=save(folder/'item.json',{'sources':[{'uri':'source.txt'}]})
            # Distinct root slots model two independent scene artifacts.
            uri,_=k.snapshot('art',file,slot='art:'+name);uris.append(read(k.path(uri))['sources'][0]['uri'])
        self.assertNotEqual(*uris)

    def test_reserved_output_needs_no_second_native_copy(self):
        k=self.kernel();task=k.run()['task'];p=Path(task['output_file'])
        save(p,{'project_id':k.project['project_id'],'content':'Original source',
                'source_refs':[k.state['sources'][0]['id']],'entities':[],'locks':[]})
        original=p.read_bytes()
        k.submit(result_for(task,artifact=str(p),artifact_sha256=digest_file(p)))
        row=k.state['artifacts']['canon']
        self.assertEqual(k.path(row['uri']),p)
        self.assertEqual(p.read_bytes(),original)
        self.assertEqual(len(list((self.root/'01-source').rglob('*.json'))),1)
        self.assertFalse((self.root/'.runtime/originals').exists())

    def test_reserved_output_rebase_preserves_original_hash(self):
        k=self.kernel();task=k.run()['task'];p=Path(task['output_file'])
        dep=self.base/'dep.txt';dep.write_text('dependent bytes')
        save(p,{'project_id':k.project['project_id'],'content':'Original source',
                'source_refs':[k.state['sources'][0]['id']],'entities':[],'locks':[],
                'sources':[{'uri':str(dep)}]})
        raw=p.read_bytes();sha=digest_file(p)
        result=result_for(task,artifact=str(p),artifact_sha256=sha)
        k.submit(result);row=k.state['artifacts']['canon']
        self.assertEqual(row['original_sha256'],sha)
        self.assertEqual(k.path(row['uri']),p)
        self.assertEqual(k.path('.runtime/originals/'+sha+'.json').read_bytes(),raw)
        self.assertNotEqual(row['sha256'],sha)
        self.assertTrue(k.valid('canon'))
        self.assertEqual(k.submit(result)['status'],'ALREADY_ACCEPTED')

    def test_explicit_module_update_does_not_restore_duplicate_index(self):
        k=self.kernel()
        k.update_modules(ROOT/'modules.lock.json',ROOT/'assets/bundled-skills')
        self.assertFalse((self.root/'phase-index.json').exists())
        self.assertFalse((self.root/'manifest.json').exists())

    def test_content_addressed_dependency_tamper_is_not_repaired(self):
        k=self.kernel();source=self.base/'dep.txt';source.write_text('original')
        file=save(self.base/'canon.json',{'sources':[{'uri':'dep.txt'}]})
        uri,_=k.snapshot('canon',file);dep=Path(read(k.path(uri))['sources'][0]['uri']);dep.write_text('tampered')
        with self.assertRaisesRegex(ValueError,'modified'):k.snapshot('canon',file)
        self.assertEqual(dep.read_text(),'tampered')

    def test_equal_external_bytes_with_different_names_share_one_object(self):
        k=self.kernel();a=self.base/'a.txt';b=self.base/'b.txt'
        a.write_text('same bytes');b.write_text('same bytes')
        file=save(self.base/'canon.json',{'sources':[{'uri':str(a)},{'uri':str(b)}]})
        uri,_=k.snapshot('canon',file)
        refs=read(k.path(uri))['sources']
        self.assertEqual(refs[0]['uri'],refs[1]['uri'])
        self.assertEqual(len(list((self.root/'.runtime/objects').rglob('*.txt'))),1)

    def test_cyclic_native_import_fails_closed(self):
        k=self.kernel();file=save(self.base/'cycle.json',{'upstreams':[{'uri':'cycle.json'}]})
        with self.assertRaisesRegex(ValueError,'Cyclic'):k.snapshot('director',file)

    def test_transaction_commit_rollback_and_failed_recovery(self):
        k=self.kernel();target=k.path('runtime/value.txt');k.write('runtime/value.txt',b'old')
        with self.assertRaises(ValueError):
            with tx.transaction(k.root):
                k.write('runtime/value.txt',b'new');raise ValueError('rollback')
        self.assertEqual(target.read_bytes(),b'old')
        self.assertFalse(list((self.root/'.runtime/transactions').glob('*.pending.json')))
        with patch.object(tx,'_restore',side_effect=OSError('test disk error')):
            with self.assertRaises(OSError):
                with tx.transaction(k.root):
                    k.write('runtime/value.txt',b'new');raise ValueError('rollback')
        self.assertTrue(list((self.root/'.runtime/transactions').glob('*.pending.json')))
        self.assertTrue(list((self.root/'.runtime/transactions').rglob('*.backup')))
        with tx.transaction(k.root):pass
        self.assertEqual(target.read_bytes(),b'old')

    def test_production_storage_and_no_video_claim(self):
        from ai_comic_drama_workflow.production import ProductionLedger
        k=self.kernel(production_target='video');ledger=ProductionLedger(k)
        self.assertEqual(ledger.root,k.path('runtime/production'))
        self.assertEqual(k.path('runtime/production/media/take.mp4'),self.root/'10-video/media/take.mp4')
        self.assertFalse(workspace.progress(k)['video_complete'])

    def test_context_stale_and_invalid_pointer_block(self):
        k=self.kernel();t=k.run()['task'];p=save(self.base/'canon.json',{'project_id':k.project['project_id'],'content':'Original source','source_refs':[k.state['sources'][0]['id']],'entities':[],'locks':[]})
        k.submit(result_for(t,artifact=str(p),artifact_sha256=digest_file(p)))
        before=set(self.root.rglob('*'))
        self.assertEqual(workspace.context(k,'canon','/content')['value'],'Original source')
        self.assertEqual(set(self.root.rglob('*')),before)
        with self.assertRaises(KeyError):workspace.context(k,'canon','/missing')
        with self.assertRaises(ValueError):workspace.context(k,None,'/content')
        k.path(k.state['artifacts']['canon']['uri']).write_text('{}')
        with self.assertRaisesRegex(ValueError,'stale'):workspace.context(k,'canon')


class CompactIntegrationTests(unittest.TestCase):
    def test_native_end_to_end_context_and_storage_reduction(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy,old=fixture_run(Path(tmp)/'legacy',False)
            current,new=fixture_run(Path(tmp)/'compact',True)
            baseline,observed=stats(legacy,old),stats(current,new)
            self.assertLess(observed['handoff_bytes'],baseline['handoff_bytes']*.6)
            self.assertLess(observed['content_files'],baseline['content_files'])
            self.assertLess(observed['content_bytes'],baseline['content_bytes']*.85)
            self.assertFalse((current.root/'09-delivery/index.json').exists())
            self.assertTrue((current.root/'09-delivery/index.md').is_file())
            self.assertEqual(workspace.progress(current)['status'],'DELIVERED')
            self.assertEqual(workspace.progress(current)['stage'],9)
            for task in new:
                for item in task['handoff']['inputs']:
                    for field in item['fields'].values():self.assertNotIn('value',field)
            # Only paths vary; native dialogue/body controls remain in both real compiled outputs.
            for kernel in (legacy,current):
                text=(kernel.path(kernel.state['build']['uri'])/'compiled/prompt.txt').read_text()
                self.assertIn('你确定？',text);self.assertIn('B.right_hand',text)
            # Final user-facing Markdown links resolve inside the project.
            for document in (current.root/'00-progress.md',current.root/'09-delivery/index.md'):
                from urllib.parse import unquote
                for uri in re.findall(r'\]\(([^)]+)\)',document.read_text()):
                    self.assertTrue((document.parent/unquote(uri)).exists(),(document,uri))
            before=current.state['build'];self.assertEqual(current.run()['status'],'DELIVERED')
            self.assertEqual(current.state['build'],before)
            # A targeted revision returns to its real phase without erasing unaffected source files.
            source=current.path(current.state['sources'][0]['uri']);original=source.read_bytes()
            current.revise('director');task=current.run()['task']
            self.assertEqual(task['kind'],'director')
            self.assertEqual(workspace.progress(current)['stage'],3)
            self.assertEqual(source.read_bytes(),original)
            current.path('runtime/tasks/'+task['task_id']+'.json').write_text('{}')
            self.assertEqual(workspace.progress(current)['status'],'BLOCKED')

    def test_compact_image_registration_uses_real_decoder_and_preserves_approval_gate(self):
        initialize=V5Kernel.initialize
        def compact_initialize(*args,**kwargs):
            kwargs.update(workflow_profile='lean',output_policy=workspace.POLICY)
            return initialize(*args,**kwargs)
        case=native_fixture.V5Tests()
        with patch.object(V5Kernel,'initialize',side_effect=compact_initialize):
            case.setUp()
        try:
            case.test_image_registration_recovers_once_and_approval_binds_version()
            self.assertTrue(case.k.state['media'])
            self.assertTrue(all(m['uri'].startswith('05-assets/') for m in case.k.state['media'].values()))
            self.assertFalse((case.k.root/'assets').exists())
        finally:case.doCleanups()

    def test_adaptive_control_text_plan_keeps_ordered_inputs_and_not_run_media(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from run_v5_example import run_example
        initialize=V5Kernel.initialize
        def compact_initialize(*args,**kwargs):
            kwargs.update(workflow_profile='lean',output_policy=workspace.POLICY)
            return initialize(*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp, patch.object(V5Kernel,'initialize',side_effect=compact_initialize):
            result=run_example(Path(tmp)/'fixture','v52','lean',control_policy='adaptive-control/1.0')
            self.assertEqual(result['status'],'DELIVERED')
            k=V5Kernel(Path(tmp)/'fixture/project')
            self.assertTrue(k.state['control']['uri'].startswith('06-storyboard/'))
            self.assertEqual(k.state['control']['materials']['status'],'PLANNED_NOT_RENDERED')
            self.assertTrue(k.validate(True)['valid'])
            self.assertFalse(workspace.progress(k)['video_complete'])

    def test_default_craft_gate_end_to_end_without_duplicate_plan_files(self):
        initialize=V5Kernel.initialize
        seen=[]
        def compact_initialize(*args,**kwargs):
            kwargs.update(workflow_profile='lean',output_policy=workspace.POLICY)
            k=initialize(*args,**kwargs);seen.append(k)
            return k
        # Only creation options change; every native validator and craft gate runs for real.
        update=workspace.update_progress
        def check_embedded(kernel, outcome=None):
            self.assertFalse(kernel.path('runtime/craft').exists())
            return update(kernel, outcome)
        with patch.object(V5Kernel,'initialize',side_effect=compact_initialize), patch.object(workspace,'update_progress',side_effect=check_embedded):
            craft_fixture.CraftEndToEndTests().test_native_text_delivery_retains_craft_proofs_without_media_claim()
        self.assertTrue(seen)
