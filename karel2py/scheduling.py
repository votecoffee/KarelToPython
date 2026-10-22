"""Deterministic cooperative task scheduling and offline event delivery."""
from contextlib import contextmanager


# Package identifiers, deliberately separate from native controller enums.
TASK_ATTRIBUTES={name:index for index,name in enumerate((
    'TSK_HOLDCOND','TSK_LINENUM','TSK_LOCKGRP','TSK_MCTL','TSK_NOABORT',
    'TSK_NOBUSY','TSK_NOPAUSE','TSK_NUMCLDS','TSK_PARENT','TSK_PAUSESFT',
    'TSK_PRIORITY','TSK_PROGNAME','TSK_PROGTYPE','TSK_ROUTNAME','TSK_STACK',
    'TSK_STATUS','TSK_STEP','TSK_TIMESLIC','TSK_TPMOTION','TSK_TRACE','TSK_TRACELEN'),1)}
TASK_STATES={name:100+index for index,name in enumerate((
    'PG_RUNACCEPT','PG_ABORTING','PG_RUNNING','PG_PAUSED','PG_ABORTED',
    'PG_COMPLETED','PG_STOPPED','PG_FAILED','PG_WAITING'))}
TASK_PROGRAM_TYPES={'PG_NOT_EXEC':200,'PG_MNEMONIC':201,'PG_AR_KAREL':202}
TASK_CONSTANTS={**TASK_ATTRIBUTES,**TASK_STATES,**TASK_PROGRAM_TYPES}
TASK_DYNAMIC={'TSK_LINENUM','TSK_PROGNAME','TSK_PROGTYPE','TSK_ROUTNAME','TSK_STACK','TSK_STATUS','TSK_TIMESLIC'}


def rt():
    from . import runtime
    return runtime


def bind_task(registry,name,program,attributes=None):
    runtime=rt();name=runtime.ascii_string(name).upper()
    if not name or len(name)>254: raise ValueError('Task binding requires an ASCII name of 1..254 characters')
    if not all(callable(getattr(program,method,None)) for method in ('run','resume','pause','stop')):
        raise TypeError('Tasks require a cooperative Program; translate with cooperative=True')
    if attributes is not None and type(attributes) is not dict: raise ValueError('Task attributes must be a named INTEGER mapping')
    values={}
    for key,value in (attributes or {}).items():
        if type(key) is not str or key.upper() not in TASK_ATTRIBUTES or key.upper() in TASK_DYNAMIC or key.upper() in values:
            raise ValueError('Only distinct unmodeled TSK_* attributes can be supplied')
        values[key.upper()]=runtime.integer(value)
    registry.tasks[name]=program;registry.attributes[name]=values


def task_attribute(registry,name,program,attribute,line=None):
    runtime=rt();root=runtime.task_root(program._state)
    active=root._task_frames[-1] if root._task_frames else (root,'')
    state=root.task_state
    if attribute=='TSK_STATUS':
        key={'ready':'PG_RUNACCEPT','running':'PG_RUNNING','paused':'PG_PAUSED','waiting':'PG_WAITING',
             'completed':'PG_COMPLETED','stopped':'PG_STOPPED','aborted':'PG_ABORTED','failed':'PG_FAILED'}[state]
        if root._abort_requested and state in ('ready','running','paused','waiting'): key='PG_ABORTING'
        return TASK_STATES[key]
    if attribute=='TSK_PROGTYPE': return TASK_PROGRAM_TYPES['PG_AR_KAREL' if root._has_run else 'PG_NOT_EXEC']
    if attribute=='TSK_PROGNAME': return active[0].program_name
    if attribute=='TSK_ROUTNAME': return active[1]
    if attribute=='TSK_LINENUM': return root._task_line
    if attribute=='TSK_STACK': return len(root._task_frames)
    if attribute=='TSK_TIMESLIC': return getattr(root._scheduler or registry,'quantum_us',0)//1000
    value=getattr(registry,'attributes',{}).get(name,{}).get(attribute)
    return None if value is None else runtime.integer(value,line)


