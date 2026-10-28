"""Atomic portable TP/VR recursive batches over explicit in-memory services."""
from copy import deepcopy
import hashlib
import re

from . import archives as tp,variable_archives as vr

FORMAT='karel2py-program-batch-v1'


def rt():return tp.rt()


def limits(context):
    banks=[context.variable_archives]
    if context.teach_programs is not None:banks.append(context.teach_programs)
    return min(bank.limit if type(bank) is vr.VariableArchives else bank.archive_limit for bank in banks),max(bank.program_limit for bank in banks)


def children(context,program):
    teach=context.teach_programs
    values=([*teach._calls.get(program,[])] if teach is not None else [])+context.variable_archives.calls.get(program,[])
    return list(dict.fromkeys(target for target in values if teach is None or teach._programs.get(target,{}).get('type')!='MR'))


def guarded(context,program):
    teach=context.teach_programs;record=context.program_attributes.record(program) if context.program_attributes is not None else None
    default=teach._programs.get(program,{}).get('attributes',{}).get('AT_PROTECT',1) if teach is not None else 1
    return (record or {}).get('attributes',{}).get('AT_PROTECT',default)==2


def walk(context,state,root,*,missing=False):
    teach=context.teach_programs;_,count=limits(context);pending=[root];seen=set();rows=[];edges=0
    while pending:
        program=pending.pop()
        if program in seen:continue
        seen.add(program)
        if len(seen)>count:raise vr.Failure(5,'Mixed archive identity count exceeded')
        has_tp=teach is not None and program in teach._programs;has_vr=vr.known(context,state,program)
        if not has_tp and not has_vr:
            if missing and program!=root:continue
            raise vr.Failure(1,'Mixed archive dependency is absent')
        calls=children(context,program);edges+=len(calls)
        if edges>32767:raise vr.Failure(5,'Mixed archive edge limit exceeded')
        rows.append((program,has_tp,has_vr,calls));pending.extend(reversed(calls))
    return rows


def manifest(root,entries,limit):return tp.encode_json(dict(format=FORMAT,root=root,entries=entries),limit)


def decode(data,root,limit,count):
    row=tp.decode_json(data,limit)
    if type(row) is not dict or set(row)!={'format','root','entries'} or row['format']!=FORMAT or row['root']!=root:raise ValueError('Invalid mixed archive identity/format')
    entries=row['entries']
    if type(entries) is not list or not 1<=len(entries)<=count:raise ValueError('Invalid mixed archive entry count')
    names={};edges=0
    for entry in entries:
        if type(entry) is not dict or set(entry)!={'name','files','calls'} or vr.name(entry['name'])!=entry['name'] or entry['name'] in names:raise ValueError('Invalid mixed archive entry identity')
        files=entry['files'];calls=entry['calls']
        if type(files) is not dict or set(files)-{'TP','VR'} or any(type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None for digest in files.values()):raise ValueError('Invalid mixed archive file hashes')
        vr.graph_value({entry['name']:calls},count);edges+=len(calls)
        if edges>32767:raise ValueError('Mixed archive edge limit exceeded')
        names[entry['name']]=entry
    if root not in names or any(target not in names for entry in entries for target in entry['calls']):raise ValueError('Incomplete mixed archive graph')
    seen=set();pending=[root]
    while pending:
        name=pending.pop()
        if name in seen:continue
        seen.add(name);pending.extend(names[name]['calls'])
    if seen!=set(names):raise ValueError('Unreachable mixed archive entries')
    return entries


def backup(context,state,root,prefix,reserve,include):
    if type(reserve) is not int or not 0<=reserve<=65536:raise vr.Failure(2,'Invalid mixed free-space hint')
    limit,_=limits(context);teach=context.teach_programs;bank=context.variable_archives;entries=[];plan=[];size=0
    rows=walk(context,state,root)
    if sum(has_vr for _,_,has_vr,_ in rows)>bank.program_limit:raise vr.Failure(5,'Mixed VR namespace count exceeded')
    for program,has_tp,has_vr,calls in rows:
        files={}
        if include or not guarded(context,program):
            if has_tp:
                code=tp.guard(context,state,teach,program,write=False)
                if code:raise vr.Failure(code,'Mixed TP snapshot is busy')
                try:data=tp.encode(teach,program)
                except ValueError as error:raise vr.Failure(5,str(error)) from error
                files['TP']=hashlib.sha256(data).hexdigest();plan.append((prefix+program+'.TP',data));size+=len(data)
            if has_vr:
                row=vr.capture(context,state,program,calls=[target for target in bank.calls.get(program,[]) if target in calls],limit=bank.limit);vr.validate(row);data=bank.encode(row)
                files['VR']=hashlib.sha256(data).hexdigest();plan.append((prefix+program+'.VR',data));size+=len(data)
        if size>limit:raise vr.Failure(5,'Mixed archive batch exceeds byte budget')
        entries.append(dict(name=program,files=files,calls=calls))
    try:data=manifest(root,entries,limit-size)
    except ValueError as error:raise vr.Failure(5,str(error)) from error
    plan.append((prefix+root+'.PB',data))
    return tp.write_files(context.require('files'),plan,overwrite=True,reserve_kb=reserve)


