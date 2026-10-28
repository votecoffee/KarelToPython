"""Injected keyboard FILE text READ, parsing transactions and lifetimes."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from tests.test_extended_services import compile_program
from tests.test_keyboard import context,WINDOW
from tests.test_project_scheduler import source


DECL='f,g:FILE x,y,s,token,key,count,device_stat:INTEGER real_value:REAL flag:BOOLEAN text,other:STRING[20] a:ARRAY[1] OF BYTE b:ARRAY[1] OF SHORT'
OPEN="OPEN FILE f('RW','KB:TPKB') "
CLOSE=' CLOSE FILE f'


def line_keys(*lines):
    return [key for text in lines for key in (*text,'ENTER')]


def execute(body='READ f(x)',*,keys=(),ctx=None,decl=DECL,**options):
    ctx=context(keys=keys) if ctx is None else ctx
    p,result=compile_program(OPEN+body+CLOSE,decl=decl,context=ctx,sleep=lambda _:None,**options)
    return p.run(),ctx,p,result


class KeyboardFileScalarTests(unittest.TestCase):
    def test_integer_text_requires_submitted_line(self):
        values,ctx,p,_=execute(keys=line_keys('42'))
        self.assertEqual(values['X'],42);self.assertEqual(len(p.read_requests),1)
        self.assertEqual(p.read_requests[0]['adapter_outcome'],'callback_completed')
        self.assertEqual(ctx.keyboard.history[-1]['operation'],'FILE_READ');ctx.to_config()

    def test_real_boolean_and_line_remainder(self):
        values,_,_,_=execute('READ f(x,real_value,flag,text,CR)',keys=line_keys('3 2.5 OFF hello there'))
        self.assertEqual((values['X'],values['REAL_VALUE'],values['FLAG'],values['TEXT']),(3,2.5,False,' hello there'))

    def test_strings_are_truncated_only_after_parsing(self):
        values,_,_,_=execute('READ f(text,CR)',keys=line_keys('abcdefghijklmnopqrstuvwxy'))
        self.assertEqual(values['TEXT'],'abcdefghijklmnopqrst')

    def test_adjacent_fixed_widths_and_integer_base(self):
        values,_,_,_=execute('READ f(x::2::16,y::3)',keys=line_keys('2A123'))
        self.assertEqual((values['X'],values['Y']),(42,123))

    def test_boolean_abbreviations_and_real_second_format(self):
        values,_,_,_=execute('READ f(flag::3::99,real_value::5::-1)',keys=line_keys('OFF 2.50'))
        self.assertEqual((values['FLAG'],values['REAL_VALUE']),(False,2.5))

    def test_quoted_string_followed_by_number(self):
        values,_,_,_=execute('READ f(text::0::2,x)',keys=line_keys("'a''b' 7"))
        self.assertEqual((values['TEXT'],values['X']),("a'b",7))

    def test_byte_short_and_sentinel(self):
        values,_,_,_=execute('READ f(a[1]::2::16,b[1]::4::16)',keys=line_keys('FF7FFF'))
        self.assertEqual(values['A'],[255]);self.assertEqual(values['B'],[{'uninitialized':True}])

    def test_multiline_statement_commits_all_fields_together(self):
        values,_,p,_=execute('READ f(x,CR,y,CR)',keys=line_keys('4','8'))
        self.assertEqual((values['X'],values['Y']),(4,8));self.assertEqual(len(p.read_requests),1)
        self.assertEqual(p.read_requests[0]['line_breaks'],[1,2])

    def test_cr_only_statement_consumes_one_submitted_line(self):
        values,_,p,_=execute('READ f(CR) READ f(x)',keys=line_keys('discard','8'))
        self.assertEqual(values['X'],8);self.assertEqual(len(p.read_requests),2)

    def test_leading_and_repeated_cr_markers(self):
        values,_,_,_=execute('READ f(CR,CR,x,CR)',keys=line_keys('discard','also discard','8'))
        self.assertEqual(values['X'],8)

    def test_unread_numeric_suffix_stays_on_same_open_file(self):
        values,ctx,p,_=execute('READ f(x) READ f(y)',keys=line_keys('42 19'))
        self.assertEqual((values['X'],values['Y']),(42,19));self.assertEqual(len(p.read_requests),2)
        self.assertEqual(len(ctx.keyboard.history),2)

    def test_consecutive_string_reads_advance_completed_records(self):
        values,_,_,_=execute('READ f(text) READ f(other)',keys=line_keys('one','two'))
        self.assertEqual((values['TEXT'],values['OTHER']),('one','two'))

    def test_string_following_numeric_read_keeps_separator_blanks(self):
        values,_,_,_=execute('READ f(x) READ f(text)',keys=line_keys('42  suffix'))
        self.assertEqual((values['X'],values['TEXT']),(42,'  suffix'))

    def test_trailing_cr_discards_suffix_without_consuming_future_events(self):
        values,ctx,_,_=execute('READ f(x,CR)',keys=line_keys('42 ignored','later'))
        self.assertEqual(values['X'],42);self.assertEqual([row['key'] for row in ctx.keyboard.events],line_keys('later'))

    def test_generic_read_bypasses_program_read_callback(self):
        values,_,_,_=execute(keys=line_keys('17'),read=lambda _:self.fail('Keyboard must not invoke Program(read=...)'))
        self.assertEqual(values['X'],17)

    def test_read_inside_typed_routine(self):
        values,_,_,_=execute('receive(x)',keys=line_keys('18'),routines='ROUTINE receive(value:INTEGER) BEGIN READ f(value) END receive')
        self.assertEqual(values['X'],18)

    def test_field_attribute_uses_string_destination_capacity(self):
        body="SET_FILE_ATR(f,ATR_FIELD) "+OPEN+'READ f(text)'+CLOSE
        ctx=context(keys=line_keys('abc'))
        p,_=compile_program(body,decl=DECL.replace('STRING[20]','STRING[3]'),context=ctx,sleep=lambda _:None)
        self.assertEqual(p.run()['TEXT'],'abc')


class KeyboardFileEditingTests(unittest.TestCase):
    def test_insert_delete_cursor_editing(self):
        values,_,_,_=execute('READ f(text)',keys=('a','c','LEFT','b','END','DELETE','d','ENTER'))
        self.assertEqual(values['TEXT'],'abd')

    def test_home_end_and_history_recall(self):
        values,_,_,_=execute('READ f(text,CR) READ f(other)',keys=('a','b','HOME','X','END','Y','ENTER','UP','ENTER'))
        self.assertEqual((values['TEXT'],values['OTHER']),('XabY','XabY'))

    def test_unhandled_control_keys_are_consumed_without_text(self):
        values,_,_,_=execute('READ f(text)',keys=('F1','PREV','SELECT','NEW_MENU','a','ENTER'))
        self.assertEqual(values['TEXT'],'a')

    def test_window_echo_is_clipped_and_keeps_cursor(self):
        body=WINDOW+"OPEN FILE f('RW','WD:W1/TPKB') SET_CURSOR(f,2,18,s) READ f(text)"+CLOSE
        ctx=context(keys=line_keys('longer'))
        p,_=compile_program(body,decl=DECL,context=ctx,sleep=lambda _:None);values=p.run()
        self.assertEqual(values['TEXT'],'longer');self.assertEqual(ctx.pendant.windows['W1']['lines'][1][-3:],'lon')
        self.assertEqual(ctx.pendant.windows['W1']['cursor'],dict(row=2,col=18,wrap=False))

    def test_noecho_preserves_existing_window_text(self):
        body=WINDOW+"SET_FILE_ATR(f,ATR_NOECHO) OPEN FILE f('RW','WD:W1/TPKB') WRITE f('keep') READ f(text)"+CLOSE
        ctx=context(keys=line_keys('secret'))
        p,_=compile_program(body,decl=DECL,context=ctx,sleep=lambda _:None);values=p.run()
        self.assertEqual(values['TEXT'],'secret');self.assertTrue(ctx.pendant.windows['W1']['lines'][0].startswith('keep'))

    def test_timed_keys_advance_explicit_logical_clock(self):
        ctx=context(events=[dict(key='4',at_ms=10),dict(key='2',at_ms=20),dict(key='ENTER',at_ms=30)])
        values,_,_,_=execute(ctx=ctx)
        self.assertEqual((values['X'],ctx.keyboard.elapsed_ms),(42,30))

    def test_pane_is_captured_at_open(self):
        events=[dict(key=key,pane=pane) for pane,text in [(1,'bad'),(2,'27')] for key in (*text,'ENTER')]
        ctx=context(events=events)
        p,_=compile_program('device_stat=2 '+OPEN+'device_stat=1 READ f(x)'+CLOSE,decl=DECL,context=ctx,sleep=lambda _:None)
        self.assertEqual(p.run()['X'],27);self.assertEqual({e['pane'] for e in ctx.keyboard.events},{1})

    def test_read_kb_and_generic_read_share_completed_line_history(self):
        body="READ f(text,CR) READ_KB(f,other,20,KC_DISPLAY OR KC_UD_ARW,KC_ENTER_KEY,0,'',count,key,s)"
        values,_,_,_=execute(body,keys=tuple(line_keys('shared'))+('UP','ENTER'))
        self.assertEqual((values['TEXT'],values['OTHER'],values['S']),('shared','shared',0))

    def test_read_kb_rejects_unread_typed_suffix_without_consuming_events(self):
        statement="READ f(x) text='old' READ_KB(f,text,20,KC_DISPLAY,KC_ENTER_KEY,0,'',count,key,s)"
        values,ctx,_,_=execute(statement,keys=line_keys('4 99','new'))
        self.assertEqual((values['X'],values['TEXT'],values['S']),(4,'old',1))
        self.assertEqual([e['key'] for e in ctx.keyboard.events],line_keys('new'))

    def test_read_kb_can_follow_a_consumed_typed_line_separator(self):
        statement="READ f(x) READ_KB(f,text,20,KC_DISPLAY,KC_ENTER_KEY,0,'',count,key,s)"
        values,_,_,_=execute(statement,keys=line_keys('4','new'))
        self.assertEqual((values['X'],values['TEXT'],values['S']),(4,'new',0))


class KeyboardFileFailureTests(unittest.TestCase):
    def failing(self,body,keys,pattern=None,**options):
        ctx=context(keys=keys);p,_=compile_program(OPEN+body,decl=DECL,context=ctx,sleep=lambda _:None,**options)
        with self.assertRaisesRegex(rt.KarelRuntimeError,pattern or '.'):
            p.run()
        self.assertEqual(ctx.keyboard.snapshot()['active'],[])
        return ctx,p

    def test_invalid_later_field_preserves_all_outputs(self):
        ctx,p=self.failing('x=1 y=2 READ f(x,y)',line_keys('7 bad'),'invalid INTEGER')
        self.assertEqual((p.snapshot()['X'],p.snapshot()['Y']),(1,2))
        self.assertEqual(len(p.read_requests),1);self.assertEqual(p.read_requests[0]['adapter_outcome'],'callback_failed')
        handle=p._state.values['F'];binding=ctx.keyboard._handles[handle]
        self.assertEqual((handle.position,binding['pending']),(0,'7 bad\n'))
        ctx.keyboard.close_all();ctx.to_config()

    def test_invalid_second_line_retains_transaction_and_both_original_values(self):
        ctx,p=self.failing('x=1 y=2 READ f(x,CR,y,CR)',line_keys('7','bad'),'invalid INTEGER')
        handle=p._state.values['F']
        self.assertEqual((p.snapshot()['X'],p.snapshot()['Y']),(1,2))
        self.assertEqual((handle.position,ctx.keyboard._handles[handle]['pending']),(0,'7\nbad\n'))
        self.assertEqual(len(p.read_requests),1);ctx.keyboard.close_all();ctx.to_config()

    def test_invalid_finite_numeric_input_rejects_complete_statement(self):
        for value in ('nan','inf','1e1000'):
            with self.subTest(value=value):
                ctx,p=self.failing('x=1 real_value=2 READ f(x,real_value)',line_keys('7 '+value),'invalid REAL')
                self.assertEqual((p.snapshot()['X'],p.snapshot()['REAL_VALUE']),(1,2.0));ctx.keyboard.close_all()

    def test_later_incomplete_field_does_not_span_physical_lines(self):
        ctx,p=self.failing('x=1 y=2 READ f(x::1,y::3)',line_keys('78','999'),'incomplete field')
        self.assertEqual((p.snapshot()['X'],p.snapshot()['Y']),(1,2))
        self.assertEqual([e['key'] for e in ctx.keyboard.events],line_keys('999'))
        ctx.keyboard.close_all()

    def test_invalid_quote_preserves_string_and_cursor(self):
        ctx,p=self.failing("text='old' READ f(text::0::2)",line_keys("'bad"),'invalid quoted STRING')
        self.assertEqual(p.snapshot()['TEXT'],'old');self.assertEqual(p._state.values['F'].position,0)
        ctx.keyboard.close_all()

    def test_no_input_fails_without_host_acquisition(self):
        ctx,p=self.failing('x=1 READ f(x)',(),'explicit queued input')
        self.assertEqual(p.snapshot()['X'],1);self.assertEqual(len(p.read_requests),1)
        ctx.keyboard.close_all();ctx.to_config()

    def test_line_length_limit_preserves_output_and_unconsumed_keys(self):
        ctx,p=self.failing("text='old' READ f(text)",tuple('x'*255)+('ENTER',),'254 characters')
        self.assertEqual(p.snapshot()['TEXT'],'old');self.assertEqual([e['key'] for e in ctx.keyboard.events],['ENTER'])
        ctx.keyboard.close_all()

    def test_too_many_control_events_is_bounded(self):
        ctx=context(keys=['F1']*4096);p,_=compile_program(OPEN+'READ f(x)',decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'4096 processed keys'):p.run(max_steps=10000)
        self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.keyboard.close_all()

    def test_passall_rejected_before_consuming_keys(self):
        ctx=context(keys=line_keys('7'))
        p,_=compile_program('SET_FILE_ATR(f,ATR_PASSALL) '+OPEN+'READ f(x)',decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ATR_PASSALL'):p.run()
        self.assertEqual([e['key'] for e in ctx.keyboard.events],line_keys('7'));ctx.keyboard.close_all()

    def test_custom_eol_rejected_before_consuming_keys(self):
        ctx=context(keys=line_keys('7'));p,_=compile_program('SET_FILE_ATR(f,ATR_EOL,59) '+OPEN+'READ f(x)',decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'custom EOL'):p.run()
        self.assertEqual([e['key'] for e in ctx.keyboard.events],line_keys('7'));ctx.keyboard.close_all()

    def test_bad_dynamic_format_does_not_consume_input(self):
        ctx,p=self.failing('x=-1 READ f(y::x)',line_keys('7'),'READ width')
        self.assertEqual([e['key'] for e in ctx.keyboard.events],line_keys('7'));self.assertEqual(p.read_requests,())
        ctx.keyboard.close_all()

    def test_binary_and_xml_endpoint_open_remain_rejected(self):
        for attribute in ('ATR_UF','ATR_XML'):
            ctx=context(keys=line_keys('7'));p,_=compile_program('SET_FILE_ATR(f,'+attribute+') '+OPEN+'READ f(x)',decl=DECL,context=ctx,sleep=lambda _:None)
            with self.subTest(attribute=attribute),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(ctx.keyboard.snapshot()['open_files'],[]);self.assertEqual(len(ctx.keyboard.events),2)

    def test_closed_keyboard_handle_fails_explicitly(self):
        ctx=context(keys=line_keys('7'));p,_=compile_program(OPEN+CLOSE+' READ f(x)',decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not open'):p.run()
        self.assertEqual(len(ctx.keyboard.events),2)

    def test_condition_handler_cannot_start_conflicting_read_on_same_file(self):
        ctx=context(events=[dict(key=key,at_ms=20) for key in line_keys('7')])
        body=OPEN+"x=0 CONDITION[1]: WHEN x=1 DO READ_KB(f,text,1,KC_DISPLAY,KC_ENTER_KEY,0,'',count,key,s) ENDCONDITION ENABLE CONDITION[1] READ f(y)"+CLOSE
        p,_=compile_program(body,decl=DECL,context=ctx,sleep=lambda _:p._state.values.__setitem__('X',1))
        p.run();self.assertEqual(p.snapshot()['S'],2);self.assertEqual(p.snapshot()['Y'],7)


class KeyboardFileLifetimeTests(unittest.TestCase):
    def test_pause_after_first_line_keeps_all_multi_target_outputs_old(self):
        events=[dict(key=key,at_ms=at) for at,value in ((0,'7'),(25,'8')) for key in line_keys(value)]
        ctx=context(events=events)
        p,_=compile_program(OPEN+'x=1 y=2 READ f(x,CR,y,CR)'+CLOSE,decl=DECL,context=ctx,
            sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual((p.snapshot()['X'],p.snapshot()['Y']),(1,2));self.assertEqual(p.read_requests,())
        self.assertEqual(ctx.keyboard._handles[p._state.values['F']]['pending'],'7\n')
        p._state._sleep=lambda _:None;p.resume()
        self.assertEqual((p.snapshot()['X'],p.snapshot()['Y']),(7,8));self.assertEqual(len(p.read_requests),1)
        ctx.to_config()

    def test_unrelated_standalone_root_cannot_share_active_clock_domain(self):
        ctx=context(events=[dict(key='ENTER',at_ms=25)])
        first,_=compile_program(OPEN+'READ f(text)',decl=DECL,context=ctx,
            sleep=lambda _:setattr(first._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):first.run()
        second,_=compile_program(OPEN+'READ f(text)',decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'clock domain'):second.run()
        self.assertEqual(len(ctx.keyboard.snapshot()['active']),1);self.assertEqual(len(ctx.keyboard.events),1)
        first.stop();ctx.keyboard.close_all();ctx.to_config()

    def test_pause_retains_editor_and_outputs_until_resume(self):
        ctx=context(events=[dict(key='4'),dict(key='2',at_ms=25),dict(key='ENTER',at_ms=25)])
        p,_=compile_program(OPEN+'x=1 READ f(x)'+CLOSE,decl=DECL,context=ctx,
            sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['X'],1);self.assertEqual(ctx.keyboard.snapshot()['active'][0]['text'],'4')
        with self.assertRaises(ValueError):ctx.to_config()
        p._state._sleep=lambda _:None;p.resume()
        self.assertEqual(p.snapshot()['X'],42);self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.to_config()

    def test_stop_releases_job_but_retains_open_handle_for_explicit_close(self):
        ctx=context(events=[dict(key='ENTER',at_ms=25)])
        p,_=compile_program(OPEN+'x=1 READ f(x)',decl=DECL,context=ctx,
            sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        handle=p._state.values['F']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Finish or stop'):ctx.keyboard.close(handle)
        p.stop();self.assertEqual(p.snapshot()['X'],1);self.assertEqual(ctx.keyboard.snapshot()['active'],[])
        self.assertEqual(ctx.keyboard.history[-1]['outcome'],'cancelled');ctx.keyboard.close_all();ctx.to_config()

    def test_failed_input_buffer_is_retained_until_close(self):
        ctx=context(keys=line_keys('bad'));p,_=compile_program(OPEN+'READ f(x)',decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.keyboard._handles[p._state.values['F']]['pending'],'bad\n')
        ctx.keyboard.close_all();self.assertEqual(ctx.keyboard._handles,{})
        saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).keyboard.to_config(),ctx.keyboard.to_config())

    def test_buffered_suffix_is_not_serialized_as_future_input(self):
        values,ctx,_,_=execute('READ f(x)',keys=line_keys('4 99'))
        self.assertEqual(values['X'],4);saved=json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(saved).keyboard.events,[])

    def test_budget_error_cleans_pending_job(self):
        ctx=context(events=[dict(key='ENTER',at_ms=10000)])
        p,_=compile_program(OPEN+'READ f(x)',decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaises(rt.KarelRuntimeError):p.run(max_steps=30)
        self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.keyboard.close_all();ctx.to_config()

    def test_fifo_reads_share_pane_and_do_not_duplicate_events(self):
        events=[dict(key=key,at_ms=100) for key in line_keys('11','22')]
        ctx=context(events=events)
        reader=OPEN+'READ f(x,CR)'+CLOSE+' SIGNAL EVENT[1]'
        main="RUN_TASK('WORKER',0,FALSE,FALSE,0,s) DELAY(10) "+OPEN+'READ f(x,CR)'+CLOSE+' WAIT FOR EVENT[1]'
        project=translate_project({'main':source('MAIN',main,decl=DECL),'worker':source('WORKER',reader,decl=DECL)}).instantiate(context=ctx)
        result=project.run('MAIN')
        self.assertEqual((result['WORKER']['values']['X'],result['MAIN']['values']['X']),(11,22))
        self.assertEqual(ctx.keyboard.events,[]);ctx.to_config()

    def test_push_pop_suspends_generic_read_and_allows_new_read(self):
        events=[dict(key=key,at_ms=100) for key in line_keys('11')]+[dict(key=key,at_ms=200) for key in line_keys('22')]
        ctx=context(events=events)
        reader=OPEN+'READ f(x,CR)'+CLOSE+' SIGNAL EVENT[1]'
        main="RUN_TASK('WORKER',0,FALSE,FALSE,0,s) DELAY(10) PUSH_KEY_RD('TPKB',KC_DISPLAY,token,s) "+OPEN+'READ f(x,CR)'+CLOSE+" POP_KEY_RD('TPKB',token,s) WAIT FOR EVENT[1]"
        project=translate_project({'main':source('MAIN',main,decl=DECL),'worker':source('WORKER',reader,decl=DECL)}).instantiate(context=ctx)
        result=project.run('MAIN')
        self.assertEqual((result['MAIN']['values']['X'],result['WORKER']['values']['X']),(11,22))
        self.assertEqual(ctx.keyboard.snapshot()['suspensions'],0);ctx.to_config()


if __name__=='__main__':unittest.main()
