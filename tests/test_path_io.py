"""Authored whole-PATH scalar I/O, capture ordering and transport boundaries."""
import json
import struct
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program


TYPES='TYPE node_t=STRUCTURE amount:INTEGER label:STRING[4] ENDSTRUCTURE header_t=STRUCTURE total:INTEGER ENDSTRUCTURE'
DECL='p,q:PATH NODEDATA=node_t PATHHEADER=header_t n,s,visits:INTEGER f:FILE'
SEED="INSERT_NODE(p,1,s) INSERT_NODE(p,2,s) p.total=2 p[1].amount=7 p[1].label='abcd' p[2].amount=9 p[2].label='wxyz' "
VALUES=[3,17,'left',19,'rght']
EXPECTED={'nodes':[{'AMOUNT':17,'LABEL':'left'},{'AMOUNT':19,'LABEL':'rght'}],'data':{'TOTAL':3}}


def build(body='',*,decl=DECL,prefix=TYPES,seed=True,values=None,**options):
    if values is not None:options['read']=lambda request:list(values)
    return compile_program((SEED if seed else '')+body,decl=decl,prefix=prefix,**options)


def text(program):return [row['text'] for row in program.write_requests]


def file_program(body,**options):
    ctx=options.pop('context',rt.ExecutionContext(files=rt.MemoryFiles()))
    p,r=build(body,context=ctx,**options);return p,r,ctx


class PathCaptureBudgetTests(unittest.TestCase):
    def test_scalar_path_budget_precedes_values_formats_and_transport(self):
        routines='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 4 END width'
        for operation in ('READ','WRITE'):
            with self.subTest(operation=operation):
                input_requests=[]
                program,_=build('visits=0 '+operation+'(p::width())',seed=False,
                                read=input_requests.append,routines=routines)
                path=program._state.values['P']
                path.append()
                path.data.values['TOTAL']=7
                node=path.nodes[0]
                node.values.update(AMOUNT=17,LABEL='abcd')
                with (patch.object(rt,'_aggregate_value',side_effect=AssertionError('captured uncharged PATH')),
                      self.assertRaisesRegex(rt.KarelRuntimeError,'step budget')):
                    program.run(max_steps=2)
                self.assertEqual(program.snapshot()['VISITS'],0)
                self.assertEqual(input_requests,[])
                self.assertEqual(text(program),[])
                self.assertEqual(node.values,{'AMOUNT':17,'LABEL':'abcd'})

    def test_scalar_path_rejects_replaced_header_during_charge(self):
        program,_=build('WRITE(p)',seed=False)
        state=program._state
        path=state.values['P']
        path.data.values['TOTAL']=7
        replacement=rt.Structure(path.spec[2])
        replacement.values['TOTAL']=11
        tick=state.tick

        def replace(*args,**kwargs):
            tick(*args,**kwargs)
            if state.steps==2:path.data=replacement

        with (patch.object(state,'tick',side_effect=replace),
              self.assertRaisesRegex(rt.KarelRuntimeError,'PATH I/O storage changed')):
            program.run()
        self.assertIs(path.data,replacement)
        self.assertEqual(text(program),[])


