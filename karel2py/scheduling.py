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
TASK_MASKS={'PG_NP_ERROR':1,'PG_NP_CMD':2,'PG_NP_END':4,'PG_NP_TPENB':8}
TASK_CONSTANTS={**TASK_ATTRIBUTES,**TASK_STATES,**TASK_PROGRAM_TYPES,**TASK_MASKS}
TASK_DYNAMIC={'TSK_LINENUM','TSK_PROGNAME','TSK_PROGTYPE','TSK_ROUTNAME','TSK_STACK','TSK_STATUS','TSK_TIMESLIC'}
TASK_SETTING_RANGES={'TSK_PRIORITY':(1,99),'TSK_TIMESLIC':(1,1000),
    'TSK_NOBUSY':(0,1),'TSK_NOABORT':(0,3),'TSK_NOPAUSE':(0,13),
    'TSK_TRACE':(0,1),'TSK_TRACELEN':(1,10000),'TSK_TPMOTION':(0,1),'TSK_PAUSESFT':(0,1)}
TASK_DIRECTIVES={'%PRIORITY':'TSK_PRIORITY','%TIMESLICE':'TSK_TIMESLIC',
    '%NOABORT':'TSK_NOABORT','%NOPAUSE':'TSK_NOPAUSE',
    '%NOBUSYLAMP':'TSK_NOBUSY','%NOPAUSESHFT':'TSK_PAUSESFT','%TPMOTION':'TSK_TPMOTION'}
TASK_FLAG_DIRECTIVES={'%NOBUSYLAMP':1,'%NOPAUSESHFT':0,'%TPMOTION':1}
SOURCE_DIRECTIVES=frozenset(('%DEFGROUP','%LOCKGROUP','%STACKSIZE','%DELAY',
    '%CMOSVARS','%CMOS2SHADOW','%SHADOWVARS','%UNINITVARS','%CRTDEVICE'))
SOURCE_FLAG_DIRECTIVES={'%CMOSVARS','%CMOS2SHADOW','%SHADOWVARS','%UNINITVARS','%CRTDEVICE'}
SOURCE_DIRECTIVE_RANGES={'%DEFGROUP':(1,32),'%STACKSIZE':(1,32767),'%DELAY':(0,86400000)}


def valid_task_setting(attribute,value):
    bounds=TASK_SETTING_RANGES.get(attribute)
    return (type(value) is int and bounds is not None and bounds[0]<=value<=bounds[1]
            and (attribute!='TSK_NOPAUSE' or (value & ~13)==0))


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


def _lineage_registry(root):
    if root._task_parent is not None:
        return root._task_parent[0]
    return root._scheduler or root.execution.tasks


def live_task_parent(registry, child):
    """Resolve a child only within the live parent run that launched it."""
    if child._task_run is None or child._task_parent is None:
        return None
    owner, parent, run = child._task_parent
    if owner is registry and parent._task_run is run:
        return parent
    return None


def paused_task_descendants(root):
    """Capture paused paths in binding order within the root's launch driver."""
    registry = _lineage_registry(root)
    children = {}
    seen = {root}
    for program in registry.tasks.values():
        child = program._state
        if (child in seen or child.task_state != 'paused' or child._scheduler is not root._scheduler
                or child._driving or getattr(program, '_execution', None) is None):
            continue
        parent = live_task_parent(registry, child)
        if parent is not None:
            seen.add(child)
            children.setdefault(parent, []).append(program)
    descendants = list(children.get(root, ()))
    for program in descendants:
        descendants.extend(children.get(program._state, ()))
    return descendants


def mark_task_continued(state):
    state.task_state = 'running'
    state._pause_requested = False
    state._lifecycle['CONTINUE'] += 1


def task_status_name(root):
    state=root.task_state
    if root._abort_requested and state in ('ready','running','paused','waiting'):return 'PG_ABORTING'
    return {'ready':'PG_RUNACCEPT','running':'PG_RUNNING','paused':'PG_PAUSED','waiting':'PG_WAITING',
            'completed':'PG_COMPLETED','stopped':'PG_STOPPED','aborted':'PG_ABORTED','failed':'PG_FAILED'}[state]


