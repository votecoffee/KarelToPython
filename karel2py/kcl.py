"""An explicit KCL channel for scripted replies and opt-in offline commands."""
from copy import deepcopy
import math
import re


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


def task_command(command):
    """Recognize only an explicit task selector and the supported FORCE suffix."""
    fields = command.upper().split()
    if len(fields) not in (2, 3):
        return None
    action, name = fields[:2]
    if action == 'CONT':
        action = 'CONTINUE'
    if action not in ('RUN', 'CONTINUE', 'PAUSE', 'ABORT') or not re.fullmatch(r'[A-Z][A-Z0-9_]*', name):
        return None
    force = len(fields) == 3
    if force and (action not in ('PAUSE', 'ABORT') or fields[2] != 'FORCE'):
        return None
    if action == 'RUN' and name == 'ALL':
        return None
    return action, name, force


def task_admin_command(command):
    from .dynamic import IDENTIFIER

    command=command.upper()
    setting=re.fullmatch(rf'SET +TASK +(?:\[ *({IDENTIFIER}) *\] +)?(PRIORITY|TRACELEN) *= *([+-]?[0-9]+)',command)
    if setting:
        return 'TASK_SETTING',(setting[1] or '', 'TSK_'+setting[2], int(setting[3]))
    trace=re.fullmatch(rf'SET +TRACE +(ON|OFF)(?: +\[ *({IDENTIFIER}) *\])?',command)
    if trace:
        return 'TASK_SETTING',(trace[2] or '', 'TSK_TRACE', int(trace[1]=='ON'))
    show_trace=re.fullmatch(rf'SHOW +TRACE(?: +({IDENTIFIER}))?',command)
    if show_trace:
        return 'SHOW_TRACE',(show_trace[1] or '',)
    change=re.fullmatch(rf'(ENABLE|DISABLE) +COND(?:ITION)? +(?:({IDENTIFIER}) +)?([0-9]+)',command)
    if change:
        return change[1],(change[2] or '', int(change[3]))
    show=re.fullmatch(rf'SHOW +COND(?:ITION)?(?: +({IDENTIFIER}))?(?: +([0-9]+))?',command)
    if show:
        return 'SHOW_CONDITION',(show[1] or '', int(show[2]) if show[2] is not None else None)
    return None


def file_command(command):
    """Capture keywords separately from case-sensitive file operands."""
    action, *args = command.split()
    action = action.upper()
    explicit_file = bool(args and args[0].upper() == 'FILE')
    if action in ('COPY', 'MOVE', 'APPEND', 'DELETE', 'RENAME') and explicit_file:
        args = args[1:]
    if action in ('COPY', 'RENAME', 'APPEND'):
        if action != 'COPY' and not explicit_file:
            return None
        overwrite = action == 'COPY' and len(args) == 4 and args[-1].upper() == 'OVERWRITE'
        if overwrite:
            args = args[:-1]
        if len(args) != 3 or args[1].upper() != 'TO':
            return None
        source, _, target = args
        if action == 'COPY':
            return 'COPY_FILE', (source, target, overwrite, False)
        if action == 'RENAME':
            return 'RENAME_FILE', (source, target, False)
        return 'APPEND_FILE', (source, target)
    if action == 'DELETE' and explicit_file:
        if len(args) == 1 or len(args) == 2 and args[1].upper() == 'YES':
            return 'DELETE_FILE', (args[0], False)
    if len(args) == 1:
        if action in ('MOVE', 'PRINT'):
            return action + '_FILE', tuple(args)
        if action == 'DIRECTORY':
            return action, tuple(args)
    return None


