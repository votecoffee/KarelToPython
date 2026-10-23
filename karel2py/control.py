"""Portable counting semaphores and explicit task error notifications."""
from collections import deque
from copy import deepcopy


# Portable identifiers, deliberately independent of controller enum encodings.
# (identifier, offline effect: warning/pause/abort, local scope)
ERROR_SEVERITIES={
    'ERSEV_NONE':(0,0,False),'ERSEV_WARN':(1,0,False),
    'ERSEV_PAUSE':(2,1,False),'ERSEV_PAUSEL':(3,1,True),
    'ERSEV_STOP':(4,1,False),'ERSEV_STOPL':(5,1,True),
    'ERSEV_SERVO':(6,1,False),'ERSEV_SERVOL':(7,1,True),
    'ERSEV_ABORT':(8,2,False),'ERSEV_ABORTL':(9,2,True),
    'ERSEV_SYSTEM':(10,2,False),
}


def rt():
    from . import runtime
    return runtime


class SemaphoreBank:
    """Explicitly sized FIFO semaphores; each outstanding wait owns a ticket."""
    def __init__(self,count,initial=None):
        if type(count) is not int or not 1<=count<=32767: raise ValueError('Semaphore count must be in 1..32767')
        self.count=count; self.values={}; self.pending={}; self.tickets=[]
        for number,value in (initial or {}).items():
            self.number(number)
            if type(value) is not int or not 0<=value<=2147483646: raise ValueError('Semaphore values must be nonnegative INTEGERs')
            self.values[number]=value

    def number(self,number,line=None):
        number=rt().integer(number,line)
        if not 1<=number<=self.count: raise rt().KarelRuntimeError('Semaphore number outside the explicit bank',line)
        return number

    def value(self,number,line=None):
        number=self.number(number,line)
        return self.values.get(number,0)-len(self.pending.get(number,()))

    def post(self,number,line=None):
        number=self.number(number,line); queue=self.pending.get(number)
        if queue: queue.popleft()['granted']=True
        else:
            value=self.values.get(number,0)+1
            reserved=sum(ticket['number']==number and ticket['granted'] and not ticket['consumed'] for ticket in self.tickets)
            rt().checked(('INTEGER',),value+reserved,line)
            self.values[number]=value

    def clear(self,number,line=None):
        self.values[self.number(number,line)]=0

    def request(self,number,line=None):
        number=self.number(number,line)
        ticket=dict(number=number,granted=self.values.get(number,0)>0,consumed=False)
        if ticket['granted']: self.values[number]-=1
        else: self.pending.setdefault(number,deque()).append(ticket)
        self.tickets.append(ticket); return ticket

    def finish(self,ticket):
        ticket['consumed']=True

    def release(self,ticket):
        number=ticket['number']
        if number in self.pending: self.pending[number]=deque(item for item in self.pending[number] if item is not ticket)
        self.tickets=[item for item in self.tickets if item is not ticket]
        if ticket['granted'] and not ticket['consumed']: self.post(number)

    def snapshot(self):
        return {number:self.value(number) for number in sorted(set(self.values)|set(self.pending))}

    def to_config(self):
        if self.tickets: raise ValueError('Cannot persist semaphores with outstanding waits')
        return dict(count=self.count,values={str(k):v for k,v in self.values.items()})

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'count','values'}: raise ValueError('Unknown semaphore configuration fields')
        if type(config.get('values',{})) is not dict: raise ValueError('Semaphore values must be an object')
        values={}
        for key,value in config.get('values',{}).items():
            if type(key) is not str or not key.isascii() or not key.isdecimal() or str(int(key))!=key: raise ValueError('Semaphore keys require canonical positive integers')
            values[int(key)]=value
        return cls(config['count'],values)