def task_attribute(registry,name,program,attribute,line=None):
    runtime=rt();root=runtime.task_root(program._state)
    if attribute == 'TSK_TPMOTION' and root._task_pendant_motion:
        return 1
    if attribute in root._task_settings: return root._task_settings[attribute]
    active=root._task_frames[-1] if root._task_frames else (root,'')
    if attribute=='TSK_STATUS': return TASK_STATES[task_status_name(root)]
    if attribute=='TSK_PROGTYPE': return TASK_PROGRAM_TYPES['PG_AR_KAREL' if root._has_run else 'PG_NOT_EXEC']
    if attribute=='TSK_PROGNAME': return active[0].program_name
    if attribute=='TSK_ROUTNAME': return active[1]
    if attribute=='TSK_LINENUM': return root._task_line
    if attribute=='TSK_STACK': return len(root._task_frames)
    if attribute=='TSK_TIMESLIC': return getattr(root._scheduler or registry,'quantum_us',0)//1000
    if attribute in ('TSK_LOCKGRP', 'TSK_MCTL') and root.execution.group_locks is not None:
        bank = root.execution.group_locks
        mask = sum(1 << (group - 1) for group in bank.groups if bank.owners.get(group) is root)
        # All 31 bits would be the reserved MAXINT storage marker.
        return None if mask == 2147483647 else mask
    value=getattr(registry,'attributes',{}).get(name,{}).get(attribute)
    if attribute in ('TSK_PARENT', 'TSK_NUMCLDS'):
        driver = registry if isinstance(registry, TaskScheduler) else None
        if (root._task_run is not None and root._scheduler is driver
                and _lineage_registry(root) is registry):
            if attribute == 'TSK_PARENT':
                parent = live_task_parent(registry, root)
                if parent is not None:
                    return next((index for index, item in enumerate(registry.tasks.values(), 1)
                                 if runtime.task_root(item._state) is parent), 0)
                return 0
            children = {runtime.task_root(item._state) for item in registry.tasks.values()}
            return sum(live_task_parent(registry, child) is root for child in children)
        return 0 if value is None else runtime.integer(value, line)
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


def select_task(registry,name,caller=None,line=None):
    name=rt().ascii_string(name,line).upper()
    if not name:
        if caller is None: return 3,None
        root=rt().task_root(caller)
        matches=[key for key,program in registry.tasks.items() if program._state is root]
        if len(matches)!=1: return 3,None
        name=matches[0]
    return (0,name) if name in registry.tasks else (1,None)


def selected_task_root(registry,name,caller=None,line=None):
    status,name=select_task(registry,name,caller,line)
    if status:return status,None
    root=rt().task_root(registry.tasks[name]._state)
    if root._scheduler is not None and root._scheduler is not registry:return 3,None
    return 0,root


def set_task_attribute(registry,name,attribute,value,*,caller=None,line=None):
    """Apply explicit portable policies to the bound task; never drive it."""
    runtime=rt();name=runtime.ascii_string(name,line)
    if type(attribute) is str: key=runtime.ascii_string(attribute,line).upper()
    else:
        attribute=runtime.integer(attribute,line)
        key=next((key for key,number in TASK_ATTRIBUTES.items() if number==attribute),None)
    value=runtime.integer(value,line)
    if key not in TASK_ATTRIBUTES: return 2
    if key not in TASK_SETTING_RANGES: return 3
    if not valid_task_setting(key,value): return 2
    status,root=selected_task_root(registry,name,caller,line)
    if status: return status
    root._task_settings[key]=value
    if key=='TSK_TPMOTION': root._task_pendant_motion=False
    if key=='TSK_TRACE' and value: root._task_settings.setdefault('TSK_TRACELEN',1000)
    if key=='TSK_TRACELEN': del root._task_trace[:-value]
    return 0


