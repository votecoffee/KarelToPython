"""Owned paused-local data selectors, named copies and retained target guards."""
import unittest
from unittest.mock import patch

from karel2py import dynamic,runtime as rt,translate_project
from tests.test_extended_services import compile_program,pose
from tests.test_kcl_task_commands import issue

TYPE='TYPE row_t=STRUCTURE label:STRING[6] count:INTEGER ENDSTRUCTURE'


def paused(decl='data:ARRAY[2]OF INTEGER',body='PAUSE',*,prefix='',globals_='n,s:INTEGER'):
    ctx=rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True,program_commands=True))
    task,_=compile_program('perform',decl=globals_,prefix=prefix,context=ctx,cooperative=True,
                           routines=f'ROUTINE perform VAR {decl} BEGIN {body} END perform')
    ctx.tasks.bind('WORKER',task)
    with unittest.TestCase().assertRaises(rt.KarelPause):task.run()
    return ctx,task,task._state._timer_frames[-1][1]


def edit(ctx,path,value,*,scope='WORKER',nowait=False):
    return issue(ctx,f'SET LOCAL VARIABLE {path} {scope} = {value}',nowait=nowait)


class LocalDataSelectorTests(unittest.TestCase):
    def test_multidimensional_coordinates_and_frame_qualifiers(self):
        ctx,task,storage=paused('data:ARRAY[2,2]OF INTEGER',body='PAUSE n=data[2,1]')
        self.assertEqual(edit(ctx,'data[ 2 , 1 ]','42',scope='IN perform FROM T WORKER')['S'],0)
        self.assertEqual(storage['DATA'].values[2],42);self.assertEqual(task.resume()['N'],42)

    def test_rank_one_and_three_elements_use_original_cells(self):
        for decl,path,index in (('data:ARRAY[2]OF INTEGER','data[2]',1),('data:ARRAY[2,1,2]OF INTEGER','data[2,1,2]',3)):
            with self.subTest(decl=decl):
                ctx,_,storage=paused(decl);original=storage['DATA'];values=original.values
                self.assertEqual(edit(ctx,path,'17')['S'],0);self.assertIs(storage['DATA'],original)
                self.assertIs(original.values,values);self.assertEqual(values[index],17)

    def test_nested_record_fields_and_record_array_elements(self):
        ctx,task,storage=paused('rows:ARRAY[2]OF row_t',prefix=TYPE,body='PAUSE n=rows[2].count')
        self.assertEqual(edit(ctx,'rows[2].label','"MiXeD"')['S'],0)
        self.assertEqual(edit(ctx,'rows[2].count','21')['S'],0)
        self.assertEqual(edit(ctx,'rows[2].label','"too long"')['S'],205)
        self.assertEqual(storage['ROWS'].values[1].values,{'LABEL':'MiXeD','COUNT':21})
        self.assertEqual(task.resume()['N'],21)

    def test_joint_axes_and_writable_position_location_fields(self):
        ctx,_,storage=paused('axes:JOINTPOS2 point:POSITION')
        self.assertEqual(edit(ctx,'axes[2]','1.25')['S'],0)
        self.assertEqual(edit(ctx,'point.location.x','12.5')['S'],0)
        self.assertEqual(storage['AXES'].values[1],1.25)
        self.assertEqual(storage['POINT'].values['LOCATION'].values['X'],12.5)
        for path,literal in (('point.normal','1,0,0'),('point.normal.x','1.0'),('point.approach.z','1.0')):
            with self.subTest(path=path):self.assertEqual(edit(ctx,path,literal)['S'],204)

    def test_config_flags_and_turns_keep_their_storage_domains(self):
        ctx,_,storage=paused('cfg:CONFIG')
        self.assertEqual(edit(ctx,'cfg.cfg_turn_no1','-8')['S'],0)
        self.assertEqual(edit(ctx,'cfg.cfg_left','TRUE')['S'],0)
        self.assertEqual(edit(ctx,'cfg.cfg_turn_no1','8')['S'],205)
        self.assertEqual(edit(ctx,'cfg.cfg_left','1')['S'],205)
        self.assertEqual(storage['CFG'].values['CFG_TURN_NO1'],-8)
        self.assertIs(storage['CFG'].values['CFG_LEFT'],True)

    def test_unknown_fields_missing_roots_and_incomplete_indices_do_not_write(self):
        ctx,_,storage=paused('data:ARRAY[2,2]OF INTEGER item:row_t',prefix=TYPE)
        before=rt.snapshot_value(storage['DATA'])
        for path,status in (('missing[1]',201),('item.absent',205),('data[0,1]',205),('data[3,1]',205),('data[1]',205)):
            with self.subTest(path=path):self.assertEqual(edit(ctx,path,'1')['S'],status)
        self.assertEqual(rt.snapshot_value(storage['DATA']),before)

    def test_dynamic_and_expression_indices_remain_unparsed(self):
        ctx,_,storage=paused();before=rt.snapshot_value(storage['DATA'])
        for path in ('data[n]','data[1+1]','data[-1]','data[1][1]'):
            with self.subTest(path=path):self.assertNotEqual(edit(ctx,path,'7')['S'],0)
        self.assertEqual(rt.snapshot_value(storage['DATA']),before)

    def test_array_and_record_literals_remain_excluded(self):
        ctx,_,storage=paused('data:ARRAY[2]OF INTEGER item:row_t',prefix=TYPE)
        self.assertEqual(edit(ctx,'data','1,2')['S'],205)
        self.assertEqual(edit(ctx,'item','"part",2')['S'],205)
        self.assertFalse(rt.fully_initialized(storage['DATA']));self.assertFalse(rt.fully_initialized(storage['ITEM']))


