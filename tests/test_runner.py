"""Authored run-document lifecycle, partial results and publication controls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from karel2py import translate
from karel2py import runner


ROOT = Path(__file__).resolve().parents[1]


def inputs(value=21):
    return {'variables':[{'program':'T','path':'X','type':['INTEGER'],'value':value}],
            'numeric':{'count':2,'values':{'1':7}}}


class _RunnerFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='karel2py_runner_')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.target = self.folder/'converted.py'
        self.document = self.folder/'run.json'

    def prepare(self, body='n=x*2', decl='x,n,s:INTEGER', context=None, **limits):
        self.target.write_bytes(translate('PROGRAM T VAR '+decl+' BEGIN '+body+' END T').python_source.encode('utf-8'))
        return runner.create_document(self.target,self.document,context=inputs() if context is None else context,**limits)

    def saved(self):
        return json.loads(self.document.read_text(encoding='utf-8'))


class RunnerTests(_RunnerFixture):
    def test_prepare_inspects_pinned_bytes_without_executing_module(self):
        flag=self.folder/'executed.txt'
        self.target.write_bytes((translate('PROGRAM T BEGIN END T').python_source+
            '\nfrom pathlib import Path\nPath('+repr(str(flag))+').write_text("executed")\n').encode())
        raw=self.target.read_bytes()
        created=runner.create_document(self.target,self.document)
        self.assertFalse(flag.exists())
        self.assertEqual(created['target'],dict(path='converted.py',sha256=hashlib.sha256(raw).hexdigest(),program='T',mode='pythonic'))
        self.assertIsNone(created['results'])
        self.assertEqual(self.target.read_bytes(),raw)
        self.assertEqual(runner.run_document(self.document)['results']['status'],'completed')
        self.assertTrue(flag.exists())

    def test_success_retains_inputs_and_captures_variables_registers_and_text(self):
        original=self.prepare("n=x*2 SET_INT_REG(2,n,s) WRITE('answer=',n,CR)")
        completed=runner.run_document(self.document)
        result=completed['results']
        self.assertEqual(completed['inputs'],original['inputs'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['variables'],dict(X=21,N=42,S=0))
        self.assertEqual(result['context']['numeric']['values'],{'1':7,'2':42})
        self.assertEqual(result['text_output'],'answer= 42\n')
        self.assertIsNone(result['error'])
        self.assertEqual(result['capture_errors'],{})
        self.assertEqual(self.saved(),completed)

    def test_replays_use_original_inputs_and_accept_explicit_edits(self):
        self.prepare('n=x*2 x=x+1')
        first=runner.run_document(self.document)
        second=runner.run_document(self.document)
        self.assertEqual(first['results']['variables'],second['results']['variables'])
        self.assertEqual(second['results']['variables']['X'],22)
        second['inputs']['context']['variables'][0]['value']=5
        self.document.write_text(json.dumps(second),encoding='utf-8')
        self.assertEqual(runner.run_document(self.document)['results']['variables'],dict(X=6,N=10,S={'uninitialized':True}))

    def test_failure_preserves_completed_effects_and_unknown_results(self):
        original=self.prepare("n=x*2 SET_INT_REG(2,n,s) WRITE('done') n=1 DIV 0")
        result=runner.run_document(self.document)
        self.assertEqual(result['inputs'],original['inputs'])
        self.assertEqual(result['results']['status'],'failed')
        self.assertEqual(result['results']['variables'],dict(X=21,N=42,S=0))
        self.assertEqual(result['results']['context']['numeric']['values'],{'1':7,'2':42})
        self.assertEqual(result['results']['text_output'],'done')
        self.assertEqual(result['results']['error']['type'],'KarelRuntimeError')
        self.assertIsInstance(result['results']['error']['line'],int)

    def test_abort_pause_and_stop_have_distinct_terminal_results(self):
        for statement,status in (('ABORT','aborted'),('PAUSE','paused'),('STOP','stopped')):
            with self.subTest(statement=statement):
                target=self.folder/(status+'.py');document=self.folder/(status+'.json')
                target.write_bytes(translate('PROGRAM T VAR n:INTEGER BEGIN n=7 '+statement+' n=99 END T').python_source.encode())
                runner.create_document(target,document)
                result=runner.run_document(document)['results']
                self.assertEqual(result['status'],status)
                self.assertEqual(result['variables'],{'N':7})
                self.assertEqual(result['capture_errors'],{})

    def test_pause_discards_continuation_and_cleans_owned_motion(self):
        config={'motion':{'groups':{'1':2},'capture_only':True},'group_locks':{'groups':[1]}}
        self.prepare('n=7 ATTACH PAUSE n=99',context=config)
        result=runner.run_document(self.document)['results']
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['variables']['N'],7)
        self.assertEqual(result['context']['group_locks']['motion'],{})
        self.assertEqual(result['capture_errors'],{})

    def test_keyboard_interrupt_is_recorded_as_cancelled(self):
        self.prepare(context={})
        self.target.write_bytes(self.target.read_bytes()+b'\nraise KeyboardInterrupt()\n')
        self.document.unlink()
        runner.create_document(self.target,self.document)
        result=runner.run_document(self.document)['results']
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(result['error']['type'],'KeyboardInterrupt')
        self.assertIsNone(result['variables'])

    def test_step_and_output_limits_preserve_partial_state(self):
        for body,limits in (('n=0 WHILE TRUE DO n=n+1 ENDWHILE',{'max_steps':8}),
                            ("n=7 WRITE('too long') n=99",{'max_output_chars':3})):
            with self.subTest(body=body):
                self.target.unlink(missing_ok=True);self.document.unlink(missing_ok=True)
                self.prepare(body,**limits)
                result=runner.run_document(self.document)['results']
                self.assertEqual(result['status'],'failed')
                self.assertIn('limit' if 'max_output_chars' in limits else 'budget',result['error']['message'])
                self.assertNotEqual(result['variables']['N'],{'uninitialized':True})

    def test_saved_file_and_array_values_use_existing_context_contract(self):
        context={'files':{'seed.dat':'42\n'}}
        self.prepare("OPEN FILE f('RO','seed.dat') READ f(n) CLOSE FILE f a[1]=n",
                     decl='f:FILE n:INTEGER a:ARRAY[2]OF INTEGER',context=context)
        result=runner.run_document(self.document)['results']
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['variables']['A'],[42,{'uninitialized':True}])
        self.assertEqual(result['context']['files']['seed.dat'],{'hex':b'42\n'.hex()})

    def test_decimal_register_inputs_keep_pythonic_numeric_mode(self):
        context={'numeric':{'count':2,'values':{'1':0.1}}}
        self.prepare('GET_REG(1,is_real,number,decimal,s) SET_REAL_REG(2,decimal+0.2,s)',
                     decl='is_real:BOOLEAN number,s:INTEGER decimal:REAL',context=context)
        document=runner.run_document(self.document)
        result=document['results']
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['variables']['DECIMAL'],0.1)
        self.assertEqual(result['variables']['NUMBER'],{'uninitialized':True})
        self.assertAlmostEqual(result['context']['numeric']['values']['2'],0.3)
        self.assertEqual(document['inputs']['context'],context)

    def test_changed_source_rejects_before_execution_or_document_write(self):
        self.prepare();before=self.document.read_bytes()
        self.target.write_bytes(self.target.read_bytes()+b'\n# changed\n')
        with self.assertRaisesRegex(runner.RunDocumentError,'target changed'):
            runner.run_document(self.document)
        self.assertEqual(self.document.read_bytes(),before)

    def test_malformed_inputs_reject_before_target_module_execution(self):
        self.prepare();data=self.saved();data['inputs']['context']={'unknown':True}
        self.document.write_text(json.dumps(data),encoding='utf-8');before=self.document.read_bytes()
        with mock.patch('builtins.exec',side_effect=AssertionError('target executed')):
            with self.assertRaisesRegex(runner.RunDocumentError,'Invalid input context'):
                runner.run_document(self.document)
        self.assertEqual(self.document.read_bytes(),before)

    def test_bad_schema_and_limits_preserve_documents(self):
        self.prepare();original=self.saved()
        for change in ({'schema':'unknown'},{'limits':{'max_steps':True,'max_output_chars':1}},
                       {'inputs':{}},{'results':[]},{'target':{'path':'converted.py'}}):
            with self.subTest(change=change):
                data={**original,**change};self.document.write_text(json.dumps(data),encoding='utf-8')
                before=self.document.read_bytes()
                with self.assertRaises(runner.RunDocumentError):runner.run_document(self.document)
                self.assertEqual(self.document.read_bytes(),before)

    def test_json_policy_rejects_duplicates_nonfinite_and_excessive_nesting(self):
        for raw in (b'{"schema":1,"schema":2}',b'{"x":NaN}',b'{"x":1e400}',b'['*2000+b'0'+b']'*2000):
            with self.subTest(raw=raw[:60]):
                self.document.write_bytes(raw)
                with self.assertRaises(runner.RunDocumentError):runner.run_document(self.document)
                self.assertEqual(self.document.read_bytes(),raw)

    def test_create_preserves_existing_reports_and_source_aliases(self):
        self.prepare();before=self.document.read_bytes();source=self.target.read_bytes()
        with self.assertRaises(FileExistsError):runner.create_document(self.target,self.document)
        with self.assertRaises(ValueError):runner.create_document(self.target,self.target)
        self.assertEqual(self.document.read_bytes(),before)
        self.assertEqual(self.target.read_bytes(),source)

    def test_initial_save_failure_does_not_execute_target(self):
        self.prepare();before=self.document.read_bytes()
        with mock.patch('karel2py.storage.os.replace',side_effect=OSError('synthetic write failure')):
            with mock.patch('builtins.exec',side_effect=AssertionError('target executed')):
                with self.assertRaisesRegex(OSError,'synthetic write failure'):runner.run_document(self.document)
        self.assertEqual(self.document.read_bytes(),before)
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()),['converted.py','run.json'])

    def test_final_save_failure_retains_running_marker_and_requires_explicit_resolution(self):
        self.prepare();real=runner.atomic_bytes;calls=[]
        def publish(*args,**kwargs):
            calls.append(1)
            if len(calls)>1:raise OSError('synthetic final write failure')
            return real(*args,**kwargs)
        with mock.patch.object(runner,'atomic_bytes',side_effect=publish):
            with self.assertRaisesRegex(OSError,'synthetic final write failure'):runner.run_document(self.document)
        self.assertEqual(self.saved()['results']['status'],'running')
        before=self.document.read_bytes()
        with self.assertRaisesRegex(runner.RunDocumentError,'running or interrupted'):runner.run_document(self.document)
        self.assertEqual(self.document.read_bytes(),before)

    def test_external_document_edits_are_preserved(self):
        self.prepare()
        self.target.write_bytes(self.target.read_bytes()+(
            '\nfrom pathlib import Path\nPath('+repr(str(self.document))+').write_bytes(b"external edit")\n').encode())
        self.document.unlink();runner.create_document(self.target,self.document)
        with self.assertRaisesRegex(runner.RunDocumentError,'external edits preserved'):runner.run_document(self.document)
        self.assertEqual(self.document.read_bytes(),b'external edit')

    def test_preparation_does_not_mutate_caller_inputs(self):
        config=inputs();before=deepcopy(config)
        self.prepare(context=config)
        runner.run_document(self.document)
        self.assertEqual(config,before)

    def test_aggregate_input_values_remain_independent_of_execution(self):
        config={'variables':[{'program':'T','path':'A','type':['ARRAY',2,['INTEGER']],
                              'value':[1,{'uninitialized':True}]}]}
        self.prepare('a[2]=7 n=a[1]+a[2]',decl='a:ARRAY[2]OF INTEGER n:INTEGER',context=config)
        result=runner.run_document(self.document)
        self.assertEqual(result['results']['variables'],{'A':[1,7],'N':8})
        self.assertEqual(result['inputs']['context'],config)
        self.assertEqual(runner.run_document(self.document)['results']['variables'],{'A':[1,7],'N':8})

    def test_unavailable_context_is_explicit_and_preserves_other_results(self):
        self.prepare("n=7 WRITE('done')")
        with mock.patch.object(runner.rt.ExecutionContext,'to_config',side_effect=ValueError('synthetic unavailable context')):
            result=runner.run_document(self.document)['results']
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['variables']['N'],7)
        self.assertEqual(result['text_output'],'done')
        self.assertIsNone(result['context'])
        self.assertIn('synthetic unavailable',result['capture_errors']['context']['message'])

    def test_runner_retains_translator_accepted_program_identity_lengths(self):
        name='P'*60
        self.target.write_bytes(translate(f'PROGRAM {name} VAR n:INTEGER BEGIN n=42 END {name}').python_source.encode())
        runner.create_document(self.target,self.document)
        self.assertEqual(runner.run_document(self.document)['results']['variables'],{'N':42})

    def test_unsupported_python_target_is_rejected_without_execution(self):
        for text in ('raise AssertionError("executed")','class Program:\n source_program="T"\n translation_mode="strict"',
                     'class Program:\n source_program=unknown()\n translation_mode="pythonic"'):
            with self.subTest(text=text):
                self.target.write_text(text,encoding='utf-8')
                with self.assertRaises(runner.RunDocumentError):runner.create_document(self.target,self.document)
                self.assertFalse(self.document.exists())


class RunnerCliTests(_RunnerFixture):
    def cli(self,*args):
        return subprocess.run([sys.executable,'-m','karel2py.runner',*map(str,args)],capture_output=True,text=True,cwd=ROOT)

    def test_cli_prepare_run_and_replay(self):
        self.target.write_bytes(translate('PROGRAM T VAR n:INTEGER BEGIN n=42 WRITE(n) END T').python_source.encode())
        process=self.cli('create',self.target,self.document)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout)['status'],'prepared')
        for _ in range(2):
            process=self.cli('run',self.document)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(json.loads(process.stdout)['status'],'completed')
            self.assertEqual(self.saved()['results']['text_output'],' 42')

    def test_cli_failure_and_preflight_have_distinct_exit_codes(self):
        self.prepare('n=7 n=1 DIV 0')
        process=self.cli('run',self.document)
        self.assertEqual(process.returncode,1,process.stderr)
        self.assertEqual(json.loads(process.stdout)['status'],'failed')
        self.target.write_bytes(self.target.read_bytes()+b'\n# changed\n')
        before=self.document.read_bytes();process=self.cli('run',self.document)
        self.assertEqual(process.returncode,2)
        self.assertIn('target changed',process.stderr)
        self.assertEqual(self.document.read_bytes(),before)

    def test_cli_version_and_context_input_protection(self):
        from karel2py import __version__
        self.assertEqual(self.cli('--version').stdout.strip(),__version__)
        self.target.write_bytes(translate('PROGRAM T BEGIN END T').python_source.encode())
        config=self.folder/'context.json';config.write_bytes(b'{}\n')
        process=self.cli('create',self.target,config,'--context',config)
        self.assertEqual(process.returncode,2)
        self.assertEqual(config.read_bytes(),b'{}\n')

    def test_runner_cli_requires_no_compiler_gui_or_network_imports(self):
        self.prepare('n=x*2')
        bootstrap='''import runpy,sys
class RuntimeOnly:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.project','tkinter','_tkinter','karel2py.gui','socket','ssl','http.client','urllib.request'):
   raise ImportError('Runner must use runtime only')
sys.meta_path.insert(0,RuntimeOnly());sys.path.insert(0,sys.argv[1])
sys.argv=['karel2py.runner','run',sys.argv[2]]
runpy.run_module('karel2py.runner',run_name='__main__')
'''
        process=subprocess.run([sys.executable,'-I','-X','utf8','-c',bootstrap,str(ROOT),str(self.document)],capture_output=True,text=True,cwd=self.folder)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(self.saved()['results']['variables']['N'],42)


if __name__=='__main__':unittest.main()
