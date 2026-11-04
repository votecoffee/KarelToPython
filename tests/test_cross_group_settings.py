"""Owned cross-group WITH metadata, FIFO lifetimes and terminal JSON contracts."""
from copy import deepcopy
import json
import unittest
from karel2py import runtime as rt, translate_project
from karel2py.lexer import TranslationError
from tests.test_motion_requests import context, program, execute, DECL, SETUP
from tests.test_motion_options import COMPLETE
from tests.test_queued_motion import bank, run, moves
from tests.test_queued_motion_clauses import terminal, triggered
from tests.test_project_scheduler import source


def enabled(**options):
    return context(groups=options.pop('groups', {1:2,2:2}),cross_group_settings=True,**options)


def rows(ctx):return moves(ctx)[-1]['data']['settings']


def saved():
    _,ctx,_,_=execute('ATTACH WITH $SPEED=25,$SPEED[2]=50 MOVE AWAY 1',ctx=enabled())
    return ctx.motion.to_config()


def qualify(settings,group):
    return ','.join(entry.split('=')[0]+'['+str(group)+']='+entry.split('=',1)[1] for entry in settings.split(','))


class CrossGroupSourceTests(unittest.TestCase):
    def test_same_name_is_independent_per_group(self):
        _,ctx,_,_=execute('ATTACH WITH $SPEED=25,$SPEED[2]=50 MOVE AWAY 1',ctx=enabled())
        self.assertEqual(rows(ctx),[dict(name='$SPEED',group=1,value=25.),dict(name='$SPEED',group=2,value=50.)])

    def test_group_prefix_and_short_form_match(self):
        histories=[]
        for spelling in ('$SPEED[2]','$GROUP[2].$SPEED'):
            _,ctx,_,_=execute('ATTACH WITH '+spelling+'=25 MOVE AWAY 1',ctx=enabled());histories.append(rows(ctx))
        self.assertEqual(*histories)

    def test_unqualified_values_use_source_selected_group(self):
        _,ctx,_,_=execute('ATTACH WITH $SPEED=25,$SPEED[1]=50 MOVE AWAY 1',ctx=enabled(),prefix='%DEFGROUP=2')
        self.assertEqual([r['group'] for r in rows(ctx)],[2,1]);self.assertEqual(moves(ctx)[0]['group'],2)

    def test_all_twenty_one_settings_on_two_groups(self):
        _,ctx,_,_=execute('ATTACH WITH '+COMPLETE+','+qualify(COMPLETE,2)+' MOVE TO p',ctx=enabled())
        self.assertEqual(len(rows(ctx)),42);self.assertEqual({r['group'] for r in rows(ctx)},{1,2})
        self.assertEqual([r['value'] for r in rows(ctx)[:21]],[r['value'] for r in rows(ctx)[21:]])

    def test_all_thirty_one_groups_reach_finite_row_limit(self):
        ctx=enabled(groups={i:2 for i in range(1,32)})
        _,ctx,_,_=execute('ATTACH WITH '+','.join(qualify(COMPLETE,g) for g in range(1,32))+' MOVE TO p',ctx=ctx)
        self.assertEqual(len(rows(ctx)),651);self.assertEqual(len(json.dumps(moves(ctx)[0]['data']).encode('ascii'))<65536,True)
        self.assertEqual(rt.MotionRequests.from_config(ctx.motion.to_config()).to_config(),ctx.motion.to_config())

    def test_all_move_forms_and_via_keep_other_group_metadata(self):
        forms=('MOVE TO p VIA q','MOVE NEAR p BY 1','MOVE AWAY 2','MOVE ABOUT v BY 3','MOVE AXIS 2 BY 4','MOVE RELATIVE v','MOVE ALONG route')
        for statement in forms:
            with self.subTest(statement=statement):
                _,ctx,_,_=execute('APPEND_NODE(route,s) route[1].node_pos=p ATTACH WITH $SPEED[2]=25 '+statement,ctx=enabled())
                self.assertEqual(rows(ctx),[dict(name='$SPEED',group=2,value=25.)]);self.assertEqual(moves(ctx)[0]['group'],1)

    def test_group_value_and_operand_capture_once_in_order(self):
        routines='ROUTINE grp:INTEGER BEGIN n=n*10+1 RETURN 2 END grp ROUTINE val:REAL BEGIN n=n*10+2 RETURN 25.0 END val ROUTINE dist:REAL BEGIN n=n*10+3 RETURN 1.0 END dist'
        state,ctx,_,_=execute('n=0 ATTACH WITH $SPEED[grp()]=val() MOVE AWAY dist()',ctx=enabled(),routines=routines)
        self.assertEqual(state['N'],123);self.assertEqual(rows(ctx)[0]['value'],25.)

    def test_pose_values_detach_before_operand_mutation(self):
        routines='ROUTINE dist:REAL BEGIN p.x=999 RETURN 1.0 END dist'
        _,ctx,_,_=execute('ATTACH WITH $UFRAME[2]=p MOVE AWAY dist()',ctx=enabled(),routines=routines)
        self.assertEqual(rows(ctx)[0]['value']['value']['X'],10.)

    def test_direct_dispatcher_and_cooperative_output(self):
        for label,cooperative in (('',False),('entry:: ',False),('',True)):
            with self.subTest(label=label,cooperative=cooperative):
                state,ctx,_,_=execute(label+'ATTACH WITH $SPEED[2]=25 MOVE AWAY 1 n=7',ctx=enabled(),cooperative=cooperative)
                self.assertEqual(state['N'],7);self.assertEqual(rows(ctx)[0]['group'],2)

    def test_circular_settings_keep_via_rules(self):
        _,ctx,_,_=execute('ATTACH WITH $MOTYPE[2]=CIRCULAR MOVE TO p VIA q',ctx=enabled())
        self.assertEqual(rows(ctx)[0]['value'],'CIRCULAR')

    def test_report_explains_opt_in_and_finite_boundaries(self):
        _,_,_,r=execute('ATTACH WITH $SPEED[2]=25 MOVE AWAY 1',ctx=enabled())
        p=r.report['motion_cross_group_setting_policy'];self.assertIn('before',p['admission']);self.assertIn('651',p['source'])
        self.assertFalse(p['controller_validated']);self.assertEqual(r.report['motion_setting_policy']['maximum_total'],651)
        self.assertTrue(r.report['motion_requests'][1]['settings'][0]['group_qualified']);json.dumps(r.report)


