"""Explicit offline serial byte streams; never open host devices."""
import re
from .communications import StreamRead, data_bytes


MAX_BYTES=64*1024*1024


def rt():
    from . import runtime
    return runtime


def serial_address(value):
    """Reserve numeric P-device prefixes, including invalid endpoint aliases."""
    return type(value) is str and bool(re.match(r'P[0-9]+:',value.upper()))


def port_number(value):
    if type(value) is not int or not 1<=value<=5:
        raise ValueError('Serial streams require actual INTEGER port numbers in 1..5')
    return value


def endpoint_name(value):
    if type(value) is not str or not re.fullmatch(r'P[1-5]:',value.upper()):
        raise ValueError('Serial FILE requires exactly P1: through P5: without a suffix')
    return value.upper()


class SerialStreams:
    """Exclusive FILE endpoints with bounded RX queues and retained TX outboxes."""
    def __init__(self,ports=None,*,limit=4*1024*1024):
        if type(limit) is not int or not 1<=limit<=MAX_BYTES:
            raise ValueError('Serial stream limit must be an INTEGER in 1..64 MiB')
        if ports is None:ports={}
        if type(ports) is not dict or len(ports)>5:
            raise ValueError('Serial streams require at most five explicitly supplied ports')
        self.limit=limit;self.ports={};self.files={};self.handles=[];self._open={};self._pending={};self._writes={}
        for port,row in ports.items():
            port=port_number(port)
            if type(row) is not dict or set(row)-{'capacity','input','output','wait','final','wait_output'}:
                raise ValueError('Unknown serial stream fields')
            capacity=row.get('capacity',limit)
            if type(capacity) is not int or not 1<=capacity<=limit:
                raise ValueError('Serial port capacity must be an INTEGER in 1..bank limit')
            wait=row.get('wait',False);final=row.get('final',not wait)
            if type(wait) is not bool or type(final) is not bool or not wait and not final:
                raise ValueError('Serial wait/final require BOOLEANs; finite ports must be final')
            wait_output=row.get('wait_output',False)
            if type(wait_output) is not bool:raise ValueError('Serial wait_output requires BOOLEAN')
            incoming=data_bytes(row.get('input',b''),capacity)
            outgoing=data_bytes(row.get('output',b''),capacity-len(incoming))
            self.ports[port]=dict(capacity=capacity,output=bytearray(outgoing),wait=wait,final=final,wait_output=wait_output)
            self.files[f'P{port}:']=bytearray(incoming)
        if self.used()>limit:raise ValueError('Combined serial input/output exceeds bank limit')

    def used(self):
        return sum(len(value) for value in self.files.values())+sum(len(row['output']) for row in self.ports.values())

    def _port(self,port):
        port=port_number(port)
        if port not in self.ports:raise ValueError('Serial stream port is not explicitly configured')
        return port

    def feed(self,port,data):
        """Append explicit host-supplied RX bytes without opening a device."""
        port=self._port(port);key=f'P{port}:';row=self.ports[port]
        if row['wait'] and row['final']:raise ValueError('Serial input is final; cannot feed more bytes')
        remaining=min(row['capacity']-len(self.files[key])-len(row['output']),self.limit-self.used())
        data=data_bytes(data,remaining)
        self.files[key].extend(data)

    def finish_input(self,port):
        """Mark explicitly waiting input complete without closing its FILE."""
        port=self._port(port);row=self.ports[port]
        if not row['wait']:raise ValueError('finish_input requires a waiting serial port')
        row['final']=True

    def take_output(self,port,count=None):
        port=self._port(port);output=self.ports[port]['output']
        count=len(output) if count is None else count
        if type(count) is not int or not 0<=count<=len(output):
            raise ValueError('Serial output count must be an INTEGER within retained TX bytes')
        result=bytes(output[:count]);del output[:count];return result

    def open_for(self,state,handle,mode,name,line=None):
        runtime=rt()
        if type(handle) is not runtime.FileHandle:raise runtime.KarelRuntimeError('Serial FILE requires an ordinary FILE handle',line)
        if handle.owner is not None or id(handle) in self._open:
            raise runtime.KarelRuntimeError('FILE is already open or has a stale serial registration',line)
        try:key=endpoint_name(name)
        except ValueError as exc:raise runtime.KarelRuntimeError(str(exc),line) from exc
        port=int(key[1])
        if port not in self.ports:raise runtime.KarelRuntimeError('Serial FILE requires an explicitly configured port',line)
        if any(record[1]==key for record in self._open.values()):
            raise runtime.KarelRuntimeError('Serial endpoint already has an open FILE',line)
        mode=runtime.ascii_string(mode,line).upper();binary=handle.binary
        if mode.endswith('B'):binary=True;mode=mode[:-1]
        mode={'RO':'R','WO':'W','UD':'RW','AP':'A','AO':'A'}.get(mode,mode)
        if mode not in ('R','W','RW','A'):
            raise runtime.KarelRuntimeError('Unsupported portable serial FILE mode',line)
        if handle.xml or handle.passall or handle.pipe_wait is not None or handle.pipe_overflow is not None:
            raise runtime.KarelRuntimeError('Serial FILE does not model XML, PASSALL or pipe attributes',line)
        if (any(type(value) is not bool for value in (binary,handle.reverse,handle.field,handle.noecho,handle.interactive))
                or type(handle.eol) is not int or not 0<=handle.eol<=127):
            raise runtime.KarelRuntimeError('Malformed serial FILE attributes',line)
        handle.name=key;handle.logical_name=key;handle.mode=mode;handle.binary=binary
        handle.position=0;handle.status=0;handle.owner=self;handle.xml_session=None
        self._open[id(handle)]=(handle,key,mode,binary,handle.reverse,handle.field,handle.eol)
        self.handles.append(handle)

    def open(self,handle,mode,name,line=None):return self.open_for(None,handle,mode,name,line)

    def _active(self,handle,line=None,*,reading=False):
        runtime=rt();record=self._open.get(id(handle))
        if (type(handle) is not runtime.FileHandle or record is None or record[0] is not handle or handle.owner is not self
                or (handle.name,handle.mode,handle.binary,handle.reverse,handle.field,handle.eol)!=record[1:]
                or handle.logical_name!=record[1]):
            raise runtime.KarelRuntimeError('Serial FILE is closed, foreign, stale or has changed endpoint metadata',line)
        if (any(type(value) is not bool for value in (handle.binary,handle.reverse,handle.field,handle.xml,
                    handle.passall,handle.noecho,handle.interactive))
                or type(handle.eol) is not int or not 0<=handle.eol<=127 or handle.xml or handle.passall
                or handle.pipe_wait is not None or handle.pipe_overflow is not None):
            raise runtime.KarelRuntimeError('Serial FILE attributes changed or are invalid',line)
        if (type(handle.position) is not int or not 0<=handle.position<=len(self.files[handle.name])
                or handle.mode in ('W','A') and handle.position!=0):
            raise runtime.KarelRuntimeError('Serial FILE has an invalid receive cursor',line)
        if reading and handle.mode in ('W','A'):
            raise runtime.KarelRuntimeError('Serial FILE is not readable',line)
        row=self.ports[int(handle.name[1])]
        if type(row['wait']) is not bool or type(row['final']) is not bool or not row['wait'] and not row['final']:
            raise runtime.KarelRuntimeError('Serial wait/final policy is invalid',line)
        if type(row['wait_output']) is not bool:raise runtime.KarelRuntimeError('Serial wait_output policy is invalid',line)
        return row

    def before_read(self,handle,line=None):
        self._active(handle,line,reading=True)
        if id(handle) in self._writes or handle._write_operation is not None:raise rt().KarelRuntimeError('Serial FILE has a pending WRITE',line)
        if id(handle) in self._pending:raise rt().KarelRuntimeError('Serial FILE has a pending READ',line)

    def bytes_ahead(self,handle,line=None):
        self._active(handle,line);return len(self.files[handle.name])-handle.position

    def seek(self,handle,position,line=None):
        self._active(handle,line);rt().integer(position,line)
        if id(handle) in self._writes or handle._write_operation is not None:raise rt().KarelRuntimeError('Serial FILE has a pending WRITE',line)
        return 2

    def read_bytes(self,handle,count,line=None):
        self._active(handle,line,reading=True)
        if id(handle) in self._writes or handle._write_operation is not None:raise rt().KarelRuntimeError('Serial FILE has a pending WRITE',line)
        if id(handle) in self._pending:raise rt().KarelRuntimeError('Serial FILE has a pending READ',line)
        if type(count) is not int or count<0:raise rt().KarelRuntimeError('Serial byte count must be a nonnegative INTEGER',line)
        if count>self.bytes_ahead(handle,line):
            handle.status=1;raise rt().KarelRuntimeError('End of finite serial input',line)
        start=handle.position;result=bytes(self.files[handle.name][start:start+count])
        handle.position+=count;handle.status=0;return result

    def write(self,handle,data,line=None):
        row=self._active(handle,line)
        if id(handle) in self._writes or handle._write_operation is not None:raise rt().KarelRuntimeError('Serial FILE has a pending WRITE',line)
        if handle.mode=='R':raise rt().KarelRuntimeError('Serial FILE is read-only',line)
        if type(data) is not bytes:raise rt().KarelRuntimeError('Serial output requires explicit bytes',line)
        if (len(self.files[handle.name])+len(row['output'])+len(data)>row['capacity']
                or self.used()+len(data)>self.limit):
            raise rt().KarelRuntimeError('Serial input/output byte capacity exceeded',line)
        row['output'].extend(data);handle.status=0

    def flush(self,handle,line=None):
        self._active(handle,line)
        if id(handle) in self._writes or handle._write_operation is not None:raise rt().KarelRuntimeError('Serial FILE has a pending WRITE',line)

    def close(self,handle,line=None):
        self._active(handle,line)
        if id(handle) in self._writes or handle._write_operation is not None:raise rt().KarelRuntimeError('Serial FILE has a pending WRITE; unwind it before CLOSE',line)
        if id(handle) in self._pending:raise rt().KarelRuntimeError('Serial FILE has a pending READ; cancel it before CLOSE',line)
        if handle.position:del self.files[handle.name][:handle.position]
        self._open.pop(id(handle));self.handles=[item for item in self.handles if item is not handle]
        handle.owner=None;handle.position=0;handle.xml_session=None

    def read_items(self,state,handle,targets,line=None,*,line_breaks=(),formats=None):
        """Opt-in cooperative READ, retaining the exact finite parser by default."""
        runtime=rt();row=self._active(handle,line,reading=True)
        if id(handle) in self._writes or handle._write_operation is not None:raise runtime.KarelRuntimeError('Serial FILE has a pending WRITE',line)
        if not row['wait']:
            return state.file_read(handle,targets,line,line_breaks=line_breaks,formats=formats)
        if id(handle) in self._pending:raise runtime.KarelRuntimeError('Serial FILE already has a pending READ',line)
        request = StreamRead(handle, targets, line_breaks, formats, 'Serial', line)
        start = handle.position
        if start + request.minimum_bytes(may_finalize=True) > row['capacity']:
            raise runtime.KarelRuntimeError('Atomic serial READ exceeds retained receive capacity', line)
        registration=self._open[id(handle)];pending=(state,registration,start)
        self._pending[id(handle)]=pending
        try:
            while True:
                row=self._active(handle,line,reading=True)
                runtime.check_file_read(handle,line)
                if (self._pending.get(id(handle)) is not pending or self._open.get(id(handle)) is not registration
                        or handle.position!=start or not row['wait']):
                    raise runtime.KarelRuntimeError('Serial pending READ registration or cursor changed',line)
                retained=self.files[handle.name]
                raw = bytes(retained[start:])
                result = request.probe(handle, raw, final=row['final'])
                if result is not None:
                    values, offset = result
                    request.publish(state, values)
                    handle.position = start + offset
                    handle.status = 0
                    return
                if row['final']:
                    raise runtime.KarelRuntimeError('End of finalized serial input before complete READ',line)
                if len(retained) >= row['capacity'] and not request.can_finalize(handle,raw):
                    raise runtime.KarelRuntimeError('Atomic serial READ cannot complete within retained receive capacity',line)
                root=runtime.task_root(state)
                if state._in_handler or root._in_handler:
                    raise runtime.KarelRuntimeError('Pending serial READ cannot wait inside a handler action',line)
                if state._scheduler is None and not getattr(root,'_sleep_injected',False):
                    raise runtime.KarelRuntimeError('Indefinite standalone serial wait requires an explicit sleeper callback',line)
                yield from runtime.delay_execution(state,10,line,scan_handlers=True)
                yield from runtime.checkpoint(state,line)
        except GeneratorExit:raise
        except BaseException:
            if handle.owner is self and self._open.get(id(handle)) is registration:handle.status=1
            raise
        finally:
            if self._pending.get(id(handle)) is pending:self._pending.pop(id(handle))

    def validate_write(self,handle,record,line=None):
        runtime=rt()
        if type(record) is not tuple or len(record)!=9 or type(record[8]) is not tuple or len(record[8])!=5:
            raise runtime.KarelRuntimeError('Serial pending WRITE record changed',line)
        row=self._active(handle,line)
        if (self._writes.get(id(handle)) is not record
                or self._open.get(id(handle)) is not record[1] or handle.position!=record[2]
                or row is not record[3] or row['output'] is not record[4] or self.files[handle.name] is not record[5]
                or type(row['capacity']) is not int or row['capacity']!=record[6]
                or type(self.limit) is not int or self.limit!=record[7] or not row['wait_output']
                or not any(item is handle for item in self.handles)
                or self.ports is not record[8][0] or self.files is not record[8][1]
                or runtime.task_root(record[0]) is not record[8][2]
                or self._writes is not record[8][3] or self._open is not record[8][4]):
            raise runtime.KarelRuntimeError('Serial pending WRITE registration or buffer identity changed',line)
        return row

    def write_items(self,state,handle,data,line=None):
        """Wait for space in a retained TX outbox, publishing one complete payload."""
        runtime=rt();row=self._active(handle,line)
        if not row['wait_output']:return self.write(handle,data,line)
        if handle.mode=='R':raise runtime.KarelRuntimeError('Serial FILE is read-only',line)
        if type(data) is not bytes:raise runtime.KarelRuntimeError('Serial output requires explicit bytes',line)
        if id(handle) in self._pending or id(handle) in self._writes:raise runtime.KarelRuntimeError('Serial FILE has pending I/O',line)
        if len(data)+len(self.files[handle.name])>min(row['capacity'],self.limit):
            raise runtime.KarelRuntimeError('Atomic serial WRITE exceeds retained port/bank capacity',line)
        record=(state,self._open[id(handle)],handle.position,row,row['output'],self.files[handle.name],row['capacity'],self.limit,(self.ports,self.files,runtime.task_root(state),self._writes,self._open))
        self._writes[id(handle)]=record
        try:
            while True:
                row=self.validate_write(handle,record,line);runtime.check_file_write(handle,line)
                if len(data)+len(self.files[handle.name])>min(row['capacity'],self.limit):
                    raise runtime.KarelRuntimeError('Atomic serial WRITE exceeds retained port/bank capacity',line)
                if (len(self.files[handle.name])+len(row['output'])+len(data)<=row['capacity']
                        and self.used()+len(data)<=self.limit):
                    row['output'].extend(data);handle.status=0;return
                if state._in_handler or runtime.task_root(state)._in_handler:
                    raise runtime.KarelRuntimeError('Pending serial WRITE cannot wait inside a handler action',line)
                if state._scheduler is None and not getattr(runtime.task_root(state),'_sleep_injected',False):
                    raise runtime.KarelRuntimeError('Indefinite standalone serial WRITE requires an explicit sleeper callback',line)
                yield from runtime.delay_execution(state,10,line,scan_handlers=True)
                yield from runtime.checkpoint(state,line)
        except GeneratorExit:raise
        except BaseException:
            if handle.owner is self and self._open.get(id(handle)) is record[1]:handle.status=1
            raise
        finally:
            if self._writes.get(id(handle)) is record:self._writes.pop(id(handle))

    def snapshot(self):
        return {port:dict(capacity=row['capacity'],input=bytes(self.files[f'P{port}:']),output=bytes(row['output']),
                **(dict(wait=True,final=row['final'])if row['wait']else{}),**(dict(wait_output=True)if row['wait_output']else{}))
            for port,row in sorted(self.ports.items())}

    def to_config(self):
        if self._open or self.handles:raise ValueError('Close live serial FILEs before saving context')
        return dict(limit=self.limit,ports={str(port):dict(capacity=row['capacity'],
            input={'hex':self.files[f'P{port}:'].hex()},output={'hex':row['output'].hex()},
            **(dict(wait=True,final=row['final'])if row['wait']else{}),**(dict(wait_output=True)if row['wait_output']else{}))for port,row in sorted(self.ports.items())})

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'limit','ports'}:
            raise ValueError('Unknown serial stream configuration fields')
        ports=config.get('ports',{})
        if type(ports) is not dict or any(type(key) is not str or not re.fullmatch(r'[1-5]',key)for key in ports):
            raise ValueError('Serial JSON port keys must be canonical strings 1 through 5')
        return cls({int(key):value for key,value in ports.items()},limit=config.get('limit',4*1024*1024))
