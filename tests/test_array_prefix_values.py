"""Authored row/plane value copies; complete element references stay exact."""
import struct
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate

U={'uninitialized':True}
B={'unknown_byte':True}


def build(body,*,decl='m:ARRAY[2,2]OF INTEGER row:ARRAY[2]OF INTEGER n:INTEGER',types='',routines='',labelled=False,cooperative=False,translator=translate,**options):
    result=translator('PROGRAM MAIN '+types+' VAR '+decl+' '+routines+' BEGIN '+('unused:: ' if labelled else '')+body+' END MAIN',**({'cooperative':True} if cooperative else {}))
    ns={'__name__':'array_prefix_test'};exec(result.python_source,ns)
    return ns['Program'](**options),result


def execute(body,**options):return build(body,**options)[0].run()


def output(program):return [row['text'] for row in program._state.write_requests]


class PrefixStorageTests(unittest.TestCase):
    def test_matrix_row_is_independent(self):
        v=execute('m[1,1]=7 row=m[1] m[1,1]=9 row[2]=42');self.assertEqual((v['M'][0],v['ROW']),([9,U],[7,42]))

    def test_cube_plane_retains_suffix_dimensions(self):
        p,_=build('cube[2,1,2]=7 plane=cube[2]',decl='cube:ARRAY[2,2,3]OF INTEGER plane:ARRAY[2,3]OF INTEGER');v=p.run();self.assertEqual(v['PLANE'],[[U,7,U],[U,U,U]])
        self.assertEqual(p._state.raw('PLANE').shape,(2,3))

    def test_cube_row_accepts_mixed_bracket_groups(self):
        v=execute('cube[2,1,2]=7 row=cube[2][1]',decl='cube:ARRAY[2,2,2]OF INTEGER row:ARRAY[2]OF INTEGER');self.assertEqual(v['ROW'],[U,7])

    def test_named_flat_outer_produces_anonymous_suffix(self):
        p,result=build('m[1,2]=7 row=m[1]',types='TYPE matrix_t=ARRAY[2,2]OF INTEGER',decl='m:matrix_t row:ARRAY[2]OF INTEGER');self.assertEqual(p.run()['ROW'],[U,7])
        self.assertEqual(result.report['array_prefix_values'][0]['selected_type_spec'],('ARRAY',2,('INTEGER',)))

    def test_prefix_inside_flat_named_component(self):
        v=execute('a[2,1,2]=7 row=a[2,1]',types='TYPE plane_t=ARRAY[2,2]OF INTEGER',decl='a:ARRAY[2]OF plane_t row:ARRAY[2]OF INTEGER');self.assertEqual(v['ROW'],[U,7])

    def test_partial_outer_component_retains_named_children(self):
        p,_=build('a[1,2,1]=7 rows=a[1]',types='TYPE row_t=ARRAY[2]OF INTEGER',decl='a:ARRAY[2,2]OF row_t rows:ARRAY[2]OF row_t');self.assertEqual(p.run()['ROWS'],[[U,U],[7,U]])
        self.assertEqual(p._state.raw('ROWS').values[0].spec[3],'ROW_T')

    def test_flat_generic_can_copy_named_actual_boundary(self):
        v=execute('m[1,2]=7 work(m)',types='TYPE row_t=ARRAY[2]OF INTEGER',decl='m:ARRAY[2]OF row_t row:ARRAY[2]OF INTEGER',routines='ROUTINE work(p:ARRAY[*,*]OF INTEGER) BEGIN row=p[1] END work');self.assertEqual(v['ROW'],[U,7])

    def test_record_fields_and_nested_arrays_detach(self):
        types='TYPE item_t=STRUCTURE values:ARRAY[2]OF INTEGER ENDSTRUCTURE'
        v=execute('m[1,1].values[1]=7 row=m[1] row[1].values[1]=9',types=types,decl='m:ARRAY[2,2]OF item_t row:ARRAY[2]OF item_t');self.assertEqual((v['M'][0][0]['VALUES'],v['ROW'][0]['VALUES']),([7,U],[9,U]))


