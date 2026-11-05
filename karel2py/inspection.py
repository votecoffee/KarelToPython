"""Bounded variable inspection and explicit offline program metadata."""
import fnmatch
import math
import re
from .extended import (PROGRAM_TYPES, PROGRAM_ATTRIBUTES, PROGRAM_KINDS,
                       PROGRAM_TEXT_ATTRIBUTES, PROGRAM_WRITABLE_ATTRIBUTES)


TYPE_CODES={'POSITION':1,'XYZWPR':2,'XYZWPREXT':6,'INTEGER':16,'REAL':17,
            'BOOLEAN':18,'VECTOR':19,'COMMON_ASSOC':20,'SHORT':23,'BYTE':24,'CONFIG':28,'GROUP_ASSOC':30,
            'FILE':29,'PATH':31,'STRING':209,'STRUCTURE':210,
            **{f'JOINTPOS{width}':25+16*(width-1) for width in range(1,10)}}


def runtime():
    from . import runtime as rt
    return rt


def variable_type(spec):
    rt=runtime(); shape=rt.array_dimensions(spec) if spec[0]=='ARRAY' else ()
    leaf=rt.array_leaf_spec(spec) if shape else spec
    name=leaf[1] if leaf[0]=='STRUCTURE' else f'JOINTPOS{rt.joint_width(leaf)}' if leaf[0]=='JOINTPOS' else leaf[0]
    return name,leaf,shape


def _type_metadata(spec):
    name,leaf,shape=variable_type(spec)
    row=dict(type=name)
    if shape:row['dimensions']=shape
    if leaf[0]=='STRING':row['string_capacity']=leaf[1]
    return row


def describe(spec):
    name,leaf,shape=variable_type(spec)
    code=TYPE_CODES.get('STRUCTURE' if leaf[0]=='STRUCTURE' else name)
    if code is None: raise NotImplementedError('No documented variable type code for '+name)
    return name,code,tuple(shape)+(0,)*(3-len(shape)),leaf[1] if leaf[0]=='STRING' else 0


def missing(value,spec,line=None):
    """Portable content rule; BYTE has no initialization tracking."""
    rt=runtime(); kind=spec[0]
    if value is rt.UNINITIALIZED: return True
    if value is rt.UNKNOWN_BYTE:
        if kind=='BYTE': return False
        raise rt.KarelRuntimeError('Unknown BYTE marker requires BYTE storage',line)
    if kind=='ARRAY':
        if not isinstance(value,rt.Array) or value.spec!=spec or len(value.values)!=math.prod(rt.array_shape(spec)):
            raise rt.KarelRuntimeError('Variable inspection found malformed ARRAY storage',line)
        flags=[missing(item,spec[2],line) for item in value.values]
        return any(flags)
    if kind in rt.RECORD_TYPES:
        if not isinstance(value,rt.Structure) or value.spec!=spec:
            raise rt.KarelRuntimeError('Variable inspection found mismatched record storage',line)
        if kind in rt.DATA_RECORD_TYPES: return rt._record_uninitialized(value,spec,line)
        fields=dict(rt.record_fields(spec))
        if set(value.values)!=set(fields): raise rt.KarelRuntimeError('Variable inspection found malformed record fields',line)
        flags=[missing(value.values[name],field,line) for name,field in fields.items()]
        return any(flags)
    if kind=='JOINTPOS':
        if not isinstance(value,rt.JointPosition) or value.spec!=spec or len(value.values)!=rt.joint_width(spec):
            raise rt.KarelRuntimeError('Variable inspection found malformed joint storage',line)
        return any([missing(axis,('REAL',),line) for axis in value.values])
    if kind=='FILE':
        if not isinstance(value,rt.FileHandle): raise rt.KarelRuntimeError('Variable inspection requires FILE storage',line)
        return value.owner is None
    if kind=='PATH':
        if not isinstance(value,rt.PathValue) or value.spec!=spec: raise rt.KarelRuntimeError('Variable inspection requires matching PATH storage',line)
        flags=[missing(node,value.node_spec,line) for node in value.nodes]
        if spec[2]: flags.append(missing(value.data,spec[2],line))
        return any(flags)
    rt.checked(spec,value,line)
    return False


