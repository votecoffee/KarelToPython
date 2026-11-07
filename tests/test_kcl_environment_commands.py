"""Authored KCL coverage for offline ports, calendar, task policy and conditions."""
from datetime import datetime
import json
import unittest

from karel2py import runtime as rt
from tests.test_directive_group_locks import program
from tests.test_extended_services import compile_program
from tests.test_kcl_task_commands import issue
from tests.test_task_control_broadcasts import advance_until, worker


def clock_command(text):
    # issue() embeds a KAREL literal. Double the clock command's inner quotes.
    return "SET CLOCK ''" + text + "''"


class KclEnvironmentTests(unittest.TestCase):
    def test_port_opt_in_and_exact_reply_precedence(self):
        bank = rt.PortBank({'DOUT': 1}, {('DOUT', 1): False})
        ctx = rt.ExecutionContext(ports=bank, kcl=rt.KclCommands())
        self.assertEqual(issue(ctx, 'SET PORT DOUT[1] = ON')['S'], 1)
        ctx.kcl = rt.KclCommands({'SET PORT DOUT[1] = ON': {'status': 17}}, environment_commands=True)
        self.assertEqual(issue(ctx, 'SET PORT DOUT[1] = ON')['S'], 17)
        self.assertFalse(bank.read('DOUT', 1))
        self.assertEqual(issue(ctx, 'set port dout [1] = on')['S'], 0)
        self.assertTrue(bank.read('DOUT', 1))
        with self.assertRaisesRegex(ValueError, 'environment_commands requires'):
            rt.KclCommands.from_config({'environment_commands': 1})

    def test_ports_share_checked_values_with_source_calls_and_persist(self):
        bank = rt.PortBank({'DIN': 2, 'DOUT': 1, 'AOUT': 1, 'GOUT': 1},
                           {('DIN', 1): False}, type_codes={10: 'DIN', 20: 'AOUT'})
        ctx = rt.ExecutionContext(ports=bank, kcl=rt.KclCommands(environment_commands=True))
        self.assertEqual(issue(ctx, 'SET PORT DIN[1]=ON', nowait=True), {'S': 0, 'N': 604})
        self.assertEqual(issue(ctx, 'SIM DIN[1]')['S'], 0)
        self.assertEqual(issue(ctx, 'SET PORT DIN[1]=ON')['S'], 0)
        self.assertEqual(issue(ctx, 'SET PORT AOUT[1]=-1.25e1')['S'], 0)
        self.assertEqual(issue(ctx, 'SET PORT GOUT[1]=255')['S'], 0)
        task, _ = compile_program('GET_PORT_SIM(10,1,sim,s) GET_PORT_VAL(20,1,analog,s) '
                                  'GET_PORT_VAL(10,1,digital,s)',
                                  decl='sim,digital:BOOLEAN analog:REAL s:INTEGER', context=ctx)
        self.assertEqual(task.run(), {'SIM': True, 'DIGITAL': True, 'ANALOG': -12.5, 'S': 0})
        self.assertEqual(issue(ctx, 'UNSIMULATE DIN[1]')['S'], 0)
        self.assertEqual(issue(ctx, 'SET PORT DIN[1]=OFF')['S'], 604)
        self.assertTrue(bank.read('DIN', 1))
        self.assertEqual(bank.read('GOUT', 1), 255)
        self.assertEqual(rt.ExecutionContext.from_config(ctx.to_config()).to_config(), ctx.to_config())

    def test_invalid_ports_and_literals_preserve_the_bank(self):
        bank = rt.PortBank({'DIN': 2, 'AOUT': 1, 'GOUT': 1}, {('DIN', 1): False},
                           comments={('DIN', 1): 'fixture'}, simulated=[('DIN', 1)])
        ctx = rt.ExecutionContext(ports=bank, kcl=rt.KclCommands(environment_commands=True))
        before = bank.snapshot(), bank.simulated.copy(), bank.comments.copy()
        for command, status in (
            ('SIM DIN[2]', 601), ('SIM DIN[3]=ON', 602), ('SIM DIN[2]=2', 603),
            ('SET PORT GOUT[1]=-1', 603), ('SET PORT AOUT[1]=1E999', 603),
            ('SET PORT GOUT[1]=1_000', 603), ('UNSIM DIN[1]=OFF', 1),
            ('SIM WDI[1]', 1),
        ):
            with self.subTest(command=command):
                self.assertEqual(issue(ctx, command)['S'], status)
                self.assertEqual((bank.snapshot(), bank.simulated, bank.comments), before)
        self.assertEqual(issue(ctx, 'SIM DIN[2]=TRUE')['S'], 0)
        values = bank.snapshot()
        self.assertEqual(issue(ctx, 'UNSIM ALL')['S'], 0)
        self.assertEqual((bank.snapshot(), bank.simulated, bank.comments), (values, set(), before[2]))

    def test_clock_uses_the_calendar_anchor_and_shared_time_format(self):
        elapsed = [100]
        clock = rt.CalendarClock(datetime(2024, 1, 1), clock_us=lambda: elapsed[0])
        ctx = rt.ExecutionContext(calendar=clock, kcl=rt.KclCommands(environment_commands=True))
        self.assertEqual(issue(ctx, clock_command('29-feb-24 21:45'), nowait=True), {'S': 0, 'N': 0})
        elapsed[0] += 3_000_000
        output = []
        self.assertEqual(issue(ctx, 'show clock', write=output.append)['S'], 0)
        self.assertEqual(output, ['29-FEB-2024 21:45:02\n'])
        task, _ = compile_program('GET_TIME(n)', context=ctx)
        self.assertEqual(task.run()['N'], clock.read())
        for text, year in (('01-JAN-79 00:00', 2079), ('01-JAN-80 00:00', 1980)):
            self.assertEqual(issue(ctx, clock_command(text))['S'], 0)
            self.assertEqual(clock.now().year, year)

    def test_invalid_clock_text_does_not_sample_or_replace_anchor(self):
        samples = []

        def elapsed():
            samples.append(0)
            return 0

        clock = rt.CalendarClock(datetime(2024, 2, 29), clock_us=elapsed)
        ctx = rt.ExecutionContext(calendar=clock, kcl=rt.KclCommands(environment_commands=True))
        for text in ('29-FEB-23 00:00', '01-FOO-24 10:00', '01-MAR-24 24:00'):
            self.assertEqual(issue(ctx, clock_command(text))['S'], 602)
        self.assertEqual(samples, [0])
        self.assertEqual(clock.now(), datetime(2024, 2, 29))
        missing = rt.ExecutionContext(kcl=rt.KclCommands(environment_commands=True))
        self.assertEqual(issue(missing, 'SHOW CLOCK')['S'], 4)
        self.assertEqual(issue(missing, 'SET PORT DOUT[1]=1')['S'], 4)


