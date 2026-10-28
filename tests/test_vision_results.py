"""Authored offline vision data, consumption, alias and persistence tests."""
from copy import deepcopy
import json
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,pose
from tests.test_project_scheduler import source


def found(x=2,*,views=(1,),score=0):
    return dict(offset=pose(x,3,4),frame=6,model=21,encoder=-40,comment='authored result',score=score,
        views={str(v):dict(position=pose(x+v),model=30+v) for v in views},measurements=[1.25,2.5])


def batch(*rows,view=-1,status=0,**options):return dict(camera_view=view,status=status,results=list(rows),**options)


def context(*runs,views=(1,),**options):
    processes={'scan':dict(views=list(views),runs=list(runs),parameters={'gain':1.5,'threshold':2.5})}
    return rt.ExecutionContext(vision=rt.VisionServices(processes=processes,**options),numeric=rt.NumericRegisters(3),positions=rt.PositionRegisters(3))


def execute(body,ctx,decl='s,n:INTEGER value:REAL p:XYZWPR',**options):
    program,result=compile_program(body,decl=decl,context=ctx,**options)
    return program.run(),program,result


START="V_RUN_FIND('scan',-1,s) "
FOUND="V_GET_FOUND('scan',frm,model_no,encoder_no,p,points,measures,s)"
DECL='s,frm,model_no,encoder_no:INTEGER p:XYZWPR points:ARRAY[4] OF XYZWPR measures:ARRAY[10] OF REAL'