def get_task_info(state,arguments,line=None):
    runtime=rt();name_ref,number_ref,attribute,int_ref,str_ref,status=arguments
    attribute=runtime.integer(attribute,line)
    key=next((key for key,value in TASK_ATTRIBUTES.items() if value==attribute),None)
    if key is None: status.set(2,line);return
    number=number_ref.raw()
    if number is not runtime.UNINITIALIZED: number=runtime.integer(number,line)
    by_name=number is runtime.UNINITIALIZED or number==0
    registry=state.execution.tasks;tasks=list(registry.tasks.items())
    if by_name:
        selected=runtime.ascii_string(name_ref.raw(),line).upper()
        number=next((index for index,(name,_) in enumerate(tasks,1) if name==selected),None)
        if number is None: status.set(1,line);return
    else:
        number=runtime.integer(number,line)
        if number<1: status.set(2,line);return
        if number>len(tasks): status.set(1,line);return
    name,program=tasks[number-1]
    value=task_attribute(registry,name,program,key,line)
    if value is None: status.set(3,line);return
    target=str_ref if key in ('TSK_PROGNAME','TSK_ROUTNAME') else int_ref
    value=runtime.checked(target.spec,value,line)
    identity=runtime.checked(number_ref.spec,number,line) if by_name else runtime.checked(name_ref.spec,name,line)
    if by_name: number_ref.set(identity,line)
    else: name_ref.set(identity,line)
    target.set(value,line);status.set(0,line)


class EventBank:
    """Broadcast event generations; every consumer keeps its own cursor."""
    def __init__(self,initial=None):
        self.generations={}
        for key,value in (initial or {}).items():
            number=self.number(int(key))
            if type(value) is not int or not 0<=value<2147483647: raise ValueError('Invalid event generation')
            self.generations[number]=value
    def number(self,number,line=None):
        number=rt().integer(number,line)
        if not 1<=number<=32767: raise rt().KarelRuntimeError('Event number must be in 1..32767',line)
        return number
    def signal(self,number,line=None):
        number=self.number(number,line); value=self.generations.get(number,0)+1
        value=rt().checked(('INTEGER',),value,line); self.generations[number]=value
    def generation(self,number,line=None): return self.generations.get(self.number(number,line),0)
    def snapshot(self): return {str(key):value for key,value in sorted(self.generations.items())}


def events(state):
    if state.execution.events is None: state.execution.events=EventBank()
    return state.execution.events


def signal_event(state,number,line=None): events(state).signal(number,line)


def event_condition(state,number,key,line=None):
    bank=events(state); number=bank.number(number,line)
    consumer=(getattr(state,'_scanning_condition',None),key,number)
    generation=bank.generation(number,line); previous=state._event_seen.get(consumer,0)
    state._event_seen[consumer]=generation
    return generation>previous


def edge_condition(state,key,value,direction,line=None):
    value=rt().boolean(value,line); consumer=(getattr(state,'_scanning_condition',None),key)
    previous=state._edge_history.get(consumer,False); state._edge_history[consumer]=value
    return value and not previous if direction=='+' else previous and not value


def lifecycle_condition(state,name,key):
    generation=state._lifecycle.get(name,0); consumer=(getattr(state,'_scanning_condition',None),key,name)
    previous=state._event_seen.get(consumer,0); state._event_seen[consumer]=generation
    return generation>previous


def delay_execution(state,milliseconds,line=None):
    runtime=rt(); milliseconds=runtime.integer(milliseconds,line)
    if not 0<=milliseconds<=86400000: raise runtime.KarelRuntimeError('DELAY requires milliseconds in 0..86400000',line)
    if state._scheduler is None:
        state.delay(milliseconds,line); return
    if milliseconds:
        deadline=state._scheduler.now_us+milliseconds*1000
        while state._scheduler.now_us<deadline:
            yield {'kind':'sleep','until':deadline,'line':line}
            if state._pause_requested or state._abort_requested: yield from rt().checkpoint(state,line,force_pause=True)


@contextmanager
def condition_scope(state):
    previous=set(state._handlers)
    try: yield
    finally:
        for number in set(state._handlers)-previous: state._handlers.pop(number,None)


