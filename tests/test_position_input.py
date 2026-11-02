"""Authored complete POSITION input, geometry admission and captured transports."""
from copy import deepcopy
import json
import math
import struct
import unittest
from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_file_cancellation import serial, pending
from tests.test_pipe_attributes import bank as pipe_bank
from tests.test_keyboard import context as keyboard_context
from tests.test_keyboard_file_read import line_keys

VALUES=[1.,0.,0.,0.,1.,0.,0.,0.,1.,10.,20.,30.,0,0,0,False,False,False,False]
EXPECTED={'NORMAL':{'X':1.,'Y':0.,'Z':0.},'ORIENT':{'X':0.,'Y':1.,'Z':0.},'APPROACH':{'X':0.,'Y':0.,'Z':1.},'LOCATION':{'X':10.,'Y':20.,'Z':30.},'CONFIG_DATA':{'CFG_TURN_NO1':0,'CFG_TURN_NO2':0,'CFG_TURN_NO3':0,'CFG_FLIP':False,'CFG_LEFT':False,'CFG_UP':False,'CFG_FRONT':False}}
DECL='p,q:POSITION cfg:CONFIG n,s,visits:INTEGER f:FILE'
SEED="CNV_STR_CONF('N',cfg,s) p=POS(3,4,5,0,0,0,cfg) "


def text(values=VALUES):return ' '.join('TRUE' if v is True else 'FALSE' if v is False else str(v) for v in values)

def packed(values=VALUES,endian='<'):return struct.pack(endian+'12f3i4?',*values)

def build(body='READ(p)',*,values=None,read=None,decl=DECL,**options):
    if values is not None:read=lambda request:list(values)
    return compile_program(body,decl=decl,read=read,**options)

def file_input(data,*,binary=True,reverse=False,body='READ f(p)',prefix='',**options):
    ctx=rt.ExecutionContext(files=rt.MemoryFiles({'pose':data}))
    source=prefix+("SET_FILE_ATR(f,ATR_REVERSE,1) " if reverse else '')+"OPEN FILE f('"+('RB' if binary else 'RO')+"','pose') "+body
    p,r=build(source,context=ctx,**options)
    return p,r,ctx

def captures():
    value=rt.Structure(('POSITION',))
    fields=rt.capture_aggregate_read_target(rt.Reference(('POSITION',),{'P':value},'P'),[],7)
    return value,[r for r,_ in fields]


