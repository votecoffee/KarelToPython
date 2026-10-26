"""Bounded, explicit variable creation, naming and routine aliases."""
import re
from .extended import runtime, fail, outputs_checked, FUNCTIONS


NAMES={'CREATE_VAR','RENAME_VAR','RENAME_VARS'}
IDENTIFIER=r'[A-Z_][A-Z_0-9]{0,35}'
MAX_LEAVES=32767


def restore_metadata(store,program,path,metadata,spec):
    """Validate saved creation policy and aggregate allocation before decoding."""
    from .storage import collection_data_spec
    if (type(program) is not str or type(path) is not str
            or not re.fullmatch(IDENTIFIER,program) or not re.fullmatch(IDENTIFIER,path)
            or type(metadata) is not dict or set(metadata)!={'group','memory_pool'}
            or type(metadata['group']) is not int or not 0<=metadata['group']<=32
            or type(metadata['memory_pool']) is not int or metadata['memory_pool'] not in (-1,0)):
        raise ValueError('Invalid dynamic variable creation metadata')
    collection_data_spec(spec)
    leaf=runtime().array_leaf_spec(spec) if spec[0]=='ARRAY' else spec
    if leaf[0] in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS') and metadata['group']==0:
        raise ValueError('Positional dynamic variables require a group in 1..32')
    used=sum(runtime().scalar_leaf_count(store.bindings[key].spec) for key in store.metadata)
    if used+runtime().scalar_leaf_count(spec)>MAX_LEAVES:
        raise ValueError('Dynamic variables exceed 32767 scalar leaves')
    store.metadata[program,path]=metadata.copy()


def name(value,state,line,*,default=False):
    value=runtime().ascii_string(value,line).strip().upper()
    if not value and default: value=state.program_name
    return value if re.fullmatch(IDENTIFIER,value) else None


def roots(store,program):
    return {path for owner,path in store.bindings if owner==program}


def declared(context,state,program):
    owner=state if program==state.program_name else context.variables.programs.get(program)
    return owner.types if owner is not None else {}


def conflict(paths,root):
    return any(path==root or path.startswith(root+'.') or path.startswith(root+'[') for path in paths)


def concrete_type(context,state,program,text,group,dimensions,line):
    """Only portable data types; validate before constructing any storage."""
    rt=runtime()
    from .storage import collection_data_spec
    text=rt.ascii_string(text,line).strip().upper()
    if text in ('INTEGER','REAL','BOOLEAN','CONFIG','VECTOR','POSITION','XYZWPR','XYZWPREXT'):
        spec=(text,)
    elif re.fullmatch(r'STRING(?:\[[0-9]{1,3}\])?',text):
        spec=('STRING',12 if text=='STRING' else int(text[7:-1]))
    elif re.fullmatch(r'JOINTPOS[1-9]?',text):
        spec=('JOINTPOS',9 if text=='JOINTPOS' else int(text[-1]))
    elif text in ('ARRAY OF BYTE','ARRAY OF SHORT'):
        if not dimensions[0]: return None
        spec=(text.split()[-1],)
    else:
        owner=state if program==state.program_name else context.variables.programs.get(program)
        spec=getattr(getattr(owner,'program',None),'variable_types',{}).get(text)
        if spec is None: return None
    # Zero means unused; dimensions must be contiguous from the inner dimension.
    if any(type(size) is not int or not 0<=size<=32767 for size in dimensions): return None
    if (dimensions[1] and not dimensions[0]) or (dimensions[2] and not dimensions[1]): return None
    shape=tuple(size for size in reversed(dimensions) if size)
    if shape:
        if spec[0]=='ARRAY': return None
        spec=('ARRAY',shape[0] if len(shape)==1 else shape,spec)
    if type(group) is not int or not 0<=group<=32: return None
    leaf=rt.array_leaf_spec(spec) if spec[0]=='ARRAY' else spec
    if leaf[0] in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS') and group==0: return None
    try: collection_data_spec(spec)
    except (ValueError,TypeError): return None
    return spec


