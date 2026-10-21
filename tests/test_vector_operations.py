"""Manual vector examples, conservative arithmetic and destination ownership."""
from fractions import Fraction
import unittest

from karel2py import translate, runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError, tokenize


def fill(name, values):
    return ' '.join(f'{name}.{field}={value}' for field, value in zip(('x','y','z'), values))


def compile_program(body, *, declarations='a,b,c: VECTOR\nr: REAL\nflag: BOOLEAN', prefix='', routines='', _translator=translate):
    result=_translator(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',filename='vector_ops.kl')
    namespace={'__name__':'vector_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](),result


def vector(*values):
    result=rt.Structure(('VECTOR',))
    result.values.update(zip(('X','Y','Z'),values))
    return result


class VectorSourceTests(unittest.TestCase):
    def run_op(self,expression,expected,*,first=(3,4,5),second=(6,7,8),target='c'):
        program,result=compile_program(fill('a',first)+' '+fill('b',second)+f' {target}={expression}')
        self.assertEqual(program.run()[target.upper()],expected)
        return program,result

    def test_manual_addition(self): self.run_op('a+b',dict(X=5.,Y=10.,Z=9.),first=(4,8,5),second=(1,2,4))
    def test_subtraction(self): self.run_op('a-b',dict(X=-3.,Y=-3.,Z=-3.))
    def test_vector_times_integer(self): self.run_op('a*2',dict(X=6.,Y=8.,Z=10.))
    def test_integer_times_vector(self): self.run_op('2*a',dict(X=6.,Y=8.,Z=10.))
    def test_vector_times_real(self): self.run_op('a*0.5',dict(X=1.5,Y=2.,Z=2.5))
    def test_real_times_vector(self): self.run_op('0.5*a',dict(X=1.5,Y=2.,Z=2.5))
    def test_manual_vector_division(self): self.run_op('a/2',dict(X=2.,Y=4.,Z=2.5),first=(4,8,5))
    def test_scalar_division(self): self.run_op('4/a',dict(X=2.,Y=1.,Z=.5),first=(2,4,8))
    def test_signed_scaling(self): self.run_op('a*(-2)',dict(X=-6.,Y=-8.,Z=-10.))
    def test_manual_cross_product(self): self.run_op('a#b',dict(X=-3.,Y=6.,Z=-3.))
    def test_cross_order(self): self.run_op('b#a',dict(X=3.,Y=-6.,Z=3.))
    def test_manual_dot_product(self): self.run_op('a@b',86.,target='r')
    def test_equal_copied_values(self): self.run_op('a=b',True,second=(3,4,5),target='flag')
    def test_unequal_values(self): self.run_op('a<>b',True,target='flag')
    def test_equal_values_are_not_object_identity(self): self.run_op('a=a',True,target='flag')
    def test_cross_precedes_multiply(self): self.run_op('a#b*2',dict(X=-6.,Y=12.,Z=-6.))
    def test_dot_precedes_multiply(self): self.run_op('a@b*2',172.,target='r')
    def test_dot_precedes_addition(self): self.run_op('1+a@b',87.,target='r')
    def test_unary_minus_below_dot(self): self.run_op('-a@b',-86.,target='r')
    def test_parentheses_change_vector_expression(self): self.run_op('(a+b)#a',dict(X=3.,Y=-6.,Z=3.))
    def test_grouped_same_precedence_operators(self): self.run_op('(a#b)@a',0.,target='r')
    def test_grouped_chained_cross(self): self.run_op('(a#b)#a',dict(X=42.,Y=6.,Z=-30.))
    def test_zero_vector_dot_and_add(self):
        self.run_op('a@b',0.,first=(0,0,0),target='r')
        self.run_op('a+b',dict(X=6.,Y=7.,Z=8.),first=(0,0,0))
    def test_fresh_result_and_in_place_assignment(self):
        program,_=compile_program(fill('a',(1,2,3))+' '+fill('b',(4,5,6))+' c=a+b a.x=99 b.y=88 c.z=77 a=a+a')
        state=program.run()
        self.assertEqual(state['C'],dict(X=5.,Y=7.,Z=77.))
        self.assertEqual(state['A'],dict(X=198.,Y=4.,Z=6.))
    def test_captured_component_survives_vector_assignment(self):
        routines='ROUTINE change(item: VECTOR; captured: REAL) BEGIN item=item+item r=captured captured=9 END change'
        program,_=compile_program(fill('a',(1,2,3))+' change(a,a.x)',routines=routines)
        state=program.run()
        self.assertEqual((state['A'],state['R']),(dict(X=9.,Y=4.,Z=6.),2.))
    def test_array_and_structure_operands(self):
        program,_=compile_program(fill('items[1]',(1,2,3))+' '+fill('box.offset',(4,5,6))+' items[2]=items[1]+box.offset',
            declarations='items: ARRAY[2] OF VECTOR\nbox: box_t',prefix='TYPE box_t=STRUCTURE offset: VECTOR ENDSTRUCTURE')
        self.assertEqual(program.run()['ITEMS'][1],dict(X=5.,Y=7.,Z=9.))
    def test_narrow_scaling_promotes_to_real(self):
        program,_=compile_program(fill('a',(1,2,3))+' bytes[1]=2 c=a*bytes[1]',declarations='a,c: VECTOR\nbytes: ARRAY[1] OF BYTE')
        self.assertEqual(program.run()['C'],dict(X=2.,Y=4.,Z=6.))
    def test_report_records_vector_policy_and_operators(self):
        _,result=self.run_op('a#b',dict(X=-3.,Y=6.,Z=-3.))
        self.assertIn('VECTOR operator #',result.report['features'])
        self.assertFalse(result.report['vector_policy']['controller_validated'])
    def test_source_line_on_uninitialized_component(self):
        program,_=compile_program('a.x=1 a.y=2\nb.x=3 b.y=4 b.z=5\nc=a+b')
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertIn('line 10',str(caught.exception))
    def test_operator_continuation(self):
        self.run_op('a & -- comment\n # b',dict(X=-3.,Y=6.,Z=-3.))
    def test_vector_tokens_exclude_literal_and_comment(self):
        tokens=tokenize("'@#' -- @#\na#b@c",'tokens.kl')
        self.assertEqual([t.value for t in tokens if t.value in ('#','@')],['#','@'])


class VectorGuardTests(unittest.TestCase):
    def test_ungrouped_same_level_product_chains_blocked(self):
        for expression in ('a#b#a','a#b@a','a@b#a','a@b@a'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError) as caught: compile_program('c='+expression)
            self.assertEqual(caught.exception.code,'E_VECTOR_ASSOCIATIVITY')
    def test_parenthesized_cross_association_is_explicit(self):
        program,_=compile_program(fill('a',(1,2,3))+' '+fill('b',(4,5,6))+' '+fill('c',(7,8,10))+' d=a#(b#c) c=(a#b)#c',
                                 declarations='a,b,c,d: VECTOR')
        state=program.run()
        self.assertEqual(state['D'],dict(X=-12.,Y=9.,Z=-2.))
        self.assertEqual(state['C'],dict(X=84.,Y=9.,Z=-66.))
    def test_invalid_type_combinations(self):
        for expression in ('a*b','a/b','a+2','2-a','a< b','a<=b','a>b','a>=b','a#2','2@a','a AND b','NOT a','(a)@2'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError): compile_program('c='+expression)
    def test_unary_vector_signs_blocked(self):
        for expression in ('-a','+a','-(a#b)'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError): compile_program('c='+expression)
    def test_value_vector_parameter_requires_initialized_components(self):
        program,_=compile_program('inspect(a+b)',routines='ROUTINE inspect(v: VECTOR) BEGIN END inspect')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
    def test_vector_function_result_requires_initialized_components(self):
        program,_=compile_program('c=create()',routines='ROUTINE create: VECTOR BEGIN RETURN a END create')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
    def test_constructor_still_blocked(self):
        with self.assertRaises(TranslationError): compile_program('a=VEC(1,2,3)')
    def test_position_transform_still_blocked(self):
        with self.assertRaises(TranslationError): compile_program('a=p:a',declarations='a: VECTOR\np: POSITION')
    def test_read_only_destination_still_blocked(self):
        with self.assertRaises(TranslationError): compile_program('p.normal=a+b',declarations='a,b: VECTOR\np: POSITION')
    def test_effectful_dot_operand_blocked(self):
        with self.assertRaises(TranslationError) as caught: compile_program('r=(a@b)*effect()',routines='ROUTINE effect: REAL BEGIN r=1 RETURN 2 END effect', _translator=legacy_translate)
        self.assertEqual(caught.exception.code,'E_EVALUATION_ORDER')
    def test_pure_function_scaling(self):
        program,_=compile_program(fill('a',(1,2,3))+' c=a*factor()',routines='ROUTINE factor: REAL BEGIN RETURN 2 END factor')
        self.assertEqual(program.run()['C'],dict(X=2.,Y=4.,Z=6.))
    def test_division_guard_preserves_destination(self):
        for expression in ('a/0','2/b'):
            with self.subTest(expression=expression):
                program,_=compile_program(fill('a',(1,2,3))+' '+fill('b',(1,0,2))+' '+fill('c',(7,8,9))+' c='+expression)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Division by zero'): program.run()
                self.assertEqual(program._state.snapshot()['C'],dict(X=7.,Y=8.,Z=9.))


class VectorRuntimeTests(unittest.TestCase):
    def test_zero_or_parallel_cross_rejected(self):
        for left,right in ((vector(0,0,0),vector(1,2,3)),(vector(1,2,3),vector(0,0,0)),(vector(1,2,3),vector(2,4,6)),(vector(1,2,3),vector(-1,-2,-3))):
            with self.subTest(left=left.values,right=right.values),self.assertRaisesRegex(rt.KarelRuntimeError,'nonzero, nonparallel'): rt.binary('#',left,right)
    def test_equality_requires_all_components_even_if_first_differs(self):
        for op in ('=','<>'):
            with self.subTest(op=op),self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):
                rt.binary(op,vector(1,2,3),vector(9,rt.UNINITIALIZED,3))
    def test_all_operators_require_initialized_components(self):
        for op in ('+','-','#','@','=','<>','*','/'):
            with self.subTest(op=op),self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):
                rt.binary(op,vector(1,2,rt.UNINITIALIZED),2 if op in ('*','/') else vector(1,2,3))
    def test_invalid_host_components_rejected(self):
        for value in (True,'x',float('nan'),float('inf'),rt.UNKNOWN_BYTE):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): rt.binary('+',vector(1,value,3),vector(1,2,3))
    def test_host_wrong_vector_shape(self):
        value=vector(1,2,3)
        del value.values['Z']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'three-component'): rt.binary('=',value,value)
    def test_inexact_component_result_rejected(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'rounding'): rt.binary('/',vector(1,2,4),3)
    def test_integer_scalar_must_promote_exactly(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'rounding'): rt.binary('*',vector(0,0,0),16777217)
    def test_scalar_division_reciprocal_guard(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'rounding'): rt.binary('/',7,vector(7,7,7))
    def test_dot_products_cannot_hide_inexact_intermediate(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'rounding'): rt.binary('@',vector(16777216,1,-16777216),vector(1,1,1))
    def test_cross_cannot_hide_overflow_in_cancellation(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overflow'): rt.binary('#',vector(2.**100,2.**100,2.**100),vector(2.**100,2.**100,2.**100))
    def test_dot_intermediate_underflow_rejected(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'underflow'): rt.binary('@',vector(2.**-100,0,0),vector(2.**-100,0,0))
    def test_cross_intermediate_underflow_rejected(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'underflow'): rt.binary('#',vector(2.**-100,0,0),vector(0,2.**-100,0))
    def test_component_underflow_uses_shared_policy(self):
        self.assertEqual(rt.snapshot_value(rt.binary('*',vector(2.**-126,0,0),2.**-24)),dict(X=0.,Y=0.,Z=0.))
    def test_overflow_rejected(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overflow'): rt.binary('*',vector(2.**127,0,0),2)
    def test_order_independent_dot_sum_guard(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'rounding'): rt.binary('@',vector(16777216,-16777216,1),vector(1,1,1))
    def test_read_only_vector_operand_produces_writable_detached_result(self):
        source=vector(1,2,3)
        source.read_only=True
        result=rt.binary('+',source,vector(1,1,1))
        rt.field_reference(result,'X').set(9)
        self.assertEqual((source.values['X'],result.values['X']),(1,9.))
    def test_unsupported_runtime_vector_operations(self):
        for op in ('*','/','<','AND'):
            with self.subTest(op=op),self.assertRaises(rt.KarelRuntimeError): rt.binary(op,vector(1,2,3),vector(4,5,6))


if __name__=='__main__': unittest.main()
