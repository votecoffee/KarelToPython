"""Discovery of checked model-backed arrays, records and private routine values."""
import unittest
from unittest import mock

from karel2py import translate
from karel2py.input_template import prepare_inputs
from tests.test_input_robot_tables import robot_configuration
from tests.test_input_template import by_path, prepare


RECORDS = (
    "TYPE joint_row=STRUCTURE point:JOINTPOS1 count:INTEGER tag:STRING[8] ENDSTRUCTURE "
    "pose_row=STRUCTURE tag:STRING[3] point:POSITION count:REAL ENDSTRUCTURE "
)


class InputModelAggregateTests(unittest.TestCase):
    def assert_discovery(self, prepared, inputs, codes=()):
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], list(codes), report['unresolved'])
        self.assertEqual(set(by_path(prepared)), set(inputs))
        self.assertEqual(report['complete'], not codes)

    def prepare_program(self, source):
        return prepare_inputs(translate(source).python_source, context={'robot': robot_configuration()})

    def test_model_arrays_round_trip_with_selected_frame_and_concrete_widths(self):
        prepared = prepare(
            '$MNUFRAMENUM[1]=2 a[1,1][1]=0.0 a[1,2][1]=0.0 b=a restored=b '
            'IF (b[1,2].x=90.0) AND (restored[1,1][1]=0.0) AND (restored[1,2][3]=0.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='a:ARRAY[1,2]OF JOINTPOS1 b:ARRAY[1,2]OF XYZWPREXT restored:ARRAY[1,2]OF JOINTPOS3 '
                 'wanted,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_model_prefix_conversion_uses_context_after_capturing_target_row(self):
        prepared = self.prepare_program(
            'PROGRAM T VAR src:ARRAY[2]OF JOINTPOS1 dst:ARRAY[2,2]OF XYZWPREXT wanted,unused:INTEGER '
            'ROUTINE slot:INTEGER BEGIN $MNUFRAMENUM[1]=2 RETURN 2 END slot '
            'BEGIN src[1][1]=0.0 src[2][1]=0.0 dst[2,1].x=77.0 dst[slot()]=src '
            'IF (dst[2,2].x=90.0) AND (CURPOS().x=90.0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_late_geometry_failure_skips_destination_selector(self):
        prepared = self.prepare_program(
            'PROGRAM T TYPE box=STRUCTURE data:ARRAY[2]OF XYZWPREXT ENDSTRUCTURE '
            'VAR src:ARRAY[2]OF JOINTPOS1 dst:ARRAY[1]OF box side_effect,unreachable:INTEGER '
            'ROUTINE slot:INTEGER BEGIN WRITE(side_effect) RETURN 1 END slot '
            'BEGIN src[1][1]=0.0 src[2][1]=5.0 dst[slot()].data=src WRITE(unreachable) END T'
        )
        self.assert_discovery(prepared, [], ['robot-conversion'])
        self.assertIn('exceed model limits', prepared['template']['discovery']['unresolved'][0]['message'])

    def test_array_batch_uses_one_solver_budget_and_keeps_both_branches(self):
        with mock.patch('karel2py.input_robot_values.MODEL_SAMPLE_LIMIT', 2):
            prepared = prepare(
                'a[1][1]=0.0 a[2][1]=0.0 b=a '
                'IF b[1].x=100.0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF',
                decl='a:ARRAY[2]OF JOINTPOS1 b:ARRAY[2]OF XYZWPREXT wanted,alternate:INTEGER',
                context={'robot': robot_configuration()},
            )
        self.assert_discovery(prepared, ['ALTERNATE', 'WANTED'], ['robot-conversion'])
        self.assertIn('model-sample limit', prepared['template']['discovery']['unresolved'][0]['message'])

    def test_wildcard_array_arguments_and_result_keep_shape_and_private_edits(self):
        prepared = self.prepare_program(
            "PROGRAM T VAR input_axes:ARRAY[2]OF JOINTPOS1 result_axes:ARRAY[2]OF JOINTPOS3 wanted,unused:INTEGER "
            "ROUTINE round_trip(private_poses:ARRAY OF XYZWPREXT):ARRAY OF JOINTPOS3 "
            "BEGIN private_poses[1]=private_poses[2] RETURN private_poses END round_trip "
            "BEGIN input_axes[1][1]=0.0 input_axes[2][1]=0.0 result_axes=round_trip(input_axes) "
            "IF (ARRAY_LEN(result_axes)=2) AND (result_axes[2][3]=0.0) AND (input_axes[1][1]=0.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_failed_array_argument_skips_later_argument_and_callee(self):
        prepared = self.prepare_program(
            "PROGRAM T VAR src:ARRAY[2]OF JOINTPOS1 next_input,callee_input:INTEGER "
            "ROUTINE later:INTEGER BEGIN WRITE(next_input) RETURN 0 END later "
            "ROUTINE consume(poses:ARRAY OF XYZWPREXT;flag:INTEGER) BEGIN WRITE(callee_input) END consume "
            "BEGIN src[1][1]=0.0 src[2][1]=5.0 consume(src,later()) END T"
        )
        self.assert_discovery(prepared, [], ['robot-conversion'])

    def test_record_argument_captures_value_before_later_argument(self):
        prepared = self.prepare_program(
            'PROGRAM T '+RECORDS+
            "VAR src:joint_row seen:INTEGER wanted,unused:INTEGER "
            "ROUTINE later:INTEGER BEGIN src.count=99 $MNUFRAMENUM[1]=2 RETURN 0 END later "
            "ROUTINE inspect(row:pose_row;flag:INTEGER) "
            "BEGIN IF (row.count=7.0) AND (row.tag='abc') AND (row.point.location.x=100.0) "
            "THEN seen=1 ELSE seen=2 ENDIF row.count=44.0 END inspect "
            "BEGIN src.point[1]=0.0 src.count=7 src.tag='abcdef' inspect(src,later()) "
            "IF (seen=1) AND (src.count=99) AND (CURPOS().x=90.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_record_conversion_preserves_known_missing_non_geometry_field(self):
        prepared = self.prepare_program(
            'PROGRAM T '+RECORDS+
            "VAR dst:pose_row wanted,unused:INTEGER "
            "ROUTINE produce:pose_row VAR temp:joint_row BEGIN temp.point[1]=0.0 temp.tag='abcdef' RETURN temp END produce "
            "BEGIN dst=produce() IF UNINIT(dst.count) AND (dst.tag='abc') AND (dst.point.location.x=100.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_generic_borrowed_record_array_uses_actual_receiver_layout(self):
        prepared = self.prepare_program(
            'PROGRAM T '+RECORDS+
            "row_t=ARRAY[2]OF pose_row VAR src:ARRAY[1,2]OF joint_row dst:ARRAY[1]OF row_t wanted,unused:INTEGER "
            "ROUTINE work(dst_arg:ARRAY[*,*]OF pose_row;src_arg:ARRAY[*,*]OF joint_row) "
            "BEGIN dst_arg=src_arg END work "
            "BEGIN src[1,1].point[1]=0.0 src[1,1].count=5 src[1,1].tag='abc' "
            "src[1,2].point[1]=0.0 src[1,2].count=6 src[1,2].tag='def' work(dst,src) "
            "IF (dst[1,2].count=6.0) AND (dst[1,2].point.location.x=100.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_scalar_argument_and_return_conversions_use_captured_group_context(self):
        prepared = self.prepare_program(
            'PROGRAM T VAR src:JOINTPOS1 p:XYZWPREXT observed,wanted,unused:INTEGER '
            'ROUTINE inspect(view:XYZWPREXT):JOINTPOS1 BEGIN '
            'IF view.x=90.0 THEN observed=1 ELSE observed=2 ENDIF RETURN view END inspect '
            'BEGIN $MNUFRAMENUM[1]=2 src[1]=0.0 src=inspect(src) p=src '
            'IF (observed=1) AND (src[1]=0.0) AND (p.x=90.0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        self.assert_discovery(prepared, ['WANTED'])
