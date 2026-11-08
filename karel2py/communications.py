"""Explicit offline socket messaging and circular PIP FILE backends."""
import re
import fnmatch
import struct
from dataclasses import dataclass
from .extended import MemoryFiles,fail


COMMUNICATION_CONSTANTS={'ATR_PIPWAIT':9,'ATR_PIPOVADV':10,'WAIT_NOTUSED':0,'WAIT_USED':1,'OVF_EOF':-1}


def rt():
    from . import runtime
    return runtime


def message_address(value):return bool(re.match(r'[CS][0-9]+:',value.upper()))


def tag_name(value):
    value=rt().ascii_string(value).upper()
    return value if re.fullmatch(r'[CS][1-8]:',value) else None


def pipe_name(value):
    value=rt().ascii_string(value).upper()
    if value.startswith('PIP:'):value=value[4:]
    if value.startswith('/'):value=value[1:]
    if not re.fullmatch(r'[A-Z0-9_][A-Z0-9_.-]{0,71}',value) or '..' in value:
        raise ValueError('File pipe requires a plain ASCII name')
    return 'PIP:'+value


def data_bytes(value,limit):
    if type(value) is dict:
        if set(value)!={'hex'} or type(value['hex']) is not str or len(value['hex'])>2*limit or not re.fullmatch(r'(?:[0-9a-fA-F]{2})*',value['hex']):
            raise ValueError('Invalid or excessive communication hex data')
        value=bytes.fromhex(value['hex'])
    elif type(value) is str:
        if not value.isascii() or len(value)>limit:raise ValueError('Communication text requires bounded ASCII')
        value=value.encode('ascii')
    if type(value) is not bytes or len(value)>limit:raise ValueError('Communication data requires bounded bytes')
    return value


def access_mode(handle,mode,line):
    mode=rt().ascii_string(mode,line).upper();binary='B' in mode or handle.binary;mode=mode.replace('B','')
    mode={'RO':'R','WO':'W','AP':'A','UD':'RW'}.get(mode,mode)
    if mode not in ('R','W','RW','A') or handle.xml:fail('Unsupported communication FILE access mode',line)
    if handle.owner is not None:fail('FILE is already open',line)
    return mode,binary


