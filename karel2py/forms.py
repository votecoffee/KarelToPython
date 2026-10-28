"""FTX source forms over typed cells, logical windows and injected keys."""
import math
import re

from .table_controls import Cell,TableControls,dictionary_lines,format_spec,invalid,number,rt
from .keyboard import key_info,pane_for


FORM_CALLS={'DISCTRL_FORM'}
FORM_PROGRAM_TYPES={1:{'TP','JB','PR','MR'},2:{'PC'},6:{'TP','JB','PR','MR','PC','VR'},16:{'TP','JB','PR','MR','PC'}}
FORMAT=re.compile(r'%([-+ 0]*)([0-9]*)(?:\.([0-9]+))?(pu|px|pk|[doxXufeEgGhbBPknwvSts%])(?:\(([^()]*)\))?')


class SimulationCell(Cell):
    def read(self):return self.port in self.bank.simulated
    def writable(self):return True
    def write(self,value,line):
        if value:
            if self.port not in self.bank.values:invalid('Supply a port value before simulating it')
            self.bank.simulated.add(self.port)
        else:self.bank.simulated.discard(self.port)


class FormControls(TableControls):
    """Only supplied text and explicit controller context; no native form ABI."""
    def __init__(self,*,window='FORM',rows=12,cols=40,limit=64,sequence=0):
        super().__init__(window=window,limit=limit,sequence=sequence)
        self.rows=number(rows,3,256);self.cols=number(cols,4,256)

    def to_config(self):
        if self._sessions:raise ValueError('Finish active forms before saving context')
        return dict(window=self.window,rows=self.rows,cols=self.cols,limit=self.limit,sequence=self.sequence)

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'window','rows','cols','limit','sequence'}:raise ValueError('Unknown forms configuration fields')
        return cls(**config)

    def snapshot(self):
        return dict(window=self.window,rows=self.rows,cols=self.cols,limit=self.limit,sequence=self.sequence,
            active=[dict(session=s['id'],program=rt().task_root(s['state']).program_name,
                dictionary=s['dictionary'],element=s['element'],selected=s['current'],
                editing=any(item.get('editor',{}).get('edit') is not None for item in s['items']),
                error=s['error'],help=s['help_offset'] is not None,
                choices=[] if s['choice'] is None else list(s['choice']['labels']),
                function_keys=self.function_keys(s)) for s in self._sessions.values()])

    def resolve(self,state,path,line):
        match=re.fullmatch(r'(?:\[([A-Za-z_][A-Za-z_0-9]*)\])?(.+)',rt().ascii_string(path,line))
        if match is None:invalid('Form path requires a static global or explicit port')
        return state.execution.resolve(state,match[1] or state.program_name,match[2],line,path_nodes=True)

    def lines(self,state,dictionary,element):return dictionary_lines(state,dictionary,element)

    def labels(self,column):
        source=column.get('choice_source')
        if source is None:return column['labels']
        labels=[]
        for value in source.raw().values[1:]:
            if value is rt().UNINITIALIZED:break
            text=rt().ascii_string(value)
            if len(labels)>=35:invalid('Form variable choices exceed 35')
            labels.append(text.lstrip())
        if not labels:invalid('Form choice array has no initialized choices after element 1')
        return labels

    def column(self,state,dictionary,text,path,changes,index,resources,line):
        match=FORMAT.match(text)
        if match is None:invalid('Unsupported form format')
        flags,width,precision,conversion,parameter=match.groups();suffix=text[match.end():]
        if '%' in suffix.replace('%%',''):invalid('One form data item requires one conversion')
        suffix=suffix.replace('%%','%')
        expected={'h':'SHORT','b':'BYTE','B':'BOOLEAN','P':'BOOLEAN','S':'BOOLEAN','k':'STRING','s':'STRING',
            'pk':'STRING','n':'INTEGER','w':'INTEGER','v':'INTEGER','t':'BOOLEAN'}.get(conversion,
            'REAL' if conversion in 'feEgG' else 'INTEGER')
        port_match=re.fullmatch(r'([A-Za-z]+)\[([1-9][0-9]*)\]',path)
        if conversion in ('P','pu','px','S'):
            from .extended import PORT_TYPES
            if port_match is None:invalid('Form port format requires a direct indexed port path')
            bank=state.execution.require('ports',line);key=port_match[1].upper(),int(port_match[2]);bank._key(*key,line)
            port_kind=PORT_TYPES[key[0]]
            if port_kind not in ('BOOLEAN','INTEGER') or conversion!='S' and port_kind!=('BOOLEAN' if conversion=='P' else 'INTEGER'):invalid('Form port format disagrees with port type')
            cell=(SimulationCell if conversion=='S' else Cell)(None,bank,key)
            expected='INTEGER' if conversion in ('pu','px') else 'BOOLEAN';reference=None
        else:
            reference=self.resolve(state,path,line)
            if not isinstance(reference,rt().Reference) or reference.spec[0]!=expected:invalid('Form data path disagrees with its format type')
            cell=Cell(reference)
        item={'h':9,'b':8,'B':7,'P':10,'S':10,'k':5,'s':5,'pk':5,'n':3,'w':4,'v':4,'t':7}.get(conversion,2 if expected=='REAL' else 1)
        kind='INTEGER' if expected in ('SHORT','BYTE') else expected
        labels=None;choice_source=None;minimum=maximum=None;clear=0;program_names=False
        if conversion in ('B','P','S','n','w','v'):
            if conversion in ('B','P','S'):
                labels=self.lines(state,dictionary,parameter) if parameter else (['UNSIM','SIMULATE'] if conversion=='S' else ['FALSE','TRUE'])
                if len(labels)!=2:invalid('Boolean form field requires two labels')
            elif not parameter:invalid('Form enum requires a label element')
            elif conversion=='n':
                labels=self.lines(state,dictionary,parameter)
                if not 1<=len(labels)<=5:invalid('Function enum requires 1..5 labels')
            elif conversion=='w':
                bank=state.execution.require('dictionaries',line);first=bank.element(state,dictionary,parameter,check=True);labels=[]
                for offset in range(36):
                    rows=self.lines(state,dictionary,first+offset)
                    if rows==['']:break
                    if len(rows)!=1 or offset==35:invalid('Subwindow enum requires at most 35 single-line choices')
                    labels.extend(rows)
            else:
                rows=self.lines(state,dictionary,parameter)
                if len(rows)!=2:invalid('Variable enum descriptor requires program and array lines')
                choice_source=self.resolve(state,'['+rows[0].strip()+']'+rows[1].strip(),line)
                if choice_source.spec[0]!='ARRAY' or len(rt().array_dimensions(choice_source.spec))!=1 or rt().array_leaf_spec(choice_source.spec)[0]!='STRING':invalid('Variable enum requires a STRING array')
                resources.append(choice_source)
                labels=self.labels(dict(choice_source=choice_source,labels=None))
            labels=[label.lstrip() for label in labels]
            if not labels:invalid('Form enum has no choices')
        elif conversion=='pk':
            selector=16 if parameter is None else int(parameter) if re.fullmatch(r'[0-9]+',parameter) else -1
            if selector not in FORM_PROGRAM_TYPES:invalid('Unknown form program-name selection type')
            owners=list(state.execution.variables.programs.values())+[state]
            entries={(owner.program_name,'PC') for owner in owners}
            if state.execution.programs is not None:entries.update(state.execution.programs.entries)
            if state.execution.teach_programs is not None:entries.update(state.execution.teach_programs.entries)
            labels=sorted({name for name,kind in entries if kind in FORM_PROGRAM_TYPES[selector]})
            if not labels or len(labels)>256:invalid('Program-name choices require 1..256 supplied programs')
            program_names=True
        elif conversion in ('k','s'):
            if parameter not in (None,'clear'):invalid('String form parameter requires clear')
            clear=int(parameter=='clear')
        elif conversion!='t' and parameter is not None:
            bounds=parameter.split(',')
            if len(bounds)!=2:invalid('Numeric form range requires minimum,maximum')
            try:minimum,maximum=[float(value) if kind=='REAL' else int(value) for value in bounds]
            except ValueError:invalid('Invalid numeric form range')
            if not all(math.isfinite(value) for value in (minimum,maximum)) or minimum>maximum:invalid('Invalid numeric form bounds')
        elif conversion=='t' and parameter is not None:invalid('Tree field takes no parameters')
        format_kind='STRING' if labels is not None else kind
        native_conversion='s' if format_kind in ('STRING','BOOLEAN') else 'd' if conversion in ('h','b','pu') else 'x' if conversion=='px' else conversion
        if conversion=='t':native_conversion='s';format_kind='STRING'
        fmt=format_spec('%'+flags+width+('' if precision is None else '.'+precision)+native_conversion,format_kind)
        field_width=int(width) if width else min(12,reference.spec[1]) if expected=='STRING' else 1 if conversion=='t' else 12
        number(field_width,1,254)
        return dict(item=item,kind=kind,cells=[cell],format=fmt,labels=labels,minimum=minimum,maximum=maximum,
            clear=clear,lower=1,start=1,width=field_width,suffix=suffix,conversion=conversion,
            base=16 if conversion in ('x','X','px') else 8 if conversion=='o' else 10,
            program_names=program_names,choice_source=choice_source,changes=changes,data_index=index)

    def prepare_form(self,state,args,line):
        dictionary,element,paths,inactive,changes,mask,selected,term,status=args
        number(mask,0,255);pendant=state.execution.require('pendant',line)
        from .pendant import PENDANT_CONSTANTS
        if pendant.menus.get(str(pane_for(state)),{}).get('menu')!=PENDANT_CONSTANTS['SPI_TPUSER2']:invalid('Forms require the USER2 menu')
        tokens=state.execution.require('dictionaries',line).element(state,dictionary,element)
        if not tokens or tokens[0][0]!='form' or tokens[-1]!=('endform',):invalid('DISCTRL_FORM requires a complete FTX form element')
        surface=pendant.windows.get(self.window);rows=self.rows if surface is None else surface['rows'];cols=self.cols if surface is None else surface['cols']
        if rows<3 or cols<4 or rows>pendant.rows or cols>pendant.cols:invalid('Form window does not fit pendant dimensions')
        if surface is None and (len(pendant.windows)>=64 or sum(w['rows']*w['cols'] for w in pendant.windows.values())+rows*cols>pendant.max_cells):invalid('Form window capacity exhausted')
        resources=[value for value in args if type(value) is rt().Reference]
        session=dict(state=state,dictionary=dictionary,element=element,rows=rows,cols=cols,items=[],segments=[],groups={},trees={},
            inactive=inactive,changes=changes,mask=mask,selected=selected,first=0,current=0,row=0,
            attributes=tokens[0][1],error='',help_offset=None,help_lines=[],choice=None,function_labels=None,function_source=None,
            pendant=pendant,attached=None,owns_attachment=False,work=None,work_value=None)
        row=col=1;data_index=0;select_index=0;tree=None;last_selector=None;continuation=False;ended=False
        for token in tokens[1:]:
            op=token[0]
            if ended:invalid('Unexpected content after form end')
            if op=='endform':ended=True;continue
            if op=='form':invalid('Nested/concatenated forms require explicit expansion into one form')
            if op in ('tree','endtree'):
                if op=='tree':invalid('Concatenated .tree forms are not modeled; use a tree data item')
                tree=None;continue
            if op=='function_keys':
                if session['function_labels'] is not None:invalid('Duplicate form function-key declaration')
                labels=self.lines(state,dictionary,token[1])
                if len(labels)==2 and all(label.startswith('*') for label in labels):
                    ref=self.resolve(state,'['+labels[0][1:].strip()+']'+labels[1][1:].strip(),line)
                    if ref.spec[0]!='ARRAY' or len(rt().array_dimensions(ref.spec))!=1 or rt().array_leaf_spec(ref.spec)[0]!='STRING':invalid('Function keys require a STRING array')
                    session['function_source']=ref;resources.append(ref);labels=[]
                if len(labels)>10:invalid('At most ten form function-key labels')
                session['function_labels']=labels;continue
            if op=='help':
                if session['help_lines']:invalid('Duplicate form help declaration')
                session['help_lines']=self.lines(state,dictionary,token[1])
                if len(session['help_lines'])>48 or any(len(text)>cols for text in session['help_lines']):invalid('Form help exceeds 48 lines or window width')
                continue
            if op=='style':continue
            if op=='home':
                if row!=1 or col!=1:invalid('Form layout cannot backtrack')
                continue
            if op in ('newline','lf'):
                row+=1;col=1;number(row,1,256);continue
            if op=='cursor':
                new_row,new_col=token[1:]
                if (new_row,new_col)<(row,col):invalid('Form layout cannot backtrack')
                row,col=new_row,new_col;continue
            if op!='text':invalid('Unsupported form control')
            text=token[1];selectable=text.startswith('-');content=text[1:] if selectable else text
            is_data=content.startswith('%') and not content.startswith('%%')
            if selectable and row<3 or is_data and row<3:invalid('Form items require body rows 3 and later')
            column=None;item=None;item_group=tree
            if is_data:
                if data_index>=len(paths.values):invalid('Form data path array is too short')
                number(data_index+1,1,256)
                path=rt().ascii_string(rt().require(paths.values[data_index]),line)
                column=self.column(state,dictionary,content,path,changes,data_index,resources,line);data_index+=1
                if column['conversion']=='t':tree=data_index;session['trees'][tree]=bool(column['cells'][0].read() is True)
                width=column['width']+len(column['suffix'])
            else:
                if content.startswith('%%'):content=content[1:]
                width=len(content[:-1] if content.endswith('+') else content)
            if selectable:
                select_index+=1;number(select_index,1,256)
                if column is not None and column['cells'][0].reference is not None and type(column['cells'][0].reference) is not rt().Reference:invalid('Editable form data requires ordinary writable storage')
            if selectable or is_data:
                item=dict(number=select_index if selectable else 0,column=column,row=row,col=col,group=item_group,tree=tree if column and column['conversion']=='t' else None)
                if column is not None:
                    dummy=rt().Array(('ARRAY',1,('BOOLEAN',)));dummy.values[0]=False
                    resource=rt().Reference(dummy.spec,{'value':dummy},'value')
                    item['editor']=dict(rows=1,row=1,col=0,columns=[column],inactive=resource,changes=changes,edit=None,cursor=0)
                session['items'].append(item)
                if selectable:last_selector=item
            if continuation:
                if selectable or is_data:invalid('Selectable continuation requires ordinary text')
                continuation=False
            if not is_data and content.endswith('+'):
                if last_selector is None:invalid('Form continuation requires a selectable item')
                continuation=True;content=content[:-1]
            if col+width-1>cols:invalid('Form content exceeds window width')
            session['groups'].setdefault(row,item_group)
            session['segments'].append(dict(row=row,col=col,text=content if column is None else None,item=item,column=column,group=item_group))
            col+=width
        if continuation:invalid('Unfinished selectable continuation')
        occupied=set()
        for resource in resources:occupied.update(rt()._reference_cells(resource))
        for item in session['items']:
            ref=None if item['column'] is None else item['column']['cells'][0].reference
            if ref is not None and occupied&rt()._reference_cells(ref):raise rt().KarelRuntimeError('Form data overlaps service outputs/resources',line)
        visible=self.selectable(session)
        self.function_keys(session)
        initial=rt().integer(rt().require(selected.raw()),line)
        if select_index:
            number(initial,1,select_index)
            if not visible:invalid('All selectable form items are hidden or inactive')
            session['current']=next((item['number'] for item in visible if item['number']>=initial),visible[-1]['number'])
        elif initial not in (0,1):invalid('Display-only form default item requires zero or one')
        if len(self._sessions)>=self.limit or self.sequence>=2147483646:invalid('Form session capacity exhausted')
        session['data_count']=data_index;session['new_window']=surface is None
        return session

    def selectable(self,session):
        flags=session['inactive'].raw().values
        return [item for item in session['items'] if item['number'] and
            (item['number']>len(flags) or flags[item['number']-1] is rt().UNINITIALIZED or not flags[item['number']-1]) and
            (item['group'] is None or session['trees'][item['group']])]

    def function_keys(self,session):
        ref=session['function_source']
        if ref is None:return session['function_labels'] or []
        if len(ref.raw().values)>10:invalid('Variable function-key array exceeds ten labels')
        return ['' if value is rt().UNINITIALIZED else rt().ascii_string(value) for value in ref.raw().values]

    def draw(self,session,line=None):
        # Dynamic tree items monitor their value; editable tree state is latched.
        for item in session['items']:
            if item['tree'] is not None and not item['number']:session['trees'][item['tree']]=item['column']['cells'][0].read() is True
        rows,cols=session['rows'],session['cols'];height=rows-2
        visible_rows=[row for row in range(3,max([2]+[s['row'] for s in session['segments']])+1) if session['groups'].get(row) is None or session['trees'][session['groups'][row]]]
        selectable=self.selectable(session)
        if selectable and session['current'] not in {item['number'] for item in selectable}:
            session['current']=next((item['number'] for item in selectable if item['number']>=session['current']),selectable[-1]['number'])
        session['selected'].set(session['current'],line);session['row']=session['current']
        selected=next((item for item in selectable if item['number']==session['current']),None)
        if selected is not None:
            at=visible_rows.index(selected['row']);session['first']=max(0,min(session['first'],at))
            if at>=session['first']+height:session['first']=at-height+1
        mapping={1:1,2:2};mapping.update((row,i+3) for i,row in enumerate(visible_rows[session['first']:session['first']+height]))
        surface=session['pendant'].windows[self.window]
        lines=list(session['background']) if 'noclear' in session['attributes'] else [' '*cols]*rows
        with rt()._numeric_scope('pythonic'):
            for segment in session['segments']:
                if segment['row'] not in mapping:continue
                column=segment['column'];item=segment['item'];text=segment['text']
                if column is not None:
                    if column['choice_source'] is not None:column['labels']=self.labels(column)
                    if item['editor']['edit'] is not None:text=item['editor']['edit']
                    elif item['tree'] is not None:text='-' if session['trees'][item['tree']] else '+'
                    elif column['program_names']:text=column['cells'][0].read();text='*' if text is rt().UNINITIALIZED else str(text)
                    else:text=self.value_text(column,1)
                    text=text[:column['width']].ljust(column['width'])+column['suffix']
                row,col=mapping[segment['row']]-1,segment['col']-1;lines[row]=lines[row][:col]+text+lines[row][col+len(text):]
            if 'unnumber' not in session['attributes']:
                numbered=set()
                for item in session['items']:
                    if item['number'] and item['row'] in mapping and item['row'] not in numbered:
                        row=mapping[item['row']]-1;lines[row]=f"{item['number']:>2} "+lines[row][3:];numbered.add(item['row'])
        if session['help_offset'] is not None:
            text=session['help_lines'][session['help_offset']:session['help_offset']+rows-1];lines=['HELP'.ljust(cols)]+[value.ljust(cols) for value in text];lines+=[' '*cols]*(rows-len(lines))
        elif session['choice'] is not None:
            choice=session['choice'];first=max(0,choice['selected']-(rows-2));labels=choice['labels'][first:first+rows-1]
            lines=['Choose value'.ljust(cols)[:cols]]+[('>' if first+i==choice['selected'] else ' ')+label[:cols-1].ljust(cols-1) for i,label in enumerate(labels)];lines+=[' '*cols]*(rows-len(lines))
        elif session['error']:lines[-1]=('! '+session['error'])[:cols].ljust(cols)
        session['pendant'].paint_fields(session['state'],self.window,[(i+1,1,text) for i,text in enumerate(lines)],line)

    def parsed(self,column,text):
        if column['program_names']:
            value=text.upper()
            if value not in column['labels']:invalid('Program name is not in the supplied selection')
            return value
        if column['base']!=10:
            try:text=str(int(text,column['base']))
            except ValueError:invalid('Invalid form integer base entry')
        value=super().parsed(column,text)
        if column['conversion']=='n' and not column['labels'][value-1]:invalid('Function enum choice is inactive')
        return value

    def commit(self,session,column,value,line):
        super().commit(session,column,value,line)
        index=column['data_index'];array=column['changes'].raw()
        if index<len(array.values):array.set(index+1,True,line)

    def act_key(self,session,key,line):
        code,category=key_info(key)
        if key=='NEW_MENU':return code
        if session['help_offset'] is not None:
            if key in ('PREV','F5'):session['help_offset']=None
            elif key in ('UP','DOWN','PAGE_UP','PAGE_DOWN'):
                delta=(-1 if key in ('UP','PAGE_UP') else 1)*(session['rows']-2 if key.startswith('PAGE') else 1)
                session['help_offset']=max(0,min(max(0,len(session['help_lines'])-session['rows']+1),session['help_offset']+delta))
            return 0
        if session['choice'] is not None:
            choice=session['choice'];labels=choice['labels']
            if key=='PREV':session['choice']=None
            elif key in ('UP','DOWN','HOME','END'):
                choice['selected']=0 if key=='HOME' else len(labels)-1 if key=='END' else max(0,min(len(labels)-1,choice['selected']+(-1 if key=='UP' else 1)))
            elif key in ('ENTER','SELECT'):
                column=choice['item']['column'];value=labels[choice['selected']] if column['program_names'] else choice['selected']+1
                self.commit(choice['item']['editor'],column,value,line);session['choice']=None;session['error']=''
            return 0
        items=self.selectable(session);item=next((item for item in items if item['number']==session['current']),None)
        column=None if item is None else item['column'];editor=None if column is None else item['editor']
        if editor is not None and editor['edit'] is not None:
            try:super().step(editor,key,line);session['error']=''
            except ValueError as error:session['error']=str(error)[:128]
            return code if editor['edit'] is None and (key=='SELECT' or key=='ENTER' and session['mask']&category) else 0
        if column is not None and column['conversion'] in ('B','P','S') and key in ('F4','F5'):
            self.commit(editor,column,key=='F4',line);session['error']='';return 0
        if column is not None and column['conversion']=='n' and key in ('F1','F2','F3','F4','F5'):
            index=int(key[1])-1
            if index<len(column['labels']) and column['labels'][index]:self.commit(editor,column,index+1,line)
            return 0
        if column is not None and (column['conversion'] in ('w','v','pk')) and key=='F4':
            if column['choice_source'] is not None:column['labels']=self.labels(column)
            labels=column['labels'];value=column['cells'][0].read()
            at=labels.index(value) if column['program_names'] and value in labels else value-1 if type(value) is int and 1<=value<=len(labels) else 0
            session['choice']=dict(item=item,labels=list(labels),selected=at);return 0
        function_keys=self.function_keys(session)
        if key=='F5' and len(function_keys)>=5 and function_keys[4].lstrip().upper().startswith('HELP') and session['help_lines']:
            session['help_offset']=0;return 0
        if key.startswith('F') and key[1:].isdigit() and session['function_labels'] is not None and (int(key[1:])>len(function_keys) or not function_keys[int(key[1:])-1]):return 0
        if key=='ENTER' and item is not None and column is None:return 1008
        if key=='SELECT':return 1008
        if session['mask']&category:return code
        if key=='REFRESH':
            for entry in session['items']:
                if entry['tree'] is not None:session['trees'][entry['tree']]=entry['column']['cells'][0].read() is True
        elif key in ('UP','DOWN','LEFT','RIGHT','HOME','END','PAGE_UP','PAGE_DOWN') and items:
            at=next((i for i,entry in enumerate(items) if entry is item),0);delta=session['rows']-2 if key.startswith('PAGE') else 1
            at=0 if key=='HOME' else len(items)-1 if key=='END' else max(0,min(len(items)-1,at+(-delta if key in ('UP','LEFT','PAGE_UP') else delta)))
            session['current']=items[at]['number']
        elif column is not None and (key=='ENTER' or len(key)==1):
            if item['tree'] is not None:
                value=not session['trees'][item['tree']];self.commit(editor,column,value,line);session['trees'][item['tree']]=value
            else:return super().step(editor,key,line)[0]
        return 0

    def invoke(self,state,name,args,line=None):
        status=args[-1];session=None
        try:
            session=self.prepare_form(state,args,line);pendant=session['pendant'];pendant.reserve()
            if session['new_window']:
                pendant.windows[self.window]=dict(rows=session['rows'],cols=session['cols'],options=0,
                    lines=[' '*session['cols']]*session['rows'],cursor=dict(row=1,col=1,wrap=False))
            session['background']=list(pendant.windows[self.window]['lines'])
            self.sequence+=1;session['id']=self.sequence;self._sessions[self.sequence]=session
            for index in range(min(session['data_count'],len(session['changes'].raw().values))):session['changes'].raw().set(index+1,False,line)
            self.display(session,True,line)
            for _ in range(4096):
                key=yield from self.read_key(state,session,'DISCTRL_FORM',line)
                try:terminal=self.act_key(session,key,line)
                except ValueError as error:session['error']=str(error)[:128];terminal=0
                self.draw(session,line)
                if terminal:args[7].set(terminal,line);status.set(0,line);return
                yield from rt().checkpoint(state,line)
            status.set(5,line)
        except ValueError:status.set(1,line)
        finally:
            if session is not None and 'id' in session:self.close(session,line)