class ResultExecutionTests(unittest.TestCase):
    def test_sequential_found_results_share_offset_cursor(self):
        ctx=context(batch(found(2),found(9)))
        values,_,_=execute(START+FOUND+" V_GET_OFFSET('scan',1,s) V_GET_OFFSET('scan',2,s)",ctx,DECL)
        self.assertEqual((values['FRM'],values['MODEL_NO'],values['ENCODER_NO'],values['P']['X'],values['S']),(6,21,-40,2.,117151))
        self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],9.);self.assertEqual(ctx.vision.processes['SCAN']['cursor'],2)

    def test_sparse_view_prefixes_preserve_unknown_tail(self):
        values,_,_=execute(START+FOUND,context(batch(found(views=(1,4))),views=(1,4)),DECL)
        self.assertEqual((values['POINTS'][0]['X'],values['POINTS'][3]['X']),(3.,6.));self.assertEqual(values['POINTS'][1]['X'],{'uninitialized':True})
        self.assertEqual(values['MEASURES'][:2],[1.25,2.5]);self.assertEqual(values['MEASURES'][2],{'uninitialized':True})

    def test_short_arrays_preserve_all_outputs_and_cursor(self):
        for decl in (DECL.replace('ARRAY[4]','ARRAY[3]'),DECL.replace('ARRAY[10]','ARRAY[1]')):
            ctx=context(batch(found(views=(4,))),views=(4,));values,_,_=execute(START+'frm=99 '+FOUND,ctx,decl)
            self.assertEqual((values['S'],values['FRM'],ctx.vision.processes['SCAN']['cursor']),(3,99,0));self.assertEqual(values['P']['X'],{'uninitialized':True})

    def test_exhausted_results_preserve_initialized_outputs(self):
        values,_,_=execute(START+FOUND+' frm=100 '+FOUND,context(batch(found())),DECL)
        self.assertEqual((values['S'],values['FRM'],values['P']['X']),(117151,100,2.))

    def test_failed_batch_consumed_once_and_replaces_old_results(self):
        ctx=context(batch(found()),batch(status=101));values,_,_=execute(START+"V_GET_OFFSET('scan',1,s) "+START+"V_GET_OFFSET('scan',2,s)",ctx)
        self.assertEqual(values['S'],101);self.assertEqual(set(ctx.vision.registers),{1});self.assertEqual(ctx.vision.processes['SCAN']['runs'],[])

    def test_missing_batch_is_explicit_failure_without_fake_success(self):
        ctx=context();program,_=compile_program('s=99 '+START,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit completed'):program.run()
        self.assertEqual(program.snapshot()['S'],99);self.assertEqual(ctx.vision.sequence,0)

    def test_mismatched_view_does_not_consume_batch(self):
        ctx=context(batch(found(),view=1),views=(1,2));values,_,_=execute(START,ctx)
        self.assertEqual(values['S'],2);self.assertEqual(len(ctx.vision.processes['SCAN']['runs']),1)
        values,_,_=execute("V_RUN_FIND('scan',1,s)",ctx);self.assertEqual(values['S'],0)

    def test_zero_view_selection_differs_between_run_and_testrun(self):
        values,_,_=execute("V_RUN_FIND('scan',0,s)",context(batch(found())));self.assertEqual(values['S'],0)
        ctx=context(batch(found(views=(1,2))),views=(1,2));values,_,_=execute("V_RUN_FIND('scan',0,s)",ctx)
        self.assertEqual(values['S'],2);self.assertIsNone(ctx.vision.processes['SCAN']['active'])
        values,_,_=execute("V_CSAPI_TESTRUN('scan',0,s)",ctx);self.assertEqual(values['S'],0)

    def test_unknown_and_unrun_processes_preserve_outputs(self):
        ctx=context(batch(found()));values,_,_=execute("frm=99 V_GET_FOUND('absent',frm,model_no,encoder_no,p,points,measures,s)",ctx,DECL)
        self.assertEqual((values['S'],values['FRM']),(2,99));values,_,_=execute("V_GET_OFFSET('scan',1,s)",ctx);self.assertEqual(values['S'],1)

    def test_empty_find_has_zero_count_and_no_reference(self):
        ctx=context(batch());values,_,_=execute(START+"V_GET_VPARAM('scan',0,-1,1,s) V_SET_REF('scan',s)",ctx)
        self.assertEqual(values['S'],117151);self.assertEqual(ctx.numeric.read(1),(0,0.));self.assertIsNone(ctx.vision.processes['SCAN']['reference'])

    def test_reference_uses_score_without_advancing_cursor_and_is_detached(self):
        ctx=context(batch(found(2,score=.2),found(7,score=.9)));execute(START+"V_GET_OFFSET('scan',1,s) V_SET_REF('scan',s)",ctx)
        process=ctx.vision.processes['SCAN'];self.assertEqual(process['reference']['offset'].values['X'],7.);self.assertEqual(process['cursor'],1)
        process['active']['results'][1]['offset'].values['X']=90.;self.assertEqual(process['reference']['offset'].values['X'],7.)

    def test_reference_ties_use_supplied_order(self):
        ctx=context(batch(found(2),found(7)));execute(START+"V_SET_REF('scan',s)",ctx);self.assertEqual(ctx.vision.processes['SCAN']['reference']['offset'].values['X'],2.)

    def test_numeric_results_use_integer_flag_and_real_count(self):
        ctx=context(batch(found(views=(1,)),found(views=(2,)),pass_flag=2),views=(1,2))
        values,_,_=execute(START+"V_GET_PASSFL('scan',1,s) V_GET_VPARAM('scan',0,2,2,s) V_GET_VPARAM('scan',0,-1,3,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.numeric.snapshot(),{1:2,2:1.,3:2.});self.assertIs(type(ctx.numeric.read(1)[1]),int);self.assertIs(type(ctx.numeric.read(2)[1]),float)

    def test_unsupplied_pass_flag_keeps_register_unknown(self):
        ctx=context(batch(found()));values,_,_=execute(START+"V_GET_PASSFL('scan',1,s)",ctx);self.assertEqual(values['S'],1);self.assertEqual(ctx.numeric.read(1),(1,None))

    def test_invalid_parameter_and_register_preserve_numeric_bank(self):
        ctx=context(batch(found()));ctx.numeric.write(1,42);execute(START,ctx)
        for call in ("V_GET_VPARAM('scan',1,-1,1,s)","V_GET_VPARAM('scan',0,4,1,s)","V_GET_PASSFL('scan',0,s)"):
            with self.subTest(call=call):
                values,_,_=execute(call,ctx);self.assertEqual(values['S'],2);self.assertEqual(ctx.numeric.snapshot(),{1:42})

    def test_missing_numeric_service_does_not_create_bank(self):
        ctx=context(batch(found(),pass_flag=1));ctx.numeric=None;execute(START,ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'numeric'):execute("V_GET_PASSFL('scan',1,s)",ctx)
        self.assertEqual(ctx.vision.processes['SCAN']['cursor'],0)


class VisionRegisterTests(unittest.TestCase):
    def setUp(self):self.ctx=context(registers={1:found(views=(1,4))})

    def test_function_outputs_are_detached_and_comments_truncate(self):
        values,_,_=execute('s=IRVU_VRGETOFFSET(1,p,n,text) p.x=99 s=IRVU_VRGETMEAS(1,2,value)',self.ctx,'s,n:INTEGER p:XYZWPR text:STRING[4] value:REAL')
        self.assertEqual((values['S'],values['N'],values['TEXT'],values['VALUE']),(0,6,'auth',2.5));self.assertEqual(self.ctx.vision.registers[1]['offset'].values['X'],2.)

    def test_sparse_view_read_and_unpopulated_view_status(self):
        values,_,_=execute('s=IRVU_VRGETVIEW(1,4,p,n) n=88 s=IRVU_VRGETVIEW(1,2,p,n)',self.ctx);self.assertEqual((values['S'],values['N'],values['P']['X']),(12311,88,6.))

    def test_invalid_register_and_measurements_preserve_outputs(self):
        for call,code in [('IRVU_VRGETMEAS(0,1,value)',2),('IRVU_VRGETMEAS(2,1,value)',1),('IRVU_VRGETMEAS(1,11,value)',2),('IRVU_VRGETMEAS(1,3,value)',1)]:
            with self.subTest(call=call):
                values,_,_=execute('value=8 s='+call,self.ctx);self.assertEqual((values['S'],values['VALUE']),(code,8.))

    def test_xy_adjustment_preserves_other_metadata_and_views(self):
        before=deepcopy(self.ctx.vision.registers[1]);values,_,_=execute('V_ADJ_2D(1,0.5,-2,s)',self.ctx)
        result=self.ctx.vision.registers[1];self.assertEqual(values['S'],0);self.assertEqual((result['offset'].values['X'],result['offset'].values['Y'],result['offset'].values['Z']),(2.5,1.,4.))
        self.assertEqual(rt.snapshot_value(result['views']['4']['position']),rt.snapshot_value(before['views']['4']['position']));self.assertEqual(result['measurements'],before['measurements'])

    def test_positions_transfer_to_selected_group(self):
        self.ctx.positions=rt.PositionRegisters(3,groups=(2,));values,_,_=execute('VREG_OFFSET(1,1,s) VREG_FND_POS(1,4,2,s)',self.ctx,prefix='%DEFGROUP=2')
        self.assertEqual(values['S'],0);self.assertEqual(self.ctx.positions.read(1,2)[1].values['X'],2.);self.assertEqual(self.ctx.positions.read(2,2)[1].values['X'],6.)

    def test_unpopulated_view_does_not_overwrite_position(self):
        self.ctx.positions.write(1,pose(99));values,_,_=execute('VREG_FND_POS(1,2,1,s)',self.ctx);self.assertEqual(values['S'],12311);self.assertEqual(self.ctx.positions.read(1)[1].values['X'],99.)

    def test_invalid_destination_view_and_group_preserve_bank(self):
        for call in ('VREG_OFFSET(1,0,s)','VREG_FND_POS(1,5,1,s)'):
            values,_,_=execute(call,self.ctx);self.assertEqual(values['S'],2);self.assertEqual(self.ctx.positions.snapshot(),{})
        self.ctx.positions=rt.PositionRegisters(1,groups=(2,));values,_,_=execute('VREG_OFFSET(1,1,s)',self.ctx);self.assertEqual(values['S'],2)

    def test_invalid_vision_destination_does_not_consume_result(self):
        ctx=context(batch(found()));values,_,_=execute(START+"V_GET_OFFSET('scan',0,s)",ctx);self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.processes['SCAN']['cursor'],0)

    def test_missing_position_service_preserves_vision_register(self):
        self.ctx.positions=None
        with self.assertRaisesRegex(rt.KarelRuntimeError,'positions'):execute('VREG_OFFSET(1,1,s)',self.ctx)
        self.assertEqual(self.ctx.vision.registers[1]['offset'].values['X'],2.)

    def test_adjust_overflow_preserves_original_offset(self):
        self.ctx.vision.registers[1]['offset'].values['X']=1.7e308
        with self.assertRaises(rt.KarelRuntimeError):execute('V_ADJ_2D(1,1.7E308,0,s)',self.ctx)
        self.assertEqual(self.ctx.vision.registers[1]['offset'].values['X'],1.7e308)


class ParameterTests(unittest.TestCase):
    def test_csapi_edits_reset_and_save(self):
        ctx=context();values,_,_=execute("V_CSAPI_SETVALUE('scan','gain',8,s) V_CSAPI_GETVALUE('scan','gain',value,s) V_CSAPI_NUMSET('scan',num,s) V_CSAPI_SAVEDATA('scan',s) V_CSAPI_NUMSET('scan',after,s)",ctx,'s:INTEGER value,num,after:REAL')
        self.assertEqual((values['VALUE'],values['NUM'],values['AFTER']),(8.,1.,0.));self.assertEqual(ctx.vision.processes['SCAN']['parameters']['GAIN'],8.)
        execute("V_CSAPI_SETVALUE('scan','gain',4,s) V_CSAPI_RESETDATA('scan',s)",ctx);values,_,_=execute("V_CSAPI_GETVALUE('scan','gain',value,s)",ctx);self.assertEqual(values['VALUE'],8.)

    def test_repeated_parameter_edit_counts_unique_names(self):
        values,_,_=execute("V_CSAPI_SETVALUE('scan','gain',5,s) V_CSAPI_SETVALUE('scan','gain',6,s) V_CSAPI_NUMSET('scan',value,s)",context());self.assertEqual(values['VALUE'],1.)

    def test_testrun_uses_edits_without_clearing_them(self):
        ctx=context(batch(found()),batch(found()));execute("V_CSAPI_SETVALUE('scan','gain',5,s) V_CSAPI_TESTRUN('scan',0,s)",ctx)
        process=ctx.vision.processes['SCAN'];self.assertEqual(process['active']['parameters']['GAIN'],5.);self.assertEqual(process['overwritten'],{'GAIN':5.})
        execute(START,ctx);self.assertEqual(process['active']['parameters']['GAIN'],1.5);self.assertEqual(process['overwritten'],{'GAIN':5.})

    def test_one_shot_override_consumed_by_accepted_run(self):
        ctx=context(batch(found()),batch(found()),overrides={'camera_gain':{'process':'scan','parameter':'gain'}})
        execute("V_OVERRIDE('camera_gain',9,s) "+START,ctx);process=ctx.vision.processes['SCAN'];self.assertEqual(process['active']['parameters']['GAIN'],9.);self.assertEqual(process['temporary'],{})
        execute(START,ctx);self.assertEqual(process['active']['parameters']['GAIN'],1.5)

    def test_failed_execution_consumes_once_but_rejected_view_does_not(self):
        ctx=context(batch(status=444),overrides={'camera_gain':{'process':'scan','parameter':'gain'}})
        values,_,_=execute("V_OVERRIDE('camera_gain',9,s) V_RUN_FIND('scan',4,s)",ctx);self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.processes['SCAN']['temporary'],{'GAIN':9.})
        values,_,_=execute(START,ctx);self.assertEqual(values['S'],444);self.assertEqual(ctx.vision.processes['SCAN']['temporary'],{})

    def test_missing_parameter_and_override_preserve_state(self):
        ctx=context()
        for call in ("V_OVERRIDE('missing',4,s)","V_CSAPI_SETVALUE('scan','missing',5,s)","V_CSAPI_GETVALUE('scan','missing',value,s)"):
            values,_,_=execute('value=9 '+call,ctx);self.assertEqual((values['S'],values['VALUE']),(4,9.));self.assertEqual(ctx.vision.processes['SCAN']['overwritten'],{})

    def test_csapi_inspection_keeps_one_shot_override_separate(self):
        ctx=context(overrides={'camera_gain':{'process':'scan','parameter':'gain'}});values,_,_=execute("V_OVERRIDE('camera_gain',9,s) V_CSAPI_GETVALUE('scan','gain',value,s)",ctx);self.assertEqual(values['VALUE'],1.5)