class KclTaskAdminTests(unittest.TestCase):
    def context(self, **services):
        return rt.ExecutionContext(kcl=rt.KclCommands(task_commands=True), **services)

    def test_task_policy_and_trace_reuse_the_same_portable_task_store(self):
        ctx = self.context()
        task = worker(ctx, 'WORKER', 'n=1 n=2 n=3 n=4')
        self.assertEqual(issue(ctx, 'SET TASK [worker] PRIORITY=9')['S'], 0)
        self.assertEqual(issue(ctx, 'SET TASK [WORKER] TRACELEN=2')['S'], 0)
        self.assertEqual(issue(ctx, 'SET TRACE ON [WORKER]')['S'], 0)
        self.assertEqual(issue(ctx, 'SET TASK [WORKER] PRIORITY=0', nowait=True), {'S': 0, 'N': 4})
        self.assertEqual(issue(ctx, 'SET TASK [ABSENT] PRIORITY=9')['S'], 3)
        self.assertEqual(task.task_settings['TSK_PRIORITY'], 9)
        self.assertEqual(task.task_state, 'ready')
        self.assertEqual(task.run()['N'], 4)
        self.assertEqual(issue(ctx, 'SET TRACE OFF [WORKER]')['S'], 0)
        output = []
        self.assertEqual(issue(ctx, 'SHOW TRACE WORKER', write=output.append)['S'], 0)
        self.assertEqual(len(output), 2)
        self.assertEqual(tuple(json.loads(row) for row in output), task.task_trace)

    def test_task_settings_require_unique_current_binding_without_selector(self):
        ctx = self.context()
        body = "KCL('SET TASK PRIORITY=5',s) n=KCL_STATUS"
        self.assertEqual(program(body, context=ctx).run()['S'], 3)
        task = worker(ctx, 'WORKER', body)
        self.assertEqual(task.run(), {'N': 0, 'S': 0})
        self.assertEqual(task.task_settings['TSK_PRIORITY'], 5)
        ctx.tasks.bind('ALIAS', task)
        self.assertEqual(task.run()['S'], 3)

    def test_named_live_conditions_share_state_and_expire_with_the_task(self):
        ctx = self.context()
        task = worker(ctx, 'WORKER', '''
            n=0 s=0
            CONDITION[2]: WHEN n=1 DO s=99 ENDCONDITION
            CONDITION[1]: WHEN n=1 DO s=41 ENDCONDITION
            ENABLE CONDITION[2]
            PAUSE
            n=1 n=2
        ''')
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(issue(ctx, 'DISABLE COND WORKER 2')['S'], 0)
        self.assertEqual(issue(ctx, 'ENABLE CONDITION WORKER 1')['S'], 0)
        output = []
        self.assertEqual(issue(ctx, 'SHOW CONDITION WORKER', write=output.append)['S'], 0)
        self.assertEqual([json.loads(row) for row in output], [
            {'number': 1, 'enabled': True, 'priority': 50, 'scan_ms': 0},
            {'number': 2, 'enabled': False, 'priority': 50, 'scan_ms': 0},
        ])
        self.assertEqual(issue(ctx, 'ENABLE CONDITION WORKER 1001')['S'], 4)
        self.assertEqual(issue(ctx, 'DISABLE COND WORKER 9')['S'], 3)
        self.assertEqual(task.resume()['S'], 41)
        self.assertEqual(issue(ctx, 'SHOW CONDITION WORKER 1')['S'], 3)

    def test_enable_condition_wakes_an_already_parked_source_delay(self):
        scheduler=rt.TaskScheduler()
        ctx=self.context(tasks=scheduler)
        task=worker(ctx,'WORKER','n=0 CONDITION[1]: WITH $SCAN_TIME=10 WHEN TRUE DO n=7 '
                                 'ENDCONDITION DELAY 100 n=n+1')
        scheduler.start('WORKER')
        advance_until(scheduler,lambda:task.task_state=='waiting')
        self.assertEqual(issue(ctx,'ENABLE CONDITION WORKER 1')['S'],0)
        advance_until(scheduler,lambda:task.snapshot()['N']==7)
        self.assertLess(scheduler.now_us,100000)
        self.assertEqual(scheduler.run()['WORKER']['values']['N'],8)

    def test_disable_condition_removes_its_earlier_parked_wake(self):
        scheduler=rt.TaskScheduler()
        ctx=self.context(tasks=scheduler)
        task=worker(ctx,'WORKER','n=0 CONNECT TIMER TO s CONDITION[1]: WITH $SCAN_TIME=10 '
                                 'WHEN s>=10 DO n=7 ENDCONDITION ENABLE CONDITION[1] DELAY 100 n=n+1')
        scheduler.start('WORKER')
        advance_until(scheduler,lambda:task.task_state=='waiting')
        self.assertEqual(issue(ctx,'DISABLE CONDITION WORKER 1')['S'],0)
        self.assertFalse(scheduler.step())
        self.assertGreaterEqual(scheduler.now_us,100000)
        self.assertEqual(scheduler.run()['WORKER']['values']['N'],1)

    def test_default_condition_selector_targets_the_calling_root(self):
        ctx = self.context()
        task = program('''
            n=0 s=0
            CONDITION[1]: WHEN n=1 DO s=42 ENDCONDITION
            KCL('ENABLE COND 1',s)
            n=1 n=2
        ''', context=ctx)
        self.assertEqual(task.run(), {'N': 2, 'S': 42})

    def test_frame_local_handlers_are_excluded_from_kcl(self):
        ctx = self.context(local_handlers=True)
        task, _ = compile_program('child', cooperative=True, context=ctx, routines='''
            ROUTINE child
            BEGIN
              n=0 s=0
              CONDITION[1]: WHEN n=1 DO s=41 ENDCONDITION
              PAUSE
              n=1 n=2
            END child
        ''')
        ctx.tasks.bind('WORKER', task)
        with self.assertRaises(rt.KarelPause):
            task.run()
        output = []
        self.assertEqual(issue(ctx, 'SHOW COND WORKER', write=output.append)['S'], 0)
        self.assertEqual(output, [])
        self.assertEqual(issue(ctx, 'ENABLE COND WORKER 1')['S'], 3)
        self.assertEqual(task.resume()['S'], 0)
