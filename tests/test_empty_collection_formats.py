"""Uniform formats on empty logical output, without field bytes or padding."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_directory_templates import backend,snapshot
from tests.test_file_cancellation import serial
from tests.test_pipe_attributes import bank as pipe_bank

PREFIX='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
DECL='p:route_t paths:ARRAY[2]OF route_t q:QUEUE_TYPE qs:ARRAY[2,2]OF QUEUE_TYPE buffer:ARRAY[2]OF INTEGER n,s,visits:INTEGER f:FILE'


def build(body='',**options):return compile_program(body,decl=options.pop('decl',DECL),prefix=options.pop('prefix',PREFIX),**options)
def texts(program):return [row['text'] for row in program.write_requests]


class EmptyCollectionOutputTests(unittest.TestCase):
    def test_scalar_path_queue_and_banks_emit_empty_items_with_formats(self):
        body='INIT_QUEUE(q) INIT_QUEUE(qs[1,1]) INIT_QUEUE(qs[1,2]) INIT_QUEUE(qs[2,1]) INIT_QUEUE(qs[2,2]) WRITE(p::4::16,paths::4::16,q::4::16,qs::4::16)'
        program,_=build(body);program.run();self.assertEqual(texts(program),[''])
        self.assertEqual(program._state.values['P'].nodes,[]);self.assertEqual(program._state.values['Q'].entries,[])

    def test_empty_groups_add_no_padding_around_real_output_or_cr(self):
        program,_=build("INIT_QUEUE(q) WRITE('left',p::254,q::254,42::4,CR,'right')")
        program.run();self.assertEqual(texts(program),['left  42\nright'])

    def test_row_and_plane_output_keeps_one_empty_group(self):
        for decl,setup,item in (
            ('bank:ARRAY[2,2]OF route_t','', 'bank[2]'),
            ('bank:ARRAY[2,1,2]OF route_t','', 'bank[2]'),
            ('bank:ARRAY[2,2]OF QUEUE_TYPE','INIT_QUEUE(bank[2,1]) INIT_QUEUE(bank[2,2])','bank[2]')):
            with self.subTest(decl=decl):
                program,_=build(setup+f' WRITE({item}::4)',decl=decl)
                program.run();self.assertEqual(texts(program),[''])

    def test_declared_primitive_node_domains_accept_valid_empty_formats(self):
        for kind,controls in (('INTEGER','4::16'),('BYTE','4::2'),('SHORT','4::10'),('REAL','4::2'),('BOOLEAN','4'),('STRING[8]','8::2')):
            with self.subTest(kind=kind):
                prefix=f'TYPE node_t=STRUCTURE value:{kind} ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
                program,_=build('WRITE(p::'+controls+')',prefix=prefix,decl='p:route_t')
                program.run();self.assertEqual(texts(program),[''])

    def test_default_position_node_and_mixed_schema_use_all_declared_kinds(self):
        program,_=build('WRITE(p::4)',decl='p:PATH',prefix='');program.run();self.assertEqual(texts(program),[''])
        prefix='TYPE node_t=STRUCTURE value:INTEGER label:STRING[8] ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        program,_=build('WRITE(p::4::2)',decl='p:route_t',prefix=prefix);program.run();self.assertEqual(texts(program),[''])
        with self.assertRaises(TranslationError):build('WRITE(p::4::16)',decl='p:route_t',prefix=prefix)

    def test_empty_string_nodes_do_not_allocate_the_requested_large_width(self):
        prefix='TYPE node_t=STRUCTURE label:STRING[8] ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        program,_=build('WRITE(p::1000000000::3)',decl='p:route_t',prefix=prefix)
        program.run();self.assertEqual(texts(program),[''])

    def test_formats_run_once_in_order_after_capture(self):
        routines='ROUTINE width:INTEGER BEGIN visits=visits*10+1 RETURN 4 END width ROUTINE base:INTEGER BEGIN visits=visits*10+2 RETURN 16 END base'
        program,_=build('visits=0 WRITE(paths::width()::base())',routines=routines)
        self.assertEqual(program.run()['VISITS'],12);self.assertEqual(texts(program),[''])

    def test_queue_added_by_format_function_does_not_change_captured_empty_output(self):
        routines='ROUTINE width:INTEGER BEGIN visits=visits+1 APPEND_QUEUE(17,q,buffer,n,s) RETURN 4 END width'
        program,_=build('visits=0 INIT_QUEUE(q) WRITE(q::width()) WRITE(q::4)',routines=routines)
        self.assertEqual(program.run()['VISITS'],1);self.assertEqual(texts(program),['','  17'])
        self.assertEqual(program._state.values['Q'].entries,[(1,17)])

    def test_path_added_by_format_function_does_not_change_captured_empty_output(self):
        routines='ROUTINE width:INTEGER BEGIN visits=visits+1 APPEND_NODE(p,s) p[1].amount=17 RETURN 4 END width'
        program,_=build('visits=0 WRITE(p::width()) WRITE(p::4)',routines=routines)
        self.assertEqual(program.run()['VISITS'],1);self.assertEqual(texts(program),['','  17'])

    def test_borrowed_and_private_routine_arguments_keep_empty_values(self):
        routines='ROUTINE show(value:route_t) BEGIN WRITE(value::4) END show ROUTINE queues(value:QUEUE_TYPE) BEGIN WRITE(value::4) END queues'
        program,_=build('INIT_QUEUE(q) show(p) show((p)) queues(q) queues((q))',routines=routines)
        program.run();self.assertEqual(texts(program),['','','',''])

    def test_empty_function_results_and_created_data_keep_existing_interfaces(self):
        routines='ROUTINE make:route_t VAR value:route_t BEGIN RETURN value END make'
        program,_=build('WRITE(make()::4) CREATE_VAR(\'CACHE\',\'ROUTE\',\'T\',\'ROUTE_T\',0,0,0,0,s) show(BYNAME(\'CACHE\',\'ROUTE\',n))',
            routines=routines+' ROUTINE show(value:route_t) BEGIN WRITE(value::4) END show')
        self.assertEqual(program.run()['S'],0);self.assertEqual(texts(program),['',''])

    def test_generic_bank_formals_keep_selected_empty_rows(self):
        routines='ROUTINE show(value:ARRAY OF route_t) BEGIN WRITE(value::4) END show ROUTINE queues(value:ARRAY OF QUEUE_TYPE) BEGIN WRITE(value::4) END queues'
        body='INIT_QUEUE(qs[2,1]) INIT_QUEUE(qs[2,2]) show(paths) show((paths)) queues(qs[2])'
        program,_=build(body,routines=routines);program.run();self.assertEqual(texts(program),['','',''])

    def test_report_identifies_declared_domain_validation_and_no_native_framing(self):
        _,result=build('WRITE(p::4)')
        policy=result.report['empty_collection_write_policy']
        self.assertIn('declared scalar',policy['formats']);self.assertIn('empty',policy['binary'])
        self.assertFalse(policy['controller_validated']);json.dumps(result.report)


class EmptyCollectionGuardTests(unittest.TestCase):
    def test_dynamic_width_base_and_precision_errors_publish_nothing(self):
        cases=[('INTEGER','255','0'),('INTEGER','4','17'),('REAL','4','255'),('STRING[8]','4','4')]
        for kind,width,second in cases:
            prefix=f'TYPE node_t=STRUCTURE value:{kind} ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
            routines=f'ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN {width} END width ROUTINE second:INTEGER BEGIN visits=visits+1 RETURN {second} END second'
            program,_=build("visits=0 WRITE('prefix',p::width()::second(),CR)",decl='p:route_t visits:INTEGER',prefix=prefix,routines=routines)
            with self.subTest(kind=kind),self.assertRaises(rt.KarelRuntimeError):program.run()
            self.assertEqual(program.snapshot()['VISITS'],2);self.assertEqual(texts(program),[])

    def test_mixed_schema_dynamic_format_must_fit_every_declared_kind(self):
        prefix='TYPE node_t=STRUCTURE value:INTEGER label:STRING[8] ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        program,_=build('WRITE(p::4::base())',decl='p:route_t',prefix=prefix,routines='ROUTINE base:INTEGER BEGIN RETURN 16 END base')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'alignment'):program.run()
        self.assertEqual(texts(program),[])

    def test_empty_uninitialized_queue_and_malformed_path_reject_before_formats(self):
        routines='ROUTINE width:INTEGER BEGIN visits=1 RETURN 4 END width'
        program,_=build('visits=0 WRITE(q::width())',routines=routines)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'INIT_QUEUE'):program.run()
        self.assertEqual((program.snapshot()['VISITS'],texts(program)),(0,[]))
        program,_=build('visits=0 WRITE(p::width())',routines=routines)
        program._state.values['P'].nodes={}
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual((program.snapshot()['VISITS'],texts(program)),(0,[]))

    def test_empty_reads_still_reject_without_consuming_input(self):
        for setup,item in (('','p'),('INIT_QUEUE(q)','q')):
            seen=[];program,_=build(setup+f' READ({item}::4)',read=lambda request:seen.append(request))
            with self.subTest(item=item),self.assertRaises(rt.KarelRuntimeError):program.run()
            self.assertEqual(seen,[])

    def test_invalid_static_formats_retain_source_diagnostics(self):
        for body in ('WRITE(p::255)','WRITE(p::4::17)','WRITE(q::4::1)'):
            with self.subTest(body=body),self.assertRaises(TranslationError):build(body)

    def test_budget_failure_before_capture_keeps_format_effects_unexecuted(self):
        program,_=build('visits=0 INIT_QUEUE(q) WRITE(q::width())',routines='ROUTINE width:INTEGER BEGIN visits=1 RETURN 4 END width')
        with self.assertRaises(rt.KarelRuntimeError):program.run(max_steps=3)
        self.assertEqual((program.snapshot()['VISITS'],texts(program)),(0,[]))

    def test_multiple_empty_items_still_obey_operation_item_limits(self):
        with self.assertRaises(TranslationError):build('WRITE('+','.join('p::0' for _ in range(1025))+')')


class EmptyCollectionFileTests(unittest.TestCase):
    def test_text_append_emits_no_field_bytes_but_keeps_real_values_and_cr(self):
        bank=rt.MemoryFiles({'out':b'prefix'});ctx=rt.ExecutionContext(files=bank)
        program,_=build("INIT_QUEUE(q) OPEN FILE f('AP','out') WRITE f(p::4,q::4) WRITE f('X',p::4,CR) CLOSE FILE f",context=ctx)
        program.run();self.assertEqual(bytes(bank.files['out']),b'prefixX\n')

    def test_binary_empty_integer_path_and_queue_write_zero_bytes(self):
        bank=rt.MemoryFiles();ctx=rt.ExecutionContext(files=bank)
        program,_=build("INIT_QUEUE(q) OPEN FILE f('WB','out') WRITE f(p::4,q::4,paths::4) CLOSE FILE f",context=ctx)
        program.run();self.assertEqual(bytes(bank.files['out']),b'')

    def test_rooted_and_capacity_full_virtual_files_keep_existing_prefix(self):
        for kind in ('directory','device'):
            with self.subTest(kind=kind),backend(kind,{'out':b'Z'}) as bank:
                name='RD:out' if kind=='device' else 'out'
                if kind=='device':bank._volumes['RD']['capacity']=1
                program,_=build(f"OPEN FILE f('AP','{name}') WRITE f(p::4) CLOSE FILE f",context=rt.ExecutionContext(files=bank))
                program.run();self.assertEqual(snapshot(bank),{'out':b'Z'})

    def test_binary_width_and_second_controls_keep_scalar_restrictions(self):
        for item in ('p::3','q::4::0'):
            bank=rt.MemoryFiles();ctx=rt.ExecutionContext(files=bank)
            program,_=build("INIT_QUEUE(q) OPEN FILE f('WB','out') WRITE f("+item+")",context=ctx)
            with self.subTest(item=item),self.assertRaises(rt.KarelRuntimeError):program.run()
            self.assertEqual(bytes(bank.files['out']),b'')

    def test_binary_empty_string_node_width_is_validated_without_nul_padding(self):
        prefix='TYPE node_t=STRUCTURE label:STRING[8] ENDSTRUCTURE route_t=PATH NODEDATA=node_t'
        bank=rt.MemoryFiles();ctx=rt.ExecutionContext(files=bank)
        program,_=build("OPEN FILE f('WB','out') WRITE f(p::8) CLOSE FILE f",decl='p:route_t f:FILE',prefix=prefix,context=ctx)
        program.run();self.assertEqual(bytes(bank.files['out']),b'')

    def test_empty_output_still_requires_open_writable_file(self):
        bank=rt.MemoryFiles({'out':b'old'});ctx=rt.ExecutionContext(files=bank)
        for body in ('WRITE f(p::4)',"OPEN FILE f('RO','out') WRITE f(p::4)"):
            program,_=build(body,context=ctx)
            with self.subTest(body=body),self.assertRaises(rt.KarelRuntimeError):program.run()
            self.assertEqual(bytes(bank.files['out']),b'old')

    def test_serial_and_plain_pipe_transports_emit_only_real_bytes(self):
        bank,ctx=serial();program,_=build("OPEN FILE f('WO','P2:') WRITE f(p::4,'X') CLOSE FILE f",context=ctx)
        program.run();self.assertEqual(bank.snapshot()[2]['output'],b'X')
        pipes=pipe_bank();ctx=rt.ExecutionContext(file_pipes=pipes)
        program,_=build("OPEN FILE f('WO','PIP:LOG') WRITE f(p::4,'X') CLOSE FILE f",context=ctx)
        program.run();self.assertEqual(pipes.snapshot()['PIP:LOG'],b'X')

    def test_linked_empty_output_and_context_roundtrip(self):
        project=translate_project({'m':'PROGRAM MAIN ROUTINE show FROM LIB BEGIN show() END MAIN',
            'l':"PROGRAM LIB VAR p:PATH q:QUEUE_TYPE ROUTINE show BEGIN INIT_QUEUE(q) WRITE('a',p::4,q::4,CR) END show BEGIN END LIB"})
        seen=[];ctx=rt.ExecutionContext();instance=project.instantiate(context=ctx,options={'write':seen.append})
        instance.run('MAIN');self.assertEqual(seen,['a\n'])
        config=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)