def assign(outputs,values,line):
    rt=runtime()
    prepared=[rt.checked(target.spec,value,line) for target,value in zip(outputs,values)]
    for target,value in zip(outputs,prepared): target.set(value,line)


def any_initialized(value,spec,line=None,trail=()):
    """Any known global content, validating all branches before returning."""
    rt=runtime();kind=spec[0]
    if value is rt.UNINITIALIZED: return False
    if value is rt.UNKNOWN_BYTE:
        if kind=='BYTE': return False
        raise rt.KarelRuntimeError('Unknown BYTE marker requires BYTE storage',line)
    if id(value) in trail or len(trail)>=128:
        raise rt.KarelRuntimeError('Program initialization query found cyclic or excessive storage',line)
    trail=trail+(id(value),)
    if isinstance(value,rt.Reference):
        if value.spec!=spec: raise rt.KarelRuntimeError('Program initialization query found mismatched reference',line)
        return any_initialized(value.raw(),spec,line,trail)
    if kind=='ARRAY':
        if not isinstance(value,rt.Array) or value.spec!=spec or len(value.values)!=math.prod(rt.array_shape(spec)):
            raise rt.KarelRuntimeError('Program initialization query found malformed ARRAY storage',line)
        return any([any_initialized(item,spec[2],line,trail) for item in value.values])
    if kind in rt.RECORD_TYPES:
        fields=dict(rt.record_fields(spec))
        if not isinstance(value,rt.Structure) or value.spec!=spec or set(value.values)!=set(fields):
            raise rt.KarelRuntimeError('Program initialization query found malformed record storage',line)
        if kind in rt.DATA_RECORD_TYPES: rt._record_uninitialized(value,spec,line)
        return any([any_initialized(value.values[name],field,line,trail) for name,field in fields.items()])
    if kind=='JOINTPOS':
        if not isinstance(value,rt.JointPosition) or value.spec!=spec or len(value.values)!=rt.joint_width(spec):
            raise rt.KarelRuntimeError('Program initialization query found malformed joint storage',line)
        return any([any_initialized(axis,('REAL',),line,trail) for axis in value.values])
    if kind=='FILE':
        if not isinstance(value,rt.FileHandle): raise rt.KarelRuntimeError('Program initialization query requires FILE storage',line)
        return value.owner is not None
    if kind=='PATH':
        if not isinstance(value,rt.PathValue) or value.spec!=spec or type(value.nodes) is not list or len(value.nodes)>32767:
            raise rt.KarelRuntimeError('Program initialization query requires matching PATH storage',line)
        flags=[any_initialized(node,value.node_spec,line,trail) for node in value.nodes]
        if spec[2]: flags.append(any_initialized(value.data,spec[2],line,trail))
        return bool(value.nodes) or any(flags)
    if kind=='QUEUE_TYPE':
        from .extended import queue_variable_value
        return queue_variable_value(value,line).initialized
    return rt.checked(spec,value,line) is not rt.UNINITIALIZED


def attached_programs(context,state):
    rt=runtime();owners={};seen=set()
    pending=list(context.variables.programs.values())+[state]
    pending.extend(program._state for program in context.tasks.tasks.values())
    while pending:
        owner=pending.pop()
        if id(owner) in seen: continue
        seen.add(id(owner));owners.setdefault(owner.program_name,[]).append(owner)
        root=rt.task_root(owner)
        if root is not owner: pending.append(root)
        pending.extend(frame for frame,routine in root._task_frames)
    return owners


