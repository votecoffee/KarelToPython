"""Authored FILE open-state initialization queries without backend I/O."""
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_dynamic_narrow import create


DECL='f,g:FILE before,during,after:BOOLEAN n,s,entry:INTEGER'


def build(body,**options):return compile_program(body,decl=options.pop('decl',DECL),context=options.pop('context',rt.ExecutionContext(files=rt.MemoryFiles())),**options)


class FileInitializationTests(unittest.TestCase):
    def test_fresh_descriptor_is_uninitialized(self):
        p,_=build('before=UNINIT(f)');self.assertIs(p.run()['BEFORE'],True)
    def test_open_descriptor_is_initialized(self):
        p,_=build("OPEN FILE f('WO','out') during=UNINIT(f)");self.assertIs(p.run()['DURING'],False)
    def test_closed_descriptor_is_uninitialized(self):
        p,_=build("OPEN FILE f('WO','out') CLOSE FILE f after=UNINIT(f)");self.assertIs(p.run()['AFTER'],True)
    def test_full_lifecycle(self):
        p,_=build("before=UNINIT(f) OPEN FILE f('WO','out') during=UNINIT(f) CLOSE FILE f after=UNINIT(f)");v=p.run();self.assertEqual((v['BEFORE'],v['DURING'],v['AFTER']),(True,False,True))
    def test_parenthesized_query_is_supported(self):
        p,_=build('before=UNINIT(((f)))');self.assertIs(p.run()['BEFORE'],True)
    def test_file_type_alias_is_supported(self):
        p,_=build('before=UNINIT(f)',prefix='TYPE stream_t=FILE',decl=DECL.replace('f,g:FILE','f,g:stream_t'));self.assertIs(p.run()['BEFORE'],True)
    def test_file_formal_observes_caller_descriptor(self):
        routines='ROUTINE query(v:FILE):BOOLEAN BEGIN RETURN UNINIT(v) END query'
        p,_=build("before=query(f) OPEN FILE f('WO','out') during=query(f) CLOSE FILE f after=query(f)",routines=routines);v=p.run();self.assertEqual((v['BEFORE'],v['DURING'],v['AFTER']),(True,False,True))
    def test_reopening_initializes_again(self):
        p,_=build("OPEN FILE f('WO','out') CLOSE FILE f before=UNINIT(f) OPEN FILE f('AP','out') during=UNINIT(f)");v=p.run();self.assertEqual((v['BEFORE'],v['DURING']),(True,False))
    def test_failed_open_keeps_uninitialized_state(self):
        p,_=build("OPEN FILE f('RO','absent')")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        with rt._numeric_scope('pythonic'):self.assertTrue(rt.file_uninit(p._state.values['F']))
    def test_queries_do_not_move_cursor_or_change_attributes(self):
        p,_=build("OPEN FILE f('WO','out') WRITE f('data') during=UNINIT(f)");p.run();handle=p._state.values['F'];before=vars(handle).copy()
        with rt._numeric_scope('pythonic'):self.assertFalse(rt.file_uninit(handle))
        self.assertEqual(vars(handle),before)
    def test_queries_do_not_invoke_backend_operations(self):
        p,_=build("OPEN FILE f('WO','out')");p.run()
        with patch.object(p._state.execution.files,'read_bytes',side_effect=AssertionError('unexpected read')),patch.object(p._state.execution.files,'write',side_effect=AssertionError('unexpected write')),rt._numeric_scope('pythonic'):
            self.assertFalse(rt.file_uninit(p._state.values['F']))
    def test_other_file_descriptor_stays_uninitialized(self):
        p,_=build("OPEN FILE f('WO','out') before=UNINIT(g) during=UNINIT(f)");v=p.run();self.assertEqual((v['BEFORE'],v['DURING']),(True,False))
    def test_cancel_without_close_retains_open_state(self):
        p,_=build("OPEN FILE f('WO','out') CANCEL FILE f during=UNINIT(f)");self.assertIs(p.run()['DURING'],False)
    def test_query_works_in_handler_predicates(self):
        body='n=0 CONDITION[1]: WHEN UNINIT(f) DO n=7 ENDCONDITION ENABLE CONDITION[1] s=0'
        p,_=build(body);self.assertEqual(p.run()['N'],7)
    def test_fresh_local_descriptor_query(self):
        p,_=build('work',routines='ROUTINE work VAR local_file:FILE BEGIN before=UNINIT(local_file) END work');self.assertIs(p.run()['BEFORE'],True)
    def test_created_file_byname_query_uses_descriptor(self):
        p,_=build(create('FILE',dims=(0,0,0)).replace('status','s')+"before=query(BYNAME('CACHE','ITEM',entry))",routines='ROUTINE query(v:FILE):BOOLEAN BEGIN RETURN UNINIT(v) END query');self.assertIs(p.run()['BEFORE'],True)
    def test_runtime_strict_guard_remains(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.uninit(rt.FileHandle())
    def test_runtime_subclass_guard_remains(self):
        class Derived(rt.FileHandle):pass
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.file_uninit(Derived())
    def test_malformed_declared_file_storage_is_rejected(self):
        for value in (7,rt.UNINITIALIZED,'closed'):
            p,_=build('before=UNINIT(f)');p._state.values['F']=value
            with self.subTest(value=repr(value)),self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_byte_queries_remain_excluded(self):
        with self.assertRaises(TranslationError) as caught:build('before=UNINIT(b)',decl='b:BYTE before:BOOLEAN')
        self.assertEqual(caught.exception.code,'E_BYTE_UNINIT')
    def test_path_queries_remain_excluded(self):
        with self.assertRaises(TranslationError):build('before=UNINIT(p)',decl='p:PATH before:BOOLEAN')
    def test_report_records_file_storage_type(self):
        _,r=build('before=UNINIT(f)');self.assertEqual(r.report['initialization_queries'][0]['operand_type'],('FILE',));self.assertFalse(r.report['path_io_policy']['controller_validated'])