class PrefixDataTests(unittest.TestCase):
    def test_bounded_string_receiver_uses_existing_conversion(self):
        v=execute("m[1,1]='abcd' row=m[1]",decl='m:ARRAY[2,2]OF STRING[4] row:ARRAY[2]OF STRING[2]');self.assertEqual(v['ROW'],['ab',U])

    def test_unknown_byte_leaves_remain_unknown(self):
        v=execute('m[1,1]=7 row=m[1]',decl='m:ARRAY[2,2]OF BYTE row:ARRAY[2]OF BYTE');self.assertEqual(v['ROW'],[7,B])

    def test_short_sentinel_remains_missing(self):
        self.assertEqual(execute('row=m[1]',decl='m:ARRAY[2,2]OF SHORT row:ARRAY[2]OF SHORT')['ROW'],[U,U])

    def test_missing_nested_record_container_remains_rejected(self):
        p,_=build('row=m[1]',types='TYPE item_t=STRUCTURE value:INTEGER ENDSTRUCTURE',decl='m:ARRAY[2,2]OF item_t row:ARRAY[2]OF item_t');p._state.raw('M').values[0]=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.snapshot()['ROW'],[{'VALUE':U},{'VALUE':U}])

    def test_position_data_copy_does_not_need_geometry(self):
        v=execute('m[1,1].location.x=7 row=m[1] row[1].location.x=9',decl='m:ARRAY[2,2]OF POSITION row:ARRAY[2]OF POSITION');self.assertEqual((v['M'][0][0]['LOCATION']['X'],v['ROW'][0]['LOCATION']['X']),(7.0,9.0))

    def test_joint_children_are_independent(self):
        v=execute('m[1,1][1]=7 row=m[1] row[1][1]=9',decl='m:ARRAY[2,2]OF JOINTPOS2 row:ARRAY[2]OF JOINTPOS2');self.assertEqual((v['M'][0][0]['axes'],v['ROW'][0]['axes']),([7.0,U],[9.0,U]))

    def test_numeric_receiver_promotion_is_existing_source_conversion(self):
        self.assertEqual(execute('m[1,1]=7 row=m[1]',decl='m:ARRAY[2,2]OF INTEGER row:ARRAY[2]OF REAL')['ROW'],[7.0,U])

    def test_record_receiver_conversion_retains_its_field_schema(self):
        types='TYPE a_t=STRUCTURE text:STRING[4] ENDSTRUCTURE b_t=STRUCTURE text:STRING[2] ENDSTRUCTURE'
        v=execute("m[1,1].text='abcd' row=m[1]",types=types,decl='m:ARRAY[2,2]OF a_t row:ARRAY[2]OF b_t');self.assertEqual(v['ROW'][0]['TEXT'],'ab')


