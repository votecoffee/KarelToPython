"""Portable counting semaphores and explicit task error notifications."""
from collections import deque
from copy import deepcopy


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
            if type(row) is not dict or set(row)!={'sequence','code','parameter','cause','severity','program','line','origin','suppressed'}: raise ValueError('Invalid error history record')
            if type(row['sequence']) is not int or row['sequence']<=self.sequence: raise ValueError('Error history IDs must increase')
            self.validate(row['code'],row['parameter'],row['cause'],row['severity'])
            if type(row['program']) is not str or row['line'] is not None and (type(row['line']) is not int or row['line']<1): raise ValueError('Invalid error source')
            if row['origin'] not in ('posted','runtime','host') or type(row['suppressed']) is not bool: raise ValueError('Invalid error record metadata')
            self.sequence=row['sequence']; self.records.append(deepcopy(row))
        self.records=self.records[-limit:]

    def validate(self,code,parameter,cause,severity,line=None):
        runtime=rt(); code=runtime.integer(code,line); cause=runtime.integer(cause,line)
        if code<0 or cause<0: raise runtime.KarelRuntimeError('Error/cause codes must be nonnegative INTEGERs',line)
        runtime.ascii_string(parameter,line)
        if len(parameter)>254: raise runtime.KarelRuntimeError('Error parameter exceeds 254 characters',line)
        severity=runtime.integer(severity,line)
        if severity not in (0,1,2): raise runtime.KarelRuntimeError('POST_ERR severity must be 0 warning, 1 pause or 2 abort',line)

    def post(self,code,parameter='',cause=0,severity=0,*,program='',line=None,origin='host'):
        self.validate(code,parameter,cause,severity,line)
        if type(program) is not str or origin not in ('posted','runtime','host'): raise ValueError('Invalid error origin/program')
        self.sequence+=1
        record=dict(sequence=self.sequence,code=code,parameter=parameter,cause=cause,severity=severity,program=program.upper(),line=line,origin=origin,suppressed=False)
        self.records.append(record); self.records=self.records[-self.limit:]; return record

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


def post_error(state,code,parameter,cause,severity,line=None):
    runtime=rt(); root=task_root(state)
    record=error_history(state).post(code,parameter,cause,severity,line=line,origin='posted')
    targets=[root,*[program._state for program in state.execution.tasks.tasks.values() if program._state is not root and program._state.task_state in ('running','waiting','paused')]]
    for target in targets:
        if severity==1: target._pause_requested=True
        elif severity==2: target._abort_requested=True; target._abort_request_line=line
        if severity==2 and target.task_state=='paused' and target._scheduler is not None: target.task_state='running'; target._pause_requested=False
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
