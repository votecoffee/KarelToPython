"""Authored logical KCL prefix copies charge and validate complete owner banks."""
import json
import unittest
from unittest.mock import patch

from karel2py import dynamic,runtime as rt
from tests.test_extended_services import compile_program
from tests.test_kcl_collection_copies import PATH,QUEUE,context,setup,seed,content,command
from tests.test_kcl_inspection_commands import listing
from tests.test_kcl_task_commands import issue


class LogicalPrefixCases:
    def banks(self,shape=(2,2)):return setup(('ARRAY',shape,self.spec))

    def test_row_copy_retains_original_cells_and_unselected_data(self):
        ctx,source,target=self.banks();root=target.raw();storage=root.values;cells=list(storage)
        before=[rt.snapshot_value(item) for item in storage[:2]]
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[1]'),0)
        self.assertIs(target.raw(),root);self.assertIs(root.values,storage)
        self.assertTrue(all(a is b for a,b in zip(cells,storage)))
        self.assertEqual([content(item) for item in storage[2:]],[7,7])
        self.assertEqual([rt.snapshot_value(item) for item in storage[:2]],before)
        seed(source.raw(),99);self.assertEqual([content(item) for item in storage[2:]],[7,7])

    def test_planes_and_comma_chained_rows(self):
        ctx,source,target=self.banks((2,2,2))
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[1]'),0)
        self.assertEqual([content(item) for item in target.raw().values[4:]],[7]*4)
        self.assertEqual(command(ctx,target='TARGET[1][2]',source='SOURCE[2,1]'),0)
        self.assertEqual([content(item) for item in target.raw().values[2:4]],[7,7])

    def test_prefix_source_and_receiver_work_with_whole_rows(self):
        ctx,source,target=self.banks()
        row=ctx.variables.define('CACHE','ROW',('ARRAY',2,self.spec))
        self.assertEqual(command(ctx,target='ROW',source='SOURCE[2]'),0)
        self.assertEqual([content(item) for item in row.raw().values],[7,7])
        self.assertEqual(command(ctx,target='TARGET[2]',source='ROW'),0)
        self.assertEqual([content(item) for item in target.raw().values[2:]],[7,7])

    def test_named_component_prefix_keeps_remaining_schema(self):
        plane=('ARRAY',(2,2),self.spec,'PLANE_T');bank=('ARRAY',2,plane,'BANK_T')
        ctx,source,target=setup(bank);root=target.raw();second=root.values[1];cells=list(second.values)
        self.assertEqual(command(ctx,target='TARGET[2][2]',source='SOURCE[1][1]'),0)
        self.assertIs(target.raw().values[1],second)
        self.assertTrue(all(a is b for a,b in zip(cells,second.values)))
        self.assertEqual([content(item) for item in second.values[2:]],[7,7])
        self.assertEqual(second.spec,plane)

    def test_same_owner_and_self_prefix_copies_are_independent(self):
        ctx,source,_=self.banks();owned=source.raw().values
        self.assertEqual(command(ctx,target='SOURCE[2]',source='SOURCE[1]'),0)
        self.assertIsNot(owned[2],owned[0]);self.assertEqual(content(owned[2]),7)
        if self.spec==PATH:owned[0].nodes[0].values['VALUE']=99
        else:owned[0].entries[0]=(1,99)
        self.assertEqual(content(owned[2]),7)
        self.assertEqual(command(ctx,target='SOURCE[2]',source='SOURCE[2]'),0)
        self.assertEqual(content(owned[2]),7)

    def test_prefix_budget_counts_complete_containing_banks(self):
        ctx,_,target=self.banks();actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):actual(state,line);calls.append(1)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[1]'),0)
        # Four source and four receiver descriptors; PATH headers/nodes or queue pairs.
        self.assertEqual(len(calls),25 if self.spec==PATH else 17)
        self.assertEqual([content(item) for item in target.raw().values[2:]],[7,7])

    def test_budget_failure_does_not_encode_or_snapshot_prefix_data(self):
        ctx,_,target=self.banks();before=rt.snapshot_value(target.raw())
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:raise rt.KarelRuntimeError('budget exhausted',line)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint),patch.object(rt,'collection_array_source_value',side_effect=AssertionError('premature snapshot')),patch('karel2py.storage.collection_payload',side_effect=AssertionError('premature encoding')):
            self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[1]'),4)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_malformed_unselected_source_cell_blocks_copy(self):
        ctx,source,target=self.banks();before=rt.snapshot_value(target.raw())
        if self.spec==PATH:source.raw().values[0].nodes[0].values['LABEL']='long'
        else:source.raw().values[0].entries[0]=(1,'bad')
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),205)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_malformed_unselected_receiver_cell_blocks_copy(self):
        ctx,_,target=self.banks();seed(target.raw(),88)
        if self.spec==PATH:target.raw().values[0].nodes[0].values['VALUE']='bad'
        else:target.raw().values[0].entries[0]=(1,'bad')
        before=rt.snapshot_value(target.raw())
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),205)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_shared_owned_source_or_receiver_siblings_are_invalid(self):
        for which in ('SOURCE','TARGET'):
            with self.subTest(which=which):
                ctx,source,target=self.banks();root=(source if which=='SOURCE' else target).raw()
                root.values[0]=root.values[1];before=rt.snapshot_value(target.raw())
                self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),205)
                self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_unselected_source_growth_rejects_before_snapshot(self):
        ctx,source,target=self.banks();before=rt.snapshot_value(target.raw())
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:
                item=source.raw().values[0]
                if self.spec==PATH:seed(item,99)
                else:item.sequence=2;item.entries.append((2,99))
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint),patch.object(rt,'collection_array_source_value',side_effect=AssertionError('snapshot after size change')):
            self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),205)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_backing_list_replacement_preserves_original_and_new_cells(self):
        ctx,_,target=self.banks();original=target.raw().values;before=rt.snapshot_value(target.raw())
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:target.raw().values=list(original)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),204)
        self.assertIsNot(target.raw().values,original)
        self.assertEqual(rt.snapshot_value(target.raw()),before)
        self.assertTrue(all(a is b for a,b in zip(original,target.raw().values)))

    def test_replaced_owner_with_same_backing_list_is_protected(self):
        ctx,_,target=self.banks();root=target.raw();before=rt.snapshot_value(root)
        replacement=object.__new__(rt.Array);replacement.spec=root.spec;replacement.shape=root.shape;replacement.values=root.values
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:target.storage[target.key]=replacement
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),204)
        self.assertIs(target.raw(),replacement);self.assertEqual(rt.snapshot_value(root),before)

    def test_resized_backing_list_and_removed_complete_cell_are_protected(self):
        for path in ('TARGET[2]','TARGET[2,2]'):
            with self.subTest(path=path):
                ctx,_,target=self.banks();actual=dynamic.variable_checkpoint;calls=[]
                def checkpoint(state,line):
                    actual(state,line);calls.append(1)
                    if len(calls)==2:target.raw().values.pop()
                with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
                    self.assertEqual(command(ctx,target=path,source='SOURCE[2]' if path=='TARGET[2]' else 'SOURCE[2,2]'),204)
                self.assertEqual(len(target.raw().values),3)

    def test_late_same_size_source_replacement_is_sampled(self):
        ctx,source,target=self.banks()
        with rt._numeric_scope('pythonic'):replacement=rt.initial_value(source.spec);seed(replacement,42)
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:source.storage[source.key]=replacement
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),0)
        self.assertEqual([content(item) for item in target.raw().values[2:]],[42,42])

    def test_alias_on_unselected_receiver_sibling_remains_protected(self):
        ctx,_,target=self.banks();before=rt.snapshot_value(target.raw())
        ctx.variables.bind('ALIASES','SIBLING',rt.Reference(self.spec,target.raw().values,0))
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),204)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_compiled_row_source_and_compiled_target_guard(self):
        ctx=context();typename='route_t' if self.spec==PATH else 'QUEUE_TYPE'
        prefix='TYPE node_t=STRUCTURE value:INTEGER label:STRING[3] ENDSTRUCTURE header_t=STRUCTURE count:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t' if self.spec==PATH else ''
        task,_=compile_program('',decl='source:ARRAY[2,2]OF '+typename,prefix=prefix,context=ctx)
        seed(task._state.values['SOURCE']);target=ctx.variables.define('CACHE','TARGET',('ARRAY',(2,2),self.spec))
        self.assertEqual(issue(ctx,'SET VAR [CACHE]TARGET[2]=[T]SOURCE[1]')['S'],0)
        self.assertEqual([content(item) for item in target.raw().values[2:]],[7,7])
        self.assertEqual(issue(ctx,'SET VAR [T]SOURCE[1]=[CACHE]TARGET[2]')['S'],204)

    def test_nowait_save_reload_omit_active_views(self):
        ctx,_,_=self.banks()
        values=issue(ctx,'SET VAR [CACHE]TARGET[2]=SOURCE[2]',nowait=True)
        self.assertEqual(values,{'S':0,'N':0})
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        self.assertFalse(any(row['path'].endswith('[2]') for row in saved['variables']))
        self.assertEqual(command(restored,target='TARGET[1]',source='SOURCE[2]'),0)

    def test_show_prefix_reports_remaining_dimensions_and_selected_values(self):
        ctx,source,_=self.banks((2,2,2));before=rt.snapshot_value(source.raw())
        for path,dimensions,count in (('SOURCE[2]',[2,2],4),('SOURCE[2][1]',[2],2)):
            with self.subTest(path=path):
                status,rows=listing(ctx,'SHOW VAR [CACHE]'+path)
                self.assertEqual((status,rows[0]['dimensions']),(0,dimensions))
                values=rows[0]['value']
                if count==4:values=[item for row in values for item in row]
                self.assertEqual(len(values),count)
                if self.spec==PATH:self.assertTrue(all(item['nodes'][0]['VALUE']==7 for item in values))
                else:self.assertTrue(all(item['entries']==[[1,7]] and item['sequence']==1 for item in values))
        self.assertEqual(rt.snapshot_value(source.raw()),before);self.assertEqual(ctx.entries,{})

    def test_invalid_show_prefix_emits_no_partial_listing(self):
        ctx,source,_=self.banks()
        if self.spec==PATH:source.raw().values[0].nodes[0].values['LABEL']='long'
        else:source.raw().values[0].entries[0]=(1,'bad')
        before=rt.snapshot_value(source.raw());status,rows=listing(ctx,'SHOW VAR [CACHE]SOURCE[2]')
        self.assertNotEqual(status,0);self.assertEqual(rows,[])
        self.assertEqual(rt.snapshot_value(source.raw()),before)

    def test_malformed_owner_metadata_is_a_data_failure(self):
        ctx,source,target=self.banks();before=rt.snapshot_value(target.raw())
        del source.raw().shape
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),205)
        self.assertEqual(rt.snapshot_value(target.raw()),before)


