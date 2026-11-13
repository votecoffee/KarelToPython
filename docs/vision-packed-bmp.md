# Packed RGB555 and RGB565 BMP output

The offline `V_SAVE_IMREG(register, filename, status)` implementation supports
an optional BMP export preference on supplied grayscale/RGB rasters:

```json
{
  "width": 1,
  "height": 1,
  "channels": 3,
  "sample_bits": 16,
  "pixels": "042202090422",
  "bmp_format": "RGB565"
}
```

Saving this register to a `.BMP` path emits a packed 16-bit image. The preference
is exact uppercase `RGB555` or `RGB565`; omission retains existing default output.
It is separate from `sample_bits`, which still describes the supplied 8- or
16-bit components. See the [authored example](../examples/vision_packed_bmp.kl).

## Input and quantization

Only nonpalette grayscale (`channels:1`) or RGB (`channels:3`) rasters accept
the preference. Alpha and palette combinations reject rather than discarding
alpha or converting palette colors. Existing bounded dimensions, immutable
sample bytes, big-endian 16-bit components and raw quotas still apply.

Each original component rounds directly into its output field:

```python
packed_component = (sample * channel_max + sample_max // 2) // sample_max
```

`sample_max` is 255 or 65535. Red and blue use `channel_max=31`; green uses
31 for RGB555 or 63 for RGB565. Grayscale supplies the same original value to
all three channels. There is no intermediate 16-to-8-bit rounding. This is a
lossy export convention without color management, calibration or dithering.

## BMP layout

| Preference | Compression | Header/masks | Pixel data offset |
| --- | --- | --- | --- |
| RGB555 | BI_RGB (0) | 40-byte information header; unused high pixel bit zero. | 54 bytes |
| RGB565 | BI_BITFIELDS (3) | Same header followed by red/green/blue DWORD masks F800/07E0/001F. | 66 bytes |

Both emit little-endian 16-bit pixel words, positive height, bottom-up scanlines
and zero padding to a four-byte row boundary. Blue occupies the low five bits,
then green, then red. These layouts follow Microsoft's
[BITMAPINFOHEADER](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapinfoheader),
[RGB pixel layouts](https://learn.microsoft.com/en-us/windows/win32/directshow/uncompressed-rgb-video-subtypes)
and [scanline alignment rules](https://learn.microsoft.com/en-us/windows/win32/gdi/bitmap-header-types).
No packed-pixel input decoder or native FANUC image layout is introduced.

## Lifetime and publication

Validate the complete raster and raw quotas first, then check the exact encoded
file size before allocating or processing rows. Each bounded row begins with
the existing execution-budget checkpoint. Packing adds no imaging dependency.

Supplied registers and capture replies preserve exact original pixels, depth
and BMP preference. Saved JSON retains those values. PNG export ignores a valid
BMP preference and retains its previous lossless bytes. Context replay therefore
reproduces BMP output without reducing the source samples.

Whole-file publication uses existing MemoryFiles, DeviceFiles and explicitly
rooted DirectoryFiles guards. Output limit, busy/read-only media, capacity and
atomic replacement failures preserve previous output bytes. Budget failures
also retain the source status target; malformed mutated rasters fail before
status/history publication.

`vision_packed_bmp_policy` records the current contract. The
[semantic ledger](semantics/vision_packed_bmp_semantics.json) and
[independent tests](../tests/test_vision_packed_bmp.py) cover headers, words,
quantization, padding, capture/replay, linkage and failed publication. Native
camera, renderer/controller and public strict-mode equivalence remain separate.
