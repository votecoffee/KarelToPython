"""Authored load-state, program attributes, activity guards and CLI cases."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError
from karel2py.inspection import any_initialized

ROOT=Path(__file__).resolve().parents[1]
DECL='loaded,initialized: BOOLEAN value,status,i: INTEGER text: STRING[128]'
RECORDS={'stored':{'loaded':True,'initialized':False,'attributes':{
    'AT_PROG_TYPE':rt.PROGRAM_CONSTANTS['PT_MNE_JOB'],'AT_OWNER':'team',
    'AT_COMMENT':'ready','AT_PROG_SIZE':400,'AT_SRC_VRSN':2}}}


def context(records=RECORDS):
    return rt.ExecutionContext(program_attributes=rt.ProgramAttributes(records))


def program(body='',name='OBSERVER',decl=DECL,context=None,prefix='',routines='',**options):
    result=translate(f'PROGRAM {name}\n{prefix}\nVAR {decl}\n{routines}\nBEGIN {body} END {name}')
    namespace={'__name__':'metadata_test'};exec(result.python_source,namespace)
    return namespace['Program'](context=context,**options),result


def run(body,**options): return program(body,**options)[0].run()


def get(attribute='AT_COMMENT',name='stored',**options):
    return run(f"value=7 text='prior' GET_ATTR_PRG('{name}',{attribute},value,text,status)",**options)


def put(attribute='AT_COMMENT',name='stored',**options):
    return run(f"SET_ATTR_PRG('{name}',{attribute},9,'updated',status)",**options)


class ProgramAttributesTests(unittest.TestCase):
    def test_names_flags_and_snapshots_are_detached(self):
        records=json.loads(json.dumps(RECORDS));service=rt.ProgramAttributes(records)
        records['stored']['attributes']['AT_OWNER']='changed'
        saved=service.to_config();saved['STORED']['attributes']['AT_OWNER']='changed'
        row=service.record('sToReD');row['attributes']['AT_OWNER']='changed'
        self.assertEqual(service.record('STORED')['attributes']['AT_OWNER'],'team')

    def test_invalid_names_and_duplicates(self):
        for name in ('','bad.name','1bad','x'*37,'é',1):
            with self.subTest(name=name),self.assertRaises(ValueError): rt.ProgramAttributes({name:{}})
        with self.assertRaises(ValueError): rt.ProgramAttributes({'a':{},'A':{}})

    def test_invalid_record_schema_and_flags(self):
        for row in (None,[],{'extra':1},{'loaded':1},{'initialized':0},{'active':'yes'},
                    {'active':True},{'attributes':[]},{'attributes':{'AT_OWNER':'x','at_owner':'y'}},
                    {'attributes':{'AT_PROG_NAME':'rename'}},{'attributes':{'unknown':0}}):
            with self.subTest(row=row),self.assertRaises(ValueError): rt.ProgramAttributes({'a':row})

    def test_invalid_attribute_values(self):
        for key,value in (('AT_OWNER','x'*9),('AT_COMMENT','é'),('AT_PROG_TYPE',6),
                          ('AT_PROTECT',0),('AT_BUSY_OFF',2),('AT_IGNR_ABRT',True),
                          ('AT_PROG_SIZE',-1),('AT_STK_SIZE',-2),('AT_SRC_VRSN',1.5),
                          ('AT_SRC_VRSN',2147483647)):
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                rt.ProgramAttributes({'a':{'attributes':{key:value}}})

    def test_json_save_reload_and_absent_service(self):
        ctx=context()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';ctx.save(path)
            self.assertEqual(rt.ExecutionContext.load(path).to_config(),ctx.to_config())
        self.assertNotIn('program_attributes',rt.ExecutionContext().to_config())
        self.assertEqual(context({}).to_config(),{'program_attributes':{}})

    def test_context_rejects_untyped_service_and_invalid_json(self):
        with self.assertRaises(TypeError): rt.ExecutionContext(program_attributes={})
        for value in (None,[],1):
            with self.subTest(value=value),self.assertRaises(ValueError):
                rt.ExecutionContext.from_config({'program_attributes':value})


class LoadStatusTests(unittest.TestCase):
    def test_unknown_invalid_and_routine_names_are_not_loaded(self):
        for name in ('absent','','file.pc','MD:NAME','1bad'):
            with self.subTest(name=name):
                state=run(f"LOAD_STATUS('{name}',loaded,initialized)",routines='ROUTINE absent BEGIN END absent')
                self.assertEqual((state['LOADED'],state['INITIALIZED']),(False,False))

    def test_constants_and_outputs_before_the_call_do_not_initialize_globals(self):
        state=run("LOAD_STATUS('observer',loaded,initialized)",prefix='CONST fixed=42')
        self.assertEqual((state['LOADED'],state['INITIALIZED']),(True,False))

    def test_previous_outputs_count_as_initialized_on_next_query(self):
        state=run("LOAD_STATUS('OBSERVER',loaded,initialized) LOAD_STATUS('OBSERVER',loaded,initialized)")
        self.assertTrue(state['INITIALIZED'])

    def test_explicit_flags_are_independent_and_do_not_infer_code(self):
        ctx=context({'data':{'initialized':True},'code':{'loaded':True},'meta':{'attributes':{'AT_OWNER':'team'}}})
        for name,expected in (('data',(False,True)),('code',(True,False)),('meta',(False,False))):
            with self.subTest(name=name):
                state=run(f"LOAD_STATUS('{name}',loaded,initialized)",context=ctx)
                self.assertEqual((state['LOADED'],state['INITIALIZED']),expected)

    def test_program_catalog_and_variable_bindings_do_not_load_code(self):
        ctx=rt.ExecutionContext(programs=rt.ProgramCatalog([{'name':'external','type':'PC'}]))
        ctx.variables.define('external','N',('INTEGER',),42)
        state=run("LOAD_STATUS('external',loaded,initialized)",context=ctx)
        self.assertEqual((state['LOADED'],state['INITIALIZED']),(False,False))

    def test_attached_empty_program_overrides_snapshot_flags(self):
        ctx=context({'worker':{'loaded':False,'initialized':True}})
        program(name='WORKER',decl='n: INTEGER',context=ctx)
        state=run("LOAD_STATUS('worker',loaded,initialized)",context=ctx)
        self.assertEqual((state['LOADED'],state['INITIALIZED']),(True,False))

    def test_partial_array_and_record_content_counts(self):
        cases=[('a: ARRAY[2,2] OF INTEGER','a[2,1]=0'),
               ('p: XYZWPREXT','p.x=0'),
               ('b: BOOLEAN','b=OFF'),('t: STRING[2]',"t=''"),('s: ARRAY[1] OF SHORT','s[1]=0')]
        for decl,body in cases:
            with self.subTest(decl=decl):
                ctx=context({});worker,_=program(name='WORKER',decl=decl,body=body,context=ctx);worker.run()
                state=run("LOAD_STATUS('worker',loaded,initialized)",context=ctx)
                self.assertEqual((state['LOADED'],state['INITIALIZED']),(True,True))

    def test_unknown_byte_and_short_sentinel_do_not_count(self):
        ctx=context({});worker,_=program(name='WORKER',decl='b: ARRAY[1] OF BYTE s: ARRAY[1] OF SHORT',body='s[1]=32767',context=ctx);worker.run()
        state=run("LOAD_STATUS('worker',loaded,initialized)",context=ctx)
        self.assertFalse(state['INITIALIZED'])

    def test_partial_joint_axes_count_without_exposing_source_joint_indexes(self):
        ctx=context({});worker,_=program(name='WORKER',decl='j:JOINTPOS3',context=ctx)
        worker._state.values['J'].values[1]=0.
        self.assertTrue(run("LOAD_STATUS('worker',loaded,initialized)",context=ctx)['INITIALIZED'])

    def test_local_variables_do_not_count_as_global_data(self):
        state=run('probe',routines="ROUTINE probe VAR local:INTEGER BEGIN local=1 LOAD_STATUS('OBSERVER',loaded,initialized) END probe")
        self.assertFalse(state['INITIALIZED'])

    def test_imported_global_reference_counts(self):
        sources={'lib':"PROGRAM LIB VAR n:INTEGER BEGIN n=0 END LIB",
                 'main':"PROGRAM MAIN VAR n FROM LIB:INTEGER a,b:BOOLEAN BEGIN n=0 LOAD_STATUS('MAIN',a,b) END MAIN"}
        instance=translate_project(sources).instantiate();instance.run('MAIN')
        self.assertTrue(instance.programs['MAIN'].snapshot()['B'])

    def test_all_branches_validate_before_outputs(self):
        ctx=context({});worker,_=program(name='WORKER',decl='a:ARRAY[2] OF INTEGER',context=ctx)
        worker._state.values['A'].values[:]=[0,'invalid']
        observer,_=program("loaded=OFF initialized=OFF LOAD_STATUS('WORKER',loaded,initialized)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): observer.run()
        self.assertEqual((observer.snapshot()['LOADED'],observer.snapshot()['INITIALIZED']),(False,False))

    def test_host_reference_cycle_is_rejected(self):
        spec=('INTEGER',);storage={};reference=rt.Reference(spec,storage,'x');storage['x']=reference
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cyclic'): any_initialized(reference,spec)

    def test_resource_conventions(self):
        path=rt.PathValue(('PATH',None,None));queue=rt.QueueValue();handle=rt.FileHandle()
        self.assertFalse(any_initialized(path,path.spec));path.append()
        self.assertTrue(any_initialized(path,path.spec))
        self.assertFalse(any_initialized(queue,queue.spec));queue.initialized=True
        self.assertTrue(any_initialized(queue,queue.spec))
        self.assertFalse(any_initialized(handle,('FILE',)));handle.owner=rt.MemoryFiles()
        self.assertTrue(any_initialized(handle,('FILE',)))


class AttributeQueryTests(unittest.TestCase):
    def test_explicit_numeric_and_text_attributes_preserve_unused_output(self):
        for attribute,expected in (('AT_COMMENT',(7,'ready')),('AT_PROG_SIZE',(400,'prior')),
                                   ('AT_PROG_TYPE',(rt.PROGRAM_CONSTANTS['PT_MNE_JOB'],'prior'))):
            with self.subTest(attribute=attribute):
                state=get(attribute,context=context());self.assertEqual((state['VALUE'],state['TEXT']),expected)
                self.assertEqual(state['STATUS'],0)

    def test_attached_identity_type_and_source_comment(self):
        ctx=context({'worker':{'attributes':{'AT_PROG_TYPE':rt.PROGRAM_CONSTANTS['PT_MNE_JOB']}}})
        program(name='WORKER',context=ctx,prefix="%COMMENT='source comment'")
        self.assertEqual(get('AT_PROG_TYPE','worker',context=ctx)['VALUE'],rt.PROGRAM_CONSTANTS['PT_KRLPRG'])
        self.assertEqual(get('AT_PROG_NAME','worker',context=ctx)['TEXT'],'WORKER')
        self.assertEqual(get('AT_COMMENT','worker',context=ctx)['TEXT'],'source comment')

    def test_missing_metadata_never_guesses_size_time_or_task_settings(self):
        for attribute in ('AT_PROG_SIZE','AT_CRE_TIME','AT_TASK_PRI'):
            with self.subTest(attribute=attribute):
                state=get(attribute,'OBSERVER')
                self.assertEqual((state['VALUE'],state['TEXT'],state['STATUS']),(7,'prior',3))

    def test_unknown_program_and_selector_preserve_values(self):
        for attribute,name,status in (('AT_COMMENT','absent',1),('999','stored',2)):
            with self.subTest(attribute=attribute):
                state=get(attribute,name,context=context())
                self.assertEqual((state['VALUE'],state['TEXT'],state['STATUS']),(7,'prior',status))

    def test_name_and_output_capacity_truncate(self):
        ctx=context({'LONG_PROGRAM_NAME':{}})
        self.assertEqual(get('AT_PROG_NAME','LONG_PROGRAM_NAME',context=ctx)['TEXT'],'LONG_PROGRAM')
        state=run("GET_ATTR_PRG('stored',AT_COMMENT,value,text,status)",decl=DECL.replace('STRING[128]','STRING[2]'),context=context())
        self.assertEqual(state['TEXT'],'re')

    def test_unselected_output_can_stay_uninitialized(self):
        state=run("GET_ATTR_PRG('stored',AT_OWNER,value,text,status)",context=context())
        self.assertEqual(state['VALUE'],{'uninitialized':True})


class AttributeWriteTests(unittest.TestCase):
    def test_four_writable_metadata_fields_roundtrip(self):
        for attribute in ('AT_OWNER','AT_COMMENT','AT_SRC_NAME','AT_SRC_VRSN'):
            with self.subTest(attribute=attribute):
                ctx=context();self.assertEqual(put(attribute,context=ctx)['STATUS'],0)
                state=get(attribute,context=ctx)
                self.assertEqual(state['VALUE'] if attribute=='AT_SRC_VRSN' else state['TEXT'],9 if attribute=='AT_SRC_VRSN' else 'updated')

    def test_metadata_strings_use_documented_capacity(self):
        ctx=context();state=run("SET_ATTR_PRG('stored',AT_OWNER,0,'123456789',status)",context=ctx)
        self.assertEqual((state['STATUS'],ctx.program_attributes.record('stored')['attributes']['AT_OWNER']),(0,'12345678'))

    def test_readonly_identity_and_task_policy_writes_are_rejected(self):
        ctx=context();before=ctx.program_attributes.to_config()
        for attribute in ('AT_PROG_NAME','AT_PROG_SIZE','AT_TASK_PRI','AT_PROTECT','AT_STORAGE','AT_CONTROL','999'):
            with self.subTest(attribute=attribute): self.assertEqual(put(attribute,context=ctx)['STATUS'],2)
        self.assertEqual(ctx.program_attributes.to_config(),before)

    def test_unknown_program_does_not_create_record(self):
        ctx=context({});self.assertEqual(put(name='absent',context=ctx)['STATUS'],1)
        self.assertEqual(ctx.program_attributes.to_config(),{})

    def test_current_program_cannot_write_own_metadata(self):
        ctx=context({});self.assertEqual(put(name='OBSERVER',context=ctx)['STATUS'],4)
        self.assertEqual(ctx.program_attributes.to_config(),{})

    def test_explicit_active_snapshot_blocks_write(self):
        ctx=context({'stored':{'loaded':True,'active':True}})
        self.assertEqual(put(context=ctx)['STATUS'],4)

    def test_paused_target_blocks_until_stopped(self):
        ctx=context({});worker,_=program('PAUSE',name='WORKER',context=ctx)
        with self.assertRaises(rt.KarelPause): worker.run()
        self.assertEqual(put(name='worker',context=ctx)['STATUS'],4)
        worker.stop();self.assertEqual(put(name='worker',context=ctx)['STATUS'],0)

    def test_completed_target_and_empty_service_allow_metadata_creation(self):
        ctx=context({});worker,_=program('value=1',name='WORKER',context=ctx);worker.run()
        self.assertEqual(put(name='worker',context=ctx)['STATUS'],0)
        self.assertNotIn('loaded',ctx.program_attributes.record('worker'))

    def test_plain_running_target_is_guarded_inside_host_callback(self):
        ctx=context({});statuses=[]
        worker,_=program("WRITE('checkpoint')",name='WORKER',context=ctx,
                         write=lambda text: statuses.append(put(name='worker',context=ctx)['STATUS']))
        worker.run();self.assertEqual(statuses,[4]);self.assertFalse(worker._state._driving)
        self.assertEqual(put(name='worker',context=ctx)['STATUS'],0)

    def test_plain_activity_guard_cleans_up_after_failure_and_blocks_reentry(self):
        ctx=context({});holder={}
        worker,_=program("WRITE('checkpoint')",name='OTHER',context=ctx,write=lambda text:holder['worker'].run())
        holder['worker']=worker
        with self.assertRaisesRegex(rt.KarelRuntimeError,'recursively'): worker.run()
        self.assertFalse(worker._state._driving)
        self.assertEqual(put(name='OTHER',context=ctx)['STATUS'],0)

    def test_active_linked_routine_cannot_change_its_program(self):
        sources={'lib':"PROGRAM LIB ROUTINE mark(code:INTEGER) BEGIN SET_ATTR_PRG('LIB',AT_COMMENT,0,'bad',code) END mark BEGIN END LIB",
                 'main':"PROGRAM MAIN VAR s:INTEGER ROUTINE mark(code:INTEGER) FROM LIB BEGIN mark(s) END MAIN"}
        instance=translate_project(sources).instantiate(context=context({}));instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].snapshot()['S'],4)

    def test_missing_write_service_raises_without_status_change(self):
        ctx=rt.ExecutionContext();program(name='WORKER',context=ctx)
        observer,_=program("status=8 SET_ATTR_PRG('WORKER',AT_OWNER,0,'a',status)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ProgramAttributes'): observer.run()
        self.assertEqual(observer.snapshot()['STATUS'],8)

    def test_both_value_inputs_are_captured_and_checked(self):
        ctx=context();observer,_=program("status=8 SET_ATTR_PRG('stored',AT_COMMENT,value,'new',status)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): observer.run()
        self.assertEqual(observer.snapshot()['STATUS'],8)
        self.assertEqual(ctx.program_attributes.record('stored')['attributes']['AT_COMMENT'],'ready')


class MetadataIntegrationTests(unittest.TestCase):
    def test_output_aliases_raise_before_output_writes(self):
        for body in ("LOAD_STATUS('stored',loaded,loaded)",
                     "GET_ATTR_PRG('stored',AT_SRC_VRSN,value,text,value)"):
            with self.subTest(body=body):
                observer,_=program(body,context=context())
                with self.assertRaises(rt.KarelRuntimeError): observer.run()
                self.assertEqual(observer.snapshot()['VALUE'],{'uninitialized':True})

    def test_active_counter_guards_include_transitive_calls(self):
        for body,routines in (("FOR i=1 TO 2 DO SET_ATTR_PRG('stored',AT_OWNER,0,'x',i) ENDFOR",''),
                ('FOR i=1 TO 2 DO mutate ENDFOR',"ROUTINE mutate BEGIN GET_ATTR_PRG('stored',AT_SRC_VRSN,i,text,status) END mutate")):
            with self.subTest(body=body),self.assertRaises(TranslationError): program(body,routines=routines)

    def test_argument_effects_run_once_in_source_order(self):
        ctx=context()
        routines="""ROUTINE who:STRING BEGIN i=i*10+1 RETURN 'stored' END who
