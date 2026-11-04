"""Explicit offline predefined FILE bindings, defaults and owned lifetimes."""
import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path
from karel2py import runtime as rt,translate,translate_project
from karel2py.extended import PREDEFINED_FILE_NAMES
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_pipe_attributes import bank as pipe_bank
from tests.test_keyboard import context as keyboard_context

DECL='n,m,s,i,count,key:INTEGER text:STRING[16] flag,done:BOOLEAN f:FILE'


def binding(name='data',mode='RO',**attributes):
    row=dict(name=name,mode=mode)
    if attributes:row['attributes']=attributes
    return row


def context(initial=None,bindings=None):
    return rt.ExecutionContext(files=rt.MemoryFiles({'data':'7\n'} if initial is None else initial),predefined_files={'TPDISPLAY':binding()} if bindings is None else bindings)


def build(body,ctx=None,**options):return compile_program(body,decl=options.pop('decl',DECL),context=context() if ctx is None else ctx,**options)


def execute(body,ctx=None,**options):
    p,r=build(body,ctx,**options);return p.run(),p._state.execution,p,r


class PredefinedConfigurationTests(unittest.TestCase):
    def test_empty_bindings_preserve_empty_context(self):self.assertEqual(rt.ExecutionContext().predefined_files,{})
    def test_all_documented_names_are_accepted(self):self.assertEqual(set(rt.ExecutionContext(predefined_files={n:binding() for n in PREDEFINED_FILE_NAMES}).predefined_files),set(PREDEFINED_FILE_NAMES))
    def test_keys_and_modes_are_case_insensitive(self):self.assertEqual(rt.ExecutionContext(predefined_files={'tpdisplay':binding(mode='ro')}).predefined_files,{'TPDISPLAY':binding()})
    def test_bindings_are_detached_from_input(self):
        data={'TPDISPLAY':binding(binary=True)};ctx=rt.ExecutionContext(predefined_files=data);data['TPDISPLAY']['attributes']['binary']=False;self.assertTrue(ctx.predefined_files['TPDISPLAY']['attributes']['binary'])
    def test_binding_property_is_defensive(self):
        ctx=context();ctx.predefined_files['TPDISPLAY']['name']='other';self.assertEqual(ctx.predefined_files['TPDISPLAY']['name'],'data')
    def test_construction_does_not_open_or_create_files(self):
        ctx=context(initial={},bindings={'TPDISPLAY':binding('new','WO')});self.assertEqual((ctx.files.files,ctx.files.handles,ctx._predefined_values),({},[],{}))
    def test_unknown_alias_rejected(self):
        with self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'CUSTOM':binding()})
    def test_case_duplicate_rejected(self):
        with self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':binding(),'input':binding()})
    def test_nonascii_alias_rejected(self):
        with self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'ınput':binding()})
    def test_mapping_required(self):
        with self.assertRaises(ValueError):rt.ExecutionContext(predefined_files=[])
    def test_row_mapping_required(self):
        with self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':'data'})
    def test_row_requires_name(self):
        with self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':dict(mode='RO')})
    def test_row_requires_mode(self):
        with self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':dict(name='data')})
    def test_unknown_row_field_rejected(self):
        with self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':dict(name='data',mode='RO',path='other')})
    def test_invalid_modes_rejected(self):
        for mode in ('','READ','RWB',7,True):
            with self.subTest(mode=mode),self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':binding(mode=mode)})
    def test_invalid_names_rejected(self):
        for name in ('','é','x'*255,7):
            with self.subTest(name=name),self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':binding(name=name)})
    def test_unknown_attributes_rejected(self):
        with self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':binding(custom=True)})
    def test_boolean_attribute_types_checked(self):
        for attr in ('binary','reverse','field','xml','passall','noecho','interactive'):
            with self.subTest(attr=attr),self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':binding(**{attr:1})})
    def test_eol_domain_checked(self):
        for value in (-1,128,True):
            with self.subTest(value=value),self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':binding(eol=value)})
    def test_pipe_attribute_domains_checked(self):
        for attrs in (dict(pipe_wait=2),dict(pipe_wait=True),dict(pipe_overflow=-2),dict(pipe_overflow=True)):
            with self.subTest(attrs=attrs),self.assertRaises(ValueError):rt.ExecutionContext(predefined_files={'INPUT':binding(**attrs)})
    def test_json_null_is_rejected(self):
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config({'predefined_files':None})
    def test_json_unknown_field_still_rejected(self):
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config({'predefined_files':{},'implicit_device':True})
    def test_json_binding_roundtrip_is_lazy(self):
        ctx=rt.ExecutionContext.from_config({'predefined_files':{'input':binding('P2:')}});saved=ctx.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(saved)));self.assertEqual(restored.to_config(),saved);self.assertEqual(restored._predefined_values,{})


