"""Trusted generated-module pins, typed linking and saved project replay."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from karel2py import runner, translate
from karel2py.project_input_discovery import discover_project_document
from karel2py.project_run import create_project_document, inspect_project_modules


ROOT = Path(__file__).resolve().parents[1]
MISSING = {'uninitialized': True}


class SavedProjectTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.document = self.folder / 'session.run.json'

    def module(self, program, body='', declarations='VAR n,s:INTEGER', routines='', *, cooperative=True):
        source = f'PROGRAM {program} {declarations} {routines} BEGIN {body} END {program}'
        path = self.folder / (program.lower() + '.py')
        path.write_bytes(translate(source, cooperative=cooperative).python_source.encode())
        return path

    def create(self, *modules, **options):
        return create_project_document(modules, self.document, entry='main', **options)

    def cli(self, module, *arguments):
        return subprocess.run([sys.executable, '-m', module, *map(str, arguments)], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)

    def test_prepare_without_execution_and_replay_imports_with_fresh_context(self):
        main = self.module('MAIN', 'n=add(4) WRITE(n,CR)', declarations='VAR n FROM LIB:INTEGER',
                           routines='ROUTINE add(x:INTEGER):INTEGER FROM LIB')
        lib = self.module('LIB', routines='ROUTINE add(x:INTEGER):INTEGER BEGIN n=n+x RETURN n END add')
        context = {'variables': [{'program': 'LIB', 'path': 'N', 'type': 'INTEGER', 'value': 3}]}
        with patch('builtins.exec', side_effect=AssertionError('target executed during preparation')):
            prepared = self.create(main, lib, context=context)
        self.assertEqual(prepared['target']['modules'], [
            {'path': path.name, 'program': name, 'sha256': sha256(path.read_bytes()).hexdigest()}
            for path, name in ((main, 'MAIN'), (lib, 'LIB'))])
        self.assertIsNone(prepared['results'])
        for _ in range(2):
            document = runner.run_document(self.document)
            self.assertEqual(document['inputs']['context'], context)
            result = document['results']
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['programs']['MAIN']['values']['N'], 7)
            self.assertEqual(result['programs']['LIB']['values']['N'], 7)
            self.assertIn('7', result['text_output'])

    def test_linked_templates_distinguish_owners_and_support_selected_edits(self):
        main = self.module('MAIN', 's=n+read_n() copied=values',
                           'VAR n,s:INTEGER values,copied:ARRAY[2] OF INTEGER',
                           'ROUTINE read_n:INTEGER FROM LIB')
        lib = self.module('LIB', routines='ROUTINE read_n:INTEGER BEGIN RETURN n END read_n')
        context = {'variables': [dict(program='LIB', path='N', type='INTEGER', value=11)]}
        with patch('builtins.exec', side_effect=AssertionError('target executed during preparation')):
            created = self.create(lib, main, context=context, discover=True)
        template = created['inputs']['template']
        self.assertEqual(template['target'], created['target'])
        self.assertEqual(template['discovery']['target'], created['target'])
        self.assertEqual({(row['program'], row['path']): row['status'] for row in template['bindings']},
                         {('MAIN', 'N'): 'missing', ('MAIN', 'VALUES'): 'missing', ('LIB', 'N'): 'supplied'})
        self.assertEqual(context['variables'], [dict(program='LIB', path='N', type='INTEGER', value=11)])

        revision = self.document.read_bytes()
        for owner, value in [('MAIN', '4'), ('LIB', '3')]:
            _, revision = runner.save_input_value(
                self.document, ('variable', owner, 'N'), 'INTEGER', value, expected=revision)
        _, revision = runner.save_input_structure(
            self.document, ('variable', 'MAIN', 'VALUES'), [5, 6], expected=revision)
        with self.assertRaisesRegex(ValueError, 'no longer in the discovery report'):
            runner.save_input_value(self.document, ('variable', 'OTHER', 'N'), 'INTEGER', '9', expected=revision)
        self.assertEqual(self.document.read_bytes(), revision)
        run = runner.run_document(self.document, expected=revision)
        self.assertEqual(run['results']['status'], 'completed')
        main_values = run['results']['programs']['MAIN']['values']
        self.assertEqual((main_values['N'], main_values['S'], main_values['COPIED']), (4, 7, [5, 6]))
        self.assertEqual(run['results']['programs']['LIB']['values']['N'], 3)
        saved, _ = runner.save_input_value(
            self.document, ('variable', 'LIB', 'N'), 'INTEGER', '17', expected=self.document.read_bytes())
        self.assertEqual(saved['results'], run['results'])
        self.assertEqual(saved['inputs']['template']['target'], run['target'])

    def test_linked_whole_path_discover_edit_and_refresh_resolve_imported_owner(self):
        types = ('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'header_t=STRUCTURE total:INTEGER ENDSTRUCTURE '
                 'route_t=PATH NODEDATA=node_t PATHHEADER=header_t')
        main = self.module('MAIN', 'route[1].amount=18 show_route(route)',
                           types+' VAR route FROM LIB:route_t',
                           'ROUTINE show_route(value:route_t) FROM LIB')
        lib = self.module('LIB', declarations=types+' VAR route:route_t',
                          routines='ROUTINE show_route(value:route_t) BEGIN WRITE(value,CR) END show_route')
        schema = ['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]],
                  ['STRUCTURE', 'HEADER_T', [['TOTAL', ['INTEGER']]]]]
        seed = dict(program='lib', path='route', type=schema,
                    value=dict(nodes=[{'AMOUNT': MISSING}], data={'TOTAL': MISSING}))
        with patch('builtins.exec', side_effect=AssertionError('discovery executed pinned Python')):
            prepared = self.create(main, lib, context={'variables': [seed]}, discover=True)
            inspected = discover_project_document(self.document)

        report = prepared['inputs']['template']['discovery']
        self.assertEqual(inspected['inputs'], report['inputs'])
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(report['path_storage'], [dict(program='LIB', path='ROUTE', type=schema)])
        candidate, = inspected['inputs']
        self.assertEqual((candidate['program'], candidate['path']), ('LIB', 'ROUTE[0]'))
        self.assertEqual(candidate['locations'][0]['routine'], 'SHOW_ROUTE')

        _, revision = runner.save_input_structure(self.document, ('variable', 'LIB', 'ROUTE[0]'),
                                                  {'TOTAL': 12}, expected=self.document.read_bytes())
        revised = self.folder/'revised.run.json'
        refreshed = runner.refresh_project_document(self.document, revised, [main, lib], expected=revision)
        binding, = refreshed['inputs']['template']['bindings']
        self.assertEqual(binding['status'], 'supplied')
        self.assertEqual(self.document.read_bytes(), revision)
        result = runner.run_document(revised)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        self.assertEqual(result['text_output'], ' 12 18\n')

    def test_linked_whole_path_bank_read_preserves_shape_without_value_candidates(self):
        main = self.module('MAIN', 'READ INPUT(routes) CLOSE FILE INPUT',
                           'TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE '
                           'VAR routes:ARRAY[2] OF PATH NODEDATA=row_t')
        spec = ['ARRAY', 2, ['PATH', ['STRUCTURE', 'ROW_T', [['VALUE', ['INTEGER']]]], None]]
        seed = dict(program='MAIN', path='ROUTES', type=spec,
                    value=[dict(nodes=[{'VALUE': MISSING}], data=None), dict(nodes=[], data=None)])
        context = dict(variables=[seed, dict(program='MAIN', path='UNUSED', type='INTEGER', value=9)],
                       files={'data': {'hex': '1f000000'}}, predefined_files={'INPUT': dict(name='data', mode='RB')})
        prepared = self.create(main, context=context, discover=True)
        report = prepared['inputs']['template']['discovery']
        self.assertEqual(report['inputs'], [])
        self.assertEqual(report['path_storage'], [dict(program='MAIN', path='ROUTES', type=spec)])
        self.assertEqual({row['code'] for row in report['unresolved']},
                         {'input-stream', 'file-state', 'file-transport'})

        revised = self.folder/'revised.run.json'
        refreshed = runner.refresh_project_document(self.document, revised, [main])
        self.assertEqual(refreshed['inputs']['context']['variables'], [seed])
        self.assertEqual([row['path'] for row in refreshed['inputs']['template']['refresh']['variables']], ['UNUSED'])
        outputs = runner.run_document(revised)['results']
        self.assertEqual(outputs['status'], 'completed', outputs['error'])
        values = outputs['programs']['MAIN']['values']['ROUTES']
        self.assertEqual(values, [dict(nodes=[{'VALUE': 31}], data=None), dict(nodes=[], data=None)])

    def test_linked_refresh_retains_owner_storage_used_only_for_path_count(self):
        types = 'TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE '
        main = self.module('MAIN', 'IF get_count()=1 THEN WRITE(19) ELSE WRITE(0) ENDIF',
                           routines='ROUTINE get_count:INTEGER FROM LIB')
        lib = self.module('LIB', declarations=types+'VAR route:PATH NODEDATA=row_t',
                          routines='ROUTINE get_count:INTEGER BEGIN RETURN PATH_LEN(route) END get_count')
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['VALUE', ['INTEGER']]]], None]
        seed = dict(program='LIB', path='ROUTE', type=spec, value=dict(nodes=[{'VALUE': MISSING}], data=None))
        self.create(main, lib, context={'variables': [seed]})
        revised = self.folder/'revised.run.json'
        prepared = runner.refresh_project_document(self.document, revised, [main, lib])['inputs']
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(report['inputs'], [])
        self.assertEqual(prepared['context']['variables'], [seed])
        self.assertEqual(report['path_storage'], [dict(program='LIB', path='ROUTE', type=spec)])
        result = runner.run_document(revised)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        self.assertEqual(result['text_output'].strip(), '19')

    def test_linked_tail_edit_refresh_retains_seed_and_resolves_updated_count(self):
        types = 'TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
        main = self.module('MAIN',
                           'APPEND_NODE(route,s) route[PATH_LEN(route)].value=31 '
                           'WRITE(PATH_LEN(route),route)',
                           types+'VAR route FROM LIB:route_t s:INTEGER')
        lib = self.module('LIB', declarations=types+'VAR route:route_t')
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['VALUE', ['INTEGER']]]], None]
        seed = dict(program='LIB', path='ROUTE', type=spec, value=dict(nodes=[{'VALUE': 5}], data=None))
        self.create(main, lib, context={'variables': [seed]})
        revised = self.folder/'revised.run.json'
        prepared = runner.refresh_project_document(self.document, revised, [main, lib])['inputs']
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(prepared['context']['variables'], [seed])
        self.assertEqual([row['path'] for row in report['inputs']], ['ROUTE[1]'])
        result = runner.run_document(revised)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        self.assertEqual(result['text_output'], ' 2 5 31')

    def test_linked_binary_read_uses_source_inserted_path_storage(self):
        types = 'TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE '
        main = self.module('MAIN', 'INSERT_NODE(route,1,s) READ INPUT(route) CLOSE FILE INPUT',
                           types+'VAR route:PATH NODEDATA=row_t s:INTEGER')
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['VALUE', ['INTEGER']]]], None]
        seed = dict(program='MAIN', path='ROUTE', type=spec, value=dict(nodes=[{'VALUE': MISSING}], data=None))
        config = dict(variables=[seed], files={'data': {'hex': '1f00000029000000'}},
                      predefined_files={'INPUT': dict(name='data', mode='RB')})
        self.create(main, context=config)
        revised = self.folder/'revised.run.json'
        prepared = runner.refresh_project_document(self.document, revised, [main])['inputs']
        report = prepared['template']['discovery']
        self.assertEqual(report['inputs'], [])
        self.assertEqual({row['code'] for row in report['unresolved']},
                         {'input-stream', 'file-state', 'file-transport'})
        self.assertEqual(prepared['context']['variables'], [seed])
        result = runner.run_document(revised)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        route = result['programs']['MAIN']['values']['ROUTE']
        self.assertEqual(route['nodes'], [{'VALUE': 31}, {'VALUE': 41}])

    def test_linked_copy_path_converts_selected_data_without_retaining_old_destination(self):
        types = ('TYPE source_t=STRUCTURE amount:REAL ENDSTRUCTURE '
                 'row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'path_t=PATH NODEDATA=source_t ')
        main = self.module('MAIN',
                           'source[2].amount=12.75 COPY_PATH(source,2,2,target,s,TRUE) WRITE(target,CR)',
                           types+'VAR source FROM LIB:path_t target:PATH NODEDATA=row_t s:INTEGER')
        lib = self.module('LIB', declarations=types+'VAR source:path_t')
        source_type = ['PATH', ['STRUCTURE', 'SOURCE_T', [['AMOUNT', ['REAL']]]], None]
        target_type = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        source = dict(program='LIB', path='SOURCE', type=source_type,
                      value=dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': MISSING}], data=None))
        target = dict(program='MAIN', path='TARGET', type=target_type,
                      value=dict(nodes=[{'AMOUNT': 99}], data=None))
        self.create(main, lib, context={'variables': [source, target]})
        revised = self.folder/'revised.run.json'
        prepared = runner.refresh_project_document(self.document, revised, [main, lib])
        report = prepared['inputs']['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertFalse(report['inputs'])
        self.assertEqual(prepared['inputs']['context']['variables'], [source])
        result = runner.run_document(revised)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        self.assertEqual(result['text_output'], ' 12\n')
        self.assertEqual(result['programs']['MAIN']['values']['TARGET']['nodes'], [{'AMOUNT': 12}])

    def test_linked_path_assignment_tracks_converted_array_cell_without_old_seed(self):
        types = ('TYPE source_t=STRUCTURE amount:REAL ENDSTRUCTURE '
                 'row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE from_t=PATH NODEDATA=source_t ')
        main = self.module('MAIN',
                           'source[1].amount=12.75 targets[2]=source WRITE(targets[2],CR)',
                           types+'VAR source FROM LIB:from_t targets:ARRAY[2] OF PATH NODEDATA=row_t')
        lib = self.module('LIB', declarations=types+'VAR source:from_t')
        source_type = ['PATH', ['STRUCTURE', 'SOURCE_T', [['AMOUNT', ['REAL']]]], None]
        target_type = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        source = dict(program='LIB', path='SOURCE', type=source_type,
                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))
        old = dict(program='MAIN', path='TARGETS', type=['ARRAY', 2, target_type],
                   value=[dict(nodes=[], data=None), dict(nodes=[{'AMOUNT': 99}], data=None)])
        self.create(main, lib, context={'variables': [source, old]})
        revised = self.folder/'revised.run.json'
        prepared = runner.refresh_project_document(self.document, revised, [main, lib])
        report = prepared['inputs']['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertFalse(report['inputs'])
        self.assertEqual(prepared['inputs']['context']['variables'], [source])
        result = runner.run_document(revised)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        self.assertEqual(result['text_output'], ' 12\n')
        self.assertEqual(result['programs']['MAIN']['values']['TARGETS'][1]['nodes'], [{'AMOUNT': 12}])

    def test_linked_private_path_argument_and_converted_return_replay(self):
        types = ('TYPE source_t=STRUCTURE amount:REAL ENDSTRUCTURE '
                 'row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'real_path=PATH NODEDATA=source_t int_path=PATH NODEDATA=row_t ')
        main = self.module('MAIN', 'source[1].amount=12.75 target=build((source)) WRITE(target,CR)',
                           types+'VAR source:real_path target:int_path',
                           'ROUTINE build(v:real_path):int_path FROM LIB')
        lib = self.module('LIB', declarations=types,
                          routines='ROUTINE build(v:real_path):int_path VAR s:INTEGER '
                                   'BEGIN APPEND_NODE(v,s) v[2].amount=21.75 RETURN v END build')
        source_type = ['PATH', ['STRUCTURE', 'SOURCE_T', [['AMOUNT', ['REAL']]]], None]
        source = dict(program='MAIN', path='SOURCE', type=source_type,
                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))
        self.create(main, lib, context={'variables': [source]})
        revised = self.folder/'revised.run.json'
        prepared = runner.refresh_project_document(self.document, revised, [main, lib])
        report = prepared['inputs']['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertFalse(report['inputs'])
        self.assertEqual(prepared['inputs']['context']['variables'], [source])
        result = runner.run_document(revised)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        self.assertEqual(result['text_output'], ' 12 21\n')
        values = result['programs']['MAIN']['values']
        self.assertEqual(values['TARGET']['nodes'], [{'AMOUNT': 12}, {'AMOUNT': 21}])
        self.assertEqual(values['SOURCE']['nodes'], [{'AMOUNT': 12.75}])

    def test_linked_seed_conversion_keeps_input_owner_and_completes_inserted_record(self):
        types = ('TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'source_t=STRUCTURE amount:REAL ENDSTRUCTURE ')
        main = self.module('MAIN', 'INSERT_NODE(route,1,seed,s,TRUE) WRITE(route[1],CR)',
                           types+'VAR route:PATH NODEDATA=row_t seed FROM LIB:source_t s:INTEGER')
        lib = self.module('LIB', declarations=types+'VAR seed:source_t')
        root = dict(program='MAIN', path='ROUTE',
                    type=['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None],
                    value=dict(nodes=[], data=None))
        seed = dict(program='LIB', path='SEED',
                    type=['STRUCTURE', 'SOURCE_T', [['AMOUNT', ['REAL']]]], value={'AMOUNT': MISSING})
        self.create(main, lib, context={'variables': [root, seed]})
        revised = self.folder/'revised.run.json'
        prepared = runner.refresh_project_document(self.document, revised, [main, lib])
        report = prepared['inputs']['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        candidate, = report['inputs']
        self.assertEqual((candidate['program'], candidate['path']), ('LIB', 'SEED'))
        runner.save_input_structure(revised, ('variable', 'LIB', 'SEED'), {'AMOUNT': 12.75},
                                    expected=revised.read_bytes())
        result = runner.run_document(revised)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        self.assertEqual(result['text_output'], ' 12\n')
        self.assertEqual(result['programs']['MAIN']['values']['ROUTE']['nodes'], [{'AMOUNT': 12}])

    def test_linked_child_after_a_shift_does_not_guess_a_saved_node_origin(self):
        decl = 'TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE '
        main = self.module('MAIN', "DELETE_NODE(route,1,s) RUN_TASK('CHILD',0,FALSE,FALSE,0,s)",
                           decl+'VAR route:PATH NODEDATA=row_t s:INTEGER')
        child = self.module('CHILD', 'WRITE(route[1].value)', decl+'VAR route FROM MAIN:PATH NODEDATA=row_t')
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['VALUE', ['INTEGER']]]], None]
        context = {'variables': [dict(program='MAIN', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'VALUE': 1}, {'VALUE': 2}], data=None))]}
        prepared = self.create(main, child, context=context, discover=True)
        report = prepared['inputs']['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertEqual(report['path_storage'], [dict(program='MAIN', path='ROUTE', type=spec)])
        self.assertTrue(any('Saved origin of ROUTE[1] is unresolved' in row['message']
                            and row['location']['program'] == 'CHILD' for row in report['unresolved']), report)

    def test_linked_selected_path_read_retains_storage_even_without_field_inputs(self):
        decl = 'TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE VAR route:PATH NODEDATA=row_t'
        main = self.module('MAIN', 'READ INPUT(route[2])', decl)
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['VALUE', ['INTEGER']]]], None]
        seed = dict(program='MAIN', path='ROUTE', type=spec,
                    value=dict(nodes=[{'VALUE': 1}, {'VALUE': MISSING}], data=None))
        context = dict(variables=[seed], files={'data': ' 25'},
                       predefined_files={'INPUT': dict(name='data', mode='RO')})
        self.create(main, context=context)
        revised = self.folder/'revised.run.json'
        refreshed = runner.refresh_project_document(self.document, revised, [main])
        self.assertEqual(refreshed['inputs']['context']['variables'], [seed])
        self.assertFalse(refreshed['inputs']['template']['bindings'])
        result = runner.run_document(revised)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        route = result['programs']['MAIN']['values']['ROUTE']
        self.assertEqual(route['nodes'], [{'VALUE': 1}, {'VALUE': 25}])

    def test_linked_whole_path_shape_stays_unproven_after_concurrent_effects(self):
        decl = 'TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE VAR route:PATH NODEDATA=row_t s:INTEGER'
        schema = ['PATH', ['STRUCTURE', 'ROW_T', [['VALUE', ['INTEGER']]]], None]
        context = {'variables': [dict(program='MAIN', path='ROUTE', type=schema,
                                      value=dict(nodes=[{'VALUE': 7}], data=None))]}
        main = self.module('MAIN', "RUN_TASK('CHILD',0,FALSE,FALSE,0,s) WRITE(route)", decl)
        child = self.module('CHILD', 'DELETE_NODE(route,1,s)',
                            'TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE '
                            'VAR route FROM MAIN:PATH NODEDATA=row_t s:INTEGER')
        prepared = self.create(main, child, context=context, discover=True)
        report = prepared['inputs']['template']['discovery']
        self.assertNotIn('path_storage', report)
        self.assertFalse(report['inputs'])
        self.assertTrue(any(row['code'] == 'schema' and row['message'].endswith('ROUTE')
                            for row in report['unresolved']), report)

    def test_prepare_existing_linked_document_preserves_results_and_checks_revision(self):
        main = self.module('MAIN', 'WRITE(n)', 'VAR n FROM LIB:INTEGER')
        lib = self.module('LIB')
        seed = dict(program='LIB', path='N', type='INTEGER', value=3)
        self.create(main, lib, context={'variables': [seed]})
        previous = runner.run_document(self.document)
        before = self.document.read_bytes()
        saved, revision = runner.prepare_project_document(
            self.document, context={'variables': [dict(seed, value=8)]}, expected=before)
        self.assertEqual(saved['results'], previous['results'])
        self.assertEqual(saved['target'], previous['target'])
        self.assertEqual(saved['limits'], previous['limits'])
        self.assertEqual(saved['inputs']['context']['variables'], [dict(seed, value=8)])
        with self.assertRaisesRegex(ValueError, 'changed on disk'):
            runner.prepare_project_document(self.document, expected=before)
        with self.assertRaisesRegex(ValueError, 'Invalid input template context'):
            runner.prepare_project_document(self.document, context={'variables': False}, expected=revision)
        self.assertEqual(self.document.read_bytes(), revision)

        self.assertEqual(runner.run_document(self.document)['results']['text_output'].strip(), '8')
        saved, _ = runner.read_document(self.document)
        saved['inputs']['template']['target']['modules'].reverse()
        self.document.write_text(json.dumps(saved), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale input-template'):
            runner.read_document(self.document)

    def test_linked_template_keeps_service_requirements_and_updates_binding_status(self):
        main = self.module('MAIN', 'read_inputs()', routines='ROUTINE read_inputs FROM LIB')
        lib = self.module('LIB', declarations='VAR enabled:BOOLEAN text:STRING[8] status:INTEGER',
                          routines='ROUTINE read_inputs BEGIN enabled=DIN[1] GET_STR_REG(1,text,status) END read_inputs')
        context = {'strings': {'count': 1, 'values': {'1': 'ready'}}}
        created = self.create(main, lib, discover=True, context=context)
        self.assertEqual(created['inputs']['context'], context)
        template = created['inputs']['template']
        self.assertEqual({row['kind']: row['status'] for row in template['bindings']},
                         {'port': 'unmapped', 'string_register': 'supplied'})
        self.assertIn('ports', [row['service'] for row in template['requirements'] if row['code'] == 'service'])
        context['ports'] = {'counts': {'DIN': 1}, 'values': {'DIN': {'1': False}}}
        updated, revision = runner.save_context(self.document, json.dumps(context), expected=self.document.read_bytes())
        template = updated['inputs']['template']
        self.assertTrue(all(row['status'] == 'supplied' for row in template['bindings']))
        self.assertEqual(template['requirements'], [])
        result = runner.run_document(self.document, expected=revision)['results']
        self.assertEqual(result['status'], 'completed')
        lib_values = result['programs']['LIB']['values']
        self.assertEqual((lib_values['ENABLED'], lib_values['TEXT']), (False, 'ready'))

    def test_linked_edit_rechecks_all_modules_before_publication(self):
        main, lib = self.module('MAIN', 'WRITE(n)'), self.module('LIB')
        self.create(main, lib, discover=True)
        before = self.document.read_bytes()
        from karel2py.runner_values import scalar_slot

        def edit_and_change_pin(*args):
            with lib.open('ab') as stream:
                stream.write(b'# changed during input edit\n')
            return scalar_slot(*args)

        with patch('karel2py.runner_values.scalar_slot', side_effect=edit_and_change_pin):
            with self.assertRaisesRegex(ValueError, 'module changed during input preparation'):
                runner.save_input_value(self.document, ('variable', 'MAIN', 'N'), 'INTEGER', '5', expected=before)
        self.assertEqual(self.document.read_bytes(), before)

    def test_cli_prepares_linked_inputs_and_replays_explicit_context(self):
        main = self.module('MAIN', 'WRITE(n)', 'VAR n FROM LIB:INTEGER')
        lib = self.module('LIB')
        command = self.cli('karel2py.runner', 'create-project', self.document, main, lib, '--entry', 'MAIN', '--discover')
        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertEqual(json.loads(command.stdout)['inputs'], 1)
        before = self.document.read_bytes()
        read_only = self.cli('karel2py.runner', 'discover-project', self.document)
        self.assertEqual(read_only.returncode, 0, read_only.stderr)
        self.assertEqual(json.loads(read_only.stdout)['inputs'][0]['program'], 'LIB')
        self.assertEqual(self.document.read_bytes(), before)

        context = self.folder / 'context.json'
        context.write_text(json.dumps({'variables': [dict(program='LIB', path='N', type='INTEGER', value=13)]}),
                           encoding='utf-8')
        command = self.cli('karel2py.runner', 'prepare-project', self.document, '--context', context)
        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertEqual(json.loads(command.stdout)['requirements'], 0)
        command = self.cli('karel2py.runner', 'run', self.document)
        self.assertEqual(command.returncode, 0, command.stderr)
        saved, revision = runner.read_document(self.document)
        self.assertEqual(saved['results']['text_output'].strip(), '13')
        context.write_text('null', encoding='utf-8')
        command = self.cli('karel2py.runner', 'prepare-project', self.document, '--context', context)
        self.assertNotEqual(command.returncode, 0)
        self.assertEqual(self.document.read_bytes(), revision)

    def test_refresh_project_preserves_owners_limits_and_compatible_array_cells(self):
        main = self.module('MAIN', 's=n+read_n()+gone+values[1]+values[2] n=99',
                           'VAR n,s,gone:INTEGER values:ARRAY[2] OF INTEGER', 'ROUTINE read_n:INTEGER FROM LIB')
        lib = self.module('LIB', routines='ROUTINE read_n:INTEGER BEGIN RETURN n END read_n')
        variables = [dict(program=owner, path=path, type=spec, value=value) for owner, path, spec, value in (
            ('MAIN', 'N', 'INTEGER', 4), ('LIB', 'N', 'INTEGER', 3), ('MAIN', 'GONE', 'INTEGER', 10),
            ('MAIN', 'VALUES', ['ARRAY', 2, ['INTEGER']], [5, 6]))]
        context = {'variables': variables, 'numeric': {'count': 1, 'values': {'1': 21}}}
        self.create(main, lib, context=context, discover=True, max_steps=123, max_cycles=456, max_output_chars=789)
        original = runner.run_document(self.document)
        self.assertEqual(original['results']['programs']['MAIN']['values']['N'], 99)
        before = self.document.read_bytes()
        main = self.module('MAIN', 's=n+read_n()+values[1]+values[2]',
                           'VAR n,s:INTEGER values:ARRAY[3] OF INTEGER', 'ROUTINE read_n:INTEGER FROM LIB')
        replacement_lib = self.folder / 'new_lib.py'
        lib.rename(replacement_lib)
        new_folder = self.folder / 'revised'
        new_folder.mkdir()
        destination = new_folder / 'linked.run.json'
        with patch('builtins.exec', side_effect=AssertionError('target executed during refresh')):
            refreshed = runner.refresh_project_document(self.document, destination, [replacement_lib, main], expected=before)
        self.assertEqual(self.document.read_bytes(), before)
        self.assertEqual(refreshed['limits'], original['limits'])
        self.assertIsNone(refreshed['results'])
        self.assertEqual([row['program'] for row in refreshed['target']['modules']], ['LIB', 'MAIN'])
        for pin, path in zip(refreshed['target']['modules'], (replacement_lib, main), strict=True):
            self.assertEqual((destination.parent / pin['path']).resolve(), path)
        annotations = refreshed['inputs']['template']['refresh']
        self.assertEqual(annotations['previous_target'], original['target'])
        self.assertEqual(annotations['previous_document'],
                         dict(path=str(Path('../session.run.json')), sha256=sha256(before).hexdigest()))
        self.assertTrue(annotations['comparison_complete'])
        self.assertEqual([(row['program'], row['path']) for row in annotations['changes']['removed']], [('MAIN', 'GONE')])
        self.assertEqual([(row['path'], row['status'], row['preserved_leaves']) for row in annotations['variables']],
                         [('GONE', 'not-discovered', 0), ('VALUES', 'migrated', 2)])
        inputs = refreshed['inputs']['context']
        self.assertEqual(inputs['numeric'], context['numeric'])
        self.assertEqual({(row['program'], row['path']): row['value'] for row in inputs['variables']},
                         {('MAIN', 'N'): 4, ('LIB', 'N'): 3, ('MAIN', 'VALUES'): [5, 6, MISSING]})
        result = runner.run_document(destination)['results']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['programs']['MAIN']['values']['S'], 18)
        saved, revision = runner.prepare_project_document(destination)
        self.assertEqual(saved['inputs']['template']['refresh'], annotations)
        self.assertEqual(saved['results'], result)
        saved, _ = runner.save_input_value(destination, ('variable', 'LIB', 'N'), 'INTEGER', '9', expected=revision)
        self.assertEqual(saved['inputs']['template']['refresh'], annotations)

    def test_refresh_project_resets_incompatible_types_without_guessing_new_owners(self):
        main = self.module('MAIN', 'WRITE(n,flag)', 'VAR n,flag:INTEGER')
        context = {'variables': [dict(program='MAIN', path=path, type='INTEGER', value=value)
                                 for path, value in [('N', 7), ('FLAG', 12)]]}
        self.create(main, discover=True, context=context)
        main = self.module('MAIN', '', 'VAR flag:BOOLEAN', 'ROUTINE show_flag BEGIN WRITE(flag) END show_flag')
        other = self.module('OTHER', 'show_flag() WRITE(n)', 'VAR n:INTEGER', 'ROUTINE show_flag FROM MAIN')
        destination = self.folder / 'revised.run.json'
        before = self.document.read_bytes()
        result = self.cli('karel2py.runner', 'refresh-project', self.document, destination, other, main, '--entry', 'other')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['changes'],
                         dict(added=1, removed=1, changed=1, retained=0, unresolved=0))
        self.assertEqual(self.document.read_bytes(), before)
        saved, _ = runner.read_document(destination)
        self.assertEqual(saved['target']['program'], 'OTHER')
        refresh = saved['inputs']['template']['refresh']
        self.assertEqual([(row['program'], row['path'], row['status']) for row in refresh['variables']],
                         [('MAIN', 'N', 'not-discovered'), ('MAIN', 'FLAG', 'reset')])
        self.assertEqual({(row['program'], row['path']): row['value'] for row in saved['inputs']['context']['variables']},
                         {('MAIN', 'FLAG'): MISSING, ('OTHER', 'N'): MISSING})
        saved['inputs']['template']['refresh']['previous_target']['modules'][0]['sha256'] = 'bad'
        destination.write_text(json.dumps(saved), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Malformed previous linked refresh target'):
            runner.read_document(destination)

    def test_refresh_project_reports_unproven_removals_when_new_linkage_is_unresolved(self):
        main = self.module('MAIN', 'WRITE(read_n())', routines='ROUTINE read_n:INTEGER FROM LIB')
        lib = self.module('LIB', routines='ROUTINE read_n:INTEGER BEGIN RETURN n END read_n')
        context = {'variables': [dict(program='LIB', path='N', type='INTEGER', value=3)]}
        self.create(main, lib, discover=True, context=context)
        with lib.open('ab') as stream:
            stream.write(b'raise AssertionError("module executed during refresh")\n')
        destination = self.folder / 'revised.run.json'
        saved = runner.refresh_project_document(self.document, destination, [main, lib])
        template = saved['inputs']['template']
        self.assertFalse(template['refresh']['comparison_complete'])
        self.assertFalse(template['refresh']['changes']['removed'])
        self.assertEqual(template['refresh']['changes']['unresolved'][0]['before']['program'], 'LIB')
        self.assertEqual(template['refresh']['variables'][0]['status'], 'unresolved')
        self.assertEqual(saved['inputs']['context']['variables'], [])
        self.assertEqual([row['code'] for row in template['discovery']['unresolved']], ['contract', 'routine'])

    def test_refresh_project_context_only_source_and_fresh_provenance_on_next_refresh(self):
        main = self.module('MAIN', 'WRITE(n)')
        context = {'variables': [dict(program='MAIN', path='N', type='INTEGER', value=8)]}
        self.create(main, context=context)
        first = self.folder / 'first.run.json'
        saved = runner.refresh_project_document(self.document, first, [main])
        template = saved['inputs']['template']
        self.assertFalse(template['refresh']['baseline_known'])
        self.assertEqual(template['refresh']['changes']['unresolved'][0]['after']['path'], 'N')
        second = self.folder / 'second.run.json'
        saved = runner.refresh_project_document(first, second, [main])
        refresh = saved['inputs']['template']['refresh']
        self.assertTrue(refresh['comparison_complete'])
        self.assertEqual(refresh['previous_document']['path'], first.name)
        self.assertEqual(refresh['changes']['retained'][0]['path'], 'N')
        self.assertEqual(runner.run_document(second)['results']['text_output'].strip(), '8')

    def test_refresh_project_refuses_stale_source_and_reviewed_pins(self):
        main, lib = self.module('MAIN'), self.module('LIB')
        self.create(main, lib, discover=True)
        original = self.document.read_bytes()
        destination = self.folder / 'revised.run.json'
        with self.assertRaisesRegex(ValueError, 'changed on disk'):
            runner.refresh_project_document(self.document, destination, [main, lib], expected=b'stale')
        pins = inspect_project_modules([main, lib])
        with lib.open('ab') as stream:
            stream.write(b'# changed after module review\n')
        with self.assertRaisesRegex(ValueError, 'changed after review'):
            runner.refresh_project_document(self.document, destination, [main, lib], expected_modules=pins)
        self.assertEqual(self.document.read_bytes(), original)
        self.assertFalse(destination.exists())

    def test_refresh_project_rechecks_source_and_module_bytes_before_publication(self):
        from karel2py.input_refresh import refresh_linked_inputs

        main, lib = self.module('MAIN'), self.module('LIB')
        self.create(main, lib, discover=True)
        original = self.document.read_bytes()
        lib_bytes = lib.read_bytes()
        destination = self.folder / 'revised.run.json'
        for path, expected_error in [(lib, 'module changed during'), (self.document, 'external edits preserved')]:
            with self.subTest(path=path):
                modified = path.read_bytes() + b'\n'

                def refresh_and_change(*args):
                    prepared = refresh_linked_inputs(*args)
                    path.write_bytes(modified)
                    return prepared

                with patch('karel2py.input_refresh.refresh_linked_inputs', side_effect=refresh_and_change):
                    with self.assertRaisesRegex(ValueError, expected_error):
                        runner.refresh_project_document(self.document, destination, [main, lib])
                self.assertFalse(destination.exists())
                self.assertEqual(path.read_bytes(), modified)
                if path == lib:
                    self.assertEqual(self.document.read_bytes(), original)
                    lib.write_bytes(lib_bytes)

    def test_refresh_project_protects_existing_destinations_and_refuses_running_marker(self):
        main, lib = self.module('MAIN'), self.module('LIB')
        document = self.create(main, lib, discover=True)
        original = self.document.read_bytes()
        destination = self.folder / 'revised.run.json'
        destination.write_bytes(b'existing')
        for path, error in [(destination, FileExistsError), (self.document, ValueError), (main, ValueError)]:
            with self.subTest(path=path), self.assertRaises(error):
                runner.refresh_project_document(self.document, path, [main])
        self.assertEqual(destination.read_bytes(), b'existing')
        self.assertEqual(self.document.read_bytes(), original)
        document['results'] = {'status': 'running'}
        running = json.dumps(document).encode()
        self.document.write_bytes(running)
        with self.assertRaisesRegex(ValueError, 'running or interrupted'):
            runner.refresh_project_document(self.document, destination, [main, lib])
        self.assertEqual(self.document.read_bytes(), running)

    def test_discovery_follows_linked_reference_writes_and_transitive_global_owners(self):
        main = self.module('MAIN', 'fill(cell) w=11 WRITE(n,cell)', 'VAR n,w FROM BRIDGE:INTEGER cell:INTEGER',
                           'ROUTINE fill(x:INTEGER) FROM BRIDGE')
        bridge = self.module('BRIDGE', 'WRITE(unused)', 'VAR n,w FROM DATA:INTEGER unused:INTEGER',
                             'ROUTINE fill(dst:INTEGER) BEGIN dst=w END fill')
        data = self.module('DATA', declarations='VAR n,w:INTEGER')
        context = {'variables': [dict(program='DATA', path=name, type='INTEGER', value=value)
                                 for name, value in (('N', 2), ('W', 3))]}
        created = self.create(main, bridge, data, context=context)
        revision = self.document.read_bytes()
        with patch('builtins.exec', side_effect=AssertionError('discovery executed the target')):
            report = discover_project_document(self.document, expected=revision)
        self.assertEqual(self.document.read_bytes(), revision)
        self.assertEqual(report['target']['modules'], created['target']['modules'])
        self.assertEqual(report['target']['sha256'], sha256(revision).hexdigest())
        self.assertTrue(report['complete'])
        self.assertEqual([(row['program'], row['path'], row['certainty']) for row in report['inputs']],
                         [('DATA', 'N', 'required'), ('DATA', 'W', 'required')])
        origin = report['inputs'][1]['locations'][0]
        self.assertEqual((origin['program'], origin['routine']), ('BRIDGE', 'FILL'))
        self.assertEqual(runner.run_document(self.document)['results']['programs']['MAIN']['values']['CELL'], 3)

    def test_linked_discovery_follows_scheduled_body_and_imported_storage(self):
        main = self.module('MAIN',
                           "target='child' RUN_TASK(target,0,FALSE,FALSE,0,s) WAIT FOR EVENT[1]",
                           'VAR target:STRING[8] s:INTEGER')
        child = self.module('CHILD', 'n=4 WRITE(n+seed,CR) SIGNAL EVENT[1]',
                            'VAR n:INTEGER seed FROM DATA:INTEGER')
        data = self.module('DATA', 'WRITE(untouched)', 'VAR seed,untouched:INTEGER')
        context = {'variables': [dict(program='DATA', path='SEED', type='INTEGER', value=17)]}
        with patch('builtins.exec', side_effect=AssertionError('module executed while discovering tasks')):
            saved = self.create(main, child, data, discover=True, context=context)
            report = discover_project_document(self.document)
        self.assertEqual([(row['program'], row['path'], row['certainty']) for row in report['inputs']],
                         [('DATA', 'SEED', 'conditional')])
        self.assertEqual(report['inputs'][0]['locations'][0]['program'], 'CHILD')
        self.assertEqual([row['status'] for row in saved['inputs']['template']['bindings']], ['supplied'])
        self.assertIn('task-scheduling', [row['code'] for row in report['unresolved']])
        self.assertFalse(report['complete'])
        result = runner.run_document(self.document)['results']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['text_output'].split(), ['21'])

    def test_linked_discovery_bounds_cyclic_dynamic_and_missing_task_targets(self):
        main = self.module('MAIN', "RUN_TASK('CHILD',0,FALSE,FALSE,0,s) RUN_TASK(varname,0,FALSE,FALSE,0,s)",
                           'VAR varname:STRING[8] s:INTEGER')
        child = self.module('CHILD',
                            "WRITE(n) RUN_TASK('MAIN',0,FALSE,FALSE,0,s) RUN_TASK('MISSING',0,FALSE,FALSE,0,s)")
        self.create(main, child)
        report = discover_project_document(self.document)
        self.assertEqual([(row['program'], row['path']) for row in report['inputs']],
                         [('CHILD', 'N'), ('MAIN', 'VARNAME')])
        targets = [row for row in report['unresolved'] if row['code'] == 'task-target']
        self.assertEqual([row['location']['program'] for row in targets], ['CHILD', 'CHILD', 'MAIN'])
        self.assertIn('Recursive', targets[0]['message'])
        self.assertIn('MISSING', targets[1]['message'])
        self.assertIn('dynamic', targets[2]['message'])

    def test_linked_paused_entry_does_not_require_dormant_body_inputs(self):
        main = self.module('MAIN', "target='CHILD' RUN_TASK(target,0,TRUE,FALSE,0,s) WRITE(s,CR)",
                           'VAR target:STRING[12] s:INTEGER')
        child = self.module('CHILD', 'WRITE(n,CR)')
        with patch('builtins.exec', side_effect=AssertionError('module executed during parked entry discovery')):
            saved = self.create(main, child, discover=True)
        report = saved['inputs']['template']['discovery']
        self.assertEqual(report['inputs'], [])
        self.assertEqual([row['code'] for row in report['unresolved']], ['task-scheduling'])
        result = runner.run_document(self.document)['results']
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(result['programs']['CHILD'], {'state': 'paused', 'values': {'N': MISSING, 'S': MISSING}})
        self.assertEqual(result['text_output'].split(), ['0'])

    def test_linked_continuations_discover_the_parked_entry_after_a_signal(self):
        child = self.module('CHILD', 'WRITE(n,CR)')
        context = {'variables': [
            dict(program='MAIN', path='EVENT_NO', type='INTEGER', value=2),
            dict(program='CHILD', path='N', type='INTEGER', value=21),
        ]}
        for index, continuation in enumerate(('CONT_TASK(target,s)', 'RUN_TASK(target,9,TRUE,FALSE,0,s)',
                                               'RESUME PROGRAM[1]')):
            with self.subTest(continuation=continuation):
                main = self.module('MAIN', """
                    target='CHILD' RUN_TASK(target,0,TRUE,FALSE,0,s)
                    SIGNAL EVENT[event_no] WAIT FOR EVENT[event_no] DELAY 1
                    """ + continuation, 'VAR target:STRING[12] s,event_no:INTEGER')
                document = self.folder / f'resume-{index}.run.json'
                saved = create_project_document([child, main], document, entry='MAIN', context=context, discover=True)
                report = saved['inputs']['template']['discovery']
                self.assertEqual({(row['program'], row['path']): row['certainty'] for row in report['inputs']},
                                 {('CHILD', 'N'): 'conditional', ('MAIN', 'EVENT_NO'): 'required'})
                gaps = [row for row in report['unresolved'] if row['code'] == 'task-continuation']
                self.assertEqual(len(gaps), 1)
                self.assertIn('paused entry', gaps[0]['message'])
                replay = runner.run_document(document)['results']
                self.assertEqual(replay['status'], 'completed', replay['error'])
                self.assertEqual(replay['text_output'].split(), ['21'])

    def test_linked_first_direct_checkpoint_parks_before_for_bound_reads(self):
        main = self.module('MAIN', "RUN_TASK('CHILD',0,TRUE,FALSE,0,s) DELAY 1")
        child = self.module('CHILD', 'FOR i=first TO 2 DO WRITE(i) ENDFOR', 'VAR i,first:INTEGER')
        self.create(main, child)
        self.assertEqual(discover_project_document(self.document)['inputs'], [])
        replay = runner.run_document(self.document)['results']
        self.assertEqual(replay['status'], 'paused', replay['error'])
        self.assertEqual(replay['programs']['CHILD']['values']['I'], MISSING)

    def test_linked_unproven_dispatch_entry_keeps_potential_body_reads(self):
        main = self.module('MAIN', "RUN_TASK('CHILD',0,TRUE,FALSE,0,s) DELAY 1")
        child = self.module('CHILD', 'start:: WRITE(first) GOTO done done::', 'VAR first:INTEGER')
        self.create(main, child)
        report = discover_project_document(self.document)
        self.assertEqual([(row['program'], row['path'], row['certainty']) for row in report['inputs']],
                         [('CHILD', 'FIRST', 'conditional')])
        self.assertIn('statement', {row['code'] for row in report['unresolved']})

    def test_linked_paused_entry_survives_structured_merge_and_wakes_on_a_known_target(self):
        main = self.module('MAIN', """
            IF choice THEN
              RUN_TASK('CHILD',0,TRUE,FALSE,0,s)
            ELSE
              RUN_TASK('CHILD',0,TRUE,FALSE,0,s)
            ENDIF
            DELAY 1 CONT_TASK('CHILD',s)
        """, 'VAR choice:BOOLEAN s:INTEGER')
        child = self.module('CHILD', 'WRITE(n,CR)')
        self.create(main, child)
        report = discover_project_document(self.document)
        self.assertEqual({(row['program'], row['path']): row['certainty'] for row in report['inputs']},
                         {('CHILD', 'N'): 'conditional', ('MAIN', 'CHOICE'): 'required'})
        self.assertIn('paused entry', next(row for row in report['unresolved']
                                          if row['code'] == 'task-continuation')['message'])

    def test_linked_dynamic_continuation_falls_back_to_potential_child_reads(self):
        main = self.module('MAIN', "RUN_TASK('CHILD',0,TRUE,FALSE,0,s) CONT_TASK(target,s)",
                           'VAR target:STRING[12] s:INTEGER')
        child = self.module('CHILD', 'WRITE(n,CR)')
        self.create(main, child)
        report = discover_project_document(self.document)
        self.assertEqual({(row['program'], row['path']): row['certainty'] for row in report['inputs']},
                         {('CHILD', 'N'): 'conditional', ('MAIN', 'TARGET'): 'conditional'})
        self.assertIn('task-target', {row['code'] for row in report['unresolved']})

    def test_linked_in_body_continuation_finds_inputs_after_the_explicit_pause(self):
        main = self.module('MAIN', "RUN_TASK('CHILD',0,FALSE,FALSE,0,s) WAIT FOR EVENT[1] DELAY 1 CONT_TASK('CHILD',s)")
        child = self.module('CHILD', 'SIGNAL EVENT[1] PAUSE WRITE(n,CR)')
        context = {'variables': [dict(program='CHILD', path='N', type='INTEGER', value=19)]}
        self.create(main, child, context=context)
        report = discover_project_document(self.document)
        self.assertEqual([(row['program'], row['path'], row['certainty']) for row in report['inputs']],
                         [('CHILD', 'N', 'conditional')])
        self.assertIn('explicit in-body pause', next(row for row in report['unresolved']
                                                     if row['code'] == 'task-continuation')['message'])
        replay = runner.run_document(self.document)['results']
        self.assertEqual(replay['status'], 'completed', replay['error'])
        self.assertEqual(replay['text_output'].split(), ['19'])

    def test_linked_pause_keeps_later_inputs_dormant_without_a_continuation(self):
        main = self.module('MAIN', "RUN_TASK('CHILD',0,FALSE,FALSE,0,s) WAIT FOR EVENT[1]")
        child = self.module('CHILD', 'saved=seed SIGNAL EVENT[1] PAUSE WRITE(later,CR)',
                            'VAR saved,seed,later:INTEGER')
        context = {'variables': [dict(program='CHILD', path='SEED', type='INTEGER', value=8)]}
        with patch('builtins.exec', side_effect=AssertionError('module ran during suspension discovery')):
            saved = self.create(main, child, context=context, discover=True)
        report = saved['inputs']['template']['discovery']
        self.assertEqual([(row['program'], row['path'], row['certainty']) for row in report['inputs']],
                         [('CHILD', 'SEED', 'conditional')])
        replay = runner.run_document(self.document)['results']
        self.assertEqual(replay['status'], 'paused', replay['error'])
        self.assertEqual(replay['programs']['CHILD']['values']['SAVED'], 8)
        self.assertEqual(replay['text_output'], '')

    def test_linked_two_pauses_preserve_private_scalar_facts_across_resumes(self):
        child = self.module('CHILD', """
            saved=seed flag=TRUE SIGNAL EVENT[1] PAUSE
            IF flag THEN result=saved+first ELSE result=unused ENDIF
            SIGNAL EVENT[2] PAUSE
            WRITE(result+second,CR)
        """, 'VAR saved,seed,result,first,second,unused:INTEGER flag:BOOLEAN')
        prefix = """target='CHILD' RUN_TASK(target,0,FALSE,FALSE,0,s)
                    WAIT FOR EVENT[1] DELAY 1 CONT_TASK(target,s)
                    WAIT FOR EVENT[2] DELAY 1 """
        for finish in (False, True):
            with self.subTest(finish=finish):
                continuation = 'RUN_TASK(target,99,TRUE,FALSE,0,s)' if finish else ''
                main = self.module('MAIN', prefix+continuation, 'VAR target:STRING[12] s:INTEGER')
                context = {'variables': [
                    dict(program='CHILD', path=name, type='INTEGER', value=value)
                    for name, value in [('SEED', 5), ('FIRST', 6), ('SECOND', 7)][:3 if finish else 2]]}
                document = self.folder / f'two-pauses-{finish}.run.json'
                saved = create_project_document([main, child], document, entry='MAIN', context=context, discover=True)
                report = saved['inputs']['template']['discovery']
                self.assertEqual({row['path'] for row in report['inputs']},
                                 {'FIRST', 'SECOND', 'SEED'} if finish else {'FIRST', 'SEED'})
                self.assertTrue(all(row['program']=='CHILD' and row['certainty']=='conditional' for row in report['inputs']))
                self.assertEqual(sum(row['code']=='task-continuation' for row in report['unresolved']), 2 if finish else 1)
                replay = runner.run_document(document)['results']
                self.assertEqual(replay['status'], 'completed' if finish else 'paused', replay['error'])
                self.assertEqual(replay['programs']['CHILD']['values']['RESULT'], 11)
                self.assertEqual(replay['text_output'].strip(), '18' if finish else '')

    def test_linked_paused_entry_can_lead_to_a_separate_in_body_pause(self):
        main = self.module('MAIN', """
            RUN_TASK('CHILD',0,TRUE,FALSE,0,s) DELAY 1 CONT_TASK('CHILD',s)
            WAIT FOR EVENT[1] DELAY 1
        """)
        child = self.module('CHILD','saved=seed SIGNAL EVENT[1] PAUSE WRITE(later)',
                            'VAR saved,seed,later:INTEGER')
        self.create(main, child)
        report = discover_project_document(self.document)
        self.assertEqual([row['path'] for row in report['inputs']], ['SEED'])
        self.assertIn('paused entry', next(row for row in report['unresolved']
                                          if row['code']=='task-continuation')['message'])

    def test_linked_dynamic_resume_recovers_reads_beyond_the_slice(self):
        main = self.module('MAIN', "RUN_TASK('CHILD',0,FALSE,FALSE,0,s) CONT_TASK(target,s)",
                           'VAR target:STRING[12] s:INTEGER')
        child = self.module('CHILD','PAUSE WRITE(n,CR)')
        self.create(main, child)
        report = discover_project_document(self.document)
        self.assertEqual({(row['program'], row['path']) for row in report['inputs']},
                         {('CHILD','N'), ('MAIN','TARGET')})
        self.assertIn('task-target', {row['code'] for row in report['unresolved']})

    def test_linked_conflicting_pause_cursors_keep_all_potential_reads(self):
        main = self.module('MAIN', """
            RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 1
            IF choice THEN CONT_TASK('CHILD',s) ENDIF
            DELAY 1 CONT_TASK('CHILD',s)
        """, 'VAR choice:BOOLEAN s:INTEGER')
        child = self.module('CHILD', 'PAUSE WRITE(middle) PAUSE WRITE(tail)',
                            'VAR middle,tail:INTEGER')
        self.create(main, child)
        report = discover_project_document(self.document)
        self.assertEqual({(row['program'], row['path']) for row in report['inputs']},
                         {('CHILD','MIDDLE'), ('CHILD','TAIL'), ('MAIN','CHOICE')})
        self.assertTrue(all('live suspended frame' in row['message'] for row in report['unresolved']
                            if row['code']=='task-continuation'))

    def test_linked_shared_storage_disables_private_pause_state_proof(self):
        main = self.module('MAIN', """
            RUN_TASK('CHILD',0,FALSE,FALSE,0,s) WAIT FOR EVENT[1] DELAY 1
            flag=FALSE CONT_TASK('CHILD',s)
        """, 'VAR flag FROM CHILD:BOOLEAN s:INTEGER')
        child = self.module('CHILD', """
            flag=TRUE SIGNAL EVENT[1] PAUSE
            IF flag THEN WRITE(one,CR) ELSE WRITE(two,CR) ENDIF
        """, 'VAR flag:BOOLEAN one,two:INTEGER')
        context = {'variables': [dict(program='CHILD', path='TWO', type='INTEGER', value=22)]}
        self.create(main, child, context=context)
        report = discover_project_document(self.document)
        self.assertTrue({'ONE','TWO'} <= {row['path'] for row in report['inputs']})
        self.assertIn('live suspended frame', next(row for row in report['unresolved']
                                                   if row['code']=='task-continuation')['message'])
        replay = runner.run_document(self.document)['results']
        self.assertEqual(replay['status'], 'completed', replay['error'])
        self.assertEqual(replay['text_output'].split(), ['22'])

    def test_linked_discovery_finds_handler_callbacks_and_eager_captures(self):
        main = self.module('MAIN', 'install(seed)', 'VAR seed:INTEGER', 'ROUTINE install(x:INTEGER) FROM LIB')
        lib = self.module('LIB', declarations='VAR rate,captured_value,never,fallback,shadowed,out:INTEGER ready:BOOLEAN',
                          routines="""ROUTINE install(value:INTEGER)
                          BEGIN
                            CONDITION[1]: WITH $SCAN_TIME=rate
                              WHEN FALSE DO out=EVAL(captured_value)+never
                              WHEN ready DO out=value WRITE(out,CR)
                              WHEN TRUE DO WRITE(fallback,CR)
                              WHEN TRUE DO WRITE(shadowed,CR)
                            ENDCONDITION
                            ENABLE CONDITION[1]
                            never=0
                          END install""")
        entries = [('LIB', 'RATE', 'INTEGER', 0), ('LIB', 'CAPTURED_VALUE', 'INTEGER', 5),
                   ('LIB', 'READY', 'BOOLEAN', True), ('MAIN', 'SEED', 'INTEGER', 42)]
        context = {'variables': [dict(program=owner, path=path, type=spec, value=value)
                                 for owner, path, spec, value in entries]}
        self.create(main, lib, context=context, discover=True)
        report = discover_project_document(self.document)
        self.assertEqual({(row['program'], row['path']): row['certainty'] for row in report['inputs']},
                         {('LIB', 'RATE'): 'required', ('LIB', 'CAPTURED_VALUE'): 'required',
                          ('LIB', 'READY'): 'conditional', ('LIB', 'FALLBACK'): 'conditional',
                          ('MAIN', 'SEED'): 'conditional'})
        reference = next(row for row in report['inputs'] if row['path'] == 'SEED')
        self.assertEqual(reference['locations'][0]['program'], 'LIB')
        self.assertEqual(reference['locations'][0]['routine'], 'INSTALL')
        self.assertTrue(all(row['code'] == 'condition-scan' for row in report['unresolved']))
        result = runner.run_document(self.document)['results']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['text_output'].split(), ['42'])

    def test_linked_discovery_keeps_async_writes_out_of_caller_flow(self):
        main = self.module('MAIN', """
            CONDITION[1]: WHEN TRUE DO from_handler=1 ENDCONDITION
            WRITE(from_handler)
            RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
            WRITE(from_child)
        """, 'VAR from_handler,from_child,s:INTEGER')
        child = self.module('CHILD', 'from_child=2', 'VAR from_child FROM MAIN:INTEGER')
        self.create(main, child)
        report = discover_project_document(self.document)
        self.assertEqual({row['path']: row['certainty'] for row in report['inputs']},
                         {'FROM_HANDLER': 'required', 'FROM_CHILD': 'conditional'})

    def test_linked_discovery_preserves_capture_order_and_accepts_legacy_plans(self):
        from karel2py.input_contract import attach, extract

        main = self.module('MAIN', """
            CONDITION[1]:
              WHEN EVAL(increment())>EVAL(n) DO WRITE(selected)
            ENDCONDITION
            ENABLE CONDITION[1]
        """, 'VAR n,selected:INTEGER',
                           'ROUTINE increment:INTEGER BEGIN n=7 RETURN n END increment')
        self.create(main)
        report = discover_project_document(self.document)
        self.assertEqual({row['path']: row['certainty'] for row in report['inputs']},
                         {'N': 'required', 'SELECTED': 'conditional'})
        source = main.read_text(encoding='utf-8')
        plan = extract(source)
        clauses = plan['body'][0]['body']
        self.assertEqual(len(clauses[0].pop('captures')), 2)
        lines = [line.partition(' = ')[0]+' = None' if line.startswith(
                 ('    input_analysis = ', '    input_analysis_sha256 = ')) else line for line in source.splitlines()]
        main.write_bytes(attach('\n'.join(lines)+'\n', plan).encode())
        legacy = self.folder / 'legacy.run.json'
        create_project_document([main], legacy, entry='MAIN')
        report = discover_project_document(legacy)
        self.assertIn('condition-capture', [row['code'] for row in report['unresolved']])
        self.assertFalse(report['complete'])

    def test_linked_handlers_distinguish_dormant_purged_and_replaced_definitions(self):
        main = self.module('MAIN', """
            ENABLE CONDITION[1]
            CONDITION[1]: WHEN TRUE DO WRITE(dormant) ENDCONDITION
            CONDITION[2]: WHEN TRUE DO WRITE(purged,EVAL(capture)) ENDCONDITION
            PURGE CONDITION[2]
            CONDITION[2]: WHEN TRUE DO WRITE(active,CR) ENDCONDITION
            DISABLE CONDITION[2]
            ENABLE CONDITION[2]
            result=0
        """, 'VAR dormant,purged,capture,active,result:INTEGER')
        context = {'variables': [dict(program='MAIN', path=name, type='INTEGER', value=value)
                                 for name, value in [('CAPTURE', 3), ('ACTIVE', 8)]]}
        saved = self.create(main, context=context, discover=True)
        report = saved['inputs']['template']['discovery']
        self.assertEqual({row['path']: row['certainty'] for row in report['inputs']},
                         {'CAPTURE': 'required', 'ACTIVE': 'conditional'})
        self.assertEqual([row['code'] for row in report['unresolved']], ['condition-scan'])
        result = runner.run_document(self.document)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        self.assertEqual(result['text_output'].split(), ['8'])

    def test_linked_handler_merge_keeps_same_number_alternatives(self):
        main = self.module('MAIN', """
            IF choose THEN
              CONDITION[3]: WHEN TRUE DO WRITE(left_value,CR) ENDCONDITION
            ELSE
              CONDITION[3]: WHEN TRUE DO WRITE(right_value,CR) ENDCONDITION
            ENDIF
            ENABLE CONDITION[3]
            done=TRUE
        """, 'VAR choose,done:BOOLEAN left_value,right_value:INTEGER')
        context = {'variables': [
            dict(program='MAIN', path='CHOOSE', type='BOOLEAN', value=False),
            dict(program='MAIN', path='RIGHT_VALUE', type='INTEGER', value=42)]}
        saved = self.create(main, context=context, discover=True)
        report = saved['inputs']['template']['discovery']
        self.assertEqual({row['path']: row['certainty'] for row in report['inputs']},
                         {'CHOOSE': 'required', 'LEFT_VALUE': 'conditional', 'RIGHT_VALUE': 'conditional'})
        replay = runner.run_document(self.document)['results']
        self.assertEqual(replay['status'], 'completed', replay['error'])
        self.assertEqual(replay['text_output'].split(), ['42'])

    def test_linked_handler_activation_uses_invocation_scope_and_definition_captures(self):
        main = self.module('MAIN', """
            CONDITION[1]: WHEN TRUE DO WRITE(other) ENDCONDITION
            install()
            arm()
        """, 'VAR other:INTEGER', 'ROUTINE install FROM LIB ROUTINE arm FROM LIB')
        lib = self.module('LIB', declarations='VAR initialized,seed,output_value,expired:INTEGER', routines="""
            ROUTINE install
            BEGIN
                CONDITION[1]: WHEN TRUE DO WRITE(expired,CR) ENDCONDITION
            END install
            ROUTINE configure
            BEGIN
                CONDITION[1]: WHEN TRUE DO WRITE(initialized+EVAL(seed),CR) ENDCONDITION
            END configure
            ROUTINE arm
            BEGIN
                ENABLE CONDITION[1]
                configure()
                initialized=10
                seed=100
                ENABLE CONDITION[1]
                output_value=0
            END arm
        """)
        context = {'variables': [dict(program='LIB', path='SEED', type='INTEGER', value=17)]}
        saved = self.create(main, lib, context=context, discover=True)
        report = saved['inputs']['template']['discovery']
        self.assertEqual([(row['program'], row['path'], row['certainty']) for row in report['inputs']],
                         [('LIB', 'SEED', 'required')])
        self.assertEqual(report['inputs'][0]['locations'][0]['routine'], 'CONFIGURE')
        replay = runner.run_document(self.document)['results']
        self.assertEqual(replay['status'], 'completed', replay['error'])
        self.assertEqual(replay['text_output'].split(), ['27'])

    def test_linked_handler_dynamic_or_nested_activation_keeps_conditional_reads(self):
        for control, expected in [
            ('ENABLE CONDITION[selection]', {'SELECTION': 'required', 'PAYLOAD': 'conditional'}),
            ('ENABLE CONDITION[2]', {'PAYLOAD': 'conditional'}),
        ]:
            with self.subTest(control=control):
                main = self.module('MAIN', """
                    CONDITION[1]: WHEN TRUE DO WRITE(payload) ENDCONDITION
                    CONDITION[2]: WHEN TRUE DO ENABLE CONDITION[1] ENDCONDITION
                    """ + control, 'VAR selection,payload:INTEGER')
                path = self.folder / ('dynamic.run.json' if 'selection' in control else 'nested.run.json')
                saved = create_project_document([main], path, entry='MAIN', discover=True)
                report = saved['inputs']['template']['discovery']
                self.assertEqual({row['path']: row['certainty'] for row in report['inputs']}, expected)
                self.assertIn('condition-scan', {row['code'] for row in report['unresolved']})

    def test_linked_motion_discovery_prepares_temporal_selectors_and_callback_inputs(self):
        main = self.module('MAIN', 'ATTACH work()', 'VAR payload:INTEGER', 'ROUTINE work FROM LIB')
        lib = self.module('LIB', declarations=(
            'VAR g,accel,offset,node_id,frozen,mark:INTEGER distance:REAL payload FROM MAIN:INTEGER'),
            routines="""ROUTINE work
            VAR boost:INTEGER
            BEGIN
                boost=5
                WITH $ACCEL_OVRD[g]=accel
                MOVE AWAY distance,
                    WHEN FALSE DO WRITE(EVAL(frozen))
                    WHEN TRUE DO WRITE(mark,CR)
                    WHEN TIME offset BEFORE NODE[node_id] DO WRITE(EVAL(frozen)+payload+boost,CR)
                    WHEN AT NODE[node_id] DO WRITE(EVAL(frozen),CR)
                ENDMOVE
            END work""")
        variables = [dict(program='LIB', path=name, type='INTEGER', value=value) for name, value in (
            ('G', 1), ('ACCEL', 100), ('OFFSET', 2), ('NODE_ID', 1), ('FROZEN', 11), ('MARK', 7))]
        variables.extend([dict(program='LIB', path='DISTANCE', type='REAL', value=3.0),
                          dict(program='MAIN', path='PAYLOAD', type='INTEGER', value=20)])
        context = {
            'motion': {'groups': {'1': 2}, 'responses': [
                {'operation': 'MOVE AWAY', 'completed': True, 'delay_ms': 7, 'node_times': {'0': 0, '1': 7}}]},
            'group_locks': {'groups': [1]},
            'variables': variables,
        }
        with patch('builtins.exec', side_effect=AssertionError('module executed during motion discovery')):
            saved = self.create(main, lib, discover=True, context=context)
        report = saved['inputs']['template']['discovery']
        self.assertEqual({(row['program'], row['path']): row['certainty'] for row in report['inputs']},
                         {**{('LIB', name): 'required' for name in ('G', 'ACCEL', 'DISTANCE', 'OFFSET',
                                                                    'NODE_ID', 'FROZEN')},
                          ('LIB', 'MARK'): 'conditional', ('MAIN', 'PAYLOAD'): 'conditional'})
        self.assertEqual({row['code'] for row in report['unresolved']}, {'motion-control', 'motion-progress'})
        self.assertEqual(saved['inputs']['template']['requirements'], [])
        payload = next(row for row in report['inputs'] if row['path'] == 'PAYLOAD')
        self.assertEqual(payload['locations'][0]['program'], 'LIB')
        self.assertEqual(payload['locations'][0]['routine'], 'WORK')

        result = runner.run_document(self.document)['results']
        self.assertEqual(result['status'], 'completed', result['error'])
        self.assertEqual(result['text_output'].split(), ['7', '36', '11'])

    def test_motion_discovery_keeps_capture_order_and_prunes_only_after_cancelling_until(self):
        main = self.module('MAIN', """
            ATTACH
            WITH $ACCEL_OVRD[group_arg()]=setting
            MOVE AWAY distance_arg(),
                WHEN FALSE DO WRITE(EVAL(frozen))
                WHEN TRUE DO WRITE(first,CR)
                UNTIL TRUE THEN result=last
                WHEN TRUE DO WRITE(unreached)
            ENDMOVE
            WRITE(result,CR)
        """, 'VAR setting,frozen,first,last,result,unreached:INTEGER', """
            ROUTINE group_arg:INTEGER BEGIN setting=100 RETURN 1 END group_arg
            ROUTINE distance_arg:REAL BEGIN frozen=20 RETURN 1.0 END distance_arg
        """)
        saved = self.create(main, discover=True)
        report = saved['inputs']['template']['discovery']
        self.assertEqual({row['path']: row['certainty'] for row in report['inputs']},
                         {'FIRST': 'conditional', 'LAST': 'conditional', 'RESULT': 'conditional'})
        services = {row['service'] for row in saved['inputs']['template']['requirements']
                    if row['code'] == 'service'}
        self.assertEqual(services, {'motion', 'group_locks'})

        _, revision = runner.prepare_project_document(self.document, context={
            'motion': {'groups': {'1': 2}, 'capture_only': True},
            'group_locks': {'groups': [1]},
            'variables': [dict(program='MAIN', path=name, type='INTEGER', value=value)
                          for name, value in [('FIRST', 8), ('LAST', 26)]],
        })
        replay = runner.run_document(self.document, expected=revision)['results']
        self.assertEqual(replay['status'], 'completed', replay['error'])
        self.assertEqual(replay['text_output'].split(), ['8', '26'])

    def test_motion_discovery_keeps_path_selectors_and_nowait_action_reads(self):
        main = self.module('MAIN', """
            MOVE ALONG route[first..last] NOWAIT,
                WHEN AT NODE[node_id] DO WRITE(extra)
            ENDMOVE
        """, 'VAR route:PATH first,last,node_id,extra:INTEGER')
        self.create(main)
        report = discover_project_document(self.document)
        self.assertEqual({row['path']: row['certainty'] for row in report['inputs']},
                         {'FIRST': 'required', 'LAST': 'required', 'NODE_ID': 'required', 'EXTRA': 'conditional'})
        self.assertEqual({row['code'] for row in report['unresolved']}, {'schema', 'motion-progress'})

    def test_discovery_reads_legacy_motion_actions_with_explicit_capture_gaps(self):
        from karel2py.input_contract import attach, extract

        main = self.module('MAIN', """
            MOVE AWAY 1, WHEN FALSE AND AT NODE[node_id] DO WRITE(EVAL(captured), unseen)
                WHEN TRUE DO WRITE(live)
            ENDMOVE
        """, 'VAR node_id,captured,unseen,live:INTEGER')
        source = main.read_text(encoding='utf-8')
        plan = extract(source)
        for clause in plan['body'][0]['body']:
            for key in ('trigger', 'captures', 'selectors'):
                del clause[key]
        lines = [line.partition(' = ')[0]+' = None' if line.startswith(
                 ('    input_analysis = ', '    input_analysis_sha256 = ')) else line for line in source.splitlines()]
        main.write_bytes(attach('\n'.join(lines)+'\n', plan).encode())
        self.create(main)
        report = discover_project_document(self.document)
        self.assertEqual([row['path'] for row in report['inputs']], ['LIVE'])
        self.assertEqual({row['code'] for row in report['unresolved']},
                         {'condition-capture', 'motion-selector', 'motion-progress'})

    def test_discovery_keeps_caller_root_schema_for_reference_reads_in_linked_branches(self):
        main = self.module('MAIN', 'update(values[2]) WRITE(values[2])', 'VAR values:ARRAY[2] OF INTEGER',
                           'ROUTINE update(x:INTEGER) FROM LIB')
        lib = self.module('LIB', declarations='VAR flag:BOOLEAN',
                          routines='ROUTINE update(cell:INTEGER) BEGIN IF flag THEN cell=cell+1 ENDIF END update')
        self.create(main, lib)
        report = discover_project_document(self.document)
        self.assertTrue(report['complete'])
        inputs = {(row['program'], row['path']): row for row in report['inputs']}
        self.assertEqual(set(inputs), {('MAIN', 'VALUES[2]'), ('LIB', 'FLAG')})
        value = inputs['MAIN', 'VALUES[2]']
        self.assertEqual(value['root_type'], ['ARRAY', 2, ['INTEGER']])
        self.assertEqual(value['selectors'], [('index', 2)])
        self.assertEqual({row['program'] for row in value['locations']}, {'MAIN', 'LIB'})

    def test_discovery_skips_unavailable_contract_and_refuses_a_changed_pin(self):
        main = self.module('MAIN', 'host(n) WRITE(s)', routines='ROUTINE host(x:INTEGER) FROM LIB')
        lib = self.module('LIB', routines='ROUTINE host(x:INTEGER) BEGIN x=1 END host')
        with lib.open('ab') as stream:
            stream.write(b'raise AssertionError("discovery executed a module")\n')
        self.create(main, lib)
        revision = self.document.read_bytes()
        report = discover_project_document(self.document)
        self.assertFalse(report['complete'])
        self.assertEqual([(row['code'], row['location']['program']) for row in report['unresolved']],
                         [('contract', 'LIB'), ('routine', 'MAIN')])
        self.assertEqual([(row['path'], row['certainty']) for row in report['inputs']],
                         [('N', 'conditional'), ('S', 'conditional')])
        self.assertEqual(self.document.read_bytes(), revision)
        with lib.open('ab') as stream:
            stream.write(b'# different module bytes\n')
        with self.assertRaisesRegex(ValueError, 'linked Python module changed'):
            discover_project_document(self.document)
        self.assertEqual(self.document.read_bytes(), revision)

    def test_discovery_distinguishes_same_named_routines_in_different_modules(self):
        main = self.module('MAIN', 'n=step()', routines=(
            'ROUTINE relay:INTEGER FROM LIB '
            'ROUTINE step:INTEGER BEGIN RETURN relay() END step'))
        lib = self.module('LIB', declarations='VAR offset:INTEGER', routines=(
            'ROUTINE step:INTEGER BEGIN RETURN offset END step '
            'ROUTINE relay:INTEGER BEGIN RETURN step() END relay'))
        self.create(main, lib)
        report = discover_project_document(self.document)
        self.assertTrue(report['complete'])
        self.assertEqual([(row['program'], row['path']) for row in report['inputs']], [('LIB', 'OFFSET')])
        self.assertEqual(report['inputs'][0]['locations'][0]['routine'], 'STEP')

    def test_incompatible_linked_interface_stays_unresolved(self):
        main = self.module('MAIN', 'host(n)', routines='ROUTINE host(x:INTEGER) FROM LIB')
        lib = self.module('LIB', routines='ROUTINE host(x:REAL) BEGIN WRITE(x) END host')
        self.create(main, lib)
        report = discover_project_document(self.document)
        self.assertEqual([row['code'] for row in report['unresolved']], ['routine'])
        self.assertEqual([(row['program'], row['path'], row['certainty']) for row in report['inputs']],
                         [('MAIN', 'N', 'conditional')])

    def test_reviewed_modules_keep_the_selected_order_and_refuse_changed_bytes(self):
        main, lib = self.module('MAIN'), self.module('LIB')
        with lib.open('ab') as stream:
            stream.write(b'raise AssertionError("module executed during review")\n')
        reviewed = inspect_project_modules([main, lib])
        self.assertEqual([(pin.program, pin.path) for pin in reviewed],
                         [('MAIN', main.resolve()), ('LIB', lib.resolve())])
        self.assertEqual(reviewed[1].sha256, sha256(lib.read_bytes()).hexdigest())
        with lib.open('ab') as stream:
            stream.write(b'# changed while choosing entry\n')
        with self.assertRaisesRegex(ValueError, 'changed after review'):
            self.create(main, lib, expected_modules=reviewed)
        self.assertFalse(self.document.exists())

        reordered = inspect_project_modules([lib, main])
        saved = self.create(lib, main, expected_modules=reordered)
        self.assertEqual(saved['target']['program'], 'MAIN')
        self.assertEqual([row['program'] for row in saved['target']['modules']], ['LIB', 'MAIN'])
        self.assertIsNone(saved['results'])

    def test_all_pins_must_match_before_any_module_executes(self):
        main, lib = self.module('MAIN'), self.module('LIB')
        self.create(main, lib)
        first = runner.run_document(self.document)
        before = self.document.read_bytes()
        with lib.open('ab') as stream:
            stream.write(b'# changed\n')
        with patch('builtins.exec', side_effect=AssertionError('target executed after a stale pin')):
            with self.assertRaisesRegex(ValueError, 'linked Python module changed'):
                runner.run_document(self.document)
        self.assertEqual(self.document.read_bytes(), before)
        self.assertEqual(first['results']['status'], 'completed')

    def test_editor_preserves_pins_results_and_revision_on_context_changes(self):
        main = self.module('MAIN', 'WRITE(n,CR)', declarations='VAR n FROM LIB:INTEGER')
        lib = self.module('LIB')
        context = {'variables': [{'program': 'LIB', 'path': 'N', 'type': 'INTEGER', 'value': 3}]}
        self.create(lib, main, context=context)
        previous = runner.run_document(self.document)
        opened, revision = runner.read_document(self.document)
        self.assertEqual(opened, previous)
        context['variables'][0]['value'] = 5
        with patch('builtins.exec', side_effect=AssertionError('target executed while editing inputs')):
            saved, updated = runner.save_context(self.document, json.dumps(context), expected=revision)
        self.assertEqual(updated, self.document.read_bytes())
        self.assertEqual(saved['target'], previous['target'])
        self.assertEqual(saved['limits'], previous['limits'])
        self.assertEqual(saved['results'], previous['results'])
        self.assertEqual(saved['inputs']['context'], context)
        with self.assertRaisesRegex(ValueError, 'changed on disk'):
            runner.save_context(self.document, '{}', expected=revision)
        with self.assertRaisesRegex(ValueError, 'Invalid input context'):
            runner.save_context(self.document, '{"numeric":{"count":1,"values":{"1":true}}}', expected=updated)
        self.assertEqual(self.document.read_bytes(), updated)
        replayed = runner.run_document(self.document, expected=updated)
        self.assertEqual(replayed['results']['programs']['LIB']['values']['N'], 5)
        self.assertEqual(replayed['results']['text_output'].strip(), '5')

    def test_editor_opens_saved_results_with_missing_modules_and_blocks_unsafe_writes(self):
        main, lib = self.module('MAIN'), self.module('LIB')
        self.create(main, lib)
        finished = runner.run_document(self.document)
        with lib.open('ab') as stream:
            stream.write(b'# changed\n')
        _, revision = runner.read_document(self.document)
        with self.assertRaisesRegex(ValueError, 'linked Python module changed'):
            runner.save_context(self.document, '{}', expected=revision)
        self.assertEqual(self.document.read_bytes(), revision)
        lib.unlink()
        self.assertEqual(runner.read_document(self.document), (finished, revision))
        finished['results']['status'] = 'running'
        self.document.write_bytes(json.dumps(finished).encode())
        opened, revision = runner.read_document(self.document)
        self.assertEqual(opened['results']['status'], 'running')
        with self.assertRaisesRegex(ValueError, 'running or interrupted'):
            runner.save_context(self.document, '{}', expected=revision)
        self.assertEqual(self.document.read_bytes(), revision)

    def test_prepare_rejects_synchronous_duplicate_and_missing_entry(self):
        main, lib = self.module('MAIN', cooperative=False), self.module('LIB')
        with self.assertRaisesRegex(ValueError, 'cooperative generated modules'):
            self.create(main, lib)
        with self.assertRaisesRegex(ValueError, 'Duplicate linked program'):
            self.create(lib, lib)
        with self.assertRaisesRegex(ValueError, 'entry must be one'):
            self.create(lib)
        self.assertFalse(self.document.exists())

    def test_invalid_edited_context_fails_before_the_running_marker(self):
        main, lib = self.module('MAIN'), self.module('LIB')
        document = self.create(main, lib)
        document['inputs']['context'] = {'numeric': {'count': 1, 'values': {'1': True}}}
        before = json.dumps(document).encode()
        self.document.write_bytes(before)
        with patch('builtins.exec', side_effect=AssertionError('target executed with invalid context')):
            with self.assertRaisesRegex(ValueError, 'Invalid input context'):
                runner.run_document(self.document)
        self.assertEqual(self.document.read_bytes(), before)

    def test_child_task_runs_and_shares_the_captured_output(self):
        main = self.module('MAIN', "RUN_TASK('CHILD',0,FALSE,FALSE,0,s) WAIT FOR EVENT[1] n=7 WRITE(n,CR)")
        child = self.module('CHILD', 'n=9 WRITE(n,CR) SIGNAL EVENT[1]')
        self.create(main, child)
        result = runner.run_document(self.document)['results']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['programs']['MAIN']['values']['N'], 7)
        self.assertEqual(result['programs']['CHILD']['values']['N'], 9)
        self.assertEqual(result['text_output'].split(), ['9', '7'])

    def test_no_overwrite_and_revision_conflict_protect_saved_files(self):
        main, lib = self.module('MAIN'), self.module('LIB')
        with self.assertRaisesRegex(ValueError, 'protected'):
            create_project_document([main, lib], lib, entry='MAIN')
        self.create(main, lib)
        original = self.document.read_bytes()
        with self.assertRaises(FileExistsError):
            self.create(main, lib)
        edited = original + b'\n'
        self.document.write_bytes(edited)
        with self.assertRaisesRegex(ValueError, 'changed on disk'):
            runner.run_document(self.document, expected=original)
        self.assertEqual(self.document.read_bytes(), edited)

    def test_mismatched_routine_and_type_are_checked_before_entry_body(self):
        for declaration, interface, lib_decl, lib_body in (
            ('VAR n:INTEGER', 'ROUTINE f(x:INTEGER) FROM LIB', 'VAR n:INTEGER',
             'ROUTINE f(x:REAL) BEGIN END f'),
            ('TYPE item_t FROM LIB=INTEGER VAR n:item_t', '', 'TYPE item_t=REAL VAR n:item_t', ''),
        ):
            with self.subTest(declaration=declaration):
                main = self.module('MAIN', 'n=42', declaration, interface)
                lib = self.module('LIB', declarations=lib_decl, routines=lib_body)
                self.create(main, lib)
                result = runner.run_document(self.document)['results']
                self.assertEqual(result['status'], 'failed')
                self.assertIn('mismatch', result['error']['message'])
                if 'MAIN' in result['programs']:
                    self.assertEqual(result['programs']['MAIN']['values']['N'], MISSING)
                self.document.unlink()

    def test_pause_retains_disposition_and_cleans_up_suspended_counter(self):
        main = self.module('MAIN', 'n=0 FOR i=1 TO 3 DO n=n+1 PAUSE ENDFOR', 'VAR i,n:INTEGER')
        self.create(main)
        result = runner.run_document(self.document)['results']
        self.assertEqual(result['status'], 'paused')
        self.assertEqual(result['programs']['MAIN'], {'state': 'paused', 'values': {'I': MISSING, 'N': 1}})

    def test_periodic_wait_honors_cycle_budget_and_preserves_prior_writes(self):
        main = self.module('MAIN', 'n=9 WAIT FOR FALSE n=42')
        self.create(main, max_cycles=8)
        result = runner.run_document(self.document)['results']
        self.assertEqual(result['status'], 'failed')
        self.assertIn('cycle budget', result['error']['message'])
        self.assertIn(result['programs']['MAIN']['state'], ('running', 'waiting'))
        self.assertEqual(result['programs']['MAIN']['values']['N'], 9)

    def test_cancellation_after_output_retains_completed_effects(self):
        main = self.module('MAIN', 'n=17 WRITE(n,CR) DELAY 1000 n=42')
        self.create(main)
        cancel = Event()
        original = runner._RunOutput.write

        def write(output, text):
            original(output, text)
            cancel.set()

        with patch.object(runner._RunOutput, 'write', write):
            result = runner.run_document(self.document, cancel_event=cancel)['results']
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['programs']['MAIN']['values']['N'], 17)
        self.assertIn('17', result['text_output'])

    def test_step_cycle_and_output_limits_are_saved_as_failed_results(self):
        for body, limits, message in (
            ('n=7 WHILE TRUE DO n=n+1 ENDWHILE', {'max_steps': 25}, 'step budget'),
            ('n=7 DELAY 1000 n=42', {'max_cycles': 5}, 'cycle budget'),
            ("n=7 WRITE('too many')", {'max_output_chars': 3}, 'output limit'),
        ):
            with self.subTest(limits=limits):
                main = self.module('MAIN', body)
                self.create(main, **limits)
                result = runner.run_document(self.document)['results']
                self.document.unlink()
                self.assertEqual(result['status'], 'failed')
                self.assertIn(message, result['error']['message'])
                self.assertGreaterEqual(result['programs']['MAIN']['values']['N'], 7)

    def test_cli_exports_checked_modules_and_runs_existing_linked_example(self):
        example = ROOT / 'examples' / 'for_start_capture_linked'
        exported = self.cli('karel2py.project', example, '--python-out', self.folder)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        modules = json.loads(exported.stdout)['modules']
        created = self.cli('karel2py.runner', 'create-project', self.document, modules['MAIN'], modules['LIB'], '--entry', 'MAIN')
        self.assertEqual(created.returncode, 0, created.stderr)
        before_discovery = self.document.read_bytes()
        report_path = self.folder / 'project.inputs.report.json'
        discovery = self.cli('karel2py.runner', 'discover-project', self.document, '--output', report_path)
        self.assertEqual(discovery.returncode, 0, discovery.stderr)
        self.assertEqual(json.loads(report_path.read_bytes())['target']['program'], 'MAIN')
        blocked_report = self.cli('karel2py.runner', 'discover-project', self.document, '--output', modules['LIB'])
        self.assertEqual(blocked_report.returncode, 2, blocked_report.stdout)
        self.assertIn('protected', blocked_report.stderr)
        self.assertEqual(self.document.read_bytes(), before_discovery)
        replay = self.cli('karel2py.runner', 'run', self.document)
        self.assertEqual(replay.returncode, 0, replay.stderr + replay.stdout)
        result = json.loads(self.document.read_bytes())['results']
        self.assertEqual(result['programs'], json.loads((example / 'expected.json').read_bytes()))
        before = Path(modules['MAIN']).read_bytes()
        blocked = self.cli('karel2py.project', example, '--python-out', self.folder)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(Path(modules['MAIN']).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
