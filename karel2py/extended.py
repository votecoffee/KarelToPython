"""Explicit offline services for translated programs.

No device discovery or robot access. Filesystem use requires an explicit backend.
The compiler and runtime share these signatures; adapters operate on checked values.
"""
from copy import deepcopy
import math
import re
import struct
import fnmatch


def runtime():
    from . import runtime as rt
    return rt


def fail(message, line=None): raise runtime().KarelRuntimeError(message,line)


# mode: i=value input, o=output reference, r=mutable resource/reference.
def arg(kind, mode='i'): return mode,kind
I=arg('INTEGER'); S=arg('STRING'); R=arg('REAL'); B=arg('BOOLEAN')
OI=arg('INTEGER','o'); OS=arg('STRING','o'); OA=arg('ANY','o')
COOPERATIVE_PROCEDURES={'PEND_SEMA','POST_ERR'}
PROCEDURES = {
    'CLEAR_SEMA':(I,), 'POST_SEMA':(I,), 'PEND_SEMA':(I,I,arg('BOOLEAN','o')),
    'POST_ERR':(I,S,I,I),
    'CONT_TASK': (S,OI), 'PAUSE_TASK': (S,B,B,OI), 'ABORT_TASK': (S,B,B,OI),
    'RUN_TASK': (S,I,B,B,I,OI),
    'GET_STR_REG': (I,OS,OI), 'SET_STR_REG': (I,S,OI),
    'SET_POS_REG': (I,arg('POSE'),OI,I), 'SET_EPOS_REG': (I,arg('POSE'),OI,I),
    'SET_JPOS_REG': (I,arg('JOINTPOS'),OI,I),
    'GET_VAR': (arg('INTEGER','o'),S,S,OA,OI),
    'SET_VAR': (arg('INTEGER','o'),S,S,arg('ANY'),OI),
    'APPEND_NODE': (arg('PATH','r'),OI), 'INSERT_NODE': (arg('PATH','r'),I,OI),
    'DELETE_NODE': (arg('PATH','r'),I,OI),
    'COPY_PATH': (arg('PATH'),I,I,arg('PATH','r'),OI),
    'COPY_FILE': (S,S,B,B,OI), 'DELETE_FILE': (S,B,OI), 'RENAME_FILE': (S,S,B,OI),
    'FILE_LIST': (S,I,I,arg('STRING_ARRAY','r'),OI,OI),
    'INIT_QUEUE': (arg('QUEUE_TYPE','r'),),
    'APPEND_QUEUE': (I,arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI,OI),
    'INSERT_QUEUE': (I,I,arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI),
    'DELETE_QUEUE': (I,arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI),
    'MODIFY_QUEUE': (I,I,arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI),
    'GET_QUEUE': (arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),OI,OI,OI),
    'COPY_QUEUE': (arg('QUEUE_TYPE','r'),arg('INT_ARRAY','r'),I,I,arg('INT_ARRAY','r'),OI,OI),
    'SET_FILE_POS': (arg('FILE'),I,OI), 'BYTES_AHEAD': (arg('FILE'),OI,OI),
    'SET_FILE_ATR': (arg('FILE'),I,I), 'CLR_IO_STAT': (arg('FILE'),),
    'JOINT2POS': (arg('JOINTPOS'),arg('POSE'),arg('POSE'),I,arg('POSITION','o'),arg('CONFIG','o'),arg('REAL_ARRAY','r'),OI),
    'POS2JOINT': (arg('JOINTPOS'),arg('POSE'),arg('POSE'),arg('POSE'),I,arg('CONFIG'),arg('REAL_ARRAY'),arg('JOINTPOS','o'),OI),
}
FUNCTIONS = {
    'SEMA_COUNT':((I,),('INTEGER',)),
    'GET_POS_REG': ((I,OI,I),('XYZWPREXT',)),
    'GET_JPOS_REG': ((I,OI,I),('JOINTPOS',9)),
    'PATH_LEN': ((arg('PATH'),),('INTEGER',)),
    'GET_FILE_POS': ((arg('FILE'),),('INTEGER',)),
    'BYTES_LEFT': ((arg('FILE'),),('INTEGER',)),
    'IO_STATUS': ((arg('FILE'),),('INTEGER',)),
    'IN_RANGE': ((arg('POSE'),),('BOOLEAN',)),
    'J_IN_RANGE': ((arg('JOINTPOS'),),('BOOLEAN',)),
    'MIRROR': ((arg('POSE'),arg('POSE'),B),('XYZWPREXT',)),
}
OPTIONAL_LAST = {'SET_POS_REG','SET_EPOS_REG','SET_JPOS_REG','GET_POS_REG','GET_JPOS_REG','SET_FILE_ATR'}
PORT_TYPES = {**{name:'BOOLEAN' for name in ('DIN','DOUT','RDI','RDO','RDIN','RDOUT')},
              **{name:'INTEGER' for name in ('GIN','GOUT')}, **{name:'REAL' for name in ('AIN','AOUT')}}
OUTPUT_PORTS = {'DOUT','RDO','RDOUT','GOUT','AOUT'}


def matches(spec, kind):
    rt=runtime()
    if kind=='ANY': return spec[0] not in ('FILE','PATH','QUEUE_TYPE')
    if kind=='POSE': return spec[0] in ('POSITION','XYZWPR','XYZWPREXT')
    if kind in ('INT_ARRAY','REAL_ARRAY'):
        return spec[0]=='ARRAY' and len(rt.array_dimensions(spec))==1 and rt.array_leaf_spec(spec)[0]==('INTEGER' if kind=='INT_ARRAY' else 'REAL')
    if kind=='STRING_ARRAY': return spec[0]=='ARRAY' and len(rt.array_dimensions(spec))==1 and rt.array_leaf_spec(spec)[0]=='STRING'
    return spec[0]==kind


