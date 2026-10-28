"""Finite explicitly supplied serial byte streams; never open host devices."""
import re
from .communications import data_bytes


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
        self.limit=limit;self.ports={};self.files={};self.handles=[];self._open={}
        for port,row in ports.items():
            port=port_number(port)
            if type(row) is not dict or set(row)-{'capacity','input','output'}:
                raise ValueError('Unknown serial stream fields')
            capacity=row.get('capacity',limit)
            if type(capacity) is not int or not 1<=capacity<=limit:
                raise ValueError('Serial port capacity must be an INTEGER in 1..bank limit')
            incoming=data_bytes(row.get('input',b''),capacity)
            outgoing=data_bytes(row.get('output',b''),capacity-len(incoming))
            self.ports[port]=dict(capacity=capacity,output=bytearray(outgoing))
            self.files[f'P{port}:']=bytearray(incoming)
        if self.used()>limit:raise ValueError('Combined serial input/output exceeds bank limit')

    def used(self):
        return sum(len(value) for value in self.files.values())+sum(len(row['output']) for row in self.ports.values())

    def _port(self,port):
        port=port_number(port)
        if port not in self.ports:raise ValueError('Serial stream port is not explicitly configured')
        return port

    def feed(self,port,data):
        """Append finite host-supplied RX bytes without opening a device."""
        port=self._port(port);key=f'P{port}:';row=self.ports[port]
        remaining=min(row['capacity']-len(self.files[key])-len(row['output']),self.limit-self.used())
        data=data_bytes(data,remaining)
        self.files[key].extend(data)

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
        return self.ports[int(handle.name[1])]

    def before_read(self,handle,line=None):self._active(handle,line,reading=True)

    def bytes_ahead(self,handle,line=None):
        self._active(handle,line);return len(self.files[handle.name])-handle.position

    def seek(self,handle,position,line=None):
        self._active(handle,line);rt().integer(position,line)
        return 2

    def read_bytes(self,handle,count,line=None):
        self._active(handle,line,reading=True)
        if type(count) is not int or count<0:raise rt().KarelRuntimeError('Serial byte count must be a nonnegative INTEGER',line)
        if count>self.bytes_ahead(handle,line):
            handle.status=1;raise rt().KarelRuntimeError('End of finite serial input',line)
        start=handle.position;result=bytes(self.files[handle.name][start:start+count])
        handle.position+=count;handle.status=0;return result

    def write(self,handle,data,line=None):
        row=self._active(handle,line)
        if handle.mode=='R':raise rt().KarelRuntimeError('Serial FILE is read-only',line)
        if type(data) is not bytes:raise rt().KarelRuntimeError('Serial output requires explicit bytes',line)
        if (len(self.files[handle.name])+len(row['output'])+len(data)>row['capacity']
                or self.used()+len(data)>self.limit):
            raise rt().KarelRuntimeError('Serial input/output byte capacity exceeded',line)
        row['output'].extend(data);handle.status=0

    def flush(self,handle,line=None):self._active(handle,line)

    def close(self,handle,line=None):
        self._active(handle,line)
        if handle.position:del self.files[handle.name][:handle.position]
        self._open.pop(id(handle));self.handles=[item for item in self.handles if item is not handle]
        handle.owner=None;handle.position=0;handle.xml_session=None

    def snapshot(self):
        return {port:dict(capacity=row['capacity'],input=bytes(self.files[f'P{port}:']),output=bytes(row['output']))
            for port,row in sorted(self.ports.items())}

    def to_config(self):
        if self._open or self.handles:raise ValueError('Close live serial FILEs before saving context')
        return dict(limit=self.limit,ports={str(port):dict(capacity=row['capacity'],
            input={'hex':self.files[f'P{port}:'].hex()},output={'hex':row['output'].hex()})for port,row in sorted(self.ports.items())})

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'limit','ports'}:
            raise ValueError('Unknown serial stream configuration fields')
        ports=config.get('ports',{})
        if type(ports) is not dict or any(type(key) is not str or not re.fullmatch(r'[1-5]',key)for key in ports):
            raise ValueError('Serial JSON port keys must be canonical strings 1 through 5')
        return cls({int(key):value for key,value in ports.items()},limit=config.get('limit',4*1024*1024))
