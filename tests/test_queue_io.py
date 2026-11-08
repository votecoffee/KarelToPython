"""Authored offline queue entry I/O, staged publication and transport boundaries."""
import json
import struct
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_file_cancellation import serial,pending,OPEN,FINISH

DECL='q,r:QUEUE_TYPE b,c:ARRAY[3]OF INTEGER n,s,visits:INTEGER f:FILE'
SEED='INIT_QUEUE(q) APPEND_QUEUE(17,q,b,n,s) APPEND_QUEUE(9,q,b,n,s) '

def build(body='',*,seed=True,decl=DECL,values=None,**options):
    if values is not None:options['read']=lambda request:list(values)
    return compile_program((SEED if seed else '')+body,decl=decl,**options)
def queue(p,name='Q'):return p._state.values[name]
def texts(p):return [item['text'] for item in p.write_requests]
def entries(p,name='Q'):return queue(p,name).entries

def capture(count=2,buffer=False):
    p,_=build('');p.run();q=queue(p);q.entries=[(i+1,17+i) for i in range(count)];q.sequence=count
    if not buffer:q.buffer=None
    with rt._numeric_scope('pythonic'):fields=rt.capture_aggregate_read_target(p._state.reference('Q'),[],41)
    return p,q,[field for field,_ in fields]

class QueueWriteTests(unittest.TestCase):
    def test_values_only_in_fifo_order(self):
        p,_=build('WRITE(q)');p.run();self.assertEqual(texts(p),[' 17 9'])
    def test_sparse_ids_and_sequence_do_not_appear(self):
        p,_=build('WRITE(q)',seed=False);q=queue(p);q.initialized=True;q.sequence=99;q.entries=[(7,17),(3,9)];p.run();self.assertEqual(texts(p),[' 17 9'])
    def test_formats_apply_to_each_integer(self):
        p,_=build('WRITE(q::4::0,CR)');p.run();self.assertEqual(texts(p),['  17   9\n'])
    def test_empty_initialized_queue_has_empty_output(self):
        p,_=build('INIT_QUEUE(q) WRITE(q)',seed=False);p.run();self.assertEqual(texts(p),[''])
    def test_empty_queue_with_scalar_and_cr(self):
        p,_=build("INIT_QUEUE(q) WRITE('a',q,CR)",seed=False);p.run();self.assertEqual(texts(p),['a\n'])
    def test_empty_formatted_queue_rejects(self):
        p,_=build('INIT_QUEUE(q) WRITE(q::4)',seed=False)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Empty PATH/queue'):p.run()
    def test_uninitialized_output_rejects_before_format(self):
        p,_=build('visits=0 WRITE(q::width())',seed=False,routines='ROUTINE width:INTEGER BEGIN visits=1 RETURN 4 END width')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'INIT_QUEUE'):p.run()
        self.assertEqual((p.snapshot()['VISITS'],texts(p)),(0,[]))
    def test_format_effect_does_not_change_captured_values(self):
        p,_=build('WRITE(q::width())',routines='ROUTINE width:INTEGER BEGIN INIT_QUEUE(q) RETURN 4 END width');p.run();self.assertEqual(texts(p),['  17   9']);self.assertEqual(entries(p),[])
    def test_grouped_and_computed_output(self):
        p,_=build('WRITE((q),copyq())',routines='ROUTINE copyq:QUEUE_TYPE BEGIN RETURN q END copyq');p.run();self.assertEqual(texts(p),[' 17 9 17 9'])
    def test_binary_output_is_integer_stream(self):
        files=rt.MemoryFiles();p,_=build("OPEN FILE f('WB','out') WRITE f(q) CLOSE FILE f",context=rt.ExecutionContext(files=files));p.run();self.assertEqual(bytes(files.files['out']),struct.pack('<ii',17,9))
    def test_empty_output_still_requires_open_file(self):
        p,_=build('INIT_QUEUE(q) WRITE f(q)',seed=False,context=rt.ExecutionContext(files=rt.MemoryFiles()))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not open'):p.run()
    def test_report_records_entry_order_and_scope(self):
        _,r=build('WRITE(q)');self.assertEqual(r.report['queue_io_policy']['guide'],'docs/queue-io.md');self.assertFalse(r.report['queue_io_policy']['controller_validated']);self.assertIn('QUEUE-entry-order',str(r.report['writes']))