def program_metadata(context,state,operation,args,line=None):
    rt=runtime();name=rt.ascii_string(args[0],line).upper()
    valid=bool(re.fullmatch(r'[A-Z_][A-Z_0-9]{0,35}',name))
    owners=attached_programs(context,state).get(name,[]) if valid else []
    service=context.program_attributes
    record=service.record(name) if valid and service is not None else None
    teach=context.teach_programs
    teach_record=teach.metadata(name) if valid and teach is not None else None
    if teach_record is not None and not owners:
        if record is None: record=teach_record
        else:
            record={**record,'active':record.get('active',False) or teach_record['active'],
                    'loaded':True,'initialized':teach_record['initialized'],
                    'attributes':{**teach_record['attributes'],**record['attributes'],
                                  'AT_PROG_TYPE':teach_record['attributes']['AT_PROG_TYPE'],
                                  'AT_NUM_LINE':teach_record['attributes']['AT_NUM_LINE']}}
    if operation=='LOAD_STATUS':
        if owners:
            flags=[any_initialized(owner.values[key],spec,line) for owner in owners for key,spec in owner.types.items()]
            loaded,initialized=True,any(flags)
        else:
            loaded,initialized=(record.get('loaded',False),record.get('initialized',False)) if record is not None else (False,False)
        assign(args[1:],(loaded,initialized),line);return
    selector=rt.integer(args[1],line);status=args[-1]
    key=next((key for key,value in PROGRAM_ATTRIBUTES.items() if value==selector),None)
    if key is None: status.set(2,line);return
    if not owners and record is None: status.set(1,line);return
    if operation=='GET_ATTR_PRG':
        attrs=record['attributes'] if record is not None else {}
        if key=='AT_PROG_NAME': value=name[:PROGRAM_TEXT_ATTRIBUTES[key]]
        elif key=='AT_PROG_TYPE' and owners: value=PROGRAM_KINDS['PT_KRLPRG']
        elif key in attrs: value=attrs[key]
        elif key=='AT_COMMENT':
            comments=[argument for owner in owners for directive,argument in owner.program.source_directives if directive=='%COMMENT']
            if not comments: status.set(3,line);return
            value=comments[0][:PROGRAM_TEXT_ATTRIBUTES[key]]
        else: status.set(3,line);return
        target=args[3] if key in PROGRAM_TEXT_ATTRIBUTES else args[2]
        assign((target,status),(value,0),line);return
    if key not in PROGRAM_WRITABLE_ATTRIBUTES: status.set(2,line);return
    current=rt.task_root(state)
    active=bool(record is not None and record.get('active',False))
    for owner in owners:
        root=rt.task_root(owner)
        active|=(owner is state or owner is current or root._driving or root.task_state in ('running','waiting','paused'))
        active|=any(frame.program_name==name for frame,routine in current._task_frames)
    if active: status.set(4,line);return
    if service is None and (teach_record is None or owners): raise rt.KarelRuntimeError('SET_ATTR_PRG requires explicit ProgramAttributes context',line)
    value=args[3] if key in PROGRAM_TEXT_ATTRIBUTES else args[2]
    # Validate both the replacement and status before publishing metadata.
    from .extended import ProgramAttributes
    value=ProgramAttributes._value(key,value,line);rt.checked(status.spec,0,line)
    if teach_record is not None and not owners and (service is None or service.record(name) is None): teach.set_metadata(name,key,value)
    else: service.set_value(name,key,value,line)
    status.set(0,line)


def variable_info(context,state,args,line=None):
    rt=runtime(); program,path,uninit,type_name,type_code,dims,slen,status=args
    if rt.array_dimensions(dims.spec)!=(3,) or dims.spec[2]!=('INTEGER',):
        raise rt.KarelRuntimeError('VAR_INFO dimensions require ARRAY[3] OF INTEGER',line)
    try: target=context.resolve(state,rt.ascii_string(program,line),rt.ascii_string(path,line),line,path_nodes=True)
    except rt.KarelRuntimeError: status.set(1,line);return
    try: name,code,shape,length=describe(target.spec)
    except NotImplementedError: status.set(4,line);return
    flag=missing(target.raw(),target.spec,line)
    dimensions=rt.Array(dims.spec)
    for index,size in enumerate(shape,1): dimensions.set(index,size,line)
    assign((uninit,type_name,type_code,dims,slen,status),(flag,name,code,dimensions,length,0),line)


def declarations(context,state):
    """Canonical roots only; declarations override bindings just as resolve does."""
    owners=dict(context.variables.programs);owners[state.program_name]=state
    result={(program,name):spec for program,owner in owners.items() for name,spec in owner.types.items()}
    for (program,path),reference in context.variables.bindings.items():
        program=program or state.program_name
        if re.fullmatch(r'[A-Z_][A-Z_0-9]*',program) and re.fullmatch(r'\$?[A-Z_][A-Z_0-9]*',path):
            result.setdefault((program,path),reference.spec)
    return sorted(result.items())


