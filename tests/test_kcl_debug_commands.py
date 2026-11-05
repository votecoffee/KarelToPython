"""Authored source checkpoints, one-shot condition breaks and cooperative steps."""
import json
import unittest

from karel2py import runtime as rt, translate_project
from tests.test_directive_group_locks import program
from tests.test_kcl_inspection_commands import listing
from tests.test_kcl_task_commands import issue
from tests.test_task_control_broadcasts import worker


def context(*,scheduler=None,**options):
    return rt.ExecutionContext(tasks=scheduler,kcl=rt.KclCommands(
        debug_commands=True,task_commands=True,**options))


class KclProgramBreakpointTests(unittest.TestCase):
    def test_line_break_pauses_before_statement_and_edits_by_slot(self):
        ctx=context()
        task=worker(ctx,'WORKER','n=1\nn=2\nn=3')
        first,second,third=task.source_checkpoints
        self.assertEqual(issue(ctx,'SET BREAK PROGRAM WORKER 4 999')['S'],802)
        self.assertEqual(issue(ctx,f'SET BREAK PROG WORKER 4 {second}')['S'],0)
        self.assertEqual(listing(ctx,'SHOW BREAK WORKER'),(0,[
            {'kind':'PROGRAM','program':'WORKER','number':4,'line':second,'action':'PAUSE','enabled':True},
        ]))
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['N'],1)
        self.assertEqual(issue(ctx,'DISABLE BREAK PROGRAM WORKER 4')['S'],0)
        self.assertEqual(task.resume()['N'],3)
        self.assertEqual(task.run()['N'],3)
        self.assertEqual(issue(ctx,'ENABLE BREAK PROG WORKER 4')['S'],0)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['N'],1)
        self.assertEqual(issue(ctx,'CLEAR BREAK PROGRAM WORKER ALL')['S'],0)
        self.assertEqual(task.resume()['N'],3)
        self.assertEqual(listing(ctx,'SHOW BREAK WORKER'),(0,[]))
        self.assertLess(first,second)
        self.assertLess(second,third)

    def test_display_and_trace_actions_use_source_order_without_pausing(self):
        ctx=context()
        output=[]
        task=worker(ctx,'WORKER','n=1\nn=2\nn=3',write=output.append)
        first,second,third=task.source_checkpoints
        for number,line,action in ((1,first,'TRACE ON'),(2,second,'DISPLAY'),(3,third,'TRACE OFF')):
            self.assertEqual(issue(ctx,f'SET BREAK PROGRAM WORKER {number} {line} {action}')['S'],0)
        self.assertEqual(task.run()['N'],3)
        self.assertEqual([row['line'] for row in task.task_trace],[first,second])
        self.assertEqual([json.loads(row) for row in output],[
            {'program':'WORKER','number':2,'line':second,'action':'DISPLAY','enabled':True},
        ])
        self.assertEqual(task.task_settings['TSK_TRACE'],0)

    def test_definitions_restore_without_replaying_and_requires_opt_in(self):
        ctx=context()
        task=worker(ctx,'WORKER','n=1\nn=2')
        line=task.source_checkpoints[0]
        self.assertEqual(issue(ctx,f'SET BREAK PROGRAM WORKER 2 {line}')['S'],0)
        restored=rt.ExecutionContext.from_config(ctx.to_config())
        self.assertEqual(restored.tasks.tasks,{})
        self.assertEqual(listing(restored,'SHOW BREAK WORKER')[1][0]['line'],line)
        fresh=worker(restored,'WORKER','n=1\nn=2')
        with self.assertRaises(rt.KarelPause):
            fresh.run()
        self.assertEqual(fresh.resume()['N'],2)
        disabled=rt.ExecutionContext(kcl=rt.KclCommands({'SHOW BREAK':{'status':17}}))
        self.assertEqual(issue(disabled,'SHOW BREAK')['S'],17)
        self.assertEqual(issue(disabled,'show break')['S'],1)
        row={'program':'WORKER','number':2,'line':line,'action':'PAUSE','enabled':True}
        for config in ({'program_breakpoints':[row]},
                       {'debug_commands':True,'program_breakpoints':[row,row]},
                       {'debug_commands':True,'program_breakpoints':[{**row,'line':0}]}):
            with self.subTest(config=config),self.assertRaises(ValueError):
                rt.KclCommands.from_config(config)

    def test_linked_routine_breaks_the_root_task_before_mutation(self):
        ctx=context()
        instance=translate_project({
            'main.kl':('PROGRAM MAIN VAR n:INTEGER ROUTINE set_value(value:INTEGER) FROM LIB '
                       'BEGIN n=1 set_value(n) END MAIN'),
            'lib.kl':'''
PROGRAM LIB
ROUTINE set_value(value:INTEGER)
BEGIN
  value=7
END set_value
BEGIN
END LIB
''',
        }).instantiate(context=ctx)
        line,=instance.programs['LIB'].source_checkpoints
        self.assertEqual(instance.project.translations['LIB'].report['kcl_policy']['source_checkpoints'],[line])
        self.assertEqual(issue(ctx,f'SET BREAK PROGRAM LIB 1 {line}')['S'],0)
        snapshot=instance.run('MAIN',max_cycles=40)
        self.assertEqual(snapshot['MAIN'],{'state':'paused','values':{'N':1}})
        status,history=listing(ctx,'SHOW HISTORY MAIN')
        self.assertEqual((status,history[-1]['program'],history[-1]['line']),(0,'LIB',line))
        instance.scheduler.continue_task('MAIN')
        self.assertEqual(instance.scheduler.run(max_cycles=40)['MAIN']['values']['N'],7)


