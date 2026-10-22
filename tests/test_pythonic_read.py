"""Typed offline READ input, captured destinations, failures and effect proofs."""
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


DECLARATIONS = 'x,y,i,total: INTEGER r: REAL flag: BOOLEAN text: STRING[4] a: ARRAY[2] OF INTEGER'


def compile_program(body, *, declarations=DECLARATIONS, types='', constants='', routines='',
                    batches=None, read=None, translator=translate, labelled=False, **context):
    source = f'PROGRAM T\n{constants}\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n'
    source += ('marker::\n' if labelled else '') + body + '\nEND T'
    result = translator(source, filename='pythonic_read.kl')
    namespace = {'__name__':'read_test'}
    exec(result.python_source, namespace)
    if batches is not None:
        responses=iter(batches)
        read=lambda request: next(responses)
    return namespace['Program'](read=read, **context), result


def execute(body, **options): return compile_program(body, **options)[0].run()


class ReadValueTests(unittest.TestCase):
    def test_integer_input(self): self.assertEqual(execute('READ(x)', batches=[[42]])['X'],42)
    def test_mixed_typed_input(self):
        state=execute('READ(x,r,flag,text)', batches=[[7,.25,True,'widget']])
        self.assertEqual((state['X'],state['R'],state['FLAG'],state['TEXT']), (7,.25,True,'widg'))
    def test_tuple_response(self): self.assertEqual(execute('READ(x)', read=lambda request:(42,))['X'],42)
    def test_false_boolean(self): self.assertFalse(execute('READ(flag)', batches=[[False]])['FLAG'])
    def test_integer_promotes_to_real(self):
        value=execute('READ(r)', batches=[[7]])['R']
        self.assertIs(type(value),float)
        self.assertEqual(value,7.0)
    def test_minint_and_maximum_storable(self):
        state=execute('READ(x,y)', batches=[[-2147483648,2147483646]])
        self.assertEqual((state['X'],state['Y']),(-2147483648,2147483646))
    def test_empty_string(self): self.assertEqual(execute('READ(text)', batches=[['']])['TEXT'],'')
    def test_string_whitespace_is_preserved(self): self.assertEqual(execute('READ(text)', batches=[[' a b ']])['TEXT'],' a b')
    def test_byte_element_can_be_initialized(self):
        state=execute('READ(data[1]) x=data[1]', declarations=DECLARATIONS+' data: ARRAY[1] OF BYTE', batches=[[255]])
        self.assertEqual(state['X'],255)
    def test_short_sentinel_keeps_existing_meaning(self):
        state=execute('READ(data[1]) flag=UNINIT(data[1])', declarations=DECLARATIONS+' data: ARRAY[1] OF SHORT', batches=[[32767]])
        self.assertTrue(state['FLAG'])
    def test_structure_fields_and_alias_types(self):
        state=execute('READ(item.id,item.label)', types='TYPE count_t=INTEGER item_t=STRUCTURE id: count_t label: STRING[3] ENDSTRUCTURE',
                      declarations='item: item_t', batches=[[7,'ready']])
        self.assertEqual(state,{'ITEM':{'ID':7,'LABEL':'rea'}})
    def test_using_fields_keep_storage_roots(self):
        state=execute('USING item DO READ(id) ENDUSING', types='TYPE item_t=STRUCTURE id: INTEGER ENDSTRUCTURE',
                      declarations='item: item_t', batches=[[7]])
        self.assertEqual(state,{'ITEM':{'ID':7}})
    def test_writable_position_location(self):
        state=execute('READ(p.location.x)', declarations='p: POSITION', batches=[[.1]])
        self.assertEqual(state['P']['LOCATION']['X'],.1)
    def test_reference_formal_writes_caller(self):
        self.assertEqual(execute('load(x)', routines='ROUTINE load(p: INTEGER) BEGIN READ(p) END load',batches=[[9]])['X'],9)
    def test_value_formal_keeps_private_input(self):
        state=execute('x=7 load((x))', routines='ROUTINE load(p: INTEGER) BEGIN READ(p) y=p END load',batches=[[9]])
        self.assertEqual((state['X'],state['Y']),(7,9))
    def test_string_formal_keeps_caller_capacity(self):
        program,_=compile_program('load(text)', routines='ROUTINE load(p: STRING) BEGIN READ(p) END load',batches=[['abcdef']])
        self.assertEqual(program.run()['TEXT'],'abcd')
        self.assertEqual(program.read_requests[0]['targets'][0]['type_spec'],('STRING',4))
    def test_function_local_input_can_be_returned(self):
        self.assertEqual(execute('x=load()',routines='ROUTINE load: INTEGER VAR p: INTEGER BEGIN READ(p) RETURN p END load',batches=[[8]])['X'],8)
    def test_multiple_statements_consume_one_batch_each(self):
        self.assertEqual(execute('READ(x) READ(y) total=x+y',batches=[[10],[20]])['TOTAL'],30)


