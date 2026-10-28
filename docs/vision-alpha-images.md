# Supplied alpha-channel vision images

Pythonic VisionServices accepts packed 8-bit grayscale-alpha and RGBA rasters in
addition to its existing grayscale/RGB formats. Capture replies, image registers,
image-bound finds and saved JSON retain the supplied bytes and channel count.
No alpha is inferred from a color, and no image acquisition or processing occurs.

| channels | Packed pixel order | PNG color type |
| --- | --- | --- |
| 1 | gray | 0 |
| 2 | gray, alpha | 4 |
| 3 | red, green, blue | 2 |
| 4 | red, green, blue, alpha | 6 |

Samples are unsigned bytes, with alpha zero transparent and 255 opaque. Color
samples remain independent of alpha, including nonzero colors beneath alpha zero.
No premultiplication, background flattening, gamma correction or automatic layout
conversion is performed. ARGB, BGRA, palettes, 16-bit samples and depth formats
are not inferred from the supplied data.

```json
{"width":2,"height":1,"channels":4,"pixels":"ff00008000ff0000"}
```

This is a half-transparent red pixel followed by a transparent green pixel. JSON
pixels remain canonical lowercase hexadecimal; Python callers can supply immutable
bytes. The exact byte count must equal width times height times channels.

## PNG and BMP export

V_SAVE_IMREG continues to select PNG/BMP from the filename suffix. PNG preserves
the packed samples with the table's color type, 8-bit depth, filter zero,
noninterlaced rows and zlib compression. Chunk integrity and alpha handling follow
the [W3C PNG specification](https://www.w3.org/TR/png/) sections 6.2 and 11.2.1.
No premultiplied sample conversion is applied.

Grayscale-alpha and RGBA BMP exports use a 108-byte BITMAPV4HEADER, pixel offset
122, 32 bits per pixel and BI_BITFIELDS. Bottom-up DWORD pixels use BGRA byte
order with red/green/blue/alpha masks 00ff0000, 0000ff00, 000000ff and ff000000.
Each gray-alpha pair expands to gray/gray/gray/alpha; the gray and alpha values
are unchanged. Complete 32-bit pixels already align each row to a DWORD.
These fields follow [Microsoft's BITMAPV4HEADER documentation](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapv4header).

The alpha BMP header declares sRGB as a portable export convention, using the
[documented LogicalColorSpace value](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-wmf/eb4bbd50-b3ce-4917-895c-be31f214797f).
It does not infer camera calibration or transform the samples. Native/viewer alpha
compositing behavior is outside this offline artifact contract.

Existing grayscale/RGB PNG and 24-bit BMP encoding paths retain their wire bytes.
Authored compatibility checks retain known artifact hashes, alongside independent
PNG CRC/decompression and BMP mask/row decoding tests.

## Limits and failure behavior

Dimensions remain 1..4096. Per-raster image_limit still defaults to and cannot
exceed 16 MiB; images and pending successful captures share the existing 64 MiB
raw-data limit. The full channel-aware byte sizes are checked before decoding hex
or admitting the next image. Failed capture replies carry no raster and consume
no raw-data capacity.

An alpha BMP may be larger than its raw input, particularly after grayscale-alpha
expansion. Its complete encoded size is checked against the destination limit
before expanded rows are allocated. PNG checks the final encoded size under the
existing file contract. File/virtual-volume limits and obsolete-byte accounting
remain unchanged.

Invalid data, budget exhaustion, busy files, insufficient output capacity and
failed atomic publication preserve the previous output and stored pixels under
the existing [vision image service rules](vision-image-services.md). Exporting
changes no capture queue or logical camera/display state. Reloaded context retains
consumed-capture lifetime and the remaining supplied bytes; it does not synthesize
new capture replies.

The [authored alpha image tests](../tests/test_vision_alpha_images.py) cover
capture/find/save/reload, transparent and intermediate samples, binary layouts,
actual raw quota boundaries and output failures without a GUI preview. This is a
portable supplied-raster feature, without native FANUC image-format, live camera,
controller or strict-mode acceptance claims.
