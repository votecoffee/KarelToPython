"""Authored bounded STRING source interfaces over existing checked storage."""
import ast
import json
from pathlib import Path
import unittest

from karel2py import translate,translate_project,load_project,runtime as rt
from karel2py.input_discovery import discover_inputs
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


U={'uninitialized':True}
ROOT=Path(__file__).resolve().parents[1]


def build(body='edit(text)',*,decl='text:STRING[3] seen:STRING[10] calls:INTEGER',routines='',prefix=''):
    result=translate(f'PROGRAM T\n{prefix}\nVAR {decl}\n{routines}\nBEGIN {body} END T',filename='authored.kl')
    ast.parse(result.python_source,feature_version=(3,11));json.dumps(result.report,allow_nan=False)
    namespace={'__name__':'bounded_string_test'};exec(result.python_source,namespace)
    return namespace['Program'](),result


class BoundedScalarStringTests(unittest.TestCase):
    EDIT="ROUTINE edit(p:STRING[3]) BEGIN p='abcdef' seen=p END edit"

    def test_matching_bare_storage_keeps_capacity_and_alias(self):
        program,result=build(routines=self.EDIT)
        self.assertEqual(program.run(),{'TEXT':'abc','SEEN':'abc','CALLS':U})
        self.assertEqual(result.report['string_formal_uses'][0]['capacity'],3)

    def test_literals_constants_grouped_values_and_results_are_private(self):
        for argument in ("'abcdef'",'label','(text)','make()'):
            with self.subTest(argument=argument):
                program,result=build("text='old' edit("+argument+')',prefix="CONST label='abcdef'",
                    routines=self.EDIT+" ROUTINE make:STRING[6] BEGIN RETURN 'abcdef' END make")
                values=program.run();self.assertEqual((values['TEXT'],values['SEEN']),('old','abc'))
                self.assertEqual(result.report['string_value_arguments'][-1]['temporary_capacity'],3)

    def test_value_is_truncated_before_body_and_remains_bounded(self):
        program,_=build("edit('abcdef')",routines="ROUTINE edit(p:STRING[3]) BEGIN seen=p p='uvwxyz' text=p END edit")
        values=program.run();self.assertEqual((values['SEEN'],values['TEXT']),('abc','uvw'))

    def test_known_mismatched_bare_scalar_capacity_still_rejects(self):
        with self.assertRaises(TranslationError) as caught:build(decl='text:STRING[4] seen:STRING[10]',routines=self.EDIT)
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_grouping_mismatched_capacity_copies_without_writeback(self):
        program,_=build("text='wide' edit((text))",decl='text:STRING[4] seen:STRING[10]',routines=self.EDIT)
        self.assertEqual(program.run(),{'TEXT':'wide','SEEN':'abc'})

    def test_alias_and_direct_scalar_signatures_resolve_identically(self):
        program,result=build(prefix='TYPE text_t=STRING[3]',routines=self.EDIT.replace('STRING[3]','text_t'))
        self.assertEqual(program.run()['TEXT'],'abc')
        self.assertEqual(result.report['string_formal_uses'],[])

    def test_module_forward_constants_pure_calls_and_newlines_define_capacity(self):
        program,result=build(prefix='CONST width=STR_LEN(label) label=\'abc\'',routines=self.EDIT.replace('[3]','[\nwidth\n]'))
        self.assertEqual(program.run()['TEXT'],'abc')
        self.assertEqual(result.report['string_formal_uses'][0]['interface_scope'],'module')

    def test_capacity_endpoints_are_valid(self):
        for size in (1,254):
            with self.subTest(size=size):
                program,_=build('edit(text)',decl=f'text:STRING[{size}]',routines=f"ROUTINE edit(p:STRING[{size}]) BEGIN p='abcd' END edit")
                self.assertEqual(program.run()['TEXT'],'abcd'[:size])

    def test_value_limit_is_checked_before_truncation_and_frame_entry(self):
        program,_=build("text='old' edit('"+'x'*128+"'+'"+'y'*127+"')",routines=self.EDIT)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'254 characters'):program.run()
        self.assertEqual(program.snapshot()['TEXT'],'old');self.assertEqual(program._state.call_depth,0)

    def test_pause_resume_and_stop_retain_the_original_borrowed_cell(self):
        routine="ROUTINE edit(p:STRING[3]) BEGIN p='one' PAUSE p='two' END edit"
        program,_=build(routines=routine)
        with self.assertRaises(rt.KarelPause):program.run()
        self.assertEqual(program.snapshot()['TEXT'],'one');self.assertEqual(program.resume()['TEXT'],'two')
        stopped,_=build(routines=routine)
        with self.assertRaises(rt.KarelPause):stopped.run()
        stopped.stop();self.assertEqual(stopped.snapshot()['TEXT'],'one');self.assertEqual(stopped._state.call_depth,0)

    def test_parameter_field_writes_cannot_alias_an_active_aggregate_counter(self):
        with self.assertRaises(TranslationError) as caught:
            build('FOR row.count=1 TO 2 DO edit(row.label) ENDFOR',decl='row:item_t',
                prefix='TYPE item_t=STRUCTURE count:INTEGER label:STRING[3] ENDSTRUCTURE',
                routines="ROUTINE edit(p:STRING[3]) BEGIN p='one' END edit")
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')


