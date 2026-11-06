"""Authored typed external data, explicit case adapters and CLI replay contracts."""
from copy import deepcopy
from io import BytesIO
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

U={'uninitialized':True}
B={'unknown_byte':True}
CFG={**dict.fromkeys(('CFG_TURN_NO1','CFG_TURN_NO2','CFG_TURN_NO3'),0),**dict.fromkeys(('CFG_FLIP','CFG_LEFT','CFG_UP','CFG_FRONT'),False)}
POINT={**dict.fromkeys(('X','Y','Z','W','P','R'),0.),'CONFIG_DATA':CFG}
ITEM=['STRUCTURE','ITEM_T',[['ID',['INTEGER']],['LABEL',['STRING',4]]]]

def row(spec,value):return {'type':spec,'value':value}
def integer(value):return row(['INTEGER'],value)
def cases(*pairs):return {'cases':[{'arguments':arguments,'result':result} for arguments,result in pairs]}
def prepare(binding):return rt.external_value_callbacks({'HOST':{'FETCH':binding}})
def build(binding,*,kind='INTEGER',body='target=fetch()',decl=None,routines='',prefix='',params='',direct=False,**options):
    ctx=options.pop('context',rt.ExecutionContext())
    ctx.externals.update({('HOST','FETCH'):lambda:binding} if direct else prepare(binding))
    p,r=compile_program(body,decl=decl or f'target:{kind} n,s:INTEGER',routines=f'ROUTINE fetch{params}:{kind} FROM HOST '+routines,prefix=prefix,context=ctx,**options)
    return p,r

def execute(binding,**options):
    p,r=build(binding,**options);return p.run(),p,r

def reference(spec,value):return rt.Reference(spec,{'value':value},'value')