def outputs_checked(signature, arguments, line=None):
    rt=runtime(); occupied=set()
    for (mode,kind), value in zip(signature,arguments):
        if mode not in ('o','r'): continue
        if type(value) is not rt.Reference or not matches(value.spec,kind): fail('Service output requires an ordinary exact-type writable reference',line)
        cells=rt._reference_cells(value)
        if occupied & cells: fail('Service output/resource references must not overlap',line)
        occupied.update(cells)


class StringRegisters:
    def __init__(self,count,initial=None,*,capacity=254):
        if type(count) is not int or not 1<=count<=32767: raise ValueError('String register count must be in 1..32767')
        if type(capacity) is not int or not 1<=capacity<=254: raise ValueError('String register capacity must be in 1..254')
        self.count,self.capacity,self.values=count,capacity,{}
        for number,value in (initial or {}).items():
            if self.write(number,value): raise ValueError('Initial string register is outside its bank')
    def read(self,number): return (2,None) if not 1<=number<=self.count else (0,self.values[number]) if number in self.values else (1,None)
    def write(self,number,value):
        value=runtime().ascii_string(value)
        if not 1<=number<=self.count: return 2
        self.values[number]=value[:self.capacity]; return 0
    def snapshot(self): return self.values.copy()


def pose_extended(value,line=None):
    rt=runtime(); value=rt.frame_value(value,line)
    if value.spec==('XYZWPREXT',): return value
    if value.spec==('POSITION',): value=rt.convert_position(('XYZWPR',),value,line)
    result=rt.Structure(('XYZWPREXT',)); result.values.update(deepcopy(value.values))
    result.values.update(EXT1=0.,EXT2=0.,EXT3=0.)
    return result


class PositionRegisters:
    def __init__(self,count,initial=None,*,groups=(1,)):
        if type(count) is not int or not 1<=count<=32767: raise ValueError('Position register count must be in 1..32767')
        if not groups or any(type(g) is not int or g<1 for g in groups): raise ValueError('Explicit positive position groups required')
        self.count,self.groups,self.values=count,tuple(groups),{}
        for key,value in (initial or {}).items():
            group,number=key if type(key) is tuple else (self.groups[0],key)
            if self.write(number,value,group): raise ValueError('Initial position register is outside its bank')
    def read(self,number,group=1):
        if group not in self.groups or not 1<=number<=self.count: return 2,None
        return (0,deepcopy(self.values[group,number])) if (group,number) in self.values else (1,None)
    def write(self,number,value,group=1):
        rt=runtime()
        if not hasattr(value,'spec') or value.spec[0] not in ('XYZWPR','XYZWPREXT','POSITION','JOINTPOS'): fail('Position register requires explicit checked pose or joint data')
        with rt._numeric_scope('pythonic'): value=rt.checked(value.spec,value)
        if group not in self.groups or not 1<=number<=self.count: return 2
        self.values[group,number]=value; return 0
    def snapshot(self): return deepcopy(self.values)


class PortBank:
    """Host updates may supply inputs; translated assignments write outputs only."""
    def __init__(self,counts,initial=None):
        self.counts={str(k).upper():v for k,v in counts.items()}; self.values={}
        if any(k not in PORT_TYPES or type(v) is not int or not 1<=v<=32767 for k,v in self.counts.items()): raise ValueError('Explicit valid port kinds/counts required')
        for (kind,number),value in (initial or {}).items(): self.update(kind,number,value)
    def update(self,kind,number,value):
        rt=runtime(); kind=kind.upper(); number=rt.integer(number)
        if kind not in self.counts or not 1<=number<=self.counts[kind]: fail('Port is outside its explicit bank')
        with rt._numeric_scope('pythonic'): value=rt.checked((PORT_TYPES[kind],),value)
        if kind in ('GIN','GOUT') and value<0: fail('Group ports require nonnegative INTEGER values')
        self.values[kind,number]=value
    def read(self,kind,number,line=None):
        number=runtime().integer(number,line)
        if (kind,number) not in self.values: fail('Port has no supplied value or is outside its bank',line)
        return self.values[kind,number]
    def write(self,kind,number,value,line=None):
        if kind not in OUTPUT_PORTS: fail('Translated programs cannot assign an input port',line)
        self.update(kind,number,value)
    def snapshot(self): return self.values.copy()


class VariableStore:
    def __init__(self): self.bindings={}; self.programs={}
    def attach(self,name,state):
        name=name.upper(); self.programs.setdefault(name,state)
        for (program,path),reference in self.bindings.items():
            if program==name and path in state.types and state.types[path]==reference.spec:
                state.values[path]=deepcopy(reference.raw())
    def bind(self,program,name,reference):
        if type(reference) is not runtime().Reference: raise TypeError('VariableStore requires ordinary Reference bindings')
        self.bindings[program.upper(),name.upper()]=reference
    def define(self,program,name,spec,value=...):
        rt=runtime()
        with rt._numeric_scope('pythonic'): stored=rt.initial_value(spec) if value is ... else rt.checked(spec,value)
        reference=rt.Reference(spec,{'value':stored},'value'); self.bind(program,name,reference); return reference


class FileHandle:
    def __init__(self):
        self.name=None; self.position=0; self.mode=''; self.binary=False; self.status=0; self.owner=None
        self.interactive=False; self.reverse=False; self.field=False; self.eol=10
    def require_open(self,line=None):
        if self.owner is None: fail('FILE is not open',line)
    def tell(self,line=None): self.require_open(line); return self.position


def binary_format(kind,formats,line=None):
    if len(formats)>1: fail('Binary fields accept only a byte width',line)
    width=formats[0] if formats else {'BYTE':1,'SHORT':2,'BOOLEAN':1,'INTEGER':4,'REAL':4}.get(kind)
    if kind=='STRING':
        if type(width) is not int or not 0<=width<=254: fail('Binary STRING needs byte width 0..254',line)
        return width,None
    formats_by_width={'BYTE':{1:'B'},'SHORT':{2:'h'},'BOOLEAN':{1:'?'},'INTEGER':{1:'b',2:'h',4:'i'},'REAL':{4:'f',8:'d'}}
    code=formats_by_width.get(kind,{}).get(width)
    if code is None: fail('Unsupported binary field type/width',line)
    return width,'<'+code


