"""Authored headless table/list translation, edits and lifetime checks."""
import json
import unittest

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program


DECL='''s,row,key,action:INTEGER attach:BOOLEAN
cols:ARRAY[2] OF COL_DESC_T inactive:ARRAY[2] OF BOOLEAN
changed:ARRAY[2,2] OF BOOLEAN paths:ARRAY[2] OF STRING[40]
data:ARRAY[2] OF INTEGER words:ARRAY[2] OF STRING[20]
reals:ARRAY[2] OF REAL flags:ARRAY[2] OF BOOLEAN
bytes:ARRAY[2] OF BYTE shorts:ARRAY[2] OF SHORT
ptrs:ARRAY[2,2] OF INTEGER work:XWORK_T'''
SETUP="""DEF_WINDOW('TABL',4,20,0,s)
ADD_DICT('header','HEAD',DP_DEFAULT,DP_DRAM,s)
cols[1].item_type=TPX_INT_ITEM cols[1].start_col=1 cols[1].field_width=8
cols[2].item_type=TPX_KST_ITEM cols[2].start_col=10 cols[2].field_width=10
paths[1]='DATA' paths[2]='WORDS' data[1]=1 data[2]=2 words[1]='old' words[2]='next'
row=1 attach=TRUE"""
TABLE="DISCTRL_TBL('HEAD',1,2,2,cols,inactive,changed,row,key,KC_FUNC_KEY OR KC_OTHER,paths,TRUE,s)"
INIT="INIT_TBL('HEAD',1,2,2,cols,inactive,changed,paths,ptrs,work,s)"
ACT='ACT_TBL(action,row,work,key,attach,s)'
DISPLAY='ACT_TBL(KY_DISP_UPDT,row,work,key,attach,s)'
CANCEL='ACT_TBL(KY_CANCEL,row,work,key,attach,s)'


def context(keys=(),**services):
    return rt.ExecutionContext(table_controls=rt.TableControls(),pendant=rt.PendantDisplay(rows=4,cols=20),
        keyboard=rt.KeyboardInput(events=[{'key':key} if type(key) is str else key for key in keys]),
        dictionaries=rt.TextDictionaries(sources={'header':'$1 "Numbers"\n$2 "Off" &new_line "On"\n$3 "Red" &new_line "Blue"\n$4 "Small"\n$5 "Large"\n$6 ""'}),**services)


def execute(body=TABLE,keys=('SELECT',),*,ctx=None,decl=DECL):
    ctx=ctx or context(keys);program,result=compile_program(SETUP+' '+body,decl=decl,context=ctx,sleep=lambda _:None)
    return program.run(),ctx,program,result


