"""Bounded ASCII XML input over explicitly opened offline FILE backends."""
from array import array
from xml.parsers import expat
import re
from .reference_contracts import capture_location as _reference_location,same_location as _same_location


XML_CONSTANTS={'ATR_XML':6,'AR_XML':6,'XML_SUCCESS':0,'XML_START':100,'XML_END':101,
    'XML_STEND':102,'XML_TXCONT':103,'XML_FUNCTION':1001,'XML_SCANLIM':1002,
    'XML_ERROR':-1,'XML_STATE':1,'XML_INVALID':2,'XML_CAPACITY':3,'XML_PARSE':4,'XML_LIMIT':5}
XML_NAMES=frozenset(('XML_ADDTAG','XML_REMTAG','XML_SCAN','XML_GETDATA','XML_SETVAR'))


def rt():
    from . import runtime
    return runtime


class RejectedXML(ValueError): pass


def xml_name(value): return bool(re.fullmatch(r'[A-Za-z_:][A-Za-z_0-9.:-]{0,253}',value))


NAMESPACE_SEPARATOR=chr(31)
XML_BYTE_LIMIT=1024*1024
NON_XML_ASCII=re.compile(rb'[^\x09\x0a\x0d\x20-\x7f]')


def namespace_uri(value):
    return 0<len(value)<=254 and all(33<=ord(char)<=126 and char not in '{}' for char in value)


def tag_key(value):
    if not value.startswith('{'):
        return ('',value) if xml_name(value) else None
    uri,separator,local=value[1:].partition('}')
    if separator and len(value)<=254 and namespace_uri(uri) and xml_name(local) and ':' not in local:
        return uri,local
    return None


