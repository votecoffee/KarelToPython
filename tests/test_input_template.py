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

    def test_fresh_path_header_has_an_editable_shape_without_nodes(self):
        from karel2py.structured_inputs import structured_slot

        prefix = ('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                  'header_t=STRUCTURE total:INTEGER name:STRING[8] ENDSTRUCTURE')
        prepared = prepare('WRITE(route)', decl='route:PATH NODEDATA=node_t PATHHEADER=header_t', prefix=prefix)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        candidate, = report['inputs']
        binding, = prepared['template']['bindings']
        self.assertEqual((candidate['path'], binding['status']), ('ROUTE[0]', 'missing'))
        root, = prepared['context']['variables']
        self.assertEqual(root['value'], {'nodes': [], 'data': {'TOTAL': MISSING, 'NAME': MISSING}})
        structured_slot(prepared['context'], candidate, binding).replace({'TOTAL': 12, 'NAME': 'Run A'})
        self.assertEqual(root['value'], {'nodes': [], 'data': {'TOTAL': 12, 'NAME': 'Run A'}})

    def test_missing_path_bank_header_can_be_edited_with_unmapped_node_input(self):
        from karel2py.runner_values import scalar_slot

        prefix = ('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                  'header_t=STRUCTURE total:INTEGER ENDSTRUCTURE '
                  'route_t=PATH NODEDATA=node_t PATHHEADER=header_t')
        prepared = prepare('WRITE(routes[1,1,2].amount,routes[2,2,0].total)',
                           decl='routes:ARRAY[2,2] OF route_t', prefix=prefix)
        bindings = by_path(prepared)
        node, header = prepared['template']['discovery']['inputs']
        self.assertEqual(bindings[node['path']]['status'], 'unmapped')
        self.assertEqual(bindings[header['path']]['status'], 'missing')
        self.assertIn('path-storage', {row['code'] for row in prepared['template']['requirements']})
        scalar_slot(prepared['context'], header, bindings[header['path']]).set_text('INTEGER', '17')
        bank = prepared['context']['variables'][0]['value']
        self.assertEqual([item['nodes'] for row in bank for item in row], [[], [], [], []])
        self.assertEqual([item['data']['TOTAL'] for row in bank for item in row], [MISSING, MISSING, MISSING, 17])

    def test_fresh_path_bank_header_shape_counts_against_template_limit(self):
        prefix = ('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                  'header_t=STRUCTURE total:INTEGER ENDSTRUCTURE '
                  'route_t=PATH NODEDATA=node_t PATHHEADER=header_t')
        with mock.patch('karel2py.input_template.MAX_LEAVES', 7):
            result = prepare('WRITE(routes[2,2,0].total)', decl='routes:ARRAY[2,2] OF route_t', prefix=prefix)
        self.assertNotIn('variables', result['context'])
        self.assertEqual(by_path(result)['ROUTES[2][2][0].TOTAL']['status'], 'unmapped')
        self.assertEqual([row['code'] for row in result['template']['requirements']], ['limit'])

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

    def test_fresh_path_can_be_copied_and_grown_without_a_context_seed(self):
        prefix = 'TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t'
        decl = 'source,target:route_t s,n,unused:INTEGER'
        prepared = prepare(
            'COPY_PATH(source,0,0,target,s) '
            'IF (s=0) AND (PATH_LEN(target)=0) THEN APPEND_NODE(target,s) '
            'target[PATH_LEN(target)].amount=n WRITE(target) ELSE WRITE(unused) ENDIF',
            decl=decl, prefix=prefix,
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'N'})
        self.assertNotIn('path_storage', report)
        self.assertEqual([row['path'] for row in prepared['context']['variables']], ['N'])

    def test_wrong_type_context_root_does_not_establish_a_default_shape(self):
        prefix = 'TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        prepared = prepare(
            'IF PATH_LEN(route)=0 THEN WRITE(empty) ELSE WRITE(nonempty) ENDIF',
            decl='route:PATH NODEDATA=row_t empty,nonempty:INTEGER', prefix=prefix,
            context={'variables': [dict(program='T', path='ROUTE', type='INTEGER', value=1)]},
        )
        report = prepared['template']['discovery']
        self.assertIn('path-topology', {row['code'] for row in report['unresolved']})
        self.assertEqual(set(by_path(prepared)), {'EMPTY', 'NONEMPTY'})
        self.assertNotIn('path_storage', report)

    def test_fresh_empty_path_write_has_no_fields_and_read_requires_records(self):
        prefix = 'TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t'
        for selector in ('routes', 'routes[2]'):
            with self.subTest(selector=selector):
                decl = 'routes:ARRAY[2] OF route_t'
                written = prepare(f'WRITE({selector},CR)', decl=decl, prefix=prefix)
                report = written['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(report['inputs'], [])
                read = prepare(f'READ({selector})', decl=decl, prefix=prefix)
                report = read['template']['discovery']
                self.assertEqual(report['inputs'], [])
                self.assertTrue(any(row['message'] == 'PATH READ requires an existing header or node'
                                    for row in report['unresolved']))

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

    def test_copy_path_selects_shifted_saved_inputs_and_creates_destination_shape(self):
        types = ('TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE')
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]
        source = dict(program='T', path='SOURCE', type=spec,
                      value=dict(nodes=[{'AMOUNT': MISSING} for _ in range(4)], data={'TOTAL': MISSING}))
        prepared = prepare(
            'source.total=7 source[4].amount=19 DELETE_NODE(source,1,s) '
            'COPY_PATH(source,3,2,target,s) IF (s=0) AND (PATH_LEN(target)=2) '
            'THEN WRITE(target[1],target.total) ELSE WRITE(unused) ENDIF',
            decl='source,target:PATH NODEDATA=row_t PATHHEADER=head_t s,unused:INTEGER',
            prefix=types, context={'variables': [source]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'SOURCE[3]'})
        self.assertEqual(report['path_storage'], [dict(program='T', path='SOURCE', type=spec)])
        self.assertEqual(prepared['context']['variables'], [source])

    def test_self_copy_captures_source_after_status_selector_effects(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=row_t PATHHEADER=head_t codes:ARRAY[1] OF INTEGER wanted,unused:INTEGER '
            'ROUTINE slot:INTEGER BEGIN route[2].amount=19 route.total=7 RETURN 1 END slot '
            'BEGIN route[1].amount=5 route[2].amount=9 route.total=2 '
            'COPY_PATH(route,2,1,route,codes[slot()]) '
            'IF (route[1].amount=19) AND (route[2].amount=5) AND (route[0].total=7) AND (codes[1]=0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING} for _ in range(2)], data={'TOTAL': MISSING}))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_copy_path_preserves_incomplete_data_without_guessing_destination_inputs(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='SOURCE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare('COPY_PATH(source,0,0,target,s) WRITE(target[1])',
                           decl='source,target:PATH NODEDATA=row_t s:INTEGER',
                           prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context=context)
        report = prepared['template']['discovery']
        self.assertEqual(set(by_path(prepared)), {'SOURCE[1]'})
        self.assertIn('derived-value', {row['code'] for row in report['unresolved']})

    def test_copy_path_rejects_invalid_bounds_before_reading_saved_records(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='SOURCE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare(
            'COPY_PATH(source,2,1,target,s) IF s=2 THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='source,target:PATH NODEDATA=row_t s,wanted,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context=context,
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_copy_path_converts_only_selected_records_of_a_routine_result(self):
        source = (
            'PROGRAM T TYPE from_n=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'to_n=STRUCTURE amount:BYTE ENDSTRUCTURE '
            'from_h=STRUCTURE total:REAL ENDSTRUCTURE to_h=STRUCTURE total:INTEGER ENDSTRUCTURE '
            'p1=PATH NODEDATA=from_n PATHHEADER=from_h p2=PATH NODEDATA=to_n PATHHEADER=to_h '
            'VAR b:p2 s:ARRAY[1] OF INTEGER seq,wanted,unused,seed:INTEGER '
            'ROUTINE build:p1 VAR p:p1 status:INTEGER '
            'BEGIN seq=seq*10+1 APPEND_NODE(p,status) APPEND_NODE(p,status) APPEND_NODE(p,status) '
            'p.total=9.75 p[1].amount=256 p[2].amount=seed p[3].amount=8 RETURN p END build '
            'ROUTINE first:INTEGER BEGIN seq=seq*10+2 RETURN 3 END first '
            'ROUTINE last:INTEGER BEGIN seq=seq*10+3 RETURN 2 END last '
            'ROUTINE slot:INTEGER BEGIN seq=seq*10+4 seed=99 RETURN 1 END slot '
            'ROUTINE flag:BOOLEAN BEGIN seq=seq*10+5 RETURN TRUE END flag '
            'BEGIN seq=0 seed=7 COPY_PATH(build(),first(),last(),b,s[slot()],flag()) '
            'IF (seq=12345) AND (s[1]=0) AND (PATH_LEN(b)=2) AND (b.total=9) '
            'AND (b[1].amount=8) AND (b[2].amount=7) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        report = prepare_inputs(translate(source).python_source)
        self.assertTrue(report['template']['discovery']['complete'], report['template']['discovery']['unresolved'])
        self.assertEqual(set(by_path(report)), {'WANTED'})

    def test_copy_path_converts_known_mixed_scalar_config_and_position_fields(self):
        source = (
            'PROGRAM T TYPE from_node=STRUCTURE score:REAL joints:JOINTPOS2 word:INTEGER pose:XYZWPR ENDSTRUCTURE '
            'to_node=STRUCTURE score:INTEGER joints:JOINTPOS3 word:CONFIG pose:XYZWPREXT ENDSTRUCTURE '
            'from_path=PATH NODEDATA=from_node to_path=PATH NODEDATA=to_node '
            'VAR a:from_path b:to_path s,wanted,unused:INTEGER '
            'BEGIN APPEND_NODE(a,s) a[1].score=42.75 a[1].joints[1]=11 a[1].joints[2]=12 a[1].word=4111 '
            'a[1].pose.x=1 a[1].pose.y=2 a[1].pose.z=3 a[1].pose.w=0 a[1].pose.p=0 a[1].pose.r=0 '
            'a[1].pose.config_data.cfg_turn_no1=0 a[1].pose.config_data.cfg_turn_no2=0 '
            'a[1].pose.config_data.cfg_turn_no3=0 a[1].pose.config_data.cfg_flip=FALSE '
            'a[1].pose.config_data.cfg_left=FALSE a[1].pose.config_data.cfg_up=FALSE '
            'a[1].pose.config_data.cfg_front=FALSE COPY_PATH(a,0,0,b,s,TRUE) '
            'IF (s=0) AND (b[1].score=42) AND (b[1].joints[3]=0) '
            'AND (b[1].word.cfg_turn_no1=-1) AND b[1].word.cfg_flip '
            'AND (b[1].pose.z=3) AND (b[1].pose.ext1=0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})
        self.assertFalse(report['context_requirements'])

    def test_copy_path_keeps_missing_config_word_and_known_array_element(self):
        source = (
            'PROGRAM T TYPE row_a=STRUCTURE bits:CONFIG amount:REAL ENDSTRUCTURE '
            'row_b=STRUCTURE bits:INTEGER amount:INTEGER ENDSTRUCTURE '
            'grid_a=ARRAY[2] OF row_a node_a=STRUCTURE data:ARRAY[2] OF grid_a ENDSTRUCTURE '
            'node_b=STRUCTURE data:ARRAY[2,2] OF row_b ENDSTRUCTURE '
            'p1=PATH NODEDATA=node_a p2=PATH NODEDATA=node_b VAR a:p1 b:p2 s,wanted,unused:INTEGER '
            'BEGIN APPEND_NODE(a,s) a[1].data[2,1].amount=-4.75 '
            'COPY_PATH(a,0,0,b,s,TRUE) '
            'IF (b[1].data[2,1].amount=-4) AND UNINIT(b[1].data[2,1].bits) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_narrowing_with_known_nonzero_axis_fails_before_destination_selector(self):
        source = (
            'PROGRAM T TYPE from_n=STRUCTURE axes:JOINTPOS2 ENDSTRUCTURE '
            'to_n=STRUCTURE axes:JOINTPOS1 ENDSTRUCTURE p1=PATH NODEDATA=from_n p2=PATH NODEDATA=to_n '
            'VAR a:p1 b:ARRAY[1] OF p2 s,unused:INTEGER value_input:REAL '
            'ROUTINE pick:INTEGER BEGIN WRITE(unused) RETURN 1 END pick '
            'BEGIN APPEND_NODE(a,s) a[1].axes[1]=value_input a[1].axes[2]=2 '
            'b[pick()]=a WRITE(unused) END T'
        )
        report = prepare_inputs(translate(source).python_source)['template']['discovery']
        self.assertEqual([row['path'] for row in report['inputs']], ['VALUE_INPUT'])
        unresolved, = report['unresolved']
        self.assertEqual(unresolved['code'], 'path-conversion')
        self.assertIn('zero discarded axes', unresolved['message'])

    def test_rejected_path_data_conversion_stops_later_reads(self):
        source = (
            'PROGRAM T TYPE from_n=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'to_n=STRUCTURE amount:BYTE ENDSTRUCTURE '
            'p1=PATH NODEDATA=from_n p2=PATH NODEDATA=to_n '
            'VAR a:p1 b:ARRAY[1] OF p2 s,unused:INTEGER '
            'ROUTINE slot:INTEGER BEGIN WRITE(unused) RETURN 1 END slot '
            'BEGIN APPEND_NODE(a,s) a[1].amount=256 s=99 {} WRITE(unused) END T'
        )
        for statement in ('COPY_PATH(a,0,0,b[1],s,TRUE)', 'b[slot()]=a'):
            with self.subTest(statement=statement):
                report = prepare_inputs(translate(source.format(statement)).python_source)['template']['discovery']
                self.assertFalse(report['inputs'])
                unresolved, = report['unresolved']
                self.assertEqual(unresolved['code'], 'path-conversion')
                self.assertIn('BYTE value outside', unresolved['message'])

    def test_scalar_variable_transfer_uses_capture_order_and_checked_values(self):
        source = (
            'PROGRAM T VAR source,out:REAL target:SHORT entry,wanted,unused:INTEGER codes:ARRAY[2] OF INTEGER '
            'ROUTINE set_slot:INTEGER BEGIN source=99.75 RETURN 1 END set_slot '
            'ROUTINE get_slot:INTEGER BEGIN target=17 RETURN 2 END get_slot '
            "BEGIN source=42.75 SET_VAR(entry,'','target',(source),codes[set_slot()]) "
            'IF target<>42 THEN WRITE(unused) ENDIF '
            "GET_VAR(entry,'T','target',out,codes[get_slot()]) "
            'IF (codes[1]=0) AND (codes[2]=0) AND (out=17) AND (source=99.75) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_variable_transfer_preserves_raw_scalar_and_record_missing_data(self):
        declarations = ('source:SHORT target:INTEGER src:src_t dst:dst_t '
                        'entry,s,wanted,unused:INTEGER')
        types = ('TYPE src_t=STRUCTURE amount:REAL missing:SHORT ENDSTRUCTURE '
                 'dst_t=STRUCTURE amount:INTEGER missing:INTEGER ENDSTRUCTURE')
        for body in (
            "source=32767 target=7 GET_VAR(entry,'','source',target,s) "
            'IF (s=12311) AND UNINIT(target) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            "source=32767 target=7 SET_VAR(entry,'','target',(source),s) "
            'IF (s=12311) AND UNINIT(target) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            "src.amount=19.75 src.missing=32767 SET_VAR(entry,'','dst',src,s) "
            'IF (s=12311) AND (dst.amount=19) AND UNINIT(dst.missing) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
        ):
            with self.subTest(body=body):
                prepared = prepare(body, decl=declarations, prefix=types)
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_named_data_array_row_preserves_other_rows_and_converts_record_fields(self):
        prepared = prepare(
            "a[1,1].amount=42.75 a[1,2].amount=19.9 b[1,1].amount=7 "
            "SET_VAR(entry,'','b[2]',a[1],s) "
            'IF (s=0) AND (b[2,1].amount=42) AND (b[2,2].amount=19) AND (b[1,1].amount=7) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='a:ARRAY[2,2] OF r1 b:ARRAY[2,2] OF r2 entry,s,wanted,unused:INTEGER',
            prefix='TYPE r1=STRUCTURE amount:REAL ENDSTRUCTURE r2=STRUCTURE amount:INTEGER ENDSTRUCTURE',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_variable_transfer_rejection_and_invalid_conversion_keep_later_reads_separate(self):
        prepared = prepare(
            "entry=88 target=7 SET_VAR(entry,'','target',TRUE,s) "
            'IF (s=3) AND (entry=88) AND (target=7) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='target,entry,s,wanted,unused:INTEGER',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

        report = prepare(
            "entry=88 s=99 target=7 SET_VAR(entry,'','target',256,s) WRITE(unused)",
            decl='target:BYTE entry,s,unused:INTEGER',
        )['template']['discovery']
        self.assertFalse(report['inputs'])
        unresolved, = report['unresolved']
        self.assertEqual(unresolved['code'], 'variable-conversion')
        self.assertIn('BYTE value outside', unresolved['message'])

    def test_variable_array_transfer_discovers_only_the_transferred_source_prefix(self):
        for transfer in ("GET_VAR(entry,'','a',b,s)", "SET_VAR(entry,'','b',a,s)"):
            with self.subTest(transfer=transfer):
                prepared = prepare(
                    'a[1]=7 '+transfer+' WRITE(b[1])',
                    decl='a:ARRAY[4] OF INTEGER b:ARRAY[2] OF INTEGER entry,s:INTEGER',
                )
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'A[2]'})

    def test_unequal_variable_array_set_captures_before_later_selector(self):
        source = (
            'PROGRAM T VAR a:ARRAY[4] OF INTEGER b:ARRAY[2] OF INTEGER '
            'codes:ARRAY[1] OF INTEGER entry,wanted,unused:INTEGER '
            'ROUTINE slot:INTEGER BEGIN a[1]=99 RETURN 1 END slot '
            "BEGIN a[1]=5 a[2]=7 SET_VAR(entry,'','b',a,codes[slot()]) "
            'IF (codes[1]=0) AND (a[1]=99) AND (b[1]=5) AND (b[2]=7) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_variable_array_transfer_changes_row_boundaries_and_keeps_unused_tail(self):
        prepared = prepare(
            "a[1,1]=11 a[1,2]=12 a[2,1]=21 a[2,2]=22 b[1,5]=99 GET_VAR(entry,'','a',b,s) "
            'IF (s=0) AND (b[1,3]=21) AND (b[1,4]=22) AND (b[1,5]=99) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='a:ARRAY[2,2] OF INTEGER b:ARRAY[1,5] OF INTEGER entry,s,wanted,unused:INTEGER',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_detached_converted_array_prefix_preserves_missing_status(self):
        source = (
            'PROGRAM T VAR b:ARRAY[1,4] OF INTEGER entry,s,wanted,unused:INTEGER '
            'ROUTINE build:ARRAY[2,1] OF SHORT VAR a:ARRAY[2,1] OF SHORT '
            'BEGIN a[1,1]=7 a[2,1]=32767 RETURN a END build '
            "BEGIN b[1,3]=99 SET_VAR(entry,'','b',build(),s) "
            'IF (s=12311) AND (b[1,1]=7) AND UNINIT(b[1,2]) AND (b[1,3]=99) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_variable_array_rank_rejection_and_late_conversion_error(self):
        prepared = prepare(
            "entry=88 b[1]=7 SET_VAR(entry,'','b',a,s) "
            'IF (s=3) AND (entry=88) AND (b[1]=7) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='a:ARRAY[1,2] OF INTEGER b:ARRAY[3] OF INTEGER entry,s,wanted,unused:INTEGER',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

        report = prepare(
            "a[1]=5 a[2]=256 SET_VAR(entry,'','b',a,s) WRITE(unused)",
            decl='a:ARRAY[2] OF INTEGER b:ARRAY[3] OF BYTE entry,s,unused:INTEGER',
        )['template']['discovery']
        self.assertFalse(report['inputs'])
        unresolved, = report['unresolved']
        self.assertEqual(unresolved['code'], 'variable-conversion')
        self.assertIn('BYTE value outside', unresolved['message'])

    def test_named_path_scalar_transfers_track_capture_order_and_missing_values(self):
        source = (
            'PROGRAM T TYPE node_t=STRUCTURE amount:SHORT ENDSTRUCTURE '
            'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=node_t PATHHEADER=head_t '
            'VAR route:route_t bank:ARRAY[1] OF route_t source,out:REAL '
            'entry,s,wanted,unused:INTEGER codes:ARRAY[2] OF INTEGER '
            'ROUTINE set_slot:INTEGER BEGIN source=99.75 RETURN 1 END set_slot '
            'ROUTINE get_slot:INTEGER BEGIN route[1].amount=17 RETURN 2 END get_slot '
            'BEGIN APPEND_NODE(route,s) APPEND_NODE(bank[1],s) source=42.75 '
            "GET_VAR(entry,'','bank[1][1].amount',route.total,s) "
            'IF (s<>12311) OR (NOT UNINIT(route.total)) THEN WRITE(unused) ENDIF '
            "SET_VAR(entry,'','route[1].amount',source,codes[set_slot()]) "
            'IF route[1].amount<>42 THEN WRITE(unused) ENDIF '
            "GET_VAR(entry,'T','route[1].amount',out,codes[get_slot()]) "
            "SET_VAR(entry,'','bank[1,0].total',out,s) "
            'IF (codes[1]=0) AND (codes[2]=0) AND (s=0) '
            'AND (bank[1].total=17) AND (source=99.75) AND (PATH_LEN(bank[1])=1) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_named_path_fields_discover_the_saved_origin_after_delete(self):
        types = 'TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        spec = ['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]], None]
        route = dict(program='T', path='ROUTE', type=spec,
                     value=dict(nodes=[{'AMOUNT': 5}, {'AMOUNT': MISSING}], data=None))
        prepared = prepare(
            "DELETE_NODE(route,1,s) GET_VAR(entry,'','route[1].amount',out,s) "
            "SET_VAR(entry,'','route[1].amount',10,s) "
            'IF (s=0) AND (route[1].amount=10) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='route:PATH NODEDATA=node_t entry,out,s,wanted,unused:INTEGER',
            prefix=types, context={'variables': [route]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[2].AMOUNT', 'WANTED'})
        self.assertEqual(by_path(prepared)['ROUTE[2].AMOUNT']['selectors'], [['index', 2], ['field', 'AMOUNT']])
        self.assertEqual(report['path_storage'], [dict(program='T', path='ROUTE', type=spec)])

    def test_named_missing_path_records_and_bad_indices_leave_outputs_unchanged(self):
        types = ('TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE')
        declarations = ('route:PATH NODEDATA=node_t PATHHEADER=head_t '
                        'other:PATH entry,out,s,wanted,unused:INTEGER')
        spec = ['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]
        route = dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[MISSING], data=MISSING))
        for address in ('route.total', 'route[1].amount', 'route[2].amount',
                        'route[1][1].amount', 'other[0].total'):
            for transfer in ('GET_VAR', 'SET_VAR'):
                with self.subTest(address=address, transfer=transfer):
                    prepared = prepare(
                        f"entry=88 out=42 {transfer}(entry,'T','{address}',out,s) "
                        'IF (s=1) AND (entry=88) AND (out=42) '
                        'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
                        decl=declarations, prefix=types, context={'variables': [route]},
                    )
                    report = prepared['template']['discovery']
                    self.assertTrue(report['complete'], report['unresolved'])
                    self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_nested_named_path_fields_and_array_prefixes_follow_definite_values(self):
        types = ('TYPE item_t=STRUCTURE amount:SHORT axes:JOINTPOS2 grid:ARRAY[2,3] OF INTEGER ENDSTRUCTURE '
                 'node_t=STRUCTURE item:item_t ENDSTRUCTURE head_t=STRUCTURE item:item_t ENDSTRUCTURE')
        prepared = prepare(
            'APPEND_NODE(route,s) route[1].item.grid[2,3]=19 source[1]=7 source[2]=8 '
            "SET_VAR(entry,'','route[1].item.amount',42.75,s) "
            "SET_VAR(entry,'','route.item.axes[2]',12.5,s) "
            "SET_VAR(entry,'','route[1].item.grid[2]',source,s) "
            "GET_VAR(entry,'T','route[1].item.grid[2]',received,s) "
            "GET_VAR(entry,'','route[0].item.axes[2]',route[1].item.axes[1],s) "
            "GET_VAR(entry,'','route[1].item.amount',out,s) "
            'IF (s=0) AND (out=42) AND (route[1].item.axes[1]=12.5) '
            'AND (received[1]=7) AND (received[2]=8) AND (received[3]=19) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl=('route:PATH NODEDATA=node_t PATHHEADER=head_t source:ARRAY[2] OF INTEGER '
                  'received:ARRAY[3] OF INTEGER entry,s,out,wanted,unused:INTEGER'),
            prefix=types,
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_nested_named_path_selected_addresses_keep_saved_origins(self):
        types = ('TYPE item_t=STRUCTURE samples:ARRAY[2] OF INTEGER ENDSTRUCTURE '
                 'node_t=STRUCTURE item:item_t ENDSTRUCTURE')
        spec = ['PATH', ['STRUCTURE', 'NODE_T', [
            ['ITEM', ['STRUCTURE', 'ITEM_T', [['SAMPLES', ['ARRAY', 2, ['INTEGER']]]]]],
        ]], None]
        route = dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[
            {'ITEM': {'SAMPLES': [3, 4]}}, {'ITEM': {'SAMPLES': [5, MISSING]}},
        ], data=None))
        prepared = prepare(
            "DELETE_NODE(route,1,s) GET_VAR(entry,'','route[1].item.samples[2]',out,s) "
            "SET_VAR(entry,'','route[1].item.samples[2]',8,s) "
            'IF (s=0) AND (route[1].item.samples[2]=8) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='route:PATH NODEDATA=node_t entry,s,out,wanted,unused:INTEGER', prefix=types,
            context={'variables': [route]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[2].ITEM.SAMPLES[2]', 'WANTED'})
        self.assertEqual(by_path(prepared)['ROUTE[2].ITEM.SAMPLES[2]']['selectors'],
                         [['index', 2], ['field', 'ITEM'], ['field', 'SAMPLES'], ['index', 2]])

    def test_nested_named_path_rejects_missing_ancestors_and_bad_coordinate_shapes(self):
        types = ('TYPE item_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'node_t=STRUCTURE item:item_t grid:ARRAY[2,2] OF item_t ENDSTRUCTURE')
        item = ['STRUCTURE', 'ITEM_T', [['AMOUNT', ['INTEGER']]]]
        spec = ['PATH', ['STRUCTURE', 'NODE_T', [
            ['ITEM', item], ['GRID', ['ARRAY', [2, 2], item]],
        ]], None]
        route = dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[
            {'ITEM': MISSING, 'GRID': [{'AMOUNT': 7}, MISSING, {'AMOUNT': 8}, {'AMOUNT': 9}]},
        ], data=None))
        for address in ('route[1].item.amount', 'route[1].grid[1,2].amount',
                        'route[1].grid[2].amount', 'route[1].grid[3,1].amount'):
            with self.subTest(address=address):
                prepared = prepare(
                    f"entry=88 out=42 GET_VAR(entry,'T','{address}',out,s) "
                    'IF (s=1) AND (entry=88) AND (out=42) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
                    decl='route:PATH NODEDATA=node_t entry,s,out,wanted,unused:INTEGER',
                    prefix=types, context={'variables': [route]},
                )
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_nested_named_path_does_not_reuse_shape_after_a_partial_aggregate_write(self):
        source = (
            'PROGRAM T TYPE item_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'node_t=STRUCTURE item:item_t ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=node_t entry,s,out,wanted,unused:INTEGER '
            'ROUTINE update VAR value:item_t BEGIN '
            "SET_VAR(entry,'','route[1].item',value,s) END update "
            'BEGIN APPEND_NODE(route,s) route[1].item.amount=7 update '
            "GET_VAR(entry,'','route[1].item.amount',out,s) "
            'IF s=0 THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        report = prepare_inputs(translate(source).python_source)['template']['discovery']
        self.assertFalse(report['complete'])
        self.assertTrue(any(row['code']=='path-topology' for row in report['unresolved']), report)
        self.assertEqual({row['path'] for row in report['inputs']}, {'WANTED', 'UNUSED'})

    def test_whole_named_path_nodes_and_headers_preserve_partial_scalar_data(self):
        types = ('TYPE row_t=STRUCTURE amount:INTEGER flag:BOOLEAN ENDSTRUCTURE '
                 'route_t=PATH NODEDATA=row_t PATHHEADER=row_t')
        prepared = prepare(
            'APPEND_NODE(route,s) APPEND_NODE(copy_route,s) route[1].amount=42 '
            "SET_VAR(entry,'','route[0]',route[1],s) "
            'IF (s<>12311) OR (route.amount<>42) THEN WRITE(unused) ENDIF '
            "GET_VAR(entry,'','route[0]',copy_route[1],s) "
            'IF (s<>12311) OR (NOT UNINIT(copy_route[1].flag)) THEN WRITE(unused) ENDIF '
            "GET_VAR(entry,'','copy_route[1]',received,s) "
            'IF (s=12311) AND (received.amount=42) AND UNINIT(received.flag) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='route,copy_route:route_t received:row_t entry,s,wanted,unused:INTEGER', prefix=types,
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_named_path_record_copies_keep_checked_values_and_argument_order(self):
        source = (
            'PROGRAM T TYPE src_t=STRUCTURE amount:REAL ENDSTRUCTURE '
            'row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route:route_t source:src_t received:row_t entry,s,wanted,unused:INTEGER codes:ARRAY[2] OF INTEGER '
            'ROUTINE set_status:INTEGER BEGIN source.amount=99.75 RETURN 1 END set_status '
            'ROUTINE get_status:INTEGER BEGIN route[1].amount=17 RETURN 2 END get_status '
            'BEGIN APPEND_NODE(route,s) source.amount=42.75 '
            "SET_VAR(entry,'','route[1]',source,codes[set_status()]) "
            'IF route[1].amount<>42 THEN WRITE(unused) ENDIF '
            "GET_VAR(entry,'','route[1]',route[0],codes[get_status()]) "
            "GET_VAR(entry,'','route[0]',received,s) "
            'IF (codes[1]=0) AND (codes[2]=0) AND (s=0) AND (received.amount=17) AND (source.amount=99.75) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_whole_named_path_node_read_keeps_original_saved_address(self):
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        route = dict(program='T', path='ROUTE', type=['PATH', row, None],
                     value=dict(nodes=[{'AMOUNT': 5}, {'AMOUNT': MISSING}], data=None))
        prepared = prepare(
            "DELETE_NODE(route,1,s) GET_VAR(entry,'','route[1]',out,s)",
            decl='route:PATH NODEDATA=row_t out:row_t entry,s:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context={'variables': [route]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[2]'})
        self.assertEqual(by_path(prepared)['ROUTE[2]']['selectors'], [['index', 2]])

    def test_get_var_whole_node_receiver_follows_a_previously_shifted_borrowed_slot(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t seed:row_t s,entry,wanted,unused:INTEGER '
            'ROUTINE update(v:route_t;held:row_t) BEGIN INSERT_NODE(v,1,s) '
            "GET_VAR(entry,'','seed',held,s) "
            'IF (s=0) AND (v[1].amount=42) AND (v[2].amount=7) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END update '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 seed.amount=42 update(route,route[1]) END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_get_var_whole_node_status_selector_can_insert_before_captured_slot(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t seed:row_t entry,s,wanted,unused:INTEGER statuses:ARRAY[1] OF INTEGER '
            'ROUTINE insert_first BEGIN INSERT_NODE(route,1,s) END insert_first '
            'ROUTINE slot:INTEGER BEGIN insert_first RETURN 1 END slot '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 seed.amount=42 '
            "GET_VAR(entry,'','seed',route[1],statuses[slot()]) "
            'IF (statuses[1]=0) AND (route[1].amount=42) AND (route[2].amount=7) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_get_var_whole_node_reports_unproved_compound_status_selector_edits(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t seed:row_t entry,s:INTEGER statuses:ARRAY[1] OF INTEGER '
            'ROUTINE slot:INTEGER BEGIN INSERT_NODE(route,1,s) RETURN 1 END slot '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 seed.amount=42 '
            "GET_VAR(entry,'','seed',route[1],statuses[slot()+0]) END T"
        )
        report = prepare_inputs(translate(source).python_source)['template']['discovery']
        self.assertFalse(report['complete'])
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']), report)

    def test_variable_transfer_overlap_checks_follow_operand_and_lookup_order(self):
        common = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route:route_t bank:ARRAY[2] OF route_t receiver:row_t '
            'entry,early,wanted,late:INTEGER seed:row_t '
            'ROUTINE named:STRING[32] BEGIN WRITE(early) RETURN \'route[9]\' END named '
            'BEGIN APPEND_NODE(route,entry) route[1].amount=7 route.amount=13 '
            'APPEND_NODE(bank[2],entry) bank[2,1].amount=11 '
        )
        cases = (
            ("GET_VAR(entry,'',named(),route,route.amount)", {'EARLY'}, 'Service output'),
            ("GET_VAR(entry,'','route',bank[2],bank[2,1].amount)", set(), 'Service output'),
            ("GET_VAR(entry,'','bank',bank,bank[2,1].amount)", set(), 'Service output'),
            ("GET_VAR(entry,'',named(),receiver,entry)", {'EARLY'}, 'Service output'),
            ("SET_VAR(entry,'','route[1]',seed,route[1].amount)", {'SEED'}, 'SET_VAR target overlaps'),
            ("SET_VAR(entry,'','bank',bank,bank[2,1].amount)", {'BANK[1][0]', 'BANK[2][0]'}, 'SET_VAR target overlaps'),
            ("SET_VAR(entry,'','route[9]',7,route[1].amount) IF route[1].amount=1 THEN WRITE(wanted) ENDIF",
             {'WANTED', 'LATE'}, None),
        )
        for statement, expected, message in cases:
            with self.subTest(statement=statement):
                source = common + statement + ' WRITE(late) END T'
                prepared = prepare_inputs(translate(source).python_source)
                report = prepared['template']['discovery']
                self.assertEqual(set(by_path(prepared)), expected)
                if message is None:
                    self.assertTrue(report['complete'], report['unresolved'])
                else:
                    self.assertEqual([row['code'] for row in report['unresolved']], ['service-output'])
                    self.assertIn(message, report['unresolved'][0]['message'])

    def test_named_path_transfer_uses_capture_and_lookup_order_across_selector_edits(self):
        common = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement,target:route_t seed:row_t entry,s,wanted,unused:INTEGER statuses:ARRAY[1] OF INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) RETURN 1 END swap '
            "ROUTINE owner_name:STRING[8] BEGIN COPY_PATH(replacement,0,0,route,s) RETURN '' END owner_name "
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 '
            'APPEND_NODE(replacement,s) replacement[1].amount=13 seed.amount=17 '
        )
        for statement, condition in (
            ("GET_VAR(route[1].amount,'','replacement',route,statuses[swap()])",
             '(PATH_LEN(route)=1) AND (route[1].amount=13) AND (statuses[1]=0)'),
            ("GET_VAR(route[1].amount,owner_name(),'replacement',route,s)",
             '(PATH_LEN(route)=1) AND (route[1].amount=13) AND (s=0)'),
            ("GET_VAR(entry,'','route',target,statuses[swap()])",
             '(PATH_LEN(target)=1) AND (target[1].amount=13) AND (statuses[1]=0)'),
            ("SET_VAR(entry,'','target',route,statuses[swap()])",
             '(PATH_LEN(target)=1) AND (target[1].amount=7) AND (route[1].amount=13) AND (statuses[1]=0)'),
            ("SET_VAR(route[1].amount,'','route[1]',seed,statuses[swap()])",
             '(PATH_LEN(route)=1) AND (route[1].amount=17) AND (statuses[1]=0)'),
        ):
            with self.subTest(statement=statement):
                source = common + f'{statement} IF {condition} THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
                prepared = prepare_inputs(translate(source).python_source)
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_get_var_status_selector_copy_path_keeps_old_node_slot(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement:route_t seed:row_t entry,s,wanted,unused:INTEGER statuses:ARRAY[1] OF INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) RETURN 1 END swap '
            'ROUTINE observe(whole:row_t;field:INTEGER) BEGIN '
            "GET_VAR(entry,'','seed',whole,statuses[swap()]) "
            'IF (statuses[1]=0) AND (whole.amount=42) AND (field=42) AND (route[1].amount=13) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END observe '
            'BEGIN APPEND_NODE(route,s) APPEND_NODE(replacement,s) '
            'route[1].amount=7 replacement[1].amount=13 seed.amount=42 '
            'observe(route[1],route[1].amount) END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_later_argument_copy_path_keeps_captured_node_and_header_slots(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,replacement:route_t s,wanted,unused:INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) RETURN s END swap '
            'ROUTINE observe(whole_node,whole_header:row_t;node_field,header_field,code:INTEGER) BEGIN '
            'whole_node.amount=41 whole_header.amount=42 '
            'IF (code=0) AND (node_field=41) AND (header_field=42) '
            'AND (route[1].amount=13) AND (route.amount=23) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END observe '
            'BEGIN APPEND_NODE(route,s) APPEND_NODE(replacement,s) '
            'route[1].amount=7 route.amount=8 replacement[1].amount=13 replacement.amount=23 '
            'observe(route[1],route[0],route[1].amount,route.amount,swap()) END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_path_descriptor_replacement_keeps_evaluated_raw_values(self):
        common = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement,target:route_t s,dummy,wanted,unused:INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) RETURN 1 END swap '
            'ROUTINE choose(n:INTEGER;ignored:INTEGER):INTEGER BEGIN RETURN n END choose '
            'ROUTINE observe(earlier:INTEGER;held:row_t) BEGIN held.amount=41 '
            'IF (earlier=41) AND (route[1].amount=13) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END observe '
            'BEGIN APPEND_NODE(route,s) APPEND_NODE(replacement,s) '
            'route[1].amount=7 replacement[1].amount=13 dummy=1 '
        )
        for statement in (
            'COPY_PATH(route,choose(dummy,swap()),1,target,s) '
            'IF (s=0) AND (target[1].amount=7) AND (route[1].amount=13) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            'IF (route[choose(dummy,swap())].amount=7) AND (route[1].amount=13) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            'observe(route[1].amount,route[choose(dummy,swap())])',
            'COPY_PATH(route,swap(),1,target,s) '
            'IF (s=0) AND (target[1].amount=7) AND (route[1].amount=13) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            'IF (route[swap()].amount=7) AND (route[1].amount=13) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
        ):
            with self.subTest(statement=statement):
                prepared = prepare_inputs(translate(common + statement + ' END T').python_source)
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_path_array_index_and_selected_transfer_follow_lowered_order(self):
        common = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR routes:ARRAY[1] OF route_t replacement:route_t s,dummy,wanted,unused:INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,routes[1],s) RETURN 1 END swap '
            'ROUTINE choose(n:INTEGER;ignored:INTEGER):INTEGER BEGIN RETURN n END choose '
            'BEGIN APPEND_NODE(routes[1],s) APPEND_NODE(replacement,s) '
            'routes[1,1].amount=7 routes[1].amount=8 replacement[1].amount=13 replacement.amount=23 dummy=1 '
        )
        for selector, value in (
            ('routes[1,choose(dummy,swap())]', 13),
            ('routes[1][choose(dummy,swap())]', 13),
        ):
            with self.subTest(selector=selector):
                source = common + (
                    f'IF {selector}.amount={value} THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
                )
                prepared = prepare_inputs(translate(source).python_source)
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'WANTED'})

        source = common + 'WRITE(routes[1,choose(dummy,swap())]) END T'
        report = prepare_inputs(translate(source).python_source)['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])

        source = common + 'READ(routes[1,choose(dummy,swap())]) END T'
        report = prepare_inputs(translate(source).python_source)['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], ['input-stream'])

    def test_copy_path_sees_edits_before_and_after_detaching_the_source_descriptor(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,replacement,target:route_t s,dummy,wanted,unused:INTEGER '
            'ROUTINE swap(held:row_t):INTEGER BEGIN INSERT_NODE(route,1,s) route[1].amount=12 '
            'COPY_PATH(replacement,0,0,route,s) held.amount=17 RETURN 0 END swap '
            'ROUTINE choose(n:INTEGER;ignored:INTEGER):INTEGER BEGIN RETURN n END choose '
            'BEGIN APPEND_NODE(route,s) APPEND_NODE(replacement,s) '
            'route[1].amount=7 route.amount=8 replacement[1].amount=13 replacement.amount=23 dummy=0 '
            'COPY_PATH(route,choose(dummy,swap(route[1])),0,target,s) '
            'IF (s=0) AND (PATH_LEN(target)=2) AND (target[1].amount=17) AND (target[2].amount=7) '
            'AND (target.amount=8) AND (route[1].amount=13) AND (route.amount=23) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_copy_path_checks_saved_storage_of_replaced_raw_source(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement,target:route_t s,dummy,wanted,unused:INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) RETURN 1 END swap '
            'ROUTINE choose(n:INTEGER;ignored:INTEGER):INTEGER BEGIN RETURN n END choose '
            'BEGIN APPEND_NODE(replacement,s) replacement[1].amount=13 dummy=1 '
            'COPY_PATH(route,choose(dummy,swap()),1,target,s) '
            'IF (s=0) AND (PATH_LEN(target)=1) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        python = translate(source).python_source
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        route = dict(program='T', path='ROUTE', type=['PATH', row, None])
        ready = dict(route, value=dict(nodes=[{'AMOUNT': 71}], data=None))
        prepared = prepare_inputs(python, context={'variables': [ready]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1]', 'WANTED'})
        self.assertEqual(prepared['context']['variables'][0]['value'], ready['value'])

        missing = dict(route, value=dict(nodes=[MISSING], data=None))
        report = prepare_inputs(python, context={'variables': [missing]})['template']['discovery']
        self.assertFalse(report['complete'])
        self.assertTrue(any('COPY_PATH layout' in row['message'] for row in report['unresolved']), report)

    def test_copy_path_uses_live_source_nodes_after_in_place_argument_edit(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,target:route_t s,dummy,wanted,unused:INTEGER '
            'ROUTINE shift:INTEGER BEGIN INSERT_NODE(route,1,s) route[1].amount=13 RETURN 1 END shift '
            'ROUTINE choose(n,ignored:INTEGER):INTEGER BEGIN RETURN n END choose '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 dummy=0 '
            'COPY_PATH(route,choose(dummy,shift()),0,target,s) '
            'IF (s=0) AND (PATH_LEN(target)=2) AND (target[1].amount=13) AND (target[2].amount=7) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_argument_copy_path_requires_materialized_source_records(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement:route_t s:INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) RETURN s END swap '
            'ROUTINE observe(whole:row_t;code:INTEGER) BEGIN WRITE(whole.amount) END observe '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 observe(route[1],swap()) END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        replacement = dict(program='T', path='REPLACEMENT', type=['PATH', row, None],
                           value=dict(nodes=[MISSING], data=None))
        report = prepare_inputs(translate(source).python_source,
                                context={'variables': [replacement]})['template']['discovery']
        self.assertFalse(report['complete'])
        self.assertTrue(any('COPY_PATH layout' in row['message'] for row in report['unresolved']), report)

    def test_later_argument_deletes_node_and_preserves_slot_and_field_identity(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t s,wanted,unused:INTEGER '
            'ROUTINE remove_first(v:route_t):INTEGER BEGIN DELETE_NODE(v,1,s) RETURN s END remove_first '
            'ROUTINE observe(whole:row_t;held,code:INTEGER) BEGIN '
            'IF (code=0) AND (held=7) AND (whole.amount=13) THEN '
            'held=19 whole.amount=42 '
            'IF (held=19) AND (route[1].amount=42) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF '
            'ELSE WRITE(unused) ENDIF END observe '
            'BEGIN APPEND_NODE(route,s) APPEND_NODE(route,s) route[1].amount=7 route[2].amount=13 '
            'observe(route[1],route[1].amount,remove_first(route)) END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_captured_node_slot_remains_unresolved_when_argument_leaves_it_vacant(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t s:INTEGER '
            'ROUTINE remove_first:INTEGER BEGIN DELETE_NODE(route,1,s) RETURN s END remove_first '
            'ROUTINE observe(whole:row_t;code:INTEGER) BEGIN WRITE(whole.amount) END observe '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 observe(route[1],remove_first()) END T'
        )
        report = prepare_inputs(translate(source).python_source)['template']['discovery']
        self.assertFalse(report['complete'])
        self.assertTrue(any('Captured PATH slot is out of bounds' in row['message']
                            for row in report['unresolved']), report)

    def test_wholly_missing_scalar_path_record_can_clear_and_reinitialize_a_record(self):
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        path = ['PATH', row, row]
        initial = dict(program='T', path='ROUTE', type=path,
                       value=dict(nodes=[MISSING], data={'AMOUNT': 9}))
        prepared = prepare(
            "GET_VAR(entry,'','route[1]',out,s) "
            'IF s<>12311 THEN WRITE(unused) ENDIF '
            "SET_VAR(entry,'','route[0]',out,s) "
            'IF s<>12311 THEN WRITE(unused) ENDIF '
            "entry=88 GET_VAR(entry,'','route.amount',n,s) "
            'IF (s<>1) OR (entry<>88) THEN WRITE(unused) ENDIF '
            "seed.amount=42 GET_VAR(entry,'','seed',route[1],s) "
            'IF s<>0 THEN WRITE(unused) ENDIF '
            "SET_VAR(entry,'','route[0]',route[1],s) "
            "GET_VAR(entry,'','route[0].amount',n,s) "
            'IF (s=0) AND (n=42) AND (route[1].amount=42) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='route:route_t out,seed:row_t entry,s,n,wanted,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=row_t',
            context={'variables': [initial]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1]', 'WANTED'})
        self.assertEqual(report['path_storage'], [dict(program='T', path='ROUTE', type=path)])

    def test_wholly_missing_path_array_header_is_distinct_from_missing_bank_node(self):
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        bank = dict(program='T', path='BANK', type=['ARRAY', 1, ['PATH', row, row]],
                    value=[dict(nodes=[MISSING], data=MISSING)])
        prepared = prepare(
            "GET_VAR(entry,'','bank[1,0]',out,s) "
            'IF s<>12311 THEN WRITE(unused) ENDIF '
            "entry=88 GET_VAR(entry,'','bank[1,1]',out,s) "
            'IF (s<>1) OR (entry<>88) THEN WRITE(unused) ENDIF '
            "seed.amount=25 SET_VAR(entry,'','bank[1,0]',seed,s) "
            "GET_VAR(entry,'','bank[1].amount',n,s) "
            'IF (s=0) AND (n=25) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='bank:ARRAY[1] OF route_t out,seed:row_t entry,s,n,wanted,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=row_t',
            context={'variables': [bank]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'BANK[1][0]', 'WANTED'})

    def test_wholly_missing_set_captures_before_status_selector_initializes_source(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,sink:route_t seed,out:row_t entry,s,wanted,unused:INTEGER codes:ARRAY[1] OF INTEGER '
            'ROUTINE slot:INTEGER BEGIN '
            "SET_VAR(entry,'','route[0]',seed,s) RETURN 1 END slot "
            'BEGIN seed.amount=42 '
            "SET_VAR(entry,'','sink[0]',route[0],codes[slot()]) "
            "GET_VAR(entry,'','route[0]',out,s) "
            'IF (codes[1]=12311) AND (s=0) AND (out.amount=42) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        initial = dict(program='T', path='ROUTE', type=['PATH', row, row],
                       value=dict(nodes=[], data=MISSING))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [initial]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[0]', 'WANTED'})

    def test_wholly_missing_path_bank_record_read_stays_unresolved_after_clear(self):
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        path = ['PATH', row, row]
        bank = dict(program='T', path='BANK', type=['ARRAY', 1, path],
                    value=[dict(nodes=[{'AMOUNT': 9}], data={'AMOUNT': 7})])
        source = dict(program='T', path='SOURCE', type=path, value=dict(nodes=[], data=MISSING))
        prepared = prepare(
            "SET_VAR(entry,'','bank[1,1]',source[0],s) "
            "entry=88 GET_VAR(entry,'','bank[1,1]',out,s) "
            'IF (s<>1) OR (entry<>88) THEN WRITE(unused) ENDIF '
            "SET_VAR(entry,'','out',bank[1,1],s)",
            decl='source:route_t bank:ARRAY[1] OF route_t out:row_t entry,s,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=row_t',
            context={'variables': [bank, source]},
        )
        report = prepared['template']['discovery']
        self.assertFalse(report['complete'])
        self.assertEqual(set(by_path(prepared)), {'SOURCE[0]'})
        self.assertTrue(any('SET_VAR operand requires proven PATH storage' in row['message']
                            for row in report['unresolved']), report)

    def test_whole_node_clear_preserves_old_borrowed_fields_and_live_slot(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t seed:row_t entry,s,wanted,unused:INTEGER '
            'ROUTINE wipe(v:route_t;whole:row_t;held:INTEGER) BEGIN '
            "GET_VAR(entry,'','route[1]',whole,s) WRITE(held) held=19 "
            'IF s<>12311 THEN WRITE(unused) ENDIF '
            "GET_VAR(entry,'','seed',whole,s) "
            'IF (s=0) AND (held=19) AND (whole.amount=42) AND (v[2].amount=42) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END wipe '
            'BEGIN seed.amount=42 wipe(route,route[2],route[2].amount) END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        initial = dict(program='T', path='ROUTE', type=['PATH', row, None],
                       value=dict(nodes=[MISSING, {'AMOUNT': MISSING}], data=None))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [initial]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1]', 'ROUTE[2].AMOUNT', 'WANTED'})
        self.assertEqual(by_path(prepared)['ROUTE[2].AMOUNT']['selectors'], [['index', 2], ['field', 'AMOUNT']])

    def test_whole_header_clear_preserves_old_borrowed_fields_and_live_slot(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,empty:route_t seed:row_t entry,s,wanted,unused:INTEGER '
            'ROUTINE wipe(v:route_t;whole:row_t;held:INTEGER) BEGIN '
            "SET_VAR(entry,'T','route[0]',empty[0],s) "
            'IF (s<>12311) OR (held<>7) THEN WRITE(unused) ENDIF held=19 '
            "GET_VAR(entry,'T','seed',whole,s) "
            'IF (s=0) AND (held=19) AND (whole.amount=42) AND (v.amount=42) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END wipe '
            'BEGIN route.amount=7 seed.amount=42 wipe(route,route[0],route.amount) END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        initial = dict(program='T', path='EMPTY', type=['PATH', row, row],
                       value=dict(nodes=[], data=MISSING))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [initial]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'EMPTY[0]', 'WANTED'})

    def test_whole_header_clear_can_follow_a_retired_descriptor_slot(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,substitute,empty:route_t seed:row_t entry,s,wanted,unused:INTEGER '
            'ROUTINE wipe(v:route_t;whole:row_t;held:INTEGER) BEGIN COPY_PATH(substitute,0,0,v,s) '
            "GET_VAR(entry,'','empty[0]',whole,s) "
            'IF (s<>12311) OR (held<>7) THEN WRITE(unused) ENDIF held=19 '
            "GET_VAR(entry,'','seed',whole,s) "
            'IF (s=0) AND (held=19) AND (whole.amount=42) AND (v.amount=23) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END wipe '
            'BEGIN route.amount=7 substitute.amount=23 seed.amount=42 wipe(route,route[0],route.amount) END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        initial = dict(program='T', path='EMPTY', type=['PATH', row, row],
                       value=dict(nodes=[], data=MISSING))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [initial]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'EMPTY[0]', 'WANTED'})

    def test_named_path_transfer_accepts_status_from_rebuilt_retired_header(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,substitute,empty,source:route_t seed:row_t entry,s,wanted,unused:INTEGER '
            'ROUTINE restore(v:route_t;whole:row_t;held:INTEGER) BEGIN COPY_PATH(substitute,0,0,v,s) '
            "GET_VAR(entry,'','empty[0]',whole,s) GET_VAR(entry,'','seed',whole,s) "
            "GET_VAR(entry,'','source',v,whole.amount) "
            'IF (held=7) AND (whole.amount=0) AND (v.amount=31) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END restore '
            'BEGIN route.amount=7 substitute.amount=23 source.amount=31 seed.amount=42 '
            'restore(route,route[0],route.amount) END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        initial = dict(program='T', path='EMPTY', type=['PATH', row, row],
                       value=dict(nodes=[], data=MISSING))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [initial]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'EMPTY[0]', 'WANTED'})

    def test_later_routine_argument_clear_keeps_borrowed_node_field(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t out:row_t entry,s,wanted,unused:INTEGER '
            'ROUTINE clear_slot:INTEGER BEGIN '
            "GET_VAR(entry,'','route[1]',route[2],s) RETURN s END clear_slot "
            'ROUTINE observe(held:INTEGER;code:INTEGER) BEGIN WRITE(held) held=19 '
            'IF (code=12311) AND (held=19) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END observe '
            'BEGIN observe(route[2].amount,clear_slot()) '
            "GET_VAR(entry,'','route[2]',out,s) IF s<>12311 THEN WRITE(unused) ENDIF END T"
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        initial = dict(program='T', path='ROUTE', type=['PATH', row, None],
                       value=dict(nodes=[MISSING, {'AMOUNT': MISSING}], data=None))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [initial]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1]', 'ROUTE[2].AMOUNT', 'WANTED'})
        self.assertEqual(by_path(prepared)['ROUTE[2].AMOUNT']['selectors'], [['index', 2], ['field', 'AMOUNT']])

    def test_get_var_preserves_receiver_captured_before_status_selector_clears_header(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,empty:route_t entry,s,source,out,wanted,unused:INTEGER codes:ARRAY[1] OF INTEGER '
            'ROUTINE slot:INTEGER BEGIN '
            "SET_VAR(entry,'','route[0]',empty[0],s) RETURN 1 END slot "
            'BEGIN route.amount=7 source=42 '
            "GET_VAR(entry,'','source',route.amount,codes[slot()]) "
            'IF codes[1]<>0 THEN WRITE(unused) ENDIF '
            "entry=88 out=19 GET_VAR(entry,'','route.amount',out,s) "
            'IF (s=1) AND (entry=88) AND (out=19) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        initial = dict(program='T', path='EMPTY', type=['PATH', row, row],
                       value=dict(nodes=[], data=MISSING))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [initial]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'EMPTY[0]', 'WANTED'})

    def test_later_register_argument_preserves_captured_path_output_field(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,empty:route_t entry,s,wanted,unused:INTEGER '
            'r:REAL flag:BOOLEAN codes:ARRAY[1] OF INTEGER '
            'ROUTINE slot:INTEGER BEGIN '
            "SET_VAR(entry,'','route[0]',empty[0],s) RETURN 1 END slot "
            'BEGIN route.amount=7 SET_INT_REG(1,42,s) '
            'GET_REG(1,flag,route.amount,r,codes[slot()]) '
            "GET_VAR(entry,'','route.amount',s,codes[1]) "
            'IF codes[1]=1 THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        initial = dict(program='T', path='EMPTY', type=['PATH', row, row],
                       value=dict(nodes=[], data=MISSING))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [initial]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'EMPTY[0]', 'WANTED'})

    def test_path_append_flag_can_clear_record_containing_captured_status(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,empty:route_t seed,out:row_t entry,s,wanted,unused:INTEGER '
            'ROUTINE flag:BOOLEAN BEGIN '
            "SET_VAR(entry,'','route[0]',empty[0],s) RETURN TRUE END flag "
            'BEGIN route.amount=7 seed.amount=12 APPEND_NODE(route,seed,route.amount,flag()) '
            "GET_VAR(entry,'','route[0]',out,s) "
            'IF (PATH_LEN(route)=1) AND (route[1].amount=12) AND (s=12311) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        initial = dict(program='T', path='EMPTY', type=['PATH', row, row],
                       value=dict(nodes=[], data=MISSING))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [initial]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'EMPTY[0]', 'WANTED'})

    def test_path_variable_transfers_preserve_known_fields_and_partial_status(self):
        types = ('TYPE src_n=STRUCTURE amount:REAL ENDSTRUCTURE '
                 'dst_n=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'src_t=PATH NODEDATA=src_n dst_t=PATH NODEDATA=dst_n')
        declarations = 'source:src_t target:dst_t entry,s,wanted,unused:INTEGER'
        for transfer in ("GET_VAR(entry,'T','source',target,s)", "SET_VAR(entry,'','target',source,s)"):
            for partial in (False, True):
                with self.subTest(transfer=transfer, partial=partial):
                    initialized = '' if partial else 'source[1].amount=42.75 '
                    wanted = ('(s=12311) AND UNINIT(target[1].amount)' if partial else
                              '(s=0) AND (target[1].amount=42)')
                    prepared = prepare(
                        f'APPEND_NODE(source,s) {initialized}{transfer} '
                        f'IF (PATH_LEN(target)=1) AND ({wanted}) '
                        'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
                        decl=declarations, prefix=types,
                    )
                    report = prepared['template']['discovery']
                    self.assertTrue(report['complete'], report['unresolved'])
                    self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_path_variable_row_transfers_sample_before_and_after_status_selectors(self):
        source = (
            'PROGRAM T TYPE src_n=STRUCTURE amount:REAL ENDSTRUCTURE '
            'dst_n=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'src_t=PATH NODEDATA=src_n dst_t=PATH NODEDATA=dst_n '
            'VAR source:ARRAY[2] OF src_t target:ARRAY[2,2] OF dst_t out:ARRAY[2] OF dst_t '
            'codes:ARRAY[2] OF INTEGER entry,s,wanted,unused:INTEGER '
            'ROUTINE set_slot:INTEGER BEGIN source[2,1].amount=99.75 RETURN 1 END set_slot '
            'ROUTINE get_slot:INTEGER BEGIN target[2,2,1].amount=17 RETURN 2 END get_slot '
            'BEGIN APPEND_NODE(source[2],s) source[2,1].amount=42.75 '
            "SET_VAR(entry,'','target[2]',source,codes[set_slot()]) "
            'IF target[2,2,1].amount<>42 THEN WRITE(unused) ENDIF '
            "GET_VAR(entry,'T','target[2]',out,codes[get_slot()]) "
            'IF (codes[1]=0) AND (codes[2]=0) AND (PATH_LEN(target[1,2])=0) '
            'AND (out[2,1].amount=17) AND (source[2,1].amount=99.75) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_created_array_cell_flows_through_transfer_and_byname(self):
        source = (
            'PROGRAM T VAR first,entry,status,out,wanted,unused:INTEGER '
            'ROUTINE increment(held:INTEGER) BEGIN held=held+2 END increment '
            "BEGIN CREATE_VAR(' CACHE ','item','','INTEGER',0,2,2,0,status,-1) "
            "SET_VAR(first,'CACHE','ITEM[2,1]',17,status) "
            "increment(BYNAME('CACHE','ITEM[2,1]',entry)) "
            "GET_VAR(entry,'CACHE','ITEM[2,1]',out,status) "
            'IF (first=1) AND (entry=1) AND (status=0) AND (out=19) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})
        self.assertEqual([row['path'] for row in prepared['context']['variables']], ['WANTED'])

    def test_created_data_join_and_uninitialized_transfer(self):
        creation = "CREATE_VAR('CACHE','item','','INTEGER',0,0,0,0,status)"
        prepared = prepare(
            f'IF option THEN {creation} ELSE {creation} ENDIF '
            "out=99 GET_VAR(entry,'CACHE','item',out,status) "
            'IF (status=12311) AND UNINIT(out) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='entry,status,out,wanted,unused:INTEGER option:BOOLEAN',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'OPTION', 'WANTED'})

    def test_created_path_alias_tracks_header_and_inserted_node(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR entry,status,head,out,wanted,unused:INTEGER '
            'ROUTINE fill(p:route_t) VAR s:INTEGER BEGIN '
            'APPEND_NODE(p,s) p[1].amount=17 p.amount=19 END fill '
            "BEGIN CREATE_VAR('CACHE','route','','ROUTE_T',0,0,0,0,status) "
            "fill(BYNAME('CACHE','route',entry)) "
            "GET_VAR(entry,'CACHE','route.amount',head,status) "
            "GET_VAR(entry,'CACHE','route[1].amount',out,status) "
            'IF (status=0) AND (head=19) AND (out=17) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_creation_status_checks_collision_shape_and_storage_budget(self):
        saved = dict(program='CACHE', path='ITEM[1]', type=['INTEGER'], value=17)
        prepared = prepare(
            "CREATE_VAR('CACHE','item','','INTEGER',0,0,0,0,duplicate) "
            "CREATE_VAR('CACHE','bad.name','','INTEGER',0,0,0,0,bad_name) "
            "CREATE_VAR('CACHE','bad_shape','','INTEGER',0,0,1,0,bad_shape) "
            "CREATE_VAR('CACHE','large','','INTEGER',0,32767,0,0,first) "
            "CREATE_VAR('CACHE','extra','','REAL',0,0,0,0,full) "
            'IF (duplicate=3) AND (bad_name=2) AND (bad_shape=5) AND (first=0) AND (full=6) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='duplicate,bad_name,bad_shape,first,full,wanted,unused:INTEGER',
            context={'variables': [saved]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})
        self.assertEqual([row['path'] for row in report['binding_storage']], ['ITEM[1]'])

    def test_branch_dependent_creation_does_not_become_an_initial_input(self):
        prepared = prepare(
            "IF option THEN CREATE_VAR('CACHE','item','','INTEGER',0,0,0,0,status) ENDIF "
            "GET_VAR(entry,'CACHE','item',out,status) ",
            decl='entry,status,out:INTEGER option:BOOLEAN',
        )
        report = prepared['template']['discovery']
        self.assertFalse(report['complete'])
        self.assertEqual(set(by_path(prepared)), {'OPTION'})

    def test_rename_keeps_captured_storage_distinct_from_recreated_name(self):
        source = (
            'PROGRAM T VAR first,entry,status,missing,moved,fresh,wanted,unused:INTEGER '
            'ROUTINE shift(held:INTEGER) BEGIN '
            "RENAME_VAR('CACHE','item','moved_item',status) "
            "GET_VAR(entry,'CACHE','item',fresh,missing) "
            "CREATE_VAR('CACHE','item','','INTEGER',0,0,0,0,status) "
            "SET_VAR(entry,'CACHE','item',7,status) held=held+2 END shift "
            "BEGIN CREATE_VAR('CACHE','item','','INTEGER',0,0,0,0,status) "
            "SET_VAR(first,'CACHE','item',19,status) shift(BYNAME('CACHE','item',entry)) "
            "GET_VAR(entry,'CACHE','moved_item',moved,status) "
            'IF (entry=first) AND (status=0) AND (moved=21) AND (missing=1) THEN '
            "GET_VAR(entry,'CACHE','item',fresh,status) "
            'IF (entry=2) AND (fresh=7) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF '
            'ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_root_rename_preserves_both_saved_row_addresses(self):
        rows = [
            dict(program='CACHE', path='ITEM', type=['VECTOR'], value={'X': 7.0, 'Y': 8.0, 'Z': 9.0}),
            dict(program='CACHE', path='ITEM.X', type=['REAL'], value=42.0),
        ]
        prepared = prepare(
            "RENAME_VAR('CACHE','item','longer_item',status) "
            "GET_VAR(entry,'CACHE','longer_item.x',out,status) WRITE(out) "
            "GET_VAR(entry,'CACHE','longer_item.y',out,status) WRITE(out) "
            'IF status=0 THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='entry,status,wanted,unused:INTEGER out:REAL',
            context={'variables': rows},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        bindings = by_path(prepared)
        self.assertEqual(set(bindings), {'WANTED', 'ITEM.X', 'ITEM.Y'})
        self.assertEqual(bindings['ITEM.X']['context_pointer'], '/variables/1/value')
        self.assertEqual(bindings['ITEM.Y']['context_pointer'], '/variables/0/value')
        self.assertEqual(prepared['context']['variables'][:2], rows)

    def test_namespace_move_follows_path_layout_and_existing_lookup_entry(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR first,entry,status,out,wanted,unused:INTEGER '
            'ROUTINE fill(p:route_t) VAR s:INTEGER BEGIN '
            'APPEND_NODE(p,s) p[1].amount=17 END fill '
            "BEGIN CREATE_VAR('CACHE','road','','ROUTE_T',0,0,0,0,status) "
            "fill(BYNAME('CACHE','road',entry)) GET_VAR(first,'CACHE','road[1].amount',out,status) "
            "RENAME_VARS('CACHE','TRANSFERRED',status) "
            "GET_VAR(entry,'TRANSFERRED','road[1].amount',out,status) "
            'IF (status=0) AND (out=17) AND (entry=first) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_rename_failures_and_branch_dependent_storage(self):
        protected = dict(program='CACHE', path='BOX[1]', type=['INTEGER'], value=7)
        prepared = prepare(
            "RENAME_VAR('','out','next',declared) RENAME_VARS('CACHE','OTHER',nested) "
            "RENAME_VAR('CACHE','absent','next',missing) "
            "RENAME_VAR('CACHE','absent','bad.name',bad) "
            'IF (declared=4) AND (nested=4) AND (missing=1) AND (bad=2) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='out,declared,nested,missing,bad,wanted,unused:INTEGER',
            context={'variables': [protected]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})
        self.assertEqual([row['path'] for row in report['binding_storage']], ['BOX[1]'])

        prepared = prepare(
            "IF option THEN RENAME_VAR('CACHE','item','next',status) ENDIF "
            "GET_VAR(entry,'CACHE','item',out,status)",
            decl='entry,out,status:INTEGER option:BOOLEAN',
            context={'variables': [dict(program='CACHE', path='ITEM', type=['INTEGER'], value=7)]},
        )
        report = prepared['template']['discovery']
        self.assertFalse(report['complete'])
        self.assertEqual(set(by_path(prepared)), {'OPTION'})

    def test_var_info_prefix_commits_metadata_without_requiring_payload(self):
        prepared = prepare(
            "value[2,1]=7 VAR_INFO('','value[2]',missing,label,code,dims[2],slen,s) "
            "IF (s=0) AND (label='INT') AND (code=16) AND (dims[2,1]=3) "
            'AND (dims[2,2]=0) AND (dims[2,3]=0) AND (slen=0) THEN '
            'IF missing THEN WRITE(wanted) ELSE WRITE(alternative) ENDIF '
            'ELSE WRITE(unused) ENDIF',
            decl='value:ARRAY[2,3] OF INTEGER missing:BOOLEAN label:STRING[3] '
                 'code,slen,s,wanted,alternative,unused:INTEGER dims:ARRAY[2,3] OF INTEGER',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED', 'ALTERNATIVE'})

    def test_var_info_checks_renamed_path_initialization(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE item:STRING[4] ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR entry,code,slen,s,wanted,unused:INTEGER empty,before:BOOLEAN '
            'label:STRING[12] dims:ARRAY[3] OF INTEGER '
            "ROUTINE fill(p:route_t) VAR status:INTEGER BEGIN APPEND_NODE(p,status) "
            "p.item='head' p[1].item='node' END fill "
            "BEGIN CREATE_VAR('CACHE','road','','ROUTE_T',0,0,0,0,s) "
            "RENAME_VARS('CACHE','TARGET',s) VAR_INFO('TARGET','road',before,label,code,dims,slen,s) "
            "fill(BYNAME('TARGET','road',entry)) VAR_INFO('TARGET','road',empty,label,code,dims,slen,s) "
            "IF before AND (NOT empty) AND (s=0) AND (label='PATH') "
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_var_info_saved_exact_row_and_status_only_failures(self):
        saved = dict(program='CACHE', path='123', type=['STRING', 8], value='ready')
        prepared = prepare(
            "VAR_INFO('CACHE','123',missing,label,code,dims,slen,s) "
            "IF (s=0) AND (NOT missing) AND (slen=8) AND (label='STRING') THEN "
            "VAR_INFO('CACHE','unknown',missing,label,code,dims,slen,absent) "
            "CREATE_VAR('CACHE','queue','','QUEUE_TYPE',0,0,0,0,s) "
            "VAR_INFO('CACHE','queue',missing,label,code,dims,slen,s) "
            "IF (s=4) AND (absent=1) AND (slen=8) AND (label='STRING') "
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF ELSE WRITE(unused) ENDIF',
            decl='missing:BOOLEAN label:STRING[12] dims:ARRAY[3] OF INTEGER '
                 'code,slen,s,absent,wanted,unused:INTEGER',
            context={'variables': [saved]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})
        self.assertEqual([row['path'] for row in report['binding_storage']], ['123'])

    def test_var_list_tracks_renamed_sorted_page_and_preserves_failed_outputs(self):
        rows = [
            dict(program='CACHE', path='APPLE', type=['INTEGER'], value=7),
            dict(program='CACHE', path='APRICOT', type=['INTEGER'], value=9),
            dict(program='CACHE', path='AXE', type=['REAL'], value=11.0),
        ]
        prepared = prepare(
            "RENAME_VARS('CACHE','MOVED',s) "
            "VAR_LIST('mov?d','a*',16,1,3,names[2],total,s) "
            "short_names[1]='old' VAR_LIST('MOVED','*',0,0,4,short_names,total,too_small) "
            "VAR_LIST('MOVED','*',0,-1,2,short_names,total,bad_filter) "
            "VAR_LIST('EMPTYSPACE','*',0,0,2,short_names,total,absent) "
            "IF (s=0) AND (total=1) AND (names[2,1]='[MOVED]APRICOT') AND (names[2,2]='') "
            "AND (too_small=3) AND (bad_filter=2) AND (absent=1) AND (short_names[1]='old') "
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='names:ARRAY[2,2] OF STRING[24] short_names:ARRAY[1] OF STRING[3] '
                 'total,s,too_small,bad_filter,absent,wanted,unused:INTEGER',
            context={'variables': rows},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})
        self.assertEqual({row['path'] for row in report['binding_storage']}, {'APPLE', 'APRICOT', 'AXE'})

    def test_var_list_overlap_and_dynamic_selectors_are_reported(self):
        prepared = prepare(
            "WRITE(read_first) VAR_LIST('','*',0,0,2,names,status,status) WRITE(unreachable)",
            decl='names:ARRAY[1] OF STRING[24] status,read_first,unreachable:INTEGER',
        )
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], ['service-output'])
        self.assertEqual(set(by_path(prepared)), {'READ_FIRST'})

        prepared = prepare(
            "VAR_LIST('CACHE',pattern,0,0,2,names,total,status)",
            decl='names:ARRAY[1] OF STRING[24] pattern:STRING[10] total,status:INTEGER',
        )
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], ['variable-catalog'])
        self.assertEqual(set(by_path(prepared)), {'PATTERN'})

    def test_program_catalog_tracks_cursor_tail_and_failed_page(self):
        prepared = prepare(
            "cursor_no=0 PROG_LIST('w?ld',7,0,1,names[2],count,s,cursor_no) "
            "first=names[2,1] PROG_LIST('w?ld',7,0,1,names[2],count,s,cursor_no) "
            "IF (first='WALD') AND (count=1) AND (cursor_no=3) AND (names[2,1]='WELD') "
            "AND (names[2,2]='') THEN "
            "PROG_LIST('w?ld',7,1,1,names[2],count,s,cursor_no) "
            "IF (s=2) AND (count=1) AND (cursor_no=3) AND (names[2,1]='WELD') "
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF ELSE WRITE(unused) ENDIF',
            decl='names:ARRAY[2,2] OF STRING[10] first:STRING[10] count,s,cursor_no,wanted,unused:INTEGER',
            context={'programs': [dict(name=name,type='PC') for name in ('WALD','WBLD','WELD','WORLD')]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_program_catalog_cursor_read_is_an_input_when_unwritten(self):
        prepared = prepare(
            "PROG_LIST('*',7,0,1,names,count,s,cursor_no)",
            decl='names:ARRAY[1] OF STRING[10] count,s,cursor_no:INTEGER',
        )
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], ['program-catalog'])
        self.assertEqual(set(by_path(prepared)), {'CURSOR_NO'})

    def test_program_metadata_tracks_loaded_flags_and_selected_outputs(self):
        prepared = prepare(
            "GET_ATTR_PRG('T',AT_COMMENT,n,label,s) "
            "IF (label='sour') AND (s=0) THEN "
            "GET_ATTR_PRG('T',AT_PROG_TYPE,n,label,s) "
            "LOAD_STATUS('T',loaded,initialized) "
            "IF loaded AND initialized AND (n=PT_KRLPRG) AND (label='sour') THEN "
            "LOAD_STATUS('EXTRA',loaded,initialized) "
            "GET_ATTR_PRG('EXTRA',AT_OWNER,n,label,s) "
            "GET_ATTR_PRG('EXTRA',AT_PROG_SIZE,n,label,unavailable) "
            "IF loaded AND (NOT initialized) AND (label='team') AND (n=PT_KRLPRG) "
            'AND (s=0) AND (unavailable=3) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF '
            'ELSE WRITE(unused) ENDIF ELSE WRITE(unused) ENDIF',
            prefix="\n%NOLOCKGROUP\n%COMMENT = 'source note'\n",
            decl='loaded,initialized:BOOLEAN n,s,unavailable,wanted,unused:INTEGER label:STRING[4]',
            context={'program_attributes': {'extra': {'loaded':True, 'attributes': {'AT_OWNER':'team'}}}},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_program_metadata_tracks_unknown_initialization_without_fake_values(self):
        prepared = prepare(
            "LOAD_STATUS('T',loaded,initialized) IF loaded THEN "
            'IF initialized THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF ELSE WRITE(unused) ENDIF',
            decl='loaded,initialized:BOOLEAN wanted,alternate,unused:INTEGER',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED', 'ALTERNATE'})

    def test_saved_byname_and_named_transfers_share_the_same_binding(self):
        source = (
            'PROGRAM T VAR first,entry,status,out,wanted,unused:INTEGER '
            'ROUTINE increment(held:INTEGER) BEGIN WRITE(held) held=41 END increment '
            "BEGIN increment(BYNAME('CACHE','ITEM',first)) "
            "GET_VAR(entry,'CACHE','item',out,status) "
            'IF (first=1) AND (entry=1) AND (status=0) AND (out=41) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        supplied = dict(program='cache', path='item', type=['INTEGER'], value=7)
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [supplied]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        bindings = by_path(prepared)
        self.assertEqual(set(bindings), {'ITEM', 'WANTED'})
        self.assertEqual((bindings['ITEM']['program'], bindings['ITEM']['status']), ('CACHE', 'supplied'))
        self.assertEqual(bindings['ITEM']['context_pointer'], '/variables/0/value')
        self.assertEqual(prepared['context']['variables'][0], supplied)

    def test_exact_saved_path_beats_saved_root_but_declared_root_takes_priority(self):
        source = (
            'PROGRAM T VAR bank:ARRAY[2] OF INTEGER entry,status,out,wanted,unused:INTEGER '
            'ROUTINE change(alias:INTEGER) BEGIN WRITE(alias) alias=41 END change '
            'ROUTINE sample(alias:ARRAY OF INTEGER) BEGIN WRITE(alias[1]) END sample '
            "BEGIN change(BYNAME('CACHE','grid[1]',entry)) sample(BYNAME('CACHE','grid',entry)) "
            "bank[1]=17 GET_VAR(entry,'','bank[1]',out,status) "
            'IF (status=0) AND (out=17) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        rows = [
            dict(program='CACHE', path='GRID', type=['ARRAY', 2, ['INTEGER']], value=[7, 8]),
            dict(program='CACHE', path='GRID[1]', type=['INTEGER'], value=13),
            dict(program='T', path='BANK[1]', type=['INTEGER'], value=99),
        ]
        prepared = prepare_inputs(translate(source).python_source, context={'variables': rows})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        grid = [binding for binding in prepared['template']['bindings'] if binding['path'] == 'GRID[1]']
        self.assertEqual({(row['context_pointer'], row['status']) for row in grid},
                         {('/variables/0/value', 'supplied'), ('/variables/1/value', 'supplied')})
        self.assertEqual(set(by_path(prepared)), {'GRID[1]', 'WANTED'})
        from karel2py.input_refresh import refresh_inputs

        refreshed = refresh_inputs(translate(source).python_source, prepared)
        retained = refreshed['template']['refresh']['changes']['retained']
        self.assertEqual({row['root_path'] for row in retained if row['path'] == 'GRID[1]'}, {'GRID', 'GRID[1]'})
        self.assertEqual(refreshed['context']['variables'][:len(rows)], rows)

    def test_blank_namespace_saved_row_remains_an_editable_named_input(self):
        prepared = prepare(
            "GET_VAR(entry,'','outside',out,s) WRITE(out)",
            decl='entry,out,s:INTEGER',
            context={'variables': [dict(program='', path='OUTSIDE', type=['INTEGER'], value=7)]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        binding = by_path(prepared)['OUTSIDE']
        self.assertEqual(binding['program'], '')
        self.assertEqual(binding['status'], 'supplied')
        self.assertEqual(binding['context_pointer'], '/variables/0/value')

    def test_byname_uses_saved_path_node_layout_and_original_input_pointer(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'VAR entry,status,out,wanted,unused:INTEGER '
            'ROUTINE change(node:row_t) BEGIN WRITE(node.amount) node.amount=51 END change '
            "BEGIN change(BYNAME('CACHE','route[1]',entry)) "
            "GET_VAR(entry,'CACHE','route[1].amount',out,status) "
            'IF (status=0) AND (out=51) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        saved = dict(program='CACHE', path='ROUTE', type=['PATH', row, None],
                     value=dict(nodes=[{'AMOUNT': MISSING}], data=None))
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [saved]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1].AMOUNT', 'WANTED'})
        binding = by_path(prepared)['ROUTE[1].AMOUNT']
        self.assertEqual(binding['selectors'], [['index', 1], ['field', 'AMOUNT']])
        self.assertEqual(binding['context_pointer'], '/variables/0/value')

    def test_saved_record_parent_controls_named_lookup_before_and_after_repair(self):
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        prepared = prepare(
            "entry=88 out=19 GET_VAR(entry,'CACHE','record.amount',out,s) "
            'IF (s<>1) OR (entry<>88) OR (out<>19) THEN WRITE(unused) ENDIF '
            "seed.amount=41 SET_VAR(entry,'CACHE','record',seed,s) IF s<>0 THEN WRITE(unused) ENDIF "
            "GET_VAR(entry,'CACHE','record.amount',out,s) "
            'IF (s=0) AND (out=41) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='entry,out,s,wanted,unused:INTEGER seed:row_t',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE',
            context={'variables': [dict(program='CACHE', path='RECORD', type=row, value=MISSING)]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_byname_borrows_declared_scalars_and_array_prefixes_with_shared_entries(self):
        source = (
            'PROGRAM T VAR n,out,a,b,entry,s,wanted,unused:INTEGER grid:ARRAY[2,2] OF INTEGER '
            'ROUTINE fill(cell:INTEGER;row:ARRAY OF INTEGER) BEGIN cell=31 row[2]=41 END fill '
            "BEGIN fill(BYNAME('','n',a),BYNAME(' T ','grid[1]',b)) "
            "GET_VAR(entry,'','N',out,s) "
            'IF (a=1) AND (b=2) AND (entry=1) AND (s=0) AND (out=31) AND (grid[1,2]=41) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_byname_distinguishes_borrowed_path_slots_and_record_fields(self):
        common = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement:route_t a,b,s,wanted,unused:INTEGER '
            'ROUTINE shift:INTEGER BEGIN INSERT_NODE(route,1,s) route[1].amount=13 RETURN 1 END shift '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) RETURN 1 END swap '
        )
        for selector, condition in (
            ('shift()', '(held=7) AND (route[1].amount=41) AND (route[2].amount=7)'),
            ('swap()', '(held=41) AND (route[1].amount=13)'),
        ):
            with self.subTest(selector=selector):
                source = common + (
                    'ROUTINE observe(whole:row_t;held,code:INTEGER) BEGIN whole.amount=41 '
                    f'IF (code=1) AND (a=1) AND (b=2) AND {condition} '
                    'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END observe '
                    'BEGIN APPEND_NODE(route,s) route[1].amount=7 '
                    'APPEND_NODE(replacement,s) replacement[1].amount=13 '
                    f"observe(BYNAME('','route[1]',a),BYNAME('','route[1].amount',b),{selector}) END T"
                )
                prepared = prepare_inputs(translate(source).python_source)
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_byname_rejection_stops_before_later_arguments(self):
        common = (
            'PROGRAM T VAR data,entry,late,early:INTEGER '
            "ROUTINE owner_name:STRING[8] BEGIN WRITE(early) RETURN '' END owner_name "
            'ROUTINE last:INTEGER BEGIN WRITE(late) RETURN 1 END last '
            'ROUTINE integer_arg(n,unused:INTEGER) BEGIN WRITE(late) END integer_arg '
            'ROUTINE real_arg(n:REAL;unused:INTEGER) BEGIN WRITE(late) END real_arg '
            'BEGIN data=7 '
        )
        for statement, message in (
            ("integer_arg(BYNAME(owner_name(),'data',data),last())", 'overlaps entry output'),
            ("integer_arg(BYNAME(owner_name(),'data[1]',entry),last())", 'selection is invalid'),
            ("real_arg(BYNAME(owner_name(),'data',entry),last())", 'type does not match'),
        ):
            with self.subTest(statement=statement):
                prepared = prepare_inputs(translate(common + statement + ' WRITE(late) END T').python_source)
                report = prepared['template']['discovery']
                self.assertEqual([gap['code'] for gap in report['unresolved']], ['byname'])
                self.assertIn(message, report['unresolved'][0]['message'])
                self.assertEqual(set(by_path(prepared)), {'EARLY'})

    def test_named_variable_entry_reuses_exact_requested_spellings(self):
        prepared = prepare(
            'grid[1,2]=7 '
            "GET_VAR(entry,'','grid[1][2]',out,s) IF (entry<>1) OR (out<>7) THEN WRITE(unused) ENDIF "
            "SET_VAR(entry,'T','GRID[1][2]',13,s) IF (entry<>1) OR (s<>0) THEN WRITE(unused) ENDIF "
            "GET_VAR(entry,'','GRID[1,2]',out,s) "
            'IF (entry=2) AND (s=0) AND (out=13) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='grid:ARRAY[2,2] OF INTEGER entry,s,out,wanted,unused:INTEGER',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_named_variable_entry_only_allocates_after_publication(self):
        prepared = prepare(
            "entry=88 out=19 APPEND_NODE(partial,s) GET_VAR(entry,'','partial[9].AMOUNT',out,s) "
            'IF (s<>1) OR (entry<>88) THEN WRITE(unused) ENDIF '
            "SET_VAR(entry,'','out',TRUE,s) IF (s<>3) OR (entry<>88) THEN WRITE(unused) ENDIF "
            "GET_VAR(entry,'','partial',target,s) "
            'IF (entry<>1) OR (s<>12311) OR (PATH_LEN(target)<>1) THEN WRITE(unused) ENDIF '
            "SET_VAR(entry,'','out',37,s) "
            'IF (entry=2) AND (s=0) AND (out=37) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='partial,target:PATH NODEDATA=row_t entry,s,out,wanted,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_named_variable_entry_merges_branch_allocations_by_count_and_key(self):
        prepared = prepare(
            "a=1 b=2 c=3 d=4 IF choice THEN GET_VAR(entry,'','a',out,s) ELSE GET_VAR(entry,'','b',out,s) ENDIF "
            'IF entry<>1 THEN WRITE(unused) ENDIF '
            "GET_VAR(entry,'','c',out,s) IF entry<>2 THEN WRITE(unused) ENDIF "
            "GET_VAR(entry,'','a',out,s) IF entry=1 THEN WRITE(reused) ELSE WRITE(allocated) ENDIF "
            "GET_VAR(entry,'','d',out,s) IF entry=3 THEN WRITE(third) ELSE WRITE(fourth) ENDIF",
            decl='a,b,c,d,entry,s,out,unused,reused,allocated,third,fourth:INTEGER choice:BOOLEAN',
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'CHOICE', 'REUSED', 'ALLOCATED', 'THIRD', 'FOURTH'})

    def test_unknown_named_transfer_keeps_prior_entries_but_loses_next_number(self):
        prepared = prepare(
            "a=1 b=2 GET_VAR(entry,'','a',out,s) GET_VAR(entry,'',address,out,s) "
            "GET_VAR(entry,'','a',out,s) IF entry<>1 THEN WRITE(unused) ENDIF "
            "GET_VAR(entry,'','b',out,s) IF entry=2 THEN WRITE(second) ELSE WRITE(later) ENDIF",
            decl='a,b,entry,s,out,unused,second,later:INTEGER address:STRING[12]',
        )
        report = prepared['template']['discovery']
        self.assertEqual([gap['code'] for gap in report['unresolved']], ['variable-path'])
        self.assertEqual(set(by_path(prepared)), {'ADDRESS', 'SECOND', 'LATER'})

    def test_named_variable_rejects_invalid_suffix_on_known_roots(self):
        common = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t bank:ARRAY[2,2] OF route_t grid:ARRAY[2,2] OF INTEGER '
            'row:row_t entry,s,out,wanted,unused:INTEGER '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 entry=88 out=19 '
        )
        for address in (
            'grid[0,1]', 'grid[1,3]', 'grid[1].amount', 'row.absent', 'row[1]',
            'row.amount.', 'route[1].absent', 'route[1,2]', 'bank[1,2,1,0]',
        ):
            for getting in (True, False):
                with self.subTest(address=address, getting=getting):
                    call = f"GET_VAR(entry,'','{address}',out,s)" if getting else f"SET_VAR(entry,'','{address}',7,s)"
                    source = common + call + (
                        ' IF (s=1) AND (entry=88) AND (out=19) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
                    )
                    prepared = prepare_inputs(translate(source).python_source)
                    report = prepared['template']['discovery']
                    self.assertTrue(report['complete'], report['unresolved'])
                    self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_rejected_get_var_layout_omits_unused_payload_reads(self):
        types = ('TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'other_row=STRUCTURE other:INTEGER ENDSTRUCTURE '
                 'route_t=PATH NODEDATA=row_t other_t=PATH NODEDATA=other_row')
        declarations = ('source:route_t incompatible:other_t bank:ARRAY[2] OF route_t '
                        'small_bank:ARRAY[1] OF route_t out,entry,s,wanted,unused:INTEGER message:STRING[12]')
        setup = ('entry=88 out=19 APPEND_NODE(incompatible,s) incompatible[1].other=23 '
                 'APPEND_NODE(small_bank[1],s) small_bank[1,1].amount=43 ')
        seed_type = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        seed = dict(program='T', path='SOURCE', type=seed_type, value=dict(nodes=[{'AMOUNT': MISSING}], data=None))
        cases = (
            ("GET_VAR(entry,'','message',out,s)", 'out=19'),
            ("GET_VAR(entry,'','source',out,s)", 'out=19'),
            ("GET_VAR(entry,'','out',incompatible,s)", 'incompatible[1].other=23'),
            ("GET_VAR(entry,'','source',incompatible,s)", 'incompatible[1].other=23'),
            ("APPEND_NODE(bank[2],s) GET_VAR(entry,'','bank',small_bank,s)", 'small_bank[1,1].amount=43'),
        )
        for call, preserved in cases:
            with self.subTest(call=call):
                body = setup + call + (
                    f' IF (s=3) AND (entry=88) AND ({preserved}) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF'
                )
                prepared = prepare(body, decl=declarations, prefix=types, context={'variables': [seed]})
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_rejected_set_var_path_layout_preserves_earlier_payload_capture(self):
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        path = dict(program='T', path='SOURCE', type=['PATH', row, None],
                    value=dict(nodes=[{'AMOUNT': MISSING}], data=None))
        prepared = prepare(
            "entry=88 out=19 SET_VAR(entry,'','out',source,s) "
            'IF (s=3) AND (entry=88) AND (out=19) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='source:PATH NODEDATA=row_t entry,s,out,wanted,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE',
            context={'variables': [path]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'SOURCE[1]', 'WANTED'})

    def test_rejected_path_variable_layout_keeps_receiver_and_entry(self):
        types = ('TYPE src_n=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                 'dst_n=STRUCTURE other:INTEGER ENDSTRUCTURE '
                 'src_t=PATH NODEDATA=src_n dst_t=PATH NODEDATA=dst_n')
        prepared = prepare(
            "entry=88 APPEND_NODE(source,s) source[1].amount=42 "
            "APPEND_NODE(target,s) target[1].other=7 SET_VAR(entry,'','target',source,s) "
            'IF (s=3) AND (entry=88) AND (target[1].other=7) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='source:src_t target:dst_t entry,s,wanted,unused:INTEGER', prefix=types,
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_unknown_copy_bounds_leave_destination_origin_unresolved(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='SOURCE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare('COPY_PATH(source,first,1,target,s) WRITE(target[1])',
                           decl='source,target:PATH NODEDATA=row_t first,s:INTEGER',
                           prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context=context)
        report = prepared['template']['discovery']
        self.assertEqual(set(by_path(prepared)), {'FIRST'})
        self.assertTrue(any('Saved origin of TARGET[1] is unresolved' in row['message']
                            for row in report['unresolved']))

    def test_path_assignment_retains_distinct_records_after_shift_and_self_copy(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]
        source = dict(program='T', path='SOURCE', type=spec,
                      value=dict(nodes=[{'AMOUNT': MISSING} for _ in range(3)], data={'TOTAL': MISSING}))
        prepared = prepare(
            'source.total=7 source[3].amount=19 DELETE_NODE(source,1,s) '
            'source=source target=(source) source[2].amount=33 '
            'IF (PATH_LEN(target)=2) AND (target[2].amount=19) AND (target.total=7) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='source,target:PATH NODEDATA=row_t PATHHEADER=head_t s,wanted,unused:INTEGER',
            prefix=('TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                    'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE'),
            context={'variables': [source]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'SOURCE[2]', 'WANTED'})
        self.assertEqual(report['path_storage'], [dict(program='T', path='SOURCE', type=spec)])

    def test_path_assignment_captures_before_a_destination_selector(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=head_t '
            'VAR source:route_t targets:ARRAY[2] OF route_t wanted,unused:INTEGER '
            'ROUTINE slot:INTEGER BEGIN source[1].amount=19 source.total=31 RETURN 2 END slot '
            'BEGIN source[1].amount=7 source.total=11 targets[slot()]=(source) '
            'IF (targets[2,1].amount=7) AND (targets[2].total=11) AND (source.total=31) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]
        context = {'variables': [dict(program='T', path='SOURCE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data={'TOTAL': MISSING}))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_path_assignment_preserves_missing_leaves_and_reports_dynamic_destination(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='SOURCE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        decl = 'source:PATH NODEDATA=row_t targets:ARRAY[2] OF PATH NODEDATA=row_t i:INTEGER'
        prefix = 'TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        exact = prepare('targets[1]=source WRITE(targets[1,1])', decl=decl, prefix=prefix, context=context)
        self.assertEqual(set(by_path(exact)), {'SOURCE[1]'})
        self.assertIn('derived-value', {row['code'] for row in exact['template']['discovery']['unresolved']})
        dynamic = prepare('targets[i]=source WRITE(targets[1,1])', decl=decl, prefix=prefix, context=context)
        self.assertEqual(set(by_path(dynamic)), {'I', 'SOURCE[1]'})
        self.assertIn('path-topology', {row['code'] for row in dynamic['template']['discovery']['unresolved']})

    def test_path_assignment_with_model_dependency_keeps_source_input_visible(self):
        source = dict(program='T', path='SOURCE',
                      type=['PATH', ['STRUCTURE', 'SOURCE_T', [['POINT', ['JOINTPOS', 2]]]], None],
                      value=dict(nodes=[{'POINT': {'axes': [MISSING, MISSING]}}], data=None))
        prepared = prepare(
            'target=source WRITE(PATH_LEN(target))',
            decl='source:PATH NODEDATA=source_t target:PATH NODEDATA=row_t',
            prefix=('TYPE source_t=STRUCTURE point:JOINTPOS2 ENDSTRUCTURE '
                    'row_t=STRUCTURE point:XYZWPR ENDSTRUCTURE'),
            context={'variables': [source]},
        )
        self.assertEqual(set(by_path(prepared)), {'SOURCE[1]'})
        self.assertIn('path-topology', {row['code'] for row in prepared['template']['discovery']['unresolved']})

    def test_private_path_argument_is_captured_before_later_argument_effects(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=head_t '
            'VAR source,target:route_t wanted,unused:INTEGER '
            'ROUTINE change_source:INTEGER BEGIN source[1].amount=99 source.total=31 RETURN 0 END change_source '
            'ROUTINE build(v:route_t;ignored:INTEGER):route_t VAR local:route_t s:INTEGER '
            'BEGIN APPEND_NODE(v,s) v[2].amount=21 local=v RETURN local END build '
            'BEGIN source[1].amount=7 source.total=11 target=build((source),change_source()) '
            'IF (PATH_LEN(target)=2) AND (target[1].amount=7) AND (target[2].amount=21) '
            'AND (target.total=11) AND (source.total=31) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]
        context = {'variables': [dict(program='T', path='SOURCE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data={'TOTAL': MISSING}))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_borrowed_path_keeps_caller_writes_and_return_is_independent(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR source,target:route_t wanted,unused:INTEGER '
            'ROUTINE update(v:route_t):route_t BEGIN v[1].amount=8 RETURN v END update '
            'BEGIN target=update(source) source[1].amount=9 '
            'IF (PATH_LEN(target)=1) AND (target[1].amount=8) AND (source[1].amount=9) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='SOURCE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_computed_path_count_works_with_fresh_routine_local_storage(self):
        from karel2py.input_discovery import discover_inputs

        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR wanted,unused:INTEGER '
            'ROUTINE build:route_t VAR p:route_t s:INTEGER '
            'BEGIN APPEND_NODE(p,s) p[1].amount=17 RETURN p END build '
            'BEGIN IF PATH_LEN(build())=1 THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        report = discover_inputs(translate(source).python_source)
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual([row['path'] for row in report['inputs']], ['WANTED'])

    def test_path_result_discovery_uses_only_selected_records_and_members(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE total:INTEGER flags:ARRAY[2,2] OF INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=head_t VAR wanted,unused,bound:INTEGER '
            'ROUTINE build:route_t VAR p:route_t s:INTEGER '
            'BEGIN INSERT_NODE(p,1,s) INSERT_NODE(p,2,s) p.total=41 '
            'p.flags[1,1]=11 p.flags[1,2]=12 p.flags[2,1]=13 p.flags[2,2]=14 '
            'p[1].amount=42 RETURN p END build '
            'BEGIN {} END T'
        )
        cases = (
            ('WRITE(build()[1..0],build[0..0],build()[1])', set(), set()),
            ('IF (build().flags[2,1]=13) AND (build()[1].amount=42) '
             'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF', {'WANTED'}, set()),
            ('IF (ARRAY_LEN(build().flags,2)=2) AND UNINIT(build()[2].amount) '
             'AND NOT UNINIT(build()[1].amount) '
             'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF', {'WANTED'}, set()),
            ('WRITE(build().flags[bound,wanted])', {'BOUND', 'WANTED'}, {'dynamic-address'}),
            ('WRITE(build())', set(), {'derived-value'}),
            ('WRITE(build()[2..2])', set(), {'derived-value'}),
            ('WRITE(build()[2].amount)', set(), {'derived-value'}),
            ('WRITE(build()[1..3])', set(), {'path-topology'}),
            ('WRITE(build()[bound..0])', {'BOUND'}, {'selection'}),
        )
        for body, inputs, codes in cases:
            with self.subTest(body=body):
                prepared = prepare_inputs(translate(source.format(body)).python_source)
                report = prepared['template']['discovery']
                self.assertEqual({row['code'] for row in report['unresolved']}, codes)
                self.assertEqual(set(by_path(prepared)), inputs)

    def test_returned_path_bank_preserves_selected_cells_and_array_prefixes(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=head_t '
            'VAR wanted,unused:INTEGER '
            'ROUTINE bank:ARRAY OF route_t VAR rows:ARRAY[2,2] OF route_t s:INTEGER '
            'BEGIN INSERT_NODE(rows[2,1],1,s) INSERT_NODE(rows[2,2],1,s) '
            'rows[2,1].total=41 rows[2,1,1].amount=42 rows[2,2].total=43 RETURN rows[2] END bank '
            'BEGIN {} END T'
        )
        for body, inputs, codes in (
            ('WRITE(bank()[1][1..0],bank()[1,1..0])', set(), set()),
            ('IF (ARRAY_LEN(bank())=2) AND (PATH_LEN(bank()[2])=1) '
             'AND (bank()[1,1].amount=42) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF', {'WANTED'}, set()),
            ('WRITE(bank())', set(), {'derived-value'}),
            ('WRITE(bank()[2,0..0])', set(), set()),
            ('WRITE(bank()[1,2..0])', set(), {'path-topology'}),
        ):
            with self.subTest(body=body):
                prepared = prepare_inputs(translate(source.format(body)).python_source)
                report = prepared['template']['discovery']
                self.assertEqual(set(by_path(prepared)), inputs)
                self.assertEqual({row['code'] for row in report['unresolved']}, codes)

    def test_path_bank_assignment_keeps_header_alias_and_detaches_old_node(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=head_t '
            'VAR target:ARRAY[2] OF route_t matrix:ARRAY[2,2] OF route_t good,bad:INTEGER '
            'ROUTINE bank:ARRAY OF route_t VAR rows:ARRAY[2] OF route_t s:INTEGER '
            'BEGIN INSERT_NODE(rows[1],1,s) rows[1].total=41 rows[1,1].amount=42 rows[2].total=43 '
            'RETURN rows END bank '
            'ROUTINE replace_bank(old:row_t; h:head_t) BEGIN target=bank() matrix[2]=target '
            'IF (old.amount=77) AND (h.total=41) AND (matrix[2,1,1].amount=42) '
            'AND (PATH_LEN(matrix[2,2])=0) THEN WRITE(good) ELSE WRITE(bad) ENDIF END replace_bank '
            'BEGIN target=bank() target[1,1].amount=77 target[1].total=88 '
            'replace_bank(target[1,1],target[1][0]) END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'GOOD'})

    def test_returned_path_bank_checks_combined_write_budget(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE scores:ARRAY[513] OF INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t VAR unused:INTEGER '
            'ROUTINE bank:ARRAY OF route_t VAR rows:ARRAY[2] OF route_t s:INTEGER '
            'BEGIN INSERT_NODE(rows[1],1,s) INSERT_NODE(rows[2],1,s) RETURN rows END bank '
            'BEGIN WRITE(bank()) END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertIn('selection', {row['code'] for row in report['unresolved']})
        self.assertTrue(any('transfer limit' in row['message'] for row in report['unresolved']))

    def test_path_bank_prefix_checks_containing_budget_before_capturing_a_cell(self):
        from karel2py.input_discovery import _discover_inputs

        source = (
            'PROGRAM T TYPE row_t=STRUCTURE scores:ARRAY[16383] OF INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t VAR rows:ARRAY[2,1] OF route_t '
            'ROUTINE bank:ARRAY OF route_t BEGIN RETURN rows[1] END bank '
            'BEGIN WRITE(bank()[1,1..1]) END T'
        )
        # Each selected row fits, but the two one-node cells and their
        # descriptors exceed the containing bank's 32767-unit snapshot limit.
        report = _discover_inputs(translate(source).python_source, filename='authored.py',
                                  saved_path_count=lambda *_: 1)
        self.assertFalse(report['inputs'])
        self.assertTrue(any(row['code'] == 'limit' and 'snapshot limit' in row['message']
                            for row in report['unresolved']))

    def test_path_bank_converts_partial_records_across_source_boundaries(self):
        source = (
            'PROGRAM T TYPE source_node=STRUCTURE amount:REAL label:STRING[8] spare:INTEGER ENDSTRUCTURE '
            'target_node=STRUCTURE amount:INTEGER label:STRING[4] spare:INTEGER ENDSTRUCTURE '
            'source_head=STRUCTURE marker:INTEGER ENDSTRUCTURE target_head=STRUCTURE marker:SHORT ENDSTRUCTURE '
            'source_path=PATH NODEDATA=source_node PATHHEADER=source_head '
            'target_path=PATH NODEDATA=target_node PATHHEADER=target_head '
            'VAR a:ARRAY[2,2] OF source_path b:ARRAY[2,2] OF target_path s,good,bad:INTEGER '
            'ROUTINE build:ARRAY OF target_path BEGIN RETURN a[2] END build '
            'ROUTINE accept(v:ARRAY OF target_path):INTEGER BEGIN RETURN v[2,1].amount END accept '
            'BEGIN APPEND_NODE(a[2,2],s) a[2,2,1].amount=42.75 a[2,2,1].label=\'abcdEF\' '
            'a[2,1].marker=1 a[2,2].marker=32767 '
            'b[1]=a[2] '
            'IF (b[1,2,1].amount=42) AND (b[1,2,1].label=\'abcd\') AND UNINIT(b[1,2].marker) '
            'AND (PATH_LEN(build()[2])=1) AND UNINIT(build()[2,1].spare) AND (accept(a[2])=42) '
            'THEN WRITE(good) ELSE WRITE(bad) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'GOOD'})

    def test_path_bank_conversion_failure_precedes_destination_or_later_argument(self):
        source = (
            'PROGRAM T TYPE source_node=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'target_node=STRUCTURE amount:BYTE ENDSTRUCTURE '
            'source_path=PATH NODEDATA=source_node target_path=PATH NODEDATA=target_node '
            'VAR a:ARRAY[1] OF source_path b:ARRAY[2,1] OF target_path s,unused:INTEGER '
            'ROUTINE pick:INTEGER BEGIN WRITE(unused) RETURN 1 END pick '
            'ROUTINE accept(v:ARRAY OF target_path; which:INTEGER) BEGIN WRITE(unused) END accept '
            'ROUTINE build:ARRAY OF target_path BEGIN RETURN a END build '
            'BEGIN APPEND_NODE(a[1],s) a[1,1].amount=256 {} WRITE(unused) END T'
        )
        for statement in ('b[pick()]=a', 'accept((a),pick())', 'WRITE(build())'):
            with self.subTest(statement=statement):
                prepared = prepare_inputs(translate(source.format(statement)).python_source)
                report = prepared['template']['discovery']
                self.assertFalse(report['inputs'])
                unresolved, = report['unresolved']
                self.assertEqual(unresolved['code'], 'path-conversion')
                self.assertIn('BYTE value outside', unresolved['message'])

    def test_path_bank_conversion_checks_combined_target_budget_before_selecting_destination(self):
        source = (
            'PROGRAM T TYPE n1=STRUCTURE joints:ARRAY[2048] OF JOINTPOS1 ENDSTRUCTURE '
            'n2=STRUCTURE joints:ARRAY[2048] OF JOINTPOS9 ENDSTRUCTURE '
            'p1=PATH NODEDATA=n1 p2=PATH NODEDATA=n2 '
            'VAR a:ARRAY[2] OF p1 b:ARRAY[2,2] OF p2 s,unused:INTEGER '
            'ROUTINE pick:INTEGER BEGIN WRITE(unused) RETURN 1 END pick '
            'BEGIN APPEND_NODE(a[1],s) APPEND_NODE(a[2],s) b[pick()]=a END T'
        )
        report = prepare_inputs(translate(source).python_source)['template']['discovery']
        self.assertFalse(report['inputs'])
        unresolved, = report['unresolved']
        self.assertEqual(unresolved['code'], 'limit')
        self.assertIn('conversion target', unresolved['message'])

    def test_model_backed_bank_conversion_preserves_the_robot_requirement(self):
        source = (
            'PROGRAM T TYPE src_node=STRUCTURE point:JOINTPOS1 ENDSTRUCTURE '
            'dst_node=STRUCTURE point:XYZWPREXT ENDSTRUCTURE '
            'src_path=PATH NODEDATA=src_node dst_path=PATH NODEDATA=dst_node '
            'VAR a:ARRAY[1] OF src_path b:ARRAY[1] OF dst_path s:INTEGER '
            'BEGIN APPEND_NODE(a[1],s) a[1,1].point[1]=42 b=a END T'
        )
        report = prepare_inputs(translate(source).python_source)['template']['discovery']
        self.assertIn({'service': 'robot', 'address': None}, report['context_requirements'])
        self.assertTrue(any(row['code'] == 'path-conversion' and 'robot model results' in row['message']
                            for row in report['unresolved']))

    def test_partial_private_path_keeps_saved_inputs_at_original_address(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR source,target:route_t '
            'ROUTINE copy(v:route_t):route_t BEGIN RETURN v END copy '
            'BEGIN target=copy((source)) WRITE(target[1]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='SOURCE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertEqual(set(by_path(prepared)), {'SOURCE[1]'})
        self.assertEqual({row['code'] for row in report['unresolved']}, {'derived-value'})

    def test_seeded_insert_reads_the_existing_seed_before_nodes_shift(self):
        from karel2py.structured_inputs import structured_slot

        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        seed = dict(program='T', path='ROUTE', type=spec,
                    value=dict(nodes=[{'AMOUNT': 5}, {'AMOUNT': MISSING}], data=None))
        prepared = prepare(
            'INSERT_NODE(route,1,route[2],s) route[3].amount=99 '
            'IF (s=0) AND (PATH_LEN(route)=3) THEN WRITE(route[1]) ELSE WRITE(unused) ENDIF',
            decl='route:PATH NODEDATA=row_t s,unused:INTEGER',
            prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context={'variables': [seed]},
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        candidate, = report['inputs']
        self.assertEqual(candidate['path'], 'ROUTE[2]')
        structured_slot(prepared['context'], candidate, by_path(prepared)['ROUTE[2]']).replace({'AMOUNT': 11})
        self.assertEqual(prepared['context']['variables'][0]['value']['nodes'], [{'AMOUNT': 5}, {'AMOUNT': 11}])

    def test_seed_is_captured_before_status_and_conversion_flag_effects(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=row_t seed:row_t report:ARRAY[2] OF INTEGER wanted,wrong:INTEGER '
            'ROUTINE slot:INTEGER BEGIN seed.amount=23 RETURN 1 END slot '
            'ROUTINE flag:BOOLEAN BEGIN seed.amount=31 RETURN TRUE END flag '
            'BEGIN seed.amount=17 APPEND_NODE(route,seed,report[slot()],flag()) '
            'IF (route[1].amount=17) AND (seed.amount=31) AND (report[1]=0) '
            'THEN WRITE(wanted) ELSE WRITE(wrong) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_seed_conversion_keeps_known_truncation_and_bounded_insert_status(self):
        source = (
            'PROGRAM T TYPE source_t=STRUCTURE amount:REAL ENDSTRUCTURE '
            'target_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=target_t seed:source_t '
            'checks:ARRAY[2] OF INTEGER wanted,unused:INTEGER '
            'ROUTINE slot:INTEGER BEGIN seed.amount=99.75 RETURN 1 END slot '
            'BEGIN seed.amount=-17.75 APPEND_NODE(route,seed,checks[slot()],TRUE) '
            'INSERT_NODE(route,999,seed,checks[2],TRUE) '
            'IF (route[1].amount=-17) AND (checks[1]=0) AND (checks[2]=2) '
            'AND (PATH_LEN(route)=1) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_known_missing_seed_or_converted_short_stops_later_reads(self):
        source = (
            'PROGRAM T TYPE source_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'target_t=STRUCTURE amount:SHORT ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=target_t seeded:source_t codes:ARRAY[1] OF INTEGER unused:INTEGER '
            'ROUTINE slot:INTEGER BEGIN WRITE(unused) RETURN 1 END slot '
            'ROUTINE allow:BOOLEAN BEGIN WRITE(unused) RETURN TRUE END allow '
            'ROUTINE fresh VAR missing:target_t '
            'BEGIN APPEND_NODE(route,missing,codes[slot()],allow()) END fresh '
            'BEGIN {} WRITE(unused) END T'
        )
        for body, code in (
            ('fresh()', 'path-seed'),
            ('seeded.amount=32767 APPEND_NODE(route,seeded,codes[1],TRUE)', 'path-conversion'),
        ):
            with self.subTest(body=body):
                report = prepare_inputs(translate(source.format(body)).python_source)['template']['discovery']
                self.assertFalse(report['inputs'])
                self.assertEqual([row['code'] for row in report['unresolved']], [code])

    def test_incompatible_seed_reports_status_before_rejected_index(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[], data=None))]}
        prepared = prepare(
            'INSERT_NODE(route,999,seed,s,FALSE) '
            'IF (s=3) AND (PATH_LEN(route)=0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='route:PATH NODEDATA=row_t seed:source_t s,wanted,unused:INTEGER',
            prefix=('TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                    'source_t=STRUCTURE amount:REAL ENDSTRUCTURE'), context=context,
        )
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'SEED', 'WANTED'})

    def test_unknown_conversion_flag_preserves_requirements_without_guessing_shape(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[], data=None))]}
        prepared = prepare('APPEND_NODE(route,seed,s,convert) WRITE(route[1])',
                           decl='route:PATH NODEDATA=row_t seed:source_t s:INTEGER convert:BOOLEAN',
                           prefix=('TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                                   'source_t=STRUCTURE amount:REAL ENDSTRUCTURE'), context=context)
        report = prepared['template']['discovery']
        self.assertEqual(set(by_path(prepared)), {'SEED', 'CONVERT'})
        self.assertIn('path-topology', {row['code'] for row in report['unresolved']})

    def test_model_dependent_seed_conversion_remains_unresolved(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['POINT', ['XYZWPR']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=dict(nodes=[], data=None))]}
        prepared = prepare('APPEND_NODE(route,seed,s,TRUE) WRITE(PATH_LEN(route))',
                           decl='route:PATH NODEDATA=row_t seed:source_t s:INTEGER',
                           prefix=('TYPE row_t=STRUCTURE point:XYZWPR ENDSTRUCTURE '
                                   'source_t=STRUCTURE point:JOINTPOS2 ENDSTRUCTURE'), context=context)
        report = prepared['template']['discovery']
        self.assertEqual(set(by_path(prepared)), {'SEED'})
        self.assertIn('path-topology', {row['code'] for row in report['unresolved']})

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

    def test_path_range_discovery_includes_trailing_or_only_header(self):
        prefix = ('TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                  'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE')
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]
        seed = dict(program='T', path='ROUTE', type=spec,
                    value=dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': MISSING}],
                               data={'TOTAL': MISSING}))
        for bounds, expected in (('2..0', {'ROUTE[0]', 'ROUTE[1]', 'ROUTE[2]'}),
                                 ('0..0', {'ROUTE[0]'})):
            with self.subTest(bounds=bounds):
                prepared = prepare(f'WRITE(route[{bounds}])',
                                   decl='route:PATH NODEDATA=row_t PATHHEADER=head_t',
                                   prefix=prefix, context={'variables': [seed]})
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), expected)

    def test_path_write_range_uses_retained_descriptor_after_both_bounds(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR routes:ARRAY[1] OF route_t replacement:route_t s,wanted,unused:INTEGER '
            'ROUTINE shift:INTEGER BEGIN INSERT_NODE(routes[1],1,s) routes[1,1].amount=31 RETURN 2 END shift '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,routes[1],s) RETURN 0 END swap '
            'BEGIN APPEND_NODE(replacement,s) replacement[1].amount=13 replacement.amount=23 '
            'WRITE(routes[1,shift()..swap()]) '
            'IF (PATH_LEN(routes[1])=1) AND (routes[1,1].amount=13) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        row = ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]]
        seed = dict(program='T', path='ROUTES', type=['ARRAY', 1, ['PATH', row, row]],
                    value=[dict(nodes=[{'AMOUNT': MISSING}], data={'AMOUNT': MISSING})])
        prepared = prepare_inputs(translate(source).python_source, context={'variables': [seed]})
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTES[1][0]', 'ROUTES[1][1]', 'WANTED'})

    def test_path_read_range_resolves_replacement_after_first_bound(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement:route_t s,wanted,unused:INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) RETURN 2 END swap '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 '
            'APPEND_NODE(replacement,s) replacement[1].amount=13 '
            'APPEND_NODE(replacement,s) replacement[2].amount=17 '
            'READ(route[swap()..2]) '
            'IF route[1].amount=13 THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], ['input-stream'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_path_read_format_keeps_fields_captured_before_descriptor_replacement(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement:route_t s,wanted,unused:INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) RETURN 3 END swap '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 '
            'APPEND_NODE(replacement,s) replacement[1].amount=13 '
            'READ(route[1..1]::swap()) '
            'IF route[1].amount=13 THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], ['input-stream'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_path_range_stops_before_evaluating_second_bound_after_abort(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t s,unused:INTEGER '
            'ROUTINE halt_now:INTEGER BEGIN ABORT RETURN 1 END halt_now '
            'ROUTINE last:INTEGER BEGIN WRITE(unused) RETURN 1 END last '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 '
            'WRITE(route[halt_now()..last()]) WRITE(unused) END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertFalse(report['inputs'])

    def test_initial_path_bounds_reject_the_whole_transfer_before_inputs(self):
        prefix = ('TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
                  'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE')
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]
        seed = dict(program='T', path='ROUTE', type=spec,
                    value=dict(nodes=[{'AMOUNT': MISSING}], data={'TOTAL': MISSING}))
        for body, context in (('WRITE(route[0..1])', {}), ('WRITE(route[2..0])', {'variables': [seed]}),
                              ('READ(route[0..2])', {'variables': [seed]})):
            with self.subTest(body=body):
                prepared = prepare(body, decl='route:PATH NODEDATA=row_t PATHHEADER=head_t',
                                   prefix=prefix, context=context)
                report = prepared['template']['discovery']
                self.assertEqual(report['inputs'], [])
                self.assertIn('path-topology', {row['code'] for row in report['unresolved']})

    def test_path_range_checks_scalar_width_before_discovering_records(self):
        prepared = prepare(
            'INSERT_NODE(route,1,s) INSERT_NODE(route,2,s) WRITE(route[1..2])',
            decl='route:PATH NODEDATA=row_t s:INTEGER',
            prefix='TYPE row_t=STRUCTURE fields:ARRAY[513] OF INTEGER ENDSTRUCTURE',
        )
        report = prepared['template']['discovery']
        self.assertFalse(report['inputs'])
        unresolved, = report['unresolved']
        self.assertEqual(unresolved['code'], 'selection')
        self.assertIn('transfer limit', unresolved['message'])

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

    def test_direct_procedure_can_forward_and_edit_a_borrowed_path_cell(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR routes:ARRAY[2] OF route_t unused:INTEGER '
            'ROUTINE edit(v:route_t) VAR s:INTEGER '
            'BEGIN INSERT_NODE(v,1,s) v[1].amount=17 DELETE_NODE(v,3,s) END edit '
            'ROUTINE forward(v:route_t) BEGIN edit(v) END forward '
            'BEGIN forward(routes[2]) IF PATH_LEN(routes[2])=2 '
            'THEN WRITE(routes[2,1]) ELSE WRITE(unused) ENDIF WRITE(routes[2,2].amount) END T'
        )
        path = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTES', type=['ARRAY', 2, path],
                                      value=[dict(nodes=[], data=None),
                                             dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': MISSING}], data=None)])]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTES[2][1].AMOUNT'})

    def test_borrowed_path_assignment_stays_independent_of_later_source_writes(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE total:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=head_t '
            'VAR source,target:route_t wanted,unused:INTEGER '
            'ROUTINE assign(v:route_t;seed:route_t) BEGIN v=seed seed.total=31 seed[1].amount=99 END assign '
            'BEGIN source.total=11 source[1].amount=7 assign(target,source) '
            'IF (PATH_LEN(target)=1) AND (target[1].amount=7) AND (target.total=11) AND (source.total=31) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['TOTAL', ['INTEGER']]]]]
        context = {'variables': [dict(program='T', path='SOURCE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data={'TOTAL': MISSING}))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})
        self.assertEqual([row['path'] for row in report['path_storage']], ['SOURCE'])

    def test_path_assignment_updates_borrowed_header_and_detaches_old_whole_node(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE code:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=head_t '
            'VAR route,seed:route_t wanted,unused:INTEGER '
            'ROUTINE replace(v:route_t;head:head_t;held:INTEGER;old:row_t) '
            'BEGIN v=seed WRITE(old.amount) old.amount=31 held=held+1 '
            'IF (head.code=42) AND (v.code=42) AND (v[1].amount=13) AND (old.amount=31) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END replace '
            'BEGIN seed.code=41 seed[1].amount=13 replace(route,route[0],route.code,route[1]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['CODE', ['INTEGER']]]]]
        context = {'variables': [
            dict(program='T', path=path, type=spec,
                 value=dict(nodes=[{'AMOUNT': MISSING}], data={'CODE': MISSING}))
            for path in ('ROUTE', 'SEED')
        ]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1].AMOUNT', 'WANTED'})

    def test_path_assignment_cannot_assume_partial_header_fields_stay_attached(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE code:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=head_t '
            'VAR route,seed:route_t '
            'ROUTINE replace(v:route_t;held:INTEGER) BEGIN v=seed WRITE(held) END replace '
            'BEGIN replace(route,route.code) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['CODE', ['INTEGER']]]]]
        context = {'variables': [dict(program='T', path='SEED', type=spec,
                                      value=dict(nodes=[], data=MISSING))]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']))

    def test_borrowed_header_remains_live_during_in_place_node_edit(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE code:INTEGER total:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=head_t '
            'VAR route:route_t unused:INTEGER '
            'ROUTINE grow(v:route_t;head:head_t) VAR s:INTEGER '
            'BEGIN INSERT_NODE(v,1,s) v[1].amount=17 head.code=s head.total=PATH_LEN(v) END grow '
            'BEGIN grow(route,route[0]) IF (route.code=0) AND (route.total=2) '
            'THEN WRITE(route[2].amount) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['CODE', ['INTEGER']], ['TOTAL', ['INTEGER']]]]]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}],
                                                 data={'CODE': MISSING, 'TOTAL': MISSING}))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        self.assertTrue(prepared['template']['discovery']['complete'], prepared['template']['discovery']['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1].AMOUNT'})

    def test_overlapping_path_service_status_stops_after_evaluating_operands(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': 7}], data=None))]}
        prepared = prepare('DELETE_NODE(route,1,route[1].amount) WRITE(late)',
                           decl='route:PATH NODEDATA=row_t late:INTEGER',
                           prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context=context)
        report = prepared['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertEqual([row['code'] for row in report['unresolved']], ['service-output'])

        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'route_t=PATH NODEDATA=row_t PATHHEADER=row_t '
            'VAR route,source:route_t flag_input,late,s:INTEGER '
            'ROUTINE flag:BOOLEAN BEGIN WRITE(flag_input) RETURN FALSE END flag '
            'BEGIN APPEND_NODE(source,s) source[1].amount=7 source.amount=8 '
            'route.amount=99 COPY_PATH(source,1,1,route,route.amount,flag()) WRITE(late) END T'
        )
        prepared = prepare_inputs(translate(source).python_source)
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], ['service-output'])
        self.assertEqual(set(by_path(prepared)), {'FLAG_INPUT'})

    def test_path_edit_loads_receiver_after_direct_operand_routines(self):
        common = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement,target:route_t seed:row_t s,wanted,unused:INTEGER statuses:ARRAY[1] OF INTEGER '
            'ROUTINE swap:INTEGER BEGIN COPY_PATH(replacement,0,0,route,s) seed.amount=99 RETURN 1 END swap '
            'ROUTINE make_row:row_t VAR value:row_t BEGIN '
            'COPY_PATH(replacement,0,0,route,s) value.amount=17 RETURN value END make_row '
            'BEGIN APPEND_NODE(route,s) route[1].amount=7 '
            'APPEND_NODE(replacement,s) replacement[1].amount=13 '
            'APPEND_NODE(replacement,s) replacement[2].amount=23 seed.amount=17 '
        )
        cases = (
            ('INSERT_NODE(route,swap(),seed,s)', '(s=0) AND (PATH_LEN(route)=3) AND (route[1].amount=99) AND (route[2].amount=13)'),
            ('DELETE_NODE(route,swap(),s)', '(s=0) AND (PATH_LEN(route)=1) AND (route[1].amount=23)'),
            ('APPEND_NODE(route,make_row(),s)', '(s=0) AND (PATH_LEN(route)=3) AND (route[1].amount=13) AND (route[3].amount=17)'),
            ('APPEND_NODE(route,seed,statuses[swap()])',
             '(statuses[1]=0) AND (PATH_LEN(route)=3) AND (route[1].amount=13) AND (route[3].amount=17) AND (seed.amount=99)'),
            ('COPY_PATH(route,1,1,target,statuses[swap()])',
             '(statuses[1]=0) AND (PATH_LEN(target)=1) AND (target[1].amount=7) AND (route[1].amount=13)'),
        )
        for statement, condition in cases:
            with self.subTest(statement=statement):
                source = common + f'{statement} IF {condition} THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
                prepared = prepare_inputs(translate(source).python_source)
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_path_service_status_follows_field_detached_by_conversion_operand(self):
        common = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route,replacement:route_t s,wanted,unused:INTEGER '
            'ROUTINE swap:BOOLEAN BEGIN COPY_PATH(replacement,0,0,route,s) RETURN FALSE END swap '
            'ROUTINE drop:BOOLEAN BEGIN DELETE_NODE(route,1,s) RETURN FALSE END drop '
        )
        for statement, condition in (
            ('APPEND_NODE(route,route[1],route[1].amount,swap())',
             '(PATH_LEN(route)=2) AND (route[1].amount=13) AND (route[2].amount=7)'),
            ('APPEND_NODE(route,route[1],route[1].amount,drop())',
             '(PATH_LEN(route)=1) AND (route[1].amount=7)'),
            ('COPY_PATH(route,0,0,route,route[1].amount,swap())',
             '(PATH_LEN(route)=1) AND (route[1].amount=7)'),
        ):
            with self.subTest(statement=statement):
                source = common + (
                    f'ROUTINE observe(held:INTEGER) BEGIN {statement} '
                    f'IF (held=0) AND {condition} THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END observe '
                    'BEGIN APPEND_NODE(route,s) route[1].amount=7 APPEND_NODE(replacement,s) '
                    'replacement[1].amount=13 observe(route[1].amount) END T'
                )
                prepared = prepare_inputs(translate(source).python_source)
                report = prepared['template']['discovery']
                self.assertTrue(report['complete'], report['unresolved'])
                self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_rejected_node_edit_preserves_a_live_node_alias(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t wanted,unused:INTEGER '
            'ROUTINE attempt(v:route_t; old:row_t) VAR s:INTEGER BEGIN DELETE_NODE(v,99,s) old.amount=s END attempt '
            'BEGIN attempt(route,route[1]) IF (PATH_LEN(route)=1) AND (route[1].amount=2) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_edits_after_borrowed_node_leave_its_position_live(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t unused:INTEGER '
            'ROUTINE edit(v:route_t;held:row_t) VAR s:INTEGER '
            'BEGIN APPEND_NODE(v,s) INSERT_NODE(v,3,s) DELETE_NODE(v,3,s) '
            'held.amount=17 v[3].amount=21 END edit '
            'BEGIN DELETE_NODE(route,1,unused) INSERT_NODE(route,1,unused) '
            'edit(route,route[1]) IF (PATH_LEN(route)=3) AND (route[1].amount=17) '
            'THEN WRITE(route[2].amount,route[3].amount) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': MISSING}], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[2].AMOUNT'})

    def test_forwarded_field_alias_keeps_its_record_when_a_node_shifts(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t unused:INTEGER '
            'ROUTINE shift(v:route_t;held:INTEGER) VAR s:INTEGER '
            'BEGIN DELETE_NODE(v,1,s) WRITE(held) held=17 END shift '
            'ROUTINE forward(held:INTEGER) BEGIN shift(route,held) END forward '
            'BEGIN forward(route[3].amount) IF (PATH_LEN(route)=2) AND (route[2].amount=17) '
            'THEN WRITE(route[1].amount) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        saved = dict(nodes=[{'AMOUNT': MISSING} for _ in range(3)], data=None)
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=saved)]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[2].AMOUNT', 'ROUTE[3].AMOUNT'})

    def test_deleted_node_field_borrow_retains_its_original_saved_address(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t unused:INTEGER '
            'ROUTINE edit(v:route_t;held:INTEGER) VAR s:INTEGER '
            'BEGIN DELETE_NODE(v,1,s) WRITE(held) INSERT_NODE(v,1,s) v[1].amount=23 held=17 '
            'IF (held=17) AND (v[1].amount=23) AND (PATH_LEN(v)=2) '
            'THEN WRITE(v[2].amount) ELSE WRITE(unused) ENDIF END edit '
            'BEGIN edit(route,route[1].amount) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        saved = dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': MISSING}], data=None)
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=saved)]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1].AMOUNT', 'ROUTE[2].AMOUNT'})

    def test_unavailable_borrowed_node_origin_does_not_count_as_detached(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t '
            'ROUTINE edit(v:route_t;held:INTEGER) VAR s:INTEGER '
            'BEGIN DELETE_NODE(v,1,s) WRITE(held) END edit '
            'BEGIN edit(route,route[3].amount) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        saved = dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': MISSING}], data=None)
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=saved)]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']))

    def test_whole_node_follows_captured_slot_after_second_insertion(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t s,wanted,unused:INTEGER '
            'ROUTINE update(v:route_t;held:row_t) VAR status:INTEGER '
            'BEGIN INSERT_NODE(v,2,status) v[2].amount=17 '
            'IF held.amount=17 THEN held.amount=23 ENDIF '
            'IF v[2].amount=23 THEN WRITE(v[3].amount,wanted) ELSE WRITE(unused) ENDIF END update '
            'BEGIN INSERT_NODE(route,1,s) update(route,route[2]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1].AMOUNT', 'WANTED'})

    def test_rejected_copy_does_not_invalidate_borrowed_header_or_node(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'other_t=STRUCTURE count:INTEGER ENDSTRUCTURE '
            'head_t=STRUCTURE code:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t PATHHEADER=head_t '
            'VAR route:route_t other:PATH NODEDATA=other_t wanted,unused:INTEGER '
            'ROUTINE attempt(v:route_t;head:head_t;held:row_t) VAR s:INTEGER '
            'BEGIN COPY_PATH(other,0,0,v,s) head.code=s '
            'COPY_PATH(v,1,99,v,s) held.amount=s END attempt '
            'BEGIN attempt(route,route[0],route[1]) '
            'IF (route.code=3) AND (PATH_LEN(route)=1) AND (route[1].amount=2) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]],
                ['STRUCTURE', 'HEAD_T', [['CODE', ['INTEGER']]]]]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data={'CODE': MISSING}))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_self_copy_preserves_detached_whole_node_borrow(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t wanted,unused:INTEGER '
            'ROUTINE replace(v:route_t;held:row_t) VAR s:INTEGER '
            'BEGIN COPY_PATH(v,0,0,v,s) held.amount=29 INSERT_NODE(v,1,s) v[1].amount=34 '
            'IF (held.amount=29) AND (v[2].amount=15) AND (PATH_LEN(v)=2) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END replace '
            'BEGIN route[1].amount=15 replace(route,route[1]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_copy_with_unavailable_captured_destination_slot_remains_unresolved(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t '
            'ROUTINE replace(v:route_t;held:row_t) VAR s:INTEGER '
            'BEGIN COPY_PATH(v,0,0,v,s) WRITE(held.amount) END replace '
            'BEGIN replace(route,route[2]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']))

    def test_nested_delete_distinguishes_whole_slot_from_original_field(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t '
            'ROUTINE edit(v:route_t;old:row_t;field:INTEGER) VAR s:INTEGER '
            'BEGIN DELETE_NODE(v,1,s) WRITE(old.amount,field) END edit '
            'ROUTINE forward(old:row_t;field:INTEGER) BEGIN edit(route,old,field) END forward '
            'BEGIN forward(route[1],route[1].amount) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': MISSING}], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'ROUTE[1].AMOUNT', 'ROUTE[2].AMOUNT'})

    def test_operand_call_updates_earlier_captured_node_slot(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t unused:INTEGER '
            'ROUTINE edit(v:route_t) VAR s:INTEGER BEGIN INSERT_NODE(v,1,s) v[1].amount=17 END edit '
            'ROUTINE later:INTEGER BEGIN edit(route) RETURN 0 END later '
            'ROUTINE use(old:row_t;ignored:INTEGER) BEGIN '
            'IF old.amount<>17 THEN WRITE(unused) ENDIF WRITE(old.amount) END use '
            'BEGIN use(route[1],later()) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertFalse(report['inputs'])

    def test_unmodeled_effect_hides_captured_slot_origin_without_prior_edit(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t address:STRING[20] '
            'ROUTINE edit(held:row_t) VAR entry,s:INTEGER '
            "BEGIN entry=0 SET_VAR(entry,'',address,17,s) WRITE(held.amount) END edit "
            'BEGIN edit(route[1]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertEqual(set(by_path(prepared)), {'ADDRESS'})
        self.assertIn('path-topology', {row['code'] for row in report['unresolved']})

    def test_whole_node_slot_recovers_when_same_list_grows(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=row_t s,wanted,unused:INTEGER '
            'ROUTINE restore(held:row_t) BEGIN DELETE_NODE(route,1,s) '
            'IF (s=0) AND (PATH_LEN(route)=0) THEN APPEND_NODE(route,s) held.amount=11 ENDIF '
            'END restore '
            'BEGIN restore(route[1]) IF (PATH_LEN(route)=1) AND (route[1].amount=11) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        prepared = prepare_inputs(translate(source).python_source, context=context)
        report = prepared['template']['discovery']
        self.assertTrue(report['complete'], report['unresolved'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})
        self.assertEqual(report['path_storage'][0]['path'], 'ROUTE')

    def test_reading_a_temporarily_missing_whole_node_reports_the_slot(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=row_t s:INTEGER '
            'ROUTINE attempt(held:row_t) BEGIN DELETE_NODE(route,1,s) WRITE(held.amount) END attempt '
            'BEGIN attempt(route[1]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertTrue(any(row['message'] == 'Captured PATH slot is out of bounds: ROUTE[1]'
                            for row in report['unresolved']))

    def test_append_cannot_make_an_initially_invalid_capture_valid(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=row_t s:INTEGER '
            'ROUTINE attempt(held:row_t) BEGIN APPEND_NODE(route,s) WRITE(held.amount) END attempt '
            'BEGIN attempt(route[2]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']))

    def test_new_list_does_not_restore_a_retired_missing_slot(self):
        prefix = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE '
            'VAR route:PATH NODEDATA=row_t s:INTEGER '
            'ROUTINE attempt(held:row_t) BEGIN DELETE_NODE(route,1,s) '
            'COPY_PATH(route,0,0,route,s) APPEND_NODE(route,s) route[1].amount=19 '
            'WRITE(route[1].amount) '
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        for use in ('', 'WRITE(held.amount) '):
            with self.subTest(use=use):
                source = prefix + use + 'END attempt BEGIN attempt(route[1]) END T'
                report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
                self.assertFalse(report['inputs'])
                self.assertEqual(report['complete'], not use, report['unresolved'])
                if use:
                    self.assertTrue(any(row['message'] == 'Captured PATH slot is out of bounds: ROUTE[1]'
                                        for row in report['unresolved']))

    def test_whole_path_topology_remains_unresolved_after_unknown_mutation(self):
        prefix = 'TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE'
        path = ['PATH', ['STRUCTURE', 'NODE_T', [['AMOUNT', ['INTEGER']]]], None]
        seed = dict(nodes=[{'AMOUNT': 7}], data=None)
        context = {'variables': [
            dict(program='T', path='ROUTE', type=path, value=seed),
            dict(program='T', path='ROUTES', type=['ARRAY', 1, path], value=[seed]),
        ]}
        decl = 'route:PATH NODEDATA=node_t routes:ARRAY[1] OF PATH NODEDATA=node_t s,i:INTEGER b:BOOLEAN address:STRING[10]'
        for body, unknown, captured in (
            ('INSERT_NODE(route,i,s) WRITE(route)', 'ROUTE', set()),
            ('routes[i]=route WRITE(routes)', 'ROUTES', set()),
            ("SET_VAR(i,'',address,route,s)\nWRITE(route)", 'ROUTE', {'ROUTE[1]'}),
            ('WHILE b DO WRITE(route) DELETE_NODE(route,1,s) ENDWHILE', 'ROUTE', set()),
        ):
            with self.subTest(body=body):
                prepared = prepare(body, decl=decl, prefix=prefix, context=context)
                report = prepared['template']['discovery']
                self.assertTrue(any(row['code'] == 'schema' and row['message'].endswith(unknown)
                                    for row in report['unresolved']), report)
                path_inputs = [row for row in report['inputs'] if row['root_path'] == unknown]
                self.assertEqual({row['path'] for row in path_inputs}, captured)
                for row in path_inputs:
                    self.assertEqual([site['line'] for site in row['locations']], [1])

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