class QueueReadTests(unittest.TestCase):
    def test_input_replaces_values_and_retains_ids(self):
        p,_=build('READ(q)',values=[42,43]);p.run();self.assertEqual(entries(p),[(1,42),(2,43)]);self.assertEqual(queue(p).sequence,2)
    def test_old_buffer_is_detached_and_unchanged(self):
        p,_=build('READ(q)',values=[42,43]);p.run();self.assertIsNone(queue(p).buffer);self.assertEqual(p.snapshot()['B'],[17,9,0])
    def test_input_retains_queue_and_entry_list_identity(self):
        p,_=build('READ(q)',seed=False,values=[42]);q=queue(p);q.initialized=True;q.sequence=7;q.entries=[(3,17)];before=q.entries;p.run();self.assertIs(queue(p),q);self.assertIs(q.entries,before);self.assertEqual((q.sequence,q.entries),(7,[(3,42)]))
    def test_next_queue_operation_rebinds_supplied_buffer(self):
        p,_=build('READ(q) GET_QUEUE(q,c,visits,n,s)',values=[42,43]);v=p.run();self.assertEqual((v['VISITS'],v['N'],v['S'],v['B'],v['C']),(42,1,0,[17,9,0],[43,0,0]));self.assertIs(queue(p).buffer,p._state.values['C'])
    def test_empty_input_rejects_before_callback(self):
        seen=[];p,_=build('INIT_QUEUE(q) READ(q)',seed=False,read=lambda req:seen.append(req))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'existing initialized'):p.run()
        self.assertEqual(seen,[])
    def test_uninitialized_input_rejects_before_callback(self):
        seen=[];p,_=build('READ(q)',seed=False,read=lambda req:seen.append(req))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'INIT_QUEUE'):p.run()
        self.assertEqual(seen,[])
    def test_bad_last_value_is_atomic(self):
        p,_=build('n=77 READ(n,q)',values=[99,42,True])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],entries(p),p.snapshot()['B']),(77,[(1,17),(2,9)],[17,9,0]));self.assertIsNotNone(queue(p).buffer)
    def test_wrong_response_count_is_atomic(self):
        for values in ([42],[42,43,44]):
            p,_=build('READ(q)',values=values)
            with self.subTest(values=values),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(entries(p),[(1,17),(2,9)])
    def test_cr_offsets_follow_expanded_entries(self):
        p,_=build('READ(q,CR,n)',values=[42,43,99]);self.assertEqual(p.run()['N'],99);self.assertEqual(p.read_requests[0]['line_breaks'],[2])
    def test_format_evaluates_once(self):
        p,_=build('visits=0 READ(q::width())',values=[42,43],routines='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 4 END width');self.assertEqual(p.run()['VISITS'],1)
    def test_format_reinitialization_rejects_before_callback(self):
        seen=[];p,_=build('READ(q::width())',read=lambda req:seen.append(req),routines='ROUTINE width:INTEGER BEGIN INIT_QUEUE(q) RETURN 0 END width')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((entries(p),seen),([],[]))
    def test_callback_queue_mutation_prevents_other_publication(self):
        def read(req):queue(p).entries[0]=(1,88);return [99,42,43]
        p,_=build('n=77 READ(n,q)',read=read)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],entries(p)),(77,[(1,88),(2,9)]))
    def test_read_can_include_former_backing_cells(self):
        p,_=build('READ(q,b[1])',values=[42,43,99]);self.assertEqual(p.run()['B'],[99,9,0]);self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_read_does_not_implicitly_write_for_counter(self):
        p,_=build('FOR b[1]=1 TO 2 DO READ(q) ENDFOR',values=[42,43]);v=p.run();self.assertEqual(v['B'],[{'uninitialized':True},9,0]);self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_borrowed_formal_reads_caller(self):
        p,_=build('fill(q)',values=[42,43],routines='ROUTINE fill(v:QUEUE_TYPE) BEGIN READ(v) END fill');p.run();self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_private_formal_reads_copy(self):
        p,_=build('fill((q))',values=[42,43],routines='ROUTINE fill(v:QUEUE_TYPE) BEGIN READ(v) r=v END fill');p.run();self.assertEqual(entries(p),[(1,17),(2,9)]);self.assertEqual(entries(p,'R'),[(1,42),(2,43)])
    def test_byname_formal_reads_original(self):
        p,_=build("fill(BYNAME('','Q',s))",values=[42,43],routines='ROUTINE fill(v:QUEUE_TYPE) BEGIN READ(v) END fill');p.run();self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_dispatcher_and_cooperative_match(self):
        for label,coop in (('',False),('start:: ',False),('',True)):
            p,_=build(label+'READ(q)',values=[42,43],cooperative=coop);p.run();self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_text_input(self):
        p,_=build('READ(q)',read=rt.TextInput('42 43'));p.run();self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_text_bad_token_rolls_back_cursor(self):
        adapter=rt.TextInput('42\r\nbad');p,_=build('READ(q)',read=adapter)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(entries(p),[(1,17),(2,9)]);self.assertEqual(adapter.position,{'line':1,'column':1,'eof':False})
        self.assertEqual(adapter.offset,0)
    def test_binary_roundtrip(self):
        body="INIT_QUEUE(r) APPEND_QUEUE(0,r,c,n,s) APPEND_QUEUE(0,r,c,n,s) OPEN FILE f('WB','out') WRITE f(q) CLOSE FILE f OPEN FILE f('RB','out') READ f(r) CLOSE FILE f"
        p,_=build(body,context=rt.ExecutionContext(files=rt.MemoryFiles()));p.run();self.assertEqual(entries(p,'R'),entries(p));self.assertEqual(p.snapshot()['C'],[0,0,0]);self.assertIsNone(queue(p,'R').buffer)
    def test_truncated_binary_restores_cursor_and_queue(self):
        p,_=build("OPEN FILE f('RB','in') READ f(q)",context=rt.ExecutionContext(files=rt.MemoryFiles({'in':struct.pack('<i',42)})))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p._state.values['F'].position,entries(p)),(0,[(1,17),(2,9)]));self.assertIsNotNone(queue(p).buffer)
    def test_fixed_width_text_file(self):
        files=rt.MemoryFiles({'in':'  42  43'});p,_=build("OPEN FILE f('RO','in') READ f(q::4) CLOSE FILE f",context=rt.ExecutionContext(files=files));p.run();self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_saved_context_retains_logical_entries(self):
        p,_=build('READ(q)',values=[42,43]);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved);self.assertNotIn('_QueueRead',json.dumps(saved))

