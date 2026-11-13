"""Authored exact detached KCL logical copies, admission and ownership guards."""
import json
import unittest
from unittest.mock import patch

from karel2py import dynamic,runtime as rt
from tests.test_extended_services import compile_program
from tests.test_kcl_task_commands import issue


NODE=('STRUCTURE','NODE_T',(('VALUE',rt.INTEGER),('LABEL',('STRING',3))))
HEADER=('STRUCTURE','HEADER_T',(('COUNT',rt.INTEGER),))
PATH=('PATH',NODE,HEADER)
QUEUE=('QUEUE_TYPE',)


def context():return rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True,program_commands=True))


def seed(value,number=7):
    if type(value) is rt.Array:
        for item in value.values:seed(item,number)
    elif type(value) is rt.PathValue:
        value.append();value.nodes[-1].values.update(VALUE=number,LABEL='ok')
        if value.data is not None:value.data.values['COUNT']=len(value.nodes)
    else:value.initialized=True;value.sequence=1;value.entries=[(1,number)]


def content(value):
    return value.nodes[-1].values['VALUE'] if type(value) is rt.PathValue else value.entries[-1][1]


def setup(spec):
    ctx=context();source=ctx.variables.define('CACHE','SOURCE',spec);target=ctx.variables.define('CACHE','TARGET',spec)
    seed(source.raw())
    return ctx,source,target


def command(ctx,target='TARGET',source='SOURCE',**options):
    return issue(ctx,f'SET VAR [CACHE]{target} = [CACHE]{source}',**options)['S']


