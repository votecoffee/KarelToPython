"""Authored per-group CONFIG profiles, capture order, guards and CLI use."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program, run

ROOT = Path(__file__).resolve().parents[1]
DECL = 'cfg: CONFIG text: STRING[40] s,total,i: INTEGER'
INIT = "CNV_STR_CONF('F L U T,-1,2,3',cfg,s) "
CALL = 'CNV_CNF_STRG(cfg,text,s)'
PROFILES = {1: dict(flags=['flip','left','up','front'], turns=[1,2,3]),
            2: dict(flags=['flip','up','front'], turns=[1,3])}


def context(groups=None):
    return rt.ExecutionContext(config_text=rt.ConfigTextFormats(PROFILES if groups is None else groups))


class ConfigProfileTests(unittest.TestCase):
    def config(self):
        p,_=compile_program(INIT,decl=DECL)
        p.run()
        return p._state.values['CFG']

    def test_profile_selection_has_canonical_order(self):
        formats=rt.ConfigTextFormats({2: dict(flags=['front','flip','up'],turns=[3,1])})
        self.assertEqual(formats.render(self.config(),2),(0,'F U T, -1, 3'))

    def test_constructor_rejects_invalid_profiles(self):
        bad=[[],{True:PROFILES[1]},{0:PROFILES[1]},{32768:PROFILES[1]},
             {1:{}},{1:dict(flags=['flip'],turns=[],extra=1)},
             {1:dict(flags='flip',turns=[])},{1:dict(flags=['unknown'],turns=[])},
             {1:dict(flags=['flip','flip'],turns=[])},{1:dict(flags=[[]],turns=[])},
             {1:dict(flags=[],turns=[True])},{1:dict(flags=[],turns=[1,1])},
             {1:dict(flags=[],turns=[0])},{1:dict(flags=[],turns='1')}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError): rt.ConfigTextFormats(value)

    def test_json_requires_canonical_group_keys_and_explicit_lists(self):
        for key in ('01','+1','0',' 1','1.0','١',1):
            with self.subTest(key=key), self.assertRaises(ValueError): rt.ConfigTextFormats.from_config({key:PROFILES[1]})
        with self.assertRaises(ValueError): rt.ConfigTextFormats.from_config({'1':dict(flags=('flip',),turns=[])})

    def test_constructor_and_json_snapshots_do_not_share_mutable_lists(self):
        groups={1:dict(flags=['flip'],turns=[1])}
        formats=rt.ConfigTextFormats(groups)
        groups[1]['flags'].append('left')
        saved=formats.to_config()
        saved['1']['turns'].append(2)
        self.assertEqual(formats.render(self.config(),1),(0,'F, -1'))

    def test_empty_profile_is_explicit_and_missing_group_has_status(self):
        formats=rt.ConfigTextFormats({1:dict(flags=[],turns=[])})
        self.assertEqual(formats.render(self.config(),1),(0,''))
        self.assertEqual(formats.render(self.config(),2),(rt.CONFIG_TEXT_GROUP_MISSING,None))

    def test_host_render_rejects_invalid_source_and_boolean_group(self):
        formats=context().config_text
        with self.assertRaises(rt.KarelRuntimeError): formats.render(rt.Structure(('CONFIG',)),1)
        with self.assertRaises(rt.KarelRuntimeError): formats.render(self.config(),True)

    def test_execution_context_persistence_roundtrips_profiles(self):
        ctx=context()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'context.json'
            ctx.save(path)
            restored=rt.ExecutionContext.load(path)
        self.assertEqual(restored.config_text.to_config(),ctx.config_text.to_config())
        self.assertEqual(restored.config_text.render(self.config(),2),(0,'F U T, -1, 3'))
        self.assertEqual(rt.ExecutionContext.from_config({}).to_config(),{})

    def test_context_rejects_untyped_profile_service(self):
        with self.assertRaises(TypeError): rt.ExecutionContext(config_text=PROFILES)


class GroupConfigConversionTests(unittest.TestCase):
    def test_default_and_explicit_groups(self):
        self.assertEqual(run(INIT+CALL,decl=DECL,context=context())['TEXT'],'F L U T, -1, 2, 3')
        state=run(INIT+'CNV_CNF_STRG(cfg,text,s,2)',decl=DECL,context=context())
        self.assertEqual((state['TEXT'],state['S']),('F U T, -1, 3',0))

    def test_omitted_group_uses_calling_root_group(self):
        p,_=compile_program(INIT+CALL,decl=DECL,context=context())
        p._state.robot_group=2
        self.assertEqual(p.run()['TEXT'],'F U T, -1, 3')

    def test_linked_routine_uses_callers_group(self):
        sources={
            'main.kl': '''PROGRAM MAIN
VAR cfg:CONFIG text:STRING[40] s:INTEGER marker:JOINTPOS1 IN GROUP[2]
ROUTINE emit(c:CONFIG;t:STRING;code:INTEGER) FROM LIB
BEGIN CNV_STR_CONF('F L U T,-1,2,3',cfg,s) emit(cfg,text,s) END MAIN''',
            'lib.kl': '''PROGRAM LIB
ROUTINE emit(c:CONFIG;t:STRING;code:INTEGER)
BEGIN CNV_CNF_STRG(c,t,code) END emit
BEGIN END LIB'''}
        project=translate_project(sources).instantiate(context=context())
        project.run('MAIN')
        self.assertEqual(project.programs['MAIN'].snapshot()['TEXT'],'F U T, -1, 3')

    def test_unconfigured_group_preserves_text_and_sets_portable_status(self):
        for group in (0,-1,3,32768):
            with self.subTest(group=group):
                state=run(INIT+f"text='prior' CNV_CNF_STRG(cfg,text,s,{group})",decl=DECL,context=context())
                self.assertEqual((state['TEXT'],state['S']),('prior',1))

    def test_default_group_does_not_infer_the_only_configured_profile(self):
        state=run(INIT+"text='prior' "+CALL,decl=DECL,context=context({2:PROFILES[2]}))
        self.assertEqual((state['TEXT'],state['S']),('prior',1))

    def test_capacity_failure_preserves_text_status_and_source(self):
        p,_=compile_program(INIT+"text='old' s=7 "+CALL,decl=DECL.replace('STRING[40]','STRING[4]'),context=context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'): p.run()
        state=p.snapshot()
        self.assertEqual((state['TEXT'],state['S'],state['CFG']['CFG_FLIP']),('old',7,True))

    def test_exact_capacity_and_selected_turns_only(self):
        state=run(INIT+CALL,decl=DECL.replace('STRING[40]','STRING[1]'),
                  context=context({1:dict(flags=[],turns=[2])}))
        self.assertEqual((state['TEXT'],state['S']),('2',0))

    def test_uninitialized_source_skips_output_selectors(self):
        decl=DECL+' labels: ARRAY[1] OF STRING[40]'
        routines='ROUTINE slot: INTEGER BEGIN total=9 RETURN 1 END slot'
        p,_=compile_program('total=0 s=7 CNV_CNF_STRG(cfg,labels[slot],s)',decl=decl,routines=routines,context=context())
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['TOTAL'],p.snapshot()['S']),(0,7))

    def test_arguments_run_once_in_order_and_source_is_captured(self):
        routines="""ROUTINE source: CONFIG BEGIN total=total*10+1 RETURN cfg END source
