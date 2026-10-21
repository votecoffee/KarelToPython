"""Portable CONFIG text grammar, status, complete formatting and checked effects."""
import itertools
import json
from pathlib import Path
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


DECLARATIONS='cfg,other: CONFIG text,encoded: STRING[40] status,i,total: INTEGER pose: XYZWPR'
DEFAULT=dict(CFG_TURN_NO1=0,CFG_TURN_NO2=0,CFG_TURN_NO3=0,CFG_FLIP=False,CFG_LEFT=False,CFG_UP=False,CFG_FRONT=False)
CANONICAL='N R D B, 0, 0, 0'


def config(**changes): return dict(DEFAULT,**changes)


def compile_program(body,*,declarations=DECLARATIONS,prefix='',routines='',translator=translate,labelled=False):
    source=f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n'
    result=translator(source+('label::\n' if labelled else '')+body+'\nEND T',filename='config_text.kl')
    ns={'__name__':'config_text_test'}; exec(result.python_source,ns)
    return ns['Program'](),result


def execute(body,**options): return compile_program(body,**options)[0].run()


def parse(text,**options): return execute("CNV_STR_CONF('"+text.replace("'","''")+"',cfg,status)",**options)


def runtime_targets():
    cells=dict(cfg=rt.Structure(('CONFIG',)),status=99,text='prior')
    return cells,rt.Reference(('CONFIG',),cells,'cfg'),rt.Reference(('INTEGER',),cells,'status'),rt.Reference(('STRING',40),cells,'text')


