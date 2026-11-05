"""Scalar assignment, detached removal and KCL portable VR commands."""
import unittest

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_kcl_task_commands import issue
from tests.test_kcl_variable_commands import authored


def context():
    return rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True), files=rt.MemoryFiles(),
                               variable_archives=rt.VariableArchives())


class KclVariableMutationTests(unittest.TestCase):
    def test_assignment_checks_exact_scalar_types_and_preserves_text_case(self):
        ctx = context()
        cases = (
            ('COUNT', ('INTEGER',), -17, '-17'),
            ('LEVEL', ('BYTE',), 255, '255'),
            ('OFFSET', ('SHORT',), -32768, '-32768'),
            ('READY', ('BOOLEAN',), True, 'TrUe'),
            ('VALUE', ('REAL',), -125.0, '-1.25E2'),
            ('TEXT', ('STRING', 20), 'Mixed "Case"', '"Mixed ""Case"""'),
        )
        for name, spec, expected, literal in cases:
            with self.subTest(name=name):
                reference = ctx.variables.define('CACHE', name, spec)
                self.assertEqual(issue(ctx, f'SET VARIABLE [CACHE]{name} = {literal}')['S'], 0)
                self.assertEqual(reference.raw(), expected)
        for name, literal in (('COUNT', '1.5'), ('COUNT', '2147483647'), ('LEVEL', '256'),
                              ('READY', '1'), ('VALUE', '1E999'), ('TEXT', '"123456789012345678901"')):
            before = ctx.variables.bindings['CACHE', name].raw()
            self.assertEqual(issue(ctx, f'SET VAR [CACHE]{name} = {literal}')['S'], 205)
            self.assertEqual(ctx.variables.bindings['CACHE', name].raw(), before)

    def test_set_array_leaf_and_path_field_only(self):
        ctx = context()
        self.assertEqual(issue(ctx, 'CREATE VAR [CACHE]ITEMS:ARRAY[2,2] OF INTEGER')['S'], 0)
        self.assertEqual(issue(ctx, 'SET VAR [CACHE]ITEMS[2, 1]=9')['S'], 0)
        cells = ctx.variables.bindings['CACHE', 'ITEMS'].raw().values
        self.assertEqual(cells[2], 9)
        self.assertIs(cells[3], rt.UNINITIALIZED)
        self.assertEqual(issue(ctx, 'SET VAR [CACHE]ITEMS=4')['S'], 205)
        self.assertEqual(issue(ctx, 'SET VAR [CACHE]ITEMS[3,1]=4')['S'], 205)
        path = authored(ctx, "KCL('CREATE VAR ROUTE:route_t',s) KCL('APPEND NODE ROUTE',s) "
                             "KCL('SET VAR ROUTE[1].VALUE=17',s) GET_VAR(e,'','ROUTE[1].VALUE',n,s)")
        self.assertEqual(path.run(), {'S': 0, 'N': 17, 'E': 1})

    def test_active_counter_and_borrowed_reference_are_protected(self):
        ctx = context()
        task, _ = compile_program("FOR n=1 TO 2 DO KCL('SET VAR [CACHE]ITEM=99',s) ENDFOR", context=ctx)
        ctx.variables.bind('CACHE', 'ITEM', task._state.reference('N'))
        self.assertEqual(task.run()['S'], 204)
        self.assertEqual(issue(ctx, 'DELETE VAR [CACHE]ITEM')['S'], 204)
        self.assertEqual(issue(ctx, 'CLEAR VARS CACHE')['S'], 204)
        other = ctx.variables.define('OTHER', 'ITEM', ('INTEGER',), 7)
        borrower = authored(ctx, "edit(BYNAME('OTHER','ITEM',e))",
                           routines="ROUTINE edit(v:INTEGER) BEGIN KCL('SET VAR [OTHER]ITEM=9',s) n=v END edit")
        self.assertEqual(borrower.run()['S'], 204)
        self.assertEqual(other.raw(), 7)

    def test_clear_preflights_all_bindings_and_releases_only_closed_files(self):
        ctx = context()
        value = ctx.variables.define('CACHE', 'VALUE', ('INTEGER',), 5)
        self.assertEqual(issue(ctx, 'CREATE VAR [CACHE]STREAM:FILE')['S'], 0)
        stream = ctx.variables.bindings['CACHE', 'STREAM'].raw()
        ctx.files.open(stream, 'WO', 'output')
        self.assertEqual(issue(ctx, 'CLEAR VARS CACHE YES')['S'], 204)
        self.assertIs(ctx.variables.bindings['CACHE', 'VALUE'], value)
        self.assertEqual(issue(ctx, 'DELETE VAR [CACHE]STREAM')['S'], 204)
        ctx.files.close(stream)
        self.assertEqual(issue(ctx, 'CLEAR VARS CACHE Y')['S'], 0)
        self.assertEqual(ctx.variables.bindings, {})
        self.assertEqual(ctx.variables.metadata, {})
        self.assertEqual(ctx.files.snapshot(), {'output': b''})

    def test_delete_removes_its_entries_without_reusing_a_live_id(self):
        ctx = context()
        for name in ('FIRST', 'SECOND', 'THIRD'):
            ctx.variables.define('CACHE', name, ('INTEGER',), 1)
        task, _ = compile_program("GET_VAR(e,'CACHE','FIRST',n,s) GET_VAR(e,'CACHE','SECOND',n,s) "
                                  "KCL('DELETE VARIABLE [CACHE]FIRST',s) GET_VAR(e,'CACHE','THIRD',n,s)",
                                  decl='e,n,s:INTEGER', context=ctx)
        self.assertEqual(task.run()['E'], 3)
        self.assertEqual(ctx.entries, {('CACHE', 'SECOND'): 2, ('CACHE', 'THIRD'): 3})
        self.assertEqual(issue(ctx, 'DELETE VAR [CACHE]FIRST')['S'], 201)

    def test_clear_protects_an_attached_namespace_but_delete_allows_detached_root(self):
        ctx = context()
        task, _ = compile_program("KCL('CREATE VAR ITEM:INTEGER',s) KCL('CLEAR VARS T',n) "
                                  "KCL('DELETE VAR ITEM',s)", context=ctx)
        self.assertEqual(task.run(), {'N': 204, 'S': 0})
        self.assertEqual(ctx.variables.bindings, {})


