"""Bounded, explicit variable creation, naming and routine aliases."""
import re
from .extended import runtime, fail, outputs_checked, FUNCTIONS


NAMES={'CREATE_VAR','RENAME_VAR','RENAME_VARS'}
IDENTIFIER=r'[A-Z_][A-Z_0-9]{0,35}'
MAX_LEAVES=32767


def file_storage_cost(spec):
    """Validate bounded ARRAY containers; identify FILE allocation intent only."""
    rt=runtime();count=1;rank=0;depth=0;current=spec
    while True:
        if type(current) is not tuple or not current:
            raise ValueError('Created storage requires a concrete type')
        if current[0]!='ARRAY':return count if current==('FILE',) else None
        if len(current) not in (3,4):raise ValueError('Invalid created ARRAY schema')
        try:identity=rt.array_identity(current)
        except rt.KarelRuntimeError as exc:raise ValueError('Invalid created ARRAY identity') from exc
        if depth and identity is None:raise ValueError('Nested created ARRAY components require names')
        shape=rt.array_shape(current);rank+=len(shape);depth+=1
        if not shape or rank>3:raise ValueError('Created ARRAYs require one through three logical dimensions')
        for size in shape:
            if type(size) is not int or not 1<=size<=MAX_LEAVES:
                raise ValueError('Created ARRAY dimensions require INTEGER in 1..32767')
            count*=size
            if count>MAX_LEAVES:raise ValueError('Created ARRAY exceeds 32767 cells')
        current=current[2]


def file_storage_payload(spec,value):
    """Preflight every created descriptor before encoding allocation intent."""
    rt=runtime()
    if file_storage_cost(spec) is None:raise ValueError('Created FILE storage requires FILE descriptors')
    pending=[(spec,value)]
    while pending:
        schema,current=pending.pop()
        if schema==('FILE',):file_descriptor_payload(current);continue
        shape=rt.array_shape(schema);size=1
        for dimension in shape:size*=dimension
        if (type(current) is not rt.Array or current.spec!=schema or current.shape!=shape
                or type(current.values) is not list or len(current.values)!=size):
            raise ValueError('Created FILE ARRAY storage does not match its schema')
        pending.extend((schema[2],item) for item in current.values)
    return {'closed':True}


def restore_file_storage(spec,payload):
    """Restore fresh closed storage after schema, quota and marker validation."""
    rt=runtime()
    if file_storage_cost(spec) is None:raise ValueError('Created FILE storage requires FILE descriptors')
    if spec==('FILE',):return restore_file_descriptor(payload)
    _closed_file_payload(payload)
    with rt._numeric_scope('pythonic'):return rt.initial_value(spec)


def creation_cost(spec):
    """Validate a creation schema and count its immediately reserved storage."""
    rt=runtime()
    from .storage import collection_data_spec,collection_array_cost
    if type(spec) is not tuple or not spec: raise ValueError('Creation requires a concrete type')
    descriptors=file_storage_cost(spec)
    if descriptors is not None:return descriptors
    collections=collection_array_cost(spec)
    if collections is not None:return collections
    if spec==('QUEUE_TYPE',): return 1
    if spec[0]=='PATH':
        if len(spec)!=3: raise ValueError('Created PATH requires node and header schemas')
        header=0
        for index,component in enumerate(spec[1:],1):
            if component is None: continue
            if type(component) is not tuple or not component or component[0]!='STRUCTURE':
                raise ValueError('Created PATH components require named data STRUCTURE layouts')
            try: count=rt._validate_data_schema(component)
            except rt.KarelRuntimeError as exc: raise ValueError('Invalid created PATH data: '+str(exc)) from exc
            collection_data_spec(component)
            if index==2: header=count
        # Nodes allocate through the existing PATH operations, not CREATE_VAR.
        return 1+header
    try:count=rt._validate_data_schema(spec)
    except rt.KarelRuntimeError as exc:raise ValueError('Invalid created data schema: '+str(exc)) from exc
    collection_data_spec(spec)
    return count


def file_descriptor_payload(value):
    """Persist allocation intent only, never an open FILE or pending operation."""
    rt=runtime()
    if type(value) is not rt.FileHandle:
        raise ValueError('Created FILE descriptor requires exact FILE storage')
    if value.owner is not None or value._read_operation is not None or value._write_operation is not None:
        raise ValueError('Created FILE descriptor must be closed without pending I/O')
    return {'closed':True}


def _closed_file_payload(payload):
    if type(payload) is not dict or set(payload)!={'closed'} or payload['closed'] is not True:
        raise ValueError('Created FILE descriptor requires exactly closed: true')


def restore_file_descriptor(payload):
    """Create a fresh closed FILE, without restoring cursor or connection data."""
    _closed_file_payload(payload)
    return runtime().FileHandle()


