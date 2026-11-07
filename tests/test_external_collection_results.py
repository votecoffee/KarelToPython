"""Explicit callback logical results: detached values, typed JSON and lifetimes."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value,collection_payload
from tests.test_extended_services import compile_program

PREFIX='TYPE node_t=STRUCTURE value:INTEGER octet:BYTE ENDSTRUCTURE header_t=STRUCTURE tag:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=node_t PATHHEADER=header_t'

def payload(value):
    with rt._numeric_scope('pythonic'):return typed_value(value)
def raw(p,name='SOURCE'):return p._state.values[name]
def seed(value):
    if type(value) is rt.PathValue:
        value.append();value.nodes[0].values['VALUE']=17;value.data.values['TAG']=7
    else:
        value.initialized=True;value.sequence=7;value.entries=[(3,17),(1,9)]
    return value

def make(kind,body='target=make()',*,result=None,encoded=False,routines='',**options):
    typename='route_t' if kind=='path' else 'QUEUE_TYPE';ctx=options.pop('context',rt.ExecutionContext())
    p,r=compile_program(body,prefix=PREFIX,decl=f'source,target:{typename} bank:ARRAY[2]OF {typename} n,s,visits:INTEGER',routines=f'ROUTINE make:{typename} FROM HOST '+routines,context=ctx,**options)
    seed(raw(p));ctx.externals['HOST','MAKE']=lambda:payload(raw(p)) if encoded else raw(p)
    if result is not None:ctx.externals['HOST','MAKE']=result
    return p,r

class ScalarCases:
    def build(self,*args,**options):return make(self.kind,*args,**options)
    def change(self,name='target'):return f'{name}[1].value=99' if self.kind=='path' else f'INIT_QUEUE({name})'
    @property
    def typename(self):return 'route_t' if self.kind=='path' else 'QUEUE_TYPE'
    def test_raw_result_is_detached(self):
        p,_=self.build();expected=payload(raw(p));p.run();self.assertEqual(payload(raw(p,'TARGET')),expected);self.assertIsNot(raw(p),raw(p,'TARGET'))
    def test_typed_json_result(self):
        p,_=self.build(encoded=True);expected=payload(raw(p));p.run();self.assertEqual(payload(raw(p,'TARGET')),expected)
    def test_result_mutation_leaves_callback_owned_value(self):
        p,_=self.build('target=make() '+self.change());expected=payload(raw(p));p.run();self.assertEqual(payload(raw(p)),expected)
    def test_plain_callback_budget_precedes_logical_publication(self):
        for encoded in (False,True):
            with self.subTest(encoded=encoded):
                p,_=self.build()
                source=raw(p)
                if type(source) is rt.PathValue:
                    for _ in range(10):source.append()
                else:
                    source.sequence=12
                    source.entries=[(index,index) for index in range(1,13)]
                value=payload(source) if encoded else source
                p._state.execution.externals['HOST','MAKE']=lambda:value
                target=raw(p,'TARGET')
                original=payload(target)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=8)
                self.assertIs(raw(p,'TARGET'),target)
                self.assertEqual(payload(target),original)

    def test_each_call_returns_an_independent_copy(self):
        p,_=self.build('bank[1]=make() bank[2]=make() '+self.change('bank[1]'));expected=payload(raw(p));p.run();self.assertEqual(payload(raw(p,'BANK').values[1]),expected)
    def test_partial_or_uninitialized_collection_is_data(self):
        p,_=self.build(encoded=True);source=raw(p)
        if self.kind=='path':source.nodes[0].values['VALUE']=rt.UNINITIALIZED
        else:source.initialized=False;source.sequence=0;source.entries=[]
        expected=payload(source);p.run();self.assertEqual(payload(raw(p,'TARGET')),expected)
    def test_receiver_root_identity_is_retained(self):
        p,_=self.build();target=raw(p,'TARGET');p.run();self.assertIs(raw(p,'TARGET'),target)
    def test_private_argument_can_use_callback_result(self):
        p,_=self.build('use(make())',routines=f'ROUTINE use(v:{self.typename}) BEGIN target=v {self.change("v")} END use');before=payload(raw(p));p.run();self.assertEqual(payload(raw(p,'TARGET')),before);self.assertEqual(payload(raw(p)),before)
    def test_internal_return_can_forward_callback_result(self):
        p,_=self.build('target=forward()',encoded=True,routines=f'ROUTINE forward:{self.typename} BEGIN RETURN make() END forward');before=payload(raw(p));p.run();self.assertEqual(payload(raw(p,'TARGET')),before)
    def test_result_precedes_destination_selector(self):
        p,_=self.build('bank[pick()]=make()',routines='ROUTINE pick:INTEGER BEGIN '+self.change('source')+' RETURN 2 END pick');before=payload(raw(p));p.run();self.assertEqual(payload(raw(p,'BANK').values[1]),before)
    def test_created_receiver_accepts_result(self):
        body=f"CREATE_VAR('CACHE','ITEM','T','{self.typename}',0,0,0,0,s) fill(BYNAME('CACHE','ITEM',n))"
        p,_=self.build(body,routines=f'ROUTINE fill(v:{self.typename}) BEGIN v=make() target=v END fill');before=payload(raw(p));p.run();self.assertEqual(payload(raw(p,'TARGET')),before)
    def test_callback_called_once(self):
        calls=[];p,_=self.build();p._state.execution.externals['HOST','MAKE']=lambda:(calls.append(1),raw(p))[1];p.run();self.assertEqual(calls,[1])
    def test_callback_side_effects_survive_invalid_result(self):
        p,_=self.build();before=payload(raw(p,'TARGET'))
        def callback():p._state.set('VISITS',7);return object()
        p._state.execution.externals['HOST','MAKE']=callback
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['VISITS'],payload(raw(p,'TARGET'))),(7,before));self.assertEqual(p._state.local_frames,[])
    def test_callback_exception_unwinds(self):
        def fail():raise ValueError('adapter failed')
        p,_=self.build(result=fail)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'adapter failed'):p.run()
        self.assertEqual(p._state.local_frames,[])
    def test_generator_can_return_value(self):
        p,_=self.build()
        def callback():
            yield from ()
            return payload(raw(p))
        p._state.execution.externals['HOST','MAKE']=callback;p.run();self.assertEqual(payload(raw(p,'TARGET')),payload(raw(p)))
    def test_generator_pause_retains_and_resumes_result(self):
        p,_=self.build()
        def callback():
            yield dict(kind='pause',line=1)
            return raw(p)
        p._state.execution.externals['HOST','MAKE']=callback
        with self.assertRaises(rt.KarelPause):p.run()
        p.resume();self.assertEqual(payload(raw(p,'TARGET')),payload(raw(p)));self.assertEqual(p._state.local_frames,[])
    def test_stop_discards_suspended_result(self):
        p,_=self.build();before=payload(raw(p,'TARGET'))
        def callback():
            yield dict(kind='pause',line=1)
            return raw(p)
        p._state.execution.externals['HOST','MAKE']=callback
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(payload(raw(p,'TARGET')),before);self.assertEqual(p._state.local_frames,[])
    def test_json_input_is_not_mutated(self):
        p,_=self.build();row=payload(raw(p));before=deepcopy(row);p._state.execution.externals['HOST','MAKE']=lambda:row;p.run();self.assertEqual(row,before)
    def test_later_json_changes_do_not_change_result(self):
        p,_=self.build();row=payload(raw(p));p._state.execution.externals['HOST','MAKE']=lambda:row;p.run();before=payload(raw(p,'TARGET'));row['value'].clear();self.assertEqual(payload(raw(p,'TARGET')),before)
    def test_unknown_result_keys_reject(self):
        p,_=self.build();row=payload(raw(p));row['extra']=1;p._state.execution.externals['HOST','MAKE']=lambda:row
        with self.assertRaisesRegex(rt.KarelRuntimeError,'exactly type and value'):p.run()
    def test_wrong_declared_json_kind_rejects(self):
        p,_=self.build(result=lambda:dict(type=['INTEGER'],value=17))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'declared schema'):p.run()
    def test_rejected_result_skips_destination_selector(self):
        p,_=self.build('visits=0 bank[pick()]=make()',result=lambda:None,routines='ROUTINE pick:INTEGER BEGIN visits=1 RETURN 1 END pick')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)
    def test_saved_context_omits_callback_and_private_captures(self):
        p,_=self.build(encoded=True);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved);self.assertNotIn('externals',saved)
    def test_compiled_and_dispatcher_engines(self):
        for prefix,coop in (('',False),('start:: ',False),('',True)):
            p,_=self.build(prefix+'target=make()',cooperative=coop,encoded=True);p.run();self.assertEqual(payload(raw(p,'TARGET')),payload(raw(p)))
    def test_report_records_callback_contract(self):
        _,r=self.build();self.assertEqual(r.report['external_collection_result_policy']['guide'],'docs/external-collection-results.md');self.assertFalse(r.report['external_collection_result_policy']['controller_validated'])

class PathCallbackTests(ScalarCases,unittest.TestCase):kind='path'
class QueueCallbackTests(ScalarCases,unittest.TestCase):
    def test_plain_result_keeps_existing_queue_entry_capacity(self):
        p,_=self.build()
        source=raw(p)
        source.sequence=16384
        source.entries=[(index,index) for index in range(1,16385)]
        p.run(max_steps=40000)
        target=raw(p,'TARGET')
        self.assertEqual((len(target.entries),target.sequence),(16384,16384))
        self.assertEqual((target.entries[0],target.entries[-1]),((1,1),(16384,16384)))

    kind='queue'
    def test_buffer_links_are_never_copied(self):
        p,_=self.build();source=raw(p)
        with rt._numeric_scope('pythonic'):source.buffer=rt.Array(('ARRAY',3,rt.INTEGER))
        p.run();self.assertIsNone(raw(p,'TARGET').buffer);self.assertIsNotNone(source.buffer)
    def test_sequence_and_sparse_id_order_are_preserved(self):
        p,_=self.build(encoded=True);p.run();self.assertEqual((raw(p,'TARGET').sequence,raw(p,'TARGET').entries),(7,[(3,17),(1,9)]))

BANK_PREFIX=PREFIX+' TYPE row_t=ARRAY[2]OF QUEUE_TYPE'
def bank(kind='queue',*,body='target=make()',encoded=False,decl=None,result_type=None,**options):
    typename='route_t' if kind=='path' else 'QUEUE_TYPE';ctx=rt.ExecutionContext();p,r=compile_program(body,prefix=BANK_PREFIX,decl=decl or f'source,target:ARRAY[2,2]OF {typename} n,s:INTEGER',routines=f'ROUTINE make:{result_type or "ARRAY[*,*]OF "+typename} FROM HOST',context=ctx,**options)
    for item in raw(p).values:
        if type(item) is rt.QueueValue:item.initialized=True
    seed(raw(p).values[-1]);ctx.externals['HOST','MAKE']=lambda:payload(raw(p)) if encoded else raw(p)
    return p,r

class BankCallbackTests(unittest.TestCase):
    def test_raw_queue_bank(self):
        p,_=bank();p.run();self.assertEqual(payload(raw(p,'TARGET')),payload(raw(p)));self.assertIsNot(raw(p).values[-1],raw(p,'TARGET').values[-1])
    def test_typed_queue_bank(self):
        p,_=bank(encoded=True);p.run();self.assertEqual(payload(raw(p,'TARGET')),payload(raw(p)))
    def test_raw_path_bank(self):
        p,_=bank('path');p.run();self.assertEqual(payload(raw(p,'TARGET')),payload(raw(p)))
    def test_typed_path_bank(self):
        p,_=bank('path',encoded=True);p.run();self.assertEqual(payload(raw(p,'TARGET')),payload(raw(p)))
    def test_cell_and_header_identity_retained(self):
        p,_=bank('path',encoded=True);target=raw(p,'TARGET');cells=list(target.values);headers=[item.data for item in cells];p.run();self.assertTrue(all(a is b for a,b in zip(cells,target.values)));self.assertTrue(all(a is b.data for a,b in zip(headers,cells)))
    def test_bank_result_can_be_written(self):
        p,_=bank(body='WRITE(make())');p.run();self.assertEqual(p.write_requests[0]['text'],' 17 9')
    def test_generic_outer_dimensions_become_concrete(self):
        p,_=bank(encoded=True);p.run();self.assertEqual(raw(p,'TARGET').shape,(2,2))
    def test_named_outer_result_requires_exact_name(self):
        p,_=bank(decl='source,target:row_t n,s:INTEGER',result_type='row_t');p.run();self.assertEqual(payload(raw(p,'TARGET')),payload(raw(p)))
    def test_wrong_named_schema_rejects(self):
        p,_=bank(decl='source,target:row_t n,s:INTEGER',result_type='row_t',encoded=True);row=payload(raw(p));row['type'][-1]='OTHER_T';p._state.execution.externals['HOST','MAKE']=lambda:row
        with self.assertRaisesRegex(rt.KarelRuntimeError,'schema'):p.run()
    def test_shape_mismatch_keeps_receiver(self):
        p,_=bank(encoded=True);row=payload(raw(p));row['type'][1]=[1,4];p._state.execution.externals['HOST','MAKE']=lambda:row;before=payload(raw(p,'TARGET'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(payload(raw(p,'TARGET')),before)
    def test_malformed_later_cell_keeps_all_receiver_cells(self):
        p,_=bank(encoded=True);row=payload(raw(p));row['value'][1][1]['entries']=[[3,True]];p._state.execution.externals['HOST','MAKE']=lambda:row;before=payload(raw(p,'TARGET'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(payload(raw(p,'TARGET')),before)
    def test_shared_owned_queue_cells_reject(self):
        p,_=bank();raw(p).values[0]=raw(p).values[-1]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_array_storage_rejects(self):
        p,_=bank();raw(p).values=()
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_runtime_array_schema_rejects(self):
        p,_=bank();raw(p).spec=None
        with self.assertRaises(rt.KarelRuntimeError):p.run()

class ResultBoundaryTests(unittest.TestCase):
    def test_strict_helper_does_not_open_collection_results(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.external_collection_result(('QUEUE_TYPE',),rt.QueueValue(),7)
    def test_generic_queue_checked_remains_closed(self):
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.checked(('QUEUE_TYPE',),rt.QueueValue())
    def test_generic_queue_bank_result_remains_closed(self):
        with rt._numeric_scope('pythonic'):
            value=rt.Array(('ARRAY',1,('QUEUE_TYPE',)))
            with self.assertRaises(rt.KarelRuntimeError):rt.array_result(value.spec,value)
    def test_generic_file_result_stays_closed(self):
        with self.assertRaises(TranslationError):compile_program('f=make()',decl='f:FILE',routines='ROUTINE make:FILE FROM HOST')
    def test_ordinary_scalar_callback_rejects_mismatched_typed_json(self):
        p,_=compile_program('n=make()',routines='ROUTINE make:INTEGER FROM HOST',context=rt.ExecutionContext(externals={('HOST','MAKE'):lambda:dict(type=['BOOLEAN'],value=True)}))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_procedure_still_requires_none(self):
        p,_=compile_program('work()',routines='ROUTINE work FROM HOST',context=rt.ExecutionContext(externals={('HOST','WORK'):lambda:dict(type=['QUEUE_TYPE'],value={})}))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'return None'):p.run()
    def test_json_path_cost_rejects_before_decoder(self):
        p,_=make('path');row=payload(raw(p));row['value']['nodes']=[{}]*16384;p._state.execution.externals['HOST','MAKE']=lambda:row
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('allocated')) as decode,self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):p.run()
        decode.assert_not_called()
    def test_json_queue_duplicate_ids_reject(self):
        p,_=make('queue');row=payload(raw(p));row['value']['entries']=[[1,17],[1,9]];p._state.execution.externals['HOST','MAKE']=lambda:row
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_json_missing_marker_requires_true(self):
        p,_=make('path');row=payload(raw(p));row['value']['nodes'][0]['VALUE']={'uninitialized':1};p._state.execution.externals['HOST','MAKE']=lambda:row
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_json_cycles_fail_with_source_line(self):
        schema=['ARRAY',1,None];schema[2]=schema
        p,_=make('queue',result=lambda:dict(type=schema,value=[]))
        with self.assertRaises(rt.KarelRuntimeError) as error:p.run()
        self.assertIn('KAREL line',str(error.exception))
    def test_malformed_expected_schema_rejects(self):
        for spec in (None,(),('FILE',)):
            with self.subTest(spec=spec),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.external_collection_result(spec,{},7)
    def test_raw_path_subclass_rejects(self):
        class Derived(rt.PathValue):pass
        p,_=make('path');source=raw(p);p._state.execution.externals['HOST','MAKE']=lambda:Derived(source.spec)
        with self.assertRaises(rt.KarelRuntimeError):p.run()

class FixedCollectionBindingTests(unittest.TestCase):
    def config(self):return {'host':{'make':{'type':['QUEUE_TYPE'],'value':{'initialized':True,'sequence':3,'entries':[[2,17]]}}}}
    def test_prepare_case_insensitive_names(self):
        callbacks=rt.external_collection_callbacks(self.config());self.assertEqual(set(callbacks),{('HOST','MAKE')});self.assertEqual(callbacks['HOST','MAKE']()['value']['entries'],[[2,17]])
    def test_each_callback_result_is_independent(self):
        callback=rt.external_collection_callbacks(self.config())['HOST','MAKE'];a=callback();a['value']['entries'].clear();self.assertEqual(callback()['value']['entries'],[[2,17]])
    def test_config_changes_do_not_change_fixed_value(self):
        config=self.config();callback=rt.external_collection_callbacks(config)['HOST','MAKE'];config['host']['make']['value'].clear();self.assertEqual(callback()['value']['entries'],[[2,17]])
    def test_fixed_callbacks_leave_borrowed_arguments_unchanged(self):
        callback=rt.external_collection_callbacks(self.config())['HOST','MAKE'];storage={'value':17};reference=rt.Reference(rt.INTEGER,storage,'value');callback(reference);self.assertEqual(storage['value'],17)
    def test_normalized_duplicate_names_reject(self):
        config=self.config();config['HOST']={'MAKE':deepcopy(config['host']['make'])}
        with self.assertRaisesRegex(ValueError,'distinct'):rt.external_collection_callbacks(config)
    def test_invalid_names_reject(self):
        for config in ({'host.name':{'make':{}}},{'host':{'make()':{}}},{'host':{}},[],{}):
            with self.subTest(config=config),self.assertRaises(ValueError):rt.external_collection_callbacks(config)
    def test_scalar_and_file_fixed_bindings_reject(self):
        for spec in (['INTEGER'],['FILE'],['ARRAY',1,['FILE']]):
            with self.subTest(spec=spec),self.assertRaises(ValueError):rt.external_collection_callbacks({'HOST':{'MAKE':dict(type=spec,value=17)}})
    def test_all_bindings_validate_before_return(self):
        config=self.config();config['host']['later']={'type':['QUEUE_TYPE'],'value':{}}
        with self.assertRaises(ValueError):rt.external_collection_callbacks(config)
    def test_binding_limit(self):
        row=self.config()['host']['make'];config={'HOST':{f'MAKE_{n}':row for n in range(129)}}
        with self.assertRaisesRegex(ValueError,'128'):rt.external_collection_callbacks(config)
    def test_missing_binding_keys_reject(self):
        with self.assertRaises(ValueError):rt.external_collection_callbacks({'HOST':{'MAKE':{'type':['QUEUE_TYPE']}}})

class ExternalCollectionCLITests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        folder=tempfile.TemporaryDirectory(prefix='external_collections_');self.addCleanup(folder.cleanup);self.folder=Path(folder.name);self.script=self.folder/'converted.py';self.config=self.folder/'external.json';self.saved=self.folder/'state.json'
        self.config.write_bytes(json.dumps({'HOST':{'MAKE':{'type':['QUEUE_TYPE'],'value':{'initialized':True,'sequence':7,'entries':[[3,17],[1,9]]}}}}).encode())
        self.source='PROGRAM T VAR q:QUEUE_TYPE done:BOOLEAN ROUTINE make:QUEUE_TYPE FROM HOST BEGIN IF UNINIT(done) THEN q=make() done=TRUE ENDIF END T'
    def run_cli(self,*arguments,source=None,expected=0):
        import os,subprocess,sys
        from pathlib import Path
        from karel2py import translate
        self.script.write_bytes(translate(source or self.source).python_source.encode());environment=dict(os.environ);environment['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
        bootstrap="""import runpy,sys
