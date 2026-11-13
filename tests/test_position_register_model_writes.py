"""Authored mixed-representation register setters and staged publication."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint
from tests.test_cartesian_interfaces import value as cartesian
from tests.test_position_register_models import context,point
from tests.test_project_scheduler import source


def build(operation='SET_POS_REG',*,ctx=None,number=None,body=None,decl=None,**options):
    ctx=context() if ctx is None else ctx
    number=(2 if operation=='SET_JPOS_REG' else 1) if number is None else number
    value='p' if operation=='SET_JPOS_REG' else 'j'
    owner,result=compile_program(body or f'{operation}({number},{value},s,2)',
        decl=decl or 'j:JOINTPOS2 p:XYZWPREXT s,n:INTEGER',context=ctx,**options)
    owner._state.values.update(J=joint([0.,42.]),P=point(),S=99,N=0)
    return owner,result,ctx


class RegisterModelWriteValues(unittest.TestCase):
    def test_all_three_setters_in_both_execution_modes(self):
        for operation in ('SET_POS_REG','SET_EPOS_REG','SET_JPOS_REG'):
            for cooperative in (False,True):
                with self.subTest(operation=operation,cooperative=cooperative):
                    p,_,ctx=build(operation,cooperative=cooperative)
                    number=2 if operation=='SET_JPOS_REG' else 1
                    old=ctx.positions.values[2,number];p.run();stored=ctx.positions.values[2,number]
                    self.assertIsNot(stored,old);self.assertEqual(p.snapshot()['S'],0)
                    if operation=='SET_JPOS_REG':self.assertEqual((stored.spec,stored.values),(('JOINTPOS',9),[0.,42.]+[0.]*7))
                    else:
                        self.assertEqual(stored.spec,('XYZWPREXT',))
                        self.assertEqual([stored.values[name] for name in ('X','Z','EXT1')],[100.,42.,42.])
                    self.assertEqual(ctx.robot.groups[2].current.joints.values,[0.,42.])

    def test_absent_register_is_populated_after_conversion(self):
        for operation in ('SET_POS_REG','SET_JPOS_REG'):
            with self.subTest(operation=operation):
                ctx=context();ctx.positions=rt.PositionRegisters(3,groups=(1,2))
                p,_,_=build(operation,ctx=ctx,number=3);p.run()
                self.assertEqual(ctx.positions.values[2,3].spec,('JOINTPOS',9) if operation=='SET_JPOS_REG' else ('XYZWPREXT',))

    def test_omitted_group_uses_calling_root(self):
        p,_,ctx=build(body='SET_POS_REG(1,j,s)',decl='j:JOINTPOS2 IN GROUP[2] p:XYZWPREXT s,n:INTEGER')
        p.run();self.assertEqual(ctx.positions.values[2,1].values['EXT1'],42.)
        self.assertEqual(ctx.positions.values[1,1].spec,('JOINTPOS',2))

    def test_plain_cartesian_inputs_convert_without_inventing_external_axes(self):
        for kind in ('POSITION','XYZWPR','XYZWPREXT'):
            with self.subTest(kind=kind):
                ctx=context();ctx.robot.groups[2]=rt.ExecutionContext.from_config({'robot':{
                    'dh':[{'a':100},{'type':'prismatic','min':0,'max':100}],
                    'current':{'joints':{'type':['JOINTPOS',2],'value':[0.,42.]}}}}).robot
                p,_,_=build('SET_JPOS_REG',ctx=ctx,decl=f'j:JOINTPOS2 p:{kind} s,n:INTEGER')
                p._state.values['P']=cartesian(kind,(100.,0.,42.),(0.,0.,0.));p.run()
                self.assertEqual(ctx.positions.values[2,2].values,[0.,42.]+[0.]*7)

    def test_zero_padded_joint_input_is_accepted_without_discarding_axes(self):
        p,_,ctx=build(decl='j:JOINTPOS p:XYZWPREXT s,n:INTEGER');p._state.values['J']=joint([0.,42.]+[0.]*7)
        p.run();self.assertEqual(ctx.positions.values[2,1].values['EXT1'],42.)

    def test_forward_config_and_all_external_slots_are_preserved(self):
        ctx=context();value=point();config=value.values['CONFIG_DATA'].clone();config.values['CFG_FLIP']=True
        ctx.robot.groups[2].forward=lambda *_:(value,config,[7.,8.,9.])
        p,_,_=build(ctx=ctx);p.run();stored=ctx.positions.values[2,1]
        self.assertEqual([stored.values[name] for name in ('EXT1','EXT2','EXT3')],[7.,8.,9.])
        self.assertTrue(stored.values['CONFIG_DATA'].values['CFG_FLIP'])

    def test_matching_input_paths_do_not_call_models_and_retain_width(self):
        ctx=context()
        def unexpected(*args):raise AssertionError('matching setter invoked a model')
        ctx.robot.groups[2].forward=unexpected;ctx.robot.groups[2].inverse=unexpected
        p,_,_=build(ctx=ctx,body='SET_JPOS_REG(1,j,s,2) SET_POS_REG(2,p,s,2) SET_EPOS_REG(2,p,s,2)');p.run()
        self.assertEqual(ctx.positions.values[2,1].spec,('JOINTPOS',2))
        self.assertEqual(ctx.positions.values[2,2].spec,('XYZWPREXT',))

    def test_number_input_status_and_group_selectors_run_once_before_conversion(self):
        ctx=context();holder={};original=ctx.robot.groups[2].forward;seen=[]
        def forward(joints,*args):
            holder['p']._state.values['TRACE']+='F';seen.append(joints.values[:]);return original(joints,*args)
        ctx.robot.groups[2].forward=forward
        routines="ROUTINE number:INTEGER BEGIN trace=trace+'N' RETURN 1 END number "
        routines+="ROUTINE value:JOINTPOS2 BEGIN trace=trace+'V' RETURN j END value "
        routines+="ROUTINE slot:INTEGER BEGIN trace=trace+'S' j[2]=10 RETURN 1 END slot "
        routines+="ROUTINE grp:INTEGER BEGIN trace=trace+'G' RETURN 2 END grp"
        p,_,_=build(ctx=ctx,body='SET_POS_REG(number,value,codes[slot],grp)',
            decl='j:JOINTPOS2 p:XYZWPREXT s,n:INTEGER codes:ARRAY[1]OF INTEGER trace:STRING[16]',routines=routines)
        p._state.values['TRACE']='';holder['p']=p;data=p.run()
        self.assertEqual((data['TRACE'],seen,data['J']['axes']),('NVSGF',[[0.,42.]],[0.,10.]))
        self.assertEqual(ctx.positions.values[2,1].values['EXT1'],42.)

    def test_linked_library_uses_explicit_register_group(self):
        ctx=context();files={'main':source('MAIN','store',routines='ROUTINE store FROM LIB'),
            'lib':source('LIB','',decl='s:INTEGER',routines='ROUTINE store VAR j:JOINTPOS2 p:XYZWPREXT '
                'BEGIN j=CURJPOS(0,0,2) SET_POS_REG(1,j,s,2) p=GET_POS_REG(1,s,2) SET_JPOS_REG(2,p,s,2) END store')}
        load=translate_project(files).instantiate(context=ctx);load.run('MAIN')
        self.assertEqual(ctx.positions.values[2,1].spec,('XYZWPREXT',))
        self.assertEqual(ctx.positions.values[2,2].values,[0.,42.]+[0.]*7)

    def test_handler_uses_staged_write(self):
        p,_,ctx=build(body='CONDITION[1]: WHEN TRUE DO SET_POS_REG(1,j,s,2) ENDCONDITION ENABLE CONDITION[1] n=1')
        p.run();self.assertEqual(ctx.positions.values[2,1].values['EXT1'],42.)

    def test_context_json_retains_written_types_and_values(self):
        p,_,ctx=build(body='SET_POS_REG(1,j,s,2) SET_JPOS_REG(2,p,s,2)');p.run()
        saved=json.loads(json.dumps(ctx.to_config()));other=rt.ExecutionContext.from_config(saved)
        self.assertEqual(other.to_config(),saved)
        self.assertEqual((other.positions.values[2,1].spec,other.positions.values[2,2].spec),(('XYZWPREXT',),('JOINTPOS',9)))


class RegisterModelWritePublication(unittest.TestCase):
    def callback(self,change,operation='SET_POS_REG',*,number=None,ctx=None):
        ctx=context() if ctx is None else ctx;holder={};seen=[]
        def forward(*args):
            seen.append(ctx.positions.values.copy());change(ctx,holder['p']);value=point()
            return value,value.values['CONFIG_DATA'],[42.,0.,0.]
        def inverse(*args):seen.append(ctx.positions.values.copy());change(ctx,holder['p']);return joint([0.,42.])
        ctx.robot.groups[2].forward=forward;ctx.robot.groups[2].inverse=inverse
        p,_,_=build(operation,ctx=ctx,number=number);holder['p']=p;return p,ctx,seen

    def test_existing_destination_changes_are_preserved_without_status_publication(self):
        for operation,key in (('SET_POS_REG',(2,1)),('SET_JPOS_REG',(2,2))):
            for kind in ('replace','edit','remove'):
                with self.subTest(operation=operation,kind=kind):
                    def change(ctx,p):
                        if kind=='remove':ctx.positions.values.pop(key)
                        elif kind=='replace':ctx.positions.values[key]=joint([0.,42.]) if key[1]==1 else point()
                        elif key[1]==1:ctx.positions.values[key].values[0]=9.
                        else:ctx.positions.values[key].values['X']=999.
                    p,ctx,seen=self.callback(change,operation);before=p.snapshot()
                    with self.assertRaises(rt.KarelRuntimeError):p.run()
                    self.assertEqual(p.snapshot(),before);self.assertEqual(len(seen),1)

    def test_newly_populated_destination_is_not_overwritten(self):
        ctx=context();ctx.positions=rt.PositionRegisters(3,groups=(1,2))
        p,ctx,_=self.callback(lambda c,p:c.positions.write(3,joint([7.,8.]),2),number=3,ctx=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((ctx.positions.values[2,3].values,p.snapshot()['S']),([7.,8.],99))

    def test_bank_metadata_and_model_group_replacements_reject(self):
        changes=(lambda c,p:setattr(c.positions,'values',dict(c.positions.values)),
                 lambda c,p:setattr(c.positions,'count',3),lambda c,p:setattr(c.positions,'groups',(1.,2)),
                 lambda c,p:c.robot.groups.__setitem__(2,context().robot.groups[2]))
        for change in changes:
            with self.subTest(change=change):
                p,ctx,_=self.callback(change);old=ctx.positions.values[2,1]
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(p.snapshot()['S'],99);self.assertIs(ctx.positions.values[2,1],old)

    def test_status_reference_binding_is_retained(self):
        holder={};other={'status':99}
        p,ctx,_=self.callback(lambda c,p:setattr(holder['ref'],'storage',other));old=ctx.positions.values[2,1]
        storage={'status':99};ref=rt.Reference(('INTEGER',),storage,'status');holder['ref']=ref;p._state.values['S']=ref
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((storage['status'],other['status']),(99,99));self.assertIs(ctx.positions.values[2,1],old)

    def test_status_aliases_are_rejected_even_when_model_is_absent(self):
        for missing in (False,True):
            with self.subTest(missing=missing):
                p,_,ctx=build('SET_JPOS_REG');ctx.robot=None if missing else ctx.robot
                storage=ctx.positions.values[2,2].values['CONFIG_DATA'].values;storage['CFG_TURN_NO1']=1
                p._state.values['S']=rt.Reference(('INTEGER',),storage,'CFG_TURN_NO1')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
                self.assertEqual(storage['CFG_TURN_NO1'],1)

    def test_unrelated_source_edits_remain_after_snapshot(self):
        p,ctx,_=self.callback(lambda c,p:p._state.values['P'].values.__setitem__('X',999.),'SET_JPOS_REG')
        p.run();self.assertEqual((p.snapshot()['P']['X'],ctx.positions.values[2,2].values),
                                (999.,[0.,42.]+[0.]*7))

    def test_caught_abort_does_not_publish_destination_or_status(self):
        def change(ctx,p):
            try:p._state.abort(17)
            except rt.KarelAbort:pass
        p,ctx,_=self.callback(change);old=ctx.positions.values[2,1]
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertIs(ctx.positions.values[2,1],old);self.assertEqual(p.snapshot()['S'],99)


class RegisterModelWriteFailures(unittest.TestCase):
    def test_without_robot_new_forms_return_type_status(self):
        for operation in ('SET_POS_REG','SET_EPOS_REG','SET_JPOS_REG'):
            with self.subTest(operation=operation):
                p,_,ctx=build(operation);ctx.robot=None;before=ctx.positions.snapshot();self.assertEqual(p.run()['S'],3)
                self.assertEqual({key:rt.snapshot_value(value) for key,value in ctx.positions.snapshot().items()},
                                 {key:rt.snapshot_value(value) for key,value in before.items()})

    def test_invalid_address_returns_status_before_model(self):
        for group in (2,3):
            with self.subTest(group=group):
                p,_,ctx=build(body=f'SET_POS_REG(3,j,s,{group})');self.assertEqual(p.run()['S'],2)
                self.assertNotIn((group,3),ctx.positions.values)

    def test_invalid_address_status_cannot_mutate_bank_count(self):
        ctx=context();ctx.positions=rt.PositionRegisters(3,groups=(1,2));ctx.robot=None
        p,_,_=build(ctx=ctx,number=4);p._state.values['S']=rt.Reference(('INTEGER',),ctx.positions.__dict__,'count')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
        self.assertEqual(ctx.positions.count,3);self.assertNotIn((2,4),ctx.positions.values)

    def test_missing_inverse_seed_keeps_status_and_destination(self):
        p,_,ctx=build('SET_JPOS_REG');ctx.robot.groups[2].current=None;old=ctx.positions.values[2,2]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'current joints'):p.run()
        self.assertIs(ctx.positions.values[2,2],old);self.assertEqual(p.snapshot()['S'],99)

    def test_exhausted_budget_does_not_write(self):
        for operation,key in (('SET_POS_REG',(2,1)),('SET_JPOS_REG',(2,2))):
            with self.subTest(operation=operation):
                p,_,ctx=build(operation);old=ctx.positions.values[key]
                with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=2)
                self.assertIs(ctx.positions.values[key],old);self.assertEqual(p.snapshot()['S'],99)

    def test_nonzero_unused_joint_axis_is_not_discarded(self):
        p,_,ctx=build(decl='j:JOINTPOS p:XYZWPREXT s,n:INTEGER');p._state.values['J']=joint([0.,42.]+[0.]*6+[1.])
        old=ctx.positions.values[2,1]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(ctx.positions.values[2,1],old);self.assertEqual(p.snapshot()['S'],99)

    def test_improper_source_geometry_fails_before_inverse_adapter(self):
        p,_,ctx=build('SET_JPOS_REG',decl='j:JOINTPOS2 p:POSITION s,n:INTEGER')
        invalid=cartesian('POSITION',(100.,0.,42.),(0.,0.,0.));invalid.values['NORMAL'].values['X']=2.
        p._state.values['P']=invalid;seen=[];ctx.robot.groups[2].inverse=lambda *_:seen.append(1) or joint([0.,42.])
        old=ctx.positions.values[2,2]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(seen,[]);self.assertIs(ctx.positions.values[2,2],old);self.assertEqual(p.snapshot()['S'],99)

    def test_malformed_old_row_needs_matching_typed_repair(self):
        p,_,ctx=build('SET_JPOS_REG');ctx.positions.values[2,2].values['X']=float('nan');old=ctx.positions.values[2,2]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(ctx.positions.values[2,2],old);self.assertEqual(p.snapshot()['S'],99)
        p,_,_=build('SET_JPOS_REG',ctx=ctx,body='SET_EPOS_REG(2,p,s,2) SET_JPOS_REG(2,p,s,2)');p.run()
        self.assertEqual(ctx.positions.values[2,2].spec,('JOINTPOS',9))

    def test_scalars_and_conservative_cross_type_forms_remain_rejected(self):
        with self.assertRaises(TranslationError):build(body='SET_POS_REG(1,7,s,2)')
        for body in ('SET_POS_REG(1,j,s)','SET_JPOS_REG(1,p,s)'):
            with self.subTest(body=body),self.assertRaises(TranslationError):
                legacy_translate('PROGRAM T VAR j:JOINTPOS p:XYZWPR s:INTEGER BEGIN '+body+' END T')

    def test_report_exposes_typed_capture_and_staged_setter_publication(self):
        _,result,_=build();policy=result.report['position_register_model_policy']
        self.assertIn('SET_EPOS_REG',policy['setters']);self.assertIn('independent complete typed input',policy['setter_capture'])
        self.assertIn('destination presence/data/containers',policy['setter_publication']);self.assertFalse(policy['controller_validated'])


if __name__=='__main__':unittest.main()