class KclVariableArchiveTests(unittest.TestCase):
    def test_save_clear_load_roundtrip_uses_archive_identity_and_policy(self):
        ctx = context()
        self.assertEqual(issue(ctx, 'CREATE VAR [CACHE]ITEM IN CMOS:INTEGER')['S'], 0)
        self.assertEqual(issue(ctx, 'SET VAR [CACHE]ITEM=43')['S'], 0)
        self.assertEqual(issue(ctx, 'SAVE VARS alias = CACHE', nowait=True), {'S': 0, 'N': 0})
        archived = ctx.files.snapshot()['ALIAS.VR']
        self.assertEqual(issue(ctx, 'SAVE VARS alias = CACHE')['S'], 203)
        self.assertEqual(issue(ctx, 'CLEAR VARS CACHE')['S'], 0)
        self.assertEqual(issue(ctx, 'LOAD VARS alias.vr')['S'], 0)
        self.assertEqual(ctx.variables.bindings['CACHE', 'ITEM'].raw(), 43)
        self.assertEqual(ctx.variables.metadata['CACHE', 'ITEM'], {'group': 1, 'memory_pool': -1})
        self.assertEqual(ctx.files.snapshot()['ALIAS.VR'], archived)
        self.assertNotIn(('ALIAS', 'ITEM'), ctx.variables.bindings)

    def test_load_preserves_independent_existing_references(self):
        ctx = context()
        reference = ctx.variables.define('CACHE', 'ITEM', ('INTEGER',), 4)
        self.assertEqual(issue(ctx, 'SAVE VARS CACHE')['S'], 0)
        reference.set(9)
        self.assertEqual(issue(ctx, 'LOAD VARS CACHE')['S'], 0)
        self.assertIs(ctx.variables.bindings['CACHE', 'ITEM'], reference)
        self.assertEqual(reference.raw(), 4)

    def test_payload_cannot_restore_into_attached_program_even_with_alias_filename(self):
        ctx = context()
        task, _ = compile_program("n=7 KCL('SAVE VARS alias = T',s) n=9 "
                                  "KCL_NO_WAIT('LOAD VARS alias',s) result=KCL_STATUS",
                                  decl='n,s,result:INTEGER', context=ctx)
        self.assertEqual(task.run(), {'N': 9, 'S': 0, 'RESULT': 204})
        self.assertIn('ALIAS.VR', ctx.files.files)

    def test_load_cannot_change_a_borrowed_reference(self):
        ctx = context()
        reference = ctx.variables.define('CACHE', 'ITEM', ('INTEGER',), 7)
        self.assertEqual(issue(ctx, 'SAVE VARS CACHE')['S'], 0)
        reference.set(9)
        task = authored(ctx, "work(BYNAME('CACHE','ITEM',e))",
                        routines="ROUTINE work(v:INTEGER) BEGIN KCL('LOAD VARS CACHE',s) n=v END work")
        self.assertEqual(task.run()['S'], 204)
        self.assertEqual(reference.raw(), 9)

    def test_load_validates_complete_archive_and_retains_bytes(self):
        ctx = context()
        one = ctx.variables.define('CACHE', 'ONE', ('INTEGER',), 1)
        ctx.variables.define('CACHE', 'TWO', ('INTEGER',), 2)
        self.assertEqual(issue(ctx, 'SAVE VARS CACHE')['S'], 0)
        ctx.variables.define('CACHE', 'TWO', ('STRING', 3), 'abc')
        one.set(5)
        before = ctx.files.snapshot()
        self.assertEqual(issue(ctx, 'LOAD VARS CACHE')['S'], 206)
        self.assertEqual(one.raw(), 5)
        self.assertEqual(ctx.variables.bindings['CACHE', 'TWO'].raw(), 'abc')
        self.assertEqual(ctx.files.snapshot(), before)
        self.assertEqual(issue(ctx, 'LOAD VARS ../CACHE')['S'], 202)
        self.assertEqual(issue(ctx, 'LOAD VARS CACHE CONVERT')['S'], 1)


if __name__ == '__main__':
    unittest.main()
