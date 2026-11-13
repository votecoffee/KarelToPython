"""Authored table publication guards, independent state and replay boundaries."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt,translate
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value
from tests.test_extended_services import compile_program,pose
from tests.test_cartesian_interfaces import value as cartesian_value
from tests.test_system_pose_values import program,context
from tests.test_system_pose_writes import execute,frame


class SystemPoseWriteGuardTests(unittest.TestCase):
    def unchanged(self,body,**options):
        p,_=program(body,**options);table=p._state.execution.robot.frames;before=deepcopy(table);old=table.get(2)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual({k:rt.snapshot_value(v) for k,v in table.items()},{k:rt.snapshot_value(v) for k,v in before.items()});self.assertIs(table.get(2),old);return p
    def reject(self,body):
        with self.assertRaises(TranslationError) as caught:program(body)
        return caught.exception.code
    def test_partial_rhs_does_not_replace_existing_row(self):self.unchanged('$MNUFRAME[1,2]=a')
    def test_partial_rhs_does_not_populate_new_row(self):self.unchanged('$MNUFRAME[1,7]=a')
    def test_incomplete_location_does_not_publish_partial_field(self):self.unchanged('p.location.x=99 $MNUFRAME[1,2].location=p.location')
    def test_nonfinite_scalar_does_not_mutate_table(self):
        p,_=program('$MNUFRAME[1,2].location.x=n');p._state.values['N']=float('nan');old=frame(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(frame(p),old);self.assertEqual(old.values['X'],12.)
    def test_out_of_domain_turn_does_not_mutate_table(self):self.unchanged('$MNUFRAME[1,2].config_data.cfg_turn_no1=8')
    def test_missing_group_does_not_populate_any_row(self):self.unchanged('a=$MNUFRAME[1,2] $MNUFRAME[2,7]=a')
    def test_invalid_number_preserves_existing_rows(self):
        for number in (-1,32768):
            with self.subTest(number=number):self.unchanged(f'a=$MNUFRAME[1,2] $MNUFRAME[1,{number}]=a')
    def test_missing_selector_value_preserves_rows(self):self.unchanged('a=$MNUFRAME[1,2] $MNUFRAME[i,2]=a')
    def test_missing_robot_context_stays_explicit(self):
        p,_=compile_program('$MNUFRAME[1,7]=a',decl='a:XYZWPR');p._state.values['A']=pose(12)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'):p.run()
    def test_active_missing_row_cannot_be_implicitly_populated(self):
        ctx=context();ctx.robot.active_frame=7;self.unchanged('a=$MNUFRAME[1,2] $GROUP[1].$UFRAME=a',context=ctx)
    def test_field_write_requires_existing_row(self):self.unchanged('$MNUFRAME[1,7].location.x=30')
    def test_field_write_rejects_malformed_previous_pose(self):
        ctx=context();ctx.robot.frames[2].values['Z']=rt.UNINITIALIZED;self.unchanged('$MNUFRAME[1,2].location.x=30',context=ctx)
    def test_invalid_position_basis_preserves_table(self):
        ctx=context();p,_=program('$MNUFRAME[1,2]=p',context=ctx);bad=cartesian_value('POSITION',(12.,0.,0.),(0.,0.,0.));bad.values['NORMAL'].values['X']=2.;p._state.values['P']=bad;old=frame(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(frame(p),old)
    def test_root_scalar_rhs_is_rejected(self):self.assertEqual(self.reject('$MNUFRAME[1,2]=7'),'E_TYPE')
    def test_joint_rhs_requires_an_explicit_model(self):
        p,_=program('j[1]=0 j[2]=0 $MNUFRAME[1,2]=j',decl='j:JOINTPOS2');old=frame(p)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'adapter'):p.run()
        self.assertIs(frame(p),old)
    def test_boolean_location_rhs_is_rejected(self):self.assertEqual(self.reject('$MNUFRAME[1,2].location.x=TRUE'),'E_TYPE')
    def test_wrong_config_boolean_rhs_is_rejected(self):self.assertEqual(self.reject('$MNUFRAME[1,2].config_data.cfg_flip=7'),'E_TYPE')
    def test_whole_location_requires_vector(self):self.assertEqual(self.reject('$MNUFRAME[1,2].location=p'),'E_TYPE')
    def test_unknown_location_field_is_rejected(self):self.assertEqual(self.reject('$MNUFRAME[1,2].location.unknown=7'),'E_SYSTEM_POSE_TARGET')
    def test_orientation_targets_still_reject_writes(self):
        for target in ('normal','normal.x','orient','approach.z'):
            with self.subTest(target=target):self.assertEqual(self.reject('$MNUFRAME[1,2].'+target+'=n'),'E_SYSTEM_POSE_TARGET')
    def test_extra_index_cannot_supply_writable_alias(self):self.assertEqual(self.reject('$MNUFRAME[1,2][1]=p'),'E_SYSTEM_POSE_TARGET')
    def test_read_target_still_cannot_alias_table(self):self.assertIn(self.reject('READ($MNUFRAME[1,2].location.x)'),('E_READ_ITEM','E_SYSTEM_POSE_READ_ONLY'))
    def test_service_output_still_cannot_alias_table(self):self.assertEqual(self.reject("GET_VAR(entry,'','n',$MNUFRAME[1,2].location.x,s)"),'E_SYSTEM_POSE_READ_ONLY')
    def test_routine_argument_is_still_a_private_value(self):
        _,p,_=execute('work($MNUFRAME[1,2].location.x)',routines='ROUTINE work(v:REAL) BEGIN v=99 END work');self.assertEqual(frame(p).values['X'],12.)
    def test_using_is_still_a_private_copy(self):
        _,p,_=execute('USING $MNUFRAME[1,2] DO location.x=99 ENDUSING');self.assertEqual(frame(p).values['X'],12.)
    def test_strict_state_guard_remains(self):
        p,_=program('')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):p._state.system_pose_write('FRAME',1,2,pose(12))
    def test_strict_context_guard_remains(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):context().system_pose_write('FRAME',1,2,pose(12))
    def test_invalid_runtime_path_is_rejected_before_mutation(self):
        ctx=context();old=ctx.robot.frames[2]
        for path in (['LOCATION','X'],('LOCATION',[]),('NORMAL','X'),('CONFIG_DATA','unknown')):
            with self.subTest(path=path),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):ctx.system_pose_write('FRAME',1,2,7,path)
        self.assertIs(ctx.robot.frames[2],old)
    def test_invalid_runtime_kind_is_rejected(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):context().system_pose_write('UNKNOWN',1,2,pose(12))
    def test_active_write_rejects_explicit_number(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):context().system_pose_write('ACTIVE_FRAME',1,2,pose(12))
    def test_subclassed_rhs_is_not_published(self):
        class Derived(rt.Structure):pass
        ctx=context();value=Derived(('XYZWPR',))
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):ctx.system_pose_write('FRAME',1,2,value)
    def test_nonordinary_table_cannot_be_mutated(self):
        class Derived(dict):pass
        ctx=context();ctx.robot.frames=Derived(ctx.robot.frames)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):ctx.system_pose_write('FRAME',1,2,pose(12))
    def test_failure_has_source_line_and_value_free_observation(self):
        p=self.unchanged('$MNUFRAME[1,2].config_data.cfg_turn_no1=8');row=p.service_requests[-1];self.assertEqual((row['operation'],row['outcome']),('SYSTEM_POSE_WRITE','failed'));self.assertIsNotNone(row['line']);self.assertEqual(set(row),{'operation','line','outcome'})
    def test_included_wrong_type_keeps_physical_diagnostic(self):
        with self.assertRaises(TranslationError) as caught:translate('PROGRAM T\n%INCLUDE BODY\nEND T',includes={'BODY.KL':'BEGIN $MNUFRAME[1,2]=7'})
        self.assertEqual((caught.exception.filename,caught.exception.token.line),('BODY.KL',1))


class SystemPoseWriteStateTests(unittest.TestCase):
    def test_model_free_context_roundtrips_published_rows(self):
        _,p,_=execute('a=$MNUFRAME[1,2] a.x=30 $MNUFRAME[1,7]=a $MNUTOOL[1,3].location.y=9');saved=json.loads(json.dumps(p._state.execution.to_config()));other=rt.ExecutionContext.from_config(saved);self.assertEqual(other.to_config(),saved);self.assertEqual(other.robot.frames[7].values['X'],30.)
    def test_extended_axes_and_representation_survive_json(self):
        ctx=context();ctx.robot.frames[2]=cartesian_value('XYZWPREXT',(12.,0.,0.),(10.,20.,30.),(7.,8.,9.));execute('$MNUFRAME[1,2].location.x=30',context=ctx);other=rt.ExecutionContext.from_config(ctx.to_config());self.assertEqual((other.robot.frames[2].spec,other.robot.frames[2].values['EXT3']),(('XYZWPREXT',),9.))
    def test_group_selections_are_not_changed_by_writes(self):
        ctx=context();execute('$GROUP[1].$UTOOL.location.x=30',context=ctx);saved=ctx.to_config();other=rt.ExecutionContext.from_config(saved);self.assertEqual((other.robot.active_frame,other.robot.active_tool),(2,3));self.assertEqual(other.robot.tools[3].values['X'],30.)
    def test_dh_identity_override_is_saved_explicitly(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100}],'frames':{'2':typed_value(pose(12))},'frame':2}});execute('a=$MNUFRAME[1,2] $MNUFRAME[1,0]=a',context=ctx);saved=ctx.to_config();self.assertEqual(saved['robot']['frames']['0']['value']['X'],12.);self.assertEqual(rt.ExecutionContext.from_config(saved).robot.frame(0).values['X'],12.)
    def test_current_state_is_not_moved_by_table_write(self):
        ctx=context();ctx.robot.current=rt.RobotState(position=pose(5));before=ctx.robot.current.to_config();execute('$MNUFRAME[1,2].location.x=30',context=ctx);self.assertEqual(ctx.robot.current.to_config(),before)
    def test_model_callbacks_are_not_invoked_for_cartesian_table_write(self):
        ctx=context();ctx.robot.forward=lambda *args:(_ for _ in ()).throw(AssertionError('unexpected model call'));ctx.robot.check_position=ctx.robot.forward;execute('$MNUFRAME[1,2].location.x=30',context=ctx);self.assertEqual(ctx.robot.frames[2].values['X'],30.)