class PositionInputValueTests(unittest.TestCase):
    def test_whole_position_accepts_declared_missing_scalar_leaves(self):
        p,_=build(values=VALUES);self.assertEqual(p.run()['P'],EXPECTED)

    def test_existing_position_updates_in_place(self):
        held=[]
        def read(_):held.append(p._state.values['P']);return VALUES
        p,_=build(SEED+'READ(p)',read=read);p.run()
        self.assertIs(p._state.values['P'],held[0]);self.assertEqual(p.snapshot()['P'],EXPECTED)

    def test_orientation_vectors_remain_read_only_after_input(self):
        p,_=build(values=VALUES);p.run()
        for name in ('NORMAL','ORIENT','APPROACH'):self.assertTrue(p._state.values['P'].values[name].read_only)
        self.assertFalse(p._state.values['P'].values['LOCATION'].read_only)

    def test_rotation_columns_follow_existing_write_order(self):
        values=[0.,1.,0.,-1.,0.,0.,0.,0.,1.,10.,20.,30.,0,0,0,False,False,False,False]
        p,_=build(values=values);v=p.run()['P'];self.assertEqual(v['NORMAL'],dict(X=0.,Y=1.,Z=0.));self.assertEqual(v['ORIENT'],dict(X=-1.,Y=0.,Z=0.))

    def test_config_turns_and_flags_follow_scalar_domains(self):
        vals=VALUES[:12]+[-8,0,7,True,False,True,False]
        p,_=build(values=vals);self.assertEqual(list(p.run()['P']['CONFIG_DATA'].values()),vals[12:])

    def test_multiple_positions_and_scalar_fields_share_one_request(self):
        p,_=build('READ(n,p,q,s)',values=[7,*VALUES,*VALUES,9]);v=p.run()
        self.assertEqual((v['N'],v['P'],v['Q'],v['S']),(7,EXPECTED,EXPECTED,9))

    def test_position_arrays_read_row_major(self):
        p,_=build('READ(a)',decl='a:ARRAY[2]OF POSITION',values=VALUES*2)
        self.assertEqual(p.run()['A'],[EXPECTED,EXPECTED])

    def test_nested_named_array_storage(self):
        prefix='TYPE row_t=ARRAY[2]OF POSITION'
        p,_=build('READ(a)',prefix=prefix,decl='a:ARRAY[1]OF row_t',values=VALUES*2)
        self.assertEqual(p.run()['A'],[[EXPECTED,EXPECTED]])

    def test_record_positions_and_ordinary_siblings(self):
        prefix='TYPE packet_t=STRUCTURE before:INTEGER pose:POSITION after:INTEGER ENDSTRUCTURE'
        p,_=build('READ(packet)',prefix=prefix,decl='packet:packet_t',values=[7,*VALUES,9])
        self.assertEqual(p.run()['PACKET'],dict(BEFORE=7,POSE=EXPECTED,AFTER=9))

    def test_array_prefix_writes_only_captured_row(self):
        p,_=build('READ(m[2])',decl='m:ARRAY[2,2]OF POSITION',values=VALUES*2);v=p.run()['M']
        self.assertEqual(v[1],[EXPECTED,EXPECTED]);self.assertTrue(v[0][0]['NORMAL']['X']['uninitialized'])

    def test_exact_borrowed_routine_input_updates_caller(self):
        routines='ROUTINE fill(item:POSITION) BEGIN READ(item) END fill'
        p,_=build('fill(p)',routines=routines,values=VALUES);self.assertEqual(p.run()['P'],EXPECTED)

    def test_generic_array_formal_inherits_actual_position_shape(self):
        routines='ROUTINE fill(items:ARRAY OF POSITION) BEGIN READ(items) END fill'
        p,_=build('fill(a)',decl='a:ARRAY[2]OF POSITION',routines=routines,values=VALUES*2)
        self.assertEqual(p.run()['A'],[EXPECTED,EXPECTED])

    def test_default_path_nodes_can_receive_position_data(self):
        p,_=build('APPEND_NODE(route,s) READ(route)',decl='route:PATH s:INTEGER',values=VALUES)
        self.assertEqual(p.run()['ROUTE']['nodes'][0]['NODE_POS'],EXPECTED)

    def test_custom_path_header_and_node_positions(self):
        prefix='TYPE node_t=STRUCTURE pose:POSITION ENDSTRUCTURE head_t=STRUCTURE home:POSITION ENDSTRUCTURE'
        p,_=build('APPEND_NODE(route,s) READ(route)',prefix=prefix,decl='route:PATH NODEDATA=node_t PATHHEADER=head_t s:INTEGER',values=VALUES*2)
        v=p.run()['ROUTE'];self.assertEqual(v['data']['HOME'],EXPECTED);self.assertEqual(v['nodes'][0]['POSE'],EXPECTED)

    def test_direct_path_position_destination(self):
        p,_=build('APPEND_NODE(route,s) READ(route[1].node_pos)',decl='route:PATH s:INTEGER',values=VALUES)
        self.assertEqual(p.run()['ROUTE']['nodes'][0]['NODE_POS'],EXPECTED)

    def test_empty_default_path_rejects_before_callback(self):
        calls=[];p,_=build('READ(route)',decl='route:PATH',read=lambda _:calls.append(1) or VALUES)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_input_can_be_consumed_by_existing_geometry(self):
        p,_=build('READ(p) q=INV(p) n=ROUND(q.location.x)',values=VALUES)
        self.assertEqual(p.run()['N'],-10)

    def test_normalized_input_is_valid_for_frame_composition(self):
        vals=VALUES[:];vals[0]=1.+2e-7
        p,_=build('READ(p) q=p:p',values=vals);v=p.run()['Q']
        self.assertEqual(v['LOCATION'],dict(X=20.,Y=40.,Z=60.))

    def test_completed_position_context_json_roundtrip(self):
        p,_=build(values=VALUES);p.run();saved=json.loads(json.dumps(p._state.execution.to_config(),allow_nan=False))
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_linked_routine_uses_same_whole_position_input(self):
        main='PROGRAM MAIN VAR p:POSITION ROUTINE fill(item:POSITION) FROM LIB BEGIN fill(p) END MAIN'
        lib='PROGRAM LIB ROUTINE fill(item:POSITION) BEGIN READ(item) END fill BEGIN END LIB'
        instance=translate_project({'main.kl':main,'lib.kl':lib}).instantiate(options=dict(read=lambda _:VALUES))
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['P'],EXPECTED)


