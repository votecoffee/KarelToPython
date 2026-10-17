"""Stable wildcard syntax selection and default-context acceptance evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOL=Path(__file__).resolve().parents[1]/'tools/audit_variable_array_corpus.py'
spec=importlib.util.spec_from_file_location('variable_array_audit',TOOL)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class WildcardArraySelectionTests(unittest.TestCase):
    def scan(self,text): return audit.wildcard_array_tokens(text)
    def test_one_dimension(self): self.assertEqual(self.scan('a: ARRAY[*] OF INTEGER'),[dict(line=1,column=4,declared_rank=1,wildcard_dimensions=[1])])
    def test_multiple_dimensions(self): self.assertEqual(self.scan('ARRAY[*,2,*]')[0]['wildcard_dimensions'],[1,3])
    def test_multiplication_is_not_a_wildcard(self): self.assertEqual(self.scan('ARRAY[2*3,(4*5)]'),[])
    def test_fixed_expression_and_wildcard(self): self.assertEqual(self.scan('ARRAY[2*3,*]')[0]['wildcard_dimensions'],[2])
    def test_quoted_comment_and_directive_decoys(self): self.assertEqual(self.scan("'ARRAY[*]' 'can''t ARRAY[*]'\n-- ARRAY[*]\n%COMMENT=ARRAY[*]"),[])
    def test_formals_and_declarations_both_selected(self): self.assertEqual(len(self.scan('VAR a: ARRAY[*] OF INTEGER ROUTINE f(p: ARRAY[*,*] OF INTEGER)')),2)
    def test_comments_and_continuations_preserve_physical_locations(self):
        self.assertEqual(self.scan('var\r\n a: ARRAY[ & -- dimensions\r\n *, &\r\n 2] OF INTEGER'),[dict(line=2,column=5,declared_rank=2,wildcard_dimensions=[1])])
    def test_case_insensitive_and_named_element(self): self.assertEqual(self.scan('array [ * ] OF row_t')[0]['declared_rank'],1)
    def test_unclosed_or_embedded_invalid_dimension_not_selected(self): self.assertEqual(self.scan('ARRAY[2,*2] ARRAY[*'),[])
    def test_balanced_nested_expression_does_not_change_dimension_count(self): self.assertEqual(self.scan('ARRAY[f(2,3),*]')[0]['declared_rank'],2)


class WildcardArrayAuditIntegrationTests(unittest.TestCase):
    def test_complete_default_context_sources_and_all_hashes_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'KL/V8.33').mkdir(parents=True); (root/'PC/V8.33').mkdir(parents=True)
            source=root/'KL/V8.33/probe.KL'
            raw=b'PROGRAM T VAR a: ARRAY[2] OF INTEGER ROUTINE f(p: ARRAY[*] OF INTEGER) BEGIN END f BEGIN ABORT END T'
            source.write_bytes(raw)
            variable=root/'KL/V8.33/variable.KL'
            variable.write_bytes(b'PROGRAM V VAR a: ARRAY[*] OF INTEGER BEGIN END V')
            unselected=root/'KL/V8.33/plain.KL'; unselected.write_bytes(b'PROGRAM N BEGIN END N')
            pc=root/'PC/V8.33/probe.PC'; pc.write_bytes(b'original PC')
            output=root/'audit.json'
            command=[sys.executable,str(TOOL),'--corpus',str(root),'--output',str(output)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(output.read_text())
            self.assertEqual(report['counts'],{'translated':1,'rejected':1})
            self.assertEqual(report['scanned_files'],3)
            self.assertEqual(report['wildcard_array_token_count'],2)
            self.assertEqual(report['cases'][0]['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['cases'][0]['preexisting_pc_sha256'],hashlib.sha256(b'original PC').hexdigest())
            self.assertEqual(report['cases'][1]['diagnostic']['code'],'E_ARRAY_SIZE')
            self.assertEqual(source.read_bytes(),raw)
            baseline=root/'baseline.json'; baseline.write_bytes(output.read_bytes())
            self.assertEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'changed PC')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            pc.write_bytes(b'original PC'); source.write_bytes(raw+b'\n')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)
            source.write_bytes(raw); unselected.write_bytes(unselected.read_bytes()+b'\n')
            self.assertNotEqual(subprocess.run([*command,'--baseline',str(baseline)],capture_output=True).returncode,0)


if __name__=='__main__': unittest.main()
