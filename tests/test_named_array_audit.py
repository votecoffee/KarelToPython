"""Positive and negative controls for the zero-match real-corpus scanner."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/audit_named_array_corpus.py'


class NamedArrayAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.sources = self.root / 'KL/V8.33'
        self.sources.mkdir(parents=True)
        self.pc = self.root / 'PC/V8.33'
        self.pc.mkdir(parents=True)
        self.report = self.root / 'report.json'

    def write(self, name, source): (self.sources / name).write_bytes(source.encode('utf-8'))

    def run_audit(self, *extra):
        return subprocess.run([sys.executable, str(TOOL), '--corpus', str(self.root),
                               '--output', str(self.report), *extra], capture_output=True, text=True)

    def test_positive_definitions_and_comment_literal_directive_negatives(self):
        self.write('named.KL', 'PROGRAM T\nTYPE row_t=ARRAY[2] OF INTEGER\nVAR a: row_t\nBEGIN a[1]=7 END T')
        self.write('structure.KL', 'PROGRAM T\nTYPE rec_t=STRUCTURE data: ARRAY[2] OF INTEGER ENDSTRUCTURE\nVAR a: rec_t\nBEGIN END T')
        self.write('noise.KL', "PROGRAM T\n%NOLOCKGROUP -- TYPE noise_t=ARRAY[3] OF INTEGER\nVAR text: STRING[80]\nBEGIN\n-- TYPE comment_t=ARRAY[2] OF INTEGER\ntext='TYPE literal_t=ARRAY[2] OF INTEGER'\nEND T")
        self.write('continued.KL', 'PROGRAM T\r\nTYPE row_t &\r\n = & -- next physical line\r\n ARRAY[2] OF INTEGER\r\nVAR a: row_t\r\nBEGIN END T')
        paired = self.pc / 'named.PC'
        paired.write_bytes(b'offline hash fixture; not a compiler output')
        process = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        report = json.loads(self.report.read_text())
        self.assertEqual(report['scanned_files'], 4)
        self.assertEqual(report['definition_candidates'], 2)
        self.assertEqual(report['counts'], {'translated': 2})
        self.assertEqual({row['relative_source'] for row in report['cases']}, {'continued.KL', 'named.KL'})
        named = next(row for row in report['cases'] if row['relative_source'] == 'named.KL')
        self.assertEqual(named['preexisting_pc_sha256'], hashlib.sha256(paired.read_bytes()).hexdigest())
        self.assertEqual(named['named_array_types']['ROW_T'], ['ARRAY', 2, ['INTEGER'], 'ROW_T'])
        continued = next(row for row in report['cases'] if row['relative_source'] == 'continued.KL')
        self.assertEqual(continued['array_definition_candidates'], [{'left_name_token': 'ROW_T', 'line': 2, 'column': 6}])

    def test_zero_candidates_and_comparison_do_not_claim_new_acceptance(self):
        self.write('plain.KL', 'PROGRAM T\nVAR a: ARRAY[2] OF INTEGER\nBEGIN a[1]=7 END T')
        process = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        baseline = self.root / 'baseline.json'
        baseline.write_bytes(self.report.read_bytes())
        process = self.run_audit('--baseline', str(baseline))
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(self.report.read_text())
        self.assertEqual((report['cases'], report['definition_candidates'], report['counts']), ([], 0, {}))
        self.assertEqual(report['comparison']['newly_translated'], 0)
        self.assertEqual(report['comparison']['regressions'], 0)
        self.assertEqual(report['comparison']['transitions'], {})

    def test_comparison_rejects_drift_even_in_an_unselected_source(self):
        self.write('plain.KL', 'PROGRAM T\nBEGIN END T')
        process = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        baseline = self.root / 'baseline.json'
        baseline.write_bytes(self.report.read_bytes())
        self.write('plain.KL', 'PROGRAM T\nVAR x: INTEGER\nBEGIN x=7 END T')
        process = self.run_audit('--baseline', str(baseline))
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('AssertionError', process.stderr)


if __name__ == '__main__': unittest.main()