ROUTINE attribute:INTEGER BEGIN i=i*10+2 RETURN AT_SRC_VRSN END attribute
ROUTINE number:INTEGER BEGIN i=i*10+3 RETURN 42 END number
ROUTINE label:STRING BEGIN i=i*10+4 RETURN 'ignored' END label
ROUTINE slot:INTEGER BEGIN i=i*10+5 RETURN 1 END slot"""
        state=run('i=0 SET_ATTR_PRG(who,attribute,number,label,codes[slot])',
                  decl=DECL+' codes:ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        self.assertEqual((state['I'],state['CODES']),(12345,[0]))
        self.assertEqual(ctx.program_attributes.record('stored')['attributes']['AT_SRC_VRSN'],42)

    def test_internal_routine_precedence(self):
        state=run('LOAD_STATUS(value)',routines='ROUTINE LOAD_STATUS(x:INTEGER) BEGIN x=42 END LOAD_STATUS')
        self.assertEqual(state['VALUE'],42)

    def test_reports_have_source_operations_and_portable_policy(self):
        _,result=program("LOAD_STATUS('stored',loaded,initialized) GET_ATTR_PRG('stored',AT_OWNER,value,text,status)")
        self.assertEqual({row['operation'] for row in result.report['service_operations']},{'LOAD_STATUS','GET_ATTR_PRG'})
        self.assertFalse(result.report['program_metadata_policy']['controller_validated'])

    def test_fresh_cli_translation_execution_and_saved_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'converted.py';report=Path(folder)/'report.json';state=Path(folder)/'state.json'
            env={**__import__('os').environ,'PYTHONPATH':str(ROOT)}
            command=[sys.executable,'-X','utf8','-m','karel2py',str(ROOT/'examples/program_metadata.kl'),'-o',str(output),'--report',str(report)]
            result=subprocess.run(command,cwd=folder,capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([sys.executable,'-X','utf8',str(output),'--context',str(ROOT/'examples/program_metadata.services.initial.json'),'--state-out',str(state)],cwd=folder,capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(ast.literal_eval(result.stdout),json.loads((ROOT/'examples/program_metadata.expected.json').read_text()))
            self.assertEqual(json.loads(state.read_text())['program_attributes']['STORED']['attributes']['AT_COMMENT'],'converted')
            self.assertIn('program_metadata_policy',json.loads(report.read_text()))
