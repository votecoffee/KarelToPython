"""Independent ATAN2 token selection and immutable complete-source controls."""
import hashlib,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]/'tools/audit_atan2_corpus.py'
spec=importlib.util.spec_from_file_location('atan2_audit',TOOL); audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)

class BearingSelectionTests(unittest.TestCase):
    def test_case_insensitive_token(self): self.assertEqual(audit.atan2_tokens('aTaN2(1,1)'),[dict(name='ATAN2',line=1,column=1)])
    def test_exact_names_only(self): self.assertEqual(audit.atan2_tokens('MY_ATAN2 ATAN20 SIN COS ASIN ACOS TAN EXP LN'),[])
    def test_string_comment_directive_decoys(self): self.assertEqual(audit.atan2_tokens("-- ATAN2\n%ATAN2=0\ntext='a''ATAN2(0,0)'"),[])
    def test_newlines_and_continuation_locations(self): self.assertEqual(audit.atan2_tokens('r=&\r\n ATAN2(1,1)\r\fatan2(0,1)'),[dict(name='ATAN2',line=2,column=2),dict(name='ATAN2',line=4,column=1)])
    def test_lexical_candidates_include_invalid_forms(self): self.assertEqual(len(audit.atan2_tokens('VAR ATAN2: REAL invalid ATAN2')),2)
    def test_names_are_independent_of_current_parser(self): self.assertEqual(audit.FUNCTIONS,('ATAN2',))

class BearingAuditIntegrationTests(unittest.TestCase):
    def test_hash_controls_and_no_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'KL/V8.33').mkdir(parents=True); (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'; pc=root/'PC/V8.33/probe.PC'
            raw=b'PROGRAM T VAR r: REAL BEGIN r=ATAN2(0,0) END T'; source.write_bytes(raw); pc.write_bytes(b'original PC')
            unselected=root/'KL/V8.33/plain.KL'; unselected.write_bytes(b'PROGRAM T BEGIN END T')
            output=root/'audit.json'; baseline=root/'baseline.json'
            command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True); self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text()); self.assertEqual(report['counts'],{'translated':1})
            self.assertEqual(report['atan2_token_count'],1)
            self.assertEqual(report['cases'][0]['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['cases'][0]['preexisting_pc_sha256'],hashlib.sha256(b'original PC').hexdigest())
            self.assertEqual(source.read_bytes(),raw)
            baseline.write_bytes(output.read_bytes())
            self.assertEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'changed'); self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'original PC'); source.write_bytes(raw+b'\n'); self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            source.write_bytes(raw); unselected.write_bytes(b'PROGRAM T BEGIN END T\n'); self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
    def test_earlier_file_blocker_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'KL/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'; raw=b'PROGRAM T VAR f: FILE r: REAL BEGIN r=ATAN2(1,1) END T'; source.write_bytes(raw)
            output=root/'audit.json'
            result=subprocess.run([sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(output.read_text())['cases'][0]['diagnostic']['code'],'E_TYPE')
            self.assertEqual(source.read_bytes(),raw)

if __name__=='__main__': unittest.main()
