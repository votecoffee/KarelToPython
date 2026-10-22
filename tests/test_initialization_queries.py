"""Authored builtin-record initialization checks and retained storage boundaries."""
import json
import unittest

from karel2py import translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source


KINDS=('CONFIG','VECTOR','XYZWPR','XYZWPREXT','POSITION')
DECL='cfg: CONFIG v: VECTOR p: POSITION q: XYZWPR e: XYZWPREXT flag: BOOLEAN s: INTEGER'
CONFIG="CNV_STR_CONF('N',cfg,s) "
POSE=CONFIG+'q=POS(1,2,3,0,0,0,cfg) '


class InitializationValueTests(unittest.TestCase):
    def test_fresh_builtin_records_are_uninitialized(self):
        for kind in KINDS:
            with self.subTest(kind=kind): self.assertTrue(run('flag=UNINIT(value)',decl=f'value: {kind} flag: BOOLEAN')['FLAG'])

    def test_complete_builtin_records_are_initialized(self):
        assignments={'CONFIG':'value=cfg','VECTOR':'value=VEC(1,2,3)',**{kind:'value=q' for kind in ('XYZWPR','XYZWPREXT','POSITION')}}
        for kind in KINDS:
            with self.subTest(kind=kind):
                state=run(POSE+assignments[kind]+' flag=UNINIT(value)',decl=DECL+f' value: {kind}')
                self.assertFalse(state['FLAG'])

    def test_partial_vector_remains_uninitialized(self):
        self.assertTrue(run('v.x=1 v.y=2 flag=UNINIT(v)',decl=DECL)['FLAG'])

    def test_partial_config_remains_uninitialized(self):
        self.assertTrue(run('cfg.cfg_turn_no1=0 flag=UNINIT(cfg)',decl=DECL)['FLAG'])

    def test_coordinates_without_configuration_remain_uninitialized(self):
        self.assertTrue(run('q.x=1 q.y=2 q.z=3 q.w=0 q.p=0 q.r=0 flag=UNINIT(q)',decl=DECL)['FLAG'])

    def test_extended_external_leaves_participate(self):
        p,_=compile_program(POSE+'e=q flag=UNINIT(e)',decl=DECL);p.run()
        p._state.values['E'].values['EXT2']=rt.UNINITIALIZED
        with rt._numeric_scope('pythonic'): self.assertTrue(rt.uninit(p._state.values['E']))

    def test_nested_config_and_position_vectors_participate(self):
        for field,leaf in (('CONFIG_DATA','CFG_FRONT'),('NORMAL','X'),('ORIENT','Y'),('APPROACH','Z'),('LOCATION','X')):
            with self.subTest(field=field):
                p,_=compile_program(POSE+'p=q',decl=DECL);p.run();p._state.values['P'].values[field].values[leaf]=rt.UNINITIALIZED
                with rt._numeric_scope('pythonic'): self.assertTrue(rt.uninit(p._state.values['P']))

    def test_whole_nested_record_clear_is_uninitialized(self):
        p,_=compile_program(POSE+'p=q',decl=DECL);p.run();p._state.values['P'].values['CONFIG_DATA']=rt.UNINITIALIZED
        with rt._numeric_scope('pythonic'): self.assertTrue(rt.uninit(p._state.values['P']))

    def test_query_does_not_initialize_or_replace_storage(self):
        p,_=compile_program('v.x=1 flag=UNINIT(v)',decl=DECL);value=p._state.values['V'];p.run()
        self.assertIs(p._state.values['V'],value);self.assertIs(value.values['Y'],rt.UNINITIALIZED);self.assertEqual(value.values['X'],1.)

    def test_query_can_guard_an_explicit_initialization(self):
        state=run('IF UNINIT(v) THEN v=VEC(1,2,3) ENDIF flag=UNINIT(v)',decl=DECL)
        self.assertFalse(state['FLAG']);self.assertEqual(state['V'],{'X':1.,'Y':2.,'Z':3.})

    def test_initialized_does_not_mean_valid_rotation(self):
        p,_=compile_program(POSE+'p=q',decl=DECL);p.run()
        value=p._state.values['P']
        for field in ('NORMAL','ORIENT','APPROACH'):
            for axis in ('X','Y','Z'): value.values[field].values[axis]=0.
        with rt._numeric_scope('pythonic'): self.assertFalse(rt.uninit(value))
        with self.assertRaises(rt.KarelRuntimeError): rt.frame_value(value)

    def test_sentinel_and_joint_queries_keep_existing_behavior(self):
        state=run('before=UNINIT(n) n=7 after=UNINIT(n) empty=UNINIT(j)',decl='n: INTEGER j: JOINTPOS before,after,empty: BOOLEAN')
        self.assertEqual((state['BEFORE'],state['AFTER'],state['EMPTY']),(True,False,True))


