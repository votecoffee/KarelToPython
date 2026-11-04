"""Explicit saved-schema dimensions across compiler, source links and CLI replay."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from karel2py import translate,translate_project,load_project,runtime as rt
from karel2py.array_context import ArrayContext,load_array_context,prepare
from karel2py.lexer import TranslationError

U={'uninitialized':True}


def source(program='T',declaration='values:ARRAY[*]OF INTEGER',body='values[2]=17',prefix=''):
    return f'PROGRAM {program} {prefix} VAR {declaration} BEGIN {body} END {program}'


def context(*rows):return dict(variables=list(rows))


def schema(program='T',name='VALUES',spec=None,value=None):
    return dict(program=program,path=name,type=spec or ['ARRAY',2,['INTEGER']],value=value if value is not None else [U,U])


def program(result,**options):
    ns={};exec(result.python_source,ns);return ns['Program'](**options)


class ArrayContextSourceTests(unittest.TestCase):
    def test_specializes_scalar_array_without_initializing_values(self):
        result=translate(source(),array_context=context(schema(value=[42,99])));p=program(result);self.assertEqual(p.snapshot()['VALUES'],[U,U]);self.assertEqual(p.run()['VALUES'],[U,17])
    def test_saved_values_load_only_when_execution_context_is_supplied(self):
        config=context(schema(value=[42,99]));p=program(translate(source(),array_context=config),context=rt.ExecutionContext.from_config(config));self.assertEqual(p.run()['VALUES'],[42,17])
    def test_mixed_fixed_and_wildcard_dimensions(self):
        result=translate(source(declaration='values:ARRAY[2,*]OF INTEGER',body='values[2,3]=17'),array_context=context(schema(spec=['ARRAY',[2,3],['INTEGER']])));self.assertEqual(program(result).run()['VALUES'],[[U,U,U],[U,U,17]])
    def test_three_dimensions(self):
        result=translate(source(declaration='values:ARRAY[*,*,*]OF INTEGER',body='values[2,1,2]=17'),array_context=context(schema(spec=['ARRAY',[2,1,2],['INTEGER']])));self.assertEqual(program(result).run()['VALUES'][1],[[U,17]])
    def test_string_capacity_remains_exact(self):
        result=translate(source(declaration='values:ARRAY[*]OF STRING[4]',body="values[2]='seed'"),array_context=context(schema(spec=['ARRAY',2,['STRING',4]])));self.assertEqual(program(result).run()['VALUES'],[U,'seed'])
    def test_record_arrays_preserve_nominal_metadata(self):
        spec=['ARRAY',2,['STRUCTURE','ITEM_T',[['ID',['INTEGER']]]]];result=translate(source(declaration='values:ARRAY[*]OF item_t',body='values[2].id=17',prefix='TYPE item_t=STRUCTURE id:INTEGER ENDSTRUCTURE'),array_context=context(schema(spec=spec)));self.assertEqual(program(result).run()['VALUES'],[{'ID':U},{'ID':17}])
    def test_named_nested_array_component(self):
        spec=['ARRAY',2,['ARRAY',2,['INTEGER'],'ROW_T']];result=translate(source(declaration='values:ARRAY[*]OF row_t',body='values[2][1]=17',prefix='TYPE row_t=ARRAY[2]OF INTEGER'),array_context=context(schema(spec=spec)));self.assertEqual(program(result).run()['VALUES'],[[U,U],[17,U]])
    def test_joint_arrays(self):
        result=translate(source(declaration='values:ARRAY[*]OF JOINTPOS2',body='values[2][1]=17'),array_context=context(schema(spec=['ARRAY',2,['JOINTPOS',2]])));self.assertEqual(program(result).run()['VALUES'][1],{'axes':[17.,U]})
    def test_path_banks(self):
        result=translate(source(declaration='values:ARRAY[*]OF PATH',body=''),array_context=context(schema(spec=['ARRAY',2,['PATH',None,None]])));self.assertEqual(len(program(result).run()['VALUES']),2)
    def test_queue_banks(self):
        result=translate(source(declaration='values:ARRAY[*]OF QUEUE_TYPE',body='INIT_QUEUE(values[2])'),array_context=context(schema(spec=['ARRAY',2,['QUEUE_TYPE']])));self.assertTrue(program(result).run()['VALUES'][1]['initialized'])
    def test_file_bank_allocation_does_not_restore_handles(self):
        result=translate(source(declaration='values:ARRAY[*]OF FILE',body=''),array_context=context(schema(spec=['ARRAY',2,['FILE']],value={'closed':True})));p=program(result);self.assertEqual(len(p._state.raw('VALUES').values),2);self.assertTrue(all(v.owner is None for v in p._state.raw('VALUES').values))
    def test_case_insensitive_schema_identity(self):
        result=translate(source(),array_context=context(schema('t','values')));self.assertEqual(program(result).run()['VALUES'],[U,17])
    def test_unrelated_program_schema_does_not_supply_dimensions(self):
        with self.assertRaises(TranslationError) as caught:translate(source(),array_context=context(schema('OTHER')))
        self.assertEqual(caught.exception.code,'E_ARRAY_SIZE')
    def test_empty_catalog_retains_existing_missing_dimension_error(self):
        with self.assertRaises(TranslationError) as caught:translate(source(),array_context=context())
        self.assertEqual(caught.exception.code,'E_ARRAY_SIZE')
    def test_matching_explicit_dimensions_coexist(self):
        result=translate(source(),array_shapes={'values':[2]},array_context=context(schema()));self.assertEqual(result.report['translation_context']['array_shapes'],{'VALUES':[2]})
    def test_explicit_dimensions_cover_unsaved_other_variable(self):
        result=translate(source(declaration='values,other:ARRAY[*]OF INTEGER',body='other[3]=17'),array_shapes={'other':[3]},array_context=context(schema()));self.assertEqual(len(program(result).run()['OTHER']),3)
    def test_fixed_global_is_not_resized_or_schema_checked(self):
        result=translate(source(declaration='values:ARRAY[2]OF INTEGER'),array_context=context(schema(spec=['ARRAY',3,['REAL']])));self.assertEqual(program(result).run()['VALUES'],[U,17])
    def test_named_global_is_not_specialized(self):
        result=translate(source(declaration='values:row_t',prefix='TYPE row_t=ARRAY[2]OF INTEGER'),array_context=context(schema(spec=['ARRAY',3,['REAL']])));self.assertEqual(program(result).run()['VALUES'],[U,17])
    def test_root_metadata_only_ignores_scalar_and_leaf_bindings(self):
        value=context(schema('T','VALUES[1]',spec=['INTEGER']),schema('T','OTHER',spec=['INTEGER']),schema());result=translate(source(),array_context=value);self.assertEqual(program(result).run()['VALUES'],[U,17])
    def test_includes_are_parsed_and_errors_are_remapped(self):
        config=context(schema(spec=['ARRAY',2,['BOOLEAN']]));text="PROGRAM T\n%INCLUDE 'globals'\nBEGIN END T"
        with self.assertRaises(TranslationError) as caught:translate(text,array_context=config,includes={'globals':'VAR values:ARRAY[*]OF INTEGER'})
        self.assertIn('globals',caught.exception.filename);self.assertEqual(caught.exception.code,'E_ARRAY_CONTEXT')
    def test_conversion_does_not_restore_values_or_services(self):
        config=context(schema(value=object()));config['robot']=object()
        with patch.object(rt.ExecutionContext,'from_config',side_effect=AssertionError('restore')):result=translate(source(),array_context=config)
        self.assertEqual(program(result).run()['VALUES'],[U,17])
    def test_payloads_do_not_enter_output_or_context_hash(self):
        first=translate(source(),array_context=context(schema(value=['private-one','private-two'])));second=translate(source(),array_context=context(schema(value=object())));self.assertEqual(first.python_source,second.python_source);self.assertEqual(first.report['translation_context_sha256'],second.report['translation_context_sha256']);self.assertNotIn('private-one',first.python_source+json.dumps(first.report))
    def test_input_schema_mutation_does_not_retarget_catalog(self):
        value=context(schema());catalog=ArrayContext(value);value['variables'][0]['type'][1]=3;self.assertEqual(program(translate(source(),array_context=catalog)).run()['VALUES'],[U,17])
    def test_no_body_execution_while_translating(self):
        result=translate(source(body='ABORT'),array_context=context(schema()));self.assertEqual(program(result).snapshot()['VALUES'],[U,U])
    def test_report_policy_and_metadata_are_explicit(self):
        result=translate(source(),array_context=context(schema()));self.assertFalse(result.report['array_context_policy']['controller_validated']);self.assertEqual(result.report['array_context_specializations'][0]['schema_program'],'T');self.assertIn('array_context',result.report['translation_context'])


class ArrayContextRejectionTests(unittest.TestCase):
    def reject(self,config,**options):
        with self.assertRaises((TranslationError,ValueError,rt.KarelRuntimeError)):translate(source(),array_context=config,**options)
    def test_wrong_scalar_terminal(self):self.reject(context(schema(spec=['ARRAY',2,['BOOLEAN']])))
    def test_wrong_string_capacity(self):
        with self.assertRaises(TranslationError):translate(source(declaration='values:ARRAY[*]OF STRING[4]',body=''),array_context=context(schema(spec=['ARRAY',2,['STRING',8]])))
    def test_wrong_joint_width(self):
        with self.assertRaises(TranslationError):translate(source(declaration='values:ARRAY[*]OF JOINTPOS2',body=''),array_context=context(schema(spec=['ARRAY',2,['JOINTPOS',3]])))
    def test_wrong_array_nominal_identity(self):self.reject(context(schema(spec=['ARRAY',2,['INTEGER'],'ROW_T'])))
    def test_wrong_rank(self):self.reject(context(schema(spec=['ARRAY',[2,2],['INTEGER']])))
    def test_wrong_fixed_dimension(self):
        with self.assertRaises(TranslationError):translate(source(declaration='values:ARRAY[3,*]OF INTEGER',body=''),array_context=context(schema(spec=['ARRAY',[2,2],['INTEGER']])))
    def test_explicit_shape_conflict(self):self.reject(context(schema()),array_shapes={'values':[3]})
    def test_existing_duplicate_explicit_names_reject(self):self.reject(context(schema()),array_shapes={'values':[2],'VALUES':[2]})
    def test_existing_unused_explicit_name_rejects(self):self.reject(context(schema()),array_shapes={'unused':[2]})
    def test_config_requires_variables_list(self):
        for value in (None,{},[],False,{'variables':{}},{'variables':()}):
            with self.subTest(value=value),self.assertRaises(ValueError):ArrayContext(value)
    def test_variable_rows_require_exact_allowed_fields(self):
        for changes in ({'extra':1},{'program':7},{'path':False}):
            value=schema();value.update(changes);self.reject(context(value))
    def test_missing_payload_key_rejects_even_though_values_are_not_read(self):
        value=schema();del value['value'];self.reject(context(value))
    def test_case_insensitive_duplicate_rows_reject(self):self.reject(context(schema(),schema('t','values')))
    def test_empty_and_oversized_dimensions_reject(self):
        for size in (0,-1,32768,None,True):
            with self.subTest(size=size):self.reject(context(schema(spec=['ARRAY',size,['INTEGER']])))
    def test_leaf_quota_rejects_before_program_allocation(self):
        with patch.object(rt.Array,'__init__',side_effect=AssertionError('allocated')):self.reject(context(schema(spec=['ARRAY',32767,['JOINTPOS',2]])))
    def test_resource_record_field_remains_excluded(self):self.reject(context(schema(spec=['ARRAY',2,['STRUCTURE','ROW',[['HANDLE',['FILE']]]]])))
    def test_cyclic_metadata_rejects(self):
        spec=['ARRAY',2];spec.append(spec);self.reject(context(schema(spec=spec)))
    def test_schema_objects_are_not_evaluated(self):
        calls=[]
        class Object:
            def __eq__(self,other):calls.append(other);return True
        self.reject(context(schema(spec=['ARRAY',2,[Object()]])));self.assertEqual(calls,[])
    def test_oversized_row_count_rejects(self):self.reject(context(*([schema()]*32768)))
    def test_strict_translation_stays_unavailable(self):
        with self.assertRaises(TranslationError) as caught:translate(source(),array_context=context(schema()),mode='strict')
        self.assertEqual(caught.exception.code,'E_MODE')


class ArrayContextProjectTests(unittest.TestCase):
    def test_program_qualified_inference_uses_program_names(self):
        result=translate_project({'random.kl':source('MAIN'), 'other.kl':source('LIB',body='')},array_context=context(schema('MAIN'),schema('LIB',spec=['ARRAY',3,['INTEGER']])));self.assertEqual(result.array_shapes,{'MAIN':{'VALUES':[2]},'LIB':{'VALUES':[3]}});self.assertEqual(result.instantiate().run('MAIN')['MAIN']['values']['VALUES'],[U,17])
    def test_partial_explicit_common_shapes_and_saved_schemas(self):
        result=translate_project({'m':source('MAIN'),'l':source('LIB',body='')},array_shapes={'VALUES':[2]},array_context=context(schema('MAIN')));self.assertEqual(result.array_shapes['LIB'],{'VALUES':[2]})
    def test_common_shape_conflict_rejects(self):
        with self.assertRaises(TranslationError):translate_project({'m':source('MAIN')},array_shapes={'VALUES':[3]},array_context=context(schema('MAIN')))
    def test_unused_common_keys_remain_rejected(self):
        with self.assertRaises(TranslationError):translate_project({'m':source('MAIN')},array_shapes={'TYPO':[2]},array_context=context(schema('MAIN')))
    def test_owner_schema_supplies_importer_dimensions(self):
        sources={'m':source('MAIN',declaration='values FROM LIB:ARRAY[*]OF INTEGER'),'l':source('LIB',body='')};result=translate_project(sources,array_context=context(schema('LIB')));instance=result.instantiate();self.assertEqual(instance.run('MAIN')['LIB']['values']['VALUES'],[U,17])
    def test_reexport_owner_chain(self):
        sources={'m':source('MAIN',declaration='values FROM MID:ARRAY[*]OF INTEGER'),'i':source('MID',declaration='values FROM LIB:ARRAY[*]OF INTEGER',body=''),'l':source('LIB',body='')};result=translate_project(sources,array_context=context(schema('LIB')));self.assertEqual(result.array_shapes['MAIN'],{'VALUES':[2]});self.assertEqual(result.instantiate().run('MAIN')['LIB']['values']['VALUES'],[U,17])
    def test_conflicting_import_and_owner_rows_reject(self):
        sources={'m':source('MAIN',declaration='values FROM LIB:ARRAY[*]OF INTEGER'),'l':source('LIB',body='')}
        with self.assertRaises(TranslationError):translate_project(sources,array_context=context(schema('LIB'),schema('MAIN',spec=['ARRAY',3,['INTEGER']])))
    def test_cyclic_import_chain_rejects(self):
        sources={'m':source('MAIN',declaration='values FROM LIB:ARRAY[*]OF INTEGER'),'l':source('LIB',declaration='values FROM MAIN:ARRAY[*]OF INTEGER',body='')}
        with self.assertRaises(TranslationError):translate_project(sources,array_context=context(schema('LIB')))
    def test_duplicate_programs_reject(self):
        with self.assertRaises(ValueError):translate_project({'a':source('MAIN'),'b':source('MAIN')},array_context=context(schema('MAIN')))
    def test_schema_catalog_is_not_mutated_by_project_linking(self):
        catalog=ArrayContext(context(schema('LIB')));translate_project({'m':source('MAIN',declaration='values FROM LIB:ARRAY[*]OF INTEGER'),'l':source('LIB',body='')},array_context=catalog);self.assertEqual(catalog.owners,{})
    def test_constructor_does_not_execute_karel(self):
        project=translate_project({'m':source('MAIN',body='ABORT')},array_context=context(schema('MAIN')));self.assertEqual(project.instantiate().programs['MAIN'].task_state,'ready')
    def test_full_saved_context_replay_needs_no_repeated_shape_map(self):
        sources={'m':source('MAIN'),'l':source('LIB',body='')};first=translate_project(sources,array_shapes={'MAIN.VALUES':[2],'LIB.VALUES':[3]}).instantiate();expected=first.run('MAIN');saved=first.context.to_config();second=translate_project(sources,array_context=saved).instantiate(context=rt.ExecutionContext.from_config(saved));self.assertEqual(second.run('MAIN'),expected)


class ArrayContextFileTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='array_context_');self.addCleanup(temp.cleanup);self.root=Path(temp.name);self.path=self.root/'context.json'
    def write(self,config=None):self.path.write_bytes(json.dumps(config if config is not None else context(schema())).encode());return self.path
    def test_load_bom_utf8(self):
        self.write();self.path.write_bytes(b'\xef\xbb\xbf'+self.path.read_bytes());self.assertEqual(load_array_context(self.path).schemas['T','VALUES'],('ARRAY',2,('INTEGER',)))
    def test_duplicate_keys_are_rejected(self):
        self.path.write_bytes(b'{"variables":[],"variables":[]}')
        with self.assertRaises(ValueError):load_array_context(self.path)
    def test_nested_duplicate_payload_keys_reject(self):
        self.path.write_bytes(b'{"variables":[],"other":{"x":1,"x":2}}')
        with self.assertRaises(ValueError):load_array_context(self.path)
    def test_nonfinite_and_overflow_numbers_reject_anywhere(self):
        for value in ('NaN','Infinity','-Infinity','1e999'):
            self.path.write_bytes(('{"variables":[],"other":'+value+'}').encode())
            with self.subTest(value=value),self.assertRaises(ValueError):load_array_context(self.path)
    def test_invalid_encoding_rejects(self):
        self.path.write_bytes(b'\xff')
        with self.assertRaises(ValueError):load_array_context(self.path)
    def test_directory_is_not_a_json_file(self):
        with self.assertRaises(ValueError):load_array_context(self.root)
    def test_file_size_limit(self):
        self.path.write_bytes(b' '*(16*1024*1024+1))
        with self.assertRaises(ValueError):load_array_context(self.path)
    def test_prepared_catalog_has_no_payload_references(self):
        value=context(schema(value=object()));catalog=prepare(value);self.assertEqual(set(vars(catalog)),{'schemas','owners'});clone=prepare(catalog);self.assertIsNot(clone.schemas,catalog.schemas)


class ArrayContextCLITests(unittest.TestCase):
    setUp=ArrayContextFileTests.setUp
    write=ArrayContextFileTests.write
    def cli(self,*args,module='karel2py',expected=0):
        result=subprocess.run([sys.executable,'-X','utf8','-m',module,*map(str,args)],env={**os.environ,'KAREL2PY_GUI_TESTS':'0'},capture_output=True,text=True,timeout=60);self.assertEqual(result.returncode,expected,result.stderr);return result
    def test_converter_check_report(self):
        self.write();src=self.root/'main.kl';src.write_bytes(source().encode());report=self.root/'report.json';self.cli(src,'--check','--array-context',self.path,'--report',report);self.assertEqual(json.loads(report.read_bytes())['translation_context']['array_shapes'],{'VALUES':[2]})
    def test_converter_compile_then_saved_values_replay(self):
        self.write(context(schema(value=[42,99])));src=self.root/'main.kl';src.write_bytes(source().encode());out=self.root/'program.py';self.cli(src,'-o',out,'--array-context',self.path);env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])};result=subprocess.run([sys.executable,str(out),'--context',str(self.path)],capture_output=True,text=True,env=env,timeout=30);self.assertEqual(result.returncode,0,result.stderr);self.assertIn("[42, 17]",result.stdout)
    def test_converter_metadata_conflict_writes_no_program(self):
        self.write();src=self.root/'main.kl';src.write_bytes(source().encode());out=self.root/'program.py';self.cli(src,'-o',out,'--array-context',self.path,'--array-shape','VALUES=3',expected=2);self.assertFalse(out.exists())
    def test_converter_protects_schema_input_even_with_force(self):
        self.write();before=self.path.read_bytes();src=self.root/'main.kl';src.write_bytes(source().encode());self.cli(src,'-o',self.path,'--array-context',self.path,'--force',expected=1);self.assertEqual(self.path.read_bytes(),before)
    def test_converter_protects_report_hardlink(self):
        self.write();before=self.path.read_bytes();alias=self.root/'alias.json';os.link(self.path,alias);src=self.root/'main.kl';src.write_bytes(source().encode());self.cli(src,'--check','--report',alias,'--array-context',self.path,'--force',expected=1);self.assertEqual(self.path.read_bytes(),before)
    def test_project_check_uses_saved_schema_without_loading_services(self):
        self.write(context(schema('MAIN')));config=json.loads(self.path.read_bytes());config['robot']={'invalid':True};self.write(config);(self.root/'main.kl').write_bytes(source('MAIN',body='ABORT').encode());self.cli(self.root,'--array-context',self.path,module='karel2py.project')
    def test_project_execute_and_saved_replay(self):
        self.write(context(schema('MAIN',value=[42,99])));(self.root/'main.kl').write_bytes(source('MAIN').encode());saved=self.root/'saved.json';first=self.cli(self.root,'--array-context',self.path,'--context',self.path,'--entry','MAIN','--state-out',saved,module='karel2py.project');second=self.cli(self.root,'--array-context',saved,'--context',saved,'--entry','MAIN',module='karel2py.project');self.assertEqual(json.loads(first.stdout),json.loads(second.stdout))
    def test_project_state_output_cannot_alias_schema_input(self):
        self.write(context(schema('MAIN')));before=self.path.read_bytes();(self.root/'main.kl').write_bytes(source('MAIN').encode());self.cli(self.root,'--array-context',self.path,'--entry','MAIN','--state-out',self.path,module='karel2py.project',expected=2);self.assertEqual(self.path.read_bytes(),before)
    def test_project_trace_output_hardlink_cannot_alias_schema_input(self):
        self.write(context(schema('MAIN')));alias=self.root/'alias.json';os.link(self.path,alias);before=self.path.read_bytes();(self.root/'main.kl').write_bytes(source('MAIN').encode());self.cli(self.root,'--array-context',self.path,'--entry','MAIN','--trace-out',alias,module='karel2py.project',expected=2);self.assertEqual(self.path.read_bytes(),before)
    def test_directory_loader_api(self):
        (self.root/'main.kl').write_bytes(source('MAIN').encode());project=load_project(self.root,array_context=context(schema('MAIN')));self.assertEqual(project.array_shapes['MAIN'],{'VALUES':[2]})


if __name__=='__main__':unittest.main()