def variable_command(command):
    from .dynamic import IDENTIFIER

    text = command
    command = command.upper()
    selected = rf'(?:\[({IDENTIFIER})\] *)?({IDENTIFIER})'
    create = re.fullmatch(
        rf'CREATE +VAR(?:IABLE)? +{selected}(?: +IN +(CMOS|DRAM))? *: *'
        rf'(?:ARRAY *\[ *([0-9]+(?: *, *[0-9]+){{0,2}}) *\] +OF +)?'
        rf'({IDENTIFIER}(?: *\[ *[0-9]+ *\])?)', command)
    if create:
        program, name, pool, shape, kind = create.groups()
        sizes = tuple(reversed([int(size) for size in shape.split(',')])) if shape else ()
        return 'CREATE_VAR', (program or '', name, pool, sizes, kind.replace(' ', ''))
    rename = re.fullmatch(rf'RENAME +VAR(?:IABLE)? +{selected} +({IDENTIFIER})', command)
    if rename:
        program, old, new = rename.groups()
        return 'RENAME_VAR', (program or '', old, new)
    namespace = re.fullmatch(rf'RENAME +VARS +({IDENTIFIER}) +({IDENTIFIER})', command)
    if namespace:
        return 'RENAME_VARS', namespace.groups()
    delete = re.fullmatch(rf'DELETE +VAR(?:IABLE)? +{selected}', command)
    if delete:
        program, name = delete.groups()
        return 'DELETE_VAR', (program or '', name)
    clear = re.fullmatch(rf'CLEAR +VARS +({IDENTIFIER})(?: +Y(?:ES)?)?', command)
    if clear:
        return 'CLEAR_VARS', (clear[1], None)
    suffix = rf'(?:\.{IDENTIFIER}|\[ *[0-9]+(?: *, *[0-9]+)* *\])*'
    assignment = re.fullmatch(rf'SET +VAR(?:IABLE)? +{selected}({suffix}) *= *(.+)', text, re.IGNORECASE)
    if assignment:
        program, name, rest, literal = assignment.groups()
        return 'SET_VAR', ((program or '').upper(), (name+rest.replace(' ','')).upper(), literal)
    show = re.fullmatch(rf'SHOW +VAR(?:IABLE)? +{selected}({suffix})(?: +(HEX(?:ADECIMAL)?|BINARY))?', command)
    if show:
        program, name, rest, radix = show.groups()
        return 'SHOW_VAR', (program or '', name+rest.replace(' ',''), radix)
    fields = command.split()
    if fields[:2] == ['SHOW', 'VARS']:
        options = fields[2:]
        values = bool(options and options[-1] == 'VALUES')
        if values:options.pop()
        if not options or len(options) == 1 and re.fullmatch(IDENTIFIER,options[0]):
            return 'SHOW_VARS', (options[0] if options else '', values)
        return None
    save = re.fullmatch(rf'SAVE +VARS +([^ =]+)(?: *= *({IDENTIFIER}))?', text, re.IGNORECASE)
    if save:
        return 'SAVE_VARS', save.groups()
    load = re.fullmatch(r'LOAD +VARS +([^ =]+)', text, re.IGNORECASE)
    if load:
        return 'LOAD_VARS', (load[1], None)
    node = re.fullmatch(rf'(APPEND|INSERT|DELETE) +NODE +{selected}(?: *\[ *([0-9]+) *\])?', command)
    if node:
        action, program, name, index = node.groups()
        if (action == 'APPEND') == (index is None):
            return action + '_NODE', (program or '', name, int(index) if index is not None else None)
    return None


def device_command(command):
    action, *args = command.split()
    action = action.upper()
    if action == 'SHOW':
        if not args or args[0].upper() != 'DEVICE':
            return None
        args = args[1:]
    if action not in ('MOUNT', 'DISMOUNT', 'FORMAT', 'PURGE', 'SHOW') or not args:
        return None
    if not re.fullmatch(r'[A-Za-z][A-Za-z_0-9]{0,7}:?', args[0]):
        return None
    device = args[0].rstrip(':').upper() + ':'
    if action == 'SHOW':
        return ('SHOW_DEVICE', (device,)) if len(args) == 1 else None
    if action != 'FORMAT':
        return (action + '_DEV', (device,)) if len(args) == 1 else None
    options = args[1:]
    if options and options[-1].upper() in ('YES', 'Y'):
        options.pop()
    if len(options) > 1 or options and any(char in options[0] for char in "\"'"):
        return None
    return 'FORMAT_DEV', (device, options[0] if options else '', False)


