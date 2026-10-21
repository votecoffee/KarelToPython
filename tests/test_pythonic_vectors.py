"""Pythonic vector construction, signs, association and checked ownership."""
import json
from pathlib import Path
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


DECLARATIONS = 'a,b,c,d: VECTOR r,seen: REAL flag: BOOLEAN n,i: INTEGER trace: STRING[64]'
MARK = 'ROUTINE mark(p: INTEGER): REAL BEGIN trace=trace+CHR(64+p) RETURN p END mark'


def compile_program(body, *, declarations=DECLARATIONS, types='', routines='', translator=translate, **context):
    source = f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T'
    result = translator(source, filename='pythonic_vectors.kl')
    namespace = {'__name__': 'vector_expressions_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](**context), result


def execute(body, **kwargs): return compile_program(body, **kwargs)[0].run()


def vector(x,y,z): return {'X':float(x), 'Y':float(y), 'Z':float(z)}


class ConstructorTests(unittest.TestCase):
    def test_integer_components(self): self.assertEqual(execute('a=VEC(1,2,3)')['A'], vector(1,2,3))
    def test_mixed_numeric_components(self): self.assertEqual(execute('a=VEC(1,0.1,-3.5)')['A'], vector(1,.1,-3.5))
    def test_zero_vector(self): self.assertEqual(execute('a=VEC(0,0,0)')['A'], vector(0,0,0))
    def test_lowercase_constructor(self): self.assertEqual(execute('a=vec(1,2,3)')['A'], vector(1,2,3))
    def test_component_expressions(self): self.assertEqual(execute('a=VEC(1+2,SQRT(2),7/2)')['A'], vector(3,2**.5,3.5))
    def test_narrow_components_promote(self):
        state = execute('data[1]=255 data[2]=7 a=VEC(data[1],data[2],0)', declarations=DECLARATIONS+' data: ARRAY[2] OF BYTE')
        self.assertEqual(state['A'], vector(255,7,0))
    def test_maxint_component_is_a_real_value(self):
        self.assertEqual(execute('a=VEC(MAXINT,MININT,0)')['A'], vector(2147483647,-2147483648,0))
    def test_field_read(self): self.assertEqual(execute('r=VEC(7,8,9).y')['R'], 8.0)
    def test_grouped_field_read(self): self.assertEqual(execute('r=(VEC(7,8,9)).z')['R'], 9.0)
    def test_alias_storage(self):
        self.assertEqual(execute('value=VEC(1,2,3)', types='TYPE direction_t=VECTOR', declarations='value: direction_t')['VALUE'], vector(1,2,3))
    def test_array_and_structure_storage(self):
        state = execute('items[1]=VEC(1,2,3) box.value=VEC(4,5,6)',
                        types='TYPE box_t=STRUCTURE value: VECTOR ENDSTRUCTURE', declarations='items: ARRAY[1] OF VECTOR box: box_t')
        self.assertEqual(state, {'ITEMS':[vector(1,2,3)], 'BOX':{'VALUE':vector(4,5,6)}})
    def test_constructor_in_return(self):
        self.assertEqual(execute('a=make()', routines='ROUTINE make: VECTOR BEGIN RETURN VEC(1,2,3) END make')['A'], vector(1,2,3))
    def test_constructor_value_argument_is_writable(self):
        state = execute('change(VEC(1,2,3))', routines='ROUTINE change(v: VECTOR) BEGIN v.x=8 a=v END change')
        self.assertEqual(state['A'], vector(8,2,3))
    def test_constructor_field_argument_owns_temporary(self):
        state = execute('change(VEC(1,2,3).x)', routines='ROUTINE change(v: REAL) BEGIN v=8 r=v END change')
        self.assertEqual(state['R'], 8.0)
    def test_constructor_copy_independence(self):
        self.assertEqual(execute('a=VEC(1,2,3) b=a a.x=99')['B'], vector(1,2,3))
    def test_whole_replacement_preserves_captured_field(self):
        state = execute('a=VEC(1,2,3) change(a,a.x)',
                        routines='ROUTINE change(v: VECTOR; x: REAL) BEGIN v=VEC(4,5,6) seen=x x=9 END change')
        self.assertEqual((state['A'],state['SEEN']), (vector(9,5,6),4.0))
    def test_constructor_inside_for(self):
        self.assertEqual(execute('FOR i=1 TO 2 DO a=VEC(i,0,0) ENDFOR')['A'], vector(2,0,0))
    def test_length_expression(self):
        self.assertEqual(execute('a=VEC(3,4,0) r=SQRT(a@a)')['R'], 5.0)


class UnaryAndProductTests(unittest.TestCase):
    def test_unary_plus(self): self.assertEqual(execute('a=VEC(1,-2,3) b=+a')['B'], vector(1,-2,3))
    def test_unary_minus(self): self.assertEqual(execute('a=VEC(1,-2,3) b=-a')['B'], vector(-1,2,-3))
    def test_repeated_unary_minus(self): self.assertEqual(execute('a=VEC(1,2,3) b=-(-a)')['B'], vector(1,2,3))
    def test_unary_constructor(self): self.assertEqual(execute('a=-VEC(1,2,3)')['A'], vector(-1,-2,-3))
    def test_unary_plus_copy_is_independent(self):
        self.assertEqual(execute('a=VEC(1,2,3) b=+a b.x=9')['A'], vector(1,2,3))
    def test_unary_value_parameter_copy(self):
        state = execute('a=VEC(1,2,3) change(-a)', routines='ROUTINE change(v: VECTOR) BEGIN v.x=9 b=v END change')
        self.assertEqual((state['A'],state['B']), (vector(1,2,3),vector(9,-2,-3)))
    def test_unary_multiplication_precedence(self): self.assertEqual(execute('a=-VEC(1,2,3)*2')['A'], vector(-2,-4,-6))
    def test_unary_cross_precedence(self): self.assertEqual(execute('a=-VEC(1,0,0)#VEC(0,1,0)')['A'], vector(0,0,-1))
    def test_unary_addition_precedence(self): self.assertEqual(execute('a=-VEC(1,2,3)+VEC(4,5,6)')['A'], vector(3,3,3))
    def test_chained_cross_associates_left(self):
        self.assertEqual(execute('a=VEC(1,2,3)#VEC(4,5,6)#VEC(7,8,10)')['A'], vector(84,9,-66))
    def test_grouped_cross_changes_association(self):
        self.assertEqual(execute('a=VEC(1,2,3)#(VEC(4,5,6)#VEC(7,8,10))')['A'], vector(-12,9,-2))
    def test_cross_then_dot_triple_product(self):
        self.assertEqual(execute('r=VEC(1,2,3)#VEC(4,5,6)@VEC(7,8,10)')['R'], -3.0)
    def test_cross_precedes_scalar_multiplication(self):
        self.assertEqual(execute('a=2*VEC(1,2,3)#VEC(4,5,6)')['A'], vector(-6,12,-6))
    def test_parallel_cross_still_supported(self): self.assertEqual(execute('a=VEC(1,2,3)#VEC(2,4,6)')['A'], vector(0,0,0))
    def test_zero_dot(self): self.assertEqual(execute('r=VEC(0,0,0)@VEC(1,2,3)')['R'], 0.0)
    def test_constructor_equality(self): self.assertTrue(execute('flag=VEC(1,2,3)=VEC(1,2,3)')['FLAG'])


class VectorEffectTests(unittest.TestCase):
    def test_constructor_arguments_evaluated_once_left_to_right(self):
        state = execute("trace='' a=VEC(mark(1),mark(2),mark(3))", routines=MARK)
        self.assertEqual((state['TRACE'],state['A']), ('ABC',vector(1,2,3)))
    def test_constructor_captures_components_before_later_mutation(self):
        state = execute('r=1 a=VEC(r,touch(),r)', routines='ROUTINE touch: REAL BEGIN r=9 RETURN 2 END touch')
        self.assertEqual(state['A'], vector(1,2,9))
    def test_constructor_error_skips_later_expressions(self):
        program, _ = compile_program("trace='' a=VEC(mark(1),1 DIV 0,mark(3))", routines=MARK)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['TRACE'], 'A')
        self.assertEqual(program.snapshot()['A'], vector_snapshot_uninitialized())
    def test_constructor_failure_preserves_destination(self):
        program, _ = compile_program('a=VEC(7,8,9) a=VEC(1,1/0,3)')
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertEqual(program.snapshot()['A'], vector(7,8,9))
        self.assertIn('line', str(caught.exception))
    def test_unary_failure_preserves_destination(self):
        program, _ = compile_program('b=VEC(7,8,9) b=-a')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()
        self.assertEqual(program.snapshot()['B'], vector(7,8,9))
    def test_failed_constructor_retains_prior_destination_argument_mutation(self):
        program, _ = compile_program('a=VEC(7,8,9) a=VEC(touch(),1/0,3)',
                                    routines='ROUTINE touch: REAL BEGIN a.x=99 RETURN 1 END touch')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['A'], vector(99,8,9))
    def test_product_chain_captures_left_before_later_effect(self):
        state = execute('a=VEC(1,0,0) b=VEC(0,1,0) c=a#b#change()',
                        routines='ROUTINE change: VECTOR BEGIN a=VEC(9,9,9) RETURN VEC(1,0,0) END change')
        self.assertEqual((state['C'],state['A']), (vector(0,1,0),vector(9,9,9)))
    def test_unary_operand_called_once(self):
        state = execute('n=0 a=-make()', routines='ROUTINE make: VECTOR BEGIN n=n+1 RETURN VEC(1,2,3) END make')
        self.assertEqual((state['N'],state['A']), (1,vector(-1,-2,-3)))
    def test_error_unwinds_nested_routine_frames(self):
        program, _ = compile_program('outer()', routines='ROUTINE inner: VECTOR BEGIN RETURN VEC(1,1/0,3) END inner '
                                                       'ROUTINE outer BEGIN a=inner() END outer')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program._state.local_frames,program._state.call_depth), ([],0))
    def test_constructor_arguments_retain_for_write_checks(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR i=1 TO 2 DO a=VEC(change(),0,0) ENDFOR',
                            routines='ROUTINE change: REAL BEGIN i=7 RETURN 1 END change')
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')
    def test_constructor_internal_host_output_effect_is_reported(self):
        _, result = compile_program('a=build()', routines="ROUTINE component: REAL BEGIN WRITE('x') RETURN 1 END component "
                                                       'ROUTINE build: VECTOR BEGIN RETURN VEC(component(),0,0) END build')
        self.assertTrue(result.report['routine_effects']['BUILD']['potential_output_requests'])
    def test_unary_rejects_unknown_position_orientation(self):
        # Unknown orientation is never synthesized by an expression.
        program, _ = compile_program('a=-pose.normal', declarations=DECLARATIONS+' pose: POSITION')
        with self.assertRaises(rt.KarelRuntimeError): program.run()