class ReadCaptureTests(unittest.TestCase):
    def test_targets_captured_before_response_assignments(self):
        state=execute('x=1 READ(x,a[x])',batches=[[2,9]])
        self.assertEqual((state['X'],state['A']),(2,[9,{'uninitialized':True}]))
    def test_repeated_target_last_value_wins(self): self.assertEqual(execute('READ(x,x)',batches=[[1,2]])['X'],2)
    def test_target_indices_evaluate_once_in_order(self):
        routines='ROUTINE choose: INTEGER BEGIN i=i+1 RETURN i END choose'
        state=execute('i=0 READ(a[choose()],a[choose()])',routines=routines,batches=[[7,8]])
        self.assertEqual((state['I'],state['A']),(2,[7,8]))
    def test_index_failure_creates_no_outer_request(self):
        calls=[]
        program,_=compile_program('READ(a[3],x)',read=lambda request:calls.append(request))
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((calls,program.read_requests),([],()))
    def test_nested_input_during_target_capture_precedes_outer_request(self):
        program,_=compile_program('READ(a[choose()])',batches=[[1],[7]],
            routines='ROUTINE choose: INTEGER VAR n: INTEGER BEGIN READ(n) RETURN n END choose')
        self.assertEqual(program.run()['A'][0],7)
        self.assertEqual(len(program.read_requests),2)
        self.assertNotEqual(program.read_requests[0]['line'],program.read_requests[1]['line'])
    def test_complete_response_checked_before_any_assignment(self):
        program,_=compile_program('x=7 y=8 READ(x,y)',batches=[[9,'bad']])
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['X'],program.snapshot()['Y']),(7,8))
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_result_rejected')
    def test_alias_first_value_still_validated(self):
        program,_=compile_program('x=7 READ(x,x)',batches=[['bad',9]])
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'],7)
    def test_target_capture_effects_survive_invalid_response(self):
        program,_=compile_program('i=0 READ(a[choose()])',batches=[['bad']],
                                 routines='ROUTINE choose: INTEGER BEGIN i=i+1 RETURN i END choose')
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['I'],1)
    def test_callback_effects_survive_rejected_response(self):
        def reader(request):
            program._state.set('X',99)
            return ['bad']
        program,_=compile_program('x=7 READ(x)',read=reader)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['X'],99)
    def test_labelled_execution_uses_same_input_contract(self):
        outcomes=[]
        for labelled in (False,True):
            program,_=compile_program('READ(x,y) total=x+y',batches=[[7,8]],labelled=labelled)
            outcomes.append((program.run(),program._state.steps))
        self.assertEqual(outcomes[0],outcomes[1])