def dictionary_command(command):
    fields = command.split()
    upper = [field.upper() for field in fields]
    if len(upper) == 2 and upper[0] == 'SHOW' and upper[1] in ('LANG','LANGS','DICTS'):
        return 'SHOW_'+upper[1], ()
    if len(upper) == 3 and upper[:2] in (['SET','LANG'],['SET','LANGUAGE']):
        if re.fullmatch(r'[A-Z][A-Z_0-9]{0,15}',upper[2]):
            return 'SET_LANGUAGE', (upper[2],)
        return None
    if len(fields) < 2 or fields[1].upper() != 'DICT':
        return None
    action = fields[0].upper()
    args = fields[2:]
    if action == 'LOAD' and len(args) in (2, 3):
        from .dictionaries import DICTIONARY_CONSTANTS
        source, name = args[:2]
        language = args[2] if len(args) == 3 else 'DEFAULT'
        return 'ADD_DICT', (source, name, language, DICTIONARY_CONSTANTS['DP_DRAM'])
    if action == 'CLEAR' and len(args) in (1, 2):
        language = args[1] if len(args) == 2 else 'DEFAULT'
        return 'REMOVE_DICT', (args[0], '' if language.upper() == 'ALL' else language)
    return None


def program_command(command):
    from .dynamic import IDENTIFIER

    save = re.fullmatch(rf'SAVE +TP +([^ =]+)(?: *= *({IDENTIFIER}))?', command, re.IGNORECASE)
    if save:
        return 'SAVE_TP', save.groups()
    load = re.fullmatch(r'LOAD +TP +([^ =]+)(?: +(OVERWRITE))?', command, re.IGNORECASE)
    if load:
        return 'LOAD_TP', (load[1], load[2] is not None)
    clear = re.fullmatch(rf'CLEAR +PROG(?:RAM)? +({IDENTIFIER})(?: +Y(?:ES)?)?', command, re.IGNORECASE)
    if clear:
        return 'CLEAR_PROGRAM', (clear[1],)
    translate = re.fullmatch(r'TRANSLATE +([^ =]+)(?: +(LIST))?', command, re.IGNORECASE)
    if translate:
        return 'TRANSLATE', (translate[1], translate[2] is not None)
    fields = command.upper().split()
    if fields == ['SHOW', 'PROGRAMS']:
        return 'SHOW_PROGRAMS', ()
    if fields == ['SHOW', 'TASKS']:
        return 'SHOW_TASKS', (None,)
    if len(fields) == 3 and fields[:2] == ['SHOW', 'TASK'] and re.fullmatch(r'[A-Z][A-Z0-9_]*', fields[2]):
        return 'SHOW_TASKS', (fields[2],)
    return None


def environment_command(command):
    command=command.upper()
    if re.fullmatch(r'SHOW +CURPOS',command):
        return 'SHOW_CURPOS',()
    if re.fullmatch(r'SHOW +CLOCK',command):
        return 'SHOW_CLOCK',()
    clock=re.fullmatch(r"SET +CLOCK +'([0-9]{2})-([A-Z]{3})-([0-9]{2}) ([0-9]{2}:[0-9]{2})'",command)
    if clock:
        return 'SET_CLOCK',clock.groups()
    if re.fullmatch(r'UNSIM(?:ULATE)? +ALL',command):
        return 'UNSIM_ALL',()
    port=r'(DIN|DOUT|AIN|AOUT|GIN|GOUT) *\[ *([0-9]+) *\]'
    simulation=re.fullmatch(rf'(SIM(?:ULATE)?|UNSIM(?:ULATE)?) +{port}(?: *= *([^ =]+))?',command)
    if simulation:
        action,kind,number,value=simulation.groups()
        if action.startswith('UNSIM'):
            return ('UNSIMULATE',(kind,int(number),None)) if value is None else None
        return 'SIMULATE',(kind,int(number),value)
    outputs=r'(DIN|DOUT|RDO|OPOUT|TPOUT|AIN|AOUT|GIN|GOUT) *\[ *([0-9]+) *\]'
    set_port=re.fullmatch(rf'SET +PORT +{outputs} *= *([^ =]+)',command)
    if set_port:
        return 'SET_PORT',(set_port[1],int(set_port[2]),set_port[3])
    return None