class StreamRead:
    """A validated scalar request shared by cooperative byte transports."""

    def __init__(self, handle, targets, line_breaks, formats, transport, line):
        runtime = rt()
        if type(targets) not in (list, tuple):
            fail(transport + ' READ requires scalar references', line)
        self.targets = tuple(targets)
        self.line_breaks = runtime._read_line_breaks(len(targets), line_breaks, line)
        runtime._validate_read_targets(targets, line)
        if formats is None:
            formats = [()] * len(targets)
        if type(formats) not in (list, tuple) or len(formats) != len(targets):
            fail(transport + ' READ requires one format per scalar target', line)
        self.formats = [runtime.read_formats(target.spec, field, line)
                        for target, field in zip(targets, formats)]
        self.widths = None
        if handle.binary:
            if self.line_breaks:
                fail('CR is not a binary READ field', line)
            from .extended import binary_read_fields
            self.widths = binary_read_fields(targets, self.formats, line)
            self.field_bytes = sum(width for width, _ in self.widths)
        else:
            self.field_bytes = sum(
                (field[0] if field else 0)
                or (target.spec[1] if handle.field and target.spec[0] == 'STRING' else 0)
                for target, field in zip(targets, self.formats)
            )
        self.request = dict(line=line, targets=[
            dict(type=target.spec[0], type_spec=target.spec,
                 **({'format_specifiers': field} if field else {}))
            for target, field in zip(targets, self.formats)
        ])
        if self.line_breaks:
            self.request['line_breaks'] = list(self.line_breaks)
        self.transport = transport
        self.line = line

    def minimum_bytes(self, *, may_finalize):
        # Finite text can consume its last unterminated record with CR.
        return self.field_bytes + max(0, len(self.line_breaks) - int(may_finalize))

    def capture(self, state, handle, retained, start, available, verify):
        from .fileops import charge_file_bytes

        length = len(retained)
        if not 0 <= start <= start + available <= length:
            fail(self.transport + ' pending READ has an invalid source range', self.line)
        if self.widths is not None and available < self.field_bytes:
            return b''  # No binary fields can be probed until all bytes arrive.
        size = available if self.widths is None else self.field_bytes
        token = handle._read_operation
        charge_file_bytes(size, lambda: state.tick(self.line))
        if handle._read_operation is not token:
            fail(self.transport + ' pending READ source token changed', self.line)
        rt().check_file_read(handle, self.line)
        verify()
        if len(retained) != length:
            fail(self.transport + ' pending READ buffer length changed during byte accounting', self.line)
        return bytes(memoryview(retained)[start:start + size])

    def can_finalize(self, handle, raw):
        try:
            return self.probe(handle, raw, final=True) is not None
        except rt().KarelRuntimeError:
            return False

    def probe(self, handle, raw, *, final):
        runtime = rt()
        if self.widths is not None:
            if len(raw) < self.field_bytes:
                return None
            values = []
            offset = 0
            for target, (width, code) in zip(self.targets, self.widths):
                data = raw[offset:offset + width]
                offset += width
                if code and handle.reverse:
                    code = '>' + code[1:]
                try:
                    value = data.decode('ascii') if code is None else struct.unpack(code, data)[0]
                except (UnicodeError, struct.error) as exc:
                    raise runtime.KarelRuntimeError(
                        'Invalid binary ' + self.transport.lower() + ' field: ' + str(exc),
                        self.line,
                    ) from exc
                runtime._validate_read_value(target, value, self.line)
                values.append(value)
            return values, offset
        try:
            text = raw.decode('ascii')
        except UnicodeDecodeError as exc:
            raise runtime.KarelRuntimeError(
                'Text ' + self.transport.lower() + ' FILE requires ASCII data', self.line,
            ) from exc
        reader = runtime.TextInput(text, terminator=handle.eol, field_mode=handle.field, final=final)
        try:
            values = reader(self.request)
        except runtime.TextInputIncomplete:
            return None
        return values, reader.offset

    def publish(self, state, values):
        previous = state._read
        try:
            state._read = lambda request: values
            state.read_items(self.targets, self.line, line_breaks=self.line_breaks, formats=self.formats)
        finally:
            state._read = previous


@dataclass(frozen=True, slots=True)
class _SocketOperation:
    kind: str
    state: object
    root: object
    identity: tuple
    position: int
    token: object
    port: dict
    connection: object
    rx: bytearray
    tx: bytearray
    limit: int
    pending: dict
    ports: dict
    files: dict


