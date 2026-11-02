"""Authored statement-only row/plane updates and captured original-cell input."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_array_prefix_values import build,execute,U,B
from tests.test_aggregate_read import file as input_file
from tests.test_file_cancellation import serial,pending
from tests.test_pipe_attributes import bank as pipe_bank
from tests.test_keyboard import context as keyboard_context
from tests.test_keyboard_file_read import line_keys
from tests.test_kinematic_arrays import values,forward_adapter
from tests.test_kinematic_assignments import callback_context
from tests.test_joint_interoperability import model_context
from tests.test_cartesian_interfaces import snapshot_x


class PrefixAssignmentStorageTests(unittest.TestCase):
    def test_row_assignment_changes_original_cells(self):self.assertEqual(execute('row[1]=7 row[2]=9 m[1]=row')['M'],[[7,9],[U,U]])

    def test_plane_assignment_retains_dimensions(self):
        v=execute('plane[2,3]=7 cube[2]=plane',decl='cube:ARRAY[2,2,3]OF INTEGER plane:ARRAY[2,3]OF INTEGER');self.assertEqual(v['CUBE'][1],[[U,U,U],[U,U,7]])

    def test_chained_cube_prefix_assignment(self):
        v=execute('row[1]=7 cube[2][1]=row',decl='cube:ARRAY[2,2,2]OF INTEGER row:ARRAY[2]OF INTEGER');self.assertEqual(v['CUBE'][1][0],[7,U])

    def test_overlapping_source_is_copied_before_publication(self):
        v=execute('m[1,1]=7 m[1,2]=9 m[2]=m[1] m[1]=m[2]');self.assertEqual(v['M'],[[7,9],[7,9]])

    def test_unselected_rows_remain_unchanged(self):
        v=execute('m[2,1]=42 row[1]=7 m[1]=row');self.assertEqual(v['M'],[[7,U],[42,U]])

    def test_captured_scalar_alias_survives_row_replacement(self):
        v=execute('m[1,1]=9 row[1]=7 work(m[1,1])',routines='ROUTINE work(p:INTEGER) BEGIN m[1]=row n=p p=42 END work');self.assertEqual((v['N'],v['M'][0][0]),(7,42))

    def test_nested_record_alias_survives_row_replacement(self):
        types='TYPE item_t=STRUCTURE values:ARRAY[2]OF INTEGER ENDSTRUCTURE'
        v=execute('m[1,1].values[1]=9 row[1].values[1]=7 work(m[1,1].values[1])',types=types,decl='m:ARRAY[2,2]OF item_t row:ARRAY[2]OF item_t n:INTEGER',routines='ROUTINE work(p:INTEGER) BEGIN m[1]=row n=p p=42 END work');self.assertEqual((v['N'],v['M'][0][0]['VALUES'][0]),(7,42))

    def test_both_statement_engines_share_prefix_assignment(self):
        self.assertEqual(execute('row[1]=7 m[1]=row'),execute('row[1]=7 m[1]=row',labelled=True))


class PrefixAssignmentConversionTests(unittest.TestCase):
    def test_string_capacity_uses_actual_receiver(self):
        v=execute("row[1]='abcd' m[1]=row",decl='m:ARRAY[2,2]OF STRING[2] row:ARRAY[2]OF STRING[4]');self.assertEqual(v['M'][0],['ab',U])

    def test_numeric_promotion(self):
        self.assertEqual(execute('row[1]=7 m[1]=row',decl='m:ARRAY[2,2]OF REAL row:ARRAY[2]OF INTEGER')['M'][0],[7.0,U])

    def test_integral_narrowing(self):
        self.assertEqual(execute('row[1]=255 row[2]=0 m[1]=row',decl='m:ARRAY[2,2]OF BYTE row:ARRAY[2]OF INTEGER')['M'][0],[255,0])

    def test_bad_last_narrow_value_has_no_partial_publication(self):
        p,_=build('m[1,1]=42 row[1]=7 row[2]=256 m[1]=row',decl='m:ARRAY[2,2]OF BYTE row:ARRAY[2]OF INTEGER')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][0],[42,B])

    def test_partial_scalar_values_are_copied(self):self.assertEqual(execute('m[1,2]=42 row[1]=7 m[1]=row')['M'][0],[7,U])

    def test_unknown_byte_contents_are_preserved(self):
        self.assertEqual(execute('m[1,2]=42 row[1]=7 m[1]=row',decl='m:ARRAY[2,2]OF BYTE row:ARRAY[2]OF BYTE')['M'][0],[7,B])

    def test_record_schema_and_string_conversion(self):
        types='TYPE a_t=STRUCTURE text:STRING[4] ENDSTRUCTURE b_t=STRUCTURE text:STRING[2] ENDSTRUCTURE'
        self.assertEqual(execute("row[1].text='abcd' m[1]=row",types=types,decl='m:ARRAY[2,2]OF b_t row:ARRAY[2]OF a_t')['M'][0][0]['TEXT'],'ab')

    def test_flat_generic_target_retains_named_actual_suffix(self):
        p,_=build('row[1]=7 work(m)',types='TYPE row_t=ARRAY[2]OF INTEGER',decl='m:ARRAY[2]OF row_t row:ARRAY[2]OF INTEGER',routines='ROUTINE work(p:ARRAY[*,*]OF INTEGER) BEGIN p[1]=row END work');self.assertEqual(p.run()['M'][0],[7,U]);self.assertEqual(p._state.raw('M').values[0].spec[3],'ROW_T')


class PrefixAssignmentEffectTests(unittest.TestCase):
    def test_rhs_runs_before_target_and_each_once(self):
        routines='ROUTINE source:ARRAY OF INTEGER BEGIN n=n*10+1 RETURN row END source ROUTINE pick:INTEGER BEGIN n=n*10+2 RETURN 1 END pick'
        v=execute('n=0 row[1]=7 m[pick()]=source()',routines=routines);self.assertEqual((v['N'],v['M'][0]),(12,[7,U]))

    def test_rhs_is_detached_before_target_mutates_source(self):
        v=execute('row[1]=7 m[pick()]=row',routines='ROUTINE pick:INTEGER BEGIN row[1]=99 RETURN 1 END pick');self.assertEqual((v['ROW'][0],v['M'][0][0]),(99,7))

    def test_multiple_target_indexes_run_once_in_order(self):
        routines='ROUTINE first:INTEGER BEGIN n=n*10+1 RETURN 2 END first ROUTINE second:INTEGER BEGIN n=n*10+2 RETURN 1 END second'
        v=execute('n=0 row[1]=7 cube[first()][second()]=row',decl='cube:ARRAY[2,2,2]OF INTEGER row:ARRAY[2]OF INTEGER n:INTEGER',routines=routines);self.assertEqual((v['N'],v['CUBE'][1][0]),(12,[7,U]))

    def test_all_target_indexes_run_before_bounds_failure(self):
        routines='ROUTINE first:INTEGER BEGIN n=n*10+1 RETURN 0 END first ROUTINE second:INTEGER BEGIN n=n*10+2 RETURN 1 END second'
        p,_=build('n=0 cube[first()][second()]=row',decl='cube:ARRAY[2,2,2]OF INTEGER row:ARRAY[2]OF INTEGER n:INTEGER',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],12)

    def test_invalid_rhs_skips_target_functions(self):
        p,_=build('n=0 m[pick()]=row',routines='ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 1 END pick');p._state.raw('ROW').values[-1]='bad'
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_pausing_target_keeps_rhs_copy_and_call_count(self):
        p,_=build('n=0 row[1]=7 m[pick()]=row',cooperative=True,routines='ROUTINE pick:INTEGER BEGIN n=n+1 PAUSE RETURN 1 END pick')
        with self.assertRaises(rt.KarelPause):p.run()
        p._state.raw('ROW').set(1,99);v=p.resume();self.assertEqual((v['N'],v['M'][0][0]),(1,7))

    def test_target_index_change_does_not_retarget_selected_row(self):
        v=execute('n=1 row[1]=7 m[pick()]=row',routines='ROUTINE pick:INTEGER BEGIN n=2 RETURN 1 END pick');self.assertEqual((v['N'],v['M']),(2,[[7,U],[U,U]]))

    def test_malformed_receiver_fails_before_any_row_publication(self):
        p,_=build('row[1]=7 m[1]=row');p._state.raw('M').values[-1]='bad'
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p._state.raw('M').values[0],rt.UNINITIALIZED)


class PrefixReadStorageTests(unittest.TestCase):
    def test_typed_input_writes_original_row(self):self.assertEqual(execute('READ(m[2])',read=lambda request:[7,9])['M'],[[U,U],[7,9]])

    def test_plane_expansion_remaps_cr(self):
        seen=[]
        def read(request):seen.append(request);return [1,2,3,4]
        v=execute('READ(cube[1],CR)',decl='cube:ARRAY[2,2,2]OF INTEGER',read=read);self.assertEqual(v['CUBE'][0],[[1,2],[3,4]]);self.assertEqual(seen[0]['line_breaks'],[4])

    def test_repeated_aliases_use_last_valid_response(self):
        self.assertEqual(execute('READ(m[1],m[1,1])',read=lambda request:[7,9,42])['M'][0],[42,9])

    def test_formatted_text_input_uses_scalar_domains(self):
        self.assertEqual(execute('READ(m[1]::2::16,CR)',read=rt.TextInput('0A0F\n'))['M'][0],[10,15])

    def test_record_fields_expand_in_declaration_order(self):
        v=execute('READ(m[1])',types='TYPE item_t=STRUCTURE value:INTEGER flag:BOOLEAN ENDSTRUCTURE',decl='m:ARRAY[2,2]OF item_t',read=lambda request:[7,True,9,False]);self.assertEqual(v['M'][0],[{'VALUE':7,'FLAG':True},{'VALUE':9,'FLAG':False}])

    def test_joint_fields_expand_in_axis_order(self):
        v=execute('READ(m[1])',decl='m:ARRAY[2,2]OF JOINTPOS2',read=lambda request:[1,2,3,4]);self.assertEqual([r['axes'] for r in v['M'][0]],[[1.,2.],[3.,4.]])

    def test_generic_formal_reads_named_actual_rows(self):
        v=execute('work(m)',types='TYPE row_t=ARRAY[2]OF INTEGER',decl='m:ARRAY[2]OF row_t',routines='ROUTINE work(p:ARRAY[*,*]OF INTEGER) BEGIN READ(p[2]) END work',read=lambda request:[7,9]);self.assertEqual(v['M'][1],[7,9])

    def test_capture_precedes_own_format_function(self):
        v=execute('n=1 READ(m[n]::width())',routines='ROUTINE width:INTEGER BEGIN n=2 RETURN 2 END width',read=lambda request:[7,9]);self.assertEqual((v['N'],v['M']),(2,[[7,9],[U,U]]))


class PrefixReadAtomicityTests(unittest.TestCase):
    def test_invalid_last_typed_value_preserves_whole_row(self):
        p,_=build('m[1,1]=42 READ(m[1])',read=lambda request:[7,True])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][0],[42,U])

    def test_callback_exception_preserves_row(self):
        def fail(request):raise ValueError('authored callback failure')
        p,_=build('m[1,1]=42 READ(m[1])',read=fail)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][0],[42,U])

    def test_bad_unselected_storage_suppresses_input(self):
        seen=[];p,_=build('READ(m[1])',read=lambda request:seen.append(request) or [7,9]);p._state.raw('M').values[-1]='bad'
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(seen,[])

    def test_wrong_response_length_preserves_row(self):
        p,_=build('m[1,1]=42 READ(m[1])',read=lambda request:[7])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][0],[42,U])

    def test_config_turn_domain_is_checked_before_any_field(self):
        p,_=build('READ(m[1])',decl='m:ARRAY[2,1]OF CONFIG',read=lambda request:[8,0,0,False,False,False])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][0][0]['CFG_TURN_NO1'],U)

    def test_read_1024_scalar_limit_accepts_exact_boundary(self):
        v=execute('READ(m[1])',decl='m:ARRAY[2,1024]OF INTEGER',read=lambda request:list(range(1024)));self.assertEqual(v['M'][0],list(range(1024)))

    def test_read_expansion_limit_rejects_before_input(self):
        seen=[];p,_=build('READ(m[1])',decl='m:ARRAY[2,1025]OF INTEGER',read=lambda request:seen.append(request) or [])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(seen,[])

    def test_callback_root_replacement_does_not_retarget_captured_cells(self):
        p=None;old=None
        def read(request):p._state.values['M']=rt.Array(p._state.types['M']);return [7,9]
        p,_=build('READ(m[1])',read=read);old=p._state.raw('M');v=p.run();self.assertEqual(v['M'],[[U,U],[U,U]]);self.assertEqual(old.snapshot()[0],[7,9])


class PrefixReadTransportTests(unittest.TestCase):
    def test_text_file_reads_selected_row(self):
        p,_=input_file(b'0709\n','READ f(m[1]::2,CR)',decl='f:FILE m:ARRAY[2,2]OF INTEGER');self.assertEqual(p.run()['M'][0],[7,9])

    def test_binary_file_reads_selected_row(self):
        p,_=input_file(struct.pack('<hh',7,9),'READ f(m[1]::2)',mode='RB',decl='f:FILE m:ARRAY[2,2]OF INTEGER');self.assertEqual(p.run()['M'][0],[7,9])

    def test_rooted_directory_file_reads_selected_row(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'input').write_bytes(b'7 9\n');ctx=rt.ExecutionContext(files=rt.DirectoryFiles(folder))
            self.assertEqual(execute("OPEN FILE f('RO','input') READ f(m[1],CR) CLOSE FILE f",decl='f:FILE m:ARRAY[2,2]OF INTEGER',context=ctx)['M'][0],[7,9])

    def test_finite_serial_read(self):
        bank,ctx=serial(b'7 9\n',final=True);p,_=build("OPEN FILE f('RO','P2:') READ f(m[2],CR) CLOSE FILE f",decl='f:FILE m:ARRAY[2,2]OF INTEGER',context=ctx);self.assertEqual(p.run()['M'][1],[7,9])

    def test_waiting_serial_feed_preserves_selected_row(self):
        bank,ctx=serial();instance,p,f=pending(ctx,"OPEN FILE f('RO','P2:') n=1 READ f(m[n]::2,CR) CLOSE FILE f",decl='f:FILE m:ARRAY[2,2]OF INTEGER n:INTEGER')
        p._state.values['N']=2;bank.feed(2,b'0709\n');instance.scheduler.run();self.assertEqual(p.snapshot()['M'],[[7,9],[U,U]])

    def test_serial_cancellation_preserves_all_prefix_outputs(self):
        bank,ctx=serial(b'07');body="OPEN FILE f('RO','P2:') m[1,1]=42 CONDITION[1]: WHEN elapsed>=10 DO CANCEL FILE f ENDCONDITION CONNECT TIMER TO elapsed ENABLE CONDITION[1] READ f(m[1]::2,CR) status=IO_STATUS(f) CLOSE FILE f"
        p,_=build(body,decl='f:FILE m:ARRAY[2,2]OF INTEGER elapsed,status:INTEGER',context=ctx,sleep=lambda _:None);v=p.run();self.assertEqual((v['M'][0],v['STATUS']),([42,U],6));self.assertEqual(bank.to_config()['ports']['2']['input']['hex'],'3037')

    def test_waiting_pipe_uses_existing_scalar_contract(self):
        pipes=pipe_bank(b'0709\n');ctx=rt.ExecutionContext(file_pipes=pipes)
        v=execute("SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) OPEN FILE f('RO','PIP:LOG') READ f(m[1]::2,CR) CLOSE FILE f",decl='f:FILE m:ARRAY[2,2]OF INTEGER',context=ctx,sleep=lambda _:None);self.assertEqual(v['M'][0],[7,9])

    def test_injected_keyboard_file_input(self):
        ctx=keyboard_context(keys=line_keys('0709'));v=execute("OPEN FILE f('RW','KB:TPKB') READ f(m[1]::2,CR) CLOSE FILE f",decl='f:FILE m:ARRAY[2,2]OF INTEGER',context=ctx,sleep=lambda _:None);self.assertEqual(v['M'][0],[7,9])


class PrefixKinematicAssignmentTests(unittest.TestCase):
    def setup_program(self,body='m[1]=row',*,first='JOINTPOS2',second='XYZWPR',context=None):
        p,r=build(body,decl=f'm:ARRAY[2,2]OF {second} row:ARRAY[2]OF {first} n:INTEGER',context=context if context is not None else model_context((0.,90.)))
        p._state.values['ROW']=values(2 if first=='JOINTPOS2' else first);return p,r

    def test_forward_conversion_into_each_cartesian_prefix(self):
        for kind in ('POSITION','XYZWPR','XYZWPREXT'):
            p,_=self.setup_program(second=kind);v=p.run();self.assertAlmostEqual(snapshot_x(v['M'][0][0],kind),100.,places=8)

    def test_inverse_conversion_uses_explicit_current_seed(self):
        p,_=self.setup_program(first='XYZWPR',second='JOINTPOS2');self.assertEqual(p.run()['M'][0][0]['axes'],[0.,90.])

    def test_missing_model_preserves_entire_receiver(self):
        p,_=self.setup_program(context=rt.ExecutionContext())
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][0][0]['X'],U)

    def test_bad_late_adapter_result_has_no_partial_row_write(self):
        calls=[]
        def forward(*args):
            result=forward_adapter(calls)(*args)
            if len(calls)==2:raise ValueError('authored second conversion failure')
            return result
        p,_=self.setup_program(context=callback_context(forward=forward))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(calls),2);self.assertEqual(p.snapshot()['M'][0][0]['X'],U)

    def test_adapter_root_replacement_retains_captured_target_cells(self):
        calls=[];p=None
        def forward(*args):
            p._state.values['M']=rt.Array(p._state.types['M']);return forward_adapter(calls)(*args)
        p,_=self.setup_program(context=callback_context(forward=forward));old=p._state.raw('M');v=p.run();self.assertEqual(v['M'][0][0]['X'],U);self.assertEqual(old.snapshot()[0][0]['X'],1.)

    def test_adapter_malformed_storage_failure_preserves_unwritten_cells(self):
        calls=[];p=None
        def forward(*args):
            if not calls:p._state.raw('M').values.pop()
            return forward_adapter(calls)(*args)
        p,_=self.setup_program(context=callback_context(forward=forward));old=p._state.raw('M')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(old.values[0].values['X'],rt.UNINITIALIZED)

    def test_partial_inverse_source_fails_before_any_adapter(self):
        p,_=self.setup_program(first='XYZWPR',second='JOINTPOS2');p._state.raw('ROW').values[1].values['X']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['M'][0][0]['axes'],[U,U])

    def test_transitive_model_service_effects_are_reported_before_emission(self):
        routines='ROUTINE leaf VAR local:ARRAY[2,2]OF XYZWPR BEGIN local[1]=row END leaf ROUTINE parent BEGIN leaf END parent'
        _,result=build('parent',decl='row:ARRAY[2]OF JOINTPOS2',routines=routines)
        rows=result.report['routine_effects']
        self.assertTrue(rows['LEAF']['potential_service_requests'] and rows['PARENT']['potential_service_requests'])

    def test_conversion_runs_after_target_index_effects(self):
        calls=[];p=None
        def forward(*args):self.assertEqual(p._state.values['N'],42);return forward_adapter(calls)(*args)
        ctx=callback_context(forward=forward);p,_=build('n=0 m[pick()]=row',decl='m:ARRAY[2,2]OF XYZWPR row:ARRAY[2]OF JOINTPOS2 n:INTEGER',routines='ROUTINE pick:INTEGER BEGIN n=42 RETURN 1 END pick',context=ctx);p._state.values['ROW']=values(2);p.run();self.assertEqual(len(calls),2)


class PrefixTargetGuardTests(unittest.TestCase):
    def reject(self,body,code,**options):
        with self.assertRaises(TranslationError) as caught:build(body,**options)
        self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_generic_runtime_reference_stays_full_rank(self):
        array=rt.Array(('ARRAY',(2,2),rt.INTEGER))
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.index_reference(array,1)
        with self.assertRaises(rt.KarelRuntimeError):rt.array_prefix_target(array,1,array.spec)

    def test_service_output_does_not_gain_prefix_aliases(self):self.reject("CNV_STR_INT('7',m[1])",'E_ARRAY_RANK')
    def test_active_counter_root_rejects_prefix_assignment(self):self.reject('FOR m[1,1]=1 TO 2 DO m[2]=row ENDFOR','E_FOR_COUNTER')
    def test_active_counter_root_rejects_prefix_read(self):self.reject('FOR m[1,1]=1 TO 2 DO READ(m[2]) ENDFOR','E_FOR_COUNTER')
    def test_position_prefix_orientation_input_remains_rejected(self):self.reject('READ(m[1,1].normal)','E_POSITION_READ_ONLY',decl='m:ARRAY[2,2]OF POSITION')
    def test_shape_mismatch_does_not_reshape(self):self.reject('m[1]=row','E_TYPE',decl='m:ARRAY[2,2]OF INTEGER row:ARRAY[1,2]OF INTEGER')
    def test_computed_read_receiver_remains_rejected(self):self.reject('READ(make()[1])','E_READ_ITEM',routines='ROUTINE make:ARRAY[2,2]OF INTEGER BEGIN RETURN m END make')

    def test_report_marks_statement_capture_without_value_ownership(self):
        _,r=build('m[1]=row READ(m[2])');self.assertEqual(len(r.report['array_prefix_targets']),2);self.assertTrue(all(not row['independent_value'] for row in r.report['array_prefix_targets']));self.assertFalse(r.report['array_prefix_target_policy']['controller_validated']);json.dumps(r.report)
