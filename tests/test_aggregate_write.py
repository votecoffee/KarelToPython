"""Authored whole-data WRITE capture, publication and scalar FILE layouts."""
import json
import struct
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_pipe_attributes import bank as pipe_bank
from tests.test_keyboard import context as keyboard_context

PREFIX='TYPE item_t=STRUCTURE value:INTEGER label:STRING[4] ENDSTRUCTURE'
DECL='a,b:ARRAY[2]OF INTEGER item:item_t n,s,visits:INTEGER f:FILE'


def build(body='a[1]=7 a[2]=9 WRITE(a)',*,decl=DECL,prefix=PREFIX,**options):return compile_program(body,decl=decl,prefix=prefix,**options)
def texts(p):return [row['text'] for row in p.write_requests]

def memory(body,*,initial=None,**options):
    ctx=rt.ExecutionContext(files=rt.MemoryFiles({} if initial is None else initial));p,r=build(body,context=ctx,**options);return p,ctx,r


class AggregateWriteValueTests(unittest.TestCase):
    def test_integer_array_renders_scalar_defaults_in_one_request(self):
        p,_=build();p.run();self.assertEqual(texts(p),[' 7 9'])

    def test_array_of_strings_adds_no_extra_separator(self):
        p,_=build("a[1]='one' a[2]='two' WRITE(a)",decl='a:ARRAY[2]OF STRING[4]');p.run();self.assertEqual(texts(p),['onetwo'])

    def test_record_renders_declaration_field_order(self):
        p,_=build("item.value=7 item.label='text' WRITE(item)");p.run();self.assertEqual(texts(p),[' 7text'])

    def test_multidimensional_array_is_row_major(self):
        p,_=build('a[1,1]=1 a[1,2]=2 a[2,1]=3 a[2,2]=4 WRITE(a)',decl='a:ARRAY[2,2]OF INTEGER');p.run();self.assertEqual(texts(p),[' 1 2 3 4'])

    def test_named_component_arrays_keep_row_major_order(self):
        p,_=build('a[1][1]=1 a[1][2]=2 a[2][1]=3 a[2][2]=4 WRITE(a)',prefix='TYPE row_t=ARRAY[2]OF INTEGER',decl='a:ARRAY[2]OF row_t');p.run();self.assertEqual(texts(p),[' 1 2 3 4'])

    def test_array_of_records_renders_element_then_fields(self):
        p,_=build("a[1].value=7 a[1].label='one' a[2].value=9 a[2].label='two' WRITE(a)",decl='a:ARRAY[2]OF item_t');p.run();self.assertEqual(texts(p),[' 7one 9two'])

    def test_vector_expression_is_supported(self):
        p,_=build('v.x=1 v.y=2 v.z=3 WRITE(v+v)',decl='v:VECTOR');p.run();self.assertEqual(texts(p),[' 2.00000E+00 4.00000E+00 6.00000E+00'])

    def test_config_uses_turn_and_flag_order(self):
        p,_=build("CNV_STR_CONF('N',cfg,s) WRITE(cfg)",decl='cfg:CONFIG s:INTEGER');v=p.run();self.assertEqual(texts(p),[' 0 0 0 FALSE FALSE FALSE FALSE']);self.assertIsNone(p._state.execution.robot)

    def test_joint_axis_order_uses_real_defaults(self):
        p,_=build('READ(a) WRITE(a)',read=lambda request:[1.5,2.5],decl='a:JOINTPOS2');p.run();self.assertEqual(texts(p),[' 1.50000E+00 2.50000E+00'])

    def test_complete_position_is_readable_output_without_orientation_writes(self):
        p,_=build("CNV_STR_CONF('N',cfg,s) p=POS(1,2,3,0,0,0,cfg) WRITE(p)",decl='cfg:CONFIG p:POSITION s:INTEGER');v=p.run();self.assertIn(' 1.00000E+00 2.00000E+00 3.00000E+00 0 0 0',texts(p)[0]);self.assertEqual(v['P']['NORMAL'],dict(X=1.,Y=0.,Z=0.))

    def test_readonly_position_vector_can_be_output(self):
        p,_=build("CNV_STR_CONF('N',cfg,s) p=POS(0,0,0,0,0,0,cfg) WRITE(p.normal)",decl='cfg:CONFIG p:POSITION s:INTEGER');p.run();self.assertEqual(texts(p),[' 1.00000E+00 0.00000E+00 -0.00000E+00'])

    def test_narrow_aggregate_data_retains_scalar_domains(self):
        p,_=build('READ(a) WRITE(a)',prefix='TYPE row_t=STRUCTURE b:BYTE small:SHORT ENDSTRUCTURE',decl='a:row_t',read=lambda request:[255,-7]);p.run();self.assertEqual(texts(p),[' 255 -7'])


