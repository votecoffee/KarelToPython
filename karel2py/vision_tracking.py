"""Explicit legacy tracking queues, supplied area maps and vision-result outbox."""
from copy import deepcopy
import json
import re

from .vision import integer,real,name,named,mapping,result,encode_result,raster,MAX_SEQUENCE


def rt():
    from . import runtime
    return runtime


def part(row):
    if type(row) is not dict or set(row)!={'work_id','result'}:raise ValueError('Tracking part requires work_id and result')
    return dict(work_id=integer(row['work_id'],1),result=result(row['result']))


def encode_part(row):return dict(work_id=row['work_id'],result=encode_result(row['result']))


def point_map(row):
    if type(row) is not dict or set(row)!={'frame','points'} or type(row['points']) is not list or len(row['points'])>4096:raise ValueError('Area map requires frame and at most 4096 supplied points')
    points=[]
    for point in row['points']:
        if type(point) is not list or len(point)!=3:raise ValueError('Map point requires three finite coordinates')
        points.append([real(v) for v in point])
    return dict(frame=integer(row['frame'],0,32767),points=points)


def active_payload(row):
    row=deepcopy(row);row['results']=[encode_result(v) for v in row['results']];return row


def json_size(value):return len(json.dumps(value,allow_nan=False,separators=(',',':')).encode('ascii'))


