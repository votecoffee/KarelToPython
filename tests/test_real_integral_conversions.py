"""Checked Pythonic REAL truncation at explicit source and variable boundaries."""
import math
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.legacy_numeric_support import translate as legacy_translate

MISSING={'uninitialized':True}
KINDS=('INTEGER','BYTE','SHORT')
HIGH={'INTEGER':'2147483647.0','BYTE':'256.0','SHORT':'32768.0'}
LOW={'INTEGER':'-2147483649.0','BYTE':'-1.0','SHORT':'-32769.0'}


def program(body,kind='INTEGER',decl='',routines='',prefix='',**options):
    return compile_program(body,decl=f'r:REAL out:{kind} seen,calls,e,s:INTEGER done:BOOLEAN '+decl,routines=routines,prefix=prefix,**options)


def execute(body,**options):return program(body,**options)[0].run()


class ScalarCases:
    def test_positive_fraction_truncates_toward_zero(self):
        self.assertEqual(execute('r=7.9 out=r',kind=self.kind)['OUT'],7)

    def test_negative_fraction_truncates_toward_zero(self):
        value,expected=('-0.9',0) if self.kind=='BYTE' else ('-7.9',-7)
        self.assertEqual(execute(f'out={value}',kind=self.kind)['OUT'],expected)

    def test_positive_and_negative_zero_become_zero(self):
        for value in ('0.0','-0.0'):
            with self.subTest(value=value):self.assertEqual(execute('out='+value,kind=self.kind)['OUT'],0)

    def test_overflow_preserves_previous_destination(self):
        for value in (HIGH[self.kind],LOW[self.kind],'1.0E100'):
            p,_=program('out=9 out='+value,kind=self.kind)
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['OUT'],9)

    def test_invalid_real_source_is_never_coerced(self):
        for value in (True,'7',math.nan,math.inf,-math.inf):
            p,_=program('out=9 out=r',kind=self.kind);p._state.values['R']=value
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['OUT'],9)

    def test_missing_scalar_source_is_still_a_read_error(self):
        p,_=program('out=9 out=r',kind=self.kind)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['OUT'],9)

    def test_named_alias_uses_same_checked_domain(self):
        p,_=compile_program('a=7.9',prefix='TYPE number='+self.kind,decl='a:number')
        self.assertEqual(p.run()['A'],7)

    def test_bare_argument_gets_private_writable_storage(self):
        state=execute('r=7.9 work(r)',kind=self.kind,routines=f'ROUTINE work(v:{self.kind}) BEGIN v=9 seen=v END work')
        self.assertEqual((state['R'],state['SEEN']),(7.9,9))

    def test_grouped_argument_and_result_convert_once(self):
        state=execute('calls=0 out=work((make()))',kind=self.kind,routines=f'ROUTINE make:REAL BEGIN calls=calls+1 RETURN 7.9 END make ROUTINE work(v:{self.kind}):{self.kind} BEGIN RETURN v END work')
        self.assertEqual((state['OUT'],state['CALLS']),(7,1))

    def test_converted_argument_failure_skips_later_arguments(self):
        p,_=program('calls=0 seen=0 work('+HIGH[self.kind]+',later())',kind=self.kind,routines=f'ROUTINE later:INTEGER BEGIN calls=calls+1 RETURN 0 END later ROUTINE work(v:{self.kind};n:INTEGER) BEGIN seen=1 END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CALLS'],p.snapshot()['SEEN']),(0,0))

    def test_scalar_function_return_uses_checked_truncation(self):
        state=execute('out=make()',kind=self.kind,routines=f'ROUTINE make:{self.kind} BEGIN RETURN 7.9 END make')
        self.assertEqual(state['OUT'],7)

    def test_failed_return_unwinds_frame_and_preserves_caller(self):
        p,_=program('out=9 out=make()',kind=self.kind,routines=f'ROUTINE make:{self.kind} BEGIN RETURN {HIGH[self.kind]} END make')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['OUT'],p._state.local_frames,p._state.call_depth),(9,[],0))

    def test_source_capture_precedes_target_index_side_effect(self):
        state=execute('r=7.9 values[pick()]=r',kind=self.kind,decl=f'values:ARRAY[1]OF {self.kind}',routines='ROUTINE pick:INTEGER BEGIN r=99.9 RETURN 1 END pick')
        self.assertEqual((state['R'],state['VALUES']),(99.9,[7]))

    def test_failed_conversion_skips_target_index(self):
        p,_=program('calls=0 values[pick()]='+HIGH[self.kind],kind=self.kind,decl=f'values:ARRAY[1]OF {self.kind}',routines='ROUTINE pick:INTEGER BEGIN calls=calls+1 RETURN 1 END pick')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CALLS'],0)

    def test_pause_retains_private_formal_without_copyback(self):
        p,_=program('r=7.9 work(r)',kind=self.kind,routines=f'ROUTINE work(v:{self.kind}) BEGIN v=9 PAUSE seen=v END work')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['R'],7.9);self.assertEqual(p.resume()['SEEN'],9)


