"""Explicit 16-bit sample rasters checked with independent PNG decoding."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from karel2py import runtime as rt
from karel2py.vision import encode_raster,raster
from tests.test_extended_services import compile_program
from tests.test_vision_io import context,execute
from tests.test_vision_results import batch
from tests.test_vision_alpha_images import crc32


PATTERN=(0x0102,0xabcd,0xffff,0,0x8000,1,0x1234,0x00ff)
def image(channels=1,width=2,height=2):
    values=[PATTERN[i%len(PATTERN)] for i in range(width*height*channels)]
    return dict(width=width,height=height,channels=channels,sample_bits=16,pixels=struct.pack('>'+'H'*len(values),*values))
def record(value):return dict(process='SCAN',views=[1],image=value)
def capture(value):return dict(record(value),status=0)
def supplied(value=None,**options):return context(io=dict(image_count=1,images={'1':record(image() if value is None else value)},**options))


def decoded(data):
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise AssertionError('Invalid PNG signature')
    at=8;chunks=[]
    while at<len(data):
        count=int.from_bytes(data[at:at+4],'big');kind=data[at+4:at+8];payload=data[at+8:at+8+count]
        if len(payload)!=count or int.from_bytes(data[at+8+count:at+12+count],'big')!=crc32(kind+payload):raise AssertionError('Invalid chunk length/CRC')
        chunks.append((kind,payload));at+=count+12
    if at!=len(data) or chunks[-1]!=(b'IEND',b''):raise AssertionError('Invalid PNG termination')
    width,height,bits,color,compression,filter_method,interlace=struct.unpack('>IIBBBBB',chunks[0][1])
    if bits!=16 or (compression,filter_method,interlace)!=(0,0,0):raise AssertionError('Unexpected PNG format')
    channels={0:1,4:2,2:3,6:4}[color];raw=zlib.decompress(b''.join(value for kind,value in chunks if kind==b'IDAT'))
    stride=width*channels*2
    if len(raw)!=height*(stride+1):raise AssertionError('Invalid scanline lengths')
    rows=[]
    for row in range(height):
        start=row*(stride+1)
        if raw[start]!=0:raise AssertionError('Unexpected scanline filter')
        rows.append(list(struct.unpack('>'+'H'*(width*channels),raw[start+1:start+stride+1])))
    return width,height,color,rows,[kind for kind,_ in chunks]


class SixteenBitImageTests(unittest.TestCase):
    def test_png_decodes_all_channels_without_scaling_or_endian_swap(self):
        for channels in (1,2,3,4):
            value=image(channels);data=encode_raster(value,'PNG',10000,lambda:None)
            width,height,color,rows,chunks=decoded(data)
            expected=[PATTERN[i%len(PATTERN)] for i in range(4*channels)]
            with self.subTest(channels=channels):
                self.assertEqual((width,height,color),(2,2,{1:0,2:4,3:2,4:6}[channels]))
                self.assertEqual(sum(rows,[]),expected);self.assertEqual(chunks,[b'IHDR',b'IDAT',b'IEND'])

    def test_multiple_widths_have_correct_two_byte_channel_strides(self):
        for channels in (1,2,3,4):
            for width in (1,3,7):
                value=image(channels,width,3);rows=decoded(encode_raster(value,'PNG',10000,lambda:None))[3]
                with self.subTest(channels=channels,width=width):self.assertEqual(len(rows),3);self.assertTrue(all(len(row)==width*channels for row in rows))

    def test_alpha_and_hidden_color_samples_survive_verbatim(self):
        value=dict(width=1,height=1,channels=4,sample_bits=16,pixels=bytes.fromhex('1234abcdffff0000'))
        self.assertEqual(decoded(encode_raster(value,'PNG',1000,lambda:None))[3],[[0x1234,0xabcd,0xffff,0]])

    def test_python_bytes_and_json_hex_have_same_immutable_raster(self):
        value=image(4);self.assertEqual(raster(value,100),value)
        self.assertEqual(raster(dict(value,pixels=value['pixels'].hex()),100),value)

    def test_sample_bits_is_explicit_and_only_accepts_8_or_16(self):
        for bits in (True,False,0,1,4,12,32,16.,'16',None):
            with self.subTest(bits=bits),self.assertRaises(ValueError):raster(dict(image(),sample_bits=bits),100)
        value=image(width=1,height=1);del value['sample_bits']
        with self.assertRaises(ValueError):raster(value,100)

    def test_absent_and_explicit_8_bit_metadata_keep_legacy_bytes(self):
        old=dict(width=2,height=1,channels=3,pixels=bytes.fromhex('123456abcdef'))
        new=dict(old,sample_bits=8)
        for kind in ('PNG','BMP'):
            with self.subTest(kind=kind):self.assertEqual(encode_raster(old,kind,1000,lambda:None),encode_raster(new,kind,1000,lambda:None))
        self.assertNotIn('sample_bits',raster(old,100));self.assertEqual(raster(new,100)['sample_bits'],8)

    def test_palette_indices_remain_8_bit(self):
        with self.assertRaisesRegex(ValueError,'8-bit'):raster(dict(image(),palette=b'\0\0\0\xff'),100)

    def test_raw_byte_quota_runs_before_hex_validation_or_allocation(self):
        value=dict(width=3,height=2,channels=1,sample_bits=16,pixels='not hex')
        with self.assertRaisesRegex(ValueError,'byte limit'):raster(value,11)
        with self.assertRaisesRegex(ValueError,'Combined'):raster(value,100,remaining=11)

    def test_raw_exact_limit_counts_both_bytes_per_sample(self):
        value=image();self.assertEqual(raster(value,8),value)
        with self.assertRaises(ValueError):raster(value,7)

    def test_malformed_pixels_uppercase_hex_and_mutable_buffers_are_rejected(self):
        value=image()
        for pixels in (value['pixels'][:-1],bytearray(value['pixels']),value['pixels'].hex().upper(),[],None):
            with self.subTest(pixels=pixels),self.assertRaises(ValueError):raster(dict(value,pixels=pixels),100)

    def test_combined_images_and_captures_charge_actual_16bit_bytes(self):
        small=image(2,1,1)
        with patch('karel2py.vision._IMAGE_TOTAL_LIMIT',8):
            ctx=supplied(small,captures=[capture(small)]);self.assertEqual(len(ctx.vision.io.captures),1)
            with self.assertRaisesRegex(ValueError,'Combined'):supplied(small,captures=[capture(small),capture(dict(small,pixels='invalid'))])

    def test_capture_detaches_and_retains_sample_bits_and_bytes(self):
        value=image(2);request=capture(value);ctx=context(io={'image_count':1,'captures':[request]})
        request['image']['pixels']=b'bad';request['image']['sample_bits']=8
        state,_,_=execute("V_SNAP_VIEW('SCAN',1,1,s)",ctx)
        self.assertEqual(state['S'],0);self.assertEqual(ctx.vision.io.images[1]['image'],image(2));self.assertFalse(ctx.vision.io.captures)

    def test_find_view_retains_16bit_register_without_reprocessing_pixels(self):
        value=image(3);ctx=context(batch(view=1,image_reg=1),io={'image_count':1,'images':{'1':record(value)}})
        state,_,_=execute("V_FIND_VIEW('SCAN',1,1,s)",ctx);self.assertEqual(state['S'],0);self.assertEqual(ctx.vision.io.images[1]['image'],value)

    def test_json_roundtrip_preserves_optional_depth_and_network_bytes(self):
        ctx=supplied(image(4));saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved);self.assertEqual(restored.vision.io.images[1]['image'],image(4))

    def test_save_png_decodes_supplied_samples_and_keeps_register(self):
        ctx=supplied(image(2));before=deepcopy(ctx.vision.io.to_config());state,_,_=execute("V_SAVE_IMREG(1,'out.png',s)",ctx)
        self.assertEqual(state['S'],0);self.assertEqual(decoded(ctx.files.snapshot()['out.png'])[3],[[0x0102,0xabcd,0xffff,0],[0x8000,1,0x1234,0xff]])
        self.assertEqual(ctx.vision.io.to_config(),before)

    def test_16bit_bmp_replaces_existing_file_without_changing_supplied_samples(self):
        ctx=supplied();ctx.files.files['out.bmp']=bytearray(b'keep');before=deepcopy(ctx.vision.io.to_config())
        state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        self.assertEqual(state['S'],0);self.assertTrue(ctx.files.snapshot()['out.bmp'].startswith(b'BM'))
        self.assertEqual(ctx.vision.io.to_config(),before)
        self.assertEqual(ctx.files.snapshot()['out.bmp'],encode_raster(image(),'BMP',1000,lambda:None))

    def test_bmp_export_rejects_mutated_malformed_raster(self):
        ctx=supplied();ctx.vision.io.images[1]['image']['pixels']=b'bad'
        p,_=compile_program("s=77 V_SAVE_IMREG(1,'out.bmp',s)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Invalid supplied image'):p.run()
        self.assertEqual(p.snapshot()['S'],77);self.assertFalse(ctx.files.files)

    def test_small_output_limit_preserves_previous_file(self):
        ctx=supplied();ctx.files=rt.MemoryFiles({'out.png':b'x'},limit=1)
        state,_,_=execute("V_SAVE_IMREG(1,'out.png',s)",ctx)
        self.assertEqual((state['S'],ctx.files.snapshot()['out.png']),(5,b'x'))

    def test_busy_file_rejection_preserves_payload_and_raster(self):
        ctx=supplied();ctx.files.files['out.png']=bytearray(b'keep')
        state,_,_=execute("OPEN FILE f('RO','out.png') V_SAVE_IMREG(1,'out.png',s) CLOSE FILE f",ctx,decl='f:FILE s:INTEGER')
        self.assertEqual((state['S'],ctx.files.snapshot()['out.png']),(3,b'keep'))

    def test_budget_exhaustion_during_rows_cannot_publish_output(self):
        ctx=supplied(image(1,2,20));ctx.files.files['out.png']=bytearray(b'keep')
        p,_=compile_program("s=77 V_SAVE_IMREG(1,'out.png',s)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=5)
        self.assertEqual((p.snapshot()['S'],ctx.files.snapshot()['out.png']),(77,b'keep'))

    def test_rooted_directory_export_keeps_exact_png_samples(self):
        with tempfile.TemporaryDirectory() as folder:
            ctx=supplied(image(4));ctx.files=rt.DirectoryFiles(folder)
            state,_,_=execute("V_SAVE_IMREG(1,'out.png',s)",ctx)
            self.assertEqual(state['S'],0);self.assertEqual(decoded((Path(folder)/'out.png').read_bytes())[0:3],(2,2,6))

    def test_virtual_volume_capacity_preflight_keeps_old_image_output(self):
        ctx=supplied();ctx.files=rt.DeviceFiles({'RD:':{'capacity':1}}, {'RD:out.png':b'x'})
        state,_,_=execute("V_SAVE_IMREG(1,'RD:out.png',s)",ctx)
        self.assertNotEqual(state['S'],0);self.assertEqual(ctx.files.snapshot()['RD:out.png'],b'x')

    def test_snapshot_and_saved_replay_keep_consumed_capture_lifetime(self):
        ctx=context(io={'image_count':1,'captures':[capture(image(2))]})
        execute("V_SNAP_VIEW('SCAN',1,1,s) V_SAVE_IMREG(1,'first.png',s)",ctx)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        state,_,_=execute("V_SAVE_IMREG(1,'second.png',s)",restored)
        self.assertEqual(state['S'],0);self.assertEqual(restored.files.snapshot()['second.png'],ctx.files.snapshot()['first.png']);self.assertFalse(restored.vision.io.captures)

    def test_report_explains_explicit_samples_and_8bit_palette_boundary(self):
        _,result=compile_program("V_SAVE_IMREG(1,'out.png',s)")
        policy=result.report['vision_sample_depth_policy'];self.assertIn('big-endian',policy['input']);self.assertIn('8-bit',policy['boundary'])


if __name__=='__main__':unittest.main()
