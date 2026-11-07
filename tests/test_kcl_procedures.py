"""Authored bounded KCL command procedures through file and scheduler services."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_directive_group_locks import program
from tests.test_kcl_task_commands import issue
from tests.test_task_control_broadcasts import worker


def context(files, *, scheduler=None, **options):
    return rt.ExecutionContext(files=files, tasks=scheduler, kcl=rt.KclCommands(
        procedure_commands=True, file_commands=True, variable_commands=True,
        task_commands=True, **options))


class KclProcedureTests(unittest.TestCase):
    def test_include_expansion_verify_and_complete_listing(self):
        ctx = context(rt.MemoryFiles({
            'scripts/start.CF': b'> %INCLUDE parts -- include\r\nSET VERIFY OFF\r\nTYPE part.txt\r\n',
            'scripts/parts.CF': b'> SET VAR [CACHE]LABEL = "A -- B" -- comment\n',
            'part.txt': b'ready\n',
        }))
        ref=ctx.variables.define('CACHE','LABEL',('STRING',12),'old')
        output=[]
        self.assertEqual(issue(ctx,'RUNCF scripts/start result',write=output.append)['S'],0)
        self.assertEqual(ref.raw(),'A -- B')
        self.assertEqual(output,[])
        self.assertEqual(ctx.files.snapshot()['result.LS'],
                         b'SET VAR [CACHE]LABEL = "A -- B"\nSET VERIFY OFF\nready\n')
        self.assertEqual([row['command'] for row in ctx.kcl.history],['RUNCF scripts/start result'])
        self.assertFalse(ctx.kcl.verify)
        restored=rt.ExecutionContext.from_config(ctx.to_config())
        self.assertFalse(restored.kcl.verify)
        self.assertEqual(issue(restored,'SET VERIFY ON')['S'],0)
        self.assertTrue(restored.kcl.verify)

    def test_failed_command_stops_in_order_without_publishing_listing(self):
        ctx=context(rt.MemoryFiles({
            'start.CF':'COPY seed.txt TO first.txt\nFAIL\nCOPY seed.txt TO second.txt\n',
            'seed.txt':'ready',
        }), replies={'FAIL':{'status':17}})
        self.assertEqual(issue(ctx,'RUNCF start log')['S'],17)
        self.assertEqual(ctx.files.snapshot()['first.txt'],b'ready')
        self.assertNotIn('second.txt',ctx.files.files)
        self.assertNotIn('log.LS',ctx.files.files)
        self.assertEqual(ctx.kcl.history[-1]['status'],17)
        self.assertEqual(issue(ctx,'RUNCF start',nowait=True),{'S':3,'N':3})

    def test_preflight_rejects_missing_nested_cyclic_and_oversize_inputs_before_effects(self):
        cases=[
            ('%INCLUDE missing',{},701),
            ('%INCLUDE ../escape',{},702),
            ('%INCLUDE child extra',{},702),
            ('RUNCF child',{'child.CF':b''},706),
            ('%INCLUDE child',{'child.CF':b'%INCLUDE start\n'},706),
            ('%INCLUDE child',{'child.CF':b'\xff'},702),
            ('%INCLUDE child',{'child.CF':b' '*65536},705),
            ('TYPE seed.txt\n'*256,{},705),
        ]
        for ending,files,status in cases:
            with self.subTest(ending=ending[:40],status=status):
                ctx=context(rt.MemoryFiles({'start.CF':'COPY seed.txt TO new.txt\n'+ending,
                                            'seed.txt':'ready',**files}))
                before=ctx.files.snapshot()
                self.assertEqual(issue(ctx,'RUNCF start log')['S'],status)
                self.assertEqual(ctx.files.snapshot(),before)

    def test_opt_in_and_exact_reply_precedence(self):
        ctx=rt.ExecutionContext(kcl=rt.KclCommands({'RUNCF scripted':{'status':17}}))
        self.assertEqual(issue(ctx,'RUNCF scripted')['S'],17)
        self.assertEqual(issue(ctx,'runCF scripted')['S'],1)
        self.assertEqual(issue(ctx,'SET VERIFY OFF')['S'],1)
        for config in ({'verify':False},{'procedure_commands':1},
                       {'procedure_commands':True,'verify':0}):
            with self.subTest(config=config),self.assertRaises(ValueError):
                rt.KclCommands.from_config(config)

    def test_listing_collision_at_entry_and_after_command_effects(self):
        ctx=context(rt.MemoryFiles({'start.CF':'COPY seed.txt TO log.LS',
                                    'seed.txt':'ready','exists.LS':'old'}))
        self.assertEqual(issue(ctx,'RUNCF start exists')['S'],703)
        self.assertNotIn('log.LS',ctx.files.files)
        self.assertEqual(issue(ctx,'RUNCF start log')['S'],703)
        self.assertEqual(ctx.files.snapshot()['log.LS'],b'ready')
        self.assertEqual(ctx.files.snapshot()['exists.LS'],b'old')

    def test_procedure_output_is_bounded_for_both_sinks(self):
        ctx=context(rt.MemoryFiles({'start.CF':'TYPE large.txt','large.txt':b'x'*66000}),verify=False)
        output=[]
        self.assertEqual(issue(ctx,'RUNCF start',write=output.append)['S'],705)
        self.assertLessEqual(sum(map(len,output)),65536)
        self.assertEqual(issue(ctx,'RUNCF start log')['S'],705)
        self.assertNotIn('log.LS',ctx.files.files)

    def test_rooted_include_budget_is_checked_before_opening_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            (root/'start.CF').write_bytes(b'COPY seed.txt TO copied.txt\n%INCLUDE child\n')
            child=root/'child.CF'
            child.write_bytes(b'-- '+b' ' * 16384+b'\n')
            (root/'seed.txt').write_bytes(b'ready')
            ctx=context(rt.DirectoryFiles(root))
            task=program("KCL('RUNCF start result',s)",context=ctx)
            original_open=Path.open
            def reject_child_open(path,*args,**kwargs):
                if path==child:self.fail('RUNCF opened an include before charging')
                return original_open(path,*args,**kwargs)
            with patch.object(Path,'open',new=reject_child_open):
                self.assertEqual(task.run(max_steps=6)['S'],4)
            self.assertFalse((root/'copied.txt').exists())
            self.assertFalse((root/'result.LS').exists())
            self.assertEqual(issue(ctx,'RUNCF start result')['S'],0)
            self.assertEqual((root/'copied.txt').read_bytes(),b'ready')

    def test_rooted_include_listing_and_publication_race(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'Jobs').mkdir()
            (root/'Jobs'/'start.CF').write_bytes(b'%INCLUDE child\n')
            (root/'Jobs'/'child.CF').write_bytes(b'TYPE part.txt\n')
            (root/'Jobs'/'part.txt').write_bytes(b'ready')
            ctx=context(rt.DirectoryFiles(root))
            self.assertEqual(issue(ctx,'CD Jobs')['S'],0)
            self.assertEqual(issue(ctx,'RUNCF start out')['S'],0)
            self.assertEqual((root/'Jobs'/'out.LS').read_bytes(),b'TYPE part.txt\nready')
            self.assertFalse((root/'out.LS').exists())
            publish=os.rename if os.name=='nt' else os.link

            def competing_writer(source,target):
                Path(target).write_bytes(b'other')
                return publish(source,target)

            with patch('karel2py.storage.os.'+('rename' if os.name=='nt' else 'link'),side_effect=competing_writer):
                self.assertEqual(issue(ctx,'RUNCF start race')['S'],703)
            self.assertEqual((root/'Jobs'/'race.LS').read_bytes(),b'other')
            self.assertEqual(list((root/'Jobs').glob('*.tmp')),[])


class KclScheduledProcedureTests(unittest.TestCase):
    def test_wait_reuses_scheduler_and_retains_busy_channel(self):
        scheduler=rt.TaskScheduler()
        ctx=context(rt.MemoryFiles({
            'start.CF':'RUN CHILD\nWAIT CHILD DONE\nTYPE seed.txt\n','seed.txt':'ready',
        }),scheduler=scheduler,verify=False)
        child=worker(ctx,'CHILD','DELAY 8000000 n=7')
        main=worker(ctx,'MAIN',"KCL('RUNCF start log',s) n=KCL_STATUS")
        observer=worker(ctx,'OBSERVER',"DELAY 10 KCL('TYPE seed.txt',s)")
        scheduler.start('MAIN')
        scheduler.start('OBSERVER')
        scheduler.run(max_cycles=50)
        self.assertEqual(main.snapshot(),{'N':0,'S':0})
        self.assertEqual(child.snapshot()['N'],7)
        self.assertEqual(observer.snapshot()['S'],2)
        self.assertEqual(ctx.files.snapshot()['log.LS'],b'ready')
        self.assertEqual([row['phase'] for row in ctx.kcl.history],['completed','busy'])
        self.assertEqual(scheduler._task_waits,{})

    def test_stop_unwinds_private_wait_and_restores_output_sink(self):
        scheduler=rt.TaskScheduler()
        ctx=context(rt.MemoryFiles({'start.CF':'RUN CHILD\nWAIT CHILD DONE\n'}),scheduler=scheduler)
        child=worker(ctx,'CHILD','DELAY 8000000 n=7')
        output=[]
        main=worker(ctx,'MAIN',"KCL('RUNCF start log',s)",write=output.append)
        scheduler.start('MAIN')
        for _ in range(20):
            scheduler.step()
            if main.task_state=='waiting':break
        self.assertEqual(main.task_state,'waiting')
        with self.assertRaisesRegex(ValueError,'Cannot persist a pending KCL'):
            ctx.to_config()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'calling activation'):
            program('n=KCL_STATUS',name='PROBE',context=ctx).run()
        scheduler.stop('MAIN')
        self.assertEqual(ctx.kcl.last_status,4)
        self.assertEqual(scheduler._task_waits,{})
        self.assertNotIn('log.LS',ctx.files.files)
        self.assertEqual(main._state._write,output.append)
        scheduler.run(max_cycles=30)
        self.assertEqual(child.snapshot()['N'],7)