class IntegerRealScalarTests(ScalarCases,unittest.TestCase):kind='INTEGER'
class ByteRealScalarTests(ScalarCases,unittest.TestCase):kind='BYTE'
class ShortRealScalarTests(ScalarCases,unittest.TestCase):kind='SHORT'


class ArrayCases:
    def build(self,body='b=a',**options):return program(body,kind=self.kind,decl=f'a:ARRAY[2]OF REAL b:ARRAY[2]OF {self.kind}',**options)
    def seed(self,p):p._state.values['A'].values[:]=[7.9,8.1];p._state.values['B'].values[:]=[9,10]

    def test_complete_array_conversion_retains_receiver_identity(self):
        p,_=self.build();self.seed(p);receiver=p._state.values['B'];state=p.run()
        self.assertEqual((state['A'],state['B']),([7.9,8.1],[7,8]));self.assertIs(p._state.values['B'],receiver)

    def test_missing_array_leaves_propagate(self):
        p,_=self.build();self.seed(p);p._state.values['A'].values[1]=rt.UNINITIALIZED
        self.assertEqual(p.run()['B'],[7,MISSING])

    def test_late_element_overflow_preserves_entire_destination(self):
        p,_=self.build();self.seed(p);p._state.values['A'].values[1]=float(HIGH[self.kind])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],[9,10])

    def test_bare_array_formal_is_private(self):
        p,_=self.build('work(a)',routines=f'ROUTINE work(v:ARRAY OF {self.kind}) BEGIN v[1]=9 seen=v[2] END work');self.seed(p)
        self.assertEqual((p.run()['A'],p.snapshot()['SEEN']),([7.9,8.1],8))

    def test_array_return_has_concrete_receiver_schema(self):
        p,_=self.build('b=make()',routines=f'ROUTINE make:ARRAY OF {self.kind} BEGIN RETURN a END make');self.seed(p)
        self.assertEqual(p.run()['B'],[7,8]);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_named_array_and_nested_prefix_conversion(self):
        p,_=program('a[1,1]=7.9 a[1,2]=8.1 b=a[1]',kind=self.kind,decl='a:ARRAY[1,2]OF REAL b:row_t',prefix=f'TYPE row_t=ARRAY[2]OF {self.kind}')
        self.assertEqual(p.run()['B'],[7,8])

    def test_generic_destination_uses_actual_receiver_dimensions(self):
        p,_=self.build('work(b,a)',routines=f'ROUTINE work(dst:ARRAY OF {self.kind};src:ARRAY OF REAL) BEGIN dst=src END work');self.seed(p)
        self.assertEqual(p.run()['B'],[7,8])

    def test_array_stop_releases_private_copy(self):
        p,_=self.build('work(a)',routines=f'ROUTINE work(v:ARRAY OF {self.kind}) BEGIN v[1]=9 PAUSE END work');self.seed(p)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual((p.snapshot()['A'],p._state.local_frames),([7.9,8.1],[]))


class IntegerRealArrayTests(ArrayCases,unittest.TestCase):kind='INTEGER'
class ByteRealArrayTests(ArrayCases,unittest.TestCase):kind='BYTE'
class ShortRealArrayTests(ArrayCases,unittest.TestCase):kind='SHORT'