class ExternalDataResultTests(unittest.TestCase):
    def test_integer(self):self.assertEqual(execute(integer(17))[0]['TARGET'],17)
    def test_real(self):self.assertEqual(execute(row(['REAL'],1.25),kind='REAL')[0]['TARGET'],1.25)
    def test_boolean(self):self.assertIs(execute(row(['BOOLEAN'],True),kind='BOOLEAN')[0]['TARGET'],True)
    def test_bounded_string(self):self.assertEqual(execute(row(['STRING',4],'seed'),kind='STRING[4]')[0]['TARGET'],'seed')
    def test_byte(self):self.assertEqual(execute(row(['BYTE'],255),kind='BYTE')[0]['TARGET'],255)
    def test_short(self):self.assertEqual(execute(row(['SHORT'],-32768),kind='SHORT')[0]['TARGET'],-32768)
    def test_vector(self):self.assertEqual(execute(row(['VECTOR'],dict(X=1.,Y=2.,Z=3.)),kind='VECTOR')[0]['TARGET'],dict(X=1.,Y=2.,Z=3.))
    def test_config(self):self.assertEqual(execute(row(['CONFIG'],CFG),kind='CONFIG')[0]['TARGET'],CFG)
    def test_xyzwpr(self):self.assertEqual(execute(row(['XYZWPR'],POINT),kind='XYZWPR')[0]['TARGET'],POINT)
    def test_xyzwprext(self):
        value={**POINT,'EXT1':7.,'EXT2':8.,'EXT3':9.};self.assertEqual(execute(row(['XYZWPREXT'],value),kind='XYZWPREXT')[0]['TARGET'],value)
    def test_position(self):
        value={'LOCATION':dict(X=12.,Y=0.,Z=0.),'NORMAL':dict(X=1.,Y=0.,Z=0.),'ORIENT':dict(X=0.,Y=1.,Z=0.),'APPROACH':dict(X=0.,Y=0.,Z=1.),'CONFIG_DATA':CFG};self.assertEqual(execute(row(['POSITION'],value),kind='POSITION')[0]['TARGET'],value)
    def test_joint(self):self.assertEqual(execute(row(['JOINTPOS',2],{'axes':[0.,90.]}),kind='JOINTPOS2')[0]['TARGET'],{'axes':[0.,90.]})
    def test_partial_joint(self):self.assertEqual(execute(row(['JOINTPOS',2],{'axes':[0.,U]}),kind='JOINTPOS2')[0]['TARGET'],{'axes':[0.,U]})
    def test_array(self):self.assertEqual(execute(row(['ARRAY',2,['INTEGER']],[17,9]),kind='ARRAY[2]OF INTEGER')[0]['TARGET'],[17,9])
    def test_partial_array(self):self.assertEqual(execute(row(['ARRAY',2,['INTEGER']],[17,U]),kind='ARRAY[2]OF INTEGER')[0]['TARGET'],[17,U])
    def test_matrix(self):self.assertEqual(execute(row(['ARRAY',[2,2],['INTEGER']],[[17,9],[3,5]]),kind='ARRAY[2,2]OF INTEGER')[0]['TARGET'],[[17,9],[3,5]])
    def test_unknown_byte_array(self):self.assertEqual(execute(row(['ARRAY',2,['BYTE']],[17,B]),kind='ARRAY[2]OF BYTE')[0]['TARGET'],[17,B])
    def test_named_record(self):
        value=dict(ID=17,LABEL='seed');self.assertEqual(execute(row(ITEM,value),kind='item_t',prefix='TYPE item_t=STRUCTURE id:INTEGER label:STRING[4] ENDSTRUCTURE')[0]['TARGET'],value)
    def test_partial_named_record(self):
        value=dict(ID=17,LABEL=U);self.assertEqual(execute(row(ITEM,value),kind='item_t',prefix='TYPE item_t=STRUCTURE id:INTEGER label:STRING[4] ENDSTRUCTURE')[0]['TARGET'],value)
    def test_named_array(self):
        self.assertEqual(execute(row(['ARRAY',2,['INTEGER'],'ROW_T'],[17,9]),kind='row_t',prefix='TYPE row_t=ARRAY[2]OF INTEGER')[0]['TARGET'],[17,9])
    def test_inherited_array_dimensions(self):
        value=row(['ARRAY',[2,2],['INTEGER']],[[17,9],[3,5]]);p,_=compile_program('target=fetch()',decl='target:ARRAY[2,2]OF INTEGER',routines='ROUTINE fetch:ARRAY[*,*]OF INTEGER FROM HOST',context=rt.ExecutionContext(externals=prepare(value)));self.assertEqual(p.run()['TARGET'],value['value'])
    def test_inherited_string_array_capacity(self):
        value=row(['ARRAY',2,['STRING',4]],['seed',U]);p,_=compile_program('target=fetch()',decl='target:ARRAY[2]OF STRING[4]',routines='ROUTINE fetch:ARRAY OF STRING FROM HOST',context=rt.ExecutionContext(externals=prepare(value)));self.assertEqual(p.run()['TARGET'],['seed',U])
    def test_direct_callback_typed_json(self):self.assertEqual(execute(integer(17),direct=True)[0]['TARGET'],17)
    def test_raw_callback_contract_still_works(self):self.assertEqual(execute(17,direct=True)[0]['TARGET'],17)
    def test_typed_schema_must_match_declaration(self):
        p,_=build(row(['BYTE'],17))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared schema'):p.run()
    def test_typed_string_capacity_does_not_cast(self):
        p,_=build(row(['STRING',8],'seed'),kind='STRING[4]')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_typed_array_name_is_exact(self):
        p,_=build(row(['ARRAY',2,['INTEGER'],'OTHER_T'],[17,9]),kind='row_t',prefix='TYPE row_t=ARRAY[2]OF INTEGER')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_anonymous_array_does_not_accept_named_outer_result(self):
        p,_=build(row(['ARRAY',2,['INTEGER'],'ROW_T'],[17,9]),kind='ARRAY[2]OF INTEGER')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_whole_missing_array_is_rejected_before_source_runs(self):
        with self.assertRaises(ValueError):prepare(row(['ARRAY',2,['INTEGER']],U))
    def test_strict_decoder_stays_closed(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.external_data_result(('INTEGER',),integer(17))


class ExternalValueOwnershipTests(unittest.TestCase):
    def test_fixed_result_is_fresh(self):
        callback=prepare(row(['ARRAY',2,['INTEGER']],[17,9]))['HOST','FETCH'];a=callback();a['value'][0]=99;self.assertEqual(callback()['value'],[17,9])
    def test_later_config_changes_are_detached(self):
        config={'HOST':{'FETCH':integer(17)}};callback=rt.external_value_callbacks(config)['HOST','FETCH'];config['HOST']['FETCH']['value']=99;self.assertEqual(callback(),integer(17))
    def test_fixed_binding_ignores_and_preserves_borrowed_arguments(self):
        ref=reference(rt.INTEGER,7);callback=prepare(integer(17))['HOST','FETCH'];self.assertEqual(callback(ref),integer(17));self.assertEqual(ref.raw(),7)
    def test_repeated_array_result_copies(self):
        v,p,_=execute(row(['ARRAY',2,['INTEGER']],[17,9]),kind='ARRAY[2]OF INTEGER',decl='target,other:ARRAY[2]OF INTEGER',body='target=fetch() other=fetch() target[1]=99');self.assertEqual(v['OTHER'],[17,9]);self.assertIsNot(p._state.raw('TARGET'),p._state.raw('OTHER'))
    def test_result_captured_before_destination_selector(self):
        binding=integer(17);p,_=build(binding,body='bank[pick()]=fetch()',decl='bank:ARRAY[2]OF INTEGER',routines='ROUTINE pick:INTEGER BEGIN change RETURN 2 END pick ROUTINE change FROM HOST',direct=True);p._state.execution.externals['HOST','CHANGE']=lambda:binding.update(value=99);self.assertEqual(p.run()['BANK'][1],17)
    def test_bad_typed_result_skips_destination_selector(self):
        p,_=build(row(['BOOLEAN'],True),body='n=0 bank[pick()]=fetch()',decl='bank:ARRAY[2]OF INTEGER n:INTEGER',routines='ROUTINE pick:INTEGER BEGIN n=1 RETURN 1 END pick')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0)
    def test_generator_pause_and_return_typed_value(self):
        p,_=build(integer(17));
        def callback():
            yield dict(kind='pause',line=1)
            return integer(17)
        p._state.execution.externals['HOST','FETCH']=callback
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['TARGET'],17);self.assertEqual(p._state.local_frames,[])
    def test_stop_discards_suspended_data(self):
        p,_=build(integer(17),body='target=7 target=fetch()')
        def callback():
            yield dict(kind='pause',line=1)
            return integer(17)
        p._state.execution.externals['HOST','FETCH']=callback
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(p.snapshot()['TARGET'],7);self.assertEqual(p._state.local_frames,[])
    def test_explicit_callback_effects_survive_bad_result(self):
        p,_=build(integer(17),body='target=7 target=fetch()')
        def callback():p._state.set('N',42);return row(['BOOLEAN'],True)
        p._state.execution.externals['HOST','FETCH']=callback
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['TARGET']),(42,7))
    def test_dispatch_engine(self):self.assertEqual(execute(integer(17),body='start:: target=fetch() GOTO done done::')[0]['TARGET'],17)
    def test_cooperative_engine(self):self.assertEqual(execute(integer(17),cooperative=True)[0]['TARGET'],17)
    def test_context_omits_bindings(self):
        _,p,_=execute(integer(17));saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertNotIn('externals',saved);self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_internal_forwarder(self):
        v,_,_=execute(integer(17),body='target=forward()',routines='ROUTINE forward:INTEGER BEGIN RETURN fetch() END forward');self.assertEqual(v['TARGET'],17)
    def test_linked_source_forwards_typed_data(self):
        project=translate_project({'main':'PROGRAM MAIN VAR target:INTEGER ROUTINE work:INTEGER FROM LIB BEGIN target=work() END MAIN','lib':'PROGRAM LIB ROUTINE fetch:INTEGER FROM HOST ROUTINE work:INTEGER BEGIN RETURN fetch() END work BEGIN END LIB'}).instantiate(context=rt.ExecutionContext(externals=prepare(integer(17))));self.assertEqual(project.run('MAIN')['MAIN']['values']['TARGET'],17)


