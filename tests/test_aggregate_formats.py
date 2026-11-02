"""Authored uniform aggregate formats, capture order and transport checks."""
import json
import struct
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_aggregate_read import build as reader
from tests.test_aggregate_write import build as writer,texts,memory
from tests.test_file_cancellation import serial
from tests.test_pipe_attributes import bank as pipe_bank
from tests.test_keyboard import context as keyboard_context
from tests.test_keyboard_file_read import line_keys


class AggregateOutputFormatTests(unittest.TestCase):
    def test_integer_array_uses_uniform_width_and_base(self):
        p,_=writer('a[1]=10 a[2]=15 WRITE(a::4::16)');p.run();self.assertEqual(texts(p),[' 00A 00F'])

    def test_signed_integer_array_preserves_scalar_base_convention(self):
        p,_=writer('a[1]=-10 a[2]=-15 WRITE(a::0::16)');p.run();self.assertEqual(texts(p),[' -A -F'])

    def test_real_array_fixed_precision(self):
        p,_=writer('a[1]=1.25 a[2]=2.5 WRITE(a::0::2)',decl='a:ARRAY[2]OF REAL');p.run();self.assertEqual(texts(p),[' 1.25 2.50'])

    def test_joint_array_uses_real_precision(self):
        p,_=writer('READ(a) WRITE(a::0::1)',decl='a:JOINTPOS2',read=lambda request:[1.25,2.5]);p.run();self.assertEqual(texts(p),[' 1.2 2.5'])

    def test_real_array_scientific_precision(self):
        p,_=writer('a[1]=1.25 a[2]=2.5 WRITE(a::0::-2)',decl='a:ARRAY[2]OF REAL');p.run();self.assertEqual(texts(p),[' 1.25E+00 2.50E+00'])

    def test_string_array_quote_and_escape_modes(self):
        p,_=writer("a[1]='O''B' a[2]='hi' WRITE(a::0::2)",decl='a:ARRAY[2]OF STRING[4]');p.run();self.assertEqual(texts(p),[" 'O''B' 'hi'"])

    def test_boolean_array_width(self):
        p,_=writer('a[1]=TRUE a[2]=FALSE WRITE(a::8)',decl='a:ARRAY[2]OF BOOLEAN');p.run();self.assertEqual(texts(p),['    TRUE   FALSE'])

    def test_string_only_large_width_keeps_scalar_natural_fallback(self):
        p,_=writer("a[1]='one' a[2]='two' WRITE(a::300)",decl='a:ARRAY[2]OF STRING[4]');p.run();self.assertEqual(texts(p),['onetwo'])

    def test_nested_named_components_share_formats(self):
        p,_=writer('a[1][1]=10 a[1][2]=15 WRITE(a::3::16)',prefix='TYPE row_t=ARRAY[2]OF INTEGER',decl='a:ARRAY[1]OF row_t');p.run();self.assertEqual(texts(p),[' 0A 0F'])

    def test_mixed_record_interprets_second_format_per_scalar_kind(self):
        p,_=writer("item.value=5 item.label='abc' WRITE(item::5::2)");p.run();self.assertEqual(texts(p),[" 0101 'ab'"])

    def test_vector_value_uses_uniform_real_format(self):
        p,_=writer('WRITE(VEC(1,2,3)::0::1)');p.run();self.assertEqual(texts(p),[' 1.0 2.0 3.0'])

    def test_default_generated_entry_is_still_usable(self):
        p,_=writer();p.run();self.assertEqual(texts(p),[' 7 9'])


