# Calling attached synchronous source programs

CALL_PROG and CALL_PROGLIN can execute a newly generated ordinary Pythonic Program
alongside existing cooperative targets. Normal output includes a private
`_execute_sync` body. A nested call uses that body with fresh stacks and shared
attached globals, without invoking the target's standalone run/reset/cleanup.

```python
from karel2py import translate, runtime as rt

def compile_program(source, context):
    namespace = {"__name__": "attached_example"}
    exec(translate(source).python_source, namespace)
    Program = namespace["Program"]
    return Program(context=context)

context = rt.ExecutionContext()
target = compile_program(
    "PROGRAM TARGET VAR n:INTEGER BEGIN n=7 END TARGET", context)
caller = compile_program(
    "PROGRAM MAIN VAR entry:INTEGER BEGIN CALL_PROG('TARGET',entry) END MAIN",
    context)
assert caller.run()["ENTRY"] == 1
assert target.snapshot()["N"] == 7
```

Construction attaches explicit source namespaces and executes no source body.
The [standalone target example](../examples/synchronous_target.kl) also runs
normally through generated CLI output. Old normal modules without the private
entry need retranslation; no source discovery or runtime compiler is used to
repair them. Preserved legacy outputs do not gain this Pythonic entry.

## Caller ownership and execution

Calls retain the existing [same-task contract](program-calls.md): shared caller
budget, root identity, observations, active frames, group scopes and global data.
The independently attached target's counters, drive flag and execution cursor are
not reset or driven. Callee return does not release caller-owned resources.
Source effects and the published index hint remain visible on a later failure.
Combined routine/program depth remains bounded at 64.

A synchronous body runs to completion without scheduler yields. Source delays
and READ/WRITE callbacks use inherited caller adapters and complete synchronously.
Use `cooperative=True` when in-body suspension, scheduler interleaving or waiting
input is needed. Automatic cooperative generation for task controls, FILE READ,
handlers and other existing source forms is unchanged. Project inputs remain
cooperative by default.

CALL_PROGLIN pause-entry still suspends before the body, after validation and
index publication. Resume enters the body once; stop before entry skips it.
Callback-injected exceptions cannot create a resumable synchronous stack. A pause
escaping such a body is reported as an execution failure. Runtime errors unwind
frames, and sticky ABORT remains authoritative even if a callback catches it.

Saved context retains values, omitting executable links, hints and call stacks.
Reattach source after loading values. `synchronous_program_call_policy` records
the generated entry, caller ownership and scheduling boundary. Native PC/TP
execution, arbitrary KAREL start lines and controller timing remain unavailable.
