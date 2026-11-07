"""Nested explicitly attached KAREL programs and logical group ownership."""
import re


def rt():
    from . import runtime
    return runtime


class GroupLocks:
    """Configured motion-group labels; no robot, motion or native locks."""
    def __init__(self,groups,*,motion=None,held=None,apply_directives=False,callee_scopes=False,
                 lock_wait_ms=0,unlock_wait_ms=0,pendant_enabled=False):
        if (type(groups) not in (list,tuple) or not groups or len(groups)>31
                or any(type(group) is not int or not 1<=group<=31 for group in groups)
                or len(groups)!=len(set(groups))):
            raise ValueError('GroupLocks requires distinct groups in 1..31')
        if motion is not None and type(motion) is not dict: raise ValueError('Group motion must be an object')
        if type(apply_directives) is not bool:raise ValueError('apply_directives requires a BOOLEAN')
        if type(callee_scopes) is not bool:raise ValueError('callee_scopes requires a BOOLEAN')
        if callee_scopes and not apply_directives:raise ValueError('callee_scopes requires apply_directives=True')
        if type(pendant_enabled) is not bool:raise ValueError('pendant_enabled requires a BOOLEAN')
        self.apply_directives=apply_directives;self.callee_scopes=callee_scopes
        self.pendant_enabled=pendant_enabled
        self.groups=tuple(sorted(groups));self.motion={};self.owners={};self._ownership_tokens={}
        for name, value in (('lock_wait_ms', lock_wait_ms), ('unlock_wait_ms', unlock_wait_ms)):
            if type(value) is not int or not 0 <= value <= 86400000:
                raise ValueError(name + ' requires an INTEGER in 0..86400000 ms')
            setattr(self, name, value)
        self._pending = {}
        for group,value in (motion or {}).items(): self.set_motion(group,value)
        if held is None:held=[]
        if (type(held) not in (list,tuple) or len(held)>31
                or any(type(group) is not int or group not in self.groups for group in held)
                or len(set(held))!=len(held)):
            raise ValueError('Held groups require distinct configured group numbers')
        self.held=set(held)

    def _automatic_groups(self,state,line=None,*,transferred=()):
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
            if group in transferred:
                continue
            owner=self.owners.get(group)
            if owner is not None and owner is not root:
                raise runtime.KarelRuntimeError('Automatic logical group acquisition blocked by another task: '+str(group),line)
            if owner is None and (self.motion.get(group,'idle')!='idle' or group in self.held):
                raise runtime.KarelRuntimeError('Automatic logical group acquisition blocked by a busy label: '+str(group),line)
        return root,selected

    def _grant(self,group,owner):
        if group not in self.owners:
            self.owners[group]=owner;self._ownership_tokens[group]=object()
        return self._ownership_tokens.get(group)

    def pendant_launch_groups(self, mask, line=None):
        if self.pendant_enabled is not True:
            raise rt().KarelRuntimeError('Offline RUN_TASK requires no motion unless pendant_enabled is true', line)
        selected = self._selected(mask, line)
        if selected is None:
            raise rt().KarelRuntimeError('RUN_TASK lock mask includes invalid or unconfigured groups', line)
        return selected

    def begin(self,state,line=None,*,handoff=None):
        """Preflight and commit the root's automatic grants and optional handoff."""
        if state is not rt().task_root(state):return
        transferred = ()
        if handoff is not None:
            parent, transferred = handoff
            motion = state.execution.motion
            for group in transferred:
                if self.owners.get(group) is not parent or group not in self._ownership_tokens:
                    raise rt().KarelRuntimeError(f'RUN_TASK handoff requires a parent grant for group {group}', line)
                if self._blocking_status(parent, group, False) or (motion is not None and motion.has_pending_group(group)):
                    raise rt().KarelRuntimeError(f'RUN_TASK handoff blocked by a busy group: {group}', line)
        request = self._automatic_groups(state, line, transferred=transferred)
        for group in transferred:
            self.owners[group] = state
            self._ownership_tokens[group] = object()
        if request is not None:
            owner, groups = request
            for group in groups:
                self._grant(group, owner)

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

    def _selected(self, mask, line):
        mask = rt().integer(mask, line)
        allowed = sum(1 << (group - 1) for group in self.groups)
        if mask < 0 or mask & ~allowed:
            return None
        return tuple(group for group in self.groups if mask & (1 << (group - 1)))

    def _blocking_status(self, root, group, locking):
        owner = self.owners.get(group)
        if owner is not None and owner is not root:
            return 2
        if not locking and owner is root:
            motion = self.motion.get(group, 'idle')
            if motion != 'idle' or group in self.held:
                return 17040 if motion == 'stopped' else 17039
        return 0

    def _apply(self, root, group, locking):
        if locking:
            self._grant(group, root)
        else:
            self.owners.pop(group, None)
            self._ownership_tokens.pop(group, None)

    def update(self, state, operation, mask, line=None):
        """Keep the immediate partial-result contract for direct calls and defaults."""
        selected = self._selected(mask, line)
        if selected is None:
            return 1
        locking = operation == 'LOCK_GROUP'
        root = rt().task_root(state)
        code = 0
        for group in selected:
            blocked = self._blocking_status(root, group, locking)
            if blocked:
                code = code or blocked
            else:
                self._apply(root, group, locking)
        return code

    def wait_ms(self, operation, line=None):
        name = 'lock_wait_ms' if operation == 'LOCK_GROUP' else 'unlock_wait_ms'
        value = getattr(self, name)
        if type(value) is not int or not 0 <= value <= 86400000:
            raise rt().KarelRuntimeError(name + ' requires an INTEGER in 0..86400000 ms', line)
        return value

    def wait_update(self, state, operation, mask, status, line=None):
        """Wait on a captured mask, publishing only an entire eligible request."""
        runtime = rt()
        selected = self._selected(mask, line)
        if selected is None:
            status.set(1, line)
            return
        locking = operation == 'LOCK_GROUP'
        root = runtime.task_root(state)
        timeout = self.wait_ms(operation, line)
        blockers = [self._blocking_status(root, group, locking) for group in selected]
        blocked = next((code for code in blockers if code), 0)
        if not blocked:
            status.set(0, line)
            for group in selected:
                self._apply(root, group, locking)
            return
        # A foreign grant is never adopted by a deferred unlock.
        if (not locking and 2 in blockers) or state._in_handler or root._in_handler:
            status.set(blocked, line)
            return
        if state._scheduler is None and not getattr(root, '_sleep_injected', False):
            raise runtime.KarelRuntimeError(operation + ' wait requires an explicit sleeper callback or scheduler', line)
        pending = self._pending
        if root in pending:
            raise runtime.KarelRuntimeError('Task already has a pending group operation', line)
        ticket = object()
        configuration = self.groups
        owners, tokens = self.owners, self._ownership_tokens
        storage, key = status.storage, status.key
        grants = () if locking else tuple(
            (group, owners.get(group), tokens.get(group)) for group in selected
        )
        remaining = timeout
        pending[root] = ticket
        try:
            while remaining:
                interval = min(10, remaining)
                yield from runtime.delay_execution(state, interval, line, scan_handlers=True)
                remaining -= interval
                yield from runtime.checkpoint(state, line)
                if (self._pending is not pending or pending.get(root) is not ticket
                        or state.execution.group_locks is not self or runtime.task_root(state) is not root
                        or self.groups is not configuration or self.owners is not owners
                        or self._ownership_tokens is not tokens or self.wait_ms(operation, line) != timeout):
                    raise runtime.KarelRuntimeError('Pending group operation ownership or configuration changed', line)
                if (status.storage is not storage or type(status.key) is not type(key)
                        or status.key != key or status.spec != ('INTEGER',)):
                    raise runtime.KarelRuntimeError('Pending group operation status target changed', line)
                if any(owners.get(group) is not owner or tokens.get(group) is not token
                       for group, owner, token in grants):
                    raise runtime.KarelRuntimeError('Pending group unlock grant changed', line)
                blocked = next((code for code in (
                    self._blocking_status(root, group, locking) for group in selected
                ) if code), 0)
                if not blocked:
                    status.set(0, line)
                    for group in selected:
                        self._apply(root, group, locking)
                    return
            status.set(blocked, line)
        finally:
            if self._pending is pending and pending.get(root) is ticket:
                del pending[root]

    def release_owner(self,state):
        root=rt().task_root(state)
        for group,owner in list(self.owners.items()):
            if owner is root:self.owners.pop(group);self._ownership_tokens.pop(group,None)

    def snapshot(self):
        result={'groups':list(self.groups),'motion':{str(key):value for key,value in sorted(self.motion.items())},
                'owners':{str(key):value.program_name for key,value in sorted(self.owners.items())}}
        if self.held:result['held']=sorted(self.held)
        if self.apply_directives:result['apply_directives']=True
        if self.callee_scopes:result['callee_scopes']=True
        self._save_optional_settings(result)
        return result

    def _save_optional_settings(self, result):
        if self.pendant_enabled:
            result['pendant_enabled'] = True
        if self.lock_wait_ms:
            result['lock_wait_ms'] = self.lock_wait_ms
        if self.unlock_wait_ms:
            result['unlock_wait_ms'] = self.unlock_wait_ms

    def to_config(self):
        if self._pending:
            raise ValueError('Cannot persist a pending group operation')
        if self.owners: raise ValueError('Cannot persist live group ownership; finish or unlock the task first')
        result={'groups':list(self.groups),'motion':{str(key):value for key,value in sorted(self.motion.items())}}
        if self.held:result['held']=sorted(self.held)
        if self.apply_directives:result['apply_directives']=True
        if self.callee_scopes:result['callee_scopes']=True
        self._save_optional_settings(result)
        return result

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'groups','motion','held','apply_directives','callee_scopes','lock_wait_ms','unlock_wait_ms','pendant_enabled'} or 'groups' not in config:
            raise ValueError('Group lock configuration requires groups and optional motion, directive, pendant and wait settings')
        motion=config.get('motion',{})
        if type(motion) is not dict or any(type(key) is not str or not re.fullmatch(r'[1-9][0-9]?',key) for key in motion):
            raise ValueError('Motion keys require canonical group numbers')
        return cls(
            config['groups'], motion={int(key):value for key,value in motion.items()}, held=config.get('held'),
            apply_directives=config.get('apply_directives',False), callee_scopes=config.get('callee_scopes',False),
            lock_wait_ms=config.get('lock_wait_ms',0), unlock_wait_ms=config.get('unlock_wait_ms',0),
            pendant_enabled=config.get('pendant_enabled',False),
        )


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
    cooperative=callable(getattr(program,'_execute',None))
    synchronous=callable(getattr(program,'_execute_sync',None)) and getattr(program,'translation_mode',None)=='pythonic'
    if program is None or not (cooperative or synchronous):
        raise runtime.KarelRuntimeError('Program is not attached as callable KAREL source: '+name,line)
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
        if cooperative:yield from instance._execute()
        else:
            try:instance._execute_sync()
            except runtime.KarelPause as exc:
                raise runtime.KarelRuntimeError('A synchronous program cannot retain a callback pause; translate it cooperatively',line) from exc
            except runtime.KarelRuntimeError as failure:
                yield from runtime.runtime_failure(child,failure);raise
        if root._aborted:raise runtime.KarelAbort(root._abort_line)
        if child._aborted:raise runtime.KarelAbort(child._abort_line)
    except runtime.KarelAbort as exc:
        root._aborted=True;root._abort_line=exc.line;raise
    finally:
        child.leave_routine()
