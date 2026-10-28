"""Logical ownership, stored perches, scripted resets and background task slots."""
from copy import deepcopy
import math
import re


CONTROLLER_CALLS={'MOTION_CTL','CNCL_STP_MTN','SET_PERCH','RESET','MIXBG_RUN','MIXBG_STOP'}
MAX_SEQUENCE=2147483646


def rt():
    from . import runtime
    return runtime


def bounded(value,minimum,maximum,message):
    if type(value) is not int or not minimum<=value<=maximum:raise ValueError(message)
    return value


def vector(value,*,tolerance=False):
    if type(value) not in (list,tuple) or len(value)!=6:raise ValueError('Perch values require six explicit axes/tolerances')
    try:valid=all(type(number) in (float,int) and math.isfinite(number) and (not tolerance or number>=0) for number in value)
    except OverflowError:valid=False
    if not valid:raise ValueError('Perch values must be finite; tolerances must be nonnegative')
    return [float(number) for number in value]


class ControllerServices:
    """No controller connection, physical movement, program discovery or reset."""
    def __init__(self,*,background=None,perch_counts=None,perches=None,resets=None,limit=500,sequence=0,history=None,elapsed_ms=0):
        self.limit=bounded(limit,1,4096,'Controller history limit requires 1..4096')
        self.sequence=bounded(sequence,0,MAX_SEQUENCE,'Invalid controller history sequence')
        self.elapsed_ms=bounded(elapsed_ms,0,MAX_SEQUENCE,'Invalid controller elapsed time')
        self.background={};self.perch_counts={};self.perches={};self.history=[];self.resets=[]
        self._background={};self._pending=None
        for supplied,label in ((background,'background'),(perch_counts,'perch_counts')):
            if supplied is not None and type(supplied) is not dict:raise ValueError(label+' requires an explicit mapping')
        if len(background or {})>256:raise ValueError('At most 256 background slots')
        for slot,name in (background or {}).items():
            slot=bounded(slot,1,256,'Background slot requires 1..256')
            if type(name) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,35}',name):raise ValueError('Background task name requires an ordinary program identifier')
            if name.upper() in self.background.values():raise ValueError('Background slots require distinct task names')
            self.background[slot]=name.upper()
        for group,count in (perch_counts or {}).items():
            group=bounded(group,1,32,'Perch group requires 1..32')
            self.perch_counts[group]=bounded(count,1,32767,'Perch count requires 1..32767')
        if perches is None:perches={}
        if type(perches) is not dict or len(perches)>4096:raise ValueError('At most 4096 stored perches')
        for key,value in perches.items():
            if type(key) is not tuple or len(key)!=2:raise ValueError('Perch key requires group and index')
            self.address(*key)
            if type(value) is not dict or set(value)!={'joints','tolerance'}:raise ValueError('Perch requires joints and tolerance')
            self.perches[key]=dict(joints=vector(value['joints']),tolerance=vector(value['tolerance'],tolerance=True))
        if resets is None:resets=[]
        if type(resets) is not list or len(resets)>4096:raise ValueError('At most 4096 scripted reset responses')
        for row in resets:
            if type(row) is not dict or set(row)-{'delay_ms','completed','fault'} or type(row.get('completed')) is not bool:raise ValueError('Reset response requires completed BOOLEAN and optional delay/fault')
            delay=bounded(row.get('delay_ms',0),0,86400000,'Reset delay requires 0..86400000 ms')
            if 'fault' in row and type(row['fault']) is not bool:raise ValueError('Reset fault requires BOOLEAN')
            self.resets.append(dict(delay_ms=delay,completed=row['completed'],**({'fault':row['fault']} if 'fault' in row else {})))
        if history is None:history=[]
        if type(history) is not list or len(history)>limit:raise ValueError('Controller history exceeds its ring limit')
        previous=0
        for row in history:
            if type(row) is not dict or set(row)!={'sequence','program','operation','outcome','data'}:raise ValueError('Malformed controller history')
            bounded(row['sequence'],previous+1,sequence,'Controller history IDs must increase');previous=row['sequence']
            if type(row['program']) is not str or len(row['program'])>254 or not all(32<=ord(c)<=126 for c in row['program']):raise ValueError('Invalid controller history owner')
            if type(row['operation']) is not str or row['operation'] not in CONTROLLER_CALLS or type(row['outcome']) is not str or row['outcome'] not in ('completed','rejected','cancelled','failed'):raise ValueError('Invalid controller history operation/outcome')
            data=row['data']
            if type(data) is not dict or len(data)>8 or any(type(k) is not str or len(k)>32 for k in data):raise ValueError('Invalid controller history data')
            for value in data.values():
                if type(value) is bool or type(value) is int and -2147483648<=value<=MAX_SEQUENCE:continue
                if type(value) is str and len(value)<=254 and all(32<=ord(c)<=126 for c in value):continue
                if type(value) is list and len(value)<=31 and all(type(v) is int and 1<=v<=31 for v in value):continue
                raise ValueError('Invalid controller history value')
            self.history.append(deepcopy(row))

    def address(self,group,index):
        if type(group) is not int or group not in self.perch_counts:raise ValueError('Perch group is not configured')
        return group,bounded(index,1,self.perch_counts[group],'Perch index is outside its configured bank')

    def begin(self,state,name,**data):
        if self.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Controller request sequence exhausted')
        self.sequence+=1;row=dict(sequence=self.sequence,program=rt().task_root(state).program_name,operation=name,outcome='pending',data=data)
        self.history.append(row);del self.history[:-self.limit];return row

    def groups(self,state,mask,line):
        bank=state.execution.require('group_locks',line)
        if mask is None:
            settings=rt().task_root(state)._source_settings;groups=settings.get('lock_groups')
            mask=sum(1<<(group-1) for group in groups) if groups is not None else 1<<((rt().task_root(state).robot_group or 1)-1)
        allowed=sum(1<<(group-1) for group in bank.groups)
        if type(mask) is not int or not 0<=mask<=MAX_SEQUENCE or mask&~allowed:raise rt().KarelRuntimeError('Motion control mask selects invalid or unconfigured groups',line)
        return bank,[group for group in bank.groups if mask&(1<<(group-1))],mask

    def motion_control(self,state,mask,line):
        bank,groups,mask=self.groups(state,mask,line);root=rt().task_root(state)
        answer=bool(groups) and all(bank.owners.get(group) is root for group in groups)
        row=self.begin(state,'MOTION_CTL',mask=mask,owned=answer);row['outcome']='completed';return answer

    def cancel_stopped(self,state,line):
        bank=state.execution.require('group_locks',line);root=rt().task_root(state)
        groups=[group for group in bank.groups if bank.owners.get(group) is root and bank.motion.get(group)=='stopped']
        row=self.begin(state,'CNCL_STP_MTN',groups=groups)
        for group in groups:bank.set_motion(group,'idle')
        row['outcome']='completed'

    def set_perch(self,state,args,line):
        joints,tolerance,index=args;group=rt().task_root(state).robot_group or 1
        try:
            key=self.address(group,index)
            if rt().array_dimensions(tolerance.spec)!=(6,):raise ValueError('SET_PERCH requires ARRAY[6] OF REAL')
            point=vector(rt().joint_values(joints,6,line));width=vector(tolerance.values,tolerance=True)
            if key not in self.perches and len(self.perches)>=4096:raise ValueError('Stored perch capacity exhausted')
        except ValueError as error:raise rt().KarelRuntimeError(str(error),line) from error
        row=self.begin(state,'SET_PERCH',group=group,index=index,axes=6)
        self.perches[key]=dict(joints=point,tolerance=width);row['outcome']='completed'

    def background_call(self,state,name,args,line):
        slot,status=args;context=state.execution;scheduler=context.tasks
        if type(scheduler) is not rt().TaskScheduler:raise rt().KarelRuntimeError('Background slots require an explicit TaskScheduler with attached cooperative tasks',line)
        task_name=self.background.get(slot);target=self._background.get(slot)
        bound_name=next((key for key,value in scheduler.tasks.items() if value is target),None) if target is not None else None
        if bound_name is not None:task_name=bound_name
        elif target is None or getattr(target,'_execution',None) is None:target=scheduler.tasks.get(task_name)
        else:task_name=None
        code=1 if target is None or task_name is None else 2 if target._state.execution is not context or rt().task_root(target._state) is rt().task_root(state) or target._state._scheduler not in (None,scheduler) else 0
        if not code and (target.task_state in ('stopped','aborted','failed') or target._state._abort_requested):code=3
        from .scheduling import task_request_suppressed
        if not code and name=='MIXBG_STOP' and getattr(target,'_execution',None) is not None and task_request_suppressed(target._state,'PAUSE','command'):code=4
        row=self.begin(state,name,slot=slot,task=task_name or '',status=code)
        if code:row['outcome']='rejected';status.set(code,line);return
        try:
            self._background[slot]=target
            if name=='MIXBG_RUN':
                if target.task_state=='paused':scheduler.continue_task(task_name);action='resumed'
                elif getattr(target,'_execution',None) is not None:target._state._pause_requested=False;action='running'
                else:scheduler.start(task_name);action='started'
            elif getattr(target,'_execution',None) is None:action='idle'
            elif target.task_state=='paused':action='paused'
            else:rt().request_task_control(target._state,'PAUSE',line);action='pause_requested'
            row['data']['action']=action;row['outcome']='completed';status.set(0,line)
        except BaseException:row['outcome']='failed';raise

    def reset(self,state,success,line):
        if self._pending is not None:raise rt().KarelRuntimeError('A scripted controller reset is already pending',line)
        if not self.resets:raise rt().KarelRuntimeError('RESET requires an explicit scripted completion response',line)
        response=self.resets[0]
        if self.elapsed_ms+response['delay_ms']>MAX_SEQUENCE:raise rt().KarelRuntimeError('Controller reset clock exhausted',line)
        ports=None
        if 'fault' in response:ports=state.execution.require('ports',line);ports._key('OPOUT',3,line)
        row=self.begin(state,'RESET',**response);self.resets.pop(0);self._pending=row
        try:
            remaining=response['delay_ms']
            while remaining:
                step=min(10,remaining);yield from rt().delay_execution(state,step,line)
                self.elapsed_ms+=step;remaining-=step;yield from rt().checkpoint(state,line)
            if ports is not None:ports.update('OPOUT',3,response['fault'])
            # The documented successful output acknowledges the request even
            # when conditions prevent a reset. The supplied fault result is separate.
            success.set(True,line);row['outcome']='completed'
        except BaseException as error:
            row['outcome']='cancelled' if isinstance(error,(GeneratorExit,rt().KarelStop,rt().KarelAbort)) else 'failed';raise
        finally:self._pending=None

    def invoke(self,state,name,args,line=None):
        if name=='MOTION_CTL':return self.motion_control(state,args[0],line)
        if name=='CNCL_STP_MTN':return self.cancel_stopped(state,line)
        if name=='SET_PERCH':return self.set_perch(state,args,line)
        if name=='RESET':return self.reset(state,args[0],line)
        return self.background_call(state,name,args,line)

    def snapshot(self):
        return dict(background={str(k):v for k,v in sorted(self.background.items())},
            perch_counts={str(k):v for k,v in sorted(self.perch_counts.items())},
            perches={str(group)+':'+str(index):deepcopy(value) for (group,index),value in sorted(self.perches.items())},
            resets=deepcopy(self.resets),limit=self.limit,sequence=self.sequence,history=deepcopy(self.history),elapsed_ms=self.elapsed_ms,
            pending_reset=self._pending is not None,background_tasks={str(slot):target.task_state for slot,target in sorted(self._background.items())})

    def to_config(self):
        if self._pending is not None:raise ValueError('Finish or stop the pending scripted reset before saving context')
        if any(getattr(target,'_execution',None) is not None for target in self._background.values()):raise ValueError('Finish or stop active background tasks before saving context')
        result=self.snapshot();result.pop('pending_reset');result.pop('background_tasks');return result

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'background','perch_counts','perches','resets','limit','sequence','history','elapsed_ms'}:raise ValueError('Unknown controller configuration fields')
        config=dict(config)
        for key in ('background','perch_counts'):
            values=config.get(key,{})
            if type(values) is not dict or any(type(k) is not str or not re.fullmatch(r'[1-9][0-9]*',k) for k in values):raise ValueError('Controller bank keys require canonical positive numbers')
            config[key]={int(k):v for k,v in values.items()}
        values=config.get('perches',{})
        if type(values) is not dict or any(type(k) is not str or not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*',k) for k in values):raise ValueError('Perch keys require canonical group:index')
        config['perches']={tuple(int(v) for v in k.split(':')):value for k,value in values.items()}
        return cls(**config)
