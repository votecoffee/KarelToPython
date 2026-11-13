"""Exact KCL row/plane copies retain detached and paused-local ownership guards."""
import json
import unittest
from unittest.mock import patch

from karel2py import dynamic,runtime as rt
from tests.test_extended_services import compile_program
from tests.test_kcl_task_commands import issue
from tests.test_kcl_inspection_commands import listing
from tests.test_kcl_local_data_paths import paused,edit


def context():return rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True,program_commands=True))


def arrays(ctx=None,*,shape=(2,2),kind=rt.INTEGER):
    ctx=context() if ctx is None else ctx
    grid=ctx.variables.define('CACHE','GRID',('ARRAY',shape,kind)).raw()
    row=ctx.variables.define('CACHE','ROW',('ARRAY',2,kind)).raw()
    return ctx,grid,row


def copy(ctx,target='GRID[2]',source='ROW',*,nowait=False):
    return issue(ctx,f'SET VAR [CACHE]{target} = [CACHE]{source}',nowait=nowait)


class DetachedKclPrefixTests(unittest.TestCase):
    def test_copy_to_and_from_row_preserves_root_storage_and_private_values(self):
        ctx,grid,row=arrays();row.values[:]=[7,9];storage=grid.values
        self.assertEqual(copy(ctx)['S'],0)
        self.assertIs(grid.values,storage);self.assertEqual(grid.snapshot()[1],[7,9])
        row.values[1]=99;self.assertEqual(grid.snapshot()[1],[7,9])
        self.assertEqual(copy(ctx,'ROW','GRID[2]')['S'],0);self.assertEqual(row.values,[7,9])
        caller,result=compile_program('',context=ctx)
        self.assertEqual(result.report['kcl_prefix_data_policy']['guide'],'docs/kcl-data-prefixes.md')
        self.assertFalse(result.report['kcl_prefix_data_policy']['controller_validated'])

    def test_cube_plane_and_comma_chained_rows(self):
        ctx,grid,row=arrays(shape=(2,2,2));row.values[:]=[7,9]
        for target in ('GRID[2,1]','GRID[2][2]'):
            self.assertEqual(copy(ctx,target)['S'],0)
        self.assertEqual(grid.snapshot()[1],[[7,9],[7,9]])
        plane=ctx.variables.define('CACHE','PLANE',('ARRAY',(2,2),rt.INTEGER)).raw()
        self.assertEqual(copy(ctx,'PLANE','GRID[2]')['S'],0);self.assertEqual(plane.snapshot(),[[7,9],[7,9]])

    def test_chained_scalar_paths_normalize_without_aggregate_copy(self):
        ctx,grid,_=arrays()
        self.assertEqual(issue(ctx,'SET VAR [CACHE]GRID[2][1] = 17')['S'],0)
        self.assertEqual(grid.snapshot()[1][0],17)

    def test_row_between_record_fields_keeps_receiver_records_and_aliases(self):
        spec=('STRUCTURE','ITEM',(('N',rt.INTEGER),('LABEL',('STRING',3))))
        ctx,grid,row=arrays(kind=spec);selected=grid.values[2];fields=selected.values
        row.values[0].values.update(N=7,LABEL='a');row.values[1].values.update(N=9,LABEL='b')
        self.assertEqual(copy(ctx)['S'],0);self.assertIs(grid.values[2],selected);self.assertIs(selected.values,fields)
        row.values[0].values['N']=99;self.assertEqual(selected.values,{'N':7,'LABEL':'a'})

    def test_nested_record_array_field_and_named_components(self):
        row_t=('ARRAY',2,rt.INTEGER,'ROW_T');box_t=('STRUCTURE','BOX',(('GRID',('ARRAY',(2,2),row_t)),))
        ctx=context();box=ctx.variables.define('CACHE','BOX',box_t).raw()
        source=ctx.variables.define('CACHE','PLANE',('ARRAY',2,row_t)).raw()
        source.values[0].values[:]=[1,2];source.values[1].values[:]=[3,4]
        self.assertEqual(copy(ctx,'BOX.GRID[2]','PLANE')['S'],0)
        self.assertEqual(box.values['GRID'].values[2].values,[1,2])
        self.assertEqual(box.values['GRID'].spec[2][-1],'ROW_T')

    def test_detached_path_node_data_rows_keep_node_and_array_identity(self):
        ctx=context();node_t=('STRUCTURE','NODE',(('GRID',('ARRAY',(2,2),rt.INTEGER)),))
        path=ctx.variables.define('CACHE','ROUTE',('PATH',node_t,None)).raw()
        node=rt.Structure(node_t);path.nodes.append(node);grid=node.values['GRID'];values=grid.values
        row=ctx.variables.define('CACHE','ROW',('ARRAY',2,rt.INTEGER)).raw();row.values[:]=[7,9]
        self.assertEqual(copy(ctx,'ROUTE[1].GRID[2]')['S'],0)
        self.assertEqual(copy(ctx,'ROW','ROUTE[1].GRID[2]')['S'],0)
        self.assertIs(path.nodes[0],node);self.assertIs(node.values['GRID'],grid);self.assertIs(grid.values,values)
        self.assertEqual(grid.snapshot()[1],[7,9])

    def test_scalar_domains_and_complete_source_are_preserved(self):
        for kind,values in [(rt.BYTE,[0,255]),(rt.SHORT,[-32768,32766]),(rt.BOOLEAN,[True,False]),(rt.REAL,[1.5,-2.]),(('STRING',3),['one','two'])]:
            ctx,grid,row=arrays(kind=kind);row.values[:]=values
            self.assertEqual(copy(ctx)['S'],0);self.assertEqual(grid.values[2:],values)
        for kind in (rt.INTEGER,rt.BYTE,rt.SHORT,rt.BOOLEAN):
            ctx,grid,row=arrays(kind=kind);before=grid.snapshot()
            self.assertEqual(copy(ctx)['S'],205);self.assertEqual(grid.snapshot(),before)

    def test_equal_leaf_count_does_not_reshape_or_convert(self):
        ctx,grid,row=arrays();row.values[:]=[7,9]
        ctx.variables.define('CACHE','REAL_ROW',('ARRAY',2,rt.REAL)).raw().values[:]=[7.,9.]
        ctx.variables.define('CACHE','PLANE',('ARRAY',(1,2),rt.INTEGER)).raw().values[:]=[7,9]
        for source in ('REAL_ROW','PLANE'):
            self.assertEqual(copy(ctx,source=source)['S'],205)
            self.assertEqual(grid.snapshot()[1],[{'uninitialized':True}]*2)

    def test_self_copy_and_nowait_use_complete_source_snapshot(self):
        ctx,grid,row=arrays();row.values[:]=[7,9]
        self.assertEqual(copy(ctx,nowait=True),{'S':0,'N':0})
        self.assertEqual(copy(ctx,source='GRID[2]')['S'],0);self.assertEqual(grid.values[2:],[7,9])

    def test_whole_owner_alias_and_timer_on_unselected_cell_block_row_edit(self):
        for mode in ('alias','timer'):
            ctx,grid,row=arrays();row.values[:]=[7,9]
            if mode=='alias':ctx.variables.bind('OTHER','CELL',rt.Reference(rt.INTEGER,grid.values,0))
            else:ctx._timer_claims[id(grid.values),0]=(None,None,grid.values,0)
            self.assertEqual(copy(ctx)['S'],204);self.assertEqual(grid.values[2:],[rt.UNINITIALIZED]*2)

    def test_compiled_targets_resources_and_array_literals_remain_excluded(self):
        ctx,grid,row=arrays();row.values[:]=[7,9]
        task,_=compile_program("KCL('SET VAR GRID[2] = [CACHE]ROW',s)",decl='grid:ARRAY[2,2]OF INTEGER s:INTEGER',context=ctx)
        self.assertEqual(task.run()['S'],204)
        self.assertEqual(issue(ctx,'SET VAR [CACHE]GRID[2] = 1,2')['S'],205)
        ctx.variables.define('CACHE','FILES',('ARRAY',(2,2),('FILE',)))
        self.assertNotEqual(copy(ctx,'FILES[2]')['S'],0)

    def test_show_selected_rows_and_planes_reports_remaining_dimensions(self):
        ctx,grid,row=arrays();row.values[:]=[7,9];self.assertEqual(copy(ctx)['S'],0)
        status,rows=listing(ctx,'SHOW VAR [CACHE]GRID[2]')
        self.assertEqual((status,rows[0]['dimensions'],rows[0]['value']),(0,[2],[7,9]))
        status,rows=listing(ctx,'SHOW VAR [CACHE]GRID[2][1]');self.assertEqual((status,rows[0]['value']),(0,7))

    def test_saved_roots_keep_values_without_row_bindings(self):
        ctx,grid,row=arrays();row.values[:]=[7,9];self.assertEqual(copy(ctx)['S'],0)
        saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
        self.assertTrue(all(entry['path']!='GRID[2]' for entry in saved['variables']))


