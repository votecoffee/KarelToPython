"""Supplied grayscale-alpha/RGBA images, wire formats and offline lifecycle."""
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


def image(channels=4,width=2,height=2,pixels=None):
    if pixels is None:pixels=bytes((i*37)%256 for i in range(width*height*channels))
    return dict(width=width,height=height,channels=channels,pixels=pixels)


def record(value):return dict(process='SCAN',views=[1],image=value)
def capture(value):return dict(record(value),status=0)


def supplied(value,*runs,**options):
    return context(*runs,io=dict(image_count=1,images={'1':record(value)},**options))


def export(value,format='PNG',**options):
    ctx=supplied(value);values,program,_=execute("V_SAVE_IMREG(1,'image."+format.lower()+"',s)",ctx,**options)
    assert values['S']==0
    return ctx.files.snapshot()['image.'+format.lower()],ctx,program


def crc32(data):
    crc=0xffffffff
    for value in data:
        crc^=value
        for _ in range(8):crc=(crc>>1)^0xedb88320 if crc&1 else crc>>1
    return crc^0xffffffff


def png(data):
    assert data[:8]==b'\x89PNG\r\n\x1a\n'
    position=8;chunks=[]
    while position<len(data):
        length=int.from_bytes(data[position:position+4],'big');kind=data[position+4:position+8]
        payload=data[position+8:position+8+length];saved=int.from_bytes(data[position+8+length:position+12+length],'big')
        assert len(payload)==length and saved==crc32(kind+payload)
        chunks.append((kind,payload));position+=12+length
    assert position==len(data)
    return chunks


def bmp_pixels(data):
    offset=int.from_bytes(data[10:14],'little');width,height=struct.unpack_from('<ii',data,18)
    masks=struct.unpack_from('<IIII',data,54);rows=[]
    for y in range(height-1,-1,-1):
        values=[]
        for x in range(width):
            packed=int.from_bytes(data[offset+(y*width+x)*4:offset+(y*width+x+1)*4],'little')
            values.append(tuple((packed&mask)>>((mask&-mask).bit_length()-1) for mask in masks))
        rows.append(values)
    return rows


class AlphaRasterValidationTests(unittest.TestCase):
    def test_ga_and_rgba_accept_exact_bytes_and_canonical_hex(self):
        for channels in (2,4):
            data=image(channels)
            for value in (data,dict(data,pixels=data['pixels'].hex())):
                with self.subTest(channels=channels):
                    ctx=supplied(value);self.assertEqual(ctx.vision.io.images[1]['image']['pixels'],data['pixels'])
                    self.assertEqual(ctx.vision.io.images[1]['image']['channels'],channels)

    def test_invalid_channel_counts_remain_rejected(self):
        for channels in (0,5,6,-1,True,False,4.,'4'):
            with self.subTest(channels=channels),self.assertRaises(ValueError):supplied(dict(image(),channels=channels))

    def test_alpha_pixel_length_must_match_every_channel(self):
        for channels in (2,4):
            for count in (0,1,3,7,9,15,17):
                with self.subTest(channels=channels,count=count),self.assertRaises(ValueError):supplied(image(channels,pixels=b'x'*count))

    def test_pixel_sources_stay_immutable_and_hex_stays_canonical(self):
        for value in (bytearray(16),[0]*16,'FF'*16,'0g'*16,'00'*15,'00'*17):
            with self.subTest(kind=type(value).__name__),self.assertRaises(ValueError):supplied(image(pixels=value))

    def test_unknown_layout_and_premultiplication_metadata_are_not_guessed(self):
        for field,value in (('layout','ARGB'),('premultiplied',True),('depth',16),('palette',[])):
            with self.subTest(field=field),self.assertRaises(ValueError):supplied(dict(image(),**{field:value}))

    def test_raw_size_checked_before_hex_parsing(self):
        with self.assertRaisesRegex(ValueError,'configured byte limit'):raster(image(pixels='not-hex'),15)
        with self.assertRaisesRegex(ValueError,'configured byte limit'):raster(image(4,4096,4096,pixels='00'),16*1024*1024)

    def test_combined_limit_checked_before_later_hex_decode(self):
        first=image(2,2,1);bad=image(2,2,1,pixels='not-hex')
        config=dict(image_count=1,images={'1':record(first)},captures=[capture(bad)])
        before=deepcopy(config)
        with patch('karel2py.vision._IMAGE_TOTAL_LIMIT',6),self.assertRaisesRegex(ValueError,'Combined vision.*64 MiB'):context(io=config)
        self.assertEqual(config,before)

    def test_images_and_pending_captures_share_complete_raw_budget(self):
        first=image(2,2,1);second=image(4,1,1)
        with patch('karel2py.vision._IMAGE_TOTAL_LIMIT',8):
            ctx=context(io={'image_count':1,'images':{'1':record(first)},'captures':[capture(second),dict(process='SCAN',views=[1],status=5)]})
            self.assertEqual(len(ctx.vision.io.captures),2)
            with self.assertRaisesRegex(ValueError,'Combined vision'):context(io={'image_count':1,'images':{'1':record(first)},'captures':[capture(second),capture(second)]})

    def test_per_image_and_combined_production_limits_are_unchanged(self):
        from karel2py.vision import _IMAGE_RAW_LIMIT,_IMAGE_TOTAL_LIMIT
        self.assertEqual((_IMAGE_RAW_LIMIT,_IMAGE_TOTAL_LIMIT),(16*1024*1024,64*1024*1024))
        with self.assertRaises(ValueError):context(io={'image_limit':16*1024*1024+1})

    def test_exact_actual_raw_limit_and_combined_limit_use_no_pixel_copies(self):
        raw=bytes(16*1024*1024);value=image(4,4096,1024,raw)
        ctx=context(io={'image_count':1,'captures':[capture(value)]*4})
        self.assertEqual(len(ctx.vision.io.captures),4)
        self.assertTrue(all(row['image']['pixels'] is raw for row in ctx.vision.io.captures))
        with self.assertRaisesRegex(ValueError,'Combined vision.*64 MiB'):
            context(io={'image_count':1,'captures':[capture(value)]*5})
        with self.assertRaisesRegex(ValueError,'configured byte limit'):
            raster(image(4,4096,1025,raw),16*1024*1024)

    def test_encoder_revalidates_corrupt_store_before_allocating_rows(self):
        for bad in (dict(image(),pixels=b'bad'),dict(image(),channels=5),dict(image(),width=0)):
            with self.subTest(bad=bad),self.assertRaises(ValueError):encode_raster(bad,'BMP',1000,lambda:self.fail('Invalid image reached row allocation'))

    def test_unknown_encoder_format_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'PNG or BMP'):encode_raster(image(),'JPEG',1000,lambda:None)


