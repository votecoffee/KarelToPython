"""Independent result-header selection, zero coverage and no-execution controls."""
import hashlib,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]/'tools/audit_array_result_corpus.py'
spec=importlib.util.spec_from_file_location('array_result_audit',TOOL); audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)

class ArrayResultSelectionTests(unittest.TestCase):
    def test_result_header_selected_case_insensitively(self): self.assertEqual(audit.array_result_tokens('ROUTINE f: aRrAy OF INTEGER'),[dict(routine='F',line=1,column=12)])
    def test_formals_and_locals_are_not_results(self): self.assertEqual(audit.array_result_tokens('ROUTINE f(p: ARRAY OF INTEGER) VAR a: ARRAY[3] OF INTEGER BEGIN END f'),[])
    def test_formals_do_not_hide_result_header(self):
        self.assertEqual(len(audit.array_result_tokens('ROUTINE f(p: ARRAY[*,*] OF INTEGER; q: INTEGER): ARRAY OF INTEGER BEGIN END f')),1)
    def test_comments_strings_directives_are_decoys(self): self.assertEqual(audit.array_result_tokens("-- ROUTINE f: ARRAY OF INTEGER\n%ARRAY=1\nx='ROUTINE f: ARRAY OF INTEGER'"),[])
    def test_physical_locations_and_continuations(self):
        self.assertEqual(audit.array_result_tokens('ROUTINE f: &\r\n ARRAY OF INTEGER\rBEGIN\fEND f'),[dict(routine='F',line=2,column=2)])
    def test_multiple_results_external_candidates_and_named_gap(self):
        text='ROUTINE f: ARRAY OF INTEGER FROM pkg\nROUTINE g: row_t BEGIN END g\nROUTINE h: ARRAY OF REAL BEGIN END h'
        self.assertEqual([row['routine'] for row in audit.array_result_tokens(text)],['F','H'])

class ArrayResultAuditIntegrationTests(unittest.TestCase):
    def test_complete_source_hashes_no_execution_and_drift_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'KL/V8.33').mkdir(parents=True); (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'; pc=root/'PC/V8.33/probe.PC'
            raw=b'PROGRAM T VAR a: ARRAY[1] OF INTEGER ROUTINE f: ARRAY OF INTEGER VAR p: ARRAY[1] OF INTEGER BEGIN RETURN p END f BEGIN a=f() END T'
            # Returning the uninitialized element would fail if this audit ran KL.
            source.write_bytes(raw); pc.write_bytes(b'original PC')
            plain=root/'KL/V8.33/plain.KL'; plain.write_bytes(b'PROGRAM T BEGIN END T')
            output=root/'audit.json'; baseline=root/'baseline.json'
            command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True); self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text()); self.assertEqual(report['counts'],{'translated':1})
            self.assertEqual(report['array_result_token_count'],1)
            self.assertEqual(report['cases'][0]['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['cases'][0]['preexisting_pc_sha256'],hashlib.sha256(b'original PC').hexdigest())
            self.assertEqual(source.read_bytes(),raw)
            baseline.write_bytes(output.read_bytes())
            self.assertEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'changed'); self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'original PC'); source.write_bytes(raw+b'\n'); self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            source.write_bytes(raw); plain.write_bytes(b'PROGRAM T BEGIN END T\n'); self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
    def test_zero_selected_sources_and_earlier_file_blocker(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'KL/V8.33').mkdir(parents=True); source=root/'KL/V8.33/probe.KL'
            source.write_bytes(b'PROGRAM T VAR a: ARRAY[1] OF INTEGER BEGIN END T')
            output=root/'audit.json'; command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            report=json.loads(output.read_text()); self.assertEqual((report['array_result_token_count'],report['cases'],report['counts']),(0,[],{}))
            raw=b'PROGRAM T VAR handle: FILE ROUTINE f: ARRAY OF INTEGER BEGIN END f BEGIN END T'; source.write_bytes(raw)
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(json.loads(output.read_text())['cases'][0]['diagnostic']['code'],'E_TYPE')
            self.assertEqual(source.read_bytes(),raw)

if __name__=='__main__': unittest.main()
