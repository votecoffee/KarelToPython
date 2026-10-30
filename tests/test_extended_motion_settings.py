"""Authored enum WITH settings, explicit groups, ordered capture and checked history."""
from copy import deepcopy
import json
import unittest
from karel2py import runtime as rt,translate_project,translate
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_motion_requests import context,program,execute,DECL,SETUP
from tests.test_motion_handlers import program as scoped_program,scripted,move
from tests.test_motion_timeline import planned

TERMS=('FINE','COARSE','NOSETTLE','NODECEL','VARDECEL')
ORIENTS=('RSWORLD','AESWORLD','WRISTJOINT')
ALL="$SPEED=25,$ROTSPEED=10,$MOTYPE=STRAIGHT,$UFRAME=p,$UTOOL=q,$USE_CONFIG=FALSE,$TERMTYPE=FINE,$SEGTERMTYPE=NODECEL,$ORIENT_TYPE=RSWORLD"


def row(ctx):return next(r for r in reversed(ctx.motion.history) if r['operation'].startswith('MOVE '))
def values(ctx):return {r['name']:r['value'] for r in row(ctx)['data']['settings']}


def rejected(test,settings,*,routines='',before='n=0',operand='1'):
    ctx=context(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True)])
    p,_,_=program(before+' ATTACH WITH '+settings+' MOVE AWAY '+operand,ctx=ctx,routines=routines)
    with test.assertRaises(rt.KarelRuntimeError):p.run()
    test.assertEqual(len(ctx.motion.responses),1);test.assertEqual([r['operation'] for r in ctx.motion.history],['ATTACH']);test.assertEqual(ctx.group_locks.motion,{})
    return p,ctx


class MotionEnumChoiceTests(unittest.TestCase):
    def test_all_termination_choices_for_both_fields(self):
        for name in ('$TERMTYPE','$SEGTERMTYPE'):
            for choice in TERMS:
                _,ctx,_,_=execute('ATTACH WITH '+name+'='+choice+' MOVE AWAY 1');self.assertEqual(values(ctx)[name],choice)

    def test_all_orientation_choices(self):
        for choice in ORIENTS:
            _,ctx,_,_=execute('ATTACH WITH $ORIENT_TYPE='+choice+' MOVE AWAY 1');self.assertEqual(values(ctx)['$ORIENT_TYPE'],choice)

    def test_integer_termination_domains_match_names(self):
        for name in ('$TERMTYPE','$SEGTERMTYPE'):
            for number,choice in enumerate(TERMS,1):
                _,ctx,_,_=execute('ATTACH WITH '+name+'='+str(number)+' MOVE AWAY 1');self.assertEqual(values(ctx)[name],choice)

    def test_integer_orientation_domains_match_names(self):
        for number,choice in enumerate(ORIENTS,1):
            _,ctx,_,_=execute('ATTACH WITH $ORIENT_TYPE='+str(number)+' MOVE AWAY 1');self.assertEqual(values(ctx)['$ORIENT_TYPE'],choice)

    def test_straight_is_canonical_linear(self):
        _,ctx,_,_=execute('ATTACH WITH $MOTYPE=STRAIGHT MOVE TO p');self.assertEqual(values(ctx)['$MOTYPE'],'LINEAR')

    def test_contextual_enum_arithmetic(self):
        _,ctx,_,_=execute('ATTACH WITH $TERMTYPE=FINE+1,$SEGTERMTYPE=VARDECEL-1,$ORIENT_TYPE=RSWORLD+1 MOVE AWAY 1');self.assertEqual(list(values(ctx).values()),['COARSE','NODECEL','AESWORLD'])

    def test_dynamic_integer_and_narrow_arguments(self):
        for kind in ('INTEGER','BYTE','SHORT'):
            routines=f'ROUTINE work(choice:{kind}) BEGIN WITH $TERMTYPE=choice MOVE AWAY 1 END work'
            _,ctx,_,_=execute('ATTACH work(2)',routines=routines);self.assertEqual(values(ctx)['$TERMTYPE'],'COARSE')

    def test_enum_names_keep_ordinary_lookup_outside_with(self):
        p,_=compile_program('fine=9 linear=10 rsworld=11',decl='fine,linear,rsworld:INTEGER');self.assertEqual(p.run(),dict(FINE=9,LINEAR=10,RSWORLD=11))

    def test_enum_names_are_specific_to_their_setting(self):
        for setting in ('$TERMTYPE=LINEAR','$ORIENT_TYPE=FINE','$MOTYPE=RSWORLD'):
            with self.subTest(setting=setting),self.assertRaises(TranslationError):program('ATTACH WITH '+setting+' MOVE AWAY 1')

    def test_non_enum_values_use_ordinary_identifier_lookup(self):
        _,ctx,_,_=execute('fine=25 ATTACH WITH $SPEED=fine MOVE AWAY 1',decl=DECL+' fine:INTEGER');self.assertEqual(values(ctx)['$SPEED'],25.)

    def test_invalid_integer_choices_reject_without_consuming_response(self):
        for name,invalid in (('$TERMTYPE',(0,6,-1)),('$SEGTERMTYPE',(0,6,-1)),('$ORIENT_TYPE',(0,4,-1))):
            for number in invalid:
                with self.subTest(name=name,number=number):rejected(self,name+'='+str(number))

    def test_invalid_types_fail_translation(self):
        for name in ('$TERMTYPE','$SEGTERMTYPE','$ORIENT_TYPE'):
            for expression in ('TRUE','1.0',"'FINE'",'p'):
                with self.subTest(name=name,expression=expression),self.assertRaises(TranslationError):program('ATTACH WITH '+name+'='+expression+' MOVE AWAY 1')