class AlphaPngTests(unittest.TestCase):
    def test_ga_png_color_type_samples_and_independent_crcs(self):
        raw=b'\x40\x80\xff\x00\x10\xff\x22\x01';data,ctx,_=export(image(2,pixels=raw))
        chunks=png(data);self.assertEqual([kind for kind,_ in chunks],[b'IHDR',b'IDAT',b'IEND'])
        self.assertEqual(struct.unpack('>IIBBBBB',chunks[0][1]),(2,2,8,4,0,0,0))
        self.assertEqual(zlib.decompress(chunks[1][1]),b'\0'+raw[:4]+b'\0'+raw[4:])
        self.assertEqual(ctx.vision.io.images[1]['image']['pixels'],raw)

    def test_rgba_png_color_type_and_nonpremultiplied_samples(self):
        raw=b'\xff\x20\x40\x00\x80\x60\x30\x80\x01\x02\x03\xff\xfe\xfd\xfc\x01';data,_,_=export(image(4,pixels=raw))
        chunks=png(data);self.assertEqual(struct.unpack('>IIBBBBB',chunks[0][1]),(2,2,8,6,0,0,0))
        self.assertEqual(zlib.decompress(chunks[1][1]),b'\0'+raw[:8]+b'\0'+raw[8:])

    def test_all_alpha_extremes_and_intermediate_values_are_retained(self):
        for alpha in (0,1,127,128,254,255):
            with self.subTest(alpha=alpha):
                raw=bytes((211,37,99,alpha));data,_,_=export(image(4,1,1,raw))
                self.assertEqual(zlib.decompress(dict(png(data))[b'IDAT']),b'\0'+raw)

    def test_many_widths_have_no_extra_png_row_padding(self):
        for channels in (2,4):
            for width in (1,2,3,4,7):
                with self.subTest(channels=channels,width=width):
                    value=image(channels,width,3);data,_,_=export(value);decompressed=zlib.decompress(dict(png(data))[b'IDAT'])
                    stride=width*channels
                    self.assertEqual(len(decompressed),(stride+1)*3)
                    self.assertEqual(decompressed,b''.join(b'\0'+value['pixels'][i:i+stride] for i in range(0,len(value['pixels']),stride)))

    def test_legacy_gray_rgb_png_wire_bytes_are_unchanged(self):
        gold={1:'15e3339f10568c80a297405e2e48e3cad96bdf82ec5bc0f1062cf760358d7cdb',3:'4e26b92e22a9d2b77461584e485638c631ab591730710170fd40af7fce08ce1d'}
        for channels,wanted in gold.items():
            data,_,_=export(image(channels,3,3));self.assertEqual(hashlib.sha256(data).hexdigest(),wanted)

    def test_impossible_png_limit_exits_before_row_work(self):
        self.assertIsNone(encode_raster(image(),'PNG',56,lambda:self.fail('Minimum PNG size already exceeds the limit')))