class ErrorHistory:
    """Bounded error records with monotonic IDs and explicit origin/scope."""
    def __init__(self,*,limit=1000,records=()):
        if type(limit) is not int or not 1<=limit<=100000: raise ValueError('Error history limit must be in 1..100000')
        self.limit=limit; self.records=[]; self.sequence=0
        for row in records:
            required={'sequence','code','parameter','cause','severity','program','line','origin','suppressed'}
            metadata={'operation','severity_name','source_program'}
            presentation={'error_string','cause_string','time_int'}
            if type(row) is not dict or not required<=set(row) or set(row)-required-metadata-presentation: raise ValueError('Invalid error history record')
            if any(row[key] is None for key in presentation if key in row): raise ValueError('Error history presentation fields cannot be null')
            if type(row['sequence']) is not int or not self.sequence<row['sequence']<2147483647: raise ValueError('Error history IDs must increase within 1..2147483646')
            self.validate(row['code'],row['parameter'],row['cause'],row['severity'])
            self.presentation(**{key:row[key] for key in presentation if key in row})
            if type(row['program']) is not str or row['line'] is not None and (type(row['line']) is not int or row['line']<1): raise ValueError('Invalid error source')
            if row['origin'] not in ('posted','runtime','host') or type(row['suppressed']) is not bool: raise ValueError('Invalid error record metadata')
            if metadata & set(row):
                if not metadata<=set(row) or row['operation']!='POST_ERR_L' or type(row['severity_name']) is not str or row['severity_name'] not in ERROR_SEVERITIES or type(row['source_program']) is not str: raise ValueError('Invalid local error metadata')
                _,effect,local=ERROR_SEVERITIES[row['severity_name']]
                if row['severity']!=effect or (bool(row['program'])!=local): raise ValueError('Local severity metadata disagrees with effect/scope')
            self.sequence=row['sequence']; self.records.append(deepcopy(row))
        self.records=self.records[-limit:]

    def validate(self,code,parameter,cause,severity,line=None):
        runtime=rt(); code=runtime.integer(code,line); cause=runtime.integer(cause,line)
        if code<0 or cause<0: raise runtime.KarelRuntimeError('Error/cause codes must be nonnegative INTEGERs',line)
        runtime.ascii_string(parameter,line)
        if len(parameter)>254: raise runtime.KarelRuntimeError('Error parameter exceeds 254 characters',line)
        severity=runtime.integer(severity,line)
        if severity not in (0,1,2): raise runtime.KarelRuntimeError('POST_ERR severity must be 0 warning, 1 pause or 2 abort',line)

    def presentation(self,*,error_string=None,cause_string=None,time_int=None):
        fields={}
        for key,value in (('error_string',error_string),('cause_string',cause_string)):
            if value is not None:
                rt().ascii_string(value)
                if len(value)>254: raise rt().KarelRuntimeError('Error history message exceeds 254 characters')
                fields[key]=value
        if time_int is not None:
            value=rt().integer(time_int)
            if value: rt()._unpack_time(value)
            fields['time_int']=value
        return fields

    def post(self,code,parameter='',cause=0,severity=0,*,program='',line=None,origin='host',error_string=None,cause_string=None,time_int=None):
        self.validate(code,parameter,cause,severity,line)
        if type(program) is not str or origin not in ('posted','runtime','host'): raise ValueError('Invalid error origin/program')
        fields=self.presentation(error_string=error_string,cause_string=cause_string,time_int=time_int)
        if self.sequence>=2147483646: raise rt().KarelRuntimeError('Error history sequence exhausted',line)
        self.sequence+=1
        record=dict(sequence=self.sequence,code=code,parameter=parameter,cause=cause,severity=severity,program=program.upper(),line=line,origin=origin,suppressed=False)
        record.update(fields)
        self.records.append(record); self.records=self.records[-self.limit:]; return record

    def read_after(self,sequence,line=None):
        sequence=rt().integer(sequence,line)
        if sequence<0: raise rt().KarelRuntimeError('ERR_DATA sequence must be nonnegative',line)
        if sequence==2147483647: record=self.records[-1] if self.records else None
        else: record=next((row for row in self.records if row['sequence']>sequence),None)
        return deepcopy(record)

    def latest(self,program,code=None):
        return next((record for record in reversed(self.records) if (not record['program'] or record['program']==program) and (code is None or record['code']==code)),None)

    def snapshot(self): return deepcopy(self.records)
    def to_config(self): return dict(limit=self.limit,records=self.snapshot())

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'limit','records'}: raise ValueError('Unknown error history fields')
        return cls(**config)


