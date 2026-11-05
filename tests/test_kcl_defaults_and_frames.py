"""Authored KCL session defaults and live routine-frame observations."""
import json
import unittest

from karel2py import runtime as rt, translate_project
from tests.test_extended_services import compile_program
from tests.test_kcl_inspection_commands import listing
from tests.test_kcl_task_commands import issue
from tests.test_task_control_broadcasts import worker


class KclDefaultProgramTests(unittest.TestCase):
    def test_default_is_opt_in_validated_and_preserved_for_variable_resolution(self):
        ctx = rt.ExecutionContext(kcl=rt.KclCommands(program_commands=True, variable_commands=True))
        ctx.variables.define('CACHE', 'COUNT', ('INTEGER',), 7)
        ctx.variables.define('OTHER', 'COUNT', ('INTEGER',), 17)
        self.assertEqual(listing(ctx,'SHOW DEFAULT'),(0,[{'program':'OBSERVER'}]))
        self.assertEqual(issue(ctx,'SET DEF cache')['S'],0)
        self.assertEqual(issue(ctx,'SET DEFAULT missing')['S'],501)
        self.assertEqual(issue(ctx,'SET DEFAULT ALL')['S'],502)
        self.assertEqual(listing(ctx,'SHOW DEFAULT'),(0,[{'program':'CACHE'}]))
        self.assertEqual(issue(ctx,'SET VAR count = 42')['S'],0)
        self.assertEqual(listing(ctx,'SHOW VAR count')[1][0]['value'],42)
        self.assertEqual(listing(ctx,'SHOW VAR [OTHER]count')[1][0]['value'],17)
        self.assertEqual(listing(ctx,'SHOW PROGRAM'),(0,[{'name':'CACHE','type':'VR'}]))
        restored = rt.ExecutionContext.from_config(ctx.to_config())
        self.assertEqual(restored.kcl.default_program,'CACHE')
        self.assertEqual(listing(restored,'SHOW VARS VALUES')[1][0]['value'],42)

    def test_named_task_defaults_apply_to_drive_wait_and_settings(self):
        scheduler = rt.TaskScheduler()
        ctx = rt.ExecutionContext(tasks=scheduler,kcl=rt.KclCommands(task_commands=True,program_commands=True))
        task = worker(ctx,'CHILD','PAUSE n=7')
        self.assertEqual(issue(ctx,'RUN')['S'],1)
        self.assertEqual(issue(ctx,'SET DEFAULT CHILD')['S'],0)
        self.assertEqual(issue(ctx,'SET TASK PRIORITY=9')['S'],0)
        self.assertEqual(task.task_settings['TSK_PRIORITY'],9)
        self.assertEqual(issue(ctx,'RUN',nowait=True)['S'],0)
        scheduler.run(max_cycles=25)
        self.assertEqual(issue(ctx,'WAIT PAUSE')['S'],0)
        self.assertEqual(issue(ctx,'CONT')['S'],0)
        scheduler.run(max_cycles=25)
        self.assertEqual(issue(ctx,'WAIT DONE')['S'],0)
        self.assertEqual(task.snapshot()['N'],7)
        self.assertEqual(issue(ctx,'WAIT MISSING DONE')['S'],3)
        restored = rt.ExecutionContext.from_config(ctx.to_config())
        self.assertEqual(issue(restored,'RUN')['S'],3)

    def test_default_configuration_requires_its_opt_in_and_canonical_fields(self):
        for config in ({'default_program':'TASK'}, {'program_commands':True,'default_program':'all'},
                       {'program_commands':True,'default_program':'ALL'}, {'default_group':1},
                       {'environment_commands':True,'default_group':True},
                       {'environment_commands':True,'default_group':33}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                rt.KclCommands.from_config(config)


class KclRoutineInspectionTests(unittest.TestCase):
    def context(self):
        return rt.ExecutionContext(kcl=rt.KclCommands(
            program_commands=True,task_commands=True,variable_commands=True))

    def test_inspects_innermost_recursive_frame_and_explicit_ancestor(self):
        ctx = self.context()
        task,_ = compile_program('n=7 outer(n)',cooperative=True,context=ctx,routines='''
            ROUTINE outer(value:INTEGER)
            VAR outer_value:INTEGER
            BEGIN outer_value=40 descend(2) s=outer_value END outer
            ROUTINE descend(depth:INTEGER)
            VAR local_value:INTEGER
            BEGIN
              local_value=depth+10
              IF depth>0 THEN descend(depth-1) ELSE PAUSE ENDIF
            END descend
        ''')
        ctx.tasks.bind('WORK',task)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(issue(ctx,'SET DEF WORK')['S'],0)
        status,rows = listing(ctx,'SHOW LOCAL VARIABLE depth HEX IN DESCEND')
        self.assertEqual((status,rows),(0,[{'program':'T','task':'WORK','routine':'DESCEND',
                                          'name':'DEPTH','type':'INTEGER','value':0,'formatted':'0x0'}]))
        status,rows = listing(ctx,'SHOW LOCAL VARS VALUES IN OUTER FROM T WORK')
        self.assertEqual((status,[(row['name'],row['value']) for row in rows]),
                         (0,[('OUTER_VALUE',40),('VALUE',7)]))
        self.assertEqual(listing(ctx,'SHOW LOCAL VAR N'),(201,[]))
        self.assertEqual(listing(ctx,'SHOW LOCAL VARS FROM MISSING WORK'),(201,[]))
        status,rows = listing(ctx,'SHOW HISTORY')
        self.assertEqual((status,[row['routine'] for row in rows]),
                         (0,['','OUTER','DESCEND','DESCEND','DESCEND']))
        self.assertEqual(rows[-1]['depth'],4)
        self.assertGreater(rows[-1]['line'],0)
        status,rows = listing(ctx,'SHOW PROG')
        self.assertEqual((status,rows[0]['status'],rows[0]['routine']), (0,'PG_PAUSED','DESCEND'))
        self.assertEqual(issue(ctx,'SET LOCAL VAR DEPTH = 99')['S'],204)
        self.assertEqual(task.resume()['S'],40)
        self.assertEqual(listing(ctx,'SHOW LOCAL VARS'),(201,[]))

    def test_read_only_local_array_observation_works_from_running_caller(self):
        output = []
        task,_ = compile_program('inspect_local',context=self.context(),write=output.append,routines='''
            ROUTINE inspect_local
            VAR data:ARRAY[2] OF INTEGER
            BEGIN
              data[2]=9
              KCL('SHOW LOCAL VAR data[2]',s)
            END inspect_local
        ''')
        self.assertEqual(task.run()['S'],0)
        self.assertEqual(json.loads(''.join(output)),{
            'program':'T','task':'T','routine':'INSPECT_LOCAL','name':'DATA[2]','type':'INTEGER','value':9
        })

    def test_linked_routine_frames_keep_module_and_task_identities_distinct(self):
        ctx = self.context()
        project = translate_project({
            'main.kl': '''
                PROGRAM MAIN
                VAR result:INTEGER
                ROUTINE stay(value:INTEGER) FROM LIB
                ROUTINE outer
                VAR marker:INTEGER
                BEGIN marker=77 stay(marker) result=marker END outer
                BEGIN outer END MAIN
            ''',
            'lib.kl': '''
                PROGRAM LIB
                ROUTINE stay(value:INTEGER)
                VAR observed:INTEGER
                BEGIN observed=value+1 PAUSE value=observed END stay
                BEGIN END LIB
            ''',
        }).instantiate(context=ctx)
        self.assertEqual(project.run('MAIN',max_cycles=60)['MAIN']['state'],'paused')
        status,rows=listing(ctx,'SHOW LOCAL VAR observed FROM LIB MAIN')
        self.assertEqual((status,rows[0]['program'],rows[0]['value']), (0,'LIB',78))
        status,rows=listing(ctx,'SHOW LOCAL VAR marker IN OUTER FROM MAIN MAIN')
        self.assertEqual((status,rows[0]['program'],rows[0]['value']), (0,'MAIN',77))
        status,rows=listing(ctx,'SHOW HISTORY MAIN')
        self.assertEqual((status,rows[-1]['program'],rows[-1]['routine']),(0,'LIB','STAY'))
        self.assertEqual(issue(ctx,'SET LOCAL VAR observed FROM LIB MAIN = 81')['S'],0)
        project.scheduler.continue_task('MAIN')
        self.assertEqual(project.scheduler.run(max_cycles=60)['MAIN']['values']['RESULT'],81)


class KclDefaultGroupTests(unittest.TestCase):
    def test_group_selection_is_local_to_kcl_and_replays(self):
        ctx = rt.ExecutionContext.from_config({
            'kcl':{'environment_commands':True}, 'robot':{
                'active_group':2, 'groups':{
                    '1':{'dh':[{'a':100}], 'current':{'joints':{'type':['JOINTPOS',1],'value':[0.0]}}},
                    '2':{'dh':[{'a':200}], 'current':{'joints':{'type':['JOINTPOS',1],'value':[0.0]}}},
                },
            },
        })
        self.assertEqual(listing(ctx,'SHOW GROUP'),(0,[{'group':2}]))
        self.assertEqual(issue(ctx,'SET GROUP 1')['S'],0)
        self.assertEqual(issue(ctx,'SET GROUP 3')['S'],602)
        self.assertEqual(issue(ctx,'SET GROUP 0')['S'],602)
        self.assertEqual(listing(ctx,'SHOW GROUP'),(0,[{'group':1}]))
        self.assertEqual(listing(ctx,'SHOW CURPOS')[1][0]['pose']['X'],100.0)
        probe,_ = compile_program('point=CURPOS',decl='point:XYZWPREXT',context=ctx)
        self.assertEqual(probe.run()['POINT']['X'],200.0)
        restored = rt.ExecutionContext.from_config(ctx.to_config())
        self.assertEqual(listing(restored,'SHOW GROUP'),(0,[{'group':1}]))