class LocalKclPrefixTests(unittest.TestCase):
    def test_owned_local_row_copy_and_resume(self):
        ctx,task,storage=paused('source:ARRAY[2]OF INTEGER grid:ARRAY[2,2]OF INTEGER',body='source[1]=7 source[2]=9 PAUSE n=grid[2,2]')
        original=storage['GRID'];values=original.values
        self.assertEqual(edit(ctx,'grid[2]','source')['S'],0)
        self.assertIs(storage['GRID'],original);self.assertIs(original.values,values);self.assertEqual(task.resume()['N'],9)

    def test_local_source_row_and_cube_row_both_directions(self):
        ctx,_,storage=paused('grid:ARRAY[2,2,2]OF INTEGER row:ARRAY[2]OF INTEGER',body='grid[2,1,1]=7 grid[2,1,2]=9 PAUSE')
        self.assertEqual(edit(ctx,'row','grid[2][1]')['S'],0)
        self.assertEqual(edit(ctx,'grid[2][2]','row')['S'],0);self.assertEqual(storage['GRID'].snapshot()[1],[[7,9],[7,9]])

    def test_local_shadowing_and_explicit_global_source_row(self):
        ctx,task,storage=paused('source:ARRAY[2,2]OF INTEGER target:ARRAY[2]OF INTEGER',body='source[2,1]=7 source[2,2]=9 PAUSE',
                                globals_='n,s:INTEGER source:ARRAY[2,2]OF INTEGER')
        task._state.values['SOURCE'].values[2:]=[11,13]
        self.assertEqual(edit(ctx,'target','source[2]')['S'],0);self.assertEqual(storage['TARGET'].values,[7,9])
        self.assertEqual(edit(ctx,'target','[T]source[2]')['S'],0);self.assertEqual(storage['TARGET'].values,[11,13])

    def test_show_local_row_uses_selected_frame_without_changing_owner(self):
        ctx,task,storage=paused('grid:ARRAY[2,2]OF INTEGER',body='grid[2,1]=7 grid[2,2]=9 PAUSE')
        status,rows=listing(ctx,'SHOW LOCAL VARIABLE grid[2] WORKER')
        self.assertEqual((status,rows[0]['value'],rows[0]['dimensions']),(0,[7,9],[2]));self.assertEqual(task.task_state,'paused')

    def test_local_row_cannot_bypass_timer_counter_or_alias_protection(self):
        for mode in ('timer','counter','alias'):
            body='source[1]=7 source[2]=9 '
            if mode=='timer':body+='grid[1,1]=0 CONNECT TIMER TO grid[1,1] PAUSE DISCONNECT TIMER grid[1,1]'
            elif mode=='counter':body+='FOR grid[1,1]=1 TO 2 DO PAUSE ENDFOR'
            else:body+='PAUSE'
            ctx,_,storage=paused('grid:ARRAY[2,2]OF INTEGER source:ARRAY[2]OF INTEGER',body=body)
            if mode=='alias':ctx.variables.bind('OTHER','CELL',rt.Reference(rt.INTEGER,storage['GRID'].values,0))
            self.assertEqual(edit(ctx,'grid[2]','source')['S'],204)
            self.assertEqual(storage['GRID'].values[2:],[rt.UNINITIALIZED]*2)


