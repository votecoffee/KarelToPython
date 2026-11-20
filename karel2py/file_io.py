"""FILE descriptors, portable field formats, PATH selection, and finite input."""
import struct


def runtime():
    from . import runtime as rt
    return rt


def fail(message, line=None):
    raise runtime().KarelRuntimeError(message, line)


FILE_TIMEOUT_ATTRIBUTE = 11
MAX_FILE_TIMEOUT_MS = 86_400_000
FILE_READ_TIMEOUT_STATUS = 4


class FileHandle:
    def __init__(self):
        self.name=None; self.position=0; self.mode=''; self.binary=False; self.status=0; self.owner=None
        self.logical_name=None
        self.xml=False;self.xml_session=None
        self.interactive=False; self.reverse=False; self.field=False
        self._file_eol = 10
        self._file_eol_explicit = False
        self._port_eol = None
        self.passall=False;self.noecho=False
        self.pipe_wait=None;self.pipe_overflow=None
        self._read_operation=None;self._write_operation=None
        self._text_cr=None
        self._append_ready = False
        self.read_timeout_ms = 0

    @property
    def eol(self):
        if self._file_eol_explicit or self._port_eol is None:
            return self._file_eol
        return self._port_eol

    @eol.setter
    def eol(self, value):
        self._file_eol = value
        self._file_eol_explicit = True

    @property
    def appends_at_end(self):
        return self.mode in ('A', 'AP')

    def require_readable(self, line=None):
        self.require_open(line)
        if self.mode in ('W', 'A'):
            fail('FILE is not readable', line)
        if self.mode == 'AP' and not self._append_ready:
            fail('AP FILE requires a successful nonempty WRITE before READ', line)

    def _finish_write(self, end, data):
        self.position = end
        self.status = 0
        if self.mode == 'AP' and data:
            self._append_ready = True

    def require_open(self,line=None):
        if self.owner is None: fail('FILE is not open',line)
    def tell(self,line=None): self.require_open(line); return self.position

    def _text_cr_pending(self):
        mark=self._text_cr
        return (mark is not None and mark[0] is self.owner and mark[1]==self.name
                and mark[2] is self.owner.files.get(self.name) and mark[3]==self.position
                and mark[4]==self.eol and self.eol in (10,13) and not self.binary)

    def _bind_text_cr(self):
        self._text_cr=(self.owner,self.name,self.owner.files[self.name],self.position,self.eol)

    def _text_reader(self,text,*,final=True):
        # A prior successful READ may have consumed CR before its LF arrived.
        skip=int(self._text_cr_pending() and text.startswith('\n'))
        return runtime().TextInput(text[skip:],terminator=self.eol,field_mode=self.field,final=final),skip

    def _finish_text_read(self,raw,offset):
        if offset:
            self._text_cr=None
            if self.eol in (10,13) and offset==len(raw) and raw[offset-1]==13:
                self._bind_text_cr()


def set_file_attribute(handle, attribute, value, line=None):
    if handle.owner is not None:
        fail('File attributes must be set before OPEN', line)
    if attribute == 1:
        handle.interactive = True
    elif attribute == 2:
        handle.binary = True
    elif attribute == 3:
        handle.reverse = True
    elif attribute == 4:
        handle.field = True
    elif attribute == 5:
        if not 0 <= value <= 127:
            fail('ATR_EOL requires an ASCII character code', line)
        handle.eol = value
    elif attribute == 6:
        handle.xml = True
    elif attribute == 7:
        handle.passall = True
    elif attribute == 8:
        handle.noecho = True
    elif attribute == 9:
        if value not in (0, 1):
            fail('ATR_PIPWAIT requires WAIT_USED or WAIT_NOTUSED', line)
        handle.pipe_wait = value
    elif attribute == 10:
        if not -1 <= value <= 64 * 1024 * 1024:
            fail('ATR_PIPOVADV requires OVF_EOF or a bounded byte count', line)
        handle.pipe_overflow = value
    elif attribute == FILE_TIMEOUT_ATTRIBUTE:
        if not 0 <= value <= MAX_FILE_TIMEOUT_MS:
            fail('ATR_TIMEOUT requires milliseconds in 0..86400000', line)
        handle.read_timeout_ms = value
    else:
        fail('Unsupported portable file attribute', line)


def path_io_components(spec, line=None):
    """Concrete data schemas for scalar PATHs and explicit PATH-bank I/O."""
    rt = runtime()
    if type(spec) is not tuple or len(spec) != 3 or spec[0] != 'PATH':
        fail('PATH I/O requires an exact PATH schema', line)
    node = rt.PREDEFINED_STRUCTURES['STD_PTH_NODE'] if spec[1] is None else spec[1]
    header = spec[2]
    components = (node,) if header is None else (node, header)
    if any(type(component) is not tuple or not component or component[0] != 'STRUCTURE'
           for component in components):
        fail('PATH I/O requires STRUCTURE node/header schemas', line)
    for component in components:
        rt._validate_data_schema(component, line)
    return node, header