class TableEditingTests(unittest.TestCase):
    def test_typed_integer_edit_updates_backing_array_and_change_grid(self):
        values,ctx,_,_=execute(keys=('5','ENTER','DOWN','SELECT'))
        self.assertEqual((values['DATA'],values['ROW'],values['KEY'],values['S']),([5,2],2,1008,0))
        self.assertEqual(values['CHANGED'],[[True,False],[False,False]])
        self.assertTrue(ctx.pendant.windows['TABL']['lines'][1].startswith('5'))
        self.assertEqual(ctx.table_controls.active_count,0);self.assertEqual(ctx.pendant.screens['SYS']['attachments'],[])
        rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))

    def test_string_clear_and_uppercase_default(self):
        values,_,_,_=execute('cols[2].clear_flag=1 '+TABLE,keys=('RIGHT','a','b','ENTER','F2'))
        self.assertEqual((values['WORDS'][0],values['KEY']),('AB',1102))

    def test_string_append_and_lowercase(self):
        values,_,_,_=execute('cols[2].lower_case=1 '+TABLE,keys=('RIGHT','x','ENTER','SELECT'))
        self.assertEqual(values['WORDS'][0],'oldx')

    def test_cursor_delete_home_and_end_edit_existing_value(self):
        values,_,_,_=execute('cols[2].lower_case=1 '+TABLE,
            keys=('RIGHT','ENTER','HOME','a','END','DELETE','ENTER','SELECT'))
        self.assertEqual(values['WORDS'][0],'aol')

    def test_prev_discards_edit_before_next_prev_terminates(self):
        values,_,_,_=execute(keys=('9','PREV','PREV'))
        self.assertEqual((values['DATA'],values['KEY'],values['S']),([1,2],1005,0))

    def test_real_edit(self):
        values,_,_,_=execute("cols[1].item_type=TPX_REL_ITEM paths[1]='REALS' "+TABLE,keys=('1','.','5','ENTER','SELECT'))
        self.assertEqual(values['REALS'][0],1.5)

    def test_boolean_toggle(self):
        values,_,_,_=execute("cols[1].item_type=TPX_KBL_ITEM paths[1]='FLAGS' "+TABLE,keys=('ENTER','SELECT'))
        self.assertTrue(values['FLAGS'][0])

    def test_byte_and_short_entry(self):
        for item,path,value in [('TPX_BYT_ITEM','BYTES','255'),('TPX_SHT_ITEM','SHORTS','-32768')]:
            with self.subTest(item=item):
                values,_,_,_=execute(f"cols[1].item_type={item} paths[1]='{path}' "+TABLE,keys=tuple(value)+('ENTER','SELECT'))
                self.assertEqual(values[path][0],int(value))

    def test_range_and_type_failures_preserve_live_value(self):
        for text in ('12','-1','x','1e9999'):
            with self.subTest(text=text):
                values,ctx,_,_=execute('cols[1].min_integer=0 cols[1].max_integer=10 '+TABLE,keys=tuple(text)+('ENTER','SELECT'))
                self.assertEqual((values['DATA'][0],values['S']),(1,1));self.assertFalse(values['CHANGED'][0][0])
                self.assertEqual(ctx.table_controls.active_count,0)

    def test_selectable_string_enter_returns_selection(self):
        values,_,_,_=execute('cols[2].item_type=TPX_KSL_ITEM '+TABLE,keys=('RIGHT','ENTER'))
        self.assertEqual((values['WORDS'][0],values['KEY']),('old',1008))

    def test_inactive_column_is_skipped(self):
        values,_,_,_=execute('inactive[1]=TRUE '+TABLE,keys=('LEFT','x','ENTER','SELECT'))
        self.assertEqual((values['DATA'][0],values['WORDS'][0]),(1,'OLDX'))

    def test_function_and_submenu_enum_numeric_indices(self):
        for item,element in [('TPX_FKY_ITEM',3),('TPX_SUB_ITEM',4)]:
            with self.subTest(item=item):
                values,ctx,_,_=execute(f"cols[1].item_type={item} cols[1].enum_dict='HEAD' cols[1].enum_ele={element} "+TABLE,keys=('2','ENTER','SELECT'))
                self.assertEqual((values['DATA'][0],values['S']),(2,0))
                self.assertIn('Blue' if element==3 else 'Large',ctx.pendant.windows['TABL']['lines'][1])

    def test_output_and_simulated_input_port_columns(self):
        for kind,item,keys,expected in [('GOUT','TPX_PIN_ITEM',('RIGHT','7','ENTER','SELECT'),7),('DIN','TPX_PBL_ITEM',('RIGHT','ENTER','SELECT'),True)]:
            with self.subTest(kind=kind):
                bank=rt.PortBank({kind:2},simulated=[(kind,1),(kind,2)])
                ctx=context(keys,ports=bank)
                values,_,_,_=execute(f"cols[2].item_type={item} words[1]='{kind}[1]' words[2]='{kind}[2]' "+TABLE,ctx=ctx)
                self.assertEqual((bank.values[kind,1],values['S']),(expected,0))

    def test_unsimulated_input_port_is_selectable_and_unchanged(self):
        bank=rt.PortBank({'DIN':2},{('DIN',1):False,('DIN',2):True});ctx=context(('RIGHT','ENTER'),ports=bank)
        values,_,_,_=execute("cols[2].item_type=TPX_PBL_ITEM words[1]='DIN[1]' words[2]='DIN[2]' "+TABLE,ctx=ctx)
        self.assertEqual((values['KEY'],bank.values['DIN',1]),(1008,False))

    def test_delayed_injected_keys_advance_cooperative_clock(self):
        ctx=context((dict(key='DOWN',at_ms=20),dict(key='SELECT',at_ms=30)))
        values,_,_,_=execute(ctx=ctx);self.assertEqual(values['ROW'],2);self.assertEqual(ctx.keyboard.elapsed_ms,30)

    def test_termination_mask_can_select_navigation_class(self):
        values,_,_,_=execute(TABLE.replace('KC_FUNC_KEY OR KC_OTHER','KC_UD_ARW'),keys=('DOWN',))
        self.assertEqual((values['KEY'],values['S']),(1004,0))

    def test_string_destination_capacity_failure_preserves_old_value(self):
        values,_,_,_=execute('cols[2].clear_flag=1 '+TABLE,keys=('RIGHT',)+tuple('x'*21)+('ENTER',),
            decl=DECL)
        self.assertEqual((values['WORDS'][0],values['S']),('old',1))

    def test_byte_and_short_out_of_range_are_rejected(self):
        for item,path,text in [('TPX_BYT_ITEM','BYTES','256'),('TPX_SHT_ITEM','SHORTS','32767')]:
            values,_,_,_=execute(f"cols[1].item_type={item} paths[1]='{path}' "+TABLE,keys=tuple(text)+('ENTER',))
            self.assertEqual(values['S'],1);self.assertFalse(values['CHANGED'][0][0])

    def test_format_prefix_percent_and_width(self):
        values,ctx,_,_=execute("cols[1].format_spec='n=%03d%%' "+TABLE)
        self.assertEqual(values['S'],0);self.assertTrue(ctx.pendant.windows['TABL']['lines'][1].startswith('n=001%'))

    def test_space_flag_real_precision_and_character_byte(self):
        for setup,expected in [("cols[1].item_type=TPX_REL_ITEM paths[1]='REALS' reals[1]=1.5 cols[1].format_spec='% .1f'",' 1.5'),
            ("cols[1].item_type=TPX_BYT_ITEM paths[1]='BYTES' bytes[1]=65 cols[1].format_spec='%c'",'A')]:
            values,ctx,_,_=execute(setup+' '+TABLE)
            self.assertEqual(values['S'],0);self.assertTrue(ctx.pendant.windows['TABL']['lines'][1].startswith(expected))