class AggregateWriteOrderTests(unittest.TestCase):
    def test_mixed_scalar_formats_and_cr_preserve_source_order(self):
        p,_=build("a[1]=7 a[2]=9 WRITE('values=',a,', n=',42::0::16,CR)");p.run();self.assertEqual(texts(p),['values= 7 9, n= 2A\n'])

    def test_array_is_rendered_before_later_function_mutates_it(self):
        routine='ROUTINE change:INTEGER BEGIN a[1]=99 RETURN 42 END change'
        p,_=build('a[1]=7 a[2]=9 WRITE(a,change())',routines=routine);v=p.run();self.assertEqual(texts(p),[' 7 9 42']);self.assertEqual(v['A'],[99,9])

    def test_record_is_rendered_before_later_format_expression(self):
        routine='ROUTINE width:INTEGER BEGIN item.value=99 RETURN 1 END width'
        p,_=build("item.value=7 item.label='text' WRITE(item,1::width())",routines=routine);p.run();self.assertEqual(texts(p),[' 7text 1'])

    def test_aggregate_function_result_evaluates_once(self):
        routine="ROUTINE make:item_t BEGIN visits=visits+1 item.value=7 item.label='text' RETURN item END make"
        p,_=build('visits=0 WRITE(make())',routines=routine);self.assertEqual(p.run()['VISITS'],1);self.assertEqual(texts(p),[' 7text'])

    def test_indexed_source_selector_runs_once(self):
        routine='ROUTINE slot:INTEGER BEGIN visits=visits+1 RETURN 1 END slot'
        p,_=build("visits=0 rows[1].value=7 rows[1].label='text' WRITE(rows[slot()])",decl=DECL+' rows:ARRAY[1]OF item_t',routines=routine);self.assertEqual(p.run()['VISITS'],1)

    def test_nested_write_from_later_expression_precedes_outer_publication(self):
        routine="ROUTINE change:INTEGER BEGIN WRITE('nested') RETURN 42 END change"
        p,_=build('a[1]=7 a[2]=9 WRITE(a,change())',routines=routine);p.run();self.assertEqual(texts(p),['nested',' 7 9 42'])

    def test_invalid_first_aggregate_prevents_later_expression_effects(self):
        routine='ROUTINE change:INTEGER BEGIN visits=visits+1 RETURN 1 END change'
        p,_=build('visits=0 WRITE(a,change())',routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0);self.assertEqual(texts(p),[])

    def test_late_invalid_aggregate_keeps_prior_expression_effects_without_outer_output(self):
        routine='ROUTINE change:INTEGER BEGIN visits=visits+1 RETURN 1 END change'
        p,_=build('visits=0 WRITE(change(),a)',routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],1);self.assertEqual(texts(p),[])

    def test_pause_in_later_expression_retains_prior_rendered_aggregate(self):
        routine='ROUTINE change:INTEGER BEGIN PAUSE a[1]=99 RETURN 42 END change'
        p,_=build('a[1]=7 a[2]=9 WRITE(a,change())',routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p.resume();self.assertEqual(texts(p),[' 7 9 42'])

    def test_scalar_only_generation_stays_on_existing_path(self):
        _,r=build('WRITE(7)');self.assertNotIn('self._state.write_groups(',r.python_source)


class AggregateWriteGuardTests(unittest.TestCase):
    def test_missing_scalar_leaf_rejects_complete_output(self):
        p,_=build('a[1]=7 WRITE(a)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(texts(p),[])

    def test_unknown_byte_content_is_not_printed_as_a_number(self):
        p,_=build('WRITE(a)',decl='a:ARRAY[1]OF BYTE')
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_short_sentinel_is_not_output_as_32767(self):
        p,_=build('a[1]=32767 WRITE(a)',decl='a:ARRAY[1]OF SHORT')
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_whole_missing_source_root_rejects(self):
        p,_=build('WRITE(a)');p._state.values['A']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_missing_nested_container_rejects(self):
        p,_=build('WRITE(a)',prefix='TYPE row_t=ARRAY[2]OF INTEGER',decl='a:ARRAY[1]OF row_t');p._state.values['A'].values[0]=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_bad_current_scalar_type_rejects_before_output(self):
        p,_=build('WRITE(a)');p._state.values['A'].values[:]=[7,True]
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_nonfinite_known_real_rejects_before_output(self):
        p,_=build('WRITE(a)',decl='a:ARRAY[1]OF REAL');p._state.values['A'].values[0]=float('nan')
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_config_turn_bound_is_checked_before_output(self):
        p,_=build("CNV_STR_CONF('N',cfg,s) cfg.cfg_turn_no1=8 WRITE(cfg)",decl='cfg:CONFIG s:INTEGER')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(texts(p),[])

    def test_aggregate_formats_apply_to_all_scalar_members(self):
        p,_=build('a[1]=7 a[2]=9 WRITE(a::3::16)');p.run();self.assertEqual(texts(p),[' 07 09'])

    def test_resources_remain_excluded(self):
        for kind in ('FILE','ARRAY[1]OF FILE'):
            with self.assertRaises(TranslationError):build('WRITE(a)',decl='a:'+kind)

    def test_malformed_array_shape_rejects(self):
        p,_=build('WRITE(a)');p._state.values['A'].values.pop()
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_empty_rendered_fields_still_count_toward_1024_limit(self):
        value=rt.Array(('ARRAY',1024,('STRING',1)));value.values[:]=['']*1024
        with rt._numeric_scope('pythonic'):pieces=rt.aggregate_write_pieces(value.spec,value)
        self.assertEqual(len(pieces),1024)

    def test_1025_scalar_leaves_reject_before_rendering(self):
        value=rt.Array(('ARRAY',1025,('INTEGER',)));value.values[:]=[7]*1025
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'1024'):rt.aggregate_write_pieces(value.spec,value)

    def test_combined_aggregate_and_cr_items_are_bounded(self):
        p,_=build("READ(a) WRITE(a,CR)",decl='a:ARRAY[1024]OF STRING[1]',read=lambda request:['']*1024)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'1024'):p.run()
        self.assertEqual(texts(p),[])

    def test_254_character_text_boundary_fits(self):
        p,_=build('READ(a) WRITE(a)',decl='a:ARRAY[127]OF INTEGER',read=lambda request:[7]*127);p.run();self.assertEqual(texts(p),[' 7'*127])

    def test_text_above_254_publishes_no_request(self):
        p,_=build('READ(a) WRITE(a)',decl='a:ARRAY[128]OF INTEGER',read=lambda request:[7]*128)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'254'):p.run()
        self.assertEqual(texts(p),[])

    def test_strict_runtime_helper_keeps_preserved_exclusion(self):
        p,_=build();value=p._state.values['A']
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.aggregate_write_pieces(value.spec,value)

    def test_write_group_helper_rejects_empty_or_malformed_groups(self):
        p,_=build()
        for groups in ([[]],['text']):
            with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):p._state.write_groups(groups)