class AggregateInputFormatTests(unittest.TestCase):
    def test_integer_array_text_width_and_base(self):
        p,_=reader('READ(a::2::16)',read=rt.TextInput('0A0F'));self.assertEqual(p.run()['A'],[10,15])

    def test_real_array_fixed_fields(self):
        p,_=reader('READ(a::4)',read=rt.TextInput('1.252.50'),decl='a:ARRAY[2]OF REAL');self.assertEqual(p.run()['A'],[1.25,2.5])

    def test_string_array_quoted_fixed_fields(self):
        p,_=reader('READ(a::5::2)',read=rt.TextInput("'one''two'"),decl='a:ARRAY[2]OF STRING[4]');self.assertEqual(p.run()['A'],['one','two'])

    def test_boolean_array_fixed_fields(self):
        p,_=reader('READ(a::4::99)',read=rt.TextInput(' ON OFF '),decl='a:ARRAY[2]OF BOOLEAN');self.assertEqual(p.run()['A'],[True,False])

    def test_joint_values_use_uniform_scalar_width(self):
        p,_=reader('READ(a::4)',read=rt.TextInput('1.252.50'),decl='a:JOINTPOS2');self.assertEqual(p.run()['A'],{'axes':[1.25,2.5]})

    def test_typed_callback_values_are_already_decoded(self):
        p,_=reader('READ(a::2::16)',values=[10,15]);self.assertEqual(p.run()['A'],[10,15]);self.assertEqual([row['format_specifiers'] for row in p.read_requests[0]['targets']],[(2,16),(2,16)])

    def test_cr_remains_after_whole_formatted_array(self):
        p,_=reader('READ(a::2,CR,n::2,CR)',read=rt.TextInput('0709\n42\n'));v=p.run();self.assertEqual((v['A'],v['N']),([7,9],42));self.assertEqual(p.read_requests[0]['line_breaks'],[2,3])

    def test_generic_array_formal_inherits_shape_and_formats(self):
        p,_=reader('take(a)',values=[10,15],routines='ROUTINE take(data:ARRAY OF INTEGER) BEGIN READ(data::2::16) END take');self.assertEqual(p.run()['A'],[10,15])

    def test_mixed_integer_and_string_input_reuses_scalar_rules(self):
        p,_=reader('READ(item::3::2)',read=rt.TextInput("101'x'"));self.assertEqual(p.run()['ITEM'],dict(VALUE=5,LABEL='x'))

    def test_invalid_late_value_preserves_all_outputs(self):
        p,_=reader('a[1]=77 a[2]=88 READ(a::2)',read=rt.TextInput('07xx'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['A'],[77,88])

    def test_config_turn_domains_are_not_widened_by_uniform_formats(self):
        p,_=reader('READ(a::1)',values=[0,0,8,False,False,False,False],decl='a:CONFIG')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p._state.values['A'].values['CFG_TURN_NO1'],rt.UNINITIALIZED)

    def test_no_format_still_uses_existing_scalar_defaults(self):
        p,_=reader(values=[7,9]);self.assertEqual(p.run()['A'],[7,9])