class VariableCases:
    def call(self,action):return f"GET_VAR(e,'','R',out,s)" if action=='GET_VAR' else f"SET_VAR(e,'','OUT',r,s)"
    def test_get_and_set_truncate_scalar_values(self):
        for action in ('GET_VAR','SET_VAR'):
            state=execute('r=7.9 '+self.call(action),kind=self.kind)
            self.assertEqual((state['OUT'],state['S'],state['E']),(7,0,1))

    def test_missing_scalar_clears_receiver_with_missing_status(self):
        for action in ('GET_VAR','SET_VAR'):
            state=execute('out=9 '+self.call(action),kind=self.kind)
            self.assertEqual((state['OUT'],state['S']),(MISSING,12311))

    def test_overflow_preserves_data_cache_and_status(self):
        for action in ('GET_VAR','SET_VAR'):
            p,_=program('out=9 e=99 s=77 r='+HIGH[self.kind]+' '+self.call(action),kind=self.kind)
            with self.subTest(action=action),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['OUT'],p.snapshot()['E'],p.snapshot()['S'],p._state.execution.entries),(9,99,77,{}))

    def test_get_and_set_array_prefix_preserve_tail(self):
        for action in ('GET_VAR','SET_VAR'):
            call="GET_VAR(e,'','A',b,s)" if action=='GET_VAR' else "SET_VAR(e,'','B',a,s)"
            state=execute('a[1]=7.9 b[2]=9 '+call,kind=self.kind,decl=f'a:ARRAY[1]OF REAL b:ARRAY[2]OF {self.kind}')
            self.assertEqual((state['B'],state['S']),([7,9],0))

    def test_late_array_overflow_is_atomic(self):
        for action in ('GET_VAR','SET_VAR'):
            call="GET_VAR(e,'','A',b,s)" if action=='GET_VAR' else "SET_VAR(e,'','B',a,s)"
            p,_=program('a[1]=7.9 a[2]='+HIGH[self.kind]+' b[1]=9 b[2]=10 e=99 s=77 '+call,kind=self.kind,decl=f'a:ARRAY[2]OF REAL b:ARRAY[2]OF {self.kind}')
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),([9,10],99,77))

    def test_named_row_get_output_uses_captured_live_cells(self):
        state=execute("a[1]=7.9 a[2]=8.1 GET_VAR(e,'','A',rows[2],s)",kind=self.kind,decl=f'a:ARRAY[2]OF REAL rows:ARRAY[2,2]OF {self.kind}')
        self.assertEqual((state['ROWS'][1],state['S']),([7,8],0))

    def test_variable_records_convert_recursive_real_fields(self):
        types=f'TYPE one=STRUCTURE n:REAL items:ARRAY[2]OF REAL ENDSTRUCTURE two=STRUCTURE items:ARRAY[2]OF {self.kind} n:{self.kind} ENDSTRUCTURE'
        for action in ('GET_VAR','SET_VAR'):
            call="GET_VAR(e,'','A',b,s)" if action=='GET_VAR' else "SET_VAR(e,'','B',a,s)"
            state=execute('a.n=7.9 a.items[1]=8.9 a.items[2]=9.1 '+call,kind=self.kind,prefix=types,decl='a:one b:two')
            self.assertEqual((state['B'],state['S']),({'ITEMS':[8,9],'N':7},0))


class IntegerRealVariableTests(VariableCases,unittest.TestCase):kind='INTEGER'
class ByteRealVariableTests(VariableCases,unittest.TestCase):kind='BYTE'
class ShortRealVariableTests(VariableCases,unittest.TestCase):kind='SHORT'


class RealIntegralCompositionTests(unittest.TestCase):
    def test_short_sentinel_can_clear_assignment_and_private_formal(self):
        state=execute('out=32767.9 work(32767.9)',kind='SHORT',routines='ROUTINE work(v:SHORT) BEGIN done=UNINIT(v) v=9 seen=v END work')
        self.assertEqual((state['OUT'],state['DONE'],state['SEEN']),(MISSING,True,9))

    def test_short_sentinel_return_must_be_initialized(self):
        p,_=program('out=9 out=make()',kind='SHORT',routines='ROUTINE make:SHORT BEGIN RETURN 32767.9 END make')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):p.run()
        self.assertEqual(p.snapshot()['OUT'],9)

    def test_short_sentinel_in_variable_array_sets_missing_status(self):
        state=execute("a[1]=32767.9 a[2]=8.9 GET_VAR(e,'','A',b,s)",kind='SHORT',decl='a:ARRAY[2]OF REAL b:ARRAY[2]OF SHORT')
        self.assertEqual((state['B'],state['S']),([MISSING,8],12311))

    def test_domain_checks_apply_after_truncation(self):
        for kind,value,expected in [('INTEGER','-2147483648.9',-2147483648),('INTEGER','2147483646.9',2147483646),('BYTE','255.99',255),('SHORT','-32768.99',-32768)]:
            with self.subTest(kind=kind):self.assertEqual(execute('out='+value,kind=kind)['OUT'],expected)

    def test_recursive_record_assignment_maps_fields_by_name(self):
        types='TYPE one=STRUCTURE n:REAL label:STRING[8] ENDSTRUCTURE two=STRUCTURE label:STRING[3] n:BYTE ENDSTRUCTURE'
        state=execute("a.n=7.9 a.label='abcdef' b=a",prefix=types,decl='a:one b:two')
        self.assertEqual(state['B'],{'LABEL':'abc','N':7})

    def test_record_conversion_failure_preserves_all_receiver_fields(self):
        types='TYPE one=STRUCTURE good:REAL bad:REAL ENDSTRUCTURE two=STRUCTURE good:BYTE bad:BYTE ENDSTRUCTURE'
        p,_=program('a.good=7.9 a.bad=256.0 b.good=9 b.bad=10 b=a',prefix=types,decl='a:one b:two')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],{'GOOD':9,'BAD':10})

    def test_builtin_config_turns_keep_their_own_bounds(self):
        state=execute('c.cfg_turn_no1=7.9',decl='c:CONFIG')
        self.assertEqual(state['C']['CFG_TURN_NO1'],7)

    def test_explicit_byname_keeps_exact_reference_type(self):
        p,_=program("r=7.9 work(BYNAME('','R',e))",routines='ROUTINE work(v:INTEGER) BEGIN v=9 END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['R'],7.9)

    def test_generic_runtime_checked_and_parameter_helpers_remain_exact(self):
        with rt._numeric_scope('pythonic'):
            for call in (lambda:rt.checked(('INTEGER',),7.9),lambda:rt.value_argument(('INTEGER',),7.9),lambda:rt.integer(7.9)):
                with self.subTest(call=call),self.assertRaises(rt.KarelRuntimeError):call()
            self.assertFalse(rt.parameter_accepts(('INTEGER',),('REAL',)))

    def test_legacy_source_and_new_runtime_helper_stay_closed(self):
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR n:INTEGER BEGIN n=7.5 END T')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.real_integral_value(('INTEGER',),7.9)

    def test_typed_service_input_does_not_gain_implicit_narrowing(self):
        with self.assertRaises(TranslationError):program('SET_INT_REG(1,7.9,s)')

    def test_real_for_bounds_remain_rejected(self):
        with self.assertRaises(TranslationError):program('FOR out=1.9 TO 3.9 DO ENDFOR')

    def test_linked_routine_uses_private_converted_argument(self):
        sources={'main':"PROGRAM MAIN VAR r:REAL n:INTEGER ROUTINE work(v:INTEGER):INTEGER FROM LIB BEGIN r=7.9 n=work(r) END MAIN",'lib':"PROGRAM LIB ROUTINE work(v:INTEGER):INTEGER BEGIN v=v+1 RETURN v END work BEGIN END LIB"}
        state=translate_project(sources).instantiate().run('MAIN')
        self.assertEqual(state['MAIN']['values'],{'R':7.9,'N':8})

    def test_value_state_survives_json_context_roundtrip(self):
        p,_=program('r=7.9 out=r');p.run();config=p._state.execution.to_config()
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)


