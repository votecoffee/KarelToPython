"""Authored owned paused-local logical copies, source scopes and lifetime guards."""
import json
import unittest
from unittest.mock import patch

from karel2py import dynamic,runtime as rt,translate_project
from tests.test_extended_services import compile_program
from tests.test_kcl_collection_copies import PATH,QUEUE,context,seed,content
from tests.test_kcl_inspection_commands import listing
from tests.test_kcl_local_data_paths import paused,edit
from tests.test_kcl_task_commands import issue


PREFIX='TYPE node_t=STRUCTURE value:INTEGER label:STRING[3] ENDSTRUCTURE header_t=STRUCTURE count:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t'


class LocalLogicalCases:
    def build(self,shape=None,body='PAUSE',*,globals_='n,s:INTEGER'):
        typename='route_t' if self.spec==PATH else 'QUEUE_TYPE'
        if shape:typename='ARRAY['+','.join(map(str,shape))+']OF '+typename
        ctx,task,storage=paused('source,target:'+typename,body=body,prefix=PREFIX if self.spec==PATH else '',globals_=globals_)
        seed(storage['SOURCE'])
        return ctx,task,storage

    def during(self,change,*,shape=None,path='target',value='source'):
        ctx,task,storage=self.build(shape);actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:change(ctx,task,storage)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):status=edit(ctx,path,value)['S']
        return status,ctx,task,storage

    def test_scalar_owned_local_copies_and_continues_without_aliasing(self):
        kind='route_t' if self.spec==PATH else 'QUEUE_TYPE'
        ctx,task,storage=self.build(body='PAUSE result=target',globals_='n,s:INTEGER result:'+kind)
        target=storage['TARGET']
        self.assertEqual(edit(ctx,'target','source')['S'],0)
        self.assertIs(storage['TARGET'],target);self.assertEqual(content(target),7)
        seed(storage['SOURCE'],99);self.assertEqual(content(target),7)
        result=task.resume()['RESULT']
        self.assertEqual(result,rt.snapshot_value(target));self.assertEqual(task.task_state,'completed')
        self.assertEqual(task._state._timer_frames,[])

    def test_whole_banks_rows_planes_and_original_cells(self):
        for shape,target_path,source_path,indices in (((2,),'target','source',[0,1]),((2,2),'target[2]','source[1]',[2,3]),((2,2,2),'target[2]','source[1]',[4,5,6,7]),((2,2,2),'target[1][2]','source[2,1]',[2,3])):
            with self.subTest(shape=shape,path=target_path):
                ctx,task,storage=self.build(shape);target=storage['TARGET'];cells=list(target.values);values=target.values
                self.assertEqual(edit(ctx,target_path,source_path)['S'],0)
                self.assertIs(storage['TARGET'],target);self.assertIs(target.values,values)
                self.assertTrue(all(a is b for a,b in zip(cells,values)))
                self.assertEqual([content(values[index]) for index in indices],[7]*len(indices))
                task.resume();self.assertEqual(task.task_state,'completed')

    def test_same_root_and_self_copy_keep_independent_payloads(self):
        ctx,_,storage=self.build((2,2));root=storage['SOURCE'];cells=list(root.values)
        self.assertEqual(edit(ctx,'source[2]','source[1]')['S'],0)
        self.assertEqual(edit(ctx,'source[2]','source[2]')['S'],0)
        if self.spec==PATH:root.values[0].nodes[0].values['VALUE']=99
        else:root.values[0].entries[0]=(1,99)
        self.assertEqual(content(root.values[2]),7)
        self.assertTrue(all(a is b for a,b in zip(cells,root.values)))

    def test_named_array_components_keep_exact_schemas_and_cells(self):
        kind='route_t' if self.spec==PATH else 'QUEUE_TYPE'
        prefix=(PREFIX+' ' if self.spec==PATH else 'TYPE ')+f'row_t=ARRAY[2]OF {kind} bank_t=ARRAY[2]OF row_t'
        ctx,_,storage=paused('source:bank_t target:row_t',prefix=prefix)
        seed(storage['SOURCE']);target=storage['TARGET'];cells=list(target.values)
        self.assertEqual(edit(ctx,'target','source[2]')['S'],0)
        self.assertIs(storage['TARGET'],target);self.assertTrue(all(a is b for a,b in zip(cells,target.values)))
        self.assertEqual([content(item) for item in target.values],[7,7])

    def test_local_shadowing_explicit_globals_and_detached_sources(self):
        kind='route_t' if self.spec==PATH else 'QUEUE_TYPE'
        ctx,task,storage=self.build(globals_='n,s:INTEGER source:'+kind)
        seed(task._state.values['SOURCE'],42)
        self.assertEqual(edit(ctx,'target','source')['S'],0);self.assertEqual(content(storage['TARGET']),7)
        self.assertEqual(edit(ctx,'target','[T]source')['S'],0);self.assertEqual(content(storage['TARGET']),42)
        external=ctx.variables.define('INPUTS','VALUE',self.spec);seed(external.raw(),31)
        self.assertEqual(edit(ctx,'target','[INPUTS]value')['S'],0);self.assertEqual(content(storage['TARGET']),31)

    def test_missing_local_source_falls_back_to_module_globals(self):
        kind='route_t' if self.spec==PATH else 'QUEUE_TYPE'
        ctx,task,storage=self.build(globals_='n,s:INTEGER global_source:'+kind)
        seed(task._state.values['GLOBAL_SOURCE'],42)
        self.assertEqual(edit(ctx,'target','global_source')['S'],0);self.assertEqual(content(storage['TARGET']),42)

    def test_invalid_declared_local_never_falls_back_to_global(self):
        kind='route_t' if self.spec==PATH else 'QUEUE_TYPE'
        ctx,task,storage=self.build(globals_='n,s:INTEGER source:'+kind)
        seed(task._state.values['SOURCE'],42);storage['SOURCE']=rt.UNINITIALIZED
        before=rt.snapshot_value(storage['TARGET'])
        self.assertEqual(edit(ctx,'target','source')['S'],205)
        self.assertEqual(rt.snapshot_value(storage['TARGET']),before)

    def test_local_source_scope_and_receiver_root_are_both_charged(self):
        ctx,_,storage=self.build((2,2));actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):actual(state,line);calls.append(1)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(edit(ctx,'target[2]','source[1]')['S'],0)
        self.assertEqual(len(calls),25 if self.spec==PATH else 17)
        self.assertEqual([content(item) for item in storage['TARGET'].values[2:]],[7,7])

    def test_budget_failure_precedes_payload_allocation(self):
        ctx,_,storage=self.build((2,2));before=rt.snapshot_value(storage['TARGET'])
        caller,_=compile_program("KCL('SET LOCAL VAR target[2] WORKER = source[1]',s)",context=ctx)
        with patch.object(rt,'collection_array_source_value',side_effect=AssertionError('copied before budget')),patch('karel2py.storage.collection_payload',side_effect=AssertionError('encoded before budget')):
            self.assertEqual(caller.run(max_steps=3)['S'],4)
        self.assertEqual(rt.snapshot_value(storage['TARGET']),before)

    def test_malformed_unselected_source_and_receiver_block_all_writes(self):
        for name in ('SOURCE','TARGET'):
            with self.subTest(name=name):
                ctx,_,storage=self.build((2,2));seed(storage['TARGET'],88)
                value=storage[name].values[0]
                if self.spec==PATH:value.nodes[0].values['LABEL']='long'
                else:value.entries[0]=(1,'bad')
                before=rt.snapshot_value(storage['TARGET'])
                self.assertEqual(edit(ctx,'target[2]','source[2]')['S'],205)
                self.assertEqual(rt.snapshot_value(storage['TARGET']),before)

    def test_owner_replacement_during_charge_is_protected(self):
        old=[]
        def change(ctx,task,storage):
            old.append(storage['TARGET']);storage['TARGET']=rt.initial_value(old[0].spec)
        status,_,_,storage=self.during(change,shape=(2,2),path='target[2]',value='source[2]')
        self.assertEqual(status,204);self.assertIsNot(storage['TARGET'],old[0])
        self.assertEqual(rt.snapshot_value(storage['TARGET']),rt.snapshot_value(old[0]))

    def test_backing_list_replacement_during_charge_is_protected(self):
        old=[]
        def change(ctx,task,storage):
            old.append(storage['TARGET'].values);storage['TARGET'].values=list(old[0])
        status,_,_,storage=self.during(change,shape=(2,2),path='target[2]',value='source[2]')
        self.assertEqual(status,204);self.assertIsNot(storage['TARGET'].values,old[0])
        self.assertTrue(all(a is b for a,b in zip(storage['TARGET'].values,old[0])))

    def test_late_source_same_size_changes_are_included(self):
        def change(ctx,task,storage):
            value=storage['SOURCE'].values[2]
            if self.spec==PATH:value.nodes[0].values['VALUE']=42
            else:value.entries[0]=(1,42)
        status,_,_,storage=self.during(change,shape=(2,2),path='target[2]',value='source[2]')
        self.assertEqual(status,0);self.assertEqual(content(storage['TARGET'].values[2]),42)

    def test_late_source_growth_rejects_before_snapshot(self):
        def change(ctx,task,storage):
            value=storage['SOURCE'].values[0]
            if self.spec==PATH:seed(value,99)
            else:value.sequence=2;value.entries.append((2,99))
        with patch.object(rt,'collection_array_source_value',side_effect=AssertionError('copied changed scope')):
            status,_,_,storage=self.during(change,shape=(2,2),path='target[2]',value='source[2]')
        self.assertEqual(status,205)
        self.assertTrue(all(not item.nodes if self.spec==PATH else not item.entries for item in storage['TARGET'].values))

    def test_new_retained_alias_on_unselected_sibling_blocks_root(self):
        def change(ctx,task,storage):ctx.variables.bind('OTHER','ALIAS',rt.Reference(self.spec,storage['TARGET'].values,0))
        status,_,_,_=self.during(change,shape=(2,2),path='target[2]',value='source[2]')
        self.assertEqual(status,204)

    def test_new_variable_store_or_program_metadata_is_protected(self):
        for mode in ('store','program','counter'):
            with self.subTest(mode=mode):
                def change(ctx,task,storage):
                    if mode=='store':
                        replacement=rt.ExecutionContext().variables;replacement.bindings=ctx.variables.bindings.copy();replacement.programs=ctx.variables.programs.copy();ctx.variables=replacement
                    elif mode=='program':task._state.program=object()
                    else:task._state.program.local_for_roots['PERFORM']=('TARGET',)
                status,_,_,_=self.during(change)
                self.assertEqual(status,204)

    def test_resume_stop_or_registry_rebind_during_charge_is_protected(self):
        for mode in ('state','continue','stop','binding'):
            with self.subTest(mode=mode):
                def change(ctx,task,storage):
                    if mode=='state':task._state.task_state='running'
                    elif mode=='continue':task._state._lifecycle['CONTINUE']+=1
                    elif mode=='stop':task.stop()
                    else:ctx.tasks.bind('WORKER',compile_program('',context=ctx,cooperative=True)[0])
                status,_,_,_=self.during(change)
                self.assertEqual(status,204)

    def test_nowait_default_task_and_closed_data_save_after_resume(self):
        kind='route_t' if self.spec==PATH else 'QUEUE_TYPE'
        ctx,task,storage=self.build(body='PAUSE result=target',globals_='n,s:INTEGER result:'+kind)
        self.assertEqual(issue(ctx,'SET DEFAULT WORKER')['S'],0)
        self.assertEqual(edit(ctx,'target','source',scope='',nowait=True),{'S':0,'N':0})
        task.resume();saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        self.assertFalse(any(row['path'] in ('SOURCE','TARGET') for row in saved['variables']))

    def test_show_local_row_keeps_task_paused_and_data_unmodified(self):
        ctx,task,storage=self.build((2,2));before=rt.snapshot_value(storage['SOURCE'])
        status,rows=listing(ctx,'SHOW LOCAL VAR source[2] IN perform FROM T WORKER')
        self.assertEqual((status,rows[0]['dimensions'],rows[0]['routine'],rows[0]['task']),(0,[2],'PERFORM','WORKER'))
        self.assertEqual(len(rows[0]['value']),2)
        self.assertEqual(rt.snapshot_value(storage['SOURCE']),before);self.assertEqual(task.task_state,'paused')

    def test_exact_remaining_schema_and_literals_remain_guarded(self):
        ctx,_,storage=self.build((2,2));before=rt.snapshot_value(storage['TARGET'])
        for path,value in (('target','source[1]'),('target[2]','1,2'),('target[2]','TRUE')):
            with self.subTest(path=path,value=value):self.assertEqual(edit(ctx,path,value)['S'],205)
        self.assertEqual(rt.snapshot_value(storage['TARGET']),before)


