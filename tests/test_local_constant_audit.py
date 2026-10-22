"""Independent lexical controls and source-integrity checks for local CONST scanning."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py.lexer import PATTERN

TOOL = Path(__file__).resolve().parents[1] / 'tools/audit_local_constant_corpus.py'
spec = importlib.util.spec_from_file_location('local_constant_audit', TOOL)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class LocalConstantSelectionTests(unittest.TestCase):
    def scan(self, text): return audit.declaration_candidates(text, PATTERN)

    def test_actual_local_section(self):
        self.assertEqual(self.scan('ROUTINE work\nCONST step=7\nBEGIN END work'),
                         [dict(routine_name_token='WORK', line=2, column=1)])

    def test_mixed_case(self):
        self.assertEqual(self.scan('routine work const step=7 begin end work')[0]['routine_name_token'], 'WORK')

    def test_multiple_sections_and_routines(self):
        rows = self.scan('ROUTINE first CONST a=1 VAR x: INTEGER CONST b=2 BEGIN END first ROUTINE second CONST c=3 BEGIN END second')
        self.assertEqual([r['routine_name_token'] for r in rows], ['FIRST', 'FIRST', 'SECOND'])

    def test_global_section_excluded(self):
        self.assertEqual(self.scan('PROGRAM p CONST a=1 ROUTINE work VAR x: INTEGER BEGIN END work BEGIN END p'), [])

    def test_comment_decoys_excluded(self):
        self.assertEqual(self.scan('-- ROUTINE work CONST step=7\nPROGRAM p BEGIN END p'), [])

    def test_string_decoys_excluded(self):
        self.assertEqual(self.scan("PROGRAM p CONST text='ROUTINE work CONST step=7' BEGIN END p"), [])

    def test_directive_decoys_excluded(self):
        self.assertEqual(self.scan('%COMMENT = ROUTINE work CONST step=7\nPROGRAM p BEGIN END p'), [])

    def test_external_header_does_not_capture_following_global_const(self):
        self.assertEqual(self.scan("ROUTINE external FROM other\nCONST global_value=7\nBEGIN END p"), [])

    def test_body_const_is_not_a_declaration_candidate(self):
        self.assertEqual(self.scan('ROUTINE work BEGIN CONST step=7 END work'), [])

    def test_main_const_after_finished_routine_excluded(self):
        self.assertEqual(self.scan('ROUTINE work BEGIN END work CONST global_value=7 BEGIN END p'), [])

    def test_complete_token_continuation_keeps_physical_position(self):
        rows = self.scan('ROUTINE &\n work\n CONST step = &\n 7\nBEGIN END work')
        self.assertEqual(rows, [dict(routine_name_token='WORK', line=3, column=2)])

    def test_parameter_string_does_not_reset_routine(self):
        rows = self.scan('ROUTINE work(p: STRING) CONST n=7 BEGIN END work')
        self.assertEqual(len(rows), 1)


class LocalConstantAuditIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / 'KL/V8.33').mkdir(parents=True)
        (self.root / 'PC/V8.33').mkdir(parents=True)

    def source(self, name, text):
        path = self.root / 'KL/V8.33' / name
        path.write_text(text, encoding='utf-8')
        return path

    def run_audit(self, baseline=None):
        out = self.root / 'audit.json'
        command = [sys.executable, str(TOOL), '--corpus', str(self.root), '--output', str(out)]
        if baseline: command += ['--baseline', str(baseline)]
        process = subprocess.run(command, capture_output=True, text=True)
        return process, json.loads(out.read_text()) if process.returncode == 0 else None

    def test_selected_complete_source_translates_without_execution(self):
        path = self.source('probe.KL', 'PROGRAM p ROUTINE work CONST n=7 BEGIN WHILE ON DO ENDWHILE END work BEGIN work END p')
        raw = path.read_bytes()
        process, report = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(report['counts'], {'translated': 1})
        self.assertEqual(report['cases'][0]['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(path.read_bytes(), raw)

    def test_preserves_earlier_blockers_and_pc_hash(self):
        path = self.source('probe.KL', 'PROGRAM p VAR f: VISION ROUTINE work CONST n=7 BEGIN END work BEGIN END p')
        raw = path.read_bytes()
        pc = self.root / 'PC/V8.33/probe.PC'
        pc.write_bytes(b'preexisting PC evidence')
        process, report = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        case = report['cases'][0]
        self.assertEqual((case['status'], case['diagnostic']['code']), ('rejected', 'E_TYPE'))
        self.assertEqual(case['preexisting_pc_sha256'], hashlib.sha256(pc.read_bytes()).hexdigest())
        self.assertEqual(path.read_bytes(), raw)

    def test_no_candidates_is_explicit_gap(self):
        self.source('probe.KL', 'PROGRAM p CONST n=7 BEGIN END p')
        process, report = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual((report['scanned_files'], report['cases'], report['local_const_section_candidates']), (1, [], 0))

    def test_baseline_unchanged_sources(self):
        self.source('probe.KL', 'PROGRAM p ROUTINE work CONST n=7 BEGIN END work BEGIN END p')
        process, _ = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        baseline = self.root / 'baseline.json'
        baseline.write_bytes((self.root / 'audit.json').read_bytes())
        process, report = self.run_audit(baseline)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(report['comparison']['transitions'], {'translated_to_translated': 1})
        self.assertEqual(report['comparison']['regressions'], 0)

    def test_unselected_source_drift_rejected(self):
        path = self.source('probe.KL', 'PROGRAM p CONST n=7 BEGIN END p')
        self.run_audit()
        baseline = self.root / 'baseline.json'
        baseline.write_bytes((self.root / 'audit.json').read_bytes())
        path.write_text('PROGRAM p CONST n=9 BEGIN END p', encoding='utf-8')
        process, _ = self.run_audit(baseline)
        self.assertNotEqual(process.returncode, 0)

    def test_selected_pc_drift_rejected(self):
        self.source('probe.KL', 'PROGRAM p ROUTINE work CONST n=7 BEGIN END work BEGIN END p')
        pc = self.root / 'PC/V8.33/probe.pc'
        pc.write_bytes(b'first')
        self.run_audit()
        baseline = self.root / 'baseline.json'
        baseline.write_bytes((self.root / 'audit.json').read_bytes())
        pc.write_bytes(b'second')
        process, _ = self.run_audit(baseline)
        self.assertNotEqual(process.returncode, 0)


if __name__ == '__main__': unittest.main()