def file_piece(handle,kind,value,formats,line=None):
    rt=runtime()
    if not handle.binary: return rt.format_write_item(kind,value,formats,line)
    if kind=='STRING' and not formats: formats=[len(rt.ascii_string(value,line))]
    width,code=binary_format(kind,formats,line)
    if code is None: return rt.ascii_string(value,line)[:width].ljust(width,'\0').encode('ascii')
    if handle.reverse: code='>'+code[1:]
    try: return struct.pack(code,value)
    except (OverflowError,struct.error) as exc: raise rt.KarelRuntimeError('Binary field cannot represent supplied value',line) from exc


def file_read(state,handle,targets,line=None,*,line_breaks=(),formats=None):
    rt=runtime(); handle.require_open(line); formats=formats if formats is not None else [()] * len(targets)
    for target in targets:
        if type(target) is not rt.Reference: fail('FILE READ requires ordinary writable scalar targets',line)
    start=handle.position
    if handle.binary:
        if line_breaks: fail('CR is not a binary READ field',line)
        values=[]
        try:
            for target,field in zip(targets,formats):
                if target.spec[0]=='STRING' and not field: field=(target.spec[1],)
                width,code=binary_format(target.spec[0],field,line); raw=handle.owner.read_bytes(handle,width,line)
                if code and handle.reverse: code='>'+code[1:]
                value=raw.decode('ascii') if code is None else struct.unpack(code,raw)[0]
                values.append(rt.checked(target.spec,value,line))
        except Exception as exc:
            handle.position=start; handle.status=1
            if isinstance(exc,UnicodeError): raise rt.KarelRuntimeError('Binary STRING requires ASCII data',line) from exc
            raise
        for target,value in zip(targets,values): target.set(value,line)
    else:
        if handle.mode in ('W','A'): fail('FILE is not readable',line)
        raw=bytes(handle.owner.files[handle.name][start:])
        try: text=raw.decode('ascii')
        except UnicodeDecodeError: fail('Text FILE requires ASCII data',line)
        reader=rt.TextInput(text); previous=state._read
        try:
            state._read=reader; state.read_items(targets,line,line_breaks=line_breaks,formats=formats)
        except Exception:
            handle.status=1; raise
        finally: state._read=previous
        lines=text.splitlines(keepends=True)
        consumed=len(raw) if reader._row>=len(lines) else sum(len(part) for part in lines[:reader._row])+reader._column
        handle.position=start+consumed
    handle.status=0


class MemoryFiles:
    """Byte-backed named files; never consult the operating-system filesystem."""
    def __init__(self,initial=None,*,limit=16*1024*1024):
        if type(limit) is not int or not 1<=limit<=64*1024*1024: raise ValueError('File limit must be in 1..64 MiB')
        self.limit=limit; self.files={}; self.handles=[]
        for name,value in (initial or {}).items():
            data=value.encode('ascii') if type(value) is str else bytes(value)
            self._check(name,data); self.files[name]=bytearray(data)
    def _check(self,name,data):
        runtime().ascii_string(name)
        if not name or len(name)>254 or len(data)>self.limit: fail('Invalid memory file name or file size limit')
    def open(self,handle,mode,name,line=None):
        if handle.owner is not None: fail('FILE is already open',line)
        if self._busy(name): fail('File is already open through this backend',line)
        mode=runtime().ascii_string(mode,line).upper(); self._check(name,b'')
        binary='B' in mode or handle.binary; mode=mode.replace('B','')
        mode={'RO':'R','WO':'W','RW':'RW','UD':'RW','AP':'A'}.get(mode,mode)
        if mode not in ('R','W','RW','A'): fail('Unsupported memory file access mode',line)
        if mode=='R' and name not in self.files: fail('Memory file does not exist',line)
        if mode=='W' or name not in self.files: self.files[name]=bytearray()
        handle.name,handle.mode,handle.owner,handle.binary=name,mode,self,binary
        handle.position=len(self.files[name]) if mode=='A' else 0; handle.status=0
        self.handles.append(handle)
    def close(self,handle,line=None):
        handle.require_open(line); handle.owner=None
        self.handles=[item for item in self.handles if item is not handle]
    def _busy(self,name): return any(handle.owner is not None and handle.name==name for handle in self.handles)
    def write(self,handle,data,line=None):
        handle.require_open(line)
        if handle.mode=='R': fail('FILE is read-only',line)
        old=self.files[handle.name]; start=len(old) if handle.mode=='A' else handle.position
        if start+len(data)>self.limit: fail('Memory file size limit exceeded',line)
        if start>len(old): old.extend(b'\0'*(start-len(old)))
        old[start:start+len(data)]=data; handle.position=start+len(data); handle.status=0
    def read_bytes(self,handle,count,line=None):
        handle.require_open(line)
        if handle.mode in ('W','A'): fail('FILE is not readable',line)
        data=self.files[handle.name][handle.position:handle.position+count]
        if len(data)!=count: handle.status=1; fail('End of memory file',line)
        handle.position+=count; handle.status=0; return bytes(data)
    def snapshot(self): return {name:bytes(data) for name,data in self.files.items()}
    def flush(self,handle,line=None): handle.require_open(line)
    def list_names(self,pattern='*'): return sorted(name for name in self.files if fnmatch.fnmatchcase(name,pattern))
    def copy(self,source,target,overwrite=False):
        self._check(source,b''); self._check(target,b'')
        if self._busy(source) or self._busy(target): return 3
        if source not in self.files: return 1
        if target in self.files and not overwrite: return 2
        self.files[target]=self.files[source].copy(); return 0
    def delete(self,name):
        if self._busy(name): return 3
        if name not in self.files: return 1
        del self.files[name]; return 0
    def rename(self,source,target):
        self._check(target,b'')
        if self._busy(source) or self._busy(target): return 3
        if source not in self.files: return 1
        if target in self.files: return 2
        self.files[target]=self.files.pop(source); return 0


