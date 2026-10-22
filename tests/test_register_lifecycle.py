"""Authored register introspection, grouped clearing and simulation lifecycle."""
import json
import tempfile
from pathlib import Path
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run,pose
from tests.test_project_scheduler import source


def joint(axes):
    value=rt.JointPosition(('JOINTPOS',axes));value.values[:]=[float(i) for i in range(axes)];return value


class PositionLifecycleTests(unittest.TestCase):
    def context(self,initial=None,**options):
        return rt.ExecutionContext(positions=rt.PositionRegisters(3,initial,**options))

    def test_representation_codes_and_axes(self):
        cartesian=pose(10)
        for spec,expected in ((('POSITION',),(1,0)),(('XYZWPR',),(2,0)),(('XYZWPREXT',),(6,3))):
            with self.subTest(spec=spec):
                with rt._numeric_scope('pythonic'): value=rt.convert_position(spec,cartesian)
                ctx=self.context({1:value})
                state=run('POS_REG_TYPE(1,1,n,a,s)',decl='n,a,s: INTEGER',context=ctx)
                self.assertEqual((state['N'],state['A'],state['S']),(*expected,0))
                self.assertEqual(ctx.positions.read(1)[1].spec,spec)

    def test_every_joint_width_reports_stored_axes(self):
        for axes in range(1,10):
            with self.subTest(axes=axes):
                ctx=self.context({1:joint(axes)})
                state=run('POS_REG_TYPE(1,n,a,s) j=GET_JPOS_REG(1,s) POS_REG_TYPE(1,n,a,s)',decl='n,a,s: INTEGER j: JOINTPOS',context=ctx)
                self.assertEqual((state['N'],state['A'],state['S']),(9,axes,0))
                self.assertEqual(ctx.positions.read(1)[1].spec,('JOINTPOS',axes))
                self.assertEqual(state['J']['axes'],[float(i) for i in range(axes)]+[0.]*(9-axes))

    def test_missing_register_preserves_representation_outputs(self):
        state=run('n=7 a=8 POS_REG_TYPE(1,n,a,s)',decl='n,a,s: INTEGER',context=self.context())
        self.assertEqual((state['N'],state['A'],state['S']),(7,8,1))

    def test_bad_number_or_group_preserves_outputs_and_bank(self):
        for number,group in ((0,1),(4,1),(1,0),(1,2),(1,-1)):
            with self.subTest(number=number,group=group):
                ctx=self.context({1:pose(10)});before=ctx.to_config()['positions']
                state=run(f'n=7 a=8 POS_REG_TYPE({number},{group},n,a,s)',decl='n,a,s: INTEGER',context=ctx)
                self.assertEqual((state['N'],state['A'],state['S']),(7,8,2));self.assertEqual(ctx.to_config()['positions'],before)

    def test_group_selects_independent_stored_representation(self):
        ctx=self.context({(1,1):pose(),(2,1):joint(2)},groups=(1,2))
        self.assertEqual(ctx.positions.describe(1,1),(0,2,0));self.assertEqual(ctx.positions.describe(1,2),(0,9,2))
        state=run('POS_REG_TYPE(1,2,n,a,s)',decl='n,a,s: INTEGER',context=ctx)
        self.assertEqual((state['N'],state['A'],state['S']),(9,2,0))

    def test_omitted_group_defaults_to_one_without_robot_context(self):
        state=run('POS_REG_TYPE(1,n,a,s)',decl='n,a,s: INTEGER',context=self.context({1:pose()}))
        self.assertEqual((state['N'],state['A'],state['S']),(2,0,0))

    def test_omitted_group_uses_current_root_group(self):
        ctx=self.context({(1,1):pose(),(2,1):joint(2)},groups=(1,2))
        ctx.robot=rt.RobotContext(current=rt.RobotState(joints=[0.]),active_group=2)
        state=run('POS_REG_TYPE(1,n,a,s)',decl='n,a,s: INTEGER',context=ctx)
        self.assertEqual((state['N'],state['A'],state['S']),(9,2,0))

    def test_source_group_overrides_context_default(self):
        ctx=self.context({(1,1):pose(),(2,1):joint(2)},groups=(1,2))
        ctx.robot=rt.RobotContext(current=rt.RobotState(joints=[0.]),active_group=2)
        state=run('POS_REG_TYPE(1,n,a,s)',decl='n,a,s: INTEGER p: XYZWPR IN GROUP[1]',context=ctx)
        self.assertEqual((state['N'],state['A'],state['S']),(2,0,0))

    def test_explicit_group_overrides_root_group(self):
        ctx=self.context({(1,1):pose(),(2,1):joint(2)},groups=(1,2))
        state=run('POS_REG_TYPE(1,2,n,a,s)',decl='n,a,s: INTEGER p: XYZWPR IN GROUP[1]',context=ctx)
        self.assertEqual((state['N'],state['A'],state['S']),(9,2,0))

    def test_linked_library_uses_callers_group_for_omission(self):
        ctx=self.context({(1,1):pose(),(2,1):joint(2)},groups=(1,2))
        routine='ROUTINE inspect: INTEGER VAR kind,axes,status: INTEGER BEGIN POS_REG_TYPE(1,kind,axes,status) RETURN axes END inspect'
        project=translate_project({'lib':source('LIB','',routines=routine),'main':source('MAIN','n=inspect()',decl='n: INTEGER p: XYZWPR IN GROUP[2]',routines='ROUTINE inspect: INTEGER FROM LIB')}).instantiate(context=ctx)
        self.assertEqual(project.run('MAIN')['MAIN']['values']['N'],2)

    def test_clear_one_group_retains_other_groups_and_comments(self):
        ctx=self.context({(1,1):pose(10),(2,1):joint(2),(1,2):pose(20)},groups=(1,2),comments={1:'keep'})
        state=run('CLR_POS_REG(1,2,s)',context=ctx)
        self.assertEqual(state['S'],0);self.assertEqual(ctx.positions.read(1,2),(1,None))
        self.assertEqual(ctx.positions.read(1,1)[1].values['X'],10.);self.assertEqual(ctx.positions.read(2,1)[1].values['X'],20.)
        self.assertEqual(ctx.positions.comments.read(1),(0,'keep'))

    def test_clear_zero_removes_all_configured_groups_of_one_register(self):
        ctx=self.context({(2,1):pose(),(3,1):joint(2),(3,2):pose(20)},groups=(2,3))
        state=run('CLR_POS_REG(1,0,s)',context=ctx)
        self.assertEqual(state['S'],0);self.assertEqual(set(ctx.positions.snapshot()),{(3,2)})

    def test_clear_absent_register_is_idempotent(self):
        ctx=self.context()
        for group in (0,1,0): self.assertEqual(run(f'CLR_POS_REG(1,{group},s)',context=ctx)['S'],0)
        self.assertEqual(ctx.positions.snapshot(),{})

    def test_bad_clear_range_preserves_bank(self):
        for number,group in ((0,0),(4,0),(1,-1),(1,2)):
            with self.subTest(number=number,group=group):
                ctx=self.context({1:pose(10)});before=ctx.to_config()['positions']
                self.assertEqual(run(f'CLR_POS_REG({number},{group},s)',context=ctx)['S'],2);self.assertEqual(ctx.to_config()['positions'],before)

    def test_inspect_clear_restore_pipeline(self):
        ctx=self.context({1:pose(10)})
        state=run('POS_REG_TYPE(1,n,a,s) old=n p=GET_POS_REG(1,s) CLR_POS_REG(1,0,s) POS_REG_TYPE(1,n,a,s) missing=s SET_EPOS_REG(1,p,s) POS_REG_TYPE(1,n,a,s)',decl='p: XYZWPREXT n,a,s,old,missing: INTEGER',context=ctx)
        self.assertEqual((state['OLD'],state['MISSING'],state['N'],state['A'],state['S']),(2,1,6,3,0))

    def test_get_after_clear_preserves_target_and_reports_absence(self):
        ctx=self.context({1:pose(10)})
        p,_=compile_program('p=GET_POS_REG(1,s) CLR_POS_REG(1,0,s) p=GET_POS_REG(1,s)',decl='p: XYZWPREXT s: INTEGER',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'absent'): p.run()
        self.assertEqual((p.snapshot()['S'],p.snapshot()['P']['X']),(1,10.))

    def test_persistence_retains_absence_other_groups_and_comment(self):
        ctx=self.context({(1,1):pose(),(2,1):joint(2)},groups=(1,2),comments={1:'keep'})
        run('CLR_POS_REG(1,1,s)',context=ctx)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'state.json';ctx.save(target);restored=rt.ExecutionContext.load(target)
        self.assertEqual(restored.to_config(),ctx.to_config());self.assertEqual(restored.positions.read(1,1),(1,None))
        self.assertEqual(restored.positions.describe(1,2),(0,9,2));self.assertEqual(restored.positions.comments.read(1),(0,'keep'))

    def test_context_is_shared_across_separate_program_runs(self):
        ctx=self.context({1:joint(2)})
        run('CLR_POS_REG(1,1,s)',context=ctx)
        self.assertEqual(run('POS_REG_TYPE(1,n,a,s)',decl='n,a,s: INTEGER',context=ctx)['S'],1)

    def test_host_api_rejects_non_integer_selectors_before_mutation(self):
        ctx=self.context({1:pose()});before=ctx.to_config()
        for method in (ctx.positions.describe,ctx.positions.clear):
            for arguments in ((True,1),(1,False),(1.,1),(1,1.)):
                with self.subTest(method=method,arguments=arguments),self.assertRaises(rt.KarelRuntimeError): method(*arguments)
        self.assertEqual(ctx.to_config(),before)


