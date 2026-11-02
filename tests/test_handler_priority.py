"""Authored deterministic handler priorities, option capture and lifecycle guards."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program


DECL='ready:BOOLEAN trace:STRING[32] n,s:INTEGER'


def handler(number,letter,options='',predicate='ready',extra=''):
    return f"CONDITION[{number}]: {('WITH '+options) if options else ''} WHEN {predicate} DO trace=trace+'{letter}' {extra} ENDCONDITION "


def execute(definitions,body='',**options):
    p,r=compile_program("trace='' ready=FALSE "+definitions+body+' s=0',decl=DECL,**options);return p,p.run(),r


class HandlerPriorityTests(unittest.TestCase):
    def test_lower_numeric_priority_scans_first(self):
        p,v,_=execute(handler(1,'a','$PRIORITY=80')+handler(2,'b','$PRIORITY=10')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ready=TRUE');self.assertEqual(v['TRACE'],'ba')
    def test_default_priority_is_fifty(self):
        p,v,_=execute(handler(1,'a','$PRIORITY=80')+handler(2,'b')+handler(3,'c','$PRIORITY=10')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ENABLE CONDITION[3] ready=TRUE');self.assertEqual(v['TRACE'],'cba');self.assertEqual(p._state._handlers[2]['priority'],50)
    def test_equal_priorities_preserve_definition_order(self):
        _,v,_=execute(handler(9,'a','$PRIORITY=30')+handler(1,'b','$PRIORITY=30')+'ENABLE CONDITION[1] ENABLE CONDITION[9] ready=TRUE');self.assertEqual(v['TRACE'],'ab')
    def test_unqualified_handlers_keep_existing_definition_order(self):
        _,v,_=execute(handler(9,'a')+handler(1,'b')+'ENABLE CONDITION[1] ENABLE CONDITION[9] ready=TRUE');self.assertEqual(v['TRACE'],'ab')
    def test_priority_bounds_are_inclusive(self):
        for priority in (1,99):
            p,v,_=execute(handler(1,'a',f'$PRIORITY={priority}')+'ENABLE CONDITION[1] ready=TRUE');self.assertEqual(v['TRACE'],'a');self.assertEqual(p._state._handlers[1]['priority'],priority)
    def test_out_of_range_priority_does_not_register(self):
        for priority in (0,100,-1):
            p,_=compile_program(handler(1,'a',f'$PRIORITY={priority}'),decl=DECL)
            with self.subTest(priority=priority),self.assertRaisesRegex(rt.KarelRuntimeError,'priority'):p.run()
            self.assertEqual(p._state._handlers,{})
    def test_invalid_scan_does_not_register(self):
        p,_=compile_program(handler(1,'a','$PRIORITY=20,$SCAN_TIME=-1'),decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'scan interval'):p.run()
        self.assertEqual(p._state._handlers,{})
    def test_noninteger_priority_is_rejected(self):
        for value in ('TRUE','1.5',"'20'"):
            with self.subTest(value=value),self.assertRaises(TranslationError):compile_program(handler(1,'a','$PRIORITY='+value),decl=DECL)
    def test_duplicate_option_is_rejected(self):
        for options in ('$PRIORITY=20,$PRIORITY=30','$SCAN_TIME=0 WITH $SCAN_TIME=1'):
            with self.subTest(options=options),self.assertRaises(TranslationError) as caught:compile_program(handler(1,'a',options),decl=DECL)
            self.assertEqual(caught.exception.code,'E_CONDITION_OPTION')
    def test_unknown_handler_option_is_rejected(self):
        with self.assertRaises(TranslationError) as caught:compile_program(handler(1,'a','$SPEED=20'),decl=DECL)
        self.assertEqual(caught.exception.code,'E_CONDITION_OPTION')
    def test_scan_and_priority_can_be_combined(self):
        p,v,r=execute(handler(1,'a','$PRIORITY=20,$SCAN_TIME=0')+'ENABLE CONDITION[1] ready=TRUE');self.assertEqual(v['TRACE'],'a');self.assertEqual(r.report['handler_definitions'][0]['option_order'],['$PRIORITY','$SCAN_TIME'])
    def test_scan_first_option_order(self):
        p,v,r=execute(handler(1,'a','$SCAN_TIME=0,$PRIORITY=20')+'ENABLE CONDITION[1] ready=TRUE');self.assertEqual(v['TRACE'],'a');self.assertEqual(r.report['handler_definitions'][0]['option_order'],['$SCAN_TIME','$PRIORITY'])
    def test_repeated_with_and_newlines(self):
        p,v,_=execute(handler(1,'a','$PRIORITY=20\nWITH\n$SCAN_TIME=0')+'ENABLE CONDITION[1] ready=TRUE');self.assertEqual(v['TRACE'],'a')
    def test_case_insensitive_options(self):
        p,v,_=execute(handler(1,'a','$priority=20,$scan_time=0')+'ENABLE CONDITION[1] ready=TRUE');self.assertEqual(v['TRACE'],'a')
    def test_number_then_options_run_once_in_source_order(self):
        routines="ROUTINE number:INTEGER BEGIN trace=trace+'n' RETURN 1 END number ROUTINE priority:INTEGER BEGIN trace=trace+'p' RETURN 20 END priority ROUTINE scan:INTEGER BEGIN trace=trace+'s' RETURN 0 END scan"
        p,v,_=execute(handler('number()','a','$PRIORITY=priority(),$SCAN_TIME=scan()'),routines=routines);self.assertEqual(v['TRACE'],'nps');self.assertEqual(p._state._handlers[1]['priority'],20)
    def test_capture_keeps_original_priority_value(self):
        p,v,_=execute('n=10 '+handler(1,'a','$PRIORITY=n')+'n=90 '+handler(2,'b','$PRIORITY=50')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ready=TRUE');self.assertEqual(v['TRACE'],'ab');self.assertEqual(p._state._handlers[1]['priority'],10)
    def test_disabled_high_priority_does_not_fire(self):
        _,v,_=execute(handler(1,'a','$PRIORITY=1')+handler(2,'b','$PRIORITY=90')+'ENABLE CONDITION[2] ready=TRUE');self.assertEqual(v['TRACE'],'b')
    def test_false_high_priority_does_not_block_lower_handler(self):
        _,v,_=execute(handler(1,'a','$PRIORITY=1',predicate='FALSE')+handler(2,'b','$PRIORITY=90')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ready=TRUE');self.assertEqual(v['TRACE'],'b')
    def test_not_due_high_priority_does_not_block_lower_handler(self):
        p,v,_=execute(handler(1,'a','$PRIORITY=1,$SCAN_TIME=100')+handler(2,'b','$PRIORITY=90')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ready=TRUE',clock_us=lambda:0);self.assertEqual(v['TRACE'],'b');self.assertTrue(p._state._handlers[1]['enabled'])
    def test_high_handler_can_disable_lower_before_its_turn(self):
        _,v,_=execute(handler(1,'a','$PRIORITY=1',extra='DISABLE CONDITION[2]')+handler(2,'b','$PRIORITY=90')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ready=TRUE');self.assertEqual(v['TRACE'],'a')
    def test_purged_lower_handler_is_skipped(self):
        _,v,_=execute(handler(1,'a','$PRIORITY=1',extra='PURGE CONDITION[2]')+handler(2,'b','$PRIORITY=90')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ready=TRUE');self.assertEqual(v['TRACE'],'a')
    def test_rearming_retains_priority_and_one_shot_behavior(self):
        p,v,_=execute(handler(1,'a','$PRIORITY=10')+'ENABLE CONDITION[1] ready=TRUE n=1 ready=FALSE ENABLE CONDITION[1] ready=TRUE');self.assertEqual(v['TRACE'],'aa');self.assertEqual(p._state._handlers[1]['priority'],10)
    def test_redefinition_requires_purge(self):
        p,_=compile_program(handler(1,'a','$PRIORITY=10')+handler(1,'b','$PRIORITY=90'),decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Purge'):p.run()
        self.assertEqual(p._state._handlers[1]['priority'],10)
    def test_purge_then_redefine_uses_new_priority(self):
        p,v,_=execute(handler(1,'a','$PRIORITY=90')+'PURGE CONDITION[1] '+handler(1,'b','$PRIORITY=10')+'ENABLE CONDITION[1] ready=TRUE');self.assertEqual(v['TRACE'],'b');self.assertEqual(p._state._handlers[1]['priority'],10)
    def test_multiple_when_clause_order_is_unchanged(self):
        p,v,_=execute("CONDITION[1]: WITH $PRIORITY=1 WHEN FALSE DO trace='bad' WHEN ready DO trace='ok' ENDCONDITION ENABLE CONDITION[1] ready=TRUE");self.assertEqual(v['TRACE'],'ok')
    def test_pause_retains_the_current_scan(self):
        text="trace='' ready=FALSE "+handler(1,'a','$PRIORITY=1',extra="PAUSE trace=trace+'b'")+handler(2,'c','$PRIORITY=90')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ready=TRUE n=7'
        p,_=compile_program(text,decl=DECL)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['TRACE'],'a');self.assertEqual(p.task_state,'paused');self.assertEqual(p.resume()['TRACE'],'abc');self.assertEqual(p.snapshot()['N'],7)
    def test_abort_retains_existing_deferred_scan_behavior(self):
        p,_=compile_program("trace='' ready=FALSE "+handler(1,'a','$PRIORITY=1',extra='ABORT')+handler(2,'b','$PRIORITY=90')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ready=TRUE s=0',decl=DECL)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot()['TRACE'],'ab')
    def test_local_scope_cleanup_keeps_no_priority_records(self):
        routines='ROUTINE work BEGIN '+handler(1,'a','$PRIORITY=1')+'END work'
        p,v,_=execute('',body='work',routines=routines,context=rt.ExecutionContext(local_handlers=True));self.assertEqual(p._state._handlers,{})
    def test_handler_records_are_not_serialized(self):
        p,v,_=execute(handler(1,'a','$PRIORITY=20'));saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertNotIn('handlers',saved);self.assertNotIn('priority',saved)
    def test_option_effects_retain_for_counter_protection(self):
        routines='ROUTINE change:INTEGER BEGIN n=7 RETURN 20 END change'
        with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+handler(1,'a','$PRIORITY=change()')+' ENDFOR',decl=DECL,routines=routines)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_dispatcher_preserves_priority_behavior(self):
        _,v,_=execute('start:: '+handler(1,'a','$PRIORITY=80')+handler(2,'b','$PRIORITY=10')+'ENABLE CONDITION[1] ENABLE CONDITION[2] ready=TRUE GOTO done trace=\'bad\' done::');self.assertEqual(v['TRACE'],'ba')
    def test_linked_parent_scans_before_callee_namespace(self):
        lib="PROGRAM LIB VAR ready FROM MAIN:BOOLEAN trace FROM MAIN:STRING[32] ROUTINE work BEGIN "+handler(1,'l','$PRIORITY=1')+'ENABLE CONDITION[1] ready=TRUE ready=ready END work BEGIN END LIB'
        main="PROGRAM MAIN VAR ready:BOOLEAN trace:STRING[32] ROUTINE work FROM LIB BEGIN trace='' ready=FALSE "+handler(1,'p','$PRIORITY=99')+'ENABLE CONDITION[1] work END MAIN'
        p=translate_project(dict(lib=lib,main=main)).instantiate();p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['TRACE'],'pl')
    def test_report_retains_defaults_and_offline_boundary(self):
        _,_,r=execute(handler(1,'a'));self.assertEqual(r.report['handler_definitions'][0]['option_order'],[]);self.assertIn('default 50',r.report['handler_priority_policy']['capture']);self.assertFalse(r.report['handler_priority_policy']['controller_validated'])
