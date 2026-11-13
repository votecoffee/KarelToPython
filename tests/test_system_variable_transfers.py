"""Authored literal robot table transfers, atomic publication and alias boundaries."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_system_pose_values import context,program
from tests.test_cartesian_interfaces import value as cartesian
from tests.test_extended_services import pose
from tests.test_project_scheduler import source


def execute(body,**options):
    p,r=program(body,**options);return p.run(),p,r


def ext_context():
    ctx=context();ctx.robot.frames[2]=cartesian('XYZWPREXT',(12.,0.,0.),(10.,20.,30.),(7.,8.,9.));return ctx


class SystemVariableReadTests(unittest.TestCase):
    def test_var_info_describes_supplied_robot_paths_without_creating_transfer_entries(self):
        decl='empty:BOOLEAN label:STRING[16] code,length,s:INTEGER dims:ARRAY[3] OF INTEGER'
        for path,label,code in (('$MNUFRAME[1,2]','XYZWPREXT',6),('$GROUP[1].$UFRAME.EXT2','REAL',17),
                                ('$MNUTOOL[1,3].APPROACH','VECTOR',19),('$MNUTOOLNUM[1]','INTEGER',16)):
            with self.subTest(path=path):
                ctx=ext_context()
                before=ctx.robot.to_config()
                state,_,_=execute(f"VAR_INFO('*SYSTEM*','{path}',empty,label,code,dims,length,s)",decl=decl,context=ctx)
                self.assertEqual((state['LABEL'],state['CODE'],state['EMPTY'],state['DIMS'],state['S']),
                                 (label,code,False,[0,0,0],0))
                self.assertEqual(ctx.robot.to_config(),before)
                self.assertEqual(ctx.entries,{})

    def test_var_info_preserves_explicit_binding_precedence_and_missing_metadata(self):
        decl='empty:BOOLEAN label:STRING[16] code,length,s:INTEGER dims:ARRAY[3] OF INTEGER'
        ctx=ext_context()
        ctx.variables.define('SYSTEM','$MNUFRAME[1,2]',('BOOLEAN',),True)
        body="VAR_INFO('SYSTEM','$MNUFRAME[1,2]',empty,label,code,dims,length,s)"
        state,_,_=execute(body,decl=decl,context=ctx)
        self.assertEqual((state['LABEL'],state['CODE'],state['S']),('BOOLEAN',18,0))
        state,_,_=execute(body+" VAR_INFO('SYSTEM','$MNUFRAME[1,99]',empty,label,code,dims,length,s)",
                          decl=decl,context=ctx)
        self.assertEqual((state['LABEL'],state['CODE'],state['S']),('BOOLEAN',18,1))

    def test_var_info_rejects_output_alias_into_robot_selection(self):
        ctx=ext_context()
        decl='empty:BOOLEAN label:STRING[16] code,length,s:INTEGER dims:ARRAY[3] OF INTEGER'
        p,_=program("VAR_INFO('SYSTEM','$MNUFRAMENUM[1]',empty,label,code,dims,length,s)",decl=decl,context=ctx)
        p._state.values['S']=rt.Reference(('INTEGER',),ctx.robot.__dict__,'active_frame')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps configured row or selection'):p.run()
        self.assertEqual(ctx.robot.active_frame,2)

    def test_numbered_frame(self):
        v,_,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',p,s)");self.assertEqual((v['P']['LOCATION']['X'],v['S'],v['ENTRY']),(12.,0,1))
    def test_numbered_tool(self):
        v,_,_=execute("GET_VAR(entry,'','$MNUTOOL[1,3]',a,s)");self.assertEqual((v['A']['X'],v['S']),(23.,0))
    def test_active_frame(self):self.assertEqual(execute("GET_VAR(entry,'','$GROUP[1].$UFRAME',a,s)")[0]['A']['X'],12.)
    def test_active_tool(self):self.assertEqual(execute("GET_VAR(entry,'','$GROUP[1].$UTOOL',a,s)")[0]['A']['X'],23.)
    def test_whole_extended_preserves_axes(self):
        v,_,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',e,s)",context=ext_context());self.assertEqual([v['E'][n] for n in ('EXT1','EXT2','EXT3')],[7.,8.,9.])
    def test_whole_position_stays_position(self):
        ctx=context();ctx.robot.frames[2]=cartesian('POSITION',(12.,0.,0.),(10.,20.,30.));v,_,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',p,s)",context=ctx);self.assertEqual(v['P']['LOCATION']['X'],12.)
    def test_location_vector(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAME[1,2].LOCATION',v,s)",decl='v:VECTOR entry,s:INTEGER')[0]['V'],{'X':12.,'Y':0.,'Z':0.})
    def test_location_scalar(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUTOOL[1,3].LOCATION.X',n,s)")[0]['N'],23.)
    def test_orientation_vector_read(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAME[1,2].NORMAL',v,s)",decl='v:VECTOR entry,s:INTEGER')[0]['V'],{'X':1.,'Y':0.,'Z':0.})
    def test_orientation_scalar_read(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAME[1,2].APPROACH.Z',n,s)")[0]['N'],1.)
    def test_config_record_read(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAME[1,2].CONFIG_DATA',c,s)",decl='c:CONFIG entry,s:INTEGER')[0]['C']['CFG_TURN_NO1'],0)
    def test_config_turn_read(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAME[1,2].CONFIG_DATA.CFG_TURN_NO1',i,s)")[0]['I'],0)
    def test_config_boolean_read(self):self.assertIs(execute("GET_VAR(entry,'','$MNUFRAME[1,2].CONFIG_DATA.CFG_FLIP',flag,s)",decl='flag:BOOLEAN entry,s:INTEGER')[0]['FLAG'],False)
    def test_external_axis_read(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAME[1,2].EXT2',n,s)",context=ext_context())[0]['N'],8.)
    def test_frame_id_read(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAMENUM[1]',i,s)")[0]['I'],2)
    def test_tool_id_read(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUTOOLNUM[1]',i,s)")[0]['I'],3)
    def test_explicit_system_namespace(self):self.assertEqual(execute("GET_VAR(entry,'*SYSTEM*','$MNUFRAME[1,2]',a,s)")[0]['A']['X'],12.)
    def test_system_namespace(self):self.assertEqual(execute("GET_VAR(entry,'SYSTEM','$MNUFRAME[1,2]',a,s)")[0]['A']['X'],12.)
    def test_case_variants_reuse_cache(self):
        v,p,_=execute("GET_VAR(entry,'system','$mnuframe[1,2]',a,s) i=entry GET_VAR(entry,'SYSTEM','$MNUFRAME[1,2]',a,s)");self.assertEqual((v['I'],v['ENTRY'],len(p._state.execution.entries)),(1,1,1))
    def test_read_output_is_detached(self):
        v,p,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',a,s) a.x=99");self.assertEqual((v['A']['X'],p._state.execution.robot.frames[2].values['X']),(99.,12.))
    def test_grouped_context(self):
        one=context().robot;two=context().robot;two.frames[2]=pose(42);ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:one,2:two}));self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAME[2,2]',a,s)",context=ctx)[0]['A']['X'],42.)
    def test_numeric_field_conversion(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',i,s)")[0]['I'],12)


class SystemVariableWriteTests(unittest.TestCase):
    def test_whole_frame(self):
        _,p,_=execute("a=$MNUTOOL[1,3] SET_VAR(entry,'','$MNUFRAME[1,2]',a,s)");self.assertEqual(p._state.execution.robot.frames[2].values['X'],23.)
    def test_whole_tool(self):
        _,p,_=execute("p=$MNUFRAME[1,2] SET_VAR(entry,'','$MNUTOOL[1,3]',p,s)");self.assertEqual(p._state.execution.robot.tools[3].spec,('POSITION',))
    def test_whole_numbered_can_populate_missing_row(self):
        _,p,_=execute("a=$MNUFRAME[1,2] SET_VAR(entry,'','$MNUTOOL[1,7]',a,s)");self.assertEqual(p._state.execution.robot.tools[7].values['X'],12.)
    def test_whole_can_populate_empty_table(self):
        ctx=context();ctx.robot.tools.clear();_,p,_=execute("a=$MNUFRAME[1,2] SET_VAR(entry,'','$MNUTOOL[1,7]',a,s)",context=ctx);self.assertEqual(p._state.execution.robot.tools[7].values['X'],12.)
    def test_whole_can_repair_malformed_row(self):
        ctx=context();ctx.robot.tools[3]=7;_,p,_=execute("a=$MNUFRAME[1,2] SET_VAR(entry,'','$MNUTOOL[1,3]',a,s)",context=ctx);self.assertEqual(p._state.execution.robot.tools[3].values['X'],12.)
    def test_whole_keeps_source_representation_and_axes(self):
        _,p,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',e,s) SET_VAR(entry,'','$MNUTOOL[1,7]',e,s) e.ext1=99",context=ext_context());row=p._state.execution.robot.tools[7];self.assertEqual((row.spec,row.values['EXT1'],row.values['EXT3']),(('XYZWPREXT',),7.,9.))
    def test_active_frame_write(self):
        _,p,_=execute("a=$MNUTOOL[1,3] SET_VAR(entry,'','$GROUP[1].$UFRAME',a,s)");self.assertEqual(p._state.execution.robot.frames[2].values['X'],23.)
    def test_active_tool_write(self):
        _,p,_=execute("a=$MNUFRAME[1,2] SET_VAR(entry,'','$GROUP[1].$UTOOL',a,s)");self.assertEqual(p._state.execution.robot.tools[3].values['X'],12.)
    def test_location_scalar_write(self):
        _,p,_=execute("n=30 SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',n,s)");self.assertEqual(p._state.execution.robot.frames[2].values['X'],30.)
    def test_location_vector_write(self):
        _,p,_=execute("p=$MNUTOOL[1,3] SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION',p.location,s)");self.assertEqual(p._state.execution.robot.frames[2].values['X'],23.)
    def test_config_whole_word_conversion(self):
        _,p,_=execute("i=0 SET_VAR(entry,'','$MNUFRAME[1,2].CONFIG_DATA',i,s)");self.assertEqual(p._state.execution.robot.frames[2].values['CONFIG_DATA'].values['CFG_TURN_NO1'],0)
    def test_config_turn_real_narrowing(self):
        _,p,_=execute("n=7.9 SET_VAR(entry,'','$MNUFRAME[1,2].CONFIG_DATA.CFG_TURN_NO1',n,s)");self.assertEqual(p._state.execution.robot.frames[2].values['CONFIG_DATA'].values['CFG_TURN_NO1'],7)
    def test_config_boolean_write(self):
        _,p,_=execute("SET_VAR(entry,'','$MNUFRAME[1,2].CONFIG_DATA.CFG_FLIP',TRUE,s)");self.assertIs(p._state.execution.robot.frames[2].values['CONFIG_DATA'].values['CFG_FLIP'],True)
    def test_external_axis_write_keeps_all_other_fields(self):
        ctx=ext_context();old=rt.snapshot_value(ctx.robot.frames[2]);_,p,_=execute("n=42 SET_VAR(entry,'','$MNUFRAME[1,2].EXT2',n,s)",context=ctx);now=rt.snapshot_value(ctx.robot.frames[2]);self.assertEqual(now.pop('EXT2'),42.);old.pop('EXT2');self.assertEqual(now,old)
    def test_frame_id_write(self):
        ctx=context();ctx.robot.frames[7]=pose(42);_,p,_=execute("i=7 SET_VAR(entry,'','$MNUFRAMENUM[1]',i,s)",context=ctx);self.assertEqual(ctx.robot.active_frame,7)
    def test_tool_id_write(self):
        ctx=context();ctx.robot.tools[7]=pose(42);_,p,_=execute("i=7 SET_VAR(entry,'','$MNUTOOLNUM[1]',i,s)",context=ctx);self.assertEqual(ctx.robot.active_tool,7)
    def test_id_set_repairs_missing_old_selected_row(self):
        ctx=context();ctx.robot.active_frame=9;execute("i=2 SET_VAR(entry,'','$MNUFRAMENUM[1]',i,s)",context=ctx);self.assertEqual(ctx.robot.active_frame,2)
    def test_field_publication_leaves_original_host_row(self):
        ctx=context();old=ctx.robot.frames[2];execute("SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',30,s)",context=ctx);self.assertEqual(old.values['X'],12.);self.assertIsNot(ctx.robot.frames[2],old)
    def test_selection_then_active_write(self):
        ctx=context();ctx.robot.frames[7]=pose(42);execute("SET_VAR(entry,'','$MNUFRAMENUM[1]',7,s) SET_VAR(entry,'','$GROUP[1].$UFRAME.LOCATION.X',30,s)",context=ctx);self.assertEqual((ctx.robot.frames[2].values['X'],ctx.robot.frames[7].values['X']),(12.,30.))
    def test_group_write_leaves_other_group(self):
        one=context().robot;two=context().robot;ctx=rt.ExecutionContext(robot=rt.RobotContext(groups={1:one,2:two}));execute("SET_VAR(entry,'','$MNUFRAME[2,2].LOCATION.X',30,s)",context=ctx);self.assertEqual((one.frames[2].values['X'],two.frames[2].values['X']),(12.,30.))


class SystemVariableFailureTests(unittest.TestCase):
    def lookup_failure(self,path,*,write=False,**options):
        call='SET_VAR' if write else 'GET_VAR';body=f"entry=77 s=88 n=42 {call}(entry,'','{path}',n,s)"
        v,p,_=execute(body,**options);self.assertEqual((v['ENTRY'],v['S'],v['N']),(77,1,42.));self.assertEqual(p._state.execution.entries,{})
    def test_missing_frame(self):self.lookup_failure('$MNUFRAME[1,7]')
    def test_missing_tool(self):self.lookup_failure('$MNUTOOL[1,7]')
    def test_missing_group(self):self.lookup_failure('$MNUFRAME[2,2]')
    def test_unknown_system_root(self):self.lookup_failure('$UNKNOWN[1]')
    def test_expression_in_quoted_selector_is_not_evaluated(self):self.lookup_failure('$MNUFRAME[1,1+1]')
    def test_named_selector_is_not_evaluated(self):self.lookup_failure('$MNUFRAME[1,I]')
    def test_negative_selector_rejected(self):self.lookup_failure('$MNUFRAME[1,-1]')
    def test_large_selector_rejected(self):self.lookup_failure('$MNUFRAME[1,32768]')
    def test_chained_pose_indexes_rejected(self):self.lookup_failure('$MNUFRAME[1][2]')
    def test_extra_indexes_rejected(self):self.lookup_failure('$MNUFRAME[1,2,3]')
    def test_selection_descendants_rejected(self):self.lookup_failure('$MNUFRAMENUM[1].X')
    def test_unknown_field_rejected(self):self.lookup_failure('$MNUFRAME[1,2].UNKNOWN')
    def test_orientation_write_rejected(self):self.lookup_failure('$MNUFRAME[1,2].NORMAL.X',write=True)
    def test_external_axis_requires_extended_row(self):self.lookup_failure('$MNUFRAME[1,2].EXT1')
    def test_external_axis_write_requires_extended_row(self):self.lookup_failure('$MNUFRAME[1,2].EXT1',write=True)
    def test_field_write_cannot_create_row(self):self.lookup_failure('$MNUFRAME[1,7].LOCATION.X',write=True)
    def test_active_write_requires_existing_row(self):
        ctx=context();ctx.robot.active_frame=7;self.lookup_failure('$GROUP[1].$UFRAME',write=True,context=ctx)
    def test_malformed_field_row_is_lookup_failure(self):
        ctx=context();ctx.robot.frames[2].values['X']=float('nan');self.lookup_failure('$MNUFRAME[1,2].LOCATION.X',write=True,context=ctx)
    def test_unconfigured_current_id_read_is_lookup_failure(self):
        ctx=context();ctx.robot.active_frame=7;self.lookup_failure('$MNUFRAMENUM[1]',context=ctx)
    def test_unattached_module_does_not_discover_system(self):
        v,p,_=execute("entry=77 GET_VAR(entry,'OTHER','$MNUFRAME[1,2]',p,s)");self.assertEqual((v['ENTRY'],v['S']),(77,1));self.assertEqual(p._state.execution.entries,{})
    def test_incompatible_whole_write_sets_type_status(self):
        v,p,_=execute("entry=77 SET_VAR(entry,'','$MNUFRAME[1,2]',42,s)");self.assertEqual((v['ENTRY'],v['S'],p._state.execution.robot.frames[2].values['X']),(77,3,12.));self.assertEqual(p._state.execution.entries,{})
    def test_joint_write_requires_an_explicit_model(self):
        p,_=program("entry=77 s=88 j[1]=0 j[2]=0 SET_VAR(entry,'','$MNUFRAME[1,2]',j,s)",decl='j:JOINTPOS2 entry,s:INTEGER')
        old=p._state.execution.robot.frames[2]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'adapter'):p.run()
        self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['S']),(77,88))
        self.assertIs(p._state.execution.robot.frames[2],old);self.assertEqual(p._state.execution.entries,{})
    def test_joint_read_requires_supplied_current_joints(self):
        p,_=program("entry=77 s=88 GET_VAR(entry,'','$MNUFRAME[1,2]',j,s)",decl='j:JOINTPOS2 entry,s:INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'current joints'):p.run()
        self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['S']),(77,88));self.assertEqual(p._state.execution.entries,{})
    def test_bad_last_config_field_rolls_back(self):
        p,_=program("entry=77 s=88 p=$MNUFRAME[1,2] p.config_data.cfg_turn_no1=8 SET_VAR(entry,'','$MNUFRAME[1,2]',p,s)");old=p._state.execution.robot.frames[2]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p._state.execution.robot.frames[2],old);self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['S']),(77,88));self.assertEqual(p._state.execution.entries,{})
    def test_partial_whole_write_cannot_populate_row(self):
        p,_=program("entry=77 s=88 SET_VAR(entry,'','$MNUFRAME[1,7]',a,s)")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertNotIn(7,p._state.execution.robot.frames);self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['S']),(77,88));self.assertEqual(p._state.execution.entries,{})
    def test_bad_turn_rolls_back(self):
        p,_=program("entry=77 s=88 SET_VAR(entry,'','$MNUFRAME[1,2].CONFIG_DATA.CFG_TURN_NO1',8,s)");old=p._state.execution.robot.frames[2]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(p._state.execution.robot.frames[2],old);self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['S']),(77,88));self.assertEqual(p._state.execution.entries,{})
    def test_selection_of_missing_row_rolls_back(self):
        p,_=program("entry=77 s=88 SET_VAR(entry,'','$MNUFRAMENUM[1]',7,s)")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p._state.execution.robot.active_frame,p.snapshot()['ENTRY'],p.snapshot()['S']),(2,77,88));self.assertEqual(p._state.execution.entries,{})
    def test_nonordinary_table_is_lookup_failure(self):
        class Derived(dict):pass
        ctx=context();ctx.robot.frames=Derived(ctx.robot.frames);self.lookup_failure('$MNUFRAME[1,2]',context=ctx)


class SystemVariableIntegrationTests(unittest.TestCase):
    def test_set_captures_source_before_later_selector_effects(self):
        routines='ROUTINE pick:INTEGER BEGIN a.x=99 RETURN 1 END pick'
        v,p,_=execute("a=$MNUFRAME[1,2] SET_VAR(entry,'','$MNUFRAME[1,7]',a,statuses[pick()])",decl='a:XYZWPR statuses:ARRAY[1]OF INTEGER entry:INTEGER',routines=routines);self.assertEqual((v['A']['X'],p._state.execution.robot.frames[7].values['X']),(99.,12.))
    def test_get_captures_source_after_output_selector_effects(self):
        routines='ROUTINE pick:INTEGER BEGIN $MNUFRAME[1,2].location.x=99 RETURN 1 END pick'
        v,_,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',rows[pick()],s)",decl='rows:ARRAY[1]OF XYZWPR entry,s:INTEGER',routines=routines);self.assertEqual(v['ROWS'][0]['X'],99.)
    def test_handler_action(self):
        _,p,_=execute("CONDITION[1]: WHEN TRUE DO SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',30,s) ENDCONDITION ENABLE CONDITION[1] i=0");self.assertEqual(p._state.execution.robot.frames[2].values['X'],30.)
    def test_label_dispatch(self):self.assertEqual(execute("start:: GET_VAR(entry,'','$MNUFRAMENUM[1]',i,s) GOTO done done::")[0]['I'],2)
    def test_cooperative(self):self.assertEqual(execute("GET_VAR(entry,'','$MNUFRAMENUM[1]',i,s)",cooperative=True)[0]['I'],2)
    def test_linked_routine(self):
        files={'main':source('MAIN','work',routines='ROUTINE work FROM LIB'),'lib':source('LIB',"",routines="ROUTINE work VAR e,s:INTEGER BEGIN SET_VAR(e,'','$MNUFRAME[1,2].LOCATION.X',30,s) END work")};ctx=context();project=translate_project(files).instantiate(context=ctx);project.run('MAIN');self.assertEqual(ctx.robot.frames[2].values['X'],30.)
    def test_explicit_full_binding_has_precedence(self):
        ctx=context();store={'value':77.};ctx.variables.bind('','$MNUFRAME[1,2].LOCATION.X',rt.Reference(('REAL',),store,'value'));v,_,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',n,s)",context=ctx);self.assertEqual(v['N'],77.)
    def test_explicit_root_binding_has_precedence(self):
        ctx=context();a=rt.Array(('ARRAY',(1,3),('XYZWPR',)));a.values[:]=[pose(10),pose(20),pose(30)];ctx.variables.bind('SYSTEM','$MNUFRAME',rt.Reference(a.spec,{'value':a},'value'));v,_,_=execute("GET_VAR(entry,'SYSTEM','$MNUFRAME[1,2].X',n,s)",context=ctx);self.assertEqual(v['N'],20.)
    def test_saved_context_replays_published_external_axes(self):
        ctx=ext_context();execute("SET_VAR(entry,'','$MNUFRAME[1,2].EXT3',42,s)",context=ctx);saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved);v,p,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',e,s)",context=restored);self.assertEqual(v['E']['EXT3'],42.);self.assertEqual(len(restored.entries),1);self.assertNotIn('entries',saved)
    def test_source_pose_value_arguments_remain_private(self):
        _,p,_=execute('work($MNUFRAME[1,2].location.x)',routines='ROUTINE work(v:REAL) BEGIN v=99 END work');self.assertEqual(p._state.execution.robot.frames[2].values['X'],12.)
    def test_direct_output_alias_remains_rejected(self):
        with self.assertRaises(TranslationError) as caught:program("GET_VAR(entry,'','n',$MNUFRAME[1,2].location.x,s)")
        self.assertEqual(caught.exception.code,'E_SYSTEM_POSE_READ_ONLY')
    def test_byname_stays_excluded(self):
        p,_=program("work(BYNAME('','$MNUFRAME[1,2].LOCATION.X',entry))",routines='ROUTINE work(v:REAL) BEGIN END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.execution.entries,{})
    def test_default_resolver_does_not_discover_system(self):
        p,_=program('')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):p._state.execution.resolve(p._state,'','$MNUFRAME[1,2]')
    def test_get_metadata_host_alias_to_configured_row_is_rejected(self):
        ctx=context();p,_=program("GET_VAR(entry,'','$MNUFRAME[1,2]',a,s)",context=ctx);row=ctx.robot.frames[2];p._state.values['ENTRY']=rt.Reference(('INTEGER',),row.values['CONFIG_DATA'].values,'CFG_TURN_NO1')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(row.values['CONFIG_DATA'].values['CFG_TURN_NO1'],0);self.assertEqual(ctx.entries,{})
    def test_set_metadata_host_alias_to_configured_row_is_rejected(self):
        ctx=context();p,_=program("SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',30,s)",context=ctx);row=ctx.robot.frames[2];p._state.values['ENTRY']=rt.Reference(('INTEGER',),row.values['CONFIG_DATA'].values,'CFG_TURN_NO1')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(row.values['X'],12.);self.assertEqual(ctx.entries,{})
    def test_get_host_output_alias_to_configured_row_is_rejected(self):
        ctx=context();p,_=program("GET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',n,s)",context=ctx);p._state.values['N']=rt.Reference(('REAL',),ctx.robot.frames[2].values,'Y')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.robot.frames[2].values['Y'],0.);self.assertEqual(ctx.entries,{})
    def test_observations_remain_value_free(self):
        _,p,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',a,s)");row=p.service_requests[-1];self.assertEqual(row,{'operation':'GET_VAR','line':6,'outcome':'completed'})
    def test_strict_context_target_guard(self):
        from karel2py.extended import _system_variable_target
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):_system_variable_target(context(),'$MNUFRAME[1,2]',False,None)
    def test_report_policy_is_explicit(self):
        _,_,r=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',a,s)");self.assertFalse(r.report['system_variable_transfer_policy']['controller_validated']);self.assertIn('BYNAME',r.report['system_variable_transfer_policy']['boundary'])


class SystemVariableAdditionalGuardTests(unittest.TestCase):
    def test_new_selection_metadata_alias_rejected_before_publication(self):
        ctx=context();ctx.robot.frames[7]=pose(42);p,_=program("SET_VAR(entry,'','$MNUFRAMENUM[1]',7,s)",context=ctx);row=ctx.robot.frames[7];p._state.values['ENTRY']=rt.Reference(('INTEGER',),row.values['CONFIG_DATA'].values,'CFG_TURN_NO1')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.robot.active_frame,2);self.assertEqual(row.values['CONFIG_DATA'].values['CFG_TURN_NO1'],0);self.assertEqual(ctx.entries,{})
    def test_unselected_row_does_not_alias_selected_target(self):
        ctx=context();ctx.robot.frames[7]=pose(42);p,_=program("SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',30,s)",context=ctx);row=ctx.robot.frames[7];p._state.values['ENTRY']=rt.Reference(('INTEGER',),row.values['CONFIG_DATA'].values,'CFG_TURN_NO1');v=p.run();self.assertEqual((ctx.robot.frames[2].values['X'],row.values['CONFIG_DATA'].values['CFG_TURN_NO1'],v['S']),(30.,1,0))
    def test_position_location_field_write_retains_basis(self):
        ctx=context();ctx.robot.frames[2]=cartesian('POSITION',(12.,0.,0.),(10.,20.,30.));before=rt.snapshot_value(ctx.robot.frames[2]);execute("SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.Y',42,s)",context=ctx);after=rt.snapshot_value(ctx.robot.frames[2]);self.assertEqual(after['LOCATION']['Y'],42.);self.assertEqual([after[n] for n in ('NORMAL','ORIENT','APPROACH')],[before[n] for n in ('NORMAL','ORIENT','APPROACH')])
    def test_active_extended_axis_write(self):
        ctx=ext_context();execute("SET_VAR(entry,'','$GROUP[1].$UFRAME.EXT1',42,s)",context=ctx);self.assertEqual(ctx.robot.frames[2].values['EXT1'],42.)
    def test_nonfinite_axis_rolls_back(self):
        ctx=ext_context();p,_=program("entry=77 s=88 SET_VAR(entry,'','$MNUFRAME[1,2].EXT1',n,s)",context=ctx);p._state.values['N']=float('nan');old=ctx.robot.frames[2]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(ctx.robot.frames[2],old);self.assertEqual(ctx.entries,{})
    def test_partial_vector_rolls_back(self):
        p,_=program("entry=77 s=88 v.x=42 SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION',v,s)",decl='v:VECTOR entry,s:INTEGER');ctx=p._state.execution;old=ctx.robot.frames[2]
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(ctx.robot.frames[2],old);self.assertEqual((p.snapshot()['ENTRY'],p.snapshot()['S']),(77,88));self.assertEqual(ctx.entries,{})
    def test_missing_context_is_lookup_failure(self):
        from tests.test_extended_services import compile_program
        p,_=compile_program("entry=77 GET_VAR(entry,'','$MNUFRAME[1,2]',p,s)",decl='p:POSITION entry,s:INTEGER');v=p.run();self.assertEqual((v['ENTRY'],v['S']),(77,1));self.assertEqual(p._state.execution.entries,{})
    def test_source_external_fields_and_quoted_transfers_share_the_same_row(self):
        values,_,_=execute("$MNUFRAME[1,2].ext1=42 GET_VAR(entry,'','$MNUFRAME[1,2].EXT1',n,s) m=$GROUP[1].$UFRAME.ext1",context=ext_context())
        self.assertEqual((values['N'],values['M'],values['S']),(42.,42.,0))
    def test_context_serialization_contains_no_endpoint(self):
        ctx=ext_context();execute("GET_VAR(entry,'','$MNUFRAME[1,2]',e,s) SET_VAR(entry,'','$MNUFRAME[1,2].EXT2',42,s)",context=ctx);payload=json.dumps(ctx.to_config());self.assertNotIn('_SystemVariableTarget',payload);self.assertNotIn('entries',payload);self.assertEqual(rt.ExecutionContext.from_config(json.loads(payload)).robot.frames[2].values['EXT2'],42.)


class SystemVariableLifetimeTests(unittest.TestCase):
    def test_pause_retains_completed_write_and_resume_uses_new_snapshot(self):
        ctx=context();p,_=program("SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',30,s) PAUSE GET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',n,s)",context=ctx,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(ctx.robot.frames[2].values['X'],30.);ctx.robot.frames[2]=pose(42);v=p.resume();self.assertEqual((v['N'],v['S']),(42.,0));self.assertEqual(len(ctx.entries),1)
    def test_stop_after_write_retains_published_row_without_later_transfer(self):
        ctx=context();p,_=program("SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',30,s) PAUSE SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',42,s)",context=ctx,cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        p.stop();self.assertEqual(ctx.robot.frames[2].values['X'],30.);self.assertEqual(p.task_state,'stopped');self.assertEqual(len(ctx.entries),1)
    def test_cartesian_endpoint_transfers_do_not_invoke_model_callbacks(self):
        ctx=context();ctx.robot.forward=lambda *a:(_ for _ in ()).throw(AssertionError('unexpected model'));ctx.robot.inverse=ctx.robot.forward
        v,_,_=execute("GET_VAR(entry,'','$MNUFRAME[1,2]',a,s) i=s SET_VAR(entry,'','$MNUFRAME[1,2]',a,s)",context=ctx,decl='a:XYZWPR entry,s,i:INTEGER');self.assertEqual((v['I'],v['S']),(0,0));self.assertEqual(len(ctx.entries),1)
    def test_explicit_set_binding_preserves_configured_row(self):
        ctx=context();storage={'value':77.};ctx.variables.bind('','$MNUFRAME[1,2].LOCATION.X',rt.Reference(('REAL',),storage,'value'));execute("SET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',30,s)",context=ctx);self.assertEqual((storage['value'],ctx.robot.frames[2].values['X']),(30.,12.))


class SystemVariableLookupAliasTests(unittest.TestCase):
    def test_invalid_row_cannot_receive_failure_status_through_host_alias(self):
        ctx=context();row=ctx.robot.frames[2];row.values['X']=float('nan');p,_=program("GET_VAR(entry,'','$MNUFRAME[1,2].LOCATION.X',n,s)",context=ctx);p._state.values['S']=rt.Reference(('INTEGER',),row.values['CONFIG_DATA'].values,'CFG_TURN_NO1')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
        self.assertEqual(row.values['CONFIG_DATA'].values['CFG_TURN_NO1'],0);self.assertEqual(ctx.entries,{})
    def test_unknown_field_cannot_receive_failure_status_through_host_alias(self):
        ctx=context();row=ctx.robot.frames[2];p,_=program("SET_VAR(entry,'','$MNUFRAME[1,2].UNKNOWN',30,s)",context=ctx);p._state.values['S']=rt.Reference(('INTEGER',),row.values['CONFIG_DATA'].values,'CFG_TURN_NO1')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
        self.assertEqual(row.values['CONFIG_DATA'].values['CFG_TURN_NO1'],0);self.assertEqual(ctx.entries,{})
    def test_invalid_selected_id_cannot_receive_failure_status_through_host_alias(self):
        ctx=context();ctx.robot.active_frame=32768;p,_=program("GET_VAR(entry,'','$MNUFRAMENUM[1]',i,s)",context=ctx);p._state.values['S']=rt.Reference(('INTEGER',),ctx.robot.__dict__,'active_frame')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
        self.assertEqual(ctx.robot.active_frame,32768);self.assertEqual(ctx.entries,{})
    def test_active_row_transfer_protects_the_selection_used_for_lookup(self):
        ctx=context();p,_=program("SET_VAR(entry,'','$GROUP[1].$UFRAME.LOCATION.X',30,s)",context=ctx);p._state.values['ENTRY']=rt.Reference(('INTEGER',),ctx.robot.__dict__,'active_frame')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps'):p.run()
        self.assertEqual((ctx.robot.active_frame,ctx.robot.frames[2].values['X']),(2,12.));self.assertEqual(ctx.entries,{})