class XMLInput:
    def __init__(self,state,handle,line=None):
        from .fileops import charge_file_bytes

        runtime = rt()
        if handle.position:
            raise runtime.KarelRuntimeError('XML input must begin at byte zero',line)
        self.handle = handle
        self.identity = runtime._file_identity(handle)
        self.files = handle.owner.files
        self.buffer = self.files.get(handle.name)
        if type(self.buffer) not in (bytes, bytearray):
            raise runtime.KarelRuntimeError('XML input requires an ordinary byte buffer', line)
        self.size = len(self.buffer)
        self.tags = []
        self.namespaces = False
        self.active = False
        self.events = None
        self.failed = 5 if self.size > XML_BYTE_LIMIT else None
        self.next = 0
        self.current = None
        self.scan_line = 1
        self.raw = None
        self.line_starts = array('L', [0])
        if self.failed is None:
            charge_file_bytes(self.size, lambda: state.tick(line))
            self.check_binding(0, None, line)
            self.raw = bytes(self.buffer)
            self.line_starts.extend(m.end() for m in re.finditer(rb'\r\n|\r|\n', self.raw))

    def check_binding(self, position, session, line):
        handle = self.handle
        if (rt()._file_identity(handle) != self.identity or handle.position != position
                or handle.xml_session is not session or handle.owner.files is not self.files
                or self.files.get(handle.name) is not self.buffer or len(self.buffer) != self.size):
            raise rt().KarelRuntimeError('XML input changed while open; close and reopen it', line)

    def unchanged(self, position, line):
        self.check_binding(position, self, line)
        if type(self.buffer) is bytearray and self.raw is not None and self.buffer != self.raw:
            raise rt().KarelRuntimeError('XML input changed while open; close and reopen it', line)

    def add(self,name,count,case,ident,line=None):
        runtime=rt();name=runtime.ascii_string(name,line);count=runtime.integer(count,line)
        case=runtime.boolean(case,line);ident=runtime.integer(ident,line)
        key=tag_key(name)
        if key is None or not 1<=count<=254 or ident<=0 or ident in (1001,1002): return 2
        uri,local=key
        if self.namespaces and ':' in local:return 2
        if uri and not self.namespaces:
            if self.events is not None or self.failed is not None:return 1
            if any(':' in row['local'] for row in self.tags):return 2
        if any(row['ident']==ident or (row['uri']==uri and row['local'].upper()==local.upper())
               for row in self.tags): return 2
        if len(self.tags)>=128: return 5
        self.tags.append(dict(uri=uri,local=local,count=count,case=case,ident=ident))
        if uri:self.namespaces=True
        return 0

    def remove(self,name,line=None):
        name=rt().ascii_string(name,line)
        key=tag_key(name)
        if key is None:return 2
        uri,local=key
        found=next((row for row in self.tags if row['uri']==uri and
                    (row['local']==local if row['case'] else row['local'].upper()==local.upper())),None)
        if found is None: return 2
        if self.current is not None and self.current['ident']==found['ident']: return 1
        self.tags.remove(found);return 0

    def parse(self,state,line=None):
        if self.events is not None or self.failed is not None:
            return self.events,self.failed
        events=[];stack=[];declarations=0
        parser=expat.ParserCreate(namespace_separator=NAMESPACE_SEPARATOR if self.namespaces else None)
        parser.ordered_attributes=True
        def reject(*args): raise RejectedXML('DTD and entity declarations are unsupported')
        def ascii_text(text):
            if not text.isascii() or any(ord(c)<32 and c not in '\r\n\t' for c in text): raise RejectedXML('XML data requires ASCII')
            return text
        def checked_name(name):
            uri,separator,local=name.partition(NAMESPACE_SEPARATOR)
            label=f'{{{uri}}}{local}' if separator else name
            key=tag_key(label)
            if key is None:raise RejectedXML('XML name is too large or invalid')
            return label,key
        def namespace_decl(prefix,uri):
            nonlocal declarations
            declarations+=1
            if (declarations>32 or (prefix is not None and not xml_name(prefix))
                    or (uri is not None and not namespace_uri(uri))):
                raise RejectedXML('XML namespace declaration is too large or invalid')
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
            nonlocal declarations
            label,key=checked_name(name)
            if len(stack)>=64 or len(attributes)//2+declarations>32: raise RejectedXML('XML depth or attribute limit exceeded')
            declarations=0
            attrs=tuple((checked_name(attr)[0],ascii_text(value)) for attr,value in zip(attributes[::2],attributes[1::2]))
            if any(len(value)>254 for _,value in attrs):raise RejectedXML('XML attribute is too large')
            end=tag_end(parser.CurrentByteIndex);empty=self.raw[end-2:end]==b'/>'
            stack.append(empty)
            append(dict(name=label,key=key,attrs=attrs,parts=[],kind=101 if empty else 100,attributes_valid=True,
                        end=end,line=parser.CurrentLineNumber))
        def end(name):
            if stack.pop(): return
            label,key=checked_name(name)
            append(dict(name=label,key=key,attrs=(),parts=[],kind=101,attributes_valid=False,
                        end=tag_end(parser.CurrentByteIndex),line=parser.CurrentLineNumber))
        def text(value):
            ascii_text(value)
            if events: events[-1]['parts'].append(value)
        parser.StartElementHandler=start;parser.EndElementHandler=end;parser.CharacterDataHandler=text
        parser.StartNamespaceDeclHandler=namespace_decl
        parser.StartDoctypeDeclHandler=reject;parser.EntityDeclHandler=reject;parser.ExternalEntityRefHandler=reject
        try:
            for at in range(0,len(self.raw),4096):
                state.tick(line)
                block = self.raw[at:at+4096]
                if NON_XML_ASCII.search(block):
                    raise RejectedXML('XML data requires ASCII')
                parser.Parse(block,False)
            parser.Parse(b'',True)
        except (expat.ExpatError,RejectedXML,UnicodeError):
            return None,4
        for event in events: event['text']=''.join(event.pop('parts'))
        return events,None

    def candidate(self,state,events,failed,line=None):
        if failed is not None: return None,dict(name='',ident=-1,kind=0,status=failed)
        if self.current is not None and self.current['read'] and self.current['offset']<len(self.current['text']):
            return None,dict(name=self.current['name'],ident=self.current['ident'],kind=103,status=1001)
        index=self.next
        while index<len(events):
            state.tick(line);event=events[index]
            if event['line']>=self.scan_line+50:
                return index,dict(name='',ident=1002,kind=0,status=1002)
            uri,local=event['key']
            for tag in self.tags:
                if tag['uri']!=uri:continue
                actual=local[:tag['count']];pattern=tag['local'][:tag['count']]
                if (actual==pattern if tag['case'] else actual.upper()==pattern.upper()):
                    return index,dict(name=event['name'],ident=tag['ident'],kind=event['kind'],status=1001)
            index+=1
        if len(self.line_starts)>=self.scan_line+50:
            return index,dict(name='',ident=1002,kind=0,status=1002)
        return index,dict(name='',ident=0,kind=101,status=0)

    def scan(self,state,args,line,verify):
        output=args[1]
        if type(output.spec[1]) is not int or not 1<=output.spec[1]<=254:
            raise rt().KarelRuntimeError('XML tag output requires concrete STRING capacity',line)
        events,failed=self.parse(state,line)
        index,result=self.candidate(state,events,failed,line)
        verify()
        self.events,self.failed=events,failed
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


