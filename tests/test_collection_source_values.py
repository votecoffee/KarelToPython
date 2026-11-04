"""Authored logical PATH/queue ARRAY source values and exact reference guards."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_collection_array_transfers import prepare,queues,row,collections,raw,snapshot,PREFIX,DECL,QDECL
from tests.test_extended_services import compile_program


def cell(p,name='SOURCE',index=1):return raw(p,name).values[index]

def content(value):return value.nodes[0].values['VALUE'] if type(value) is rt.PathValue and value.nodes else value.entries[-1][1] if type(value) is rt.QueueValue and value.entries else None


class CopyCases:
    def build(self,body='target=source',**options):
        if self.kind=='path':return prepare(body,**options)
        return prepare(body,decl=options.pop('decl',QDECL+' visits:INTEGER'),prefix=options.pop('prefix',''),**options)
    def changed(self,formal='v'):
        return f'{formal}[2][1].value=99' if self.kind=='path' else f'INIT_QUEUE({formal}[2])'
    @property
    def typename(self):return 'route_t' if self.kind=='path' else 'QUEUE_TYPE'

    def test_whole_assignment_detaches_source_data(self):
        p,_=self.build();expected=snapshot(raw(p,'SOURCE'));p.run()
        self.assertEqual(snapshot(raw(p)),expected);self.assertIsNot(cell(p),cell(p,'TARGET'))
        if self.kind=='path':cell(p).nodes[0].values['VALUE']=99
        else:cell(p).entries[:]=[(2,99)]
        self.assertEqual(content(cell(p,'TARGET')),17)

    def test_receiver_array_list_and_cells_stay_live(self):
        p,_=self.build();a=raw(p);storage=a.values;owned=list(storage);p.run()
        self.assertIs(raw(p),a);self.assertIs(raw(p).values,storage)
        self.assertTrue(all(old is new for old,new in zip(owned,raw(p).values)))

    def test_self_assignment_keeps_cells_and_detaches_contents(self):
        p,_=self.build('source=source');old=cell(p);data=old.nodes if self.kind=='path' else old.entries;expected=snapshot(raw(p,'SOURCE'));p.run()
        self.assertIs(cell(p),old);self.assertEqual(snapshot(raw(p,'SOURCE')),expected)
        self.assertIsNot(old.nodes if self.kind=='path' else old.entries,data)

    def test_assignment_does_not_publish_variable_service_cache(self):
        p,_=self.build();p.run();self.assertEqual(p._state.execution.entries,{})

    def test_grouped_source_is_an_independent_value(self):
        p,_=self.build('target=(source)');p.run();self.assertEqual(content(cell(p,'TARGET')),17)

    def test_named_outer_array_identity_is_preserved(self):
        alias=f'TYPE bank_t=ARRAY[2]OF {self.typename}'
        p,_=self.build(decl='source,target:bank_t entry,status,visits:INTEGER',prefix=(PREFIX+' '+alias.removeprefix('TYPE ') if self.kind=='path' else alias))
        before=raw(p).spec;p.run();self.assertEqual(raw(p).spec,before);self.assertEqual(content(cell(p,'TARGET')),17)

    def test_copy_failure_preserves_receiver_and_source(self):
        p,_=self.build();before=p.snapshot()
        if self.kind=='path':cell(p).nodes[0].values['VALUE']='bad'
        else:cell(p).entries=[(2,'bad')]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['TARGET'],before['TARGET'])

    def test_shared_source_cell_is_rejected_before_publication(self):
        p,_=self.build();raw(p,'SOURCE').values[0]=cell(p);before=snapshot(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(snapshot(raw(p)),before)

    def test_shared_receiver_cells_are_rejected_before_publication(self):
        p,_=self.build();raw(p).values[0]=cell(p,'TARGET');before=snapshot(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(snapshot(raw(p)),before)

    def test_malformed_array_storage_is_rejected(self):
        for change in (lambda a:a.values.pop(),lambda a:setattr(a,'shape',(1,2)),lambda a:setattr(a,'spec',('ARRAY',None,a.spec[2]))):
            p,_=self.build();before=snapshot(raw(p));change(raw(p,'SOURCE'))
            with self.subTest(change=change),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(snapshot(raw(p)),before)

    def test_generic_checked_clone_and_value_helpers_stay_closed(self):
        p,_=self.build();source=raw(p,'SOURCE')
        with rt._numeric_scope('pythonic'):
            for operation in (source.clone,lambda:rt.checked(source.spec,source),lambda:rt.value_argument(source.spec,source),lambda:rt.array_result(source.spec,source)):
                with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()

    def test_bare_argument_still_borrows_source_cells(self):
        p,_=self.build('work(source)',routines=f'ROUTINE work(v:ARRAY OF {self.typename}) BEGIN {self.changed()} END work');p.run()
        self.assertEqual(content(cell(p)),99 if self.kind=='path' else None)

    def test_grouped_argument_keeps_caller_unchanged(self):
        p,_=self.build('work((source))',routines=f'ROUTINE work(v:ARRAY OF {self.typename}) BEGIN {self.changed()} END work');expected=snapshot(raw(p,'SOURCE'));p.run()
        self.assertEqual(snapshot(raw(p,'SOURCE')),expected)

    def test_exact_forwarded_argument_aliases_private_copy(self):
        p,_=self.build('work((source))',routines=f'ROUTINE child(v:ARRAY OF {self.typename}) BEGIN {self.changed()} END child ROUTINE work(v:ARRAY OF {self.typename}) BEGIN child(v) END work');expected=snapshot(raw(p,'SOURCE'));p.run()
        self.assertEqual(snapshot(raw(p,'SOURCE')),expected)

    def test_private_argument_survives_pause(self):
        p,_=self.build('work((source))',routines=f'ROUTINE work(v:ARRAY OF {self.typename}) BEGIN {self.changed()} PAUSE target=v END work');expected=snapshot(raw(p,'SOURCE'))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(snapshot(raw(p,'SOURCE')),expected);p.resume()
        self.assertEqual(content(cell(p,'TARGET')),99 if self.kind=='path' else None);self.assertEqual(p._state.local_frames,[])

    def test_stop_has_no_private_copyback(self):
        p,_=self.build('work((source))',routines=f'ROUTINE work(v:ARRAY OF {self.typename}) BEGIN {self.changed()} PAUSE END work');expected=snapshot(raw(p,'SOURCE'))
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(snapshot(raw(p,'SOURCE')),expected);self.assertEqual(p._state.local_frames,[])

    def test_retained_handler_keeps_private_collection(self):
        p,_=self.build('work((source)) ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=f'ROUTINE work(v:ARRAY OF {self.typename}) BEGIN CONDITION[1]: WHEN EVENT[1] DO {self.changed()} target=v ENDCONDITION END work');expected=snapshot(raw(p,'SOURCE'));p.run()
        self.assertEqual(snapshot(raw(p,'SOURCE')),expected);self.assertEqual(content(cell(p,'TARGET')),99 if self.kind=='path' else None)

    def test_result_is_an_independent_concrete_array(self):
        p,_=self.build('target=make()',routines=f'ROUTINE make:ARRAY OF {self.typename} BEGIN RETURN source END make');p.run()
        self.assertEqual(content(cell(p,'TARGET')),17);self.assertIsNot(cell(p),cell(p,'TARGET'))

    def test_result_can_be_passed_privately(self):
        p,_=self.build('work(make())',routines=f'ROUTINE make:ARRAY OF {self.typename} BEGIN RETURN source END make ROUTINE work(v:ARRAY OF {self.typename}) BEGIN {self.changed()} target=v END work');expected=snapshot(raw(p,'SOURCE'));p.run()
        self.assertEqual(snapshot(raw(p,'SOURCE')),expected);self.assertEqual(content(cell(p,'TARGET')),99 if self.kind=='path' else None)

    def test_result_can_pause_before_capture_finishes(self):
        p,_=self.build('target=make()',routines=f'ROUTINE make:ARRAY OF {self.typename} BEGIN PAUSE RETURN source END make')
        with self.assertRaises(rt.KarelPause):p.run()
        p.resume();self.assertEqual(content(cell(p,'TARGET')),17)

    def test_failed_result_capture_unwinds_without_publication(self):
        p,_=self.build('target=make()',routines=f'ROUTINE make:ARRAY OF {self.typename} BEGIN RETURN source END make');before=snapshot(raw(p));raw(p,'SOURCE').values[0]=cell(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(snapshot(raw(p)),before);self.assertEqual(p._state.local_frames,[])

    def test_result_snapshot_precedes_later_argument_effect(self):
        p,_=self.build('work(make(),change())',routines=f'ROUTINE make:ARRAY OF {self.typename} BEGIN RETURN source END make ROUTINE change:INTEGER BEGIN {self.changed("source")} RETURN 0 END change ROUTINE work(v:ARRAY OF {self.typename};ignored:INTEGER) BEGIN target=v END work');p.run()
        self.assertEqual(content(cell(p,'TARGET')),17);self.assertEqual(content(cell(p)),99 if self.kind=='path' else None)

    def test_malformed_argument_skips_later_arguments(self):
        p,_=self.build('visits=0 work((source),change())',routines=f'ROUTINE change:INTEGER BEGIN visits=1 RETURN 0 END change ROUTINE work(v:ARRAY OF {self.typename};ignored:INTEGER) BEGIN END work');raw(p,'SOURCE').values[0]=cell(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)

    def test_saved_context_contains_values_not_private_aliases(self):
        p,_=self.build();p.run();config=p._state.execution.to_config()
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)


class PathSourceValueTests(CopyCases,unittest.TestCase):kind='path'
class QueueSourceValueTests(CopyCases,unittest.TestCase):kind='queue'


class CollectionPrefixValueTests(unittest.TestCase):
    def test_path_row_assignment_updates_original_selected_cells(self):
        p,_=row('target[1]=source[2]');untouched=raw(p).values[2:];p.run()
        self.assertEqual(content(raw(p).values[1]),17);self.assertTrue(all(a is b for a,b in zip(untouched,raw(p).values[2:])))

    def test_queue_row_assignment_is_independent(self):
        p,_=prepare('target[1]=source[2]',prefix='',decl='source,target:ARRAY[2,2]OF QUEUE_TYPE entry,status,seq:INTEGER');p.run()
        self.assertEqual(content(raw(p).values[1]),17);self.assertIsNot(raw(p).values[1],raw(p,'SOURCE').values[3])

    def test_prefix_argument_is_private_without_grouping(self):
        p,_=row('work(source[2])',routines='ROUTINE work(v:ARRAY OF route_t) BEGIN v[2][1].value=99 END work');p.run()
        self.assertEqual(content(raw(p,'SOURCE').values[3]),17)

    def test_prefix_return_inherits_selected_row_dimensions(self):
        p,_=row('target[1]=make()',routines='ROUTINE make:ARRAY OF route_t BEGIN RETURN source[2] END make');p.run()
        self.assertEqual(content(raw(p).values[1]),17)

    def test_prefix_source_captured_before_target_selector(self):
        p,_=row('target[pick()]=source[2]',routines='ROUTINE pick:INTEGER BEGIN source[2,2][1].value=99 RETURN 1 END pick');p.run()
        self.assertEqual((content(raw(p).values[1]),content(raw(p,'SOURCE').values[3])),(17,99))

    def test_prefix_capture_checks_unselected_owned_bank(self):
        p,_=row('target[1]=source[2]');raw(p,'SOURCE').values[0]=raw(p,'SOURCE').values[3]
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_three_dimensional_plane_copy_preserves_unselected_planes(self):
        p,_=prepare('target[1]=source[2]',decl='source,target:ARRAY[2,2,2]OF route_t entry,status,visits:INTEGER');p.run()
        self.assertEqual(content(list(collections(raw(p)))[3]),17);self.assertIsNone(content(list(collections(raw(p)))[7]))


class CollectionValueBoundaries(unittest.TestCase):
    def test_path_header_and_old_node_aliases_keep_their_contracts(self):
        p,_=prepare('target=source');target=cell(p,'TARGET');target.append();target.nodes[0].values['VALUE']=88;nodes=target.nodes;header=target.data;alias=rt.field_reference(nodes[0],'VALUE');p.run()
        self.assertIs(target.data,header);self.assertIsNot(target.nodes,nodes);self.assertEqual(alias.raw(),88)

    def test_queue_copy_drops_only_receiver_buffer_links(self):
        p,_=queues('target=source');source=cell(p);target=cell(p,'TARGET');buffer=rt.Array(('ARRAY',3,('INTEGER',)));source.buffer=buffer;target.buffer=buffer;p.run()
        self.assertIs(source.buffer,buffer);self.assertIsNone(target.buffer);self.assertEqual(target.sequence,2)

    def test_partial_path_data_is_copied_without_default_values(self):
        p,_=prepare('target=source');cell(p).nodes[0].values['VALUE']=rt.UNINITIALIZED;p.run()
        self.assertIs(cell(p,'TARGET').nodes[0].values['VALUE'],rt.UNINITIALIZED)

    def test_uninitialized_queue_state_is_a_valid_logical_copy(self):
        p,_=queues('target=source',seed=False);p.run();self.assertFalse(cell(p,'TARGET').initialized)

    def test_queue_entries_and_sequence_must_be_valid(self):
        for sequence,entries in [(0,[(1,7)]),(2,[(2,7),(2,8)]),(2,[(2,7.5)])]:
            p,_=queues('target=source');cell(p).sequence=sequence;cell(p).entries=entries;before=snapshot(raw(p))
            with self.subTest(entries=entries),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(snapshot(raw(p)),before)

    def test_different_collection_kinds_remain_incompatible(self):
        with self.assertRaises(TranslationError):compile_program('paths=queues',decl='paths:ARRAY[2]OF PATH queues:ARRAY[2]OF QUEUE_TYPE')

    def test_different_path_node_schemas_remain_incompatible(self):
        with self.assertRaises(TranslationError):compile_program('b=a',prefix='TYPE n1=STRUCTURE value:INTEGER ENDSTRUCTURE n2=STRUCTURE value:REAL ENDSTRUCTURE p1=PATH NODEDATA=n1 p2=PATH NODEDATA=n2',decl='a:ARRAY[2]OF p1 b:ARRAY[2]OF p2')

    def test_different_outer_named_types_remain_incompatible(self):
        with self.assertRaises(TranslationError):compile_program('b=a',prefix='TYPE a_t=ARRAY[2]OF QUEUE_TYPE b_t=ARRAY[2]OF QUEUE_TYPE',decl='a:a_t b:b_t')

    def test_dimension_reshape_is_not_a_source_copy(self):
        with self.assertRaises(TranslationError):compile_program('b=a',decl='a:ARRAY[2,2]OF QUEUE_TYPE b:ARRAY[4]OF QUEUE_TYPE')

    def test_file_arrays_are_not_logical_values(self):
        for body in ('b=a','work((a))'):
            with self.subTest(body=body),self.assertRaises(TranslationError):compile_program(body,decl='a,b:ARRAY[2]OF FILE',routines='ROUTINE work(v:ARRAY OF FILE) BEGIN END work')

    def test_scalar_queue_source_copy_keeps_generic_copying_closed(self):
        p,_=compile_program('b=a',decl='a,b:QUEUE_TYPE');p.run();value=p._state.values['B']
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.checked(value.spec,value)

    def test_containing_bank_and_snapshot_costs_stay_bounded(self):
        p,_=prepare('target=source');node=cell(p).nodes[0];cell(p).nodes=[deepcopy(node) for _ in range(32767)];before=snapshot(raw(p))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):p.run()
        self.assertEqual(snapshot(raw(p)),before)

    def test_source_snapshot_fails_before_target_index_side_effect(self):
        p,_=row('target[pick()]=source[2]',routines='ROUTINE pick:INTEGER BEGIN visits=1 RETURN 1 END pick');p._state.values['VISITS']=0;raw(p,'SOURCE').values[0]=raw(p,'SOURCE').values[3]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)

    def test_legacy_runtime_source_value_helper_is_closed(self):
        p,_=prepare('');source=raw(p,'SOURCE')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.collection_array_source_value(source.spec,source)

    def test_dynamic_created_copy_and_byname_results_share_owned_storage(self):
        p,_=prepare("CREATE_VAR('CACHE','bank','T','ARRAY OF route_t',0,2,0,0,status) work(BYNAME('CACHE','BANK',entry))",routines='ROUTINE work(v:ARRAY OF route_t) BEGIN v=source END work');p.run()
        rows=p._state.execution.to_config()['variables'];created=next(r for r in rows if r['path']=='BANK');self.assertEqual(created['value'][1]['nodes'][0]['VALUE'],17)

    def test_linked_source_result_and_grouped_argument_use_same_policy(self):
        prefix='TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        sources={'main':f"PROGRAM MAIN {prefix} VAR a,b:ARRAY[2]OF route_t s:INTEGER ROUTINE work(v:ARRAY OF route_t):ARRAY OF route_t FROM LIB BEGIN APPEND_NODE(a[2],s) a[2][1].value=17 b=work((a)) END MAIN",'lib':f"PROGRAM LIB {prefix} ROUTINE work(v:ARRAY OF route_t):ARRAY OF route_t BEGIN v[2][1].value=99 RETURN v END work BEGIN END LIB"}
        project=translate_project(sources).instantiate();state=project.run('MAIN')
        self.assertEqual((state['MAIN']['values']['A'][1]['nodes'][0]['VALUE'],state['MAIN']['values']['B'][1]['nodes'][0]['VALUE']),(17,99))


class CollectionValueSchemaTests(unittest.TestCase):
    def test_declared_source_schema_cannot_be_relabelled(self):
        p,_=prepare('target=source');value=raw(p,'SOURCE');value.spec=(*value.spec,'FOREIGN');before=snapshot(raw(p))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared source'):p.run()
        self.assertEqual(snapshot(raw(p)),before)

    def test_declared_receiver_schema_cannot_be_relabelled(self):
        p,_=prepare('target=source');value=raw(p);value.spec=(*value.spec,'FOREIGN');before=snapshot(value)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared source'):p.run()
        self.assertEqual(snapshot(value),before)

    def test_generic_receiver_checks_actual_named_identity(self):
        p,_=prepare('work(target,source)',prefix=PREFIX+' TYPE a_t=ARRAY[2]OF route_t b_t=ARRAY[2]OF route_t',decl='source:a_t target:b_t',routines='ROUTINE work(dst:ARRAY OF route_t;src:ARRAY OF route_t) BEGIN dst=src END work');before=snapshot(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(snapshot(raw(p)),before)

    def test_named_result_keeps_exact_named_schema(self):
        for kind in ('route_t','QUEUE_TYPE'):
            prefix=PREFIX+' TYPE bank_t=ARRAY[2]OF route_t' if kind=='route_t' else 'TYPE bank_t=ARRAY[2]OF QUEUE_TYPE'
            p,_=prepare('target=make()',prefix=prefix,decl='source,target:bank_t',routines='ROUTINE make:bank_t BEGIN RETURN source END make');p.run()
            self.assertEqual(content(cell(p,'TARGET')),17);self.assertEqual(raw(p).spec,raw(p,'SOURCE').spec)

    def test_anonymous_result_canonicalizes_declared_outer_schema(self):
        p,_=prepare('target=make()',prefix=PREFIX+' TYPE bank_t=ARRAY[2]OF route_t',decl='source:bank_t target:ARRAY[2]OF route_t',routines='ROUTINE make:ARRAY[2]OF route_t BEGIN RETURN source END make');p.run()
        self.assertIsNone(rt.array_identity(raw(p).spec));self.assertEqual(content(cell(p,'TARGET')),17)

    def test_runtime_result_size_mismatch_preserves_receiver(self):
        p,_=prepare('target=make()',decl='source:ARRAY[3]OF route_t target:ARRAY[2]OF route_t',routines='ROUTINE make:ARRAY OF route_t BEGIN RETURN source END make');before=snapshot(raw(p))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(snapshot(raw(p)),before)

    def test_named_inner_component_result_preserves_owned_cells(self):
        p,_=prepare('target=make()',prefix=PREFIX+' TYPE row_t=ARRAY[2]OF route_t',decl='source,target:ARRAY[2]OF row_t',routines='ROUTINE make:ARRAY OF row_t BEGIN RETURN source END make');old=list(collections(raw(p)));p.run()
        self.assertTrue(all(a is b for a,b in zip(old,collections(raw(p)))));self.assertEqual(content(old[-1]),17)

    def test_raw_external_callback_returns_detached_collection_bank(self):
        ctx=rt.ExecutionContext();p,_=prepare('target=make()',routines='ROUTINE make:ARRAY OF route_t FROM FOREIGN',context=ctx);source=raw(p,'SOURCE');before=snapshot(source);ctx.externals['FOREIGN','MAKE']=lambda:source
        p.run();self.assertEqual(snapshot(source),before);self.assertEqual(snapshot(raw(p)),before)
        self.assertIsNot(raw(p).values[0],source.values[0])

    def test_direct_path_result_spelling_has_default_node_schema(self):
        p,_=compile_program('b=make()',decl='a,b:ARRAY[2]OF PATH',routines='ROUTINE make:ARRAY OF PATH BEGIN RETURN a END make');state=p.run()
        self.assertEqual(state['B'],[{'nodes':[],'data':None},{'nodes':[],'data':None}])

    def test_returned_path_node_can_be_read_as_a_value(self):
        p,_=prepare('visits=make()[2][1].value',routines='ROUTINE make:ARRAY OF route_t BEGIN RETURN source END make');self.assertEqual(p.run()['VISITS'],17)

    def test_unknown_byte_and_missing_path_leaves_survive_source_copy(self):
        p,_=compile_program('APPEND_NODE(a[1],s) b=a',prefix='TYPE node_t=STRUCTURE b:BYTE n:INTEGER ENDSTRUCTURE path_t=PATH NODEDATA=node_t',decl='a,b:ARRAY[1]OF path_t s:INTEGER');state=p.run()
        self.assertEqual(state['B'][0]['nodes'][0],{'B':{'unknown_byte':True},'N':{'uninitialized':True}})

    def test_shared_headers_are_rejected_before_copying(self):
        p,_=prepare('target=source');raw(p,'SOURCE').values[0].data=cell(p).data
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_byname_prefix_still_borrows_original_storage(self):
        p,_=row("work(BYNAME('','SOURCE[2]',entry))",routines='ROUTINE work(v:ARRAY OF route_t) BEGIN v[2][1].value=99 END work');p.run()
        self.assertEqual(content(raw(p,'SOURCE').values[3]),99)

    def test_linked_queue_result_is_independent(self):
        sources={'main':"PROGRAM MAIN VAR a,b:ARRAY[2]OF QUEUE_TYPE buffer:ARRAY[3]OF INTEGER seq,s:INTEGER ROUTINE work(v:ARRAY OF QUEUE_TYPE):ARRAY OF QUEUE_TYPE FROM LIB BEGIN INIT_QUEUE(a[2]) APPEND_QUEUE(17,a[2],buffer,seq,s) b=work((a)) END MAIN",'lib':"PROGRAM LIB ROUTINE work(v:ARRAY OF QUEUE_TYPE):ARRAY OF QUEUE_TYPE BEGIN RETURN v END work BEGIN END LIB"}
        project=translate_project(sources).instantiate();project.run('MAIN');values=project.programs['MAIN']._state.values
        self.assertIsNot(values['A'].values[1],values['B'].values[1]);self.assertEqual(values['B'].values[1].entries,[(1,17)]);self.assertIsNone(values['B'].values[1].buffer)


class CollectionValuePolicyTests(unittest.TestCase):
    def policy(self):return prepare('target=source')[1].report['collection_array_source_policy']
    def test_policy_records_value_and_borrowed_ownership(self):
        policy=self.policy();self.assertIn('private',policy['arguments']);self.assertIn('BYNAME',policy['exact']);self.assertIn('existing',policy['publication'])
    def test_policy_records_limits_and_persistence(self):
        policy=self.policy();self.assertIn('32767',policy['bounds']);self.assertIn('queue buffer',policy['persistence']);self.assertFalse(policy['controller_validated'])
    def test_policy_links_current_guide(self):
        self.assertEqual(self.policy()['guide'],'docs/collection-source-values.md')


if __name__=='__main__':unittest.main()
