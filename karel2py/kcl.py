"""An explicit KCL channel for scripted replies and opt-in offline commands."""
from copy import deepcopy
import math
import re


PROCEDURE_LIMIT=65536
VARIABLE_FILTERS=frozenset((
    'ARRAY','STRUCTURE','INTEGER','SHORT','BYTE','REAL','BOOLEAN','STRING','CONFIG','VECTOR',
    'POSITION','XYZWPR','XYZWPREXT','COMMON_ASSOC','GROUP_ASSOC','FILE','PATH','QUEUE_TYPE',
    'JOINTPOS',*(f'JOINTPOS{width}' for width in range(1,10)),
))
BREAK_ACTIONS=('PAUSE','DISPLAY','TRACE ON','TRACE OFF')


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


def task_command(command,default=None):
    """Recognize only an explicit task selector and the supported FORCE suffix."""
    fields = command.upper().split()
    if len(fields)==1 and default is not None:fields.append(default)
    if len(fields) not in (2, 3):
        return None
    action, name = fields[:2]
    if action == 'CONT':
        action = 'CONTINUE'
    if action == 'HO':
        action = 'HOLD'
    if action not in ('RUN', 'CONTINUE', 'PAUSE', 'ABORT', 'HOLD', 'UNHOLD') or not re.fullmatch(r'[A-Z_][A-Z0-9_]*', name):
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
    if command=='RESET':return 'RESET',()
    setting=re.fullmatch(rf'SET +TASK +(?:\[ *({IDENTIFIER}) *\] +)?(PRIORITY|TRACELEN) *= *([+-]?[0-9]+)',command)
    if setting:
        return 'TASK_SETTING',(setting[1] or '', 'TSK_'+setting[2], int(setting[3]))
    trace=re.fullmatch(rf'SET +TRACE +(ON|OFF)(?: +\[ *({IDENTIFIER}) *\])?',command)
    if trace:
        return 'TASK_SETTING',(trace[2] or '', 'TSK_TRACE', int(trace[1]=='ON'))
    show_trace=re.fullmatch(rf'SHOW +TRACE(?: +({IDENTIFIER}))?',command)
    if show_trace:
        return 'SHOW_TRACE',(show_trace[1] or '',)
    history=re.fullmatch(rf'SHOW +HIST(?:ORY)?(?: +({IDENTIFIER}))?',command)
    if history:
        return 'SHOW_HISTORY',(history[1] or '',)
    change=re.fullmatch(rf'(ENABLE|DISABLE) +COND(?:ITION)? +(?:({IDENTIFIER}) +)?([0-9]+)',command)
    if change:
        return change[1],(change[2] or '', int(change[3]))
    show=re.fullmatch(rf'SHOW +COND(?:ITION)?(?: +({IDENTIFIER}))?(?: +([0-9]+))?',command)
    if show:
        return 'SHOW_CONDITION',(show[1] or '', int(show[2]) if show[2] is not None else None)
    return None


def task_wait_command(command,default=None):
    match=re.fullmatch(r'WAIT +(?:([A-Z_][A-Z0-9_]*) +)?(DONE|PAUSE)',command.upper())
    if match:
        selector=match[1] or default
        if selector is not None and selector!='ALL':
            return selector,match[2]=='PAUSE'
    return None


