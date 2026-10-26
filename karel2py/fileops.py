"""Bounded offline file comparison and printing over explicit FILE backends."""
from itertools import zip_longest
import fnmatch
import json
import re


def rt():
    from . import runtime
    return runtime


def check_name(name,line=None):
    """Portable simple file/program base name, without an extension or device."""
    name=rt().ascii_string(name,line)
    return 0 if re.fullmatch(r'[A-Za-z0-9_]{1,36}',name) else 2


def move_specification(value,*,pattern=True):
    value=rt().ascii_string(value)
    if ':' not in value: return None
    device,relative=value.split(':',1);device=device.upper()
    if device not in ('RD','FR'): return None
    relative=relative.replace('\\','/')
    if relative.startswith('/'): relative=relative[1:]
    parts=relative.split('/')
    if (any(part in ('','.','..') for part in parts) or any('*' in part for part in parts[:-1])
            or ':' in relative or pattern and any(char in relative for char in '?[]')
            or any(ord(char)<32 or ord(char)==127 for char in relative)):
        raise ValueError('MOVE_FILE requires a relative file pattern with star wildcards only in its final component')
    return device,'/'.join(parts[:-1]),parts[-1]


def move_files(files,specification,*,check=None):
    """Preflight a bounded RD/FR batch, then perform ordered per-file moves."""
    from .storage import DirectoryFiles
    parsed=move_specification(specification)
    if parsed is None: return 4
    device,parent,pattern=parsed;peer='FR' if device=='RD' else 'RD'
    check=check or (lambda:None);directory=isinstance(files,DirectoryFiles)
    plan=[];existing=set()
    def selected(name): return fnmatch.fnmatchcase(name.casefold(),pattern.casefold())
    if directory:
        if device not in files.devices or peer not in files.devices: return 4
        source_root=files._path('/'.join(part for part in (files.devices[device],parent) if part) or '.',directory=True)
        target_root=files._path('/'.join(part for part in (files.devices[peer],parent) if part) or '.',directory=True)
        if source_root==target_root: return 4
        if not source_root.is_dir(): return 1
        if not target_root.is_dir(): raise ValueError('MOVE_FILE target parent directory must already exist')
        candidates=set()
        for path in source_root.iterdir():
            check()
            if selected(path.name) and (path.is_file() or path.is_symlink()):
                candidates.add(path.relative_to(files.root).as_posix())
                if len(candidates)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        for handle in files.handles:
            if handle.owner is files:
                path=files._path(handle.name)
                if path.parent==source_root and selected(path.name):
                    candidates.add(handle.name)
                    if len(candidates)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        for name in sorted(candidates):
            source=files._path(name);target=files._path((target_root/source.name).relative_to(files.root).as_posix())
            plan.append((name,target.relative_to(files.root).as_posix()))
            if len(plan)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        wanted={files._path(target).name.casefold() for _,target in plan}
        for path in target_root.iterdir():
            check()
            if path.name.casefold() in wanted: existing.add(path.relative_to(files.root).as_posix().casefold())
    else:
        for name in sorted(files.files):
            check()
            try: candidate=move_specification(name,pattern=False)
            except ValueError: continue
            if candidate is None: continue
            found,folder,base=candidate
            if found==device and folder.casefold()==parent.casefold() and selected(base):
                target=peer+':'+(folder+'/' if folder else '')+base
                plan.append((name,target))
                if len(plan)>32767: raise ValueError('MOVE_FILE batch exceeds 32767 files')
        def logical_name(name):
            try: parsed=move_specification(name,pattern=False)
            except ValueError: parsed=None
            if parsed is None: return name.casefold()
            found,folder,base=parsed
            return (found+':'+(folder+'/' if folder else '')+base).casefold()
        existing={logical_name(name) for name in files.files}
    if not plan: return 1
    key=str.casefold if directory else logical_name
    busy={key(handle.name) for handle in files.handles if handle.owner is files}
    if any(key(source) in busy or key(target) in busy for source,target in plan): return 3
    targets=[target.casefold() for _,target in plan]
    if len(set(targets))!=len(targets) or any(target in existing for target in targets): return 2
    preflight=getattr(files,'preflight_moves',None)
    if preflight is not None: preflight(plan)
    for source,target in plan:
        check()
        if directory:
            path=files._path(source)
            if not path.is_file() or path.stat().st_size>files.limit: raise ValueError('MOVE_FILE source is not a bounded regular file')
        else: files._check(source,files.files[source]);files._check(target,b'')
    for source,target in plan:
        check()
        if directory:
            code,data=files.read_named(source)
            if code: return code
            code=files.rename(source,target)
            if code: return code
            files.files[target]=bytearray(data)
        else:
            code=files.rename(source,target)
            if code: return code
    return 0


