"""Authored Pythonic narrow CREATE_VAR, exact aliases and saved data checks."""
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt, translate_project
from karel2py.dynamic import concrete_type
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


UNKNOWN = {'unknown_byte': True}
MISSING = {'uninitialized': True}
DECL = 'entry,status,n,seen,prior,calls: INTEGER b: BYTE small: SHORT flag: BOOLEAN'


def create(kind='BYTE', *, owner='CACHE', name='ITEM', type_owner='', group=0, dims=(0, 0, 0), pool=None):
    inner, middle, outer = dims
    tail = '' if pool is None else f',{pool}'
    return f"CREATE_VAR('{owner}','{name}','{type_owner}','{kind}',{group},{inner},{middle},{outer},status{tail}) "


def program(body='', **options):
    return compile_program(body, decl=options.pop('decl', DECL), **options)


def execute(body='', **options):
    p, _ = program(body, **options)
    return p.run(), p._state.execution


class DynamicNarrowCreationTests(unittest.TestCase):
    def test_direct_byte_scalar_starts_unknown(self):
        state, ctx = execute(create())
        ref = ctx.variables.bindings['CACHE', 'ITEM']
        self.assertEqual((state['STATUS'], ref.spec, rt.snapshot_value(ref.raw())), (0, ('BYTE',), UNKNOWN))
        self.assertEqual(ctx.variables.metadata['CACHE', 'ITEM'], {'group': 0, 'memory_pool': 0})

    def test_direct_short_scalar_starts_missing(self):
        state, ctx = execute(create('SHORT'))
        self.assertEqual((state['STATUS'], ctx.variables.bindings['CACHE', 'ITEM'].spec), (0, ('SHORT',)))
        self.assertIs(ctx.variables.bindings['CACHE', 'ITEM'].raw(), rt.UNINITIALIZED)

    def test_blank_current_namespace_and_case_folded_type(self):
        state, ctx = execute(create(' byte ', owner=' ') + "SET_VAR(entry,'','item',255,status) GET_VAR(entry,'T','ITEM',b,status)")
        self.assertEqual((state['B'], state['STATUS']), (255, 0))
        self.assertIn(('T', 'ITEM'), ctx.variables.bindings)

    def test_explicit_type_program_is_not_needed_for_builtin_names(self):
        state, ctx = execute(create('SHORT', type_owner='UNATTACHED') + "SET_VAR(entry,'CACHE','ITEM',-32768,status)")
        self.assertEqual((state['STATUS'], ctx.variables.bindings['CACHE', 'ITEM'].raw()), (0, -32768))

    def test_current_transparent_alias_and_alias_chain(self):
        state, ctx = execute(create('octet') + create('signed', name='COUNT'), prefix='TYPE base=BYTE octet=base signed=SHORT')
        self.assertEqual((state['STATUS'], ctx.variables.bindings['CACHE', 'ITEM'].spec, ctx.variables.bindings['CACHE', 'COUNT'].spec),
                         (0, ('BYTE',), ('SHORT',)))

    def test_foreign_attached_transparent_alias_selects_its_owner(self):
        project = translate_project({
            'lib': 'PROGRAM LIB TYPE selected=SHORT VAR n:INTEGER BEGIN END LIB',
            'main': source('MAIN', create('selected', type_owner='LIB'), decl=DECL)})
        instance = project.instantiate(); instance.run('MAIN')
        self.assertEqual(instance.context.variables.bindings['CACHE', 'ITEM'].spec, ('SHORT',))

    def test_type_name_uses_current_program_when_owner_blank(self):
        project = translate_project({
            'lib': 'PROGRAM LIB TYPE selected=SHORT VAR n:INTEGER BEGIN END LIB',
            'main': 'PROGRAM MAIN TYPE selected=BYTE VAR status:INTEGER BEGIN ' + create('selected') + ' END MAIN'})
        instance = project.instantiate(); instance.run('MAIN')
        self.assertEqual(instance.context.variables.bindings['CACHE', 'ITEM'].spec, ('BYTE',))

    def test_linked_routine_defaults_to_executing_source_for_creation(self):
        instance = translate_project({
            'lib': 'PROGRAM LIB TYPE octet=SHORT VAR status:INTEGER ROUTINE make BEGIN ' + create('octet', owner='') + ' END make BEGIN END LIB',
            'main': source('MAIN', 'make()', decl=DECL, routines='ROUTINE make FROM LIB')}).instantiate()
        instance.run('MAIN')
        self.assertEqual(instance.context.variables.bindings['LIB', 'ITEM'].spec, ('SHORT',))
        self.assertNotIn(('MAIN', 'ITEM'), instance.context.variables.bindings)

    def test_unknown_or_unattached_alias_returns_status_without_creation(self):
        for type_owner in ('', 'ABSENT'):
            with self.subTest(type_owner=type_owner):
                state, ctx = execute(create('not_declared', type_owner=type_owner))
                self.assertEqual((state['STATUS'], ctx.variables.bindings, ctx.variables.metadata), (5, {}, {}))

    def test_both_memory_pools_retain_nonpositional_group_metadata(self):
        for pool in (-1, 0):
            with self.subTest(pool=pool):
                state, ctx = execute(create('BYTE', group=32, pool=pool))
                self.assertEqual((state['STATUS'], ctx.variables.metadata['CACHE', 'ITEM']), (0, {'group': 32, 'memory_pool': pool}))

    def test_direct_narrow_names_follow_existing_dimension_wrapping(self):
        for kind in ('BYTE', 'SHORT'):
            with self.subTest(kind=kind):
                state, ctx = execute(create(kind, dims=(4, 3, 2)))
                ref = ctx.variables.bindings['CACHE', 'ITEM']
                self.assertEqual((state['STATUS'], ref.spec, rt.scalar_leaf_count(ref.spec)), (0, ('ARRAY', (2, 3, 4), (kind,)), 24))

    def test_transparent_narrow_alias_can_have_dimensions(self):
        state, ctx = execute(create('octet', dims=(2, 0, 0)), prefix='TYPE octet=BYTE')
        self.assertEqual((state['STATUS'], ctx.variables.bindings['CACHE', 'ITEM'].raw().snapshot()), (0, [UNKNOWN, UNKNOWN]))

    def test_documented_array_spellings_still_require_a_dimension(self):
        for kind in ('ARRAY OF BYTE', 'ARRAY OF SHORT'):
            with self.subTest(kind=kind):
                state, ctx = execute(create(kind))
                self.assertEqual((state['STATUS'], ctx.variables.bindings), (5, {}))
                state, ctx = execute(create(kind, dims=(2, 0, 0)))
                self.assertEqual((state['STATUS'], ctx.variables.bindings['CACHE', 'ITEM'].spec), (0, ('ARRAY', 2, (kind.split()[-1],))))

    def test_runtime_type_string_is_evaluated_once(self):
        state, ctx = execute("calls=0 " + create('unused').replace("'unused'", 'kind()'),
                            routines="ROUTINE kind: STRING BEGIN calls=calls+1 RETURN 'SHORT' END kind")
        self.assertEqual((state['CALLS'], state['STATUS'], ctx.variables.bindings['CACHE', 'ITEM'].spec), (1, 0, ('SHORT',)))


