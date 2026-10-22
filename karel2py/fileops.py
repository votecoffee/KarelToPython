"""Bounded offline file comparison and printing over explicit FILE backends."""
from itertools import zip_longest
import json
import re


def rt():
    from . import runtime
    return runtime


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
