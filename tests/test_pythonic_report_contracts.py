"""Public report claims agree with executable Pythonic forms and retained guards."""
import json
from pathlib import Path
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate

ROOT=Path(__file__).resolve().parents[1]


def build(body='',decl='n:INTEGER',prefix='',routines=''):
    result=translate(f'PROGRAM T {prefix} VAR {decl} {routines} BEGIN {body} END T')
    namespace={'__name__':'report_contract_test'};exec(result.python_source,namespace)
    return namespace['Program'](),result.report


def descriptions(report):return {row['id']:row['description'] for row in report['limitation_details']}


class ExecutedReportClaims(unittest.TestCase):
    def test_writable_string_value_arguments_are_already_supported(self):
        program,report=build("text='old' work((text))",decl='text,answer:STRING[8]',
            routines="ROUTINE work(value:STRING) BEGIN value=value+'x' answer=value END work")
        self.assertEqual(program.run(),{'TEXT':'old','ANSWER':'oldx'})
        self.assertIn('writable',report['string_value_policy']['storage'])
        self.assertIn('writable',descriptions(report)['strings'])
        self.assertNotIn('require read-only formals',' '.join(report['limitations']))

    def test_partial_record_copy_is_reported_as_supported(self):
        program,report=build('source.first=7 target=source',decl='source,target:item_t',
                            prefix='TYPE item_t=STRUCTURE first:INTEGER second:INTEGER ENDSTRUCTURE')
        snapshot=program.run();self.assertEqual(snapshot['TARGET'],{'FIRST':7,'SECOND':{'uninitialized':True}})
        self.assertIn('preserve',descriptions(report)['initialization'])
        self.assertNotIn('Whole-structure copying requires every scalar leaf initialized',' '.join(report['limitations']))

    def test_partial_array_private_argument_keeps_caller_unchanged(self):
        program,report=build('source[1]=3 work((source))',decl='source:ARRAY[2]OF INTEGER n:INTEGER',
            routines='ROUTINE work(value:ARRAY OF INTEGER) BEGIN value[2]=9 n=value[1]+value[2] END work')
        snapshot=program.run();self.assertEqual(snapshot['N'],12)
        self.assertEqual(snapshot['SOURCE'],[3,{'uninitialized':True}])
        self.assertNotIn('require every scalar leaf known and initialized',' '.join(report['limitations']))

    def test_partial_record_return_uses_declared_receiver_and_preserves_missing(self):
        program,report=build('target=make()',decl='target:item_t',
            prefix='TYPE item_t=STRUCTURE first:INTEGER second:INTEGER ENDSTRUCTURE',
            routines='ROUTINE make:item_t VAR value:item_t BEGIN value.first=5 RETURN value END make')
        self.assertEqual(program.run()['TARGET'],{'FIRST':5,'SECOND':{'uninitialized':True}})
        self.assertIn('missing',report['structure_routine_policy']['results'])

    def test_forward_types_and_constants_are_resolved_before_execution(self):
        program,report=build('value.child.number=FIRST n=value.child.number',decl='value:outer_t n:INTEGER',
            prefix='CONST FIRST=LATER+1 LATER=6 TYPE outer_t=STRUCTURE child:inner_t ENDSTRUCTURE inner_t=STRUCTURE number:INTEGER ENDSTRUCTURE')
        self.assertEqual(program.run()['N'],7)
        self.assertIn('acyclic',descriptions(report)['types'])
        self.assertNotIn('TYPE aliases resolve prior definitions transparently',' '.join(report['limitations']))

    def test_nested_and_sibling_jumps_do_not_retain_old_report_prohibition(self):
        program,report=build('n=0 GOTO chosen IF TRUE THEN n=99 ELSE chosen:: n=7 ENDIF')
        self.assertEqual(program.run()['N'],7)
        text=descriptions(report)['control_transfers']
        self.assertIn('nested/sibling',text);self.assertIn('unstarted FOR',text)
        self.assertNotIn('entry into nested or sibling blocks is blocked',' '.join(report['limitations']))

    def test_for_exit_clears_original_counter_and_keeps_body_scope_limit(self):
        program,report=build('n=0 FOR counter=1 TO 3 DO n=n+counter GOTO done ENDFOR done:: cleared=UNINIT(counter)',
            decl='counter,n:INTEGER cleared:BOOLEAN')
        snapshot=program.run();self.assertEqual((snapshot['N'],snapshot['CLEARED']),(1,True))
        self.assertIn('program/routine body',descriptions(report)['control_transfers'])

    def test_named_numeric_array_conversion_preserves_target_schema(self):
        program,report=build('source[1]=1 source[2]=2 target=source',decl='source:source_t target:target_t',
            prefix='TYPE source_t=ARRAY[2]OF INTEGER target_t=ARRAY[2]OF REAL')
        self.assertEqual(program.run()['TARGET'],[1.,2.])
        self.assertTrue(all(type(item) is float for item in program._state.values['TARGET'].values))
        self.assertIn('conversions',descriptions(report)['array_storage'])
        self.assertNotIn('Whole-array assignment requires identical concrete types and sizes at runtime',' '.join(report['limitations']))

    def test_nominal_record_source_conversion_is_not_reported_as_generic_coercion(self):
        program,report=build('source.value=7 target=source',decl='source:source_t target:target_t',
            prefix='TYPE source_t=STRUCTURE value:INTEGER ENDSTRUCTURE target_t=STRUCTURE value:REAL ENDSTRUCTURE')
        self.assertEqual(program.run()['TARGET'],{'VALUE':7.})
        self.assertIn('source conversions',report['structure_routine_policy']['limits'])
        self.assertIn('linked-interface',descriptions(report)['reference_guards'])

    def test_cartesian_argument_return_and_array_conversions_match_scope(self):
        program,report=build("CNV_STR_CONF('N',cfg,s) source[1]=POS(1,2,3,0,0,0,cfg) target=source matrix=convert(source[1])",
            decl='cfg:CONFIG s:INTEGER source:ARRAY[1]OF XYZWPR target:ARRAY[1]OF POSITION matrix:POSITION',
            routines='ROUTINE convert(value:XYZWPR):POSITION BEGIN RETURN value END convert')
        snapshot=program.run();self.assertEqual(snapshot['TARGET'][0]['LOCATION']['X'],1.)
        self.assertEqual(snapshot['MATRIX']['LOCATION']['Z'],3.)
        policy=report['position_conversion_policy'];self.assertIn('RETURNs',policy['scope']);self.assertIn('ARRAY',policy['scope'])
        self.assertNotIn('whole arrays, BYNAME',policy['boundary'])

    def test_formatted_negative_real_and_cr_output_remain_supported(self):
        program,report=build('WRITE(-2::3,0.25::5::2,CR)')
        program.run();text=program.write_requests[0]['text']
        self.assertIn('-2',text);self.assertIn('0.25',text);self.assertTrue(text.endswith('\n'))
        self.assertNotIn('negative INTEGER/REAL output',' '.join(report['limitations']))

    def test_integer_conversion_accepts_user_call_arguments(self):
        program,report=build('visits=0 CNV_INT_STR(31,width(),base(),text)',decl='visits:INTEGER text:STRING[8]',
            routines='ROUTINE base:INTEGER BEGIN visits=visits+1 RETURN 16 END base ROUTINE width:INTEGER BEGIN visits=visits+1 RETURN 2 END width')
        snapshot=program.run();self.assertEqual(snapshot['VISITS'],2);self.assertEqual(snapshot['TEXT'].strip(),'1F')
        self.assertNotIn('argument user calls and active counter writes are blocked',' '.join(report['limitations']))