class BoundedStringForwardingTests(unittest.TestCase):
    ROUTINES="ROUTINE inner(p:STRING[3]) BEGIN p='abcdef' seen=p END inner ROUTINE outer(p:STRING) BEGIN calls=1 inner(p) END outer"

    def test_unknown_borrowed_capacity_is_checked_and_alias_is_retained(self):
        program,result=build('outer(text)',routines=self.ROUTINES)
        self.assertEqual(program.run(),{'TEXT':'abc','SEEN':'abc','CALLS':1})
        row=result.report['string_forward_uses'][0]
        self.assertTrue(row['alias_retained']);self.assertEqual((row['body'],row['routine']),('OUTER','INNER'))
        self.assertEqual(result.report['array_forward_uses'],[])

    def test_wrong_concrete_capacity_fails_before_inner_body(self):
        program,_=build("text='wide' outer(text)",decl='text:STRING[4] seen:STRING[10] calls:INTEGER',routines=self.ROUTINES)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Parameter binding'):program.run()
        self.assertEqual(program.snapshot(),{'TEXT':'wide','SEEN':U,'CALLS':1})
        self.assertEqual(program._state.call_depth,0)

    def test_grouped_forwarding_is_private_and_uses_the_bounded_capacity(self):
        program,result=build("text='wide' outer(text)",decl='text:STRING[4] seen:STRING[10] calls:INTEGER',
            routines=self.ROUTINES.replace('inner(p) END outer','inner((p)) END outer'))
        self.assertEqual(program.run(),{'TEXT':'wide','SEEN':'abc','CALLS':1})
        self.assertEqual(result.report['string_forward_uses'],[])

    def test_direct_and_alias_targets_share_the_same_concrete_guard(self):
        program,result=build('outer(text)',prefix='TYPE text_t=STRING[3]',routines=self.ROUTINES.replace('STRING[3]','text_t'))
        self.assertEqual(program.run()['TEXT'],'abc');self.assertTrue(result.report['string_forward_uses'])

    def test_byname_capacity_mismatch_preserves_entry_and_original_value(self):
        program,_=build("calls=99 text='wide' inner(BYNAME('','TEXT',calls))",decl='text:STRING[4] seen:STRING[10] calls:INTEGER',routines=self.ROUTINES)
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual(program.snapshot(),{'TEXT':'wide','SEEN':U,'CALLS':99})

    def test_later_argument_effect_precedes_the_concrete_entry_guard(self):
        routines="ROUTINE inner(p:STRING[3];q:INTEGER) BEGIN seen='body' END inner ROUTINE touch:INTEGER BEGIN calls=7 RETURN 1 END touch ROUTINE outer(p:STRING) BEGIN inner(p,touch()) END outer"
        program,_=build('outer(text)',decl='text:STRING[4] seen:STRING[10] calls:INTEGER',routines=routines)
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual(program.snapshot()['CALLS'],7);self.assertEqual(program.snapshot()['SEEN'],U)

    def test_runtime_compatibility_helper_remains_exact(self):
        self.assertFalse(rt.parameter_accepts(('STRING',3),('STRING',None)))
        self.assertFalse(rt.parameter_accepts(('STRING',3),('STRING',4)))

    def test_input_discovery_retains_matching_alias_writes(self):
        _,result=build('outer(text)',routines=self.ROUTINES)
        report=discover_inputs(result.python_source)
        self.assertTrue(report['complete'],report['unresolved']);self.assertEqual(report['inputs'],[])

    def test_input_discovery_reports_wrong_capacity_without_callee_write_proofs(self):
        _,result=build('outer(text) calls=n',decl='text:STRING[4] seen:STRING[10] calls,n:INTEGER',
            routines=self.ROUTINES.replace("p='abcdef' seen=p","n=7"))
        report=discover_inputs(result.python_source)
        self.assertTrue(any(row['code']=='parameter-capacity' for row in report['unresolved']))
        self.assertEqual([(row['path'],row['certainty']) for row in report['inputs']],[('N','conditional')])


