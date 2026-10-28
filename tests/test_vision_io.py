"""Authored image, reader, view-line and logical vision-device regressions."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_vision_results import found,batch
from tests.test_path_geometry import SCHEMAS,DECL as PATH_DECL
from tests.test_project_scheduler import source


def pixels(width=2,height=2,channels=3):
    data=bytes((i*37)%256 for i in range(width*height*channels))
    return dict(width=width,height=height,channels=channels,pixels=data.hex())


def image_record(**options):return dict(process='SCAN',views=[1],image=pixels(),**options)


def capture(status=0,**options):
    row=dict(process='SCAN',views=[1],status=status)
    if not status:row['image']=pixels()
    row.update(options);return row


def lines():return dict(group=2,frame=3,focal=[0,0,10],nodes=[dict(direction=[0,0,-1],polarity=[1,0,0],model=7)])


def context(*runs,io=None,views=(1,),**options):
    config=dict(image_count=2,images={'1':image_record()}) if io is None else io
    return rt.ExecutionContext(vision=rt.VisionServices(processes={'SCAN':dict(views=list(views),runs=list(runs),parameters={'GAIN':1.})},io=config,**options),files=rt.MemoryFiles(),strings=rt.StringRegisters(2,capacity=4))


def execute(body,ctx,decl='s,n:INTEGER powered:BOOLEAN',**options):
    p,result=compile_program(body,decl=decl,context=ctx,**options);return p.run(),p,result


class ImageExecutionTests(unittest.TestCase):
    def test_capture_replaces_register_with_detached_input(self):
        row=capture();ctx=context(io={'image_count':1,'captures':[row]});row['image']['pixels']='00'*12
        values,_,_=execute("V_SNAP_VIEW('scan',0,1,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.io.images[1]['image']['pixels'],bytes.fromhex(pixels()['pixels']));self.assertEqual(ctx.vision.io.captures,[])

    def test_failed_capture_consumed_without_replacing_existing_image(self):
        ctx=context(io={'image_count':1,'images':{'1':image_record()},'captures':[capture(117)]});before=ctx.vision.io.to_config()['images']
        values,_,_=execute("V_SNAP_VIEW('scan',1,1,s)",ctx);self.assertEqual(values['S'],117);self.assertEqual(ctx.vision.io.to_config()['images'],before);self.assertEqual(ctx.vision.io.captures,[])

    def test_invalid_capture_address_and_selection_preserve_queue(self):
        for call in ("V_SNAP_VIEW('scan',1,0,s)","V_SNAP_VIEW('scan',4,1,s)","V_SNAP_VIEW('absent',1,1,s)"):
            ctx=context(io={'image_count':1,'captures':[capture()]});values,_,_=execute(call,ctx);self.assertEqual(values['S'],2);self.assertEqual(len(ctx.vision.io.captures),1);self.assertEqual(ctx.vision.io.images,{})

    def test_missing_capture_does_not_invent_pixels(self):
        ctx=context();p,_=compile_program("s=99 V_SNAP_VIEW('scan',1,1,s)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capture response'):p.run()
        self.assertEqual(p.snapshot()['S'],99);self.assertEqual(ctx.vision.sequence,0)

    def test_find_view_consumes_matching_image_bound_run(self):
        ctx=context(dict(batch(found(5),view=1),image_reg=1));values,_,_=execute("V_FIND_VIEW('scan',1,1,s) V_GET_OFFSET('scan',1,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],5.);self.assertEqual(ctx.vision.processes['SCAN']['runs'],[])

    def test_regular_run_cannot_consume_image_bound_or_line_batches(self):
        for run in (dict(batch(found(),view=1),image_reg=1),dict(batch(view=1),operation='lines',view_lines=lines())):
            ctx=context(run);values,_,_=execute("V_RUN_FIND('scan',1,s)",ctx);self.assertEqual(values['S'],2);self.assertEqual(len(ctx.vision.processes['SCAN']['runs']),1)

    def test_missing_image_and_wrong_image_binding_preserve_run(self):
        for io,run,code in [({'image_count':1},dict(batch(view=1),image_reg=1),1),
            ({'image_count':2,'images':{'1':image_record()}},dict(batch(view=1),image_reg=2),2)]:
            ctx=context(run,io=io);values,_,_=execute("V_FIND_VIEW('scan',1,1,s)",ctx);self.assertEqual(values['S'],code);self.assertEqual(len(ctx.vision.processes['SCAN']['runs']),1)

    def test_find_rejects_unbound_batch_and_missing_completion(self):
        ctx=context(batch(view=1));values,_,_=execute("V_FIND_VIEW('scan',1,1,s)",ctx);self.assertEqual(values['S'],2)
        ctx=context()
        with self.assertRaisesRegex(rt.KarelRuntimeError,'completed result batch'):execute("V_FIND_VIEW('scan',1,1,s)",ctx)

    def test_find_failed_completion_replaces_old_active_results(self):
        ctx=context(batch(found()),dict(batch(view=1,status=51),image_reg=1));before=ctx.vision.io.to_config()['images']
        values,_,_=execute("V_RUN_FIND('scan',1,s) V_FIND_VIEW('scan',1,1,s) V_GET_OFFSET('scan',1,s)",ctx)
        self.assertEqual(values['S'],51);self.assertEqual(ctx.vision.registers,{});self.assertEqual(ctx.vision.io.to_config()['images'],before)

    def test_find_captures_one_shot_parameters_once(self):
        ctx=context(dict(batch(view=1),image_reg=1),overrides={'BRIGHT':{'process':'SCAN','parameter':'GAIN'}})
        execute("V_OVERRIDE('BRIGHT',8,s) V_FIND_VIEW('scan',1,1,s)",ctx)
        process=ctx.vision.processes['SCAN'];self.assertEqual(process['active']['parameters'],{'GAIN':8.});self.assertEqual(process['temporary'],{})

    def test_multiview_capture_can_feed_one_selected_view(self):
        ctx=context(dict(batch(view=2),image_reg=1),views=(1,2),io={'image_count':1,'captures':[capture(views=[1,2])]})
        values,_,_=execute("V_SNAP_VIEW('scan',-1,1,s) V_FIND_VIEW('scan',2,1,s)",ctx);self.assertEqual(values['S'],0)

    def test_image_owner_and_coverage_are_checked(self):
        ctx=context(dict(batch(view=2),image_reg=1),views=(1,2));values,_,_=execute("V_FIND_VIEW('scan',2,1,s)",ctx);self.assertEqual(values['S'],2)
        config=ctx.to_config();config['vision']['processes']['OTHER']={'views':[1],'runs':[]};config['vision']['io']['images']['1']['process']='OTHER'
        restored=rt.ExecutionContext.from_config(config);values,_,_=execute("V_FIND_VIEW('scan',1,1,s)",restored);self.assertEqual(values['S'],2)


class ImageExportTests(unittest.TestCase):
    def test_png_chunks_crc_dimensions_and_pixels(self):
        for channels in (1,3):
            image=pixels(3,2,channels);ctx=context(io={'image_count':1,'images':{'1':dict(image_record(),image=image)}})
            values,_,_=execute("V_SAVE_IMREG(1,'image.PNG',s)",ctx);self.assertEqual(values['S'],0)
            data=ctx.files.snapshot()['image.PNG'];self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n');offset=8;chunks=[];compressed=b''
            while offset<len(data):
                size=int.from_bytes(data[offset:offset+4],'big');kind=data[offset+4:offset+8];payload=data[offset+8:offset+8+size]
                self.assertEqual(int.from_bytes(data[offset+8+size:offset+12+size],'big'),zlib.crc32(kind+payload));chunks.append(kind)
                if kind==b'IHDR':self.assertEqual(struct.unpack('>IIBBBBB',payload),(3,2,8,0 if channels==1 else 2,0,0,0))
                if kind==b'IDAT':compressed+=payload
                offset+=12+size
            expected=bytes.fromhex(image['pixels']);self.assertEqual(zlib.decompress(compressed),b'\0'+expected[:3*channels]+b'\0'+expected[3*channels:]);self.assertEqual(chunks,[b'IHDR',b'IDAT',b'IEND'])

    def test_bmp_dimensions_bottom_up_bgr_and_padding(self):
        for width in (1,2,3,4):
            for channels in (1,3):
                image=pixels(width,2,channels);ctx=context(io={'image_count':1,'images':{'1':dict(image_record(),image=image)}})
                execute("V_SAVE_IMREG(1,'image.bmp',s)",ctx);data=ctx.files.snapshot()['image.bmp']
                self.assertEqual(data[:2],b'BM');self.assertEqual(int.from_bytes(data[2:6],'little'),len(data));self.assertEqual(int.from_bytes(data[10:14],'little'),54)
                header=struct.unpack('<IiiHHIIiiII',data[14:54]);self.assertEqual(header[:6],(40,width,2,1,24,0));stride=((width*24+31)//32)*4
                raw=bytes.fromhex(image['pixels'])
                for y in range(2):
                    row=raw[(1-y)*width*channels:(2-y)*width*channels];expected=b''
                    for x in range(width):expected+=bytes([row[x]])*3 if channels==1 else row[x*3:x*3+3][::-1]
                    self.assertEqual(data[54+y*stride:54+(y+1)*stride],expected+b'\0'*(stride-width*3))

    def test_bad_extension_invalid_address_and_missing_image_preserve_file(self):
        for call,code in [("V_SAVE_IMREG(1,'old.jpg',s)",2),("V_SAVE_IMREG(0,'old.png',s)",2),("V_SAVE_IMREG(2,'old.png',s)",1)]:
            ctx=context();ctx.files=rt.MemoryFiles({'old.jpg':b'keep','old.png':b'keep'});values,_,_=execute(call,ctx);self.assertEqual(values['S'],code);self.assertEqual(ctx.files.snapshot(),{'old.jpg':b'keep','old.png':b'keep'})

    def test_busy_export_preserves_open_file_and_position(self):
        ctx=context();ctx.files=rt.MemoryFiles({'image.png':b'keep'});handle=rt.FileHandle();ctx.files.open(handle,'RO','image.png')
        values,_,_=execute("V_SAVE_IMREG(1,'image.png',s)",ctx);self.assertEqual(values['S'],3);self.assertEqual(ctx.files.snapshot()['image.png'],b'keep');self.assertEqual(handle.position,0);ctx.files.close(handle)

    def test_export_limit_and_missing_backend_fail_without_writes(self):
        ctx=context();ctx.files=rt.MemoryFiles({'image.png':b'keep'},limit=8);values,_,_=execute("V_SAVE_IMREG(1,'image.png',s)",ctx)
        self.assertEqual(values['S'],5);self.assertEqual(ctx.files.snapshot()['image.png'],b'keep')
        ctx.files=None
        with self.assertRaisesRegex(rt.KarelRuntimeError,'files'):execute("V_SAVE_IMREG(1,'image.png',s)",ctx)

    def test_rooted_exports_and_device_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ctx=context();ctx.files=rt.DirectoryFiles(root,devices={'UD':'images'});(root/'images').mkdir()
            values,_,_=execute("V_SAVE_IMREG(1,'UD:color.png',s)",ctx);self.assertEqual(values['S'],0);self.assertTrue((root/'images/color.png').read_bytes().startswith(b'\x89PNG'))
            values,_,_=execute("V_SAVE_IMREG(1,'../outside.png',s)",ctx);self.assertEqual(values['S'],6);self.assertEqual(len(list(root.rglob('*.png'))),1)

    def test_rooted_replace_failure_preserves_existing_data_and_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'image.png').write_bytes(b'keep');ctx=context();ctx.files=rt.DirectoryFiles(root)
            with patch('karel2py.storage.atomic_bytes',side_effect=OSError('authored write failure')):values,_,_=execute("V_SAVE_IMREG(1,'image.png',s)",ctx)
            self.assertEqual(values['S'],6);self.assertEqual((root/'image.png').read_bytes(),b'keep');self.assertEqual(ctx.files.files,{})

    def test_virtual_device_capacity_and_read_only_guards(self):
        for properties in ({'capacity':20},{'capacity':1000,'read_only':True},{'capacity':1000,'mounted':False}):
            ctx=context();ctx.files=rt.DeviceFiles({'UD:':properties},{'UD:image.png':b'keep'})
            values,_,_=execute("V_SAVE_IMREG(1,'UD:image.png',s)",ctx);self.assertEqual(values['S'],6);self.assertEqual(ctx.files.snapshot()['UD:image.png'],b'keep')

    def test_virtual_replacement_accounts_obsolete_bytes(self):
        ctx=context();ctx.files=rt.DeviceFiles({'FR:':{'capacity':1000}},{'FR:image.png':b'keep'})
        values,_,_=execute("V_SAVE_IMREG(1,'FR:image.png',s)",ctx);self.assertEqual(values['S'],0);self.assertEqual(ctx.files._volumes['FR']['garbage'],4)

    def test_budget_failure_during_encoding_preserves_file(self):
        ctx=context(io={'image_count':1,'images':{'1':dict(image_record(),image=pixels(1,128,1))}});ctx.files=rt.MemoryFiles({'image.png':b'keep'})
        p,_=compile_program("V_SAVE_IMREG(1,'image.png',s)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=50)
        self.assertEqual(ctx.files.snapshot()['image.png'],b'keep');self.assertEqual(ctx.vision.sequence,0)

    def test_unknown_save_overloads_remain_rejected(self):
        for call in ("V_SAVE_IMREG(1,'a.png',s,TRUE)","V_SAVE_IMREG('',1,'a.png',s,TRUE)"):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(call)


class ReaderTests(unittest.TestCase):
    def test_register_output_reports_stored_length_after_truncation(self):
        ctx=context(dict(batch(),read_result='PART-123'));values,_,_=execute("V_RUN_FIND('scan',0,s) V_GET_READ('scan',1,'ignored',n,s)",ctx)
        self.assertEqual((values['N'],values['S']),(4,0));self.assertEqual(ctx.strings.read(1),(0,'PART'));self.assertEqual(ctx.files.snapshot(),{})

    def test_file_output_preserves_ascii_bytes_without_added_newline(self):
        text='ABC\nDEF\0';ctx=context(dict(batch(),read_result=text));values,_,_=execute("V_RUN_FIND('scan',0,s) V_GET_READ('scan',0,'code.txt',n,s)",ctx)
        self.assertEqual((values['N'],values['S']),(8,0));self.assertEqual(ctx.files.snapshot()['code.txt'],text.encode('ascii'))

    def test_reader_can_run_without_vision_io_and_does_not_consume_cursor(self):
        ctx=rt.ExecutionContext(vision=rt.VisionServices(processes={'SCAN':{'views':[1],'runs':[dict(batch(found()),read_result='OK')]}}),strings=rt.StringRegisters(1))
        values,_,_=execute("V_RUN_FIND('scan',0,s) V_GET_READ('scan',1,'',n,s) V_GET_READ('scan',1,'',n,s)",ctx);self.assertEqual(values['N'],2);self.assertEqual(ctx.vision.processes['SCAN']['cursor'],0)

    def test_empty_result_is_known_and_distinct_from_absent_result(self):
        ctx=context(dict(batch(),read_result=''));values,_,_=execute("V_RUN_FIND('scan',0,s) V_GET_READ('scan',1,'',n,s)",ctx);self.assertEqual((values['S'],values['N']),(0,0));self.assertEqual(ctx.strings.read(1),(0,''))
        ctx=context(batch());values,_,_=execute("V_RUN_FIND('scan',0,s) n=99 V_GET_READ('scan',1,'',n,s)",ctx);self.assertEqual((values['S'],values['N']),(1,99))

    def test_failed_or_unknown_process_preserves_length_and_register(self):
        ctx=context(batch(status=321));ctx.strings.write(1,'keep')
        values,_,_=execute("V_RUN_FIND('scan',0,s) n=99 V_GET_READ('scan',1,'',n,s)",ctx);self.assertEqual((values['S'],values['N']),(321,99));self.assertEqual(ctx.strings.read(1),(0,'keep'))
        values,_,_=execute("n=99 V_GET_READ('absent',1,'',n,s)",ctx);self.assertEqual((values['S'],values['N']),(2,99))

    def test_invalid_string_register_preserves_length(self):
        for number in (-1,3):
            ctx=context(dict(batch(),read_result='new'));values,_,_=execute(f"V_RUN_FIND('scan',0,s) n=99 V_GET_READ('scan',{number},'',n,s)",ctx);self.assertEqual((values['S'],values['N']),(2,99));self.assertEqual(ctx.strings.snapshot(),{})

    def test_busy_file_preserves_length(self):
        ctx=context(dict(batch(),read_result='new'));ctx.files=rt.MemoryFiles({'code.txt':b'keep'});handle=rt.FileHandle();ctx.files.open(handle,'RO','code.txt')
        values,_,_=execute("V_RUN_FIND('scan',0,s) n=99 V_GET_READ('scan',0,'code.txt',n,s)",ctx);self.assertEqual((values['S'],values['N']),(3,99));self.assertEqual(ctx.files.snapshot()['code.txt'],b'keep');ctx.files.close(handle)

    def test_rooted_write_failure_keeps_length_and_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'code.txt').write_bytes(b'keep');ctx=context(dict(batch(),read_result='new'));ctx.files=rt.DirectoryFiles(root)
            with patch('karel2py.storage.atomic_bytes',side_effect=OSError('authored failure')):values,_,_=execute("V_RUN_FIND('scan',0,s) n=99 V_GET_READ('scan',0,'code.txt',n,s)",ctx)
            self.assertEqual((values['S'],values['N']),(6,99));self.assertEqual((root/'code.txt').read_bytes(),b'keep')

    def test_missing_string_or_file_backend_fails_explicitly(self):
        for number,missing in ((1,'strings'),(0,'files')):
            ctx=context(dict(batch(),read_result='new'));setattr(ctx,missing,None);execute("V_RUN_FIND('scan',0,s)",ctx)
            with self.assertRaisesRegex(rt.KarelRuntimeError,missing):execute(f"V_GET_READ('scan',{number},'code.txt',n,s)",ctx)


class ViewLineTests(unittest.TestCase):
    def test_lines_replace_path_and_feed_plane_intersection(self):
        ctx=context(dict(batch(view=1),operation='lines',image_reg=1,view_lines=lines()))
        setup="lines.grp_num=1 lines.ufrm_num=0 lines.focal_point=VEC(0,0,20) APPEND_NODE(lines,s) APPEND_NODE(lines,s) "
        body=setup+"V_FIND_VLINE('scan',1,1,lines,s) CNV_STR_CONF('N',cfg,s) plane=POS(0,0,0,0,0,0,cfg) INTSCT_VL_PL(lines,plane,points,s)"
        values,_,_=execute(body,ctx,PATH_DECL,prefix=SCHEMAS);self.assertEqual(values['S'],0);self.assertEqual(len(values['LINES']['nodes']),1);self.assertEqual(values['LINES']['data']['GRP_NUM'],2)
        self.assertEqual(values['POINTS']['nodes'][0],{'POS':{'X':0.,'Y':0.,'Z':0.},'POL':{'X':1.,'Y':0.,'Z':0.},'MODEL_ID':7})

    def test_nonpositive_image_register_uses_supplied_inline_completion(self):
        for number in (0,-1,-8):
            ctx=context(dict(batch(view=1),operation='lines',view_lines=lines()),io={});values,_,_=execute(f"V_FIND_VLINE('scan',1,{number},lines,s)",ctx,PATH_DECL,prefix=SCHEMAS)
            self.assertEqual(values['S'],0);self.assertEqual(len(values['LINES']['nodes']),1)

    def test_failed_completion_keeps_existing_path_and_consumes_reply(self):
        ctx=context(dict(batch(view=1,status=91),operation='lines'))
        values,_,_=execute("APPEND_NODE(lines,s) V_FIND_VLINE('scan',1,0,lines,s)",ctx,PATH_DECL,prefix=SCHEMAS)
        self.assertEqual(values['S'],91);self.assertEqual(len(values['LINES']['nodes']),1);self.assertEqual(ctx.vision.processes['SCAN']['runs'],[])

    def test_empty_line_result_clears_old_nodes(self):
        row=lines();row['nodes']=[];ctx=context(dict(batch(view=1),operation='lines',view_lines=row));values,_,_=execute("APPEND_NODE(lines,s) V_FIND_VLINE('scan',1,0,lines,s)",ctx,PATH_DECL,prefix=SCHEMAS)
        self.assertEqual(values['LINES']['nodes'],[]);self.assertEqual(values['LINES']['data']['UFRM_NUM'],3)

    def test_wrong_schema_and_overlapping_status_are_rejected(self):
        with self.assertRaises(TranslationError):compile_program("V_FIND_VLINE('scan',1,0,lines,s)",decl='lines:PATH s:INTEGER')
        ctx=context(dict(batch(view=1),operation='lines',view_lines=lines()));p,_=compile_program("V_FIND_VLINE('scan',1,0,lines,lines.grp_num)",decl=PATH_DECL,prefix=SCHEMAS,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(len(ctx.vision.processes['SCAN']['runs']),1);self.assertEqual(ctx.vision.sequence,0)

    def test_budget_failure_during_staging_preserves_path_and_reply(self):
        row=lines();row['nodes']*=100;ctx=context(dict(batch(view=1),operation='lines',view_lines=row));p,_=compile_program("APPEND_NODE(lines,s) V_FIND_VLINE('scan',1,0,lines,s)",decl=PATH_DECL,prefix=SCHEMAS,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=50)
        self.assertEqual(len(p.snapshot()['LINES']['nodes']),1);self.assertEqual(len(ctx.vision.processes['SCAN']['runs']),1)

    def test_reader_and_line_runs_remain_distinct(self):
        ctx=context(batch(view=1));values,_,_=execute("V_FIND_VLINE('scan',1,0,lines,s)",ctx,PATH_DECL,prefix=SCHEMAS);self.assertEqual(values['S'],2);self.assertEqual(len(ctx.vision.processes['SCAN']['runs']),1)


class LogicalDeviceTests(unittest.TestCase):
    def test_known_off_camera_and_failure_preserving_power_output(self):
        ctx=context(io={'cameras':{'OFF':{'powered':False},'FAIL':{'status':90}}})
        values,_,_=execute("V_CAM_CHECK('OFF',powered,s) n=0 IF NOT powered THEN n=1 ENDIF powered=TRUE V_CAM_CHECK('FAIL',powered,s)",ctx)
        self.assertEqual((values['N'],values['POWERED'],values['S']),(1,True,90))

    def test_unknown_camera_does_not_invent_power(self):
        values,_,_=execute("powered=TRUE V_CAM_CHECK('absent',powered,s)",context(io={}));self.assertEqual((values['S'],values['POWERED']),(2,True))

    def test_calibration_matches_and_consumes_supplied_replies(self):
        ctx=context(io={'calibrations':{'CAL':{'responses':[{'function':1,'status':0},{'function':2,'status':92}]}}})
        values,_,_=execute("V_CAM_CALIB('cal',2,s)",ctx);self.assertEqual(values['S'],2);self.assertEqual(len(ctx.vision.io.calibrations['CAL']['responses']),2)
        execute("V_CAM_CALIB('cal',1,s)",ctx);values,_,_=execute("V_CAM_CALIB('cal',2,s)",ctx)
        self.assertEqual(values['S'],92);self.assertEqual(ctx.vision.io.calibrations['CAL'],{'responses':[],'last':{'function':2,'status':92}})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'calibration reply'):execute("V_CAM_CALIB('cal',2,s)",ctx)

    def test_display_selection_is_headless_and_failures_keep_old_selection(self):
        ctx=context(io={'display_tools':{'SCAN':0,'FAIL':93}});values,_,_=execute("V_DISPLAY4D('scan',s) V_DISPLAY4D('fail',s)",ctx)
        self.assertEqual(values['S'],93);self.assertEqual(ctx.vision.io.displayed,'SCAN')

    def test_led_channel_switch_off_and_persistence(self):
        ctx=context(io={'led_channels':[1,2]});execute('V_LED_ON(1,4,s) V_LED_ON(2,16,s)',ctx)
        self.assertEqual(ctx.vision.io.led,{'channel':2,'intensity':16});restored=rt.ExecutionContext.from_config(ctx.to_config());execute('V_LED_OFF(s) V_LED_OFF(s)',restored)
        self.assertIsNone(restored.vision.io.led);self.assertEqual(ctx.vision.io.led,{'channel':2,'intensity':16})

    def test_invalid_led_values_preserve_previous_state(self):
        for channel,intensity in ((0,1),(9,1),(2,1),(1,0),(1,17)):
            ctx=context(io={'led_channels':[1],'led':{'channel':1,'intensity':4}});values,_,_=execute(f'V_LED_ON({channel},{intensity},s)',ctx)
            self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.io.led,{'channel':1,'intensity':4})

    def test_led_off_requires_configured_multiplexer(self):
        values,_,_=execute('V_LED_OFF(s)',context(io={}));self.assertEqual(values['S'],2)

    def test_missing_io_and_bad_output_fail_before_mutation(self):
        ctx=rt.ExecutionContext(vision=rt.VisionServices())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'vision io'):execute("V_CAM_CHECK('cam',powered,s)",ctx)
        with self.assertRaises(TranslationError):compile_program("V_CAM_CHECK('cam',TRUE,s)")
        with self.assertRaises(TranslationError):compile_program('FOR n=1 TO 2 DO V_LED_OFF(n) ENDFOR')


class PersistenceAndGuardTests(unittest.TestCase):
    def test_state_roundtrip_preserves_remaining_inputs_and_image_bytes(self):
        ctx=context(dict(batch(view=1),image_reg=1,read_result='CODE'),io={'image_count':2,'captures':[capture(),capture(94)],'calibrations':{'CAL':{'responses':[{'function':1,'status':0}]}}})
        execute("V_SNAP_VIEW('scan',1,1,s) V_FIND_VIEW('scan',1,1,s)",ctx);saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.vision.to_config(),ctx.vision.to_config());execute("V_GET_READ('scan',1,'',n,s)",restored)
        self.assertEqual(restored.strings.read(1),(0,'CODE'));self.assertEqual(len(restored.vision.io.captures),1);self.assertEqual(len(restored.vision.io.calibrations['CAL']['responses']),1)
        saved['vision']['io']['images']['1']['image']['pixels']='00'*12;self.assertEqual(restored.vision.io.images[1]['image']['pixels'],bytes.fromhex(pixels()['pixels']))

    def test_sequence_exhaustion_preserves_all_service_inputs(self):
        for call in ("V_SNAP_VIEW('scan',1,1,s)","V_SAVE_IMREG(1,'image.png',s)","V_CAM_CALIB('cal',1,s)",'V_LED_OFF(s)'):
            ctx=context(io={'image_count':1,'images':{'1':image_record()},'captures':[capture()],'calibrations':{'CAL':{'responses':[{'function':1,'status':0}]}},'led_channels':[1]},sequence=2147483646)
            before=ctx.vision.to_config()
            with self.subTest(call=call),self.assertRaisesRegex(rt.KarelRuntimeError,'sequence exhausted'):execute(call,ctx)
            self.assertEqual(ctx.vision.to_config(),before);self.assertEqual(ctx.files.snapshot(),{})

    def test_reader_output_aliasing_status_is_rejected(self):
        ctx=context(dict(batch(),read_result='CODE'));execute("V_RUN_FIND('scan',0,s)",ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):execute("V_GET_READ('scan',1,'',s,s)",ctx)
        self.assertEqual(ctx.strings.snapshot(),{})

    def test_linked_routine_uses_shared_io_and_root_history_owner(self):
        ctx=context(io={'cameras':{'CAM':{'powered':True}},'led_channels':[1]})
        project=translate_project({'main':source('MAIN','show_camera()',routines='ROUTINE show_camera FROM LIB'),
            'lib':source('LIB','',decl='s:INTEGER powered:BOOLEAN',routines="ROUTINE show_camera BEGIN V_CAM_CHECK('cam',powered,s) V_LED_ON(1,3,s) END show_camera")})
        project.instantiate(context=ctx).run('MAIN');self.assertEqual(ctx.vision.io.led,{'channel':1,'intensity':3});self.assertEqual({v['program'] for v in ctx.vision.history},{'MAIN'})


class ConfigurationTests(unittest.TestCase):
    def test_public_metadata_records_offline_forms_and_save_boundary(self):
        policy=translate('PROGRAM T BEGIN END T').report['vision_io_policy']
        self.assertEqual(len(policy['calls']),10);self.assertFalse(policy['controller_validated']);self.assertIn('Three-argument',policy['save_signature'])

    def test_invalid_image_dimensions_pixels_and_channels(self):
        for update in ({'width':0},{'height':4097},{'channels':True},{'channels':4},{'pixels':'FF'*12},{'pixels':'00'},{'pixels':[]},{'width':True}):
            image=dict(pixels(),**update)
            with self.subTest(update=update),self.assertRaises(ValueError):context(io={'image_count':1,'images':{'1':dict(image_record(),image=image)}})

    def test_image_capacity_keys_and_record_ownership(self):
        for io in ({'unknown':1},{'image_count':True},{'image_count':257},{'image_limit':0},{'image_count':1,'image_limit':1,'images':{'1':image_record()}},
            {'image_count':1,'images':{'01':image_record()}},{'image_count':1,'images':{'2':image_record()}},{'image_count':1,'images':{'1':dict(image_record(),process='missing')}},
            {'image_count':1,'images':{'1':dict(image_record(),views=[True])}},{'image_count':1,'captures':[capture(5,image=pixels())]},{'captures':[capture()]}):
            with self.subTest(io=io),self.assertRaises(ValueError):context(io=io)

    def test_invalid_camera_led_display_and_calibration_configuration(self):
        for io in ({'cameras':{'C':{}}},{'cameras':{'C':{'powered':1}}},{'cameras':{'C':{'status':True}}},{'cameras':{'C':{'powered':False,'other':1}}},
            {'led_channels':[1,1]},{'led_channels':[True]},{'led_channels':[1],'led':{'channel':2,'intensity':4}}, {'displayed':'absent'}, {'display_tools':{'T':True}},
            {'calibrations':{'C':{'responses':[{'function':0,'status':0}]}}},{'calibrations':{'C':{'responses':[],'last':{'function':1,'status':False}}}}):
            with self.subTest(io=io),self.assertRaises(ValueError):context(io=io)

    def test_invalid_reader_and_line_batch_data(self):
        bad=lines();bad['nodes'][0]['direction']=[0,0,0]
        for row in (dict(batch(),read_result='\u00e9'),dict(batch(status=5),read_result='CODE'),dict(batch(),read_result='X'*65536),
            dict(batch(view=1),operation='lines'),dict(batch(view=1),operation='lines',view_lines=bad),dict(batch(view=1),view_lines=lines()),
            dict(batch(view=1,status=5),operation='lines',view_lines=lines()),dict(batch(view=1),operation='lines',view_lines=lines(),read_result='CODE')):
            with self.subTest(row=row),self.assertRaises(ValueError):context(row)

    def test_unknown_io_fields_cannot_import_callbacks_or_native_links(self):
        config=context().to_config();config['vision']['io']['callback']='untrusted'
        with self.assertRaises(ValueError):rt.ExecutionContext.from_config(config)

    def test_global_empty_batch_capacity_is_bounded(self):
        with self.assertRaisesRegex(ValueError,'Combined vision'):
            rt.VisionServices(processes={'A':{'views':[1],'runs':[batch()]*2050},'B':{'views':[1],'runs':[batch()]*2050}})


if __name__=='__main__':unittest.main()
