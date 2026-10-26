"""Portable logical TP archives; never load native code or execute instructions."""
from copy import deepcopy
import json
import re


ARCHIVE_CONSTANTS={name:index for index,name in enumerate(('PBR_VRTYPE','PBR_MNTYPE','PBR_JBTYPE',
    'PBR_PRTYPE','PBR_MRTYPE','PBR_PCTYPE','PBR_ALLTYPE','PBR_NVRTYPE','PBR_NMRTYPE'),1)}
ARCHIVE_NAMES=('SAVE','LOAD','CLEAR','PROG_BACKUP','PROG_RESTORE','PROG_CLEAR')
FORMAT='karel2py-teach-program-v1'


def rt():
    from . import runtime
    return runtime


def call_graph(value,limit):
    from .teach import name_key
    if value is None:return {}
    if type(value) is not dict or len(value)>limit:raise ValueError('TP calls require a bounded mapping')
    result={};edges=0
    for name,targets in value.items():
        key=name_key(name) if type(name) is str else None
        if key is None or key in result or type(targets) not in (list,tuple) or len(targets)>limit:
            raise ValueError('Invalid or duplicate TP dependency list')
        edges+=len(targets)
        if edges>32767:raise ValueError('TP dependency graph exceeds 32767 edges')
        names=[];seen=set()
        for target in targets:
            target=name_key(target) if type(target) is str else None
            if target is None or target in seen:raise ValueError('Invalid or duplicate TP dependency')
            names.append(target);seen.add(target)
        result[key]=names
    return result


def specification(value,*,wildcard=False):
    value=rt().ascii_string(value)
    if not value or len(value)>254 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Invalid archive file specification')
    value=value.replace('\\','/')
    device,sep,path=value.partition(':')
    if sep:
        if not re.fullmatch(r'[A-Za-z][A-Za-z_0-9]{0,7}',device) or device.upper() in ('MF','PIP') or re.fullmatch(r'[CS][0-9]+',device.upper()):
            raise ValueError('Archive requires an ordinary file device')
        prefix=device.upper()+':'
        if path.startswith('/'):path=path[1:]
    else:prefix='';path=value
    parts=path.split('/')
    if ':' in path or any(part in ('','.','..') or not re.fullmatch(r'[A-Za-z0-9_.-]+',part) for part in parts[:-1]):
        raise ValueError('Archive path must remain relative')
    match=re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]{0,35}|\*)(?:\.([A-Za-z]{2}))?',parts[-1])
    if not match or match[1]=='*' and not wildcard:raise ValueError('Archive requires a plain program file name')
    return prefix+('/'.join(parts[:-1])+'/' if len(parts)>1 else ''),match[1].upper(),(match[2] or '').upper()


def options(bank):
    return {name:getattr(bank,name) for name in ('groups','position_limit','program_limit','register_limit',
        'string_register_limit','position_register_limit','string_capacity','archive_limit')}


def protected(context,name,bank):
    record=context.program_attributes.record(name) if context.program_attributes is not None else None
    return (record or {}).get('attributes',{}).get('AT_PROTECT',bank._programs[name]['attributes'].get('AT_PROTECT',1))==2


def guard(context,state,bank,name,*,write):
    from .inspection import attached_programs
    if name in attached_programs(context,state):return 4
    record=context.program_attributes.record(name) if context.program_attributes is not None else None
    if record is not None and record.get('active',False):return 4
    if bank.busy(name):return 4
    if write and (bank.selected==name or name in bank._callers.values()):return 4
    if write and name in bank._programs and protected(context,name,bank):return 4
    return 0


def refresh_flags(context,bank,name):
    service=context.program_attributes
    if service is None or service.record(name) is None:return
    metadata=bank.metadata(name)
    service._records[name].update(loaded=metadata is not None,
        initialized=False if metadata is None else metadata['initialized'],active=False)


def encode(bank,name):
    envelope=dict(format=FORMAT,name=name,program=bank.program_config(name),calls=[target for target in bank._calls.get(name,[]) if bank._programs.get(target,{}).get('type')!='MR'])
    return encode_json(envelope,bank.archive_limit)


def encode_json(envelope,limit):
    output=bytearray()
    for chunk in json.JSONEncoder(ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).iterencode(envelope):
        data=chunk.encode('ascii')
        if len(output)+len(data)+1>limit:raise ValueError('Archive exceeds byte budget')
        output.extend(data)
    return bytes(output)+b'\n'