class TableSessionTests(unittest.TestCase):
    def test_init_act_literal_commands_and_logical_pointer_grid(self):
        values,ctx,_,_=execute(INIT+' '+DISPLAY+' action=KY_DN_ARW '+ACT+' '+CANCEL,keys=())
        self.assertEqual((values['ROW'],values['S'],values['WORK']['SESSION']),(2,0,0))
        self.assertEqual(values['PTRS'],[[1,2],[3,4]]);self.assertEqual(ctx.table_controls.active_count,0)

    def test_reissue_writes_actual_action_key(self):
        values,_,_,_=execute(INIT+' '+DISPLAY+' action=KY_REISSUE '+ACT+' '+CANCEL,keys=('DOWN',))
        self.assertEqual(values['ACTION'],1004)

    def test_new_menu_cancels_session(self):
        values,ctx,_,_=execute(INIT+' '+DISPLAY+' action=KY_REISSUE '+ACT,keys=('NEW_MENU',))
        self.assertEqual((values['KEY'],values['WORK']['SESSION']),(1007,0));ctx.to_config()

    def test_active_session_blocks_save_and_cancel_allows_save(self):
        values,ctx,p,_=execute(INIT+' '+DISPLAY,keys=())
        with self.assertRaisesRegex(ValueError,'Cancel active tables'):ctx.to_config()
        session=next(iter(ctx.table_controls._sessions.values()));ctx.table_controls.close(session)
        ctx.to_config();self.assertEqual(p.snapshot()['WORK']['SESSION'],0)

    def test_cancel_after_display_sequence_exhaustion(self):
        _,ctx,_,_=execute(INIT+' '+DISPLAY,keys=());ctx.pendant.sequence=2147483646
        session=next(iter(ctx.table_controls._sessions.values()));ctx.table_controls.close(session)
        self.assertEqual(ctx.table_controls.active_count,0);ctx.to_config()

    def test_preexisting_attachment_survives_cleanup(self):
        values,ctx,_,_=execute("ATT_WINDOW_S('TABL','SYS',1,1,s) "+TABLE)
        self.assertEqual(values['S'],0);self.assertEqual(len(ctx.pendant.screens['SYS']['attachments']),1)

    def test_ordinary_window_file_cursor_is_preserved(self):
        values,ctx,_,_=execute("OPEN FILE f('WO','WD:TABL') SET_CURSOR(f,4,7,s) "+TABLE+' CLOSE FILE f',decl=DECL+' f:FILE')
        self.assertEqual(ctx.pendant.windows['TABL']['cursor']['col'],7)

    def test_invalid_preparation_preserves_flags_pointers_and_keyboard_queue(self):
        for amendment in ("paths[1]='WORDS'",'cols[1].start_col=0','cols[1].field_width=21',
            'cols[2].start_col=2','inactive[1]=TRUE inactive[2]=TRUE',"cols[1].format_spec='%s'",
            'cols[1].min_integer=10 cols[1].max_integer=1'):
            with self.subTest(amendment=amendment):
                values,ctx,_,_=execute(amendment+' '+INIT)
                self.assertEqual(values['S'],1);self.assertEqual(values['PTRS'][0][0],{'uninitialized':True})
                self.assertEqual(values['CHANGED'][0][0],{'uninitialized':True});self.assertEqual(len(ctx.keyboard.events),1)

    def test_missing_static_path_fails_closed(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'static declared global'):
            execute("paths[1]='MISSING' "+INIT)

    def test_missing_injected_keys_releases_internal_session(self):
        ctx=context(())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit queued input'):execute(ctx=ctx)
        self.assertEqual(ctx.table_controls.active_count,0);self.assertEqual(ctx.keyboard.history[-1]['outcome'],'failed');ctx.to_config()

    def test_table_output_cannot_alias_backing_data(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps service outputs'):
            execute(INIT+' '+DISPLAY+' ACT_TBL(KY_DN_ARW,row,work,data[1],attach,s)')

    def test_indirect_editor_is_blocked_in_active_for_scope(self):
        for body in (TABLE,ACT):
            with self.subTest(body=body),self.assertRaises(TranslationError):
                compile_program('FOR row=1 TO 2 DO '+body+' ENDFOR',decl=DECL)

    def test_unrelated_output_procedures_still_reject_constants(self):
        with self.assertRaises(TranslationError):compile_program('GET_TIME(MAXINT)')

    def test_record_types_and_manager_configuration_are_checked(self):
        for config in ({'unknown':True},{'limit':0},{'sequence':True},{'window':'TOOLONG'}):
            with self.subTest(config=config),self.assertRaises(ValueError):rt.TableControls.from_config(config)
        for amendment in ('cols:ARRAY[2] OF INTEGER','work:INTEGER'):
            decl=DECL.replace('cols:ARRAY[2] OF COL_DESC_T',amendment) if amendment.startswith('cols') else DECL.replace('work:XWORK_T',amendment)
            with self.subTest(amendment=amendment),self.assertRaises(TranslationError):compile_program(INIT,decl=decl)

    def test_translation_report_exposes_portable_table_contract(self):
        _,_,_,result=execute(INIT+' '+CANCEL,keys=())
        policy=result.report['table_control_policy']
        self.assertEqual(set(policy['calls']),rt.TABLE_CALLS);self.assertEqual(policy['constants']['KY_REISSUE'],1010)
        self.assertFalse(policy['controller_validated']);self.assertEqual(policy['guide'],'docs/table-controls.md')

    def test_indirect_editor_routine_cannot_write_an_active_for_counter(self):
        with self.assertRaises(TranslationError):compile_program('FOR row=1 TO 2 DO edit_table() ENDFOR',
            decl=DECL,routines='ROUTINE edit_table BEGIN '+TABLE+' END edit_table')

    def test_shared_manager_attachment_survives_until_last_session_closes(self):
        _,ctx,_,_=execute(INIT+' '+INIT.replace('work,s','second,s'),decl=DECL+' second:XWORK_T',keys=())
        first,second=ctx.table_controls._sessions.values()
        ctx.table_controls.display(first,True);ctx.table_controls.display(second,True)
        ctx.table_controls.close(first);self.assertEqual(len(ctx.pendant.screens['SYS']['attachments']),1)
        ctx.table_controls.close(second);self.assertEqual(ctx.pendant.screens['SYS']['attachments'],[])

    def test_maxint_edit_is_rejected_with_portable_status(self):
        values,_,_,_=execute(keys=tuple('2147483647')+('ENTER',))
        self.assertEqual((values['DATA'][0],values['S']),(1,1))

    def test_budget_failure_releases_internal_table_and_keyboard_request(self):
        ctx=context((dict(key='SELECT',at_ms=10000),));p,_=compile_program(SETUP+' '+TABLE,decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=60)
        self.assertEqual(ctx.table_controls.active_count,0);self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.to_config()

    def test_interrupting_act_releases_prepared_session(self):
        ctx=context((dict(key='SELECT',at_ms=10000),));body=SETUP+' '+INIT+' '+DISPLAY+' action=KY_REISSUE '+ACT
        p,_=compile_program(body,decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=65)
        self.assertEqual(ctx.table_controls.active_count,0);self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.to_config()

    def test_unused_change_grid_placeholder_is_accepted(self):
        values,_,_,_=execute(keys=('5','ENTER','SELECT'),decl=DECL.replace('changed:ARRAY[2,2]','changed:ARRAY[1]'))
        self.assertEqual((values['DATA'][0],values['S']),(5,0))

    def test_small_change_grid_records_available_cells_only(self):
        values,_,_,_=execute(keys=('DOWN','5','ENTER','SELECT'),decl=DECL.replace('changed:ARRAY[2,2]','changed:ARRAY[1,1]'))
        self.assertEqual((values['DATA'],values['CHANGED']),([1,5],[[False]]))

    def test_init_does_not_reinitialize_active_session(self):
        values,ctx,_,_=execute(INIT+' '+INIT,keys=())
        self.assertEqual((values['S'],ctx.table_controls.sequence,ctx.table_controls.active_count),(1,1,1))
        ctx.table_controls.close(next(iter(ctx.table_controls._sessions.values())))

    def test_small_pointer_grid_is_rejected_before_any_changes(self):
        values,ctx,_,_=execute(INIT,decl=DECL.replace('ptrs:ARRAY[2,2]','ptrs:ARRAY[1,1]'))
        self.assertEqual((values['S'],ctx.table_controls.active_count),(1,0))
        self.assertEqual(values['CHANGED'][0][0],{'uninitialized':True})

    def test_live_inactive_flags_and_array_replacement_are_observed(self):
        values,_,_,_=execute(INIT+' '+DISPLAY+" inactive[1]=TRUE words[1]='live' action=KY_RT_ARW "+ACT+' '+CANCEL,keys=())
        self.assertEqual((values['WORDS'][0],values['S']),('live',0))

    def test_exhausted_manager_and_display_sequences_do_not_leak_session(self):
        ctx=context(('SELECT',));ctx.table_controls.sequence=2147483646
        values,_,_,_=execute(INIT,ctx=ctx);self.assertEqual((values['S'],ctx.table_controls.active_count),(1,0))
        ctx=context(('SELECT',));_,ctx,_,_=execute(INIT,ctx=ctx)
        session=next(iter(ctx.table_controls._sessions.values()));ctx.pendant.sequence=2147483646
        with self.assertRaises(rt.KarelRuntimeError):ctx.table_controls.display(session,True)
        ctx.table_controls.close(session);ctx.to_config()

    def test_foreign_record_cannot_act_on_another_session(self):
        values,ctx,_,_=execute(INIT+' second.session=work.session ACT_TBL(KY_CANCEL,row,second,key,attach,s)',
            decl=DECL+' second:XWORK_T',keys=())
        self.assertEqual((values['S'],ctx.table_controls.active_count),(3,1))
        ctx.table_controls.close(next(iter(ctx.table_controls._sessions.values())))

    def test_snapshot_does_not_expose_live_reference_objects(self):
        _,ctx,_,_=execute(INIT,keys=())
        snapshot=json.loads(json.dumps(ctx.table_controls.snapshot()));self.assertEqual(snapshot['active'][0]['column'],1)
        ctx.table_controls.close(next(iter(ctx.table_controls._sessions.values())))

    def test_missing_service_and_strict_mode_fail_closed(self):
        ctx=context();ctx.table_controls=None
        with self.assertRaisesRegex(rt.KarelRuntimeError,'table_controls'):execute(ctx=ctx)
        from karel2py import translate
        with self.assertRaises(TranslationError):translate('PROGRAM T VAR w:XWORK_T BEGIN END T',mode='strict')


LIST_DECL='f:FILE d:DISP_DAT_T items:ARRAY[5] OF STRING[20] s:INTEGER'
LIST_SETUP="""DEF_WINDOW('LIST',3,12,0,s) OPEN FILE f('WO','WD:LIST')
d.curr_win=0 d.win_start[1]=1 d.win_end[1]=3 d.cursor_row=1 d.lins_per_pg=3
d.last_field=1 d.curr_field=0 d.curs_st_col[1]=0 d.curs_en_col[1]=3 d.curs_st_col[2]=5 d.curs_en_col[2]=9
d.curr_it_num=1 d.sob_it_num=1 d.eob_it_num=5 d.last_it_num=5
items[1]='one' items[2]='two' items[3]='three' items[4]='four' items[5]='five'"""


class ResidentListTests(unittest.TestCase):
    def execute(self,body):
        ctx=context(());p,result=compile_program(LIST_SETUP+' '+body+' CLOSE FILE f',decl=LIST_DECL,context=ctx)
        return p.run(),ctx

    def test_scrolls_resident_rows_and_moves_cursor(self):
        body='DISCTRL_LIST(f,d,items,DC_DISP,s) '+'DISCTRL_LIST(f,d,items,DC_DN,s) '*4+'DISCTRL_LIST(f,d,items,DC_RT,s)'
        values,ctx=self.execute(body)
        self.assertEqual((values['D']['CURR_IT_NUM'],values['D']['CURSOR_ROW'],values['D']['CURR_FIELD'],values['S']),(5,3,1,0))
        self.assertEqual(ctx.pendant.windows['LIST']['lines'],['three       ','four        ','five        '])
        self.assertEqual(ctx.pendant.windows['LIST']['cursor']['col'],6)

    def test_up_and_left_clamp(self):
        values,_,=self.execute('DISCTRL_LIST(f,d,items,DC_UP,s) DISCTRL_LIST(f,d,items,DC_LF,s)')
        self.assertEqual((values['D']['CURR_IT_NUM'],values['D']['CURR_FIELD']),(1,0))

    def test_invalid_unused_fields_can_remain_uninitialized(self):
        values,_=self.execute('DISCTRL_LIST(f,d,items,DC_DISP,s)')
        self.assertEqual(values['S'],0);self.assertEqual(values['D']['MENU_ID'],{'uninitialized':True})

    def test_invalid_layout_preserves_window(self):
        values,ctx=self.execute('d.curs_en_col[1]=20 DISCTRL_LIST(f,d,items,DC_DISP,s)')
        self.assertEqual(values['S'],1);self.assertEqual(ctx.pendant.windows['LIST']['lines'],[' '*12]*3)

    def test_list_requires_open_window_file(self):
        values,_=self.execute('CLOSE FILE f DISCTRL_LIST(f,d,items,DC_DISP,s) OPEN FILE f(\'WO\',\'WD:LIST\')')
        self.assertEqual(values['S'],1)

    def test_resident_absolute_item_numbers_need_no_fetch(self):
        values,ctx=self.execute('d.sob_it_num=10 d.eob_it_num=14 d.last_it_num=30 d.curr_it_num=10 DISCTRL_LIST(f,d,items,DC_DN,s)')
        self.assertEqual((values['D']['CURR_IT_NUM'],values['S']),(11,0))
        self.assertEqual(ctx.pendant.windows['LIST']['lines'][0].strip(),'one')

    def test_list_accepts_combined_writable_endpoint(self):
        ctx=context(());p,_=compile_program(LIST_SETUP.replace("'WO','WD:LIST'","'RW','WD:LIST/TPKB'")+ ' DISCTRL_LIST(f,d,items,DC_DISP,s) CLOSE FILE f',decl=LIST_DECL,context=ctx)
        self.assertEqual(p.run()['S'],0);ctx.to_config()


if __name__=='__main__':unittest.main()
