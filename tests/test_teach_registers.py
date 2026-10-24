"""Authored TP caller-local registers, sharing, lifecycle and persisted CLI use."""
from copy import deepcopy
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from karel2py.teach import TPE_REGISTER_NAMES
from tests.test_extended_services import compile_program,run,pose
from tests.test_project_scheduler import source


ROOT=Path(__file__).resolve().parents[1]
DECL='n,s,k,a,f,t: INTEGER r: REAL real_flag: BOOLEAN text: STRING[16] p: XYZWPREXT j: JOINTPOS9'


def context(**options):
    point=pose(1,2,3)
    point=rt.TeachPrograms.position_value(point)
    joint=rt.JointPosition(('JOINTPOS',2));joint.values=[10.,20.]
    bank=rt.TeachPrograms({'DEMO':{'positions':[{'group':1,'number':1,'value':pose(99)}],
        'numeric_registers':{'1':42,'2':1.25},'string_registers':{'1':'local'},
        'position_registers':[{'group':1,'number':1,'value':point,'uframe':7,'utool':8},
                              {'group':2,'number':1,'value':joint,'uframe':2,'utool':3}]},
        'OTHER':{'numeric_registers':{'1':99}}},groups=(1,2),callers={'T':'DEMO'},
        register_limit=4,string_register_limit=4,position_register_limit=4,**options)
    return rt.ExecutionContext(teach_programs=bank,numeric=rt.NumericRegisters(4,{1:999}),
        strings=rt.StringRegisters(4,{1:'global'}),positions=rt.PositionRegisters(4,{1:pose(999)}))


class LocalScalarTests(unittest.TestCase):
    def test_numeric_get_selects_only_corresponding_output(self):
        ctx=context()
        data=run('n=-1 r=-2 GET_TPE_REG(1,real_flag,n,r,s) k=n GET_TPE_REG(2,real_flag,n,r,s)',decl=DECL,context=ctx)
        self.assertEqual((data['K'],data['N'],data['R'],data['REAL_FLAG'],data['S']),(42,42,1.25,True,0))

    def test_numeric_setters_switch_representation_and_keep_global_bank(self):
        ctx=context()
        data=run('SET_REAL_TPE_REG(1,7,s) GET_TPE_REG(1,real_flag,n,r,s) SET_INT_TPE_REG(2,-3,s)',decl=DECL,context=ctx)
        self.assertEqual((data['REAL_FLAG'],data['R'],data['S']),(True,7.,0))
        self.assertIs(type(ctx.teach_programs.read_register('T',1)[1]),float)
        self.assertEqual(ctx.teach_programs.read_register('T',2),(0,-3))
        self.assertEqual(ctx.numeric.snapshot(),{1:999})

    def test_uninitialized_and_out_of_range_numeric_preserve_outputs(self):
        for number,code in ((3,1),(0,2),(5,2)):
            with self.subTest(number=number):
                data=run(f'n=7 r=8 real_flag=TRUE GET_TPE_REG({number},real_flag,n,r,s)',decl=DECL,context=context())
                self.assertEqual((data['N'],data['R'],data['REAL_FLAG'],data['S']),(7,8.,True,code))

    def test_string_values_capacity_and_global_bank_are_separate(self):
        ctx=context(string_capacity=5)
        data=run("SET_TPE_STR_REG(2,'abcdef',s) GET_TPE_STR_REG(2,text,s)",decl=DECL,context=ctx)
        self.assertEqual((data['TEXT'],data['S']),('abcde',0));self.assertEqual(ctx.strings.snapshot(),{1:'global'})
        self.assertEqual(run("SET_TPE_STR_REG(2,'',s) GET_TPE_STR_REG(2,text,s)",decl=DECL,context=ctx)['TEXT'],'')

    def test_string_missing_range_and_small_destination_preserve_output(self):
        for number,code in ((1,8),(3,1),(5,2)):
            with self.subTest(number=number):
                data=run(f"text='old' GET_TPE_STR_REG({number},text,s)",decl='text: STRING[3] s: INTEGER',context=context())
                self.assertEqual((data['TEXT'],data['S']),('old',code))

    def test_missing_caller_has_status_and_never_uses_selected_program(self):
        ctx=context();ctx.teach_programs=rt.TeachPrograms({'DEMO':{}},selected='DEMO')
        data=run("n=7 r=8 real_flag=TRUE text='old' GET_TPE_REG(1,real_flag,n,r,s) k=s SET_INT_TPE_REG(1,3,s) a=s GET_TPE_STR_REG(1,text,s) f=s SET_TPE_STR_REG(1,'new',s)",decl=DECL,context=ctx)
        self.assertEqual((data['N'],data['R'],data['TEXT'],data['K'],data['A'],data['F'],data['S']),(7,8.,'old',9,9,9,9))
        self.assertNotIn('numeric_registers',ctx.teach_programs.to_config()['programs']['DEMO'])

    def test_binding_is_case_insensitive_explicit_and_defensive(self):
        bank=context().teach_programs
        self.assertEqual(bank.bind_caller('t','other'),0);self.assertEqual(bank.read_register('t',1),(0,99))
        copy=bank.callers;copy['T']='DEMO';self.assertEqual(bank.callers,{'T':'OTHER'})
        before=bank.callers
        self.assertEqual(bank.bind_caller('T','missing'),1);self.assertEqual(bank.bind_caller('bad name','demo'),2)
        self.assertEqual(bank.callers,before)

    def test_host_bad_values_do_not_mutate_bank(self):
        bank=context().teach_programs;before=bank.to_config()
        for value in (True,float('nan'),float('inf'),2147483647):
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):bank.write_register('T',1,value)
        with self.assertRaises(rt.KarelRuntimeError):bank.write_register('T',1,'nonascii\N{LATIN SMALL LETTER E WITH ACUTE}','string')
        self.assertEqual(bank.to_config(),before)


