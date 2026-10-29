"""Authored PATH clause compatibility and predefined data record contracts."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value,decode_typed
from tests.legacy_numeric_support import translate as legacy_translate

ROOT=Path(__file__).resolve().parents[1]
TYPES='TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE header_t=STRUCTURE count:INTEGER ENDSTRUCTURE'
DECL='track:PATH NODEDATA=node_t,PATHHEADER=header_t s,n:INTEGER'
FIELDS=('CURR_WIN','CURSOR_ROW','LINS_PER_PG','CURR_FIELD','LAST_FIELD','CURR_IT_NUM','SOB_IT_NUM','EOB_IT_NUM','LAST_IT_NUM','MENU_ID')


def compile_program(body='',*,types=TYPES,decl=DECL,routines='',translator=translate,context=None):
    result=translator(f'PROGRAM T\n{types}\nVAR {decl}\n{routines}\nBEGIN {body} END T',filename='path_declarations.kl')
    namespace={'__name__':'path_declaration_test'};exec(result.python_source,namespace)
    return namespace['Program'](context=context),result


def run(body='',**options):return compile_program(body,**options)[0].run()


def initialize_display(name='display'):
    return (f'FOR index_value=1 TO 4 DO {name}.win_start[index_value]=index_value {name}.win_end[index_value]=index_value+10 ENDFOR '
            f'FOR index_value=1 TO 10 DO {name}.curs_st_col[index_value]=0 {name}.curs_en_col[index_value]=9 ENDFOR '
            +' '.join(f'{name}.{field.lower()}=0' for field in FIELDS))


def roundtrip(value):return decode_typed(json.loads(json.dumps(typed_value(value))))[1]


class PathClauseSyntaxTests(unittest.TestCase):
    def test_header_spellings_and_clause_orders_share_schema_and_storage(self):
        forms=('NODEDATA=node_t,PATHHEADER=header_t','PATHHEADER=header_t,NODEDATA=node_t',
               'NODEDATA=node_t,PATHDATA=header_t','PATHDATA=header_t,NODEDATA=node_t',
               'NODEDATA=node_t PATHHEADER=header_t','PATHDATA=header_t NODEDATA=node_t',
               'PATHDATA=header_t\n NODEDATA=node_t','NODEDATA=node_t,\n PATHHEADER=header_t')
        for clauses in forms:
            with self.subTest(clauses=clauses):
                p,_=compile_program('APPEND_NODE(track,s) track[1].value=42 track.count=1',decl='track:PATH '+clauses+' s:INTEGER')
                self.assertEqual(p.run()['TRACK'],{'nodes':[{'VALUE':42}],'data':{'COUNT':1}})

    def test_header_only_alias_has_default_nodes(self):
        p,_=compile_program('APPEND_NODE(track,s) track.count=1',decl='track:PATH PATHDATA=header_t s:INTEGER')
        self.assertEqual(p._state.types['TRACK'][1],None)
        self.assertEqual(p.run()['TRACK']['data'],{'COUNT':1})

    def test_omitted_header_stays_absent(self):
        self.assertIsNone(run('APPEND_NODE(track,s)',decl='track:PATH NODEDATA=node_t s:INTEGER')['TRACK']['data'])

    def test_header_alias_cannot_be_repeated_under_other_spelling(self):
        for clauses in ('PATHDATA=header_t,PATHHEADER=header_t','PATHHEADER=header_t PATHDATA=header_t',
                        'NODEDATA=node_t,NODEDATA=node_t'):
            with self.subTest(clauses=clauses):
                with self.assertRaises(TranslationError) as caught:compile_program(decl='track:PATH '+clauses)
                self.assertEqual(caught.exception.code,'E_TYPE')

    def test_dangling_comma_requires_another_clause(self):
        with self.assertRaises(TranslationError) as caught:compile_program(decl='track:PATH NODEDATA=node_t,')
        self.assertEqual(caught.exception.code,'E_PATH_CLAUSE')

    def test_bad_comma_does_not_consume_a_variable_declaration(self):
        with self.assertRaises(TranslationError) as caught:compile_program(decl='track:PATH NODEDATA=node_t, n:INTEGER')
        self.assertEqual(caught.exception.code,'E_PATH_CLAUSE')

    def test_pathdata_remains_an_ordinary_identifier_outside_clause_context(self):
        values=run('pathdata=42',decl='track:PATH\npathdata:INTEGER')
        self.assertEqual(values['PATHDATA'],42)

    def test_clause_right_hand_type_can_be_reflowed(self):
        values=run('track.count=42',decl='track:PATH\nPATHDATA=\n header_t')
        self.assertEqual(values['TRACK']['data']['COUNT'],42)

    def test_type_definition_structure_and_alias_can_be_reflowed(self):
        types='TYPE header_t=\nSTRUCTURE count:INTEGER ENDSTRUCTURE route_t=\n PATH PATHDATA=header_t'
        self.assertEqual(run('track.count=42',types=types,decl='track:route_t')['TRACK']['data']['COUNT'],42)

    def test_variable_colon_and_array_element_type_can_be_reflowed(self):
        values=run('display[1].curr_win=1',types='',decl='display:\n ARRAY[1] OF\n DISP_DAT_T')
        self.assertEqual(values['DISPLAY'][0]['CURR_WIN'],1)

    def test_invalid_component_types_stay_blocked(self):
        for component in ('INTEGER','VECTOR','FILE','ARRAY[2] OF INTEGER'):
            with self.subTest(component=component):
                with self.assertRaises(TranslationError) as caught:compile_program(decl='track:PATH PATHDATA='+component)
                self.assertEqual(caught.exception.code,'E_TYPE')

    def test_unknown_components_are_not_inferred(self):
        with self.assertRaises(TranslationError) as caught:compile_program(decl='track:PATH NODEDATA=missing')
        self.assertEqual(caught.exception.code,'E_TYPE')


class PredefinedRecordTests(unittest.TestCase):
    def test_display_layout_has_documented_array_widths_and_short_fields(self):
        p,_=compile_program(types='',decl='display:DISP_DAT_T')
        fields=dict(p._state.types['DISPLAY'][2])
        self.assertEqual(len(fields),14)
        self.assertEqual({name:spec[1] for name,spec in fields.items() if spec[0]=='ARRAY'},
            {'WIN_START':4,'WIN_END':4,'CURS_ST_COL':10,'CURS_EN_COL':10})
        self.assertEqual({name for name,spec in fields.items() if spec==('SHORT',)},set(FIELDS))
        self.assertEqual(rt.scalar_leaf_count(p._state.types['DISPLAY']),38)

    def test_case_insensitive_names(self):
        self.assertEqual(run('display.curr_win=1',types='',decl='display:dIsP_dAt_t')['DISPLAY']['CURR_WIN'],1)

    def test_display_fields_start_uninitialized(self):
        values=run(types='',decl='display:DISP_DAT_T')['DISPLAY']
        self.assertEqual(values['CURR_WIN'],{'uninitialized':True})
        self.assertEqual(values['WIN_START'],[{'uninitialized':True}]*4)

    def test_short_storage_bounds_still_apply(self):
        for invalid in (-32769,32768):
            with self.subTest(value=invalid):
                p,_=compile_program('display.curr_win=1 display.curr_win='+str(invalid),types='',decl='display:DISP_DAT_T')
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(p.snapshot()['DISPLAY']['CURR_WIN'],1)

    def test_short_missing_sentinel_is_not_an_initialized_value(self):
        values=run('display.curr_win=32767 flag=UNINIT(display.curr_win)',types='',decl='display:DISP_DAT_T flag:BOOLEAN')
        self.assertTrue(values['FLAG'])

    def test_using_exposes_arrays_and_short_fields(self):
        values=run('USING display DO curr_win=1 win_start[4]=42 ENDUSING',types='',decl='display:DISP_DAT_T')
        self.assertEqual((values['DISPLAY']['CURR_WIN'],values['DISPLAY']['WIN_START'][3]),(1,42))

    def test_predefined_records_work_as_fields_and_array_elements(self):
        values=run('box.display.curr_win=1 nodes[2].node_pos.location.x=42',
            types='TYPE box_t=STRUCTURE display:DISP_DAT_T ENDSTRUCTURE',decl='box:box_t nodes:ARRAY[2] OF STD_PTH_NODE')
        self.assertEqual(values['BOX']['DISPLAY']['CURR_WIN'],1)
        self.assertEqual(values['NODES'][1]['NODE_POS']['LOCATION']['X'],42.0)

    def test_alias_retains_predefined_nominal_identity(self):
        p,_=compile_program(types='TYPE display_t=DISP_DAT_T node_t=STD_PTH_NODE',decl='display:display_t node:node_t')
        self.assertEqual(p._state.types['DISPLAY'][1],'DISP_DAT_T')
        self.assertEqual(p._state.types['NODE'][1],'STD_PTH_NODE')

    def test_explicit_default_node_and_alias_use_existing_implicit_schema(self):
        for suffix in ('',' NODEDATA=STD_PTH_NODE',' NODEDATA=node_t'):
            with self.subTest(suffix=suffix):
                p,_=compile_program(types='TYPE node_t=STD_PTH_NODE',decl='track:PATH'+suffix)
                self.assertEqual(p._state.types['TRACK'],('PATH',None,None))

    def test_std_node_omits_obsolete_association_fields(self):
        p,_=compile_program(types='',decl='node:STD_PTH_NODE')
        self.assertEqual(tuple(p.snapshot()['NODE']),('NODE_POS',))
        for field in ('group_data','common_data'):
            with self.subTest(field=field):
                with self.assertRaises(TranslationError) as caught:compile_program('node.'+field+'=1',types='',decl='node:STD_PTH_NODE')
                self.assertEqual(caught.exception.code,'E_FIELD')

    def test_position_orientation_is_still_protected(self):
        with self.assertRaises(TranslationError) as caught:compile_program('node.node_pos.normal.x=1',types='',decl='node:STD_PTH_NODE')
        self.assertEqual(caught.exception.code,'E_POSITION_READ_ONLY')

    def test_packed_node_sizes_are_portable_not_native_layouts(self):
        values=run('n=NODE_SIZE(track) s=NODE_SIZE(defaults)',types='',decl='track:PATH NODEDATA=DISP_DAT_T defaults:PATH n,s:INTEGER')
        self.assertEqual((values['N'],values['S']),(76,64))

    def test_predefined_type_names_cannot_be_redeclared(self):
        for declaration in ('VAR DISP_DAT_T:INTEGER','CONST STD_PTH_NODE=7','TYPE DISP_DAT_T=INTEGER'):
            with self.subTest(declaration=declaration):
                with self.assertRaises(TranslationError) as caught:translate('PROGRAM T '+declaration+' BEGIN END T')
                self.assertEqual(caught.exception.code,'E_NAME')

    def test_legacy_parser_does_not_gain_predefined_types(self):
        for kind in ('DISP_DAT_T','STD_PTH_NODE'):
            with self.subTest(kind=kind):
                with self.assertRaises(TranslationError):compile_program(types='',decl='item:'+kind,translator=legacy_translate)

    def test_native_association_types_remain_unsupported(self):
        for kind in ('COMMON_ASSOC','GROUP_ASSOC'):
            with self.subTest(kind=kind):
                with self.assertRaises(TranslationError):compile_program(types='',decl='item:'+kind)


class PathRecordInterfaceTests(unittest.TestCase):
    def test_default_path_actual_matches_explicit_default_node_formal(self):
        values=run('edit(track) n=PATH_LEN(track)',types='',decl='track:PATH n,s:INTEGER',
            routines='ROUTINE edit(p:PATH NODEDATA=STD_PTH_NODE) VAR status:INTEGER BEGIN APPEND_NODE(p,status) p[1].node_pos.location.x=42 END edit')
        self.assertEqual(values['N'],1)
        self.assertEqual(values['TRACK']['nodes'][0]['NODE_POS']['LOCATION']['X'],42.0)

    def test_parameter_type_and_clauses_accept_physical_reflow(self):
        values=run('edit(track)',routines='ROUTINE edit(p:\n PATH NODEDATA=node_t,\n PATHDATA=header_t) BEGIN p.count=42 END edit')
        self.assertEqual(values['TRACK']['data']['COUNT'],42)

    def test_copy_path_accepts_canonical_alias_equivalence(self):
        values=run('APPEND_NODE(track,s) track[1].value=42 track.count=1 COPY_PATH(track,0,0,other,s)',
            decl=DECL+' other:PATH PATHDATA=header_t NODEDATA=node_t')
        self.assertEqual(values['OTHER'],values['TRACK'])

    def test_header_schema_mismatch_is_still_rejected(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('edit(track)',routines='ROUTINE edit(p:PATH NODEDATA=node_t) BEGIN END edit')
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_display_reference_argument_needs_no_complete_value(self):
        values=run('edit(display)',types='',decl='display:DISP_DAT_T',
            routines='ROUTINE edit(d:DISP_DAT_T) BEGIN d.curr_it_num=42 END edit')
        self.assertEqual(values['DISPLAY']['CURR_IT_NUM'],42)

    def test_display_value_argument_is_detached(self):
        values=run(initialize_display()+' edit((display))',types='',decl='display:DISP_DAT_T index_value:INTEGER',
            routines='ROUTINE edit(d:DISP_DAT_T) BEGIN d.curr_it_num=42 END edit')
        self.assertEqual(values['DISPLAY']['CURR_IT_NUM'],0)

    def test_partial_value_argument_keeps_missing_fields_and_private_storage(self):
        p,_=compile_program('display.curr_it_num=1 edit((display))',types='',decl='display:DISP_DAT_T',
            routines='ROUTINE edit(d:DISP_DAT_T) BEGIN d.curr_it_num=42 END edit')
        display=p.run()['DISPLAY']
        self.assertEqual(display['CURR_IT_NUM'],1)
        self.assertEqual(display['CURR_WIN'],{'uninitialized':True})
        self.assertEqual(display['WIN_START'],[{'uninitialized':True}]*4)

    def test_predefined_record_result_and_local_storage(self):
        values=run('display=make()',types='',decl='display:DISP_DAT_T',
            routines='ROUTINE make:DISP_DAT_T VAR display:DISP_DAT_T index_value:INTEGER BEGIN '+initialize_display()+' display.curr_it_num=42 RETURN display END make')
        self.assertEqual(values['DISPLAY']['CURR_IT_NUM'],42)

    def test_generic_array_formal_preserves_predefined_element_identity(self):
        values=run('edit(displays)',types='',decl='displays:ARRAY[2] OF DISP_DAT_T',
            routines='ROUTINE edit(rows:ARRAY[*] OF DISP_DAT_T) BEGIN rows[2].curr_it_num=42 END edit')
        self.assertEqual(values['DISPLAYS'][1]['CURR_IT_NUM'],42)

    def test_source_linked_aliases_and_routines_share_predefined_schemas(self):
        main='PROGRAM MAIN TYPE display_t FROM LIB=DISP_DAT_T VAR display:display_t ROUTINE edit(d:display_t) FROM LIB BEGIN edit(display) END MAIN'
        lib='PROGRAM LIB TYPE display_t=DISP_DAT_T ROUTINE edit(d:display_t) BEGIN d.curr_it_num=42 END edit BEGIN END LIB'
        instance=translate_project({'main.kl':main,'lib.kl':lib}).instantiate()
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['DISPLAY']['CURR_IT_NUM'],42)


class PathRecordPersistenceAndDynamicTests(unittest.TestCase):
    def test_partial_display_record_roundtrip_keeps_short_markers(self):
        p,_=compile_program('display.win_start[1]=1 display.curr_it_num=42',types='',decl='display:DISP_DAT_T')
        p.run();value=p._state.values['DISPLAY'];other=roundtrip(value)
        self.assertEqual(other.spec,value.spec)
        self.assertEqual(rt.snapshot_value(other),rt.snapshot_value(value))
        self.assertIs(other.values['MENU_ID'],rt.UNINITIALIZED)

    def test_path_with_predefined_nodes_and_headers_roundtrips(self):
        p,_=compile_program('APPEND_NODE(track,s) track.curr_win=1 track[1].node_pos.location.x=42',types='',
            decl='track:PATH NODEDATA=STD_PTH_NODE,PATHDATA=DISP_DAT_T s:INTEGER')
        p.run();other=roundtrip(p._state.values['TRACK'])
        self.assertEqual(other.spec,p._state.types['TRACK'])
        self.assertEqual(rt.snapshot_value(other),p.snapshot()['TRACK'])

    def test_context_saved_implicit_default_loads_into_explicit_declaration(self):
        first,_=compile_program('APPEND_NODE(track,s) track[1].node_pos.location.x=42',types='',decl='track:PATH s:INTEGER')
        first.run();saved=json.loads(json.dumps(first._state.execution.to_config()))
        restored=rt.ExecutionContext.from_config(saved)
        second,_=compile_program(types='',decl='track:PATH NODEDATA=STD_PTH_NODE s:INTEGER',context=restored)
        self.assertEqual(second.snapshot()['TRACK'],first.snapshot()['TRACK'])

    def test_predefined_schema_mutation_is_rejected_on_load(self):
        p,_=compile_program(types='',decl='display:DISP_DAT_T')
        config=p._state.execution.to_config();row=next(row for row in config['variables'] if row['path']=='DISPLAY')
        # A decoded foreign schema must still match the target declaration.
        row['type'][2][0][1][1]=3
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_mismatched_saved_schema_is_not_reused_as_declared_storage(self):
        p,_=compile_program(types='',decl='display:DISP_DAT_T')
        config=p._state.execution.to_config();row=next(row for row in config['variables'] if row['path']=='DISPLAY')
        row['type'][2][0][1][1]=3;row['value']['WIN_START'].pop()
        context=rt.ExecutionContext.from_config(config)
        restored,_=compile_program(types='',decl='display:DISP_DAT_T',context=context)
        self.assertEqual(len(restored._state.values['DISPLAY'].values['WIN_START'].values),4)
        self.assertIsNot(restored._state.values['DISPLAY'],context.variables.bindings['T','DISPLAY'].raw())

    def test_get_var_promotes_known_short_into_integer_storage(self):
        values=run("CREATE_VAR('CACHE','DISPLAY','','DISP_DAT_T',0,0,0,0,s) SET_VAR(e,'CACHE','DISPLAY.curr_it_num',42,s) GET_VAR(e,'CACHE','DISPLAY.curr_it_num',n,s)",
            types='',decl='e,n,s:INTEGER')
        self.assertEqual(values['S'],0)
        self.assertEqual(values['N'],42)

    def test_create_var_supports_builtin_display_schema(self):
        values=run("CREATE_VAR('CACHE','DISPLAY','','DISP_DAT_T',0,0,0,0,s) SET_VAR(e,'CACHE','DISPLAY.curr_it_num',42,s) GET_VAR(e,'CACHE','DISPLAY.curr_it_num',result.curr_it_num,s) n=result.curr_it_num",
            types='',decl='e,n,s:INTEGER result:DISP_DAT_T')
        self.assertEqual((values['N'],values['S']),(42,0))

    def test_create_var_supports_builtin_std_arrays(self):
        p,_=compile_program("CREATE_VAR('CACHE','NODES','','STD_PTH_NODE',0,2,0,0,s) SET_VAR(e,'CACHE','NODES[2].node_pos.location.x',42,s)",types='',decl='e,s:INTEGER')
        self.assertEqual(p.run()['S'],0)
        ref=p._state.execution.variables.bindings['CACHE','NODES']
        self.assertEqual(ref.spec[2],rt.PREDEFINED_STRUCTURES['STD_PTH_NODE'])
        self.assertEqual(ref.raw().values[1].values['NODE_POS'].values['LOCATION'].values['X'],42.0)

    def test_dynamic_predefined_records_persist_as_existing_structure_tuples(self):
        p,_=compile_program("CREATE_VAR('CACHE','DISPLAY','','DISP_DAT_T',0,0,0,0,s) SET_VAR(e,'CACHE','DISPLAY.curr_it_num',42,s)",types='',decl='e,s:INTEGER')
        p.run();context=rt.ExecutionContext.from_config(json.loads(json.dumps(p._state.execution.to_config())))
        self.assertEqual(context.variables.bindings['CACHE','DISPLAY'].spec,rt.PREDEFINED_STRUCTURES['DISP_DAT_T'])
        self.assertEqual(context.variables.bindings['CACHE','DISPLAY'].raw().values['CURR_IT_NUM'],42)

    def test_vr_archive_roundtrip_retains_predefined_nominal_schema(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles(),variable_archives=rt.VariableArchives())
        p,_=compile_program("CREATE_VAR('CACHE','DISPLAY','','DISP_DAT_T',0,0,0,0,s) SET_VAR(e,'CACHE','DISPLAY.curr_it_num',42,s) SAVE('CACHE','FR:CACHE.VR',s) CLEAR('CACHE.VR',s) LOAD('FR:CACHE.VR',0,s) GET_VAR(e,'CACHE','DISPLAY.curr_it_num',result.curr_it_num,s) n=result.curr_it_num",
            types='',decl='e,n,s:INTEGER result:DISP_DAT_T',context=ctx)
        self.assertEqual(p.run()['N'],42)
        self.assertEqual(ctx.variables.bindings['CACHE','DISPLAY'].spec,rt.PREDEFINED_STRUCTURES['DISP_DAT_T'])


class PathRecordReportAndCLITests(unittest.TestCase):
    def test_reports_preserve_original_and_canonical_clause_names(self):
        _,result=compile_program(decl='track:PATH PATHDATA=header_t NODEDATA=STD_PTH_NODE')
        report=json.loads(json.dumps(result.report))
        self.assertEqual([(r['clause'],r['canonical']) for r in report['path_clause_uses']],
            [('PATHDATA','PATHHEADER'),('NODEDATA','NODEDATA')])
        self.assertEqual(report['predefined_structures']['STD_PTH_NODE'][1],'STD_PTH_NODE')
        self.assertFalse(report['path_declaration_policy']['controller_validated'])

    def test_included_clause_and_type_uses_have_physical_origins(self):
        result=translate('PROGRAM T\n%INCLUDE declarations\nBEGIN END T',
            includes={'declarations.kl':'VAR track:PATH PATHDATA=DISP_DAT_T NODEDATA=STD_PTH_NODE'})
        for row in result.report['path_clause_uses']+result.report['predefined_structure_uses']:
            self.assertEqual((row['source_file'],row['source_line']),('declarations.kl',1))

    def test_invalid_included_clause_reports_original_file(self):
        with self.assertRaises(TranslationError) as caught:
            translate('PROGRAM T\n%INCLUDE declarations\nBEGIN END T',includes={'declarations.kl':'VAR track:PATH PATHDATA=DISP_DAT_T,'})
        self.assertEqual(caught.exception.filename,'declarations.kl')
        self.assertEqual(caught.exception.code,'E_PATH_CLAUSE')

    def test_cli_accepts_predefined_types_and_header_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'input.kl';output=Path(folder)/'output.py';report=Path(folder)/'report.json'
            source.write_text('PROGRAM T VAR track:PATH PATHDATA=DISP_DAT_T NODEDATA=STD_PTH_NODE BEGIN track.curr_it_num=42 END T')
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(source),'-o',str(output),'--report',str(report)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(report.read_text());self.assertIn('DISP_DAT_T',data['predefined_structures'])
            namespace={'__name__':'cli_test'};exec(output.read_text(),namespace)
            self.assertEqual(namespace['Program']().run()['TRACK']['data']['CURR_IT_NUM'],42)
