"""Authored Pythonic scalar SELECT categories, first matches and lifetime checks."""
import ast
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


ROOT=Path(__file__).resolve().parents[1]
U={'uninitialized':True}
TYPES='TYPE row_t=STRUCTURE flag:BOOLEAN label:STRING[8] value:REAL code:BYTE ENDSTRUCTURE'
DECL='flag:BOOLEAN text:STRING[254] number:REAL result,calls,total,i,j,status:INTEGER seed:row_t flags:ARRAY[2] OF BOOLEAN words:ARRAY[2] OF STRING[8] numbers:ARRAY[2] OF REAL small:BYTE signed:SHORT'


def build(body,*,labelled=False,decl=DECL,types=TYPES,constants='',routines='',cooperative=False,includes=None,translator=translate,**options):
    source=f'PROGRAM MAIN {constants} {types} VAR {decl} {routines} BEGIN '+('unused_marker:: ' if labelled else '')+body+' END MAIN'
    kwargs={'filename':'scalar_select.kl'}
    if translator is translate:kwargs.update(cooperative=cooperative,includes=includes)
    r=translator(source,**kwargs);ast.parse(r.python_source)
    ns={'__name__':'scalar_select_test'};exec(r.python_source,ns)
    return ns['Program'](**options),r


def execute(body,**options):return build(body,**options)[0].run()


def select(value,cases,has_else=False,*,category=None,line=71):
    with rt._numeric_scope('pythonic'):return rt.select_case(value,cases,has_else,line,category=category)


