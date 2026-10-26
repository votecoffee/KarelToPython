"""Explicit offline socket messaging and circular PIP FILE backends."""
import re
from .extended import MemoryFiles,fail


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


class Messaging(MemoryFiles):
    """Scripted endpoints and ping results; never create host sockets or DNS calls."""
    def __init__(self,ports=None,*,hosts=None,limit=4*1024*1024):
        super().__init__(limit=limit);self.ports={};self.hosts={}
        if ports is not None and (type(ports) is not dict or len(ports)>16):raise ValueError('Messaging requires at most sixteen ports')
        remaining=limit
        for tag,row in (ports or {}).items():
            key=tag_name(tag) if type(tag) is str else None
            if key is None or key in self.ports or type(row) is not dict or set(row)-{'mounted','available','connected','input','output'}:
                raise ValueError('Invalid or duplicate messaging port')
            flags={name:row.get(name,False if name=='connected' else True) for name in ('mounted','available','connected')}
            if any(type(value) is not bool for value in flags.values()) or flags['connected'] and not (flags['mounted'] and flags['available']):
                raise ValueError('Inconsistent messaging port flags')
            incoming=data_bytes(row.get('input',b''),remaining);remaining-=len(incoming)
            outgoing=data_bytes(row.get('output',b''),remaining);remaining-=len(outgoing)
            self.files[key]=bytearray(incoming);self.ports[key]={**flags,'output':bytearray(outgoing)}
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
        elif operation=='DISMOUNT_DEV':row.update(mounted=False,connected=False)
        elif operation=='MSG_CONNECT':
            if not row['mounted'] or not row['available']:return 4
            row['connected']=True
        elif operation=='MSG_DISCO':row['connected']=False
        else:raise ValueError('Unknown messaging state operation')
        return 0

    def ping(self,host):
        key=self.host_name(host)
        return 2 if key is None else self.hosts.get(key,1)

    def set_available(self,tag,available):
        key=tag_name(tag)
        if key not in self.ports or type(available) is not bool:raise ValueError('Availability requires a configured port and Boolean')
        self.ports[key]['available']=available
        if not available:self.ports[key]['connected']=False

    def feed(self,tag,data):
        key=tag_name(tag)
        if key not in self.ports:raise ValueError('Input requires a configured messaging tag')
        data=data_bytes(data,self.limit-self.used())
        if self.used()+len(data)>self.limit:raise ValueError('Combined socket data exceeds its bank limit')
        self.files[key].extend(data)

    def take_output(self,tag,count=None):
        key=tag_name(tag)
        if key not in self.ports:raise ValueError('Output requires a configured messaging tag')
        buffer=self.ports[key]['output'];count=len(buffer) if count is None else count
        if type(count) is not int or not 0<=count<=len(buffer):raise ValueError('Socket output count exceeds queued bytes')
        data=bytes(buffer[:count]);del buffer[:count];return data

    def connected(self,handle,line=None):
        handle.require_open(line);row=self.ports[handle.name]
        if not all(row[name] for name in ('mounted','available','connected')):fail('Offline socket endpoint is disconnected',line)
        return row

    def open_for(self,state,handle,mode,name,line=None):
        mode,binary=access_mode(handle,mode,line);key=tag_name(name)
        if key not in self.ports:fail('Socket FILE requires an explicitly configured C1:..C8:/S1:..S8: tag',line)
        if self._busy(key):fail('Socket endpoint already has an open FILE',line)
        row=self.ports[key]
        if not all(row[name] for name in ('mounted','available','connected')):fail('Offline socket endpoint is disconnected',line)
        handle.name,handle.mode,handle.owner,handle.binary=key,mode,self,binary
        handle.logical_name=key;handle.position=0;handle.status=0;self.handles.append(handle)

    def before_read(self,handle,line=None):self.connected(handle,line)
    def read_bytes(self,handle,count,line=None):self.connected(handle,line);return super().read_bytes(handle,count,line)

    def after_read(self,handle,start,line=None):
        if handle.position:del self.files[handle.name][:handle.position];handle.position=0

    def write(self,handle,data,line=None):
        row=self.connected(handle,line)
        if handle.mode=='R':fail('Socket FILE is read-only',line)
        if self.used()+len(data)>self.limit:fail('Combined socket data exceeds its bank limit',line)
        row['output'].extend(data);handle.status=0

    def to_config(self):
        if self.handles:raise ValueError('Close live messaging FILEs before saving context')
        ports={key:{**{name:row[name] for name in ('mounted','available','connected')},
            'input':{'hex':self.files[key].hex()},'output':{'hex':row['output'].hex()}} for key,row in sorted(self.ports.items())}
        return {'limit':self.limit,'ports':ports,'hosts':dict(sorted(self.hosts.items()))}

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'limit','ports','hosts'}:raise ValueError('Unknown messaging fields')
        return cls(config.get('ports'),hosts=config.get('hosts'),limit=config.get('limit',4*1024*1024))


class FilePipes(MemoryFiles):
    """Bounded circular byte histories, with independent FILE read cursors."""
    def __init__(self,*,limit=16*1024*1024):super().__init__(limit=limit);self.pipes={}

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
        if mode=='W':
            self.files[key].clear()
            for other in self.handles:
                if other.name==key:other.position=0
        handle.name,handle.mode,handle.owner,handle.binary=key,mode,self,binary
        handle.logical_name=key;handle.position=0;handle.status=0;self.handles.append(handle)

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
                if other.name==handle.name:other.position=max(0,other.position-dropped)
        handle.status=0

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
