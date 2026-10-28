"""Typed array tables and resident lists on explicit, headless windows."""
import math
import re

from .keyboard import key_info, pane_for


TABLE_CALLS={'INIT_TBL','ACT_TBL','DISCTRL_TBL','DISCTRL_LIST'}
TABLE_CONSTANTS={name:i for i,name in enumerate(('TPX_INT_ITEM','TPX_REL_ITEM','TPX_FKY_ITEM',
    'TPX_SUB_ITEM','TPX_KST_ITEM','TPX_KSL_ITEM','TPX_KBL_ITEM','TPX_BYT_ITEM',
    'TPX_SHT_ITEM','TPX_PBL_ITEM','TPX_PIN_ITEM'),1)}
TABLE_CONSTANTS.update(DC_DISP=1,DC_UP=2,DC_DN=3,DC_LF=4,DC_RT=5,
    KY_DISP_UPDT=1009,KY_REISSUE=1010,KY_CANCEL=1011)
MAX_SEQUENCE=2147483646
CONVERSION=re.compile(r'%(?!%)([-+ 0]*)([0-9]*)(?:\.([0-9]+))?([doxXucfeEgGs])')


def rt():
    from . import runtime
    return runtime


def invalid(message):raise ValueError(message)


def number(value,low,high):
    if type(value) is not int or not low<=value<=high:invalid('Value outside portable table bounds')
    return value


def field(record,name,default=None):
    value=record.values[name]
    return default if value is rt().UNINITIALIZED else value


def reference_value(reference):return rt().require(reference.raw())


def dictionary_lines(state,name,element):
    tokens=state.execution.require('dictionaries').element(state,name,element)
    if tokens==[('terminator',)]:return ['']
    if any(token[0] not in ('text','newline','style') for token in tokens):invalid('Table headers require plain dictionary lines')
    text=''.join(token[1] if token[0]=='text' else '\n' if token[0]=='newline' else '' for token in tokens)
    if any(char!='\n' and not 32<=ord(char)<=126 for char in text):invalid('Table text requires printable ASCII')
    return text.split('\n')


def format_spec(text,kind):
    if not text:text={'INTEGER':'%d','REAL':'%g','STRING':'%s','BOOLEAN':'%s'}[kind]
    if type(text) is not str or len(text)>80 or not all(32<=ord(c)<=126 for c in text):invalid('Invalid table format')
    # Remove literal percent escapes before finding the one actual conversion.
    stripped=text.replace('%%','');matches=list(CONVERSION.finditer(stripped))
    if len(matches)!=1 or '%' in stripped[:matches[0].start()]+stripped[matches[0].end():]:invalid('Table format requires one conversion')
    flags,width,precision,conversion=matches[0].groups()
    if len(set(flags))!=len(flags) or int(width or 0)>254 or int(precision or 0)>254:invalid('Table format exceeds bounds')
    if conversion not in {'INTEGER':'doxXuc','REAL':'feEgG','STRING':'s','BOOLEAN':'s'}[kind]:invalid('Table format disagrees with column type')
    if kind in ('STRING','BOOLEAN') and any(c in flags for c in '+ 0'):invalid('String format has numeric flags')
    return text


class Cell:
    def __init__(self,reference,bank=None,port=None):self.reference=reference;self.bank=bank;self.port=port
    def read(self):
        if self.bank is None:return self.reference.raw()
        self.bank.poll_pulses()
        return self.bank.values.get(self.port,rt().UNINITIALIZED)
    def writable(self):
        from .extended import OUTPUT_PORTS
        return self.bank is None or self.port[0] in OUTPUT_PORTS or self.port in self.bank.simulated
    def write(self,value,line):
        if self.bank is None:self.reference.set(value,line)
        else:self.bank.write(*self.port,value,line)