class LocalPathCopies(LocalLogicalCases,unittest.TestCase):
    spec=PATH

    def test_partial_headers_nodes_and_old_alias_lifetime(self):
        ctx,_,storage=self.build((2,2));seed(storage['TARGET'],88)
        old=storage['TARGET'].values[2].nodes;header=storage['TARGET'].values[2].data
        storage['SOURCE'].values[2].nodes[0].values['LABEL']=rt.UNINITIALIZED
        storage['SOURCE'].values[3].data=rt.UNINITIALIZED
        self.assertEqual(edit(ctx,'target[2]','source[2]')['S'],0)
        self.assertIs(storage['TARGET'].values[2].data,header);self.assertEqual(old[0].values['VALUE'],88)
        self.assertIs(storage['TARGET'].values[2].nodes[0].values['LABEL'],rt.UNINITIALIZED)
        self.assertIs(storage['TARGET'].values[3].data,rt.UNINITIALIZED)

    def test_timer_and_private_header_alias_protect_whole_root(self):
        for mode in ('timer','header'):
            ctx,_,storage=self.build((2,2));header=storage['TARGET'].values[0].data
            if mode=='timer':ctx._timer_claims[id(header.values),'COUNT']=(None,None,header.values,'COUNT')
            else:ctx.variables.bind('OTHER','HEADER',rt.Reference(header.spec,{'value':header},'value'))
            self.assertEqual(edit(ctx,'target[2]','source[2]')['S'],204)

    def test_borrowed_header_formal_and_for_root_stay_protected(self):
        ctx=context();task,_=compile_program('outer',context=ctx,prefix=PREFIX,cooperative=True,routines='''
          ROUTINE outer VAR target,source:route_t BEGIN consume(target.count) END outer
          ROUTINE consume(alias:INTEGER) BEGIN PAUSE END consume
        ''');ctx.tasks.bind('WORKER',task)
        with self.assertRaises(rt.KarelPause):task.run()
        storage=task._state._timer_frames[0][1];seed(storage['SOURCE'])
        self.assertEqual(edit(ctx,'target','source',scope='IN outer WORKER')['S'],204)

    def test_source_declared_path_for_counter_protects_containing_local(self):
        ctx,_,storage=paused('source,target:route_t',prefix=PREFIX,
                            body='FOR target.count=1 TO 2 DO PAUSE ENDFOR')
        seed(storage['SOURCE'])
        self.assertEqual(edit(ctx,'target','source')['S'],204)