def ascii_lines(data):
    text=data.decode('ascii');start=0
    for boundary in re.finditer(r'\r\n|\r|\n',text):
        yield text[start:boundary.start()];start=boundary.end()
    if start<len(text): yield text[start:]


def compare_files(state,files,left_name,right_name,handle,ascii_flag,line=None):
    runtime=rt();ascii_flag=runtime.boolean(ascii_flag,line)
    handle.require_open(line)
    if handle.owner is not files: raise runtime.KarelRuntimeError('Comparison result FILE must belong to the input backend',line)
    if handle.mode=='R': raise runtime.KarelRuntimeError('Comparison result FILE must be writable',line)
    left_code,left=files.read_named(left_name)
    if left_code: return left_code,None
    right_code,right=files.read_named(right_name)
    if right_code: return right_code,None
    start=len(files.files[handle.name]) if handle.mode=='A' else handle.position
    capacity=files.limit-start;records=bytearray();eol=bytes((handle.eol,))
    def record(value):
        data=json.dumps(value,ensure_ascii=True,separators=(',',':')).encode('ascii')+eol
        if len(records)+len(data)>capacity: raise runtime.KarelRuntimeError('Comparison report exceeds remaining FILE capacity',line)
        return data
    if ascii_flag:
        # Decode both inputs completely before comparing or preparing output.
        left.decode('ascii');right.decode('ascii');count=0
        for number,(a,b) in enumerate(zip_longest(ascii_lines(left),ascii_lines(right)),1):
            state.tick(line)
            if a!=b:
                count+=1;records.extend(record(dict(line=number,left=a,right=b)))
        summary=dict(mode='ascii',left=left_name,right=right_name,different_lines=count)
    else:
        count=0;a=b=None
        for offset in range(0,max(len(left),len(right)),4096):
            state.tick(line);first=left[offset:offset+4096];second=right[offset:offset+4096]
            if first!=second:
                local=next((index for index,(x,y) in enumerate(zip(first,second)) if x!=y),min(len(first),len(second)))
                index=offset+local;count=index+1
                a=left[index] if index<len(left) else None;b=right[index] if index<len(right) else None
                break
        summary=dict(mode='binary',left=left_name,right=right_name,first_difference=count,left_byte=a,right_byte=b)
    header=record(summary)
    count=runtime.checked(('INTEGER',),count,line)
    files.write(handle,header+records,line)
    return 0,count


def print_file(state,files,name,nowait,line=None):
    runtime=rt();runtime.boolean(nowait,line)
    code,data=files.read_named(name)
    if code: return code
    text=data.decode('ascii');root=runtime.task_root(state)
    for offset in range(0,len(text),254):
        state.tick(line)
        try: state.write_string(text[offset:offset+254],line)
        except Exception:
            if root._aborted: raise runtime.KarelAbort(root._abort_line)
            if state._aborted: raise runtime.KarelAbort(state._abort_line)
            raise
        if root._aborted: raise runtime.KarelAbort(root._abort_line)
        if state._aborted: raise runtime.KarelAbort(state._abort_line)
    return 0


def file_operation(state,name,args,line=None):
    runtime=rt();files=state.execution.require('files',line)
    try:
        if name=='PRINT_FILE': code=print_file(state,files,*args[:2],line)
        else:
            code,count=compare_files(state,files,*args[:4],line)
            if code==0: args[4].set(count,line)
    except (OSError,ValueError) as exc:
        raise runtime.KarelRuntimeError('FILE operation failed: '+str(exc),line) from exc
    args[-1].set(code,line)
