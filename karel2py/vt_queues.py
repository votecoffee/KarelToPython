"""Portable VT line queues and checked nullable-source arguments; no motion I/O."""
from copy import deepcopy
import re

from .vision import integer,real,pose,result,encode_result,MAX_SEQUENCE


def rt():
    from . import runtime
    return runtime


def key_number(key):
    if type(key) is not str or re.fullmatch('[1-9][0-9]*',key) is None:raise ValueError('VT keys require canonical positive numbers')
    return integer(int(key),1,32767)


def queue_schema(spec):
    if len(spec)!=3 or spec[0]!='PATH' or any(v is None or v[0]!='STRUCTURE' for v in spec[1:]):return False
    node,header=dict(spec[1][2]),dict(spec[2][2]);coords={k:('REAL',) for k in ('X','Y','Z','W','P','R')}
    return (header=={'AREA_ID':('INTEGER',),'NUM_PARTS':('INTEGER',)} and set(node)=={'WORK_ID','MODEL_ID','TRAY_ID','ENC_COUNT','OFFSET','FOUND_POS','MEAS_VALUE'}
        and all(node[k]==('INTEGER',) for k in ('WORK_ID','MODEL_ID','TRAY_ID','ENC_COUNT'))
        and all(node[k][0]=='STRUCTURE' and dict(node[k][2])==coords for k in ('OFFSET','FOUND_POS'))
        and node['MEAS_VALUE'][0]=='ARRAY' and rt().array_dimensions(node['MEAS_VALUE'])==(10,) and rt().array_leaf_spec(node['MEAS_VALUE'])==('REAL',))


def missing(value):
    if value is rt().UNINITIALIZED:return True
    if type(value) is rt().Structure:return all(missing(v) for v in value.values.values())
    if type(value) is rt().Array:return all(missing(v) for v in value.values)
    return False


def selector(value):
    return None if value.value is rt().UNINITIALIZED else integer(value.value)


def source_result(model,encoder,offset,positions,measurements,line):
    views={}
    for index,value in enumerate([] if positions.value is rt().UNINITIALIZED else positions.value.values,1):
        if missing(value):continue
        point=rt().positional_value(('XYZWPR',),value,line);views[str(index)]=dict(position=point,model=model)
    values=[None if v is rt().UNINITIALIZED else rt().real(v,line) for v in ([rt().UNINITIALIZED]*10 if measurements.value is rt().UNINITIALIZED else measurements.value.values)]
    return result(dict(offset=offset,views=views,model=model,encoder=encoder,measurements=values))


def encoded(part):
    row=dict(part,result=encode_result(part['result']),ready={str(k):v for k,v in part['ready'].items()},passed=list(part['passed']))
    if 'tray_origin' in row:row['tray_origin']=list(row['tray_origin'])
    return row


def detection(value):
    return (value['encoder'],value['model'],*[value['offset'].values[k] for k in ('X','Y','Z','W','P','R')])