def reserved(store):
    # Shared immutable schemas need validation once per accounting pass. Never
    # keep this cache across a callback/checkpoint or a later restore row.
    costs={};total=0
    for key in store.metadata:
        spec=store.bindings[key].spec;identity=id(spec)
        if identity not in costs: costs[identity]=creation_cost(spec)
        total+=costs[identity]
        if total>MAX_LEAVES: return MAX_LEAVES+1
    return total


def restore_metadata(store,program,path,metadata,spec):
    """Validate saved creation policy and aggregate allocation before decoding."""
    if (type(program) is not str or type(path) is not str
            or not re.fullmatch(IDENTIFIER,program) or not re.fullmatch(IDENTIFIER,path)
            or type(metadata) is not dict or set(metadata)!={'group','memory_pool'}
            or type(metadata['group']) is not int or not 0<=metadata['group']<=32
            or type(metadata['memory_pool']) is not int or metadata['memory_pool'] not in (-1,0)):
        raise ValueError('Invalid dynamic variable creation metadata')
    cost=creation_cost(spec)
    leaf=runtime().array_leaf_spec(spec) if spec[0]=='ARRAY' else spec
    if leaf[0] in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS') and metadata['group']==0:
        raise ValueError('Positional dynamic variables require a group in 1..32')
    if reserved(store)+cost>MAX_LEAVES:
        raise ValueError('Dynamic variables exceed 32767 reserved creation units')
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
    """Portable data and Pythonic root resources; validate before allocation."""
    rt=runtime()
    text=rt.ascii_string(text,line).strip().upper()
    if (type(dimensions) not in (tuple,list) or len(dimensions)!=3
            or any(type(size) is not int or not 0<=size<=32767 for size in dimensions)):
        return None
    if rt._pythonic():
        array=re.fullmatch(r'ARRAY +OF +(.+)',text)
        if array:
            if not dimensions[0]:return None
            text=array[1]
            if text.startswith('ARRAY '):return None
    if text in ('INTEGER','REAL','BOOLEAN','CONFIG','VECTOR','POSITION','XYZWPR','XYZWPREXT',*rt.ASSOCIATION_TYPES):
        spec=(text,)
    elif text in ('FILE','PATH','QUEUE_TYPE') and rt._pythonic():
        spec=('PATH',None,None) if text=='PATH' else (text,)
    elif text in ('BYTE','SHORT') and rt._pythonic():
        # Standalone narrow types are an explicit Pythonic extension, using the
        # same checked domains and initial markers as aggregate narrow leaves.
        spec=(text,)
    elif text in rt.PREDEFINED_STRUCTURES:
        spec=rt.PREDEFINED_STRUCTURES[text]
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
    if spec[0] in ('FILE','PATH','QUEUE_TYPE') and not rt._pythonic(): return None
    if shape:
        if spec[0]=='ARRAY' and (not rt._pythonic() or rt.array_identity(spec) is None):return None
        spec=('ARRAY',shape[0] if len(shape)==1 else shape,spec)
    if spec[0] in ('BYTE','SHORT') and not rt._pythonic(): return None
    if type(group) is not int or not 0<=group<=32: return None
    leaf=rt.array_leaf_spec(spec) if spec[0]=='ARRAY' else spec
    if leaf[0] in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS') and group==0: return None
    try:
        creation_cost(spec)
        if not rt._pythonic() and rt.file_storage_type(spec):return None
    except (ValueError,TypeError): return None
    return spec


def variable_checkpoint(state,line):
    rt=runtime()
    state.tick(line)
    for owner in (rt.task_root(state),state):
        if owner._aborted: raise rt.KarelAbort(owner._abort_line)
        if owner.task_state=='stopped': raise rt.KarelStop('Task is stopped')


def create(context,state,args,line):
    rt=runtime();store=context.variables
    program,var,type_program,text,group,inner,middle,outer,pool=args
    program=name(program,state,line,default=True);var=name(var,state,line)
    type_program=name(type_program,state,line,default=True)
    if program is None or var is None or type_program is None:return 2
    if conflict(roots(store,program)|set(declared(context,state,program)),var):return 3
    if type(pool) is not int or pool not in (-1,0):return 2
    spec=concrete_type(context,state,type_program,text,group,(inner,middle,outer),line)
    if spec is None:return 5
    cost=creation_cost(spec)
    if reserved(store)+cost>MAX_LEAVES:return 6
    # Budget checkpoint precedes the only allocation and mutation.
    variable_checkpoint(state,line)
    if context.variables is not store: fail('Variable store changed during CREATE_VAR',line)
    if conflict(roots(store,program)|set(declared(context,state,program)),var):return 3
    if reserved(store)+cost>MAX_LEAVES:return 6
    reference=rt.Reference(spec,{'value':rt.initial_value(spec)},'value')
    key=(program,var);store.bindings[key]=reference
    store.metadata[key]={'group':group,'memory_pool':pool}
    return 0


