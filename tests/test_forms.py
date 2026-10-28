"""Authored FTX forms, typed edits, overlays, trees and execution guards."""
import json
import unittest

from karel2py import runtime as rt,translate,translate_project
from karel2py.dictionaries import parse
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


DECL='''n,chosen,key,status:INTEGER real_value:REAL flag:BOOLEAN byte_value:ARRAY[1] OF BYTE short_value:ARRAY[1] OF SHORT
text:STRING[12] values:ARRAY[10] OF STRING[40] inactive,changed:ARRAY[10] OF BOOLEAN
choices:ARRAY[5] OF STRING[12] fkeys:ARRAY[5] OF STRING[12]'''
LOAD="ADD_DICT('formtext','FORM',DP_DEFAULT,DP_DRAM,status) "
SETUP="""FORCE_SPMENU(TP_PANEL,SPI_TPUSER2,1)
n=1 real_value=1.5 flag=FALSE text='old' chosen=1
values[1]='N' values[2]='TEXT' values[3]='FLAG'"""
CALL="DISCTRL_FORM('FORM',1,values,inactive,changed,KC_FUNC_KEY OR KC_PREV_KEY,chosen,key,status)"


def ftx(body='"Number " "-%4d(0,10)" &new_line "- Done"',attributes='unnumber',extra=''):
    return '.form '+attributes+'\n$1,editor\n&home "Editor" &new_line "Values" &new_line\n'+body+'\n.endform\n'+extra


def context(text=None,keys=('F3',),**services):
    return rt.ExecutionContext(forms=rt.FormControls(rows=5,cols=24),pendant=rt.PendantDisplay(rows=5,cols=24),
        dictionaries=rt.TextDictionaries(sources={'formtext':text or ftx()}),
        keyboard=rt.KeyboardInput(events=[{'key':key} if type(key) is str else key for key in keys]),**services)


def execute(text=None,keys=('F3',),body=CALL,decl=DECL,ctx=None,setup=SETUP):
    ctx=ctx or context(text,keys);p,result=compile_program(LOAD+setup+' '+body,decl=decl,context=ctx,sleep=lambda _:None)
    return p.run(),ctx,p,result