class KclPathPrefixTests(LogicalPrefixCases,unittest.TestCase):
    spec=PATH

    def test_partial_path_row_and_old_header_node_aliases(self):
        ctx,source,target=self.banks();seed(target.raw(),88)
        header=target.raw().values[2].data;old=target.raw().values[2].nodes
        source.raw().values[2].nodes[0].values['LABEL']=rt.UNINITIALIZED
        source.raw().values[3].nodes.append(rt.UNINITIALIZED)
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),0)
        self.assertIs(target.raw().values[2].data,header)
        self.assertEqual(old[0].values['VALUE'],88)
        self.assertIsNot(target.raw().values[2].nodes,old)
        self.assertIs(target.raw().values[2].nodes[0].values['LABEL'],rt.UNINITIALIZED)
        self.assertIs(target.raw().values[3].nodes[-1],rt.UNINITIALIZED)

    def test_header_timer_on_unselected_owner_blocks_row_copy(self):
        ctx,_,target=self.banks();fields=target.raw().values[0].data.values
        ctx._timer_claims[id(fields),'COUNT']=(None,None,fields,'COUNT')
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),204)


class KclQueuePrefixTests(LogicalPrefixCases,unittest.TestCase):
    spec=QUEUE

    def test_copied_queue_links_reset_unselected_and_source_links_stay(self):
        ctx,source,target=self.banks();seed(target.raw(),88)
        buffer=rt.Array(('ARRAY',2,rt.INTEGER));buffer.values[:]=[88,99]
        for item in (*source.raw().values,*target.raw().values):item.buffer=buffer
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),0)
        self.assertTrue(all(item.buffer is buffer for item in source.raw().values))
        self.assertTrue(all(item.buffer is buffer for item in target.raw().values[:2]))
        self.assertTrue(all(item.buffer is None for item in target.raw().values[2:]))
        self.assertEqual(buffer.values,[88,99])

    def test_unselected_content_counts_toward_snapshot_bound(self):
        ctx,source,target=self.banks();item=source.raw().values[0]
        item.sequence=16382;item.entries=[(i,i) for i in range(1,16383)]
        before=rt.snapshot_value(target.raw())
        with patch.object(rt,'collection_array_source_value',side_effect=AssertionError('snapshot beyond bound')):
            self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),205)
        self.assertEqual(rt.snapshot_value(target.raw()),before)


