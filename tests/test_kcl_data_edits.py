"""Checked KCL named data copies and paused owned positional literals."""
import json
import unittest
from unittest.mock import patch

from karel2py import dynamic,runtime as rt,translate_project
from tests.test_extended_services import compile_program,pose
from tests.test_kcl_task_commands import issue


def context():return rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True,program_commands=True))


def array(spec,values):
    result=rt.Array(spec);result.values[:]=values;return result


ROW=('STRUCTURE','ROW_T',(('LABEL',('STRING',8)),('COUNT',('INTEGER',))))


def record(label='part',count=7):
    value=rt.Structure(ROW);value.values.update(LABEL=label,COUNT=count);return value


class KclNamedDataCopyTests(unittest.TestCase):
    def test_rank_one_two_and_three_arrays_copy_independently(self):
        for shape in ((4,),(2,2),(1,2,2)):
            with self.subTest(shape=shape):
                ctx=context();spec=('ARRAY',shape,('INTEGER',))
                source=ctx.variables.define('INPUTS','SOURCE',spec,array(spec,[1,2,3,4]))
                target=ctx.variables.define('CELL','TARGET',spec)
                original=target.raw();values=original.values
                self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET=[inputs]source')['S'],0)
                self.assertIs(target.raw(),original);self.assertIs(target.raw().values,values)
                self.assertEqual(target.raw().values,[1,2,3,4]);source.raw().values[0]=99
                self.assertEqual(target.raw().values,[1,2,3,4])

    def test_nested_named_arrays_and_complete_component_selection(self):
        ctx=context();row=('ARRAY',2,('INTEGER',),'ROW_T');bank=('ARRAY',2,row,'BANK_T')
        seed=array(bank,[array(row,[1,2]),array(row,[3,4])])
        ctx.variables.define('CELL','SOURCE',bank,seed);target=ctx.variables.define('CELL','TARGET',row)
        self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET=SOURCE[2]')['S'],0)
        self.assertEqual(target.raw().values,[3,4])
        dest=ctx.variables.define('CELL','DEST',bank)
        self.assertEqual(issue(ctx,'SET VAR [CELL]DEST[1]=SOURCE[2]')['S'],0)
        self.assertEqual(dest.raw().values[0].values,[3,4])
        self.assertFalse(rt.fully_initialized(dest.raw().values[1]))

    def test_user_records_and_record_arrays_keep_nested_receivers(self):
        ctx=context();spec=('ARRAY',2,ROW)
        source=ctx.variables.define('CELL','SOURCE',spec,array(spec,[record('one',1),record('two',2)]))
        target=ctx.variables.define('CELL','TARGET',spec)
        original=target.raw().values[1];fields=original.values
        self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET=SOURCE')['S'],0)
        self.assertIs(target.raw().values[1],original);self.assertIs(original.values,fields)
        self.assertEqual(rt.snapshot_value(target.raw()),[{'LABEL':'one','COUNT':1},{'LABEL':'two','COUNT':2}])
        source.raw().values[1].values['COUNT']=99;self.assertEqual(original.values['COUNT'],2)
        item=ctx.variables.define('CELL','ITEM',ROW)
        self.assertEqual(issue(ctx,'SET VAR [CELL]ITEM=SOURCE[2]')['S'],0)
        self.assertEqual(item.raw().values['COUNT'],99)

    def test_record_fields_can_copy_complete_arrays(self):
        ctx=context();spec=('ARRAY',2,('INTEGER',));outer=('STRUCTURE','OUTER_T',(('DATA',spec),('FLAG',('BOOLEAN',))))
        source=rt.Structure(outer);source.values['DATA'].values[:]=[8,9]
        ctx.variables.define('CELL','SOURCE',outer,source);target=ctx.variables.define('CELL','TARGET',outer)
        self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET.DATA=SOURCE.DATA')['S'],0)
        self.assertEqual(target.raw().values['DATA'].values,[8,9]);self.assertIs(target.raw().values['FLAG'],rt.UNINITIALIZED)

    def test_pose_and_joint_data_inside_records_are_private_and_validated(self):
        ctx=context();spec=('STRUCTURE','POSE_T',(('POINT',('XYZWPR',)),('AXES',('JOINTPOS',2))))
        source=rt.Structure(spec);source.values['POINT']=pose(12);source.values['AXES'].values[:]=[1.,2.]
        src=ctx.variables.define('CELL','SOURCE',spec,source);target=ctx.variables.define('CELL','TARGET',spec)
        self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET=SOURCE')['S'],0)
        src.raw().values['POINT'].values['X']=77.
        self.assertEqual(target.raw().values['POINT'].values['X'],12.)
        self.assertEqual(target.raw().values['AXES'].values,[1.,2.])

    def test_source_may_be_compiled_while_destination_must_be_independent(self):
        ctx=context();task,_=compile_program('data[1]=3 data[2]=4',decl='data:ARRAY[2]OF INTEGER',context=ctx);task.run()
        target=ctx.variables.define('CELL','TARGET',('ARRAY',2,('INTEGER',)))
        self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET=[T]DATA')['S'],0)
        self.assertEqual(target.raw().values,[3,4])
        self.assertEqual(issue(ctx,'SET VAR [T]DATA=[CELL]TARGET')['S'],204)

    def test_default_namespace_nowait_and_saved_context(self):
        ctx=context();spec=('ARRAY',2,('INTEGER',))
        ctx.variables.define('CELL','SOURCE',spec,array(spec,[5,6]));ctx.variables.define('CELL','TARGET',spec)
        self.assertEqual(issue(ctx,'SET DEFAULT CELL')['S'],0)
        self.assertEqual(issue(ctx,'SET VARIABLE TARGET=SOURCE',nowait=True),{'S':0,'N':0})
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        self.assertEqual(restored.variables.bindings['CELL','TARGET'].raw().values,[5,6])

    def test_selected_source_is_read_after_the_last_copy_checkpoint(self):
        ctx=context();spec=('ARRAY',2,('INTEGER',))
        source=ctx.variables.define('CELL','SOURCE',spec,array(spec,[1,2]));target=ctx.variables.define('CELL','TARGET',spec)
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==3:source.raw().values[1]=42
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET=SOURCE')['S'],0)
        self.assertEqual(len(calls),3);self.assertEqual(target.raw().values,[1,42])