def file_command(command):
    """Capture keywords separately from case-sensitive file operands."""
    action, *args = command.split()
    action = action.upper()
    if action in ('CHDIR','CD') and len(args)<=1:
        return 'CHDIR',tuple(args)
    if action in ('MKDIR','RMDIR') and len(args)==1:
        return action,tuple(args)
    if action=='TYPE' and len(args)==1:
        return 'PRINT_FILE',tuple(args)
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
    from .dynamic import IDENTIFIER, VARIABLE_SELECTOR, VARIABLE_SUFFIX

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
    suffix = VARIABLE_SUFFIX
    frame = rf'(?: +IN +({IDENTIFIER}))?(?: +FROM +({IDENTIFIER}))?(?: +({IDENTIFIER}))?'
    set_local = re.fullmatch(rf'SET +LOCAL +VAR(?:IABLE)? +({IDENTIFIER}){frame} *= *(.+)',text,re.IGNORECASE)
    if set_local:
        name,routine,module,task,literal=set_local.groups()
        return 'SET_LOCAL_VAR',((task or '').upper(),routine.upper() if routine else None,
                                module.upper() if module else None,name.upper(),literal)
    local = re.fullmatch(rf'SHOW +LOCAL +VAR(?:IABLE)? +({IDENTIFIER}{suffix})(?: +(HEX(?:ADECIMAL)?|BINARY))?{frame}',command)
    if local:
        path, radix, routine, module, task = local.groups()
        return 'SHOW_LOCAL_VAR',(task or '',routine,module,path.replace(' ',''),radix)
    locals_list = re.fullmatch(rf'SHOW +LOCAL +VARS(?: +(VALUES))?{frame}',command)
    if locals_list:
        values, routine, module, task = locals_list.groups()
        return 'SHOW_LOCAL_VARS',(task or '',routine,module,values is not None)
    assignment = re.fullmatch(rf'SET +VAR(?:IABLE)? +{VARIABLE_SELECTOR} *= *(.+)', text, re.IGNORECASE)
    if assignment:
        program, name, rest, literal = assignment.groups()
        return 'SET_VAR', ((program or '').upper(), (name+rest.replace(' ','')).upper(), literal)
    record = re.fullmatch(rf'RECORD +{VARIABLE_SELECTOR}',command)
    if record:
        program, name, rest = record.groups()
        return 'SET_VAR',(program or '',name+rest.replace(' ',''),None)
    show = re.fullmatch(rf'SHOW +VAR(?:IABLE)? +{selected}({suffix})(?: +(HEX(?:ADECIMAL)?|BINARY))?', command)
    if show:
        program, name, rest, radix = show.groups()
        return 'SHOW_VAR', (program or '', name+rest.replace(' ',''), radix)
    fields = command.split()
    if len(fields)>=2 and fields[:2]==['SHOW','SYSTEM']:
        options=fields[2:]
        values=bool(options and options[-1]=='VALUES')
        if values:options.pop()
        if not options or len(options)==1 and options[0] in VARIABLE_FILTERS:
            return 'SHOW_SYSTEM',('',values,options[0] if options else None)
        return None
    if fields==['SHOW','MEMORY']:
        return 'SHOW_MEMORY',('',)
    if len(fields)>=2 and fields[0]=='SHOW' and fields[1] in VARIABLE_FILTERS|{'VARS','TYPES'}:
        kind=fields[1]
        options = fields[2:]
        include = bool(options and options[-1] == ('FIELDS' if kind=='TYPES' else 'VALUES'))
        if include:options.pop()
        if not options or len(options) == 1 and re.fullmatch(IDENTIFIER,options[0]):
            owner=options[0] if options else ''
            if kind=='TYPES':return 'SHOW_TYPES',(owner,include)
            return 'SHOW_VARS',(owner,include,None if kind=='VARS' else kind)
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
        source, name = args[:2]
        language = args[2] if len(args) == 3 else 'DEFAULT'
        return 'LOAD_DICT', (source, name, language)
    if action == 'COMPRESS' and len(args)==1:
        return 'COMPRESS_DICT',tuple(args)
    if action == 'CLEAR' and len(args) in (1, 2):
        language = args[1] if len(args) == 2 else 'DEFAULT'
        return 'REMOVE_DICT', (args[0], '' if language.upper() == 'ALL' else language)
    return None


def program_command(command):
    from .dynamic import IDENTIFIER

    default = re.fullmatch(rf'SET +DEF(?:AULT)? +({IDENTIFIER})',command.upper())
    if default:
        return 'SET_DEFAULT',(default[1],)
    if re.fullmatch(r'SHOW +DEFAULT',command.upper()):
        return 'SHOW_DEFAULT',()
    show = re.fullmatch(rf'SHOW +PROG(?:RAM)?(?: +({IDENTIFIER}))?',command.upper())
    if show:
        return 'SHOW_PROGRAM',(show[1],)

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
    if len(fields) in (2,3) and fields[1]=='ALL' and fields[0] in ('SAVE','LOAD','CLEAR'):
        if fields[0]=='CLEAR':
            return ('CLEAR_ALL',(len(fields)==3,)) if len(fields)==2 or fields[2] in ('Y','YES') else None
        if fields==['LOAD','ALL','CONVERT']:return None
        return fields[0]+'_ALL',(command.split()[2] if len(fields)==3 else None,)
    if fields == ['SHOW', 'BUILTINS']:
        return 'SHOW_BUILTINS', ()
    if fields == ['SHOW', 'PROGRAMS']:
        return 'SHOW_PROGRAMS', ()
    if fields == ['SHOW', 'TASKS']:
        return 'SHOW_TASKS', (None,)
    if len(fields) == 3 and fields[:2] == ['SHOW', 'TASK'] and re.fullmatch(r'[A-Z][A-Z0-9_]*', fields[2]):
        return 'SHOW_TASKS', (fields[2],)
    return None


def environment_command(command):
    command=command.upper()
    group=re.fullmatch(r'SET +GROUP +([0-9]+)',command)
    if group:
        return 'SET_GROUP',(int(group[1]),)
    if re.fullmatch(r'SHOW +GROUP',command):
        return 'SHOW_GROUP',()
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