class AggregateFormatCaptureTests(unittest.TestCase):
    def test_write_capture_precedes_width_function_mutation(self):
        routine='ROUTINE width:INTEGER BEGIN a[1]=99 visits=visits+1 RETURN 3 END width'
        p,_=writer('visits=0 a[1]=7 a[2]=9 WRITE(a::width())',routines=routine);v=p.run();self.assertEqual((texts(p),v['A'],v['VISITS']),(['  7  9'],[99,9],1))

    def test_write_capture_precedes_second_format_mutation(self):
        routine='ROUTINE base:INTEGER BEGIN a[1]=99 RETURN 16 END base'
        p,_=writer('a[1]=10 a[2]=15 WRITE(a::3::base())',routines=routine);p.run();self.assertEqual(texts(p),[' 0A 0F'])

    def test_record_string_is_detached_before_format_call(self):
        routine="ROUTINE width:INTEGER BEGIN item.label='new' RETURN 6 END width"
        p,_=writer("item.value=7 item.label='text' WRITE(item::width())",routines=routine);p.run();self.assertEqual(texts(p),['     7text  '])

    def test_source_width_and_precision_evaluate_once_in_order(self):
        routines='ROUTINE width:INTEGER BEGIN visits=visits*10+1 RETURN 0 END width ROUTINE precision:INTEGER BEGIN visits=visits*10+2 RETURN 1 END precision'
        p,_=writer('visits=0 a[1]=1.25 a[2]=2.5 WRITE(a::width()::precision())',decl='a:ARRAY[2]OF REAL visits:INTEGER',routines=routines);self.assertEqual(p.run()['VISITS'],12)

    def test_missing_write_value_prevents_format_side_effects(self):
        routine='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 3 END width'
        p,_=writer('visits=0 WRITE(a::width())',routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)

    def test_pause_in_write_format_retains_complete_early_capture(self):
        routine='ROUTINE width:INTEGER BEGIN visits=visits+1 PAUSE a[1]=99 RETURN 3 END width'
        p,_=writer('visits=0 a[1]=7 a[2]=9 WRITE(a::width())',routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p.resume();self.assertEqual(texts(p),['  7  9']);self.assertEqual(p.snapshot()['VISITS'],1)

    def test_read_leaf_capture_precedes_format_root_replacement(self):
        ctx=rt.ExecutionContext();ctx.variables.bind('CACHE','EMPTY',rt.Reference(('ARRAY',2,('INTEGER',)),{'value':rt.UNINITIALIZED},'value'))
        routine="ROUTINE width:INTEGER BEGIN GET_VAR(n,'CACHE','EMPTY',a,s) RETURN 2 END width"
        p,_=reader('READ(a::width())',values=[7,9],context=ctx,routines=routine);old=p._state.values['A'];p.run();self.assertEqual(old.values,[7,9]);self.assertIs(p._state.values['A'],rt.UNINITIALIZED)

    def test_read_width_function_runs_once_for_all_fields(self):
        routine='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 2 END width'
        p,_=reader('visits=0 READ(a::width())',values=[7,9],routines=routine);self.assertEqual(p.run()['VISITS'],1)

    def test_malformed_read_capture_prevents_format_side_effects(self):
        routine='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 2 END width'
        p,_=reader('visits=0 READ(a::width())',values=[7,9],routines=routine);p._state.values['A'].values[0]=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)

    def test_pause_in_read_format_retains_selected_fields(self):
        routine='ROUTINE width:INTEGER BEGIN visits=visits+1 PAUSE RETURN 2 END width'
        p,_=reader('visits=0 READ(a::width())',values=[7,9],routines=routine,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['A'],[7,9]);self.assertEqual(p.snapshot()['VISITS'],1)

    def test_later_output_item_mutation_cannot_change_formatted_aggregate(self):
        routine='ROUTINE change:INTEGER BEGIN a[1]=99 RETURN 42 END change'
        p,_=writer('a[1]=10 a[2]=15 WRITE(a::3::16,change())',routines=routine);p.run();self.assertEqual(texts(p),[' 0A 0F 42'])

    def test_nested_output_in_format_precedes_outer_statement(self):
        routine="ROUTINE width:INTEGER BEGIN WRITE('nested') RETURN 3 END width"
        p,_=writer('a[1]=7 a[2]=9 WRITE(a::width())',routines=routine);p.run();self.assertEqual(texts(p),['nested','  7  9'])