ROUTINE target: INTEGER BEGIN total=total*10+2 cfg.cfg_flip=OFF RETURN 1 END target
ROUTINE code: INTEGER BEGIN total=total*10+3 RETURN 1 END code
ROUTINE group: INTEGER BEGIN total=total*10+4 RETURN 2 END group"""
        state=run(INIT+'total=0 CNV_CNF_STRG(source,labels[target],codes[code],group)',
                  decl=DECL+' labels: ARRAY[1] OF STRING[40] codes: ARRAY[1] OF INTEGER',routines=routines,context=context())
        self.assertEqual((state['TOTAL'],state['LABELS'],state['CODES']),(1234,['F U T, -1, 3'],[0]))
        self.assertFalse(state['CFG']['CFG_FLIP'])

    def test_group_function_failure_preserves_outputs_and_prior_effects(self):
        routines='ROUTINE group: INTEGER BEGIN total=9 RETURN 1 DIV 0 END group'
        p,_=compile_program(INIT+"total=0 text='prior' s=7 CNV_CNF_STRG(cfg,text,s,group)",
                            decl=DECL,routines=routines,context=context())
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['TEXT'],p.snapshot()['S'],p.snapshot()['TOTAL']),('prior',7,9))

    def test_user_function_precedence_is_preserved(self):
        routines='ROUTINE CNV_CNF_STRG(n: INTEGER): INTEGER BEGIN RETURN n+1 END CNV_CNF_STRG'
        state=run('total=CNV_CNF_STRG(7)',decl=DECL,routines=routines)
        self.assertEqual(state['TOTAL'],8)

    def test_direct_and_transitive_for_counter_outputs_are_rejected(self):
        cases=[('FOR i=1 TO 2 DO CNV_CNF_STRG(cfg,text,i) ENDFOR',''),
               ('FOR i=1 TO 2 DO emit(i) ENDFOR','ROUTINE emit(code: INTEGER) BEGIN CNV_CNF_STRG(cfg,text,code) END emit')]
        for body,routines in cases:
            with self.subTest(body=body), self.assertRaises(TranslationError) as caught:
                compile_program(body,decl=DECL,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_typed_outputs_config_fields_and_arity_stay_guarded(self):
        for call in ('CNV_CNF_STRG(cfg,text)', 'CNV_CNF_STRG(cfg,text,s,1,2)',
                     'CNV_CNF_STRG(cfg,text,2)', 'CNV_CNF_STRG(text,text,s)',
                     'CNV_CNF_STRG(cfg,(text),s)', 'CNV_CNF_STRG(cfg,text,cfg.cfg_turn_no1)',
                     'CNV_CNF_STRG(cfg,text,s,ON)', 'CNV_CNF_STRG(cfg,text,narrow[1])'):
            with self.subTest(call=call), self.assertRaises(TranslationError):
                compile_program(call,decl=DECL+' narrow: ARRAY[1] OF SHORT')

    def test_value_string_parameter_uses_private_storage(self):
        routines='ROUTINE emit(t: STRING) BEGIN CNV_CNF_STRG(cfg,t,s,2) saved=t END emit'
        state=run(INIT+"text='original' emit((text))",decl=DECL+' saved: STRING[40]',routines=routines,context=context())
        self.assertEqual((state['TEXT'],state['SAVED']),('original','F U T, -1, 3'))

    def test_label_dispatcher_preserves_for_cleanup(self):
        p,_=compile_program(INIT+'here:: FOR i=1 TO 2 DO '+CALL+' ENDFOR',decl=DECL,context=context())
        self.assertEqual(p.run()['TEXT'],'F L U T, -1, 2, 3')
        self.assertEqual(p.snapshot()['I'],{'uninitialized':True})
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))

    def test_runtime_failure_unwinds_routine_frames_and_clears_counter(self):
        p,_=compile_program(INIT+'s=7 FOR i=1 TO 2 DO emit ENDFOR',
                            decl=DECL.replace('STRING[40]','STRING[1]'),
                            routines='ROUTINE emit BEGIN '+CALL+' END emit',context=context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'): p.run()
        self.assertEqual(p.snapshot()['I'],{'uninitialized':True})
        self.assertEqual(p.snapshot()['S'],7)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))

    def test_reports_and_runtime_observations_keep_values_out(self):
        p,result=compile_program(INIT+CALL,decl=DECL,context=context())
        p.run()
        report=json.loads(json.dumps(result.report))
        self.assertEqual(report['service_operations'][0]['operation'],'CNV_CNF_STRG')
        self.assertFalse(report['group_config_text_policy']['controller_validated'])
        self.assertEqual(p.service_requests,(dict(operation='CNV_CNF_STRG',line=6,outcome='completed'),))

    def test_legacy_mode_keeps_unsupported_call_boundary(self):
        with self.assertRaises(TranslationError) as caught:
            legacy_translate('PROGRAM T VAR cfg:CONFIG text:STRING[40] s:INTEGER BEGIN '+CALL+' END T')
        self.assertEqual(caught.exception.code,'E_CALL')

    def test_cli_translation_and_generated_execution_use_persisted_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source,output,settings,state=(root/name for name in ('source.kl','out.py','context.json','state.json'))
            source.write_text('PROGRAM T VAR '+DECL+' BEGIN '+INIT+'CNV_CNF_STRG(cfg,text,s,2) END T')
            context().save(settings)
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(source),'-o',str(output)],
                                  cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            execution=subprocess.run([sys.executable,'-X','utf8',str(output),'--context',str(settings),'--state-out',str(state)],
                                     cwd=root,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True)
            self.assertEqual(execution.returncode,0,execution.stderr)
            self.assertEqual(ast.literal_eval(execution.stdout)['TEXT'],'F U T, -1, 3')
            self.assertEqual(json.loads(state.read_text())['config_text'],context().config_text.to_config())


if __name__ == '__main__': unittest.main()