class KclCommands:
    """Single accepted-command channel with configured replies and bounded history."""
    def __init__(self,replies=None,*,limit=500,history=None,sequence=0,last_status=None,
                 task_commands=False,file_commands=False,variable_commands=False,
                 device_commands=False,dictionary_commands=False,program_commands=False,
                 environment_commands=False):
        if replies is None:replies={}
        if type(replies) is not dict or len(replies)>256:raise ValueError('KCL requires at most 256 configured replies')
        if type(limit) is not int or not 1<=limit<=4096:raise ValueError('KCL history limit requires 1..4096')
        if type(sequence) is not int or not 0<=sequence<=2147483646:raise ValueError('KCL sequence is out of range')
        if type(task_commands) is not bool:raise ValueError('KCL task_commands requires a BOOLEAN')
        if type(file_commands) is not bool:raise ValueError('KCL file_commands requires a BOOLEAN')
        if type(variable_commands) is not bool:raise ValueError('KCL variable_commands requires a BOOLEAN')
        if type(device_commands) is not bool:raise ValueError('KCL device_commands requires a BOOLEAN')
        if type(dictionary_commands) is not bool:raise ValueError('KCL dictionary_commands requires a BOOLEAN')
        if type(program_commands) is not bool:raise ValueError('KCL program_commands requires a BOOLEAN')
        if type(environment_commands) is not bool:raise ValueError('KCL environment_commands requires a BOOLEAN')
        self.replies={};self.limit=limit;self.history=[];self.sequence=sequence
        self.task_commands=task_commands
        self.file_commands=file_commands
        self.variable_commands=variable_commands
        self.device_commands=device_commands
        self.dictionary_commands=dictionary_commands
        self.program_commands=program_commands
        self.environment_commands=environment_commands
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
        if job is not None and job['clock'] is not None and job['clock']()>=job['due']:self.complete(job)

    def _record(self,state,name,command,phase,code):
        self.sequence+=1
        row=dict(sequence=self.sequence,program=rt().task_root(state).program_name,operation=name,command=command,phase=phase,status=code)
        self.history.append(row);del self.history[:-self.limit]
        return row

    def _dispatch(self,state,name,command,operation):
        """Hold the channel busy during a supported inline command."""
        row=self._record(state,name,command,'pending',0)
        job=dict(row=row,status=4,clock=None,delay_ms=0)
        self._pending=job
        try:
            job['status']=operation(job)
        except rt().KarelRuntimeError:
            # The accepted command encountered an offline operation error.
            pass
        finally:
            self.complete(job)
        return 0,job

    def _task_targets(self,state,registry,owner,action,selector):
        from .control import broadcast_task_targets, task_control_eligible, task_root
        from .scheduling import live_task_parent

        if selector == 'ALL':
            targets = broadcast_task_targets(registry, action)
            if action == 'CONTINUE':
                # Resume paused parents first through their normal cascade.
                paused = set(targets)
                targets = tuple(root for root in targets if live_task_parent(registry, root) not in paused)
            return targets
        program = registry.tasks.get(selector)
        if program is None:
            return None
        target = task_root(program._state)
        if action in ('PAUSE', 'ABORT'):
            return (target,) if task_control_eligible(target, owner, action) else None
        if target is not program._state or target is task_root(state) or target._driving:
            return None
        if target.task_state == 'paused':
            return (target,) if task_control_eligible(target, owner, 'CONTINUE') else None
        if (action == 'RUN' and getattr(target.program, '_execution', None) is None and target._scheduler is None
                and target.task_state in ('ready', 'completed', 'failed')):
            return (target,)
        return None

    def _submit_task(self,state,name,command,request,line):
        from .control import request_task_control, task_root
        from .scheduling import TaskScheduler, drive_registered_task

        action, selector, force = request
        registry = state.execution.tasks
        owner = registry if isinstance(registry, TaskScheduler) else None
        driving = action in ('RUN', 'CONTINUE')
        targets = self._task_targets(state, registry, owner, action, selector)
        if targets is None or (name == 'KCL_NO_WAIT' and driving and owner is None):
            self._record(state, name, command, 'rejected', 3)
            self.last_status = 3
            return 3, None

        def dispatch(job):
            if driving:
                cohort = [(target, target._task_run, target._lifecycle['CONTINUE']) for target in targets]
                for target, run, continued in cohort:
                    # An earlier target can already have continued this descendant.
                    if (target._task_run is not run or target._lifecycle['CONTINUE'] != continued
                            or action == 'CONTINUE' and target.task_state != 'paused'):
                        continue
                    binding = owner._primary_name(target.program) if owner is not None else selector
                    drive_registered_task(registry, binding, target.program,
                                          continuing=target.task_state == 'paused', line=line)
            else:
                for target in targets:
                    request_task_control(target, action, line, force=force)
                if task_root(state) in targets:
                    job['self_action'] = action
            return 0
        return self._dispatch(state,name,command,dispatch)

    def _submit_file(self,state,name,command,request,line):
        from .fileops import kcl_file_operation

        operation,args=request
        def dispatch(_job):
            code=kcl_file_operation(state,operation,args,line)
            return 100+code if code else 0
        return self._dispatch(state,name,command,dispatch)

    def _submit_task_admin(self,state,name,command,request,line):
        from .scheduling import kcl_task_admin

        operation,args=request
        return self._dispatch(state,name,command,lambda _job:kcl_task_admin(state,operation,args,line))

    def _submit_variable(self,state,name,command,request,line):
        from .dynamic import create, edit_detached_path, remove_detached, rename, set_detached_scalar

        operation,args=request
        def dispatch(_job):
            if operation=='CREATE_VAR':
                program, variable, pool, sizes, kind = args
                if any(size==0 for size in sizes):
                    return 205
                group=rt().task_root(state)._source_settings.get('default_group',1)
                dimensions=(*sizes,*(0,)*(3-len(sizes)))
                code=create(state.execution,state,(program,variable,program,kind,group,*dimensions,-1 if pool=='CMOS' else 0),line)
            elif operation in ('RENAME_VAR','RENAME_VARS'):
                code=rename(state.execution,state,operation,args,line)
            elif operation in ('DELETE_VAR','CLEAR_VARS'):
                code=remove_detached(state,*args,line)
            elif operation=='SET_VAR':
                code=set_detached_scalar(state,*args,line)
            elif operation in ('SAVE_VARS','LOAD_VARS'):
                from .variable_archives import kcl_archive
                code=kcl_archive(state,operation,*args,line)
            elif operation in ('SHOW_VAR','SHOW_VARS'):
                from .inspection import kcl_variable_listing
                code=kcl_variable_listing(state,operation,args,line)
            else:
                code=edit_detached_path(state,operation,*args,line)
            return 200+code if code else 0
        return self._dispatch(state,name,command,dispatch)

    def _submit_device(self,state,name,command,request,line):
        from .devices import manage_device

        operation,args=request
        def dispatch(_job):
            code=manage_device(state,operation,args,line)
            return 300+code if 0<code<100 else code
        return self._dispatch(state,name,command,dispatch)

    def _submit_dictionary(self,state,name,command,request,line):
        from .dictionaries import kcl_catalog

        operation,args=request
        def dispatch(_job):
            if operation in ('ADD_DICT','REMOVE_DICT'):
                code=state.execution.require('dictionaries',line).manage(state,operation,args)
            else:
                code=kcl_catalog(state,operation,args,line)
            return 400+code if 0<code<100 else code
        return self._dispatch(state,name,command,dispatch)

    def _submit_program(self,state,name,command,request,line):
        from .archives import kcl_program_archive
        from .inspection import kcl_program_listing
        from .source_translations import translate_stored_source

        operation,args=request
        def dispatch(_job):
            if operation=='TRANSLATE':
                return translate_stored_source(state.execution,state,*args,line)
            if operation in ('SHOW_PROGRAMS','SHOW_TASKS'):
                code=kcl_program_listing(state,operation,args,line)
            else:
                code=kcl_program_archive(state,operation,args,line)
            return 500+code if code else 0
        return self._dispatch(state,name,command,dispatch)

    def _submit_environment(self,state,name,command,request,line):
        from .clocks import kcl_calendar

        operation,args=request
        def dispatch(_job):
            if operation in ('SET_CLOCK','SHOW_CLOCK'):
                code=kcl_calendar(state,operation,args,line)
            elif operation=='SHOW_CURPOS':
                from .fileops import write_json_lines

                runtime=rt()
                pose=state.execution.invoke(state,'CURPOS',(),line)
                group=runtime.task_root(state).robot_group
                if group is None:group=state.execution.robot.active_group
                write_json_lines(state,[dict(group=group,pose=runtime.snapshot_value(pose))],line)
                code=0
            else:
                bank=state.execution.require('ports',line)
                code=bank.kcl_operation(operation,args,line)
            return 600+code if code else 0
        return self._dispatch(state,name,command,dispatch)

    def submit(self,state,name,command,line=None):
        try:command=command_text(command)
        except ValueError as exc:raise rt().KarelRuntimeError(str(exc),line) from exc
        if self.sequence>=2147483646:raise rt().KarelRuntimeError('KCL request sequence exhausted',line)
        self.poll();reply=self.replies.get(command)
        if self._pending is None and reply is None:
            for enabled,parse,submit in (
                (self.task_commands,task_command,self._submit_task),
                (self.task_commands,task_admin_command,self._submit_task_admin),
                (self.file_commands,file_command,self._submit_file),
                (self.variable_commands,variable_command,self._submit_variable),
                (self.device_commands,device_command,self._submit_device),
                (self.dictionary_commands,dictionary_command,self._submit_dictionary),
                (self.program_commands,program_command,self._submit_program),
                (self.environment_commands,environment_command,self._submit_environment),
            ):
                if enabled:
                    request=parse(command)
                    if request is not None:return submit(state,name,command,request,line)
        phase='busy' if self._pending is not None else 'unsupported' if reply is None else 'rejected' if reply['accept_status'] else 'pending'
        code=2 if phase=='busy' else 1 if phase=='unsupported' else reply['accept_status']
        # Capture the clock only for actual delayed work, before mutating history.
        clock=None;now=0
        if phase=='pending' and reply['delay_ms']:
            scheduler=state._scheduler
            clock=(lambda:scheduler.now_us) if scheduler is not None else (lambda:rt().timer_clock(state,line))
            now=clock()
        row=self._record(state,name,command,phase,code)
        if phase!='pending':
            if self._pending is None:self.last_status=code
            return code,None
        job=dict(row=row,status=reply['status'],clock=clock,due=now+reply['delay_ms']*1000,delay_ms=reply['delay_ms'])
        self._pending=job
        if not reply['delay_ms']:self.complete(job)
        return 0,job

    def wait(self,state,job,line=None):
        if self._pending is job:
            if job['clock'] is None:
                raise rt().KarelRuntimeError('Cannot collect an executing inline KCL command', line)
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
        if job is not None and 'self_action' in job:
            yield from rt().checkpoint(state,line,force_pause=job['self_action']=='PAUSE')

    def snapshot(self):
        result=dict(replies=deepcopy(self.replies),limit=self.limit,history=deepcopy(self.history),sequence=self.sequence,last_status=self.last_status)
        if self.task_commands:result['task_commands']=True
        if self.file_commands:result['file_commands']=True
        if self.variable_commands:result['variable_commands']=True
        if self.device_commands:result['device_commands']=True
        if self.dictionary_commands:result['dictionary_commands']=True
        if self.program_commands:result['program_commands']=True
        if self.environment_commands:result['environment_commands']=True
        if self._pending is not None:
            job=self._pending;result['pending']=dict(sequence=job['row']['sequence'],command=job['row']['command'],status=job['status'],delay_ms=job['delay_ms'])
        return result

    def to_config(self):
        if self._pending is not None:raise ValueError('Cannot persist a pending KCL command; collect KCL_STATUS first')
        return self.snapshot()

    @classmethod
    def from_config(cls,config):
        fields={'replies','limit','history','sequence','last_status','task_commands','file_commands',
                'variable_commands','device_commands','dictionary_commands','program_commands','environment_commands'}
        if type(config) is not dict or set(config)-fields:raise ValueError('Unknown KCL channel fields')
        return cls(**config)
