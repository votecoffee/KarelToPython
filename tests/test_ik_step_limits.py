"""Authored long-travel IK, per-axis limits and shared conversion consumers."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from karel2py.kinematics import SerialRobotModel, pose
from tests.test_extended_services import compile_program
from tests.test_record_variable_transfers import call


def context(*,step=None,iterations=200,groups=False):
    row={'type':'prismatic','min':-10000,'max':10000}
    if step is not None:row['ik_step_limit']=step
    model={'dh':[row],'iterations':iterations,
           'current':{'joints':{'type':['JOINTPOS',1],'value':[0.]}}}
    return rt.ExecutionContext.from_config({'robot':
        {'groups':{'2':model},'active_group':2} if groups else model})


def point(z):
    result=pose();result.values['LOCATION'].values['Z']=float(z);return result


class SolverStepTests(unittest.TestCase):
    def test_defaults_distinguish_degrees_and_millimetres(self):
        model=SerialRobotModel([{}, {'type':'prismatic'}])
        self.assertEqual(model.ik_step_limits,(10.,100.))

    def test_long_linear_travel_in_both_directions_and_from_endpoints(self):
        for start,end in ((0,5000),(0,-5000),(-10000,10000),(10000,-10000)):
            with self.subTest(start=start,end=end):
                model=context(iterations=250).robot.model
                solution=model.solve(model.chain([end]),[start])
                self.assertIsNotNone(solution)
                self.assertAlmostEqual(solution[0],end,delta=.01)
                self.assertTrue(model.within_limits(solution))

    def test_explicit_old_step_retains_its_bounded_failure(self):
        model=context(step=10).robot.model
        self.assertIsNone(model.solve(model.chain([5000]),[0]))

    def test_override_can_cross_long_distance_in_a_small_budget(self):
        for step,expected in ((100,False),(1000,True)):
            with self.subTest(step=step):
                model=context(step=step,iterations=8).robot.model
                solution=model.solve(model.chain([5000]),[0])
                self.assertEqual(solution is not None,expected)
                if solution is not None:self.assertAlmostEqual(solution[0],5000,delta=.01)

    def test_mixed_joint_proposal_uses_one_direction_preserving_scale(self):
        model=SerialRobotModel([{'ik_step_limit':2},
            {'type':'prismatic','min':0,'max':10000,'ik_step_limit':500}],iterations=1)
        target=model.chain([20,200]);observed=[];chain=model.chain
        def record(values):observed.append(values.copy());return chain(values)
        with patch.object(model,'chain',side_effect=record):
            self.assertIsNone(model.solve(target,[0,0]))
        first_trial=observed[3]  # Initial pose, two Jacobian probes, first trial.
        self.assertAlmostEqual(first_trial[0],2.,delta=1e-8)
        self.assertAlmostEqual(first_trial[1],20.,delta=.2)
        self.assertLessEqual(abs(first_trial[1]),500.)

    def test_fixed_external_axis_does_not_limit_the_free_axis_step(self):
        model=SerialRobotModel([{'type':'prismatic','min':0,'max':10000,'ik_step_limit':1000},
            {'min':0,'max':90,'ik_step_limit':.0001}],external_axes=1,iterations=8)
        solution=model.solve(model.chain([5000,45]),[0,0],fixed={1:45})
        self.assertIsNotNone(solution)
        self.assertAlmostEqual(solution[0],5000,delta=.01)
        self.assertEqual(solution[1],45)

    def test_override_does_not_change_forward_geometry_or_joint_limits(self):
        plain=SerialRobotModel([{'a':100}]);configured=SerialRobotModel([{'a':100,'ik_step_limit':1}])
        self.assertEqual(plain.chain([45]),configured.chain([45]))
        self.assertEqual(plain.limits,configured.limits)

    def test_zero_travel_row_does_not_limit_the_free_axis(self):
        model=SerialRobotModel([{'min':0,'max':0,'ik_step_limit':1e-300},
            {'type':'prismatic','min':0,'max':10000,'ik_step_limit':1000}],iterations=8)
        solution=model.solve(model.chain([0,5000]),[0,0])
        self.assertIsNotNone(solution)
        self.assertAlmostEqual(solution[1],5000,delta=.01)
        self.assertEqual(solution[0],0)

    def test_bad_limits_rejected_before_model_construction(self):
        for value in (True,False,None,'100',[],{},0,-1,float('nan'),float('inf'),-float('inf'),10**400):
            with self.subTest(value=repr(value)[:40]),self.assertRaisesRegex(ValueError,'IK step limit'):
                SerialRobotModel([{'ik_step_limit':value}])

    def test_tiny_finite_step_is_bounded_without_progress(self):
        model=SerialRobotModel([{'type':'prismatic','ik_step_limit':1e-300}],iterations=1)
        self.assertIsNone(model.solve(model.chain([42]),[1]))

    def test_saved_grouped_settings_roundtrip_without_current_state_changes(self):
        ctx=context(step=1000,iterations=8,groups=True);before=ctx.to_config()
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(before)))
        model=restored.robot.for_group(2).model
        self.assertEqual(model.ik_step_limits,(1000.,))
        self.assertIsNotNone(model.solve(model.chain([5000]),[0]))
        self.assertEqual(restored.to_config(),before)


class ConversionStepTests(unittest.TestCase):
    def test_routine_argument_and_return_conversion_use_the_same_setting(self):
        routines='ROUTINE distance(j:JOINTPOS1):INTEGER BEGIN RETURN ROUND(j[1]) END distance '
        routines+='ROUTINE inverse(p:POSITION):JOINTPOS1 BEGIN RETURN p END inverse'
        program,report=compile_program('n=distance((a)) b=inverse(a)',
            decl='a:POSITION b:JOINTPOS1 n:INTEGER',routines=routines,
            context=context(step=1000,iterations=8))
        program._state.values['A']=point(5000)
        data=program.run()
        self.assertEqual(data['N'],5000)
        self.assertAlmostEqual(data['B']['axes'][0],5000,delta=.01)
        policy=report.report['kinematic_assignment_policy']
        self.assertIn('100 millimetres',policy['inverse_steps'])
        self.assertIn('ik_step_limit',policy['inverse_steps'])
        self.assertFalse(policy['controller_validated'])

    def test_source_assignment_and_scalar_variable_transfers(self):
        for action in ('assignment','GET_VAR','SET_VAR'):
            with self.subTest(action=action):
                ctx=context(step=1000,iterations=8)
                program,_=compile_program('b=a' if action=='assignment' else call(action),
                    decl='a:POSITION b:JOINTPOS1 e,s:INTEGER',context=ctx)
                program._state.values.update(A=point(5000),E=0,S=77)
                data=program.run()
                self.assertAlmostEqual(data['B']['axes'][0],5000,delta=.01)
                if action!='assignment':self.assertEqual(data['S'],0)
                self.assertEqual(ctx.robot.current.joints.values,[0.])

    def test_source_array_assignment_and_named_variable_batches(self):
        for action in ('assignment','GET_VAR','SET_VAR'):
            with self.subTest(action=action):
                program,_=compile_program('b=a' if action=='assignment' else call(action),
                    decl='a:ARRAY[2]OF POSITION b:ARRAY[2]OF JOINTPOS1 e,s:INTEGER',
                    context=context(step=1000,iterations=8))
                program._state.values.update(E=0,S=77)
                program._state.values['A'].values[:]=[point(5000),point(-5000)]
                data=program.run()
                for row,expected in zip(data['B'],(5000,-5000)):
                    self.assertAlmostEqual(row['axes'][0],expected,delta=.01)
                if action!='assignment':self.assertEqual(data['S'],0)

    def test_explicit_inverse_and_reachability_share_the_limit(self):
        body="CNV_STR_CONF('N',c,s) f=POS(0,0,0,0,0,0,c) p=POS(0,0,5000,0,0,0,c) "
        body+='j=CURJPOS(0,0) e[1]=0 e[2]=0 e[3]=0 '
        body+='POS2JOINT(j,p,f,f,0,c,e,out,s) hit=IN_RANGE(p) CHECK_EPOS(p,f,f,checked)'
        for grouped in (False,True):
            with self.subTest(grouped=grouped):
                program,_=compile_program(body,decl='c:CONFIG f,p:POSITION j,out:JOINTPOS1 '
                    'e:ARRAY[3]OF REAL s,checked:INTEGER hit:BOOLEAN',
                    context=context(step=1000,iterations=8,groups=grouped))
                data=program.run()
                self.assertEqual((data['S'],data['CHECKED'],data['HIT']),(0,0,True))
                self.assertAlmostEqual(data['OUT']['axes'][0],5000,delta=.01)

    def test_failed_batch_preserves_receiver_and_status(self):
        program,_=compile_program(call('GET_VAR'),decl='a:ARRAY[2]OF POSITION '
            'b:ARRAY[2]OF JOINTPOS1 e,s:INTEGER',context=context(step=1000,iterations=8))
        program._state.values.update(E=0,S=77)
        program._state.values['A'].values[:]=[point(5000),point(20000)]
        for value in program._state.values['B'].values:value.values[:]=[7.]
        before=program.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'IK solution'):program.run()
        self.assertEqual(program.snapshot(),before)

    def test_unreachable_checks_preserve_supplied_current_state(self):
        ctx=context(step=1000,iterations=8);before=ctx.to_config()['robot']
        program,_=compile_program('hit=IN_RANGE(p) CHECK_EPOS(p,f,f,s)',
            decl='p,f:POSITION hit:BOOLEAN s:INTEGER',context=ctx)
        program._state.values.update(P=point(20000),F=point(0),S=77)
        data=program.run()
        self.assertEqual((data['HIT'],data['S']),(False,1))
        self.assertEqual(ctx.to_config()['robot'],before)

    def test_exhausted_source_budget_retains_destination(self):
        program,_=compile_program('b=a',decl='a:POSITION b:JOINTPOS1',context=context())
        program._state.values['A']=point(5000);program._state.values['B'].values[:]=[7.]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):program.run(max_steps=2)
        self.assertEqual(program.snapshot()['B']['axes'],[7.])


if __name__=='__main__':unittest.main()