class ScalarSelectExecutionTests(unittest.TestCase):
    def parity(self,body,**options):
        states=[]
        for labelled in (False,True):
            p,_=build(body,labelled=labelled,**options);states.append((p.run(),p._state.steps))
        self.assertEqual(states[0],states[1]);return states[0][0]

    def test_boolean_on_off_cases(self):
        v=self.parity('SELECT ON OF CASE(OFF): result=1 CASE(TRUE): result=42 ENDSELECT SELECT FALSE OF CASE(FALSE): total=7 ELSE: total=9 ENDSELECT')
        self.assertEqual((v['RESULT'],v['TOTAL']),(42,7))

    def test_boolean_expression_and_constant_expression(self):
        v=self.parity('flag=TRUE SELECT flag AND NOT FALSE OF CASE(FALSE OR FALSE): result=1 CASE(TRUE AND TRUE): result=42 ENDSELECT')
        self.assertEqual(v['RESULT'],42)

    def test_boolean_duplicate_first_match(self):self.assertEqual(self.parity('SELECT TRUE OF CASE(TRUE,TRUE): result=42 CASE(ON): result=99 ENDSELECT')['RESULT'],42)

    def test_string_exact_match(self):self.assertEqual(self.parity("text='ready' SELECT text OF CASE('busy'): result=1 CASE('ready'): result=42 ENDSELECT")['RESULT'],42)

    def test_strings_are_case_sensitive_and_preserve_spaces(self):
        self.assertEqual(self.parity("SELECT ' Ready ' OF CASE('ready','READY','Ready'): result=1 CASE(' Ready '): result=42 ENDSELECT")['RESULT'],42)

    def test_empty_string_is_valid_case(self):self.assertEqual(self.parity("SELECT '' OF CASE('x'): result=1 CASE(''): result=42 ENDSELECT")['RESULT'],42)

    def test_apostrophe_string_roundtrip(self):self.assertEqual(self.parity("SELECT 'can''t' OF CASE('cannot'): result=1 CASE('can''t'): result=42 ENDSELECT")['RESULT'],42)

    def test_string_concatenation_selector_and_constant(self):self.assertEqual(self.parity("text='pre' SELECT text+'fix' OF CASE('pre'+'fix'): result=42 ENDSELECT")['RESULT'],42)

    def test_maximum_254_character_string(self):
        value='a'*254
        self.assertEqual(self.parity("SELECT '"+value+"' OF CASE('"+value+"'): result=42 ENDSELECT")['RESULT'],42)

    def test_fractional_real_selector_and_case(self):self.assertEqual(self.parity('SELECT 1.25 OF CASE(1.5): result=1 CASE(1.25): result=42 ENDSELECT')['RESULT'],42)

    def test_real_integer_cross_numeric_equality(self):
        v=self.parity('SELECT 2.0 OF CASE(2): result=42 ENDSELECT SELECT 3 OF CASE(3.0): total=7 ENDSELECT')
        self.assertEqual((v['RESULT'],v['TOTAL']),(42,7))

    def test_mixed_numeric_duplicates_choose_first_case(self):self.assertEqual(self.parity('SELECT 2 OF CASE(1,2.0): result=42 CASE(2): result=99 ENDSELECT')['RESULT'],42)

    def test_real_rounding_uses_exact_python_float_equality(self):
        v=self.parity('SELECT 0.3 OF CASE(0.1+0.2): result=1 ELSE: result=42 ENDSELECT SELECT 0.1+0.2 OF CASE(0.1+0.2): total=7 ENDSELECT')
        self.assertEqual((v['RESULT'],v['TOTAL']),(42,7))

    def test_signed_zero_real_matches_numeric_zero(self):self.assertEqual(self.parity('SELECT -0.0 OF CASE(0): result=42 CASE(0.0): result=99 ENDSELECT')['RESULT'],42)

    def test_finite_real_extremes_are_valid(self):
        v=self.parity('SELECT 1.0E308 OF CASE(1.0E308): result=42 ENDSELECT SELECT -1.0E308 OF CASE(-1.0E308): total=7 ENDSELECT')
        self.assertEqual((v['RESULT'],v['TOTAL']),(42,7))

    def test_smallest_subnormal_real_and_underflow_follow_pythonic_policy(self):
        v=self.parity('SELECT 5.0E-324 OF CASE(5.0E-324): result=42 ENDSELECT SELECT 1.0E-999 OF CASE(0): total=7 ENDSELECT')
        self.assertEqual((v['RESULT'],v['TOTAL']),(42,7))

    def test_integer_extremes_and_real_labels(self):
        v=self.parity('SELECT MININT OF CASE(-2147483648.0): result=42 ENDSELECT SELECT MAXINT OF CASE(2147483647.0): total=7 ENDSELECT')
        self.assertEqual((v['RESULT'],v['TOTAL']),(42,7))

    def test_byte_and_short_selectors_keep_numeric_behavior(self):
        v=self.parity('small=255 signed=-7 SELECT small OF CASE(255.0): result=42 ENDSELECT SELECT signed OF CASE(-7): total=7 ENDSELECT')
        self.assertEqual((v['RESULT'],v['TOTAL']),(42,7))

    def test_fields_and_array_elements_supply_scalar_selectors(self):
        v=self.parity("seed.flag=ON words[2]='yes' numbers[1]=2.5 SELECT seed.flag OF CASE(TRUE): result=1 ENDSELECT SELECT words[2] OF CASE('yes'): result=result+1 ENDSELECT SELECT numbers[1] OF CASE(2.5): result=result+40 ENDSELECT")
        self.assertEqual(v['RESULT'],42)

    def test_lexical_global_and_local_case_constants(self):
        routine="ROUTINE work:INTEGER CONST local_text='go' local_real=1.25 BEGIN SELECT local_text OF CASE('go'): SELECT local_real OF CASE(1.25): RETURN 42 ENDSELECT ENDSELECT RETURN 0 END work"
        v=self.parity('SELECT enabled OF CASE(TRUE): result=work() ENDSELECT',constants='CONST enabled=TRUE',routines=routine)
        self.assertEqual(v['RESULT'],42)

    def test_empty_first_match_does_not_fall_through(self):self.assertEqual(self.parity("result=42 SELECT 'yes' OF CASE('yes'): CASE('yes'): result=99 ELSE: result=100 ENDSELECT")['RESULT'],42)

    def test_empty_else_allows_continuation(self):self.assertEqual(self.parity('result=42 SELECT FALSE OF CASE(TRUE): result=99 ELSE: ENDSELECT total=result')['TOTAL'],42)

    def test_nested_mixed_category_selects(self):self.assertEqual(self.parity("SELECT TRUE OF CASE(TRUE): SELECT 'go' OF CASE('go'): SELECT 1.25 OF CASE(1.25): result=42 ENDSELECT ENDSELECT ENDSELECT")['RESULT'],42)

    def test_thousand_duplicate_string_clauses_still_choose_first(self):
        body="result=42 SELECT 'match' OF "+"CASE('match'): "*999+"CASE('match'): result=99 ENDSELECT"
        self.assertEqual(self.parity(body)['RESULT'],42)


