"""Packed date/time conversion, independent bit patterns and checked output effects."""
from datetime import datetime
import json
from pathlib import Path
import random
import struct
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


DECLARATIONS = 'encoded,other,i,total: INTEGER text,saved: STRING[20]'
EPOCH = 2162688
LEAP = 1482515548


def compile_program(body, *, declarations=DECLARATIONS, prefix='', routines='', translator=translate, labelled=False):
    source=f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n'
    result=translator(source+('label::\n' if labelled else '')+body+'\nEND T',filename='time_text.kl')
    namespace={'__name__':'time_text_test'}; exec(result.python_source,namespace)
    return namespace['Program'](),result


def execute(body, **options): return compile_program(body,**options)[0].run()


def parse(text): return execute("CNV_STR_TIME('"+text.replace("'","''")+"',encoded)")['ENCODED']


def independent_packed(stamp):
    date=(stamp.year-1980)*512+stamp.month*32+stamp.day
    time=stamp.hour*2048+stamp.minute*32+stamp.second//2
    return int.from_bytes(struct.pack('<HH',time,date),'little',signed=True)


class TimeParseTests(unittest.TestCase):
    def test_epoch_known_pattern(self): self.assertEqual(parse('01-JAN-1980 00:00:00'),EPOCH)
    def test_leap_known_pattern_and_odd_seconds(self): self.assertEqual(parse('29-FEB-2024 12:34:57'),LEAP)
    def test_end_of_year_pattern(self): self.assertEqual(parse('31-DEC-2026 23:59:59'),1570750333)
    def test_optional_seconds(self): self.assertEqual(parse('01-JAN-1980 00:00'),EPOCH)
    def test_case_and_outer_whitespace(self): self.assertEqual(parse('  29-fEb-2024 12:34:56\t'),LEAP)
    def test_independent_random_bit_patterns_and_roundtrips(self):
        rng=random.Random(7621)
        # Independently encoded little-endian date/time words, with no runtime constants.
        with rt._numeric_scope('pythonic'):
            for _ in range(250):
                stamp=datetime(rng.randrange(1980,2108),rng.randrange(1,13),rng.randrange(1,29),rng.randrange(24),rng.randrange(60),rng.randrange(60))
                text=f'{stamp.day:02d}-{("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())[stamp.month-1]}-{stamp.year:04d} {stamp.hour:02d}:{stamp.minute:02d}:{stamp.second:02d}'
                cells={'value':99,'text':'prior'}
                rt.time_text_conversion('CNV_STR_TIME',text,rt.Reference(('INTEGER',),cells,'value'))
                self.assertEqual(cells['value'],independent_packed(stamp))
                rt.time_text_conversion('CNV_TIME_STR',cells['value'],rt.Reference(('STRING',20),cells,'text'))
                self.assertEqual(cells['text'],text[:-2]+f'{stamp.second//2*2:02d}')
    def test_calendar_boundaries(self):
        for value in ('29-FEB-2000 00:00','01-JAN-1980 00:00','31-DEC-2107 23:59:58'):
            with self.subTest(value=value): self.assertNotEqual(parse(value),0)
    def test_invalid_calendar_or_clock_writes_zero(self):
        for value in ('29-FEB-2100 00:00','29-FEB-2023 00:00','31-APR-2024 00:00','00-JAN-2024 00:00',
                      '32-JAN-2024 00:00','01-JAN-1979 00:00','01-JAN-2108 00:00','01-JAN-2024 24:00',
                      '01-JAN-2024 00:60','01-JAN-2024 00:00:60','01-XYZ-2024 00:00'):
            with self.subTest(value=value): self.assertEqual(parse(value),0)
    def test_invalid_grammar_writes_zero(self):
        for value in ('','   ','1-JAN-2024 00:00','01-JAN-024 00:00','01-JAN-2024 0:00','01-JAN-2024 00:0',
                      '01-JAN-2024 00:00:0','01-JAN-2024  00:00','01-JAN-2024T00:00','01-JAN-2024 00:00Z',
                      '01-JAN-2024 00:00:00.0','01-JAN-2024 00:00:00 extra'):
            with self.subTest(value=value): self.assertEqual(parse(value),0)
    def test_invalid_text_overwrites_initialized_target(self): self.assertEqual(execute("encoded=42 CNV_STR_TIME('bad',encoded)")['ENCODED'],0)
    def test_signed_bit_patterns_after_2043(self):
        state=execute("CNV_STR_TIME('01-JAN-2044 00:00',encoded) CNV_TIME_STR(encoded,text)")
        self.assertEqual(state['ENCODED'],-2145320960); self.assertEqual(state['TEXT'],'01-JAN-2044 00:00:00')