class KclDataCopyGuardTests(unittest.TestCase):
    def setUp(self):
        self.ctx=context();self.spec=('ARRAY',2,('INTEGER',))
        self.source=self.ctx.variables.define('CELL','SOURCE',self.spec,array(self.spec,[1,2]))
        self.target=self.ctx.variables.define('CELL','TARGET',self.spec,array(self.spec,[8,9]))

    def command(self):return issue(self.ctx,'SET VAR [CELL]TARGET=SOURCE')['S']

    def during_charge(self,change):
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:change()
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):return self.command()

    def test_late_missing_or_malformed_source_leaf_keeps_every_destination(self):
        for invalid in (rt.UNINITIALIZED,rt.UNKNOWN_BYTE,'bad',True,1e99):
            self.source.raw().values[1]=invalid
            with self.subTest(invalid=invalid):
                self.assertEqual(self.command(),205);self.assertEqual(self.target.raw().values,[8,9])

    def test_short_string_arrays_reject_overcapacity_without_truncation(self):
        spec=('ARRAY',2,('STRING',3));ctx=context()
        source=ctx.variables.define('CELL','SOURCE',spec,array(spec,['one','two']));target=ctx.variables.define('CELL','TARGET',spec,array(spec,['old','old']))
        source.raw().values[1]='long'
        self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET=SOURCE')['S'],205);self.assertEqual(target.raw().values,['old','old'])

    def test_shape_terminal_and_nominal_identity_must_match_exactly(self):
        for spec in (('ARRAY',(1,2),('INTEGER',)),('ARRAY',2,('REAL',)),('ARRAY',2,('INTEGER',),'OTHER_T')):
            with self.subTest(spec=spec):
                self.ctx.variables.define('CELL','OTHER',spec)
                self.assertEqual(issue(self.ctx,'SET VAR [CELL]TARGET=OTHER')['S'],205)
                self.assertEqual(self.target.raw().values,[8,9])

    def test_nominal_record_names_must_match(self):
        ctx=context();ctx.variables.define('CELL','SOURCE',ROW,record())
        other=('STRUCTURE','OTHER_T',ROW[2]);target=ctx.variables.define('CELL','TARGET',other)
        before=rt.snapshot_value(target.raw())
        self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET=SOURCE')['S'],205)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_malformed_destination_fails_before_partial_replacement(self):
        self.target.raw().values.append(10)
        self.assertEqual(self.command(),205);self.assertEqual(self.target.raw().values,[8,9,10])
        ctx=context();ctx.variables.define('CELL','SOURCE',ROW,record());target=ctx.variables.define('CELL','TARGET',ROW)
        del target.raw().values['COUNT']
        self.assertEqual(issue(ctx,'SET VAR [CELL]TARGET=SOURCE')['S'],205)
        self.assertIs(target.raw().values['LABEL'],rt.UNINITIALIZED)

    def test_existing_overlapping_binding_or_timer_claim_stays_protected(self):
        self.ctx.variables.bind('OTHER','ALIAS',rt.Reference(('INTEGER',),self.target.raw().values,1))
        self.assertEqual(self.command(),204);self.assertEqual(self.target.raw().values,[8,9])
        del self.ctx.variables.bindings['OTHER','ALIAS']
        key=id(self.target.raw().values),1;self.ctx._timer_claims[key]=(None,None,self.target.raw().values,1)
        self.assertEqual(self.command(),204);self.assertEqual(self.target.raw().values,[8,9])

    def test_budget_exhaustion_precedes_data_validation_or_copy(self):
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:raise rt.KarelRuntimeError('authored copy step budget',line)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint),patch.object(rt,'_aggregate_value',side_effect=AssertionError('copy before budget')):
            self.assertEqual(self.command(),4)
        self.assertEqual(self.target.raw().values,[8,9])

    def test_real_step_budget_and_nowait_keep_completed_failure_status(self):
        for verb,accepted in (('KCL',4),('KCL_NO_WAIT',0)):
            with self.subTest(verb=verb):
                self.setUp()
                task,_=compile_program(f"{verb}('SET VAR [CELL]TARGET=SOURCE',s)",context=self.ctx)
                self.assertEqual(task.run(max_steps=3)['S'],accepted)
                self.assertEqual(self.ctx.kcl.last_status,4);self.assertIsNone(self.ctx.kcl._pending)
                self.assertEqual(self.target.raw().values,[8,9])

    def test_excess_schema_size_rejects_before_copy_charges(self):
        self.target.spec=('ARRAY',32768,('INTEGER',))
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):actual(state,line);calls.append(1)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(self.command(),205)
        self.assertEqual(len(calls),1);self.assertEqual(self.target.raw().values,[8,9])

    def test_self_copy_preserves_complete_storage(self):
        original=self.target.raw();values=original.values
        self.assertEqual(issue(self.ctx,'SET VAR [CELL]TARGET=TARGET')['S'],0)
        self.assertIs(self.target.raw(),original);self.assertIs(original.values,values)
        self.assertEqual(original.values,[8,9])

    def test_destination_protection_added_during_charge_is_rechecked(self):
        self.ctx.program_attributes=rt.ProgramAttributes({'CELL':{'attributes':{'AT_PROTECT':1}}})
        def protect():self.ctx.program_attributes=rt.ProgramAttributes({'CELL':{'attributes':{'AT_PROTECT':2}}})
        self.assertEqual(self.during_charge(protect),204);self.assertEqual(self.target.raw().values,[8,9])

    def test_replaced_removed_or_retyped_target_binding_is_not_published(self):
        for change in ('replace','remove','retype'):
            with self.subTest(change=change):
                self.setUp();original=self.target
                def replace():
                    if change=='remove':del self.ctx.variables.bindings['CELL','TARGET']
                    elif change=='retype':original.spec=('ARRAY',2,('REAL',))
                    else:self.ctx.variables.define('CELL','TARGET',self.spec,array(self.spec,[7,7]))
                self.assertEqual(self.during_charge(replace),204);self.assertEqual(original.raw().values,[8,9])
                if change=='replace':self.assertEqual(self.ctx.variables.bindings['CELL','TARGET'].raw().values,[7,7])

    def test_alias_or_timer_added_during_charge_prevents_publication(self):
        def alias():self.ctx.variables.bind('OTHER','ALIAS',rt.Reference(('INTEGER',),self.target.raw().values,1))
        self.assertEqual(self.during_charge(alias),204);self.assertEqual(self.target.raw().values,[8,9])
        del self.ctx.variables.bindings['OTHER','ALIAS']
        def timer():
            key=id(self.target.raw().values),1;self.ctx._timer_claims[key]=(None,None,self.target.raw().values,1)
        self.assertEqual(self.during_charge(timer),204);self.assertEqual(self.target.raw().values,[8,9])

    def test_replaced_nested_parent_does_not_redirect_captured_target(self):
        outer=('STRUCTURE','BOX_T',(('DATA',self.spec),))
        ref=self.ctx.variables.define('CELL','BOX',outer);old=ref.raw().values['DATA'];old.values[:]=[8,9]
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:ref.raw().values['DATA']=array(self.spec,[7,7])
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(issue(self.ctx,'SET VAR [CELL]BOX.DATA=SOURCE')['S'],204)
        self.assertEqual(old.values,[8,9]);self.assertEqual(ref.raw().values['DATA'].values,[7,7])

    def test_file_values_remain_excluded(self):
        ctx=context()
        declarations,_=compile_program('',decl='f:FILE')
        for kind in declarations._state.types.values():
            ctx.variables.define('CELL','SOURCE',kind);ctx.variables.define('CELL','TARGET',kind)
            self.assertNotEqual(issue(ctx,'SET VAR [CELL]TARGET=SOURCE')['S'],0)
        files=('ARRAY',2,('FILE',));ctx.variables.define('CELL','FILE_SOURCE',files);target=ctx.variables.define('CELL','FILES',files)
        before=rt.snapshot_value(target.raw())
        self.assertEqual(issue(ctx,'SET VAR [CELL]FILES=FILE_SOURCE')['S'],205);self.assertEqual(rt.snapshot_value(target.raw()),before)


