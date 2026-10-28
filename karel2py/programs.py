"""Nested explicitly attached KAREL programs and logical group ownership."""
import re


def rt():
    from . import runtime
    return runtime


class GroupLocks:
    """Configured motion-group labels; no robot, motion or native locks."""
    def __init__(self,groups,*,motion=None,apply_directives=False,callee_scopes=False):
        if (type(groups) not in (list,tuple) or not groups or len(groups)>31
                or any(type(group) is not int or not 1<=group<=31 for group in groups)
                or len(groups)!=len(set(groups))):
            raise ValueError('GroupLocks requires distinct groups in 1..31')
        if motion is not None and type(motion) is not dict: raise ValueError('Group motion must be an object')
        if type(apply_directives) is not bool:raise ValueError('apply_directives requires a BOOLEAN')
        if type(callee_scopes) is not bool:raise ValueError('callee_scopes requires a BOOLEAN')
        if callee_scopes and not apply_directives:raise ValueError('callee_scopes requires apply_directives=True')
        self.apply_directives=apply_directives;self.callee_scopes=callee_scopes
        self.groups=tuple(sorted(groups));self.motion={};self.owners={};self._ownership_tokens={}
        for group,value in (motion or {}).items(): self.set_motion(group,value)

    def _automatic_groups(self,state,line=None):
        """Preflight an entire module request without changing ownership."""
        runtime=rt()
        if type(self.apply_directives) is not bool:
            raise runtime.KarelRuntimeError('apply_directives requires a BOOLEAN',line)
        if type(self.callee_scopes) is not bool:
            raise runtime.KarelRuntimeError('callee_scopes requires a BOOLEAN',line)
        if self.callee_scopes and not self.apply_directives:
            raise runtime.KarelRuntimeError('callee_scopes requires apply_directives=True',line)
        if not self.apply_directives:return None
        root=runtime.task_root(state)
        groups=state._source_settings.get('lock_groups')
        if groups is None:groups=self.groups
        if (type(groups) not in (list,tuple) or len(groups)>31
                or any(type(group) is not int or not 1<=group<=31 for group in groups)
                or len(set(groups))!=len(groups)):
            raise runtime.KarelRuntimeError('Invalid automatic logical group requirements',line)
        selected=tuple(sorted(groups))
        unknown=set(selected)-set(self.groups)
        if unknown:
            raise runtime.KarelRuntimeError('Automatic group requirements include unconfigured groups: '+','.join(map(str,sorted(unknown))),line)
        for group in selected:
            owner=self.owners.get(group)
            if owner is not None and owner is not root:
                raise runtime.KarelRuntimeError('Automatic logical group acquisition blocked by another task: '+str(group),line)
            if owner is None and self.motion.get(group,'idle')!='idle':
                raise runtime.KarelRuntimeError('Automatic logical group acquisition blocked by a busy label: '+str(group),line)
        return root,selected

    def _grant(self,group,owner):
        if group not in self.owners:
            self.owners[group]=owner;self._ownership_tokens[group]=object()
        return self._ownership_tokens.get(group)

    def begin(self,state,line=None):
        """Acquire root-entry requirements, retaining the established default."""
        if state is not rt().task_root(state):return
        request=self._automatic_groups(state,line)
        if request is None:return
        owner,groups=request
        for group in groups:self._grant(group,owner)

    def enter_scope(self,state,line=None):
        """Return an opaque lease for additional module groups, when opted in."""
        if self.callee_scopes is False:return None
        request=self._automatic_groups(state,line)
        if request is None:return None
        owner,groups=request;acquired={}
        for group in groups:
            if group not in self.owners:acquired[group]=self._grant(group,owner)
        return self,owner,acquired

    def leave_scope(self,scope):
        """Release only this lease's surviving grants, never later acquisitions."""
        if scope is None:return
        bank,owner,acquired=scope
        if bank is not self:raise rt().KarelRuntimeError('Group scope belongs to a different bank')
        for group,token in acquired.items():
            if self.owners.get(group) is owner and self._ownership_tokens.get(group) is token:
                self.owners.pop(group);self._ownership_tokens.pop(group,None)

    def set_motion(self,group,value):
        if type(group) is not int or group not in self.groups or value not in ('idle','executing','stopped'):
            raise ValueError('Motion requires a configured group and idle/executing/stopped label')
        if value=='idle': self.motion.pop(group,None)
        else:self.motion[group]=value

    def update(self,state,operation,mask,line=None):
        runtime=rt();mask=runtime.integer(mask,line)
        allowed=sum(1<<(group-1) for group in self.groups)
        if mask<0 or mask&~allowed: return 1
        selected=[group for group in self.groups if mask&(1<<(group-1))]
        root=runtime.task_root(state);code=0
        for group in selected:
            owner=self.owners.get(group)
            if owner is not None and owner is not root:
                if not code:code=2
                continue
            if operation=='LOCK_GROUP': self._grant(group,root)
            else:
                motion=self.motion.get(group,'idle')
                if owner is root and motion!='idle':
                    if not code:code=17039 if motion=='executing' else 17040
                else:self.owners.pop(group,None);self._ownership_tokens.pop(group,None)
        return code

    def release_owner(self,state):
        root=rt().task_root(state)
        for group,owner in list(self.owners.items()):
            if owner is root:self.owners.pop(group);self._ownership_tokens.pop(group,None)

    def snapshot(self):
        result={'groups':list(self.groups),'motion':{str(key):value for key,value in sorted(self.motion.items())},
                'owners':{str(key):value.program_name for key,value in sorted(self.owners.items())}}
        if self.apply_directives:result['apply_directives']=True
        if self.callee_scopes:result['callee_scopes']=True
        return result

    def to_config(self):
        if self.owners: raise ValueError('Cannot persist live group ownership; finish or unlock the task first')
        result={'groups':list(self.groups),'motion':{str(key):value for key,value in sorted(self.motion.items())}}
        if self.apply_directives:result['apply_directives']=True
        if self.callee_scopes:result['callee_scopes']=True
        return result

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'groups','motion','apply_directives','callee_scopes'} or 'groups' not in config:
            raise ValueError('Group lock configuration requires groups and optional motion/directive settings')
        motion=config.get('motion',{})
        if type(motion) is not dict or any(type(key) is not str or not re.fullmatch(r'[1-9][0-9]?',key) for key in motion):
            raise ValueError('Motion keys require canonical group numbers')
        return cls(config['groups'],motion={int(key):value for key,value in motion.items()},apply_directives=config.get('apply_directives',False),callee_scopes=config.get('callee_scopes',False))


