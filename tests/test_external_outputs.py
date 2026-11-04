"""Authored explicit response outputs, staged data and source argument lifetimes."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_external_values import row,integer,U,B,CFG,POINT,ITEM,reference


def output(argument,value):return dict(argument=argument,value=value)
def reply(*outputs,result=None):return dict(result=result,outputs=list(outputs))
def cases(arguments,response):return {'cases':[dict(arguments=arguments,**response)]}
def callbacks(binding):return rt.external_value_callbacks({'HOST':{'WORK':binding}})
def build(binding,*,params='value:INTEGER',kind=None,body='work(n)',decl='n,s:INTEGER',prefix='',routines='',direct=False,**options):
    ctx=options.pop('context',rt.ExecutionContext());ctx.externals.update({('HOST','WORK'):lambda *args:binding} if direct else callbacks(binding))
    interface=f'ROUTINE work({params})'+(f':{kind}' if kind else '')+' FROM HOST '
    return compile_program(body,decl=decl,prefix=prefix,routines=interface+routines,context=ctx,**options)
def execute(binding,**options):
    p,r=build(binding,**options);return p.run(),p,r


class ExternalOutputScalarTests(unittest.TestCase):
    def test_uninitialized_integer_output(self):self.assertEqual(execute(reply(output(1,integer(17))))[0]['N'],17)
    def test_initialized_integer_output(self):self.assertEqual(execute(reply(output(1,integer(17))),body='n=7 work(n)')[0]['N'],17)
    def test_real_output(self):self.assertEqual(execute(reply(output(1,row(['REAL'],1.25))),params='value:REAL',decl='n:REAL')[0]['N'],1.25)
    def test_boolean_output(self):self.assertIs(execute(reply(output(1,row(['BOOLEAN'],True))),params='value:BOOLEAN',decl='n:BOOLEAN')[0]['N'],True)
    def test_byte_output(self):self.assertEqual(execute(reply(output(1,row(['BYTE'],255))),params='value:BYTE',decl='n:BYTE')[0]['N'],255)
    def test_short_output(self):self.assertEqual(execute(reply(output(1,row(['SHORT'],-32768))),params='value:SHORT',decl='n:SHORT')[0]['N'],-32768)
    def test_string_output(self):self.assertEqual(execute(reply(output(1,row(['STRING',4],'seed'))),params='value:STRING',decl='n:STRING[4]')[0]['N'],'seed')
    def test_missing_scalar_output(self):self.assertEqual(execute(reply(output(1,integer(U))),body='n=7 work(n)')[0]['N'],U)
    def test_unknown_byte_output(self):self.assertEqual(execute(reply(output(1,row(['BYTE'],B))),params='value:BYTE',decl='n:BYTE',body='n=7 work(n)')[0]['N'],B)
    def test_short_sentinel_output_canonicalizes_missing(self):self.assertEqual(execute(reply(output(1,row(['SHORT'],32767))),params='value:SHORT',decl='n:SHORT',body='n=7 work(n)')[0]['N'],U)
    def test_function_result_and_output(self):
        v,_,_=execute(reply(output(1,integer(17)),result=integer(42)),kind='INTEGER',body='s=work(n)');self.assertEqual((v['N'],v['S']),(17,42))
    def test_multiple_disjoint_outputs(self):
        v,_,_=execute(reply(output(2,integer(42)),output(1,integer(17))),params='a,b:INTEGER',body='work(n,s)');self.assertEqual((v['N'],v['S']),(17,42))
    def test_untargeted_argument_unchanged(self):
        v,_,_=execute(reply(output(2,integer(42))),params='a,b:INTEGER',body='n=7 work(n,s)');self.assertEqual((v['N'],v['S']),(7,42))
    def test_grouped_argument_uses_private_cell(self):self.assertEqual(execute(reply(output(1,integer(17))),body='n=7 work((n))')[0]['N'],7)
    def test_computed_argument_uses_private_cell(self):self.assertEqual(execute(reply(output(1,integer(17))),body='n=7 work(n+0)')[0]['N'],7)
    def test_literal_argument_uses_private_cell(self):self.assertEqual(execute(reply(output(1,integer(17))),body='n=7 work(7)')[0]['N'],7)
    def test_promoted_narrow_argument_has_no_copyback(self):self.assertEqual(execute(reply(output(1,integer(17))),decl='n:BYTE',body='n=7 work(n)')[0]['N'],7)
    def test_inherited_string_capacity_must_be_actual(self):
        p,_=build(reply(output(1,row(['STRING',4],'seed'))),params='value:STRING',decl='n:STRING[8]',body="n='old' work(n)")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],'old')
    def test_direct_callback_response_protocol(self):self.assertEqual(execute(reply(output(1,integer(17))),direct=True)[0]['N'],17)
    def test_empty_output_response(self):self.assertEqual(execute(reply(),body='n=7 work(n)')[0]['N'],7)
    def test_case_matches_missing_output_input(self):self.assertEqual(execute(cases([integer(U)],reply(output(1,integer(17)))))[0]['N'],17)
    def test_case_matches_old_value_before_outputs(self):self.assertEqual(execute(cases([integer(7)],reply(output(1,integer(17)))),body='n=7 work(n)')[0]['N'],17)


class ExternalOutputAggregateTests(unittest.TestCase):
    def test_vector_output(self):
        value=dict(X=1.,Y=2.,Z=3.);self.assertEqual(execute(reply(output(1,row(['VECTOR'],value))),params='value:VECTOR',decl='n:VECTOR')[0]['N'],value)
    def test_config_output(self):self.assertEqual(execute(reply(output(1,row(['CONFIG'],CFG))),params='value:CONFIG',decl='n:CONFIG')[0]['N'],CFG)
    def test_xyzwpr_output(self):self.assertEqual(execute(reply(output(1,row(['XYZWPR'],POINT))),params='value:XYZWPR',decl='n:XYZWPR')[0]['N'],POINT)
    def test_extended_pose_output(self):
        value={**POINT,'EXT1':7.,'EXT2':8.,'EXT3':9.};self.assertEqual(execute(reply(output(1,row(['XYZWPREXT'],value))),params='value:XYZWPREXT',decl='n:XYZWPREXT')[0]['N'],value)
    def test_partial_joint_output(self):self.assertEqual(execute(reply(output(1,row(['JOINTPOS',2],{'axes':[0.,U]}))),params='value:JOINTPOS2',decl='n:JOINTPOS2')[0]['N'],{'axes':[0.,U]})
    def test_joint_axis_output(self):self.assertEqual(execute(reply(output(1,row(['REAL'],90.))),params='value:REAL',decl='n:JOINTPOS2',body='work(n[2])')[0]['N'],{'axes':[U,90.]})
    def test_array_output(self):self.assertEqual(execute(reply(output(1,row(['ARRAY',2,['INTEGER']],[17,42]))),params='value:ARRAY OF INTEGER',decl='n:ARRAY[2]OF INTEGER')[0]['N'],[17,42])
    def test_partial_array_output(self):self.assertEqual(execute(reply(output(1,row(['ARRAY',2,['INTEGER']],[17,U]))),params='value:ARRAY OF INTEGER',decl='n:ARRAY[2]OF INTEGER')[0]['N'],[17,U])
    def test_named_array_output(self):self.assertEqual(execute(reply(output(1,row(['ARRAY',2,['INTEGER'],'ROW_T'],[17,42]))),prefix='TYPE row_t=ARRAY[2]OF INTEGER',params='value:row_t',decl='n:row_t')[0]['N'],[17,42])
    def test_named_record_output(self):
        value=dict(ID=17,LABEL='seed');self.assertEqual(execute(reply(output(1,row(ITEM,value))),prefix='TYPE item_t=STRUCTURE id:INTEGER label:STRING[4] ENDSTRUCTURE',params='value:item_t',decl='n:item_t')[0]['N'],value)
    def test_scalar_field_and_element_outputs(self):
        v,_,_=execute(reply(output(1,integer(17)),output(2,integer(42))),prefix='TYPE item_t=STRUCTURE id:INTEGER ENDSTRUCTURE',params='a,b:INTEGER',decl='n:item_t s:ARRAY[2]OF INTEGER',body='work(n.id,s[2])');self.assertEqual((v['N']['ID'],v['S'][1]),(17,42))
    def test_grouped_array_is_private(self):
        v,_,_=execute(reply(output(1,row(['ARRAY',2,['INTEGER']],[17,42]))),params='value:ARRAY OF INTEGER',decl='n:ARRAY[2]OF INTEGER',body='n[1]=7 work((n))');self.assertEqual(v['N'],[7,U])
    def test_direct_prefix_is_private(self):
        v,_,_=execute(reply(output(1,row(['ARRAY',2,['INTEGER']],[17,42]))),params='value:ARRAY OF INTEGER',decl='n:ARRAY[2,2]OF INTEGER',body='n[1,1]=7 work(n[1])');self.assertEqual(v['N'],[[7,U],[U,U]])
    def test_byname_prefix_updates_original_cells(self):
        v,_,_=execute(reply(output(1,row(['ARRAY',2,['INTEGER']],[17,42]))),params='value:ARRAY OF INTEGER',decl='n:ARRAY[2,2]OF INTEGER s:INTEGER',body="n[1,1]=7 work(BYNAME('','N[1]',s))");self.assertEqual(v['N'],[[17,42],[U,U]])
    def test_disjoint_byname_rows_publish_together(self):
        v,_,_=execute(reply(output(1,row(['ARRAY',2,['INTEGER']],[17,42])),output(2,row(['ARRAY',2,['INTEGER']],[7,9]))),params='a,b:ARRAY OF INTEGER',decl='n:ARRAY[2,2]OF INTEGER s:INTEGER',body="work(BYNAME('','N[1]',s),BYNAME('','N[2]',s))");self.assertEqual(v['N'],[[17,42],[7,9]])
    def test_aggregate_root_identity_survives(self):
        p,_=build(reply(output(1,row(['ARRAY',2,['INTEGER']],[17,42]))),params='value:ARRAY OF INTEGER',decl='n:ARRAY[2]OF INTEGER');old=p._state.raw('N');p.run();self.assertIs(p._state.raw('N'),old)
    def test_field_alias_survives_record_output(self):
        binding=reply(output(1,row(ITEM,dict(ID=17,LABEL='seed'))));v,_,_=execute(binding,prefix='TYPE item_t=STRUCTURE id:INTEGER label:STRING[4] ENDSTRUCTURE',params='value:item_t',decl='n:item_t s:INTEGER',body='n.id=7 borrow(n.id)',routines='ROUTINE borrow(alias:INTEGER) BEGIN work(n) s=alias alias=99 END borrow');self.assertEqual((v['S'],v['N']['ID']),(17,99))
    def test_joint_axis_alias_survives_whole_joint_output(self):
        binding=reply(output(1,row(['JOINTPOS',2],{'axes':[17.,42.]})));v,_,_=execute(binding,params='value:JOINTPOS2',decl='n:JOINTPOS2 seen:REAL',body='n[1]=7 borrow(n[1])',routines='ROUTINE borrow(alias:REAL) BEGIN work(n) seen=alias alias=99 END borrow');self.assertEqual((v['SEEN'],v['N']['axes']),(17.,[99.,42.]))
    def test_position_whole_output_keeps_readonly_columns(self):
        value={'LOCATION':dict(X=12.,Y=0.,Z=0.),'NORMAL':dict(X=1.,Y=0.,Z=0.),'ORIENT':dict(X=0.,Y=1.,Z=0.),'APPROACH':dict(X=0.,Y=0.,Z=1.),'CONFIG_DATA':CFG};v,p,_=execute(reply(output(1,row(['POSITION'],value))),params='value:POSITION',decl='n:POSITION');self.assertEqual(v['N'],value);self.assertTrue(p._state.raw('N').values['NORMAL'].read_only)


class ExternalOutputAtomicTests(unittest.TestCase):
    def test_wrong_result_type_keeps_all_outputs(self):
        p,_=build(reply(output(1,integer(17)),result=row(['BOOLEAN'],True)),kind='INTEGER',body='n=7 s=99 s=work(n)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,99))
    def test_procedure_result_failure_keeps_outputs(self):
        p,_=build(reply(output(1,integer(17)),result=integer(42)),body='n=7 work(n)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],7)
    def test_missing_function_result_keeps_outputs(self):
        p,_=build(reply(output(1,integer(17))),kind='INTEGER',body='n=7 s=work(n)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],7)
    def test_bad_later_output_schema_keeps_earlier_target(self):
        p,_=build(reply(output(1,integer(17)),output(2,row(['BOOLEAN'],True))),params='a,b:INTEGER',body='n=7 s=9 work(n,s)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,9))
    def test_bad_later_raw_payload_keeps_earlier_target(self):
        p,_=build(reply(output(1,integer(17)),output(2,integer(True))),params='a,b:INTEGER',body='n=7 s=9 work(n,s)',direct=True)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,9))
    def test_duplicate_actual_scalar_outputs_reject(self):
        p,_=build(reply(output(1,integer(17)),output(2,integer(42))),params='a,b:INTEGER',body='n=7 work(n,n)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['N'],7)
    def test_whole_array_and_element_overlap_reject(self):
        p,_=build(reply(output(1,row(['ARRAY',2,['INTEGER']],[17,42])),output(2,integer(99))),params='a:ARRAY OF INTEGER;b:INTEGER',decl='n:ARRAY[2]OF INTEGER',body='n[1]=7 work(n,n[1])')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['N'],[7,U])
    def test_whole_joint_and_axis_overlap_reject(self):
        p,_=build(reply(output(1,row(['JOINTPOS',2],{'axes':[17.,42.]})),output(2,row(['REAL'],99.))),params='a:JOINTPOS2;b:REAL',decl='n:JOINTPOS2',body='n[1]=7 work(n,n[1])')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['N']['axes'],[7.,U])
    def test_equal_byname_rows_overlap_reject(self):
        values=row(['ARRAY',2,['INTEGER']],[17,42]);p,_=build(reply(output(1,values),output(2,values)),params='a,b:ARRAY OF INTEGER',decl='n:ARRAY[2,2]OF INTEGER s:INTEGER',body="n[1,1]=7 work(BYNAME('','N[1]',s),BYNAME('','N[1]',s))")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['N'],[[7,U],[U,U]])
    def test_unselected_argument_alias_is_allowed(self):
        self.assertEqual(execute(reply(output(1,integer(17))),params='a,b:INTEGER',body='n=7 work(n,n)')[0]['N'],17)
    def test_invalid_later_target_value_keeps_earlier_target(self):
        p,_=build(reply(output(1,integer(17)),output(2,row(['REAL'],42.))),params='a:INTEGER;b:REAL',decl='n:INTEGER s:REAL',body='n=7 work(n,s)');p._state.values['S']=float('nan')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],7)
    def test_raw_callback_effects_remain_on_failed_response(self):
        p,_=build(reply(),kind='INTEGER',body='n=7 s=work(n)')
        def callback(value):value.set(42);return reply(output(1,integer(17)),result=row(['BOOLEAN'],True))
        p._state.execution.externals['HOST','WORK']=callback
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],42)
    def test_unmatched_case_does_not_publish_outputs(self):
        p,_=build(cases([integer(7)],reply(output(1,integer(17)))),body='n=9 work(n)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'No external value case'):p.run()
        self.assertEqual(p.snapshot()['N'],9)
    def test_wrong_array_shape_does_not_publish(self):
        p,_=build(reply(output(1,row(['ARRAY',1,['INTEGER']],[17]))),params='value:ARRAY OF INTEGER',decl='n:ARRAY[2]OF INTEGER',body='n[1]=7 work(n)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],[7,U])
    def test_wrong_named_array_does_not_publish(self):
        p,_=build(reply(output(1,row(['ARRAY',2,['INTEGER'],'OTHER_T'],[17,42]))),prefix='TYPE row_t=ARRAY[2]OF INTEGER',params='value:row_t',decl='n:row_t',body='n[1]=7 work(n)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],[7,U])
    def test_output_ordinal_must_exist_in_actual_call(self):
        p,_=build(reply(output(2,integer(17))),body='n=7 work(n)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],7)
    def test_bad_response_does_not_run_destination_selector(self):
        p,_=build(reply(output(1,integer(17)),result=row(['BOOLEAN'],True)),kind='INTEGER',decl='n,s:INTEGER data:ARRAY[2]OF INTEGER',body='n=7 s=0 data[pick()]=work(n)',routines='ROUTINE pick:INTEGER BEGIN s=1 RETURN 1 END pick')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,0))
    def test_result_is_detached_before_destination_selector_effects(self):
        binding=reply(output(1,integer(17)),result=row(['ARRAY',2,['INTEGER']],[7,9]));p,_=build(binding,kind='ARRAY[2]OF INTEGER',decl='n:INTEGER data:ARRAY[2,2]OF INTEGER',body='data[pick()]=work(n)',routines='ROUTINE pick:INTEGER BEGIN change RETURN 1 END pick ROUTINE change FROM HOST',direct=True);p._state.execution.externals['HOST','CHANGE']=lambda:binding['result']['value'].__setitem__(0,99);self.assertEqual(p.run()['DATA'][0],[7,9])


class ExternalOutputCaptureTests(unittest.TestCase):
    def test_output_selector_evaluates_once(self):
        v,_,_=execute(reply(output(1,integer(17))),decl='n:ARRAY[2]OF INTEGER s:INTEGER',body='s=0 work(n[pick()])',routines='ROUTINE pick:INTEGER BEGIN s=s+1 RETURN 2 END pick');self.assertEqual((v['N'],v['S']),([U,17],1))
    def test_later_selector_does_not_retarget_earlier_output(self):
        v,_,_=execute(reply(output(1,integer(17))),params='a,b:INTEGER',decl='n:ARRAY[2]OF INTEGER s:INTEGER',body='s=1 work(n[s],pick())',routines='ROUTINE pick:INTEGER BEGIN s=2 RETURN 9 END pick');self.assertEqual((v['N'],v['S']),([17,U],2))
    def test_selector_effects_remain_when_batch_rejects(self):
        p,_=build(reply(output(1,row(['BOOLEAN'],True))),decl='n:ARRAY[2]OF INTEGER s:INTEGER',body='s=0 work(n[pick()])',routines='ROUTINE pick:INTEGER BEGIN s=1 RETURN 2 END pick')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),([U,U],1))
    def test_config_turn_argument_remains_private(self):
        v,_,_=execute(reply(output(1,integer(7))),decl='n:CONFIG',body='n.cfg_turn_no1=0 work(n.cfg_turn_no1)');self.assertEqual(v['N']['CFG_TURN_NO1'],0)
    def test_position_orientation_source_argument_remains_rejected(self):
        with self.assertRaises(TranslationError):build(reply(output(1,row(['REAL'],17.))),params='value:REAL',decl='n:POSITION',body='work(n.normal.x)')
    def test_for_counter_source_argument_remains_rejected(self):
        with self.assertRaises(TranslationError):build(reply(output(1,integer(17))),body='FOR n=1 TO 2 DO work(n) ENDFOR')
    def test_grouped_for_counter_has_private_output(self):
        v,_,_=execute(reply(output(1,integer(17))),body='s=0 FOR n=1 TO 2 DO work((n)) s=s+n ENDFOR');self.assertEqual(v['S'],3)
    def test_dispatch_engine(self):self.assertEqual(execute(reply(output(1,integer(17))),body='start:: work(n) GOTO done done::')[0]['N'],17)
    def test_cooperative_engine(self):self.assertEqual(execute(reply(output(1,integer(17))),cooperative=True)[0]['N'],17)
    def test_linked_source_forwards_output_reference(self):
        files={'main':'PROGRAM MAIN VAR n:INTEGER ROUTINE fill(value:INTEGER) FROM LIB BEGIN fill(n) END MAIN','lib':'PROGRAM LIB ROUTINE work(value:INTEGER) FROM HOST ROUTINE fill(value:INTEGER) BEGIN work(value) END fill BEGIN END LIB'};p=translate_project(files).instantiate(context=rt.ExecutionContext(externals=callbacks(reply(output(1,integer(17))))));self.assertEqual(p.run('MAIN')['MAIN']['values']['N'],17)
    def test_handler_action_publishes_response(self):
        self.assertEqual(execute(reply(output(1,integer(17))),body='CONDITION[1]: WHEN TRUE DO work(n) ENDCONDITION ENABLE CONDITION[1] s=0')[0]['N'],17)
    def test_case_output_is_captured_independently(self):
        binding=cases([integer(7)],reply(output(1,integer(17))));p,_=build(binding,body='n=7 work(n)');binding['cases'][0]['outputs'][0]['value']['value']=99;self.assertEqual(p.run()['N'],17)
    def test_saved_globals_omit_response_bindings(self):
        _,p,_=execute(reply(output(1,integer(17))));saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertNotIn('externals',saved);self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)


class ExternalOutputLifecycleTests(unittest.TestCase):
    def test_generator_pause_defers_all_outputs_until_return(self):
        p,_=build(reply(),kind='INTEGER',body='n=7 s=work(n)')
        def callback(value):
            yield dict(kind='pause',line=1)
            return reply(output(1,integer(17)),result=integer(42))
        p._state.execution.externals['HOST','WORK']=callback
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],7);v=p.resume();self.assertEqual((v['N'],v['S']),(17,42));self.assertEqual(p._state.local_frames,[])
    def test_stop_discards_pending_response(self):
        p,_=build(reply(),body='n=7 work(n)')
        def callback(value):
            yield dict(kind='pause',line=1)
            return reply(output(1,integer(17)))
        p._state.execution.externals['HOST','WORK']=callback
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['N'],7);self.assertEqual(p._state.local_frames,[])
    def test_pause_after_completed_response_keeps_outputs(self):
        p,_=build(reply(output(1,integer(17))),body='work(n) PAUSE s=n',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['N'],17);self.assertEqual(p.resume()['S'],17)
    def test_raw_callback_abort_keeps_prior_effects_and_discards_reply(self):
        p,_=build(reply(),body='n=7 work(n)')
        def callback(value):value.set(42);p._state._aborted=True;return reply(output(1,integer(17)))
        p._state.execution.externals['HOST','WORK']=callback
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(p.snapshot()['N'],42)
    def test_budget_failure_prevents_call_outputs(self):
        p,_=build(reply(output(1,integer(17))),body='n=7 work(n)')
        with self.assertRaises(rt.KarelRuntimeError):p.run(max_steps=1)
        self.assertNotEqual(p.snapshot()['N'],17)


class ExternalOutputValidationTests(unittest.TestCase):
    def reject(self,binding):
        with self.assertRaises(ValueError):callbacks(binding)
    def test_outputs_must_be_list(self):self.reject(dict(result=None,outputs={}))
    def test_output_entry_has_exact_keys(self):self.reject(reply(dict(argument=1,value=integer(17),extra=1)))
    def test_duplicate_output_ordinals_reject(self):self.reject(reply(output(1,integer(17)),output(1,integer(42))))
    def test_boolean_ordinal_rejects(self):self.reject(reply(output(True,integer(17))))
    def test_zero_ordinal_rejects(self):self.reject(reply(output(0,integer(17))))
    def test_negative_ordinal_rejects(self):self.reject(reply(output(-1,integer(17))))
    def test_string_ordinal_rejects(self):self.reject(reply(output('1',integer(17))))
    def test_large_ordinal_rejects(self):self.reject(reply(output(65,integer(17))))
    def test_case_ordinal_must_exist_in_selector_arity(self):self.reject(cases([integer(7)],reply(output(2,integer(17)))))
    def test_none_output_is_not_a_typed_value(self):self.reject(reply(output(1,None)))
    def test_resource_output_schema_rejects(self):self.reject(reply(output(1,row(['FILE'],{}))))
    def test_collection_output_has_logical_contract(self):self.assertEqual(callbacks(reply(output(1,row(['QUEUE_TYPE'],dict(initialized=True,sequence=0,entries=[])))))['HOST','WORK']()['outputs'][0]['value']['value']['entries'],[])
    def test_missing_aggregate_container_rejects(self):self.reject(reply(output(1,row(['ARRAY',2,['INTEGER']],U))))
    def test_oversized_string_output_rejects(self):self.reject(reply(output(1,row(['STRING',2],'seed'))))
    def test_bad_later_output_rejects_before_installation(self):
        ctx=rt.ExecutionContext();before=dict(ctx.externals)
        with self.assertRaises(ValueError):ctx.externals.update(callbacks(reply(output(1,integer(17)),output(2,row(['BYTE'],256)))))
        self.assertEqual(ctx.externals,before)
    def test_response_storage_budget_includes_outputs(self):
        value=row(['ARRAY',16384,['INTEGER']],[U]*16384)
        with self.assertRaisesRegex(ValueError,'32767'):callbacks(reply(output(1,value),result=value))
    def test_raw_response_budget_precedes_codec(self):
        value=row(['ARRAY',16384,['INTEGER']],[U]*16384)
        with rt._numeric_scope('pythonic'),patch('karel2py.storage.decode_typed',side_effect=AssertionError('decoded')) as decode,self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(('ARRAY',None,('INTEGER',)),reply(output(1,value),result=value),[reference(('INTEGER',),7)])
        decode.assert_not_called()
    def test_strict_reply_helper_is_closed(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(),[])
    def test_readonly_reference_class_rejects(self):
        value=rt.Structure(('VECTOR',));ref=rt.ReadOnlyFieldReference(('REAL',),value.values,'X')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(output(1,row(['REAL'],17.))),[ref])
    def test_nonordinary_mapping_is_never_read(self):
        calls=[]
        class Mapping(dict):
            def __getitem__(self,key):calls.append(key);return super().__getitem__(key)
        ref=rt.Reference(rt.INTEGER,Mapping(value=7),'value')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(output(1,integer(17))),[ref])
        self.assertEqual(calls,[])
    def test_malformed_reference_schema_is_not_compared(self):
        calls=[]
        class Schema:
            def __eq__(self,other):calls.append(1);return True
        ref=rt.Reference(Schema(),{'value':7},'value')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(output(1,integer(17))),[ref])
        self.assertEqual(calls,[])
    def test_readonly_record_root_is_not_mutated(self):
        value=rt.Structure(('VECTOR',));value.read_only=True;value.values.update(X=1.,Y=0.,Z=0.);ref=reference(('VECTOR',),value)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(output(1,row(['VECTOR'],dict(X=17.,Y=42.,Z=0.)))),[ref])
        self.assertEqual(value.values['X'],1.)
    def test_public_reply_api_requires_exact_shape(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,dict(result=None,outputs=[],extra=1),[])
    def test_raw_reference_argument_count_is_bounded(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(),[reference(rt.INTEGER,7)]*65)


class ExternalOutputContextTests(unittest.TestCase):
    def test_system_pose_actual_remains_private(self):
        from tests.test_system_pose_values import context
        ctx=context();execute(reply(output(1,row(['REAL'],17.))),params='value:REAL',decl='n:REAL',body='work($MNUFRAME[1,2].location.x)',context=ctx);self.assertEqual(ctx.robot.frames[2].values['X'],12.)
    def test_joint_inside_array_overlaps_captured_axis(self):
        binding=reply(output(1,row(['ARRAY',1,['JOINTPOS',2]],[{'axes':[17.,42.]}])),output(2,row(['REAL'],99.)));p,_=build(binding,params='a:ARRAY OF JOINTPOS2;b:REAL',decl='n:ARRAY[1]OF JOINTPOS2',body='n[1][1]=7 work(n,n[1][1])')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['N'],[{'axes':[7.,U]}])
    def test_whole_record_and_field_overlap(self):
        binding=reply(output(1,row(ITEM,dict(ID=17,LABEL='seed'))),output(2,integer(99)));p,_=build(binding,prefix='TYPE item_t=STRUCTURE id:INTEGER label:STRING[4] ENDSTRUCTURE',params='a:item_t;b:INTEGER',decl='n:item_t',body='n.id=7 work(n,n.id)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['N']['ID'],7)
    def test_successful_case_result_and_outputs_share_old_input_snapshot(self):
        binding=cases([integer(7),integer(U)],reply(output(1,integer(17)),output(2,integer(42)),result=integer(99)));v,_,_=execute(binding,params='a,b:INTEGER',kind='INTEGER',decl='n,s,result:INTEGER',body='n=7 result=work(n,s)');self.assertEqual((v['N'],v['S'],v['RESULT']),(17,42,99))
    def test_outputs_are_not_applied_until_response_is_returned(self):
        binding=reply(output(1,integer(17)));callback=callbacks(binding)['HOST','WORK'];ref=reference(rt.INTEGER,7);response=callback(ref);self.assertEqual(ref.raw(),7)
        with rt._numeric_scope('pythonic'):self.assertIsNone(rt.external_reply_result(None,response,[ref]))
        self.assertEqual(ref.raw(),17)
    def test_response_callbacks_return_fresh_output_data(self):
        callback=callbacks(reply(output(1,row(['ARRAY',2,['INTEGER']],[17,42]))))['HOST','WORK'];first=callback();first['outputs'][0]['value']['value'][0]=99;self.assertEqual(callback()['outputs'][0]['value']['value'],[17,42])
    def test_new_report_policy(self):
        _,_,r=execute(reply(output(1,integer(17))));policy=r.report['external_output_policy'];self.assertFalse(policy['controller_validated']);self.assertIn('before',policy['publication']);self.assertEqual(policy['guide'],'docs/external-outputs.md')


class ExternalOutputOrderingTests(unittest.TestCase):
    def test_caller_result_assignment_follows_output_publication(self):
        v,_,_=execute(reply(output(1,integer(17)),result=integer(42)),kind='INTEGER',body='n=7 n=work(n)');self.assertEqual(v['N'],42)
    def test_caller_selector_observes_published_output(self):
        v,_,_=execute(reply(output(1,integer(2)),result=integer(42)),kind='INTEGER',decl='n:INTEGER data:ARRAY[2]OF INTEGER',body='n=1 data[n]=work(n)');self.assertEqual((v['N'],v['DATA']),(2,[U,42]))
    def test_missing_later_target_container_keeps_earlier_output(self):
        first=reference(rt.INTEGER,7);second=reference(('ARRAY',2,rt.INTEGER),rt.UNINITIALIZED)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.external_reply_result(None,reply(output(1,integer(17)),output(2,row(['ARRAY',2,['INTEGER']],[7,9]))),[first,second])
        self.assertEqual(first.raw(),7);self.assertIs(second.raw(),rt.UNINITIALIZED)
    def test_file_result_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):callbacks(reply(output(1,integer(17)),result=row(['FILE'],{})))


class ExternalOutputCLITests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='external_outputs_cli_');self.addCleanup(temp.cleanup);self.folder=Path(temp.name);self.script=self.folder/'converted.py';self.config=self.folder/'outputs.json';self.saved=self.folder/'state.json'
        self.binding=reply(output(1,integer(17)),output(2,integer(42)));self.config.write_bytes(json.dumps({'HOST':{'WORK':self.binding}}).encode());self.source='PROGRAM T VAR n,s:INTEGER ROUTINE work(a,b:INTEGER) FROM HOST BEGIN work(n,s) END T'
    def run_cli(self,*arguments,source=None,expected=0):
        self.script.write_bytes(translate(source or self.source).python_source.encode());environment=dict(os.environ);environment['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
        bootstrap="""import runpy,sys
