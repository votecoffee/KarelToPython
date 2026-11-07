"""Portable state serialization and explicitly rooted filesystem services."""
from contextlib import closing
from copy import deepcopy
import errno
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
    if spec is None or runtime.file_storage_type(spec): raise ValueError('A serializable value requires an explicit data type without FILE storage')
    if runtime.collection_array_type(spec):
        with runtime._numeric_scope('pythonic'):payload=collection_array_payload(spec,value)
        return {'type':json.loads(json.dumps(spec)),'value':payload}
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
    if runtime.file_storage_type(spec): raise ValueError('FILE handles and FILE ARRAYs are not persistent values')
    if runtime.collection_array_type(spec):return restore_collection_array(spec,payload)
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


def collection_array_cost(spec):
    """Validate concrete containers and count descriptors plus immediate headers."""
    runtime=rt()
    if type(spec) is not tuple or not spec:raise ValueError('Collection ARRAY requires a concrete type')
    if spec[0]!='ARRAY':return None
    cells=1;rank=0;depth=0;current=spec
    while current[0]=='ARRAY':
        if type(current) is not tuple or len(current) not in (3,4):raise ValueError('Malformed collection ARRAY schema')
        try:identity=runtime.array_identity(current)
        except runtime.KarelRuntimeError as exc:raise ValueError('Malformed collection ARRAY identity') from exc
        if depth and identity is None:raise ValueError('Nested collection ARRAY components require names')
        if identity is not None and not re.fullmatch(r'[A-Z_][A-Z_0-9]*',identity):raise ValueError('Invalid collection ARRAY identity')
        shape=runtime.array_shape(current);rank+=len(shape);depth+=1
        if not shape or rank>3:raise ValueError('Collection ARRAY requires one through three logical dimensions')
        for size in shape:
            if type(size) is not int or not 1<=size<=32767:raise ValueError('Collection ARRAY requires fixed dimensions in 1..32767')
            cells*=size
            if cells>32767:raise ValueError('Collection ARRAY exceeds 32767 reserved units')
        current=current[2]
        if type(current) is not tuple or not current:raise ValueError('Malformed collection ARRAY terminal type')
    width=1
    if current[0]=='QUEUE_TYPE':
        if current!=('QUEUE_TYPE',):raise ValueError('Malformed collection ARRAY queue type')
    elif current[0]=='PATH' and len(current)==3:
        for index,component in enumerate(current[1:],1):
            if component is None:continue
            if type(component) is not tuple or not component or component[0]!='STRUCTURE':raise ValueError('Collection PATH components require named STRUCTURE layouts')
            try:runtime._validate_data_schema(component)
            except runtime.KarelRuntimeError as exc:raise ValueError('Invalid collection ARRAY component schema: '+str(exc)) from exc
            collection_data_spec(component)
            if index==2:width+=runtime.scalar_leaf_count(component)
    elif current[0]=='PATH':raise ValueError('Malformed collection ARRAY PATH type')
    else:return None
    cost=cells*width
    if cost>32767:raise ValueError('Collection ARRAY exceeds 32767 reserved units including headers')
    return cost


def _collection_array_units(spec,value,encoded):
    runtime=rt()
    if encoded:
        keys={'initialized','sequence','entries'} if spec[0]=='QUEUE_TYPE' else {'nodes','data'}
        if type(value) is not dict or set(value)!=keys:raise ValueError('Malformed collection ARRAY cell payload')
        items=value['entries' if spec[0]=='QUEUE_TYPE' else 'nodes']
        if spec[0]=='PATH' and spec[2] is None and value['data'] is not None:raise ValueError('Headerless PATH cannot contain data')
    else:
        kind=runtime.QueueValue if spec[0]=='QUEUE_TYPE' else runtime.PathValue
        if type(value) is not kind or value.spec!=spec:raise ValueError('Collection ARRAY cell does not match its schema')
        items=value.entries if spec[0]=='QUEUE_TYPE' else value.nodes
    if type(items) is not list or len(items)>32767:raise ValueError('Collection ARRAY cell exceeds its entry/node limit')
    if spec[0]=='QUEUE_TYPE':return 1+2*len(items)
    node=spec[1] or runtime.PREDEFINED_STRUCTURES['STD_PTH_NODE']
    return 1+(runtime.scalar_leaf_count(spec[2]) if spec[2] else 0)+len(items)*runtime.scalar_leaf_count(node)