class PathSelectionTests(unittest.TestCase):
    def test_header_only_read_and_write_change_no_nodes(self):
        p, result = build('READ(p[0]) WRITE(p[0],CR)', values=[42])
        values = p.run()
        self.assertEqual(values['P']['data'], {'TOTAL': 42})
        self.assertEqual(values['P']['nodes'], [
            {'AMOUNT': 7, 'LABEL': 'abcd'}, {'AMOUNT': 9, 'LABEL': 'wxyz'},
        ])
        self.assertEqual(text(p), [' 42\n'])
        self.assertEqual(result.report['reads'][0]['destinations'][0]['path_selection'], 'header')

    def test_runtime_index_selects_header_or_node_once_per_transfer(self):
        batches = iter(([12], [17, 'edit']))
        requests = []

        def reader(request):
            requests.append(request)
            return next(batches)

        p, result = build(
            'visits=0 READ(p[pick(0)]) READ(p[pick(2)]) WRITE(p[pick(0)],p[pick(2)])',
            routines='ROUTINE pick(i:INTEGER):INTEGER BEGIN visits=visits+1 RETURN i END pick',
            read=reader,
        )
        values = p.run()
        self.assertEqual(values['VISITS'], 4)
        self.assertEqual(values['P']['data'], {'TOTAL': 12})
        self.assertEqual(values['P']['nodes'], [
            {'AMOUNT': 7, 'LABEL': 'abcd'}, {'AMOUNT': 17, 'LABEL': 'edit'},
        ])
        self.assertEqual(len(requests), 2)
        self.assertEqual(text(p), [' 12 17edit'])
        self.assertEqual(result.report['reads'][0]['destinations'][0]['path_selection'], 'index')

    def test_runtime_array_selection_formats_match_header_and_node_schemas(self):
        p, _ = build(
            "INSERT_NODE(routes[1],1,s) routes[1].label='part' routes[1,1].amount=26 "
            "n=0 WRITE(routes[1,n]::7::3) n=1 WRITE(routes[1][n]::4::16)",
            decl='routes:ARRAY[1] OF PATH NODEDATA=node_t PATHHEADER=header_t n,s:INTEGER',
            prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                   'header_t=STRUCTURE label:STRING[4] ENDSTRUCTURE',
            seed=False,
        )
        p.run()
        self.assertEqual(text(p), [" 'part'", ' 01A'])

    def test_dynamic_range_format_is_checked_against_the_selected_records(self):
        p, _ = build(
            'INSERT_NODE(p,1,s) p[1].amount=26 p.flag=TRUE '
            'n=1 WRITE(p[n..1]::4::16) n=0 WRITE(p[n..1]::4::16)',
            decl='p:PATH NODEDATA=node_t PATHHEADER=header_t n,s:INTEGER',
            prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                   'header_t=STRUCTURE flag:BOOLEAN ENDSTRUCTURE',
            seed=False,
        )
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'BOOLEAN WRITE accepts only a width'):
            p.run()
        self.assertEqual(text(p), [' 01A'])

    def test_incompatible_runtime_read_format_preserves_input_and_path(self):
        requests = []
        p, _ = build(
            "n=0 p.label='old' READ(p[n]::4::16)",
            decl='p:PATH NODEDATA=node_t PATHHEADER=header_t n:INTEGER',
            prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                   'header_t=STRUCTURE label:STRING[4] ENDSTRUCTURE',
            seed=False, read=requests.append,
        )
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'Invalid STRING READ second format'):
            p.run()
        self.assertEqual(requests, [])
        self.assertEqual(p.snapshot()['P']['data'], {'LABEL': 'old'})

    def test_waiting_read_keeps_original_selected_header(self):
        packed = struct.pack('<i', 42)
        bank = rt.SerialStreams({2: {'input': packed[:1], 'wait': True}})
        ctx = rt.ExecutionContext(serial_streams=bank)
        delays = []

        def feed(delay):
            delays.append(delay)
            self.assertEqual(len(delays), 1)
            self.assertEqual(p.snapshot()['P']['data'], {'TOTAL': 2})
            p._state.values['N'] = 2
            bank.feed(2, packed[1:])

        p, _ = build(
            "n=0 OPEN FILE f('RB','P2:') READ f(p[n]) CLOSE FILE f",
            context=ctx, sleep=feed,
        )
        values = p.run()
        self.assertEqual((delays, values['N']), ([.01], 2))
        self.assertEqual(values['P']['data'], {'TOTAL': 42})
        self.assertEqual(values['P']['nodes'][1]['AMOUNT'], 9)
        self.assertEqual(bank.snapshot()[2]['input'], b'')

    def test_binary_path_ranges_follow_explicit_order(self):
        p, _, ctx = file_program(
            "OPEN FILE f('WB','out') WRITE f(p[0..2]) CLOSE FILE f "
            "INSERT_NODE(q,1,s) INSERT_NODE(q,2,s) INSERT_NODE(q,3,s) q[3].amount=99 "
            "OPEN FILE f('RB','out') READ f(q[0],q[2..1]) CLOSE FILE f",
        )
        values = p.run()
        self.assertEqual(ctx.files.snapshot()['out'], struct.pack('<ii4si4s', 2, 7, b'abcd', 9, b'wxyz'))
        self.assertEqual(values['Q']['data'], {'TOTAL': 2})
        self.assertEqual(values['Q']['nodes'][:2], [
            {'AMOUNT': 9, 'LABEL': 'wxyz'}, {'AMOUNT': 7, 'LABEL': 'abcd'},
        ])
        self.assertEqual(values['Q']['nodes'][2]['AMOUNT'], 99)

    def test_array_cell_selection_and_bounds_evaluated_once(self):
        p, _ = build(
            "INSERT_NODE(routes[1],1,s) INSERT_NODE(routes[1],2,s) "
            "routes[1].total=2 routes[1,1].amount=7 routes[1,1].label='abcd' "
            "routes[1,2].amount=9 routes[1,2].label='wxyz' visits=0 "
            "WRITE(routes[1,first()..last()]::4::0,CR) WRITE(routes[1][(+top)])",
            decl=DECL + ' routes:ARRAY[2] OF PATH NODEDATA=node_t PATHHEADER=header_t',
            prefix=TYPES + ' CONST top=0',
            routines='ROUTINE first:INTEGER BEGIN visits=visits*10+1 RETURN 2 END first '
                     'ROUTINE last:INTEGER BEGIN visits=visits*10+2 RETURN 1 END last',
            seed=False,
        )
        self.assertEqual(p.run()['VISITS'], 12)
        self.assertEqual(text(p), ['   9wxyz   7abcd\n', ' 2'])

    def test_headerless_range_can_start_at_zero(self):
        p, _ = build(
            "INSERT_NODE(p,1,s) p[1].amount=7 p[1].label='abcd' WRITE(p[0..1])",
            decl='p:PATH NODEDATA=node_t s:INTEGER', seed=False,
        )
        p.run()
        self.assertEqual(text(p), [' 7abcd'])

    def test_out_of_bounds_range_has_no_transport_or_format_effects(self):
        routines = 'ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 4 END width'
        for operation, bounds in (('READ', '2..0'), ('WRITE', '1..3')):
            with self.subTest(operation=operation):
                calls = []
                p, _ = build(f'visits=0 {operation}(p[{bounds}]::width())',
                             read=calls.append, write=calls.append, routines=routines)
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'range is outside'):
                    p.run()
                self.assertEqual((p.snapshot()['VISITS'], calls), (0, []))

    def test_headerless_zero_and_nonpath_ranges_are_rejected(self):
        for body, decl in (
            ('WRITE(p[0])', 'p:PATH NODEDATA=node_t'),
            ('READ(n[1..2])', 'n:ARRAY[2] OF INTEGER'),
        ):
            with self.subTest(body=body), self.assertRaises(TranslationError) as error:
                build(body, decl=decl, seed=False)
            self.assertEqual(error.exception.code, 'E_PATH_IO')

    def test_selected_record_replacement_during_budget_fails_before_transport(self):
        p, _ = build('WRITE(p[1..1])', seed=False)
        state = p._state
        path = state.values['P']
        path.append()
        saved = path.nodes[0]
        saved.values.update(AMOUNT=7, LABEL='abcd')
        replacement = rt.Structure(path.node_spec)
        replacement.values.update(AMOUNT=9, LABEL='wxyz')
        tick = state.tick

        def replace(*args, **kwargs):
            tick(*args, **kwargs)
            if state.steps == 2:
                path.nodes[0] = replacement

        with (patch.object(state, 'tick', side_effect=replace),
              self.assertRaisesRegex(rt.KarelRuntimeError, 'PATH I/O storage changed')):
            p.run()
        self.assertIs(path.nodes[0], replacement)
        self.assertEqual(text(p), [])