class CrossGroupAdmissionTests(unittest.TestCase):
    def reject(self,settings,*,ctx=None,body='ATTACH',operand='1',routines='',pattern=None):
        ctx=ctx or enabled(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True)])
        p,ctx,_=program(body+' WITH '+settings+' MOVE AWAY '+operand,ctx=ctx,routines=routines)
        with self.assertRaisesRegex(rt.KarelRuntimeError,pattern or '.'):
            p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(moves(ctx),[])
        return p,ctx

    def test_default_service_keeps_cross_group_rejection(self):
        self.reject('$SPEED[2]=25',ctx=context(groups={1:2,2:2},capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True)]),pattern='must match')

    def test_unconfigured_reference_rejects(self):
        self.reject('$SPEED[3]=25',pattern='configured')

    def test_noncanonical_group_values_reject(self):
        for group in ('0','32','-1'):
            with self.subTest(group=group):self.reject('$SPEED['+group+']=25',pattern='configured')

    def test_unowned_reference_rejects_before_reply(self):
        self.reject('$SPEED[2]=25',body='LOCK_GROUP(1,s)',pattern='attached')

    def test_foreign_reference_is_preserved(self):
        ctx=enabled(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True)])
        foreign,_,_=program('',ctx=ctx,setup='');ctx.group_locks._grant(2,foreign._state)
        self.reject('$SPEED[2]=25',ctx=ctx,body='LOCK_GROUP(1,s)',pattern='another task')
        self.assertIs(ctx.group_locks.owners[2],foreign._state);ctx.group_locks.release_owner(foreign._state)

    def test_same_pair_duplicate_rejects_across_spelling(self):
        self.reject('$SPEED[2]=25,$GROUP[2].$SPEED=50',pattern='duplicate')

    def test_dynamic_groups_that_alias_reject(self):
        self.reject('$SPEED[n]=25,$SPEED[2]=50',body='n=2 ATTACH',pattern='duplicate')

    def test_unqualified_selected_group_alias_rejects(self):
        self.reject('$SPEED=25,$SPEED[1]=50',pattern='duplicate')

    def test_invalid_late_enum_preserves_prior_expression_effect(self):
        p,_=self.reject('$SPEED[2]=val(),$TERMTYPE[2]=99',body='n=0 ATTACH',routines='ROUTINE val:REAL BEGIN n=7 RETURN 25.0 END val')
        self.assertEqual(p.snapshot()['N'],7)

    def test_bad_reference_preserves_operand_effect(self):
        p,_=self.reject('$SPEED[3]=25',body='n=0 ATTACH',operand='dist()',routines='ROUTINE dist:REAL BEGIN n=7 RETURN 1.0 END dist')
        self.assertEqual(p.snapshot()['N'],7)

    def test_cross_group_circular_without_via_rejects(self):
        self.reject('$MOTYPE[2]=CIRCULAR',pattern='VIA')

    def test_reference_may_be_held_and_logically_busy(self):
        ctx=enabled();ctx.group_locks.motion[2]='executing';ctx.group_locks.held.add(2)
        execute('LOCK_GROUP(3,s) WITH $SPEED[2]=25 MOVE AWAY 1',ctx=ctx)
        self.assertEqual(ctx.group_locks.motion,{2:'executing'});self.assertEqual(ctx.group_locks.held,{2})

    def test_selected_group_hold_still_rejects(self):
        ctx=enabled(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True)]);ctx.group_locks.held.add(1)
        self.reject('$SPEED[2]=25',ctx=ctx,body='LOCK_GROUP(3,s)',pattern='without a hold')

    def test_selected_group_busy_still_rejects(self):
        ctx=enabled(capture_only=False,responses=[dict(operation='MOVE AWAY',completed=True)])
        ctx.group_locks.motion[1]='executing'
        self.reject('$SPEED[2]=25',ctx=ctx,body='LOCK_GROUP(3,s)',pattern='idle logical group')


