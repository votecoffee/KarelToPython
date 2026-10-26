"""Bounded source-event diagnostics and explicit logical call-stack estimates."""
from copy import deepcopy
from weakref import WeakKeyDictionary

# Portable labels; these numbers are independent of native DEBUG environment IDs.
DIAGNOSTIC_CONSTANTS={name:index for index,name in enumerate(
    ('LOG_ENABLE','LOG_DISABLE','START_K_LINE','CALL','RTN_FRM_RTN','TASK_START','TASK_END','PCODE_EXEC'),1)}


def rt():
    from . import runtime
    return runtime


def flag(value,line=None):
    if type(value) is bool:return value
    if type(value) is int and value in (0,1):return bool(value)
    raise rt().KarelRuntimeError('CHECK_STACK initialize requires BOOLEAN or INTEGER 0/1',line)


class DiagnosticLog:
    """Events describe this offline interpreter; stack words are a chosen model."""
    def __init__(self,*,stack_words=4096,frame_words=32,limit=500,selected=None,
                 logging_enabled=True,default_enabled=False,records=None,sequence=0):
        if type(stack_words) is not int or not 1<=stack_words<=2147483646:raise ValueError('stack_words requires 1..2147483646')
        if type(frame_words) is not int or not 1<=frame_words<=stack_words:raise ValueError('frame_words requires 1..stack_words')
        if type(limit) is not int or not 1<=limit<=4096:raise ValueError('Diagnostic limit requires 1..4096')
        if type(logging_enabled) is not bool or type(default_enabled) is not bool:raise ValueError('Diagnostic logging flags require BOOLEANs')
        if selected is None:selected=[]
        if type(selected) not in (list,tuple) or any(type(value) is not int or value not in DIAGNOSTIC_CONSTANTS.values() for value in selected) or len(selected)!=len(set(selected)):
            raise ValueError('Selected diagnostics require distinct supported event IDs')
        if type(sequence) is not int or not 0<=sequence<=2147483646:raise ValueError('Diagnostic sequence is out of range')
        self.stack_words=stack_words;self.frame_words=frame_words;self.limit=limit
        self.selected=set(selected);self.logging_enabled=logging_enabled;self.default_enabled=default_enabled
        self.records=[];self.sequence=sequence;self._tasks=WeakKeyDictionary()
        if records is None:records=[]
        if type(records) is not list or len(records)>limit:raise ValueError('Diagnostic records exceed the ring limit')
        previous=0
        for row in records:
            if type(row) is not dict or set(row)!={'sequence','event','task','program','routine','line','depth'}:raise ValueError('Malformed diagnostic record')
            if type(row['sequence']) is not int or not previous<row['sequence']<=sequence:raise ValueError('Diagnostic records require increasing sequence IDs')
            if type(row['event']) is not str or row['event'] not in DIAGNOSTIC_CONSTANTS:raise ValueError('Unsupported diagnostic event')
            if any(type(row[key]) is not str or not row[key].isascii() or len(row[key])>254 for key in ('task','program','routine')):raise ValueError('Diagnostic names require bounded ASCII')
            if row['line'] is not None and (type(row['line']) is not int or not 1<=row['line']<=100000):raise ValueError('Diagnostic line is invalid')
            if type(row['depth']) is not int or not 0<=row['depth']<=64:raise ValueError('Diagnostic depth is invalid')
            self.records.append(row.copy());previous=row['sequence']

    def task(self,state):
        root=rt().task_root(state)
        if root not in self._tasks:self._tasks[root]=dict(enabled=self.default_enabled,low=None,ended=False)
        return root,self._tasks[root]

    def free(self,state):return max(0,self.stack_words-self.frame_words*len(rt().task_root(state)._task_frames))

    def observe(self,state):
        _,task=self.task(state)
        if task['low'] is not None:task['low']=min(task['low'],self.free(state))

    def record(self,state,event,line=None):
        root,task=self.task(state)
        if not self.logging_enabled or not task['enabled'] or DIAGNOSTIC_CONSTANTS[event] not in self.selected:return
        # Logging must never alter source execution when its finite sequence ends.
        if self.sequence>=2147483646:return
        self.sequence+=1
        routine=root._task_frames[-1][1] if root._task_frames else ''
        self.records.append(dict(sequence=self.sequence,event=event,task=root.program_name,
            program=state.program_name,routine=routine,line=line,depth=len(root._task_frames)))
        del self.records[:-self.limit]

    def begin(self,state):
        root=rt().task_root(state)
        self._tasks[root]=dict(enabled=self.default_enabled,low=None,ended=False)
        self.record(state,'TASK_START')

    def finish(self,state):
        _,task=self.task(state)
        if not task['ended']:self.record(state,'TASK_END');task['ended']=True

    def checkpoint(self,state,line=None):
        self.observe(state)
        if line is not None:
            self.record(state,'START_K_LINE',line);self.record(state,'PCODE_EXEC',line)

    def invoke(self,state,name,args,line=None):
        if name=='SET_DEBUG':
            enabled=rt().boolean(args[0],line);_,task=self.task(state)
            if enabled:task['enabled']=True;self.record(state,'LOG_ENABLE',line)
            else:self.record(state,'LOG_DISABLE',line);task['enabled']=False
        elif name=='SET_DB_EVENT':
            event=rt().integer(args[0],line);enabled=rt().boolean(args[1],line)
            if event not in DIAGNOSTIC_CONSTANTS.values():raise rt().KarelRuntimeError('Unsupported offline diagnostic event ID',line)
            if enabled:self.selected.add(event)
            else:self.selected.discard(event)
        else:
            initialize=flag(args[0],line);low=rt().boolean(args[1],line);_,task=self.task(state)
            current=self.free(state)
            if initialize:task['low']=current
            if low and task['low'] is None:raise rt().KarelRuntimeError('CHECK_STACK low-water query requires initialization',line)
            result=task['low'] if low else current
            if args[2]!=0:args[2].set(result,line)

    def to_config(self):
        return dict(stack_words=self.stack_words,frame_words=self.frame_words,limit=self.limit,
            selected=sorted(self.selected),logging_enabled=self.logging_enabled,default_enabled=self.default_enabled,
            records=deepcopy(self.records),sequence=self.sequence)

    def snapshot(self):return self.to_config()

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'stack_words','frame_words','limit','selected','logging_enabled','default_enabled','records','sequence'}:
            raise ValueError('Unknown diagnostic configuration fields')
        return cls(**config)