class ScalarSelectEffectsAndFailureTests(unittest.TestCase):
    def test_effectful_function_selector_evaluates_once_in_each_engine(self):
        for kind,value,cases in (('BOOLEAN','TRUE','TRUE'),('STRING',"'yes'","'yes'"),('REAL','1.25','1.25')):
            for labelled in (False,True):
                with self.subTest(kind=kind,labelled=labelled):
                    routine=f'ROUTINE choose:{kind} BEGIN calls=calls+1 RETURN {value} END choose'
                    v=execute('calls=0 SELECT choose() OF CASE('+cases+'): result=42 ENDSELECT',routines=routine,labelled=labelled)
                    self.assertEqual((v['CALLS'],v['RESULT']),(1,42))

    def test_bare_typed_function_selector(self):
        v=execute("calls=0 SELECT choose OF CASE('yes'): result=42 ENDSELECT",routines="ROUTINE choose:STRING BEGIN calls=calls+1 RETURN 'yes' END choose")
        self.assertEqual((v['CALLS'],v['RESULT']),(1,42))

    def test_index_effect_is_evaluated_once_before_dispatch(self):
        routine='ROUTINE pick:INTEGER BEGIN calls=calls+1 RETURN 2 END pick'
        v=execute("calls=0 words[2]='yes' SELECT words[pick()] OF CASE('yes'): result=42 CASE('yes'): result=99 ENDSELECT",routines=routine)
        self.assertEqual((v['CALLS'],v['RESULT']),(1,42))

    def test_no_match_without_else_retains_effects_and_source_location(self):
        for value,candidate in (('FALSE','TRUE'),("'no'","'yes'"),('1.25','2.5')):
            for labelled in (False,True):
                p,r=build('result=7 SELECT '+value+' OF CASE('+candidate+'): result=99 ENDSELECT total=100',labelled=labelled)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'No match in CASE') as caught:p.run()
                self.assertEqual((p.snapshot()['RESULT'],p.snapshot()['TOTAL']),(7,U))
                self.assertEqual(caught.exception.line,r.report['selects'][0]['line'])

    def test_unmatched_effectful_scalar_selector_runs_once_before_error(self):
        for labelled in (False,True):
            p,_=build("calls=0 SELECT choose() OF CASE('yes'): result=42 ENDSELECT",labelled=labelled,
                routines="ROUTINE choose:STRING BEGIN calls=calls+1 RETURN 'no' END choose")
            with self.assertRaisesRegex(rt.KarelRuntimeError,'No match in CASE'):p.run()
            self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['RESULT'],p._state.call_depth),(1,U,0))

    def test_uninitialized_scalar_selector_fails_before_else(self):
        for selector in ('flag','text','number','small','signed'):
            case='TRUE' if selector=='flag' else "'x'" if selector=='text' else '1'
            with self.subTest(selector=selector):
                p,_=build('SELECT '+selector+' OF CASE('+case+'): result=1 ELSE: result=99 ENDSELECT')
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(p.snapshot()['RESULT'],U)

    def test_nonfinite_host_real_is_rejected_before_comparison(self):
        for value in (math.inf,-math.inf,math.nan):
            p,_=build('SELECT number OF CASE(1.0): result=1 ELSE: result=99 ENDSELECT')
            p._state.values['NUMBER']=value
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['RESULT'],U)

    def test_static_category_rejects_forged_boolean_numeric_storage(self):
        p,_=build('SELECT number OF CASE(1): result=42 ELSE: result=99 ENDSELECT');p._state.values['NUMBER']=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['RESULT'],U)

    def test_selector_budget_is_checked_before_call(self):
        p,_=build("calls=0 SELECT choose() OF CASE('yes'): result=42 ENDSELECT",routines="ROUTINE choose:STRING BEGIN calls=calls+1 RETURN 'yes' END choose")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=1)
        self.assertEqual(p.snapshot()['CALLS'],0)

    def test_only_selected_body_runs_and_later_body_remains_type_checked(self):
        v=execute('SELECT TRUE OF CASE(FALSE): ABORT CASE(TRUE): result=42 CASE(TRUE): result=99 ENDSELECT')
        self.assertEqual(v['RESULT'],42)
        with self.assertRaises(TranslationError):build('SELECT TRUE OF CASE(TRUE): result=42 CASE(FALSE): result=TRUE ENDSELECT')

    def test_selector_reference_effect_cannot_modify_active_counter(self):
        routine='ROUTINE choose(p:INTEGER):BOOLEAN BEGIN p=99 RETURN TRUE END choose'
        with self.assertRaises(TranslationError) as caught:build('FOR i=1 TO 2 DO SELECT choose(i) OF CASE(TRUE): ENDSELECT ENDFOR',routines=routine)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_function_return_unwinds_frames_after_selected_case(self):
        routine="ROUTINE choose(n:STRING):INTEGER BEGIN SELECT n OF CASE('yes'): RETURN 42 ELSE: RETURN 7 ENDSELECT END choose"
        p,_=build("result=choose('yes')",routines=routine);self.assertEqual(p.run()['RESULT'],42)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))