class DynamicNarrowAliasAndTransferTests(unittest.TestCase):
    def test_unknown_byte_can_be_initialized_through_exact_byname(self):
        state, ctx = execute(create() + "put(BYNAME('CACHE','ITEM',entry)) GET_VAR(entry,'CACHE','ITEM',b,status)",
                            routines='ROUTINE put(value:BYTE) BEGIN value=255 END put')
        self.assertEqual((state['B'], state['STATUS'], ctx.variables.bindings['CACHE', 'ITEM'].raw()), (255, 0, 255))

    def test_missing_short_exact_byname_supports_uninit_and_initialization(self):
        state, _ = execute(create('SHORT') + "put(BYNAME('CACHE','ITEM',entry)) GET_VAR(entry,'CACHE','ITEM',small,status)",
                           routines='ROUTINE put(value:SHORT) BEGIN flag=UNINIT(value) value=-11 END put')
        self.assertEqual((state['FLAG'], state['SMALL'], state['STATUS']), (True, -11, 0))

    def test_alias_formal_preserves_exact_underlying_scalar_type(self):
        state, _ = execute(create('octet') + "put(BYNAME('CACHE','ITEM',entry)) GET_VAR(entry,'CACHE','ITEM',b,status)",
                           prefix='TYPE octet=BYTE', routines='ROUTINE put(value:octet) BEGIN value=42 END put')
        self.assertEqual(state['B'], 42)

    def test_byname_does_not_perform_integral_value_conversion(self):
        for actual, formal in (('BYTE', 'SHORT'), ('SHORT', 'BYTE'), ('BYTE', 'INTEGER'), ('INTEGER', 'BYTE')):
            with self.subTest(actual=actual, formal=formal):
                p, _ = program(create(actual) + "entry=77 seen=0 put(BYNAME('CACHE','ITEM',entry))",
                               routines=f'ROUTINE put(value:{formal}) BEGIN seen=1 END put')
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'type does not match'): p.run()
                self.assertEqual((p.snapshot()['ENTRY'], p.snapshot()['SEEN'], p._state.call_depth, p._state.local_frames), (77, 0, 0, []))

    def test_unknown_byte_read_fails_without_routine_frame_leak(self):
        p, _ = program(create() + "n=9 probe(BYNAME('CACHE','ITEM',entry))", routines='ROUTINE probe(value:BYTE) BEGIN n=value END probe')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'BYTE contents are unknown'): p.run()
        self.assertEqual((p.snapshot()['N'], p._state.local_frames, p._state.call_depth), (9, [], 0))

    def test_byte_uninit_policy_cannot_be_bypassed_by_dynamic_formal(self):
        with self.assertRaises(TranslationError) as caught:
            program(create() + "probe(BYNAME('CACHE','ITEM',entry))", routines='ROUTINE probe(value:BYTE) BEGIN flag=UNINIT(value) END probe')
        self.assertEqual(caught.exception.code, 'E_BYTE_UNINIT')

    def test_set_var_accepts_checked_integer_domain_values(self):
        state, _ = execute(create() + create('SHORT', name='COUNT') +
            "SET_VAR(entry,'CACHE','ITEM',255,status) SET_VAR(entry,'CACHE','COUNT',-32768,status) "
            "GET_VAR(entry,'CACHE','ITEM',b,status) GET_VAR(entry,'CACHE','COUNT',small,status)")
        self.assertEqual((state['B'], state['SMALL'], state['STATUS']), (255, -32768, 0))

    def test_set_var_range_failures_preserve_existing_narrow_value(self):
        for kind, invalid in (('BYTE', -1), ('BYTE', 256), ('SHORT', -32769), ('SHORT', 32768)):
            with self.subTest(kind=kind, invalid=invalid):
                p, _ = program(create(kind) + f"SET_VAR(entry,'CACHE','ITEM',7,status) SET_VAR(entry,'CACHE','ITEM',{invalid},status)")
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'outside'): p.run()
                self.assertEqual(p._state.execution.variables.bindings['CACHE', 'ITEM'].raw(), 7)

    def test_get_var_unknown_byte_copies_the_unknown_marker(self):
        state, _ = execute(create() + "b=7 GET_VAR(entry,'CACHE','ITEM',b,status)")
        self.assertEqual((state['B'], state['STATUS']), (UNKNOWN, 0))

    def test_get_var_missing_short_sets_missing_status(self):
        state, _ = execute(create('SHORT') + "small=7 GET_VAR(entry,'CACHE','ITEM',small,status)")
        self.assertEqual((state['SMALL'], state['STATUS']), (MISSING, 12311))

    def test_get_var_does_not_promote_output_reference(self):
        state, _ = execute(create() + "SET_VAR(entry,'CACHE','ITEM',7,status) n=99 GET_VAR(entry,'CACHE','ITEM',n,status)")
        self.assertEqual((state['N'], state['STATUS']), (99, 3))

    def test_short_sentinel_can_clear_dynamic_storage_through_alias(self):
        state, ctx = execute(create('SHORT') + "clear(BYNAME('CACHE','ITEM',entry)) GET_VAR(entry,'CACHE','ITEM',small,status)",
                             routines='ROUTINE clear(value:SHORT) BEGIN value=32767 END clear')
        self.assertEqual((state['SMALL'], state['STATUS']), (MISSING, 12311))
        self.assertIs(ctx.variables.bindings['CACHE', 'ITEM'].raw(), rt.UNINITIALIZED)

    def test_set_var_integer_sentinel_clears_dynamic_short_with_missing_status(self):
        state, ctx = execute(create('SHORT') + "SET_VAR(entry,'CACHE','ITEM',7,status) SET_VAR(entry,'CACHE','ITEM',32767,status)")
        self.assertEqual(state['STATUS'], 12311)
        self.assertIs(ctx.variables.bindings['CACHE', 'ITEM'].raw(), rt.UNINITIALIZED)

    def test_byname_alias_survives_pause_and_root_rename(self):
        p, _ = program(create() + "put(BYNAME('CACHE','ITEM',entry)) GET_VAR(entry,'CACHE','RENAMED',b,status)", cooperative=True,
                       routines="ROUTINE put(value:BYTE) BEGIN RENAME_VAR('CACHE','ITEM','RENAMED',status) PAUSE value=255 END put")
        with self.assertRaises(rt.KarelPause): p.run()
        reference = p._state.execution.variables.bindings['CACHE', 'RENAMED']
        p.resume()
        self.assertEqual((p.snapshot()['B'], reference.raw(), p._state.local_frames), (255, 255, []))

    def test_linked_narrow_routine_receives_true_dynamic_reference(self):
        instance = translate_project({
            'lib': source('LIB', '', decl='n:INTEGER', routines='ROUTINE put(value:BYTE) BEGIN value=42 END put'),
            'main': source('MAIN', create() + "put(BYNAME('CACHE','ITEM',entry)) GET_VAR(entry,'CACHE','ITEM',b,status)",
                           decl=DECL, routines='ROUTINE put(value:BYTE) FROM LIB')}).instantiate()
        instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].snapshot()['B'], 42)


