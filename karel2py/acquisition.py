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
    """Check the aggregate once and pack portable leaves in declaration order."""
    runtime=rt()
    prepared=runtime.checked(spec,value,line)
    data=bytearray()
    formats={'BYTE':'B','SHORT':'h','INTEGER':'i','REAL':'f','BOOLEAN':'?'}

    def append(schema,item):
        kind=schema[0]
        if kind=='ARRAY':
            for element in item.values:
                append(schema[2],element)
        elif kind in runtime.RECORD_TYPES:
            for name,field in runtime.record_fields(schema):
                append(field,item.values[name])
        elif kind=='JOINTPOS':
            for axis in item.values:
                append(('REAL',),axis)
        else:
            item=runtime.require(runtime.checked(schema,item,line),line)
            if kind=='STRING':
                data.extend(item.encode('ascii').ljust(schema[1],b'\0'))
            else:
                data.extend(struct.pack('<'+formats[kind],item))

    try:
        append(spec,prepared)
    except (OverflowError,struct.error,KeyError) as exc:
        raise runtime.KarelRuntimeError('DAQ record cannot represent the supplied portable data',line) from exc
    return bytes(data)


def append_stream(files,name,data,line=None,*,commit=True,check=None):
    """Plan the existing prefix without reading it until a batch can publish."""
    from .devices import DeviceFiles
    from .fileops import _plan_snapshot,charge_file_bytes,publish_file_bytes
    from .storage import DirectoryFiles
    if type(files) not in (MemoryFiles,DirectoryFiles,DeviceFiles):return 7
    try:
        code,size,read_prefix=_plan_snapshot(files,name)
        if code not in (0,1):return code
        length=size+len(data)
        if length>files.limit:return 5
        if type(files) is DirectoryFiles:
            key=files._key(name)
            if not files._path(key).parent.is_dir():return 7
        else:
            key=files.canonical(name) if type(files) is DeviceFiles else name
            if type(files) is DeviceFiles:files.reserve(key,length,line=line)
    except (OSError,ValueError,rt().KarelRuntimeError):return 7
    if not commit:return 0

    charge_file_bytes(length,check)
    try:
        old=b''
        if read_prefix is not None:
            code,old=read_prefix()
            if code:return 3 if code==3 else 7
        code=publish_file_bytes(files,key,old+data,read_prefix is not None,line,obsolete=0)
        return 7 if code==2 else code
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
            leaves=rt().scalar_leaf_count(spec)
        except (ValueError,rt().KarelRuntimeError):return 4
        if key in self.files:return 3
        if width<1 or width*capacity+sum(row['width']*row['capacity'] for row in self.pipes.values())>self.limit:return 5
        self.pipes[number]=dict(memory=memory,capacity=capacity,spec=spec,name=key,stream_size=stream_size,
            width=width,leaves=leaves,revision=0,mode=0,starts=0,created=False,first_read=False,
            stream_dev='',pending=b'',writers=WeakSet())
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

    def _pipe_plan(self,number,row,line):
        files=self.files
        name=row['name']
        buffer=files.get(name)
        if type(buffer) is not bytearray or len(buffer)%row['width'] or len(buffer)>row['capacity']*row['width']:
            fail('DAQ ring has invalid record storage',line)
        size,limit,pending=len(buffer),self.limit,row['pending']
        keys=('name','spec','width','leaves','capacity','stream_size','starts','mode','created','stream_dev','revision')
        stamp=tuple(row[key] for key in keys)

        def verify():
            if (self.pipes.get(number) is not row or self.files is not files or files.get(name) is not buffer
                    or len(buffer)!=size or self.limit!=limit or row['pending'] is not pending
                    or tuple(row[key] for key in keys)!=stamp):
                fail('DAQ pipe changed during preparation',line)

        return buffer,verify

    def stop(self,number,force,files,line=None,*,check=None):
        row=self.get(number,line)
        if row is None:return 1
        force=rt().boolean(force,line);remaining=0 if force else max(0,row['starts']-1)
        if not remaining and row['pending']:
            _,verify=self._pipe_plan(number,row,line)

            def checkpoint():
                check()
                verify()

            code=append_stream(files,row['stream_dev']+row['name'][4:],row['pending'],line,
                               check=checkpoint if check is not None else None)
            if code:return code
            row['pending']=b''
        row['starts']=remaining;return 0

    def unregister(self,number,line=None):
        row=self.get(number,line)
        if row is None:return 1
        if row['starts'] or any(info['number']==number for info in self.readers.values()):return 3
        del self.files[row['name']];del self.pipes[number];return 0

    def write_record(self,state,number,spec,value,files,line=None,*,check=None,reference=None):
        from .fileops import charge_file_bytes

        row=self.get(number,line)
        if row is None:return 1
        if not row['starts']:return 6
        if spec!=row['spec']:return 4
        buffer,verify=self._pipe_plan(number,row,line)

        def checkpoint():
            if check is None:state.tick(line)
            else:check()
            verify()

        for _ in range(row['leaves']):
            checkpoint()
        width=row['width']
        batch_bytes=len(row['pending'])+width if row['stream_size'] else 0
        charge_file_bytes(width+batch_bytes,checkpoint)
        verify()
        if reference is not None and reference.raw() is not value:
            fail('DAQ source binding changed during record preparation',line)
        try:data=encode(spec,value,line)
        except rt().KarelRuntimeError:return 4
        if len(data)!=width:return 4
        pending=row['pending']+data if row['stream_size'] else b''
        if row['stream_size'] and len(pending)>=row['stream_size']*width:
            code=append_stream(files,row['stream_dev']+row['name'][4:],pending,line,check=checkpoint)
            if code:return code
            pending=b''
        if len(buffer)==row['capacity']*row['width']:
            del buffer[:row['width']]
            for handle,info in self.readers.items():
                if info['number']==number and not info['snapshot']:
                    if handle.position<row['width']:info['overflow']=True
                    handle.position=max(0,handle.position-row['width'])
        buffer.extend(data)
        row['pending']=pending
        row['revision']+=1
        row['writers'].add(rt().task_root(state))
        return 0

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

    def _snapshot_room(self,size,line):
        if len(self.readers)>=32:fail('DAQ pipe reader limit exceeded (32)',line)
        retained=sum(len(value) for key,value in self.files.items() if key.startswith('@DAQ_VIEW:'))
        if retained+size>self.limit:fail('DAQ snapshot reader byte limit exceeded',line)

    def open_for(self,state,handle,mode,name,line=None,*,check=None):
        from .fileops import charge_file_bytes

        if handle.owner is not None:fail('FILE is already open',line)
        mode=rt().ascii_string(mode,line).upper();name=rt().ascii_string(name,line).upper()
        binary='B' in mode or handle.binary
        if mode.replace('B','') not in ('R','RO') or not binary or handle.xml:
            fail('DAQ pipe FILE requires binary read-only access',line)
        number=next((number for number,row in self.pipes.items() if row['name']==name),None)
        if number is None or not self.pipes[number]['created']:fail('DAQ pipe FILE has not been created',line)
        row=self.pipes[number];snapshot=row['mode']==1;key=name
        if snapshot:
            buffer,verify=self._pipe_plan(number,row,line)
            size=len(buffer)
            identity=rt()._file_identity(handle)
            position=handle.position
            self._snapshot_room(size,line)
            charge_file_bytes(size,check)
            verify()
            if rt()._file_identity(handle)!=identity or handle.position!=position or handle in self.readers:
                fail('DAQ FILE binding changed during snapshot preparation',line)
            self._snapshot_room(size,line)
            data=buffer.copy()
            self._view_number+=1;key=f'@DAQ_VIEW:{self._view_number}'
            self.files[key]=data
        elif len(self.readers)>=32:
            fail('DAQ pipe reader limit exceeded (32)',line)
        handle.name,handle.mode,handle.owner,handle.binary=key,'R',self,True
        handle.logical_name=name
        handle.position=0;handle.status=0;self.handles.append(handle)
        self.readers[handle]=dict(number=number,snapshot=snapshot,owner=rt().task_root(state),overflow=False)

    def capture_reader(self,handle,line=None):
        readers=self.readers
        info=readers.get(handle)
        if info is None:fail('DAQ FILE requires an original reader registration',line)
        number=info['number']
        row=self.pipes[number]
        snapshot=info['snapshot']
        revision=row['revision']

        def matches():
            return (self.readers is readers and readers.get(handle) is info
                    and self.pipes.get(number) is row and info['number']==number
                    and info['snapshot'] is snapshot and (snapshot or row['revision']==revision))

        return matches

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
            row['revision']+=1
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
        size=count*row['width'];buffer=self.files[row['name']]
        with memoryview(buffer) as view, view[:size] as selected:
            data=selected.tobytes()
        if size:
            row['first_read']=True
            if row['mode']==2:
                del buffer[:size]
                row['revision']+=1
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
                if type(text) is not str or len(text)>maximum*2 or len(text)%2 or re.search(r'[^0-9a-fA-F]',text):
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
    files=context.files

    def check():
        state.tick(line)
        if context.acquisition is not bank or context.files is not files:
            fail('DAQ services changed during preparation',line)

    if operation=='DAQ_CHECKP':
        flags,available=bank.check(state,args[0],line)
        args[1].set(flags,line);args[2].set(available,line);return
    if operation in ('DAQ_REGPIPE','DAQ_WRITE'):
        program,path=args[3:5] if operation=='DAQ_REGPIPE' else args[1:3]
        try:reference=context.resolve(state,runtime.ascii_string(program,line).strip() or state.program_name,runtime.ascii_string(path,line),line)
        except runtime.KarelRuntimeError:args[-1].set(1,line);return
        if operation=='DAQ_REGPIPE':
            try:key=pipe_name(args[5])
            except (ValueError,runtime.KarelRuntimeError):args[-1].set(2,line);return
            if context.file_pipes is not None and key in context.file_pipes.files:code=3
            else:code=bank.register(args[0],args[1],args[2],reference.spec,args[5],args[6],line)
        else:
            code=bank.write_record(state,args[0],reference.spec,reference.raw(),files,line,
                                   check=check,reference=reference)
    elif operation=='DAQ_START':code=bank.start(*args[:3],files,line)
    elif operation=='DAQ_STOP':code=bank.stop(*args[:2],files,line,check=check)
    else:code=bank.unregister(args[0],line)
    args[-1].set(code,line)