def _collection_array_rows(spec,value,encoded):
    """Check hierarchy and combined contents before encoding or allocating arrays."""
    runtime=rt();rows=[];units=0
    if collection_array_cost(spec) is None:raise ValueError('Collection ARRAY codec requires PATH or QUEUE_TYPE cells')
    def visit(schema,item):
        nonlocal units
        if schema[0]!='ARRAY':
            units+=_collection_array_units(schema,item,encoded)
            if units>32767:raise ValueError('Collection ARRAY snapshot exceeds 32767 units including contents')
            rows.append((schema,item));return
        shape=runtime.array_shape(schema)
        if encoded:values=array_state_values(shape,item)
        else:
            if (type(item) is not runtime.Array or item.spec!=schema or item.shape!=shape
                    or type(item.values) is not list or len(item.values)!=math.prod(shape)):
                raise ValueError('Collection ARRAY storage does not match its concrete schema')
            values=item.values
        for child in values:visit(schema[2],child)
    visit(spec,value)
    return rows


def collection_array_payload(spec,value):
    runtime=rt();rows=_collection_array_rows(spec,value,False)
    payloads=iter(collection_payload(schema,item) for schema,item in rows)
    def encode(schema,item):
        if schema[0]!='ARRAY':return next(payloads)
        values=[encode(schema[2],child) for child in item.values]
        for dimension in reversed(runtime.array_shape(schema)[1:]):
            values=[values[start:start+dimension] for start in range(0,len(values),dimension)]
        return values
    return encode(spec,value)


def restore_collection_array(spec,payload):
    """Validate counts first; restore independent cells with no queue buffer links."""
    runtime=rt();rows=_collection_array_rows(spec,payload,True)
    restored=iter([restore_collection(schema,item) for schema,item in rows])
    def allocate(schema):
        if schema[0]!='ARRAY':return next(restored)
        result=object.__new__(runtime.Array);result.spec=schema;result.shape=runtime.array_shape(schema)
        result.values=[allocate(schema[2]) for _ in range(math.prod(result.shape))]
        return result
    return allocate(spec)


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


def atomic_bytes(target, data, *, overwrite=True):
    target=Path(target)
    descriptor,name=tempfile.mkstemp(prefix='.'+target.name+'.',suffix='.tmp',dir=target.parent)
    temporary=Path(name)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        if overwrite:os.replace(temporary,target)
        elif os.name=='nt':os.rename(temporary,target)
        else:os.link(temporary,target)
    finally:
        if temporary.exists(): temporary.unlink()


