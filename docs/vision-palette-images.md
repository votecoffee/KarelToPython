# Explicit palette vision images

Pythonic VisionServices accepts an optional palette on explicitly supplied
single-channel image records. With `palette` present, each pixel byte is an
unsigned palette index. Without it, channels=1 retains its existing grayscale
meaning. No palette, grayscale conversion or camera acquisition is inferred.

```json
{
  "width": 2,
  "height": 1,
  "channels": 1,
  "pixels": "0001",
  "palette": "ff00008000ff0000"
}
```

This image contains index 0 and index 1. Palette entry 0 is red with alpha 128;
entry 1 is green with alpha 0. The palette is one packed sequence of RGBA bytes,
with exactly four bytes per entry and 1 through 256 entries. Opaque colors require
an explicit alpha byte of ff. RGB triplet palettes and other layouts are not
guessed. Unused and duplicate entries are retained.

Python callers may supply immutable `bytes` for pixels and palette. JSON uses
canonical lowercase hexadecimal strings without whitespace or prefixes. Lists,
mutable byte arrays, nested palette objects and separate palette-layout fields
are rejected. A palette requires channels=1; grayscale-alpha, RGB and RGBA images
retain their existing packed-sample contracts. Every index must be less than the
entry count. Invalid indexes fail instead of clipping or selecting a fallback
color.

## Registers, captures and limits

The existing image-record wrapper still binds each supplied image to a process
and configured views. Image registers, successful capture replies, image-bound
finds and context snapshots preserve dimensions, index bytes and the exact RGBA
palette. Capture inputs and saved configuration dictionaries are detached from
the caller's mutable metadata. Failed captures keep their existing reply/queue
behavior and carry no image.

Dimensions remain 1..4096. The per-image `image_limit` defaults to and cannot exceed
16 MiB. It counts **pixel index bytes plus all RGBA palette bytes**, including
unused entries. Images and pending successful captures also share the existing
64 MiB combined raw budget on that basis. Size admission checks precede decoding
either hex string or allocating decoded pixel buffers. Canonical schema and
bounded palette lengths are checked before decoding. No capacity is inferred
from compressed export sizes or shared immutable Python objects.

Image-bound finds consume supplied completed vision results; they do not inspect
pixels, search colors or generate new findings. Exporting changes no stored
palette, capture queue, camera configuration or display state.

## Indexed PNG export

V_SAVE_IMREG selects PNG from the existing filename suffix. Palette PNGs use
8-bit indexes, color type 3, filter-zero rows and the existing noninterlaced zlib
path. PLTE contains the palette's RGB triplets in the original order. If any entry
is not fully opaque, a following tRNS chunk contains one alpha byte for every
palette entry; otherwise tRNS is omitted. IDAT contains the original indexes,
without color expansion or packed sub-byte indexes. These choices follow the
[W3C PNG PLTE rules](https://www.w3.org/TR/png-3/#11PLTE) and
[tRNS rules](https://www.w3.org/TR/png-3/#11tRNS).

Colors remain independent of alpha, including nonzero RGB values below alpha
zero. No premultiplication, color quantization, background flattening or palette
reordering occurs. Palette chunk overhead is included in the minimum-output-size
check before row work. The complete encoded PNG must also fit the destination's
file limit before publication.

## BMP export

Palette BMP export always expands index bytes to the existing 32-bit alpha BMP
format, including for fully opaque palettes. It does not produce an indexed BMP.
The 108-byte BITMAPV4HEADER, pixel offset 122, BI_BITFIELDS and explicit RGBA masks
retain the existing alpha export convention. Bottom-up BGRA pixels preserve every
palette color and alpha value, using the documented
[Microsoft BITMAPV4HEADER fields](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapv4header).

The complete expanded BMP size is checked before lookup-table/row allocation or
row callbacks. The existing sRGB header convention does not infer camera color
calibration or transform samples. Viewer compositing and native FANUC file
formats remain outside this offline artifact contract.

## Publication and compatibility

The existing checked V_SAVE_IMREG publication path remains: invalid images,
budget exhaustion, busy outputs, insufficient file/device capacity and failed
atomic directory publication preserve prior output and stored image data.
DeviceFiles replacement still charges retained old bytes under its existing
volume policy. Context JSON saves canonical palette and pixel hex; reload keeps
the remaining capture queue and consumed-capture lifetime.

Nonpalette grayscale, grayscale-alpha, RGB and RGBA PNG/BMP wire bytes are
unchanged. The authored tests retain eight pre-change artifact hashes, independent
PNG CRC/chunk/index-row decoding, BMP mask/color/row checks and image-service
lifetime/error cases. See `tests/test_vision_palette_images.py`,
[alpha images](vision-alpha-images.md) and the existing
[vision image service](vision-image-services.md). No GUI preview, image processing,
live camera, native controller or public strict-mode support is added.

Palette indices remain eight-bit even when nonpalette images use explicit
[16-bit samples](vision-16bit-images.md). The latter use direct grayscale/GA/RGB/RGBA
PNG encodings; this does not add 16-bit palette entries or inferred image layouts.
