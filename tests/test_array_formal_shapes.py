"""Authored fixed/mixed ARRAY constraints, aliases and concrete entry checks."""
import ast
import json
from pathlib import Path
import unittest

from karel2py import translate,translate_project,load_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


U={'uninitialized':True}
ROOT=Path(__file__).resolve().parents[1]


def build(body='work(a)',*,decl='a:ARRAY[2,3]OF INTEGER n,e,s:INTEGER',prefix='',routines='',**adapters):
    result=translate(f'PROGRAM T\n{prefix}\nVAR {decl}\n{routines}\nBEGIN {body} END T',filename='authored.kl')
    ast.parse(result.python_source,feature_version=(3,11));json.dumps(result.report,allow_nan=False)
    namespace={'__name__':'array_formal_test'};exec(result.python_source,namespace)
    return namespace['Program'](**adapters),result


class ArrayFormalSourceTests(unittest.TestCase):
    def test_fixed_and_mixed_two_dimensional_masks_borrow_original(self):
        for shape in ('2,3','2,*','*,3','2,\n*'):
            with self.subTest(shape=shape):
                program,result=build(routines=f'ROUTINE work(p:ARRAY[{shape}]OF INTEGER) BEGIN p[2,3]=7 END work')
                self.assertEqual(program.run()['A'],[[U,U,U],[U,U,7]])
                self.assertEqual(result.report['array_formal_uses'][0]['parameter'],'P')

    def test_one_and_three_dimensional_masks(self):
        for declaration,shape,index,expected in (
                ('a:ARRAY[2]OF INTEGER','2','2',[U,7]),
                ('a:ARRAY[2,1,2]OF INTEGER','2,*,2','2,1,2',[[[U,U]],[[U,7]]])):
            with self.subTest(shape=shape):
                program,_=build(decl=declaration,routines=f'ROUTINE work(p:ARRAY[{shape}]OF INTEGER) BEGIN p[{index}]=7 END work')
                self.assertEqual(program.run()['A'],expected)

    def test_inline_layers_normalize_before_fixed_constraints(self):
        program,_=build(routines='ROUTINE work(p:ARRAY[2]OF ARRAY[*]OF INTEGER) BEGIN p[2][3]=7 END work')
        self.assertEqual(program.run()['A'][1][2],7)

    def test_module_forward_constants_and_pure_calls_define_interface(self):
        program,result=build(prefix='CONST count=ROUND(SQRT(square)) square=4',
            routines='ROUTINE work(p:ARRAY[count,STR_LEN(\'abc\')]OF INTEGER) BEGIN p[2,3]=7 END work')
        self.assertEqual(program.run()['A'][1][2],7)
        self.assertEqual(result.report['array_formal_uses'][0]['logical_dimensions'],[2,3])

    def test_local_variables_are_not_needed_to_infer_formal_sizes(self):
        routines='ROUTINE work(p:ARRAY[2,*]OF INTEGER) VAR local:INTEGER BEGIN local=ARRAY_LEN(p,2) n=local p[2,local]=7 END work'
        program,_=build(routines=routines)
        values=program.run();self.assertEqual((values['N'],values['A'][1][2]),(3,7))

    def test_grouped_values_remain_private_with_partial_data(self):
        program,_=build('work((a))',routines='ROUTINE work(p:ARRAY[2,*]OF INTEGER) BEGIN p[2,3]=7 n=p[2,3] END work')
        values=program.run();self.assertEqual(values['N'],7);self.assertEqual(values['A'],[[U,U,U],[U,U,U]])

    def test_ordinary_row_values_and_explicit_byname_references_stay_distinct(self):
        routine='ROUTINE work(p:ARRAY[3]OF INTEGER) BEGIN p[1]=7 END work'
        private,_=build('work(a[1])',routines=routine)
        self.assertEqual(private.run()['A'],[[U,U,U],[U,U,U]])
        shared,_=build("work(BYNAME('','A[1]',e))",routines=routine)
        self.assertEqual(shared.run()['A'],[[7,U,U],[U,U,U]])

    def test_string_capacity_is_inherited_for_direct_element_type(self):
        program,_=build(decl='a:ARRAY[2]OF STRING[3]',routines="ROUTINE work(p:ARRAY[2]OF STRING) BEGIN p[1]='abcd' END work")
        self.assertEqual(program.run()['A'],['abc',U])

    def test_named_components_and_record_fields_keep_their_types(self):
        program,result=build(decl='a:ARRAY[2,3]OF row_t',prefix='TYPE row_t=ARRAY[2]OF INTEGER',
            routines='ROUTINE work(p:ARRAY[2,*]OF row_t) BEGIN p[2,3,2]=7 END work')
        self.assertEqual(program.run()['A'][1][2],[U,7])
        self.assertEqual(result.report['array_formal_uses'][0]['logical_dimensions'],[2,None,2])
        program,_=build(decl='a:ARRAY[2]OF row_t',prefix='TYPE row_t=STRUCTURE count:INTEGER other:REAL ENDSTRUCTURE',
            routines='ROUTINE work(p:ARRAY[2]OF row_t) BEGIN p[2].count=7 END work')
        self.assertEqual(program.run()['A'][1],{'COUNT':7,'OTHER':U})

    def test_existing_numeric_conversion_stays_a_private_argument(self):
        program,_=build('a[1]=3 work(a)',decl='a:ARRAY[2]OF INTEGER value:REAL',
            routines='ROUTINE work(p:ARRAY[2]OF REAL) BEGIN p[1]=9.5 value=p[1] END work')
        values=program.run();self.assertEqual((values['A'],values['VALUE']),([3,U],9.5))

    def test_whole_array_assignment_cannot_resize_concrete_borrowed_storage(self):
        program,_=build('a[1,1]=7 work(a)',decl='a:ARRAY[2,3]OF INTEGER b:ARRAY[2,4]OF INTEGER',
            routines='ROUTINE work(p:ARRAY[2,*]OF INTEGER) BEGIN p=b END work')
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual(program.snapshot()['A'],[[7,U,U],[U,U,U]])

    def test_whole_assignment_preserves_named_actual_identity(self):
        program,_=build('b[1]=7 b[2]=9 work(a)',prefix='TYPE row_t=ARRAY[2]OF INTEGER',
            decl='a:row_t b:ARRAY[2]OF INTEGER',routines='ROUTINE work(p:ARRAY[2]OF INTEGER) BEGIN p=b END work')
        self.assertEqual(program.run()['A'],[7,9])
        self.assertEqual(rt.array_identity(program._state.values['A'].spec),'ROW_T')

    def test_fixed_formal_array_can_be_returned_as_an_independent_result(self):
        program,_=build('a[1]=7 b=work(a) b[1]=9',decl='a,b:ARRAY[2]OF INTEGER',
            routines='ROUTINE work(p:ARRAY[2]OF INTEGER):ARRAY[*]OF INTEGER BEGIN RETURN p END work')
        values=program.run();self.assertEqual((values['A'],values['B']),([7,U],[9,U]))