def vector_snapshot_uninitialized(): return {field:{'uninitialized':True} for field in ('X','Y','Z')}


class ConstructorNamespaceAndGuardTests(unittest.TestCase):
    def reject(self, body, code='E_TYPE', **options):
        with self.assertRaises(TranslationError) as caught: compile_program(body, **options)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.filename, 'pythonic_vectors.kl')

    def test_wrong_arity(self):
        for args in ('','1','1,2','1,2,3,4'):
            with self.subTest(args=args): self.reject('a=VEC('+args+')', 'E_ARGUMENTS')
    def test_wrong_component_types(self):
        for item in ('ON', "'x'", 'a'):
            with self.subTest(item=item): self.reject('a=VEC(1,'+item+',3)')
    def test_invalid_left_associated_products(self):
        for expression in ('a@b#c', 'a@b@c'):
            with self.subTest(expression=expression): self.reject('r='+expression)
    def test_wrong_constructor_field(self): self.reject('r=VEC(1,2,3).w', 'E_FIELD')
    def test_pos_constructor_arity(self): self.reject('a=POS(1,2,3)', 'E_ARGUMENTS')
    def test_unary_not_vector(self): self.reject('a=NOT VEC(1,2,3)')
    def test_position_orientation_writes_stay_blocked(self):
        self.reject('pose.normal=VEC(1,2,3)', 'E_POSITION_READ_ONLY', declarations=DECLARATIONS+' pose: POSITION')
    def test_internal_vec_function_precedes_constructor(self):
        state = execute('r=VEC(4)', routines='ROUTINE VEC(p: INTEGER): REAL BEGIN RETURN p+1 END VEC')
        self.assertEqual(state['R'], 5.0)
    def test_internal_vec_vector_result_field(self):
        state = execute('r=VEC().x', routines='ROUTINE VEC: VECTOR BEGIN a.x=7 a.y=8 a.z=9 RETURN a END VEC')
        self.assertEqual(state['R'], 7.0)
    def test_user_vec_arity_checked(self):
        self.reject('r=VEC(1,2,3)', 'E_ARGUMENTS', routines='ROUTINE VEC(p: INTEGER): REAL BEGIN RETURN p END VEC')
    def test_vec_storage_and_constructor_use_call_context(self):
        state = execute('vec=7 a=VEC(vec,2,3)', declarations=DECLARATIONS+' vec: INTEGER')
        self.assertEqual(state['A'], vector(7,2,3))
    def test_legacy_internal_vec_routine_remains_supported(self):
        state = execute('r=VEC(4)', routines='ROUTINE VEC(p: INTEGER): REAL BEGIN RETURN p END VEC', translator=legacy_translate)
        self.assertEqual(state['R'], 4.0)
    def test_legacy_constructor_guard_remains(self): self.reject('a=VEC(1,2,3)', 'E_CALL', translator=legacy_translate)
    def test_legacy_sign_guard_remains(self): self.reject('a=-b', translator=legacy_translate)
    def test_legacy_chain_guard_remains(self): self.reject('a=b#c#d', 'E_VECTOR_ASSOCIATIVITY', translator=legacy_translate)
    def test_report_constructor_locations_and_policy(self):
        _, result = compile_program('a=VEC(1,2,3) b=-a c=a#b#a')
        report = json.loads(json.dumps(result.report))
        self.assertEqual(len(report['vector_constructors']), 1)
        self.assertEqual(report['vector_constructors'][0]['argument_order'], ['x','y','z'])
        self.assertTrue(report['vector_constructors'][0]['independent_value'])
        self.assertIn('left to right', report['vector_policy']['precedence'])
        self.assertFalse(report['vector_policy']['controller_validated'])
    def test_internal_vec_is_not_reported_as_constructor(self):
        _, result = compile_program('r=VEC(4)', routines='ROUTINE VEC(p: INTEGER): REAL BEGIN RETURN p END VEC')
        self.assertEqual(result.report['vector_constructors'], [])