class KclPausedPoseEditTests(unittest.TestCase):
    def paused(self,decl='point:XYZWPR',routines=None,prefix=''):
        ctx=context()
        task,_=compile_program('perform',decl='n,s:INTEGER',context=ctx,cooperative=True,prefix=prefix,routines=routines or f'ROUTINE perform VAR {decl} BEGIN PAUSE END perform')
        ctx.tasks.bind('WORKER',task)
        with self.assertRaises(rt.KarelPause):task.run()
        return ctx,task,task._state._timer_frames[-1][1]

    def test_vector_config_cartesian_and_joint_roots_accept_typed_literals(self):
        cases=[('shift:VECTOR','SHIFT','1,-2,3',lambda v:v.values['Y'],-2.),
               ('cfg:CONFIG','CFG','"N L U T,1,2,3"',lambda v:v.values['CFG_TURN_NO3'],3),
               ('point:XYZWPR','POINT','1,2,3,0,0,0',lambda v:v.values['X'],1.),
               ('point:POSITION','POINT','1,2,3,0,0,0',lambda v:v.values['LOCATION'].values['Z'],3.),
               ('point:XYZWPREXT','POINT','1,2,3,0,0,0,7,8,9',lambda v:v.values['EXT3'],9.),
               ('axes:JOINTPOS2','AXES','1,-2',lambda v:v.values,[1.,-2.])]
        for decl,name,literal,read,expected in cases:
            with self.subTest(decl=decl):
                ctx,task,storage=self.paused(decl);original=storage[name]
                self.assertEqual(issue(ctx,f'SET LOCAL VARIABLE {name} IN perform FROM T WORKER = {literal}')['S'],0)
                self.assertIs(storage[name],original);self.assertEqual(read(storage[name]),expected)
                task.resume()

    def test_pose_edit_survives_resume_and_keeps_matrix_columns_readonly(self):
        ctx,task,storage=self.paused(routines='ROUTINE perform VAR point:POSITION BEGIN PAUSE n=ROUND(point.location.x) END perform')
        self.assertEqual(issue(ctx,'SET LOCAL VAR point WORKER = 12,2,3,0,0,0')['S'],0)
        self.assertTrue(storage['POINT'].values['NORMAL'].read_only)
        self.assertEqual(task.resume()['N'],12)

    def test_invalid_pose_components_do_not_write_any_field(self):
        ctx,task,storage=self.paused();self.assertEqual(issue(ctx,'SET LOCAL VAR point WORKER = 1,2,3,0,0,0')['S'],0)
        before=rt.snapshot_value(storage['POINT'])
        for literal in ('9,8,7,1e999,0,0','9,8,7,400,0,0','9,8,7,0,0','9,8,7,0,0,0,"bad"'):
            with self.subTest(literal=literal):
                self.assertEqual(issue(ctx,'SET LOCAL VAR point WORKER = '+literal)['S'],205)
                self.assertEqual(rt.snapshot_value(storage['POINT']),before)

    def test_borrowed_pose_root_and_retained_field_alias_are_protected(self):
        routines="ROUTINE perform VAR point:XYZWPR cfg:CONFIG BEGIN CNV_STR_CONF('N',cfg,s) point=POS(1,2,3,0,0,0,cfg) consume(point.x) END perform ROUTINE consume(alias:REAL) BEGIN PAUSE END consume"
        ctx,task,_=self.paused(routines=routines)
        self.assertEqual(issue(ctx,'SET LOCAL VAR point IN perform WORKER = 9,8,7,0,0,0')['S'],204)
        self.assertEqual(task._state._timer_frames[0][1]['POINT'].values['X'],1.)
        routines="ROUTINE perform VAR point:XYZWPR cfg:CONFIG BEGIN CNV_STR_CONF('N',cfg,s) point=POS(1,2,3,0,0,0,cfg) consume(point) END perform ROUTINE consume(alias:XYZWPR) BEGIN PAUSE END consume"
        ctx,task,_=self.paused(routines=routines)
        self.assertEqual(issue(ctx,'SET LOCAL VAR alias WORKER = 9,8,7,0,0,0')['S'],204)

    def test_retained_joint_axis_alias_prevents_whole_joint_edit(self):
        routines='ROUTINE perform VAR axes:JOINTPOS2 BEGIN axes[1]=0 consume(axes[1]) END perform ROUTINE consume(axis:REAL) BEGIN PAUSE END consume'
        ctx,task,_=self.paused(routines=routines)
        self.assertEqual(issue(ctx,'SET LOCAL VAR axes IN perform WORKER = 1,2')['S'],204)

    def test_descendant_timer_claim_or_protected_metadata_prevents_whole_pose_edit(self):
        ctx,task,storage=self.paused()
        cfg=storage['POINT'].values['CONFIG_DATA'].values
        key=id(cfg),'CFG_TURN_NO1';ctx._timer_claims[key]=(task._state,None,cfg,'CFG_TURN_NO1')
        self.assertEqual(issue(ctx,'SET LOCAL VAR point WORKER = 9,8,7,0,0,0')['S'],204)
        del ctx._timer_claims[key]
        with patch.object(type(task),'local_for_roots',{'PERFORM':('POINT',)}):
            self.assertEqual(issue(ctx,'SET LOCAL VAR point WORKER = 9,8,7,0,0,0')['S'],204)

    def test_running_task_and_missing_metadata_still_reject(self):
        ctx,task,_=self.paused()
        with patch.object(type(task),'local_for_roots',{}):
            self.assertEqual(issue(ctx,'SET LOCAL VAR point WORKER = 1,2,3,0,0,0')['S'],204)
        task._state.task_state='running'
        self.assertEqual(issue(ctx,'SET LOCAL VAR point WORKER = 1,2,3,0,0,0')['S'],204)

    def test_user_record_array_and_named_source_local_writes_stay_excluded(self):
        for decl,literal in (('data:ARRAY[2]OF INTEGER','1,2'),('point:XYZWPR','OTHER')):
            with self.subTest(decl=decl):
                ctx,task,storage=self.paused(decl);name=next(iter(storage));before=rt.snapshot_value(storage[name])
                self.assertNotEqual(issue(ctx,f'SET LOCAL VAR {name} WORKER = {literal}')['S'],0)
                self.assertEqual(rt.snapshot_value(storage[name]),before)

    def test_linked_routine_pose_edits_keep_module_and_frame_selection(self):
        ctx=context();project=translate_project({'m':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN','l':'PROGRAM LIB VAR result:REAL ROUTINE work VAR shift:VECTOR BEGIN PAUSE result=shift.z END work BEGIN END LIB'})
        instance=project.instantiate(context=ctx);ctx.tasks.bind('WORKER',instance.programs['MAIN'])
        with self.assertRaises(rt.KarelPause):instance.programs['MAIN'].run()
        self.assertEqual(issue(ctx,'SET LOCAL VAR shift IN work FROM LIB WORKER = 1,2,30')['S'],0)
        instance.programs['MAIN'].resume();self.assertEqual(instance.programs['LIB'].snapshot()['RESULT'],30.)
