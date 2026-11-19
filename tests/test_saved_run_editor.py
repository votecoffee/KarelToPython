"""Saved-run editing, revision checks, and cooperative cancellation."""
import json
from copy import deepcopy
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest

from karel2py import runner, translate
from karel2py.structured_inputs import structured_slot


class SavedRunEditorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.target = self.folder / 'converted.py'
        self.path = self.folder / 'session.run.json'

    def create(self, body, *, declarations='VAR n,x,i:INTEGER', context=None):
        result = translate(f'PROGRAM DEMO {declarations} BEGIN {body} END DEMO')
        self.target.write_bytes(result.python_source.encode('utf-8'))
        self.saved = runner.create_document(self.target, self.path, discover=True, context=context)
        self.revision = self.path.read_bytes()

    def set_input(self, source_kind, path, value_kind, text, *, owner='DEMO'):
        document, self.revision = runner.save_input_value(
            self.path, (source_kind, owner, path), value_kind, text, expected=self.revision)
        return document

    def draft(self, key):
        document, _ = runner.read_document(self.path)
        template = document['inputs']['template']
        candidate, binding = next((candidate, binding) for candidate, binding in
                                  zip(template['discovery']['inputs'], template['bindings'])
                                  if (candidate['kind'], candidate['program'], candidate['path']) == key)
        return structured_slot(document['inputs']['context'], candidate, binding).draft(candidate['path'])

    def save_structure(self, key, payload):
        document, self.revision = runner.save_input_structure(self.path, key, payload, expected=self.revision)
        return document

    def test_structured_record_draft_keeps_other_roots_and_missing_leaves(self):
        missing = {'uninitialized': True}
        self.create('target=source n=source.count', declarations='''
            TYPE item_t=STRUCTURE count:INTEGER ready:BOOLEAN label:STRING[7] ENDSTRUCTURE
            VAR source,target:item_t n:INTEGER''',
            context={'variables': [{'program': 'OTHER', 'path': 'KEEP', 'type': 'INTEGER', 'value': 17}]})
        key = ('variable', 'DEMO', 'SOURCE')
        draft = self.draft(key)
        fields = dict(draft.fields)
        fields['SOURCE.COUNT'].set_text('INTEGER', '9')
        fields['SOURCE.READY'].set_text('BOOLEAN', 'false')
        self.assertEqual(self.path.read_bytes(), self.revision)
        result = self.save_structure(key, draft.checked_payload())
        values = result['inputs']['context']['variables']
        self.assertEqual(values[0], {'program': 'OTHER', 'path': 'KEEP', 'type': 'INTEGER', 'value': 17})
        self.assertEqual(values[1]['value'], {'COUNT': 9, 'READY': False, 'LABEL': missing})
        observed = runner.run_document(self.path)['results']['variables']
        self.assertEqual(observed['TARGET'], values[1]['value'])
        self.assertEqual(observed['N'], 9)

    def test_structured_array_row_edit_retains_sibling_row(self):
        missing = {'uninitialized': True}
        context = {'variables': [{'program': 'DEMO', 'path': 'G', 'type': ['ARRAY', [2, 2], ['INTEGER']],
                                  'value': [[1, 2], [3, missing]]}]}
        self.create('row=g[2]', declarations='VAR g:ARRAY[2,2]OF INTEGER row:ARRAY[2]OF INTEGER', context=context)
        key = ('variable', 'DEMO', 'G[2]')
        draft = self.draft(key)
        dict(draft.fields)['G[2][2]'].set_text('INTEGER', '13')
        edited = self.save_structure(key, draft.checked_payload())
        self.assertEqual(edited['inputs']['context']['variables'][0]['value'], [[1, 2], [3, 13]])
        self.assertEqual(runner.run_document(self.path)['results']['variables']['ROW'], [3, 13])

    def test_structured_new_position_requires_complete_cartesian_data(self):
        self.create('p=GET_POS_REG(2,s,3)', declarations='VAR p:XYZWPREXT s:INTEGER',
                    context={'positions': {'count': 2, 'groups': [3], 'comments': {'2': 'keep'}}})
        key = ('position_register', None, '2[group=3]')
        draft = self.draft(key)
        self.assertEqual(draft.spec, ('XYZWPREXT',))
        self.assertTrue(all(slot.value is None for _, slot in draft.fields))
        with self.assertRaisesRegex(ValueError, 'complete data'):
            draft.checked_payload()
        with self.assertRaises(ValueError):
            self.save_structure(key, draft.payload)
        self.assertEqual(self.path.read_bytes(), self.revision)
        for path, slot in draft.fields:
            kind = slot.options[0]
            text = 'true' if kind == 'BOOLEAN' else '0'
            slot.set_text(kind, '12.5' if path.endswith('.X') else text)
        result = self.save_structure(key, draft.checked_payload())
        self.assertEqual(result['inputs']['context']['positions']['comments'], {'2': 'keep'})
        self.assertEqual(result['inputs']['context']['positions']['values']['3:2']['type'], ['XYZWPREXT'])
        self.assertEqual(result['inputs']['template']['bindings'][0]['status'], 'supplied')
        self.assertEqual(runner.run_document(self.path)['results']['variables']['P']['X'], 12.5)

    def test_structured_existing_position_uses_its_stored_group_key_and_joint_width(self):
        self.create('p=GET_JPOS_REG(2,s,3)', declarations='VAR p:JOINTPOS s:INTEGER',
                    context={'positions': {'count': 2, 'groups': [3], 'values': {
                        '3:02': {'type': 'JOINTPOS2', 'value': [1.0, 2.0]}}}})
        key = ('position_register', None, '2[group=3]')
        draft = self.draft(key)
        self.assertEqual(draft.spec, ('JOINTPOS', 2))
        dict(draft.fields)['2[group=3][2]'].set_text('REAL', '7.25')
        edited = self.save_structure(key, draft.checked_payload())
        self.assertEqual(edited['inputs']['context']['positions']['values'], {
            '3:02': {'type': 'JOINTPOS2', 'value': {'axes': [1.0, 7.25]}}})
        self.assertEqual(runner.run_document(self.path)['results']['variables']['P']['axes'], [1.0, 7.25] + [0.0] * 7)

    def test_structured_rejects_bad_record_domain_and_stale_revision(self):
        self.create('target=source', declarations='VAR target,source:CONFIG')
        key = ('variable', 'DEMO', 'SOURCE')
        draft = self.draft(key)
        invalid = deepcopy(draft.payload)
        invalid['CFG_TURN_NO1'] = 8
        with self.assertRaisesRegex(ValueError, 'limited to -8..7'):
            self.save_structure(key, invalid)
        self.assertEqual(self.path.read_bytes(), self.revision)
        disk_edit = self.revision + b'\n'
        self.path.write_bytes(disk_edit)
        with self.assertRaisesRegex(ValueError, 'changed on disk'):
            self.save_structure(key, draft.payload)
        self.assertEqual(self.path.read_bytes(), disk_edit)

    def test_selected_scalars_preserve_saved_record_array_and_joint_representations(self):
        missing = {'uninitialized': True}
        record = ['STRUCTURE', 'ITEM_T', [['FLAG', ['BOOLEAN']], ['KEEP', ['INTEGER']]]]
        context = {'variables': [
            {'program': 'demo', 'path': 'row', 'type': record, 'value': {'flag': missing, 'keep': 17}},
            {'program': 'demo', 'path': 'grid', 'type': ['ARRAY', [2, 2], ['INTEGER']], 'value': [1, 2, missing, 4]},
            {'program': 'demo', 'path': 'j', 'type': ['JOINTPOS', 2], 'value': {'joints': [3.0, missing]}},
        ]}
        self.create('IF row.flag THEN n=grid[2,1]+TRUNC(j[2]) ELSE n=0 ENDIF',
                    declarations='TYPE item_t=STRUCTURE flag:BOOLEAN keep:INTEGER ENDSTRUCTURE VAR row:item_t grid:ARRAY[2,2]OF INTEGER j:JOINTPOS2 n:INTEGER',
                    context=context)
        self.set_input('variable', 'ROW.FLAG', 'BOOLEAN', 'true')
        self.set_input('variable', 'GRID[2][1]', 'INTEGER', '8')
        edited = self.set_input('variable', 'J[2]', 'REAL', '2.75')
        self.assertEqual([row['value'] for row in edited['inputs']['context']['variables']],
                         [{'flag': True, 'keep': 17}, [1, 2, 8, 4], {'joints': [3.0, 2.75]}])
        self.assertTrue(all(row['status'] == 'supplied' for row in edited['inputs']['template']['bindings']))
        self.assertEqual(runner.run_document(self.path)['results']['variables']['N'], 10)

    def test_scalar_bank_edits_preserve_configuration_and_choose_numeric_type(self):
        context = {'numeric': {'count': 2, 'values': {'2': 7}, 'comments': {'2': 'keep'}},
                   'strings': {'count': 1, 'capacity': 6}, 'ports': {'counts': {'DIN': 1}}}
        self.create('GET_REG(1,b,n,r,s) GET_STR_REG(1,text,s) b=DIN[1]',
                    declarations='VAR b:BOOLEAN n,s:INTEGER r:REAL text:STRING[8]', context=context)
        self.set_input('numeric_register', '1', 'REAL', '4', owner=None)
        self.set_input('string_register', '1', 'STRING', '  hi ', owner=None)
        edited = self.set_input('port', 'DIN[1]', 'BOOLEAN', 'false', owner=None)
        config = edited['inputs']['context']
        self.assertIs(type(config['numeric']['values']['1']), float)
        self.assertEqual(config['numeric']['values'], {'1': 4.0, '2': 7})
        self.assertEqual(config['numeric']['comments'], {'2': 'keep'})
        self.assertEqual(config['strings']['values'], {'1': '  hi '})
        self.assertEqual(config['ports']['values'], {'DIN': {'1': False}})
        self.assertEqual(runner.run_document(self.path)['results']['variables']['R'], 4.0)

    def test_legacy_flat_joint_array_with_singleton_dimension(self):
        missing = {'uninitialized': True}
        context = {'variables': [{'program': 'DEMO', 'path': 'J', 'type': ['ARRAY', [2, 1], ['JOINTPOS', 1]],
                                  'value': [[3.0], [missing]]}]}
        self.create('r=j[2,1,1]', declarations='VAR j:ARRAY[2,1]OF JOINTPOS1 r:REAL', context=context)
        edited = self.set_input('variable', 'J[2][1][1]', 'REAL', '2.75')
        self.assertEqual(edited['inputs']['context']['variables'][0]['value'], [[3.0], [2.75]])
        self.assertEqual(runner.run_document(self.path)['results']['variables']['R'], 2.75)

    def test_config_turn_domain_applies_even_when_other_fields_are_missing(self):
        self.create('n=cfg.cfg_turn_no1', declarations='VAR cfg:CONFIG n:INTEGER')
        previous = self.revision
        with self.assertRaisesRegex(ValueError, 'limited to -8..7'):
            self.set_input('variable', 'CFG.CFG_TURN_NO1', 'INTEGER', '8')
        self.assertEqual(self.path.read_bytes(), previous)
        edited = self.set_input('variable', 'CFG.CFG_TURN_NO1', 'INTEGER', '-8')
        self.assertEqual(edited['inputs']['context']['variables'][0]['value']['CFG_TURN_NO1'], -8)

    def test_selected_value_rejects_bad_type_bounds_and_stale_identity(self):
        self.create('n=x+small+STR_LEN(text)', declarations='VAR n:INTEGER x:BYTE small:SHORT text:STRING[3]')
        for path, kind, text in [('X', 'BYTE', '256'), ('X', 'INTEGER', '7'), ('SMALL', 'SHORT', '32767'),
                                 ('TEXT', 'STRING', 'wide'), ('TEXT', 'STRING', '\u00e9')]:
            with self.subTest(path=path, text=text), self.assertRaises(ValueError):
                self.set_input('variable', path, kind, text)
            self.assertEqual(self.path.read_bytes(), self.revision)
        with self.assertRaisesRegex(ValueError, 'no longer in the discovery report'):
            self.set_input('variable', 'N', 'INTEGER', '13')
        with self.target.open('ab') as stream:
            stream.write(b'\n')
        with self.assertRaisesRegex(ValueError, 'Python target changed'):
            self.set_input('variable', 'X', 'BYTE', '13')
        self.assertEqual(self.path.read_bytes(), self.revision)

    def test_selected_edit_rebuilds_tampered_pointer_and_rejects_unconfigured_register(self):
        self.create('n=x GET_REG(1,flag,n,r,s)', declarations='VAR n,x,s:INTEGER flag:BOOLEAN r:REAL')
        previous = self.revision
        with self.assertRaisesRegex(ValueError, 'scalar binding'):
            self.set_input('numeric_register', '1', 'INTEGER', '4', owner=None)
        self.assertEqual(self.path.read_bytes(), previous)
        template = self.saved['inputs']['template']
        variable = next(binding for binding in template['bindings'] if binding['kind'] == 'variable')
        variable['context_pointer'] = '/results'
        self.revision = json.dumps(self.saved).encode('utf-8')
        self.path.write_bytes(self.revision)
        result = self.set_input('variable', 'X', 'INTEGER', '13')
        self.assertEqual(result['inputs']['context']['variables'][0]['value'], 13)
        self.assertIsNone(result['results'])

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
                       lambda: self.set_input('variable', 'X', 'INTEGER', '4'),
                       lambda: runner.run_document(self.path, expected=self.revision),
                       lambda: runner.refresh_document(self.path, self.folder / 'new.json', expected=self.revision)):
            with self.assertRaisesRegex(runner.RunDocumentError, 'changed on disk'):
                action()
        self.assertEqual(self.path.read_bytes(), external)
        self.assertFalse((self.folder / 'new.json').exists())

    def test_selected_edit_keeps_refresh_history_and_previous_result(self):
        self.create('n=x')
        self.set_input('variable', 'X', 'INTEGER', '4')
        refreshed = self.folder / 'refreshed.run.json'
        document = runner.refresh_document(self.path, refreshed)
        self.path = refreshed
        completed = runner.run_document(self.path)
        self.revision = self.path.read_bytes()
        updated = self.set_input('variable', 'X', 'INTEGER', '5')
        self.assertEqual(updated['inputs']['template']['refresh'], document['inputs']['template']['refresh'])
        self.assertEqual(updated['results'], completed['results'])
        self.assertEqual(updated['inputs']['context']['variables'][0]['value'], 5)

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