class LocalQueueCopies(LocalLogicalCases,unittest.TestCase):
    spec=QUEUE

    def test_copied_links_reset_and_unselected_links_remain_live(self):
        ctx,_,storage=self.build((2,2));seed(storage['TARGET'],88)
        buffer=rt.Array(('ARRAY',2,rt.INTEGER));buffer.values[:]=[88,99]
        for item in (*storage['SOURCE'].values,*storage['TARGET'].values):item.buffer=buffer
        self.assertEqual(edit(ctx,'target[2]','source[2]')['S'],0)
        self.assertTrue(all(item.buffer is buffer for item in storage['SOURCE'].values))
        self.assertTrue(all(item.buffer is buffer for item in storage['TARGET'].values[:2]))
        self.assertTrue(all(item.buffer is None for item in storage['TARGET'].values[2:]))
        self.assertEqual(buffer.values,[88,99])

    def test_uninitialized_queue_source_remains_copyable(self):
        ctx,_,storage=self.build();seed(storage['TARGET'],88)
        storage['SOURCE'].initialized=False;storage['SOURCE'].sequence=0;storage['SOURCE'].entries=[]
        self.assertEqual(edit(ctx,'target','source')['S'],0)
        self.assertFalse(storage['TARGET'].initialized);self.assertEqual(storage['TARGET'].entries,[])


