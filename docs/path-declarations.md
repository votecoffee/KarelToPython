# PATH declarations and predefined records

Pythonic declarations accept `PATHHEADER` and its compatibility spelling
`PATHDATA`, with `NODEDATA` in either order. Clauses can be separated by a comma
or whitespace and can continue on physical newlines. A comma must introduce
another clause; it cannot silently consume a following variable declaration.
Duplicate NODEDATA clauses and duplicate headers, including mixed spellings,
are rejected.

```karel
TYPE node_t=STRUCTURE value:INTEGER ENDSTRUCTURE
     header_t=STRUCTURE count:INTEGER ENDSTRUCTURE
     route_t=
       PATH PATHDATA=header_t
            NODEDATA=node_t
VAR track:route_t
```

The manual's A.15.1 PATH section documents PATHHEADER, comma separation and
structure components. Its introductory PATH example also uses PATHDATA.
Accepting that spelling and whitespace separation is a Pythonic compatibility
choice; it is not native compiler acceptance evidence. Reflow after TYPE `=`,
VAR/field `:` and ARRAY `OF` is supported without token fusion or macros.

PATH components must resolve to supported named STRUCTURE layouts. Omitted
NODEDATA uses the portable STD_PTH_NODE layout; omitted PATHHEADER has no
user-accessible header. Header fields use `path.field`, node fields use
`path[index].field`. Existing typed reference/value interfaces, copy/range
operations and nominal layout checks remain. Function PATH results and resource
fields in STRUCTURE remain outside the supported contract.

## Predefined data layouts

Two names now resolve without a preceding user TYPE definition. They use the
existing nominal STRUCTURE schema, so declarations, transparent aliases, nested
fields, ARRAY elements, routine parameters/results and collection components
follow ordinary checked structure behavior. Predefined type names cannot be
redeclared as variables, constants, routines or user types.

| Type | Portable layout |
| --- | --- |
| DISP_DAT_T | SHORT arrays WIN_START[4], WIN_END[4], CURS_ST_COL[10], CURS_EN_COL[10]; SHORT scalars CURR_WIN, CURSOR_ROW, LINS_PER_PG, CURR_FIELD, LAST_FIELD, CURR_IT_NUM, SOB_IT_NUM, EOB_IT_NUM, LAST_IT_NUM and MENU_ID. |
| STD_PTH_NODE | NODE_POS: POSITION. GROUP_DATA and COMMON_DATA association fields are omitted. |

DISP_DAT_T follows the documented A.4.27 field names, order and sizes: 38 SHORT
leaves. Known values follow the existing SHORT range and 32767 missing sentinel;
fields start uninitialized. The manual permits MENU_ID to remain uninitialized,
which is supported for field operations and partial saved state. Whole value
copies/results still require every leaf initialized under existing Pythonic
structure rules. The separate [list/table service](table-controls.md) now uses
DISP_DAT_T for resident field/row navigation. Native windows, memory layouts and
controller display validation remain outside the implementation.

STD_PTH_NODE exposes the same NODE_POS POSITION field already used for implicit
PATH nodes. A.18.47 lists GROUP_DATA and COMMON_DATA as no longer used; their
native association layouts are not inferred. POSITION initialization, conversion
and recursively protected orientation fields retain their normal rules. No
native group association, automatic UFRAME/UTOOL recording or new motion behavior
is added.

NODE_SIZE reports the existing portable packed sizes: 76 bytes for DISP_DAT_T
and 64 for the modeled STD_PTH_NODE. These are prototype sizes rather than native
alignment or binary ABI claims.

## Interfaces, creation and persistence

`PATH NODEDATA=STD_PTH_NODE` and aliases of that predefined type normalize to the
same schema as a PATH omitting NODEDATA. This preserves existing default-node
context files and permits equal typed routine/copy interfaces. Distinct user
structure names, header types, capacities and shapes still require exact matches.
Source-linked TYPE aliases and external routines use the same resolved layouts.

[Dynamic collection creation](dynamic-collections.md) also accepts root PATH and
supplied PATH aliases, preserving checked NODEDATA/PATHHEADER layouts and
allocating only the empty descriptor/header at creation.

CREATE_VAR recognizes DISP_DAT_T and STD_PTH_NODE, plus the portable
[COL_DESC_T and opaque XWORK_T schemas](table-controls.md), including supported
fixed ARRAY dimensions. It retains existing allocation, dimension, memory-pool,
metadata and schema validation. GET_VAR/SET_VAR use their existing exact service
interfaces. For example, a DISP_DAT_T SHORT field must be read into SHORT field
storage; it is not silently promoted into an INTEGER service output. An ordinary
INTEGER assignment can then read that field.

```karel
VAR result:DISP_DAT_T entry_no,status,seen:INTEGER
-- Inside BEGIN:
CREATE_VAR('CACHE','DISPLAY','','DISP_DAT_T',0,0,0,0,status)
SET_VAR(entry_no,'CACHE','DISPLAY.curr_it_num',42,status)
GET_VAR(entry_no,'CACHE','DISPLAY.curr_it_num',result.curr_it_num,status)
seen=result.curr_it_num
```

Context JSON and portable VR archives retain the existing STRUCTURE/PATH tuple
schemas. Partial fields, exact array shapes, nominal identities, SHORT missing
markers and POSITION protections survive supported round trips. There is no new
state format or native VR/PC codec. Existing explicit-binding precedence and
saved-state matching rules continue to apply.

## CLI examples and reports

```sh
python -m karel2py examples/path_declarations.kl --check
python -m karel2py examples/path_declarations.kl -o path_declarations.py --report path_declarations.report.json
python path_declarations.py
python -m karel2py examples/predefined_records.kl -o predefined_records.py
python predefined_records.py
python -m karel2py.project examples/path_declarations_project --entry MAIN
```

The linked project combines TYPE FROM aliases, a shared PATH, equivalent header
spellings and an external routine receiving PATH and DISP_DAT_T arguments.

`path_clause_uses` records original/canonical clause names and physical source
origins, including included files. `predefined_structure_uses` records each
resolved predefined name; `predefined_structures` provides the used schemas.
`path_declaration_policy` and the [semantics ledger](semantics/path_declaration_semantics.json)
describe accepted forms and boundaries. No native compiler, controller UI,
recording, storage layout or runtime equivalence is claimed; strict mode remains
future work.
