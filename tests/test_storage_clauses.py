"""Authored declaration placement metadata and unchanged offline lifetimes."""
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program


class StorageClauseTests(unittest.TestCase):
    def test_global_cmos_values(self):
        p,_=compile_program('saved=7',decl='saved IN CMOS:INTEGER');self.assertEqual(p.run()['SAVED'],7)
    def test_global_dram_values(self):
        p,_=compile_program('saved=9',decl='saved IN DRAM:INTEGER');self.assertEqual(p.run()['SAVED'],9)
    def test_comma_list_records_each_variable(self):
        p,r=compile_program('a=1 b=2',decl='a,b IN CMOS:INTEGER');self.assertEqual([x['name'] for x in r.report['storage_declarations']],['A','B']);self.assertEqual(p.run(),{'A':1,'B':2})
    def test_mixed_qualified_and_unqualified_declarations(self):
        p,r=compile_program('a=1 b=2 c=3',decl='a IN CMOS:INTEGER b:INTEGER c IN DRAM:INTEGER');self.assertEqual([x['pool'] for x in r.report['storage_declarations']],['CMOS','DRAM']);self.assertEqual(p.run()['B'],2)
    def test_case_insensitive_pool(self):
        p,r=compile_program('a=1',decl='a in cMoS:integer');self.assertEqual(r.report['storage_declarations'][0]['pool'],'CMOS')
    def test_type_alias_and_array(self):
        p,_=compile_program('a[2]=5',prefix='TYPE row=ARRAY[2]OF INTEGER',decl='a IN CMOS:row');self.assertEqual(p.run()['A'][1],5)
    def test_group_qualification_remains_after_type(self):
        p,_=compile_program('a.x=5',decl='a IN DRAM:XYZWPR IN GROUP[1]');self.assertEqual(p.run()['A']['X'],5.)
    def test_physical_newlines_after_in_and_pool(self):
        p,_=compile_program('a=1',decl='a IN\n CMOS\n:INTEGER');self.assertEqual(p.run()['A'],1)
    def test_comments_in_placement(self):
        p,_=compile_program('a=1',decl='a IN -- note\n DRAM:INTEGER');self.assertEqual(p.run()['A'],1)
    def test_local_metadata_names_routine_owner(self):
        p,r=compile_program('work',decl='n:INTEGER',routines='ROUTINE work VAR a IN DRAM:INTEGER BEGIN a=3 n=a END work');self.assertEqual(p.run()['N'],3);self.assertEqual((r.report['storage_declarations'][0]['owner'],r.report['storage_declarations'][0]['name']),('WORK','A'))
    def test_local_storage_is_fresh_per_call(self):
        p,_=compile_program('work work',decl='n:INTEGER',routines='ROUTINE work VAR a IN CMOS:INTEGER BEGIN IF UNINIT(a) THEN a=1 ELSE a=a+1 ENDIF n=a END work');self.assertEqual(p.run()['N'],1)
    def test_cmos_does_not_initialize_data(self):
        p,_=compile_program('',decl='a IN CMOS:INTEGER');self.assertEqual(p.run()['A'],{'uninitialized':True})
    def test_pool_does_not_change_unknown_byte_default(self):
        p,_=compile_program('',decl='a IN DRAM:BYTE');self.assertEqual(p.run()['A'],{'unknown_byte':True})
    def test_program_metadata_is_immutable_and_independent_of_report(self):
        p,r=compile_program('',decl='a IN CMOS:INTEGER');before=p.source_storage_declarations;r.report['storage_declarations'][0]['pool']='DRAM';self.assertEqual(p.source_storage_declarations,before);self.assertIsInstance(before,tuple);self.assertTrue(all(isinstance(x,tuple) for x in before))
    def test_locations_are_original_source_coordinates(self):
        result=translate('PROGRAM SAMPLE\nVAR\n  saved IN CMOS:INTEGER\nBEGIN END SAMPLE');row=result.report['storage_declarations'][0];self.assertEqual(row,dict(owner='SAMPLE',name='SAVED',pool='CMOS',line=3,column=3))
    def test_local_shadows_global_without_pool_collision(self):
        p,r=compile_program('a=2 work',decl='a IN CMOS:INTEGER n:INTEGER',routines='ROUTINE work VAR a IN DRAM:INTEGER BEGIN a=7 n=a END work');self.assertEqual((p.run()['A'],p.snapshot()['N']),(2,7));self.assertEqual([x['owner'] for x in r.report['storage_declarations']],['T','WORK'])
    def test_default_storage_directives_and_explicit_intent_are_separate(self):
        p,r=compile_program('a=1',prefix='%SHADOWVARS',decl='a IN DRAM:INTEGER');self.assertEqual((p.run()['A'],r.report['storage_declarations'][0]['pool']),(1,'DRAM'));self.assertEqual(p.source_settings['storage'],'SHADOW')
    def test_linked_declaration_keeps_owned_storage(self):
        result=translate_project({'lib':'PROGRAM LIB VAR n IN CMOS:INTEGER BEGIN n=7 END LIB','main':'PROGRAM MAIN VAR n FROM LIB:INTEGER out IN DRAM:INTEGER BEGIN n=9 out=n END MAIN'});p=result.instantiate();p.run('MAIN');self.assertEqual(p.programs['LIB'].snapshot()['N'],9)
    def test_imported_storage_clause_is_rejected(self):
        with self.assertRaises(TranslationError) as caught:compile_program('',decl='n FROM LIB IN CMOS:INTEGER')
        self.assertEqual(caught.exception.code,'E_STORAGE')
    def test_unknown_pool_is_rejected(self):
        for pool in ('SHADOW','GROUP[1]','1','TRUE'):
            with self.subTest(pool=pool),self.assertRaises(TranslationError) as caught:compile_program('',decl='a IN '+pool+':INTEGER')
            self.assertEqual(caught.exception.code,'E_STORAGE_POOL')
    def test_repeated_pool_is_rejected(self):
        with self.assertRaises(TranslationError):compile_program('',decl='a IN CMOS IN DRAM:INTEGER')
    def test_storage_after_type_is_not_group_syntax(self):
        with self.assertRaises(TranslationError):compile_program('',decl='a:INTEGER IN CMOS')
    def test_formal_storage_remains_rejected(self):
        with self.assertRaises(TranslationError):compile_program('',routines='ROUTINE work(a IN CMOS:INTEGER) BEGIN END work')
    def test_strict_is_still_future_work(self):
        with self.assertRaises(TranslationError) as caught:translate('PROGRAM SAMPLE VAR a IN CMOS:INTEGER BEGIN END SAMPLE',mode='strict')
        self.assertEqual(caught.exception.code,'E_MODE')
    def test_include_storage_metadata_retains_physical_origin(self):
        r=translate('PROGRAM SAMPLE\n%INCLUDE VARS\nBEGIN saved=7 END SAMPLE',includes={'VARS.KL':'VAR\n saved IN CMOS:INTEGER'})
        row=r.report['storage_declarations'][0];self.assertEqual((row['source_file'],row['source_line'],row['source_column']),('VARS.KL',2,2));self.assertEqual(row['include_stack'],['VARS.KL'])
    def test_bad_storage_pool_in_include_is_source_located(self):
        with self.assertRaises(TranslationError) as caught:translate('PROGRAM SAMPLE\n%INCLUDE VARS\nBEGIN END SAMPLE',includes={'VARS.KL':'VAR saved IN SHADOW:INTEGER'})
        self.assertEqual((caught.exception.filename,caught.exception.token.line),('VARS.KL',1))
    def test_report_describes_offline_lifetime_boundary(self):
        _,r=compile_program('',decl='a IN DRAM:INTEGER');p=r.report['source_form_policy'];self.assertFalse(p['controller_validated']);self.assertIn('fresh routine locals',p['lifetime'])