class BoundedStringArrayTests(unittest.TestCase):
    def test_matching_scalar_element_capacity_and_mixed_sizes_borrow_original(self):
        program,result=build('edit(data)',decl='data:ARRAY[2,2]OF STRING[3]',
            routines="ROUTINE edit(p:ARRAY[2,*]OF STRING[3]) BEGIN p[2,2]='abcdef' END edit")
        self.assertEqual(program.run()['DATA'],[[U,U],[U,'abc']])
        self.assertEqual(result.report['string_formal_uses'][0]['container'],'ARRAY')

    def test_different_array_capacity_uses_existing_private_schema_conversion(self):
        program,result=build("data[1]='wide' edit(data)",decl='data:ARRAY[2]OF STRING[4] seen:STRING[10]',
            routines="ROUTINE edit(p:ARRAY OF STRING[3]) BEGIN seen=p[1] p[1]='edit' END edit")
        self.assertEqual(program.run(),{'DATA':['wide',U],'SEEN':'wid'})
        self.assertEqual(result.report['array_value_arguments'][0]['conversion_kind'],'array_schema')

    def test_grouped_partial_array_preserves_missing_data_and_ownership(self):
        program,_=build("data[1]='old' edit((data))",decl='data:ARRAY[2]OF STRING[3] seen:STRING[10]',
            routines="ROUTINE edit(p:ARRAY OF STRING[3]) BEGIN p[2]='new' seen=p[2] END edit")
        self.assertEqual(program.run(),{'DATA':['old',U],'SEEN':'new'})

    def test_inline_layers_and_named_source_components_keep_logical_dimensions(self):
        program,_=build('edit(data)',prefix='TYPE row_t=ARRAY[2]OF STRING[3]',decl='data:ARRAY[1]OF row_t',
            routines="ROUTINE edit(p:ARRAY[1]OF ARRAY[*]OF STRING[3]) BEGIN p[1,2]='hello' END edit")
        self.assertEqual(program.run()['DATA'],[[U,'hel']])

    def test_unbounded_string_array_forwarding_retains_existing_private_cast(self):
        program,result=build("data[1]='old' outer(data)",decl='data:ARRAY[1]OF STRING[3] seen:STRING[10]',routines="""
            ROUTINE inner(p:ARRAY OF STRING[3]) BEGIN p[1]='new' seen=p[1] END inner
            ROUTINE outer(p:ARRAY OF STRING) BEGIN inner(p) END outer""")
        self.assertEqual(program.run(),{'DATA':['old'],'SEEN':'new'})
        self.assertEqual(result.report['string_forward_uses'],[])

    def test_input_discovery_keeps_bounded_shapes_and_conservative_truncation(self):
        _,result=build("data[1]='old' edit((data))",decl='data:ARRAY[1]OF STRING[3] x,n:INTEGER',
            routines="ROUTINE edit(p:ARRAY OF STRING[3]) BEGIN p[1]='abcd' IF p[1]='abc' THEN n=x ENDIF END edit")
        report=discover_inputs(result.python_source)
        self.assertTrue(report['complete'],report['unresolved'])
        self.assertEqual([(row['path'],row['certainty']) for row in report['inputs']],[('X','conditional')])