def decode_json(data,limit):
    if len(data)>limit:raise ValueError('Archive exceeds byte budget')
    # Bound nesting before the JSON decoder, respecting quoted punctuation.
    depth=0;quoted=escaped=False
    for char in data.decode('ascii'):
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
        elif char=='"':quoted=True
        elif char in '[{':
            depth+=1
            if depth>32:raise ValueError('Archive JSON exceeds depth 32')
        elif char in ']}':depth-=1
    def pairs(items):
        row={}
        for key,value in items:
            if key in row:raise ValueError('Duplicate archive JSON key')
            row[key]=value
        return row
    def constant(value):raise ValueError('Nonfinite archive number')
    return json.loads(data,object_pairs_hook=pairs,parse_constant=constant)


def decode(bank,data):
    from .teach import TeachPrograms,name_key
    row=decode_json(data,bank.archive_limit)
    if type(row) is not dict or set(row)!={'format','name','program','calls'} or row['format']!=FORMAT:
        raise ValueError('Unsupported portable archive format')
    name=name_key(row['name']) if type(row['name']) is str else None
    if name is None or name!=row['name']:raise ValueError('Archive identity must be canonical')
    calls=call_graph({name:row['calls']},bank.program_limit)
    validated=TeachPrograms.from_config(dict(**options(bank),programs={name:row['program']},calls=calls))
    return name,validated._programs[name],validated._calls[name]


def read_file(files,name,limit):
    from .remote_messages import read_file as read
    code,_,data=read(files,name,delete=False,limit=limit)
    return (4 if code==3 else code),data


def write_files(files,plan,*,overwrite=False,reserve_kb=0):
    from .extended import MemoryFiles
    from .devices import DeviceFiles
    if type(files) not in (MemoryFiles,DeviceFiles):return 4
    prepared=[];growth={};new=0
    if reserve_kb*1024>files.limit and type(files) is MemoryFiles:return 5
    try:
        for name,data in plan:
            key=files.canonical(name) if type(files) is DeviceFiles else name
            if files._busy(key):return 4
            if key in files.files and not overwrite:return 3
            if len(data)>files.limit:return 5
            files._check(key,data)
            if key not in files.files:new+=1
            old=files.files.get(key,b'')
            unchanged=key in files.files and old==data
            if type(files) is DeviceFiles:
                device=key.split(':',1)[0];volume=files.require_volume(device,write=True)
                delta=0 if unchanged else len(data)-len(old)+(len(old) if volume['retain_deleted'] else 0)
                growth[device]=growth.get(device,0)+delta
            prepared.append((key,data,unchanged))
        if len(files.files)+new>32767:return 5
        if type(files) is DeviceFiles:
            for device,delta in growth.items():
                volume=files._volumes[device];free=volume['capacity']-files.used(device)
                if free<max(delta,reserve_kb*1024):return 5
    except rt().KarelRuntimeError:return 4
    # Exact in-memory backends, with all writes and quota deltas prepared first.
    for key,data,unchanged in prepared:
        if unchanged:continue
        if type(files) is DeviceFiles:
            volume=files._volumes[key.split(':',1)[0]]
            if volume['retain_deleted']:volume['garbage']+=len(files.files.get(key,b''))
        files.files[key]=bytearray(data)
    return 0


def walk(bank,root,*,missing=False):
    order=[];seen=set();pending=[root]
    while pending:
        name=pending.pop()
        if name in seen:continue
        seen.add(name)
        if len(seen)>bank.program_limit:return 5,[]
        row=bank._programs.get(name)
        if row is None:
            if missing and name!=root:continue
            return 1,[]
        if name!=root and row['type']=='MR':continue
        order.append(name);pending.extend(reversed(bank._calls.get(name,[])))
    return 0,order


def filter_kind(kind,selector):
    if selector in (1,6):return None
    selected={2:('TP','JB','PR','MR'),3:('JB',),4:('PR',),5:('MR',),
        7:('TP','JB','PR','MR'),8:('TP','JB','PR','MR'),9:('TP','JB','PR')}
    return kind in selected[selector] if selector in selected else None


def save(context,state,bank,program,spec):
    from .teach import name_key
    try:prefix,base,extension=specification(spec,wildcard=True)
    except ValueError:return 2
    if extension!='TP':return 4
    if program=='*':names=sorted(bank._programs)
    else:
        key=name_key(program)
        if key is None or base=='*':return 2
        names=[key]
    if not names or any(name not in bank._programs for name in names):return 1
    plan=[];size=0
    for name in names:
        code=guard(context,state,bank,name,write=False)
        if code:return code
        try:data=encode(bank,name)
        except ValueError:return 5
        size+=len(data)
        if size>bank.archive_limit:return 5
        plan.append((prefix+(name if program=='*' else base)+'.TP',data))
    return write_files(context.require('files'),plan)


