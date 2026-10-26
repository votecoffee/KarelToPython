"""Authored text dictionary parsing, formatting, window output and persistence."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.dictionaries import parse
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


DECL='lines:ARRAY[3] OF STRING[80] paths:ARRAY[3] OF STRING[80] last,s,n:INTEGER f:FILE label:STRING[40] x:REAL flag:BOOLEAN'
LOAD="ADD_DICT('labels','USER',DP_DEFAULT,DP_DRAM,s) "
WINDOW="DEF_WINDOW('W1',3,16,WD_COM_CURSR,s) ATT_WINDOW_S('W1','SYS',1,1,s) OPEN FILE f('RW','WD:W1') "
CLOSE=' CLOSE FILE f'


def context(text='$1 "Hello" &new_line',**options):
    return rt.ExecutionContext(dictionaries=rt.TextDictionaries(sources={'labels':text},**options),pendant=rt.PendantDisplay(rows=3,cols=16))


def execute(body,text='$1 "Hello" &new_line',*,ctx=None,decl=DECL,**options):
    ctx=context(text) if ctx is None else ctx
    program,result=compile_program(body,decl=decl,context=ctx,**options)
    return program.run(),ctx,program,result


class DictionaryLoadTests(unittest.TestCase):
    def test_add_and_check_by_integer(self):
        values,ctx,_,_=execute(LOAD+"CHECK_DICT('USER',1,s)")
        self.assertEqual(values['S'],0);self.assertIn('USER',ctx.dictionaries.loaded['ENGLISH'])

    def test_source_labels_are_case_insensitive_and_default_to_tx(self):
        values,_,_,_=execute("ADD_DICT('LABELS.tx','USER',DP_DEFAULT,DP_DRAM,s)")
        self.assertEqual(values['S'],0)

    def test_dictionary_name_uses_first_four_characters(self):
        values,_,_,_=execute("ADD_DICT('labels','UserLong',DP_DEFAULT,DP_DRAM,s) CHECK_DICT('userElse',1,s)")
        self.assertEqual(values['S'],0)

    def test_check_supports_case_sensitive_names_and_decimal_text(self):
        for selector in ("'Greeting'","'1'"):
            with self.subTest(selector=selector):
                values,_,_,_=execute(LOAD+f"CHECK_DICT('USER',{selector},s)",'$1, Greeting "Hi"')
                self.assertEqual(values['S'],0)
        values,_,_,_=execute(LOAD+"CHECK_DICT('USER','greeting',s)",'$1, Greeting "Hi"')
        self.assertEqual(values['S'],3)

    def test_duplicate_load_preserves_loaded_snapshot(self):
        ctx=context();execute(LOAD,ctx=ctx);ctx.dictionaries.sources['LABELS.TX']='$1 "Replacement"'
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",ctx=ctx)
        self.assertEqual(values['LINES'][0],'Hello');self.assertEqual(ctx.dictionaries.loaded['ENGLISH']['USER']['text'],'$1 "Hello" &new_line')

    def test_duplicate_load_reports_status(self):
        values,_,_,_=execute(LOAD+LOAD)
        self.assertEqual(values['S'],2)

    def test_missing_source_and_element(self):
        values,_,_,_=execute("ADD_DICT('missing','USER',DP_DEFAULT,DP_DRAM,s)")
        self.assertEqual(values['S'],3)
        values,_,_,_=execute(LOAD+"CHECK_DICT('USER',99,s)")
        self.assertEqual(values['S'],3)

    def test_invalid_option_and_name_do_not_load(self):
        for name,option in (("'USER'",0),("'1BAD'",1)):
            with self.subTest(name=name,option=option):
                values,ctx,_,_=execute(f"ADD_DICT('labels',{name},DP_DEFAULT,{option},s)")
                self.assertEqual(values['S'],1);self.assertEqual(ctx.dictionaries.loaded,{})

    def test_missing_language_reports_documented_status(self):
        values,ctx,_,_=execute("ADD_DICT('labels','USER',DP_SPANISH,DP_DRAM,s)")
        self.assertEqual(values['S'],33003);self.assertEqual(ctx.dictionaries.loaded,{})

    def test_remove_one_language_and_all_languages(self):
        ctx=context(languages=['ENGLISH','SPANISH']);ctx.pendant=rt.PendantDisplay(languages=['ENGLISH','SPANISH'])
        body=LOAD+"ADD_DICT('labels','USER',DP_SPANISH,DP_DRAM,s) REMOVE_DICT('USER',DP_ENGLISH,s) SET_LANG(DP_SPANISH,s) CHECK_DICT('USER',1,s)"
        values,_,_,_=execute(body,ctx=ctx)
        self.assertEqual(values['S'],0);self.assertEqual(set(ctx.dictionaries.loaded),{'SPANISH'})
        values,_,_,_=execute("REMOVE_DICT('USER','',s)",ctx=ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.dictionaries.loaded,{})

    def test_current_pendant_language_selects_exact_dictionary(self):
        ctx=context(languages=['ENGLISH','SPANISH']);ctx.pendant=rt.PendantDisplay(languages=['ENGLISH','SPANISH'])
        execute(LOAD,ctx=ctx);ctx.dictionaries.sources['LABELS.TX']='$1 "Hola"'
        values,_,_,_=execute("ADD_DICT('labels','USER',DP_SPANISH,DP_DRAM,s) SET_LANG(DP_SPANISH,s) READ_DICT('USER',1,lines,1,last,s)",ctx=ctx)
        self.assertEqual(values['LINES'][0],'Hola')

    def test_no_implicit_fallback_to_default_language(self):
        ctx=context(languages=['ENGLISH','SPANISH']);ctx.pendant=rt.PendantDisplay(languages=['ENGLISH','SPANISH'])
        values,_,_,_=execute(LOAD+"SET_LANG(DP_SPANISH,s) CHECK_DICT('USER',1,s)",ctx=ctx)
        self.assertEqual(values['S'],3)

    def test_default_selector_uses_pendant_default(self):
        ctx=context(languages=['ENGLISH','SPANISH']);ctx.pendant=rt.PendantDisplay(languages=['ENGLISH','SPANISH'],default_language='SPANISH')
        _,_,_,_=execute(LOAD,ctx=ctx)
        self.assertEqual(set(ctx.dictionaries.loaded),{'SPANISH'})

    def test_model_language_works_without_pendant(self):
        ctx=rt.ExecutionContext(dictionaries=rt.TextDictionaries(sources={'labels':'$1 "Hola"'},languages=['SPANISH'],default_language='SPANISH'))
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",ctx=ctx)
        self.assertEqual((values['LINES'][0],values['S']),('Hola',0))

    def test_missing_service_raises_instead_of_creating_dictionary_bank(self):
        program,_=compile_program(LOAD,context=rt.ExecutionContext())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'dictionaries'):program.run()


class DictionarySyntaxTests(unittest.TestCase):
    def test_comments_auto_numbers_and_multiple_strings(self):
        text='* comment\n$0, Base "A" "B" * trailing\n$- "C"'
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",text)
        self.assertEqual(values['LINES'][0],'C')

    def test_backslash_and_quote_escapes(self):
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",r'$1 "a\\b\"c"')
        self.assertEqual(values['LINES'][0],'a\\b"c')

    def test_nested_forward_numeric_and_named_elements(self):
        text='$1 +Greeting " " +3\n$2, Greeting "Hello"\n$3 "world"'
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",text)
        self.assertEqual(values['LINES'][0],'Hello world')

    def test_read_ignores_style_and_cursor_controls(self):
        text='$1 &bold @2,3 "Hello" &clear_win &home &new_line &fg_red "next"'
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",text)
        self.assertEqual(values['LINES'][:2],['Hello','next']);self.assertEqual(values['LAST'],2)

    def test_character_codes_and_newline(self):
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",'$1 #65 #135 #66')
        self.assertEqual(values['LINES'][:2],['A','B'])

    def test_empty_element_returns_one_empty_line(self):
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",'$1 ""')
        self.assertEqual(values['LINES'][0],'');self.assertEqual(values['LAST'],1)

    def test_malformed_text_fails_load_without_mutation(self):
        documents=('text before header','$1 "unterminated','$1 "bad\\q"','$1 &unknown','$1 #255',
                   '$1 "A"\n$1 "B"','$1, Same "A"\n$2, Same "B"','$1 +Missing','$1 +1',
                   '$1 @0,1 "A"','$32768 "x"','$1 "multi\nline"')
        for text in documents:
            with self.subTest(text=text):
                values,ctx,_,_=execute(LOAD,text)
                self.assertEqual(values['S'],1);self.assertEqual(ctx.dictionaries.loaded,{})

    def test_nesting_limit_is_five_levels(self):
        parse('$1 +2\n$2 +3\n$3 +4\n$4 +5\n$5 "x"')
        with self.assertRaises(ValueError):parse('$1 +2\n$2 +3\n$3 +4\n$4 +5\n$5 +6\n$6 "x"')

    def test_expansion_budget_does_not_write_partial_output(self):
        text='$1 '+('+2 '*100)+'\n$2 '+('+3 '*100)+'\n$3 "abcdefgh"'
        values,_,_,_=execute(LOAD+"lines[1]='old' READ_DICT('USER',1,lines,1,last,s)",text)
        self.assertEqual((values['S'],values['LINES'][0]),(5,'old'))


class DictionaryReadTests(unittest.TestCase):
    def test_first_line_and_tail_preservation(self):
        values,_,_,_=execute(LOAD+"lines[1]='keep' lines[3]='tail' READ_DICT('USER',1,lines,2,last,s)")
        self.assertEqual(values['LINES'],['keep','Hello','tail']);self.assertEqual(values['LAST'],2)

    def test_too_many_lines_returns_truncation_and_last_used(self):
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,2,last,s)",'$1 "A" &new_line "B" &new_line "C"')
        self.assertEqual(values['LINES'][1:],['A','B']);self.assertEqual((values['LAST'],values['S']),(3,33008))

    def test_narrow_string_cells_right_truncate(self):
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",decl='lines:ARRAY[2] OF STRING[3] last,s:INTEGER')
        self.assertEqual((values['LINES'][0],values['S']),('Hel',33008))

    def test_trailing_newline_does_not_add_extra_output_row(self):
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)")
        self.assertEqual(values['LAST'],1)

    def test_consecutive_newlines_preserve_empty_row(self):
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",'$1 "A" &new_line &new_line "B"')
        self.assertEqual(values['LINES'],['A','','B'])

    def test_bad_first_line_preserves_every_output(self):
        for start in (0,4):
            with self.subTest(start=start):
                values,_,_,_=execute(LOAD+f"lines[1]='old' last=99 READ_DICT('USER',1,lines,{start},last,s)")
                self.assertEqual((values['LINES'][0],values['LAST'],values['S']),('old',99,1))

    def test_plain_read_keeps_percent_markers_literal(self):
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",'$1 "%s %%"')
        self.assertEqual(values['LINES'][0],'%s %%')

    def test_named_array_output_retains_nominal_storage(self):
        values,_,_,_=execute(LOAD+"READ_DICT('USER',1,lines,1,last,s)",decl='lines:LINES_T last,s:INTEGER',prefix='TYPE LINES_T=ARRAY[3] OF STRING[80]')
        self.assertEqual(values['LINES'][0],'Hello')


class DictionaryFormatTests(unittest.TestCase):
    def formatted(self,template,body,decl=DECL):
        return execute(LOAD+body+" READ_DICT_V('USER',1,paths,lines,s)",'$1 "'+template+'"',decl=decl)[0]

    def test_string_numeric_and_literal_percent(self):
        values=self.formatted('%s %05d %.2f %%',"label='ready' n=42 x=1.25 paths[1]='label' paths[2]='n' paths[3]='x'")
        self.assertEqual((values['LINES'][0],values['S']),('ready 00042 1.25 %',0))

    def test_reordered_and_repeated_variables(self):
        values=self.formatted('%s^2/%s^1/%s^2',"paths[1]='label' paths[2]='lines[3]' label='one' lines[3]='two'")
        self.assertEqual(values['LINES'][0],'two/one/two')

    def test_nested_elements_share_argument_order(self):
        text='$1 "%d" +2\n$2 "/%s"'
        values,_,_,_=execute(LOAD+"n=7 label='ok' paths[1]='n' paths[2]='label' READ_DICT_V('USER',1,paths,lines,s)",text)
        self.assertEqual(values['LINES'][0],'7/ok')

    def test_width_precision_and_left_justification(self):
        values=self.formatted('[%-6.3s] [%+5d] [%.4d]',"label='abcdef' n=12 paths[1]='label' paths[2]='n' paths[3]='n'")
        self.assertEqual(values['LINES'][0],'[abc   ] [  +12] [0012]')

    def test_unsigned_octal_hex_and_decimal_use_32_bits(self):
        values=self.formatted('%x/%X/%u',"n=-1 paths[1]='n' paths[2]='n' paths[3]='n'")
        self.assertEqual(values['LINES'][0],'ffffffff/FFFFFFFF/4294967295')
        values=self.formatted('%o',"n=9 paths[1]='n'")
        self.assertEqual(values['LINES'][0],'11')

    def test_boolean_and_narrow_fields_as_integer_formats(self):
        text='$1 "%d/%d/%d"'
        values,_,_,_=execute(LOAD+"flag=TRUE data.a=7 data.b=8 paths[1]='flag' paths[2]='data.a' paths[3]='data.b' READ_DICT_V('USER',1,paths,lines,s)",text,decl=DECL+' data:DATA_T',prefix='TYPE DATA_T=STRUCTURE a:SHORT b:BYTE ENDSTRUCTURE')
        self.assertEqual(values['LINES'][0],'1/7/8')

    def test_scientific_and_general_formats(self):
        values=self.formatted('%.2e/%.3G',"x=123.5 paths[1]='x' paths[2]='x'")
        self.assertEqual(values['LINES'][0],'1.24e+02/124')

    def test_unused_value_slots_may_remain_uninitialized(self):
        values=self.formatted('%s',"label='ok' paths[1]='label'")
        self.assertEqual((values['LINES'][0],values['S']),('ok',0))

    def test_input_output_array_alias_is_captured_before_write(self):
        values,_,_,_=execute(LOAD+"label='ok' paths[1]='label' READ_DICT_V('USER',1,paths,paths,s)",'$1 "%s"')
        self.assertEqual(values['PATHS'][0],'ok')

    def test_missing_uninitialized_or_nonscalar_variables_preserve_output(self):
        for path in ('missing','label','lines','[MISSING]x'):
            with self.subTest(path=path):
                values=self.formatted('%s',f"paths[1]='{path}' lines[1]='old'")
                self.assertEqual(values['LINES'][0],'old');self.assertEqual(values['S'],4)

    def test_type_mismatch_and_malformed_formats_are_status_failures(self):
        for template in ('%f','%q','%999d','%.999d','%++d','%s^4','%+s'):
            with self.subTest(template=template):
                values=self.formatted(template,"n=7 paths[1]='n' lines[1]='old'")
                self.assertEqual(values['LINES'][0],'old');self.assertEqual(values['S'],4)

    def test_routine_local_names_are_not_dictionary_static_globals(self):
        routines="ROUTINE local_read VAR local_value:STRING[10] BEGIN local_value='hidden' paths[1]='local_value' READ_DICT_V('USER',1,paths,lines,s) END local_read"
        values,_,_,_=execute(LOAD+'local_read',routines=routines,text='$1 "%s"')
        self.assertEqual(values['S'],4)

    def test_linked_routine_can_read_explicit_owner_globals(self):
        ctx=context('$1 "%d"')
        project=translate_project({'main':source('MAIN',LOAD+"n=42 paths[1]='[MAIN]n' read_it",decl=DECL,routines='ROUTINE read_it FROM LIB'),
            'lib':source('LIB',"",decl='lines FROM MAIN:ARRAY[3] OF STRING[80] paths FROM MAIN:ARRAY[3] OF STRING[80] s FROM MAIN:INTEGER',routines="ROUTINE read_it BEGIN READ_DICT_V('USER',1,paths,lines,s) END read_it")})
        instance=project.instantiate(context=ctx);values=instance.run('MAIN')['MAIN']['values']
        self.assertEqual((values['LINES'][0],values['S']),('42',0))


class DictionaryWindowTests(unittest.TestCase):
    def test_plain_and_formatted_window_output(self):
        text='$1 "Count="\n$2 "%d" &new_line'
        values,ctx,_,_=execute(LOAD+WINDOW+"WRITE_DICT(f,'USER',1,s) n=42 paths[1]='n' WRITE_DICT_V(f,'USER',2,paths,s)"+CLOSE,text)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'Count=42        ')

    def test_cursor_clear_and_home_controls(self):
        text='$1 "obsolete" &clear_win @2,3 "XY" &home "A"'
        values,ctx,_,_=execute(LOAD+WINDOW+"WRITE_DICT(f,'USER',1,s)"+CLOSE,text)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.pendant.windows['W1']['lines'],['A               ','  XY            ','                '])

    def test_clear_to_end_of_line_and_window(self):
        for command in ('clear_2_eol','clear_2_eow'):
            with self.subTest(command=command):
                text='$1 "abcdef" @1,3 &'+command+' "Z"'
                _,ctx,_,_=execute(LOAD+WINDOW+"WRITE_DICT(f,'USER',1,s)"+CLOSE,text)
                self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'abZ             ')

    def test_reverse_line_feed_preserves_column(self):
        text='$1 @3,4 "B" &rev_lf "A"'
        _,ctx,_,_=execute(LOAD+WINDOW+"WRITE_DICT(f,'USER',1,s)"+CLOSE,text)
        self.assertEqual(ctx.pendant.windows['W1']['lines'][1],'    A           ')

    def test_bad_late_cursor_keeps_complete_previous_surface(self):
        text='$1 "new" @4,1 "invalid"'
        values,ctx,_,_=execute(LOAD+WINDOW+"WRITE f('old') WRITE_DICT(f,'USER',1,s)"+CLOSE,text)
        self.assertEqual(values['S'],4);self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'old             ')
        self.assertEqual(values['F']['position'],3)

    def test_bad_late_format_keeps_complete_previous_surface(self):
        text='$1 "prefix %d"'
        values,ctx,_,_=execute(LOAD+WINDOW+"WRITE f('old') paths[1]='missing' WRITE_DICT_V(f,'USER',1,paths,s)"+CLOSE,text)
        self.assertEqual(values['S'],4);self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'old             ')

    def test_write_requires_window_handle_and_does_not_modify_ordinary_file(self):
        ctx=context();ctx.files=rt.MemoryFiles({'data':''})
        values,_,_,_=execute(LOAD+"OPEN FILE f('RW','data') WRITE_DICT(f,'USER',1,s) CLOSE FILE f",ctx=ctx)
        self.assertEqual(values['S'],4);self.assertEqual(ctx.files.snapshot()['data'],b'')

    def test_window_sequence_exhaustion_reports_failure_without_mutation(self):
        ctx=context();_,_,program,_=execute(LOAD+WINDOW,ctx=ctx);ctx.pendant.sequence=2147483646
        ctx.dictionaries.invoke(program._state,'WRITE_DICT',[program._state.values['F'],'USER',1,rt.Reference(('INTEGER',),program._state.values,'S')])
        self.assertEqual(program.snapshot()['S'],4);self.assertEqual(ctx.pendant.windows['W1']['lines'][0],' '*16)
        ctx.pendant.close(program._state.values['F'])


class DictionaryPersistenceAndGuardTests(unittest.TestCase):
    def test_roundtrip_retains_loaded_snapshot_after_source_change(self):
        ctx=context();execute(LOAD,ctx=ctx);ctx.dictionaries.sources['LABELS.TX']='$1 "changed"'
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        values,_,_,_=execute("READ_DICT('USER',1,lines,1,last,s)",ctx=restored)
        self.assertEqual(values['LINES'][0],'Hello');self.assertEqual(restored.dictionaries.sources['LABELS.TX'],'$1 "changed"')

    def test_snapshots_are_detached(self):
        ctx=context();execute(LOAD,ctx=ctx);data=ctx.dictionaries.snapshot();data['loaded']['ENGLISH']['USER']['text']='broken'
        self.assertNotEqual(data,ctx.dictionaries.snapshot())

    def test_bad_configuration_and_unknown_fields_rejected(self):
        for config in ({'sources':[]},{'sources':{'a':'$1 "x"','A.tx':'$1 "y"'}},{'language':''},{'languages':['ENGLISH','english']},
                       {'sources':{'a':'x'*65537}},{'loaded':{'ENGLISH':{'USER':{'source':'A.TX','text':'bad'}}}},{'unknown':1}):
            with self.subTest(config=str(config)[:80]),self.assertRaises(ValueError):rt.TextDictionaries.from_config(config)
        with self.assertRaises(TypeError):rt.ExecutionContext(dictionaries={})

    def test_output_overlap_rejected_before_read(self):
        ctx=context();program,_=compile_program(LOAD+"READ_DICT('USER',1,lines,1,s,s)",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):program.run()

    def test_active_counter_output_and_wrong_array_shapes_are_blocked(self):
        cases=(("FOR n=1 TO 2 DO CHECK_DICT('USER',1,n) ENDFOR",DECL,'E_FOR_COUNTER'),
               ("READ_DICT('USER',1,n,1,last,s)",DECL,'E_TYPE'),
               ("READ_DICT('USER',1,lines,1,last,s)",'lines:ARRAY[2,2] OF STRING[20] last,s:INTEGER','E_TYPE'),
               ("CHECK_DICT('USER',TRUE,s)",DECL,'E_TYPE'))
        for body,decl,code in cases:
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:compile_program(body,decl=decl)
            self.assertEqual(caught.exception.code,code)


class DictionaryBoundaryTests(unittest.TestCase):
    def test_presence_check_does_not_expand_large_valid_element(self):
        text='$1 '+('+2 '*100)+'\n$2 '+('+3 '*100)+'\n$3 "abcdefgh"'
        values,_,_,_=execute(LOAD+"CHECK_DICT('USER',1,s)",text)
        self.assertEqual(values['S'],0)

    def test_loaded_dictionary_capacity_is_preflighted(self):
        loaded={'ENGLISH':{f'A{index:03d}':{'source':'LABELS.TX','text':'$1 "x"'} for index in range(64)}}
        ctx=context();ctx.dictionaries=rt.TextDictionaries(sources={'labels':'$1 "Hello"'},loaded=loaded)
        values,_,_,_=execute(LOAD,ctx=ctx)
        self.assertEqual(values['S'],5);self.assertNotIn('USER',ctx.dictionaries.loaded['ENGLISH'])

    def test_path_node_field_is_a_checked_static_format_source(self):
        prefix='TYPE NODE_T=STRUCTURE label:STRING[10] ENDSTRUCTURE'
        decl=DECL+' route:PATH NODEDATA=NODE_T'
        values,_,_,_=execute(LOAD+"APPEND_NODE(route,s) route[1].label='node' paths[1]='ROUTE[1].LABEL' READ_DICT_V('USER',1,paths,lines,s)",'$1 "%s"',decl=decl,prefix=prefix)
        self.assertEqual((values['LINES'][0],values['S']),('node',0))

    def test_window_position_overflow_does_not_change_surface(self):
        ctx=context();_,_,program,_=execute(LOAD+WINDOW,ctx=ctx)
        handle=program._state.values['F'];handle.position=2147483646
        ctx.dictionaries.invoke(program._state,'WRITE_DICT',[handle,'USER',1,rt.Reference(('INTEGER',),program._state.values,'S')])
        self.assertEqual(program.snapshot()['S'],4);self.assertEqual(ctx.pendant.windows['W1']['lines'][0],' '*16)
        ctx.pendant.close(handle)


class DictionaryReportTests(unittest.TestCase):
    def test_report_records_source_and_offline_boundaries(self):
        _,_,_,result=execute(LOAD)
        policy=result.report['dictionary_policy']
        self.assertEqual(len(policy['calls']),7)
        self.assertEqual(policy['constants'],{'DP_DRAM':1})
        self.assertEqual(policy['guide'],'docs/text-dictionaries.md')
        self.assertIs(policy['controller_validated'],False)
