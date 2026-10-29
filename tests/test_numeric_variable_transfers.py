"""Checked numeric scalar/ARRAY GET_VAR and SET_VAR prefix conversions."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt,translate_project
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_variable_transfers import transfer,MISSING,BYTE


BASE='e,s,old:INTEGER'
TYPES=('INTEGER','BYTE','SHORT','REAL')


def build(body,decl,**options):return compile_program(body,decl=BASE+' '+decl,**options)


class NumericVariableTransferTests(unittest.TestCase):
    def test_get_and_set_promote_all_integral_scalar_sources(self):
        for action in ('GET_VAR','SET_VAR'):
            for kind in TYPES[:-1]:
                call=transfer(action,'A','b') if action=='GET_VAR' else transfer(action,'B','a')
                p,_=build('a=7 '+call,f'a:{kind} b:REAL')
                with self.subTest(action=action,kind=kind):self.assertEqual((p.run()['B'],p.snapshot()['S']),(7.,0))

    def test_every_integral_scalar_pair_is_checked_in_both_directions(self):
        for source_type in TYPES[:-1]:
            for target_type in TYPES[:-1]:
                for action in ('GET_VAR','SET_VAR'):
                    call=transfer(action,'A','b') if action=='GET_VAR' else transfer(action,'B','a')
                    p,_=build('a=7 '+call,f'a:{source_type} b:{target_type}')
                    with self.subTest(source=source_type,target=target_type,action=action):self.assertEqual((p.run()['B'],p.snapshot()['S']),(7,0))

    def test_array_promotion_converts_prefix_and_preserves_tail(self):
        for action in ('GET_VAR','SET_VAR'):
            call=transfer(action,'A','b') if action=='GET_VAR' else transfer(action,'B','a')
            p,_=build('a[1]=7 a[2]=-2 b[3]=9 '+call,'a:ARRAY[2] OF INTEGER b:ARRAY[3] OF REAL')
            with self.subTest(action=action):self.assertEqual((p.run()['B'],p.snapshot()['S']),([7.,-2.,9.],0))

    def test_matrix_reshape_prefix_keeps_same_rank(self):
        p,_=build('a[1,1]=1 a[1,2]=2 a[2,1]=3 a[2,2]=4 b[2,2]=8 b[2,3]=9 '+transfer(),
                  'a:ARRAY[2,2] OF INTEGER b:ARRAY[2,3] OF REAL')
        self.assertEqual(p.run()['B'],[[1.,2.,3.],[4.,8.,9.]])

    def test_named_nested_array_to_flat_matrix_promotes_leaves(self):
        p,_=build('a[1][1]=1 a[1][2]=2 '+transfer(),'a:ARRAY[1] OF row_t b:ARRAY[1,3] OF REAL',
                  prefix='TYPE row_t=ARRAY[2] OF SHORT')
        state=p.run();self.assertEqual((state['B'],state['S']),([[1.,2.,MISSING]],0))

    def test_three_dimensional_numeric_prefix(self):
        p,_=build('a[1,1,1]=1 a[1,1,2]=2 '+transfer(),'a:ARRAY[1,1,2] OF BYTE b:ARRAY[1,1,3] OF REAL')
        self.assertEqual(p.run()['B'],[[[1.,2.,MISSING]]])

    def test_late_narrow_overflow_preserves_data_entry_and_status(self):
        for action in ('GET_VAR','SET_VAR'):
            call=transfer(action,'A','b') if action=='GET_VAR' else transfer(action,'B','a')
            p,_=build('e=99 s=77 a[1]=7 a[2]=256 b[1]=8 b[2]=9 '+call,'a:ARRAY[2] OF INTEGER b:ARRAY[2] OF BYTE')
            with self.subTest(action=action),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),([8,9],99,77));self.assertFalse(p._state.execution.entries)

    def test_negative_integer_to_byte_rejects_without_mutation(self):
        p,_=build('e=99 s=77 a=-1 b=8 '+transfer(),'a:INTEGER b:BYTE')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(8,99,77))

    def test_invalid_declared_source_domain_is_checked_before_widening(self):
        for kind,value in (('BYTE',256),('SHORT',-32769),('INTEGER',2147483647)):
            p,_=build('e=99 s=77 b=8 '+transfer(),f'a:{kind} b:REAL');p._state.values['A']=value
            with self.subTest(kind=kind),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),(8.,99,77))

    def test_real_to_integral_remains_incompatible_without_rounding(self):
        for target in TYPES[:-1]:
            for array in (False,True):
                decl=f'a:REAL b:{target}' if not array else f'a:ARRAY[1] OF REAL b:ARRAY[1] OF {target}'
                setup='a=7.0 b=9' if not array else 'a[1]=7.0 b[1]=9'
                p,_=build('e=99 '+setup+' '+transfer(),decl)
                with self.subTest(target=target,array=array):self.assertEqual((p.run()['S'],p.snapshot()['E'],p.snapshot()['B']),(3,99,[9] if array else 9))

    def test_boolean_never_enters_numeric_conversions(self):
        for source_type,target_type in (('BOOLEAN','INTEGER'),('INTEGER','BOOLEAN'),('BOOLEAN','REAL')):
            p,_=build('e=99 '+transfer(),f'a:{source_type} b:{target_type}')
            with self.subTest(source=source_type,target=target_type):self.assertEqual((p.run()['S'],p.snapshot()['E']),(3,99))

    def test_rank_changes_remain_incompatible_before_missing_propagation(self):
        p,_=build('e=99 b[1,1]=9 '+transfer(),'a:ARRAY[2] OF INTEGER b:ARRAY[1,1] OF REAL')
        self.assertEqual((p.run()['S'],p.snapshot()['B'],p.snapshot()['E']),(3,[[9.]],99))

    def test_missing_integral_scalar_can_clear_real_receiver(self):
        p,_=build('b=9 '+transfer(),'a:INTEGER b:REAL')
        self.assertEqual((p.run()['B'],p.snapshot()['S']),(MISSING,12311))

    def test_partial_integral_array_preserves_missing_and_reports_only_prefix(self):
        p,_=build('a[1]=7 b[3]=9 '+transfer(),'a:ARRAY[3] OF INTEGER b:ARRAY[3] OF REAL')
        self.assertEqual((p.run()['B'],p.snapshot()['S']),([7.,MISSING,MISSING],12311))
        p,_=build('a[1]=7 '+transfer(),'a:ARRAY[3] OF INTEGER b:ARRAY[1] OF REAL')
        self.assertEqual((p.run()['B'],p.snapshot()['S']),([7.],0))

    def test_unknown_byte_cannot_be_promoted_or_turned_into_missing(self):
        for target in ('INTEGER','SHORT','REAL'):
            p,_=build('e=99 s=77 b[1]=9 '+transfer(),f'a:ARRAY[1] OF BYTE b:ARRAY[1] OF {target}')
            with self.subTest(target=target),self.assertRaisesRegex(rt.KarelRuntimeError,'Unknown BYTE'):p.run()
            self.assertEqual((p.snapshot()['B'],p.snapshot()['E'],p.snapshot()['S']),([9],99,77))

    def test_unknown_byte_beyond_receiver_prefix_is_not_promoted(self):
        p,_=build('a[1]=7 '+transfer(),'a:ARRAY[2] OF BYTE b:ARRAY[1] OF REAL')
        self.assertEqual((p.run()['B'],p.snapshot()['S']),([7.],0))

    def test_short_sentinel_conversion_reports_missing(self):
        p,_=build('a=32767 b=9 '+transfer(),'a:INTEGER b:SHORT')
        self.assertEqual((p.run()['B'],p.snapshot()['S']),(MISSING,12311))

    def test_success_preserves_container_and_retained_leaf_references(self):
        p,_=build('a[1]=7 a[2]=8 '+transfer(),'a:ARRAY[2] OF INTEGER b:ARRAY[2] OF REAL')
        target=p._state.values['B'];ref=rt.index_reference(target,1);p.run()
        self.assertIs(p._state.values['B'],target);self.assertEqual(ref.raw(),7.)

    def test_set_input_is_captured_before_later_status_selector_changes_source(self):
        p,_=build("a[1]=7 SET_VAR(e,'','B',a,codes[change()])",'a:ARRAY[1] OF INTEGER b:ARRAY[1] OF REAL codes:ARRAY[1] OF INTEGER',
                  routines='ROUTINE change:INTEGER BEGIN a[1]=99 RETURN 1 END change')
        state=p.run();self.assertEqual((state['A'],state['B'],state['CODES']),([99],[7.],[0]))

    def test_get_reads_source_after_later_output_selector_effects(self):
        p,_=build("a=7 GET_VAR(e,'','A',b,codes[change()])",'a:INTEGER b:REAL codes:ARRAY[1] OF INTEGER',
                  routines='ROUTINE change:INTEGER BEGIN a=99 RETURN 1 END change')
        self.assertEqual(p.run()['B'],99.)

    def test_saved_context_retains_source_and_receiver_concrete_types(self):
        p,_=build('a[1]=7 '+transfer(),'a:ARRAY[1] OF SHORT b:ARRAY[1] OF REAL');p.run()
        saved=json.loads(json.dumps(p._state.execution.to_config()));ctx=rt.ExecutionContext.from_config(saved)
        again,_=build(transfer(),'a:ARRAY[1] OF SHORT b:ARRAY[1] OF REAL',context=ctx)
        self.assertEqual((again.run()['A'],again.snapshot()['B']),([7],[7.]))

    def test_explicit_system_binding_can_supply_integral_data_for_real_get(self):
        store=rt.VariableStore();store.define('SYSTEM','$COUNT',('INTEGER',),7)
        p,_=build("GET_VAR(e,'SYSTEM','$COUNT',b,s)",'b:REAL',context=rt.ExecutionContext(variables=store))
        self.assertEqual((p.run()['B'],p.snapshot()['S']),(7.,0))

    def test_linked_source_owner_uses_same_numeric_transfer_contract(self):
        project=translate_project({'lib':source('LIB','',decl='a:ARRAY[1] OF SHORT'),
            'main':source('MAIN',"GET_VAR(e,'LIB','A',b,s)",decl='e,s:INTEGER b:ARRAY[2] OF REAL')}).instantiate()
        project.programs['LIB']._state.values['A'].set(1,7);project.run('MAIN')
        self.assertEqual(project.programs['MAIN'].snapshot()['B'],[7.,MISSING])

    def test_whole_record_and_joint_representations_remain_exact(self):
        for source_type,target_type in (('XYZWPR','XYZWPREXT'),('JOINTPOS2','JOINTPOS9')):
            p,_=build('e=99 '+transfer(),f'a:{source_type} b:{target_type}')
            with self.subTest(source=source_type,target=target_type):self.assertEqual((p.run()['S'],p.snapshot()['E']),(3,99))

    def test_numeric_reports_describe_missing_and_atomic_prefix_behavior(self):
        _,result=build(transfer(),'a:ARRAY[1] OF INTEGER b:ARRAY[1] OF REAL')
        policy=json.loads(json.dumps(result.report))['numeric_variable_transfer_policy']
        self.assertIn('GET_VAR',policy['conversions']);self.assertIn('complete',policy['atomicity']);self.assertIn('REAL-to-integral',policy['boundary'])


if __name__=='__main__':unittest.main()
