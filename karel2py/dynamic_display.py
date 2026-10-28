"""Read-only live bindings and deterministic headless dynamic display updates."""
from copy import deepcopy


DYNAMIC_DISPLAY_CALLS={prefix+kind for prefix in ('INI_DYN_DIS','CNC_DYN_DIS') for kind in 'BEIPRS'}
MAX_SEQUENCE=2147483646


def rt():
    from . import runtime
    return runtime


def marker(binding,char):return char*max(1,binding['width'])


def checked_format(text,kind):
    from .dictionaries import FORMAT
    if type(text) is not str or len(text)>254:raise ValueError('Dynamic format requires bounded text')
    match=FORMAT.fullmatch(text)
    if match is None or match[5] is not None:raise ValueError('Dynamic format requires one conversion')
    flags,width,precision,conversion,_=match.groups()
    if len(set(flags))!=len(flags) or int(width or 0)>254 or precision is not None and int(precision)>254:raise ValueError('Invalid dynamic format bounds/flags')
    if conversion=='%':
        if flags or width or precision is not None:raise ValueError('Literal percent has no format fields')
    elif conversion not in {'I':'doxXu','R':'feEgG','S':'s'}[kind]:raise ValueError('Dynamic format disagrees with variable type')
    if kind=='S' and ('+' in flags or '0' in flags):raise ValueError('STRING display has no numeric flags')
    return match