class VTQueues:
    def __init__(self,config,parent):
        if type(config) is not dict or set(config)-{'lines','areas','allocations','trays'}:raise ValueError('Unknown VT queue configuration fields')
        self.parent=parent;self.owner=parent.owner;self.lines={};self.areas={};self.allocations={};self.pending={};self.trays={}
        lines=config.get('lines',{});areas=config.get('areas',{});allocations=config.get('allocations',{})
        if any(type(v) is not dict for v in (lines,areas,allocations)) or len(lines)>32 or len(areas)>256:raise ValueError('VT requires bounded explicit line/area mappings')
        trays=config.get('trays',{})
        if type(trays) is not dict or len(trays)>256:raise ValueError('VT tray patterns require a bounded mapping')
        cell_count=0
        for key,row in trays.items():
            number=key_number(key)
            if number not in parent.ids['trays'].values():raise ValueError('VT tray pattern ID is not configured in the name bank')
            if type(row) is not dict or 'cells' not in row or set(row)-{'cells','sequenced'}:raise ValueError('VT tray pattern requires explicit cells')
            cells=row['cells'];sequenced=row.get('sequenced',True)
            if type(cells) is not list or not 1<=len(cells)<=256 or type(sequenced) is not bool:raise ValueError('VT tray pattern requires 1..256 cells and BOOLEAN sequenced')
            prepared=[];cell_count+=len(cells)
            if cell_count>4096:raise ValueError('VT tray patterns exceed 4096 supplied cells')
            for cell in cells:
                if type(cell) is not dict or 'offset' not in cell or set(cell)-{'offset','model'}:raise ValueError('VT tray cell requires a complete offset and optional model')
                value=dict(offset=pose(cell['offset']))
                if 'model' in cell:value['model']=integer(cell['model'])
                prepared.append(value)
            self.trays[number]=dict(cells=prepared,sequenced=sequenced)
        for key,row in lines.items():
            number=key_number(key)
            if type(row) is not dict or not {'areas','capacity'}<=set(row) or set(row)-{'areas','capacity','flags','direction','speed','sequence','weights','parts','tray_edit'}:raise ValueError('VT line requires ordered areas and capacity')
            order=row['areas']
            if type(order) is not list or not 1<=len(order)<=32 or any(type(v) is not int or not 1<=v<=32767 for v in order) or len(set(order))!=len(order):raise ValueError('VT line requires distinct ordered area IDs')
            direction=row.get('direction',1)
            if type(direction) is not int or direction not in (-1,1):raise ValueError('VT line direction requires -1 or 1')
            speed=None if row.get('speed') is None else real(row['speed'])
            if speed is not None and speed<0:raise ValueError('VT speed must be nonnegative')
            tray_edit=row.get('tray_edit',False)
            if type(tray_edit) is not bool:raise ValueError('tray_edit requires BOOLEAN')
            value=dict(areas=order.copy(),capacity=integer(row['capacity'],1,4096),flags=integer(row.get('flags',0),0,3),direction=direction,speed=speed,sequence=integer(row.get('sequence',0)),weights={},parts=[],tray_edit=tray_edit)
            weights=row.get('weights',{'0':dict(pick=[1]*len(order),**{'pass':0},cursor=0)})
            if type(weights) is not dict or len(weights)>256:raise ValueError('VT weight profiles require a bounded mapping')
            for model,profile in weights.items():
                if type(model) is not str or re.fullmatch('0|[1-9][0-9]*',model) is None:raise ValueError('VT weight model requires a canonical nonnegative ID')
                integer(int(model));value['weights'][model]=self.weights(profile,len(order))
            if '0' not in value['weights']:raise ValueError('VT weights require default model 0')
            self.lines[number]=value
        for key,row in areas.items():
            number=key_number(key)
            if type(row) is not dict or 'line' not in row or set(row)-{'line','flags','elapsed_ms','travel_ms','span','frame'}:raise ValueError('VT area requires a configured line')
            line=integer(row['line'],1,32767)
            if line not in self.lines or number not in self.lines[line]['areas']:raise ValueError('VT area and line order do not agree')
            span=None if row.get('span') is None else real(row['span'])
            if span is not None and span<=0:raise ValueError('VT area span must be positive')
            self.areas[number]=dict(line=line,flags=integer(row.get('flags',0),0,31),elapsed_ms=integer(row.get('elapsed_ms',0)),travel_ms=integer(row.get('travel_ms',0),0,86400000),span=span,frame=integer(row.get('frame',0),0,32767))
        if any(any(area not in self.areas or self.areas[area]['line']!=number for area in line['areas']) for number,line in self.lines.items()):raise ValueError('Every ordered VT area must exist on its line')
        for number,line in self.lines.items():
            rows=lines[str(number)].get('parts',[])
            if type(rows) is not list:raise ValueError('VT parts require a list')
            line['parts']=[self.part(row,number) for row in rows]
        for key,row in allocations.items():
            vr=key_number(key)
            if vr>self.owner.count or vr not in self.owner.registers or vr in parent.allocations or type(row) is not dict or set(row)!={'area','part'}:raise ValueError('VT allocation requires a distinct populated vision register')
            area=integer(row['area'],1,32767)
            if area not in self.areas:raise ValueError('VT allocation area is not configured')
            part=self.part(row['part'],self.areas[area]['line'])
            if part['result']['encoder']!=self.owner.registers[vr]['encoder']:raise ValueError('VT allocation encoder does not match its register')
            self.allocations[vr]=dict(area=area,part=part)
        total=0
        for number,line in self.lines.items():
            rows=self.held(number);total+=len(rows)
            if len(rows)>line['capacity'] or total>4096:raise ValueError('VT part capacity exceeded')
            if len({v['uid'] for v in rows})!=len(rows):raise ValueError('VT internal queue indexes must be distinct')
            ids={};instances={}
            for part in rows:
                instance=part.get('tray_instance')
                group=('part',part['uid']) if instance is None else ('tray',instance)
                if part['work_id']:
                    if part['work_id'] in ids and ids[part['work_id']]!=group:raise ValueError('Nonzero caller work IDs must be distinct outside a tray instance')
                    ids[part['work_id']]=group
                if instance is not None:
                    identity=(part['tray'],part['work_id'],part['tray_origin'])
                    if instance in instances and instances[instance]!=identity:raise ValueError('VT tray instance ownership is inconsistent')
                    instances[instance]=identity

    @staticmethod
    def weights(row,count):
        if type(row) is not dict or not {'pick','pass'}<=set(row) or set(row)-{'pick','pass','cursor'} or type(row['pick']) is not list or len(row['pick'])!=count:raise ValueError('VT weights require pick rates for each ordered area and pass rate')
        pick=[integer(v,0,32767) for v in row['pick']];bypass=integer(row['pass'],0,32767);total=sum(pick)+bypass
        if not total:raise ValueError('VT rates cannot all be zero')
        return dict(pick=pick,**{'pass':bypass},cursor=integer(row.get('cursor',0),0,total-1))

    def part(self,row,number):
        required={'uid','work_id','tray','result','ready','passed','target'}
        cell_fields={'tray_instance','tray_cell','tray_origin'}
        if type(row) is not dict or set(row) not in (required,required|cell_fields):raise ValueError('Malformed VT part record')
        line=self.lines[number];uid=integer(row['uid'],1,line['sequence']);work=integer(row['work_id']);tray=integer(row['tray'],0,32767)
        if tray and tray not in self.parent.ids['trays'].values():raise ValueError('VT tray ID is not configured')
        if type(row['ready']) is not dict:raise ValueError('VT part requires ready times for every area')
        ready={key_number(k):integer(v) for k,v in row['ready'].items()}
        passed=row['passed'];target=integer(row['target'],1,32767)
        if set(ready)!=set(line['areas']) or type(passed) is not list or any(type(v) is not int or v not in line['areas'] for v in passed) or len(set(passed))!=len(passed) or target not in line['areas']:raise ValueError('VT part area metadata is inconsistent')
        value=dict(uid=uid,work_id=work,tray=tray,result=result(row['result']),ready=ready,passed=passed.copy(),target=target)
        if cell_fields<=set(row):
            if tray not in self.trays:raise ValueError('VT cell requires its configured tray pattern')
            instance=integer(row['tray_instance'],1,line['sequence']);cell=integer(row['tray_cell'],1,len(self.trays[tray]['cells']))
            if instance+cell-1!=uid or instance+len(self.trays[tray]['cells'])-1>line['sequence']:raise ValueError('VT cell index does not belong to its tray instance')
            origin=row['tray_origin']
            if type(origin) not in (tuple,list) or len(origin)!=8:raise ValueError('VT tray origin requires encoder, model and six pose coordinates')
            origin=(integer(origin[0],-2147483648),integer(origin[1]),*(real(v) for v in origin[2:]))
            value.update(tray_instance=instance,tray_cell=cell,tray_origin=origin)
        return value

    def held(self,number):return self.lines[number]['parts']+[v['part'] for v in self.allocations.values() if self.areas[v['area']]['line']==number]
    def register_busy(self,vr):return any(v['register']==vr for v in self.pending.values())
    def line_busy(self,number):return any(self.areas[area]['line']==number for area in self.pending)

    def eligible(self,area,consecutive,model,work):
        settings=self.areas[area];line=self.lines[settings['line']]
        if settings['flags']&1:return []
        values=[v for v in line['parts'] if area not in v['passed'] and (model is None or v['result']['model']==model) and (work is None or v['work_id']==work) and (not line['flags']&1 or consecutive>1 or v['target']==area)]
        return self.ordered(values,line,settings)

    def ordered(self,values,line,area=None):
        if area is not None and area['flags']&2:values=sorted(values,key=lambda v:((-1 if area['flags']&4 else 1)*v['result']['offset'].values['Y'],v['uid']))
        else:values=sorted(values,key=lambda v:(line['direction']*v['result']['encoder'],v['uid']))
        answer=[];seen=set();groups={}
        for part in values:
            if 'tray_instance' in part and self.trays[part['tray']]['sequenced']:groups.setdefault(part['tray_instance'],[]).append(part)
        for part in values:
            instance=part.get('tray_instance')
            if instance is None or not self.trays[part['tray']]['sequenced']:answer.append(part);continue
            if instance in seen:continue
            seen.add(instance)
            answer.extend(sorted(groups[instance],key=lambda v:v['tray_cell']))
        return answer

    def expand_tray(self,tray,value,line):
        """Apply supplied local cell transforms only to complete existing poses."""
        pattern=self.trays.get(tray)
        if pattern is None:return [deepcopy(value)]
        values=[]
        for cell in pattern['cells']:
            updated=deepcopy(value)
            with rt()._numeric_scope('pythonic'):
                updated['offset']=rt().frame_transform(value['offset'],cell['offset'],line)
                for key,view in updated['views'].items():view['position']=rt().frame_transform(value['views'][key]['position'],cell['offset'],line)
            if 'model' in cell:
                updated['model']=cell['model']
                for view in updated['views'].values():view['model']=cell['model']
            values.append(result(updated))
        return values

    def next_target(self,line,part,after=None):
        order=line['areas'];start=0 if after is None else order.index(after)+1
        return next((v for v in order[start:] if v not in part['passed'] and not self.areas[v]['flags']&1),None)

    def route(self,line,model):
        order=line['areas'];available=[v for v in order if not self.areas[v]['flags']&1]
        if not available:return None,None,None
        if not line['flags']&1:return available[0],None,None
        profile=line['weights'].get(str(model),line['weights']['0']);indices=list(range(len(order)))
        if line['flags']&2:indices.reverse()
        slots=[(order[i],profile['pick'][i]) for i in indices if order[i] in available]+[(None,profile['pass'])]
        total=sum(weight for _,weight in slots)
        if not total:return None,None,None
        position=profile['cursor']%total;next_cursor=(position+1)%total
        for area,weight in slots:
            if position<weight:return area,profile,next_cursor
            position-=weight

    def get(self,state,args,line_no):
        area,vr,timeout,consecutive,model_arg,work_arg,status=args;owner=self.owner
        if owner.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Vision request sequence exhausted',line_no)
        try:model,work=selector(model_arg),selector(work_arg)
        except ValueError:model=work=None;invalid=True
        else:invalid=False
        settings=self.areas.get(area)
        code=2 if invalid or settings is None or not 1<=vr<=owner.count or timeout>86400000 or consecutive<1 else 3 if area in self.pending or self.parent.register_busy(vr) or vr in self.allocations or vr in self.parent.allocations else 0
        if not code and timeout>=0 and settings['elapsed_ms']+timeout>MAX_SEQUENCE:raise rt().KarelRuntimeError('VT area clock exhausted',line_no)
        row=owner.begin(state,'VT_GET_QUEUE',area)
        if code:row['status']=code;status.set(code,line_no);return
        self.pending[area]=dict(register=vr,state=state);deadline=None if timeout<0 else settings['elapsed_ms']+timeout
        try:
            while True:
                candidates=self.eligible(area,consecutive,model,work);ready=[v for v in candidates if v['ready'][area]<=settings['elapsed_ms']]
                if ready:
                    part=ready[0];value=deepcopy(part['result']);value['frame']=settings['frame']
                    owner.registers[vr]=value;self.parent.invalidate(vr);self.lines[settings['line']]['parts'].remove(part);self.allocations[vr]=dict(area=area,part=part)
                    status.set(0,line_no);return
                if deadline is not None and settings['elapsed_ms']>=deadline:row['status']=117249;status.set(117249,line_no);return
                step=10 if deadline is None else min(10,deadline-settings['elapsed_ms'])
                if candidates:step=min(step,min(v['ready'][area]-settings['elapsed_ms'] for v in candidates))
                if settings['elapsed_ms']+step>MAX_SEQUENCE:raise rt().KarelRuntimeError('VT area clock exhausted',line_no)
                yield from rt().delay_execution(state,step,line_no);settings['elapsed_ms']+=step;yield from rt().checkpoint(state,line_no)
        except BaseException as error:row['status']=8 if isinstance(error,(GeneratorExit,rt().KarelStop,rt().KarelAbort)) else 9;raise
        finally:self.pending.pop(area,None)

    def invoke(self,state,operation,args,line=None):
        if operation=='VT_GET_QUEUE':return self.get(state,args,line)
        if self.owner.sequence>=MAX_SEQUENCE:raise rt().KarelRuntimeError('Vision request sequence exhausted',line)
        target=args[0];status=args[-1];code=0;pairs=[];commit=None
        if operation in ('VT_PUT_QUEUE','VT_PUT_QUE2'):
            settings=self.lines.get(target);work,tray,encoder,model,offset,positions,measures=args[1:8]
            if settings is None or work<0 or model<0 or tray<0 or tray and tray not in self.parent.ids['trays'].values() or operation=='VT_PUT_QUE2' and tray:code=2
            else:
                try:value=source_result(model,encoder,offset,positions,measures,line)
                except (ValueError,rt().KarelRuntimeError):code=2
                if not code:
                    fingerprint=detection(value)
                    duplicate=any(work and v['work_id']==work or detection(v['result'])==fingerprint or v.get('tray_origin')==fingerprint for v in self.held(target))
                    if operation=='VT_PUT_QUE2':pairs=[(args[8],bool(duplicate))]
                    if not duplicate:
                        count=len(self.trays[tray]['cells']) if tray in self.trays else 1
                        if len(self.held(target))+count>settings['capacity'] or sum(len(self.held(k)) for k in self.lines)+count>4096:code=4
                        elif settings['sequence']+count>MAX_SEQUENCE:raise rt().KarelRuntimeError('VT internal index exhausted',line)
                        else:
                            if tray in self.trays:
                                for _ in range(count):state.tick(line)
                            try:values=self.expand_tray(tray,value,line)
                            except (ValueError,rt().KarelRuntimeError):code=2
                            ready={k:self.areas[k]['elapsed_ms']+self.areas[k]['travel_ms'] for k in settings['areas']}
                            if any(v>MAX_SEQUENCE for v in ready.values()):raise rt().KarelRuntimeError('VT arrival clock exhausted',line)
                            if not code:
                                route_state=dict(settings,weights=deepcopy(settings['weights']));parts=[];instance=settings['sequence']+1
                                for index,value in enumerate(values,1):
                                    destination,profile,cursor=self.route(route_state,value['model'])
                                    if profile is not None:profile['cursor']=cursor
                                    part=dict(uid=instance+index-1,work_id=work,tray=tray,result=value,ready=ready.copy(),passed=[],target=destination)
                                    if tray in self.trays:part.update(tray_instance=instance,tray_cell=index,tray_origin=fingerprint)
                                    if destination is not None:parts.append(part)
                                def commit():
                                    settings['sequence']+=count;settings['weights']=route_state['weights'];settings['parts'].extend(parts)
        elif operation in ('VT_SET_FLAG','VT_SET_LDBAL'):
            settings=self.lines.get(target)
            if settings is None:code=2
            elif self.line_busy(target):code=3
            elif operation=='VT_SET_LDBAL':
                model,pick,bypass=args[1:4];values=pick.values
                try:
                    if model<0 or any(v!=0 for v in values[len(settings['areas']):]):raise ValueError('Unused VT weight slots must be zero')
                    profile=self.weights(dict(pick=values[:len(settings['areas'])],**{'pass':bypass}),len(settings['areas']))
                except ValueError:code=2
                else:
                    if str(model) not in settings['weights'] and len(settings['weights'])>=256:code=4
                    else:
                        def commit():settings['weights'][str(model)]=profile
            else:
                enable,disable,area_enable,area_disable=args[1:5];en,dis=area_enable.values,area_disable.values;count=len(settings['areas'])
                if not 0<=enable<=3 or not 0<=disable<=3 or enable and disable or any(not 0<=a<=31 or not 0<=b<=31 or a and b for a,b in zip(en,dis)) or any(en[count:]) or any(dis[count:]):code=2
                else:
                    flags=(settings['flags']|enable)&~disable;updates={area:(self.areas[area]['flags']|en[i])&~dis[i] for i,area in enumerate(settings['areas'])}
                    def commit():
                        settings['flags']=flags
                        for area,value in updates.items():self.areas[area]['flags']=value
                        for part in list(settings['parts']):
                            if self.areas[part['target']]['flags']&1:
                                destination=self.next_target(settings,part)
                                if destination is None:settings['parts'].remove(part)
                                else:part['target']=destination
        else:
            area=self.areas.get(target);settings=None if area is None else self.lines[area['line']]
            if area is None:code=2
            elif operation=='VT_ACK_QUEUE':
                vr,ack=args[1:3];receipt=self.allocations.get(vr)
                if not 1<=vr<=self.owner.count or ack not in (1,2,3):code=2
                elif receipt is None or receipt['area']!=target:code=6
                elif self.parent.register_busy(vr):code=3
                else:
                    part=deepcopy(receipt['part']);part['result']=deepcopy(self.owner.registers[vr]);part['passed']=sorted(set(part['passed'])|set(settings['areas'][:settings['areas'].index(target)+1]));destination=self.next_target(settings,part,after=target) if ack==2 else None
                    if destination is not None:part['target']=destination
                    def commit():
                        self.allocations.pop(vr)
                        if destination is not None:settings['parts'].append(part)
            elif operation=='VT_CLR_QUEUE':
                if target in self.pending or any(self.parent.register_busy(vr) for vr,v in self.allocations.items() if v['area']==target):code=3
                else:
                    def commit():
                        for part in list(settings['parts']):
                            if target not in part['passed']:part['passed'].append(target)
                            if part['target']==target:
                                destination=self.next_target(settings,part)
                                if destination is None:settings['parts'].remove(part)
                                else:part['target']=destination
                        for vr in [k for k,v in self.allocations.items() if v['area']==target]:self.allocations.pop(vr)
            elif operation in ('VT_GET_TIME','VT_GET_PFRT'):
                try:
                    if operation=='VT_GET_TIME':consecutive=args[1];model=selector(args[2]);work=selector(args[3]);count=1
                    else:consecutive,count=args[1:3];model=selector(args[3]);work=None
                    if consecutive<1 or count<1 or operation=='VT_GET_PFRT' and consecutive>count:raise ValueError('Invalid VT consecutive selection')
                except ValueError:code=2
                else:
                    candidates=self.eligible(target,consecutive,model,work)
                    if operation=='VT_GET_TIME':
                        if not candidates:code=1
                        else:
                            available=[v for v in candidates if v['ready'][target]<=area['elapsed_ms']];selected=available[0] if available else min(candidates,key=lambda v:v['ready'][target]);difference=selected['ready'][target]-area['elapsed_ms'];pairs=[(args[4],difference if difference>0 else -max(1,-difference))]
                    elif settings['speed'] is None or area['span'] is None:code=1
                    else:
                        try:value=rt().integer(round(max(0,(len(candidates)+count-consecutive)//count)*settings['speed']*60/area['span']),line)
                        except (ArithmeticError,ValueError,rt().KarelRuntimeError):code=2
                        else:pairs=[(args[4],value)]
            elif target in self.pending:code=3
            elif settings['flags']&1:code=7
            elif operation=='VT_READ_PQ':
                path=args[1].raw();rows=self.ordered([v for v in settings['parts'] if target not in v['passed']],settings);rows=rows[:len(path.nodes)]
                if not settings['tray_edit'] and any(v['tray'] for v in rows):code=7
                else:
                    prepared_nodes=[]
                    for part in rows:
                        state.tick(line);node=rt().Structure(path.node_spec);value=part['result'];node.values.update(WORK_ID=part['uid'],MODEL_ID=value['model'],ENC_COUNT=value['encoder'])
                        if part['tray']:node.values['TRAY_ID']=part['tray']
                        for field,point in [('OFFSET',value['offset']),('FOUND_POS',value['views'].get('1',{}).get('position'))]:
                            if point is not None:
                                for k in ('X','Y','Z','W','P','R'):node.values[field].values[k]=point.values[k]
                        for i,v in enumerate(value['measurements']):
                            if v is not None:node.values['MEAS_VALUE'].set(i+1,v,line)
                        rt().variable_value(node.spec,node,line);prepared_nodes.append(node)
                    def commit():
                        path.data.values.update(AREA_ID=target,NUM_PARTS=len(prepared_nodes))
                        for current,new in zip(path.nodes,prepared_nodes):rt().replace_value(current,new)
            else:
                uid=args[1];part=next((v for v in settings['parts'] if v['uid']==uid and target not in v['passed']),None)
                if part is None:code=3 if any(v['part']['uid']==uid and self.areas[v['area']]['line']==area['line'] for v in self.allocations.values()) else 1
                elif part['tray'] and not settings['tray_edit']:code=7
                elif operation=='VT_DELETE_PQ':
                    def commit():
                        part['passed'].append(target)
                        if part['target']==target:
                            destination=self.next_target(settings,part)
                            if destination is None:settings['parts'].remove(part)
                            else:part['target']=destination
                else:
                    value=deepcopy(part['result'])
                    try:
                        if not missing(args[2].value):value['model']=integer(args[2].value)
                        if not missing(args[3].value):value['encoder']=integer(args[3].value,-2147483648)
                        for index,field in ((4,'offset'),(5,'found')):
                            if missing(args[index].value):continue
                            point=rt().positional_value(('XYZWPR',),args[index].value,line)
                            if field=='offset':value['offset']=point
                            else:value['views']['1']=dict(position=point,model=value['model'])
                        values=list(value['measurements'])+[None]*(10-len(value['measurements']))
                        for i,v in enumerate([] if args[6].value is rt().UNINITIALIZED else args[6].value.values):
                            if v is not rt().UNINITIALIZED:values[i]=rt().real(v,line)
                        value['measurements']=values
                        value=result(value)
                    except (ValueError,rt().KarelRuntimeError):code=2
                    else:
                        def commit():part['result']=value
        staged=[(ref,rt().checked(ref.spec,value,line)) for ref,value in pairs] if not code else []
        row=self.owner.begin(state,operation,target);row['status']=code
        if commit is not None and not code:commit()
        for ref,value in staged:ref.set(value,line)
        status.set(code,line)

    def to_config(self):
        if self.pending:raise ValueError('Finish or stop pending VT queue reads before saving context')
        lines={str(k):dict(v,parts=[encoded(p) for p in v['parts']],weights=deepcopy(v['weights']),areas=v['areas'].copy()) for k,v in self.lines.items()}
        value=dict(lines=lines,areas={str(k):v.copy() for k,v in self.areas.items()},allocations={str(k):dict(area=v['area'],part=encoded(v['part'])) for k,v in self.allocations.items()})
        if self.trays:
            from .storage import typed_value
            value['trays']={str(k):dict(sequenced=v['sequenced'],cells=[dict(cell,offset=typed_value(cell['offset'])) for cell in v['cells']]) for k,v in self.trays.items()}
        return value
