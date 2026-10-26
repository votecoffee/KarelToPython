"""Headless pendant display definitions, character surfaces and request history."""
from copy import deepcopy
import re

# Pane labels follow the documented pane numbering. Menu/screen/option labels
# are portable IDs; native environment binary encodings are not inferred.
PENDANT_CONSTANTS={'TP_PANEL':1,'TP2_PANEL':2,'TP3_PANEL':3,'WD_COM_CURSR':1,'WD_SCROLLED':2}
PENDANT_CONSTANTS.update((name,1001+index) for index,name in enumerate((
    'SPI_TPUSER','SPI_TPUSER2','SPI_TPHINTS','SPI_TPPRGADJ','SPI_TPMIRROR','SPI_TPSHIFT',
    'SPI_TPTSTRUN','SPI_TPMANUAL','SPI_TPOTREL','SPI_TPALARM','SPI_TPDIGIO','SPI_TPANAIO',
    'SPI_TPGRPIO','SPI_TPROBIO','SPI_TPUOPIO','SPI_TPSOPIO','SPI_TPPLCIO','SPI_TPSETGEN',
    'SPI_TPFRAM','SPI_TPPORT','SPI_TPMMACRO','SPI_TPREFPOS','SPI_TPPWORD','SPI_TPHCCOMM',
    'SPI_TPSYRSR','SPI_TPFILS','SPI_TPSTATUS','SPI_TPMEMORY','SPI_TPVERSN','SPI_TPPRGSTS',
    'SPI_TPSFTY','SPI_TPSELECT','SPI_TPTCH','SPI_TPREGIS','SPI_SFMPREG','SPI_TPSYSV',
    'SPI_TPPOSN','SPI_TPMASCAL','SPI_TPBRKCTR','SPI_TPAXLM','SPI_CRTKCL')))
PENDANT_CONSTANTS.update((name,2001+index) for index,name in enumerate((
    'SCR_MACMAN','SCR_ALM_ALL','SCR_ALM_MOT','SCR_ALM_SYS','SCR_ALM_APPL','SCR_MACSETUP',
    'SCR_AXIS','SCR_NUMREG','SCR_POSREG','SCR_NUMVAR','SCR_POSVAR','SCR_CLOCK','SCR_KCL')))
PENDANT_CONSTANTS.update(("DP_"+name,name) for name in ('DEFAULT','ENGLISH','JAPANESE','FRENCH','GERMAN','SPANISH'))
PENDANT_CALLS={'FORCE_LINK','FORCE_SPMENU','SET_LANG','DEF_SCREEN','DEF_WINDOW',
               'ACT_SCREEN','ATT_WINDOW_D','ATT_WINDOW_S','DET_WINDOW','SET_CURSOR'}


def rt():
    from . import runtime
    return runtime


def ordinary_name(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,3}',value):raise ValueError('Display names require 1..4 identifier characters')
    return value.upper()


def language_name(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z_0-9]{0,15}',value):raise ValueError('Language names require bounded ASCII identifiers')
    return value.upper()


def printable(value,minimum=0,maximum=254):
    return type(value) is str and minimum<=len(value)<=maximum and all(32<=ord(char)<=126 for char in value)


def cursor_valid(cursor,rows,cols):
    return (type(cursor) is dict and set(cursor)=={'row','col','wrap'}
        and type(cursor['row']) is int and 1<=cursor['row']<=rows
        and type(cursor['col']) is int and 1<=cursor['col']<=cols
        and type(cursor['wrap']) is bool and (not cursor['wrap'] or cursor['col']==cols))


