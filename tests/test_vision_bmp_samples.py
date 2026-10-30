"""Lossy BMP exports of exact supplied 16-bit samples; no imaging dependency."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from karel2py import runtime as rt
from karel2py.vision import encode_raster
from tests.test_extended_services import compile_program
from tests.test_vision_16bit_images import image,supplied,capture,decoded
from tests.test_vision_io import context,execute
from tests.test_vision_alpha_images import bmp_pixels


def samples(values,channels=1,width=None):
    width=width or len(values)//channels
    return dict(width=width,height=len(values)//(width*channels),channels=channels,sample_bits=16,pixels=struct.pack('>'+'H'*len(values),*values))


def read_bmp(data):
    if data[:2]!=b'BM' or int.from_bytes(data[2:6],'little')!=len(data):raise AssertionError('Invalid BMP file header')
    offset=int.from_bytes(data[10:14],'little');w,h=struct.unpack_from('<ii',data,18);depth=struct.unpack_from('<H',data,28)[0]
    if depth==32:return bmp_pixels(data)
    if depth!=24 or offset!=54:raise AssertionError('Unexpected BMP layout')
    stride=(w*3+3)//4*4;rows=[]
    for y in range(h-1,-1,-1):
        row=data[offset+y*stride:offset+(y+1)*stride]
        if len(row)!=stride or any(row[w*3:]):raise AssertionError('Invalid BMP row/padding')
        rows.append([tuple(reversed(row[x*3:x*3+3]))+(255,) for x in range(w)])
    return rows


def exported(value):
    ctx=supplied(value);state,p,r=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
    assert state['S']==0
    return ctx.files.snapshot()['out.bmp'],ctx,p,r


class BmpSampleEncodingTests(unittest.TestCase):
    def test_known_rounding_boundaries_and_endpoints(self):
        value=samples([0,1,128,129,256,257,385,386,32767,32768,65406,65407,65535])
        expected=[0,0,0,1,1,1,1,2,127,128,254,255,255]
        self.assertEqual([pixel[0] for pixel in read_bmp(exported(value)[0])[0]],expected)

    def test_all_unsigned_samples_monotone_and_within_half_a_step(self):
        value=samples(list(range(65536)),width=256);rows=read_bmp(exported(value)[0]);result=[p[0] for row in rows for p in row]
        self.assertEqual((result[0],result[-1]),(0,255));self.assertEqual(result,sorted(result))
        self.assertTrue(all(abs(n-v*257)<=128 for n,v in enumerate(result)))

    def test_rgb_channels_and_big_endian_samples_decode_in_order(self):
        value=samples([0x0102,0xabcd,0xffff,0,0x8000,0x1234],3)
        self.assertEqual(read_bmp(exported(value)[0]),[[(1,171,255,255),(0,128,18,255)]])

    def test_grayscale_alpha_rounds_both_channels(self):
        self.assertEqual(read_bmp(exported(samples([0x0123,65535,0xfedc,0],2))[0]),[[(1,1,1,255),(254,254,254,0)]])

    def test_rgba_preserves_hidden_colors_without_premultiplication(self):
        self.assertEqual(read_bmp(exported(samples([0x1234,0xabcd,65535,0],4))[0]),[[(18,171,255,0)]])

    def test_all_channel_counts_and_padding_widths(self):
        for channels in (1,2,3,4):
            for width in (1,2,3,7):
                value=image(channels,width,3);rows=read_bmp(exported(value)[0])
                with self.subTest(channels=channels,width=width):self.assertEqual((len(rows),len(rows[0])),(3,width))

    def test_bottom_up_storage_retains_logical_top_down_rows(self):
        value=samples([0,65535,257,514],width=2)
        self.assertEqual(read_bmp(exported(value)[0]),[[(0,0,0,255),(255,255,255,255)],[(1,1,1,255),(2,2,2,255)]])

    def test_alpha_header_uses_32_bit_v4_and_explicit_masks(self):
        data=exported(image(4))[0];self.assertEqual(struct.unpack_from('<I',data,14)[0],108)
        self.assertEqual(struct.unpack_from('<HHI',data,26),(1,32,3));self.assertEqual(struct.unpack_from('<IIII',data,54),(0xff0000,0xff00,0xff,0xff000000))

    def test_nonalpha_header_uses_24_bit_rgb(self):
        for c in (1,3):
            data=exported(image(c))[0];self.assertEqual(struct.unpack_from('<I',data,14)[0],40);self.assertEqual(struct.unpack_from('<HHI',data,26),(1,24,0))

    def test_exact_output_limit_precedes_any_row_work(self):
        for c in (1,2,3,4):
            value=image(c);data=encode_raster(value,'BMP',1000,lambda:None)
            self.assertIsNone(encode_raster(value,'BMP',len(data)-1,lambda:self.fail('No row should run')))
            self.assertEqual(encode_raster(value,'BMP',len(data),lambda:None),data)

    def test_raw_schema_checks_precede_output_size_return(self):
        for bad in (dict(image(),pixels=b'bad'),dict(image(),sample_bits=12),dict(image(),palette=b'\0\0\0\xff')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):encode_raster(bad,'BMP',0,lambda:self.fail('Invalid image reached rows'))

    def test_row_checkpoints_are_bounded_and_cancellable(self):
        value=image(4,2,3);before=deepcopy(value);checks=[]
        def check():
            checks.append(1)
            if len(checks)==2:raise RuntimeError('authored cancellation')
        with self.assertRaisesRegex(RuntimeError,'authored cancellation'):encode_raster(value,'BMP',1000,check)
        self.assertEqual((len(checks),value),(2,before))

    def test_source_and_context_keep_exact_16_bit_samples(self):
        value=image(4);before=deepcopy(value);_,ctx,_,_=exported(value)
        self.assertEqual(value,before);self.assertEqual(ctx.vision.io.images[1]['image'],before)

    def test_png_after_bmp_retains_full_samples(self):
        value=image(4);_,ctx,_,_=exported(value);execute("V_SAVE_IMREG(1,'out.png',s)",ctx)
        self.assertEqual(decoded(ctx.files.snapshot()['out.png'])[3],decoded(encode_raster(value,'PNG',1000,lambda:None))[3])

    def test_explicit_json_hex_input_has_same_export(self):
        value=image(3);self.assertEqual(exported(value)[0],exported(dict(value,pixels=value['pixels'].hex()))[0])


class BmpSampleServiceTests(unittest.TestCase):
    def test_existing_file_is_replaced_only_on_success(self):
        ctx=supplied(image());ctx.files=rt.MemoryFiles({'out.bmp':b'keep'})
        state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx);self.assertEqual(state['S'],0);self.assertTrue(ctx.files.snapshot()['out.bmp'].startswith(b'BM'))

    def test_output_limit_failure_keeps_bytes_and_samples(self):
        ctx=supplied(image(4));ctx.files=rt.MemoryFiles({'out.bmp':b'keep'},limit=64);before=deepcopy(ctx.vision.io.to_config())
        state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx);self.assertEqual((state['S'],ctx.files.snapshot()['out.bmp']),(5,b'keep'));self.assertEqual(ctx.vision.io.to_config(),before)

    def test_busy_file_keeps_cursor_and_bytes(self):
        ctx=supplied(image(2));ctx.files=rt.MemoryFiles({'out.bmp':b'keep'});handle=rt.FileHandle();ctx.files.open(handle,'R','out.bmp');handle.position=2
        state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx);self.assertEqual((state['S'],handle.position,ctx.files.snapshot()['out.bmp']),(3,2,b'keep'));ctx.files.close(handle)

    def test_readonly_volume_retains_old_file(self):
        ctx=supplied(image());ctx.files=rt.DeviceFiles({'RD:':{'capacity':1000,'read_only':True}},{'RD:out.bmp':b'keep'})
        state,_,_=execute("V_SAVE_IMREG(1,'RD:out.bmp',s)",ctx);self.assertEqual((state['S'],ctx.files.snapshot()['RD:out.bmp']),(6,b'keep'))

    def test_virtual_capacity_includes_obsolete_flash_bytes(self):
        for capacity,status in ((141,6),(142,0)):
            ctx=supplied(image(2));ctx.files=rt.DeviceFiles({'FR:':{'capacity':capacity}},{'FR:out.bmp':b'keep'})
            state,_,_=execute("V_SAVE_IMREG(1,'FR:out.bmp',s)",ctx);self.assertEqual(state['S'],status)
            self.assertEqual(ctx.files._volumes['FR']['garbage'],0 if status else 4)

    def test_rooted_directory_produces_readable_bmp(self):
        with tempfile.TemporaryDirectory() as folder:
            ctx=supplied(image(4));ctx.files=rt.DirectoryFiles(folder);state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
            self.assertEqual(state['S'],0);self.assertEqual(read_bmp((Path(folder)/'out.bmp').read_bytes()),read_bmp(exported(image(4))[0]))

    def test_atomic_directory_failure_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'out.bmp';path.write_bytes(b'keep');ctx=supplied(image(2));ctx.files=rt.DirectoryFiles(folder)
            with patch('karel2py.storage.atomic_bytes',side_effect=OSError('authored failure')):state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
            self.assertEqual((state['S'],path.read_bytes()),(6,b'keep'))

    def test_budget_stop_retains_status_and_previous_output(self):
        for channels in (1,2,3,4):
            ctx=supplied(image(channels,2,128));ctx.files=rt.MemoryFiles({'out.bmp':b'keep'});before=ctx.vision.to_config()
            p,_=compile_program("s=77 V_SAVE_IMREG(1,'out.bmp',s)",context=ctx)
            with self.subTest(channels=channels),self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=30)
            self.assertEqual((p.snapshot()['S'],ctx.files.snapshot()['out.bmp']),(77,b'keep'));self.assertEqual(ctx.vision.to_config(),before)

    def test_malformed_mutation_fails_before_status_or_history(self):
        ctx=supplied(image());ctx.vision.io.images[1]['image']['pixels']=b'bad';ctx.files=rt.MemoryFiles({'out.bmp':b'keep'})
        p,_=compile_program("s=77 V_SAVE_IMREG(1,'out.bmp',s)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['S'],ctx.vision.sequence,ctx.files.snapshot()['out.bmp']),(77,0,b'keep'))

    def test_missing_files_service_fails_explicitly(self):
        ctx=supplied(image());ctx.files=None
        with self.assertRaises(rt.KarelRuntimeError):execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        self.assertEqual(ctx.vision.sequence,0)

    def test_bad_suffix_still_returns_unsupported_status(self):
        ctx=supplied(image());state,_,_=execute("V_SAVE_IMREG(1,'out.tiff',s)",ctx);self.assertEqual(state['S'],2);self.assertFalse(ctx.files.files)

    def test_capture_and_saved_replay_keep_16_bit_source(self):
        ctx=context(io={'image_count':1,'captures':[capture(image(2))]});execute("V_SNAP_VIEW('SCAN',1,1,s) V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved);state,_,_=execute("V_SAVE_IMREG(1,'copy.bmp',s)",restored)
        self.assertEqual(state['S'],0);self.assertEqual(restored.files.snapshot()['copy.bmp'],ctx.files.snapshot()['out.bmp']);self.assertEqual(restored.vision.io.images[1]['image']['sample_bits'],16)

    def test_existing_8_bit_samples_produce_same_wire_bytes(self):
        for c in (1,2,3,4):
            value=image(c);reduced=bytes((n*256+lo+128)//257 for n,lo in zip(value['pixels'][::2],value['pixels'][1::2]));old=dict(value,pixels=reduced);del old['sample_bits']
            self.assertEqual(exported(value)[0],exported(old)[0])

    def test_report_explains_lossy_policy_and_source_preservation(self):
        _,r=compile_program("V_SAVE_IMREG(1,'out.bmp',s)");p=r.report['vision_bmp_sample_policy']
        self.assertIn('(sample+128)//257',p['rounding']);self.assertIn('PNG',p['lifetime']);self.assertFalse(p['controller_validated'])

    def test_no_extra_processing_or_dependencies_are_required(self):
        with patch.dict('sys.modules',{'PIL':None,'numpy':None}):self.assertEqual(read_bmp(exported(samples([65535]))[0]),[[(255,255,255,255)]])


if __name__=='__main__':unittest.main()