class CrossGroupScopeTests(unittest.TestCase):
    def configured(self,*delays,**options):return bank(*delays,groups={1:2,2:2},cross_group_settings=True,**options)

    def test_delayed_nowait_changes_only_selected_group(self):
        seen=[];ctx=self.configured(20)
        p,ctx,_,_=run('ATTACH WITH $SPEED[2]=25 MOVE AWAY 1 NOWAIT inspect() DELAY 20',ctx=ctx,routines='ROUTINE inspect FROM HOST')
        ctx.externals['HOST','INSPECT']=lambda:seen.append(dict(ctx.group_locks.motion));p.run()
        self.assertEqual(seen,[{1:'executing'}]);self.assertEqual(terminal(ctx),['completed'])

    def test_reference_release_after_admission_does_not_fail_scope(self):
        ctx=self.configured(20)
        p,ctx,_,_=run('ATTACH WITH $SPEED[2]=25 MOVE AWAY 1 NOWAIT unlock() DELAY 20',ctx=ctx,routines='ROUTINE unlock FROM HOST')
        def unlock():self.assertEqual(ctx.group_locks.update(p._state,'UNLOCK_GROUP',2),0)
        ctx.externals['HOST','UNLOCK']=unlock
        p.run();self.assertEqual(terminal(ctx),['completed'])

    def test_reference_foreign_regrant_does_not_steal_or_fail_selected_scope(self):
        ctx=self.configured(20);foreign,_,_=program('',ctx=ctx,setup='')
        p,ctx,_,_=run('ATTACH WITH $SPEED[2]=25 MOVE AWAY 1 NOWAIT change() DELAY 20',ctx=ctx,routines='ROUTINE change FROM HOST')
        def change():
            ctx.group_locks.update(p._state,'UNLOCK_GROUP',2);ctx.group_locks._grant(2,foreign._state)
        ctx.externals['HOST','CHANGE']=change;p.run();self.assertEqual(terminal(ctx),['completed'])
        self.assertIs(ctx.group_locks.owners[2],foreign._state);ctx.group_locks.release_owner(foreign._state)

    def test_waiting_job_keeps_captured_other_group_values(self):
        ctx=self.configured(10,20)
        p,ctx,_,_=run('n=25 ATTACH MOVE AWAY 1 NOWAIT\nWITH $SPEED[2]=n MOVE AWAY 2 NOWAIT n=99 DELAY 30',ctx=ctx)
        p.run();self.assertEqual(rows(ctx)[0]['value'],25.);self.assertEqual(terminal(ctx),['completed']*2)

    def test_queued_blocking_clause_retains_cross_group_metadata(self):
        ctx=self.configured(10,20)
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT\nWITH $SPEED[2]=25 MOVE AWAY 2, WHEN TRUE DO n=7 ENDMOVE',ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertEqual(rows(ctx)[0]['group'],2);self.assertEqual(triggered(ctx),[[],[1]])

    def test_queued_nowait_clause_retains_other_group_values(self):
        ctx=self.configured(10,20)
        p,ctx,_,_=run('n=0 ATTACH MOVE AWAY 1 NOWAIT\nWITH $SPEED[2]=25 MOVE AWAY 2 NOWAIT, WHEN TRUE DO n=7 ENDMOVE DELAY 30 s=7',ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertEqual(triggered(ctx),[[],[1]])

    def test_until_cancels_selected_scope_without_other_group_label_change(self):
        ctx=self.configured(20)
        p,ctx,_,_=run('n=0 ATTACH WITH $SPEED[2]=25 MOVE AWAY 1, UNTIL TRUE THEN n=7 ENDMOVE',ctx=ctx)
        self.assertEqual(p.run()['N'],7);self.assertEqual(terminal(ctx),['cancelled']);self.assertEqual(ctx.group_locks.motion,{})

    def test_pause_and_resume_keep_detached_settings(self):
        ctx=self.configured(20)
        p,ctx,_,_=run('n=0 ATTACH WITH $SPEED[2]=25 MOVE AWAY 1, WHEN TRUE DO PAUSE n=7 ENDMOVE',ctx=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(rows(ctx)[0]['value'],25.);self.assertEqual(p.resume()['N'],7);self.assertEqual(terminal(ctx),['completed'])

    def test_rejected_queued_reference_leaves_reply_and_completed_arguments(self):
        ctx=self.configured(10,20)
        p,ctx,_,_=run('ATTACH MOVE AWAY 1 NOWAIT\nWITH $SPEED[3]=25 MOVE AWAY 2',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'configured'):p.run()
        self.assertEqual(len(ctx.motion.responses),1);self.assertEqual(len(moves(ctx)),1)

    def test_save_of_active_scope_remains_rejected(self):
        ctx=self.configured(20)
        p,ctx,_,_=run('ATTACH WITH $SPEED[2]=25 MOVE AWAY 1 NOWAIT save()',ctx=ctx,routines='ROUTINE save FROM HOST')
        def save():
            with self.assertRaisesRegex(ValueError,'active motion'):ctx.motion.to_config()
        ctx.externals['HOST','SAVE']=save;p.run()

    def test_linked_source_group_uses_calling_root_ownership(self):
        ctx=enabled();docs={'main':source('MAIN','ATTACH work()',routines='ROUTINE work FROM LIB'),
             'lib':source('LIB','',routines='ROUTINE work BEGIN WITH $SPEED[1]=25,$SPEED=50 MOVE AWAY 1 END work').replace('PROGRAM LIB','PROGRAM LIB\n%DEFGROUP=2\n')}
        linked=translate_project(docs).instantiate(context=ctx);linked.run('MAIN')
        self.assertEqual([(r['group'],r['value']) for r in rows(ctx)],[(1,25.),(2,50.)]);self.assertEqual(moves(ctx)[0]['program'],'MAIN')


class CrossGroupPersistenceTests(unittest.TestCase):
    def test_exact_bool_configuration(self):
        for value in (0,1,None,[],{},'true'):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'BOOLEAN'):rt.MotionRequests({1:2},cross_group_settings=value)

    def test_disabled_default_is_omitted(self):
        self.assertNotIn('cross_group_settings',context().motion.to_config())
        self.assertNotIn('cross_group_settings',rt.MotionRequests.from_config(dict(groups={'1':2},cross_group_settings=False)).to_config())

    def test_enabled_flag_and_cross_group_history_round_trip(self):
        data=saved();self.assertIs(data['cross_group_settings'],True)
        self.assertEqual(rt.MotionRequests.from_config(json.loads(json.dumps(data))).to_config(),data)

    def test_loading_cross_group_history_requires_opt_in(self):
        for value in ('omit',False):
            data=saved()
            if value=='omit':del data['cross_group_settings']
            else:data['cross_group_settings']=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'must match'):rt.MotionRequests.from_config(data)

    def test_loading_duplicate_pair_rejects(self):
        data=saved();data['history'][-1]['data']['settings'].append(deepcopy(data['history'][-1]['data']['settings'][1]))
        with self.assertRaisesRegex(ValueError,'duplicate'):rt.MotionRequests.from_config(data)

    def test_loading_unknown_group_rejects(self):
        data=saved();data['history'][-1]['data']['settings'][1]['group']=3
        with self.assertRaisesRegex(ValueError,'configured'):rt.MotionRequests.from_config(data)

    def test_history_group_requires_exact_integer(self):
        for value in (True,2.0,'2',None,[],{}):
            data=saved();data['history'][-1]['data']['settings'][1]['group']=value
            with self.subTest(value=value),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_history_names_and_value_domains_remain_checked(self):
        for name,value in (('$REF_POS',1),('$SPEED',-1),('$SPEED',True),('$TERMTYPE','STRAIGHT'),('$MOTYPE','CIRCULAR')):
            data=saved();data['history'][-1]['data']['settings'][1].update(name=name,value=value)
            with self.subTest(name=name,value=value),self.assertRaises(ValueError):rt.MotionRequests.from_config(data)

    def test_history_rows_must_fit_configured_capacity(self):
        data=saved();data['history'][-1]['data']['settings']*=22
        with self.assertRaisesRegex(ValueError,'1..42'):rt.MotionRequests.from_config(data)

    def test_saved_data_is_detached_both_directions(self):
        data=saved();restored=rt.MotionRequests.from_config(data);data['history'][-1]['data']['settings'][1]['value']=99
        output=restored.to_config();self.assertEqual(output['history'][-1]['data']['settings'][1]['value'],50.)
        output['history'][-1]['data']['settings'][1]['value']=77;self.assertEqual(restored.to_config()['history'][-1]['data']['settings'][1]['value'],50.)

    def test_context_json_replay_retains_enabled_service(self):
        _,ctx,_,_=execute('ATTACH WITH $SPEED[2]=25 MOVE AWAY 1 RELEASE',ctx=enabled())
        data=ctx.to_config();self.assertEqual(rt.ExecutionContext.from_config(json.loads(json.dumps(data))).to_config(),data)