class DirectoryFiles:
    """FILE backend rooted in a caller-selected directory; buffered until close.

    Source names are relative paths, optionally prefixed by an explicit device
    mapping. Resolved keys use forward slashes. Exact paths reject links,
    junctions and traversal.
    """
    def __init__(self,root,*,devices=None,limit=16*1024*1024,listing_timestamps=False):
        from .extended import MemoryFiles
        self.root=Path(root).resolve(strict=True)
        if not self.root.is_dir(): raise ValueError('Filesystem root must be a directory')
        self.devices={str(key).upper():str(value).replace('\\','/') for key,value in (devices or {}).items()}
        self.listing_timestamps=listing_timestamps
        self.memory=MemoryFiles(limit=limit); self.files=self.memory.files; self.limit=limit
        self.handles=[]
        for value in self.devices.values():
            if ':' in value:raise ValueError('Mapped FILE directories must stay relative to their explicit root')
            self._path(value or '.',directory=True)

    def _relative_name(self,name):
        from .fileops import _file_name_separators
        name=_file_name_separators(rt().ascii_string(name))
        if ':' in name:
            device,tail=name.split(':',1)
            if device.upper() not in self.devices: raise ValueError('Unmapped file device')
            name='/'.join(part for part in (self.devices[device.upper()],tail) if part)
        if any(part in ('..','') for part in name.split('/')) or ':' in name or '\0' in name:
            raise ValueError('File name must stay relative to its explicit root')
        return name

    @staticmethod
    def _linked_path(path):
        from .fileops import _wildcard_link
        try:return _wildcard_link(path)
        except FileNotFoundError:return False

    def _path(self,name,*,directory=False):
        name=self._relative_name(name)
        target=self.root
        for part in name.split('/'):
            target=target/part
            if self._linked_path(target): raise ValueError('Rooted FILE paths cannot traverse links or junctions')
        resolved=target.resolve()
        if not resolved.is_relative_to(self.root) or not directory and resolved==self.root: raise ValueError('File path escapes its root')
        return resolved

    def _key(self,name): return self._path(name).relative_to(self.root).as_posix()

    def _identity(self,name):
        try: info=self._path(name).stat()
        except FileNotFoundError:return None
        return (info.st_dev,info.st_ino) if info.st_ino else None

    def _busy_keys(self,keys,*,casefold=False):
        open_names=[handle.name for handle in self.handles if handle.owner is self]
        if not open_names:return False
        normalize=str.casefold if casefold else os.path.normcase
        open_keys={normalize(name) for name in open_names}
        if any(normalize(key) in open_keys for key in keys):return True
        identities=set()
        for name in open_names:
            try: identity=self._identity(name)
            except (OSError,ValueError):continue
            if identity is not None:identities.add(identity)
        return bool(identities) and any(self._identity(key) in identities for key in keys)

    def _busy(self,key): return self._busy_keys((key,))

    def _create_directory(self,name):
        target=self._path(name,directory=True)
        try:target.mkdir()
        except FileNotFoundError:return 1
        except FileExistsError:return 2
        return 0

    def _remove_directory(self,name):
        target=self._path(name,directory=True)
        if not target.is_dir():return 1
        if any(self._path(handle.name).is_relative_to(target) for handle in self.handles if handle.owner is self):
            return 3
        try:target.rmdir()
        except FileNotFoundError:return 1
        except OSError as exc:
            if exc.errno in (errno.ENOTEMPTY,errno.EEXIST):return 3
            raise
        return 0

    def open(self,handle,mode,name,line=None):
        if handle.owner is not None: raise rt().KarelRuntimeError('FILE is already open',line)
        try:
            key=self._key(name); path=self._path(key)
            if self._busy(key): raise ValueError('File is already open through this backend')
            previous=self.files.get(key)
            if path.exists():
                self.files[key]=bytearray(self._disk_bytes(path))
            else:self.files.pop(key,None)
            try:self.memory.open(handle,mode,key,line)
            except Exception:
                if previous is None:self.files.pop(key,None)
                else:self.files[key]=previous
                raise
            handle.owner=self; self.handles.append(handle)
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
        self.flush(handle,line); handle.owner=None;handle.xml_session=None
        self.handles=[item for item in self.handles if item is not handle]
        self.memory.handles=[item for item in self.memory.handles if item is not handle]

    def write(self,handle,data,line=None):
        if not handle.interactive:
            self.memory.write(handle,data,line)
            return
        old=bytes(self.files.get(handle.name,b''));position,status=handle.position,handle.status
        self.memory.write(handle,data,line)
        try:self.flush(handle,line)
        except Exception:
            self.files[handle.name]=bytearray(old);handle.position=position;handle.status=status
            raise

    def read_bytes(self,handle,count,line=None): return self.memory.read_bytes(handle,count,line)

    def snapshot(self): return self.memory.snapshot()

    def _disk_bytes(self,path):
        if not path.is_file() or path.stat().st_size>self.limit: raise ValueError('Invalid file or file size limit exceeded')
        with path.open('rb') as stream: data=stream.read(self.limit+1)
        if len(data)>self.limit: raise ValueError('File size limit exceeded')
        return data

    def read_named(self,name):
        key=self._key(name)
        if self._busy(key): return 3,None
        path=self._path(key)
        if not path.exists(): return 1,None
        return 0,self._disk_bytes(path)

    def list_names(self,pattern='*',*,check=None):
        from .fileops import _listing_entries

        # Validate the non-wildcard path components before traversing the selected root.
        self._path(pattern.replace('*','x').replace('?','x'))
        pattern=self._relative_name(pattern)
        def candidates():
            pending=[self.root]
            while pending:
                parent=pending.pop()
                if self._linked_path(parent) or parent.resolve()!=parent:continue
                with os.scandir(parent) as entries:
                    for entry in entries:
                        path=parent/entry.name
                        yield path,entry
                        if entry.is_dir(follow_symlinks=False) and not self._linked_path(path):
                            pending.append(path)
            for handle in self.handles:
                if handle.owner is self:yield self.root/handle.name,None

        names=set()
        with closing(candidates()) as entries:
            for path,entry in _listing_entries(entries,check):
                relative=path.relative_to(self.root).as_posix()
                if not fnmatch.fnmatchcase(relative,pattern):continue
                if entry is None or entry.is_file(follow_symlinks=False) and not self._linked_path(path):
                    self._path(relative);names.add(relative)
        return sorted(names)

    def copy(self,source,target,overwrite=False,*,check=None):
        from .fileops import charge_file_bytes

        source=self._key(source); target=self._key(target)
        if self._busy(source) or self._busy(target): return 3
        src=self._path(source); dst=self._path(target)
        if not src.is_file(): return 1
        if dst.exists() and not overwrite: return 2
        data=self._disk_bytes(src)
        charge_file_bytes(len(data),check)
        if check is not None:
            if self._busy(source) or self._busy(target):return 3
            dst=self._path(target)
        try:atomic_bytes(dst,data,overwrite=overwrite)
        except FileExistsError:
            if overwrite:raise
            return 2
        self.files[target]=bytearray(data); return 0

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


