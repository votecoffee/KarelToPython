# Supplied 16-bit PNG images

Explicit vision rasters accept optional `sample_bits: 16` for grayscale,
grayscale-alpha, RGB and RGBA data. The default remains 8 when the field is absent;
an explicitly supplied 8 is also retained. All channels use the same sample depth.

```json
{
  "width": 2,
  "height": 1,
  "channels": 2,
  "sample_bits": 16,
  "pixels": "0123fffffedc0000"
}
```

This is two grayscale-alpha pixels: gray 291/alpha 65535, then gray 65244/alpha 0.
Each unsigned sample occupies two bytes, most significant byte first. Python
input uses immutable bytes; JSON uses canonical lowercase hexadecimal. The
sample depth is never inferred from payload length. Palette indices remain
8-bit and cannot be combined with 16-bit samples.

The byte order and supported direct-color types follow the
[W3C PNG Third Edition](https://www.w3.org/TR/png-3/), sections 6.1 and 7.
The export retains original samples and alpha, including color data beneath zero
alpha. It performs no rescaling, quantization, byte swapping, calibration or color
processing. PNG IHDR contains depth 16 and color type 0, 4, 2 or 6 for one through
four channels, with matching two-byte scanline strides.

## Lifetime, quotas and output failures

Captures, image registers, completed finds and saved context retain `sample_bits`
and supplied bytes. Raw quota calculation multiplies width, height, channel count
and bytes per sample before hex decoding/allocation. Existing 16 MiB per-image
and 64 MiB combined image/capture limits remain; bit depth does not increase them.
Dimensions remain 1 through 4096.

V_SAVE_IMREG exports these rasters to PNG through existing file backends and
publication guards. PNG capacity, busy-file, budget and publication failures
preserve previous output bytes and raster data. A 16-bit BMP save returns portable
unsupported status 2 without changing the output; this encoder does not silently
reduce the data to eight bits. Direct `encode_raster(..., 'BMP', ...)` raises a
ValueError for such valid 16-bit data. Malformed supplied data remains an error.

Existing 8-bit grayscale, alpha, RGB, RGBA and palette artifact bytes remain
unchanged. No depth-map units, proprietary image layouts, image processing,
camera acquisition or native viewer/controller acceptance are introduced.

The [authored example](../examples/vision_16bit.kl) saves the two pixels above.
`vision_sample_depth_policy` records the input, PNG/BMP and quota contracts.
The [independent decoder tests](../tests/test_vision_16bit_images.py) check chunk
CRCs, PNG headers, decompressed rows, channel order, endian samples, alpha,
context replay and guarded failures. Strict mode remains future work.