def _variable_stamp(spec,value):
    """Bounded data tokens plus strong storage owners; never call task hooks."""
    runtime=rt();rows=[];owners=[]
    def visit(expected,item):
        kind=expected[0]
        if kind=='ARRAY':
            shape=runtime.array_shape(expected)
            size=1
            for dimension in shape:size*=dimension
            if (type(item) is not runtime.Array or item.spec!=expected or item.shape!=shape
                    or not runtime._array_storage(item.values) or len(item.values)!=size):raise ValueError('ARRAY storage changed')
            mapping=item.values
            view=(() if type(mapping) is list else
                  (id(mapping.storage),mapping.start,mapping.size,mapping.length))
            if type(mapping) is not list:owners.append(mapping.storage)
            owners.extend((item,mapping));rows.append(('ARRAY',id(item),id(mapping),shape,view))
            for child in mapping:visit(expected[2],child)
        elif kind in runtime.RECORD_TYPES:
            fields=runtime.record_fields(expected)
            if (type(item) is not runtime.Structure or item.spec!=expected
                    or type(item.types) is not dict or item.types!=dict(fields)
                    or type(item.values) is not dict or item.values.keys()!=item.types.keys()
                    or type(item.read_only) is not bool):raise ValueError('Record storage changed')
            owners.extend((item,item.values,item.types))
            rows.append(('RECORD',id(item),id(item.values),id(item.types),item.read_only))
            for name,member in fields:visit(member,item.values[name])
        elif kind=='JOINTPOS':
            if (type(item) is not runtime.JointPosition or item.spec!=expected
                    or type(item.values) is not list or len(item.values)!=expected[1]):raise ValueError('Joint storage changed')
            owners.extend((item,item.values));rows.append(('JOINTPOS',id(item),id(item.values)))
            for axis in item.values:visit(runtime.REAL,axis)
        elif item is runtime.UNINITIALIZED:rows.append(('missing',))
        elif item is runtime.UNKNOWN_BYTE:rows.append(('unknown_byte',))
        elif type(item) in (int,bool,str):rows.append((type(item),item))
        elif type(item) is float:rows.append((float,item.hex()))
        else:raise ValueError('Scalar storage changed')
    visit(spec,value)
    return tuple(rows),tuple(owners)


class _VariablePublication:
    def __init__(self,target,location,line):
        self.target,self.location,self.line=target,location,line
        self.original=target.raw()
        self.stamp,self.owners=_variable_stamp(location[1],self.original)

    def verify(self):
        try:
            if not _same_location(self.target,self.location) or self.target.raw() is not self.original:raise ValueError('Target binding changed')
            current,_=_variable_stamp(self.location[1],self.original)
            if current!=self.stamp:raise ValueError('Target data changed')
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,rt().KarelRuntimeError) as error:
            raise rt().KarelRuntimeError('XML_SETVAR target changed during staging',self.line) from error