class LocalNamedCopyTests(unittest.TestCase):
    def test_named_local_arrays_copy_without_aliasing_or_replacing_receivers(self):
        ctx,task,storage=paused('source,target:ARRAY[2]OF INTEGER',body='source[1]=3 source[2]=4 PAUSE n=target[2]')
        original=storage['TARGET'];values=original.values
        self.assertEqual(edit(ctx,'target','source')['S'],0)
        self.assertIs(storage['TARGET'],original);self.assertIs(original.values,values)
        storage['SOURCE'].values[1]=99;self.assertEqual(original.values,[3,4])
        self.assertEqual(task.resume()['N'],4)

    def test_named_records_and_complete_record_array_components_copy(self):
        ctx,_,storage=paused('source,target:row_t rows:ARRAY[2]OF row_t',prefix=TYPE,
                             body="source.label='part' source.count=5 PAUSE")
        original=storage['TARGET'];fields=original.values
        self.assertEqual(edit(ctx,'target','source')['S'],0)
        self.assertEqual(edit(ctx,'rows[2]','source')['S'],0)
        self.assertIs(storage['TARGET'],original);self.assertIs(original.values,fields)
        storage['SOURCE'].values['COUNT']=99
        self.assertEqual((original.values['COUNT'],storage['ROWS'].values[1].values['COUNT']),(5,5))

    def test_named_components_can_copy_arrays_inside_records(self):
        prefix=TYPE+' box_t=STRUCTURE numbers:ARRAY[2]OF INTEGER item:row_t ENDSTRUCTURE'
        ctx,_,storage=paused('source,target:box_t',prefix=prefix,body='source.numbers[1]=8 source.numbers[2]=9 PAUSE')
        self.assertEqual(edit(ctx,'target.numbers','source.numbers')['S'],0)
        self.assertEqual(storage['TARGET'].values['NUMBERS'].values,[8,9])

    def test_local_lookup_shadows_globals_and_explicit_namespace_reads_global(self):
        ctx,_,storage=paused('source,target:INTEGER',body='source=7 PAUSE',globals_='n,s,source:INTEGER')
        # Selected-frame names take precedence over the same module's globals.
        ctx.variables.programs['T'].values['SOURCE']=99
        self.assertEqual(edit(ctx,'target','source')['S'],0);self.assertEqual(storage['TARGET'],7)
        self.assertEqual(edit(ctx,'target','[T]source')['S'],0);self.assertEqual(storage['TARGET'],99)
        ctx.variables.define('INPUTS','VALUE',('INTEGER',),31)
        self.assertEqual(edit(ctx,'target','[inputs]value')['S'],0);self.assertEqual(storage['TARGET'],31)

    def test_missing_local_source_falls_back_to_selected_module_globals(self):
        ctx,task,storage=paused('target:INTEGER',globals_='n,s,global_source:INTEGER')
        task._state.values['GLOBAL_SOURCE']=19
        self.assertEqual(edit(ctx,'target','global_source')['S'],0);self.assertEqual(storage['TARGET'],19)
        self.assertEqual(edit(ctx,'target','missing')['S'],205);self.assertEqual(storage['TARGET'],19)

    def test_uninitialized_shadowing_local_never_falls_back(self):
        ctx,task,storage=paused('source,target:INTEGER',globals_='n,s,source:INTEGER')
        task._state.values['SOURCE']=99
        self.assertEqual(edit(ctx,'target','source')['S'],205);self.assertIs(storage['TARGET'],rt.UNINITIALIZED)

    def test_named_scalar_fields_string_capacities_and_boolean_values(self):
        ctx,_,storage=paused('source:STRING[8] target:STRING[3] box:row_t a,b:BOOLEAN',prefix=TYPE,
                             body="source='fit' box.count=12 a=TRUE PAUSE")
        self.assertEqual(edit(ctx,'target','source')['S'],0);self.assertEqual(storage['TARGET'],'fit')
        self.assertEqual(edit(ctx,'box.label','source')['S'],0);self.assertEqual(storage['BOX'].values['LABEL'],'fit')
        self.assertEqual(edit(ctx,'b','a')['S'],0);self.assertIs(storage['B'],True)
        storage['SOURCE']='long'
        self.assertEqual(edit(ctx,'target','source')['S'],205);self.assertEqual(storage['TARGET'],'fit')

    def test_pose_joint_vector_and_config_sources_are_private(self):
        ctx,_,storage=paused('source,target:XYZWPR shifts:ARRAY[2]OF VECTOR joints:ARRAY[2]OF JOINTPOS2')
        storage['SOURCE']=pose(12)
        self.assertEqual(edit(ctx,'target','source')['S'],0)
        storage['SOURCE'].values['X']=99.;self.assertEqual(storage['TARGET'].values['X'],12.)
        self.assertEqual(edit(ctx,'shifts[1]','1,2,3')['S'],0)
        self.assertEqual(edit(ctx,'shifts[2]','shifts[1]')['S'],0)
        storage['SHIFTS'].values[0].values['Z']=99.;self.assertEqual(storage['SHIFTS'].values[1].values['Z'],3.)
        self.assertEqual(edit(ctx,'joints[1]','1,2')['S'],0)
        self.assertEqual(edit(ctx,'joints[2]','joints[1]')['S'],0)
        self.assertEqual(storage['JOINTS'].values[1].values,[1.,2.])

    def test_late_missing_or_malformed_array_source_rejects_complete_copy(self):
        ctx,_,storage=paused('source,target:ARRAY[2]OF INTEGER',body='source[1]=3 target[1]=8 target[2]=9 PAUSE')
        for invalid in (rt.UNINITIALIZED,True,'bad',1e99):
            with self.subTest(invalid=invalid):
                storage['SOURCE'].values[1]=invalid
                self.assertEqual(edit(ctx,'target','source')['S'],205);self.assertEqual(storage['TARGET'].values,[8,9])

    def test_exact_array_shape_terminal_and_record_names_are_required(self):
        ctx,_,storage=paused('source:ARRAY[2]OF INTEGER target:ARRAY[1,2]OF INTEGER real_target:ARRAY[2]OF REAL')
        self.assertEqual(edit(ctx,'target','source')['S'],205)
        self.assertEqual(edit(ctx,'real_target','source')['S'],205)
        prefix=TYPE+' other_t=STRUCTURE label:STRING[6] count:INTEGER ENDSTRUCTURE'
        ctx,_,storage=paused('source:row_t target:other_t',prefix=prefix,body="source.label='part' source.count=1 PAUSE")
        self.assertEqual(edit(ctx,'target','source')['S'],205);self.assertFalse(rt.fully_initialized(storage['TARGET']))

    def test_self_copy_nowait_and_default_task_selection(self):
        ctx,_,storage=paused('data:ARRAY[2]OF INTEGER',body='data[1]=3 data[2]=4 PAUSE')
        self.assertEqual(issue(ctx,'SET DEFAULT WORKER')['S'],0)
        self.assertEqual(edit(ctx,'data','data',scope='',nowait=True),{'S':0,'N':0})
        self.assertEqual(storage['DATA'].values,[3,4])