class FormEditingTests(unittest.TestCase):
    def test_integer_commit_selectable_item_and_change_prefix(self):
        values,ctx,_,_=execute(keys=('5','ENTER','DOWN','ENTER'))
        self.assertEqual((values['N'],values['CHOSEN'],values['KEY'],values['STATUS']),(5,2,1008,0))
        self.assertTrue(values['CHANGED'][0]);self.assertEqual(values['CHANGED'][1],{'uninitialized':True})
        self.assertTrue(ctx.pendant.windows['FORM']['lines'][2].startswith('Number    5'))
        self.assertEqual(ctx.forms.active_count,0);self.assertEqual(ctx.pendant.screens['SYS']['attachments'],[])
        rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))

    def test_failed_range_entry_can_be_corrected_without_rewriting_live_value(self):
        values,_,_,_=execute(keys=('9','9','ENTER','DELETE','ENTER','F3'))
        self.assertEqual((values['N'],values['STATUS']),(9,0));self.assertTrue(values['CHANGED'][0])

    def test_invalid_edit_then_prev_discards_and_next_prev_exits(self):
        values,_,_,_=execute(keys=('x','ENTER','PREV','PREV'))
        self.assertEqual((values['N'],values['KEY'],values['STATUS']),(1,1005,0));self.assertFalse(values['CHANGED'][0])

    def test_real_byte_short_and_hexadecimal_fields(self):
        cases=[('%8.2f(0,100)','REAL_VALUE',('2','.','5'),2.5),('%4b','BYTE_VALUE[1]',tuple('255'),255),
            ('%6h','SHORT_VALUE[1]',tuple('-32768'),-32768),('%4x','N',tuple('ff'),255),('%4o','N',tuple('17'),15)]
        for fmt,path,keys,expected in cases:
            with self.subTest(fmt=fmt):
                values,_,_,_=execute(ftx('"-'+fmt+'"'),keys=keys+('ENTER','F3'),setup=SETUP+" values[1]='"+path+"'")
                self.assertEqual(((values[path.split('[')[0]][0] if '[' in path else values[path]),values['STATUS']),(expected,0))

    def test_string_clear_append_and_cursor_editing_preserve_case(self):
        for fmt,keys,expected in [('%10k(clear)',('a','b','ENTER','F3'),'ab'),('%10k',('x','ENTER','F3'),'oldx'),
            ('%10k',('ENTER','HOME','a','END','DELETE','ENTER','F3'),'aol')]:
            values,_,_,_=execute(ftx('"-'+fmt+'"'),keys=keys,setup=SETUP+" values[1]='TEXT'")
            self.assertEqual((values['TEXT'],values['STATUS']),(expected,0))

    def test_string_capacity_failure_can_be_cancelled(self):
        values,_,_,_=execute(ftx('"-%12k(clear)"'),keys=tuple('x'*13)+('ENTER','PREV','F3'),setup=SETUP+" values[1]='TEXT'")
        self.assertEqual(values['TEXT'],'old');self.assertFalse(values['CHANGED'][0])

    def test_boolean_function_keys_override_form_termination_mask(self):
        text=ftx('"-%6B(labels)"',extra='$2,labels " No" &new_line " Yes"')
        values,_,_,_=execute(text,keys=('F4','F5','F4','F3'),setup=SETUP+" values[1]='FLAG'")
        self.assertEqual((values['FLAG'],values['KEY']),(True,1103))

    def test_function_key_enum_skips_blank_choices(self):
        text=ftx('"-%6n(labels)"',extra='$2,labels "" &new_line "Slow" &new_line "Fast"')
        values,_,_,_=execute(text,keys=('F1','F3','F7'))
        self.assertEqual((values['N'],values['KEY']),(3,1107))

    def test_subwindow_enum_accepts_bell_terminator(self):
        text=ftx('"-%6w(options)"',extra='$2,options "One"\n$3 "Two"\n$4 "\\a"')
        values,ctx,_,_=execute(text,keys=('F4','DOWN','ENTER','F3'))
        self.assertEqual((values['N'],values['KEY']),(2,1103));self.assertIn('Two',ctx.pendant.windows['FORM']['lines'][2])

    def test_variable_choice_array_skips_element_one_and_stops_at_unknown(self):
        text=ftx('"-%6v(options)"',extra='$2,options "T" &new_line "CHOICES"')
        setup=SETUP+" choices[2]='Red' choices[3]='Blue' choices[5]='Hidden'"
        values,_,_,_=execute(text,keys=('F4','DOWN','ENTER','F3'),setup=setup)
        self.assertEqual(values['N'],2)

    def test_program_selection_uses_explicit_catalog_and_attached_names(self):
        text=ftx('"-%12pk(2)"');ctx=context(text,('F4','DOWN','ENTER','F3'),programs=rt.ProgramCatalog([dict(name='ALPHA',type='PC'),dict(name='ROBOT',type='TP')]))
        values,_,_,_=execute(ctx=ctx,setup=SETUP+" values[1]='TEXT'")
        self.assertEqual(values['TEXT'],'T')

    def test_display_only_fields_consume_paths_without_becoming_selectable(self):
        text=ftx('"Read " "%4d" &new_line "- Done"')
        values,ctx,_,_=execute(text,keys=('ENTER',))
        self.assertEqual((values['CHOSEN'],values['KEY']),(1,1008));self.assertFalse(values['CHANGED'][0])
        self.assertIn('   1',ctx.pendant.windows['FORM']['lines'][2])

    def test_output_ports_and_simulation_are_explicit(self):
        text=ftx('"-%6S" &new_line "-%6pu"')
        ctx=context(text,('F4','DOWN','7','ENTER','F3'),ports=rt.PortBank({'GIN':1},{('GIN',1):1}))
        values,_,_,_=execute(ctx=ctx,setup=SETUP+" values[1]='GIN[1]' values[2]='GIN[1]'")
        self.assertEqual((ctx.ports.values['GIN',1],values['STATUS']),(7,0));self.assertIn(('GIN',1),ctx.ports.simulated)

    def test_boolean_port_and_unsimulate_preserve_value(self):
        text=ftx('"-%4P" &new_line "-%5S"')
        ctx=context(text,('F4','DOWN','F5','F3'),ports=rt.PortBank({'DOUT':1},{('DOUT',1):False},simulated=[('DOUT',1)]))
        values,_,_,_=execute(ctx=ctx,setup=SETUP+" values[1]='DOUT[1]' values[2]='DOUT[1]'")
        self.assertTrue(ctx.ports.values['DOUT',1]);self.assertNotIn(('DOUT',1),ctx.ports.simulated)

    def test_inactive_items_are_skipped_and_default_is_continuous(self):
        values,_,_,_=execute(keys=('ENTER',),setup=SETUP+' inactive[1]=TRUE')
        self.assertEqual((values['N'],values['CHOSEN'],values['KEY']),(1,2,1008))

    def test_navigation_pages_and_fixed_title(self):
        text=ftx(' &new_line '.join('"- Item '+str(n)+'"' for n in range(1,9)))
        values,ctx,_,_=execute(text,keys=('END','PAGE_UP','HOME','PAGE_DOWN','ENTER'))
        self.assertEqual((values['CHOSEN'],values['KEY']),(4,1008));self.assertEqual(ctx.pendant.windows['FORM']['lines'][0].strip(),'Editor')

    def test_masked_enter_exits_before_opening_an_edit(self):
        values,_,_,_=execute(keys=('ENTER',),body=CALL.replace('KC_FUNC_KEY OR KC_PREV_KEY','KC_ENTER_KEY'))
        self.assertEqual((values['N'],values['KEY']),(1,13))

    def test_select_and_new_menu_always_terminate(self):
        for key,code in [('SELECT',1008),('NEW_MENU',1007)]:
            values,ctx,_,_=execute(keys=(key,),body=CALL.replace('KC_FUNC_KEY OR KC_PREV_KEY','0'))
            self.assertEqual(values['KEY'],code);self.assertEqual(ctx.forms.active_count,0)

    def test_select_commits_active_edit_and_new_menu_discards_it(self):
        for key,expected in [('SELECT',5),('NEW_MENU',1)]:
            values,_,_,_=execute(keys=('5',key))
            self.assertEqual(values['N'],expected);self.assertEqual(values['KEY'],1008 if key=='SELECT' else 1007)

    def test_read_only_input_port_enter_returns_selection(self):
        text=ftx('"-%4P"');ctx=context(text,('ENTER',),ports=rt.PortBank({'DIN':1},{('DIN',1):False}))
        values,_,_,_=execute(ctx=ctx,setup=SETUP+" values[1]='DIN[1]'")
        self.assertEqual((values['KEY'],values['STATUS']),(1008,0));self.assertFalse(ctx.ports.values['DIN',1])

    def test_display_only_form_has_no_selection(self):
        values,_,_,_=execute(ftx('"%4d"'))
        self.assertEqual((values['CHOSEN'],values['KEY'],values['STATUS']),(0,1103,0))

    def test_unsigned_maximum_and_short_sentinel_are_rejected_without_mutation(self):
        for fmt,path,text in [('%12d','N','2147483647'),('%6h','SHORT_VALUE[1]','32767'),('%4b','BYTE_VALUE[1]','256')]:
            values,_,_,_=execute(ftx('"-'+fmt+'"'),keys=tuple(text)+('ENTER','PREV','F3'),setup=SETUP+" values[1]='"+path+"'")
            self.assertFalse(values['CHANGED'][0]);self.assertEqual(values['STATUS'],0)


