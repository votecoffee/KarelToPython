"""Saved-run editing, revision checks, and cooperative cancellation."""
import json
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest

from karel2py import runner, translate


class SavedRunEditorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.target = self.folder / 'converted.py'
        self.path = self.folder / 'session.run.json'

    def create(self, body):
        result = translate('PROGRAM DEMO VAR n,x,i:INTEGER BEGIN ' + body + ' END DEMO')
        self.target.write_bytes(result.python_source.encode('utf-8'))
        self.saved = runner.create_document(self.target, self.path, discover=True)
        self.revision = self.path.read_bytes()

    def test_edits_refresh_discovery_and_first_run_results_share_the_same_document(self):
        self.create("n=x+1 WRITE(n,CR)")
        self.assertEqual(self.saved['inputs']['template']['bindings'][0]['status'], 'missing')
        context = self.saved['inputs']['context']
        context['variables'][0]['value'] = 41
        edited, revision = runner.save_context(self.path, json.dumps(context), expected=self.revision)
        self.assertEqual(edited['inputs']['template']['bindings'][0]['status'], 'supplied')
        running = runner.run_document(self.path, expected=revision)
        self.assertEqual(running['inputs']['context'], context)
        self.assertEqual(running['results']['variables']['N'], 42)
        self.assertIn('42', running['results']['text_output'])
        self.assertEqual(runner.read_document(self.path)[0], running)

    def test_invalid_context_or_external_document_edit_preserves_saved_bytes(self):
        self.create('n=x')
        context = self.saved['inputs']['context']
        context['variables'][0]['value'] = 'not an integer'
        with self.assertRaises(ValueError):
            runner.save_context(self.path, json.dumps(context), expected=self.revision)
        self.assertEqual(self.path.read_bytes(), self.revision)
        external = self.revision + b'\n'
        self.path.write_bytes(external)
        for action in (lambda: runner.save_context(self.path, '{}', expected=self.revision),
                       lambda: runner.run_document(self.path, expected=self.revision),
                       lambda: runner.refresh_document(self.path, self.folder / 'new.json', expected=self.revision)):
            with self.assertRaisesRegex(runner.RunDocumentError, 'changed on disk'):
                action()
        self.assertEqual(self.path.read_bytes(), external)
        self.assertFalse((self.folder / 'new.json').exists())

    def test_cancel_interrupts_delay_and_saves_completed_writes_and_counter_cleanup(self):
        self.create('n=0 FOR i=1 TO 3 DO n=n+1 DELAY 30000 ENDFOR')
        waiting = Event()

        class CancelEvent(Event):
            def wait(self, timeout=None):
                waiting.set()
                return super().wait(min(timeout, 5))

        cancel = CancelEvent()
        outcomes = []

        def execute():
            try:
                outcomes.append(runner.run_document(self.path, expected=self.revision, cancel_event=cancel))
            except BaseException as error:
                outcomes.append(error)

        thread = Thread(target=execute)
        thread.start()
        try:
            self.assertTrue(waiting.wait(5), outcomes)
        finally:
            cancel.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        if isinstance(outcomes[0], BaseException):
            raise outcomes[0]
        document = outcomes[0]
        self.assertEqual(document['inputs'], self.saved['inputs'])
        self.assertEqual(document['results']['status'], 'cancelled')
        self.assertEqual(document['results']['variables']['N'], 1)
        self.assertEqual(document['results']['variables']['I'], {'uninitialized': True})
        self.assertEqual(runner.read_document(self.path)[0], document)

    def test_cancel_before_execution_retains_inputs_with_terminal_status(self):
        self.create('n=x')
        cancel = Event()
        cancel.set()
        document = runner.run_document(self.path, cancel_event=cancel)
        self.assertEqual(document['results']['status'], 'cancelled')
        self.assertIsNone(document['results']['variables'])
        self.assertEqual(document['inputs'], self.saved['inputs'])


if __name__ == '__main__':
    unittest.main()
