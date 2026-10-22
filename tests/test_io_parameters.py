"""Authored indirect I/O, independent register comments and CALL parameters."""
import json
import tempfile
from pathlib import Path
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


def ports(initial=None,**options):
    return rt.PortBank({'DIN':2,'DOUT':2,'GOUT':2,'AOUT':2},initial,type_codes={10:'DIN',20:'DOUT',30:'GOUT',40:'AOUT'},**options)


class IndirectPortTests(unittest.TestCase):
    def execute(self,body,initial=None,decl='n,s: INTEGER',**options):
        bank=ports(initial,**options)
        return run(body,decl=decl,context=rt.ExecutionContext(ports=bank)),bank

    def test_indirect_boolean_output_and_direct_read_share_storage(self):
        state,bank=self.execute('SET_PORT_VAL(20,1,1,s) GET_PORT_VAL(20,1,n,s) flag=DOUT[1]',decl='n,s: INTEGER flag: BOOLEAN')
        self.assertEqual((state['N'],state['S'],state['FLAG'],bank.read('DOUT',1)),(1,0,True,True))

    def test_boolean_get_supports_integer_real_string_and_boolean(self):
        state,_=self.execute('GET_PORT_VAL(10,1,n,s) GET_PORT_VAL(10,1,x,s) GET_PORT_VAL(10,1,text,s) GET_PORT_VAL(10,1,flag,s)',{('DIN',1):True},decl='n,s: INTEGER x: REAL text: STRING[4] flag: BOOLEAN')
        self.assertEqual((state['N'],state['X'],state['TEXT'],state['FLAG']),(1,1.,'1',True))

    def test_fractional_analog_get_preserves_integer_output(self):
        state,_=self.execute('n=7 GET_PORT_VAL(40,1,n,s)',{('AOUT',1):1.5})
        self.assertEqual((state['N'],state['S']),(7,3))

    def test_analog_and_group_roundtrip(self):
        state,bank=self.execute("SET_PORT_VAL(40,1,'1.25',s) GET_PORT_VAL(40,1,x,s) GET_PORT_VAL(40,1,text,s) SET_PORT_VAL(30,1,42,s) GET_PORT_VAL(30,1,n,s)",decl='n,s: INTEGER x: REAL text: STRING[8]')
        self.assertEqual((state['N'],state['X'],state['TEXT'],bank.read('GOUT',1)),(42,1.25,'1.25',42))

    def test_missing_value_preserves_output(self):
        state,_=self.execute('n=7 GET_PORT_VAL(20,1,n,s)');self.assertEqual((state['N'],state['S']),(7,1))

    def test_unmapped_type_or_outside_range_preserves_output(self):
        for code,number in ((99,1),(20,0),(20,3)):
            with self.subTest(code=code,number=number):
                state,_=self.execute(f'n=7 GET_PORT_VAL({code},{number},n,s)');self.assertEqual((state['N'],state['S']),(7,2))

    def test_input_write_requires_simulation(self):
        state,bank=self.execute('SET_PORT_VAL(10,1,1,s)',{('DIN',1):False})
        self.assertEqual((state['S'],bank.read('DIN',1)),(4,False))

    def test_simulated_input_value_is_initialized_and_writable(self):
        state,bank=self.execute('GET_PORT_SIM(10,1,n,s) old=n SET_PORT_SIM(10,1,1,s) SET_PORT_VAL(10,1,FALSE,s) GET_PORT_SIM(10,1,n,s) flag=DIN[1]',decl='n,s,old: INTEGER flag: BOOLEAN')
        self.assertEqual((state['OLD'],state['N'],state['S'],state['FLAG']),(0,1,0,False));self.assertIn(('DIN',1),bank.simulated)

    def test_invalid_simulation_value_preserves_flag_and_value(self):
        state,bank=self.execute('SET_PORT_SIM(10,1,2,s)',{('DIN',1):False})
        self.assertEqual((state['S'],bank.simulated,bank.read('DIN',1)),(3,set(),False))

    def test_bad_values_preserve_port(self):
        for code,value in ((20,'2'),(30,'-1'),(30,'1.5'),(40,"'nan'"),(40,"'bad'")):
            with self.subTest(code=code,value=value):
                state,bank=self.execute(f'SET_PORT_VAL({code},1,{value},s)')
                self.assertEqual((state['S'],bank.snapshot()),(3,{}))

    def test_no_mapping_is_an_explicit_context_error(self):
        p,_=compile_program('GET_PORT_VAL(1,1,n,s)',context=rt.ExecutionContext(ports=rt.PortBank({'DIN':1},{('DIN',1):True})))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type_codes'): p.run()

    def test_port_comments_default_and_capacity(self):
        state,bank=self.execute("GET_PORT_CMT(20,1,text,s) blank=text SET_PORT_CMT(20,1,'abcdefghijklmnopqr',s) GET_PORT_CMT(20,1,text,s)",decl='text,blank: STRING[20] s: INTEGER')
        self.assertEqual((state['BLANK'],state['TEXT'],bank.snapshot()),('','abcdefghijklmnop',{}))

    def test_port_comments_truncate_to_destination(self):
        state,_=self.execute('GET_PORT_CMT(10,1,text,s)',decl='text: STRING[3] s: INTEGER',comments={('DIN',1):'ready'})
        self.assertEqual(state['TEXT'],'rea')

    def test_alias_rejected_before_bank_access(self):
        p,_=compile_program('n=7 GET_PORT_VAL(20,1,n,n)',context=rt.ExecutionContext(ports=ports({('DOUT',1):True})))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
        self.assertEqual(p.snapshot()['N'],7)

    def test_input_capture_and_output_selector_once_in_order(self):
        bank=ports({('DOUT',1):True})
        state=run('count=0 GET_PORT_VAL(which(),1,a[choose_slot()],s)',decl='count,s: INTEGER a: ARRAY[2] OF INTEGER',routines='ROUTINE which: INTEGER BEGIN count=count+1 RETURN 20 END which ROUTINE choose_slot: INTEGER BEGIN count=count*10+2 RETURN 1 END choose_slot',context=rt.ExecutionContext(ports=bank))
        self.assertEqual((state['COUNT'],state['A'][0],state['S']),(12,1,0))

    def test_simulation_comments_and_type_codes_persist(self):
        bank=ports(comments={('DIN',1):'sensor'},simulated=[('DIN',1)])
        ctx=rt.ExecutionContext(ports=bank);run('SET_PORT_VAL(10,1,1,s)',context=ctx)
        config=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(config)
        self.assertEqual(restored.to_config(),config);self.assertEqual(restored.ports.read('DIN',1),True)
        config['ports']['comments']['DIN']['1']='changed';self.assertEqual(restored.ports.comments['DIN',1],'sensor')

    def test_invalid_type_code_and_metadata_configuration(self):
        for codes in ({True:'DIN'},{-1:'DIN'},{1:'MISSING'},{1:None}):
            with self.subTest(codes=codes),self.assertRaises(ValueError): rt.PortBank({'DIN':1},type_codes=codes)
        for extra in ({'type_codes':{'01':'DIN'}},{'comments':{'DIN':{'01':'bad'}}},{'simulated':{'DIN':[True]}},{'simulated':{'DIN':[2]}},{'comments':None},{'simulated':None},{'simulated':{'DIN':True}}):
            with self.subTest(extra=extra),self.assertRaises((ValueError,rt.KarelRuntimeError)):
                rt.ExecutionContext.from_config({'ports':dict(counts={'DIN':1},**extra)})

    def test_source_procedures_can_still_be_shadowed_by_internal_routines(self):
        state=run('SET_PORT_VAL(7)',routines='ROUTINE SET_PORT_VAL(x: INTEGER) BEGIN n=x END SET_PORT_VAL')
        self.assertEqual(state['N'],7)


