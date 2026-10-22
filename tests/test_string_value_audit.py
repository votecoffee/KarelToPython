"""Fixed original-source selection, provenance and translation-only boundaries."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1]/'tools/audit_string_value_corpus.py'
spec = importlib.util.spec_from_file_location('string_value_audit', TOOL)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class StringValueAuditTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.raw = {}
        for relative in audit.SELECTED:
            path = self.root/'KL/V8.33'/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text("PROGRAM p VAR f: VISION BEGIN END p",encoding='utf-8')
            self.raw[relative] = path.read_bytes()

    def invoke(self, baseline=None):
        output = self.root/'audit.json'
        command = [sys.executable,str(TOOL),'--corpus',str(self.root),'--output',str(output)]
        if baseline: command += ['--baseline',str(baseline)]
        process = subprocess.run(command,capture_output=True,text=True,timeout=10)
        return process,json.loads(output.read_text()) if process.returncode==0 else None

    def baseline(self):
        process,_ = self.invoke()
        self.assertEqual(process.returncode,0,process.stderr)
        path = self.root/'baseline.json'
        path.write_bytes((self.root/'audit.json').read_bytes())
        return path

    def test_complete_source_blockers_hashes_and_uppercase_pc(self):
        pc = self.root/'PC/V8.33'/Path(audit.SELECTED[0]).with_suffix('.PC')
        pc.parent.mkdir(parents=True)
        pc.write_bytes(b'preexisting PC')
        process,report = self.invoke()
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual((report['selection'],report['counts']),(audit.SELECTED,{'rejected':5}))
        for row in report['cases']:
            relative = row['relative_source']
            self.assertEqual(row['diagnostic']['code'],'E_TYPE')
            self.assertEqual(row['source_sha256'],hashlib.sha256(self.raw[relative]).hexdigest())
            self.assertEqual((self.root/'KL/V8.33'/relative).read_bytes(),self.raw[relative])
        self.assertEqual(report['cases'][0]['preexisting_pc_sha256'],hashlib.sha256(pc.read_bytes()).hexdigest())
        self.assertEqual(pc.read_bytes(),b'preexisting PC')
    def test_translation_does_not_execute_runtime_failure(self):
        path = self.root/'KL/V8.33'/audit.SELECTED[0]
        path.write_text("PROGRAM p VAR x: INTEGER ROUTINE r(p: STRING) BEGIN x=1 DIV 0 END r BEGIN r('abc') END p")
        process,report = self.invoke()
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(report['counts'],{'translated':1,'rejected':4})
    def test_unchanged_baseline(self):
        baseline = self.baseline()
        process,report = self.invoke(baseline)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(report['comparison']['transitions'],{'rejected_to_rejected':5})
        self.assertEqual(report['comparison']['regressions'],0)
    def test_selected_source_drift(self):
        baseline = self.baseline()
        (self.root/'KL/V8.33'/audit.SELECTED[0]).write_text('PROGRAM p\nVAR f: VISION BEGIN END p')
        self.assertNotEqual(self.invoke(baseline)[0].returncode,0)
    def test_paired_pc_drift(self):
        pc = self.root/'PC/V8.33'/Path(audit.SELECTED[0]).with_suffix('.pc')
        pc.parent.mkdir(parents=True)
        pc.write_bytes(b'first')
        baseline = self.baseline()
        pc.write_bytes(b'second')
        self.assertNotEqual(self.invoke(baseline)[0].returncode,0)
    def test_baseline_selection_drift(self):
        baseline = self.baseline()
        data = json.loads(baseline.read_text())
        data['selection'] = data['selection'][:-1]
        baseline.write_text(json.dumps(data))
        self.assertNotEqual(self.invoke(baseline)[0].returncode,0)
    def test_missing_selected_source_fails(self):
        (self.root/'KL/V8.33'/audit.SELECTED[0]).unlink()
        self.assertNotEqual(self.invoke()[0].returncode,0)
    def test_string_return_control_translates_without_execution(self):
        path = self.root/'KL/V8.33'/audit.SELECTED[-1]
        path.write_text("PROGRAM p ROUTINE f: STRING[8] BEGIN RETURN 'abc' END f BEGIN END p")
        process,report = self.invoke()
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(report['cases'][-1]['status'],'translated')


if __name__ == '__main__': unittest.main()