class ExternalValueCaseTests(unittest.TestCase):
    def binding(self):return cases(([integer(1)],integer(17)),([integer(2)],integer(42)))
    def test_bare_argument_selects_case(self):self.assertEqual(execute(self.binding(),params='(v:INTEGER)',body='n=2 target=fetch(n)')[0]['TARGET'],42)
    def test_computed_argument_selects_case(self):self.assertEqual(execute(self.binding(),params='(v:INTEGER)',body='target=fetch(1+1)')[0]['TARGET'],42)
    def test_case_result_is_fresh(self):
        callback=prepare(self.binding())['HOST','FETCH'];a=callback(reference(rt.INTEGER,1));a['value']=99;self.assertEqual(callback(reference(rt.INTEGER,1)),integer(17))
    def test_cases_are_detached_from_config(self):
        binding=self.binding();callback=prepare(binding)['HOST','FETCH'];binding['cases'][0]['result']['value']=99;self.assertEqual(callback(reference(rt.INTEGER,1)),integer(17))

    def test_default_response_runs_only_after_no_case_matches(self):
        binding={**self.binding(),'default':{'result':integer(81),'outputs':[{'argument':1,'value':integer(12)}]}}
        values,_,_=execute(binding,params='(v:INTEGER)',body='n=1 s=fetch(n) n=9 target=fetch(n)')
        self.assertEqual((values['S'],values['TARGET'],values['N']),(17,81,12))

    def test_explicit_null_is_a_noop_and_null_case_keeps_precedence(self):
        binding={**cases(([integer(1)],None)),'default':{'result':None,'outputs':[{'argument':1,'value':integer(12)}]}}
        callback=prepare(binding)['HOST','FETCH']
        self.assertIsNone(callback(reference(rt.INTEGER,1)))
        self.assertIsNone(prepare({**self.binding(),'default':None})['HOST','FETCH'](reference(rt.INTEGER,9)))

    def test_default_response_output_failure_keeps_original_arguments_and_result(self):
        binding={**self.binding(),'default':{'result':integer(81),'outputs':[{'argument':1,'value':row(['REAL'],12.)}]}}
        program,_=build(binding,params='(v:INTEGER)',body='n=9 target=42 target=fetch(n)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'differs from its captured argument schema'):program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['TARGET']),(9,42))

    def test_default_does_not_bypass_case_capture_validation(self):
        callback=prepare({**self.binding(),'default':integer(99)})['HOST','FETCH']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'argument count differs'):callback()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ordinary typed data'):callback(9)
    def test_arguments_evaluate_once_before_matching(self):
        v,_,_=execute(self.binding(),params='(v:INTEGER)',body='n=0 target=fetch(pick())',routines='ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 2 END pick');self.assertEqual((v['N'],v['TARGET']),(1,42))
    def test_all_arguments_are_matched(self):
        binding=cases(([integer(1),integer(2)],integer(17)),([integer(2),integer(1)],integer(42)));self.assertEqual(execute(binding,params='(a,b:INTEGER)',body='target=fetch(2,1)')[0]['TARGET'],42)
    def test_unmatched_case_preserves_destination_and_arguments(self):
        p,_=build(self.binding(),params='(v:INTEGER)',body='target=7 n=3 target=fetch(n)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'No external value case'):p.run()
        self.assertEqual((p.snapshot()['TARGET'],p.snapshot()['N']),(7,3));self.assertEqual(p._state.local_frames,[])
    def test_missing_scalar_can_be_an_explicit_selector(self):
        v,_,_=execute(cases(([integer(U)],integer(17))),params='(v:INTEGER)',body='target=fetch(n)');self.assertEqual((v['TARGET'],v['N']),(17,U))
    def test_unknown_byte_selector(self):
        v,_,_=execute(cases(([row(['BYTE'],B)],integer(17))),params='(v:BYTE)',decl='target:INTEGER n:BYTE',body='target=fetch(n)');self.assertEqual((v['TARGET'],v['N']),(17,B))
    def test_integer_and_boolean_do_not_compare_equal(self):
        callback=prepare(cases(([integer(1)],integer(17)),([row(['BOOLEAN'],True)],integer(42))))['HOST','FETCH'];self.assertEqual(callback(reference(('BOOLEAN',),True)),integer(42))
    def test_real_numeric_representation_normalizes(self):
        callback=prepare(cases(([row(['REAL'],1)],integer(17))))['HOST','FETCH'];self.assertEqual(callback(reference(('REAL',),1.0)),integer(17))
    def test_string_capacity_remains_part_of_selector(self):
        callback=prepare(cases(([row(['STRING',4],'seed')],integer(17))))['HOST','FETCH']
        with self.assertRaises(rt.KarelRuntimeError):callback(reference(('STRING',8),'seed'))
    def test_partial_array_selector(self):
        binding=cases(([row(['ARRAY',2,['INTEGER']],[17,U])],integer(42)));v,_,_=execute(binding,params='(v:ARRAY OF INTEGER)',decl='target:INTEGER data:ARRAY[2]OF INTEGER',body='data[1]=17 target=fetch(data)');self.assertEqual(v['TARGET'],42)
    def test_named_record_selector(self):
        binding=cases(([row(ITEM,dict(ID=17,LABEL='seed'))],integer(42)));v,_,_=execute(binding,params='(v:item_t)',decl='target:INTEGER data:item_t',prefix='TYPE item_t=STRUCTURE id:INTEGER label:STRING[4] ENDSTRUCTURE',body="data.id=17 data.label='seed' target=fetch(data)");self.assertEqual(v['TARGET'],42)
    def test_wrong_argument_count_is_explicit(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'argument count'):prepare(self.binding())['HOST','FETCH']()
    def test_resource_argument_is_not_read_as_data(self):
        handle=rt.FileHandle()
        with self.assertRaises(rt.KarelRuntimeError):prepare(self.binding())['HOST','FETCH'](reference(('FILE',),handle))
        self.assertIsNone(handle.owner)
    def test_raw_python_argument_is_not_an_inferred_reference(self):
        with self.assertRaises(rt.KarelRuntimeError):prepare(self.binding())['HOST','FETCH'](1)
    def test_zero_argument_case(self):self.assertEqual(execute(cases(([],integer(17))))[0]['TARGET'],17)
    def test_error_does_not_echo_argument_payload(self):
        callback=prepare(cases(([row(['STRING',12],'allowed')],integer(17))))['HOST','FETCH']
        with self.assertRaises(rt.KarelRuntimeError) as caught:callback(reference(('STRING',12),'secret'))
        self.assertNotIn('secret',str(caught.exception))
    def test_source_counter_protection_is_preserved(self):
        with self.assertRaises(TranslationError):build(self.binding(),params='(v:INTEGER)',body='FOR n=1 TO 2 DO target=fetch(n) ENDFOR')
    def test_grouped_counter_uses_private_value(self):
        v,_,_=execute(self.binding(),params='(v:INTEGER)',body='FOR n=1 TO 2 DO target=fetch((n)) ENDFOR');self.assertEqual(v['TARGET'],42)


class ExternalValueProcedureTests(unittest.TestCase):
    def test_explicit_fixed_noop(self):
        p,_=compile_program('n=7 work(n) s=n',routines='ROUTINE work(v:INTEGER) FROM HOST',context=rt.ExecutionContext(externals=rt.external_value_callbacks({'HOST':{'WORK':None}})));self.assertEqual((p.run()['S'],p.snapshot()['N']),(7,7))
    def test_case_noop_preserves_argument(self):
        p,_=compile_program('n=7 work(n) s=n',routines='ROUTINE work(v:INTEGER) FROM HOST',context=rt.ExecutionContext(externals=rt.external_value_callbacks({'HOST':{'WORK':cases(([integer(7)],None))}})));self.assertEqual(p.run()['S'],7)
    def test_case_noop_must_match(self):
        p,_=compile_program('n=8 work(n)',routines='ROUTINE work(v:INTEGER) FROM HOST',context=rt.ExecutionContext(externals=rt.external_value_callbacks({'HOST':{'WORK':cases(([integer(7)],None))}})))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],8)
    def test_function_cannot_use_noop_result(self):
        p,_=build(None)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_procedure_cannot_return_data(self):
        p,_=compile_program('work',routines='ROUTINE work FROM HOST',context=rt.ExecutionContext(externals=rt.external_value_callbacks({'HOST':{'WORK':integer(17)}})))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'return None'):p.run()