class RegisterCommentTests(unittest.TestCase):
    def context(self): return rt.ExecutionContext(numeric=rt.NumericRegisters(2),strings=rt.StringRegisters(2),positions=rt.PositionRegisters(2))

    def test_all_comment_families_without_register_values(self):
        for kind,service in (('REG','numeric'),('SREG','strings'),('PREG','positions')):
            with self.subTest(kind=kind):
                ctx=self.context();state=run(f"SET_{kind}_CMT(1,'ready',s) GET_{kind}_CMT(1,text,s)",decl='text: STRING[20] s: INTEGER',context=ctx)
                self.assertEqual((state['TEXT'],state['S'],getattr(ctx,service).snapshot()),('ready',0,{}))

    def test_comment_default_does_not_initialize_register(self):
        ctx=self.context();state=run('GET_REG_CMT(1,text,s)',decl='text: STRING[20] s: INTEGER',context=ctx)
        self.assertEqual((state['TEXT'],state['S'],ctx.numeric.snapshot()),('',0,{}))

    def test_numeric_and_position_comments_have_16_character_capacity(self):
        for kind in ('REG','PREG'):
            with self.subTest(kind=kind):
                state=run(f"SET_{kind}_CMT(1,'abcdefghijklmnopqr',s) GET_{kind}_CMT(1,text,s)",decl='text: STRING[30] s: INTEGER',context=self.context())
                self.assertEqual(state['TEXT'],'abcdefghijklmnop')

    def test_string_register_comment_uses_254_capacity(self):
        ctx=self.context();value='x'*200;ctx.strings.comments.write(1,value)
        self.assertEqual(run('GET_SREG_CMT(1,text,s)',decl='text: STRING[254] s: INTEGER',context=ctx)['TEXT'],value)

    def test_range_failure_preserves_destination(self):
        ctx=self.context();state=run("text='old' GET_REG_CMT(3,text,s)",decl='text: STRING[20] s: INTEGER',context=ctx)
        self.assertEqual((state['TEXT'],state['S']),("old",2))

    def test_program_register_argument_takes_precedence(self):
        ctx=self.context();ctx.numeric.comments.write(1,'context')
        bank=rt.NumericRegisters(2,comments={1:'argument'})
        self.assertEqual(run('GET_REG_CMT(1,text,s)',decl='text: STRING[20] s: INTEGER',context=ctx,registers=bank)['TEXT'],'argument')

    def test_metadata_persistence_preserves_value_kinds_and_absence(self):
        ctx=self.context();ctx.numeric.write(1,7.);ctx.numeric.comments.write(2,'empty');ctx.positions.comments.write(1,'pose');ctx.strings.comments.write(1,'text')
        config=ctx.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(config)))
        self.assertEqual(restored.to_config(),config);self.assertIs(type(restored.numeric.read(1)[1]),float)
        self.assertEqual(restored.numeric.read(2),(1,None));self.assertEqual(restored.numeric.comments.read(2),(0,'empty'))
        self.assertEqual(rt.NumericRegisters.from_config(ctx.numeric.to_config()).to_config(),ctx.numeric.to_config())

    def test_legacy_context_shape_stays_identical_without_comments(self):
        ctx=self.context();config=ctx.to_config()
        self.assertFalse(any('comments' in config[kind] for kind in ('numeric','strings','positions')))
        self.assertEqual(rt.ExecutionContext.from_config(config).to_config(),config)

    def test_invalid_comment_input_preserves_bank(self):
        ctx=self.context();ctx.numeric.comments.write(1,'before')
        with self.assertRaises(rt.KarelRuntimeError): ctx.numeric.comments.write(1,'\u00fc')
        p,_=compile_program('GET_REG_CMT(1,text,s)',decl='text: STRING[20] s: INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit'): p.run()
        self.assertEqual(ctx.numeric.comments.read(1),(0,'before'))
        for values in ({'01':'bad'},{'0':'bad'},{'3':'bad'},{'1':True}):
            with self.subTest(values=values),self.assertRaises((ValueError,rt.KarelRuntimeError)):
                rt.NumericRegisters.from_config({'count':2,'values':{},'comments':values})


