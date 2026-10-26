"""PC byte-buffer builders and an explicit bounded offline event outbox."""
from copy import deepcopy
import math
import re
import struct


PC_NAMES={'ADD_BYNAMEPC','ADD_INTPC','ADD_REALPC','ADD_STRINGPC','SEND_DATAPC','SEND_EVENTPC'}
MAX_SEQUENCE=2147483646


def rt():
    from . import runtime
    return runtime


def buffer_values(spec,value,line=None):
    runtime=rt()
    if (spec[0]!='ARRAY' or len(runtime.array_dimensions(spec))!=1
            or runtime.array_leaf_spec(spec)!=('BYTE',)
            or type(runtime.array_dimensions(spec)[0]) is not int
            or not 1<=runtime.array_dimensions(spec)[0]<=244):
        raise runtime.KarelRuntimeError('PC buffer requires a one-dimensional BYTE ARRAY of 1..244 bytes',line)
    if value is runtime.UNINITIALIZED:return [runtime.UNKNOWN_BYTE]*runtime.array_dimensions(spec)[0]
    if type(value) is not runtime.Array or value.spec!=spec or len(value.values)!=runtime.array_dimensions(spec)[0]:
        raise runtime.KarelRuntimeError('Malformed PC BYTE buffer storage',line)
    for item in value.values:
        if item is runtime.UNKNOWN_BYTE or item is runtime.UNINITIALIZED:continue
        if type(item) is not int or not 0<=item<=255:
            raise runtime.KarelRuntimeError('Malformed PC BYTE contents',line)
    return list(value.values)


def item_bytes(kind,value,line=None):
    runtime=rt()
    if kind=='STRING':
        value=runtime.ascii_string(value,line)
        if len(value)>254:raise runtime.KarelRuntimeError('PC STRING exceeds 254 characters',line)
        return b'\x00\xd1'+bytes((len(value),))+value.encode('ascii')+b'\0'
    if kind not in ('INTEGER','REAL'):raise runtime.KarelRuntimeError('PC items require INTEGER, REAL or STRING',line)
    value=runtime.checked((kind,),value,line)
    try:return (b'\x00\x10' if kind=='INTEGER' else b'\x00\x11')+struct.pack('>i' if kind=='INTEGER' else '>f',value)
    except (OverflowError,struct.error) as exc:
        raise runtime.KarelRuntimeError('PC numeric item cannot be represented',line) from exc


def decode_packet(values,line=None):
    """Decode the common ADD_* envelope; stop at its checked end marker."""
    runtime=rt();offset=0;items=[]
    if not 1<=len(values)<=244:raise runtime.KarelRuntimeError('PC packet requires 1..244 bytes',line)
    def take(count):
        nonlocal offset
        selected=values[offset:offset+count]
        if len(selected)!=count or any(type(value) is not int or not 0<=value<=255 for value in selected):
            raise runtime.KarelRuntimeError('PC packet contains truncated or unknown data',line)
        offset+=count;return bytes(selected)
    while True:
        kind=int.from_bytes(take(2),'big')
        if kind==0:return bytes(values[:offset]),items
        if kind==16:
            value=runtime.checked(('INTEGER',),int.from_bytes(take(4),'big',signed=True),line);label='INTEGER'
        elif kind==17:
            value=struct.unpack('>f',take(4))[0];label='REAL'
            if not math.isfinite(value):raise runtime.KarelRuntimeError('PC REAL must be finite',line)
        elif kind==209:
            size=take(1)[0];data=take(size)
            if size>254 or take(1)!=b'\0' or not data.isascii():
                raise runtime.KarelRuntimeError('PC STRING requires its length, ASCII text and NUL terminator',line)
            value=data.decode('ascii');label='STRING'
        else:raise runtime.KarelRuntimeError('Unsupported PC typed-packet item',line)
        items.append({'type':label,'value':value})