class AlphaBmpTests(unittest.TestCase):
    def test_v4_header_alpha_masks_and_color_space_are_explicit(self):
        data,_,_=export(image(),'BMP')
        self.assertEqual(data[:2],b'BM');self.assertEqual(int.from_bytes(data[2:6],'little'),len(data));self.assertEqual(data[6:10],b'\0'*4)
        self.assertEqual(int.from_bytes(data[10:14],'little'),122)
        header=struct.unpack_from('<IiiHHIIiiII',data,14)
        self.assertEqual(header,(108,2,2,1,32,3,16,0,0,0,0))
        masks=struct.unpack_from('<IIII',data,54);self.assertEqual(masks,(0x00ff0000,0x0000ff00,0x000000ff,0xff000000))
        self.assertEqual(struct.unpack_from('<I',data,70)[0],0x73524742);self.assertEqual(data[74:122],b'\0'*48)
        self.assertEqual(len(data),138)

    def test_rgba_bottom_up_bgra_pixels_decode_through_masks(self):
        raw=b'\xff\x20\x40\x00\x80\x60\x30\x80\x01\x02\x03\xff\xfe\xfd\xfc\x01'
        data,_,_=export(image(4,pixels=raw),'BMP')
        self.assertEqual(bmp_pixels(data),[[tuple(raw[i:i+4]) for i in (0,4)],[tuple(raw[i:i+4]) for i in (8,12)]])
        self.assertEqual(data[122:126],b'\x03\x02\x01\xff')

    def test_gray_alpha_expands_gray_without_changing_opacity(self):
        raw=b'\x40\x80\xff\x00\x10\xff\x22\x01';data,_,_=export(image(2,pixels=raw),'BMP')
        self.assertEqual(bmp_pixels(data),[[(64,64,64,128),(255,255,255,0)],[(16,16,16,255),(34,34,34,1)]])
        self.assertEqual(data[122:126],b'\x10\x10\x10\xff')

    def test_odd_widths_need_no_padding_beyond_32bit_pixels(self):
        for channels in (2,4):
            for width in (1,2,3,4,7):
                with self.subTest(channels=channels,width=width):
                    data,_,_=export(image(channels,width,3),'BMP');self.assertEqual(len(data),122+width*3*4)
                    self.assertEqual(struct.unpack_from('<I',data,34)[0],width*3*4)

    def test_transparent_color_values_are_never_blackened(self):
        data,_,_=export(image(4,1,1,b'\xff\x80\x40\0'),'BMP')
        self.assertEqual(bmp_pixels(data),[[(255,128,64,0)]])

    def test_gray_alpha_encoded_size_is_preflighted_before_expansion(self):
        value=image(2)
        with patch('karel2py.vision.bytearray',side_effect=AssertionError('Expanded before size preflight'),create=True):
            self.assertIsNone(encode_raster(value,'BMP',137,lambda:self.fail('Oversized BMP reached rows')))

    def test_legacy_gray_rgb_bmp_wire_bytes_are_unchanged(self):
        gold={1:'9879734f475e4e763b55d4bf747f3ae322ce0238dd92de17f7e53780c139f928',3:'eb9a8477c421f7a20d78a44f02ca21a738170520242d3fd5d437e3390a46db52'}
        for channels,wanted in gold.items():
            data,_,_=export(image(channels,3,3),'BMP');self.assertEqual(hashlib.sha256(data).hexdigest(),wanted)
            self.assertEqual(struct.unpack_from('<I',data,14)[0],40);self.assertEqual(struct.unpack_from('<H',data,28)[0],24)