class PositionInputCaptureTests(unittest.TestCase):
    def test_later_destination_selector_does_not_retarget_position(self):
        routines='ROUTINE select_slot:INTEGER BEGIN slot=2 RETURN 1 END select_slot'
        p,_=build('slot=1 READ(poses[slot],numbers[select_slot()])',routines=routines,decl='poses:ARRAY[2]OF POSITION numbers:ARRAY[1]OF INTEGER slot:INTEGER',values=[*VALUES,9])
        v=p.run();self.assertEqual(v['POSES'][0],EXPECTED);self.assertEqual((v['SLOT'],v['NUMBERS']), (2,[9]))

    def test_replacing_root_in_callback_keeps_original_captured_cells(self):
        held=[]
        def read(_):
            held.append(p._state.values['P']);p._state.values['P']=rt.Structure(('POSITION',));return VALUES
        p,_=build(read=read);p.run()
        self.assertEqual(rt.snapshot_value(held[0]),EXPECTED);self.assertTrue(p.snapshot()['P']['NORMAL']['X']['uninitialized'])

    def test_replacing_nested_vector_keeps_original_vector_alias(self):
        held=[]
        def read(_):
            held.append(p._state.values['P'].values['NORMAL']);p._state.values['P'].values['NORMAL']=rt.Structure(('VECTOR',));return VALUES
        p,_=build(read=read);p.run();self.assertEqual(rt.snapshot_value(held[0]),EXPECTED['NORMAL'])
        self.assertTrue(p.snapshot()['P']['NORMAL']['X']['uninitialized'])

    def test_later_path_deletion_keeps_original_captured_node(self):
        def read(_):return [*VALUES,9]
        routines='ROUTINE change:INTEGER BEGIN DELETE_NODE(route,1,s) RETURN 1 END change'
        p,_=build('APPEND_NODE(route,s) READ(route,nums[change()])',decl='route:PATH nums:ARRAY[1]OF INTEGER s:INTEGER',routines=routines,read=read)
        # Retain the original node at the checkpoint before its deletion.
        node=[]
        from unittest.mock import patch
        native=rt._capture_position_read
        def capture(value,line=None):node.append(value);return native(value,line)
        with patch.object(rt,'_capture_position_read',capture):v=p.run()
        self.assertEqual(v['ROUTE']['nodes'],[]);self.assertEqual(rt.snapshot_value(node[0]),EXPECTED);self.assertEqual(v['NUMS'],[9])

    def test_repeated_whole_position_input_uses_source_order(self):
        vals=VALUES[:];vals[9]=99.
        p,_=build('READ(p,p)',values=[*VALUES,*vals]);self.assertEqual(p.run()['P']['LOCATION']['X'],99.)

    def test_source_callback_effects_survive_later_geometry_failure(self):
        bad=VALUES[:];bad[0]=2.
        def read(_):p._state.values['N']=8;return bad
        p,_=build('n=7 READ(p)',read=read)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],8)

    def test_callback_metadata_cannot_modify_captured_targets(self):
        def read(request):request['targets'][0]['type_spec']=('BOOLEAN',);return VALUES
        p,_=build(read=read);self.assertEqual(p.run()['P'],EXPECTED)

    def test_pause_during_later_format_retains_position_capture(self):
        routines='ROUTINE width:INTEGER BEGIN visits=visits+1 PAUSE RETURN 1 END width'
        p,_=build('visits=0 READ(p,n::width())',values=[*VALUES,7],routines=routines,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['P'],EXPECTED);self.assertEqual(p.snapshot()['VISITS'],1)

    def test_cr_offsets_follow_complete_position(self):
        observed=[]
        def read(request):observed.append(request);return [*VALUES,7]
        p,_=build('READ(p,CR,n)',read=read);p.run();self.assertEqual(observed[0]['line_breaks'],[19])
        self.assertEqual([r['type'] for r in observed[0]['targets']],['REAL']*12+['INTEGER']*3+['BOOLEAN']*4+['INTEGER'])

    def test_uniform_width_text_input(self):
        data=''.join(str(v).upper().rjust(8) for v in VALUES)
        p,_=build('READ(p::8)',read=rt.TextInput(data));self.assertEqual(p.run()['P'],EXPECTED)

    def test_successful_typed_read_observation_remains_plain_data(self):
        p,_=build(values=VALUES);p.run();record=p.read_requests[0]
        self.assertEqual(record['adapter_outcome'],'callback_completed');json.dumps(record,allow_nan=False)

    def test_missing_nested_container_rejects_before_callback(self):
        calls=[];p,_=build(read=lambda _:calls.append(True) or VALUES)
        p._state.values['P'].values['NORMAL']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_request_field_limit_counts_every_position_leaf(self):
        p,_=build('READ(a)',decl='a:ARRAY[54]OF POSITION',values=VALUES*54)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'1024'):p.run()
        self.assertEqual(p.read_requests,())


