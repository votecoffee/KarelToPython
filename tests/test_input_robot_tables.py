"""Read-before-write discovery across authored frame and tool table changes."""
from copy import deepcopy
import unittest

from karel2py import runtime as rt, translate
from karel2py.input_template import prepare_inputs
from karel2py.storage import typed_value
from tests.test_extended_services import pose
from tests.test_input_template import by_path, prepare


def robot_configuration():
    return {
        'dh': [{'a': 100.0, 'min': 0.0, 'max': 0.0}],
        'frames': {'2': typed_value(pose(10))},
        'tools': {'3': typed_value(pose(25))},
        'current': {'joints': {'type': ['JOINTPOS', 1], 'value': [0.0]}},
    }


class InputRobotTableTests(unittest.TestCase):
    def assert_discovery(self, prepared, inputs, gaps=()):
        report = prepared['template']['discovery']
        self.assertEqual(set(by_path(prepared)), set(inputs))
        self.assertEqual([row['code'] for row in report['unresolved']], list(gaps), report['unresolved'])
        self.assertEqual(report['context_requirements'], [{'service': 'robot', 'address': None}])
        self.assertEqual(report['complete'], not gaps)

    def test_numbered_and_active_pose_updates_feed_model_queries(self):
        context = {'robot': robot_configuration()}
        before = deepcopy(context)
        prepared = prepare(
            'old=$MNUFRAME[1,2] $MNUFRAME[1,7]=old $MNUFRAMENUM[1]=7 $MNUTOOLNUM[1]=3 '
            '$GROUP[1].$UFRAME.location.x=15.0 '
            'new=$MNUFRAME[1,$MNUFRAMENUM[1]] xcoord=CURPOS().x '
            'target=POS(xcoord,0,0,0,0,0,CURPOS().config_data) '
            'IF (old.location.x=10.0) AND (new.location.x=15.0) AND (xcoord=110.0) '
            'AND ($MNUTOOLNUM[1]=3) AND IN_RANGE(target) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='old,new:POSITION target:XYZWPR xcoord:REAL wanted,unused:INTEGER', context=context,
        )
        self.assert_discovery(prepared, ['WANTED'])
        self.assertEqual(context, before)
        self.assertEqual(prepared['context']['robot'], before['robot'])

    def test_identical_branch_writes_merge_and_unknown_group_rows_stay_isolated(self):
        context = {'robot': {'groups': {'1': robot_configuration(), '2': robot_configuration()}, 'active_group': 2}}
        prepared = prepare(
            'IF take THEN $MNUFRAME[2,2].location.x=20.0 ELSE $MNUFRAME[2,2].location.x=20.0 ENDIF '
            '$MNUFRAMENUM[2]=2 $GROUP[1].$UFRAME.location.x=offset '
            'IF (CURPOS().x=80.0) AND ($MNUFRAMENUM[2]=2) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='take:BOOLEAN offset:REAL wanted,unused:INTEGER', context=context,
        )
        self.assert_discovery(prepared, ['TAKE', 'OFFSET', 'WANTED'], ['robot-tables'])

    def test_conflicting_selection_does_not_hide_fixed_row_and_strong_write_recovers(self):
        prepared = prepare(
            'IF take THEN $MNUFRAMENUM[1]=2 ELSE $MNUFRAMENUM[1]=0 ENDIF '
            'IF $MNUFRAME[1,2].location.x=10.0 THEN '
            'IF $GROUP[1].$UFRAME.location.x=0.0 THEN WRITE(first) ELSE WRITE(second) ENDIF ENDIF '
            '$MNUFRAMENUM[1]=2 IF CURPOS().x=90.0 THEN WRITE(recovered) ELSE WRITE(unused) ENDIF',
            decl='take:BOOLEAN first,second,recovered,unused:INTEGER', context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['TAKE', 'FIRST', 'SECOND', 'RECOVERED'], ['robot-tables'])

    def test_unknown_numbered_write_does_not_hide_tool_and_can_be_overwritten(self):
        prepared = prepare(
            'saved=$MNUFRAME[1,2] $MNUFRAME[1,index_no]=saved $MNUFRAME[1,2]=saved '
            '$MNUTOOLNUM[1]=3 $MNUFRAMENUM[1]=2 '
            'IF (CURPOS().x=115.0) AND ($GROUP[1].$UTOOL.location.x=25.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='saved:POSITION index_no,wanted,unused:INTEGER', context={'robot': robot_configuration()},
        )
        self.assert_discovery(prepared, ['INDEX_NO', 'WANTED'], ['robot-tables'])

    def test_joint_write_converts_before_evaluating_target_selectors(self):
        generated = translate(
            'PROGRAM T VAR joint:JOINTPOS1 wanted,unused:INTEGER '
            'ROUTINE pick:INTEGER BEGIN $MNUFRAMENUM[1]=2 RETURN 4 END pick '
            'BEGIN joint[1]=0.0 $MNUFRAME[1,pick()]=joint '
            'IF ($MNUFRAME[1,4].location.x=100.0) AND (CURPOS().x=90.0) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF END T'
        )
        prepared = prepare_inputs(generated.python_source, context={'robot': robot_configuration()})
        self.assert_discovery(prepared, ['WANTED'])

    def test_external_axis_and_configuration_fields_use_the_checked_row_shape(self):
        context = {'robot': robot_configuration()}
        with rt._numeric_scope('pythonic'):
            context['robot']['frames']['2'] = typed_value(rt.convert_position(('XYZWPREXT',), pose(10)))
        prepared = prepare(
            '$MNUFRAME[1,2].ext1=8.0 $MNUFRAMENUM[1]=2 '
            '$GROUP[1].$UFRAME.config_data.cfg_turn_no1=2.0 '
            'IF (($GROUP[1].$UFRAME).ext1=8.0) AND ($MNUFRAME[1,2].config_data.cfg_turn_no1=2) '
            'THEN WRITE(wanted) ELSE WRITE(unused) ENDIF',
            decl='wanted,unused:INTEGER', context=context,
        )
        self.assert_discovery(prepared, ['WANTED'])

    def test_proven_missing_selection_reports_the_failure_before_downstream_reads(self):
        prepared = prepare('$MNUFRAMENUM[1]=77 WRITE(unreachable)',
                           decl='unreachable:INTEGER', context={'robot': robot_configuration()})
        self.assert_discovery(prepared, [], ['robot-tables'])
        self.assertIn('not configured', prepared['template']['discovery']['unresolved'][0]['message'])
