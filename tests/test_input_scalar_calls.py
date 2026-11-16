"""Checked scalar call facts without target execution or invented input values."""
import json
from pathlib import Path
import unittest
from unittest import mock

from karel2py import translate,load_project,runtime as rt
from karel2py.compiler import CONSTANT_BUILTINS
from karel2py.input_discovery import SCALAR_PURE,discover_inputs
from tests.test_input_discovery import scan,names


ROOT=Path(__file__).resolve().parents[1]


class ScalarCallFacts(unittest.TestCase):
    def test_whitelist_matches_existing_checked_compile_time_scalar_functions(self):
        self.assertEqual(set(SCALAR_PURE),set(CONSTANT_BUILTINS))
        self.assertEqual(len(SCALAR_PURE),17)

    def test_math_results_select_only_the_reachable_input(self):
        cases=[('ABS(-7)=7'),('ABS(-7.25)=7.25'),('ROUND(2.5)=2'),('ROUND(3.5)=4'),
            ('TRUNC(-7.9)=-7'),('SQRT(9)=3'),('EXP(0)=1'),('LN(1)=0'),
            ('SIN(90)=1'),('COS(0)=1'),('TAN(0)=0'),('ASIN(1)=90'),('ACOS(1)=0'),
            ('ATAN2(0,1)=90'),('ATAN2(1,0)=0'),('ROUND(SIN(30)*100)=50')]
        for condition in cases:
            with self.subTest(condition=condition):
                report,_=scan('IF '+condition+' THEN n=x ELSE n=y ENDIF')
                self.assertEqual(names(report),{('variable','X'):'required'})
                self.assertTrue(report['complete'],report['unresolved'])

    def test_text_results_include_ascii_one_based_and_clipped_cases(self):
        cases=["STR_LEN('a''b')=3","STR_LEN('')=0","SUB_STR('abc',2,99)='bc'",
            "SUB_STR('abc',4,9)=''","SUB_STR('abc',2,0)=''","INDEX('abc','b')=2",
            "INDEX('abc','')=1","INDEX('abc','z')=0","CHR(65)='A'","ORD('AZ',2)=90",
            "ORD(CHR(0),1)=0","STR_LEN(SUB_STR('abcd',2,2))=2"]
        for condition in cases:
            with self.subTest(condition=condition):
                report,_=scan('IF '+condition+' THEN n=x ELSE n=y ENDIF')
                self.assertEqual(names(report),{('variable','X'):'required'})
                self.assertTrue(report['complete'],report['unresolved'])

    def test_str_len_is_not_an_unknown_service_and_preserves_prior_writes(self):
        report,_=scan('x=7 n=STR_LEN(text) n=x',decl='x,n:INTEGER text:STRING[8]')
        self.assertEqual(names(report),{('variable','TEXT'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_unknown_scalar_reads_remain_inputs_without_invented_values(self):
        report,_=scan('n=ROUND(source) IF n=1 THEN n=x ELSE n=y ENDIF',decl='n,x,y:INTEGER source:REAL')
        self.assertEqual(names(report),{('variable','SOURCE'):'required',('variable','X'):'conditional',('variable','Y'):'conditional'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_nested_math_calls_resolve_an_array_address(self):
        report,_=scan('n=a[ROUND(SQRT(4))]',decl='n:INTEGER a:ARRAY[3]OF INTEGER')
        self.assertEqual(names(report),{('variable','A[2]'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_scalar_bounds_expand_existing_for_analysis(self):
        report,_=scan("FOR i=TRUNC(1.9) TO STR_LEN('abc') DO n=a[i] ENDFOR",decl='i,n:INTEGER a:ARRAY[3]OF INTEGER')
        self.assertEqual(names(report),{('variable','A[1]'):'required',('variable','A[2]'):'required',('variable','A[3]'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_text_calls_resolve_a_register_address(self):
        report,_=scan("GET_STR_REG(STR_LEN('ab'),text,s)",decl='text:STRING[8] s:INTEGER')
        self.assertEqual(names(report),{('string_register','2'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_scalar_calls_resolve_an_own_program_variable_path(self):
        report,_=scan("entry=0 GET_VAR(entry,'T',SUB_STR('Xignored',1,1),n,s)",decl='entry,x,n,s:INTEGER')
        self.assertEqual(names(report),{('variable','X'):'required'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_typed_results_preserve_real_narrowing_and_short_sentinel_rules(self):
        for expression,complete in (('SQRT(49)',True),('TRUNC(32767.9)',False),('ROUND(32766.5)',True)):
            with self.subTest(expression=expression):
                report,_=scan('small='+expression+' n=small',decl='small:SHORT n:INTEGER')
                self.assertEqual(report['inputs'],[]);self.assertEqual(report['complete'],complete,report['unresolved'])

    def test_integer_values_stored_in_real_keep_the_runtime_numeric_category(self):
        for expression in ('ABS(r)','ABS(r+0)','ABS(make())'):
            with self.subTest(expression=expression):
                report,result=scan('r=MININT IF '+expression+'=2147483648.0 THEN n=x ELSE n=y ENDIF',
                    decl='r:REAL n,x,y:INTEGER',routines='ROUTINE make:REAL BEGIN RETURN MININT END make')
                self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'],report['unresolved'])
                namespace={'__name__':'authored'};exec(result.python_source,namespace)
                context=rt.ExecutionContext.from_config({'variables':[{'program':'T','path':'X','type':['INTEGER'],'value':11}]})
                self.assertEqual(namespace['Program'](context=context).run()['N'],11)

    def test_clipped_stored_string_does_not_retain_an_uncast_value(self):
        report,_=scan("text=SUB_STR('abcd',1,4) IF STR_LEN(text)=3 THEN n=x ELSE n=y ENDIF",decl='text:STRING[3] n,x,y:INTEGER')
        self.assertEqual(names(report),{('variable','X'):'conditional',('variable','Y'):'conditional'})
        self.assertTrue(report['complete'],report['unresolved'])

    def test_direct_local_constants_flow_through_calls(self):
        report,_=scan('use()',decl='n,x,y:INTEGER',routines="ROUTINE use CONST word='abc' BEGIN IF STR_LEN(word)=3 THEN n=x ELSE n=y ENDIF END use")
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'])

    def test_private_routine_arguments_and_results_keep_scalar_facts(self):
        report,_=scan("IF size(('abc'))=3 THEN n=x ELSE n=y ENDIF",decl='n,x,y:INTEGER',
            routines='ROUTINE size(text:STRING):INTEGER BEGIN RETURN STR_LEN(text) END size')
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'],report['unresolved'])


class ScalarCallEffectsAndFailures(unittest.TestCase):
    def test_arguments_are_captured_once_before_later_effects(self):
        report,result=scan("text='abc' calls=0 found=INDEX(text,change()) IF found=2 THEN n=x ELSE n=y ENDIF",decl='text:STRING[8] calls,found,n,x,y:INTEGER',
            routines="ROUTINE change:STRING BEGIN calls=calls+1 text='XYZ' RETURN 'b' END change")
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'],report['unresolved'])
        namespace={'__name__':'authored'};exec(result.python_source,namespace)
        context=rt.ExecutionContext.from_config({'variables':[{'program':'T','path':'X','type':['INTEGER'],'value':11}]})
        values=namespace['Program'](context=context).run()
        self.assertEqual((values['TEXT'],values['CALLS'],values['FOUND'],values['N']),('XYZ',1,2,11))

    def test_later_arguments_observe_earlier_routine_writes(self):
        report,_=scan("found=INDEX(first(),second()) IF (found=2) AND (calls=2) THEN n=x ELSE n=y ENDIF",decl='calls,found,n,x,y:INTEGER',routines="""
            ROUTINE first:STRING BEGIN calls=1 RETURN 'abc' END first
            ROUTINE second:STRING BEGIN calls=calls+1 RETURN 'b' END second""")
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'])

    def test_reference_effects_inside_scalar_calls_are_retained(self):
        report,_=scan('n=ABS(change(x)) n=x',decl='n,x:INTEGER',routines='ROUTINE change(p:INTEGER):INTEGER BEGIN p=7 RETURN -3 END change')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])

    def test_a_nonreturning_argument_skips_later_arguments_and_continuation(self):
        report,_=scan('n=INDEX(first(),text) n=x',decl='n,x:INTEGER text:STRING[8]',
            routines="ROUTINE first:STRING BEGIN ABORT RETURN '' END first")
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])

    def test_short_circuit_skips_scalar_calls_and_their_arguments(self):
        _,result=scan("IF FALSE AND (STR_LEN(text)=3) THEN n=x ENDIF n=7",decl='text:STRING[8] n,x:INTEGER')
        with mock.patch.object(rt,'builtin',side_effect=AssertionError('skipped scalar call')):
            report=discover_inputs(result.python_source)
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'])

    def test_known_domain_failures_are_explicit_and_do_not_seed_written_values(self):
        cases=['SQRT(-1)','LN(0)','EXP(1000)','TAN(90)','ASIN(2)','ACOS(2)','ATAN2(0,0)',
            'ABS(MININT)','ROUND(MAXINT)','TRUNC(MAXINT)']
        for expression in cases:
            with self.subTest(expression=expression):
                report,_=scan('r='+expression+' r=r',decl='r:REAL')
                self.assertEqual(report['inputs'],[])
                self.assertTrue(any(row['code']=='scalar-call' for row in report['unresolved']))
                self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))

    def test_invalid_text_domains_are_explicit(self):
        for expression,target,decl in (("CHR(128)",'text','text:STRING[8]'),("ORD('A',2)",'n','n:INTEGER'),
                ("SUB_STR('a',0,1)",'text','text:STRING[8]')):
            with self.subTest(expression=expression):
                report,_=scan(target+'='+expression,decl=decl)
                self.assertTrue(any(row['code']=='scalar-call' for row in report['unresolved']))

    def test_missing_local_scalar_is_not_evaluated_or_invented_as_an_input(self):
        _,result=scan('use()',decl='n:INTEGER',routines='ROUTINE use VAR text:STRING[8] BEGIN n=STR_LEN(text) END use')
        with mock.patch.object(rt,'builtin',side_effect=AssertionError('unproven local value')):
            report=discover_inputs(result.python_source)
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='local-value' for row in report['unresolved']))

    def test_short_missing_marker_does_not_turn_into_an_ordinary_known_scalar(self):
        _,result=scan('small=32767 n=ABS(small)',decl='small:SHORT n:INTEGER')
        with mock.patch.object(rt,'builtin',side_effect=AssertionError('missing SHORT')):
            report=discover_inputs(result.python_source)
        self.assertFalse(report['complete']);self.assertEqual(report['inputs'],[])

    def test_unknown_external_effects_remain_explicit(self):
        report,_=scan('n=ABS(remote()) n=x',decl='n,x:INTEGER',routines='ROUTINE remote:INTEGER FROM LIB')
        self.assertFalse(report['complete']);self.assertTrue(any(row['code']=='routine' for row in report['unresolved']))
        self.assertIn(('variable','X'),names(report))


class ScalarCallDiscoveryBoundary(unittest.TestCase):
    def test_authored_scalar_examples_and_linked_execution(self):
        from tools.run_examples import run_example
        for name in ('discovery_scalar_calls','discovery_scalar_addresses'):
            with self.subTest(name=name):
                path=ROOT/'examples'/(name+'.kl');run_example(path)
                report=discover_inputs(translate(path.read_text(encoding='utf-8')).python_source)
                self.assertTrue(report['complete'],report['unresolved'])
                summary=[{key:row[key] for key in ('kind','path','certainty')} for row in report['inputs']]
                self.assertEqual(summary,json.loads((path.parent/(name+'.inputs.expected.json')).read_bytes()))
        folder=ROOT/'examples/scalar_discovery_calls_linked';instance=load_project(folder).instantiate()
        expected=json.loads((folder/'expected.json').read_bytes())
        self.assertEqual(instance.run('MAIN'),expected);self.assertEqual(instance.run('MAIN'),expected)

    def test_analysis_uses_pythonic_math_and_restores_the_callers_mode(self):
        _,result=scan('IF ROUND(2.5)=2 THEN n=x ELSE n=y ENDIF')
        with rt._numeric_scope('strict'):
            report=discover_inputs(result.python_source)
            self.assertFalse(rt._pythonic())
        self.assertEqual(names(report),{('variable','X'):'required'})

    def test_failure_also_restores_the_callers_mode(self):
        _,result=scan('n=ROUND(MAXINT)')
        with rt._numeric_scope('strict'):
            report=discover_inputs(result.python_source)
            self.assertFalse(rt._pythonic())
        self.assertFalse(report['complete'])

    def test_discovery_does_not_execute_target_or_construct_execution_context(self):
        _,result=scan("n=STR_LEN(SUB_STR('abcd',2,2)) IF n=2 THEN n=x ELSE n=y ENDIF")
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')),mock.patch('builtins.eval',side_effect=AssertionError('evaluated')),\
                mock.patch.object(rt,'ExecutionContext',side_effect=AssertionError('execution context')):
            report=discover_inputs(result.python_source)
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'])

    def test_scalar_calls_obey_the_existing_step_budget(self):
        _,result=scan("n=STR_LEN(SUB_STR('abcd',1,2))")
        with mock.patch('karel2py.input_discovery.MAX_STEPS',3):report=discover_inputs(result.python_source)
        self.assertTrue(any(row['code']=='limit' for row in report['unresolved']))

    def test_include_locations_retain_the_actual_selected_read(self):
        result=translate("PROGRAM T VAR n,x,y:INTEGER BEGIN\n%INCLUDE choice.inc\nEND T",filename='main.kl',
            includes={'choice.inc':"IF STR_LEN('abc')=3 THEN\nn=x\nELSE n=y ENDIF"})
        report=discover_inputs(result.python_source);row=report['inputs'][0]
        self.assertEqual((row['path'],row['locations'][0]['file'],row['locations'][0]['line']),('X','choice.inc',2))


if __name__=='__main__':unittest.main()