class DynamicNarrowPreflightTests(unittest.TestCase):
    def test_duplicate_creation_preserves_value_type_and_policy(self):
        state, ctx = execute(create(pool=-1) + "SET_VAR(entry,'CACHE','ITEM',7,status) " + create('SHORT', pool=0))
        ref = ctx.variables.bindings['CACHE', 'ITEM']
        self.assertEqual((state['STATUS'], ref.spec, ref.raw(), ctx.variables.metadata['CACHE', 'ITEM']), (3, ('BYTE',), 7, {'group': 0, 'memory_pool': -1}))

    def test_declared_narrow_global_collision_preserves_original(self):
        state, ctx = execute('b=7 ' + create(owner='', name='B'))
        self.assertEqual((state['STATUS'], state['B'], ctx.variables.bindings), (3, 7, {}))

    def test_preexisting_descendant_binding_prevents_root_creation(self):
        store = rt.VariableStore(); ref = store.define('CACHE', 'ITEM[1]', ('BYTE',), 8)
        state, ctx = execute(create(), context=rt.ExecutionContext(variables=store))
        self.assertEqual((state['STATUS'], set(ctx.variables.bindings), ref.raw()), (3, {('CACHE', 'ITEM[1]')}, 8))

    def test_invalid_options_fail_before_allocating_or_changing_store(self):
        calls = [create(group=-1), create(group=33), create(pool=1), create(name='BAD.NAME'),
                 create(dims=(-1, 0, 0)), create(dims=(0, 1, 0)), create(dims=(1, 0, 1)),
                 create(dims=(32768, 0, 0)), create(dims=(32767, 2, 0))]
        for call in calls:
            with self.subTest(call=call):
                p, _ = program(call)
                with patch.object(rt, 'initial_value', side_effect=AssertionError('Allocated invalid variable')): state = p.run()
                self.assertIn(state['STATUS'], (2, 5))
                self.assertEqual((p._state.execution.variables.bindings, p._state.execution.variables.metadata), ({}, {}))

    def test_scalar_creation_consumes_one_leaf_of_existing_limit(self):
        state, ctx = execute(create('ARRAY OF BYTE', name='BUFFER', dims=(32766, 0, 0)) + create('SHORT') + create(name='EXCESS'))
        self.assertEqual((state['STATUS'], set(ctx.variables.bindings)), (6, {('CACHE', 'BUFFER'), ('CACHE', 'ITEM')}))
        self.assertEqual(sum(rt.scalar_leaf_count(ref.spec) for ref in ctx.variables.bindings.values()), 32767)

    def test_excess_scalar_limit_is_checked_before_initial_value(self):
        p, _ = program(create('ARRAY OF SHORT', name='BUFFER', dims=(32767, 0, 0)))
        p.run(); q, _ = program(create(), context=p._state.execution)
        with patch.object(rt, 'initial_value', side_effect=AssertionError('Allocated over-limit scalar')): state = q.run()
        self.assertEqual(state['STATUS'], 6)
        self.assertNotIn(('CACHE', 'ITEM'), p._state.execution.variables.bindings)

    def test_budget_failure_preserves_status_and_no_creation_is_published(self):
        p, _ = program('status=77 ' + create())
        original = p._state.tick
        def tick(line=None):
            if any(row['operation'] == 'CREATE_VAR' for row in p._state.service_requests): raise rt.KarelRuntimeError('Authored budget exhaustion')
            return original(line)
        with patch.object(p._state, 'tick', side_effect=tick), self.assertRaisesRegex(rt.KarelRuntimeError, 'budget'): p.run()
        self.assertEqual((p.snapshot()['STATUS'], p._state.execution.variables.bindings, p._state.execution.variables.metadata), (77, {}, {}))

    def test_narrow_status_output_does_not_satisfy_integer_reference(self):
        with self.assertRaises(TranslationError): program(create().replace(',status)', ',b)'))

    def test_strict_source_creation_remains_unsupported(self):
        with self.assertRaises(TranslationError): legacy_translate('PROGRAM T VAR status:INTEGER BEGIN ' + create() + ' END T')

    def test_internal_strict_helper_rejects_new_scalar_names_and_aliases(self):
        p, _ = program(prefix='TYPE octet=BYTE signed=SHORT')
        with rt._numeric_scope('strict'):
            for kind in ('BYTE', 'SHORT', 'OCTET', 'SIGNED'):
                with self.subTest(kind=kind): self.assertIsNone(concrete_type(p._state.execution, p._state, 'T', kind, 0, (0, 0, 0), None))
            self.assertEqual(concrete_type(p._state.execution, p._state, 'T', 'ARRAY OF BYTE', 0, (2, 0, 0), None), ('ARRAY', 2, ('BYTE',)))