class ArrayFormalForwardingTests(unittest.TestCase):
    ROUTINES='ROUTINE inner(p:ARRAY[2]OF INTEGER) BEGIN p[1]=7 END inner ROUTINE outer(p:ARRAY OF INTEGER) BEGIN n=1 inner(p) END outer'

    def test_wildcard_forwarding_keeps_alias_and_records_runtime_guard(self):
        program,result=build('outer(a)',decl='a:ARRAY[2]OF INTEGER n:INTEGER',routines=self.ROUTINES)
        self.assertEqual(program.run()['A'],[7,U])
        row=result.report['array_forward_uses'][0]
        self.assertTrue(row['alias_retained']);self.assertEqual((row['body'],row['routine']),('OUTER','INNER'))

    def test_wrong_concrete_shape_fails_before_inner_body_and_unwinds_frames(self):
        program,_=build('outer(a)',decl='a:ARRAY[3]OF INTEGER n:INTEGER',routines=self.ROUTINES)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Parameter binding'):program.run()
        self.assertEqual(program.snapshot(),{'A':[U,U,U],'N':1})
        self.assertEqual(program._state.call_depth,0)

    def test_grouped_forwarding_keeps_existing_value_semantics(self):
        program,result=build('outer(a)',decl='a:ARRAY[2]OF INTEGER n:INTEGER',routines=self.ROUTINES.replace('inner(p) END outer','inner((p)) END outer'))
        self.assertEqual(program.run()['A'],[U,U])
        self.assertEqual(result.report['array_forward_uses'],[])

    def test_forwarded_writes_remain_visible_to_counter_effect_proof(self):
        with self.assertRaises(TranslationError) as caught:
            build('FOR a[1]=1 TO 2 DO outer(a) ENDFOR',decl='a:ARRAY[2]OF INTEGER n:INTEGER',routines=self.ROUTINES)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_byname_size_mismatch_preserves_entry_and_original_cells(self):
        program,_=build("e=99 work(BYNAME('','A[1]',e))",routines='ROUTINE work(p:ARRAY[2]OF INTEGER) BEGIN p[1]=7 END work')
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual(program.snapshot()['E'],99)
        self.assertEqual(program.snapshot()['A'],[[U,U,U],[U,U,U]])

    def test_pause_resume_and_stop_keep_original_borrowed_cells(self):
        routine='ROUTINE work(p:ARRAY[2]OF INTEGER) BEGIN p[1]=7 PAUSE p[2]=9 END work'
        program,_=build(decl='a:ARRAY[2]OF INTEGER',routines=routine)
        with self.assertRaises(rt.KarelPause):program.run()
        self.assertEqual(program.snapshot()['A'],[7,U])
        self.assertEqual(program.resume()['A'],[7,9])
        stopped,_=build(decl='a:ARRAY[2]OF INTEGER',routines=routine)
        with self.assertRaises(rt.KarelPause):stopped.run()
        stopped.stop();self.assertEqual(stopped.snapshot()['A'],[7,U])


