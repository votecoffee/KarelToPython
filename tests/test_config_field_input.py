"""Authored bounded CONFIG input across scalar callbacks and offline FILE transports."""
import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_keyboard import context as keyboard_context
from tests.test_keyboard_file_read import line_keys
from tests.test_pipe_attributes import bank as pipe_bank
from tests.test_serial_waits import streams,pending_project
from tests.test_acquisition import setup as daq_setup,write as daq_write
from tests.legacy_numeric_support import translate as legacy_translate

U={'uninitialized':True}
DEFAULT=dict(CFG_TURN_NO1=0,CFG_TURN_NO2=0,CFG_TURN_NO3=0,CFG_FLIP=False,CFG_LEFT=False,CFG_UP=False,CFG_FRONT=False)
FIELDS=tuple(DEFAULT)
DECL='cfg,other:CONFIG f:FILE n,m,s,visits:INTEGER small:SHORT flag,done:BOOLEAN text:STRING[40]'
READ_ALL='READ('+','.join('cfg.'+name for name in FIELDS)+')'


def seed(p):
    p._state.values['CFG'].values.update(DEFAULT);p._state.values.update(N=77,M=88,VISITS=0);return p


def build(body='READ(cfg.cfg_turn_no1)',**options):
    decl=options.pop('decl',DECL);p,r=compile_program(body,decl=decl,**options);return seed(p),r


def callback(values,body='READ(cfg.cfg_turn_no1)',**options):return build(body,read=lambda request:list(values),**options)


def file_task(data,statement='READ f(cfg.cfg_turn_no1)',mode='RO',ctx=None,name='data',prefix='',**options):
    ctx=rt.ExecutionContext(files=rt.MemoryFiles({'data':data})) if ctx is None else ctx
    return build(prefix+f" OPEN FILE f('{mode}','{name}') "+statement+' CLOSE FILE f',context=ctx,**options)


def close_file(p):
    f=p._state.values['F']
    if f.owner is not None:p._state.file_close(f)


def preserved(test,p):
    before=(copy.deepcopy(p.snapshot()['CFG']),p.snapshot()['N'],p.snapshot()['M'])
    with test.assertRaises(rt.KarelRuntimeError):p.run()
    f=p._state.values['F'];test.assertEqual((p.snapshot()['CFG'],p.snapshot()['N'],p.snapshot()['M']),before)
    test.assertEqual((f.position,f.status,f._read_operation),(0,1,None));close_file(p)


