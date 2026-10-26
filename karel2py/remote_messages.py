"""Bounded offline mobile-message outboxes and deferred ZDT attachments."""
from copy import deepcopy
from io import BytesIO
import json
import re
from xml.etree import ElementTree


MAX_SEQUENCE=2147483646
NAMES=('QUEUE_ATTACH','RMCN_ALERT','RMCN_SEND')


def rt():
    from . import runtime
    return runtime


def text(value):
    if type(value) is not str or not value.isascii() or len(value)>254:
        raise ValueError('Message text requires at most 254 ASCII characters')
    return value


def message_type(value):
    value=text(value).upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',value):raise ValueError('Invalid explicit message type')
    return value


def file_name(value):
    value=text(value)
    if not value or '\\' in value or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('Attachment requires a relative portable file name')
    device,sep,path=value.partition(':')
    if sep:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,7}',device) or device.upper() in ('PIP','MF') or re.fullmatch(r'[CS][0-9]+',device.upper()):
            raise ValueError('Attachment requires an ordinary file device')
        value=device.upper()+':'+path
    else:path=value
    if ':' in path or any(part in ('','.','..') for part in path.split('/')):
        raise ValueError('Attachment file path must remain relative')
    return value


def attachments(value):
    runtime=rt()
    if type(value) is runtime.Array:
        if len(runtime.array_dimensions(value.spec))!=1 or runtime.array_leaf_spec(value.spec)[0]!='STRING':
            raise ValueError('Attachments require a one-dimensional STRING array')
        value=value.values
    if type(value) not in (list,tuple) or not 1<=len(value)<=32:
        raise ValueError('Attachments require 1..32 entries; use an empty string for none')
    names=[]
    for item in value:
        if text(item)=='':continue
        name=file_name(item)
        if name in names:raise ValueError('Duplicate attachment name')
        names.append(name)
    return names


def priority_value(value):
    if type(value) is not int or value not in (0,1):raise ValueError('Message priority requires 0 or 1')
    return value


def xml_document(data):
    """Bounded UTF-8 XML, without DTDs, entities or schema interpretation."""
    try:
        decoded=data.decode('utf-8-sig')
        if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b',decoded,re.I):return False
        depth=count=0
        for event,_ in ElementTree.iterparse(BytesIO(decoded.encode('utf-8')),events=('start','end')):
            if event=='start':
                depth+=1;count+=1
                if depth>64 or count>4096:return False
            else:depth-=1
        return True
    except (UnicodeError,ElementTree.ParseError,ValueError):return False


def read_file(files,name,*,delete,limit):
    """Preflight only the two explicit in-memory backends, without callbacks."""
    runtime=rt()
    from .extended import MemoryFiles
    from .devices import DeviceFiles
    if type(files) not in (MemoryFiles,DeviceFiles):return 4,None,None
    try:
        key=files.canonical(name) if type(files) is DeviceFiles else name
        files._check(key,b'')
        if type(files) is DeviceFiles:files.require_volume(key.split(':',1)[0],write=delete)
        if files._busy(key):return 3,None,None
        if key not in files.files:return 1,None,None
        if len(files.files[key])>min(files.limit,limit):return 5,None,None
        return 0,key,bytes(files.files[key])
    except runtime.KarelRuntimeError:return 4,None,None