class MotionQualifiedSettingTests(unittest.TestCase):
    def test_explicit_group_prefix_and_short_form_have_identical_data(self):
        _,first,_,_=execute('ATTACH WITH $GROUP[1].$TERMTYPE=FINE MOVE AWAY 1')
        _,second,_,_=execute('ATTACH WITH $TERMTYPE[1]=FINE MOVE AWAY 1');self.assertEqual(row(first)['data'],row(second)['data'])

    def test_all_nine_settings_accept_explicit_group_prefix(self):
        settings=','.join('$GROUP[1].'+entry for entry in ALL.split(','))
        _,ctx,_,_=execute('ATTACH WITH '+settings+' MOVE TO p');self.assertEqual(len(values(ctx)),9)

    def test_mixed_qualifiers_keep_canonical_names(self):
        _,ctx,_,_=execute('ATTACH WITH $TERMTYPE=FINE,$SEGTERMTYPE[1]=COARSE,$GROUP[1].$ORIENT_TYPE=AESWORLD MOVE AWAY 1');self.assertEqual(list(values(ctx)),['$TERMTYPE','$SEGTERMTYPE','$ORIENT_TYPE'])

    def test_group_then_value_then_move_operand_evaluate_once(self):
        routines='ROUTINE group_id:INTEGER BEGIN n=n*10+1 RETURN 1 END group_id ROUTINE choice:INTEGER BEGIN n=n*10+2 RETURN 2 END choice ROUTINE distance:REAL BEGIN n=n*10+3 RETURN 5.0 END distance'
        state,ctx,_,_=execute('n=0 ATTACH WITH $GROUP[group_id()].$TERMTYPE=choice() MOVE AWAY distance()',routines=routines);self.assertEqual(state['N'],123);self.assertEqual(values(ctx)['$TERMTYPE'],'COARSE')

    def test_late_invalid_choice_preserves_earlier_effects_and_skips_operand(self):
        routines='ROUTINE choice:INTEGER BEGIN n=n+1 RETURN 2 END choice ROUTINE distance:REAL BEGIN n=99 RETURN 1.0 END distance'
        p,_=rejected(self,'$TERMTYPE=choice(),$ORIENT_TYPE=4',routines=routines,operand='distance()');self.assertEqual(p.snapshot()['N'],1)

    def test_wrong_selected_group_is_atomic(self):
        rejected(self,'$GROUP[2].$TERMTYPE=FINE')

    def test_zero_group_is_atomic(self):
        rejected(self,'$GROUP[0].$TERMTYPE=FINE')

    def test_group_expression_requires_integer(self):
        for expression in ('TRUE','1.0',"'1'"):
            with self.subTest(expression=expression),self.assertRaises(TranslationError):program('ATTACH WITH $GROUP['+expression+'].$TERMTYPE=FINE MOVE AWAY 1')

    def test_duplicate_names_across_qualifiers_are_rejected(self):
        for setting in ('$TERMTYPE=FINE,$GROUP[1].$TERMTYPE=COARSE','$ORIENT_TYPE[1]=RSWORLD,$ORIENT_TYPE=AESWORLD'):
            with self.subTest(setting=setting):rejected(self,setting)

    def test_double_group_qualification_is_rejected_at_translation(self):
        with self.assertRaises(TranslationError) as caught:program('ATTACH WITH $GROUP[1].$TERMTYPE[1]=FINE MOVE AWAY 1')
        self.assertEqual(caught.exception.code,'E_MOTION_GROUP')

    def test_group_prefix_rejects_missing_parts_and_unknown_fields(self):
        for spelling in ('$GROUP.$TERMTYPE','$GROUP[1]','$GROUP[1].TERMTYPE','$GROUP[1].$SCAN_TIME','$GROUP[1].$GROUP'):
            with self.subTest(spelling=spelling),self.assertRaises(TranslationError):program('ATTACH WITH '+spelling+'=1 MOVE AWAY 1')

    def test_explicit_group_two_uses_the_selected_source_group(self):
        ctx=context(groups={1:2,2:2});_,ctx,_,_=execute('ATTACH WITH $GROUP[2].$TERMTYPE=FINE MOVE AWAY 1',ctx=ctx,prefix='%DEFGROUP=2');self.assertEqual((row(ctx)['group'],row(ctx)['data']['settings'][0]['group']),(2,2))