class LocalOwnershipTests(unittest.TestCase):
    def test_borrowed_formal_and_owner_with_retained_sibling_alias_stay_protected(self):
        ctx=rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True))
        task,_=compile_program('outer',context=ctx,cooperative=True,routines='''
          ROUTINE outer VAR data:ARRAY[2]OF INTEGER
          BEGIN data[1]=1 data[2]=2 consume(data[1]) END outer
          ROUTINE consume(alias:INTEGER) BEGIN PAUSE END consume
        ''')
        ctx.tasks.bind('WORKER',task)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(edit(ctx,'alias','7')['S'],204)
        self.assertEqual(edit(ctx,'data[2]','7',scope='IN outer WORKER')['S'],204)
        self.assertEqual(task._state._timer_frames[0][1]['DATA'].values,[1,2])

    def test_borrowed_source_can_be_read_into_owned_local_data(self):
        ctx=rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True))
        task,_=compile_program('data[1]=1 data[2]=2 consume(data)',decl='n,s:INTEGER data:ARRAY[2]OF INTEGER',context=ctx,cooperative=True,
            routines='ROUTINE consume(source:ARRAY OF INTEGER) VAR target:ARRAY[2]OF INTEGER BEGIN PAUSE n=target[2] END consume')
        ctx.tasks.bind('WORKER',task)
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(edit(ctx,'source[2]','9')['S'],204)
        self.assertEqual(edit(ctx,'target','source')['S'],0);self.assertEqual(task.resume()['N'],2)

    def test_timer_claim_on_sibling_and_for_metadata_guard_whole_owner_root(self):
        ctx,_,storage=paused(body='data[1]=0 data[2]=1 CONNECT TIMER TO data[1] PAUSE DISCONNECT TIMER data[1]')
        self.assertEqual(edit(ctx,'data[2]','7')['S'],204);self.assertEqual(storage['DATA'].values[1],1)
        ctx,_,storage=paused(body='data[2]=1 FOR data[1]=1 TO 2 DO PAUSE ENDFOR')
        self.assertEqual(edit(ctx,'data[2]','7')['S'],204);self.assertEqual(storage['DATA'].values[1],1)

    def test_explicit_alias_to_unselected_element_protects_containing_local(self):
        ctx,_,storage=paused(body='data[1]=1 data[2]=2 PAUSE')
        ctx.variables.bind('ALIAS','VALUE',rt.Reference(('INTEGER',),storage['DATA'].values,0))
        self.assertEqual(edit(ctx,'data[2]','7')['S'],204);self.assertEqual(storage['DATA'].values,[1,2])

    def test_resource_roots_and_targets_remain_excluded(self):
        ctx,_,storage=paused('files:ARRAY[2]OF FILE route:PATH queue:QUEUE_TYPE data:INTEGER')
        for path in ('files[1]','route','queue'):
            with self.subTest(path=path):self.assertNotEqual(edit(ctx,path,'data')['S'],0)
        self.assertIs(storage['DATA'],rt.UNINITIALIZED)