class AlphaImageLifetimeTests(unittest.TestCase):
    def test_capture_preserves_rgba_and_detaches_caller_record(self):
        value=image();request=capture(value);ctx=context(io={'image_count':1,'captures':[request]})
        request['image']['pixels']=b'changed';values,_,_=execute("V_SNAP_VIEW('scan',1,1,s)",ctx)
        self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.io.images[1]['image']['pixels'],image()['pixels'])
        self.assertEqual(ctx.vision.io.images[1]['image']['channels'],4);self.assertEqual(ctx.vision.io.captures,[])

    def test_failed_capture_preserves_prior_gray_alpha_image(self):
        ctx=supplied(image(2),captures=[dict(process='SCAN',views=[1],status=91)]);before=deepcopy(ctx.vision.io.images)
        values,_,_=execute("V_SNAP_VIEW('scan',1,1,s)",ctx)
        self.assertEqual(values['S'],91);self.assertEqual(ctx.vision.io.images,before);self.assertEqual(ctx.vision.io.captures,[])

    def test_find_view_consumes_supplied_results_without_modifying_alpha(self):
        for channels in (2,4):
            ctx=supplied(image(channels),dict(batch(found(5),view=1),image_reg=1));before=deepcopy(ctx.vision.io.images)
            values,_,_=execute("V_FIND_VIEW('scan',1,1,s) V_GET_OFFSET('scan',1,s)",ctx)
            self.assertEqual(values['S'],0);self.assertEqual(ctx.vision.io.images,before)
            self.assertEqual(ctx.vision.registers[1]['offset'].values['X'],5.)

    def test_export_does_not_modify_raw_storage_capture_queue_or_display(self):
        ctx=supplied(image(2),captures=[capture(image(4))],display_tools={'SCAN':0},displayed='SCAN');before=ctx.vision.io.to_config()
        execute("V_SAVE_IMREG(1,'alpha.png',s) V_SAVE_IMREG(1,'alpha.bmp',s)",ctx)
        self.assertEqual(ctx.vision.io.to_config(),before)

    def test_saved_json_preserves_channels_bytes_and_consumed_capture_lifetime(self):
        ctx=context(io={'image_count':1,'captures':[capture(image(4)),capture(image(2))]})
        execute("V_SNAP_VIEW('scan',1,1,s)",ctx);saved=json.loads(json.dumps(ctx.to_config()))
        restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.vision.io.images[1]['image']['channels'],4)
        self.assertEqual(saved['vision']['io']['images']['1']['image']['pixels'],image(4)['pixels'].hex())
        execute("V_SNAP_VIEW('scan',1,1,s)",restored)
        self.assertEqual(restored.vision.io.images[1]['image']['channels'],2);self.assertEqual(restored.vision.io.captures,[])
        self.assertEqual(ctx.vision.io.images[1]['image']['channels'],4)

    def test_saved_configuration_is_detached_after_reload(self):
        ctx=supplied(image(4));saved=ctx.to_config();restored=rt.ExecutionContext.from_config(saved)
        saved['vision']['io']['images']['1']['image']['pixels']='00'*16
        self.assertEqual(restored.vision.io.images[1]['image']['pixels'],image(4)['pixels'])

    def test_replayed_export_matches_original_artifact_bytes(self):
        ctx=supplied(image(4));execute("V_SAVE_IMREG(1,'first.png',s)",ctx)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        execute("V_SAVE_IMREG(1,'second.png',s)",restored)
        self.assertEqual(restored.files.files['first.png'],restored.files.files['second.png'])