class ConfigParseTests(unittest.TestCase):
    def test_single_flag_has_explicit_portable_omitted_values(self): self.assertEqual(parse('N')['CFG'],DEFAULT)
    def test_normal_robot_style_flags(self): self.assertEqual(parse('N U T')['CFG'],config(CFG_UP=True,CFG_FRONT=True))
    def test_all_flags_and_turns(self):
        state=parse('F L U T, -8, 0, 7')
        self.assertEqual(state['CFG'],config(CFG_FLIP=True,CFG_LEFT=True,CFG_UP=True,CFG_FRONT=True,CFG_TURN_NO1=-8,CFG_TURN_NO3=7))
        self.assertEqual(state['STATUS'],0)
    def test_flags_any_order_case_and_whitespace(self): self.assertEqual(parse(' t\tU l f , +1, -2, 3 ')['CFG'],config(CFG_FLIP=True,CFG_LEFT=True,CFG_UP=True,CFG_FRONT=True,CFG_TURN_NO1=1,CFG_TURN_NO2=-2,CFG_TURN_NO3=3))
    def test_compact_flags(self): self.assertEqual(parse('FLUT')['CFG'],config(CFG_FLIP=True,CFG_LEFT=True,CFG_UP=True,CFG_FRONT=True))
    def test_all_flag_combinations(self):
        for bits in itertools.product((False,True),repeat=4):
            text=''.join(on if enabled else off for enabled,(_,off,on) in zip(bits,rt.CONFIG_TEXT_FLAGS))
            with self.subTest(bits=bits): self.assertEqual(parse(text)['CFG'],config(**dict(zip(('CFG_FLIP','CFG_LEFT','CFG_UP','CFG_FRONT'),bits))))
    def test_python_decimal_turn_grammar(self): self.assertEqual(parse('N, +0_1, -0_2, 03')['CFG'],config(CFG_TURN_NO1=1,CFG_TURN_NO2=-2,CFG_TURN_NO3=3))
    def test_unknown_letters_and_empty_text(self):
        for text in ('','   ','XYZ','N!','N U T A'):
            with self.subTest(text=text): self.assertEqual(parse(text)['STATUS'],1)
    def test_duplicate_or_conflicting_flags(self):
        for text in ('NN','NF','RL','UD','BT','N U U'):
            with self.subTest(text=text): self.assertEqual(parse(text)['STATUS'],1)
    def test_incomplete_or_invalid_turns(self):
        for text in ('N,1','N,1,2','N,1,2,3,4','N,1,,3','N,1.0,2,3','N,0x1,2,3',',0,0,0','N,8,0,0','N,0,-9,0'):
            with self.subTest(text=text): self.assertEqual(parse(text)['STATUS'],1)
    def test_bad_text_preserves_existing_configuration(self):
        state=execute("CNV_STR_CONF('F L U T,1,2,3',cfg,status) CNV_STR_CONF('bad',cfg,status)")
        self.assertEqual((state['CFG'],state['STATUS']),(config(CFG_FLIP=True,CFG_LEFT=True,CFG_UP=True,CFG_FRONT=True,CFG_TURN_NO1=1,CFG_TURN_NO2=2,CFG_TURN_NO3=3),1))
    def test_bad_text_preserves_uninitialized_config_leaves(self):
        self.assertTrue(all(value=={'uninitialized':True} for value in parse('bad')['CFG'].values()))
    def test_status_drives_control_flow(self): self.assertEqual(execute("CNV_STR_CONF('bad',cfg,status) IF status<>0 THEN total=9 ELSE total=0 ENDIF")['TOTAL'],9)
    def test_partial_config_is_overwritten_on_success(self): self.assertEqual(execute("cfg.cfg_flip=ON CNV_STR_CONF('N',cfg,status)")['CFG'],DEFAULT)
    def test_position_config_destination(self): self.assertEqual(execute("CNV_STR_CONF('F',pose.config_data,status)")['POSE']['CONFIG_DATA'],config(CFG_FLIP=True))
    def test_complete_pos_expression(self): self.assertEqual(execute("CNV_STR_CONF('N U T',cfg,status) pose=POS(.1,2,3,4,5,6,cfg)")['POSE']['CONFIG_DATA'],config(CFG_UP=True,CFG_FRONT=True))
    def test_array_and_status_element(self):
        state=execute("CNV_STR_CONF('F',items[1],codes[1])",declarations=DECLARATIONS+' items: ARRAY[1] OF CONFIG codes: ARRAY[1] OF INTEGER')
        self.assertEqual((state['ITEMS'],state['CODES']),([config(CFG_FLIP=True)],[0]))
    def test_alias_and_using(self):
        state=execute("USING box DO CNV_STR_CONF('F',value,code) ENDUSING",prefix='TYPE c_t=CONFIG packet=STRUCTURE value: c_t code: INTEGER ENDSTRUCTURE',declarations='box: packet')
        self.assertEqual(state['BOX'],dict(VALUE=config(CFG_FLIP=True),CODE=0))