class ScalarSelectRejectionTests(unittest.TestCase):
    def reject(self,body,code,**options):
        for labelled in (False,True):
            with self.subTest(labelled=labelled):
                with self.assertRaises(TranslationError) as caught:build(body,labelled=labelled,**options)
                self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_boolean_and_numeric_categories_never_mix(self):
        for body in ('SELECT TRUE OF CASE(1): ENDSELECT','SELECT 1 OF CASE(TRUE): ENDSELECT',
                     'SELECT 0.0 OF CASE(FALSE): ENDSELECT','SELECT FALSE OF CASE(0.0): ENDSELECT'):
            self.reject(body,'E_CASE')

    def test_string_and_other_categories_never_mix(self):
        for body in ("SELECT '1' OF CASE(1): ENDSELECT","SELECT 1 OF CASE('1'): ENDSELECT",
                     "SELECT TRUE OF CASE('TRUE'): ENDSELECT","SELECT 'TRUE' OF CASE(TRUE): ENDSELECT"):
            self.reject(body,'E_CASE')

    def test_invalid_category_after_earlier_matching_case_still_rejected(self):self.reject('SELECT TRUE OF CASE(TRUE): result=42 CASE(1): result=99 ENDSELECT','E_CASE')

    def test_dynamic_case_variable_is_checked_at_runtime(self):
        self.assertEqual(execute('flag=TRUE SELECT TRUE OF CASE(flag): result=42 ENDSELECT')['RESULT'],42)

    def test_dynamic_function_case_translates_without_execution(self):
        p,_=build('SELECT TRUE OF CASE(choose()): ENDSELECT',routines='ROUTINE choose:BOOLEAN BEGIN ABORT END choose')
        self.assertIsNone(p.abort_info)
        with self.assertRaises(rt.KarelAbort):p.run()

    def test_aggregate_and_resource_selectors_are_rejected(self):
        for spec in ('VECTOR','CONFIG','JOINTPOS3','ARRAY[2] OF BOOLEAN','FILE','PATH','QUEUE_TYPE'):
            self.reject('SELECT value OF CASE(TRUE): ENDSELECT','E_TYPE',types='',decl='value:'+spec)

    def test_whole_record_selector_is_rejected(self):self.reject('SELECT seed OF CASE(TRUE): ENDSELECT','E_TYPE')

    def test_nonfinite_real_literal_or_constant_is_rejected(self):
        self.reject('SELECT 1.0E999 OF CASE(1.0): ENDSELECT','E_REAL_LITERAL')
        self.reject('SELECT 1.0 OF CASE(1.0E999): ENDSELECT','E_CONSTANT')

    def test_out_of_range_integer_case_is_rejected(self):self.reject('SELECT 1.0 OF CASE(2147483648): ENDSELECT','E_CASE')

    def test_minimum_literal_guard_is_retained(self):self.reject('SELECT -1.0 OF CASE(-2147483648): ENDSELECT','E_MININT_LITERAL')

    def test_unicode_literal_is_rejected(self):
        with self.assertRaises(TranslationError):build("SELECT 'caf\u00e9' OF CASE('caf\u00e9'): ENDSELECT")

    def test_using_field_is_a_dynamic_case(self):
        self.assertEqual(execute('seed.flag=TRUE USING seed DO SELECT TRUE OF CASE(flag): result=42 ENDSELECT ENDUSING')['RESULT'],42)

    def test_legacy_selector_types_and_real_case_remain_restricted(self):
        for body,code in (('SELECT TRUE OF CASE(TRUE): ENDSELECT','E_TYPE'),("SELECT 'yes' OF CASE('yes'): ENDSELECT",'E_TYPE'),
                         ('SELECT 1.0 OF CASE(1): ENDSELECT','E_TYPE'),('SELECT 1 OF CASE(1.0): ENDSELECT','E_CASE')):
            self.reject(body,code,translator=legacy_translate,types='',decl='result:INTEGER')