class PredefinedSourceTests(unittest.TestCase):
    def test_explicit_read_and_status(self):
        v,ctx,_,_=execute('READ TPDISPLAY(n,CR) s=IO_STATUS(TPDISPLAY) CLOSE FILE TPDISPLAY');self.assertEqual((v['N'],v['S']),(7,0));self.assertEqual(ctx.files.handles,[])
    def test_default_read(self):self.assertEqual(execute('READ(n,CR) CLOSE FILE TPDISPLAY')[0]['N'],7)
    def test_explicit_output(self):
        ctx=context(initial={},bindings={'OUTPUT':binding('out','WO')});execute("WRITE OUTPUT(7,CR) CLOSE FILE OUTPUT",ctx);self.assertEqual(bytes(ctx.files.files['out']),b' 7\n')
    def test_default_output(self):
        ctx=context(initial={},bindings={'TPDISPLAY':binding('out','WO')});execute("WRITE('ready',CR) CLOSE FILE TPDISPLAY",ctx);self.assertEqual(bytes(ctx.files.files['out']),b'ready\n')
    def test_crt_defaults_use_input_and_output(self):
        ctx=context(bindings={'INPUT':binding(),'OUTPUT':binding('out','WO')});v,_,_,_=execute("READ(n,CR) WRITE(n,CR) CLOSE FILE INPUT CLOSE FILE OUTPUT",ctx,prefix='%CRTDEVICE');self.assertEqual(v['N'],7);self.assertEqual(bytes(ctx.files.files['out']),b' 7\n')
    def test_crt_binding_does_not_fall_back_to_tpdisplay(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'input callback'):execute('READ(n)',context(),prefix='%CRTDEVICE')
    def test_explicit_alias_does_not_use_crt_default(self):self.assertEqual(execute('READ TPDISPLAY(n) CLOSE FILE TPDISPLAY',prefix='%CRTDEVICE')[0]['N'],7)
    def test_unbound_default_read_preserves_callback(self):
        calls=[];ctx=context(bindings={});v,_,_,_=execute('READ(n)',ctx,read=lambda request:calls.append(request) or [9]);self.assertEqual(v['N'],9);self.assertEqual(len(calls),1)
    def test_unbound_default_write_preserves_callback(self):
        written=[];execute("WRITE('ready',CR)",context(bindings={}),write=written.append);self.assertEqual(written,['ready\n'])
    def test_bound_default_read_does_not_call_callback(self):
        def forbidden(_):raise AssertionError('Unexpected callback')
        self.assertEqual(execute('READ(n) CLOSE FILE TPDISPLAY',read=forbidden)[0]['N'],7)
    def test_bound_default_write_does_not_call_callback(self):
        def forbidden(_):raise AssertionError('Unexpected callback')
        ctx=context(initial={},bindings={'TPDISPLAY':binding('out','WO')});execute("WRITE('ready') CLOSE FILE TPDISPLAY",ctx,write=forbidden)
    def test_explicit_unconfigured_alias_fails(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit binding: INPUT'):execute('READ INPUT(n)',context(bindings={}))
    def test_ordinary_declared_input_name_keeps_its_type(self):self.assertEqual(execute('input=7 n=input',decl='input,n:INTEGER')[0]['N'],7)
    def test_ordinary_local_output_name_keeps_its_type(self):self.assertEqual(execute('work',routines='ROUTINE work VAR output:INTEGER BEGIN output=7 n=output END work')[0]['N'],7)
    def test_constant_input_name_keeps_its_value(self):self.assertEqual(execute('n=input',prefix='CONST input=7')[0]['N'],7)
    def test_declared_file_with_standard_name_keeps_its_handle(self):
        v,ctx,_,_=execute("OPEN FILE input('RO','data') READ input(n) CLOSE FILE input",decl=DECL+' input:FILE');self.assertEqual(v['N'],7);self.assertEqual(ctx._predefined_values,{})
    def test_predefined_open_is_not_a_retarget_operation(self):
        with self.assertRaises(TranslationError) as e:build("OPEN FILE TPDISPLAY('RO','other')")
        self.assertEqual(e.exception.code,'E_PREDEFINED_FILE_OPEN')
    def test_alias_passes_same_file_to_routine(self):self.assertEqual(execute('work(TPDISPLAY) CLOSE FILE TPDISPLAY',routines='ROUTINE work(h:FILE) BEGIN READ h(n) END work')[0]['N'],7)
    def test_repeated_alias_keeps_cursor(self):self.assertEqual(execute('READ TPDISPLAY(n) READ TPDISPLAY(m) CLOSE FILE TPDISPLAY',context(initial={'data':'7 8'}))[0]['M'],8)
    def test_scalar_formats_use_bound_file(self):self.assertEqual(execute('READ(n::2) CLOSE FILE TPDISPLAY',context(initial={'data':'07'}))[0]['N'],7)
    def test_aggregate_read_uses_bound_file(self):self.assertEqual(execute('READ(a) n=a[2] CLOSE FILE TPDISPLAY',context(initial={'data':'7 8'}),decl=DECL+' a:ARRAY[2]OF INTEGER')[0]['N'],8)
    def test_aggregate_write_uses_bound_file(self):
        ctx=context(initial={},bindings={'TPDISPLAY':binding('out','WO')});execute('a[1]=7 a[2]=8 WRITE(a) CLOSE FILE TPDISPLAY',ctx,decl=DECL+' a:ARRAY[2]OF INTEGER');self.assertEqual(bytes(ctx.files.files['out']),b' 7 8')
    def test_uninit_uses_open_state(self):
        v,_,_,_=execute('flag=UNINIT(TPDISPLAY) CLOSE FILE TPDISPLAY done=UNINIT(TPDISPLAY)');self.assertEqual((v['FLAG'],v['DONE']),(False,True))
    def test_status_can_be_cleared_after_close(self):self.assertEqual(execute('CLOSE FILE TPDISPLAY CLR_IO_STAT(TPDISPLAY) s=IO_STATUS(TPDISPLAY)')[0]['S'],0)
    def test_closed_alias_does_not_implicitly_reopen(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'open'):execute('CLOSE FILE TPDISPLAY READ TPDISPLAY(n)')
    def test_aliases_are_not_global_variable_data(self):
        _,ctx,p,_=execute('READ(n) CLOSE FILE TPDISPLAY');self.assertNotIn('TPDISPLAY',p.snapshot());self.assertFalse(any(row['path']=='TPDISPLAY' for row in ctx.to_config()['variables']))


class PredefinedBackendTests(unittest.TestCase):
    def test_binary_input(self):self.assertEqual(execute('READ(n) CLOSE FILE TPDISPLAY',context(initial={'data':struct.pack('<i',7)},bindings={'TPDISPLAY':binding(binary=True)}))[0]['N'],7)
    def test_binary_output(self):
        ctx=context(initial={},bindings={'TPDISPLAY':binding('out','WO',binary=True)});execute('WRITE(7) CLOSE FILE TPDISPLAY',ctx);self.assertEqual(bytes(ctx.files.files['out']),struct.pack('<i',7))
    def test_reverse_binary_input(self):self.assertEqual(execute('READ(n) CLOSE FILE TPDISPLAY',context(initial={'data':struct.pack('>i',7)},bindings={'TPDISPLAY':binding(binary=True,reverse=True)}))[0]['N'],7)
    def test_eol_output(self):
        ctx=context(initial={},bindings={'TPDISPLAY':binding('out','WO',eol=13)});execute("WRITE('ready',CR) CLOSE FILE TPDISPLAY",ctx);self.assertEqual(bytes(ctx.files.files['out']),b'ready\r')
    def test_memory_append(self):
        ctx=context(initial={'data':'seed'},bindings={'TPDISPLAY':binding(mode='AP')});execute("WRITE('more') CLOSE FILE TPDISPLAY",ctx);self.assertEqual(bytes(ctx.files.files['data']),b'seedmore')
    def test_rooted_directory_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            ctx=rt.ExecutionContext(files=rt.DirectoryFiles(directory),predefined_files={'OUTPUT':binding('out','WO')});execute("WRITE OUTPUT('ready') CLOSE FILE OUTPUT",ctx);self.assertEqual((Path(directory)/'out').read_bytes(),b'ready')
    def test_missing_service_does_not_create_one(self):
        ctx=rt.ExecutionContext(predefined_files={'TPDISPLAY':binding()})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'files service'):execute('READ(n)',ctx)
        self.assertIsNone(ctx.files);self.assertEqual(ctx._predefined_values,{})
    def test_serial_finite_input(self):
        bank=rt.SerialStreams({2:dict(input=b'7\n')});ctx=rt.ExecutionContext(serial_streams=bank,predefined_files={'TPDISPLAY':binding('P2:')});self.assertEqual(execute('READ TPDISPLAY(n,CR) CLOSE FILE TPDISPLAY',ctx)[0]['N'],7)
    def test_pipe_snapshot_input(self):
        pipes=pipe_bank(b'7\n');ctx=rt.ExecutionContext(file_pipes=pipes,predefined_files={'TPDISPLAY':binding('PIP:LOG',pipe_wait=0)});self.assertEqual(execute('READ TPDISPLAY(n,CR) CLOSE FILE TPDISPLAY',ctx)[0]['N'],7)
    def test_keyboard_typed_input(self):
        ctx=keyboard_context(keys=['7','ENTER']);ctx=rt.ExecutionContext(keyboard=ctx.keyboard,pendant=ctx.pendant,predefined_files={'TPDISPLAY':binding('KB:TPKB','RW')});self.assertEqual(execute('READ TPDISPLAY(n,CR) CLOSE FILE TPDISPLAY',ctx)[0]['N'],7)
    def test_default_keyboard_uses_cooperative_option(self):
        ctx=keyboard_context(keys=['7','ENTER']);ctx=rt.ExecutionContext(keyboard=ctx.keyboard,pendant=ctx.pendant,predefined_files={'TPDISPLAY':binding('KB:TPKB','RW')});self.assertEqual(execute('READ(n,CR) CLOSE FILE TPDISPLAY',ctx,cooperative=True)[0]['N'],7)
    def test_read_kb_uses_predefined_file_argument(self):
        ctx=keyboard_context(keys=['a','ENTER']);ctx=rt.ExecutionContext(keyboard=ctx.keyboard,pendant=ctx.pendant,predefined_files={'TPDISPLAY':binding('KB:TPKB','RW')});v,_,_,_=execute("READ_KB(TPDISPLAY,text,16,KC_DISPLAY,KC_ENTER_KEY,0,'',count,key,s) CLOSE FILE TPDISPLAY",ctx);self.assertEqual((v['TEXT'],v['S']),('a',0))


