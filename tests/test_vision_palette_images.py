"""Explicit indexed vision rasters, palette bounds and independent export checks."""
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
from tests.test_vision_results import batch,found
from tests.test_vision_alpha_images import png,bmp_pixels


COLORS=bytes.fromhex('ff20400080603080010203ff')
OPAQUE=bytes.fromhex('ff2040ff806030ff010203ff')


def image(width=2,height=2,pixels=b'\0\1\2\0',palette=COLORS):
    return dict(width=width,height=height,channels=1,pixels=pixels,palette=palette)


def record(value):return dict(process='SCAN',views=[1],image=value)
def capture(value):return dict(record(value),status=0)


def supplied(value=None,*runs,**options):
    return context(*runs,io=dict(image_count=1,images={'1':record(image() if value is None else value)},**options))


def exported(value=None,format='PNG'):
    ctx=supplied(value);state,program,_=execute("V_SAVE_IMREG(1,'out."+format.lower()+"',s)",ctx)
    assert state['S']==0
    return ctx.files.snapshot()['out.'+format.lower()],ctx,program


def expected_rgba(value):
    palette=value['palette'];raw=value['pixels'];width=value['width']
    return [[tuple(palette[index*4:index*4+4]) for index in raw[start:start+width]] for start in range(0,len(raw),width)]