def rename(context,state,operation,args,line):
    store=context.variables
    if operation=='RENAME_VAR':
        program,old,new=args
        program=name(program,state,line,default=True);old=name(old,state,line);new=name(new,state,line)
        if None in (program,old,new):return 2
        if old in declared(context,state,program):return 4
        key=(program,old)
        if key not in store.bindings:return 1
        if old==new:return 0
        if conflict(roots(store,program)|set(declared(context,state,program)),new):return 3
        changes={key:(program,new)}
        for owner,path in store.bindings:
            if owner==program and (path.startswith(old+'.') or path.startswith(old+'[')):
                changes[owner,path]=(program,new+path[len(old):])
        def cache_key(owner,path):
            if owner==program and (path==old or path.startswith(old+'.') or path.startswith(old+'[')):
                return owner,new+path[len(old):]
            return owner,path
    else:
        old,new=args;old=name(old,state,line,default=True);new=name(new,state,line)
        if old is None or new is None:return 2
        # Compiled program identities and their live references cannot be renamed.
        if old in store.programs or old==state.program_name:return 4
        if not roots(store,old):return 1
        if any(not re.fullmatch(IDENTIFIER,path) for path in roots(store,old)):return 4
        if old==new:return 0
        if new in store.programs or new==state.program_name or roots(store,new):return 3
        changes={key:(new,key[1]) for key in store.bindings if key[0]==old}
        def cache_key(owner,path): return (new if owner==old else owner),path
    bindings_before,programs_before=store.bindings.copy(),store.programs.copy()
    variable_checkpoint(state,line)
    if context.variables is not store or store.bindings!=bindings_before or store.programs!=programs_before:
        fail('Variable bindings changed during rename',line)
    bindings={changes.get(key,key):value for key,value in store.bindings.items()}
    metadata={changes.get(key,key):value for key,value in store.metadata.items()}
    entries={cache_key(owner,path):value for (owner,path),value in context.entries.items()}
    store.bindings=bindings;store.metadata=metadata;context.entries=entries
    return 0


def invoke(context,state,operation,args,line):
    if operation=='CREATE_VAR':
        code=create(context,state,(*args[:-2],args[-1]),line)
        args[-2].set(code,line)
    else:
        args[-1].set(rename(context,state,operation,args[:-1],line),line)


def detached_storage(state,targets):
    """Check that explicit roots are independent of the context's other live cells."""
    from .inspection import attached_programs
    from .variable_archives import cells, ordinary

    if not targets:return 0
    rt=runtime();context=state.execution;store=context.variables
    owners=attached_programs(context,state)
    selected=set();paths={}
    try:
        for (program,var),reference in targets.items():
            if any(var in owner.types for owner in owners.get(program,())):return 4
            record=context.program_attributes.record(program) if context.program_attributes is not None else None
            if record is not None and (record.get('active',False) or record['attributes'].get('AT_PROTECT',1)==2):
                return 4
            if not ordinary(reference):return 5
            occupied=cells(reference)
            if selected&occupied:return 4
            selected.update(occupied);paths.setdefault(program,set()).add(var)
        for key,other in store.bindings.items():
            if key in targets:continue
            program,path=key
            if (any(conflict((path,),var) for var in paths.get(program,()))
                    or not ordinary(other) or selected&cells(other)):
                return 4
        for claim in context._timer_claims.values():
            if type(claim) is not tuple or len(claim)!=4 or (id(claim[2]),claim[3]) in selected:return 4
        for instances in owners.values():
            for owner in instances:
                for declarations,values in ((owner.types,owner.values),*owner.local_frames):
                    for member,spec in declarations.items():
                        stored=values[member]
                        other=stored if type(stored) is rt.Reference else rt.Reference(spec,values,member)
                        if selected&cells(other):return 4
    except (ValueError,TypeError,KeyError,rt.KarelRuntimeError):return 5
    return 0


def remove_detached(state,program,var,line):
    """Remove an independent root or a complete unattached ordinary namespace."""
    from .inspection import attached_programs

    rt=runtime();context=state.execution
    program=name(program,state,line,default=True)
    if program is None:return 2
    if var is not None:
        var=name(var,state,line)
        if var is None:return 2
    variable_checkpoint(state,line)
    store=context.variables
    owners=attached_programs(context,state).get(program,())
    if var is None:
        if owners:return 4
        targets={key:reference for key,reference in store.bindings.items() if key[0]==program}
        if any(not re.fullmatch(IDENTIFIER,path) for _,path in targets):return 4
    else:
        if any(var in owner.types for owner in owners):return 4
        key=(program,var);reference=store.bindings.get(key)
        targets={} if reference is None else {key:reference}
    if not targets:return 1
    code=detached_storage(state,targets)
    if code:return code
    for reference in targets.values():
        if rt.file_storage_type(reference.spec):
            try:file_storage_payload(reference.spec,reference.raw())
            except (ValueError,TypeError,rt.KarelRuntimeError):return 4
    for key in targets:
        del store.bindings[key];store.metadata.pop(key,None)
    for key in tuple(context.entries):
        if key[0]==program and (var is None or conflict((key[1],),var)):
            del context.entries[key]
    return 0