def path_io_indexes(length, has_header, bounds, line=None):
    """Select ordered one-based node indexes and zero for a declared header."""
    if bounds is None:
        return range(0 if has_header else 1, length + 1)
    rt = runtime()
    first, last = bounds
    first = rt.integer(first, line)
    if last is None:
        if first == 0 and not has_header:
            fail('PATH header selection requires a declared PATHHEADER', line)
        if not 0 <= first <= length:
            fail('PATH node index out of range', line)
        return range(first, first + 1)

    last = rt.integer(last, line)
    if not 0 <= first <= length or not (0 if has_header else 1) <= last <= length:
        fail('PATH I/O range is outside the existing nodes', line)
    if first == 0 and not has_header:
        first = 1
    step = 1 if first <= last else -1
    return range(first, last + step, step)


def path_io_references(spec, value, line=None, *, check=None, bounds=None):
    """Capture the records selected by one PATH I/O item."""
    rt = runtime()
    node, header = path_io_components(spec, line)
    if type(value) is not rt.PathValue or value.spec != spec or type(value.nodes) is not list or len(value.nodes) > 32767:
        fail('PATH I/O requires matching ordinary PATH storage', line)
    if header is None and value.data is not None:
        fail('PATH I/O found unexpected header storage', line)

    nodes, data = value.nodes, value.data
    length = len(nodes)
    indexes = path_io_indexes(length, header is not None, bounds, line)
    include_header = 0 in indexes
    count = (len(indexes) - include_header) * rt.scalar_leaf_count(node)
    if include_header:
        count += rt.scalar_leaf_count(header)
    if count > 1024:
        fail('PATH I/O is limited to 1024 scalar fields including CR', line)
    if check is not None:
        selected_nodes = tuple((index, nodes[index - 1]) for index in indexes if index)
        for _ in range(count):
            check(line)
        if (value.spec != spec or value.nodes is not nodes or len(nodes) != length or value.data is not data
                or any(nodes[index - 1] is not saved for index, saved in selected_nodes)):
            fail('PATH I/O storage changed during preparation', line)

    references = [
        rt.Reference(header, vars(value), 'data') if index == 0 else rt.Reference(node, nodes, index - 1)
        for index in indexes
    ]
    for reference in references:
        rt._aggregate_value(reference.spec, reference.raw(), line, allow_partial=True)
    return references


def binary_format(kind,formats,line=None):
    if len(formats)>1: fail('Binary fields accept only a byte width',line)
    width=formats[0] if formats else {'BYTE':1,'SHORT':2,'BOOLEAN':1,'INTEGER':4,'REAL':4}.get(kind)
    if kind=='STRING':
        if type(width) is not int or not 0<=width<=254: fail('Binary STRING needs byte width 0..254',line)
        return width,None
    formats_by_width={'BYTE':{1:'B'},'SHORT':{2:'h'},'BOOLEAN':{1:'?'},'INTEGER':{1:'b',2:'h',4:'i'},'REAL':{4:'f',8:'d'}}
    code=formats_by_width.get(kind,{}).get(width)
    if code is None: fail('Unsupported binary field type/width',line)
    return width,'<'+code


def binary_read_fields(targets,formats,line=None):
    """Plan every fixed-width field before a FILE transport reads bytes."""
    if type(formats) not in (list,tuple) or len(formats)!=len(targets):
        fail('Binary READ requires one format list per target',line)
    return [binary_format(target.spec[0],(target.spec[1],) if target.spec[0]=='STRING' and not field else field,line)
            for target,field in zip(targets,formats)]


def file_piece(handle,kind,value,formats,line=None):
    rt=runtime()
    if not handle.binary: return rt.format_write_item(kind,value,formats,line)
    if kind=='STRING' and not formats: formats=[len(rt.ascii_string(value,line))]
    width,code=binary_format(kind,formats,line)
    if code is None: return rt.ascii_string(value,line)[:width].ljust(width,'\0').encode('ascii')
    if handle.reverse: code='>'+code[1:]
    try: return struct.pack(code,value)
    except (OverflowError,struct.error) as exc: raise rt.KarelRuntimeError('Binary field cannot represent supplied value',line) from exc


