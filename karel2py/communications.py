"""Explicit offline socket messaging and circular PIP FILE backends."""
import re
import fnmatch
import struct
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

    def list_names(self,pattern='*'):
        pattern=rt().ascii_string(pattern).upper()
        if pattern.startswith('PIP:'):pattern=pattern[4:]
        if pattern.startswith('/'):pattern=pattern[1:]
        if (not pattern or len(pattern)>72 or '..' in pattern
                or re.fullmatch(r'[A-Z0-9_.*?\-]+',pattern) is None):
            raise ValueError('Pipe listing requires a plain basename pattern with star/question wildcards')
        return sorted(key for key in self.pipes if fnmatch.fnmatchcase(key,'PIP:'+pattern))

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
        if type(targets) not in (list,tuple):fail('Pipe READ requires scalar references',line)
        line_breaks=runtime._read_line_breaks(len(targets),line_breaks,line)
        for target in targets:
            if type(target) is not runtime.Reference:fail('Pipe READ requires ordinary writable scalar targets',line)
            runtime._read_scalar_spec(target.spec,line)
        formats=[()] * len(targets) if formats is None else formats
        if type(formats) not in (list,tuple) or len(formats)!=len(targets):fail('Pipe READ requires one format per scalar target',line)
        formats=[runtime.read_formats(target.spec,field,line) for target,field in zip(targets,formats)]
        widths=[]
        if handle.binary:
            if line_breaks:fail('CR is not a binary READ field',line)
            from .extended import binary_format
            for target,field in zip(targets,formats):
                if target.spec[0]=='STRING' and not field:field=(target.spec[1],)
                widths.append(binary_format(target.spec[0],field,line))
            if sum(width for width,code in widths)>self.pipes[handle.name]['sectors']*1024:
                fail('Atomic pipe READ exceeds circular capacity',line)
        request=dict(line=line,targets=[dict(type=target.spec[0],type_spec=target.spec,
            **({'format_specifiers':field} if field else {})) for target,field in zip(targets,formats)])
        if line_breaks:request['line_breaks']=list(line_breaks)
        if id(handle) in self._reads:fail('Pipe FILE already has an active READ',line)
        self._reads[id(handle)]=state
        try:
            while True:
                self.before_read(handle,line)
                start=handle.position;available=self.bytes_ahead(handle,line)
                raw=bytes(self.files[handle.name][start:start+available]);waiting=getattr(handle,'pipe_wait',None)==1
                result=None
                if handle.binary:
                    size=sum(width for width,code in widths)
                    if len(raw)>=size:
                        offset=0;values=[]
                        for target,(width,code) in zip(targets,widths):
                            data=raw[offset:offset+width];offset+=width
                            if code and handle.reverse:code='>'+code[1:]
                            try:value=data.decode('ascii') if code is None else struct.unpack(code,data)[0]
                            except (UnicodeError,struct.error) as exc:raise runtime.KarelRuntimeError('Invalid binary pipe field: '+str(exc),line) from exc
                            runtime.checked(target.spec,value,line);values.append(value)
                        result=values,offset
                else:
                    try:text=raw.decode('ascii')
                    except UnicodeDecodeError as exc:raise runtime.KarelRuntimeError('Text pipe FILE requires ASCII data',line) from exc
                    reader=runtime.TextInput(text,terminator=handle.eol,field_mode=handle.field,final=not waiting)
                    try:values=reader(request)
                    except runtime.TextInputIncomplete:pass
                    else:result=values,reader.offset
                if result is not None:
                    values,offset=result;previous=state._read
                    try:
                        state._read=lambda request:values
                        state.read_items(targets,line,line_breaks=line_breaks,formats=formats)
                    finally:state._read=previous
                    handle.position=start+offset;handle.status=0;return
                if not waiting:
                    handle.status=1;fail('End of pipe FILE',line)
                if state._scheduler is None and not getattr(runtime.task_root(state),'_sleep_injected',False):
                    fail('Indefinite standalone pipe wait requires an explicit sleeper callback',line)
                yield from runtime.delay_execution(state,10,line)
                yield from runtime.checkpoint(state,line)
        except GeneratorExit:raise
        except BaseException:
            handle.status=1;raise
        finally:self._reads.pop(id(handle),None)

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
