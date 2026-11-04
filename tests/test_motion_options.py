"""Authored motion option domains, request publication, timing and saved history."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError, tokenize
from tests.test_motion_requests import program, execute, context, DECL
from tests.test_extended_motion_settings import ALL, row, values, rejected
from tests.test_motion_handlers import program as scoped, scripted
from tests.test_motion_timeline import planned

NEW = '$ACCEL_OVRD=125,$ACCU_NUM=3,$SEG_TIME=40,$TIME_SHIFT=10,$CONTAXISVEL=-25.5,$CNSTNT_PATH=TRUE,$DYN_I_COMP=FALSE,$USE_CARTACC=TRUE,$USERELACCEL=TRUE,$USETIMESHFT=TRUE'
COMPLETE = ALL + ',$DECELTOL=50,$USEMAXACCEL=TRUE,' + NEW
EXPECTED = {'$ACCEL_OVRD':125,'$ACCU_NUM':3,'$SEG_TIME':40,'$TIME_SHIFT':10,'$CONTAXISVEL':-25.5,'$CNSTNT_PATH':True,'$DYN_I_COMP':False,'$USE_CARTACC':True,'$USERELACCEL':True,'$USETIMESHFT':True}
FLAGS = ('$CNSTNT_PATH','$DYN_I_COMP','$USE_CARTACC','$USERELACCEL','$USETIMESHFT')
INTEGERS = ('$ACCEL_OVRD','$ACCU_NUM','$SEG_TIME','$TIME_SHIFT')


def saved_options():
    _, ctx, _, _ = execute('ATTACH WITH '+NEW+' MOVE AWAY 1')
    return ctx.motion.to_config()


def changed(saved, name, value):
    data = deepcopy(saved)
    next(r for r in data['history'][-1]['data']['settings'] if r['name']==name)['value'] = value
    return data


class MotionOptionValueTests(unittest.TestCase):
    def test_acceleration_override_endpoints_and_zero(self):
        for n in (0,1,100,125,500):
            _,ctx,_,_=execute('ATTACH WITH $ACCEL_OVRD='+str(n)+' MOVE AWAY 1')
            self.assertEqual(values(ctx)['$ACCEL_OVRD'],n)

    def test_accuracy_area_endpoints(self):
        for n in (0,1,5,10):
            _,ctx,_,_=execute('ATTACH WITH $ACCU_NUM='+str(n)+' MOVE AWAY 1')
            self.assertEqual(values(ctx)['$ACCU_NUM'],n)

    def test_segment_milliseconds_endpoints(self):
        for n in (0,1,99999,100000):
            _,ctx,_,_=execute('ATTACH WITH $SEG_TIME='+str(n)+' MOVE AWAY 1')
            self.assertEqual(values(ctx)['$SEG_TIME'],n)

    def test_shift_milliseconds_endpoints(self):
        for n in (0,1,9999,10000):
            _,ctx,_,_=execute('ATTACH WITH $TIME_SHIFT='+str(n)+' MOVE AWAY 1')
            self.assertEqual(values(ctx)['$TIME_SHIFT'],n)

    def test_continuous_axis_speed_retains_both_directions_and_zero(self):
        for n in (-100.,-25.5,0.,25.5,100.):
            _,ctx,_,_=execute('ATTACH WITH $CONTAXISVEL='+str(n)+' MOVE AWAY 1')
            self.assertEqual(values(ctx)['$CONTAXISVEL'],n)
            self.assertIs(type(values(ctx)['$CONTAXISVEL']),float)

    def test_continuous_axis_integer_promotes_to_real(self):
        _,ctx,_,_=execute('ATTACH WITH $CONTAXISVEL=-25 MOVE AWAY 1')
        self.assertEqual(values(ctx)['$CONTAXISVEL'],-25.)
        self.assertIs(type(values(ctx)['$CONTAXISVEL']),float)

    def test_boolean_options_retain_exact_false_and_true(self):
        for name in FLAGS:
            for source,expected in [('TRUE',True),('FALSE',False)]:
                _,ctx,_,_=execute('ATTACH WITH '+name+'='+source+' MOVE AWAY 1')
                self.assertIs(values(ctx)[name],expected)

    def test_all_ten_options_share_one_request(self):
        _,ctx,_,_=execute('ATTACH WITH '+NEW+' MOVE AWAY 1')
        self.assertEqual(values(ctx),EXPECTED)

    def test_all_twenty_one_settings_share_one_request(self):
        _,ctx,_,_=execute('ATTACH WITH '+COMPLETE+' MOVE TO p')
        self.assertEqual(len(values(ctx)),21)
        for name,value in EXPECTED.items():self.assertEqual(values(ctx)[name],value)

    def test_group_qualified_and_indexed_options_share_selected_group(self):
        settings='$GROUP[2].$ACCEL_OVRD=125,$SEG_TIME[2]=40,$CONTAXISVEL[2]=-25.5,$USETIMESHFT[2]=TRUE'
        _,ctx,_,_=execute('ATTACH WITH '+settings+' MOVE AWAY 1',ctx=context(groups={1:2,2:2}),prefix='%DEFGROUP=2')
        self.assertTrue(all(r['group']==2 for r in row(ctx)['data']['settings']))

    def test_case_insensitive_option_names(self):
        _,ctx,_,_=execute('ATTACH with $accel_ovrd=125,$contaxisvel=-25.5,$cnstnt_path=true move away 1')
        self.assertEqual(values(ctx),{'$ACCEL_OVRD':125,'$CONTAXISVEL':-25.5,'$CNSTNT_PATH':True})

    def test_narrow_integer_arguments_are_supported(self):
        for kind in ('INTEGER','BYTE','SHORT'):
            for name in INTEGERS:
                _,ctx,_,_=execute('ATTACH work(5)',routines='ROUTINE work(n:'+kind+') BEGIN WITH '+name+'=n MOVE AWAY 1 END work')
                self.assertEqual(values(ctx)[name],5)

    def test_dynamic_boolean_and_real_expressions(self):
        _,ctx,_,_=execute('n=5 ATTACH WITH $CNSTNT_PATH=n>0,$CONTAXISVEL=-n/2 MOVE AWAY 1')
        self.assertEqual(values(ctx),{'$CNSTNT_PATH':True,'$CONTAXISVEL':-2.5})

    def test_all_move_forms_carry_new_options(self):
        for form in ('TO p','NEAR p BY 1','AWAY 1','ABOUT v BY 1','AXIS 1 BY 1','RELATIVE v','ALONG route'):
            _,ctx,_,_=execute('APPEND_NODE(route,s) route[1].node_pos=p ATTACH WITH '+NEW+' MOVE '+form)
            self.assertEqual(values(ctx),EXPECTED)

    def test_circular_via_retains_options_and_existing_constraint(self):
        _,ctx,_,_=execute('ATTACH WITH '+NEW+',$MOTYPE=CIRCULAR MOVE TO p VIA q')
        self.assertEqual(values(ctx)['$CONTAXISVEL'],-25.5)
        rejected(self,NEW+',$MOTYPE=CIRCULAR')

    def test_unqualified_next_request_has_no_options(self):
        _,ctx,_,_=execute('ATTACH WITH '+NEW+' MOVE AWAY 1 MOVE AWAY 2')
        self.assertNotIn('settings',row(ctx)['data'])

    def test_immediate_nowait_keeps_checked_metadata(self):
        _,ctx,_,_=execute('ATTACH WITH '+NEW+' MOVE AWAY 1 NOWAIT')
        self.assertTrue(row(ctx)['nowait']);self.assertEqual(values(ctx),EXPECTED)

    def test_request_does_not_change_robot_context_or_feedback(self):
        from tests.test_joint_interoperability import model_context
        ctx=context();ctx.robot=model_context().robot;before=deepcopy(ctx.robot.to_config())
        execute('ATTACH WITH '+NEW+' MOVE AWAY 1',ctx=ctx)
        self.assertEqual(ctx.robot.to_config(),before)


class MotionOptionAdmissionTests(unittest.TestCase):
    def test_acceleration_domain_rejection_preserves_response(self):
        for n in (-1,501,2147483646):rejected(self,'$ACCEL_OVRD='+str(n))

    def test_accuracy_domain_rejection_preserves_response(self):
        for n in (-1,11,2147483646):rejected(self,'$ACCU_NUM='+str(n))

    def test_segment_domain_rejection_preserves_response(self):
        for n in (-1,100001,2147483646):rejected(self,'$SEG_TIME='+str(n))

    def test_time_shift_domain_rejection_preserves_response(self):
        for n in (-1,10001,2147483646):rejected(self,'$TIME_SHIFT='+str(n))

    def test_signed_velocity_outside_range_preserves_response(self):
        for n in (-100.01,100.01):rejected(self,'$CONTAXISVEL='+str(n))

    def test_real_boolean_and_string_cannot_supply_integer_options(self):
        for name in INTEGERS:
            for bad in ('TRUE','1.0',"'1'"):
                with self.subTest(name=name,bad=bad),self.assertRaises(TranslationError):program('ATTACH WITH '+name+'='+bad+' MOVE AWAY 1')

    def test_numeric_and_string_truthiness_cannot_supply_flags(self):
        for name in FLAGS:
            for bad in ('1','0','1.0',"'TRUE'"):
                with self.subTest(name=name,bad=bad),self.assertRaises(TranslationError):program('ATTACH WITH '+name+'='+bad+' MOVE AWAY 1')

    def test_signed_velocity_rejects_boolean_and_string(self):
        for bad in ('TRUE',"'-25'"):
            with self.assertRaises(TranslationError):program('ATTACH WITH $CONTAXISVEL='+bad+' MOVE AWAY 1')

    def test_uninitialized_integer_option_is_not_defaulted(self):
        p,ctx,_=program('ATTACH WITH $ACCU_NUM=n MOVE AWAY 1')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual([r['operation'] for r in ctx.motion.history],['ATTACH'])

    def test_uninitialized_boolean_option_is_not_defaulted(self):
        p,ctx,_=program('ATTACH WITH $CNSTNT_PATH=flag MOVE AWAY 1',decl=DECL+' flag:BOOLEAN')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.motion.history),1)

    def test_duplicate_names_reject_across_group_spellings(self):
        for setting in ('$SEG_TIME=1,$GROUP[1].$SEG_TIME=2','$CNSTNT_PATH=TRUE,$CNSTNT_PATH[1]=FALSE'):
            rejected(self,setting)

    def test_cross_group_options_do_not_consume_completion(self):
        rejected(self,'$SEG_TIME[2]=40')

    def test_group_selector_cannot_use_boolean(self):
        with self.assertRaises(TranslationError):program('ATTACH WITH $SEG_TIME[TRUE]=40 MOVE AWAY 1')

    def test_group_selector_and_value_and_operand_run_once_in_order(self):
        routines='ROUTINE grp:INTEGER BEGIN n=n*10+1 RETURN 1 END grp ROUTINE duration:INTEGER BEGIN n=n*10+2 RETURN 40 END duration ROUTINE direction:REAL BEGIN n=n*10+3 RETURN -25.5 END direction ROUTINE distance:REAL BEGIN n=n*10+4 RETURN 1 END distance'
        p,ctx,_=program('n=0 ATTACH WITH $GROUP[grp()].$SEG_TIME=duration(),$CONTAXISVEL=direction() MOVE AWAY distance()',routines=routines)
        self.assertEqual(p.run()['N'],1234);self.assertEqual(values(ctx)['$CONTAXISVEL'],-25.5)

    def test_invalid_later_setting_retains_earlier_source_effect(self):
        p,ctx,_=program('n=0 ATTACH WITH $CNSTNT_PATH=effect(),$ACCU_NUM=11 MOVE AWAY 1',routines='ROUTINE effect:BOOLEAN BEGIN n=n+1 RETURN TRUE END effect')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],len(ctx.motion.history)),(1,1))

    def test_later_expression_cannot_change_captured_integer(self):
        p,ctx,_=program('n=40 ATTACH WITH $SEG_TIME=n,$CNSTNT_PATH=effect() MOVE AWAY 1',routines='ROUTINE effect:BOOLEAN BEGIN n=80 RETURN TRUE END effect')
        self.assertEqual(p.run()['N'],80);self.assertEqual(values(ctx)['$SEG_TIME'],40)

    def test_ownership_is_still_required(self):
        p,ctx,_=program('WITH '+NEW+' MOVE AWAY 1')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.motion.history,[])

    def test_arbitrary_system_variable_reads_and_writes_are_not_added(self):
        for body in ('n=$SEG_TIME','$SEG_TIME=40','n=$GROUP[1].$ACCU_NUM','$GROUP[1].$CONTAXISVEL=10'):
            with self.assertRaises(TranslationError):program(body)

    def test_prefixes_are_not_accepted_as_setting_tokens(self):
        for name in ('$SEG_TIME_EXTRA','$USE_CARTACC2','$CONTAXISVEL_'):
            with self.assertRaises(TranslationError):tokenize('WITH '+name+'=1 MOVE AWAY 1','option.kl')

    def test_unresolved_reference_position_remains_explicitly_blocked(self):
        for value in ('1','p','j','TRUE'):
            with self.assertRaises(TranslationError):program('ATTACH WITH $REF_POS='+value+' MOVE AWAY 1')

    def test_legacy_does_not_gain_motion_options(self):
        with self.assertRaises(TranslationError):translate('PROGRAM T BEGIN WITH '+NEW+' MOVE AWAY 1 END T',mode='legacy')


class MotionOptionScopeTests(unittest.TestCase):
    def test_segment_time_does_not_replace_explicit_completion_delay(self):
        p,ctx,_,sleeps=scoped('ATTACH WITH '+NEW+' MOVE AWAY 1',ctx=scripted(7))
        p.run();self.assertEqual(sleeps,[.007]);self.assertEqual(values(ctx),EXPECTED)

    def test_time_shift_does_not_rewrite_supplied_arrival_schedule(self):
        p,ctx,_,sleeps=scoped('n=0 ATTACH WITH '+NEW+' MOVE AWAY 1, WHEN AT NODE[1] DO n=9 ENDMOVE',ctx=planned(delay=7))
        self.assertEqual((p.run()['N'],sleeps),(9,[.007]));self.assertEqual(values(ctx)['$TIME_SHIFT'],10)

    def test_zero_segment_time_does_not_infer_duration(self):
        p,ctx,_,sleeps=scoped('ATTACH WITH $SEG_TIME=0 MOVE AWAY 1',ctx=scripted(7))
        p.run();self.assertEqual(sleeps,[.007])

    def test_pause_resume_retains_once_captured_options(self):
        p,ctx,_,_=scoped('n=0 ATTACH WITH $SEG_TIME=once(),$CONTAXISVEL=-25.5 MOVE AWAY 1, WHEN TRUE DO PAUSE ENDMOVE',ctx=scripted(7),routines='ROUTINE once:INTEGER BEGIN n=n+1 RETURN 40 END once')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['N'],1);self.assertEqual(values(ctx)['$SEG_TIME'],40);self.assertEqual(ctx.motion._active,{})

    def test_active_scopes_cannot_be_serialized(self):
        p,ctx,_,_=scoped('ATTACH WITH '+NEW+' MOVE AWAY 1, WHEN TRUE DO PAUSE ENDMOVE',ctx=scripted(7))
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaises(ValueError):ctx.to_config()
        p.resume()

    def test_until_cancellation_keeps_metadata_and_releases_ownership(self):
        p,ctx,_,_=scoped('ATTACH WITH '+NEW+' MOVE AWAY 1, UNTIL TRUE ENDMOVE')
        p.run();self.assertEqual(row(ctx)['outcome'],'cancelled');self.assertEqual(ctx.group_locks.owners,{})
        self.assertEqual(values(ctx),EXPECTED)

    def test_abort_cleanup_keeps_admitted_request(self):
        p,ctx,_,_=scoped('ATTACH WITH '+NEW+' MOVE AWAY 1, WHEN TRUE DO ABORT ENDMOVE',ctx=scripted(7))
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual((ctx.motion._active,ctx.group_locks.owners),({},{}));self.assertEqual(values(ctx),EXPECTED)

    def test_delayed_nowait_retains_options_until_terminal_cleanup(self):
        p,ctx,_,_=scoped('ATTACH WITH '+NEW+' MOVE AWAY 1 NOWAIT',ctx=scripted(7),clock_us=lambda:0)
        p.run();self.assertEqual((len(ctx.motion.responses),len(ctx.motion.history)),(0,2))
        self.assertEqual(ctx.motion.history[-1]['outcome'],'cancelled');self.assertEqual(values(ctx),EXPECTED)

    def test_linked_routine_shares_new_motion_option_contract(self):
        main='PROGRAM MAIN ROUTINE work FROM LIB BEGIN ATTACH work RELEASE END MAIN'
        lib='PROGRAM LIB ROUTINE work BEGIN WITH '+NEW+' MOVE AWAY 1 END work BEGIN END LIB'
        ctx=context();translate_project({'main.kl':main,'lib.kl':lib}).instantiate(context=ctx).run('MAIN')
        self.assertEqual(values(ctx),EXPECTED);self.assertEqual(row(ctx)['source_program'],'LIB')

    def test_include_reports_preserve_option_source_locations(self):
        result=translate('PROGRAM T VAR n:INTEGER BEGIN ATTACH\n%INCLUDE options\nRELEASE END T',includes={'options':'WITH $SEG_TIME=40 MOVE AWAY 1'})
        site=result.report['motion_requests'][-2]['settings'][0]
        self.assertEqual(site['name'],'$SEG_TIME');self.assertEqual(site['source_line'],1)
        self.assertEqual(site['source_file'],'options');self.assertTrue(site['include_stack'])


class MotionOptionHistoryTests(unittest.TestCase):
    def test_all_new_values_roundtrip_through_context_json(self):
        _,ctx,_,_=execute('ATTACH WITH '+NEW+' MOVE AWAY 1')
        saved=json.loads(json.dumps(ctx.to_config(),allow_nan=False))
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_twenty_one_settings_roundtrip_through_motion_json(self):
        _,ctx,_,_=execute('ATTACH WITH '+COMPLETE+' MOVE TO p')
        saved=json.loads(json.dumps(ctx.motion.to_config(),allow_nan=False))
        self.assertEqual(rt.MotionRequests.from_config(saved).to_config(),saved)

    def test_integer_history_categories_and_domains_reject(self):
        saved=saved_options()
        for name,upper in [('$ACCEL_OVRD',500),('$ACCU_NUM',10),('$SEG_TIME',100000),('$TIME_SHIFT',10000)]:
            for bad in (True,False,1.0,'1',None,-1,upper+1):
                with self.subTest(name=name,bad=bad),self.assertRaises(ValueError):rt.MotionRequests.from_config(changed(saved,name,bad))

    def test_boolean_history_rejects_truthy_nonbooleans(self):
        saved=saved_options()
        for name in FLAGS:
            for bad in (0,1,1.,'TRUE',None,[]):
                with self.subTest(name=name,bad=bad),self.assertRaises(ValueError):rt.MotionRequests.from_config(changed(saved,name,bad))

    def test_signed_velocity_history_rejects_invalid_values(self):
        saved=saved_options()
        for bad in (-100.01,100.01,True,'-25',None,float('nan'),float('inf'),float('-inf')):
            with self.subTest(bad=bad),self.assertRaises((ValueError,rt.KarelRuntimeError)):rt.MotionRequests.from_config(changed(saved,'$CONTAXISVEL',bad))

    def test_history_wrong_group_and_duplicate_name_reject(self):
        saved=saved_options()
        for change in ('group','duplicate'):
            data=deepcopy(saved);rows=data['history'][-1]['data']['settings']
            if change=='group':rows[0]['group']=2
            else:rows.append(deepcopy(rows[0]))
            with self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_restored_history_is_independent_of_supplied_rows(self):
        saved=saved_options();restored=rt.MotionRequests.from_config(saved)
        saved['history'][-1]['data']['settings'][0]['value']=500
        self.assertEqual(restored.history[-1]['data']['settings'][0]['value'],125)

    def test_unresolved_reference_position_rejects_saved_history(self):
        saved=saved_options();saved['history'][-1]['data']['settings'][0]['name']='$REF_POS'
        with self.assertRaises(ValueError):rt.MotionRequests.from_config(saved)

    def test_direct_scalar_capture_reports_source_line(self):
        for name,value in [('$ACCEL_OVRD',501),('$ACCU_NUM',11),('$SEG_TIME',-1),('$TIME_SHIFT',10001),('$CONTAXISVEL',100.01),('$CNSTNT_PATH',1)]:
            with self.subTest(name=name),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line 7'):
                rt.motion_setting(name,value,('INTEGER',),7)

    def test_nonfinite_direct_velocity_capture_is_rejected(self):
        for value in (float('nan'),float('inf'),float('-inf')):
            with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.motion_setting('$CONTAXISVEL',value,('REAL',),7)

    def test_unknown_direct_capture_remains_rejected(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.motion_setting('$REF_POS',1,('INTEGER',),7)

    def test_report_records_portable_domains_and_unresolved_name(self):
        _,_,_,result=execute('ATTACH WITH '+NEW+' MOVE AWAY 1')
        p=result.report['motion_setting_policy']
        self.assertEqual(p['maximum'],21);self.assertEqual(p['integer_options']['$ACCEL_OVRD'],[0,500])
        self.assertEqual(p['unresolved_options'],['$REF_POS']);self.assertIn('milliseconds',p['time_options'])
        self.assertFalse(p['controller_validated']);json.dumps(result.report,allow_nan=False)


if __name__=='__main__':unittest.main()