class MotionSettingLifetimeTests(unittest.TestCase):
    def test_all_seven_move_forms_retain_choices(self):
        setup='APPEND_NODE(route,s) route[1].node_pos=p '
        for form in ('TO p','NEAR p BY 1','AWAY 1','ABOUT v BY 45','AXIS 1 BY 1','RELATIVE v','ALONG route'):
            _,ctx,_,_=execute(setup+'ATTACH WITH $TERMTYPE=FINE,$ORIENT_TYPE=RSWORLD MOVE '+form);self.assertEqual(values(ctx)['$TERMTYPE'],'FINE')

    def test_immediate_nowait_keeps_choices(self):
        _,ctx,_,_=execute('ATTACH WITH $TERMTYPE=NOSETTLE MOVE AWAY 1 NOWAIT');self.assertTrue(row(ctx)['nowait']);self.assertEqual(values(ctx)['$TERMTYPE'],'NOSETTLE')

    def test_straight_with_via_retains_interpolation_guard(self):
        p,ctx,_=program('ATTACH WITH $MOTYPE=STRAIGHT,$TERMTYPE=FINE MOVE TO p VIA q')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.history),1)

    def test_circular_with_termination_and_orientation_accepts_via(self):
        _,ctx,_,_=execute('ATTACH WITH $MOTYPE=CIRCULAR,$TERMTYPE=VARDECEL,$ORIENT_TYPE=WRISTJOINT MOVE TO p VIA q');self.assertEqual(values(ctx)['$MOTYPE'],'CIRCULAR')

    def test_choices_do_not_carry_to_next_move(self):
        _,ctx,_,_=execute('ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1 MOVE AWAY 2');self.assertNotIn('settings',row(ctx)['data'])

    def test_local_when_sees_ordinary_names_after_setting_parse(self):
        p,ctx,_,_=scoped_program('fine=9 n=0 ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1, WHEN fine=9 DO n=1 ENDMOVE',decl=DECL+' fine:INTEGER');self.assertEqual(p.run()['N'],1);self.assertEqual(values(ctx)['$TERMTYPE'],'FINE')

    def test_local_until_keeps_captured_setting_on_cancellation(self):
        p,ctx,_,_=scoped_program('n=0 ATTACH WITH $SEGTERMTYPE=COARSE MOVE AWAY 1, UNTIL TRUE THEN n=1 ENDMOVE');self.assertEqual(p.run()['N'],1);self.assertEqual((row(ctx)['outcome'],values(ctx)['$SEGTERMTYPE']),('cancelled','COARSE'))

    def test_explicit_delay_keeps_choices(self):
        p,ctx,_,sleeps=scoped_program('ATTACH WITH $TERMTYPE=FINE,$ORIENT_TYPE=AESWORLD MOVE AWAY 1',ctx=scripted(7));p.run();self.assertEqual((sleeps,values(ctx)['$ORIENT_TYPE']),([.007],'AESWORLD'))

    def test_temporal_handler_keeps_choices_and_exact_arrival(self):
        p,ctx,_,sleeps=scoped_program('n=0 ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1, WHEN AT NODE[1] DO n=1 ENDMOVE',ctx=planned(delay=7));self.assertEqual((p.run()['N'],sleeps),(1,[.007]));self.assertEqual(values(ctx)['$TERMTYPE'],'FINE')

    def test_pause_resume_does_not_repeat_group_or_choice_calls(self):
        routines='ROUTINE group_id:INTEGER BEGIN n=n*10+1 RETURN 1 END group_id ROUTINE choice:INTEGER BEGIN n=n*10+2 RETURN 2 END choice'
        p,ctx,_,_=scoped_program('n=0 ATTACH WITH $GROUP[group_id()].$TERMTYPE=choice() MOVE AWAY 1, WHEN TRUE DO PAUSE ENDMOVE',ctx=scripted(7),routines=routines)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],12);self.assertEqual(p.resume()['N'],12);self.assertEqual(values(ctx)['$TERMTYPE'],'COARSE')

    def test_abort_releases_scope_with_choice_metadata(self):
        p,ctx,_,_=scoped_program('ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1, WHEN TRUE DO ABORT ENDMOVE',ctx=scripted(7))
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual((ctx.motion._active,ctx.group_locks.owners),({},{}));self.assertEqual(values(ctx)['$TERMTYPE'],'FINE')

    def test_positive_delay_nowait_stays_rejected_without_consumption(self):
        p,ctx,_,_=scoped_program('ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1 NOWAIT',ctx=scripted(7))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((len(ctx.motion.responses),len(ctx.motion.history)),(1,1))


