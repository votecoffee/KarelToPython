"""Authored atomic PASSALL fixed fields and explicitly requested CR discards."""
import unittest

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_file_cancellation import pending
from tests.test_keyboard import context
from tests.test_keyboard_raw_numeric import DECL
from tests.test_keyboard_raw_read import PASSALL, OPEN, CLOSE


def build(body,keys=(),*,ctx=None,eol=10,decl=DECL,**options):
    ctx=context(keys=keys) if ctx is None else ctx
    task,result=compile_program(PASSALL+f'SET_FILE_ATR(f,ATR_EOL,{eol}) '+OPEN+body,
                                decl=decl,context=ctx,**options)
    return task,ctx,result


class KeyboardRawRecordTests(unittest.TestCase):
    def test_fixed_field_then_cr_discards_remainder_and_counts_all_bytes(self):
        task,ctx,_=build('READ f(n::2,CR)'+CLOSE,keys=tuple('17garbage')+('ENTER',)+tuple('later'))
        values=task.run()
        self.assertEqual((values['N'],values['F']['position']),(17,10))
        self.assertEqual([row['key'] for row in ctx.keyboard.events],list('later'))
        self.assertEqual(ctx.keyboard.history[-1]['data']['bytes'],10)
        self.assertEqual(task.read_requests[0]['line_breaks'],[1])

    def test_leading_and_repeated_cr_markers_preserve_field_order(self):
        keys=tuple('skip')+('ENTER','ENTER')+tuple('17rest')+('ENTER','ENTER')+tuple('29')
        task,ctx,_=build('READ f(CR,CR,n::2,CR,CR,m::2)'+CLOSE,keys=keys)
        values=task.run()
        self.assertEqual((values['N'],values['M'],values['F']['position']),(17,29,len(keys)))
        self.assertEqual(ctx.keyboard.events,[])
        self.assertEqual(task.read_requests[0]['line_breaks'],[0,0,1,1])

    def test_cr_only_read_consumes_one_record(self):
        task,ctx,_=build('READ f(CR)'+CLOSE,keys=tuple('skip')+('ENTER','Z'))
        values=task.run()
        self.assertEqual(values['F']['position'],5)
        self.assertEqual([row['key'] for row in ctx.keyboard.events],['Z'])
        self.assertEqual(task.read_requests[0]['targets'],[])
        self.assertEqual(ctx.keyboard.history[-1]['data']['fields'],0)

    def test_queue_entry_input_and_cr_publish_as_one_request(self):
        body='INIT_QUEUE(q) APPEND_QUEUE(7,q,data,n,s) APPEND_QUEUE(9,q,data,n,s) READ f(q::2,CR)'+CLOSE
        task,_,_=build(body,keys=tuple('1213skip')+('ENTER',),decl=DECL+' q:QUEUE_TYPE data:ARRAY[2]OF INTEGER')
        values=task.run()
        self.assertEqual(task._state.values['Q'].entries,[(1,12),(2,13)])
        self.assertIsNone(task._state.values['Q'].buffer)
        self.assertEqual((values['DATA'],values['F']['position']),([7,9],9))
        self.assertEqual(task.read_requests[0]['line_breaks'],[2])

    def test_literal_enter_inside_a_fixed_string_is_not_a_record_marker(self):
        task,ctx,_=build('READ f(text::3,n::2,CR)'+CLOSE,keys=('a','ENTER','b','1','7','ENTER','Z'))
        values=task.run()
        self.assertEqual((values['TEXT'],values['N'],values['F']['position']),('a\rb',17,6))
        self.assertEqual([row['key'] for row in ctx.keyboard.events],['Z'])

    def test_custom_printable_delimiter_and_quoted_field(self):
        task,ctx,_=build('READ f(text::5::2,CR,n::2::16,CR)'+CLOSE,keys=tuple("'a;b'ignored;2A;Z"),eol=59)
        values=task.run()
        self.assertEqual((values['TEXT'],values['N']),('a;b',42))
        self.assertEqual([row['key'] for row in ctx.keyboard.events],['Z'])

    def test_delete_and_refresh_can_be_explicit_raw_terminators(self):
        for code,key in ((8,'DELETE'),(23,'REFRESH'),(13,'ENTER'),(10,'ENTER')):
            with self.subTest(code=code):
                task,ctx,_=build('READ f(n::2,CR)'+CLOSE,keys=tuple('17skip')+(key,'Z'),eol=code)
                self.assertEqual(task.run()['N'],17)
                self.assertEqual([row['key'] for row in ctx.keyboard.events],['Z'])

    def test_noninjectable_cr_terminator_rejects_before_consuming_keys(self):
        for code in (0,9,127):
            with self.subTest(code=code):
                task,ctx,_=build('READ f(n::2,CR)',keys=('1','7','ENTER'),eol=code)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'injectable ASCII terminator'):task.run()
                self.assertEqual((len(ctx.keyboard.events),task.read_requests),(3,()))
                self.assertEqual(ctx.keyboard.snapshot()['active'],[])
                ctx.keyboard.close_all()

    def test_missing_terminator_preserves_the_ready_numeric_field(self):
        task,ctx,_=build('n=77 READ f(n::2,CR)',keys=('1','7'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit queued input'):task.run()
        handle=task._state.values['F']
        self.assertEqual((task.snapshot()['N'],handle.position),(77,0))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],'17')
        self.assertEqual(ctx.keyboard.snapshot()['active'],[])
        ctx.keyboard.close_all()

    def test_invalid_later_field_retains_fields_and_discarded_bytes_together(self):
        keys=tuple('17first')+('ENTER',)+tuple('xxsecond')+('ENTER','Z')
        task,ctx,_=build('n=77 m=88 READ f(n::2,CR,m::2,CR)',keys=keys)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid INTEGER'):task.run()
        handle=task._state.values['F']
        self.assertEqual((task.snapshot()['N'],task.snapshot()['M'],handle.position),(77,88,0))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],'17first\rxxsecond\r')
        self.assertEqual([row['key'] for row in ctx.keyboard.events],['Z'])
        self.assertEqual(len(task.read_requests),1)
        ctx.keyboard.close_all()

    def test_pause_before_terminator_does_not_publish_the_numeric_field(self):
        ctx=context(events=[dict(key='1'),dict(key='7'),dict(key='ENTER',at_ms=25)])
        task,_,_=build('n=77 READ f(n::2,CR)'+CLOSE,ctx=ctx,
                       sleep=lambda _:setattr(task._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(task.snapshot()['N'],77)
        self.assertEqual(ctx.keyboard._handles[task._state.values['F']]['pending'],'17')
        task._state._sleep=lambda _:None
        task.resume()
        self.assertEqual(task.snapshot()['N'],17)
        ctx.to_config()

    def test_cancel_while_discarding_retains_complete_prefix(self):
        ctx=context(keys=tuple('17discard'))
        project,task,handle=pending(ctx,PASSALL+OPEN+'n=77 READ f(n::2,CR) s=IO_STATUS(f)',decl=DECL)
        for _ in range(60):
            if ctx.keyboard._handles[handle]['pending']=='17discard':break
            project.scheduler.step()
        rt.cancel_file(task._state,handle)
        project.scheduler.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['S'],handle.position),(77,6,0))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],'17discard')
        self.assertEqual(ctx.keyboard.snapshot()['active'],[])
        ctx.keyboard.close_all()

    def test_cr_minimum_bytes_participate_in_preflight(self):
        fields=['text::254']*16+['CR']*33
        task,ctx,_=build('READ f('+','.join(fields)+')',keys=('a',))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'4096 raw bytes'):task.run()
        self.assertEqual((len(ctx.keyboard.events),task.read_requests),(1,()))
        ctx.keyboard.close_all()

    def test_exact_raw_buffer_limit_includes_terminator(self):
        task,ctx,_=build('READ f(CR)'+CLOSE,keys=tuple('a'*4095)+('ENTER',))
        self.assertEqual(task.run()['F']['position'],4096)
        self.assertEqual(ctx.keyboard.history[-1]['data']['bytes'],4096)

    def test_missing_terminator_at_buffer_limit_preserves_next_event(self):
        task,ctx,_=build('READ f(CR)',keys=tuple('a'*4096))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'4096 raw bytes'):task.run()
        state=task._state;handle=state.values['F']
        self.assertEqual((handle.position,len(ctx.keyboard._handles[handle]['pending'])),(0,4096))
        ctx.keyboard.feed('ENTER')
        with rt._numeric_scope('pythonic'):
            with self.assertRaisesRegex(rt.KarelRuntimeError,'4096 raw bytes'):
                list(ctx.keyboard.file_read(state,handle,[],line_breaks=[0]))
        self.assertEqual([row['key'] for row in ctx.keyboard.events],['ENTER'])
        ctx.keyboard.close_all()

    def test_history_sample_excludes_unconsumed_retained_suffix(self):
        task,ctx,_=build('READ f(text::6)',keys=('a','ENTER','b','ENTER','x','LEFT','Z'))
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        state=task._state;handle=state.values['F']
        with rt._numeric_scope('pythonic'):
            list(ctx.keyboard.file_read(state,handle,[],line_breaks=[0]))
        self.assertEqual((handle.position,ctx.keyboard._handles[handle]['pending']),(2,'b\rx'))
        data=ctx.keyboard.history[-1]['data']
        self.assertEqual((data['bytes'],data['sample_hex']),(2,b'a\r'.hex()))
        self.assertEqual([row['key'] for row in ctx.keyboard.events],['Z'])
        ctx.keyboard.close_all()


if __name__=='__main__':unittest.main()