class PrefixEffectTests(unittest.TestCase):
    def test_index_functions_evaluate_once_in_order(self):
        v=execute('n=0 cube[1,2,1]=7 row=cube[first()][second()]',decl='cube:ARRAY[2,2,2]OF INTEGER row:ARRAY[2]OF INTEGER n:INTEGER',routines='ROUTINE first:INTEGER BEGIN n=n*10+1 RETURN 1 END first ROUTINE second:INTEGER BEGIN n=n*10+2 RETURN 2 END second');self.assertEqual((v['N'],v['ROW']),(12,[7,U]))

    def test_index_effects_finish_before_selected_value_is_copied(self):
        v=execute('m[1,1]=7 row=m[pick()]',routines='ROUTINE pick:INTEGER BEGIN m[1,1]=9 RETURN 1 END pick');self.assertEqual(v['ROW'],[9,U])

    def test_later_argument_cannot_change_captured_row(self):
        routines='ROUTINE change:INTEGER BEGIN m[1,1]=9 RETURN 0 END change ROUTINE work(p:ARRAY OF INTEGER;dummy:INTEGER) BEGIN n=p[1] END work'
        v=execute('m[1,1]=7 work(m[1],change())',routines=routines);self.assertEqual((v['N'],v['M'][0][0]),(7,9))

    def test_rhs_copy_precedes_target_index_effect(self):
        v=execute('m[1,1]=7 rows[pick()]=m[1]',types='TYPE row_t=ARRAY[2]OF INTEGER',decl='m:ARRAY[2,2]OF INTEGER rows:ARRAY[2]OF row_t',routines='ROUTINE pick:INTEGER BEGIN m[1,1]=9 RETURN 1 END pick');self.assertEqual(v['ROWS'][0],[7,U])

    def test_source_failure_preserves_destination_and_skips_target(self):
        p,_=build('n=0 row[1]=42 row=m[1]',decl='m:ARRAY[2,2]OF INTEGER row:ARRAY[2]OF INTEGER n:INTEGER');p._state.raw('M').values[-1]='bad'
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.snapshot()['ROW'],[42,U])

    def test_all_supplied_indexes_run_before_bounds_failure(self):
        p,_=build('n=0 row=cube[first()][second()]',decl='cube:ARRAY[2,2,2]OF INTEGER row:ARRAY[2]OF INTEGER n:INTEGER',routines='ROUTINE first:INTEGER BEGIN n=n*10+1 RETURN 0 END first ROUTINE second:INTEGER BEGIN n=n*10+2 RETURN 1 END second')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.snapshot()['N'],12)

    def test_mutable_private_argument_does_not_guard_source_counter(self):
        routines='ROUTINE edit(p:ARRAY OF INTEGER) BEGIN p[1]=99 END edit'
        v=execute('n=0 FOR m[1,1]=1 TO 3 DO edit(m[1]) n=n+m[1,1] ENDFOR',routines=routines);self.assertEqual(v['N'],6);self.assertEqual(v['M'][0][0],U)

    def test_pausing_index_is_not_replayed(self):
        p,_=build('n=0 m[1,1]=7 row=m[pick()]',cooperative=True,routines='ROUTINE pick:INTEGER BEGIN n=n+1 PAUSE RETURN 1 END pick')
        with self.assertRaises(rt.KarelPause):p.run()
        p._state.raw('M').set((1,1),9)
        v=p.resume();self.assertEqual((v['N'],v['ROW']),(1,[9,U]))

    def test_private_argument_survives_pause_without_copyback(self):
        p,_=build('m[1,1]=7 edit(m[1])',cooperative=True,labelled=True,routines='ROUTINE edit(p:ARRAY OF INTEGER) BEGIN p[1]=99 PAUSE n=p[1] END edit')
        with self.assertRaises(rt.KarelPause):p.run()
        p._state.raw('M').set((1,1),42)
        v=p.resume();self.assertEqual((v['N'],v['M'][0][0]),(99,42))

    def test_dispatcher_and_structured_code_share_copy_behavior(self):
        results=[execute('m[1,1]=7 row=m[1] row[1]=9',labelled=value) for value in (False,True)];self.assertEqual(results[0],results[1])


class PrefixInterfaceTests(unittest.TestCase):
    def test_bare_prefix_argument_is_a_private_value(self):
        v=execute('m[1,1]=7 edit(m[1])',routines='ROUTINE edit(p:ARRAY OF INTEGER) BEGIN p[1]=99 n=p[1] END edit');self.assertEqual((v['M'][0][0],v['N']),(7,99))

    def test_complete_named_boundary_still_borrows_storage(self):
        v=execute('m[1,1]=7 edit(m[1])',types='TYPE row_t=ARRAY[2]OF INTEGER',decl='m:ARRAY[2]OF row_t',routines='ROUTINE edit(p:row_t) BEGIN p[1]=99 END edit');self.assertEqual(v['M'][0][0],99)

    def test_return_inherits_concrete_generic_suffix_shape(self):
        v=execute('m[1,2]=7 row=make(m)',routines='ROUTINE make(p:ARRAY[*,*]OF INTEGER):ARRAY OF INTEGER BEGIN RETURN p[1] END make');self.assertEqual(v['ROW'],[U,7])

    def test_return_inherits_string_capacity(self):
        p,_=build("m[1,1]='abcd' row=make(m)",decl='m:ARRAY[2,2]OF STRING[4] row:ARRAY[2]OF STRING[4]',routines='ROUTINE make(p:ARRAY[*,*]OF STRING):ARRAY OF STRING BEGIN RETURN p[1] END make');self.assertEqual(p.run()['ROW'],['abcd',U])

    def test_linked_generic_argument_is_private(self):
        result=translate_project({'main.kl':'PROGRAM MAIN VAR m:ARRAY[2,2]OF INTEGER ROUTINE edit(p:ARRAY OF INTEGER) FROM LIB BEGIN m[1,1]=7 edit(m[1]) END MAIN','lib.kl':'PROGRAM LIB ROUTINE edit(p:ARRAY OF INTEGER) BEGIN p[1]=99 END edit BEGIN END LIB'})
        instance=result.instantiate();instance.run('MAIN');self.assertEqual(instance.programs['MAIN']._state.snapshot()['M'][0][0],7)

    def test_formatted_write_captures_prefix_before_format_function(self):
        p,_=build('m[1,1]=10 m[1,2]=15 WRITE(m[1]::width()::16)',routines='ROUTINE width:INTEGER BEGIN m[1,1]=99 RETURN 3 END width');p.run();self.assertEqual(output(p),[' 0A 0F'])

    def test_binary_file_output_uses_prefix_as_separate_fields(self):
        context=rt.ExecutionContext(files=rt.MemoryFiles({}))
        p,_=build("m[1,1]=7 m[1,2]=9 OPEN FILE f('WB','values.bin') WRITE f(m[1]::2) CLOSE FILE f",decl='m:ARRAY[2,2]OF INTEGER f:FILE',context=context);p.run();self.assertEqual(bytes(context.files.files['values.bin']),struct.pack('<hh',7,9))

    def test_report_has_source_located_independent_values(self):
        _,result=build('row=m[1]');rows=result.report['array_prefix_values'];self.assertEqual(len(rows),1);self.assertTrue(rows[0]['independent_value'] and rows[0]['evaluated_once']);self.assertGreater(rows[0]['column'],0);self.assertFalse(result.report['array_prefix_policy']['controller_validated'])