class ExternalValueValidationTests(unittest.TestCase):
    def reject(self,value):
        with self.assertRaises(ValueError):prepare(value)
    def test_typed_string_cannot_silently_truncate(self):self.reject(row(['STRING',2],'seed'))
    def test_missing_marker_requires_boolean_true(self):self.reject(row(['ARRAY',1,['INTEGER']],[{'uninitialized':1}]))
    def test_false_missing_marker_rejects(self):self.reject(row(['ARRAY',1,['INTEGER']],[{'uninitialized':False}]))
    def test_marker_extra_keys_reject(self):self.reject(row(['ARRAY',1,['INTEGER']],[{'uninitialized':True,'extra':1}]))
    def test_unknown_byte_marker_cannot_be_integer(self):self.reject(row(['ARRAY',1,['INTEGER']],[B]))
    def test_scalar_missing_result_rejects(self):self.reject(integer(U))
    def test_scalar_unknown_byte_result_rejects(self):self.reject(row(['BYTE'],B))
    def test_scalar_short_sentinel_rejects(self):self.reject(row(['SHORT'],32767))
    def test_nonfinite_result_rejects(self):self.reject(row(['REAL'],float('inf')))
    def test_boolean_cannot_be_integer(self):self.reject(integer(True))
    def test_overflow_byte_rejects(self):self.reject(row(['BYTE'],256))
    def test_overflow_short_rejects(self):self.reject(row(['SHORT'],32768))
    def test_maxint_result_rejects(self):self.reject(integer(2147483647))
    def test_flat_matrix_payload_is_not_silently_reshaped(self):self.reject(row(['ARRAY',[2,2],['INTEGER']],[1,2,3,4]))
    def test_tuple_array_payload_rejects(self):self.reject(row(['ARRAY',2,['INTEGER']],(1,2)))
    def test_record_payload_field_case_is_explicit(self):self.reject(row(ITEM,dict(id=17,LABEL='seed')))
    def test_joint_payload_requires_canonical_axes(self):self.reject(row(['JOINTPOS',2],[0.,90.]))
    def test_file_schema_rejects(self):self.reject(row(['FILE'],{}))
    def test_path_schema_has_logical_value_contract(self):self.assertEqual(prepare(row(['PATH',None,None],{'nodes':[],'data':None}))['HOST','FETCH'](),row(['PATH',None,None],{'nodes':[],'data':None}))
    def test_embedded_resource_schema_rejects(self):self.reject(row(['STRUCTURE','ITEM_T',[['HANDLE',['FILE']]]],{'HANDLE':{}}))
    def test_unknown_type_rejects(self):self.reject(row(['UNLISTED'],17))
    def test_extra_typed_keys_reject(self):self.reject(dict(type=['INTEGER'],value=17,extra=1))
    def test_nonlist_type_rejects(self):self.reject(row('INTEGER',17))
    def test_generic_schema_cannot_allocate_data(self):self.reject(row(['ARRAY',None,['INTEGER']],[17]))
    def test_oversized_schema_rejects_before_codec(self):
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('allocated')) as decode,self.assertRaises(ValueError):prepare(row(['ARRAY',32768,['INTEGER']],[]))
        decode.assert_not_called()
    def test_case_argument_none_is_not_a_typed_selector(self):self.reject(cases(([None],integer(17))))
    def test_empty_cases_reject(self):self.reject({'cases':[]})
    def test_extra_case_keys_reject(self):self.reject({'cases':[{'arguments':[],'result':integer(17),'extra':1}]})
    def test_inconsistent_case_arities_reject(self):self.reject(cases(([],integer(17)),([integer(1)],integer(42))))
    def test_duplicate_normalized_cases_reject(self):self.reject(cases(([row(['REAL'],1)],integer(17)),([row(['REAL'],1.0)],integer(42))))
    def test_too_many_case_arguments_reject(self):self.reject(cases(([integer(1)]*65,integer(17))))
    def test_default_counts_against_case_budget_and_output_arity(self):
        binding=cases(*[([integer(i)],integer(i)) for i in range(128)])
        self.reject({**binding,'default':integer(128)})
        self.reject({**cases(([integer(1)],integer(17))),
                     'default':{'result':integer(42),'outputs':[{'argument':2,'value':integer(1)}]}})
    def test_fixed_and_case_row_budget_is_shared(self):
        config={'HOST':{'FETCH':cases(*[([integer(i)],integer(i)) for i in range(128)]),'OTHER':integer(1)}}
        with self.assertRaisesRegex(ValueError,'128'):rt.external_value_callbacks(config)
    def test_stored_scalar_leaf_budget_is_shared(self):
        config={'HOST':{'A':row(['ARRAY',16384,['INTEGER']],[U]*16384),'B':row(['ARRAY',16384,['INTEGER']],[U]*16384)}}
        with self.assertRaisesRegex(ValueError,'32767'):rt.external_value_callbacks(config)
    def test_binding_names_normalize(self):self.assertEqual(set(rt.external_value_callbacks({'host':{'fetch':integer(17)}})),{('HOST','FETCH')})
    def test_duplicate_normalized_bindings_reject(self):
        with self.assertRaises(ValueError):rt.external_value_callbacks({'host':{'fetch':integer(17)},'HOST':{'FETCH':integer(17)}})
    def test_invalid_program_name_rejects(self):
        with self.assertRaises(ValueError):rt.external_value_callbacks({'host.name':{'FETCH':integer(17)}})
    def test_invalid_routine_name_rejects(self):
        with self.assertRaises(ValueError):rt.external_value_callbacks({'HOST':{'fetch()':integer(17)}})
    def test_empty_configuration_rejects(self):
        with self.assertRaises(ValueError):rt.external_value_callbacks({})
    def test_invalid_later_binding_does_not_return_partial_bank(self):
        ctx=rt.ExecutionContext(externals={('KEEP','RUN'):lambda:None});before=dict(ctx.externals)
        with self.assertRaises(ValueError):ctx.externals.update(rt.external_value_callbacks({'HOST':{'FETCH':integer(17),'LATER':row(['STRING',1],'seed')}}))
        self.assertEqual(ctx.externals,before)


class ExternalValueFileTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='external_values_');self.addCleanup(temp.cleanup);self.folder=Path(temp.name);self.path=self.folder/'values.json';self.path.write_bytes(json.dumps({'HOST':{'FETCH':integer(17)}}).encode())
    def test_strict_file_load(self):self.assertEqual(rt.load_external_values(self.path)['HOST','FETCH'](),integer(17))
    def test_file_growth_after_stat_is_bounded_before_decode(self):
        limit=4*1024*1024
        stream=BytesIO(b' '*(limit+1))
        with patch.object(Path,'open',return_value=stream),patch.object(stream,'read',wraps=stream.read) as read:
            with patch('json.loads',side_effect=AssertionError('decoded')),self.assertRaisesRegex(ValueError,'exceeds 4 MiB'):
                rt.load_external_values(self.path)
        read.assert_called_once_with(limit+1)
    def test_utf8_bom(self):self.path.write_bytes(b'\xef\xbb\xbf'+self.path.read_bytes());self.test_strict_file_load()
    def test_duplicate_keys(self):
        self.path.write_bytes(b'{"HOST":{},"HOST":{}}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):rt.load_external_values(self.path)
    def test_nonfinite_json(self):
        self.path.write_bytes(b'{"HOST":{"FETCH":{"type":["REAL"],"value":NaN}}}')
        with self.assertRaisesRegex(ValueError,'Nonfinite'):rt.load_external_values(self.path)
    def test_overflow_json_real(self):
        self.path.write_bytes(b'{"HOST":{"FETCH":{"type":["REAL"],"value":1e999}}}')
        with self.assertRaises(ValueError):rt.load_external_values(self.path)
    def test_invalid_utf8(self):
        self.path.write_bytes(b'\xff')
        with self.assertRaises(ValueError):rt.load_external_values(self.path)
    def test_oversized_file_before_json_decode(self):
        self.path.write_bytes(b' '*(4*1024*1024+1))
        with patch('json.loads',side_effect=AssertionError('decoded')) as decode,self.assertRaisesRegex(ValueError,'4 MiB'):rt.load_external_values(self.path)
        decode.assert_not_called()
    def test_output_alias_preserves_input(self):
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):rt.load_external_values(self.path,outputs=(self.path,))
        self.assertEqual(self.path.read_bytes(),before)
    def test_hardlink_output_alias_preserves_input(self):
        alias=self.folder/'alias.json'
        try:os.link(self.path,alias)
        except OSError as error:self.skipTest(str(error))
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):rt.load_external_values(self.path,outputs=(alias,))
        self.assertEqual(self.path.read_bytes(),before)
    def test_data_and_legacy_collection_bindings_combine(self):
        collection=self.folder/'collections.json';collection.write_bytes(json.dumps({'HOST':{'QUEUE':row(['QUEUE_TYPE'],dict(initialized=True,sequence=1,entries=[[1,7]]))}}).encode());bank=rt.load_external_bindings(values=self.path,collections=collection);self.assertEqual(set(bank),{('HOST','FETCH'),('HOST','QUEUE')})
    def test_duplicate_binding_between_files_rejects(self):
        collection=self.folder/'collections.json';collection.write_bytes(json.dumps({'HOST':{'FETCH':row(['QUEUE_TYPE'],dict(initialized=True,sequence=1,entries=[[1,7]]))}}).encode())
        with self.assertRaisesRegex(ValueError,'duplicate'):rt.load_external_bindings(values=self.path,collections=collection)
    def test_other_input_file_is_also_protected(self):
        collection=self.folder/'collections.json';collection.write_bytes(json.dumps({'HOST':{'QUEUE':row(['QUEUE_TYPE'],dict(initialized=True,sequence=1,entries=[[1,7]]))}}).encode());before=collection.read_bytes()
        with self.assertRaises(ValueError):rt.load_external_bindings(values=self.path,collections=collection,outputs=(collection,))
        self.assertEqual(collection.read_bytes(),before)


