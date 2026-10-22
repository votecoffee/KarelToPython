"""Authored static-variable inspection, pagination and guarded output fixtures."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from karel2py.inspection import TYPE_CODES
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


INFO="VAR_INFO('','value',empty,label,code,dims,length,status)"
OUTPUTS='empty: BOOLEAN label: STRING[32] code,length,status: INTEGER dims: ARRAY[3] OF INTEGER'


def info(declaration,body='',**options):
    return run(body+' '+INFO,decl=declaration+' '+OUTPUTS,**options)


class VariableInfoTests(unittest.TestCase):
    def test_scalar_metadata_and_initialization(self):
        for kind,code in (('INTEGER',16),('REAL',17),('BOOLEAN',18),('STRING[12]',209)):
            with self.subTest(kind=kind):
                state=info('value: '+kind)
                self.assertEqual((state['EMPTY'],state['LABEL'],state['CODE'],state['DIMS'],state['LENGTH'],state['STATUS']),
                                 (True,kind.split('[')[0],code,[0,0,0],12 if code==209 else 0,0))

    def test_initialized_scalars(self):
        for kind,text in (('INTEGER','7'),('REAL','1.25'),('BOOLEAN','FALSE'),('STRING[12]',"'abc'")):
            with self.subTest(kind=kind): self.assertFalse(info('value: '+kind,'value='+text)['EMPTY'])

    def test_builtin_records(self):
        for kind in ('CONFIG','VECTOR','POSITION','XYZWPR','XYZWPREXT'):
            with self.subTest(kind=kind):
                state=info('value: '+kind)
                self.assertEqual((state['EMPTY'],state['LABEL'],state['CODE']),(True,kind,TYPE_CODES[kind]))

    def test_initialized_vector(self): self.assertFalse(info('value: VECTOR','value=VEC(1,2,3)')['EMPTY'])

    def test_named_structure_and_partial_leaves(self):
        state=info('value: packet','value.id=7',prefix='TYPE packet=STRUCTURE id: INTEGER text: STRING[4] ENDSTRUCTURE')
        self.assertEqual((state['LABEL'],state['CODE'],state['EMPTY']),('PACKET',210,True))

    def test_full_structure(self):
        state=info('value: packet',"value.id=7 value.text='done'",prefix='TYPE packet=STRUCTURE id: INTEGER text: STRING[4] ENDSTRUCTURE')
        self.assertFalse(state['EMPTY'])

    def test_array_dimensions_and_leaf_type(self):
        state=info('value: ARRAY[2,3] OF STRING[7]')
        self.assertEqual((state['DIMS'],state['LABEL'],state['CODE'],state['LENGTH'],state['EMPTY']),([2,3,0],'STRING',209,7,True))

    def test_nested_array_dimensions(self):
        state=info('value: ARRAY[2] OF row_t',prefix='TYPE row_t=ARRAY[3,4] OF INTEGER')
        self.assertEqual((state['DIMS'],state['CODE']),([2,3,4],16))

    def test_array_of_named_records(self):
        state=info('value: ARRAY[2] OF packet',prefix='TYPE packet=STRUCTURE id: INTEGER ENDSTRUCTURE')
        self.assertEqual((state['DIMS'],state['LABEL'],state['CODE']),([2,0,0],'PACKET',210))

    def test_all_initialized_array(self): self.assertFalse(info('value: ARRAY[2] OF INTEGER','value[1]=1 value[2]=2')['EMPTY'])

    def test_unknown_byte_has_no_initialization_tracking(self):
        state=info('value: ARRAY[2] OF BYTE')
        self.assertEqual((state['EMPTY'],state['CODE'],state['VALUE']),(False,24,[{'unknown_byte':True}]*2))

    def test_short_sentinel_is_uninitialized(self):
        state=run("value[1]=32767 VAR_INFO('','value[1]',empty,label,code,dims,length,status)",decl='value: ARRAY[1] OF SHORT '+OUTPUTS)
        self.assertEqual((state['EMPTY'],state['CODE']),(True,23))

    def test_joint_width_codes(self):
        for width in range(1,10):
            with self.subTest(width=width):
                state=info('value: JOINTPOS'+str(width))
                self.assertEqual((state['LABEL'],state['CODE'],state['EMPTY']),(f'JOINTPOS{width}',25+16*(width-1),True))

    def test_jointpos_alias_uses_canonical_width(self): self.assertEqual(info('value: JOINTPOS')['LABEL'],'JOINTPOS9')

    def test_transparent_alias_uses_canonical_type(self):
        self.assertEqual(info('value: distance',prefix='TYPE distance=REAL')['LABEL'],'REAL')

    def test_static_field_and_subscript(self):
        state=run("value[2].text='abc' VAR_INFO('t','VaLuE[2].TeXt',empty,label,code,dims,length,status)",
                  decl='value: ARRAY[2] OF packet '+OUTPUTS,prefix='TYPE packet=STRUCTURE text: STRING[6] ENDSTRUCTURE')
        self.assertEqual((state['EMPTY'],state['LABEL'],state['DIMS'],state['LENGTH']),(False,'STRING',[0,0,0],6))

    def test_readonly_orientation_can_be_inspected(self):
        state=run("VAR_INFO('','value.normal',empty,label,code,dims,length,status)",decl='value: POSITION '+OUTPUTS)
        self.assertEqual((state['EMPTY'],state['LABEL'],state['STATUS']),(True,'VECTOR',0))

    def test_globals_ignore_routine_local_shadow(self):
        state=info('value: INTEGER',"value=7 inspect",routines='ROUTINE inspect VAR value: STRING[5] BEGIN '+INFO+' END inspect')
        self.assertEqual((state['EMPTY'],state['LABEL']),(False,'INTEGER'))

    def test_query_target_can_be_one_output(self):
        state=run("VAR_INFO('','empty',empty,label,code,dims,length,status)",decl=OUTPUTS)
        self.assertEqual((state['EMPTY'],state['LABEL']),(True,'BOOLEAN'))

    def test_type_name_obeys_destination_capacity(self):
        state=run(INFO,decl='value: POSITION '+OUTPUTS.replace('STRING[32]','STRING[3]'))
        self.assertEqual((state['LABEL'],state['STATUS']),('POS',0))

    def test_foreign_attached_globals(self):
        lib,_=compile_program('value=7',decl='value: INTEGER');lib._state.program_name='LIB'
        ctx=lib._state.execution;ctx.variables.attach('LIB',lib._state)
        state=run(INFO.replace("'','value'","'LIB','VALUE'"),decl=OUTPUTS,context=ctx)
        self.assertEqual((state['LABEL'],state['STATUS']),('INTEGER',0))

    def test_explicit_system_root(self):
        ctx=rt.ExecutionContext();ctx.variables.define('SYSTEM','$LIMIT',('INTEGER',),7)
        state=run(INFO.replace("'value'","'$LIMIT'"),decl=OUTPUTS,context=ctx)
        self.assertEqual((state['EMPTY'],state['CODE'],state['STATUS']),(False,16,0))

    def test_path_header_and_node_selectors(self):
        prefix='TYPE head_t=STRUCTURE id: INTEGER ENDSTRUCTURE node_t=STRUCTURE point: VECTOR ENDSTRUCTURE'
        for path,name in (('value','PATH'),('value.id','INTEGER'),('value[1].point','VECTOR')):
            with self.subTest(path=path):
                state=run('APPEND_NODE(value,status) '+INFO.replace("'value'",repr(path)),prefix=prefix,
                          decl='value: PATH NODEDATA=node_t,PATHHEADER=head_t '+OUTPUTS)
                self.assertEqual((state['EMPTY'],state['LABEL'],state['STATUS']),(True,name,0))

    def test_empty_path_is_initialized_container(self): self.assertEqual((info('value: PATH')['EMPTY']),False)

    def test_file_open_state(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles())
        self.assertTrue(info('value: FILE',context=ctx)['EMPTY'])
        self.assertFalse(info('value: FILE',"OPEN FILE value('W','out')",context=ctx)['EMPTY'])

    def test_unsupported_queue_code_preserves_metadata(self):
        state=info('value: QUEUE_TYPE',"empty=FALSE label='old' code=7 length=9 dims[1]=5")
        self.assertEqual((state['STATUS'],state['LABEL'],state['CODE'],state['EMPTY'],state['DIMS'][0]),(4,'old',7,False,5))

    def test_failed_lookup_preserves_all_metadata(self):
        for path in ('missing','value[0]','value[2]','value[x]','value.__class__'):
            with self.subTest(path=path):
                state=run("empty=FALSE label='old' code=7 length=9 dims[1]=5 "+INFO.replace("'value'",repr(path)),decl='value: ARRAY[1] OF INTEGER '+OUTPUTS)
                self.assertEqual((state['STATUS'],state['LABEL'],state['CODE'],state['EMPTY'],state['DIMS'][0]),(1,'old',7,False,5))

    def test_dimensions_buffer_must_have_exact_size(self):
        p,_=compile_program('code=7 '+INFO,decl='value: INTEGER '+OUTPUTS.replace('ARRAY[3]','ARRAY[2]'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,r'ARRAY\[3\]'): p.run()
        self.assertEqual(p.snapshot()['CODE'],7)

    def test_output_overlap_rejected(self):
        p,_=compile_program(INFO.replace('code,dims,length,status','code,dims,length,code'),decl='value: INTEGER '+OUTPUTS)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()

    def test_partial_record_invalid_known_leaf_fails_before_outputs(self):
        p,_=compile_program("label='old' "+INFO,decl='value: POSITION '+OUTPUTS)
        p._state.values['VALUE'].values['CONFIG_DATA'].values['CFG_TURN_NO1']=8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): p.run()
        self.assertEqual(p.snapshot()['LABEL'],'old')

    def test_array_schema_failure(self):
        p,_=compile_program(INFO,decl='value: ARRAY[2] OF INTEGER '+OUTPUTS);p._state.values['VALUE'].values.pop()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ARRAY'): p.run()

    def test_partial_state_persists_without_query_side_effects(self):
        p,_=compile_program('value.x=1 '+INFO,decl='value: VECTOR '+OUTPUTS);p.run()
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(p._state.execution.to_config())))
        other,_=compile_program(INFO,decl='value: VECTOR '+OUTPUTS,context=restored)
        self.assertTrue(other.run()['EMPTY']);self.assertEqual(other.snapshot()['VALUE']['Y'],{'uninitialized':True})


    def test_arguments_and_output_selectors_evaluate_once_in_order(self):
        routines="""ROUTINE program_name: STRING BEGIN tick=tick*10+1 RETURN '' END program_name
