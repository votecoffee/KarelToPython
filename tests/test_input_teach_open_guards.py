"""Read-before-write regressions for guarded TP open outcomes."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner, translate
from karel2py.project_run import create_project_document
from tests.test_input_teach_handle_choices import two_banks
from tests.test_input_teach_tolerance import prepared_run
from tests.test_input_template import prepare


class TeachOpenGuardTests(unittest.TestCase):
    def assert_inputs(self, prepared, expected, unresolved=()):
        discovery = prepared['template']['discovery']
        rows = [(row['kind'],row['program'],row['path'],row['certainty']) for row in discovery['inputs']]
        self.assertCountEqual(rows, expected)
        self.assertEqual([row['code'] for row in discovery['unresolved']], list(unresolved), discovery['unresolved'])

    def test_if_success_does_not_discover_uninitialized_handle_from_failure(self):
        source = """PROGRAM T
VAR name_to_open:STRING[36]
    h,s,both,failure_input:INTEGER
BEGIN
  OPEN_TPE(name_to_open,TPE_RDACC,TPE_NOREJ,h,s)
  IF s=0 THEN
    WRITE(both,':',GET_POS_TPE(h,1,s).x)
  ELSE
    WRITE(both,':',failure_input)
  ENDIF
END T
"""
        context = two_banks()
        context['variables'] = [
            dict(program='T',path='NAME_TO_OPEN',type=['STRING',36],value='OTHER'),
            dict(program='T',path='BOTH',type=['INTEGER'],value=21),
            dict(program='T',path='FAILURE_INPUT',type=['INTEGER'],value=87),
        ]
        with TemporaryDirectory() as folder:
            doc = prepared_run(Path(folder),source,context)
            stored = json.loads(doc.read_bytes())['inputs']
            self.assert_inputs(stored, [
                ('variable','T','NAME_TO_OPEN','required'),
                ('variable','T','BOTH','required'),
                ('variable','T','FAILURE_INPUT','conditional'),
                ('teach_program_position','DRAFTTP','1[group=1]','conditional'),
                ('teach_program_position','OTHER','1[group=1]','conditional'),
            ])
            left, right = runner.run_document(doc)['results']['text_output'].split(':')
            self.assertEqual((int(left), float(right)), (21,11.0))

    def test_failure_guard_retains_existing_handle_after_open_to_same_output(self):
        context = two_banks()
        context['teach_programs']['programs']['OTHER']['positions'][0]['uframe'] = 31
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) OPEN_TPE(name_to_open,TPE_RDACC,TPE_NOREJ,h,s) "
            "IF s<>0 THEN GET_POS_FRM(h,1,1,f,t,s) "
            "IF (s=0) AND (f=7) THEN WRITE(previous_handle) ELSE WRITE(impossible) ENDIF "
            "ELSE WRITE(GET_POS_TPE(h,1,s).x) ENDIF",
            'name_to_open:STRING[36] h,s,f,t,previous_handle,impossible:INTEGER', context=context,
        )
        self.assert_inputs(prepared, [
            ('variable','T','NAME_TO_OPEN','required'),
            ('variable','T','PREVIOUS_HANDLE','conditional'),
            ('teach_program_position','DRAFTTP','1[group=1]','conditional'),
            ('teach_program_position','OTHER','1[group=1]','conditional'),
        ])

    def test_select_follows_literal_indexed_status_and_plain_status_copy(self):
        prepared = prepare(
            "OPEN_TPE(name_to_open,TPE_RDACC,TPE_NOREJ,h,result[1]) receipt=result[1] reset=0 "
            "SELECT receipt OF CASE(0): WRITE(GET_POS_TPE(h,1,s).x,reset) ELSE: WRITE(failed) ENDSELECT",
            'name_to_open:STRING[36] h,s,receipt,reset,failed:INTEGER result:ARRAY[1] OF INTEGER', context=two_banks(),
        )
        self.assert_inputs(prepared, [
            ('variable','T','NAME_TO_OPEN','required'),
            ('variable','T','FAILED','conditional'),
            ('teach_program_position','DRAFTTP','1[group=1]','conditional'),
            ('teach_program_position','OTHER','1[group=1]','conditional'),
        ])

    def test_compound_guard_uses_status_before_short_circuiting_handle_read(self):
        prepared = prepare(
            "OPEN_TPE(name_to_open,TPE_RDACC,TPE_NOREJ,h,s) "
            "IF (s=0) AND (GET_POS_TPE(h,1,read_status).x>0.0) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'name_to_open:STRING[36] h,s,read_status,good,other:INTEGER', context=two_banks(),
        )
        self.assert_inputs(prepared, [
            ('variable','T','NAME_TO_OPEN','required'), ('variable','T','GOOD','conditional'),
            ('variable','T','OTHER','conditional'),
            ('teach_program_position','DRAFTTP','1[group=1]','conditional'),
            ('teach_program_position','OTHER','1[group=1]','conditional'),
        ])

    def test_handle_number_guard_preserves_allocation_program_identity(self):
        prepared = prepare(
            "IF pick THEN OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,old_h,s) ENDIF "
            "OPEN_TPE('other',TPE_RDACC,TPE_NOREJ,h,s) "
            "IF h=1 THEN WRITE(GET_POS_TPE(1,1,read_status).x) ELSE WRITE(GET_POS_TPE(2,1,read_status).x) ENDIF",
            'pick:BOOLEAN old_h,h,s,read_status:INTEGER', context=two_banks(),
        )
        self.assert_inputs(prepared, [
            ('variable','T','PICK','required'),
            ('teach_program_position','OTHER','1[group=1]','required'),
        ])

    def test_unrelated_intervening_assignment_invalidates_original_status_alias(self):
        prepared = prepare(
            "h=0 seed=0 OPEN_TPE(name_to_open,TPE_RDACC,TPE_NOREJ,h,s) s=seed "
            "IF s=0 THEN WRITE(GET_POS_TPE(h,1,read_status).x) ENDIF",
            'name_to_open:STRING[36] h,s,seed,read_status:INTEGER', context=two_banks(),
        )
        self.assert_inputs(prepared, [
            ('variable','T','NAME_TO_OPEN','required'),
            ('teach_program_position','DRAFTTP','1[group=1]','conditional'),
            ('teach_program_position','OTHER','1[group=1]','conditional'),
        ], ['position-read'])

    def test_linked_child_rejection_selects_old_handle_for_failure_branch(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            main,child=root/'main.py',root/'child.py'
            main.write_bytes(translate("""PROGRAM MAIN
