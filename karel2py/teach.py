"""Explicit offline TP program data, access handles and portable operations."""
from copy import deepcopy
import re


TPE_CONSTANTS={'TPE_RDACC':1,'TPE_RWACC':2,'TPE_NOREJ':0,'TPE_RDREJ':1,
    'TPE_WRTREJ':2,'TPE_RWREJ':3,'TPE_ALLREJ':4,'TPE_NOT_FOUND':1,
    'TPE_INVALID':2,'TPE_ACCESS':3,'TPE_BUSY':4,'TPE_EXISTS':5,'TPE_FULL':6,
    'TPE_CMT_TRUNCATED':7,'TPE_CMT_CAPACITY':8,'TPE_UNINITIALIZED':17038}
TPE_NAMES=frozenset(('OPEN_TPE','CLOSE_TPE','CREATE_TPE','COPY_TPE','SELECT_TPE',
    'AVL_POS_NUM','DEL_INST_TPE','GET_POS_FRM','GET_POS_TYP','GET_POS_TPE',
    'GET_JPOS_TPE','SET_POS_TPE','SET_EPOS_TPE','SET_JPOS_TPE','SET_TRNS_TPE',
    'GET_TPE_CMT','SET_TPE_CMT'))
KIND_NAMES={'TP':'PT_MNE_UNDEF','JB':'PT_MNE_JOB','PR':'PT_MNE_PROC','MR':'PT_MNE_MACRO'}


def rt():
    from . import runtime
    return runtime


def name_key(value,line=None):
    value=rt().ascii_string(value,line).upper()
    return value if re.fullmatch(r'[A-Z][A-Z_0-9]{0,35}',value) else None


def cartesian_value(kind,value,line=None):
    runtime=rt()
    from .extended import pose_extended
    with runtime._numeric_scope('pythonic'):
        value=runtime.frame_value(value,line)
        if value.spec==(kind,): return value
        if kind=='XYZWPREXT': return pose_extended(value,line)
        if kind=='XYZWPR' and value.spec==('XYZWPREXT',):
            result=runtime.Structure(('XYZWPR',))
            result.values.update({key:deepcopy(value.values[key]) for key in result.types})
            return runtime.checked(result.spec,result,line)
        return runtime.convert_position((kind,),value,line)