def directory_files_options(parser):
    parser.add_argument('--filesystem-root',type=Path,help='Explicit directory for FILE operations')
    parser.add_argument('--filesystem-device',action='append',default=[],metavar='DEVICE=SUBDIRECTORY',
                        help='Map a FILE device to an existing directory within the filesystem root (repeatable)')
    parser.add_argument('--filesystem-timestamps',action='store_true',
                        help='Include UTC host modification times in rooted FILE_LIST metadata')


def directory_files_from_args(parser,args):
    if args.filesystem_root is None:
        if args.filesystem_device:parser.error('--filesystem-device requires --filesystem-root')
        if args.filesystem_timestamps:parser.error('--filesystem-timestamps requires --filesystem-root')
        return None
    devices={}
    for mapping in args.filesystem_device:
        name,separator,location=mapping.partition('=')
        name=name.removesuffix(':')
        if not separator or re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,7}',name) is None:
            parser.error('--filesystem-device requires DEVICE=SUBDIRECTORY')
        name=name.upper()
        if name in devices:parser.error('Duplicate --filesystem-device '+name)
        devices[name]=location
    try:
        files=DirectoryFiles(args.filesystem_root,devices=devices,listing_timestamps=args.filesystem_timestamps)
        for name,location in devices.items():
            directory=files._path(location or '.',directory=True)
            if not directory.is_dir():
                raise ValueError('Mapped FILE directory does not exist for '+name)
            files.devices[name]='' if directory==files.root else directory.relative_to(files.root).as_posix()
        return files
    except (OSError,ValueError,rt().KarelRuntimeError) as error:
        parser.error('Invalid filesystem configuration: '+str(error))