class LifecycleOwnershipTests(unittest.TestCase):
    def test_invalid_arity_and_exact_output_types(self):
        for body in ('POS_REG_TYPE(1,n,s)','POS_REG_TYPE(1,1,n,n,s,s)','CLR_POS_REG(1,s)','CLR_PORT_SIM(1,s)','POS_REG_TYPE(1,x,n,s)','POS_REG_TYPE(1,n,small,s)','POS_REG_TYPE(1,0,n,s)'):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,decl='n,s: INTEGER x: REAL small: SHORT')

    def test_output_alias_rejected_before_bank_access(self):
        for body in ('POS_REG_TYPE(1,n,n,s)','POS_REG_TYPE(1,1,n,s,s)','POS_REG_TYPE(1,a[1],a[1],s)'):
            with self.subTest(body=body):
                p,_=compile_program('n=7 s=8 '+body,decl='n,s: INTEGER a: ARRAY[2] OF INTEGER')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
                self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,8))

    def test_missing_service_preserves_outputs(self):
        for body in ('POS_REG_TYPE(1,n,a,s)','CLR_POS_REG(1,0,s)','CLR_PORT_SIM(10,1,s)'):
            with self.subTest(body=body):
                p,_=compile_program('n=7 a=8 s=9 '+body,decl='n,a,s: INTEGER')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit'): p.run()
                self.assertEqual((p.snapshot()['N'],p.snapshot()['A'],p.snapshot()['S']),(7,8,9))

    def test_inputs_captured_before_aliasing_outputs(self):
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(1,{1:pose()}))
        state=run('n=1 POS_REG_TYPE(n,n,a,s)',decl='n,a,s: INTEGER',context=ctx)
        self.assertEqual((state['N'],state['A'],state['S']),(2,0,0))

    def test_source_order_and_output_selectors_evaluated_once(self):
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(1,{1:joint(2)}))
        routines='ROUTINE regno: INTEGER BEGIN count=count*10+1 RETURN 1 END regno ROUTINE slot: INTEGER BEGIN count=count*10+2 RETURN 1 END slot'
        state=run('count=0 POS_REG_TYPE(regno(),a[slot()],axes,s)',decl='count,axes,s: INTEGER a: ARRAY[2] OF INTEGER',routines=routines,context=ctx)
        self.assertEqual((state['COUNT'],state['A'][0],state['AXES'],state['S']),(12,9,2,0))

    def test_direct_and_transitive_for_counter_guards(self):
        for body,routines in (('FOR n=1 TO 2 DO POS_REG_TYPE(1,n,a,s) ENDFOR',''),('FOR n=1 TO 2 DO inspect(n) ENDFOR','ROUTINE inspect(out: INTEGER) BEGIN POS_REG_TYPE(1,out,a,s) END inspect'),('FOR n=1 TO 2 DO inspect() ENDFOR','ROUTINE inspect BEGIN POS_REG_TYPE(1,n,a,s) END inspect'),('CONDITION[1]: WHEN TRUE DO POS_REG_TYPE(1,n,a,s) ENDCONDITION FOR n=1 TO 2 DO ENDFOR','')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught: compile_program(body,decl='n,a,s: INTEGER',routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_other_lifecycle_status_outputs_cannot_write_for_counter(self):
        for operation in ('CLR_POS_REG(1,0,n)','CLR_PORT_SIM(10,1,n)'):
            with self.subTest(operation=operation),self.assertRaises(TranslationError): compile_program('FOR n=1 TO 2 DO '+operation+' ENDFOR')

    def test_user_routines_keep_precedence(self):
        for name in ('POS_REG_TYPE','CLR_POS_REG','CLR_PORT_SIM'):
            with self.subTest(name=name):
                state=run(f'{name}(7)',routines=f'ROUTINE {name}(value: INTEGER) BEGIN n=value END {name}')
                self.assertEqual(state['N'],7)

    def test_failure_retains_prior_effects_and_cleans_routine_frames(self):
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(1,{1:pose()}))
        p,_=compile_program('helper()',decl='n,s: INTEGER',routines='ROUTINE helper VAR a: ARRAY[1] OF INTEGER BEGIN CLR_POS_REG(1,0,s) n=7 POS_REG_TYPE(1,a[2],n,s) END helper',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(ctx.positions.read(1),(1,None));self.assertEqual(p.snapshot()['N'],7)
        self.assertEqual(p._state.local_frames,[]);self.assertEqual(p._state.call_depth,0)

    def test_report_policy_and_value_free_observations(self):
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(1,{1:pose()}))
        p,result=compile_program('POS_REG_TYPE(1,n,a,s) CLR_POS_REG(1,0,s)',decl='n,a,s: INTEGER',context=ctx)
        p.run();self.assertFalse(result.report['register_lifecycle_policy']['controller_validated'])
        self.assertEqual([row['operation'] for row in p.service_requests],['POS_REG_TYPE','CLR_POS_REG'])
        self.assertTrue(all(set(row)=={'operation','line','outcome'} and row['outcome']=='completed' for row in p.service_requests))


class PortUnsimulationTests(unittest.TestCase):
    def context(self,initial=None,**options):
        return rt.ExecutionContext(ports=rt.PortBank({'DIN':2,'DOUT':2},initial,type_codes={10:'DIN',20:'DOUT'},**options))

    def test_clear_disables_input_writes_and_retains_last_value(self):
        ctx=self.context()
        state=run('SET_PORT_SIM(10,1,1,s) CLR_PORT_SIM(10,1,s) GET_PORT_SIM(10,1,n,s) SET_PORT_VAL(10,1,0,s) flag=DIN[1]',decl='n,s: INTEGER flag: BOOLEAN',context=ctx)
        self.assertEqual((state['N'],state['S'],state['FLAG']),(0,4,True));self.assertEqual(ctx.ports.simulated,set())

    def test_clear_one_address_keeps_other_flags_and_comments(self):
        ctx=self.context({('DIN',1):True,('DIN',2):False},simulated=[('DIN',1),('DIN',2)],comments={('DIN',1):'sensor'})
        run('CLR_PORT_SIM(10,1,s)',context=ctx)
        self.assertEqual(ctx.ports.simulated,{('DIN',2)});self.assertEqual(ctx.ports.comments,{('DIN',1):'sensor'})
        self.assertEqual(ctx.ports.snapshot(),{('DIN',1):True,('DIN',2):False})

    def test_clear_is_idempotent_and_does_not_initialize_value(self):
        ctx=self.context(simulated=[('DIN',1)])
        state=run('CLR_PORT_SIM(10,1,s) CLR_PORT_SIM(10,1,s) GET_PORT_SIM(10,1,n,s)',context=ctx)
        self.assertEqual((state['N'],state['S'],ctx.ports.snapshot()),(0,0,{}))

    def test_output_remains_writable_after_unsimulation(self):
        ctx=self.context()
        state=run('SET_PORT_SIM(20,1,1,s) CLR_PORT_SIM(20,1,s) SET_PORT_VAL(20,1,0,s) flag=DOUT[1]',decl='flag: BOOLEAN n,s: INTEGER',context=ctx)
        self.assertEqual((state['S'],state['FLAG']),(0,False))

    def test_host_update_after_unsimulation_is_visible(self):
        ctx=self.context({('DIN',1):True},simulated=[('DIN',1)])
        run('CLR_PORT_SIM(10,1,s)',context=ctx);ctx.ports.update('DIN',1,False)
        self.assertFalse(run('flag=DIN[1]',decl='flag: BOOLEAN',context=ctx)['FLAG'])

    def test_invalid_address_preserves_simulation_and_values(self):
        for code,number in ((99,1),(10,0),(10,3)):
            with self.subTest(code=code,number=number):
                ctx=self.context({('DIN',1):True},simulated=[('DIN',1)]);before=ctx.to_config()['ports']
                self.assertEqual(run(f'CLR_PORT_SIM({code},{number},s)',context=ctx)['S'],2);self.assertEqual(ctx.to_config()['ports'],before)

    def test_missing_mapping_fails_without_changing_status(self):
        ctx=rt.ExecutionContext(ports=rt.PortBank({'DIN':1},simulated=[('DIN',1)]))
        p,_=compile_program('s=7 CLR_PORT_SIM(10,1,s)',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type_codes'): p.run()
        self.assertEqual(p.snapshot()['S'],7);self.assertEqual(ctx.ports.simulated,{('DIN',1)})

    def test_cleared_flags_survive_json_roundtrip_and_can_be_reenabled(self):
        ctx=self.context({('DIN',1):True},simulated=[('DIN',1)])
        run('CLR_PORT_SIM(10,1,s)',context=ctx)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.to_config(),ctx.to_config());self.assertEqual(restored.ports.simulated,set())
        state=run('SET_PORT_SIM(10,1,0,s) GET_PORT_SIM(10,1,n,s)',context=restored)
        self.assertEqual((state['N'],state['S'],restored.ports.read('DIN',1)),(1,0,False))


if __name__=='__main__': unittest.main()