def kcl_task_admin(state,operation,args,line=None):
    from .extended import condition_control
    from .fileops import write_json_lines

    registry=state.execution.tasks
    name=args[0]
    if operation=='TASK_SETTING':
        code=set_task_attribute(registry,*args,caller=state,line=line)
        return {0:0,1:3,2:4,3:3}[code]
    if name or operation=='SHOW_TRACE':
        status,root=selected_task_root(registry,name,state,line)
        if status:return 3
    else:
        root=rt().task_root(state)
    if operation=='SHOW_TRACE':
        write_json_lines(state,tuple(root._task_trace),line)
        return 0
    if root.task_state not in ('running','paused','waiting'):return 3
    number=args[1]
    if number is not None and not 1<=number<=1000:return 4
    handlers={key:handler for key,handler in root._handlers.items() if handler.get('local_frame') is None}
    if number is not None and number not in handlers:return 3
    if operation=='SHOW_CONDITION':
        keys=sorted(handlers) if number is None else [number]
        rows=[dict(number=key,enabled=handlers[key]['enabled'],priority=handlers[key]['priority'],
                   scan_ms=handlers[key]['scan_ms']) for key in keys]
        write_json_lines(state,rows,line)
    else:
        condition_control(root,operation,number,line)
    return 0


def configure_task(state,directives):
    settings=dict(default_group=state.robot_group or 1,lock_groups=None,storage='DRAM',
        cmos_to_shadow=False,uninitialized_variables=True,default_io_device='TPDISPLAY',
        periodic_delay_ms=8,stack_words=300)
    values=dict(directives)
    if '%DEFGROUP' in values:
        state.robot_group=values['%DEFGROUP'];settings['default_group']=state.robot_group
    if '%LOCKGROUP' in values: settings['lock_groups']=values['%LOCKGROUP']
    elif '%NOLOCKGROUP' in values: settings['lock_groups']=()
    if '%CMOSVARS' in values: settings['storage']='CMOS'
    if '%CMOS2SHADOW' in values:
        settings['cmos_to_shadow']=True
        if settings['storage']=='CMOS': settings['storage']='SHADOW'
    if '%SHADOWVARS' in values: settings['storage']='SHADOW'
    if '%CRTDEVICE' in values: settings['default_io_device']='CRT/KB'
    if '%DELAY' in values: settings['periodic_delay_ms']=values['%DELAY']
    if '%STACKSIZE' in values: settings['stack_words']=values['%STACKSIZE']
    state._source_settings=settings
    for name,value in directives:
        if name not in TASK_DIRECTIVES: continue
        key=TASK_DIRECTIVES[name];value=TASK_FLAG_DIRECTIVES.get(name,value)
        if not valid_task_setting(key,value): raise ValueError('Invalid translated task directive')
        state._task_settings[key]=value


def record_task_trace(state,line=None):
    root=rt().task_root(state)
    if not root._task_settings.get('TSK_TRACE',0): return
    root._task_trace_sequence+=1
    routine=root._task_frames[-1][1] if root._task_frames else ''
    root._task_trace.append(dict(sequence=root._task_trace_sequence,program=state.program_name,routine=routine,line=line))
    limit=root._task_settings.get('TSK_TRACELEN',1000)
    del root._task_trace[:-limit]


def task_request_suppressed(target,action,origin):
    settings=rt().task_root(target)._task_settings
    if action=='ABORT':
        bit={'command':TASK_MASKS['PG_NP_CMD'],'error':TASK_MASKS['PG_NP_ERROR']}.get(origin,0)
        return bool(settings.get('TSK_NOABORT',0)&bit)
    if origin=='shift': return settings.get('TSK_PAUSESFT',1)==0
    bit={'command':TASK_MASKS['PG_NP_END'],'error':TASK_MASKS['PG_NP_ERROR'],
         'tpenable':TASK_MASKS['PG_NP_TPENB']}[origin]
    return bool(settings.get('TSK_NOPAUSE',0)&bit)