class PcExchange:
    """No transport or callbacks: producers publish inspectable local events."""
    def __init__(self,capacity=1024,*,packet_format='typed'):
        if type(capacity) is not int or not 1<=capacity<=32767:raise ValueError('PC outbox capacity requires 1..32767')
        if type(packet_format) is not str or packet_format not in ('typed','raw'):raise ValueError('PC packet format requires typed or raw')
        self.capacity=capacity;self.packet_format=packet_format;self.sequence=0;self.messages=[]

    def send(self,event,buffer=None,line=None):
        runtime=rt();event=runtime.integer(event,line)
        if not 0<=event<=255:return 2
        payload=None
        if buffer is not None:
            try:
                if type(buffer) is bytes:
                    if not 1<=len(buffer)<=244:return 4
                    values=list(buffer)
                else:
                    from .extended import VariableValue
                    if type(buffer) not in (VariableValue,runtime.Array):return 4
                    values=buffer_values(buffer.spec,buffer.value if type(buffer) is VariableValue else buffer,line)
                if self.packet_format=='typed':payload,_=decode_packet(values,line)
                else:
                    if any(type(value) is not int for value in values):return 4
                    payload=bytes(values)
            except runtime.KarelRuntimeError:return 4
        if len(self.messages)>=self.capacity or self.sequence>=MAX_SEQUENCE:return 5
        self.sequence+=1
        self.messages.append({'sequence':self.sequence,'event':event,'data':None if payload is None else payload.hex()})
        return 0

    def drain(self,count=None):
        count=len(self.messages) if count is None else count
        if type(count) is not int or not 0<=count<=len(self.messages):raise ValueError('PC drain count exceeds queued events')
        result=deepcopy(self.messages[:count]);del self.messages[:count];return result

    def snapshot(self):return deepcopy(self.messages)

    def to_config(self):
        return {'capacity':self.capacity,'format':self.packet_format,'sequence':self.sequence,'messages':self.snapshot()}

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'capacity','format','sequence','messages'}:raise ValueError('Unknown PC outbox fields')
        result=cls(config.get('capacity',1024),packet_format=config.get('format','typed'))
        sequence=config.get('sequence',0);rows=config.get('messages',[])
        if type(sequence) is not int or not 0<=sequence<=MAX_SEQUENCE:raise ValueError('Invalid PC event sequence')
        if type(rows) is not list or len(rows)>result.capacity:raise ValueError('PC event queue exceeds capacity')
        previous=0
        for row in rows:
            if type(row) is not dict or set(row)!={'sequence','event','data'}:raise ValueError('Invalid saved PC event')
            if type(row['sequence']) is not int or not previous<row['sequence']<=sequence:raise ValueError('PC queued sequences must increase within their saved sequence')
            if type(row['event']) is not int or not 0<=row['event']<=255:raise ValueError('PC event number requires 0..255')
            data=row['data']
            if data is not None:
                if type(data) is not str or not 2<=len(data)<=488 or not re.fullmatch(r'(?:[0-9a-fA-F]{2})+',data):
                    raise ValueError('Invalid or excessive saved PC bytes')
                payload=bytes.fromhex(data)
                if result.packet_format=='typed':
                    try:prepared,_=decode_packet(payload)
                    except rt().KarelRuntimeError as exc:raise ValueError(str(exc)) from exc
                    if prepared!=payload:raise ValueError('Saved PC typed packet has unused trailing bytes')
                data=payload.hex()
            result.messages.append({'sequence':row['sequence'],'event':row['event'],'data':data});previous=row['sequence']
        result.sequence=sequence;return result


def invoke(state,operation,args,line=None):
    runtime=rt();context=state.execution
    if operation.startswith('SEND_'):
        bank=context.require('pc_exchange',line)
        args[-1].set(bank.send(args[0],args[1] if operation=='SEND_DATAPC' else None,line),line);return
    reference,index=args[:2];status=args[-1]
    try:values=buffer_values(reference.spec,reference.raw(),line)
    except runtime.KarelRuntimeError:status.set(4,line);return
    try:position=runtime.integer(index.raw(),line)
    except runtime.KarelRuntimeError:status.set(2,line);return
    if not 1<=position<=len(values):status.set(2,line);return
    if operation=='ADD_BYNAMEPC':
        program=runtime.ascii_string(args[2],line).strip() or state.program_name
        path=runtime.ascii_string(args[3],line)
        if path.startswith('$'):status.set(1,line);return
        try:source=context.resolve(state,program,path,line)
        except runtime.KarelRuntimeError:status.set(1,line);return
        kind=source.spec[0];value=source.raw()
    else:kind={'ADD_INTPC':'INTEGER','ADD_REALPC':'REAL','ADD_STRINGPC':'STRING'}[operation];value=args[2]
    try:payload=item_bytes(kind,value,line)
    except runtime.KarelRuntimeError:status.set(4,line);return
    end=position-1+len(payload)
    if end+2>len(values):status.set(3,line);return
    values[position-1:end+2]=[*payload,0,0]
    # Ordinary ARRAY checks require every BYTE initialized. Builders deliberately
    # preserve unknown unused tails after checking the complete storage shape.
    prepared=runtime.Array(reference.spec);prepared.values[:]=values
    reference.storage[reference.key]=runtime.replace_value(reference.raw(),prepared)
    index.set(end+1,line);status.set(0,line)