class RemoteMessages:
    """Local publication and explicit host collection, without transport or timers."""
    def __init__(self,capacity=1024,*,limit=4*1024*1024,message_types=(),defaults=None):
        if type(capacity) is not int or not 1<=capacity<=32767:raise ValueError('Message capacity requires 1..32767')
        if type(limit) is not int or not 1<=limit<=64*1024*1024:raise ValueError('Message limit requires 1..64 MiB')
        if type(message_types) not in (list,tuple) or len(message_types)>32:raise ValueError('At most 32 explicit message types')
        names=[message_type(name) for name in message_types]
        if len(set(names))!=len(names):raise ValueError('Duplicate message type')
        if defaults is None:defaults={}
        if type(defaults) is not dict or set(defaults)-{'address','subject','url'}:raise ValueError('Unknown alert defaults')
        self.defaults={key:text(defaults.get(key,value)) for key,value in dict(address='',subject='iRConnect Alert',url='').items()}
        self.capacity=capacity;self.limit=limit;self.message_types=sorted(names)
        self.sequence=0;self.messages=[];self.pending={}

    @staticmethod
    def size(value):return len(json.dumps(value,ensure_ascii=True,separators=(',',':')).encode('ascii'))

    def used(self):return sum(self.size(row) for row in self.messages)+sum(self.size([key,row]) for key,row in self.pending.items())

    def room(self,row):
        return len(self.messages)<self.capacity and self.sequence<MAX_SEQUENCE and self.used()+self.size(row)<=self.limit

    def append(self,row):self.sequence+=1;self.messages.append(row)

    def alert(self,address,subject,message,url):
        try:
            row=dict(sequence=self.sequence+1,kind='alert',address=text(address) or self.defaults['address'],
                subject=text(subject) or self.defaults['subject'],message=text(message),url=text(url) or self.defaults['url'])
        except ValueError:return 2
        if not self.room(row):return 5
        self.append(row);return 0

    def queue_attach(self,name,paths,priority):
        try:key=message_type(name);row=dict(attachments=attachments(paths),priority=priority_value(priority))
        except ValueError:return 2
        if key not in self.message_types:return 1
        previous=self.size([key,self.pending[key]]) if key in self.pending else 0
        if self.used()-previous+self.size([key,row])>self.limit:return 5
        self.pending[key]=row;return 0

    def publish(self,name,data=b''):
        """Host publishes opaque ZDT data; SET_VAR does not implicitly send."""
        try:key=message_type(name)
        except ValueError:return 2
        if key not in self.message_types:return 1
        if type(data) is not bytes:return 4
        if len(data)>self.limit//2:return 5
        selection=deepcopy(self.pending.get(key,dict(attachments=[],priority=0)))
        row=dict(sequence=self.sequence+1,kind='typed',message_type=key,data=data.hex(),**selection)
        if not self.room(row):return 5
        self.append(row);return 0

    def send(self,files,xml_file,paths,priority):
        try:
            name=file_name(xml_file);paths=attachments(paths);priority=priority_value(priority)
            if name in paths:return 2
        except ValueError:return 2
        code,key,data=read_file(files,name,delete=True,limit=self.limit//2)
        if code:return code
        if not xml_document(data):return 4
        row=dict(sequence=self.sequence+1,kind='xml',xml_file=name,data=data.hex(),attachments=paths,priority=priority)
        if not self.room(row):return 5
        code=files.delete(key)
        if code:return code
        self.append(row);return 0

    def collect(self,sequence,files=None):
        """Consume one row and current attachments after a complete preflight."""
        if type(sequence) is not int or not 1<=sequence<=MAX_SEQUENCE:return 2,None
        selected=next((row for row in self.messages if row['sequence']==sequence),None)
        if selected is None:return 1,None
        result=deepcopy(selected);plan=[];collected=[];remaining=self.limit-self.size(result)
        for name in selected.get('attachments',[]):
            retained=name.upper().startswith('MD:')
            code,key,data=read_file(files,name,delete=not retained,limit=max(0,remaining//2))
            if code:return code,None
            row=dict(name=name,data=data.hex(),retained=retained);remaining-=self.size(row)
            if remaining<0:return 5,None
            collected.append(row)
            if not retained:plan.append(key)
        # No external callbacks or host I/O occur between preflight and commit.
        for key in plan:
            code=files.delete(key)
            if code:raise RuntimeError('Preflighted in-memory attachment deletion changed unexpectedly')
        if 'attachments' in result:result['attachments']=collected
        self.messages.remove(selected);return 0,result

    def snapshot(self):return deepcopy(self.messages)

    def to_config(self):
        return dict(capacity=self.capacity,limit=self.limit,message_types=list(self.message_types),defaults=dict(self.defaults),
            sequence=self.sequence,pending=deepcopy(self.pending),messages=self.snapshot())

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'capacity','limit','message_types','defaults','sequence','pending','messages'}:
            raise ValueError('Unknown remote-message fields')
        result=cls(config.get('capacity',1024),limit=config.get('limit',4*1024*1024),
            message_types=config.get('message_types',()),defaults=config.get('defaults'))
        sequence=config.get('sequence',0);pending=config.get('pending',{});rows=config.get('messages',[])
        if type(sequence) is not int or not 0<=sequence<=MAX_SEQUENCE:raise ValueError('Invalid message sequence')
        if type(pending) is not dict or len(pending)>32:raise ValueError('Invalid pending attachments')
        for key,row in pending.items():
            canonical=message_type(key)
            if canonical in result.pending or type(row) is not dict or set(row)!={'attachments','priority'}:
                raise ValueError('Invalid or duplicate pending attachment fields')
            if type(row['attachments']) is not list or any(item=='' for item in row['attachments']):raise ValueError('Noncanonical saved attachment list')
            if result.queue_attach(key,row['attachments'] or [''],row['priority']):raise ValueError('Invalid pending attachment selection')
        if type(rows) is not list or len(rows)>result.capacity:raise ValueError('Invalid message queue length')
        previous=0;used=result.used()
        for row in rows:
            if type(row) is not dict:raise ValueError('Invalid saved message row')
            kind=row.get('kind');number=row.get('sequence')
            if type(number) is not int or not previous<number<=sequence:raise ValueError('Queued message sequences must increase within saved sequence')
            if kind=='alert':
                if set(row)!={'sequence','kind','address','subject','message','url'}:raise ValueError('Invalid alert fields')
                prepared={key:text(row[key]) for key in ('address','subject','message','url')}
            elif kind in ('xml','typed'):
                fields={'sequence','kind','data','attachments','priority','xml_file' if kind=='xml' else 'message_type'}
                if set(row)!=fields:raise ValueError('Invalid queued message fields')
                paths=row['attachments']
                if type(paths) is not list or any(item=='' for item in paths):raise ValueError('Noncanonical saved attachment list')
                prepared=dict(attachments=attachments(paths or ['']),priority=priority_value(row['priority']))
                data=row['data']
                if type(data) is not str or len(data)>result.limit or not re.fullmatch(r'(?:[0-9a-fA-F]{2})*',data):raise ValueError('Invalid or excessive message payload')
                prepared['data']=data.lower()
                if kind=='xml':
                    name=file_name(row['xml_file'])
                    if name in prepared['attachments'] or not xml_document(bytes.fromhex(data)):raise ValueError('Invalid saved XML message')
                    prepared['xml_file']=name
                else:
                    name=message_type(row['message_type'])
                    if name not in result.message_types:raise ValueError('Unknown saved message type')
                    prepared['message_type']=name
            else:raise ValueError('Unknown saved message kind')
            prepared=dict(sequence=number,kind=kind,**prepared)
            used+=result.size(prepared)
            if used>result.limit:raise ValueError('Saved messages exceed byte budget')
            result.messages.append(prepared);previous=number
        result.sequence=sequence;return result


def invoke(state,operation,args,line=None):
    bank=state.execution.require('remote_messages',line)
    if operation=='RMCN_ALERT':code=bank.alert(*args[:-1])
    elif operation=='QUEUE_ATTACH':code=bank.queue_attach(*args[:-1])
    else:code=bank.send(state.execution.require('files',line),*args[:-1])
    args[-1].set(code,line)