class LogicalCopyCases:
    def test_scalar_copy_retains_receiver_and_independent_contents(self):
        ctx,source,target=setup(self.spec);original=target.raw()
        self.assertEqual(command(ctx),0)
        self.assertIs(target.raw(),original)
        self.assertEqual(content(original),7)
        seed(source.raw(),99)
        self.assertEqual(content(original),7)

    def test_self_copy_retains_root_and_replaces_owned_payload(self):
        ctx,source,_=setup(self.spec);value=source.raw()
        before=rt.snapshot_value(value);payload=value.nodes if self.spec[0]=='PATH' else value.entries
        self.assertEqual(command(ctx,target='SOURCE'),0)
        self.assertIs(source.raw(),value);self.assertEqual(rt.snapshot_value(value),before)
        self.assertIsNot(value.nodes if self.spec[0]=='PATH' else value.entries,payload)

    def test_whole_bank_copies_all_ranks_without_replacing_cells(self):
        for dimensions in (2,(2,2),(1,2,2)):
            with self.subTest(dimensions=dimensions):
                ctx,source,target=setup(('ARRAY',dimensions,self.spec))
                original=target.raw();storage=original.values;cells=list(storage)
                self.assertEqual(command(ctx),0)
                self.assertIs(target.raw(),original);self.assertIs(original.values,storage)
                self.assertTrue(all(a is b for a,b in zip(cells,storage)))
                self.assertTrue(all(content(item)==7 for item in storage))
                seed(source.raw(),99)
                self.assertTrue(all(content(item)==7 for item in storage))

    def test_complete_indexed_cell_copies_and_preserves_siblings(self):
        ctx,source,target=setup(('ARRAY',(2,2),self.spec))
        sibling=rt.snapshot_value(target.raw().values[0])
        self.assertEqual(command(ctx,target='TARGET[2][1]',source='SOURCE[1,2]'),0)
        self.assertEqual(content(target.raw().values[2]),7)
        self.assertEqual(rt.snapshot_value(target.raw().values[0]),sibling)
        self.assertEqual(ctx.entries,{})

    def test_complete_named_component_can_copy(self):
        row=('ARRAY',2,self.spec,'ROW_T');bank=('ARRAY',2,row,'BANK_T')
        ctx,source,target=setup(bank)
        row_value=target.raw().values[1];cells=list(row_value.values)
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[1]'),0)
        self.assertIs(target.raw().values[1],row_value)
        self.assertTrue(all(a is b for a,b in zip(cells,row_value.values)))
        self.assertEqual([content(item) for item in row_value.values],[7,7])

    def test_compiled_source_can_copy_to_detached_target(self):
        ctx=context();typename='route_t' if self.spec[0]=='PATH' else 'QUEUE_TYPE'
        prefix='TYPE node_t=STRUCTURE value:INTEGER label:STRING[3] ENDSTRUCTURE header_t=STRUCTURE count:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t' if self.spec[0]=='PATH' else ''
        task,_=compile_program('',decl='source:'+typename,prefix=prefix,context=ctx)
        seed(task._state.values['SOURCE']);target=ctx.variables.define('CACHE','TARGET',self.spec)
        self.assertEqual(issue(ctx,'SET VAR [CACHE]TARGET=[T]SOURCE')['S'],0)
        self.assertEqual(content(target.raw()),7)
        self.assertEqual(issue(ctx,'SET VAR [T]SOURCE=[CACHE]TARGET')['S'],204)

    def test_no_wait_and_saved_closed_context(self):
        ctx,_,target=setup(self.spec)
        values=issue(ctx,'SET VAR [CACHE]TARGET=SOURCE',nowait=True)
        self.assertEqual(values,{'S':0,'N':0});self.assertEqual(content(target.raw()),7)
        saved=json.loads(json.dumps(ctx.to_config()))
        restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        self.assertEqual(command(restored),0)

    def test_source_is_sampled_after_final_admitted_charge(self):
        ctx,source,target=setup(self.spec)
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==3:
                if self.spec[0]=='PATH':source.raw().nodes[0].values['VALUE']=42
                else:source.raw().entries[0]=(1,42)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):self.assertEqual(command(ctx),0)
        self.assertEqual(content(target.raw()),42)
        self.assertEqual(len(calls),7 if self.spec[0]=='PATH' else 5)

    def test_budget_failure_precedes_snapshot_and_keeps_receiver(self):
        ctx,_,target=setup(self.spec);before=rt.snapshot_value(target.raw())
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==3:raise rt.KarelRuntimeError('Execution step budget exhausted',line)
        codec='collection_source_value'
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint),patch.object(rt,codec,side_effect=AssertionError('premature copy')):
            self.assertEqual(command(ctx),4)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_source_growth_after_admission_rejects_without_copy(self):
        ctx,source,target=setup(self.spec);before=rt.snapshot_value(target.raw())
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:
                if self.spec[0]=='PATH':seed(source.raw(),99)
                else:source.raw().sequence=2;source.raw().entries.append((2,99))
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(command(ctx),205)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_target_root_replacement_during_charge_is_protected(self):
        ctx,_,target=setup(self.spec);old=target.raw();replacement=rt.initial_value(self.spec)
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:target.storage[target.key]=replacement
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):self.assertEqual(command(ctx),204)
        self.assertIs(target.raw(),replacement);self.assertIsNot(target.raw(),old)
        self.assertEqual(rt.snapshot_value(old),rt.snapshot_value(rt.initial_value(self.spec)))

    def test_retargeted_root_reference_to_same_value_is_protected(self):
        ctx,_,target=setup(self.spec);old=target.raw();actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:target.storage={'replacement':old};target.key='replacement'
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):self.assertEqual(command(ctx),204)
        self.assertEqual(rt.snapshot_value(old),rt.snapshot_value(rt.initial_value(self.spec)))

    def test_alias_created_during_charge_protects_whole_owner(self):
        ctx,_,target=setup(('ARRAY',2,self.spec));before=rt.snapshot_value(target.raw())
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:ctx.variables.bind('ALIAS','SIBLING',rt.Reference(self.spec,target.raw().values,0))
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):
            self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),204)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_shared_collection_cells_are_invalid(self):
        for name in ('SOURCE','TARGET'):
            with self.subTest(name=name):
                ctx,source,target=setup(('ARRAY',2,self.spec))
                bank=(source if name=='SOURCE' else target).raw();bank.values[1]=bank.values[0]
                before=rt.snapshot_value(target.raw())
                self.assertEqual(command(ctx),205);self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_malformed_last_bank_cell_keeps_all_receiver_cells(self):
        ctx,source,target=setup(('ARRAY',2,self.spec));before=rt.snapshot_value(target.raw())
        source.raw().values[-1]=rt.UNINITIALIZED
        self.assertEqual(command(ctx),205);self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_changed_variable_store_is_protected_even_if_bindings_match(self):
        ctx,_,target=setup(self.spec);before=rt.snapshot_value(target.raw())
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:
                replacement=rt.ExecutionContext().variables
                replacement.bindings=ctx.variables.bindings.copy();ctx.variables=replacement
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):self.assertEqual(command(ctx),204)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_destination_growth_after_admission_is_not_overwritten(self):
        ctx,_,target=setup(self.spec);actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:seed(target.raw(),88)
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):self.assertEqual(command(ctx),205)
        self.assertEqual(content(target.raw()),88)

    def test_late_source_binding_with_matching_schema_and_size_is_read(self):
        ctx,_,target=setup(self.spec);replacement=rt.initial_value(self.spec);seed(replacement,42)
        actual=dynamic.variable_checkpoint;calls=[]
        def checkpoint(state,line):
            actual(state,line);calls.append(1)
            if len(calls)==2:ctx.variables.bindings['CACHE','SOURCE']=rt.Reference(self.spec,{'value':replacement},'value')
        with patch.object(dynamic,'variable_checkpoint',side_effect=checkpoint):self.assertEqual(command(ctx),0)
        self.assertEqual(content(target.raw()),42)

    def test_collection_rows_copy_with_original_receiver_cells(self):
        ctx,source,target=setup(('ARRAY',(2,2),self.spec));cells=list(target.raw().values)
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[1]'),0)
        self.assertTrue(all(a is b for a,b in zip(cells,target.raw().values)))
        self.assertEqual([content(item) for item in target.raw().values[2:]],[7,7])


