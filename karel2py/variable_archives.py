"""Portable owned-global snapshots and explicit offline DRAM save points."""
from copy import deepcopy
from functools import wraps
import re


FORMAT='karel2py-variables-v1'
IDENTIFIER=r'[A-Z_][A-Z_0-9]{0,35}'
MAX_LEAVES=32767


def rt():
    from . import runtime
    return runtime


def pythonic(function):
    @wraps(function)
    def call(*args,**kwargs):
        with rt()._numeric_scope('pythonic'):return function(*args,**kwargs)
    return call


class Failure(ValueError):
    def __init__(self,code,message):self.code=code;super().__init__(message)


def name(value):
    if type(value) is not str or not re.fullmatch(IDENTIFIER,value.upper()):raise Failure(2,'Invalid variable program/name')
    return value.upper()


def graph_value(value,limit):
    if value is None:return {}
    if type(value) is not dict or len(value)>limit:raise ValueError('Variable calls require a bounded mapping')
    result={};edges=0
    for key,targets in value.items():
        key=name(key)
        if key in result or type(targets) not in (list,tuple) or len(targets)>limit:raise ValueError('Invalid or duplicate variable call list')
        targets=[name(target) for target in targets];edges+=len(targets)
        if len(set(targets))!=len(targets) or edges>32767:raise ValueError('Duplicate targets or excessive variable call graph')
        result[key]=targets
    return result


def ordinary(reference):
    runtime=rt()
    if type(reference) is not runtime.Reference or type(reference.storage) not in (dict,list):return False
    if type(reference.storage) is dict:return type(reference.key) in (str,int) and reference.key in reference.storage
    return type(reference.key) is int and 0<=reference.key<len(reference.storage)


def cells(reference):
    result=rt()._reference_cells(reference);value=reference.raw()
    if isinstance(value,(rt().Array,rt().Structure,rt().JointPosition,rt().QueueValue)):result.add((id(value),'aggregate'))
    return result


def owner_of(context,state,program):return state if program==state.program_name else context.variables.programs.get(program)


def roots(context,state,program):
    runtime=rt();store=context.variables;owner=owner_of(context,state,program);result={};excluded=[]
    imported={row[0] for row in getattr(getattr(owner,'program',None),'imported_variables',())}
    if owner is not None:
        for key,spec in owner.types.items():
            if key in imported or spec[0] in ('FILE','PATH'):excluded.append(key);continue
            value=owner.values[key]
            result[key]=value if type(value) is runtime.Reference else runtime.Reference(spec,owner.values,key)
    for (scope,path),reference in store.bindings.items():
        if scope!=program or path.startswith('$'):continue
        if not re.fullmatch(IDENTIFIER,path):
            root=re.match(IDENTIFIER,path)
            if root is None or root[0] not in result:raise Failure(4,'Sparse variable bindings cannot be archived')
            try:selected=context.descend(result[root[0]],path[root.end():])
            except runtime.KarelRuntimeError as exc:raise Failure(4,'Sparse variable binding does not match its root') from exc
            if (not ordinary(reference) or not ordinary(selected) or reference.spec!=selected.spec
                    or reference.storage is not selected.storage or reference.key!=selected.key):
                raise Failure(4,'Sparse variable binding is independent of its root')
            continue
        if owner is not None and path in owner.types:continue
        if reference.spec[0] in ('FILE','PATH'):excluded.append(path);continue
        result[path]=reference
    if owner is None and not result and not excluded:raise Failure(1,'Variable namespace is absent')
    occupied=set()
    for reference in result.values():
        if not ordinary(reference):raise Failure(4,'Archive requires ordinary root storage')
        selected=cells(reference)
        if occupied&selected:raise Failure(4,'Variable roots overlap')
        occupied.update(selected)
    return result,sorted(set(excluded))