class ScalarSelectControlFlowTests(unittest.TestCase):
    def test_goto_to_sibling_case_runs_explicit_suffix_without_fallthrough(self):
        v=execute("SELECT 'yes' OF CASE('yes'): result=7 GOTO sibling CASE('no'): result=99 sibling:: total=result+35 ENDSELECT")
        self.assertEqual((v['RESULT'],v['TOTAL']),(7,42))

    def test_direct_case_entry_skips_selector_and_dispatch(self):
        v=execute('calls=0 GOTO inside SELECT choose() OF CASE(TRUE): inside:: result=42 ENDSELECT',routines='ROUTINE choose:BOOLEAN BEGIN calls=calls+1 RETURN FALSE END choose')
        self.assertEqual((v['CALLS'],v['RESULT']),(0,42))

    def test_goto_out_of_selected_case_clears_active_for_counter(self):
        v=execute('FOR i=1 TO 3 DO SELECT TRUE OF CASE(TRUE): GOTO done ENDSELECT ENDFOR done:: flag=UNINIT(i)')
        self.assertEqual((v['FLAG'],v['I']),(True,U))

    def test_private_using_counter_can_select_and_exit_with_cleanup(self):
        types='TYPE row_t=STRUCTURE count:INTEGER ENDSTRUCTURE'
        routine='ROUTINE make:row_t BEGIN RETURN seed END make'
        v=execute('total=0 USING make() DO FOR count=1 TO 3 DO SELECT count=2 OF CASE(TRUE): GOTO done ELSE: total=total+count ENDSELECT ENDFOR done:: flag=UNINIT(count) ENDUSING',types=types,routines=routine)
        self.assertEqual((v['TOTAL'],v['FLAG'],v['SEED']['COUNT']),(1,True,U))

    def test_pause_in_selected_body_does_not_reselect(self):
        p,_=build("calls=0 SELECT choose() OF CASE('yes'): result=20 PAUSE result=result+22 ELSE: result=99 ENDSELECT",cooperative=True,routines="ROUTINE choose:STRING BEGIN calls=calls+1 RETURN 'yes' END choose")
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['RESULT']),(1,20))
        v=p.resume();self.assertEqual((v['CALLS'],v['RESULT']),(1,42))

    def test_pause_in_selector_function_resumes_one_call(self):
        p,_=build('calls=0 SELECT choose() OF CASE(1.25): result=42 ENDSELECT',cooperative=True,routines='ROUTINE choose:REAL BEGIN calls=calls+1 PAUSE RETURN 1.25 END choose')
        with self.assertRaises(rt.KarelPause):p.run()
        v=p.resume();self.assertEqual((v['CALLS'],v['RESULT']),(1,42))

    def test_stop_while_selected_case_paused_clears_for_and_routine_frames(self):
        routine='ROUTINE work BEGIN FOR i=1 TO 2 DO SELECT TRUE OF CASE(TRUE): PAUSE ENDSELECT ENDFOR END work'
        p,_=build('work',routines=routine,cooperative=True,labelled=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual((p.snapshot()['I'],p._state.local_frames,p._state.call_depth),(U,[],0))

    def test_selected_abort_unwinds_active_counter(self):
        p,_=build('FOR i=1 TO 2 DO SELECT TRUE OF CASE(TRUE): ABORT ENDSELECT ENDFOR')
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot()['I'],U)

    def test_handler_can_use_boolean_string_and_real_selects(self):
        v=execute("CONDITION[1]: WHEN EVENT[1] DO SELECT TRUE OF CASE(TRUE): SELECT 'go' OF CASE('go'): SELECT 1.25 OF CASE(1.25): result=42 ENDSELECT ENDSELECT ENDSELECT ENDCONDITION ENABLE CONDITION[1] SIGNAL EVENT[1]")
        self.assertEqual(v['RESULT'],42)

    def test_missing_match_cleans_active_for_counter_in_both_engines(self):
        for labelled in (False,True):
            p,_=build('FOR i=1 TO 2 DO SELECT FALSE OF CASE(TRUE): ENDSELECT ENDFOR',labelled=labelled)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'No match in CASE'):p.run()
            self.assertEqual(p.snapshot()['I'],U)


