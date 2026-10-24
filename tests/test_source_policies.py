"""Authored source policies and explicit offline default-group/device behavior."""
import json
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run,pose
from tests.legacy_numeric_support import translate as legacy_translate


class SourcePolicyTests(unittest.TestCase):
    def test_all_policy_fields_and_defensive_observation(self):
        prefix='%DEFGROUP=2\n%LOCKGROUP=1,3\n%STACKSIZE=600\n%DELAY=12\n%CMOSVARS\n%CMOS2SHADOW\n%UNINITVARS\n%CRTDEVICE'
        p,result=compile_program('n=7',prefix=prefix)
        expected=dict(default_group=2,lock_groups=(1,3),storage='SHADOW',cmos_to_shadow=True,
            uninitialized_variables=True,default_io_device='CRT/KB',periodic_delay_ms=12,stack_words=600)
        self.assertEqual(p.source_settings,expected)
        copy=p.source_settings;copy['default_group']=99;self.assertEqual(p.source_settings,expected)
        self.assertEqual(p.source_directives[1],('%LOCKGROUP',(1,3)))
        self.assertEqual(p.run()['N'],7);json.dumps(result.report)

    def test_defaults_shadow_and_cmos_mapping(self):
        for prefix,storage in (('','DRAM'),('%CMOSVARS','CMOS'),('%SHADOWVARS','SHADOW'),('%CMOS2SHADOW','DRAM')):
            with self.subTest(prefix=prefix):
                p,_=compile_program('n=7',prefix=prefix)
                self.assertEqual((p.source_settings['storage'],p.source_settings['periodic_delay_ms'],p.source_settings['stack_words']),(storage,8,300))

    def test_explicit_default_group_wins_over_data_inference_and_context(self):
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(3,{(1,1):pose(1),(2,1):pose(2)},groups=(1,2)),robot=rt.RobotContext())
        data=run('p=GET_POS_REG(1,s) SET_EPOS_REG(2,p,s) POS_REG_TYPE(2,k,a,s)',prefix='%DEFGROUP=2',decl='p: XYZWPREXT IN GROUP[1] s,k,a: INTEGER',context=ctx)
        self.assertEqual((data['P']['X'],data['S'],data['K']),(2.,0,6))
        self.assertEqual(ctx.positions.read(2,1),(1,None));self.assertEqual(ctx.positions.read(2,2)[1].values['X'],2.)

    def test_explicit_call_group_wins_over_source_default(self):
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(1,{(1,1):pose(1),(2,1):pose(2)},groups=(1,2)))
        self.assertEqual(run('p=GET_POS_REG(1,s,1)',prefix='%DEFGROUP=2',decl='p: XYZWPREXT s: INTEGER',context=ctx)['P']['X'],1.)

    def test_missing_default_group_fails_without_fallback(self):
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(1,{1:pose(1)}))
        p,_=compile_program('p=GET_POS_REG(1,s)',prefix='%DEFGROUP=2',decl='p: XYZWPREXT s: INTEGER',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],2)

    def test_linked_calls_use_root_default_group(self):
        ctx=rt.ExecutionContext(positions=rt.PositionRegisters(1,{(2,1):pose(2)},groups=(1,2)))
        library='PROGRAM LIB\n%DEFGROUP=1\nVAR s: INTEGER ROUTINE get_x: REAL VAR p: XYZWPREXT BEGIN p=GET_POS_REG(1,s) RETURN p.x END get_x BEGIN END LIB'
        main='PROGRAM MAIN\n%DEFGROUP=2\nVAR x: REAL ROUTINE get_x: REAL FROM LIB BEGIN x=get_x() END MAIN'
        instance=translate_project({'main':main,'lib':library}).instantiate(context=ctx);instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].snapshot()['X'],2.)

    def test_crt_labels_read_metadata_and_retains_text_callback(self):
        seen=[];written=[]
        def read(request):seen.append(request);request['device']='mutated';return [7]
        p,_=compile_program("READ(n) WRITE('done')",prefix='%CRTDEVICE',read=read,write=written.append)
        self.assertEqual(p.run()['N'],7);self.assertEqual(written,['done'])
        self.assertEqual((p.read_requests[0]['device'],p.write_requests[0]['device']),('CRT/KB','CRT/KB'))

    def test_crt_does_not_label_explicit_file_io(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles())
        p,_=compile_program("OPEN FILE f('RW','test') WRITE f('data') CLOSE FILE f",prefix='%CRTDEVICE',decl='f: FILE',context=ctx)
        p.run();self.assertEqual(p.write_requests,());self.assertEqual(ctx.files.snapshot(),{'test':b'data'})

    def test_metadata_does_not_allocate_reset_or_insert_delays(self):
        for prefix in ('%UNINITVARS','%CMOSVARS','%SHADOWVARS','%DELAY=0','%DELAY=86400000','%STACKSIZE=1','%LOCKGROUP=1'):
            delays=[]
            with self.subTest(prefix=prefix):
                p,_=compile_program('IF UNINIT(n) THEN n=0 ENDIF n=n+1',prefix=prefix,sleep=delays.append)
                self.assertEqual(p.run()['N'],1);self.assertEqual(p.run()['N'],2);self.assertEqual(delays,[])

    def test_numeric_bounds(self):
        for directive,values in (('%DEFGROUP',(1,32)),('%STACKSIZE',(1,32767)),('%DELAY',(0,86400000))):
            for value in values:
                with self.subTest(directive=directive,value=value):compile_program('n=7',prefix=f'{directive}={value}')
        for directive,value in (('%DEFGROUP',0),('%DEFGROUP',33),('%STACKSIZE',0),('%STACKSIZE',32768),('%DELAY',86400001)):
            with self.subTest(directive=directive),self.assertRaises(TranslationError) as caught:compile_program('',prefix=f'{directive}={value}')
            self.assertEqual(caught.exception.code,'E_DIRECTIVE_VALUE')

    def test_flags_and_numeric_syntax(self):
        for prefix in ('%CMOSVARS=1','%SHADOWVARS extra','%CRTDEVICE=TRUE','%DEFGROUP=-1','%DELAY=1+2','%STACKSIZE=1.5','%LOCKGROUP=1,,2','%LOCKGROUP='):
            with self.subTest(prefix=prefix),self.assertRaises(TranslationError) as caught:compile_program('',prefix=prefix)
            self.assertEqual(caught.exception.code,'E_DIRECTIVE_SYNTAX')

    def test_duplicates_conflicts_and_group_bounds(self):
        for prefix,code in (('%DEFGROUP=1\n%DEFGROUP=2','E_DIRECTIVE_DUPLICATE'),('%CRTDEVICE\n%CRTDEVICE','E_DIRECTIVE_DUPLICATE'),
            ('%LOCKGROUP=1,1','E_DIRECTIVE_VALUE'),('%LOCKGROUP=0','E_DIRECTIVE_VALUE'),('%LOCKGROUP=33','E_DIRECTIVE_VALUE'),
            ('%LOCKGROUP=1\n%NOLOCKGROUP','E_DIRECTIVE_VALUE'),('%NOLOCKGROUP\n%LOCKGROUP=1','E_DIRECTIVE_VALUE'),
            ('%CMOSVARS\n%SHADOWVARS','E_DIRECTIVE_VALUE'),('%SHADOWVARS\n%CMOSVARS','E_DIRECTIVE_VALUE')):
            with self.subTest(prefix=prefix),self.assertRaises(TranslationError) as caught:compile_program('',prefix=prefix)
            self.assertEqual(caught.exception.code,code)

    def test_late_directives_and_legacy_mode_stay_blocked(self):
        for prefix in ('%DEFGROUP=2','%LOCKGROUP=1','%STACKSIZE=600','%DELAY=12','%CMOSVARS','%CMOS2SHADOW','%SHADOWVARS','%UNINITVARS','%CRTDEVICE'):
            with self.subTest(prefix=prefix),self.assertRaises(TranslationError) as caught:translate('PROGRAM T\nVAR n: INTEGER\n'+prefix+'\nBEGIN END T')
            self.assertEqual(caught.exception.code,'E_DIRECTIVE_POSITION')
            with self.assertRaises(TranslationError):legacy_translate('PROGRAM T\n'+prefix+'\nBEGIN END T')

    def test_default_io_requests_retain_existing_schema(self):
        p,_=compile_program("READ(n) WRITE('done')",read=lambda request:[7]);p.run()
        self.assertNotIn('device',p.read_requests[0]);self.assertNotIn('device',p.write_requests[0])


if __name__=='__main__':unittest.main()
