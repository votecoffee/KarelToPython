"""Authored source frame/tool number values, assignments and offline integration."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.storage import typed_value
from tests.test_extended_services import pose
from tests.test_system_pose_values import program,context
from tests.test_project_scheduler import source


def execute(body,**options):
    p,r=program(body,**options);v=p.run();return v,p,r


def model_context():
    return rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100,'min':0,'max':0}],
        'current':{'joints':{'type':['JOINTPOS',1],'value':[0.0]}},
        'frames':{'2':typed_value(pose(10))},'tools':{'3':typed_value(pose(20))}}})


class FrameToolSelectionValueTests(unittest.TestCase):
    def test_frame_number_read_is_integer(self):
        v,_,_=execute('i=$MNUFRAMENUM[1]');self.assertEqual(v['I'],2);self.assertIs(type(v['I']),int)
    def test_tool_number_read_is_integer(self):self.assertEqual(execute('i=$MNUTOOLNUM[1]')[0]['I'],3)
    def test_casefolded_names_and_group_parentheses(self):self.assertEqual(execute('i=$mnuframenum[(1)]')[0]['I'],2)
    def test_integer_value_can_promote_to_real(self):self.assertEqual(execute('n=$MNUFRAMENUM[1]')[0]['N'],2.)
    def test_number_can_select_configured_pose_row(self):self.assertEqual(execute('p=$MNUFRAME[1,$MNUFRAMENUM[1]]')[0]['P']['LOCATION']['X'],12.)
    def test_number_can_select_configured_tool_row(self):self.assertEqual(execute('p=$MNUTOOL[1,$MNUTOOLNUM[1]]')[0]['P']['LOCATION']['X'],23.)
    def test_number_works_in_arithmetic(self):self.assertEqual(execute('i=$MNUFRAMENUM[1]+$MNUTOOLNUM[1]')[0]['I'],5)
    def test_number_works_in_select(self):self.assertEqual(execute('SELECT $MNUFRAMENUM[1] OF CASE(2): i=7 ELSE: i=9 ENDSELECT')[0]['I'],7)
    def test_read_group_selector_runs_once(self):
        routines='ROUTINE grp:INTEGER BEGIN i=i+1 RETURN 1 END grp'
        v,_,_=execute('i=0 s=$MNUFRAMENUM[grp]',routines=routines);self.assertEqual((v['I'],v['S']),(1,2))
    def test_bare_routine_argument_is_a_private_value(self):
        _,p,_=execute('edit($MNUFRAMENUM[1])',routines='ROUTINE edit(v:INTEGER) BEGIN v=99 END edit');self.assertEqual(p._state.execution.robot.active_frame,2)
    def test_grouped_argument_is_a_private_value(self):
        _,p,_=execute('edit(($MNUTOOLNUM[1]))',routines='ROUTINE edit(v:INTEGER) BEGIN v=99 END edit');self.assertEqual(p._state.execution.robot.active_tool,3)
    def test_function_result_returns_private_integer(self):
        self.assertEqual(execute('i=pick()',routines='ROUTINE pick:INTEGER BEGIN RETURN $MNUFRAMENUM[1] END pick')[0]['I'],2)
    def test_input_service_can_read_selection_value(self):
        _,p,_=execute("SET_VAR(entry,'','i',$MNUTOOLNUM[1],s)");self.assertEqual(p.snapshot()['I'],3)
    def test_read_observation_contains_no_selection_payload(self):
        _,p,_=execute('i=$MNUFRAMENUM[1]');row=p.service_requests[-1];self.assertEqual((row['operation'],row['outcome']),('SYSTEM_SELECTION_READ','completed'));self.assertEqual(set(row),{'operation','line','outcome'})


class FrameToolSelectionWriteTests(unittest.TestCase):
    def test_frame_assignment_changes_active_lookup(self):
        v,p,_=execute('$MNUFRAMENUM[1]=0 p=$GROUP[1].$UFRAME');self.assertEqual((p._state.execution.robot.active_frame,v['P']['LOCATION']['X']),(0,0.))
    def test_tool_assignment_changes_active_lookup(self):
        v,p,_=execute('$MNUTOOLNUM[1]=0 p=$GROUP[1].$UTOOL');self.assertEqual((p._state.execution.robot.active_tool,v['P']['LOCATION']['X']),(0,0.))
    def test_same_id_assignment_is_valid(self):self.assertEqual(execute('$MNUFRAMENUM[1]=$MNUFRAMENUM[1] i=$MNUFRAMENUM[1]')[0]['I'],2)
    def test_maximum_configured_row_can_be_selected(self):
        v,_,_=execute('a=$MNUFRAME[1,2] $MNUFRAME[1,32767]=a $MNUFRAMENUM[1]=32767 i=$MNUFRAMENUM[1]');self.assertEqual(v['I'],32767)
    def test_configured_special_number_is_an_ordinary_row(self):
        ctx=context();ctx.robot.frames[62]=pose(40);v,_,_=execute('$MNUFRAMENUM[1]=62 p=$GROUP[1].$UFRAME',context=ctx);self.assertEqual(v['P']['LOCATION']['X'],40.)
    def test_selection_and_table_write_form_complete_workflow(self):
        v,p,_=execute('a=$MNUFRAME[1,2] a.x=40 $MNUFRAME[1,7]=a $MNUFRAMENUM[1]=7 $GROUP[1].$UFRAME.location.y=9 p=$GROUP[1].$UFRAME');self.assertEqual((v['P']['LOCATION']['X'],v['P']['LOCATION']['Y']),(40.,9.));self.assertEqual(p._state.execution.robot.frames[2].values['X'],12.)
    def test_old_pose_snapshot_stays_independent_after_selection(self):
        v,_,_=execute('p=$GROUP[1].$UFRAME $MNUFRAMENUM[1]=0 q=$GROUP[1].$UFRAME');self.assertEqual((v['P']['LOCATION']['X'],v['Q']['LOCATION']['X']),(12.,0.))
    def test_integral_narrow_rhs_is_accepted(self):
        v,p,_=execute('b=0 $MNUFRAMENUM[1]=b i=$MNUFRAMENUM[1]',decl='b:BYTE i:INTEGER');self.assertEqual(v['I'],0)
    def test_selection_does_not_replace_or_modify_table_rows(self):
        ctx=context();a=ctx.robot.frames[2];b=ctx.robot.tools[3];execute('$MNUFRAMENUM[1]=0 $MNUTOOLNUM[1]=0',context=ctx);self.assertIs(ctx.robot.frames[2],a);self.assertIs(ctx.robot.tools[3],b);self.assertEqual((a.values['X'],b.values['X']),(12.,23.))
    def test_frame_and_tool_selection_are_independent(self):
        _,p,_=execute('$MNUFRAMENUM[1]=0');self.assertEqual((p._state.execution.robot.active_frame,p._state.execution.robot.active_tool),(0,3))
    def test_grouped_selection_changes_only_explicit_group(self):
        one=context().robot;two=context().robot;ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:one,2:two},active_group=1));execute('$MNUFRAMENUM[2]=0 $MNUTOOLNUM[2]=0',context=ctx);self.assertEqual((one.active_frame,one.active_tool,two.active_frame,two.active_tool),(2,3,0,0))
    def test_handler_predicate_and_action_use_selection(self):
        _,p,_=execute('CONDITION[1]: WHEN $MNUFRAMENUM[1]=2 DO $MNUFRAMENUM[1]=0 ENDCONDITION ENABLE CONDITION[1] i=0');self.assertEqual(p._state.execution.robot.active_frame,0)
    def test_linked_routine_selection_is_shared(self):
        files={'main':source('MAIN','select_zero i=$MNUFRAMENUM[1]',decl='i:INTEGER',routines='ROUTINE select_zero FROM LIB'),'lib':source('LIB','',routines='ROUTINE select_zero BEGIN $MNUFRAMENUM[1]=0 END select_zero')};project=translate_project(files).instantiate(context=context());project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['I'],0)
    def test_dispatch_mode_supports_selection(self):self.assertEqual(execute('start:: $MNUFRAMENUM[1]=0 GOTO done done:: i=$MNUFRAMENUM[1]')[0]['I'],0)
    def test_cooperative_mode_supports_selection(self):self.assertEqual(execute('$MNUFRAMENUM[1]=0 i=$MNUFRAMENUM[1]',cooperative=True)[0]['I'],0)
    def test_rhs_then_group_once_in_source_order(self):
        routines="ROUTINE val:INTEGER BEGIN trace=trace+'R' RETURN 0 END val ROUTINE grp:INTEGER BEGIN trace=trace+'G' RETURN 1 END grp"
        v,_,_=execute("trace='' $MNUFRAMENUM[grp]=val",routines=routines);self.assertEqual(v['TRACE'],'RG')
    def test_rhs_value_is_captured_before_group_effect(self):
        routines='ROUTINE grp:INTEGER BEGIN i=2 RETURN 1 END grp'
        _,p,_=execute('i=0 $MNUFRAMENUM[grp]=i',routines=routines);self.assertEqual(p._state.execution.robot.active_frame,0)
    def test_write_observation_contains_no_selection_payload(self):
        _,p,_=execute('$MNUFRAMENUM[1]=0');row=p.service_requests[-1];self.assertEqual((row['operation'],row['outcome']),('SYSTEM_SELECTION_WRITE','completed'));self.assertEqual(set(row),{'operation','line','outcome'})
    def test_report_records_private_reads_and_capture_order(self):
        _,_,r=execute('i=$MNUFRAMENUM[1] $MNUTOOLNUM[1]=0');rows=r.report['system_selections'];self.assertEqual([row['operation'] for row in rows],['READ_FRAME','WRITE_TOOL']);self.assertTrue(rows[0]['private_value']);self.assertTrue(rows[1]['rhs_before_selector']);self.assertFalse(r.report['frame_selection_policy']['controller_validated'])


class FrameToolSelectionIntegrationTests(unittest.TestCase):
    def test_curpos_uses_selected_model_frame(self):
        v,_,_=execute('$MNUFRAMENUM[1]=2 p=CURPOS(0,0)',context=model_context());self.assertEqual(v['P']['LOCATION']['X'],90.)
    def test_curpos_uses_selected_model_tool(self):
        v,_,_=execute('$MNUFRAMENUM[1]=2 $MNUTOOLNUM[1]=3 p=CURPOS(0,0)',context=model_context());self.assertEqual(v['P']['LOCATION']['X'],110.)
    def test_selection_changes_do_not_move_current_joint_snapshot(self):
        ctx=model_context();before=ctx.robot.current.to_config();execute('$MNUFRAMENUM[1]=2 $MNUTOOLNUM[1]=3',context=ctx);self.assertEqual(ctx.robot.current.to_config(),before)
    def test_kinematic_assignment_uses_selected_frame_and_tool(self):
        v,_,_=execute('$MNUFRAMENUM[1]=2 $MNUTOOLNUM[1]=3 j=CURJPOS(0,0) p=j',decl='j:JOINTPOS1 p:POSITION',context=model_context());self.assertEqual(v['P']['LOCATION']['X'],110.)
    def test_reachability_uses_selected_model_frame(self):
        ctx=model_context();v,_,_=execute('a=CURPOS(0,0) $MNUFRAMENUM[1]=2 ready=IN_RANGE(a)',decl='a:XYZWPR ready:BOOLEAN',context=ctx);self.assertIs(v['READY'],False)
    def test_json_replay_retains_model_free_selections(self):
        _,p,_=execute('$MNUFRAMENUM[1]=0 $MNUTOOLNUM[1]=0');saved=json.loads(json.dumps(p._state.execution.to_config()));other=rt.ExecutionContext.from_config(saved);v,_,_=execute('i=$MNUFRAMENUM[1] s=$MNUTOOLNUM[1]',context=other);self.assertEqual((v['I'],v['S']),(0,0));self.assertEqual(other.robot.to_config(),saved['robot'])
    def test_json_replay_retains_model_selection_and_transforms(self):
        ctx=model_context();execute('$MNUFRAMENUM[1]=2 $MNUTOOLNUM[1]=3',context=ctx);other=rt.ExecutionContext.from_config(ctx.to_config());v,_,_=execute('p=CURPOS(0,0)',context=other);self.assertEqual(v['P']['LOCATION']['X'],110.)
    def test_callbacks_are_not_invoked_during_selection(self):
        ctx=context();ctx.robot.forward=lambda *args:(_ for _ in ()).throw(AssertionError('unexpected model callback'));execute('$MNUFRAMENUM[1]=0 $MNUTOOLNUM[1]=0',context=ctx);self.assertEqual(ctx.robot.active_frame,0)