class PendantDisplay:
    """Logical TP surfaces only; no browser, desktop, network or native display."""
    def __init__(self,*,rows=24,cols=80,max_cells=65536,limit=500,languages=None,
                 default_language='ENGLISH',language=None,screens=None,windows=None,
                 active=None,links=None,menus=None,history=None,sequence=0):
        if type(rows) is not int or type(cols) is not int or not 1<=rows<=256 or not 1<=cols<=256:raise ValueError('Display dimensions require 1..256')
        if type(max_cells) is not int or not 1<=max_cells<=262144:raise ValueError('Window cell budget requires 1..262144')
        if type(limit) is not int or not 1<=limit<=4096:raise ValueError('Display history limit requires 1..4096')
        if type(sequence) is not int or not 0<=sequence<=2147483646:raise ValueError('Display sequence is invalid')
        if languages is None:languages=['ENGLISH']
        if type(languages) is not list or not 1<=len(languages)<=32:raise ValueError('Display requires 1..32 language labels')
        self.languages=[language_name(name) for name in languages]
        if len(set(self.languages))!=len(self.languages) or 'DEFAULT' in self.languages:raise ValueError('Language labels must be distinct; DEFAULT is a selector')
        self.default_language=language_name(default_language);self.language=language_name(default_language if language is None else language)
        if self.default_language not in self.languages or self.language not in self.languages:raise ValueError('Default/current language must be configured')
        self.rows=rows;self.cols=cols;self.max_cells=max_cells;self.limit=limit;self.sequence=sequence
        self.windows={};self.screens={};self.links={};self.menus={};self.history=[];self._handles={}
        if windows is None:windows={}
        if type(windows) is not dict or len(windows)>64:raise ValueError('At most 64 windows may be configured')
        total=0
        for name,window in windows.items():
            key=ordinary_name(name)
            if key!=name or key in self.windows:raise ValueError('Window names must be canonical and unique')
            if type(window) is not dict or set(window)!={'rows','cols','options','lines','cursor'}:raise ValueError('Malformed window')
            n_rows,n_cols,options=(window[key] for key in ('rows','cols','options'))
            if type(n_rows) is not int or type(n_cols) is not int or not 1<=n_rows<=256 or not 1<=n_cols<=256 or type(options) is not int or not 0<=options<=3:raise ValueError('Invalid window dimensions/options')
            total+=n_rows*n_cols
            if total>max_cells:raise ValueError('Window cell budget exceeded')
            if type(window['lines']) is not list or len(window['lines'])!=n_rows or any(not printable(row,n_cols,n_cols) for row in window['lines']):raise ValueError('Window lines require exact printable character widths')
            if not cursor_valid(window['cursor'],n_rows,n_cols):raise ValueError('Invalid window cursor')
            self.windows[key]=deepcopy(window)
        if screens is None:screens={'SYS':{'device':'TP','attachments':[]}}
        if type(screens) is not dict or not 1<=len(screens)<=64:raise ValueError('Display requires 1..64 screens')
        for name,screen in screens.items():
            if ordinary_name(name)!=name or type(screen) is not dict or set(screen)!={'device','attachments'} or screen['device']!='TP':raise ValueError('Malformed screen')
            attachments=screen['attachments']
            if type(attachments) is not list or len(attachments)>64:raise ValueError('Too many screen attachments')
            seen=set()
            for item in attachments:
                if type(item) is not dict or set(item)!={'window','row','col'} or type(item['window']) is not str or item['window'] in seen or item['window'] not in self.windows:raise ValueError('Malformed screen attachment')
                if not self.fits(self.windows[item['window']],item['row'],item['col']):raise ValueError('Screen attachment exceeds display bounds')
                seen.add(item['window'])
            self.screens[name]=deepcopy(screen)
        if active is None:active={'TP':next(iter(self.screens))}
        if type(active) is not dict or set(active)!={'TP'} or type(active['TP']) is not str or active['TP'] not in self.screens:raise ValueError('Active TP screen must be defined')
        self.active=active.copy()
        for field,values in (('links',{} if links is None else links),('menus',{} if menus is None else menus)):
            if type(values) is not dict or any(type(key) is not str or not re.fullmatch(r'[1-9]',key) for key in values):raise ValueError('Pane keys require 1..9')
            for key,value in values.items():
                if field=='links' and not printable(value,1):raise ValueError('Link requires a bounded printable location')
                if field=='menus' and (type(value) is not dict or set(value)!={'menu','screen'} or any(type(value[key]) is not int or not 1<=value[key]<=32767 for key in value)):raise ValueError('Invalid menu request')
                getattr(self,field)[key]=deepcopy(value)
        if history is None:history=[]
        if type(history) is not list or len(history)>limit:raise ValueError('Display history exceeds ring limit')
        previous=0
        for item in history:
            if type(item) is not dict or set(item)!={'sequence','program','operation','data'}:raise ValueError('Malformed display history')
            if type(item['sequence']) is not int or not previous<item['sequence']<=sequence:raise ValueError('History sequence must increase')
            if type(item['program']) is not str or not item['program'].isascii() or len(item['program'])>254:raise ValueError('Display owner must be bounded ASCII')
            if type(item['operation']) is not str or item['operation'] not in PENDANT_CALLS|{'WINDOW_WRITE','WINDOW_OPEN','WINDOW_CLOSE'}:raise ValueError('Unknown display history operation')
            data=item['data']
            if type(data) is not dict or len(data)>8 or any(type(key) is not str or len(key)>32 for key in data):raise ValueError('Invalid display history data')
            if any(not (printable(value) or type(value) is int and -2147483648<=value<=2147483646) for value in data.values()):raise ValueError('History values require bounded printable text or INTEGERs')
            self.history.append(deepcopy(item));previous=item['sequence']

    def fits(self,window,row,col):
        return type(row) is int and type(col) is int and row>=1 and col>=1 and row+window['rows']-1<=self.rows and col+window['cols']-1<=self.cols

    def reserve(self):
        if self.sequence>=2147483646:raise rt().KarelRuntimeError('Display request sequence exhausted')

    def record(self,state,operation,**data):
        self.sequence+=1
        self.history.append(dict(sequence=self.sequence,program=rt().task_root(state).program_name if state is not None else '',operation=operation,data=data))
        del self.history[:-self.limit]

    def attach(self,window,screen,row,col):
        if window not in self.windows or screen not in self.screens:return 3
        if not self.fits(self.windows[window],row,col):return 1
        if any(item['window']==window for item in self.screens[screen]['attachments']):return 2
        self.screens[screen]['attachments'].append(dict(window=window,row=row,col=col));return 0

    def invoke(self,state,name,args,line=None):
        self.reserve();status=None;data={}
        try:
            if name=='FORCE_LINK':
                pane,url=args
                if type(pane) is not int or not 1<=pane<=9 or not printable(url,1):raise rt().KarelRuntimeError('FORCE_LINK requires pane 1..9 and printable location text',line)
                self.links[str(pane)]=url;data=dict(pane=pane,url=url)
            elif name=='FORCE_SPMENU':
                pane,menu,screen=args
                if any(type(value) is not int for value in args) or not 1<=pane<=9 or not 1<=menu<=32767 or not 1<=screen<=32767:raise rt().KarelRuntimeError('Invalid FORCE_SPMENU request',line)
                self.menus[str(pane)]=dict(menu=menu,screen=screen);data=dict(pane=pane,menu=menu,screen=screen)
            elif name=='SET_LANG':
                language=language_name(args[0]);language=self.default_language if language=='DEFAULT' else language
                status=0 if language in self.languages else 33003
                if not status:self.language=language;data=dict(language=language)
            elif name=='DEF_SCREEN':
                screen=ordinary_name(args[0]);device=args[1].upper()
                status=1 if device!='TP' else 2 if screen in self.screens else 5 if len(self.screens)>=64 else 0
                if not status:self.screens[screen]=dict(device=device,attachments=[]);data=dict(screen=screen,device=device)
            elif name=='DEF_WINDOW':
                window=ordinary_name(args[0]);rows,cols,options=args[1:4]
                valid=all(type(value) is int for value in (rows,cols,options)) and 1<=rows<=256 and 1<=cols<=256 and 0<=options<=3
                status=1 if not valid else 2 if window in self.windows else 5 if len(self.windows)>=64 or sum(w['rows']*w['cols'] for w in self.windows.values())+rows*cols>self.max_cells else 0
                if not status:self.windows[window]=dict(rows=rows,cols=cols,options=options,lines=[' '*cols]*rows,cursor=dict(row=1,col=1,wrap=False));data=dict(window=window,rows=rows,cols=cols,options=options)
            elif name=='ACT_SCREEN':
                screen=ordinary_name(args[0]);old=self.active['TP']
                menu=self.menus.get('1',{}).get('menu')
                status=3 if screen not in self.screens else 9093 if menu not in (PENDANT_CONSTANTS['SPI_TPUSER'],PENDANT_CONSTANTS['SPI_TPUSER2']) else 5 if args[1].spec[1]<len(old) else 0
                if not status:self.active['TP']=screen;args[1].set(old,line);data=dict(screen=screen,previous=old)
            elif name in ('ATT_WINDOW_S','ATT_WINDOW_D'):
                window=ordinary_name(args[0]);target=args[1].upper()
                screen=self.active['TP'] if name=='ATT_WINDOW_D' else ordinary_name(target)
                status=1 if name=='ATT_WINDOW_D' and target!='TP' else 5 if name=='ATT_WINDOW_D' and args[4].spec[1]<len(screen) else None
                if status is None:status=self.attach(window,screen,args[2],args[3])
                if not status:
                    if name=='ATT_WINDOW_D':args[4].set(screen,line)
                    data=dict(window=window,screen=screen,row=args[2],col=args[3])
            elif name=='DET_WINDOW':
                window,screen=(ordinary_name(arg) for arg in args[:2])
                status=3 if window not in self.windows or screen not in self.screens else 0
                if not status:
                    previous=self.screens[screen]['attachments'];current=[item for item in previous if item['window']!=window]
                    status=4 if len(previous)==len(current) else 0
                    if not status:self.screens[screen]['attachments']=current;data=dict(window=window,screen=screen)
            elif name=='SET_CURSOR':
                handle,row,col=args[:3];binding=self._handles.get(handle)
                status=4 if handle.owner is not self or binding is None else 1 if type(row) is not int or type(col) is not int or not 1<=row<=self.windows[binding['window']]['rows'] or not 1<=col<=self.windows[binding['window']]['cols'] else 0
                if not status:
                    cursor=dict(row=row,col=col,wrap=False);binding['cursor']=cursor.copy();self.windows[binding['window']]['cursor']=cursor
                    data=dict(window=binding['window'],row=row,col=col)
            else:raise rt().KarelRuntimeError('Unknown pendant display operation',line)
        except ValueError:
            if name in ('FORCE_LINK','FORCE_SPMENU'):raise
            status=1
        if status is None or status==0:self.record(state,name,**data)
        if status is not None:args[-1].set(status,line)

    def open_for(self,state,handle,mode,name,line=None):
        self.reserve()
        match=re.fullmatch(r'WD:([A-Za-z_][A-Za-z_0-9]{0,3})',name,re.I)
        if not match:raise rt().KarelRuntimeError('Window FILE requires WD:name without a keyboard suffix',line)
        window=match[1].upper();mode=rt().ascii_string(mode,line).upper()
        mode={'WO':'W','RW':'RW','UD':'RW','AP':'A'}.get(mode,mode)
        if handle.owner is not None or window not in self.windows or len(self._handles)>=256:raise rt().KarelRuntimeError('Window FILE is busy, undefined or over capacity',line)
        if mode not in ('W','RW','A') or handle.binary or handle.xml:raise rt().KarelRuntimeError('Window FILE supports text output modes only',line)
        handle.name='WD:'+window;handle.logical_name=None;handle.mode=mode;handle.position=0;handle.status=0;handle.owner=self
        handle.binary=False;handle.xml_session=None
        self._handles[handle]=dict(window=window,cursor=dict(row=1,col=1,wrap=False),state=state)
        self.record(state,'WINDOW_OPEN',window=window)

    def close(self,handle,line=None):
        if handle.owner is not self or handle not in self._handles:raise rt().KarelRuntimeError('Window FILE is not open',line)
        binding=self._handles.pop(handle);handle.owner=None;handle.xml_session=None
        if self.sequence<2147483646:self.record(binding['state'],'WINDOW_CLOSE',window=binding['window'])

    def write(self,handle,data,line=None):
        if type(data) is not bytes or len(data)>65536 or any(byte not in (8,9,10,12,13) and not 32<=byte<=126 for byte in data):raise rt().KarelRuntimeError('Window WRITE requires bounded supported ASCII text/controls',line)
        return self.write_dictionary(handle,[('text',data.decode('ascii'))],line)

    def write_dictionary(self,handle,tokens,line=None):
        """Stage one complete text/control request before changing any surface."""
        self.reserve();binding=self._handles.get(handle)
        if handle.owner is not self or binding is None:raise rt().KarelRuntimeError('Window FILE is not open',line)
        if type(tokens) is not list or len(tokens)>16384:raise rt().KarelRuntimeError('Window operation budget exceeded',line)
        window=self.windows[binding['window']];lines=list(window['lines'])
        count=0;controls={'newline':10,'lf':10,'cr':13,'clear':12,'bs':8,'tab':9}
        for token in tokens:
            if type(token) is not tuple or not token:raise rt().KarelRuntimeError('Invalid window operation',line)
            op=token[0]
            if op=='text':
                if len(token)!=2 or type(token[1]) is not str or any(ord(c) not in (8,9,10,12,13) and not 32<=ord(c)<=126 for c in token[1]):raise rt().KarelRuntimeError('Window text requires supported ASCII',line)
                count+=len(token[1])
            elif op=='cursor':
                if len(token)!=3 or any(type(v) is not int for v in token[1:]) or not 1<=token[1]<=window['rows'] or not 1<=token[2]<=window['cols']:raise rt().KarelRuntimeError('Dictionary cursor exceeds window bounds',line)
            elif op=='style':
                if len(token)!=2 or type(token[1]) is not str:raise rt().KarelRuntimeError('Invalid style token',line)
            elif op in controls:
                if len(token)!=1:raise rt().KarelRuntimeError('Invalid window control',line)
                count+=1
            elif op not in ('eol','eow','home','up') or len(token)!=1:raise rt().KarelRuntimeError('Unknown window operation',line)
        if count>65536 or handle.position+count>2147483646:raise rt().KarelRuntimeError('Window text/position budget exceeded',line)
        cursor=(window['cursor'] if window['options']&1 else binding['cursor']).copy()
        rows,cols=window['rows'],window['cols']
        def newline():
            cursor.update(col=1,wrap=False)
            if cursor['row']<rows:cursor['row']+=1
            elif window['options']&2:lines.pop(0);lines.append(' '*cols)
            else:lines[-1]=' '*cols
        def character(char):
            if cursor['wrap']:newline()
            row,col=cursor['row']-1,cursor['col']-1
            lines[row]=lines[row][:col]+char+lines[row][col+1:]
            if cursor['col']==cols:cursor['wrap']=True
            else:cursor['col']+=1
        def emit(data):
            for byte in data:
                if byte==10:newline()
                elif byte==13:cursor.update(col=1,wrap=False)
                elif byte==12:lines[:]=[' '*cols]*rows;cursor.update(row=1,col=1,wrap=False)
                elif byte==8:
                    if cursor['wrap']:cursor['wrap']=False
                    else:cursor['col']=max(1,cursor['col']-1)
                elif byte==9:
                    if cursor['wrap']:newline()
                    for _ in range(8-((cursor['col']-1)%8)):character(' ')
                else:character(chr(byte))
        for token in tokens:
            op=token[0]
            if op=='text':emit(token[1].encode('ascii'))
            elif op in controls:emit(bytes([controls[op]]))
            elif op=='cursor':cursor.update(row=token[1],col=token[2],wrap=False)
            elif op=='home':cursor.update(row=1,col=1,wrap=False)
            elif op=='up':cursor.update(row=max(1,cursor['row']-1),wrap=False)
            elif op in ('eol','eow'):
                row,col=cursor['row']-1,cursor['col']-1
                lines[row]=lines[row][:col]+' '*(cols-col);cursor['wrap']=False
                if op=='eow':lines[row+1:]=[' '*cols]*(rows-row-1)
        window['lines']=lines;window['cursor']=cursor.copy();binding['cursor']=cursor
        handle.position+=count;handle.status=0
        self.record(binding['state'],'WINDOW_WRITE',window=binding['window'],bytes=count)

    def render(self,screen=None):
        screen=self.active['TP'] if screen is None else ordinary_name(screen)
        if screen not in self.screens:raise ValueError('Unknown logical screen')
        lines=[' '*self.cols]*self.rows
        for item in self.screens[screen]['attachments']:
            window=self.windows[item['window']]
            for offset,text in enumerate(window['lines']):
                row,col=item['row']-1+offset,item['col']-1
                lines[row]=lines[row][:col]+text+lines[row][col+window['cols']:]
        return lines

    def snapshot(self):
        return dict(rows=self.rows,cols=self.cols,max_cells=self.max_cells,limit=self.limit,languages=list(self.languages),
            default_language=self.default_language,language=self.language,screens=deepcopy(self.screens),windows=deepcopy(self.windows),
            active=self.active.copy(),links=self.links.copy(),menus=deepcopy(self.menus),history=deepcopy(self.history),sequence=self.sequence,
            open_files=sorted(handle.name for handle in self._handles))

    def to_config(self):
        if self._handles:raise ValueError('Close window FILE handles before saving pendant state')
        result=self.snapshot();result.pop('open_files');return result

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'rows','cols','max_cells','limit','languages','default_language','language','screens','windows','active','links','menus','history','sequence'}:raise ValueError('Unknown pendant configuration fields')
        return cls(**config)
