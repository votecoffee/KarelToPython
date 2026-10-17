"""Exact unambiguous KAREL (x,y) bearings and fail-closed branch/order guards."""
import ast,math,unittest
from unittest.mock import patch
from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_reals import compile_program,execute

def direct(x,y,line=23): return rt.builtin('ATAN2',[x,y],line)

class ExactBearingTests(unittest.TestCase):
    def test_positive_horizontal_axis(self): self.assertEqual(direct(4,0),0.)
    def test_positive_vertical_axis(self): self.assertEqual(direct(0,4),90.)
    def test_positive_diagonal(self):
        for value in (.5,1,2.5,90,36000): self.assertEqual(direct(value,value),45.)
    def test_karel_coordinate_order_is_distinguished(self): self.assertEqual((direct(7,0),direct(0,7)),(0.,90.))
    def test_scale_independence_without_ratios(self):
        for exponent in (-126,-80,-1,0,1,80,127):
            value=math.ldexp(1.,exponent)
            self.assertEqual(direct(value,0),0.)
            self.assertEqual(direct(0,value),90.)
            self.assertEqual(direct(value,value),45.)
    def test_large_coordinates_do_not_acquire_angle_limits(self): self.assertEqual(direct(32768,32768),45.)
    def test_overflowing_square_intermediates_are_not_computed(self): self.assertEqual(direct(math.ldexp(1.,127),math.ldexp(1.,127)),45.)
    def test_results_are_real(self):
        for x,y in ((1,0),(1,1),(0,1)): self.assertIs(type(direct(x,y)),float)
    def test_zero_keeps_existing_normalization(self): self.assertEqual(math.copysign(1.,direct(1,-0.)),1.)
    def test_no_host_atan2_or_conversion_calls(self):
        for name in ('atan2','atan','hypot','sqrt','degrees','radians'):
            with patch('math.'+name,side_effect=AssertionError('host math called')):
                self.assertEqual((direct(1,0),direct(1,1),direct(0,1)),(0.,45.,90.))

class BearingGuardTests(unittest.TestCase):
    def rejected(self,x,y,message):
        with self.assertRaisesRegex(rt.KarelRuntimeError,message) as caught: direct(x,y)
        self.assertEqual(caught.exception.line,23)
    def test_origin_is_undefined(self): self.rejected(0,0,'origin')
    def test_normalized_signed_zero_is_origin(self): self.rejected(-0.,-0.,'origin')
    def test_negative_axes_are_guarded(self):
        for x,y in ((-1,0),(0,-1)): self.rejected(x,y,'negative-coordinate return range')
    def test_other_quadrants_are_guarded(self):
        for x,y in ((-1,1),(-1,-1),(1,-1),(-2,1),(1,-2)): self.rejected(x,y,'negative-coordinate return range')
    def test_positive_rounded_bearings_stay_blocked(self):
        for x,y in ((1,2),(2,1),(100,200),(.5,.25)): self.rejected(x,y,'rounding is not validated')
    def test_near_diagonal_is_not_snapped(self): self.rejected(1.,1.00000011920928955078125,'rounding is not validated')
    def test_near_axis_is_not_snapped(self): self.rejected(math.ldexp(1.,127),math.ldexp(1.,-126),'rounding is not validated')
    def test_both_coordinates_must_be_initialized(self):
        for x,y in ((rt.UNINITIALIZED,0),(1,rt.UNINITIALIZED),(0,rt.UNINITIALIZED),(-1,rt.UNINITIALIZED)):
            self.rejected(x,y,'uninitialized')
    def test_both_coordinates_must_be_exact_real(self):
        for value in (.1,16777217,float('nan'),float('inf'),-float('inf')):
            self.rejected(value,0,'REAL|real|exact|finite|represent')
            self.rejected(1,value,'REAL|real|exact|finite|represent')
    def test_boolean_text_unknown_and_other_host_types(self):
        for value in (True,False,'0',None,rt.UNKNOWN_BYTE):
            self.rejected(value,0,'REAL|BYTE'); self.rejected(1,value,'REAL|BYTE')
    def test_runtime_arity_guard(self):
        for args in ([],[1],[1,1,1]):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'exactly two'): rt.builtin('ATAN2',args,7)
    def test_underflow_normalization_precedes_bearing_guard(self):
        # Existing REAL policy flushes these values; no native quadrant inference.
        self.assertEqual(direct(1,-1e-40),0.)
        self.rejected(1e-40,1e-40,'origin')

