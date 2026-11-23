"""Discovery of checked quoted robot paths, metadata and staged transfers."""
from copy import deepcopy
import unittest
from unittest import mock

from karel2py import translate
from karel2py.input_template import prepare_inputs
from karel2py.storage import typed_value
from tests.test_cartesian_interfaces import value as cartesian
from tests.test_input_robot_tables import robot_configuration
from tests.test_input_template import by_path, prepare
from tests.test_system_variable_models import context as system_model_context


class InputRobotTransferTests(unittest.TestCase):
    def assert_discovery(self, prepared, paths, gaps=()):
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], list(gaps), report['unresolved'])
        self.assertEqual(set(by_path(prepared)), set(paths))
        self.assertEqual(report['complete'], not gaps)

    def test_named_and_direct_writes_share_rows_selections_and_cache_entries(self):
        robot = robot_configuration()
        robot['frames']['2'] = typed_value(
            cartesian('XYZWPREXT', (10.0, 0.0, 0.0), (0.0, 0.0, 0.0), (7.0, 0.0, 0.0)),
        )
        saved = {'robot': robot}
        original = deepcopy(saved)
        prepared = prepare(
            "GET_VAR(e,'SYSTEM','$MNUFRAME[1,2]',p,s) "
            "SET_VAR(e,'SYSTEM','$MNUFRAME[1,4]',p,s) "
            "SET_VAR(e,'','$mnuframenum[1]',4,s) "
            "$GROUP[1].$UFRAME.ext1=8.0 "
            "GET_VAR(e,'system','$mnuframe[1,4]',q,s) "
            "IF (e=2) AND (s=0) AND (q.ext1=8.0) AND (p.ext1=7.0) "
            "AND ($MNUFRAMENUM[1]=4) AND (CURPOS().x=90.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='p,q:XYZWPREXT e,s,wanted,unused:INTEGER', context=saved,
        )
        self.assert_discovery(prepared, ['WANTED'])
        self.assertEqual(prepared['context']['robot'], original['robot'])
        self.assertEqual(saved, original)

    def test_pose_field_source_and_quoted_config_conversions(self):
        prepared = prepare(
            "SET_VAR(e,'','$MNUTOOL[1,3].LOCATION.X',$MNUFRAME[1,2].location.x,s) "
            "SET_VAR(e,'','$MNUTOOL[1,3].CONFIG_DATA.CFG_TURN_NO1',2.0,s) "
            "GET_VAR(e,'','$MNUTOOL[1,3].CONFIG_DATA.CFG_TURN_NO1',turn,s) "
            "IF (turn=2) AND ($MNUTOOL[1,3].location.x=10.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='e,s,turn,wanted,unused:INTEGER', context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_var_info_observes_stored_representation_without_allocating_entry(self):
        prepared = prepare(
            "p=$MNUFRAME[1,2] SET_VAR(e,'','$MNUTOOL[1,7]',p,s) "
            "VAR_INFO('SYSTEM','$MNUTOOL[1,7]',empty,label,code,dims,n,s) "
            "IF (s=0) AND (label='POSITION') AND (code=1) AND (NOT empty) AND (dims[3]=0) THEN "
            "GET_VAR(e,'','$MNUFRAMENUM[1]',picked,s) "
            "IF (s=0) AND (e=2) THEN WRITE(wanted) ELSE WRITE(unused) ENDIF "
            "ELSE WRITE(unused) ENDIF",
            decl='p:POSITION empty:BOOLEAN label:STRING[16] dims:ARRAY[3] OF INTEGER e,s,code,n,picked,wanted,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_missing_malformed_and_incompatible_lookups_preserve_prior_outputs(self):
        prepared = prepare(
            "e=41 out_value=17 "
            "GET_VAR(e,'','$MNUFRAME[1,99].LOCATION.X',out_value,missing_status) "
            "SET_VAR(e,'','$MNUTOOL[1,3]',TRUE,type_status) "
            "GET_VAR(e,'','$MNUFRAME[1,1+1].LOCATION.X',out_value,bad_path) "
            "IF (e=41) AND (out_value=17) AND (missing_status=1) AND (type_status=3) AND (bad_path=1) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='e,out_value,missing_status,type_status,bad_path,wanted,unused:INTEGER',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_quoted_write_can_use_saved_full_path_binding_without_mutating_robot(self):
        prepared = prepare(
            "SET_VAR(e,'SYSTEM','$MNUFRAME[1,2]',TRUE,s) "
            "GET_VAR(e,'SYSTEM','$MNUFRAME[1,2]',flag,s) "
            "IF (e=1) AND (s=0) AND flag AND ($MNUFRAME[1,2].location.x=10.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='e,s,wanted,unused:INTEGER flag:BOOLEAN',
            context={'robot': robot_configuration(), 'variables': [
                {'program': 'SYSTEM', 'path': '$MNUFRAME[1,2]', 'type': ['BOOLEAN'], 'value': False},
            ]},
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_unknown_source_only_invalidates_the_written_row(self):
        prepared = prepare(
            "SET_VAR(e,'','$MNUFRAME[1,2].LOCATION.X',offset,s) "
            "IF $MNUTOOL[1,3].location.x=25.0 THEN "
            "IF $MNUFRAME[1,2].location.x=10.0 THEN WRITE(first) ELSE WRITE(second) ENDIF "
            "ELSE WRITE(unused) ENDIF",
            decl='e,s,first,second,unused:INTEGER offset:REAL',
            context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['OFFSET', 'FIRST', 'SECOND'], ['robot-tables', 'robot-tables'])

    def test_model_transfer_uses_the_task_group_that_differs_from_the_table_group(self):
        prepared = prepare(
            "j[1]=0.0 j[2]=42.0 "
            "SET_VAR(e,'','$MNUFRAME[1,6]',j,s) "
            "GET_VAR(e,'','$MNUFRAME[1,6]',copy_joint,s) "
            "IF (e=1) AND (s=0) AND ($MNUFRAME[1,6].ext1=42.0) AND (copy_joint[2]=42.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF",
            decl='e,s,wanted,unused:INTEGER j,copy_joint:JOINTPOS2',
            prefix='%DEFGROUP=2\n', context=system_model_context().to_config(),
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_bounded_inverse_keeps_unknown_branches(self):
        with mock.patch('karel2py.input_robot_transfers.MODEL_SAMPLE_LIMIT', 1):
            prepared = prepare(
                "GET_VAR(e,'','$MNUFRAME[1,7]',j,s) "
                "IF s=0 THEN WRITE(wanted) ELSE WRITE(alternate) ENDIF",
                decl='e,s,wanted,alternate:INTEGER j:JOINTPOS2',
                prefix='%DEFGROUP=2\n', context=system_model_context().to_config(),
            )
        self.assert_discovery(prepared, ['WANTED', 'ALTERNATE'], ['robot-tables'])
        self.assertIn('model-sample limit', prepared['template']['discovery']['unresolved'][0]['message'])

    def test_rhs_is_captured_before_status_selector_side_effect(self):
        generated = translate(
            "PROGRAM T VAR e,wanted,unused:INTEGER codes:ARRAY[1]OF INTEGER desired:REAL "
            "ROUTINE slot:INTEGER BEGIN desired=12.0 RETURN 1 END slot "
            "BEGIN desired=30.0 SET_VAR(e,'','$MNUFRAME[1,2].LOCATION.X',desired,codes[slot()]) "
            "IF (codes[1]=0) AND (desired=12.0) AND ($MNUFRAME[1,2].location.x=30.0) "
            "THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T"
        )
        prepared = prepare_inputs(generated.python_source, context={'robot': robot_configuration()})
        self.assert_discovery(prepared, ['WANTED'])
