"""Discovery, editing and replay of saved TP positions and pose tolerances."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner, runtime as rt, translate
from karel2py.input_template import InputTemplateError, prepare_inputs
from karel2py.storage import typed_value
from karel2py.structured_inputs import structured_slot
from tests.test_extended_services import pose, run
from tests.test_input_robot_tables import robot_configuration
from tests.test_input_template import by_path, prepare


def teach_context(*, rows=(), bound=True):
    return {'teach_programs': {
        'programs': {'draftTp': {'position_registers': list(rows)}, 'OTHER': {}},
        'callers': {'T': 'draftTp'} if bound else {},
        'groups': [1, 2], 'position_register_limit': 4, 'selected': 'OTHER',
    }}


def prepared_run(folder, source, context):
    target = folder / 'program.py'
    target.write_text(translate(source).python_source, encoding='utf-8')
    document = folder / 'session.json'
    runner.create_document(target, document, context=context, discover=True)
    return document


class TeachPositionDiscoveryTests(unittest.TestCase):
    def assert_discovery(self, prepared, names, codes=()):
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], list(codes), report['unresolved'])
        self.assertEqual(report['complete'], not codes)
        self.assertEqual(set(by_path(prepared)), set(names))

    def test_teach_setters_metadata_padding_and_global_bank_are_independent(self):
        context = teach_context(rows=[{'group': 2, 'number': 1, 'uframe': 7, 'utool': 8,
                                       'value': typed_value(pose(5))}])
        context['positions'] = {'groups': [2], 'count': 3, 'values': {}}
        original = deepcopy(context)
        prepared = prepare(
            "CNV_STR_CONF('N',cfg,s) p=POS(9,0,0,0,0,0,cfg,1,2,3) "
            "SET_TPE_POS_REG(1,p,s) SET_TPE_EPOS_REG(2,p,s,2) "
            "j[1]=7.0 j[2]=8.0 SET_TPE_JPOS_REG(3,j,s,2) SET_POS_REG(1,p,s,2) "
            "TPE_POS_REG_FRM(1,frame_id,tool_id,s) TPE_POS_REG_TYPE(3,2,kind,axes,s) "
            "IF (s=0) AND (frame_id=7) AND (tool_id=8) AND (kind=9) AND (axes=2) "
            "AND (GET_TPE_POS_REG(1,s).ext1=0.0) AND (GET_TPE_POS_REG(2,s,2).ext3=3.0) "
            "AND (GET_TPE_JPOS_REG(3,s,2)[9]=0.0) AND (GET_POS_REG(1,s,2).ext1=1.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            prefix='%DEFGROUP=2\n',
            decl='cfg:CONFIG p:XYZWPREXT j:JOINTPOS2 s,frame_id,tool_id,kind,axes,wanted,unused:INTEGER',
            context=context,
        )
        self.assert_discovery(prepared, ['WANTED'])
        self.assertEqual(context, original)

    def test_saved_tp_row_is_editable_at_original_program_and_ordered_slot(self):
        context = teach_context(rows=[
            {'group': 1, 'number': 1, 'value': typed_value(pose(55))},
            {'group': 2, 'number': 1, 'uframe': 7, 'utool': 8, 'value': typed_value(pose(5))},
        ])
        prepared = prepare(
            "TPE_POS_REG_FRM(1,2,f,t,s) "
            "IF (f=7) AND (t=8) THEN "
            "IF GET_TPE_POS_REG(1,s,2).x=5.0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF "
            "ELSE WRITE(unused) ENDIF",
            decl='f,t,s,wanted,alternate,unused:INTEGER', context=context,
        )
        self.assert_discovery(prepared, ['1[group=2]', 'WANTED', 'ALTERNATE'])
        binding = by_path(prepared)['1[group=2]']
        self.assertEqual(binding['context_pointer'], '/teach_programs/programs/draftTp/position_registers/1/value')
        self.assertEqual(binding['status'], 'supplied')
        candidate = next(row for row in prepared['template']['discovery']['inputs'] if row['path'] == '1[group=2]')
        self.assertEqual(candidate['program'], 'DRAFTTP')
        slot = structured_slot(prepared['context'], candidate, binding)
        self.assertEqual(slot.draft(candidate['path']).spec, ('XYZWPR',))
        slot.replace(typed_value(pose(7))['value'])
        row = prepared['context']['teach_programs']['programs']['draftTp']['position_registers'][1]
        self.assertEqual((row['uframe'], row['utool'], row['value']['value']['X']), (7, 8, 7.0))

    def test_missing_tp_position_row_can_be_created_and_replayed(self):
        source = ('PROGRAM T VAR s:INTEGER BEGIN '
                  'WRITE(GET_TPE_JPOS_REG(1,s,2)[2]) END T')
        with TemporaryDirectory() as temp:
            path = prepared_run(Path(temp), source, teach_context())
            initial = path.read_bytes()
            first = json.loads(initial)
            binding = first['inputs']['template']['bindings'][0]
            self.assertEqual((binding['status'], binding['context_pointer']),
                             ('missing', '/teach_programs/programs/draftTp/position_registers/0/value'))
            updated, revision = runner.save_input_structure(
                path, ('teach_position_register', 'DRAFTTP', '1[group=2]'), {'axes': [0.0, 7.0]+[0.0]*7},
                expected=initial,
            )
            self.assertEqual(updated['inputs']['template']['bindings'][0]['status'], 'supplied')
            result = runner.run_document(path, expected=revision)
            self.assertEqual(float(result['results']['text_output'].strip()), 7.0)

    def test_missing_address_and_caller_status_preserve_metadata_outputs(self):
        prepared = prepare(
            'f=7 t=8 TPE_POS_REG_FRM(3,f,t,s) TPE_POS_REG_TYPE(5,2,k,a,bad) '
            'IF (s=17038) AND (bad=2) AND (f=7) AND (t=8) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='f,t,s,k,a,bad,wanted,unused:INTEGER', context=teach_context(),
        )
        self.assert_discovery(prepared, ['WANTED'])
        unbound = prepare(
            'TPE_POS_REG_TYPE(1,k,a,s) IF s=9 THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='k,a,s,wanted,unused:INTEGER', context=teach_context(bound=False),
        )
        self.assert_discovery(unbound, ['WANTED'])

    def test_wrong_representation_rejects_tp_getter_with_a_robot_present(self):
        config = teach_context()
        config['robot'] = robot_configuration()
        prepared = prepare(
            'j[1]=0.0 SET_TPE_JPOS_REG(1,j,s) p=GET_TPE_POS_REG(1,s) WRITE(unreachable)',
            decl='j:JOINTPOS1 p:XYZWPREXT s,unreachable:INTEGER', context=config,
        )
        self.assert_discovery(prepared, [], ['position-read'])
        self.assertIn('different representation', prepared['template']['discovery']['unresolved'][0]['message'])

    def test_unknown_write_address_keeps_prior_bank_row_conservative(self):
        prepared = prepare(
            "CNV_STR_CONF('N',cfg,s) p=POS(100,0,0,0,0,0,cfg) "
            "SET_TPE_POS_REG(1,p,s) p.x=30.0 SET_TPE_POS_REG(address,p,s) "
            "IF GET_TPE_POS_REG(1,s).x=100.0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF",
            decl='cfg:CONFIG p:XYZWPR s,address,wanted,alternate:INTEGER', context=teach_context(),
        )
        self.assert_discovery(prepared, ['ADDRESS', '1[group=1]', 'WANTED', 'ALTERNATE'], ['teach-position'])


class PoseToleranceDiscoveryTests(unittest.TestCase):
    def test_pose_tolerance_config_is_shared_with_runner_and_keeps_exact_bounds(self):
        source = """PROGRAM T