def create(context,state,args,line):
    rt=runtime();store=context.variables
    program,var,type_program,text,group,inner,middle,outer,status,pool=args
    program=name(program,state,line,default=True);var=name(var,state,line)
    type_program=name(type_program,state,line,default=True)
    if program is None or var is None or type_program is None: status.set(2,line);return
    if conflict(roots(store,program)|set(declared(context,state,program)),var): status.set(3,line);return
    if type(pool) is not int or pool not in (-1,0): status.set(2,line);return
    spec=concrete_type(context,state,type_program,text,group,(inner,middle,outer),line)
    if spec is None: status.set(5,line);return
    used=sum(rt.scalar_leaf_count(store.bindings[key].spec) for key in store.metadata)
    if used+rt.scalar_leaf_count(spec)>MAX_LEAVES: status.set(6,line);return
    # Budget checkpoint precedes the only allocation and mutation.
    state.tick(line)
    reference=rt.Reference(spec,{'value':rt.initial_value(spec)},'value')
    key=(program,var);store.bindings[key]=reference
    store.metadata[key]={'group':group,'memory_pool':pool}
    status.set(0,line)


def rename(context,state,operation,args,line):
    store=context.variables
    if operation=='RENAME_VAR':
        program,old,new,status=args
        program=name(program,state,line,default=True);old=name(old,state,line);new=name(new,state,line)
        if None in (program,old,new): status.set(2,line);return
        if old in declared(context,state,program): status.set(4,line);return
        key=(program,old)
        if key not in store.bindings: status.set(1,line);return
        if old==new: status.set(0,line);return
        if conflict(roots(store,program)|set(declared(context,state,program)),new): status.set(3,line);return
        changes={key:(program,new)}
        for owner,path in store.bindings:
            if owner==program and (path.startswith(old+'.') or path.startswith(old+'[')):
                changes[owner,path]=(program,new+path[len(old):])
        def cache_key(owner,path):
            if owner==program and (path==old or path.startswith(old+'.') or path.startswith(old+'[')):
                return owner,new+path[len(old):]
            return owner,path
    else:
        old,new,status=args;old=name(old,state,line,default=True);new=name(new,state,line)
        if old is None or new is None: status.set(2,line);return
        # Compiled program identities and their live references cannot be renamed.
        if old in store.programs or old==state.program_name: status.set(4,line);return
        if not roots(store,old): status.set(1,line);return
        if any(not re.fullmatch(IDENTIFIER,path) for path in roots(store,old)): status.set(4,line);return
        if old==new: status.set(0,line);return
        if new in store.programs or new==state.program_name or roots(store,new): status.set(3,line);return
        changes={key:(new,key[1]) for key in store.bindings if key[0]==old}
        def cache_key(owner,path): return (new if owner==old else owner),path
    bindings={changes.get(key,key):value for key,value in store.bindings.items()}
    metadata={changes.get(key,key):value for key,value in store.metadata.items()}
    entries={cache_key(owner,path):value for (owner,path),value in context.entries.items()}
    state.tick(line)
    store.bindings=bindings;store.metadata=metadata;context.entries=entries
    status.set(0,line)


def invoke(context,state,operation,args,line):
    return create(context,state,args,line) if operation=='CREATE_VAR' else rename(context,state,operation,args,line)


def byname(state,expected,program,path,entry,line=None):
    """Resolve an ordinary exact formal-compatible reference, without copying."""
    rt=runtime()
    if not rt._pythonic(): fail('BYNAME requires Pythonic mode',line)
    row={'operation':'BYNAME','line':line,'outcome':'requested'};state.service_requests.append(row)
    try:
        outputs_checked(FUNCTIONS['BYNAME'][0],(program,path,entry),line)
        program=rt.ascii_string(program,line).strip().upper() or rt.task_root(state).program_name
        path=rt.ascii_string(path,line).upper()
        if not re.fullmatch(IDENTIFIER+r'(?:\.[A-Z_][A-Z_0-9]*|\[[0-9]+(?:,[0-9]+)*\])*',path):
            fail('BYNAME requires an ordinary static variable path; system variables are excluded',line)
        context=state.execution;target=context.resolve(state,program,path,line)
        if type(target) is not rt.Reference: fail('BYNAME requires ordinary writable storage',line)
        if not rt.parameter_accepts(expected,target.spec): fail('BYNAME variable type does not match the routine parameter',line)
        if rt._reference_cells(target)&rt._reference_cells(entry): fail('BYNAME variable overlaps entry output',line)
        key=(program,path)
        if key not in context.entries: context.entries[key]=max(context.entries.values(),default=0)+1
        entry.set(context.entries[key],line)
    except Exception:
        row['outcome']='failed';raise
    row['outcome']='completed';return target