def call_program(state,operation,args,line=None):
    runtime=rt();context=state.execution
    name=runtime.ascii_string(args[0],line).strip().upper()
    index=args[1] if operation=='CALL_PROG' else args[2]
    pause=False
    if operation=='CALL_PROGLIN':
        if runtime.integer(args[1],line)<0: raise runtime.KarelRuntimeError('Program line must be nonnegative',line)
        pause=runtime.boolean(args[3],line)
    if not re.fullmatch(r'[A-Z_][A-Z_0-9]{0,35}',name):
        raise runtime.KarelRuntimeError('Program call requires an ordinary program name',line)
    prototype=context.variables.programs.get(name)
    program=getattr(prototype,'program',None)
    if program is None or not callable(getattr(program,'_execute',None)):
        raise runtime.KarelRuntimeError('Program is not attached as cooperative KAREL source: '+name,line)
    if state.call_depth>=64: raise runtime.KarelRuntimeError('Prototype program/routine call-depth limit exceeded (64)',line)
    # Clone stacks and retain module globals, including imported references. Do not
    # drive or reset the prototype's independently registered task/generator.
    instance=type(program)(context=context,joint_axes=prototype.joint_axes,
        pose_tolerance=prototype.pose_tolerance,external_tolerance=prototype.external_tolerance,
        registers=prototype.registers,sleep=state._sleep,read=state._read,write=state._write,clock_us=state._clock_us)
    child=instance._state;root=runtime.task_root(state)
    child._sleep_injected=state._sleep_injected
    child.values=prototype.values;child._budget_parent=state;child.call_depth=state.call_depth
    child._scheduler=state._scheduler;child.max_steps=state.max_steps
    child._lifecycle=state._lifecycle
    for attr in ('service_requests','write_requests','read_requests','clock_reads','register_requests'):
        setattr(child,attr,getattr(root,attr))
    child.enter_routine({},line,routine='')
    try:
        if name not in context.program_entries: context.program_entries[name]=len(context.program_entries)+1
        index.set(context.program_entries[name],line)
        if pause: yield from runtime.pause_execution(child,line)
        yield from instance._execute()
    except runtime.KarelAbort as exc:
        root._aborted=True;root._abort_line=exc.line;raise
    finally:
        child.leave_routine()