class ExternalValueBoundaryTests(unittest.TestCase):
    def test_incoming_budget_precedes_argument_copies(self):
        callback=prepare(cases(([integer(1),integer(2)],integer(17))))['HOST','FETCH']
        with rt._numeric_scope('pythonic'):array=rt.Array(('ARRAY',16384,rt.INTEGER))
        with patch('karel2py.runtime._aggregate_value',side_effect=AssertionError('copied')) as copy,self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):callback(reference(array.spec,array),reference(array.spec,array))
        copy.assert_not_called()
    def test_real_zero_sign_does_not_create_a_distinct_selector(self):
        callback=prepare(cases(([row(['REAL'],-0.0)],integer(17))))['HOST','FETCH'];self.assertEqual(callback(reference(('REAL',),0.0)),integer(17))
    def test_zero_sign_duplicate_cases_reject(self):
        with self.assertRaises(ValueError):prepare(cases(([row(['REAL'],-0.0)],integer(17)),([row(['REAL'],0.0)],integer(42))))
    def test_live_data_prefix_is_copied_for_matching(self):
        binding=cases(([row(['ARRAY',2,['INTEGER']],[1,2])],integer(17)));v,_,_=execute(binding,params='(v:ARRAY OF INTEGER)',decl='target,n:INTEGER m:ARRAY[2,2]OF INTEGER',body="m[1,1]=1 m[1,2]=2 target=fetch(BYNAME('','M[1]',n))");self.assertEqual((v['TARGET'],v['M'][0]),(17,[1,2]))
    def test_explicit_callback_precedes_supplied_source_library(self):
        files={'main':'PROGRAM MAIN VAR result:INTEGER ROUTINE fetch:INTEGER FROM HOST BEGIN result=fetch() END MAIN','host':'PROGRAM HOST ROUTINE fetch:INTEGER BEGIN RETURN 99 END fetch BEGIN END HOST'};project=translate_project(files).instantiate(context=rt.ExecutionContext(externals=prepare(integer(17))));self.assertEqual(project.run('MAIN')['MAIN']['values']['RESULT'],17)
    def test_bad_later_array_leaf_preserves_receiver(self):
        source=row(['ARRAY',2,['BYTE']],[17,256]);p,_=build(source,kind='ARRAY[2]OF BYTE',body='target[1]=7 target=fetch()',direct=True)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['TARGET'],[7,B])
    def test_row_and_depth_limits_are_checked_before_decode(self):
        spec=['INTEGER']
        for i in range(65):spec=['STRUCTURE',f'T_{i}',[['VALUE',spec]]]
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('decoded')) as decode,self.assertRaises(ValueError):prepare(row(spec,{}))
        decode.assert_not_called()
    def test_new_report_policy_is_explicit(self):
        _,_,r=execute(integer(17));policy=r.report['external_value_policy'];self.assertFalse(policy['controller_validated']);self.assertIn('32767',policy['bounds']);self.assertEqual(policy['guide'],'docs/external-values.md')


