"""Authored input rediscovery, compatible data migration and publication checks."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from karel2py import translate, runner
from karel2py.input_template import prepare_inputs, InputTemplateError
from karel2py.input_refresh import refresh_inputs


ROOT=Path(__file__).resolve().parents[1]
MISSING={'uninitialized':True}


def code(body='n=x',decl='x,n:INTEGER',prefix='',program='T'):
    return translate(f'PROGRAM {program} {prefix} VAR {decl} BEGIN {body} END {program}').python_source


def rows(prepared):
    return {row['path']:row for row in prepared['context'].get('variables',[])}


class InputRefreshTests(unittest.TestCase):
    def test_recompute_status_preserve_edited_context_and_leave_previous_unchanged(self):
        previous=prepare_inputs(code());previous['context']['variables'][0]['value']=21
        original=deepcopy(previous)
        result=refresh_inputs(code(),previous)
        self.assertEqual(result['context'],previous['context'])
        self.assertEqual(previous,original)
        self.assertEqual(result['template']['requirements'],[])
        self.assertEqual(result['template']['bindings'][0]['status'],'supplied')
        self.assertEqual(len(result['template']['refresh']['changes']['retained']),1)
        result['context']['variables'][0]['value']=99
        self.assertEqual(previous,original)

    def test_catalog_changes_reset_incompatible_scalar_and_retain_removed_context(self):
        previous=prepare_inputs(code('n=x+y',decl='x,y,n:INTEGER'))
        rows(previous)['X']['value']=7;rows(previous)['Y']['value']=9
        result=refresh_inputs(code('n=x+z',decl='x,z,n:REAL'),previous)
        self.assertEqual(rows(result)['X']['value'],MISSING)
        self.assertEqual(rows(result)['X']['type'],['REAL'])
        self.assertEqual(rows(result)['Y']['value'],9)
        changes=result['template']['refresh']['changes']
        self.assertEqual([row['path'] for row in changes['added']],['Z'])
        self.assertEqual([row['path'] for row in changes['removed']],['Y'])
        self.assertEqual(changes['changed'][0]['after']['path'],'X')
        self.assertEqual(result['template']['refresh']['variables'][0]['status'],'reset')

    def test_conditional_input_becoming_required_is_reported_without_inventing_value(self):
        previous=prepare_inputs(code('IF flag THEN n=x ELSE n=0 ENDIF',decl='flag:BOOLEAN x,n:INTEGER'))
        rows(previous)['FLAG']['value']=False
        result=refresh_inputs(code(),previous)
        change=result['template']['refresh']['changes']['changed'][0]
        self.assertEqual((change['before']['certainty'],change['after']['certainty']),('conditional','required'))
        self.assertEqual(result['template']['bindings'][0]['status'],'missing')
        self.assertEqual(rows(result)['X']['value'],MISSING)

    def test_structure_migration_preserves_common_fields_and_leaves_new_fields_missing(self):
        previous=prepare_inputs(code('n=p.a+p.b',decl='p:data_t n:INTEGER',prefix='TYPE data_t=STRUCTURE a:INTEGER b:INTEGER ENDSTRUCTURE'))
        rows(previous)['P']['value']={'A':7,'B':9}
        result=refresh_inputs(code('n=p.a+p.c',decl='p:data_t n:INTEGER',prefix='TYPE data_t=STRUCTURE a:INTEGER c:INTEGER ENDSTRUCTURE'),previous)
        self.assertEqual(rows(result)['P']['value'],{'A':7,'C':MISSING})
        migration=result['template']['refresh']['variables'][0]
        self.assertEqual((migration['preserved_leaves'],migration['missing_leaves']),(1,1))
        self.assertEqual(migration['source_pointer'],'/inputs/context/variables/0/value')
        self.assertEqual(len(result['template']['requirements']),1)

    def test_nominal_record_name_change_does_not_implicitly_transfer_fields(self):
        previous=prepare_inputs(code('n=p.a',decl='p:old_t n:INTEGER',prefix='TYPE old_t=STRUCTURE a:INTEGER ENDSTRUCTURE'))
        rows(previous)['P']['value']={'A':7}
        result=refresh_inputs(code('n=p.a',decl='p:new_t n:INTEGER',prefix='TYPE new_t=STRUCTURE a:INTEGER ENDSTRUCTURE'),previous)
        self.assertEqual(rows(result)['P']['value'],{'A':MISSING})
        self.assertEqual(result['template']['refresh']['variables'][0]['preserved_leaves'],0)

    def test_multidimensional_resize_copies_logical_coordinates(self):
        previous=prepare_inputs(code('n=a[1,1]',decl='a:ARRAY[2,2]OF INTEGER n:INTEGER'))
        rows(previous)['A']['value']=[[1,2],[3,4]]
        result=refresh_inputs(code('n=a[3,1]',decl='a:ARRAY[3,1]OF INTEGER n:INTEGER'),previous)
        self.assertEqual(rows(result)['A']['value'],[[1],[3],[MISSING]])
        self.assertEqual(result['template']['refresh']['variables'][0]['preserved_leaves'],2)

    def test_named_nested_array_resize_and_rank_change(self):
        old=code('n=a[1,1]',decl='a:ARRAY[2]OF pair_t n:INTEGER',prefix='TYPE pair_t=ARRAY[2]OF INTEGER')
        previous=prepare_inputs(old);rows(previous)['A']['value']=[[1,2],[3,4]]
        new=code('n=a[2,3]',decl='a:ARRAY[2]OF pair_t n:INTEGER',prefix='TYPE pair_t=ARRAY[3]OF INTEGER')
        result=refresh_inputs(new,previous)
        self.assertEqual(rows(result)['A']['value'],[[1,2,MISSING],[3,4,MISSING]])
        flat=prepare_inputs(code('n=a[1]',decl='a:ARRAY[4]OF INTEGER n:INTEGER'))
        rows(flat)['A']['value']=[1,2,3,4]
        result=refresh_inputs(code('n=a[1,1]',decl='a:ARRAY[2,2]OF INTEGER n:INTEGER'),flat)
        self.assertEqual(rows(result)['A']['value'],[[MISSING,MISSING],[MISSING,MISSING]])

    def test_string_capacity_changes_preserve_only_fitting_values(self):
        previous=prepare_inputs(code('WRITE(text)',decl='text:STRING[8] n:INTEGER'))
        rows(previous)['TEXT']['value']='ready'
        for capacity,expected in ((10,'ready'),(5,'ready'),(4,MISSING)):
            with self.subTest(capacity=capacity):
                result=refresh_inputs(code('WRITE(text)',decl=f'text:STRING[{capacity}] n:INTEGER'),previous)
                self.assertEqual(rows(result)['TEXT']['value'],expected)

    def test_joint_resize_keeps_known_axes_and_unknown_byte_stays_unknown(self):
        previous=prepare_inputs(code('n=j[1]+b',decl='j:JOINTPOS2 b:BYTE n:REAL'))
        rows(previous)['J']['value']={'axes':[1.0,MISSING]}
        result=refresh_inputs(code('n=j[3]+b',decl='j:JOINTPOS3 b:BYTE n:REAL'),previous)
        self.assertEqual(rows(result)['J']['value'],{'axes':[1.0,MISSING,MISSING]})
        self.assertEqual(rows(result)['B']['value'],{'unknown_byte':True})
        self.assertEqual(result['template']['refresh']['variables'][0]['preserved_leaves'],1)

    def test_program_rename_preserves_old_namespace_without_guessing_new_owner(self):
        previous=prepare_inputs(code());rows(previous)['X']['value']=7
        result=refresh_inputs(code(program='NEW'),previous)
        bindings={(row['program'],row['path']):row['value'] for row in result['context']['variables']}
        self.assertEqual(bindings,{('T','X'):7,('NEW','X'):MISSING})

    def test_bank_configuration_values_comments_and_new_missing_addresses_are_preserved(self):
        context={'ports':{'counts':{'DIN':2},'values':{'DIN':{'1':True}}},
            'numeric':{'count':2,'values':{'1':0.1},'comments':{'1':'keep'}},'files':{'seed.txt':'data'}}
        previous=prepare_inputs(code('flag=DIN[1]',decl='flag:BOOLEAN'),context=context)
        result=refresh_inputs(code('flag=DIN[2]',decl='flag:BOOLEAN'),previous)
        self.assertEqual(result['context'],context)
        self.assertEqual(result['template']['bindings'][0]['status'],'missing')
        changes=result['template']['refresh']['changes']
        self.assertEqual(changes['removed'][0]['path'],'DIN[1]')
        self.assertEqual(changes['added'][0]['path'],'DIN[2]')

    def test_plain_context_baseline_unknown_and_new_dynamic_gaps_are_visible(self):
        previous={'context':{'variables':[dict(program='t',path='x',type='INTEGER',value=2)]}}
        result=refresh_inputs(code('n=a[x]',decl='x,n:INTEGER a:ARRAY[2]OF INTEGER'),previous)
        self.assertFalse(result['template']['refresh']['baseline_known'])
        self.assertFalse(result['template']['discovery']['complete'])
        self.assertTrue(result['template']['discovery']['unresolved'])
        self.assertEqual(result['context'],previous['context'])

    def test_incomplete_new_discovery_does_not_claim_inputs_were_removed(self):
        previous=prepare_inputs(code());rows(previous)['X']['value']=7
        with mock.patch('karel2py.input_contract.MAX_NODES',1):partial=code()
        result=refresh_inputs(partial,previous)
        comparison=result['template']['refresh']
        self.assertFalse(comparison['comparison_complete'])
        self.assertEqual(comparison['changes']['removed'],[])
        self.assertEqual(comparison['changes']['unresolved'][0]['before']['path'],'X')
        self.assertEqual(result['context'],previous['context'])

    def test_incomplete_previous_discovery_keeps_newly_observed_additions_unproven(self):
        previous=prepare_inputs(code('n=a[x]',decl='x,n:INTEGER a:ARRAY[2]OF INTEGER'))
        result=refresh_inputs(code('n=x+y',decl='x,y,n:INTEGER'),previous)
        comparison=result['template']['refresh']
        self.assertTrue(comparison['baseline_known'])
        self.assertFalse(comparison['comparison_complete'])
        self.assertEqual(comparison['changes']['added'],[])
        self.assertEqual(comparison['changes']['unresolved'][0]['after']['path'],'Y')

    def test_second_status_pass_does_not_bypass_shared_materialization_limit(self):
        previous=prepare_inputs(code('n=a[1]',decl='a:ARRAY[1]OF INTEGER n:INTEGER'))
        rows(previous)['A']['value']=[7]
        with mock.patch('karel2py.input_template.MAX_LEAVES',2):
            result=refresh_inputs(code('n=a[1]+b[1]',decl='a,b:ARRAY[2]OF INTEGER n:INTEGER'),previous)
        self.assertEqual(set(rows(result)),{'A'})
        self.assertEqual(rows(result)['A']['value'],[7,MISSING])
        self.assertTrue(any(row['code']=='limit' for row in result['template']['requirements']))
        self.assertEqual(next(row for row in result['template']['bindings'] if row['path']=='B[1]')['status'],'unmapped')

    def test_invalid_previous_metadata_and_context_are_rejected(self):
        previous=prepare_inputs(code())
        variants=[{'context':{},'template':None},{'context':{'unknown':True}},deepcopy(previous)]
        variants[-1]['template']['discovery']['inputs']*=2
        for value in variants:
            with self.subTest(value=value),self.assertRaises(InputTemplateError):refresh_inputs(code(),value)

    def test_refresh_is_nonexecuting(self):
        source=code();previous=prepare_inputs(source)
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')):
            with mock.patch('builtins.eval',side_effect=AssertionError('evaluated')):
                self.assertEqual(refresh_inputs(source,previous)['context'],previous['context'])


class RefreshDocumentTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.folder=Path(folder.name);self.target=self.folder/'converted.py';self.source=self.folder/'old.json';self.output=self.folder/'new.json'
        self.target.write_bytes(code('n=x*2 x=x+1').encode())
        context={'variables':[dict(program='T',path='X',type=['INTEGER'],value=21)]}
        runner.create_document(self.target,self.source,context=context,discover=True,max_steps=123,max_output_chars=456)
        runner.run_document(self.source)

    def test_changed_default_target_repin_preserves_inputs_original_results_and_limits(self):
        old=self.source.read_bytes();self.target.write_bytes(code('n=x*3 x=x+2').encode())
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')):
            result=runner.refresh_document(self.source,self.output)
        self.assertEqual(self.source.read_bytes(),old)
        self.assertIsNone(result['results'])
        self.assertEqual(result['limits'],dict(max_steps=123,max_output_chars=456))
        self.assertEqual(rows({'context':result['inputs']['context']})['X']['value'],21)
        self.assertEqual(result['inputs']['template']['refresh']['previous_document'],dict(path='old.json',sha256=hashlib.sha256(old).hexdigest()))
        for _ in range(2):
            completed=runner.run_document(self.output)
            self.assertEqual(completed['results']['variables'],{'X':23,'N':63})
            self.assertEqual(completed['inputs'],result['inputs'])

    def test_explicit_target_works_when_old_python_is_missing_and_baseline_is_plain_context(self):
        data=json.loads(self.source.read_bytes());data['inputs'].pop('template')
        self.source.write_bytes(json.dumps(data).encode());self.target.unlink()
        target=self.folder/'replacement.py';target.write_bytes(code('n=x+1').encode())
        result=runner.refresh_document(self.source,self.output,target=target)
        self.assertFalse(result['inputs']['template']['refresh']['baseline_known'])
        self.assertEqual(runner.run_document(self.output)['results']['variables']['N'],22)

    def test_relative_paths_and_successive_refresh_keep_only_immediate_provenance(self):
        folder=self.folder/'sub';folder.mkdir();first=folder/'new.json'
        result=runner.refresh_document(self.source,first)
        self.assertEqual(Path(result['target']['path']),Path('../converted.py'))
        again=runner.refresh_document(first,self.output)
        self.assertEqual(again['inputs']['template']['refresh']['previous_document']['path'],str(Path('sub/new.json')))
        self.assertEqual(len(again['inputs']['template']['refresh']['changes']['retained']),1)
        self.assertNotIn('refresh',again['inputs']['template']['refresh'])
        self.assertEqual(runner.run_document(self.output)['results']['variables']['N'],42)

    def test_running_marker_is_refused_without_publication(self):
        data=json.loads(self.source.read_bytes());data['results']['status']='running'
        original=json.dumps(data).encode();self.source.write_bytes(original)
        with self.assertRaisesRegex(runner.RunDocumentError,'running or interrupted'):
            runner.refresh_document(self.source,self.output)
        self.assertFalse(self.output.exists());self.assertEqual(self.source.read_bytes(),original)

    def test_existing_output_and_source_target_aliases_are_preserved(self):
        original=self.source.read_bytes();target=self.target.read_bytes()
        for destination in (self.source,self.target):
            with self.subTest(destination=destination),self.assertRaises((FileExistsError,ValueError)):
                runner.refresh_document(self.source,destination)
        self.output.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):runner.refresh_document(self.source,self.output)
        self.assertEqual(self.output.read_bytes(),b'keep')
        self.assertEqual(self.source.read_bytes(),original);self.assertEqual(self.target.read_bytes(),target)

    def test_source_edits_during_refresh_are_retained_without_output(self):
        make=runner.make_document
        def edited(*args,**kwargs):
            result=make(*args,**kwargs);self.source.write_bytes(b'external edit');return result
        with mock.patch.object(runner,'make_document',side_effect=edited):
            with self.assertRaisesRegex(runner.RunDocumentError,'external edits preserved'):
                runner.refresh_document(self.source,self.output)
        self.assertEqual(self.source.read_bytes(),b'external edit');self.assertFalse(self.output.exists())

    def test_target_edits_between_analysis_and_pin_reject_without_output(self):
        make=runner.make_document
        def edited(*args,**kwargs):
            self.target.write_bytes(self.target.read_bytes()+b'\n# changed\n');return make(*args,**kwargs)
        with mock.patch.object(runner,'make_document',side_effect=edited):
            with self.assertRaisesRegex(runner.RunDocumentError,'target changed during'):
                runner.refresh_document(self.source,self.output)
        self.assertFalse(self.output.exists())

    def test_failed_publication_preserves_old_document_and_target(self):
        old=self.source.read_bytes();target=self.target.read_bytes()
        with mock.patch.object(runner,'atomic_bytes',side_effect=OSError('synthetic publication failure')):
            with self.assertRaisesRegex(OSError,'synthetic publication'):
                runner.refresh_document(self.source,self.output)
        self.assertFalse(self.output.exists());self.assertEqual(self.source.read_bytes(),old);self.assertEqual(self.target.read_bytes(),target)

    def test_bad_refresh_annotation_rejects_before_execution_and_publication(self):
        data=runner.refresh_document(self.source,self.output)
        data['inputs']['template']['refresh']['changes']={}
        before=json.dumps(data).encode();self.output.write_bytes(before)
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')):
            with self.assertRaisesRegex(runner.RunDocumentError,'Malformed input-refresh'):
                runner.run_document(self.output)
        self.assertEqual(self.output.read_bytes(),before)

    def test_cli_runtime_only_refresh_and_result_summary(self):
        bootstrap='''import runpy,sys
class RuntimeOnly:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.project','tkinter','_tkinter','karel2py.gui','socket','ssl','http.client','urllib.request'):
   raise ImportError('Refresh needs runtime only')
sys.meta_path.insert(0,RuntimeOnly());sys.path.insert(0,sys.argv[1])
sys.argv=['karel2py.runner','refresh',sys.argv[2],sys.argv[3]]
runpy.run_module('karel2py.runner',run_name='__main__')
'''
        process=subprocess.run([sys.executable,'-I','-X','utf8','-c',bootstrap,str(ROOT),str(self.source),str(self.output)],capture_output=True,text=True,cwd=self.folder)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout),dict(status='refreshed',program='T',changes=dict(added=0,removed=0,changed=0,retained=1,unresolved=0),requirements=0,unresolved=0))
        self.assertEqual(runner.run_document(self.output)['results']['variables']['N'],42)


if __name__=='__main__':unittest.main()
