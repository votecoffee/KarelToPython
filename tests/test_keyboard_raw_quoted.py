"""Authored bounded quoted STRING fields in injected PASSALL keyboard input."""
import unittest

from karel2py import runtime as rt, translate_project
from tests.test_file_cancellation import pending
from tests.test_keyboard import context
from tests.test_keyboard_raw_numeric import prepare, DECL
from tests.test_keyboard_raw_read import PASSALL, OPEN, CLOSE
from tests.test_project_scheduler import source


class KeyboardRawQuotedTests(unittest.TestCase):
    def test_mixed_quoted_numeric_and_literal_fields_without_enter(self):
        text="'O''Brien'2AOK"
        task,ctx,_=prepare('READ f(text::10::2,n::2::16,other::2)'+CLOSE,keys=tuple(text+'tail'),
                           decl=DECL+' other:STRING[8]')
        values=task.run()
        self.assertEqual((values['TEXT'],values['N'],values['OTHER']),("O'Brien",42,'OK'))
        self.assertEqual([row['key'] for row in ctx.keyboard.events],list('tail'))
        self.assertEqual((len(task.read_requests),values['F']['position']),(1,14))

    def test_empty_escaped_and_padded_fields(self):
        for text,expected in (("''",''),("''''","'"),("  'a'  ",'a'),("'x''y'","x'y")):
            with self.subTest(text=text):
                task,_,_=prepare(f'READ f(text::{len(text)}::2)'+CLOSE,keys=tuple(text))
                self.assertEqual(task.run()['TEXT'],expected)

    def test_decoded_text_truncates_after_consuming_complete_field(self):
        task,_,_=prepare('READ f(text::8::2,n::2)'+CLOSE,keys=tuple("'abcdef'17"),decl=DECL.replace('STRING[8]','STRING[3]'))
        values=task.run()
        self.assertEqual((values['TEXT'],values['N'],values['F']['position']),('abc',17,10))

    def test_unquoted_format_keeps_quote_characters_literal(self):
        task,_,_=prepare('READ f(text::3::0)'+CLOSE,keys=tuple("'a'"))
        self.assertEqual(task.run()['TEXT'],"'a'")

    def test_malformed_quoted_field_retains_every_destination_and_prefix(self):
        for text in ("abcde","'abc ","'a'xx"):
            with self.subTest(text=text):
                task,ctx,_=prepare("n=77 text='old' READ f(n::2,text::5::2)",keys=tuple('17'+text+'Z'))
                with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid quoted STRING'):task.run()
                handle=task._state.values['F']
                self.assertEqual((task.snapshot()['N'],task.snapshot()['TEXT'],handle.position,handle.status),(77,'old',0,1))
                self.assertEqual(ctx.keyboard._handles[handle]['pending'],'17'+text)
                self.assertEqual([row['key'] for row in ctx.keyboard.events],['Z'])
                self.assertEqual(len(task.read_requests),1)
                self.assertEqual(ctx.keyboard.snapshot()['active'],[])
                ctx.keyboard.close_all()

    def test_quoted_input_can_be_recovered_as_literal_bytes_after_error(self):
        task,ctx,_=prepare('READ f(text::5::2)',keys=tuple("'bad "))
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        state=task._state;handle=state.values['F']
        with rt._numeric_scope('pythonic'):
            list(ctx.keyboard.file_read(state,handle,[state.reference('TEXT')],formats=[(5,)]))
        self.assertEqual((task.snapshot()['TEXT'],handle.position),("'bad ",5))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],'')
        ctx.keyboard.close_all()

    def test_width_includes_padding_after_the_closing_quote(self):
        ctx=context(events=[dict(key=key) for key in "'a'"]+[dict(key=' ',at_ms=25),dict(key=' ',at_ms=25)])
        task,_,_=prepare("text='old' READ f(text::5::2)"+CLOSE,ctx=ctx,
                         sleep=lambda _:setattr(task._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(task.snapshot()['TEXT'],'old')
        self.assertEqual(ctx.keyboard._handles[task._state.values['F']]['pending'],"'a'")
        task._state._sleep=lambda _:None
        task.resume()
        self.assertEqual(task.snapshot()['TEXT'],'a')
        ctx.to_config()

    def test_width_preflight_requires_room_for_both_quotes(self):
        for width in (0,1):
            with self.subTest(width=width):
                task,ctx,_=prepare(f'READ f(text::{width}::2)',keys=tuple("'a'"))
                with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit width in 2..254'):task.run()
                self.assertEqual((len(ctx.keyboard.events),task.read_requests),(3,()))
                ctx.keyboard.close_all()

    def test_uniform_quoted_array_fields(self):
        task,_,_=prepare('READ f(labels::3::2)'+CLOSE,keys=tuple("'a''b'"),decl=DECL+' labels:ARRAY[2]OF STRING[4]')
        self.assertEqual(task.run()['LABELS'],['a','b'])

    def test_quoted_field_cannot_cross_a_physical_record_separator(self):
        task,ctx,_=prepare("text='old' READ f(text::5::2)",keys=("'",'a','ENTER','b',"'"))
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        handle=task._state.values['F']
        self.assertEqual((task.snapshot()['TEXT'],handle.position),('old',0))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],"'a\rb'")
        ctx.keyboard.close_all()

    def test_cancel_keeps_partial_quoted_field_without_publishing(self):
        ctx=context(keys=("'",'a'))
        project,task,handle=pending(ctx,PASSALL+OPEN+"text='old' READ f(text::3::2) s=IO_STATUS(f)",decl=DECL)
        for _ in range(30):
            if ctx.keyboard._handles[handle]['pending']=="'a":break
            project.scheduler.step()
        rt.cancel_file(task._state,handle)
        project.scheduler.run()
        self.assertEqual((task.snapshot()['TEXT'],task.snapshot()['S'],handle.position),('old',6,0))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],"'a")
        ctx.keyboard.close_all()

    def test_linked_borrowed_file_and_string_use_quoted_field(self):
        main=source('MAIN',PASSALL+OPEN+'take(f,text)'+CLOSE,decl=DECL,
                    routines='ROUTINE take(channel:FILE;label:STRING) FROM LIB')
        library=source('LIB','',routines='ROUTINE take(channel:FILE;label:STRING) BEGIN READ channel(label::6::2) END take')
        ctx=context(keys=tuple("'A''B'"))
        project=translate_project({'main':main,'lib':library}).instantiate(context=ctx)
        self.assertEqual(project.run('MAIN')['MAIN']['values']['TEXT'],"A'B")
        ctx.to_config()


if __name__=='__main__':unittest.main()
