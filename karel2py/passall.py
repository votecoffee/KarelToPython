"""Fixed ASCII field plans for portable ATR_PASSALL reads."""

MAX_READ_BYTES = 4096


def plan_read(targets, formats, breaks, line, transport):
    from . import runtime

    fields = []
    for target, controls in zip(targets, formats):
        spec = target.spec
        controls = runtime.read_formats(spec, controls, line)
        quoted = spec[0] == 'STRING' and len(controls) == 2 and controls[1] == 2
        width = controls[0] if controls else 0
        if quoted and width < 2:
            raise runtime.KarelRuntimeError(
                'ATR_PASSALL quoted STRING fields require an explicit width in 2..254', line,
            )
        if not width and spec[0] == 'STRING':
            width = spec[1]
        if not 1 <= width <= 254:
            raise runtime.KarelRuntimeError(
                f'ATR_PASSALL {transport} fields require an explicit positive width in 1..254, or a STRING capacity',
                line,
            )
        fields.append((width, spec, controls, quoted))

    required = sum(field[0] for field in fields) + len(breaks)
    if required > MAX_READ_BYTES:
        raise runtime.KarelRuntimeError(f'ATR_PASSALL {transport} READ exceeds {MAX_READ_BYTES} raw bytes', line)
    operations = []
    marker = 0
    for index in range(len(fields) + 1):
        while marker < len(breaks) and breaks[marker] == index:
            operations.append(None)
            marker += 1
        if index < len(fields):
            operations.append(fields[index])
    return operations, required


def decode_field(text, field, line):
    from . import runtime

    _, spec, controls, quoted = field
    if spec[0] == 'STRING' and not quoted:
        return text
    request = dict(line=line, targets=[dict(type=spec[0], type_spec=spec, format_specifiers=controls)])
    return runtime.TextInput(text)(request)[0]


def probe_bytes(raw, operations, eol, line):
    """Return values and bytes consumed once every field and CR is present."""
    from . import runtime

    offset = 0
    spans = []
    for field in operations:
        if field is None:
            end = raw.find(bytes((eol,)), offset)
            if end == -1:
                break
            offset = end + 1
        else:
            end = offset + field[0]
            if end > len(raw):
                break
            spans.append((offset, end, field))
            offset = end
    else:
        values = []
        for start, end, field in spans:
            try:
                text = raw[start:end].decode('ascii')
            except UnicodeError as exc:
                raise runtime.KarelRuntimeError('ATR_PASSALL serial fields require ASCII data', line) from exc
            values.append(decode_field(text, field, line))
        return values, offset

    if len(raw) >= MAX_READ_BYTES:
        raise runtime.KarelRuntimeError(f'ATR_PASSALL serial READ exceeds {MAX_READ_BYTES} raw bytes', line)
    return None