def clear(context,state,root,status):
    teach=context.teach_programs;bank=context.variable_archives;selected=[];snapshots=[]
    for program,has_tp,has_vr,calls in walk(context,state,root,missing=True):
        if guarded(context,program):continue
        if has_tp:
            code=tp.guard(context,state,teach,program,write=True)
            if code:raise vr.Failure(code,'Mixed TP clear is busy')
            selected.append(program)
        if has_vr:snapshots.append(vr.capture(context,state,program,calls=bank.calls.get(program,[]),limit=bank.limit))
    prepared=vr.prepare(context,state,bank,snapshots,status,clear=True)
    for program in selected:
        del teach._programs[program];teach._calls.pop(program,None);tp.refresh_flags(context,teach,program)
    vr.commit(context,bank,prepared);return 0


def restore(context,state,root,prefix,data,status):
    limit,count=limits(context)
    try:entries=decode(data,root,limit,count)
    except vr.Failure as error:raise ValueError('Malformed mixed archive graph') from error
    teach=context.teach_programs;bank=context.variable_archives
    prepared={};graph={} if teach is None else deepcopy(teach._calls);snapshots=[];bridges={};size=len(data);files=context.require('files')
    for entry in entries:
        program=entry['name']
        if not entry['files']:raise vr.Failure(1,'Mixed archive omitted a required protected identity')
        covered=set()
        for kind,digest in entry['files'].items():
            code,payload=tp.read_file(files,prefix+program+'.'+kind,limit-size)
            if code:raise vr.Failure(code,'Mixed archive member unavailable')
            size+=len(payload)
            if hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('Mixed archive member hash differs')
            if kind=='TP':
                if teach is None:raise vr.Failure(4,'Mixed archive needs explicit TeachPrograms')
                identity,row,calls=tp.decode(teach,payload)
                if identity!=program or not set(calls)<=set(entry['calls']):raise ValueError('Mixed TP member identity/graph differs')
                covered.update(calls)
                if program not in teach._programs:
                    code=tp.guard(context,state,teach,program,write=True)
                    if code:raise vr.Failure(code,'Mixed TP restore is busy')
                    prepared[program]=row;graph[program]=calls
            else:
                row=bank.decode(payload)
                if row['program']!=program or not set(row['calls'])<=set(entry['calls']):raise ValueError('Mixed VR member identity/graph differs')
                if guarded(context,program):raise vr.Failure(4,'Mixed VR restore is protected')
                covered.update(row['calls']);snapshots.append(row)
        extra=[target for target in entry['calls'] if target not in covered]
        if extra:bridges[program]=extra
    if teach is not None:
        if len(teach._programs)+len(prepared)>teach.program_limit:raise vr.Failure(5,'Mixed TP program count exceeded')
        try:graph=tp.call_graph(graph,teach.program_limit)
        except ValueError as error:raise vr.Failure(5,str(error)) from error
    variables=vr.prepare(context,state,bank,snapshots,status)
    # Edges supplied for a namespace without that store's record must still
    # survive fresh restore. Retain these bridge edges in the variable graph.
    for program,targets in bridges.items():variables[3][program]=list(dict.fromkeys(variables[3].get(program,[])+targets))
    try:vr.graph_value(variables[3],bank.program_limit)
    except ValueError as error:raise vr.Failure(5,str(error)) from error
    if teach is not None:
        teach._programs.update(prepared);teach._calls=graph
        for program in prepared:tp.refresh_flags(context,teach,program)
    vr.commit(context,bank,variables);return 0


def invoke(state,operation,args,line=None):
    """Return False only when the ordinary TP/VR branch owns this source form."""
    context=state.execution
    selected=operation in ('PROG_BACKUP','PROG_CLEAR') and args[1]==tp.ARCHIVE_CONSTANTS['PBR_ALLTYPE']
    if not selected and operation!='PROG_RESTORE':return False
    status=args[-1]
    if operation in ('PROG_BACKUP','PROG_RESTORE'):context.require('files',line)
    try:
        try:prefix,root,extension=tp.specification(args[0])
        except ValueError:raise vr.Failure(2,'Invalid mixed archive specification')
        if operation=='PROG_RESTORE':
            if extension=='VR':return False
            limit,_=limits(context);code,data=tp.read_file(context.require('files',line),prefix+root+'.PB',limit)
            if code==1 and extension!='PB':return False
            if code:raise vr.Failure(code,'Mixed archive manifest unavailable')
            code=restore(context,state,root,prefix,data,status)
        elif operation=='PROG_BACKUP':code=backup(context,state,root,prefix,args[2],args[3])
        else:
            if prefix:raise vr.Failure(2,'Mixed clear requires a plain name')
            if extension not in ('','TP','VR'):raise vr.Failure(4,'Unsupported mixed clear extension')
            code=clear(context,state,root,status)
    except vr.Failure as error:code=error.code
    except (ValueError,TypeError,rt().KarelRuntimeError):code=6
    status.set(code,line);return True