class ArrayFormalResourcesAndLinks(unittest.TestCase):
    def test_fixed_file_row_borrows_original_descriptors(self):
        context=rt.ExecutionContext(files=rt.MemoryFiles())
        program,_=build('work(a[1])',decl='a:ARRAY[2,2]OF FILE',context=context,
            routines="ROUTINE work(p:ARRAY[2]OF FILE) BEGIN OPEN FILE p[1]('RW','row.txt') WRITE p[1](7,CR) CLOSE FILE p[1] END work")
        program.run();self.assertEqual(bytes(context.files.files['row.txt']),b' 7\n')
        self.assertFalse(program.snapshot()['A'][0][0]['open'])

    def test_fixed_path_bank_mutates_original_header(self):
        program,_=build(prefix='TYPE data_t=STRUCTURE count:INTEGER ENDSTRUCTURE path_t=PATH PATHHEADER=data_t',
            decl='a:ARRAY[2]OF path_t',routines='ROUTINE work(p:ARRAY[2]OF path_t) BEGIN p[2].count=7 END work')
        self.assertEqual(program.run()['A'][1]['data'],{'COUNT':7})

    def test_fixed_queue_bank_keeps_original_buffer_binding(self):
        program,_=build(decl='a:ARRAY[2]OF QUEUE_TYPE buffer:ARRAY[4]OF INTEGER sequence,status:INTEGER',
            routines='ROUTINE work(p:ARRAY[2]OF QUEUE_TYPE) BEGIN INIT_QUEUE(p[2]) APPEND_QUEUE(7,p[2],buffer,sequence,status) END work')
        values=program.run();self.assertEqual(values['A'][1],{'initialized':True,'entries':[[1,7]]})
        self.assertEqual(values['BUFFER'],[7,0,0,0]);self.assertEqual((values['SEQUENCE'],values['STATUS']),(1,0))

    def test_linked_fixed_interfaces_accept_equivalent_inline_spelling(self):
        main='PROGRAM MAIN VAR a:ARRAY[2,3]OF INTEGER ROUTINE work(p:ARRAY[2]OF ARRAY[*]OF INTEGER) FROM LIB BEGIN work(a) END MAIN'
        lib='PROGRAM LIB ROUTINE work(p:ARRAY[2,*]OF INTEGER) BEGIN p[2,3]=7 END work BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate()
        self.assertEqual(project.run('MAIN')['MAIN']['values']['A'][1][2],7)

    def test_linked_fixed_and_wildcard_declarations_still_must_match_exactly(self):
        main='PROGRAM MAIN ROUTINE work(p:ARRAY[2]OF INTEGER) FROM LIB BEGIN END MAIN'
        lib='PROGRAM LIB ROUTINE work(p:ARRAY[*]OF INTEGER) BEGIN END work BEGIN END LIB'
        with self.assertRaisesRegex(ValueError,'mismatch'):translate_project({'main':main,'lib':lib}).instantiate()


