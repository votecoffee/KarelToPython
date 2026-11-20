"""Authored context-shape, preservation and saved-run preparation contracts."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from karel2py import translate, runner
from karel2py.input_template import prepare_inputs, InputTemplateError


ROOT = Path(__file__).resolve().parents[1]
MISSING = {'uninitialized': True}


def prepare(body, decl='x,n:INTEGER', prefix='', context=None):
    result = translate('PROGRAM T '+prefix+' VAR '+decl+' BEGIN '+body+' END T')
    return prepare_inputs(result.python_source, context=context)


def by_path(prepared):
    return {row['path']: row for row in prepared['template']['bindings']}


def pointer(document, path):
    for token in path.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        document = document[int(token)] if type(document) is list else document[token]
    return document


class InputTemplateTests(unittest.TestCase):
    def test_authored_example_matches_independent_context_shape_fixture(self):
        path=ROOT/'examples/discovery_inputs.kl'
        result=prepare_inputs(translate(path.read_text(encoding='utf-8'),filename=path.name).python_source)
        self.assertEqual(result['context'],json.loads(path.with_suffix('.template.expected.json').read_bytes()))

    def test_selected_record_inputs_make_one_whole_root_without_fabricated_values(self):
        result = prepare('n=a.x+a.y',decl='a:item_t n:INTEGER',prefix='TYPE item_t=STRUCTURE x:INTEGER y:INTEGER ENDSTRUCTURE')
        self.assertEqual(result['context']['variables'],[dict(program='T',path='A',
            type=['STRUCTURE','ITEM_T',[['X',['INTEGER']],['Y',['INTEGER']]]],value=dict(X=MISSING,Y=MISSING))])
        rows = by_path(result)
        self.assertEqual(set(rows),{'A.X','A.Y'})
        self.assertEqual(rows['A.X']['context_pointer'],'/variables/0/value')
        self.assertEqual(rows['A.Y']['selectors'],[['field','Y']])
        self.assertEqual({row['status'] for row in rows.values()},{'missing'})
        self.assertIsNot(result['context']['variables'][0]['value']['X'],result['context']['variables'][0]['value']['Y'])

    def test_shapes_for_multidimensional_named_arrays_and_joint_axes(self):
        result = prepare('n=a[2,1,2]+j[3]',decl='a:ARRAY[2,1]OF pair_t j:JOINTPOS3 n:REAL',
                         prefix='TYPE pair_t=ARRAY[2]OF REAL')
        values = {row['path']:row['value'] for row in result['context']['variables']}
        self.assertEqual(values['A'],[[[MISSING,MISSING]],[[MISSING,MISSING]]])
        self.assertEqual(values['J'],{'axes':[MISSING,MISSING,MISSING]})
        self.assertEqual(by_path(result)['A[2][1][2]']['selectors'],[['index',2],['index',1],['index',2]])

    def test_byte_and_builtin_pose_fields_keep_missing_markers(self):
        result = prepare('n=b+j[1]+p.x',decl='b:BYTE j:JOINTPOS2 p:XYZWPREXT n:REAL')
        values = {row['path']:row['value'] for row in result['context']['variables']}
        self.assertEqual(values['B'],{'unknown_byte':True})
        self.assertEqual(set(values['P']),{'X','Y','Z','W','P','R','CONFIG_DATA','EXT1','EXT2','EXT3'})
        self.assertTrue(all(value==MISSING for value in values['P']['CONFIG_DATA'].values()))

    def test_preserves_existing_case_partial_data_and_unrelated_services(self):
        context={'variables':[dict(program='t',path='a',type=['STRUCTURE','ITEM_T',
            [['X',['INTEGER']],['Y',['INTEGER']]]],value={'x':7,'y':MISSING}),
            dict(program='OTHER',path='KEEP',type='INTEGER',value=9)],
            'numeric':{'count':3,'values':{'1':0.1},'comments':{'1':'keep'}},'files':{'seed.txt':'data'}}
        original=deepcopy(context)
        result=prepare('n=a.x+a.y',decl='a:item_t n:INTEGER',prefix='TYPE item_t=STRUCTURE x:INTEGER y:INTEGER ENDSTRUCTURE',context=context)
        self.assertEqual(result['context'],original)
        self.assertEqual(context,original)
        self.assertEqual(by_path(result)['A.X']['status'],'supplied')
        self.assertEqual(by_path(result)['A.Y']['status'],'missing')
        result['context']['variables'][0]['value']['x']=99
        self.assertEqual(context,original)

    def test_predefined_file_requirement_uses_explicit_context_bindings(self):
        missing = prepare('WRITE OUTPUT(x) CLOSE FILE OUTPUT')
        self.assertNotIn('predefined_files', missing['context'])
        requirements = [row for row in missing['template']['requirements'] if row['code'] == 'service']
        self.assertEqual([(row['service'], row['address']) for row in requirements],
                         [('predefined_files', 'OUTPUT')])
        context = {'predefined_files': {'OUTPUT': {'name': 'out', 'mode': 'WO'}}}
        bound = prepare('WRITE OUTPUT(x) CLOSE FILE OUTPUT', context=context)
        self.assertEqual(bound['context']['predefined_files'], context['predefined_files'])
        self.assertFalse(any(row['code'] == 'service' for row in bound['template']['requirements']))
        self.assertIn('file-transport', {
            row['code'] for row in bound['template']['discovery']['unresolved']
        })

    def test_path_header_and_node_inputs_bind_to_supplied_records(self):
        from karel2py.runner_values import scalar_slot
        from karel2py.structured_inputs import structured_slot

        prefix = ('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                  'header_t=STRUCTURE total:INTEGER ENDSTRUCTURE')
        context = {'variables': [{
            'program': 'T', 'path': 'ROUTE',
            'type': ['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]],
                     ['STRUCTURE', 'HEADER_T', [['TOTAL', ['INTEGER']]]]],
            'value': {'nodes': [{'AMOUNT': MISSING}, {'AMOUNT': 9}], 'data': {'TOTAL': 7}},
        }]}
        result = prepare('WRITE(route[0],route[1].amount)',
                         decl='route:PATH NODEDATA=node_t PATHHEADER=header_t', prefix=prefix, context=context)
        header, node = result['template']['discovery']['inputs']
        bindings = by_path(result)
        self.assertEqual(bindings['ROUTE[0]']['status'], 'supplied')
        self.assertEqual(bindings['ROUTE[1].AMOUNT']['status'], 'missing')
        editable = result['context']
        structured_slot(editable, header, bindings[header['path']]).replace({'TOTAL': 12})
        scalar_slot(editable, node, bindings[node['path']]).set_text('INTEGER', '17')
        self.assertEqual(editable['variables'][0]['value'],
                         {'nodes': [{'AMOUNT': 17}, {'AMOUNT': 9}], 'data': {'TOTAL': 12}})
        self.assertEqual(context['variables'][0]['value']['data'], {'TOTAL': 7})

    def test_missing_path_root_or_node_is_explicit_and_never_allocated(self):
        args = dict(decl='route:PATH NODEDATA=node_t',
                    prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE')
        missing = prepare('WRITE(route[2].amount)', **args)
        self.assertNotIn('variables', missing['context'])
        self.assertEqual(by_path(missing)['ROUTE[2].AMOUNT']['status'], 'unmapped')
        self.assertEqual([row['code'] for row in missing['template']['requirements']], ['path-storage'])
        context = {'variables': [{
            'program': 'T', 'path': 'ROUTE',
            'type': ['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]], None],
            'value': {'nodes': [{'AMOUNT': 7}], 'data': None},
        }]}
        short = prepare('WRITE(route[2].amount)', context=context, **args)
        self.assertEqual(short['context'], context)
        self.assertIsNone(by_path(short)['ROUTE[2].AMOUNT']['context_pointer'])
        self.assertEqual([row['code'] for row in short['template']['requirements']], ['path-storage'])

    def test_path_array_selection_binds_to_the_original_saved_cell(self):
        from karel2py.runner_values import scalar_slot

        node_type = ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]]
        context = {'variables': [{
            'program': 'T', 'path': 'ROUTES',
            'type': ['ARRAY', [1, 2], ['PATH', node_type, None]],
            'value': [[{'nodes': [], 'data': None}, {'nodes': [{'AMOUNT': 7}], 'data': None}]],
        }]}
        result = prepare('WRITE(routes[1,2,1].amount)',
                         decl='routes:ARRAY[1,2] OF PATH NODEDATA=node_t',
                         prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context=context)
        candidate, = result['template']['discovery']['inputs']
        binding = by_path(result)['ROUTES[1][2][1].AMOUNT']
        self.assertEqual(binding['status'], 'supplied')
        scalar_slot(result['context'], candidate, binding).set_text('INTEGER', '31')
        self.assertEqual(result['context']['variables'][0]['value'][0][1]['nodes'], [{'AMOUNT': 31}])

    def test_whole_path_write_discovers_only_read_before_write_records(self):
        from karel2py.input_discovery import discover_inputs
        from karel2py.structured_inputs import structured_slot

        prefix = ('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                  'header_t=STRUCTURE total:INTEGER ENDSTRUCTURE')
        decl = 'route:PATH NODEDATA=node_t PATHHEADER=header_t'
        body = 'route[1].amount=18 WRITE(route)'
        program = translate('PROGRAM T '+prefix+' VAR '+decl+' BEGIN '+body+' END T').python_source
        context = {'variables': [dict(program='t', path='route',
            type=['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]],
                  ['STRUCTURE', 'HEADER_T', [['TOTAL', ['INTEGER']]]]],
            value=dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': 9}], data={'TOTAL': MISSING}))]}

        self.assertFalse(discover_inputs(program)['complete'])
        prepared = prepare_inputs(program, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report)
        header, node = report['inputs']
        bindings = by_path(prepared)
        self.assertEqual(set(bindings), {'ROUTE[0]', 'ROUTE[2]'})
        self.assertEqual(bindings[node['path']]['status'], 'supplied')
        structured_slot(prepared['context'], header, bindings[header['path']]).replace({'TOTAL': 12})
        self.assertEqual(prepared['context']['variables'][0]['value']['data'], {'TOTAL': 12})
        self.assertEqual(context['variables'][0]['value']['data'], {'TOTAL': MISSING})

    def test_whole_path_bank_and_selected_cell_use_exact_saved_shapes(self):
        prefix = 'TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        decl = 'routes:ARRAY[1,2] OF PATH NODEDATA=node_t'
        spec = ['ARRAY', [1, 2], ['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]], None]]
        context = {'variables': [dict(program='T', path='ROUTES', type=spec,
            value=[[dict(nodes=[], data=None), dict(nodes=[{'AMOUNT': 31}], data=None)]])]}
        for body in ('WRITE(routes)', 'WRITE(routes[1,2])'):
            with self.subTest(body=body):
                prepared = prepare(body, decl=decl, prefix=prefix, context=context)
                self.assertTrue(prepared['template']['discovery']['complete'])
                self.assertEqual(set(by_path(prepared)), {'ROUTES[1][2][1]'})
        empty = prepare('WRITE(routes[1,1])', decl=decl, prefix=prefix, context=context)
        self.assertTrue(empty['template']['discovery']['complete'])
        self.assertFalse(by_path(empty))

    def test_whole_path_read_uses_shape_but_still_requires_input_stream(self):
        prefix = 'TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        context = {'variables': [dict(program='T', path='ROUTE',
            type=['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]], None],
            value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare('READ(route) WRITE(route)', decl='route:PATH NODEDATA=node_t',
                           prefix=prefix, context=context)
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], ['input-stream'])
        self.assertEqual(by_path(prepared)['ROUTE[1]']['certainty'], 'conditional')

    def test_saved_path_count_selects_last_record_and_prunes_empty_branch(self):
        prefix = ('TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                  'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE')
        decl = 'routes:ARRAY[2] OF PATH NODEDATA=row_t PATHHEADER=head_t n,unused:INTEGER'
        context = {'variables': [dict(program='T', path='ROUTES',
            type=['ARRAY', 2, ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                               ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]],
            value=[dict(nodes=[], data={'TOTAL': 7}),
                   dict(nodes=[{'AMOUNT': 19}, {'AMOUNT': MISSING}], data={'TOTAL': 9})])]}
        prepared = prepare('IF PATH_LEN(routes[1])=0 THEN '
                           'n=PATH_LEN(routes[2]) WRITE(routes[2][n]) ELSE WRITE(unused) ENDIF',
                           decl=decl, prefix=prefix, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTES[2][2]'})
        self.assertEqual(by_path(prepared)['ROUTES[2][2]']['status'], 'missing')

    def test_path_count_is_unresolved_after_node_mutation(self):
        context = {'variables': [dict(program='T', path='ROUTE',
            type=['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None],
            value=dict(nodes=[{'AMOUNT': 7}, {'AMOUNT': 9}], data=None))]}
        prepared = prepare('DELETE_NODE(route,i,s) n=PATH_LEN(route) '
                           'IF n=1 THEN WRITE(x) ELSE WRITE(y) ENDIF',
                           decl='route:PATH NODEDATA=row_t i,n,s,x,y:INTEGER',
                           prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context=context)
        report = prepared['template']['discovery']
        self.assertIn('path-topology', {row['code'] for row in report['unresolved']})
        self.assertEqual(report['path_storage'][0]['path'], 'ROUTE')
        self.assertEqual(set(by_path(prepared)), {'I', 'N', 'X', 'Y'})
        self.assertEqual(by_path(prepared)['N']['certainty'], 'conditional')

    def test_path_end_edits_update_shapes_and_keep_earlier_saved_inputs(self):
        prefix = 'TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        path = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTES', type=['ARRAY', 2, path],
            value=[dict(nodes=[], data=None), dict(nodes=[{'AMOUNT': MISSING}], data=None)])]}
        prepared = prepare(
            'APPEND_NODE(routes[2],s) n=PATH_LEN(routes[2]) routes[2,n].amount=8 '
            'INSERT_NODE(routes[2],n+1,s) routes[2,3].amount=9 '
            'IF (s=0) AND (PATH_LEN(routes[2])=3) THEN WRITE(routes[2]) ELSE WRITE(unused) ENDIF',
            decl='routes:ARRAY[2] OF PATH NODEDATA=row_t n,s,unused:INTEGER', prefix=prefix, context=context,
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTES[2][1]'})
        self.assertEqual(by_path(prepared)['ROUTES[2][1]']['status'], 'missing')
        self.assertEqual(report['path_storage'], [dict(program='T', path='ROUTES', type=['ARRAY', 2, path])])

    def test_middle_edits_preserve_saved_origins_and_earlier_writes(self):
        from karel2py.structured_inputs import structured_slot

        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        seed = dict(program='T', path='ROUTE', type=spec,
                    value=dict(nodes=[{'AMOUNT': 1}, {'AMOUNT': 2}, {'AMOUNT': MISSING}, {'AMOUNT': MISSING}],
                               data=None))
        prepared = prepare(
            'route[3].amount=18 INSERT_NODE(route,2,s) route[2].amount=20 '
            'DELETE_NODE(route,1,s) DELETE_NODE(route,2,s) '
            'IF (s=0) AND (PATH_LEN(route)=3) THEN WRITE(route[3..1]) ELSE WRITE(unused) ENDIF',
            decl='route:PATH NODEDATA=row_t s,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context={'variables': [seed]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        candidate, = report['inputs']
        self.assertEqual(candidate['path'], 'ROUTE[4]')
        binding = by_path(prepared)[candidate['path']]
        structured_slot(prepared['context'], candidate, binding).replace({'AMOUNT': 44})
        self.assertEqual(prepared['context']['variables'][0]['value']['nodes'],
                         [{'AMOUNT': 1}, {'AMOUNT': 2}, {'AMOUNT': MISSING}, {'AMOUNT': 44}])
        self.assertEqual(seed['value']['nodes'][-1], {'AMOUNT': MISSING})

    def test_unknown_edit_does_not_guess_the_original_slot_of_a_shifted_node(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        seed = dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[{'AMOUNT': 7}], data=None))
        prepared = prepare('INSERT_NODE(route,1,s) INSERT_NODE(route,i,s) WRITE(route[2].amount)',
                           decl='route:PATH NODEDATA=row_t i,s:INTEGER',
                           prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE',
                           context={'variables': [seed]})
        report = prepared['template']['discovery']
        self.assertEqual(set(by_path(prepared)), {'I'})
        self.assertTrue(any('Saved origin of ROUTE[2] is unresolved' in row['message']
                            for row in report['unresolved']), report)

    def test_tail_deletion_drops_old_facts_when_the_index_is_reused(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        seed = dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[{'AMOUNT': 7}], data=None))
        context = {'variables': [seed]}
        prefix = 'TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        decl = 'route:PATH NODEDATA=row_t s:INTEGER'
        prepared = prepare('route[1].amount=11 DELETE_NODE(route,1,s) APPEND_NODE(route,s) WRITE(route)',
                           decl=decl, prefix=prefix, context=context)
        report = prepared['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertEqual({row['code'] for row in report['unresolved']}, {'derived-value'})
        bounds = prepare('DELETE_NODE(route,1,s) WRITE(route[1])', decl=decl, prefix=prefix, context=context)
        gap = bounds['template']['discovery']
        self.assertIn('path-topology', {row['code'] for row in gap['unresolved']})
        self.assertEqual(gap['inputs'], [])

    def test_range_outside_an_edited_path_has_no_partial_candidates(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        seed = dict(program='T', path='ROUTE', type=spec,
                    value=dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': MISSING}], data=None))
        prepared = prepare('DELETE_NODE(route,1,s) WRITE(route[1..2])',
                           decl='route:PATH NODEDATA=row_t s:INTEGER',
                           prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context={'variables': [seed]})
        report = prepared['template']['discovery']
        self.assertEqual(report['inputs'], [])
        self.assertIn('path-topology', {row['code'] for row in report['unresolved']})

    def test_invalid_path_edit_index_preserves_count_and_sets_status(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[], data=None))]}
        prepared = prepare(
            'INSERT_NODE(route,0,s) IF s=2 THEN DELETE_NODE(route,1,s) ENDIF '
            'IF (s=2) AND (PATH_LEN(route)=0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='route:PATH NODEDATA=row_t s,wanted,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context=context,
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_potentially_repeated_end_edit_leaves_topology_unresolved(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[], data=None))]}
        prepared = prepare('REPEAT APPEND_NODE(route,s) UNTIL done WRITE(PATH_LEN(route))',
                           decl='route:PATH NODEDATA=row_t s:INTEGER done:BOOLEAN',
                           prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context=context)
        report = prepared['template']['discovery']
        self.assertEqual(report['path_storage'][0]['path'], 'ROUTE')
        self.assertIn('path-topology', {row['code'] for row in report['unresolved']})

    def test_routine_captured_node_is_not_rebound_after_an_edit(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': 7}], data=None))]}
        program = translate(
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=row_t s:INTEGER '
            'ROUTINE replace(old:row_t) BEGIN DELETE_NODE(route,1,s) APPEND_NODE(route,s) '
            'old.amount=11 END replace '
            'BEGIN replace(route[1]) WRITE(route) END T'
        )
        report = prepare_inputs(program.python_source, context=context)['template']['discovery']
        self.assertFalse(report['complete'])
        self.assertEqual(report['path_storage'][0]['path'], 'ROUTE')
        self.assertIn('path-topology', {row['code'] for row in report['unresolved']})

    def test_whole_path_topology_remains_unresolved_after_unknown_mutation(self):
        prefix = 'TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        path = ['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]], None]
        seed = dict(nodes=[{'AMOUNT': 7}], data=None)
        context = {'variables': [
            dict(program='T', path='ROUTE', type=path, value=seed),
            dict(program='T', path='ROUTES', type=['ARRAY', 1, path], value=[seed]),
        ]}
        decl = 'route:PATH NODEDATA=node_t routes:ARRAY[1] OF PATH NODEDATA=node_t s,i:INTEGER b:BOOLEAN address:STRING[10]'
        for body, unknown in (
            ('INSERT_NODE(route,i,s) WRITE(route)', 'ROUTE'),
            ('routes[i]=route WRITE(routes)', 'ROUTES'),
            ("SET_VAR(i,'',address,route,s) WRITE(route)", 'ROUTE'),
            ('WHILE b DO WRITE(route) DELETE_NODE(route,1,s) ENDWHILE', 'ROUTE'),
        ):
            with self.subTest(body=body):
                prepared = prepare(body, decl=decl, prefix=prefix, context=context)
                report = prepared['template']['discovery']
                self.assertTrue(any(row['code'] == 'schema' and row['message'].endswith(unknown)
                                    for row in report['unresolved']), report)
                self.assertFalse(any(row['root_path'] == unknown for row in report['inputs']))

    def test_whole_path_expansion_enforces_scalar_limit_before_publishing(self):
        prefix = 'TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        context = {'variables': [dict(program='T', path='ROUTE',
            type=['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]], None],
            value=dict(nodes=[{'AMOUNT': 7} for _ in range(1025)], data=None))]}
        prepared = prepare('WRITE(route)', decl='route:PATH NODEDATA=node_t', prefix=prefix, context=context)
        self.assertFalse(prepared['template']['discovery']['complete'])
        self.assertFalse(by_path(prepared))

    def test_existing_root_type_conflicts_are_rejected(self):
        context={'variables':[dict(program='T',path='X',type=['REAL'],value=1.0)]}
        with self.assertRaisesRegex(InputTemplateError,'type differs'):
            prepare('n=x',context=context)

    def test_selected_existing_flat_physical_array_values_are_preserved(self):
        context={'variables':[dict(program='T',path='A',type=['ARRAY',[2,2],['INTEGER']],value=[1,2,3,4])]}
        result=prepare('n=a[2,1]',decl='a:ARRAY[2,2]OF INTEGER n:INTEGER',context=context)
        self.assertEqual(result['context'],context)
        self.assertEqual(by_path(result)['A[2][1]']['status'],'supplied')

    def test_marker_for_entire_existing_aggregate_is_preserved_and_needs_review(self):
        context={'variables':[dict(program='T',path='A',type=['ARRAY',2,['INTEGER']],value=MISSING)]}
        result=prepare('n=a[1]',decl='a:ARRAY[2]OF INTEGER n:INTEGER',context=context)
        self.assertEqual(result['context'],context)
        self.assertEqual(by_path(result)['A[1]']['status'],'missing')

    def test_numeric_string_and_port_inputs_preserve_explicit_bank_values(self):
        context={'numeric':{'count':1,'values':{'1':0.1}},'strings':{'count':1,'values':{'01':'ready'}},
            'ports':{'counts':{'din':1},'values':{'din':{'01':True}}}}
        result=prepare('GET_REG(1,b,n,r,s) GET_STR_REG(1,text,s) b=DIN[1]',
                       decl='b:BOOLEAN n,s:INTEGER r:REAL text:STRING[8]',context=context)
        self.assertEqual(result['context'],context)
        self.assertEqual(result['template']['requirements'],[])
        rows=result['template']['bindings']
        self.assertEqual({row['status'] for row in rows},{'supplied'})
        self.assertEqual({pointer(result['context'],row['context_pointer']) for row in rows},{0.1,'ready',True})

    def test_zero_based_panel_inputs_use_real_bank_bounds_and_value_status(self):
        context = {'ports': {'counts': {'OPIN': 1, 'TPIN': 1, 'WDI': 1, 'WDO': 1},
                             'values': {'OPIN': {'0': False}, 'WDI': {'1': True}}}}
        prepared = prepare('local_flag=OPIN[0] pendant_flag=TPIN[0] WDO[1]=WDI[1]',
                           decl='local_flag,pendant_flag:BOOLEAN', context=context)
        self.assertEqual(prepared['context'], context)
        bindings = by_path(prepared)
        self.assertEqual({key: row['status'] for key, row in bindings.items()},
                         {'OPIN[0]': 'supplied', 'TPIN[0]': 'missing', 'WDI[1]': 'supplied'})
        self.assertEqual(bindings['OPIN[0]']['context_pointer'], '/ports/values/OPIN/0')
        self.assertEqual(bindings['TPIN[0]']['context_pointer'], '/ports/values/TPIN/0')
        self.assertFalse(any(row['code'] == 'service' for row in prepared['template']['requirements']))

    def test_bank_counts_and_values_are_not_invented(self):
        result=prepare('GET_REG(2,b,n,r,s) GET_STR_REG(3,text,s) b=DIN[4]',decl='b:BOOLEAN n,s:INTEGER r:REAL text:STRING[8]')
        self.assertEqual(result['context'],{})
        self.assertEqual({row['status'] for row in result['template']['bindings']},{'unmapped'})
        self.assertEqual(len([row for row in result['template']['requirements'] if row['code']=='service']),3)

    def test_configured_empty_banks_need_values_and_write_only_banks_need_services(self):
        result=prepare('GET_REG(1,b,n,r,s)',decl='b:BOOLEAN n,s:INTEGER r:REAL',context={'numeric':{'count':1,'values':{}}})
        self.assertEqual(by_path(result)['1']['status'],'missing')
        self.assertEqual([row['code'] for row in result['template']['requirements']],['value'])
        result=prepare('SET_INT_REG(4,42,n)')
        self.assertEqual(result['context'],{})
        self.assertEqual(result['template']['bindings'],[])
        self.assertEqual(result['template']['requirements'][0]['service'],'numeric')

    def test_position_groups_and_noncanonical_existing_addresses(self):
        context={'positions':{'count':2,'groups':[3],'values':{'3:02':{'type':['JOINTPOS',2],'value':{'axes':[1.0,2.0]}}}}}
        result=prepare('p=GET_JPOS_REG(2,s,3)',decl='p:JOINTPOS s:INTEGER',context=context)
        row=result['template']['bindings'][0]
        self.assertEqual((row['status'],row['context_pointer']),('supplied','/positions/values/3:02'))
        self.assertEqual(result['template']['requirements'],[])
        result=prepare('p=GET_POS_REG(2,s)',decl='p:XYZWPREXT s:INTEGER',context=context)
        self.assertEqual(result['template']['bindings'][0]['status'],'unmapped')
        self.assertTrue(any(row['code']=='group' for row in result['template']['requirements']))

    def test_dynamic_and_external_gaps_are_kept_in_the_same_document(self):
        result=prepare('n=a[x]',decl='n,x:INTEGER a:ARRAY[3]OF INTEGER')
        self.assertEqual(set(by_path(result)),{'X'})
        self.assertFalse(result['template']['discovery']['complete'])
        self.assertTrue(result['template']['discovery']['unresolved'])

    def test_root_storage_budget_is_shared_and_reports_skipped_roots(self):
        with mock.patch('karel2py.input_template.MAX_LEAVES',2):
            result=prepare('n=a[1]+b[1]',decl='a,b:ARRAY[2]OF INTEGER n:INTEGER')
        self.assertEqual([row['path'] for row in result['context']['variables']],['A'])
        self.assertEqual(by_path(result)['B[1]']['status'],'unmapped')
        self.assertTrue(any(row['code']=='limit' for row in result['template']['requirements']))

    def test_invalid_existing_context_is_rejected(self):
        for context in ({'numeric':{'count':1,'values':{'1':True}}},{'unknown':True}):
            with self.subTest(context=context),self.assertRaises(InputTemplateError):
                prepare('n=x',context=context)

    def test_preparation_never_executes_or_evaluates_target(self):
        source=translate('PROGRAM T VAR x,n:INTEGER BEGIN n=x END T').python_source
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')):
            with mock.patch('builtins.eval',side_effect=AssertionError('evaluated')):
                self.assertEqual(prepare_inputs(source)['context']['variables'][0]['value'],MISSING)


class InputTemplateRunnerTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.folder=Path(folder.name);self.target=self.folder/'converted.py';self.document=self.folder/'session.json'
        self.target.write_bytes(translate('PROGRAM T VAR x,n:INTEGER BEGIN n=x*2 END T').python_source.encode())

    def test_missing_then_edited_inputs_run_and_replay_without_annotation_updates(self):
        prepared=runner.create_document(self.target,self.document,discover=True)
        self.assertEqual(prepared['inputs']['context']['variables'][0]['value'],MISSING)
        self.assertEqual(runner.run_document(self.document)['results']['status'],'failed')
        prepared['inputs']['context']['variables'][0]['value']=21
        self.document.write_bytes((json.dumps(prepared)+'\n').encode())
        for _ in range(2):
            result=runner.run_document(self.document)
            self.assertEqual(result['results']['variables'],{'X':21,'N':42})
            self.assertEqual(result['inputs'],prepared['inputs'])
        self.assertEqual(prepared['inputs']['template']['bindings'][0]['status'],'missing')

    def test_conditional_missing_input_can_remain_when_branch_is_not_taken(self):
        self.target.write_bytes(translate('PROGRAM T VAR flag:BOOLEAN x,n:INTEGER BEGIN IF flag THEN n=x ELSE n=42 ENDIF END T').python_source.encode())
        prepared=runner.create_document(self.target,self.document,discover=True)
        flag=next(row for row in prepared['inputs']['context']['variables'] if row['path']=='FLAG');flag['value']=False
        self.document.write_bytes(json.dumps(prepared).encode())
        result=runner.run_document(self.document)
        self.assertEqual(result['results']['status'],'completed')
        self.assertEqual(result['results']['variables']['N'],42)

    def test_annotations_pin_source_and_malformed_annotations_preserve_document(self):
        prepared=runner.create_document(self.target,self.document,discover=True)
        for edit in ('hash','shape'):
            data=deepcopy(prepared)
            if edit=='hash':data['inputs']['template']['target']['sha256']='0'*64
            else:data['inputs']['template']['bindings']=[42]
            before=json.dumps(data).encode();self.document.write_bytes(before)
            with mock.patch('builtins.exec',side_effect=AssertionError('executed')):
                with self.assertRaisesRegex(runner.RunDocumentError,'Malformed or stale'):
                    runner.run_document(self.document)
            self.assertEqual(self.document.read_bytes(),before)

    def test_target_race_during_discovery_does_not_publish(self):
        inspected=runner._target(self.target)
        read=runner._read
        def changed(path):
            raw=read(path)
            return raw+b'\n# changed\n' if Path(path)==self.target else raw
        with mock.patch.object(runner,'_read',side_effect=changed):
            with mock.patch.object(runner,'_target',return_value=inspected):
                with self.assertRaisesRegex(runner.RunDocumentError,'changed during'):
                    runner.create_document(self.target,self.document,discover=True)
        self.assertFalse(self.document.exists())

    def test_legacy_target_and_non_boolean_flag_fail_without_publication(self):
        with self.assertRaisesRegex(runner.RunDocumentError,'BOOLEAN'):
            runner.create_document(self.target,self.document,discover=1)
        self.target.write_bytes(b'class Program:\n source_program="T"\n translation_mode="pythonic"\n')
        with self.assertRaisesRegex(ValueError,'Re-translate'):
            runner.create_document(self.target,self.document,discover=True)
        self.assertFalse(self.document.exists())

    def test_failed_publication_and_existing_destination_preserve_previous_bytes(self):
        self.document.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):runner.create_document(self.target,self.document,discover=True)
        self.assertEqual(self.document.read_bytes(),b'keep')
        self.document.unlink()
        with mock.patch.object(runner,'atomic_bytes',side_effect=OSError('synthetic failure')):
            with self.assertRaisesRegex(OSError,'synthetic failure'):
                runner.create_document(self.target,self.document,discover=True)
        self.assertFalse(self.document.exists())

    def test_cli_create_from_context_and_runtime_only_preparation(self):
        context=self.folder/'context.json'
        config={'variables':[dict(program='T',path='X',type=['INTEGER'],value=21)]}
        raw=(json.dumps(config)+'\n').encode();context.write_bytes(raw)
        bootstrap='''import runpy,sys
class RuntimeOnly:
 def find_spec(self,fullname,path=None,target=None):
  if fullname in ('karel2py.compiler','karel2py.lexer','karel2py.project','tkinter','_tkinter','karel2py.gui','socket','ssl','http.client','urllib.request'):
   raise ImportError('Preparation needs runtime only')
sys.meta_path.insert(0,RuntimeOnly());sys.path.insert(0,sys.argv[1])
sys.argv=['karel2py.runner','create',sys.argv[2],sys.argv[3],'--discover','--context',sys.argv[4]]
runpy.run_module('karel2py.runner',run_name='__main__')
'''
        process=subprocess.run([sys.executable,'-I','-X','utf8','-c',bootstrap,str(ROOT),str(self.target),str(self.document),str(context)],capture_output=True,text=True,cwd=self.folder)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout),dict(status='prepared',program='T',inputs=1,requirements=0,unresolved=0))
        self.assertEqual(context.read_bytes(),raw)
        saved=json.loads(self.document.read_bytes())
        self.assertEqual(saved['inputs']['context'],config)
        self.assertEqual(runner.run_document(self.document)['results']['variables']['N'],42)


if __name__=='__main__':unittest.main()
