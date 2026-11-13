"""Authored mixed-representation position-register getters with explicit models."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.kinematics import pose
from tests.test_cartesian_interfaces import value as cartesian
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint
from tests.test_project_scheduler import source


def point(kind='XYZWPREXT'):
    return cartesian(kind,(100.,0.,42.),(0.,0.,0.),(42.,0.,0.) if kind=='XYZWPREXT' else (0.,0.,0.))


def context():
    ctx=rt.ExecutionContext.from_config({'robot':{'groups':{
        '1':{'dh':[{'a':10},{'a':10}]},
        '2':{'dh':[{'a':100},{'type':'prismatic','min':0,'max':100}], 'external_axes':1,
             'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,42.]}}}},'active_group':1}})
    ctx.positions=rt.PositionRegisters(2,{(1,1):joint([0.,0.]),(2,1):joint([0.,42.]),(2,2):point()},groups=(1,2))
    return ctx


def build(operation='GET_POS_REG',*,ctx=None,body=None,decl=None,**options):
    ctx=context() if ctx is None else ctx
    target='p' if operation=='GET_POS_REG' else 'j';number=1 if target=='p' else 2
    owner,result=compile_program(body or f'{target}={operation}({number},s,2)',
        decl=decl or 'p:XYZWPREXT j:JOINTPOS s,n:INTEGER',context=ctx,**options)
    owner._state.values.update(S=99,N=0)
    return owner,result,ctx


class RegisterModelValueTests(unittest.TestCase):
    def test_both_getters_in_synchronous_and_cooperative_modes(self):
        for operation in ('GET_POS_REG','GET_JPOS_REG'):
            for cooperative in (False,True):
                with self.subTest(operation=operation,cooperative=cooperative):
                    p,_,ctx=build(operation,cooperative=cooperative);before=ctx.positions.snapshot();data=p.run()
                    self.assertEqual(data['S'],0)
                    if operation=='GET_POS_REG':self.assertEqual([data['P'][name] for name in ('X','Z','EXT1')],[100.,42.,42.])
                    else:self.assertEqual(data['J']['axes'],[0.,42.]+[0.]*7)
                    self.assertEqual({key:rt.snapshot_value(value) for key,value in ctx.positions.snapshot().items()},
                                     {key:rt.snapshot_value(value) for key,value in before.items()})

    def test_explicit_group_overrides_callers_model_group(self):
        p,_,_=build(body='p=GET_POS_REG(1,s,2)');self.assertEqual(p.run()['P']['X'],100.)
        p,_,_=build(body='p=GET_POS_REG(1,s,1)');self.assertEqual(p.run()['P']['X'],20.)

    def test_omitted_group_uses_calling_root_group(self):
        p,_,_=build(body='p=GET_POS_REG(1,s)',decl='p:XYZWPREXT IN GROUP[2] j:JOINTPOS s,n:INTEGER')
        self.assertEqual(p.run()['P']['EXT1'],42.)

    def test_plain_cartesian_forms_use_zero_external_values(self):
        for kind in ('POSITION','XYZWPR','XYZWPREXT'):
            with self.subTest(kind=kind):
                ctx=context();ctx.robot.groups[2]=rt.ExecutionContext.from_config({'robot':{
                    'dh':[{'a':100},{'type':'prismatic','min':0,'max':100}],
                    'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,42.]}}}}).robot
                ctx.positions.write(2,cartesian(kind,(100.,0.,42.),(0.,0.,0.)),2)
                p,_,_=build('GET_JPOS_REG',ctx=ctx);self.assertEqual(p.run()['J']['axes'],[0.,42.]+[0.]*7)

    def test_forward_adapter_config_and_external_values_are_retained(self):
        ctx=context();value=pose();config=value.values['CONFIG_DATA'].clone();config.values['CFG_FLIP']=True
        ctx.robot.groups[2].forward=lambda *_:(value,config,[7.,8.,9.])
        p,_,_=build(ctx=ctx);data=p.run()['P']
        self.assertEqual([data[name] for name in ('EXT1','EXT2','EXT3')],[7.,8.,9.]);self.assertTrue(data['CONFIG_DATA']['CFG_FLIP'])

    def test_inverse_seed_comes_from_selected_group_not_destination(self):
        ctx=context();seen=[]
        def inverse(seed,*args):seen.append(seed.values[:]);return joint([0.,42.])
        ctx.robot.groups[2].inverse=inverse;p,_,_=build('GET_JPOS_REG',ctx=ctx)
        p._state.values['J']=joint([7.]*9);p.run();self.assertEqual(seen,[[0.,42.]])

    def test_matching_getters_do_not_call_models(self):
        ctx=context()
        def unexpected(*args):raise AssertionError('matching representation invoked model')
        ctx.robot.groups[2].forward=unexpected;ctx.robot.groups[2].inverse=unexpected
        p,_,_=build(ctx=ctx,body='p=GET_POS_REG(2,s,2) j=GET_JPOS_REG(1,s,2)')
        self.assertEqual(p.run()['J']['axes'],[0.,42.]+[0.]*7)

    def test_linked_library_explicit_group_is_retained(self):
        ctx=context();files={'main':source('MAIN','read_stored',routines='ROUTINE read_stored FROM LIB'),
            'lib':source('LIB','',decl='p:XYZWPREXT j:JOINTPOS s:INTEGER',routines=
                'ROUTINE read_stored BEGIN p=GET_POS_REG(1,s,2) j=GET_JPOS_REG(2,s,2) END read_stored')}
        instance=translate_project(files).instantiate(context=ctx);data=instance.run('MAIN')['LIB']['values']
        self.assertEqual(data['J']['axes'],[0.,42.]+[0.]*7);self.assertEqual(data['P']['EXT1'],42.)

    def test_handler_uses_the_same_bridge(self):
        p,_,_=build(body='CONDITION[1]: WHEN TRUE DO p=GET_POS_REG(1,s,2) ENDCONDITION ENABLE CONDITION[1] n=1')
        self.assertEqual(p.run()['P']['EXT1'],42.)

    def test_results_and_saved_values_are_independent(self):
        p,_,ctx=build(body='p=GET_POS_REG(1,s,2) j=GET_JPOS_REG(2,s,2) p.x=999 j[2]=9');p.run()
        self.assertEqual(ctx.positions.read(1,2)[1].values,[0.,42.])
        self.assertEqual(ctx.positions.read(2,2)[1].values['X'],100.)
        saved=json.loads(json.dumps(ctx.to_config()));other=rt.ExecutionContext.from_config(saved)
        self.assertEqual(other.to_config(),saved)


class RegisterModelPublicationTests(unittest.TestCase):
    def callback(self,change,operation='GET_POS_REG'):
        ctx=context();holder={}
        def forward(*args):change(ctx,holder['p']);value=pose();return value,value.values['CONFIG_DATA'],[0.,0.,0.]
        def inverse(*args):change(ctx,holder['p']);return joint([0.,42.])
        ctx.robot.groups[2].forward=forward;ctx.robot.groups[2].inverse=inverse
        p,_,_=build(operation,ctx=ctx);holder['p']=p;return p,ctx

    def test_selected_source_replacement_edit_or_removal_prevents_publication(self):
        for operation,key in (('GET_POS_REG',(2,1)),('GET_JPOS_REG',(2,2))):
            for change in ('replace','edit','remove'):
                with self.subTest(operation=operation,change=change):
                    def edit(ctx,p):
                        if change=='remove':ctx.positions.values.pop(key)
                        elif change=='replace':ctx.positions.values[key]=joint([0.,42.]) if key[1]==1 else point()
                        elif key[1]==1:ctx.positions.values[key].values[0]=9.
                        else:ctx.positions.values[key].values['X']=999.
                    p,ctx=self.callback(edit,operation);before=p.snapshot()
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'changed during preparation'):p.run()
                    self.assertEqual(p.snapshot(),before)

    def test_position_bank_and_model_group_replacements_are_retained(self):
        changes=(lambda c,p:setattr(c,'positions',rt.PositionRegisters(2,groups=(1,2))),
                 lambda c,p:setattr(c.positions,'values',dict(c.positions.values)),
                 lambda c,p:setattr(c.positions,'count',3),
                 lambda c,p:setattr(c.positions,'groups',(1.,2)),
                 lambda c,p:c.robot.groups.__setitem__(2,context().robot.groups[2]))
        for change in changes:
            with self.subTest(change=change):
                p,ctx=self.callback(change);before=p.snapshot()
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(p.snapshot(),before)

    def test_status_reference_storage_cannot_be_rebound(self):
        holder={};other={'status':99}
        p,ctx=self.callback(lambda c,p:setattr(holder['ref'],'storage',other));original={'status':99}
        ref=rt.Reference(('INTEGER',),original,'status');holder['ref']=ref;p._state.values['S']=ref
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((original['status'],other['status']),(99,99))

    def test_status_cannot_overlap_source_config_or_bank_count(self):
        for metadata in (False,True):
            with self.subTest(metadata=metadata):
                p,_,ctx=build('GET_JPOS_REG');bank=ctx.positions
                storage,key=(bank.__dict__,'count') if metadata else (bank.values[2,2].values['CONFIG_DATA'].values,'CFG_TURN_NO1')
                before=storage[key];p._state.values['S']=rt.Reference(('INTEGER',),storage,key)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
                self.assertEqual(storage[key],before)

    def test_status_cannot_overlap_a_stored_joint_axis(self):
        p,_,ctx=build();values=ctx.positions.values[2,1].values;values[0]=0
        p._state.values['S']=rt.Reference(('INTEGER',),values,0)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
        self.assertEqual(values,[0,42.])

    def test_unrelated_register_and_program_edits_remain_on_success(self):
        def change(ctx,p):ctx.positions.write(2,joint([1.,2.]),1);p._state.values['N']=7
        p,ctx=self.callback(change);data=p.run()
        self.assertEqual((data['N'],data['S']),(7,0));self.assertEqual(ctx.positions.read(2,1)[1].values,[1.,2.])

    def test_caught_abort_still_prevents_result_and_status_publication(self):
        def change(ctx,p):
            try:p._state.abort(17)
            except rt.KarelAbort:pass
        p,ctx=self.callback(change);before=p.snapshot()
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot(),before)


class RegisterModelFailureTests(unittest.TestCase):
    def test_without_robot_context_existing_type_failure_remains(self):
        for operation in ('GET_POS_REG','GET_JPOS_REG'):
            with self.subTest(operation=operation):
                ctx=context();ctx.robot=None;p,_,_=build(operation,ctx=ctx)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'different representation'):p.run()
                self.assertEqual(p.snapshot()['S'],3)

    def test_missing_inverse_seed_preserves_status_and_assignment(self):
        ctx=context();ctx.robot.groups[2].current=None;p,_,_=build('GET_JPOS_REG',ctx=ctx);before=p.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'current joints'):p.run()
        self.assertEqual(p.snapshot(),before)

    def test_source_charges_precede_model_and_output_publication(self):
        for operation in ('GET_POS_REG','GET_JPOS_REG'):
            with self.subTest(operation=operation):
                p,_,ctx=build(operation);before=p.snapshot()
                with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=2)
                self.assertEqual(p.snapshot(),before)

    def test_inverse_evaluations_keep_source_budget_charges(self):
        ctx=context();ctx.robot.groups[2]=rt.ExecutionContext.from_config({'robot':{
            'dh':[{'a':100},{'type':'prismatic','min':0,'max':100}],
            'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,0.]}}}}).robot
        model=ctx.robot.groups[2].model
        ctx.positions.write(2,cartesian('XYZWPREXT',(100.,0.,87.),(0.,0.,0.),(87.,0.,0.)),2)
        p,_,_=build('GET_JPOS_REG',ctx=ctx);before=p.snapshot()
        units=rt._validate_data_schema(ctx.positions.values[2,2].spec)
        with patch.object(model,'chain',wraps=model.chain) as calls:
            with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=units+3)
            self.assertEqual(calls.call_count,1)
        self.assertEqual(p.snapshot(),before)

    def test_unreachable_pose_preserves_result_and_status(self):
        ctx=context();ctx.positions.values[2,2].values['X']=20000.
        p,_,_=build('GET_JPOS_REG',ctx=ctx);before=p.snapshot()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'IK solution'):p.run()
        self.assertEqual(p.snapshot(),before)

    def test_getter_read_preserves_stored_representation_and_width(self):
        p,_,ctx=build(body='p=GET_POS_REG(1,s,2) j=GET_JPOS_REG(2,s,2)');p.run()
        self.assertEqual(ctx.positions.read(1,2)[1].spec,('JOINTPOS',2))
        self.assertEqual(ctx.positions.read(2,2)[1].spec,('XYZWPREXT',))

    def test_report_exposes_group_and_retained_publication_contract(self):
        _,result,_=build();policy=result.report['position_register_model_policy']
        self.assertIn('selected register group',policy['group']);self.assertIn('status location/data',policy['publication'])
        self.assertFalse(policy['controller_validated'])


if __name__=='__main__':unittest.main()