class BearingSourceTests(unittest.TestCase):
    def rejected(self,body,code='E_TYPE',**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code)
    def test_source_order_and_case(self): self.assertEqual((execute('r=aTaN2(1,0)')['R'],execute('r=ATAN2(0,1)')['R']),(0.,90.))
    def test_integer_and_real_inputs(self): self.assertEqual(execute('x=3 s=3 r=ATAN2(x,s)')['R'],45.)
    def test_narrow_inputs(self):
        state=execute('p.x=3 p.y=3 r=ATAN2(p.x,p.y)',declarations='r: REAL p: point_t',constants='TYPE point_t=STRUCTURE x: BYTE y: SHORT ENDSTRUCTURE')
        self.assertEqual(state['R'],45.)
    def test_array_and_field_coordinates(self):
        state=execute('a[1]=.5 a[2]=.5 r=ATAN2(a[1],a[2])')
        self.assertEqual(state['R'],45.)
    def test_nested_pure_builtins(self): self.assertEqual(execute('r=ATAN2(ABS(-1),SQRT(1)) s=COS(ATAN2(0,1))')['R'],45.)
    def test_parameterized_routine_result(self):
        state=execute('r=bearing(2.5,2.5)','ROUTINE bearing(px,py: REAL): REAL BEGIN RETURN ATAN2(px,py) END bearing')
        self.assertEqual(state['R'],45.)
    def test_result_is_independent_writable_real_argument(self):
        self.assertEqual(execute('set_value(ATAN2(1,1))','ROUTINE set_value(p: REAL) BEGIN p=90 r=p END set_value')['R'],90.)
    def test_arguments_read_once(self):
        program,_=compile_program('r=ATAN2(s,s)'); program._state.values['S']=1.
        original=program._state.get; reads=[]
        def counted(name,*args):
            if name=='S': reads.append(name)
            return original(name,*args)
        program._state.get=counted
        self.assertEqual(program.run()['R'],45.); self.assertEqual(reads,['S','S'])
    def test_local_for_loop_and_counter_cleanup(self):
        routine='ROUTINE fill VAR k: INTEGER BEGIN FOR k=1 TO 2 DO a[k]=ATAN2(k,k) ENDFOR END fill'
        program,_=compile_program('fill',routines=routine)
        self.assertEqual(program.run()['A'],[45.,45.]); self.assertEqual(program._state.local_frames,[])
    def test_labelled_execution(self): self.assertEqual(execute('GOTO calc calc:: r=ATAN2(0,1)')['R'],90.)
    def test_dynamic_other_quadrant_translates_then_fails(self):
        program,result=compile_program('r=ATAN2(-1,1)'); self.assertEqual(result.report['status'],'translated')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'negative-coordinate'): program.run()
    def test_guard_preserves_destination_and_prior_writes(self):
        program,_=compile_program('r=99 x=7 r=ATAN2(1,2)')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['R'],program.snapshot()['X']),(99.,7))
    def test_origin_error_unwinds_frames_and_retains_write(self):
        program,_=compile_program('r=99 r=bearing()',routines='ROUTINE bearing: REAL BEGIN x=7 RETURN ATAN2(0,0) END bearing')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['R'],program.snapshot()['X']),(99.,7))
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
        self.assertIsNone(program.abort_info)
    def test_earlier_output_retained_on_guard_failure(self):
        program,_=compile_program('r=bearing()',routines='ROUTINE bearing: REAL BEGIN WRITE(ON) RETURN ATAN2(-1,0) END bearing')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual([row['text'] for row in program.write_requests],[' TRUE'])
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_user_routine_in_either_coordinate_is_blocked(self):
        routine='ROUTINE value: REAL BEGIN RETURN 1 END value'
        for body in ('r=ATAN2(value(),1)','r=ATAN2(1,value())','r=ATAN2(SIN(value()),1)'):
            self.rejected(body,'E_EVALUATION_ORDER',routines=routine)
    def test_effectful_wrapper_indexed_target_guard(self):
        self.rejected('a[x]=bearing()','E_EVALUATION_ORDER',routines='ROUTINE bearing: REAL BEGIN x=2 RETURN ATAN2(1,1) END bearing')
    def test_wrapper_transitive_timing_effect_guard(self):
        self.rejected('r=bearing()+1','E_EVALUATION_ORDER',routines='ROUTINE bearing: REAL BEGIN DELAY 0 RETURN ATAN2(1,1) END bearing')
    def test_pure_wrapper_in_operator(self):
        self.assertEqual(execute('r=bearing()+45','ROUTINE bearing: REAL BEGIN RETURN ATAN2(1,1) END bearing')['R'],90.)
    def test_wrong_source_coordinate_types(self):
        for argument in ('TRUE',"'0'",'a'):
            self.rejected(f'r=ATAN2({argument},0)'); self.rejected(f'r=ATAN2(1,{argument})')
    def test_source_arity_guard(self):
        for arguments in ('','1','1,1,1'): self.rejected(f'r=ATAN2({arguments})','E_ARGUMENTS')
    def test_result_not_implicitly_integer(self): self.rejected('x=ATAN2(1,1)')
    def test_rounding_dependent_inputs_stay_blocked(self): self.rejected('r=ATAN2(0.1,0)','E_REAL_LITERAL')
    def test_const_function_calls_remain_blocked(self):
        self.rejected('','E_CONSTANT',constants='CONST C=ATAN2(1,1)')
    def test_builtin_name_cannot_be_redeclared(self):
        with self.assertRaises(TranslationError) as caught: translate('PROGRAM T VAR atan2: REAL BEGIN END T')
        self.assertEqual(caught.exception.code,'E_NAME')
    def test_error_and_report_physical_locations(self):
        source='PROGRAM T\nVAR r: REAL\nBEGIN\n r=ATAN2(0,0)\nEND T'
        result=translate(source); ast.parse(result.python_source,feature_version=(3,11))
        self.assertEqual([(row['line'],row['column'],row['argument_order']) for row in result.report['atan2_uses']],[(4,4,['x','y'])])
        self.assertTrue(result.report['atan2_uses'][0]['arguments_evaluated_once'])
        self.assertEqual(result.report['atan2_policy']['exact_results'],[0,45,90])
        self.assertFalse(result.report['atan2_policy']['controller_validated'])
        namespace={'__name__':'bearing_location'}; exec(result.python_source,namespace)
        with self.assertRaises(rt.KarelRuntimeError) as caught: namespace['Program']().run()
        self.assertEqual(caught.exception.line,4)

if __name__=='__main__': unittest.main()