class ArrayFormalGuardsAndReports(unittest.TestCase):
    def test_authored_examples_have_independent_expected_snapshots(self):
        from tools.run_examples import run_example
        for name in ('array_formal_masks','array_formal_forwarding','array_formal_values'):
            with self.subTest(name=name):run_example(ROOT/'examples'/(name+'.kl'))
        folder=ROOT/'examples/array_formal_shapes_linked'
        instance=load_project(folder).instantiate()
        self.assertEqual(instance.run('MAIN'),json.loads((folder/'expected.json').read_bytes()))

    def reject(self,spec,code='E_SIZE',prefix=''):
        with self.assertRaises(TranslationError) as caught:build(prefix=prefix,routines=f'ROUTINE work(p:{spec}) BEGIN END work',body='')
        self.assertEqual(caught.exception.code,code)

    def test_invalid_sizes_and_minimum_capacity_are_rejected(self):
        for spec in ('ARRAY[0]OF INTEGER','ARRAY[-1,*]OF INTEGER','ARRAY[TRUE]OF INTEGER','ARRAY[1.5]OF INTEGER','ARRAY[32768,*]OF INTEGER'):
            with self.subTest(spec=spec):self.reject(spec)
        self.reject('ARRAY[200,200]OF INTEGER','E_ARRAY_CAPACITY')
        self.reject('ARRAY[32767,*]OF JOINTPOS2','E_ARRAY_CAPACITY')

    def test_interface_dimensions_cannot_read_parameter_local_or_unknown_values(self):
        self.reject('ARRAY[missing]OF INTEGER','E_CONSTANT')
        with self.assertRaises(TranslationError) as caught:
            build(body='',routines='ROUTINE work(p:ARRAY[local]OF INTEGER) CONST local=2 BEGIN END work')
        self.assertEqual(caught.exception.code,'E_CONSTANT')

    def test_known_shape_mismatch_is_not_an_equal_count_reshape(self):
        with self.assertRaises(TranslationError) as caught:build(routines='ROUTINE work(p:ARRAY[3,2]OF INTEGER) BEGIN END work')
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_logical_rank_and_string_formal_capacity_guards_remain(self):
        self.reject('ARRAY[2,1,1,1]OF INTEGER','E_ARRAY_RANK')
        self.reject('ARRAY[2]OF STRING[0]','E_SIZE')
        self.reject('ARRAY[1,1,1]OF row_t','E_ARRAY_RANK',prefix='TYPE row_t=ARRAY[1]OF INTEGER')

    def test_legacy_fixed_formal_syntax_stays_rejected(self):
        with self.assertRaises(TranslationError) as caught:legacy_translate('PROGRAM T ROUTINE work(p:ARRAY[2]OF INTEGER) BEGIN END work BEGIN END T')
        self.assertEqual(caught.exception.code,'E_PARAMETERS')

    def test_generic_runtime_type_compatibility_is_not_weakened(self):
        self.assertFalse(rt.parameter_accepts(('ARRAY',2,rt.INTEGER),('ARRAY',None,rt.INTEGER)))
        self.assertFalse(rt.parameter_accepts(('ARRAY',2,rt.INTEGER),('ARRAY',3,rt.INTEGER)))

    def test_include_metadata_retains_original_declaration_position(self):
        source='PROGRAM T CONST count=2 VAR a:ARRAY[2,3]OF INTEGER\n%INCLUDE routine.inc\nBEGIN work(a) END T'
        result=translate(source,filename='main.kl',includes={'routine.inc':'ROUTINE work(p:ARRAY[count,*]OF INTEGER) BEGIN p[2,3]=7 END work'})
        row=result.report['array_formal_uses'][0]
        self.assertEqual((row['source_file'],row['source_line'],row['fixed_dimensions'],row['wildcard_dimensions']),('routine.inc',1,[1],[2]))
        self.assertFalse(result.report['array_formal_policy']['controller_validated'])


if __name__=='__main__':unittest.main()
