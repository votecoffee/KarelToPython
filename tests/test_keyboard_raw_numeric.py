"""Authored fixed-width ASCII numeric input without keyboard line submission."""
import unittest

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_file_cancellation import pending
from tests.test_keyboard import context
from tests.test_keyboard_raw_read import PASSALL, OPEN, CLOSE


DECL='f:FILE n,m,s,count:INTEGER text:STRING[8] value:REAL flag:BOOLEAN b:BYTE small:SHORT'


def prepare(body,keys=(),*,ctx=None,decl=DECL,routines='',**options):
    ctx=context(keys=keys) if ctx is None else ctx
    task,result=compile_program(PASSALL+OPEN+body,decl=decl,context=ctx,routines=routines,**options)
    return task,ctx,result


class KeyboardRawNumericTests(unittest.TestCase):
    def test_adjacent_mixed_fields_finish_without_enter(self):
        task,ctx,_=prepare('READ f(text::2,n::2::16,value::4,flag::3)'+CLOSE,keys=tuple('ID2A1.25OFFtail'))
        values=task.run()
        self.assertEqual((values['TEXT'],values['N'],values['VALUE'],values['FLAG']),('ID',42,1.25,False))
        self.assertEqual([row['key'] for row in ctx.keyboard.events],list('tail'))
        self.assertEqual(len(task.read_requests),1)
        self.assertEqual(values['F']['position'],11)

    def test_supported_scalar_domains(self):
        cases=(('n','-17',-17),('n::3::2','101',5),('b','255',255),('small','-123',-123),
               ('value','1e3',1000.),('flag','TRUE',True),('flag','0',False),('flag','ON',True))
        for target,text,expected in cases:
            with self.subTest(target=target,text=text):
                field=target if '::' in target else target+'::'+str(len(text))
                task,_,_=prepare(f'READ f({field})'+CLOSE,keys=tuple(text))
                self.assertEqual(task.run()[target.split('::')[0].upper()],expected)

    def test_fixed_width_includes_numeric_padding(self):
        task,_,_=prepare('READ f(n::4,m::3)'+CLOSE,keys=tuple(' -7  12'))
        values=task.run()
        self.assertEqual((values['N'],values['M']),(-7,12))

    def test_string_control_bytes_stay_literal_beside_numeric_fields(self):
        task,_,_=prepare('READ f(text::3,n::2)'+CLOSE,keys=('ENTER','DELETE','REFRESH','1','7'))
        values=task.run()
        self.assertEqual((values['TEXT'],values['N']),('\r\x08\x17',17))

    def test_later_bad_number_preserves_all_destinations_and_raw_bytes(self):
        task,ctx,_=prepare("text='old' n=77 READ f(text::2,n::2)",keys=tuple('OKxxZ'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'invalid INTEGER'):task.run()
        handle=task._state.values['F']
        self.assertEqual((task.snapshot()['TEXT'],task.snapshot()['N'],handle.position,handle.status),('old',77,0,1))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],'OKxx')
        self.assertEqual([row['key'] for row in ctx.keyboard.events],['Z'])
        self.assertEqual(len(task.read_requests),1)
        self.assertEqual(task.read_requests[0]['adapter_outcome'],'callback_failed')
        self.assertEqual(ctx.keyboard.snapshot()['active'],[])
        ctx.keyboard.close_all()

    def test_out_of_domain_values_do_not_publish(self):
        for target,text in (('b','256'),('small','32768'),('n','2147483648'),('value','nan'),('value','inf'),('flag','YES')):
            with self.subTest(target=target,text=text):
                task,ctx,_=prepare(f'READ f({target}::{len(text)})',keys=tuple(text))
                before=task.snapshot()[target.upper()]
                with self.assertRaises(rt.KarelRuntimeError):task.run()
                handle=task._state.values['F']
                self.assertEqual((task.snapshot()[target.upper()],handle.position),(before,0))
                self.assertEqual(ctx.keyboard._handles[handle]['pending'],text)
                ctx.keyboard.close_all()

    def test_control_byte_does_not_turn_numeric_input_into_a_submitted_line(self):
        task,ctx,_=prepare('n=77 READ f(n::3)',keys=('1','ENTER','7'))
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        handle=task._state.values['F']
        self.assertEqual((task.snapshot()['N'],handle.position,ctx.keyboard._handles[handle]['pending']),(77,0,'1\r7'))
        ctx.keyboard.close_all()

    def test_invalid_numeric_field_can_be_recovered_as_raw_string(self):
        task,ctx,_=prepare('n=77 READ f(n::3)',keys=tuple('badZ'))
        with self.assertRaises(rt.KarelRuntimeError):task.run()
        state=task._state;handle=state.values['F']
        with rt._numeric_scope('pythonic'):
            list(ctx.keyboard.file_read(state,handle,[state.reference('TEXT')],formats=[(3,)]))
        self.assertEqual((task.snapshot()['TEXT'],task.snapshot()['N'],handle.position),('bad',77,3))
        self.assertEqual([row['key'] for row in ctx.keyboard.events],['Z'])
        ctx.keyboard.close_all()

    def test_numeric_width_must_be_positive_before_consuming_events(self):
        for field in ('n','n::0','flag','value::0'):
            with self.subTest(field=field):
                task,ctx,_=prepare(f'READ f({field})',keys=('7',))
                with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit positive width'):task.run()
                self.assertEqual((len(ctx.keyboard.events),task.read_requests),(1,()))
                self.assertEqual(ctx.keyboard.snapshot()['active'],[])
                ctx.keyboard.close_all()

    def test_uniform_array_format_uses_fixed_numeric_fields(self):
        task,_,_=prepare('READ f(a::2)'+CLOSE,keys=tuple('123456'),decl=DECL+' a:ARRAY[3]OF INTEGER')
        self.assertEqual(task.run()['A'],[12,34,56])

    def test_initialized_queue_entries_use_the_same_numeric_fields(self):
        body='INIT_QUEUE(q) APPEND_QUEUE(7,q,data,n,s) APPEND_QUEUE(9,q,data,n,s) READ f(q::2)'+CLOSE
        task,_,_=prepare(body,keys=tuple('1213'),decl=DECL+' q:QUEUE_TYPE data:ARRAY[2]OF INTEGER')
        values=task.run()
        self.assertEqual(task._state.values['Q'].entries,[(1,12),(2,13)])
        self.assertIsNone(task._state.values['Q'].buffer)
        self.assertEqual(values['DATA'],[7,9])

    def test_selectors_and_formats_are_captured_once(self):
        routines='ROUTINE slot:INTEGER BEGIN count=count+1 RETURN 1 END slot ROUTINE columns:INTEGER BEGIN count=count+1 RETURN 2 END columns'
        task,_,_=prepare('count=0 READ f(a[slot()]::columns())'+CLOSE,keys=tuple('17'),
                         decl=DECL+' a:ARRAY[1]OF INTEGER',routines=routines)
        values=task.run()
        self.assertEqual((values['A'],values['COUNT']),([17],2))

    def test_pause_retains_partial_numeric_field(self):
        ctx=context(events=[dict(key='1'),dict(key='7',at_ms=25)])
        task,_,_=prepare('n=77 READ f(n::2)'+CLOSE,ctx=ctx,
                         sleep=lambda _:setattr(task._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):task.run()
        self.assertEqual(task.snapshot()['N'],77)
        self.assertEqual(ctx.keyboard._handles[task._state.values['F']]['pending'],'1')
        task._state._sleep=lambda _:None
        task.resume()
        self.assertEqual(task.snapshot()['N'],17)
        ctx.to_config()

    def test_cancel_retains_partial_numeric_field(self):
        ctx=context(keys=('1',))
        project,task,handle=pending(ctx,PASSALL+OPEN+'n=77 READ f(n::2) s=IO_STATUS(f)',decl=DECL)
        for _ in range(30):
            if ctx.keyboard._handles[handle]['pending']=='1':break
            project.scheduler.step()
        rt.cancel_file(task._state,handle)
        project.scheduler.run()
        self.assertEqual((task.snapshot()['N'],task.snapshot()['S'],handle.position),(77,6,0))
        self.assertEqual(ctx.keyboard._handles[handle]['pending'],'1')
        self.assertEqual(ctx.keyboard.snapshot()['active'],[])
        ctx.keyboard.close_all()


if __name__=='__main__':unittest.main()
