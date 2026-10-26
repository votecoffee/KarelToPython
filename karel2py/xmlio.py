"""Bounded ASCII XML input over explicitly opened offline FILE backends."""
from xml.parsers import expat
import re


XML_CONSTANTS={'ATR_XML':6,'AR_XML':6,'XML_SUCCESS':0,'XML_START':100,'XML_END':101,
    'XML_STEND':102,'XML_TXCONT':103,'XML_FUNCTION':1001,'XML_SCANLIM':1002,
    'XML_ERROR':-1,'XML_STATE':1,'XML_INVALID':2,'XML_CAPACITY':3,'XML_PARSE':4,'XML_LIMIT':5}
XML_NAMES=frozenset(('XML_ADDTAG','XML_REMTAG','XML_SCAN','XML_GETDATA','XML_SETVAR'))


def rt():
    from . import runtime
    return runtime


class RejectedXML(ValueError): pass


def xml_name(value): return bool(re.fullmatch(r'[A-Za-z_:][A-Za-z_0-9.:-]{0,253}',value))


class XMLInput:
    def __init__(self,handle,line=None):
        handle.require_open(line)
        if not handle.xml or handle.mode!='R' or handle.binary:
            raise rt().KarelRuntimeError('XML requires ATR_XML and a text FILE opened RO',line)
        if handle.position: raise rt().KarelRuntimeError('XML input must begin at byte zero',line)
        self.handle=handle;self.raw=bytes(handle.owner.files[handle.name]);self.tags=[]
        self.events=None;self.failed=5 if len(self.raw)>1024*1024 else None
        self.next=0;self.current=None;self.scan_line=1
        self.line_starts=[0] if self.failed else [0,*[m.end() for m in re.finditer(rb'\r\n|\r|\n',self.raw)]]

    def unchanged(self,line=None):
        if bytes(self.handle.owner.files[self.handle.name])!=self.raw:
            raise rt().KarelRuntimeError('XML input changed while open; close and reopen it',line)

    def add(self,name,count,case,ident,line=None):
        runtime=rt();name=runtime.ascii_string(name,line);count=runtime.integer(count,line)
        case=runtime.boolean(case,line);ident=runtime.integer(ident,line)
        if not xml_name(name) or not 1<=count<=254 or ident<=0 or ident in (1001,1002): return 2
        if any(row['ident']==ident or row['name'].upper()==name.upper() for row in self.tags): return 2
        if len(self.tags)>=128: return 5
        self.tags.append(dict(name=name,count=count,case=case,ident=ident));return 0

    def remove(self,name,line=None):
        name=rt().ascii_string(name,line)
        found=next((row for row in self.tags if (row['name']==name if row['case'] else row['name'].upper()==name.upper())),None)
        if found is None: return 2
        if self.current is not None and self.current['ident']==found['ident']: return 1
        self.tags.remove(found);return 0

    def parse(self,state,line=None):
        if self.events is not None or self.failed is not None: return
        if len(self.raw)>1024*1024: self.failed=5;return
        events=[];stack=[];parser=expat.ParserCreate();parser.ordered_attributes=True
        def reject(*args): raise RejectedXML('DTD and entity declarations are unsupported')
        def ascii_text(text):
            if not text.isascii() or any(ord(c)<32 and c not in '\r\n\t' for c in text): raise RejectedXML('XML data requires ASCII')
            return text
        def tag_end(at):
            quote=None
            for i in range(at,len(self.raw)):
                char=self.raw[i]
                if quote is not None:
                    if char==quote: quote=None
                elif char in (34,39): quote=char
                elif char==62: return i+1
            raise RejectedXML('Incomplete XML tag')
        def append(event):
            state.tick(line)
            if len(events)>=65536: raise RejectedXML('XML event limit exceeded')
            events.append(event)
        def start(name,attributes):
            ascii_text(name)
            if not xml_name(name) or len(stack)>=64 or len(attributes)>64: raise RejectedXML('XML name, depth or attribute limit exceeded')
            attrs=tuple(zip(attributes[::2],attributes[1::2]))
            for key,value in attrs:
                if not xml_name(key) or len(ascii_text(value))>254: raise RejectedXML('XML attribute is too large or invalid')
            end=tag_end(parser.CurrentByteIndex);empty=self.raw[end-2:end]==b'/>'
            stack.append(empty)
            append(dict(name=name,attrs=attrs,parts=[],kind=101 if empty else 100,attributes_valid=True,
                        end=end,line=parser.CurrentLineNumber))
        def end(name):
            if stack.pop(): return
            append(dict(name=name,attrs=(),parts=[],kind=101,attributes_valid=False,
                        end=tag_end(parser.CurrentByteIndex),line=parser.CurrentLineNumber))
        def text(value):
            ascii_text(value)
            if events: events[-1]['parts'].append(value)
        parser.StartElementHandler=start;parser.EndElementHandler=end;parser.CharacterDataHandler=text
        parser.StartDoctypeDeclHandler=reject;parser.EntityDeclHandler=reject;parser.ExternalEntityRefHandler=reject
        try:
            ascii_text(self.raw.decode('ascii'))
            for at in range(0,len(self.raw),4096):
                state.tick(line);parser.Parse(self.raw[at:at+4096],False)
            parser.Parse(b'',True)
        except (expat.ExpatError,RejectedXML,UnicodeError): self.failed=4;return
        for event in events: event['text']=''.join(event.pop('parts'))
        self.events=events

    def candidate(self,state,line=None):
        self.parse(state,line)
        if self.failed is not None: return None,dict(name='',ident=-1,kind=0,status=self.failed)
        if self.current is not None and self.current['read'] and self.current['offset']<len(self.current['text']):
            return None,dict(name=self.current['name'],ident=self.current['ident'],kind=103,status=1001)
        index=self.next
        while index<len(self.events):
            state.tick(line);event=self.events[index]
            if event['line']>=self.scan_line+50:
                return index,dict(name='',ident=1002,kind=0,status=1002)
            for tag in self.tags:
                actual=event['name'][:tag['count']];pattern=tag['name'][:tag['count']]
                if (actual==pattern if tag['case'] else actual.upper()==pattern.upper()):
                    return index,dict(name=event['name'],ident=tag['ident'],kind=event['kind'],status=1001)
            index+=1
        if len(self.line_starts)>=self.scan_line+50:
            return index,dict(name='',ident=1002,kind=0,status=1002)
        return index,dict(name='',ident=0,kind=101,status=0)

    def scan(self,state,args,line=None):
        output=args[1]
        if type(output.spec[1]) is not int or not 1<=output.spec[1]<=254:
            raise rt().KarelRuntimeError('XML tag output requires concrete STRING capacity',line)
        index,result=self.candidate(state,line)
        if len(result['name'])>output.spec[1]: args[4].set(3,line);self.handle.status=3;return
        if result['status']==1002:
            self.next=index;self.current=None;self.scan_line+=50
            self.handle.position=self.line_starts[self.scan_line-1]
        elif result['status']==1001 and result['kind']!=103:
            self.next=index+1;self.current=dict(self.events[index],ident=result['ident'],offset=0,read=False)
            self.scan_line=self.current['line'];self.handle.position=self.current['end']
        elif result['status']!=1001:
            self.current=None
            if result['status']==0: self.next=index;self.handle.position=len(self.raw)
        for ref,key in zip(args[1:],('name','ident','kind','status')): ref.set(result[key],line)
        self.handle.status=result['status']

    def data(self,args,line=None):
        if self.current is None: args[6].set(1,line);self.handle.status=1;return
        names,values=args[2].raw(),args[3].raw();attrs=self.current['attrs']
        text=args[4];capacity=text.spec[1]
        if type(capacity) is not int or not 1<=capacity<=254: raise rt().KarelRuntimeError('XML text requires concrete STRING capacity',line)
        if any(type(array.spec[2][1]) is not int or not 1<=array.spec[2][1]<=254 for array in (names,values)):
            raise rt().KarelRuntimeError('XML attribute arrays require concrete STRING capacities',line)
        if len(attrs)>min(len(names.values),len(values.values)) or any(len(key)>names.spec[2][1] or len(value)>values.spec[2][1] for key,value in attrs):
            args[6].set(3,line);self.handle.status=3;return
        offset=self.current['offset'];chunk=self.current['text'][offset:offset+capacity];offset+=len(chunk)
        for i,(key,value) in enumerate(attrs,1): names.set(i,key,line);values.set(i,value,line)
        args[1].set(len(attrs),line);text.set(chunk,line);args[5].set(offset==len(self.current['text']),line);args[6].set(0,line)
        self.current.update(offset=offset,read=True);self.handle.status=0