class KclCollectionPrefixBoundaries(unittest.TestCase):
    def test_exact_remaining_types_and_file_prefix_exclusion(self):
        ctx,_,target=setup(('ARRAY',(2,2),QUEUE));before=rt.snapshot_value(target.raw())
        ctx.variables.define('CACHE','PATHS',('ARRAY',(2,2),PATH))
        ctx.variables.define('CACHE','FILES',('ARRAY',(2,2),('FILE',)))
        self.assertEqual(command(ctx,target='TARGET[2]',source='PATHS[2]'),205)
        self.assertNotEqual(command(ctx,target='FILES[2]',source='FILES[1]'),0)
        self.assertNotEqual(listing(ctx,'SHOW VAR [CACHE]FILES[2]')[0],0)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_detached_whole_value_from_explicit_full_path_keeps_precedence(self):
        ctx,_,target=setup(('ARRAY',(2,2),QUEUE))
        row=ctx.variables.define('CACHE','SOURCE[2]',('ARRAY',2,QUEUE)).raw();seed(row,42)
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),0)
        self.assertEqual([content(item) for item in target.raw().values[2:]],[42,42])

    def test_collection_deferred_prefix_requires_explicit_resource_policy(self):
        ctx,source,_=setup(('ARRAY',(2,2),QUEUE))
        with rt._numeric_scope('pythonic'):
            with self.assertRaises(rt.KarelRuntimeError):
                ctx.descend(source,'[2]',prefixes=True,defer_prefix_data=True)
            view=ctx.descend(source,'[2]',prefixes=True,resources='collections',defer_prefix_data=True)
            self.assertEqual(view.spec,('ARRAY',2,QUEUE))
            self.assertEqual([content(item) for item in view.raw().values],[7,7])
            with self.assertRaises(rt.KarelRuntimeError):rt.checked(view.spec,view.raw())

    def test_explicit_live_view_must_match_its_named_owner(self):
        ctx,_,target=setup(('ARRAY',(2,2),QUEUE));foreign=ctx.variables.define('FOREIGN','VALUES',('ARRAY',(2,2),QUEUE))
        seed(foreign.raw(),42)
        with rt._numeric_scope('pythonic'):
            view=ctx.descend(foreign,'[2]',prefixes=True,resources='collections',defer_prefix_data=True)
        ctx.variables.bind('CACHE','SOURCE[2]',view);before=rt.snapshot_value(target.raw())
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),205)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_report_describes_containing_bank_checks_and_prefix_inspection(self):
        _,result=compile_program('')
        policy=result.report['kcl_collection_copy_policy']
        self.assertIn('containing bank',policy['prefixes'])
        self.assertIn('SHOW VAR',policy['inspection'])
        self.assertEqual(policy['prefix_ledger'],'docs/semantics/kcl_collection_prefix_semantics.json')
        self.assertFalse(policy['controller_validated'])


if __name__=='__main__':unittest.main()