class ConfigFormatTests(unittest.TestCase):
    def test_canonical_complete_format(self): self.assertEqual(execute("CNV_STR_CONF('N',cfg,status) CNV_CONF_STR(cfg,text)")['TEXT'],CANONICAL)
    def test_canonical_order_and_signed_turns(self): self.assertEqual(execute("CNV_STR_CONF('tulf,-8,7,-1',cfg,status) CNV_CONF_STR(cfg,text)")['TEXT'],'F L U T, -8, 7, -1')
    def test_parse_format_parse_roundtrip(self):
        state=execute("CNV_STR_CONF('F L U T,-8,7,-1',cfg,status) CNV_CONF_STR(cfg,text) CNV_STR_CONF(text,other,status)")
        self.assertEqual(state['CFG'],state['OTHER']); self.assertEqual(state['STATUS'],0)
    def test_exact_capacity(self):
        self.assertEqual(execute("CNV_STR_CONF('N',cfg,status) CNV_CONF_STR(cfg,text)",declarations='cfg: CONFIG status: INTEGER text: STRING[16]')['TEXT'],CANONICAL)
    def test_insufficient_capacity_preserves_output(self):
        p,_=compile_program("CNV_STR_CONF('N',cfg,status) text='prior' CNV_CONF_STR(cfg,text)",declarations='cfg: CONFIG status: INTEGER text: STRING[15]')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'): p.run()
        self.assertEqual(p.snapshot()['TEXT'],'prior')
    def test_uninitialized_config_rejected(self):
        p,_=compile_program("text='prior' CNV_CONF_STR(cfg,text)")
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TEXT'],'prior')
    def test_config_function_expression(self):
        state=execute("CNV_STR_CONF('F',cfg,status) CNV_CONF_STR(value,text)",routines='ROUTINE value: CONFIG BEGIN RETURN cfg END value')
        self.assertEqual(state['TEXT'],'F R D B, 0, 0, 0')
    def test_pos_config_expression(self): self.assertEqual(execute("CNV_STR_CONF('N',cfg,status) CNV_CONF_STR(POS(1,2,3,4,5,6,cfg).config_data,text)")['TEXT'],CANONICAL)
    def test_unspecified_string_formal_keeps_caller_capacity(self):
        state=execute("CNV_STR_CONF('N',cfg,status) emit(text)",routines='ROUTINE emit(s: STRING) BEGIN CNV_CONF_STR(cfg,s) END emit')
        self.assertEqual(state['TEXT'],CANONICAL)
    def test_value_string_formal_has_writable_private_capacity(self):
        state=execute("CNV_STR_CONF('N',cfg,status) text='original' emit((text))",routines='ROUTINE emit(s: STRING) BEGIN CNV_CONF_STR(cfg,s) encoded=s END emit')
        self.assertEqual((state['TEXT'],state['ENCODED']),('original',CANONICAL))


class ConfigEffectTests(unittest.TestCase):
    def test_parse_arguments_in_source_order_once(self):
        routines='''ROUTINE source: STRING BEGIN total=total*10+1 RETURN 'N' END source
ROUTINE dest: INTEGER BEGIN total=total*10+2 RETURN 1 END dest
ROUTINE code: INTEGER BEGIN total=total*10+3 RETURN 1 END code'''
        state=execute('total=0 CNV_STR_CONF(source,items[dest],codes[code])',routines=routines,declarations=DECLARATIONS+' items: ARRAY[1] OF CONFIG codes: ARRAY[1] OF INTEGER')
        self.assertEqual((state['TOTAL'],state['CODES']),(123,[0]))
    def test_format_source_copy_precedes_target_effects(self):
        state=execute("CNV_STR_CONF('N',cfg,status) CNV_CONF_STR(cfg,labels[dest])",declarations=DECLARATIONS+' labels: ARRAY[1] OF STRING[40]',
                      routines='ROUTINE dest: INTEGER BEGIN cfg.cfg_flip=ON RETURN 1 END dest')
        self.assertTrue(state['CFG']['CFG_FLIP']); self.assertEqual(state['LABELS'],[CANONICAL])
    def test_uninitialized_source_fails_before_target_expression(self):
        p,_=compile_program('total=0 CNV_CONF_STR(cfg,labels[dest])',declarations=DECLARATIONS+' labels: ARRAY[1] OF STRING[40]',
                            routines='ROUTINE dest: INTEGER BEGIN total=9 RETURN 1 END dest')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TOTAL'],0)
    def test_config_replacement_preserves_captured_field(self):
        state=execute("CNV_STR_CONF('N',cfg,status) load(cfg,cfg.cfg_flip)",routines="ROUTINE load(c: CONFIG; old: BOOLEAN) BEGIN CNV_STR_CONF('F',c,status) IF old THEN total=1 ELSE total=2 ENDIF END load")
        # CONFIG scalar actuals remain values, so old is the earlier OFF.
        self.assertEqual(state['TOTAL'],2); self.assertTrue(state['CFG']['CFG_FLIP'])
    def test_formatted_config_value_is_independent(self):
        state=execute("CNV_STR_CONF('N',cfg,status) load((cfg))",routines="ROUTINE load(c: CONFIG) BEGIN CNV_STR_CONF('F',c,status) other=c END load")
        self.assertFalse(state['CFG']['CFG_FLIP']); self.assertTrue(state['OTHER']['CFG_FLIP'])
    def test_both_outputs_mark_formals_writable(self):
        _,result=compile_program("load(cfg,status)",routines="ROUTINE load(c: CONFIG; code: INTEGER) BEGIN CNV_STR_CONF('N',c,code) END load")
        self.assertEqual(result.report['routine_effects']['LOAD']['potential_parameter_writes'],['C','CODE'])
    def test_transitive_status_write_protects_for_counter(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR i=1 TO 2 DO load(cfg,i) ENDFOR',routines="ROUTINE load(c: CONFIG; code: INTEGER) BEGIN CNV_STR_CONF('N',c,code) END load")
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_direct_status_write_protects_for_counter(self):
        with self.assertRaises(TranslationError) as caught: compile_program("FOR i=1 TO 2 DO CNV_STR_CONF('N',cfg,i) ENDFOR")
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_for_body_with_disjoint_status(self): self.assertEqual(execute("FOR i=1 TO 2 DO CNV_STR_CONF('N',cfg,status) ENDFOR")['STATUS'],0)
    def test_failure_unwinds_for_and_frames(self):
        p,_=compile_program('FOR i=1 TO 2 DO emit() ENDFOR',routines='ROUTINE emit BEGIN CNV_CONF_STR(cfg,text) END emit')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['I'],{'uninitialized':True}); self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
    def test_label_dispatcher(self): self.assertEqual(parse('N',labelled=True)['STATUS'],0)
    def test_observations_and_policy(self):
        _,result=compile_program("CNV_STR_CONF('N',cfg,status) CNV_CONF_STR(cfg,text)")
        report=json.loads(json.dumps(result.report))
        self.assertEqual([row['outputs'] for row in report['config_text_conversions']],[2,1])
        self.assertEqual(report['config_text_conversions'][0]['argument_order'],['source','target','status'])
        self.assertTrue(report['config_text_conversions'][1]['source_copied']); self.assertFalse(report['config_text_policy']['controller_validated'])


