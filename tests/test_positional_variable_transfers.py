"""Whole positional GET_VAR/SET_VAR conversion, atomicity and exact boundaries."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.kinematics import pose as identity_pose
from tests.test_cartesian_interfaces import value as cartesian_value,snapshot_x
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint,model_context
from tests.test_project_scheduler import source
from tests.test_variable_transfers import transfer


CARTESIANS=('POSITION','XYZWPR','XYZWPREXT')
def pose(kind):return cartesian_value(kind,(7.,8.,9.),(0.,0.,0.),(10.,20.,30.))
def build(body,first='XYZWPR',second='POSITION',**options):
    return compile_program(body,decl=f'a:{first} b:{second} e,s,n:INTEGER',**options)


class PositionalVariableTransferTests(unittest.TestCase):
    def test_all_cartesian_pairs_in_both_directions(self):
        for first in CARTESIANS:
            for second in CARTESIANS:
                for action in ('GET_VAR','SET_VAR'):
                    call=transfer(action,'A','b') if action=='GET_VAR' else transfer(action,'B','a')
                    p,_=build(call,first,second);p._state.values['A']=pose(first)
                    with self.subTest(first=first,second=second,action=action):
                        result=p.run();self.assertEqual((snapshot_x(result['B'],second),result['S'],result['E']),(7.,0,1))
                    self.assertEqual(p.snapshot()['A'],rt.snapshot_value(pose(first)))
                    self.assertIsNot(p._state.values['A'],p._state.values['B'])

    def test_external_metadata_widening_and_narrowing_follow_source_conversion(self):
        p,_=build(transfer(),'XYZWPR','XYZWPREXT');p._state.values['A']=pose('XYZWPR')
        self.assertEqual([p.run()['B'][key] for key in ('EXT1','EXT2','EXT3')],[0.,0.,0.])
        p,_=build(transfer(),'XYZWPREXT','XYZWPR');p._state.values['A']=pose('XYZWPREXT')
        self.assertNotIn('EXT1',p.run()['B'])

    def test_every_joint_width_pair_pads_or_narrows_zero_only(self):
        for first in range(1,10):
            for second in range(1,10):
                p,_=build(transfer(),f'JOINTPOS{first}',f'JOINTPOS{second}');p._state.values['A']=joint([7.]+[0.]*(first-1))
                with self.subTest(first=first,second=second):self.assertEqual(p.run()['B']['axes'],[7.]+[0.]*(second-1))

    def test_set_joint_value_uses_the_same_width_policy(self):
        p,_=build(transfer('SET_VAR','B','a'),'JOINTPOS2','JOINTPOS9');p._state.values['A']=joint([7.,8.])
        self.assertEqual(p.run()['B']['axes'],[7.,8.]+[0.]*7)

    def test_nonzero_discarded_joint_axis_retains_all_outputs(self):
        p,_=build('e=99 s=77 '+transfer(),'JOINTPOS3','JOINTPOS2');p._state.values['A']=joint([7.,8.,9.]);p._state.values['B']=joint([1.,2.])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'zero discarded'):p.run()
        self.assertEqual((p.snapshot()['B']['axes'],p.snapshot()['E'],p.snapshot()['S']),([1.,2.],99,77));self.assertFalse(p._state.execution.entries)

    def test_representation_changes_require_complete_source(self):
        for first,second in (('XYZWPR','POSITION'),('POSITION','XYZWPREXT'),('JOINTPOS2','JOINTPOS9')):
            p,_=build('e=99 s=77 '+transfer(),first,second);before=p.snapshot()['B']
            with self.subTest(first=first,second=second),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(before,99,77))

    def test_exact_same_type_still_copies_partial_values(self):
        for kind in CARTESIANS:
            p,_=build(transfer(),kind,kind);state=p.run()
            with self.subTest(kind=kind):self.assertEqual(state['A'],state['B']);self.assertEqual(state['S'],12311)

    def test_improper_position_matrix_is_rejected_before_publication(self):
        p,_=build('e=99 s=77 '+transfer(),'POSITION','XYZWPR');point=pose('POSITION');point.values['NORMAL'].values['X']=2.
        p._state.values['A']=point;before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(before,99,77))

    def test_invalid_config_and_nonfinite_values_are_not_reinterpreted(self):
        for field,value in (('X',float('nan')),('X',True),('TURN',8)):
            p,_=build('e=99 s=77 '+transfer(),'XYZWPR','POSITION');point=pose('XYZWPR')
            if field=='TURN':point.values['CONFIG_DATA'].values['CFG_TURN_NO1']=value
            else:point.values[field]=value
            p._state.values['A']=point
            with self.subTest(field=field,value=value),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['E'],p.snapshot()['S']),(99,77))

    def test_whole_array_kinematic_pairs_stay_incompatible(self):
        for first,second in (('XYZWPR','JOINTPOS9'),('JOINTPOS2','POSITION')):
            p,_=build('e=99 '+transfer(),f'ARRAY[1] OF {first}',f'ARRAY[1] OF {second}')
            with self.subTest(first=first,second=second):self.assertEqual((p.run()['S'],p.snapshot()['E']),(3,99))

    def test_joint_cartesian_pair_without_robot_service_stays_incompatible(self):
        for first,second in (('JOINTPOS2','POSITION'),('XYZWPR','JOINTPOS9')):
            p,_=build('e=99 '+transfer(),first,second,context=rt.ExecutionContext())
            with self.subTest(first=first,second=second):self.assertEqual((p.run()['S'],p.snapshot()['E']),(3,99))

    def test_set_captures_source_before_later_status_selector(self):
        p,_=compile_program("SET_VAR(e,'','B',a,codes[change()])",decl='a:XYZWPR b:POSITION e:INTEGER codes:ARRAY[1] OF INTEGER',
            routines='ROUTINE change:INTEGER BEGIN a.x=99 RETURN 1 END change')
        p._state.values['A']=pose('XYZWPR');state=p.run();self.assertEqual((state['A']['X'],state['B']['LOCATION']['X']),(99.,7.))

    def test_get_reads_named_source_after_output_selector_effect(self):
        p,_=compile_program("GET_VAR(e,'','A',b,codes[change()])",decl='a:XYZWPR b:POSITION e:INTEGER codes:ARRAY[1] OF INTEGER',
            routines='ROUTINE change:INTEGER BEGIN a.x=99 RETURN 1 END change')
        p._state.values['A']=pose('XYZWPR');self.assertEqual(p.run()['B']['LOCATION']['X'],99.)

    def test_success_keeps_destination_container_and_child_aliases(self):
        p,_=build(transfer());p._state.values['A']=pose('XYZWPR');root=p._state.values['B'];child=root.values['LOCATION'];ref=rt.field_reference(child,'X')
        p.run();self.assertIs(p._state.values['B'],root);self.assertIs(root.values['LOCATION'],child);self.assertEqual(ref.raw(),7.)

    def test_position_orientation_descendants_remain_readonly(self):
        p,_=build(transfer());p._state.values['A']=pose('XYZWPR');p.run()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'):rt.field_reference(p._state.values['B'].values['NORMAL'],'X').set(7.)

    def test_scalar_field_or_array_element_transfer_can_change_representation(self):
        p,_=compile_program("GET_VAR(e,'','items[1]',b,s)",decl='items:ARRAY[1] OF XYZWPR b:POSITION e,s:INTEGER')
        p._state.values['ITEMS'].set(1,pose('XYZWPR'))
        self.assertEqual(p.run()['B']['LOCATION']['X'],7.)

    def test_explicit_foreign_binding_is_read_without_changing_it(self):
        ctx=rt.ExecutionContext();ref=ctx.variables.define('OTHER','POINT',('XYZWPR',),pose('XYZWPR'))
        p,_=build("GET_VAR(e,'OTHER','POINT',b,s)",context=ctx)
        self.assertEqual(p.run()['B']['LOCATION']['X'],7.);self.assertEqual(ref.raw().values['X'],7.)

    def test_saved_context_replays_concrete_source_and_destination_types(self):
        p,_=build(transfer());p._state.values['A']=pose('XYZWPR');state=p.run()
        ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(p._state.execution.to_config())))
        again,_=build(transfer(),context=ctx);self.assertEqual(again.run(),state)

    def test_linked_get_uses_named_source_owner(self):
        project=translate_project({'lib':source('LIB','',decl='a:XYZWPR'),
            'main':source('MAIN',"GET_VAR(e,'LIB','A',b,s)",decl='b:POSITION e,s:INTEGER')}).instantiate()
        project.programs['LIB']._state.values['A']=pose('XYZWPR');project.run('MAIN')
        self.assertEqual(project.programs['MAIN'].snapshot()['B']['LOCATION']['X'],7.)

    def test_report_keeps_kinematics_and_array_boundaries_explicit(self):
        _,result=build(transfer());policy=result.report['positional_variable_transfer_policy']
        self.assertIn('same-rank ARRAY prefixes',policy['conversions']);self.assertIn('kinematics',policy['boundary'])


if __name__=='__main__':unittest.main()
