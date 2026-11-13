"""Packed BMP words, headers and offline publication checked without imaging libraries."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt,translate_project
from karel2py.vision import encode_raster,raster
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_vision_16bit_images import supplied,capture
from tests.test_vision_io import context,execute


def image(values=(255,0,0,0,255,0,0,0,255),channels=3,width=3,bits=8,layout='RGB565'):
    pixels=bytes(values) if bits==8 else struct.pack('>'+'H'*len(values),*values)
    return dict(width=width,height=len(values)//(width*channels),channels=channels,
                pixels=pixels,sample_bits=bits,bmp_format=layout)


def packed(data):
    """Read a restricted 555/565 BMP independently from the production encoder."""
    assert data[:2]==b'BM' and int.from_bytes(data[2:6],'little')==len(data)
    assert data[6:10]==b'\0'*4
    offset=int.from_bytes(data[10:14],'little')
    assert int.from_bytes(data[14:18],'little')==40
    w,h=struct.unpack_from('<ii',data,18)
    assert w>0 and h>0 and data[26:30]==b'\x01\0\x10\0'
    compression=int.from_bytes(data[30:34],'little')
    if compression==0:
        assert offset==54;layout='RGB555'
    else:
        assert compression==3 and offset==66
        assert struct.unpack_from('<III',data,54)==(63488,2016,31);layout='RGB565'
    stride=((w*16+31)//32)*4
    assert int.from_bytes(data[34:38],'little')==stride*h
    assert data[38:54]==b'\0'*16 and len(data)==offset+stride*h
    rows=[]
    for y in range(h-1,-1,-1):
        row=data[offset+y*stride:offset+(y+1)*stride]
        assert row[w*2:]==b'\0'*(stride-w*2)
        words=[int.from_bytes(row[i:i+2],'little') for i in range(0,w*2,2)]
        if layout=='RGB555':assert all(word<32768 for word in words)
        rows.append(words)
    return layout,rows


def encoded(value,check=lambda:None,limit=1000000):return encode_raster(value,'BMP',limit,check)


class PackedBmpEncodingTests(unittest.TestCase):
    def test_primary_words_header_masks_and_padding(self):
        for layout,expected in [('RGB555',[31744,992,31]),('RGB565',[63488,2016,31])]:
            with self.subTest(layout=layout):self.assertEqual(packed(encoded(image(layout=layout))),(layout,[expected]))

    def test_black_white_and_unused_555_bit(self):
        for layout,white in [('RGB555',32767),('RGB565',65535)]:
            self.assertEqual(packed(encoded(image((0,0,0,255,255,255),width=2,layout=layout)))[1],[[0,white]])

    def test_gray_8bit_rounding_has_checked_endpoints_and_midrange(self):
        for layout,words in [('RGB555',[0,0,15855,16912,32767,32767]),
                             ('RGB565',[0,0,31727,33808,65535,65535])]:
            self.assertEqual(packed(encoded(image((0,1,127,128,254,255),channels=1,width=6,layout=layout)))[1],[words])

    def test_big_endian_samples_quantize_directly_without_8bit_roundtrip(self):
        self.assertEqual(packed(encoded(image((1058,521,1058),width=1,bits=16)))[1],[[2081]])
        direct=encoded(image((1058,521,1058),width=1,bits=16))
        rounded=encoded(image((4,2,4),width=1))
        self.assertNotEqual(direct,rounded)

    def test_exact_fraction_oracle_covers_channels_and_both_sample_depths(self):
        for bits in (8,16):
            maximum=2**bits-1
            values=[0,maximum,maximum//2,1,maximum-1,maximum//3,maximum//5,maximum//7,maximum//11]
            for layout,green_bits in [('RGB555',5),('RGB565',6)]:
                expected=[]
                for start in range(0,len(values),3):
                    r,g,b=values[start:start+3]
                    r=round(Fraction(r*31,maximum));g=round(Fraction(g*(2**green_bits-1),maximum));b=round(Fraction(b*31,maximum))
                    expected.append(r*2**(green_bits+5)+g*32+b)
                self.assertEqual(packed(encoded(image(values,bits=bits,layout=layout)))[1],[expected])

    def test_all_unsigned_16bit_gray_samples_are_monotonic_with_bounded_error(self):
        values=list(range(65536))
        for layout,green_bits in [('RGB555',5),('RGB565',6)]:
            rows=packed(encoded(image(values,channels=1,width=256,bits=16,layout=layout)))[1]
            words=[word for row in rows for word in row]
            self.assertEqual((words[0],words[-1]),(0,32767 if layout=='RGB555' else 65535))
            self.assertEqual(words,sorted(words))
            for shift,mask in [(0,31),(5,2**green_bits-1),(green_bits+5,31)]:
                self.assertTrue(all(abs(n*mask-((word>>shift)&mask)*65535)<=32767 for n,word in enumerate(words)))

    def test_bottom_up_rows_and_odd_even_padding_widths(self):
        for width in (1,2,3,4,7):
            values=tuple(v for gray in range(width*3) for v in (gray*8,gray*8,gray*8))
            data=encoded(image(values,width=width))
            self.assertEqual(len(packed(data)[1]),3)
            offset=int.from_bytes(data[10:14],'little')
            self.assertEqual(int.from_bytes(data[offset:offset+2],'little'),packed(data)[1][-1][0])

    def test_eight_and_sixteen_bit_equivalent_samples_share_wire_bytes(self):
        values=(0,1,127,128,254,255,2,90,200)
        for layout in ('RGB555','RGB565'):
            self.assertEqual(encoded(image(values,layout=layout)),encoded(image(tuple(v*257 for v in values),bits=16,layout=layout)))

    def test_png_bytes_and_original_pixels_ignore_valid_bmp_preference(self):
        value=image(bits=16,values=(0,65535,32768,1,256,500,1000,2000,3000));before=deepcopy(value)
        plain=dict(value);plain.pop('bmp_format')
        self.assertEqual(encode_raster(value,'PNG',1000,lambda:None),encode_raster(plain,'PNG',1000,lambda:None))
        encoded(value);self.assertEqual(value,before)

    def test_unspecified_bmp_preference_keeps_default_24bit_encoding(self):
        value=image();value.pop('bmp_format')
        data=encoded(value)
        self.assertEqual((int.from_bytes(data[28:30],'little'),int.from_bytes(data[10:14],'little')),(24,54))

    def test_exact_output_size_is_checked_before_row_processing(self):
        for layout in ('RGB555','RGB565'):
            value=image(layout=layout);data=encoded(value)
            self.assertIsNone(encoded(value,lambda:self.fail('Oversize image reached a row'),len(data)-1))
            self.assertEqual(encoded(value,limit=len(data)),data)

    def test_each_row_checkpoint_precedes_processing_and_cancellation(self):
        value=image(tuple(range(27)),width=3);before=deepcopy(value);seen=[]
        def check():
            seen.append(1)
            if len(seen)==2:raise RuntimeError('authored cancellation')
        with self.assertRaisesRegex(RuntimeError,'authored cancellation'):encoded(value,check)
        self.assertEqual((len(seen),value),(2,before))

    def test_row_callback_cannot_retarget_captured_pixels_or_layout(self):
        value=image();expected=encoded(value)
        def check():
            value['pixels']=b'\0'*9;value['bmp_format']='RGB555'
        self.assertEqual(encoded(value,check),expected)
        self.assertEqual(value['bmp_format'],'RGB555')

    def test_no_imaging_or_numeric_dependency_is_used(self):
        with patch.dict('sys.modules',{'PIL':None,'numpy':None}):self.assertEqual(packed(encoded(image()))[1][0][0],63488)


class PackedBmpInputTests(unittest.TestCase):
    def test_mode_and_source_samples_survive_json_replay(self):
        value=image(bits=16,values=(0,65535,32768,1,256,500,1000,2000,3000));ctx=supplied(value)
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.to_config(),saved)
        self.assertEqual(restored.vision.io.images[1]['image'],value)

    def test_capture_retains_packing_choice_and_detached_pixels(self):
        value=image();response=capture(value);ctx=context(io={'image_count':1,'captures':[response]})
        response['image']['bmp_format']='RGB555'
        state,_,_=execute("V_SNAP_VIEW('SCAN',1,1,s) V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        self.assertEqual((state['S'],packed(ctx.files.snapshot()['out.bmp'])[0]),(0,'RGB565'))
        self.assertFalse(ctx.vision.io.captures)

    def test_invalid_modes_and_alpha_or_palette_input_reject(self):
        bad=[dict(image(),bmp_format=value) for value in (None,True,16,'rgb565','RGB555 ','ARGB1555','')]
        bad+=[dict(image((0,0),channels=2,width=1)),dict(image((0,0,0,0),channels=4,width=1)),
              dict(image((0,),channels=1,width=1),palette=b'\0\0\0\xff')]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):raster(value,1000)

    def test_invalid_packing_rejects_before_pixel_hex_decode(self):
        value=dict(image(),bmp_format='bad',pixels='zz')
        with self.assertRaisesRegex(ValueError,'bmp_format'):raster(value,1000)

    def test_original_raw_quota_applies_before_export_size(self):
        value=image(bits=16,values=(0,65535,32768,1,256,500,1000,2000,3000))
        with self.assertRaisesRegex(ValueError,'Raw image'):raster(value,17)
        with self.assertRaisesRegex(ValueError,'Combined'):raster(value,1000,remaining=17)

    def test_bad_mutated_register_does_not_change_status_history_or_output(self):
        ctx=supplied(image());ctx.files=rt.MemoryFiles({'out.bmp':b'keep'})
        ctx.vision.io.images[1]['image']['bmp_format']='bad'
        p,_=compile_program("s=77 V_SAVE_IMREG(1,'out.bmp',s)",context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['S'],ctx.vision.sequence,ctx.files.snapshot()['out.bmp']),(77,0,b'keep'))


class PackedBmpServiceTests(unittest.TestCase):
    def test_save_replaces_whole_file_on_success_and_preserves_source(self):
        value=image();ctx=supplied(value);ctx.files=rt.MemoryFiles({'out.bmp':b'keep'})
        before=ctx.vision.io.to_config();state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        self.assertEqual(state['S'],0);self.assertEqual(packed(ctx.files.snapshot()['out.bmp'])[0],'RGB565')
        self.assertEqual(ctx.vision.io.to_config(),before)

    def test_bmp_then_png_keep_original_16bit_register_samples(self):
        value=image((1058,521,1058),width=1,bits=16);ctx=supplied(value)
        state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s) V_SAVE_IMREG(1,'out.png',s)",ctx)
        self.assertEqual(state['S'],0)
        self.assertEqual(ctx.files.snapshot()['out.png'],encode_raster(value,'PNG',1000,lambda:None))
        self.assertEqual(ctx.vision.io.images[1]['image'],value)

    def test_saved_context_reexports_identical_packed_bytes(self):
        ctx=supplied(image());execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        state,_,_=execute("V_SAVE_IMREG(1,'again.bmp',s)",restored)
        self.assertEqual((state['S'],restored.files.snapshot()['again.bmp']),(0,ctx.files.snapshot()['out.bmp']))

    def test_linked_routine_uses_the_supplied_packing_policy(self):
        ctx=supplied(image());project=translate_project({
            'main':source('MAIN','saveit',routines='ROUTINE saveit FROM LIB'),
            'lib':source('LIB','',decl='s:INTEGER',routines="ROUTINE saveit BEGIN V_SAVE_IMREG(1,'out.bmp',s) END saveit")}).instantiate(context=ctx)
        project.run('MAIN');self.assertEqual(packed(ctx.files.snapshot()['out.bmp'])[0],'RGB565')

    def test_output_limit_and_busy_targets_preserve_previous_bytes(self):
        ctx=supplied(image());ctx.files=rt.MemoryFiles({'out.bmp':b'keep'},limit=73)
        state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        self.assertEqual((state['S'],ctx.files.snapshot()['out.bmp']),(5,b'keep'))
        ctx.files=rt.MemoryFiles({'out.bmp':b'keep'});handle=rt.FileHandle();ctx.files.open(handle,'R','out.bmp');handle.position=2
        try:
            state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
            self.assertEqual((state['S'],handle.position,ctx.files.snapshot()['out.bmp']),(3,2,b'keep'))
        finally:ctx.files.close(handle)

    def test_readonly_virtual_volume_preserves_previous_bytes(self):
        ctx=supplied(image());ctx.files=rt.DeviceFiles({'RD:':{'capacity':1000,'read_only':True}},{'RD:out.bmp':b'keep'})
        state,_,_=execute("V_SAVE_IMREG(1,'RD:out.bmp',s)",ctx)
        self.assertEqual((state['S'],ctx.files.snapshot()['RD:out.bmp']),(6,b'keep'))

    def test_virtual_flash_capacity_counts_obsolete_bytes(self):
        for capacity,status in ((77,6),(78,0)):
            ctx=supplied(image());ctx.files=rt.DeviceFiles({'FR:':{'capacity':capacity}},{'FR:out.bmp':b'keep'})
            state,_,_=execute("V_SAVE_IMREG(1,'FR:out.bmp',s)",ctx)
            self.assertEqual(state['S'],status)
            self.assertEqual(ctx.files._volumes['FR']['garbage'],4 if status==0 else 0)

    def test_rooted_filesystem_writes_readable_packed_bmp(self):
        with tempfile.TemporaryDirectory() as folder:
            ctx=supplied(image(layout='RGB555'));ctx.files=rt.DirectoryFiles(folder)
            state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
            self.assertEqual((state['S'],packed((Path(folder)/'out.bmp').read_bytes())[0]),(0,'RGB555'))

    def test_atomic_rooted_failure_preserves_original_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'out.bmp';path.write_bytes(b'keep');ctx=supplied(image());ctx.files=rt.DirectoryFiles(folder)
            with patch('karel2py.storage.atomic_bytes',side_effect=OSError('authored failure')):
                state,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
            self.assertEqual((state['S'],path.read_bytes()),(6,b'keep'))

    def test_budget_failure_retains_status_source_and_previous_output(self):
        value=image(tuple([0,255,128]*128),width=1);ctx=supplied(value);ctx.files=rt.MemoryFiles({'out.bmp':b'keep'})
        before=ctx.vision.to_config();p,_=compile_program("s=77 V_SAVE_IMREG(1,'out.bmp',s)",context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=30)
        self.assertEqual((p.snapshot()['S'],ctx.files.snapshot()['out.bmp']),(77,b'keep'))
        self.assertEqual(ctx.vision.to_config(),before)

    def test_unknown_suffix_and_absent_files_keep_existing_errors(self):
        ctx=supplied(image());state,_,_=execute("V_SAVE_IMREG(1,'out.tiff',s)",ctx)
        self.assertEqual((state['S'],ctx.files.snapshot()),(2,{}))
        ctx.files=None
        with self.assertRaises(rt.KarelRuntimeError):execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)

    def test_report_exposes_packing_and_source_preservation_boundaries(self):
        _,result=compile_program("V_SAVE_IMREG(1,'out.bmp',s)")
        policy=result.report['vision_packed_bmp_policy']
        self.assertFalse(policy['controller_validated'])
        self.assertEqual(policy['guide'],'docs/vision-packed-bmp.md')
        self.assertIn('RGB555',policy['formats']);self.assertIn('RGB565',policy['formats'])
        self.assertIn('PNG',policy['lifetime'])


if __name__=='__main__':unittest.main()
