"""Authored static-variable monitors, logical polling and field cancellation."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source


DECL='b:BOOLEAN e,n,s:INTEGER r:REAL label:STRING[20] choices:ARRAY[3] OF STRING[12] f:FILE'
SETUP="DEF_WINDOW('W1',3,20,WD_COM_CURSR,s) ATT_WINDOW_S('W1','SYS',1,1,s) "
CHOICES="choices[1]='OFF' choices[2]='ON' choices[3]='OTHER' "


def context(**options):return rt.ExecutionContext(pendant=rt.PendantDisplay(rows=4,cols=24),dynamic_display=rt.DynamicDisplays(**options))


def call(kind='I',*,variable=None,row=1,col=1,width=6,interval=1,format=None,window='W1'):
    variable=variable or {'B':'b','E':'e','I':'n','R':'r','S':'label','P':'1,1'}[kind]
    tail='choices' if kind in 'BEP' else "0,'"+(format or {'I':'%d','R':'%.2f','S':'%s'}[kind])+"'"
    return f"INI_DYN_DIS{kind}({variable},'{window}',{width},0,0,{row},{col},{interval},{tail},s) "


def execute(body,*,ctx=None,decl=DECL,**options):
    ctx=context() if ctx is None else ctx
    program,result=compile_program(body,decl=decl,context=ctx,**options)
    return program.run(),ctx,program,result


def line(ctx,row=1):return ctx.pendant.windows['W1']['lines'][row-1]


class DynamicValueTests(unittest.TestCase):
    def test_integer_initial_draw_and_live_update(self):
        values,ctx,p,_=execute(SETUP+'n=7 '+call())
        self.assertEqual(values['S'],0);self.assertEqual(line(ctx)[:6],'7     ')
        p._state.set('N',42);ctx.dynamic_display.advance(1)
        self.assertEqual(line(ctx)[:6],'42    ')

    def test_real_and_string_families(self):
        for kind,assignment,text in (('R','r=1.25','1.25  '),('S',"label='ready'",'ready ')):
            with self.subTest(kind=kind):
                values,ctx,_,_=execute(SETUP+assignment+' '+call(kind))
                self.assertEqual((values['S'],line(ctx)[:6]),(0,text))

    def test_boolean_choices_follow_later_values(self):
        _,ctx,p,_=execute(SETUP+CHOICES+'b=FALSE '+call('B'))
        self.assertEqual(line(ctx)[:6],'OFF   ')
        p._state.set('B',True);ctx.dynamic_display.advance(1)
        self.assertEqual(line(ctx)[:6],'ON    ')

    def test_enum_uses_zero_based_value_for_labels(self):
        _,ctx,p,_=execute(SETUP+CHOICES+'e=2 '+call('E'))
        self.assertEqual(line(ctx)[:6],'OTHER ')
        p._state.set('E',0);ctx.dynamic_display.advance(1)
        self.assertEqual(line(ctx)[:6],'OFF   ')

    def test_uninitialized_scalar_draws_stars_and_can_later_initialize(self):
        for kind,field,value in (('I','N',42),('R','R',2.5),('S','LABEL','ok'),('B','B',True),('E','E',0)):
            with self.subTest(kind=kind):
                values,ctx,p,_=execute(SETUP+CHOICES+call(kind))
                self.assertEqual((values['S'],line(ctx)[:6]),(0,'******'))
                p._state.set(field,value);ctx.dynamic_display.advance(1)
                self.assertNotEqual(line(ctx)[:6],'******')

    def test_uninitialized_selected_label_is_a_placeholder(self):
        values,ctx,_,_=execute(SETUP+'b=TRUE '+call('B'))
        self.assertEqual(values['S'],0);self.assertEqual(line(ctx)[:6],'******')

    def test_out_of_range_enum_uses_question_marks(self):
        for number in (-1,3):
            with self.subTest(number=number):
                values,ctx,_,_=execute(SETUP+CHOICES+f'e={number} '+call('E'))
                self.assertEqual((values['S'],line(ctx)[:6]),(0,'??????'))

    def test_nonprintable_string_is_not_interpreted_as_terminal_control(self):
        _,ctx,_,_=execute(SETUP+"label=CHR(12)+'bad' "+call('S'))
        self.assertEqual(line(ctx)[:6],'??????');self.assertEqual(ctx.dynamic_display.snapshot()['bindings'][0]['last_status'],4)

    def test_fixed_width_truncates_and_pads(self):
        _,ctx,p,_=execute(SETUP+"label='longer than field' "+call('S',width=4))
        self.assertEqual(line(ctx)[:4],'long')
        p._state.set('LABEL','x');ctx.dynamic_display.advance(1)
        self.assertEqual(line(ctx)[:4],'x   ')

    def test_zero_width_preserves_old_trailing_cells_on_shrink(self):
        _,ctx,p,_=execute(SETUP+"label='ABCDE' "+call('S',width=0))
        p._state.set('LABEL','x');ctx.dynamic_display.advance(1)
        self.assertEqual(line(ctx)[:5],'xBCDE')

    def test_zero_width_clips_to_available_columns(self):
        _,ctx,_,_=execute(SETUP+"label='abcdefgh' "+call('S',width=0,col=18))
        self.assertEqual(line(ctx)[17:],'abc')

    def test_format_flags_unsigned_and_precision(self):
        cases=(('%+05d',12,'+0012 '),('%X',-1,'FFFFFF'),('%.4d',12,'0012  '))
        for format,value,expected in cases:
            with self.subTest(format=format):
                _,ctx,_,_=execute(SETUP+f'n={value} '+call(format=format))
                self.assertEqual(line(ctx)[:6],expected)

    def test_literal_percent_format(self):
        _,ctx,_,_=execute(SETUP+'n=1 '+call(format='%%'))
        self.assertEqual(line(ctx)[:6],'%     ')

    def test_buffer_size_is_metadata_only(self):
        statement=call().replace(",0,'%d'",",-1,'%d'")
        values,ctx,_,_=execute(SETUP+'n=7 '+statement)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.dynamic_display.snapshot()['bindings'][0]['buffer_size'],-1)

    def test_recognized_character_attributes_do_not_change_grid_size(self):
        statement=call().replace("'W1',6,0,0","'W1',6,15,2")
        values,ctx,_,_=execute(SETUP+'n=7 '+statement)
        self.assertEqual(values['S'],0);self.assertEqual(len(line(ctx)),20)


class DynamicClockAndCancellationTests(unittest.TestCase):
    def test_minimum_interval_uses_explicit_logical_time(self):
        _,ctx,p,_=execute(SETUP+'n=1 '+call(interval=10))
        p._state.set('N',7);self.assertEqual(ctx.dynamic_display.advance(9),0)
        self.assertEqual(line(ctx)[:6],'1     ')
        self.assertEqual(ctx.dynamic_display.advance(1),1);self.assertEqual(line(ctx)[:6],'7     ')

    def test_force_samples_without_advancing_clock(self):
        _,ctx,p,_=execute(SETUP+'n=1 '+call(interval=10))
        p._state.set('N',7);ctx.dynamic_display.advance(0,force=True)
        self.assertEqual((line(ctx)[:6],ctx.dynamic_display.elapsed_ms),('7     ',0))

    def test_source_checkpoints_drive_display_updates(self):
        _,ctx,_,_=execute(SETUP+'n=1 '+call()+'n=7 e=2')
        self.assertEqual(line(ctx)[:6],'7     ');self.assertEqual(ctx.dynamic_display.elapsed_ms,2)

    def test_clock_does_not_advance_without_bindings(self):
        _,ctx,_,_=execute(SETUP+'n=1 n=2')
        self.assertEqual(ctx.dynamic_display.elapsed_ms,0)

    def test_cancel_all_family_variants_clear_fixed_fields(self):
        for kind,assignment,variable in (('B','b=TRUE','b'),('E','e=1','e'),('I','n=1','n'),('R','r=1.5','r'),('S',"label='ok'",'label')):
            with self.subTest(kind=kind):
                values,ctx,_,_=execute(SETUP+CHOICES+assignment+' '+call(kind)+f"CNC_DYN_DIS{kind}({variable},'W1',s)")
                self.assertEqual(values['S'],0);self.assertEqual(ctx.dynamic_display.active_count,0);self.assertEqual(line(ctx),' '*20)
                ctx.to_config()

    def test_cancel_zero_width_leaves_last_text(self):
        values,ctx,_,_=execute(SETUP+'n=42 '+call(width=0)+"CNC_DYN_DISI(n,'W1',s)")
        self.assertEqual(values['S'],0);self.assertEqual(line(ctx)[:2],'42')

    def test_cancel_matches_storage_identity_not_equal_values(self):
        values,ctx,_,_=execute(SETUP+'n=7 e=7 '+call()+"CNC_DYN_DISI(e,'W1',s)")
        self.assertEqual(values['S'],3);self.assertEqual(ctx.dynamic_display.active_count,1)

    def test_multiple_locations_cancel_together(self):
        values,ctx,_,_=execute(SETUP+'n=7 '+call(row=1)+call(row=2)+"CNC_DYN_DISI(n,'W1',s)")
        self.assertEqual(values['S'],0);self.assertEqual(ctx.dynamic_display.active_count,0)
        self.assertEqual(ctx.pendant.windows['W1']['lines'],[' '*20]*3)

    def test_cancel_does_not_remove_other_windows_or_families(self):
        values,ctx,_,_=execute(SETUP+"DEF_WINDOW('W2',1,20,0,s) "+CHOICES+'n=1 '+call()+call(window='W2')+call('E',variable='n',row=2)+"CNC_DYN_DISI(n,'W1',s)")
        self.assertEqual(values['S'],0);self.assertEqual(ctx.dynamic_display.active_count,2)

    def test_overlapping_fields_repaint_in_registration_order(self):
        _,ctx,_,_=execute(SETUP+"n=12345 label='XY' "+call(width=6,interval=100)+call('S',width=2,col=3,interval=100))
        self.assertEqual(line(ctx)[:6],'12XY5 ')

    def test_cancel_restores_surviving_overlapping_last_sample(self):
        values,ctx,p,_=execute(SETUP+"n=12345 label='XY' "+call(width=6,interval=100)+call('S',width=2,col=3,interval=100)+"CNC_DYN_DISS(label,'W1',s)")
        self.assertEqual(values['S'],0);self.assertEqual(line(ctx)[:6],'12345 ')
        self.assertEqual(ctx.dynamic_display.active_count,1)

    def test_background_writes_preserve_source_file_cursor_and_position(self):
        values,ctx,_,_=execute(SETUP+"OPEN FILE f('RW','WD:W1') WRITE f('AB') n=7 "+call(col=5)+"WRITE f('C') CLOSE FILE f")
        self.assertEqual(values['F']['position'],3);self.assertEqual(line(ctx)[:6],'ABC 7 ')
        self.assertEqual(ctx.pendant.windows['W1']['cursor'],dict(row=1,col=4,wrap=False))

    def test_cleanup_remains_available_at_display_sequence_exhaustion(self):
        _,ctx,_,_=execute(SETUP+'n=7 '+call());ctx.pendant.sequence=2147483646
        self.assertEqual(ctx.dynamic_display.close_all(),0);self.assertEqual(ctx.dynamic_display.active_count,0);self.assertEqual(line(ctx),' '*20)
        ctx.to_config()

    def test_failed_poll_preflights_multiple_windows(self):
        _,ctx,p,_=execute(SETUP+"DEF_WINDOW('W2',1,20,0,s) n=7 "+call()+call(window='W2'))
        p._state.set('N',42);before=ctx.pendant.snapshot();ctx.pendant.sequence=2147483645
        with self.assertRaises(rt.KarelRuntimeError):ctx.dynamic_display.advance(1,force=True)
        self.assertEqual(ctx.pendant.windows,before['windows']);ctx.dynamic_display.close_all()

    def test_background_failure_does_not_block_source_cancellation(self):
        ctx=context();p,_=compile_program(SETUP+'n=7 '+call()+"PAUSE CNC_DYN_DISI(n,'W1',s)",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        ctx.pendant.sequence=2147483646;p.resume()
        self.assertEqual(ctx.dynamic_display.active_count,0);self.assertEqual(p.snapshot()['S'],0)

    def test_logical_clock_saturates_without_blocking_cleanup(self):
        _,ctx,p,_=execute(SETUP+'n=7 '+call());ctx.dynamic_display.elapsed_ms=2147483646
        ctx.dynamic_display.checkpoint(p._state)
        self.assertEqual(ctx.dynamic_display.elapsed_ms,2147483646);ctx.dynamic_display.close_all()


class DynamicPortTests(unittest.TestCase):
    def port_context(self):
        ctx=context();ctx.ports=rt.PortBank({'DIN':1,'GIN':1,'AIN':1},type_codes={1:'DIN',2:'GIN',3:'AIN'})
        return ctx

    def test_boolean_port_and_cancellation(self):
        ctx=self.port_context();ctx.ports.update('DIN',1,False)
        _,_,_,_=execute(SETUP+CHOICES+call('P'),ctx=ctx)
        self.assertEqual(line(ctx)[:6],'OFF   ')
        ctx.ports.update('DIN',1,True);ctx.dynamic_display.advance(1)
        self.assertEqual(line(ctx)[:6],'ON    ')
        values,_,_,_=execute("CNC_DYN_DISP(1,1,'W1',s)",ctx=ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.dynamic_display.active_count,0)

    def test_group_port_uses_enum_labels(self):
        ctx=self.port_context();ctx.ports.update('GIN',1,2)
        _,_,_,_=execute(SETUP+CHOICES+call('P',variable='2,1'),ctx=ctx)
        self.assertEqual(line(ctx)[:6],'OTHER ')

    def test_unsupplied_port_uses_stars(self):
        values,ctx,_,_=execute(SETUP+CHOICES+call('P'),ctx=self.port_context())
        self.assertEqual((values['S'],line(ctx)[:6]),(0,'******'))

    def test_unknown_code_out_of_range_and_real_ports_reject(self):
        for variable in ('9,1','1,2','3,1'):
            with self.subTest(variable=variable):
                values,ctx,_,_=execute(SETUP+CHOICES+call('P',variable=variable),ctx=self.port_context())
                self.assertEqual(values['S'],1);self.assertEqual(ctx.dynamic_display.active_count,0)


class DynamicReferenceAndGuardTests(unittest.TestCase):
    def test_field_and_indexed_sources_capture_storage_once(self):
        _,ctx,p,_=execute(SETUP+'e=1 data[1]=7 data[2]=9 '+call(variable='data[e]')+'e=2',decl=DECL+' data:ARRAY[2] OF INTEGER')
        p._state.values['DATA'].set(1,42);ctx.dynamic_display.advance(1)
        self.assertEqual(line(ctx)[:6],'42    ')

    def test_index_function_runs_once_at_registration(self):
        routines='ROUTINE pick:INTEGER BEGIN e=e+1 RETURN e END pick'
        values,ctx,_,_=execute(SETUP+'e=0 data[1]=7 '+call(variable='data[pick]'),decl=DECL+' data:ARRAY[2] OF INTEGER',routines=routines)
        ctx.dynamic_display.advance(5,force=True)
        self.assertEqual(values['E'],1);self.assertEqual(line(ctx)[:6],'7     ')

    def test_structure_field_and_using_capture_are_supported(self):
        prefix='TYPE RECORD_T=STRUCTURE value:INTEGER ENDSTRUCTURE'
        _,ctx,_,_=execute(SETUP+'data.value=42 USING data DO '+call(variable='value')+'ENDUSING',decl=DECL+' data:RECORD_T',prefix=prefix)
        self.assertEqual(line(ctx)[:6],'42    ')

    def test_active_counter_can_be_watched_read_only(self):
        values,ctx,_,_=execute(SETUP+'n=1 '+call()+"FOR n=1 TO 3 DO e=n ENDFOR CNC_DYN_DISI(n,'W1',s)")
        self.assertEqual(values['E'],3);self.assertEqual(values['S'],0)

    def test_live_label_changes_are_sampled(self):
        _,ctx,p,_=execute(SETUP+CHOICES+'b=FALSE '+call('B'))
        p._state.values['CHOICES'].set(1,'new');ctx.dynamic_display.advance(1)
        self.assertEqual(line(ctx)[:6],'new   ')

    def test_temporary_constant_local_and_formal_sources_are_blocked(self):
        for statement in (call(variable='42'),call(variable='n+1'),call(variable='MAXINT')):
            with self.subTest(statement=statement),self.assertRaises(TranslationError) as caught:compile_program(statement,decl=DECL)
            self.assertEqual(caught.exception.code,'E_STATIC_ARGUMENT')
        for declaration in ('VAR local_n:INTEGER','(local_n:INTEGER)'):
            routines='ROUTINE work '+declaration+' BEGIN '+call(variable='local_n')+'END work'
            with self.subTest(declaration=declaration),self.assertRaises(TranslationError) as caught:compile_program('',decl=DECL,routines=routines)
            self.assertEqual(caught.exception.code,'E_STATIC_ARGUMENT')

    def test_local_label_array_is_blocked(self):
        routines='ROUTINE work VAR labels:ARRAY[2] OF STRING[10] BEGIN '+call('B').replace('choices','labels')+'END work'
        with self.assertRaises(TranslationError) as caught:compile_program('',decl=DECL,routines=routines)
        self.assertEqual(caught.exception.code,'E_STATIC_ARGUMENT')

    def test_wrong_source_type_and_active_counter_status_remain_blocked(self):
        for statement,code in ((call('R',variable='n'),'E_TYPE'),("FOR s=1 TO 2 DO "+call()+"ENDFOR",'E_FOR_COUNTER')):
            with self.subTest(statement=statement),self.assertRaises(TranslationError) as caught:compile_program(statement,decl=DECL)
            self.assertEqual(caught.exception.code,code)

    def test_linked_module_binding_uses_shared_global_storage(self):
        ctx=context()
        main=source('MAIN',SETUP+'n=7 watch n=42 e=1',decl=DECL,routines='ROUTINE watch FROM LIB')
        lib=source('LIB','',decl='n FROM MAIN:INTEGER s:INTEGER',routines='ROUTINE watch BEGIN '+call()+'END watch')
        instance=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);instance.run('MAIN')
        self.assertEqual(line(ctx)[:6],'42    ')
        binding=ctx.dynamic_display.snapshot()['bindings'][0]
        self.assertEqual((binding['program'],binding['owner']),('LIB','MAIN'))

    def test_linked_module_can_cancel_its_shared_binding(self):
        ctx=context();main=source('MAIN',SETUP+'n=7 watch unwatch',decl=DECL,routines='ROUTINE watch FROM LIB ROUTINE unwatch FROM LIB')
        lib=source('LIB','',decl='n FROM MAIN:INTEGER s:INTEGER',routines='ROUTINE watch BEGIN '+call()+'END watch ROUTINE unwatch BEGIN CNC_DYN_DISI(n,\'W1\',s) END unwatch')
        instance=translate_project({'main':main,'lib':lib}).instantiate(context=ctx);instance.run('MAIN')
        self.assertEqual(ctx.dynamic_display.active_count,0)


class DynamicPersistenceAndValidationTests(unittest.TestCase):
    def test_active_bindings_block_context_save_until_cancelled(self):
        _,ctx,_,_=execute(SETUP+'n=7 '+call())
        with self.assertRaisesRegex(ValueError,'Cancel dynamic'):ctx.to_config()
        ctx.dynamic_display.close_all();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.dynamic_display.to_config(),ctx.dynamic_display.to_config())
        self.assertEqual(restored.dynamic_display.active_count,0)

    def test_snapshot_has_metadata_without_live_references(self):
        _,ctx,_,_=execute(SETUP+'n=7 '+call());snapshot=ctx.dynamic_display.snapshot()
        json.dumps(snapshot);snapshot['bindings'][0]['last_text']='changed'
        self.assertEqual(ctx.dynamic_display.snapshot()['bindings'][0]['last_text'],'7     ')

    def test_capacity_is_preflighted(self):
        values,ctx,_,_=execute(SETUP+'n=7 '+call()+call(row=2),ctx=context(limit=1))
        self.assertEqual(values['S'],5);self.assertEqual(ctx.dynamic_display.active_count,1);self.assertEqual(line(ctx,2),' '*20)

    def test_binding_sequence_limit_is_preflighted(self):
        values,ctx,_,_=execute(SETUP+'n=7 '+call(),ctx=context(sequence=2147483646))
        self.assertEqual(values['S'],5);self.assertEqual(ctx.dynamic_display.active_count,0)

    def test_invalid_layout_options_and_intervals_have_no_binding(self):
        cases=(call(width=21),call(row=4),call(col=21),call(interval=0),call().replace("'W1',6,0,0","'W1',6,16,0"),call().replace("'W1',6,0,0","'W1',6,0,1"))
        for statement in cases:
            with self.subTest(statement=statement):
                values,ctx,_,_=execute(SETUP+'n=7 '+statement)
                self.assertEqual(values['S'],1);self.assertEqual(ctx.dynamic_display.active_count,0)

    def test_invalid_format_does_not_paint_or_bind(self):
        for format in ('%s','prefix %d','%d^1','%999d','%.999d','%++d'):
            with self.subTest(format=format):
                values,ctx,_,_=execute(SETUP+'n=7 '+call(format=format))
                self.assertEqual(values['S'],1);self.assertEqual(line(ctx),' '*20);self.assertEqual(ctx.dynamic_display.active_count,0)

    def test_boolean_requires_two_label_slots(self):
        values,ctx,_,_=execute(SETUP+'b=FALSE '+call('B'),decl=DECL.replace('ARRAY[3]','ARRAY[1]'))
        self.assertEqual(values['S'],1);self.assertEqual(ctx.dynamic_display.active_count,0)

    def test_missing_window_reports_missing(self):
        values,ctx,_,_=execute('n=7 '+call())
        self.assertEqual(values['S'],3);self.assertEqual(ctx.dynamic_display.active_count,0)

    def test_missing_model_and_pendant_remain_explicit_errors(self):
        for ctx in (rt.ExecutionContext(),rt.ExecutionContext(dynamic_display=rt.DynamicDisplays())):
            with self.subTest(ctx=ctx):
                p,_=compile_program(call(),decl=DECL,context=ctx)
                with self.assertRaises(rt.KarelRuntimeError):p.run()

    def test_invalid_configuration_and_clock_advances_rejected(self):
        for config in ({'quantum_ms':0},{'elapsed_ms':-1},{'limit':0},{'sequence':True},{'bindings':[]}):
            with self.subTest(config=config),self.assertRaises(ValueError):rt.DynamicDisplays.from_config(config)
        with self.assertRaises(TypeError):rt.ExecutionContext(dynamic_display={})
        bank=rt.DynamicDisplays()
        for value in (-1,True,2147483647):
            with self.subTest(value=value),self.assertRaises(ValueError):bank.advance(value)

    def test_painted_history_survives_closed_state_reload(self):
        _,ctx,_,_=execute(SETUP+'n=7 '+call()+"CNC_DYN_DISI(n,'W1',s)")
        restored=rt.ExecutionContext.from_config(ctx.to_config())
        self.assertTrue(any(row['operation']=='DYNAMIC_WRITE' for row in restored.pendant.history))


class DynamicIntegrationBoundaryTests(unittest.TestCase):
    def test_readonly_position_orientation_can_be_watched(self):
        values,ctx,_,_=execute(SETUP+"CNV_STR_CONF('N',conf,s) pose=POS(0,0,0,0,0,0,conf) "+call('R',variable='pose.normal.x'),decl=DECL+' conf:CONFIG pose:POSITION')
        self.assertEqual(values['S'],0);self.assertEqual(line(ctx)[:6],'1.00  ')

    def test_registration_inside_for_counter_scope_is_read_only(self):
        values,ctx,_,_=execute(SETUP+'FOR n=1 TO 2 DO '+call()+"ENDFOR CNC_DYN_DISI(n,'W1',s)")
        self.assertEqual(values['S'],0);self.assertEqual(ctx.dynamic_display.sequence,2);self.assertEqual(ctx.dynamic_display.active_count,0)

    def test_scheduler_samples_shared_globals_without_background_threads(self):
        ctx=context()
        main=source('MAIN',SETUP+'n=1 '+call(width=0)+"RUN_TASK('WORKER',0,FALSE,FALSE,0,s) WAIT FOR EVENT[1] CNC_DYN_DISI(n,'W1',s)",decl=DECL)
        worker=source('WORKER','n=42 SIGNAL EVENT[1]',decl='n FROM MAIN:INTEGER')
        instance=translate_project({'main':main,'worker':worker}).instantiate(context=ctx);instance.run('MAIN')
        self.assertEqual(line(ctx)[:2],'42');self.assertEqual(ctx.dynamic_display.active_count,0)

    def test_field_paint_batch_rejects_late_invalid_location_atomically(self):
        _,ctx,p,_=execute(SETUP);before=ctx.pendant.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):ctx.pendant.paint_fields(p._state,'W1',[(1,1,'new'),(4,1,'bad')])
        self.assertEqual(ctx.pendant.snapshot(),before)


class DynamicHostNumericTests(unittest.TestCase):
    def test_host_poll_keeps_pythonic_real_range_and_format(self):
        _,ctx,_,_=execute(SETUP+'r=1.0E50 '+call('R',width=20,format='%.1e'))
        expected='1.0e+50'+' '*13
        self.assertEqual(line(ctx),expected)
        ctx.dynamic_display.advance(1,force=True)
        self.assertEqual(line(ctx),expected)


class DynamicDisplayReportTests(unittest.TestCase):
    def test_report_describes_static_inputs_clock_and_persistence(self):
        _,_,_,result=execute(SETUP+'n=7 '+call())
        policy=result.report['dynamic_display_policy']
        self.assertEqual(len(policy['calls']),12)
        self.assertEqual(policy['guide'],'docs/dynamic-displays.md')
        self.assertIn('Active bindings',policy['persistence'])
        self.assertIs(policy['controller_validated'],False)
