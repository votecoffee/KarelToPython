"""Portable state serialization and explicitly rooted filesystem services."""
from copy import deepcopy
import fnmatch
import json
import math
import os
import re
from pathlib import Path
import tempfile


def rt():
    from . import runtime
    return runtime


def tuple_spec(value):
    return tuple(tuple_spec(item) if isinstance(item,(list,tuple)) else item for item in value)


def typed_value(value, spec=None):
    """Encode the type as well as values, including partially initialized data."""
    runtime=rt()
    if spec is None:
        spec=getattr(value,'spec',None)
        if spec is None:
            spec=('BOOLEAN',) if type(value) is bool else ('INTEGER',) if type(value) is int else ('REAL',) if type(value) is float else ('STRING',254) if type(value) is str else None
    if spec is None or spec[0]=='FILE': raise ValueError('A serializable value requires an explicit data type')
    if spec[0] in ('PATH','QUEUE_TYPE'):
        with runtime._numeric_scope('pythonic'): payload=collection_payload(spec,value)
        return {'type':json.loads(json.dumps(spec)),'value':payload}
    return {'type':json.loads(json.dumps(spec)),'value':runtime.snapshot_value(value)}


def array_state_values(shape,payload):
    """Flatten only physical ARRAY dimensions; leave named element payloads intact."""
    if type(payload) is not list or len(payload)!=shape[0]: raise ValueError('ARRAY state shape mismatch')
    if len(shape)==1: return payload
    return [value for row in payload for value in array_state_values(shape[1:],row)]


def restore_value(spec, payload):
    runtime=rt(); spec=tuple_spec(spec)
    if spec[0]=='FILE': raise ValueError('FILE handles are not persistent values')
    if spec[0] in ('PATH','QUEUE_TYPE'): return restore_collection(spec,payload)
    if payload=={'uninitialized':True}: return runtime.UNINITIALIZED
    if payload=={'unknown_byte':True}:
        if spec!=('BYTE',): raise ValueError('Unknown BYTE marker requires BYTE storage')
        return runtime.UNKNOWN_BYTE
    if spec[0]=='ARRAY':
        result=runtime.Array(spec)
        try:
            values=array_state_values(result.shape,payload)
            restored=[restore_value(spec[2],item) for item in values]
        except (ValueError,runtime.KarelRuntimeError):
            # Earlier configurations accepted flat physical storage, including
            # singleton dimensions. Keep that explicit representation readable.
            if len(result.shape)==1 or type(payload) is not list or len(payload)!=len(result.values): raise
            restored=[restore_value(spec[2],item) for item in payload]
        result.values[:]=restored
        return result
    if spec[0]=='JOINTPOS':
        result=runtime.JointPosition(spec)
        # Runtime snapshots use a joints object; accept a plain list for configuration.
        values=payload.get('axes',payload.get('joints',payload.get('values'))) if type(payload) is dict else payload
        if type(values) is not list or len(values)!=len(result.values): raise ValueError('Joint state axis count mismatch')
        result.values[:]=[restore_value(('REAL',),item) for item in values]
        return result
    if spec[0] in runtime.RECORD_TYPES:
        result=runtime.Structure(spec)
        if type(payload) is not dict: raise ValueError('Record state must be an object')
        fields={key.upper():value for key,value in payload.items()}
        if set(fields)!=set(result.types): raise ValueError('Record state fields do not match its type')
        for key,member in result.types.items():
            result.values[key]=runtime.replace_value(result.values[key],restore_value(member,fields[key]))
        if runtime.fully_initialized(result): return runtime.checked(spec,result)
        return result
    return runtime.checked(spec,payload)


def decode_typed(row):
    if type(row) is not dict or set(row)!={'type','value'}: raise ValueError('Typed state requires exactly type and value')
    spec=row['type']
    if type(spec) is str:
        name=spec.upper()
        spec=rt().joint_spec(name) if name in rt().JOINT_TYPE_NAMES else (name,)
    spec=tuple_spec(spec)
    with rt()._numeric_scope('pythonic'): value=restore_value(spec,row['value'])
    return spec,value


