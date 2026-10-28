"""Explicit keyboard events, cooperative reads and headless dictionary menus."""
from copy import deepcopy
import re


MAX_SEQUENCE=2147483646
KEYBOARD_CALLS={'READ_KB','PUSH_KEY_RD','POP_KEY_RD','DISCTRL_ALPH','DISCTRL_PLMN','DISCTRL_SBMN'}
KEYBOARD_CONSTANTS=dict(KC_DISPLAY=1,KC_FUNC_KEY=2,KC_KEYPAD=4,KC_ENTER_KEY=8,KC_DELETE=16,
    KC_LR_ARW=32,KC_UD_ARW=64,KC_OTHER=128,KC_PREV_KEY=128,KY_UNDEF=0,KY_ENTER=13,KY_DELETE=8,
    KY_LF_ARW=1001,KY_RT_ARW=1002,KY_UP_ARW=1003,KY_DN_ARW=1004,KY_PREV=1005,KY_NEXT=1006,
    KY_NEW_MENU=1007,KY_SELECT=1008,KY_REFRESH=23,KY_PAGE_UP=1017,KY_PAGE_DOWN=1018,KY_HOME=1012,KY_END=1013,KY_FULL=1015,KY_TIMEOUT=1016,
    ATR_PASSALL=7,ATR_NOECHO=8)
KEYBOARD_CONSTANTS.update(('KY_F'+str(i),1100+i) for i in range(1,11))
KEYS={'ENTER':(13,8),'DELETE':(8,16),'LEFT':(1001,32),'RIGHT':(1002,32),'UP':(1003,64),'DOWN':(1004,64),
      'PREV':(1005,128),'NEXT':(1006,128),'NEW_MENU':(1007,128),'SELECT':(1008,128),'HOME':(1012,4),'END':(1013,4)}
KEYS.update(REFRESH=(23,4),PAGE_UP=(1017,4),PAGE_DOWN=(1018,4))
KEYS.update(('F'+str(i),(1100+i,2)) for i in range(1,11))


def rt():
    from . import runtime
    return runtime


def printable(value,maximum=254):return type(value) is str and len(value)<=maximum and all(32<=ord(c)<=126 for c in value)


def key_name(value):
    if type(value) is int:
        if 32<=value<=126:return chr(value)
        value=next((name for name,(code,_) in KEYS.items() if code==value),None)
    if type(value) is not str or not value:raise ValueError('Key requires a printable character or known key name')
    if len(value)==1 and 32<=ord(value)<=126:return value
    value=value.upper()
    if value not in KEYS:raise ValueError('Unknown keyboard key')
    return value


def key_info(value):return (ord(value),1) if len(value)==1 else KEYS[value]


def pane_for(state):
    root=rt().task_root(state);value=root.values.get('DEVICE_STAT',rt().UNINITIALIZED)
    while isinstance(value,rt().Reference):value=value.raw()
    if value is rt().UNINITIALIZED:return 1
    if type(value) is not int or not 1<=value<=9:raise rt().KarelRuntimeError('DEVICE_STAT requires pane 1..9')
    return value