def context_config(context):
    result={}
    if context.predefined_files:result['predefined_files']=context.predefined_files
    for name in context._predefined_values:
        if context._predefined_handle(name).owner is not None:raise ValueError('Close predefined FILE handles before saving context')
    if context.serial_streams is not None:result['serial_streams']=context.serial_streams.to_config()
    if context.source_translations is not None: result['source_translations']=context.source_translations.to_config()
    if context.serial_ports is not None: result['serial_ports']=context.serial_ports.to_config()
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
        if type(context.files) is rt().DeviceFiles: result['device_files']=context.files.to_config()
        else: result['files']={name:{'hex':value.hex()} for name,value in context.files.snapshot().items()}
    if context.variables.bindings:
        rows=[]
        for (program,path),reference in sorted(context.variables.bindings.items()):
            from .dynamic import file_storage_cost,file_storage_payload
            if (program,path) in context.variables.metadata and file_storage_cost(reference.spec) is not None:
                value={'type':json.loads(json.dumps(reference.spec)),'value':file_storage_payload(reference.spec,reference.raw())}
            else: value=typed_value(reference.raw(),reference.spec)
            rows.append(dict(program=program,path=path,**value))
        result['variables']=rows
    variables={(row['program'],row['path']):row for row in result.get('variables',[])}
    for key,metadata in context.variables.metadata.items():
        if key in variables: variables[key]['creation']=metadata.copy()
    for name,state in context.variables.programs.items():
        for path,spec in state.types.items():
            if not rt().file_storage_type(spec):
                value=state.values[path]
                if isinstance(value,rt().Reference): value=value.raw()
                variables[name,path]=dict(program=name,path=path,**typed_value(value,spec))
    if variables: result['variables']=[variables[key] for key in sorted(variables)]
    if context.events is not None: result['events']=context.events.snapshot()
    if context.group_locks is not None: result['group_locks']=context.group_locks.to_config()
    if context.acquisition is not None: result['acquisition']=context.acquisition.to_config()
    if context.variable_archives is not None: result['variable_archives']=context.variable_archives.to_config()
    if context.diagnostics is not None: result['diagnostics']=context.diagnostics.to_config()
    if context.kcl is not None: result['kcl']=context.kcl.to_config()
    if context.controller is not None: result['controller']=context.controller.to_config()
    if context.motion is not None: result['motion']=context.motion.to_config()
    if context.vision is not None: result['vision']=context.vision.to_config()
    if context.forms is not None: result['forms']=context.forms.to_config()
    if context.table_controls is not None: result['table_controls']=context.table_controls.to_config()
    if context.keyboard is not None: result['keyboard']=context.keyboard.to_config()
    if context.dynamic_display is not None: result['dynamic_display']=context.dynamic_display.to_config()
    if context.dictionaries is not None: result['dictionaries']=context.dictionaries.to_config()
    if context.pendant is not None: result['pendant']=context.pendant.to_config()
    if context.remote_messages is not None: result['remote_messages']=context.remote_messages.to_config()
    if context.pc_exchange is not None: result['pc_exchange']=context.pc_exchange.to_config()
    if context.messaging is not None: result['messaging']=context.messaging.to_config()
    if context.file_pipes is not None: result['file_pipes']=context.file_pipes.to_config()
    if context.semaphores is not None: result['semaphores']=context.semaphores.to_config()
    if context.errors is not None: result['errors']=context.errors.to_config()
    if context.parameters is not None: result['parameters']=context.parameters.to_config()
    if context.robot is not None:
        config=context.robot.to_config()
        if config is not None: result['robot']=config
    return result