class PositionInputGeometryTests(unittest.TestCase):
    def reject_values(self,values):
        p,_=build(SEED+'n=7 READ(n,p)',values=[9,*values])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],7);self.assertEqual(p.snapshot()['P']['LOCATION'],dict(X=3.,Y=4.,Z=5.))
        self.assertEqual(p.read_requests[-1]['adapter_outcome'],'callback_result_rejected')

    def test_non_unit_column_rejects_entire_batch(self):
        vals=VALUES[:];vals[0]=2.;self.reject_values(vals)

    def test_nonorthogonal_columns_reject_entire_batch(self):
        vals=VALUES[:];vals[3:6]=[1.,0.,0.];self.reject_values(vals)

    def test_reflection_rejects_entire_batch(self):
        vals=VALUES[:];vals[8]=-1.;self.reject_values(vals)

    def test_degenerate_zero_columns_reject(self):
        vals=VALUES[:];vals[:9]=[0.]*9;self.reject_values(vals)

    def test_large_matrix_errors_are_not_repaired(self):
        vals=VALUES[:];vals[0]=1.00001;self.reject_values(vals)

    def test_small_transport_roundoff_is_normalized(self):
        vals=VALUES[:];vals[0]=1.0000002;vals[3]=1e-8
        p,_=build(values=vals);self.assertEqual(p.run()['P'],EXPECTED)

    def test_single_precision_rotated_matrix_becomes_proper_rotation(self):
        a=struct.unpack('<f',struct.pack('<f',math.sqrt(.5)))[0]
        vals=VALUES[:];vals[:9]=[a,a,0.,-a,a,0.,0.,0.,1.]
        p,_=build('READ(p) q=p:p',values=vals);p.run()
        self.assertAlmostEqual(p.snapshot()['P']['NORMAL']['X'],math.sqrt(.5),places=14)
        with rt._numeric_scope('pythonic'):self.assertAlmostEqual(rt._frame_parts(p._state.values['P'])[0][2][2],1.,places=14)

    def test_nan_and_infinite_fields_reject(self):
        for value in (float('nan'),float('inf'),float('-inf')):
            vals=VALUES[:];vals[9]=value;self.reject_values(vals)

    def test_boolean_cannot_supply_matrix_number(self):
        vals=VALUES[:];vals[0]=True;self.reject_values(vals)

    def test_string_cannot_supply_matrix_number(self):
        vals=VALUES[:];vals[0]='1';self.reject_values(vals)

    def test_real_cannot_supply_config_turn(self):
        vals=VALUES[:];vals[12]=1.;self.reject_values(vals)

    def test_config_turn_out_of_range_rejects_entire_batch(self):
        for value in (-9,8):
            vals=VALUES[:];vals[12]=value;self.reject_values(vals)

    def test_numeric_truthiness_cannot_supply_config_flag(self):
        vals=VALUES[:];vals[15]=1;self.reject_values(vals)

    def test_short_or_long_response_does_not_publish(self):
        for vals in (VALUES[:-1],VALUES+[0]):
            p,_=build(SEED+'READ(p)',values=vals)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['P']['LOCATION']['X'],3.)

    def test_invalid_later_position_keeps_earlier_position_unchanged(self):
        bad=VALUES[:];bad[0]=2.
        p,_=build(SEED+'READ(p,q)',values=[*VALUES,*bad])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['P']['LOCATION']['X'],3.)

    def test_exact_text_adapter_rolls_back_after_geometry_rejection(self):
        vals=VALUES[:];vals[0]=2.;reader=rt.TextInput(text(vals));before=reader.position
        p,_=build(read=reader)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(reader.position,before);self.assertEqual(reader.offset,0)

    def test_exact_text_adapter_rolls_back_after_parse_failure(self):
        reader=rt.TextInput('1 0 BAD')
        p,_=build(read=reader)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(reader.offset,0)

    def test_geometry_failure_restores_current_text_cursor_not_initial_cursor(self):
        bad=VALUES[:];bad[0]=2.;reader=rt.TextInput(text()+' '+text(bad))
        p,_=build('READ(p) READ(q)',read=reader)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['P'],EXPECTED);self.assertEqual(reader.offset,len(text()))


