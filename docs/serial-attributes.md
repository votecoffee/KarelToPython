# Offline serial attributes

GET_PORT_ATR and SET_PORT_ATR are functions returning INTEGER status. They use an
explicit SerialPorts service, independently of digital/group/analog PortBank,
FILE attributes and actual operating-system serial ports.

```python
from karel2py import runtime as rt

bank = rt.SerialPorts({2: {"ATR_BAUD": 9600}})
context = rt.ExecutionContext(serial_ports=bank)
assert bank.read(2, rt.SERIAL_CONSTANTS["ATR_BAUD"]) == (0, 9600)
```

`status = GET_PORT_ATR(port_id, attribute, value)` writes the exact INTEGER value
output on success. `status = SET_PORT_ATR(port_id, attribute, value)` updates a
configured port after validating the complete setting. Port IDs PORT_1..PORT_5
are supported. An empty configured port has no inferred attribute defaults.

| Attribute | Portable values |
| --- | --- |
| ATR_READAHD | 0..32767 units of 128 bytes; no buffer is allocated |
| ATR_BAUD | BAUD_1200, BAUD_2400, BAUD_4800, BAUD_9600; represented by the baud rate |
| ATR_PARITY | PARITY_NONE=0, PARITY_ODD=1, PARITY_EVEN=2 |
| ATR_SBITS | SBITS_1=1, SBITS_15=15, SBITS_2=2; 15 denotes the 1.5-stop-bit choice |
| ATR_DBITS | DBITS_5..DBITS_8, represented by the number of bits |
| ATR_XONOFF | XF_NOT_USED=0 or XF_USED=1 |
| ATR_EOL | ASCII code 0..127 |

Attribute IDs and constants are package identifiers; native enum equality is not
claimed. ATR_EOL remains the same portable constant used by FILE attributes,
while the services retain separate state. The report's `serial_attribute_policy`
lists the complete constant mapping.

Function return 0 means success, 1 an unset attribute, 2 an unconfigured port and
3 an invalid attribute/value. Failed reads preserve the attribute output; failed
writes preserve settings. Missing services and invalid ordinary argument types
raise before publishing output. Inputs/selectors evaluate once in source order,
and existing writable-output, counter and user-routine precedence rules apply.

Host `read(port, attribute)` returns `(status, value)`; `write(port, attribute,
value)` returns status. `to_config()` creates a detached canonical mapping;
`from_config()` rejects unknown/duplicate attributes and invalid values. Context
JSON uses `serial_ports`, mapping canonical string IDs `"1"`..`"5"` to named
attribute mappings. It persists settings without opening devices or allocating
resources.

The [authored example](../examples/serial_attributes.kl) sets and reads all seven
attributes, using an [explicit initial bank](../examples/serial_attributes.services.initial.json).
The [semantic ledger](semantics/serial_attribute_semantics.json) records manual
provenance and portable choices. There is no COM-port discovery, serial data
transfer, physical I/O or controller validation.