class ReadCallbackTests(unittest.TestCase):
    def test_missing_adapter_has_explicit_failure(self):
        program,_=compile_program('READ(x)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit Program'): program.run()
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'missing_adapter')
    def test_noncallable_adapter_is_rejected(self):
        with self.assertRaises(TypeError): compile_program('READ(x)',read=7)
    def test_callback_exception_is_source_located_and_not_retried(self):
        calls=[]
        def reader(request):
            calls.append(request)
            raise OSError('offline input failed')
        program,_=compile_program('READ(x)',read=reader)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'READ input callback failed') as caught: program.run()
        self.assertIsInstance(caught.exception.__cause__,OSError)
        self.assertIsNotNone(caught.exception.line)
        self.assertEqual(len(calls),1)
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_failed')
    def test_callback_interruption_propagates(self):
        def reader(request): raise KeyboardInterrupt()
        program,_=compile_program('READ(x)',read=reader)
        with self.assertRaises(KeyboardInterrupt): program.run()
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_interrupted')
    def test_exhausted_batches_fail_without_invented_values(self):
        program,_=compile_program('x=7 READ(x)',batches=[])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'callback failed'): program.run()
        self.assertEqual(program.snapshot()['X'],7)
    def test_async_callback_is_not_awaited(self):
        entered=[]
        async def reader(request):
            entered.append(True)
            return [7]
        program,_=compile_program('READ(x)',read=reader)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'list/tuple'): program.run()
        self.assertEqual(entered,[])
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_result_rejected')
    def test_metadata_is_defensive(self):
        def reader(request):
            request['targets'][0]['type_spec']=('STRING',254)
            request['targets'].clear()
            request['line']=-1
            return [7]
        program,_=compile_program('READ(x)',read=reader)
        self.assertEqual(program.run()['X'],7)
        record=program.read_requests[0]
        self.assertEqual(record['targets'][0]['type_spec'],('INTEGER',))
        self.assertGreater(record['line'],0)
    def test_observations_are_deep_copies(self):
        program,_=compile_program('READ(x)',batches=[[7]])
        program.run()
        program.read_requests[0]['targets'].clear()
        program.read_requests[0]['adapter_outcome']='changed'
        self.assertEqual(len(program.read_requests[0]['targets']),1)
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_completed')
    def test_observations_do_not_retain_input_values(self):
        program,_=compile_program('READ(text)',batches=[['private-input']])
        program.run()
        self.assertNotIn('private-input',json.dumps(program.read_requests))
    def test_warm_run_clears_observations(self):
        program,_=compile_program('READ(x)',batches=[[7],[8]])
        program.run()
        self.assertEqual(program.run()['X'],8)
        self.assertEqual(len(program.read_requests),1)


class ReadValidationTests(unittest.TestCase):
    def reject_value(self,value,target='x'):
        program,_=compile_program('READ('+target+')',batches=[[value]])
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.read_requests[0]['adapter_outcome'],'callback_result_rejected')
    def test_wrong_response_shape(self):
        for response in (None,7,'7',{'x':7},[],[7,8],iter([7])):
            with self.subTest(response=response):
                program,_=compile_program('READ(x)',read=lambda request:response)
                with self.assertRaises(rt.KarelRuntimeError): program.run()
    def test_integer_rejects_real_boolean_and_text(self):
        for value in (7.0,True,'7'):
            with self.subTest(value=value): self.reject_value(value)
    def test_integer_range_and_maxint(self):
        for value in (-2147483649,2147483647,2147483648):
            with self.subTest(value=value): self.reject_value(value)
    def test_real_rejects_nonfinite_and_boolean(self):
        for value in (float('nan'),float('inf'),True):
            with self.subTest(value=value): self.reject_value(value,'r')
    def test_boolean_rejects_numeric_input(self): self.reject_value(1,'flag')
    def test_nonascii_input_checked_before_truncation(self): self.reject_value('abcd\u00e9','text')
    def test_oversize_string_checked_before_truncation(self): self.reject_value('x'*255,'text')
    def test_uninitialized_host_value_is_rejected(self): self.reject_value(rt.UNINITIALIZED)
    def test_byte_range_retains_prior_value(self):
        program,_=compile_program('data[1]=7 READ(data[1])',declarations='data: ARRAY[1] OF BYTE',batches=[[256]])
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['DATA'],[7])
    def test_runtime_rejects_protected_or_invalid_references_before_callback(self):
        calls=[]
        state=rt.State({}, {},read=lambda request:calls.append(request))
        storage={'x':1}
        references=[rt.ReadOnlyFieldReference(rt.REAL,storage,'x'),rt.ConfigFieldReference(rt.INTEGER,storage,'x'),
                    rt.Reference(('STRING',None),storage,'x'),rt.Reference(('VECTOR',),storage,'x')]
        for reference in references:
            with self.subTest(reference=reference), self.assertRaises(rt.KarelRuntimeError): state.read_items([reference],17)
        self.assertEqual((calls,state.read_requests),([],[]))


