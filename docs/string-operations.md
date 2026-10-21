# Pythonic STRING operations

Since 0.58.0, Pythonic SUB_STR clips requests at the source end, permits zero
counts and caps returned values at 254 characters. INDEX accepts empty searches.
These are chosen practical equivalents; they do not claim native edge behavior.

```karel
PROGRAM strings
VAR text,payload,empty: STRING[16]
    match: INTEGER
BEGIN
  text='part:robot'
  payload=SUB_STR(text,INDEX(text,':')+1,MAXINT)
  empty=SUB_STR(text,1,0)
  match=INDEX('','')
  WRITE(payload,CR)
END strings
```

This finishes with `TEXT="part:robot"`, `PAYLOAD="robot"`, `EMPTY=""` and
`MATCH=1`, and records `robot\n`. The [complete example](../examples/pythonic_string_operations.kl)
also demonstrates smaller destination capacities, STRING routine composition
and absent searches, with independent
[expected values](../examples/pythonic_string_operations.expected.json) and
[expected output](../examples/pythonic_string_operations.write.expected.json).

| KAREL operation | Pythonic equivalent | Checked convention |
| --- | --- | --- |
| `SUB_STR(source,start,count)` | `source[start-1:start-1+min(count,254)]` | Positive one-based start; nonnegative INTEGER count. Clip at source end; zero count or start past end returns initialized empty STRING. |
| `INDEX(source,search)` | `source.find(search)+1` | First exact case-sensitive match; zero when absent. Empty search returns 1, including in an empty source. |
| `STR_LEN(source)` | `len(source)` | Count logical ASCII characters, including controls and decoded apostrophes. |
| `CHR(code)` | `chr(code)` | INTEGER code 0..127. |
| `ORD(source,index)` | `ord(source[index-1])` | One-based INTEGER index within current contents. |

SUB_STR bounds the slice **before allocation**. A count such as MAXINT does not
allocate a huge intermediate or require the requested end to exist. Concatenated
source expressions may exceed 254 characters, but SUB_STR returns at most 254
before a consumer receives its value. Smaller STRING assignment or routine-result
capacities truncate further using the existing rules. This capacity convention
also applies to STR_LEN, WRITE and writable value arguments consuming the result;
it is not just a destination-assignment rule.

All supplied STRING values must still be initialized ASCII, including when a
zero count would produce an empty result, or an empty search would return 1.
Starts below 1, counts below 0, invalid INTEGER values and out-of-range CHR/ORD
arguments raise source-located errors. Empty STRING values are initialized data;
they are distinct from an uninitialized variable. The combined WRITE output
limit of 254 still applies after rendering all items.

Arguments evaluate once, from left to right, before operation validation. A
STRING read captures an immutable value before a later argument can change its
source storage. Errors while evaluating an argument skip later arguments; domain
errors after evaluation retain prior effects and nested output. Destination
assignment happens after the result is produced; earlier argument mutations of
that same destination are not rolled back. Frames unwind on errors or
ABORT. See [evaluation order](evaluation-order.md),
[STRING values](pythonic-strings.md) and [text output](pythonic-output.md).

The translation report's `string_operation_policy` records these choices and the
remaining checks. The [semantic ledger](semantics/pythonic_string_operation_semantics.json)
and [execution tests](../tests/test_pythonic_string_operations.py) cover the
boundaries, composition and failure behavior. Earlier conservative substring and
empty-search rejections remain internal for the future strict milestone.
