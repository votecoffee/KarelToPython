"""Authored selection validation, publication and reference boundaries."""
from copy import deepcopy
import unittest

from karel2py import runtime as rt,translate
from karel2py.lexer import TranslationError,tokenize
from tests.test_extended_services import compile_program
from tests.test_system_pose_values import program,context
from tests.test_frame_tool_selection import execute


class FrameToolSelectionGuardTests(unittest.TestCase):
    def fail_write(self,body,ctx=None,**options):
        p,_=program(body,context=ctx or context(),**options);robot=p._state.execution.robot;before=(robot.active_frame,robot.active_tool);tables=deepcopy((robot.frames,robot.tools))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((robot.active_frame,robot.active_tool),before);self.assertEqual([rt.snapshot_value(x) for bank in (robot.frames,robot.tools) for x in bank.values()],[rt.snapshot_value(x) for bank in tables for x in bank.values()]);return p
    def reject(self,body):
        with self.assertRaises(TranslationError) as caught:program(body)
        return caught.exception.code
    def test_missing_frame_row_preserves_selection(self):self.fail_write('$MNUFRAMENUM[1]=7')
    def test_missing_tool_row_preserves_selection(self):self.fail_write('$MNUTOOLNUM[1]=7')
    def test_out_of_range_selection_preserves_state(self):
        for number in (-1,32768):
            with self.subTest(number=number):self.fail_write(f'$MNUFRAMENUM[1]={number}')
    def test_missing_group_preserves_state(self):self.fail_write('$MNUFRAMENUM[2]=0')
    def test_zero_group_is_not_inferred(self):self.fail_write('$MNUFRAMENUM[0]=0')
    def test_missing_robot_context_stays_explicit(self):
        p,_=compile_program('$MNUFRAMENUM[1]=0')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'):p.run()
    def test_unconfigured_special_tool_number_is_not_inferred(self):self.fail_write('$MNUTOOLNUM[1]=30')
    def test_unhashable_stored_id_fails_with_source_located_error(self):
        ctx=context();ctx.robot.active_frame=[];p,_=program('i=$MNUFRAMENUM[1]',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError) as caught:p.run()
        self.assertIsNotNone(caught.exception.line);self.assertIs(p._state.raw('I'),rt.UNINITIALIZED)
    def test_missing_rhs_value_preserves_selection(self):self.fail_write('$MNUFRAMENUM[1]=i')
    def test_malformed_row_is_not_selected(self):
        ctx=context();ctx.robot.frames[0].values['X']=float('nan');self.fail_write('$MNUFRAMENUM[1]=0',ctx)
    def test_partial_row_is_not_selected(self):
        ctx=context();ctx.robot.frames[0].values['X']=rt.UNINITIALIZED;self.fail_write('$MNUFRAMENUM[1]=0',ctx)
    def test_wrong_record_type_is_not_selected(self):
        ctx=context();ctx.robot.frames[0]=rt.Structure(('VECTOR',));self.fail_write('$MNUFRAMENUM[1]=0',ctx)
    def test_invalid_stored_selection_cannot_be_read(self):
        ctx=context();ctx.robot.active_frame=7;p,_=program('i=$MNUFRAMENUM[1]',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p._state.raw('I'),rt.UNINITIALIZED)
    def test_read_validates_selected_pose_geometry(self):
        ctx=context();ctx.robot.frames[2].values['X']=float('nan');p,_=program('i=$MNUFRAMENUM[1]',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_selector_effects_remain_after_failed_selection(self):
        routines='ROUTINE grp:INTEGER BEGIN n=7 RETURN 1 END grp'
        p=self.fail_write('$MNUFRAMENUM[grp]=7',routines=routines);self.assertEqual(p.snapshot()['N'],7.)
    def test_missing_rhs_prevents_group_effects(self):
        routines='ROUTINE grp:INTEGER BEGIN n=7 RETURN 1 END grp';p,_=program('$MNUFRAMENUM[grp]=i',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p._state.raw('N'),rt.UNINITIALIZED)
    def test_noninteger_rhs_is_rejected(self):
        for value in ('TRUE','2.0',"'2'",'p'):
            with self.subTest(value=value):self.assertEqual(self.reject('$MNUFRAMENUM[1]='+value),'E_TYPE')
    def test_noninteger_group_is_rejected(self):self.assertEqual(self.reject('i=$MNUFRAMENUM[TRUE]'),'E_TYPE')
    def test_wrong_arity_is_rejected(self):
        for value in ('$MNUFRAMENUM[]','$MNUFRAMENUM[1,2]','$MNUTOOLNUM'):
            with self.subTest(value=value),self.assertRaises(TranslationError):program('i='+value)
    def test_descendant_assignment_is_rejected(self):self.assertEqual(self.reject('$MNUFRAMENUM[1][1]=0'),'E_SYSTEM_SELECTION_TARGET')
    def test_read_output_cannot_alias_selection(self):self.assertIn(self.reject('READ($MNUFRAMENUM[1])'),('E_READ_ITEM','E_SYSTEM_SELECTION_REFERENCE'))
    def test_service_output_cannot_alias_selection(self):self.assertIn(self.reject("GET_VAR(entry,'','i',$MNUFRAMENUM[1],s)"),('E_OUTPUT_ARGUMENT','E_SYSTEM_SELECTION_REFERENCE'))
    def test_connected_timer_cannot_alias_selection(self):
        with self.assertRaises(TranslationError):program('CONNECT TIMER TO $MNUFRAMENUM[1]')
    def test_for_counter_cannot_alias_selection(self):
        with self.assertRaises(TranslationError):program('FOR $MNUFRAMENUM[1]=0 TO 2 DO i=7 ENDFOR')
    def test_system_names_cannot_be_declared(self):
        with self.assertRaises(TranslationError):program('',decl='$MNUFRAMENUM:INTEGER')
    def test_unknown_dollar_prefixes_remain_lexical_errors(self):
        for token in ('$MNUFRAMENUMBER[1]','$MNUTOOLNUM_X[1]'):
            with self.subTest(token=token),self.assertRaises(TranslationError) as caught:program('i='+token)
            self.assertEqual(caught.exception.code,'E_LEX')
    def test_lexing_retains_positions_and_casefolding(self):
        values=[t for t in tokenize('i=$mnuframenum[1] s=$mnutoolnum[1]','authored.kl') if t.value.startswith('$')];self.assertEqual([(t.value,t.column) for t in values],[('$MNUFRAMENUM',3),('$MNUTOOLNUM',21)])
    def test_strict_state_read_guard_remains(self):
        p,_=program('')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):p._state.system_selection('FRAME',1)
    def test_strict_state_write_guard_remains(self):
        p,_=program('')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):p._state.system_selection_write('FRAME',1,0)
    def test_strict_context_read_and_write_guards_remain(self):
        for operation in (lambda:context().system_selection('FRAME',1),lambda:context().system_selection_write('FRAME',1,0)):
            with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):operation()
    def test_invalid_runtime_kind_is_rejected(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):context().system_selection_write('UNKNOWN',1,0)
    def test_runtime_boolean_id_is_rejected(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):context().system_selection_write('FRAME',1,True)
    def test_nonordinary_table_is_rejected(self):
        class Derived(dict):pass
        ctx=context();ctx.robot.frames=Derived(ctx.robot.frames)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):ctx.system_selection_write('FRAME',1,0)
    def test_subclassed_row_is_rejected(self):
        class Derived(rt.Structure):pass
        ctx=context();ctx.robot.frames[0]=Derived(('XYZWPR',))
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):ctx.system_selection_write('FRAME',1,0)
    def test_failure_observation_is_value_free_and_source_located(self):
        p=self.fail_write('$MNUFRAMENUM[1]=7');row=p.service_requests[-1];self.assertEqual((row['operation'],row['outcome']),('SYSTEM_SELECTION_WRITE','failed'));self.assertIsNotNone(row['line']);self.assertEqual(set(row),{'operation','line','outcome'})
    def test_include_diagnostics_preserve_physical_source(self):
        with self.assertRaises(TranslationError) as caught:translate('PROGRAM T\n%INCLUDE BODY\nEND T',includes={'BODY.KL':'BEGIN $MNUFRAMENUM[TRUE]=0'})
        self.assertEqual((caught.exception.filename,caught.exception.token.line),('BODY.KL',1))
