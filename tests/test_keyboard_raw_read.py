"""Portable printable keyboard EOL and bounded PASSALL ASCII STRING fields."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from tests.test_extended_services import compile_program
from tests.test_keyboard import context,WINDOW
from tests.test_project_scheduler import source


DECL='f:FILE text,other:STRING[8] x,y,s,count,key,token,device_stat:INTEGER'
OPEN="OPEN FILE f('RW','KB:TPKB') "
CLOSE=' CLOSE FILE f'
PASSALL='SET_FILE_ATR(f,ATR_PASSALL) '
CUSTOM='SET_FILE_ATR(f,ATR_EOL,59) '


def execute(body='READ f(text)',*,keys=(),ctx=None,decl=DECL,attributes=PASSALL):
    ctx=context(keys=keys) if ctx is None else ctx
    p,result=compile_program(attributes+OPEN+body+CLOSE,decl=decl,context=ctx,sleep=lambda _:None)
    return p.run(),ctx,p,result


def prepare(body,keys=(),*,ctx=None,attributes=PASSALL,decl=DECL,sleep=None):
    ctx=context(keys=keys) if ctx is None else ctx
    p,result=compile_program(attributes+OPEN+body,decl=decl,context=ctx,sleep=sleep or (lambda _:None))
    return ctx,p,result


class KeyboardCustomTerminatorTests(unittest.TestCase):
    def test_printable_delimiter_submits_typed_integer(self):
        values,ctx,p,_=execute('READ f(x,CR)',keys=tuple('42;'),attributes=CUSTOM)
        self.assertEqual(values['X'],42);self.assertEqual(ctx.keyboard.events,[])
        self.assertEqual(len(p.read_requests),1)

    def test_enter_is_not_an_alternate_custom_terminator(self):
        values,_,_,_=execute('READ f(x,CR)',keys=('4','ENTER','2',';'),attributes=CUSTOM)
        self.assertEqual(values['X'],42)

    def test_printable_delimiter_excluded_from_string(self):
        values,_,_,_=execute(keys=tuple('hello;'),attributes=CUSTOM)
        self.assertEqual(values['TEXT'],'hello')

    def test_custom_records_keep_unread_suffix_and_advance_string_reads(self):
        values,_,_,_=execute('READ f(text) READ f(other)',keys=tuple('one;two;'),attributes=CUSTOM)
        self.assertEqual((values['TEXT'],values['OTHER']),('one','two'))

    def test_custom_records_support_width_base_and_repeated_cr(self):
        values,_,_,_=execute('READ f(CR,x::2::16,CR,CR,y,CR)',keys=tuple('discard;2Aignored;discard;19;'),attributes=CUSTOM)
        self.assertEqual((values['X'],values['Y']),(42,19))

    def test_custom_delimiter_can_be_space(self):
        values,_,_,_=execute('READ f(x,CR,y,CR)',keys=tuple('42 19 '),attributes='SET_FILE_ATR(f,ATR_EOL,32) ')
        self.assertEqual((values['X'],values['Y']),(42,19))

    def test_custom_delimiter_preserves_editing(self):
        values,_,_,_=execute(keys=('a','c','LEFT','b','END','DELETE','d',';'),attributes=CUSTOM)
        self.assertEqual(values['TEXT'],'abd')

    def test_empty_custom_string_is_a_valid_record(self):
        values,_,_,_=execute(keys=(';',),attributes=CUSTOM)
        self.assertEqual(values['TEXT'],'')

    def test_custom_delimiter_does_not_consume_future_record(self):
        values,ctx,_,_=execute('READ f(x,CR)',keys=tuple('7;later;'),attributes=CUSTOM)
        self.assertEqual(values['X'],7);self.assertEqual([e['key'] for e in ctx.keyboard.events],list('later;'))

    def test_custom_delimiter_can_switch_to_read_kb_after_consumed_separator(self):
        statement="READ f(x) READ_KB(f,text,8,KC_DISPLAY,KC_ENTER_KEY,0,'',count,key,s)"
        values,_,_,_=execute(statement,keys=tuple('7;new')+('ENTER',),attributes=CUSTOM)
        self.assertEqual((values['X'],values['TEXT'],values['S']),(7,'new',0))

    def test_noninjectable_control_terminator_fails_before_events(self):
        for code in (0,9,23,127):
            with self.subTest(code=code):
                ctx,p,_=prepare('READ f(text)',keys=('a','ENTER'),attributes=f'SET_FILE_ATR(f,ATR_EOL,{code}) ')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'custom EOL'):p.run()
                self.assertEqual(len(ctx.keyboard.events),2);self.assertEqual(p.read_requests,());ctx.keyboard.close_all()

    def test_lf_and_cr_still_submit_on_enter(self):
        for code in (10,13):
            with self.subTest(code=code):
                values,_,_,_=execute('READ f(x)',keys=('7','ENTER'),attributes=f'SET_FILE_ATR(f,ATR_EOL,{code}) ')
                self.assertEqual(values['X'],7)

    def test_wrong_record_terminator_causes_explicit_input_wait_failure(self):
        ctx,p,_=prepare('READ f(x)',keys=('7','ENTER'),attributes=CUSTOM)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit queued input'):p.run()
        self.assertEqual(p.snapshot()['X'],{'uninitialized':True});ctx.keyboard.close_all()


class KeyboardPassallFieldTests(unittest.TestCase):
    def test_default_width_uses_concrete_destination_capacity(self):
        values,ctx,p,_=execute(keys=tuple('ABCDEFGH'))
        self.assertEqual(values['TEXT'],'ABCDEFGH');self.assertEqual(ctx.keyboard.events,[])
        self.assertEqual(len(p.read_requests),1);self.assertEqual(values['F']['position'],8)

    def test_explicit_width_completes_without_enter(self):
        values,ctx,_,_=execute('READ f(text::3)',keys=tuple('abcZ'))
        self.assertEqual(values['TEXT'],'abc');self.assertEqual([e['key'] for e in ctx.keyboard.events],['Z'])

    def test_zero_width_uses_declared_string_capacity(self):
        values,_,_,_=execute('READ f(text::0)',keys=tuple('ABCDEFGH'))
        self.assertEqual(values['TEXT'],'ABCDEFGH')

    def test_field_attribute_is_implied_and_explicit_is_compatible(self):
        values,_,_,_=execute(keys=tuple('ABCDEFGH'),attributes=PASSALL+'SET_FILE_ATR(f,ATR_FIELD) ')
        self.assertEqual(values['TEXT'],'ABCDEFGH')

    def test_multiple_fields_publish_together(self):
        values,_,p,_=execute('READ f(text::3,other::2)',keys=tuple('abcde'))
        self.assertEqual((values['TEXT'],values['OTHER']),('abc','de'));self.assertEqual(len(p.read_requests),1)

    def test_field_longer_than_destination_consumes_then_truncates(self):
        values,_,_,_=execute('READ f(text::10,other::2)',keys=tuple('ABCDEFGHIJKL'))
        self.assertEqual((values['TEXT'],values['OTHER']),('ABCDEFGH','KL'))

    def test_successive_reads_do_not_require_records(self):
        values,_,p,_=execute('READ f(text::2) READ f(other::2)',keys=tuple('abcd'))
        self.assertEqual((values['TEXT'],values['OTHER']),('ab','cd'));self.assertEqual(len(p.read_requests),2)

    def test_quote_characters_are_literal(self):
        values,_,_,_=execute('READ f(text::3::0)',keys=("'",'a',"'"))
        self.assertEqual(values['TEXT'],"'a'")

    def test_enter_delete_refresh_have_literal_ascii_values(self):
        values,_,_,_=execute('READ f(text::4)',keys=('a','ENTER','DELETE','REFRESH'))
        self.assertEqual(values['TEXT'],'a\r\x08\x17')

    def test_delimiter_is_ignored_as_a_raw_termination_rule(self):
        values,_,_,_=execute('READ f(text::4)',keys=tuple('a;b;'),attributes=PASSALL+CUSTOM)
        self.assertEqual(values['TEXT'],'a;b;')

    def test_passall_can_ignore_noninjectable_eol_setting(self):
        values,_,_,_=execute('READ f(text::1)',keys=('a',),attributes=PASSALL+'SET_FILE_ATR(f,ATR_EOL,0) ')
        self.assertEqual(values['TEXT'],'a')

    def test_raw_controls_do_not_echo_or_modify_window(self):
        ctx=context(keys=('a','ENTER','DELETE'))
        body=WINDOW+PASSALL+"OPEN FILE f('RW','WD:W1/TPKB') WRITE f('keep') READ f(text::3)"+CLOSE
        p,_=compile_program(body,decl=DECL,context=ctx,sleep=lambda _:None)
        self.assertEqual(p.run()['TEXT'],'a\r\x08');self.assertTrue(ctx.pendant.windows['W1']['lines'][0].startswith('keep'))
        self.assertEqual(ctx.pendant.windows['W1']['cursor'],dict(row=1,col=5,wrap=False))

    def test_noecho_attribute_is_compatible(self):
        values,_,_,_=execute('READ f(text::2)',keys=('a','b'),attributes=PASSALL+'SET_FILE_ATR(f,ATR_NOECHO) ')
        self.assertEqual(values['TEXT'],'ab')

    def test_raw_read_does_not_add_line_history(self):
        values,ctx,_,_=execute("READ f(text::2) READ_KB(f,other,8,KC_DISPLAY OR KC_UD_ARW,KC_ENTER_KEY,0,'',count,key,s)",keys=('a','b','UP','ENTER'))
        self.assertEqual((values['TEXT'],values['OTHER']),('ab',''));self.assertEqual(ctx.keyboard.history[0]['data']['raw'],1)

    def test_control_history_roundtrips_as_bounded_hex_sample(self):
        values,ctx,_,_=execute('READ f(text::3)',keys=('ENTER','DELETE','REFRESH'))
        row=ctx.keyboard.history[-1]
        self.assertEqual((row['data']['sample_hex'],row['data']['bytes']),('0d0817',3))
        self.assertEqual(values['TEXT'],'\r\x08\x17')
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.keyboard.to_config(),ctx.keyboard.to_config())

    def test_exact_total_read_bound_of_4096_bytes(self):
        fields=['text::254']*16+['other::32']
        values,ctx,p,_=execute('READ f('+','.join(fields)+')',keys=tuple('x'*4096))
        self.assertEqual((values['TEXT'],values['OTHER']),('x'*8,'x'*8))
        self.assertEqual(values['F']['position'],4096);self.assertEqual(len(p.read_requests),1)
        self.assertEqual(ctx.keyboard.history[-1]['data']['bytes'],4096);ctx.to_config()

    def test_repeated_raw_destinations_keep_source_order(self):
        values,_,p,_=execute('READ f(text::2,text::2)',keys=tuple('abcd'))
        self.assertEqual(values['TEXT'],'cd');self.assertEqual(len(p.read_requests),1)

    def test_maximum_single_field_width(self):
        values,ctx,_,_=execute('READ f(text::254)',keys=tuple('x'*254),decl=DECL.replace('STRING[8]','STRING[254]'))
        self.assertEqual(values['TEXT'],'x'*254);self.assertLessEqual(len(ctx.keyboard.history[-1]['data']['sample_hex']),64)


class KeyboardRawFailureTests(unittest.TestCase):
    def test_numeric_destination_rejected_before_keys_or_observation(self):
        ctx,p,_=prepare('READ f(x)',keys=('7',))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ATR_PASSALL.*STRING'):p.run()
        self.assertEqual(len(ctx.keyboard.events),1);self.assertEqual(p.read_requests,())
        self.assertEqual(p._state.values['F'].status,1);ctx.keyboard.close_all()

    def test_mixed_numeric_destination_rejected_before_any_assignment(self):
        ctx,p,_=prepare("text='old' x=1 READ f(text::1,x)",keys=('a','7'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ATR_PASSALL.*STRING'):p.run()
        self.assertEqual((p.snapshot()['TEXT'],p.snapshot()['X']),('old',1));self.assertEqual(len(ctx.keyboard.events),2)
        ctx.keyboard.close_all()

    def test_quoted_format_rejected_before_consuming_keys(self):
        ctx,p,_=prepare('READ f(text::3::2)',keys=("'",'a',"'"))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'unquoted fixed STRING'):p.run()
        self.assertEqual(len(ctx.keyboard.events),3);ctx.keyboard.close_all()

    def test_cr_markers_rejected_before_consuming_keys(self):
        for statement in ('READ f(text::1,CR)','READ f(CR)'):
            with self.subTest(statement=statement):
                ctx,p,_=prepare(statement,keys=('a',))
                with self.assertRaisesRegex(rt.KarelRuntimeError,'CR markers'):p.run()
                self.assertEqual(len(ctx.keyboard.events),1);ctx.keyboard.close_all()

    def test_total_width_limit_preflight(self):
        statement='READ f('+','.join('text::254' for _ in range(17))+')'
        ctx,p,_=prepare(statement,keys=('a',))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'4096 raw bytes'):p.run()
        self.assertEqual(len(ctx.keyboard.events),1);self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.keyboard.close_all()

    def test_nonascii_key_consumed_once_without_publishing_prefix(self):
        for key in ('LEFT','F1','HOME','SELECT'):
            with self.subTest(key=key):
                ctx,p,_=prepare("text='old' READ f(text::3)",keys=('a',key,'b','c'))
                with self.assertRaisesRegex(rt.KarelRuntimeError,'no portable ASCII'):p.run()
                handle=p._state.values['F'];binding=ctx.keyboard._handles[handle]
                self.assertEqual((p.snapshot()['TEXT'],handle.position,binding['pending']),('old',0,'a'))
                self.assertEqual(handle.status,1)
                self.assertEqual([e['key'] for e in ctx.keyboard.events],['b','c'])
                self.assertEqual(p.read_requests[-1]['adapter_outcome'],'callback_failed');ctx.keyboard.close_all()

    def test_short_input_preserves_every_destination_and_raw_prefix(self):
        ctx,p,_=prepare("text='old' other='kept' READ f(text::2,other::2)",keys=tuple('abc'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit queued input'):p.run()
        handle=p._state.values['F']
        self.assertEqual((p.snapshot()['TEXT'],p.snapshot()['OTHER']),('old','kept'))
        self.assertEqual((handle.position,ctx.keyboard._handles[handle]['pending']),(0,'abc'))
        self.assertEqual(len(p.read_requests),1);ctx.keyboard.close_all()

    def test_pending_raw_control_cannot_be_discarded_by_read_kb(self):
        ctx,p,_=prepare("text='old' READ f(text::2)",keys=('ENTER','LEFT'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        state=p._state;handle=state.values['F']
        args=[handle,state.reference('OTHER'),8,1,8,0,'',state.reference('COUNT'),state.reference('KEY'),state.reference('S')]
        list(ctx.keyboard.read(state,args))
        self.assertEqual(p.snapshot()['S'],1);self.assertEqual(ctx.keyboard._handles[handle]['pending'],'\r')
        ctx.keyboard.close_all()

    def test_compatible_raw_read_can_retry_a_retained_prefix(self):
        ctx,p,_=prepare("text='old' READ f(text::3)",keys=('a','LEFT','b','c'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        state=p._state;handle=state.values['F']
        with rt._numeric_scope('pythonic'):
            list(ctx.keyboard.file_read(state,handle,[state.reference('TEXT')],formats=[(3,)]))
        self.assertEqual((p.snapshot()['TEXT'],handle.position,handle.status),('abc',3,0))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],'');self.assertEqual(len(p.read_requests),2)
        ctx.keyboard.close_all();ctx.to_config()

    def test_raw_line_mode_switch_rejects_retained_bytes(self):
        ctx,p,_=prepare('READ f(text::2)',keys=('a','LEFT','b','ENTER'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        state=p._state;handle=state.values['F'];handle.passall=False
        with self.assertRaisesRegex(rt.KarelRuntimeError,'before switching line/raw'):
            list(ctx.keyboard.file_read(state,handle,[state.reference('TEXT')]))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],'a');self.assertEqual(len(ctx.keyboard.events),2)
        ctx.keyboard.close_all()

    def test_line_raw_mode_switch_rejects_retained_text(self):
        ctx,p,_=prepare('READ f(x) PAUSE',keys=tuple('7 rest;'),attributes=CUSTOM)
        with self.assertRaises(rt.KarelPause):p.run()
        state=p._state;handle=state.values['F'];handle.passall=True
        with self.assertRaisesRegex(rt.KarelRuntimeError,'before switching line/raw'):
            list(ctx.keyboard.file_read(state,handle,[state.reference('TEXT')]))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],' rest;')
        p.stop();ctx.keyboard.close_all()

    def test_closed_raw_file_discards_retained_prefix(self):
        ctx,p,_=prepare('READ f(text::2)',keys=('a','LEFT'))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        ctx.keyboard.close_all();ctx.to_config();self.assertEqual(ctx.keyboard._handles,{})


class KeyboardRawLifetimeTests(unittest.TestCase):
    def test_partial_raw_read_pause_keeps_outputs_and_prefix(self):
        events=[dict(key='a'),dict(key='b',at_ms=25)]
        ctx=context(events=events)
        p,_=compile_program(PASSALL+OPEN+"text='old' READ f(text::2)"+CLOSE,decl=DECL,context=ctx,
            sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['TEXT'],'old');self.assertEqual(ctx.keyboard._handles[p._state.values['F']]['pending'],'a')
        self.assertEqual(p.read_requests,())
        with self.assertRaises(ValueError):ctx.to_config()
        p._state._sleep=lambda _:None;p.resume()
        self.assertEqual(p.snapshot()['TEXT'],'ab');self.assertEqual(len(p.read_requests),1);ctx.to_config()

    def test_stop_releases_raw_job_without_publishing_or_replaying_input(self):
        ctx=context(events=[dict(key='a'),dict(key='b',at_ms=25)])
        p,_=compile_program(PASSALL+OPEN+"text='old' READ f(text::2)",decl=DECL,context=ctx,
            sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        handle=p._state.values['F']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Finish or stop'):ctx.keyboard.close(handle)
        p.stop();self.assertEqual(p.snapshot()['TEXT'],'old');self.assertEqual(ctx.keyboard.snapshot()['active'],[])
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],'a');self.assertEqual([e['key'] for e in ctx.keyboard.events],['b'])
        self.assertEqual(ctx.keyboard.history[-1]['outcome'],'cancelled');ctx.keyboard.close_all();ctx.to_config()

    def test_budget_failure_releases_job(self):
        ctx=context(events=[dict(key='b',at_ms=10000)])
        ctx,p,_=prepare('READ f(text::2)',ctx=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run(max_steps=30)
        self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.keyboard.close_all();ctx.to_config()

    def test_timed_raw_characters_advance_keyboard_clock(self):
        ctx=context(events=[dict(key='a',at_ms=10),dict(key='b',at_ms=20)])
        values,_,_,_=execute('READ f(text::2)',ctx=ctx)
        self.assertEqual((values['TEXT'],ctx.keyboard.elapsed_ms),('ab',20))

    def test_raw_read_captures_open_pane(self):
        events=[dict(key=key,pane=pane) for pane,text in ((1,'xx'),(2,'ab')) for key in text]
        ctx=context(events=events)
        body=PASSALL+'device_stat=2 '+OPEN+'device_stat=1 READ f(text::2)'+CLOSE
        p,_=compile_program(body,decl=DECL,context=ctx,sleep=lambda _:None)
        self.assertEqual(p.run()['TEXT'],'ab');self.assertEqual({e['pane'] for e in ctx.keyboard.events},{1})

    def test_shared_pane_fifo_raw_reads_consume_each_event_once(self):
        ctx=context(events=[dict(key=key,at_ms=100) for key in '1122'])
        reader=PASSALL+OPEN+'READ f(text::2)'+CLOSE+' SIGNAL EVENT[1]'
        main="RUN_TASK('WORKER',0,FALSE,FALSE,0,s) DELAY(10) "+PASSALL+OPEN+'READ f(text::2)'+CLOSE+' WAIT FOR EVENT[1]'
        project=translate_project({'main':source('MAIN',main,decl=DECL),'worker':source('WORKER',reader,decl=DECL)}).instantiate(context=ctx)
        result=project.run('MAIN')
        self.assertEqual((result['WORKER']['values']['TEXT'],result['MAIN']['values']['TEXT']),('11','22'))
        self.assertEqual(ctx.keyboard.events,[]);ctx.to_config()

    def test_push_pop_suspends_raw_reader_without_changing_buffer(self):
        ctx=context(events=[dict(key=key,at_ms=100) for key in '11']+[dict(key=key,at_ms=200) for key in '22'])
        reader=PASSALL+OPEN+'READ f(text::2)'+CLOSE+' SIGNAL EVENT[1]'
        main="RUN_TASK('WORKER',0,FALSE,FALSE,0,s) DELAY(10) PUSH_KEY_RD('TPKB',KC_DISPLAY,token,s) "+PASSALL+OPEN+'READ f(text::2)'+CLOSE+" POP_KEY_RD('TPKB',token,s) WAIT FOR EVENT[1]"
        project=translate_project({'main':source('MAIN',main,decl=DECL),'worker':source('WORKER',reader,decl=DECL)}).instantiate(context=ctx)
        result=project.run('MAIN')
        self.assertEqual((result['MAIN']['values']['TEXT'],result['WORKER']['values']['TEXT']),('11','22'))
        self.assertEqual(ctx.keyboard.snapshot()['suspensions'],0);ctx.to_config()


if __name__=='__main__':unittest.main()