class KclPathCopyTests(LogicalCopyCases,unittest.TestCase):
    spec=PATH

    def test_partial_node_and_header_data_preserve_unknown_markers(self):
        ctx,source,target=setup(PATH);source.raw().data=rt.UNINITIALIZED
        source.raw().nodes[0].values['LABEL']=rt.UNINITIALIZED;source.raw().nodes.append(rt.UNINITIALIZED)
        self.assertEqual(command(ctx),0)
        self.assertEqual(rt.snapshot_value(target.raw()),rt.snapshot_value(source.raw()))

    def test_header_container_stays_live_old_nodes_detach(self):
        ctx,source,target=setup(PATH);seed(target.raw(),88)
        header=target.raw().data;old_nodes=target.raw().nodes;old_node=old_nodes[0]
        self.assertEqual(command(ctx),0)
        self.assertIs(target.raw().data,header);self.assertIsNot(target.raw().nodes,old_nodes)
        self.assertEqual(old_node.values['VALUE'],88);self.assertEqual(content(target.raw()),7)

    def test_missing_and_empty_headerless_paths_copy(self):
        ctx,source,target=setup(('PATH',NODE,None));source.raw().nodes=[]
        self.assertEqual(command(ctx),0);self.assertEqual(target.raw().nodes,[])
        source.storage[source.key]=rt.UNINITIALIZED
        self.assertEqual(command(ctx),205)

    def test_path_layouts_remain_exact(self):
        ctx,source,target=setup(PATH)
        source.spec=('PATH',('STRUCTURE','OTHER_T',NODE[2]),HEADER)
        self.assertEqual(command(ctx),205);self.assertEqual(target.raw().nodes,[])

    def test_malformed_source_data_does_not_publish(self):
        for invalid in (float('nan'),'bad',True):
            with self.subTest(invalid=invalid):
                ctx,source,target=setup(PATH);source.raw().nodes[0].values['VALUE']=invalid
                before=rt.snapshot_value(target.raw())
                self.assertEqual(command(ctx),205);self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_shared_path_header_node_and_overlong_string_are_invalid(self):
        for mode in ('shared_node','overlong','missing_field'):
            with self.subTest(mode=mode):
                ctx,source,target=setup(PATH)
                if mode=='shared_node':source.raw().nodes.append(source.raw().nodes[0])
                elif mode=='overlong':source.raw().nodes[0].values['LABEL']='long'
                else:del source.raw().nodes[0].values['VALUE']
                self.assertEqual(command(ctx),205);self.assertEqual(target.raw().nodes,[])

    def test_timer_on_header_sibling_protects_complete_target_root(self):
        ctx,_,target=setup(('ARRAY',2,PATH))
        data=target.raw().values[0].data.values;ctx._timer_claims[id(data),'COUNT']=(None,None,data,'COUNT')
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),204)
        self.assertEqual(target.raw().values[1].nodes,[])