def variable_list(context,state,args,line=None):
    rt=runtime(); program,pattern,kind,skip,form,names,count,status=args
    program=rt.ascii_string(program,line).upper() or state.program_name
    pattern=rt.ascii_string(pattern,line).upper()
    kind,skip,form=(rt.integer(value,line) for value in (kind,skip,form))
    if kind not in (0,*TYPE_CODES.values()) or skip<0 or form not in (1,2,3,4): status.set(2,line);return
    if not pattern or any(symbol in program+pattern for symbol in '[]?'):
        status.set(2,line);return
    roots=declarations(context,state)
    known=set(context.variables.programs)|{state.program_name}|{owner for (owner,name),spec in roots}
    if '*' not in program and program not in known:
        status.set(1,line);return
    rows=[]
    for (owner,name),spec in roots:
        if not (fnmatch.fnmatchcase(owner,program) and fnmatch.fnmatchcase(name,pattern)): continue
        if kind:
            try: code=describe(spec)[1]
            except NotImplementedError: continue
            if code!=kind: continue
        rows.append((owner,name))
    capacity=rt.array_dimensions(names.spec)[0]
    rows=rows[skip:skip+capacity];text=[]
    for owner,name in rows:
        if form==4 and (len(owner)>15 or len(name)>12): status.set(3,line);return
        text.append(owner if form==1 else name if form==2 else f'[{owner}]{name}' if form==3 else f'{owner:<15}{name:<12}')
    if any(len(value)>names.spec[2][1] for value in text): status.set(3,line);return
    array=rt.Array(names.spec)
    for index in range(1,capacity+1): array.set(index,text[index-1] if index<=len(text) else '',line)
    assign((names,count,status),(array,len(rows),0),line)


def kcl_variable_listing(state,operation,args,line=None):
    context=state.execution
    program=args[0] or state.program_name
    selector='' if program==state.program_name else program
    if operation=='SHOW_VAR':
        path,radix=args[1:]
        names=[(path,None)]
        values=True
    else:
        values,kind=args[1:]
        radix=None
        names=[(name,spec) for (owner,name),spec in declarations(context,state)
               if owner==program and not name.startswith('$')]
        if not names and program!=state.program_name and program not in context.variables.programs:return 1
        if kind is not None:
            names=[(name,spec) for name,spec in names if spec[0]==kind
                   or spec[0]=='JOINTPOS' and variable_type(spec)[0]==kind]
    def resolve(path):
        return context.resolve(state,selector,path,line,path_nodes=True)
    return _kcl_value_rows(state,program,names,values,radix,resolve,line)


def _kcl_value_rows(state,program,names,values,radix,resolve,line,**fields):
    from .archives import encode_json
    from .fileops import write_file_text
    from .storage import typed_value
    from .variable_archives import MAX_LEAVES, schema

    rt=runtime()
    if len(names)>MAX_LEAVES:return 5
    remaining=1024*1024
    leaves=0
    rows=[]
    for path,spec in names:
        if values:
            try:reference=resolve(path)
            except rt.KarelRuntimeError:return 1
            spec=reference.spec
        row=dict(program=program,name=path,**_type_metadata(spec),**fields)
        try:
            if values:
                if rt.file_storage_type(spec):
                    if radix:return 2
                    row['value_available']=False
                else:
                    value=reference.raw()
                    if radix and (type(value) is not int or spec[0] not in ('INTEGER','SHORT','BYTE')):return 2
                    leaves+=schema(spec,value)
                    if leaves>MAX_LEAVES:return 5
                    row['value']=typed_value(value,spec)['value']
                    if radix:row['formatted']=format(value,'#b' if radix=='BINARY' else '#x')
            encoded=encode_json(row,remaining)
        except (ValueError,TypeError,RecursionError,rt.KarelRuntimeError):return 5
        remaining-=len(encoded)
        rows.append(encoded)
    for row in rows:
        write_file_text(state,row.decode('ascii'),line)
    return 0


def _kcl_task_root(state,selector,line):
    from .scheduling import selected_task_root

    if not selector:return runtime().task_root(state)
    return selected_task_root(state.execution.tasks,selector,state,line)[1]