def task_root(state):
    while state._budget_parent is not None: state=state._budget_parent
    return state


def error_history(state):
    if state.execution.errors is None: state.execution.errors=ErrorHistory()
    return state.execution.errors


def read_error_data(state,arguments,line=None):
    """Read a retained record; preflight every output before publishing fields."""
    runtime=rt()
    for reference in (arguments[2],arguments[4]):
        if type(reference.spec[1]) is not int or not 40<=reference.spec[1]<=254:
            raise runtime.KarelRuntimeError('ERR_DATA message outputs require STRING capacity in 40..254',line)
    cursor=arguments[0]
    sequence=runtime.integer(cursor.raw() if type(cursor) is runtime.Reference else cursor,line)
    if sequence<0: raise runtime.KarelRuntimeError('ERR_DATA sequence must be nonnegative',line)
    history=state.execution.errors
    record=None if history is None else history.read_after(sequence,line)
    if record is None:
        if type(cursor) is runtime.Reference: cursor.set(0,line)
        return
    values=(record['sequence'],record['code'],record.get('error_string',record['parameter']),
            record['cause'],record.get('cause_string',''),record.get('time_int',0),
            record['severity'],'' if record['origin']=='posted' else record['program'])
    prepared=[(reference,runtime.checked(reference.spec,value,line)) for reference,value in zip(arguments,values) if type(reference) is runtime.Reference]
    for reference,value in prepared: reference.set(value,line)


def error_condition(state,code,key,line=None):
    if code is not None:
        code=rt().integer(code,line)
        if code<0: raise rt().KarelRuntimeError('ERROR condition code must be nonnegative',line)
    record=error_history(state).latest(task_root(state).program_name,code)
    consumer=(state._scanning_condition,key,'ERROR',code)
    previous=state._event_seen.get(consumer,0)
    if record is None or record['sequence']<=previous: return False
    state._event_seen[consumer]=record['sequence']; state._current_error=record
    return True


def handler_action(state,action,line=None):
    if not state._in_handler: raise rt().KarelRuntimeError(action+' requires a condition action',line)
    if action=='NOPAUSE': state._pause_requested=False
    elif action=='NOABORT': state._abort_requested=False
    elif action=='NOMESSAGE':
        if state._current_error is not None: state._current_error['suppressed']=True
    else: raise rt().KarelRuntimeError('Unknown handler action',line)


def request_task_control(target,action,line=None):
    """Queue a request on a live task; terminal/inactive aborts have no frames."""
    if target.task_state in ('stopped','aborted'): return
    if action=='PAUSE': target._pause_requested=True; return
    if action!='ABORT': raise rt().KarelRuntimeError('Unsupported pending task request',line)
    if getattr(getattr(target,'program',None),'_execution',None) is None:
        target._aborted=True; target._abort_line=line; target.task_state='aborted'; return
    target._abort_requested=True; target._abort_request_line=line
    if target.task_state=='paused' and target._scheduler is not None:
        target.task_state='running'; target._pause_requested=False


def named_task_control(state,name,args,line=None):
    runtime=rt(); target=state.execution.tasks.tasks.get(args[0].upper())
    if target is None: args[-1].set(1,line); return
    if args[2]: raise runtime.KarelRuntimeError('Motion-stop/cancellation semantics are outside the offline task model',line)
    action='PAUSE' if name=='PAUSE_TASK' else 'ABORT'
    args[-1].set(0,line)
    if target._state is task_root(state):
        yield from (runtime.pause_execution if action=='PAUSE' else runtime.abort_execution)(state,line)
    else: request_task_control(target._state,action,line)