def schema(spec):
    from .storage import collection_data_spec
    if spec==('QUEUE_TYPE',):return 1
    collection_data_spec(spec)
    leaves=rt().scalar_leaf_count(spec)
    if not 1<=leaves<=MAX_LEAVES:raise ValueError('Variable data requires 1..32767 leaves')
    return leaves


def capture(context,state,program,*,calls=(),limit=16*1024*1024):
    from .extended import variable_reference
    from .storage import typed_value
    from .archives import encode_json
    variables,excluded=roots(context,state,program);records={};leaves=0;remaining=limit
    for key,reference in sorted(variables.items()):
        leaves+=schema(reference.spec)
        if leaves>MAX_LEAVES:raise Failure(5,'Variable snapshot exceeds 32767 leaves')
        copied=variable_reference(reference).value;records[key]=typed_value(copied,reference.spec)
        metadata=context.variables.metadata.get((program,key))
        if metadata is not None:records[key]['creation']=metadata.copy()
        try:remaining-=len(encode_json(records[key],remaining))
        except (ValueError,RecursionError) as exc:raise Failure(5,'Variable snapshot exceeds byte budget') from exc
    return dict(format=FORMAT,program=program,variables=records,excluded=excluded,calls=list(calls))


def markers(payload):
    pending=[payload]
    while pending:
        item=pending.pop()
        if type(item) is dict:
            if set(item) in ({'uninitialized'},{'unknown_byte'}):
                if next(iter(item.values())) is not True:raise ValueError('Missing markers require exact true flags')
            else:pending.extend(item.values())
        elif type(item) is list:pending.extend(item)


def validate(row):
    """Check every schema/allocation before restoring any typed value."""
    from .storage import tuple_spec,decode_typed,typed_value
    from .dynamic import restore_metadata
    from .extended import VariableStore
    if type(row) is not dict or set(row)!={'format','program','variables','excluded','calls'} or row['format']!=FORMAT:
        raise ValueError('Unsupported variable archive format')
    program=name(row['program'])
    if program!=row['program']:raise ValueError('Variable archive program must be canonical')
    graph_value({program:row['calls']},4096)
    records=row['variables'];excluded=row['excluded']
    if type(records) is not dict or len(records)>MAX_LEAVES or type(excluded) is not list or len(excluded)>MAX_LEAVES:
        raise ValueError('Invalid variable archive root lists')
    if any(name(key)!=key for key in excluded) or len(set(excluded))!=len(excluded) or set(excluded)&set(records):
        raise ValueError('Invalid excluded variable roots')
    specs={};leaves=0
    for key,record in records.items():
        if name(key)!=key or type(record) is not dict or set(record)-{'type','value','creation'} or not {'type','value'}<=set(record):
            raise ValueError('Invalid variable archive row')
        markers(record['value'])
        spec=tuple_spec(record['type']);leaves+=schema(spec);specs[key]=spec
        if leaves>MAX_LEAVES:raise ValueError('Variable snapshot exceeds 32767 leaves')
    decoded={};metadata=VariableStore()
    for key,record in records.items():
        typed={field:record[field] for field in ('type','value')}
        spec,value=decode_typed(typed)
        if typed_value(value,spec)!=typed:raise ValueError('Variable archive requires canonical typed data')
        reference=rt().Reference(spec,{'value':value},'value');metadata.bind(program,key,reference)
        if 'creation' in record:restore_metadata(metadata,program,key,record['creation'],spec)
        decoded[key]=(spec,value,record.get('creation'))
    return program,decoded


def active(owner):
    root=rt().task_root(owner)
    return root._driving or root.task_state in ('running','paused','waiting') or bool(root._task_frames)


