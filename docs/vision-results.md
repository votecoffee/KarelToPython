# Supplied vision results

Pythonic mode supports 53 vision calls through an explicit `VisionServices`
service. The service consumes supplied completed runs and stores vision results,
registers and parameter edits. It opens no camera or controller connection and
performs no image processing. Generated programs use the same service through
Python and the CLI. The ten [image/device calls](vision-image-services.md) add
explicit rasters, image export, reader and view-line results, and logical devices.
Twelve [legacy tracking calls](vision-tracking.md) add timed queues, allocation
receipts, lookup/result forms, supplied point maps and a local outbox. Twelve
[VT queue calls](vt-queues.md) add allocation, PATH editing, routing and estimates.

```sh
python -m karel2py examples/vision_results.kl -o vision_results.py
python vision_results.py --context examples/vision_results.services.initial.json --state-out vision-state.json
```

See [vision_results](../examples/vision_results.kl),
[vision_parameters](../examples/vision_parameters.kl) and the
[linked project](../examples/vision_project/main.kl) for complete authored inputs.

## Calls and results

| Calls | Pythonic behavior |
| --- | --- |
| `V_RUN_FIND(process,view,status)` | Consume the next matching supplied completed run. |
| `V_CSAPI_TESTRUN(process,view,status)` | Consume a run using the current CSAPI edits. |
| `V_GET_FOUND(process,frame,model,encoder,offset,positions,measurements,status)` | Read the next result into checked outputs and advance the cursor. |
| `V_GET_OFFSET(process,register,status)` | Read the next result into a vision register and advance the same cursor. |
| `V_GET_PASSFL(process,register,status)` | Store the supplied inspection flag, INTEGER 0/1/2, in a numeric register. |
| `V_GET_VPARAM(process,0,view,register,status)` | Store the number of found results for that selection as a REAL numeric register. |
| `V_SET_REF(process,status)` | Store an independent copy of the highest supplied-score result as the process reference. |
| `IRVU_VRGETMEAS(register,measurement,value)` | Read a REAL measurement and return INTEGER status. |
| `IRVU_VRGETOFFSET(register,offset,frame,comment)` | Read XYZWPR offset, frame and comment; return INTEGER status. |
| `IRVU_VRGETVIEW(register,view,position,model)` | Read that view's XYZWPR position/model; return INTEGER status. |
| `VREG_OFFSET(register,position_register,status)` | Copy the offset into the calling root's position-register group. |
| `VREG_FND_POS(register,view,position_register,status)` | Copy the selected found position into that group. |
| `V_ADJ_2D(register,x,y,status)` | Add finite X/Y adjustments, preserving other stored fields. |
| `V_CSAPI_GETVALUE(process,parameter,value,status)` | Read a saved parameter or its current CSAPI edit. |
| `V_CSAPI_SETVALUE(process,parameter,value,status)` | Set a temporary CSAPI edit for a declared parameter. |
| `V_CSAPI_NUMSET(process,count,status)` | Return the number of distinct edited parameters in a REAL output. |
| `V_CSAPI_RESETDATA(process,status)` | Clear the CSAPI edits. |
| `V_CSAPI_SAVEDATA(process,status)` | Commit the CSAPI edits to the saved parameter bank, then clear them. |
| `V_OVERRIDE(name,value,status)` | Set a declared one-shot override binding for the next accepted run. |

The three IRVU calls accept direct built-in syntax or the exact documented
INTEGER-returning declarations `FROM IRVUTILVR`, with unsized STRING in the
OFFSET wrapper. Those declarations lower to
checked service calls. Wrong signatures and duplicate declarations are rejected.
Local routine implementations and declarations from other owners keep ordinary
routine linkage and precedence. Native binary libraries are never loaded.

The manual's `V_CSAPI_NUMSET` parameter table labels `num_values` as input, while
its purpose/details describe a returned count. This implementation follows the
purpose/details and requires a writable REAL output. The discrepancy remains
recorded in the [semantic ledger](semantics/vision_result_semantics.json).

## Optional camera and measurement data

A supplied result can have an empty `views` mapping when only the workpiece
pose is known. Sparse measurement lists accept JSON `null` for unknown entries.
GET_FOUND and VT_GET_FOUND leave corresponding output elements unchanged;
IRVU_VRGETMEAS returns unavailable for an unknown element. These explicit service
inputs do not permit ordinary reads of uninitialized source storage. All-view
result counts include workpieces with no camera observations.

## Supply completed runs

Python construction accepts complete runtime XYZWPR objects. JSON uses the
existing typed value representation, for example an offset has `type: ["XYZWPR"]`
and a `value` object containing X/Y/Z/W/P/R and complete CONFIG_DATA. No
configuration, frame, model, calibration or camera values are acquired.

A minimal process without workpieces can be configured as follows:

```json
{
  "vision": {
    "count": 10,
    "processes": {
      "INSPECT": {
        "views": [1],
        "parameters": {"GAIN": 1.5},
        "runs": [
          {"camera_view": -1, "status": 0, "results": [], "pass_flag": 1}
        ]
      }
    },
    "overrides": {
      "CAMERA_GAIN": {"process": "INSPECT", "parameter": "GAIN"}
    }
  },
  "numeric": {"count": 2, "values": {}}
}
```