class LocalPositionTests(unittest.TestCase):
    def test_positions_are_separate_from_global_and_program_points(self):
        ctx=context()
        data=run('p=GET_TPE_POS_REG(1,s) p.x=9 SET_TPE_POS_REG(2,p,s) TPE_POS_REG_TYPE(2,k,a,s) TPE_POS_REG_FRM(1,f,t,s)',decl=DECL,context=ctx)
        self.assertEqual((data['P']['X'],data['K'],data['A'],data['F'],data['T'],data['S']),(9.,2,0,7,8,0))
        self.assertEqual(ctx.positions.read(1)[1].values['X'],999.)
        _,h=ctx.teach_programs.open('demo',1)
        self.assertEqual(ctx.teach_programs.read_position(h,1)[1]['value'].values['X'],99.)
        self.assertEqual(ctx.teach_programs.read_register('T',1,'position')[1]['value'].values['X'],1.)

    def test_extended_axes_survive_write_get_and_copy(self):
        ctx=context()
        data=run('p=GET_TPE_POS_REG(1,s) p.ext1=4 p.ext2=-5 p.ext3=6 SET_TPE_EPOS_REG(1,p,s) p=GET_TPE_POS_REG(1,s) TPE_POS_REG_TYPE(1,k,a,s)',decl=DECL,context=ctx)
        self.assertEqual((data['P']['EXT1'],data['P']['EXT2'],data['P']['EXT3'],data['K'],data['A']),(4.,-5.,6.,6,3))
        self.assertEqual(ctx.teach_programs.copy('demo','copy'),0)
        self.assertEqual(ctx.teach_programs.bind_caller('copycaller','copy'),0)
        row=ctx.teach_programs.read_register('copycaller',1,'position')[1]
        self.assertEqual((row['value'].values['EXT1'],row['uframe'],row['utool']),(4.,7,8))

    def test_narrow_joint_width_and_independent_groups(self):
        ctx=context()
        data=run('j=GET_TPE_JPOS_REG(1,s,2) SET_TPE_JPOS_REG(2,j,s,2) TPE_POS_REG_TYPE(1,2,k,a,s)',decl=DECL,context=ctx)
        self.assertEqual((data['J'],data['K'],data['A'],data['S']),({'axes':[10.,20.,0.,0.,0.,0.,0.,0.,0.]},9,2,0))
        self.assertEqual(ctx.teach_programs.read_register('T',2,'position',2)[1]['value'].spec,('JOINTPOS',9))
        self.assertEqual(ctx.teach_programs.read_register('T',2,'position',1),(17038,None))

    def test_group_default_comes_from_root_and_metadata_group_can_be_omitted(self):
        ctx=context();ctx.robot=rt.RobotContext(groups={2:rt.RobotContext()},active_group=2)
        data=run('j=GET_TPE_JPOS_REG(1,s) TPE_POS_REG_TYPE(1,k,a,s) TPE_POS_REG_FRM(1,f,t,s)',decl=DECL,context=ctx)
        self.assertEqual((data['K'],data['A'],data['F'],data['T'],data['S']),(9,2,2,3,0))

    def test_getter_failures_set_status_and_preserve_assignment(self):
        cases=(('GET_TPE_POS_REG(3,s)',17038),('GET_TPE_POS_REG(5,s)',2),
               ('GET_TPE_POS_REG(1,s,3)',2),('GET_TPE_POS_REG(1,s,2)',2))
        for call,code in cases:
            with self.subTest(call=call):
                p,_=compile_program('p=GET_TPE_POS_REG(1,s) p.x=7 p='+call,decl=DECL,context=context())
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual((p.snapshot()['P']['X'],p.snapshot()['S']),(7.,code))

    def test_absent_caller_position_function_and_metadata_status(self):
        ctx=rt.ExecutionContext(teach_programs=rt.TeachPrograms())
        p,_=compile_program('p=GET_TPE_POS_REG(1,s)',decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],9)
        data=run('k=7 a=8 TPE_POS_REG_TYPE(1,k,a,s)',decl=DECL,context=ctx)
        self.assertEqual((data['K'],data['A'],data['S']),(7,8,9))

    def test_missing_metadata_and_invalid_setter_preserve_data(self):
        ctx=context();before=ctx.teach_programs.to_config()
        data=run('k=7 a=8 TPE_POS_REG_TYPE(3,k,a,s) n=s TPE_POS_REG_FRM(5,k,a,s)',decl=DECL,context=ctx)
        self.assertEqual((data['K'],data['A'],data['N'],data['S']),(7,8,17038,2))
        self.assertEqual(run('p=GET_TPE_POS_REG(1,s) SET_TPE_POS_REG(0,p,s)',decl=DECL,context=ctx)['S'],2)
        self.assertEqual(ctx.teach_programs.to_config(),before)

    def test_host_metadata_preserved_and_snapshots_detached(self):
        bank=context().teach_programs;point=pose(7)
        self.assertEqual(bank.write_register('T',2,point,'position',uframe=4,utool=5),0)
        point.values['X']=99.;row=bank.read_register('T',2,'position')[1]
        self.assertEqual((row['value'].values['X'],row['uframe'],row['utool']),(7.,4,5))
        row['value'].values['X']=88.;self.assertEqual(bank.read_register('T',2,'position')[1]['value'].values['X'],7.)
        before=bank.to_config()
        with self.assertRaises(rt.KarelRuntimeError):bank.write_register('T',2,rt.Structure(('XYZWPR',)),'position')
        self.assertEqual(bank.write_register('T',2,pose(1),'position',uframe=-1),2)
        self.assertEqual(bank.to_config(),before)