class TableControls:
    """Sessions retain live references; only an inactive manager can be saved."""
    def __init__(self,*,window='TABL',limit=64,sequence=0):
        from .pendant import ordinary_name
        self.window=ordinary_name(window);self.limit=number(limit,1,64);self.sequence=number(sequence,0,MAX_SEQUENCE)
        self._sessions={}

    @property
    def active_count(self):return len(self._sessions)

    def to_config(self):
        if self._sessions:raise ValueError('Cancel active tables before saving context')
        return dict(window=self.window,limit=self.limit,sequence=self.sequence)

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'window','limit','sequence'}:raise ValueError('Unknown table_controls configuration fields')
        return cls(**config)

    def snapshot(self):
        return dict(window=self.window,limit=self.limit,sequence=self.sequence,active=[dict(session=n,
            program=rt().task_root(s['state']).program_name,row=s['row'],column=s['col']+1,
            editing=s['edit'] is not None) for n,s in self._sessions.items()])

    def prepare(self,state,dictionary,element,rows,cols,descriptors,inactive,changes,paths,resources,line):
        runtime=rt();number(rows,1,32766);number(cols,1,40)
        if rows*cols>16384:invalid('Table exceeds 16384 cell budget')
        pendant=state.execution.require('pendant',line);surface=pendant.windows.get(self.window)
        if surface is None:invalid('Define the configured table window first')
        header=dictionary_lines(state,dictionary,element)
        if header==['']:header=[]
        if len(header)>=surface['rows'] or any(len(text)>surface['cols'] for text in header):invalid('Table header exceeds window')
        if len(descriptors.raw().values)<cols or len(paths.values)<cols:invalid('Table descriptors/paths are too short')
        occupied=set()
        for ref in resources:
            if type(ref) is runtime.Reference:occupied.update(runtime._reference_cells(ref))
        columns=[];regions=set()
        for index in range(cols):
            descriptor=descriptors.raw().values[index]
            item=number(field(descriptor,'ITEM_TYPE'),1,11)
            start=number(field(descriptor,'START_COL'),1,surface['cols'])
            width=number(field(descriptor,'FIELD_WIDTH'),1,surface['cols']-start+1)
            region=set(range(start,start+width))
            if regions&region:invalid('Table column fields overlap')
            regions.update(region)
            kind={1:'INTEGER',2:'REAL',3:'INTEGER',4:'INTEGER',5:'STRING',6:'STRING',
                  7:'BOOLEAN',8:'BYTE',9:'SHORT',10:'STRING',11:'STRING'}[item]
            name=runtime.ascii_string(runtime.require(paths.values[index]),line)
            match=re.fullmatch(r'(?:\[([A-Za-z_][A-Za-z_0-9]*)\])?(.+)',name)
            if match is None:invalid('Invalid table array path')
            target=state.execution.resolve(state,match[1] or state.program_name,match[2],line,path_nodes=True)
            if type(target) is not runtime.Reference or target.spec[0]!='ARRAY' or len(runtime.array_dimensions(target.spec))!=1 or runtime.array_leaf_spec(target.spec)[0]!=kind:invalid('Table requires a static global array matching its column type')
            if len(target.raw().values)<rows:invalid('Table backing array is too short')
            if occupied&runtime._reference_cells(target):invalid('Table backing data overlaps output/resource storage')
            cells=[]
            for row in range(rows):
                ref=runtime.index_reference(target.raw(),row+1,line)
                if item in (10,11):
                    from .extended import PORT_TYPES
                    port=re.fullmatch(r'([A-Za-z]+)\[(0|[1-9][0-9]*)\]',reference_value(ref))
                    if port is None or PORT_TYPES.get(port[1].upper())!=('BOOLEAN' if item==10 else 'INTEGER'):invalid('Port table requires a matching explicit port path')
                    bank=state.execution.require('ports',line);key=port[1].upper(),int(port[2]);bank._key(*key,line)
                    cells.append(Cell(ref,bank,key))
                else:cells.append(Cell(ref))
            display_kind='BOOLEAN' if item==10 else 'INTEGER' if item in (3,4,8,9,11) else kind
            labels=None
            if item in (3,4,7,10):
                enum_dict=field(descriptor,'ENUM_DICT','');enum_ele=field(descriptor,'ENUM_ELE',1)
                if not enum_dict and item in (7,10):labels=['FALSE','TRUE']
                elif item==4:
                    labels=[]
                    for offset in range(29):
                        lines=dictionary_lines(state,enum_dict,enum_ele+offset)
                        if lines==['']:break
                        if len(lines)!=1 or offset==28:invalid('Table submenu requires at most 28 single-line labels')
                        labels.extend(lines)
                else:labels=dictionary_lines(state,enum_dict,enum_ele)
                if not labels or len(labels)>(10 if item==3 else 2 if item in (7,10) else 28) or item in (7,10) and len(labels)!=2:invalid('Invalid table enumeration labels')
            fmt=format_spec(field(descriptor,'FORMAT_SPEC',''),'STRING' if labels is not None else display_kind)
            if CONVERSION.search(fmt.replace('%%',''))[4]=='c' and item!=8:invalid('Character format requires a BYTE column')
            minimum=field(descriptor,'MIN_REAL' if item==2 else 'MIN_INTEGER')
            maximum=field(descriptor,'MAX_REAL' if item==2 else 'MAX_INTEGER')
            if minimum is not None and maximum is not None and minimum>maximum:invalid('Table range is inverted')
            columns.append(dict(item=item,start=start,width=width,cells=cells,kind=display_kind,labels=labels,
                format=fmt,minimum=minimum,maximum=maximum,clear=number(field(descriptor,'CLEAR_FLAG',0),0,1),
                lower=number(field(descriptor,'LOWER_CASE',0),0,1)))
        session=dict(state=state,rows=rows,columns=columns,inactive=inactive,changes=changes,header=header,
            pendant=pendant,row=1,col=0,first=1,edit=None,cursor=0,attached=None,owns_attachment=False,work=None,work_value=None)
        session['col']=self.enabled(session)[0]
        if len(self._sessions)>=self.limit or self.sequence>=MAX_SEQUENCE:invalid('Table session capacity exhausted')
        return session

    def enabled(self,session):
        flags=session['inactive'].raw().values
        enabled=[i for i in range(len(session['columns'])) if i>=len(flags) or flags[i] is rt().UNINITIALIZED or not flags[i]]
        if not enabled:invalid('All table columns are inactive')
        return enabled

    def grid(self,reference,row,col,value,line=None):
        array=reference.raw()
        dimensions=rt().array_dimensions(array.spec)
        if len(dimensions)==2 and row<=dimensions[0] and col<=dimensions[1]:
            rt().index_reference(array,(row,col),line).set(value,line)

    def register(self,session,work=None,pointers=None,line=None):
        self.sequence+=1;identity=self.sequence;session['id']=identity
        if work is not None:
            session['work']=work;session['work_value']=work.raw()
            rt().field_reference(work.raw(),'SESSION',line).set(identity,line)
        self._sessions[identity]=session
        for row in range(1,session['rows']+1):
            for col in range(1,len(session['columns'])+1):
                self.grid(session['changes'],row,col,False,line)
                if pointers is not None:self.grid(pointers,row,col,(row-1)*len(session['columns'])+col,line)

    def close(self,session,line=None):
        self._sessions.pop(session['id'],None)
        screen=session['attached']
        shared=screen is not None and any(s.get('attachment') is session['attachment'] for s in self._sessions.values())
        if screen is not None and session['owns_attachment'] and not shared:
            attachments=session['pendant'].screens[screen]['attachments']
            attachments[:]=[item for item in attachments if item is not session['attachment']]
        session['attached']=None
        if session['work_value'] is not None:
            rt().field_reference(session['work_value'],'SESSION',line).set(0,line)

    def value_text(self,column,row):
        value=column['cells'][row-1].read()
        if value is rt().UNINITIALIZED or value is rt().UNKNOWN_BYTE:return '*'
        try:
            if column['labels'] is not None:
                index=int(value) if column['kind']=='BOOLEAN' else value-1
                if type(index) is not int or not 0<=index<len(column['labels']):return '?'
                value=column['labels'][index]
            text=column['format']%value
            return text if all(32<=ord(c)<=126 for c in text) else '?'
        except (TypeError,ValueError,OverflowError):return '?'

    def draw(self,session,line=None):
        surface=session['pendant'].windows[self.window];height=surface['rows']-len(session['header'])
        session['first']=max(1,min(session['first'],session['row']))
        if session['row']>=session['first']+height:session['first']=session['row']-height+1
        lines=[text.ljust(surface['cols']) for text in session['header']]
        with rt()._numeric_scope('pythonic'):
            for row in range(session['first'],session['first']+height):
                text=' '*surface['cols']
                if row<=session['rows']:
                    for index,column in enumerate(session['columns']):
                        value=session['edit'] if row==session['row'] and index==session['col'] and session['edit'] is not None else self.value_text(column,row)
                        start=column['start']-1;width=column['width']
                        text=text[:start]+value[:width].ljust(width)+text[start+width:]
                lines.append(text)
        session['pendant'].paint_fields(session['state'],self.window,[(i+1,1,text) for i,text in enumerate(lines)],line)

    def display(self,session,attach,line=None):
        pendant=session['pendant'];pendant.reserve()
        if session['attached'] is None:
            screen=pendant.active['TP'];attachments=pendant.screens[screen]['attachments']
            existing=next((item for item in attachments if item['window']==self.window),None)
            if attach and existing is None:
                if pendant.attach(self.window,screen,1,1):invalid('Table window does not fit active screen')
                existing=attachments[-1];session['owns_attachment']=True
            elif existing is not None:
                session['owns_attachment']=any(s['owns_attachment'] and s.get('attachment') is existing for s in self._sessions.values())
            if existing is not None:session['attached']=screen;session['attachment']=existing
        self.draw(session,line)

    def parsed(self,column,text):
        if column['kind']=='STRING':return text if column['lower'] else text.upper()
        if column['kind']=='REAL':
            if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?',text):invalid('Invalid real table entry')
            value=float(text)
            if not math.isfinite(value):invalid('Table REAL must be finite')
        else:
            if not re.fullmatch(r'[+-]?[0-9]+',text):invalid('Invalid integer table entry')
            value=int(text);number(value,0 if column['item']==8 else -32768 if column['item']==9 else -2147483648,
                255 if column['item']==8 else 32766 if column['item']==9 else MAX_SEQUENCE)
        if column['labels'] is not None and not 1<=value<=len(column['labels']):invalid('Table enum index outside labels')
        if column['minimum'] is not None and value<column['minimum'] or column['maximum'] is not None and value>column['maximum']:invalid('Table entry exceeds descriptor range')
        return value

    def commit(self,session,column,value,line):
        cell=column['cells'][session['row']-1]
        if not cell.writable():invalid('Table port is read only')
        # Validate destination capacity before changing the live cell.
        if cell.bank is None and cell.reference.spec[0]=='STRING' and len(value)>cell.reference.spec[1]:invalid('Table string exceeds destination capacity')
        cell.write(value,line);self.grid(session['changes'],session['row'],session['col']+1,True,line)

    def step(self,session,key,line=None):
        enabled=self.enabled(session)
        if session['col'] not in enabled:session['col']=enabled[0];session['edit']=None
        column=session['columns'][session['col']];cell=column['cells'][session['row']-1];code,category=key_info(key)
        if key=='NEW_MENU':return code,category
        text=session['edit']
        if text is not None:
            cursor=session['cursor']
            if key in ('ENTER','SELECT'):
                self.commit(session,column,self.parsed(column,text),line);session['edit']=None
            elif key=='PREV':session['edit']=None
            elif key=='LEFT':session['cursor']=max(0,cursor-1)
            elif key=='RIGHT':session['cursor']=min(len(text),cursor+1)
            elif key=='HOME':session['cursor']=0
            elif key=='END':session['cursor']=len(text)
            elif key=='DELETE' and cursor:session['edit']=text[:cursor-1]+text[cursor:];session['cursor']-=1
            elif len(key)==1:
                if len(text)>=254:invalid('Table edit exceeds 254 characters')
                session['edit']=text[:cursor]+key+text[cursor:];session['cursor']+=1
            return 0,category
        if key in ('UP','DOWN'):
            session['row']=max(1,min(session['rows'],session['row']+(-1 if key=='UP' else 1)))
        elif key in ('LEFT','RIGHT'):
            at=enabled.index(session['col']);session['col']=enabled[max(0,min(len(enabled)-1,at+(-1 if key=='LEFT' else 1)))]
        elif key=='SELECT':return code,category
        elif key=='ENTER' or len(key)==1:
            if column['item']==6 or not cell.writable():return 1008,128
            if column['kind']=='BOOLEAN':
                value=cell.read();self.commit(session,column,not value if type(value) is bool else True,line)
            else:
                value=cell.read();initial='' if value is rt().UNINITIALIZED or value is rt().UNKNOWN_BYTE else str(value)
                if len(key)==1 and (column['kind']!='STRING' or column['clear']):initial=''
                session['edit']=initial+(key if len(key)==1 else '');session['cursor']=len(session['edit'])
        elif key in ('PREV','NEXT') or key.startswith('F') and len(key)>1:return code,category
        return 0,category

    def check_aliases(self,session,args,line):
        occupied=set()
        for value in args:
            if type(value) is rt().Reference:occupied.update(rt()._reference_cells(value))
        for column in session['columns']:
            for cell in column['cells']:
                if occupied&rt()._reference_cells(cell.reference):raise rt().KarelRuntimeError('Table data overlaps service outputs/resources',line)

    def read_key(self,state,session,operation,line):
        keyboard=state.execution.require('keyboard',line);job=keyboard.start(state,operation,pane_for(state),255)
        if job is None:invalid('Keyboard is busy')
        complete=False
        try:
            while True:
                event=keyboard.event(job)
                if event is not None:
                    keyboard.record(job,'completed',selected=session['row'],term=key_info(event['key'])[0],status=0)
                    complete=True;return event['key']
                yield from keyboard.wait(state,job,None,line);self.draw(session,line)
        except BaseException as error:
            outcome='cancelled' if isinstance(error,(GeneratorExit,rt().KarelAbort,rt().KarelStop)) else 'failed'
            keyboard.record(job,outcome,selected=session['row'],term=0,status=6);complete=True;raise
        finally:
            if not complete:keyboard.record(job,'cancelled',selected=session['row'],term=0,status=6)
            keyboard.end(job)

    def init(self,state,args,line):
        dictionary,element,rows,cols,descriptors,inactive,changes,paths,pointers,work,status=args
        try:
            old=field(work.raw(),'SESSION',0)
            if old in self._sessions:invalid('XWORK_T already has an active session')
            dimensions=rt().array_dimensions(pointers.spec)
            if dimensions[0]<rows or dimensions[1]<cols:invalid('Table pointer grid is too short')
            session=self.prepare(state,dictionary,element,rows,cols,descriptors,inactive,changes,paths,args,line)
            self.register(session,work,pointers,line);status.set(0,line)
        except ValueError:status.set(1,line)

    def act(self,state,args,line):
        action,selected,work,term,attach,status=args;session=None
        try:
            session=self._sessions.get(field(work.raw(),'SESSION',0))
            if session is None or rt().task_root(session['state']) is not rt().task_root(state) or session['work_value'] is not work.raw():status.set(3,line);return
            code=reference_value(action) if type(action) is rt().Reference else action
            if code==TABLE_CONSTANTS['KY_CANCEL']:self.close(session,line);term.set(0,line);status.set(0,line);return
            self.check_aliases(session,args,line)
            session['row']=number(reference_value(selected),1,session['rows'])
            if code==TABLE_CONSTANTS['KY_DISP_UPDT']:self.display(session,reference_value(attach),line);terminal=0
            else:
                if code==TABLE_CONSTANTS['KY_REISSUE']:key=yield from self.read_key(state,session,'ACT_TBL',line)
                else:
                    from .keyboard import key_name
                    key=key_name(code)
                terminal,_=self.step(session,key,line);self.draw(session,line)
                if type(action) is rt().Reference:action.set(key_info(key)[0],line)
                if terminal==1007:self.close(session,line)
            selected.set(session['row'],line);term.set(terminal,line);status.set(0,line)
        except ValueError:status.set(1,line)
        except BaseException:
            if session is not None:self.close(session,line)
            raise

    def table(self,state,args,line):
        dictionary,element,rows,cols,descriptors,inactive,changes,selected,term,mask,paths,attach,status=args
        session=None
        try:
            number(mask,0,255)
            session=self.prepare(state,dictionary,element,rows,cols,descriptors,inactive,changes,paths,args,line)
            session['row']=number(reference_value(selected),1,rows);self.register(session,line=line)
            self.display(session,attach,line)
            for _ in range(4096):
                key=yield from self.read_key(state,session,'DISCTRL_TBL',line)
                code,category=key_info(key)
                if mask&category and session['edit'] is None or code in (1007,1008):
                    terminal=code
                else:terminal,category=self.step(session,key,line)
                self.draw(session,line)
                # Committing an edit remains inside the table. Non-edit keys
                # follow the explicit termination mask; SELECT/new menu always end.
                if terminal in (1007,1008) or terminal and mask&category:
                    selected.set(session['row'],line);term.set(terminal,line);status.set(0,line);return
                yield from rt().checkpoint(state,line)
            status.set(5,line)
        except ValueError:status.set(1,line)
        finally:
            if session is not None and 'id' in session:self.close(session,line)

    def listing(self,state,args,line):
        handle,data,items,action,status=args;runtime=rt()
        try:
            pendant=state.execution.require('pendant',line)
            if state.execution.keyboard is not None and handle.owner is state.execution.keyboard:
                if handle.mode=='R':invalid('List requires writable window FILE')
                handle=state.execution.keyboard.window_handle(handle)
            binding=pendant._handles.get(handle)
            if binding is None:invalid('List requires an open window FILE')
            window=pendant.windows[binding['window']];record=data.raw()
            viewport=number(field(record,'CURR_WIN'),0,3)
            start=number(record.values['WIN_START'].values[viewport],1,window['rows'])
            end=number(record.values['WIN_END'].values[viewport],start,window['rows'])
            number(field(record,'LINS_PER_PG'),1,end-start+1)
            last_field=number(field(record,'LAST_FIELD'),0,9);current_field=number(field(record,'CURR_FIELD'),0,last_field)
            for index in range(last_field+1):
                left=number(record.values['CURS_ST_COL'].values[index],0,window['cols']-1)
                number(record.values['CURS_EN_COL'].values[index],left,window['cols']-1)
            sob=number(field(record,'SOB_IT_NUM'),1,32766);eob=number(field(record,'EOB_IT_NUM'),sob,32766)
            number(field(record,'LAST_IT_NUM'),eob,32766)
            if eob-sob+1>len(items.values):invalid('Resident list array is too short')
            item=number(field(record,'CURR_IT_NUM'),sob,eob);row=number(field(record,'CURSOR_ROW'),start,end)
            number(action,1,5);first=max(sob,min(item-(row-start),max(sob,eob-(end-start))))
            if action==2:item=max(sob,item-1)
            if action==3:item=min(eob,item+1)
            if action==4:current_field=max(0,current_field-1)
            if action==5:current_field=min(last_field,current_field+1)
            if item<first:first=item
            if item>first+end-start:first=item-(end-start)
            row=start+item-first;fields=[]
            for offset in range(end-start+1):
                index=first+offset;text='' if index>eob else runtime.ascii_string(runtime.require(items.values[index-sob]),line)
                if any(not 32<=ord(c)<=126 for c in text):invalid('List lines require printable ASCII')
                fields.append((start+offset,1,text[:window['cols']].ljust(window['cols'])))
            if pendant.sequence>MAX_SEQUENCE-2:raise runtime.KarelRuntimeError('Display request sequence exhausted',line)
            pendant.paint_fields(state,binding['window'],fields,line)
            temporary=runtime.Reference(('INTEGER',),{'value':0},'value')
            pendant.invoke(state,'SET_CURSOR',[handle,row,record.values['CURS_ST_COL'].values[current_field]+1,temporary],line)
            for name,value in (('CURR_FIELD',current_field),('CURR_IT_NUM',item),('CURSOR_ROW',row)):
                runtime.field_reference(record,name,line).set(value,line)
            status.set(0,line)
        except ValueError:status.set(1,line)

    def invoke(self,state,name,args,line=None):
        if name=='INIT_TBL':return self.init(state,args,line)
        if name=='ACT_TBL':return self.act(state,args,line)
        if name=='DISCTRL_TBL':return self.table(state,args,line)
        return self.listing(state,args,line)
