"""Retain edited/raw keyboard FILE read ownership across waits and pauses."""
import unittest

from karel2py import runtime as rt,translate_project
from tests.test_extended_services import compile_program
from tests.test_file_cancellation import pending
from tests.test_keyboard import context
from tests.test_keyboard_raw_numeric import DECL
from tests.test_keyboard_raw_read import PASSALL, OPEN, CLOSE
from tests.test_project_scheduler import source


def waiting(raw=False):
    ctx=context(keys=('1',))
    prefix=PASSALL if raw else ''
    field='n::2' if raw else 'n,CR'
    project,task,handle=pending(ctx,prefix+OPEN+f'n=77 READ f({field}) s=IO_STATUS(f)'+CLOSE,decl=DECL)
    for _ in range(30):
        if not ctx.keyboard.events:break
        project.scheduler.step()
    job=ctx.keyboard._handles[handle]['_file_read_job']
    return project,task,handle,job


class KeyboardFileBindingTests(unittest.TestCase):
    def test_replaced_binding_during_wait_cannot_publish_input(self):
        for raw in (False,True):
            with self.subTest(raw=raw):
                ctx=context(events=[dict(key='1'),dict(key='7',at_ms=25),dict(key='ENTER',at_ms=25)])
                prefix=PASSALL if raw else ''
                field='n::2' if raw else 'n,CR'
                changed=[]

                def replace(_):
                    if not changed:
                        handle=task._state.values['F']
                        original=ctx.keyboard._handles[handle]
                        ctx.keyboard._handles[handle]=dict(original)
                        changed.append(original)

                task,_=compile_program(prefix+OPEN+f'n=77 READ f({field})',decl=DECL,context=ctx,sleep=replace)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Keyboard FILE READ identity or registration changed'):
                    task.run()
                handle=task._state.values['F']
                self.assertEqual((task.snapshot()['N'],handle.position),(77,0))
                self.assertEqual([row['key'] for row in ctx.keyboard.events],['7','ENTER'])
                self.assertEqual(ctx.keyboard._active,{})
                self.assertIn('_file_read_job',ctx.keyboard._handles[handle])
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Finish or stop'):ctx.keyboard.close(handle)

    def test_binding_mutations_reject_cancellation_before_marking(self):
        def row(bank,handle):
            old=bank._handles[handle];bank._handles[handle]=dict(old)
            return lambda:bank._handles.__setitem__(handle,old)
        def handles(bank,handle):
            old=bank._handles;bank._handles=dict(old)
            return lambda:setattr(bank,'_handles',old)
        def past(bank,handle):
            old=bank._handles[handle]['past'];bank._handles[handle]['past']=[]
            return lambda:bank._handles[handle].__setitem__('past',old)
        def pane(bank,handle):
            bank._handles[handle]['pane']=2
            return lambda:bank._handles[handle].__setitem__('pane',1)
        def mode(bank,handle):
            old=bank._handles[handle]['input_mode'];bank._handles[handle]['input_mode']='other'
            return lambda:bank._handles[handle].__setitem__('input_mode',old)
        def echo(bank,handle):
            old=bank._handles[handle]['echo'];bank._handles[handle]['echo']=object()
            return lambda:bank._handles[handle].__setitem__('echo',old)
        def cursor(bank,handle):
            handle.position=1
            return lambda:setattr(handle,'position',0)
        def flag_type(bank,handle):
            handle.noecho=0
            return lambda:setattr(handle,'noecho',False)
        for raw in (False,True):
            for mutate in (row,handles,past,pane,mode,echo,cursor,flag_type):
                with self.subTest(raw=raw,mutation=mutate.__name__):
                    project,task,handle,_=waiting(raw)
                    bank=project.context.keyboard
                    before=bank._handles[handle]['pending']
                    restore=mutate(bank,handle)
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'identity|registration|binding|cursor'):
                        rt.cancel_file(task._state,handle)
                    self.assertFalse(handle._read_operation['cancelled'])
                    restore()
                    rt.cancel_file(task._state,handle)
                    project.scheduler.run()
                    self.assertEqual((task.snapshot()['N'],task.snapshot()['S']),(77,6))
                    self.assertEqual(bank._active,{})
                    self.assertEqual(before,'1' if raw else '')
                    project.context.to_config()

    def test_pause_keeps_original_file_binding(self):
        for raw in (False,True):
            with self.subTest(raw=raw):
                project,task,handle,_=waiting(raw)
                task.pause()
                for _ in range(30):
                    project.scheduler.step()
                    if task.task_state=='paused':break
                self.assertEqual(task.task_state,'paused')
                bank=project.context.keyboard
                bank._handles[handle]=dict(bank._handles[handle])
                bank.feed('7');bank.feed('ENTER')
                project.scheduler.continue_task('MAIN')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Keyboard FILE READ identity or registration'):
                    project.scheduler.run()
                self.assertEqual(task.snapshot()['N'],77)
                self.assertEqual([row['key'] for row in bank.events],['7','ENTER'])

    def test_replaced_active_registry_and_slot_remain_reserved(self):
        for replace_map in (False,True):
            with self.subTest(replace_map=replace_map):
                project,task,handle,job=waiting(True)
                bank=project.context.keyboard
                owned=bank._active
                replacement=dict(owned) if replace_map else dict(job)
                if replace_map:bank._active=replacement
                else:bank._active[job['id']]=replacement
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Keyboard FILE READ identity or registration'):
                    project.scheduler.run()
                self.assertEqual((task.snapshot()['N'],handle.position),(77,0))
                if replace_map:
                    self.assertIs(bank._active,replacement)
                    self.assertIs(replacement[job['id']],job)
                else:self.assertIs(bank._active[job['id']],replacement)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Finish or stop'):bank.close(handle)

    def test_removed_active_slot_does_not_make_file_available_to_new_reader(self):
        project,task,handle,job=waiting(True)
        bank=project.context.keyboard
        bank._active.pop(job['id'])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Keyboard FILE READ identity or registration'):
            project.scheduler.run()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'already has an active read'):
            list(bank.file_read(task._state,handle,[task._state.reference('M')],formats=[(2,)]))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Finish or stop'):bank.close(handle)
        args=[handle,task._state.reference('TEXT'),8,1,8,0,'',task._state.reference('COUNT'),
              task._state.reference('M'),task._state.reference('S')]
        list(bank.read(task._state,args))
        self.assertEqual(task.snapshot()['S'],2)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cooperative FILE registration'):
            rt.cancel_file(task._state,handle)

    def test_direct_host_generator_keeps_its_own_claim(self):
        ctx=context(keys=('1',))
        task,_=compile_program(PASSALL+OPEN,decl=DECL,context=ctx)
        task.run();state=task._state;handle=state.values['F'];state._scheduler=rt.TaskScheduler()
        reader=ctx.keyboard.file_read(state,handle,[state.reference('N')],formats=[(2,)])
        with rt._numeric_scope('pythonic'):
            for _ in range(20):
                next(reader)
                if not ctx.keyboard.events:break
            ctx.keyboard._handles[handle]=dict(ctx.keyboard._handles[handle])
            with self.assertRaisesRegex(rt.KarelRuntimeError,'Keyboard FILE READ identity or registration'):
                for _ in range(50):next(reader)
        self.assertEqual(state.values['N'],rt.UNINITIALIZED)
        self.assertEqual(ctx.keyboard._active,{})

    def test_ordinary_feed_completes_and_releases_the_claim(self):
        for raw in (False,True):
            with self.subTest(raw=raw):
                project,task,handle,_=waiting(raw)
                bank=project.context.keyboard
                binding=bank._handles[handle]
                bank.feed('7');bank.feed('ENTER')
                project.scheduler.run()
                self.assertEqual((task.snapshot()['N'],task.snapshot()['S']),(17,0))
                self.assertNotIn('_file_read_job',binding)
                self.assertEqual(bank._active,{})
                project.context.to_config()

    def test_failure_history_and_cleanup_keep_the_original_job_metadata(self):
        for raw in (False,True):
            with self.subTest(raw=raw):
                project,task,handle,job=waiting(raw)
                bank=project.context.keyboard
                number=job['id']
                job.update(id=number+100,state=None,operation='FOREIGN',pane=2)
                bank.feed('7');bank.feed('ENTER')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Keyboard FILE READ identity or registration'):
                    project.scheduler.run()
                self.assertEqual((task.snapshot()['N'],handle.position),(77,0))
                self.assertEqual([row['key'] for row in bank.events],['7','ENTER'])
                record=bank.history[-1]
                self.assertEqual((record['request'],record['program'],record['operation'],record['pane']),
                                 (number,'MAIN','FILE_READ',1))
                self.assertEqual(bank._active,{})
                bank.close(handle)

    def test_predefined_cleanup_preflights_uncertain_read_before_closing_output(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(),keyboard=rt.KeyboardInput(events=[dict(key='1')]),
            predefined_files={'OUTPUT':dict(name='out',mode='WO'),
                              'INPUT':dict(name='KB:TPKB',mode='RO',attributes=dict(passall=True))})
        project=translate_project({'main':source('MAIN','WRITE OUTPUT(1) n=77 READ INPUT(n::2)',decl='n:INTEGER')}).instantiate(context=ctx)
        project.scheduler.start('MAIN')
        for _ in range(50):
            project.scheduler.step()
            if ctx.keyboard._active:break
        job=next(iter(ctx.keyboard._active.values()))
        ctx.keyboard._active.pop(job['id'])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Keyboard FILE READ identity or registration'):
            project.scheduler.run()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Predefined FILE has a pending READ'):
            ctx.close_predefined_files()
        self.assertIs(ctx._predefined_values['OUTPUT'].owner,ctx.files)
        self.assertIs(ctx._predefined_values['INPUT'].owner,ctx.keyboard)


if __name__=='__main__':unittest.main()
