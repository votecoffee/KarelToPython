"""Authored headless display, window FILE and request persistence scenarios."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source

DECL='f,g:FILE old:STRING[4] s,n:INTEGER'
SETUP="DEF_SCREEN('SCR','TP',s) DEF_WINDOW('W1',2,4,0,s)"
ACTIVATE="FORCE_SPMENU(TP_PANEL,SPI_TPUSER,1) ACT_SCREEN('SCR',old,s)"


def context(**options):return rt.ExecutionContext(pendant=rt.PendantDisplay(rows=4,cols=8,**options))


def execute(body,*,ctx=None,**options):
    ctx=context() if ctx is None else ctx
    p,result=compile_program(body,decl=options.pop('decl',DECL),context=ctx,**options)
    values=p.run();return values,ctx,p,result


class DisplayDefinitionTests(unittest.TestCase):
    def test_define_screen_and_window(self):
        values,ctx,_,_=execute(SETUP)
        self.assertEqual(values['S'],0)
        self.assertEqual(ctx.pendant.windows['W1']['lines'],['    ','    '])
        self.assertEqual(ctx.pendant.screens['SCR'],{'device':'TP','attachments':[]})

    def test_names_are_case_insensitive(self):
        values,ctx,_,_=execute("DEF_SCREEN('scr','tp',s) DEF_WINDOW('win',1,2,0,s)")
        self.assertEqual(values['S'],0);self.assertIn('WIN',ctx.pendant.windows)

    def test_invalid_names_return_status_without_creating_resources(self):
        for name in ('','ABCDE','a/b','1ABC'):
            with self.subTest(name=name):
                values,ctx,_,_=execute("DEF_SCREEN('"+name+"','TP',s)")
                self.assertEqual(values['S'],1);self.assertEqual(set(ctx.pendant.screens),{'SYS'})

    def test_unknown_display_device_rejected(self):
        values,ctx,_,_=execute("DEF_SCREEN('SCR','UNKNOWN',s)")
        self.assertEqual(values['S'],1);self.assertNotIn('SCR',ctx.pendant.screens)

    def test_duplicate_definition_does_not_replace_existing_data(self):
        values,ctx,_,_=execute(SETUP+" DEF_WINDOW('W1',3,3,0,s)")
        self.assertEqual(values['S'],2);self.assertEqual(ctx.pendant.windows['W1']['cols'],4)

    def test_window_size_and_option_validation(self):
        for rows,cols,options in ((0,4,0),(2,-1,0),(257,1,0),(1,1,4)):
            with self.subTest(values=(rows,cols,options)):
                values,ctx,_,_=execute(f"DEF_WINDOW('W1',{rows},{cols},{options},s)")
                self.assertEqual(values['S'],1);self.assertEqual(ctx.pendant.windows,{})

    def test_total_window_cell_budget_is_preflighted(self):
        values,ctx,_,_=execute("DEF_WINDOW('W1',2,4,0,s)",ctx=context(max_cells=7))
        self.assertEqual(values['S'],5);self.assertEqual(ctx.pendant.windows,{})

    def test_attach_and_composite_surface(self):
        _,ctx,_,_=execute(SETUP+" ATT_WINDOW_S('W1','SCR',2,3,s) OPEN FILE f('RW','WD:W1') WRITE f('Hi') CLOSE FILE f")
        self.assertEqual(ctx.pendant.render('SCR'),['        ','  Hi    ','        ','        '])

    def test_attachment_must_fit_entirely(self):
        values,ctx,_,_=execute(SETUP+" ATT_WINDOW_S('W1','SCR',4,1,s)")
        self.assertEqual(values['S'],1);self.assertEqual(ctx.pendant.screens['SCR']['attachments'],[])

    def test_duplicate_attachment_rejected(self):
        values,ctx,_,_=execute(SETUP+" ATT_WINDOW_S('W1','SCR',1,1,s) ATT_WINDOW_S('W1','SCR',2,2,s)")
        self.assertEqual(values['S'],2);self.assertEqual(len(ctx.pendant.screens['SCR']['attachments']),1)

    def test_one_window_can_belong_to_multiple_screens(self):
        values,ctx,_,_=execute(SETUP+" ATT_WINDOW_S('W1','SCR',1,1,s) ATT_WINDOW_S('W1','SYS',2,1,s)")
        self.assertEqual(values['S'],0)
        self.assertEqual(len(ctx.pendant.screens['SYS']['attachments']),1)

    def test_activation_requires_user_menu(self):
        values,ctx,_,_=execute(SETUP+" ACT_SCREEN('SCR',old,s)")
        self.assertEqual(values['S'],9093);self.assertEqual(ctx.pendant.active['TP'],'SYS')
        self.assertEqual(values['OLD'],{'uninitialized':True})

    def test_activation_returns_old_screen(self):
        values,ctx,_,_=execute(SETUP+' '+ACTIVATE)
        self.assertEqual((values['S'],values['OLD']),(0,'SYS'));self.assertEqual(ctx.pendant.active['TP'],'SCR')

    def test_small_old_screen_output_does_not_switch_screen(self):
        values,ctx,_,_=execute(SETUP+' '+ACTIVATE,decl=DECL.replace('STRING[4]','STRING[1]'))
        self.assertEqual(values['S'],5);self.assertEqual(ctx.pendant.active['TP'],'SYS')

    def test_attach_to_active_device_returns_screen(self):
        values,ctx,_,_=execute(SETUP+' '+ACTIVATE+" ATT_WINDOW_D('W1','TP',1,1,old,s)")
        self.assertEqual((values['OLD'],values['S']),('SCR',0))
        self.assertEqual(ctx.pendant.screens['SCR']['attachments'][0]['window'],'W1')

    def test_small_active_screen_output_does_not_attach(self):
        values,ctx,_,_=execute(SETUP+" ATT_WINDOW_D('W1','TP',1,1,old,s)",decl=DECL.replace('STRING[4]','STRING[1]'))
        self.assertEqual(values['S'],5)
        self.assertEqual(ctx.pendant.screens['SYS']['attachments'],[])

    def test_detach_redisplays_underlying_window(self):
        body=SETUP+" DEF_WINDOW('W2',1,2,0,s) ATT_WINDOW_S('W1','SCR',1,1,s) ATT_WINDOW_S('W2','SCR',1,2,s) OPEN FILE f('RW','WD:W1') WRITE f('ABCD') CLOSE FILE f OPEN FILE f('RW','WD:W2') WRITE f('zz') CLOSE FILE f DET_WINDOW('W2','SCR',s)"
        values,ctx,_,_=execute(body)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.pendant.render('SCR')[0],'ABCD    ')

    def test_detach_unknown_attachment_has_no_side_effect(self):
        values,ctx,_,_=execute(SETUP+" DET_WINDOW('W1','SCR',s)")
        self.assertEqual(values['S'],4);self.assertEqual(ctx.pendant.screens['SCR']['attachments'],[])


class DisplayRequestAndLanguageTests(unittest.TestCase):
    def test_force_link_retains_opaque_location_without_opening_it(self):
        _,ctx,_,_=execute("FORCE_LINK(TP2_PANEL,'http://example.invalid/panel')")
        self.assertEqual(ctx.pendant.links,{'2':'http://example.invalid/panel'})
        self.assertEqual(ctx.pendant.history[-1]['operation'],'FORCE_LINK')

    def test_refresh_and_current_links_are_not_interpreted(self):
        _,ctx,_,_=execute("FORCE_LINK(TP_PANEL,'current=/fr/demo.stm') FORCE_LINK(TP3_PANEL,'refresh=third')")
        self.assertEqual(ctx.pendant.links,{'1':'current=/fr/demo.stm','3':'refresh=third'})

    def test_invalid_pane_does_not_add_request(self):
        ctx=context();p,_=compile_program("FORCE_LINK(0,'/fr/demo.stm')",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.pendant.history,[])

    def test_empty_link_is_rejected_without_history_or_state_changes(self):
        ctx=context();p,_=compile_program("FORCE_LINK(TP_PANEL,'')",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.pendant.links,{})
        self.assertEqual(ctx.pendant.sequence,0)

    def test_menu_requests_have_portable_symbolic_ids(self):
        _,ctx,_,_=execute('FORCE_SPMENU(TP_PANEL,SPI_TPALARM,SCR_ALM_ALL)')
        self.assertEqual(ctx.pendant.menus['1'],{'menu':rt.PENDANT_CONSTANTS['SPI_TPALARM'],'screen':rt.PENDANT_CONSTANTS['SCR_ALM_ALL']})

    def test_available_language_selection(self):
        values,ctx,_,_=execute('SET_LANG(DP_SPANISH,s)',ctx=context(languages=['ENGLISH','SPANISH']))
        self.assertEqual((values['S'],ctx.pendant.language),(0,'SPANISH'))

    def test_unavailable_language_preserves_previous_selection(self):
        values,ctx,_,_=execute('SET_LANG(DP_JAPANESE,s)')
        self.assertEqual((values['S'],ctx.pendant.language),(33003,'ENGLISH'))

    def test_default_language_selector(self):
        values,ctx,_,_=execute('SET_LANG(DP_SPANISH,s) SET_LANG(DP_DEFAULT,s)',ctx=context(languages=['ENGLISH','SPANISH']))
        self.assertEqual((values['S'],ctx.pendant.language),(0,'ENGLISH'))

    def test_string_predefined_values_keep_string_types(self):
        values,_,_,_=execute('label=DP_ENGLISH',decl=DECL+' label:STRING[12]')
        self.assertEqual(values['LABEL'],'ENGLISH')
        with self.assertRaises(TranslationError):compile_program('n=DP_ENGLISH')

    def test_predefined_language_can_be_a_constant_value(self):
        values,ctx,_,_=execute('SET_LANG(chosen,s)',ctx=context(languages=['ENGLISH','SPANISH']),prefix='CONST chosen=DP_SPANISH')
        self.assertEqual((values['S'],ctx.pendant.language),(0,'SPANISH'))


class WindowFileTests(unittest.TestCase):
    def test_text_write_and_cursor_movement(self):
        values,ctx,_,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') WRITE f('AB') SET_CURSOR(f,2,2,s) WRITE f('X') CLOSE FILE f")
        self.assertEqual(values['S'],0);self.assertEqual(ctx.pendant.windows['W1']['lines'],['AB  ',' X  '])

    def test_exact_width_defers_wrap_until_next_character(self):
        _,ctx,_,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') WRITE f('ABCD') CLOSE FILE f")
        self.assertEqual(ctx.pendant.windows['W1']['lines'],['ABCD','    '])
        self.assertTrue(ctx.pendant.windows['W1']['cursor']['wrap'])

    def test_automatic_wrap_on_next_character(self):
        _,ctx,_,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') WRITE f('ABCDE') CLOSE FILE f")
        self.assertEqual(ctx.pendant.windows['W1']['lines'],['ABCD','E   '])

    def test_newline_and_scrolling(self):
        _,ctx,_,_=execute("DEF_WINDOW('W1',2,4,WD_SCROLLED,s) OPEN FILE f('RW','WD:W1') WRITE f('ONE',CR,'TWO',CR,'END') CLOSE FILE f")
        self.assertEqual(ctx.pendant.windows['W1']['lines'],['TWO ','END '])

    def test_non_scrolling_bottom_line_is_cleared_without_moving_top_line(self):
        _,ctx,_,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') WRITE f('ONE',CR,'TWO',CR,'END') CLOSE FILE f")
        self.assertEqual(ctx.pendant.windows['W1']['lines'],['ONE ','END '])

    def test_common_cursor_continues_across_file_handles(self):
        _,ctx,_,_=execute("DEF_WINDOW('W1',2,4,WD_COM_CURSR,s) OPEN FILE f('RW','WD:W1') OPEN FILE g('RW','WD:W1') WRITE f('AB') WRITE g('CD') CLOSE FILE f CLOSE FILE g")
        self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'ABCD')

    def test_individual_cursor_starts_at_each_handle_origin(self):
        _,ctx,_,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') OPEN FILE g('RW','WD:W1') WRITE f('AB') WRITE g('Z') CLOSE FILE f CLOSE FILE g")
        self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'ZB  ')

    def test_common_cursor_can_be_set_by_either_handle(self):
        _,ctx,_,_=execute("DEF_WINDOW('W1',2,4,WD_COM_CURSR,s) OPEN FILE f('RW','WD:W1') OPEN FILE g('RW','WD:W1') SET_CURSOR(f,2,2,s) WRITE g('X') CLOSE FILE f CLOSE FILE g")
        self.assertEqual(ctx.pendant.windows['W1']['lines'][1],' X  ')

    def test_carriage_return_and_form_feed(self):
        _,ctx,_,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') WRITE f('AB',CHR(13),'X') WRITE f(CHR(12),'Z') CLOSE FILE f")
        self.assertEqual(ctx.pendant.windows['W1']['lines'],['Z   ','    '])

    def test_backspace_repositions_without_deleting_other_characters(self):
        _,ctx,_,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') WRITE f('AB',CHR(8),'Z') CLOSE FILE f")
        self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'AZ  ')

    def test_tab_expansion_and_shared_cursor_snapshot_are_valid(self):
        _,ctx,_,_=execute("DEF_WINDOW('W1',2,16,0,s) OPEN FILE f('RW','WD:W1') WRITE f('A',CHR(9),'B') CLOSE FILE f",ctx=rt.ExecutionContext(pendant=rt.PendantDisplay(rows=4,cols=20)))
        self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'A       B       ')

    def test_invalid_cursor_preserves_existing_cursor(self):
        values,ctx,_,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') SET_CURSOR(f,3,1,s) WRITE f('A') CLOSE FILE f")
        self.assertEqual(values['S'],1);self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'A   ')

    def test_cursor_on_non_window_file_returns_status(self):
        values,_,_,_=execute('SET_CURSOR(f,1,1,s)')
        self.assertEqual(values['S'],4)

    def test_unsupported_control_is_atomic(self):
        ctx=context();p,_=compile_program(SETUP+" OPEN FILE f('RW','WD:W1') WRITE f('AB') WRITE f('X',CHR(27),'Y')",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'AB  ')
        self.assertEqual(p.snapshot()['F']['position'],2)
        ctx.pendant.close(p._state.values['F'])

    def test_window_file_rejects_input_and_keyboard_suffix(self):
        for body in ("OPEN FILE f('RO','WD:W1')","OPEN FILE f('RW','WD:W1/tpkb')","OPEN FILE f('WB','WD:W1')"):
            with self.subTest(body=body):
                ctx=context();p,_=compile_program(SETUP+' '+body,decl=DECL,context=ctx)
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(ctx.pendant.snapshot()['open_files'],[])

    def test_read_is_not_mistaken_for_keyboard_input(self):
        ctx=context();p,_=compile_program(SETUP+" OPEN FILE f('RW','WD:W1') READ f(n)",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'output only'):p.run()
        ctx.pendant.close(p._state.values['F'])

    def test_byte_seek_and_input_availability_are_explicitly_unsupported(self):
        for call in ('SET_FILE_POS(f,0,s)','BYTES_AHEAD(f,n,s)','n=BYTES_LEFT(f)'):
            with self.subTest(call=call):
                ctx=context();p,_=compile_program(SETUP+" OPEN FILE f('RW','WD:W1') "+call,decl=DECL,context=ctx)
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                ctx.pendant.close(p._state.values['F'])

    def test_logical_output_byte_position_is_available(self):
        values,_,_,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') WRITE f('ABC') n=GET_FILE_POS(f) CLOSE FILE f")
        self.assertEqual(values['N'],3)

    def test_missing_pendant_service_does_not_fall_back_to_memory_files(self):
        with self.assertRaisesRegex(rt.KarelRuntimeError,'pendant'):
            run("OPEN FILE f('RW','WD:W1')",decl='f:FILE',context=rt.ExecutionContext(files=rt.MemoryFiles()))


class PendantPersistenceAndIntegrationTests(unittest.TestCase):
    def test_closed_state_roundtrip_retains_surfaces_and_requests(self):
        _,ctx,_,_=execute(SETUP+' '+ACTIVATE+" ATT_WINDOW_S('W1','SCR',1,1,s) OPEN FILE f('RW','WD:W1') WRITE f('Hi') CLOSE FILE f FORCE_LINK(TP_PANEL,'/fr/demo.stm')")
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.pendant.to_config(),ctx.pendant.to_config())
        self.assertEqual(restored.pendant.render()[0],'Hi      ')

    def test_open_handles_must_be_closed_before_persistence(self):
        _,ctx,p,_=execute(SETUP+" OPEN FILE f('RW','WD:W1') WRITE f('Hi')")
        with self.assertRaisesRegex(ValueError,'Close window'):ctx.to_config()
        self.assertEqual(ctx.pendant.snapshot()['open_files'],['WD:W1'])
        ctx.pendant.close(p._state.values['F']);ctx.to_config()

    def test_snapshots_do_not_alias_live_surface_data(self):
        _,ctx,_,_=execute(SETUP)
        snapshot=ctx.pendant.snapshot();snapshot['windows']['W1']['lines'][0]='XXXX'
        self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'    ')

    def test_common_cursor_survives_closed_handle_state_roundtrip(self):
        _,ctx,_,_=execute("DEF_WINDOW('W1',2,4,WD_COM_CURSR,s) OPEN FILE f('RW','WD:W1') WRITE f('AB') CLOSE FILE f")
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        _,restored,_,_=execute("OPEN FILE f('RW','WD:W1') WRITE f('CD') CLOSE FILE f",ctx=restored)
        self.assertEqual(restored.pendant.windows['W1']['lines'][0],'ABCD')

    def test_linked_routine_writes_through_borrowed_file(self):
        ctx=context()
        instance=translate_project({'main':source('MAIN',SETUP+" OPEN FILE f('RW','WD:W1') put(f) CLOSE FILE f",decl=DECL,routines='ROUTINE put(out:FILE) FROM LIB'),
            'lib':source('LIB','',routines="ROUTINE put(out:FILE) BEGIN WRITE out('Hi') END put")}).instantiate(context=ctx)
        instance.run('MAIN');self.assertEqual(ctx.pendant.windows['W1']['lines'][0],'Hi  ')
        self.assertEqual(ctx.pendant.history[-2]['program'],'MAIN')

    def test_scheduled_tasks_share_common_cursor_without_sharing_file_handles(self):
        ctx=context()
        main="DEF_WINDOW('W1',1,8,WD_COM_CURSR,s) OPEN FILE f('RW','WD:W1') WRITE f('AB') RUN_TASK('WORKER',0,FALSE,FALSE,0,s) WAIT FOR EVENT[1] WRITE f('D') CLOSE FILE f"
        worker="OPEN FILE f('RW','WD:W1') WRITE f('C') CLOSE FILE f SIGNAL EVENT[1]"
        instance=translate_project({'main':source('MAIN',main,decl='f:FILE s:INTEGER'),
            'worker':source('WORKER',worker,decl='f:FILE')}).instantiate(context=ctx)
        instance.run('MAIN')
        self.assertEqual(ctx.pendant.windows['W1']['lines'],['ABCD    '])
        self.assertEqual([item['program'] for item in ctx.pendant.history if item['operation']=='WINDOW_WRITE'],['MAIN','WORKER','MAIN'])
        ctx.to_config()

    def test_sequence_exhaustion_rejects_new_requests_before_mutation(self):
        ctx=context();ctx.pendant.sequence=2147483646
        p,_=compile_program("FORCE_LINK(1,'/fr/demo.stm')",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.pendant.links,{})

    def test_cursor_status_cannot_write_active_counter(self):
        with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO SET_CURSOR(f,1,1,n) ENDFOR',decl=DECL)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_history_ring_retains_latest_accepted_requests(self):
        _,ctx,_,_=execute("FORCE_LINK(1,'a') FORCE_LINK(1,'b') FORCE_LINK(1,'c')",ctx=context(limit=2))
        self.assertEqual([item['sequence'] for item in ctx.pendant.history],[2,3])

    def test_sequence_exhaustion_does_not_prevent_file_cleanup(self):
        _,ctx,p,_=execute(SETUP+" OPEN FILE f('RW','WD:W1')")
        ctx.pendant.sequence=2147483646
        ctx.pendant.close(p._state.values['F'])
        self.assertEqual(ctx.pendant.snapshot()['open_files'],[])
        ctx.to_config()

    def test_invalid_configuration_is_rejected(self):
        for config in ({'rows':0},{'max_cells':0},{'language':''},{'language':False},{'links':[]},
                       {'menus':{'0':{'menu':1,'screen':1}}},{'active':{'TP':'NONE'}},{'languages':['ENGLISH','english']},
                       {'windows':{'W1':{}}},{'history':[{}]}):
            with self.subTest(config=config),self.assertRaises(ValueError):rt.PendantDisplay(**config)

    def test_malformed_saved_cursor_and_attachments_are_rejected(self):
        _,ctx,_,_=execute(SETUP)
        for mutate in (lambda row:row['windows']['W1']['cursor'].update(col=5),
                       lambda row:row['screens']['SCR']['attachments'].append({'window':'NOPE','row':1,'col':1}),
                       lambda row:row['windows']['W1']['lines'].append('    ')):
            data=ctx.pendant.to_config();mutate(data)
            with self.assertRaises(ValueError):rt.PendantDisplay.from_config(data)

    def test_unknown_service_fields_and_wrong_service_type_are_rejected(self):
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config({'pendant':{'unknown':1}})
        with self.assertRaises(TypeError):rt.ExecutionContext(pendant={})


class DisplayReportTests(unittest.TestCase):
    def test_report_exposes_portable_display_contract(self):
        _,_,_,result=execute("FORCE_LINK(TP_PANEL,'/fr/demo.stm')")
        policy=result.report['pendant_policy']
        self.assertEqual(set(policy['calls']),{'FORCE_LINK','FORCE_SPMENU','SET_LANG','DEF_SCREEN','DEF_WINDOW','ACT_SCREEN','ATT_WINDOW_D','ATT_WINDOW_S','DET_WINDOW','SET_CURSOR'})
        self.assertEqual(policy['constants']['DP_ENGLISH'],'ENGLISH')
        self.assertEqual(policy['constants']['WD_SCROLLED'],2)
        self.assertEqual(policy['guide'],'docs/pendant-display.md')
        self.assertIs(policy['controller_validated'],False)
