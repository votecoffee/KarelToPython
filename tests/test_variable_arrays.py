"""Explicit translation specialization for direct static wildcard ARRAYs."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from karel2py import runtime as rt


UNKNOWN = {'uninitialized': True}


def compile_program(body='', *, declarations='a: ARRAY[*] OF INTEGER', types='', routines='', shapes=None, labelled=False, _translator=translate):
    label = 'entry::\n' if labelled else ''
    source = f'PROGRAM T\n{types}\nVAR\n{declarations}\n{routines}\nBEGIN\n{label}{body}\nEND T'
    result = _translator(source, filename='external_arrays.kl', array_shapes=shapes)
    ast.parse(result.python_source, feature_version=(3, 11))
    namespace = {'__name__': 'variable_array_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](), result


def execute(body='', **kwargs): return compile_program(body, **kwargs)[0].run()


class VariableArrayExecutionTests(unittest.TestCase):
    def test_no_values_are_invented_from_dimensions(self):
        self.assertEqual(execute(shapes={'a': [3]}), {'A': [UNKNOWN, UNKNOWN, UNKNOWN]})

    def test_one_based_write_and_array_len(self):
        state = execute('a[3]=7 n=ARRAY_LEN(a)', declarations='a: ARRAY[*] OF INTEGER n: INTEGER', shapes={'a': [3]})
        self.assertEqual(state, {'A': [UNKNOWN, UNKNOWN, 7], 'N': 3})

    def test_two_dimensional_storage(self):
        self.assertEqual(execute('a[2,3]=7', declarations='a: ARRAY[*,*] OF INTEGER', shapes={'a': [2,3]})['A'], [[UNKNOWN]*3, [UNKNOWN, UNKNOWN, 7]])

    def test_three_dimensional_storage(self):
        self.assertEqual(execute('a[2,1,2]=7', declarations='a: ARRAY[*,*,*] OF INTEGER', shapes={'a': [2,1,2]})['A'], [[[UNKNOWN,UNKNOWN]], [[UNKNOWN,7]]])

    def test_mixed_first_wildcard(self):
        self.assertEqual(execute('a[2,3]=7', declarations='a: ARRAY[*,3] OF INTEGER', shapes={'a': [2,3]})['A'][1][2], 7)

    def test_mixed_last_wildcard_constant_expression(self):
        state = execute('a[2,3]=7', types='CONST rows=1+1', declarations='a: ARRAY[rows,*] OF INTEGER', shapes={'a': [2,3]})
        self.assertEqual(state['A'][1][2], 7)

    def test_mixed_middle_wildcard(self):
        self.assertEqual(execute('a[1,2,3]=7', declarations='a: ARRAY[1,*,3] OF INTEGER', shapes={'a': [1,2,3]})['A'][0][1][2], 7)

    def test_grouped_variables_have_independent_shapes(self):
        state = execute('a[2]=7 b[3]=9', declarations='a,b: ARRAY[*] OF INTEGER', shapes={'a':[2], 'b':[3]})
        self.assertEqual(state, {'A':[UNKNOWN,7], 'B':[UNKNOWN,UNKNOWN,9]})

    def test_copy_is_independent(self):
        state = execute('a[1]=7 b=a a[1]=9', declarations='a,b: ARRAY[*] OF INTEGER', shapes={'a':[2], 'b':[2]})
        self.assertEqual(state, {'A':[9,UNKNOWN], 'B':[7,UNKNOWN]})

    def test_copy_between_fixed_and_specialized_arrays(self):
        state = execute('a[1]=7 b=a a=b', declarations='a: ARRAY[*] OF INTEGER b: ARRAY[2] OF INTEGER', shapes={'a':[2]})
        self.assertEqual(state, {'A':[7,UNKNOWN], 'B':[7,UNKNOWN]})

    def test_reference_forwarding_retains_concrete_shape(self):
        routines = 'ROUTINE fill(p: ARRAY OF INTEGER) BEGIN p[ARRAY_LEN(p)]=7 END fill\nROUTINE forward(p: ARRAY[*] OF INTEGER) BEGIN fill(p) END forward'
        self.assertEqual(execute('forward(a)', routines=routines, shapes={'a':[3]})['A'], [UNKNOWN,UNKNOWN,7])

    def test_two_dimensional_reference(self):
        routine = 'ROUTINE fill(p: ARRAY[*,*] OF INTEGER) BEGIN p[2,3]=7 END fill'
        self.assertEqual(execute('fill(a)', declarations='a: ARRAY[*,3] OF INTEGER', routines=routine, shapes={'a':[2,3]})['A'][1][2], 7)

    def test_named_subarray_reference(self):
        routine = 'ROUTINE fill(p: row_t) BEGIN p[2]=7 END fill'
        program, result = compile_program('fill(a[2,1])', types='TYPE row_t=ARRAY[2] OF INTEGER', declarations='a: ARRAY[*,*] OF row_t', routines=routine, shapes={'a':[2,1]})
        self.assertEqual(program.run()['A'][1][0], [UNKNOWN,7])
        self.assertEqual(program._state.raw('A').spec[2][3], 'ROW_T')
        self.assertEqual(result.report['variable_array_declarations'][0]['logical_dimensions'], [2,1,2])

    def test_structure_elements_use_existing_initialization_rules(self):
        state = execute('a[2].value=7', types='TYPE packet_t=STRUCTURE value: INTEGER ENDSTRUCTURE', declarations='a: ARRAY[*] OF packet_t', shapes={'a':[2]})
        self.assertEqual(state['A'], [{'VALUE':UNKNOWN},{'VALUE':7}])

    def test_string_elements_retain_capacity(self):
        self.assertEqual(execute("a[1]='abcdef'", declarations='a: ARRAY[*] OF STRING[3]', shapes={'a':[1]})['A'], ['abc'])

    def test_boolean_elements(self):
        self.assertEqual(execute('a[1]=ON', declarations='a: ARRAY[*] OF BOOLEAN', shapes={'a':[1]})['A'], [True])

    def test_real_elements(self):
        self.assertEqual(execute('a[1]=1.25', declarations='a: ARRAY[*] OF REAL', shapes={'a':[1]})['A'], [1.25])

    def test_byte_elements_remain_unknown(self):
        self.assertEqual(execute(declarations='a: ARRAY[*] OF BYTE', shapes={'a':[1]})['A'], [{'unknown_byte':True}])

    def test_short_elements_use_existing_sentinel(self):
        self.assertEqual(execute('a[1]=32767', declarations='a: ARRAY[*] OF SHORT', shapes={'a':[1]})['A'], [UNKNOWN])

    def test_joint_elements_remain_uninitialized(self):
        self.assertEqual(execute(declarations='a: ARRAY[*] OF JOINTPOS3', shapes={'a':[1]})['A'], [{'axes':[UNKNOWN]*3}])

    def test_boundary_guard_preserves_prior_write(self):
        program, _ = compile_program('a[1]=7 a[3]=9', shapes={'a':[2]})
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside 1..2'): program.run()
        self.assertEqual(program.snapshot()['A'], [7,UNKNOWN])

    def test_generic_copy_mismatched_shapes_guarded_before_write(self):
        routine = 'ROUTINE copy(p,q: ARRAY OF INTEGER) BEGIN p=q END copy'
        program, _ = compile_program('a[1]=7 b[1]=9 copy(a,b)', declarations='a,b: ARRAY[*] OF INTEGER', routines=routine, shapes={'a':[2],'b':[3]})
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'matching logical dimensions'): program.run()
        self.assertEqual(program.snapshot()['A'], [7,UNKNOWN])

    def test_labelled_and_structured_execution_match(self):
        outcomes=[]
        for labelled in (False,True):
            program, _ = compile_program('a[1]=7 IF a[1]=7 THEN a[2]=9 ENDIF', shapes={'a':[2]}, labelled=labelled)
            outcomes.append((program.run(), program._state.steps))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_distinct_translations_allow_distinct_sizes(self):
        self.assertEqual(len(execute(shapes={'a':[2]})['A']),2)
        self.assertEqual(len(execute(shapes={'a':[3]})['A']),3)

    def test_program_instances_have_independent_storage(self):
        program, result = compile_program('a[1]=7', shapes={'a':[2]})
        namespace={'__name__':'another'}
        exec(result.python_source,namespace)
        other=namespace['Program']()
        program.run()
        self.assertEqual(other.snapshot()['A'], [UNKNOWN,UNKNOWN])


class VariableArrayContextTests(unittest.TestCase):
    def reject(self, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(**kwargs)
        self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_missing_context(self): self.reject('E_ARRAY_SIZE')
    def test_empty_context(self): self.reject('E_ARRAY_SIZE',shapes={})
    def test_missing_second_declaration(self): self.reject('E_ARRAY_SIZE',declarations='a,b: ARRAY[*] OF INTEGER',shapes={'a':[2]})
    def test_fixed_dimension_mismatch(self): self.reject('E_ARRAY_CONTEXT',declarations='a: ARRAY[2,*] OF INTEGER',shapes={'a':[3,4]})
    def test_outer_rank_mismatch(self): self.reject('E_ARRAY_CONTEXT',declarations='a: ARRAY[*,*] OF INTEGER',shapes={'a':[2]})
    def test_named_element_shape_does_not_include_inner_dimensions(self): self.reject('E_ARRAY_CONTEXT',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='a: ARRAY[*] OF row_t',shapes={'a':[2,2]})
    def test_case_insensitive_duplicates(self): self.reject('E_ARRAY_CONTEXT',shapes={'a':[2],'A':[2]})
    def test_unused_name(self): self.reject('E_ARRAY_CONTEXT',shapes={'a':[2],'typo':[2]})
    def test_fixed_array_context_not_silently_used(self): self.reject('E_ARRAY_CONTEXT',declarations='a: ARRAY[2] OF INTEGER',shapes={'a':[2]})
    def test_scalar_context_rejected(self): self.reject('E_ARRAY_CONTEXT',declarations='a: INTEGER',shapes={'a':[2]})
    def test_named_array_context_rejected(self): self.reject('E_ARRAY_CONTEXT',types='TYPE row_t=ARRAY[2] OF INTEGER',declarations='a: row_t',shapes={'a':[2]})
    def test_context_for_local_only_rejected(self): self.reject('E_ARRAY_CONTEXT',declarations='x: INTEGER',routines='ROUTINE f VAR a: ARRAY[2] OF INTEGER BEGIN END f',shapes={'a':[2]})
    def test_invalid_context_containers(self):
        for context in ([],(),42,'a=2',False):
            with self.subTest(context=context): self.reject('E_ARRAY_CONTEXT',shapes=context)
    def test_invalid_context_names(self):
        for name in ('','1a','a.b','a[1]','\u00e4','a b',2,None):
            with self.subTest(name=name): self.reject('E_ARRAY_CONTEXT',shapes={name:[2]})
    def test_invalid_shape_containers_and_ranks(self):
        for shape in (2,'2',None,[],[1,1,1,1],{2},iter([2])):
            with self.subTest(shape=shape): self.reject('E_ARRAY_CONTEXT',shapes={'a':shape})
    def test_invalid_dimensions(self):
        for dimension in (True,False,0,-1,32768,2.0,'2',None):
            with self.subTest(dimension=dimension): self.reject('E_ARRAY_CONTEXT',shapes={'a':[dimension]})
    def test_named_type_wildcard_prohibited(self): self.reject('E_VARIABLE_ARRAY_SCOPE',types='TYPE row_t=ARRAY[*] OF INTEGER',declarations='a: row_t',shapes={'a':[2]})
    def test_structure_field_wildcard_prohibited(self): self.reject('E_VARIABLE_ARRAY_SCOPE',types='TYPE packet_t=STRUCTURE values: ARRAY[*] OF INTEGER ENDSTRUCTURE',declarations='a: packet_t',shapes={'a':[2]})
    def test_routine_local_wildcard_prohibited(self): self.reject('E_VARIABLE_ARRAY_SCOPE',declarations='x: INTEGER',routines='ROUTINE f VAR a: ARRAY[*] OF INTEGER BEGIN END f')
    def test_wildcard_in_unreachable_local_still_checked(self): self.reject('E_VARIABLE_ARRAY_SCOPE',declarations='x: INTEGER',routines='ROUTINE unused VAR a: ARRAY[2,*] OF INTEGER BEGIN END unused')
    def test_four_outer_dimensions_prohibited(self): self.reject('E_ARRAY_RANK',declarations='a: ARRAY[*,*,*,*] OF INTEGER',shapes={'a':[2]})
    def test_four_logical_dimensions_prohibited(self): self.reject('E_ARRAY_RANK',types='TYPE row_t=ARRAY[2,2] OF INTEGER',declarations='a: ARRAY[*,*] OF row_t',shapes={'a':[2,2]})
    def test_element_count_bound(self): self.reject('E_ARRAY_CAPACITY',declarations='a: ARRAY[*,*] OF INTEGER',shapes={'a':[256,128]})
    def test_scalar_leaf_bound_includes_structure_fields(self): self.reject('E_ARRAY_CAPACITY',types='TYPE pair_t=STRUCTURE x: INTEGER y: INTEGER ENDSTRUCTURE',declarations='a: ARRAY[*] OF pair_t',shapes={'a':[16384]})
    def test_fixed_dimension_type_stays_strict(self): self.reject('E_SIZE',declarations='a: ARRAY[TRUE,*] OF INTEGER',shapes={'a':[1,2]})
    def test_fixed_dimension_range_stays_strict(self): self.reject('E_SIZE',declarations='a: ARRAY[0,*] OF INTEGER',shapes={'a':[1,2]})
    def test_fixed_dimension_must_remain_constant(self): self.reject('E_CONSTANT',declarations='n: INTEGER a: ARRAY[n,*] OF INTEGER',shapes={'a':[2,2]})
    def test_whole_copy_mismatched_shapes_rejected_statically(self): self.reject('E_TYPE',body='a=b',declarations='a,b: ARRAY[*] OF INTEGER',shapes={'a':[2],'b':[3]})
    def test_multidimensional_array_len_stays_blocked(self): self.reject('E_ARRAY_LEN',body='n=ARRAY_LEN(a)',declarations='a: ARRAY[*,*] OF INTEGER n: INTEGER',shapes={'a':[2,2]}, _translator=legacy_translate)
    def test_implicit_zero_or_resize_not_introduced(self):
        self.reject('E_ARRAY_SIZE')
        self.assertEqual(execute(shapes={'a':[1]})['A'],[UNKNOWN])


class VariableArrayEvidenceTests(unittest.TestCase):
    def test_report_records_original_and_resolved_dimensions(self):
        _, result = compile_program(types='CONST rows=2',declarations='a: ARRAY[rows,*] OF INTEGER',shapes={'a':[2,3]})
        self.assertEqual(result.report['variable_array_declarations'],[dict(name='A',line=4,column=1,declared_dimensions=[2,'*'],resolved_outer_dimensions=[2,3],wildcard_dimensions=[2],logical_dimensions=[2,3])])
        self.assertIn('externally sized static ARRAY',result.report['features'])
        self.assertFalse(result.report['variable_array_policy']['controller_validated'])

    def test_context_hash_is_independent_of_spelling_order_and_container(self):
        args=dict(declarations='a,b: ARRAY[*] OF INTEGER')
        first=compile_program(shapes={'b':[3],'a':[2]},**args)[1]
        second=compile_program(shapes={'A':(2,),'B':(3,)},**args)[1]
        self.assertEqual(first.python_source,second.python_source)
        self.assertEqual(first.report['translation_context_sha256'],second.report['translation_context_sha256'])
        encoded=json.dumps(first.report['translation_context'],sort_keys=True,separators=(',',':')).encode('ascii')
        self.assertEqual(hashlib.sha256(encoded).hexdigest(),first.report['translation_context_sha256'])

    def test_same_source_different_context_has_different_generated_hash(self):
        first=compile_program(shapes={'a':[2]})[1]
        second=compile_program(shapes={'a':[3]})[1]
        self.assertEqual(first.report['source_sha256'],second.report['source_sha256'])
        self.assertNotEqual(first.report['translation_context_sha256'],second.report['translation_context_sha256'])
        self.assertNotEqual(first.report['python_sha256'],second.report['python_sha256'])

    def test_host_context_is_copied_and_generated_metadata_is_immutable(self):
        shapes={'a':[2]}
        program,result=compile_program(shapes=shapes)
        shapes['a'][0]=9
        self.assertEqual(program.external_array_shapes,(('A',(2,)),))
        self.assertEqual(result.report['translation_context'],{'mode':'pythonic','array_shapes':{'A':[2]}})
        self.assertEqual(len(program.run()['A']),2)

    def test_fixed_and_formal_arrays_need_no_context(self):
        _,result=compile_program(declarations='a: ARRAY[2] OF INTEGER',routines='ROUTINE f(p: ARRAY[*] OF INTEGER) BEGIN END f')
        self.assertEqual(result.report['variable_array_declarations'],[])
        self.assertEqual(result.report['translation_context'],{'mode':'pythonic','array_shapes':{}})

    def test_missing_shape_diagnostic_has_original_variable_location(self):
        with self.assertRaises(TranslationError) as caught: compile_program()
        self.assertEqual((caught.exception.token.line,caught.exception.token.column),(4,1))

    def test_continued_declaration_preserves_physical_locations(self):
        _,result=compile_program(declarations='a: ARRAY &\n[2,*] OF INTEGER',shapes={'a':[2,3]})
        self.assertEqual(result.report['variable_array_declarations'][0]['line'],4)
        self.assertTrue(result.report['continuations'])


class VariableArrayCLITests(unittest.TestCase):
    def run_cli(self,*arguments):
        return subprocess.run([sys.executable,'-m','karel2py',*map(str,arguments)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)

    def test_cli_compiles_checks_reports_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'probe.kl'; output=root/'probe.py'; report=root/'probe.json'
            raw=b'PROGRAM T VAR a: ARRAY[2,*] OF INTEGER BEGIN a[2,3]=7 END T'
            source.write_bytes(raw)
            result=self.run_cli(source,'--array-shape','a=2,3','-o',output,'--report',report)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(source.read_bytes(),raw)
            data=json.loads(report.read_text())
            self.assertEqual(data['translation_context'],{'mode':'pythonic','array_shapes':{'A':[2,3]}})
            namespace={'__name__':'cli_test'}; exec(output.read_text(),namespace)
            self.assertEqual(namespace['Program']().run()['A'][1][2],7)
            self.assertEqual(self.run_cli(source,'--check','--array-shape','A=2,3').returncode,0)
            rejected=root/'rejected.json'
            self.assertEqual(self.run_cli(source,'--check','--array-shape','A=3,3','--report',rejected).returncode,2)
            self.assertEqual(json.loads(rejected.read_text())['diagnostics'][0]['code'],'E_ARRAY_CONTEXT')

    def test_cli_missing_context_reports_rejection_without_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'probe.kl'; output=root/'probe.py'; report=root/'probe.json'
            source.write_text('PROGRAM T VAR a: ARRAY[*] OF INTEGER BEGIN END T')
            result=self.run_cli(source,'-o',output,'--report',report)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertFalse(output.exists())
            self.assertEqual(json.loads(report.read_text())['diagnostics'][0]['code'],'E_ARRAY_SIZE')

    def test_cli_invalid_context_options(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'probe.kl'; source.write_text('PROGRAM T BEGIN END T')
            for option in ('a=0','a=-1','a=32768','a=1,1,1,1','a=1.0','a=1,','a=1+1','a.b=2','a=2;print(7)'):
                with self.subTest(option=option): self.assertEqual(self.run_cli(source,'--check','--array-shape',option).returncode,2)

    def test_cli_duplicate_names_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'probe.kl'; source.write_text('PROGRAM T VAR a: ARRAY[*] OF INTEGER BEGIN END T')
            result=self.run_cli(source,'--check','--array-shape','a=2','--array-shape','A=3')
            self.assertEqual(result.returncode,2)
            self.assertIn('Duplicate case-insensitive',result.stderr)


if __name__=='__main__': unittest.main()
