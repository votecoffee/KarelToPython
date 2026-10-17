"""UNPOS selection preserves complete source/PC evidence and never executes it."""
import hashlib,importlib.util,json
from pathlib import Path
import subprocess,sys,tempfile,unittest
from karel2py.lexer import PATTERN

TOOL=Path(__file__).resolve().parents[1]/'tools/audit_unpos_corpus.py'
spec=importlib.util.spec_from_file_location('unpos_audit',TOOL)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class UnposSelectionTests(unittest.TestCase):
    def scan(self,text): return audit.unpos_tokens(text,PATTERN)
    def test_calls_selected(self): self.assertEqual(len(self.scan('UNPOS(p,a,b,c,d,e,f,g) UNPOS(q,a,b,c,d,e,f,g)')),2)
    def test_case_insensitive(self): self.assertEqual(self.scan('unpos'),[dict(name='UNPOS',line=1,column=1)])
    def test_comment_decoy(self): self.assertEqual(self.scan('-- UNPOS'),[])
    def test_literal_decoy(self): self.assertEqual(self.scan("text='UNPOS'"),[])
    def test_directive_decoy(self): self.assertEqual(self.scan('%UNPOS=1'),[])
    def test_substrings_and_other_forms(self): self.assertEqual(self.scan('MY_UNPOS UNPOS2 POS'),[])
    def test_physical_location(self): self.assertEqual(self.scan('BEGIN\n UNPOS(p,a,b,c,d,e,f,g)'),[dict(name='UNPOS',line=2,column=2)])


class UnposAuditIntegrationTests(unittest.TestCase):
    def test_complete_sources_unknown_input_never_executed_and_drift_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'KL/V8.33').mkdir(parents=True)
            (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'
            raw=b'PROGRAM T VAR pose: XYZWPR a,b,c,d,e,f: REAL g: CONFIG BEGIN UNPOS(pose,a,b,c,d,e,f,g) END T'
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
            source.write_bytes(raw.replace(b'VAR pose:',b'VAR file_var: FILE pose:'))
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(json.loads(output.read_text())['cases'][0]['diagnostic']['code'],'E_TYPE')


if __name__=='__main__': unittest.main()