class Messaging(MemoryFiles):
    """Scripted endpoints and ping results; never create host sockets or DNS calls."""
    def __init__(self,ports=None,*,hosts=None,limit=4*1024*1024):
        super().__init__(limit=limit);self.ports={};self.hosts={};self._pending={}
        if ports is not None and (type(ports) is not dict or len(ports)>16):raise ValueError('Messaging requires at most sixteen ports')
        remaining=limit
        for tag,row in (ports or {}).items():
            key=tag_name(tag) if type(tag) is str else None
            if key is None or key in self.ports or type(row) is not dict or set(row)-{'mounted','available','connected','input','output','wait','final','wait_output'}:
                raise ValueError('Invalid or duplicate messaging port')
            flags={name:row.get(name,False if name=='connected' else True) for name in ('mounted','available','connected')}
            if any(type(value) is not bool for value in flags.values()) or flags['connected'] and not (flags['mounted'] and flags['available']):
                raise ValueError('Inconsistent messaging port flags')
            wait = row.get('wait', False)
            final = row.get('final', not wait)
            wait_output = row.get('wait_output', False)
            if type(wait) is not bool or type(final) is not bool or not wait and not final:
                raise ValueError('Socket wait/final require BOOLEANs; finite ports must be final')
            if type(wait_output) is not bool:
                raise ValueError('Socket wait_output requires BOOLEAN')
            incoming=data_bytes(row.get('input',b''),remaining);remaining-=len(incoming)
            outgoing=data_bytes(row.get('output',b''),remaining);remaining-=len(outgoing)
            self.files[key] = bytearray(incoming)
            self.ports[key] = dict(flags, output=bytearray(outgoing), wait=wait, final=final,
                                   wait_output=wait_output,
                                   _connection=object() if flags['connected'] else None)
        if self.used()>limit:raise ValueError('Combined socket data exceeds its bank limit')
        if hosts is not None and (type(hosts) is not dict or len(hosts)>256):raise ValueError('Ping table requires at most 256 supplied hosts')
        for host,status in (hosts or {}).items():
            key=self.host_name(host)
            if key is None or key in self.hosts or type(status) is not int or not 0<=status<=2147483646:
                raise ValueError('Invalid or duplicate scripted ping result')
            self.hosts[key]=status

    @staticmethod
    def host_name(value):
        if type(value) is not str or not value.isascii() or not 1<=len(value)<=254 or any(ord(c)<=32 or ord(c)==127 for c in value):return None
        return value.lower()

    def used(self):return sum(map(len,self.files.values()))+sum(len(row['output']) for row in self.ports.values())

    def change(self,operation,tag,line=None):
        key=tag_name(tag)
        if key is None:return 2
        if key not in self.ports:return 1
        row=self.ports[key]
        if operation in ('MSG_DISCO','DISMOUNT_DEV') and self._busy(key):return 3
        if operation=='MOUNT_DEV':row['mounted']=True
        elif operation=='DISMOUNT_DEV':row.update(mounted=False,connected=False,_connection=None)
        elif operation=='MSG_CONNECT':
            if not row['mounted'] or not row['available']:return 4
            if not row['connected']:row.update(connected=True,_connection=object())
        elif operation=='MSG_DISCO':row.update(connected=False,_connection=None)
        else:raise ValueError('Unknown messaging state operation')
        return 0

    def ping(self,host):
        key=self.host_name(host)
        return 2 if key is None else self.hosts.get(key,1)

    def set_available(self,tag,available):
        key=tag_name(tag)
        if key not in self.ports or type(available) is not bool:raise ValueError('Availability requires a configured port and Boolean')
        self.ports[key]['available']=available
        if not available:self.ports[key].update(connected=False,_connection=None)

    def feed(self,tag,data):
        key=tag_name(tag)
        if key not in self.ports:raise ValueError('Input requires a configured messaging tag')
        row = self.ports[key]
        if row['wait'] and row['final']:
            raise ValueError('Socket input is final; cannot feed more bytes')
        data=data_bytes(data,self.limit-self.used())
        if self.used()+len(data)>self.limit:raise ValueError('Combined socket data exceeds its bank limit')
        self.files[key].extend(data)

    def finish_input(self, tag):
        """Mark a waiting endpoint's explicitly supplied RX stream as final."""
        key = tag_name(tag)
        if key not in self.ports or self.ports[key]['wait'] is not True:
            raise ValueError('finish_input requires a waiting messaging tag')
        self.ports[key]['final'] = True

    def take_output(self,tag,count=None):
        key=tag_name(tag)
        if key not in self.ports:raise ValueError('Output requires a configured messaging tag')
        buffer=self.ports[key]['output'];count=len(buffer) if count is None else count
        if type(count) is not int or not 0<=count<=len(buffer):raise ValueError('Socket output count exceeds queued bytes')
        data=bytes(buffer[:count]);del buffer[:count];return data

    def connected(self,handle,line=None):
        handle.require_open(line)
        row = self.ports.get(handle.name)
        if handle.owner is not self or row is None or not all(
            row.get(name) is True for name in ('mounted', 'available', 'connected')
        ):
            fail('Offline socket endpoint is disconnected', line)
        if (any(type(row.get(name)) is not bool for name in ('wait', 'final', 'wait_output'))
                or not row['wait'] and not row['final']):
            fail('Socket wait policy is invalid', line)
        return row

    def open_for(self,state,handle,mode,name,line=None):
        mode,binary=access_mode(handle,mode,line);key=tag_name(name)
        if key not in self.ports:fail('Socket FILE requires an explicitly configured C1:..C8:/S1:..S8: tag',line)
        if id(handle) in self._pending or self._busy(key):
            fail('Socket endpoint already has an open FILE or pending operation', line)
        row=self.ports[key]
        if not all(row[name] for name in ('mounted','available','connected')):fail('Offline socket endpoint is disconnected',line)
        handle.name,handle.mode,handle.owner,handle.binary=key,mode,self,binary
        handle.logical_name=key;handle.position=0;handle.status=0;self.handles.append(handle)

    def require_idle(self, handle, line=None, *, reading=False):
        if id(handle) in self._pending:
            fail('Socket FILE has pending I/O', line)
        if handle._write_operation is not None:
            fail('Socket FILE has a pending WRITE', line)
        if not reading and handle._read_operation is not None:
            fail('Socket FILE has a pending READ', line)

    def before_read(self, handle, line=None):
        self.require_idle(handle, line, reading=True)
        self.connected(handle, line)

    def read_bytes(self, handle, count, line=None):
        self.before_read(handle, line)
        return super().read_bytes(handle, count, line)

    def close(self, handle, line=None):
        self.require_idle(handle, line)
        return super().close(handle, line)

    def flush(self, handle, line=None):
        self.require_idle(handle, line)
        return super().flush(handle, line)

    def after_read(self,handle,start,line=None):
        if handle.position:del self.files[handle.name][:handle.position];handle.position=0

    def write(self,handle,data,line=None):
        self.require_idle(handle, line)
        row=self.connected(handle,line)
        if handle.mode=='R':fail('Socket FILE is read-only',line)
        if self.used()+len(data)>self.limit:fail('Combined socket data exceeds its bank limit',line)
        row['output'].extend(data);handle.status=0

    def _start_operation(self, state, handle, row, kind, line):
        if id(handle) in self._pending or not any(item is handle for item in self.handles):
            fail('Socket FILE has pending I/O or a stale open registration', line)
        if type(handle.position) is not int or not 0 <= handle.position <= len(self.files[handle.name]):
            fail('Socket FILE has an invalid receive cursor', line)
        runtime = rt()
        token = handle._read_operation if kind == 'READ' else handle._write_operation
        record = _SocketOperation(kind, state, runtime.task_root(state), runtime._file_identity(handle),
                                  handle.position, token, row, row['_connection'],
                                  self.files[handle.name], row['output'], self.limit,
                                  self._pending, self.ports, self.files)
        self._pending[id(handle)] = record
        return record

    def validate_pending(self, handle, state, kind, line=None, *, expected=None):
        record = self._pending.get(id(handle))
        if (type(record) is not _SocketOperation or expected is not None and record is not expected
                or record.kind != kind or record.state is not state
                or rt().task_root(state) is not record.root
                or record.pending is not self._pending or record.ports is not self.ports
                or record.files is not self.files or handle.owner is not self
                or not any(item is handle for item in self.handles)
                or type(handle.position) is not int or handle.position != record.position
                or type(self.limit) is not int or self.limit != record.limit):
            fail('Socket pending I/O registration, cursor or limit changed', line)
        identity = rt()._file_identity(handle)
        if any(type(value) is not type(original) or value != original
               for value, original in zip(identity, record.identity)):
            fail('Socket pending FILE attributes changed', line)
        token = handle._read_operation if kind == 'READ' else handle._write_operation
        if token is not record.token:
            fail('Socket pending I/O source token changed', line)
        row = self.ports.get(handle.name)
        if (row is not record.port or self.files.get(handle.name) is not record.rx
                or row.get('output') is not record.tx):
            fail('Socket pending I/O buffer identity changed', line)
        self.connected(handle, line)
        if row.get('_connection') is not record.connection:
            fail('Socket connection changed during pending I/O', line)
        policy = 'wait' if kind == 'READ' else 'wait_output'
        if row.get(policy) is not True or type(row.get('final')) is not bool:
            fail('Socket pending I/O wait policy changed', line)
        return row

    def _release_operation(self, handle, record):
        if self._pending is record.pending and self._pending.get(id(handle)) is record:
            del self._pending[id(handle)]

    def _operation_failed(self, handle, record):
        if (handle.owner is self and self._pending is record.pending
                and self._pending.get(id(handle)) is record
                and any(item is handle for item in self.handles)):
            handle.status = 1

    @staticmethod
    def _wait(state, kind, line):
        runtime = rt()
        root = runtime.task_root(state)
        if state._in_handler or root._in_handler:
            fail('Pending socket ' + kind + ' cannot wait inside a handler action', line)
        if state._scheduler is None and not getattr(root, '_sleep_injected', False):
            fail('Indefinite standalone socket ' + kind + ' requires an explicit sleeper callback', line)
        yield from runtime.delay_execution(state, 10, line, scan_handlers=True)
        yield from runtime.checkpoint(state, line)

    def read_items(self, state, handle, targets, line=None, *, line_breaks=(), formats=None):
        row = self.connected(handle, line)
        if not row['wait']:
            return state.file_read(handle, targets, line, line_breaks=line_breaks, formats=formats)
        if handle.mode in ('W', 'A'):
            fail('Socket FILE is not readable', line)
        request = StreamRead(handle, targets, line_breaks, formats, 'Socket', line)
        record = self._start_operation(state, handle, row, 'READ', line)
        try:
            if record.position + request.minimum_bytes(may_finalize=True) > record.limit:
                fail('Atomic socket READ exceeds receive bank limit', line)
            while True:
                row = self.validate_pending(handle, state, 'READ', line, expected=record)
                rt().check_file_read(handle, line)
                raw = request.capture(
                    state, handle, record.rx, record.position, len(record.rx) - record.position,
                    lambda: self.validate_pending(handle, state, 'READ', line, expected=record),
                )
                result = request.probe(handle, raw, final=row['final'])
                if result is not None:
                    values, offset = result
                    request.publish(state, values)
                    handle.position = record.position + offset
                    self.after_read(handle, record.position, line)
                    handle.status = 0
                    return
                if row['final']:
                    fail('End of finalized socket input before complete READ', line)
                if len(record.rx) >= record.limit and not request.can_finalize(handle, raw):
                    fail('Atomic socket READ cannot complete within receive bank limit', line)
                yield from self._wait(state, 'READ', line)
        except GeneratorExit:
            raise
        except BaseException:
            self._operation_failed(handle, record)
            raise
        finally:
            self._release_operation(handle, record)

    def write_items(self, state, handle, data, line=None):
        row = self.connected(handle, line)
        if not row['wait_output']:
            return self.write(handle, data, line)
        if handle.mode == 'R':
            fail('Socket FILE is read-only', line)
        if type(data) is not bytes:
            fail('Socket output requires explicit bytes', line)
        record = self._start_operation(state, handle, row, 'WRITE', line)
        try:
            while True:
                self.validate_pending(handle, state, 'WRITE', line, expected=record)
                rt().check_file_write(handle, line)
                if len(record.rx) + len(data) > record.limit:
                    fail('Atomic socket WRITE exceeds retained receive and output bank limit', line)
                if self.used() + len(data) <= record.limit:
                    record.tx.extend(data)
                    handle.status = 0
                    return
                yield from self._wait(state, 'WRITE', line)
        except GeneratorExit:
            raise
        except BaseException:
            self._operation_failed(handle, record)
            raise
        finally:
            self._release_operation(handle, record)

    def to_config(self):
        if self.handles or self._pending:
            raise ValueError('Close live messaging FILEs before saving context')
        ports={key:{**{name:row[name] for name in ('mounted','available','connected')},
            'input':{'hex':self.files[key].hex()},'output':{'hex':row['output'].hex()},
            **(dict(wait=True, final=row['final']) if row['wait'] else {}),
            **(dict(wait_output=True) if row['wait_output'] else {})}
            for key,row in sorted(self.ports.items())}
        return {'limit':self.limit,'ports':ports,'hosts':dict(sorted(self.hosts.items()))}

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'limit','ports','hosts'}:raise ValueError('Unknown messaging fields')
        return cls(config.get('ports'),hosts=config.get('hosts'),limit=config.get('limit',4*1024*1024))


