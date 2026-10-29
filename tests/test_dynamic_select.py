"""Eager typed CASE expressions, captured selectors and source effect guards."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


DECL='n,key,label,result,total,i:INTEGER text,trace:STRING[32] flag:BOOLEAN real_value:REAL'


def build(body,*,routines='',decl=DECL,prefix='',labelled=False,cooperative=False,**options):
    return compile_program(('entry:: ' if labelled else '')+body,decl=decl,routines=routines,
                           prefix=prefix,cooperative=cooperative,**options)


class DynamicSelectTests(unittest.TestCase):
    def parity(self,body,**options):
        states=[]
        for labelled in (False,True):
            for cooperative in (False,True):
                p,_=build(body,labelled=labelled,cooperative=cooperative,**options);states.append(p.run())
        self.assertTrue(all(value==states[0] for value in states));return states[0]

    def test_dynamic_integer_label(self):
        self.assertEqual(self.parity('key=7 label=7 SELECT key OF CASE(label): result=42 ENDSELECT')['RESULT'],42)

    def test_dynamic_boolean_and_string_labels(self):
        state=self.parity("flag=TRUE text='go' SELECT TRUE OF CASE(flag): result=7 ENDSELECT SELECT 'go' OF CASE(text): total=42 ENDSELECT")
        self.assertEqual((state['RESULT'],state['TOTAL']),(7,42))

    def test_mixed_numeric_case_expressions_keep_normal_equality(self):
        state=self.parity('key=2 real_value=2.0 SELECT key OF CASE(real_value): result=42 CASE(key): result=99 ENDSELECT')
        self.assertEqual(state['RESULT'],42)

    def test_all_case_lists_evaluate_once_after_selector_in_source_order(self):
        routines='''ROUTINE selector:INTEGER BEGIN trace=trace+'S' RETURN 2 END selector
ROUTINE choice(value:INTEGER):INTEGER BEGIN trace=trace+CHR(value+64) n=n+1 RETURN value END choice'''
        state=self.parity("n=0 trace='' SELECT selector() OF CASE(choice(1),choice(2)): result=42 CASE(choice(3)): result=99 ENDSELECT",routines=routines)
        self.assertEqual((state['RESULT'],state['N'],state['TRACE']),(42,3,'SABC'))

    def test_selector_is_captured_before_case_function_mutates_it(self):
        state=self.parity('key=7 SELECT key OF CASE(change()): result=42 ELSE: result=99 ENDSELECT',
                          routines='ROUTINE change:INTEGER BEGIN key=8 RETURN 7 END change')
        self.assertEqual((state['KEY'],state['RESULT']),(8,42))

    def test_later_failure_cannot_hide_behind_earlier_match(self):
        p,_=build('result=7 SELECT 1 OF CASE(1): result=42 CASE(fail()): result=99 ENDSELECT',
                  routines='ROUTINE fail:INTEGER BEGIN n=9 RETURN 1 DIV 0 END fail')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['RESULT'],p.snapshot()['N']),(7,9));self.assertEqual(p._state.local_frames,[])

    def test_unknown_selector_prevents_all_case_effects(self):
        p,_=build('n=0 SELECT key OF CASE(choice()): result=42 ENDSELECT',
                  routines='ROUTINE choice:INTEGER BEGIN n=99 RETURN 7 END choice')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_nonfinite_selector_prevents_dynamic_case_effects(self):
        p,_=build('n=0 SELECT real_value OF CASE(choice()): result=42 ENDSELECT',
                  routines='ROUTINE choice:REAL BEGIN n=99 RETURN 1.0 END choice')
        p._state.values['REAL_VALUE']=float('nan')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_dynamic_array_elements_and_using_fields(self):
        state=self.parity('values[1]=7 packet.code=7 USING packet DO SELECT code OF CASE(values[1]): result=42 ENDSELECT ENDUSING',
            prefix='TYPE packet_t=STRUCTURE code:INTEGER ENDSTRUCTURE',decl=DECL+' values:ARRAY[1] OF INTEGER packet:packet_t')
        self.assertEqual(state['RESULT'],42)

    def test_bare_zero_argument_function_case_and_short_circuit(self):
        state=self.parity('n=0 SELECT TRUE OF CASE(FALSE AND side()): result=99 CASE(side): result=42 ENDSELECT',
            routines='ROUTINE side:BOOLEAN BEGIN n=n+1 RETURN TRUE END side')
        self.assertEqual((state['N'],state['RESULT']),(1,42))

    def test_uninitialized_case_prevents_body_and_later_label_effects(self):
        p,_=build('result=7 n=0 SELECT 1 OF CASE(key): result=42 CASE(later()): ENDSELECT',
                  routines='ROUTINE later:INTEGER BEGIN n=99 RETURN 1 END later')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['RESULT'],p.snapshot()['N']),(7,0))

    def test_pause_in_case_function_retains_selector_and_earlier_labels(self):
        routines='''ROUTINE first:INTEGER BEGIN n=n+1 RETURN 1 END first
ROUTINE second:INTEGER BEGIN n=n+1 PAUSE RETURN 2 END second'''
        p,_=build('n=0 key=2 SELECT key OF CASE(first()): result=1 CASE(second()): result=42 ENDSELECT',routines=routines)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],2);p._state.values['KEY']=99
        self.assertEqual((p.resume()['RESULT'],p.snapshot()['N']),(42,2))

    def test_pause_in_body_does_not_reevaluate_labels(self):
        p,_=build('n=0 SELECT 1 OF CASE(choice()): PAUSE result=n ENDSELECT',
                  routines='ROUTINE choice:INTEGER BEGIN n=n+1 RETURN 1 END choice')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['RESULT'],1)

    def test_stop_during_case_unwinds_without_running_body(self):
        p,_=build('result=7 SELECT 1 OF CASE(choice()): result=42 ENDSELECT',
                  routines='ROUTINE choice:INTEGER BEGIN PAUSE RETURN 1 END choice')
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['RESULT'],7);self.assertEqual(p._state.local_frames,[])

    def test_abort_in_late_case_is_sticky_and_prevents_body(self):
        p,_=build('result=7 SELECT 1 OF CASE(1): result=42 CASE(choice()): ENDSELECT',
                  routines='ROUTINE choice:INTEGER BEGIN ABORT RETURN 1 END choice')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot()['RESULT'],7)
        with self.assertRaises(rt.KarelAbort):p.run()

    def test_counter_writes_in_dynamic_labels_remain_rejected(self):
        for routine in ('ROUTINE choice:INTEGER BEGIN i=9 RETURN 1 END choice',
                        'ROUTINE change BEGIN i=9 END change ROUTINE choice:INTEGER BEGIN change() RETURN 1 END choice'):
            with self.subTest(routine=routine),self.assertRaises(TranslationError) as error:
                build('FOR i=1 TO 2 DO SELECT 1 OF CASE(choice()): ENDSELECT ENDFOR',routines=routine)
            self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_fresh_routine_local_counter_can_be_read_by_case_expression(self):
        state=self.parity('result=work()',routines='ROUTINE work:INTEGER VAR j,k:INTEGER BEGIN k=0 FOR j=1 TO 2 DO SELECT j OF CASE(j): k=k+j ENDSELECT ENDFOR RETURN k END work')
        self.assertEqual(state['RESULT'],3)

    def test_dynamic_category_mismatch_is_rejected_even_after_match(self):
        for body in ('SELECT 1 OF CASE(1): CASE(flag): ENDSELECT',"SELECT text OF CASE('go'): CASE(key): ENDSELECT",
                     'SELECT TRUE OF CASE(TRUE): CASE(real_value): ENDSELECT'):
            with self.subTest(body=body),self.assertRaises(TranslationError) as error:build(body)
            self.assertEqual(error.exception.code,'E_CASE')

    def test_aggregate_and_resource_cases_are_rejected(self):
        for spec in ('VECTOR','ARRAY[1] OF INTEGER','FILE','PATH','QUEUE_TYPE','JOINTPOS2'):
            with self.subTest(spec=spec),self.assertRaises(TranslationError):build('SELECT 1 OF CASE(value): ENDSELECT',decl=DECL+' value:'+spec)

    def test_permitted_case_label_entry_bypasses_all_dispatch_expressions(self):
        p,_=build('n=0 GOTO selected SELECT key OF CASE(choice()): selected:: result=42 ENDSELECT',
                  routines='ROUTINE choice:INTEGER BEGIN n=99 RETURN 1 END choice')
        self.assertEqual((p.run()['N'],p.snapshot()['RESULT']),(0,42))

    def test_no_match_and_empty_else_keep_existing_behavior(self):
        p,_=build('key=2 result=7 SELECT 1 OF CASE(key): result=42 ENDSELECT')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'No match'):p.run()
        self.assertEqual(p.snapshot()['RESULT'],7)
        self.assertEqual(self.parity('key=2 result=7 SELECT 1 OF CASE(key): result=42 ELSE: ENDSELECT')['RESULT'],7)

    def test_translation_does_not_execute_case_functions(self):
        p,_=build('SELECT 1 OF CASE(choice()): ENDSELECT',routines='ROUTINE choice:INTEGER BEGIN ABORT RETURN 1 END choice')
        self.assertIsNone(p.abort_info)

    def test_source_linked_case_function_uses_callers_order(self):
        project=translate_project({'lib':source('LIB','',routines='ROUTINE choice:INTEGER BEGIN n=n+1 RETURN 7 END choice'),
            'main':source('MAIN','SELECT 7 OF CASE(choice()): result=42 ENDSELECT',decl='result:INTEGER',routines='ROUTINE choice:INTEGER FROM LIB')}).instantiate()
        project.programs['LIB']._state.values['N']=0;project.run('MAIN')
        self.assertEqual(project.programs['MAIN'].snapshot()['RESULT'],42);self.assertEqual(project.programs['LIB'].snapshot()['N'],1)

    def test_legacy_dynamic_integer_cases_remain_rejected(self):
        for case in ('n','choice()'):
            with self.subTest(case=case),self.assertRaises(TranslationError) as error:
                legacy_translate('PROGRAM T VAR n:INTEGER ROUTINE choice:INTEGER BEGIN RETURN 1 END choice BEGIN SELECT 1 OF CASE('+case+'): ENDSELECT END T')
            self.assertEqual(error.exception.code,'E_CONSTANT')

    def test_report_distinguishes_constant_slots_from_dynamic_slots(self):
        _,result=build('SELECT key OF CASE(1,label): result=42 ENDSELECT')
        report=json.loads(json.dumps(result.report));row=report['selects'][0]
        self.assertEqual(row['case_values'],[[1,None]]);self.assertEqual([x['dynamic'] for x in row['case_expressions']],[False,True])
        self.assertTrue(row['dynamic_cases']);self.assertIn('all_once',row['case_evaluation'])


if __name__=='__main__':unittest.main()
