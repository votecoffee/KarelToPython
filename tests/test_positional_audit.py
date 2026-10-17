"""Positional lexical selection and immutable complete-source controls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py.lexer import PATTERN

TOOL=Path(__file__).resolve().parents[1]/'tools/audit_positional_corpus.py'
spec=importlib.util.spec_from_file_location('positional_audit',TOOL)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class PositionalSelectionTests(unittest.TestCase):
    def scan(self,text): return audit.positional_tokens(text,PATTERN)
    def test_three_types(self): self.assertEqual([r['name'] for r in self.scan('XYZWPR CONFIG VECTOR')],['XYZWPR','CONFIG','VECTOR'])
    def test_case_insensitive(self): self.assertEqual(self.scan('vector'),[dict(name='VECTOR',line=1,column=1)])
    def test_comment_decoy(self): self.assertEqual(self.scan('-- XYZWPR CONFIG VECTOR'),[])
    def test_literal_decoy(self): self.assertEqual(self.scan("text='XYZWPR CONFIG VECTOR'"),[])
    def test_directive_decoy(self): self.assertEqual(self.scan('%VECTOR=1'),[])
    def test_substring_decoy(self): self.assertEqual(self.scan('XYZWPREXT VECTORS MY_CONFIG'),[])
    def test_physical_locations(self): self.assertEqual(self.scan('x: &\n VECTOR'),[dict(name='VECTOR',line=2,column=2)])


class PositionalAuditIntegrationTests(unittest.TestCase):
    def test_complete_sources_and_drift_guards_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'KL/V8.33').mkdir(parents=True)
            (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'
            # Both would fail if run: these checks establish translation only.
            raw=b'PROGRAM T VAR v: VECTOR BEGIN v.x=v.y END T'
            source.write_bytes(raw)
            pc=root/'PC/V8.33/probe.PC'
            pc.write_bytes(b'original PC')
            output=root/'audit.json'
            command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text())
            self.assertEqual(report['counts'],{'translated':1})
            self.assertEqual(report['cases'][0]['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['cases'][0]['preexisting_pc_sha256'],hashlib.sha256(b'original PC').hexdigest())
            self.assertEqual(source.read_bytes(),raw)
            baseline=root/'baseline.json'
            baseline.write_bytes(output.read_bytes())
            result=subprocess.run([*command,'--baseline',str(baseline)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(output.read_text())['comparison']['regressions'],0)
            pc.write_bytes(b'changed PC')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'original PC')
            source.write_bytes(raw+b'\n')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            source.write_bytes(b'PROGRAM T VAR f: FILE v: VECTOR BEGIN END T')
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(output.read_text())['cases'][0]['diagnostic']['code'],'E_TYPE')


if __name__=='__main__': unittest.main()