def collection_data_spec(spec):
    """Validate the concrete, resource-free data schema of a PATH component."""
    runtime=rt()
    if type(spec) is not tuple or not spec: raise ValueError('Collection data requires a concrete type')
    kind=spec[0]
    if kind in ('INTEGER','REAL','BOOLEAN','BYTE','SHORT',*runtime.DATA_RECORD_TYPES):
        if spec!=(kind,): raise ValueError('Malformed collection scalar/record type')
    elif kind=='STRING':
        if len(spec)!=2 or type(spec[1]) is not int or not 1<=spec[1]<=254: raise ValueError('Collection STRING capacity requires 1..254')
    elif kind=='JOINTPOS':
        if len(spec)!=2 or type(spec[1]) is not int or not 1<=spec[1]<=9: raise ValueError('Collection JOINTPOS width requires 1..9')
    elif kind=='STRUCTURE':
        if len(spec)!=3 or type(spec[1]) is not str or not re.fullmatch(r'[A-Z_][A-Z_0-9]*',spec[1]) or type(spec[2]) is not tuple:
            raise ValueError('Collection STRUCTURE requires a canonical name and fields')
        names=set()
        for field in spec[2]:
            if (type(field) is not tuple or len(field)!=2 or type(field[0]) is not str
                    or not re.fullmatch(r'[A-Z_][A-Z_0-9]*',field[0]) or field[0] in names):
                raise ValueError('Collection STRUCTURE fields require distinct canonical names')
            names.add(field[0]);collection_data_spec(field[1])
    elif kind=='ARRAY':
        if len(spec) not in (3,4): raise ValueError('Malformed collection ARRAY type')
        if len(spec)==4 and (type(spec[3]) is not str or not re.fullmatch(r'[A-Z_][A-Z_0-9]*',spec[3])):
            raise ValueError('Collection ARRAY identity requires a canonical name')
        physical=spec[1] if type(spec[1]) is tuple else (spec[1],)
        if not 1<=len(physical)<=3 or any(type(size) is not int or not 1<=size<=32767 for size in physical):
            raise ValueError('Collection ARRAY dimensions require fixed sizes in 1..32767')
        collection_data_spec(spec[2]);shape=runtime.array_dimensions(spec)
        if spec[2][0]=='ARRAY' and runtime.array_identity(spec[2]) is None:
            raise ValueError('Nested collection ARRAY components require named types')
        if not 1<=len(shape)<=3 or any(type(size) is not int or not 1<=size<=32767 for size in shape):
            raise ValueError('Collection ARRAY dimensions require one through three fixed sizes')
    else: raise ValueError('Unsupported collection data type or embedded resource')
    if runtime.scalar_leaf_count(spec)>32767: raise ValueError('Collection component exceeds 32767 scalar leaves')


def collection_data_payload(spec,value):
    """Preserve partial data while checking known leaves and exact host shapes."""
    runtime=rt()
    if value is runtime.UNINITIALIZED: return {'uninitialized':True}
    if value is runtime.UNKNOWN_BYTE:
        if spec!=('BYTE',): raise ValueError('Unknown BYTE requires BYTE collection storage')
        return {'unknown_byte':True}
    if spec[0]=='ARRAY':
        if (type(value) is not runtime.Array or value.spec!=spec or value.shape!=runtime.array_shape(spec)
                or len(value.values)!=math.prod(runtime.array_shape(spec))):
            raise ValueError('Collection ARRAY storage does not match its schema')
        return [collection_data_payload(spec[2],item) for item in value.values]
    if spec[0] in runtime.RECORD_TYPES:
        fields=dict(runtime.record_fields(spec))
        if type(value) is not runtime.Structure or value.spec!=spec or value.types!=fields or set(value.values)!=set(fields):
            raise ValueError('Collection record storage does not match its schema')
        if spec[0] in runtime.DATA_RECORD_TYPES: runtime._record_uninitialized(value,spec)
        return {name:collection_data_payload(field,value.values[name]) for name,field in fields.items()}
    if spec[0]=='JOINTPOS':
        if type(value) is not runtime.JointPosition or value.spec!=spec or len(value.values)!=spec[1]:
            raise ValueError('Collection joint storage does not match its schema')
        return {'axes':[collection_data_payload(('REAL',),axis) for axis in value.values]}
    if spec[0]=='STRING' and (type(value) is not str or len(value)>spec[1]): raise ValueError('Collection STRING exceeds its declared capacity')
    checked=runtime.checked(spec,value)
    if checked is runtime.UNINITIALIZED: raise ValueError('Collection missing values require an explicit marker')
    return runtime.snapshot_value(checked)