class ConfigSourceGuardTests(unittest.TestCase):
    def reject(self,body,code,**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)
    def test_arity(self):
        for body in ("CNV_STR_CONF('N',cfg)",'CNV_CONF_STR(cfg,text,status)'):
            with self.subTest(body=body): self.reject(body,'E_ARGUMENTS')
    def test_source_type(self): self.reject('CNV_CONF_STR(text,encoded)','E_TYPE')
    def test_config_destination_type(self): self.reject("CNV_STR_CONF('N',text,status)",'E_TYPE')
    def test_status_exact_integer_type(self): self.reject("CNV_STR_CONF('N',cfg,pose.x)",'E_TYPE')
    def test_grouped_or_computed_outputs(self):
        for output in ('(cfg)',"POS(1,2,3,4,5,6,cfg).config_data"):
            with self.subTest(output=output): self.reject(f"CNV_STR_CONF('N',{output},status)",'E_OUTPUT_ARGUMENT')
    def test_config_subfield_status_stays_blocked(self): self.reject("CNV_STR_CONF('N',cfg,cfg.cfg_turn_no1)",'E_CONFIG_OUTPUT')
    def test_procedure_result_is_blocked(self): self.reject("status=CNV_STR_CONF('N',cfg,status)",'E_PROCEDURE_RESULT')
    def test_internal_names_keep_user_procedure_precedence(self):
        state=execute('CNV_STR_CONF(7) CNV_CONF_STR(8)',routines='ROUTINE CNV_STR_CONF(n: INTEGER) BEGIN total=n END CNV_STR_CONF\nROUTINE CNV_CONF_STR(n: INTEGER) BEGIN status=n END CNV_CONF_STR')
        self.assertEqual((state['TOTAL'],state['STATUS']),(7,8))
    def test_user_function_is_preserved(self):
        state=execute('total=CNV_STR_CONF(7)',routines='ROUTINE CNV_STR_CONF(n: INTEGER): INTEGER BEGIN RETURN n+1 END CNV_STR_CONF')
        self.assertEqual(state['TOTAL'],8)
    def test_legacy_rejections(self):
        for body in ("CNV_STR_CONF('N',cfg,status)",'CNV_CONF_STR(cfg,text)'):
            with self.subTest(body=body): self.reject(body,'E_CALL',translator=legacy_translate)
    def test_masked_conversion_stays_unsupported(self): self.reject('CNV_CNF_STRG(cfg,text,status)','E_CALL')