class PositionInputTransportTests(unittest.TestCase):
    def test_binary_input_uses_twelve_reals_three_integers_four_flags(self):
        p,_,_=file_input(packed());self.assertEqual(p.run()['P'],EXPECTED);self.assertEqual(p._state.values['F'].position,64)

    def test_reverse_binary_byte_order(self):
        p,_,_=file_input(packed(endian='>'),reverse=True);self.assertEqual(p.run()['P'],EXPECTED)

    def test_binary_roundtrip_matches_existing_write_layout(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles())
        p,_=build(SEED+"OPEN FILE f('WB','pose') WRITE f(p) CLOSE FILE f OPEN FILE f('RB','pose') READ f(q) CLOSE FILE f",context=ctx)
        v=p.run();self.assertEqual(v['P'],v['Q']);self.assertEqual(len(ctx.files.snapshot()['pose']),64)

    def test_binary_rotated_matrix_roundtrip_tolerates_float32_rounding(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles())
        source="CNV_STR_CONF('N',cfg,s) p=POS(3,4,5,0,0,45,cfg) OPEN FILE f('WB','pose') WRITE f(p) CLOSE FILE f OPEN FILE f('RB','pose') READ f(q) CLOSE FILE f"
        p,_=build(source,context=ctx);p.run();self.assertAlmostEqual(p.snapshot()['Q']['NORMAL']['X'],math.sqrt(.5),places=14)
        with rt._numeric_scope('pythonic'):rt._frame_parts(p._state.values['Q'])

    def test_text_file_input(self):
        p,_,_=file_input(text(),binary=False);self.assertEqual(p.run()['P'],EXPECTED)

    def test_invalid_binary_geometry_rolls_back_cursor_and_all_outputs(self):
        vals=VALUES[:];vals[8]=-1.;p,_,_=file_input(packed(vals),prefix=SEED)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p._state.values['F'].position,p._state.values['F'].status),(0,1));self.assertEqual(p.snapshot()['P']['LOCATION']['X'],3.)

    def test_incomplete_binary_pose_rolls_back_cursor(self):
        p,_,_=file_input(packed()[:-1])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.values['F'].position,0)

    def test_invalid_text_geometry_keeps_file_cursor(self):
        vals=VALUES[:];vals[0]=2.;p,_,_=file_input(text(vals),binary=False)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.values['F'].position,0)

    def test_waiting_serial_input_uses_complete_pose(self):
        bank,ctx=serial(b'1 ')
        def sleeper(_):bank.feed(2,(text(VALUES[1:])+'\n').encode())
        p,_=build("OPEN FILE f('RO','P2:') READ f(p,CR) CLOSE FILE f",context=ctx,sleep=sleeper)
        self.assertEqual(p.run()['P'],EXPECTED);self.assertEqual(bank._pending,{})

    def test_waiting_binary_serial_input_normalizes_once(self):
        bank,ctx=serial(packed()[:4]);calls=[]
        def sleeper(_):calls.append(1);bank.feed(2,packed()[4:])
        p,_=build("OPEN FILE f('RB','P2:') READ f(p) CLOSE FILE f",context=ctx,sleep=sleeper)
        self.assertEqual(p.run()['P'],EXPECTED);self.assertEqual(calls,[1])

    def test_waiting_pipe_input_uses_same_capture(self):
        bank=pipe_bank(b'1 ');ctx=rt.ExecutionContext(file_pipes=bank)
        def sleeper(_):bank.feed('LOG',(text(VALUES[1:])+'\n').encode())
        p,_=build("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') READ f(p,CR) CLOSE FILE f",context=ctx,sleep=sleeper)
        self.assertEqual(p.run()['P'],EXPECTED);self.assertEqual(bank._reads,{})

    def test_keyboard_line_input_uses_same_pose_validation(self):
        ctx=keyboard_context(keys=line_keys(text()))
        p,_=build("OPEN FILE f('RW','KB:TPKB') READ f(p,CR) CLOSE FILE f",context=ctx,sleep=lambda _:None)
        self.assertEqual(p.run()['P'],EXPECTED)

    def test_invalid_keyboard_pose_keeps_destinations_and_pending_text(self):
        vals=VALUES[:];vals[0]=2.;ctx=keyboard_context(keys=line_keys(text(vals)))
        p,_=build(SEED+"OPEN FILE f('RW','KB:TPKB') READ f(p,CR)",context=ctx,sleep=lambda _:None)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['P']['LOCATION']['X'],3.);self.assertEqual(p._state.values['F'].position,0)

    def test_serial_cancellation_keeps_complete_earlier_input_fields(self):
        bank,ctx=serial(packed()[:48])
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build(SEED+"OPEN FILE f('RB','P2:') READ f(p) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper)
        self.assertEqual((p.run()['P']['LOCATION']['X'],p.snapshot()['S']),(3.,6));self.assertEqual(bank.snapshot()[2]['input'],packed()[:48])

    def test_pipe_cancellation_keeps_position_and_input_prefix(self):
        bank=pipe_bank(b'1 ');ctx=rt.ExecutionContext(file_pipes=bank)
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build(SEED+"SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') READ f(p,CR) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper)
        self.assertEqual((p.run()['P']['LOCATION']['X'],p.snapshot()['S']),(3.,6));self.assertEqual(bank._reads,{})

    def test_invalid_serial_geometry_preserves_cursor_and_cleans_pending_input(self):
        vals=VALUES[:];vals[0]=2.;bank,ctx=serial((text(vals)+'\n').encode())
        p,_=build(SEED+"OPEN FILE f('RO','P2:') READ f(p,CR)",context=ctx,sleep=lambda _:None)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['P']['LOCATION']['X'],p._state.values['F'].position),(3.,0));self.assertEqual(bank._pending,{})

    def test_invalid_binary_serial_geometry_preserves_all_input(self):
        vals=VALUES[:];vals[8]=-1.;bank,ctx=serial(packed(vals))
        p,_=build(SEED+"OPEN FILE f('RB','P2:') READ f(p)",context=ctx,sleep=lambda _:None)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.values['F'].position,0);self.assertEqual(bank.snapshot()[2]['input'],packed(vals))

    def test_invalid_pipe_geometry_preserves_cursor_and_cleans_pending_input(self):
        vals=VALUES[:];vals[0]=2.;bank=pipe_bank((text(vals)+'\n').encode());ctx=rt.ExecutionContext(file_pipes=bank)
        p,_=build(SEED+"SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') READ f(p,CR)",context=ctx,sleep=lambda _:None)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['P']['LOCATION']['X'],p._state.values['F'].position),(3.,0));self.assertEqual(bank._reads,{})

    def test_binary_pipe_input_uses_whole_position_validation(self):
        bank=pipe_bank(packed());ctx=rt.ExecutionContext(file_pipes=bank)
        p,_=build("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RB','PIP:LOG') READ f(p) CLOSE FILE f",context=ctx,sleep=lambda _:None)
        self.assertEqual(p.run()['P'],EXPECTED)

    def test_scheduler_stop_cleans_pending_pose_input(self):
        bank,ctx=serial(b'1 ')
        project,task,handle=pending(ctx,"OPEN FILE f('RO','P2:') READ f(p,CR)",decl='p:POSITION f:FILE')
        project.scheduler.stop('MAIN');self.assertIsNone(handle._read_operation);self.assertEqual(bank._pending,{})