class RuntimeOnly:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.project','tkinter','_tkinter','karel2py.gui','socket','ssl','http.client','urllib.request'):
   raise ImportError('Generated execution must use runtime only')
sys.meta_path.insert(0,RuntimeOnly());sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name='__main__')
"""
        result=subprocess.run([sys.executable,'-X','utf8','-c',bootstrap,str(self.script),*map(str,arguments)],cwd=self.folder,env=environment,capture_output=True,text=True)
        self.assertEqual(result.returncode,expected,result.stderr);return result
    def test_generated_cli_loads_fixed_queue_result(self):
        import ast
        result=self.run_cli('--external-collections',self.config,'--state-out',self.saved);self.assertEqual(ast.literal_eval(result.stdout)['Q']['entries'],[[3,17],[1,9]]);self.assertTrue(self.saved.exists())
    def test_generated_cli_replays_with_explicit_binding_file(self):
        self.run_cli('--external-collections',self.config,'--state-out',self.saved);first=json.loads(self.saved.read_text());again=self.folder/'replay.json';self.run_cli('--external-collections',self.config,'--context',self.saved,'--state-out',again);self.assertEqual(json.loads(again.read_text()),first)
    def test_malformed_json_rejects_before_execution(self):
        self.config.write_bytes(b'{');result=self.run_cli('--external-collections',self.config,'--state-out',self.saved,expected=2);self.assertIn('Invalid external collections',result.stderr);self.assertFalse(self.saved.exists())
    def test_duplicate_json_keys_reject(self):
        self.config.write_bytes(b'{"HOST":{},"HOST":{}}');result=self.run_cli('--external-collections',self.config,expected=2);self.assertIn('Duplicate',result.stderr)
    def test_nonfinite_json_rejects(self):
        self.config.write_bytes(b'{"HOST":{"MAKE":NaN}}');result=self.run_cli('--external-collections',self.config,expected=2);self.assertIn('Nonfinite',result.stderr)
    def test_utf8_bom_is_supported(self):
        self.config.write_bytes(b'\xef\xbb\xbf'+self.config.read_bytes());self.run_cli('--external-collections',self.config)
    def test_input_file_is_protected_from_state_output(self):
        before=self.config.read_bytes();self.run_cli('--external-collections',self.config,'--state-out',self.config,expected=2);self.assertEqual(self.config.read_bytes(),before)
    def test_input_hardlink_is_protected(self):
        import os
        alias=self.folder/'alias.json'
        try:os.link(self.config,alias)
        except OSError as error:self.skipTest(str(error))
        before=self.config.read_bytes();self.run_cli('--external-collections',self.config,'--state-out',alias,expected=2);self.assertEqual(self.config.read_bytes(),before)
    def test_fixed_return_must_match_source_declaration(self):
        self.run_cli('--external-collections',self.config,source=self.source.replace('q:QUEUE_TYPE','q:PATH').replace('make:QUEUE_TYPE','make:PATH'),expected=1)
    def test_project_cli_loads_fixed_result(self):
        import os,subprocess,sys
        from pathlib import Path
        (self.folder/'main.kl').write_bytes(self.source.replace('PROGRAM T','PROGRAM MAIN').replace('END T','END MAIN').encode());environment=dict(os.environ);environment['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
        result=subprocess.run([sys.executable,'-m','karel2py.project',str(self.folder),'--entry','MAIN','--external-collections',str(self.config),'--state-out',str(self.saved)],cwd=self.folder,env=environment,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['MAIN']['values']['Q']['entries'],[[3,17],[1,9]])
    def test_project_trace_cannot_overwrite_binding_file(self):
        import os,subprocess,sys
        from pathlib import Path
        (self.folder/'main.kl').write_bytes(self.source.replace('PROGRAM T','PROGRAM MAIN').replace('END T','END MAIN').encode());environment=dict(os.environ);environment['PYTHONPATH']=str(Path(__file__).resolve().parents[1]);before=self.config.read_bytes()
        result=subprocess.run([sys.executable,'-m','karel2py.project',str(self.folder),'--entry','MAIN','--external-collections',str(self.config),'--trace-out',str(self.config)],cwd=self.folder,env=environment,capture_output=True,text=True)
        self.assertEqual(result.returncode,2,result.stderr);self.assertEqual(self.config.read_bytes(),before)

class CallbackCompositionTests(unittest.TestCase):
    def test_private_path_header_using_result(self):
        p,_=make('path','USING make() DO visits=tag tag=99 ENDUSING');self.assertEqual(p.run()['VISITS'],7);self.assertEqual(raw(p).data.values['TAG'],7)
    def test_callback_queue_result_supports_entry_read(self):
        p,_=make('queue','target=make() READ(target)',encoded=True,read=lambda request:[42,43]);p.run();self.assertEqual(raw(p,'TARGET').entries,[(3,42),(1,43)]);self.assertEqual(raw(p).entries,[(3,17),(1,9)])
    def test_json_bank_cost_precedes_cell_allocation(self):
        p,_=bank(encoded=True);row=payload(raw(p));row['value'][1][1]['sequence']=16384;row['value'][1][1]['entries']=[[i+1,17] for i in range(16384)];p._state.execution.externals['HOST','MAKE']=lambda:row
        with patch('karel2py.storage.restore_collection',side_effect=AssertionError('allocated')) as restore,self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):p.run()
        restore.assert_not_called()
    def test_file_size_limit_precedes_json_decode(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'large.json';path.write_bytes(b' '*(4*1024*1024+1))
            with self.assertRaisesRegex(ValueError,'4 MiB'):rt.load_external_collections(path)
