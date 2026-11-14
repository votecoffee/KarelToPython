"""Independent per-leaf facts for legal partial data copies and conversions."""
import json
from pathlib import Path
import unittest
from unittest import mock

from karel2py import translate,load_project
from karel2py.input_contract import extract
from karel2py.input_discovery import discover_inputs
from karel2py.lexer import TranslationError
from tests.test_input_discovery import scan,names


ROOT=Path(__file__).resolve().parents[1]
ROW='TYPE row_t=STRUCTURE known:INTEGER unused:REAL ENDSTRUCTURE'


class PartialCopyFactTests(unittest.TestCase):
    def test_known_array_cell_survives_a_partial_whole_copy(self):
        report,_=scan('a[1]=7 b=a n=b[1]',decl='a,b:ARRAY[2]OF INTEGER n:INTEGER')
        self.assertEqual(names(report),{('variable','A'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_missing_copied_cell_remains_derived_instead_of_a_fake_input(self):
        report,_=scan('a[1]=7 b=a n=b[2]',decl='a,b:ARRAY[2]OF INTEGER n:INTEGER')
        self.assertEqual(names(report),{('variable','A'):'required'})
        self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))

    def test_partial_overwrite_clears_an_old_destination_cell_fact(self):
        report,_=scan('b[2]=8 a[1]=7 b=a n=b[2]',decl='a,b:ARRAY[2]OF INTEGER n:INTEGER')
        self.assertEqual(names(report),{('variable','A'):'required'})
        self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))

    def test_chained_copies_do_not_erase_known_facts_or_add_target_inputs(self):
        report,_=scan('a[1]=7 b=a c=b n=c[1]',decl='a,b,c:ARRAY[2]OF INTEGER n:INTEGER')
        self.assertEqual(names(report),{('variable','A'):'required'});self.assertTrue(report['complete'])

    def test_exact_known_leaf_constants_can_select_a_branch(self):
        report,_=scan('a.known=7 b=a IF b.known=7 THEN n=x ELSE n=y ENDIF',prefix=ROW,decl='a,b:row_t n,x,y:INTEGER')
        self.assertEqual(names(report),{('variable','A'):'required',('variable','X'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_nested_records_arrays_and_selected_copies_keep_relative_leaf_paths(self):
        report,_=scan('a.items[2].known=7 b=a.items n=b[2].known',prefix=ROW+' TYPE box_t=STRUCTURE items:ARRAY[2]OF row_t ENDSTRUCTURE',
            decl='a:box_t b:ARRAY[2]OF row_t n:INTEGER')
        self.assertEqual(names(report),{('variable','A.ITEMS'):'required'});self.assertTrue(report['complete'],report['unresolved'])

    def test_prefix_copies_preserve_known_cells(self):
        report,_=scan('a[1,2]=7 b=a[1] n=b[2]',decl='a:ARRAY[2,2]OF INTEGER b:ARRAY[2]OF INTEGER n:INTEGER')
        self.assertEqual(names(report),{('variable','A[1]'):'required'});self.assertTrue(report['complete'],report['unresolved'])

    def test_both_branch_copies_keep_only_definitely_available_leaf_facts(self):
        report,_=scan('a[1]=7 c[1]=9 IF flag THEN b=a ELSE b=c ENDIF n=b[1]',
            decl='a,b,c:ARRAY[2]OF INTEGER n:INTEGER flag:BOOLEAN')
        self.assertTrue(report['complete'],report['unresolved'])
        self.assertEqual(names(report),{('variable','FLAG'):'required',('variable','A'):'conditional',('variable','C'):'conditional'})

    def test_a_conditional_copy_cannot_initialize_untaken_destination(self):
        report,_=scan('a[1]=7 IF flag THEN b=a ENDIF n=b[1]',decl='a,b:ARRAY[2]OF INTEGER n:INTEGER flag:BOOLEAN')
        self.assertIn(('variable','B[1]'),names(report));self.assertEqual(names(report)[('variable','B[1]')],'conditional')

    def test_source_facts_are_captured_before_later_target_selector_effects(self):
        report,_=scan('source.known=7 bank[pick()]=source IF bank[1].known=7 THEN n=x ELSE n=y ENDIF',prefix=ROW,
            decl='source:row_t bank:ARRAY[2]OF row_t n,x,y:INTEGER',
            routines='ROUTINE pick:INTEGER BEGIN source.known=99 RETURN 1 END pick')
        self.assertEqual(names(report),{('variable','SOURCE'):'required',('variable','X'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_numeric_schema_conversion_retains_availability_without_uncast_constants(self):
        report,_=scan('a[1]=1.9 b=a IF b[1]=1 THEN n=x ELSE n=y ENDIF',
            decl='a:ARRAY[2]OF REAL b:ARRAY[2]OF INTEGER n,x,y:INTEGER')
        self.assertEqual(names(report),{('variable','A'):'required',('variable','X'):'conditional',('variable','Y'):'conditional'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_truncating_string_copy_cannot_prune_a_reachable_read(self):
        report,_=scan("a[1]='abcd' b=a IF b[1]='abc' THEN n=x ELSE n=y ENDIF",
            decl='a:ARRAY[2]OF STRING[4] b:ARRAY[2]OF STRING[3] n,x,y:INTEGER')
        self.assertEqual(names(report),{('variable','A'):'required',('variable','X'):'conditional',('variable','Y'):'conditional'})
        self.assertTrue(report['complete'],report['unresolved'])


class PrivateAndResultFactTests(unittest.TestCase):
    def test_grouped_partial_value_and_private_writes_do_not_change_caller_facts(self):
        report,_=scan('a[1]=7 use((a)) n=a[1]',decl='a:ARRAY[2]OF INTEGER n:INTEGER',
            routines='ROUTINE use(p:ARRAY OF INTEGER) BEGIN n=p[1] p[1]=99 END use')
        self.assertEqual(names(report),{('variable','A'):'required'});self.assertTrue(report['complete'],report['unresolved'])

    def test_private_write_does_not_initialize_a_missing_caller_cell(self):
        report,_=scan('a[1]=7 use((a)) n=a[2]',decl='a:ARRAY[2]OF INTEGER n:INTEGER',
            routines='ROUTINE use(p:ARRAY OF INTEGER) BEGIN p[2]=99 END use')
        self.assertEqual(names(report),{('variable','A'):'required',('variable','A[2]'):'required'})

    def test_fresh_partial_local_can_be_copied_without_inventing_a_local_input(self):
        report,_=scan('use()',decl='n:INTEGER',routines='''ROUTINE use VAR a,b:ARRAY[2]OF INTEGER
            BEGIN a[1]=7 b=a n=b[1] END use''')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])

    def test_partial_local_result_retains_known_cells_after_frame_cleanup(self):
        report,_=scan('b=make() n=b[1]',decl='b:ARRAY[2]OF INTEGER n:INTEGER',routines='''
            ROUTINE make:ARRAY OF INTEGER VAR a:ARRAY[2]OF INTEGER BEGIN a[1]=7 RETURN a END make''')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])

    def test_partial_record_result_can_feed_another_private_call(self):
        report,_=scan('use(make())',prefix=ROW,decl='n:INTEGER',routines='''
            ROUTINE make:row_t VAR a:row_t BEGIN a.known=7 RETURN a END make
            ROUTINE use(p:row_t) BEGIN n=p.known END use''')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])

    def test_matching_return_shapes_merge_available_leaves_and_only_common_constants(self):
        for second in (7,9):
            with self.subTest(second=second):
                report,_=scan('b=make() IF b[1]=7 THEN n=x ELSE n=y ENDIF',decl='b:ARRAY[2]OF INTEGER n,x,y:INTEGER flag:BOOLEAN',routines=f'''
                    ROUTINE make:ARRAY OF INTEGER VAR a,c:ARRAY[2]OF INTEGER
                    BEGIN a[1]=7 c[1]={second} IF flag THEN RETURN a ELSE RETURN c ENDIF END make''')
                expected={('variable','FLAG'):'required',('variable','X'):'required' if second==7 else 'conditional'}
                if second!=7:expected[('variable','Y')]='conditional'
                self.assertEqual(names(report),expected);self.assertTrue(report['complete'],report['unresolved'])

    def test_missing_returned_leaf_still_reports_a_derived_gap(self):
        report,_=scan('b=make() n=b[2]',decl='b:ARRAY[2]OF INTEGER n:INTEGER',routines='''
            ROUTINE make:ARRAY OF INTEGER VAR a:ARRAY[2]OF INTEGER BEGIN a[1]=7 RETURN a END make''')
        self.assertEqual(report['inputs'],[])
        self.assertEqual({row['code'] for row in report['unresolved']},{'derived-value'})

    def test_prior_private_snapshot_survives_later_argument_mutation(self):
        report,_=scan('a[1]=7 use((a),touch())',decl='a:ARRAY[2]OF INTEGER n,x,y:INTEGER',routines='''
            ROUTINE touch:INTEGER BEGIN a[1]=99 RETURN 1 END touch
            ROUTINE use(p:ARRAY OF INTEGER;q:INTEGER) BEGIN IF p[1]=7 THEN n=x ELSE n=y ENDIF END use''')
        self.assertEqual(names(report),{('variable','A'):'required',('variable','X'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_noncopy_scalar_and_whole_value_consumers_keep_missing_local_gaps(self):
        for body in ('n=a[2]','WRITE(a)'):
            with self.subTest(body=body):
                report,_=scan('use()',decl='n:INTEGER',routines='ROUTINE use VAR a:ARRAY[2]OF INTEGER BEGIN a[1]=7 '+body+' END use')
                self.assertTrue(any(row['code']=='local-value' for row in report['unresolved']))

    def test_geometry_consumers_still_require_complete_local_data(self):
        report,_=scan('use()',decl='n:REAL',routines='ROUTINE use VAR v:VECTOR BEGIN v.x=1 n=v @ v END use')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='local-value' for row in report['unresolved']))

    def test_computed_partial_geometry_results_remain_explicit_for_consumers(self):
        report,_=scan('n=make() @ make()',decl='n:REAL',routines='ROUTINE make:VECTOR VAR v:VECTOR BEGIN v.x=1 RETURN v END make')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))

    def test_implicit_geometric_value_conversion_keeps_its_complete_input_precondition(self):
        report,_=scan('use(make())',decl='n:INTEGER',routines='''
            ROUTINE make:XYZWPR VAR p:XYZWPR BEGIN p.x=1 RETURN p END make
            ROUTINE use(p:POSITION) BEGIN n=7 END use''')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='conversion-value' for row in report['unresolved']))

    def test_implicit_geometric_array_conversion_keeps_its_complete_input_precondition(self):
        report,_=scan('use(make())',decl='n:INTEGER',routines='''
            ROUTINE make:ARRAY[1]OF XYZWPR VAR p:ARRAY[1]OF XYZWPR BEGIN p[1].x=1 RETURN p END make
            ROUTINE use(p:ARRAY OF POSITION) BEGIN n=7 END use''')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='conversion-value' for row in report['unresolved']))

    def test_config_word_packing_still_needs_complete_source_fields(self):
        report,_=scan('n=make()',decl='n:INTEGER',routines='ROUTINE make:CONFIG VAR v:CONFIG BEGIN RETURN v END make')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='conversion-value' for row in report['unresolved']))

    def test_function_calls_still_require_a_value_consumption_site(self):
        with self.assertRaises(TranslationError):
            scan('make()',decl='n:REAL',routines='ROUTINE make:VECTOR VAR v:VECTOR BEGIN v.x=1 RETURN v END make')