class FormHelpAndTreeTests(unittest.TestCase):
    def test_help_overlay_scrolls_and_prev_restores_form(self):
        text=ftx('"- Done" ^keys ?hint',extra='$2,keys "" &new_line "" &new_line "Exit" &new_line "" &new_line "HELP"\n$3,hint "Line 1" &new_line "Line 2" &new_line "Line 3" &new_line "Line 4" &new_line "Line 5" &new_line "Line 6"')
        values,ctx,_,_=execute(text,keys=('F5','DOWN','PAGE_DOWN','PREV','ENTER'))
        self.assertEqual((values['KEY'],values['STATUS']),(1008,0));self.assertEqual(ctx.pendant.windows['FORM']['lines'][0].strip(),'Editor')

    def test_disabled_form_function_keys_are_ignored(self):
        text=ftx('"- Done" ^keys',extra='$2,keys "" &new_line "Exit"')
        values,_,_,_=execute(text,keys=('F1','F2'))
        self.assertEqual(values['KEY'],1102)

    def test_function_key_labels_can_come_from_a_variable(self):
        text=ftx('"- Done" ^keys',extra='$2,keys "*T" &new_line "*FKEYS"')
        values,_,_,_=execute(text,keys=('F1','F3'),setup=SETUP+" fkeys[3]='Exit'")
        self.assertEqual(values['KEY'],1103)

    def test_tree_toggles_visibility_without_nested_groups(self):
        text=ftx('"-%t Group" &new_line "Number " "-%4d" &new_line\n.endtree\n"- Done"')
        values,_,_,_=execute(text,keys=('ENTER','DOWN','5','ENTER','DOWN','ENTER'),setup=SETUP+" values[1]='FLAG' values[2]='N'")
        self.assertEqual((values['FLAG'],values['N'],values['CHOSEN']),(True,5,3))

    def test_collapsed_children_are_skipped(self):
        text=ftx('"-%t Group" &new_line "-%4d" &new_line\n.endtree\n"- Done"')
        values,_,_,_=execute(text,keys=('DOWN','ENTER'),setup=SETUP+" values[1]='FLAG' values[2]='N'")
        self.assertEqual((values['CHOSEN'],values['N']),(3,1))

    def test_unknown_display_values_render_stars(self):
        text=ftx('"%4h" &new_line "- Done"')
        values,ctx,_,_=execute(text,keys=('ENTER',),setup=SETUP+" values[1]='SHORT_VALUE[1]'")
        self.assertEqual(values['STATUS'],0);self.assertTrue(ctx.pendant.windows['FORM']['lines'][2].startswith('*'))

    def test_numbered_forms_use_reserved_first_three_columns(self):
        text=ftx('@3,4 "- Done"',attributes='')
        values,ctx,_,_=execute(text,keys=('ENTER',))
        self.assertEqual(values['KEY'],1008);self.assertTrue(ctx.pendant.windows['FORM']['lines'][2].startswith(' 1  Done'))

    def test_noclear_preserves_untouched_background_and_file_cursor(self):
        text=ftx('"- Done"',attributes='unnumber noclear')
        body="DEF_WINDOW('FORM',5,24,WD_COM_CURSR,status) OPEN FILE f('WO','WD:FORM') SET_CURSOR(f,5,18,status) WRITE f('keep') SET_CURSOR(f,5,9,status) "+CALL+' CLOSE FILE f'
        values,ctx,_,_=execute(text,keys=('ENTER',),body=body,decl=DECL+' f:FILE')
        self.assertEqual(values['STATUS'],0);self.assertEqual(ctx.pendant.windows['FORM']['cursor']['col'],9)
        # Title overwrites its field; cells outside form text retain the saved background.
        self.assertEqual(ctx.pendant.windows['FORM']['lines'][4],' '*17+'keep'+' '*3)

    def test_dynamic_tree_repaints_after_live_value_change_during_wait(self):
        text=ftx('"%t Group" &new_line "-%4d" &new_line\n.endtree\n"- Done"')
        ctx=context(text,keys=(dict(key='F3',at_ms=25),));p,_=compile_program(LOAD+SETUP+" values[1]='FLAG' values[2]='N' "+CALL,decl=DECL,context=ctx,
            sleep=lambda _:p._state.values.__setitem__('FLAG',True))
        values=p.run();self.assertTrue(values['FLAG']);self.assertIn('   1',ctx.pendant.windows['FORM']['lines'][3])

    def test_continuation_text_does_not_create_another_selectable_item(self):
        text=ftx('"- Long +" &new_line "  continuation" &new_line "- Done"')
        values,_,_,_=execute(text,keys=('DOWN','ENTER'));self.assertEqual(values['CHOSEN'],2)


