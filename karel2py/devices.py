"""Explicit virtual device volumes; never mount, format or inspect host drives."""
from copy import deepcopy
import fnmatch
import re

from .extended import MemoryFiles


DEVICE_NAMES=frozenset(('MOUNT_DEV','DISMOUNT_DEV','FORMAT_DEV','PURGE_DEV','VOL_SPACE','DOSFILE_INF'))
DEVICE_INFO={name:index for index,name in enumerate(('DF_MANUFNAME','DF_PRODNAME','DF_SERIALNO','DF_PRODID','DF_VENDID'),1)}
DEVICE_CONSTANTS={**DEVICE_INFO,'DEV_NOTHING_TO_PURGE':85023}
TOTAL_ONLY={'FROM','DRAM','CMOS'}
MAX_BYTES=64*1024*1024


def rt():
    from . import runtime
    return runtime


def device_name(value,line=None):
    value=rt().ascii_string(value,line).upper()
    return value[:-1] if re.fullmatch(r'[A-Z][A-Z_0-9]{0,7}:',value) else None


def label_value(value):
    return type(value) is str and value.isascii() and all(32<=ord(c)<127 for c in value)


class DeviceFiles(MemoryFiles):
    """MemoryFiles with explicit volume state, quotas and obsolete-byte counts."""
    def __init__(self,volumes,initial=None,*,limit=16*1024*1024):
        if type(volumes) is not dict or not 1<=len(volumes)<=32: raise ValueError('Virtual volumes require 1..32 device records')
        self._volumes={};self._loading=True
        for name,row in volumes.items():
            key=device_name(name)
            if key is None or key=='MF' or key in self._volumes: raise ValueError('Invalid, reserved or duplicate virtual device name; include colon')
            if type(row) is not dict or set(row)-{'capacity','mounted','label','read_only','retain_deleted','garbage','info'} or 'capacity' not in row:
                raise ValueError('Unknown virtual volume fields or missing capacity')
            capacity=row['capacity'];garbage=row.get('garbage',0)
            if type(capacity) is not int or not 1<=capacity<=MAX_BYTES or type(garbage) is not int or not 0<=garbage<=capacity:
                raise ValueError('Virtual capacity/garbage must be bounded nonnegative byte counts')
            result=dict(capacity=capacity,mounted=row.get('mounted',True),label=row.get('label',''),
                read_only=row.get('read_only',False),retain_deleted=row.get('retain_deleted',key=='FR'),garbage=garbage,info={})
            if any(type(result[field]) is not bool for field in ('mounted','read_only','retain_deleted')):
                raise ValueError('Virtual volume state flags require BOOLEANs')
            if not label_value(result['label']) or len(result['label'])>11: raise ValueError('Volume label requires at most 11 printable ASCII characters')
            info=row.get('info',{})
            if type(info) is not dict: raise ValueError('Virtual device information requires named fields')
            for field,value in info.items():
                if type(field) is not str or field.upper() not in DEVICE_INFO or field.upper() in result['info'] or type(value) is not str or not value.isascii() or len(value)>254:
                    raise ValueError('Invalid or duplicate virtual device information')
                result['info'][field.upper()]=value
            self._volumes[key]=result
        if sum(row['capacity'] for row in self._volumes.values())>MAX_BYTES:
            raise ValueError('Combined virtual volume capacities exceed 64 MiB')
        if initial is None: initial={}
        if type(initial) is not dict or len(initial)>32767: raise ValueError('Virtual files require a bounded mapping')
        values={}
        for name,data in initial.items():
            key=self.canonical(name)
            if key in values or type(data) not in (str,bytes,bytearray): raise ValueError('Invalid or aliased virtual file initializer')
            values[key]=data
        super().__init__(values,limit=limit);self._loading=False
        for key,row in self._volumes.items():
            if self.used(key)>row['capacity']: raise ValueError('Initial virtual files and garbage exceed capacity')

    def canonical(self,name):
        name=rt().ascii_string(name)
        device,sep,path=name.partition(':');key=device_name(device+':') if sep else None
        if key not in self._volumes or key in TOTAL_ONLY: raise rt().KarelRuntimeError('File requires an explicitly configured virtual file device')
        if not path or ':' in path or '\\' in path or path.startswith('/') or any(part in ('','.','..') for part in path.split('/')) or any(ord(c)<32 or ord(c)==127 for c in path):
            raise rt().KarelRuntimeError('Virtual file path must remain relative to its device')
        return key+':'+path

    def used(self,key):
        return self._volumes[key]['garbage']+sum(len(value) for name,value in self.files.items() if name.split(':',1)[0]==key)

    def require_volume(self,key,*,write=False,line=None):
        row=self._volumes[key]
        if not row['mounted']: raise rt().KarelRuntimeError('Virtual device is not mounted',line)
        if write and row['read_only']: raise rt().KarelRuntimeError('Virtual device is read-only',line)
        return row

    def _check(self,name,data):
        name=self.canonical(name)
        if not self._loading: self.require_volume(name.split(':',1)[0])
        return super()._check(name,data)

    def reserve(self,name,new_length,obsolete=0,line=None,*,replace_slot=False):
        key=name.split(':',1)[0];row=self.require_volume(key,write=True,line=line)
        if name not in self.files and len(self.files)>=32767 and not replace_slot: raise rt().KarelRuntimeError('Virtual file count exceeded',line)
        current=len(self.files.get(name,b''));added=obsolete if row['retain_deleted'] else 0
        if self.used(key)-current+new_length+added>row['capacity']:
            raise rt().KarelRuntimeError('Virtual device capacity exceeded; PURGE_DEV may reclaim obsolete bytes',line)
        return row,added

    def open(self,handle,mode,name,line=None):
        name=self.canonical(name);text=rt().ascii_string(mode,line).upper().replace('B','')
        text={'RO':'R','WO':'W','UD':'RW','AP':'A'}.get(text,text)
        self.require_volume(name.split(':',1)[0],write=text!='R',line=line)
        old=len(self.files.get(name,b''));row=None;added=0
        if text=='W': row,added=self.reserve(name,0,old,line)
        elif name not in self.files and text!='R': row,added=self.reserve(name,0,line=line)
        super().open(handle,mode,name,line)
        if row is not None: row['garbage']+=added

    def write(self,handle,data,line=None):
        handle.require_open(line);self._check(handle.name,b'')
        old=len(self.files[handle.name]);start=old if handle.mode=='A' else handle.position
        overwritten=min(len(data),max(0,old-start))
        row,added=self.reserve(handle.name,max(old,start+len(data)),overwritten,line)
        super().write(handle,data,line);row['garbage']+=added

    def read_named(self,name): return super().read_named(self.canonical(name))

    def list_names(self,pattern='*'):
        pattern=rt().ascii_string(pattern)
        if ':' in pattern:
            device,tail=pattern.split(':',1);key=device_name(device+':')
            if key not in self._volumes or key in TOTAL_ONLY: raise rt().KarelRuntimeError('Unknown virtual listing device')
            self.require_volume(key);pattern=key+':'+tail
        return sorted(name for name in self.files if self._volumes[name.split(':',1)[0]]['mounted'] and fnmatch.fnmatchcase(name,pattern))

    def copy(self,source,target,overwrite=False):
        source=self.canonical(source);target=self.canonical(target)
        self._check(source,b'');self._check(target,b'')
        if self._busy(source) or self._busy(target): return 3
        if source not in self.files: return 1
        if target in self.files and not overwrite: return 2
        self.require_volume(target.split(':',1)[0],write=True)
        if source==target: return 0
        row,added=self.reserve(target,len(self.files[source]),len(self.files.get(target,b'')))
        code=super().copy(source,target,overwrite)
        if not code: row['garbage']+=added
        return code

    def delete(self,name):
        name=self.canonical(name);self._check(name,b'')
        self.require_volume(name.split(':',1)[0],write=True)
        if self._busy(name): return 3
        if name not in self.files: return 1
        row=self._volumes[name.split(':',1)[0]];size=len(self.files[name])
        code=super().delete(name)
        if not code and row['retain_deleted']: row['garbage']+=size
        return code

    def rename(self,source,target):
        source=self.canonical(source);target=self.canonical(target)
        self._check(source,b'');self._check(target,b'')
        first=source.split(':',1)[0];second=target.split(':',1)[0]
        row=self.require_volume(first,write=True);self.require_volume(second,write=True)
        if self._busy(source) or self._busy(target): return 3
        if source not in self.files: return 1
        if target in self.files: return 2
        size=len(self.files[source])
        if first!=second: self.reserve(target,size,replace_slot=True)
        code=super().rename(source,target)
        if not code and first!=second and row['retain_deleted']: row['garbage']+=size
        return code

    def preflight_moves(self,plan):
        changes={}
        for source,target in plan:
            source=self.canonical(source);target=self.canonical(target)
            first=source.split(':',1)[0];second=target.split(':',1)[0]
            row=self.require_volume(first,write=True);self.require_volume(second,write=True)
            if first==second: continue
            size=len(self.files[source]);changes[second]=changes.get(second,0)+size
            if not row['retain_deleted']: changes[first]=changes.get(first,0)-size
        for key,delta in changes.items():
            if self.used(key)+delta>self._volumes[key]['capacity']:
                raise rt().KarelRuntimeError('Virtual device capacity exceeded by complete MOVE_FILE batch')

    def selected(self,device,line=None):
        key=device_name(device,line)
        return (2,None) if key not in self._volumes else (0,key)

    def ready(self,key,*,write=False):
        row=self._volumes[key]
        if not row['mounted']: return 3
        if write and row['read_only']: return 5
        if any(handle.owner is self and handle.name.startswith(key+':') for handle in self.handles): return 4
        return 0

    def mount(self,device,mounted=True,line=None):
        if type(mounted) is not bool: raise ValueError('Virtual mount flag requires BOOLEAN')
        code,key=self.selected(device,line)
        if code: return code
        if not mounted and any(handle.owner is self and handle.name.startswith(key+':') for handle in self.handles): return 4
        self._volumes[key]['mounted']=mounted;return 0

    def format(self,device,label,nowait=False,*,check=None,line=None):
        runtime=rt();label=runtime.ascii_string(label,line);runtime.boolean(nowait,line)
        code,key=self.selected(device,line)
        if code: return code
        if not label_value(label) or key in TOTAL_ONLY: return 2
        code=self.ready(key,write=True)
        if code: return code
        names=[name for name in self.files if name.startswith(key+':')]
        for name in names:
            if check is not None: check()
        code=self.ready(key,write=True)
        if code: return code
        if set(names)!={name for name in self.files if name.startswith(key+':')}:
            raise runtime.KarelRuntimeError('Virtual volume changed during format preflight',line)
        for name in names: del self.files[name]
        self._volumes[key].update(garbage=0,label=label[:11]);return 0

    def purge(self,device,*,check=None,line=None):
        key=device_name(device,line);keys=('RD','FR') if key=='MF' else (key,)
        if any(key not in self._volumes or key in TOTAL_ONLY for key in keys): return 2
        for key in keys:
            code=self.ready(key,write=True)
            if code: return code
            if check is not None: check()
        for key in keys:
            code=self.ready(key,write=True)
            if code: return code
        amount=sum(self._volumes[key]['garbage'] for key in keys)
        if not amount: return 85023
        for key in keys: self._volumes[key]['garbage']=0
        return 0

    def space(self,device,line=None):
        code,key=self.selected(device,line)
        if code: return code,None
        row=self._volumes[key]
        if not row['mounted']: return 3,None
        return 0,dict(total=row['capacity'],free=row['capacity']-self.used(key),
            label='' if key in ('RD','FR') else row['label'],total_only=key in TOTAL_ONLY)

    def info(self,device,item,line=None):
        item=rt().integer(item,line);code,key=self.selected(device,line)
        if code: return code,None
        row=self._volumes[key]
        if not row['mounted']: return 3,None
        field=next((key for key,value in DEVICE_INFO.items() if value==item),None)
        if field is None: return 2,None
        return (0,row['info'][field]) if field in row['info'] else (1,None)

    def to_config(self):
        return dict(limit=self.limit,volumes={key+':':deepcopy(row) for key,row in sorted(self._volumes.items())},
                    files={name:{'hex':value.hex()} for name,value in sorted(self.files.items())})

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'volumes','files','limit'} or 'volumes' not in config:
            raise ValueError('Virtual file configuration requires volumes, optional files and limit')
        values=config.get('files',{});limit=config.get('limit',16*1024*1024)
        if type(values) is not dict or len(values)>32767 or type(limit) is not int or not 1<=limit<=MAX_BYTES: raise ValueError('Invalid virtual file limits')
        total=0;decoded={}
        for name,value in values.items():
            if type(value) is str:
                if not value.isascii(): raise ValueError('Virtual text files require ASCII')
                size=len(value)
            elif type(value) is dict and set(value)=={'hex'} and type(value['hex']) is str:
                if len(value['hex'])%2 or not re.fullmatch('[0-9a-fA-F]*',value['hex']): raise ValueError('Invalid virtual file hex payload')
                size=len(value['hex'])//2
            else: raise ValueError('Virtual files require ASCII strings or hex payloads')
            total+=size
            if size>limit or total>MAX_BYTES: raise ValueError('Virtual file payload limit exceeded')
            decoded[name]=value if type(value) is str else bytes.fromhex(value['hex'])
        return cls(config['volumes'],decoded,limit=limit)


