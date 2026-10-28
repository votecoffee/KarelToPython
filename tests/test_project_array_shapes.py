"""Authored project-wide wildcard specialization, linkage and CLI scenarios."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import load_project,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from karel2py.project import project_array_shape_option


UNKNOWN={'uninitialized':True}


def source(name,body='',decl='values: ARRAY[*] OF INTEGER',routines=''):
    return f'PROGRAM {name} VAR {decl} {routines} BEGIN {body} END {name}'


class ProjectArrayShapeTests(unittest.TestCase):
    def test_common_shape_skips_programs_without_the_wildcard(self):
        project=translate_project({'main':source('MAIN','values[3]=7'),
            'lib':source('LIB','n=9',decl='n: INTEGER')},array_shapes={'values':[3]})
        self.assertEqual(project.array_shapes,{'MAIN':{'VALUES':[3]},'LIB':{}})
        result=project.instantiate().run('MAIN')
        self.assertEqual(result['MAIN']['values']['VALUES'],[UNKNOWN,UNKNOWN,7])
        self.assertEqual(result['LIB']['state'],'ready')

    def test_common_shape_applies_to_every_matching_program(self):
        project=translate_project({'x':source('FIRST'),'y':source('SECOND')},array_shapes={'VALUES':(2,)})
        self.assertEqual(project.array_shapes,{'FIRST':{'VALUES':[2]},'SECOND':{'VALUES':[2]}})

    def test_qualified_shapes_follow_program_names_not_filenames(self):
        project=translate_project({'main.kl':source('OTHER'),'other.kl':source('MAIN')},
            array_shapes={'other.values':[2],'MaIn.VaLuEs':[3]})
        instance=project.instantiate()
        self.assertEqual(len(instance.programs['OTHER'].snapshot()['VALUES']),2)
        self.assertEqual(len(instance.programs['MAIN'].snapshot()['VALUES']),3)

    def test_qualified_matrix_and_vector_link_through_a_wildcard_formal(self):
        sources={'main':source('MAIN','values[3,2]=7 result=count(values)',
            decl='values: ARRAY[*,2] OF INTEGER result: INTEGER',
            routines='ROUTINE count(p: ARRAY[*,*] OF INTEGER): INTEGER FROM LIB'),
            'lib':source('LIB',routines='ROUTINE count(p: ARRAY[*,*] OF INTEGER): INTEGER BEGIN RETURN ARRAY_LEN(p) END count')}
        result=translate_project(sources,array_shapes={'MAIN.VALUES':[3,2],'LIB.VALUES':[2]}).instantiate().run('MAIN')
        self.assertEqual(result['MAIN']['values']['RESULT'],3)
        self.assertEqual(result['MAIN']['values']['VALUES'][2],[UNKNOWN,7])

    def test_common_and_qualified_disjoint_keys_can_be_combined(self):
        project=translate_project({'one':source('ONE'),'two':source('TWO',decl='grid: ARRAY[*,2] OF REAL')},
            array_shapes={'values':[2],'two.grid':[3,2]})
        self.assertEqual(project.array_shapes,{'ONE':{'VALUES':[2]},'TWO':{'GRID':[3,2]}})

    def test_imported_wildcards_share_owner_storage(self):
        project=translate_project({'main':source('MAIN','values[2]=9',decl='values FROM LIB: ARRAY[*] OF INTEGER'),
            'lib':source('LIB')},array_shapes={'values':[2]})
        instance=project.instantiate();instance.run('MAIN')
        self.assertEqual(instance.programs['LIB'].snapshot()['VALUES'],[UNKNOWN,9])

    def test_imported_qualified_shapes_still_require_equal_types(self):
        project=translate_project({'main':source('MAIN',decl='values FROM LIB: ARRAY[*] OF INTEGER'),
            'lib':source('LIB')},array_shapes={'MAIN.VALUES':[2],'LIB.VALUES':[3]})
        with self.assertRaisesRegex(ValueError,'Imported variable type mismatch'):project.instantiate()

    def test_common_shape_does_not_specialize_same_named_fixed_storage(self):
        project=translate_project({'a':source('ONE'),'b':source('TWO',decl='values: ARRAY[4] OF INTEGER')},
            array_shapes={'VALUES':[2]})
        self.assertEqual(project.array_shapes['TWO'],{})
        self.assertEqual(len(project.instantiate().programs['TWO'].snapshot()['VALUES']),4)

    def test_reports_and_generated_metadata_contain_only_local_shapes(self):
        project=translate_project({'a':source('ONE'),'b':source('TWO')},array_shapes={'ONE.VALUES':[2],'TWO.VALUES':[3]})
        for name,size in [('ONE',2),('TWO',3)]:
            report=project.translations[name].report
            self.assertEqual(report['translation_context']['array_shapes'],{'VALUES':[size]})
            self.assertEqual(project.classes[name].external_array_shapes,(('VALUES',(size,)),))

    def test_shape_configuration_is_not_mutated_or_retained_by_reference(self):
        shapes={'main.values':[2]};original=copy.deepcopy(shapes)
        project=translate_project({'main':source('MAIN')},array_shapes=shapes)
        self.assertEqual(shapes,original)
        shapes['main.values'][0]=9
        self.assertEqual(project.array_shapes['MAIN'],{'VALUES':[2]})
        self.assertEqual(len(project.instantiate().programs['MAIN'].snapshot()['VALUES']),2)

    def test_construction_does_not_run_karel_bodies(self):
        project=translate_project({'a':source('ONE','ABORT'),'b':source('TWO','ABORT')},array_shapes={'values':[2]})
        instance=project.instantiate()
        self.assertEqual({p.task_state for p in instance.programs.values()},{'ready'})

    def test_saved_context_replays_the_same_concrete_shapes(self):
        project=translate_project({'a':source('MAIN','values[2]=7'),'b':source('LIB')},
            array_shapes={'MAIN.VALUES':[2],'LIB.VALUES':[3]})
        first=project.instantiate();first.run('MAIN')
        config=json.loads(json.dumps(first.context.to_config()))
        second=project.instantiate(context=rt.ExecutionContext.from_config(config))
        self.assertEqual(second.run('MAIN')['MAIN']['values'],first.programs['MAIN'].snapshot())

    def test_memory_includes_route_declarations_and_headers(self):
        sources={'a':"PROGRAM MAIN\n%INCLUDE 'storage'\nBEGIN values[2]=8 END MAIN",'b':source('LIB',decl='n: INTEGER')}
        project=translate_project(sources,array_shapes={'main.values':[2]},includes={'storage':'VAR values: ARRAY[*] OF INTEGER'})
        self.assertEqual(project.instantiate().run('MAIN')['MAIN']['values']['VALUES'],[UNKNOWN,8])

    def test_expanded_syntax_errors_keep_the_include_location(self):
        with self.assertRaises(TranslationError) as caught:
            translate_project({'main':"PROGRAM MAIN\n%INCLUDE 'broken'\nBEGIN END MAIN"},
                includes={'broken':'VAR values: ARRAY[* OF INTEGER'},array_shapes={'values':[2]})
        self.assertIn('broken',caught.exception.filename)
        self.assertEqual(caught.exception.token.line,1)

    def test_directory_load_excludes_top_level_included_fragments(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'main.kl').write_text("PROGRAM MAIN\n%INCLUDE 'storage.kl'\nBEGIN values[2]=8 END MAIN",encoding='utf-8')
            (root/'storage.kl').write_text('VAR values: ARRAY[*] OF INTEGER',encoding='utf-8')
            (root/'lib.kl').write_text(source('LIB',decl='n: INTEGER'),encoding='utf-8')
            project=load_project(root,array_shapes={'MAIN.VALUES':[2]})
            self.assertEqual(set(project.classes),{'MAIN','LIB'})
            self.assertEqual(project.instantiate().run('MAIN')['MAIN']['values']['VALUES'],[UNKNOWN,8])

    def test_device_mapped_include_declaration_routes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);programs=root/'programs';programs.mkdir();library=root/'library';library.mkdir()
            (programs/'main.kl').write_text("PROGRAM MAIN\n%INCLUDE 'MD:storage'\nBEGIN END MAIN",encoding='utf-8')
            (library/'storage.kl').write_text('VAR values: ARRAY[*] OF INTEGER',encoding='utf-8')
            project=load_project(programs,array_shapes={'MAIN.VALUES':[2]},include_devices={'MD':library})
            self.assertEqual(project.array_shapes['MAIN'],{'VALUES':[2]})

    def reject(self,shapes,*,sources=None,code='E_ARRAY_CONTEXT'):
        with self.assertRaises(TranslationError) as caught:
            translate_project(sources or {'a':source('MAIN'),'b':source('LIB',decl='n: INTEGER')},array_shapes=shapes)
        self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_unknown_program_and_variable_names_fail_closed(self):
        for shapes in ({'MISSING.VALUES':[2]},{'MAIN.MISSING':[2]},{'LIB.VALUES':[2]},{'MISSING':[2]},
                       {'MAIN.VALUES':[2],'typo':[3]}):
            with self.subTest(shapes=shapes):self.reject(shapes)

    def test_scalar_fixed_named_and_routine_local_targets_reject(self):
        for program in (source('MAIN',decl='values: INTEGER'),source('MAIN',decl='values: ARRAY[2] OF INTEGER'),
                        'PROGRAM MAIN TYPE row_t=ARRAY[2] OF INTEGER VAR values: row_t BEGIN END MAIN',
                        source('MAIN',decl='n: INTEGER',routines='ROUTINE f VAR values: ARRAY[2] OF INTEGER BEGIN END f')):
            with self.subTest(program=program):self.reject({'MAIN.VALUES':[2]},sources={'a':program})

    def test_case_insensitive_duplicates_reject(self):
        for shapes in ({'values':[2],'VALUES':[2]},{'main.values':[2],'MAIN.VALUES':[2]}):
            with self.subTest(shapes=shapes):self.reject(shapes)

    def test_common_qualified_overlap_rejects_independent_of_order_or_equality(self):
        for common,qualified in (([2],[2]),([2],[3])):
            for shapes in ({'values':common,'MAIN.VALUES':qualified},{'MAIN.VALUES':qualified,'values':common}):
                with self.subTest(shapes=shapes):self.reject(shapes)

    def test_shape_container_and_names_are_strict(self):
        for shapes in ([],False,'VALUES=2',{'':[2]},{'1MAIN.VALUES':[2]},{'MAIN..VALUES':[2]},
                       {'MAIN.VALUES.EXTRA':[2]},{'MAIN.välues':[2]},{1:[2]},{None:[2]}):
            with self.subTest(shapes=shapes):self.reject(shapes)

    def test_shape_dimensions_are_bounded_positive_integers(self):
        for shape in (None,2,'2',[],[1,1,1,1],[0],[-1],[32768],[True],[2.0],{2}):
            with self.subTest(shape=shape):self.reject({'MAIN.VALUES':shape})

    def test_rank_fixed_dimension_and_leaf_guards_remain(self):
        self.reject({'MAIN.VALUES':[2]},sources={'a':source('MAIN',decl='values: ARRAY[*,*] OF INTEGER')})
        self.reject({'MAIN.VALUES':[3,2]},sources={'a':source('MAIN',decl='values: ARRAY[2,*] OF INTEGER')})
        self.reject({'MAIN.VALUES':[32767,2]},sources={'a':source('MAIN',decl='values: ARRAY[*,*] OF INTEGER')},code='E_ARRAY_CAPACITY')

    def test_missing_specializations_keep_the_original_diagnostic(self):
        self.reject(None,code='E_ARRAY_SIZE')
        self.reject({},code='E_ARRAY_SIZE')
        self.reject({'MAIN.VALUES':[2]},sources={'a':source('MAIN'),'b':source('LIB')},code='E_ARRAY_SIZE')

    def test_duplicate_program_names_reject_during_routing(self):
        with self.assertRaisesRegex(ValueError,'Duplicate project program'):
            translate_project({'a':source('MAIN'),'b':source('MAIN')},array_shapes={'values':[2]})


class ProjectArrayShapeCliTests(unittest.TestCase):
    def test_option_parser_accepts_common_and_qualified_literals(self):
        self.assertEqual(project_array_shape_option('Values=2'),('VALUES',(2,)))
        self.assertEqual(project_array_shape_option('mAiN.Values=3,2'),('MAIN.VALUES',(3,2)))
        self.assertEqual(project_array_shape_option('M.V=1,2,3'),('M.V',(1,2,3)))

    def test_option_parser_rejects_expressions_paths_and_unbounded_shapes(self):
        for value in ('VALUES=0','VALUES=-1','VALUES=32768','VALUES=2+2','VALUES=1,2,3,4',
                      'A.B.C=2','A[1]=2','A.=2','.B=2','A=B','A=','A=2.0','A=TRUE','A =2','Ä.B=2'):
            with self.subTest(value=value),self.assertRaises(argparse.ArgumentTypeError):project_array_shape_option(value)

    def cli(self,root,*args):
        return subprocess.run([sys.executable,'-X','utf8','-m','karel2py.project',str(root),*args],
            capture_output=True,text=True,env={**os.environ,'KAREL2PY_GUI_TESTS':'0'},timeout=30)

    def write_project(self,root):
        (root/'main.kl').write_text(source('MAIN','values[3]=7'),encoding='utf-8')
        (root/'lib.kl').write_text(source('LIB'),encoding='utf-8')

    def test_cli_common_shape_checks_without_executing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.write_project(root)
            result=self.cli(root,'--array-shape','VALUES=3')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),{'programs':['LIB','MAIN'],'linked':True})

    def test_cli_qualified_shapes_execute_save_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.write_project(root);state=root/'state.json'
            options=['--array-shape','MAIN.VALUES=3','--array-shape','LIB.VALUES=2','--entry','MAIN','--state-out',str(state)]
            first=self.cli(root,*options)
            self.assertEqual(first.returncode,0,first.stderr)
            values=json.loads(first.stdout)
            self.assertEqual(values['MAIN']['values']['VALUES'],[UNKNOWN,UNKNOWN,7])
            self.assertEqual(len(values['LIB']['values']['VALUES']),2)
            config=json.loads(state.read_text(encoding='utf-8'))
            self.assertTrue(any(row['path']=='VALUES' and row['program']=='MAIN' for row in config['variables']))
            replay=root/'replay.json';replay.write_text(json.dumps(config),encoding='utf-8')
            repeated=self.cli(root,*options,'--context',str(replay))
            self.assertEqual(repeated.returncode,0,repeated.stderr)
            self.assertEqual(json.loads(repeated.stdout),values)

    def test_cli_duplicate_and_unknown_shapes_return_two(self):
        cases=(['--array-shape','MAIN.VALUES=3','--array-shape','main.values=3'],
               ['--array-shape','MAIN.VALUES=3','--array-shape','VALUES=3'],
               ['--array-shape','MISSING.VALUES=3'],['--array-shape','VALUES=3','--array-shape','TYPO=2'],
               ['--array-shape','VALUES=0'],['--array-shape','VALUES=1,2,3,4'])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.write_project(root)
            for options in cases:
                with self.subTest(options=options):
                    result=self.cli(root,*options)
                    self.assertEqual(result.returncode,2,result.stderr)
                    self.assertEqual(result.stdout,'')


if __name__=='__main__':unittest.main()