class TimeFormatTests(unittest.TestCase):
    def test_complete_canonical_text(self): self.assertEqual(execute(f'CNV_TIME_STR({LEAP},text)')['TEXT'],'29-FEB-2024 12:34:56')
    def test_exact_capacity_and_larger_capacity(self):
        for size in (20,40,254):
            with self.subTest(size=size): self.assertEqual(execute(f'CNV_TIME_STR({EPOCH},text)',declarations=f'text: STRING[{size}]')['TEXT'],'01-JAN-1980 00:00:00')
    def test_short_capacity_preserves_output(self):
        p,_=compile_program(f"text='prior' CNV_TIME_STR({EPOCH},text)",declarations='text: STRING[19]')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'): p.run()
        self.assertEqual(p.snapshot()['TEXT'],'prior')
    def test_invalid_packed_fields_preserve_output(self):
        for packed in (0,1<<21,1<<16,EPOCH|24<<11,EPOCH|60<<5,EPOCH|30,EPOCH|31,2147483647,-1):
            p,_=compile_program(f"text='prior' CNV_TIME_STR({packed},text)")
            with self.subTest(packed=packed),self.assertRaisesRegex(rt.KarelRuntimeError,'Packed time'): p.run()
            self.assertEqual(p.snapshot()['TEXT'],'prior')
    def test_uninitialized_source_preserves_output(self):
        p,_=compile_program("text='prior' CNV_TIME_STR(encoded,text)")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TEXT'],'prior')
    def test_uninitialized_text_is_not_invalid_grammar(self):
        p,_=compile_program('encoded=42 CNV_STR_TIME(text,encoded)')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['ENCODED'],42)
    def test_aliases_using_arrays_and_fields(self):
        state=execute("USING packet DO CNV_STR_TIME('01-JAN-1980 00:00',values[1]) CNV_TIME_STR(values[1],labels[1]) ENDUSING",
                      prefix='TYPE stamp=INTEGER label_t=STRING[20] record_t=STRUCTURE values: ARRAY[1] OF stamp labels: ARRAY[1] OF label_t ENDSTRUCTURE',declarations='packet: record_t')
        self.assertEqual(state['PACKET'],{'VALUES':[EPOCH],'LABELS':['01-JAN-1980 00:00:00']})
    def test_reference_formals(self):
        state=execute('load(encoded,text)',routines="ROUTINE load(n: INTEGER; s: STRING) BEGIN CNV_STR_TIME('01-JAN-1980 00:00',n) CNV_TIME_STR(n,s) END load")
        self.assertEqual((state['ENCODED'],state['TEXT']),(EPOCH,'01-JAN-1980 00:00:00'))
    def test_value_string_formal_has_private_writable_output(self):
        state=execute("text='original' emit((text))",routines=f'ROUTINE emit(s: STRING) BEGIN CNV_TIME_STR({EPOCH},s) saved=s END emit')
        self.assertEqual((state['TEXT'],state['SAVED']),('original','01-JAN-1980 00:00:00'))