def invoke_device(context,state,name,args,line=None):
    runtime=rt();files=context.files
    if type(files) is not DeviceFiles: raise runtime.KarelRuntimeError('Device operation requires explicit virtual DeviceFiles backend',line)
    if name=='MOUNT_DEV': code=files.mount(args[0],True,line)
    elif name=='DISMOUNT_DEV': code=files.mount(args[0],False,line)
    elif name=='FORMAT_DEV': code=files.format(*args[:3],check=lambda:state.tick(line),line=line)
    elif name=='PURGE_DEV': code=files.purge(args[0],check=lambda:state.tick(line),line=line)
    elif name=='VOL_SPACE':
        code,row=files.space(args[0],line)
        if code: raise runtime.KarelRuntimeError('VOL_SPACE failed with portable device code '+str(code),line)
        if not row['total_only']:
            capacity=args[3].spec[1]
            if type(capacity) is not int or not 1<=capacity<=254 or len(row['label'])>capacity:
                raise runtime.KarelRuntimeError('VOL_SPACE requires complete label output capacity',line)
        args[1].set(row['total'],line)
        if not row['total_only']: args[2].set(row['free'],line);args[3].set(row['label'],line)
        return
    else:
        code,value=files.info(*args[:2],line=line)
        if not code:
            capacity=args[2].spec[1]
            if type(capacity) is not int or not 1<=capacity<=254:
                raise runtime.KarelRuntimeError('DOSFILE_INF requires concrete STRING output capacity',line)
            if len(value)>capacity: code=7
            else: args[2].set(value,line)
    args[-1].set(code,line)
