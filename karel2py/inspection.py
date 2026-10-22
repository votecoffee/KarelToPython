"""Read-only metadata and bounded name queries over explicit program storage."""
import fnmatch
import math
import re


TYPE_CODES={'POSITION':1,'XYZWPR':2,'XYZWPREXT':6,'INTEGER':16,'REAL':17,
            'BOOLEAN':18,'VECTOR':19,'SHORT':23,'BYTE':24,'CONFIG':28,
            'FILE':29,'PATH':31,'STRING':209,'STRUCTURE':210,
            **{f'JOINTPOS{width}':25+16*(width-1) for width in range(1,10)}}


def runtime():
    from . import runtime as rt
    return rt


def describe(spec):
    rt=runtime(); shape=rt.array_dimensions(spec) if spec[0]=='ARRAY' else ()
    leaf=rt.array_leaf_spec(spec) if shape else spec
    name=leaf[1] if leaf[0]=='STRUCTURE' else f'JOINTPOS{rt.joint_width(leaf)}' if leaf[0]=='JOINTPOS' else leaf[0]
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