class MotionSettingHistoryTests(unittest.TestCase):
    def test_all_nine_values_roundtrip_canonical_json(self):
        _,ctx,_,_=execute('ATTACH WITH '+ALL+' MOVE TO p');saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_history_rejects_raw_numeric_enum_values(self):
        for name in ('$TERMTYPE','$SEGTERMTYPE','$ORIENT_TYPE'):
            _,ctx,_,_=execute('ATTACH WITH '+name+'=1 MOVE AWAY 1');data=ctx.motion.to_config();data['history'][-1]['data']['settings'][0]['value']=1
            with self.subTest(name=name),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_history_rejects_invalid_enum_strings(self):
        for name in ('$TERMTYPE','$SEGTERMTYPE','$ORIENT_TYPE'):
            _,ctx,_,_=execute('ATTACH WITH '+name+'=1 MOVE AWAY 1');data=ctx.motion.to_config();data['history'][-1]['data']['settings'][0]['value']='UNKNOWN'
            with self.subTest(name=name),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_history_uses_linear_instead_of_source_straight_alias(self):
        _,ctx,_,_=execute('ATTACH WITH $MOTYPE=STRAIGHT MOVE TO p');data=ctx.motion.to_config();self.assertEqual(data['history'][-1]['data']['settings'][0]['value'],'LINEAR');data['history'][-1]['data']['settings'][0]['value']='STRAIGHT'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_history_rejects_choice_from_another_domain(self):
        _,ctx,_,_=execute('ATTACH WITH $ORIENT_TYPE=RSWORLD MOVE AWAY 1');data=ctx.motion.to_config();data['history'][-1]['data']['settings'][0]['value']='FINE'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_history_rejects_duplicate_new_settings(self):
        _,ctx,_,_=execute('ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1');data=ctx.motion.to_config();data['history'][-1]['data']['settings']*=2
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_history_rejects_group_mismatch(self):
        _,ctx,_,_=execute('ATTACH WITH $GROUP[1].$TERMTYPE=FINE MOVE AWAY 1');data=ctx.motion.to_config();data['history'][-1]['data']['settings'][0]['group']=2
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_history_rejects_qualified_name_instead_of_canonical_name(self):
        _,ctx,_,_=execute('ATTACH WITH $GROUP[1].$TERMTYPE=FINE MOVE AWAY 1');data=ctx.motion.to_config();data['history'][-1]['data']['settings'][0]['name']='$GROUP[1].$TERMTYPE'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_live_scoped_save_remains_rejected(self):
        p,ctx,_,_=scoped_program('ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1, WHEN TRUE DO PAUSE ENDMOVE',ctx=scripted(7))
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaises(ValueError):ctx.to_config()
        p.resume()

    def test_immediate_settings_history_is_detached_from_supplied_rows(self):
        _,ctx,_,_=execute('ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1');data=ctx.motion.to_config();data['history'][-1]['data']['settings'][0]['value']='COARSE';self.assertEqual(values(ctx)['$TERMTYPE'],'FINE')

    def test_old_six_setting_history_remains_valid(self):
        _,ctx,_,_=execute('ATTACH WITH '+','.join(ALL.split(',')[:6])+' MOVE TO p');saved=ctx.motion.to_config();self.assertEqual(rt.MotionRequests.from_config(saved).to_config(),saved)

    def test_eleven_setting_limit_is_enforced_at_translation(self):
        with self.assertRaises(TranslationError):program('ATTACH WITH '+ALL+',$DECELTOL=50,$USEMAXACCEL=TRUE,$SPEED=1 MOVE TO p')