class LocalCollectionInterfaces(unittest.TestCase):
    def test_report_describes_local_lifetime_and_borrowed_source_scope(self):
        _,result=compile_program('')
        policy=result.report['kcl_local_collection_policy']
        self.assertIn('borrowed',policy['source']);self.assertIn('continuation',policy['lifetime'])
        self.assertEqual(policy['guide'],'docs/kcl-local-collections.md');self.assertFalse(policy['controller_validated'])

    def test_borrowed_whole_bank_and_row_sources_can_copy_owned_local_rows(self):
        for argument in ('source',"BYNAME('','SOURCE[2]',entry)"):
            with self.subTest(argument=argument):
                ctx=context();formal='ARRAY[*,*]OF QUEUE_TYPE' if argument=='source' else 'ARRAY OF QUEUE_TYPE'
                selection='input[2]' if argument=='source' else 'input'
                task,_=compile_program(f'work({argument})',decl='source:ARRAY[2,2]OF QUEUE_TYPE result:ARRAY[2]OF QUEUE_TYPE entry:INTEGER',context=ctx,cooperative=True,
                    routines=f'ROUTINE work(input:{formal}) VAR target:ARRAY[2]OF QUEUE_TYPE BEGIN PAUSE result=target END work')
                seed(task._state.values['SOURCE']);ctx.tasks.bind('WORKER',task)
                with self.assertRaises(rt.KarelPause):task.run()
                self.assertEqual(edit(ctx,'target',selection)['S'],0)
                self.assertEqual(edit(ctx,'input',selection)['S'],204)
                result=task.resume()['RESULT'];self.assertEqual([item['entries'] for item in result],[[[1,7]],[[1,7]]])

    def test_linked_owner_source_scopes_and_resume(self):
        ctx=context();project=translate_project({'m':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN',
            'l':'PROGRAM LIB VAR result:ARRAY[2]OF QUEUE_TYPE ROUTINE work VAR source,target:ARRAY[2,2]OF QUEUE_TYPE BEGIN PAUSE result=target[2] END work BEGIN END LIB'})
        instance=project.instantiate(context=ctx);task=instance.programs['MAIN'];ctx.tasks.bind('WORKER',task)
        with self.assertRaises(rt.KarelPause):task.run()
        from karel2py.inspection import _kcl_routine_frame
        storage=_kcl_routine_frame(task._state,'WORK','LIB')[3];seed(storage['SOURCE'])
        self.assertEqual(edit(ctx,'target[2]','source[1]',scope='IN work FROM LIB WORKER')['S'],0)
        task.resume();self.assertEqual([item['entries'] for item in instance.programs['LIB'].snapshot()['RESULT']],[[[1,7]],[[1,7]]])

    def test_path_scalar_fields_file_and_resource_literals_stay_excluded(self):
        ctx,_,storage=paused('target,source:route_t files:ARRAY[2]OF FILE',prefix=PREFIX)
        seed(storage['TARGET']);seed(storage['SOURCE'])
        before=rt.snapshot_value(storage['TARGET'])
        for path,value in (('target[1].value','42'),('target.count','7'),('files[1]','files[2]')):
            with self.subTest(path=path):self.assertNotEqual(edit(ctx,path,value)['S'],0)
        self.assertEqual(rt.snapshot_value(storage['TARGET']),before)

    def test_reference_catalog_bound_rejects_before_publishing(self):
        ctx,_,storage=paused('source,target:QUEUE_TYPE');seed(storage['SOURCE'])
        for index in range(32768):ctx.variables.bind('CATALOG','V'+str(index),rt.Reference(rt.INTEGER,{'value':0},'value'))
        self.assertEqual(edit(ctx,'target','source')['S'],205)
        self.assertFalse(storage['TARGET'].initialized);self.assertEqual(storage['TARGET'].entries,[])


if __name__=='__main__':unittest.main()
