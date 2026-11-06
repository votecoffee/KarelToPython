# Pythonic POS construction

Since 0.66.0, `POS(x,y,z,w,p,r,c)` constructs a fresh XYZWPR value from six
numeric components and an explicitly initialized CONFIG.
Since 0.67.0, [CONFIG text conversion](config-text.md) offers a shorter way to
initialize all CONFIG fields using a documented portable grammar.

Pythonic mode also accepts `POS(x,y,z,w,p,r,c,ext1,ext2,ext3)`, which constructs
a fresh XYZWPREXT with all three supplied axis values. That form can round-trip
through [UNPOS](pose-decomposition.md) with external-axis outputs.

```karel
PROGRAM CARTESIAN
VAR cfg: CONFIG pose: XYZWPR
BEGIN
  cfg.cfg_turn_no1=0 cfg.cfg_turn_no2=0 cfg.cfg_turn_no3=0
  cfg.cfg_flip=OFF cfg.cfg_left=OFF cfg.cfg_up=OFF cfg.cfg_front=OFF
  pose=POS(.1,2,3,10,-20,30,cfg)
END CARTESIAN
```

The constructor copies cfg into `pose.config_data`. Changing either CONFIG
after construction does not change the other. Numeric components are finite
Python floats, so ordinary decimal values such as .1 are accepted.

The complete [authored example](../examples/pythonic_pos.kl) returns a constructed
value from a function, builds another pose and extracts data with UNPOS. Its
[snapshot](../examples/pythonic_pos.expected.json) and
[output](../examples/pythonic_pos.write.expected.json) are independent fixtures.

## Inputs and bounds

| Argument | Accepted values |
| --- | --- |
| x, y, z | Finite REAL, or promoted INTEGER/BYTE/SHORT; inclusive -10000000..10000000 mm |
| w, p, r | Finite REAL, or promoted INTEGER/BYTE/SHORT; inclusive -180..180 degrees |
| c | Exact CONFIG with all seven fields initialized; turn numbers -8..7 and strict BOOLEAN flags |
| ext1, ext2, ext3 | All three together. Finite REAL or promoted INTEGER/BYTE/SHORT. The values carry the caller's axis units. |

Numeric arguments cannot be BOOLEAN or text. The CONFIG must have its exact
declared fields and types, including when supplied by a host. Every field is
copied into independent storage; the constructor supplies no defaults. These
checks do not establish CONFIG validity for a particular robot or motion group.

Angles remain as supplied within the bound. The seven-argument form returns
XYZWPR. The ten-argument form returns XYZWPREXT and preserves its supplied
external values. Assignments to other pose types follow their existing
conversion rules.

## Composition and evaluation

POS initializes compatible variables, ARRAY elements and STRUCTURE fields.
Transparent XYZWPR/CONFIG aliases retain their types. Functions can return the
result or accept it as an independent writable value argument. Explicit calls
support fields such as `POS(1,2,3,4,5,6,cfg).x`, including temporary field arguments.

Arguments run once, left to right. Scalar values are captured before later
expressions. CONFIG reflects preceding coordinate effects. The seven-argument
form copies CONFIG in the constructor. The ten-argument form validates and
copies CONFIG before the first axis expression runs. Cartesian ranges and
axis finiteness are checked before the value is returned. Prior effects remain
if a later expression or check fails.

Failure performs no surrounding destination assignment. Successful values are
captured before an effectful assignment target resolves. Existing local-frame,
FOR-counter, transitive write, resource, ownership and failure-cleanup rules apply.

POS is a fallback call name in Pythonic mode. Explicit internal routines named
POS keep precedence, signatures and effects. Ordinary variables named pos remain
valid. Constructor calls require an explicit argument list.

Reports expose source-located `pos_constructors` with the result type and ordered
inputs. `pos_policy` documents the construction rules. UNPOS accepts constructor
results directly and checks the output references for overlap.

## Evidence boundary

The reviewed [reference edition](references.md), PDF page 478, documents the
seven-argument XYZWPR result and bounds. The additional external-axis arguments
are a Pythonic extension. This implementation combines the bounds with chosen
Python float, evaluation and checked-copy policies. It does not validate
robot CONFIG data, select frames/groups, perform kinematics or reproduce native
pause/alarm handling. Strict mode remains future work with internal POS rejection.
