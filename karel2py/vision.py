"""Supplied completed vision results and portable vision-register operations."""
from copy import deepcopy
import math
import re


VISION_PROCEDURES={
    'V_RUN_FIND':(('i','STRING'),('i','INTEGER'),('o','INTEGER')),
    'V_CSAPI_TESTRUN':(('i','STRING'),('i','INTEGER'),('o','INTEGER')),
    'V_GET_FOUND':(('i','STRING'),('o','INTEGER'),('o','INTEGER'),('o','INTEGER'),('o','XYZWPR'),('r','XYZWPR_ARRAY'),('r','REAL_ARRAY'),('o','INTEGER')),
    'V_GET_OFFSET':(('i','STRING'),('i','INTEGER'),('o','INTEGER')),
    'V_GET_PASSFL':(('i','STRING'),('i','INTEGER'),('o','INTEGER')),
    'V_GET_VPARAM':(('i','STRING'),('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'V_ADJ_2D':(('i','INTEGER'),('i','REAL'),('i','REAL'),('o','INTEGER')),
    'VREG_OFFSET':(('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'VREG_FND_POS':(('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'V_SET_REF':(('i','STRING'),('o','INTEGER')),
    'V_OVERRIDE':(('i','STRING'),('i','REAL'),('o','INTEGER')),
    'V_CSAPI_GETVALUE':(('i','STRING'),('i','STRING'),('o','REAL'),('o','INTEGER')),
    'V_CSAPI_SETVALUE':(('i','STRING'),('i','STRING'),('i','REAL'),('o','INTEGER')),
    'V_CSAPI_NUMSET':(('i','STRING'),('o','REAL'),('o','INTEGER')),
    'V_CSAPI_SAVEDATA':(('i','STRING'),('o','INTEGER')),
    'V_CSAPI_RESETDATA':(('i','STRING'),('o','INTEGER')),
}
VISION_FUNCTIONS={
    'IRVU_VRGETMEAS':((('i','INTEGER'),('i','INTEGER'),('o','REAL')),('INTEGER',)),
    'IRVU_VRGETOFFSET':((('i','INTEGER'),('o','XYZWPR'),('o','INTEGER'),('o','STRING')),('INTEGER',)),
    'IRVU_VRGETVIEW':((('i','INTEGER'),('i','INTEGER'),('o','XYZWPR'),('o','INTEGER')),('INTEGER',)),
}
VISION_CALLS=set(VISION_PROCEDURES)|set(VISION_FUNCTIONS)
MAX_SEQUENCE=2147483646


def rt():
    from . import runtime
    return runtime


def integer(value,low=0,high=MAX_SEQUENCE):
    if type(value) is not int or not low<=value<=high:raise ValueError('Vision INTEGER outside its explicit range')
    return value


def real(value):
    try:valid=type(value) in (float,int) and math.isfinite(value)
    except OverflowError:valid=False
    if not valid:raise ValueError('Vision values require finite numbers')
    return float(value)


def name(value):
    if type(value) is not str or not 1<=len(value)<=254 or any(not 32<=ord(c)<=126 for c in value) or not value.strip():raise ValueError('Vision names require nonempty printable ASCII')
    return value.upper()


def mapping(value,maximum=256):
    if type(value) is not dict or len(value)>maximum:raise ValueError('Vision mapping exceeds its explicit capacity')
    return value


def named(value):
    result={}
    for key,row in mapping(value).items():
        key=name(key)
        if key in result:raise ValueError('Duplicate case-insensitive vision name')
        result[key]=row
    return result


def pose(value):
    from .storage import decode_typed
    try:
        if type(value) is dict:spec,value=decode_typed(value)
        if type(value) is not rt().Structure or value.spec!=('XYZWPR',):raise ValueError('Vision positions require exact complete XYZWPR data')
        with rt()._numeric_scope('pythonic'):return rt().checked(('XYZWPR',),value)
    except (rt().KarelRuntimeError,KeyError,TypeError) as error:raise ValueError('Vision positions require exact complete XYZWPR data') from error


def result(value):
    if type(value) is not dict or not {'offset','views'}<=set(value) or set(value)-{'offset','views','frame','model','encoder','measurements','comment','score'}:raise ValueError('Malformed supplied vision result')
    views={}
    for key,row in mapping(value['views'],4).items():
        if type(key) is not str or key not in ('1','2','3','4') or type(row) is not dict or set(row)!={'position','model'}:raise ValueError('Vision result views require canonical 1..4, position and model')
        views[key]=dict(position=pose(row['position']),model=integer(row['model']))
    if not views:raise ValueError('Vision result requires at least one supplied view')
    measurements=value.get('measurements',[])
    if type(measurements) is not list or len(measurements)>10:raise ValueError('At most ten supplied measurements')
    comment=value.get('comment','')
    if type(comment) is not str or len(comment)>254 or any(not 32<=ord(c)<=126 for c in comment):raise ValueError('Vision comment requires bounded printable ASCII')
    return dict(offset=pose(value['offset']),views=views,frame=integer(value.get('frame',0)),model=integer(value.get('model',0)),encoder=integer(value.get('encoder',0),-2147483648),measurements=[real(v) for v in measurements],comment=comment,score=real(value.get('score',0)))


def encode_result(value):
    from .storage import typed_value
    row=deepcopy(value);row['offset']=typed_value(row['offset'])
    for view in row['views'].values():view['position']=typed_value(view['position'])
    return row


class VisionServices:
    """Completed input batches only; no camera, pixel algorithm or controller I/O."""
    def __init__(self,*,count=10,registers=None,processes=None,overrides=None,limit=500,sequence=0,history=None):
        self.count=integer(count,1,32767);self.limit=integer(limit,1,4096);self.sequence=integer(sequence)
        self.registers={};self.processes={};self.overrides={};self.history=[]
        for key,row in mapping({} if registers is None else registers,32767).items():
            if type(key) is not int:raise ValueError('Vision register keys require INTEGER addresses')
            self.registers[integer(key,1,self.count)]=result(row)
        total=0
        for key,row in named({} if processes is None else processes).items():
            if type(row) is not dict or not {'views','runs'}<=set(row) or set(row)-{'views','runs','parameters','overwritten','temporary','active','cursor','reference'}:raise ValueError('Vision process requires explicit views and runs')
            views=row['views']
            if type(views) is not list or not views or len(views)>4 or any(type(v) is not int or not 1<=v<=4 for v in views) or len(set(views))!=len(views):raise ValueError('Vision process views require distinct IDs 1..4')
            process=dict(views=sorted(views),parameters={k:real(v) for k,v in named(row.get('parameters',{})).items()})
            for field in ('overwritten','temporary'):
                process[field]={k:real(v) for k,v in named(row.get(field,{})).items()}
                if set(process[field])-set(process['parameters']):raise ValueError('Vision overrides require declared parameters')
            runs=row['runs']
            if type(runs) is not list or len(runs)>4096:raise ValueError('At most 4096 completed vision batches')
            process['runs']=[self.batch(v,process) for v in runs]
            active=row.get('active');process['active']=None if active is None else self.batch(active,process,active=True)
            process['cursor']=integer(row.get('cursor',0),0,len(process['active']['results']) if process['active'] is not None else 0)
            reference=row.get('reference');process['reference']=None if reference is None else result(reference)
            if process['reference'] is not None and set(map(int,process['reference']['views']))-set(views):raise ValueError('Reference view is not configured')
            total+=sum(len(v['results']) for v in process['runs'])+(len(process['active']['results']) if process['active'] else 0)
            if total>4096:raise ValueError('Vision result capacity exceeds 4096')
            self.processes[key]=process
        for key,row in named({} if overrides is None else overrides).items():
            if type(row) is not dict or set(row)!={'process','parameter'}:raise ValueError('Vision override requires explicit process and parameter')
            owner,parameter=name(row['process']),name(row['parameter'])
            if owner not in self.processes or parameter not in self.processes[owner]['parameters']:raise ValueError('Vision override binding is not configured')
            self.overrides[key]=dict(process=owner,parameter=parameter)
        if history is None:history=[]
        if type(history) is not list or len(history)>self.limit:raise ValueError('Vision history exceeds its ring limit')
        previous=0
        for row in history:
            if type(row) is not dict or set(row)!={'sequence','program','operation','target','status'}:raise ValueError('Malformed vision history')
            integer(row['sequence'],previous+1,self.sequence);previous=row['sequence']
            if type(row['operation']) is not str or row['operation'] not in VISION_CALLS:raise ValueError('Unknown vision history operation')
            for field in ('program','target'):
                if type(row[field]) is not str or len(row[field])>254 or any(not 32<=ord(c)<=126 for c in row[field]):raise ValueError('Malformed vision history text')
            integer(row['status']);self.history.append(deepcopy(row))

    @staticmethod
    def batch(row,process,active=False):
        allowed={'camera_view','status','results','pass_flag'}|({'parameters'} if active else set())
        if type(row) is not dict or not {'camera_view','status','results'}<=set(row) or set(row)-allowed:raise ValueError('Vision batch requires camera_view, status and results')
        view=integer(row['camera_view'],-1,4)
        if view==0 or view!=-1 and view not in process['views']:raise ValueError('Batch camera view requires -1 or a configured view')
        status=integer(row['status']);rows=row['results']
        if type(rows) is not list or len(rows)>4096 or status and rows:raise ValueError('Vision batch results must be bounded and empty on failure')
        rows=[result(v) for v in rows];selected=process['views'] if view==-1 else [view]
        if any(set(map(int,v['views']))-set(selected) for v in rows):raise ValueError('Batch result view is outside its selection')
        answer=dict(camera_view=view,status=status,results=rows)
        if 'pass_flag' in row:answer['pass_flag']=integer(row['pass_flag'],0,2)
        if active:
            values={k:real(v) for k,v in named(row.get('parameters',{})).items()}
            if set(values)!=set(process['parameters']):raise ValueError('Active vision run requires every captured parameter')
            answer['parameters']=values
        return answer

    @staticmethod
    def selection(process,view,test=False):
        if view==-1 or test and view==0:return process['views']
        if view==0 and len(process['views'])==1:return process['views']
        return [view] if view in process['views'] else None

    def begin(self,state,operation,target):
        if self.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Vision request sequence exhausted')
        self.sequence+=1;row=dict(sequence=self.sequence,program=rt().task_root(state).program_name,operation=operation,target=str(target),status=0)
        self.history.append(row);del self.history[:-self.limit];return row

    def register(self,number):
        return (2,None) if type(number) is not int or not 1<=number<=self.count else (0,self.registers[number]) if number in self.registers else (1,None)

    def invoke(self,state,operation,args,line=None):
        # All source references have already passed shared disjoint/type guards.
        target=args[0];function=operation in VISION_FUNCTIONS
        status=None if function else args[-1]
        if self.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Vision request sequence exhausted',line)
        code=0;pairs=[];commit=None
        process=self.processes.get(target.upper()) if type(target) is str else None
        if operation in ('V_RUN_FIND','V_CSAPI_TESTRUN'):
            if process is None:code=2
            else:
                selected=self.selection(process,args[1],operation=='V_CSAPI_TESTRUN')
                if selected is None:code=2
                elif not process['runs']:raise rt().KarelRuntimeError('Vision execution requires an explicit completed result batch',line)
                else:
                    batch=process['runs'][0]
                    if self.selection(process,batch['camera_view'])!=selected:code=2
                    else:
                        captured=dict(process['parameters'])
                        if operation=='V_CSAPI_TESTRUN':captured.update(process['overwritten'])
                        captured.update(process['temporary']);active=deepcopy(batch);active['parameters']=captured;code=batch['status']
                        def commit():
                            process['runs'].pop(0);process['active']=active;process['cursor']=0;process['temporary'].clear()
        elif operation.startswith('V_CSAPI_'):
            if process is None:code=2
            elif operation=='V_CSAPI_NUMSET':pairs=[(args[1],float(len(process['overwritten']))) ]
            elif operation in ('V_CSAPI_GETVALUE','V_CSAPI_SETVALUE'):
                parameter=args[1].upper()
                if parameter not in process['parameters']:code=4
                elif operation=='V_CSAPI_GETVALUE':pairs=[(args[2],process['overwritten'].get(parameter,process['parameters'][parameter]))]
                else:
                    value=rt().real(args[2],line)
                    def commit():process['overwritten'][parameter]=value
            elif operation=='V_CSAPI_RESETDATA':
                def commit():process['overwritten'].clear()
            else:
                def commit():process['parameters'].update(process['overwritten']);process['overwritten'].clear()
        elif operation=='V_OVERRIDE':
            binding=self.overrides.get(target.upper())
            if binding is None:code=4
            else:
                owner=self.processes[binding['process']];parameter=binding['parameter'];value=rt().real(args[1],line)
                def commit():owner['temporary'][parameter]=value
        elif operation in ('V_GET_FOUND','V_GET_OFFSET','V_GET_PASSFL','V_GET_VPARAM','V_SET_REF'):
            active=process['active'] if process is not None else None
            if process is None:code=2
            elif active is None:code=1
            elif active['status']:code=active['status']
            elif operation in ('V_GET_FOUND','V_GET_OFFSET'):
                cursor=process['cursor']
                if cursor>=len(active['results']):code=117151
                else:
                    value=active['results'][cursor]
                    if operation=='V_GET_OFFSET':
                        number=args[1]
                        if not 1<=number<=self.count:code=2
                        else:
                            detached=deepcopy(value)
                            def commit():self.registers[number]=detached;process['cursor']+=1
                    else:
                        positions=rt().require(args[5].raw(),line);measurements=rt().require(args[6].raw(),line)
                        if len(positions.values)<max(map(int,value['views'])) or len(measurements.values)<len(value['measurements']):code=3
                        else:
                            pairs=[(args[1],value['frame']),(args[2],value['model']),(args[3],value['encoder']),(args[4],value['offset'])]
                            pairs.extend((rt().index_reference(positions,int(view),line),row['position']) for view,row in value['views'].items())
                            pairs.extend((rt().index_reference(measurements,i+1,line),v) for i,v in enumerate(value['measurements']))
                            def commit():process['cursor']+=1
            elif operation=='V_SET_REF':
                if not active['results']:code=117151
                else:
                    reference=deepcopy(max(active['results'],key=lambda v:v['score']))
                    def commit():process['reference']=reference
            else:
                bank=state.execution.require('numeric',line);number=args[3] if operation=='V_GET_VPARAM' else args[1]
                if not 1<=number<=bank.count:code=2
                elif operation=='V_GET_PASSFL':
                    if 'pass_flag' not in active:code=1
                    else:
                        value=active['pass_flag']
                        def commit():bank.write(number,value,line)
                else:
                    selected=self.selection(process,args[2])
                    if args[1]!=0 or selected is None:code=2
                    else:
                        value=float(sum(any(int(k) in selected for k in v['views']) for v in active['results']))
                        def commit():bank.write(number,value,line)
        else:
            code,value=self.register(target)
            if not code:
                if operation in ('IRVU_VRGETVIEW','VREG_FND_POS'):
                    view=args[1]
                    if not 1<=view<=4:code=2
                    elif str(view) not in value['views']:code=12311
                    elif operation=='IRVU_VRGETVIEW':pairs=[(args[2],value['views'][str(view)]['position']),(args[3],value['views'][str(view)]['model'])]
                    else:value=value['views'][str(view)]['position']
                if not code and operation=='IRVU_VRGETMEAS':
                    index=args[1]
                    if not 1<=index<=10:code=2
                    elif index>len(value['measurements']):code=1
                    else:pairs=[(args[2],value['measurements'][index-1])]
                elif not code and operation=='IRVU_VRGETOFFSET':pairs=[(args[1],value['offset']),(args[2],value['frame']),(args[3],value['comment'])]
                elif not code and operation=='V_ADJ_2D':
                    adjusted=deepcopy(value)
                    adjusted['offset'].values['X']=rt().real(value['offset'].values['X']+args[1],line)
                    adjusted['offset'].values['Y']=rt().real(value['offset'].values['Y']+args[2],line)
                    def commit():self.registers[target]=adjusted
                elif not code and operation in ('VREG_OFFSET','VREG_FND_POS'):
                    bank=state.execution.require('positions',line);group=rt().task_root(state).robot_group or 1;number=args[2] if operation=='VREG_FND_POS' else args[1]
                    if group not in bank.groups or not 1<=number<=bank.count:code=2
                    else:
                        point=deepcopy(value if operation=='VREG_FND_POS' else value['offset'])
                        def commit():bank.write(number,point,group)
        # Failed lookups preserve all ordinary outputs and result cursors.
        if code:pairs=[]
        staged=[(ref,rt().checked(ref.spec,value,line)) for ref,value in pairs]
        if status is not None:staged.append((status,rt().checked(status.spec,code,line)))
        row=self.begin(state,operation,target);row['status']=code
        for ref,output in staged:ref.set(output,line)
        if commit is not None:commit()
        return code if function else None

    def to_config(self):
        processes={}
        for key,process in self.processes.items():
            row=deepcopy(process)
            for batch in row['runs']+([row['active']] if row['active'] is not None else []):batch['results']=[encode_result(v) for v in batch['results']]
            if row['reference'] is not None:row['reference']=encode_result(row['reference'])
            processes[key]=row
        return dict(count=self.count,registers={str(k):encode_result(v) for k,v in sorted(self.registers.items())},processes=processes,overrides=deepcopy(self.overrides),limit=self.limit,sequence=self.sequence,history=deepcopy(self.history))

    def snapshot(self):return self.to_config()

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'count','registers','processes','overrides','limit','sequence','history'}:raise ValueError('Unknown vision configuration fields')
        config=dict(config);registers=mapping(config.get('registers',{}),32767)
        if any(type(k) is not str or not re.fullmatch(r'[1-9][0-9]*',k) for k in registers):raise ValueError('Vision JSON register keys require canonical positive integers')
        config['registers']={int(k):v for k,v in registers.items()};return cls(**config)