class BoundedStringGuardsAndLinkTests(unittest.TestCase):
    def test_authored_standalone_and_linked_examples(self):
        from tools.run_examples import run_example
        for name in ('bounded_string_parameters','bounded_string_array_parameters'):
            with self.subTest(name=name):run_example(ROOT/'examples'/(name+'.kl'))
        folder=ROOT/'examples/bounded_string_formals_linked'
        instance=load_project(folder).instantiate();expected=json.loads((folder/'expected.json').read_bytes())
        self.assertEqual(instance.run('MAIN'),expected);self.assertEqual(instance.run('MAIN'),expected)

    def test_invalid_capacities_reject_with_existing_storage_domain(self):
        for capacity in ('0','255','-1','1.5','TRUE'):
            for formal in ('STRING['+capacity+']','ARRAY[2,*]OF STRING['+capacity+']'):
                with self.subTest(formal=formal):
                    with self.assertRaises(TranslationError) as caught:build('',routines=f'ROUTINE edit(p:{formal}) BEGIN END edit')
                    self.assertEqual(caught.exception.code,'E_SIZE')

    def test_interface_scope_excludes_unknown_local_and_caller_names(self):
        for prefix,routines in (('', 'ROUTINE edit(p:STRING[width]) BEGIN END edit'),
                ('','ROUTINE edit(p:STRING[width]) CONST width=3 BEGIN END edit')):
            with self.subTest(routines=routines):
                with self.assertRaises(TranslationError) as caught:build('',prefix=prefix,routines=routines)
                self.assertEqual(caught.exception.code,'E_CONSTANT')

    def test_legacy_direct_capacities_still_reject(self):
        for spec in ('STRING[3]','ARRAY OF STRING[3]'):
            with self.subTest(spec=spec):
                with self.assertRaises(TranslationError) as caught:legacy_translate(f'PROGRAM T ROUTINE edit(p:{spec}) BEGIN END edit BEGIN END T')
                self.assertEqual(caught.exception.code,'E_PARAMETERS')

    def test_direct_and_alias_linked_signatures_match_after_resolution(self):
        sources={'main':'PROGRAM MAIN VAR text:STRING[3] ROUTINE edit(p:STRING[3]) FROM LIB BEGIN edit(text) END MAIN',
            'lib':"PROGRAM LIB TYPE text_t=STRING[3] ROUTINE edit(p:text_t) BEGIN p='abcdef' END edit BEGIN END LIB"}
        self.assertEqual(translate_project(sources).instantiate().run('MAIN')['MAIN']['values']['TEXT'],'abc')

    def test_different_linked_capacities_still_reject(self):
        sources={'main':'PROGRAM MAIN ROUTINE edit(p:STRING[3]) FROM LIB BEGIN END MAIN',
            'lib':'PROGRAM LIB ROUTINE edit(p:STRING[4]) BEGIN END edit BEGIN END LIB'}
        with self.assertRaisesRegex(ValueError,'mismatch'):translate_project(sources).instantiate()

    def test_physical_include_origins_and_scoped_metadata(self):
        result=translate('PROGRAM T\n%INCLUDE routines.inc\nBEGIN END T',filename='main.kl',
            includes={'routines.inc':'ROUTINE edit(p:STRING[3]) BEGIN END edit'})
        row=result.report['string_formal_uses'][0]
        self.assertEqual((row['source_file'],row['source_line'],row['capacity']),('routines.inc',1,3))
        self.assertFalse(result.report['string_formal_policy']['controller_validated'])


if __name__=='__main__':unittest.main()