class TeachPrograms:
    """Logical TP records; no native TP parser, execution, robot or filesystem."""
    def __init__(self,programs=None,*,groups=(1,),position_limit=32767,program_limit=256,selected=None):
        if type(groups) not in (tuple,list) or not groups or any(type(g) is not int or not 1<=g<=32 for g in groups) or len(set(groups))!=len(groups):
            raise ValueError('TP groups require distinct INTEGERs in 1..32')
        if type(position_limit) is not int or not 1<=position_limit<=32767: raise ValueError('TP position limit must be in 1..32767')
        if type(program_limit) is not int or not 1<=program_limit<=4096: raise ValueError('TP program limit must be in 1..4096')
        if programs is None: programs={}
        if type(programs) is not dict or len(programs)>program_limit: raise ValueError('TP programs require a bounded name mapping')
        self.groups=tuple(groups);self.position_limit=position_limit;self.program_limit=program_limit
        self._programs={};self._handles={};self._sequence=0;self.selected=None
        for name,row in programs.items():
            key=name_key(name)
            if key is None or key in self._programs: raise ValueError('Invalid or duplicate TP program name')
            if type(row) is not dict or set(row)-{'type','instructions','positions','comments','attributes'}: raise ValueError('Unknown TP program fields')
            kind=row.get('type','TP')
            if type(kind) is not str or kind not in KIND_NAMES: raise ValueError('TP type must be TP, JB, PR or MR')
            instructions=row.get('instructions',[])
            if type(instructions) is not list or len(instructions)>32767: raise ValueError('TP instructions require a bounded list')
            if any(type(text) is not str or not text.isascii() or len(text)>254 or '\n' in text or '\r' in text for text in instructions):
                raise ValueError('TP instructions require single-line ASCII text up to 254 characters')
            program={'type':kind,'instructions':instructions.copy(),'positions':{},'comments':{},'attributes':{}}
            positions=row.get('positions',[])
            if type(positions) is not list or len(positions)>position_limit*len(groups): raise ValueError('Invalid TP position list')
            for item in positions:
                if type(item) is not dict or set(item)-{'group','number','value','uframe','utool'} or not {'group','number','value'}<=set(item): raise ValueError('Invalid TP position row')
                group,number=item['group'],item['number']
                if not self.address(group,number) or (group,number) in program['positions']: raise ValueError('Invalid or duplicate TP position address')
                frame,tool=item.get('uframe',0),item.get('utool',0)
                if any(type(n) is not int or not 0<=n<=32767 for n in (frame,tool)): raise ValueError('Invalid TP frame/tool identifiers')
                value=self.position_value(item['value'])
                program['positions'][group,number]={'value':value,'uframe':frame,'utool':tool}
            comments=row.get('comments',{})
            if type(comments) is not dict: raise ValueError('TP comments require position-number keys')
            for number,text in comments.items():
                if type(number) is not str or not number.isascii() or not number.isdecimal() or str(int(number))!=number: raise ValueError('TP comment keys require canonical position numbers')
                if not self.recorded(program,int(number)) or type(text) is not str or not text.isascii() or len(text)>16: raise ValueError('TP comments require recorded positions and at most 16 ASCII characters')
                program['comments'][int(number)]=text
            from .extended import ProgramAttributes,PROGRAM_WRITABLE_ATTRIBUTES
            attributes=row.get('attributes',{})
            if type(attributes) is not dict or set(attributes)-PROGRAM_WRITABLE_ATTRIBUTES: raise ValueError('TP attributes require supported writable header keys')
            for attr,value in attributes.items():
                program['attributes'][attr]=ProgramAttributes._value(attr,value)
                if type(value) is str and program['attributes'][attr]!=value: raise ValueError('TP header attribute exceeds its capacity')
            self._programs[key]=program
        if selected is not None:
            key=name_key(selected)
            if key not in self._programs: raise ValueError('Selected TP program is absent')
            self.selected=key

    @staticmethod
    def position_value(value,line=None):
        runtime=rt();spec=getattr(value,'spec',())
        if not spec or spec[0] not in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS'):
            raise runtime.KarelRuntimeError('TP position requires complete pose or joint data',line)
        with runtime._numeric_scope('pythonic'):
            return runtime.checked(spec,value,line) if spec[0]=='JOINTPOS' else runtime.frame_value(value,line)

    def address(self,group,number):
        return type(group) is int and group in self.groups and type(number) is int and 1<=number<=self.position_limit

    @staticmethod
    def recorded(program,number): return any(n==number for group,n in program['positions'])

    @property
    def entries(self): return tuple(sorted((name,row['type']) for name,row in self._programs.items()))

    @property
    def open_count(self): return len(self._handles)

    def busy(self,name): return any(row['name']==name for row in self._handles.values())

    def create(self,name,kind='TP',line=None):
        name=name_key(name,line)
        if name is None or kind not in KIND_NAMES: return 2
        if name in self._programs: return 5
        if len(self._programs)>=self.program_limit: return 6
        self._programs[name]={'type':kind,'instructions':[],'positions':{},'comments':{},'attributes':{}}
        return 0

    def copy(self,source,target,overwrite=False,line=None):
        source=name_key(source,line);target=name_key(target,line)
        if type(overwrite) is not bool: raise rt().KarelRuntimeError('TP overwrite requires BOOLEAN',line)
        if source is None or target is None or source==target: return 2
        if source not in self._programs: return 1
        if self.busy(source) or self.busy(target) or self.selected==target: return 4
        if target in self._programs and not overwrite: return 5
        if target not in self._programs and len(self._programs)>=self.program_limit: return 6
        value=deepcopy(self._programs[source]);self._programs[target]=value;return 0

    def select(self,name,line=None):
        name=name_key(name,line)
        if name is None: return 2
        if name not in self._programs: return 1
        if self.busy(name): return 4
        self.selected=name;return 0

    def open(self,name,mode,reject=0,*,owner=None,line=None):
        runtime=rt();name=name_key(name,line);mode=runtime.integer(mode,line);reject=runtime.integer(reject,line)
        if name is None or mode not in (0,1,2) or reject not in (0,1,2,3,4): return 2,None
        if name not in self._programs: return 1,None
        access=(0,1,3)[mode]
        for other in self._handles.values():
            if other['name']!=name or other['owner'] is owner: continue
            if reject==4 or other['reject']==4 or (other['reject'] & access) or (reject & (0,1,3)[other['mode']]): return 4,None
        if len(self._handles)>=1024 or self._sequence>=2147483646: return 6,None
        self._sequence+=1
        self._handles[self._sequence]={'name':name,'mode':mode,'reject':reject,'owner':owner}
        return 0,self._sequence

    def handle(self,number,owner=None,*,write=False,access=True,line=None):
        number=rt().integer(number,line);handle=self._handles.get(number)
        if handle is None or handle['owner'] is not owner: return 3,None
        if access and (handle['mode']==0 or write and handle['mode']!=2): return 3,None
        return 0,self._programs[handle['name']]

    def close(self,number,*,owner=None,line=None):
        code,_=self.handle(number,owner,access=False,line=line)
        if not code: del self._handles[number]
        return code

    def release_owner(self,owner):
        for number in [n for n,row in self._handles.items() if row['owner'] is owner]: del self._handles[number]

    def read_position(self,handle,number,group=1,*,owner=None,line=None):
        number=rt().integer(number,line);group=rt().integer(group,line)
        code,program=self.handle(handle,owner,line=line)
        if code: return code,None
        if not self.address(group,number): return 2,None
        row=program['positions'].get((group,number))
        return (0,deepcopy(row)) if row is not None else (17038,None)

    def write_position(self,handle,number,value,group=1,*,owner=None,uframe=None,utool=None,line=None):
        runtime=rt();number=runtime.integer(number,line);group=runtime.integer(group,line)
        code,program=self.handle(handle,owner,write=True,line=line)
        if code: return code
        if not self.address(group,number): return 2
        old=program['positions'].get((group,number),{'uframe':0,'utool':0})
        frame=old['uframe'] if uframe is None else runtime.integer(uframe,line)
        tool=old['utool'] if utool is None else runtime.integer(utool,line)
        if not 0<=frame<=32767 or not 0<=tool<=32767: return 2
        value=self.position_value(value,line)
        program['positions'][group,number]={'value':value,'uframe':frame,'utool':tool};return 0

    def metadata(self,name):
        from .extended import PROGRAM_KINDS
        row=self._programs.get(name)
        if row is None: return None
        attrs={'AT_PROG_TYPE':PROGRAM_KINDS[KIND_NAMES[row['type']]],'AT_NUM_LINE':len(row['instructions']),
               'AT_OWNER':'','AT_COMMENT':'','AT_SRC_NAME':'','AT_SRC_VRSN':0,**row['attributes']}
        return {'loaded':True,'initialized':bool(row['positions']),
                'active':self.busy(name) or self.selected==name,'attributes':attrs}

    def set_metadata(self,name,key,value): self._programs[name]['attributes'][key]=value

    def to_config(self):
        from .storage import typed_value
        programs={}
        for name,row in sorted(self._programs.items()):
            programs[name]={'type':row['type'],'instructions':row['instructions'].copy(),
                'positions':[{'group':group,'number':number,'value':typed_value(item['value']),
                              'uframe':item['uframe'],'utool':item['utool']}
                             for (group,number),item in sorted(row['positions'].items())],
                'comments':{str(n):v for n,v in sorted(row['comments'].items())},'attributes':row['attributes'].copy()}
        result={'groups':list(self.groups),'position_limit':self.position_limit,'program_limit':self.program_limit,'programs':programs}
        if self.selected is not None: result['selected']=self.selected
        return result

    @classmethod
    def from_config(cls,config):
        from .storage import decode_typed
        if type(config) is not dict or set(config)-{'groups','position_limit','program_limit','programs','selected'}: raise ValueError('Unknown TP context fields')
        values=deepcopy(config)
        programs=values.get('programs',{})
        if type(programs) is not dict: raise ValueError('TP programs require a mapping')
        for row in programs.values():
            if type(row) is not dict or type(row.get('positions',[])) is not list: raise ValueError('Malformed TP program')
            for item in row.get('positions',[]):
                if type(item) is not dict or 'value' not in item: raise ValueError('Malformed typed TP position')
                typed=item['value']
                if type(typed) is not dict or set(typed)!={'type','value'}: raise ValueError('TP positions require typed values')
                spec=typed['type']
                valid=(type(spec) is str and spec.upper() in ('POSITION','XYZWPR','XYZWPREXT',*rt().JOINT_TYPE_NAMES))
                if type(spec) in (tuple,list):
                    valid=(len(spec)==1 and spec[0] in ('POSITION','XYZWPR','XYZWPREXT') or
                           len(spec)==2 and spec[0]=='JOINTPOS' and type(spec[1]) is int and 1<=spec[1]<=9)
                if not valid: raise ValueError('TP typed values require Cartesian records or exact-width joints')
                item['value']=decode_typed(item['value'])[1]
        return cls(**values)


