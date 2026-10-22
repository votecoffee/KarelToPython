"""Stable declared-type interface selection and complete-source evidence checks."""
import hashlib,importlib.util,json
from pathlib import Path
import subprocess,sys,tempfile,unittest
TOOL=Path(__file__).resolve().parents[1]/'tools/audit_structure_routine_corpus.py'
spec=importlib.util.spec_from_file_location('structure_routine_audit',TOOL)
audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


class StructureRoutineSelectionTests(unittest.TestCase):
    def scan(self,text): return audit.structure_routine_tokens(text)
    def test_declared_result_type(self):
        self.assertEqual(self.scan('TYPE item_t=STRUCTURE x: INTEGER ENDSTRUCTURE\nROUTINE get: item_t'),[dict(routine='GET',type_name='ITEM_T',line=2,column=14)])
    def test_parameter_and_result(self): self.assertEqual(len(self.scan('TYPE item_t=STRUCTURE x: INTEGER ENDSTRUCTURE ROUTINE get(p: item_t): item_t')),2)
    def test_named_array_result_not_misidentified_as_structure(self): self.assertEqual(self.scan('TYPE item_t=ARRAY[2] OF INTEGER ROUTINE get: item_t'),[])
    def test_global_and_local_variables_not_interface_uses(self): self.assertEqual(self.scan('TYPE item_t=STRUCTURE x: INTEGER ENDSTRUCTURE VAR a: item_t ROUTINE get VAR b: item_t BEGIN END get'),[])
    def test_quoted_comment_and_directive_type_decoys(self): self.assertEqual(self.scan("'item_t=STRUCTURE' -- item_t=STRUCTURE\n%COMMENT=item_t=STRUCTURE\nROUTINE get: item_t"),[])
    def test_comments_continuation_and_case(self): self.assertEqual(self.scan('TYPE Item_T & -- declaration\n = STRUCTURE x: INTEGER ENDSTRUCTURE\nROUTINE get: &\n iTeM_t')[0],dict(routine='GET',type_name='ITEM_T',line=4,column=2))
    def test_array_reference_formal_is_only_an_interface_candidate(self): self.assertEqual(len(self.scan('TYPE item_t=STRUCTURE x: INTEGER ENDSTRUCTURE ROUTINE get(p: ARRAY OF item_t)')),1)
    def test_multiple_routines_and_type_names(self):
        text='TYPE first_t=STRUCTURE x: INTEGER ENDSTRUCTURE second_t=STRUCTURE y: INTEGER ENDSTRUCTURE ROUTINE first: first_t BEGIN END first ROUTINE second(p: second_t) BEGIN END second'
        self.assertEqual([row['type_name'] for row in self.scan(text)],['FIRST_T','SECOND_T'])


class StructureRoutineAuditIntegrationTests(unittest.TestCase):
    def test_full_sources_and_all_hashes_without_runtime_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'KL/V8.33').mkdir(parents=True); (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'
            raw=b'PROGRAM T TYPE item_t=STRUCTURE x: INTEGER ENDSTRUCTURE VAR a: item_t ROUTINE get: item_t BEGIN RETURN a END get BEGIN a=get() ABORT END T'
            source.write_bytes(raw)
            unselected=root/'KL/V8.33/plain.KL'; unselected.write_bytes(b'PROGRAM N BEGIN END N')
            pc=root/'PC/V8.33/probe.PC'; pc.write_bytes(b'original PC')
            output=root/'audit.json'; command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text())
            self.assertEqual(report['counts'],{'translated':1}); self.assertEqual(report['scanned_files'],2)
            self.assertEqual(report['structure_routine_token_count'],1)
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
            source.write_bytes(raw.replace(b'VAR a:',b'VAR file_var: VISION a:'))
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(json.loads(output.read_text())['cases'][0]['diagnostic']['code'],'E_TYPE')


if __name__=='__main__': unittest.main()