class FormGuardTests(unittest.TestCase):
    def test_wrong_menu_is_rejected_before_creating_window_or_consuming_input(self):
        values,ctx,_,_=execute(setup=SETUP.replace('SPI_TPUSER2','SPI_TPUSER'))
        self.assertEqual(values['STATUS'],1);self.assertNotIn('FORM',ctx.pendant.windows);self.assertEqual(len(ctx.keyboard.events),1)

    def test_wrong_type_layout_and_missing_paths_do_not_clear_changes(self):
        cases=[ftx('"-%4B"'),ftx('"-%80d"'),ftx('@4,1 "- First" @3,1 "- Second"')]
        for text in cases:
            with self.subTest(text=text):
                values,ctx,_,_=execute(text,setup=SETUP+' changed[1]=TRUE')
                self.assertEqual(values['STATUS'],1);self.assertTrue(values['CHANGED'][0]);self.assertEqual(ctx.keyboard.request_sequence,0)

    def test_data_cannot_alias_outputs(self):
        for path in ('CHOSEN','KEY','STATUS','INACTIVE[1]','CHANGED[1]'):
            text=ftx('"-%4B"') if '[' in path else ftx('"-%4d"')
            with self.subTest(path=path),self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps service outputs'):
                execute(text,setup=SETUP+" values[1]='"+path+"'")

    def test_incorrect_port_format_fails_closed(self):
        text=ftx('"-%4pu"');ctx=context(text,ports=rt.PortBank({'DIN':1},{('DIN',1):False}))
        values,_,_,_=execute(ctx=ctx,setup=SETUP+" values[1]='DIN[1]'")
        self.assertEqual(values['STATUS'],1);self.assertEqual(ctx.keyboard.request_sequence,0)

    def test_all_items_inactive_is_rejected(self):
        values,ctx,_,_=execute(setup=SETUP+' inactive[1]=TRUE inactive[2]=TRUE')
        self.assertEqual(values['STATUS'],1);self.assertEqual(ctx.forms.active_count,0)

    def test_direct_and_transitive_for_counter_guards(self):
        for routines,body in [('',CALL),('ROUTINE edit_form BEGIN '+CALL+' END edit_form','edit_form()')]:
            with self.subTest(body=body),self.assertRaises(TranslationError):
                compile_program('FOR n=1 TO 2 DO '+body+' ENDFOR',decl=DECL,routines=routines)

    def test_saved_active_form_and_interruption_cleanup(self):
        ctx=context(keys=(dict(key='F3',at_ms=25),));p,_=compile_program(LOAD+SETUP+' '+CALL,decl=DECL,context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        snapshot=json.loads(json.dumps(ctx.forms.snapshot()));self.assertEqual(snapshot['active'][0]['selected'],1)
        with self.assertRaisesRegex(ValueError,'Finish active forms'):ctx.to_config()
        p.stop();self.assertEqual(ctx.forms.active_count,0);self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.to_config()

    def test_budget_failure_and_missing_keys_release_sessions(self):
        for keys,budget in [((),100),( (dict(key='F3',at_ms=10000),),30)]:
            ctx=context(keys=keys);p,_=compile_program(LOAD+SETUP+' '+CALL,decl=DECL,context=ctx,sleep=lambda _:None)
            with self.assertRaises(rt.KarelRuntimeError):p.run(max_steps=budget)
            self.assertEqual(ctx.forms.active_count,0);self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.to_config()

    def test_history_exhaustion_still_allows_task_cleanup(self):
        ctx=context(keys=(dict(key='F3',at_ms=25),));p,_=compile_program(LOAD+SETUP+' '+CALL,decl=DECL,context=ctx,sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        ctx.pendant.sequence=2147483646;ctx.keyboard.sequence=2147483646;p.stop()
        self.assertEqual(ctx.forms.active_count,0);self.assertEqual(ctx.pendant.screens['SYS']['attachments'],[]);ctx.to_config()

    def test_form_context_and_missing_service_are_checked(self):
        for config in ({'unknown':0},{'rows':2},{'cols':0},{'limit':False},{'window':'TOOLONG'}):
            with self.subTest(config=config),self.assertRaises(ValueError):rt.FormControls.from_config(config)
        ctx=context();ctx.forms=None
        with self.assertRaisesRegex(rt.KarelRuntimeError,'forms'):execute(ctx=ctx)

    def test_foreign_program_data_paths_are_captured_and_edited(self):
        main=source('MAIN',LOAD+SETUP+" values[1]='[LIB]N' "+CALL,decl=DECL)
        library=source('LIB','',decl='n:INTEGER')
        ctx=context(keys=('4','ENTER','F3'));instance=translate_project({'main.kl':main,'lib.kl':library}).instantiate(context=ctx)
        result=instance.run('MAIN');self.assertEqual(result['LIB']['values']['N'],4)

    def test_source_step_budget_preserves_shared_attachment(self):
        ctx=context(keys=(dict(key='F3',at_ms=10000),));body=LOAD+SETUP+" DEF_WINDOW('FORM',5,24,0,status) ATT_WINDOW_S('FORM','SYS',1,1,status) "+CALL
        p,_=compile_program(body,decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaises(rt.KarelRuntimeError):p.run(max_steps=50)
        self.assertEqual(len(ctx.pendant.screens['SYS']['attachments']),1);self.assertEqual(ctx.forms.active_count,0)

    def test_form_sequence_exhaustion_preserves_changes(self):
        ctx=context();ctx.forms.sequence=2147483646
        values,_,_,_=execute(ctx=ctx,setup=SETUP+' changed[1]=TRUE')
        self.assertEqual(values['STATUS'],1);self.assertTrue(values['CHANGED'][0]);self.assertNotIn('FORM',ctx.pendant.windows)


class FtxDictionaryTests(unittest.TestCase):
    def test_report_describes_offline_form_contract(self):
        _,_,_,result=execute()
        policy=result.report['form_policy']
        self.assertEqual(policy['calls'],['DISCTRL_FORM']);self.assertFalse(policy['controller_validated'])
        self.assertEqual(policy['guide'],'docs/forms.md')

    def test_form_loading_roundtrip_and_named_check(self):
        values,ctx,_,_=execute(body="CHECK_DICT('FORM','editor',status)")
        self.assertEqual(values['STATUS'],0);restored=rt.ExecutionContext.from_config(ctx.to_config())
        self.assertEqual(restored.dictionaries.to_config(),ctx.dictionaries.to_config())

    def test_form_data_cannot_be_silently_read_as_plain_dictionary(self):
        values,_,_,_=execute(body="READ_DICT('FORM',1,values,1,chosen,status)")
        self.assertEqual(values['STATUS'],4);self.assertEqual(values['CHOSEN'],1)

    def test_malformed_directives_and_unsupported_attributes_are_rejected(self):
        for document in ['.form\n$1 "x"','.endform','.form strange\n$1 "x"\n.endform',
            '.form\n$1 "x"\n$2 "y"\n.endform',' .form\n.form\n$1 "x"\n.endform',
            '$1 "plain" ^keys','.form\n$1 "x" .endform','.form\n"no header"\n$1 "x"\n.endform',
            '.form\n$1 "x"\n.endform\n"trailing content"']:
            with self.subTest(document=document),self.assertRaises(ValueError):parse(document)

    def test_ordinary_dictionary_elements_can_share_form_source(self):
        document=ftx(extra='$2 "ordinary"')
        values,_,_,_=execute(document,body="READ_DICT('FORM',2,values,1,chosen,status)")
        self.assertEqual((values['VALUES'][0],values['STATUS']),('ordinary',0))


if __name__=='__main__':unittest.main()