def pend_semaphore(state,number,max_time,time_out,line=None):
    runtime=rt(); bank=state.execution.require('semaphores',line)
    number=bank.number(number,line); max_time=runtime.integer(max_time,line)
    if not -1<=max_time<=86400000: raise runtime.KarelRuntimeError('PEND_SEMA max_time must be -1 or 0..86400000 ms',line)
    if type(time_out) is not runtime.Reference or time_out.spec!=('BOOLEAN',): raise runtime.KarelRuntimeError('PEND_SEMA requires a BOOLEAN output reference',line)
    def now(): return state._scheduler.now_us if state._scheduler is not None else runtime.timer_clock(state,line)
    deadline=None if max_time==-1 else now()+max_time*1000
    ticket=bank.request(number,line)
    try:
        while not ticket['granted']:
            if state._pause_requested or state._abort_requested: yield from runtime.checkpoint(state,line,force_pause=True)
            if deadline is not None and now()>=deadline:
                time_out.set(True,line); return
            yield from runtime.checkpoint(state,line)
            if ticket['granted']: break
            if state._scheduler is not None:
                until=state._scheduler.now_us+state._scheduler.quantum_us
                yield dict(kind='sleep',until=min(until,deadline) if deadline is not None else until,line=line)
            else:
                try: state._sleep(.001)
                except Exception as exc: raise runtime.KarelRuntimeError('Semaphore wait callback failed: '+str(exc),line) from exc
        time_out.set(False,line); bank.finish(ticket)
    finally: bank.release(ticket)


def post_error(state,code,parameter,cause,severity,line=None,*,severity_name=None):
    runtime=rt(); root=task_root(state)
    local=False
    if severity_name is not None:
        raw=runtime.integer(severity,line)
        match=next(((name,effect,local) for name,(identifier,effect,local) in ERROR_SEVERITIES.items() if identifier==raw),None)
        if match is None: raise runtime.KarelRuntimeError('POST_ERR_L requires a portable ERSEV_* identifier in 0..10',line)
        severity_name,severity,local=match
    stamp=state.execution.calendar.read(line) if state.execution.calendar is not None else None
    record=error_history(state).post(code,parameter,cause,severity,program=root.program_name if local else '',line=line,origin='posted',time_int=stamp)
    if severity_name is not None: record.update(operation='POST_ERR_L',severity_name=severity_name,source_program=state.program_name)
    targets=[root]
    if not local: targets.extend(program._state for program in state.execution.tasks.tasks.values() if program._state is not root and program._state.task_state in ('running','waiting','paused'))
    for target in targets:
        if severity: request_task_control(target,'PAUSE' if severity==1 else 'ABORT',line)
    previous=state._current_error; state._current_error=record
    try: yield from runtime.checkpoint(state,line)
    finally: state._current_error=previous


def runtime_failure(state,error):
    """Notify handlers, then the generated wrapper re-raises the original error."""
    runtime=rt(); root=task_root(state)
    record=error_history(state).post(1,str(error).encode('ascii','backslashreplace').decode()[:254],0,0,program=root.program_name,line=error.line,origin='runtime')
    if root.steps>=root.max_steps: return
    previous=state._current_error; state._current_error=record
    try:
        try: yield from runtime.checkpoint(state,error.line)
        except runtime.KarelRuntimeError as secondary: error.add_note('Error handler failed: '+str(secondary))
    finally: state._current_error=previous


def cooperative_service(state,name,arguments,line=None):
    runtime=rt()
    if not runtime._pythonic(): raise runtime.KarelRuntimeError('Cooperative services require Pythonic mode',line)
    row=dict(operation=name,line=line,outcome='requested'); state.service_requests.append(row)
    try:
        result=state.execution.invoke(state,name,arguments,line)
        if runtime.inspect.isgenerator(result): result=yield from result
    except GeneratorExit: row['outcome']='cancelled'; raise
    except BaseException: row['outcome']='failed'; raise
    row['outcome']='completed'; return result


def powerup_cooperative(program):
    state=program._state
    if state.task_state!='paused' or state._scheduler is not None: raise rt().KarelRuntimeError('POWERUP recovery requires a paused standalone Program')
    state._lifecycle['POWERUP']=state._lifecycle.get('POWERUP',0)+1
    return rt().resume_cooperative(program)