class PathValue:
    def __init__(self,spec): self.spec=spec; self.nodes=[]; self.data=runtime().initial_value(spec[2]) if spec[2] else None
    @property
    def node_spec(self):
        return self.spec[1] or ('STRUCTURE','STD_PTH_NODE',(('NODE_POS',('POSITION',)),))
    def node(self,index,line=None):
        index=runtime().integer(index,line)
        if not 1<=index<=len(self.nodes): fail('PATH node index out of range',line)
        return self.nodes[index-1]
    def append(self,index=None,line=None):
        if len(self.nodes)>=32767: fail('PATH node limit exceeded',line)
        index=len(self.nodes)+1 if index is None else runtime().integer(index,line)
        if not 1<=index<=len(self.nodes)+1: return 2
        self.nodes.insert(index-1,runtime().Structure(self.node_spec)); return 0
    def clone(self): return deepcopy(self)


class QueueValue:
    def __init__(self): self.spec=('QUEUE_TYPE',); self.initialized=False; self.entries=[]; self.sequence=0; self.buffer=None
    def bind(self,buffer,line=None):
        if not self.initialized: fail('QUEUE_TYPE requires INIT_QUEUE before use',line)
        if self.buffer is not None and self.buffer is not buffer: fail('Queue must keep its original backing ARRAY',line)
        self.buffer=buffer
    def sync(self,line=None):
        for index in range(len(self.buffer.values)): self.buffer.set(index+1,self.entries[index][1] if index<len(self.entries) else 0,line)


class RobotContext:
    """User-supplied offline kinematics/reachability, with no guessed robot model."""
    def __init__(self,*,forward=None,inverse=None,reachable=None,joint_limits=None,groups=None,active_group=1,frames=None,tools=None):
        for value in (forward,inverse,reachable):
            if value is not None and not callable(value): raise TypeError('Robot model adapters must be callable')
        self.forward,self.inverse,self.reachable=forward,inverse,reachable
        self.groups=dict(groups or {}); self.active_group=active_group
        self.frames=dict(frames or {}); self.tools=dict(tools or {}); self.model_config=None; self.model=None
        self.joint_limits=tuple(joint_limits) if joint_limits is not None else None
        if self.joint_limits is not None and any(len(pair)!=2 or not all(type(x) in (int,float) and math.isfinite(x) for x in pair) or pair[0]>pair[1] for pair in self.joint_limits): raise ValueError('Invalid explicit joint limits')
    @classmethod
    def from_config(cls,config):
        from .kinematics import robot_context_from_config
        return robot_context_from_config(config)
    def for_group(self,group=None):
        if not self.groups: return self
        group=self.active_group if group is None else group
        if group not in self.groups: fail('Robot group has no configured model')
        return self.groups[group]
    def frame(self,number=0):
        if number not in self.frames: fail('Requested frame is not configured')
        return self.frames[number].clone()
    def tool(self,number=0):
        if number not in self.tools: fail('Requested tool is not configured')
        return self.tools[number].clone()


class TaskRegistry:
    def __init__(self): self.tasks={}
    def bind(self,name,program):
        if not all(callable(getattr(program,method,None)) for method in ('run','resume','pause','stop')):
            raise TypeError('Tasks require a cooperative Program; translate with cooperative=True')
        self.tasks[runtime().ascii_string(name).upper()]=program


class KarelPause(RuntimeError):
    """Suspended with the Python generator/call stack retained for resume()."""


class KarelStop(RuntimeError):
    """Stopped permanently; construct a new Program to restart."""


def timer_clock(state,line=None):
    rt=runtime()
    try: value=state._clock_us() if state._clock_us else rt.time.monotonic_ns()//1000
    except Exception as exc: raise rt.KarelRuntimeError('Connected timer clock failed',line) from exc
    if type(value) is not int or value<0: fail('Connected timers require nonnegative integer clock microseconds',line)
    return value


def update_timers(state,line=None):
    if not state._timers: return
    now=timer_clock(state,line); pending=[]
    for record in state._timers.values():
        reference,previous,remainder=record
        if now<previous: fail('Connected timer clock moved backwards',line)
        increment,remainder=divmod(now-previous+remainder,1000)
        value=runtime().checked(('INTEGER',),runtime().integer(reference.raw(),line)+increment,line)
        pending.append((record,value,remainder))
    for record,value,remainder in pending:
        record[0].set(value,line); record[1:]=[now,remainder]


def connect_timer(state,reference,line=None):
    rt=runtime()
    if type(reference) is not rt.Reference or reference.spec!=('INTEGER',): fail('Timer requires ordinary INTEGER storage',line)
    key=(id(reference.storage),reference.key)
    if key in state._timers: fail('Timer is already connected',line)
    now=timer_clock(state,line)
    if reference.raw() is rt.UNINITIALIZED: reference.set(0,line)
    state._timers[key]=[reference,now,0]


def disconnect_timer(state,reference,line=None):
    key=(id(reference.storage),reference.key)
    if key not in state._timers: fail('Timer is not connected',line)
    del state._timers[key]


def define_condition(state,number,clauses,line=None,*,scan_ms=0):
    number=runtime().integer(number,line)
    if not 1<=number<=1000: fail('Condition number must be in 1..1000',line)
    if number in state._handlers: fail('Purge an existing condition before redefining it',line)
    scan_ms=runtime().integer(scan_ms,line)
    if not 0<=scan_ms<=86400000: fail('Handler scan interval must be in 0..86400000 ms',line)
    local_frame=state.local_frames[-1] if state.execution.local_handlers and state.local_frames else None
    state._handlers[number]=dict(clauses=clauses,enabled=False,frames=list(state.local_frames),scan_ms=scan_ms,due=None,local_frame=local_frame)


def condition_control(state,operation,number,line=None):
    number=runtime().integer(number,line)
    if operation=='PURGE': state._handlers.pop(number,None); return
    if number not in state._handlers: return
    state._handlers[number]['enabled']=operation=='ENABLE'
    if operation=='ENABLE': state._handlers[number]['due']=None