class ShortAvailabilityAndBoundsTests(unittest.TestCase):
    def test_authored_partial_copy_and_linked_result_examples(self):
        from tools.run_examples import run_example
        for name in ('discovery_partial_values','discovery_partial_arrays'):
            with self.subTest(name=name):
                path=ROOT/'examples'/(name+'.kl');run_example(path)
                report=discover_inputs(translate(path.read_text(encoding='utf-8')).python_source)
                self.assertTrue(report['complete'],report['unresolved'])
                summary=[{key:row[key] for key in ('kind','path','certainty')} for row in report['inputs']]
                self.assertEqual(summary,json.loads((path.parent/(name+'.inputs.expected.json')).read_bytes()))
        folder=ROOT/'examples/partial_discovery_values_linked';instance=load_project(folder).instantiate()
        expected=json.loads((folder/'expected.json').read_bytes())
        self.assertEqual(instance.run('MAIN'),expected);self.assertEqual(instance.run('MAIN'),expected)

    def test_unknown_real_and_integer_to_short_can_create_missing_state(self):
        for kind in ('REAL','INTEGER'):
            with self.subTest(kind=kind):
                report,_=scan('narrowed=source n=narrowed',decl=f'source:{kind} narrowed:SHORT n:INTEGER')
                self.assertEqual(names(report),{('variable','SOURCE'):'required'})
                self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))

    def test_unknown_but_initialized_byte_and_short_sources_are_safe(self):
        for kind in ('BYTE','SHORT'):
            with self.subTest(kind=kind):
                report,_=scan('narrowed=source n=narrowed',decl=f'source:{kind} narrowed:SHORT n:INTEGER')
                self.assertEqual(names(report),{('variable','SOURCE'):'required'});self.assertTrue(report['complete'],report['unresolved'])

    def test_known_safe_and_sentinel_numeric_array_leaves_are_independent(self):
        for value in ('7','7.9','32767','32767.9'):
            with self.subTest(value=value):
                report,_=scan('a[1]='+value+' b=a n=b[1]',decl='a:ARRAY[2]OF REAL b:ARRAY[2]OF SHORT n:INTEGER')
                self.assertEqual(names(report),{('variable','A'):'required'})
                self.assertEqual(report['complete'],not value.startswith('32767'),report['unresolved'])

    def test_known_safe_real_scalar_coercion_remains_available(self):
        report,_=scan('narrowed=7.9 n=narrowed',decl='narrowed:SHORT n:INTEGER')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])

    def test_structured_short_conversion_checks_each_copied_leaf(self):
        report,_=scan('a.good=7 a.bad=32767 b=a n=b.good',
            prefix='TYPE in_t=STRUCTURE good:INTEGER bad:INTEGER ENDSTRUCTURE out_t=STRUCTURE good:SHORT bad:SHORT ENDSTRUCTURE',
            decl='a:in_t b:out_t n:INTEGER')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])
        report,_=scan('a.good=7 a.bad=32767 b=a n=b.bad',
            prefix='TYPE in_t=STRUCTURE good:INTEGER bad:INTEGER ENDSTRUCTURE out_t=STRUCTURE good:SHORT bad:SHORT ENDSTRUCTURE',
            decl='a:in_t b:out_t n:INTEGER')
        self.assertEqual(report['inputs'],[]);self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))

    def test_facts_obey_existing_storage_and_step_budgets_without_target_execution(self):
        _,result=scan('b=a',decl='a,b:ARRAY[32]OF INTEGER')
        with mock.patch('karel2py.input_discovery.MAX_STEPS',20),mock.patch('builtins.exec',side_effect=AssertionError('executed')):
            report=discover_inputs(result.python_source)
        self.assertFalse(report['complete']);self.assertTrue(any(row['code']=='limit' for row in report['unresolved']))

    def test_discovery_copies_do_not_mutate_the_checked_contract(self):
        _,result=scan('a[1]=7 b=a n=b[1]',decl='a,b:ARRAY[2]OF INTEGER n:INTEGER')
        original=json.dumps(extract(result.python_source),sort_keys=True)
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')),mock.patch('builtins.eval',side_effect=AssertionError('evaluated')):
            report=discover_inputs(result.python_source)
        self.assertTrue(report['complete'],report['unresolved']);self.assertEqual(original,json.dumps(extract(result.python_source),sort_keys=True))

    def test_file_copy_guards_remain_closed(self):
        with self.assertRaises(TranslationError):scan('b=a',decl='a,b:ARRAY[2]OF FILE')


if __name__=='__main__':unittest.main()
