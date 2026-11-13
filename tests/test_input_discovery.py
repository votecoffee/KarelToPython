"""Authored dependency expectations; discovery never executes target Python."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from karel2py import translate
from karel2py.input_contract import module_digest
from karel2py.input_discovery import discover_inputs,InputDiscoveryError


ROOT=Path(__file__).resolve().parents[1]


def scan(body,decl='x,y,n:INTEGER flag:BOOLEAN',prefix='',routines=''):
    result=translate(f'PROGRAM T {prefix} VAR {decl} {routines} BEGIN {body} END T',filename='authored.kl')
    return discover_inputs(result.python_source),result


def names(report):
    return {(row['kind'],row['path']):row['certainty'] for row in report['inputs']}


class InputDiscoveryTests(unittest.TestCase):
    def test_authored_discovery_example_and_independent_execution_fixtures(self):
        from tools.run_examples import run_example
        path=ROOT/'examples/discovery_inputs.kl'
        run_example(path)
        report=discover_inputs(translate(path.read_text(),filename=path.name).python_source)
        summary=[{key:row[key] for key in ('kind','path','certainty')} for row in report['inputs']]
        self.assertEqual(summary,json.loads(path.with_suffix('.inputs.expected.json').read_text()))
        self.assertTrue(report['complete'])

    def test_ordering_compiler_temporaries_and_dead_routines(self):
        report,_=scan('n=x+1 y=2 n=n+y',routines='ROUTINE unused:INTEGER BEGIN RETURN x END unused')
        self.assertEqual(names(report),{('variable','X'):'required'})
        self.assertTrue(report['complete'])

    def test_both_branches_initialize_but_one_branch_does_not(self):
        both,_=scan('IF flag THEN x=1 ELSE x=2 ENDIF n=x')
        one,_=scan('IF flag THEN x=1 ENDIF n=x')
        self.assertEqual(names(both),{('variable','FLAG'):'required'})
        self.assertEqual(names(one),{('variable','FLAG'):'required',('variable','X'):'conditional'})

    def test_literal_conditions_prune_unreachable_dependencies(self):
        report,_=scan('IF FALSE THEN n=x ENDIF WHILE FALSE DO n=y ENDWHILE n=7')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(report['complete'])

    def test_zero_iteration_while_and_at_least_once_repeat(self):
        report,_=scan('WHILE flag DO x=1 ENDWHILE n=x')
        self.assertEqual(names(report),{('variable','FLAG'):'required',('variable','X'):'conditional'})
        report,_=scan('REPEAT x=1 UNTIL flag n=x')
        self.assertEqual(names(report),{('variable','FLAG'):'required'})

    def test_partial_record_and_array_writes_are_independent(self):
        report,_=scan('a.x=1 b[1]=2 n=a.y+b[2]',decl='a:item_t b:ARRAY[2]OF INTEGER n:INTEGER',
                      prefix='TYPE item_t=STRUCTURE x:INTEGER y:INTEGER ENDSTRUCTURE')
        self.assertEqual(names(report),{('variable','A.Y'):'required',('variable','B[2]'):'required'})
        field=next(row for row in report['inputs'] if row['path']=='A.Y')
        self.assertEqual(field['type'],['INTEGER'])
        self.assertEqual(field['root_path'],'A')
        self.assertEqual(field['root_type'][0],'STRUCTURE')

    def test_whole_aggregate_copy_does_not_prove_missing_leaves_ready(self):
        report,_=scan('a[1]=1 b=a n=b[2]',decl='a,b:ARRAY[2]OF INTEGER n:INTEGER')
        self.assertIn(('variable','A'),names(report))
        self.assertNotIn(('variable','B[2]'),names(report))
        self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))
        self.assertFalse(report['complete'])

    def test_fixed_for_visits_each_selected_element_and_clears_counter(self):
        report,_=scan('n=0 FOR i=1 TO 2 DO n=n+a[i] ENDFOR',decl='a:ARRAY[2]OF INTEGER i,n:INTEGER')
        self.assertEqual(names(report),{('variable','A[1]'):'required',('variable','A[2]'):'required'})
        report,_=scan('FOR i=2 TO 1 DO n=x ENDFOR n=i',decl='i,x,n:INTEGER')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))

    def test_dynamic_selectors_and_loop_widening_remain_visible(self):
        report,_=scan('n=a[i]',decl='a:ARRAY[2]OF INTEGER i,n:INTEGER')
        self.assertEqual(names(report),{('variable','I'):'required'})
        self.assertTrue(any(row['code']=='dynamic-address' for row in report['unresolved']))
        report,_=scan('i=1 WHILE flag DO n=a[i] i=i+1 ENDWHILE',decl='a:ARRAY[2]OF INTEGER i,n:INTEGER flag:BOOLEAN')
        self.assertFalse(report['complete'])
        self.assertTrue(any(row['code']=='dynamic-address' for row in report['unresolved']))

    def test_select_merges_writes_and_evaluates_dynamic_labels_first(self):
        report,_=scan('SELECT flag OF CASE(TRUE): x=1 ELSE: x=2 ENDSELECT n=x')
        self.assertEqual(names(report),{('variable','FLAG'):'required'})
        report,_=scan('SELECT 1 OF CASE(label()): n=x ELSE: n=0 ENDSELECT',
                      routines='ROUTINE label:INTEGER BEGIN x=7 RETURN 1 END label')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(report['complete'])

    def test_reference_and_private_value_arguments_have_different_dependencies(self):
        routine='ROUTINE fill(a:INTEGER) BEGIN a=7 END fill'
        reference,_=scan('fill(x) n=x',routines=routine)
        private,_=scan('fill((x)) n=x',routines=routine)
        self.assertEqual(reference['inputs'],[])
        self.assertEqual(names(private),{('variable','X'):'required'})

    def test_unused_borrowed_parameter_is_not_a_value_read(self):
        routine='ROUTINE answer(a:INTEGER):INTEGER BEGIN RETURN 42 END answer'
        report,_=scan('n=answer(x)',routines=routine)
        self.assertEqual(report['inputs'],[])
        report,_=scan('n=answer((x))',routines=routine)
        self.assertEqual(names(report),{('variable','X'):'required'})

    def test_aliases_and_multiple_returns_propagate_callee_writes(self):
        routine='ROUTINE fill(a:INTEGER) BEGIN IF flag THEN a=1 RETURN ENDIF a=2 END fill'
        report,_=scan('fill(x) n=x',routines=routine)
        self.assertEqual(names(report),{('variable','FLAG'):'required'})

    def test_for_cleanup_applies_to_callee_return_paths(self):
        routine='ROUTINE once:INTEGER BEGIN FOR i=1 TO 2 DO RETURN i ENDFOR RETURN 0 END once'
        report,_=scan('n=once() n=n+i',decl='i,n:INTEGER',routines=routine)
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='derived-value' and 'I' in row['message'] for row in report['unresolved']))

    def test_fresh_local_reads_and_external_recursion_are_not_fake_global_inputs(self):
        report,_=scan('n=bad()',routines='ROUTINE bad:INTEGER VAR v:INTEGER BEGIN RETURN v END bad')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='local-value' for row in report['unresolved']))
        report,_=scan('n=host(x)',routines='ROUTINE host(a:INTEGER):INTEGER FROM LIB')
        self.assertFalse(report['complete'])
        report,_=scan('n=recurse(x)',routines='ROUTINE recurse(a:INTEGER):INTEGER BEGIN RETURN recurse(a) END recurse')
        self.assertFalse(report['complete'])
        self.assertTrue(any(row['code']=='routine' for row in report['unresolved']))

    def test_ports_and_register_banks_keep_address_and_write_order(self):
        report,_=scan('flag=DIN[1] DOUT[2]=flag flag=DOUT[2] GET_REG(1,flag,x,r,s)',decl='flag:BOOLEAN x,s:INTEGER r:REAL')
        self.assertEqual(names(report),{('port','DIN[1]'):'required',('numeric_register','1'):'required'})
        self.assertTrue(report['context_requirements'])
        report,_=scan('SET_INT_REG(1,42,s) GET_REG(1,flag,x,r,s)',decl='flag:BOOLEAN x,s:INTEGER r:REAL')
        self.assertEqual(report['inputs'],[])

    def test_string_and_grouped_position_registers_are_reported(self):
        report,_=scan('GET_STR_REG(1,text,s) p=GET_POS_REG(2,s,3)',decl='text:STRING[10] s:INTEGER p:XYZWPREXT')
        self.assertEqual(set(names(report)),{('string_register','1'),('position_register','2[group=3]')})
        point=next(row for row in report['inputs'] if row['kind']=='position_register')
        self.assertEqual((point['index'],point['group']),(2,3))
        self.assertTrue(report['complete'])

    def test_dynamic_position_groups_stay_explicit_and_json_serializable(self):
        report,_=scan('p=GET_POS_REG(2,s,g)',decl='g,s:INTEGER p:XYZWPREXT')
        self.assertEqual(names(report),{('variable','G'):'required'})
        self.assertFalse(report['complete'])
        self.assertTrue(any(row['code']=='dynamic-address' for row in report['unresolved']))
        json.dumps(report,allow_nan=False)

    def test_get_var_uses_static_own_global_paths_and_status_is_an_output(self):
        report,_=scan("entry=0 GET_VAR(entry,'T','a.y',n,s)",decl='entry,n,s:INTEGER a:item_t',
                      prefix='TYPE item_t=STRUCTURE x:INTEGER y:INTEGER ENDSTRUCTURE')
        self.assertEqual(names(report),{('variable','A.Y'):'required'})

    def test_uninit_and_array_len_are_metadata_probes(self):
        report,_=scan('flag=UNINIT(x) n=ARRAY_LEN(a)',decl='x,n:INTEGER a:ARRAY[2]OF INTEGER flag:BOOLEAN')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(report['complete'])

    def test_read_requires_a_provider_and_does_not_read_its_output_first(self):
        report,_=scan('READ(n)')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='input-stream' for row in report['unresolved']))

    def test_unknown_control_cannot_hide_reads_after_skipped_writes(self):
        report,_=scan('GOTO chosen x=1 chosen:: n=x')
        self.assertIn(('variable','X'),names(report))
        self.assertFalse(report['complete'])

    def test_source_and_python_locations_survive_includes(self):
        result=translate('PROGRAM T\n%INCLUDE defs.inc\nBEGIN\n%INCLUDE body.inc\nEND T',filename='main.kl',
                         includes={'defs.inc':'VAR x,n:INTEGER','body.inc':'n=1\nn=x'})
        report=discover_inputs(result.python_source)
        location=report['inputs'][0]['locations'][0]
        self.assertEqual((location['file'],location['line']),('body.inc',2))
        self.assertTrue(location['python_lines'])
        self.assertTrue(any("get('X'" in result.python_source.splitlines()[line-1] for line in location['python_lines']))


class ContractTests(unittest.TestCase):
    def test_empty_type_parameter_fields_do_not_change_cross_minor_fingerprints(self):
        _,result=scan('n=x');tree=ast.parse(result.python_source);real=ast.iter_fields
        def older(node):return [(key,value) for key,value in real(node) if key!='type_params']
        def newer(node):
            fields=list(older(node))
            if isinstance(node,(ast.FunctionDef,ast.ClassDef)):fields.append(('type_params',[]))
            return fields
        with mock.patch('ast.iter_fields',side_effect=older):old=module_digest(tree)
        with mock.patch('ast.iter_fields',side_effect=newer):new=module_digest(tree)
        self.assertEqual(old,new)

    def test_discovery_never_executes_or_evaluates_target_python(self):
        _,result=scan('n=x')
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')):
            with mock.patch('builtins.eval',side_effect=AssertionError('evaluated')):
                self.assertEqual(names(discover_inputs(result.python_source)),{('variable','X'):'required'})

    def test_payload_and_execution_edits_invalidate_the_contract(self):
        _,result=scan('n=x')
        changed=result.python_source.replace("self._state.reference('N', 1).set", "self._state.reference('X', 1).set")
        self.assertNotEqual(changed,result.python_source)
        with self.assertRaisesRegex(InputDiscoveryError,'execution syntax changed'):discover_inputs(changed)
        changed=result.python_source.replace("'status': 'available'","'status': 'edited'",1)
        with self.assertRaisesRegex(InputDiscoveryError,'payload changed'):discover_inputs(changed)

    def test_comments_change_byte_identity_but_not_semantic_fingerprint(self):
        report,result=scan('n=x')
        changed=discover_inputs(result.python_source+'\n# note\n')
        self.assertEqual(changed['inputs'],report['inputs'])
        self.assertNotEqual(changed['target']['sha256'],report['target']['sha256'])

    def test_analysis_budgets_do_not_block_translation_or_claim_complete(self):
        with mock.patch('karel2py.input_contract.MAX_NODES',1):result=translate('PROGRAM T VAR n:INTEGER BEGIN n=42 END T')
        report=discover_inputs(result.python_source)
        self.assertFalse(report['complete'])
        namespace={'__name__':'authored'};exec(result.python_source,namespace)
        self.assertEqual(namespace['Program']().run(),{'N':42})
        _,result=scan('n=x+y')
        with mock.patch('karel2py.input_discovery.MAX_STEPS',1):report=discover_inputs(result.python_source)
        self.assertFalse(report['complete'])

    def test_legacy_or_unmarked_python_requires_retranslation(self):
        with self.assertRaises(InputDiscoveryError):discover_inputs('class Program: pass')


class DiscoveryCliTests(unittest.TestCase):
    def test_discovery_cli_needs_no_compiler_gui_network_or_target_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);target=folder/'converted.py'
            _,result=scan('n=x');target.write_bytes(result.python_source.encode())
            bootstrap='''import runpy,sys
class RuntimeOnly:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.project','tkinter','_tkinter','karel2py.gui','socket','ssl','http.client','urllib.request'):
   raise ImportError('Discovery must not import compiler, GUI or network')
sys.meta_path.insert(0,RuntimeOnly());sys.path.insert(0,sys.argv[1])
sys.argv=['karel2py.runner','discover',sys.argv[2]]
runpy.run_module('karel2py.runner',run_name='__main__')
'''
            process=subprocess.run([sys.executable,'-I','-X','utf8','-c',bootstrap,str(ROOT),str(target)],capture_output=True,text=True,cwd=folder)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(names(json.loads(process.stdout)),{('variable','X'):'required'})

    def test_cli_report_and_existing_output_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);target=folder/'converted.py';output=folder/'inputs.report.json'
            _,result=scan('n=x');target.write_bytes(result.python_source.encode())
            command=[sys.executable,'-m','karel2py.runner','discover',str(target),'--output',str(output)]
            process=subprocess.run(command,capture_output=True,text=True,cwd=ROOT)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(json.loads(process.stdout),dict(complete=True,inputs=1,unresolved=0))
            saved=output.read_bytes();report=json.loads(saved)
            self.assertEqual(report['target']['sha256'],hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertEqual(names(report),{('variable','X'):'required'})
            process=subprocess.run(command,capture_output=True,text=True,cwd=ROOT)
            self.assertEqual(process.returncode,2)
            self.assertEqual(output.read_bytes(),saved)


if __name__=='__main__':unittest.main()