def checkpoint(state,line=None,*,force_pause=False,_defer_control=False):
    rt=runtime(); state.tick(line)
    # A library invocation owns its locals, while its caller still owns the
    # running task. Scan that task and honor its pause requests inside the call.
    parent=state._budget_parent
    if parent is not None: yield from checkpoint(parent,line,_defer_control=True)
    if not state._in_handler:
        for number in list(state._handlers):
            handler=state._handlers.get(number)
            if handler is None or not handler['enabled']: continue
            if handler['scan_ms']:
                now=timer_clock(state,line)
                if handler['due'] is not None and now<handler['due']: continue
                handler['due']=now+handler['scan_ms']*1000
            original,depth=state.local_frames,state.call_depth
            previous_scan=state._scanning_condition; state._scanning_condition=number
            previous_error=state._current_error
            state.local_frames=list(handler['frames']); state.call_depth=len(state.local_frames); state._in_handler=True
            try:
                for predicate,action in handler['clauses']:
                    result=predicate()
                    if rt.inspect.isgenerator(result): result=yield from result
                    if rt.boolean(result,line):
                        handler['enabled']=False
                        result=action()
                        if rt.inspect.isgenerator(result): yield from result
                        break
            finally:
                state.local_frames=original; state.call_depth=depth; state._in_handler=False
                state._scanning_condition=previous_scan
                state._current_error=previous_error
    if state._abort_requested and not state._in_handler and not _defer_control:
        state.abort(state._abort_request_line or line)
    if state._pause_requested and (not state._in_handler or force_pause) and not _defer_control:
        state.task_state='paused'; yield dict(kind='pause',line=line)
        state._pause_requested=False; state.task_state='running'
        if state._abort_requested: state.abort(state._abort_request_line or line)
    if state._scheduler is not None and not _defer_control: yield dict(kind='timeslice',line=line)


def cooperative_test(state,predicate,line=None):
    yield from checkpoint(state,line)
    value=predicate()
    if runtime().inspect.isgenerator(value): value=yield from value
    return runtime().boolean(value,line)


def pause_execution(state,line=None):
    state._pause_requested=True
    yield from checkpoint(state,line,force_pause=True)


def abort_execution(state,line=None):
    state._abort_requested=True; state._abort_request_line=line
    yield from checkpoint(state,line)


def drive(program):
    state=program._state
    if state._driving: fail('A Program cannot be driven recursively')
    state._driving=True
    try:
        event=next(program._execution)
        if type(event) is not dict or event.get('kind')!='pause': fail('Unknown cooperative execution event')
        state.task_state='paused'; raise KarelPause('Task paused; call Program.resume()')
    except StopIteration as finished:
        program._execution=None; state.task_state='completed'; return finished.value
    except KarelPause: raise
    except BaseException as exc:
        if program._execution is not None: program._execution.close()
        program._execution=None
        state.task_state='stopped' if isinstance(exc,KarelStop) else 'aborted' if isinstance(exc,runtime().KarelAbort) else 'failed'
        raise
    finally: state._driving=False


def run_cooperative(program,max_steps=100000):
    state=program._state
    if getattr(program,'_execution',None) is not None: fail('Program is paused or running; resume or stop it before starting again')
    if state.task_state=='stopped': raise KarelStop('Task is stopped; construct a new Program')
    state.begin(max_steps); state.task_state='running'; program._execution=program._execute()
    return drive(program)


def resume_cooperative(program):
    if program._state.task_state!='paused': fail('Only a paused task can resume')
    if program._state._scheduler is not None: fail('Scheduled tasks continue through their TaskScheduler')
    program._state._lifecycle['CONTINUE']+=1
    program._state.task_state='running'; return drive(program)


def stop_cooperative(program):
    state=program._state
    if state._driving: raise KarelStop('Task stopped')
    if getattr(program,'_execution',None) is not None:
        program._execution.close(); program._execution=None
    state.task_state='stopped'
    state._scheduler=None
    if state._scheduler_clock: state._clock_us=None; state._scheduler_clock=False