def load(context,state,bank,spec,overwrite):
    try:prefix,base,extension=specification(spec)
    except ValueError:return 2
    if extension!='TP':return 4
    code,data=read_file(context.require('files'),prefix+base+'.TP',bank.archive_limit)
    if code:return code
    try:name,row,calls=decode(bank,data)
    except (ValueError,TypeError,rt().KarelRuntimeError):return 6
    if name in bank._programs and not overwrite:return 3
    code=guard(context,state,bank,name,write=True)
    if code:return code
    if name not in bank._programs and len(bank._programs)>=bank.program_limit:return 5
    graph={**bank._calls,name:calls}
    try:call_graph(graph,bank.program_limit)
    except ValueError:return 5
    bank._programs[name]=row;bank._calls=graph;refresh_flags(context,bank,name);return 0


def clear(context,state,bank,spec,selector=None):
    try:prefix,root,extension=specification(spec)
    except ValueError:return 2
    if prefix:return 2
    if extension not in ('','TP'):return 4
    if selector is None:code,names=(0,[root]) if root in bank._programs else (1,[])
    else:
        if filter_kind('TP',selector) is None:return 4
        code,names=walk(bank,root,missing=True)
        names=[name for name in names if filter_kind(bank._programs[name]['type'],selector) and not protected(context,name,bank)]
    if code:return code
    for name in names:
        code=guard(context,state,bank,name,write=True)
        if code:return code
    for name in names:
        del bank._programs[name];bank._calls.pop(name,None);refresh_flags(context,bank,name)
    return 0


def backup(context,state,bank,spec,selector,reserve_kb,include_protected):
    try:prefix,root,_=specification(spec)
    except ValueError:return 2
    if filter_kind('TP',selector) is None:return 4
    if type(reserve_kb) is not int or not 0<=reserve_kb<=65536:return 2
    code,names=walk(bank,root)
    if code:return code
    plan=[];size=0
    for name in names:
        if not filter_kind(bank._programs[name]['type'],selector) or not include_protected and protected(context,name,bank):continue
        code=guard(context,state,bank,name,write=False)
        if code:return code
        try:data=encode(bank,name)
        except ValueError:return 5
        size+=len(data)
        if size>bank.archive_limit:return 5
        plan.append((prefix+name+'.TP',data))
    if not plan:return 0
    return write_files(context.require('files'),plan,overwrite=True,reserve_kb=reserve_kb)


def restore(context,state,bank,spec):
    try:prefix,root,_=specification(spec)
    except ValueError:return 2
    files=context.require('files');prepared={};seen=set();pending=[root];size=0
    graph=deepcopy(bank._calls)
    while pending:
        name=pending.pop()
        if name in seen:continue
        seen.add(name)
        if len(seen)>bank.program_limit:return 5
        if name in bank._programs:
            row=bank._programs[name];calls=bank._calls.get(name,[])
        else:
            code,data=read_file(files,prefix+name+'.TP',bank.archive_limit-size)
            if code:return code
            size+=len(data)
            try:identity,row,calls=decode(bank,data)
            except (ValueError,TypeError,rt().KarelRuntimeError):return 6
            if identity!=name:return 6
            if name!=root and row['type']=='MR':continue
            code=guard(context,state,bank,name,write=True)
            if code:return code
            prepared[name]=row;graph[name]=calls
        if name!=root and row['type']=='MR':continue
        pending.extend(reversed(calls))
    if len(bank._programs)+len(prepared)>bank.program_limit:return 5
    try:graph=call_graph(graph,bank.program_limit)
    except ValueError:return 5
    bank._programs.update(prepared);bank._calls=graph
    for name in prepared:refresh_flags(context,bank,name)
    return 0


def invoke(state,operation,args,line=None):
    from .variable_archives import variable_operation,invoke as invoke_variables
    if variable_operation(operation,args):return invoke_variables(state,operation,args,line)
    context=state.execution;bank=context.require('teach_programs',line)
    if operation=='SAVE':code=save(context,state,bank,*args[:-1])
    elif operation=='LOAD':code=load(context,state,bank,args[0],args[1]==1)
    elif operation=='CLEAR':code=clear(context,state,bank,args[0])
    elif operation=='PROG_CLEAR':code=clear(context,state,bank,*args[:-1])
    elif operation=='PROG_BACKUP':code=backup(context,state,bank,*args[:-1])
    else:code=restore(context,state,bank,args[0])
    args[-1].set(code,line)