def set_variables(context,state,session,args,line=None):
    runtime=rt();current=session.current;status=args[3]
    if current is None or not current['attributes_valid']: status.set(1,line);return
    try: target=context.resolve(state,runtime.ascii_string(args[1],line),runtime.ascii_string(args[2],line),line,path_nodes=True)
    except runtime.KarelRuntimeError: status.set(1,line);return
    if target.spec[0]!='STRUCTURE': status.set(2,line);return
    if runtime._reference_cells(target)&runtime._reference_cells(status):
        raise runtime.KarelRuntimeError('XML_SETVAR target overlaps status output',line)
    record=target.raw();prepared=[];seen=set()
    for key,value in current['attrs']:
        key=key.upper()
        if key in seen or key not in record.types: status.set(2,line);return
        seen.add(key);spec=record.types[key]
        try:
            if spec[0]=='INTEGER':
                if not re.fullmatch(r'[+-]?[0-9]+',value.strip()): raise ValueError('Expected decimal INTEGER')
                converted=int(value.strip())
            elif spec[0]=='REAL': converted=float(value.strip())
            elif spec[0]=='BOOLEAN':
                text=value.strip().upper()
                if text not in ('0','1','FALSE','TRUE','OFF','ON'): raise ValueError('Expected BOOLEAN')
                converted=text in ('1','TRUE','ON')
            elif spec[0]=='STRING':
                if len(value)>spec[1]: status.set(3,line);return
                converted=value
            else: status.set(2,line);return
            prepared.append((key,runtime.checked(spec,converted,line)))
        except (ValueError,OverflowError,runtime.KarelRuntimeError): status.set(2,line);return
    for key,value in prepared: record.values[key]=value
    status.set(0,line)


def invoke_xml(context,state,name,args,line=None):
    handle=args[0];handle.require_open(line)
    if not handle.xml or handle.mode!='R' or handle.binary:
        raise rt().KarelRuntimeError('XML requires ATR_XML and a text FILE opened RO',line)
    if handle.xml_session is None: handle.xml_session=XMLInput(handle,line)
    session=handle.xml_session;session.unchanged(line)
    if name=='XML_ADDTAG': code=session.add(*args[1:5],line=line)
    elif name=='XML_REMTAG': code=session.remove(args[1],line)
    elif name=='XML_SCAN': return session.scan(state,args,line)
    elif name=='XML_GETDATA': return session.data(args,line)
    else:
        set_variables(context,state,session,args,line);handle.status=args[-1].raw();return
    args[-1].set(code,line);handle.status=code
