"""Cross-feature ownership, suspension and invalid-input checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program, pose, run


class ExtendedBoundaryTests(unittest.TestCase):
    def reject(self, body, code, **options):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **options)
        self.assertEqual(caught.exception.code, code)

    def test_handler_cannot_write_active_counter(self):
        self.reject('CONDITION[1]: WHEN TRUE DO n=8 ENDCONDITION FOR n=1 TO 2 DO ENDFor', 'E_FOR_COUNTER')

    def test_handler_indirect_counter_write(self):
        self.reject('CONDITION[1]: WHEN TRUE DO alter() ENDCONDITION FOR n=1 TO 2 DO ENDFOR', 'E_FOR_COUNTER', routines='ROUTINE alter BEGIN n=8 END alter')

    def test_connected_counter_cannot_enter_loop(self):
        self.reject('CONNECT TIMER TO n FOR n=1 TO 2 DO ENDFOR', 'E_FOR_COUNTER')

    def test_timer_local_storage_rejected(self):
        self.reject('work()', 'E_TIMER_SCOPE', routines='ROUTINE work VAR local: INTEGER BEGIN CONNECT TIMER TO local END work')

    def test_condition_multiple_when_and_comma_actions(self):
        state=run('n=0 CONDITION[1]: WHEN FALSE DO n=90 WHEN TRUE DO n=7,s=8 ENDCONDITION ENABLE CONDITION[1] n=n+1')
        self.assertEqual((state['N'],state['S']),(8,8))

    def test_condition_rearm(self):
        state=run('n=0 CONDITION[1]: WHEN n<3 DO n=n+1,ENABLE CONDITION[1] ENDCONDITION ENABLE CONDITION[1] s=0 s=1 s=2 s=3')
        self.assertEqual(state['N'],3)

    def test_undefined_condition_controls_noop(self):
        self.assertEqual(run('ENABLE CONDITION[1] DISABLE CONDITION[1] PURGE CONDITION[1] n=7')['N'],7)

    def test_condition_redefinition_requires_purge(self):
        p,_=compile_program('CONDITION[1]: WHEN FALSE DO ENDCONDITION CONDITION[1]: WHEN FALSE DO ENDCONDITION')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Purge'): p.run()

    def test_condition_number_bound(self):
        p,_=compile_program('CONDITION[1001]: WHEN FALSE DO ENDCONDITION')
        with self.assertRaises(rt.KarelRuntimeError): p.run()

    def test_pause_event_handler(self):
        p,_=compile_program('n=0 CONDITION[1]: WHEN PAUSE DO n=9 ENDCONDITION ENABLE CONDITION[1] PAUSE s=n')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p.snapshot()['N'],9); self.assertEqual(p.resume()['S'],9)

    def test_handler_jumps_explicitly_rejected(self):
        self.reject('CONDITION[1]: WHEN TRUE DO GOTO finish ENDCONDITION finish:: n=7','E_CONDITION_ACTION')

    def test_paused_run_cannot_restart(self):
        p,_=compile_program('n=1 PAUSE n=2')
        with self.assertRaises(rt.KarelPause): p.run()
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.resume()['N'],2)

    def test_resume_requires_pause(self):
        p,_=compile_program('n=1',cooperative=True)
        with self.assertRaises(rt.KarelRuntimeError): p.resume()
        self.assertEqual(p.run()['N'],1)

    def test_host_pause_ordinary_source(self):
        p,_=compile_program('n=1 DELAY 1 n=2',cooperative=True)
        # Sleep adapters receive seconds; request suspension at the next checkpoint.
        p._state._sleep=lambda seconds:p.pause()
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(p.snapshot()['N'],1); self.assertEqual(p.resume()['N'],2)

    def test_task_registry_requires_cooperative_program(self):
        p,_=compile_program('n=1')
        with self.assertRaises(TypeError): rt.TaskRegistry().bind('child',p)

    def test_task_pause_requested_before_start(self):
        child,_=compile_program('n=2',cooperative=True)
        tasks=rt.TaskRegistry(); tasks.bind('child',child)
        run("RUN_TASK('child',0,TRUE,FALSE,0,s)",context=rt.ExecutionContext(tasks=tasks))
        self.assertEqual(child.task_state,'paused'); self.assertEqual(child.resume()['N'],2)

    def test_task_abort_closes_paused_frames(self):
        child,_=compile_program('work()',routines='ROUTINE work BEGIN PAUSE END work')
        with self.assertRaises(rt.KarelPause): child.run()
        tasks=rt.TaskRegistry(); tasks.bind('child',child)
        run("ABORT_TASK('child',TRUE,FALSE,s)",context=rt.ExecutionContext(tasks=tasks))
        self.assertTrue(child._state._abort_requested)
        with self.assertRaises(rt.KarelAbort): child.resume()
        self.assertEqual((child.task_state,child._state.call_depth),('aborted',0))
        with self.assertRaises(rt.KarelAbort): child.run()

    def test_timer_backwards_clock_is_error(self):
        clock=iter((2000,1000))
        p,_=compile_program('n=0 CONNECT TIMER TO n s=1',clock_us=lambda:next(clock))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'backwards'): p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_file_routine_reference(self):
        files=rt.MemoryFiles()
        state=run("OPEN FILE f ('RW','a') put(f) CLOSE FILE f",decl='f: FILE',routines="ROUTINE put(handle: FILE) BEGIN WRITE handle ('ok') END put",context=rt.ExecutionContext(files=files))
        self.assertEqual(files.snapshot()['a'],b'ok'); self.assertFalse(state['F']['open'])

    def test_binary_nonfinite_input_is_error(self):
        files=rt.MemoryFiles({'b':bytes.fromhex('0000807f')})
        p,_=compile_program("x=1 OPEN FILE f ('RB','b') READ f (x)",decl='f: FILE x: REAL',context=rt.ExecutionContext(files=files))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['X'],p.snapshot()['F']['position']),(1.,0))

    def test_file_failed_field_does_not_partially_write(self):
        files=rt.MemoryFiles()
        p,_=compile_program("OPEN FILE f ('WB','b') WRITE f (7,256::1)",decl='f: FILE',context=rt.ExecutionContext(files=files))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(files.snapshot()['b'],b'')

    def test_file_append_cannot_overwrite(self):
        files=rt.MemoryFiles({'a':'seed'})
        run("OPEN FILE f ('AP','a') SET_FILE_POS(f,0,s) WRITE f ('!') CLOSE FILE f",decl='f: FILE s: INTEGER',context=rt.ExecutionContext(files=files))
        self.assertEqual(files.snapshot()['a'],b'seed!')

    def test_path_reversed_partial_copy(self):
        state=run('APPEND_NODE(p,s) APPEND_NODE(p,s) p[1].n=7 p[2].n=9 COPY_PATH(p,2,1,q,s)',prefix='TYPE node=STRUCTURE n: INTEGER ENDSTRUCTURE',decl='p,q: PATH NODEDATA=node s: INTEGER')
        self.assertEqual([row['N'] for row in state['Q']['nodes']],[9,7])

    def test_path_output_status_overlap(self):
        p,_=compile_program('p.n=7 APPEND_NODE(p,p.n)',prefix='TYPE header=STRUCTURE n: INTEGER ENDSTRUCTURE',decl='p: PATH PATHHEADER=header')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
        self.assertEqual(len(p.snapshot()['P']['nodes']),0)

    def test_path_nodes_pass_to_routine(self):
        state=run('APPEND_NODE(p,s) set_node(p[1])',prefix='TYPE node=STRUCTURE n: INTEGER ENDSTRUCTURE',decl='p: PATH NODEDATA=node s: INTEGER',routines='ROUTINE set_node(value: node) BEGIN value.n=42 END set_node')
        self.assertEqual(state['P']['nodes'][0]['N'],42)

    def test_queue_bad_insert_preserves_order(self):
        state=run('INIT_QUEUE(q) APPEND_QUEUE(7,q,a,seq,s) INSERT_QUEUE(9,999,q,a,s)',decl='q: QUEUE_TYPE a: ARRAY[2] OF INTEGER seq,s: INTEGER')
        self.assertEqual((state['A'],state['S']),([7,0],1))

    def test_queue_insert_before_existing_sequence(self):
        state=run('INIT_QUEUE(q) APPEND_QUEUE(7,q,a,seq,s) INSERT_QUEUE(9,seq,q,a,s) GET_QUEUE(q,a,n,seq,s)',decl='q: QUEUE_TYPE a: ARRAY[2] OF INTEGER n,seq,s: INTEGER')
        self.assertEqual(state['N'],9)

    def test_queue_outputs_cannot_overlap_buffer(self):
        p,_=compile_program('INIT_QUEUE(q) APPEND_QUEUE(7,q,a,a[1],s)',decl='q: QUEUE_TYPE a: ARRAY[2] OF INTEGER s: INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()

    def test_queue_keeps_original_buffer(self):
        p,_=compile_program('INIT_QUEUE(q) APPEND_QUEUE(7,q,a,seq,s) GET_QUEUE(q,b,n,seq,s)',decl='q: QUEUE_TYPE a,b: ARRAY[2] OF INTEGER n,seq,s: INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'original'): p.run()

    def test_register_wrong_pose_kind_sets_status(self):
        bank=rt.PositionRegisters(1,{1:pose()})
        p,_=compile_program('j=GET_JPOS_REG(1,s)',decl='j: JOINTPOS s: INTEGER',context=rt.ExecutionContext(positions=bank))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['S'],3)

    def test_port_counts_have_no_defaults(self):
        with self.assertRaises(rt.KarelRuntimeError): rt.PortBank({}).read('DIN',1)

    def test_service_requests_are_defensive(self):
        p,_=compile_program("SET_STR_REG(1,'a',s)",context=rt.ExecutionContext(strings=rt.StringRegisters(1)))
        p.run(); p.service_requests[0]['outcome']='changed'
        self.assertEqual(p.service_requests[0]['outcome'],'completed')

    def test_extended_pose_conversion_narrows_and_widens(self):
        state=run("CNV_STR_CONF('N',c,s) ext=POS(1,2,3,0,0,0,c) ext.ext1=9 p=ext ext=p",decl='c: CONFIG s: INTEGER ext: XYZWPREXT p: POSITION')
        self.assertEqual((state['EXT']['X'],state['EXT']['EXT1']),(1.,0.))

    def test_extended_comparison_requires_tolerances(self):
        p,_=compile_program("CNV_STR_CONF('N',c,s) p=POS(0,0,0,0,0,0,c) ok=p>=<p",decl='c: CONFIG s: INTEGER p: XYZWPREXT ok: BOOLEAN',pose_tolerance=(0,0,True))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'external_tolerance'): p.run()

    def test_invalid_path_node_type_is_diagnostic(self):
        self.reject('', 'E_TYPE',decl='p: PATH NODEDATA=INTEGER')

    def test_invalid_clock_does_not_initialize_timer(self):
        p,_=compile_program('CONNECT TIMER TO n',clock_us=lambda:False)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['N'],{'uninitialized':True})

    def test_unknown_context_fields_rejected(self):
        with self.assertRaises(ValueError): rt.ExecutionContext.from_config({'positions':{'count':1,'unexpected':{}}})

    def test_reachability_failure_is_source_located(self):
        def broken(value): raise ValueError('model unavailable')
        ctx=rt.ExecutionContext(robot=rt.RobotContext(reachable=broken))
        p,_=compile_program("CNV_STR_CONF('N',c,s) p=POS(0,0,0,0,0,0,c) ok=IN_RANGE(p)",decl='c: CONFIG s: INTEGER p: XYZWPR ok: BOOLEAN',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError) as caught: p.run()
        self.assertIsNotNone(caught.exception.line)

    def test_model_validates_all_outputs_before_assignment(self):
        def forward(joints,frame,tool,solution):
            return pose(7),frame.values['CONFIG_DATA'],[0.,0.]
        ctx=rt.ExecutionContext(robot=rt.RobotContext(forward=forward))
        p,_=compile_program("CNV_STR_CONF('N',c,s) f=POS(0,0,0,0,0,0,c) s=9 JOINT2POS(j,f,f,0,p,c,axes,s)",decl='j: JOINTPOS f,p: POSITION c: CONFIG axes: ARRAY[1] OF REAL s: INTEGER',context=ctx)
        p._state.values['J'].values[:]=[0.]*9
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['P']['LOCATION']['X'],{'uninitialized':True})
        self.assertEqual(p.snapshot()['S'],9)

    def test_public_reports_describe_supplied_services(self):
        _,result=compile_program('PAUSE')
        self.assertTrue(result.report['cooperative_policy']['enabled'])
        self.assertFalse(result.report['service_policy']['controller_validated'])
        self.assertIn('MIRROR',result.report['service_policy']['functions'])
        self.assertIn('external_axes',result.report['extended_geometry_policy'])

    def test_handler_function_predicate_and_action(self):
        state=run('n=0 CONDITION[1]: WHEN ready() DO change() ENDCONDITION ENABLE CONDITION[1] s=0',routines='ROUTINE ready: BOOLEAN BEGIN RETURN TRUE END ready ROUTINE change BEGIN n=7 END change')
        self.assertEqual(state['N'],7)

    def test_cooperative_function_in_boolean_loop_test(self):
        state=run('n=0 WHILE (n<2) AND advance() DO s=n ENDWHILE',cooperative=True,routines='ROUTINE advance: BOOLEAN BEGIN n=n+1 RETURN TRUE END advance')
        self.assertEqual((state['N'],state['S']),(2,2))

    def test_returned_pose_field_value_argument(self):
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(1,{1:pose(7)}))
        state=run('take(GET_POS_REG(1,s).config_data)',decl='s,n: INTEGER',routines='ROUTINE take(value: CONFIG) BEGIN n=value.cfg_turn_no1 END take',context=ctx)
        self.assertEqual(state['N'],0)


class ExtendedCliTests(unittest.TestCase):
    def test_generated_context_and_cooperative_option(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); source=folder/'source.kl'; output=folder/'converted.py'; config=folder/'context.json'
            source.write_text("PROGRAM T VAR text: STRING[4] s: INTEGER BEGIN GET_STR_REG(1,text,s) END T")
            config.write_text(json.dumps({'strings':{'count':1,'values':{'1':'done'}}}))
            result=subprocess.run([sys.executable,'-m','karel2py',str(source),'-o',str(output),'--cooperative'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            result=subprocess.run([sys.executable,str(output),'--context',str(config)],capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr); self.assertIn("'TEXT': 'done'",result.stdout)

    def test_cooperative_option_in_context_hash(self):
        source='PROGRAM T BEGIN END T'
        plain=translate(source); cooperative=translate(source,cooperative=True)
        self.assertNotEqual(plain.report['translation_context_sha256'],cooperative.report['translation_context_sha256'])
        self.assertTrue(cooperative.report['translation_context']['cooperative'])

    def test_cooperative_option_requires_boolean(self):
        with self.assertRaises(ValueError): translate('PROGRAM T BEGIN END T',cooperative=1)