class InitializationStorageTests(unittest.TestCase):
    def test_builtin_records_in_array_elements(self):
        state=run('before=UNINIT(items[1]) items[1]=VEC(1,2,3) after=UNINIT(items[1]) other=UNINIT(items[2])',decl='items: ARRAY[2] OF VECTOR before,after,other: BOOLEAN')
        self.assertEqual((state['BEFORE'],state['AFTER'],state['OTHER']),(True,False,True))

    def test_record_fields_in_user_structures(self):
        prefix='TYPE packet=STRUCTURE point: XYZWPR ENDSTRUCTURE'
        state=run(POSE+'before=UNINIT(item.point) item.point=q after=UNINIT(item.point)',prefix=prefix,decl=DECL+' item: packet before,after: BOOLEAN')
        self.assertEqual((state['BEFORE'],state['AFTER']),(True,False))

    def test_parentheses_preserve_storage_query(self):
        for operand in ('(v)','((v))','(points[1])'):
            with self.subTest(operand=operand): self.assertTrue(run(f'flag=UNINIT({operand})',decl=DECL+' points: ARRAY[1] OF VECTOR')['FLAG'])

    def test_position_orientation_records_can_be_queried_readonly(self):
        state=run('flag=UNINIT(p.normal) p.location.x=1',decl=DECL)
        self.assertTrue(state['FLAG']);self.assertEqual(state['P']['NORMAL']['X'],{'uninitialized':True})

    def test_computed_selector_evaluates_once(self):
        routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN 1 END at'
        state=run('n=0 flag=UNINIT((points[at()]))',decl='points: ARRAY[1] OF VECTOR n: INTEGER flag: BOOLEAN',routines=routines)
        self.assertEqual((state['N'],state['FLAG']),(1,True))

    def test_failed_selector_retains_earlier_effect_and_destination(self):
        routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN 2 END at'
        p,_=compile_program('n=0 flag=FALSE flag=UNINIT(points[at()])',decl='points: ARRAY[1] OF VECTOR n: INTEGER flag: BOOLEAN',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['FLAG']),(1,False))

    def test_readonly_value_formals_can_be_queried(self):
        routines='ROUTINE missing(value: VECTOR): BOOLEAN BEGIN RETURN UNINIT(value) END missing'
        state=run('v=VEC(1,2,3) flag=missing((v))',decl=DECL,routines=routines)
        self.assertFalse(state['FLAG']);self.assertEqual(state['V']['X'],1.)

    def test_reference_formal_can_observe_partial_record(self):
        routines='ROUTINE missing(value: VECTOR): BOOLEAN BEGIN RETURN UNINIT(value) END missing'
        self.assertTrue(run('flag=missing(v)',decl=DECL,routines=routines)['FLAG'])

    def test_condition_predicate_can_observe_initialization_transition(self):
        state=run('n=0 CONDITION[1]: WHEN NOT UNINIT(v) DO n=7 ENDCONDITION ENABLE CONDITION[1] v=VEC(1,2,3) s=1',decl=DECL+' n: INTEGER')
        self.assertEqual(state['N'],7)

    def test_foreign_imported_record_query_uses_shared_storage(self):
        sources={'lib':source('LIB','',decl='point: VECTOR'),
                 'main':source('MAIN','before=UNINIT(point) point=VEC(1,2,3) after=UNINIT(point)',decl='point FROM LIB: VECTOR before,after: BOOLEAN')}
        instance=translate_project(sources).instantiate();state=instance.run('MAIN')
        self.assertEqual((state['MAIN']['values']['BEFORE'],state['MAIN']['values']['AFTER']),(True,False));self.assertEqual(state['LIB']['values']['POINT']['X'],1.)

    def test_partial_record_snapshot_restores_same_query(self):
        p,_=compile_program('v.x=1 flag=UNINIT(v)',decl=DECL);p.run()
        context=rt.ExecutionContext.from_config(json.loads(json.dumps(p._state.execution.to_config())))
        other,_=compile_program('flag=UNINIT(v)',decl=DECL,context=context)
        self.assertTrue(other.run()['FLAG']);self.assertEqual(other.snapshot()['V']['X'],1.)


