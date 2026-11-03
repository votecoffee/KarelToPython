"""Authored portable CONFIG word values, staged containers and exact boundaries."""
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_config_text import config

U={'uninitialized':True}
B={'unknown_byte':True}
CFG=('CONFIG',)
DECL='cfg,other:CONFIG word,n,e,s,visits:INTEGER b:BYTE small:SHORT flag:BOOLEAN'
DEFAULT=config()
MISSING={name:U for name in DEFAULT}
TYPES='TYPE packed_t=STRUCTURE value:INTEGER note:STRING[4] ENDSTRUCTURE expanded_t=STRUCTURE value:CONFIG note:STRING[4] ENDSTRUCTURE'


def build(body,*,decl=DECL,**options):return compile_program(body,decl=decl,**options)
def execute(body,**options):return build(body,**options)[0].run()


class ConfigWordRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.scope=rt._numeric_scope('pythonic');self.scope.__enter__();self.addCleanup(self.scope.__exit__,None,None,None)
    def encode(self,word):return rt.config_word_value(('INTEGER',),rt.config_word_value(CFG,word))
    def test_zero(self):self.assertEqual(rt.snapshot_value(rt.config_word_value(CFG,0)),DEFAULT)
    def test_all_bits(self):self.assertEqual(rt.snapshot_value(rt.config_word_value(CFG,65535)),config(CFG_TURN_NO1=-1,CFG_TURN_NO2=-1,CFG_TURN_NO3=-1,CFG_FLIP=True,CFG_LEFT=True,CFG_UP=True,CFG_FRONT=True))
    def test_signed_turn_boundaries(self):self.assertEqual(rt.snapshot_value(rt.config_word_value(CFG,0x789)),config(CFG_TURN_NO1=-7,CFG_TURN_NO2=-8,CFG_TURN_NO3=7))
    def test_first_flag(self):self.assertEqual(rt.snapshot_value(rt.config_word_value(CFG,0x1000)),config(CFG_FLIP=True))
    def test_second_flag(self):self.assertEqual(rt.snapshot_value(rt.config_word_value(CFG,0x2000)),config(CFG_LEFT=True))
    def test_third_flag(self):self.assertEqual(rt.snapshot_value(rt.config_word_value(CFG,0x4000)),config(CFG_UP=True))
    def test_fourth_flag(self):self.assertEqual(rt.snapshot_value(rt.config_word_value(CFG,0x8000)),config(CFG_FRONT=True))
    def test_complete_domain_round_trip(self):
        for word in range(65536):self.assertEqual(self.encode(word),word)
    def test_negative_word_rejected(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.config_word_value(CFG,-1)
    def test_oversized_word_rejected(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.config_word_value(CFG,65536)
    def test_boolean_word_rejected(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.config_word_value(CFG,True)
    def test_real_word_rejected(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.config_word_value(CFG,1.)
    def test_partial_scalar_config_rejected(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.config_word_value(('INTEGER',),rt.Structure(CFG))
    def test_malformed_known_turn_rejected(self):
        value=rt.config_word_value(CFG,0);value.values['CFG_TURN_NO1']=8
        with self.assertRaises(rt.KarelRuntimeError):rt.config_word_value(('INTEGER',),value)
    def test_nonboolean_flag_rejected(self):
        value=rt.config_word_value(CFG,0);value.values['CFG_FLIP']=1
        with self.assertRaises(rt.KarelRuntimeError):rt.config_word_value(('INTEGER',),value)
    def test_decode_is_independently_owned(self):
        a=rt.config_word_value(CFG,7);b=rt.config_word_value(CFG,7);a.values['CFG_TURN_NO1']=0;self.assertEqual(b.values['CFG_TURN_NO1'],7)
    def test_strict_runtime_rejected(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.config_word_value(CFG,0)
    def test_checked_does_not_gain_implicit_word_conversion(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.checked(CFG,0)
    def test_value_argument_remains_exact(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.value_argument(CFG,0)
    def test_data_codec_validates_declared_byte_source(self):
        with self.assertRaises(rt.KarelRuntimeError):rt._config_word_data(CFG,('BYTE',),300)
    def test_missing_config_to_byte_remains_missing_data(self):self.assertIs(rt._config_word_data(('BYTE',),CFG,rt.UNINITIALIZED),rt.UNINITIALIZED)
    def test_real_output_not_invented(self):
        with self.assertRaises(rt.KarelRuntimeError):rt.config_word_value(('REAL',),rt.config_word_value(CFG,0))


class ConfigWordSourceTests(unittest.TestCase):
    def test_scalar_decode(self):self.assertEqual(execute('cfg=0')['CFG'],DEFAULT)
    def test_scalar_encode(self):self.assertEqual(execute('cfg=22415 word=cfg')['WORD'],22415)
    def test_fields_follow_documented_word_order(self):self.assertEqual(execute('cfg=22415')['CFG'],config(CFG_TURN_NO1=-1,CFG_TURN_NO2=-8,CFG_TURN_NO3=7,CFG_FLIP=True,CFG_UP=True))
    def test_encode_existing_config_text(self):self.assertEqual(execute("CNV_STR_CONF('F L U T, -1, -1, -1',cfg,s) word=cfg")['WORD'],65535)
    def test_word_round_trip_through_text(self):self.assertEqual(execute('cfg=65535 CNV_CONF_STR(cfg,text)',decl=DECL+' text:STRING[40]')['TEXT'],'F L U T, -1, -1, -1')
    def test_config_field_in_pose(self):self.assertEqual(execute('p.config_data=4096 word=p.config_data',decl=DECL+' p:XYZWPR')['WORD'],4096)
    def test_byte_source(self):self.assertEqual(execute('b=127 cfg=b word=cfg')['WORD'],127)
    def test_short_source(self):self.assertEqual(execute('small=32766 cfg=small word=cfg')['WORD'],32766)
    def test_byte_output(self):self.assertEqual(execute('cfg=255 b=cfg')['B'],255)
    def test_short_output(self):self.assertEqual(execute('cfg=32766 small=cfg')['SMALL'],32766)
    def test_short_missing_sentinel_retained(self):self.assertEqual(execute('cfg=32767 small=cfg')['SMALL'],U)
    def test_byte_overflow_keeps_destination(self):
        p,_=build('b=7 cfg=65535 b=cfg')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],7)
    def test_invalid_word_keeps_config(self):
        p,_=build('cfg=7 word=65536 cfg=word')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CFG']['CFG_TURN_NO1'],7)
    def test_missing_word_fails_before_assignment(self):
        p,_=build('cfg=7 cfg=word')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CFG']['CFG_TURN_NO1'],7)
    def test_unknown_byte_cannot_invent_bits(self):
        p,_=build('cfg=b')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_private_config_argument(self):
        v=execute('word=7 work(word)',routines='ROUTINE work(x:CONFIG) BEGIN x.cfg_turn_no1=0 n=x END work');self.assertEqual((v['WORD'],v['N']),(7,0))
    def test_private_integer_argument(self):
        v=execute('cfg=7 work(cfg)',routines='ROUTINE work(x:INTEGER) BEGIN n=x x=0 END work');self.assertEqual((v['N'],v['CFG']['CFG_TURN_NO1']),(7,7))
    def test_config_result(self):self.assertEqual(execute('cfg=make()',routines='ROUTINE make:CONFIG BEGIN RETURN 4096 END make')['CFG'],config(CFG_FLIP=True))
    def test_integer_result(self):self.assertEqual(execute('cfg=4096 word=make()',routines='ROUTINE make:INTEGER BEGIN RETURN cfg END make')['WORD'],4096)
    def test_scalar_receiver_index_after_conversion(self):
        v=execute('n=0 a[pick()]=4096',decl=DECL+' a:ARRAY[1]OF CONFIG',routines='ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 1 END pick');self.assertEqual((v['N'],v['A'][0]),(1,config(CFG_FLIP=True)))
    def test_rhs_effect_once(self):
        v=execute('visits=0 cfg=make()',routines='ROUTINE make:INTEGER BEGIN visits=visits+1 RETURN 7 END make');self.assertEqual(v['VISITS'],1)
    def test_label_dispatch(self):self.assertEqual(execute('unused:: cfg=7 word=cfg')['WORD'],7)
    def test_for_counter_converted_argument_is_private(self):
        v=execute('n=0 FOR word=1 TO 2 DO work(word) ENDFOR',routines='ROUTINE work(x:CONFIG) BEGIN x.cfg_turn_no1=0 n=n+1 END work');self.assertEqual((v['N'],v['WORD']),(2,U))
    def test_global_counter_effect_remains_protected(self):
        with self.assertRaises(TranslationError):build('FOR word=1 TO 2 DO work(word) ENDFOR',routines='ROUTINE work(x:CONFIG) BEGIN word=0 END work')
    def test_capture_before_later_argument_effects(self):
        v=execute('cfg=7 work(cfg,later())',routines='ROUTINE later:INTEGER BEGIN cfg=0 RETURN 1 END later ROUTINE work(x,y:INTEGER) BEGIN n=x END work');self.assertEqual((v['N'],v['CFG']), (7,DEFAULT))
    def test_pause_preserves_private_value(self):
        p,_=build('word=7 work(word)',cooperative=True,routines='ROUTINE work(x:CONFIG) BEGIN PAUSE n=x END work')
        with self.assertRaises(rt.KarelPause):p.run()
        p._state.values['WORD']=9;self.assertEqual((p.resume()['N'],p.snapshot()['WORD']),(7,9))


class ConfigWordContainerTests(unittest.TestCase):
    DECL=DECL+' words:ARRAY[2]OF INTEGER configs:ARRAY[2]OF CONFIG'
    def test_array_decode_preserves_missing_shape(self):self.assertEqual(execute('words[1]=7 configs=words',decl=self.DECL)['CONFIGS'],[config(CFG_TURN_NO1=7),MISSING])
    def test_array_encode_preserves_missing_word(self):self.assertEqual(execute('configs[1]=7 words=configs',decl=self.DECL)['WORDS'],[7,U])
    def test_partially_initialized_config_becomes_missing_word(self):self.assertEqual(execute('configs[1].cfg_flip=TRUE words=configs',decl=self.DECL)['WORDS'],[U,U])
    def test_array_failure_is_atomic(self):
        p,_=build('configs[1]=7 words[1]=9 words[2]=65536 configs=words',decl=self.DECL)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CONFIGS'][0],config(CFG_TURN_NO1=7))
    def test_named_component_array_conversion(self):
        v=execute('a[1,2]=4096 b=a',prefix='TYPE row_t=ARRAY[2]OF CONFIG',decl='a:ARRAY[2,2]OF INTEGER b:ARRAY[2]OF row_t');self.assertEqual(v['B'][0][1],config(CFG_FLIP=True))
    def test_prefix_assignment_decode(self):
        v=execute('words[1]=7 m[2]=words',decl=self.DECL+' m:ARRAY[2,2]OF CONFIG');self.assertEqual(v['M'][1],[config(CFG_TURN_NO1=7),MISSING])
    def test_borrowed_live_prefix_conversion(self):
        v=execute("words[1]=7 work(BYNAME('','M[2]',e))",decl=self.DECL+' m:ARRAY[2,2]OF CONFIG',routines='ROUTINE work(x:ARRAY OF CONFIG) BEGIN x=words END work');self.assertEqual(v['M'][1],[config(CFG_TURN_NO1=7),MISSING])
    def test_private_array_argument(self):
        v=execute('words[1]=7 work(words)',decl=self.DECL,routines='ROUTINE work(x:ARRAY OF CONFIG) BEGIN n=x[1] x[1]=0 END work');self.assertEqual((v['N'],v['WORDS']), (7,[7,U]))
    def test_array_return(self):
        v=execute('words[1]=7 configs=make()',decl=self.DECL,routines='ROUTINE make:ARRAY[2]OF CONFIG BEGIN RETURN words END make');self.assertEqual(v['CONFIGS'],[config(CFG_TURN_NO1=7),MISSING])
    def test_record_decode(self):
        v=execute("a.value=4096 a.note='test' b=a",prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t');self.assertEqual(v['B'],dict(VALUE=config(CFG_FLIP=True),NOTE='test'))
    def test_record_encode(self):
        v=execute('b.value=4096 a=b',prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t');self.assertEqual(v['A'],dict(VALUE=4096,NOTE=U))
    def test_record_partial_word_becomes_shaped_config(self):
        v=execute('b=a',prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t');self.assertEqual(v['B']['VALUE'],MISSING)
    def test_record_partial_config_becomes_missing_word(self):
        v=execute('a=b',prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t');self.assertEqual(v['A']['VALUE'],U)
    def test_nested_record_array(self):
        v=execute('a[2].value=4096 b=a',prefix=TYPES,decl='a:ARRAY[2]OF packed_t b:ARRAY[2]OF expanded_t');self.assertEqual(v['B'][1]['VALUE'],config(CFG_FLIP=True))
    def test_record_argument(self):
        v=execute('a.value=7 work(a)',prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t',routines='ROUTINE work(x:expanded_t) BEGIN n=x.value x.value=0 END work');self.assertEqual((v['N'],v['A']['VALUE']),(7,7))
    def test_record_return(self):
        v=execute('a.value=7 b=make()',prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t',routines='ROUTINE make:expanded_t BEGIN RETURN a END make');self.assertEqual(v['B']['VALUE'],config(CFG_TURN_NO1=7))


class ConfigWordVariableTests(unittest.TestCase):
    def test_get_word_as_config(self):self.assertEqual(execute("word=4096 GET_VAR(e,'','WORD',cfg,s)")['CFG'],config(CFG_FLIP=True))
    def test_set_config_into_word(self):self.assertEqual(execute("cfg=4096 SET_VAR(e,'','WORD',cfg,s)")['WORD'],4096)
    def test_get_config_as_word(self):self.assertEqual(execute("cfg=4096 GET_VAR(e,'','CFG',word,s)")['WORD'],4096)
    def test_set_word_into_config(self):self.assertEqual(execute("SET_VAR(e,'','CFG',4096,s)")['CFG'],config(CFG_FLIP=True))
    def test_get_missing_word_as_shaped_config(self):
        v=execute("GET_VAR(e,'','WORD',cfg,s)");self.assertEqual((v['CFG'],v['S']), (MISSING,12311))
    def test_get_partial_config_as_missing_word(self):
        v=execute("cfg.cfg_flip=TRUE GET_VAR(e,'','CFG',word,s)");self.assertEqual((v['WORD'],v['S']), (U,12311))
    def test_get_arrays(self):
        v=execute("words[1]=7 GET_VAR(e,'','WORDS',configs,s)",decl=ConfigWordContainerTests.DECL);self.assertEqual((v['CONFIGS'],v['S']),([config(CFG_TURN_NO1=7),MISSING],12311))
    def test_set_arrays(self):
        v=execute("configs[1]=7 SET_VAR(e,'','WORDS',configs,s)",decl=ConfigWordContainerTests.DECL);self.assertEqual(v['WORDS'],[7,U])
    def test_get_prefix_into_prefix(self):
        v=execute("words[1,1]=7 GET_VAR(e,'','WORDS[1]',configs[2],s)",decl=ConfigWordContainerTests.DECL.replace('[2]','[2,2]'));self.assertEqual(v['CONFIGS'][1],[config(CFG_TURN_NO1=7),MISSING])
    def test_variable_record(self):
        v=execute("a.value=7 GET_VAR(e,'','A',b,s)",prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t');self.assertEqual(v['B']['VALUE'],config(CFG_TURN_NO1=7))
    def test_variable_bad_word_preserves_output_and_cache(self):
        p,_=build("cfg=7 word=65536 e=77 s=88 GET_VAR(e,'','WORD',cfg,s)")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CFG'],p.snapshot()['E'],p.snapshot()['S'],p._state.execution.entries),(config(CFG_TURN_NO1=7),77,88,{}))
    def test_whole_missing_config_to_byte_reports_missing_status(self):
        p,_=build("GET_VAR(e,'','CFG',b,s)");p._state.values['CFG']=rt.UNINITIALIZED;v=p.run();self.assertEqual((v['B'],v['S']),(U,12311))
    def test_dynamic_config_binding(self):
        v=execute("CREATE_VAR('CACHE','CFG','','CONFIG',0,0,0,0,s) SET_VAR(e,'CACHE','CFG',4096,s) GET_VAR(e,'CACHE','CFG',word,s)");self.assertEqual(v['WORD'],4096)


class ConfigWordBoundaryTests(unittest.TestCase):
    def reject(self,body,**options):
        with self.assertRaises(TranslationError):build(body,**options)
    def test_boolean_source_rejected(self):self.reject('cfg=TRUE')
    def test_real_source_rejected(self):self.reject('cfg=1.0')
    def test_real_destination_rejected(self):self.reject('x=cfg',decl=DECL+' x:REAL')
    def test_config_arithmetic_not_invented(self):self.reject('word=cfg+1')
    def test_config_integer_comparison_stays_explicit(self):self.reject('flag=cfg=0')
    def test_byname_stays_exact(self):
        p,_=build("word=7 work(BYNAME('','WORD',e))",routines='ROUTINE work(x:CONFIG) BEGIN END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.execution.entries,{})
    def test_legacy_assignment_not_enabled(self):
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR cfg:CONFIG n:INTEGER BEGIN cfg=0 n=cfg END T')
    def test_position_orientation_stays_protected(self):self.reject('p.normal=cfg',decl=DECL+' p:POSITION')
    def test_builtin_typed_input_stays_exact(self):self.reject('p=POS(0,0,0,0,0,0,0)',decl=DECL+' p:XYZWPR')
    def test_report_records_source_boundaries(self):
        _,r=build('cfg=0 word=cfg');policy=r.report['config_word_policy'];self.assertFalse(policy['controller_validated']);self.assertEqual([row['operation'] for row in policy['calls']],['ASSIGNMENT','ASSIGNMENT']);self.assertIn('16-bit',policy['encoding'])
    def test_json_retains_values_without_codec_state(self):
        p,_=build('cfg=4096 word=cfg');p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_linked_declared_signatures_remain_exact(self):
        with self.assertRaises(ValueError):translate_project({'lib':'PROGRAM LIB ROUTINE work(x:CONFIG) BEGIN END work BEGIN END LIB','main':'PROGRAM MAIN ROUTINE work(x:INTEGER) FROM LIB BEGIN END MAIN'}).instantiate()
    def test_linked_scalar_conversion(self):
        p=translate_project({'lib':'PROGRAM LIB VAR word:INTEGER ROUTINE work(x:CONFIG) BEGIN word=x x=0 END work BEGIN END LIB','main':"PROGRAM MAIN VAR word:INTEGER ROUTINE work(x:CONFIG) FROM LIB BEGIN word=7 work(word) END MAIN"}).instantiate();p.run('MAIN');self.assertEqual((p.programs['MAIN'].snapshot()['WORD'],p.programs['LIB'].snapshot()['WORD']),(7,7))
    def test_linked_array_conversion(self):
        p=translate_project({'lib':'PROGRAM LIB VAR word:INTEGER ROUTINE work(x:ARRAY OF CONFIG) BEGIN word=x[1] x[1]=0 END work BEGIN END LIB','main':'PROGRAM MAIN VAR words:ARRAY[2]OF INTEGER ROUTINE work(x:ARRAY OF CONFIG) FROM LIB BEGIN words[1]=7 work(words) END MAIN'}).instantiate();p.run('MAIN');self.assertEqual((p.programs['MAIN'].snapshot()['WORDS'],p.programs['LIB'].snapshot()['WORD']),([7,U],7))


class ConfigWordIntegrationTests(unittest.TestCase):
    def test_array_unknown_byte_rejects_before_publication(self):
        p,_=build('configs[1]=7 configs=bytes',decl=DECL+' bytes:ARRAY[2]OF BYTE configs:ARRAY[2]OF CONFIG')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CONFIGS'][0],config(CFG_TURN_NO1=7))
    def test_variable_array_failure_keeps_outputs_and_cache(self):
        p,_=build("configs[1]=7 words[1]=9 words[2]=65536 e=77 s=88 GET_VAR(e,'','WORDS',configs,s)",decl=ConfigWordContainerTests.DECL)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['CONFIGS'][0],p.snapshot()['E'],p.snapshot()['S'],p._state.execution.entries),(config(CFG_TURN_NO1=7),77,88,{}))
    def test_variable_array_unused_tail_retained(self):
        v=execute("words[1]=7 words[2]=9 configs[3]=4096 GET_VAR(e,'','WORDS',configs,s)",decl=DECL+' words:ARRAY[2]OF INTEGER configs:ARRAY[3]OF CONFIG');self.assertEqual((v['CONFIGS'][2],v['S']),(config(CFG_FLIP=True),0))
    def test_short_array_sentinel_conversion(self):
        v=execute('configs[1]=32767 smalls=configs',decl=ConfigWordContainerTests.DECL+' smalls:ARRAY[2]OF SHORT');self.assertEqual(v['SMALLS'],[U,U])
    def test_variable_short_sentinel_status(self):
        v=execute("cfg=32767 GET_VAR(e,'','CFG',small,s)");self.assertEqual((v['SMALL'],v['S']),(U,12311))
    def test_private_using_config_values(self):
        v=execute('cfg=4096 USING cfg DO n=cfg_turn_no1 cfg_flip=FALSE ENDUSING word=cfg');self.assertEqual((v['N'],v['WORD']),(0,0))
    def test_config_subfield_argument_remains_value_only(self):
        v=execute('a.value=7 b.value=9 work(b.value.cfg_turn_no1)',prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t',routines='ROUTINE work(alias:INTEGER) BEGIN b=a n=alias END work');self.assertEqual(v['N'],-7)
    def test_config_alias_survives_record_replacement(self):
        v=execute('a.value=7 b.value=9 work(b.value)',prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t',routines='ROUTINE work(alias:CONFIG) BEGIN b=a n=alias END work');self.assertEqual(v['N'],7)
    def test_binary_integer_transport_then_decode(self):
        import struct
        context=rt.ExecutionContext(files=rt.MemoryFiles({'input':struct.pack('<i',4096)}))
        v=execute("OPEN FILE f('RB','input') READ f(word) CLOSE FILE f cfg=word",decl=DECL+' f:FILE',context=context);self.assertEqual(v['CFG'],config(CFG_FLIP=True))
    def test_explicit_text_transport_then_decode(self):
        v=execute('READ(word) cfg=word',read=rt.TextInput('4096'));self.assertEqual(v['CFG'],config(CFG_FLIP=True))
    def test_same_config_argument_remains_alias(self):
        v=execute('cfg=7 work(cfg)',routines='ROUTINE work(x:CONFIG) BEGIN x.cfg_turn_no1=0 END work');self.assertEqual(v['CFG'],DEFAULT)
    def test_grouped_config_argument_stays_private(self):
        v=execute('cfg=7 work((cfg))',routines='ROUTINE work(x:CONFIG) BEGIN x.cfg_turn_no1=0 END work');self.assertEqual(v['CFG']['CFG_TURN_NO1'],7)
    def test_record_bad_known_config_is_not_hidden_by_missing_fields(self):
        p,_=build('a=b',prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t');p._state.raw('B').values['VALUE'].values['CFG_TURN_NO1']=9
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['A']['VALUE'],U)
    def test_linked_return_conversion(self):
        p=translate_project({'lib':'PROGRAM LIB ROUTINE make:CONFIG BEGIN RETURN 4096 END make BEGIN END LIB','main':'PROGRAM MAIN VAR cfg:CONFIG word:INTEGER ROUTINE make:CONFIG FROM LIB BEGIN cfg=make() word=cfg END MAIN'}).instantiate();p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['WORD'],4096)
    def test_saved_record_values_restore_independently(self):
        p,_=build('a.value=4096 b=a',prefix=TYPES,decl=DECL.replace(' b:BYTE','')+' a:packed_t b:expanded_t');p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));restored=rt.ExecutionContext.from_config(saved);self.assertEqual(restored.to_config(),saved)


if __name__=='__main__':unittest.main()