class ConfigCallbackInputTests(unittest.TestCase):
    def test_all_turn_and_boolean_fields(self):
        p,_=callback([-8,0,7,True,False,True,False],READ_ALL);v=p.run()['CFG'];self.assertEqual(v,dict(zip(FIELDS,[-8,0,7,True,False,True,False])))

    def test_every_turn_boundary_and_field(self):
        for field in FIELDS[:3]:
            for value in range(-8,8):
                p,_=callback([value],f'READ(cfg.{field})');self.assertEqual(p.run()['CFG'][field],value)

    def test_invalid_turn_values_are_rejected_before_publication(self):
        for value in (-9,8,2147483647,True,1.,rt.UNINITIALIZED):
            p,_=callback([value]);before=p.snapshot()['CFG']
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual(p.snapshot()['CFG'],before);self.assertEqual(p.read_requests[-1]['adapter_outcome'],'callback_result_rejected')

    def test_boolean_flags_keep_exact_boolean_domain(self):
        for value in (False,True):
            p,_=callback([value],'READ(cfg.cfg_flip)');self.assertIs(p.run()['CFG']['CFG_FLIP'],value)
        for value in (0,1,'ON',None):
            p,_=callback([value],'READ(cfg.cfg_flip)')
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertFalse(p.snapshot()['CFG']['CFG_FLIP'])

    def test_late_config_error_preserves_earlier_ordinary_output(self):
        p,_=callback([12,8],'READ(n,cfg.cfg_turn_no1)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['CFG']['CFG_TURN_NO1']),(77,0))

    def test_late_ordinary_error_preserves_earlier_config_output(self):
        p,_=callback([7,1.5],'READ(cfg.cfg_turn_no1,n)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['CFG']['CFG_TURN_NO1']),(77,0))

    def test_missing_callback_retains_fields(self):
        p,_=build();before=p.snapshot()['CFG']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'callback'):p.run()
        self.assertEqual(p.snapshot()['CFG'],before);self.assertEqual(p.read_requests[-1]['adapter_outcome'],'missing_adapter')

    def test_readonly_parent_fails_before_callback(self):
        calls=[];p,_=build(read=lambda request:calls.append(request));p._state.values['CFG'].read_only=True
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((calls,p.read_requests),([],()))

    def test_substituted_or_malformed_config_parent_is_rejected(self):
        for change in ('spec','fields','types','extra','uninitialized'):
            calls=[];p,_=build(read=lambda request:calls.append(request));cfg=p._state.values['CFG']
            if change=='spec':cfg.spec=('STRUCTURE','FOREIGN',tuple(cfg.types.items()))
            elif change=='fields':cfg.values.pop('CFG_FLIP')
            elif change=='types':cfg.types['CFG_TURN_NO1']=('REAL',)
            elif change=='extra':cfg.values['OTHER']=1
            else:p._state.values['CFG']=rt.UNINITIALIZED
            with self.subTest(change=change),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertEqual((calls,p.read_requests),([],()))

    def test_forged_direct_field_reference_is_rejected_before_callback(self):
        calls=[];state=rt.State({}, {},read=lambda request:calls.append(request));ref=rt.ConfigFieldReference(rt.INTEGER,{'x':0},'x')
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):state.read_items([ref],17)
        self.assertEqual((calls,state.read_requests),([],[]))
        cfg=rt.Structure(('CONFIG',))
        with rt._numeric_scope('pythonic'):
            for member in ([],1,None,'TURN_NO1'):
                with self.subTest(member=member),self.assertRaises(rt.KarelRuntimeError) as caught:rt.config_read_reference(cfg,member,17)
                self.assertEqual(caught.exception.line,17)

    def test_other_short_target_is_normalized_exactly_once(self):
        p,_=callback([7,32767],'READ(cfg.cfg_turn_no1,small)');v=p.run();self.assertEqual((v['CFG']['CFG_TURN_NO1'],v['SMALL']),(7,U))


