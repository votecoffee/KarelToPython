"""Stable escaped-literal selection and whole-corpus evidence controls."""
import hashlib,importlib.util,json,re
from pathlib import Path
import subprocess,sys,tempfile,unittest
from karel2py.lexer import PATTERN

TOOL=Path(__file__).resolve().parents[1]/'tools/audit_literal_corpus.py'
spec=importlib.util.spec_from_file_location('literal_audit',TOOL)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class LiteralSelectionTests(unittest.TestCase):
    def scan(self,text): return audit.escaped_literal_tokens(text)
    def test_complete_literal_selected(self):
        self.assertEqual(self.scan("'can''t'"),[dict(raw_literal="'can''t'",escaped_apostrophes=1,line=1,column=1)])
    def test_multiple_escapes_counted(self): self.assertEqual(self.scan("'A''''B'" )[0]['escaped_apostrophes'],2)
    def test_empty_and_plain_literals_not_selected(self): self.assertEqual(self.scan("'' 'plain'"),[])
    def test_comment_decoy(self): self.assertEqual(self.scan("-- 'can''t'"),[])
    def test_directive_decoy(self): self.assertEqual(self.scan("%COMMENT='can''t'"),[])
    def test_comment_and_directive_text_inside_literal(self): self.assertEqual(len(self.scan("'A''--%B'")),1)
    def test_physical_location(self): self.assertEqual(self.scan("BEGIN\r\n text='can''t'")[0]['column'],7)
    def test_selection_does_not_depend_on_legacy_token_boundaries(self):
        legacy=re.compile(PATTERN.pattern.replace(r"(?P<STRING>'(?:[^'\r\n\f]|'')*')",r"(?P<STRING>'[^'\r\n\f]*')"))
        source="text='can''t'"
        self.assertEqual(sum(m.lastgroup=='STRING' for m in legacy.finditer(source)),2)
        self.assertEqual(sum(m.lastgroup=='STRING' for m in PATTERN.finditer(source)),1)
        self.assertEqual(len(self.scan(source)),1)


class LiteralAuditIntegrationTests(unittest.TestCase):
    def test_complete_sources_never_executed_and_all_input_hashes_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'KL/V8.33').mkdir(parents=True)
            (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'
            raw=b"PROGRAM T VAR text: STRING[8] BEGIN text='can''t' ABORT END T"
            source.write_bytes(raw)
            unselected=root/'KL/V8.33/plain.KL'
            unselected.write_bytes(b'PROGRAM N BEGIN END N')
            pc=root/'PC/V8.33/probe.PC'
            pc.write_bytes(b'original PC')
            output=root/'audit.json'
            command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text())
            self.assertEqual(report['counts'],{'translated':1})
            self.assertEqual(report['scanned_files'],2)
            self.assertEqual(report['escaped_literal_token_count'],1)
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
            source.write_bytes(raw)
            unselected.write_bytes(unselected.read_bytes()+b'\n')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            source.write_bytes(raw.replace(b'VAR text:',b'VAR file_var: FILE text:'))
            self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual(json.loads(output.read_text())['cases'][0]['diagnostic']['code'],'E_TYPE')


if __name__=='__main__': unittest.main()
