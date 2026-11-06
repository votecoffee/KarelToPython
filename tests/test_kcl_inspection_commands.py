"""Authored KCL coverage for offline variable, device, language and pose views."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_directive_group_locks import program
from tests.test_extended_services import compile_program
from tests.test_kcl_task_commands import issue


def listing(ctx, command, **options):
    output = []
    status = issue(ctx, command, write=output.append, **options)['S']
    return status, [json.loads(row) for row in ''.join(output).splitlines()]


class KclVariableListingTests(unittest.TestCase):
    def setUp(self):
        self.ctx = rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True))

    def test_named_and_unnamed_roots_and_integer_radices(self):
        self.ctx.variables.define('FIXTURE', 'COUNT', ('INTEGER',), -31)
        self.ctx.variables.define('', 'FLAG', ('BOOLEAN',), True)
        for radix, formatted in (('HEX', '-0x1f'), ('HEXADECIMAL', '-0x1f'), ('BINARY', '-0b11111')):
            with self.subTest(radix=radix):
                self.assertEqual(listing(self.ctx, f'SHOW VARIABLE [fixture] count {radix}'), (0, [
                    {'program': 'FIXTURE', 'name': 'COUNT', 'type': 'INTEGER', 'value': -31, 'formatted': formatted}
                ]))
        self.assertEqual(listing(self.ctx, 'SHOW VAR FLAG'), (0, [
            {'program': 'OBSERVER', 'name': 'FLAG', 'type': 'BOOLEAN', 'value': True}
        ]))
        self.assertEqual(listing(self.ctx, 'SHOW VAR FLAG HEX'), (202, []))
        self.assertEqual(listing(self.ctx, 'SHOW VAR [missing]FLAG'), (201, []))
        self.assertEqual(listing(self.ctx, 'SHOW VAR $LANGUAGE'), (1, []))

    def test_complete_array_and_path_selectors_use_typed_snapshots(self):
        output = []
        task, _ = compile_program('''
            nums[1,2]=31
            APPEND_NODE(route,s)
            route[1].value=7
            KCL('SHOW VAR nums',s)
            KCL('SHOW VAR nums[1, 2]',s)
            KCL('SHOW VAR route[1].value',s)
        ''', prefix='''
            TYPE node_t=STRUCTURE
              value:INTEGER
            ENDSTRUCTURE
            route_t=PATH NODEDATA=node_t
        ''', decl='nums:ARRAY[2,2] OF INTEGER route:route_t s:INTEGER', context=self.ctx,
            write=output.append)
        self.assertEqual(task.run()['S'], 0)
        rows = [json.loads(row) for row in ''.join(output).splitlines()]
        self.assertEqual(rows[0]['dimensions'], [2, 2])
        self.assertEqual(rows[0]['value'][0], [{'uninitialized': True}, 31])
        self.assertEqual([(row['name'],row['value']) for row in rows[1:]], [
            ('NUMS[1,2]',31), ('ROUTE[1].VALUE',7)
        ])

    def test_metadata_only_and_values_do_not_read_file_contents(self):
        output = []
        task, _ = compile_program("label='ready' KCL('SHOW VARS',s) KCL('SHOW VARS VALUES',s)",
                                  decl='label:STRING[12] file_ref:FILE s:INTEGER',
                                  context=self.ctx, write=output.append)
        self.assertEqual(task.run()['S'], 0)
        rows = [json.loads(row) for row in ''.join(output).splitlines()]
        self.assertEqual([row['name'] for row in rows], ['FILE_REF','LABEL','S'] * 2)
        self.assertTrue(all('value' not in row for row in rows[:3]))
        self.assertIs(rows[3]['value_available'], False)
        self.assertEqual((rows[4]['string_capacity'], rows[4]['value']), (12, 'ready'))

    def test_cohort_budget_and_callback_preserve_snapshot_boundaries(self):
        for name in ('A','B'):
            self.ctx.variables.define('LARGE', name, ('ARRAY',18000,('INTEGER',)))
        self.assertEqual(listing(self.ctx, 'SHOW VARS LARGE VALUES'), (205, []))
        self.ctx.variables.define('FIXTURE','A',('INTEGER',),1)
        later = self.ctx.variables.define('FIXTURE','B',('INTEGER',),2)
        output = []

        def write(text):
            later.set(3)
            output.append(text)

        self.assertEqual(issue(self.ctx, 'SHOW VARS FIXTURE VALUES', write=write)['S'], 0)
        self.assertEqual([json.loads(row)['value'] for row in output], [1,2])
        self.assertEqual(later.raw(), 3)

    def test_scan_limits_include_filtered_out_bindings(self):
        self.ctx.variables.define('FIXTURE','TARGET',('INTEGER',),7)
        for index in range(12):
            self.ctx.variables.define('OTHER',f'VALUE{index}',('INTEGER',),index)
        with patch('karel2py.inspection.CATALOG_SCAN_LIMIT',6):
            self.assertEqual(listing(self.ctx,'SHOW VARS FIXTURE'),(205,[]))
            self.assertEqual(listing(self.ctx,'SHOW SYSTEM'),(205,[]))
            self.assertEqual(listing(self.ctx,'SHOW VAR [FIXTURE]TARGET')[0],0)

    def test_scan_exhausts_step_budget_before_output(self):
        for index in range(12):
            self.ctx.variables.define('OTHER',f'VALUE{index}',('INTEGER',),index)
        output=[]
        task,_=compile_program("KCL('SHOW VARS',s)",context=self.ctx,write=output.append)
        self.assertEqual(task.run(max_steps=5)['S'],4)
        self.assertEqual(output,[])


class KclDeviceListingTests(unittest.TestCase):
    def test_mounted_and_offline_volume_metadata_is_observable(self):
        files = rt.DeviceFiles({'FR:': {'capacity': 40, 'garbage': 3, 'label': 'Fixture'},
                                'CMOS:': {'capacity': 20, 'read_only': True}}, {'FR:note': b'rd'})
        ctx = rt.ExecutionContext(files=files, kcl=rt.KclCommands(device_commands=True))
        self.assertEqual(issue(ctx, 'DISMOUNT FR:')['S'], 0)
        before = files.to_config()
        self.assertEqual(listing(ctx, 'show device fr:'), (0, [
            {'name':'FR:', 'mounted':False, 'read_only':False, 'total':40,
             'label':'Fixture', 'garbage':3, 'free':35}
        ]))
        self.assertEqual(listing(ctx, 'SHOW DEVICE CMOS'), (0, [
            {'name':'CMOS:', 'mounted':True, 'read_only':True, 'total':20, 'label':''}
        ]))
        self.assertEqual(listing(ctx, 'SHOW DEVICE RD:'), (302, []))
        self.assertEqual(listing(ctx, 'SHOW_DEVICE FR:'), (1, []))
        self.assertEqual(files.to_config(), before)


class KclLanguageTests(unittest.TestCase):
    def test_catalog_only_selection_changes_active_dictionary_view(self):
        catalog = rt.TextDictionaries(languages=['ENGLISH','FRENCH'],
                                      sources={'one':'$1 "Ready"', 'two':'$1 "Pret"'})
        ctx = rt.ExecutionContext(dictionaries=catalog, kcl=rt.KclCommands(dictionary_commands=True))
        self.assertEqual(issue(ctx, 'LOAD DICT one MENU')['S'], 0)
        self.assertEqual(issue(ctx, 'LOAD DICT two MENU FRENCH')['S'], 0)
        self.assertEqual(issue(ctx, 'SET LANG FRENCH')['S'], 0)
        self.assertEqual(listing(ctx, 'SHOW DICTS'), (0, [
            {'language':'FRENCH','name':'MENU','source':'TWO.TX'}
        ]))
        self.assertEqual(listing(ctx, 'SHOW LANGS'), (0, [
            {'language':'ENGLISH','active':False,'default':True},
            {'language':'FRENCH','active':True,'default':False},
        ]))
        self.assertEqual(listing(ctx, 'SHOW LANG'), (0, [{'language':'FRENCH','default':'ENGLISH'}]))
        task, _ = compile_program("READ_DICT('MENU',1,lines,1,n,s)",
                                  decl='lines:ARRAY[1] OF STRING[16] n,s:INTEGER', context=ctx)
        self.assertEqual(task.run()['LINES'], ['Pret'])
        self.assertEqual(issue(ctx, 'SET LANGUAGE DEFAULT')['S'], 0)
        self.assertEqual(rt.ExecutionContext.from_config(ctx.to_config()).to_config(), ctx.to_config())

    def test_pendant_selection_preflights_catalog_and_reuses_history(self):
        pendant = rt.PendantDisplay(languages=['ENGLISH','FRENCH','GERMAN'])
        catalog = rt.TextDictionaries(languages=['ENGLISH','FRENCH','SPANISH'])
        ctx = rt.ExecutionContext(pendant=pendant, dictionaries=catalog,
                                  kcl=rt.KclCommands(dictionary_commands=True))
        self.assertEqual(issue(ctx, 'SET LANG GERMAN', nowait=True), {'S':0,'N':33003})
        self.assertEqual((pendant.language, pendant.history), ('ENGLISH', []))
        self.assertEqual(issue(ctx, 'SET LANGUAGE FRENCH')['S'], 0)
        self.assertEqual(pendant.history[-1]['operation'], 'SET_LANG')
        self.assertEqual(listing(ctx, 'SHOW DICTS'), (0, []))
        status, rows = listing(ctx, 'SHOW LANGS')
        self.assertEqual((status, [row['language'] for row in rows]), (0, ['ENGLISH','FRENCH']))
        self.assertEqual(catalog.language, 'ENGLISH')
        self.assertEqual(rt.ExecutionContext.from_config(ctx.to_config()).pendant.language, 'FRENCH')


class KclPoseListingTests(unittest.TestCase):
    def test_current_pose_uses_task_group_and_preserves_external_axes(self):
        ctx = rt.ExecutionContext.from_config({
            'kcl':{'environment_commands':True}, 'robot':{
                'active_group':2, 'groups':{
                    '1':{'dh':[{'a':100}], 'current':{'joints':{'type':['JOINTPOS',1],'value':[0.0]}}},
                    '2':{'dh':[{'a':200},{'type':'prismatic'}], 'external_axes':1,
                         'current':{'joints':{'type':['JOINTPOS',2],'value':[0.0,42.0]}}},
                },
            },
        })
        status, rows = listing(ctx, 'SHOW CURPOS')
        self.assertEqual(status, 0)
        row, = rows
        self.assertEqual((row['group'],row['pose']['X'],row['pose']['EXT1']), (2,200.0,42.0))
        output = []
        task = program("KCL('SHOW CURPOS',s)", prefix='%DEFGROUP=1', context=ctx, write=output.append)
        self.assertEqual(task.run()['S'], 0)
        row = json.loads(''.join(output))
        self.assertEqual((row['group'],row['pose']['X'],row['pose']['EXT1']), (1,100.0,0.0))

    def test_pose_requires_explicit_current_state(self):
        ctx = rt.ExecutionContext(kcl=rt.KclCommands(environment_commands=True))
        self.assertEqual(listing(ctx, 'SHOW CURPOS'), (4, []))