class ReadEffectAndCleanupTests(unittest.TestCase):
    def test_direct_and_transitive_effects(self):
        routines='ROUTINE load(p: INTEGER) BEGIN READ(p) END load ROUTINE outer BEGIN load(x) END outer'
        _,result=compile_program('outer()',routines=routines,batches=[[7]])
        load=result.report['routine_effects']['LOAD']; outer=result.report['routine_effects']['OUTER']
        self.assertEqual(load['potential_parameter_writes'],['P'])
        self.assertEqual(outer['potential_global_writes'],['X'])
        self.assertTrue(outer['potential_input_requests'])
    def test_for_rejects_writable_input_formal(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR i=1 TO 2 DO load(i) ENDFOR',routines='ROUTINE load(p: INTEGER) BEGIN READ(p) END load')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_for_rejects_transitive_global_counter_input(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR i=1 TO 2 DO outer() ENDFOR',routines='ROUTINE load BEGIN READ(i) END load ROUTINE outer BEGIN load() END outer')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_for_allows_input_to_other_global(self):
        state=execute('total=0 FOR i=1 TO 2 DO load() total=total+x ENDFOR',
                      routines='ROUTINE load BEGIN READ(x) END load',batches=[[7],[8]])
        self.assertEqual(state['TOTAL'],15)
    def test_for_counter_value_argument_remains_private(self):
        state=execute('FOR i=1 TO 2 DO load((i)) ENDFOR',routines='ROUTINE load(p: INTEGER) BEGIN READ(p) x=p END load',batches=[[7],[8]])
        self.assertEqual((state['X'],state['I']),(8,{'uninitialized':True}))
    def test_failure_unwinds_routine_frames(self):
        program,_=compile_program('load()',routines='ROUTINE load VAR p: INTEGER BEGIN READ(p) END load',batches=[['bad']])
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_callback_interruption_clears_for_counter(self):
        def reader(request): raise KeyboardInterrupt()
        program,_=compile_program('FOR i=1 TO 2 DO READ(x) ENDFOR',read=reader)
        with self.assertRaises(KeyboardInterrupt): program.run()
        self.assertEqual(program.snapshot()['I'],{'uninitialized':True})
    def test_step_budget_exhaustion_precedes_callback(self):
        calls=[]
        program,_=compile_program('x=7 READ(x)',read=lambda request:calls.append(request))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'): program.run(max_steps=1)
        self.assertEqual((calls,program.read_requests),([],()))
    def test_local_storage_shadowing_a_function_remains_storage(self):
        state=execute('load()',routines='ROUTINE value: INTEGER BEGIN RETURN 1 END value '
                      'ROUTINE load VAR value: INTEGER BEGIN READ(value) x=value END load',batches=[[7]])
        self.assertEqual(state['X'],7)