class PredefinedLifetimeTests(unittest.TestCase):
    def test_live_handle_prevents_save(self):
        _,ctx,_,_=execute('READ(n)')
        with self.assertRaisesRegex(ValueError,'Close predefined'):ctx.to_config()
        ctx.close_predefined_files();self.assertIn('predefined_files',ctx.to_config())
    def test_closed_context_replays_binding_intent_only(self):
        _,ctx,_,_=execute('READ(n) CLOSE FILE TPDISPLAY');saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved);self.assertEqual(restored._predefined_values,{});self.assertEqual(execute('READ(n) CLOSE FILE TPDISPLAY',restored)[0]['N'],7)
    def test_cleanup_does_not_close_ordinary_file(self):
        _,ctx,p,_=execute("OPEN FILE f('RO','other') READ(n)",context(initial={'data':'7','other':'8'}));ctx.close_predefined_files();self.assertIs(p._state.values['F'].owner,ctx.files);ctx.files.close(p._state.values['F'])
    def test_cleanup_is_idempotent(self):
        _,ctx,_,_=execute('READ(n)');ctx.close_predefined_files();ctx.close_predefined_files();self.assertEqual((ctx._predefined_values,ctx.files.handles),({},[]))
    def test_cleanup_allows_fresh_open_on_next_use(self):
        _,ctx,_,_=execute('READ(n)');old=ctx._predefined_values['TPDISPLAY'];ctx.close_predefined_files();self.assertEqual(execute('READ(n) CLOSE FILE TPDISPLAY',ctx)[0]['N'],7);self.assertIsNot(old,ctx._predefined_values['TPDISPLAY'])
    def test_foreign_cache_replacement_is_retained(self):
        _,ctx,p,_=execute('READ(n)');h=ctx._predefined_values['TPDISPLAY'];fake=copy.copy(h);ctx._predefined_values['TPDISPLAY']=fake
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cache identity'):ctx.close_predefined_files()
        self.assertIs(ctx._predefined_values['TPDISPLAY'],fake);self.assertIs(h.owner,ctx.files);ctx._predefined_values['TPDISPLAY']=h;ctx.close_predefined_files()
    def test_changed_endpoint_is_retained_for_recovery(self):
        _,ctx,_,_=execute('READ(n)');h=ctx._predefined_values['TPDISPLAY'];h.name='other'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'backend identity'):ctx.close_predefined_files()
        self.assertIs(h.owner,ctx.files);h.name='data';ctx.close_predefined_files()
    def test_missing_registration_is_not_hidden_by_cleanup(self):
        _,ctx,_,_=execute('READ(n)');h=ctx._predefined_values['TPDISPLAY'];ctx.files.handles.remove(h)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'registration'):ctx.close_predefined_files()
        self.assertIs(h.owner,ctx.files);ctx.files.handles.append(h);ctx.close_predefined_files()
    def test_failed_open_does_not_cache_a_closed_handle(self):
        ctx=context(initial={})
        with self.assertRaises(rt.KarelRuntimeError):execute('READ(n)',ctx)
        self.assertEqual(ctx._predefined_values,{});ctx.files.files['data']=bytearray(b'7');self.assertEqual(execute('READ(n) CLOSE FILE TPDISPLAY',ctx)[0]['N'],7)
    def test_aliases_share_existing_busy_file_guard(self):
        ctx=context(bindings={'TPDISPLAY':binding(),'INPUT':binding()})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already open'):execute('READ TPDISPLAY(n) READ INPUT(m)',ctx)
        self.assertEqual(set(ctx._predefined_values),{'TPDISPLAY'});ctx.close_predefined_files()
    def test_linked_routine_uses_shared_context_alias(self):
        main='PROGRAM MAIN VAR n:INTEGER ROUTINE work(x:INTEGER) FROM LIB BEGIN work(n) CLOSE FILE TPDISPLAY END MAIN'
        lib='PROGRAM LIB ROUTINE work(x:INTEGER) BEGIN READ TPDISPLAY(x) END work BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate(context=context());self.assertEqual(project.run('MAIN')['MAIN']['values']['N'],7)
    def test_borrowed_alias_can_be_closed_by_callee(self):
        _,ctx,_,_=execute('work(TPDISPLAY)',routines='ROUTINE work(h:FILE) BEGIN READ h(n) CLOSE FILE h END work');self.assertEqual(ctx.files.handles,[]);ctx.to_config()
    def test_budget_failure_does_not_open_default_endpoint(self):
        p,_=build('n=0 READ(n)')
        with self.assertRaises(rt.KarelRuntimeError):p.run(max_steps=1)
        self.assertEqual(p._state.execution._predefined_values,{})