class ConfigFormatAndScopeTests(unittest.TestCase):
    def test_signed_text_turns_and_boolean_tokens(self):
        p,_=build(READ_ALL,read=rt.TextInput('-8 0 7 ON OFF TRUE FALSE'));self.assertEqual(p.run()['CFG'],dict(zip(FIELDS,[-8,0,7,True,False,True,False])))

    def test_widths_and_integer_bases(self):
        p,_=build('READ(cfg.cfg_turn_no1::2::16,cfg.cfg_turn_no2::3::2)',read=rt.TextInput('-8111'));v=p.run()['CFG'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_TURN_NO2']),(-8,7))

    def test_boolean_formats_retain_existing_scalar_rules(self):
        p,_=build('READ(cfg.cfg_up::4::99)',read=rt.TextInput(' ON '));self.assertTrue(p.run()['CFG']['CFG_UP'])

    def test_target_and_format_calls_evaluate_once_in_order(self):
        routines='ROUTINE slot:INTEGER BEGIN visits=visits*10+1 RETURN 1 END slot ROUTINE width:INTEGER BEGIN visits=visits*10+2 RETURN 1 END width'
        p,_=build('READ(configs[slot()].cfg_turn_no1::width())',decl=DECL+' configs:ARRAY[2]OF CONFIG',routines=routines,read=rt.TextInput('7'))
        self.assertEqual((p.run()['VISITS'],p.snapshot()['CONFIGS'][0]['CFG_TURN_NO1']),(12,7))

    def test_targets_capture_left_to_right(self):
        routines='ROUTINE first:INTEGER BEGIN visits=visits*10+1 RETURN 1 END first ROUTINE second:INTEGER BEGIN visits=visits*10+2 RETURN 2 END second'
        p,_=callback([1,2],'READ(configs[first()].cfg_turn_no1,configs[second()].cfg_turn_no2)',decl=DECL+' configs:ARRAY[2]OF CONFIG',routines=routines);v=p.run();self.assertEqual((v['VISITS'],v['CONFIGS'][1]['CFG_TURN_NO2']),(12,2))

    def test_captured_using_config_fields(self):
        p,_=callback([7,True],'USING cfg DO READ(cfg_turn_no1,cfg_flip) ENDUSING');v=p.run()['CFG'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_FLIP']),(7,True))

    def test_computed_using_keeps_private_config(self):
        routines='ROUTINE make:CONFIG BEGIN RETURN cfg END make'
        p,_=callback([7],'USING make() DO READ(cfg_turn_no1) n=cfg_turn_no1 ENDUSING',routines=routines);self.assertEqual((p.run()['N'],p.snapshot()['CFG']['CFG_TURN_NO1']),(7,0))

    def test_nested_user_record_config_field(self):
        p,_=callback([7],'READ(packet.config_data.cfg_turn_no1)',prefix='TYPE packet_t=STRUCTURE config_data:CONFIG ENDSTRUCTURE',decl=DECL+' packet:packet_t');self.assertEqual(p.run()['PACKET']['CONFIG_DATA']['CFG_TURN_NO1'],7)

    def test_position_config_remains_writable(self):
        p,_=callback([-8,True],'READ(point.config_data.cfg_turn_no1,point.config_data.cfg_front)',decl=DECL+' point:POSITION');v=p.run()['POINT']['CONFIG_DATA'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_FRONT']),(-8,True))

    def test_exact_config_formal_and_byname_keep_borrowed_storage(self):
        for actual in ('cfg',"BYNAME('','CFG',s)"):
            p,_=callback([7],f'load({actual})',routines='ROUTINE load(v:CONFIG) BEGIN READ(v.cfg_turn_no1) END load');self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],7)

    def test_three_dimensional_array_element(self):
        p,_=callback([-8],'READ(configs[1,1,1].cfg_turn_no1)',decl=DECL+' configs:ARRAY[1,1,1]OF CONFIG');self.assertEqual(p.run()['CONFIGS'][0][0][0]['CFG_TURN_NO1'],-8)

    def test_report_records_canonical_fields_bounds_and_locations(self):
        _,r=callback([7,True],'READ(cfg.cfg_turn_no1::1,cfg.cfg_flip)');rows=r.report['config_field_reads'];self.assertEqual([row['field'] for row in rows],['CFG_TURN_NO1','CFG_FLIP']);self.assertEqual(rows[0]['integer_range'],[-8,7]);self.assertNotIn('integer_range',rows[1]);self.assertTrue(all(row['target_evaluated_once'] and row['validated_before_publication'] and not row['file_input'] for row in rows));json.dumps(r.report)


class ConfigFileInputTests(unittest.TestCase):
    def test_memory_text_file(self):
        p,_=file_task(b'-8 7 ON\n','READ f(cfg.cfg_turn_no1,cfg.cfg_turn_no2,cfg.cfg_flip,CR)');v=p.run()['CFG'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_TURN_NO2'],v['CFG_FLIP']),(-8,7,True))

    def test_memory_binary_file(self):
        p,_=file_task(struct.pack('<ii?',-8,7,True),'READ f(cfg.cfg_turn_no1,cfg.cfg_turn_no2,cfg.cfg_flip)',mode='RB');v=p.run()['CFG'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_TURN_NO2'],v['CFG_FLIP']),(-8,7,True))

    def test_reverse_binary_widths(self):
        p,_=file_task(struct.pack('>ii',-8,7),'READ f(cfg.cfg_turn_no1,cfg.cfg_turn_no2)',mode='RB',prefix='SET_FILE_ATR(f,ATR_REVERSE)');self.assertEqual(p.run()['CFG']['CFG_TURN_NO2'],7)

    def test_invalid_text_field_rolls_back_all_outputs_and_cursor(self):
        p,_=file_task(b'12 8\n','READ f(n,cfg.cfg_turn_no1,CR)');preserved(self,p)

    def test_invalid_binary_field_rolls_back_all_outputs_and_cursor(self):
        p,_=file_task(struct.pack('<ii',12,8),'READ f(n,cfg.cfg_turn_no1)',mode='RB');preserved(self,p)

    def test_short_binary_input_rolls_back(self):
        p,_=file_task(struct.pack('<i',7),'READ f(cfg.cfg_turn_no1,n)',mode='RB');preserved(self,p)

    def test_rooted_directory_file_uses_same_bounded_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'data').write_bytes(b'-8\n');bank=rt.DirectoryFiles(folder,devices={'RD':''});p,_=file_task(b'',name='RD:data',ctx=rt.ExecutionContext(files=bank),statement='READ f(cfg.cfg_turn_no1,CR)');self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],-8)

    def test_virtual_device_binary_input(self):
        bank=rt.DeviceFiles({'RD:':{'capacity':1024}},{'RD:data':struct.pack('<i',7)});p,_=file_task(b'',name='RD:data',mode='RB',ctx=rt.ExecutionContext(files=bank));self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],7)

    def test_explicit_messaging_input(self):
        ctx=rt.ExecutionContext(messaging=rt.Messaging({'S1:':{'input':'7\n'}}));p,_=file_task(b'',name='S1:',ctx=ctx,prefix="MSG_CONNECT('S1:',s)",statement='READ f(cfg.cfg_turn_no1,CR)');self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],7)

    def test_acquisition_binary_input(self):
        ctx=daq_setup();daq_write(ctx,-8);daq_write(ctx,7);p,_=file_task(b'',name='PIP:AUTHORED.DAT',mode='RB',ctx=ctx,statement='READ f(cfg.cfg_turn_no1,cfg.cfg_turn_no2)');v=p.run()['CFG'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_TURN_NO2']),(-8,7))

    def test_bad_parent_capture_does_not_consume_file_input(self):
        p,_=file_task(b'7\n');cfg=p._state.values['CFG'];cfg.spec=('STRUCTURE','FOREIGN',tuple(cfg.types.items()))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        f=p._state.values['F'];self.assertEqual((f.position,f.status,f._read_operation),(0,0,None));close_file(p)

    def test_formatted_binary_config_and_short_sentinel(self):
        p,_=file_task(struct.pack('<hh',7,32767),'READ f(cfg.cfg_turn_no1::2,small::2)',mode='RB');v=p.run();self.assertEqual((v['CFG']['CFG_TURN_NO1'],v['SMALL']),(7,U))


class ConfigSerialInputTests(unittest.TestCase):
    def finite(self,data,mode='RO',statement='READ f(cfg.cfg_turn_no1,CR)'):
        ctx=rt.ExecutionContext(serial_streams=rt.SerialStreams({2:{'input':data}}));return file_task(b'',name='P2:',mode=mode,ctx=ctx,statement=statement)[0]

    def test_finite_serial_text(self):
        p=self.finite(b'7\n');self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],7);self.assertEqual(p._state.execution.serial_streams.snapshot()[2]['input'],b'')

    def test_finite_serial_binary(self):
        p=self.finite(struct.pack('<i',-8),mode='RB',statement='READ f(cfg.cfg_turn_no1)');self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],-8)

    def test_finite_serial_bad_field_retains_prefix(self):
        p=self.finite(b'12 8\n',statement='READ f(n,cfg.cfg_turn_no1,CR)');preserved(self,p);self.assertEqual(p._state.execution.serial_streams.snapshot()[2]['input'],b'12 8\n')

    def test_waiting_fragments_publish_once(self):
        bank,ctx=streams(b'-8 ');calls=[]
        def sleeper(_):calls.append(1);self.assertEqual(p.snapshot()['CFG'],DEFAULT);bank.feed(2,b'7\n')
        p,_=file_task(b'',name='P2:',ctx=ctx,statement='READ f(cfg.cfg_turn_no1,cfg.cfg_turn_no2,CR)',sleep=sleeper);v=p.run()['CFG'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_TURN_NO2'],calls),(-8,7,[1]));self.assertEqual(len(p.read_requests),1);self.assertFalse(bank._pending)

    def test_waiting_invalid_field_preserves_cursor_and_cleans_pending(self):
        bank,ctx=streams(b'12 8\n');p,_=file_task(b'',name='P2:',ctx=ctx,statement='READ f(n,cfg.cfg_turn_no1,CR)',sleep=lambda _:None);preserved(self,p);self.assertFalse(bank._pending);self.assertEqual(bank.snapshot()[2]['input'],b'12 8\n')

    def test_final_incomplete_input_keeps_earlier_config_value(self):
        bank,ctx=streams(b'7 ',final=True);p,_=file_task(b'',name='P2:',ctx=ctx,statement='READ f(cfg.cfg_turn_no1,n,CR)',sleep=lambda _:None);preserved(self,p);self.assertFalse(bank._pending)

    def test_pause_resume_keeps_captured_target_and_format(self):
        bank,_=streams();routines='ROUTINE slot:INTEGER BEGIN visits=visits*10+1 RETURN 1 END slot ROUTINE width:INTEGER BEGIN visits=visits*10+2 RETURN 1 END width'
        decl=DECL+' configs:ARRAY[2]OF CONFIG';body="OPEN FILE f('RO','P2:') visits=0 READ f(configs[slot()].cfg_turn_no1::width()) CLOSE FILE f"
        project=translate_project({'main':source('MAIN',body,decl=decl,routines=routines)}).instantiate(context=rt.ExecutionContext(serial_streams=bank));project.scheduler.start('MAIN')
        for _ in range(80):
            project.scheduler.step()
            if bank._pending:break
        p=project.programs['MAIN'];self.assertEqual(p.snapshot()['VISITS'],12);p.pause()
        for _ in range(30):
            project.scheduler.step()
            if p.task_state=='paused':break
        bank.feed(2,b'7');project.scheduler.continue_task('MAIN');project.scheduler.run();self.assertEqual((p.snapshot()['VISITS'],p.snapshot()['CONFIGS'][0]['CFG_TURN_NO1']),(12,7));self.assertFalse(bank._pending)

    def test_cancel_waiting_text_keeps_all_destinations(self):
        bank,ctx=streams(b'12 ')
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build("OPEN FILE f('RO','P2:') READ f(n,cfg.cfg_turn_no1,CR) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper);v=p.run();self.assertEqual((v['N'],v['CFG'],v['S'],p.read_requests),(77,DEFAULT,6,()));self.assertEqual(bank.snapshot()[2]['input'],b'12 ')

    def test_cancel_waiting_binary_keeps_complete_earlier_field(self):
        data=struct.pack('<i',7);bank,ctx=streams(data)
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=build("OPEN FILE f('RB','P2:') READ f(cfg.cfg_turn_no1,n) s=IO_STATUS(f) CLOSE FILE f",context=ctx,sleep=sleeper);v=p.run();self.assertEqual((v['N'],v['CFG'],v['S']),(77,DEFAULT,6));self.assertEqual(bank.snapshot()[2]['input'],data)

    def test_stop_unwinds_pending_without_consuming_input(self):
        bank,_=streams(b'7 ');project=pending_project(bank,body="OPEN FILE f('RO','P2:') READ f(cfg.cfg_turn_no1,n,CR) CLOSE FILE f",decl=DECL);p=project.programs['MAIN'];project.scheduler.stop('MAIN');self.assertEqual((p.snapshot()['CFG']['CFG_TURN_NO1'],bank._pending,p.snapshot()['F']['position']),(U,{},0));close_file(p)

    def test_abort_unwinds_pending_without_publication(self):
        bank,_=streams(b'7 ');project=pending_project(bank,body="OPEN FILE f('RO','P2:') READ f(cfg.cfg_turn_no1,n,CR) CLOSE FILE f",decl=DECL);p=project.programs['MAIN'];rt.request_task_control(p._state,'ABORT')
        with self.assertRaises(rt.KarelAbort):project.scheduler.run()
        self.assertEqual((p.snapshot()['CFG']['CFG_TURN_NO1'],bank._pending),(U,{}));close_file(p)

    def test_budget_failure_cleans_pending_config_read(self):
        bank,_=streams();project=pending_project(bank,body="OPEN FILE f('RO','P2:') READ f(cfg.cfg_turn_no1,CR) CLOSE FILE f",decl=DECL);p=project.programs['MAIN'];p._state.max_steps=p._state.steps+1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):project.scheduler.run(max_cycles=100)
        self.assertFalse(bank._pending);self.assertIsNone(p._state.values['F']._read_operation);close_file(p)


class ConfigPipeInputTests(unittest.TestCase):
    def pipe(self,data,statement='READ f(cfg.cfg_turn_no1,CR)',mode='RO',wait=False,sleep=None):
        bank=pipe_bank(data);ctx=rt.ExecutionContext(file_pipes=bank);prefix='SET_FILE_ATR(f,ATR_PIPWAIT,WAIT_USED) ' if wait else ''
        p,r=file_task(b'',name='PIP:LOG',mode=mode,ctx=ctx,statement=statement,prefix=prefix,sleep=sleep);return p,bank,r

    def test_snapshot_pipe_text(self):
        p,_,_=self.pipe(b'7\n');self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],7)

    def test_snapshot_pipe_binary(self):
        p,_,_=self.pipe(struct.pack('<i',-8),mode='RB',statement='READ f(cfg.cfg_turn_no1)');self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],-8)

    def test_invalid_text_prefix_does_not_publish(self):
        p,bank,_=self.pipe(b'12 8\n',statement='READ f(n,cfg.cfg_turn_no1,CR)');preserved(self,p);self.assertEqual(bank.snapshot(),{'PIP:LOG':b'12 8\n'})

    def test_invalid_binary_prefix_does_not_publish(self):
        data=struct.pack('<ii',12,8);p,bank,_=self.pipe(data,mode='RB',statement='READ f(n,cfg.cfg_turn_no1)');preserved(self,p);self.assertEqual(bank.snapshot(),{'PIP:LOG':data})

    def test_waiting_pipe_retains_atomicity_across_feed(self):
        def sleeper(_):self.assertEqual(p.snapshot()['CFG'],DEFAULT);bank.feed('LOG',b'7\n')
        p,bank,_=self.pipe(b'-8 ',statement='READ f(cfg.cfg_turn_no1,cfg.cfg_turn_no2,CR)',wait=True,sleep=sleeper);v=p.run()['CFG'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_TURN_NO2']),(-8,7));self.assertFalse(bank._reads)

    def test_cancel_waiting_pipe_keeps_config(self):
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,bank,_=self.pipe(b'7 ',statement='READ f(cfg.cfg_turn_no1,n,CR) s=IO_STATUS(f)',wait=True,sleep=sleeper);v=p.run();self.assertEqual((v['CFG'],v['S'],p.read_requests),(DEFAULT,6,()));self.assertFalse(bank._reads)


class ConfigKeyboardInputTests(unittest.TestCase):
    def keyboard(self,keys,statement='READ f(cfg.cfg_turn_no1,CR)',prefix='',sleep=None):
        ctx=keyboard_context(keys=keys);p,r=file_task(b'',name='KB:TPKB',mode='RW',ctx=ctx,statement=statement,prefix=prefix,sleep=sleep or (lambda _:None));return p,ctx,r

    def test_submitted_turn_line(self):
        p,ctx,_=self.keyboard(line_keys('-8'));self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],-8);self.assertEqual(ctx.keyboard.history[-1]['outcome'],'completed')

    def test_mixed_integer_and_boolean_fields(self):
        p,_,_=self.keyboard(line_keys('7 ON'),statement='READ f(cfg.cfg_turn_no1,cfg.cfg_flip,CR)');v=p.run()['CFG'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_FLIP']),(7,True))

    def test_invalid_late_turn_keeps_submitted_line_and_cursor(self):
        p,ctx,_=self.keyboard(line_keys('12 8'),statement='READ f(n,cfg.cfg_turn_no1,CR)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        h=p._state.values['F'];self.assertEqual((p.snapshot()['N'],p.snapshot()['CFG'],h.position,h.status),(77,DEFAULT,0,1));self.assertEqual(ctx.keyboard._handles[h]['pending'],'12 8\n');close_file(p)

    def test_bad_config_parent_consumes_no_key_events(self):
        keys=line_keys('7');p,ctx,_=self.keyboard(keys);p._state.values['CFG'].values.pop('CFG_FRONT')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual([event['key'] for event in ctx.keyboard.events],keys);close_file(p)

    def test_line_editing_retains_bounded_conversion(self):
        p,_,_=self.keyboard(['8','DELETE','7','ENTER']);self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],7)

    def test_adjacent_fixed_width_config_fields(self):
        p,_,_=self.keyboard(line_keys('-87'),statement='READ f(cfg.cfg_turn_no1::2,cfg.cfg_turn_no2::1,CR)');v=p.run()['CFG'];self.assertEqual((v['CFG_TURN_NO1'],v['CFG_TURN_NO2']),(-8,7))

    def test_passall_numeric_config_stays_rejected(self):
        p,ctx,_=self.keyboard(['7'],statement='READ f(cfg.cfg_turn_no1::1)',prefix='SET_FILE_ATR(f,ATR_PASSALL) ')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'STRING'):p.run()
        self.assertEqual(p.snapshot()['CFG'],DEFAULT);self.assertEqual([event['key'] for event in ctx.keyboard.events],['7']);close_file(p)

    def test_cancel_keyboard_wait_preserves_config(self):
        ctx=keyboard_context(events=[dict(key='ENTER',at_ms=100)])
        def sleeper(_):rt.cancel_file(p._state,p._state.values['F'])
        p,_=file_task(b'',name='KB:TPKB',mode='RW',ctx=ctx,statement='READ f(cfg.cfg_turn_no1,CR) s=IO_STATUS(f)',sleep=sleeper);v=p.run();self.assertEqual((v['CFG'],v['S'],p.read_requests),(DEFAULT,6,()));self.assertFalse(ctx.keyboard._active)

    def test_config_status_alias_in_read_kb_remains_blocked(self):
        body="READ_KB(f,text,40,KC_DISPLAY,KC_ENTER_KEY,-1,'',n,m,cfg.cfg_turn_no1)"
        with self.assertRaises(TranslationError) as error:build(body)
        self.assertEqual(error.exception.code,'E_CONFIG_OUTPUT')

    def test_closed_keyboard_data_json_is_not_a_pending_read(self):
        p,ctx,_=self.keyboard(line_keys('7'));p.run();saved=json.loads(json.dumps(ctx.to_config()));loaded=rt.ExecutionContext.from_config(saved);self.assertEqual(loaded.to_config(),saved)


