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
    def test_clipped_strings_do_not_prune_a_reachable_initial_read(self):
        report,_=scan("text='abcd' IF text='abc' THEN n=x ELSE n=0 ENDIF",decl='text:STRING[3] n,x:INTEGER')
        self.assertEqual(names(report),{('variable','X'):'conditional'})

    def test_integral_source_coercion_invalidates_uncast_constant_facts(self):
        report,_=scan('n=1.9 IF n=1 THEN n=x ENDIF')
        self.assertEqual(names(report),{('variable','X'):'conditional'})

    def test_real_to_short_missing_sentinel_is_a_derived_gap_not_an_input(self):
        report,_=scan('narrow_value=32767.9 n=narrow_value',decl='narrow_value:SHORT n:INTEGER')
        self.assertEqual(report['inputs'],[])
        self.assertTrue(any(row['code']=='derived-value' for row in report['unresolved']))

    def test_bitwise_constants_keep_integer_addresses_and_branch_truth(self):
        report,_=scan('IF (NOT 1)=0 THEN n=x ELSE n=y ENDIF')
        self.assertEqual(names(report),{('variable','Y'):'required'})
        report,_=scan('n=a[(6 AND 3)]',decl='n:INTEGER a:ARRAY[6]OF INTEGER')
        self.assertEqual(names(report),{('variable','A[2]'):'required'})
        report,_=scan('n=a[(4 OR 2)]',decl='n:INTEGER a:ARRAY[6]OF INTEGER')
        self.assertEqual(names(report),{('variable','A[6]'):'required'})

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

    def test_program_return_removes_inputs_on_terminated_paths(self):
        report, _ = scan('IF TRUE THEN RETURN ENDIF n=x')
        self.assertEqual(report['inputs'], [])
        self.assertTrue(report['complete'])
        report, _ = scan('IF flag THEN RETURN ENDIF n=x')
        self.assertEqual(names(report), {('variable', 'FLAG'): 'required',
                                         ('variable', 'X'): 'conditional'})

    def test_loop_reads_after_possible_program_return_are_conditional(self):
        report, _ = scan('REPEAT IF flag THEN RETURN ENDIF UNTIL x=0')
        self.assertEqual(names(report), {('variable', 'FLAG'): 'required',
                                         ('variable', 'X'): 'conditional'})
        report, _ = scan('FOR i=1 TO 2 DO IF i=1 THEN IF flag THEN RETURN ENDIF '
                         'ELSE n=x ENDIF ENDFOR', decl='i,x,n:INTEGER flag:BOOLEAN')
        self.assertEqual(names(report), {('variable', 'FLAG'): 'required',
                                         ('variable', 'X'): 'conditional'})

    def test_discovery_includes_edge_subscripts_before_boolean_short_circuit(self):
        report, _ = scan('WAIT FOR TRUE OR DIN[x]+')
        self.assertEqual(names(report)[('variable', 'X')], 'required')
        self.assertTrue(any(row['code'] == 'condition-source' for row in report['unresolved']))
        self.assertTrue(any(row['service'] == 'ports' for row in report['context_requirements']))

    def test_discovery_includes_wait_eval_inputs_before_boolean_short_circuit(self):
        report, _ = scan('WAIT FOR TRUE OR EVAL(flag)')
        self.assertEqual(names(report), {('variable', 'FLAG'): 'required'})
        report, _ = scan('WAIT FOR DIN[EVAL(x)]+')
        self.assertEqual(names(report)[('variable', 'X')], 'required')
        self.assertTrue(any(row['service'] == 'ports' for row in report['context_requirements']))

    def test_numbered_pause_wait_reads_its_target_before_boolean_short_circuit(self):
        report, _ = scan('WAIT FOR TRUE OR PAUSE PROGRAM[x]')
        self.assertEqual(names(report), {('variable', 'X'): 'required'})
        self.assertTrue(any(row['service'] == 'tasks' for row in report['context_requirements']))
        self.assertTrue(any(row['code'] == 'condition-source' for row in report['unresolved']))

    def test_notification_wait_reads_code_and_reports_unresolved_delivery(self):
        report, _ = scan('WAIT FOR TRUE OR ERROR[x] OR POWERUP')
        self.assertEqual(names(report), {('variable', 'X'): 'required'})
        self.assertTrue(any(row['service'] == 'errors' for row in report['context_requirements']))
        self.assertEqual(sum(row['code'] == 'condition-source' for row in report['unresolved']), 2)
        wildcard, _ = scan('WAIT FOR ERROR[*]')
        self.assertTrue(any(row['service'] == 'errors' for row in wildcard['context_requirements']))

    def test_repeat_capture_discovery_follows_first_body_and_eager_capture(self):
        report, _ = scan('REPEAT flag=TRUE UNTIL TRUE OR (EVAL(flag) AND EVAL(x>0))')
        self.assertEqual(names(report), {('variable', 'X'): 'required'})
        report, _ = scan('REPEAT RETURN UNTIL EVAL(x>0)')
        self.assertEqual(names(report), {})
        self.assertTrue(report['complete'])

    def test_weld_ports_and_zero_based_panel_ports_are_discovered(self):
        report, _ = scan('flag=WDI[1] WDO[1]=flag b=WDO[1] c=OPIN[0] d=TPIN[0]',
                         decl='flag,b,c,d:BOOLEAN')
        self.assertEqual(names(report), {('port', 'WDI[1]'): 'required',
                                         ('port', 'OPIN[0]'): 'required',
                                         ('port', 'TPIN[0]'): 'required'})
        report, _ = scan('flag=WDI[0]')
        self.assertEqual(names(report), {})
        self.assertTrue(any(row['code'] == 'dynamic-address' for row in report['unresolved']))

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

    def test_explicit_file_open_and_write_discover_source_operands(self):
        report, _ = scan(
            'i=2 OPEN FILE channel[which](mode,endpoint) '
            'WRITE channel[which](samples[i]::width,CR) CLOSE FILE channel[which]',
            decl='channel:ARRAY[2] OF FILE i,which,width:INTEGER '
                 'samples:ARRAY[3] OF INTEGER mode,endpoint:STRING[32]',
        )
        self.assertEqual(names(report), {
            ('variable', 'WHICH'): 'required',
            ('variable', 'MODE'): 'required',
            ('variable', 'ENDPOINT'): 'required',
            ('variable', 'SAMPLES[2]'): 'required',
            ('variable', 'WIDTH'): 'required',
        })
        self.assertEqual(
            {row['code'] for row in report['unresolved']},
            {'dynamic-address', 'file-state', 'file-transport'},
        )

    def test_node_size_queries_schema_without_reading_path_values(self):
        report, _ = scan(
            'i=1 IF NODE_SIZE((routes[i]))=8 THEN n=known ELSE n=unused ENDIF '
            'IF NODE_SIZE(defaults)=64 THEN n=n+standard ELSE n=unused ENDIF WRITE(i,n)',
            decl='routes:ARRAY[2] OF PATH NODEDATA=row_t PATHHEADER=head_t defaults:PATH '
                 'i,n,known,standard,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE axes:JOINTPOS2 ENDSTRUCTURE '
                   'head_t=STRUCTURE text:STRING[9] ENDSTRUCTURE',
        )
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(names(report), {('variable', name): 'required' for name in ('KNOWN', 'STANDARD')})

    def test_node_size_subscript_evaluates_once_before_using_declared_schema(self):
        report, _ = scan(
            'i=1 n=NODE_SIZE(routes[next_index()]) '
            'IF (i=2) AND (n=4) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='routes:ARRAY[3] OF PATH NODEDATA=row_t i,n,wanted,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE count:INTEGER ENDSTRUCTURE',
            routines='ROUTINE next_index:INTEGER BEGIN i=i+1 RETURN i END next_index',
        )
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(names(report), {('variable', 'WANTED'): 'required'})

    def test_node_size_known_schema_with_unknown_cell_still_tracks_subscript(self):
        report, _ = scan(
            'IF NODE_SIZE(routes[i])=4 THEN WRITE(used) ELSE WRITE(unused) ENDIF',
            decl='routes:ARRAY[2] OF PATH NODEDATA=row_t i,used,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE value:INTEGER ENDSTRUCTURE',
        )
        self.assertEqual(names(report), {('variable', name): 'required' for name in ('I', 'USED')})
        self.assertEqual({row['code'] for row in report['unresolved']}, {'dynamic-address'})

    def test_unknown_path_count_does_not_discard_unrelated_write_facts(self):
        report, _ = scan(
            'n=7 i=PATH_LEN(route) WRITE(n,i) IF i>0 THEN WRITE(x) ELSE WRITE(y) ENDIF',
            decl='route:PATH i,n,x,y:INTEGER',
        )
        self.assertEqual({row['code'] for row in report['unresolved']}, {'path-topology'})
        self.assertEqual(names(report), {('variable', name): 'conditional' for name in ('X', 'Y')})

    def test_path_header_field_aliases_share_write_facts(self):
        prefix = ('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                  'header_t=STRUCTURE total:INTEGER ENDSTRUCTURE')
        report, _ = scan(
            'route.total=7 n=route[0].total+route[1].amount',
            decl='route:PATH NODEDATA=node_t PATHHEADER=header_t n:INTEGER', prefix=prefix,
        )
        self.assertEqual(names(report), {('variable', 'ROUTE[1].AMOUNT'): 'required'})
        self.assertEqual(report['inputs'][0]['selectors'], [('index', 1), ('field', 'AMOUNT')])

    def test_analyzes_known_path_ranges_and_runtime_header_index(self):
        report, _ = scan(
            'first=0 WRITE(routes[1][first]) first=2 WRITE channel(routes[1,first..1])',
            decl='channel:FILE routes:ARRAY[1] OF PATH NODEDATA=node_t PATHHEADER=header_t first:INTEGER',
            prefix=('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                    'header_t=STRUCTURE total:INTEGER ENDSTRUCTURE'),
        )
        self.assertEqual(names(report), {
            ('variable', 'ROUTES[1][1]'): 'required',
            ('variable', 'ROUTES[1][2]'): 'required',
            ('variable', 'ROUTES[1][0]'): 'required',
        })

    def test_read_range_does_not_treat_destinations_as_initial_reads(self):
        report, _ = scan('READ(route[1..2]) n=route[2].amount',
                         decl='route:PATH NODEDATA=node_t n:INTEGER',
                         prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE')
        self.assertEqual(names(report), {('variable', 'ROUTE[2].AMOUNT'): 'conditional'})
        self.assertEqual({row['code'] for row in report['unresolved']}, {'input-stream'})

    def test_path_data_discovery_includes_implicit_node_schema_and_named_header(self):
        report, _ = scan(
            "GET_VAR(entry,'','ROUTE[0].TOTAL',n,status) WRITE(route[1].node_pos.location.x)",
            decl='route:PATH PATHHEADER=header_t entry,n,status:INTEGER',
            prefix='TYPE header_t=STRUCTURE total:INTEGER ENDSTRUCTURE',
        )
        self.assertEqual(names(report), {
            ('variable', 'ROUTE[0].TOTAL'): 'required',
            ('variable', 'ROUTE[1].NODE_POS.LOCATION.X'): 'required',
        })

    def test_path_replacement_invalidates_prior_node_value_facts(self):
        report, _ = scan(
            'route[1].amount=0 route=other '
            'IF route[1].amount=0 THEN n=x ELSE n=y ENDIF',
            decl='route,other:PATH NODEDATA=node_t n,x,y:INTEGER',
            prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE',
        )
        self.assertEqual(names(report), {
            ('variable', 'ROUTE[1].AMOUNT'): 'conditional',
            ('variable', 'X'): 'conditional',
            ('variable', 'Y'): 'conditional',
        })

    def test_computed_ordinary_zero_keeps_its_unresolved_node_selection(self):
        report, _ = scan(
            'i=0 n=route[i].amount',
            decl='route:PATH NODEDATA=node_t PATHHEADER=header_t n,i:INTEGER',
            prefix=('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                    'header_t=STRUCTURE total:INTEGER ENDSTRUCTURE'),
        )
        self.assertEqual(report['inputs'], [])
        self.assertIn('selection', {row['code'] for row in report['unresolved']})

    def test_explicit_file_read_discovers_path_bounds_and_format_controls(self):
        report, _ = scan(
            'READ channel[which](route[first..last]::width)',
            decl='channel:ARRAY[2] OF FILE route:PATH NODEDATA=node_t first,last,which,width:INTEGER',
            prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE',
        )
        self.assertEqual(names(report), {
            ('variable', name): 'required' for name in ('WHICH', 'FIRST', 'LAST', 'WIDTH')
        })
        self.assertIn('input-stream', {row['code'] for row in report['unresolved']})
        self.assertIn('selection', {row['code'] for row in report['unresolved']})

    def test_read_captures_later_destination_using_pre_read_index(self):
        report, _ = scan(
            'n=2 READ(n,samples[n]::width) x=samples[2]',
            decl='n,x,width:INTEGER samples:ARRAY[3] OF INTEGER',
        )
        self.assertEqual(names(report), {
            ('variable', 'WIDTH'): 'required', ('variable', 'SAMPLES[2]'): 'conditional',
        })
        self.assertEqual({row['code'] for row in report['unresolved']}, {'input-stream'})

    def test_explicit_predefined_file_is_a_requirement_unless_shadowed(self):
        report, _ = scan('WRITE OUTPUT(x) CLOSE FILE OUTPUT')
        self.assertEqual(names(report), {('variable', 'X'): 'required'})
        self.assertEqual(report['context_requirements'], [
            {'service': 'predefined_files', 'address': 'OUTPUT'},
        ])
        shadowed, _ = scan('READ INPUT(n) CLOSE FILE INPUT', decl='input:FILE n:INTEGER')
        self.assertEqual(shadowed['context_requirements'], [])
        self.assertEqual(shadowed['inputs'], [])

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