def prepare_variables(context,state,session,args,line=None):
    runtime=rt();current=session.current;status=args[3]
    if current is None or not current['attributes_valid']: return 1,None
    try: target=context.resolve(state,runtime.ascii_string(args[1],line),runtime.ascii_string(args[2],line),line,path_nodes=True)
    except runtime.KarelRuntimeError: return 1,None
    if target.spec[0] not in runtime.RECORD_TYPES or type(target) is not runtime.Reference: return 2,None
    location=_reference_location(target)
    try: cost=runtime._validate_data_schema(target.spec,line)
    except runtime.KarelRuntimeError: return 2,None
    for _ in range(cost):state.tick(line)
    if not _same_location(target,location):
        raise runtime.KarelRuntimeError('XML_SETVAR target binding changed during preparation',line)
    if runtime._reference_cells(target)&runtime._reference_cells(status):
        raise runtime.KarelRuntimeError('XML_SETVAR target overlaps status output',line)
    # Stage the complete value so a late path/domain/protection failure cannot
    # publish an earlier attribute. Replacing preserves existing storage identities.
    try:
        staged=runtime.checked(target.spec,target.raw(),line)
        publication=_VariablePublication(target,location,line)
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,runtime.KarelRuntimeError): return 2,None
    seen=set()
    for key,value in current['attrs']:
        state.tick(line)
        try:
            parts=key.upper().split('.')
            node=staged;reference=None;at=0
            while at<len(parts):
                if isinstance(node,runtime.Structure):
                    if re.fullmatch(r'[A-Z_][A-Z_0-9]*',parts[at]) is None: raise ValueError('Invalid XML field path')
                    reference=runtime.field_reference(node,parts[at],line);at+=1
                elif isinstance(node,runtime.Array):
                    rank=len(node.shape);indices=parts[at:at+rank]
                    if len(indices)!=rank or any(re.fullmatch(r'[0-9]+',index) is None for index in indices):
                        raise ValueError('XML ARRAY paths require every dimension')
                    reference=runtime.index_reference(node,tuple(int(index) for index in indices),line);at+=rank
                elif isinstance(node,runtime.JointPosition):
                    if at+1!=len(parts) or re.fullmatch(r'[0-9]+',parts[at]) is None:
                        raise ValueError('XML JOINTPOS paths require one final axis number')
                    reference=runtime.joint_index_reference(node,int(parts[at]),reference.spec,line);at+=1
                else: raise ValueError('XML path must select a declared scalar leaf')
                node=reference.raw()
            if reference is None or isinstance(reference,runtime.ReadOnlyFieldReference):
                raise ValueError('XML leaf must be writable')
            cells=runtime._reference_cells(reference)
            if cells & seen: raise ValueError('Duplicate XML leaf')
            seen.update(cells);spec=reference.spec
            if spec[0] in ('INTEGER','BYTE','SHORT'):
                if not re.fullmatch(r'[+-]?[0-9]+',value.strip()): raise ValueError('Expected decimal integral value')
                converted=int(value.strip())
            elif spec[0]=='REAL': converted=float(value.strip())
            elif spec[0]=='BOOLEAN':
                text=value.strip().upper()
                if text not in ('0','1','FALSE','TRUE','OFF','ON'): raise ValueError('Expected BOOLEAN')
                converted=text in ('1','TRUE','ON')
            elif spec[0]=='STRING':
                if len(value)>spec[1]: return 3,None
                converted=value
            else: raise ValueError('XML attributes require scalar leaves')
            reference.set(converted,line)
        except (ValueError,OverflowError,runtime.KarelRuntimeError):
            return 2,None
    return 0,(target,staged,publication)


def invoke_xml(context,state,name,args,line=None):
    from .fileops import charge_file_bytes

    handle=args[0];handle.require_open(line)
    status_location=_reference_location(args[-1]) if name=='XML_SETVAR' else None
    if not handle.xml or handle.mode!='R' or handle.binary:
        raise rt().KarelRuntimeError('XML requires ATR_XML and a text FILE opened RO',line)
    fresh = handle.xml_session is None
    if fresh:
        handle.xml_session = XMLInput(state, handle, line)
    session = handle.xml_session
    if session.active:
        raise rt().KarelRuntimeError('XML FILE already has an active operation', line)
    position = handle.position
    session.check_binding(position, session, line)

    def verify():
        session.unchanged(position, line)

    session.active = True
    try:
        # Reserve comparison work before staging a result. The final check
        # must not call back into the task after a result has been prepared.
        deferred = name in ('XML_SCAN', 'XML_SETVAR')
        if (deferred or not fresh) and session.raw is not None and type(session.buffer) is bytearray:
            charge_file_bytes(session.size, lambda: state.tick(line))
            session.check_binding(position, session, line)
        if name=='XML_SCAN':
            return session.scan(state, args, line, verify)
        if name=='XML_SETVAR':
            code, plan = prepare_variables(context, state, session, args, line)
            verify()
            if not _same_location(args[-1],status_location):
                raise rt().KarelRuntimeError('XML_SETVAR status binding changed during preparation',line)
            if plan is not None:
                target, staged, publication = plan
                publication.verify()
                target.set(staged, line)
        else:
            if not fresh:
                verify()
            if name=='XML_ADDTAG':
                code=session.add(*args[1:5],line=line)
            elif name=='XML_REMTAG':
                code=session.remove(args[1],line)
            else:
                return session.data(args,line)
        args[-1].set(code,line);handle.status=code
    finally:
        session.active = False
