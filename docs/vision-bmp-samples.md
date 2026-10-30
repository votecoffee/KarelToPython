# BMP export from 16-bit samples

`V_SAVE_IMREG(register, filename, status)` accepts `.BMP` output for supplied
16-bit grayscale, grayscale-alpha, RGB and RGBA rasters. Each unsigned big-endian
component is rounded independently into an 8-bit component:

```python
output_component = (sample + 128) // 257
```

This is an explicit lossy Pythonic export policy. It maps 0 to 0 and 65535 to
255, rounds to the nearest representable component and bounds reconstruction
error to 128 sample units. Alpha uses the same rule. Colors beneath zero alpha
are retained independently; no premultiplication or color management occurs.

| Supplied channels | BMP encoding |
| --- | --- |
| Grayscale | Replicate rounded gray into 24-bit RGB. |
| RGB | Round each component into 24-bit RGB. |
| Grayscale-alpha | Replicate rounded gray into RGB and round alpha into a 32-bit V4 BITFIELDS image. |
| RGBA | Round each component into a 32-bit V4 BITFIELDS image. |

The existing bottom-up BGR/BGRA layouts, row padding, explicit alpha masks and
[BMP header conventions](vision-image-services.md#image-export-and-files) are retained.
This does not emit packed 16-bit RGB555/RGB565 BMP pixels. Existing 8-bit and
palette output bytes remain unchanged.

## Original samples and limits

Captures, image registers and saved context preserve the original `sample_bits`
and every supplied byte. [PNG output](vision-16bit-images.md) continues preserving
all 16-bit samples. Exporting BMP then PNG from the same register therefore
retains full precision in PNG.

Validate the complete supplied raster, dimensions, sample depth and raw quotas
before output preparation. Calculate the exact BMP size before allocating or
processing rows. Round one row after its execution-budget checkpoint; existing
16 MiB per-image and 64 MiB combined raw limits still count both input bytes.
The encoder adds no imaging dependency or external connection.

MemoryFiles, DeviceFiles and explicitly rooted DirectoryFiles use the existing
whole-file publication guards. Encoded file limits, busy/read-only targets,
volume capacity and atomic publication failures retain previous output bytes.
A budget error retains the prior status value, raster data and output file.
Valid BMP exports now return success instead of the previous unsupported status
2. Malformed supplied data remains a runtime error; unknown suffixes retain
status 2. Status codes follow the [image service contract](vision-image-services.md).

Reports expose `vision_bmp_sample_policy` with rounding, format, quota and
lifetime boundaries; `vision_sample_depth_policy` links the BMP policy. Native
camera, renderer/controller, physical depth, calibration and strict equivalence
remain unverified.

See the [grayscale example](../examples/vision_bmp_gray16.kl),
[RGBA example](../examples/vision_bmp_rgba16.kl),
[linked example](../examples/vision_bmp_samples_project/lib.kl),
[independent BMP checks](../tests/test_vision_bmp_samples.py) and
[ledger](semantics/vision_bmp_sample_semantics.json).