class PositionInputGuardTests(unittest.TestCase):
    def test_direct_orientation_input_stays_blocked(self):
        for target in ('p.normal','p.orient.x','p.approach'):
            with self.assertRaises(TranslationError):build('READ('+target+')')

    def test_direct_orientation_assignment_stays_blocked(self):
        with self.assertRaises(TranslationError):build('p.normal.x=1')

    def test_orientation_reference_arguments_stay_blocked(self):
        with self.assertRaises(TranslationError):build('use(p.normal)',routines='ROUTINE use(v:VECTOR) BEGIN READ(v) END use')

    def test_legacy_whole_position_input_stays_blocked(self):
        with self.assertRaises(TranslationError):translate('PROGRAM T VAR p:POSITION BEGIN READ(p) END T',mode='legacy')

    def test_incomplete_cohort_rejects_before_callback(self):
        with rt._numeric_scope('pythonic'):
            _,targets=captures();calls=[];p,_=build(read=lambda _:calls.append(True) or VALUES)
            with self.assertRaises(rt.KarelRuntimeError):p._state.read_items(targets[:-1],7)
            self.assertEqual(calls,[])

    def test_reordered_or_duplicated_cohorts_reject_before_callback(self):
        with rt._numeric_scope('pythonic'):
            _,targets=captures()
            for data in ([targets[1],targets[0],*targets[2:]],[*targets[:-1],targets[0]]):
                calls=[];p,_=build(read=lambda _:calls.append(True) or VALUES)
                with self.assertRaises(rt.KarelRuntimeError):p._state.read_items(data,7)
                self.assertEqual(calls,[])

    def test_scalar_cannot_split_a_cohort(self):
        with rt._numeric_scope('pythonic'):
            _,targets=captures();data=targets[:9]+[rt.Reference(('INTEGER',),{'N':0},'N')]+targets[9:]
            with self.assertRaises(rt.KarelRuntimeError):rt._validate_read_targets(data,7)

    def test_capture_detects_later_shape_change(self):
        with rt._numeric_scope('pythonic'):
            value,targets=captures();del value.values['NORMAL'].values['Z']
            with self.assertRaises(rt.KarelRuntimeError):rt._validate_read_targets(targets,7)

    def test_capture_detects_retargeted_field_key(self):
        with rt._numeric_scope('pythonic'):
            _,targets=captures();targets[0].base.key='Y'
            with self.assertRaises(rt.KarelRuntimeError):rt._validate_read_targets(targets,7)

    def test_capture_requires_exact_scalar_schema(self):
        with rt._numeric_scope('pythonic'):
            _,targets=captures();targets[0].base.spec=('BOOLEAN',)
            with self.assertRaises(rt.KarelRuntimeError):rt._validate_read_targets(targets,7)

    def test_direct_preparation_requires_full_response(self):
        with rt._numeric_scope('pythonic'):
            _,targets=captures()
            with self.assertRaises(rt.KarelRuntimeError):rt._prepare_read_values(targets,VALUES[:-1],7)

    def test_report_exposes_input_tolerance_and_evidence_boundary(self):
        _,r=build(values=VALUES);policy=r.report['position_input_policy']
        self.assertIn('1e-6',policy['validation']);self.assertIn('19',policy['order']);self.assertFalse(policy['controller_validated'])
        self.assertEqual(policy['guide'],'docs/position-input.md')


if __name__=='__main__':unittest.main()
