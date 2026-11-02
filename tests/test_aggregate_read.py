"""Authored Pythonic whole-data READ, scalar transport ordering and atomicity."""
import json
import struct
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_keyboard_file_read import line_keys
from tests.test_keyboard import context as keyboard_context
from tests.test_pipe_attributes import bank as pipe_bank
from tests.test_file_cancellation import serial

PREFIX='TYPE item_t=STRUCTURE value:INTEGER label:STRING[4] ENDSTRUCTURE'
DECL='a:ARRAY[2]OF INTEGER item:item_t n,s,visits:INTEGER f:FILE'


def build(body='READ(a)',*,values=None,read=None,decl=DECL,prefix=PREFIX,**options):
    if values is not None:read=lambda request:list(values)
    return compile_program(body,decl=decl,prefix=prefix,read=read,**options)


def file(data,body='READ f(a)',*,mode='RO',**options):
    ctx=rt.ExecutionContext(files=rt.MemoryFiles({'input':data}))
    return build("OPEN FILE f('"+mode+"','input') "+body,context=ctx,**options)


class AggregateReadValueTests(unittest.TestCase):
    def test_integer_array_consumes_flat_typed_values(self):
        p,_=build(values=[7,9]);self.assertEqual(p.run()['A'],[7,9])

    def test_record_uses_declaration_field_order(self):
        p,_=build('READ(item)',values=[7,'abcdef']);self.assertEqual(p.run()['ITEM'],dict(VALUE=7,LABEL='abcd'))

    def test_multidimensional_array_is_row_major(self):
        p,_=build(values=[1,2,3,4],decl='a:ARRAY[2,2]OF INTEGER');self.assertEqual(p.run()['A'],[[1,2],[3,4]])

    def test_nested_named_array_components_keep_layout(self):
        p,_=build(values=[1,2,3,4],prefix='TYPE row_t=ARRAY[2]OF INTEGER',decl='a:ARRAY[2]OF row_t');self.assertEqual(p.run()['A'],[[1,2],[3,4]])

    def test_array_of_records_flattens_each_element(self):
        p,_=build(values=[7,'one',9,'two'],decl='a:ARRAY[2]OF item_t');self.assertEqual(p.run()['A'],[dict(VALUE=7,LABEL='one'),dict(VALUE=9,LABEL='two')])

    def test_vector_reads_three_real_components_without_robot_context(self):
        p,_=build('READ(v)',values=[1.5,2.5,3.5],decl='v:VECTOR');self.assertEqual(p.run()['V'],dict(X=1.5,Y=2.5,Z=3.5));self.assertIsNone(p._state.execution.robot)

    def test_joint_values_read_in_axis_order(self):
        p,_=build('READ(j)',values=[1.5,2.5,3.5],decl='j:JOINTPOS3');self.assertEqual(p.run()['J'],{'axes':[1.5,2.5,3.5]})

    def test_config_uses_existing_turn_and_flag_domains(self):
        values=[-8,0,7,True,False,True,False];p,_=build('READ(cfg)',values=values,decl='cfg:CONFIG')
        self.assertEqual(list(p.run()['CFG'].values()),values)

    def test_cartesian_record_accepts_config_fields_without_geometry_inference(self):
        values=[1.,2.,3.,4.,5.,6.,0,0,0,False,False,False,False]
        p,_=build('READ(p)',values=values,decl='p:XYZWPR');v=p.run()['P'];self.assertEqual((v['X'],v['R'],v['CONFIG_DATA']['CFG_TURN_NO1']),(1.,6.,0))

    def test_unknown_byte_and_short_sentinel_use_existing_input_rules(self):
        p,_=build('READ(data)',values=[255,32767],prefix='TYPE data_t=STRUCTURE b:BYTE small:SHORT ENDSTRUCTURE',decl='data:data_t')
        v=p.run()['DATA'];self.assertEqual(v['B'],255);self.assertEqual(v['SMALL'],{'uninitialized':True})

    def test_uninitialized_scalar_leaves_are_valid_destinations(self):
        p,_=build(values=[7,9]);self.assertIs(p._state.values['A'].values[0],rt.UNINITIALIZED);self.assertEqual(p.run()['A'],[7,9])

    def test_root_and_descendant_aliases_keep_storage_identity(self):
        p,_=build('READ(item)',values=[7,'text']);root=p._state.values['ITEM'];field=rt.field_reference(root,'VALUE');p.run();self.assertIs(p._state.values['ITEM'],root);self.assertEqual(field.raw(),7)


