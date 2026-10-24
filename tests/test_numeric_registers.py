"""Explicit memory registers, checked multi-output operations and portable statuses."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


ROOT=Path(__file__).resolve().parents[1]
DECLARATIONS='flag: BOOLEAN value,code,total,i: INTEGER real_value: REAL'


def compile_program(body, *, declarations=DECLARATIONS, prefix='', routines='', translator=translate, labelled=False):
    source=f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n'+('label::\n' if labelled else '')+body+'\nEND T'
    result=translator(source,filename='registers.kl'); namespace={'__name__':'register_test'}
    exec(result.python_source,namespace)
    return namespace['Program'],result


def execute(body, *, initial=None, count=3, **options):
    program,result=compile_program(body,**options); bank=rt.NumericRegisters(count,initial)
    p=program(registers=bank); state=p.run()
    return state,bank,p,result


def outputs():
    cells=dict(flag=False,value=17,real_value=2.5,code=99)
    return cells,[rt.Reference(spec,cells,key) for key,spec in [('flag',('BOOLEAN',)),('value',('INTEGER',)),('real_value',('REAL',)),('code',('INTEGER',))]]


class RegisterBankTests(unittest.TestCase):
    def test_explicit_empty_bank_has_no_implicit_values(self):
        bank=rt.NumericRegisters(3); self.assertEqual(bank.count,3); self.assertEqual(bank.snapshot(),{})
        self.assertEqual(bank.read(1),(rt.REGISTER_UNINITIALIZED,None))
    def test_seed_types_and_defensive_ownership(self):
        seed={1:7,2:7.0}; bank=rt.NumericRegisters(3,seed); seed[1]=99
        snapshot=bank.snapshot(); snapshot[2]=99
        self.assertEqual(bank.snapshot(),{1:7,2:7.0}); self.assertIs(type(bank.read(1)[1]),int); self.assertIs(type(bank.read(2)[1]),float)
    def test_count_validation(self):
        for count in (0,-1,32768,True,3.,None):
            with self.subTest(count=count),self.assertRaises(ValueError): rt.NumericRegisters(count)
    def test_seed_numbers_must_be_valid_integer_indices(self):
        for number in (0,-1,4,True,'1'):
            with self.subTest(number=number),self.assertRaises((ValueError,rt.KarelRuntimeError)): rt.NumericRegisters(3,{number:7})
    def test_seed_numeric_guards(self):
        for value in (True,None,'7',float('inf'),float('nan'),2**31,2147483647):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError): rt.NumericRegisters(3,{1:value})
    def test_pythonic_floats_without_global_mode_dependence(self):
        bank=rt.NumericRegisters(3,{1:.1,2:1e200})
        self.assertEqual(bank.snapshot(),{1:.1,2:1e200})
    def test_host_write_and_read_preserve_kind(self):
        bank=rt.NumericRegisters(1,{1:7}); self.assertEqual(bank.write(1,7.),0)
        self.assertIs(type(bank.read(1)[1]),float); self.assertEqual(bank.write(1,-8),0); self.assertIs(type(bank.read(1)[1]),int)
    def test_out_of_range_host_operations_preserve_bank(self):
        bank=rt.NumericRegisters(1,{1:7})
        self.assertEqual(bank.write(2,8),rt.REGISTER_OUT_OF_RANGE); self.assertEqual(bank.read(2),(rt.REGISTER_OUT_OF_RANGE,None)); self.assertEqual(bank.snapshot(),{1:7})
    def test_config_roundtrip(self): self.assertEqual(rt.NumericRegisters.from_config({'count':3,'values':{'1':7,'2':.1}}).snapshot(),{1:7,2:.1})
    def test_config_shape_and_keys(self):
        for config in ([],{}, {'count':3}, {'count':3,'values':[]},{'count':3,'values':{},'extra':1},
                       {'count':3,'values':{'01':7}}, {'count':3,'values':{'+1':7}}, {'count':3,'values':{'4':7}}, {'count':3,'values':{1:7}}):
            with self.subTest(config=config),self.assertRaises((TypeError,ValueError,rt.KarelRuntimeError)): rt.NumericRegisters.from_config(config)
    def test_count_is_read_only(self):
        bank=rt.NumericRegisters(1)
        with self.assertRaises(AttributeError): bank.count=2


class RegisterBehaviorTests(unittest.TestCase):
    def test_integer_get_preserves_inactive_real_output(self):
        state,_,_,_=execute('real_value=2.5 GET_REG(1,flag,value,real_value,code)',initial={1:-7})
        self.assertEqual((state['FLAG'],state['VALUE'],state['REAL_VALUE'],state['CODE']),(False,-7,2.5,0))
    def test_real_get_preserves_inactive_integer_output(self):
        state,_,_,_=execute('value=17 GET_REG(1,flag,value,real_value,code)',initial={1:.1})
        self.assertEqual((state['FLAG'],state['VALUE'],state['REAL_VALUE'],state['CODE']),(True,17,.1,0))
    def test_unused_output_can_remain_uninitialized(self):
        state,_,_,_=execute('GET_REG(1,flag,value,real_value,code)',initial={1:7})
        self.assertEqual(state['REAL_VALUE'],{'uninitialized':True}); self.assertEqual(state['VALUE'],7)
    def test_missing_preserves_all_data_outputs(self):
        state,_,_,_=execute('flag=TRUE value=17 real_value=2.5 GET_REG(1,flag,value,real_value,code)')
        self.assertEqual((state['FLAG'],state['VALUE'],state['REAL_VALUE'],state['CODE']),(True,17,2.5,rt.REGISTER_UNINITIALIZED))
    def test_missing_preserves_unknown_output_state(self):
        state,_,_,_=execute('GET_REG(1,flag,value,real_value,code)')
        self.assertTrue(all(state[key]=={'uninitialized':True} for key in ('FLAG','VALUE','REAL_VALUE'))); self.assertEqual(state['CODE'],1)
    def test_out_of_range_get_reports_portable_status(self):
        for number in (0,-1,4,2147483647):
            with self.subTest(number=number): self.assertEqual(execute(f'GET_REG({number},flag,value,real_value,code)')[0]['CODE'],2)
    def test_integer_set_and_get(self):
        state,bank,_,_=execute('SET_INT_REG(1,-42,code) GET_REG(1,flag,value,real_value,code)')
        self.assertEqual((state['VALUE'],state['FLAG'],state['CODE']),(-42,False,0)); self.assertEqual(bank.snapshot(),{1:-42})
    def test_real_set_promotes_integer_input(self):
        state,bank,_,_=execute('SET_REAL_REG(1,7,code) GET_REG(1,flag,value,real_value,code)')
        self.assertEqual((state['REAL_VALUE'],state['FLAG'],state['CODE']),(7.,True,0)); self.assertIs(type(bank.snapshot()[1]),float)
    def test_set_changes_numeric_kind(self):
        state,bank,_,_=execute('SET_REAL_REG(1,.1,code) SET_INT_REG(1,8,code) GET_REG(1,flag,value,real_value,code)')
        self.assertEqual((state['FLAG'],bank.snapshot()),(False,{1:8}))
    def test_out_of_range_set_preserves_bank(self):
        state,bank,_,_=execute('SET_INT_REG(4,8,code)',initial={1:7})
        self.assertEqual((state['CODE'],bank.snapshot()),(2,{1:7}))
    def test_bank_persists_across_runs(self):
        Program,_=compile_program('GET_REG(1,flag,value,real_value,code) SET_INT_REG(1,value+1,code)')
        bank=rt.NumericRegisters(1,{1:7}); p=Program(registers=bank); p.run(); p.run()
        self.assertEqual(bank.snapshot(),{1:9}); self.assertEqual(len(p.register_requests),2)
    def test_shared_bank_between_programs(self):
        Writer,_=compile_program('SET_INT_REG(1,42,code)'); Reader,_=compile_program('GET_REG(1,flag,value,real_value,code)')
        bank=rt.NumericRegisters(1); Writer(registers=bank).run(); self.assertEqual(Reader(registers=bank).run()['VALUE'],42)
    def test_separate_banks_are_independent(self):
        state,bank,_,_=execute('SET_INT_REG(1,42,code)'); other=rt.NumericRegisters(1)
        self.assertEqual(bank.snapshot(),{1:42}); self.assertEqual(other.snapshot(),{})
    def test_aliases_using_and_nested_outputs(self):
        state,_,_,_=execute('USING box DO GET_REG(1,flag,values[1],real_value,code) ENDUSING',initial={1:42},
                           prefix='TYPE number=INTEGER packet=STRUCTURE flag: BOOLEAN values: ARRAY[1] OF number real_value: REAL code: number ENDSTRUCTURE',declarations='box: packet')
        self.assertEqual((state['BOX']['VALUES'],state['BOX']['FLAG'],state['BOX']['CODE']),([42],False,0))
    def test_reference_formal_outputs(self):
        state,_,_,_=execute('load(flag,value,real_value,code)',initial={1:42},routines='ROUTINE load(f: BOOLEAN; n: INTEGER; r: REAL; s: INTEGER) BEGIN GET_REG(1,f,n,r,s) END load')
        self.assertEqual((state['VALUE'],state['CODE']),(42,0))
    def test_label_dispatch(self): self.assertEqual(execute('SET_INT_REG(1,42,code)',labelled=True)[1].snapshot(),{1:42})


class RegisterEffectTests(unittest.TestCase):
    def test_get_captures_inputs_and_outputs_once_in_order(self):
        routines='ROUTINE number: INTEGER BEGIN total=total*10+1 RETURN 1 END number\n'
        routines+='\n'.join(f'ROUTINE {name}: INTEGER BEGIN total=total*10+{digit} RETURN 1 END {name}' for name,digit in [('fidx',2),('iidx',3),('ridx',4),('sidx',5)])
        state,_,_,_=execute('total=0 GET_REG(number,flags[fidx],ints[iidx],reals[ridx],codes[sidx])',initial={1:42},routines=routines,
                           declarations=DECLARATIONS+' flags: ARRAY[1] OF BOOLEAN ints,codes: ARRAY[1] OF INTEGER reals: ARRAY[1] OF REAL')
        self.assertEqual((state['TOTAL'],state['INTS']),(12345,[42]))
    def test_set_captures_source_before_status_index_effect(self):
        state,bank,_,_=execute('value=42 SET_INT_REG(1,value,codes[idx])',declarations=DECLARATIONS+' codes: ARRAY[1] OF INTEGER',routines='ROUTINE idx: INTEGER BEGIN value=99 RETURN 1 END idx')
        self.assertEqual((state['VALUE'],bank.snapshot()),(99,{1:42}))
    def test_unknown_input_skips_status_effect_and_bank_write(self):
        Program,_=compile_program('total=0 SET_INT_REG(1,value,codes[idx])',declarations=DECLARATIONS+' codes: ARRAY[1] OF INTEGER',routines='ROUTINE idx: INTEGER BEGIN total=9 RETURN 1 END idx')
        bank=rt.NumericRegisters(1,{1:7}); p=Program(registers=bank)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['TOTAL'],bank.snapshot()),(0,{1:7})); self.assertEqual(p.register_requests,())
    def test_overlap_fails_before_get_outputs(self):
        Program,_=compile_program('value=17 flag=TRUE GET_REG(1,flag,value,real_value,value)'); p=Program(registers=rt.NumericRegisters(1,{1:42}))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
        self.assertEqual((p.snapshot()['VALUE'],p.snapshot()['FLAG']),(17,True)); self.assertEqual(p.register_requests,())
    def test_prior_index_effect_survives_overlap_error(self):
        Program,_=compile_program('total=0 GET_REG(1,flag,items[idx],real_value,items[1])',declarations=DECLARATIONS+' items: ARRAY[1] OF INTEGER',routines='ROUTINE idx: INTEGER BEGIN total=9 RETURN 1 END idx')
        p=Program(registers=rt.NumericRegisters(1,{1:42}))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TOTAL'],9)
    def test_transitive_read_and_write_reports(self):
        _,_,_,result=execute('outer()',routines='ROUTINE inner BEGIN SET_INT_REG(1,7,code) GET_REG(1,flag,value,real_value,code) END inner\nROUTINE outer BEGIN inner END outer')
        for name in ('INNER','OUTER'):
            self.assertTrue(result.report['routine_effects'][name]['potential_register_reads']); self.assertTrue(result.report['routine_effects'][name]['potential_register_writes'])
    def test_formal_output_write_analysis(self):
        Program,result=compile_program('load(flag,value,real_value,code)',routines='ROUTINE load(f: BOOLEAN; n: INTEGER; r: REAL; s: INTEGER) BEGIN GET_REG(1,f,n,r,s) END load')
        self.assertEqual(result.report['routine_effects']['LOAD']['potential_parameter_writes'],['F','N','R','S'])
    def test_completed_bank_write_survives_later_abort(self):
        Program,_=compile_program('SET_INT_REG(1,42,code) ABORT'); bank=rt.NumericRegisters(1); p=Program(registers=bank)
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual(bank.snapshot(),{1:42}); self.assertEqual(p.register_requests[0]['status'],0)
    def test_failure_unwinds_for_and_frames(self):
        Program,_=compile_program('FOR i=1 TO 2 DO load() ENDFOR',routines='ROUTINE load BEGIN SET_INT_REG(1,value,code) END load')
        p=Program(registers=rt.NumericRegisters(1))
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['I'],{'uninitialized':True}); self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
    def test_observations_are_defensive_source_records_without_values(self):
        _,_,p,result=execute('SET_INT_REG(1,42,code)\nGET_REG(1,flag,value,real_value,code)')
        self.assertEqual([(r['procedure'],r['line'],r['status']) for r in p.register_requests],[('SET_INT_REG',6,0),('GET_REG',7,0)])
        observed=p.register_requests; observed[0]['status']=99; self.assertEqual(p.register_requests[0]['status'],0)
        self.assertTrue(all('value' not in row for row in p.register_requests)); self.assertFalse(result.report['register_policy']['controller_validated']); json.dumps(result.report)
        self.assertEqual([r['output_parameters'] for r in result.report['register_operations']],[[3],[2,3,4,5]])


class RegisterSourceGuardTests(unittest.TestCase):
    def reject(self,body,code,**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)
    def test_arity(self):
        for body in ('GET_REG(1,value)','SET_INT_REG(1,7)','SET_REAL_REG(1,.1,code,value)'):
            with self.subTest(body=body): self.reject(body,'E_ARGUMENTS')
    def test_input_types(self):
        for body in ("SET_INT_REG('1',7,code)",'SET_INT_REG(1,1.5,code)','SET_REAL_REG(1,TRUE,code)'):
            with self.subTest(body=body): self.reject(body,'E_TYPE')
    def test_exact_output_types(self):
        for body in ('GET_REG(1,value,code,real_value,total)','GET_REG(1,flag,real_value,real_value,code)','GET_REG(1,flag,value,value,code)','SET_INT_REG(1,7,flag)'):
            with self.subTest(body=body): self.reject(body,'E_TYPE')
    def test_grouped_and_constant_outputs(self):
        for target in ('(code)','1','constant'):
            with self.subTest(target=target): self.reject(f'SET_INT_REG(1,7,{target})','E_OUTPUT_ARGUMENT',prefix='CONST constant=1')
    def test_config_subfields_remain_protected(self): self.reject('SET_INT_REG(1,7,cfg.cfg_turn_no1)','E_CONFIG_OUTPUT',declarations=DECLARATIONS+' cfg: CONFIG')
    def test_position_fields_remain_protected(self): self.reject('GET_REG(1,flag,value,pose.orient.x,code)','E_POSITION_READ_ONLY',declarations=DECLARATIONS+' pose: POSITION')
    def test_direct_for_counter_output_rejected(self): self.reject('FOR i=1 TO 2 DO SET_INT_REG(1,7,i) ENDFOR','E_FOR_COUNTER')
    def test_transitive_get_counter_output_rejected(self): self.reject('FOR i=1 TO 2 DO load(i) ENDFOR','E_FOR_COUNTER',routines='ROUTINE load(n: INTEGER) BEGIN GET_REG(1,flag,n,real_value,code) END load')
    def test_transitive_set_status_counter_rejected(self): self.reject('FOR i=1 TO 2 DO load(i) ENDFOR','E_FOR_COUNTER',routines='ROUTINE load(n: INTEGER) BEGIN SET_INT_REG(1,7,n) END load')
    def test_procedure_expression_rejected(self): self.reject('value=SET_INT_REG(1,7,code)','E_PROCEDURE_RESULT')
    def test_internal_procedures_preserve_signatures(self):
        state,_,_,result=execute('GET_REG(7) SET_INT_REG(8) SET_REAL_REG(9)',routines='ROUTINE GET_REG(n: INTEGER) BEGIN value=n END GET_REG\nROUTINE SET_INT_REG(n: INTEGER) BEGIN total=n END SET_INT_REG\nROUTINE SET_REAL_REG(n: INTEGER) BEGIN code=n END SET_REAL_REG')
        self.assertEqual((state['VALUE'],state['TOTAL'],state['CODE']),(7,8,9)); self.assertEqual(result.report['register_operations'],[])
    def test_internal_function_precedence(self):
        state,_,_,_=execute('value=GET_REG(7)',routines='ROUTINE GET_REG(n: INTEGER): INTEGER BEGIN RETURN n+1 END GET_REG')
        self.assertEqual(state['VALUE'],8)
    def test_ordinary_declarations_remain_usable(self): self.assertEqual(execute('GET_REG=7',declarations='GET_REG: INTEGER')[0]['GET_REG'],7)
    def test_serial_call_and_invalid_mode_arity_remain_blocked(self):
        self.reject('GET_PORT_ATR(code)','E_CALL')
        self.reject('GET_PORT_MOD(code)','E_ARGUMENTS')
    def test_legacy_calls_remain_unsupported(self): self.reject('SET_INT_REG(1,7,code)','E_CALL',translator=legacy_translate)


class RegisterRuntimeGuardTests(unittest.TestCase):
    def test_missing_context_raises_before_outputs(self):
        Program,_=compile_program('code=99 SET_INT_REG(1,7,code)'); p=Program()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit'): p.run()
        self.assertEqual(p.snapshot()['CODE'],99)
    def test_nonbank_and_subclass_context_rejected(self):
        class Other(rt.NumericRegisters): pass
        Program,_=compile_program('value=7')
        for context in ({},1,Other(1)):
            with self.subTest(context=context),self.assertRaises(TypeError): Program(registers=context)
    def test_readonly_or_missing_output_reference(self):
        for bad in (None,rt.ReadOnlyFieldReference(('INTEGER',),{'value':7},'value')):
            cells,refs=outputs(); refs[-1]=bad; state=rt.State({}, {},registers=rt.NumericRegisters(1,{1:42}))
            with self.subTest(bad=bad),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): state.numeric_register('GET_REG',1,*refs)
            self.assertEqual(cells['value'],17); self.assertEqual(state.register_requests,[])
    def test_forged_narrow_output_rejected(self):
        cells,refs=outputs(); refs[1]=rt.Reference(('SHORT',),cells,'value'); state=rt.State({}, {},registers=rt.NumericRegisters(1,{1:42}))
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): state.numeric_register('GET_REG',1,*refs)
        self.assertEqual(cells['value'],17)
    def test_bad_set_value_preserves_bank_and_status(self):
        for value in (True,float('inf'),float('nan'),2147483647):
            bank=rt.NumericRegisters(1,{1:7}); state=rt.State({}, {},registers=bank); cells,refs=outputs()
            with self.subTest(value=value),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): state.numeric_register('SET_INT_REG',1,value,refs[-1])
            self.assertEqual((bank.snapshot(),cells['code']),({1:7},99))
    def test_wrong_runtime_procedure_or_arity(self):
        state=rt.State({}, {},registers=rt.NumericRegisters(1))
        for name in ('bad','GET_REG','SET_INT_REG'):
            with self.subTest(name=name),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): state.numeric_register(name,1)
    def test_legacy_runtime_guard(self):
        state=rt.State({}, {},registers=rt.NumericRegisters(1))
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): state.numeric_register('SET_INT_REG',1,7,outputs()[1][-1])


class RegisterCLITests(unittest.TestCase):
    def run_script(self,config,*,missing=False,body='SET_INT_REG(1,7,code) GET_REG(1,flag,value,real_value,code)',read_values=None):
        Program,result=compile_program(body)
        with tempfile.TemporaryDirectory() as folder:
            package=Path(folder)/'karel2py'; package.mkdir()
            for name in ('__init__.py','runtime.py','extended.py','storage.py','kinematics.py','scheduling.py','control.py','clocks.py', 'fileops.py', 'pulses.py', 'configtext.py', 'teach.py'): (package/name).write_bytes((ROOT/'karel2py'/name).read_bytes())
            module=Path(folder)/'converted.py'; module.write_text(result.python_source,encoding='utf-8')
            initial=Path(folder)/'registers.json'; initial.write_text(config,encoding='utf-8')
            command=[sys.executable,str(module),* ([] if missing else ['--registers',str(initial)])]
            if read_values is not None:
                batches=Path(folder)/'read.json'; batches.write_text(json.dumps(read_values),encoding='utf-8')
                command.extend(['--read-values',str(batches)])
            return subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    def test_explicit_json_context_executes(self):
        result=self.run_script('{"count":3,"values":{}}'); self.assertEqual(result.returncode,0,result.stderr); self.assertIn("'VALUE': 7",result.stdout)
    def test_context_is_required(self):
        result=self.run_script('',missing=True); self.assertEqual(result.returncode,2); self.assertIn('--registers',result.stderr)
    def test_context_composes_with_read_input(self):
        result=self.run_script('{"count":3,"values":{}}',body='READ(value) SET_INT_REG(1,value,code)',read_values=[[11]])
        self.assertEqual(result.returncode,0,result.stderr); self.assertIn("'VALUE': 11",result.stdout)
    def test_bad_json_or_config_rejected(self):
        for config in ('bad','[]','{"count":0,"values":{}}','{"count":3,"values":{"1":true}}','{"count":3,"values":{"01":7}}'):
            with self.subTest(config=config):
                result=self.run_script(config); self.assertEqual(result.returncode,2); self.assertIn('Unable to load numeric registers',result.stderr)


class AuthoredNumericRegisterTests(unittest.TestCase):
    def test_complete_fixture(self):
        source=ROOT/'examples/pythonic_numeric_registers.kl'; result=translate(source.read_text(),filename=source.name)
        namespace={'__name__':'authored_registers'}; exec(result.python_source,namespace)
        bank=rt.NumericRegisters.from_config(json.loads(source.with_suffix('.registers.initial.json').read_text()))
        output=[]; p=namespace['Program'](registers=bank,write=output.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(output,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual({str(key):value for key,value in bank.snapshot().items()},json.loads(source.with_suffix('.registers.expected.json').read_text()))
        self.assertEqual([row['status'] for row in p.register_requests],[0,0,0,0,1,2]); self.assertEqual(len(result.report['register_operations']),6)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
