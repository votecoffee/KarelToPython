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
from karel2py.project_run import create_project_document


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