Names are case-insensitive printable ASCII, 1..254 characters, with duplicate
spellings rejected. Each process requires explicit distinct `views` from 1..4
and a `runs` list. Each batch requires `camera_view`, `status` and `results`.
Batch selections are -1 for all configured views or a configured positive view.
A nonzero completion status requires an empty result list. Optional `pass_flag`
is exactly INTEGER 0, 1 or 2; an absent flag remains unknown.

`V_RUN_FIND` and `V_GET_VPARAM` accept -1 for all views, a configured positive
view, or 0 for a process with only one configured view. `V_CSAPI_TESTRUN` also
accepts 0 for all views, following its documented numbering. A batch must match
the selected view set. Invalid selections leave it queued; an exhausted queue
raises an explicit runtime error. The service never invents a successful find.

Accepted executions consume one batch, replace the active result set, reset its
cursor and clear that process's one-shot overrides, including on a supplied
nonzero completion status. Old results cannot leak through a failed new run.
Pythonic execution makes the supplied completion visible synchronously. It does
not model asynchronous image-processing time or a getter waiting for a camera.

Each found result requires `offset` and nonempty `views`. Views use canonical
keys `"1"`..`"4"`, each containing `position` and INTEGER `model`. Optional result
fields are `frame`, `model`, signed `encoder`, `measurements`, `comment` and
`score`. Missing metadata defaults to 0, an empty measurement list/comment and
score 0. Frames and model IDs are nonnegative. Results outside the batch's
selection are rejected. Scores are supplied finite numbers; score ties retain
supplied order. Reference selection reads the complete active result set and
does not change its cursor or recompute offsets.

## Checked outputs and register transfers

`V_GET_FOUND` requires one-dimensional ARRAY OF XYZWPR and ARRAY OF REAL
resources, plus exact scalar/XYZWPR output storage. Each view writes its actual
one-based index, including sparse views. Measurements write only their supplied
prefix, up to ten elements. Unpopulated elements remain unchanged, including
unknown tails. Insufficient array capacity returns status 3 before changing any
ordinary output or advancing the cursor.

All output/resource references must be disjoint. An offset destination inside
the positions array, repeated scalar destinations, protected storage, incorrect
types and active FOR counter outputs retain the existing compiler/runtime guards.
Complete supplied poses and every destination are checked before publication or
result consumption. Ordinary failures retain outputs and cursor positions.

Vision registers use addresses 1..`count`, default count 10 when the service is
explicitly supplied. They retain independent copies of all result fields. View
and measurement reads do not consume results. Comments truncate to the output
STRING capacity. `V_ADJ_2D` adds X/Y in the supplied offset coordinates; it applies
no frame/angle transform. Vision position transfers require an explicit
`PositionRegisters` bank. Numeric transfers require `NumericRegisters`.
Neither modifies current robot pose, joints, frame or tool state.

## Parameter lifetime and saved state

`parameters` contains saved REAL parameter values. `overwritten` contains
persistent CSAPI edits until reset or save. Repeatedly editing one name counts
once. TESTRUN captures those edits; RUN_FIND uses saved values. Neither operation
silently commits or clears CSAPI edits.

`V_OVERRIDE` uses explicit global `overrides` bindings to one process/parameter.
Its values live in that process's separate `temporary` mapping. Both execution
calls apply those values after their ordinary parameter selection and clear them
only when a matching run is accepted. Other processes' overrides remain intact.
CSAPI GETVALUE reports CSAPI/saved values, independently of one-shot overrides.
The captured effective parameters are retained in the active run for inspection;
changing them does not recalculate supplied workpiece results.

Context JSON preserves registers, remaining batches, active results/cursors,
references, saved/edited/one-shot parameters and bounded request history.
It stores data only. Reloading does not rerun consumed batches, restore a native
session or discard parameter edits. Supply new batches explicitly for repeated
execution. History is a ring of 1..4096 rows, default 500, with a finite sequence
counter that fails before mutation on exhaustion. Processes and parameter maps
are limited to 256 entries; each process has at most 4096 queued batches and the
service at most 4096 queued/active workpiece rows and process batches. Image,
view-line and reader data have additional [explicit bounds](vision-image-services.md).
All numbers must be finite.

| Status | Meaning |
| --- | --- |
| 0 | Completed offline operation |
| 1 | Value, completed run or inspection flag is unavailable |
| 2 | Invalid/unconfigured process, register, group, view or parameter selector |
| 3 | Result output array is too short |
| 4 | Parameter or override binding is not configured |
| 12311 | Selected camera view is not populated in the vision register |
| 117151 | No more found results |

12311 and 117151 are documented native values for those specific cases. Other
statuses and all supplied failure completions are portable choices, without
native alarm classification. Supplied [image/reader/view-line data and logical
device calls](vision-image-services.md) now have offline forms. Live acquisition,
calibration computation, pixel/edge extraction, native graphics, undocumented
image-save overloads and native conveyor tracking remain open. Legacy queues,
VT results/lookups and supplied maps now have [offline forms](vision-tracking.md);
the remaining VT allocation, flow/time, PATH editing and load-balancing calls
remain unregistered.