def invoke_teach(context,state,name,args,line=None):
    runtime=rt();bank=context.require('teach_programs',line);owner=runtime.task_root(state)
    if name=='CREATE_TPE':
        from .extended import PROGRAM_KINDS
        kind=next((kind for kind,key in KIND_NAMES.items() if PROGRAM_KINDS[key]==args[1]),None)
        args[2].set(bank.create(args[0],kind,line),line);return
    if name=='COPY_TPE': args[3].set(bank.copy(*args[:3],line=line),line);return
    if name=='SELECT_TPE': args[1].set(bank.select(args[0],line),line);return
    if name=='OPEN_TPE':
        code,handle=bank.open(*args[:3],owner=owner,line=line)
        if not code: args[3].set(handle,line)
        args[4].set(code,line);return
    if name=='CLOSE_TPE': args[1].set(bank.close(args[0],owner=owner,line=line),line);return
    if name.startswith(('GET_POS_','GET_JPOS_')):
        getter=name in ('GET_POS_TPE','GET_JPOS_TPE')
        group=(owner.robot_group or 1) if getter and args[3] is None else args[3] if getter else args[2]
        code,row=bank.read_position(args[0],args[1],group,owner=owner,line=line)
        if getter:
            value=None
            if not code:
                stored=row['value']
                if (stored.spec[0]=='JOINTPOS')!=(name=='GET_JPOS_TPE'): code=2
                else:
                    with runtime._numeric_scope('pythonic'):
                        value=runtime.padded_joints(stored,line) if name=='GET_JPOS_TPE' else cartesian_value('XYZWPREXT',stored,line)
            args[2].set(code,line)
            if code: raise runtime.KarelRuntimeError('TP position getter failed; inspect status before retrying',line)
            return value
        if not code:
            if name=='GET_POS_FRM': values=row['uframe'],row['utool']
            else:
                value=row['value'];kind=value.spec[0]
                values={'POSITION':1,'XYZWPR':2,'XYZWPREXT':6,'JOINTPOS':9}[kind],runtime.joint_width(value.spec) if kind=='JOINTPOS' else 3 if kind=='XYZWPREXT' else 0
            args[3].set(values[0],line);args[4].set(values[1],line)
        args[5].set(code,line);return
    if name in ('SET_POS_TPE','SET_EPOS_TPE','SET_JPOS_TPE','SET_TRNS_TPE'):
        group=args[4] if len(args)==5 and args[4] is not None else owner.robot_group or 1
        value=args[2]
        if name!='SET_JPOS_TPE':
            kind={'SET_POS_TPE':'XYZWPR','SET_EPOS_TPE':'XYZWPREXT','SET_TRNS_TPE':'POSITION'}[name]
            value=cartesian_value(kind,value,line)
        args[3].set(bank.write_position(args[0],args[1],value,group,owner=owner,line=line),line);return
    write=name in ('DEL_INST_TPE','SET_TPE_CMT')
    code,program=bank.handle(args[0],owner,write=write,line=line)
    status=args[-1]
    if not code:
        if name=='AVL_POS_NUM':
            occupied={n for group,n in program['positions']}
            number=next((n for n in range(1,bank.position_limit+1) if n not in occupied),None)
            if number is None: code=6
            else: args[1].set(number,line)
        elif name=='DEL_INST_TPE':
            number=runtime.integer(args[1],line)
            if not 1<=number<=len(program['instructions']): code=2
            else: del program['instructions'][number-1]
        else:
            number=runtime.integer(args[1],line)
            if not bank.address(bank.groups[0],number): code=2
            elif not bank.recorded(program,number): code=17038
            elif name=='SET_TPE_CMT':
                text=runtime.ascii_string(args[2],line);program['comments'][number]=text[:16]
                if len(text)>16: code=7
            else:
                text=program['comments'].get(number,'')
                capacity=args[2].spec[1]
                if type(capacity) is not int or not 1<=capacity<=254:
                    raise runtime.KarelRuntimeError('TP comments require a concrete STRING output capacity',line)
                if len(text)>capacity: code=8
                else: args[2].set(text,line)
    status.set(code,line)
