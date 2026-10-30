"""Authored request-local deceleration/acceleration intent and admission guards."""
from copy import deepcopy
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_motion_settings import ALL,row,values,rejected
from tests.test_motion_requests import program,execute,context,DECL
from tests.test_motion_handlers import program as scoped,scripted
from tests.test_motion_timeline import planned

BOTH='$DECELTOL=50,$USEMAXACCEL=TRUE'


class MotionDecelerationTests(unittest.TestCase):
    def test_percentage_endpoints_and_unspecified_zero_intent(self):
        for n in (0,1,50,99):
            _,ctx,_,_=execute('ATTACH WITH $DECELTOL='+str(n)+' MOVE AWAY 1');self.assertEqual(values(ctx)['$DECELTOL'],n)

    def test_every_percentage_is_accepted_as_integer_metadata(self):
        ctx=context(limit=128)
        for n in range(100):
            _,ctx,_,_=execute('ATTACH WITH $DECELTOL='+str(n)+' MOVE AWAY 1 RELEASE',ctx=ctx)
            self.assertEqual(next(x for x in reversed(ctx.motion.history) if x['operation']=='MOVE AWAY')['data']['settings'][0]['value'],n)

    def test_exact_boolean_acceleration_intents(self):
        for word,expected in [('TRUE',True),('FALSE',False)]:
            _,ctx,_,_=execute('ATTACH WITH $USEMAXACCEL='+word+' MOVE AWAY 1');self.assertIs(values(ctx)['$USEMAXACCEL'],expected)

    def test_eleven_distinct_settings_share_one_move(self):
        _,ctx,_,_=execute('ATTACH WITH '+ALL+','+BOTH+' MOVE TO p');self.assertEqual(len(values(ctx)),11)

    def test_checked_dynamic_narrow_percentage(self):
        for kind in ('INTEGER','BYTE','SHORT'):
            _,ctx,_,_=execute('ATTACH work(99)',routines=f'ROUTINE work(n:{kind}) BEGIN WITH $DECELTOL=n MOVE AWAY 1 END work')
            self.assertEqual(values(ctx)['$DECELTOL'],99)

    def test_wrong_percentage_domains_preserve_script_and_history(self):
        for n in (-1,100,2147483646):
            with self.subTest(n=n):rejected(self,'$DECELTOL='+str(n))

    def test_scalar_category_checks_remain_exact(self):
        for setting in ('$DECELTOL=1.0','$DECELTOL=TRUE',"$DECELTOL='1'",'$USEMAXACCEL=1','$USEMAXACCEL=0.0',"$USEMAXACCEL='TRUE'"):
            with self.subTest(setting=setting),self.assertRaises(TranslationError):program('ATTACH WITH '+setting+' MOVE AWAY 1')

    def test_uninitialized_intent_fails_before_publication(self):
        p,ctx,_=program('ATTACH WITH $USEMAXACCEL=flag MOVE AWAY 1',decl=DECL+' flag:BOOLEAN')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual([r['operation'] for r in ctx.motion.history],['ATTACH'])

    def test_duplicate_canonical_setting_rejects_before_publication(self):
        for setting in ('$DECELTOL=1,$GROUP[1].$DECELTOL=2','$USEMAXACCEL=TRUE,$USEMAXACCEL[1]=FALSE'):
            with self.subTest(setting=setting):rejected(self,setting)

    def test_group_qualifications_and_selected_group_two(self):
        _,ctx,_,_=execute('ATTACH WITH $GROUP[2].$DECELTOL=25,$USEMAXACCEL[2]=TRUE MOVE AWAY 1',ctx=context(groups={1:2,2:2}),prefix='%DEFGROUP=2')
        self.assertTrue(all(s['group']==2 for s in row(ctx)['data']['settings']))

    def test_cross_group_setting_rejects_without_consuming_reply(self):
        rejected(self,'$GROUP[2].$DECELTOL=50')

    def test_group_value_and_operand_calls_capture_in_order(self):
        routines='ROUTINE grp:INTEGER BEGIN n=n*10+1 RETURN 1 END grp ROUTINE pct:INTEGER BEGIN n=n*10+2 RETURN 25 END pct ROUTINE flag:BOOLEAN BEGIN n=n*10+3 RETURN TRUE END flag ROUTINE distance:REAL BEGIN n=n*10+4 RETURN 1 END distance'
        p,ctx,_=program('n=0 ATTACH WITH $GROUP[grp()].$DECELTOL=pct(),$USEMAXACCEL=flag() MOVE AWAY distance()',routines=routines)
        self.assertEqual(p.run()['N'],1234);self.assertEqual(values(ctx)['$DECELTOL'],25)

    def test_failed_later_capture_keeps_earlier_source_effects(self):
        p,ctx,_=program('n=0 ATTACH WITH $USEMAXACCEL=flag(),$DECELTOL=100 MOVE AWAY 1',routines='ROUTINE flag:BOOLEAN BEGIN n=n+1 RETURN TRUE END flag')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],1);self.assertEqual(len(ctx.motion.history),1)

    def test_all_move_forms_carry_intents(self):
        for form in ('TO p','NEAR p BY 1','AWAY 1','ABOUT v BY 1','AXIS 1 BY 1','RELATIVE v','ALONG route'):
            _,ctx,_,_=execute('APPEND_NODE(route,s) route[1].node_pos=p ATTACH WITH '+BOTH+' MOVE '+form)
            self.assertEqual(values(ctx),{'$DECELTOL':50,'$USEMAXACCEL':True})

    def test_unspecified_intent_does_not_leak_to_next_move(self):
        _,ctx,_,_=execute('ATTACH WITH '+BOTH+' MOVE AWAY 1 MOVE AWAY 2');self.assertNotIn('settings',row(ctx)['data'])

    def test_immediate_nowait_uses_same_capture(self):
        _,ctx,_,_=execute('ATTACH WITH '+BOTH+' MOVE AWAY 1 NOWAIT');self.assertTrue(row(ctx)['nowait']);self.assertEqual(values(ctx)['$DECELTOL'],50)

    def test_supplied_delay_is_not_computed_from_intent(self):
        p,ctx,_,sleeps=scoped('ATTACH WITH '+BOTH+' MOVE AWAY 1',ctx=scripted(7));p.run();self.assertEqual(sleeps,[.007]);self.assertEqual(values(ctx)['$DECELTOL'],50)

    def test_temporal_arrivals_remain_explicit(self):
        p,ctx,_,sleeps=scoped('n=0 ATTACH WITH '+BOTH+' MOVE AWAY 1, WHEN AT NODE[1] DO n=9 ENDMOVE',ctx=planned(delay=7))
        self.assertEqual((p.run()['N'],sleeps),(9,[.007]));self.assertTrue(values(ctx)['$USEMAXACCEL'])

    def test_pause_resume_retains_values_and_call_count(self):
        p,ctx,_,_=scoped('n=0 ATTACH WITH $DECELTOL=pct(),$USEMAXACCEL=TRUE MOVE AWAY 1, WHEN TRUE DO PAUSE ENDMOVE',ctx=scripted(7),routines='ROUTINE pct:INTEGER BEGIN n=n+1 RETURN 50 END pct')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['N'],1);self.assertEqual(values(ctx)['$DECELTOL'],50);self.assertEqual(ctx.motion._active,{})

    def test_until_cleanup_retains_intents(self):
        p,ctx,_,_=scoped('ATTACH WITH '+BOTH+' MOVE AWAY 1, UNTIL TRUE ENDMOVE');p.run()
        self.assertEqual(row(ctx)['outcome'],'cancelled');self.assertEqual(ctx.group_locks.owners,{})

    def test_abort_cleans_scope_without_discarding_request(self):
        p,ctx,_,_=scoped('ATTACH WITH '+BOTH+' MOVE AWAY 1, WHEN TRUE DO ABORT ENDMOVE',ctx=scripted(7))
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual((ctx.motion._active,ctx.group_locks.owners),({},{}));self.assertEqual(values(ctx)['$DECELTOL'],50)

    def test_nowait_delay_stays_rejected(self):
        p,ctx,_,_=scoped('ATTACH WITH '+BOTH+' MOVE AWAY 1 NOWAIT',ctx=scripted(7))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((len(ctx.motion.responses),len(ctx.motion.history)),(1,1))

    def test_intents_do_not_mutate_robot_context(self):
        from tests.test_joint_interoperability import model_context
        ctx=context();ctx.robot=model_context().robot;before=deepcopy(ctx.robot.to_config())
        execute('ATTACH WITH '+BOTH+' MOVE AWAY 1',ctx=ctx);self.assertEqual(ctx.robot.to_config(),before)

    def test_history_roundtrip_keeps_integer_and_boolean_values(self):
        _,ctx,_,_=execute('ATTACH WITH '+ALL+','+BOTH+' MOVE TO p');saved=json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_invalid_history_percentages_fail_closed(self):
        _,ctx,_,_=execute('ATTACH WITH '+BOTH+' MOVE AWAY 1');saved=ctx.motion.to_config()
        for bad in (True,False,-1,100,1.0,'50',None):
            data=deepcopy(saved);data['history'][-1]['data']['settings'][0]['value']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_invalid_history_acceleration_categories_fail_closed(self):
        _,ctx,_,_=execute('ATTACH WITH '+BOTH+' MOVE AWAY 1');saved=ctx.motion.to_config()
        for bad in (0,1,1.0,'TRUE',None):
            data=deepcopy(saved);data['history'][-1]['data']['settings'][1]['value']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_runtime_capture_rejects_bad_domains_with_source_line(self):
        for name,value in [('$DECELTOL',-1),('$DECELTOL',100),('$DECELTOL',True),('$USEMAXACCEL',1)]:
            with self.subTest(name=name,value=value),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line 7'):
                rt.motion_setting(name,value,('INTEGER',),7)

    def test_report_explains_zero_intent_and_native_boundaries(self):
        _,_,_,r=execute('ATTACH WITH '+BOTH+' MOVE AWAY 1');p=r.report['motion_setting_policy']
        self.assertEqual(p['maximum'],11);self.assertIn('unspecified',p['deceleration']);self.assertIn('BOOLEAN',p['acceleration']);self.assertFalse(p['controller_validated'])

    def test_legacy_still_rejects_motion_source_forms(self):
        from karel2py import translate
        with self.assertRaises(TranslationError):translate('PROGRAM T BEGIN WITH '+BOTH+' MOVE AWAY 1 END T',mode='legacy')

    def test_linked_routine_uses_its_declared_settings(self):
        main='PROGRAM MAIN ROUTINE work FROM LIB BEGIN ATTACH work RELEASE END MAIN'
        lib='PROGRAM LIB ROUTINE work BEGIN WITH '+BOTH+' MOVE AWAY 1 END work BEGIN END LIB'
        ctx=context();translate_project({'main.kl':main,'lib.kl':lib}).instantiate(context=ctx).run('MAIN')
        self.assertEqual(values(ctx)['$DECELTOL'],50)


if __name__=='__main__':unittest.main()
