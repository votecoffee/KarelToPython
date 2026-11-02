"""Authored Boolean identity and representation-based range predicates."""
import inspect
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint,model_context
from tests.test_cartesian_interfaces import value as cartesian_value


def limits():return rt.ExecutionContext(robot=rt.RobotContext(joint_limits=[(-5,5),(-10,10)]))

def cartesian(kind='XYZWPR',answer=True):
    ctx=rt.ExecutionContext(robot=rt.RobotContext(reachable=lambda point:answer))
    p,r=compile_program('a=IN_RANGE(p) b=J_IN_RANGE(p)',decl='a,b:BOOLEAN p:'+kind,context=ctx)
    p._state.values['P']=cartesian_value(kind,(2.,3.,4.),(0.,0.,0.),(0.,0.,0.))
    return p,r


class BooleanPlusTests(unittest.TestCase):
    def test_true_and_false_keep_boolean_type(self):
        p,_=compile_program('a=+TRUE b=+FALSE',decl='a,b:BOOLEAN');self.assertEqual(p.run(),dict(A=True,B=False))
    def test_nested_plus_and_not(self):
        p,_=compile_program('a=NOT +(+(FALSE))',decl='a:BOOLEAN');self.assertIs(p.run()['A'],True)
    def test_constant_expression(self):
        p,_=compile_program('a=+choice',prefix='CONST choice=TRUE',decl='a:BOOLEAN');self.assertIs(p.run()['A'],True)
    def test_array_element(self):
        p,_=compile_program('a[2]=TRUE b=+a[2]',decl='a:ARRAY[2]OF BOOLEAN b:BOOLEAN');self.assertIs(p.run()['B'],True)
    def test_user_function_runs_once(self):
        p,_=compile_program('n=0 b=+work()',decl='n:INTEGER b:BOOLEAN',routines='ROUTINE work:BOOLEAN BEGIN n=n+1 RETURN TRUE END work');self.assertEqual(p.run(),dict(N=1,B=True))
    def test_routine_boolean_parameter(self):
        p,_=compile_program('work(+TRUE)',decl='b:BOOLEAN',routines='ROUTINE work(v:BOOLEAN) BEGIN b=v END work');self.assertIs(p.run()['B'],True)
    def test_dispatch_and_cooperative_parity(self):
        for body,coop in [('b=+TRUE',False),('start:: b=+TRUE GOTO done b=FALSE done::',False),('b=+TRUE',True)]:
            with self.subTest(body=body,cooperative=coop):
                p,_=compile_program(body,decl='b:BOOLEAN',cooperative=coop);self.assertIs(p.run()['B'],True)
    def test_missing_boolean_is_still_an_error(self):
        p,_=compile_program('b=TRUE b=+a',decl='a,b:BOOLEAN')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p.snapshot()['B'],True)
    def test_boolean_minus_is_rejected(self):
        with self.assertRaises(TranslationError):compile_program('b=-TRUE',decl='b:BOOLEAN')
    def test_boolean_plus_does_not_enable_arithmetic(self):
        with self.assertRaises(TranslationError):compile_program('n=(+TRUE)+1',decl='n:INTEGER')
    def test_boolean_plus_is_not_numeric_assignment(self):
        with self.assertRaises(TranslationError):compile_program('n=+TRUE',decl='n:INTEGER')
    def test_host_runtime_scope_is_explicit(self):
        with rt._numeric_scope('pythonic'):self.assertIs(rt.unary('+',True),True)
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.unary('+',True)