class KclConditionAndStepTests(unittest.TestCase):
    def test_condition_break_is_one_shot_and_holds_the_action_until_continue(self):
        ctx=context()
        task=worker(ctx,'WORKER','''
            n=0 s=0
            CONDITION[1]: WHEN n=1 DO s=s+1 ENDCONDITION
            ENABLE CONDITION[1]
            PAUSE
            n=1 n=2
            ENABLE CONDITION[1]
            n=1 n=3
        ''')
        self.assertEqual(issue(ctx,'SET BREAK COND WORKER 1')['S'],801)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(issue(ctx,'SET BREAK CONDITION WORKER 1')['S'],0)
        self.assertEqual(listing(ctx,'SHOW BREAK WORKER'),(0,[
            {'kind':'CONDITION','program':'WORKER','number':1,'enabled':True},
        ]))
        self.assertEqual(issue(ctx,'CLEAR BREAK COND WORKER ALL')['S'],0)
        self.assertEqual(listing(ctx,'SHOW BREAK WORKER'),(0,[]))
        self.assertEqual(issue(ctx,'SET BREAK COND WORKER 1')['S'],0)
        with self.assertRaises(rt.KarelPause):
            task.resume()
        self.assertEqual(task.snapshot(),{'N':1,'S':0})
        self.assertEqual(listing(ctx,'SHOW BREAK WORKER'),(0,[]))
        self.assertEqual(task.resume(),{'N':3,'S':2})

    def test_scheduled_step_pauses_at_source_checkpoints_and_step_off_is_local(self):
        scheduler=rt.TaskScheduler()
        ctx=context(scheduler=scheduler)
        task=worker(ctx,'WORKER','n=1\nn=2\nn=3')
        other=worker(ctx,'OTHER','n=9')
        self.assertEqual(issue(ctx,'STEP ON WORKER')['S'],0)
        scheduler.start('WORKER')
        scheduler.start('OTHER')
        state=scheduler.run(max_cycles=25)
        self.assertEqual(state['WORKER']['state'],'paused')
        self.assertEqual(state['OTHER']['values']['N'],9)
        self.assertEqual(task.task_settings['TSK_STEP'],1)
        scheduler.continue_task('WORKER')
        self.assertEqual(scheduler.run(max_cycles=25)['WORKER'],{
            'state':'paused','values':{'N':1,'S':{'uninitialized':True}},
        })
        self.assertEqual(issue(ctx,'STEP OFF')['S'],0)
        scheduler.continue_task('WORKER')
        self.assertEqual(scheduler.run(max_cycles=25)['WORKER']['values']['N'],3)
        self.assertEqual(task.task_settings['TSK_STEP'],0)
        self.assertFalse(other.task_settings.get('TSK_STEP'))

    def test_abort_from_condition_break_discards_the_pending_action(self):
        scheduler=rt.TaskScheduler()
        ctx=context(scheduler=scheduler)
        task=worker(ctx,'WORKER','''
            n=0 s=0
            CONDITION[1]: WHEN n=1 DO s=9 ENDCONDITION
            ENABLE CONDITION[1]
            PAUSE
            n=1 n=2
        ''')
        scheduler.start('WORKER')
        scheduler.run(max_cycles=25)
        self.assertEqual(issue(ctx,'SET BREAK COND WORKER 1')['S'],0)
        scheduler.continue_task('WORKER')
        scheduler.run(max_cycles=25)
        self.assertEqual(task.task_state,'paused')
        self.assertEqual(issue(ctx,'ABORT WORKER')['S'],0)
        with self.assertRaises(rt.KarelAbort):
            scheduler.run(max_cycles=25)
        self.assertEqual(task.snapshot(),{'N':1,'S':0})
