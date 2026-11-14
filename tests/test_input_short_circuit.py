"""Boolean optional effects and eager INTEGER operations in checked input plans."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from karel2py import translate,load_project,runtime as rt
from karel2py.input_contract import extract,attach
from karel2py.input_discovery import discover_inputs,InputDiscoveryError
from karel2py.input_template import prepare_inputs
from karel2py.lexer import TranslationError
from tests.test_input_discovery import scan,names


ROOT=Path(__file__).resolve().parents[1]
FILL='ROUTINE fill:BOOLEAN BEGIN x=7 RETURN TRUE END fill'


def without_evaluation(source):
    plan=copy.deepcopy(extract(source))
    def visit(node):
        if type(node) is dict:
            node.pop('evaluation',None)
            for value in node.values():visit(value)
        elif type(node) is list:
            for value in node:visit(value)
    visit(plan)
    lines=[]
    for line in source.splitlines():
        if line.startswith('    input_analysis = '):line='    input_analysis = None'
        elif line.startswith('    input_analysis_sha256 = '):line='    input_analysis_sha256 = None'
        lines.append(line)
    return attach('\n'.join(lines)+'\n',plan)


class BooleanDiscoveryTests(unittest.TestCase):
    def test_authored_examples_and_independent_discovery_expectations(self):
        from tools.run_examples import run_example
        for name in ('discovery_boolean_short_circuit','discovery_integer_eager'):
            with self.subTest(name=name):
                path=ROOT/'examples'/(name+'.kl');run_example(path)
                report=discover_inputs(translate(path.read_text(encoding='utf-8')).python_source)
                self.assertTrue(report['complete'],report['unresolved'])
                summary=[{key:row[key] for key in ('kind','path','certainty')} for row in report['inputs']]
                self.assertEqual(summary,json.loads((path.parent/(name+'.inputs.expected.json')).read_bytes()))
        folder=ROOT/'examples/boolean_short_circuit_linked';instance=load_project(folder).instantiate()
        self.assertEqual(instance.run('MAIN'),json.loads((folder/'expected.json').read_bytes()))

    def test_decisive_literals_skip_right_reads(self):
        for expression in ('FALSE AND flag','TRUE OR flag','OFF AND flag','ON OR flag'):
            with self.subTest(expression=expression):
                report,_=scan('answer='+expression,decl='answer,flag:BOOLEAN')
                self.assertTrue(report['complete'],report['unresolved']);self.assertEqual(report['inputs'],[])

    def test_nondecisive_literals_require_right_reads(self):
        for expression in ('TRUE AND flag','FALSE OR flag'):
            with self.subTest(expression=expression):
                report,_=scan('answer='+expression,decl='answer,flag:BOOLEAN')
                self.assertEqual(names(report),{('variable','FLAG'):'required'})

    def test_skipped_routine_cannot_hide_an_initial_read(self):
        for expression in ('FALSE AND fill()','TRUE OR fill()'):
            with self.subTest(expression=expression):
                report,_=scan('flag='+expression+' n=x',routines=FILL)
                self.assertTrue(report['complete'],report['unresolved'])
                self.assertEqual(names(report),{('variable','X'):'required'})

    def test_required_routine_effects_initialize_the_original(self):
        for expression in ('TRUE AND fill()','FALSE OR fill()'):
            with self.subTest(expression=expression):
                report,_=scan('flag='+expression+' n=x',routines=FILL)
                self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'])

    def test_unknown_left_preserves_a_conditional_initial_read(self):
        for operation in ('AND','OR'):
            with self.subTest(operation=operation):
                report,_=scan('answer=flag '+operation+' fill() n=x',decl='answer,flag:BOOLEAN n,x:INTEGER',routines=FILL)
                self.assertEqual(names(report),{('variable','FLAG'):'required',('variable','X'):'conditional'})
                self.assertTrue(report['complete'],report['unresolved'])

    def test_unknown_left_makes_callee_reads_conditional(self):
        report,_=scan('answer=flag AND needs()',decl='answer,flag:BOOLEAN n,x:INTEGER',
            routines='ROUTINE needs:BOOLEAN BEGIN n=x RETURN TRUE END needs')
        self.assertEqual(names(report),{('variable','FLAG'):'required',('variable','X'):'conditional'})
        self.assertEqual(report['inputs'][-1]['locations'][0]['routine'],'NEEDS')

    def test_conditional_alias_writes_do_not_become_definite(self):
        report,_=scan('answer=flag AND fill(x) n=x',decl='answer,flag:BOOLEAN n,x:INTEGER',
            routines='ROUTINE fill(p:INTEGER):BOOLEAN BEGIN p=7 RETURN TRUE END fill')
        self.assertEqual(names(report),{('variable','FLAG'):'required',('variable','X'):'conditional'})

    def test_left_operand_effects_are_retained_when_right_is_skipped(self):
        report,result=scan('flag=left() AND right() n=x',routines='''
            ROUTINE left:BOOLEAN BEGIN x=7 RETURN FALSE END left
            ROUTINE right:BOOLEAN BEGIN x=99 RETURN TRUE END right''')
        self.assertEqual(report['inputs'],[])
        namespace={'__name__':'authored'};exec(result.python_source,namespace)
        values=namespace['Program']().run();self.assertEqual((values['FLAG'],values['N'],values['X']),(False,7,7))

    def test_nested_operations_preserve_short_circuit_order(self):
        report,_=scan('flag=(FALSE AND fill()) OR (TRUE OR fill()) n=x',routines=FILL)
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'])

    def test_rhs_constants_can_determine_result_without_strengthening_writes(self):
        for expression,body,expected in (
                ('flag AND FALSE','IF answer THEN n=x ELSE n=y ENDIF','Y'),
                ('flag OR TRUE','IF answer THEN n=x ELSE n=y ENDIF','X')):
            with self.subTest(expression=expression):
                report,_=scan('answer='+expression+' '+body,decl='answer,flag:BOOLEAN n,x,y:INTEGER')
                self.assertEqual(names(report),{('variable','FLAG'):'required',('variable',expected):'required'})

    def test_decisive_rhs_result_does_not_make_its_side_effect_definite(self):
        report,_=scan('answer=flag AND fill() IF answer THEN n=x ELSE n=y ENDIF',
            decl='answer,flag:BOOLEAN n,x,y:INTEGER',routines=FILL.replace('RETURN TRUE','y=7 RETURN FALSE'))
        self.assertEqual(names(report),{('variable','FLAG'):'required',('variable','Y'):'conditional'})

    def test_optional_nonreturning_rhs_keeps_only_live_skip_path_facts(self):
        report,_=scan('answer=flag AND halt() n=x',decl='answer,flag:BOOLEAN n,x:INTEGER',
            routines='ROUTINE halt:BOOLEAN BEGIN x=7 ABORT RETURN TRUE END halt')
        self.assertEqual(names(report),{('variable','FLAG'):'required',('variable','X'):'required'})

    def test_required_nonreturning_rhs_stops_following_reads(self):
        report,_=scan('flag=TRUE AND halt() n=x',routines='ROUTINE halt:BOOLEAN BEGIN ABORT RETURN TRUE END halt')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])

    def test_loop_conditions_preserve_skip_effects(self):
        for body in ('WHILE FALSE AND fill() DO n=0 ENDWHILE n=x','REPEAT n=0 UNTIL TRUE OR fill() n=x'):
            with self.subTest(body=body):
                report,_=scan(body,routines=FILL)
                self.assertEqual(names(report),{('variable','X'):'required'})

    def test_dynamic_case_labels_remain_eager_but_their_boolean_rhs_can_skip(self):
        report,_=scan('SELECT TRUE OF CASE(FALSE AND fill()): n=0 ELSE: n=x ENDSELECT',routines=FILL)
        self.assertEqual(names(report),{('variable','X'):'required'});self.assertTrue(report['complete'])

    def test_skipped_ports_add_neither_inputs_nor_context_requirements(self):
        report,_=scan('flag=FALSE AND DIN[1]')
        self.assertEqual(report['inputs'],[]);self.assertEqual(report['context_requirements'],[])
        report,_=scan('flag=TRUE AND DIN[1]')
        self.assertEqual(names(report),{('port','DIN[1]'):'required'});self.assertTrue(report['context_requirements'])

    def test_skipped_external_routine_does_not_create_a_false_gap(self):
        report,_=scan('flag=FALSE AND external()',routines='ROUTINE external:BOOLEAN FROM LIB')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])
        report,_=scan('flag=TRUE AND external()',routines='ROUTINE external:BOOLEAN FROM LIB')
        self.assertTrue(any(row['code']=='routine' for row in report['unresolved']))

    def test_uninit_is_a_nonreading_unknown_boolean_probe(self):
        report,_=scan('flag=UNINIT(x) AND needs()',routines='ROUTINE needs:BOOLEAN BEGIN n=y RETURN TRUE END needs')
        self.assertEqual(names(report),{('variable','Y'):'conditional'});self.assertTrue(report['complete'])

    def test_runtime_and_template_agree_on_the_previously_hidden_input(self):
        _,result=scan('flag=FALSE AND fill() n=x',routines=FILL)
        prepared=prepare_inputs(result.python_source)
        self.assertEqual([(row['path'],row['status']) for row in prepared['template']['bindings']],[('X','missing')])
        namespace={'__name__':'authored'};exec(result.python_source,namespace)
        context=rt.ExecutionContext.from_config({'variables':[{'program':'T','path':'X','type':['INTEGER'],'value':11}]})
        self.assertEqual(namespace['Program'](context=context).run()['N'],11)

    def test_static_type_validation_still_checks_skipped_source(self):
        with self.assertRaises(TranslationError):scan('flag=FALSE AND 7')

    def test_skipped_pause_has_no_runtime_or_analysis_effect(self):
        report,result=scan('flag=TRUE OR paused()',routines='ROUTINE paused:BOOLEAN BEGIN PAUSE RETURN TRUE END paused')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'],report['unresolved'])
        namespace={'__name__':'authored'};exec(result.python_source,namespace)
        self.assertTrue(namespace['Program']().run()['FLAG'])

    def test_skipped_runtime_arithmetic_failure_is_not_evaluated(self):
        report,result=scan('flag=FALSE AND (1 DIV 0=0)')
        self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'])
        namespace={'__name__':'authored'};exec(result.python_source,namespace)
        self.assertFalse(namespace['Program']().run()['FLAG'])


class LogicalContractTests(unittest.TestCase):
    def test_integer_bitwise_rhs_remains_required_even_with_zero_left(self):
        for operation in ('AND','OR'):
            with self.subTest(operation=operation):
                report,result=scan('n=0 '+operation+' fill() n=x',routines='ROUTINE fill:INTEGER BEGIN x=7 RETURN 1 END fill')
                self.assertEqual(report['inputs'],[]);self.assertTrue(report['complete'])
                namespace={'__name__':'authored'};exec(result.python_source,namespace)
                self.assertEqual(namespace['Program']().run()['N'],7)

    def test_integer_rhs_inputs_are_required(self):
        report,_=scan('n=0 AND x')
        self.assertEqual(names(report),{('variable','X'):'required'})

    def test_contract_distinguishes_checked_emission_categories(self):
        _,result=scan('flag=(x AND y=0) AND (flag OR TRUE)')
        evaluations=[]
        def visit(node):
            if type(node) is dict:
                if node.get('kind')=='binary' and node.get('value') in ('AND','OR'):evaluations.append(node['evaluation'])
                for item in node.values():visit(item)
            elif type(node) is list:
                for item in node:visit(item)
        visit(extract(result.python_source))
        self.assertEqual(sorted(evaluations),['eager','short-circuit','short-circuit'])

    def test_older_contracts_with_proven_boolean_or_integer_left_are_supported(self):
        for body,routines,expected in (
                ('flag=FALSE AND fill() n=x',FILL,{('variable','X'):'required'}),
                ('n=0 AND fill() n=x',FILL.replace(':BOOLEAN',':INTEGER').replace('RETURN TRUE','RETURN 1'),{}),
                ('answer=flag AND fill() n=x',FILL,{('variable','FLAG'):'required',('variable','X'):'conditional'})):
            with self.subTest(body=body):
                decl='answer,flag:BOOLEAN n,x,y:INTEGER'
                _,result=scan(body,decl=decl,routines=routines)
                report=discover_inputs(without_evaluation(result.python_source))
                self.assertEqual(names(report),expected);self.assertTrue(report['complete'],report['unresolved'])

    def test_unproven_older_operator_mode_is_explicit_and_never_assumes_rhs_writes(self):
        _,result=scan('answer=(NOT flag) AND fill() n=x',decl='answer,flag:BOOLEAN n,x:INTEGER',routines=FILL)
        report=discover_inputs(without_evaluation(result.python_source))
        self.assertTrue(any(row['code']=='operator-mode' for row in report['unresolved']))
        self.assertEqual(names(report),{('variable','FLAG'):'required',('variable','X'):'conditional'})

    def test_evaluation_metadata_edits_are_rejected_by_the_payload_pin(self):
        _,result=scan('flag=FALSE AND fill()',routines=FILL)
        changed=result.python_source.replace("'evaluation': 'short-circuit'","'evaluation': 'eager'",1)
        self.assertNotEqual(changed,result.python_source)
        with self.assertRaises(InputDiscoveryError):discover_inputs(changed)

    def test_no_target_execution_or_mutation_during_discovery(self):
        _,result=scan('flag=FALSE AND fill() n=x',routines=FILL)
        original=json.dumps(extract(result.python_source),sort_keys=True)
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')),mock.patch('builtins.eval',side_effect=AssertionError('evaluated')):
            report=discover_inputs(result.python_source)
        self.assertEqual(names(report),{('variable','X'):'required'})
        self.assertEqual(original,json.dumps(extract(result.python_source),sort_keys=True))

    def test_include_origins_retain_conditional_callee_read_locations(self):
        result=translate('PROGRAM T VAR flag,answer:BOOLEAN n,x:INTEGER\n%INCLUDE calls.inc\nBEGIN answer=flag AND needs() END T',
            filename='main.kl',includes={'calls.inc':'ROUTINE needs:BOOLEAN\nBEGIN\nn=x\nRETURN TRUE\nEND needs'})
        report=discover_inputs(result.python_source);row=next(row for row in report['inputs'] if row['path']=='X')
        self.assertEqual(row['certainty'],'conditional')
        self.assertEqual((row['locations'][0]['file'],row['locations'][0]['line']),('calls.inc',3))


if __name__=='__main__':unittest.main()
