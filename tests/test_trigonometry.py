"""Independent exact degree identities, domain limits and translation integration."""
import ast,math,unittest
from unittest.mock import patch
from karel2py import translate,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_reals import compile_program,execute

FUNCTIONS=('SIN','COS','TAN','ASIN','ACOS')
def direct(name,value,line=19): return rt.builtin(name,[value],line)

class ExactDegreeTests(unittest.TestCase):
    def test_sine_unit_circle_values(self):
        for angle,expected in ((0,0.),(30,.5),(90,1.),(150,.5),(180,0.),(210,-.5),(270,-1.),(330,-.5)):
            with self.subTest(angle=angle): self.assertEqual(direct('SIN',angle),expected)
    def test_cosine_unit_circle_values(self):
        for angle,expected in ((0,1.),(60,.5),(90,0.),(120,-.5),(180,-1.),(240,-.5),(270,0.),(300,.5)):
            with self.subTest(angle=angle): self.assertEqual(direct('COS',angle),expected)
    def test_tangent_diagonals_and_axes(self):
        for angle,expected in ((0,0.),(45,1.),(135,-1.),(180,0.),(225,1.),(315,-1.)):
            with self.subTest(angle=angle): self.assertEqual(direct('TAN',angle),expected)
    def test_sine_is_odd_across_revolutions(self):
        for angle in (30,90,150,210,270,330,390,810,17970): self.assertEqual(direct('SIN',-angle),-direct('SIN',angle))
    def test_cosine_is_even_across_revolutions(self):
        for angle in (0,60,90,120,180,240,270,300,420,17940): self.assertEqual(direct('COS',-angle),direct('COS',angle))
    def test_tangent_is_odd_across_revolutions(self):
        for angle in (0,45,135,225,315,405,17955): self.assertEqual(direct('TAN',-angle),-direct('TAN',angle))
    def test_all_full_turns_in_documented_range(self):
        for turn in range(-50,51):
            self.assertEqual(direct('SIN',turn*360),0.)
            self.assertEqual(direct('COS',turn*360),1.)
            self.assertEqual(direct('TAN',turn*360),0.)
    def test_all_half_turn_tangents(self):
        for turn in range(-100,101): self.assertEqual(direct('TAN',turn*180),0.)
    def test_forward_closed_boundaries(self):
        for angle in (-18000,18000):
            for name,expected in (('SIN',0.),('COS',1.),('TAN',0.)): self.assertEqual(direct(name,angle),expected)
    def test_sine_cosine_complement_identity(self):
        for angle in (-690,-330,-270,-210,-90,0,30,90,150,180,210,270,330,450):
            self.assertEqual(direct('SIN',angle),direct('COS',90-angle))
    def test_inverse_sine_values(self):
        for value,expected in ((-1,-90.),(-.5,-30.),(0,0.),(.5,30.),(1,90.)): self.assertEqual(direct('ASIN',value),expected)
    def test_inverse_cosine_values(self):
        for value,expected in ((-1,180.),(-.5,120.),(0,90.),(.5,60.),(1,0.)): self.assertEqual(direct('ACOS',value),expected)
    def test_inverse_complement_identity(self):
        for value in (-1,-.5,0,.5,1): self.assertEqual(direct('ASIN',value)+direct('ACOS',value),90.)
    def test_principal_sine_roundtrip(self):
        for angle in (-90,-30,0,30,90): self.assertEqual(direct('ASIN',direct('SIN',angle)),float(angle))
    def test_principal_cosine_roundtrip(self):
        for angle in (0,60,90,120,180): self.assertEqual(direct('ACOS',direct('COS',angle)),float(angle))
    def test_results_are_real(self):
        for name in FUNCTIONS: self.assertIs(type(direct(name,0)),float)
    def test_zero_normalization_retains_real_policy(self):
        for name in ('SIN','TAN','ASIN'):
            self.assertEqual(math.copysign(1.,direct(name,-0.)),1.)
    def test_no_host_trig_or_radian_calls(self):
        for name in ('sin','cos','tan','asin','acos','radians','degrees'):
            with patch('math.'+name,side_effect=AssertionError('host trig called')):
                self.assertEqual(direct('SIN',30),.5)
                self.assertEqual(direct('COS',60),.5)
                self.assertEqual(direct('TAN',45),1.)
                self.assertEqual(direct('ASIN',.5),30.)
                self.assertEqual(direct('ACOS',.5),60.)

