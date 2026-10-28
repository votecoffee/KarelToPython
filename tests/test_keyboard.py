"""Authored injected-key editing, pane routing, menus and lifetime regressions."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


DECL='f,g:FILE buffer,other:STRING[20] n,key,s,token,chosen,device_stat:INTEGER'
OPEN="OPEN FILE f('RW','KB:TPKB') "
CLOSE=' CLOSE FILE f'
READ="READ_KB(f,buffer,20,KC_DISPLAY,KC_ENTER_KEY,0,'',n,key,s)"
WINDOW="DEF_WINDOW('W1',2,20,WD_COM_CURSR,s) ATT_WINDOW_S('W1','SYS',1,1,s) "
MENU="FORCE_SPMENU(TP_PANEL,SPI_TPUSER,1) "
LOAD="ADD_DICT('menu','MENU',DP_DEFAULT,DP_DRAM,s) "


def context(keys=(),*,events=None,text=None,**options):
    events=[dict(key=key) for key in keys] if events is None else events
    ctx=rt.ExecutionContext(keyboard=rt.KeyboardInput(events=events,**options),pendant=rt.PendantDisplay(rows=3,cols=24))
    if text is not None:ctx.dictionaries=rt.TextDictionaries(sources={'menu':text})
    return ctx


def execute(body,*,ctx=None,keys=(),decl=DECL,**options):
    ctx=context(keys) if ctx is None else ctx
    p,result=compile_program(body,decl=decl,context=ctx,sleep=lambda _:None,**options)
    return p.run(),ctx,p,result


def read(keys,statement=READ,**options):return execute(OPEN+statement+CLOSE,keys=keys,**options)


class KeyboardReadTests(unittest.TestCase):
    def test_basic_text_and_enter(self):
        values,ctx,_,_=read(['a','b','ENTER'])
        self.assertEqual((values['BUFFER'],values['N'],values['KEY'],values['S']),('ab',2,rt.KEYBOARD_CONSTANTS['KY_ENTER'],0))
        self.assertEqual(ctx.keyboard.events,[]);ctx.to_config()

    def test_zero_capacity_waits_for_a_termination_key(self):
        values,_,_,_=read(['F1'],READ.replace('20,KC_DISPLAY,KC_ENTER_KEY', '0,0,KC_FUNC_KEY'))
        self.assertEqual((values['BUFFER'],values['N'],values['KEY'],values['S']),('',0,1101,0))

    def test_termination_class_has_priority_over_acceptance(self):
        values,_,_,_=read(['a'],READ.replace('KC_ENTER_KEY','KC_DISPLAY'))
        self.assertEqual((values['BUFFER'],values['N'],values['KEY']),('',0,ord('a')))

    def test_full_buffer_terminates_without_consuming_next_key(self):
        values,ctx,_,_=read(['a','b','c','ENTER'],READ.replace('buffer,20,','buffer,3,'))
        self.assertEqual((values['BUFFER'],values['KEY'],values['S']),('abc',rt.KEYBOARD_CONSTANTS['KY_FULL'],0))
        self.assertEqual([event['key'] for event in ctx.keyboard.events],['ENTER'])

    def test_destination_capacity_limits_requested_size(self):
        values,_,_,_=read(['a','b','c'],decl=DECL.replace('STRING[20]','STRING[2]'))
        self.assertEqual(values['BUFFER'],'ab');self.assertEqual(values['N'],2)

    def test_full_initial_data_can_complete_without_keys(self):
        values,_,_,_=read([],READ.replace("buffer,20,","buffer,2,").replace("0,'',","0,'ab',"))
        self.assertEqual((values['BUFFER'],values['KEY']),('ab',rt.KEYBOARD_CONSTANTS['KY_FULL']))

    def test_function_key_can_terminate_a_partial_edit(self):
        values,_,_,_=read(['a','F3'],READ.replace('KC_ENTER_KEY','KC_FUNC_KEY'))
        self.assertEqual((values['BUFFER'],values['KEY']),('a',1103))

    def test_unaccepted_keys_are_consumed_without_insertion(self):
        values,_,_,_=read(['F1','a','ENTER'])
        self.assertEqual(values['BUFFER'],'a')

    def test_immediate_empty_poll_returns_timeout_with_initial_text(self):
        values,_,_,_=read([],READ.replace("0,'',","0,'seed',"))
        self.assertEqual((values['BUFFER'],values['N'],values['KEY'],values['S']),('seed',4,rt.KEYBOARD_CONSTANTS['KY_TIMEOUT'],4))

    def test_future_event_arrives_before_positive_timeout(self):
        ctx=context(events=[dict(key='ENTER',at_ms=25)])
        values,_,_,_=execute(OPEN+READ.replace("0,'',","40,'ok',")+CLOSE,ctx=ctx)
        self.assertEqual((values['BUFFER'],values['S'],ctx.keyboard.elapsed_ms),('ok',0,25))

    def test_timeout_preserves_future_event_for_later_read(self):
        ctx=context(events=[dict(key='ENTER',at_ms=25)])
        values,_,_,_=execute(OPEN+READ.replace("0,'',","10,'a',")+CLOSE,ctx=ctx)
        self.assertEqual(values['S'],4);self.assertEqual(ctx.keyboard.elapsed_ms,10);self.assertEqual(len(ctx.keyboard.events),1)
        values,_,_,_=execute(OPEN+READ.replace("0,'',","20,'b',")+CLOSE,ctx=ctx)
        self.assertEqual((values['BUFFER'],values['S'],ctx.keyboard.elapsed_ms),('b',0,25))

    def test_unbounded_standalone_wait_requires_supplied_input(self):
        ctx=context();p,_=compile_program(OPEN+READ.replace("0,'',","-1,'',"),decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit queued input'):p.run()
        self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.keyboard.close_all();ctx.to_config()

    def test_invalid_arguments_preserve_output_and_queue(self):
        cases=(READ.replace('buffer,20,','buffer,-1,'),READ.replace('KC_DISPLAY','256'),READ.replace("0,'',","-2,'',"),READ.replace("0,'',","0,'too long',").replace('buffer,20,','buffer,1,'))
        for statement in cases:
            with self.subTest(statement=statement):
                values,ctx,_,_=execute(OPEN+"buffer='old' n=99 key=99 "+statement+CLOSE,keys=['ENTER'])
                self.assertEqual((values['BUFFER'],values['N'],values['KEY'],values['S']),('old',99,99,1));self.assertEqual(len(ctx.keyboard.events),1)

    def test_io_status_and_clear(self):
        values,_,_,_=execute(OPEN+READ+" n=IO_STATUS(f) CLR_IO_STAT(f) key=IO_STATUS(f)"+CLOSE)
        self.assertEqual((values['N'],values['KEY']),(4,0))


class KeyboardEditingTests(unittest.TestCase):
    EDIT=READ.replace('KC_DISPLAY,','KC_DISPLAY+KC_DELETE+KC_LR_ARW+KC_UD_ARW+KC_KEYPAD,')

    def test_left_delete_and_insert(self):
        values,_,_,_=read(['a','b','c','LEFT','DELETE','X','ENTER'],self.EDIT)
        self.assertEqual(values['BUFFER'],'aXc')

    def test_home_and_end_move_insertion_point(self):
        values,_,_,_=read(['a','b','HOME','X','END','Y','ENTER'],self.EDIT)
        self.assertEqual(values['BUFFER'],'XabY')

    def test_delete_at_start_and_arrows_at_edges_are_bounded(self):
        values,_,_,_=read(['DELETE','LEFT','a','RIGHT','RIGHT','ENTER'],self.EDIT)
        self.assertEqual(values['BUFFER'],'a')

    def test_edit_keys_need_their_acceptance_class(self):
        values,_,_,_=read(['a','b','DELETE','ENTER'])
        self.assertEqual(values['BUFFER'],'ab')

    def test_history_up_reads_previous_value_on_same_file(self):
        body=OPEN+self.EDIT+' '+self.EDIT+CLOSE
        values,_,_,_=execute(body,keys=['o','n','e','ENTER','UP','ENTER'])
        self.assertEqual(values['BUFFER'],'one')

    def test_history_down_returns_current_initial_text(self):
        body=OPEN+self.EDIT+' '+self.EDIT.replace("0,'',","0,'seed',")+CLOSE
        values,_,_,_=execute(body,keys=['o','n','e','ENTER','UP','DOWN','ENTER'])
        self.assertEqual(values['BUFFER'],'seed')

    def test_history_does_not_leak_into_fresh_file_handles(self):
        body=OPEN+self.EDIT+" CLOSE FILE f OPEN FILE f('RW','KB:TPKB') "+self.EDIT+CLOSE
        values,_,_,_=execute(body,keys=['a','ENTER','UP','ENTER'])
        self.assertEqual(values['BUFFER'],'')


class KeyboardEndpointTests(unittest.TestCase):
    def test_combined_window_echoes_edit_without_moving_file_cursor(self):
        body=WINDOW+"OPEN FILE f('RW','WD:W1/TPKB') SET_CURSOR(f,2,3,s) "+READ+CLOSE
        values,ctx,_,_=execute(body,keys=['a','b','ENTER'])
        self.assertEqual(values['BUFFER'],'ab');self.assertEqual(ctx.pendant.windows['W1']['lines'][1],'  ab                ')
        self.assertEqual(ctx.pendant.windows['W1']['cursor'],dict(row=2,col=3,wrap=False))
        ctx.to_config()

    def test_noecho_attribute_preserves_window_text(self):
        body=WINDOW+"SET_FILE_ATR(f,ATR_NOECHO) SET_FILE_ATR(f,ATR_PASSALL) OPEN FILE f('RW','WD:W1/TPKB') WRITE f('old') "+READ+CLOSE
        values,ctx,_,_=execute(body,keys=['x','ENTER'])
        self.assertEqual(values['BUFFER'],'x');self.assertTrue(ctx.pendant.windows['W1']['lines'][0].startswith('old'))

    def test_combined_window_write_and_dictionary_write_work(self):
        ctx=context(text='$1 "Hello"')
        values,ctx,_,_=execute(LOAD+WINDOW+"OPEN FILE f('RW','WD:W1/TPKB') WRITE_DICT(f,'MENU',1,s) WRITE f('!') CLOSE FILE f",ctx=ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.pendant.windows['W1']['lines'][0][:6],'Hello!')
        self.assertEqual(values['F']['position'],6)

    def test_standalone_keyboard_has_no_output_window(self):
        ctx=context();p,_=compile_program(OPEN+"WRITE f('bad')",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        ctx.keyboard.close_all()

    def test_set_cursor_on_standalone_keyboard_returns_nonwindow_status(self):
        values,_,_,_=execute(OPEN+"SET_CURSOR(f,1,1,s)"+CLOSE)
        self.assertEqual(values['S'],4)

    def test_generic_keyboard_read_requires_explicit_queued_input(self):
        ctx=context();p,_=compile_program(OPEN+'READ f(n)',decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit queued input'):p.run()
        ctx.keyboard.close_all()

    def test_byte_queries_and_seeking_are_explicitly_rejected(self):
        for statement in ('n=GET_FILE_POS(f)','n=BYTES_LEFT(f)','BYTES_AHEAD(f,n,s)','SET_FILE_POS(f,0,s)'):
            with self.subTest(statement=statement):
                ctx=context();p,_=compile_program(OPEN+statement,decl=DECL,context=ctx)
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                ctx.keyboard.close_all()

    def test_pane_is_captured_from_root_device_stat_at_open(self):
        events=[dict(pane=1,key='F1'),dict(pane=2,key='F2')]
        ctx=context(events=events);body="device_stat=2 "+OPEN+"device_stat=1 "+READ.replace('KC_ENTER_KEY','KC_FUNC_KEY')+CLOSE
        values,_,_,_=execute(body,ctx=ctx)
        self.assertEqual(values['KEY'],1102);self.assertEqual(ctx.keyboard.events[0]['key'],'F1')

    def test_bad_pane_endpoint_and_file_mode_fail_before_open(self):
        for statement in ("device_stat=0 "+OPEN,"OPEN FILE f('WO','KB:TPKB')","OPEN FILE f('RW','KB:OTHER')","SET_FILE_ATR(f,ATR_UF) "+OPEN,"OPEN FILE f('RW','WD:MISSING/TPKB')"):
            with self.subTest(statement=statement):
                ctx=context();p,_=compile_program(statement,decl=DECL,context=ctx)
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertEqual(ctx.keyboard.snapshot()['open_files'],[])

    def test_missing_service_never_falls_back_to_memory_files(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles())
        p,_=compile_program(OPEN,decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'keyboard'):p.run()


class KeyboardSuspensionTests(unittest.TestCase):
    def test_null_push_does_not_suspend_future_reads(self):
        body="PUSH_KEY_RD('TPKB',255,token,s) "+OPEN+READ+CLOSE+" POP_KEY_RD('TPKB',token,s)"
        values,ctx,_,_=execute(body,keys=['ENTER'])
        self.assertEqual(values['S'],0);self.assertEqual(ctx.keyboard.history[0]['data']['suspended'],0);ctx.to_config()

    def test_nested_tokens_can_be_popped_by_id(self):
        values,ctx,_,_=execute("PUSH_KEY_RD('TPKB',1,token,s) PUSH_KEY_RD('TPKB',1,n,s) POP_KEY_RD('TPKB',token,s) POP_KEY_RD('TPKB',n,s)")
        self.assertEqual(values['S'],0);self.assertEqual(ctx.keyboard.snapshot()['suspensions'],0)

    def test_unknown_pop_and_invalid_mask_preserve_frames(self):
        values,ctx,_,_=execute("PUSH_KEY_RD('TPKB',256,token,s) POP_KEY_RD('TPKB',999,s)")
        self.assertEqual(values['S'],3);self.assertEqual(ctx.keyboard.snapshot()['suspensions'],0)

    def test_pop_cleanup_works_at_exhausted_history_sequence(self):
        ctx=context();p,_=compile_program("PUSH_KEY_RD('TPKB',1,token,s) PAUSE POP_KEY_RD('TPKB',token,s)",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        ctx.keyboard.sequence=2147483646;p.resume()
        self.assertEqual(p.snapshot()['S'],0);ctx.to_config()

    def test_scheduler_suspends_old_reader_but_allows_new_one(self):
        events=[dict(key='F1',at_ms=100),dict(key='F2',at_ms=200)]
        ctx=context(events=events)
        reader="OPEN FILE f('RW','KB:TPKB') READ_KB(f,text,0,0,KC_FUNC_KEY,500,'',n,key,s) CLOSE FILE f SIGNAL EVENT[1]"
        main="RUN_TASK('WORKER',0,FALSE,FALSE,0,s) DELAY(10) PUSH_KEY_RD('TPKB',KC_FUNC_KEY,token,s) "+OPEN+READ.replace('20,KC_DISPLAY,KC_ENTER_KEY,0','0,0,KC_FUNC_KEY,500')+CLOSE+" POP_KEY_RD('TPKB',token,s) WAIT FOR EVENT[1]"
        instance=translate_project({'main':source('MAIN',main,decl=DECL),'worker':source('WORKER',reader,decl='f:FILE text:STRING[1] n,key,s:INTEGER')}).instantiate(context=ctx)
        result=instance.run('MAIN')
        self.assertEqual(result['MAIN']['values']['KEY'],1101);self.assertEqual(result['WORKER']['values']['KEY'],1102)
        self.assertEqual(next(row for row in ctx.keyboard.history if row['operation']=='PUSH_KEY_RD')['data']['suspended'],1)
        restored=rt.ExecutionContext.from_config(ctx.to_config());self.assertEqual(restored.keyboard.to_config(),ctx.keyboard.to_config())


class KeyboardControlTests(unittest.TestCase):
    def test_comment_entry_uses_supplied_keys_and_existing_window(self):
        body=WINDOW+MENU+"buffer='hi' DISCTRL_ALPH('W1',1,1,buffer,'COMM',0,key,s)"
        values,ctx,_,_=execute(body,keys=['!','ENTER'])
        self.assertEqual((values['BUFFER'],values['KEY'],values['S']),('hi!',13,0));self.assertTrue(ctx.pendant.windows['W1']['lines'][0].startswith('hi!'))

    def test_program_entry_normalizes_identifier_case(self):
        body=WINDOW+MENU+"buffer='' DISCTRL_ALPH('W1',1,1,buffer,'PROG',0,key,s)"
        values,_,_,_=execute(body,keys=['m','a','i','n','ENTER'])
        self.assertEqual((values['BUFFER'],values['S']),('MAIN',0))

    def test_invalid_program_name_preserves_original_variable(self):
        body=WINDOW+MENU+"buffer='' DISCTRL_ALPH('W1',1,1,buffer,'PROG',0,key,s)"
        values,_,_,_=execute(body,keys=['1','a','ENTER'])
        self.assertEqual((values['BUFFER'],values['S']),('',1))

    def test_custom_alphabet_uses_dictionary_characters(self):
        ctx=context(keys=['A','Z','B','ENTER'],text='$1 "ABC"')
        body=LOAD+WINDOW+MENU+"buffer='' DISCTRL_ALPH('W1',1,1,buffer,'MENU',1,key,s)"
        values,_,_,_=execute(body,ctx=ctx)
        self.assertEqual((values['BUFFER'],values['S']),('AB',0))

    def test_alphanumeric_entry_requires_user_menu(self):
        ctx=context(keys=['ENTER']);values,_,_,_=execute(WINDOW+"buffer='old' DISCTRL_ALPH('W1',1,1,buffer,'COMM',0,key,s)",ctx=ctx)
        self.assertEqual((values['BUFFER'],values['S']),('old',9093));self.assertEqual(len(ctx.keyboard.events),1)

    def test_custom_alphabet_rejects_trailing_newline(self):
        ctx=context(keys=['ENTER'],text='$1 "ABC" &new_line')
        values,_,_,_=execute(LOAD+WINDOW+MENU+"buffer='' DISCTRL_ALPH('W1',1,1,buffer,'MENU',1,key,s)",ctx=ctx)
        self.assertEqual(values['S'],1);self.assertEqual(len(ctx.keyboard.events),1)

    def test_subwindow_menu_navigation_and_selection(self):
        ctx=context(keys=['DOWN','DOWN','UP','ENTER'],text='$1 "Red"\n$2 "Blue"\n$3 "Green"\n$4 ""')
        values,_,_,_=execute(LOAD+"chosen=1 DISCTRL_SBMN('MENU',1,chosen,key,s)",ctx=ctx)
        self.assertEqual((values['CHOSEN'],values['KEY'],values['S']),(2,13,0));self.assertEqual(ctx.keyboard.history[-1]['data']['items'],['Red','Blue','Green'])

    def test_pullup_function_key_and_previous_termination(self):
        for key,code in (('F2',1102),('PREV',1005),('NEW_MENU',1007)):
            with self.subTest(key=key):
                ctx=context(keys=['DOWN',key],text='$1 "One"\n$2 "Two"\n$3 ""')
                values,_,_,_=execute(LOAD+"chosen=1 DISCTRL_PLMN('MENU',1,3,chosen,key,s)",ctx=ctx)
                self.assertEqual((values['CHOSEN'],values['KEY'],values['S']),(2,code,0))

    def test_subwindow_page_movement_is_bounded(self):
        text='\n'.join(f'${i} "Item{i}"' for i in range(1,11))+'\n$11 ""'
        ctx=context(keys=['RIGHT','ENTER'],text=text)
        values,_,_,_=execute(LOAD+"chosen=1 DISCTRL_SBMN('MENU',1,chosen,key,s)",ctx=ctx)
        self.assertEqual(values['CHOSEN'],8)

    def test_bad_menu_layout_does_not_consume_keys_or_change_selection(self):
        for text in ('$1 "too long for pullup"\n$2 ""','$1 "one" &new_line\n$2 ""','$1 "one"'):
            with self.subTest(text=text):
                ctx=context(keys=['ENTER'],text=text)
                values,_,_,_=execute(LOAD+"chosen=1 DISCTRL_PLMN('MENU',1,3,chosen,key,s)",ctx=ctx)
                self.assertEqual((values['CHOSEN'],values['S']),(1,1));self.assertEqual(len(ctx.keyboard.events),1)

    def test_bad_default_and_function_key_number_are_status_failures(self):
        for chosen,function in ((0,1),(1,6)):
            with self.subTest(chosen=chosen,function=function):
                ctx=context(keys=['ENTER'],text='$1 "One"\n$2 ""')
                values,_,_,_=execute(LOAD+f"chosen={chosen} DISCTRL_PLMN('MENU',1,{function},chosen,key,s)",ctx=ctx)
                self.assertEqual(values['S'],1);self.assertEqual(len(ctx.keyboard.events),1)


class KeyboardPersistenceAndGuardTests(unittest.TestCase):
    def test_consumed_input_is_not_replayed_after_save_load(self):
        values,ctx,_,_=read(['a','ENTER','F1'])
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual([event['key'] for event in restored.keyboard.events],['F1'])
        self.assertEqual(restored.keyboard.to_config(),ctx.keyboard.to_config())

    def test_open_files_and_unpopped_frames_block_save(self):
        for body in (OPEN,"PUSH_KEY_RD('TPKB',1,token,s)"):
            with self.subTest(body=body):
                _,ctx,_,_=execute(body)
                with self.assertRaises(ValueError):ctx.to_config()
                ctx.keyboard.close_all();ctx.to_config()

    def test_events_snapshots_are_detached(self):
        ctx=context(keys=['a']);snapshot=ctx.keyboard.snapshot();snapshot['events'][0]['key']='b'
        self.assertEqual(ctx.keyboard.events[0]['key'],'a')

    def test_feed_text_is_atomic_on_invalid_or_excess_input(self):
        bank=rt.KeyboardInput();bank.feed_text('ok');self.assertEqual([row['key'] for row in bank.events],['o','k'])
        for text in ('bad\n','x'*4096):
            with self.subTest(length=len(text)),self.assertRaises(ValueError):bank.feed_text(text)
        self.assertEqual([row['key'] for row in bank.events],['o','k'])

    def test_native_numeric_and_named_key_inputs_are_normalized(self):
        bank=rt.KeyboardInput(events=[{'key':65},{'key':13},{'key':'f2'}])
        self.assertEqual([row['key'] for row in bank.events],['A','ENTER','F2'])

    def test_invalid_configuration_rejected(self):
        cases=({'events':{}},{'events':[{'key':'UNKNOWN'}]},{'events':[{'key':'a','pane':0}]},{'event_sequence':True},
               {'events':[{'key':'a','sequence':1},{'key':'b','sequence':1}]},{'elapsed_ms':-1},{'active':[]},{'history':[{}]})
        for config in cases:
            with self.subTest(config=config),self.assertRaises(ValueError):rt.KeyboardInput.from_config(config)
        with self.assertRaises(TypeError):rt.ExecutionContext(keyboard={})

    def test_request_sequence_exhaustion_has_no_input_side_effects(self):
        ctx=context(keys=['ENTER'],request_sequence=2147483646);p,_=compile_program(OPEN+READ,decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(len(ctx.keyboard.events),1);ctx.keyboard.close_all()

    def test_output_overlap_and_active_counter_guards_remain(self):
        ctx=context(keys=['ENTER']);p,_=compile_program(OPEN+READ.replace('n,key,s','n,n,s'),decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(len(ctx.keyboard.events),1);ctx.keyboard.close_all()
        with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO '+READ+' ENDFOR',decl=DECL)
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_wrong_buffer_and_mask_types_are_rejected(self):
        for statement in (READ.replace('f,buffer,','f,n,'),READ.replace('KC_DISPLAY','TRUE')):
            with self.subTest(statement=statement),self.assertRaises(TranslationError) as caught:compile_program(statement,decl=DECL)
            self.assertEqual(caught.exception.code,'E_TYPE')

    def test_linked_routine_borrows_keyboard_file_and_outputs(self):
        ctx=context(keys=['x','ENTER'])
        main=source('MAIN',OPEN+'get_text(f,buffer)'+CLOSE,decl=DECL,routines='ROUTINE get_text(stream:FILE; text:STRING) FROM LIB')
        lib=source('LIB','',decl='n,key,s:INTEGER',routines="ROUTINE get_text(stream:FILE; text:STRING) BEGIN READ_KB(stream,text,20,KC_DISPLAY,KC_ENTER_KEY,0,'',n,key,s) END get_text")
        instance=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);values=instance.run('MAIN')
        self.assertEqual(values['MAIN']['values']['BUFFER'],'x');self.assertEqual(ctx.keyboard.history[-1]['program'],'MAIN');ctx.to_config()


class KeyboardFailureAndLifecycleTests(unittest.TestCase):
    def test_invalid_program_submission_records_failed_status(self):
        values,ctx,_,_=execute(WINDOW+MENU+"buffer='' DISCTRL_ALPH('W1',1,1,buffer,'PROG',0,key,s)",keys=['1','a','ENTER'])
        self.assertEqual(values['S'],1);self.assertEqual(ctx.keyboard.history[-1]['outcome'],'failed');self.assertEqual(ctx.keyboard.history[-1]['data']['status'],1)

    def test_previous_key_does_not_validate_unsubmitted_program_name(self):
        values,_,_,_=execute(WINDOW+MENU+"buffer='' DISCTRL_ALPH('W1',1,1,buffer,'PROG',0,key,s)",keys=['PREV'])
        self.assertEqual((values['BUFFER'],values['KEY'],values['S']),('',1005,0))

    def test_normalized_program_text_matches_echo_and_history(self):
        values,ctx,_,_=execute(WINDOW+MENU+"buffer='' DISCTRL_ALPH('W1',1,1,buffer,'PROG',0,key,s)",keys=['a','b','ENTER'])
        self.assertEqual(values['BUFFER'],'AB');self.assertTrue(ctx.pendant.windows['W1']['lines'][0].startswith('AB'))
        self.assertEqual(ctx.keyboard.history[-1]['data']['text'],'AB')

    def test_per_read_event_budget_returns_failed_terminal_record(self):
        values,ctx,_,_=read(['F1']*4096)
        self.assertEqual(values['S'],5);self.assertEqual(ctx.keyboard.events,[])
        self.assertEqual(ctx.keyboard.history[-1]['outcome'],'failed');ctx.to_config()

    def test_failed_sleeper_releases_pending_request(self):
        ctx=context()
        def broken_sleep(seconds):raise RuntimeError('authored sleeper failure')
        p,_=compile_program(OPEN+READ.replace("0,'',","10,'',"),decl=DECL,context=ctx,sleep=broken_sleep)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(ctx.keyboard.snapshot()['active'],[]);self.assertEqual(ctx.keyboard.history[-1]['outcome'],'failed')
        ctx.keyboard.close_all();ctx.to_config()

    def test_foreign_root_cannot_pop_another_roots_frame(self):
        _,ctx,_,_=execute("PUSH_KEY_RD('TPKB',1,token,s)")
        values,_,_,_=execute("POP_KEY_RD('TPKB',1,s)",ctx=ctx)
        self.assertEqual(values['S'],3);self.assertEqual(ctx.keyboard.snapshot()['suspensions'],1)
        ctx.keyboard.close_all();ctx.to_config()

    def test_paused_read_can_resume_or_stop_without_leaking_request(self):
        for stop in (False,True):
            with self.subTest(stop=stop):
                ctx=context(events=[dict(key='ENTER',at_ms=25)])
                def pause_once(seconds):p._state._pause_requested=True
                p,_=compile_program(OPEN+READ.replace("0,'',","100,'',")+CLOSE,decl=DECL,context=ctx,sleep=pause_once)
                with self.assertRaises(rt.KarelPause):p.run()
                self.assertEqual(len(ctx.keyboard.snapshot()['active']),1)
                with self.assertRaises(ValueError):ctx.keyboard.close_all()
                if stop:
                    p.stop();ctx.keyboard.close_all()
                    self.assertEqual(ctx.keyboard.history[-1]['outcome'],'cancelled')
                else:
                    p._state._sleep=lambda seconds:None;p.resume()
                    self.assertEqual(p.snapshot()['S'],0)
                self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.to_config()


class KeyboardBudgetAndReportTests(unittest.TestCase):
    def test_waits_obey_step_budget_and_release_request(self):
        ctx=context(events=[dict(key='ENTER',at_ms=1000)])
        p,_=compile_program(OPEN+READ.replace("0,'',","1000,'',"),decl=DECL,context=ctx,sleep=lambda seconds:None)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=5)
        self.assertEqual(ctx.keyboard.snapshot()['active'],[])
        self.assertEqual(ctx.keyboard.history[-1]['outcome'],'failed')
        ctx.keyboard.close_all();ctx.to_config()

    def test_report_exposes_injected_input_contract(self):
        _,_,_,result=read(['ENTER'])
        policy=result.report['keyboard_policy']
        self.assertEqual(len(policy['calls']),6)
        self.assertEqual(policy['constants']['KY_ENTER'],13)
        self.assertEqual(policy['guide'],'docs/keyboard-input.md')
        self.assertIs(policy['controller_validated'],False)


class KeyboardReadonlyOutputTests(unittest.TestCase):
    def test_dictionary_write_cannot_bypass_readonly_combined_file(self):
        ctx=context(text='$1 "Hello"')
        values,_,_,_=execute(LOAD+WINDOW+"OPEN FILE f('RO','WD:W1/TPKB') WRITE_DICT(f,'MENU',1,s) CLOSE FILE f",ctx=ctx)
        self.assertEqual(values['S'],4);self.assertEqual(values['F']['position'],0)
        self.assertEqual(ctx.pendant.windows['W1']['lines'],[' '*20]*2)
