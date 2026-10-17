"""Stable routine-interface candidates and complete-source acceptance controls."""
import hashlib,importlib.util,json
from pathlib import Path
import subprocess,sys,tempfile,unittest
TOOL=Path(__file__).resolve().parents[1]/'tools/audit_vector_routine_corpus.py'
spec=importlib.util.spec_from_file_location('vector_routine_audit',TOOL)
audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class VectorRoutineSelectionTests(unittest.TestCase):
    def scan(self,text): return audit.vector_routine_tokens(text)
    def test_vector_result(self): self.assertEqual(self.scan('ROUTINE get: VECTOR'),[dict(routine='GET',line=1,column=14)])
    def test_vector_parameter_and_result(self): self.assertEqual(len(self.scan('ROUTINE get(v: VECTOR): VECTOR')),2)
    def test_global_and_local_variables_excluded(self): self.assertEqual(self.scan('VAR a: VECTOR ROUTINE get VAR v: VECTOR BEGIN END get'),[])
    def test_constant_section_ends_interface(self): self.assertEqual(self.scan('ROUTINE get CONST x=VECTOR'),[])
    def test_strings_comments_directives_excluded(self): self.assertEqual(self.scan("'ROUTINE get: VECTOR'\n-- ROUTINE get: VECTOR\n%COMMENT=ROUTINE get: VECTOR"),[])
    def test_multiple_routines(self): self.assertEqual([r['routine'] for r in self.scan('ROUTINE first: VECTOR BEGIN END first ROUTINE second(v: VECTOR) BEGIN END second')],['FIRST','SECOND'])
    def test_continuation_and_physical_location(self): self.assertEqual(self.scan('routine get: & -- result\r\n VECTOR')[0],dict(routine='GET',line=2,column=2))
    def test_external_interface_is_candidate_not_accepted(self): self.assertEqual(len(self.scan('ROUTINE get: VECTOR FROM external_program')),1)


class VectorRoutineAuditIntegrationTests(unittest.TestCase):
    def test_source_acceptance_never_executes_uninitialized_result_or_abort(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'KL/V8.33').mkdir(parents=True); (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'
            raw=b'PROGRAM T VAR v: VECTOR ROUTINE get: VECTOR BEGIN RETURN v END get BEGIN v=get() ABORT END T'
            source.write_bytes(raw)
            unselected=root/'KL/V8.33/plain.KL'; unselected.write_bytes(b'PROGRAM N BEGIN END N')
            pc=root/'PC/V8.33/probe.PC'; pc.write_bytes(b'original PC')
            output=root/'audit.json'; command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text())
            self.assertEqual(report['counts'],{'translated':1}); self.assertEqual(report['scanned_files'],2)
            self.assertEqual(report['vector_routine_token_count'],1)
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
            source.write_bytes(raw.replace(b'VAR v:',b'VAR file_var: FILE v:'))
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(json.loads(output.read_text())['cases'][0]['diagnostic']['code'],'E_TYPE')


if __name__=='__main__': unittest.main()