ROUTINE variable_name: STRING BEGIN tick=tick*10+2 RETURN 'VALUE' END variable_name
ROUTINE flag_slot: INTEGER BEGIN tick=tick*10+3 RETURN 1 END flag_slot
ROUTINE code_slot: INTEGER BEGIN tick=tick*10+4 RETURN 1 END code_slot"""
        state=run('tick=0 value=7 VAR_INFO(program_name(),variable_name(),flags[flag_slot()],label,codes[code_slot()],dims,length,status)',
                  decl='tick,value: INTEGER flags: ARRAY[1] OF BOOLEAN codes: ARRAY[1] OF INTEGER '+OUTPUTS,routines=routines)
        self.assertEqual((state['TICK'],state['FLAGS'],state['CODES']),(1234,[False],[16]))

    def test_selector_failure_retains_earlier_effects_and_outputs(self):
        p,_=compile_program("tick=0 label='old' VAR_INFO('','value',flags[slot()],label,code,dims,length,status)",
                            decl='tick,value: INTEGER flags: ARRAY[1] OF BOOLEAN '+OUTPUTS,
                            routines='ROUTINE slot: INTEGER BEGIN tick=tick+1 RETURN 2 END slot')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['TICK'],p.snapshot()['LABEL']),(1,'old'))

    def test_strict_queries_remain_blocked(self):
        text='PROGRAM T VAR value: INTEGER '+OUTPUTS+' BEGIN '+INFO+' END T'
        with self.assertRaises(TranslationError): legacy_translate(text)

    def test_internal_procedure_keeps_priority(self):
        state=run('VAR_INFO(7)',decl='n: INTEGER',routines='ROUTINE VAR_INFO(value: INTEGER) BEGIN n=value END VAR_INFO')
        self.assertEqual(state['N'],7)

    def test_transitive_for_output_is_rejected(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR n=1 TO 2 DO inspect(n) ENDFOR',decl='value,n: INTEGER '+OUTPUTS,
                            routines='ROUTINE inspect(result: INTEGER) BEGIN '+INFO.replace('code,dims','result,dims')+' END inspect')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_config_and_position_outputs_stay_protected(self):
        for output in ('cfg.cfg_turn_no1','pose.normal.x'):
            with self.subTest(output=output),self.assertRaises(TranslationError):
                compile_program(INFO.replace('code,dims',output+',dims'),decl='value: INTEGER cfg: CONFIG pose: POSITION '+OUTPUTS)

    def test_invalid_known_array_leaf_is_not_hidden_by_missing_first_leaf(self):
        p,_=compile_program("label='old' "+INFO,decl='value: ARRAY[2] OF INTEGER '+OUTPUTS)
        p._state.values['VALUE'].values[1]=True
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['LABEL'],'old')


class VariableListTests(unittest.TestCase):
    DECL='apple: INTEGER apricot: REAL berry: STRING[3] names: ARRAY[8] OF STRING[32] count,status: INTEGER'
    CALL="VAR_LIST('','a*',0,0,2,names,count,status)"

    def test_prefix_filter_is_case_insensitive_and_sorted(self):
        state=run(self.CALL,decl=self.DECL)
        self.assertEqual((state['NAMES'],state['COUNT'],state['STATUS']),(['APPLE','APRICOT']+['']*6,2,0))

    def test_scalar_type_filter(self):
        state=run(self.CALL.replace("'a*',0","'*',17"),decl=self.DECL)
        self.assertEqual((state['NAMES'][0],state['COUNT']),('APRICOT',1))

    def test_array_filter_uses_leaf_type(self):
        state=run(self.CALL.replace("'a*',0","'*',209"),decl=self.DECL)
        self.assertEqual(state['NAMES'][:2],['BERRY','NAMES'])

    def test_pagination_and_short_final_page(self):
        state=run(self.CALL.replace(',0,2,names',',1,2,names'),decl=self.DECL.replace('ARRAY[8]','ARRAY[1]'))
        self.assertEqual((state['NAMES'],state['COUNT']),(['APRICOT'],1))

    def test_skip_past_end_clears_names(self):
        state=run("names[1]='old' "+self.CALL.replace(',0,2,names',',99,2,names'),decl=self.DECL)
        self.assertEqual((state['NAMES'],state['COUNT']),(['']*8,0))

    def test_all_four_formats(self):
        for form,expected in ((1,'T'),(2,'APPLE'),(3,'[T]APPLE'),(4,'T'.ljust(15)+'APPLE'.ljust(12))):
            with self.subTest(form=form):
                state=run(self.CALL.replace("'a*'","'apple'").replace(',2,names',f',{form},names'),decl=self.DECL)
                self.assertEqual(state['NAMES'][0],expected)

    def test_unknown_program_preserves_array_and_count(self):
        state=run("names[1]='old' count=7 "+self.CALL.replace("'','a*'","'MISSING','*'"),decl=self.DECL)
        self.assertEqual((state['NAMES'][0],state['COUNT'],state['STATUS']),('old',7,1))

    def test_invalid_filter_skip_and_format_preserve_outputs(self):
        for old,new in (("'a*',0","'a*',999"),(',0,2,names',',-1,2,names'),(',2,names',',0,names'),("'a*'","'a?'")):
            with self.subTest(new=new):
                state=run("names[1]='old' count=7 "+self.CALL.replace(old,new),decl=self.DECL)
                self.assertEqual((state['NAMES'][0],state['COUNT'],state['STATUS']),('old',7,2))

    def test_capacity_error_is_atomic(self):
        state=run("names[1]='old' count=7 "+self.CALL,decl=self.DECL.replace('STRING[32]','STRING[3]'))
        self.assertEqual((state['NAMES'][0],state['COUNT'],state['STATUS']),('old',7,3))

    def test_no_matches_is_success(self):
        state=run(self.CALL.replace("'a*'","'z*'"),decl=self.DECL)
        self.assertEqual((state['NAMES'],state['COUNT'],state['STATUS']),(['']*8,0,0))

    def test_wildcard_programs_include_explicit_roots_and_attached_programs(self):
        ctx=rt.ExecutionContext();ctx.variables.define('LIB','ALPHA',('INTEGER',),7)
        ctx.variables.define('SYSTEM','$LIMIT',('INTEGER',),9)
        state=run(self.CALL.replace("'','a*'","'*','*'").replace(',2,names',',3,names'),decl=self.DECL,context=ctx)
        self.assertEqual(state['NAMES'][:3],['[LIB]ALPHA','[SYSTEM]$LIMIT','[T]APPLE'])

    def test_local_variables_are_excluded(self):
        state=run('inspect',decl=self.DECL,routines='ROUTINE inspect VAR aardvark: INTEGER BEGIN '+self.CALL+' END inspect')
        self.assertEqual((state['NAMES'][:2],state['COUNT']),(['APPLE','APRICOT'],2))

    def test_globals_include_output_names_without_reading_values(self):
        state=run(self.CALL.replace("'a*'","'*'"),decl=self.DECL)
        self.assertEqual(state['NAMES'][:6],['APPLE','APRICOT','BERRY','COUNT','NAMES','STATUS'])

    def test_listing_does_not_initialize_values(self):
        state=run(self.CALL,decl=self.DECL)
        self.assertEqual(state['APPLE'],{'uninitialized':True})

    def test_named_structure_filter(self):
        state=run(self.CALL.replace("'a*',0","'*',210"),decl=self.DECL+' packet: item_t',prefix='TYPE item_t=STRUCTURE id: INTEGER ENDSTRUCTURE')
        self.assertEqual((state['NAMES'][0],state['COUNT']),('PACKET',1))

    def test_overlap_rejected_before_listing(self):
        p,_=compile_program(self.CALL.replace('count,status','count,count'),decl=self.DECL)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()

    def test_linked_project_metadata(self):
        sources={'main':source('MAIN',"VAR_INFO('LIB','point',empty,label,code,dims,length,status)",decl=OUTPUTS),
                 'lib':source('LIB','',decl='point: VECTOR')}
        state=translate_project(sources).instantiate().run('MAIN')
        self.assertEqual((state['MAIN']['values']['LABEL'],state['MAIN']['values']['EMPTY']),('VECTOR',True))

    def test_service_records_are_value_free(self):
        p,result=compile_program(self.CALL,decl=self.DECL);p.run()
        self.assertEqual(p.service_requests,({'operation':'VAR_LIST','line':6,'outcome':'completed'},))
        self.assertEqual(result.report['service_operations'][0]['operation'],'VAR_LIST')
        self.assertFalse(result.report['variable_inspection_policy']['controller_validated'])

    def test_wrong_source_output_types_are_rejected(self):
        for text,declaration in ((INFO.replace('empty,label','code,label'),'value: INTEGER '+OUTPUTS),
                                 (self.CALL.replace('names,count','apple,count'),self.DECL)):
            with self.subTest(text=text),self.assertRaises(TranslationError) as caught: compile_program(text,decl=declaration)
            self.assertEqual(caught.exception.code,'E_TYPE')


    def test_list_input_functions_evaluate_once_in_order(self):
        routines="""ROUTINE program_name: STRING BEGIN tick=tick*10+1 RETURN '' END program_name
