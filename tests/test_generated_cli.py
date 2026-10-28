"""Every generated Pythonic CLI parses explicit context and successful state output."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate
from tests.legacy_numeric_support import translate as legacy_translate

ROOT=Path(__file__).resolve().parents[1]
BOOTSTRAP='''import runpy,sys
class RuntimeOnly:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.project','tkinter','_tkinter','karel2py.gui','socket','ssl','http.client','urllib.request'):
   raise ImportError('Generated CLI must use runtime only, without desktop or network')
sys.meta_path.insert(0,RuntimeOnly());sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:]
runpy.run_path(sys.argv[0],run_name='__main__')
'''


class GeneratedCLIContextTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='karel2py_cli_');self.addCleanup(temporary.cleanup);self.folder=Path(temporary.name)
        self.script=self.folder/'converted.py';self.state=self.folder/'state.json';self.config=self.folder/'input.json'

    def compile(self,body,decl='n:INTEGER',translator=translate):
        self.script.write_bytes(translator('PROGRAM T VAR '+decl+' BEGIN '+body+' END T').python_source.encode())

    def run_cli(self,*args):return subprocess.run([sys.executable,'-I','-X','utf8','-c',BOOTSTRAP,str(ROOT),str(self.script),*map(str,args)],cwd=self.folder,capture_output=True,text=True)

    def save_config(self,value):self.config.write_bytes((json.dumps(value)+'\n').encode());return self.config

    def test_help_exposes_context_and_state_flags_without_running(self):
        self.compile('n=n+1');result=self.run_cli('--help');self.assertEqual(result.returncode,0,result.stderr);self.assertIn('--context',result.stdout);self.assertIn('--state-out',result.stdout)

    def test_unknown_flags_are_rejected_instead_of_ignored(self):
        self.compile('n=42');result=self.run_cli('--unknown-flag');self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,'');self.assertIn('unrecognized arguments',result.stderr)

    def test_plain_execution_retains_snapshot_stdout(self):
        self.compile('n=42');result=self.run_cli();self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(ast.literal_eval(result.stdout),{'N':42})

    def test_state_output_works_without_any_service_calls_or_initial_context(self):
        self.compile('n=42');result=self.run_cli('--state-out',self.state);self.assertEqual(result.returncode,0,result.stderr)
        saved=json.loads(self.state.read_text());self.assertEqual(saved['variables'],[{'program':'T','path':'N','type':['INTEGER'],'value':42}])

    def test_supplied_global_inputs_are_restored_before_pure_arithmetic(self):
        self.compile('value=x*2',decl='x,value:INTEGER');config={'variables':[{'program':'T','path':'X','type':['INTEGER'],'value':7}]}
        result=self.run_cli('--context',self.save_config(config),'--state-out',self.state);self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(ast.literal_eval(result.stdout),{'X':7,'VALUE':14})

    def test_saved_state_can_be_loaded_and_replaced_for_a_second_run(self):
        self.compile('IF UNINIT(n) THEN n=1 ELSE n=n+1 ENDIF');first=self.run_cli('--state-out',self.state);self.assertEqual(first.returncode,0,first.stderr)
        second=self.run_cli('--context',self.state,'--state-out',self.state);self.assertEqual(second.returncode,0,second.stderr);self.assertEqual(ast.literal_eval(second.stdout),{'N':2});self.assertEqual(json.loads(self.state.read_text())['variables'][0]['value'],2)

    def test_invalid_or_missing_context_rejects_before_execution_and_save(self):
        self.compile('n=42')
        for raw in ('not json','[]','{"unsupported":true}'):
            self.config.write_bytes(raw.encode());result=self.run_cli('--context',self.config,'--state-out',self.state)
            with self.subTest(raw=raw):self.assertEqual(result.returncode,2);self.assertIn('Invalid service context',result.stderr);self.assertFalse(self.state.exists());self.assertEqual(result.stdout,'')
        self.config.unlink();self.assertEqual(self.run_cli('--context',self.config).returncode,2)

    def test_unused_context_banks_are_preserved_on_state_output(self):
        self.compile('n=42');config={'numeric':{'count':1,'values':{'1':7}}};result=self.run_cli('--context',self.save_config(config),'--state-out',self.state)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(self.state.read_text())['numeric'],config['numeric'])

    def test_legacy_strict_entrypoint_retains_its_existing_scope(self):
        self.compile('n=42',translator=legacy_translate);result=self.run_cli();self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(ast.literal_eval(result.stdout),{'N':42})


if __name__=='__main__':unittest.main()