class AggregateReadOrderTests(unittest.TestCase):
    def test_mixed_scalar_aggregate_and_format_inputs_keep_order(self):
        seen=[]
        def read(request):seen.extend(request['targets']);return [5,7,9,42]
        p,_=build('READ(n::1,a,s::2)',read=read);v=p.run();self.assertEqual((v['N'],v['A'],v['S']),(5,[7,9],42));self.assertEqual([x.get('format_specifiers') for x in seen],[(1,),None,None,(2,)])

    def test_repeated_array_alias_uses_last_validated_value(self):
        p,_=build('READ(a,a[1])',values=[7,9,42]);self.assertEqual(p.run()['A'],[42,9])

    def test_repeated_record_leaf_before_whole_record_uses_record_value(self):
        p,_=build('READ(item.value,item)',values=[99,7,'hi']);self.assertEqual(p.run()['ITEM'],dict(VALUE=7,LABEL='hi'))

    def test_selector_and_later_format_functions_run_once(self):
        routines='ROUTINE slot:INTEGER BEGIN visits=visits*10+1 RETURN 1 END slot ROUTINE width:INTEGER BEGIN visits=visits*10+2 RETURN 1 END width'
        p,_=build('visits=0 READ(items[slot()],n::width())',values=[7,'hi',9],decl=DECL+' items:ARRAY[1]OF item_t',routines=routines);self.assertEqual(p.run()['VISITS'],12)

    def test_invalid_aggregate_capture_prevents_later_selector_effects(self):
        routines='ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 1 END width'
        p,_=build('visits=0 READ(a,n::width())',values=[7,9,1],routines=routines);p._state.values['A'].values[0]=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)

    def test_callback_receives_flat_metadata_with_source_cr_remapped(self):
        calls=[]
        def read(request):calls.append(request);return [7,9,42]
        p,_=build('READ(CR,a,CR,n,CR)',read=read);p.run();self.assertEqual(calls[0]['line_breaks'],[0,2,3]);self.assertEqual(len(calls[0]['targets']),3)

    def test_root_selected_before_later_root_rebinding_keeps_old_fields(self):
        def read(request):p._state.values['A']=rt.Array(('ARRAY',2,('INTEGER',)));return [7,9]
        p,_=build(read=read);original=p._state.values['A'];p.run();self.assertEqual(original.values,[7,9]);self.assertIsNot(p._state.values['A'],original)

    def test_dynamic_generic_array_formal_inherits_actual_shape(self):
        p,_=build('take(a)',values=[7,9],routines='ROUTINE take(data:ARRAY OF INTEGER) BEGIN READ(data) END take');self.assertEqual(p.run()['A'],[7,9])

    def test_generic_string_record_formal_keeps_declared_capacity(self):
        p,_=build('take(item)',values=[7,'abcdef'],routines='ROUTINE take(data:item_t) BEGIN READ(data) END take');self.assertEqual(p.run()['ITEM']['LABEL'],'abcd')