class VectorRuntimeTests(unittest.TestCase):
    def test_constructor_arity_guard(self):
        with rt._numeric_scope('pythonic'), self.assertRaisesRegex(rt.KarelRuntimeError,'three arguments'):
            rt.builtin('VEC',[1,2],17)
    def test_constructor_rejects_invalid_components(self):
        for value in (True,'x',float('nan'),float('inf'),rt.UNINITIALIZED,rt.UNKNOWN_BYTE):
            with self.subTest(value=value), rt._numeric_scope('pythonic'), self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'):
                rt.builtin('VEC',[1,value,3],17)
    def test_constructor_values_are_fresh(self):
        with rt._numeric_scope('pythonic'):
            first=rt.builtin('VEC',[1,2,3]); second=rt.builtin('VEC',[1,2,3]); first.values['X']=9
            self.assertIsNot(first,second)
            self.assertEqual(second.values['X'],1.0)
    def test_unary_plus_is_independent(self):
        with rt._numeric_scope('pythonic'):
            value=rt.builtin('VEC',[1,2,3]); other=rt.unary('+',value); other.values['X']=9
            self.assertEqual(value.values['X'],1.0)
    def test_unary_rejects_malformed_shape(self):
        with rt._numeric_scope('pythonic'):
            value=rt.builtin('VEC',[1,2,3]); del value.values['Z']
            with self.assertRaisesRegex(rt.KarelRuntimeError,'three-component'): rt.unary('-',value,17)
    def test_unary_rejects_unknown_components(self):
        with rt._numeric_scope('pythonic'), self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):
            rt.unary('+',rt.initial_value(('VECTOR',)),17)
    def test_strict_constructor_remains_blocked(self):
        with rt._numeric_scope('strict'), self.assertRaisesRegex(rt.KarelRuntimeError,'Unsupported built-in'):
            rt.builtin('VEC',[1,2,3],17)


class AuthoredVectorExampleTests(unittest.TestCase):
    def test_complete_fixtures(self):
        source = Path(__file__).resolve().parents[1]/'examples/pythonic_vectors.kl'
        result = translate(source.read_text(), filename=source.name)
        namespace = {'__name__':'vector_fixture'}
        exec(result.python_source, namespace)
        observed=[]
        program=namespace['Program'](write=observed.append)
        self.assertEqual(program.run(), json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(observed, json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual((program._state.local_frames,program._state.call_depth), ([],0))