class ScalarSelectRuntimeTests(unittest.TestCase):
    def test_boolean_runtime_first_match_and_else(self):
        self.assertEqual(select(True,((False,),(True,True),(True,))),1)
        self.assertEqual(select(False,((True,),),True),1)

    def test_numeric_runtime_preserves_mixed_first_match(self):
        self.assertEqual(select(2,((2.0,),(2,))),0)
        self.assertEqual(select(2.0,((1,),(2,))),1)

    def test_runtime_numeric_comparison_does_not_truncate_or_tolerate(self):
        self.assertEqual(select(1.25,((1,),),True),1)
        self.assertEqual(select(0.3,((0.1+0.2,),),True),1)

    def test_runtime_string_controls_and_case_sensitive_equality(self):
        self.assertEqual(select('A\t\x00',(('a\t\x00',),('A\t\x00',))),1)

    def test_numeric_boolean_leakage_is_rejected_both_directions(self):
        for value,cases in ((True,((1,),)),(1,((True,),)),(False,((0.0,),)),(0.0,((False,),))):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):select(value,cases)

    def test_explicit_category_is_checked_even_for_matching_values(self):
        for value,category,cases in ((True,'NUMERIC',((True,),)),(1,'BOOLEAN',((1,),)),('x','NUMERIC',(('x',),))):
            with self.assertRaises(rt.KarelRuntimeError):select(value,cases,category=category)

    def test_runtime_nonfinite_selector_and_later_constants_rejected(self):
        for value in (math.inf,-math.inf,math.nan):
            with self.assertRaises(rt.KarelRuntimeError):select(value,((1.0,),),True)
            with self.assertRaises(rt.KarelRuntimeError):select(1.0,((1.0,),(value,)))

    def test_runtime_nonascii_or_overlong_strings_rejected_before_match(self):
        for value in ('\u00e9','a'*255):
            with self.assertRaises(rt.KarelRuntimeError):select(value,(('x',),),True)
            with self.assertRaises(rt.KarelRuntimeError):select('x',(('x',),(value,)))

    def test_runtime_later_category_mismatch_is_not_hidden_by_first_match(self):
        for value,cases in ((True,((True,),(1,))),('x',(('x',),(False,))),(1.0,((1,),(True,)))):
            with self.assertRaises(rt.KarelRuntimeError):select(value,cases)

    def test_runtime_exact_primitive_types_prevent_custom_equality(self):
        class Evil:
            def __eq__(self,other):raise AssertionError('must not call custom equality')
        class StrangeInt(int):pass
        for value in (Evil(),StrangeInt(1)):
            with self.assertRaises(rt.KarelRuntimeError):select(value,((1,),),True)
            with self.assertRaises(rt.KarelRuntimeError):select(1,((1,),(value,)))

    def test_runtime_invalid_shapes_flags_and_categories_rejected(self):
        for cases in ((),((),),({'x'},),None,((True,),)*1001):
            with self.assertRaises(rt.KarelRuntimeError):select(True,cases)
        for category in ('INTEGER','REAL','numeric',False,[]):
            with self.assertRaises(rt.KarelRuntimeError):select(1,((1,),),category=category)
        for flag in (0,1,None,'true'):
            with self.assertRaises(rt.KarelRuntimeError):select(True,((True,),),flag)

    def test_runtime_missing_value_and_source_line(self):
        for missing in (rt.UNINITIALIZED,rt.UNKNOWN_BYTE,None):
            with self.assertRaises(rt.KarelRuntimeError):select(missing,((1,),),True)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'No match in CASE') as caught:select('no',(('yes',),),line=47)
        self.assertEqual(caught.exception.line,47)

    def test_legacy_runtime_remains_integer_only_and_rejects_explicit_category(self):
        for value,cases in ((True,((True,),)),('yes',(('yes',),)),(1.0,((1.0,),))):
            with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.select_case(value,cases,False)
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.select_case(1,((1,),),False,category='NUMERIC')