class VisionTracking:
    def __init__(self,config,owner):
        allowed={'queues','allocations','triggers','processes','ids','sensors','latest','outbox','outbox_limit','payload_limit','include_images','vt'}
        if type(config) is not dict or set(config)-allowed:raise ValueError('Unknown vision tracking configuration fields')
        self.vt=None
        self.owner=owner;self.queues={};self.allocations={};self.triggers={};self.pending={};self.ids={};self.sensors={};self.outbox=[]
        total=0
        for key,row in mapping(config.get('queues',{})).items():
            if type(key) is not str or re.fullmatch('[1-9][0-9]*',key) is None:raise ValueError('Tracking queue keys require canonical positive numbers')
            number=integer(int(key),1,32767)
            if type(row) is not dict or set(row)-{'capacity','parts','arrivals','elapsed_ms'} or 'capacity' not in row:raise ValueError('Tracking queue requires explicit capacity')
            capacity=integer(row['capacity'],1,4096);parts=row.get('parts',[]);arrivals=row.get('arrivals',[])
            if type(parts) is not list or len(parts)>capacity or type(arrivals) is not list:raise ValueError('Tracking queue parts/arrivals must fit explicit bounds')
            queue=dict(capacity=capacity,parts=[part(v) for v in parts],arrivals=[],elapsed_ms=integer(row.get('elapsed_ms',0)))
            previous=-1
            for arrival in arrivals:
                if type(arrival) is not dict or set(arrival)!={'at_ms','part'}:raise ValueError('Arrival requires at_ms and part')
                at=integer(arrival['at_ms'],max(0,previous));previous=at
                queue['arrivals'].append(dict(at_ms=at,part=part(arrival['part'])))
            identifiers=[v['work_id'] for v in queue['parts']]+[v['part']['work_id'] for v in queue['arrivals']]
            if len(set(identifiers))!=len(identifiers):raise ValueError('Tracking queue work IDs must be distinct')
            total+=len(identifiers)
            if total>4096:raise ValueError('At most 4096 tracking workpieces and future arrivals')
            self.queues[number]=queue
        allocations=mapping(config.get('allocations',{}),32767);triggers=mapping(config.get('triggers',{}),32767)
        if set(allocations)!=set(triggers):raise ValueError('Allocation receipts and trigger records must agree')
        for key,row in allocations.items():
            if type(key) is not str or re.fullmatch('[1-9][0-9]*',key) is None:raise ValueError('Allocation keys require canonical vision-register numbers')
            vr=integer(int(key),1,owner.count)
            if vr not in owner.registers or type(row) is not dict or set(row)!={'queue','work_id'}:raise ValueError('Allocation requires a populated vision register, queue and work ID')
            queue=integer(row['queue'],1,32767);work=integer(row['work_id'],1)
            if queue not in self.queues or work in self.work_ids(queue):raise ValueError('Allocation work ID/queue is missing or already present')
            trigger=triggers[key]
            if type(trigger) is not dict or set(trigger)!={'queue','work_id','encoder'} or trigger['queue']!=queue or trigger['work_id']!=work or type(trigger['queue']) is not int or type(trigger['work_id']) is not int:raise ValueError('Malformed tracking trigger')
            encoder=integer(trigger['encoder'],-2147483648)
            if encoder!=owner.registers[vr]['encoder']:raise ValueError('Tracking trigger encoder does not match the allocated result')
            self.allocations[vr]=dict(queue=queue,work_id=work);self.triggers[vr]=dict(queue=queue,work_id=work,encoder=encoder)
            total+=1
            if total>4096:raise ValueError('At most 4096 tracking workpieces including allocations')
        self.processes={}
        for key,row in named(config.get('processes',{})).items():
            if key not in owner.processes or type(row) is not dict or set(row)!={'running'} or type(row['running']) is not bool:raise ValueError('Tracking process requires a configured vision process and BOOLEAN running flag')
            self.processes[key]=dict(running=row['running'])
        ids=config.get('ids',{})
        if type(ids) is not dict or set(ids)-{'areas','lines','trays'}:raise ValueError('Unknown tracking name-ID bank')
        for kind in ('areas','lines','trays'):
            values={k:integer(v,1,32767) for k,v in named(ids.get(kind,{})).items()}
            if len(set(values.values()))!=len(values):raise ValueError('Tracking names require distinct IDs within each bank')
            self.ids[kind]=values
        total=points=0
        for key,row in named(config.get('sensors',{})).items():
            if type(row) is not dict or set(row)-{'responses','map'} or type(row.get('responses')) is not list:raise ValueError('Area sensor requires a supplied response queue')
            sensor=dict(responses=[],map=None if row.get('map') is None else point_map(row['map']))
            points+=len(sensor['map']['points']) if sensor['map'] is not None else 0
            for response in row['responses']:
                if type(response) is not dict or 'status' not in response or set(response)-{'status','map'}:raise ValueError('Map reply requires status and map on success')
                code=integer(response['status'])
                if bool(code)==('map' in response):raise ValueError('Only successful area-map replies contain map data')
                value=point_map(response['map']) if not code else None
                points+=len(value['points']) if value is not None else 0
                if points>32767:raise ValueError('At most 32767 supplied area-map points')
                sensor['responses'].append(dict(status=code,**({'map':value} if value is not None else {})))
            total+=len(sensor['responses'])
            if total>4096:raise ValueError('At most 4096 area-map replies')
            if points>32767:raise ValueError('At most 32767 supplied area-map points')
            self.sensors[key]=sensor
        self.latest=config.get('latest')
        if self.latest is not None:
            self.latest=name(self.latest)
            if self.latest not in owner.processes or owner.processes[self.latest]['active'] is None:raise ValueError('Latest vision process requires an active supplied completion')
        self.outbox_limit=integer(config.get('outbox_limit',500),1,4096);self.payload_limit=integer(config.get('payload_limit',1024*1024),1,16*1024*1024)
        self.include_images=config.get('include_images',False)
        if type(self.include_images) is not bool:raise ValueError('include_images requires BOOLEAN')
        rows=config.get('outbox',[])
        if type(rows) is not list or len(rows)>self.outbox_limit:raise ValueError('Vision outbox capacity exceeded')
        previous=0;total=0
        for row in rows:
            packet=self.packet(row,previous);previous=packet['sequence'];total+=json_size(packet)
            if total>16*1024*1024:raise ValueError('Vision outbox exceeds 16 MiB')
            self.outbox.append(packet)

        if config.get('vt') is not None:
            from .vt_queues import VTQueues
            self.vt=VTQueues(config['vt'],self)

    def work_ids(self,number):
        queue=self.queues[number]
        return {v['work_id'] for v in queue['parts']}|{v['part']['work_id'] for v in queue['arrivals']}|{v['work_id'] for v in self.allocations.values() if v['queue']==number}

    def invalidate(self,vr):self.allocations.pop(vr,None);self.triggers.pop(vr,None)

    def register_busy(self,vr):return any(row['register']==vr for row in self.pending.values()) or self.vt is not None and self.vt.register_busy(vr)

    def register_allocated(self,vr):return self.vt is not None and vr in self.vt.allocations

    def packet(self,row,previous=0):
        if type(row) is not dict or set(row)!={'sequence','program','description','priority','process','result','images'}:raise ValueError('Malformed portable vision outbox packet')
        integer(row['sequence'],previous+1,self.owner.sequence)
        for key in ('program','description'):
            if type(row[key]) is not str or len(row[key])>254 or not row[key].isascii():raise ValueError('Vision packet text requires bounded ASCII')
        integer(row['priority'],0,3);process=name(row['process']);completion=row['result']
        if type(completion) is not dict:raise ValueError('Vision packet requires a supplied completion')
        parameters={k:real(v) for k,v in named(completion.get('parameters',{})).items()}
        completion=self.owner.batch(completion,dict(views=[1,2,3,4],parameters=parameters),active=True)
        images={}
        for key,image in mapping(row['images'],256).items():
            if type(key) is not str or re.fullmatch('[1-9][0-9]*',key) is None or not 1<=int(key)<=256 or type(image) is not dict or set(image)!={'process','views','image'}:raise ValueError('Malformed portable vision image attachment')
            views=image['views']
            if name(image['process'])!=process or type(views) is not list or not views or any(type(v) is not int or not 1<=v<=4 for v in views) or len(set(views))!=len(views):raise ValueError('Vision attachment process/views do not agree')
            value=raster(image['image'],16*1024*1024);value['pixels']=value['pixels'].hex();images[key]=dict(process=process,views=sorted(views),image=value)
        packet=dict(row,process=process,result=active_payload(completion),images=images)
        if json_size(packet)>self.payload_limit:raise ValueError('Vision packet exceeds payload_limit')
        return deepcopy(packet)

    def enqueue(self,number,work_id,value):
        """Explicit host feed; validates data and never discovers a producer."""
        row=part(dict(work_id=work_id,result=value))
        if number not in self.queues:return 2
        queue=self.queues[number]
        if row['work_id'] in self.work_ids(number):return 5
        total=sum(len(v['parts'])+len(v['arrivals']) for v in self.queues.values())+len(self.allocations)
        if len(queue['parts'])>=queue['capacity'] or total>=4096:return 4
        queue['parts'].append(row);return 0

    @staticmethod
    def promote(queue):
        while queue['arrivals'] and queue['arrivals'][0]['at_ms']<=queue['elapsed_ms'] and len(queue['parts'])<queue['capacity']:
            queue['parts'].append(queue['arrivals'].pop(0)['part'])

    def get(self,state,args,line):
        number,vr,timeout,status=args;owner=self.owner
        if owner.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Vision request sequence exhausted',line)
        queue=self.queues.get(number);code=2 if queue is None or not 1<=vr<=owner.count or timeout>86400000 else 3 if number in self.pending or self.register_busy(vr) or self.register_allocated(vr) else 0
        if not code and timeout>=0 and queue['elapsed_ms']+timeout>MAX_SEQUENCE:raise rt().KarelRuntimeError('Tracking queue clock exhausted',line)
        row=owner.begin(state,'V_GET_QUEUE',number)
        if code:row['status']=code;status.set(code,line);return
        self.pending[number]=dict(state=state,register=vr);deadline=None if timeout<0 else queue['elapsed_ms']+timeout
        try:
            while True:
                self.promote(queue)
                if queue['parts']:
                    selected=queue['parts'][0];value=deepcopy(selected['result'])
                    owner.registers[vr]=value;self.invalidate(vr)
                    self.allocations[vr]=dict(queue=number,work_id=selected['work_id'])
                    self.triggers[vr]=dict(queue=number,work_id=selected['work_id'],encoder=value['encoder'])
                    queue['parts'].pop(0);status.set(0,line);row['status']=0;return
                if deadline is not None and queue['elapsed_ms']>=deadline:row['status']=117249;status.set(117249,line);return
                step=10 if deadline is None else min(10,deadline-queue['elapsed_ms'])
                if queue['arrivals']:step=min(step,queue['arrivals'][0]['at_ms']-queue['elapsed_ms'])
                if queue['elapsed_ms']+step>MAX_SEQUENCE:raise rt().KarelRuntimeError('Tracking queue clock exhausted',line)
                yield from rt().delay_execution(state,step,line);queue['elapsed_ms']+=step;yield from rt().checkpoint(state,line)
        except BaseException as error:
            row['status']=8 if isinstance(error,(GeneratorExit,rt().KarelStop,rt().KarelAbort)) else 9;raise
        finally:self.pending.pop(number,None)

    def to_config(self):
        if self.pending:raise ValueError('Finish or stop pending tracking queue reads before saving context')
        queues={str(k):dict(capacity=v['capacity'],parts=[encode_part(p) for p in v['parts']],arrivals=[dict(at_ms=p['at_ms'],part=encode_part(p['part'])) for p in v['arrivals']],elapsed_ms=v['elapsed_ms']) for k,v in sorted(self.queues.items())}
        answer=dict(queues=queues,allocations={str(k):v.copy() for k,v in sorted(self.allocations.items())},triggers={str(k):v.copy() for k,v in sorted(self.triggers.items())},processes=deepcopy(self.processes),ids=deepcopy(self.ids),sensors=deepcopy(self.sensors),latest=self.latest,outbox=deepcopy(self.outbox),outbox_limit=self.outbox_limit,payload_limit=self.payload_limit,include_images=self.include_images)
        if self.vt is not None:answer['vt']=self.vt.to_config()
        return answer


