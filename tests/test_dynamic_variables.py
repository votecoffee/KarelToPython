"""Authored dynamic variable lifecycle and typed routine alias regressions."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


DECL='e,n,s,prior: INTEGER text: STRING[32]'
CREATE="CREATE_VAR('','item','','INTEGER',0,0,0,0,s)"
CHANGE='ROUTINE change(x: INTEGER) BEGIN x=x+2 END change'


class DynamicCreationTests(unittest.TestCase):
    def test_scalar_create_set_get_and_default_namespace(self):
        p,_=compile_program(CREATE+" SET_VAR(e,'','item',7,s) GET_VAR(e,'','ITEM',n,s)",decl=DECL)
        self.assertEqual(p.run()['N'],7)
        self.assertEqual(p._state.execution.variables.metadata['T','ITEM'],{'group':0,'memory_pool':0})

    def test_created_value_starts_uninitialized(self):
        data=run(CREATE+" n=99 GET_VAR(e,'','item',n,s)",decl=DECL)
        self.assertEqual((data['N'],data['S']),({'uninitialized':True},12311))

    def test_collision_preserves_declared_value(self):
        self.assertEqual(run("n=9 CREATE_VAR('','n','','INTEGER',0,0,0,0,s)",decl=DECL)['N'],9)
        self.assertEqual(run("CREATE_VAR('','n','','INTEGER',0,0,0,0,s)",decl=DECL)['S'],3)

    def test_duplicate_preserves_dynamic_value(self):
        data=run(CREATE+" SET_VAR(e,'','item',8,s) "+CREATE+" prior=s GET_VAR(e,'','item',n,s)",decl=DECL)
        self.assertEqual((data['PRIOR'],data['N']),(3,8))

    def test_multidimensional_arrays_use_outer_to_inner_order(self):
        p,_=compile_program("CREATE_VAR('CACHE','data','','INTEGER',0,4,3,2,s) SET_VAR(e,'cache','data[2,3,4]',19,s) GET_VAR(e,'CACHE','DATA[2,3,4]',n,s)",decl=DECL)
        self.assertEqual(p.run()['N'],19)
        self.assertEqual(p._state.execution.variables.bindings['CACHE','DATA'].spec,('ARRAY',(2,3,4),('INTEGER',)))

    def test_byte_short_arrays_and_string_capacity(self):
        for kind,value in (('ARRAY OF BYTE',255),('ARRAY OF SHORT',32766)):
            p,_=compile_program(f"CREATE_VAR('','item','','{kind}',0,2,0,0,s) SET_VAR(e,'','item[2]',{value},s)",decl=DECL)
            self.assertEqual(p.run()['S'],0)
            self.assertEqual(p._state.execution.variables.bindings['T','ITEM'].raw().values[1],value)
        p,_=compile_program("CREATE_VAR('','item','','STRING',0,0,0,0,s) SET_VAR(e,'','item','abcdefghijklmnop',s) GET_VAR(e,'','item',text,s)",decl=DECL)
        self.assertEqual(p.run()['TEXT'],'abcdefghijkl')

    def test_supported_records_and_joint_widths(self):
        for kind in ('BOOLEAN','REAL','STRING[4]','CONFIG','VECTOR','POSITION','XYZWPR','XYZWPREXT','JOINTPOS','JOINTPOS1','JOINTPOS9'):
            p,_=compile_program(f"CREATE_VAR('','item','','{kind}',2,0,0,0,s)",decl=DECL)
            self.assertEqual(p.run()['S'],0,kind)
            value=p._state.execution.variables.bindings['T','ITEM'].raw()
            if kind=='JOINTPOS1': self.assertEqual(len(value.values),1)

    def test_user_structure_and_nested_paths(self):
        p,_=compile_program("CREATE_VAR('','item','','packet',0,0,0,0,s) SET_VAR(e,'','item.id',13,s) GET_VAR(e,'','item.id',n,s)",
            decl=DECL,prefix='TYPE packet=STRUCTURE id: INTEGER text: STRING[4] ENDSTRUCTURE')
        self.assertEqual(p.run()['N'],13)

    def test_foreign_user_type_and_named_array_identity(self):
        instance=translate_project({'lib':'PROGRAM LIB TYPE series=ARRAY[2] OF INTEGER VAR n:INTEGER BEGIN END LIB',
            'main':source('MAIN',"CREATE_VAR('CACHE','a','LIB','series',0,0,0,0,s)")}).instantiate()
        instance.run('MAIN');self.assertEqual(instance.programs['MAIN'].snapshot()['S'],0)
        self.assertEqual(instance.context.variables.bindings['CACHE','A'].spec[-1],'SERIES')

    def test_invalid_options_never_allocate(self):
        cases=[('bad.name','INTEGER',0,0,0,0,0,2),('item','FILE',0,0,0,0,0,5),
            ('item','CAM_SETUP',0,0,0,0,0,5),('item','UNKNOWN_TYPE',0,0,0,0,0,5),
            ('item','INTEGER',0,0,1,0,0,5),('item','INTEGER',0,1,0,1,0,5),
            ('item','INTEGER',0,-1,0,0,0,5),('item','INTEGER',0,32767,2,0,0,5),
            ('item','STRING[0]',0,0,0,0,0,5),('item','STRING[255]',0,0,0,0,0,5),
            ('item','POSITION',0,0,0,0,0,5),('item','INTEGER',33,0,0,0,0,5),
            ('item','INTEGER',0,0,0,0,1,2)]
        for var,kind,group,inner,middle,outer,pool,code in cases:
            ctx=rt.ExecutionContext()
            data=run(f"CREATE_VAR('','{var}','','{kind}',{group},{inner},{middle},{outer},s,{pool})",context=ctx)
            self.assertEqual(data['S'],code,(var,kind));self.assertEqual(ctx.variables.bindings,{})

    def test_aggregate_creation_budget_rejects_before_allocation(self):
        ctx=rt.ExecutionContext()
        data=run("CREATE_VAR('','a','','INTEGER',0,32767,0,0,s) CREATE_VAR('','b','','REAL',0,0,0,0,s)",context=ctx)
        self.assertEqual(data['S'],6);self.assertEqual(set(ctx.variables.bindings),{('T','A')})

    def test_budget_failure_preserves_bank_and_status(self):
        p,_=compile_program('s=77 '+CREATE)
        original=p._state.tick
        def tick(line=None):
            if any(row['operation']=='CREATE_VAR' for row in p._state.service_requests): raise rt.KarelRuntimeError('Authored budget exhaustion')
            return original(line)
        with patch.object(p._state,'tick',side_effect=tick),self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],77);self.assertEqual(p._state.execution.variables.bindings,{})


class DynamicRenameTests(unittest.TestCase):
    def test_rename_preserves_value_identity_metadata_and_cache(self):
        p,_=compile_program(CREATE+" SET_VAR(e,'','item',9,s) prior=e RENAME_VAR('','item','renamed',s) GET_VAR(e,'','renamed',n,s)",decl=DECL)
        data=p.run();ctx=p._state.execution
        self.assertEqual((data['N'],data['E']),(9,data['PRIOR']))
        self.assertNotIn(('T','ITEM'),ctx.variables.bindings);self.assertIn(('T','RENAMED'),ctx.variables.metadata)
        self.assertNotIn(('','ITEM'),ctx.entries)

    def test_nested_bindings_follow_root_rename(self):
        store=rt.VariableStore();value=rt.Structure(('VECTOR',));value.values.update(X=1.,Y=2.,Z=3.)
        record=store.define('CACHE','ITEM',('VECTOR',),value)
        store.bind('CACHE','ITEM.X',rt.field_reference(record.raw(),'X'))
        data=run("RENAME_VAR('cache','item','moved',s) GET_VAR(e,'cache','moved.x',x,s)",decl='e,s: INTEGER x: REAL',context=rt.ExecutionContext(variables=store))
        self.assertEqual(data['X'],1.);self.assertIn(('CACHE','MOVED.X'),store.bindings)

    def test_namespace_rename_preserves_all_references(self):
        store=rt.VariableStore();ref=store.define('OLD','ITEM',('INTEGER',),8)
        data=run("RENAME_VARS('old','new',s) GET_VAR(e,'new','item',n,s)",decl=DECL,context=rt.ExecutionContext(variables=store))
        self.assertEqual(data['N'],8);self.assertIs(store.bindings['NEW','ITEM'],ref)

    def test_missing_collision_invalid_and_compiled_guards(self):
        for call,code in (("RENAME_VAR('','absent','next',s)",1),("RENAME_VAR('','n','next',s)",4),
                ("RENAME_VAR('','item','n',s)",3),("RENAME_VAR('','item','bad.name',s)",2),
                ("RENAME_VARS('T','NEW',s)",4),("RENAME_VARS('ABSENT','NEW',s)",1),
                ("RENAME_VARS('CACHE','T',s)",3),("RENAME_VARS('CACHE','TAKEN',s)",3)):
            ctx=rt.ExecutionContext();ctx.variables.define('CACHE','A',('INTEGER',),1);ctx.variables.define('TAKEN','A',('INTEGER',),2)
            data=run(CREATE+' '+call,context=ctx);self.assertEqual(data['S'],code,call)
            self.assertEqual(ctx.variables.bindings['CACHE','A'].raw(),1)

    def test_same_name_operations_are_idempotent(self):
        data=run(CREATE+" RENAME_VAR('','item','ITEM',s) prior=s CREATE_VAR('CACHE','item','','INTEGER',0,0,0,0,s) RENAME_VARS('CACHE','CACHE',s)",decl=DECL)
        self.assertEqual((data['S'],data['PRIOR']),(0,0))

    def test_namespace_with_system_or_partial_bindings_is_protected(self):
        for path in ('$SYS','A[1]'):
            store=rt.VariableStore();store.define('CACHE',path,('INTEGER',),1)
            self.assertEqual(run("RENAME_VARS('CACHE','NEW',s)",context=rt.ExecutionContext(variables=store))['S'],4)
            self.assertIn(('CACHE',path),store.bindings)

    def test_var_info_and_list_follow_new_names(self):
        data=run(CREATE+" RENAME_VAR('','item','renamed',s) VAR_INFO('','renamed',empty,text,n,dims,e,s) VAR_LIST('T','RE*',0,0,2,names,prior,s)",
            decl=DECL+' empty:BOOLEAN dims:ARRAY[3] OF INTEGER names:ARRAY[2] OF STRING[36]')
        self.assertEqual((data['EMPTY'],data['TEXT'],data['N'],data['PRIOR'],data['NAMES']),(True,'INTEGER',16,1,['RENAMED','']))


class ByNameTests(unittest.TestCase):
    def test_bare_global_alias_mutates_original(self):
        data=run("n=4 change(BYNAME('','n',e))",decl=DECL,routines=CHANGE)
        self.assertEqual(data['N'],6);self.assertGreater(data['E'],0)

    def test_dynamic_alias_and_foreign_namespace(self):
        data=run("CREATE_VAR('CACHE','item','','INTEGER',0,0,0,0,s) SET_VAR(e,'CACHE','item',7,s) change(BYNAME('CACHE','item',e)) GET_VAR(e,'CACHE','item',n,s)",decl=DECL,routines=CHANGE)
        self.assertEqual(data['N'],9)

    def test_uninitialized_alias_can_be_initialized_by_routine(self):
        data=run("put(BYNAME('','n',e))",decl=DECL,routines='ROUTINE put(x:INTEGER) BEGIN x=12 END put')
        self.assertEqual(data['N'],12)

    def test_nested_fields_and_array_elements(self):
        data=run("a[2]=4 change(BYNAME('','a[2]',e)) n=a[2]",decl=DECL+' a:ARRAY[2] OF INTEGER',routines=CHANGE)
        self.assertEqual(data['N'],6)

    def test_array_formals_keep_shape_and_alias(self):
        data=run("a[2]=5 put(BYNAME('','a',e)) n=a[2]",decl=DECL+' a:ARRAY[2] OF INTEGER',
            routines='ROUTINE put(x:ARRAY OF INTEGER) BEGIN x[2]=x[2]+1 END put')
        self.assertEqual(data['N'],6)

    def test_string_formals_inherit_capacity(self):
        data=run("text='abc' put(BYNAME('','text',e))",decl=DECL,routines="ROUTINE put(x:STRING) BEGIN x=x+'d' END put")
        self.assertEqual(data['TEXT'],'abcd')

    def test_resolution_errors_preserve_entry_and_routine_side_effects(self):
        for path in ('absent','text','$SYSTEM','n[1]'):
            p,_=compile_program(f"e=77 n=8 change(BYNAME('','{path}',e))",decl=DECL,routines=CHANGE)
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['E'],p.snapshot()['N']),(77,8),path)
            self.assertEqual(p.service_requests[-1]['outcome'],'failed')

    def test_entry_overlap_rejects_before_mutation(self):
        p,_=compile_program("n=7 change(BYNAME('','n',n))",decl=DECL,routines=CHANGE)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['N'],7)

    def test_readonly_position_and_config_fields_are_not_aliases(self):
        for path,kind in (('p.orient.x','REAL'),('cfg.cfg_turn_no1','INTEGER')):
            p,_=compile_program(f"e=77 put(BYNAME('','{path}',e))",decl=DECL+' p:POSITION cfg:CONFIG',
                routines=f'ROUTINE put(x:{kind}) BEGIN END put')
            with self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['E'],77)

    def test_only_immediate_user_routine_argument_is_supported(self):
        for body in ("n=BYNAME('','n',e)","WRITE(BYNAME('','n',e))","change((BYNAME('','n',e)))","n=ABS(BYNAME('','n',e))"):
            with self.assertRaises(TranslationError) as caught:compile_program(body,decl=DECL,routines=CHANGE)
            self.assertEqual(caught.exception.code,'E_BYNAME_CONTEXT',body)

    def test_arity_and_entry_guards_and_user_override(self):
        for body in ("change(BYNAME('','n'))","change(BYNAME('','n',0))","change(BYNAME('','n',text))"):
            with self.assertRaises(TranslationError):compile_program(body,decl=DECL,routines=CHANGE)
        self.assertEqual(run('n=BYNAME(4)',routines='ROUTINE BYNAME(x:INTEGER):INTEGER BEGIN RETURN x+1 END BYNAME')['N'],5)

    def test_all_indirect_operations_retain_for_counter_guards(self):
        for body in (CREATE,"RENAME_VAR('','item','renamed',s)","RENAME_VARS('OLD','NEW',s)","change(BYNAME('','n',e))"):
            with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+body+' ENDFOR',decl=DECL,routines=CHANGE)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER',body)
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR n=1 TO 2 DO hidden ENDFOR',decl=DECL,
                routines=CHANGE+" ROUTINE hidden BEGIN change(BYNAME('','n',e)) END hidden")
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_linked_external_routine_receives_real_alias(self):
        instance=translate_project({'lib':source('LIB','',routines=CHANGE),
            'main':source('MAIN',"n=5 change(BYNAME('','n',e))",decl=DECL,routines='ROUTINE change(x:INTEGER) FROM LIB')}).instantiate()
        instance.run('MAIN');self.assertEqual(instance.programs['MAIN'].snapshot()['N'],7)

    def test_alias_survives_pause_and_rename_in_routine(self):
        p,_=compile_program(CREATE+" SET_VAR(e,'','item',5,s) change(BYNAME('','item',e)) GET_VAR(e,'','renamed',n,s)",decl=DECL,cooperative=True,
            routines="ROUTINE change(x:INTEGER) BEGIN RENAME_VAR('','item','renamed',s) PAUSE x=x+1 END change")
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.task_state,'paused')
        p.resume();self.assertEqual(p.snapshot()['N'],6)

    def test_blank_program_inside_linked_routine_uses_calling_root(self):
        instance=translate_project({'lib':source('LIB', '',routines=CHANGE+" ROUTINE probe BEGIN change(BYNAME('','n',s)) END probe"),
            'main':source('MAIN','n=5 probe',routines='ROUTINE probe FROM LIB')}).instantiate()
        instance.run('MAIN');self.assertEqual(instance.programs['MAIN'].snapshot()['N'],7)
        self.assertEqual(instance.programs['LIB'].snapshot()['N'],{'uninitialized':True})

    def test_name_and_entry_selectors_evaluate_once_in_source_order(self):
        routines=CHANGE+"""