class RuntimeOnly:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.project','tkinter','_tkinter','karel2py.gui','socket','ssl','http.client','urllib.request'):
   raise ImportError('Generated execution must use runtime only')
sys.meta_path.insert(0,RuntimeOnly());sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name='__main__')
"""
        result=subprocess.run([sys.executable,'-X','utf8','-c',bootstrap,str(self.script),*map(str,arguments)],cwd=self.folder,env=environment,capture_output=True,text=True);self.assertEqual(result.returncode,expected,result.stderr);return result
    def project_cli(self,*arguments,expected=0):
        (self.folder/'main.kl').write_bytes(self.source.replace('PROGRAM T','PROGRAM MAIN').replace('END T','END MAIN').encode());environment=dict(os.environ);environment['PYTHONPATH']=str(Path(__file__).resolve().parents[1]);result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py.project',str(self.folder),*map(str,arguments)],cwd=self.folder,env=environment,capture_output=True,text=True);self.assertEqual(result.returncode,expected,result.stderr);return result
    def test_generated_runtime_only_applies_outputs(self):
        import ast
        self.assertEqual(ast.literal_eval(self.run_cli('--external-values',self.config,'--state-out',self.saved).stdout),{'N':17,'S':42})
    def test_generated_saved_context_replay(self):
        self.run_cli('--external-values',self.config,'--state-out',self.saved);again=self.folder/'again.json';self.run_cli('--external-values',self.config,'--context',self.saved,'--state-out',again);self.assertEqual(json.loads(self.saved.read_text()),json.loads(again.read_text()))
    def test_generated_case_outputs(self):
        self.config.write_bytes(json.dumps({'HOST':{'WORK':cases([integer(U),integer(U)],self.binding)}}).encode());self.run_cli('--external-values',self.config)
    def test_generated_function_result_and_outputs(self):
        import ast
        self.binding['result']=integer(99);self.config.write_bytes(json.dumps({'HOST':{'WORK':self.binding}}).encode());source=self.source.replace('work(a,b:INTEGER) FROM','work(a,b:INTEGER):INTEGER FROM').replace('BEGIN work(n,s)','BEGIN s=work(n,s)');self.assertEqual(ast.literal_eval(self.run_cli('--external-values',self.config,source=source).stdout),{'N':17,'S':99})
    def test_bad_later_output_cannot_create_state_file(self):
        self.binding['outputs'][1]['value']=row(['BOOLEAN'],True);self.config.write_bytes(json.dumps({'HOST':{'WORK':self.binding}}).encode());self.run_cli('--external-values',self.config,'--state-out',self.saved,expected=1);self.assertFalse(self.saved.exists())
    def test_overlap_cannot_create_state_file(self):
        self.run_cli('--external-values',self.config,'--state-out',self.saved,source=self.source.replace('work(n,s)','work(n,n)'),expected=1);self.assertFalse(self.saved.exists())
    def test_bad_configuration_rejects_before_execution(self):
        self.config.write_bytes(json.dumps({'HOST':{'WORK':reply(output(0,integer(17)))}}).encode());self.run_cli('--external-values',self.config,'--state-out',self.saved,expected=2);self.assertFalse(self.saved.exists())
    def test_input_file_is_protected_from_output(self):
        before=self.config.read_bytes();self.run_cli('--external-values',self.config,'--state-out',self.config,expected=2);self.assertEqual(self.config.read_bytes(),before)
    def test_hardlinked_input_file_is_protected(self):
        alias=self.folder/'alias.json'
        try:os.link(self.config,alias)
        except OSError as error:self.skipTest(str(error))
        before=self.config.read_bytes();self.run_cli('--external-values',self.config,'--state-out',alias,expected=2);self.assertEqual(self.config.read_bytes(),before)
    def test_project_applies_response_outputs(self):
        result=self.project_cli('--entry','MAIN','--external-values',self.config,'--state-out',self.saved);self.assertEqual(json.loads(result.stdout)['MAIN']['values'],{'N':17,'S':42})
    def test_project_saved_context_replay(self):
        self.project_cli('--entry','MAIN','--external-values',self.config,'--state-out',self.saved);again=self.folder/'again.json';self.project_cli('--entry','MAIN','--external-values',self.config,'--context',self.saved,'--state-out',again);self.assertEqual(json.loads(self.saved.read_text()),json.loads(again.read_text()))
    def test_project_trace_cannot_overwrite_binding_input(self):
        before=self.config.read_bytes();self.project_cli('--entry','MAIN','--external-values',self.config,'--trace-out',self.config,expected=2);self.assertEqual(self.config.read_bytes(),before)
    def test_project_failed_response_still_saves_bounded_trace(self):
        self.source=self.source.replace('BEGIN work(n,s)','BEGIN work(n,n)');trace=self.folder/'trace.json';self.project_cli('--entry','MAIN','--external-values',self.config,'--state-out',self.saved,'--trace-out',trace,expected=1);self.assertTrue(trace.exists());self.assertFalse(self.saved.exists())