class TimeEffectTests(unittest.TestCase):
    def test_source_then_target_once(self):
        state=execute('total=0 CNV_STR_TIME(source,items[dest])',declarations=DECLARATIONS+' items: ARRAY[1] OF INTEGER',routines="ROUTINE source: STRING BEGIN total=total*10+1 RETURN '01-JAN-1980 00:00' END source\nROUTINE dest: INTEGER BEGIN total=total*10+2 RETURN 1 END dest")
        self.assertEqual((state['TOTAL'],state['ITEMS']),(12,[EPOCH]))
    def test_source_value_captured_before_target_effects(self):
        state=execute(f'encoded={EPOCH} CNV_TIME_STR(encoded,labels[dest])',declarations=DECLARATIONS+' labels: ARRAY[1] OF STRING[20]',routines=f'ROUTINE dest: INTEGER BEGIN encoded={LEAP} RETURN 1 END dest')
        self.assertEqual((state['ENCODED'],state['LABELS']),(LEAP,['01-JAN-1980 00:00:00']))
    def test_source_error_skips_target_effects(self):
        p,_=compile_program('total=0 CNV_TIME_STR(encoded,labels[dest])',declarations=DECLARATIONS+' labels: ARRAY[1] OF STRING[20]',routines='ROUTINE dest: INTEGER BEGIN total=9 RETURN 1 END dest')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TOTAL'],0)
    def test_conversion_error_retains_prior_target_effects(self):
        p,_=compile_program("total=0 labels[1]='prior' CNV_TIME_STR(0,labels[dest])",declarations=DECLARATIONS+' labels: ARRAY[1] OF STRING[20]',routines='ROUTINE dest: INTEGER BEGIN total=9 RETURN 1 END dest')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['TOTAL'],p.snapshot()['LABELS']),(9,['prior']))
    def test_parameter_write_report(self):
        _,result=compile_program('load(encoded)',routines="ROUTINE load(n: INTEGER) BEGIN CNV_STR_TIME('bad',n) END load")
        self.assertEqual(result.report['routine_effects']['LOAD']['potential_parameter_writes'],['N'])
    def test_failure_cleans_for_and_routine_frames(self):
        p,_=compile_program('FOR i=1 TO 2 DO emit() ENDFOR',routines='ROUTINE emit BEGIN CNV_TIME_STR(0,text) END emit')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['I'],{'uninitialized':True}); self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
    def test_label_dispatch(self): self.assertEqual(execute("CNV_STR_TIME('bad',encoded)",labelled=True)['ENCODED'],0)
    def test_source_location_and_policy(self):
        _,result=compile_program("CNV_STR_TIME('bad',encoded)\nCNV_TIME_STR(encoded,text)")
        report=json.loads(json.dumps(result.report)); rows=report['time_text_conversions']
        self.assertEqual([(r['name'],r['body'],r['line'],r['column'],r['output_type']) for r in rows],[('CNV_STR_TIME','T',6,1,'INTEGER'),('CNV_TIME_STR','T',7,1,'STRING')])
        self.assertTrue(all(r['arguments_evaluated_once'] and r['argument_order']==['source','target'] for r in rows))
        self.assertFalse(report['time_text_policy']['controller_validated'])


class TimeSourceGuardTests(unittest.TestCase):
    def reject(self,body,code,**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)
    def test_argument_count(self):
        for body in ("CNV_STR_TIME('bad')",'CNV_TIME_STR(0,text,encoded)'):
            with self.subTest(body=body): self.reject(body,'E_ARGUMENTS')
    def test_input_types(self):
        for body in ('CNV_STR_TIME(1,encoded)',"CNV_TIME_STR('bad',text)",'CNV_TIME_STR(1.5,text)'):
            with self.subTest(body=body): self.reject(body,'E_TYPE')
    def test_exact_output_types(self):
        for body in ("CNV_STR_TIME('bad',text)",'CNV_TIME_STR(0,encoded)',"CNV_STR_TIME('bad',n)"):
            with self.subTest(body=body): self.reject(body,'E_TYPE',declarations=DECLARATIONS+' n: SHORT')
    def test_group_and_constant_outputs(self):
        for output in ('(encoded)','1','constant'):
            with self.subTest(output=output): self.reject(f"CNV_STR_TIME('bad',{output})",'E_OUTPUT_ARGUMENT',prefix='CONST constant=1')
    def test_config_subfield_output(self): self.reject("CNV_STR_TIME('bad',cfg.cfg_turn_no1)",'E_CONFIG_OUTPUT',declarations=DECLARATIONS+' cfg: CONFIG')
    def test_position_protection(self): self.reject("CNV_STR_TIME('bad',pose.orient.x)",'E_POSITION_READ_ONLY',declarations=DECLARATIONS+' pose: POSITION')
    def test_direct_for_write(self): self.reject("FOR i=1 TO 2 DO CNV_STR_TIME('bad',i) ENDFOR",'E_FOR_COUNTER')
    def test_transitive_for_parameter_write(self): self.reject('FOR i=1 TO 2 DO load(i) ENDFOR','E_FOR_COUNTER',routines="ROUTINE load(n: INTEGER) BEGIN CNV_STR_TIME('bad',n) END load")
    def test_transitive_for_global_write(self): self.reject('FOR i=1 TO 2 DO load() ENDFOR','E_FOR_COUNTER',routines="ROUTINE load BEGIN CNV_STR_TIME('bad',i) END load")
    def test_procedure_results_rejected(self): self.reject("other=CNV_STR_TIME('bad',encoded)",'E_PROCEDURE_RESULT')
    def test_internal_user_procedures_keep_signatures(self):
        state=execute('CNV_STR_TIME(7) CNV_TIME_STR(8)',routines='ROUTINE CNV_STR_TIME(n: INTEGER) BEGIN total=n END CNV_STR_TIME\nROUTINE CNV_TIME_STR(n: INTEGER) BEGIN other=n END CNV_TIME_STR')
        self.assertEqual((state['TOTAL'],state['OTHER']),(7,8))
    def test_user_function_precedence(self):
        state=execute('other=CNV_TIME_STR(7)',routines='ROUTINE CNV_TIME_STR(n: INTEGER): INTEGER BEGIN RETURN n+1 END CNV_TIME_STR')
        self.assertEqual(state['OTHER'],8)
    def test_ordinary_variable_names(self): self.assertEqual(execute('CNV_TIME_STR=7',declarations='CNV_TIME_STR: INTEGER')['CNV_TIME_STR'],7)
    def test_legacy_rejects_builtins(self):
        for body in ("CNV_STR_TIME('bad',encoded)",'CNV_TIME_STR(0,text)'):
            with self.subTest(body=body): self.reject(body,'E_CALL',translator=legacy_translate)
    def test_legacy_clock_calls_remain_unsupported(self):
        for body in ('GET_TIME(encoded)','SET_TIME(encoded)'):
            with self.subTest(body=body): self.reject(body,'E_CALL',translator=legacy_translate)


