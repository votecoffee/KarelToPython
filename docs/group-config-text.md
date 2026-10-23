# Group-specific CONFIG text

Pythonic mode supports `CNV_CNF_STRG(source,target,status[,group_no])` using
explicit `ConfigTextFormats` profiles. Each profile selects CONFIG flags and turn
numbers for one group. This is an offline field-selection convention; it does
not discover a controller's configuration mask or validate robot configurations.

```karel
CNV_STR_CONF('F L U T,-1,0,2',cfg,code)
CNV_CNF_STRG(cfg,text,code,2)
```

## Profiles

Supply profiles in an execution context:

```python
from karel2py import runtime as rt

formats = rt.ConfigTextFormats({
    1: {"flags": ["flip", "left", "up", "front"], "turns": [1, 2, 3]},
    2: {"flags": ["flip", "up", "front"], "turns": [1, 3]},
})
context = rt.ExecutionContext(config_text=formats)
# Pass context=context when constructing the generated Program.
context.save("context.json")
```

Group 2 formats the example as `F U T, -1, 2`. Flags always appear in
flip/left/up/front order, with the corresponding N/F, R/L, D/U and B/T choices.
Selected turns follow in numeric order, separated by comma-space. A profile with
no flags emits only its selected turns; a profile with both lists empty emits an
empty STRING. Formatting can omit data, so masked text need not round-trip
through `CNV_STR_CONF`.

Group numbers are explicit INTEGER values in 1..32767. Flags and turns must be
unique known names/numbers. Constructor inputs and exported JSON are detached
copies. JSON uses canonical string keys for groups and lists for both fields:

```json
{"config_text": {"2": {"flags": ["flip", "up", "front"], "turns": [1, 3]}}}
```

The optional fourth argument selects that group's profile. When omitted, the
calling root task's group is used; an unqualified root uses group 1. This includes
calls through linked source routines. The selected group still requires a
supplied profile. A lone profile for group 2 does not become a default for group 1.

## Outputs and failure behavior

The source must be a complete, checked CONFIG, including fields omitted by its
profile. It is captured before evaluating target/status selectors. All arguments
evaluate once in source order, with the group expression last.

Status is 0 on success. An unconfigured group returns the portable status 1
(`runtime.CONFIG_TEXT_GROUP_MISSING`) and leaves target text unchanged. Missing
formatting context, malformed/uninitialized CONFIG data and insufficient STRING
capacity raise `KarelRuntimeError` without changing conversion outputs. Earlier
argument effects remain. Formatting never truncates its result.

The output STRING and exact INTEGER status require ordinary writable references.
Existing read-only, alias, active FOR-counter and transitive effect checks remain.
Internal routines with the same name retain their own signatures and effects.
The older context-free `CNV_CONF_STR` continues to emit all seven CONFIG fields.

Reports include source-located `service_operations`, `group_config_text_policy`
and normal routine effects. Runtime service observations record operation, line
and outcome without recording configuration values.

## CLI workflow

Create an ignored local output directory, then translate the authored example:

```sh
python -c "from pathlib import Path; Path('.local').mkdir(exist_ok=True)"
python -m karel2py examples/group_config_text.kl -o .local/group_config.py
python .local/group_config.py --context examples/group_config_text.services.initial.json
```

The runtime package must be installed or available on the Python import path.
The generated script also supports `--state-out` to save profiles and global
values in a fresh execution-context snapshot.

## Reference and evidence

MARRC75KR07091E Rev N, PDF pages 337-338, documents CONFIG input, STRING/status
outputs, optional group selection and sufficient target capacity. The example on
page 338 omits the status argument shown by the signature. This implementation
uses the documented three/four-argument signature and requires writable status.
Native masks and error codes remain unspecified here; profiles and missing-group
status are explicit portable choices.

The [new ledger](semantics/group_config_text_semantics.json) supersedes the
CNV_CNF_STRG exclusion in the historical context-free CONFIG ledger. Authored
tests and CLI checks establish offline behavior, without controller acceptance.