class CallParameterTests(unittest.TestCase):
    def program(self,values,body='GET_TPE_PRM(1,kind,n,x,text,s)',**options):
        return compile_program(body,decl='kind,n,s: INTEGER x: REAL text: STRING[8]',context=rt.ExecutionContext(parameters=rt.CallParameters({'T':values})),**options)[0]

    def test_each_type_writes_only_its_selected_output(self):
        for value,kind,key in ((42,1,'N'),(1.25,2,'X'),('ready',3,'TEXT')):
            with self.subTest(value=value):
                state=self.program({1:value},'n=7 x=2.5 text=\'old\' GET_TPE_PRM(1,kind,n,x,text,s)').run()
                expected={'N':7,'X':2.5,'TEXT':'old','KIND':kind,'S':0};expected[key]=value
                self.assertEqual(state,expected)

    def test_missing_parameter_preserves_all_value_outputs_and_type(self):
        state=self.program({},"kind=7 n=8 x=9.5 text='old' GET_TPE_PRM(1,kind,n,x,text,s)").run()
        self.assertEqual(state,{'KIND':7,'N':8,'X':9.5,'TEXT':'old','S':17042})

    def test_parameter_numbers_outside_1_to_10_are_absent(self):
        for number in (0,11,-1):
            with self.subTest(number=number): self.assertEqual(self.program({1:42},f'GET_TPE_PRM({number},kind,n,x,text,s)').run()['S'],17042)

    def test_unused_output_can_remain_uninitialized(self):
        state=self.program({1:42}).run();self.assertEqual(state['X'],{'uninitialized':True});self.assertEqual(state['TEXT'],{'uninitialized':True})

    def test_string_destination_truncates(self):
        self.assertEqual(self.program({1:'abcdefghijkl'}).run()['TEXT'],'abcdefgh')

    def test_linked_routine_uses_callers_arguments(self):
        ctx=rt.ExecutionContext(parameters=rt.CallParameters({'MAIN':{1:42},'LIB':{1:99}}))
        instance=translate_project({'a':source('LIB','',decl='n,kind,s: INTEGER x: REAL text: STRING[8]',routines='ROUTINE readarg: INTEGER BEGIN GET_TPE_PRM(1,kind,n,x,text,s) RETURN n END readarg'),
            'b':source('MAIN','n=readarg()',routines='ROUTINE readarg: INTEGER FROM LIB')}).instantiate(context=ctx)
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['N'],42)

    def test_concurrent_tasks_use_separate_arguments(self):
        body='GET_TPE_PRM(1,kind,n,x,text,s)'
        ctx=rt.ExecutionContext(parameters=rt.CallParameters({'MAIN':{1:42},'CHILD':{1:7}}))
        instance=translate_project({'a':source('MAIN',"RUN_TASK('CHILD',0,FALSE,FALSE,0,s) "+body,decl='n,kind,s: INTEGER x: REAL text: STRING[8]'),
            'b':source('CHILD',body,decl='n,kind,s: INTEGER x: REAL text: STRING[8]')}).instantiate(context=ctx)
        result=instance.run('MAIN');self.assertEqual((result['MAIN']['values']['N'],result['CHILD']['values']['N']),(42,7))

    def test_missing_service_and_output_overlap_fail_before_writes(self):
        for body,ctx in (('GET_TPE_PRM(1,kind,n,x,text,s)',None),('n=7 GET_TPE_PRM(1,n,n,x,text,s)',rt.ExecutionContext(parameters=rt.CallParameters({'T':{1:42}})))):
            with self.subTest(body=body):
                p,_=compile_program(body,decl='kind,n,s: INTEGER x: REAL text: STRING[8]',context=ctx)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                if ctx is not None: self.assertEqual(p.snapshot()['N'],7)

    def test_invalid_host_arguments_rejected(self):
        for values in ({0:1},{11:1},{True:1},{1:True},{1:float('nan')},{1:'\u00fc'},{1:'x'*255}):
            with self.subTest(values=values),self.assertRaises((ValueError,rt.KarelRuntimeError)): rt.CallParameters({'T':values})
        with self.assertRaises(ValueError): rt.CallParameters({'T':{},'t':{}})

    def test_persistence_and_defensive_config(self):
        ctx=rt.ExecutionContext(parameters=rt.CallParameters({'T':{1:42,2:1.25,3:'ready'}}))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder,'context.json');ctx.save(path);restored=rt.ExecutionContext.load(path)
            self.assertEqual(restored.to_config(),ctx.to_config())
        config=ctx.to_config();config['parameters']['T']['1']=7;self.assertEqual(ctx.parameters.read('T',1),42)

    def test_bad_serialized_keys_and_programs_rejected(self):
        for values in ({'T':{'01':1}},{'T':{'0':1}},{'T':{'11':1}},{'T':[]},{'bad name':{'1':1}}):
            with self.subTest(values=values),self.assertRaises(ValueError): rt.CallParameters.from_config(values)

    def test_signature_and_for_counter_guards(self):
        for body in ('GET_TPE_PRM(1,s)','GET_TPE_PRM(1,kind,x,x,text,s)','FOR n=1 TO 2 DO GET_TPE_PRM(1,kind,n,x,text,s) ENDFOR'):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,decl='kind,n,s: INTEGER x: REAL text: STRING[8]')


if __name__=='__main__': unittest.main()
