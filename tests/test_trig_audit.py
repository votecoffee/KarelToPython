"""Stable trig selection, full-source provenance and no-execution controls."""
import hashlib,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]/'tools/audit_trig_corpus.py'
spec=importlib.util.spec_from_file_location('trig_audit',TOOL); audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)

class TrigSelectionTests(unittest.TestCase):
    def test_all_function_tokens(self): self.assertEqual([row['name'] for row in audit.trig_tokens('SIN(0) COS(0) TAN(0) ASIN(0) ACOS(0)')],list(audit.FUNCTIONS))
    def test_case_insensitive(self): self.assertEqual(audit.trig_tokens('sIn(0)'),[dict(name='SIN',line=1,column=1)])
    def test_comments_strings_directives_are_decoys(self): self.assertEqual(audit.trig_tokens("-- SIN(0)\ntext='COS(0)'\n%TAN=0\nx='a''ASIN(0)'"),[])
    def test_exact_names_only(self): self.assertEqual(audit.trig_tokens('MY_SIN SINE ACOS2 ATAN2 LN EXP'),[])
    def test_physical_positions_newlines_and_continuation(self): self.assertEqual(audit.trig_tokens('a=&\r\n sin(0)\rCOS(0)\f TAN(0)'),[dict(name='SIN',line=2,column=2),dict(name='COS',line=3,column=1),dict(name='TAN',line=4,column=2)])
    def test_candidates_are_not_validated_calls(self): self.assertEqual(len(audit.trig_tokens('VAR SIN: REAL; nonsense COS')),2)

class TrigAuditIntegrationTests(unittest.TestCase):
    def test_complete_source_hashes_no_execution_and_drift_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'KL/V8.33').mkdir(parents=True); (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'; pc=root/'PC/V8.33/probe.PC'
            # Translation succeeds; execution would fail the deliberately unknown angle.
            raw=b'PROGRAM T VAR angle,r: REAL BEGIN r=SIN(angle) END T'
            source.write_bytes(raw); pc.write_bytes(b'original PC')
            unselected=root/'KL/V8.33/plain.KL'; unselected.write_bytes(b'PROGRAM T BEGIN END T')
            output=root/'audit.json'; baseline=root/'baseline.json'
            command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True); self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text()); self.assertEqual(report['counts'],{'translated':1})
            self.assertEqual(report['function_token_counts'],{'SIN':1})
            self.assertEqual(report['cases'][0]['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['cases'][0]['preexisting_pc_sha256'],hashlib.sha256(b'original PC').hexdigest())
            self.assertEqual(source.read_bytes(),raw)
            baseline.write_bytes(output.read_bytes())
            self.assertEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'changed'); self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'original PC'); source.write_bytes(raw+b'\n'); self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            source.write_bytes(raw); unselected.write_bytes(b'PROGRAM T BEGIN END T\n'); self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
    def test_earlier_blocker_is_not_trimmed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'KL/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'; raw=b'PROGRAM T VAR f: VISION r: REAL BEGIN r=COS(0) END T'; source.write_bytes(raw)
            output=root/'audit.json'
            result=subprocess.run([sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text()); self.assertEqual(report['counts'],{'rejected':1})
            self.assertEqual(report['cases'][0]['diagnostic']['code'],'E_TYPE')
            self.assertEqual(source.read_bytes(),raw)

if __name__=='__main__': unittest.main()
