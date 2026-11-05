"""Authored paused scalar edits and source type/variable inspection."""
import unittest
from unittest.mock import patch

from karel2py import runtime as rt, translate_project
from tests.test_extended_services import compile_program
from tests.test_kcl_inspection_commands import listing
from tests.test_kcl_task_commands import issue


def context():
    return rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True,program_commands=True))


class KclPausedLocalWriteTests(unittest.TestCase):
    def test_owned_scalar_edit_persists_and_all_for_roots_are_guarded(self):
        ctx=context()
        task,result=compile_program('n=0 perform',context=ctx,cooperative=True,routines='''
            ROUTINE perform
            VAR counter, value:INTEGER
                label:STRING[5]
            BEGIN
              value=4 label='old'
              FOR counter=1 TO 2 DO
                n=n+1 PAUSE
              ENDFOR
              PAUSE
              n=value
            END perform
        ''')
        ctx.tasks.bind('WORKER',task)
        self.assertEqual(task.local_for_roots,{'PERFORM':('COUNTER',)})
        self.assertIn('local_for_roots',result.python_source)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(issue(ctx,'SET DEFAULT WORKER')['S'],0)
        self.assertEqual(issue(ctx,'SET LOCAL VAR counter = 88')['S'],204)
        self.assertEqual(issue(ctx,'SET LOCAL VARIABLE value IN perform FROM T = 42')['S'],0)
        self.assertEqual(issue(ctx,'SET LOCAL VAR label = "MiXeD"')['S'],0)
        self.assertEqual(issue(ctx,'SET LOCAL VAR label = "too long"')['S'],205)
        self.assertEqual(listing(ctx,'SHOW LOCAL VAR LABEL')[1][0]['value'],'MiXeD')
        self.assertEqual(issue(ctx,'SET LOCAL VAR value = TRUE')['S'],205)
        with self.assertRaises(rt.KarelPause):
            task.resume()
        with self.assertRaises(rt.KarelPause):
            task.resume()
        self.assertEqual(issue(ctx,'SET LOCAL VAR counter = 88')['S'],204)
        self.assertEqual(task.resume()['N'],42)
        self.assertEqual(issue(ctx,'SET LOCAL VAR value = 1')['S'],201)

    def test_borrowed_formals_and_aliased_owner_cells_are_guarded(self):
        ctx=context()
        task,_=compile_program('outer',context=ctx,cooperative=True,routines='''
            ROUTINE outer
            VAR value, spare:INTEGER
            BEGIN value=6 spare=7 hold_value(value) n=value+spare END outer
            ROUTINE hold_value(formal:INTEGER)
            BEGIN PAUSE END hold_value
        ''')
        ctx.tasks.bind('WORKER',task)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(issue(ctx,'SET LOCAL VAR formal WORKER = 99')['S'],204)
        self.assertEqual(issue(ctx,'SET LOCAL VAR value IN outer WORKER = 99')['S'],204)
        self.assertEqual(issue(ctx,'SET LOCAL VAR spare IN outer WORKER = 12')['S'],0)
        self.assertEqual(task.resume()['N'],18)

    def test_connected_timer_running_frame_and_missing_metadata_guard(self):
        ctx=context()
        task,_=compile_program('perform',context=ctx,cooperative=True,clock_us=lambda:0,routines='''
            ROUTINE perform
            VAR elapsed, spare:INTEGER
            BEGIN
              spare=7
              KCL('SET LOCAL VAR spare = 99',s)
              CONNECT TIMER TO elapsed
              PAUSE
              DISCONNECT TIMER elapsed
              n=spare
            END perform
        ''')
        ctx.tasks.bind('WORKER',task)
        with self.assertRaises(rt.KarelPause):
            task.run()
        self.assertEqual(task.snapshot()['S'],204)
        self.assertEqual(issue(ctx,'SET LOCAL VAR elapsed WORKER = 42')['S'],204)
        with patch.object(type(task),'local_for_roots',{}):
            self.assertEqual(issue(ctx,'SET LOCAL VAR spare WORKER = 42')['S'],204)
        self.assertEqual(issue(ctx,'SET LOCAL VAR spare WORKER = 42')['S'],0)
        self.assertEqual(task.resume()['N'],42)


class KclTypeListingTests(unittest.TestCase):
    def test_lists_declared_types_and_record_fields_with_owner_and_sizes(self):
        ctx=context()
        task,_=compile_program('n=0',context=ctx,prefix='''
            TYPE row_t=STRUCTURE
                label:STRING[12]
                ordinal:INTEGER
            ENDSTRUCTURE
            grid_t=ARRAY[2] OF row_t
        ''')
        task.run()
        status,rows=listing(ctx,'SHOW TYPES T FIELDS')
        self.assertEqual(status,0)
        self.assertEqual(rows,[
            {'program':'T','owner':'T','name':'GRID_T','kind':'ARRAY','type':'ROW_T','dimensions':[2],
             'fields':[{'name':'LABEL','type':'STRING','string_capacity':12},{'name':'ORDINAL','type':'INTEGER'}]},
            {'program':'T','owner':'T','name':'ROW_T','kind':'STRUCTURE','type':'ROW_T',
             'fields':[{'name':'LABEL','type':'STRING','string_capacity':12},{'name':'ORDINAL','type':'INTEGER'}]},
        ])
        status,rows=listing(ctx,'SHOW TYPES T')
        self.assertEqual(status,0)
        self.assertTrue(all('fields' not in row for row in rows))
        self.assertEqual(listing(ctx,'SHOW TYPES MISSING'),(201,[]))

    def test_imported_type_reports_the_declared_source_owner(self):
        ctx=context()
        translate_project({
            'lib.kl':'PROGRAM LIB TYPE item_t=STRUCTURE value:INTEGER ENDSTRUCTURE BEGIN END LIB',
            'main.kl':('PROGRAM MAIN TYPE item_t FROM LIB=STRUCTURE value:INTEGER ENDSTRUCTURE '
                       'VAR item:item_t BEGIN END MAIN'),
        }).instantiate(context=ctx)
        self.assertEqual(listing(ctx,'SHOW TYPES MAIN FIELDS'),(0,[
            {'program':'MAIN','owner':'LIB','name':'ITEM_T','kind':'STRUCTURE','type':'ITEM_T',
             'fields':[{'name':'VALUE','type':'INTEGER'}]},
        ]))

    def test_type_filters_apply_to_root_storage_and_preserve_empty_matches(self):
        ctx=context()
        task,_=compile_program('n=7',context=ctx,decl='''
            n:INTEGER
            a:ARRAY[2] OF INTEGER
            narrow:JOINTPOS2
            wide:JOINTPOS6
            text:STRING[8]
        ''')
        task.run()
        self.assertEqual(issue(ctx,'SET DEFAULT T')['S'],0)
        self.assertEqual(listing(ctx,'SHOW INTEGER VALUES'),(0,[
            {'program':'T','name':'N','type':'INTEGER','value':7},
        ]))
        self.assertEqual(listing(ctx,'SHOW ARRAY'),(0,[
            {'program':'T','name':'A','type':'INTEGER','dimensions':[2]},
        ]))
        self.assertEqual([row['name'] for row in listing(ctx,'SHOW JOINTPOS')[1]],['NARROW','WIDE'])
        self.assertEqual([row['name'] for row in listing(ctx,'SHOW JOINTPOS2')[1]],['NARROW'])
        self.assertEqual(listing(ctx,'SHOW REAL'),(0,[]))
        self.assertEqual(listing(ctx,'SHOW REAL MISSING'),(201,[]))