class ReadSourceGuardTests(unittest.TestCase):
    def reject(self,body,code,**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)
        self.assertEqual(caught.exception.filename,'pythonic_read.kl')
    def test_explicit_device_is_blocked(self): self.reject('READ INPUT(x)','E_SYMBOL')
    def test_empty_input_list(self): self.reject('READ()','E_READ_ITEM')
    def test_legacy_cr_is_blocked(self): self.reject('READ(x,CR)','E_UNSUPPORTED',translator=legacy_translate)
    def test_legacy_formats_are_blocked(self): self.reject('READ(x::4)','E_UNSUPPORTED',translator=legacy_translate)
    def test_expression_destination(self): self.reject('READ(x+1)','E_READ_ITEM')
    def test_grouped_destination(self): self.reject('READ((x))','E_READ_ITEM')
    def test_constant_destination(self): self.reject('READ(code)','E_CONST_ASSIGN',constants='CONST code=7')
    def test_aggregate_destination(self): self.reject('READ(a)','E_READ_TYPE')
    def test_temporary_field_destination(self): self.reject('READ(VEC(1,2,3).x)','E_READ_ITEM')
    def test_position_orientation(self): self.reject('READ(p.normal.x)','E_POSITION_READ_ONLY',declarations='p: POSITION')
    def test_config_field(self): self.reject('READ(c.turn_no1)','E_CONFIG_OUTPUT',declarations='c: CONFIG')
    def test_active_counter(self): self.reject('FOR i=1 TO 2 DO READ(i) ENDFOR','E_FOR_COUNTER')
    def test_item_limit(self): self.reject('READ('+','.join(['x']*1025)+')','E_READ_LIMIT')
    def test_maximum_item_count(self): self.assertEqual(execute('READ('+','.join(['x']*1024)+')',batches=[[7]*1024])['X'],7)
    def test_strict_guard_remains_internal(self): self.reject('READ(x)','E_UNSUPPORTED',translator=legacy_translate)
    def test_report_records_destinations_and_policy(self):
        _,result=compile_program('READ(x,text)')
        self.assertEqual([row['root'] for row in result.report['reads'][0]['destinations']],['X','TEXT'])
        self.assertFalse(result.report['read_policy']['controller_validated'])


class ReadScriptAndExampleTests(unittest.TestCase):
    def run_script(self,body,values,arguments=(),**options):
        program,result=compile_program(body,**options)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'converted.py'; data=root/'values.json'
            package=root/'karel2py'; package.mkdir()
            for name in ('__init__.py','runtime.py','extended.py'):
                shutil.copyfile(Path(__file__).resolve().parents[1]/'karel2py'/name,package/name)
            source.write_text(result.python_source,encoding='utf-8')
            data.write_text(json.dumps(values),encoding='utf-8')
            process=subprocess.run([sys.executable,str(source),'--read-values',str(data),*arguments],
                                   capture_output=True,text=True)
            return process
    def test_generated_script_consumes_json_batches(self):
        process=self.run_script('READ(x) READ(y)',[[7],[8]])
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertIn("'X': 7",process.stdout)
        self.assertIn("'Y': 8",process.stdout)
    def test_script_rejects_wrong_json_outer_shape(self):
        process=self.run_script('READ(x)',{'x':7})
        self.assertEqual(process.returncode,2)
        self.assertIn('JSON list',process.stderr)
    def test_read_and_joint_context_compose(self):
        process=self.run_script('READ(x) data[1]=5 CNV_REL_JPOS(data,j,status)',[[7]],arguments=('--joint-axes','1'),
                                declarations='x,status: INTEGER data: ARRAY[1] OF REAL j: JOINTPOS1')
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertIn("'STATUS': 0",process.stdout)
    def test_authored_example_complete_fixtures(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_read.kl'
        batches=json.loads(source.with_suffix('.read.values.json').read_text())
        responses=iter(batches); output=[]
        result=translate(source.read_text(),filename=source.name); namespace={'__name__':'read_fixture'}
        exec(result.python_source,namespace)
        program=namespace['Program'](read=lambda request:next(responses),write=output.append)
        self.assertEqual(program.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(output,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(json.loads(json.dumps(program.read_requests)),json.loads(source.with_suffix('.read.expected.json').read_text()))
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
