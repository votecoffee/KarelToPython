# Explicit predefined FILE bindings

Pythonic mode recognizes unshadowed TPDISPLAY, TPPROMPT, TPSTATUS, TPFUNC, TPERROR,
INPUT, OUTPUT, CRTPROMPT, CRTSTATUS, CRTFUNC and CRTERROR as FILE references.
Configure their endpoints explicitly through ExecutionContext.predefined_files
or the same context JSON field. This model does not discover native windows,
ports, files or controller resources.

```json
{
  "files": {"input": {"hex": "370a"}},
  "predefined_files": {
    "INPUT": {"name": "input", "mode": "RO"},
    "OUTPUT": {"name": "output", "mode": "WO"}
  }
}
```

```karel
PROGRAM EXAMPLE
%CRTDEVICE
VAR number:INTEGER
BEGIN
  READ(number,CR)
  WRITE(number,CR)
  CLOSE FILE INPUT
  CLOSE FILE OUTPUT
END EXAMPLE
```

Translate with the ordinary CLI, then run generated Python with --context and,
after closing resources as above, --state-out. Use --cooperative at translation
for default input that may wait without existing handler/task-control forms.
Explicit FILE READ and READ_KB retain their automatic cooperative translation.
No desktop window, physical keyboard, socket or serial port is opened.

## Binding and capture

Alias keys and modes are case-insensitive; endpoint names retain their spelling.
Each binding requires name and mode, with optional attributes. Supported modes
are R/RO, W/WO, RW/UD and A/AP. Attributes are the existing binary, reverse, field,
xml, passall, noecho, interactive, eol, pipe_wait and pipe_overflow settings;
Boolean flags and integer domains are checked before any resource opens.
Backend-specific restrictions still apply.

Descriptions are detached from constructor input. The predefined_files property
returns a defensive configuration copy. First use, including a status or UNINIT
query, lazily opens an ordinary handle through the existing configured service.
Each context retains one handle per alias; linked routines share it. Distinct
aliases targeting one busy endpoint retain the backend's existing busy-file rule.
No endpoint is created during context loading.

Omitted READ/WRITE selects TPDISPLAY, or INPUT/OUTPUT under that module's
%CRTDEVICE directive, once before destination/item/format evaluation. If that
default is unbound, existing callbacks and observations remain unchanged.
Explicit predefined names require a binding. Declared variables, constants,
routines and lexical USING fields keep their normal priority over the names.
Aliases are not discoverable variable data or additional globals.

Bound operations reuse ordinary text/binary formats, aggregate capture, byte
cursors and atomic destination publication. Default WRITE bypasses its callback
when bound. No new packed layouts, device timings or numeric conventions are added.

## Cancellation and ownership

Bare CANCEL FILE selects the bound default input: TPDISPLAY or CRTDEVICE INPUT.
Explicit CANCEL FILE alias and borrowed FILE arguments use the same handle.
Typed input and READ_KB cancellation preserve existing outputs/cursors, return
portable status 6, and retain pause, stop, abort and identity checks. Fileless
callbacks, menu controls, direct backend readers and pending writes keep their
separate contracts; unbound callback input is not canceled.

CLOSE FILE closes the cached handle without reopening it on a later lookup.
OPEN FILE cannot retarget a predefined binding, including through borrowed FILE
arguments. The host can call context.close_predefined_files() to close and reset
only its owned alias cache. Pending reads/editors and replaced registrations fail
without deleting foreign cache entries. A later source use after host reset opens
a fresh configured handle; retained borrowed references keep the original closed
handle. Cleanup may retain earlier successful closes if a
later backend close fails; it does not roll back filesystem effects.

## Saved contexts and limits

Live alias handles prevent context save. After source CLOSE or owned host cleanup,
JSON retains declarative bindings and ordinary service data. Loading creates no
handles; later use starts fresh without restoring cursor positions, registrations,
editors or suspended execution. Partial open failures retain any registered owned
handle for explicit recovery, rather than losing its identity.

This is an offline Pythonic model. Native preopened-file status, window routing,
hardware/controller timing, pending WRITE interruption and strict equivalence
remain outside it. See the [ledger](semantics/predefined_file_semantics.json),
[regressions](../tests/test_predefined_files.py), authored
[read](../examples/predefined_file_read.kl), [default output](../examples/predefined_default_write.kl),
[CRT](../examples/predefined_crt_defaults.kl), [binary](../examples/predefined_binary_io.kl),
[linked alias](../examples/predefined_files_linked/main.kl) and
[module-default](../examples/predefined_files_defaults/main.kl) examples.