class AlphaExportFailureTests(unittest.TestCase):
    def test_encoded_file_limit_rejects_without_replacing_old_file(self):
        for format in ('PNG','BMP'):
            ctx=supplied(image(2));ctx.files=rt.MemoryFiles({'image.'+format.lower():b'keep'},limit=64)
            before=ctx.vision.io.to_config();values,_,_=execute("V_SAVE_IMREG(1,'image."+format.lower()+"',s)",ctx)
            self.assertEqual(values['S'],5);self.assertEqual(ctx.files.snapshot()['image.'+format.lower()],b'keep');self.assertEqual(ctx.vision.io.to_config(),before)

    def test_exact_encoded_capacity_succeeds_one_byte_less_fails(self):
        for channels in (2,4):
            for format in ('PNG','BMP'):
                raw=encode_raster(image(channels),format,1000,lambda:None)
                for limit,expected in ((len(raw),0),(len(raw)-1,5)):
                    with self.subTest(channels=channels,format=format,limit=limit):
                        ctx=supplied(image(channels));ctx.files=rt.MemoryFiles({'old':b'keep'},limit=limit)
                        values,_,_=execute("V_SAVE_IMREG(1,'out."+format.lower()+"',s)",ctx);self.assertEqual(values['S'],expected)
                        if expected:self.assertEqual(ctx.files.snapshot(),{'old':b'keep'})
                        else:self.assertEqual(ctx.files.snapshot()['out.'+format.lower()],raw)

    def test_encoding_budget_failure_preserves_all_source_data_and_file(self):
        for channels in (2,4):
            for format in ('png','bmp'):
                ctx=supplied(image(channels,1,128));ctx.files=rt.MemoryFiles({'out.'+format:b'keep'});before=ctx.vision.to_config()
                p,_=compile_program("s=99 V_SAVE_IMREG(1,'out."+format+"',s)",context=ctx)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'step budget'):p.run(max_steps=30)
                self.assertEqual(ctx.files.snapshot()['out.'+format],b'keep');self.assertEqual(ctx.vision.to_config(),before)

    def test_busy_destination_preserves_open_cursor(self):
        ctx=supplied(image());ctx.files=rt.MemoryFiles({'out.bmp':b'keep'});handle=rt.FileHandle();ctx.files.open(handle,'R','out.bmp');handle.position=2
        before=ctx.vision.io.to_config();values,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
        self.assertEqual((values['S'],handle.position),(3,2));self.assertEqual(ctx.files.snapshot()['out.bmp'],b'keep')
        self.assertEqual(ctx.vision.io.to_config(),before);ctx.files.close(handle)

    def test_virtual_quota_includes_expanded_alpha_bmp_and_obsolete_bytes(self):
        for capacity,expected in ((141,6),(142,0)):
            ctx=supplied(image(2));ctx.files=rt.DeviceFiles({'FR:':{'capacity':capacity}},{'FR:out.bmp':b'keep'})
            values,_,_=execute("V_SAVE_IMREG(1,'FR:out.bmp',s)",ctx)
            self.assertEqual(values['S'],expected)
            if expected:self.assertEqual(ctx.files.snapshot()['FR:out.bmp'],b'keep');self.assertEqual(ctx.files._volumes['FR']['garbage'],0)
            else:self.assertEqual(len(ctx.files.files['FR:out.bmp']),138);self.assertEqual(ctx.files._volumes['FR']['garbage'],4)

    def test_readonly_virtual_volume_preserves_previous_file(self):
        ctx=supplied(image());ctx.files=rt.DeviceFiles({'RD:':{'capacity':1000,'read_only':True}},{'RD:out.bmp':b'keep'})
        values,_,_=execute("V_SAVE_IMREG(1,'RD:out.bmp',s)",ctx)
        self.assertEqual(values['S'],6);self.assertEqual(ctx.files.snapshot()['RD:out.bmp'],b'keep')

    def test_atomic_directory_failure_keeps_existing_target(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'out.bmp';path.write_bytes(b'keep');ctx=supplied(image());ctx.files=rt.DirectoryFiles(root)
            with patch('karel2py.storage.atomic_bytes',side_effect=OSError('authored export failure')):
                values,_,_=execute("V_SAVE_IMREG(1,'out.bmp',s)",ctx)
            self.assertEqual(values['S'],6);self.assertEqual(path.read_bytes(),b'keep');self.assertEqual(ctx.files.files,{})

    def test_mutated_invalid_raster_does_not_publish_output(self):
        ctx=supplied(image());ctx.vision.io.images[1]['image']['pixels']=b'bad';ctx.files=rt.MemoryFiles({'out.png':b'keep'})
        with self.assertRaises(rt.KarelRuntimeError):execute("V_SAVE_IMREG(1,'out.png',s)",ctx)
        self.assertEqual(ctx.files.snapshot()['out.png'],b'keep');self.assertEqual(ctx.vision.sequence,0)

    def test_encoder_callback_failure_does_not_mutate_input(self):
        value=image(2,3,3);before=deepcopy(value);checks=[]
        def check():
            checks.append(True)
            if len(checks)==2:raise RuntimeError('authored budget stop')
        with self.assertRaisesRegex(RuntimeError,'budget stop'):encode_raster(value,'BMP',1000,check)
        self.assertEqual(value,before)

    def test_bad_suffix_and_missing_image_preserve_files(self):
        ctx=supplied(image());ctx.files=rt.MemoryFiles({'old.jpg':b'keep'})
        values,_,_=execute("V_SAVE_IMREG(1,'old.jpg',s)",ctx);self.assertEqual(values['S'],2)
        values,_,_=execute("V_SAVE_IMREG(0,'out.png',s)",ctx);self.assertEqual(values['S'],2)
        self.assertEqual(ctx.files.snapshot(),{'old.jpg':b'keep'})


if __name__=='__main__':unittest.main()