class LocalSharingAndLifecycleTests(unittest.TestCase):
    def test_foreign_open_rejections_apply_to_local_reads_and_writes(self):
        for mask,read,write in ((0,0,0),(1,4,4),(2,0,4),(3,4,4),(4,4,4)):
            with self.subTest(mask=mask):
                ctx=context();bank=ctx.teach_programs;_,h=bank.open('demo',2,mask,owner=object())
                data=run('GET_TPE_REG(1,real_flag,n,r,s) k=s SET_INT_TPE_REG(1,9,s)',decl=DECL,context=ctx)
                self.assertEqual((data['K'],data['S']),(read,write));self.assertEqual(bank.open_count,1)

    def test_same_root_handles_do_not_block_local_registers(self):
        ctx=context()
        data=run("OPEN_TPE('demo',TPE_RWACC,TPE_ALLREJ,n,s) SET_INT_TPE_REG(1,7,s) GET_TPE_REG(1,real_flag,k,r,s)",decl=DECL,context=ctx)
        self.assertEqual((data['K'],data['S']),(7,0));self.assertEqual(ctx.teach_programs.open_count,0)

    def test_pause_resume_and_rerun_retain_local_data(self):
        ctx=context();p,_=compile_program('GET_TPE_REG(1,real_flag,n,r,s) SET_INT_TPE_REG(1,n+1,s) PAUSE GET_TPE_REG(1,real_flag,n,r,s)',decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(ctx.teach_programs.read_register('T',1),(0,43));self.assertEqual(p.resume()['N'],43)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['N'],44)

    def test_linked_routines_use_calling_root_after_scheduler_rename(self):
        ctx=context();bank=ctx.teach_programs;bank.bind_caller('MAIN','demo');bank.bind_caller('LIB','other')
        library=source('LIB','',routines='ROUTINE store(n: INTEGER) BEGIN SET_INT_TPE_REG(1,n,s) END store')
        main=source('MAIN','store(7) PAUSE store(8)',routines='ROUTINE store(n: INTEGER) FROM LIB')
        instance=translate_project({'main':main,'lib':library}).instantiate(context=ctx)
        instance.run('MAIN');instance.scheduler.rename('MAIN','RENAMED')
        instance.scheduler.continue_task('RENAMED');instance.scheduler.run()
        self.assertEqual(bank.read_register('MAIN',1),(0,8));self.assertEqual(bank.read_register('LIB',1),(0,99))

    def test_multiple_roots_can_share_or_isolate_caller_registers(self):
        ctx=context();bank=ctx.teach_programs;bank.bind_caller('A','demo');bank.bind_caller('B','demo');bank.bind_caller('C','other')
        sources={name:source(name,f'SET_INT_TPE_REG(1,{value},s)') for name,value in (('A',10),('B',20),('C',30))}
        instance=translate_project(sources).instantiate(context=ctx)
        for name in ('A','B','C'):instance.run(name)
        self.assertEqual(bank.read_register('A',1),(0,20));self.assertEqual(bank.read_register('C',1),(0,30))


