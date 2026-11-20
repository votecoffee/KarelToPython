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