class RealIntegralAdditionalTests(unittest.TestCase):
    def test_system_frame_turn_assignment_uses_explicit_context(self):
        from tests.test_system_pose_values import context
        p,_=program('$MNUFRAME[1,2].config_data.cfg_turn_no1=7.9',context=context());p.run()
        self.assertEqual(p._state.execution.robot.frames[2].values['CONFIG_DATA'].values['CFG_TURN_NO1'],7)

    def test_system_frame_turn_overflow_preserves_table(self):
        from tests.test_system_pose_values import context
        ctx=context();before=ctx.robot.to_config();p,_=program('$MNUFRAME[1,2].config_data.cfg_turn_no1=8.9',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.robot.to_config(),before)

    def test_retained_handler_keeps_private_truncated_scalar(self):
        state=execute('r=7.9 work(r) ENABLE CONDITION[1] SIGNAL EVENT[1]',routines='ROUTINE work(v:INTEGER) BEGIN CONDITION[1]: WHEN EVENT[1] DO v=9 seen=v ENDCONDITION END work')
        self.assertEqual((state['R'],state['SEEN']),(7.9,9))

    def test_forwarded_exact_formal_aliases_private_converted_value(self):
        state=execute('r=7.9 work(r)',routines='ROUTINE child(v:INTEGER) BEGIN v=9 END child ROUTINE work(v:INTEGER) BEGIN child(v) seen=v END work')
        self.assertEqual((state['R'],state['SEEN']),(7.9,9))

    def test_record_array_preserves_receiver_prefix_and_missing_status(self):
        types='TYPE one=STRUCTURE n:REAL ENDSTRUCTURE two=STRUCTURE n:SHORT ENDSTRUCTURE'
        state=execute("a[1].n=32767.9 b[2].n=9 GET_VAR(e,'','A',b,s)",prefix=types,decl='a:ARRAY[1]OF one b:ARRAY[2]OF two')
        self.assertEqual((state['B'],state['S']),([{'N':MISSING},{'N':9}],12311))

    def test_real_narrow_policy_describes_exact_reference_boundary(self):
        policy=program('out=7.9')[1].report['real_integral_policy']
        self.assertIn('toward zero',policy['conversion']);self.assertIn('MAXINT',policy['domains'])
        self.assertIn('BYNAME',policy['exact']);self.assertFalse(policy['controller_validated'])
        self.assertEqual(policy['guide'],'docs/real-integral-conversions.md')


if __name__=='__main__':unittest.main()