class PathWriteTests(unittest.TestCase):
    def test_header_then_nodes_follow_declaration_order(self):
        p,_=build('WRITE(p)');p.run();self.assertEqual(text(p),[' 2 7abcd 9wxyz'])
    def test_headerless_paths_write_existing_nodes(self):
        p,_=build("INSERT_NODE(p,1,s) p[1].amount=7 p[1].label='row' WRITE(p)",decl='p:PATH NODEDATA=node_t s:INTEGER',seed=False);p.run();self.assertEqual(text(p),[' 7row'])
    def test_header_only_path_can_write(self):
        p,_=build('p.total=7 WRITE(p)',seed=False);p.run();self.assertEqual(text(p),[' 7'])
    def test_empty_default_path_writes_empty_text(self):
        p,_=build('WRITE(p)',decl='p:PATH',seed=False);p.run();self.assertEqual(text(p),[''])
    def test_empty_path_combines_with_scalar_and_cr(self):
        p,_=build("WRITE('a',p,CR)",decl='p:PATH',seed=False);p.run();self.assertEqual(text(p),['a\n'])
    def test_formatted_empty_path_produces_one_empty_item(self):
        p,_=build('WRITE(p::4)',decl='p:PATH',seed=False)
        p.run();self.assertEqual(text(p),[''])
    def test_uniform_fixed_width_formats_apply_per_leaf(self):
        p,_=build('WRITE(p::4::0)');p.run();self.assertEqual(text(p),['   2   7abcd   9wxyz'])
    def test_named_array_node_fields_are_flattened(self):
        types='TYPE row_t=ARRAY[2]OF INTEGER node_t=STRUCTURE values:row_t ENDSTRUCTURE'
        p,_=build('INSERT_NODE(p,1,s) p[1].values[1]=7 p[1].values[2]=9 WRITE(p)',decl='p:PATH NODEDATA=node_t s:INTEGER',prefix=types,seed=False);p.run();self.assertEqual(text(p),[' 7 9'])
    def test_joint_node_fields_use_axis_order(self):
        types='TYPE node_t=STRUCTURE axes:JOINTPOS2 ENDSTRUCTURE'
        p,_=build('INSERT_NODE(p,1,s) p[1].axes[1]=2 p[1].axes[2]=3 WRITE(p::0::1)',decl='p:PATH NODEDATA=node_t s:INTEGER',prefix=types,seed=False);p.run();self.assertEqual(text(p),[' 2.0 3.0'])
    def test_missing_header_prevents_output(self):
        p,_=build('WRITE(p)',seed=False)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(text(p),[])
    def test_missing_last_node_prevents_all_output(self):
        p,_=build('INSERT_NODE(p,3,s) WRITE(p)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(text(p),[])
    def test_format_effects_follow_detached_value_capture(self):
        routines='ROUTINE width:INTEGER BEGIN p.total=99 p[1].amount=88 RETURN 4 END width'
        p,_=build('WRITE(p::width()::0)',routines=routines);v=p.run();self.assertEqual(text(p),['   2   7abcd   9wxyz']);self.assertEqual((v['P']['data']['TOTAL'],v['P']['nodes'][0]['AMOUNT']),(99,88))
    def test_format_can_delete_node_without_changing_captured_output(self):
        p,_=build('WRITE(p::width()::0)',routines='ROUTINE width:INTEGER BEGIN DELETE_NODE(p,1,s) RETURN 4 END width');v=p.run();self.assertEqual(text(p),['   2   7abcd   9wxyz']);self.assertEqual(len(v['P']['nodes']),1)
    def test_invalid_value_suppresses_format_effects(self):
        p,_=build('visits=0 WRITE(p::width())',seed=False,routines='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 4 END width')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)
    def test_stdout_combined_size_limit_is_retained(self):
        types='TYPE node_t=STRUCTURE label:STRING[254] ENDSTRUCTURE'
        p,_=build("INSERT_NODE(p,1,s) INSERT_NODE(p,2,s) p[1].label='a' p[2].label='b' WRITE(p::200)",decl='p:PATH NODEDATA=node_t s:INTEGER',prefix=types,seed=False)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(text(p),[])
    def test_text_file_formats_share_scalar_layout(self):
        p,_,ctx=file_program("OPEN FILE f('WO','out') WRITE f(p::4::0) CLOSE FILE f");p.run();self.assertEqual(bytes(ctx.files.files['out']),b'   2   7abcd   9wxyz')
    def test_binary_file_uses_scalar_encodings_and_capacities(self):
        p,_,ctx=file_program("OPEN FILE f('WB','out') WRITE f(p) CLOSE FILE f");p.run();self.assertEqual(bytes(ctx.files.files['out']),struct.pack('<ii',2,7)+b'abcd'+struct.pack('<i',9)+b'wxyz')
    def test_empty_binary_path_writes_no_bytes(self):
        p,_,ctx=file_program("OPEN FILE f('WB','out') WRITE f(p) CLOSE FILE f",decl='p:PATH f:FILE',seed=False);p.run();self.assertEqual(bytes(ctx.files.files['out']),b'')
    def test_closed_file_is_still_rejected_for_empty_output(self):
        p,_,_=file_program('WRITE f(p)',decl='p:PATH f:FILE',seed=False)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not open'):p.run()
    def test_borrowed_path_parameter_writes_caller_data(self):
        p,_=build('show(p)',routines='ROUTINE show(v:PATH NODEDATA=node_t PATHHEADER=header_t) BEGIN WRITE(v) END show');p.run();self.assertEqual(text(p),[' 2 7abcd 9wxyz'])
    def test_grouped_source_value_is_supported_for_write(self):
        p,_=build('WRITE((p))');p.run();self.assertEqual(text(p),[' 2 7abcd 9wxyz'])
    def test_dispatcher_and_cooperative_output_parity(self):
        for labelled,coop in ((False,False),(True,False),(False,True)):
            p,_=build(('start:: ' if labelled else '')+'WRITE(p)',cooperative=coop);p.run();self.assertEqual(text(p),[' 2 7abcd 9wxyz'])
    def test_report_records_root_path_item(self):
        _,r=build('WRITE(p)');self.assertEqual(r.report['writes'][0]['items'][0]['data_type'],'PATH');self.assertFalse(r.report['path_io_policy']['controller_validated'])


