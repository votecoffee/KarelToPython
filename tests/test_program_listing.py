"""Authored program catalog, paging and checked output integration cases."""
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from test_extended_services import compile_program,run
from test_project_scheduler import source


ENTRIES=[{'name':'weld','type':'TP'},{'name':'job','type':'JB'},
         {'name':'process','type':'PR'},{'name':'macro','type':'MR'},
         {'name':'stored','type':'VR'},{'name':'helper','type':'PC'}]
DECL='names: ARRAY[8] OF STRING[39] count,status,cursor_no: INTEGER'
CALL="PROG_LIST('*',7,0,1,names,count,status)"


def context(entries=ENTRIES): return rt.ExecutionContext(programs=rt.ProgramCatalog(entries))


class ProgramCatalogTests(unittest.TestCase):
    def test_empty_catalog(self):
        self.assertEqual(rt.ProgramCatalog().to_config(),[])

    def test_normalized_sorted_and_detached(self):
        entries=[dict(row) for row in ENTRIES];catalog=rt.ProgramCatalog(entries)
        entries[0]['name']='changed';saved=catalog.to_config();saved[0]['name']='changed'
        self.assertEqual(catalog.entries,tuple(sorted((row['name'].upper(),row['type']) for row in ENTRIES)))

    def test_all_kinds_accept_lowercase(self):
        self.assertEqual(rt.ProgramCatalog([{'name':'a','type':'pc'}]).entries,(('A','PC'),))

    def test_duplicate_identity_rejected_case_insensitively(self):
        with self.assertRaises(ValueError): rt.ProgramCatalog([{'name':'a','type':'PC'},{'name':'A','type':'pc'}])

    def test_same_name_different_types_retained(self):
        self.assertEqual(len(rt.ProgramCatalog([{'name':'a','type':'PC'},{'name':'a','type':'VR'}]).entries),2)

    def test_invalid_names(self):
        for name in ('','1bad','x.y','a*','a?','a-b','with space','é','a'*37,7,None):
            with self.subTest(name=name),self.assertRaises(ValueError): rt.ProgramCatalog([{'name':name,'type':'PC'}])

    def test_invalid_kinds_and_schema(self):
        for row in ({'name':'a','type':'KL'},{'name':'a','type':6},{'name':'a'},
                    {'name':'a','type':'PC','extra':1},('a','PC'),None):
            with self.subTest(row=row),self.assertRaises(ValueError): rt.ProgramCatalog([row])

    def test_context_requires_catalog(self):
        for value in ([],{},'PC'):
            with self.subTest(value=value),self.assertRaises(TypeError): rt.ExecutionContext(programs=value)

    def test_json_roundtrip(self):
        ctx=context();saved=json.loads(json.dumps(ctx.to_config()))
        self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
        self.assertEqual(saved['programs'],ctx.programs.to_config())

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'context.json';ctx=context();ctx.save(path)
            self.assertEqual(rt.ExecutionContext.load(path).programs.entries,ctx.programs.entries)

    def test_empty_and_absent_catalog_stay_distinct(self):
        self.assertNotIn('programs',rt.ExecutionContext().to_config())
        self.assertEqual(rt.ExecutionContext.from_config({'programs':[]}).to_config(),{'programs':[]})

    def test_bad_json_rejected(self):
        for value in ({},None,'PC',1,[{'name':'bad-name','type':'PC'}]):
            with self.subTest(value=value),self.assertRaises(ValueError): rt.ExecutionContext.from_config({'programs':value})