class DynamicDisplays:
    """Explicit checkpoint clock; active references are never serialized."""
    def __init__(self,*,quantum_ms=1,elapsed_ms=0,limit=256,sequence=0):
        if type(quantum_ms) is not int or not 1<=quantum_ms<=86400000:raise ValueError('Display quantum requires 1..86400000 ms')
        if type(elapsed_ms) is not int or not 0<=elapsed_ms<=MAX_SEQUENCE:raise ValueError('Invalid display elapsed milliseconds')
        if type(limit) is not int or not 1<=limit<=256:raise ValueError('Display binding limit requires 1..256')
        if type(sequence) is not int or not 0<=sequence<=MAX_SEQUENCE:raise ValueError('Invalid display binding sequence')
        self.quantum_ms=quantum_ms;self.elapsed_ms=elapsed_ms;self.limit=limit;self.sequence=sequence;self._bindings=[]

    @property
    def active_count(self):return len(self._bindings)

    def checkpoint(self,state,line=None):
        if not self._bindings:return
        delta=min(self.quantum_ms,MAX_SEQUENCE-self.elapsed_ms)
        try:self.advance(delta,state=state,line=line)
        except rt().KarelRuntimeError:
            # A background repaint failure must not block source cancellation.
            self.elapsed_ms+=delta
            for binding in self._bindings:
                if binding['next_due']<=self.elapsed_ms:binding['last_status']=5

    def sample(self,binding,line=None):
        with rt()._numeric_scope('pythonic'):return self._sample(binding,line)

    def _sample(self,binding,line=None):
        runtime=rt();kind=binding['kind'];reference=binding['reference']
        if kind=='P':
            bank=binding['ports'];bank.poll_pulses(line)
            value=bank.values.get(binding['port'],runtime.UNINITIALIZED)
        else:value=reference.raw()
        if value is runtime.UNINITIALIZED or value is runtime.UNKNOWN_BYTE:return marker(binding,'*'),1
        try:
            if kind in 'BEP':
                if kind=='B' or kind=='P' and binding['port_kind']=='BOOLEAN':
                    index=int(runtime.boolean(value,line))
                else:index=runtime.integer(value,line)
                labels=binding['labels'].raw()
                if not 0<=index<len(labels.values):return marker(binding,'?'),2
                text=labels.values[index]
                if text is runtime.UNINITIALIZED:return marker(binding,'*'),1
                text=runtime.ascii_string(text,line)
            else:
                from .dictionaries import format_value
                text='%' if binding['match'][4]=='%' else format_value(binding['match'],reference,line)
            if any(not 32<=ord(char)<=126 for char in text):return marker(binding,'?'),4
        except (ValueError,OverflowError,runtime.KarelRuntimeError):return marker(binding,'?'),4
        return text,0

    def field(self,binding,text):
        available=binding['pendant'].windows[binding['window']]['cols']-binding['col']+1
        return text[:binding['width']].ljust(binding['width']) if binding['width'] else text[:available]

    def advance(self,milliseconds,*,force=False,state=None,line=None):
        if type(milliseconds) is not int or milliseconds<0 or self.elapsed_ms+milliseconds>MAX_SEQUENCE:raise ValueError('Display clock advance requires bounded nonnegative milliseconds')
        if type(force) is not bool:raise ValueError('force must be BOOLEAN')
        moment=self.elapsed_ms+milliseconds;prepared=[];groups={}
        for binding in self._bindings:
            if not force and binding['next_due']>moment:continue
            text,status=self.sample(binding,line);text=self.field(binding,text)
            prepared.append((binding,text,status))
            # Repaint due fields even if text is unchanged, preserving registration order.
            key=binding['pendant'],binding['window']
            groups.setdefault(key,[]).append((binding['row'],binding['col'],text))
        for pendant in {key[0] for key in groups}:
            if pendant.sequence+sum(key[0] is pendant for key in groups)>MAX_SEQUENCE:raise rt().KarelRuntimeError('Display request sequence exhausted',line)
        for (pendant,window),fields in groups.items():
            owner=state or next(binding['state'] for binding,_,_ in prepared if binding['pendant'] is pendant and binding['window']==window)
            pendant.paint_fields(owner,window,fields,line)
        self.elapsed_ms=moment
        for binding,text,status in prepared:
            binding.update(last_text=text,last_status=status,next_due=moment+binding['interval'])
        return len(prepared)

    def cancel(self,selected,state=None,line=None):
        if not selected:return 3
        selected_ids={binding['id'] for binding in selected};groups={}
        for binding in selected:
            if binding['width']:
                groups.setdefault((binding['pendant'],binding['window']),[]).append((binding['row'],binding['col'],' '*binding['width']))
        # Restore surviving fields from their last sample without bypassing intervals.
        for (pendant,window),fields in groups.items():
            fields.extend((binding['row'],binding['col'],binding['last_text']) for binding in self._bindings
                if binding['id'] not in selected_ids and binding['pendant'] is pendant and binding['window']==window)
            owner=state or next(binding['state'] for binding in selected if binding['pendant'] is pendant and binding['window']==window)
            pendant.paint_fields(owner,window,fields,line,cleanup=True)
        self._bindings[:]=[binding for binding in self._bindings if binding['id'] not in selected_ids]
        return 0

    def close_all(self):return self.cancel(list(self._bindings))

    def invoke(self,state,name,args,line=None):
        from .extended import PORT_TYPES
        runtime=rt();status=args[-1];kind=name[-1];port=kind=='P';offset=1 if port else 0
        try:
            from .pendant import ordinary_name
            window=ordinary_name(args[1+offset]);pendant=state.execution.require('pendant',line)
            if window not in pendant.windows:status.set(3,line);return
            if port:
                bank=state.execution.require('ports',line);code,number=args[:2];key=bank.type_codes.get(code)
                if key not in bank.counts or not 1<=number<=bank.counts[key] or PORT_TYPES[key] not in ('BOOLEAN','INTEGER'):status.set(1,line);return
                identity=(key,number)
            else:identity=frozenset(runtime._reference_cells(args[0]))
            if name.startswith('CNC_'):
                selected=[binding for binding in self._bindings if binding['kind']==kind and binding['window']==window
                    and binding['pendant'] is pendant and binding['identity']==identity and (not port or binding['ports'] is bank)]
                status.set(self.cancel(selected,state,line),line);return
            width,attributes,size,row,col,interval=args[2+offset:8+offset]
            surface=pendant.windows[window]
            if not 0<=width<=256 or not 0<=attributes<=15 or size not in (0,2) or not 1<=row<=surface['rows'] or not 1<=col<=surface['cols'] or width>surface['cols']-col+1 or not 1<=interval<=86400000:
                status.set(1,line);return
            if len(self._bindings)>=self.limit or self.sequence>=MAX_SEQUENCE:status.set(5,line);return
            binding=dict(id=self.sequence+1,kind=kind,window=window,width=width,attributes=attributes,char_size=size,row=row,col=col,
                interval=interval,reference=None if port else args[0],identity=identity,state=state,pendant=pendant,
                program=state.program_name,owner=runtime.task_root(state).program_name,line=line or 0,
                buffer_size=None,format=None,labels=None,match=None,next_due=self.elapsed_ms+interval)
            if kind in 'BEP':
                labels=args[8+offset]
                if kind=='B' and len(labels.raw().values)<2:status.set(1,line);return
                binding['labels']=labels
                if port:
                    binding.update(ports=bank,port=identity,port_kind=PORT_TYPES[key])
                    if binding['port_kind']=='BOOLEAN' and len(labels.raw().values)<2:status.set(1,line);return
            else:
                binding['buffer_size']=args[8];binding['format']=args[9];binding['match']=checked_format(args[9],kind)
            text,code=self.sample(binding,line);text=self.field(binding,text)
            pendant.paint_fields(state,window,[(row,col,text)],line)
            binding.update(last_text=text,last_status=code)
            self.sequence+=1;self._bindings.append(binding);status.set(0,line)
        except ValueError:status.set(1,line)

    def snapshot(self):
        bindings=[]
        for binding in self._bindings:
            data={key:binding[key] for key in ('id','kind','window','width','attributes','char_size','row','col','interval','program','owner','line','buffer_size','format','next_due','last_text','last_status')}
            data['source_key']=None if binding['reference'] is None else str(binding['reference'].key)
            if binding['kind']=='P':data['port']=list(binding['port'])
            bindings.append(data)
        return dict(quantum_ms=self.quantum_ms,elapsed_ms=self.elapsed_ms,limit=self.limit,sequence=self.sequence,bindings=deepcopy(bindings))

    def to_config(self):
        if self._bindings:raise ValueError('Cancel dynamic display bindings before saving context')
        result=self.snapshot();result.pop('bindings');return result

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'quantum_ms','elapsed_ms','limit','sequence'}:raise ValueError('Unknown dynamic display configuration fields')
        return cls(**config)
