# Supplied VT tray cells

The [offline VT queues](vt-queues.md) can expand a detected tray into explicitly
configured workpiece cells. This is an opt-in Pythonic model. Without a matching
cell configuration, a known nonzero tray ID retains its existing single tagged
part behavior. `VT_PUT_QUE2` still requires tray zero.

The reference manual describes tray IDs in `VT_PUT_QUEUE`, cell editing in
`VT_READ_PQ`/`VT_WRITE_PQ`/`VT_DELETE_PQ`, and sequence-dependent cell ordering.
It delegates native tray patterns and allocation details to a separate PickTool
guide. The composition and sequence choices below are portable conventions;
they do not reproduce a discovered controller setup or native Seq algorithm.

## Explicit cell configuration

Add a `trays` mapping under `vision.tracking.vt`. Keys are canonical positive
tray IDs already present in `vision.tracking.ids.trays`. Each pattern has a
nonempty `cells` list and an optional BOOLEAN `sequenced`, default TRUE.

```json
{
  "3": {
    "sequenced": true,
    "cells": [
      {
        "model": 6,
        "offset": {
          "type": ["XYZWPR"],
          "value": {
            "X": 10.0, "Y": 0.0, "Z": 0.0,
            "W": 0.0, "P": 0.0, "R": 0.0,
            "CONFIG_DATA": {
              "CFG_TURN_NO1": 0, "CFG_TURN_NO2": 0, "CFG_TURN_NO3": 0,
              "CFG_FLIP": false, "CFG_LEFT": false,
              "CFG_UP": false, "CFG_FRONT": false
            }
          }
        }
      }
    ]
  }
}
```

This example is the value of `vision.tracking.vt.trays`, alongside the existing
`lines` and `areas` configuration. The direct Python API also accepts complete
XYZWPR objects for cell offsets. Each cell may override the supplied nonnegative
model ID; omitting `model` inherits the insertion's model. No row/column pitch,
calibration, occupancy or measured poses are inferred.

Every offset must include all pose and CONFIG fields. Entirely unknown and
partially initialized cell poses reject configuration. Limits are 256 patterns,
1..256 cells per pattern and 4096 supplied cells across all patterns.

## Expansion, identity and duplicates

`VT_PUT_QUEUE` prepares the entire batch before modifying the pool. A cell's
result offset is `input_offset:cell_offset`, using the existing
[pose composition convention](frame-transforms.md). Each already-present found
view uses `input_found_pose:cell_offset`; missing views stay absent. A model
override also updates that cell's existing view models. Measurements retain
their supplied values and missing markers. No unknown pose becomes a zero pose.

For example, an input at (1,2,3) with zero rotation and a local cell displacement
(10,0,0) gives a cell at (11,2,3). With input R=90 degrees, the same local
displacement gives (1,12,3). CONFIG follows the existing right-operand pose
composition rule; it is supplied data rather than a native branch selection.

Every cell reserves a distinct internal index. The first reserved index is the
`tray_instance`; `tray_cell` is its one-based position in the configured list.
Cells share the original caller work ID within that instance. The same nonzero
caller ID cannot coexist in a different instance or ordinary part on that line.
GET's work-ID selector can therefore select successive cells from one tray;
READ/WRITE/DELETE continue to use unique internal indexes.

Duplicate checks include pooled and allocated cells. They retain the insertion's
original encoder/model/six-coordinate fingerprint as `tray_origin`, so a repeat
detection is still recognized when every configured cell has a nonzero local
offset. The existing exact-result fingerprint and nonzero caller-ID checks also
remain. There is no calibrated proximity or native duplicate tolerance.

Line/global held-part limits count every cell, including outstanding allocations.
Full batch capacity, nonwrapping indexes, pose calculations, arrival clocks and
routing changes are prepared before commit. Capacity reserves every input cell
even if routing will bypass some cells. Every cell reserves its index even when
bypassed, and consumes one ordinary execution step during preparation. A later
failure retains the pool, indexes, receipts and routing cursors; already charged
execution steps remain charged.

## Allocation and order

Cells use their own model's ordinary weighted routing profile. With `sequenced`
TRUE, first sort the eligible parts by the area's existing encoder/Y rule. Each
tray instance occupies its first position in that order, with its eligible cells
in configured list order. READ_PQ uses the same instance grouping over its
ordinary encoder ordering. With FALSE, cells retain normal encoder/Y ordering.

This grouping applies after area/model/work/target filters. A filtered earlier
cell does not block a later matching cell. GET still considers only arrived
cells, and allocated cells are absent until acknowledged. TIME and PFRT retain
their explicit-clock estimates; PFRT now counts each expanded cell as a
workpiece. There is no historical calibrated flow-region reconstruction.

ACK 1/3 discards only its allocated cell. ACK 2 forwards only that cell, preserving
its instance/ordinal/origin and the adjusted vision-register result. Siblings
keep their own routing and allocations. Clear, pause/resume, timeout, stop and
budget cleanup retain the ordinary VT queue contracts. READ/WRITE/DELETE still
require disabled load balancing and explicit line `tray_edit: true` for tray
entries. A scalar edit does not redefine the cell's instance or original
detection fingerprint.

## Persistence and evidence

Context JSON retains complete pattern offsets, expanded values, nullable data,
instance identities and outstanding allocation receipts. Restore checks cell
ordinals/index arithmetic, configured pattern membership, consistent instance
ownership/origin, unique internal IDs and shared caller-ID rules. Pending GET
requests must finish or stop before saving. JSON remains explicit supplied
state; it does not restore suspended execution or acquire a tray configuration.

The [authored tests](../tests/test_vt_trays.py) cover pose composition, missing
values, per-cell routing, whole-batch failures, allocation/forwarding, PATH edits,
sequence choices, pause/stop cleanup and inconsistent saved metadata. These are
offline results, without controller motion, encoder updates, native status/ABI,
automatic frame transforms, calibration or strict-mode acceptance.
