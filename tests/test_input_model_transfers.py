"""Discovery of saved-model PATH and ordinary named variable transfers."""
import unittest
from unittest import mock

from karel2py import translate
from karel2py.input_template import prepare_inputs
from tests.test_input_robot_tables import robot_configuration
from tests.test_input_template import by_path, prepare


PATH_TYPES = (
    'TYPE joint_node=STRUCTURE point:JOINTPOS1 ENDSTRUCTURE '
    'pose_node=STRUCTURE point:XYZWPREXT ENDSTRUCTURE '
    'joint_header=STRUCTURE tag:INTEGER ENDSTRUCTURE '
    'pose_header=STRUCTURE tag:REAL ENDSTRUCTURE '
    'joint_path=PATH NODEDATA=joint_node PATHHEADER=joint_header '
    'pose_path=PATH NODEDATA=pose_node PATHHEADER=pose_header '
)
JOINT_ROUTE = 'APPEND_NODE(src,status) src[1].point[1]=42.0 src.tag=7 '
PRISMATIC = {'robot': {
    'dh': [{'type': 'prismatic', 'min': 0.0, 'max': 100.0}],
    'current': {'joints': {'type': ['JOINTPOS', 1], 'value': [0.0]}},
}}


class InputModelTransferTests(unittest.TestCase):
    def assert_discovery(self, prepared, expected, gaps=()):
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], list(gaps), report['unresolved'])
        self.assertEqual(set(by_path(prepared)), set(expected))
        self.assertEqual(report['complete'], not gaps)
        self.assertIn({'service': 'robot', 'address': None}, report['context_requirements'])

    def test_model_node_edit_seeds_use_current_selection_and_retain_order(self):
        prepared = prepare(
            '$MNUFRAMENUM[1]=2 seed.point[1]=0.0 APPEND_NODE(route,seed,status,TRUE) '
            '$MNUFRAMENUM[1]=0 INSERT_NODE(route,1,seed,status,TRUE) '
            'IF (status=0) AND (PATH_LEN(route)=2) AND (route[1].point.x=100.0) AND (route[2].point.x=90.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            prefix=PATH_TYPES, decl='seed:joint_node route:pose_path status,wanted,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_model_seed_keeps_captured_source_and_uses_frame_after_status_selector(self):
        code = translate(
            'PROGRAM T '+PATH_TYPES+
            'VAR seed:joint_node route:pose_path codes:ARRAY[1]OF INTEGER wanted,unused:INTEGER '
            'ROUTINE pick:INTEGER BEGIN seed.point[1]=5.0 $MNUFRAMENUM[1]=2 RETURN 1 END pick '
            'BEGIN seed.point[1]=0.0 APPEND_NODE(route,seed,codes[pick()],TRUE) '
            'IF (codes[1]=0) AND (route[1].point.x=90.0) AND (seed.point[1]=5.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        self.assert_discovery(prepare_inputs(code.python_source, context={'robot': robot_configuration()}), ['WANTED'])

    def test_empty_path_assignment_converts_model_backed_header(self):
        prepared = prepare(
            'src.point[1]=0.0 dst=src '
            'IF (PATH_LEN(dst)=0) AND (dst.point.x=100.0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            prefix=('TYPE in_t=STRUCTURE point:JOINTPOS1 ENDSTRUCTURE '
                    'out_t=STRUCTURE point:XYZWPREXT ENDSTRUCTURE'),
            decl='src:PATH NODEDATA=in_t PATHHEADER=in_t dst:PATH NODEDATA=out_t PATHHEADER=out_t '
                 'wanted,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_reverse_copy_path_models_nodes_and_converts_declared_header(self):
        prepared = prepare(
            JOINT_ROUTE+'APPEND_NODE(src,status) src[2].point[1]=17.0 '
            'COPY_PATH(src,2,1,dst,status,TRUE) src[2].point[1]=1.0 '
            'IF (status=0) AND (PATH_LEN(dst)=2) AND (dst.tag=7.0) '
            'AND (dst[1].point.z=17.0) AND (dst[2].point.z=42.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            prefix=PATH_TYPES, decl='src:joint_path dst:pose_path status,wanted,unused:INTEGER', context=PRISMATIC,
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_model_path_array_conversion_flows_through_argument_and_return(self):
        code = translate(
            'PROGRAM T '+PATH_TYPES+
            'VAR src:ARRAY[2]OF joint_path dst:ARRAY[2]OF pose_path status,wanted,unused:INTEGER '
            'ROUTINE reflect(received:ARRAY OF pose_path):ARRAY OF pose_path '
            'BEGIN received[1].tag=9.0 RETURN received END reflect '
            'BEGIN APPEND_NODE(src[1],status) src[1,1].point[1]=17.0 src[1].tag=5 src[2].tag=6 '
            'dst=reflect((src)) '
            'IF (dst[1].tag=9.0) AND (dst[2].tag=6.0) AND (src[1].tag=5) '
            'AND (dst[1,1].point.z=17.0) AND (PATH_LEN(dst[2])=0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(code.python_source, context=PRISMATIC)
        self.assert_discovery(prepared, ['WANTED'])

    def test_named_path_transfers_round_trip_and_allocate_entries_on_success(self):
        prepared = prepare(
            JOINT_ROUTE+"GET_VAR(entry,'','SRC',dst,status) SET_VAR(entry,'','RESTORED',dst,status) "
            "IF (entry=2) AND (status=0) AND (dst[1].point.z=42.0) AND (restored.tag=7) "
            "AND (ABS(restored[1].point[1]-42.0)<0.01) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            prefix=PATH_TYPES, decl='src,restored:joint_path dst:pose_path entry,status,wanted,unused:INTEGER',
            context=PRISMATIC,
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_missing_saved_model_leaves_named_path_cache_and_receiver_untouched(self):
        prepared = prepare(
            JOINT_ROUTE+"entry=91 APPEND_NODE(dst,status) GET_VAR(entry,'','SRC',dst,status) "
            "IF (entry=91) AND (status=3) AND (PATH_LEN(dst)=1) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            prefix=PATH_TYPES, decl='src:joint_path dst:pose_path entry,status,wanted,unused:INTEGER', context={},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_array_transfer_uses_row_major_prefix_and_retains_receiver_tail(self):
        prepared = prepare(
            "a[1,1][1]=0.0 a[1,2][1]=0.0 dst[3,1].x=77.0 "
            "GET_VAR(e,'','A',dst,s) SET_VAR(e,'','JOINTS',dst,s) "
            "IF (e=2) AND (s=0) AND (dst[2,1].x=100.0) AND (dst[3,1].x=77.0) "
            "AND (joints[2,1][1]=0.0) AND (joints[2,1][3]=0.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='a:ARRAY[1,2]OF JOINTPOS1 dst:ARRAY[3,1]OF XYZWPREXT joints:ARRAY[2,1]OF JOINTPOS3 '
                 'e,s,wanted,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_named_scalar_transfer_tracks_selection_and_no_model_status(self):
        body = (
            "j[1]=0.0 SET_VAR(e,'','POINT',j,s) "
            "IF (e=1) AND (s=0) AND (point.x=90.0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF"
        )
        decl = 'j:JOINTPOS1 point:XYZWPREXT e,s,wanted,unused:INTEGER'
        prepared = prepare('$MNUFRAMENUM[1]=2 '+body, decl=decl, context={'robot': robot_configuration()})
        self.assert_discovery(prepared, ['WANTED'])
        rejected = prepare(
            "e=55 j[1]=0.0 SET_VAR(e,'','POINT',j,s) "
            "IF (e=55) AND (s=3) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl=decl, context={},
        )
        self.assert_discovery(rejected, ['WANTED'])

    def test_named_prefix_can_ignore_uninitialized_source_tail(self):
        prepared = prepare(
            "src[1][1]=0.0 src[2][1]=0.0 GET_VAR(e,'','SRC',dst,s) "
            "IF (e=1) AND (s=0) AND (dst[2].x=100.0) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='src:ARRAY[3]OF JOINTPOS1 dst:ARRAY[2]OF XYZWPREXT e,s,wanted,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_named_record_transfer_reports_missing_non_geometry_field_status(self):
        code = translate(
            "PROGRAM T "+PATH_TYPES+
            "TYPE in_t=STRUCTURE point:JOINTPOS1 count:INTEGER ENDSTRUCTURE "
            "out_t=STRUCTURE point:XYZWPREXT count:REAL ENDSTRUCTURE "
            "VAR dst:out_t e,s,wanted,unused:INTEGER "
            "ROUTINE copy_row VAR row:in_t BEGIN row.point[1]=0.0 SET_VAR(e,'','DST',row,s) END copy_row "
            "BEGIN copy_row IF (e=1) AND (s=12311) AND UNINIT(dst.count) AND (dst.point.x=100.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        self.assert_discovery(prepare_inputs(code.python_source, context={'robot': robot_configuration()}), ['WANTED'])

    def test_named_conversion_budget_leaves_status_open_and_preserves_other_facts(self):
        with mock.patch('karel2py.input_robot_values.MODEL_SAMPLE_LIMIT', 2):
            prepared = prepare(
                "joints[1][1]=0.0 joints[2][1]=0.0 keep=7 GET_VAR(e,'','JOINTS',dst,s) "
                "IF keep=7 THEN IF s=0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF ELSE WRITE(unused) ENDIF",
                decl='joints:ARRAY[2]OF JOINTPOS1 dst:ARRAY[2]OF XYZWPREXT e,s,keep,wanted,alternate,unused:INTEGER',
                context={'robot': robot_configuration()},
            )
        self.assert_discovery(prepared, ['ALTERNATE', 'WANTED'], ['variable-model'])
        self.assertIn('model-sample limit', prepared['template']['discovery']['unresolved'][0]['message'])
