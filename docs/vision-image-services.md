# Vision images and logical devices

Pythonic mode adds ten calls over supplied pixels, reader strings, view lines
and logical device state. Use the [core vision guide](vision-results.md) for
result/register calls and parameter lifetime. Every call requires an explicit
`VisionServices`; image and device calls also require its `io` configuration.

```sh
python -m karel2py examples/vision_image_io.kl -o vision_image_io.py
python vision_image_io.py --context examples/vision_image_io.services.initial.json --state-out vision-image-state.json
```

The output state contains the image registers and virtual output files. To write
ordinary files to disk, select an explicit existing root with `--filesystem-root`.
The generated script uses the same bounded file backends as other FILE services.

## Calls

| Source form | Pythonic equivalent |
| --- | --- |
| `V_SNAP_VIEW(process,view,image_register,status)` | Consume one matching supplied capture reply and store its pixels. |
| `V_FIND_VIEW(process,view,image_register,status)` | Consume a completed find batch explicitly bound to that image register. |
| `V_FIND_VLINE(process,1,image_register,path,status)` | Replace the documented view-line PATH from supplied line data. Nonpositive image register means an inline supplied completion. |
| `V_SAVE_IMREG(image_register,filename,status)` | Encode supplied pixels as PNG or BMP into an explicit file backend. |
| `V_GET_READ(process,string_register,filename,length,status)` | Copy the active reader result into a string register, or a file when the register is zero. |
| `V_CAM_CHECK(camera,powered,status)` | Read a supplied BOOLEAN power observation and status. |
| `V_CAM_CALIB(calibration,function,status)` | Consume a matching supplied calibration reply and retain it as `last`. |
| `V_DISPLAY4D(tool,status)` | Record the selected configured tool in headless state. |
| `V_LED_ON(channel,intensity,status)` | Set one configured logical multiplexer LED. |
| `V_LED_OFF(status)` | Clear its active logical LED. |

These operations acquire no pixels, power observations or calibration from
hardware. Find results and view lines are supplied data, independent of the
pixels. Parameter changes are captured for inspection; they do not recalculate
those results. Calibration replies acknowledge supplied outcomes and do not
compute camera geometry. Display requests open no GUI or native graphics window.
LED state causes no hardware output.

## Image configuration and capture lifetime

Configure `vision.io` alongside the ordinary `vision.processes` map:

```json
{
  "image_count": 2,
  "captures": [
    {
      "process": "SCAN",
      "views": [1],
      "status": 0,
      "image": {
        "width": 2,
        "height": 1,
        "channels": 3,
        "pixels": "ff000000ff00"
      }
    }
  ],
  "cameras": {"CAMERA": {"powered": true}},
  "calibrations": {
    "GRID": {"responses": [{"function": 1, "status": 0}]}
  },
  "display_tools": {"SCAN": 0},
  "led_channels": [1, 2]
}
```

`SCAN` must exist in `vision.processes` with the configured view. Image register
addresses are 1..`image_count`, with zero configured registers by default. The
count is bounded at 256. Initial `images` use canonical positive string keys and
the same process/views/image fields as a successful capture, without `status`.

Images contain top-to-bottom packed grayscale (`channels:1`), grayscale-alpha
(`channels:2`), RGB (`channels:3`) or RGBA (`channels:4`) samples. The default
sample depth is 8; explicit [sample_bits=16](vision-16bit-images.md) uses two
big-endian bytes per sample. JSON pixels are canonical lowercase hex; Python
construction can also supply immutable bytes. Dimensions are 1..4096 and must
exactly match the pixel count. Each raster is limited by `image_limit`, default
16 MiB and maximum 16 MiB; combined stored/capture raster data is at most 64 MiB.
Alpha samples and colors under zero alpha are preserved without premultiplication.
[Explicit palettes](vision-palette-images.md) add indexed rasters with supplied RGBA
tables, counted together with index bytes in raw limits. Depth maps, color
transforms and proprietary camera formats remain open.

Capture replies form one ordered queue, at most 4096 entries. They name an
explicit process and nonempty distinct configured views. Only successful replies
contain an image. A matching request consumes the reply once, including a supplied
failure status. Failed replies preserve the previous image. Invalid selections,
addresses and mismatched requests retain the queue. A missing reply raises an
explicit error; there is no automatic frame generation or replay.

FIND_VIEW requires an existing image with the same process and coverage of the
selected views. Its next completed process batch must have `image_reg` equal to
the requested register, a matching camera selection and ordinary find operation.
An unbound batch cannot be borrowed by an image find, and RUN_FIND/TESTRUN cannot
consume image-bound or line batches. Accepted finds share the ordinary active
result set/cursor and consume that process's one-shot overrides. Supplied
nonzero completion statuses replace old active results, preventing stale success.

## Image export and files