ROUTINE pattern: STRING BEGIN tick=tick*10+2 RETURN 'a*' END pattern
ROUTINE kind: INTEGER BEGIN tick=tick*10+3 RETURN 0 END kind"""
        state=run('tick=0 VAR_LIST(program_name(),pattern(),kind(),0,2,names,count,status)',decl='tick: INTEGER '+self.DECL,routines=routines)
        self.assertEqual((state['TICK'],state['COUNT']),(123,2))

    def test_fixed_format_needs_all_27_characters(self):
        state=run("names[1]='old' count=7 "+self.CALL.replace(',2,names',',4,names'),decl=self.DECL.replace('STRING[32]','STRING[26]'))
        self.assertEqual((state['NAMES'][0],state['COUNT'],state['STATUS']),('old',7,3))

    def test_fixed_format_rejects_overlong_identifier(self):
        state=run(self.CALL.replace("'a*'","'abcdefghijklmnop'").replace(',2,names',',4,names'),decl=self.DECL+' abcdefghijklmnop: INTEGER')
        self.assertEqual(state['STATUS'],3)

    def test_empty_attached_program_is_success(self):
        ctx=rt.ExecutionContext();empty,_=compile_program('',decl='',context=ctx)
        empty._state.program_name='EMPTY';empty._state.types={};ctx.variables.attach('EMPTY',empty._state)
        state=run(self.CALL.replace("'','a*'","'EMPTY','*'"),decl=self.DECL,context=ctx)
        self.assertEqual((state['COUNT'],state['STATUS']),(0,0))

    def test_path_alias_bindings_do_not_become_root_names(self):
        ctx=rt.ExecutionContext();ctx.variables.define('LIB','VALUE[1]',('INTEGER',),7)
        state=run(self.CALL.replace("'','a*'","'*','*'"),decl=self.DECL,context=ctx)
        self.assertEqual(state['COUNT'],6);self.assertNotIn('VALUE[1]',state['NAMES'])


if __name__=='__main__': unittest.main()
