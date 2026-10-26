"""Explicit bounded DAQ pipes with portable binary records and FILE readers."""
import re
import struct
from weakref import WeakSet
from .extended import MemoryFiles,fail,path_node_size


DAQ_CONSTANTS={'DAQ_DRAM':0,'DAQ_CMOS':-1,'DAQ_SNAPSHT':1,'DAQ_STREAM':2,
    'DAQ_PIPREG':1,'DAQ_ACTIVE':2,'DAQ_CREATD':4,'DAQ_SNAPSH':8,
    'DAQ_1STRD':16,'DAQ_OVFLOW':32,'DAQ_FLUSH':64}
DAQ_NAMES={'DAQ_REGPIPE','DAQ_START','DAQ_STOP','DAQ_UNREG','DAQ_CHECKP','DAQ_WRITE'}


def rt():
    from . import runtime
    return runtime


def pipe_name(value):
    value=rt().ascii_string(value).upper()
    if not re.fullmatch(r'[A-Z0-9_][A-Z0-9_.-]{0,62}\.[A-Z0-9_]{1,8}',value) or '..' in value:
        raise ValueError('DAQ pipe requires a plain filename with an extension')
    return 'PIP:'+value


def encode(spec,value,line=None):
    """Portable little-endian scalar leaves, fixed ASCII strings, no padding."""
    runtime=rt();kind=spec[0]
    value=runtime.checked(spec,value,line)
    if kind=='ARRAY': return b''.join(encode(spec[2],item,line) for item in value.values)
    if kind in runtime.RECORD_TYPES:
        return b''.join(encode(field,value.values[name],line) for name,field in runtime.record_fields(spec))
    if kind=='JOINTPOS': return b''.join(encode(('REAL',),item,line) for item in value.values)
    if kind=='STRING': return value.encode('ascii').ljust(spec[1],b'\0')
    try:return struct.pack('<'+{'BYTE':'B','SHORT':'h','INTEGER':'i','REAL':'f','BOOLEAN':'?'}[kind],value)
    except (OverflowError,struct.error,KeyError) as exc:
        raise runtime.KarelRuntimeError('DAQ record cannot represent the supplied portable data',line) from exc


def append_stream(files,name,data,line=None,*,commit=True):
    """Preflight a whole batch; publish through explicitly supplied file backends."""
    from .storage import DirectoryFiles,atomic_bytes
    from .devices import DeviceFiles
    if type(files) not in (MemoryFiles,DirectoryFiles,DeviceFiles):return 7
    try:
        code,old=files.read_named(name)
        if code not in (0,1):return code
        old=old or b''
        if len(old)+len(data)>files.limit:return 5
        if type(files) is DirectoryFiles:
            key=files._key(name);path=files._path(key)
            if not path.parent.is_dir():return 7
        else:
            key=files.canonical(name) if type(files) is DeviceFiles else name
            files._check(key,old+data)
            if type(files) is DeviceFiles:files.reserve(key,len(old)+len(data),line=line)
        if commit:
            updated=old+data
            if type(files) is DirectoryFiles:atomic_bytes(path,updated)
            files.files[key]=bytearray(updated)
        return 0
    except (OSError,ValueError,rt().KarelRuntimeError):return 7


