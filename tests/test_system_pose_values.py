"""Authored configured frame/tool values, private ownership and source boundaries."""
import json
import unittest

from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError,tokenize
from karel2py.storage import typed_value
from tests.test_extended_services import compile_program,pose
from tests.test_cartesian_interfaces import value as cartesian_value


DECL='p,q:POSITION a:XYZWPR e:XYZWPREXT n,m:REAL i,s,entry:INTEGER trace:STRING[32]'


def context():
    return rt.ExecutionContext(robot=rt.RobotContext(frames={0:pose(0),2:pose(12)},tools={0:pose(0),3:pose(23)},active_frame=2,active_tool=3))


def program(body,**options):return compile_program(body,decl=options.pop('decl',DECL),context=options.pop('context',None) or context(),**options)


def run(body,**options):
    p,r=program(body,**options);return p.run(),p,r


class SystemPoseValueTests(unittest.TestCase):
    def test_numbered_frame_reads_position(self):
        v,_,_=run('p=$MNUFRAME[1,2]');self.assertEqual(v['P']['LOCATION']['X'],12.)
    def test_numbered_tool_reads_position(self):
        v,_,_=run('p=$MNUTOOL[1,3]');self.assertEqual(v['P']['LOCATION']['X'],23.)
    def test_active_frame_uses_selected_frame(self):
        v,_,_=run('p=$GROUP[1].$UFRAME');self.assertEqual(v['P']['LOCATION']['X'],12.)
    def test_active_tool_uses_selected_tool(self):
        v,_,_=run('p=$GROUP[1].$UTOOL');self.assertEqual(v['P']['LOCATION']['X'],23.)
    def test_zero_table_entries_are_explicit(self):
        v,_,_=run('p=$MNUFRAME[1,0] q=$MNUTOOL[1,0]');self.assertEqual((v['P']['LOCATION']['X'],v['Q']['LOCATION']['X']),(0.,0.))
    def test_case_insensitive_system_tokens(self):
        v,_,_=run('p=$mnuframe[1,2] q=$group[1].$utool');self.assertEqual((v['P']['LOCATION']['X'],v['Q']['LOCATION']['X']),(12.,23.))
    def test_pose_fields_are_ordinary_read_values(self):
        v,_,_=run('n=$MNUFRAME[1,2].location.x m=$GROUP[1].$UTOOL.location.x');self.assertEqual((v['N'],v['M']),(12.,23.))
    def test_orientation_fields_are_readable(self):
        v,_,_=run('n=$MNUFRAME[1,2].normal.x m=$MNUFRAME[1,2].approach.z');self.assertEqual((v['N'],v['M']),(1.,1.))
    def test_cartesian_assignment_conversions_still_apply(self):
        v,_,_=run('a=$MNUFRAME[1,2] e=$MNUTOOL[1,3]');self.assertEqual((v['A']['X'],v['E']['X'],v['E']['EXT1']),(12.,23.,0.))
    def test_each_read_is_an_independent_copy(self):
        v,p,_=run('p=$MNUFRAME[1,2] q=$MNUFRAME[1,2] p.location.x=99');self.assertEqual((v['Q']['LOCATION']['X'],p._state.execution.robot.frame(2).values['X']),(12.,12.))
    def test_configuration_is_independent(self):
        v,p,_=run('p=$MNUFRAME[1,2] p.config_data.cfg_turn_no1=7 q=$MNUFRAME[1,2]');self.assertEqual(v['Q']['CONFIG_DATA']['CFG_TURN_NO1'],0)
    def test_group_then_number_effects_run_once(self):
        routines="ROUTINE grp:INTEGER BEGIN trace=trace+'g' RETURN 1 END grp ROUTINE slot:INTEGER BEGIN trace=trace+'n' RETURN 2 END slot"
        v,_,r=run("trace='' p=$MNUFRAME[grp(),slot()]",routines=routines);self.assertEqual(v['TRACE'],'gn');self.assertEqual(len(r.report['system_pose_values']),1)
    def test_active_group_expression_runs_once(self):
        routines='ROUTINE grp:INTEGER BEGIN i=i+1 RETURN 1 END grp'
        v,_,_=run('i=0 p=$GROUP[grp()].$UFRAME',routines=routines);self.assertEqual(v['I'],1)
    def test_selector_values_capture_before_context_lookup(self):
        ctx=context();routines='ROUTINE later:INTEGER FROM HOST';seen=[]
        def later():ctx.robot.active_frame=0;seen.append(1);return 2
        ctx.externals['HOST','LATER']=later
        # Ordinary source calls can affect later selected data; both selectors still run.
        v,_,_=run('i=1 p=$MNUFRAME[i,later()]',routines=routines,context=ctx);self.assertEqual(v['P']['LOCATION']['X'],12.);self.assertEqual(seen,[1])
    def test_missing_frame_preserves_destination_and_reports_failure(self):
        p,r=program('p=$MNUFRAME[1,2] p=$MNUFRAME[1,9]')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not configured') as caught:p.run()
        self.assertEqual(p.snapshot()['P']['LOCATION']['X'],12.);self.assertIsNotNone(caught.exception.line);self.assertEqual(p.service_requests[-1]['outcome'],'failed')
    def test_missing_tool_is_explicit(self):
        p,_=program('p=$MNUTOOL[1,9]')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not configured'):p.run()
    def test_missing_group_is_explicit(self):
        p,_=program('p=$GROUP[2].$UFRAME')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'group'):p.run()
    def test_missing_robot_context_is_explicit(self):
        p,_=compile_program('p=$MNUFRAME[1,2]',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'):p.run()
    def test_active_selection_must_be_configured(self):
        ctx=context();ctx.robot.active_frame=9;p,_=program('p=$GROUP[1].$UFRAME',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'not configured'):p.run()
    def test_noninteger_selectors_are_rejected(self):
        for expression in ('$MNUFRAME[TRUE,2]','$MNUTOOL[1,2.5]','$GROUP[TRUE].$UTOOL'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError):program('p='+expression)
    def test_selector_bounds_are_checked(self):
        for expression in ('$MNUFRAME[0,2]','$MNUTOOL[1,-1]','$MNUFRAME[1,32768]'):
            p,_=program('p='+expression)
            with self.subTest(expression=expression),self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_missing_selector_value_is_an_error(self):
        p,_=program('p=$MNUFRAME[i,2]')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_array_and_chained_expression_selectors(self):
        v,_,_=run('i=1 ids[1]=2 p=$MNUFRAME[i,ids[1]]',decl=DECL+' ids:ARRAY[2]OF INTEGER');self.assertEqual(v['P']['LOCATION']['X'],12.)
    def test_context_returns_complete_position_representation(self):
        for kind in ('POSITION','XYZWPR','XYZWPREXT'):
            ctx=context();ctx.robot.frames[2]=cartesian_value(kind,(12.,0.,0.),(0.,0.,0.),(7.,8.,9.));v,_,_=run('p=$MNUFRAME[1,2]',context=ctx);self.assertEqual(v['P']['LOCATION']['X'],12.);self.assertNotIn('EXT1',v['P'])
    def test_malformed_configured_pose_is_rejected(self):
        ctx=context();ctx.robot.frames[2].values['X']=float('nan');p,_=program('p=$MNUFRAME[1,2]',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_partial_configured_pose_is_rejected(self):
        ctx=context();ctx.robot.frames[2].values['Z']=rt.UNINITIALIZED;p,_=program('p=$MNUFRAME[1,2]',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_private_routine_position_argument_cannot_change_context(self):
        v,p,_=run('work($MNUFRAME[1,2])',routines='ROUTINE work(v:POSITION) BEGIN v.location.x=99 n=v.location.x END work');self.assertEqual((v['N'],p._state.execution.robot.frame(2).values['X']),(99.,12.))
    def test_private_scalar_field_argument_can_be_changed(self):
        v,p,_=run('work($MNUFRAME[1,2].location.x)',routines='ROUTINE work(v:REAL) BEGIN v=99 n=v END work');self.assertEqual((v['N'],p._state.execution.robot.frame(2).values['X']),(99.,12.))
    def test_private_orientation_argument_is_a_value(self):
        v,p,_=run('work($MNUFRAME[1,2].normal.x)',routines='ROUTINE work(v:REAL) BEGIN v=99 n=v END work');self.assertEqual(v['N'],99.);self.assertEqual(p._state.execution.robot.frame(2).values['X'],12.)
    def test_routine_result_retains_independent_pose(self):
        v,p,_=run('p=pick() p.location.x=99',routines='ROUTINE pick:POSITION BEGIN RETURN $GROUP[1].$UFRAME END pick');self.assertEqual(p._state.execution.robot.frame(2).values['X'],12.)
    def test_typed_variable_service_can_copy_pose_fields(self):
        v,p,_=run("n=0 SET_VAR(entry,'','n',$MNUFRAME[1,2].location.x,s)");self.assertEqual((v['N'],v['S']),(12.,0))
    def test_using_captures_a_private_snapshot(self):
        v,p,r=run('USING $MNUFRAME[1,2] DO location.x=99 n=location.x ENDUSING');self.assertEqual((v['N'],p._state.execution.robot.frame(2).values['X']),(99.,12.));self.assertTrue(r.report['using_scopes'][0]['selector_captures'][0]['independent_copy'])
    def test_using_location_captures_private_vector(self):
        v,p,_=run('USING $MNUFRAME[1,2].location DO x=99 n=x ENDUSING');self.assertEqual((v['N'],p._state.execution.robot.frame(2).values['X']),(99.,12.))
    def test_direct_system_orientation_assignments_remain_rejected(self):
        for target in ('$MNUFRAME[1,2].normal','$MNUTOOL[1,3].orient.x','$GROUP[1].$UFRAME.approach'):
            with self.subTest(target=target),self.assertRaises(TranslationError) as caught:program(target+'=p')
            self.assertEqual(caught.exception.code,'E_SYSTEM_POSE_TARGET')
    def test_read_and_service_output_aliases_are_rejected(self):
        for body in ('READ($MNUFRAME[1,2].location.x)',"GET_VAR(entry,'','n',$MNUFRAME[1,2].location.x,s)"):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:program(body)
            self.assertIn(caught.exception.code,('E_READ_ITEM','E_SYSTEM_POSE_READ_ONLY'))
    def test_unknown_dollar_roots_remain_lexical_errors(self):
        with self.assertRaises(TranslationError) as caught:program('p=$UNLISTED[1]')
        self.assertEqual(caught.exception.code,'E_LEX')
    def test_unknown_group_member_is_rejected(self):
        with self.assertRaises(TranslationError) as caught:program('p=$GROUP[1].$SPEED')
        self.assertEqual(caught.exception.code,'E_SYSTEM_POSE')
    def test_system_names_cannot_be_declared(self):
        with self.assertRaises(TranslationError):program('',decl='$MNUFRAME:INTEGER')
    def test_wrong_array_arity_is_rejected(self):
        for expression in ('$MNUFRAME[1]','$MNUFRAME[1,2,3]','$GROUP[1,2].$UFRAME','$MNUFRAME[1][2]'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError):program('p='+expression)
    def test_scalar_group_syntax_is_rejected(self):
        for expression in ('$GROUP[1]','$UFRAME','$UTOOL'):
            with self.subTest(expression=expression),self.assertRaises(TranslationError):program('p='+expression)
    def test_lexing_is_bounded_and_positioned(self):
        tokens=tokenize('x=$MNUFRAME[1,2] y=$PRIORITY','authored.kl');self.assertEqual([(t.value,t.column) for t in tokens if t.value.startswith('$')],[('$MNUFRAME',3),('$PRIORITY',20)])
    def test_dispatch_and_cooperative_parity(self):
        for body,coop in [('p=$GROUP[1].$UFRAME',False),('start:: p=$GROUP[1].$UFRAME GOTO done done::',False),('p=$GROUP[1].$UFRAME',True)]:
            v,_,_=run(body,cooperative=coop);self.assertEqual(v['P']['LOCATION']['X'],12.)
    def test_grouped_robot_tables_use_explicit_group(self):
        ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:context().robot,2:rt.RobotContext(frames={2:pose(42)},tools={3:pose(43)},active_frame=2,active_tool=3)},active_group=1));v,_,_=run('p=$MNUFRAME[2,2] q=$GROUP[2].$UTOOL',context=ctx);self.assertEqual((v['P']['LOCATION']['X'],v['Q']['LOCATION']['X']),(42.,43.))
    def test_dh_context_and_selections_roundtrip(self):
        ctx=rt.ExecutionContext.from_config({'robot':{'dh':[{'a':100},{'a':100}],'frames':{'2':typed_value(pose(12))},'tools':{'3':typed_value(pose(23))},'frame':2,'tool':3}});ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())));v,_,_=run('p=$GROUP[1].$UFRAME q=$MNUTOOL[1,3]',context=ctx);self.assertEqual((v['P']['LOCATION']['X'],v['Q']['LOCATION']['X']),(12.,23.))
    def test_source_include_diagnostics_keep_physical_file(self):
        with self.assertRaises(TranslationError) as caught:translate('PROGRAM SAMPLE\nVAR p:POSITION\n%INCLUDE BODY\nEND SAMPLE',includes={'BODY.KL':'BEGIN p=$MNUFRAME[TRUE,2]'})
        self.assertEqual((caught.exception.filename,caught.exception.token.line),('BODY.KL',1))
    def test_success_observations_contain_no_pose_data(self):
        _,p,_=run('p=$MNUFRAME[1,2]');self.assertEqual(p.service_requests[-1]['operation'],'SYSTEM_POSE');self.assertEqual(set(p.service_requests[-1]),{'operation','line','outcome'})
    def test_runtime_scope_guard_remains(self):
        p,_=program('')
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):p._state.system_pose('FRAME',1,2)
    def test_report_has_explicit_lookup_and_copy_boundary(self):
        _,_,r=run('p=$MNUFRAME[1,2]');self.assertEqual(r.report['system_pose_values'][0]['result_type'],'POSITION');self.assertFalse(r.report['system_pose_policy']['controller_validated']);self.assertIn('no VariableStore discovery',r.report['system_pose_policy']['context'])