def file_read(state,handle,targets,line=None,*,line_breaks=(),formats=None):
    from .fileops import charge_file_bytes

    if handle.xml: fail('Use XML_SCAN/XML_GETDATA for XML FILE input',line)
    rt=runtime();handle.require_open(line)
    formats=formats if formats is not None else [()] * len(targets)
    owner=handle.owner
    if type(owner) is rt.KeyboardInput:fail('Keyboard FILE requires READ_KB',line)
    if type(owner) is rt.PendantDisplay:fail('Window FILE provides output only; keyboard READ is not modeled',line)
    if type(owner) in (rt.Messaging,rt.SerialStreams):owner.before_read(handle,line)
    rt._validate_read_targets(targets,line)

    name,start,operation=handle.name,handle.position,handle._read_operation
    identity=rt._file_identity(handle)
    reader_matches=owner.capture_reader(handle,line) if type(owner) in (rt.Acquisition,rt.FilePipes) else None
    data=owner.files.get(name)
    if type(data) not in (bytes,bytearray) or type(start) is not int or start<0:
        fail('FILE READ requires ordinary byte storage and a nonnegative cursor',line)
    size=len(data)

    def matches():
        return (handle._read_operation is operation and rt._file_identity(handle)==identity
                and owner.files.get(name) is data and len(data)==size
                and (reader_matches is None or reader_matches()))

    def check(position):
        if type(owner) is rt.SerialStreams:owner._active(handle,line,reading=True)
        if operation is not None and operation['finite'] is not None and position==start:
            rt._validate_file_read(handle,operation,line)
        if not matches() or handle.position!=position:
            fail('FILE READ identity, data or cursor changed during preparation',line)
        if operation is not None and operation['cancelled']:
            raise rt._FileReadCancelled()

    def charge():
        state.tick(line)
        check(start)

    transport = {rt.SerialStreams: 'Serial', rt.Messaging: 'Socket', rt.FilePipes: 'Pipe'}.get(type(owner)) if handle.passall else None
    if transport is not None:
        from .communications import StreamRead

        handle.require_readable(line)
        read_end = owner.end_position(handle, line) if type(owner) is rt.FilePipes else size
        try:
            request = StreamRead(handle, targets, line_breaks, formats, transport, line, raw_fields=True)
            raw = request.capture(state, handle, data, start, max(0, read_end - start), lambda: check(start))
            result = request.probe(handle, raw, final=True)
            if result is None:
                fail(f'End of finite {transport.lower()} input before complete PASSALL READ', line)
            values, offset = result
            request.publish(state, values)
        except Exception:
            if matches():
                handle.status = 1
            raise
        handle.position = start + offset
    elif handle.binary:
        if line_breaks: fail('CR is not a binary READ field',line)
        try:fields=binary_read_fields(targets,formats,line)
        except rt.KarelRuntimeError:
            handle.status=1
            raise
        length=sum(width for width,_ in fields)
        reclaim=type(owner) in (rt.Messaging,rt.SerialStreams) and owner._reclaims_input(handle,line)
        charge_file_bytes(max(length,size-start) if reclaim else length,charge)
        check(start)
        end=start+length
        try:
            raw=owner.read_bytes(handle,length,line)
            check(end)
            if type(raw) is not bytes or len(raw)!=length:
                fail('Incomplete binary FILE payload',line)
            values=[];offset=0
            for target,(width,code) in zip(targets,fields):
                data_field=raw[offset:offset+width];offset+=width
                if code and handle.reverse:code='>'+code[1:]
                value=data_field.decode('ascii') if code is None else struct.unpack(code,data_field)[0]
                # Keep the raw SHORT sentinel until its setter normalizes it.
                rt._validate_read_value(target,value,line);values.append(value)
            values=rt._prepare_read_values(targets,values,line)
            check(end)
            for target,value in zip(targets,values):target.set(value,line)
        except (Exception,rt._FileReadCancelled) as exc:
            if matches() and handle.position in (start,end):
                handle.position=start
                if not isinstance(exc,rt._FileReadCancelled):handle.status=1
            if isinstance(exc,UnicodeError): raise rt.KarelRuntimeError('Binary STRING requires ASCII data',line) from exc
            raise
    else:
        handle.require_readable(line)
        read_end=owner.end_position(handle,line) if type(owner) is rt.FilePipes else size
        charge_file_bytes(max(0,read_end-start),charge)
        check(start)
        raw=bytes(memoryview(data)[start:read_end])
        try: text=raw.decode('ascii')
        except UnicodeDecodeError: fail('Text FILE requires ASCII data',line)
        reader,skip=handle._text_reader(text); previous=state._read
        try:
            state._read=reader; state.read_items(targets,line,line_breaks=line_breaks,formats=formats)
        except Exception:
            handle.status=1; raise
        finally: state._read=previous
        offset=skip+reader.offset
        handle.position=start+offset
    if type(handle.owner) in (rt.Acquisition,rt.Messaging,rt.SerialStreams):handle.owner.after_read(handle,start,line)
    if handle.binary or transport is not None:handle._text_cr=None
    else:handle._finish_text_read(raw,offset)
    handle.status=0