class MotionSettingScopeTests(unittest.TestCase):
    def test_routine_local_constant_supplies_numeric_choice(self):
        _,ctx,_,_=execute('ATTACH work()',routines='ROUTINE work CONST chosen=5 BEGIN WITH $TERMTYPE=chosen MOVE AWAY 1 END work');self.assertEqual(values(ctx)['$TERMTYPE'],'VARDECEL')

    def test_computed_using_integer_field_can_supply_choice(self):
        prefix='TYPE settings_t=STRUCTURE term:INTEGER ENDSTRUCTURE'
        _,ctx,_,_=execute('settings.term=2 ATTACH USING settings DO WITH $TERMTYPE=term MOVE AWAY 1 ENDUSING',prefix=prefix,decl=DECL+' settings:settings_t');self.assertEqual(values(ctx)['$TERMTYPE'],'COARSE')

    def test_active_for_counter_cannot_be_changed_through_selector_call(self):
        with self.assertRaises(TranslationError):program('ATTACH FOR n=1 TO 2 DO WITH $GROUP[change()].$TERMTYPE=FINE MOVE AWAY 1 ENDFOR',routines='ROUTINE change:INTEGER BEGIN n=99 RETURN 1 END change')

    def test_linked_routine_records_source_module_and_dynamic_choice(self):
        main='PROGRAM MAIN ROUTINE work(choice:INTEGER) FROM LIB BEGIN ATTACH work(5) RELEASE END MAIN'
        lib='PROGRAM LIB ROUTINE work(choice:INTEGER) BEGIN WITH $GROUP[1].$TERMTYPE=choice MOVE AWAY 1 END work BEGIN END LIB'
        ctx=context();project=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);project.run('MAIN');self.assertEqual((row(ctx)['program'],row(ctx)['source_program'],values(ctx)['$TERMTYPE']),('MAIN','LIB','VARDECEL'))

    def test_no_system_namespace_access_is_added(self):
        for body in ('n=$TERMTYPE','$TERMTYPE=FINE','n=$GROUP[1].$TERMTYPE','$GROUP[1].$TERMTYPE=1'):
            with self.subTest(body=body),self.assertRaises(TranslationError):program(body)

    def test_setting_constant_scope_does_not_leak_to_move_operand(self):
        with self.assertRaises(TranslationError):program('ATTACH WITH $TERMTYPE=FINE MOVE AWAY FINE')

    def test_setting_constant_scope_does_not_leak_to_next_statement(self):
        with self.assertRaises(TranslationError):program('ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1 n=FINE')

    def test_group_qualified_report_preserves_canonical_name_and_location(self):
        _,_,_,r=execute('ATTACH WITH $GROUP[1].$TERMTYPE=FINE MOVE AWAY 1');site=r.report['motion_requests'][-1]['settings'][0];self.assertEqual((site['name'],site['group_qualified']),('$TERMTYPE',True));self.assertGreater(site['column'],1)

    def test_report_lists_domains_alias_and_limit(self):
        _,_,_,r=execute('ATTACH WITH $TERMTYPE=FINE MOVE AWAY 1');policy=r.report['motion_setting_policy'];self.assertEqual(policy['maximum'],11);self.assertEqual(policy['choices']['$MOTYPE']['STRAIGHT'],7);self.assertFalse(policy['controller_validated']);json.dumps(r.report)

    def test_context_frames_and_feedback_are_not_applied(self):
        from tests.test_joint_interoperability import model_context
        ctx=context();robot=model_context().robot;ctx.robot=robot;before=deepcopy(robot.to_config())
        execute('ATTACH WITH $TERMTYPE=FINE,$ORIENT_TYPE=WRISTJOINT,$UFRAME=p,$UTOOL=q MOVE TO p',ctx=ctx);self.assertEqual(robot.to_config(),before)

    def test_other_motion_variables_remain_rejected(self):
        for name in ('$ACCEL_OVRD','$SEG_TIME','$REF_POS','$DYN_I_COMP','$ACCU_NUM','$CNSTNT_PATH','$CONTAXISVEL','$TIME_SHIFT','$USE_CARTACC','$USERELACCEL','$USETIMESHFT'):
            with self.subTest(name=name),self.assertRaises(TranslationError):program('ATTACH WITH '+name+'=1 MOVE AWAY 1')

    def test_strict_mode_remains_a_future_milestone(self):
        with self.assertRaises(TranslationError) as caught:translate('PROGRAM T BEGIN END T',mode='strict')
        self.assertEqual(caught.exception.code,'E_MODE')


if __name__=='__main__':unittest.main()