class PaletteRasterValidationTests(unittest.TestCase):
    def test_packed_rgba_bytes_and_canonical_hex_have_same_internal_data(self):
        value=image()
        for source in (value,dict(value,pixels=value['pixels'].hex(),palette=value['palette'].hex())):
            with self.subTest(source=source):self.assertEqual(supplied(source).vision.io.images[1]['image'],value)

    def test_gray_without_palette_keeps_its_existing_meaning(self):
        gray=dict(width=1,height=1,channels=1,pixels=b'\xff')
        checked=raster(gray,1);self.assertNotIn('palette',checked)
        self.assertEqual(struct.unpack('>IIBBBBB',dict(png(encode_raster(gray,'PNG',1000,lambda:None)))[b'IHDR'])[3],0)

    def test_palette_is_only_valid_for_single_index_channel(self):
        for channels in (2,3,4,True,'1'):
            with self.subTest(channels=channels),self.assertRaises(ValueError):raster(dict(image(),channels=channels),1000)

    def test_one_and_256_color_palettes_accept_every_index(self):
        one=image(1,1,b'\0',bytes((12,34,56,255)));self.assertEqual(raster(one,5),one)
        colors=bytes(component for index in range(256) for component in (index,255-index,index//2,index))
        value=image(256,1,bytes(range(256)),colors);self.assertEqual(raster(value,1280),value)

    def test_empty_short_non_rgba_and_oversized_palettes_are_rejected(self):
        for palette in (b'',b'\0',b'\0'*3,b'\0'*5,b'\0'*1028,'','000000','00'*5,'00'*1028):
            with self.subTest(length=len(palette)),self.assertRaises(ValueError):raster(dict(image(),palette=palette),10000)

    def test_palette_rejects_mutable_arrays_lists_objects_and_none(self):
        for palette in (None,[],[0,0,0,255],bytearray(COLORS),{'hex':COLORS.hex()},True,123):
            with self.subTest(palette=palette),self.assertRaises(ValueError):raster(dict(image(),palette=palette),1000)

    def test_palette_hex_requires_lowercase_no_spaces_or_prefix(self):
        for palette in ('FF0000FF','gg0000ff','0x0000ff','0000 0ff','000000f\n'):
            with self.subTest(palette=palette),self.assertRaises(ValueError):raster(image(1,1,b'\0',palette),1000)

    def test_unknown_color_layout_and_palette_metadata_fail_closed(self):
        for field,value in (('palette_channels',3),('palette_format','RGB'),('premultiplied',True),('depth',4)):
            with self.subTest(field=field),self.assertRaises(ValueError):raster(dict(image(),**{field:value}),1000)

    def test_rgb_triplets_are_not_inferred_as_rgba_entries(self):
        with self.assertRaisesRegex(ValueError,'RGBA'):raster(image(1,1,b'\0',b'\xff\0\0'),1000)

    def test_out_of_range_index_is_rejected_without_clipping(self):
        for value in (image(pixels=b'\0\1\3\0'),image(1,1,b'\xff',OPAQUE)):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'index'):raster(value,1000)

    def test_unused_and_duplicate_palette_entries_are_preserved(self):
        colors=OPAQUE+OPAQUE[:4];value=image(1,1,b'\0',colors)
        self.assertEqual(raster(value,17)['palette'],colors)

    def test_palette_bytes_count_against_exact_per_raster_limit(self):
        self.assertEqual(raster(image(),16),image())
        with self.assertRaisesRegex(ValueError,'configured byte limit'):raster(image(),15)

    def test_limits_precede_pixel_and_palette_hex_decoding(self):
        value=image(1,1,'zz','zzzzzzzz')
        for options in ({'limit':4},{'limit':1000,'remaining':4}):
            with self.subTest(options=options),patch('karel2py.vision.re.fullmatch',side_effect=AssertionError('hex parsed before quota')):
                with self.assertRaisesRegex(ValueError,'byte limit|Combined vision'):raster(value,**options)

    def test_images_and_captures_share_index_plus_palette_budget(self):
        value=image(2,1,b'\0\1',OPAQUE[:8]);config={'image_count':1,'images':{'1':record(value)},'captures':[capture(value)]}
        with patch('karel2py.vision._IMAGE_TOTAL_LIMIT',20):self.assertEqual(len(context(io=config).vision.io.captures),1)
        with patch('karel2py.vision._IMAGE_TOTAL_LIMIT',19),self.assertRaisesRegex(ValueError,'Combined vision'):context(io=config)

    def test_combined_limit_rejects_later_hex_before_allocating_or_mutating_config(self):
        value=image(2,1,b'\0\1',OPAQUE[:8]);bad=dict(value,pixels='zzzz',palette='zzzzzzzzzzzzzzzz')
        config={'image_count':1,'images':{'1':record(value)},'captures':[capture(bad)]};before=deepcopy(config)
        with patch('karel2py.vision._IMAGE_TOTAL_LIMIT',19),self.assertRaisesRegex(ValueError,'Combined vision'):context(io=config)
        self.assertEqual(config,before)

    def test_failed_capture_replies_use_no_palette_budget(self):
        with patch('karel2py.vision._IMAGE_TOTAL_LIMIT',16):
            ctx=supplied(captures=[dict(process='SCAN',views=[1],status=7)])
            self.assertEqual(len(ctx.vision.io.captures),1)

    def test_production_limits_include_palette_before_large_pixel_admission(self):
        value=image(4096,4096,'bad',b'\0\0\0\xff')
        with self.assertRaisesRegex(ValueError,'configured byte limit'):raster(value,16*1024*1024)

    def test_encoder_revalidates_palette_before_any_rows(self):
        for value in (dict(image(),palette=b'bad'),dict(image(),pixels=b'\0\1\3\0')):
            with self.subTest(value=value),self.assertRaises(ValueError):encode_raster(value,'BMP',1000,lambda:self.fail('Malformed image reached row expansion'))


class PalettePngTests(unittest.TestCase):
    def test_indexed_header_required_palette_transparency_order_and_independent_crcs(self):
        data,_,_=exported();chunks=png(data);parts=dict(chunks)
        self.assertEqual([kind for kind,_ in chunks],[b'IHDR',b'PLTE',b'tRNS',b'IDAT',b'IEND'])
        self.assertEqual(struct.unpack('>IIBBBBB',parts[b'IHDR']),(2,2,8,3,0,0,0))
        self.assertEqual(parts[b'PLTE'],bytes.fromhex('ff2040806030010203'));self.assertEqual(parts[b'tRNS'],b'\0\x80\xff')
        self.assertEqual(zlib.decompress(parts[b'IDAT']),b'\0\0\1\0\2\0')

    def test_opaque_palette_omits_transparency_chunk(self):
        data,_,_=exported(image(palette=OPAQUE));chunks=png(data)
        self.assertEqual([kind for kind,_ in chunks],[b'IHDR',b'PLTE',b'IDAT',b'IEND'])

    def test_every_alpha_value_and_hidden_rgb_color_is_preserved(self):
        for alpha in (0,1,127,128,254,255):
            with self.subTest(alpha=alpha):
                data,_,_=exported(image(1,1,b'\0',bytes((211,37,99,alpha))));parts=dict(png(data))
                self.assertEqual(parts[b'PLTE'],bytes((211,37,99)))
                if alpha==255:self.assertNotIn(b'tRNS',parts)
                else:self.assertEqual(parts[b'tRNS'],bytes((alpha,)))

    def test_256_entries_keep_full_tables_and_byte_indexes(self):
        colors=bytes(component for index in range(256) for component in (index,255-index,index//2,index))
        data,_,_=exported(image(256,1,bytes(range(256)),colors));parts=dict(png(data))
        self.assertEqual(len(parts[b'PLTE']),768);self.assertEqual(parts[b'tRNS'],bytes(range(256)))
        self.assertEqual(zlib.decompress(parts[b'IDAT']),b'\0'+bytes(range(256)))

    def test_odd_width_rows_keep_index_bytes_without_bit_packing_or_padding(self):
        for width in (1,2,3,4,7):
            with self.subTest(width=width):
                raw=bytes(index%3 for index in range(width*3));data,_,_=exported(image(width,3,raw))
                self.assertEqual(zlib.decompress(dict(png(data))[b'IDAT']),b''.join(b'\0'+raw[start:start+width] for start in range(0,len(raw),width)))

    def test_palette_metadata_minimum_size_is_checked_before_row_work(self):
        # 57-byte chunk framing + PLTE(12+9) + tRNS(12+3).
        self.assertIsNone(encode_raster(image(),'PNG',92,lambda:self.fail('Impossible PNG reached rows')))


class PaletteBmpTests(unittest.TestCase):
    def test_palette_bmp_expands_to_existing_v4_alpha_header(self):
        data,_,_=exported(format='BMP')
        self.assertEqual(struct.unpack_from('<IiiHHIIiiII',data,14),(108,2,2,1,32,3,16,0,0,0,0))
        self.assertEqual(struct.unpack_from('<IIII',data,54),(0x00ff0000,0x0000ff00,0x000000ff,0xff000000))
        self.assertEqual((int.from_bytes(data[10:14],'little'),len(data)),(122,138))
        self.assertEqual(struct.unpack_from('<I',data,70)[0],0x73524742)

    def test_bottom_up_bgra_rows_decode_to_original_palette_colors(self):
        value=image();data,_,_=exported(value,'BMP')
        self.assertEqual(bmp_pixels(data),expected_rgba(value));self.assertEqual(data[122:126],bytes((3,2,1,255)))

    def test_all_opaque_palettes_still_use_v4_without_losing_colors(self):
        value=image(palette=OPAQUE);data,_,_=exported(value,'BMP')
        self.assertEqual(int.from_bytes(data[28:30],'little'),32);self.assertEqual(bmp_pixels(data),expected_rgba(value))

    def test_many_widths_and_repeated_colors_keep_alpha_without_extra_padding(self):
        for width in (1,2,3,4,7):
            with self.subTest(width=width):
                value=image(width,3,bytes(index%3 for index in range(width*3)));data,_,_=exported(value,'BMP')
                self.assertEqual(len(data),122+width*3*4);self.assertEqual(bmp_pixels(data),expected_rgba(value))

    def test_size_preflight_precedes_expansion_and_row_callbacks(self):
        with patch('karel2py.vision.bytearray',side_effect=AssertionError('allocated rows before quota'),create=True):
            self.assertIsNone(encode_raster(image(),'BMP',137,lambda:self.fail('Oversized BMP reached rows')))

    def test_transparent_colors_remain_nonpremultiplied(self):
        value=image(1,1,b'\0',bytes((255,128,64,0)));data,_,_=exported(value,'BMP')
        self.assertEqual(bmp_pixels(data),[[(255,128,64,0)]])


class PaletteImageLifetimeTests(unittest.TestCase):
    def test_capture_detaches_caller_metadata_and_retains_indexes_and_palette(self):
        value=image();request=capture(value);ctx=context(io={'image_count':1,'captures':[request]})
        request['image']['palette']=OPAQUE;request['image']['pixels']=b'bad';request['views'].append(2)
        values,_,_=execute("V_SNAP_VIEW('scan',1,1,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.io.images[1]['image'],image());self.assertEqual(ctx.vision.io.captures,[])

    def test_failed_capture_consumes_reply_without_changing_prior_palette(self):
        ctx=supplied(captures=[dict(process='SCAN',views=[1],status=91)]);before=deepcopy(ctx.vision.io.images)
        values,_,_=execute("V_SNAP_VIEW('scan',1,1,s)",ctx)
        self.assertEqual(values['S'],91);self.assertEqual(ctx.vision.io.images,before);self.assertEqual(ctx.vision.io.captures,[])

    def test_capture_selection_mismatch_preserves_queue_and_prior_image(self):
        ctx=context(views=(1,2),io={'image_count':1,'images':{'1':record(image())},'captures':[dict(capture(image()),views=[2])]})
        before=ctx.vision.io.to_config();values,_,_=execute("V_SNAP_VIEW('scan',1,1,s)",ctx)
        self.assertEqual(values['S'],2);self.assertEqual(ctx.vision.io.to_config(),before)

    def test_find_consumes_supplied_results_without_changing_palette_or_dimensions(self):
        ctx=supplied(image(),dict(batch(found(5),view=1),image_reg=1));before=deepcopy(ctx.vision.io.images)
        values,_,_=execute("V_FIND_VIEW('scan',1,1,s) V_GET_OFFSET('scan',1,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.io.images,before);self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],5.)

    def test_export_does_not_change_images_capture_queue_or_display_state(self):
        ctx=supplied(captures=[capture(image(palette=OPAQUE))],display_tools={'SCAN':0},displayed='SCAN');before=ctx.vision.io.to_config()
        execute("V_SAVE_IMREG(1,'out.png',s) V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        self.assertEqual(ctx.vision.io.to_config(),before)

    def test_context_json_roundtrip_uses_canonical_palette_hex_and_consumed_queue(self):
        ctx=context(io={'image_count':1,'captures':[capture(image())]});execute("V_SNAP_VIEW('scan',1,1,s) V_SAVE_IMREG(1,'first.png',s)",ctx)
        saved=json.loads(json.dumps(ctx.to_config()));image_config=saved['vision']['io']['images']['1']['image']
        self.assertEqual((image_config['pixels'],image_config['palette']),('00010200',COLORS.hex()))
        restored=rt.ExecutionContext.from_config(saved);self.assertEqual(restored.to_config(),saved)
        execute("V_SAVE_IMREG(1,'second.png',s)",restored);self.assertEqual(restored.files.files['first.png'],restored.files.files['second.png'])
        self.assertEqual(restored.vision.io.captures,[])

    def test_saved_configuration_is_detached_from_live_palette_records(self):
        ctx=supplied();saved=ctx.vision.io.to_config();saved['images']['1']['image']['palette']='ffffffff'
        self.assertEqual(ctx.vision.io.images[1]['image']['palette'],COLORS)


class PaletteExportFailureTests(unittest.TestCase):
    def test_exact_encoded_limit_succeeds_one_byte_less_preserves_existing_output(self):
        for format in ('PNG','BMP'):
            data=encode_raster(image(),format,1000,lambda:None)
            for limit,code in ((len(data),0),(len(data)-1,5)):
                with self.subTest(format=format,limit=limit):
                    ctx=supplied();ctx.files=rt.MemoryFiles({'out.'+format.lower():b'keep'},limit=limit);before=ctx.vision.io.to_config()
                    values,_,_=execute("V_SAVE_IMREG(1,'out."+format.lower()+"',s)",ctx)
                    self.assertEqual(values['S'],code);self.assertEqual(ctx.vision.io.to_config(),before)
                    self.assertEqual(ctx.files.snapshot()['out.'+format.lower()],b'keep' if code else data)

    def test_budget_failure_preserves_file_palette_queues_and_status(self):
        for format in ('png','bmp'):
            with self.subTest(format=format):
                value=image(1,128,bytes(index%3 for index in range(128)));ctx=supplied(value,captures=[capture(image())])
                ctx.files=rt.MemoryFiles({'out.'+format:b'keep'});before=ctx.vision.to_config()
                program,_=compile_program("s=99 V_SAVE_IMREG(1,'out."+format+"',s)",decl='s:INTEGER',context=ctx)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):program.run(max_steps=30)
                self.assertEqual(ctx.files.snapshot()['out.'+format],b'keep');self.assertEqual(ctx.vision.to_config(),before)
                self.assertEqual(program.snapshot()['S'],99)

    def test_busy_destination_keeps_owner_and_cursor(self):
        ctx=supplied();ctx.files=rt.MemoryFiles({'out.bmp':b'keep'});handle=rt.FileHandle();ctx.files.open(handle,'R','out.bmp');handle.position=2
        before=ctx.vision.io.to_config();values,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        self.assertEqual((values['S'],handle.position),(3,2));self.assertIs(handle.owner,ctx.files)
        self.assertEqual(ctx.files.snapshot()['out.bmp'],b'keep');self.assertEqual(ctx.vision.io.to_config(),before);ctx.files.close(handle)

    def test_virtual_volume_quota_counts_expansion_and_retained_old_output(self):
        for capacity,code in ((141,6),(142,0)):
            with self.subTest(capacity=capacity):
                ctx=supplied();ctx.files=rt.DeviceFiles({'FR:':{'capacity':capacity}},{'FR:out.bmp':b'keep'})
                values,_,_=execute("V_SAVE_IMREG(1,'FR:out.bmp',s)",ctx);self.assertEqual(values['S'],code)
                self.assertEqual(ctx.files._volumes['FR']['garbage'],0 if code else 4)
                self.assertEqual(ctx.files.snapshot()['FR:out.bmp'],b'keep' if code else encode_raster(image(),'BMP',1000,lambda:None))

    def test_readonly_device_does_not_replace_previous_output(self):
        ctx=supplied();ctx.files=rt.DeviceFiles({'RD:':{'capacity':1000,'read_only':True}},{'RD:out.bmp':b'keep'})
        values,_,_=execute("V_SAVE_IMREG(1,'RD:out.bmp',s)",ctx);self.assertEqual(values['S'],6)
        self.assertEqual(ctx.files.snapshot()['RD:out.bmp'],b'keep')

    def test_directory_atomic_publish_failure_keeps_old_output(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'out.bmp';path.write_bytes(b'keep');ctx=supplied();ctx.files=rt.DirectoryFiles(root)
            with patch('karel2py.storage.atomic_bytes',side_effect=OSError('authored palette publish failure')):
                values,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
            self.assertEqual(values['S'],6);self.assertEqual(path.read_bytes(),b'keep');self.assertEqual(ctx.files.files,{})

    def test_corrupt_internal_palette_or_index_fails_before_request_or_output(self):
        for field,value in (('palette',b'bad'),('pixels',b'\0\1\3\0')):
            with self.subTest(field=field):
                ctx=supplied();ctx.vision.io.images[1]['image'][field]=value;ctx.files=rt.MemoryFiles({'out.png':b'keep'})
                with self.assertRaises(rt.KarelRuntimeError):execute("V_SAVE_IMREG(1,'out.png',s)",ctx)
                self.assertEqual(ctx.files.snapshot()['out.png'],b'keep');self.assertEqual(ctx.vision.sequence,0)

    def test_encoder_callback_failure_keeps_supplied_image_unchanged(self):
        value=image(1,3,b'\0\1\2');before=deepcopy(value);seen=[]
        def check():
            seen.append(True)
            if len(seen)==2:raise RuntimeError('authored budget stop')
        with self.assertRaisesRegex(RuntimeError,'budget stop'):encode_raster(value,'BMP',1000,check)
        self.assertEqual(value,before)


class PaletteLegacyArtifactTests(unittest.TestCase):
    def test_existing_gray_ga_rgb_rgba_png_and_bmp_wire_hashes_are_unchanged(self):
        hashes={
            1:('15e3339f10568c80a297405e2e48e3cad96bdf82ec5bc0f1062cf760358d7cdb','9879734f475e4e763b55d4bf747f3ae322ce0238dd92de17f7e53780c139f928'),
            2:('e4fd515194ee912f10d4364d1210dccce932a3ebb0e196ecf1b2ee09e3f2780b','b2153926d47d7ef0a7fe8db2a39bda45a516f9ef9b76173111fb8e644790fa0a'),
            3:('4e26b92e22a9d2b77461584e485638c631ab591730710170fd40af7fce08ce1d','eb9a8477c421f7a20d78a44f02ca21a738170520242d3fd5d437e3390a46db52'),
            4:('08174714fe4dc08ab6ba64c11fc21bbd3b0652d0d3fdad90df0405092c3db72f','89aa30247dc6eeee154bee1050601d5fbeabb8d4d1e02e6634d3ace2a343580c')}
        for channels,pair in hashes.items():
            value=dict(width=3,height=3,channels=channels,pixels=bytes((index*37)%256 for index in range(9*channels)))
            for format,wanted in zip(('PNG','BMP'),pair):
                with self.subTest(channels=channels,format=format):self.assertEqual(hashlib.sha256(encode_raster(value,format,10000,lambda:None)).hexdigest(),wanted)


if __name__=='__main__':unittest.main()