def procedure_command(command):
    action,*args=command.split()
    if action.upper()=='RUNCF' and len(args) in (1,2):
        return 'RUNCF',tuple(args)
    if action.upper()=='SET' and len(args)==2 and args[0].upper()=='VERIFY':
        setting=args[1].upper()
        if setting in ('ON','OFF'):return 'VERIFY',(setting=='ON',)
    return None


def debug_command(command):
    from .dynamic import IDENTIFIER

    command=command.upper()
    name=rf'(?:({IDENTIFIER}) +)?'
    program=re.fullmatch(rf'SET +BREAK +PROG(?:RAM)? +{name}([0-9]+) +([0-9]+)'
                         r'(?: +(PAUSE|DISPLAY|TRACE +ON|TRACE +OFF))?',command)
    if program:
        selector,number,line,action=program.groups()
        return 'PROGRAM',('SET',selector,int(number),int(line),' '.join((action or 'PAUSE').split()))
    condition=re.fullmatch(rf'SET +BREAK +COND(?:ITION)? +{name}([0-9]+)',command)
    if condition:
        return 'CONDITION',('SET',condition[1],int(condition[2]))
    edit=re.fullmatch(rf'(CLEAR|ENABLE|DISABLE) +BREAK +(PROG(?:RAM)?|COND(?:ITION)?) +'
                      rf'{name}([0-9]+|ALL)',command)
    if edit:
        action,kind,selector,number=edit.groups()
        if action!='CLEAR' and (kind.startswith('COND') or number=='ALL'):return None
        return ('PROGRAM' if kind.startswith('PROG') else 'CONDITION',
                (action,selector,None if number=='ALL' else int(number)))
    show=re.fullmatch(rf'SHOW +BREAK(?: +({IDENTIFIER}))?',command)
    if show:return 'SHOW_BREAK',(show[1],)
    step=re.fullmatch(rf'STEP +ON(?: +({IDENTIFIER}))?',command)
    if step:return 'STEP_ON',(step[1],)
    if re.fullmatch(r'STEP +OFF',command):return 'STEP_OFF',()
    return None


def breakpoint_config(rows,enabled):
    if rows is None:return {}
    if not enabled or type(rows) is not list or len(rows)>256:
        raise ValueError('Program breakpoints require debug_commands and at most 256 rows')
    result={}
    for row in rows:
        if (type(row) is not dict or set(row)!={'program','number','line','action','enabled'}
                or type(row['program']) is not str or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,35}',row['program'])
                or any(type(row[key]) is not int or not 1<=row[key]<=32767 for key in ('number','line'))
                or row['action'] not in BREAK_ACTIONS or type(row['enabled']) is not bool):
            raise ValueError('Invalid program breakpoint')
        key=row['program'],row['number']
        if key in result:raise ValueError('Duplicate program breakpoint')
        result[key]=row.copy()
    return result


class ProcedureError(Exception):
    def __init__(self,status):
        self.status=status


def procedure_line(text):
    """Strip optional prompt and a comment outside quoted operands."""
    text=text.strip().removeprefix('>').lstrip()
    quote=None
    for index,char in enumerate(text):
        if quote:
            if char==quote:quote=None
        elif char in ("'",'"'):
            quote=char
        elif char=='-' and text[index:index+2]=='--' and (not index or text[index-1]==' '):
            return text[:index].rstrip()
    return text


def procedure_plan(state,channel,args,line):
    from .fileops import (kcl_procedure_endpoint,kcl_read_bytes,kcl_procedure_output,
                          kcl_scoped_file)

    def resolve(value,suffix):
        return kcl_procedure_endpoint(state,kcl_scoped_file(state,channel,value,line),suffix,line)

    files,source=resolve(args[0],'.CF')
    commands=[]
    remaining=PROCEDURE_LIMIT
    count=0
    def load(key,active):
        nonlocal remaining,count
        count+=1
        if len(active)>=4 or count>32:raise ProcedureError(705)
        state.tick(line)
        status,data,identity=kcl_read_bytes(files,key,remaining,line)
        if status:raise ProcedureError(700+status)
        if identity in active:raise ProcedureError(706)
        remaining-=len(data)
        text=data.decode('ascii')
        if any(ord(char)<32 and char not in '\r\n' or ord(char)==127 for char in text):
            raise ProcedureError(702)
        for number,physical in enumerate(text.splitlines()):
            if number%256==0:state.tick(line)
            command=procedure_line(physical)
            if not command:continue
            command=command_text(command)
            verb,*parts=command.split()
            if verb.upper()=='RUNCF':raise ProcedureError(706)
            if verb.startswith('%'):
                if verb.upper()!='%INCLUDE' or len(parts)!=1:raise ProcedureError(702)
                include=parts[0]
                if ':' not in include:
                    device,separator,tail=key.partition(':')
                    parent=(tail if separator else device).rpartition('/')[0]
                    include=(device+':' if separator else '')+(parent+'/' if parent else '')+include
                backend,target=kcl_procedure_endpoint(state,include,'.CF',line)
                if backend is not files:raise ProcedureError(704)
                load(target,(*active,identity))
            else:
                if len(commands)>=256:raise ProcedureError(705)
                commands.append(command)

    load(source,())
    listing=None
    if len(args)==2:
        backend,listing=resolve(args[1],'.LS')
        if backend is not files:raise ProcedureError(704)
        status=kcl_procedure_output(files,listing,line)
        if status:raise ProcedureError(status)
    return files,commands,listing