class AggregateWriteFileTests(unittest.TestCase):
    def test_memory_text_file_records_one_combined_statement(self):
        p,ctx,_=memory("OPEN FILE f('WO','data') a[1]=7 a[2]=9 WRITE f('a=',a,CR) CLOSE FILE f");p.run();self.assertEqual(ctx.files.files['data'],b'a= 7 9\n');self.assertEqual(texts(p),[])

    def test_binary_integer_array_matches_scalar_byte_layout(self):
        p,ctx,_=memory("OPEN FILE f('WB','data') a[1]=7 a[2]=9 WRITE f(a) CLOSE FILE f");p.run();self.assertEqual(ctx.files.files['data'],struct.pack('<ii',7,9))

    def test_binary_write_read_roundtrip_uses_declared_string_capacity(self):
        body="item.value=42 item.label='text' OPEN FILE f('WB','data') WRITE f(item) CLOSE FILE f item.value=99 item.label='old' OPEN FILE f('RB','data') READ f(item) CLOSE FILE f"
        p,ctx,_=memory(body);v=p.run();self.assertEqual(v['ITEM'],dict(VALUE=42,LABEL='text'));self.assertEqual(ctx.files.files['data'],struct.pack('<i',42)+b'text')

    def test_binary_short_string_is_padded_and_read_padding_is_retained(self):
        p,ctx,_=memory("item.value=7 item.label='hi' OPEN FILE f('WB','data') WRITE f(item) CLOSE FILE f OPEN FILE f('RB','data') READ f(item) CLOSE FILE f");self.assertEqual(p.run()['ITEM']['LABEL'],'hi\0\0');self.assertEqual(bytes(ctx.files.files['data'])[-4:],b'hi\0\0')

    def test_reverse_binary_array_uses_existing_endianness(self):
        p,ctx,_=memory("a[1]=7 a[2]=9 SET_FILE_ATR(f,ATR_REVERSE) OPEN FILE f('WB','data') WRITE f(a) CLOSE FILE f");p.run();self.assertEqual(ctx.files.files['data'],struct.pack('>ii',7,9))

    def test_binary_late_real_overflow_preserves_existing_bytes_and_cursor(self):
        p,ctx,_=memory("a[1]=1.0 a[2]=1.0E100 OPEN FILE f('RWB','data') WRITE f(a)",initial={'data':b'original'},decl='a:ARRAY[2]OF REAL f:FILE')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((ctx.files.files['data'],p._state.values['F'].position),(b'original',0))

    def test_file_text_can_exceed_callback_254_limit_with_bounded_leaves(self):
        p,ctx,_=memory("READ(a) OPEN FILE f('WO','data') WRITE f(a) CLOSE FILE f",decl='a:ARRAY[200]OF INTEGER f:FILE',read=lambda request:[7]*200);p.run();self.assertEqual(ctx.files.files['data'],b' 7'*200)

    def test_directory_output_uses_the_existing_explicit_root(self):
        with tempfile.TemporaryDirectory() as folder:
            ctx=rt.ExecutionContext(files=rt.DirectoryFiles(folder));p,_=build("a[1]=7 a[2]=9 OPEN FILE f('WO','data') WRITE f(a) CLOSE FILE f",context=ctx);p.run();self.assertEqual(Path(folder,'data').read_bytes(),b' 7 9')

    def test_backend_quota_rejects_before_file_data_changes(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'data':b'old'},limit=3));p,_=build("a[1]=7 a[2]=9 OPEN FILE f('RW','data') WRITE f(a)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.files.files['data'],b'old')

    def test_eol_mapping_reuses_existing_file_behavior(self):
        p,ctx,_=memory("a[1]=7 a[2]=9 SET_FILE_ATR(f,ATR_EOL,13) OPEN FILE f('WO','data') WRITE f(a,CR) CLOSE FILE f");p.run();self.assertEqual(ctx.files.files['data'],b' 7 9\r')


class AggregateWriteIntegrationTests(unittest.TestCase):
    def test_generic_array_formal_uses_actual_concrete_shape(self):
        p,_=build('a[1]=7 a[2]=9 take(a)',routines='ROUTINE take(data:ARRAY OF INTEGER) BEGIN WRITE(data) END take');p.run();self.assertEqual(texts(p),[' 7 9'])

    def test_byname_record_formal_renders_explicit_storage(self):
        spec=('STRUCTURE','ITEM_T',(('VALUE',('INTEGER',)),('LABEL',('STRING',4))));value=rt.Structure(spec);value.values.update(VALUE=7,LABEL='text');ctx=rt.ExecutionContext();ctx.variables.define('CACHE','ITEM',spec,value)
        p,_=build("take(BYNAME('CACHE','ITEM',n))",context=ctx,routines='ROUTINE take(data:item_t) BEGIN WRITE(data) END take');p.run();self.assertEqual(texts(p),[' 7text'])

    def test_linked_reference_formal_uses_caller_owned_text_sink(self):
        main='PROGRAM MAIN VAR a:ARRAY[2]OF INTEGER ROUTINE take(data:ARRAY OF INTEGER) FROM LIB BEGIN a[1]=7 a[2]=9 take(a) END MAIN';lib='PROGRAM LIB ROUTINE take(data:ARRAY OF INTEGER) BEGIN WRITE(data) END take BEGIN END LIB'
        observed=[];p=translate_project({'main':main,'lib':lib}).instantiate(options=dict(write=observed.append));p.run('MAIN');self.assertEqual(observed,[' 7 9'])

    def test_serial_output_appends_one_rendered_batch(self):
        bank=rt.SerialStreams({2:dict(output=b'prior')});ctx=rt.ExecutionContext(serial_streams=bank);p,_=build("a[1]=7 a[2]=9 OPEN FILE f('WO','P2:') WRITE f(a,CR) CLOSE FILE f",context=ctx);p.run();self.assertEqual(bank.snapshot()[2]['output'],b'prior 7 9\n')

    def test_plain_pipe_output_uses_existing_configured_endpoint(self):
        bank=pipe_bank();ctx=rt.ExecutionContext(file_pipes=bank);p,_=build("a[1]=7 a[2]=9 OPEN FILE f('WO','PIP:LOG') WRITE f(a,CR) CLOSE FILE f",context=ctx);p.run();self.assertEqual(bank.snapshot(),{'PIP:LOG':b' 7 9\n'})

    def test_callback_failure_is_recorded_once_without_retry(self):
        calls=[]
        def sink(text):calls.append(text);raise ValueError('authored failure')
        p,_=build(write=sink)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[' 7 9']);self.assertEqual(p.write_requests[0]['adapter_outcome'],'callback_failed')

    def test_callback_receives_one_complete_statement(self):
        seen=[];p,_=build(write=seen.append);p.run();self.assertEqual(seen,[' 7 9']);self.assertEqual(p.write_requests[0]['adapter_outcome'],'callback_completed')

    def test_completed_context_json_preserves_values(self):
        p,_=build();p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_active_for_counter_can_be_read_without_writing_it(self):
        p,_=build('FOR n=1 TO 2 DO a[1]=n a[2]=9 WRITE(a) ENDFOR');p.run();self.assertEqual(texts(p),[' 1 9',' 2 9'])

    def test_report_describes_capture_defaults_and_native_boundaries(self):
        _,r=build();policy=r.report['aggregate_write_policy'];self.assertFalse(policy['controller_validated']);self.assertIn('1024',policy['limits']);self.assertTrue(r.report['writes'][0]['items'][0]['aggregate'])

    def test_array_write_does_not_mutate_source_or_captured_field_alias(self):
        p,_=build();value=p._state.values['A'];field=rt.index_reference(value,1);p.run();self.assertIs(p._state.values['A'],value);self.assertEqual(field.raw(),7)

    def test_no_robot_context_is_inferred_for_joint_output(self):
        p,_=build('READ(a) WRITE(a)',decl='a:JOINTPOS2',read=lambda request:[1.,2.]);p.run();self.assertIsNone(p._state.execution.robot)

    def test_keyboard_window_output_uses_the_headless_sink(self):
        from tests.test_keyboard import WINDOW
        ctx=keyboard_context();p,_=build(WINDOW+"a[1]=7 a[2]=9 OPEN FILE f('RW','WD:W1/TPKB') WRITE f(a) CLOSE FILE f",context=ctx);p.run();self.assertEqual(texts(p),[])

    def test_aggregate_result_with_missing_data_rejects_later_output(self):
        routine='ROUTINE make:item_t BEGIN item.value=7 RETURN item END make'
        p,_=build('WRITE(make())',routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(texts(p),[])


if __name__=='__main__':unittest.main()