ROUTINE owner:STRING BEGIN prior=prior*10+1 RETURN '' END owner
ROUTINE pathname:STRING BEGIN prior=prior*10+2 RETURN 'n' END pathname
ROUTINE slot:INTEGER BEGIN prior=prior*10+3 RETURN 1 END slot
"""
        data=run('prior=0 n=5 change(BYNAME(owner,pathname,cache[slot]))',decl=DECL+' cache:ARRAY[1] OF INTEGER',routines=routines)
        self.assertEqual((data['PRIOR'],data['N']),(123,7))

    def test_exact_named_structure_parameter_keeps_identity(self):
        data=run("record.id=5 put(BYNAME('','record',e)) n=record.id",decl=DECL+' record:packet',
            prefix='TYPE packet=STRUCTURE id:INTEGER ENDSTRUCTURE',routines='ROUTINE put(x:packet) BEGIN x.id=x.id+1 END put')
        self.assertEqual(data['N'],6)

    def test_named_array_mismatch_does_not_publish_entry(self):
        p,_=compile_program("e=77 put(BYNAME('','a',e))",decl=DECL+' a:first',
            prefix='TYPE first=ARRAY[2] OF INTEGER second=ARRAY[2] OF INTEGER',routines='ROUTINE put(x:second) BEGIN END put')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type'):p.run()
        self.assertEqual(p.snapshot()['E'],77)

    def test_report_records_all_four_operations(self):
        _,result=compile_program(CREATE+" change(BYNAME('','item',e)) RENAME_VAR('','item','next',s) RENAME_VARS('CACHE','SAVED',s)",decl=DECL,routines=CHANGE)
        policy=result.report['dynamic_variable_policy']
        self.assertEqual([row['operation'] for row in policy['calls']],['CREATE_VAR','BYNAME','RENAME_VAR','RENAME_VARS'])
        self.assertFalse(policy['controller_validated'])


class DynamicPersistenceTests(unittest.TestCase):
    def test_json_roundtrip_preserves_partial_arrays_and_creation_policy(self):
        p,_=compile_program("CREATE_VAR('CACHE','item','','INTEGER',0,2,0,0,s,-1) SET_VAR(e,'CACHE','item[2]',8,s) RENAME_VARS('CACHE','SAVED',s)",decl=DECL)
        p.run();config=json.loads(json.dumps(p._state.execution.to_config()))
        ctx=rt.ExecutionContext.from_config(config)
        self.assertEqual(ctx.to_config(),config)
        self.assertEqual(ctx.variables.metadata['SAVED','ITEM'],{'group':0,'memory_pool':-1})
        self.assertEqual(run("GET_VAR(e,'SAVED','item[2]',n,s)",decl=DECL,context=ctx)['N'],8)

    def test_invalid_saved_metadata_rejects(self):
        base={'program':'CACHE','path':'ITEM','type':['INTEGER'],'value':1,'creation':{'group':0,'memory_pool':0}}
        for metadata in ({'group':True,'memory_pool':0},{'group':33,'memory_pool':0},{'group':0,'memory_pool':1},{'group':0},{'group':0,'memory_pool':0,'extra':1}):
            row=deepcopy(base);row['creation']=metadata
            with self.assertRaises(ValueError):rt.ExecutionContext.from_config({'variables':[row]})

    def test_saved_creation_limit_checked_before_array_allocation(self):
        row={'program':'CACHE','path':'ITEM','type':['ARRAY',32767,['ARRAY',32767,['INTEGER']]],'value':[],
            'creation':{'group':0,'memory_pool':0}}
        with patch.object(rt,'Array',side_effect=AssertionError('Allocated before validation')):
            with self.assertRaises(ValueError):rt.ExecutionContext.from_config({'variables':[row]})

    def test_duplicate_saved_bindings_reject_including_folded_names(self):
        row={'program':'CACHE','path':'ITEM','type':['INTEGER'],'value':1}
        other={**row,'program':'cache'}
        with self.assertRaisesRegex(ValueError,'Duplicate'):rt.ExecutionContext.from_config({'variables':[row,other]})


if __name__=='__main__':unittest.main()
