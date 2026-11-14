"""Concrete private ARRAY schemas and metadata probes without target execution."""
import builtins
import json
from pathlib import Path
import unittest
from unittest import mock

from karel2py import translate
from karel2py.input_contract import extract
from karel2py.input_discovery import discover_inputs
from tests.test_input_discovery import scan,names


ROOT=Path(__file__).resolve().parents[1]


class PrivateArrayDiscoveryTests(unittest.TestCase):
    def complete(self,report,expected=None):
        self.assertTrue(report['complete'],report['unresolved'])
        self.assertEqual(names(report),expected or {})

    def test_existing_grouped_forwarding_example_has_no_remaining_shape_gaps(self):
        source=(ROOT/'examples/array_formal_forwarding.kl').read_text(encoding='utf-8')
        self.complete(discover_inputs(translate(source).python_source))

    def test_fixed_and_mixed_private_formals_resolve_both_actual_axes(self):
        for shape in ('*,*','2,*','*,2','2,2'):
            with self.subTest(shape=shape):
                report,_=scan('a[1,1]=1 a[1,2]=2 a[2,1]=3 a[2,2]=4 use((a))',
                    decl='a:ARRAY[2,2]OF INTEGER n:INTEGER',routines=f'''ROUTINE use(p:ARRAY[{shape}]OF INTEGER)
                    VAR i,j:INTEGER BEGIN n=0 FOR i=1 TO ARRAY_LEN(p,1) DO
                    FOR j=1 TO ARRAY_LEN(p,2) DO n=n+p[i,j] ENDFOR ENDFOR END use''')
                self.complete(report)

    def test_each_private_call_uses_its_own_shape(self):
        report,_=scan('a[1]=1 a[2]=2 b[1]=1 b[2]=2 b[3]=3 use((a)) use((b))',
            decl='a:ARRAY[2]OF INTEGER b:ARRAY[3]OF INTEGER n:INTEGER',routines='''
            ROUTINE use(p:ARRAY OF INTEGER) VAR i:INTEGER BEGIN
            FOR i=1 TO ARRAY_LEN(p) DO n=p[i] ENDFOR END use''')
        self.complete(report)

    def test_nested_named_components_supply_logical_metadata_dimensions(self):
        report,_=scan('a[1,1]=1 a[1,2]=2 use((a))',prefix='TYPE row_t=ARRAY[2]OF INTEGER',
            decl='a:ARRAY[1]OF row_t n:INTEGER',routines='''ROUTINE use(p:ARRAY[*,*]OF INTEGER)
            VAR i:INTEGER BEGIN FOR i=1 TO ARRAY_LEN(p,2) DO n=p[1,i] ENDFOR END use''')
        self.complete(report)

    def test_named_formals_and_inline_layers_keep_concrete_values(self):
        for formal in ('row_t','ARRAY[*]OF ARRAY[*]OF INTEGER'):
            with self.subTest(formal=formal):
                report,_=scan('a[1,1]=1 a[1,2]=2 use((a))',prefix='TYPE row_t=ARRAY[1,2]OF INTEGER',
                    decl='a:row_t n:INTEGER',routines=f'''ROUTINE use(p:{formal}) VAR i:INTEGER
                    BEGIN FOR i=1 TO ARRAY_LEN(p,2) DO n=p[1,i] ENDFOR END use''')
                self.complete(report)

    def test_existing_numeric_value_conversion_uses_target_terminal(self):
        report,_=scan('a[1]=1 a[2]=2 use(a)',decl='a:ARRAY[2]OF INTEGER n:REAL',routines='''
            ROUTINE use(p:ARRAY OF REAL) VAR i:INTEGER BEGIN
            FOR i=1 TO ARRAY_LEN(p) DO n=p[i] ENDFOR END use''')
        self.complete(report)

    def test_string_array_element_capacity_is_inherited_without_false_branch_pruning(self):
        report,_=scan("a[1]='abc' use((a))",decl='a:ARRAY[1]OF STRING[3] n,x:INTEGER',routines='''
            ROUTINE use(p:ARRAY OF STRING) BEGIN p[1]='abcd'
            IF p[1]='abc' THEN n=x ENDIF END use''')
        self.complete(report,{('variable','X'):'conditional'})

    def test_private_scalar_string_has_its_existing_254_character_capacity(self):
        report,_=scan("text='abc' use((text))",decl='text:STRING[3] x,y,n:INTEGER',routines='''
            ROUTINE use(p:STRING) BEGIN p='abcd'
            IF p='abcd' THEN n=x ELSE n=y ENDIF END use''')
        self.complete(report,{('variable','X'):'required'})

    def test_integral_to_short_array_conversion_keeps_a_possible_missing_sentinel_explicit(self):
        report,_=scan('a[1]=32767 use(a)',decl='a:ARRAY[1]OF INTEGER n:INTEGER',routines='''
            ROUTINE use(p:ARRAY OF SHORT) BEGIN n=p[1] END use''')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))

    def test_partial_private_aggregate_has_a_derived_gap_instead_of_a_fake_local_input(self):
        report,_=scan('a[1]=7 use((a))',decl='a:ARRAY[2]OF INTEGER n:INTEGER',routines='''
            ROUTINE use(p:ARRAY OF INTEGER) BEGIN n=p[2] END use''')
        self.assertEqual(names(report),{('variable','A'):'required'})
        self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))
        self.assertFalse(any(row['code']=='selection' for row in report['unresolved']))

    def test_private_writes_do_not_initialize_original_cells(self):
        report,_=scan('use((a)) n=a[1]',decl='a:ARRAY[1]OF INTEGER n:INTEGER',routines='''
            ROUTINE use(p:ARRAY OF INTEGER) BEGIN p[1]=7 END use''')
        self.complete(report,{('variable','A'):'required',('variable','A[1]'):'required'})

    def test_borrowed_writes_still_initialize_original_cells(self):
        report,_=scan('use(a) n=a[1]',decl='a:ARRAY[1]OF INTEGER n:INTEGER',routines='''
            ROUTINE use(p:ARRAY OF INTEGER) BEGIN p[1]=7 END use''')
        self.complete(report)

    def test_wrong_concrete_forwarding_shape_does_not_publish_callee_write_facts(self):
        report,_=scan('outer(a) n=x',decl='a:ARRAY[3]OF INTEGER x,n:INTEGER',routines='''
            ROUTINE inner(p:ARRAY[2]OF INTEGER) BEGIN x=7 END inner
            ROUTINE outer(p:ARRAY OF INTEGER) BEGIN inner(p) END outer''')
        self.assertFalse(report['complete'])
        self.assertTrue(any(row['code']=='parameter-shape' for row in report['unresolved']))
        self.assertEqual(names(report),{('variable','X'):'conditional'})