def prepare(context,state,bank,snapshots,status=None,*,clear=False):
    from .inspection import attached_programs,any_initialized
    from .extended import VariableStore,_variable_shape
    from .dynamic import restore_metadata
    runtime=rt();store=context.variables;owners=attached_programs(context,state);current=runtime.task_root(state)
    protected=set() if status is None else cells(status);updates=[];new=[];occupied=set();initializations={}
    graph=deepcopy(bank.calls)
    temporary=VariableStore();temporary.bindings=dict(store.bindings);temporary.metadata=deepcopy(store.metadata)
    for group in owners.values():
        for owner in group:
            for timer in owner._timers.values():protected.update(cells(timer[0]))
            if active(owner) and (runtime.task_root(owner) is not current or owner.program_name!=state.program_name):
                for key,spec in owner.types.items():
                    value=owner.values[key]
                    reference=value if type(value) is runtime.Reference else runtime.Reference(spec,owner.values,key)
                    protected.update(cells(reference))
    for snapshot in snapshots:
        program,records=validate(snapshot);existing,_=roots(context,state,program) if known(context,state,program) else ({},[])
        record=context.program_attributes.record(program) if context.program_attributes is not None else None
        if record is not None and (record['attributes'].get('AT_PROTECT',1)==2 or record.get('active',False)):
            raise Failure(4,'Variable program is protected or explicitly active')
        for owner in owners.get(program,[]):
            if active(owner) and (runtime.task_root(owner) is not current or owner.program_name!=state.program_name):
                raise Failure(4,'Variable program belongs to another active execution')
        future={key:(reference.spec,reference.raw()) for key,reference in existing.items()}
        owner=owner_of(context,state,program)
        if not clear:graph[program]=list(snapshot['calls'])
        for key,(spec,value,creation) in records.items():
            reference=existing.get(key)
            if reference is None:
                if owner is not None and key in owner.types:raise Failure(4,'Archive cannot replace imported or resource globals')
                if clear:raise Failure(4,'Clear requires existing variable roots')
                reference=runtime.Reference(spec,{'value':runtime.initial_value(spec)},'value');new.append((program,key,reference))
                temporary.bind(program,key,reference)
            if reference.spec!=spec:raise Failure(6,'Variable archive type differs from destination')
            _variable_shape(spec,reference.raw()) if spec!=('QUEUE_TYPE',) else None
            selected=cells(reference)
            if selected&(protected|occupied):raise Failure(4,'Variable archive overlaps protected/output storage')
            occupied.update(selected)
            if clear:value=runtime.initial_value(spec)
            elif value is runtime.UNINITIALIZED and spec[0] in (*runtime.RECORD_TYPES,'ARRAY','JOINTPOS'):
                value=runtime.initial_value(spec)
            previous=temporary.metadata.get((program,key))
            if creation is not None:
                if previous is not None and previous!=creation:raise Failure(6,'Variable creation policy differs from destination')
                if previous is None:
                    temporary.bindings.setdefault((program,key),reference)
                    restore_metadata(temporary,program,key,creation,spec)
            updates.append((reference,value));future[key]=(spec,value)
        if context.program_attributes is not None and context.program_attributes.record(program) is not None:
            initializations[program]=any(any_initialized(value,spec) for spec,value in future.values())
    if len({program for program,_ in temporary.bindings if re.fullmatch(IDENTIFIER,program)})>bank.program_limit:
        raise Failure(5,'Variable namespace count exceeded')
    try:graph=graph_value(graph,bank.program_limit)
    except ValueError as exc:raise Failure(5,str(exc)) from exc
    return updates,new,temporary.metadata,graph,initializations


def commit(context,bank,prepared):
    runtime=rt();updates,new,metadata,graph,initializations=prepared
    for reference,value in updates:
        current=reference.raw()
        if type(current) is runtime.QueueValue and type(value) is runtime.QueueValue:
            current.initialized=value.initialized;current.sequence=value.sequence;current.entries=list(value.entries);current.buffer=None
        else:reference.storage[reference.key]=runtime.replace_value(current,value)
    for program,key,reference in new:context.variables.bind(program,key,reference)
    context.variables.metadata=metadata;bank.calls=graph
    for program,initialized in initializations.items():
        context.program_attributes._records[program]['initialized']=initialized


