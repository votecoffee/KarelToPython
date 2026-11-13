"""Authored context-shape, preservation and saved-run preparation contracts."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from karel2py import translate, runner
from karel2py.input_template import prepare_inputs, InputTemplateError


ROOT = Path(__file__).resolve().parents[1]
MISSING = {'uninitialized': True}


def prepare(body, decl='x,n:INTEGER', prefix='', context=None):
    result = translate('PROGRAM T '+prefix+' VAR '+decl+' BEGIN '+body+' END T')
    return prepare_inputs(result.python_source, context=context)


def by_path(prepared):
    return {row['path']: row for row in prepared['template']['bindings']}


def pointer(document, path):
    for token in path.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        document = document[int(token)] if type(document) is list else document[token]
    return document


class InputTemplateTests(unittest.TestCase):
    def test_authored_example_matches_independent_context_shape_fixture(self):
        path=ROOT/'examples/discovery_inputs.kl'
        result=prepare_inputs(translate(path.read_text(encoding='utf-8'),filename=path.name).python_source)
        self.assertEqual(result['context'],json.loads(path.with_suffix('.template.expected.json').read_bytes()))

    def test_selected_record_inputs_make_one_whole_root_without_fabricated_values(self):
        result = prepare('n=a.x+a.y',decl='a:item_t n:INTEGER',prefix='TYPE item_t=STRUCTURE x:INTEGER y:INTEGER ENDSTRUCTURE')
        self.assertEqual(result['context']['variables'],[dict(program='T',path='A',
            type=['STRUCTURE','ITEM_T',[['X',['INTEGER']],['Y',['INTEGER']]]],value=dict(X=MISSING,Y=MISSING))])
        rows = by_path(result)
        self.assertEqual(set(rows),{'A.X','A.Y'})
        self.assertEqual(rows['A.X']['context_pointer'],'/variables/0/value')
        self.assertEqual(rows['A.Y']['selectors'],[['field','Y']])
        self.assertEqual({row['status'] for row in rows.values()},{'missing'})
        self.assertIsNot(result['context']['variables'][0]['value']['X'],result['context']['variables'][0]['value']['Y'])

    def test_shapes_for_multidimensional_named_arrays_and_joint_axes(self):
        result = prepare('n=a[2,1,2]+j[3]',decl='a:ARRAY[2,1]OF pair_t j:JOINTPOS3 n:REAL',
                         prefix='TYPE pair_t=ARRAY[2]OF REAL')
        values = {row['path']:row['value'] for row in result['context']['variables']}
        self.assertEqual(values['A'],[[[MISSING,MISSING]],[[MISSING,MISSING]]])
        self.assertEqual(values['J'],{'axes':[MISSING,MISSING,MISSING]})
        self.assertEqual(by_path(result)['A[2][1][2]']['selectors'],[['index',2],['index',1],['index',2]])

    def test_byte_and_builtin_pose_fields_keep_missing_markers(self):
        result = prepare('n=b+j[1]+p.x',decl='b:BYTE j:JOINTPOS2 p:XYZWPREXT n:REAL')
        values = {row['path']:row['value'] for row in result['context']['variables']}
        self.assertEqual(values['B'],{'unknown_byte':True})
        self.assertEqual(set(values['P']),{'X','Y','Z','W','P','R','CONFIG_DATA','EXT1','EXT2','EXT3'})
        self.assertTrue(all(value==MISSING for value in values['P']['CONFIG_DATA'].values()))

    def test_preserves_existing_case_partial_data_and_unrelated_services(self):
        context={'variables':[dict(program='t',path='a',type=['STRUCTURE','ITEM_T',
            [['X',['INTEGER']],['Y',['INTEGER']]]],value={'x':7,'y':MISSING}),
            dict(program='OTHER',path='KEEP',type='INTEGER',value=9)],
            'numeric':{'count':3,'values':{'1':0.1},'comments':{'1':'keep'}},'files':{'seed.txt':'data'}}
        original=deepcopy(context)
        result=prepare('n=a.x+a.y',decl='a:item_t n:INTEGER',prefix='TYPE item_t=STRUCTURE x:INTEGER y:INTEGER ENDSTRUCTURE',context=context)
        self.assertEqual(result['context'],original)
        self.assertEqual(context,original)
        self.assertEqual(by_path(result)['A.X']['status'],'supplied')
        self.assertEqual(by_path(result)['A.Y']['status'],'missing')
        result['context']['variables'][0]['value']['x']=99
        self.assertEqual(context,original)

    def test_existing_root_type_conflicts_are_rejected(self):
        context={'variables':[dict(program='T',path='X',type=['REAL'],value=1.0)]}
        with self.assertRaisesRegex(InputTemplateError,'type differs'):
            prepare('n=x',context=context)

    def test_selected_existing_flat_physical_array_values_are_preserved(self):
        context={'variables':[dict(program='T',path='A',type=['ARRAY',[2,2],['INTEGER']],value=[1,2,3,4])]}
        result=prepare('n=a[2,1]',decl='a:ARRAY[2,2]OF INTEGER n:INTEGER',context=context)
        self.assertEqual(result['context'],context)
        self.assertEqual(by_path(result)['A[2][1]']['status'],'supplied')

    def test_marker_for_entire_existing_aggregate_is_preserved_and_needs_review(self):
        context={'variables':[dict(program='T',path='A',type=['ARRAY',2,['INTEGER']],value=MISSING)]}
        result=prepare('n=a[1]',decl='a:ARRAY[2]OF INTEGER n:INTEGER',context=context)
        self.assertEqual(result['context'],context)
        self.assertEqual(by_path(result)['A[1]']['status'],'missing')

    def test_numeric_string_and_port_inputs_preserve_explicit_bank_values(self):
        context={'numeric':{'count':1,'values':{'1':0.1}},'strings':{'count':1,'values':{'01':'ready'}},
            'ports':{'counts':{'din':1},'values':{'din':{'01':True}}}}
        result=prepare('GET_REG(1,b,n,r,s) GET_STR_REG(1,text,s) b=DIN[1]',
                       decl='b:BOOLEAN n,s:INTEGER r:REAL text:STRING[8]',context=context)
        self.assertEqual(result['context'],context)
        self.assertEqual(result['template']['requirements'],[])
        rows=result['template']['bindings']
        self.assertEqual({row['status'] for row in rows},{'supplied'})
        self.assertEqual({pointer(result['context'],row['context_pointer']) for row in rows},{0.1,'ready',True})

    def test_bank_counts_and_values_are_not_invented(self):
        result=prepare('GET_REG(2,b,n,r,s) GET_STR_REG(3,text,s) b=DIN[4]',decl='b:BOOLEAN n,s:INTEGER r:REAL text:STRING[8]')
        self.assertEqual(result['context'],{})
        self.assertEqual({row['status'] for row in result['template']['bindings']},{'unmapped'})
        self.assertEqual(len([row for row in result['template']['requirements'] if row['code']=='service']),3)

    def test_configured_empty_banks_need_values_and_write_only_banks_need_services(self):
        result=prepare('GET_REG(1,b,n,r,s)',decl='b:BOOLEAN n,s:INTEGER r:REAL',context={'numeric':{'count':1,'values':{}}})
        self.assertEqual(by_path(result)['1']['status'],'missing')
        self.assertEqual([row['code'] for row in result['template']['requirements']],['value'])
        result=prepare('SET_INT_REG(4,42,n)')
        self.assertEqual(result['context'],{})
        self.assertEqual(result['template']['bindings'],[])
        self.assertEqual(result['template']['requirements'][0]['service'],'numeric')

    def test_position_groups_and_noncanonical_existing_addresses(self):
        context={'positions':{'count':2,'groups':[3],'values':{'3:02':{'type':['JOINTPOS',2],'value':{'axes':[1.0,2.0]}}}}}
        result=prepare('p=GET_JPOS_REG(2,s,3)',decl='p:JOINTPOS s:INTEGER',context=context)
        row=result['template']['bindings'][0]
        self.assertEqual((row['status'],row['context_pointer']),('supplied','/positions/values/3:02'))
        self.assertEqual(result['template']['requirements'],[])
        result=prepare('p=GET_POS_REG(2,s)',decl='p:XYZWPREXT s:INTEGER',context=context)
        self.assertEqual(result['template']['bindings'][0]['status'],'unmapped')
        self.assertTrue(any(row['code']=='group' for row in result['template']['requirements']))

    def test_dynamic_and_external_gaps_are_kept_in_the_same_document(self):
        result=prepare('n=a[x]',decl='n,x:INTEGER a:ARRAY[3]OF INTEGER')
        self.assertEqual(set(by_path(result)),{'X'})
        self.assertFalse(result['template']['discovery']['complete'])
        self.assertTrue(result['template']['discovery']['unresolved'])

    def test_root_storage_budget_is_shared_and_reports_skipped_roots(self):
        with mock.patch('karel2py.input_template.MAX_LEAVES',2):
            result=prepare('n=a[1]+b[1]',decl='a,b:ARRAY[2]OF INTEGER n:INTEGER')
        self.assertEqual([row['path'] for row in result['context']['variables']],['A'])
        self.assertEqual(by_path(result)['B[1]']['status'],'unmapped')
        self.assertTrue(any(row['code']=='limit' for row in result['template']['requirements']))

    def test_invalid_existing_context_is_rejected(self):
        for context in ({'numeric':{'count':1,'values':{'1':True}}},{'unknown':True}):
            with self.subTest(context=context),self.assertRaises(InputTemplateError):
                prepare('n=x',context=context)

    def test_preparation_never_executes_or_evaluates_target(self):
        source=translate('PROGRAM T VAR x,n:INTEGER BEGIN n=x END T').python_source
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')):
            with mock.patch('builtins.eval',side_effect=AssertionError('evaluated')):
                self.assertEqual(prepare_inputs(source)['context']['variables'][0]['value'],MISSING)


class InputTemplateRunnerTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.folder=Path(folder.name);self.target=self.folder/'converted.py';self.document=self.folder/'session.json'
        self.target.write_bytes(translate('PROGRAM T VAR x,n:INTEGER BEGIN n=x*2 END T').python_source.encode())

    def test_missing_then_edited_inputs_run_and_replay_without_annotation_updates(self):
        prepared=runner.create_document(self.target,self.document,discover=True)
        self.assertEqual(prepared['inputs']['context']['variables'][0]['value'],MISSING)
        self.assertEqual(runner.run_document(self.document)['results']['status'],'failed')
        prepared['inputs']['context']['variables'][0]['value']=21
        self.document.write_bytes((json.dumps(prepared)+'\n').encode())
        for _ in range(2):
            result=runner.run_document(self.document)
            self.assertEqual(result['results']['variables'],{'X':21,'N':42})
            self.assertEqual(result['inputs'],prepared['inputs'])
        self.assertEqual(prepared['inputs']['template']['bindings'][0]['status'],'missing')

    def test_conditional_missing_input_can_remain_when_branch_is_not_taken(self):
        self.target.write_bytes(translate('PROGRAM T VAR flag:BOOLEAN x,n:INTEGER BEGIN IF flag THEN n=x ELSE n=42 ENDIF END T').python_source.encode())
        prepared=runner.create_document(self.target,self.document,discover=True)
        flag=next(row for row in prepared['inputs']['context']['variables'] if row['path']=='FLAG');flag['value']=False
        self.document.write_bytes(json.dumps(prepared).encode())
        result=runner.run_document(self.document)
        self.assertEqual(result['results']['status'],'completed')
        self.assertEqual(result['results']['variables']['N'],42)

    def test_annotations_pin_source_and_malformed_annotations_preserve_document(self):
        prepared=runner.create_document(self.target,self.document,discover=True)
        for edit in ('hash','shape'):
            data=deepcopy(prepared)
            if edit=='hash':data['inputs']['template']['target']['sha256']='0'*64
            else:data['inputs']['template']['bindings']=[42]
            before=json.dumps(data).encode();self.document.write_bytes(before)
            with mock.patch('builtins.exec',side_effect=AssertionError('executed')):
                with self.assertRaisesRegex(runner.RunDocumentError,'Malformed or stale'):
                    runner.run_document(self.document)
            self.assertEqual(self.document.read_bytes(),before)

    def test_target_race_during_discovery_does_not_publish(self):
        inspected=runner._target(self.target)
        read=runner._read
        def changed(path):
            raw=read(path)
            return raw+b'\n# changed\n' if Path(path)==self.target else raw
        with mock.patch.object(runner,'_read',side_effect=changed):
            with mock.patch.object(runner,'_target',return_value=inspected):
                with self.assertRaisesRegex(runner.RunDocumentError,'changed during'):
                    runner.create_document(self.target,self.document,discover=True)
        self.assertFalse(self.document.exists())

    def test_legacy_target_and_non_boolean_flag_fail_without_publication(self):
        with self.assertRaisesRegex(runner.RunDocumentError,'BOOLEAN'):
            runner.create_document(self.target,self.document,discover=1)
        self.target.write_bytes(b'class Program:\n source_program="T"\n translation_mode="pythonic"\n')
        with self.assertRaisesRegex(ValueError,'Re-translate'):
            runner.create_document(self.target,self.document,discover=True)
        self.assertFalse(self.document.exists())

    def test_failed_publication_and_existing_destination_preserve_previous_bytes(self):
        self.document.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):runner.create_document(self.target,self.document,discover=True)
        self.assertEqual(self.document.read_bytes(),b'keep')
        self.document.unlink()
        with mock.patch.object(runner,'atomic_bytes',side_effect=OSError('synthetic failure')):
            with self.assertRaisesRegex(OSError,'synthetic failure'):
                runner.create_document(self.target,self.document,discover=True)
        self.assertFalse(self.document.exists())

    def test_cli_create_from_context_and_runtime_only_preparation(self):
        context=self.folder/'context.json'
        config={'variables':[dict(program='T',path='X',type=['INTEGER'],value=21)]}
        raw=(json.dumps(config)+'\n').encode();context.write_bytes(raw)
        bootstrap='''import runpy,sys
class RuntimeOnly:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.project','tkinter','_tkinter','karel2py.gui','socket','ssl','http.client','urllib.request'):
   raise ImportError('Preparation needs runtime only')
sys.meta_path.insert(0,RuntimeOnly());sys.path.insert(0,sys.argv[1])
sys.argv=['karel2py.runner','create',sys.argv[2],sys.argv[3],'--discover','--context',sys.argv[4]]
runpy.run_module('karel2py.runner',run_name='__main__')
'''
        process=subprocess.run([sys.executable,'-I','-X','utf8','-c',bootstrap,str(ROOT),str(self.target),str(self.document),str(context)],capture_output=True,text=True,cwd=self.folder)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout),dict(status='prepared',program='T',inputs=1,requirements=0,unresolved=0))
        self.assertEqual(context.read_bytes(),raw)
        saved=json.loads(self.document.read_bytes())
        self.assertEqual(saved['inputs']['context'],config)
        self.assertEqual(runner.run_document(self.document)['results']['variables']['N'],42)


if __name__=='__main__':unittest.main()
