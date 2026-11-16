"""Discovery follows the emitted post-final-bound captured FOR start."""
import json
from pathlib import Path
import unittest
from unittest import mock

from karel2py import translate,load_project,runtime as rt
from karel2py.input_discovery import discover_inputs
from karel2py.lexer import TranslationError
from tests.test_input_discovery import scan,names
from tests.legacy_numeric_support import translate as legacy_translate


ROOT=Path(__file__).resolve().parents[1]
BOUND='ROUTINE bound:INTEGER BEGIN i=0 RETURN 1 END bound'


class ForStartCaptureTests(unittest.TestCase):
    def test_lowered_start_reveals_the_previously_hidden_input(self):
        report,_=scan('FOR i=1 TO bound() DO IF i=0 THEN n=x ELSE n=0 ENDIF ENDFOR',decl='i,n,x:INTEGER',routines=BOUND)
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'],report['unresolved'])

    def test_higher_start_does_not_read_skipped_array_cells(self):
        report,_=scan('FOR i=1 TO bound() DO n=a[i] ENDFOR',decl='i,n:INTEGER a:ARRAY[3]OF INTEGER',
            routines=BOUND.replace('i=0 RETURN 1','i=2 RETURN 3'))
        self.assertEqual(names(report),{('variable','A[2]'):'required',('variable','A[3]'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_downward_range_uses_the_post_bound_counter(self):
        report,_=scan('FOR i=5 DOWNTO bound() DO n=a[i] ENDFOR',decl='i,n:INTEGER a:ARRAY[5]OF INTEGER',
            routines=BOUND.replace('i=0 RETURN 1','i=3 RETURN 2'))
        self.assertEqual(names(report),{('variable','A[3]'):'required',('variable','A[2]'):'required'})

    def test_post_bound_start_can_make_either_direction_empty(self):
        for header,routine in (('1 TO',BOUND.replace('i=0 RETURN 1','i=4 RETURN 3')),
                ('5 DOWNTO',BOUND.replace('i=0 RETURN 1','i=1 RETURN 2'))):
            with self.subTest(header=header):
                report,_=scan('FOR i='+header+' bound() DO n=x ENDFOR',decl='i,n,x:INTEGER',routines=routine)
                self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'])

    def test_final_expression_observes_the_initialized_counter(self):
        report,_=scan('FOR i=1 TO bound() DO n=a[i] ENDFOR',decl='i,n:INTEGER a:ARRAY[2]OF INTEGER',
            routines='ROUTINE bound:INTEGER BEGIN RETURN i+1 END bound')
        self.assertEqual(names(report),{('variable','A[1]'):'required',('variable','A[2]'):'required'})

    def test_reference_argument_updates_counter_but_grouped_value_does_not(self):
        routine='ROUTINE bound(p:INTEGER):INTEGER BEGIN p=0 RETURN 1 END bound'
        for argument,expected in (('i',{('variable','X'):'required'}),('(i)',{})):
            with self.subTest(argument=argument):
                report,_=scan(f'FOR i=1 TO bound({argument}) DO IF i=0 THEN n=x ELSE n=0 ENDIF ENDFOR',
                    decl='i,n,x:INTEGER',routines=routine)
                self.assertEqual(names(report),expected);self.assertTrue(report['complete'],report['unresolved'])

    def test_fresh_caller_local_counter_can_be_updated_by_a_bound_reference(self):
        report,_=scan('use()',decl='n,x:INTEGER',routines='''
            ROUTINE bound(p:INTEGER):INTEGER BEGIN p=0 RETURN 1 END bound
            ROUTINE use VAR i:INTEGER BEGIN FOR i=1 TO bound(i) DO IF i=0 THEN n=x ELSE n=0 ENDIF ENDFOR END use''')
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'])

    def test_narrow_counters_follow_exact_typed_reference_effects(self):
        for kind in ('BYTE','SHORT'):
            with self.subTest(kind=kind):
                report,_=scan('FOR i=1 TO bound(i) DO IF i=0 THEN n=x ELSE n=0 ENDIF ENDFOR',decl=f'i:{kind} n,x:INTEGER',
                    routines=f'ROUTINE bound(p:{kind}):INTEGER BEGIN p=0 RETURN 1 END bound')
                self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'],report['unresolved'])

    def test_narrow_to_integer_value_conversion_does_not_mutate_the_counter(self):
        report,_=scan('FOR i=1 TO bound(i) DO IF i=0 THEN n=x ELSE n=0 ENDIF ENDFOR',decl='i:BYTE n,x:INTEGER',
            routines='ROUTINE bound(p:INTEGER):INTEGER BEGIN p=0 RETURN 1 END bound')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'])

    def test_unknown_post_bound_start_keeps_body_inputs_conditional(self):
        report,_=scan('FOR i=1 TO bound() DO IF i=0 THEN n=payload ELSE n=0 ENDIF ENDFOR',decl='i,n,x,payload:INTEGER',
            routines='ROUTINE bound:INTEGER BEGIN i=x RETURN 1 END bound')
        self.assertEqual(names(report),{('variable','X'):'required',('variable','PAYLOAD'):'conditional'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_bound_is_evaluated_once_and_its_effect_survives_loop_cleanup(self):
        report,result=scan('calls=0 visits=0 total=0 FOR i=1 TO bound() DO visits=visits+1 total=total+i ENDFOR IF calls=1 THEN n=x ELSE n=y ENDIF',
            decl='i,n,x,y,calls,visits,total:INTEGER',routines='ROUTINE bound:INTEGER BEGIN calls=calls+1 i=0 RETURN 2 END bound')
        self.assertEqual(names(report),{('variable','X'):'required'})
        namespace={'__name__':'authored'};exec(result.python_source,namespace)
        context=rt.ExecutionContext.from_config({'variables':[{'program':'T','path':'X','type':['INTEGER'],'value':11}]})
        values=namespace['Program'](context=context).run()
        self.assertEqual((values['CALLS'],values['VISITS'],values['TOTAL']),(1,3,3))

    def test_early_return_captures_the_post_bound_counter_before_cleanup(self):
        report,_=scan('n=first() IF n=0 THEN n=x ELSE n=y ENDIF',decl='n,x,y:INTEGER',routines='''
            ROUTINE bound(p:INTEGER):INTEGER BEGIN p=0 RETURN 1 END bound
            ROUTINE first:INTEGER VAR i:INTEGER BEGIN FOR i=1 TO bound(i) DO RETURN i ENDFOR RETURN 9 END first''')
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'],report['unresolved'])

    def test_nested_loop_bound_changes_do_not_change_an_independent_outer_counter(self):
        report,_=scan('FOR i=1 TO 2 DO FOR j=1 TO bound() DO IF j=0 THEN n=x ELSE n=0 ENDIF ENDFOR ENDFOR',
            decl='i,j,n,x:INTEGER',routines=BOUND.replace('i=0','j=0'))
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'],report['unresolved'])


class CapturedCounterStorageTests(unittest.TestCase):
    def test_selector_changes_in_final_bound_do_not_retarget_the_counter(self):
        report,result=scan('slot=1 a[2]=99 FOR a[slot]=1 TO bound() DO IF a[1]=0 THEN n=x ELSE n=0 ENDIF ENDFOR',
            decl='a:ARRAY[2]OF INTEGER slot,n,x:INTEGER',routines='ROUTINE bound:INTEGER BEGIN slot=2 a[1]=0 RETURN 1 END bound')
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'],report['unresolved'])
        namespace={'__name__':'authored'};exec(result.python_source,namespace)
        context=rt.ExecutionContext.from_config({'variables':[{'program':'T','path':'X','type':['INTEGER'],'value':11}]})
        values=namespace['Program'](context=context).run()
        self.assertEqual((values['A'],values['SLOT']),([{'uninitialized':True},99],2))

    def test_reference_capture_precedes_initializer_selector_effects(self):
        report,_=scan('slot=1 a[2]=99 FOR a[slot]=seed() TO bound() DO IF a[1]=0 THEN n=x ELSE n=0 ENDIF ENDFOR',
            decl='a:ARRAY[2]OF INTEGER slot,n,x:INTEGER',routines='''
            ROUTINE seed:INTEGER BEGIN slot=2 RETURN 1 END seed
            ROUTINE bound:INTEGER BEGIN a[1]=0 RETURN 1 END bound''')
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'])

    def test_whole_record_copy_updates_the_existing_captured_leaf(self):
        report,_=scan('donor.value=0 donor.guard=11 FOR item.value=1 TO bound() DO IF item.value=0 THEN n=x ELSE n=0 ENDIF ENDFOR',
            prefix='TYPE item_t=STRUCTURE value:INTEGER guard:INTEGER ENDSTRUCTURE',decl='item,donor:item_t n,x:INTEGER',
            routines='ROUTINE bound:INTEGER BEGIN item=donor RETURN 1 END bound')
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'],report['unresolved'])

    def test_short_missing_sentinel_in_final_bound_is_an_explicit_start_gap(self):
        report,result=scan('FOR i=1 TO bound() DO n=7 ENDFOR',decl='i:SHORT n,calls:INTEGER',
            routines='ROUTINE bound:INTEGER BEGIN calls=1 i=32767 RETURN 1 END bound')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='for-start' for row in report['unresolved']))
        namespace={'__name__':'authored'};exec(result.python_source,namespace);program=namespace['Program']()
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual(program.snapshot(),{'I':{'uninitialized':True},'N':{'uninitialized':True},'CALLS':1})

    def test_nonreturning_final_bound_does_not_require_unreachable_start_or_body(self):
        report,_=scan('FOR i=1 TO bound() DO n=x ENDFOR n=y',decl='i:SHORT n,x,y:INTEGER',
            routines='ROUTINE bound:INTEGER BEGIN i=32767 ABORT RETURN 1 END bound')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])

    def test_unproven_external_bound_effects_do_not_reuse_the_initial_constant(self):
        report,_=scan('FOR i=1 TO bound(i) DO n=x ENDFOR',decl='i,n,x:INTEGER',routines='ROUTINE bound(p:INTEGER):INTEGER FROM LIB')
        self.assertFalse(report['complete'])
        self.assertTrue(any(row['code']=='for-start' for row in report['unresolved']))
        self.assertEqual(names(report)[('variable','X')],'conditional')

    def test_pausing_bound_retains_runtime_reference_and_remains_explicit_in_analysis(self):
        report,result=scan('total=0 FOR i=1 TO bound() DO total=total+x ENDFOR',decl='i,total,x:INTEGER',
            routines='ROUTINE bound:INTEGER BEGIN PAUSE i=0 RETURN 1 END bound')
        self.assertFalse(report['complete']);self.assertTrue(any(row['code']=='statement' for row in report['unresolved']))
        namespace={'__name__':'authored'};exec(result.python_source,namespace)
        context=rt.ExecutionContext.from_config({'variables':[{'program':'T','path':'X','type':['INTEGER'],'value':11}]})
        program=namespace['Program'](context=context)
        with self.assertRaises(rt.KarelPause):program.run()
        self.assertEqual(program.snapshot()['I'],1);self.assertEqual(program.resume()['TOTAL'],22)


class ForDiscoveryContractTests(unittest.TestCase):
    def test_authored_discovery_examples_and_linked_execution(self):
        from tools.run_examples import run_example
        for name in ('discovery_for_start','discovery_for_empty'):
            with self.subTest(name=name):
                path=ROOT/'examples'/(name+'.kl');run_example(path)
                report=discover_inputs(translate(path.read_text(encoding='utf-8')).python_source)
                self.assertTrue(report['complete'],report['unresolved'])
                summary=[{key:row[key] for key in ('kind','path','certainty')} for row in report['inputs']]
                self.assertEqual(summary,json.loads((path.parent/(name+'.inputs.expected.json')).read_bytes()))
        folder=ROOT/'examples/for_start_capture_linked';instance=load_project(folder).instantiate()
        expected=json.loads((folder/'expected.json').read_bytes())
        self.assertEqual(instance.run('MAIN'),expected);self.assertEqual(instance.run('MAIN'),expected)

    def test_include_locations_refer_to_the_actual_body_read(self):
        result=translate('PROGRAM T VAR i,n,x:INTEGER\n'+BOUND+'\nBEGIN\n%INCLUDE loop.inc\nEND T',filename='main.kl',
            includes={'loop.inc':'FOR i=1 TO bound() DO\nIF i=0 THEN n=x ELSE n=0 ENDIF\nENDFOR'})
        report=discover_inputs(result.python_source);row=report['inputs'][0]
        self.assertEqual((row['path'],row['locations'][0]['file'],row['locations'][0]['line']),('X','loop.inc',2))

    def test_discovery_does_not_execute_or_evaluate_the_target(self):
        _,result=scan('FOR i=1 TO bound() DO IF i=0 THEN n=x ELSE n=0 ENDIF ENDFOR',decl='i,n,x:INTEGER',routines=BOUND)
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')),mock.patch('builtins.eval',side_effect=AssertionError('evaluated')):
            report=discover_inputs(result.python_source)
        self.assertEqual(names(report),{('variable','X'):'required'})

    def test_legacy_bound_call_rejection_is_unchanged(self):
        with self.assertRaises(TranslationError) as caught:
            legacy_translate('PROGRAM T VAR i,n:INTEGER '+BOUND+' BEGIN FOR i=1 TO bound() DO n=7 ENDFOR END T')
        self.assertEqual(caught.exception.code,'E_EVALUATION_ORDER')


if __name__=='__main__':unittest.main()