class Acquisition(MemoryFiles):
    def __init__(self,*,limit=16*1024*1024):
        super().__init__(limit=limit);self.pipes={};self.readers={};self._view_number=0

    def get(self,number,line=None):
        number=rt().integer(number,line)
        if not 1<=number<=5:fail('DAQ pipe number requires 1..5',line)
        return self.pipes.get(number)

    def register(self,number,memory,capacity,spec,name,stream_size,line=None):
        from .storage import collection_data_spec
        if self.get(number,line) is not None:return 3
        if memory not in (0,-1) or type(memory) is not int:return 2
        if (type(capacity) is not int or not 1<=capacity<=32767 or type(stream_size) is not int
                or not 0<=stream_size<=capacity):return 2
        try:key=pipe_name(name)
        except (ValueError,rt().KarelRuntimeError):return 2
        try:
            collection_data_spec(spec);width=path_node_size(spec,line)
        except (ValueError,rt().KarelRuntimeError):return 4
        if key in self.files:return 3
        if width<1 or width*capacity+sum(row['width']*row['capacity'] for row in self.pipes.values())>self.limit:return 5
        self.pipes[number]=dict(memory=memory,capacity=capacity,spec=spec,name=key,stream_size=stream_size,
            width=width,mode=0,starts=0,created=False,first_read=False,stream_dev='',pending=b'',writers=WeakSet())
        self.files[key]=bytearray();return 0

    def start(self,number,mode,device,files,line=None):
        row=self.get(number,line)
        if row is None:return 1
        if type(mode) is not int or mode not in (1,2):return 2
        device=rt().ascii_string(device,line)
        target=device+row['name'][4:] if row['stream_size'] else ''
        if row['stream_size']:
            if len(device)>180 or any(ord(c)<32 or ord(c)==127 for c in device):return 2
            if mode!=2:return 2
            code=append_stream(files,target,b'',line,commit=False)
            if code:return code
        if row['starts'] and (mode,device if row['stream_size'] else '')!=(row['mode'],row['stream_dev']):return 2
        if row['starts']>=32767:return 5
        if row['mode']!=mode and any(info['number']==number for info in self.readers.values()):return 3
        row.update(mode=mode,starts=row['starts']+1,created=True,stream_dev=device if row['stream_size'] else '')
        return 0

    def stop(self,number,force,files,line=None):
        row=self.get(number,line)
        if row is None:return 1
        force=rt().boolean(force,line);remaining=0 if force else max(0,row['starts']-1)
        if not remaining and row['pending']:
            code=append_stream(files,row['stream_dev']+row['name'][4:],row['pending'],line)
            if code:return code
            row['pending']=b''
        row['starts']=remaining;return 0

    def unregister(self,number,line=None):
        row=self.get(number,line)
        if row is None:return 1
        if row['starts'] or any(info['number']==number for info in self.readers.values()):return 3
        del self.files[row['name']];del self.pipes[number];return 0

    def write_record(self,state,number,spec,value,files,line=None):
        row=self.get(number,line)
        if row is None:return 1
        if not row['starts']:return 6
        if spec!=row['spec']:return 4
        try:data=encode(spec,value,line)
        except rt().KarelRuntimeError:return 4
        pending=row['pending']+data if row['stream_size'] else b''
        if row['stream_size'] and len(pending)>=row['stream_size']*row['width']:
            code=append_stream(files,row['stream_dev']+row['name'][4:],pending,line)
            if code:return code
            pending=b''
        buffer=self.files[row['name']]
        if len(buffer)==row['capacity']*row['width']:
            del buffer[:row['width']]
            for handle,info in self.readers.items():
                if info['number']==number and not info['snapshot']:
                    if handle.position<row['width']:info['overflow']=True
                    handle.position=max(0,handle.position-row['width'])
        buffer.extend(data);row['pending']=pending;row['writers'].add(rt().task_root(state));return 0

    def check(self,state,number,line=None):
        row=self.get(number,line)
        if row is None:return 0,0
        root=rt().task_root(state);flags=1|(2 if row['starts'] else 0)|(4 if row['created'] else 0)
        if row['mode']==1:flags|=8
        if row['first_read']:flags|=16
        readers=[(handle,info) for handle,info in self.readers.items() if info['number']==number and info['owner'] is root]
        if root not in row['writers'] and any(info['overflow'] for handle,info in readers):flags|=32
        available=max((len(self.files[handle.name])-handle.position for handle,info in readers),default=len(self.files[row['name']]))
        return flags,available

    def open_for(self,state,handle,mode,name,line=None):
        if handle.owner is not None:fail('FILE is already open',line)
        mode=rt().ascii_string(mode,line).upper();name=rt().ascii_string(name,line).upper()
        binary='B' in mode or handle.binary
        if mode.replace('B','') not in ('R','RO') or not binary or handle.xml:
            fail('DAQ pipe FILE requires binary read-only access',line)
        number=next((number for number,row in self.pipes.items() if row['name']==name),None)
        if number is None or not self.pipes[number]['created']:fail('DAQ pipe FILE has not been created',line)
        if len(self.readers)>=32:fail('DAQ pipe reader limit exceeded (32)',line)
        row=self.pipes[number];snapshot=row['mode']==1;key=name
        if snapshot:
            if sum(len(value) for key,value in self.files.items() if key.startswith('@DAQ_VIEW:'))+len(self.files[name])>self.limit:
                fail('DAQ snapshot reader byte limit exceeded',line)
            self._view_number+=1;key=f'@DAQ_VIEW:{self._view_number}'
            self.files[key]=self.files[name].copy()
        handle.name,handle.mode,handle.owner,handle.binary=key,'R',self,True
        handle.logical_name=name
        handle.position=0;handle.status=0;self.handles.append(handle)
        self.readers[handle]=dict(number=number,snapshot=snapshot,owner=rt().task_root(state),overflow=False)

    def after_read(self,handle,start,line=None):
        info=self.readers[handle];row=self.pipes[info['number']]
        if handle.position>start:row['first_read']=True
        if info['snapshot']:return
        self.trim(info['number'])

    def trim(self,number):
        row=self.pipes[number]
        handles=[other for other,value in self.readers.items() if value['number']==number and not value['snapshot']]
        consumed=min((other.position for other in handles),default=0)//row['width']*row['width']
        if consumed:
            del self.files[row['name']][:consumed]
            for other in handles:other.position-=consumed

    def close(self,handle,line=None):
        info=self.readers.pop(handle)
        if info['snapshot']:del self.files[handle.name]
        super().close(handle,line)
        if not info['snapshot']:self.trim(info['number'])

    def read_records(self,number,count=None,line=None):
        row=self.get(number,line)
        if row is None:fail('DAQ pipe is not registered',line)
        if any(info['number']==number for info in self.readers.values()):fail('Close DAQ FILE readers before host record reads',line)
        available=len(self.files[row['name']])//row['width'];count=available if count is None else count
        if type(count) is not int or not 0<=count<=available:fail('DAQ host read exceeds available records',line)
        size=count*row['width'];data=bytes(self.files[row['name']][:size])
        if size:
            row['first_read']=True
            if row['mode']==2:del self.files[row['name']][:size]
        return data

    def to_config(self):
        from .storage import typed_value
        if self.readers:raise ValueError('Close live DAQ FILE readers before saving context')
        rows=[]
        for number,row in sorted(self.pipes.items()):
            values={key:row[key] for key in ('memory','capacity','name','stream_size','mode','starts','created','first_read','stream_dev')}
            schema=typed_value(rt().UNINITIALIZED,row['spec'])['type']
            values.update(number=number,schema=schema,data=self.files[row['name']].hex(),pending=row['pending'].hex())
            rows.append(values)
        return {'limit':self.limit,'pipes':rows}

    @classmethod
    def from_config(cls,config):
        from .storage import tuple_spec
        if type(config) is not dict or set(config)-{'limit','pipes'}:raise ValueError('Unknown acquisition fields')
        result=cls(limit=config.get('limit',16*1024*1024));rows=config.get('pipes',[])
        if type(rows) is not list or len(rows)>5:raise ValueError('DAQ requires at most five pipe records')
        fields={'number','memory','capacity','name','stream_size','mode','starts','created','first_read','stream_dev','schema','data','pending'}
        for item in rows:
            if type(item) is not dict or set(item)!=fields:raise ValueError('Invalid saved DAQ pipe fields')
            number=item['number'];name=item['name'];spec=tuple_spec(item['schema'])
            if type(name) is not str or not name.startswith('PIP:'):raise ValueError('DAQ names require PIP:')
            try:code=result.register(number,item['memory'],item['capacity'],spec,name[4:],item['stream_size'])
            except rt().KarelRuntimeError as exc:raise ValueError(str(exc)) from exc
            if code:raise ValueError('Invalid saved DAQ registration')
            row=result.pipes[number]
            if (type(item['mode']) is not int or item['mode'] not in (0,1,2)
                    or type(item['starts']) is not int or not 0<=item['starts']<=32767
                    or type(item['created']) is not bool or type(item['first_read']) is not bool
                    or type(item['stream_dev']) is not str or not item['stream_dev'].isascii() or len(item['stream_dev'])>180
                    or any(ord(c)<32 or ord(c)==127 for c in item['stream_dev'])):
                raise ValueError('Invalid DAQ state metadata')
            if ((not item['created'] and (item['mode'] or item['starts'] or item['first_read'] or item['stream_dev']))
                    or item['created'] and not item['mode'] or item['starts'] and not item['created']
                    or item['stream_size'] and item['mode']==1 or not item['stream_size'] and item['stream_dev']):
                raise ValueError('Inconsistent DAQ lifecycle metadata')
            values=[]
            for key,maximum in (('data',row['capacity']*row['width']),('pending',row['stream_size']*row['width'])):
                text=item[key]
                if type(text) is not str or len(text)>maximum*2 or not re.fullmatch(r'(?:[0-9a-fA-F]{2})*',text):
                    raise ValueError('Invalid or excessive DAQ bytes')
                data=bytes.fromhex(text)
                if len(data)%row['width']:raise ValueError('DAQ data must contain complete records')
                values.append(data)
            if (not item['created'] and any(values)) or values[1] and (not item['starts'] or len(values[1])>=row['stream_size']*row['width']):
                raise ValueError('Inconsistent DAQ retained records')
            row.update({key:item[key] for key in ('mode','starts','created','first_read','stream_dev')})
            result.files[row['name']][:]=values[0];row['pending']=values[1]
        return result


def invoke(state,operation,args,line=None):
    runtime=rt();context=state.execution;bank=context.require('acquisition',line)
    if operation=='DAQ_CHECKP':
        flags,available=bank.check(state,args[0],line)
        args[1].set(flags,line);args[2].set(available,line);return
    if operation in ('DAQ_REGPIPE','DAQ_WRITE'):
        program,path=args[3:5] if operation=='DAQ_REGPIPE' else args[1:3]
        try:reference=context.resolve(state,runtime.ascii_string(program,line).strip() or state.program_name,runtime.ascii_string(path,line),line)
        except runtime.KarelRuntimeError:args[-1].set(1,line);return
        if operation=='DAQ_REGPIPE':code=bank.register(args[0],args[1],args[2],reference.spec,args[5],args[6],line)
        else:code=bank.write_record(state,args[0],reference.spec,reference.raw(),context.files,line)
    elif operation=='DAQ_START':code=bank.start(*args[:3],context.files,line)
    elif operation=='DAQ_STOP':code=bank.stop(*args[:2],context.files,line)
    else:code=bank.unregister(args[0],line)
    args[-1].set(code,line)