class PathReadTests(unittest.TestCase):
    def test_callback_reads_header_then_nodes(self):
        p,_=build('READ(p)',values=VALUES);self.assertEqual(p.run()['P'],EXPECTED)
    def test_header_only_read_initializes_missing_leaves(self):
        p,_=build('READ(p)',seed=False,values=[7]);self.assertEqual(p.run()['P']['data'],{'TOTAL':7})
    def test_read_does_not_resize_path(self):
        p,_=build('READ(p)',values=VALUES);v=p.run();self.assertEqual(len(v['P']['nodes']),2)
    def test_empty_headerless_read_is_rejected_before_adapter(self):
        seen=[];p,_=build('READ(p)',decl='p:PATH NODEDATA=node_t',seed=False,read=lambda request:seen.append(request))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'existing header or node'):p.run()
        self.assertEqual(seen,[])
    def test_unknown_byte_fields_can_be_initialized(self):
        p,_=build('INSERT_NODE(p,1,s) READ(p)',prefix='TYPE node_t=STRUCTURE value:BYTE ENDSTRUCTURE',decl='p:PATH NODEDATA=node_t s:INTEGER',seed=False,values=[255]);self.assertEqual(p.run()['P']['nodes'],[{'VALUE':255}])
    def test_short_missing_marker_uses_existing_input_rules(self):
        p,_=build('INSERT_NODE(p,1,s) READ(p)',prefix='TYPE node_t=STRUCTURE value:SHORT ENDSTRUCTURE',decl='p:PATH NODEDATA=node_t s:INTEGER',seed=False,values=[32767]);self.assertEqual(p.run()['P']['nodes'],[{'VALUE':{'uninitialized':True}}])
    def test_string_capacities_are_preserved(self):
        p,_=build('READ(p)',values=[3,17,'longer',19,'text']);self.assertEqual(p.run()['P']['nodes'][0]['LABEL'],'long')
    def test_invalid_last_input_preserves_every_original_leaf(self):
        p,_=build('READ(p)',values=[3,17,'left',True,'rght'])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['P'],{'nodes':[{'AMOUNT':7,'LABEL':'abcd'},{'AMOUNT':9,'LABEL':'wxyz'}],'data':{'TOTAL':2}})
    def test_too_few_inputs_preserve_original_data(self):
        p,_=build('READ(p)',values=[3,17])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['P']['data']['TOTAL'],2)
    def test_missing_node_fields_still_have_shaped_targets(self):
        p,_=build('INSERT_NODE(p,1,s) READ(p)',seed=False,values=[3,17,'left']);self.assertEqual(p.run()['P'],{'nodes':[{'AMOUNT':17,'LABEL':'left'}],'data':{'TOTAL':3}})
    def test_read_with_cr_and_later_scalar_uses_expanded_offsets(self):
        p,_=build('READ(p,CR,n)',values=VALUES+[99]);v=p.run();self.assertEqual(v['N'],99);self.assertEqual(p.read_requests[0]['line_breaks'],[5])
    def test_uniform_read_formats_are_captured_per_scalar(self):
        p,_=build('READ(p::4::0)',values=VALUES);self.assertEqual(p.run()['P'],EXPECTED);self.assertEqual(len(p.read_requests[0]['targets']),5)
    def test_format_effects_run_once_after_capture(self):
        p,_=build('visits=0 READ(p::width())',values=VALUES,routines='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 0 END width');self.assertEqual((p.run()['VISITS'],p.snapshot()['P']),(1,EXPECTED))
    def test_deleted_node_does_not_retarget_captured_cells(self):
        p,_=build('READ(p::width())',values=VALUES,routines='ROUTINE width:INTEGER BEGIN DELETE_NODE(p,1,s) RETURN 0 END width');v=p.run();self.assertEqual(v['P']['nodes'],[{'AMOUNT':19,'LABEL':'rght'}])
    def test_root_and_descendant_alias_follow_input_order(self):
        p,_=build('READ(p,p[1].amount)',values=VALUES+[99]);self.assertEqual(p.run()['P']['nodes'][0]['AMOUNT'],99)
    def test_node_xyzwpr_pose_can_be_read(self):
        values=[1.,2.,3.,0.,0.,0.,0,0,0,False,False,False,False]
        p,_=build('INSERT_NODE(p,1,s) READ(p)',prefix='TYPE node_t=STRUCTURE node_pos:XYZWPR ENDSTRUCTURE',decl='p:PATH NODEDATA=node_t s:INTEGER',seed=False,values=values);v=p.run();self.assertEqual(v['P']['nodes'][0]['NODE_POS']['X'],1.)
    def test_joint_node_fields_read_in_axis_order(self):
        p,_=build('INSERT_NODE(p,1,s) READ(p)',prefix='TYPE node_t=STRUCTURE axes:JOINTPOS2 ENDSTRUCTURE',decl='p:PATH NODEDATA=node_t s:INTEGER',seed=False,values=[2.,3.]);self.assertEqual(p.run()['P']['nodes'][0]['AXES'],{'axes':[2.,3.]})
    def test_config_domain_failure_is_atomic(self):
        p,_=build("INSERT_NODE(p,1,s) READ(p)",prefix='TYPE node_t=STRUCTURE cfg:CONFIG ENDSTRUCTURE',decl='p:PATH NODEDATA=node_t s:INTEGER',seed=False,values=[0,0,8,False,False,False,False])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['P']['nodes'][0]['CFG']['CFG_TURN_NO1'],{'uninitialized':True})
    def test_binary_roundtrip_into_existing_nodes(self):
        body="OPEN FILE f('WB','out') WRITE f(p) CLOSE FILE f INSERT_NODE(q,1,s) INSERT_NODE(q,2,s) OPEN FILE f('RB','out') READ f(q) CLOSE FILE f"
        p,_,ctx=file_program(body);v=p.run();self.assertEqual(v['Q'],v['P']);self.assertEqual(len(ctx.files.files['out']),20)
    def test_fixed_width_text_roundtrip(self):
        body="OPEN FILE f('WO','out') WRITE f(p::4::0) CLOSE FILE f INSERT_NODE(q,1,s) INSERT_NODE(q,2,s) OPEN FILE f('RO','out') READ f(q::4::0) CLOSE FILE f"
        p,_,_=file_program(body);v=p.run();self.assertEqual(v['Q'],v['P'])
    def test_truncated_binary_input_restores_cursor_and_data(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'input':struct.pack('<ii',3,17)}));p,_,_=file_program("OPEN FILE f('RB','input') READ f(p)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.values['F'].position,0);self.assertEqual(p.snapshot()['P']['data']['TOTAL'],2)
    def test_borrowed_path_parameter_keeps_caller_cells(self):
        p,_=build('fill(p)',values=VALUES,routines='ROUTINE fill(v:PATH NODEDATA=node_t PATHHEADER=header_t) BEGIN READ(v) END fill');self.assertEqual(p.run()['P'],EXPECTED)
    def test_dispatcher_and_cooperative_input_parity(self):
        for labelled,coop in ((False,False),(True,False),(False,True)):
            p,_=build(('start:: ' if labelled else '')+'READ(p)',values=VALUES,cooperative=coop);self.assertEqual(p.run()['P'],EXPECTED)
    def test_report_records_path_destination(self):
        _,r=build('READ(p)');self.assertEqual(r.report['reads'][0]['destinations'][0]['type_spec'][0],'PATH')


class PathIOGuardTests(unittest.TestCase):
    def test_oversized_path_rejected_before_formats_or_input(self):
        types='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        for operation in ('READ','WRITE'):
            calls=[];p,_=build(operation+'(p)',prefix=types,decl='p:PATH NODEDATA=node_t',seed=False,read=lambda request:calls.append(request))
            value=p._state.values['P']
            for _ in range(1025):value.append()
            with self.subTest(operation=operation),self.assertRaisesRegex(rt.KarelRuntimeError,'1024'):p.run()
            self.assertEqual(calls,[])
    def test_exactly_1024_fields_can_be_read(self):
        p,_=build('READ(p)',prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE',decl='p:PATH NODEDATA=node_t',seed=False,values=list(range(1024)))
        for _ in range(1024):p._state.values['P'].append()
        self.assertEqual(p.run()['P']['nodes'][-1]['AMOUNT'],1023)
    def test_malformed_node_container_is_rejected(self):
        p,_=build('READ(p)',seed=False,values=[7]);p._state.values['P'].nodes=()
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_node_schema_is_rejected(self):
        p,_=build('READ(p)',values=VALUES);p._state.values['P'].nodes=[rt.Structure(('VECTOR',))]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_header_is_rejected(self):
        p,_=build('READ(p)',values=VALUES);p._state.values['P'].data=rt.Structure(('VECTOR',))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_unexpected_header_is_rejected(self):
        p,_=build('WRITE(p)',decl='p:PATH',seed=False);p._state.values['P'].data=rt.Structure(('VECTOR',))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_position_orientation_input_inside_path_remains_excluded(self):
        with self.assertRaises(TranslationError):build('READ(p[1].point.normal)',prefix='TYPE node_t=STRUCTURE point:POSITION ENDSTRUCTURE',decl='p:PATH NODEDATA=node_t',seed=False)
    def test_nested_path_schema_does_not_become_data_output(self):
        bad=('STRUCTURE','NESTED',(('VALUE',('PATH',None,None)),));self.assertFalse(rt.aggregate_write_type(bad));self.assertFalse(rt.aggregate_read_type(('ARRAY',2,('FILE',))))
    def test_unknown_byte_cannot_be_written(self):
        p,_=build('INSERT_NODE(p,1,s) WRITE(p)',prefix='TYPE node_t=STRUCTURE amount:BYTE ENDSTRUCTURE',decl='p:PATH NODEDATA=node_t s:INTEGER',seed=False)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(text(p),[])
    def test_direct_helpers_reject_malformed_schemas(self):
        for spec in (('PATH',False,None),('PATH',(),None),('PATH',None,('INTEGER',)),('PATH',None)):
            with self.subTest(spec=spec),self.assertRaises(rt.KarelRuntimeError):rt.path_io_components(spec)
    def test_path_subclasses_are_not_accepted_as_storage(self):
        class Derived(rt.PathValue):pass
        p,_=build('WRITE(p)',decl='p:PATH',seed=False);p._state.values['P']=Derived(('PATH',None,None))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_existing_generic_empty_array_capture_guard_remains(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.format_aggregate_write(rt._AggregateWriteValue(('ARRAY',1,rt.INTEGER),[]))
    def test_readonly_root_reference_is_rejected(self):
        p,_=build('');p.run();value=p._state.values['P'];ref=rt.ReadOnlyFieldReference(value.spec,{'value':value},'value')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.capture_aggregate_read_target(ref,[])
    def test_context_json_contains_data_and_no_capture_objects(self):
        p,_=build('READ(p)',values=VALUES);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));again=rt.ExecutionContext.from_config(saved);self.assertEqual(again.to_config(),saved)