class ScalarSelectReportAndIntegrationTests(unittest.TestCase):
    def test_report_preserves_selector_and_case_categories_in_json(self):
        _,r=build("SELECT TRUE OF CASE(TRUE): ENDSELECT SELECT 'yes' OF CASE('yes'): ENDSELECT SELECT 2.0 OF CASE(2,2.0): ENDSELECT")
        rows=json.loads(json.dumps(r.report))['selects']
        self.assertEqual([row['comparison_category'] for row in rows],['BOOLEAN','STRING','NUMERIC'])
        self.assertEqual([row['selector_type'][0] for row in rows],['BOOLEAN','STRING','REAL'])
        self.assertEqual(rows[2]['case_types'],[['INTEGER','REAL']])
        self.assertEqual(rows[2]['case_values'],[[2,2.0]])

    def test_included_select_uses_physical_source_map(self):
        p,r=build('\n%INCLUDE selection\n',includes={'selection.kl':"SELECT 'yes' OF CASE('yes'): result=42 ENDSELECT"})
        self.assertEqual(p.run()['RESULT'],42)
        self.assertTrue(any(row.get('source_file')=='selection.kl' for row in r.report['source_map']))

    def test_linked_external_typed_selector_executes_once(self):
        sources={'main':"PROGRAM MAIN VAR result:INTEGER ROUTINE choose:STRING FROM LIB BEGIN SELECT choose() OF CASE('yes'): result=42 ENDSELECT END MAIN",
            'lib':"PROGRAM LIB VAR calls:INTEGER ROUTINE choose:STRING BEGIN IF UNINIT(calls) THEN calls=0 ENDIF calls=calls+1 RETURN 'yes' END choose BEGIN END LIB"}
        instance=translate_project(sources).instantiate();v=instance.run('MAIN')
        self.assertEqual((v['MAIN']['values']['RESULT'],v['LIB']['values']['CALLS']),(42,1))

    def test_context_roundtrip_retains_scalar_inputs_and_outputs(self):
        body="IF UNINIT(text) THEN text='yes' ENDIF IF UNINIT(number) THEN number=1.25 ENDIF SELECT text OF CASE('yes'): SELECT number OF CASE(1.25): result=42 ENDSELECT ENDSELECT"
        p,_=build(body);self.assertEqual(p.run()['RESULT'],42)
        config=json.loads(json.dumps(p._state.execution.to_config()))
        q,_=build(body,context=rt.ExecutionContext.from_config(config));self.assertEqual(q.run()['RESULT'],42)
        self.assertEqual((q.snapshot()['TEXT'],q.snapshot()['NUMBER']),('yes',1.25))

    def test_generated_cli_and_state_out_preserve_scalar_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'main.kl';target=Path(folder)/'main.py';state=Path(folder)/'state.json'
            source.write_bytes(b"PROGRAM MAIN VAR result:INTEGER BEGIN SELECT 'yes' OF CASE('yes'): result=42 ENDSELECT END MAIN")
            p=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(source),'-o',str(target)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            env=dict(os.environ,PYTHONPATH=str(ROOT))
            p=subprocess.run([sys.executable,'-X','utf8',str(target),'--state-out',str(state)],cwd=ROOT,env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(state.read_text(encoding='utf-8'))['variables'],[dict(program='MAIN',path='RESULT',type=['INTEGER'],value=42)])


if __name__=='__main__':unittest.main()