BANK_DECL='bank:ARRAY[2,2]OF QUEUE_TYPE a,b,c,d:ARRAY[3]OF INTEGER n,s:INTEGER'
BANK_SEED='INIT_QUEUE(bank[1,1]) INIT_QUEUE(bank[1,2]) INIT_QUEUE(bank[2,1]) INIT_QUEUE(bank[2,2]) APPEND_QUEUE(17,bank[1,2],b,n,s) APPEND_QUEUE(9,bank[2,1],c,n,s) '
def bank(body,**options):return compile_program(BANK_SEED+body,decl=BANK_DECL,**options)

class QueueBankTests(unittest.TestCase):
    def test_row_major_output_skips_empty_cells(self):
        p,_=bank('WRITE(bank)');p.run();self.assertEqual(texts(p),[' 17 9'])
    def test_input_skips_empty_cells(self):
        p,_=bank('READ(bank)',read=lambda req:[42,43]);v=p.run()['BANK'];self.assertEqual([[q['entries'] for q in row] for row in v],[[[],[[1,42]]],[[[1,43]],[]]]);self.assertEqual(p.snapshot()['B'],[17,0,0])
    def test_live_row_input(self):
        p,_=bank('READ(bank[2])',read=lambda req:[42]);v=p.run()['BANK'];self.assertEqual(v[0][1]['entries'],[[1,17]]);self.assertEqual(v[1][0]['entries'],[[1,42]])
    def test_row_output(self):
        p,_=bank('WRITE(bank[1])');p.run();self.assertEqual(texts(p),[' 17'])
    def test_uninitialized_later_cell_prevents_input(self):
        seen=[];p,_=compile_program('INIT_QUEUE(bank[1]) READ(bank)',decl='bank:ARRAY[2]OF QUEUE_TYPE',read=lambda req:seen.append(req))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(seen,[])
    def test_duplicate_queue_destinations_reject_before_callback(self):
        seen=[];p,_=build('READ(q,q)',read=lambda req:seen.append(req))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'disjoint'):p.run()
        self.assertEqual(seen,[])
    def test_bank_and_selected_cell_overlap_reject(self):
        p,_=bank('READ(bank,bank[1,2])',read=lambda req:[42,43,44])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'disjoint'):p.run()
    def test_named_nested_components(self):
        prefix='TYPE row_t=ARRAY[2]OF QUEUE_TYPE'
        p,_=compile_program('INIT_QUEUE(bank[1,1]) INIT_QUEUE(bank[1,2]) APPEND_QUEUE(17,bank[1,2],b,n,s) READ(bank[1]) WRITE(bank[1])',prefix=prefix,decl='bank:ARRAY[1]OF row_t b:ARRAY[2]OF INTEGER n,s:INTEGER',read=lambda req:[42]);p.run();self.assertEqual(texts(p),[' 42'])
    def test_ordinary_row_argument_is_private(self):
        p,_=bank('fill(bank[2])',routines='ROUTINE fill(v:ARRAY OF QUEUE_TYPE) BEGIN READ(v) END fill',read=lambda req:[42]);self.assertEqual(p.run()['BANK'][1][0]['entries'],[[1,9]])
        # Ordinary prefix arguments are private logical copies; READ itself is live.
    def test_bare_bank_formal_borrows(self):
        p,_=bank('fill(bank)',routines='ROUTINE fill(v:ARRAY[*,*]OF QUEUE_TYPE) BEGIN READ(v) END fill',read=lambda req:[42,43]);self.assertEqual(p.run()['BANK'][1][0]['entries'],[[1,43]])
    def test_all_empty_bank_output(self):
        p,_=compile_program('INIT_QUEUE(bank[1]) INIT_QUEUE(bank[2]) WRITE(bank)',decl='bank:ARRAY[2]OF QUEUE_TYPE');p.run();self.assertEqual(texts(p),[''])
    def test_bank_shape_replacement_in_callback_rejects_cell_retargeting(self):
        def read(req):p._state.values['BANK'].values[1]=rt.QueueValue();return [42,43]
        p,_=bank('READ(bank)',read=read)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['BANK'][1][0]['entries'],[[1,9]])

