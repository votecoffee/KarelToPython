"""TP handle ownership and discovery at pinned linked-task boundaries."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner, translate
from karel2py.project_run import create_project_document
from karel2py.storage import typed_value
from tests.test_extended_services import pose


LAUNCH = "RUN_TASK('CHILD',0,FALSE,FALSE,0,s) WAIT FOR PAUSE PROGRAM[2] "
CONTINUE = "CONT_TASK('CHILD',s) WAIT FOR PAUSE PROGRAM[2] "


class LinkedTeachHandleTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def run_case(self, main, child, main_decl, child_decl, *, extra=(), position=False, replay=True):
        paths = []
        for name, decl, body in (('MAIN', main_decl, main), ('CHILD', child_decl, child)):
            path = self.root / (name.lower()+'.py')
            source = 'PROGRAM '+name+' VAR '+decl+' BEGIN '+body+' END '+name
            path.write_bytes(translate(source, cooperative=True).python_source.encode('utf-8'))
            paths.append(path)
        target = self.root / 'linked.run.json'
        context = {'teach_programs': {'programs': {'SharedBank': {
            'numeric_registers': {'1': 31},
            'positions': [{'group': 1, 'number': 1, 'value': typed_value(pose(5))}] if position else [],
        }}, 'callers': {'MAIN': 'SharedBank', 'CHILD': 'SharedBank'}}, 'variables': list(extra)}
        prepared = create_project_document(paths, target, entry='MAIN', context=context, discover=True)
        result = runner.run_document(target)['results'] if replay else None
        return prepared['inputs']['template']['discovery'], result

    def assert_inputs(self, report, expected):
        actual = [(row['kind'], row['program'], row['path'], row['certainty']) for row in report['inputs']]
        self.assertCountEqual(actual, expected)

    def assert_no_teach_gaps(self, report):
        self.assertFalse([row for row in report['unresolved'] if row['code'].startswith('teach-')],
                         report['unresolved'])

    def test_paused_child_rejects_foreign_open_and_local_register_read_until_close(self):
        report, replay = self.run_case(
            LAUNCH+
            "h=77 n=66 GET_TPE_REG(1,is_real,n,r,blocked) "
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_NOREJ,h,rejected) saved_h=h "
            +CONTINUE+
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_NOREJ,h,s) "
            "IF (blocked=4) AND (rejected=4) AND (n=66) AND (saved_h=77) AND (h=2) AND (s=0) "
            "THEN WRITE(accepted) ELSE WRITE(unused) ENDIF",
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_ALLREJ,h,s) "
            "p=GET_POS_TPE(h,1,s) PAUSE CLOSE_TPE(h,s) PAUSE",
            'h,n,s,blocked,rejected,saved_h,accepted,unused:INTEGER is_real:BOOLEAN r:REAL',
            'h,s:INTEGER p:XYZWPREXT',
            extra=[dict(program='MAIN',path='ACCEPTED',type=['INTEGER'],value=21)], position=True,
        )
        self.assert_inputs(report, [
            ('teach_program_position', 'SHAREDBANK', '1[group=1]', 'conditional'),
            ('variable', 'MAIN', 'ACCEPTED', 'required'),
        ])
        self.assert_no_teach_gaps(report)
        self.assertEqual(replay['status'], 'paused')
        self.assertEqual(int(replay['text_output']), 21)
        self.assertEqual(replay['programs']['MAIN']['values']['H'], 2)
        self.assertEqual(replay['programs']['CHILD']['values']['P']['X'], 5.0)

    def test_foreign_close_and_position_lookup_preserve_owner_handle_and_receivers(self):
        report, replay = self.run_case(
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_WRTREJ,h,s) "+LAUNCH+
            "IF GET_POS_TPE(h,1,s).x>0.0 THEN again=TRUE ENDIF",
            "CLOSE_TPE(1,foreign_close) "
            "f=9 t=8 GET_POS_FRM(1,1,1,f,t,foreign_position) "
            "OPEN_TPE('SharedBank',TPE_RWACC,TPE_NOREJ,h,blocked_write) "
            "GET_TPE_REG(1,is_real,n,r,s) SET_INT_TPE_REG(1,80,blocked_local) "
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_NOREJ,h,own_read) "
            "IF (foreign_close=3) AND (foreign_position=3) AND (f=9) AND (t=8) "
            "AND (blocked_write=4) AND (blocked_local=4) AND (own_read=0) AND (h=2) "
            "THEN WRITE(expected,n) ELSE WRITE(unused) ENDIF PAUSE",
            'h,s:INTEGER again:BOOLEAN',
            ('foreign_close,foreign_position,blocked_write,blocked_local,h,n,s,f,t,own_read:INTEGER '
             'is_real:BOOLEAN r:REAL expected,unused:INTEGER'),
            extra=[dict(program='CHILD',path='EXPECTED',type=['INTEGER'],value=56)], position=True,
        )
        self.assert_inputs(report, [
            ('teach_numeric_register', 'SHAREDBANK', '1', 'conditional'),
            ('teach_program_position', 'SHAREDBANK', '1[group=1]', 'required'),
            ('variable', 'CHILD', 'EXPECTED', 'conditional'),
        ])
        self.assert_no_teach_gaps(report)
        self.assertEqual(replay['status'], 'paused')
        self.assertEqual([int(item) for item in replay['text_output'].split()], [56, 31])
        self.assertTrue(replay['programs']['MAIN']['values']['AGAIN'])

    def test_resumed_child_reads_parent_write_from_its_still_open_handle(self):
        report, replay = self.run_case(
            LAUNCH+
            "OPEN_TPE('SharedBank',TPE_RWACC,TPE_NOREJ,h,s) "
            "p=GET_POS_TPE(h,1,s) p.x=23.0 SET_POS_TPE(h,1,p,s) "
            "CONTINUE PROGRAM[2] WAIT FOR PAUSE PROGRAM[2]",
            "OPEN_TPE('SharedBank',TPE_RWACC,TPE_NOREJ,h,s) "
            "CNV_STR_CONF('N',cfg,s) p=POS(7,0,0,0,0,0,cfg) SET_POS_TPE(h,1,p,s) PAUSE "
            "IF GET_POS_TPE(h,1,s).x=23.0 THEN WRITE(expected) ELSE WRITE(unused) ENDIF PAUSE",
            'h,s:INTEGER p:XYZWPREXT',
            'h,s,expected,unused:INTEGER p:XYZWPR cfg:CONFIG',
            extra=[dict(program='CHILD',path='EXPECTED',type=['INTEGER'],value=42)],
        )
        self.assert_inputs(report, [('variable', 'CHILD', 'EXPECTED', 'conditional')])
        self.assert_no_teach_gaps(report)
        self.assertEqual(replay['status'], 'paused')
        self.assertEqual(int(replay['text_output']), 42)

    def test_entry_pause_and_final_continuation_find_child_input(self):
        report, replay = self.run_case(
            "RUN_TASK('CHILD',0,TRUE,FALSE,0,s) WAIT FOR PAUSE PROGRAM[2] CONT_TASK('CHILD',s)",
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_NOREJ,h,s) WRITE(GET_POS_TPE(h,1,s).x)",
            's:INTEGER', 'h,s:INTEGER', position=True,
        )
        self.assert_inputs(report, [('teach_program_position', 'SHAREDBANK', '1[group=1]', 'conditional')])
        self.assert_no_teach_gaps(report)
        self.assertEqual(replay['status'], 'completed')
        self.assertEqual(float(replay['text_output']), 5.0)

    def test_last_resume_after_in_body_pause_reaches_natural_completion(self):
        report, replay = self.run_case(
            LAUNCH+"CONT_TASK('CHILD',s)",
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_NOREJ,h,s) PAUSE WRITE(GET_POS_TPE(h,1,s).x)",
            's:INTEGER', 'h,s:INTEGER', position=True,
        )
        self.assert_inputs(report, [('teach_program_position', 'SHAREDBANK', '1[group=1]', 'conditional')])
        self.assert_no_teach_gaps(report)
        self.assertEqual(replay['status'], 'completed')
        self.assertEqual(float(replay['text_output']), 5.0)

    def test_unsynchronized_wait_keeps_foreign_access_unknown(self):
        report, _ = self.run_case(
            "RUN_TASK('CHILD',0,FALSE,FALSE,0,s) DELAY 1 "
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_NOREJ,h,s)",
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_ALLREJ,h,s) PAUSE",
            'h,s:INTEGER', 'h,s:INTEGER', replay=False,
        )
        self.assertIn('teach-handle', {row['code'] for row in report['unresolved']})

    def test_entry_cleanup_can_race_a_final_child_access(self):
        report, _ = self.run_case(
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_ALLREJ,h,s) RUN_TASK('CHILD',0,FALSE,FALSE,0,s)",
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_NOREJ,h,s)",
            'h,s:INTEGER', 'h,s:INTEGER', replay=False,
        )
        self.assertIn('teach-handle', {row['code'] for row in report['unresolved']})

    def test_pause_between_two_otherwise_exact_requests_has_no_early_child_input(self):
        report, replay = self.run_case(
            LAUNCH.strip(),
            "OPEN_TPE('SharedBank',TPE_RDACC,TPE_NOREJ,h,s) PAUSE WRITE(GET_POS_TPE(h,1,s).x)",
            's:INTEGER', 'h,s:INTEGER', position=True,
        )
        self.assert_inputs(report, [])
        self.assert_no_teach_gaps(report)
        self.assertEqual(replay['status'], 'paused')
        self.assertEqual(replay['text_output'], '')