VAR h,old_h,s,read_status:INTEGER
BEGIN
  OPEN_TPE('other',TPE_RDACC,TPE_NOREJ,old_h,s)
  h=old_h
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s)
  IF s=0 THEN
    WRITE('opened:',GET_POS_TPE(h,1,read_status).x)
    CLOSE_TPE(h,s)
  ELSE
    WRITE('retained:',GET_POS_TPE(h,1,read_status).x)
  ENDIF
  CLOSE_TPE(old_h,s)
  CONT_TASK('CHILD',s)
END MAIN
""",cooperative=True).python_source.encode('utf-8'))
            child.write_bytes(translate("""PROGRAM CHILD
VAR reject_code,h,s:INTEGER
BEGIN
  OPEN_TPE('draftTp',TPE_RDACC,reject_code,h,s)
  PAUSE
END CHILD
""",cooperative=True).python_source.encode('utf-8'))
            config=two_banks()
            config['variables']=[dict(program='CHILD',path='REJECT_CODE',type=['INTEGER'],value=4)]
            doc=root/'linked.run.json'
            prepared=create_project_document([main,child], doc, entry='MAIN', context=config, discover=True)
            self.assert_inputs(prepared['inputs'], [
                ('variable','CHILD','REJECT_CODE','conditional'),
                ('teach_program_position','DRAFTTP','1[group=1]','conditional'),
                ('teach_program_position','OTHER','1[group=1]','conditional'),
            ], ['task-scheduling','task-wait','task-continuation'])
            label,x=runner.run_document(doc)['results']['text_output'].split(':')
            self.assertEqual((label,float(x)),('retained',11.0))
