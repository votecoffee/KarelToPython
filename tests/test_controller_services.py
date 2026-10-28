"""Authored logical controller calls and explicit panel-I/O regressions."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


def context(**options):return rt.ExecutionContext(controller=rt.ControllerServices(**options),group_locks=rt.GroupLocks([1,2,3]))


def execute(body,*,ctx=None,decl='s,n:INTEGER owned,ok:BOOLEAN',prefix='',**options):
    ctx=ctx or context()
    if 'JOINTPOS' in decl:options.setdefault('joint_axes',6)
    p,result=compile_program(body,decl=decl,prefix=prefix,context=ctx,sleep=lambda _:None,**options)
    return p.run(),ctx,p,result


class MotionOwnershipTests(unittest.TestCase):
    def test_query_before_and_after_explicit_lock(self):
        values,ctx,_,_=execute('owned=MOTION_CTL(1) LOCK_GROUP(1,s) ok=MOTION_CTL()')
        self.assertEqual((values['OWNED'],values['OK']),(False,True));self.assertEqual(ctx.group_locks.owners,{})

    def test_bare_query_and_directive_default_mask(self):
        values,ctx,_,_=execute('LOCK_GROUP(5,s) owned=MOTION_CTL',prefix='%LOCKGROUP=1,3')
        self.assertTrue(values['OWNED']);self.assertEqual(ctx.controller.history[-1]['data']['mask'],5)

    def test_nolock_default_has_no_control_even_with_explicit_locks(self):
        values,_,_,_=execute('LOCK_GROUP(1,s) owned=MOTION_CTL ok=MOTION_CTL(1)',prefix='%NOLOCKGROUP')
        self.assertEqual((values['OWNED'],values['OK']),(False,True))

    def test_default_group_uses_source_group_selection(self):
        values,ctx,_,_=execute('LOCK_GROUP(2,s) owned=MOTION_CTL',prefix='%DEFGROUP=2')
        self.assertTrue(values['OWNED']);self.assertEqual(ctx.controller.history[-1]['data']['mask'],2)

    def test_query_requires_every_selected_group(self):
        values,_,_,_=execute('LOCK_GROUP(1,s) owned=MOTION_CTL(3) LOCK_GROUP(2,s) ok=MOTION_CTL(3)')
        self.assertEqual((values['OWNED'],values['OK']),(False,True))

    def test_invalid_masks_fail_without_fabricating_false(self):
        for mask in (-1,8):
            ctx=context();p,_=compile_program(f'owned=TRUE owned=MOTION_CTL({mask})',decl='owned:BOOLEAN',context=ctx)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'unconfigured'):p.run()
            self.assertTrue(p.snapshot()['OWNED']);self.assertEqual(ctx.controller.sequence,0)

    def test_cancel_only_own_stopped_groups(self):
        ctx=context();ctx.group_locks.set_motion(1,'stopped');ctx.group_locks.set_motion(2,'executing');ctx.group_locks.set_motion(3,'stopped')
        other,_=compile_program('',context=ctx);ctx.group_locks.update(other._state,'LOCK_GROUP',4)
        values,_,_,_=execute('LOCK_GROUP(3,s) CNCL_STP_MTN UNLOCK_GROUP(1,s)',ctx=ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.group_locks.motion,{2:'executing',3:'stopped'})
        self.assertIs(ctx.group_locks.owners[3],other._state);ctx.group_locks.release_owner(other._state)

    def test_cancel_idle_is_a_successful_noop(self):
        _,ctx,_,_=execute('CNCL_STP_MTN CNCL_STP_MTN()')
        self.assertEqual([row['data']['groups'] for row in ctx.controller.history],[[],[]])

    def test_missing_explicit_services_fail_closed(self):
        for ctx,pattern in [(rt.ExecutionContext(),'controller'),(rt.ExecutionContext(controller=rt.ControllerServices()),'group_locks')]:
            with self.subTest(pattern=pattern),self.assertRaisesRegex(rt.KarelRuntimeError,pattern):execute('owned=MOTION_CTL',ctx=ctx)

    def test_sequence_exhaustion_preserves_motion_label(self):
        ctx=context(sequence=2147483646);ctx.group_locks.set_motion(1,'stopped');p,_=compile_program('LOCK_GROUP(1,s) CNCL_STP_MTN',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'):p.run()
        self.assertEqual(ctx.group_locks.motion,{1:'stopped'})

    def test_nested_routine_keeps_calling_root_ownership(self):
        ctx=context();ctx.group_locks.set_motion(1,'stopped')
        instance=translate_project({'main':source('MAIN','LOCK_GROUP(1,s) clear_stopped() UNLOCK_GROUP(1,s)',routines='ROUTINE clear_stopped FROM LIB'),
            'lib':source('LIB','',routines='ROUTINE clear_stopped BEGIN CNCL_STP_MTN END clear_stopped')}).instantiate(context=ctx)
        result=instance.run('MAIN');self.assertEqual(result['MAIN']['values']['S'],0)
        self.assertEqual(ctx.controller.history[0]['program'],'MAIN');self.assertEqual(ctx.group_locks.motion,{})


PERCH_DECL='j:JOINTPOS6 axes,tolerance:ARRAY[6] OF REAL i,s:INTEGER'
PERCH_SETUP='FOR i=1 TO 6 DO axes[i]=i*1.0 tolerance[i]=0.1 ENDFOR CNV_REL_JPOS(axes,j,s) '


class PerchTests(unittest.TestCase):
    def test_store_detached_six_axis_reference_and_tolerances(self):
        values,ctx,_,_=execute(PERCH_SETUP+'SET_PERCH(j,tolerance,2) tolerance[1]=4',decl=PERCH_DECL,ctx=context(perch_counts={1:3}))
        self.assertEqual(ctx.controller.perches[1,2],dict(joints=[1.,2.,3.,4.,5.,6.],tolerance=[.1]*6))
        self.assertEqual(values['TOLERANCE'][0],4.)

    def test_group_qualified_joint_selects_single_source_group(self):
        _,ctx,_,_=execute(PERCH_SETUP+'SET_PERCH(j,tolerance,1)',decl=PERCH_DECL.replace('JOINTPOS6','JOINTPOS6 IN GROUP[2]'),ctx=context(perch_counts={2:1}))
        self.assertIn((2,1),ctx.controller.perches)

    def test_explicit_default_group_policy_selects_bank(self):
        _,ctx,_,_=execute(PERCH_SETUP+'SET_PERCH(j,tolerance,1)',decl=PERCH_DECL,ctx=context(perch_counts={3:1}),prefix='%DEFGROUP=3')
        self.assertIn((3,1),ctx.controller.perches)

    def test_bad_index_negative_tolerance_and_missing_values_preserve_bank(self):
        for setup,call in [(PERCH_SETUP,'SET_PERCH(j,tolerance,0)'),(PERCH_SETUP+'tolerance[6]=-1 ','SET_PERCH(j,tolerance,1)'),
            ('','SET_PERCH(j,tolerance,1)')]:
            ctx=context(perch_counts={1:2})
            with self.subTest(call=call),self.assertRaises(rt.KarelRuntimeError):execute(setup+call,decl=PERCH_DECL,ctx=ctx)
            self.assertEqual(ctx.controller.perches,{})

    def test_wrong_tolerance_shape_and_joint_width_are_rejected(self):
        for decl in (PERCH_DECL.replace('ARRAY[6]','ARRAY[5]'),PERCH_DECL.replace('JOINTPOS6','JOINTPOS7')):
            ctx=context(perch_counts={1:1})
            with self.subTest(decl=decl),self.assertRaises(rt.KarelRuntimeError):execute('SET_PERCH(j,tolerance,1)',decl=decl,ctx=ctx)
            self.assertEqual(ctx.controller.perches,{})

    def test_perch_bank_roundtrip_has_no_live_aliases(self):
        _,ctx,_,_=execute(PERCH_SETUP+'SET_PERCH(j,tolerance,1)',decl=PERCH_DECL,ctx=context(perch_counts={1:1}))
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        config['controller']['perches']['1:1']['joints'][0]=99
        self.assertEqual(restored.controller.perches[1,1]['joints'][0],1.)


class ScriptedResetTests(unittest.TestCase):
    def test_acknowledgement_does_not_claim_faults_cleared(self):
        ctx=context(resets=[dict(completed=False,fault=True)]);ctx.ports=rt.PortBank({'OPOUT':3})
        values,_,_,_=execute('RESET(ok) owned=OPOUT[3]',ctx=ctx)
        self.assertTrue(values['OK']);self.assertTrue(values['OWNED']);self.assertFalse(ctx.controller.history[-1]['data']['completed'])

    def test_successful_response_applies_explicit_fault_result(self):
        ctx=context(resets=[dict(completed=True,fault=False)]);ctx.ports=rt.PortBank({'OPOUT':3},{('OPOUT',3):True})
        values,_,_,_=execute('RESET(ok) owned=OPOUT[3]',ctx=ctx)
        self.assertTrue(values['OK']);self.assertFalse(values['OWNED'])

    def test_delay_is_budgeted_and_does_not_generate_a_pause_notification(self):
        body='n=0 CONDITION[1]: WHEN PAUSE DO n=n+1 ENDCONDITION ENABLE CONDITION[1] RESET(ok)'
        values,ctx,_,_=execute(body,ctx=context(resets=[dict(completed=True,delay_ms=25)]))
        self.assertEqual((values['N'],values['OK'],ctx.controller.elapsed_ms),(0,True,25))

    def test_remaining_plans_are_consumed_once_and_persisted(self):
        values,ctx,_,_=execute('RESET(ok)',ctx=context(resets=[dict(completed=True),dict(completed=False)]))
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        execute('RESET(ok)',ctx=restored);self.assertEqual(restored.controller.resets,[])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit scripted'):execute('RESET(ok)',ctx=restored)

    def test_missing_fault_port_preserves_plan_clock_and_output(self):
        ctx=context(resets=[dict(completed=True,fault=False,delay_ms=10)]);p,_=compile_program('ok=FALSE RESET(ok)',decl='ok:BOOLEAN',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ports'):p.run()
        self.assertFalse(p.snapshot()['OK']);self.assertEqual((len(ctx.controller.resets),ctx.controller.elapsed_ms,ctx.controller.sequence),(1,0,0))

    def test_missing_response_preserves_output(self):
        ctx=context();p,_=compile_program('ok=FALSE RESET(ok)',decl='ok:BOOLEAN',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertFalse(p.snapshot()['OK']);self.assertEqual(ctx.controller.sequence,0)

    def test_stop_releases_pending_reset_without_replaying_it(self):
        ctx=context(resets=[dict(completed=True,delay_ms=30,fault=False)]);ctx.ports=rt.PortBank({'OPOUT':3},{('OPOUT',3):True})
        p,_=compile_program('ok=FALSE RESET(ok)',decl='ok:BOOLEAN',context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaisesRegex(ValueError,'pending scripted reset'):ctx.to_config()
        ctx.controller.sequence=2147483646;p.stop()
        self.assertFalse(p.snapshot()['OK']);self.assertTrue(ctx.ports.values['OPOUT',3]);self.assertEqual(ctx.controller.resets,[])
        self.assertEqual(ctx.controller.history[-1]['outcome'],'cancelled');ctx.to_config()

    def test_budget_failure_releases_pending_and_preserves_output(self):
        ctx=context(resets=[dict(completed=True,delay_ms=1000)]);p,_=compile_program('ok=FALSE RESET(ok)',decl='ok:BOOLEAN',context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=5)
        self.assertFalse(p.snapshot()['OK']);self.assertFalse(ctx.controller.snapshot()['pending_reset'])
        self.assertEqual(ctx.controller.history[-1]['outcome'],'failed');ctx.to_config()

    def test_bad_reset_output_cannot_consume_response(self):
        for call in ('RESET(TRUE)','RESET(n)'):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(call,decl='n:INTEGER')

    def test_pause_and_resume_finish_the_original_response_once(self):
        ctx=context(resets=[dict(completed=True,delay_ms=25)])
        p,_=compile_program('ok=FALSE RESET(ok)',decl='ok:BOOLEAN',context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        p._state._sleep=lambda _:None;p.resume()
        self.assertTrue(p.snapshot()['OK']);self.assertEqual((ctx.controller.elapsed_ms,ctx.controller.sequence),(25,1));ctx.to_config()

    def test_reset_clock_and_sequence_limits_preflight_before_consuming_plan(self):
        for options in (dict(sequence=2147483646),dict(elapsed_ms=2147483640)):
            ctx=context(resets=[dict(completed=True,delay_ms=25)],**options)
            with self.subTest(options=options),self.assertRaises(rt.KarelRuntimeError):execute('RESET(ok)',ctx=ctx)
            self.assertEqual(len(ctx.controller.resets),1);self.assertFalse(ctx.controller.snapshot()['pending_reset'])

    def test_competing_reset_does_not_cancel_or_borrow_first_request(self):
        ctx=context(resets=[dict(completed=True,delay_ms=100),dict(completed=False)])
        instance=translate_project({'a':source('A','RESET(ok)',decl='ok:BOOLEAN'),'b':source('B','RESET(ok)',decl='ok:BOOLEAN')}).instantiate(context=ctx)
        instance.scheduler.start('A');instance.scheduler.start('B')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already pending'):instance.scheduler.run()
        self.assertTrue(ctx.controller.snapshot()['pending_reset']);self.assertEqual(len(ctx.controller.resets),1)
        instance.scheduler.stop('A');self.assertEqual(ctx.controller.history[0]['outcome'],'cancelled');ctx.to_config()


def project(main,bg='IF UNINIT(count) THEN count=0 ENDIF WHILE NOT done DO count=count+1 DELAY 2 ENDWHILE',*,ctx=None,bg_prefix=''):
    ctx=ctx or context(background={1:'BG'})
    main_decl='s,before,paused,later:INTEGER count FROM BG:INTEGER done:BOOLEAN'
    return translate_project({'main':source('MAIN',main,decl=main_decl),
        'bg':f'PROGRAM BG\n{bg_prefix}\nVAR count:INTEGER done FROM MAIN:BOOLEAN BEGIN {bg} END BG'}).instantiate(context=ctx)


class BackgroundSlotTests(unittest.TestCase):
    def test_start_suspend_resume_and_complete_attached_task(self):
        body='done=FALSE MIXBG_RUN(1,s) DELAY 10 before=count MIXBG_STOP(1,s) DELAY 10 paused=count DELAY 10 later=count MIXBG_RUN(1,s) DELAY 10 done=TRUE'
        instance=project(body);result=instance.run('MAIN');values=result['MAIN']['values']
        self.assertEqual(values['S'],0);self.assertEqual(values['PAUSED'],values['LATER']);self.assertGreater(result['BG']['values']['COUNT'],values['PAUSED'])
        self.assertEqual(result['BG']['state'],'completed');instance.context.to_config()
        self.assertEqual([r['data']['action'] for r in instance.context.controller.history],['started','pause_requested','resumed'])

    def test_stop_then_run_before_checkpoint_cancels_pending_pause(self):
        instance=project('done=FALSE MIXBG_RUN(1,s) MIXBG_STOP(1,s) MIXBG_RUN(1,s) DELAY 10 done=TRUE')
        result=instance.run('MAIN');self.assertEqual(result['MAIN']['values']['S'],0);self.assertEqual(result['BG']['state'],'completed')

    def test_start_completed_task_again_retains_globals(self):
        instance=project('MIXBG_RUN(1,s) DELAY 10 MIXBG_RUN(1,s) DELAY 10',bg='IF UNINIT(count) THEN count=0 ENDIF count=count+1')
        self.assertEqual(instance.run('MAIN')['BG']['values']['COUNT'],2)

    def test_already_running_request_is_idempotent(self):
        instance=project('done=FALSE MIXBG_RUN(1,s) MIXBG_RUN(1,s) DELAY 5 done=TRUE');result=instance.run('MAIN')
        self.assertEqual(result['MAIN']['values']['S'],0);self.assertEqual(instance.context.controller.history[1]['data']['action'],'running')

    def test_unstarted_stop_does_not_execute_target(self):
        instance=project('MIXBG_STOP(1,s)');result=instance.run('MAIN')
        self.assertEqual((result['MAIN']['values']['S'],result['BG']['state']),(0,'ready'));instance.context.to_config()

    def test_unconfigured_slot_and_self_target_return_checked_status(self):
        for ctx,slot,expected in [(context(background={1:'BG'}),2,1),(context(background={1:'MAIN'}),1,2)]:
            result=project(f'MIXBG_RUN({slot},s)',ctx=ctx).run('MAIN');self.assertEqual(result['MAIN']['values']['S'],expected)

    def test_pause_mask_is_honored(self):
        instance=project('done=FALSE MIXBG_RUN(1,s) DELAY 5 MIXBG_STOP(1,s) done=TRUE',bg_prefix='%NOPAUSE=COMMAND')
        result=instance.run('MAIN');self.assertEqual(result['MAIN']['values']['S'],4);self.assertEqual(result['BG']['state'],'completed')

    def test_stopped_task_is_not_silently_restarted(self):
        instance=project('MIXBG_RUN(1,s)');instance.scheduler.stop('BG');result=instance.run('MAIN')
        self.assertEqual((result['MAIN']['values']['S'],result['BG']['state']),(3,'stopped'))

    def test_active_background_task_prevents_saved_execution_links(self):
        instance=project('done=FALSE MIXBG_RUN(1,s) MIXBG_STOP(1,s)');result=instance.run('MAIN')
        self.assertEqual(result['BG']['state'],'paused')
        with self.assertRaisesRegex(ValueError,'active background'):instance.context.to_config()
        instance.scheduler.stop('BG');instance.context.to_config()

    def test_slot_tracks_renamed_live_and_completed_task_identity(self):
        for body in ('count=1','IF UNINIT(count) THEN count=0 ENDIF WHILE NOT done DO count=count+1 DELAY 2 ENDWHILE'):
            instance=project("done=FALSE MIXBG_RUN(1,s) DELAY 5 SET_TSK_NAME('BG','RENAMED',s) MIXBG_STOP(1,s) DELAY 5 MIXBG_RUN(1,s) done=TRUE",bg=body)
            result=instance.run('MAIN');self.assertEqual(result['MAIN']['values']['S'],0);self.assertEqual(result['RENAMED']['state'],'completed')

    def test_background_calls_guard_active_for_counters_directly_and_transitively(self):
        for call in ('MIXBG_RUN(1,s)','MIXBG_STOP(1,s)'):
            for routine in (False,True):
                with self.subTest(call=call,routine=routine),self.assertRaises(TranslationError):
                    compile_program('FOR n=1 TO 2 DO '+('go()' if routine else call)+' ENDFOR',routines='ROUTINE go BEGIN '+call+' END go' if routine else '')

    def test_background_slots_require_scheduler_and_explicit_bindings(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'TaskScheduler'):execute('MIXBG_RUN(1,s)',ctx=context(background={1:'BG'}))

    def test_foreign_execution_context_is_not_adopted(self):
        ctx=context(background={1:'BG'});ctx.tasks=rt.TaskScheduler()
        target,_=compile_program('n=1',cooperative=True);ctx.tasks.bind('BG',target)
        values,_,_,_=execute('MIXBG_RUN(1,s)',ctx=ctx)
        self.assertEqual(values['S'],2);self.assertEqual(target.task_state,'ready')

    def test_pending_abort_is_not_overridden_by_background_run(self):
        instance=project('done=FALSE MIXBG_RUN(1,s) DELAY 5')
        instance.scheduler.start('BG');target=instance.programs['BG'];rt.request_task_control(target._state,'ABORT')
        status=rt.Reference(('INTEGER',),{'value':0},'value')
        instance.context.controller.background_call(instance.programs['MAIN']._state,'MIXBG_RUN',[1,status],None)
        self.assertEqual(status.raw(),3);instance.scheduler.stop('BG')

    def test_sequence_exhaustion_does_not_start_target(self):
        ctx=context(background={1:'BG'},sequence=2147483646);instance=project('MIXBG_RUN(1,s)',ctx=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'):instance.run('MAIN')
        self.assertEqual(instance.programs['BG'].task_state,'ready')


class PanelPortTests(unittest.TestCase):
    def test_zero_based_panel_ports_and_existing_one_based_ports(self):
        ctx=context();ctx.ports=rt.PortBank({'OPIN':1,'OPOUT':3,'TPIN':1,'TPOUT':1,'DIN':1},
            {('OPIN',0):True,('TPIN',0):False,('DIN',1):True})
        values,_,_,_=execute('owned=OPIN[0] OPOUT[0]=owned TPOUT[0]=NOT TPIN[0] ok=DIN[1]',ctx=ctx)
        self.assertTrue(values['OWNED']);self.assertTrue(ctx.ports.values['OPOUT',0]);self.assertTrue(ctx.ports.values['TPOUT',0])
        for kind in ('DIN','DOUT','GIN','GOUT','AIN','AOUT','RDI','RDO'):
            with self.subTest(kind=kind),self.assertRaises(rt.KarelRuntimeError):rt.PortBank({kind:1}).update(kind,0,False)

    def test_unsimulated_panel_input_remains_protected(self):
        ctx=context();ctx.ports=rt.PortBank({'OPIN':1})
        with self.assertRaises(TranslationError):execute('OPIN[0]=TRUE',ctx=ctx)

    def test_zero_port_values_comments_and_simulation_roundtrip(self):
        ctx=context();ctx.ports=rt.PortBank({'OPIN':1,'OPOUT':3},{('OPIN',0):False,('OPOUT',3):True},
            simulated=[('OPIN',0)],comments={('OPIN',0):'zero'})
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(restored.to_config(),config);self.assertEqual(restored.ports.comments['OPIN',0],'zero')

    def test_indirect_panel_access_uses_explicit_type_code(self):
        ctx=context();ctx.ports=rt.PortBank({'OPOUT':3},type_codes={10:'OPOUT'})
        values,_,_,_=execute('SET_PORT_VAL(10,0,TRUE,s) GET_PORT_VAL(10,0,owned,s)',ctx=ctx)
        self.assertTrue(values['OWNED']);self.assertEqual(values['S'],0)

    def test_panel_zero_mode_configuration_roundtrip(self):
        config=dict(modes=[dict(kind='OPOUT',number=0,mask=0)])
        bank=rt.PortBank({'OPOUT':3},configuration=config)
        restored=rt.ExecutionContext.from_config(rt.ExecutionContext(ports=bank).to_config())
        self.assertEqual(restored.ports.configuration['modes'],config['modes'])
        with self.assertRaises(ValueError):rt.PortBank({'OPOUT':3},configuration=dict(modes=[dict(kind=[],number=0,mask=0)]))

    def test_zero_panel_field_works_in_forms(self):
        from tests.test_forms import context as form_context,execute as form_execute,ftx,SETUP
        ctx=form_context(ftx('"-%4P"'),keys=('F4','F3'),ports=rt.PortBank({'OPOUT':3},{('OPOUT',0):False}))
        values,_,_,_=form_execute(ctx=ctx,setup=SETUP+" values[1]='OPOUT[0]'")
        self.assertTrue(ctx.ports.values['OPOUT',0]);self.assertEqual(values['STATUS'],0)

    def test_zero_panel_cell_works_in_tables(self):
        from tests.test_table_controls import context as table_context,execute as table_execute,TABLE
        ctx=table_context(('RIGHT','ENTER','SELECT'),ports=rt.PortBank({'OPOUT':3},{('OPOUT',0):False,('OPOUT',1):False}))
        values,_,_,_=table_execute("cols[2].item_type=TPX_PBL_ITEM words[1]='OPOUT[0]' words[2]='OPOUT[1]' "+TABLE,ctx=ctx)
        self.assertTrue(ctx.ports.values['OPOUT',0]);self.assertEqual(values['S'],0)

    def test_panel_input_zero_can_be_written_through_explicit_simulation(self):
        ctx=context();ctx.ports=rt.PortBank({'OPIN':1},type_codes={11:'OPIN'})
        values,_,_,_=execute('SET_PORT_SIM(11,0,TRUE,s) GET_PORT_VAL(11,0,owned,s)',ctx=ctx)
        self.assertTrue(values['OWNED']);self.assertIn(('OPIN',0),ctx.ports.simulated)


class ControllerPersistenceTests(unittest.TestCase):
    def test_report_records_controller_model_boundaries(self):
        _,_,_,result=execute('owned=MOTION_CTL(0)')
        policy=result.report['controller_policy'];self.assertEqual(set(policy['calls']),rt.CONTROLLER_CALLS)
        self.assertFalse(policy['controller_validated']);self.assertEqual(policy['guide'],'docs/controller-services.md')

    def test_history_ring_is_bounded_and_snapshot_is_detached(self):
        _,ctx,_,_=execute('owned=MOTION_CTL(0) owned=MOTION_CTL(0)',ctx=context(limit=1))
        self.assertEqual(len(ctx.controller.history),1);self.assertEqual(ctx.controller.sequence,2)
        copy=ctx.controller.snapshot();copy['history'][0]['data']['mask']=99
        self.assertEqual(ctx.controller.history[0]['data']['mask'],0)
        rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))

    def test_invalid_configuration_is_rejected(self):
        for config in ({'unknown':0},{'background':{'01':'A'}},{'background':{'1':'A','2':'a'}},{'perch_counts':{'0':1}},
            {'resets':[{'completed':1}]},{'resets':[{'completed':True,'fault':0}]},{'resets':[{'completed':True,'delay_ms':-1}]},
            {'sequence':True},{'elapsed_ms':-1},{'perches':{'1:0':{'joints':[0.]*6,'tolerance':[.1]*6}}},
            {'perch_counts':{'1':1},'perches':{'1:1':{'joints':[float('nan')]*6,'tolerance':[.1]*6}}}):
            with self.subTest(config=config),self.assertRaises(ValueError):rt.ControllerServices.from_config(config)


if __name__=='__main__':unittest.main()