class DegreeGuardTests(unittest.TestCase):
    def rejects(self,name,value,message):
        with self.assertRaisesRegex(rt.KarelRuntimeError,message) as caught: direct(name,value)
        self.assertEqual(caught.exception.line,19)
    def test_outside_angle_range(self):
        for name in ('SIN','COS','TAN'):
            for value in (-18000.5,18000.5,-18001,18001): self.rejects(name,value,'-18000..18000')
    def test_range_guard_precedes_period_reduction(self):
        for name in ('SIN','COS','TAN'):
            for angle in (-18360,18360,-36000,36000): self.rejects(name,angle,'-18000..18000')
    def test_inverse_domain_guard(self):
        for name in ('ASIN','ACOS'):
            for value in (-1.5,1.5,-2,2): self.rejects(name,value,'-1..1')
    def test_inverse_near_endpoint_outside_domain(self):
        for name in ('ASIN','ACOS'):
            for value in (-1.00000011920928955078125,1.00000011920928955078125): self.rejects(name,value,'-1..1')
    def test_non_table_forward_inputs_remain_blocked(self):
        for name,value in (('SIN',45),('SIN',60),('COS',30),('TAN',30),('TAN',60),('SIN',.5)):
            self.rejects(name,value,'rounding is not validated')
    def test_non_table_inverse_inputs_remain_blocked(self):
        for name in ('ASIN','ACOS'):
            for value in (-.75,-.25,.25,.75): self.rejects(name,value,'rounding is not validated')
    def test_no_tolerance_snapping(self):
        for name,value in (('SIN',89.9999847412109375),('COS',60.000003814697265625),('TAN',45.000003814697265625),('ASIN',.500000059604644775390625),('ACOS',.500000059604644775390625)):
            self.rejects(name,value,'rounding is not validated')
    def test_all_tangent_poles(self):
        for angle in range(-17910,17911,180): self.rejects('TAN',angle,'undefined')
    def test_runtime_unknown_and_boolean_guards(self):
        for name in FUNCTIONS:
            for value in (rt.UNINITIALIZED,rt.UNKNOWN_BYTE,True,False,'0',None): self.rejects(name,value,'REAL|uninitialized|BYTE')
    def test_runtime_numeric_input_guards(self):
        for name in FUNCTIONS:
            for value in (float('nan'),float('inf'),-float('inf'),.1,16777217): self.rejects(name,value,'REAL|real|exact|finite|represent')
    def test_runtime_arity_guard(self):
        for name in FUNCTIONS:
            for args in ([],[0,0]):
                with self.assertRaisesRegex(rt.KarelRuntimeError,'exactly one'): rt.builtin(name,args,7)
    def test_unknown_math_names_remain_blocked(self):
        for name in ('EXP','LN','VEC'):
            with self.assertRaises(TranslationError): translate(f'PROGRAM T VAR r: REAL BEGIN r={name}(0) END T')

