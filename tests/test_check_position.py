"""Authored framed position checks, model groups, callback isolation and CLI use."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.kinematics import pose as identity_pose
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value
from tests.test_extended_services import compile_program,run,pose
from tests.test_project_scheduler import source

ROOT=Path(__file__).resolve().parents[1]
DECL='p: XYZWPREXT f,t: POSITION c: CONFIG s: INTEGER'
SETUP="CNV_STR_CONF('N',c,s) p=POS(100,0,0,0,0,0,c) f=POS(0,0,0,0,0,0,c) t=f "
CALL='CHECK_EPOS(p,f,t,s)'


def context(**changes):
    return rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100,'min':0,'max':0}],**changes}})


def callback_context(callback): return rt.ExecutionContext(robot=rt.RobotContext(check_position=callback))


def grouped_context():
    return rt.ExecutionContext.from_config({'robot':{'groups':{'1':{'dh':[{'a':100,'min':0,'max':0}]},'2':{'dh':[{'a':200,'min':0,'max':0}]}},'active_group':2}})


class PositionModelCheckTests(unittest.TestCase):
    def test_reachable_without_current_snapshot(self):
        ctx=context();state=run(SETUP+CALL,decl=DECL,context=ctx)
        self.assertEqual(state['S'],0);self.assertIsNone(ctx.robot.current)

    def test_unreachable_returns_portable_failure_status(self):
        state=run(SETUP+'p.x=250 '+CALL,decl=DECL,context=context())
        self.assertEqual(state['S'],1)

    def test_explicit_frame_and_tool_offsets(self):
        state=run(SETUP+'f=POS(10,0,0,0,0,0,c) t=POS(5,0,0,0,0,0,c) p.x=95 '+CALL,decl=DECL,context=context())
        self.assertEqual(state['S'],0)

    def test_explicit_frame_rotation(self):
        state=run(SETUP+'f=POS(0,0,0,0,0,90,c) p=POS(0,-100,0,0,0,-90,c) '+CALL,decl=DECL,context=context())
        self.assertEqual(state['S'],0)

    def test_explicit_tool_rotation(self):
        state=run(SETUP+'t=POS(0,0,0,0,0,90,c) p.r=90 '+CALL,decl=DECL,context=context())
        self.assertEqual(state['S'],0)

    def test_model_base_is_applied(self):
        state=run(SETUP+'p.x=120 '+CALL,decl=DECL,context=context(base=typed_value(pose(20))))
        self.assertEqual(state['S'],0)

    def test_active_frame_tool_selection_is_not_used(self):
        ctx=context();ctx.robot.active_frame=99;ctx.robot.active_tool=True
        self.assertEqual(run(SETUP+CALL,decl=DECL,context=ctx)['S'],0)
        self.assertEqual((ctx.robot.active_frame,ctx.robot.active_tool),(99,True))

    def test_all_cartesian_representations_are_accepted(self):
        for point_kind in ('POSITION','XYZWPR','XYZWPREXT'):
            for frame_kind in ('POSITION','XYZWPR','XYZWPREXT'):
                with self.subTest(point=point_kind,frame=frame_kind):
                    decl=f'p: {point_kind} f,t: {frame_kind} c: CONFIG s: INTEGER'
                    self.assertEqual(run(SETUP+CALL,decl=decl,context=context())['S'],0)

    def test_external_axis_values_constrain_the_check(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100,'min':0,'max':0},{'type':'prismatic','min':0,'max':100}],'external_axes':1}})
        for value,expected in ((42,0),(43,1),(101,1)):
            with self.subTest(axis=value):
                state=run(SETUP+f'p.z=42 p.ext1={value} '+CALL,decl=DECL,context=ctx)
                self.assertEqual(state['S'],expected)

    def test_model_limits_can_reject_cartesian_orientation(self):
        self.assertEqual(run(SETUP+'p.r=90 '+CALL,decl=DECL,context=context())['S'],1)

    def test_model_data_and_current_state_are_unchanged(self):
        ctx=context(current={'joints':{'type':['JOINTPOS',1],'value':[0.0]}})
        before=json.loads(json.dumps(ctx.robot.to_config()))
        run(SETUP+CALL,decl=DECL,context=ctx)
        self.assertEqual(ctx.robot.to_config(),before)

    def test_restored_model_retains_position_check_support(self):
        ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(context().to_config())))
        self.assertEqual(run(SETUP+CALL,decl=DECL,context=ctx)['S'],0)


class PositionCheckGroupTests(unittest.TestCase):
    def test_default_group_uses_active_context(self):
        self.assertEqual(run(SETUP+'p.x=200 '+CALL,decl=DECL,context=grouped_context())['S'],0)
        self.assertEqual(run(SETUP+CALL,decl=DECL,context=grouped_context())['S'],1)

    def test_explicit_group_overrides_active_group(self):
        ctx=grouped_context()
        self.assertEqual(run(SETUP+CALL.replace(',s)',',s,1)'),decl=DECL,context=ctx)['S'],0)
        self.assertEqual(ctx.robot.active_group,2)

    def test_source_group_qualifier_controls_default(self):
        decl=DECL.replace('p: XYZWPREXT','p: XYZWPREXT IN GROUP[1]')
        self.assertEqual(run(SETUP+CALL,decl=decl,context=grouped_context())['S'],0)

    def test_explicit_group_overrides_source_group(self):
        decl=DECL.replace('p: XYZWPREXT','p: XYZWPREXT IN GROUP[1]')
        self.assertEqual(run(SETUP+'p.x=200 '+CALL.replace(',s)',',s,2)'),decl=decl,context=grouped_context())['S'],0)

    def test_missing_group_preserves_status_with_source_location(self):
        for group in (0,-1,3):
            p,_=compile_program(SETUP+'s=99 '+CALL.replace(',s)',f',s,{group})'),decl=DECL,context=grouped_context())
            with self.subTest(group=group),self.assertRaises(rt.KarelRuntimeError) as caught:p.run()
            self.assertEqual(p.snapshot()['S'],99);self.assertIsNotNone(caught.exception.line)

    def test_linked_library_uses_calling_root_group(self):
        routine='ROUTINE check_point: INTEGER VAR '+DECL+' BEGIN '+SETUP+CALL+' RETURN s END check_point'
        sources={'library.kl':source('LIB','',routines=routine),
                 'main.kl':source('MAIN','s=check_point()',decl='s: INTEGER p: XYZWPREXT IN GROUP[1]',routines='ROUTINE check_point: INTEGER FROM LIB')}
        instance=translate_project(sources).instantiate(context=grouped_context())
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['S'],0)

    def test_for_counter_can_be_a_read_only_group(self):
        body=SETUP+'FOR group_id=1 TO 2 DO CHECK_EPOS(p,f,t,statuses[group_id],group_id) ENDFOR'
        state=run(body,decl=DECL+' group_id: INTEGER statuses: ARRAY[2] OF INTEGER',context=grouped_context())
        self.assertEqual(state['STATUSES'],[0,1])


class PositionCheckAdapterTests(unittest.TestCase):
    def test_callback_receives_detached_pose_frame_and_tool(self):
        calls=[]
        def check(point,frame,tool):
            calls.append((point,frame,tool))
            point.values['X']=999.;frame.values['LOCATION'].values['X']=998.;tool.values['LOCATION'].values['X']=997.
            return True
        state=run(SETUP+CALL,decl=DECL,context=callback_context(check))
        self.assertEqual((state['S'],state['P']['X'],state['F']['LOCATION']['X'],state['T']['LOCATION']['X']),(0,100.,0.,0.))
        self.assertEqual(len(calls),1)

    def test_false_callback_has_failure_status(self):
        self.assertEqual(run(SETUP+CALL,decl=DECL,context=callback_context(lambda *args:False))['S'],1)

    def test_callback_exception_preserves_status(self):
        def broken(*args):raise ValueError('authored failure')
        p,_=compile_program(SETUP+'s=99 '+CALL,decl=DECL,context=callback_context(broken))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'authored failure'):p.run()
        self.assertEqual(p.snapshot()['S'],99)

    def test_invalid_callback_results_are_not_coerced(self):
        for answer in (0,1,None,'yes',[],object()):
            p,_=compile_program(SETUP+'s=99 '+CALL,decl=DECL,context=callback_context(lambda *args:answer))
            with self.subTest(answer=answer),self.assertRaisesRegex(rt.KarelRuntimeError,'synchronous BOOLEAN'):p.run()
            self.assertEqual(p.snapshot()['S'],99)

    def test_async_adapters_are_rejected_at_construction(self):
        async def asynchronous(*args):return True
        class AsyncCallable:
            async def __call__(self,*args):return True
        for callback in (asynchronous,AsyncCallable(),17):
            with self.subTest(callback=callback),self.assertRaises(TypeError):rt.RobotContext(check_position=callback)

    def test_returned_coroutine_is_closed_without_execution(self):
        results=[]
        async def pending():return True
        def check(*args):
            result=pending();results.append(result);return result
        p,_=compile_program(SETUP+'s=99 '+CALL,decl=DECL,context=callback_context(check))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'synchronous BOOLEAN'):p.run()
        self.assertIsNone(results[0].cr_frame);self.assertEqual(p.snapshot()['S'],99)

    def test_one_argument_range_callback_is_not_reinterpreted(self):
        p,_=compile_program(SETUP+'s=99 '+CALL,decl=DECL,context=rt.ExecutionContext(robot=rt.RobotContext(reachable=lambda point:True)))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'framed position check adapter'):p.run()
        self.assertEqual(p.snapshot()['S'],99)

    def test_missing_robot_context_preserves_status(self):
        p,_=compile_program(SETUP+'s=99 '+CALL,decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit'):p.run()
        self.assertEqual(p.snapshot()['S'],99)

    def test_host_api_is_usable_without_translation_scope(self):
        self.assertTrue(context().robot.check_pose(pose(100),identity_pose(),identity_pose()))

    def test_inputs_capture_values_before_later_argument_effects(self):
        seen=[]
        def check(point,frame,tool):seen.append(point.values['X']);return True
        routines='ROUTINE later_tool: POSITION BEGIN p.x=999 RETURN t END later_tool'
        state=run(SETUP+CALL.replace(',t,',',later_tool(),'),decl=DECL,routines=routines,context=callback_context(check))
        self.assertEqual((seen,state['P']['X'],state['S']),([100.],999.,0))


class PositionCheckProtectionTests(unittest.TestCase):
    def test_uninitialized_operands_fail_before_callback(self):
        bodies={'p':"f=POS(0,0,0,0,0,0,c) t=f ",
                'f':"p=POS(100,0,0,0,0,0,c) t=POS(0,0,0,0,0,0,c) ",
                't':"p=POS(100,0,0,0,0,0,c) f=POS(0,0,0,0,0,0,c) "}
        for operand,assignments in bodies.items():
            calls=[]
            body="CNV_STR_CONF('N',c,s) "+assignments+'s=99 '+CALL
            p,_=compile_program(body,decl=DECL,context=callback_context(lambda *args:calls.append(args) or True))
            with self.subTest(operand=operand),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['S'],calls),(99,[]))

    def test_invalid_matrix_is_rejected_before_callback(self):
        calls=[];point=identity_pose();frame=identity_pose();frame.values['NORMAL'].values['X']=2.
        p,_=compile_program('s=99 '+CALL,decl=DECL,context=callback_context(lambda *args:calls.append(args) or True))
        with rt._numeric_scope('pythonic'):p._state.values['P']=rt.convert_position(('XYZWPREXT',),point)
        p._state.values['F']=frame;p._state.values['T']=point
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['S'],calls),(99,[]))

    def test_status_must_be_an_exact_writable_integer(self):
        for call in (CALL.replace(',s)',',0)'),CALL.replace(',s)',',c.flip)'),CALL.replace(',s)',',p.x)'),CALL[:-1]+',1,2)'):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(SETUP+call,decl=DECL)

    def test_non_pose_operands_and_bad_group_types_are_rejected(self):
        for call in (CALL.replace('(p,','(s,'),CALL.replace(',f,',',c,'),CALL.replace(',s)',',s,TRUE)')):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(SETUP+call,decl=DECL)

    def test_direct_and_transitive_counter_outputs_are_rejected(self):
        for body,routines in ((SETUP+'FOR s=1 TO 2 DO '+CALL+' ENDFOR',''),
                              (SETUP+'FOR s=1 TO 2 DO check_point ENDFOR','ROUTINE check_point BEGIN '+CALL+' END check_point')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:compile_program(body,decl=DECL,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_report_describes_the_portable_contract(self):
        result=translate(source('TEST',SETUP+CALL,decl=DECL))
        self.assertFalse(result.report['position_check_policy']['controller_validated'])
        self.assertIn('CHECK_EPOS',result.report['service_policy']['procedures'])


class PositionCheckCliTests(unittest.TestCase):
    def test_cli_translation_execution_and_state_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'check.py';report=root/'report.json';saved=root/'state.json'
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(ROOT/'examples/check_positions.kl'),'-o',str(output),'--report',str(report)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(json.loads(report.read_text(encoding='utf-8'))['position_check_policy']['controller_validated'])
            result=subprocess.run([sys.executable,'-X','utf8',str(output),'--context',str(ROOT/'examples/check_positions.services.initial.json'),'--state-out',str(saved)],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(ast.literal_eval(result.stdout),json.loads((ROOT/'examples/check_positions.expected.json').read_text(encoding='utf-8')))
            persisted=json.loads(saved.read_text(encoding='utf-8'))
            self.assertEqual(persisted['robot'],json.loads((ROOT/'examples/check_positions.services.initial.json').read_text(encoding='utf-8'))['robot'])
            restored=rt.ExecutionContext.load(saved)
            self.assertTrue(restored.robot.for_group(1).check_pose(pose(100),identity_pose(),identity_pose()))


if __name__=='__main__':unittest.main()