class AggregateFormatGuardTests(unittest.TestCase):
    def test_boolean_write_second_format_is_rejected_for_mixed_records(self):
        with self.assertRaises(TranslationError):writer('WRITE(a::2::2)',prefix='TYPE data_t=STRUCTURE n:INTEGER b:BOOLEAN ENDSTRUCTURE',decl='a:data_t')

    def test_integer_member_prevents_string_only_large_width(self):
        with self.assertRaises(TranslationError):writer('WRITE(item::300)')

    def test_string_member_rejects_numeric_only_base(self):
        with self.assertRaises(TranslationError):writer('WRITE(item::4::16)')

    def test_read_string_member_rejects_unsupported_second_mode(self):
        with self.assertRaises(TranslationError):reader('READ(item::4::16)')

    def test_read_integer_member_rejects_invalid_base(self):
        with self.assertRaises(TranslationError):reader('READ(a::2::1)')

    def test_boolean_format_expression_is_not_an_integer(self):
        for build,body in ((reader,'READ(a::TRUE)'),(writer,'WRITE(a::TRUE)')):
            with self.assertRaises(TranslationError):build(body)

    def test_dynamic_invalid_write_format_keeps_prior_format_effects(self):
        routine='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 255 END width'
        p,_=writer('visits=0 a[1]=7 a[2]=9 WRITE(a::width())',routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((texts(p),p.snapshot()['VISITS']),([],1))

    def test_dynamic_invalid_read_format_rejects_before_callback(self):
        seen=[];routine='ROUTINE width:INTEGER BEGIN RETURN 255 END width'
        p,_=reader('READ(a::width())',read=lambda request:seen.append(request),routines=routine)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(seen,[])

    def test_strict_runtime_cannot_format_captured_aggregate(self):
        p,_=writer('a[1]=7 a[2]=9');p.run()
        with rt._numeric_scope('pythonic'):captured=rt.capture_aggregate_write(p._state.types['A'],p._state.values['A'])
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.format_aggregate_write(captured,[2])

    def test_position_input_remains_excluded(self):
        with self.assertRaises(TranslationError):reader('READ(a::4)',decl='a:POSITION')

    def test_resource_output_remains_excluded(self):
        with self.assertRaises(TranslationError):writer('WRITE(a::4)',decl='a:FILE')

    def test_runtime_helpers_reject_invalid_format_types(self):
        p,_=writer();p.run()
        with rt._numeric_scope('pythonic'):
            value=rt.capture_aggregate_write(p._state.types['A'],p._state.values['A'])
            with self.assertRaises(rt.KarelRuntimeError):rt.format_aggregate_write(value,[True])
            with self.assertRaises(rt.KarelRuntimeError):rt.format_aggregate_read_group([],[])


class AggregateFormatTransportTests(unittest.TestCase):
    def test_text_file_write_read_roundtrip_with_hex_fields(self):
        p,ctx,_=memory("a[1]=10 a[2]=15 OPEN FILE f('WO','data') WRITE f(a::3::16,CR) CLOSE FILE f OPEN FILE f('RO','data') READ f(b::3::16,CR) CLOSE FILE f");self.assertEqual(p.run()['B'],[10,15]);self.assertEqual(ctx.files.files['data'],b' 0A 0F\n')

    def test_binary_integral_width_override_roundtrips(self):
        p,ctx,_=memory("a[1]=7 a[2]=9 OPEN FILE f('WB','data') WRITE f(a::2) CLOSE FILE f OPEN FILE f('RB','data') READ f(b::2) CLOSE FILE f");self.assertEqual(p.run()['B'],[7,9]);self.assertEqual(ctx.files.files['data'],struct.pack('<hh',7,9))

    def test_binary_string_width_override_roundtrips_truncated_fields(self):
        p,ctx,_=memory("a[1]='abcd' a[2]='wxyz' OPEN FILE f('WB','data') WRITE f(a::2) CLOSE FILE f OPEN FILE f('RB','data') READ f(b::2) CLOSE FILE f",decl='a,b:ARRAY[2]OF STRING[4] f:FILE');self.assertEqual(p.run()['B'],['ab','wx']);self.assertEqual(ctx.files.files['data'],b'abwx')

    def test_binary_second_format_rejects_without_file_publication(self):
        p,ctx,_=memory("a[1]=7 a[2]=9 OPEN FILE f('RWB','data') WRITE f(a::2::16)",initial={'data':b'original'})
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.files.files['data'],b'original');self.assertEqual(p._state.values['F'].position,0)

    def test_waiting_serial_read_uses_uniform_fixed_fields(self):
        bank,ctx=serial(b'07')
        def sleeper(_):bank.feed(2,b'09\n')
        p,_=reader("OPEN FILE f('RO','P2:') READ f(a::2,CR) CLOSE FILE f",context=ctx,sleep=sleeper);self.assertEqual(p.run()['A'],[7,9])

    def test_waiting_serial_cancel_keeps_formatted_group_unchanged(self):
        bank,ctx=serial(b'07')
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=reader("OPEN FILE f('RO','P2:') a[1]=77 a[2]=88 READ f(a::2,CR) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper);self.assertEqual((p.run()['A'],p.snapshot()['S']),([77,88],6))

    def test_waiting_pipe_keeps_captured_formats(self):
        bank=pipe_bank(b'07');ctx=rt.ExecutionContext(file_pipes=bank)
        def sleeper(_):bank.feed('LOG',b'09\n')
        p,_=reader("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') READ f(a::2,CR) CLOSE FILE f",context=ctx,sleep=sleeper);self.assertEqual(p.run()['A'],[7,9])

    def test_keyboard_line_uses_uniform_formatted_fields(self):
        ctx=keyboard_context(keys=line_keys('0709'));p,_=reader("OPEN FILE f('RW','KB:TPKB') READ f(a::2,CR) CLOSE FILE f",context=ctx,sleep=lambda _:None);self.assertEqual(p.run()['A'],[7,9])

    def test_linked_generic_formal_inherits_actual_format_categories(self):
        main='PROGRAM MAIN VAR a:ARRAY[2]OF INTEGER ROUTINE take(data:ARRAY OF INTEGER) FROM LIB BEGIN a[1]=10 a[2]=15 take(a) END MAIN';lib='PROGRAM LIB ROUTINE take(data:ARRAY OF INTEGER) BEGIN WRITE(data::3::16) END take BEGIN END LIB'
        seen=[];p=translate_project({'main':main,'lib':lib}).instantiate(options=dict(write=seen.append));p.run('MAIN');self.assertEqual(seen,[' 0A 0F'])

    def test_context_json_remains_data_only_after_formatted_io(self):
        p,_=reader('READ(a::2::16) WRITE(a::3::16)',values=[10,15]);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_generic_string_formal_uses_caller_capacity(self):
        p,_=writer("a[1]='abcd' a[2]='wxyz' take(a)",decl='a:ARRAY[2]OF STRING[4]',routines='ROUTINE take(data:ARRAY OF STRING) BEGIN WRITE(data::3) END take');p.run();self.assertEqual(texts(p),['abcwxy'])

    def test_report_records_formats_without_scalar_alignment_claim(self):
        _,r=writer('a[1]=10 a[2]=15 WRITE(a::3::16)');policy=r.report['aggregate_format_policy'];self.assertFalse(policy['controller_validated']);self.assertTrue(r.report['writes'][0]['items'][0]['capture_before_formats']);self.assertNotIn('alignment',r.report['writes'][0])

    def test_read_metadata_marks_capture_before_formats(self):
        _,r=reader('READ(a::2::16)',values=[10,15]);self.assertTrue(r.report['reads'][0]['destinations'][0]['capture_before_formats'])

    def test_invalid_late_binary_read_format_preserves_outputs_and_cursor(self):
        p,ctx,_=memory("a[1]=77 a[2]=88 OPEN FILE f('RB','data') READ f(a::2::16)",initial={'data':struct.pack('<hh',7,9)})
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['A'],[77,88]);self.assertEqual(p._state.values['F'].position,0)

    def test_formatted_group_retains_1024_scalar_limit(self):
        p,_=writer('READ(a) WRITE(a::0)',decl='a:ARRAY[1025]OF STRING[1]',read=lambda request:['']*1025)
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_callback_format_metadata_is_defensive(self):
        seen=[]
        def callback(request):seen.append(request);request['targets'].clear();return [10,15]
        p,_=reader('READ(a::2::16)',read=callback);self.assertEqual(p.run()['A'],[10,15]);self.assertEqual(len(p.read_requests[0]['targets']),2)


if __name__=='__main__':unittest.main()