class ExternalValueCLITests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='external_values_cli_');self.addCleanup(temp.cleanup);self.folder=Path(temp.name);self.script=self.folder/'converted.py';self.config=self.folder/'values.json';self.saved=self.folder/'state.json'
        self.config.write_bytes(json.dumps({'HOST':{'FETCH':cases(([integer(2)],integer(17)))}}).encode())
        self.source='PROGRAM T VAR n,result:INTEGER ROUTINE fetch(v:INTEGER):INTEGER FROM HOST BEGIN n=2 result=fetch(n) END T'
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
    def test_generated_runtime_only_loads_case_file(self):
        import ast
        result=self.run_cli('--external-values',self.config,'--state-out',self.saved);self.assertEqual(ast.literal_eval(result.stdout),{'N':2,'RESULT':17});self.assertTrue(self.saved.exists())
    def test_generated_replay_supplies_the_file_again(self):
        self.run_cli('--external-values',self.config,'--state-out',self.saved);first=json.loads(self.saved.read_text());again=self.folder/'again.json';self.run_cli('--external-values',self.config,'--context',self.saved,'--state-out',again);self.assertEqual(json.loads(again.read_text()),first)
    def test_bindings_are_not_embedded_in_saved_state(self):
        self.run_cli('--external-values',self.config,'--state-out',self.saved);self.assertNotIn('externals',json.loads(self.saved.read_text()));self.run_cli('--context',self.saved,expected=1)
    def test_bad_json_rejects_before_state_output(self):
        self.config.write_bytes(b'{');self.run_cli('--external-values',self.config,'--state-out',self.saved,expected=2);self.assertFalse(self.saved.exists())
    def test_duplicate_keys_reject_before_execution(self):
        self.config.write_bytes(b'{"HOST":{},"HOST":{}}');self.assertIn('Duplicate',self.run_cli('--external-values',self.config,expected=2).stderr)
    def test_input_is_protected_from_state_output(self):
        before=self.config.read_bytes();self.run_cli('--external-values',self.config,'--state-out',self.config,expected=2);self.assertEqual(self.config.read_bytes(),before)
    def test_hardlinked_input_is_protected_from_state_output(self):
        alias=self.folder/'alias.json'
        try:os.link(self.config,alias)
        except OSError as error:self.skipTest(str(error))
        before=self.config.read_bytes();self.run_cli('--external-values',self.config,'--state-out',alias,expected=2);self.assertEqual(self.config.read_bytes(),before)
    def test_unmatched_case_is_a_runtime_error(self):
        self.run_cli('--external-values',self.config,source=self.source.replace('n=2','n=3'),expected=1)
    def test_wrong_result_type_remains_a_runtime_error(self):
        self.config.write_bytes(json.dumps({'HOST':{'FETCH':row(['BOOLEAN'],True)}}).encode());self.run_cli('--external-values',self.config,expected=1)
    def test_explicit_noop_procedure_from_file(self):
        import ast
        self.config.write_bytes(json.dumps({'HOST':{'WORK':None}}).encode());source='PROGRAM T VAR n:INTEGER ROUTINE work(v:INTEGER) FROM HOST BEGIN n=7 work(n) END T';self.assertEqual(ast.literal_eval(self.run_cli('--external-values',self.config,source=source).stdout),{'N':7})
    def test_legacy_collections_and_data_can_share_one_execution(self):
        import ast
        legacy=self.folder/'collections.json';legacy.write_bytes(json.dumps({'HOST':{'QUEUE':row(['QUEUE_TYPE'],dict(initialized=True,sequence=1,entries=[[1,7]]))}}).encode());source=self.source.replace('VAR n,result:INTEGER','VAR n,result:INTEGER q:QUEUE_TYPE').replace('BEGIN n=2','ROUTINE queue:QUEUE_TYPE FROM HOST BEGIN n=2').replace('result=fetch(n)','result=fetch(n) q=queue()');result=self.run_cli('--external-values',self.config,'--external-collections',legacy,source=source);self.assertEqual(ast.literal_eval(result.stdout)['Q']['entries'],[[1,7]])
    def test_duplicate_binding_across_files_rejects(self):
        legacy=self.folder/'collections.json';legacy.write_bytes(json.dumps({'HOST':{'FETCH':row(['QUEUE_TYPE'],dict(initialized=True,sequence=1,entries=[[1,7]]))}}).encode());self.run_cli('--external-values',self.config,'--external-collections',legacy,expected=2)
    def test_project_execution_loads_explicit_values(self):
        result=self.project_cli('--entry','MAIN','--external-values',self.config,'--state-out',self.saved);self.assertEqual(json.loads(result.stdout)['MAIN']['values'],{'N':2,'RESULT':17})
    def test_project_json_replay(self):
        self.project_cli('--entry','MAIN','--external-values',self.config,'--state-out',self.saved);again=self.folder/'again.json';self.project_cli('--entry','MAIN','--external-values',self.config,'--context',self.saved,'--state-out',again);self.assertEqual(json.loads(self.saved.read_text()),json.loads(again.read_text()))
    def test_project_trace_cannot_overwrite_binding_file(self):
        before=self.config.read_bytes();self.project_cli('--entry','MAIN','--external-values',self.config,'--trace-out',self.config,expected=2);self.assertEqual(self.config.read_bytes(),before)
    def test_project_hardlinked_trace_cannot_overwrite_binding_file(self):
        alias=self.folder/'alias.json'
        try:os.link(self.config,alias)
        except OSError as error:self.skipTest(str(error))
        before=self.config.read_bytes();self.project_cli('--entry','MAIN','--external-values',self.config,'--trace-out',alias,expected=2);self.assertEqual(self.config.read_bytes(),before)


class ExternalValueStorageGuardTests(unittest.TestCase):
    def test_nonordinary_mapping_is_rejected_before_lookup(self):
        calls=[]
        class Mapping(dict):
            def __getitem__(self,key):calls.append(key);return super().__getitem__(key)
        callback=prepare(cases(([integer(1)],integer(17))))['HOST','FETCH'];ref=rt.Reference(rt.INTEGER,Mapping(value=1),'value')
        with self.assertRaises(rt.KarelRuntimeError):callback(ref)
        self.assertEqual(calls,[])
    def test_missing_reference_endpoint_is_explicit(self):
        callback=prepare(cases(([integer(1)],integer(17))))['HOST','FETCH'];ref=rt.Reference(rt.INTEGER,{},'value')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ordinary typed data'):callback(ref)