class TaskScheduler:
    """Round-robin checkpoints with a deterministic clock; no operating-system tasks."""
    def __init__(self,*,quantum_ms=1,max_steps=100000):
        if type(quantum_ms) is not int or not 1<=quantum_ms<=1000: raise ValueError('Scheduler quantum must be in 1..1000 ms')
        if type(max_steps) is not int or max_steps<1: raise ValueError('Task step budget must be positive')
        self.tasks={}; self.attributes={}; self.quantum_us=quantum_ms*1000; self.max_steps=max_steps
        self.now_us=0; self.waiting={}; self.errors={}; self._running=False
    def bind(self,name,program,*,attributes=None): bind_task(self,name,program,attributes)
    def start(self,name,*,paused=False):
        name=name.upper()
        if name not in self.tasks: raise KeyError(name)
        program=self.tasks[name]; state=program._state
        if getattr(program,'_execution',None) is not None: raise rt().KarelRuntimeError('Task is already active')
        if state.task_state=='stopped': raise rt().KarelStop('Task is stopped; create a new instance')
        with rt()._numeric_scope('pythonic'):
            state.begin(self.max_steps)
        state._scheduler=self
        if state._clock_us is None: state._clock_us=lambda:self.now_us; state._scheduler_clock=True
        state._pause_requested=paused; state.task_state='running'
        program._execution=program._execute(); self.waiting.pop(name,None); self.errors.pop(name,None)
    def continue_task(self,name,*,powerup=False):
        if type(powerup) is not bool: raise TypeError('powerup must be BOOLEAN')
        program=self.tasks[name.upper()]
        if program._state.task_state!='paused': raise rt().KarelRuntimeError('Only a paused task can continue')
        program._state.task_state='running'; program._state._pause_requested=False
        program._state._lifecycle['CONTINUE']=program._state._lifecycle.get('CONTINUE',0)+1
        if powerup: program._state._lifecycle['POWERUP']=program._state._lifecycle.get('POWERUP',0)+1
    def powerup(self,name): self.continue_task(name,powerup=True)
    def stop(self,name):
        name=name.upper(); self.tasks[name].stop(); self.waiting.pop(name,None)
    def step(self):
        runtime=rt(); progressed=False
        for name,program in tuple(self.tasks.items()):
            state=program._state
            if state.task_state=='waiting':
                deadline=self.waiting.get(name,0)
                if self.now_us<deadline and not state._pause_requested and not state._abort_requested: continue
                state.task_state='running'; self.waiting.pop(name,None)
            if state.task_state!='running' or getattr(program,'_execution',None) is None: continue
            progressed=True; state._driving=True
            try:
                with runtime._numeric_scope('pythonic'): event=next(program._execution)
                if type(event) is not dict: raise runtime.KarelRuntimeError('Invalid scheduler event')
                if event['kind']=='pause': state.task_state='paused'
                elif event['kind']=='sleep': self.waiting[name]=event['until']; state.task_state='waiting'
                elif event['kind']!='timeslice': raise runtime.KarelRuntimeError('Unknown scheduler event')
            except StopIteration:
                program._execution=None; state.task_state='completed'; state._scheduler=None
                if getattr(state,'_scheduler_clock',False): state._clock_us=None; state._scheduler_clock=False
            except BaseException as exc:
                if getattr(program,'_execution',None) is not None: program._execution.close(); program._execution=None
                state.task_state='stopped' if isinstance(exc,runtime.KarelStop) else 'aborted' if isinstance(exc,runtime.KarelAbort) else 'failed'
                state._scheduler=None
                if state._scheduler_clock: state._clock_us=None; state._scheduler_clock=False
                self.errors[name]=exc; raise
            finally: state._driving=False
        self.now_us+=self.quantum_us
        if not progressed and self.waiting: self.now_us=max(self.now_us,min(self.waiting.values()))
        return progressed
    def run(self,*,max_cycles=100000):
        if self._running: raise rt().KarelRuntimeError('Scheduler cannot be driven recursively')
        if type(max_cycles) is not int or max_cycles<1: raise ValueError('Scheduler cycle budget must be positive')
        self._running=True
        try:
            for _ in range(max_cycles):
                if not any(program._state.task_state in ('running','waiting') for program in self.tasks.values()): return self.snapshot()
                self.step()
            raise rt().KarelRuntimeError('Scheduler cycle budget exceeded')
        finally: self._running=False
    def snapshot(self):
        return {name:{'state':program._state.task_state,'values':program.snapshot()} for name,program in self.tasks.items()}


def control_task(state,action,number,line=None):
    number=rt().integer(number,line); tasks=list(state.execution.tasks.tasks.values())
    if not 1<=number<=len(tasks): raise rt().KarelRuntimeError('Task number is not registered',line)
    target=tasks[number-1]
    if target._state is rt().task_root(state):
        if action=='PAUSE': yield from rt().pause_execution(state,line)
        elif action=='ABORT': yield from rt().abort_execution(state,line)
        else:
            state._pause_requested=False; state._lifecycle['CONTINUE']+=1
            yield from rt().checkpoint(state,line)
        return
    if action in ('PAUSE','ABORT'): rt().request_task_control(target._state,action,line)
    elif target._state._scheduler is not None: target._state._scheduler.continue_task(next(name for name,program in state.execution.tasks.tasks.items() if program is target))
    else:
        try: target.resume()
        except (rt().KarelPause,rt().KarelAbort,rt().KarelStop): pass