class KclQueueCopyTests(LogicalCopyCases,unittest.TestCase):
    spec=QUEUE

    def test_uninitialized_queue_is_copyable_state(self):
        ctx,source,target=setup(QUEUE);seed(target.raw(),88)
        source.raw().initialized=False;source.raw().sequence=0;source.raw().entries=[]
        self.assertEqual(command(ctx),0)
        self.assertEqual((target.raw().initialized,target.raw().sequence,target.raw().entries),(False,0,[]))

    def test_buffer_links_reset_without_changing_old_buffer_data(self):
        ctx,source,target=setup(('ARRAY',2,QUEUE))
        seed(target.raw(),88)
        old=rt.Array(('ARRAY',2,rt.INTEGER));old.values[:]=[88,99]
        for item in (*source.raw().values,*target.raw().values):item.buffer=old
        untouched=target.raw().values[0]
        self.assertEqual(command(ctx,target='TARGET[2]',source='SOURCE[2]'),0)
        self.assertIs(untouched.buffer,old);self.assertIsNone(target.raw().values[1].buffer)
        self.assertIs(source.raw().values[1].buffer,old);self.assertEqual(old.values,[88,99])

    def test_invalid_queue_sequences_and_entries_do_not_publish(self):
        for attribute,value in (('sequence',0),('entries',[(1,'bad')]),('entries',[(1,7),(1,8)]),('initialized',False),('entries',None)):
            with self.subTest(attribute=attribute,value=value):
                ctx,source,target=setup(QUEUE);setattr(source.raw(),attribute,value)
                self.assertEqual(command(ctx),205)
                self.assertFalse(target.raw().initialized);self.assertEqual(target.raw().entries,[])

    def test_over_limit_queue_and_bank_are_rejected_before_snapshot(self):
        for bank in (False,True):
            with self.subTest(bank=bank):
                ctx,source,target=setup(('ARRAY',2,QUEUE) if bank else QUEUE)
                item=source.raw().values[0] if bank else source.raw();item.sequence=16384
                item.entries=[(index,index) for index in range(1,16385)]
                with patch.object(rt,'collection_array_source_value',side_effect=AssertionError('premature bank snapshot')),patch.object(rt,'collection_source_value',side_effect=AssertionError('premature scalar snapshot')):
                    self.assertEqual(command(ctx),205)


class KclLogicalCopyBoundaryTests(unittest.TestCase):
    def test_wrong_schema_and_aggregate_literals_stay_rejected(self):
        ctx,_,target=setup(PATH);before=rt.snapshot_value(target.raw())
        ctx.variables.define('CACHE','Q',QUEUE)
        self.assertEqual(command(ctx,source='Q'),205)
        self.assertEqual(issue(ctx,'SET VAR [CACHE]TARGET=1,2')['S'],205)
        self.assertEqual(rt.snapshot_value(target.raw()),before)

    def test_named_array_identity_stays_exact(self):
        ctx,_,target=setup(('ARRAY',2,QUEUE,'BANK_T'))
        ctx.variables.define('CACHE','OTHER',('ARRAY',2,QUEUE,'OTHER_T'))
        self.assertEqual(command(ctx,source='OTHER'),205)

    def test_opt_in_script_precedence_and_default_namespace_unchanged(self):
        ctx,_,target=setup(QUEUE)
        self.assertEqual(issue(ctx,'SET DEFAULT CACHE')['S'],0)
        self.assertEqual(issue(ctx,'SET VARIABLE TARGET=SOURCE')['S'],0)
        self.assertEqual(content(target.raw()),7)
        disabled=rt.ExecutionContext(kcl=rt.KclCommands())
        self.assertNotEqual(issue(disabled,'SET VAR [CACHE]TARGET=SOURCE')['S'],0)
        scripted=rt.ExecutionContext(kcl=rt.KclCommands({'SET VAR [CACHE]TARGET=SOURCE':{'status':19}},variable_commands=True))
        self.assertEqual(issue(scripted,'SET VAR [CACHE]TARGET=SOURCE')['S'],19)

    def test_report_scope_matches_detached_logical_contract(self):
        _,result=compile_program('')
        policy=result.report['kcl_collection_copy_policy']
        self.assertIn('PATH',policy['values']);self.assertIn('QUEUE_TYPE',policy['values'])
        self.assertIn('both',policy['budget']);self.assertIn('paused-local',policy['boundary'])
        self.assertEqual(policy['guide'],'docs/kcl-collection-copies.md')
        self.assertFalse(policy['controller_validated'])


if __name__=='__main__':unittest.main()
