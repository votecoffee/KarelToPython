"""Authored offline TP records, source calls, lifecycle, sharing and JSON checks."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from karel2py.teach import TPE_NAMES
from tests.test_extended_services import compile_program,run,pose
from tests.test_project_scheduler import source


ROOT=Path(__file__).resolve().parents[1]


def context(*,groups=(1,2),limit=10):
    joint=rt.JointPosition(('JOINTPOS',2));joint.values=[10.,20.]
    return rt.ExecutionContext(teach_programs=rt.TeachPrograms({'DEMO':{'instructions':['first','second','third'],
        'positions':[{'number':1,'group':1,'value':pose(1,2,3),'uframe':2,'utool':3},
                     {'number':1,'group':2,'value':joint,'uframe':7,'utool':8}],
        'comments':{'1':'point one'}}},groups=groups,position_limit=limit))


OPEN="OPEN_TPE('demo',TPE_RWACC,TPE_NOREJ,h,s) "
DECL='h,s,n,k,a,f,t: INTEGER text: STRING[16] p: XYZWPREXT j: JOINTPOS9'


class TeachManagementTests(unittest.TestCase):
    def test_four_program_kinds_and_duplicate_creation(self):
        bank=rt.TeachPrograms(program_limit=4);ctx=rt.ExecutionContext(teach_programs=bank)
        for suffix,key in (('A','PT_MNE_UNDEF'),('B','PT_MNE_JOB'),('C','PT_MNE_PROC'),('D','PT_MNE_MACRO')):
            with self.subTest(key=key):self.assertEqual(run(f"CREATE_TPE('{suffix}',{key},s)",context=ctx)['S'],0)
        self.assertEqual(bank.entries,(('A','TP'),('B','JB'),('C','PR'),('D','MR')))
        self.assertEqual(bank.create('a'),5);self.assertEqual(bank.create('fifth'),6)

    def test_invalid_names_and_kind_do_not_create_programs(self):
        bank=rt.TeachPrograms();ctx=rt.ExecutionContext(teach_programs=bank)
        for name in ('','1BAD','HAS SPACE','FILE.TP','A'*37):
            with self.subTest(name=name):self.assertEqual(run(f"CREATE_TPE('{name}',PT_MNE_JOB,s)",context=ctx)['S'],2)
        self.assertEqual(run("CREATE_TPE('valid',PT_KRLPRG,s)",context=ctx)['S'],2)
        self.assertEqual(bank.entries,())

    def test_open_failure_preserves_handle_and_disjoint_outputs(self):
        ctx=context()
        for name,mode,reject,code in (('missing','TPE_RDACC','TPE_NOREJ',1),('demo','99','TPE_NOREJ',2),('demo','TPE_RDACC','99',2)):
            with self.subTest(name=name,mode=mode,reject=reject):
                data=run(f"h=77 OPEN_TPE('{name}',{mode},{reject},h,s)",decl='h,s: INTEGER',context=ctx)
                self.assertEqual((data['H'],data['S']),(77,code))
        p,_=compile_program("s=99 OPEN_TPE('demo',TPE_RWACC,TPE_NOREJ,s,s)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual((p.snapshot()['S'],ctx.teach_programs.open_count),(99,0))

    def test_copy_detaches_positions_comments_instructions_and_headers(self):
        ctx=context();bank=ctx.teach_programs
        data=run("COPY_TPE('demo','copy',FALSE,s) OPEN_TPE('copy',TPE_RWACC,TPE_NOREJ,h,s) p=GET_POS_TPE(h,1,s,1) p.x=9 SET_POS_TPE(h,1,p,s,1) SET_TPE_CMT(h,1,'copy only',s) DEL_INST_TPE(h,1,s) CLOSE_TPE(h,s) SET_ATTR_PRG('copy',AT_COMMENT,0,'header',s)",decl=DECL,context=ctx)
        self.assertEqual(data['S'],0)
        saved=bank.to_config()['programs']
        self.assertEqual(saved['DEMO']['positions'][0]['value']['value']['X'],1.)
        self.assertEqual(saved['COPY']['positions'][0]['value']['value']['X'],9.)
        self.assertEqual(saved['DEMO']['comments']['1'],'point one')
        self.assertEqual(saved['COPY']['comments']['1'],'copy only')
        self.assertEqual(saved['DEMO']['instructions'],['first','second','third'])
        self.assertEqual(saved['COPY']['instructions'],['second','third'])
        self.assertEqual(saved['COPY']['attributes'],{'AT_COMMENT':'header'})

    def test_copy_collision_busy_selected_and_capacity_guards(self):
        ctx=context();bank=ctx.teach_programs
        self.assertEqual(bank.copy('missing','copy'),1)
        self.assertEqual(bank.copy('demo','demo',True),2)
        self.assertEqual(bank.copy('demo','copy'),0)
        self.assertEqual(bank.copy('demo','copy'),5)
        code,handle=bank.open('demo',1)
        self.assertEqual(bank.copy('demo','copy',True),4);bank.close(handle)
        self.assertEqual(bank.select('copy'),0)
        self.assertEqual(bank.copy('demo','copy',True),4)
        bank.select('demo');self.assertEqual(bank.copy('demo','copy',True),0)

    def test_selection_is_metadata_and_rejects_open_program(self):
        ctx=context();bank=ctx.teach_programs
        self.assertEqual(run(OPEN+"SELECT_TPE('demo',s)",decl=DECL,context=ctx)['S'],4)
        self.assertIsNone(bank.selected)
        self.assertEqual(run("SELECT_TPE('demo',s)",context=ctx)['S'],0)
        self.assertEqual(bank.selected,'DEMO')

    def test_delete_instruction_is_one_based_and_keeps_position_data(self):
        ctx=context();bank=ctx.teach_programs
        self.assertEqual(run(OPEN+'DEL_INST_TPE(h,2,s)',decl=DECL,context=ctx)['S'],0)
        row=bank.to_config()['programs']['DEMO']
        self.assertEqual(row['instructions'],['first','third'])
        self.assertEqual(len(row['positions']),2)
        self.assertEqual(run(OPEN+'DEL_INST_TPE(h,0,s)',decl=DECL,context=ctx)['S'],2)

    def test_available_position_uses_all_groups_and_reports_full(self):
        ctx=context(limit=2)
        state=run(OPEN+'AVL_POS_NUM(h,n,s) p=GET_POS_TPE(h,1,s,1) SET_POS_TPE(h,2,p,s,1) n=99 AVL_POS_NUM(h,n,s)',decl=DECL,context=ctx)
        self.assertEqual((state['N'],state['S']),(99,6))


class TeachAccessTests(unittest.TestCase):
    def test_read_only_and_no_access_handles_do_not_mutate_data(self):
        ctx=context();before=ctx.teach_programs.to_config()
        for mode in ('TPE_RDACC','0'):
            body=f"OPEN_TPE('demo',{mode},TPE_NOREJ,h,s) SET_TPE_CMT(h,1,'changed',s)"
            with self.subTest(mode=mode):self.assertEqual(run(body,decl=DECL,context=ctx)['S'],3)
        self.assertEqual(ctx.teach_programs.to_config(),before)

    def test_foreign_handles_cannot_be_read_or_closed(self):
        ctx=context();bank=ctx.teach_programs;first=object();second=object()
        code,handle=bank.open('demo',2,owner=first)
        self.assertEqual(code,0)
        self.assertEqual(bank.close(handle,owner=second),3)
        self.assertEqual(bank.read_position(handle,1,owner=second)[0],3)
        self.assertEqual(bank.close(handle,owner=first),0)

    def test_reject_modes_are_symmetric_between_different_owners(self):
        for first_mode,first_reject,second_mode,second_reject,expected in (
                (1,0,1,0,0),(1,1,1,0,4),(1,2,1,0,0),(1,2,2,0,4),
                (2,0,1,2,4),(1,0,2,1,4),(0,4,0,0,4),(0,0,0,4,4),(2,3,2,0,4)):
            with self.subTest(case=(first_mode,first_reject,second_mode,second_reject)):
                bank=context().teach_programs
                self.assertEqual(bank.open('demo',first_mode,first_reject,owner=object())[0],0)
                self.assertEqual(bank.open('demo',second_mode,second_reject,owner=object())[0],expected)

    def test_same_owner_reopens_and_handle_numbers_do_not_reuse(self):
        bank=context().teach_programs;owner=object()
        _,a=bank.open('demo',2,4,owner=owner);_,b=bank.open('demo',2,4,owner=owner)
        self.assertNotEqual(a,b);bank.release_owner(owner)
        _,c=bank.open('demo',1,owner=owner);self.assertGreater(c,b)

    def test_exhausted_handle_sequence_does_not_wrap(self):
        bank=context().teach_programs;bank._sequence=2147483646
        self.assertEqual(bank.open('demo',1),(6,None));self.assertEqual(bank.open_count,0)


class TeachPositionTests(unittest.TestCase):
    def test_cartesian_and_joint_queries_return_detached_padded_values(self):
        ctx=context()
        state=run(OPEN+'p=GET_POS_TPE(h,1,s,1) p.x=99 j=GET_JPOS_TPE(h,1,s,2) GET_POS_TYP(h,1,2,k,a,s) GET_POS_FRM(h,1,2,f,t,s)',decl=DECL,context=ctx)
        self.assertEqual((state['J']['axes'],state['K'],state['A'],state['F'],state['T'],state['S']),([10.,20.,0.,0.,0.,0.,0.,0.,0.],9,2,7,8,0))
        self.assertEqual(ctx.teach_programs.to_config()['programs']['DEMO']['positions'][0]['value']['value']['X'],1.)

    def test_position_setters_preserve_group_and_frame_metadata(self):
        ctx=context()
        state=run(OPEN+'p=GET_POS_TPE(h,1,s,1) p.ext1=5 SET_EPOS_TPE(h,2,p,s,1) SET_POS_TPE(h,1,p,s,1) SET_TRNS_TPE(h,3,p,s) SET_JPOS_TPE(h,2,GET_JPOS_TPE(h,1,s,2),s,2) GET_POS_TYP(h,3,1,k,a,s) GET_POS_FRM(h,1,1,f,t,s)',decl=DECL,context=ctx)
        self.assertEqual((state['K'],state['F'],state['T'],state['S']),(1,2,3,0))
        positions=ctx.teach_programs.to_config()['programs']['DEMO']['positions']
        values={(row['group'],row['number']):row for row in positions}
        self.assertEqual(values[1,1]['value']['type'],['XYZWPR'])
        self.assertEqual(values[1,2]['value']['value']['EXT1'],5.)
        self.assertEqual(values[1,3]['value']['type'],['POSITION'])
        self.assertEqual(values[2,1]['value']['type'],['JOINTPOS',2])
        self.assertEqual(values[2,2]['value']['type'],['JOINTPOS',9])

    def test_optional_group_uses_calling_root_and_linked_calls(self):
        lib=source('LIB','',decl='s: INTEGER',routines="ROUTINE read_point(h: INTEGER): JOINTPOS9 BEGIN RETURN GET_JPOS_TPE(h,1,s) END read_point")
        main=source('MAIN',OPEN+'j=read_point(h)',decl='h,s: INTEGER j: JOINTPOS9',routines='ROUTINE read_point(h: INTEGER): JOINTPOS9 FROM LIB')
        instance=translate_project({'main':main,'lib':lib}).instantiate(context=context())
        instance.programs['MAIN']._state.robot_group=2;instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].snapshot()['J']['axes'][:2],[10.,20.])

    def test_missing_metadata_leaves_outputs_unchanged(self):
        for call in ('GET_POS_TYP(h,9,1,k,a,s)','GET_POS_FRM(h,9,1,k,a,s)'):
            state=run(OPEN+'k=7 a=8 '+call,decl=DECL,context=context())
            self.assertEqual((state['K'],state['A'],state['S']),(7,8,17038))

    def test_missing_or_wrong_representation_getter_sets_status_then_fails(self):
        for call,status in (('GET_POS_TPE(h,9,s)',17038),('GET_POS_TPE(h,1,s,2)',2)):
            ctx=context();p,_=compile_program(OPEN+'n=7 p='+call,decl=DECL,context=ctx)
            with self.subTest(call=call),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['S'],p.snapshot()['N'],ctx.teach_programs.open_count),(status,7,0))
            self.assertTrue(p.snapshot()['P']['X']['uninitialized'])

    def test_bad_address_and_frame_values_preserve_record(self):
        bank=context().teach_programs;_,h=bank.open('demo',2);before=bank.to_config()
        for number,group,frame,tool in ((0,1,None,None),(1,3,None,None),(1,1,-1,None),(1,1,None,32768)):
            with self.subTest(number=number,group=group,frame=frame,tool=tool):
                self.assertEqual(bank.write_position(h,number,pose(),group,uframe=frame,utool=tool),2)
                self.assertEqual(bank.to_config(),before)

    def test_host_writes_copy_complete_values_and_validate_before_mutation(self):
        bank=context().teach_programs;_,h=bank.open('demo',2);point=pose(9)
        self.assertEqual(bank.write_position(h,2,point,uframe=4,utool=5),0)
        point.values['X']=99.
        code,row=bank.read_position(h,2);self.assertEqual((row['value'].values['X'],row['uframe'],row['utool']),(9.,4,5))
        row['value'].values['X']=999.;self.assertEqual(bank.read_position(h,2)[1]['value'].values['X'],9.)
        before=bank.to_config()
        with self.assertRaises(rt.KarelRuntimeError):bank.write_position(h,2,rt.Structure(('XYZWPR',)))
        self.assertEqual(bank.to_config(),before)


class TeachCommentTests(unittest.TestCase):
    def test_comment_get_capacity_and_write_warning(self):
        ctx=context()
        state=run(OPEN+"SET_TPE_CMT(h,1,'abcdefghijklmnopqrs',s) n=s text='old' GET_TPE_CMT(h,1,text,s)",decl='h,s,n: INTEGER text: STRING[3]',context=ctx)
        self.assertEqual((state['N'],state['S'],state['TEXT']),(7,8,'old'))
        self.assertEqual(ctx.teach_programs.to_config()['programs']['DEMO']['comments']['1'],'abcdefghijklmnop')

    def test_comments_require_recorded_positions_and_empty_comment_is_valid(self):
        ctx=context()
        state=run(OPEN+"SET_TPE_CMT(h,9,'absent',s) n=s SET_TPE_CMT(h,1,'',s) GET_TPE_CMT(h,1,text,s)",decl=DECL,context=ctx)
        self.assertEqual((state['N'],state['S'],state['TEXT']),(17038,0,''))


class TeachLifecycleTests(unittest.TestCase):
    def test_completion_abort_failure_and_host_stop_release_handles(self):
        for tail,error in (('n=1',None),('ABORT',rt.KarelAbort),('n=1 DIV 0',rt.KarelRuntimeError)):
            with self.subTest(tail=tail):
                ctx=context();p,_=compile_program(OPEN+tail,decl=DECL,context=ctx)
                if error:
                    with self.assertRaises(error):p.run()
                else:p.run()
                self.assertEqual(ctx.teach_programs.open_count,0)
        ctx=context();p,_=compile_program(OPEN+'PAUSE',decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(ctx.teach_programs.open_count,1);p.stop();self.assertEqual(ctx.teach_programs.open_count,0)

    def test_pause_retains_handle_and_resume_reuses_it(self):
        ctx=context();p,_=compile_program(OPEN+'PAUSE GET_POS_TYP(h,1,1,k,a,s)',decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(ctx.teach_programs.open_count,1)
        self.assertEqual(p.resume()['K'],2);self.assertEqual(ctx.teach_programs.open_count,0)

    def test_scheduled_completion_and_failure_release_only_owner_handles(self):
        for tail,error in (('n=1',None),('n=1 DIV 0',rt.KarelRuntimeError)):
            with self.subTest(tail=tail):
                ctx=context();ctx.tasks=rt.TaskScheduler()
                first,_=compile_program(OPEN+tail,decl=DECL,context=ctx,cooperative=True)
                second,_=compile_program(OPEN+'PAUSE',decl=DECL,context=ctx)
                ctx.tasks.bind('first',first);ctx.tasks.bind('second',second)
                ctx.tasks.start('second');ctx.tasks.run();ctx.tasks.start('first')
                if error:
                    with self.assertRaises(error):ctx.tasks.run()
                else:ctx.tasks.run()
                self.assertEqual(ctx.teach_programs.open_count,1)
                ctx.tasks.stop('second');self.assertEqual(ctx.teach_programs.open_count,0)

    def test_linked_routine_handles_belong_to_caller_and_survive_return(self):
        library=source('LIB','',decl='s: INTEGER',routines="ROUTINE open_point(h: INTEGER) BEGIN OPEN_TPE('demo',TPE_RDACC,TPE_NOREJ,h,s) END open_point")
        main=source('MAIN','open_point(h) PAUSE GET_POS_TYP(h,1,1,k,a,s)',decl=DECL,routines='ROUTINE open_point(h: INTEGER) FROM LIB')
        ctx=context();instance=translate_project({'main':main,'lib':library}).instantiate(context=ctx)
        instance.run('MAIN');self.assertEqual(ctx.teach_programs.open_count,1)
        instance.scheduler.rename('MAIN','RENAMED');instance.scheduler.continue_task('RENAMED');instance.scheduler.run()
        self.assertEqual(instance.programs['MAIN'].snapshot()['K'],2);self.assertEqual(ctx.teach_programs.open_count,0)


class TeachPersistenceAndMetadataTests(unittest.TestCase):
    def test_json_roundtrip_keeps_data_and_selection_but_omits_handles(self):
        ctx=context();bank=ctx.teach_programs;bank.select('demo');_,h=bank.open('demo',2)
        saved=json.loads(json.dumps(ctx.to_config()))
        restored=rt.ExecutionContext.from_config(saved).teach_programs
        self.assertEqual(restored.to_config(),bank.to_config())
        self.assertEqual(restored.open_count,0);self.assertEqual(restored.selected,'DEMO')
        self.assertEqual(restored.close(h),3)
        saved['teach_programs']['programs']['DEMO']['instructions'][0]='changed'
        self.assertEqual(bank.to_config()['programs']['DEMO']['instructions'][0],'first')

    def test_program_listing_load_status_and_writable_headers_use_store(self):
        ctx=context()
        data=run("CREATE_TPE('job',PT_MNE_JOB,s) LOAD_STATUS('job',loaded,initialized) SET_ATTR_PRG('job',AT_COMMENT,0,'authored',s) GET_ATTR_PRG('job',AT_PROG_TYPE,n,text,s) GET_ATTR_PRG('job',AT_COMMENT,k,text,s) PROG_LIST('*',7,0,1,names,count,s)",decl='s,n,k,count: INTEGER text: STRING[16] loaded,initialized: BOOLEAN names: ARRAY[3] OF STRING[36]',context=ctx)
        self.assertEqual((data['LOADED'],data['INITIALIZED'],data['N'],data['TEXT'],data['NAMES']),(True,False,rt.PROGRAM_CONSTANTS['PT_MNE_JOB'],'authored',['DEMO','JOB','T']))
        self.assertEqual(ctx.teach_programs.to_config()['programs']['JOB']['attributes'],{'AT_COMMENT':'authored'})

    def test_header_write_guards_open_or_selected_program(self):
        ctx=context()
        self.assertEqual(run(OPEN+"SET_ATTR_PRG('demo',AT_COMMENT,0,'blocked',s)",decl=DECL,context=ctx)['S'],4)
        ctx.teach_programs.select('demo')
        self.assertEqual(run("SET_ATTR_PRG('demo',AT_COMMENT,0,'blocked',s)",context=ctx)['S'],4)

    def test_attached_karel_namespace_keeps_metadata_precedence(self):
        ctx=context();ctx.teach_programs.create('T')
        data=run("GET_ATTR_PRG('T',AT_PROG_TYPE,n,text,s)",decl='n,s: INTEGER text: STRING[16]',context=ctx)
        self.assertEqual(data['N'],rt.PROGRAM_CONSTANTS['PT_KRLPRG'])

    def test_separate_metadata_overlay_preserves_derived_type_and_line_count(self):
        ctx=context();ctx.program_attributes=rt.ProgramAttributes({'DEMO':{'attributes':{'AT_PROG_TYPE':rt.PROGRAM_CONSTANTS['PT_KRLPRG'],'AT_NUM_LINE':99,'AT_COMMENT':'overlay'}}})
        data=run("GET_ATTR_PRG('demo',AT_PROG_TYPE,n,text,s) GET_ATTR_PRG('demo',AT_NUM_LINE,k,text,s) GET_ATTR_PRG('demo',AT_COMMENT,a,text,s)",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['K'],data['TEXT']),(rt.PROGRAM_CONSTANTS['PT_MNE_UNDEF'],3,'overlay'))

    def test_malformed_json_and_incomplete_poses_are_rejected(self):
        config=context().teach_programs.to_config()
        variants=[]
        for key,value in (('unknown',1),('groups',[True]),('groups',[[1]]),('position_limit',True),('selected','absent')):
            row=deepcopy(config);row[key]=value;variants.append(row)
        row=deepcopy(config);row['programs']['DEMO']['positions'][0]['value']={'type':['ARRAY',[100000000],['INTEGER']],'value':[]};variants.append(row)
        row=deepcopy(config);row['programs']['DEMO']['positions'][0]['value']['value']['X']={'uninitialized':True};variants.append(row)
        row=deepcopy(config);row['programs']['DEMO']['comments']['9']='orphan';variants.append(row)
        row=deepcopy(config);row['programs']['demo']=deepcopy(row['programs']['DEMO']);variants.append(row)
        for item in variants:
            with self.subTest(item=item),self.assertRaises((ValueError,rt.KarelRuntimeError)):rt.TeachPrograms.from_config(item)
        self.assertEqual(config,context().teach_programs.to_config())


class TeachSourceChecks(unittest.TestCase):
    def test_exact_types_optional_groups_and_invalid_arity(self):
        calls=("OPEN_TPE('demo',TPE_RWACC,TPE_NOREJ,0,s)","OPEN_TPE('demo',TRUE,0,h,s)",
               'GET_POS_FRM(h,1,1,n,n,s)','SET_JPOS_TPE(h,1,p,s)',
               'SET_POS_TPE(h,1,j,s)','CLOSE_TPE(h)','CREATE_TPE(1,PT_MNE_JOB,s)')
        for call in calls:
            if call=='GET_POS_FRM(h,1,1,n,n,s)':
                p,_=compile_program(call,decl=DECL,context=context())
                with self.assertRaises(rt.KarelRuntimeError):p.run()
            else:
                with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(call,decl=DECL)

    def test_active_counter_outputs_direct_transitive_and_handler(self):
        call='AVL_POS_NUM(h,s,n)'
        for body,routines in ((f'FOR s=1 TO 2 DO {call} ENDFOR',''),('FOR s=1 TO 2 DO inspect_point() ENDFOR',f'ROUTINE inspect_point BEGIN {call} END inspect_point'),(f'CONDITION[1]: WHEN TRUE DO {call} ENDCONDITION FOR s=1 TO 2 DO ENDFOR','')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:compile_program(body,decl=DECL,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_function_status_outputs_participate_in_counter_protection(self):
        for call in ('p=GET_POS_TPE(h,1,s)','j=GET_JPOS_TPE(h,1,s,2)'):
            with self.subTest(call=call),self.assertRaises(TranslationError) as caught:compile_program('FOR s=1 TO 2 DO '+call+' ENDFOR',decl=DECL)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_uninitialized_inputs_preserve_bank_and_status(self):
        ctx=context();before=ctx.teach_programs.to_config()
        p,_=compile_program("s=99 CREATE_TPE(text,PT_MNE_JOB,s)",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],99);self.assertEqual(ctx.teach_programs.to_config(),before)

    def test_inputs_and_outputs_capture_once_in_source_order(self):
        ctx=context();routine="ROUTINE target: STRING BEGIN order=order*10+1 RETURN 'demo' END target ROUTINE mode: INTEGER BEGIN order=order*10+2 RETURN TPE_RDACC END mode ROUTINE reject: INTEGER BEGIN order=order*10+3 RETURN TPE_NOREJ END reject ROUTINE slot: INTEGER BEGIN order=order*10+4 RETURN 1 END slot"
        data=run('order=0 OPEN_TPE(target(),mode(),reject(),handles[slot()],s)',decl='order,s: INTEGER handles: ARRAY[1] OF INTEGER',routines=routine,context=ctx)
        self.assertEqual((data['ORDER'],data['HANDLES'],data['S']),(1234,[1],0))

    def test_missing_service_preserves_outputs(self):
        p,_=compile_program("h=99 s=88 OPEN_TPE('demo',TPE_RDACC,TPE_NOREJ,h,s)",decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'teach_programs'):p.run()
        self.assertEqual((p.snapshot()['H'],p.snapshot()['S']),(99,88))

    def test_user_routine_precedence_and_report(self):
        self.assertEqual(run('OPEN_TPE(7)',routines='ROUTINE OPEN_TPE(n: INTEGER) BEGIN s=n END OPEN_TPE')['S'],7)
        result=translate(source('T',"CREATE_TPE('demo',PT_MNE_UNDEF,s)"))
        self.assertFalse(result.report['teach_program_policy']['controller_validated'])
        self.assertEqual(set(result.report['teach_program_policy']['calls']),TPE_NAMES)


class TeachCliTests(unittest.TestCase):
    def test_all_calls_cli_translation_execution_and_json_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);generated=folder/'teach.py';report=folder/'report.json';saved=folder/'state.json'
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(ROOT/'examples/teach_programs.kl'),'-o',str(generated),'--report',str(report)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(set(json.loads(report.read_text(encoding='utf-8'))['teach_program_policy']['calls']),TPE_NAMES)
            import ast,os
            expected=json.loads((ROOT/'examples/teach_programs.expected.json').read_text(encoding='utf-8'))
            for initial in (ROOT/'examples/teach_programs.services.initial.json',saved):
                result=subprocess.run([sys.executable,'-X','utf8',str(generated),'--context',str(initial),'--state-out',str(saved)],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(ast.literal_eval(result.stdout),expected)
                config=json.loads(saved.read_text(encoding='utf-8'))
                expected_store=json.loads((ROOT/'examples/teach_programs.services.expected.json').read_text(encoding='utf-8'))['teach_programs']
                self.assertEqual(config['teach_programs'],expected_store)
                self.assertEqual(rt.ExecutionContext.load(saved).teach_programs.open_count,0)


if __name__=='__main__':unittest.main()