def pending(ctx,*,body='n=77 READ(n,CR) s=IO_STATUS(TPDISPLAY) CLOSE FILE TPDISPLAY done=TRUE',prefix='',keyboard=False):
    document='PROGRAM MAIN\n'+prefix+'\nVAR '+DECL+' BEGIN '+body+' END MAIN'
    project=translate_project({'main':document}).instantiate(context=ctx);project.scheduler.start('MAIN');task=project.programs['MAIN']
    for _ in range(80):
        project.scheduler.step()
        for handle in ctx._predefined_values.values():
            if handle._read_operation is not None or keyboard and ctx.keyboard._active:return project,task,handle
    raise AssertionError('Predefined read did not become pending')


def waiting_serial(bindings=None):
    bank=rt.SerialStreams({2:dict(input=b'7',wait=True)})
    return rt.ExecutionContext(serial_streams=bank,predefined_files={'TPDISPLAY':binding('P2:')} if bindings is None else bindings)


class PredefinedCancellationTests(unittest.TestCase):
    def test_bare_cancel_cancels_default_typed_read(self):
        ctx=waiting_serial();project,p,h=pending(ctx);execute('CANCEL FILE',ctx);project.scheduler.run();self.assertEqual((p.snapshot()['N'],p.snapshot()['S'],p.task_state),(77,6,'completed'));self.assertEqual(p.read_requests,())
    def test_explicit_alias_cancels_default_typed_read(self):
        ctx=waiting_serial();project,p,h=pending(ctx);execute('CANCEL FILE TPDISPLAY',ctx);project.scheduler.run();self.assertEqual(p.snapshot()['S'],6)
    def test_cancelled_default_retains_unconsumed_serial_prefix(self):
        ctx=waiting_serial();project,p,h=pending(ctx);execute('CANCEL FILE',ctx);project.scheduler.run();self.assertEqual(bytes(ctx.serial_streams.files['P2:']),b'7')
    def test_idle_bare_cancel_does_not_cancel_future_input(self):
        self.assertEqual(execute('CANCEL FILE\n READ(n) CLOSE FILE TPDISPLAY')[0]['N'],7)
    def test_bare_cancel_uses_crt_input(self):
        ctx=waiting_serial({'INPUT':binding('P2:')});body='n=77 READ(n,CR) s=IO_STATUS(INPUT) CLOSE FILE INPUT'
        project,p,h=pending(ctx,body=body,prefix='%CRTDEVICE');execute('CANCEL FILE',ctx,prefix='%CRTDEVICE');project.scheduler.run();self.assertEqual(p.snapshot()['S'],6);self.assertNotIn('OUTPUT',ctx._predefined_values)
    def test_handler_bare_cancel_uses_active_default(self):
        ctx=waiting_serial();body='flag=FALSE CONDITION[1]: WHEN flag DO CANCEL FILE\n ENDCONDITION ENABLE CONDITION[1] n=77 READ(n,CR) s=IO_STATUS(TPDISPLAY) CLOSE FILE TPDISPLAY'
        p,_=build(body,ctx,sleep=lambda _:p._state.set('FLAG',True));self.assertEqual((p.run()['S'],p.snapshot()['N']),(6,77))
    def test_pending_typed_read_prevents_host_cleanup(self):
        ctx=waiting_serial();project,p,h=pending(ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'pending READ'):ctx.close_predefined_files()
        self.assertIsNotNone(h._read_operation);execute('CANCEL FILE',ctx);project.scheduler.run();ctx.close_predefined_files()
    def test_pending_read_prevents_json_save(self):
        ctx=waiting_serial();project,p,h=pending(ctx)
        with self.assertRaisesRegex(ValueError,'Close predefined'):ctx.to_config()
        execute('CANCEL FILE',ctx);project.scheduler.run();ctx.to_config()
    def test_repeated_cancel_is_idempotent(self):
        ctx=waiting_serial();project,p,h=pending(ctx);operation=h._read_operation;execute('CANCEL FILE TPDISPLAY CANCEL FILE TPDISPLAY',ctx);self.assertIs(h._read_operation,operation);project.scheduler.run();self.assertEqual(p.snapshot()['S'],6)
    def test_paused_cancel_waits_for_resume(self):
        ctx=waiting_serial();project,p,h=pending(ctx);p.pause()
        for _ in range(40):
            project.scheduler.step()
            if p.task_state=='paused':break
        self.assertEqual(p.task_state,'paused');execute('CANCEL FILE',ctx);self.assertEqual(p.task_state,'paused');project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual(p.snapshot()['S'],6)
    def test_stop_keeps_terminal_precedence_and_releases_pending_read(self):
        ctx=waiting_serial();project,p,h=pending(ctx);execute('CANCEL FILE',ctx);project.scheduler.stop('MAIN');self.assertEqual((p.task_state,p.snapshot()['N']),('stopped',77));self.assertIsNone(h._read_operation);ctx.close_predefined_files()
    def test_abort_keeps_terminal_precedence(self):
        ctx=waiting_serial();project,p,h=pending(ctx);execute('CANCEL FILE',ctx);rt.request_task_control(p._state,'ABORT')
        with self.assertRaises(rt.KarelAbort):project.scheduler.run()
        self.assertEqual(p.task_state,'aborted');ctx.close_predefined_files()
    def test_mutated_endpoint_is_detected_before_cancellation(self):
        ctx=waiting_serial();project,p,h=pending(ctx);old=h.name;h.name='P3:'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'identity'):execute('CANCEL FILE',ctx)
        self.assertFalse(h._read_operation['cancelled']);h.name=old;execute('CANCEL FILE',ctx);project.scheduler.run()
    def test_pipe_default_read_cancels(self):
        pipes=pipe_bank(b'7');ctx=rt.ExecutionContext(file_pipes=pipes,predefined_files={'TPDISPLAY':binding('PIP:LOG',pipe_wait=1)});project,p,h=pending(ctx);execute('CANCEL FILE',ctx);project.scheduler.run();self.assertEqual(p.snapshot()['S'],6)
    def test_read_kb_cancels_through_bare_default(self):
        old=keyboard_context();ctx=rt.ExecutionContext(keyboard=old.keyboard,pendant=old.pendant,predefined_files={'TPDISPLAY':binding('KB:TPKB','RW')})
        body="text='old' count=77 key=88 READ_KB(TPDISPLAY,text,16,KC_DISPLAY,KC_ENTER_KEY,-1,'',count,key,s) CLOSE FILE TPDISPLAY"
        project,p,h=pending(ctx,body=body,keyboard=True);execute('CANCEL FILE',ctx);project.scheduler.run();self.assertEqual((p.snapshot()['TEXT'],p.snapshot()['COUNT'],p.snapshot()['KEY'],p.snapshot()['S']),('old',77,88,6))
    def test_read_kb_prevents_cleanup_before_cancellation(self):
        old=keyboard_context();ctx=rt.ExecutionContext(keyboard=old.keyboard,pendant=old.pendant,predefined_files={'TPDISPLAY':binding('KB:TPKB','RW')})
        body="READ_KB(TPDISPLAY,text,16,KC_DISPLAY,KC_ENTER_KEY,-1,'',count,key,s) CLOSE FILE TPDISPLAY"
        project,p,h=pending(ctx,body=body,keyboard=True)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'pending READ'):ctx.close_predefined_files()
        execute('CANCEL FILE',ctx);project.scheduler.run();ctx.close_predefined_files()