class LocalPersistenceAndSourceTests(unittest.TestCase):
    def test_json_roundtrip_limits_bindings_values_metadata_and_empty_compatibility(self):
        bank=context().teach_programs;saved=json.loads(json.dumps(bank.to_config()));restored=rt.TeachPrograms.from_config(saved)
        self.assertEqual(restored.to_config(),saved);self.assertEqual(restored.open_count,0)
        self.assertEqual(restored.read_register('T',2),(0,1.25))
        saved['programs']['DEMO']['numeric_registers']['1']=999;self.assertEqual(bank.read_register('T',1),(0,42))
        old=json.loads((ROOT/'examples/teach_programs.services.initial.json').read_text())['teach_programs']
        self.assertEqual(rt.TeachPrograms.from_config(old).to_config(),old)

    def test_copy_includes_local_banks_without_changing_caller_bindings(self):
        bank=context().teach_programs;self.assertEqual(bank.copy('demo','copy'),0)
        bank.bind_caller('COPYCALLER','copy');bank.write_register('COPYCALLER',1,7)
        bank.write_register('COPYCALLER',1,'copy','string')
        self.assertEqual(bank.read_register('T',1),(0,42));self.assertEqual(bank.read_register('T',1,'string'),(0,'local'))
        self.assertEqual(bank.callers['T'],'DEMO')
        bank.copy('demo','copy',True);self.assertEqual(bank.read_register('COPYCALLER',1),(0,42))

    def test_local_values_mark_program_initialized(self):
        ctx=rt.ExecutionContext(teach_programs=rt.TeachPrograms({'DEMO':{}},callers={'T':'demo'}))
        data=run("LOAD_STATUS('demo',loaded,initialized) before=initialized SET_INT_TPE_REG(1,7,s) LOAD_STATUS('demo',loaded,initialized)",decl='s: INTEGER loaded,initialized,before: BOOLEAN',context=ctx)
        self.assertEqual((data['LOADED'],data['BEFORE'],data['INITIALIZED']),(True,False,True))

    def test_malformed_local_config_is_rejected(self):
        base=context().teach_programs.to_config();variants=[]
        for key,value in (('register_limit',True),('string_register_limit',0),('position_register_limit',32768),('string_capacity',255),('callers',[]),('callers',{'T':'absent'}),('callers',{'T':'demo','t':'other'})):
            config=deepcopy(base);config[key]=value;variants.append(config)
        for field,value in (('numeric_registers',[]),('numeric_registers',{'01':3}),('numeric_registers',{'5':3}),('numeric_registers',{'1':True}),('numeric_registers',{'1':float('nan')}),('string_registers',{'1':'x'*255}),('string_registers',{'1':7}),('position_registers',{})):
            config=deepcopy(base);config['programs']['DEMO'][field]=value;variants.append(config)
        for field,value in (('group',True),('number',5),('uframe',-1)):
            config=deepcopy(base);config['programs']['DEMO']['position_registers'][0][field]=value;variants.append(config)
        for config in variants:
            with self.subTest(config=config),self.assertRaises((ValueError,TypeError,rt.KarelRuntimeError)):rt.TeachPrograms.from_config(config)

    def test_bad_typed_local_register_is_rejected_before_decoder(self):
        config=context().teach_programs.to_config()
        config['programs']['DEMO']['positions']=[]
        config['programs']['DEMO']['position_registers'][0]['value']={'type':['ARRAY',[100000000],['INTEGER']],'value':[]}
        with patch('karel2py.storage.decode_typed',side_effect=AssertionError('decoder must not run')):
            with self.assertRaises(ValueError):rt.TeachPrograms.from_config(config)

    def test_types_and_arity_are_checked(self):
        calls=('SET_INT_TPE_REG(1,TRUE,s)','SET_REAL_TPE_REG(1,\'text\',s)',
            'GET_TPE_REG(1,real_flag,n,r)','GET_TPE_STR_REG(1,n,s)',
            'SET_TPE_JPOS_REG(1,p,s)','SET_TPE_EPOS_REG(1,j,s)',
            'GET_TPE_POS_REG(1,0)','TPE_POS_REG_TYPE(1,TRUE,k,a,s)')
        for call in calls:
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(call,decl=DECL)

    def test_disjoint_outputs_are_checked_before_mutation(self):
        ctx=context();before=ctx.teach_programs.to_config()
        for call in ('GET_TPE_REG(1,real_flag,s,r,s)','TPE_POS_REG_FRM(1,s,s,s)'):
            p,_=compile_program('s=99 '+call,decl=DECL,context=ctx)
            with self.subTest(call=call),self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
            self.assertEqual(p.snapshot()['S'],99)
        self.assertEqual(ctx.teach_programs.to_config(),before)

    def test_active_counter_protection_direct_transitive_and_getter(self):
        cases=(('FOR s=1 TO 2 DO SET_INT_TPE_REG(1,7,s) ENDFOR',''),
            ('FOR s=1 TO 2 DO p=GET_TPE_POS_REG(1,s) ENDFOR',''),
            ('FOR s=1 TO 2 DO inspect_local() ENDFOR','ROUTINE inspect_local BEGIN TPE_POS_REG_TYPE(1,k,a,s) END inspect_local'))
        for body,routines in cases:
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:compile_program(body,decl=DECL,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_inputs_capture_once_in_source_order(self):
        ctx=context();routines='ROUTINE slot: INTEGER BEGIN order=order*10+1 RETURN 1 END slot ROUTINE value: INTEGER BEGIN order=order*10+2 RETURN 7 END value ROUTINE output_slot: INTEGER BEGIN order=order*10+3 RETURN 1 END output_slot'
        data=run('order=0 SET_INT_TPE_REG(slot(),value(),statuses[output_slot()])',decl='order: INTEGER statuses: ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        self.assertEqual((data['ORDER'],data['STATUSES']),(123,[0]));self.assertEqual(ctx.teach_programs.read_register('T',1),(0,7))

    def test_uninitialized_inputs_missing_service_and_user_precedence(self):
        ctx=context();before=ctx.teach_programs.to_config();p,_=compile_program('s=99 SET_INT_TPE_REG(1,n,s)',decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['S'],ctx.teach_programs.to_config()),(99,before))
        p,_=compile_program('s=99 SET_INT_TPE_REG(1,7,s)',decl=DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'teach_programs'):p.run()
        self.assertEqual(p.snapshot()['S'],99)
        self.assertEqual(run('SET_INT_TPE_REG(7)',routines='ROUTINE SET_INT_TPE_REG(n: INTEGER) BEGIN s=n END SET_INT_TPE_REG')['S'],7)

    def test_all_calls_cli_json_execution_and_saved_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);generated=folder/'registers.py';report=folder/'report.json';saved=folder/'state.json'
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(ROOT/'examples/teach_registers.kl'),'-o',str(generated),'--report',str(report)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            policy=json.loads(report.read_text())['teach_register_policy']
            self.assertEqual(set(policy['calls']),TPE_REGISTER_NAMES);self.assertFalse(policy['controller_validated'])
            expected=json.loads((ROOT/'examples/teach_registers.expected.json').read_text())
            expected_store=json.loads((ROOT/'examples/teach_registers.services.expected.json').read_text())['teach_programs']
            for initial in (ROOT/'examples/teach_registers.services.initial.json',saved):
                result=subprocess.run([sys.executable,'-X','utf8',str(generated),'--context',str(initial),'--state-out',str(saved)],cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(ast.literal_eval(result.stdout),expected)
                restored=rt.ExecutionContext.load(saved).teach_programs
                self.assertEqual(restored.to_config(),expected_store);self.assertEqual(restored.open_count,0)


if __name__=='__main__':unittest.main()
