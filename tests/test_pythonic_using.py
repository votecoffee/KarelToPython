"""Nested lexical USING paths, namespace choices and retained mutation guards."""
import json
from pathlib import Path
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


TYPES = '''TYPE leaf_t=STRUCTURE value: INTEGER label: STRING[8] ENDSTRUCTURE
branch_t=STRUCTURE child: leaf_t value: INTEGER ready: BOOLEAN ENDSTRUCTURE
root_t=STRUCTURE section: branch_t other: leaf_t value: INTEGER ENDSTRUCTURE'''
DECLARATIONS = '''left,right,child: leaf_t tree: root_t
value,result,index_value,total: INTEGER text: STRING[32] flag: BOOLEAN
items: ARRAY[2] OF leaf_t'''


def compile_program(body, routines='', *, declarations=DECLARATIONS, types=TYPES, constants='',
                    translator=translate, **context):
    result = translator(f'PROGRAM T\n{constants}\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',
                        filename='pythonic_using.kl')
    namespace = {'__name__':'pythonic_using_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](**context), result


def execute(body, **kwargs):
    return compile_program(body, **kwargs)[0].run()


class NestedUsingTests(unittest.TestCase):
    def test_inner_field_wins(self):
        state = execute('USING left DO value=1 USING right DO value=2 ENDUSING ENDUSING')
        self.assertEqual((state['LEFT']['VALUE'], state['RIGHT']['VALUE']), (1,2))

    def test_outer_binding_restored(self):
        state = execute('USING left DO value=1 USING right DO value=2 ENDUSING value=value+3 ENDUSING')
        self.assertEqual((state['LEFT']['VALUE'], state['RIGHT']['VALUE']), (4,2))

    def test_global_binding_restored(self):
        state = execute('value=99 USING left DO USING right DO value=2 ENDUSING ENDUSING result=value')
        self.assertEqual((state['VALUE'],state['RESULT']), (99,99))

    def test_three_levels_and_inherited_outer_fields(self):
        state = execute("USING tree DO value=1 USING section DO value=2 USING child DO value=3 ready=ON label='leaf' text=label ENDUSING ENDUSING ENDUSING")
        section = state['TREE']['SECTION']
        self.assertEqual((state['TREE']['VALUE'],section['VALUE'],section['CHILD']['VALUE']), (1,2,3))
        self.assertEqual((section['READY'], state['TEXT']), (True,'leaf'))
        self.assertEqual(state['FLAG'], {'uninitialized':True})

    def test_rightmost_inner_selector_wins(self):
        state = execute('USING tree DO USING section.child,other DO value=7 ENDUSING ENDUSING')
        self.assertEqual(state['TREE']['OTHER']['VALUE'], 7)
        self.assertEqual(state['TREE']['SECTION']['CHILD']['VALUE'], {'uninitialized':True})

    def test_reversed_inner_selector_priority(self):
        state = execute('USING tree DO USING other,section.child DO value=7 ENDUSING ENDUSING')
        self.assertEqual(state['TREE']['SECTION']['CHILD']['VALUE'], 7)
        self.assertEqual(state['TREE']['OTHER']['VALUE'], {'uninitialized':True})

    def test_inner_uninitialized_field_does_not_fall_back(self):
        program, _ = compile_program('left.value=7 USING left DO USING right DO result=value ENDUSING ENDUSING')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): program.run()

    def test_repeated_same_selector(self):
        self.assertEqual(execute('USING left DO value=1 USING left DO value=value+1 ENDUSING value=value+1 ENDUSING')['LEFT']['VALUE'], 3)

    def test_sequential_inner_scopes_do_not_leak(self):
        state = execute('USING tree DO USING section.child DO value=3 ENDUSING USING other DO value=4 ENDUSING value=5 ENDUSING')
        self.assertEqual((state['TREE']['VALUE'], state['TREE']['OTHER']['VALUE'], state['TREE']['SECTION']['CHILD']['VALUE']), (5,4,3))

    def test_empty_nested_scope_has_no_runtime_initialization_requirement(self):
        state = execute('USING tree DO USING section.child DO ENDUSING ENDUSING')
        self.assertEqual(state['TREE']['SECTION']['CHILD']['VALUE'], {'uninitialized':True})


