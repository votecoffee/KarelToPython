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

    def test_overlapping_service_status_does_not_establish_an_edit(self):
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': 7}], data=None))]}
        prepared = prepare('DELETE_NODE(route,1,route[1].amount) WRITE(route[1])',
                           decl='route:PATH NODEDATA=row_t',
                           prefix='TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE', context=context)
        report = prepared['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertIn('path-topology', {row['code'] for row in report['unresolved']})

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

    def test_deleting_borrowed_field_record_stays_unresolved(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t '
            'ROUTINE edit(v:route_t;held:INTEGER) VAR s:INTEGER '
            'BEGIN DELETE_NODE(v,1,s) WRITE(held) END edit '
            'BEGIN edit(route,route[1].amount) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        saved = dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': MISSING}], data=None)
        context = {'variables': [dict(program='T', path='ROUTE', type=spec, value=saved)]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']))

    def test_saved_node_origin_does_not_override_current_slot_in_alias_guard(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t s:INTEGER '
            'ROUTINE update(v:route_t;held:row_t) VAR status:INTEGER '
            'BEGIN INSERT_NODE(v,2,status) WRITE(held.amount) END update '
            'BEGIN INSERT_NODE(route,1,s) update(route,route[2]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']))

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

    def test_valid_copy_may_rebind_a_live_borrow_and_stays_unresolved(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t '
            'ROUTINE replace(v:route_t;held:row_t) VAR s:INTEGER '
            'BEGIN COPY_PATH(v,0,0,v,s) WRITE(held.amount) END replace '
            'BEGIN replace(route,route[1]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']))

    def test_descendant_borrow_in_ancestor_frame_blocks_a_nested_edit(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t '
            'ROUTINE edit(v:route_t) VAR s:INTEGER BEGIN DELETE_NODE(v,1,s) END edit '
            'ROUTINE forward(old:row_t) BEGIN edit(route) WRITE(old.amount) END forward '
            'BEGIN forward(route[1]) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}, {'AMOUNT': 42}], data=None))]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']))

    def test_operand_call_cannot_rebind_an_earlier_captured_path_argument(self):
        source = (
            'PROGRAM T TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE route_t=PATH NODEDATA=row_t '
            'VAR route:route_t '
            'ROUTINE edit(v:route_t) VAR s:INTEGER BEGIN INSERT_NODE(v,1,s) v[1].amount=17 END edit '
            'ROUTINE later:INTEGER BEGIN edit(route) RETURN 0 END later '
            'ROUTINE use(old:row_t;ignored:INTEGER) BEGIN WRITE(old.amount) END use '
            'BEGIN use(route[1],later()) END T'
        )
        spec = ['PATH', ['STRUCTURE', 'ROW_T', [['AMOUNT', ['INTEGER']]]], None]
        context = {'variables': [dict(program='T', path='ROUTE', type=spec,
                                      value=dict(nodes=[{'AMOUNT': MISSING}], data=None))]}
        report = prepare_inputs(translate(source).python_source, context=context)['template']['discovery']
        self.assertFalse(report['inputs'])
        self.assertTrue(any('Captured PATH reference has an unresolved origin' in row['message']
                            for row in report['unresolved']))

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