def _kcl_routine_frame(root,routine_filter,module_filter):
    # Handler predicates can temporarily replace local_frames with their captured
    # scope. _timer_frames retains the actual entered frames, including bridges.
    offsets={}
    for owner,routine in reversed(root._task_frames):
        offset=offsets.get(owner,len(owner._timer_frames))-1
        offsets[owner]=offset
        if (routine_filter is not None and routine!=routine_filter
                or module_filter is not None and owner.program_name!=module_filter):
            continue
        declarations,storage=owner._timer_frames[offset]
        return owner,routine,declarations,storage
    return None


def _kcl_local_write(state,root,frame,name,literal,line):
    from .dynamic import assign_scalar_literal

    rt=runtime()
    owner,routine,declarations,storage=frame
    if name not in declarations:return 1
    if root.task_state!='paused' or root._driving or root._abort_requested:return 4
    counter_roots=getattr(owner.program,'local_for_roots',{}).get(routine)
    if counter_roots is None or name in counter_roots or isinstance(storage[name],rt.Reference):return 4
    if declarations[name][0] not in ('INTEGER','SHORT','BYTE','REAL','BOOLEAN','STRING'):return 4
    key=id(storage),name
    def references():
        contexts={state.execution:state,owner.execution:owner}
        for context,caller in contexts.items():
            yield from context.variables.bindings.values()
            for instances in attached_programs(context,caller).values():
                for active in instances:
                    yield from active.values.values()
                    for _,locals_ in active._timer_frames:
                        yield from locals_.values()

    if key in owner.execution._timer_claims:return 4
    for index,value in enumerate(references(),1):
        if index>32767:return 5
        if isinstance(value,rt.Reference) and (id(value.storage),value.key)==key:return 4
    return assign_scalar_literal(rt.Reference(declarations[name],storage,name),literal,line)


def kcl_local_operation(state,operation,args,line=None):
    """Resolve a live routine frame without substituting a global variable."""
    from .dynamic import IDENTIFIER,variable_checkpoint

    selector,routine_filter,module_filter,*request=args
    if operation=='SET_LOCAL_VAR':variable_checkpoint(state,line)
    root=_kcl_task_root(state,selector,line)
    if root is None or root.task_state not in ('running','paused','waiting'):return 1
    frame=_kcl_routine_frame(root,routine_filter,module_filter)
    if frame is None:return 1
    if operation=='SET_LOCAL_VAR':return _kcl_local_write(state,root,frame,*request,line)
    owner,routine,declarations,storage=frame
    if operation=='SHOW_LOCAL_VAR':
        path,radix=request
        names=[(path,None)]
        values=True
    else:
        values,=request
        radix=None
        names=sorted(declarations.items())

    def resolve(path):
        rt=runtime();base=re.match(IDENTIFIER,path)
        if base is None or base[0] not in declarations:
            raise rt.KarelRuntimeError('Local variable is absent from the selected frame',line)
        key=base[0];value=storage[key]
        reference=value if isinstance(value,rt.Reference) else rt.Reference(declarations[key],storage,key)
        return owner.execution.descend(reference,path[base.end():],line,path_nodes=True)

    return _kcl_value_rows(state,owner.program_name,names,values,radix,resolve,line,
                           routine=routine,task=selector or root.program_name)


def kcl_type_listing(state,selector,fields,line=None):
    from .archives import encode_json
    from .fileops import write_file_text

    rt=runtime();context=state.execution
    name=selector or state.program_name
    owner=state if name==state.program_name else context.variables.programs.get(name)
    if owner is None and name in context.tasks.tasks:owner=_kcl_task_root(state,name,line)
    program=getattr(owner,'program',None)
    if program is None:return 1
    remaining=1024*1024
    rows=[]
    if len(program.variable_types)>32767:return 5
    for name,spec in sorted(program.variable_types.items()):
        row=dict(program=owner.program_name,name=name,kind=spec[0],
                 owner=program.type_owners.get(name,owner.program_name),**_type_metadata(spec))
        leaf=rt.array_leaf_spec(spec) if spec[0]=='ARRAY' else spec
        if fields and leaf[0] in rt.RECORD_TYPES:
            row['fields']=[dict(name=member,**_type_metadata(member_spec))
                           for member,member_spec in rt.record_fields(leaf)]
        try:data=encode_json(row,remaining)
        except (ValueError,TypeError,RecursionError):return 5
        remaining-=len(data)
        rows.append(data)
    for data in rows:write_file_text(state,data.decode('ascii'),line)
    return 0


