"""Stable positional-interface selection and complete-source evidence guards."""
import hashlib,importlib.util,json
from pathlib import Path
import subprocess,sys,tempfile,unittest
TOOL=Path(__file__).resolve().parents[1]/'tools/audit_positional_routine_corpus.py'
spec=importlib.util.spec_from_file_location('positional_routine_audit',TOOL)
audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class PositionalRoutineSelectionTests(unittest.TestCase):
    def scan(self,text): return audit.positional_routine_tokens(text)
    def test_record_result(self): self.assertEqual(self.scan('ROUTINE get: XYZWPR'),[dict(routine='GET',type_name='XYZWPR',line=1,column=14)])
    def test_all_record_and_joint_spellings(self):
        for kind in ('CONFIG','POSITION','XYZWPR','XYZWPREXT','JOINTPOS',*[f'JOINTPOS{n}' for n in range(1,10)]):
            with self.subTest(kind=kind): self.assertEqual(self.scan(f'ROUTINE get: {kind}')[0]['type_name'],kind)
    def test_vector_and_lookalikes_excluded(self): self.assertEqual(self.scan('ROUTINE get(v: VECTOR): JOINTPOS10'),[])
    def test_global_and_local_sections_excluded(self): self.assertEqual(self.scan('VAR p: POSITION ROUTINE get VAR q: XYZWPR BEGIN END get'),[])
    def test_strings_comments_and_directives_excluded(self): self.assertEqual(self.scan("'ROUTINE get: POSITION'\n-- ROUTINE get: CONFIG\n%COMMENT=ROUTINE get: XYZWPR"),[])
    def test_case_continuation_and_location(self): self.assertEqual(self.scan('routine get: & -- type\r\n jointpos3')[0],dict(routine='GET',type_name='JOINTPOS3',line=2,column=2))
    def test_multiple_parameters_and_result(self): self.assertEqual(len(self.scan('ROUTINE get(p: XYZWPR; j: JOINTPOS3): CONFIG')),3)
    def test_array_reference_formals_are_candidates_only(self): self.assertEqual(len(self.scan('ROUTINE get(p: ARRAY OF XYZWPR)')),1)


class PositionalRoutineAuditIntegrationTests(unittest.TestCase):
    def test_complete_sources_never_execute_uninitialized_results_or_abort(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'KL/V8.33').mkdir(parents=True); (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'
            raw=b'PROGRAM T VAR p: XYZWPR ROUTINE get: XYZWPR BEGIN RETURN p END get BEGIN p=get() ABORT END T'
            source.write_bytes(raw)
            unselected=root/'KL/V8.33/plain.KL'; unselected.write_bytes(b'PROGRAM N BEGIN END N')
            pc=root/'PC/V8.33/probe.PC'; pc.write_bytes(b'original PC')
            output=root/'audit.json'; command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text()); self.assertEqual(report['counts'],{'translated':1})
            self.assertEqual(report['scanned_files'],2); self.assertEqual(report['positional_routine_token_count'],1)
            self.assertEqual(report['cases'][0]['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['cases'][0]['preexisting_pc_sha256'],hashlib.sha256(b'original PC').hexdigest())
            self.assertEqual(source.read_bytes(),raw)
            baseline=root/'baseline.json'; baseline.write_bytes(output.read_bytes())
            self.assertEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'changed PC')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'original PC'); source.write_bytes(raw+b'\n')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            source.write_bytes(raw); unselected.write_bytes(unselected.read_bytes()+b'\n')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            source.write_bytes(raw.replace(b'VAR p:',b'VAR file_var: FILE p:'))
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(json.loads(output.read_text())['cases'][0]['diagnostic']['code'],'E_TYPE')


if __name__=='__main__': unittest.main()
