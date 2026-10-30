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
VISION_IO_PROCEDURES={
    'V_SNAP_VIEW':(('i','STRING'),('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'V_FIND_VIEW':(('i','STRING'),('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'V_FIND_VLINE':(('i','STRING'),('i','INTEGER'),('i','INTEGER'),('r','VIEW_LINES'),('o','INTEGER')),
    'V_SAVE_IMREG':(('i','INTEGER'),('i','STRING'),('o','INTEGER')),
    'V_GET_READ':(('i','STRING'),('i','INTEGER'),('i','STRING'),('o','INTEGER'),('o','INTEGER')),
    'V_CAM_CHECK':(('i','STRING'),('o','BOOLEAN'),('o','INTEGER')),
    'V_CAM_CALIB':(('i','STRING'),('i','INTEGER'),('o','INTEGER')),
    'V_DISPLAY4D':(('i','STRING'),('o','INTEGER')),
    'V_LED_ON':(('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'V_LED_OFF':(('o','INTEGER'),),
}
VISION_PROCEDURES.update(VISION_IO_PROCEDURES)
VISION_FUNCTIONS={
    'IRVU_VRGETMEAS':((('i','INTEGER'),('i','INTEGER'),('o','REAL')),('INTEGER',)),
    'IRVU_VRGETOFFSET':((('i','INTEGER'),('o','XYZWPR'),('o','INTEGER'),('o','STRING')),('INTEGER',)),
    'IRVU_VRGETVIEW':((('i','INTEGER'),('i','INTEGER'),('o','XYZWPR'),('o','INTEGER')),('INTEGER',)),
}
VISION_TRACKING_PROCEDURES={
    'V_GET_QUEUE':(('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'V_INIT_QUEUE':(('i','INTEGER'),('o','INTEGER')),
    'V_RALC_QUEUE':(('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'V_START_VTRK':(('i','STRING'),('o','INTEGER')),
    'V_STOP_VTRK':(('i','STRING'),('o','INTEGER')),
    'V_ACQ_VAMAP':(('i','STRING'),('i','BOOLEAN'),('i','VECTOR'),('o','INTEGER')),
    'V_CLR_VAMAP':(('i','STRING'),('o','INTEGER')),
    'V_IRCONNECT':(('i','STRING'),('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'VT_GET_FOUND':(('i','STRING'),('o','INTEGER'),('o','INTEGER'),('o','XYZWPR'),('r','TRACKING_POSITIONS'),('r','TRACKING_MEASURES'),('o','INTEGER')),
}
VISION_TRACKING_FUNCTIONS={name:((('i','STRING'),),('INTEGER',)) for name in ('VT_GET_AREID','VT_GET_LINID','VT_GET_TRYID')}
VISION_PROCEDURES.update(VISION_TRACKING_PROCEDURES)
VISION_FUNCTIONS.update(VISION_TRACKING_FUNCTIONS)
VT_QUEUE_PROCEDURES={
    'VT_PUT_QUEUE':(('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('i','XYZWPR'),('v','TRACKING_POSITIONS'),('v','TRACKING_MEASURES'),('o','INTEGER')),
    'VT_PUT_QUE2':(('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('i','XYZWPR'),('v','TRACKING_POSITIONS'),('v','TRACKING_MEASURES'),('o','BOOLEAN'),('o','INTEGER')),
    'VT_GET_QUEUE':(('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('v','INTEGER'),('v','INTEGER'),('o','INTEGER')),
    'VT_ACK_QUEUE':(('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'VT_CLR_QUEUE':(('i','INTEGER'),('o','INTEGER')),
    'VT_GET_TIME':(('i','INTEGER'),('i','INTEGER'),('v','INTEGER'),('v','INTEGER'),('o','INTEGER'),('o','INTEGER')),
    'VT_GET_PFRT':(('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('v','INTEGER'),('o','INTEGER'),('o','INTEGER')),
    'VT_READ_PQ':(('i','INTEGER'),('r','VT_QUEUE_PATH'),('o','INTEGER')),
    'VT_WRITE_PQ':(('i','INTEGER'),('i','INTEGER'),('v','INTEGER'),('v','INTEGER'),('v','XYZWPR'),('v','XYZWPR'),('v','TRACKING_MEASURES'),('o','INTEGER')),
    'VT_DELETE_PQ':(('i','INTEGER'),('i','INTEGER'),('o','INTEGER')),
    'VT_SET_FLAG':(('i','INTEGER'),('i','INTEGER'),('i','INTEGER'),('i','VT_INT32'),('i','VT_INT32'),('o','INTEGER')),
    'VT_SET_LDBAL':(('i','INTEGER'),('i','INTEGER'),('i','VT_INT32'),('i','INTEGER'),('o','INTEGER')),
}
VISION_PROCEDURES.update(VT_QUEUE_PROCEDURES)
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
        with rt()._numeric_scope('pythonic'):return rt().positional_value(('XYZWPR',),value)
    except (rt().KarelRuntimeError,KeyError,TypeError) as error:raise ValueError('Vision positions require exact complete XYZWPR data') from error


def result(value):
    if type(value) is not dict or not {'offset','views'}<=set(value) or set(value)-{'offset','views','frame','model','encoder','measurements','comment','score'}:raise ValueError('Malformed supplied vision result')
    views={}
    for key,row in mapping(value['views'],4).items():
        if type(key) is not str or key not in ('1','2','3','4') or type(row) is not dict or set(row)!={'position','model'}:raise ValueError('Vision result views require canonical 1..4, position and model')
        views[key]=dict(position=pose(row['position']),model=integer(row['model']))
    measurements=value.get('measurements',[])
    if type(measurements) is not list or len(measurements)>10:raise ValueError('At most ten supplied measurements')
    comment=value.get('comment','')
    if type(comment) is not str or len(comment)>254 or any(not 32<=ord(c)<=126 for c in comment):raise ValueError('Vision comment requires bounded printable ASCII')
    return dict(offset=pose(value['offset']),views=views,frame=integer(value.get('frame',0)),model=integer(value.get('model',0)),encoder=integer(value.get('encoder',0),-2147483648),measurements=[None if v is None else real(v) for v in measurements],comment=comment,score=real(value.get('score',0)))


def encode_result(value):
    from .storage import typed_value
    row=deepcopy(value);row['offset']=typed_value(row['offset'])
    for view in row['views'].values():view['position']=typed_value(view['position'])
    return row


class VisionServices:
    """Completed input batches only; no camera, pixel algorithm or controller I/O."""
    def __init__(self,*,count=10,registers=None,processes=None,overrides=None,limit=500,sequence=0,history=None,io=None,tracking=None):
        self.count=integer(count,1,32767);self.limit=integer(limit,1,4096);self.sequence=integer(sequence)
        self.registers={};self.processes={};self.overrides={};self.history=[]
        for key,row in mapping({} if registers is None else registers,32767).items():
            if type(key) is not int:raise ValueError('Vision register keys require INTEGER addresses')
            self.registers[integer(key,1,self.count)]=result(row)
        total=batches=line_count=read_size=0
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
            completed=process['runs']+([process['active']] if process['active'] is not None else [])
            batches+=len(completed);line_count+=sum(len(v.get('view_lines',{}).get('nodes',[])) for v in completed);read_size+=sum(len(v.get('read_result','')) for v in completed)
            if batches>4096 or line_count>32767 or read_size>4*1024*1024:raise ValueError('Combined vision batch, view-line or reader capacity exceeded')
            self.processes[key]=process
        for key,row in named({} if overrides is None else overrides).items():
            if type(row) is not dict or set(row)!={'process','parameter'}:raise ValueError('Vision override requires explicit process and parameter')
            owner,parameter=name(row['process']),name(row['parameter'])
            if owner not in self.processes or parameter not in self.processes[owner]['parameters']:raise ValueError('Vision override binding is not configured')
            self.overrides[key]=dict(process=owner,parameter=parameter)
        self.io=None if io is None else VisionIO(io,self.processes)
        self.tracking=None
        if tracking is not None:
            from .vision_tracking import VisionTracking
            self.tracking=VisionTracking(tracking,self)
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
        allowed={'camera_view','status','results','pass_flag','operation','image_reg','read_result','view_lines'}|({'parameters'} if active else set())
        if type(row) is not dict or not {'camera_view','status','results'}<=set(row) or set(row)-allowed:raise ValueError('Vision batch requires camera_view, status and results')
        view=integer(row['camera_view'],-1,4)
        if view==0 or view!=-1 and view not in process['views']:raise ValueError('Batch camera view requires -1 or a configured view')
        status=integer(row['status']);rows=row['results']
        if type(rows) is not list or len(rows)>4096 or status and rows:raise ValueError('Vision batch results must be bounded and empty on failure')
        rows=[result(v) for v in rows];selected=process['views'] if view==-1 else [view]
        if any(set(map(int,v['views']))-set(selected) for v in rows):raise ValueError('Batch result view is outside its selection')
        answer=dict(camera_view=view,status=status,results=rows)
        if 'pass_flag' in row:answer['pass_flag']=integer(row['pass_flag'],0,2)
        operation=row.get('operation','find')
        if type(operation) is not str or operation not in ('find','lines'):raise ValueError('Vision batch operation requires find or lines')
        if 'operation' in row:answer['operation']=operation
        if 'image_reg' in row:answer['image_reg']=integer(row['image_reg'],0,32767)
        if 'read_result' in row:
            text=row['read_result']
            if type(text) is not str or not text.isascii() or len(text)>65535 or status:raise ValueError('Reader output requires at most 65535 ASCII characters on success')
            answer['read_result']=text
        if 'view_lines' in row:
            if operation!='lines' or status:raise ValueError('View lines require a successful lines batch')
            answer['view_lines']=view_lines(row['view_lines'])
        if operation=='lines' and (rows or 'pass_flag' in row or 'read_result' in row or view!=1 or not status and 'view_lines' not in row):raise ValueError('Lines batches require view 1, only view-line output on success, and no workpiece/reader/flag results')
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

    def active_batch(self,process,batch,test=False):
        captured=dict(process['parameters'])
        if test:captured.update(process['overwritten'])
        captured.update(process['temporary']);active=deepcopy(batch);active['parameters']=captured;return active

    def note_active(self,process):
        if self.tracking is not None:self.tracking.latest=process.upper()

    def invoke(self,state,operation,args,line=None):
        if operation in VT_QUEUE_PROCEDURES:
            if self.tracking is None or self.tracking.vt is None:raise rt().KarelRuntimeError('Operation requires explicit vision tracking vt configuration',line)
            return self.tracking.vt.invoke(state,operation,args,line)
        if operation in VISION_TRACKING_PROCEDURES or operation in VISION_TRACKING_FUNCTIONS:
            from .vision_tracking import invoke_tracking
            return invoke_tracking(self,state,operation,args,line)
        if operation in VISION_IO_PROCEDURES:return invoke_io(self,state,operation,args,line)
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
                    if batch.get('operation','find')!='find' or batch.get('image_reg',0)!=0 or self.selection(process,batch['camera_view'])!=selected:code=2
                    else:
                        active=self.active_batch(process,batch,operation=='V_CSAPI_TESTRUN');code=batch['status']
                        def commit():
                            process['runs'].pop(0);process['active']=active;process['cursor']=0;process['temporary'].clear();self.note_active(target)
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
                        elif self.tracking is not None and (self.tracking.register_busy(number) or self.tracking.register_allocated(number)):code=3
                        else:
                            detached=deepcopy(value)
                            def commit():
                                self.registers[number]=detached;process['cursor']+=1
                                if self.tracking is not None:self.tracking.invalidate(number)
                    else:
                        positions=rt().require(args[5].raw(),line);measurements=rt().require(args[6].raw(),line)
                        if len(positions.values)<max(map(int,value['views']),default=0) or len(measurements.values)<len(value['measurements']):code=3
                        else:
                            pairs=[(args[1],value['frame']),(args[2],value['model']),(args[3],value['encoder']),(args[4],value['offset'])]
                            pairs.extend((rt().index_reference(positions,int(view),line),row['position']) for view,row in value['views'].items())
                            pairs.extend((rt().index_reference(measurements,i+1,line),v) for i,v in enumerate(value['measurements']) if v is not None)
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
                        value=float(sum((not v['views'] and args[2] in (-1,0)) or any(int(k) in selected for k in v['views']) for v in active['results']))
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
                    elif index>len(value['measurements']) or value['measurements'][index-1] is None:code=1
                    else:pairs=[(args[2],value['measurements'][index-1])]
                elif not code and operation=='IRVU_VRGETOFFSET':pairs=[(args[1],value['offset']),(args[2],value['frame']),(args[3],value['comment'])]
                elif not code and operation=='V_ADJ_2D':
                    if self.tracking is not None and self.tracking.register_busy(target):code=3
                    else:
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
        answer=dict(count=self.count,registers={str(k):encode_result(v) for k,v in sorted(self.registers.items())},processes=processes,overrides=deepcopy(self.overrides),limit=self.limit,sequence=self.sequence,history=deepcopy(self.history))
        if self.io is not None:answer['io']=self.io.to_config()
        if self.tracking is not None:answer['tracking']=self.tracking.to_config()
        return answer

    def snapshot(self):return self.to_config()

    @classmethod
    def from_config(cls,config):
        if type(config) is not dict or set(config)-{'count','registers','processes','overrides','limit','sequence','history','io','tracking'}:raise ValueError('Unknown vision configuration fields')
        config=dict(config);registers=mapping(config.get('registers',{}),32767)
        if any(type(k) is not str or not re.fullmatch(r'[1-9][0-9]*',k) for k in registers):raise ValueError('Vision JSON register keys require canonical positive integers')
        config['registers']={int(k):v for k,v in registers.items()};return cls(**config)


def vector(value):
    if type(value) is not list or len(value)!=3:raise ValueError('View-line vectors require three finite numbers')
    return [real(v) for v in value]


def view_lines(row):
    if type(row) is not dict or set(row)!={'group','frame','focal','nodes'}:raise ValueError('View-line data requires group, frame, focal and nodes')
    nodes=row['nodes']
    if type(nodes) is not list or len(nodes)>4096:raise ValueError('At most 4096 supplied view lines per batch')
    prepared=[]
    for node in nodes:
        if type(node) is not dict or set(node)!={'direction','polarity','model'}:raise ValueError('View-line node requires direction, polarity and model')
        direction=vector(node['direction']);polarity=vector(node['polarity'])
        if not all(0<math.hypot(*v)<math.inf for v in (direction,polarity)):raise ValueError('View-line directions and polarities require finite nonzero lengths')
        prepared.append(dict(direction=direction,polarity=polarity,model=integer(node['model'])))
    return dict(group=integer(row['group'],1,32),frame=integer(row['frame'],0,32767),focal=vector(row['focal']),nodes=prepared)


_IMAGE_RAW_LIMIT=16*1024*1024
_IMAGE_TOTAL_LIMIT=64*1024*1024


def raster(row,limit,*,remaining=None):
    fields={'width','height','channels','pixels'}
    if type(row) is not dict or not fields<=set(row) or set(row)-fields-{'palette','sample_bits'}:raise ValueError('Image requires width, height, channels and pixels')
    width=integer(row['width'],1,4096);height=integer(row['height'],1,4096);channels=row['channels']
    if type(channels) is not int or channels not in (1,2,3,4):raise ValueError('Images require grayscale, grayscale-alpha, RGB or RGBA channels')
    bits=row.get('sample_bits',8)
    if type(bits) is not int or bits not in (8,16):raise ValueError('Image sample_bits requires 8 or 16')
    pixels=row['pixels'];size=width*height*channels*(bits//8);palette=row.get('palette');palette_size=0
    if 'palette' in row:
        if channels!=1 or bits!=8:raise ValueError('An explicit palette requires channels=1 and 8-bit index bytes')
        if type(palette) not in (bytes,str):raise ValueError('Image palette requires packed RGBA bytes or canonical lowercase hexadecimal')
        palette_size=len(palette)//2 if type(palette) is str else len(palette)
        if (type(palette) is str and len(palette)%8 or not 4<=palette_size<=1024 or palette_size%4):
            raise ValueError('Image palette requires 1..256 packed RGBA entries')
    if size+palette_size>limit:raise ValueError('Raw image exceeds its configured byte limit')
    if remaining is not None and size+palette_size>remaining:raise ValueError('Combined vision raw-image capacity exceeds 64 MiB')
    if type(palette) is str:
        if re.fullmatch('[0-9a-f]*',palette) is None:raise ValueError('Image JSON palette requires canonical lowercase hexadecimal bytes')
        palette=bytes.fromhex(palette)
    if type(pixels) is str:
        if len(pixels)!=size*2 or re.fullmatch('[0-9a-f]*',pixels) is None:raise ValueError('Image JSON pixels require canonical lowercase hexadecimal bytes')
        pixels=bytes.fromhex(pixels)
    if type(pixels) is not bytes or len(pixels)!=size:raise ValueError('Raw pixel size does not match image dimensions')
    if palette is not None and max(pixels)>=palette_size//4:raise ValueError('Image pixel index is outside its explicit palette')
    return dict(width=width,height=height,channels=channels,pixels=pixels,**({'palette':palette} if palette is not None else {}),**({'sample_bits':bits} if 'sample_bits' in row else {}))


class VisionIO:
    """Bounded supplied rasters and logical camera, calibration, display and LED data."""
    def __init__(self,config,processes):
        fields={'image_count','image_limit','images','captures','cameras','calibrations','display_tools','displayed','led_channels','led'}
        if type(config) is not dict or set(config)-fields:raise ValueError('Unknown vision I/O configuration fields')
        self.image_count=integer(config.get('image_count',0),0,256);self.image_limit=integer(config.get('image_limit',_IMAGE_RAW_LIMIT),1,_IMAGE_RAW_LIMIT)
        self.images={};total=0
        def image_record(row,*,capture=False):
            nonlocal total
            required={'process','views','status'} if capture else {'process','views','image'}
            allowed={'process','views','image','status'} if capture else required
            if type(row) is not dict or not required<=set(row) or set(row)-allowed:raise ValueError('Malformed supplied image/capture record')
            owner=name(row['process']);views=row['views']
            if owner not in processes or type(views) is not list or not views or any(type(v) is not int or v not in processes[owner]['views'] for v in views) or len(set(views))!=len(views):raise ValueError('Image requires a configured process and distinct configured views')
            answer=dict(process=owner,views=sorted(views))
            code=integer(row['status']) if capture else 0
            if capture:answer['status']=code
            if code and 'image' in row or not code and 'image' not in row:raise ValueError('Only successful captures require an image')
            if not code:
                answer['image']=raster(row['image'],self.image_limit,remaining=_IMAGE_TOTAL_LIMIT-total)
                total+=len(answer['image']['pixels'])+len(answer['image'].get('palette',b''))
            return answer
        for key,row in mapping(config.get('images',{}),256).items():
            if type(key) is not str or re.fullmatch('[1-9][0-9]*',key) is None:raise ValueError('Image register keys require canonical positive numbers')
            key=integer(int(key),1,self.image_count);self.images[key]=image_record(row)
        captures=config.get('captures',[])
        if type(captures) is not list or len(captures)>4096 or captures and not self.image_count:raise ValueError('Capture queue requires an image bank and at most 4096 responses')
        self.captures=[image_record(row,capture=True) for row in captures]
        self.cameras={}
        for key,row in named(config.get('cameras',{})).items():
            if type(row) is not dict or set(row)-{'powered','status'}:raise ValueError('Camera requires powered and optional status')
            code=integer(row.get('status',0))
            if 'powered' in row and type(row['powered']) is not bool or not code and 'powered' not in row:raise ValueError('Successful camera query requires explicit BOOLEAN power state')
            self.cameras[key]=dict(row,status=code)
        self.calibrations={};total=0
        def calibration(row):
            if type(row) is not dict or set(row)!={'function','status'}:raise ValueError('Calibration reply requires function and status')
            return dict(function=integer(row['function'],1,32767),status=integer(row['status']))
        for key,row in named(config.get('calibrations',{})).items():
            if type(row) is not dict or set(row)-{'responses','last'} or type(row.get('responses')) is not list:raise ValueError('Calibration requires an explicit response queue')
            total+=len(row['responses'])
            if total>4096:raise ValueError('At most 4096 calibration replies')
            self.calibrations[key]=dict(responses=[calibration(v) for v in row['responses']],last=None if row.get('last') is None else calibration(row['last']))
        self.display_tools={k:integer(v) for k,v in named(config.get('display_tools',{})).items()}
        self.displayed=config.get('displayed')
        if self.displayed is not None:
            self.displayed=name(self.displayed)
            if self.displayed not in self.display_tools:raise ValueError('Displayed tool must be explicitly configured')
        channels=config.get('led_channels',[])
        if type(channels) is not list or any(type(v) is not int or not 1<=v<=8 for v in channels) or len(set(channels))!=len(channels):raise ValueError('LED channels require distinct numbers 1..8')
        self.led_channels=sorted(channels);self.led=deepcopy(config.get('led'))
        if self.led is not None:
            if type(self.led) is not dict or set(self.led)!={'channel','intensity'}:raise ValueError('Active LED requires channel and intensity')
            channel=integer(self.led['channel'],1,8);integer(self.led['intensity'],1,16)
            if channel not in self.led_channels:raise ValueError('Active LED channel is not configured')

    def to_config(self):
        def image_record(row):
            row=deepcopy(row)
            if 'image' in row:
                row['image']['pixels']=row['image']['pixels'].hex()
                if 'palette' in row['image']:row['image']['palette']=row['image']['palette'].hex()
            return row
        return dict(image_count=self.image_count,image_limit=self.image_limit,images={str(k):image_record(v) for k,v in sorted(self.images.items())},captures=[image_record(v) for v in self.captures],cameras=deepcopy(self.cameras),calibrations=deepcopy(self.calibrations),display_tools=self.display_tools.copy(),displayed=self.displayed,led_channels=self.led_channels.copy(),led=deepcopy(self.led))


def encode_raster(image,format,limit,check):
    """Encode checked samples; BMP rounds 16-bit components to eight bits."""
    import struct
    import zlib
    image=raster(image,_IMAGE_RAW_LIMIT)
    if format not in ('PNG','BMP'):raise ValueError('Raster export requires PNG or BMP')
    width,height,channels,pixels=(image[k] for k in ('width','height','channels','pixels'))
    palette=image.get('palette');bits=image.get('sample_bits',8)
    def bmp_row(y):
        # Called after size preflight and a row checkpoint, before publication.
        stride=width*channels*(bits//8);row=pixels[y*stride:(y+1)*stride]
        if bits==16:
            row=bytes((row[i]*256+row[i+1]+128)//257 for i in range(0,len(row),2))
        return row
    if format=='BMP' and (channels in (2,4) or palette is not None):
        stride=width*4;offset=14+108;size=offset+stride*height
        if size>limit:return None
        rows=[];colors=None if palette is None else tuple(bytes((palette[i+2],palette[i+1],palette[i],palette[i+3])) for i in range(0,len(palette),4))
        for y in range(height-1,-1,-1):
            check();row=bmp_row(y)
            if colors is not None:rows.append(b''.join(colors[index] for index in row));continue
            bgra=bytearray(stride)
            if channels==2:
                gray=row[0::2];bgra[0::4]=gray;bgra[1::4]=gray;bgra[2::4]=gray;bgra[3::4]=row[1::2]
            else:
                bgra[0::4]=row[2::4];bgra[1::4]=row[1::4];bgra[2::4]=row[0::4];bgra[3::4]=row[3::4]
            rows.append(bytes(bgra))
        header=struct.pack('<IiiHHIIiiII',108,width,height,1,32,3,stride*height,0,0,0,0)
        header+=struct.pack('<IIIII',0x00ff0000,0x0000ff00,0x000000ff,0xff000000,0x73524742)+b'\0'*48
        return struct.pack('<2sIHHI',b'BM',size,0,0,offset)+header+b''.join(rows)
    if format=='BMP':
        stride=(width*3+3)//4*4;size=54+stride*height
        if size>limit:return None
        rows=[]
        for y in range(height-1,-1,-1):
            check();row=bmp_row(y)
            if channels==1:row=b''.join(bytes((v,v,v)) for v in row)
            else:
                bgr=bytearray(len(row));bgr[0::3]=row[2::3];bgr[1::3]=row[1::3];bgr[2::3]=row[0::3];row=bytes(bgr)
            rows.append(row+b'\0'*(stride-len(row)))
        return struct.pack('<2sIHHI',b'BM',size,0,0,54)+struct.pack('<IiiHHIIiiII',40,width,height,1,24,0,stride*height,0,0,0,0)+b''.join(rows)
    palette_entries=0 if palette is None else len(palette)//4
    transparent=palette is not None and any(palette[i]!=255 for i in range(3,len(palette),4))
    overhead=0 if palette is None else 12+palette_entries*3+(12+palette_entries if transparent else 0)
    if limit<57+overhead:return None
    rows=[];stride=width*channels*(bits//8)
    for start in range(0,len(pixels),stride):check();rows.append(b'\0'+pixels[start:start+stride])
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    table=b'' if palette is None else chunk(b'PLTE',b''.join(palette[i:i+3] for i in range(0,len(palette),4)))
    if transparent:table+=chunk(b'tRNS',palette[3::4])
    encoded=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,bits,3 if palette is not None else {1:0,2:4,3:2,4:6}[channels],0,0,0))+table+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
    return encoded if len(encoded)<=limit else None


def prepare_write(files,filename,data,line):
    """Prepare one whole named-file replacement; never truncate through OPEN."""
    from .extended import MemoryFiles
    from .devices import DeviceFiles
    from .storage import DirectoryFiles,atomic_bytes
    if type(files) not in (MemoryFiles,DeviceFiles,DirectoryFiles):return 6,None
    try:
        if len(data)>files.limit:return 5,None
        if type(files) is DirectoryFiles:
            key=files._key(filename);path=files._path(key)
            if files._busy(key):return 3,None
            if not path.parent.is_dir() or path.exists() and (not path.is_file() or path.stat().st_size>files.limit):return 6,None
        else:
            key=files.canonical(filename) if type(files) is DeviceFiles else filename
            files._check(key,data)
            if files._busy(key):return 3,None
            if key not in files.files and len(files.files)>=32767:return 5,None
        volume=None;obsolete=0
        if type(files) is DeviceFiles:
            volume,obsolete=files.reserve(key,len(data),len(files.files.get(key,b'')),line)
        def commit():
            try:
                if type(files) is DirectoryFiles:atomic_bytes(path,data)
                files.files[key]=bytearray(data)
                if volume is not None:volume['garbage']+=obsolete
                return 0
            except (OSError,ValueError,rt().KarelRuntimeError):return 6
        return 0,commit
    except (OSError,ValueError,rt().KarelRuntimeError):return 6,None


def stage_lines(state,reference,value,line):
    path=reference.raw();header=rt().Structure(path.spec[2]);header.values.update(GRP_NUM=value['group'],UFRM_NUM=value['frame'])
    header.values['FOCAL_POINT'].values.update(zip(('X','Y','Z'),value['focal']));nodes=[]
    for row in value['nodes']:
        state.tick(line);node=rt().Structure(path.node_spec)
        node.values['DIR'].values.update(zip(('X','Y','Z'),row['direction']));node.values['POL'].values.update(zip(('X','Y','Z'),row['polarity']));node.values['MODEL_ID']=row['model']
        nodes.append(rt().checked(node.spec,node,line))
    header=rt().checked(header.spec,header,line)
    def commit():
        path.data=rt().replace_value(path.data,header);path.nodes[:]=nodes
        return 0
    return commit


def invoke_io(bank,state,operation,args,line):
    if bank.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Vision request sequence exhausted',line)
    io=bank.io;code=0;pairs=[];commit=None;target='' if operation=='V_LED_OFF' else args[0]
    status=args[-1]
    process=bank.processes.get(target.upper()) if type(target) is str else None
    if operation=='V_GET_READ':
        active=None if process is None else process['active'];number,filename,length=args[1:4]
        if process is None:code=2
        elif active is None:code=1
        elif active['status']:code=active['status']
        elif 'read_result' not in active:code=1
        else:
            text=active['read_result']
            if number==0:
                files=state.execution.require('files',line);code,commit=prepare_write(files,filename,text.encode('ascii'),line);stored=len(text)
            elif number<0:code=2
            else:
                strings=state.execution.require('strings',line)
                if number>strings.count:code=2
                else:
                    text=text[:strings.capacity];stored=len(text)
                    def commit():return strings.write(number,text)
            if not code:pairs=[(length,stored)]
    else:
        if io is None:raise rt().KarelRuntimeError('Operation requires explicit vision io configuration',line)
        if operation in ('V_SNAP_VIEW','V_FIND_VIEW','V_FIND_VLINE'):
            view,number=args[1:3];selected=bank.selection(process,view) if process is not None else None
            image=None
            if process is None or selected is None or operation=='V_FIND_VLINE' and view!=1:code=2
            elif operation!='V_FIND_VLINE' or number>0:
                if not 1<=number<=io.image_count:code=2
                elif operation!='V_SNAP_VIEW':
                    image=io.images.get(number)
                    if image is None:code=1
                    elif image['process']!=target.upper() or not set(selected)<=set(image['views']):code=2
            if not code and operation=='V_SNAP_VIEW':
                if not io.captures:raise rt().KarelRuntimeError('V_SNAP_VIEW requires an explicit capture response',line)
                response=io.captures[0]
                if response['process']!=target.upper() or response['views']!=selected:code=2
                else:
                    code=response['status'];captured=deepcopy(response)
                    def commit():
                        io.captures.pop(0)
                        if not code:captured.pop('status');io.images[number]=captured
                        return 0
            elif not code:
                if not process['runs']:raise rt().KarelRuntimeError('Vision execution requires an explicit completed result batch',line)
                batch=process['runs'][0];expected='lines' if operation=='V_FIND_VLINE' else 'find';image_number=max(0,number)
                if batch.get('operation','find')!=expected or batch.get('image_reg',0)!=image_number or bank.selection(process,batch['camera_view'])!=selected:code=2
                else:
                    active=bank.active_batch(process,batch);code=batch['status']
                    publish=stage_lines(state,args[3],batch['view_lines'],line) if not code and operation=='V_FIND_VLINE' else None
                    def commit():
                        if publish is not None:publish()
                        process['runs'].pop(0);process['active']=active;process['cursor']=0;process['temporary'].clear();bank.note_active(target);return 0
        elif operation=='V_SAVE_IMREG':
            number,filename=args[:2]
            if not 1<=number<=io.image_count:code=2
            elif number not in io.images:code=1
            else:
                extension=filename.rsplit('.',1)[-1].upper() if '.' in filename else ''
                if extension not in ('PNG','BMP'):code=2
                else:
                    files=state.execution.require('files',line)
                    try:data=encode_raster(io.images[number]['image'],extension,files.limit,lambda:state.tick(line))
                    except ValueError as exc:raise rt().KarelRuntimeError('Invalid supplied image: '+str(exc),line) from exc
                    if data is None:code=5
                    else:code,commit=prepare_write(files,filename,data,line)
        elif operation=='V_CAM_CHECK':
            camera=io.cameras.get(target.upper())
            if camera is None:code=2
            else:
                code=camera['status']
                if not code:pairs=[(args[1],camera['powered'])]
        elif operation=='V_CAM_CALIB':
            calibration=io.calibrations.get(target.upper())
            if calibration is None or args[1]<1 or args[1]>32767:code=2
            elif not calibration['responses']:raise rt().KarelRuntimeError('V_CAM_CALIB requires an explicit calibration reply',line)
            else:
                response=calibration['responses'][0]
                if response['function']!=args[1]:code=2
                else:
                    code=response['status'];reply=deepcopy(response)
                    def commit():calibration['responses'].pop(0);calibration['last']=reply;return 0
        elif operation=='V_DISPLAY4D':
            if target.upper() not in io.display_tools:code=2
            else:
                code=io.display_tools[target.upper()]
                if not code:
                    def commit():io.displayed=target.upper();return 0
        elif operation=='V_LED_ON':
            if type(target) is not int or target not in io.led_channels or not 1<=args[1]<=16:code=2
            else:
                led=dict(channel=target,intensity=args[1])
                def commit():io.led=led;return 0
        elif not io.led_channels:code=2
        else:
            def commit():io.led=None;return 0
    # Failed scripted completions are consumed, but failed preflight plans have
    # no commit. Publish ordinary outputs only after a successful file commit.
    staged=[(ref,rt().checked(ref.spec,value,line)) for ref,value in pairs] if not code else []
    row=bank.begin(state,operation,target)
    if commit is not None:
        outcome=commit()
        if outcome:code=outcome;staged=[]
    for ref,value in staged:ref.set(value,line)
    row['status']=code;status.set(code,line)