def kcl_task_history(state,selector,line=None):
    from .fileops import write_json_lines

    root=_kcl_task_root(state,selector,line)
    if root is None:return 3
    rows=[dict(depth=0,program=root.program_name,routine='')]
    rows.extend(dict(depth=index,program=owner.program_name,routine=routine)
                for index,(owner,routine) in enumerate(root._task_frames,1))
    rows[-1]['line']=root._task_line
    write_json_lines(state,rows,line)
    return 0


def program_rows(context,state):
    owners=list(context.variables.programs.values())+[state]
    owners.extend(program._state for program in context.tasks.tasks.values())
    rows={(owner.program_name,'PC') for owner in owners}
    if context.programs is not None: rows.update(context.programs.entries)
    if context.teach_programs is not None: rows.update(context.teach_programs.entries)
    return rows


def kcl_program_entries(context,state):
    from .dynamic import IDENTIFIER

    entries=program_rows(context,state)
    entries.update((owner,'VR') for owner,_ in context.variables.bindings if re.fullmatch(IDENTIFIER,owner))
    return entries


def kcl_program_listing(state,operation,args,line=None):
    from .fileops import write_json_lines
    from .scheduling import task_status_name

    context=state.execution
    if operation in ('SHOW_PROGRAMS','SHOW_PROGRAM'):
        entries=kcl_program_entries(context,state)
        target=None
        if operation=='SHOW_PROGRAM':
            selector=args[0]
            entries={row for row in entries if row[0]==selector}
            program=context.tasks.tasks.get(selector)
            if program is not None:
                target=runtime().task_root(program._state)
                entries.add((selector,'PC'))
            elif selector==state.program_name:
                target=runtime().task_root(state)
            if not entries:return 1
        if len(entries)>32767:return 5
        rows=[dict(name=name,type=kind) for name,kind in sorted(entries)]
        if target is not None:
            for row in rows:
                if row['type']=='PC':
                    active=target._task_frames[-1] if target._task_frames else (target,'')
                    row.update(program=active[0].program_name,routine=active[1],
                               status=task_status_name(target),line=target._task_line)
    else:
        tasks=context.tasks.tasks
        selector=args[0]
        if selector is not None:
            if selector not in tasks:return 1
            names=[selector]
        else:
            if len(tasks)>32767:return 5
            names=sorted(tasks)
        root=runtime().task_root
        rows=[dict(name=name,status=task_status_name(root(tasks[name]._state))) for name in names]
    # Capture rows before the first output callback or execution checkpoint.
    write_json_lines(state,rows,line)
    return 0


def program_list(context,state,args,line=None):
    rt=runtime(); pattern,kind,skip,form,names,count,status=args[:7]
    cursor=args[7] if len(args)==8 else None
    pattern=rt.ascii_string(pattern,line).upper()
    kind,skip,form=(rt.integer(value,line) for value in (kind,skip,form))
    offset=rt.integer(cursor.raw(),line) if cursor is not None else 0
    if (kind not in PROGRAM_TYPES or skip<0 or offset<0 or form not in (1,2)
            or not pattern or any(symbol in pattern for symbol in '[]?')
            or (skip and (pattern!='*' or kind!=7))):
        status.set(2,line);return
    rows=sorted(row for row in program_rows(context,state)
                if row[1] in PROGRAM_TYPES[kind] and fnmatch.fnmatchcase(row[0],pattern))
    capacity=rt.array_dimensions(names.spec)[0]
    selected=rows[skip+offset:skip+offset+capacity];text=[]
    for name,program_type in selected:
        if form==2 and len(name)>36: status.set(3,line);return
        width=12 if len(name)<=12 else 36
        text.append(name if form==1 else f'{name:<{width}} {program_type}')
    if any(len(value)>names.spec[2][1] for value in text): status.set(3,line);return
    array=rt.Array(names.spec)
    for index in range(1,capacity+1): array.set(index,text[index-1] if index<=len(text) else '',line)
    outputs=(names,count,status);values=(array,len(selected),0)
    if cursor is not None: outputs+=cursor,;values+=offset+len(selected),
    assign(outputs,values,line)