class TranslationAndPersistenceTests(unittest.TestCase):
    def test_exact_native_wrapper_declarations_lower_to_services(self):
        routines='''ROUTINE IRVU_VRGETOFFSET(a:INTEGER; b:XYZWPR; c:INTEGER; d:STRING):INTEGER FROM IRVUTILVR
ROUTINE IRVU_VRGETVIEW(a:INTEGER; b:INTEGER; c:XYZWPR; d:INTEGER):INTEGER FROM IRVUTILVR
ROUTINE IRVU_VRGETMEAS(a:INTEGER; b:INTEGER; c:REAL):INTEGER FROM IRVUTILVR'''
        ctx=context(registers={1:found()});values,_,report=execute('s=IRVU_VRGETOFFSET(1,p,n,text) s=IRVU_VRGETVIEW(1,1,p,n) s=IRVU_VRGETMEAS(1,1,value)',ctx,'s,n:INTEGER p:XYZWPR text:STRING[30] value:REAL',routines=routines)
        self.assertEqual((values['S'],values['N'],values['VALUE']),(0,31,1.25));self.assertNotIn('external_call(',report.python_source)

    def test_invalid_wrapper_signatures_remain_rejected(self):
        for declaration in ('ROUTINE IRVU_VRGETMEAS(a:INTEGER; b:INTEGER; c:INTEGER):INTEGER FROM IRVUTILVR',
            'ROUTINE IRVU_VRGETMEAS(a:INTEGER; b:INTEGER; c:REAL):REAL FROM IRVUTILVR',
            'ROUTINE IRVU_VRGETMEAS(a:INTEGER; a:INTEGER; c:REAL):INTEGER FROM IRVUTILVR',
            'ROUTINE IRVU_VRGETOFFSET(a:INTEGER; b:XYZWPR; c:INTEGER; d:STRING[255]):INTEGER FROM IRVUTILVR'):
            with self.subTest(declaration=declaration),self.assertRaises(TranslationError):compile_program('',routines=declaration)

    def test_duplicate_wrapper_declarations_remain_rejected(self):
        declaration='ROUTINE IRVU_VRGETMEAS(a:INTEGER; b:INTEGER; c:REAL):INTEGER FROM IRVUTILVR'
        with self.assertRaises(TranslationError):compile_program('',routines=declaration+'\n'+declaration)

    def test_internal_routine_keeps_precedence(self):
        values,_,_=execute('s=IRVU_VRGETMEAS(1,2,value)',rt.ExecutionContext(),'s:INTEGER value:REAL',routines='ROUTINE IRVU_VRGETMEAS(a:INTEGER; b:INTEGER; c:REAL):INTEGER BEGIN c=8 RETURN 9 END IRVU_VRGETMEAS');self.assertEqual((values['S'],values['VALUE']),(9,8.))

    def test_other_external_owner_requires_explicit_link(self):
        program,_=compile_program('s=IRVU_VRGETMEAS(1,1,value)',decl='s:INTEGER value:REAL',routines='ROUTINE IRVU_VRGETMEAS(a:INTEGER; b:INTEGER; c:REAL):INTEGER FROM OTHER',context=context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicitly linked'):program.run()

    def test_exact_output_types_shapes_and_lvalues_remain_checked(self):
        for body,decl in [("V_CSAPI_NUMSET('scan',n,s)",'n,s:INTEGER'),('s=IRVU_VRGETMEAS(1,1,4.0)','s:INTEGER'),
            (FOUND,DECL.replace('ARRAY[4] OF XYZWPR','ARRAY[2,2] OF XYZWPR')),(FOUND,DECL.replace('ARRAY[4] OF XYZWPR','ARRAY[4] OF XYZWPREXT'))]:
            with self.subTest(body=body),self.assertRaises(TranslationError):compile_program(body,decl=decl)

    def test_active_for_output_and_wrapper_cannot_bypass_guards(self):
        for routines in ('','ROUTINE IRVU_VRGETVIEW(a:INTEGER; b:INTEGER; c:XYZWPR; d:INTEGER):INTEGER FROM IRVUTILVR'):
            with self.subTest(routines=routines),self.assertRaises(TranslationError):compile_program('FOR n=1 TO 2 DO s=IRVU_VRGETVIEW(1,1,p,n) ENDFOR',decl='n,s:INTEGER p:XYZWPR',routines=routines)

    def test_overlapping_outputs_preserve_cursor_and_history(self):
        for call in (FOUND.replace('frm,model_no','frm,frm'),FOUND.replace(',p,',',points[1],')):
            ctx=context(batch(found()));execute(START,ctx);program,_=compile_program(call,decl=DECL,context=ctx)
            with self.subTest(call=call),self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):program.run()
            self.assertEqual(ctx.vision.processes['SCAN']['cursor'],0);self.assertEqual(ctx.vision.sequence,1)

    def test_sequence_exhaustion_preserves_batch_and_parameter_edit(self):
        ctx=context(batch(found()),sequence=2147483646)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'):execute(START,ctx)
        self.assertEqual(len(ctx.vision.processes['SCAN']['runs']),1)
        with self.assertRaises(rt.KarelRuntimeError):execute("V_CSAPI_SETVALUE('scan','gain',4,s)",ctx)
        self.assertEqual(ctx.vision.processes['SCAN']['overwritten'],{})

    def test_roundtrip_keeps_cursor_remaining_batches_and_edits(self):
        ctx=context(batch(found(2),found(8)),batch(found(20)));execute("V_CSAPI_SETVALUE('scan','gain',7,s) "+START+"V_GET_OFFSET('scan',1,s)",ctx)
        payload=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(payload);execute("V_GET_OFFSET('scan',2,s)",restored)
        self.assertEqual(restored.vision.registers[2]['offset'].values['X'],8.);self.assertEqual(ctx.vision.processes['SCAN']['cursor'],1)
        self.assertEqual(restored.vision.processes['SCAN']['overwritten'],{'GAIN':7.});self.assertEqual(len(restored.vision.processes['SCAN']['runs']),1)
        payload['vision']['processes']['SCAN']['parameters']['GAIN']=99;self.assertEqual(restored.vision.processes['SCAN']['parameters']['GAIN'],1.5)

    def test_history_ring_and_sequence_roundtrip(self):
        ctx=context(limit=2);execute("V_CSAPI_NUMSET('scan',value,s) V_CSAPI_NUMSET('scan',value,s) V_CSAPI_NUMSET('scan',value,s)",ctx)
        config=ctx.to_config();self.assertEqual([v['sequence'] for v in config['vision']['history']],[2,3]);self.assertEqual(rt.ExecutionContext.from_config(config).vision.sequence,3)

    def test_missing_service_fails_closed(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'vision'):execute(START,rt.ExecutionContext())
        with self.assertRaises(TypeError):rt.ExecutionContext(vision={})

    def test_linked_root_group_and_history_owner(self):
        ctx=context(registers={1:found()});ctx.positions=rt.PositionRegisters(1,groups=(2,))
        project=translate_project({'main':source('MAIN','copy_result()',routines='ROUTINE copy_result FROM LIB').replace('PROGRAM MAIN','PROGRAM MAIN\n%DEFGROUP=2\n'),
            'lib':source('LIB','',routines='ROUTINE copy_result BEGIN VREG_OFFSET(1,1,s) END copy_result')})
        project.instantiate(context=ctx).run('MAIN');self.assertEqual(ctx.positions.read(1,2)[1].values['X'],2.);self.assertEqual(ctx.vision.history[-1]['program'],'MAIN')

    def test_metadata_records_offline_boundary_and_direction_discrepancy(self):
        report=translate('PROGRAM T BEGIN END T').report['vision_policy'];self.assertEqual(len(report['calls']),29);self.assertFalse(report['controller_validated']);self.assertIn('input',report['discrepancy'])