class ConfigReadBoundaryTests(unittest.TestCase):
    def test_whole_config_read_remains_rejected(self):
        with self.assertRaises(TranslationError) as error:build('READ(cfg)')
        self.assertEqual(error.exception.code,'E_READ_TYPE')

    def test_position_orientation_read_remains_rejected(self):
        with self.assertRaises(TranslationError) as error:build('READ(point.normal.x)',decl=DECL+' point:POSITION')
        self.assertEqual(error.exception.code,'E_POSITION_READ_ONLY')

    def test_generic_conversion_config_status_alias_is_not_relaxed(self):
        with self.assertRaises(TranslationError) as error:build("CNV_STR_CONF('N',cfg,cfg.cfg_turn_no1)")
        self.assertEqual(error.exception.code,'E_CONFIG_OUTPUT')

    def test_runtime_legacy_config_target_remains_rejected(self):
        p,_=build();ref=rt.field_reference(p._state.values['CFG'],'CFG_TURN_NO1');calls=[];p._state._read=lambda request:calls.append(request)
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):p._state.read_items([ref],17)
        self.assertEqual(calls,[])
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR c:CONFIG BEGIN READ(c.cfg_turn_no1) END T')

    def test_config_counter_and_active_ordinary_counter_guards_remain(self):
        for body in ('FOR cfg.cfg_turn_no1=1 TO 2 DO READ(cfg.cfg_turn_no1) ENDFOR','FOR n=1 TO 2 DO READ(n,cfg.cfg_turn_no1) ENDFOR'):
            with self.subTest(body=body),self.assertRaises(TranslationError):build(body)

    def test_const_destination_remains_rejected(self):
        with self.assertRaises(TranslationError) as error:build('READ(code)',prefix='CONST code=7')
        self.assertEqual(error.exception.code,'E_CONST_ASSIGN')

    def test_unknown_config_field_does_not_gain_alias_inference(self):
        with self.assertRaises(TranslationError) as error:build('READ(cfg.turn_no1)')
        self.assertEqual(error.exception.code,'E_FIELD')

    def test_repeated_field_aliases_validate_before_ordered_assignment(self):
        p,_=callback([1,7],'READ(cfg.cfg_turn_no1,cfg.cfg_turn_no1)');self.assertEqual(p.run()['CFG']['CFG_TURN_NO1'],7)
        p,_=callback([1,8],'READ(cfg.cfg_turn_no1,cfg.cfg_turn_no1)')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CFG']['CFG_TURN_NO1'],0)

    def test_policy_and_saved_config_keep_domains_without_native_claim(self):
        p,r=callback([-8]);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));q,_=compile_program('n=cfg.cfg_turn_no1',decl=DECL,context=rt.ExecutionContext.from_config(saved));self.assertEqual(q.run()['N'],-8)
        policy=r.report['config_field_read_policy'];self.assertFalse(policy['controller_validated']);self.assertEqual(policy['guide'],'docs/config-field-input.md');self.assertIn('-8..7',policy['domains']);self.assertIn('CONFIG conversion status',policy['boundary'])


if __name__=='__main__':unittest.main()