class ArrayMetadataAndReturnDiscoveryTests(unittest.TestCase):
    def test_authored_examples_have_independent_discovery_and_execution_fixtures(self):
        from tools.run_examples import run_example
        for name in ('discovery_private_arrays','discovery_array_shape_results'):
            with self.subTest(name=name):
                path=ROOT/'examples'/(name+'.kl');run_example(path)
                report=discover_inputs(translate(path.read_text(encoding='utf-8')).python_source)
                self.assertTrue(report['complete'],report['unresolved'])
                summary=[{key:row[key] for key in ('kind','path','certainty')} for row in report['inputs']]
                self.assertEqual(summary,json.loads((path.parent/(name+'.inputs.expected.json')).read_bytes()))

    def test_array_len_bounded_loop_reports_each_original_input_cell(self):
        report,_=scan('FOR i=1 TO ARRAY_LEN(a) DO n=a[i] ENDFOR',decl='a:ARRAY[3]OF INTEGER i,n:INTEGER')
        self.assertTrue(report['complete'],report['unresolved'])
        self.assertEqual(names(report),{('variable','A[1]'):'required',('variable','A[2]'):'required',('variable','A[3]'):'required'})

    def test_length_probe_of_missing_data_and_selected_rows_does_not_read_cells(self):
        report,_=scan('n=ARRAY_LEN(a[1]) IF n=3 THEN n=x ELSE n=y ENDIF',decl='a:ARRAY[2,3]OF INTEGER n,x,y:INTEGER')
        self.assertTrue(report['complete'],report['unresolved'])
        self.assertEqual(names(report),{('variable','X'):'required'})

    def test_dynamic_dimension_is_read_without_inventing_a_constant_length(self):
        report,_=scan('n=ARRAY_LEN(a,d) IF n=2 THEN n=x ELSE n=y ENDIF',decl='a:ARRAY[2,3]OF INTEGER d,n,x,y:INTEGER')
        self.assertEqual(names(report),{('variable','D'):'required',('variable','X'):'conditional',('variable','Y'):'conditional'})

    def test_three_dimensional_metadata_in_a_private_frame(self):
        report,_=scan('use((a))',decl='a:ARRAY[1,2,3]OF INTEGER n,x,y:INTEGER',routines='''
            ROUTINE use(p:ARRAY[*,*,*]OF INTEGER) BEGIN
            IF ARRAY_LEN(p,3)=3 THEN n=x ELSE n=y ENDIF END use''')
        self.assertTrue(report['complete'],report['unresolved'])
        self.assertEqual(names(report),{('variable','A'):'required',('variable','X'):'required'})

    def test_result_shape_supplies_private_parameter_and_metadata_loop(self):
        report,_=scan('consume(make())',decl='n:INTEGER',routines='''
            ROUTINE make:ARRAY[*]OF INTEGER VAR a:ARRAY[2]OF INTEGER
            BEGIN a[1]=7 a[2]=9 RETURN a END make
            ROUTINE consume(p:ARRAY OF INTEGER) VAR i:INTEGER
            BEGIN FOR i=1 TO ARRAY_LEN(p) DO n=p[i] ENDFOR END consume''')
        self.assertTrue(report['complete'],report['unresolved']);self.assertEqual(report['inputs'],[])

    def test_result_metadata_call_is_analyzed_once_in_source_order(self):
        report,_=scan('calls=0 n=ARRAY_LEN(make()) IF calls=1 THEN n=x ELSE n=y ENDIF',decl='calls,n,x,y:INTEGER',routines='''
            ROUTINE make:ARRAY[*]OF INTEGER VAR a:ARRAY[2]OF INTEGER
            BEGIN calls=calls+1 RETURN a END make''')
        self.assertEqual(names(report),{('variable','X'):'required'})
        self.assertTrue(any(row['code']=='local-value' for row in report['unresolved']))

    def test_equal_return_shapes_merge_but_conflicting_shapes_remain_partial(self):
        for size in (2,3):
            with self.subTest(size=size):
                report,_=scan('consume(make())',decl='flag:BOOLEAN n,x,y:INTEGER',routines=f'''
                    ROUTINE make:ARRAY[*]OF INTEGER VAR a:ARRAY[2]OF INTEGER b:ARRAY[{size}]OF INTEGER
                    BEGIN IF flag THEN RETURN a ELSE RETURN b ENDIF END make
                    ROUTINE consume(p:ARRAY OF INTEGER) BEGIN
                    IF ARRAY_LEN(p)=2 THEN n=x ELSE n=y ENDIF END consume''')
                expected={('variable','FLAG'):'required',('variable','X'):'required' if size==2 else 'conditional'}
                if size==3:expected[('variable','Y')]='conditional'
                self.assertEqual(names(report),expected)
                self.assertTrue(any(row['code']=='local-value' for row in report['unresolved']))

    def test_uninit_remains_a_nonreading_nonconstant_probe(self):
        report,_=scan('IF UNINIT(a[1]) THEN n=x ELSE n=y ENDIF',decl='a:ARRAY[2]OF INTEGER n,x,y:INTEGER')
        self.assertEqual(names(report),{('variable','X'):'conditional',('variable','Y'):'conditional'})
        self.assertTrue(report['complete'])

    def test_scalar_result_coercion_cannot_hide_a_reachable_branch(self):
        report,_=scan('IF make()=1 THEN n=x ELSE n=y ENDIF',routines='ROUTINE make:INTEGER BEGIN RETURN 1.9 END make')
        self.assertEqual(names(report),{('variable','X'):'conditional',('variable','Y'):'conditional'})
        self.assertTrue(report['complete'])

    def test_discovery_has_no_runtime_or_target_execution_and_does_not_mutate_contract(self):
        source=(ROOT/'examples/array_formal_forwarding.kl').read_text(encoding='utf-8')
        result=translate(source);plan=extract(result.python_source);saved=json.dumps(plan,sort_keys=True)
        with mock.patch.object(builtins,'exec',side_effect=AssertionError('target execution')),mock.patch.object(builtins,'eval',side_effect=AssertionError('target evaluation')):
            report=discover_inputs(result.python_source)
        self.assertTrue(report['complete'],report['unresolved'])
        self.assertEqual(saved,json.dumps(extract(result.python_source),sort_keys=True))


if __name__=='__main__':unittest.main()