class QualifiedSelectorTests(unittest.TestCase):
    def test_dotted_selector(self):
        self.assertEqual(execute('USING tree.section.child DO value=7 ENDUSING')['TREE']['SECTION']['CHILD']['VALUE'], 7)

    def test_explicit_and_inherited_selector_are_equivalent(self):
        direct = execute('USING tree.section.child DO value=7 ENDUSING')
        nested = execute('USING tree DO USING section DO USING child DO value=7 ENDUSING ENDUSING ENDUSING')
        self.assertEqual(direct, nested)

    def test_outer_field_selector_wins_over_global_variable(self):
        state = execute('USING tree.section DO USING child DO value=7 ENDUSING ENDUSING')
        self.assertEqual(state['TREE']['SECTION']['CHILD']['VALUE'], 7)
        self.assertEqual(state['CHILD']['VALUE'], {'uninitialized':True})

    def test_selector_list_does_not_use_its_own_new_fields(self):
        types = 'TYPE leaf_t=STRUCTURE value: INTEGER ENDSTRUCTURE\nholder_t=STRUCTURE right: leaf_t ENDSTRUCTURE'
        state = execute('USING left,right DO value=7 ENDUSING', types=types, declarations='left: holder_t right: leaf_t')
        self.assertEqual(state['RIGHT']['VALUE'], 7)
        self.assertEqual(state['LEFT']['RIGHT']['VALUE'], {'uninitialized':True})

    def test_inserted_root_is_not_reinterpreted_in_inner_scope(self):
        types = 'TYPE leaf_t=STRUCTURE value: INTEGER ENDSTRUCTURE\nholder_t=STRUCTURE left: leaf_t ENDSTRUCTURE'
        state = execute('USING left DO USING right DO value=7 ENDUSING ENDUSING', types=types, declarations='left: holder_t right: leaf_t')
        self.assertEqual(state['RIGHT']['VALUE'], 7)
        self.assertEqual(state['LEFT']['LEFT']['VALUE'], {'uninitialized':True})

    def test_same_list_unknown_selector_does_not_find_an_introduced_field(self):
        types = 'TYPE leaf_t=STRUCTURE value: INTEGER ENDSTRUCTURE\nholder_t=STRUCTURE right: leaf_t ENDSTRUCTURE'
        with self.assertRaises(TranslationError) as caught:
            compile_program('USING left,right DO ENDUSING', types=types, declarations='left: holder_t')
        self.assertEqual(caught.exception.code, 'E_SYMBOL')

    def test_dotted_selector_parameter(self):
        routine = 'ROUTINE edit(p: root_t) BEGIN USING p.section.child DO value=7 ENDUSING END edit'
        self.assertEqual(execute('edit(tree)', routines=routine)['TREE']['SECTION']['CHILD']['VALUE'], 7)

    def test_dotted_selector_local(self):
        routine = 'ROUTINE work VAR p: root_t BEGIN USING p.section.child DO value=7 result=value ENDUSING END work'
        self.assertEqual(execute('work', routines=routine)['RESULT'], 7)

    def test_whole_structure_copy_keeps_alias_storage(self):
        body = "right.value=9 right.label='new' USING tree.section.child DO value=1 label='old' tree.section.child=right result=value text=label ENDUSING"
        state = execute(body)
        self.assertEqual((state['RESULT'],state['TEXT']), (9,'new'))