class ProgramListTests(unittest.TestCase):
    def test_current_program_without_adapter(self):
        state=run(CALL,decl=DECL)
        self.assertEqual((state['NAMES'],state['COUNT'],state['STATUS']),(['T']+['']*7,1,0))

    def test_all_types_are_sorted_and_merged(self):
        state=run(CALL,decl=DECL,context=context())
        self.assertEqual(state['NAMES'],['HELPER','JOB','MACRO','PROCESS','STORED','T','WELD',''])
        self.assertEqual(state['COUNT'],7)

    def test_type_filters(self):
        for kind,expected in ((1,['STORED']),(2,['JOB','MACRO','PROCESS','WELD']),
                              (3,['JOB']),(4,['PROCESS']),(5,['MACRO']),
                              (6,['HELPER','T']),(7,['HELPER','JOB','MACRO','PROCESS','STORED','T','WELD']),
                              (8,['HELPER','JOB','MACRO','PROCESS','T','WELD'])):
            with self.subTest(kind=kind):
                state=run(CALL.replace(',7,',f',{kind},'),decl=DECL,context=context())
                self.assertEqual(state['NAMES'],expected+['']*(8-len(expected)))
                self.assertEqual((state['COUNT'],state['STATUS']),(len(expected),0))

    def test_case_insensitive_star_patterns(self):
        state=run(CALL.replace("'*'","'*o*'"),decl=DECL,context=context())
        self.assertEqual(state['NAMES'][:4],['JOB','MACRO','PROCESS','STORED'])

    def test_exact_name_and_same_name_multiple_types(self):
        ctx=context([{'name':'shared','type':'PC'},{'name':'shared','type':'VR'}])
        state=run(CALL.replace("'*'","'shared'").replace(',1,names',',2,names'),decl=DECL,context=ctx)
        self.assertEqual(state['NAMES'][:2],['SHARED'.ljust(12)+' PC','SHARED'.ljust(12)+' VR'])

    def test_no_matches_succeeds_and_clears_output(self):
        state=run("names[1]='old' "+CALL.replace("'*'","'missing'"),decl=DECL)
        self.assertEqual((state['NAMES'],state['COUNT'],state['STATUS']),(['']*8,0,0))

    def test_skip_all_types(self):
        state=run(CALL.replace(',0,1,',',2,1,'),decl=DECL.replace('ARRAY[8]','ARRAY[2]'),context=context())
        self.assertEqual((state['NAMES'],state['COUNT']),(['MACRO','PROCESS'],2))

    def test_skip_beyond_end(self):
        state=run(CALL.replace(',0,1,',',99,1,'),decl=DECL,context=context())
        self.assertEqual((state['NAMES'],state['COUNT'],state['STATUS']),(['']*8,0,0))

    def test_cursor_pages_filtered_results(self):
        call="PROG_LIST('*o*',7,0,1,names,count,status,cursor_no)"
        body='cursor_no=0 '+call+' first=names[1] '+call+' second=names[1] '+call
        state=run(body,decl=DECL.replace('ARRAY[8]','ARRAY[2]')+' first,second: STRING[39]',context=context())
        self.assertEqual((state['FIRST'],state['SECOND'],state['NAMES'],state['COUNT'],state['CURSOR_NO']),('JOB','PROCESS',['',''],0,4))

    def test_cursor_and_skip_use_offset_in_remaining_rows(self):
        state=run('cursor_no=1 '+CALL.replace(',0,1,',',2,1,')[:-1]+',cursor_no)',decl=DECL.replace('ARRAY[8]','ARRAY[2]'),context=context())
        self.assertEqual((state['NAMES'],state['CURSOR_NO']),(['PROCESS','STORED'],3))

    def test_cursor_beyond_end_does_not_rewind(self):
        state=run('cursor_no=99 '+CALL[:-1]+',cursor_no)',decl=DECL)
        self.assertEqual((state['NAMES'],state['COUNT'],state['CURSOR_NO']),(['']*8,0,99))

    def test_uninitialized_cursor_raises_without_other_writes(self):
        program,_=compile_program("names[1]='old' count=9 status=8 "+CALL[:-1]+',cursor_no)',decl=DECL)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual((program.snapshot()['NAMES'][0],program.snapshot()['COUNT'],program.snapshot()['STATUS']),('old',9,8))

    def test_invalid_options_preserve_outputs_and_cursor(self):
        for old,new in (("'*'","''"),("'*'","'a?'"),("'*'","'[A]'"),(',7,',',0,'),(',7,',',9,'),
                        (',0,1,',',-1,1,'),(',0,1,',',0,3,')):
            with self.subTest(new=new):
                state=run("names[1]='old' count=9 cursor_no=0 "+CALL.replace(old,new)[:-1]+',cursor_no)',decl=DECL)
                self.assertEqual((state['NAMES'][0],state['COUNT'],state['CURSOR_NO'],state['STATUS']),('old',9,0,2))

    def test_negative_cursor_is_status_failure(self):
        state=run('cursor_no=-1 count=9 '+CALL[:-1]+',cursor_no)',decl=DECL)
        self.assertEqual((state['COUNT'],state['CURSOR_NO'],state['STATUS']),(9,-1,2))

    def test_skip_restricted_to_all_program_query(self):
        for call in (CALL.replace(',0,1,',',1,1,').replace(',7,',',6,'),CALL.replace(',0,1,',',1,1,').replace("'*'","'T'")):
            with self.subTest(call=call): self.assertEqual(run(call,decl=DECL)['STATUS'],2)

    def test_format_two_short_names(self):
        state=run(CALL.replace(',1,names',',2,names'),decl=DECL)
        self.assertEqual(state['NAMES'][0],'T'.ljust(12)+' PC')

    def test_format_two_long_names(self):
        name='abcdefghijklmnop';state=run(CALL.replace("'*'",repr(name)).replace(',1,names',',2,names'),decl=DECL,context=context([{'name':name,'type':'JB'}]))
        self.assertEqual(state['NAMES'][0],name.upper().ljust(36)+' JB')

    def test_capacity_failure_is_atomic_for_entire_page(self):
        state=run("names[1]='old' count=9 cursor_no=0 "+CALL.replace(',1,names',',2,names')[:-1]+',cursor_no)',decl=DECL.replace('STRING[39]','STRING[14]'),context=context())
        self.assertEqual((state['NAMES'][0],state['COUNT'],state['CURSOR_NO'],state['STATUS']),('old',9,0,3))

    def test_later_long_name_does_not_partially_write_page(self):
        ctx=context([{'name':'A','type':'PC'},{'name':'longer_than_twelve','type':'TP'}])
        state=run("names[1]='old' count=9 "+CALL.replace(',1,names',',2,names'),decl=DECL.replace('STRING[39]','STRING[15]'),context=ctx)
        self.assertEqual((state['NAMES'][0],state['COUNT'],state['STATUS']),('old',9,3))

    def test_format_one_does_not_truncate(self):
        state=run('count=9 '+CALL,decl=DECL.replace('STRING[39]','STRING[3]'),context=context())
        self.assertEqual((state['COUNT'],state['STATUS']),(9,3))

    def test_success_clears_entire_remainder(self):
        state=run("names[1]='old' names[8]='old' "+CALL,decl=DECL)
        self.assertEqual(state['NAMES'],['T']+['']*7)

    def test_explicit_and_attached_duplicates_collapse(self):
        state=run(CALL,decl=DECL,context=context([{'name':'T','type':'PC'}]))
        self.assertEqual(state['COUNT'],1)

    def test_bindings_files_and_externals_are_not_programs(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'NOT_LOADED.PC':'data'}),externals={('OTHER','ROUTINE'):lambda:None})
        ctx.variables.define('VARIABLES','VALUE',('INTEGER',),7)
        self.assertEqual(run(CALL,decl=DECL,context=ctx)['NAMES'],['T']+['']*7)

    def test_metadata_does_not_create_variables_or_tasks(self):
        ctx=context();state=run(CALL,decl=DECL,context=ctx)
        self.assertEqual(state['COUNT'],7)
        self.assertEqual(ctx.tasks.tasks,{})
        self.assertEqual(set(ctx.variables.programs),{'T'})
        self.assertEqual(ctx.variables.bindings,{})

    def test_linked_project_lists_unstarted_library(self):
        result=translate_project({'main':source('MAIN',CALL,decl=DECL),'lib':source('LIB','',decl='value: INTEGER')})
        snapshot=result.instantiate().run('MAIN')
        self.assertEqual(snapshot['MAIN']['values']['NAMES'],['LIB','MAIN']+['']*6)

    def test_task_alias_is_not_program_name(self):
        ctx=rt.ExecutionContext();other,_=compile_program('',cooperative=True)
        other._state.program_name='WORKER';ctx.tasks.bind('TASK_ALIAS',other)
        state=run(CALL,decl=DECL,context=ctx)
        self.assertEqual(state['NAMES'],['T','WORKER']+['']*6)

    def test_cursor_reference_may_be_selected_storage(self):
        state=run('indexes[2]=0 '+CALL[:-1]+',indexes[2])',decl=DECL+' indexes: ARRAY[2] OF INTEGER')
        self.assertEqual(state['INDEXES'],[{'uninitialized':True},1])

    def test_output_aliases_rejected_before_query(self):
        for call in (CALL.replace('count,status','count,count'),CALL[:-1]+',count)'):
            with self.subTest(call=call):
                program,_=compile_program('count=0 '+call,decl=DECL)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): program.run()
                self.assertEqual(program.snapshot()['COUNT'],0)

    def test_wrong_source_types_and_cursor_values_rejected(self):
        for call in (CALL.replace('names,count','count,count'),CALL[:-1]+',0)',CALL[:-1]+',names)',CALL.replace(',7,',",'PC',")):
            with self.subTest(call=call),self.assertRaises(TranslationError): compile_program(call,decl=DECL)

    def test_wrong_arity_rejected(self):
        for call in ("PROG_LIST('*',7,0,1,names,count)",CALL[:-1]+',cursor_no,cursor_no)'):
            with self.subTest(call=call),self.assertRaises(TranslationError) as caught: compile_program(call,decl=DECL)
            self.assertEqual(caught.exception.code,'E_ARGUMENTS')

    def test_active_for_counter_cannot_be_cursor(self):
        with self.assertRaises(TranslationError) as caught: compile_program('FOR cursor_no=1 TO 2 DO '+CALL[:-1]+',cursor_no) ENDFOR',decl=DECL)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_all_inputs_and_output_selectors_capture_once_in_order(self):
        routines="""ROUTINE pattern: STRING BEGIN tick=tick*10+1 RETURN '*' END pattern
ROUTINE kind: INTEGER BEGIN tick=tick*10+2 RETURN 7 END kind
ROUTINE skipped: INTEGER BEGIN tick=tick*10+3 RETURN 0 END skipped
ROUTINE form: INTEGER BEGIN tick=tick*10+4 RETURN 1 END form
ROUTINE selected: INTEGER BEGIN tick=tick*10+5 RETURN 1 END selected"""
        state=run('tick=0 indexes[1]=0 PROG_LIST(pattern(),kind(),skipped(),form(),names,count,status,indexes[selected()])',
                  decl=DECL+' tick: INTEGER indexes: ARRAY[2] OF INTEGER',routines=routines)
        self.assertEqual((state['TICK'],state['COUNT'],state['INDEXES'][0]),(12345,1,1))

    def test_input_is_captured_before_same_storage_output(self):
        state=run("names[1]='*' PROG_LIST(names[1],7,0,1,names,count,status)",decl=DECL)
        self.assertEqual((state['COUNT'],state['NAMES'][0]),(1,'T'))

    def test_service_reports_and_records_contain_no_names(self):
        program,result=compile_program(CALL,decl=DECL);program.run()
        self.assertEqual(program.service_requests,({'operation':'PROG_LIST','line':6,'outcome':'completed'},))
        self.assertEqual(result.report['service_operations'][0]['operation'],'PROG_LIST')
        self.assertFalse(result.report['program_listing_policy']['controller_validated'])

    def test_routine_output_effects_include_cursor(self):
        routines='ROUTINE list_programs(cursor: INTEGER) BEGIN '+CALL[:-1]+',cursor) END list_programs'
        program,result=compile_program('cursor_no=0 list_programs(cursor_no)',decl=DECL,routines=routines)
        program.run();self.assertEqual(program.snapshot()['CURSOR_NO'],1)
        self.assertTrue(result.report['routine_effects']['LIST_PROGRAMS']['potential_service_requests'])

    def test_roundtrip_keeps_catalog_without_serializing_tasks(self):
        ctx=context();run(CALL,decl=DECL,context=ctx)
        restored=rt.ExecutionContext.from_config(ctx.to_config())
        self.assertEqual(run(CALL,decl=DECL,context=restored)['NAMES'],['HELPER','JOB','MACRO','PROCESS','STORED','T','WELD',''])


if __name__=='__main__': unittest.main()