class QueueIOBudgetTests(unittest.TestCase):
    def test_scalar_capture_charges_before_payload_formats_or_transport(self):
        routine='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 4 END width'
        for operation in ('READ','WRITE'):
            with self.subTest(operation=operation):
                seen=[]
                p,_=build('visits=0 '+operation+'(q::width())',seed=False,
                          routines=routine,read=seen.append)
                q=queue(p)
                q.initialized=True
                q.sequence=2
                q.entries=[(1,17),(2,9)]
                q.buffer=p._state.values['B']
                entries_before,buffer=q.entries,q.buffer
                with (patch('karel2py.storage.collection_payload',
                            side_effect=AssertionError('encoded uncharged queue')),
                      self.assertRaisesRegex(rt.KarelRuntimeError,'step budget')):
                    p.run(max_steps=2)
                self.assertEqual((p.snapshot()['VISITS'],seen,texts(p)),(0,[],[]))
                self.assertIs(q.entries,entries_before)
                self.assertIs(q.buffer,buffer)
                self.assertEqual((q.entries,q.sequence),([(1,17),(2,9)],2))

    def test_bank_and_flat_row_preflight_charge_before_payload_or_formats(self):
        routine='ROUTINE width:INTEGER BEGIN n=n+1 RETURN 4 END width'
        for operation in ('READ','WRITE'):
            for selector in ('bank','bank[2]'):
                with self.subTest(operation=operation,selector=selector):
                    seen=[]
                    p,_=compile_program(f'n=0 {operation}({selector}::width())',
                                        decl=BANK_DECL,routines=routine,read=seen.append)
                    for q in p._state.values['BANK'].values:q.initialized=True
                    q=p._state.values['BANK'].values[3]
                    q.sequence=1
                    q.entries=[(1,17)]
                    with (patch('karel2py.storage.collection_payload',
                                side_effect=AssertionError('encoded uncharged bank')),
                          self.assertRaisesRegex(rt.KarelRuntimeError,'step budget')):
                        p.run(max_steps=2)
                    self.assertEqual((p.snapshot()['N'],seen,texts(p)),(0,[],[]))
                    self.assertEqual(q.entries,[(1,17)])

    def test_grouped_write_row_captures_values_without_cloning(self):
        p,_=bank('WRITE((bank[1])::width())',
                 routines='ROUTINE width:INTEGER BEGIN INIT_QUEUE(bank[1,2]) RETURN 3 END width')
        with patch.object(rt,'collection_array_source_value',side_effect=AssertionError('cloned queue row')):
            p.run()
        self.assertEqual(texts(p),[' 17'])
        self.assertEqual(p.snapshot()['BANK'][0][1]['entries'],[])

    def test_read_declines_rebound_root_after_charge(self):
        seen=[]
        p,_=build('READ(q)',seed=False,read=seen.append)
        state=p._state
        original=queue(p)
        original.initialized=True
        original.sequence=1
        original.entries=[(1,17)]
        replacement=rt.QueueValue()
        replacement.initialized=True
        replacement.sequence=1
        replacement.entries=[(1,9)]
        tick=state.tick

        def replace(*args,**kwargs):
            tick(*args,**kwargs)
            if state.steps==2:state.values['Q']=replacement

        with (patch.object(state,'tick',side_effect=replace),
              self.assertRaisesRegex(rt.KarelRuntimeError,'Queue READ destination changed')):
            p.run()
        self.assertIs(queue(p),replacement)
        self.assertEqual((original.entries,replacement.entries,seen),([(1,17)],[(1,9)],[]))

    def test_bank_rejects_backing_mapping_change_during_charge(self):
        seen=[]
        p,_=compile_program('READ(bank)',decl=BANK_DECL,read=seen.append)
        state=p._state
        for q in state.values['BANK'].values:q.initialized=True
        q=state.values['BANK'].values[1]
        q.sequence=1
        q.entries=[(1,17)]
        q.buffer=state.values['B']
        tick=state.tick

        def replace(*args,**kwargs):
            tick(*args,**kwargs)
            if state.steps==2:q.buffer.values=q.buffer.values[:]

        with (patch.object(state,'tick',side_effect=replace),
              patch('karel2py.storage.collection_payload',side_effect=AssertionError('encoded stale bank')),
              self.assertRaisesRegex(rt.KarelRuntimeError,'Queue ARRAY I/O storage changed')):
            p.run()
        self.assertEqual((q.entries,seen),([(1,17)],[]))

    def test_combined_queue_field_limit_precedes_payload_validation(self):
        p,_=compile_program('WRITE(bank)',decl='bank:ARRAY[2]OF QUEUE_TYPE')
        for q in p._state.values['BANK'].values:
            q.initialized=True
            q.sequence=513
            q.entries=[(i,i) for i in range(1,514)]
        with (patch('karel2py.storage.collection_payload',side_effect=AssertionError('encoded oversized bank')),
              self.assertRaisesRegex(rt.KarelRuntimeError,'1024 scalar fields')):
            p.run()
        self.assertEqual(texts(p),[])