def known(context,state,program):
    return program==state.program_name or program in context.variables.programs or any(scope==program and re.fullmatch(IDENTIFIER,key) for scope,key in context.variables.bindings)


class VariableArchives:
    """Bounded snapshots and explicit call graph; no native flash or power-up hook."""
    def __init__(self,*,limit=16*1024*1024,program_limit=256,calls=None):
        if type(limit) is not int or not 1<=limit<=64*1024*1024:raise ValueError('Variable archive limit requires 1..64 MiB')
        if type(program_limit) is not int or not 1<=program_limit<=4096:raise ValueError('Variable archive program limit requires 1..4096')
        self.limit=limit;self.program_limit=program_limit;self.calls=graph_value(calls,program_limit);self.flash={}

    @pythonic
    def decode(self,data):
        from .archives import decode_json
        row=decode_json(data,self.limit)
        try:validate(row)
        except Failure as exc:raise ValueError(str(exc)) from exc
        return row

    def encode(self,row):
        from .archives import encode_json,decode_json
        try:
            data=encode_json(row,self.limit);decode_json(data,self.limit);return data
        except RecursionError as exc:raise Failure(6,'Variable archive nesting is excessive') from exc
        except ValueError as exc:raise Failure(5,str(exc)) from exc

    @pythonic
    def save_dram(self,state,program):
        try:
            program=name(program);row=capture(state.execution,state,program,calls=self.calls.get(program,[]),limit=self.limit);validate(row);self.encode(row)
            prepared={**self.flash,program:row}
            if len(prepared)>self.program_limit or sum(len(self.encode(item)) for item in prepared.values())>self.limit:return 5
        except Failure as exc:return exc.code
        except (ValueError,TypeError,rt().KarelRuntimeError):return 6
        self.flash=prepared;return 0

    @pythonic
    def restore_dram(self,state,program):
        try:
            program=name(program)
            if program not in self.flash:return 1
            prepared=prepare(state.execution,state,self,[self.flash[program]])
        except Failure as exc:return exc.code
        except (ValueError,TypeError,rt().KarelRuntimeError):return 6
        commit(state.execution,self,prepared);return 0

    def to_config(self):return dict(limit=self.limit,program_limit=self.program_limit,calls=deepcopy(self.calls),flash=deepcopy(self.flash))

    @classmethod
    @pythonic
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'limit','program_limit','calls','flash'}:raise ValueError('Unknown variable archive fields')
        result=cls(limit=config.get('limit',16*1024*1024),program_limit=config.get('program_limit',256),calls=config.get('calls'))
        rows=config.get('flash',{});size=0
        if type(rows) is not dict or len(rows)>result.program_limit:raise ValueError('Invalid saved DRAM snapshot list')
        for program,row in rows.items():
            if name(program)!=program or type(row) is not dict or row.get('program')!=program:raise ValueError('Invalid saved DRAM program identity')
            size+=len(result.encode(row))
            if size>result.limit:raise ValueError('Saved DRAM snapshots exceed byte budget')
            result.decode(result.encode(row))
            if len(row['calls'])>result.program_limit:raise ValueError('Saved DRAM call list exceeds limit')
            result.flash[program]=deepcopy(row)
        return result


def variable_operation(operation,args):
    if operation=='SAVE_DRAM':return True
    if operation in ('PROG_BACKUP','PROG_CLEAR') and args[1] in (1,6):return True
    if operation in ('SAVE','LOAD','CLEAR','PROG_RESTORE'):
        return args[1 if operation=='SAVE' else 0].upper().endswith('.VR')
    return False


def walk(context,state,bank,root,*,missing=False):
    order=[];pending=[root];seen=set()
    while pending:
        program=pending.pop()
        if program in seen:continue
        seen.add(program)
        if len(seen)>bank.program_limit:raise Failure(5,'Variable call graph count exceeded')
        if not known(context,state,program):
            if missing and program!=root:continue
            raise Failure(1,'Variable dependency namespace is absent')
        order.append(program);pending.extend(reversed(bank.calls.get(program,[])))
    return order


