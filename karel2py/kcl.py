"""An explicit scripted KCL channel; never a host or controller command runner."""
from copy import deepcopy
import math


def rt():
    from . import runtime
    return runtime


def command_text(value):
    if type(value) is not str or not value.isascii() or not 1<=len(value)<=126 or any(ord(char)<32 or ord(char)==127 for char in value):
        raise ValueError('KCL command requires 1..126 printable ASCII characters')
    value=value.strip()
    if not value:raise ValueError('KCL command cannot be blank')
    return value


def status_value(value):
    if type(value) is not int or not -2147483648<=value<=2147483646:raise ValueError('KCL statuses require ordinary INTEGER values')
    return value


class KclCommands:
    """Single accepted-command channel with configured replies and bounded history."""
    def __init__(self,replies=None,*,limit=500,history=None,sequence=0,last_status=None):
        if replies is None:replies={}
        if type(replies) is not dict or len(replies)>256:raise ValueError('KCL requires at most 256 configured replies')
        if type(limit) is not int or not 1<=limit<=4096:raise ValueError('KCL history limit requires 1..4096')
        if type(sequence) is not int or not 0<=sequence<=2147483646:raise ValueError('KCL sequence is out of range')
        self.replies={};self.limit=limit;self.history=[];self.sequence=sequence
        self.last_status=None if last_status is None else status_value(last_status);self._pending=None
        for command,row in replies.items():
            command=command_text(command)
            if command in self.replies:raise ValueError('Duplicate normalized KCL reply')
            if type(row) is not dict or set(row)-{'status','accept_status','delay_ms'} or 'status' not in row:raise ValueError('KCL reply requires status and optional acceptance/delay')
            result=status_value(row['status']);accepted=status_value(row.get('accept_status',0));delay=row.get('delay_ms',0)
            if type(delay) is not int or not 0<=delay<=86400000:raise ValueError('KCL reply delay requires 0..86400000 ms')
            self.replies[command]=dict(status=result,accept_status=accepted,delay_ms=delay)
        if history is None:history=[]
        if type(history) is not list or len(history)>limit:raise ValueError('KCL history exceeds ring limit')
        previous=0
        for row in history:
            if type(row) is not dict or set(row)!={'sequence','program','operation','command','phase','status'}:raise ValueError('Malformed KCL history row')
            if type(row['sequence']) is not int or not previous<row['sequence']<=sequence:raise ValueError('KCL history requires increasing sequence IDs')
            if type(row['program']) is not str or not row['program'].isascii() or len(row['program'])>254:raise ValueError('KCL owner requires bounded ASCII')
            if row['operation'] not in ('KCL','KCL_NO_WAIT') or row['phase'] not in ('completed','rejected','unsupported','busy'):raise ValueError('KCL history requires terminal request phases')
            if command_text(row['command'])!=row['command']:raise ValueError('KCL history command is not canonical')
            status_value(row['status']);self.history.append(row.copy());previous=row['sequence']

    def complete(self,job):
        if self._pending is job:
            job['row'].update(phase='completed',status=job['status'])
            self.last_status=job['status'];self._pending=None

    def poll(self):
        job=self._pending
        if job is not None and job['clock']()>=job['due']:self.complete(job)

    def submit(self,state,name,command,line=None):
        try:command=command_text(command)
        except ValueError as exc:raise rt().KarelRuntimeError(str(exc),line) from exc
        if self.sequence>=2147483646:raise rt().KarelRuntimeError('KCL request sequence exhausted',line)
        self.poll();reply=self.replies.get(command)
        phase='busy' if self._pending is not None else 'unsupported' if reply is None else 'rejected' if reply['accept_status'] else 'pending'
        code=2 if phase=='busy' else 1 if phase=='unsupported' else reply['accept_status']
        # Capture the clock only for actual delayed work, before mutating history.
        clock=None;now=0
        if phase=='pending' and reply['delay_ms']:
            scheduler=state._scheduler
            clock=(lambda:scheduler.now_us) if scheduler is not None else (lambda:rt().timer_clock(state,line))
            now=clock()
        self.sequence+=1
        row=dict(sequence=self.sequence,program=rt().task_root(state).program_name,operation=name,command=command,phase=phase,status=code)
        self.history.append(row);del self.history[:-self.limit]
        if phase!='pending':
            if self._pending is None:self.last_status=code
            return code,None
        job=dict(row=row,status=reply['status'],clock=clock,due=now+reply['delay_ms']*1000,delay_ms=reply['delay_ms'])
        self._pending=job
        if not reply['delay_ms']:self.complete(job)
        return 0,job

    def wait(self,state,job,line=None):
        if self._pending is job:
            remaining=max(0,math.ceil((job['due']-job['clock']())/1000))
            if remaining:yield from rt().delay_execution(state,remaining,line)
            # Standalone sleeper completion is the logical completion signal;
            # scheduler/other callers may already have completed this request.
            self.complete(job)
        return job['status']

    def invoke(self,state,name,args,line=None):
        if name=='KCL_STATUS':
            self.poll();job=self._pending
            if job is not None:return (yield from self.wait(state,job,line))
            if self.last_status is None:raise rt().KarelRuntimeError('KCL_STATUS has no submitted or configured result',line)
            return self.last_status
        code,job=self.submit(state,name,args[0],line)
        if name=='KCL' and job is not None:code=yield from self.wait(state,job,line)
        args[1].set(code,line)

    def snapshot(self):
        result=dict(replies=deepcopy(self.replies),limit=self.limit,history=deepcopy(self.history),sequence=self.sequence,last_status=self.last_status)
        if self._pending is not None:
            job=self._pending;result['pending']=dict(sequence=job['row']['sequence'],command=job['row']['command'],status=job['status'],delay_ms=job['delay_ms'])
        return result

    def to_config(self):
        if self._pending is not None:raise ValueError('Cannot persist a pending KCL command; collect KCL_STATUS first')
        return self.snapshot()

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'replies','limit','history','sequence','last_status'}:raise ValueError('Unknown KCL channel fields')
        return cls(**config)
