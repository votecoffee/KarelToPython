"""Offline timed digital outputs; explicit polling, no background threads."""
from dataclasses import dataclass
import time


def rt():
    from . import runtime
    return runtime


@dataclass(eq=False)
class Pulse:
    key: tuple
    owner: object
    clock: object
    scheduler: object
    deadline: int
    previous: int


def sample(clock,line=None):
    try: value=clock()
    except Exception as exc: raise rt().KarelRuntimeError('Pulse clock failed: '+str(exc),line) from exc
    if type(value) is not int or value<0: raise rt().KarelRuntimeError('Pulse clock requires nonnegative INTEGER microseconds',line)
    return value


def terminal(owner):
    return owner._aborted or owner.task_state in ('aborted','stopped','failed')


def poll(bank,line=None):
    if not bank._pulses: return 0
    if bank._polling_pulses: raise rt().KarelRuntimeError('Pulse polling cannot recurse',line)
    bank._polling_pulses=True
    try:
        pending=[]
        for key,pulse in tuple(bank._pulses.items()):
            if terminal(pulse.owner): pending.append((key,pulse,None));continue
            now=sample(pulse.clock,line)
            if now<pulse.previous: raise rt().KarelRuntimeError('Pulse clock moved backwards',line)
            pending.append((key,pulse,now))
        expired=0
        for key,pulse,now in pending:
            if bank._pulses.get(key) is not pulse: continue
            if now is None or terminal(pulse.owner): del bank._pulses[key]
            elif now>=pulse.deadline:
                bank.values[key]=False;del bank._pulses[key];expired+=1
            else: pulse.previous=now
        return expired
    finally: bank._polling_pulses=False


def finish(bank,pulse):
    if pulse is not None and bank._pulses.get(pulse.key) is pulse:
        if not terminal(pulse.owner): bank.values[pulse.key]=False
        del bank._pulses[pulse.key]


def pulse_execution(state,number,milliseconds,nowait=False,line=None):
    runtime=rt()
    if not runtime._pythonic(): raise runtime.KarelRuntimeError('PULSE requires Pythonic mode',line)
    number=runtime.integer(number,line);milliseconds=runtime.integer(milliseconds,line);nowait=runtime.boolean(nowait,line)
    if not 0<=milliseconds<=86400000: raise runtime.KarelRuntimeError('PULSE requires milliseconds in 0..86400000',line)
    bank=state.execution.require('ports',line);key=bank._key('DOUT',number,line)
    row=dict(operation='PULSE',line=line,outcome='requested');state.service_requests.append(row)
    try:
        if not milliseconds: row['outcome']='completed';return
        owner=runtime.task_root(state);scheduler=owner._scheduler
        clock=(lambda:scheduler.now_us) if scheduler is not None else state._clock_us or (lambda:time.monotonic_ns()//1000)
        now=sample(clock,line);bank.poll_pulses(line)
        if owner._aborted: raise runtime.KarelAbort(owner._abort_line)
        if state._aborted: raise runtime.KarelAbort(state._abort_line)
        if key in bank._pulses: raise runtime.KarelRuntimeError('PULSE output already has a pending pulse',line)
        duration=((milliseconds+7)//8)*8
        pulse=Pulse(key,owner,clock,scheduler,now+duration*1000,now)
        bank.values[key]=True;bank._pulses[key]=pulse
        if not nowait:
            yield from runtime.delay_execution(state,duration,line)
            if owner._aborted: raise runtime.KarelAbort(owner._abort_line)
            if state._aborted: raise runtime.KarelAbort(state._abort_line)
            finish(bank,pulse)
    except Exception:
        row['outcome']='failed'
        root=runtime.task_root(state)
        if root._aborted: raise runtime.KarelAbort(root._abort_line)
        if state._aborted: raise runtime.KarelAbort(state._abort_line)
        raise
    row['outcome']='completed'