class PrefixGuardTests(unittest.TestCase):
    def reject(self,body,code='E_ARRAY_RANK',**options):
        with self.assertRaises(TranslationError) as caught:build(body,**options)
        self.assertEqual(caught.exception.code,code,str(caught.exception))

    def test_partial_assignment_target_stays_rejected(self):self.reject('m[1]=row')
    def test_partial_read_destination_stays_rejected(self):self.reject('READ(m[1])')
    def test_partial_service_output_stays_rejected(self):self.reject("GET_VAR(n,'MAIN','M[1]',m[1],n)")
    def test_position_orientation_does_not_become_writable(self):self.reject('row=m[1] row[1].normal.x=1','E_POSITION_READ_ONLY',decl='m:ARRAY[2,2]OF POSITION row:ARRAY[2]OF POSITION')
    def test_wrong_index_type_stays_rejected(self):self.reject('row=m[TRUE]','E_TYPE')
    def test_prefix_is_not_a_scalar_or_record(self):
        self.reject('n=m[1]','E_TYPE');self.reject('n=m[1].field','E_TYPE')

    def test_strict_and_runtime_reference_helpers_remain_full_rank(self):
        self.reject('row=m[1]',translator=legacy_translate)
        array=rt.Array(('ARRAY',(2,2),rt.INTEGER))
        with self.assertRaises(rt.KarelRuntimeError):rt.index_reference(array,1)
        with self.assertRaises(rt.KarelRuntimeError):rt.array_prefix_value(array,1,array.spec)

    def test_resources_and_overlarge_schemas_reject_before_copy(self):
        for spec in (('ARRAY',(2,2),('FILE',)),('ARRAY',(2,20000),rt.INTEGER)):
            array=object.__new__(rt.Array);array.spec=spec;array.shape=rt.array_shape(spec);array.values=[]
            with self.subTest(spec=spec),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.array_prefix_value(array,1,spec,73)

    def test_malformed_actual_schema_is_a_source_located_error(self):
        array=rt.Array(('ARRAY',(2,2),rt.INTEGER));array.spec=None
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError) as caught:rt.array_prefix_value(array,1,('ARRAY',(2,2),rt.INTEGER),73)
        self.assertEqual(caught.exception.line,73)

    def test_runtime_prefix_rejects_malformed_storage_and_resources(self):
        array=rt.Array(('ARRAY',(2,2),rt.INTEGER));array.values.pop()
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.array_prefix_value(array,1,array.spec,73)
        self.assertIsNone(rt.array_prefix_type(('ARRAY',(2,2),rt.INTEGER),True))
