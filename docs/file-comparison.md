# Offline file comparison and printing

Version 0.89.0 adds COMPARE_FILE and PRINT_FILE to explicit MemoryFiles and
DirectoryFiles contexts. Inputs are named, closed files. The source forms are:

```karel
COMPARE_FILE(filea,fileb,result_file,ascii_flag,diff_count,status)
PRINT_FILE(file_spec,nowait,status)
```

Names are STRING inputs, flags are BOOLEAN inputs, result_file is an already
open writable FILE, and diff_count/status are writable INTEGER outputs. The
result handle must belong to the same backend that supplies the input names.
The handle is captured as a value: assigning another FILE variable to it shares
its cursor and contents. The call does not replace either FILE variable.

## Comparing files

ASCII comparison pairs records by their line number. It normalizes CR, LF and
CRLF separators and ignores whether the final record has a terminator. It counts
unequal pairs and missing records, without aligning inserted or deleted lines.
An empty file has zero records; a single newline has one blank record. Other
ASCII controls remain part of the record. Non-ASCII data raises an error.

Binary comparison accepts arbitrary bytes and returns the one-based position
of the first difference. A prefix-only difference returns the shorter length
plus one. Equal files return zero. This offset base is a portable choice.

The result is compact ASCII JSON Lines. A summary comes first, followed by each
different ASCII record with one-based line number and left/right strings; null
means a missing record. Binary results contain only the summary, with
first_difference and the unequal byte values; null means end of file.

```json
{"mode":"ascii","left":"left.txt","right":"right.txt","different_lines":2}
{"line":2,"left":"old","right":"new"}
{"line":3,"left":null,"right":"extra"}
```

Controls are escaped inside JSON strings. Each report record ends with the
result FILE's ATR_EOL byte (LF by default). A custom terminator can require a
matching custom record reader. The report is written at the current cursor,
or appended in append mode. Existing trailing bytes are retained under the
normal FILE overwrite rules. Binary FILE attributes do not change JSON encoding.

The complete report must fit in the remaining per-file capacity. Validation,
comparison, report construction and budget checks precede its single write.
On those failures, the comparison leaves report bytes, cursor, diff_count and
status unchanged. Earlier OPEN FILE effects still apply, including truncation
in W mode. Directory writes retain normal buffering until CLOSE FILE; ATR_IA
flushes immediately, with buffer/cursor rollback if that flush fails.

```python
import json
from karel2py import translate, runtime as rt

source = """PROGRAM DEMO
VAR report: FILE different,status: INTEGER
BEGIN
  OPEN FILE report ('W','changes.jsonl')
  COMPARE_FILE('left.txt','right.txt',report,TRUE,different,status)
  CLOSE FILE report
END DEMO"""
files = rt.MemoryFiles({"left.txt": "alpha\r\nold\r\n", "right.txt": "alpha\nnew\nextra\n"})
namespace = {"__name__": "comparison_demo"}
exec(translate(source).python_source, namespace)
Program = namespace["Program"]
result = Program(context=rt.ExecutionContext(files=files)).run()
assert (result["DIFFERENT"], result["STATUS"]) == (2, 0)
records = [json.loads(line) for line in files.snapshot()["changes.jsonl"].splitlines()]
assert records[1] == {"line": 2, "left": "old", "right": "new"}
assert records[2] == {"line": 3, "left": None, "right": "extra"}
```

## Printing files

PRINT_FILE validates the entire input as ASCII before emitting output. It
preserves the exact text and newline bytes in chunks of at most 254 characters
through the existing WRITE recorder or supplied write callback. An empty file
produces no request. Both nowait values run synchronously in Pythonic mode.

```python
from karel2py import translate, runtime as rt

files = rt.MemoryFiles({"message.txt": "ready\r\nsource file\n"})
namespace = {"__name__": "print_demo"}
exec(translate("PROGRAM DEMO VAR status: INTEGER BEGIN PRINT_FILE('message.txt',FALSE,status) END DEMO").python_source, namespace)
Program = namespace["Program"]
messages = []
program = Program(context=rt.ExecutionContext(files=files), write=messages.append)
assert program.run()["STATUS"] == 0
assert messages == ["ready\r\nsource file\n"]
assert program.write_requests[0]["adapter_outcome"] == "callback_completed"
```

A callback or budget failure preserves the pending status output; earlier
completed output requests and callback effects remain. A sticky ABORT stops
further output and prevents a success status. Nothing is retried automatically.
Routine output-effect reporting includes direct and transitive PRINT_FILE calls.

## Services, status and execution limits

| Portable status | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Missing input file |
| 3 | Input is open through the selected backend |

Missing/busy inputs write status only, retaining the comparison count and
report. The result FILE is validated before input access. Invalid paths,
unsupported ASCII, invalid context, report overflow and host I/O failures raise
source-located runtime errors. Output references must be disjoint and writable;
FOR counters remain protected through routines and condition actions. Arguments
and selectors are captured once in source order.

Both backends expose read_named(name), returning (status, detached_bytes) on
success or (status, None) on a missing/busy file. DirectoryFiles reads current
disk contents rather than previously cached bytes, using its explicit root,
device mapping, traversal restrictions and per-file limit. Named reads do not
populate its buffered-file snapshot. Re-select a directory root after restoring
context JSON; restored file bytes use MemoryFiles.

Each ASCII record, each 4096-byte binary comparison block and each print chunk
charges one execution step. These operations are synchronous and do not scan
handlers or yield to another task internally. Callback latency has no wall-time
bound. Existing partial output remains observable if a later chunk exhausts the
budget. No operating-system printer or default device is selected implicitly.

The authored [comparison](../examples/file_compare.kl) and
[printing](../examples/file_print.kl) examples include initial service state and
independent expected bytes. The translation report's file_comparison_policy and
[semantic ledger](semantics/file_comparison_semantics.json) record these choices.
The manual specifies API forms and broad behavior but leaves report layout,
line alignment and binary offset details unspecified. Native printer/device
behavior, asynchronous spooling, physical PATH node sizes and strict mode
remain future work.
