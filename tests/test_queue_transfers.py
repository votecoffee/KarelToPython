"""Authored logical queue transfers, ownership boundaries and copy failure guards."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.extended import matches
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source as module_source


DECL='entry,status,n,seq,count: INTEGER source,target: QUEUE_TYPE a,b,view: ARRAY[3] OF INTEGER'
SEED='INIT_QUEUE(source) APPEND_QUEUE(7,source,a,seq,status) APPEND_QUEUE(9,source,a,seq,status) '


def call(action='GET_VAR',status='status',value=None,path=None):
    value=value or ('target' if action=='GET_VAR' else 'source')
    path=path or ('SOURCE' if action=='GET_VAR' else 'TARGET')
    return f"{action}(entry,'','{path}',{value},{status})"


def queue(entries=((2,70),(1,50)),sequence=3,initialized=True):
    value=rt.QueueValue();value.entries=list(entries);value.sequence=sequence;value.initialized=initialized
    return value


def prepared(body=None,**options):
    program,result=compile_program(body or call(),decl=DECL,**options)
    program._state.values['SOURCE']=queue()
    program._state.values['TARGET']=queue(((1,90),),1)
    return program,result


class QueueLogicalCopyTests(unittest.TestCase):
    def test_get_and_set_copy_order_counter_and_independent_entries(self):
        for action in ('GET_VAR','SET_VAR'):
            with self.subTest(action=action):
                program,_=prepared(call(action));old=program._state.values['TARGET'];entries=old.entries
                state=program.run();copied=program._state.values['TARGET'];original=program._state.values['SOURCE']
                self.assertEqual((state['STATUS'],copied.sequence,copied.entries),(0,3,[(2,70),(1,50)]))
                self.assertIs(copied,old);self.assertIsNot(copied.entries,entries)
                self.assertIsNot(copied.entries,original.entries)
                copied.entries.pop();self.assertEqual(original.entries,[(2,70),(1,50)])

    def test_distinct_host_queues_with_shared_old_entries_are_detached(self):
        program,_=prepared();original=program._state.values['SOURCE'];target=program._state.values['TARGET']
        target.entries=original.entries;target.sequence=original.sequence
        program.run();self.assertIsNot(target.entries,original.entries)
        target.entries.pop();self.assertEqual(original.entries,[(2,70),(1,50)])

    def test_initialized_empty_queue_preserves_sequence_gaps(self):
        program,_=prepared(call()+' APPEND_QUEUE(11,target,b,seq,status)')
        program._state.values['SOURCE']=queue((),7)
        self.assertEqual(program.run()['SEQ'],8);self.assertEqual(program._state.values['SOURCE'].sequence,7)

    def test_transfer_does_not_sync_old_or_new_arrays(self):
        program,_=compile_program(SEED+'INIT_QUEUE(target) APPEND_QUEUE(99,target,b,seq,status) '+call(),decl=DECL)
        state=program.run()
        self.assertEqual((state['A'],state['B']),([7,9,0],[99,0,0]))
        self.assertIsNone(program._state.values['TARGET'].buffer)
        self.assertIs(program._state.values['SOURCE'].buffer,program._state.values['A'])

    def test_next_operation_binds_a_different_larger_array(self):
        body=SEED+'INIT_QUEUE(target) APPEND_QUEUE(99,target,small,seq,status) '+call()+' GET_QUEUE(target,b,n,seq,status)'
        program,_=compile_program(body,decl=DECL+' small: ARRAY[1] OF INTEGER')
        state=program.run();self.assertEqual((state['N'],state['SEQ'],state['B'],state['SMALL']),(7,1,[9,0,0],[99]))
        self.assertIs(program._state.values['TARGET'].buffer,program._state.values['B'])

    def test_next_operation_rejects_too_small_array_before_consumption(self):
        program,_=compile_program(SEED+call()+' GET_QUEUE(target,small,n,seq,status)',decl=DECL+' small: ARRAY[1] OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'too small'): program.run()
        self.assertEqual(program._state.values['TARGET'].entries,[(1,7),(2,9)])
        self.assertIsNone(program._state.values['TARGET'].buffer)

    def test_same_buffer_guard_resumes_after_explicit_binding(self):
        program,_=compile_program(SEED+call()+' GET_QUEUE(target,b,n,seq,status) GET_QUEUE(target,view,n,seq,status)',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'original backing ARRAY'): program.run()
        self.assertEqual(program._state.values['TARGET'].entries,[(2,9)])

    def test_self_copy_keeps_queue_identity_and_releases_binding(self):
        program,_=compile_program(SEED+call(value='source'),decl=DECL)
        original=program._state.values['SOURCE'];program.run()
        self.assertIs(program._state.values['SOURCE'],original);self.assertIsNone(original.buffer)
        self.assertEqual(original.entries,[(1,7),(2,9)])

    def test_set_self_copy_is_independent_snapshot(self):
        program,_=compile_program(SEED+call('SET_VAR',path='SOURCE'),decl=DECL)
        program.run();self.assertEqual(program._state.values['SOURCE'].sequence,2)
        self.assertIsNone(program._state.values['SOURCE'].buffer)

    def test_grouped_set_source_is_supported(self):
        state=run(SEED+call('SET_VAR',value='((source))'),decl=DECL)
        self.assertEqual(state['TARGET']['entries'],[[1,7],[2,9]])

    def test_initialized_false_copies_missing_logical_state(self):
        for action in ('GET_VAR','SET_VAR'):
            with self.subTest(action=action):
                program,_=prepared(call(action));program._state.values['SOURCE']=rt.QueueValue()
                state=program.run();target=program._state.values['TARGET']
                self.assertEqual((state['STATUS'],target.initialized,target.entries,target.sequence),(12311,False,[],0))
                self.assertIsNone(target.buffer);self.assertGreater(state['ENTRY'],0)

    def test_uninitialized_copy_requires_init_before_queue_operations(self):
        program,_=compile_program(call()+' APPEND_QUEUE(1,target,b,seq,status)',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'INIT_QUEUE'): program.run()
        self.assertEqual(program._state.values['STATUS'],12311)

    def test_whole_missing_source_normalizes_to_valid_uninitialized_queue(self):
        program,_=prepared(call('SET_VAR'));program._state.values['SOURCE']=rt.UNINITIALIZED
        self.assertEqual(program.run()['STATUS'],12311)
        target=program._state.values['TARGET'];self.assertIsInstance(target,rt.QueueValue);self.assertFalse(target.initialized)

    def test_whole_missing_receiver_is_materialized(self):
        program,_=prepared();program._state.values['TARGET']=rt.UNINITIALIZED
        self.assertEqual(program.run()['STATUS'],0)
        self.assertEqual(program._state.values['TARGET'].entries,[(2,70),(1,50)])

    def test_copy_then_init_deliberately_resets_transferred_counter(self):
        program,_=prepared(call()+' INIT_QUEUE(target) APPEND_QUEUE(8,target,b,seq,status)')
        self.assertEqual(program.run()['SEQ'],1);self.assertEqual(program._state.values['TARGET'].entries,[(1,8)])

    def test_copy_queue_query_uses_transferred_fifo_order(self):
        program,_=prepared(call()+' COPY_QUEUE(target,b,0,0,view,count,status)')
        state=program.run();self.assertEqual((state['COUNT'],state['VIEW']),(2,[70,50,{'uninitialized':True}]))


class QueueTransferGuardTests(unittest.TestCase):
    def test_queue_to_scalar_mismatch_writes_status_only(self):
        program,_=prepared('entry=99 n=42 '+call(value='n'))
        state=program.run();self.assertEqual((state['ENTRY'],state['N'],state['STATUS']),(99,42,3))
        self.assertEqual(program._state.execution.entries,{})

    def test_scalar_to_queue_mismatch_preserves_receiver(self):
        for action in ('GET_VAR','SET_VAR'):
            with self.subTest(action=action):
                body='entry=99 n=42 '+(call(path='N') if action=='GET_VAR' else call(action,value='n'))
                program,_=prepared(body);state=program.run()
                self.assertEqual((state['ENTRY'],state['STATUS']),(99,3));self.assertEqual(state['TARGET']['entries'],[[1,90]])

    def test_missing_data_cannot_clear_queue_of_different_type(self):
        program,_=prepared('entry=99 '+call('SET_VAR',value='n'));state=program.run()
        self.assertEqual((state['STATUS'],state['ENTRY']),(3,99));self.assertEqual(state['TARGET']['entries'],[[1,90]])

    def test_missing_path_preserves_queue_and_entry(self):
        program,_=prepared('entry=99 '+call(path='ABSENT'));state=program.run()
        self.assertEqual((state['STATUS'],state['ENTRY'],state['TARGET']['entries']),(1,99,[[1,90]]))

    def test_queue_output_requires_disjoint_entry_and_status(self):
        program,_=prepared(call(status='entry'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): program.run()
        self.assertEqual(program._state.values['TARGET'].entries,[(1,90)])

    def test_dynamic_scalar_target_still_cannot_overlap_cache_output(self):
        program,_=prepared(call('SET_VAR',path='ENTRY'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): program.run()

    def test_other_any_interfaces_do_not_accept_queue_resources(self):
        self.assertTrue(matches(('QUEUE_TYPE',),'VARIABLE'));self.assertFalse(matches(('QUEUE_TYPE',),'ANY'))

    def test_embedded_queue_is_not_a_transferable_array(self):
        value=rt.Array(('ARRAY',1,('QUEUE_TYPE',)))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without resources'): rt.variable_value(value.spec,value)

    def test_file_and_path_targets_remain_excluded_at_runtime(self):
        for kind in ('FILE','PATH'):
            with self.subTest(kind=kind):
                program,_=compile_program(SEED+call('SET_VAR',path='RESOURCE'),decl=DECL+' resource: '+kind)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'without resources'): program.run()

    def test_ordinary_queue_assignment_remains_rejected(self):
        program,_=compile_program('target=source',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cannot be copied'): program.run()

    def test_queue_uninit_query_remains_rejected(self):
        with self.assertRaises(TranslationError): compile_program('flag=UNINIT(source)',decl=DECL+' flag: BOOLEAN')

    def test_active_for_counter_indirect_write_guard_remains(self):
        with self.assertRaises(TranslationError): compile_program('FOR n=1 TO 2 DO '+call('SET_VAR')+' ENDFOR',decl=DECL)

    def test_bad_source_queue_state_preserves_all_outputs_and_receiver(self):
        changes=(('initialized',1),('sequence',-1),('sequence',True),('sequence',2147483647),
                 ('entries',[(1,7),(1,8)]),('entries',[(4,7)]),('entries',[(1,True)]),
                 ('entries',[(1,float('nan'))]),('entries',[(1,2147483647)]),('entries',[(1,7,8)]),
                 ('entries',((1,7),)),('entries',[(1,7)]*32768),('spec',('INTEGER',)))
        for field,value in changes:
            with self.subTest(field=field,value=str(value)[:24]):
                program,_=prepared('entry=99 status=88 '+call('SET_VAR'))
                setattr(program._state.values['SOURCE'],field,value)
                with self.assertRaises(rt.KarelRuntimeError): program.run()
                self.assertEqual((program._state.values['ENTRY'],program._state.values['STATUS']),(99,88))
                self.assertEqual(program._state.values['TARGET'].entries,[(1,90)])
                self.assertEqual(program._state.execution.entries,{})

    def test_bad_receiver_queue_state_is_not_silently_overwritten(self):
        program,_=prepared('entry=99 status=88 '+call());program._state.values['TARGET'].entries=[(1,7),(1,8)]
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program._state.values['ENTRY'],program._state.values['STATUS']),(99,88))
        self.assertEqual(program._state.values['TARGET'].entries,[(1,7),(1,8)])

    def test_bad_source_buffer_shape_is_checked_before_copy(self):
        program,_=prepared();original=program._state.values['SOURCE']
        original.buffer=rt.Array(('ARRAY',3,('INTEGER',)));original.buffer.shape=(1,)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.values['TARGET'].entries,[(1,90)])

    def test_insufficient_source_buffer_is_not_copied(self):
        program,_=prepared();program._state.values['SOURCE'].buffer=rt.Array(('ARRAY',1,('INTEGER',)))
        with self.assertRaises(rt.KarelRuntimeError): program.run()

    def test_uninitialized_source_cannot_hide_entries_or_binding(self):
        for member in ('entries','buffer','sequence'):
            with self.subTest(member=member):
                program,_=prepared();q=rt.QueueValue()
                setattr(q,member,[(1,7)] if member=='entries' else rt.Array(('ARRAY',3,('INTEGER',))) if member=='buffer' else 1)
                program._state.values['SOURCE']=q
                with self.assertRaises(rt.KarelRuntimeError): program.run()


class QueueTransferOrderingAndIntegrationTests(unittest.TestCase):
    def test_set_source_snapshot_precedes_status_selector_changes(self):
        routines='ROUTINE at: INTEGER BEGIN APPEND_QUEUE(11,source,a,seq,status) RETURN 1 END at'
        program,_=compile_program(SEED+call('SET_VAR',status='codes[at()]'),decl=DECL+' codes: ARRAY[1] OF INTEGER',routines=routines)
        state=program.run();self.assertEqual(state['SOURCE']['entries'],[[1,7],[2,9],[3,11]])
        self.assertEqual(state['TARGET']['entries'],[[1,7],[2,9]]);self.assertEqual(state['CODES'],[0])

    def test_get_source_snapshot_follows_status_selector_changes(self):
        routines='ROUTINE at: INTEGER BEGIN APPEND_QUEUE(11,source,a,seq,status) RETURN 1 END at'
        state=run(SEED+call(status='codes[at()]'),decl=DECL+' codes: ARRAY[1] OF INTEGER',routines=routines)
        self.assertEqual(state['TARGET']['entries'],[[1,7],[2,9],[3,11]])

    def test_bad_set_source_skips_later_selector_effects(self):
        routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN 1 END at'
        program,_=compile_program('n=0 '+call('SET_VAR',status='codes[at()]'),decl=DECL+' codes: ARRAY[1] OF INTEGER',routines=routines)
        program._state.values['SOURCE']=queue(((1,7),(1,8)))
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.values['N'],0)

    def test_bad_receiver_retains_prior_selector_effects(self):
        routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN 1 END at'
        program,_=compile_program('n=0 '+call('SET_VAR',status='codes[at()]'),decl=DECL+' codes: ARRAY[1] OF INTEGER',routines=routines)
        program._state.values['SOURCE']=queue();program._state.values['TARGET']=queue(((1,7),(1,8)))
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program._state.values['N'],1)

    def test_typed_foreign_binding_uses_independent_snapshot(self):
        ctx=rt.ExecutionContext();original=queue();ref=ctx.variables.define('LIB','Q',('QUEUE_TYPE',),original)
        original.entries.clear()
        program,_=compile_program("GET_VAR(entry,'LIB','Q',target,status)",decl=DECL,context=ctx)
        state=program.run();self.assertEqual(state['TARGET']['entries'],[[2,70],[1,50]])
        self.assertIsNot(program._state.values['TARGET'],ref.raw())

    def test_define_discards_source_buffer_identity(self):
        original=queue();original.buffer=rt.Array(('ARRAY',3,('INTEGER',)))
        ref=rt.VariableStore().define('LIB','Q',('QUEUE_TYPE',),original)
        self.assertIsNone(ref.raw().buffer);self.assertIsNotNone(original.buffer)

    def test_linked_queue_reference_formal_transfers_in_executing_module(self):
        main=module_source('MAIN','INIT_QUEUE(q) APPEND_QUEUE(7,q,a,seq,status) put(q)',decl='q: QUEUE_TYPE a: ARRAY[2] OF INTEGER seq,status: INTEGER',routines='ROUTINE put(value: QUEUE_TYPE) FROM LIB')
        lib=module_source('LIB','',decl=DECL,routines="ROUTINE put(value: QUEUE_TYPE) BEGIN SET_VAR(entry,'','TARGET',value,status) END put")
        state=translate_project({'main':main,'lib':lib}).instantiate().run('MAIN')
        self.assertEqual(state['LIB']['values']['TARGET']['entries'],[[1,7]])

    def test_cooperative_program_can_transfer_queues(self):
        program,_=compile_program(SEED+call(),decl=DECL,cooperative=True)
        self.assertEqual(program.run()['TARGET']['entries'],[[1,7],[2,9]])

    def test_transferred_state_survives_typed_context_reload(self):
        program,result=prepared();expected=program.run()
        ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(program._state.execution.to_config())))
        namespace={'__name__':'queue_reload'};exec(result.python_source,namespace)
        other=namespace['Program'](context=ctx);self.assertEqual(other.snapshot(),expected)
        self.assertEqual(other._state.values['TARGET'].sequence,3);self.assertIsNone(other._state.values['TARGET'].buffer)

    def test_service_records_and_report_are_value_free(self):
        program,result=prepared();program.run()
        self.assertEqual(program.service_requests,({'operation':'GET_VAR','line':6,'outcome':'completed'},))
        self.assertFalse(result.report['queue_transfer_policy']['controller_validated'])
        self.assertEqual(result.report['queue_transfer_policy']['guide'],'docs/queue-transfers.md')

    def test_cache_id_reused_for_initialized_and_uninitialized_copies(self):
        body=call()+' n=entry INIT_QUEUE(source) '+call()
        state=run(body,decl=DECL);self.assertEqual((state['ENTRY'],state['N'],state['STATUS']),(1,1,0))


if __name__=='__main__': unittest.main()