def rename_task(registry,old_name,new_name,*,caller=None,line=None):
    """Rename one binding in place without changing its numeric slot or Program."""
    runtime=rt()
    old_name=runtime.ascii_string(old_name,line).upper()
    new_name=runtime.ascii_string(new_name,line).upper()
    if not new_name or len(new_name)>254: return 2
    status,old_name=select_task(registry,old_name,caller,line)
    if status: return status
    if old_name==new_name: return 0
    program=registry.tasks[old_name]
    # A second registry cannot change an active scheduler's identity by alias.
    owner=program._state._scheduler
    if owner is not None and owner is not registry: return 3
    mappings=[registry.tasks,registry.attributes]
    if isinstance(registry,TaskScheduler): mappings.extend((registry.waiting,registry.errors))
    if any(new_name in mapping for mapping in mappings): return 2
    for mapping in mappings:
        if old_name in mapping:
            rows=[(new_name if name==old_name else name,value) for name,value in mapping.items()]
            mapping.clear();mapping.update(rows)
    batch=getattr(registry,'_step_names',None)
    if batch is not None:
        batch[:]=[new_name if name==old_name else name for name in batch]
    return 0


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
    """Cooperative priority/weighted rounds with a deterministic virtual clock."""
    def __init__(self,*,quantum_ms=1,max_steps=100000):
        if type(quantum_ms) is not int or not 1<=quantum_ms<=1000: raise ValueError('Scheduler quantum must be in 1..1000 ms')
        if type(max_steps) is not int or max_steps<1: raise ValueError('Task step budget must be positive')
        self.tasks={}; self.attributes={}; self.quantum_us=quantum_ms*1000; self.max_steps=max_steps
        self.now_us=0; self.waiting={}; self.errors={}; self._running=False; self._step_names=None
    def bind(self, name, program, *, attributes=None):
        key = rt().ascii_string(name).upper()
        previous = self.tasks.get(key)
        replacing = previous is not None and previous is not program
        if replacing and (self._step_names is not None or previous._state._scheduler is self
                          or getattr(getattr(program, '_state', None), '_scheduler', None) is self):
            raise rt().KarelRuntimeError('Cannot replace a scheduler binding during a live run or round')
        bind_task(self, key, program, attributes)
        if replacing:
            self.waiting.pop(key, None)
            self.errors.pop(key, None)

    def _distinct_bindings(self):
        """Use the first binding as the scheduling slot for each Program."""
        seen = set()
        for name, program in self.tasks.items():
            identity = id(program)
            if identity not in seen:
                seen.add(identity)
                yield name, program

    def _primary_name(self, program):
        return next(name for name, item in self.tasks.items() if item is program)

    def rename(self,old_name,new_name): return rename_task(self,old_name,new_name)
    def set_attribute(self,name,attribute,value): return set_task_attribute(self,name,attribute,value)
    def start(self,name,*,paused=False):
        name=name.upper()
        if name not in self.tasks: raise KeyError(name)
        program=self.tasks[name]; state=program._state
        name = self._primary_name(program)
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
        program = self.tasks[name.upper()]
        state = program._state
        if state.task_state != 'paused':
            raise rt().KarelRuntimeError('Only a paused task can continue')
        if state._scheduler is not self or getattr(program, '_execution', None) is None:
            raise rt().KarelRuntimeError('Only the owning TaskScheduler can continue a live paused task')
        descendants = paused_task_descendants(state)
        mark_task_continued(state)
        for child in descendants:
            mark_task_continued(child._state)
        if powerup:
            state._lifecycle['POWERUP'] = state._lifecycle.get('POWERUP', 0) + 1
    def powerup(self,name): self.continue_task(name,powerup=True)
    def _pulse_banks(self):
        # A completed task can leave a NOWAIT pulse on this clock after
        # the same Program starts again under another scheduler.
        return {program._state.execution.ports for program in self.tasks.values()
                if program._state.execution.ports is not None}
    def _pulse_deadlines(self):
        return [pulse.deadline for bank in self._pulse_banks() for pulse in bank._pulses.values() if pulse.scheduler is self]
    def _poll_motion(self):
        runtime=rt()
        for name,program in list(self._distinct_bindings()):
            state=program._state;bank=state.execution.motion
            if bank is None or state._scheduler is not self or runtime.task_root(state) is not state:continue
            try:bank.poll(state)
            except BaseException as error:
                name=self._primary_name(program)
                if getattr(program,'_execution',None) is not None:program._execution.close();program._execution=None
                state.task_state='stopped' if isinstance(error,runtime.KarelStop) else 'aborted' if isinstance(error,runtime.KarelAbort) else 'failed'
                state._scheduler=None;state.finish_teach_programs();self.waiting.pop(name,None)
                if state._scheduler_clock:state._clock_us=None;state._scheduler_clock=False
                self.errors[name]=error;raise
    def _motion_deadlines(self):
        banks={program._state.execution.motion for program in self.tasks.values() if program._state.execution.motion is not None}
        return [deadline for bank in banks for deadline in bank.deadlines(self)]
    def stop(self, name):
        program = self.tasks[name.upper()]
        owner = program._state._scheduler
        if owner is not self and (owner is not None or getattr(program, '_execution', None) is not None):
            raise rt().KarelRuntimeError('Only the owning TaskScheduler can stop a live task')
        program.stop()
        self.waiting.pop(self._primary_name(program), None)
    def step(self):
        runtime=rt(); progressed=False
        if self._step_names is not None: raise runtime.KarelRuntimeError('Scheduler cannot be stepped recursively')
        self._poll_motion()
        for bank in self._pulse_banks(): bank.poll_pulses()
        names = sorted((name for name, _ in self._distinct_bindings()),
                       key=lambda name: runtime.task_root(self.tasks[name]._state)._task_settings.get('TSK_PRIORITY', 50))
        self._step_names=names
        try:
            for slot in range(len(names)):
                name=names[slot]; program=self.tasks[name]
                state=program._state
                if state._scheduler is not self:
                    continue
                if state.task_state=='waiting':
                    deadline=self.waiting.get(name,0)
                    if self.now_us<deadline and not state._pause_requested and not state._abort_requested: continue
                    state.task_state='running'; self.waiting.pop(name,None)
                if state.task_state!='running' or getattr(program,'_execution',None) is None: continue
                duration=state._task_settings.get('TSK_TIMESLIC',self.quantum_us//1000)
                turns=max(1,(duration*1000+self.quantum_us-1)//self.quantum_us)
                for _ in range(turns):
                    progressed=True; state._driving=True
                    try:
                        with runtime._numeric_scope('pythonic'): event=next(program._execution)
                        name=names[slot]
                        if type(event) is not dict: raise runtime.KarelRuntimeError('Invalid scheduler event')
                        if event['kind']=='pause': state.task_state='paused'
                        elif event['kind']=='sleep': self.waiting[name]=event['until']; state.task_state='waiting'
                        elif event['kind']!='timeslice': raise runtime.KarelRuntimeError('Unknown scheduler event')
                    except StopIteration:
                        program._execution=None; state.task_state='completed'; state._scheduler=None
                        state.finish_teach_programs()
                        if getattr(state,'_scheduler_clock',False): state._clock_us=None; state._scheduler_clock=False
                    except BaseException as exc:
                        if getattr(program,'_execution',None) is not None: program._execution.close(); program._execution=None
                        state.task_state='stopped' if isinstance(exc,runtime.KarelStop) else 'aborted' if isinstance(exc,runtime.KarelAbort) else 'failed'
                        state._scheduler=None
                        state.finish_teach_programs()
                        if state._scheduler_clock: state._clock_us=None; state._scheduler_clock=False
                        self.errors[names[slot]]=exc; raise
                    finally: state._driving=False
                    if state.task_state!='running' or program._execution is None: break
        finally: self._step_names=None
        self.now_us+=self.quantum_us
        deadlines=[*self.waiting.values(),*self._pulse_deadlines(),*self._motion_deadlines()]
        if not progressed and deadlines: self.now_us=max(self.now_us,min(deadlines))
        for bank in self._pulse_banks(): bank.poll_pulses()
        self._poll_motion()
        return progressed
    def run(self,*,max_cycles=100000):
        if self._running: raise rt().KarelRuntimeError('Scheduler cannot be driven recursively')
        if type(max_cycles) is not int or max_cycles<1: raise ValueError('Scheduler cycle budget must be positive')
        self._running=True
        try:
            for _ in range(max_cycles):
                for bank in self._pulse_banks(): bank.poll_pulses()
                active = any(program._state._scheduler is self and program._state.task_state in ('running', 'waiting')
                             for _, program in self._distinct_bindings())
                if not active and not self._pulse_deadlines():
                    return self.snapshot()
                self.step()
            raise rt().KarelRuntimeError('Scheduler cycle budget exceeded')
        finally: self._running=False
    def snapshot(self):
        return {name:{'state':program._state.task_state,'values':program.snapshot()} for name,program in self.tasks.items()}


def drive_registered_task(registry, name, task, *, continuing, pause_on_entry=False, line=None):
    """Use the registered task's scheduler or its standalone continuation."""
    runtime = rt()
    if hasattr(registry, 'start'):
        if continuing:
            registry.continue_task(name)
        else:
            registry.start(name, paused=pause_on_entry)
        return
    try:
        if continuing:
            task.resume()
        elif pause_on_entry:
            target = task._state
            if target._driving or getattr(task, '_execution', None) is not None:
                raise runtime.KarelRuntimeError('Task is already active', line)
            before = target.task_state
            prior_pause = target._pause_requested
            target._pause_requested = True
            try:
                task.run()
            except BaseException:
                # Admission may fail before a continuation or body exists.
                if target.task_state == before and getattr(task, '_execution', None) is None:
                    target._pause_requested = prior_pause
                raise
        else:
            task.run()
    except (runtime.KarelPause, runtime.KarelAbort, runtime.KarelStop):
        pass


def run_registered_task(registry, caller, operation, args, line=None):
    """Drive an explicitly registered root, preserving an existing continuation."""
    runtime = rt()
    name = runtime.ascii_string(args[0], line).upper()
    status = args[-1]
    task = registry.tasks.get(name)
    if task is None:
        status.set(1, line)
        return
    target = task._state
    parent = runtime.task_root(caller)
    if target is parent:
        raise runtime.KarelRuntimeError('A task cannot synchronously drive itself', line)

    pause_on_entry = False
    transferred = None
    if operation == 'RUN_TASK':
        if runtime.integer(args[1], line) < 0:
            raise runtime.KarelRuntimeError('Offline RUN_TASK requires a nonnegative line hint', line)
        pause_on_entry = runtime.boolean(args[2], line)
        tp_motion = runtime.boolean(args[3], line)
        mask = runtime.integer(args[4], line)
        if tp_motion:
            bank = parent.execution.group_locks
            if bank is None:
                raise runtime.KarelRuntimeError('Offline RUN_TASK requires no motion without an explicit GroupLocks bank', line)
            if parent.execution is not target.execution or target is not runtime.task_root(target):
                raise runtime.KarelRuntimeError('RUN_TASK pendant motion requires separate roots in a shared execution context', line)
            transferred = bank.pendant_launch_groups(mask, line)
        elif mask != 0:
            raise runtime.KarelRuntimeError('RUN_TASK requires lock mask 0 when tp_motion is FALSE', line)
    continuing = operation == 'CONT_TASK' or target.task_state == 'paused'
    previous_launch = target._task_launch
    if not continuing:
        driver = registry if isinstance(registry, TaskScheduler) else None
        lineage = (
            (registry, parent, parent._task_run)
            if (parent._task_run is not None and parent._scheduler is driver
                and _lineage_registry(parent) is registry) else None
        )
        if transferred is not None and lineage is None:
            raise runtime.KarelRuntimeError('RUN_TASK pendant motion requires a live parent in the launch driver', line)
        target._task_launch = (lineage, transferred, line) if lineage is not None else None
    try:
        drive_registered_task(registry, name, task, continuing=continuing, pause_on_entry=pause_on_entry, line=line)
    finally:
        if not continuing:
            target._task_launch = previous_launch
    status.set(0, line)


def control_task(state,action,number,line=None):
    number=rt().integer(number,line); tasks=list(state.execution.tasks.tasks.values())
    if not 1<=number<=len(tasks): raise rt().KarelRuntimeError('Task number is not registered',line)
    target=tasks[number-1]
    if target._state is rt().task_root(state):
        if action in ('PAUSE','ABORT'):
            rt().request_task_control(target._state,action,line)
            yield from rt().checkpoint(state,line,force_pause=action=='PAUSE')
        else:
            state._pause_requested=False; state._lifecycle['CONTINUE']+=1
            yield from rt().checkpoint(state,line)
        return
    if action in ('PAUSE','ABORT'): rt().request_task_control(target._state,action,line)
    elif target._state._scheduler is not None:
        scheduler = target._state._scheduler
        if scheduler is not state.execution.tasks:
            raise rt().KarelRuntimeError('Only the owning TaskScheduler can continue a live paused task', line)
        scheduler.continue_task(scheduler._primary_name(target))
    else:
        try: target.resume()
        except (rt().KarelPause,rt().KarelAbort,rt().KarelStop): pass