def collection_payload(spec,value):
    runtime=rt()
    if spec==('QUEUE_TYPE',):
        if type(value) is not runtime.QueueValue or value.spec!=spec or type(value.initialized) is not bool:
            raise ValueError('Malformed QUEUE_TYPE state')
        sequence=runtime.checked(('INTEGER',),value.sequence)
        if sequence<0 or type(value.entries) is not list or len(value.entries)>32767: raise ValueError('Invalid queue sequence or entry count')
        entries=[];seen=set()
        for pair in value.entries:
            if type(pair) not in (tuple,list) or len(pair)!=2: raise ValueError('Queue entries require sequence/value pairs')
            number,item=(runtime.checked(('INTEGER',),member) for member in pair)
            if not 1<=number<=sequence or number in seen: raise ValueError('Queue entry sequences require distinct positive IDs no greater than the sequence counter')
            seen.add(number);entries.append([number,item])
        if not value.initialized and (sequence or entries or value.buffer is not None): raise ValueError('Uninitialized queue cannot contain entries, a sequence or a buffer')
        if value.buffer is not None:
            buffer=value.buffer
            if (type(buffer) is not runtime.Array or len(runtime.array_dimensions(buffer.spec))!=1
                    or buffer.spec[2]!=('INTEGER',) or buffer.shape!=runtime.array_shape(buffer.spec)
                    or len(buffer.values)!=math.prod(runtime.array_shape(buffer.spec))
                    or len(entries)>len(buffer.values)):
                raise ValueError('Queue backing ARRAY cannot hold its entries')
        return dict(initialized=value.initialized,sequence=sequence,entries=entries)
    if len(spec)!=3 or spec[0]!='PATH': raise ValueError('Malformed PATH type')
    for component in spec[1:]:
        if component is not None:
            collection_data_spec(component)
            if component[0]!='STRUCTURE': raise ValueError('PATH NODEDATA/PATHHEADER require named STRUCTURE types')
    if type(value) is not runtime.PathValue or value.spec!=spec or type(value.nodes) is not list or len(value.nodes)>32767:
        raise ValueError('PATH storage does not match its type or node limit')
    if spec[2] is None and value.data is not None: raise ValueError('Headerless PATH cannot contain header data')
    return dict(nodes=[collection_data_payload(value.node_spec,node) for node in value.nodes],
                data=collection_data_payload(spec[2],value.data) if spec[2] else None)


def restore_collection(spec,payload):
    runtime=rt()
    if type(payload) is not dict: raise ValueError('Collection state requires an object')
    if spec==('QUEUE_TYPE',):
        if set(payload)!={'initialized','sequence','entries'} or type(payload['entries']) is not list:
            raise ValueError('Queue state requires initialized, sequence and entries')
        value=runtime.QueueValue();value.initialized=payload['initialized'];value.sequence=payload['sequence'];value.entries=payload['entries']
        normalized=collection_payload(spec,value)
        value.entries=[tuple(pair) for pair in normalized['entries']]
        return value
    if len(spec)!=3 or spec[0]!='PATH' or set(payload)!={'nodes','data'} or type(payload['nodes']) is not list or len(payload['nodes'])>32767:
        raise ValueError('PATH state requires nodes and data within the node limit')
    # Validate the schema before constructing its records or arrays.
    for component in spec[1:]:
        if component is not None:
            collection_data_spec(component)
            if component[0]!='STRUCTURE': raise ValueError('PATH NODEDATA/PATHHEADER require named STRUCTURE types')
    def check_markers(item):
        if type(item) is dict:
            if 'uninitialized' in item or 'unknown_byte' in item:
                if len(item)!=1 or next(iter(item.values())) is not True: raise ValueError('Collection missing markers require exactly a true Boolean flag')
            else:
                for member in item.values(): check_markers(member)
        elif type(item) is list:
            for member in item: check_markers(member)
    check_markers(payload)
    value=runtime.PathValue(spec)
    value.nodes=[restore_value(value.node_spec,node) for node in payload['nodes']]
    value.data=restore_value(spec[2],payload['data']) if spec[2] else None
    if collection_payload(spec,value)!=payload: raise ValueError('PATH payload must preserve canonical fields, capacities and missing markers')
    return value


def write_json(path, data):
    """Write one explicitly named state file atomically, without creating parents."""
    target=Path(path)
    payload=(json.dumps(data,indent=2,allow_nan=False)+'\n').encode('utf-8')
    atomic_bytes(target,payload)


def atomic_bytes(target, data):
    target=Path(target)
    descriptor,name=tempfile.mkstemp(prefix='.'+target.name+'.',suffix='.tmp',dir=target.parent)
    temporary=Path(name)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,target)
    finally:
        if temporary.exists(): temporary.unlink()