class AggregateReadGuardTests(unittest.TestCase):
    def test_late_invalid_callback_value_keeps_all_destinations(self):
        p,_=build('n=77 a[1]=88 a[2]=99 READ(n,a)',values=[1,2,True])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['A']),(77,[88,99]))

    def test_invalid_config_turn_prevents_earlier_array_stores(self):
        p,_=build('a[1]=77 READ(a,cfg)',values=[1,2,0,0,8,False,False,False,False],decl=DECL+' cfg:CONFIG')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['A'][0],77)

    def test_nested_callback_payload_is_not_silently_flattened(self):
        p,_=build(values=[[7,9]])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p._state.values['A'].values[0],rt.UNINITIALIZED)

    def test_missing_root_container_rejects_before_callback(self):
        calls=[];p,_=build(read=lambda request:calls.append(request));p._state.values['A']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_missing_nested_container_rejects_before_callback(self):
        p,_=build(values=[7,9],prefix='TYPE row_t=ARRAY[2]OF INTEGER',decl='a:ARRAY[1]OF row_t');p._state.values['A'].values[0]=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_malformed_known_current_leaf_is_rejected_before_input(self):
        p,_=build(values=[7,9]);p._state.values['A'].values[0]=False
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_wrong_array_shape_rejects_before_input(self):
        p,_=build(values=[7,9]);p._state.values['A'].values.pop()
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_1024_scalar_leaves_fit(self):
        p,_=build(values=[7]*1024,decl='a:ARRAY[1024]OF INTEGER');self.assertEqual(p.run()['A'],[7]*1024)

    def test_1025_scalar_leaves_reject_before_callback(self):
        p,_=build(values=[7]*1025,decl='a:ARRAY[1025]OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'1024'):p.run()

    def test_combined_aggregate_scalar_and_cr_limit_is_checked(self):
        for body in ('READ(a,n)','READ(a,CR)'):
            p,_=build(body,values=[7]*1025,decl='a:ARRAY[1024]OF INTEGER n:INTEGER')
            with self.assertRaisesRegex(rt.KarelRuntimeError,'1024'):p.run()

    def test_aggregate_formats_are_rejected_at_translation(self):
        with self.assertRaises(TranslationError) as caught:build('READ(a::2)')
        self.assertEqual(caught.exception.code,'E_READ_FORMAT')

    def test_position_and_nested_position_remain_excluded(self):
        for prefix,decl in (('', 'a:POSITION'),('TYPE item_t=STRUCTURE p:POSITION ENDSTRUCTURE','a:item_t'),('', 'a:ARRAY[1]OF POSITION')):
            with self.assertRaises(TranslationError) as caught:build(prefix=prefix,decl=decl)
            self.assertEqual(caught.exception.code,'E_READ_TYPE')

    def test_resource_roots_remain_excluded(self):
        for kind in ('PATH','QUEUE_TYPE','FILE'):
            with self.assertRaises(TranslationError):build(decl='a:'+kind)

    def test_active_for_counter_root_and_constant_guard_remain(self):
        with self.assertRaises(TranslationError):build('FOR a[1]=1 TO 2 DO READ(a) ENDFOR')
        with self.assertRaises(TranslationError):build('READ(a)',prefix='CONST a=7',decl='n:INTEGER')

    def test_preserved_strict_helper_cannot_enable_aggregate_input(self):
        p,_=build();target=p._state.reference('A')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.capture_aggregate_read_target(target,[])

    def test_flatten_helper_rejects_malformed_packets(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.flatten_read_groups([[]])
        with self.assertRaises(rt.KarelRuntimeError):rt.flatten_read_groups([[('not a ref',)]])


class AggregateReadFileTests(unittest.TestCase):
    def test_memory_text_file_and_cr_remapping(self):
        p,_=file('7 9\n42\n','READ f(a,CR,n,CR) s=IO_STATUS(f) CLOSE FILE f');v=p.run();self.assertEqual((v['A'],v['N'],v['S']),([7,9],42,0))

    def test_memory_binary_file_uses_separate_scalar_widths(self):
        p,_=file(struct.pack('<ii',7,9),mode='RB');self.assertEqual(p.run()['A'],[7,9])

    def test_binary_record_string_capacity_and_narrow_fields(self):
        p,_=file(struct.pack('<Bhi',255,-7,42)+b'abcd','READ f(a)',mode='RB',prefix='TYPE row_t=STRUCTURE b:BYTE small:SHORT n:INTEGER label:STRING[4] ENDSTRUCTURE',decl='a:row_t f:FILE')
        self.assertEqual(p.run()['A'],dict(B=255,SMALL=-7,N=42,LABEL='abcd'))

    def test_reverse_binary_fields_keep_existing_byte_order(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'input':struct.pack('>ii',7,9)}))
        p,_=build("SET_FILE_ATR(f,ATR_REVERSE) OPEN FILE f('RB','input') READ f(a)",context=ctx);self.assertEqual(p.run()['A'],[7,9])

    def test_invalid_late_text_value_keeps_outputs_and_cursor(self):
        p,_=file('7 bad','a[1]=77 a[2]=88 READ f(a)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['A'],p._state.values['F'].position,p._state.values['F'].status),([77,88],0,1))

    def test_short_binary_record_keeps_outputs_and_cursor(self):
        p,_=file(struct.pack('<i',7),'a[1]=77 a[2]=88 READ f(a)',mode='RB')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['A'],p._state.values['F'].position),([77,88],0))

    def test_directory_file_uses_same_leaf_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'input').write_bytes(b'7 9');ctx=rt.ExecutionContext(files=rt.DirectoryFiles(folder));p,_=build("OPEN FILE f('RO','input') READ f(a) CLOSE FILE f",context=ctx)
            self.assertEqual(p.run()['A'],[7,9])

    def test_device_file_uses_same_leaf_contract(self):
        ctx=rt.ExecutionContext(files=rt.DeviceFiles({'FR:':dict(capacity=1024)},initial={'FR:input':'7 9'}));p,_=build("OPEN FILE f('RO','FR:input') READ f(a) CLOSE FILE f",context=ctx);self.assertEqual(p.run()['A'],[7,9])

    def test_textinput_and_json_callback_metadata_are_equivalent(self):
        p,_=build(read=rt.TextInput('7 9'));q,_=build(values=[7,9]);self.assertEqual(p.run()['A'],q.run()['A']);self.assertEqual(p.read_requests,q.read_requests)


