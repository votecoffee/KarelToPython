"""WRITE lexical selection and immutable full-source/PC provenance controls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py.lexer import PATTERN

TOOL = Path(__file__).resolve().parents[1] / 'tools/audit_write_corpus.py'
spec = importlib.util.spec_from_file_location('write_audit', TOOL)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class WriteSelectionTests(unittest.TestCase):
    def scan(self, source): return audit.write_tokens(source, PATTERN)
    def test_write_token(self): self.assertEqual(self.scan("WRITE('text')"), [dict(line=1, column=1)])
    def test_case_insensitive(self): self.assertEqual(len(self.scan("write('text')")), 1)
    def test_multiple_tokens(self): self.assertEqual(len(self.scan("WRITE('text') WRITE('next')")), 2)
    def test_comment_decoy(self): self.assertEqual(self.scan("-- WRITE('text')"), [])
    def test_literal_decoy(self): self.assertEqual(self.scan("text='WRITE text'"), [])
    def test_directive_decoy(self): self.assertEqual(self.scan('%WRITE=125'), [])
    def test_identifier_substring_decoy(self): self.assertEqual(self.scan('WRITER=125'), [])
    def test_continuation_physical_positions(self): self.assertEqual(self.scan("WRITE &\n ('text')\n WRITE('next')"), [dict(line=1,column=1),dict(line=3,column=2)])


class WriteAuditIntegrationTests(unittest.TestCase):
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
        cmd = [sys.executable, str(TOOL), '--corpus', str(self.root), '--output', str(out)]
        if baseline: cmd += ['--baseline', str(baseline)]
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return process, json.loads(out.read_text()) if process.returncode == 0 else None

    def test_write_request_is_translated_without_execution(self):
        path = self.source('probe.KL', "PROGRAM p BEGIN WRITE('text') END p")
        raw = path.read_bytes()
        process, report = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(report['counts'], {'translated': 1})
        self.assertEqual(report['cases'][0]['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(path.read_bytes(), raw)

    def test_overlong_text_acceptance_is_not_execution(self):
        self.source('probe.KL', "PROGRAM p BEGIN WRITE('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa') END p")
        process, report = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(report['counts'], {'translated': 1})

    def test_preserves_complete_source_blockers_and_pc(self):
        path = self.source('probe.KL', "PROGRAM p VAR f: FILE BEGIN WRITE('text') END p")
        raw = path.read_bytes()
        pc = self.root / 'PC/V8.33/probe.PC'
        pc.write_bytes(b'preexisting PC')
        process, report = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        case = report['cases'][0]
        self.assertEqual((case['status'], case['diagnostic']['code']), ('rejected', 'E_TYPE'))
        self.assertEqual(case['preexisting_pc_sha256'], hashlib.sha256(pc.read_bytes()).hexdigest())
        self.assertEqual(path.read_bytes(), raw)

    def test_only_directive_is_unselected(self):
        self.source('probe.KL', 'PROGRAM p\n%WRITE=0\nBEGIN END p')
        process, report = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual((report['scanned_files'], report['cases'], report['write_token_count']), (1, [], 0))

    def test_unchanged_baseline_hashes(self):
        self.source('probe.KL', "PROGRAM p BEGIN WRITE('text') END p")
        process, _ = self.run_audit()
        self.assertEqual(process.returncode, 0, process.stderr)
        baseline = self.root / 'baseline.json'
        baseline.write_bytes((self.root / 'audit.json').read_bytes())
        process, report = self.run_audit(baseline)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(report['comparison']['transitions'], {'translated_to_translated': 1})
        self.assertEqual(report['comparison']['regressions'], 0)

    def test_unselected_source_drift_fails(self):
        path = self.source('probe.KL', 'PROGRAM p BEGIN END p')
        self.run_audit()
        baseline = self.root / 'baseline.json'
        baseline.write_bytes((self.root / 'audit.json').read_bytes())
        path.write_text('PROGRAM p\nBEGIN END p', encoding='utf-8')
        process, _ = self.run_audit(baseline)
        self.assertNotEqual(process.returncode, 0)

    def test_paired_pc_drift_fails(self):
        self.source('probe.KL', "PROGRAM p BEGIN WRITE('text') END p")
        pc = self.root / 'PC/V8.33/probe.pc'
        pc.write_bytes(b'first')
        self.run_audit()
        baseline = self.root / 'baseline.json'
        baseline.write_bytes((self.root / 'audit.json').read_bytes())
        pc.write_bytes(b'second')
        process, _ = self.run_audit(baseline)
        self.assertNotEqual(process.returncode, 0)


if __name__ == '__main__': unittest.main()