class ConfigRuntimeGuardTests(unittest.TestCase):
    def test_readonly_or_nonreference_outputs(self):
        cells,c,s,t=runtime_targets()
        for target in (None,rt.ReadOnlyFieldReference(('CONFIG',),cells,'cfg')):
            with self.subTest(target=target),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.config_text_conversion('CNV_STR_CONF','N',target,s)
        self.assertEqual(cells['status'],99)
    def test_output_alias_rejected_before_mutation(self):
        cells,c,_,_=runtime_targets(); s=rt.Reference(('INTEGER',),cells['cfg'].values,'CFG_TURN_NO1')
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): rt.config_text_conversion('CNV_STR_CONF','N',c,s)
        self.assertIs(s.raw(),rt.UNINITIALIZED)
    def test_malformed_config_output_shape(self):
        cells,c,s,_=runtime_targets(); del cells['cfg'].values['CFG_FLIP']
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'malformed'): rt.config_text_conversion('CNV_STR_CONF','N',c,s)
        self.assertEqual(cells['status'],99)
    def test_nonascii_or_oversize_input_preserves_outputs(self):
        for text in ('caf\u00e9','N'*255,rt.UNINITIALIZED,7):
            cells,c,s,_=runtime_targets()
            with self.subTest(text=text),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.config_text_conversion('CNV_STR_CONF',text,c,s)
            self.assertEqual(cells['status'],99); self.assertIs(cells['cfg'].values['CFG_FLIP'],rt.UNINITIALIZED)
    def test_bad_format_config_does_not_modify_output(self):
        cells,c,_,t=runtime_targets()
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.config_text_conversion('CNV_CONF_STR',c.raw(),t)
        self.assertEqual(cells['text'],'prior')
    def test_format_rejects_out_of_range_config(self):
        cells,c,s,t=runtime_targets()
        with rt._numeric_scope('pythonic'):
            rt.config_text_conversion('CNV_STR_CONF','N',c,s); c.raw().values['CFG_TURN_NO1']=8
            with self.assertRaises(rt.KarelRuntimeError): rt.config_text_conversion('CNV_CONF_STR',c.raw(),t)
        self.assertEqual(cells['text'],'prior')
    def test_concrete_capacity_required(self):
        cells,c,s,_=runtime_targets()
        with rt._numeric_scope('pythonic'):
            rt.config_text_conversion('CNV_STR_CONF','N',c,s)
            with self.assertRaises(rt.KarelRuntimeError): rt.config_text_conversion('CNV_CONF_STR',c.raw(),rt.Reference(('STRING',None),cells,'text'))
        self.assertEqual(cells['text'],'prior')
    def test_strict_runtime_rejects_conversion(self):
        _,c,s,_=runtime_targets()
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.config_text_conversion('CNV_STR_CONF','N',c,s)


class AuthoredConfigTextTests(unittest.TestCase):
    def test_complete_fixture(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_config_text.kl'
        result=translate(source.read_text(),filename=source.name); ns={'__name__':'config_text_fixture'}
        exec(result.python_source,ns); output=[]; p=ns['Program'](write=output.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(output,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(len(result.report['config_text_conversions']),3)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