class UsingNamespaceTests(unittest.TestCase):
    def test_global_constant_shadowed_only_inside_scope(self):
        state = execute('USING left DO value=7 result=value ENDUSING total=value', constants='CONST value=99',
                        declarations='left: leaf_t result,total: INTEGER')
        self.assertEqual((state['LEFT']['VALUE'],state['RESULT'],state['TOTAL']), (7,7,99))

    def test_local_constant_shadowed_only_inside_scope(self):
        routine = 'ROUTINE work CONST value=99 BEGIN USING left DO value=7 result=value ENDUSING total=value END work'
        state = execute('work', routines=routine, declarations='left: leaf_t result,total: INTEGER')
        self.assertEqual((state['RESULT'],state['TOTAL']), (7,99))

    def test_explicit_function_call_and_bare_field(self):
        routine = 'ROUTINE value: INTEGER BEGIN RETURN 42 END value'
        state = execute('USING left DO value=7 result=value+value() ENDUSING', routines=routine,
                        declarations='left: leaf_t result: INTEGER')
        self.assertEqual((state['LEFT']['VALUE'],state['RESULT']), (7,49))

    def test_bare_function_restored_outside_scope(self):
        routine = 'ROUTINE value: INTEGER BEGIN RETURN 42 END value'
        state = execute('USING left DO value=7 result=value ENDUSING total=value', routines=routine,
                        declarations='left: leaf_t result,total: INTEGER')
        self.assertEqual((state['RESULT'],state['TOTAL']), (7,42))

    def test_procedure_call_statement_uses_call_context(self):
        routine = 'ROUTINE value BEGIN result=42 END value'
        state = execute('USING left DO value=7 value ENDUSING', routines=routine,
                        declarations='left: leaf_t result: INTEGER')
        self.assertEqual((state['LEFT']['VALUE'],state['RESULT']), (7,42))

    def test_explicit_procedure_call_arguments_resolve_fields(self):
        routine = 'ROUTINE value(p: INTEGER) BEGIN result=p END value'
        self.assertEqual(execute('USING left DO value=7 value(value) ENDUSING', routines=routine,
                                 declarations='left: leaf_t result: INTEGER')['RESULT'], 7)

    def test_local_selector_shadows_same_named_function(self):
        routine = 'ROUTINE left: INTEGER BEGIN result=99 RETURN 42 END left\nROUTINE work VAR left: leaf_t BEGIN USING left DO value=7 ENDUSING result=left.value END work'
        program, result = compile_program('work', routines=routine, declarations='result: INTEGER')
        self.assertEqual(program.run()['RESULT'], 7)
        self.assertEqual(result.report['bare_function_calls'], [])

    def test_noncolliding_case_constant_still_works(self):
        state = execute('USING left DO value=1 SELECT value OF CASE(wanted): result=value ENDSELECT ENDUSING', constants='CONST wanted=1')
        self.assertEqual(state['RESULT'], 1)

    def test_shadowed_case_label_is_not_a_runtime_case(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('USING left DO SELECT result OF CASE(value): result=7 ENDSELECT ENDUSING', constants='CONST value=7',
                            declarations='left: leaf_t result: INTEGER')
        self.assertEqual(caught.exception.code, 'E_CONSTANT')

    def test_unknown_call_still_rejected(self):
        with self.assertRaises(TranslationError) as caught: compile_program('USING left DO value() ENDUSING')
        self.assertEqual(caught.exception.code, 'E_CALL')


class UsingEffectsAndControlTests(unittest.TestCase):
    def test_nested_alias_passes_writable_reference(self):
        routine = 'ROUTINE put(p: INTEGER) BEGIN p=7 END put'
        state = execute('USING tree DO USING section.child DO put(value) ENDUSING ENDUSING', routines=routine)
        self.assertEqual(state['TREE']['SECTION']['CHILD']['VALUE'], 7)

    def test_callee_does_not_inherit_caller_scope(self):
        routine = 'ROUTINE read_global BEGIN result=value END read_global'
        state = execute('value=99 USING tree DO USING section.child DO value=7 read_global ENDUSING ENDUSING', routines=routine)
        self.assertEqual(state['RESULT'], 99)

    def test_nested_formal_effect_report(self):
        routines = 'ROUTINE put(p: INTEGER) BEGIN p=7 END put\nROUTINE edit(p: root_t) BEGIN USING p DO USING section.child DO put(value) ENDUSING ENDUSING END edit'
        program, result = compile_program('edit(tree)', routines=routines)
        self.assertEqual(program.run()['TREE']['SECTION']['CHILD']['VALUE'], 7)
        self.assertEqual(result.report['routine_effects']['EDIT']['potential_parameter_writes'], ['P'])

    def test_nested_global_effect_report(self):
        routine = 'ROUTINE edit BEGIN USING tree DO USING section.child DO value=7 ENDUSING ENDUSING END edit'
        _, result = compile_program('edit', routines=routine)
        self.assertEqual(result.report['routine_effects']['EDIT']['potential_global_writes'], ['TREE'])

    def test_field_named_like_counter_is_different_storage(self):
        state = execute('FOR value=1 TO 2 DO USING tree.section.child DO value=7 ENDUSING ENDFOR')
        self.assertEqual(state['TREE']['SECTION']['CHILD']['VALUE'], 7)
        self.assertEqual(state['VALUE'], {'uninitialized':True})

    def test_callee_counter_write_not_hidden_by_field_alias(self):
        routine = 'ROUTINE change BEGIN value=99 END change'
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR value=1 TO 2 DO USING tree.section.child DO change ENDUSING ENDFOR', routines=routine)
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')

    def test_inherited_field_cannot_be_for_counter(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('USING tree DO USING section.child DO FOR value=1 TO 2 DO ENDFOR ENDUSING ENDUSING')
        self.assertEqual(caught.exception.code, 'E_USING_FOR_COUNTER')

    def test_nested_for_reads_and_updates_fields(self):
        state = execute('USING tree DO USING section.child DO value=0 FOR index_value=1 TO 3 DO value=value+index_value ENDFOR ENDUSING ENDUSING')
        self.assertEqual(state['TREE']['SECTION']['CHILD']['VALUE'], 6)

    def test_return_from_nested_scopes(self):
        routine = 'ROUTINE first: INTEGER BEGIN USING tree DO USING section.child DO value=7 RETURN value ENDUSING ENDUSING RETURN 0 END first'
        program, _ = compile_program('result=first()', routines=routine)
        self.assertEqual(program.run()['RESULT'], 7)
        self.assertEqual((program._state.local_frames,program._state.call_depth), ([],0))

    def test_error_preserves_prior_field_writes_and_unwinds_frames(self):
        routine = 'ROUTINE work BEGIN USING tree DO USING section.child DO value=7 result=1 DIV 0 ENDUSING ENDUSING END work'
        program, _ = compile_program('work', routines=routine)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['TREE']['SECTION']['CHILD']['VALUE'], 7)
        self.assertEqual((program._state.local_frames,program._state.call_depth), ([],0))

    def test_abort_inside_nested_scopes(self):
        routine = 'ROUTINE work BEGIN USING tree DO USING section.child DO value=7 ABORT ENDUSING ENDUSING END work'
        program, _ = compile_program('work', routines=routine)
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['TREE']['SECTION']['CHILD']['VALUE'], 7)
        self.assertEqual((program._state.local_frames,program._state.call_depth), ([],0))

    def test_jump_out_of_inner_scope_restores_outer_binding(self):
        state = execute('USING tree DO value=1 USING section.child DO value=2 GOTO done value=99 ENDUSING done:: value=value+3 ENDUSING')
        self.assertEqual((state['TREE']['VALUE'],state['TREE']['SECTION']['CHILD']['VALUE']), (4,2))

    def test_jump_into_nested_scope_still_rejected(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('GOTO inside USING tree DO USING section.child DO inside:: value=7 ENDUSING ENDUSING')
        self.assertEqual(caught.exception.code, 'E_GOTO_ENTRY')


class UsingBoundaryAndReportTests(unittest.TestCase):
    def test_unsupported_selector_forms_remain_blocked(self):
        for selector in ('items[1]', 'tree.section.child[1]', 'make()', 'tree.section.child()'):
            with self.subTest(selector=selector), self.assertRaises(TranslationError) as caught:
                compile_program(f'USING {selector} DO ENDUSING')
            self.assertEqual(caught.exception.code, 'E_USING_TARGET')

    def test_grouped_selector_remains_blocked(self):
        with self.assertRaises(TranslationError): compile_program('USING (left) DO ENDUSING')

    def test_scalar_array_and_builtin_records_not_selectors(self):
        for name, declaration in [('n','INTEGER'), ('n','ARRAY[1] OF INTEGER'), ('n','VECTOR'), ('n','XYZWPR')]:
            with self.subTest(declaration=declaration), self.assertRaises(TranslationError) as caught:
                compile_program('USING n DO ENDUSING', declarations=f'n: {declaration}')
            self.assertEqual(caught.exception.code, 'E_USING_TYPE')

    def test_missing_field_has_source_diagnostic(self):
        with self.assertRaises(TranslationError) as caught: compile_program('USING tree.missing DO ENDUSING')
        self.assertEqual(caught.exception.code, 'E_FIELD')
        self.assertEqual(caught.exception.filename, 'pythonic_using.kl')

    def test_field_type_checks_remain(self):
        with self.assertRaises(TranslationError) as caught: compile_program("USING tree.section.child DO value='bad' ENDUSING")
        self.assertEqual(caught.exception.code, 'E_TYPE')

    def test_scope_report_records_parent_and_paths(self):
        _, result = compile_program('USING tree DO USING section.child DO value=7 ENDUSING ENDUSING')
        scopes = json.loads(json.dumps(result.report))['using_scopes']
        self.assertEqual([(row['id'],row['parent'],row['depth']) for row in scopes], [(0,None,0),(1,0,1)])
        self.assertEqual(scopes[1]['source_selectors'], ['SECTION.CHILD'])
        self.assertEqual(scopes[1]['variables'], ['TREE.SECTION.CHILD'])
        self.assertEqual(scopes[1]['field_bindings']['VALUE'], 'TREE.SECTION.CHILD')
        self.assertEqual(scopes[1]['resolved_uses'][0]['variable'], 'TREE.SECTION.CHILD')
        self.assertIn('nested USING lexical scope', result.report['features'])
        self.assertFalse(result.report['using_policy']['controller_validated'])

    def test_sibling_scope_ids_and_depth(self):
        _, result = compile_program('USING tree DO USING section.child DO ENDUSING USING other DO ENDUSING ENDUSING')
        self.assertEqual([(row['id'],row['parent'],row['depth']) for row in result.report['using_scopes']], [(0,None,0),(1,0,1),(2,0,1)])

    def test_legacy_guards_remain_internal(self):
        for body in ('USING tree.section.child DO value=7 ENDUSING', 'USING left DO USING right DO value=7 ENDUSING ENDUSING'):
            with self.subTest(body=body), self.assertRaises(TranslationError): compile_program(body, translator=legacy_translate)

    def test_legacy_namespace_guards_remain_internal(self):
        for body, options in [('USING left DO value=7 ENDUSING', dict(constants='CONST value=99', declarations='left: leaf_t')),
                              ('USING left DO result=value() ENDUSING', dict(routines='ROUTINE value: INTEGER BEGIN RETURN 42 END value', declarations='left: leaf_t result: INTEGER'))]:
            with self.subTest(body=body), self.assertRaises(TranslationError): compile_program(body, translator=legacy_translate, **options)

    def test_authored_example_matches_complete_fixtures(self):
        source = Path(__file__).resolve().parents[1]/'examples/pythonic_using.kl'
        result = translate(source.read_text(), filename=source.name)
        namespace = {'__name__':'using_fixture'}
        exec(result.python_source, namespace)
        observed = []
        program = namespace['Program'](write=observed.append)
        self.assertEqual(program.run(), json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(observed, json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual((program._state.local_frames,program._state.call_depth), ([],0))
