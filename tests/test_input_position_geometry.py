"""Discovery of offline model-backed position registers and joint geometry."""
from copy import deepcopy
import unittest
from unittest import mock

from karel2py import translate
from karel2py.input_template import prepare_inputs
from tests.test_input_kinematics import EXTERNAL_MODEL
from tests.test_input_robot_tables import robot_configuration
from tests.test_input_template import by_path, prepare


def bank_context(*, robot=None, groups=(1,), count=3, values=None):
    return {'robot': robot if robot is not None else robot_configuration(),
            'positions': {'count': count, 'groups': list(groups), 'values': values or {}}}


class InputPositionAndGeometryTests(unittest.TestCase):
    def assert_discovery(self, prepared, inputs, gaps=()):
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], list(gaps), report['unresolved'])
        self.assertEqual(set(by_path(prepared)), set(inputs))
        self.assertEqual(report['complete'], not gaps)

    def test_position_setters_and_cross_getters_publish_checked_shapes(self):
        context = bank_context()
        original = deepcopy(context)
        prepared = prepare(
            '$MNUFRAMENUM[1]=2 joint[1]=0.0 SET_POS_REG(1,joint,s) SET_EPOS_REG(2,joint,s) '
            'poses=GET_POS_REG(2,s) SET_JPOS_REG(3,poses,s) '
            'POS_REG_TYPE(1,kind,axes,first) POS_REG_TYPE(3,jkind,jaxes,third) '
            'decomposed=GET_JPOS_REG(1,s) other=GET_POS_REG(3,s) '
            'IF (first=0) AND (third=0) AND (kind=6) AND (axes=3) AND (jkind=9) AND (jaxes=9) '
            'AND (s=0) AND (other.x=90.0) AND (decomposed[9]=0.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='joint:JOINTPOS1 decomposed:JOINTPOS poses,other:XYZWPREXT '
                 's,first,third,kind,axes,jkind,jaxes,wanted,unused:INTEGER',
            context=context,
        )
        self.assert_discovery(prepared, ['WANTED'])
        self.assertEqual(context, original)
        self.assertEqual(prepared['context']['positions'], original['positions'])

    def test_explicit_register_group_overrides_callers_robot_group(self):
        first, second = robot_configuration(), robot_configuration()
        second['dh'][0]['a'] = 200.0
        robot = {'active_group': 1, 'groups': {'1': first, '2': second}}
        prepared = prepare(
            'joint[1]=0.0 SET_JPOS_REG(1,joint,s,2) '
            'before=GET_POS_REG(1,s,2).x $MNUFRAMENUM[2]=2 '
            'after=GET_POS_REG(1,s,2).x SET_POS_REG(2,joint,s,2) '
            'IF (s=0) AND (before=200.0) AND (after=190.0) AND (GET_POS_REG(2,s,2).x=190.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='joint:JOINTPOS1 before,after:REAL s,wanted,unused:INTEGER',
            context=bank_context(robot=robot, groups=(1, 2)),
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_register_model_uses_captured_source_and_frame_after_status_selector(self):
        generated = translate(
            'PROGRAM T VAR joint:JOINTPOS1 codes:ARRAY[1]OF INTEGER status,wanted,unused:INTEGER '
            'ROUTINE slot:INTEGER BEGIN joint[1]=5.0 $MNUFRAMENUM[1]=2 RETURN 1 END slot '
            'BEGIN joint[1]=0.0 SET_POS_REG(1,joint,codes[slot()]) '
            'IF (codes[1]=0) AND (joint[1]=5.0) AND (GET_POS_REG(1,status).x=90.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(generated.python_source, context=bank_context())
        self.assert_discovery(prepared, ['WANTED'])

    def test_saved_cross_model_register_keeps_editable_type_and_related_branches(self):
        prepared = prepare(
            'keep=7 pose=GET_POS_REG(1,s) '
            'IF keep=7 THEN IF pose.x=100.0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF '
            'ELSE WRITE(unused) ENDIF',
            decl='pose:XYZWPREXT keep,s,wanted,alternate,unused:INTEGER',
            context=bank_context(values={'1': {'type': ['JOINTPOS', 1], 'value': [0.0]}}),
        )
        self.assert_discovery(prepared, ['1[group=1]', 'WANTED', 'ALTERNATE'], ['position-model'])
        self.assertEqual(prepared['context']['positions']['values']['1']['type'], ['JOINTPOS', 1])

    def test_unknown_model_setter_preserves_independent_register_facts(self):
        prepared = prepare(
            'j[1]=0.0 SET_JPOS_REG(2,j,s) j[1]=angle SET_POS_REG(1,j,modeled) '
            'IF GET_POS_REG(2,s).x=100.0 THEN '
            'IF modeled=0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF ELSE WRITE(unused) ENDIF',
            decl='j:JOINTPOS1 angle:REAL s,modeled,wanted,alternate,unused:INTEGER',
            context=bank_context(),
        )
        self.assert_discovery(prepared, ['ANGLE', 'WANTED', 'ALTERNATE'], ['position-model'])

    def test_position_read_inverse_budget_preserves_unrelated_known_values(self):
        robot = {'dh': [{'type': 'prismatic', 'min': 0.0, 'max': 100.0}],
                 'current': {'joints': {'type': ['JOINTPOS', 1], 'value': [0.0]}}}
        with mock.patch('karel2py.input_robot_values.MODEL_SAMPLE_LIMIT', 1):
            prepared = prepare(
                "CNV_STR_CONF('N',cfg,s) p=POS(0,0,42,0,0,0,cfg) SET_POS_REG(1,p,s) "
                "out=GET_JPOS_REG(1,s) "
                "IF out[1]>40.0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF",
                decl='cfg:CONFIG p:XYZWPR out:JOINTPOS s,wanted,alternate:INTEGER',
                context=bank_context(robot=robot),
            )
        self.assert_discovery(prepared, ['WANTED', 'ALTERNATE'], ['position-model'])
        self.assertIn('model-sample limit', prepared['template']['discovery']['unresolved'][0]['message'])

    def test_known_unreachable_register_conversion_stops_without_downstream_inputs(self):
        prepared = prepare(
            "CNV_STR_CONF('N',cfg,s) p=POS(500,0,0,0,0,0,cfg) SET_POS_REG(1,p,s) "
            "out=GET_JPOS_REG(1,s) WRITE(unreachable)",
            decl='cfg:CONFIG p:XYZWPR out:JOINTPOS s,unreachable:INTEGER',
            context=bank_context(),
        )
        self.assert_discovery(prepared, [], ['position-model'])
        self.assertIn('No IK solution', prepared['template']['discovery']['unresolved'][0]['message'])

    def test_joint_inverse_mirror_frame_and_axis_queries(self):
        prepared = prepare(
            "$MNUFRAMENUM[1]=2 joint[1]=0.0 CNV_STR_CONF('N',cfg,s) "
            "identity=POS(0,0,0,0,0,0,cfg) "
            "built=FRAME(joint,VEC(120,0,0),VEC(90,20,0)) "
            "mirror_pose=MIRROR(joint,identity,FALSE) "
            "IF (INV(joint).x=-90.0) AND (built.x=90.0) AND (mirror_pose.x=90.0) "
            "AND (ORIENT(joint).y=1.0) AND (APPROACH(joint).z=1.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='cfg:CONFIG identity:XYZWPR joint:JOINTPOS1 built,mirror_pose:XYZWPREXT s,wanted,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_relative_operands_convert_before_later_frame_selector(self):
        code = translate(
            "PROGRAM T VAR joint:JOINTPOS1 pose:XYZWPREXT wanted,unused:INTEGER "
            "ROUTINE later:JOINTPOS1 BEGIN $MNUFRAMENUM[1]=2 RETURN joint END later "
            "BEGIN joint[1]=0.0 pose=joint:later() "
            "IF (pose.x=190.0) AND ((joint:joint).x=180.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        prepared = prepare_inputs(code.python_source, context={'robot': robot_configuration()})
        self.assert_discovery(prepared, ['WANTED'])

    def test_unpos_snapshots_converted_pose_before_output_selectors(self):
        code = translate(
            "PROGRAM T VAR joint:JOINTPOS2 coords:ARRAY[1]OF REAL y,z,w,p,r,axis_one,axis_two,axis_three:REAL "
            "cfg:CONFIG wanted,unused:INTEGER "
            "ROUTINE slot:INTEGER BEGIN joint[2]=17.0 RETURN 1 END slot "
            "BEGIN joint[1]=0.0 joint[2]=42.0 "
            "UNPOS(joint,coords[slot()],y,z,w,p,r,cfg,axis_one,axis_two,axis_three) "
            "IF (coords[1]=100.0) AND (z=42.0) AND (axis_one=42.0) AND (axis_two=0.0) AND (joint[2]=17.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        self.assert_discovery(prepare_inputs(code.python_source, context=EXTERNAL_MODEL), ['WANTED'])

    def test_known_invalid_joint_unpos_skips_output_selector(self):
        code = translate(
            "PROGRAM T VAR joint:JOINTPOS1 coords:ARRAY[1]OF REAL y,z,w,p,r:REAL cfg:CONFIG "
            "needed,unreachable:INTEGER ROUTINE slot:INTEGER BEGIN WRITE(needed) RETURN 1 END slot "
            "BEGIN joint[1]=5.0 UNPOS(joint,coords[slot()],y,z,w,p,r,cfg) WRITE(unreachable) END T"
        )
        prepared = prepare_inputs(code.python_source, context={'robot': robot_configuration()})
        self.assert_discovery(prepared, [], ['geometry'])

    def test_comparison_retains_both_paths_until_host_tolerances_are_available(self):
        prepared = prepare(
            'joint[1]=0.0 IF joint>=<joint THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF',
            decl='joint:JOINTPOS1 wanted,alternate:INTEGER', context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED', 'ALTERNATE'], ['geometry'])
        self.assertIn('host tolerances', prepared['template']['discovery']['unresolved'][0]['message'])