class DirectoryFiles:
    """FILE backend rooted in a caller-selected directory; buffered until close.

    Source names are relative POSIX paths, optionally prefixed by an explicit
    device mapping. Symlinks and path traversal are rejected on every operation.
    """
    def __init__(self,root,*,devices=None,limit=16*1024*1024):
        from .extended import MemoryFiles
        self.root=Path(root).resolve(strict=True)
        if not self.root.is_dir(): raise ValueError('Filesystem root must be a directory')
        self.devices={str(key).upper():str(value) for key,value in (devices or {}).items()}
        self.memory=MemoryFiles(limit=limit); self.files=self.memory.files; self.limit=limit
        self.handles=[]
        for value in self.devices.values(): self._path(value or '.',directory=True)

    def _path(self,name,*,directory=False):
        runtime=rt(); name=runtime.ascii_string(name).replace('\\','/')
        if ':' in name:
            device,tail=name.split(':',1)
            if device.upper() not in self.devices: raise ValueError('Unmapped file device')
            name='/'.join(part for part in (self.devices[device.upper()],tail) if part)
        parts=name.split('/')
        if not name or name.startswith('/') or any(part in ('..','') for part in parts) or '\0' in name:
            raise ValueError('File name must stay relative to its explicit root')
        target=self.root
        for part in parts:
            target=target/part
            if target.is_symlink(): raise ValueError('Symlink FILE paths are unsupported')
        resolved=target.resolve()
        if not resolved.is_relative_to(self.root) or not directory and resolved==self.root: raise ValueError('File path escapes its root')
        return resolved

    def _key(self,name): return self._path(name).relative_to(self.root).as_posix()

    def _busy(self,key): return any(handle.owner is self and os.path.normcase(handle.name)==os.path.normcase(key) for handle in self.handles)

    def open(self,handle,mode,name,line=None):
        if handle.owner is not None: raise rt().KarelRuntimeError('FILE is already open',line)
        try:
            key=self._key(name); path=self._path(key)
            if self._busy(key): raise ValueError('File is already open through this backend')
            if path.exists():
                if not path.is_file() or path.stat().st_size>self.limit: raise ValueError('Invalid file or file size limit exceeded')
                self.files[key]=bytearray(path.read_bytes())
            elif key in self.files: del self.files[key]
            self.memory.open(handle,mode,key,line); handle.owner=self; self.handles.append(handle)
        except (OSError,ValueError) as exc: raise rt().KarelRuntimeError('Filesystem OPEN failed: '+str(exc),line) from exc

    def flush(self,handle,line=None):
        handle.require_open(line)
        if handle.mode=='R': return
        try:
            path=self._path(handle.name)
            if not path.parent.is_dir(): raise ValueError('File parent directory does not exist')
            atomic_bytes(path,bytes(self.files[handle.name]))
        except (OSError,ValueError) as exc: raise rt().KarelRuntimeError('Filesystem flush failed: '+str(exc),line) from exc

    def close(self,handle,line=None):
        self.flush(handle,line); handle.owner=None
        self.handles=[item for item in self.handles if item is not handle]
        self.memory.handles=[item for item in self.memory.handles if item is not handle]

    def write(self,handle,data,line=None):
        old=bytes(self.files.get(handle.name,b'')); position=handle.position
        self.memory.write(handle,data,line)
        if handle.interactive:
            try: self.flush(handle,line)
            except Exception:
                self.files[handle.name]=bytearray(old); handle.position=position; raise

    def read_bytes(self,handle,count,line=None): return self.memory.read_bytes(handle,count,line)

    def snapshot(self): return self.memory.snapshot()

    def read_named(self,name):
        key=self._key(name)
        if self._busy(key): return 3,None
        path=self._path(key)
        if not path.exists(): return 1,None
        if not path.is_file() or path.stat().st_size>self.limit: raise ValueError('Invalid file or file size limit exceeded')
        with path.open('rb') as stream: data=stream.read(self.limit+1)
        if len(data)>self.limit: raise ValueError('File size limit exceeded')
        return 0,data

    def list_names(self,pattern='*'):
        # Validate the non-wildcard path components before traversing the selected root.
        self._path(pattern.replace('*','x').replace('?','x'))
        if ':' in pattern:
            device,tail=pattern.split(':',1); pattern='/'.join(part for part in (self.devices[device.upper()],tail) if part)
        names=set()
        for path in self.root.rglob('*'):
            if path.is_symlink(): continue
            relative=path.relative_to(self.root).as_posix()
            if path.is_file() and fnmatch.fnmatchcase(relative,pattern):
                self._path(relative); names.add(relative)
        names.update(name for name in self.files if self._busy(name) and fnmatch.fnmatchcase(name,pattern))
        return sorted(names)

    def copy(self,source,target,overwrite=False):
        source=self._key(source); target=self._key(target)
        if self._busy(source) or self._busy(target): return 3
        src=self._path(source); dst=self._path(target)
        if not src.is_file(): return 1
        if dst.exists() and not overwrite: return 2
        if src.stat().st_size>self.limit: raise ValueError('File size limit exceeded')
        data=src.read_bytes(); atomic_bytes(dst,data); self.files[target]=bytearray(data); return 0

    def delete(self,name):
        key=self._key(name)
        if self._busy(key): return 3
        path=self._path(key)
        if not path.is_file(): return 1
        path.unlink(); self.files.pop(key,None); return 0

    def rename(self,source,target):
        source=self._key(source); target=self._key(target)
        if self._busy(source) or self._busy(target): return 3
        src=self._path(source); dst=self._path(target)
        if not src.is_file(): return 1
        if dst.exists(): return 2
        src.rename(dst)
        if source in self.files: self.files[target]=self.files.pop(source)
        return 0

    def move(self,specification,*,check=None):
        from .fileops import move_files
        return move_files(self,specification,check=check)