VAR a,b:XYZWPREXT flag,beyond:BOOLEAN cfg:CONFIG s,wanted,unused:INTEGER
BEGIN
  CNV_STR_CONF('N',cfg,s)
  a=POS(0,0,0,0,0,0,cfg,0,0,0)
  b=POS(3,4,0,0,0,0,cfg,0.5,0,0)
  flag=a>=<b
  b.ext1=0.51
  beyond=a>=<b
  IF flag AND (NOT beyond) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF
END T
"""
        context = {'pose_tolerance': [5, 0, True], 'external_tolerance': [0.5, 0, 0],
                   'variables': [{'program': 'T', 'path': 'WANTED', 'type': ['INTEGER'], 'value': 87}]}
        with TemporaryDirectory() as temp:
            path = prepared_run(Path(temp), source, context)
            saved = json.loads(path.read_bytes())
            template = saved['inputs']['template']
            self.assertTrue(template['discovery']['complete'], template['discovery']['unresolved'])
            self.assertEqual([row['path'] for row in template['bindings']], ['WANTED'])
            result = runner.run_document(path)
            self.assertEqual(result['results']['variables']['FLAG'], True)
            self.assertEqual(result['results']['variables']['BEYOND'], False)
            self.assertEqual(result['results']['text_output'].strip(), '87')
            self.assertEqual(result['results']['context']['pose_tolerance'], [5.0, 0.0, True])

    def test_compare_joint_value_uses_saved_model_and_scalar_external_tolerance(self):
        prepared = prepare(
            "joint[1]=0.0 p=POS(100,0,0,0,0,0,CURPOS().config_data) "
            "IF joint>=<p THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='joint:JOINTPOS1 p:XYZWPR wanted,unused:INTEGER',
            context={'robot': robot_configuration(), 'pose_tolerance': [0, 0, True], 'external_tolerance': 0},
        )
        self.assertTrue(prepared['template']['discovery']['complete'])
        self.assertEqual(set(by_path(prepared)), {'WANTED'})

    def test_plain_pose_needs_only_base_tolerance_and_respects_config_flag(self):
        body = (
            "CNV_STR_CONF('N',cfg,s) a=POS(0,0,0,0,0,0,cfg) "
            "CNV_STR_CONF('F',cfg,s) b=POS(0,0,0,0,0,0,cfg) "
            "IF a>=<b THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF"
        )
        for check_config, name in ((True, 'ALTERNATE'), (False, 'WANTED')):
            with self.subTest(check_config=check_config):
                prepared = prepare(body, decl='a,b:XYZWPR cfg:CONFIG s,wanted,alternate:INTEGER',
                                   context={'pose_tolerance': [0, 0, check_config]})
                self.assertEqual(set(by_path(prepared)), {name})
                self.assertEqual(prepared['template']['requirements'][0]['code'], 'value')
                self.assertFalse(any(row['code'] == 'service' for row in prepared['template']['requirements']))

    def test_missing_external_tolerance_has_its_own_requirement(self):
        prepared = prepare(
            "CNV_STR_CONF('N',cfg,s) p=POS(0,0,0,0,0,0,cfg,0,0,0) "
            "IF p>=<p THEN WRITE(first) ELSE WRITE(second) ENDIF",
            decl='p:XYZWPREXT cfg:CONFIG s,first,second:INTEGER', context={'pose_tolerance': [0, 0, False]},
        )
        self.assertEqual(set(by_path(prepared)), {'FIRST', 'SECOND'})
        self.assertEqual([row['service'] for row in prepared['template']['requirements'] if row['code'] == 'service'],
                         ['external_tolerance'])

    def test_explicit_program_options_override_saved_values_independently(self):
        context = rt.ExecutionContext.from_config({'pose_tolerance': [1, 0, False], 'external_tolerance': 0})
        self.assertEqual(context.to_config(), {'pose_tolerance': [1.0, 0.0, False], 'external_tolerance': [0.0, 0.0, 0.0]})
        values = run(
            "CNV_STR_CONF('N',cfg,s) a=POS(0,0,0,0,0,0,cfg,0,0,0) b=POS(0.5,0,0,0,0,0,cfg,0,0,0) flag=a>=<b",
            decl='a,b:XYZWPREXT cfg:CONFIG s:INTEGER flag:BOOLEAN',
            context=context, pose_tolerance=(0, 0, False),
        )
        self.assertFalse(values['FLAG'])

    def test_invalid_saved_tolerances_fail_context_validation(self):
        for context in ({'pose_tolerance': [True, 0, False]}, {'pose_tolerance': [0, 181, False]},
                        {'external_tolerance': [0, -1, 0]}, {'external_tolerance': 10**400}):
            with self.subTest(context=context), self.assertRaises(InputTemplateError):
                prepare('x=1', decl='x:INTEGER', context=context)
