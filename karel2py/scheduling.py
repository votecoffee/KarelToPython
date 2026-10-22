"""Deterministic cooperative task scheduling and offline event delivery."""
from contextlib import contextmanager


def rt():
    from . import runtime
    return runtime


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
            if state._pause_requested: yield from rt().checkpoint(state,line,force_pause=True)


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
        self.tasks={}; self.quantum_us=quantum_ms*1000; self.max_steps=max_steps
        self.now_us=0; self.waiting={}; self.errors={}; self._running=False
    def bind(self,name,program):
        if not all(callable(getattr(program,method,None)) for method in ('run','resume','pause','stop')): raise TypeError('Scheduler requires cooperative Programs')
        self.tasks[name.upper()]=program
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
    def continue_task(self,name):
        program=self.tasks[name.upper()]
        if program._state.task_state!='paused': raise rt().KarelRuntimeError('Only a paused task can continue')
        program._state.task_state='running'; program._state._pause_requested=False
        program._state._lifecycle['CONTINUE']=program._state._lifecycle.get('CONTINUE',0)+1
    def stop(self,name):
        name=name.upper(); self.tasks[name].stop(); self.waiting.pop(name,None)
    def step(self):
        runtime=rt(); progressed=False
        for name,program in tuple(self.tasks.items()):
            state=program._state
            if state.task_state=='waiting':
                deadline=self.waiting.get(name,0)
                if self.now_us<deadline and not state._pause_requested: continue
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
    if target._state is state:
        if action=='PAUSE': yield from rt().pause_execution(state,line)
        elif action=='ABORT': yield from rt().abort_execution(state,line)
        else: state._pause_requested=False; state._lifecycle['CONTINUE']+=1
        return
    if action=='PAUSE': target.pause()
    elif action=='ABORT':
        target.stop(); target._state._aborted=True; target._state._abort_line=line; target._state.task_state='aborted'
    elif target._state._scheduler is not None: target._state._scheduler.continue_task(next(name for name,program in state.execution.tasks.tasks.items() if program is target))
    else:
        try: target.resume()
        except rt().KarelPause: pass