class LocalPreparationTests(unittest.TestCase):
    def setUp(self):
        self.ctx,self.task,self.storage=paused('source,target:ARRAY[2]OF INTEGER',
            body='source[1]=1 source[2]=2 target[1]=8 target[2]=9 PAUSE')
        self.original=self.storage['TARGET']

    def during(self,change,path='target',value='source'):
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:change()
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):return edit(self.ctx,path,value)['S']

    def test_actual_command_budget_and_nowait_leave_target_unchanged(self):
        for verb,accepted in (('KCL',4),('KCL_NO_WAIT',0)):
            with self.subTest(verb=verb):
                command,_=compile_program(f"{verb}('SET LOCAL VAR target WORKER = source',s)",context=self.ctx)
                self.assertEqual(command.run(max_steps=3)['S'],accepted);self.assertEqual(self.ctx.kcl.last_status,4)
                self.assertEqual(self.original.values,[8,9]);self.assertEqual(self.task.task_state,'paused')

    def test_replaced_owner_value_or_selected_parent_cannot_redirect_edit(self):
        def replace():self.storage['TARGET']=rt.Array(self.original.spec)
        self.assertEqual(self.during(replace),204);self.assertEqual(self.original.values,[8,9])
        self.setUp()
        self.assertEqual(self.during(replace,path='target[1]',value='3'),204);self.assertEqual(self.original.values,[8,9])

    def test_replaced_task_binding_or_run_generation_blocks_publication(self):
        replacement,_=compile_program('',context=self.ctx)
        def bind():self.ctx.tasks.tasks['WORKER']=replacement
        self.assertEqual(self.during(bind),204);self.assertEqual(self.original.values,[8,9])
        self.setUp()
        def generation():self.task._state._task_run=object()
        self.assertEqual(self.during(generation),204);self.assertEqual(self.original.values,[8,9])

    def test_resumed_or_reshaped_frame_is_not_edited(self):
        def resume():self.task._state.task_state='running'
        self.assertEqual(self.during(resume),204);self.assertEqual(self.original.values,[8,9])
        self.setUp()
        removed=[]
        def remove_frame():removed.append(self.task._state._timer_frames.pop())
        try:
            self.assertEqual(self.during(remove_frame),204);self.assertEqual(self.original.values,[8,9])
        finally:self.task._state._timer_frames.extend(removed)

    def test_changed_continuation_declaration_or_target_schema_is_rejected(self):
        def continued():self.task._state._lifecycle['CONTINUE']+=1
        self.assertEqual(self.during(continued),204);self.assertEqual(self.original.values,[8,9])
        self.setUp()
        def retype():self.task._state._timer_frames[-1][0]['TARGET']=('ARRAY',2,('REAL',))
        self.assertEqual(self.during(retype),204);self.assertEqual(self.original.values,[8,9])

    def test_alias_timer_or_counter_added_during_preparation_is_rechecked(self):
        def alias():self.ctx.variables.bind('ALIAS','VALUE',rt.Reference(('INTEGER',),self.original.values,0))
        self.assertEqual(self.during(alias),204);self.assertEqual(self.original.values,[8,9])
        self.setUp()
        def timer():
            key=id(self.original.values),0;self.ctx._timer_claims[key]=(self.task._state,None,self.original.values,0)
        self.assertEqual(self.during(timer),204);self.assertEqual(self.original.values,[8,9])
        self.setUp()
        with patch.object(type(self.task),'local_for_roots',{'PERFORM':('TARGET',)}):
            self.assertEqual(edit(self.ctx,'target','source')['S'],204)

    def test_source_is_observed_after_last_preparation_checkpoint(self):
        def update():self.storage['SOURCE'].values[1]=42
        self.assertEqual(self.during(update),0);self.assertEqual(self.original.values,[1,42])

    def test_malformed_destination_keeps_every_old_member(self):
        self.original.values.append(10)
        self.assertEqual(edit(self.ctx,'target','source')['S'],205);self.assertEqual(self.original.values,[8,9,10])

    def test_linked_owner_module_resolves_its_local_sources(self):
        ctx=rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True))
        project=translate_project({'m':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN',
            'l':'PROGRAM LIB VAR result:INTEGER ROUTINE work VAR source,target:ARRAY[2]OF INTEGER BEGIN source[1]=3 source[2]=4 PAUSE result=target[2] END work BEGIN END LIB'})
        instance=project.instantiate(context=ctx);ctx.tasks.bind('WORKER',instance.programs['MAIN'])
        with self.assertRaises(rt.KarelPause):instance.programs['MAIN'].run()
        self.assertEqual(edit(ctx,'target','source',scope='IN work FROM LIB WORKER')['S'],0)
        self.assertEqual(edit(ctx,'target[2]','42',scope='IN work FROM LIB WORKER')['S'],0)
        instance.programs['MAIN'].resume();self.assertEqual(instance.programs['LIB'].snapshot()['RESULT'],42)