class RetainedReportGuards(unittest.TestCase):
    def test_public_strict_mode_remains_future(self):
        with self.assertRaises(TranslationError):translate('PROGRAM T BEGIN END T',mode='strict')
        _,report=build();self.assertIn('strict mode',descriptions(report)['future_tools'])

    def test_missing_and_cyclic_type_definitions_stay_rejected(self):
        for prefix in ('TYPE first=second second=first','TYPE first=absent'):
            with self.subTest(prefix=prefix),self.assertRaises(TranslationError):build(prefix=prefix)

    def test_unavailable_scalar_and_maxint_values_still_fail(self):
        for body in ('n=MAXINT','n=other'):
            with self.subTest(body=body),self.assertRaises(rt.KarelRuntimeError):build(body,decl='n,other:INTEGER')[0].run()

    def test_aggregate_uninit_and_orientation_writes_remain_blocked(self):
        for body,decl in (('flag=UNINIT(values)','values:ARRAY[2]OF INTEGER flag:BOOLEAN'),
                          ('point.normal.x=1.0','point:POSITION')):
            with self.subTest(body=body),self.assertRaises(TranslationError):build(body,decl=decl)

    def test_unstarted_for_entry_and_rank_reshape_remain_blocked(self):
        for body,decl in (('GOTO inside FOR i=1 TO 2 DO inside:: n=1 ENDFOR','i,n:INTEGER'),
                          ('target=source','source:ARRAY[2,2]OF INTEGER target:ARRAY[4]OF INTEGER')):
            with self.subTest(body=body),self.assertRaises(TranslationError):build(body,decl=decl)

    def test_unknown_byte_contents_and_non_ascii_literals_remain_guarded(self):
        with self.assertRaises(rt.KarelRuntimeError):build('n=byte_value',decl='n:INTEGER byte_value:BYTE')[0].run()
        with self.assertRaises(TranslationError):build("text='\u00e9'",decl='text:STRING[8]')


