"""Authored TYPE FROM layouts, source linkage, provenance and CLI coverage."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from karel2py import translate,translate_project,load_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate

ROOT=Path(__file__).resolve().parents[1]
POINT='STRUCTURE x:REAL y:REAL ENDSTRUCTURE'


def source(name='MAIN',types='item_t FROM LIB=INTEGER',decl='',body='',routines=''):
    return f'PROGRAM {name}\nTYPE {types}\n'+(f'VAR {decl}\n' if decl else '')+f'{routines}\nBEGIN {body} END {name}'


def compile_program(**options):
    result=translate(source(**options),filename='authored.kl')
    namespace={'__name__':'external_type_test'};exec(result.python_source,namespace)
    return namespace['Program'],result


def pair(definition='INTEGER',owner_definition=None,**options):
    return translate_project({'main.kl':source(types='item_t FROM LIB='+definition,**options),
        'lib.kl':source('LIB',types='item_t='+(definition if owner_definition is None else owner_definition))})


class ExternalTypeDeclarationTests(unittest.TestCase):
    def test_standalone_full_layout_needs_no_owner_loading(self):
        cls,result=compile_program(decl='value:item_t',body='value=42')
        self.assertEqual(cls().run(),{'VALUE':42})
        self.assertEqual(cls.imported_types,(('ITEM_T','LIB'),))
        self.assertEqual(cls.type_owners,{'ITEM_T':'LIB'})
        self.assertEqual(result.report['imported_types'][0]['linkage'],'unverified')

    def test_case_insensitive_owner_and_name(self):
        cls,_=compile_program(types='Item_T FrOm lIb=INTEGER',decl='value:iTEM_t',body='value=7')
        self.assertEqual(cls.imported_types,(('ITEM_T','LIB'),))
        self.assertEqual(cls().run()['VALUE'],7)

    def test_self_owned_declaration_is_not_a_self_alias(self):
        cls,result=compile_program(types='item_t FROM MAIN=INTEGER',decl='value:item_t',body='value=8')
        self.assertEqual(cls().run()['VALUE'],8)
        self.assertEqual(result.report['imported_types'][0]['linkage'],'self-declared')

    def test_transparent_local_alias_keeps_imported_aggregate_identity(self):
        cls,_=compile_program(types='item_t FROM LIB=ARRAY[2] OF INTEGER alias_t=item_t',decl='value:alias_t',body='value[1]=1 value[2]=2')
        self.assertEqual(cls.variable_types['ALIAS_T'],cls.variable_types['ITEM_T'])
        self.assertEqual(cls.variable_types['ALIAS_T'][-1],'ITEM_T')
        self.assertEqual(cls.type_owners,{'ITEM_T':'LIB','ALIAS_T':'MAIN'})

    def test_string_capacity_retained_in_value_interface(self):
        cls,_=compile_program(types='item_t FROM LIB=STRING[3]',decl='value:item_t',body="put('abcdef')",
            routines='ROUTINE put(p:item_t) BEGIN value=p END put')
        self.assertEqual(cls().run()['VALUE'],'abc')

    def test_nested_arrays_structures_and_narrow_fields(self):
        cls,_=compile_program(types='entry_t FROM LIB=STRUCTURE code:BYTE ENDSTRUCTURE item_t FROM LIB=ARRAY[2] OF entry_t',
            decl='value:item_t',body='value[1].code=7 value[2].code=8')
        self.assertEqual(cls().run()['VALUE'],[{'CODE':7},{'CODE':8}])

    def test_named_array_function_results_keep_identity(self):
        cls,_=compile_program(types='item_t FROM LIB=ARRAY[2] OF INTEGER',decl='value:item_t',body='value=make()',
            routines='ROUTINE make:item_t VAR temp:item_t BEGIN temp[1]=20 temp[2]=22 RETURN temp END make')
        self.assertEqual(cls().run()['VALUE'],[20,22])

    def test_plain_owned_and_external_types_can_share_sections(self):
        cls,result=compile_program(types='local_t=INTEGER item_t FROM LIB=local_t TYPE text_t FROM LIB=STRING[4]')
        self.assertEqual(cls.type_owners,{'LOCAL_T':'MAIN','ITEM_T':'LIB','TEXT_T':'LIB'})
        self.assertEqual(len(result.report['imported_types']),2)

    def test_report_json_and_declaration_location(self):
        _,result=compile_program()
        row=json.loads(json.dumps(result.report))['imported_types'][0]
        self.assertEqual((row['name'],row['owner'],row['source_file'],row['source_line'],row['source_column']),
                         ('ITEM_T','LIB','authored.kl',2,6))
        self.assertIn('source-linked TYPE FROM declaration',result.report['features'])
        self.assertFalse(result.report['external_type_policy']['controller_validated'])
        self.assertNotIn('external FROM types',result.report['type_alias_policy']['boundary'])
        self.assertNotIn('external FROM types remain blocked',' '.join(result.report['limitations']))
        self.assertNotIn('external types/routines',result.report['structure_routine_policy']['boundary'])

    def test_uninitialized_storage_rules_remain(self):
        cls,_=compile_program(decl='value:item_t',body='value=value+1')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):cls().run()

    def test_for_counter_write_guard_remains(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program(decl='value:item_t',body='FOR value=1 TO 2 DO change(value) ENDFOR',
                routines='ROUTINE change(p:item_t) BEGIN p=7 END change')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_invalid_declarations_keep_existing_guards(self):
        cases=(('item_t FROM LIB', 'E_SYNTAX'),
               ("item_t FROM 'LIB'=INTEGER",'E_NAME'),
               ('item_t FROM LIB=item_t','E_TYPE'),
               ('item_t FROM LIB=later_t later_t=INTEGER','E_TYPE'),
               ('item_t FROM LIB=ARRAY[*] OF INTEGER','E_VARIABLE_ARRAY_SCOPE'),
               ('item_t FROM LIB=STRUCTURE f:FILE ENDSTRUCTURE','E_TYPE'),
               ('item_t FROM LIB=INTEGER item_t FROM LIB=REAL','E_DUPLICATE'))
        for types,code in cases:
            with self.subTest(types=types),self.assertRaises(TranslationError) as caught:compile_program(types=types)
            self.assertEqual(caught.exception.code,code)

    def test_routine_local_types_remain_prohibited(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program(routines='ROUTINE work TYPE local_t FROM LIB=INTEGER BEGIN END work')
        self.assertEqual(caught.exception.code,'E_ROUTINE_LOCALS')

    def test_legacy_parser_does_not_gain_external_types(self):
        with self.assertRaises(TranslationError):legacy_translate(source())


class ExternalTypeProjectTests(unittest.TestCase):
    def test_exact_scalar_alias_and_bounded_string_schemas(self):
        for definition in ('INTEGER','REAL','BOOLEAN','STRING[5]','XYZWPREXT','JOINTPOS7'):
            with self.subTest(definition=definition):
                project=pair(definition)
                self.assertEqual(project.type_owners['MAIN']['ITEM_T'],'LIB')
                self.assertEqual(project.translations['MAIN'].report['imported_types'][0]['linkage'],'source-validated')

    def test_structure_array_and_path_definitions(self):
        for definition in (POINT,'ARRAY[2,3] OF REAL','PATH','FILE','QUEUE_TYPE'):
            with self.subTest(definition=definition):self.assertEqual(pair(definition).type_owners['MAIN']['ITEM_T'],'LIB')

    def test_named_components_and_path_header_match(self):
        types='header_t FROM LIB=STRUCTURE seq:INTEGER ENDSTRUCTURE item_t FROM LIB=PATH NODEDATA=header_t, PATHHEADER=header_t'
        project=translate_project({'main.kl':source(types=types),'lib.kl':source('LIB',types=types.replace(' FROM LIB',''))})
        self.assertEqual(project.type_owners['MAIN'],{'HEADER_T':'LIB','ITEM_T':'LIB'})

    def test_owned_alias_expands_before_matching(self):
        project=translate_project({'main.kl':source(),'lib.kl':source('LIB',types='count_t=INTEGER item_t=count_t')})
        self.assertEqual(project.type_owners['MAIN']['ITEM_T'],'LIB')

    def test_owner_self_declaration_terminates_chain(self):
        project=translate_project({'main.kl':source(),'lib.kl':source('LIB',types='item_t FROM LIB=INTEGER')})
        self.assertEqual(project.type_owners['LIB']['ITEM_T'],'LIB')
        self.assertEqual(project.translations['LIB'].report['imported_types'][0]['resolved_owner'],'LIB')

    def test_reexport_chain_and_source_order_independence(self):
        sources={'main.kl':source(),'lib.kl':source('LIB',types='item_t FROM BASE=INTEGER'),
                 'base.kl':source('BASE',types='item_t=INTEGER')}
        for documents in (sources,dict(reversed(list(sources.items())))):
            project=translate_project(documents)
            self.assertEqual(project.type_owners['MAIN']['ITEM_T'],'BASE')
            self.assertEqual(project.translations['MAIN'].report['imported_types'][0]['resolved_owner'],'BASE')
            self.assertEqual(project.classes['MAIN'].type_owners['ITEM_T'],'LIB')

    def test_long_chain_uses_iterative_resolution(self):
        sources={f'p{n}.kl':source(f'P{n}',types='item_t'+(f' FROM P{n+1}' if n<79 else '')+'=INTEGER') for n in range(80)}
        project=translate_project(sources)
        self.assertEqual(project.type_owners['P0']['ITEM_T'],'P79')

    def test_missing_owner_fails_before_allocating_globals(self):
        with patch.object(rt.State,'__init__',side_effect=AssertionError('must not allocate')):
            with self.assertRaises(TranslationError) as caught:translate_project({'main.kl':source(decl='value:item_t')})
        self.assertEqual(caught.exception.code,'E_TYPE_LINK')
        self.assertEqual((caught.exception.filename,caught.exception.token.line),('main.kl',2))

    def test_missing_same_named_type_does_not_search_other_modules(self):
        with self.assertRaises(TranslationError) as caught:
            translate_project({'main.kl':source(),'lib.kl':source('LIB',types='different=INTEGER'),
                'base.kl':source('BASE',types='item_t=INTEGER')})
        self.assertEqual(caught.exception.code,'E_TYPE_LINK')
        self.assertIn('LIB.ITEM_T',caught.exception.message)

    def test_global_variable_is_not_a_type_export(self):
        with self.assertRaises(TranslationError) as caught:
            translate_project({'main.kl':source(),'lib.kl':'PROGRAM LIB VAR item_t:INTEGER BEGIN END LIB'})
        self.assertEqual(caught.exception.code,'E_TYPE_LINK')

    def test_scalar_string_width_rank_and_record_mismatches(self):
        cases=(('INTEGER','REAL'),('STRING[3]','STRING[4]'),('JOINTPOS6','JOINTPOS7'),
               ('ARRAY[2] OF INTEGER','ARRAY[3] OF INTEGER'),('ARRAY[2,3] OF INTEGER','ARRAY[3,2] OF INTEGER'),
               (POINT,'STRUCTURE y:REAL x:REAL ENDSTRUCTURE'),(POINT,'STRUCTURE x:REAL y:INTEGER ENDSTRUCTURE'),
               (POINT,'STRUCTURE x:REAL ENDSTRUCTURE'))
        for definition,other in cases:
            with self.subTest(definition=definition,other=other),self.assertRaises(TranslationError) as caught:pair(definition,other)
            self.assertEqual(caught.exception.code,'E_TYPE_LINK_TYPE')

    def test_group_annotations_retain_existing_schema_policy(self):
        project=pair('XYZWPR IN GROUP[1]','XYZWPR IN GROUP[2]')
        self.assertEqual(project.classes['MAIN'].variable_types['ITEM_T'],('XYZWPR',))
        self.assertEqual(project.classes['MAIN'].source_groups,(1,))
        self.assertEqual(project.classes['LIB'].source_groups,(2,))

    def test_matching_layout_cannot_erase_named_array_identity(self):
        with self.assertRaises(TranslationError) as caught:
            translate_project({'main.kl':source(types='item_t FROM LIB=ARRAY[2] OF INTEGER'),
                'lib.kl':source('LIB',types='different=ARRAY[2] OF INTEGER item_t=different')})
        self.assertEqual(caught.exception.code,'E_TYPE_LINK_TYPE')

    def test_two_program_cycle(self):
        with self.assertRaises(TranslationError) as caught:
            translate_project({'main.kl':source(),'lib.kl':source('LIB',types='item_t FROM MAIN=INTEGER')})
        self.assertEqual(caught.exception.code,'E_TYPE_LINK_CYCLE')

    def test_tail_into_cycle_rejected(self):
        with self.assertRaises(TranslationError) as caught:
            translate_project({'main.kl':source(),'lib.kl':source('LIB',types='item_t FROM BASE=INTEGER'),
                'base.kl':source('BASE',types='item_t FROM LIB=INTEGER')})
        self.assertEqual(caught.exception.code,'E_TYPE_LINK_CYCLE')

    def test_unused_external_type_is_still_checked(self):
        with self.assertRaises(TranslationError):pair('REAL','INTEGER')

    def test_owner_body_is_not_executed_for_linking(self):
        project=translate_project({'main.kl':source(),'lib.kl':source('LIB',types='item_t=INTEGER',decl='value:INTEGER',body='value=value+1')})
        self.assertEqual(project.instantiate().run('MAIN')['LIB']['state'],'ready')

    def test_included_link_error_uses_physical_origin(self):
        with self.assertRaises(TranslationError) as caught:
            translate_project({'main.kl':'PROGRAM MAIN\n%INCLUDE declarations\nBEGIN END MAIN'},
                includes={'declarations.kl':'-- authored\nTYPE item_t FROM MISSING=INTEGER'})
        self.assertEqual((caught.exception.code,caught.exception.filename,caught.exception.token.line,caught.exception.token.column),
                         ('E_TYPE_LINK','declarations.kl',2,6))

    def test_nested_include_schema_error_uses_physical_origin(self):
        with self.assertRaises(TranslationError) as caught:
            translate_project({'main.kl':'PROGRAM MAIN\n%INCLUDE first\nBEGIN END MAIN','lib.kl':source('LIB',types='item_t=REAL')},
                includes={'first.kl':'%INCLUDE second','second.kl':'TYPE item_t FROM LIB=INTEGER'})
        self.assertEqual((caught.exception.code,caught.exception.filename,caught.exception.token.line),('E_TYPE_LINK_TYPE','second.kl',1))

    def test_included_syntax_error_still_remapped(self):
        with self.assertRaises(TranslationError) as caught:
            translate('PROGRAM MAIN\n%INCLUDE first\nBEGIN END MAIN',includes={'first.kl':'TYPE item_t FROM LIB'})
        self.assertEqual((caught.exception.filename,caught.exception.token.line),('first.kl',1))

    def test_project_instances_do_not_share_values(self):
        project=pair(decl='value:item_t',body='value=42')
        first=project.instantiate();second=project.instantiate();first.run('MAIN')
        self.assertEqual(second.programs['MAIN'].snapshot()['VALUE'],{'uninitialized':True})

    def test_imported_variable_and_external_routine_interfaces(self):
        project=load_project(ROOT/'examples/external_types_project')
        instance=project.instantiate();values=instance.run('MAIN')
        self.assertEqual(values,json.loads((ROOT/'examples/external_types_project/expected.json').read_text()))
        main=instance.programs['MAIN']._state
        self.assertEqual(main.types['ROWS'],project.classes['GEOMLIB'].variable_types['ROW_T'])
        self.assertEqual(project.type_owners['MAIN']['POINT_T'],'GEOMLIB')
        self.assertEqual(len(project.classes['BRIDGE'].imported_types),2)
        self.assertIn('geometry.kl',project.translations['BRIDGE'].report['imported_types'][0]['source_file'])


class ExternalTypeCLITests(unittest.TestCase):
    def cli(self,*args):
        return subprocess.run([sys.executable,'-X','utf8','-m',*map(str,args)],cwd=ROOT,capture_output=True,text=True)

    def test_standalone_cli_check_and_report(self):
        path=ROOT/'examples/external_types.kl'
        self.assertEqual(self.cli('karel2py',path,'--check').returncode,0)
        with tempfile.TemporaryDirectory() as temporary:
            generated=Path(temporary)/'output.py';report=Path(temporary)/'report.json'
            result=self.cli('karel2py',path,'-o',generated,'--report',report)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(report.read_text())
            self.assertEqual(len(data['imported_types']),4)
            namespace={'__name__':'cli_fixture'};exec(generated.read_text(),namespace)
            self.assertEqual(namespace['Program']().run(),json.loads(path.with_suffix('.expected.json').read_text()))

    def test_linked_cli_check_and_execution(self):
        folder=ROOT/'examples/external_types_project'
        result=self.cli('karel2py.project',folder)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{'programs':['BRIDGE','GEOMLIB','MAIN'],'linked':True})
        result=self.cli('karel2py.project',folder,'--entry','MAIN')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),json.loads((folder/'expected.json').read_text()))

    def test_cli_rejects_type_mismatch_without_running(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            (folder/'main.kl').write_text(source())
            (folder/'lib.kl').write_text(source('LIB',types='item_t=REAL'))
            result=self.cli('karel2py.project',folder,'--entry','MAIN')
            self.assertEqual(result.returncode,2)
            self.assertIn('E_TYPE_LINK_TYPE',result.stderr)
            self.assertEqual(result.stdout,'')

    def test_single_source_fixture(self):
        path=ROOT/'examples/external_types.kl';result=translate(path.read_text())
        namespace={'__name__':'fixture'};exec(result.python_source,namespace)
        self.assertEqual(namespace['Program']().run(),json.loads(path.with_suffix('.expected.json').read_text()))
