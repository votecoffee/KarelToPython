"""Selection and full-source provenance for POSITION/XYZWPREXT."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py.lexer import PATTERN

TOOL=Path(__file__).resolve().parents[1]/'tools/audit_position_corpus.py'
spec=importlib.util.spec_from_file_location('position_audit',TOOL)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class PositionSelectionTests(unittest.TestCase):
    def scan(self,text): return audit.position_tokens(text,PATTERN)
    def test_both_types(self): self.assertEqual([r['name'] for r in self.scan('POSITION XYZWPREXT')],['POSITION','XYZWPREXT'])
    def test_case_insensitive(self): self.assertEqual(self.scan('position'),[dict(name='POSITION',line=1,column=1)])
    def test_comment_decoy(self): self.assertEqual(self.scan('-- POSITION XYZWPREXT'),[])
    def test_literal_decoy(self): self.assertEqual(self.scan("text='POSITION XYZWPREXT'"),[])
    def test_directive_decoy(self): self.assertEqual(self.scan('%POSITION=1'),[])
    def test_substring_and_prior_types(self): self.assertEqual(self.scan('POSITIONS MY_XYZWPREXT XYZWPR VECTOR CONFIG'),[])
    def test_physical_location(self): self.assertEqual(self.scan('p: &\n POSITION'),[dict(name='POSITION',line=2,column=2)])


class PositionAuditIntegrationTests(unittest.TestCase):
    def test_full_sources_rejections_and_drift_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'KL/V8.33').mkdir(parents=True)
            (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'
            # This translates but would fail if executed: orientation is uninitialized.
            raw=b'PROGRAM T VAR p: POSITION r: REAL BEGIN r=p.normal.x END T'
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
            self.assertEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'changed PC')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'original PC')
            source.write_bytes(raw+b'\n')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            source.write_bytes(b'PROGRAM T VAR p: POSITION BEGIN p.normal.x=1 END T')
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(json.loads(output.read_text())['cases'][0]['diagnostic']['code'],'E_POSITION_READ_ONLY')


if __name__=='__main__': unittest.main()