The supported `V_SAVE_IMREG` form has three parameters: image register, output
path and INTEGER status. This follows the parameter table and stated purpose.
The manuals also show an unexplained `not_zip` argument, rename `output_path` to
`value` in syntax, and add an iPC argument in a newer edition. Their type/default
and routing contract are incomplete in the supplied references. Four/five-argument
forms are rejected; no compression flag or iPC connection is guessed.

Filename suffixes `.PNG` and `.BMP` are case-insensitive. PNG export uses the
supplied 8/16-bit depth, noninterlaced grayscale/truecolor with optional alpha,
filter zero and zlib compression. [BMP from 16-bit samples](vision-bmp-samples.md)
uses explicit per-component rounding to eight bits, including alpha; source
samples and PNG output retain full precision.
Existing grayscale/RGB BMP export retains bottom-up 24-bit BGR rows with padding.
Alpha BMP uses 32-bit BGRA, a V4 header and explicit bit masks; grayscale-alpha
replicates gray into RGB while retaining alpha. See [alpha images](vision-alpha-images.md).
No native image metadata or calibration is
inferred. These are portable encodings, following the
[PNG specification](https://www.w3.org/TR/png-3/) and Microsoft's
[BMP file header](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapfileheader)
and [bitmap information header](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/ns-wingdi-bitmapinfoheader).

Exports replace a whole file through exact MemoryFiles, DeviceFiles or explicitly
rooted DirectoryFiles backends. Open targets, file-size/quota limits, unmapped
volumes, read-only/unmounted devices, missing parents and invalid rooted paths
retain their guards. Directory writes use atomic replacement; failures preserve
the old file and do not publish a new cached value. Virtual FROM volumes account
for obsolete replaced bytes. Encoding and view-line staging obey the source step
budget before publication. No file is truncated through an intermediate OPEN.

## Reader and view-line results

A successful completed batch can supply `read_result`, up to 65535 ASCII
characters. An absent result is unknown; an empty string is a known empty result.
Reader lookup is repeatable and does not advance the found-workpiece cursor.

For positive string-register numbers, the destination bank must exist. Text
truncates to its configured capacity and `length` reports the stored length.
The filename is ignored in this form. Register zero selects the file backend,
which receives the complete ASCII bytes without an added newline; length reports
that byte count. Negative/invalid registers, absent results and write failures
preserve the ordinary length output. `V_GET_READ` does not require `vision.io`.

A view-line batch has `operation:"lines"`, `camera_view:1`, an empty ordinary
`results` list and, on success, `view_lines` with `group`, `frame`, `focal` and
`nodes`. Each node has three-number `direction` and `polarity` vectors plus a
nonnegative `model`. Vectors must be finite, with nonzero direction/polarity
lengths. Supplied group/frame coordinates are preserved; no camera transform is
computed. At most 4096 lines are accepted per batch.

The target PATH must have the documented field schemas already accepted by
[INTSCT_VL_PL](path-geometry.md): GRP_NUM/UFRM_NUM/FOCAL_POINT in its header and
DIR/POL/MODEL_ID in each node. Authored type names are allowed. Successful line
finds replace all nodes and update the existing header storage; failed finds
preserve the PATH. Type, overlap and step-budget guards run before consuming the
batch. Header/status overlap is rejected. See the authored
[view-line example](../examples/vision_view_lines.kl) for both inline and stored
image forms feeding plane intersections.

## Logical devices and persistence

Camera entries require an explicit BOOLEAN `powered` value on status zero.
Nonzero camera status can omit the observation and preserves the output value.
Calibration entries contain ordered `responses`, each with positive `function`
and INTEGER `status`. Functions must match the next reply; the service does not
infer a calibration type. Accepted success/failure replies are consumed once
and recorded as `last`. Missing replies raise errors.

`display_tools` maps known names to supplied statuses. Status zero updates
`displayed`; failure leaves the old selection intact. LED channels are explicit,
distinct IDs 1..8, with intensities 1..16. Turning on a second channel replaces
the first. OFF is idempotent when a multiplexer is configured; absent channel
configuration returns status 2.

Context JSON retains pixels, image ownership/view coverage, remaining captures,
line/reader completions, logical device state and calibration replies. It restores
no executable callback, live camera, native graphics or suspended image-processing
session. There are at most 4096 queued/active process batches, 32767 cumulative
queued/active view-line nodes, and 4 MiB of reader strings, in addition to the
existing workpiece/result bounds. Replies and data remain explicitly supplied.

Portable statuses extend the core vision table: 3 is an open/busy file target,
5 a file-size/count limit, and 6 a backend/path/device/quota/write failure.
Statuses 1 and 2 retain unavailable/invalid meanings. Supplied nonzero camera,
calibration and completion statuses pass through. These values and synchronous
completion are offline choices, without native alarm or timing equivalence.
