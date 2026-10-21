# Pythonic numeric registers

Since 0.78.0, Pythonic mode supports `GET_REG`, `SET_INT_REG` and `SET_REAL_REG`
using an explicitly supplied in-memory numeric register bank. A host program
chooses its size and initial values. The translator does not connect to a robot.

```karel
PROGRAM PYTHONIC_NUMERIC_REGISTERS
%ENVIRONMENT REGOPE
VAR code,missing,invalid,value: INTEGER real_flag: BOOLEAN real_value: REAL
BEGIN
  SET_INT_REG(1,42,code)
  GET_REG(1,real_flag,value,real_value,code)
  SET_REAL_REG(2,1.25,code)
  GET_REG(2,real_flag,value,real_value,code)
  GET_REG(3,real_flag,value,real_value,code)
  missing=code
  GET_REG(4,real_flag,value,real_value,code)
  invalid=code
  WRITE('int=',value::0,', real=',real_value::0::2,CR)
END PYTHONIC_NUMERIC_REGISTERS
```

With a three-register bank containing only registers 1 and 2, this writes
`int= 42, real= 1.25` and a newline. The missing third register gives status 1;
the fourth register is outside the explicit count and gives status 2.
The [authored example](../examples/pythonic_numeric_registers.kl) includes
[initial registers](../examples/pythonic_numeric_registers.registers.initial.json),
[final registers](../examples/pythonic_numeric_registers.registers.expected.json),
[program state](../examples/pythonic_numeric_registers.expected.json) and
[output](../examples/pythonic_numeric_registers.write.expected.json) fixtures.

## Supplying a bank

```python
from karel2py import translate
from karel2py.runtime import NumericRegisters

source = """PROGRAM REGISTERS
VAR flag: BOOLEAN value,code: INTEGER real_value: REAL
BEGIN
  SET_REAL_REG(1,0.1,code)
  GET_REG(1,flag,value,real_value,code)
END REGISTERS"""
namespace = {"__name__": "register_example"}
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
bank = NumericRegisters(3, {1: 7})
program = Program(registers=bank)
snapshot = program.run()
assert snapshot["FLAG"] is True and snapshot["REAL_VALUE"] == 0.1
assert snapshot["VALUE"] == {"uninitialized": True}
assert bank.snapshot() == {1: 0.1}
```

`NumericRegisters(count, initial=None)` requires an explicit integer count in
1..32767. This is a prototype resource limit, not a native register-count claim.
Initial values use a dictionary with integer keys in 1..count. Omitted registers
are absent; they do not acquire zero or a guessed controller value. Python `int`
values create INTEGER registers, while `float` values create REAL registers,
including floats such as `7.0`. Boolean and other values are rejected. Ordinary
checked INTEGER storage and finite Pythonic REAL rules apply.

The constructor copies the initial dictionary. `count` is read-only and
`snapshot()` returns a detached dictionary with integer keys. Host `read(number)`
returns `(status, value)`, using `None` on absence/range failures. Host
`write(number, value)` returns status and validates numeric type/range before
mutation. A shared bank retains writes across program runs and can be explicitly
passed to other programs. Create separate banks for independent state. There is
no automatic persistence, copying, rollback or reset of the bank at run start.

`Program(registers=None)` remains valid for programs that never execute these
operations. Executing one without an explicit `NumericRegisters` instance raises
`KarelRuntimeError`. Arbitrary backend objects and subclasses are not accepted.

## Procedures and portable status

| Procedure | Behavior on success |
| --- | --- |
| `GET_REG(number, real_flag, int_value, real_value, status)` | Write BOOLEAN `real_flag`, the selected exact INTEGER or REAL output, and status 0. Preserve the unused numeric output and its initialization state. |
| `SET_INT_REG(number, value, status)` | Store an INTEGER and write status 0. |
| `SET_REAL_REG(number, value, status)` | Store a Python float and write status 0; ordinary numeric input promotion applies. |

Setting a register changes its numeric kind to that of the setter. On a missing
read, write `runtime.REGISTER_UNINITIALIZED` (1) to status and preserve all data
outputs. On an out-of-range read or write, write
`runtime.REGISTER_OUT_OF_RANGE` (2); preserve data outputs and the bank. These two
nonzero codes are portable project conventions and do not map native alarms.

Type, initialization, context, output-reference and overlap failures raise before
the operation changes outputs or the bank. They do not become status 1 or 2.
GET outputs require exact BOOLEAN, INTEGER, REAL and INTEGER storage, even when
one numeric output will be unused. A setter's status requires exact INTEGER.
Variables, nested fields, ARRAY elements and reference formals are supported.
Outputs must be ordinary writable, pairwise-disjoint references; CONFIG scalar
subfields and protected POSITION descendants stay blocked. Active FOR counters
are protected directly and through transitive routine output writes.

Arguments are captured once, left to right, before the operation validates its
outputs and accesses the bank. A later status-index function cannot change a
captured input. Earlier effects remain after an error, including bank writes
from earlier completed statements. Normal routine/FOR cleanup and sticky ABORT
apply. Internal routines with these names retain their own signatures and effects;
ordinary declarations remain usable.

## Generated scripts

Scripts containing these built-ins require an explicit JSON configuration:

```sh
python -m karel2py examples/pythonic_numeric_registers.kl -o converted.py
python converted.py --registers examples/pythonic_numeric_registers.registers.initial.json
```

The JSON contains exactly `count` and `values`, for example
`{"count": 3, "values": {"1": -7, "2": 0.5}}`. Keys are canonical positive decimal
strings within the explicit count. `NumericRegisters.from_config(config)` loads
the same decoded structure for embedding. Invalid files/configurations produce
a command-line error. The file seeds detached memory and is left unchanged.
The script prints program state; embedding code can inspect final bank state.
The `--registers` flag composes with existing explicit READ and pose contexts.

Reports add `register_operations`, `register_policy` and transitive
`potential_register_reads` / `potential_register_writes` routine effects.
`Program.register_requests` returns copied procedure, register number, source
line, read/write operation, status and outcome records. Outcomes are `completed`,
`uninitialized` or `out_of_range`. Records omit register values, reset at run
start and cover completed operations; guard failures have no completed record.

## Evidence boundary

The reviewed [reference edition](references.md), PDF pages 413, 540 and 551,
documents the procedure signatures, real flag, selected output and status zero
for success. The in-memory bank, explicit limits, absent values, unused-output
preservation and portable nonzero statuses are project choices. They do not
establish native register initialization, count, error mapping or persistence.

This is an offline execution context. Real controller access, remote/group
register operations, position/string registers, register comments and `R[]`
syntax remain unsupported. REGOPE is metadata; strict remains a future milestone.