class QueueCaptureTests(unittest.TestCase):
    def test_complete_capture_can_publish_repeated_inputs(self):
        p,q,targets=capture()
        with rt._numeric_scope('pythonic'):
            for values in ([42,43],[52,53]):
                prepared=rt._prepare_read_values(targets,values,41)
                for target,value in zip(targets,prepared):target.set(value,41)
        self.assertEqual(q.entries,[(1,52),(2,53)])
    def test_callback_read_publishes_without_reencoding_queues(self):
        started=False

        def read(_):
            nonlocal started
            started=True
            return [7,42,43,52]

        original=rt._queue_io_payload

        def validate(queue,line=None):
            self.assertFalse(started,'encoded a queue after input began')
            return original(queue,line)

        p,_=build('INIT_QUEUE(r) APPEND_QUEUE(11,r,c,n,s) READ(n,q,r)',read=read)
        with patch.object(rt,'_queue_io_payload',side_effect=validate):
            result=p.run()
        self.assertEqual(result['N'],7)
        self.assertEqual((entries(p),entries(p,'R')),([(1,42),(2,43)],[(1,52)]))
        self.assertEqual((result['B'],result['C']),([17,9,0],[11,0,0]))
        self.assertIsNone(queue(p).buffer)
        self.assertIsNone(queue(p,'R').buffer)

    def test_binary_read_publishes_without_reencoding_after_transport(self):
        files=rt.MemoryFiles({'in':struct.pack('<ii',42,43)})
        p,_=build("OPEN FILE f('RB','in') READ f(q)",context=rt.ExecutionContext(files=files))
        started=False
        read_bytes=files.read_bytes
        encode=rt._queue_io_payload

        def read(*args,**kwargs):
            nonlocal started
            started=True
            return read_bytes(*args,**kwargs)

        def validate(queue,line=None):
            self.assertFalse(started,'encoded a queue after binary transport began')
            return encode(queue,line)

        with (patch.object(files,'read_bytes',side_effect=read),
              patch.object(rt,'_queue_io_payload',side_effect=validate)):
            result=p.run()
        self.assertEqual((result['F']['position'],result['F']['status']),(8,0))
        self.assertEqual(entries(p),[(1,42),(2,43)])
        self.assertIsNone(queue(p).buffer)

    def test_invalid_later_queue_does_not_install_any_new_plans(self):
        p,q,first=capture()
        r=queue(p,'R')
        r.initialized=True
        r.entries=[(1,29)]
        r.sequence=1
        with rt._numeric_scope('pythonic'):
            second=[field for field,_ in rt.capture_aggregate_read_target(p._state.reference('R'),[],41)]
            with self.assertRaisesRegex(rt.KarelRuntimeError,'Expected INTEGER'):
                rt._prepare_read_values(first+second,[42,43,'bad'],41)
        self.assertIsNone(first[0].cohort.plan)
        self.assertIsNone(second[0].cohort.plan)
        self.assertEqual((q.entries,r.entries),([(1,17),(2,18)],[(1,29)]))

    def test_relocated_queue_reference_is_rejected_even_if_it_names_same_queue(self):
        _,q,targets=capture()
        source=targets[0].cohort.source
        source.storage={source.key:q}
        with (rt._numeric_scope('pythonic'),
              self.assertRaisesRegex(rt.KarelRuntimeError,'capture changed')):
            rt._prepare_read_values(targets,[42,43],41)
        self.assertEqual(q.entries,[(1,17),(2,18)])

    def test_boolean_metadata_or_entry_values_cannot_match_integer_snapshot(self):
        for member in ('sequence','entry'):
            with self.subTest(member=member):
                _,q,targets=capture(1)
                if member=='sequence':q.sequence=True
                else:q.entries[0]=(True,17)
                with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):
                    rt._prepare_read_values(targets,[42],41)

    def test_direct_unprepared_field_write_rejects(self):
        _,q,targets=capture()
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'prepared'):targets[0].set(42,41)
        self.assertEqual(q.entries,[(1,17),(2,18)])
    def test_partial_reordered_duplicate_or_interleaved_capture_rejects(self):
        p,q,t=capture();ref=p._state.reference('N')
        for targets in (t[:1],list(reversed(t)),t+t,[t[0],ref,t[1]]):
            with self.subTest(targets=len(targets)),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt._validate_read_targets(targets,41)
    def test_malformed_field_metadata_rejects(self):
        for name,value in (('index',True),('index',99),('cohort',object())):
            _,_,t=capture();setattr(t[0],name,value)
            with self.subTest(name=name),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt._validate_read_targets(t,41)
    def test_entry_storage_alias_rejects(self):
        _,q,t=capture();ref=rt.Reference(rt.INTEGER,q.entries,0)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):rt._validate_read_targets(t+[ref],41)
    def test_malformed_queue_state_fails_closed(self):
        mutations=[lambda q:setattr(q,'initialized',1),lambda q:setattr(q,'sequence',True),lambda q:setattr(q,'sequence',-1),lambda q:setattr(q,'entries',[(1,True)]),lambda q:setattr(q,'entries',[(1,1),(1,2)]),lambda q:setattr(q,'entries',[(3,1)]),lambda q:setattr(q,'entries',())]
        for mutate in mutations:
            p,_=build('WRITE(q)',seed=False);q=queue(p);q.initialized=True;q.sequence=2;q.entries=[(1,17)];mutate(q)
            with self.subTest(mutation=mutate),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(texts(p),[])
    def test_stale_queue_metadata_fails_before_publication(self):
        for mutate in (lambda q:setattr(q,'initialized',False),lambda q:setattr(q,'sequence',3),lambda q:setattr(q,'entries',q.entries[:]),lambda q:q.entries.append((3,99)),lambda q:q.entries.__setitem__(0,(1,99))):
            _,q,t=capture();mutate(q)
            with self.subTest(mutation=mutate),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt._prepare_read_values(t,[42,43],41)
    def test_backing_mapping_replacement_rejects(self):
        _,q,t=capture(buffer=True);q.buffer.values=q.buffer.values[:]
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'capture changed'):rt._prepare_read_values(t,[42,43],41)
    def test_backing_values_can_change_independently(self):
        _,q,t=capture(buffer=True);old=q.buffer;old.values[0]=99
        with rt._numeric_scope('pythonic'):
            values=rt._prepare_read_values(t,[42,43],41)
            for target,value in zip(t,values):target.set(value,41)
        self.assertEqual(old.values,[99,9,0]);self.assertIsNone(q.buffer)
    def test_readonly_queue_reference_rejects(self):
        p,_=build('');p.run();ref=rt.ReadOnlyFieldReference(('QUEUE_TYPE',),{'q':queue(p)},'q')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.capture_aggregate_read_target(ref,[],41)
    def test_exact_1024_values_can_be_read(self):
        _,q,t=capture(1024)
        with rt._numeric_scope('pythonic'):
            values=rt._prepare_read_values(t,list(range(1024)),41)
            for target,value in zip(t,values):target.set(value,41)
        self.assertEqual(q.entries[-1],(1024,1023))
    def test_1025_values_reject_before_callback(self):
        for operation in ('READ','WRITE'):
            p,_=build(operation+'(q)',seed=False,read=lambda req:self.fail('adapter called'));q=queue(p);q.initialized=True;q.sequence=1025;q.entries=[(i+1,i) for i in range(1025)]
            with self.subTest(operation=operation),self.assertRaisesRegex(rt.KarelRuntimeError,'1024'):p.run()
    def test_resource_record_fields_and_file_banks_stay_closed(self):
        self.assertFalse(rt.aggregate_read_type(('STRUCTURE','T',(('Q',('QUEUE_TYPE',)),))));self.assertFalse(rt.aggregate_write_type(('ARRAY',2,('FILE',))))
    def test_generic_queue_copy_helpers_stay_closed(self):
        _,q,_=capture()
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.checked(('QUEUE_TYPE',),q)
    def test_queue_query_preserves_entries_sequence_and_backing_buffer(self):
        p,_=build('flag=UNINIT(q)',decl=DECL+' flag:BOOLEAN')
        self.assertFalse(p.run()['FLAG'])
        self.assertEqual((entries(p),queue(p).sequence),([(1,17),(2,9)],2))
        self.assertIs(queue(p).buffer,p._state.values['B'])