class AggregateReadCooperativeTests(unittest.TestCase):
    def test_waiting_serial_read_uses_same_flat_scalar_parser(self):
        bank,ctx=serial(b'7 ')
        def sleeper(_):bank.feed(2,b'9\n')
        p,_=build("OPEN FILE f('RO','P2:') READ f(a,CR) CLOSE FILE f",context=ctx,sleep=sleeper);self.assertEqual(p.run()['A'],[7,9])

    def test_waiting_serial_cancel_retains_all_outputs_and_input_prefix(self):
        bank,ctx=serial(b'7 ')
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build("OPEN FILE f('RO','P2:') a[1]=77 a[2]=88 READ f(a,CR) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper)
        self.assertEqual((p.run()['A'],p.snapshot()['S']),([77,88],6));self.assertEqual(bank.snapshot()[2]['input'],b'7 ')

    def test_waiting_pipe_read_reuses_captured_fields(self):
        bank=pipe_bank(b'7 ');ctx=rt.ExecutionContext(file_pipes=bank)
        def sleeper(_):bank.feed('LOG',b'9\n')
        p,_=build("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') READ f(a,CR) CLOSE FILE f",context=ctx,sleep=sleeper);self.assertEqual(p.run()['A'],[7,9])

    def test_keyboard_line_read_uses_same_flat_scalar_values(self):
        ctx=keyboard_context(keys=line_keys('7 9'));p,_=build("OPEN FILE f('RW','KB:TPKB') READ f(a,CR) CLOSE FILE f",context=ctx,sleep=lambda _:None);self.assertEqual(p.run()['A'],[7,9])

    def test_pause_before_status_format_keeps_already_captured_aggregate(self):
        routines='ROUTINE width:INTEGER BEGIN visits=visits+1 PAUSE RETURN 1 END width'
        p,_=build('visits=0 READ(a,n::width())',values=[7,9,1],routines=routines,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['A'],[7,9]);self.assertEqual(p.snapshot()['VISITS'],1)

    def test_context_json_saves_completed_aggregate_values(self):
        p,_=build(values=[7,9]);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)

    def test_linked_reference_formal_reads_caller_storage(self):
        main='PROGRAM MAIN VAR a:ARRAY[2]OF INTEGER ROUTINE take(data:ARRAY OF INTEGER) FROM LIB BEGIN take(a) END MAIN'
        lib='PROGRAM LIB ROUTINE take(data:ARRAY OF INTEGER) BEGIN READ(data) END take BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate(options=dict(read=lambda request:[7,9]));self.assertEqual(project.run('MAIN')['MAIN']['values']['A'],[7,9])

    def test_byname_exact_record_formal_reads_explicit_bank(self):
        spec=('STRUCTURE','ITEM_T',(('VALUE',('INTEGER',)),('LABEL',('STRING',4))));ctx=rt.ExecutionContext();ctx.variables.define('CACHE','ITEM',spec)
        p,_=build("take(BYNAME('CACHE','ITEM',n))",values=[7,'hi'],context=ctx,routines='ROUTINE take(data:item_t) BEGIN READ(data) END take');p.run();self.assertEqual(ctx.variables.bindings['CACHE','ITEM'].raw().values,dict(VALUE=7,LABEL='hi'))

    def test_report_describes_flat_order_limits_and_native_boundary(self):
        _,r=build(values=[7,9]);policy=r.report['aggregate_read_policy'];self.assertFalse(policy['controller_validated']);self.assertIn('1024',policy['validation']);self.assertTrue(r.report['reads'][0]['destinations'][0]['aggregate'])