class DynamicNarrowPersistenceTests(unittest.TestCase):
    def test_rename_namespace_preserves_reference_metadata_and_entry_cache(self):
        p, _ = program(create(pool=-1) + "put(BYNAME('CACHE','ITEM',entry)) prior=entry PAUSE "
            "RENAME_VAR('CACHE','ITEM','RENAMED',status) RENAME_VARS('CACHE','SAVED',status) "
            "GET_VAR(entry,'SAVED','RENAMED',b,status)", cooperative=True, routines='ROUTINE put(value:BYTE) BEGIN value=255 END put')
        with self.assertRaises(rt.KarelPause): p.run()
        ctx = p._state.execution; original = ctx.variables.bindings['CACHE', 'ITEM']
        p.resume(); state = p.snapshot()
        self.assertEqual((state['B'], state['ENTRY']), (255, state['PRIOR']))
        self.assertIs(ctx.variables.bindings['SAVED', 'RENAMED'], original)
        self.assertEqual(ctx.variables.metadata, {('SAVED', 'RENAMED'): {'group': 0, 'memory_pool': -1}})
        self.assertEqual(set(ctx.variables.bindings), {('SAVED', 'RENAMED')})

    def test_context_json_preserves_narrow_scalar_values_markers_and_metadata(self):
        state, ctx = execute(create(pool=-1) + create('SHORT', name='COUNT') + create(name='KNOWN') + "SET_VAR(entry,'CACHE','KNOWN',255,status)")
        saved = json.loads(json.dumps(ctx.to_config()))
        restored = rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(), saved)
        self.assertIs(restored.variables.bindings['CACHE', 'ITEM'].raw(), rt.UNKNOWN_BYTE)
        self.assertIs(restored.variables.bindings['CACHE', 'COUNT'].raw(), rt.UNINITIALIZED)
        self.assertEqual(restored.variables.bindings['CACHE', 'KNOWN'].raw(), 255)

    def test_saved_alias_creation_preserves_type_without_executable_alias_table(self):
        _, ctx = execute(create('octet'), prefix='TYPE octet=BYTE')
        restored = rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        state, _ = execute(create('octet', name='OTHER'), context=restored)
        self.assertEqual(state['STATUS'], 5)
        self.assertEqual(restored.variables.bindings['CACHE', 'ITEM'].spec, ('BYTE',))

    def test_saved_narrow_metadata_validates_before_value_restore(self):
        for kind, payload in (('BYTE', UNKNOWN), ('SHORT', MISSING)):
            for creation in ({'group': 33, 'memory_pool': 0}, {'group': 0, 'memory_pool': 1}):
                with self.subTest(kind=kind, creation=creation), self.assertRaises(ValueError):
                    rt.ExecutionContext.from_config({'variables': [{'program': 'CACHE', 'path': 'ITEM', 'type': [kind], 'value': payload, 'creation': creation}]})

    def test_invalid_saved_scalar_domains_are_rejected(self):
        for kind, value in (('BYTE', -1), ('BYTE', 256), ('SHORT', -32769), ('SHORT', 32768)):
            with self.subTest(kind=kind, value=value), self.assertRaises((ValueError, rt.KarelRuntimeError)):
                rt.ExecutionContext.from_config({'variables': [{'program': 'CACHE', 'path': 'ITEM', 'type': [kind], 'value': value,
                                                                'creation': {'group': 0, 'memory_pool': 0}}]})

    def test_variable_archive_restores_narrow_values_and_creation_policy(self):
        ctx = rt.ExecutionContext(files=rt.MemoryFiles(), variable_archives=rt.VariableArchives())
        _, ctx = execute(create(pool=-1) + create('SHORT', name='COUNT') + "SET_VAR(entry,'CACHE','ITEM',255,status) "
            "SET_VAR(entry,'CACHE','COUNT',-11,status) SAVE('CACHE','FR:CACHE.VR',status) CLEAR('CACHE.VR',status) "
            "LOAD('FR:CACHE.VR',0,status) GET_VAR(entry,'CACHE','ITEM',b,status) GET_VAR(entry,'CACHE','COUNT',small,status)", context=ctx)
        self.assertEqual((ctx.variables.bindings['CACHE', 'ITEM'].raw(), ctx.variables.bindings['CACHE', 'COUNT'].raw()), (255, -11))
        self.assertEqual(ctx.variables.metadata['CACHE', 'ITEM'], {'group': 0, 'memory_pool': -1})

    def test_variable_archive_restores_unknown_byte_and_missing_short(self):
        ctx = rt.ExecutionContext(files=rt.MemoryFiles(), variable_archives=rt.VariableArchives())
        state, _ = execute(create() + create('SHORT', name='COUNT') + "SAVE('CACHE','FR:CACHE.VR',status) "
            "SET_VAR(entry,'CACHE','ITEM',7,status) SET_VAR(entry,'CACHE','COUNT',8,status) LOAD('FR:CACHE.VR',0,status)", context=ctx)
        self.assertEqual(state['STATUS'], 0)
        self.assertIs(ctx.variables.bindings['CACHE', 'ITEM'].raw(), rt.UNKNOWN_BYTE)
        self.assertIs(ctx.variables.bindings['CACHE', 'COUNT'].raw(), rt.UNINITIALIZED)

    def test_archive_creation_policy_mismatch_is_atomic(self):
        ctx = rt.ExecutionContext(files=rt.MemoryFiles(), variable_archives=rt.VariableArchives())
        execute(create(pool=-1) + "SET_VAR(entry,'CACHE','ITEM',7,status) SAVE('CACHE','FR:CACHE.VR',status)", context=ctx)
        ctx.variables.metadata['CACHE', 'ITEM']['memory_pool'] = 0
        ctx.variables.bindings['CACHE', 'ITEM'].set(9)
        state, _ = execute("LOAD('FR:CACHE.VR',0,status)", context=ctx)
        self.assertEqual((state['STATUS'], ctx.variables.bindings['CACHE', 'ITEM'].raw(), ctx.variables.metadata['CACHE', 'ITEM']),
                         (6, 9, {'group': 0, 'memory_pool': 0}))


if __name__ == '__main__': unittest.main()
