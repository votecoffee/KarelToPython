"""Opt-in KCL creation, renaming and detached PATH node changes."""
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_kcl_task_commands import issue


TYPES = ('TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE '
         'header_t=STRUCTURE count:INTEGER ENDSTRUCTURE '
         'route_t=PATH NODEDATA=node_t PATHHEADER=header_t')


def context(**options):
    return rt.ExecutionContext(kcl=rt.KclCommands(variable_commands=True, **options))


def authored(ctx, body, decl='s,n,e:INTEGER', routines=''):
    return compile_program(body, decl=decl, routines=routines, prefix=TYPES, context=ctx)[0]


class KclVariableCommandTests(unittest.TestCase):
    def test_opt_in_and_exact_scripted_replies_keep_precedence(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                ctx = rt.ExecutionContext(kcl=rt.KclCommands(
                    {'CREATE VAR [CACHE]ITEM: INTEGER': {'status': 17}}, variable_commands=enabled))
                self.assertEqual(issue(ctx, 'CREATE VAR [CACHE]ITEM: INTEGER')['S'], 17)
                self.assertEqual(ctx.variables.bindings, {})
                self.assertEqual(issue(ctx, 'create var [cache]item: integer')['S'], 0 if enabled else 1)
                self.assertEqual(('CACHE', 'ITEM') in ctx.variables.bindings, enabled)

    def test_create_array_preserves_outer_order_type_and_pool(self):
        ctx = context()
        command = 'CREATE VARIABLE [CACHE]ITEM IN CMOS: ARRAY[2, 3,4] OF STRING[8]'
        task, _ = compile_program(f"KCL('{command}',s)", prefix='%DEFGROUP=2', context=ctx)
        self.assertEqual(task.run()['S'], 0)
        key = ('CACHE', 'ITEM')
        self.assertEqual(ctx.variables.bindings[key].spec, ('ARRAY', (2, 3, 4), ('STRING', 8)))
        self.assertEqual(ctx.variables.metadata[key], {'group': 2, 'memory_pool': -1})
        self.assertEqual(issue(ctx, command, nowait=True), {'N': 203, 'S': 0})
        self.assertEqual(issue(ctx, 'CREATE VAR [CACHE]ZERO: ARRAY[0] OF INTEGER')['S'], 205)
        self.assertNotIn(('CACHE', 'ZERO'), ctx.variables.bindings)

    def test_rename_root_and_namespace_preserve_reference_metadata_and_lookup(self):
        ctx = context()
        self.assertEqual(issue(ctx, 'CREATE VAR [CACHE]ITEM: INTEGER')['S'], 0)
        key = ('CACHE', 'ITEM')
        reference = ctx.variables.bindings[key]
        reference.set(7)
        ctx.entries[key] = 13
        self.assertEqual(issue(ctx, 'RENAME VARIABLE [CACHE]ITEM RESULT')['S'], 0)
        self.assertEqual(issue(ctx, 'RENAME VARS CACHE SAVED')['S'], 0)
        renamed = ('SAVED', 'RESULT')
        self.assertIs(ctx.variables.bindings[renamed], reference)
        self.assertEqual(ctx.variables.metadata[renamed], {'group': 1, 'memory_pool': 0})
        self.assertEqual(ctx.entries, {renamed: 13})
        self.assertEqual(reference.raw(), 7)

    def test_rename_declined_when_callback_changes_the_planned_bindings(self):
        ctx = context()
        original = ctx.variables.define('CACHE', 'ITEM', ('INTEGER',), 7)
        task = authored(ctx, "KCL('RENAME VAR [CACHE]ITEM RESULT',s)")
        tick = task._state.tick
        changes = []

        def update(*args, **kwargs):
            tick(*args, **kwargs)
            if ctx.kcl._pending is not None and not changes:
                changes.append(ctx.variables.define('CACHE', 'RESULT', ('INTEGER',), 9))

        with patch.object(task._state, 'tick', side_effect=update):
            self.assertEqual(task.run()['S'], 4)
        self.assertIs(ctx.variables.bindings['CACHE', 'ITEM'], original)
        self.assertIs(ctx.variables.bindings['CACHE', 'RESULT'], changes[0])
        self.assertEqual(ctx.kcl.last_status, 4)

    def test_node_edits_retain_header_and_surviving_node_identity(self):
        ctx = context()
        task = authored(ctx, "KCL('CREATE VAR ROUTE: route_t',s) KCL('APPEND NODE ROUTE',s) "
                            "SET_VAR(e,'','ROUTE[1].VALUE',7,s) SET_VAR(e,'','ROUTE.COUNT',9,s)")
        self.assertEqual(task.run()['S'], 0)
        path = ctx.variables.bindings['T', 'ROUTE'].raw()
        header, node = path.data, path.nodes[0]
        self.assertEqual(issue(ctx, 'INSERT NODE [T]ROUTE [1]')['S'], 0)
        self.assertIs(path.nodes[0].values['VALUE'], rt.UNINITIALIZED)
        self.assertIs(path.nodes[1], node)
        self.assertEqual(issue(ctx, 'DELETE NODE [T]ROUTE[1]')['S'], 0)
        self.assertIs(path.nodes[0], node)
        self.assertIs(path.data, header)
        self.assertEqual((header.values['COUNT'], node.values['VALUE']), (9, 7))
        self.assertEqual(issue(ctx, 'INSERT NODE [T]ROUTE[2]')['S'], 202)
        self.assertEqual(len(path.nodes), 1)
        saved = ctx.to_config()
        restored = rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(), saved)
        self.assertEqual(len(restored.variables.bindings['T', 'ROUTE'].raw().nodes), 1)

    def test_borrowed_path_and_explicit_descendant_bindings_block_edits(self):
        ctx = context()
        task = authored(ctx, "KCL('CREATE VAR ROUTE: route_t',s) KCL('APPEND NODE ROUTE',s) "
                            "work(BYNAME('','ROUTE',e))",
                        routines="ROUTINE work(p:route_t) BEGIN KCL('DELETE NODE ROUTE[1]',s) n=PATH_LEN(p) END work")
        self.assertEqual(task.run(), {'S': 204, 'N': 1, 'E': 1})
        path = ctx.variables.bindings['T', 'ROUTE'].raw()
        ctx.variables.bind('OTHER', 'ALIAS', rt.Reference(path.node_spec, path.nodes, 0))
        self.assertEqual(issue(ctx, 'DELETE NODE [T]ROUTE[1]')['S'], 204)
        self.assertEqual(len(path.nodes), 1)

    def test_alias_to_compiled_path_cannot_shift_an_active_for_counter(self):
        ctx = context()
        task = authored(ctx, "APPEND_NODE(route,s) FOR route[1].value=1 TO 2 DO "
                            "KCL('DELETE NODE [CACHE]ALIAS[1]',s) n=route[1].value ENDFOR",
                        decl='route:route_t s,n:INTEGER')
        ctx.variables.bind('CACHE', 'ALIAS', task._state.reference('ROUTE'))
        result = task.run()
        self.assertEqual((result['S'], result['N']), (204, 2))
        self.assertEqual(len(task._state.values['ROUTE'].nodes), 1)
        self.assertEqual(issue(ctx, 'DELETE NODE [T]ROUTE[1]')['S'], 204)

    def test_path_capacity_rejection_keeps_original_nodes(self):
        ctx = context()
        task = authored(ctx, "KCL('CREATE VAR ROUTE: route_t',s) KCL('APPEND NODE ROUTE',s)")
        self.assertEqual(task.run()['S'], 0)
        path = ctx.variables.bindings['T', 'ROUTE'].raw()
        before = path.nodes.copy()
        with patch('karel2py.dynamic.MAX_LEAVES', 2):
            self.assertEqual(issue(ctx, 'APPEND NODE [T]ROUTE')['S'], 206)
        self.assertEqual(path.nodes, before)

    def test_malformed_or_missing_commands_keep_existing_storage(self):
        ctx = context()
        ctx.variables.define('CACHE', 'COUNT', ('INTEGER',), 7)
        for command, status in (('APPEND NODE [CACHE]COUNT', 205), ('APPEND NODE [CACHE]MISSING', 201),
                                ('INSERT NODE [CACHE]COUNT', 1), ('APPEND NODE [CACHE]COUNT[1]', 1),
                                ('DELETE VARIABLE [CACHE]COUNT[1]', 1), ('CREATE VAR [CACHE]SYS: MISSING', 205)):
            self.assertEqual(issue(ctx, command)['S'], status)
        self.assertEqual(ctx.variables.bindings['CACHE', 'COUNT'].raw(), 7)
        with self.assertRaisesRegex(ValueError, 'variable_commands requires'):
            rt.KclCommands.from_config({'variable_commands': 1})


if __name__ == '__main__':
    unittest.main()
