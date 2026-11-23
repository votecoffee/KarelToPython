"""Discovery of source kinematics calls, assignment order and CONFIG operands."""
import unittest
from unittest import mock

from karel2py import translate
from karel2py.input_template import prepare_inputs
from tests.test_input_robot_tables import robot_configuration
from tests.test_input_template import by_path, prepare


EXTERNAL_MODEL = {'robot': {
    'dh': [{'a': 100.0, 'min': 0.0, 'max': 0.0}, {'type': 'prismatic', 'min': 0.0, 'max': 100.0}],
    'external_axes': 1,
    'current': {'joints': {'type': ['JOINTPOS', 2], 'value': [0.0, 42.0]}},
}}


class InputKinematicsTests(unittest.TestCase):
    def assert_discovery(self, prepared, paths, gaps=()):
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], list(gaps), report['unresolved'])
        self.assertEqual(set(by_path(prepared)), set(paths))
        self.assertEqual(report['complete'], not gaps)

    def test_forward_inverse_and_external_array_prefix(self):
        prepared = prepare(
            "CNV_STR_CONF('N',cfg,status) frm=POS(10,0,0,0,0,0,cfg) tool=POS(0,0,0,0,0,0,cfg) "
            "j=CURJPOS() axes[1,1]=77.0 "
            "JOINT2POS(j,frm,tool,0,p,cfg,axes[2],status) "
            "POS2JOINT(j,p,frm,tool,0,cfg,axes[2],out,status) "
            "IF (status=0) AND (p.x=90.0) AND (p.z=42.0) AND (p.ext1=42.0) "
            "AND (axes[1,1]=77.0) AND (axes[2,1]=42.0) AND (out[2]=42.0) AND (out[3]=0.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='cfg:CONFIG frm,tool:POSITION j:JOINTPOS out:JOINTPOS3 p:XYZWPREXT '
                 'axes:ARRAY[2,1]OF REAL status,wanted,unused:INTEGER',
            context=EXTERNAL_MODEL,
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_forward_outputs_follow_all_pose_representations_and_config(self):
        for spec, coordinate in (('POSITION', 'p.location.x'), ('XYZWPR', 'p.x'), ('XYZWPREXT', 'p.x')):
            with self.subTest(spec=spec):
                prepared = prepare(
                    "CNV_STR_CONF('F',cfg,s) f=POS(0,0,0,0,0,0,cfg) j=CURJPOS() "
                    "JOINT2POS(j,f,f,0,p,cfg,axes,s) "
                    f"IF ({coordinate}=100.0) AND (s=0) AND cfg.cfg_flip AND (axes[3]=0.0) "
                    "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
                    decl=f'cfg:CONFIG f:POSITION p:{spec} j:JOINTPOS axes:ARRAY[3]OF REAL s,wanted,unused:INTEGER',
                    context={'robot': robot_configuration()},
                )
                self.assert_discovery(prepared, ['WANTED'])

    def test_zero_external_axis_model_still_evaluates_array_selector_once(self):
        code = translate(
            "PROGRAM T VAR frm,point:POSITION cfg:CONFIG axes:ARRAY[2,1]OF REAL "
            "j,out:JOINTPOS1 s,visits,wanted,unused:INTEGER "
            "ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN 2 END pick "
            "BEGIN visits=0 CNV_STR_CONF('N',cfg,s) "
            "frm=POS(0,0,0,0,0,0,cfg) point=POS(100,0,0,0,0,0,cfg) j[1]=0.0 "
            "POS2JOINT(j,point,frm,frm,0,cfg,axes[pick()],out,s) "
            "IF (s=0) AND (visits=1) AND (out[1]=0.0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        prepared = prepare_inputs(code.python_source, context={'robot': robot_configuration()})
        self.assert_discovery(prepared, ['WANTED'])

    def test_dynamic_forward_data_keeps_branches_and_unrelated_facts(self):
        prepared = prepare(
            "CNV_STR_CONF('N',cfg,s) f=POS(0,0,0,0,0,0,cfg) "
            "j[1]=angle keep=7 JOINT2POS(j,f,f,0,p,cfg,axes,s) "
            "IF keep=7 THEN IF p.x=100.0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF "
            "ELSE WRITE(unused) ENDIF",
            decl='cfg:CONFIG f:POSITION p:XYZWPR j:JOINTPOS1 axes:ARRAY[3]OF REAL '
                 'angle:REAL s,keep,wanted,alternate,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['ANGLE', 'WANTED', 'ALTERNATE'], ['robot-conversion'])

    def test_inverse_budget_does_not_publish_a_known_answer(self):
        with mock.patch('karel2py.input_robot_values.MODEL_SAMPLE_LIMIT', 1):
            prepared = prepare(
                "CNV_STR_CONF('N',cfg,s) f=POS(0,0,0,0,0,0,cfg) p=POS(0,0,42,0,0,0,cfg) j[1]=0.0 "
                "POS2JOINT(j,p,f,f,0,cfg,axes,out,s) "
                "IF s=0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF",
                decl='cfg:CONFIG f,p:POSITION j,out:JOINTPOS1 axes:ARRAY[3]OF REAL s,wanted,alternate:INTEGER',
                context={'robot': {'dh': [{'type': 'prismatic', 'min': 0.0, 'max': 100.0}]}},
            )
        self.assert_discovery(prepared, ['WANTED', 'ALTERNATE'], ['robot-conversion'])
        self.assertIn('model-sample limit', prepared['template']['discovery']['unresolved'][0]['message'])

    def test_proven_forward_validation_failure_stops_before_downstream_reads(self):
        prepared = prepare(
            "CNV_STR_CONF('N',cfg,s) f=POS(0,0,0,0,0,0,cfg) j=CURJPOS() "
            "JOINT2POS(j,f,f,1,p,cfg,axes,s) WRITE(unreachable)",
            decl='cfg:CONFIG f,p:POSITION j:JOINTPOS axes:ARRAY[3]OF REAL s,unreachable:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, [], ['robot-conversion'])
        self.assertIn('config_ref=0', prepared['template']['discovery']['unresolved'][0]['message'])

    def test_forward_rejects_pose_and_config_outputs_that_overlap(self):
        prepared = prepare(
            "CNV_STR_CONF('N',cfg,s) f=POS(0,0,0,0,0,0,cfg) j=CURJPOS() "
            "JOINT2POS(j,f,f,0,p,p.config_data,axes,s) WRITE(unreachable)",
            decl='cfg:CONFIG f,p:POSITION j:JOINTPOS axes:ARRAY[3]OF REAL s,unreachable:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, [], ['service-output'])

    def test_assignment_uses_selected_tables_before_target_selector_side_effect(self):
        translated = translate(
            "PROGRAM T VAR cells:ARRAY[1]OF XYZWPREXT j:JOINTPOS1 wanted,unused:INTEGER "
            "ROUTINE slot:INTEGER BEGIN $MNUFRAMENUM[1]=2 RETURN 1 END slot "
            "BEGIN j[1]=0.0 cells[slot()]=j "
            "IF (cells[1].x=100.0) AND (CURPOS().x=90.0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        prepared = prepare_inputs(translated.python_source, context={'robot': robot_configuration()})
        self.assert_discovery(prepared, ['WANTED'])

    def test_joint_pose_assignments_round_trip_with_source_table_update(self):
        prepared = prepare(
            '$MNUFRAMENUM[1]=2 $GROUP[1].$UFRAME.location.x=20.0 '
            'j=CURJPOS() p=j reconstructed=p '
            'IF (p.x=80.0) AND (reconstructed[1]=0.0) AND (reconstructed[9]=0.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='j,reconstructed:JOINTPOS p:XYZWPREXT wanted,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_config_text_profiles_and_invalid_parse_keep_prior_configuration(self):
        prepared = prepare(
            "CNV_STR_CONF('F, 3',cfg,s,2) CNV_STR_CONF('bad',cfg,bad_status,2) "
            "CNV_CNF_STRG(cfg,text,render_status,2) CNV_CONF_STR(cfg,full) "
            "IF (s=0) AND (bad_status=1) AND (render_status=0) AND (text='F, 3') "
            "AND (full='F R D B, 3, 0, 0') THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='cfg:CONFIG text,full:STRING[32] s,bad_status,render_status,wanted,unused:INTEGER',
            context={'config_text': {'2': {'flags': ['flip'], 'turns': [1]}}},
        )
        self.assert_discovery(prepared, ['WANTED'])