class KclPrefixPreparationTests(unittest.TestCase):
    def during(self,action,*,local=False):
        if local:
            ctx,task,storage=paused('grid:ARRAY[2,2]OF INTEGER row:ARRAY[2]OF INTEGER',body='grid[2,1]=8 grid[2,2]=9 row[1]=7 row[2]=11 PAUSE')
            grid=storage['GRID'];row=storage['ROW'];execute=lambda:edit(ctx,'grid[2]','row')['S']
        else:
            ctx,grid,row=arrays();grid.values[2:]=[8,9];row.values[:]=[7,11]
            task=None;storage=None;execute=lambda:copy(ctx)['S']
        checkpoint=dynamic.variable_checkpoint;calls=[]
        def check(state,line):
            checkpoint(state,line);calls.append(1)
            if len(calls)==2:action(ctx,grid,row,task,storage)
        with patch.object(dynamic,'variable_checkpoint',side_effect=check):status=execute()
        return status,ctx,grid,row,task

    def test_root_list_replacement_during_charge_rejects_stale_target(self):
        for local in (False,True):
            status,_,grid,_,_=self.during(lambda c,g,r,t,s:setattr(g,'values',[1,2,99,100]),local=local)
            self.assertEqual((status,grid.values),(204,[1,2,99,100]))

    def test_source_row_edits_before_capture_are_included(self):
        for local in (False,True):
            status,_,grid,_,_=self.during(lambda c,g,r,t,s:r.values.__setitem__(1,42),local=local)
            self.assertEqual((status,grid.values[2:]),(0,[7,42]))

    def test_alias_added_during_capture_still_blocks_whole_owner(self):
        for local in (False,True):
            def alias(ctx,grid,*_):ctx.variables.bind('OTHER','CELL',rt.Reference(rt.INTEGER,grid.values,0))
            status,_,grid,_,_=self.during(alias,local=local)
            self.assertEqual((status,grid.values[2:]),(204,[8,9]))

    def test_detached_root_reference_retargeting_to_same_value_is_rejected(self):
        def retarget(ctx,grid,*_):ctx.variables.bindings['CACHE','GRID'].storage={'value':grid};ctx.variables.bindings['CACHE','GRID'].key='value'
        status,_,grid,_,_=self.during(retarget);self.assertEqual((status,grid.values[2:]),(204,[8,9]))

    def test_local_resume_during_preparation_preserves_target(self):
        status,_,grid,_,_=self.during(lambda c,g,r,t,s:setattr(t._state,'task_state','running'),local=True)
        self.assertEqual((status,grid.values[2:]),(204,[8,9]))

    def test_budget_failure_and_nowait_keep_unpublished_row(self):
        for local in (False,True):
            for nowait in (False,True):
                if local:
                    ctx,_,storage=paused('grid:ARRAY[2,2]OF INTEGER row:ARRAY[2]OF INTEGER',body='row[1]=7 row[2]=9 PAUSE')
                    grid=storage['GRID'];command='SET LOCAL VAR grid[2] WORKER = row'
                else:
                    ctx,grid,row=arrays();row.values[:]=[7,9];command='SET VAR [CACHE]GRID[2] = [CACHE]ROW'
                verb='KCL_NO_WAIT' if nowait else 'KCL'
                caller,_=compile_program(f"{verb}('{command}',s)",context=ctx)
                with patch.object(rt.Array,'__init__',side_effect=AssertionError('allocated before copy budget')):
                    self.assertEqual(caller.run(max_steps=3)['S'],0 if nowait else 4)
                self.assertEqual(ctx.kcl.last_status,4);self.assertEqual(grid.values[2:],[rt.UNINITIALIZED]*2)


if __name__=='__main__':unittest.main()