def invoke(state,operation,args,line=None):
    from .archives import specification,read_file,write_files
    context=state.execution;bank=context.require('variable_archives',line);status=args[-1]
    files=context.require('files',line) if operation in ('SAVE','LOAD','PROG_BACKUP','PROG_RESTORE') else None
    try:
        if operation=='SAVE_DRAM':status.set(bank.save_dram(state,args[0]),line);return
        spec=args[1] if operation=='SAVE' else args[0]
        try:prefix,root,extension=specification(spec,wildcard=operation=='SAVE')
        except ValueError:raise Failure(2,'Invalid variable archive specification')
        if operation=='SAVE':
            if extension!='VR':raise Failure(4,'Variable SAVE requires VR')
            if args[0]=='*':
                names=sorted({state.program_name,*context.variables.programs,*[scope for scope,key in context.variables.bindings if re.fullmatch(IDENTIFIER,scope) and re.fullmatch(IDENTIFIER,key)]})
            else:names=[name(args[0])]
        elif operation in ('PROG_BACKUP','PROG_CLEAR'):names=walk(context,state,bank,root,missing=operation=='PROG_CLEAR')
        else:names=[root]
        if len(names)>bank.program_limit:raise Failure(5,'Variable archive namespace count exceeded')
        if operation in ('SAVE','PROG_BACKUP'):
            if operation=='PROG_BACKUP' and (type(args[2]) is not int or not 0<=args[2]<=65536):raise Failure(2,'Invalid free-space hint')
            if operation=='PROG_BACKUP' and not args[3]:
                names=[program for program in names if context.program_attributes is None or (context.program_attributes.record(program) or {}).get('attributes',{}).get('AT_PROTECT',1)!=2]
            rows=[capture(context,state,program,calls=bank.calls.get(program,[]),limit=bank.limit) for program in names]
            for row in rows:validate(row)
            data=[bank.encode(row) for row in rows]
            if sum(map(len,data))>bank.limit:raise Failure(5,'Variable archive batch exceeds byte budget')
            plan=[(prefix+(root if operation=='SAVE' and args[0]!='*' else row['program'])+'.VR',payload) for row,payload in zip(rows,data)]
            code=write_files(files,plan,overwrite=operation=='PROG_BACKUP',reserve_kb=args[2] if operation=='PROG_BACKUP' else 0)
        elif operation in ('CLEAR','PROG_CLEAR'):
            if prefix:raise Failure(2,'Variable clear requires an ordinary program name')
            if operation=='PROG_CLEAR':names=[program for program in names if context.program_attributes is None or (context.program_attributes.record(program) or {}).get('attributes',{}).get('AT_PROTECT',1)!=2]
            rows=[capture(context,state,program,calls=bank.calls.get(program,[]),limit=bank.limit) for program in names]
            prepared=prepare(context,state,bank,rows,status,clear=True);commit(context,bank,prepared);code=0
        else:
            rows=[];pending=[root];seen=set();size=0
            while pending:
                selected=pending.pop()
                if selected in seen:continue
                seen.add(selected)
                if len(seen)>bank.program_limit:raise Failure(5,'Variable restore count exceeded')
                code,data=read_file(files,prefix+selected+'.VR',bank.limit-size)
                if code:raise Failure(code,'Variable archive file unavailable')
                size+=len(data);row=bank.decode(data)
                if operation=='PROG_RESTORE' and row['program']!=selected:raise Failure(6,'Variable dependency archive identity differs')
                rows.append(row)
                if operation=='PROG_RESTORE':pending.extend(reversed(row['calls']))
            prepared=prepare(context,state,bank,rows,status);commit(context,bank,prepared);code=0
    except Failure as exc:code=exc.code
    except (ValueError,TypeError,rt().KarelRuntimeError):code=6
    status.set(code,line)