def get_found(owner,state,args,line):
    target,model,encoder,offset,points,measures,status=args;process=owner.processes.get(target.upper());code=0;pairs=[]
    if owner.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Vision request sequence exhausted',line)
    active=None if process is None else process['active'];cursor=process['cursor'] if process is not None else 0
    if process is None:code=2
    elif active is None:code=1
    elif active['status']:code=active['status']
    elif cursor>=len(active['results']):code=117151
    else:
        value=active['results'][cursor];positions=points.raw();measurements=measures.raw()
        pairs=[(model,value['model']),(encoder,value['encoder']),(offset,value['offset'])]
        pairs.extend((rt().index_reference(positions,int(view),line),row['position']) for view,row in value['views'].items())
        pairs.extend((rt().index_reference(measurements,index+1,line),v) for index,v in enumerate(value['measurements']) if v is not None)
    staged=[(ref,rt().checked(ref.spec,value,line)) for ref,value in pairs]
    row=owner.begin(state,'VT_GET_FOUND',target);row['status']=code
    for ref,value in staged:ref.set(value,line)
    if not code:process['cursor']+=1
    status.set(code,line)


def invoke_tracking(owner,state,operation,args,line):
    if operation=='VT_GET_FOUND':return get_found(owner,state,args,line)
    bank=owner.tracking
    if bank is None:raise rt().KarelRuntimeError('Operation requires explicit vision tracking configuration',line)
    if operation=='V_GET_QUEUE':return bank.get(state,args,line)
    if owner.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Vision request sequence exhausted',line)
    target=args[0];code=0;commit=None
    if operation in ('VT_GET_AREID','VT_GET_LINID','VT_GET_TRYID'):
        kind={'VT_GET_AREID':'areas','VT_GET_LINID':'lines','VT_GET_TRYID':'trays'}[operation];value=bank.ids[kind].get(target.upper())
        row=owner.begin(state,operation,target)
        if value is None:row['status']=2;raise rt().KarelRuntimeError('Tracking name is not configured in '+kind,line)
        return value
    status=args[-1]
    if operation in ('V_START_VTRK','V_STOP_VTRK'):
        process=bank.processes.get(target.upper())
        if process is None:code=2
        else:
            def commit():process['running']=operation=='V_START_VTRK'
    elif operation=='V_INIT_QUEUE':
        queue=bank.queues.get(target)
        if queue is None:code=2
        elif target in bank.pending:code=3
        else:
            def commit():
                queue['parts'].clear()
                for vr in [k for k,v in bank.allocations.items() if v['queue']==target]:bank.invalidate(vr)
    elif operation=='V_RALC_QUEUE':
        queue=bank.queues.get(target);vr=args[1];receipt=bank.allocations.get(vr)
        code,value=owner.register(vr)
        if queue is None:code=2
        elif bank.register_busy(vr):code=3
        elif not code and receipt is None:code=6
        elif not code:
            work=receipt['work_id']
            duplicates={v['work_id'] for v in queue['parts']}|{v['part']['work_id'] for v in queue['arrivals']}|{v['work_id'] for k,v in bank.allocations.items() if k!=vr and v['queue']==target}
            if len(queue['parts'])>=queue['capacity']:code=4
            elif work in duplicates:code=5
            elif bank.triggers[vr]['encoder']!=value['encoder']:code=6
            else:
                restored=dict(work_id=work,result=deepcopy(value))
                def commit():queue['parts'].append(restored);bank.invalidate(vr)
    elif operation in ('V_ACQ_VAMAP','V_CLR_VAMAP'):
        sensor=bank.sensors.get(target.upper())
        if sensor is None:code=2
        elif operation=='V_CLR_VAMAP':
            def commit():sensor['map']=None
        elif args[1] or any(v!=0 for v in rt().vector_components(args[2],line)):code=2
        elif not sensor['responses']:raise rt().KarelRuntimeError('V_ACQ_VAMAP requires an explicit area-map response',line)
        else:
            response=deepcopy(sensor['responses'][0]);code=response['status']
            def commit():
                sensor['responses'].pop(0)
                if not code:sensor['map']=response['map']
    else:
        priority,vr=args[1:3]
        if not 0<=priority<=3 or vr!=0:code=2
        elif bank.latest is None:code=1
        elif len(bank.outbox)>=bank.outbox_limit:code=4
        else:
            active=active_payload(owner.processes[bank.latest]['active']);images={}
            if bank.include_images and owner.io is not None:
                selected={str(k):v for k,v in owner.io.images.items() if v['process']==bank.latest}
                if sum(len(v['image']['pixels'])*2 for v in selected.values())>bank.payload_limit:code=4
                else:
                    for key,row in selected.items():
                        copied=deepcopy(row);copied['image']['pixels']=copied['image']['pixels'].hex();images[key]=copied
            packet=dict(sequence=owner.sequence+1,program=rt().task_root(state).program_name,description=target,priority=priority,process=bank.latest,result=active,images=images)
            size=json_size(packet)
            if size>bank.payload_limit or sum(json_size(v) for v in bank.outbox)+size>16*1024*1024:code=4
            if not code:
                def commit():bank.outbox.append(packet)
    row=owner.begin(state,operation,target);row['status']=code
    if commit is not None:commit()
    status.set(code,line)