class TimeRuntimeGuardTests(unittest.TestCase):
    def test_ascii_type_and_length_errors_preserve_target(self):
        for source in ('caf\u00e9',' '*255,rt.UNINITIALIZED,7):
            cells={'value':42}
            with self.subTest(source=source),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.time_text_conversion('CNV_STR_TIME',source,rt.Reference(('INTEGER',),cells,'value'),line=9)
            self.assertEqual(cells['value'],42)
    def test_special_or_missing_reference_rejected(self):
        cells={'value':42}
        for target in (None,rt.ReadOnlyFieldReference(('INTEGER',),cells,'value')):
            with self.subTest(target=target),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.time_text_conversion('CNV_STR_TIME','bad',target)
        self.assertEqual(cells['value'],42)
    def test_invalid_capacity_specs_preserve_target(self):
        for spec in (('STRING',None),('STRING',True),('STRING',19),('STRING',255),('INTEGER',)):
            cells={'text':'prior'}
            with self.subTest(spec=spec),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.time_text_conversion('CNV_TIME_STR',EPOCH,rt.Reference(spec,cells,'text'))
            self.assertEqual(cells['text'],'prior')
    def test_wrong_parse_output_spec(self):
        cells={'value':42}
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.time_text_conversion('CNV_STR_TIME','bad',rt.Reference(('SHORT',),cells,'value'))
        self.assertEqual(cells['value'],42)
    def test_source_integer_range_and_type(self):
        for source in (2**31,-2**31-1,True,1.0,rt.UNINITIALIZED):
            cells={'text':'prior'}
            with self.subTest(source=source),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.time_text_conversion('CNV_TIME_STR',source,rt.Reference(('STRING',20),cells,'text'))
            self.assertEqual(cells['text'],'prior')
    def test_errors_carry_source_line(self):
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line 9'): rt.time_text_conversion('CNV_TIME_STR',0,rt.Reference(('STRING',20),{'text':'prior'},'text'),line=9)
    def test_strict_runtime_guard(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.time_text_conversion('CNV_STR_TIME','bad',rt.Reference(('INTEGER',),{'value':42},'value'))


class AuthoredTimeTextTests(unittest.TestCase):
    def test_complete_fixture(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_time_text.kl'
        result=translate(source.read_text(),filename=source.name); namespace={'__name__':'time_text_fixture'}
        exec(result.python_source,namespace); output=[]; p=namespace['Program'](write=output.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(output,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(len(result.report['time_text_conversions']),5)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