class ReportSummaryContracts(unittest.TestCase):
    def test_string_list_remains_compatible_and_details_have_real_policy_links(self):
        _,report=build();details=report['limitation_details']
        self.assertEqual(report['limitations'],[row['description'] for row in details])
        self.assertEqual(len({row['id'] for row in details}),len(details))
        for row in details:
            self.assertEqual(set(row),{'id','description','policies','guide'})
            self.assertTrue(row['description']);self.assertTrue((ROOT/row['guide']).is_file())
            for key in row['policies']:self.assertIn(key,report)
        self.assertEqual(report['limitation_policy']['schema_version'],1)
        self.assertEqual(report['limitation_policy']['mode'],'pythonic')
        self.assertFalse(report['limitation_policy']['controller_validated'])
        self.assertEqual(json.loads(json.dumps(report['limitations'])),report['limitations'])

    def test_each_report_owns_its_lists_and_category_mappings(self):
        _,first=build();_,second=build()
        first['limitations'].clear();first['limitation_details'][1]['policies'].clear()
        first['limitation_details'][0]['description']='host edit'
        self.assertTrue(second['limitations']);self.assertTrue(second['limitation_details'][1]['policies'])
        self.assertNotEqual(second['limitation_details'][0]['description'],'host edit')
        _,third=build();self.assertEqual(second['limitation_details'],third['limitation_details'])

    def test_internal_legacy_report_keeps_legacy_guards_separate(self):
        report=legacy_translate('PROGRAM T BEGIN END T').report
        self.assertNotIn('limitation_details',report)
        self.assertTrue(any('REAL uses exact binary32' in row for row in report['limitations']))

    def test_supplied_project_reports_share_current_mode_summary(self):
        project=translate_project({'m':'PROGRAM MAIN ROUTINE work FROM LIB BEGIN work() END MAIN',
            'l':'PROGRAM LIB ROUTINE work BEGIN END work BEGIN END LIB'})
        summaries=[translation.report['limitation_details'] for translation in project.translations.values()]
        self.assertEqual(summaries[0],summaries[1]);self.assertIsNot(summaries[0],summaries[1])
        self.assertTrue(all(t.report['limitation_policy']['mode']=='pythonic' for t in project.translations.values()))

    def test_empty_source_executes_without_claiming_a_complete_inventory(self):
        program,report=build();self.assertEqual(program.run()['N'],{'uninitialized':True})
        self.assertIn('not a complete',report['limitation_policy']['scope'])
        self.assertEqual(report['limitation_policy']['remaining_support'],'docs/unsupported.md')