class DegreeSourceTests(unittest.TestCase):
    def rejected(self,body,code='E_TYPE',**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code)
    def test_case_insensitive_source_calls(self): self.assertEqual(execute('r=sIn(30) s=CoS(60)')['R'],.5)
    def test_integer_promotion(self): self.assertEqual(execute('x=90 r=SIN(x)')['R'],1.)
    def test_narrow_field_promotion(self):
        state=execute('packet.angle=30 r=SIN(packet.angle)',declarations='r: REAL packet: sample_t',constants='TYPE sample_t=STRUCTURE angle: BYTE ENDSTRUCTURE')
        self.assertEqual(state['R'],.5)
    def test_real_field_and_array_inputs(self):
        state=execute('a[1]=60 r=COS(a[1]) s=ASIN(r)')
        self.assertEqual((state['R'],state['S']),(.5,30.))
    def test_nested_exact_functions(self): self.assertEqual(execute('r=ACOS(COS(120))+ASIN(SIN(150))+TAN(45)')['R'],151.)
    def test_pure_routine_argument(self):
        self.assertEqual(execute('r=SIN(angle())','ROUTINE angle: INTEGER BEGIN RETURN 30 END angle')['R'],.5)
    def test_effectful_argument_evaluated_once(self):
        state=execute('x=0 r=SIN(next_angle())','ROUTINE next_angle: REAL BEGIN x=x+1 RETURN 90 END next_angle')
        self.assertEqual((state['R'],state['X']),(1.,1))
    def test_reference_argument_writes_retained(self):
        state=execute('s=0 r=SIN(change(s))','ROUTINE change(p: REAL): REAL BEGIN p=30 RETURN p END change')
        self.assertEqual((state['R'],state['S']),(.5,30.))
    def test_result_is_a_writable_real_value_argument(self):
        state=execute('r=0 change(SIN(30))','ROUTINE change(p: REAL) BEGIN p=99 r=p END change')
        self.assertEqual(state['R'],99.)
    def test_routine_return_and_recursive_frames(self):
        routine='ROUTINE result(n: INTEGER): REAL BEGIN IF n=0 THEN RETURN SIN(90) ENDIF RETURN result(n-1) END result'
        program,_=compile_program('r=result(4)',routines=routine)
        self.assertEqual(program.run()['R'],1.)
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_local_for_counter_and_calls(self):
        routine='ROUTINE value: REAL BEGIN RETURN COS(60) END value\nROUTINE fill VAR k: INTEGER BEGIN FOR k=1 TO 2 DO a[k]=value() ENDFOR END fill'
        self.assertEqual(execute('fill',routine)['A'],[.5,.5])
    def test_labelled_dispatch_path(self):
        self.assertEqual(execute('GOTO calc calc:: r=ACOS(-1)')['R'],180.)
    def test_dynamic_unsupported_input_translates_then_fails(self):
        program,result=compile_program('s=45 r=SIN(s)')
        self.assertEqual(result.report['status'],'translated')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'exact degree subset'): program.run()
    def test_runtime_failure_preserves_destination_and_prior_effects(self):
        routine='ROUTINE angle: REAL BEGIN x=7 RETURN 45 END angle'
        program,_=compile_program('r=99 r=SIN(angle())',routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['R'],program.snapshot()['X']),(99.,7))
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_failing_builtin_inside_routine_unwinds_frames(self):
        program,_=compile_program('r=8 r=value()',routines='ROUTINE value: REAL BEGIN x=5 RETURN ASIN(.25) END value')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['R'],program.snapshot()['X']),(8.,5))
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_abort_argument_stays_distinct(self):
        program,_=compile_program('r=SIN(stopped())',routines='ROUTINE stopped: REAL BEGIN ABORT RETURN 0 END stopped')
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))
    def test_transitive_timing_effect_guard(self):
        self.rejected('r=SIN(value())+1','E_EVALUATION_ORDER',routines='ROUTINE value: REAL BEGIN DELAY 0 RETURN 30 END value')
    def test_transitive_write_effect_guard(self):
        self.rejected('r=COS(value())+1','E_EVALUATION_ORDER',routines='ROUTINE value: REAL BEGIN WRITE(ON) RETURN 60 END value')
    def test_indexed_result_effect_guard(self):
        self.rejected('a[x]=SIN(value())','E_EVALUATION_ORDER',routines='ROUTINE value: REAL BEGIN x=2 RETURN 30 END value')
    def test_multiple_argument_order_guard(self):
        self.rejected('use(SIN(value()),0)','E_EVALUATION_ORDER',routines='ROUTINE value: REAL BEGIN RETURN 30 END value\nROUTINE use(p,q: REAL) BEGIN END use')
    def test_wrong_argument_types(self):
        for name in FUNCTIONS:
            for argument in ('TRUE',"'0'",'a'):
                with self.subTest(name=name,argument=argument): self.rejected(f'r={name}({argument})')
    def test_source_argument_counts(self):
        for name in FUNCTIONS:
            self.rejected(f'r={name}()','E_ARGUMENTS')
            self.rejected(f'r={name}(0,0)','E_ARGUMENTS')
    def test_real_result_not_implicitly_integer(self):
        for name in FUNCTIONS: self.rejected(f'x={name}(0)')
    def test_rounding_dependent_source_literal_remains_blocked(self):
        for name in FUNCTIONS: self.rejected(f'r={name}(0.1)','E_REAL_LITERAL')
    def test_builtin_names_cannot_be_redeclared(self):
        for name in FUNCTIONS:
            with self.assertRaises(TranslationError) as caught: translate(f'PROGRAM T VAR {name}: REAL BEGIN END T')
            self.assertEqual(caught.exception.code,'E_NAME')
    def test_uninitialized_input_keeps_runtime_source_line(self):
        source='PROGRAM T\nVAR angle,r: REAL\nBEGIN\n r=SIN(angle)\nEND T'
        namespace={'__name__':'trig_location'}; exec(translate(source).python_source,namespace)
        with self.assertRaises(rt.KarelRuntimeError) as caught: namespace['Program']().run()
        self.assertEqual(caught.exception.line,4)
    def test_report_and_python_311_grammar(self):
        source='PROGRAM T\nVAR r: REAL\nBEGIN\n r=SIN(30)\n r=COS(60)\nEND T'
        result=translate(source); ast.parse(result.python_source,feature_version=(3,11))
        self.assertEqual([(row['function'],row['line'],row['column']) for row in result.report['trig_uses']],[('SIN',4,4),('COS',5,4)])
        self.assertTrue(all(row['evaluated_once'] and row['runtime_exact_subset_guard'] for row in result.report['trig_uses']))
        self.assertEqual(result.report['trig_policy']['angle_units'],'degrees')
        self.assertFalse(result.report['trig_policy']['controller_validated'])

if __name__=='__main__': unittest.main()