class FilePipes(MemoryFiles):
    """Bounded circular byte histories, with independent FILE read cursors."""
    def __init__(self,*,limit=16*1024*1024):super().__init__(limit=limit);self.pipes={};self._reads={}

    def configure(self,name,cmos,sectors,record_size,dictionary,element,line=None):
        try:key=pipe_name(name)
        except (ValueError,rt().KarelRuntimeError):return 2
        if (type(cmos) is not bool or type(sectors) is not int or not 0<=sectors<=65536
                or type(record_size) is not int or record_size<0 or type(element) is not int or not 0<=element<=32767):return 2
        dictionary=rt().ascii_string(dictionary,line)
        if len(dictionary)>64:return 2
        sectors=sectors or 8;capacity=sectors*1024
        if record_size>capacity:return 2
        if self._busy(key):return 3
        if key not in self.pipes and len(self.pipes)>=32:return 5
        if capacity+sum(row['sectors']*1024 for name,row in self.pipes.items() if name!=key)>self.limit:return 5
        if len(self.files.get(key,b''))>capacity:return 5
        self.pipes[key]=dict(cmos=cmos,sectors=sectors,record_size=record_size,form_dict=dictionary,form_ele=element)
        self.files.setdefault(key,bytearray());return 0

    def open_for(self,state,handle,mode,name,line=None):
        mode,binary=access_mode(handle,mode,line)
        try:key=pipe_name(name)
        except ValueError:fail('Invalid PIP FILE name',line)
        if key not in self.pipes:fail('PIP FILE is not explicitly configured',line)
        if len(self.handles)>=32:fail('File pipe handle limit exceeded (32)',line)
        wait=getattr(handle,'pipe_wait',None);overflow=getattr(handle,'pipe_overflow',None)
        capacity=self.pipes[key]['sectors']*1024;record_size=self.pipes[key]['record_size']
        if wait is not None and (type(wait) is not int or wait not in (0,1)):
            fail('ATR_PIPWAIT requires WAIT_USED or WAIT_NOTUSED',line)
        if overflow is not None and (type(overflow) is not int or overflow!=-1 and not 0<=overflow<=capacity):
            fail('ATR_PIPOVADV requires OVF_EOF or bytes in 0..pipe capacity',line)
        advance=overflow
        if overflow is not None and overflow>=0 and record_size:
            advance=((overflow+record_size-1)//record_size)*record_size
            if advance>capacity:fail('Rounded ATR_PIPOVADV exceeds pipe capacity',line)
        if (wait is not None or overflow is not None) and mode in ('W','A'):
            fail('Pipe read attributes require a readable FILE mode',line)
        if mode=='W':
            self.files[key].clear()
            for other in self.handles:
                if other.name==key:
                    other.position=0
                    if getattr(other,'_pipe_snapshot_end',None) is not None:other._pipe_snapshot_end=0
        handle.name,handle.mode,handle.owner,handle.binary=key,mode,self,binary
        handle.logical_name=key;handle.position=0;handle.status=0
        handle._pipe_snapshot_end=len(self.files[key]) if wait==0 else None
        handle._pipe_overflowed=False;handle._pipe_advance=advance
        self.handles.append(handle)

    def write(self,handle,data,line=None):
        handle.require_open(line)
        if handle.mode=='R':fail('Pipe FILE is read-only',line)
        buffer=self.files[handle.name];capacity=self.pipes[handle.name]['sectors']*1024
        dropped=max(0,len(buffer)+len(data)-capacity)
        if len(data)>=capacity:buffer[:]=data[-capacity:]
        else:
            if dropped:del buffer[:dropped]
            buffer.extend(data)
        if dropped:
            for other in self.handles:
                if other.name!=handle.name:continue
                lost=other.position<dropped
                other.position=max(0,other.position-dropped)
                end=getattr(other,'_pipe_snapshot_end',None)
                if end is not None:other._pipe_snapshot_end=max(0,end-dropped)
                if lost and (getattr(other,'pipe_wait',None) is not None or getattr(other,'pipe_overflow',None) is not None):
                    advance=getattr(other,'_pipe_advance',None)
                    if advance is None or advance==-1:other._pipe_overflowed=True
                    else:other.position=min(advance,len(buffer))
        handle.status=0

    def feed(self,name,data):
        """Append explicitly supplied host bytes through ordinary circular rules."""
        key=pipe_name(name)
        if key not in self.pipes:raise ValueError('Input requires an explicitly configured pipe')
        data=data_bytes(data,self.limit)
        handle=rt().FileHandle();handle.name=key;handle.mode='A';handle.owner=self
        self.write(handle,data)

    def read_named(self,name):
        key=pipe_name(name)
        if self._busy(key):return 3,None
        if key not in self.pipes:return 1,None
        return 0,bytes(self.files[key])

    def replace_named(self,name,data,overwrite=False):
        """Replace a configured closed pipe with one finite snapshot, without overflow."""
        key=pipe_name(name)
        if self._busy(key):return 3
        if key not in self.pipes:return 1
        if not overwrite:return 2
        if len(data)>self.pipes[key]['sectors']*1024:return 4
        self.files[key]=bytearray(data);return 0

    def list_names(self,pattern='*',*,check=None):
        from .fileops import _listing_entries

        pattern=rt().ascii_string(pattern).upper()
        if pattern.startswith('PIP:'):pattern=pattern[4:]
        if pattern.startswith('/'):pattern=pattern[1:]
        if (not pattern or len(pattern)>72 or '..' in pattern
                or re.fullmatch(r'[A-Z0-9_.*?\-]+',pattern) is None):
            raise ValueError('Pipe listing requires a plain basename pattern with star/question wildcards')
        return sorted(key for key in _listing_entries(self.pipes,check) if fnmatch.fnmatchcase(key,'PIP:'+pattern))

    def copy(self,source,target,overwrite=False):
        source=pipe_name(source);target=pipe_name(target)
        if self._busy(source) or self._busy(target):return 3
        code,data=self.read_named(source)
        return code or self.replace_named(target,data,overwrite)

    def delete(self,name):
        key=pipe_name(name)
        if self._busy(key):return 3
        if key not in self.pipes:return 1
        del self.files[key];del self.pipes[key];return 0

    def rename(self,source,target):
        source=pipe_name(source);target=pipe_name(target)
        if self._busy(source) or self._busy(target):return 3
        if source not in self.pipes:return 1
        if target in self.pipes:return 2
        self.pipes[target]=self.pipes.pop(source);self.files[target]=self.files.pop(source);return 0

    def before_read(self,handle,line=None):
        handle.require_open(line)
        if handle.owner is not self:fail('Pipe READ requires its original backend',line)
        if handle.mode in ('W','A'):fail('Pipe FILE is not readable',line)
        if getattr(handle,'_pipe_overflowed',False):
            handle.status=1;fail('Pipe read overflow reached EOF; close and reopen FILE',line)

    def end_position(self,handle,line=None):
        self.before_read(handle,line)
        end=getattr(handle,'_pipe_snapshot_end',None)
        return len(self.files[handle.name]) if end is None else min(end,len(self.files[handle.name]))

    def bytes_ahead(self,handle,line=None):
        return max(0,self.end_position(handle,line)-handle.position)

    def seek(self,handle,position,line=None):
        end=self.end_position(handle,line)
        if id(handle) in self._reads:fail('Pipe FILE has an active READ; cannot seek',line)
        position=rt().integer(position,line)
        if position==-1:position=end
        if not 0<=position<=end:return 2
        handle.position=position;return 0

    def close(self,handle,line=None):
        if id(handle) in self._reads:fail('Pipe FILE has an active READ; cancel it before CLOSE',line)
        return super().close(handle,line)

    def read_bytes(self,handle,count,line=None):
        if getattr(handle,'pipe_wait',None) is None and getattr(handle,'pipe_overflow',None) is None:
            return super().read_bytes(handle,count,line)
        self.before_read(handle,line)
        if count>self.bytes_ahead(handle,line):handle.status=1;fail('End of pipe FILE',line)
        return super().read_bytes(handle,count,line)

    def pipe_read(self,state,handle,targets,line=None,*,line_breaks=(),formats=None):
        """Probe complete input without publication, then commit one READ request."""
        runtime=rt();self.before_read(handle,line)
        request = StreamRead(handle, targets, line_breaks, formats, 'Pipe', line)
        waiting=getattr(handle,'pipe_wait',None)==1
        minimum=request.minimum_bytes(may_finalize=not waiting)
        if (handle.binary or waiting) and minimum > self.pipes[handle.name]['sectors'] * 1024:
            fail('Atomic pipe READ exceeds circular capacity', line)
        if id(handle) in self._reads:fail('Pipe FILE already has an active READ',line)
        self._reads[id(handle)]=state
        try:
            while True:
                self.before_read(handle,line)
                runtime.check_file_read(handle,line)
                start = handle.position
                available = self.bytes_ahead(handle, line)
                retained = self.files[handle.name]

                def verify():
                    if (self._reads.get(id(handle)) is not state or handle.position != start
                            or self.files.get(handle.name) is not retained
                            or self.bytes_ahead(handle, line) != available):
                        fail('Pipe pending READ source changed during byte accounting', line)

                raw = request.capture(state, handle, retained, start, available, verify)
                result = request.probe(handle, raw, final=not waiting)
                if result is not None:
                    values, offset = result
                    request.publish(state, values)
                    handle.position = start + offset
                    handle.status = 0
                    return
                if not waiting:
                    handle.status=1;fail('End of pipe FILE',line)
                root=runtime.task_root(state)
                if state._in_handler or root._in_handler:
                    fail('Pending pipe READ cannot wait inside a handler action',line)
                if state._scheduler is None and not getattr(root,'_sleep_injected',False):
                    fail('Indefinite standalone pipe wait requires an explicit sleeper callback',line)
                yield from runtime.delay_execution(state,10,line,scan_handlers=True)
                yield from runtime.checkpoint(state,line)
        except GeneratorExit:raise
        except BaseException:
            if handle.owner is self and self._reads.get(id(handle)) is state:
                handle.status = 1
            raise
        finally:
            if self._reads.get(id(handle)) is state:
                del self._reads[id(handle)]

    def to_config(self):
        if self.handles:raise ValueError('Close live pipe FILEs before saving context')
        return {'limit':self.limit,'pipes':{name:{**row,'data':{'hex':self.files[name].hex()}} for name,row in sorted(self.pipes.items())}}

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'limit','pipes'}:raise ValueError('Unknown file-pipe fields')
        result=cls(limit=config.get('limit',16*1024*1024));rows=config.get('pipes',{})
        if type(rows) is not dict or len(rows)>32:raise ValueError('File pipes require a bounded mapping')
        for name,row in rows.items():
            if type(row) is not dict or set(row)-{'cmos','sectors','record_size','form_dict','form_ele','data'}:raise ValueError('Unknown file-pipe metadata')
            try:key=pipe_name(name)
            except (ValueError,rt().KarelRuntimeError) as exc:raise ValueError(str(exc)) from exc
            if key in result.pipes:raise ValueError('Duplicate file-pipe name')
            try:code=result.configure(key,row.get('cmos',False),row.get('sectors',8),row.get('record_size',0),row.get('form_dict',''),row.get('form_ele',0))
            except rt().KarelRuntimeError as exc:raise ValueError(str(exc)) from exc
            if code:
                raise ValueError('Invalid file-pipe configuration')
            data=data_bytes(row.get('data',b''),result.pipes[key]['sectors']*1024);result.files[key][:]=data
        return result


def invoke(state,operation,args,line=None):
    context=state.execution
    if operation=='PIPE_CONFIG':
        bank=context.require('file_pipes',line)
        try:key=pipe_name(args[0])
        except (ValueError,rt().KarelRuntimeError):args[-1].set(2,line);return
        if context.acquisition is not None and key in context.acquisition.files:code=3
        else:code=bank.configure(*args[:-1],line=line)
    else:
        bank=context.require('messaging',line)
        code=bank.ping(args[0]) if operation=='MSG_PING' else bank.change(operation,args[0],line)
    args[-1].set(code,line)