def set_detached_scalar(state,program,path,literal,line):
    """Assign a checked literal to a scalar cell under a detached explicit root."""
    from .inspection import attached_programs

    rt=runtime();context=state.execution
    program=name(program,state,line,default=True)
    if program is None:return 2
    selector=re.match(IDENTIFIER,path)
    if selector is None:return 2
    var=selector[0]
    variable_checkpoint(state,line)
    if any(var in owner.types for owner in attached_programs(context,state).get(program,())):return 4
    key=(program,var);reference=context.variables.bindings.get(key)
    if reference is None:return 1
    code=detached_storage(state,{key:reference})
    if code:return code
    try:
        target=context.descend(reference,path[len(var):],line,path_nodes=True)
        if type(target) is not rt.Reference:return 4
        kind=target.spec[0]
        if kind in ('INTEGER','BYTE','SHORT') and re.fullmatch(r'[+-]?[0-9]+',literal):
            value=int(literal)
        elif kind=='REAL' and re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?',literal):
            value=float(literal)
        elif kind=='BOOLEAN' and literal.upper() in ('TRUE','FALSE'):
            value=literal.upper()=='TRUE'
        elif kind=='STRING' and len(literal)>=2 and literal[0] in ('"',"'"):
            quote=literal[0]
            if not re.fullmatch(re.escape(quote)+r'(?:[^'+re.escape(quote)+r']|'+re.escape(quote)*2+r')*'+re.escape(quote),literal):
                return 5
            value=literal[1:-1].replace(quote*2,quote)
            if len(value)>target.spec[1]:return 5
        else:return 5
        target.set(value,line)
    except (ValueError,TypeError,rt.KarelRuntimeError):return 5
    return 0


def edit_detached_path(state,operation,program,var,index,line):
    """Edit an explicit PATH without invalidating a compiled or retained alias."""
    from .inspection import attached_programs
    from .storage import collection_payload
    from .variable_archives import ordinary

    rt=runtime();context=state.execution
    program=name(program,state,line,default=True)
    var=name(var,state,line)
    if program is None or var is None:return 2
    variable_checkpoint(state,line)
    store=context.variables;key=(program,var)
    owners=attached_programs(context,state)
    if any(var in owner.types for owner in owners.get(program,())):return 4
    reference=store.bindings.get(key)
    if reference is None:return 1
    if not ordinary(reference) or reference.spec[0]!='PATH':return 5
    value=reference.raw()
    if type(value) is not rt.PathValue or value.spec!=reference.spec or type(value.nodes) is not list:
        return 5
    try:
        node_size=rt._validate_data_schema(value.node_spec)
        header_size=rt._validate_data_schema(value.spec[2]) if value.spec[2] is not None else 0
        count=len(value.nodes)
        if count>MAX_LEAVES or header_size+count*node_size>MAX_LEAVES:return 6
        if operation!='APPEND_NODE' and not 1<=index<=count:return 2
        if operation!='DELETE_NODE' and (count>=MAX_LEAVES or header_size+(count+1)*node_size>MAX_LEAVES):
            return 6
        collection_payload(reference.spec,value)
    except (ValueError,TypeError,rt.KarelRuntimeError):return 5
    code=detached_storage(state,{key:reference})
    if code:return code
    if operation=='DELETE_NODE':
        del value.nodes[index-1]
        return 0
    return value.append(index,line)


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
        context=state.execution;target=context.resolve(state,program,path,line,prefixes=True,resources=True)
        if type(target) is rt._ArrayPrefixTarget:target=rt.array_prefix_reference(target,line)
        if type(target) is not rt.Reference: fail('BYNAME requires ordinary writable storage',line)
        if not rt.parameter_accepts(expected,target.spec): fail('BYNAME variable type does not match the routine parameter',line)
        if rt._reference_cells(target,queue_buffers=True)&rt._reference_cells(entry): fail('BYNAME variable overlaps entry output',line)
        key=(program,path)
        if key not in context.entries: context.entries[key]=max(context.entries.values(),default=0)+1
        entry.set(context.entries[key],line)
    except Exception:
        row['outcome']='failed';raise
    row['outcome']='completed';return target