class AggregateReadAdditionalTests(unittest.TestCase):
    def test_array_of_configs_checks_all_turns_before_any_output(self):
        values=[0,0,0,False,False,False,False,0,0,8,False,False,False,False]
        p,_=build(values=values,decl='a:ARRAY[2]OF CONFIG')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p._state.values['A'].values[0].values['CFG_TURN_NO1'],rt.UNINITIALIZED)

    def test_xyz_external_metadata_uses_ordinary_declared_leaf_order(self):
        spec=('XYZWPREXT',);count=rt._validate_data_schema(spec)
        # Typed flags and turns use their exact scalar domains rather than an
        # invented pose/config parser or external-axis model.
        value=rt.initial_value(spec);target=rt.Reference(spec,{'value':value},'value')
        with rt._numeric_scope('pythonic'):group=rt.capture_aggregate_read_target(target,[])
        data=[False if item[0].spec==('BOOLEAN',) else 0 if item[0].spec[0] in ('INTEGER','SHORT','BYTE') else 2.5 for item in group]
        p,_=build('READ(a)',values=data,decl='a:XYZWPREXT');p.run();self.assertEqual(len(group),count);self.assertEqual(p.snapshot()['A']['X'],2.5)

    def test_waiting_binary_serial_cancel_keeps_complete_first_field(self):
        bank,ctx=serial(struct.pack('<i',7))
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build("OPEN FILE f('RB','P2:') a[1]=77 a[2]=88 READ f(a) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper)
        self.assertEqual((p.run()['A'],p.snapshot()['S']),([77,88],6));self.assertEqual(bank.snapshot()[2]['input'],struct.pack('<i',7))

    def test_waiting_pipe_cancel_keeps_array_and_prefix(self):
        bank=pipe_bank(b'7 ');ctx=rt.ExecutionContext(file_pipes=bank)
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') a[1]=77 a[2]=88 READ f(a,CR) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper)
        self.assertEqual((p.run()['A'],p.snapshot()['S']),([77,88],6));self.assertEqual(bank.snapshot(),{'PIP:LOG':b'7 '})

    def test_keyboard_cancel_keeps_all_array_leaves(self):
        ctx=keyboard_context(events=[dict(key='7'),dict(key=' '),dict(key='ENTER',at_ms=100)])
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build("OPEN FILE f('RW','KB:TPKB') a[1]=77 a[2]=88 READ f(a,CR) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper)
        self.assertEqual((p.run()['A'],p.snapshot()['S']),([77,88],6))

    def test_wrong_config_parent_schema_fails_before_callback(self):
        p,_=build(values=[0,0,0,False,False,False,False],decl='a:CONFIG');p._state.values['A'].types['EXTRA']=('INTEGER',)
        with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_reference_subclass_cannot_bypass_aggregate_capture(self):
        class Derived(rt.Reference):pass
        p,_=build();ref=p._state.reference('A');target=Derived(ref.spec,ref.storage,ref.key)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.capture_aggregate_read_target(target,[])

    def test_array_element_record_captures_only_selected_storage(self):
        p,_=build('READ(items[2])',values=[7,'hi'],decl='items:ARRAY[2]OF item_t');v=p.run()['ITEMS'];self.assertEqual(v[1],dict(VALUE=7,LABEL='hi'));self.assertEqual(v[0]['VALUE'],{'uninitialized':True})

    def test_record_nested_array_preserves_captured_array_object(self):
        p,_=build('READ(a)',values=[7,9],prefix='TYPE row_t=STRUCTURE data:ARRAY[2]OF INTEGER ENDSTRUCTURE',decl='a:row_t');array=p._state.values['A'].values['DATA'];field=rt.index_reference(array,1)
        p.run();self.assertIs(p._state.values['A'].values['DATA'],array);self.assertEqual(field.raw(),7)


if __name__=='__main__':unittest.main()
