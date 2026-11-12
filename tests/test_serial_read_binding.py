"""Keep pending serial READs on their original explicitly supplied endpoint."""
import unittest

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_serial_waits import pending_project


def streams(reclaim=False):
    return rt.SerialStreams({2:dict(input=b'1',wait=True,reclaim_input=reclaim,capacity=32)},limit=64)


def waiting(bank):
    project=pending_project(bank)
    task=project.programs['MAIN']
    return project,task,task._state.values['F']


class SerialReadBindingTests(unittest.TestCase):
    def test_replaced_buffer_between_polls_is_not_consumed(self):
        for reclaim in (False,True):
            with self.subTest(reclaim=reclaim):
                bank=streams(reclaim)
                original=bank.files['P2:']
                replacement=bytearray(b'27\n')

                def replace(_):
                    bank.files['P2:']=replacement

                task,_=compile_program("n=77 OPEN FILE f('RO','P2:') READ f(n,CR)",decl='f:FILE n:INTEGER',
                                       context=rt.ExecutionContext(serial_streams=bank),sleep=replace)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Serial pending READ source'):
                    task.run()
                self.assertEqual((task.snapshot()['N'],task._state.values['F'].position),(77,0))
                self.assertEqual((original,replacement),(b'1',b'27\n'))
                self.assertEqual(bank._pending,{})
                self.assertIsNone(task._state.values['F']._read_operation)

    def test_replaced_registries_and_limits_reject_before_publication(self):
        def buffer(bank):bank.files['P2:']=bytearray(b'27\n')
        def files(bank):bank.files=dict(bank.files)
        def ports(bank):bank.ports=dict(bank.ports)
        def port(bank):bank.ports[2]=dict(bank.ports[2])
        def opened(bank):bank._open=dict(bank._open)
        def capacity(bank):bank.ports[2]['capacity']=33
        def limit(bank):bank.limit=65
        def output(bank):bank.ports[2]['output']=bytearray(b'new')
        for mutate in (buffer,files,ports,port,opened,capacity,limit,output):
            with self.subTest(mutate=mutate.__name__):
                bank=streams()
                project,task,handle=waiting(bank)
                original=bank.files['P2:']
                mutate(bank)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'Serial pending READ'):
                    project.scheduler.run()
                self.assertEqual((task.snapshot()['N'],handle.position,len(task.read_requests)),(77,0,0))
                self.assertEqual(original,b'1')
                self.assertEqual(bank._pending,{})

    def test_changed_binding_rejects_cancellation_without_setting_cancel_flag(self):
        bank=streams()
        project,task,handle=waiting(bank)
        original=bank.files['P2:']
        bank.files['P2:']=bytearray(b'27\n')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Serial pending READ source'):
            rt.cancel_file(task._state,handle)
        self.assertFalse(handle._read_operation['cancelled'])
        bank.files['P2:']=original
        rt.cancel_file(task._state,handle)
        project.scheduler.run()
        self.assertEqual((task.snapshot()['N'],bank.files['P2:']),(77,b'1'))
        self.assertEqual(bank._pending,{})

    def test_replaced_pending_registry_is_preserved_on_unwind(self):
        bank=streams()
        project,task,handle=waiting(bank)
        owned=bank._pending
        replacement=dict(owned)
        record=owned[id(handle)]
        bank._pending=replacement
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Serial pending READ registration'):
            project.scheduler.run()
        self.assertIs(bank._pending,replacement)
        self.assertIs(replacement[id(handle)],record)
        self.assertIs(owned[id(handle)],record)
        self.assertEqual((task.snapshot()['N'],bank.files['P2:']),(77,b'1'))

    def test_pause_preserves_original_source_binding(self):
        bank=streams(True)
        project,task,handle=waiting(bank)
        task.pause()
        for _ in range(30):
            project.scheduler.step()
            if task.task_state=='paused':break
        self.assertEqual(task.task_state,'paused')
        bank.files['P2:']=bytearray(b'27\n')
        project.scheduler.continue_task('MAIN')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Serial pending READ source'):
            project.scheduler.run()
        self.assertEqual((task.snapshot()['N'],handle.position),(77,0))
        self.assertEqual(bank.files['P2:'],b'27\n')

    def test_feeds_and_finalization_keep_the_original_binding(self):
        for reclaim in (False,True):
            with self.subTest(reclaim=reclaim):
                bank=streams(reclaim)
                project,task,_=waiting(bank)
                original=bank.files['P2:']
                bank.feed(2,b'7')
                bank.finish_input(2)
                project.scheduler.run()
                self.assertEqual(task.snapshot()['N'],17)
                self.assertIs(bank.files['P2:'],original)
                self.assertEqual((bank.used(),bank._pending),(0,{}))

if __name__=='__main__':unittest.main()