class ConfigurationTests(unittest.TestCase):
    def test_malformed_top_level_banks_and_keys(self):
        for config in ({'unknown':1},{'count':True},{'count':0},{'registers':{'01':{}}},{'registers':{'0':{}}},{'sequence':2147483647},{'limit':0},{'processes':[]},{'registers':{'11':found()}},{'history':[{'operation':[]}]}):
            with self.subTest(config=config),self.assertRaises(ValueError):rt.VisionServices.from_config(config)

    def test_duplicate_names_and_views(self):
        for processes in ({'scan':{'views':[1,1],'runs':[]}}, {'scan':{'views':[True],'runs':[]}}, {'scan':{'views':[1],'runs':[]},'SCAN':{'views':[1],'runs':[]}}):
            with self.assertRaises(ValueError):rt.VisionServices(processes=processes)

    def test_incomplete_pose_wrong_type_and_unconfigured_views(self):
        row=found();row['offset']=rt.Structure(('XYZWPR',))
        with self.assertRaises(ValueError):context(batch(row))
        row=found();row['offset']=rt.Structure(('XYZWPREXT',))
        with self.assertRaises(ValueError):context(batch(row))
        with self.assertRaises(ValueError):context(batch(found(views=(4,))))

    def test_bad_batch_status_view_and_measurements(self):
        for row in (batch(found(),status=9),batch(found(),view=0),batch(found(),status=True),batch(dict(found(),measurements=[float('nan')])),batch(dict(found(),measurements=[0.]*11))):
            with self.subTest(row=row),self.assertRaises(ValueError):context(row)

    def test_missing_active_parameter_snapshot_and_bad_cursor(self):
        ctx=context(batch(found()));execute(START,ctx);config=ctx.to_config();config['vision']['processes']['SCAN']['active']['parameters']={}
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)
        config=ctx.to_config();config['vision']['processes']['SCAN']['cursor']=2
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_unknown_override_binding_and_parameter(self):
        for binding in ({'process':'missing','parameter':'gain'},{'process':'scan','parameter':'missing'},{'process':'scan'}):
            with self.assertRaises(ValueError):context(overrides={'g':binding})

    def test_constructor_detaches_supplied_results(self):
        row=found();ctx=context(batch(row));row['offset'].values['X']=99;row['views']['1']['position'].values['X']=99
        execute(START+"V_GET_OFFSET('scan',1,s)",ctx);self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],2.);self.assertEqual(ctx.vision.registers[1]['views']['1']['position'].values['X'],3.)

    def test_malformed_history_rejected(self):
        ctx=context();execute("V_CSAPI_NUMSET('scan',value,s)",ctx);original=ctx.to_config()
        for key,value in [('operation',[]),('status',True),('sequence',0),('target','\n'),('program','\u00e9')]:
            config=deepcopy(original);config['vision']['history'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)


if __name__=='__main__':unittest.main()