class QueueTransportTests(unittest.TestCase):
    def test_serial_input_and_output(self):
        bank,ctx=serial(b'42 43\n');p,_=build("OPEN FILE f('UD','P2:') READ f(q,CR) WRITE f(q,CR) CLOSE FILE f",context=ctx);p.run();self.assertEqual(entries(p),[(1,42),(2,43)]);self.assertEqual(bank.snapshot()[2]['output'],b' 42 43\n')
    def test_cancel_keeps_queue_and_buffer_link(self):
        bank,ctx=serial(b'42 ')
        def sleep(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build(OPEN+'READ f(q,CR) s=IO_STATUS(f) CLOSE FILE f',context=ctx,sleep=sleep);self.assertEqual(p.run()['S'],6);self.assertEqual(entries(p),[(1,17),(2,9)]);self.assertIsNotNone(queue(p).buffer);self.assertEqual(bank.snapshot()[2]['input'],b'42 ')
    def test_pause_resume_retains_capture(self):
        bank,ctx=serial();project,p,h=pending(ctx,SEED+OPEN+'READ f(q,CR) s=IO_STATUS(f) CLOSE FILE f',decl=DECL);p.pause()
        for _ in range(80):
            project.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');bank.feed(2,b'42 43\n');self.assertEqual(entries(p),[(1,17),(2,9)]);project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_stop_discards_pending_publication(self):
        bank,ctx=serial(b'42 ');project,p,h=pending(ctx,SEED+OPEN+'READ f(q,CR)',decl=DECL);project.scheduler.stop('MAIN');self.assertIsNone(h._read_operation);self.assertEqual(entries(p),[(1,17),(2,9)]);self.assertIsNotNone(queue(p).buffer);bank.close(h)
    def test_linked_borrowed_queue(self):
        main='PROGRAM MAIN VAR q:QUEUE_TYPE b:ARRAY[3]OF INTEGER n,s:INTEGER ROUTINE fill(v:QUEUE_TYPE) FROM LIB BEGIN '+SEED+'fill(q) END MAIN'
        lib='PROGRAM LIB ROUTINE fill(v:QUEUE_TYPE) BEGIN READ(v) END fill BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate(options={'read':lambda req:[42,43]});project.run('MAIN');self.assertEqual(entries(project.programs['MAIN']),[(1,42),(2,43)])
    def test_linked_shared_queue_bank(self):
        main='PROGRAM MAIN VAR q FROM LIB:ARRAY[2]OF QUEUE_TYPE b:ARRAY[3]OF INTEGER n,s:INTEGER BEGIN INIT_QUEUE(q[1]) INIT_QUEUE(q[2]) APPEND_QUEUE(17,q[2],b,n,s) READ(q) END MAIN'
        lib='PROGRAM LIB VAR q:ARRAY[2]OF QUEUE_TYPE BEGIN END LIB';project=translate_project({'main':main,'lib':lib}).instantiate(options={'read':lambda req:[42]});project.run('MAIN');self.assertEqual(project.programs['LIB'].snapshot()['Q'][1]['entries'],[[1,42]])

class QueueExtendedTests(unittest.TestCase):
    def test_mixed_position_and_queue_input(self):
        from tests.test_position_input import VALUES,EXPECTED
        p,_=build('READ(q,pose)',decl=DECL+' pose:POSITION',values=[42,43]+VALUES);self.assertEqual(p.run()['POSE'],EXPECTED);self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_invalid_position_prevents_queue_publication(self):
        from tests.test_position_input import VALUES
        values=list(VALUES);values[0]=2.
        p,_=build('READ(q,pose)',decl=DECL+' pose:POSITION',values=[42,43]+values)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'POSITION'):p.run()
        self.assertEqual(entries(p),[(1,17),(2,9)]);self.assertIsNotNone(queue(p).buffer)
    def test_text_geometry_failure_restores_cursor(self):
        from tests.test_position_input import VALUES,text
        values=list(VALUES);values[0]=2.;adapter=rt.TextInput('42 43 '+text(values));initial=adapter.position.copy()
        p,_=build('READ(q,pose)',decl=DECL+' pose:POSITION',read=adapter)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(adapter.position,initial);self.assertEqual(entries(p),[(1,17),(2,9)])
    def test_bad_second_queue_is_atomic_across_cohorts(self):
        p,_=build('INIT_QUEUE(r) APPEND_QUEUE(5,r,c,n,s) READ(q,r)',values=[42,43,True])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((entries(p),entries(p,'R')),([(1,17),(2,9)],[(1,5)]))
    def test_shared_entries_between_queue_descriptors_reject(self):
        p,_=build('READ(q,r)',seed=False,values=[42,43]);q,r=queue(p),queue(p,'R');q.initialized=r.initialized=True;q.sequence=r.sequence=1;q.entries=[(1,17)];r.entries=q.entries
        with self.assertRaisesRegex(rt.KarelRuntimeError,'disjoint'):p.run()
        self.assertEqual(q.entries,[(1,17)])
    def test_mutable_entry_pair_alias_rejects(self):
        _,q,t=capture();q.entries[0]=[1,17];ref=rt.Reference(rt.INTEGER,q.entries[0],1)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):rt._validate_read_targets(t+[ref],41)
    def test_malformed_cohort_members_reject(self):
        _,_,t=capture();t[0].cohort.members=None
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt._validate_read_targets(t,41)
    def test_malformed_buffer_schema_rejects_with_source_line(self):
        _,q,t=capture(buffer=True);q.buffer.spec=None
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError) as error:rt._validate_read_targets(t,41)
        self.assertIn('line 41',str(error.exception))
    def test_malformed_bank_storage_is_source_located(self):
        p,_=compile_program('READ(bank)',decl=BANK_DECL,read=lambda req:self.fail('adapter called'));p._state.values['BANK'].values=()
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_buffer_link_change_during_callback_rejects(self):
        def read(req):queue(p).buffer=p._state.values['C'];return [42,43]
        p,_=build('READ(q)',read=read)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(entries(p),[(1,17),(2,9)])
    def test_reverse_binary_order_roundtrip(self):
        files=rt.MemoryFiles();p,_=build("SET_FILE_ATR(f,ATR_REVERSE,1) OPEN FILE f('WB','out') WRITE f(q) CLOSE FILE f OPEN FILE f('RB','out') READ f(q) CLOSE FILE f",context=rt.ExecutionContext(files=files));p.run();self.assertEqual(bytes(files.files['out']),struct.pack('>ii',17,9));self.assertEqual(entries(p),[(1,17),(2,9)]);self.assertIsNone(queue(p).buffer)
    def test_pipe_input(self):
        from tests.test_pipe_attributes import bank as pipe_bank
        files=pipe_bank(b'42 43\n');p,_=build("OPEN FILE f('RO','PIP:LOG') READ f(q,CR) CLOSE FILE f",context=rt.ExecutionContext(file_pipes=files));p.run();self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_keyboard_input(self):
        from tests.test_keyboard import context
        from tests.test_keyboard_file_read import line_keys
        p,_=build("OPEN FILE f('RO','KB:TPKB') READ f(q,CR) CLOSE FILE f",context=context(line_keys('42 43')));p.run();self.assertEqual(entries(p),[(1,42),(2,43)])
    def test_created_scalar_queue(self):
        body="CREATE_VAR('CACHE','ITEM','T','QUEUE_TYPE',0,0,0,0,s) fill(BYNAME('CACHE','ITEM',n))"
        routines='ROUTINE fill(v:QUEUE_TYPE) BEGIN INIT_QUEUE(v) APPEND_QUEUE(17,v,b,n,s) READ(v) r=v END fill'
        p,_=build(body,seed=False,routines=routines,values=[42]);p.run();self.assertEqual(entries(p,'R'),[(1,42)])
    def test_created_queue_bank(self):
        body="CREATE_VAR('CACHE','BANK','T','ARRAY OF QUEUE_TYPE',0,2,0,0,s) fill(BYNAME('CACHE','BANK',n))"
        routines='ROUTINE fill(v:ARRAY OF QUEUE_TYPE) BEGIN INIT_QUEUE(v[1]) INIT_QUEUE(v[2]) APPEND_QUEUE(17,v[2],b,n,s) READ(v) r=v[2] END fill'
        p,_=build(body,seed=False,routines=routines,values=[42]);p.run();self.assertEqual(entries(p,'R'),[(1,42)])
    def test_three_dimensional_plane_input(self):
        p,_=compile_program('READ(bank[2])',decl='bank:ARRAY[2,2,2]OF QUEUE_TYPE',read=lambda req:[42]);a=p._state.values['BANK']
        for q in a.values:q.initialized=True
        a.values[7].sequence=1;a.values[7].entries=[(1,17)];v=p.run()['BANK'];self.assertEqual(v[1][1][1]['entries'],[[1,42]])
    def test_bad_queue_array_type_helper_does_not_open_record_resources(self):
        for spec in (None,(),('ARRAY',2),('STRUCTURE','T',(('Q',('QUEUE_TYPE',)),)),('ARRAY',1,('FILE',))):
            with self.subTest(spec=spec):self.assertFalse(rt.queue_io_type(spec))
    def test_input_report_records_queue_order(self):
        _,r=build('READ(q)');self.assertIn('QUEUE-entry-order',str(r.report['reads']))
