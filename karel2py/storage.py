"""Portable state serialization and explicitly rooted filesystem services."""
from copy import deepcopy
import fnmatch
import json
import os
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
    if spec is None or spec[0] in ('FILE','PATH','QUEUE_TYPE'): raise ValueError('A serializable value requires an explicit data type')
    return {'type':json.loads(json.dumps(spec)),'value':runtime.snapshot_value(value)}


def restore_value(spec, payload):
    runtime=rt(); spec=tuple_spec(spec)
    if spec[0] in ('FILE','PATH','QUEUE_TYPE'): raise ValueError('Resource handles are not persistent values')
    if payload=={'uninitialized':True}: return runtime.UNINITIALIZED
    if payload=={'unknown_byte':True}:
        if spec!=('BYTE',): raise ValueError('Unknown BYTE marker requires BYTE storage')
        return runtime.UNKNOWN_BYTE
    if spec[0]=='ARRAY':
        result=runtime.Array(spec)
        if type(payload) is not list or len(payload)!=len(result.values): raise ValueError('ARRAY state shape mismatch')
        result.values[:]=[restore_value(spec[2],item) for item in payload]
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
        result.values.update({key:restore_value(member,fields[key]) for key,member in result.types.items()})
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

    def _busy(self,key): return any(handle.owner is self and handle.name==key for handle in self.handles)

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


def context_config(context):
    result={}
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
            if spec[0] not in ('FILE','PATH','QUEUE_TYPE'):
                value=state.values[path]
                if isinstance(value,rt().Reference): value=value.raw()
                variables[name,path]=dict(program=name,path=path,**typed_value(value,spec))
    if variables: result['variables']=[variables[key] for key in sorted(variables)]
    if context.events is not None: result['events']=context.events.snapshot()
    if context.semaphores is not None: result['semaphores']=context.semaphores.to_config()
    if context.errors is not None: result['errors']=context.errors.to_config()
    if context.parameters is not None: result['parameters']=context.parameters.to_config()
    if context.robot is not None and context.robot.model_config is not None: result['robot']=deepcopy(context.robot.model_config)
    return result