class ExecutionContext:
    def __init__(self,*,strings=None,positions=None,ports=None,variables=None,files=None,robot=None,externals=None,tasks=None,numeric=None,events=None,semaphores=None,errors=None,local_handlers=False):
        self.strings,self.positions,self.ports=strings,positions,ports
        self.variables=variables if variables is not None else VariableStore()
        self.files,self.robot=files,robot
        self.externals=dict(externals or {}); self.entries={}
        self.tasks=tasks if tasks is not None else TaskRegistry()
        self.numeric=numeric; self.events=events
        self.semaphores=semaphores; self.errors=errors
        if type(local_handlers) is not bool: raise TypeError('local_handlers must be BOOLEAN')
        self.local_handlers=local_handlers
    def to_config(self):
        from .storage import context_config
        return context_config(self)
    def save(self,path):
        from .storage import write_json
        write_json(path,self.to_config())
    @classmethod
    def load(cls,path):
        import json
        from pathlib import Path
        return cls.from_config(json.loads(Path(path).read_text(encoding='utf-8-sig')))
    def require(self,name,line=None):
        value=getattr(self,name)
        if value is None: fail('Operation requires explicit ExecutionContext '+name+' service',line)
        return value
    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'strings','positions','ports','files','numeric','variables','robot','events','semaphores','errors','local_handlers'}: raise ValueError('Unknown execution context fields')
        for name,allowed in (('strings',{'count','capacity','values'}),('positions',{'count','groups','values'}),('ports',{'counts','values'})):
            if name in config and (type(config[name]) is not dict or set(config[name])-allowed): raise ValueError('Unknown '+name+' context fields')
        services={}
        if 'local_handlers' in config: services['local_handlers']=config['local_handlers']
        if 'strings' in config:
            row=config['strings']; services['strings']=StringRegisters(row['count'],{int(k):v for k,v in row.get('values',{}).items()},capacity=row.get('capacity',254))
        if 'positions' in config:
            from .storage import decode_typed
            row=config['positions']; values={}
            for key,value in row.get('values',{}).items():
                pair=tuple(int(x) for x in key.split(':'))
                if len(pair)==1: pair=(row.get('groups',[1])[0],pair[0])
                if len(pair)!=2: raise ValueError('Position keys require group:number')
                values[pair]=decode_typed(value)[1]
            services['positions']=PositionRegisters(row['count'],values,groups=row.get('groups',(1,)))
        if 'ports' in config:
            row=config['ports']; services['ports']=PortBank(row['counts'],{(kind,int(n)):v for kind,values in row.get('values',{}).items() for n,v in values.items()})
        if 'files' in config:
            services['files']=MemoryFiles({name:bytes.fromhex(value['hex']) if type(value) is dict else value for name,value in config['files'].items()})
        if 'numeric' in config: services['numeric']=runtime().NumericRegisters.from_config(config['numeric'])
        if 'variables' in config:
            from .storage import decode_typed
            variables=VariableStore()
            for row in config['variables']:
                if set(row)!={'program','path','type','value'}: raise ValueError('Variable state requires program, path, type and value')
                spec,value=decode_typed({'type':row['type'],'value':row['value']})
                variables.bind(row['program'],row['path'],runtime().Reference(spec,{'value':value},'value'))
            services['variables']=variables
        if 'robot' in config: services['robot']=RobotContext.from_config(config['robot'])
        if 'events' in config:
            from .scheduling import EventBank
            services['events']=EventBank(config['events'])
        if 'semaphores' in config:
            from .control import SemaphoreBank
            services['semaphores']=SemaphoreBank.from_config(config['semaphores'])
        if 'errors' in config:
            from .control import ErrorHistory
            services['errors']=ErrorHistory.from_config(config['errors'])
        return cls(**services)
    def invoke(self,state,name,arguments,line=None):
        rt=runtime(); args=list(arguments)
        signature=PROCEDURES.get(name,FUNCTIONS.get(name,((),None))[0])
        if name in OPTIONAL_LAST and len(args)==len(signature)-1: args.append(1 if name!='SET_FILE_ATR' else 0)
        if len(args)!=len(signature): fail('Service argument count mismatch',line)
        outputs_checked(signature,args,line)
        if name in ('CLEAR_SEMA','POST_SEMA','SEMA_COUNT'):
            bank=self.require('semaphores',line)
            return (bank.clear if name=='CLEAR_SEMA' else bank.post if name=='POST_SEMA' else bank.value)(args[0],line)
        if name in ('PEND_SEMA','POST_ERR'):
            from .control import pend_semaphore,post_error
            return (pend_semaphore if name=='PEND_SEMA' else post_error)(state,*args,line=line)
        if name in ('COPY_FILE','DELETE_FILE','RENAME_FILE','FILE_LIST'):
            files=self.require('files',line)
            try:
                if name=='COPY_FILE': code=files.copy(args[0],args[1],args[2])
                elif name=='DELETE_FILE': code=files.delete(args[0])
                elif name=='RENAME_FILE': code=files.rename(args[0],args[1])
                else:
                    if args[1]<0 or args[2]!=0: fail('FILE_LIST requires nonnegative skip and portable name format 0',line)
                    selected=files.list_names(args[0])[args[1]:]; array=args[3].raw(); selected=selected[:len(array.values)]
                    for i,name in enumerate(selected): array.set(i+1,name,line)
                    args[4].set(len(selected),line); code=0
            except (OSError,ValueError) as exc: raise rt.KarelRuntimeError('FILE operation failed: '+str(exc),line) from exc
            args[-1].set(code,line); return
        if name in ('CONT_TASK','PAUSE_TASK','ABORT_TASK','RUN_TASK'):
            task=self.tasks.tasks.get(args[0].upper())
            if task is None: args[-1].set(1,line); return
            if task is getattr(state,'program',None) and name in ('CONT_TASK','RUN_TASK'): fail('A task cannot synchronously drive itself',line)
            if name=='PAUSE_TASK':
                if args[2]: fail('Motion-stop semantics are outside the offline task model',line)
                task._state._pause_requested=True
            elif name=='ABORT_TASK':
                if args[2]: fail('Motion cancellation is outside the offline task model',line)
                if getattr(task._state,'_driving',False): task._state.abort(line)
                task.stop()
                task._state._aborted=True; task._state._abort_line=line; task._state.task_state='aborted'
            else:
                if name=='RUN_TASK' and (args[1]!=0 or args[3] or args[4]!=0): fail('Offline RUN_TASK requires line 0, no motion and lock mask 0',line)
                if hasattr(self.tasks,'start'):
                    if name=='CONT_TASK': self.tasks.continue_task(args[0])
                    else: self.tasks.start(args[0],paused=args[2])
                    args[-1].set(0,line); return
                try:
                    if name=='CONT_TASK': task.resume()
                    else:
                        if args[2]: task._state._pause_requested=True
                        task.run()
                except KarelPause: pass
            args[-1].set(0,line); return
        if name in ('GET_STR_REG','SET_STR_REG'):
            bank=self.require('strings',line); number=args[0]
            if name=='GET_STR_REG':
                code,value=bank.read(number)
                if code==0: args[1].set(value,line)
            else: code=bank.write(number,args[1])
            args[-1].set(code,line); return
        if name in ('GET_POS_REG','GET_JPOS_REG','SET_POS_REG','SET_EPOS_REG','SET_JPOS_REG'):
            bank=self.require('positions',line); number=args[0]; group=args[-1]
            if name.startswith('SET_'):
                code=bank.write(number,args[1],group); args[2].set(code,line); return
            code,value=bank.read(number,group)
            if code==0:
                if name=='GET_POS_REG' and value.spec[0]!='JOINTPOS': value=pose_extended(value,line)
                elif name=='GET_JPOS_REG' and value.spec[0]=='JOINTPOS' and value.spec!=('JOINTPOS',9): code=3
                elif (name=='GET_JPOS_REG')!=(value.spec[0]=='JOINTPOS'): code=3
            args[1].set(code,line)
            if code: fail('Position register is absent, out of range or has a different representation',line)
            return value
        if name in ('GET_VAR','SET_VAR'): return self.variable(state,name,args,line)
        if name=='COPY_PATH':
            source,start,end,destination,status=args
            if source.spec!=destination.spec: status.set(3,line); return
            copied=source.clone()
            if start==end==0: pass
            elif not 1<=start<=len(copied.nodes) or not 1<=end<=len(copied.nodes): status.set(2,line); return
            else:
                direction=1 if end>=start else -1
                copied.nodes=[copied.nodes[i-1] for i in range(start,end+direction,direction)]
            destination.set(copied,line); status.set(0,line); return
        if name in ('APPEND_NODE','INSERT_NODE','DELETE_NODE','PATH_LEN'):
            path=args[0].raw() if type(args[0]) is rt.Reference else args[0]
            if name=='PATH_LEN': return len(path.nodes)
            if name=='APPEND_NODE': code=path.append(line=line)
            elif name=='INSERT_NODE': code=path.append(args[1],line)
            else:
                code=0 if 1<=args[1]<=len(path.nodes) else 2
                if not code: del path.nodes[args[1]-1]
            args[-1].set(code,line); return
        if 'QUEUE' in name: return self.queue(name,args,line)
        if name in ('GET_FILE_POS','BYTES_LEFT','IO_STATUS','SET_FILE_POS','BYTES_AHEAD','SET_FILE_ATR','CLR_IO_STAT'):
            handle=args[0]
            if name=='SET_FILE_ATR':
                if handle.owner is not None: fail('File attributes must be set before OPEN',line)
                attribute=args[1]
                if attribute==1: handle.interactive=True
                elif attribute==2: handle.binary=True
                elif attribute==3: handle.reverse=True
                elif attribute==4: handle.field=True
                elif attribute==5:
                    if not 0<=args[2]<=127: fail('ATR_EOL requires an ASCII character code',line)
                    handle.eol=args[2]
                else: fail('Unsupported portable file attribute',line)
                return
            if name=='CLR_IO_STAT': handle.status=0; return
            if name=='IO_STATUS': return handle.status
            handle.require_open(line); length=len(handle.owner.files[handle.name])
            if name=='GET_FILE_POS': return handle.position
            if name=='BYTES_LEFT': return length-handle.position
            if name=='BYTES_AHEAD': args[1].set(length-handle.position,line); args[2].set(0,line); return
            position=length if args[1]==-1 else args[1]
            code=0 if 0<=position<=length else 2
            if not code: handle.position=position
            args[-1].set(code,line); return
        if name=='MIRROR': return mirror(*args,line=line)
        if name in ('IN_RANGE','J_IN_RANGE'):
            robot=self.require('robot',line).for_group(getattr(state,'robot_group',None)); value=args[0]
            if name=='IN_RANGE':
                if robot.reachable is None: fail('IN_RANGE requires an explicit reachability adapter',line)
                pose=rt.frame_value(value,line)
                try: answer=robot.reachable(pose)
                except Exception as exc: raise rt.KarelRuntimeError('Reachability adapter failed: '+str(exc),line) from exc
                return rt.boolean(answer,line)
            if robot.joint_limits is None or len(robot.joint_limits)!=len(value.values): fail('J_IN_RANGE requires explicit limits for every joint',line)
            return all(lo<=rt.real(axis,line)<=hi for axis,(lo,hi) in zip(value.values,robot.joint_limits))
        if name in ('JOINT2POS','POS2JOINT'): return self.kinematics(name,args,line,group=getattr(state,'robot_group',None))
        fail('Unsupported extended operation '+name,line)
    def resolve(self,state,program,path,line=None):
        rt=runtime(); program=program.upper(); path=path.upper()
        # Explicit system roots and full-path bindings have precedence over discovery.
        selected=program if program not in ('',state.program_name) else state.program_name
        reference=self.variables.bindings.get((selected,path)) or self.variables.bindings.get((program,path))
        owner=state if program in ('',state.program_name) else self.variables.programs.get(program)
        root=re.match(r'[A-Z_][A-Z_0-9]*',path)
        if reference is not None and (owner is None or root is None or root[0] not in owner.types): return reference
        if path.startswith('$'):
            candidates=[(key,reference) for (owner,key),reference in self.variables.bindings.items() if owner in (program,selected,'SYSTEM','*SYSTEM*','') and (path==key or path.startswith(key+'.') or path.startswith(key+'['))]
            if candidates:
                key,reference=max(candidates,key=lambda item:len(item[0])); rest=path[len(key):]
                return self.descend(reference,rest,line)
        if program not in ('',state.program_name):
            state=self.variables.programs.get(program)
            if state is None: fail('Variable program is not attached to the explicit context',line)
        tokens=re.fullmatch(r'([A-Z_][A-Z_0-9]*)(.*)',path)
        if not tokens or tokens[1] not in state.types: fail('Variable path requires a static declared global',line)
        value=state.values[tokens[1]]
        reference=value if isinstance(value,rt.Reference) else rt.Reference(state.types[tokens[1]],state.values,tokens[1]); rest=tokens[2]
        return self.descend(reference,rest,line)
    def descend(self,reference,rest,line=None):
        rt=runtime()
        while rest:
            field=re.match(r'\.([A-Z_][A-Z_0-9]*)',rest)
            index=re.match(r'\[([0-9]+(?:,[0-9]+)*)\]',rest)
            if field: reference=rt.field_reference(reference.raw(),field[1],line); rest=rest[field.end():]
            elif index:
                numbers=tuple(int(x) for x in index[1].split(',')); reference=rt.index_reference(reference.raw(),numbers[0] if len(numbers)==1 else numbers,line); rest=rest[index.end():]
            else: fail('Invalid static variable path',line)
        return reference
    def variable(self,state,name,args,line):
        rt=runtime(); entry,program,path,value,status=args
        try: target=self.resolve(state,rt.ascii_string(program,line),rt.ascii_string(path,line),line)
        except rt.KarelRuntimeError: status.set(1,line); return
        if type(target) is not rt.Reference: fail('Protected variable storage cannot be a GET_VAR/SET_VAR alias',line)
        key=(program.upper(),path.upper())
        if key not in self.entries: self.entries[key]=len(self.entries)+1
        if name=='GET_VAR':
            raw=target.raw()
            if raw is rt.UNINITIALIZED: value.clear(); entry.set(self.entries[key],line); status.set(12311,line); return
            if not (value.spec==target.spec or value.spec[0]==target.spec[0]=='STRING'): status.set(3,line); return
            copied=rt.checked(value.spec,raw,line); value.set(copied,line)
        else:
            if rt._reference_cells(target) & (rt._reference_cells(entry)|rt._reference_cells(status)): fail('SET_VAR target overlaps entry/status',line)
            copied=rt.checked(target.spec,value,line); target.set(copied,line)
        entry.set(self.entries[key],line); status.set(0,line)
    def queue(self,name,args,line):
        rt=runtime()
        if name=='INIT_QUEUE':
            q=args[0].raw(); q.initialized=True; q.entries=[]; q.sequence=0; q.buffer=None; return
        offset=0 if name in ('GET_QUEUE','COPY_QUEUE') else 1 if name in ('APPEND_QUEUE','DELETE_QUEUE','MODIFY_QUEUE') else 2
        if name=='MODIFY_QUEUE': offset=2
        q=args[offset].raw(); buffer=args[offset+1].raw(); q.bind(buffer,line); code=0
        if name in ('APPEND_QUEUE','INSERT_QUEUE'):
            if len(q.entries)>=len(buffer.values): code=2
            elif name=='INSERT_QUEUE' and not any(pair[0]==args[1] for pair in q.entries): code=1
            else:
                q.sequence=rt.checked(('INTEGER',),q.sequence+1,line)
                at=len(q.entries) if name=='APPEND_QUEUE' else next(i for i,pair in enumerate(q.entries) if pair[0]==args[1])
                q.entries.insert(at,(q.sequence,rt.integer(args[0],line)))
                if name=='APPEND_QUEUE': args[-2].set(q.sequence,line)
        elif name=='GET_QUEUE':
            if not q.entries: code=61002
            else:
                sequence,value=q.entries.pop(0); args[2].set(value,line); args[3].set(sequence,line)
        elif name=='COPY_QUEUE':
            if args[2]<0 or args[3]<0: fail('Queue copy sequence and skip must be nonnegative',line)
            at=0 if args[2]==0 else next((i for i,pair in enumerate(q.entries) if pair[0]==args[2]),None)
            if at is None: code=1
            selected=[] if at is None else q.entries[at+args[3]:]
            output=args[4].raw(); selected=selected[:len(output.values)]
            for i,(_,value) in enumerate(selected): output.set(i+1,value,line)
            args[5].set(len(selected),line)
        else:
            sequence=args[1] if name=='MODIFY_QUEUE' else args[0]
            at=next((i for i,pair in enumerate(q.entries) if pair[0]==sequence),None)
            if at is None: code=1
            elif name=='DELETE_QUEUE': del q.entries[at]
            else: q.entries[at]=(sequence,rt.integer(args[0],line))
        q.sync(line); args[-1].set(code,line)
    def kinematics(self,name,args,line,*,group=None):
        rt=runtime(); robot=self.require('robot',line).for_group(group)
        callback=robot.forward if name=='JOINT2POS' else robot.inverse
        if callback is None: fail(name+' requires an explicit robot model adapter',line)
        inputs=deepcopy(tuple(args[:4] if name=='JOINT2POS' else args[:7]))
        try: result=callback(*inputs)
        except Exception as exc: raise rt.KarelRuntimeError('Robot model adapter failed: '+str(exc),line) from exc
        if name=='JOINT2POS':
            if type(result) is not tuple or len(result)!=3: fail('Forward adapter must return (position,config,external_axes)',line)
            if not isinstance(result[0],rt.Structure) or result[0].spec[0] not in ('POSITION','XYZWPR','XYZWPREXT'):
                fail('Forward adapter must return a complete pose',line)
            position=rt.convert_position(('POSITION',),result[0],line) if result[0].spec!=('POSITION',) else rt.frame_value(result[0],line)
            config=rt.checked(('CONFIG',),result[1],line); external=[rt.real(v,line) for v in result[2]]
            array=args[6].raw()
            if len(external)!=len(array.values): fail('Forward external axis result does not match output ARRAY',line)
            args[4].set(position,line); args[5].set(config,line)
            for i,value in enumerate(external): array.set(i+1,value,line)
        else:
            result=rt.checked(args[7].spec,result,line); args[7].set(result,line)
        args[-1].set(0,line)


def mirror(value,frame,orientation,line=None):
    rt=runtime(); value=rt.frame_value(value,line); frame=rt.frame_value(frame,line)
    rotation,location,config=rt._frame_parts(value,line); plane,origin,_=rt._frame_parts(frame,line)
    normal=tuple(row[1] for row in plane); distance=sum(normal[i]*(location[i]-origin[i]) for i in range(3))
    reflected=tuple(location[i]-2*normal[i]*distance for i in range(3))
    if rt.boolean(orientation,line):
        # Reflect the frame, then reverse its local Y to retain a proper rotation.
        rotation=tuple(tuple((rotation[i][j]-2*normal[i]*sum(normal[k]*rotation[k][j] for k in range(3)))*(-1 if j==1 else 1) for j in range(3)) for i in range(3))
    result=rt._frame_result(rotation,reflected,config,line,result_type=('XYZWPR',))
    result=pose_extended(result,line)
    if value.spec==('XYZWPREXT',):
        for key in ('EXT1','EXT2','EXT3'): result.values[key]=value.values[key]
    return result