def context_config(context):
    result={}
    if context.teach_programs is not None: result['teach_programs']=context.teach_programs.to_config()
    if context.peers is not None: result['peers']=context.peers.to_config()
    if context.program_attributes is not None: result['program_attributes']=context.program_attributes.to_config()
    if context.config_text is not None: result['config_text']=context.config_text.to_config()
    if context.programs is not None: result['programs']=context.programs.to_config()
    if context.calendar is not None: result['calendar']=context.calendar.to_config()
    if context.local_handlers: result['local_handlers']=True
    if context.numeric is not None: result['numeric']=context.numeric.to_config()
    if context.strings is not None: result['strings']={'count':context.strings.count,'capacity':context.strings.capacity,'values':{str(k):v for k,v in context.strings.snapshot().items()}}
    if context.positions is not None:
        result['positions']={'count':context.positions.count,'groups':list(context.positions.groups),'values':{f'{group}:{number}':typed_value(value) for (group,number),value in context.positions.snapshot().items()}}
    for name in ('strings','positions'):
        bank=getattr(context,name)
        if bank is not None and bank.comments.values: result[name]['comments']={str(k):v for k,v in bank.comments.snapshot().items()}
    if context.ports is not None:
        values={}
        for (kind,number),value in context.ports.snapshot().items(): values.setdefault(kind,{})[str(number)]=value
        result['ports']={'counts':context.ports.counts.copy(),'values':values}
        if context.ports.configuration is not None: result['ports']['configuration']=context.ports.configuration
        if context.ports.type_codes: result['ports']['type_codes']={str(k):v for k,v in context.ports.type_codes.items()}
        if context.ports.comments:
            comments={}
            for (kind,number),value in context.ports.comments.items(): comments.setdefault(kind,{})[str(number)]=value
            result['ports']['comments']=comments
        if context.ports.simulated:
            simulated={}
            for kind,number in sorted(context.ports.simulated): simulated.setdefault(kind,[]).append(number)
            result['ports']['simulated']=simulated
    if context.files is not None:
        result['files']={name:{'hex':value.hex()} for name,value in context.files.snapshot().items()}
    if context.variables.bindings:
        result['variables']=[dict(program=program,path=path,**typed_value(reference.raw(),reference.spec)) for (program,path),reference in sorted(context.variables.bindings.items())]
    variables={(row['program'],row['path']):row for row in result.get('variables',[])}
    for name,state in context.variables.programs.items():
        for path,spec in state.types.items():
            if spec[0]!='FILE':
                value=state.values[path]
                if isinstance(value,rt().Reference): value=value.raw()
                variables[name,path]=dict(program=name,path=path,**typed_value(value,spec))
    if variables: result['variables']=[variables[key] for key in sorted(variables)]
    if context.events is not None: result['events']=context.events.snapshot()
    if context.semaphores is not None: result['semaphores']=context.semaphores.to_config()
    if context.errors is not None: result['errors']=context.errors.to_config()
    if context.parameters is not None: result['parameters']=context.parameters.to_config()
    if context.robot is not None:
        config=context.robot.to_config()
        if config is not None: result['robot']=config
    return result