class RangeOverloadTests(unittest.TestCase):
    def test_joint_inputs_need_only_explicit_limits(self):
        p,_=compile_program('a=IN_RANGE(j) b=J_IN_RANGE(j)',decl='j:JOINTPOS2 a,b:BOOLEAN',context=limits());p._state.values['J']=joint([2.,3.]);self.assertEqual((p.run()['A'],p.snapshot()['B']),(True,True));self.assertFalse(any(x['operation']=='JOINT_GEOMETRY' for x in p.service_requests))
    def test_joint_boundary_is_inclusive(self):
        p,_=compile_program('a=IN_RANGE(j) b=J_IN_RANGE(j)',decl='j:JOINTPOS2 a,b:BOOLEAN',context=limits());p._state.values['J']=joint([-5.,10.]);self.assertEqual((p.run()['A'],p.snapshot()['B']),(True,True))
    def test_outside_joint_limits_is_false(self):
        p,_=compile_program('a=IN_RANGE(j) b=J_IN_RANGE(j)',decl='j:JOINTPOS2 a,b:BOOLEAN',context=limits());p._state.values['J']=joint([5.1,0.]);self.assertEqual((p.run()['A'],p.snapshot()['B']),(False,False))
    def test_nine_slot_zero_padding_is_checked(self):
        p,_=compile_program('a=IN_RANGE(j)',decl='j:JOINTPOS a:BOOLEAN',context=limits());p._state.values['J']=joint([2.,3.]+[0.]*7);self.assertIs(p.run()['A'],True)
    def test_nonzero_padding_preserves_answer(self):
        p,_=compile_program('a=TRUE a=IN_RANGE(j)',decl='j:JOINTPOS a:BOOLEAN',context=limits());p._state.values['J']=joint([2.,3.,1.]+[0.]*6)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Unused'):p.run()
        self.assertIs(p.snapshot()['A'],True)
    def test_width_mismatch_is_an_error(self):
        p,_=compile_program('a=IN_RANGE(j)',decl='j:JOINTPOS3 a:BOOLEAN',context=limits());p._state.values['J']=joint([2.,3.,0.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_missing_joint_axis_is_an_error(self):
        p,_=compile_program('a=IN_RANGE(j)',decl='j:JOINTPOS2 a:BOOLEAN',context=limits());p._state.values['J']=joint([2.,rt.UNINITIALIZED])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_nonfinite_axis_is_an_error(self):
        p,_=compile_program('a=IN_RANGE(j)',decl='j:JOINTPOS2 a:BOOLEAN',context=limits());p._state.values['J']=joint([float('inf'),0.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_reachability_adapter_does_not_replace_joint_limits(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(reachable=lambda p:True));p,_=compile_program('a=IN_RANGE(j)',decl='j:JOINTPOS2 a:BOOLEAN',context=ctx);p._state.values['J']=joint([2.,3.])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit limits'):p.run()
    def test_each_cartesian_representation_uses_adapter(self):
        for kind in ('POSITION','XYZWPR','XYZWPREXT'):
            with self.subTest(kind=kind):
                p,_=cartesian(kind);self.assertEqual((p.run()['A'],p.snapshot()['B']),(True,True))
    def test_false_cartesian_result_is_preserved(self):
        p,_=cartesian(answer=False);self.assertEqual((p.run()['A'],p.snapshot()['B']),(False,False))
    def test_callback_receives_independent_cartesian_data(self):
        p,_=cartesian();calls=[]
        def callback(point):calls.append(point);point.values['X']=99.;return True
        p._state.execution.robot.reachable=callback;p.run();self.assertEqual(p.snapshot()['P']['X'],2.);self.assertEqual(len(calls),2);self.assertIsNot(calls[0],calls[1])
    def test_external_axes_are_forwarded(self):
        p,_=cartesian('XYZWPREXT');p._state.values['P'].values['EXT2']=13.;seen=[];p._state.execution.robot.reachable=lambda point:seen.append(point.values['EXT2']) is None;p.run();self.assertEqual(seen,[13.,13.])
    def test_no_robot_context_fails_explicitly(self):
        p,_=compile_program('a=IN_RANGE(j)',decl='j:JOINTPOS2 a:BOOLEAN');p._state.values['J']=joint([0.,0.])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'):p.run()
    def test_limits_do_not_supply_cartesian_reachability(self):
        p,_=cartesian();p._state.execution.robot=limits().robot
        with self.assertRaisesRegex(rt.KarelRuntimeError,'reachability'):p.run()
    def test_bad_callback_result_does_not_assign(self):
        for result in (1,None,'TRUE'):
            with self.subTest(result=result):
                p,_=cartesian(answer=result);p._state.values['A']=True
                with self.assertRaisesRegex(rt.KarelRuntimeError,'synchronous BOOLEAN'):p.run()
                self.assertIs(p.snapshot()['A'],True)
    def test_callback_exception_is_source_located(self):
        p,_=cartesian()
        def callback(point):raise ValueError('authored error')
        p._state.execution.robot.reachable=callback
        with self.assertRaisesRegex(rt.KarelRuntimeError,'authored error') as caught:p.run()
        self.assertIsNotNone(caught.exception.line)
    def test_async_result_is_closed(self):
        results=[]
        async def work():return True
        def callback(point):result=work();results.append(result);return result
        p,_=cartesian();p._state.execution.robot.reachable=callback
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(inspect.getcoroutinestate(results[0]),inspect.CORO_CLOSED)
    def test_generator_result_is_closed(self):
        results=[]
        def work():yield True
        def callback(point):result=work();results.append(result);return result
        p,_=cartesian();p._state.execution.robot.reachable=callback
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(inspect.getgeneratorstate(results[0]),inspect.GEN_CLOSED)
    def test_joint_expression_runs_once(self):
        p,_=compile_program('n=0 a=IN_RANGE(work())',decl='n:INTEGER a:BOOLEAN j:JOINTPOS2',context=limits(),routines='ROUTINE work:JOINTPOS2 BEGIN n=n+1 RETURN j END work');p._state.values['J']=joint([0.,0.]);self.assertEqual((p.run()['N'],p.snapshot()['A']),(1,True))
    def test_structured_dispatcher_and_cooperative_parity(self):
        for labelled,coop in ((False,False),(True,False),(False,True)):
            p,_=compile_program(('start:: ' if labelled else '')+'a=IN_RANGE(j) b=J_IN_RANGE(j)',decl='j:JOINTPOS2 a,b:BOOLEAN',context=limits(),cooperative=coop);p._state.values['J']=joint([0.,0.]);self.assertEqual((p.run()['A'],p.snapshot()['B']),(True,True))
    def test_dh_model_supports_cartesian_overload(self):
        ctx=model_context((0.,90.));p,_=compile_program('p=CURPOS(0,0) a=J_IN_RANGE(p)',decl='p:XYZWPREXT a:BOOLEAN',context=ctx);self.assertIs(p.run()['A'],True)
    def test_limits_only_context_roundtrip(self):
        ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(limits().to_config())));p,_=compile_program('a=IN_RANGE(j)',decl='j:JOINTPOS2 a:BOOLEAN',context=ctx);p._state.values['J']=joint([1.,2.]);self.assertIs(p.run()['A'],True)
    def test_group_mismatch_is_explicit_and_source_located(self):
        p,_=compile_program('a=IN_RANGE(j)',prefix='%DEFGROUP=2',decl='j:JOINTPOS2 a:BOOLEAN',context=limits());p._state.values['J']=joint([0.,0.])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'group') as caught:p.run()
        self.assertIsNotNone(caught.exception.line)
    def test_linked_routine_uses_calling_root_group(self):
        lib='PROGRAM LIB ROUTINE ready(j:JOINTPOS2):BOOLEAN BEGIN RETURN IN_RANGE(j) END ready BEGIN END LIB'
        main='PROGRAM MAIN %DEFGROUP=2\nVAR a:BOOLEAN j:JOINTPOS2 ROUTINE ready(j:JOINTPOS2):BOOLEAN FROM LIB BEGIN a=ready(j) END MAIN'
        ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:rt.RobotContext(joint_limits=[(-1,1)]*2),2:rt.RobotContext(joint_limits=[(-10,10)]*2)},active_group=1));p=translate_project(dict(lib=lib,main=main)).instantiate(context=ctx);p.programs['MAIN']._state.values['J']=joint([3.,4.]);p.run('MAIN');self.assertIs(p.programs['MAIN'].snapshot()['A'],True)
    def test_invalid_source_operand_categories_are_rejected(self):
        for value in ('1','TRUE',"'value'"):
            for name in ('IN_RANGE','J_IN_RANGE'):
                with self.subTest(name=name,value=value),self.assertRaises(TranslationError):compile_program('a='+name+'('+value+')',decl='a:BOOLEAN')
    def test_invalid_arity_is_rejected(self):
        for call in ('IN_RANGE()','J_IN_RANGE(1,2)'):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program('a='+call,decl='a:BOOLEAN')
    def test_report_states_approximate_portable_policy(self):
        _,r=cartesian();policy=r.report['source_form_policy'];self.assertIn('per-axis limits',policy['range']);self.assertFalse(policy['controller_validated'])