class PredefinedOwnershipTests(unittest.TestCase):
    def test_foreign_context_cannot_supply_state(self):
        p,_=build('n=7');other=context()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'owning execution context'):other.predefined_file(p._state,'TPDISPLAY')
        self.assertEqual(other.files.handles,[])
    def test_host_alias_name_is_case_insensitive(self):
        p,_=build('n=7');h=p._state.predefined_file('tpdisplay');self.assertIs(h,p._state.predefined_file('TPDISPLAY'));p._state.execution.close_predefined_files()
    def test_default_direction_is_checked_before_open(self):
        p,_=build('n=7')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'READ or WRITE'):p._state.default_file('OTHER')
        self.assertEqual(p._state.execution._predefined_values,{})
    def test_borrowed_alias_cannot_be_retargeted(self):
        p,_=build("work(TPDISPLAY)",routines="ROUTINE work(h:FILE) BEGIN CLOSE FILE h OPEN FILE h('RO','other') END work")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cannot be reopened'):p.run()
        self.assertEqual(p._state.execution._predefined_values['TPDISPLAY'].owner,None)
    def test_registered_partial_open_failure_retains_owned_handle(self):
        from unittest.mock import patch
        ctx=context();p,_=build('READ(n)',ctx);original=p._state.file_open
        def failing(*args):original(*args);raise rt.KarelRuntimeError('Injected post-registration failure')
        with patch.object(p._state,'file_open',side_effect=failing):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'post-registration'):p.run()
        self.assertEqual(len(ctx.files.handles),1);self.assertIs(ctx._predefined_values['TPDISPLAY'],ctx.files.handles[0]);ctx.close_predefined_files()

    def test_cleanup_does_not_delete_replacement_during_close(self):
        from unittest.mock import patch
        _,ctx,_,_=execute('READ(n)');original=ctx.files.close;foreign=rt.FileHandle()
        def replaced(handle,line=None):original(handle,line);ctx._predefined_values['TPDISPLAY']=foreign
        with patch.object(ctx.files,'close',side_effect=replaced):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'cleanup ownership'):ctx.close_predefined_files()
        self.assertIs(ctx._predefined_values['TPDISPLAY'],foreign)
    def test_policy_exposes_binding_and_offline_boundaries(self):
        _,report=build('n=7');policy=report.report['predefined_file_policy'];self.assertEqual(policy['guide'],'docs/predefined-files.md');self.assertFalse(policy['controller_validated']);self.assertIn('callback',policy['defaults'])
    def test_type_name_does_not_become_a_predefined_file_value(self):
        with self.assertRaises(TranslationError) as e:build('n=input',prefix='TYPE input=INTEGER')
        self.assertEqual(e.exception.code,'E_SYMBOL')
    def test_host_reference_name_is_case_insensitive(self):
        p,_=build('n=7');reference=p._state.predefined_file_reference('tpdisplay');self.assertIs(reference.raw(),p._state.predefined_file('TPDISPLAY'));p._state.execution.close_predefined_files()
    def test_borrowed_reference_retains_original_closed_handle_after_reset(self):
        p,_=build('n=7');ctx=p._state.execution;reference=p._state.predefined_file_reference('TPDISPLAY');old=reference.raw();ctx.close_predefined_files();new=p._state.predefined_file('TPDISPLAY')
        self.assertIs(reference.raw(),old);self.assertIsNone(old.owner);self.assertIsNot(new,old);ctx.close_predefined_files()