class KclCommands:
    """Single accepted-command channel with configured replies and bounded history."""
    def __init__(self,replies=None,*,limit=500,history=None,sequence=0,last_status=None,
                 task_commands=False,file_commands=False,variable_commands=False,
                 device_commands=False,dictionary_commands=False,program_commands=False,
                 environment_commands=False,working_directory='.',default_program=None,default_group=None,
                 procedure_commands=False,verify=True,debug_commands=False,program_breakpoints=None):
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
        if type(procedure_commands) is not bool:raise ValueError('KCL procedure_commands requires a BOOLEAN')
        if type(debug_commands) is not bool:raise ValueError('KCL debug_commands requires a BOOLEAN')
        if type(verify) is not bool or not verify and not procedure_commands:
            raise ValueError('KCL verify requires a BOOLEAN and procedure_commands to disable verification')
        if default_program is not None:
            if (not program_commands or type(default_program) is not str or default_program=='ALL'
                    or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,35}',default_program)):
                raise ValueError('KCL default_program requires program_commands and a canonical program identifier')
        if default_group is not None and (not environment_commands or type(default_group) is not int
                                          or not 1<=default_group<=32):
            raise ValueError('KCL default_group requires environment_commands and a group in 1..32')
        if working_directory!='.':
            from .fileops import kcl_working_directory
            if not file_commands:raise ValueError('KCL working_directory requires file_commands')
            kcl_working_directory(working_directory)
        self.replies={};self.limit=limit;self.history=[];self.sequence=sequence
        self.task_commands=task_commands
        self.file_commands=file_commands
        self.working_directory=working_directory
        self.default_program=default_program
        self.default_group=default_group
        self.variable_commands=variable_commands
        self.device_commands=device_commands
        self.dictionary_commands=dictionary_commands
        self.program_commands=program_commands
        self.environment_commands=environment_commands
        self.procedure_commands=procedure_commands
        self.verify=verify
        self.debug_commands=debug_commands
        self.program_breakpoints=breakpoint_config(program_breakpoints,debug_commands)
        self._step_target=None
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
            if 'task_ready' in job:
                job['scheduler']._remove_task_wait(job['target'],job['task_ready'])
            job['row'].update(phase='completed',status=job['status'])
            self.last_status=job['status'];self._pending=None

    def poll(self):
        job=self._pending
        if job is None:return
        if 'task_ready' in job:
            job['task_ready']()
        elif job['clock'] is not None and job['clock']()>=job['due']:
            self.complete(job)

    def _record(self,state,name,command,phase,code):
        self.sequence+=1
        row=dict(sequence=self.sequence,program=rt().task_root(state).program_name,operation=name,command=command,phase=phase,status=code)
        self.history.append(row);del self.history[:-self.limit]
        return row

    def _begin_inline(self,state,name,command):
        row=self._record(state,name,command,'pending',0)
        job=dict(row=row,status=4,clock=None,delay_ms=0)
        self._pending=job
        return job

    def _dispatch(self,state,name,command,operation):
        """Hold the channel busy during a supported inline command."""
        job=self._begin_inline(state,name,command)
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
        if action in ('PAUSE', 'ABORT', 'UNHOLD'):
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
        from .scheduling import TaskScheduler, drive_registered_task, task_request_suppressed

        action, selector, force = request
        registry = state.execution.tasks
        owner = registry if isinstance(registry, TaskScheduler) else None
        driving = action in ('RUN', 'CONTINUE')
        control = 'PAUSE' if action == 'HOLD' else action
        targets = self._task_targets(state, registry, owner, control, selector)
        if targets is None or (name == 'KCL_NO_WAIT' and driving and owner is None):
            return self._reject_ineligible(state,name,command)

        def dispatch(job):
            if action in ('HOLD','UNHOLD'):
                bank=state.execution.require('motion',line)
                state.execution.require('group_locks',line)
                affected=targets
                if action=='HOLD':
                    affected=tuple(target for target in targets if not task_request_suppressed(target,'PAUSE','command'))
                plan=bank.prepare_task_controls(state,affected,action,line)
                bank.apply_task_controls(state,action,line,plan)
                if action=='UNHOLD':return 0
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
                    request_task_control(target, control, line, force=force)
                if task_root(state) in targets:
                    job['self_action'] = control
            return 0
        return self._dispatch(state,name,command,dispatch)

    def _reject_ineligible(self,state,name,command):
        self._record(state,name,command,'rejected',3)
        self.last_status=3
        return 3,None

    def _submit_task_wait(self,state,name,command,request,line):
        from .scheduling import TaskScheduler, selected_task_root, task_wait_result

        registry=state.execution.tasks
        selector,until_pause=request
        code,target=selected_task_root(registry,selector,state,line)
        caller=rt().task_root(state)
        if code or target is caller or target.task_state=='ready':
            return self._reject_ineligible(state,name,command)
        run=target._task_run
        code=task_wait_result(target,run,until_pause)
        if code is not None:
            return self._dispatch(state,name,command,lambda _job:code)
        if (not isinstance(registry,TaskScheduler) or target._scheduler is not registry
                or name=='KCL' and caller._scheduler is not registry):
            return self._reject_ineligible(state,name,command)

        def ready():
            if self._pending is job:
                result=task_wait_result(target,run,until_pause)
                if result is not None:
                    job['status']=result
                    self.complete(job)
            return self._pending is not job

        row=self._record(state,name,command,'pending',0)
        job=dict(row=row,status=0,delay_ms=0,target=target,scheduler=registry,task_ready=ready)
        self._pending=job
        registry._add_task_wait(target,ready)
        return 0,job

    def _submit_file(self,state,name,command,request,line):
        from .fileops import kcl_file_operation

        operation,args=request
        def dispatch(_job):
            code=kcl_file_operation(state,operation,args,line,channel=self)
            return 100+code if code else 0
        return self._dispatch(state,name,command,dispatch)

    def _submit_task_admin(self,state,name,command,request,line):
        from .scheduling import kcl_task_admin

        operation,args=request
        if operation=='RESET':
            return self._submit_activation(state,name,command,self._run_reset)
        if operation=='SHOW_HISTORY':
            from .inspection import kcl_task_history
            selector=args[0] or self.default_program
            return self._dispatch(state,name,command,lambda _job:kcl_task_history(state,selector,line))
        if not args[0] and self.default_program is not None:
            args=(self.default_program,*args[1:])
        return self._dispatch(state,name,command,lambda _job:kcl_task_admin(state,operation,args,line))

    def _submit_variable(self,state,name,command,request,line):
        from .dynamic import create, edit_detached_path, remove_detached, rename, set_detached_value

        operation,args=request
        if self.default_program is not None and not args[0] and operation not in ('SAVE_VARS','LOAD_VARS'):
            args=(self.default_program,*args[1:])
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
                group=self.default_group or rt().task_root(state).robot_group
                code=set_detached_value(state,*args,group,line)
            elif operation in ('SAVE_VARS','LOAD_VARS'):
                from .variable_archives import kcl_archive
                code=kcl_archive(state,operation,*args,line)
            elif operation in ('SHOW_VAR','SHOW_VARS'):
                from .inspection import kcl_variable_listing
                code=kcl_variable_listing(state,operation,args,line)
            elif operation in ('SHOW_SYSTEM','SHOW_MEMORY'):
                from .inspection import kcl_storage_listing
                code=kcl_storage_listing(state,operation,args[1:],line)
            elif operation in ('SHOW_LOCAL_VAR','SHOW_LOCAL_VARS','SET_LOCAL_VAR'):
                from .inspection import kcl_local_operation
                code=kcl_local_operation(state,operation,args,line)
            elif operation=='SHOW_TYPES':
                from .inspection import kcl_type_listing
                code=kcl_type_listing(state,*args,line)
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
        from .dictionaries import kcl_catalog,kcl_dictionary_file

        operation,args=request
        def dispatch(_job):
            if operation in ('LOAD_DICT','COMPRESS_DICT'):
                code=kcl_dictionary_file(state,operation,args,self,line)
            elif operation=='REMOVE_DICT':
                code=state.execution.require('dictionaries',line).manage(state,operation,args)
            else:
                code=kcl_catalog(state,operation,args,line)
            return 400+code if 0<code<100 else code
        return self._dispatch(state,name,command,dispatch)

    def _submit_program(self,state,name,command,request,line):
        from .archives import kcl_program_archive
        from .fileops import write_json_lines
        from .inspection import kcl_program_entries, kcl_program_listing
        from .source_translations import translate_stored_source

        operation,args=request
        def dispatch(_job):
            if operation=='TRANSLATE':
                return translate_stored_source(state.execution,state,*args,line)
            if operation=='SET_DEFAULT':
                program=args[0]
                if program=='ALL':return 502
                context=state.execution
                if program not in context.tasks.tasks and not any(
                        candidate==program for candidate,_ in kcl_program_entries(context,state)):
                    return 501
                self.default_program=program
                return 0
            if operation=='SHOW_DEFAULT':
                write_json_lines(state,[dict(program=self.default_program or state.program_name)],line)
                return 0
            if operation=='SHOW_BUILTINS':
                from .extended import FUNCTIONS, PROCEDURES

                rows=[dict(name=builtin,kind='FUNCTION' if builtin in FUNCTIONS else 'PROCEDURE')
                      for builtin in sorted(FUNCTIONS.keys()|PROCEDURES.keys())]
                write_json_lines(state,rows,line)
                return 0
            if operation=='SHOW_PROGRAM':
                selector=args[0] or self.default_program or state.program_name
                code=kcl_program_listing(state,operation,(selector,),line)
            elif operation in ('SHOW_PROGRAMS','SHOW_TASKS'):
                code=kcl_program_listing(state,operation,args,line)
            elif operation in ('SAVE_ALL','LOAD_ALL','CLEAR_ALL'):
                from .mixed_archives import kcl_batch

                operand=args[0]
                if operation!='CLEAR_ALL' and operand is None:operand=self.default_program
                code=kcl_batch(state,operation,operand,line)
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
            elif operation in ('SET_GROUP','SHOW_GROUP','SHOW_CURPOS'):
                from .fileops import write_json_lines

                runtime=rt()
                robot=state.execution.require('robot',line)
                group=args[0] if operation=='SET_GROUP' else (
                    self.default_group or runtime.task_root(state).robot_group or robot.active_group)
                if operation=='SET_GROUP':
                    if not 1<=group<=32:return 602
                    try:robot.for_group(group,line)
                    except runtime.KarelRuntimeError:return 602
                    self.default_group=group
                    return 0
                row=dict(group=group)
                if operation=='SHOW_CURPOS':
                    pose=state.execution.invoke(state,'CURPOS',(0,0,group),line)
                    row['pose']=runtime.snapshot_value(pose)
                else:robot.for_group(group,line)
                write_json_lines(state,[row],line)
                code=0
            else:
                bank=state.execution.require('ports',line)
                code=bank.kcl_operation(operation,args,line)
            return 600+code if code else 0
        return self._dispatch(state,name,command,dispatch)

    def _submit_procedure(self,state,name,command,request,line):
        operation,args=request
        if operation=='VERIFY':
            def set_verify(_job):
                self.verify=args[0]
                return 0
            return self._dispatch(state,name,command,set_verify)
        return self._submit_activation(state,name,command,self._run_procedure,procedure=args)

    def _submit_activation(self,state,name,command,runner,**data):
        if name=='KCL_NO_WAIT':return self._reject_ineligible(state,name,command)
        job=self._begin_inline(state,name,command)
        job.update(data,runner=runner)
        return 0,job

    def _run_reset(self,state,job,line):
        try:
            controller=state.execution.require('controller',line)
            completed=yield from controller.reset(state,None,line)
            job['status']=0 if completed else 4
        except rt().KarelRuntimeError:
            pass
        finally:
            self.complete(job)
        return job['status']

    def _debug_task(self,state,selector,line):
        from .scheduling import selected_task_root

        selector=selector or self.default_program
        if selector is None:return rt().task_root(state)
        return selected_task_root(state.execution.tasks,selector,state,line)[1]

    def _debug_module(self,state,selector,line):
        name=selector or self.default_program or state.program_name
        owner=state if name==state.program_name else state.execution.variables.programs.get(name)
        if owner is None and name in state.execution.tasks.tasks:
            owner=self._debug_task(state,name,line)
        return (owner.program_name,owner) if owner is not None else (name,None)

    def _program_break_command(self,state,args,line):
        action,selector,number,*options=args
        module,owner=self._debug_module(state,selector,line)
        if number is not None and not 1<=number<=32767:return 802
        if action=='SET':
            source_line,mode=options
            if owner is None:return 801
            if owner.execution.kcl is not state.execution.kcl:return 802
            lines=getattr(getattr(owner,'program',None),'source_checkpoints',())
            if not 1<=source_line<=32767 or source_line not in lines:return 802
            key=module,number
            if key not in self.program_breakpoints and len(self.program_breakpoints)>=256:return 805
            self.program_breakpoints[key]=dict(program=module,number=number,line=source_line,
                                               action=mode,enabled=True)
        else:
            keys=[key for key in self.program_breakpoints if key[0]==module and (number is None or key[1]==number)]
            if not keys and (number is not None or owner is None):return 801
            for key in keys:
                if action=='CLEAR':del self.program_breakpoints[key]
                else:self.program_breakpoints[key]['enabled']=action=='ENABLE'
        return 0

    def _condition_break_command(self,state,args,line):
        action,selector,number=args
        root=self._debug_task(state,selector,line)
        if number is not None and not 1<=number<=1000:return 802
        if root is None or root.task_state not in ('running','paused','waiting'):return 801
        if root.execution.kcl is not state.execution.kcl:return 802
        handlers={key:handler for key,handler in root._handlers.items() if handler.get('local_frame') is None}
        if number is not None and number not in handlers:return 801
        if action=='SET':handlers[number]['kcl_break']=state.execution.kcl
        else:
            for key in handlers if number is None else (number,):
                handlers[key].pop('kcl_break',None)
        return 0

    def _show_breaks(self,state,selector,line):
        from .fileops import write_json_lines

        module,owner=self._debug_module(state,selector,line)
        rows=[dict(kind='PROGRAM',**row) for (name,_),row in sorted(self.program_breakpoints.items())
              if name==module]
        root=self._debug_task(state,selector,line)
        if root is not None and root.program_name==module:
            rows.extend(dict(kind='CONDITION',program=module,number=number,enabled=True)
                        for number,handler in sorted(root._handlers.items())
                        if handler.get('kcl_break') is state.execution.kcl)
        if not rows and owner is None:return 801
        write_json_lines(state,rows,line)
        return 0

    def _submit_debug(self,state,name,command,request,line):
        operation,args=request
        def dispatch(_job):
            if operation=='PROGRAM':return self._program_break_command(state,args,line)
            if operation=='CONDITION':return self._condition_break_command(state,args,line)
            if operation=='SHOW_BREAK':return self._show_breaks(state,args[0],line)
            target=None
            if operation=='STEP_ON':
                target=self._debug_task(state,args[0],line)
                if target is None:return 801
                if (target.execution.kcl is not state.execution.kcl
                        or not hasattr(getattr(target,'program',None),'source_checkpoints')):return 802
            if self._step_target is not None:self._step_target._task_settings['TSK_STEP']=0
            self._step_target=target
            if target is not None:target._task_settings['TSK_STEP']=1
            return 0
        return self._dispatch(state,name,command,dispatch)

    def source_break(self,state,line):
        from .fileops import write_json_lines

        root=rt().task_root(state)
        pause=root is self._step_target
        matches=sorted((row.copy() for row in self.program_breakpoints.values()
                        if row['enabled'] and row['program']==state.program_name and row['line']==line),
                       key=lambda row:row['number'])
        for row in matches:
            action=row['action']
            if action=='PAUSE':pause=True
            elif action=='DISPLAY':write_json_lines(state,[row],line)
            else:
                root._task_settings['TSK_TRACE']=int(action=='TRACE ON')
                if action=='TRACE ON':root._task_settings.setdefault('TSK_TRACELEN',1000)
        return pause

    def _run_procedure(self,state,job,line):
        from .fileops import kcl_procedure_output,write_file_text

        previous=state._write
        child=None
        transcript=[]
        remaining=PROCEDURE_LIMIT
        overflow=False
        try:
            try:files,commands,listing=procedure_plan(state,self,job['procedure'],line)
            except ValueError as error:raise ProcedureError(702) from error
            config=self.snapshot()
            for key in ('history','sequence','last_status','pending'):config.pop(key)
            child=self.from_config(config)
            child._step_target=self._step_target

            def output(text):
                nonlocal remaining,overflow
                if len(text)>remaining:
                    overflow=True
                    raise ProcedureError(705)
                remaining-=len(text)
                if listing is not None:transcript.append(text)
                elif previous is not None:return previous(text)

            state._write=output
            status=0
            for command in commands:
                state.tick(line)
                if child.verify:write_file_text(state,command+'\n',line)
                status,step=child.submit(state,'KCL',command,line)
                if step is not None:status=yield from child.wait(state,step,line,activate=True)
                self.working_directory=child.working_directory
                self.default_program=child.default_program
                self.default_group=child.default_group
                self.verify=child.verify
                self.program_breakpoints=child.program_breakpoints
                self._step_target=child._step_target
                if step is not None and 'self_action' in step:
                    yield from rt().checkpoint(state,line,force_pause=step['self_action']=='PAUSE')
                if status:break
            state._write=previous
            if overflow:status=705
            if not status and listing is not None:
                if state.execution.files is not files:raise ProcedureError(704)
                status=kcl_procedure_output(files,listing,line,data=''.join(transcript).encode('ascii'))
            job['status']=status
        except ProcedureError as error:
            job['status']=error.status
        except (OSError,ValueError):
            job['status']=704
        except rt().KarelRuntimeError:
            if overflow:job['status']=705
        finally:
            state._write=previous
            if child is not None and child._pending is not None:
                # The enclosing source activation owns the command procedure.
                # Retire an uncollected private wait without stopping its target.
                pending=child._pending
                pending['status']=4
                child.complete(pending)
            self.complete(job)
        return job['status']

    def submit(self,state,name,command,line=None):
        try:command=command_text(command)
        except ValueError as exc:raise rt().KarelRuntimeError(str(exc),line) from exc
        if self.sequence>=2147483646:raise rt().KarelRuntimeError('KCL request sequence exhausted',line)
        self.poll();reply=self.replies.get(command)
        if self._pending is None and reply is None:
            for enabled,parse,submit in (
                (self.task_commands,lambda text:task_command(text,self.default_program),self._submit_task),
                (self.task_commands,task_admin_command,self._submit_task_admin),
                (self.task_commands,lambda text:task_wait_command(text,self.default_program),self._submit_task_wait),
                (self.file_commands,file_command,self._submit_file),
                (self.variable_commands,variable_command,self._submit_variable),
                (self.device_commands,device_command,self._submit_device),
                (self.dictionary_commands,dictionary_command,self._submit_dictionary),
                (self.program_commands,program_command,self._submit_program),
                (self.environment_commands,environment_command,self._submit_environment),
                (self.procedure_commands,procedure_command,self._submit_procedure),
                (self.debug_commands,debug_command,self._submit_debug),
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

    def wait(self,state,job,line=None,*,activate=False):
        if 'task_ready' in job:
            root=rt().task_root(state)
            while not job['task_ready']():
                if root is job['target'] or root._scheduler is not job['scheduler']:
                    raise rt().KarelRuntimeError('Unfinished KCL task wait requires another task on its owning scheduler',line)
                yield dict(kind='kcl_wait',ready=job['task_ready'],line=line)
                if root._pause_requested or root._abort_requested:
                    yield from rt().checkpoint(root,line,force_pause=True)
            return job['status']
        if self._pending is job:
            if 'runner' in job:
                if not activate:
                    raise rt().KarelRuntimeError('An executing KCL command belongs to its calling activation',line)
                return (yield from job['runner'](state,job,line))
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
        if name=='KCL' and job is not None:
            code=yield from self.wait(state,job,line,activate=True)
        args[1].set(code,line)
        if job is not None and 'self_action' in job:
            yield from rt().checkpoint(state,line,force_pause=job['self_action']=='PAUSE')

    def snapshot(self):
        result=dict(replies=deepcopy(self.replies),limit=self.limit,history=deepcopy(self.history),sequence=self.sequence,last_status=self.last_status)
        if self.task_commands:result['task_commands']=True
        if self.file_commands:result['file_commands']=True
        if self.working_directory!='.':result['working_directory']=self.working_directory
        if self.default_program is not None:result['default_program']=self.default_program
        if self.default_group is not None:result['default_group']=self.default_group
        if self.variable_commands:result['variable_commands']=True
        if self.device_commands:result['device_commands']=True
        if self.dictionary_commands:result['dictionary_commands']=True
        if self.program_commands:result['program_commands']=True
        if self.environment_commands:result['environment_commands']=True
        if self.procedure_commands:result['procedure_commands']=True
        if self.debug_commands:result['debug_commands']=True
        if self.program_breakpoints:
            result['program_breakpoints']=[row.copy() for _,row in sorted(self.program_breakpoints.items())]
        if not self.verify:result['verify']=False
        if self._pending is not None:
            job=self._pending;result['pending']=dict(sequence=job['row']['sequence'],command=job['row']['command'],status=job['status'],delay_ms=job['delay_ms'])
        return result

    def to_config(self):
        if self._pending is not None:raise ValueError('Cannot persist a pending KCL command; collect KCL_STATUS first')
        return self.snapshot()

    @classmethod
    def from_config(cls,config):
        fields={'replies','limit','history','sequence','last_status','task_commands','file_commands',
                'variable_commands','device_commands','dictionary_commands','program_commands','environment_commands',
                'working_directory','default_program','default_group','procedure_commands','verify',
                'debug_commands','program_breakpoints'}
        if type(config) is not dict or set(config)-fields:raise ValueError('Unknown KCL channel fields')
        return cls(**config)