class KeyboardInput:
    """No host keyboard capture; events come only from configured or fed data."""
    def __init__(self,*,events=None,event_sequence=None,elapsed_ms=0,limit=500,history=None,sequence=0,request_sequence=0):
        for value in (elapsed_ms,sequence,request_sequence):
            if type(value) is not int or not 0<=value<=MAX_SEQUENCE:raise ValueError('Invalid keyboard clock/sequence')
        if type(limit) is not int or not 1<=limit<=4096:raise ValueError('Keyboard history limit requires 1..4096')
        self.elapsed_ms=elapsed_ms;self.limit=limit;self.sequence=sequence;self.request_sequence=request_sequence
        self.events=[];self.history=[];self._handles={};self._active={};self._frames={};self._domain=None
        if events is None:events=[]
        if type(events) is not list or len(events)>4096:raise ValueError('Keyboard event queue exceeds 4096')
        seen=set();highest=0
        for i,event in enumerate(events,1):
            if type(event) is not dict or set(event)-{'pane','at_ms','key','sequence'} or 'key' not in event:raise ValueError('Malformed keyboard event')
            pane=event.get('pane',1);at=event.get('at_ms',0);number=event.get('sequence',i)
            if type(pane) is not int or not 1<=pane<=9 or type(at) is not int or not 0<=at<=MAX_SEQUENCE or type(number) is not int or not 1<=number<=MAX_SEQUENCE or number in seen:raise ValueError('Invalid keyboard event pane/time/sequence')
            seen.add(number);highest=max(highest,number);self.events.append(dict(pane=pane,at_ms=at,key=key_name(event['key']),sequence=number))
        self.events.sort(key=lambda row:(row['at_ms'],row['sequence']))
        self.event_sequence=highest if event_sequence is None else event_sequence
        if type(self.event_sequence) is not int or not highest<=self.event_sequence<=MAX_SEQUENCE:raise ValueError('Invalid keyboard event sequence')
        if history is None:history=[]
        if type(history) is not list or len(history)>limit:raise ValueError('Keyboard history exceeds ring limit')
        previous=0
        for row in history:
            if type(row) is not dict or set(row)!={'sequence','request','program','operation','pane','outcome','data'}:raise ValueError('Malformed keyboard history row')
            if type(row['sequence']) is not int or not previous<row['sequence']<=sequence or type(row['request']) is not int or not 1<=row['request']<=request_sequence:raise ValueError('Invalid keyboard history IDs')
            if not printable(row['program']) or type(row['operation']) is not str or row['operation'] not in KEYBOARD_CALLS|{'ACT_TBL','DISCTRL_TBL','DISCTRL_FORM'} or row['outcome'] not in ('completed','timeout','cancelled','failed') or type(row['pane']) is not int or not 1<=row['pane']<=9:raise ValueError('Invalid keyboard history metadata')
            data=row['data']
            if type(data) is not dict or len(data)>8 or any(type(k) is not str or len(k)>32 for k in data):raise ValueError('Invalid keyboard history data')
            for value in data.values():
                if printable(value) or type(value) is int and -2147483648<=value<=MAX_SEQUENCE:continue
                if type(value) is list and len(value)<=35 and all(printable(item) for item in value):continue
                raise ValueError('Invalid keyboard history value')
            self.history.append(deepcopy(row));previous=row['sequence']

    def reserve(self):
        if self.request_sequence>=MAX_SEQUENCE or self.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Keyboard request/history sequence exhausted')

    def record(self,job,outcome,**data):
        if self.sequence>=MAX_SEQUENCE:return
        self.sequence+=1;self.history.append(dict(sequence=self.sequence,request=job['id'],program=rt().task_root(job['state']).program_name,
            operation=job['operation'],pane=job['pane'],outcome=outcome,data=data));del self.history[:-self.limit]

    def sync(self):
        if self._domain is not None and self._domain['scheduler'] is not None:
            delta=max(0,(self._domain['scheduler'].now_us-self._domain['anchor'])//1000)
            self.elapsed_ms=max(self.elapsed_ms,min(MAX_SEQUENCE,self._domain['base']+delta))

    def feed(self,key,*,pane=1,at_ms=None):
        self.sync();key=key_name(key);at_ms=self.elapsed_ms if at_ms is None else at_ms
        if type(pane) is not int or not 1<=pane<=9 or type(at_ms) is not int or not 0<=at_ms<=MAX_SEQUENCE:raise ValueError('Invalid keyboard event pane/time')
        if len(self.events)>=4096 or self.event_sequence>=MAX_SEQUENCE:raise ValueError('Keyboard event capacity exhausted')
        self.event_sequence+=1;self.events.append(dict(pane=pane,at_ms=at_ms,key=key,sequence=self.event_sequence));self.events.sort(key=lambda row:(row['at_ms'],row['sequence']))

    def feed_text(self,text,*,pane=1,at_ms=None):
        if not printable(text,4096):raise ValueError('feed_text requires bounded printable ASCII')
        if len(self.events)+len(text)>4096 or self.event_sequence+len(text)>MAX_SEQUENCE:raise ValueError('Keyboard event capacity exhausted')
        self.sync();at_ms=self.elapsed_ms if at_ms is None else at_ms
        if type(pane) is not int or not 1<=pane<=9 or type(at_ms) is not int or not 0<=at_ms<=MAX_SEQUENCE:raise ValueError('Invalid keyboard event pane/time')
        for char in text:self.feed(char,pane=pane,at_ms=at_ms)

    def open_for(self,state,handle,mode,name,line=None):
        mode=rt().ascii_string(mode,line).upper();mode={'RO':'R','RW':'RW','UD':'RW'}.get(mode,mode)
        if handle.owner is not None or handle.binary or handle.xml or mode not in ('R','RW') or len(self._handles)>=256:raise rt().KarelRuntimeError('Keyboard FILE requires an available text input handle',line)
        pane=pane_for(state);match=re.fullmatch(r'WD:([A-Za-z_][A-Za-z_0-9]{0,3})/TPKB',name,re.I);echo=None
        if match:
            pendant=state.execution.require('pendant',line);echo=rt().FileHandle();pendant.open_for(state,echo,'RW','WD:'+match[1],line)
            name=echo.name+'/TPKB'
        elif name.upper()=='KB:TPKB':name='KB:TPKB'
        else:raise rt().KarelRuntimeError('Keyboard endpoint requires KB:TPKB or WD:name/TPKB',line)
        handle.owner=self;handle.name=name;handle.logical_name=None;handle.mode=mode;handle.position=0;handle.status=0
        self._handles[handle]=dict(pane=pane,echo=echo,state=state,past=[])

    def window_handle(self,handle):
        binding=self._handles.get(handle)
        return None if handle.owner is not self or binding is None else binding['echo']

    def write(self,handle,data,line=None):
        echo=self.window_handle(handle)
        if echo is None or handle.mode=='R':raise rt().KarelRuntimeError('Keyboard FILE has no writable window',line)
        echo.owner.write(echo,data,line);handle.position+=len(data);handle.status=0

    def close(self,handle,line=None):
        if handle.owner is not self or handle not in self._handles:raise rt().KarelRuntimeError('Keyboard FILE is not open',line)
        if any(job.get('handle') is handle for job in self._active.values()):raise rt().KarelRuntimeError('Finish or stop READ_KB before closing its FILE',line)
        binding=self._handles.pop(handle)
        if binding['echo'] is not None:binding['echo'].owner.close(binding['echo'],line)
        handle.owner=None;handle.xml_session=None

    def close_all(self):
        if self._active:raise ValueError('Finish or stop active keyboard requests before cleanup')
        for handle in list(self._handles):self.close(handle)
        self._frames.clear()

    def start(self,state,operation,pane,interest,handle=None):
        self.reserve();self.sync()
        if len(self._active)>=64:return None
        scheduler=state._scheduler;domain=scheduler if scheduler is not None else rt().task_root(state)
        if self._domain is not None and self._domain['identity'] is not domain:return None
        if self._domain is None:self._domain=dict(identity=domain,scheduler=scheduler,anchor=0 if scheduler is None else scheduler.now_us,base=self.elapsed_ms)
        self.request_sequence+=1;job=dict(id=self.request_sequence,state=state,operation=operation,pane=pane,interest=interest,handle=handle,suspended=set(),text='',cursor=0)
        self._active[job['id']]=job;return job

    def end(self,job):
        self.sync();self._active.pop(job['id'],None)
        if not self._active:self._domain=None

    def event(self,job):
        self.sync()
        if job['suspended']:return None
        for event in list(self.events):
            if event['pane']!=job['pane'] or event['at_ms']>self.elapsed_ms:continue
            _,category=key_info(event['key'])
            owners=[reader for reader in self._active.values() if reader['pane']==job['pane'] and reader['interest']&category]
            eligible=[reader for reader in owners if not reader['suspended']]
            if eligible and min(eligible,key=lambda reader:reader['id']) is not job:continue
            if not eligible and owners:continue
            self.events.remove(event);return event
        return None

    def wait(self,state,job,deadline,line=None):
        self.sync()
        if deadline is not None and self.elapsed_ms>=deadline:return False
        future=[event['at_ms'] for event in self.events if event['pane']==job['pane'] and event['at_ms']>self.elapsed_ms]
        if state._scheduler is None and deadline is None and not future:raise rt().KarelRuntimeError('Indefinite standalone keyboard wait needs explicit queued input',line)
        delay=min([10]+[at-self.elapsed_ms for at in future]+([] if deadline is None else [deadline-self.elapsed_ms]))
        delay=max(1,delay);due=min(MAX_SEQUENCE,self.elapsed_ms+delay)
        yield from rt().delay_execution(state,delay,line)
        if state._scheduler is None:self.elapsed_ms=max(self.elapsed_ms,due)
        else:self.sync()
        yield from rt().checkpoint(state,line)
        return deadline is None or self.elapsed_ms<=deadline

    def echo(self,job,field,text,line=None):
        if field is None:return
        pendant,window,row,col,width=field
        pendant.paint_fields(job['state'],window,[(row,col,text[:width].ljust(width))],line)

    def edit(self,state,operation,pane,initial,capacity,accept,terminate,timeout,*,handle=None,field=None,allowed=None,validate=None,line=None):
        job=self.start(state,operation,pane,accept|terminate,handle)
        if job is None:return None
        text=initial;cursor=len(text);past=self._handles[handle]['past'] if handle is not None else [];history_index=len(past);steps=0;complete=False
        deadline=None if timeout==-1 else min(MAX_SEQUENCE,self.elapsed_ms+timeout)
        try:
            self.echo(job,field,text,line)
            while True:
                job.update(text=text,cursor=cursor)
                if capacity and len(text)>=capacity:
                    term=KEYBOARD_CONSTANTS['KY_FULL'];status=0;break
                event=self.event(job)
                if event is None:
                    if not (yield from self.wait(state,job,deadline,line)):
                        term=KEYBOARD_CONSTANTS['KY_TIMEOUT'];status=4;break
                    continue
                steps+=1;code,category=key_info(event['key']);key=event['key']
                if terminate&category:term=code;status=0;break
                if steps>=4096:term=0;status=5;break
                if not accept&category:continue
                if len(key)==1:
                    if allowed is None or key in allowed:
                        if len(text)<capacity:text=text[:cursor]+key+text[cursor:];cursor+=1
                elif accept&1:
                    if key=='DELETE' and cursor:text=text[:cursor-1]+text[cursor:];cursor-=1
                    elif key=='LEFT':cursor=max(0,cursor-1)
                    elif key=='RIGHT':cursor=min(len(text),cursor+1)
                    elif key=='HOME':cursor=0
                    elif key=='END':cursor=len(text)
                    elif key in ('UP','DOWN') and past:
                        history_index=max(0,history_index-1) if key=='UP' else min(len(past),history_index+1)
                        text=(past[history_index] if history_index<len(past) else initial)[:capacity];cursor=len(text)
                self.echo(job,field,text,line)
            if status==0 and validate is not None and term in (13,1008,KEYBOARD_CONSTANTS['KY_FULL']):
                checked=validate(text)
                if checked is None:status=1
                else:text=checked
            self.echo(job,field,text,line)
            if handle is not None:
                handle.status=status
                if status==0 and text and (not past or past[-1]!=text):past.append(text);del past[:-32]
            self.record(job,'timeout' if status==4 else 'completed' if status==0 else 'failed',text=text,term=term,status=status)
            complete=True;return text,term,status
        except BaseException as error:
            outcome='cancelled' if isinstance(error,(GeneratorExit,rt().KarelAbort,rt().KarelStop)) else 'failed'
            self.record(job,outcome,text=text,term=0,status=6);complete=True;raise
        finally:
            if not complete:self.record(job,'cancelled',text=text,term=0,status=6)
            self.end(job)

    def push_pop(self,state,name,args,line=None):
        status=args[-1]
        try:
            if args[0].upper()!='TPKB':status.set(1,line);return
            pane=pane_for(state)
            if name=='PUSH_KEY_RD':
                mask=args[1]
                if not 0<=mask<=255:status.set(1,line);return
                if len(self._frames)>=64:status.set(5,line);return
                self.reserve();self.request_sequence+=1;token=self.request_sequence
                readers=[job for job in self._active.values() if job['pane']==pane and job['interest']&mask]
                for job in readers:job['suspended'].add(token)
                frame=dict(id=token,state=state,operation=name,pane=pane,readers=[job['id'] for job in readers],owner=rt().task_root(state))
                self._frames[token]=frame;args[2].set(token,line);self.record(frame,'completed',mask=mask,suspended=len(readers));status.set(0,line)
            else:
                frame=self._frames.get(args[1])
                if frame is None or frame['pane']!=pane or frame['owner'] is not rt().task_root(state):status.set(3,line);return
                self._frames.pop(frame['id'])
                for job in self._active.values():job['suspended'].discard(frame['id'])
                row=dict(frame,operation=name);self.record(row,'completed',resumed=sum(number in self._active for number in frame['readers']));status.set(0,line)
        except ValueError:status.set(1,line)

    def field_for(self,state,handle,capacity):
        if handle.noecho:return None
        echo=self.window_handle(handle)
        if echo is None:return None
        pendant=echo.owner;binding=pendant._handles[echo];window=pendant.windows[binding['window']]
        cursor=window['cursor'] if window['options']&1 else binding['cursor']
        return pendant,binding['window'],cursor['row'],cursor['col'],min(capacity,window['cols']-cursor['col']+1)

    def read(self,state,args,line=None):
        handle,output,size,accept,terminate,timeout,initial,count,term,status=args
        binding=self._handles.get(handle)
        if handle.owner is not self or binding is None or handle.mode not in ('R','RW'):status.set(1,line);return
        if any(job.get('handle') is handle for job in self._active.values()):status.set(2,line);return
        capacity=min(size,output.spec[1])
        if size<0 or size>254 or not 0<=accept<=255 or not 0<=terminate<=255 or not -1<=timeout<=86400000 or not printable(initial) or len(initial)>capacity:status.set(1,line);return
        result=yield from self.edit(state,'READ_KB',binding['pane'],initial,capacity,accept,terminate,timeout,handle=handle,field=self.field_for(state,handle,capacity),line=line)
        if result is None:status.set(2,line);return
        text,key,code=result;output.set(text,line);count.set(len(text),line);term.set(key,line);status.set(code,line)

    def dictionary_lines(self,state,name,element):
        bank=state.execution.require('dictionaries');tokens=bank.element(state,name,element)
        return ''.join(token[1] if token[0]=='text' else '\n' if token[0]=='newline' else '' for token in tokens)

    def alph(self,state,args,line=None):
        from .pendant import ordinary_name,PENDANT_CONSTANTS
        window,row,col,target,name,element,term,status=args;pendant=state.execution.require('pendant',line);pane=pane_for(state)
        if pendant.menus.get(str(pane),{}).get('menu') not in (PENDANT_CONSTANTS['SPI_TPUSER'],PENDANT_CONSTANTS['SPI_TPUSER2']):status.set(9093,line);return
        try:
            window=ordinary_name(window);surface=pendant.windows.get(window)
            if surface is None or not 1<=row<=surface['rows'] or not 1<=col<=surface['cols']:status.set(1,line);return
            initial=rt().require(target.raw(),line)
            if not printable(initial):status.set(1,line);return
            if name.upper()=='COMM':allowed=None
            elif name.upper()=='PROG':allowed=set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789')
            else:
                text=self.dictionary_lines(state,name,element);rows=text.split('\n')
                if not 1<=len(rows)<=5 or text.endswith('\n'):status.set(1,line);return
                allowed=set(text.replace('\n',''))
            field=pendant,window,row,col,min(target.spec[1],surface['cols']-col+1)
        except ValueError:status.set(1,line);return
        validate=(lambda text:text.upper() if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',text) else None) if name.upper()=='PROG' else None
        result=yield from self.edit(state,'DISCTRL_ALPH',pane,initial,target.spec[1],1|4|16|32|64,8|2|128,-1,field=field,allowed=allowed,validate=validate,line=line)
        if result is None:status.set(2,line);return
        text,key,code=result
        if code!=1:target.set(text,line)
        term.set(key,line);status.set(code,line)

    def menu(self,state,name,args,line=None):
        dictionary,element=args[:2];pull=name=='DISCTRL_PLMN';selected=args[3] if pull else args[2];term=args[-2];status=args[-1];maximum=9 if pull else 35
        try:
            if pull and not 1<=args[2]<=5:status.set(1,line);return
            items=[]
            for offset in range(maximum+1):
                text=self.dictionary_lines(state,dictionary,element+offset)
                if text=='':break
                if '\n' in text or offset==maximum:status.set(1,line);return
                items.append(text)
            width=12 if pull else 40 if len(items)<=4 else 16
            if not items or any(len(item)>width for item in items):status.set(1,line);return
            current=rt().integer(rt().require(selected.raw(),line),line)
            if not 1<=current<=len(items):status.set(1,line);return
        except ValueError:status.set(1,line);return
        pane=pane_for(state);job=self.start(state,name,pane,255)
        if job is None:status.set(2,line);return
        complete=False;steps=0
        try:
            job.update(items=list(items),selected=current)
            while True:
                event=self.event(job)
                if event is None:yield from self.wait(state,job,None,line);continue
                steps+=1;key=event['key'];code,_=key_info(key)
                if key in ('ENTER','SELECT','PREV','NEW_MENU','NEXT') or key.startswith('F') and key in KEYS:break
                if steps>=4096:
                    self.record(job,'failed',items=items,selected=current,term=0,status=5);complete=True;status.set(5,line);return
                if key=='UP':current=max(1,current-1)
                elif key=='DOWN':current=min(len(items),current+1)
                elif key=='LEFT':current=max(1,current-(1 if pull else 7))
                elif key=='RIGHT':current=min(len(items),current+(1 if pull else 7))
                job['selected']=current
            selected.set(current,line);term.set(code,line);status.set(0,line)
            self.record(job,'completed',items=items,selected=current,term=code,status=0);complete=True
        except BaseException as error:
            outcome='cancelled' if isinstance(error,(GeneratorExit,rt().KarelAbort,rt().KarelStop)) else 'failed'
            self.record(job,outcome,items=items,selected=current,term=0,status=6);complete=True;raise
        finally:
            if not complete:self.record(job,'cancelled',items=items,selected=current,term=0,status=6)
            self.end(job)

    def invoke(self,state,name,args,line=None):
        if name in ('PUSH_KEY_RD','POP_KEY_RD'):return self.push_pop(state,name,args,line)
        if name=='READ_KB':return self.read(state,args,line)
        if name=='DISCTRL_ALPH':return self.alph(state,args,line)
        return self.menu(state,name,args,line)

    def snapshot(self):
        self.sync()
        active=[dict(request=job['id'],operation=job['operation'],pane=job['pane'],suspended=bool(job['suspended']),text=job['text'],cursor=job['cursor'],**({'items':list(job['items']),'selected':job['selected']} if 'items' in job else {})) for job in self._active.values()]
        return dict(events=deepcopy(self.events),event_sequence=self.event_sequence,elapsed_ms=self.elapsed_ms,limit=self.limit,history=deepcopy(self.history),sequence=self.sequence,request_sequence=self.request_sequence,
            open_files=sorted(handle.name for handle in self._handles),active=active,suspensions=len(self._frames))

    def to_config(self):
        if self._handles or self._active or self._frames:raise ValueError('Close keyboard FILEs, finish reads and POP suspension frames before saving context')
        result=self.snapshot()
        for key in ('open_files','active','suspensions'):result.pop(key)
        return result

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'events','event_sequence','elapsed_ms','limit','history','sequence','request_sequence'}:raise ValueError('Unknown keyboard configuration fields')
        return cls(**config)