class InitializationValidationTests(unittest.TestCase):
    def query(self,value):
        with rt._numeric_scope('pythonic'): return rt.uninit(value,71)

    def test_missing_or_extra_record_fields_fail(self):
        for edit in ('missing','extra'):
            value=rt.Structure(('VECTOR',))
            if edit=='missing': del value.values['Z']
            else: value.values['OTHER']=0.
            with self.subTest(edit=edit),self.assertRaisesRegex(rt.KarelRuntimeError,'line 71'): self.query(value)

    def test_wrong_nested_record_type_fails(self):
        value=rt.Structure(('POSITION',));value.values['NORMAL']=rt.Structure(('CONFIG',))
        with self.assertRaises(rt.KarelRuntimeError): self.query(value)

    def test_invalid_known_values_are_not_hidden_by_missing_leaves(self):
        for leaf in (True,None,float('nan'),float('inf'),'bad'):
            value=rt.Structure(('VECTOR',));value.values['Z']=leaf
            with self.subTest(leaf=leaf),self.assertRaises(rt.KarelRuntimeError): self.query(value)

    def test_invalid_later_nested_record_is_not_hidden_by_earlier_missing_leaf(self):
        value=rt.Structure(('POSITION',));value.values['CONFIG_DATA'].values['CFG_FRONT']=7
        with self.assertRaises(rt.KarelRuntimeError): self.query(value)

    def test_wrong_builtin_spec_shape_fails(self):
        value=rt.Structure(('VECTOR',));value.spec=('VECTOR',1)
        with self.assertRaises(rt.KarelRuntimeError): self.query(value)

    def test_unknown_byte_is_not_treated_as_uninitialized(self):
        value=rt.Structure(('VECTOR',));value.values['X']=rt.UNKNOWN_BYTE
        with self.assertRaisesRegex(rt.KarelRuntimeError,'BYTE'): self.query(value)

    def test_strict_record_queries_remain_blocked(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.uninit(rt.Structure(('VECTOR',)))
        with self.assertRaises(TranslationError): legacy_translate('PROGRAM T VAR v: VECTOR flag: BOOLEAN BEGIN flag=UNINIT(v) END T')

    def test_arrays_paths_structures_and_resources_remain_blocked(self):
        declarations=('items: ARRAY[2] OF INTEGER','items: PATH','items: FILE','items: QUEUE_TYPE','items: packet')
        for declaration in declarations:
            with self.subTest(declaration=declaration),self.assertRaises(TranslationError):
                compile_program('flag=UNINIT(items)',decl=declaration+' flag: BOOLEAN',prefix='TYPE packet=STRUCTURE n: INTEGER ENDSTRUCTURE')

    def test_constants_literals_and_function_results_remain_blocked(self):
        for operand in ('1','TRUE','MAXINT','VEC(1,2,3)','make()'):
            with self.subTest(operand=operand),self.assertRaises(TranslationError): compile_program(f'flag=UNINIT({operand})',decl=DECL,routines='ROUTINE make: VECTOR BEGIN RETURN VEC(1,2,3) END make')

    def test_byte_element_queries_remain_blocked(self):
        with self.assertRaises(TranslationError): compile_program('flag=UNINIT(items[1])',decl='items: ARRAY[1] OF BYTE flag: BOOLEAN')

    def test_arity_stays_exact(self):
        for operands in ('','v,v'):
            with self.subTest(operands=operands),self.assertRaises(TranslationError): compile_program(f'flag=UNINIT({operands})',decl=DECL)

    def test_schema_failure_preserves_source_and_destination(self):
        p,_=compile_program('flag=FALSE flag=UNINIT(v)',decl=DECL);value=p._state.values['V'];value.values['Z']=True;before=dict(value.values)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertFalse(p.snapshot()['FLAG']);self.assertEqual(value.values,before)

    def test_report_records_source_locations_and_exact_operand_type(self):
        p,result=compile_program('flag=UNINIT((p.normal))',decl=DECL);p.run();rows=result.report['initialization_queries']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['operand_type'],('VECTOR',));self.assertTrue(rows[0]['grouped']);self.assertTrue(rows[0]['evaluated_once'])
        self.assertFalse(result.report['initialization_query_policy']['controller_validated']);self.assertEqual(p.service_requests,())


if __name__=='__main__': unittest.main()
