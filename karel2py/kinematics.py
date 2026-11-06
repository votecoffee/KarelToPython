"""Explicit serial-chain models with standard DH forward and numerical inverse math.

Lengths use millimetres and joint angles use degrees. Model parameters are caller
data; this module contains no FANUC robot dimensions or calibration defaults.
"""
from copy import deepcopy
import math


def rt():
    from . import runtime
    return runtime


IDENTITY=((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.))


def multiply(a,b): return tuple(tuple(sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)) for i in range(4))


def inverse(a):
    r=tuple(tuple(a[j][i] for j in range(3)) for i in range(3))
    return tuple(tuple(r[i][j] if j<3 else -sum(r[i][k]*a[k][3] for k in range(3)) for j in range(4)) for i in range(3))+((0.,0.,0.,1.),)


def matrix(pose):
    runtime=rt()
    with runtime._numeric_scope('pythonic'):
        rotation,location,_=runtime._frame_parts(pose)
    return tuple(tuple(rotation[i][j] if j<3 else location[i] for j in range(4)) for i in range(3))+((0.,0.,0.,1.),)


def config_zero():
    result=rt().Structure(('CONFIG',))
    result.values.update({name:0 if spec==('INTEGER',) else False for name,spec in result.types.items()})
    return result


def pose(value=IDENTITY,config=None,*,extended=()):
    runtime=rt()
    with runtime._numeric_scope('pythonic'):
        result=runtime._frame_result(tuple(tuple(value[i][j] for j in range(3)) for i in range(3)),tuple(value[i][3] for i in range(3)),config or config_zero(),None,result_type=('XYZWPREXT',) if extended else ('POSITION',))
        if extended:
            for i,name in enumerate(('EXT1','EXT2','EXT3')): result.values[name]=float(extended[i]) if i<len(extended) else 0.
        return result


def rotation_error(a,b):
    """World-axis rotation vector from a to b, including stable half-turns."""
    r=[[sum(b[i][k]*a[j][k] for k in range(3)) for j in range(3)] for i in range(3)]
    angle=math.acos(max(-1.,min(1.,(sum(r[i][i] for i in range(3))-1.)/2)))
    skew=(r[2][1]-r[1][2],r[0][2]-r[2][0],r[1][0]-r[0][1])
    if angle<1e-8: return tuple(v/2 for v in skew)
    if math.pi-angle<1e-5:
        axis=[math.sqrt(max(0.,(r[i][i]+1.)/2)) for i in range(3)]
        largest=max(range(3),key=lambda i:axis[i])
        if axis[largest]>1e-8:
            for i in range(3):
                if i!=largest: axis[i]=math.copysign(axis[i],r[largest][i]+r[i][largest])
        return tuple(v*angle for v in axis)
    return tuple(v*angle/(2*math.sin(angle)) for v in skew)


def error(current,target,weight):
    return tuple(target[i][3]-current[i][3] for i in range(3))+tuple(weight*v for v in rotation_error(current,target))


def linear_solve(a,b):
    n=len(b); work=[list(row)+[value] for row,value in zip(a,b)]
    for column in range(n):
        pivot=max(range(column,n),key=lambda i:abs(work[i][column]))
        if abs(work[pivot][column])<1e-15: return None
        work[column],work[pivot]=work[pivot],work[column]
        scale=work[column][column]; work[column]=[x/scale for x in work[column]]
        for row in range(n):
            if row==column: continue
            factor=work[row][column]
            work[row]=[x-factor*y for x,y in zip(work[row],work[column])]
    return [row[-1] for row in work]


class SerialRobotModel:
    def __init__(self,dh,*,external_axes=0,external_axis_indices=None,base=None,iterations=200,
                 position_tolerance=.01,orientation_tolerance=.01,ik_fallback_seeds=()):
        if not isinstance(dh,(list,tuple)) or not 1<=len(dh)<=9: raise ValueError('DH model requires 1..9 joints')
        external_limit=min(3,len(dh)-1)
        if type(external_axes) is not int or not 0<=external_axes<=external_limit: raise ValueError('External-axis count must leave at least one main joint')
        if external_axis_indices is None:
            self._external_joints=tuple(range(len(dh)-external_axes,len(dh)))
        else:
            if external_axes:raise ValueError('Choose external_axes or external_axis_indices')
            if (not isinstance(external_axis_indices,(list,tuple)) or len(external_axis_indices)>external_limit
                    or any(type(index) is not int or not 1<=index<=len(dh) for index in external_axis_indices)
                    or len(set(external_axis_indices))!=len(external_axis_indices)):
                raise ValueError('External-axis indices require up to three distinct one-based DH rows and at least one main joint')
            self._external_joints=tuple(index-1 for index in external_axis_indices)
        if type(iterations) is not int or not 1<=iterations<=2000: raise ValueError('IK iterations must be in 1..2000')
        self.rows=[]; self.limits=[]
        for row in dh:
            if type(row) is not dict or set(row)-{'a','alpha','d','theta','type','offset','min','max'}: raise ValueError('Unknown DH joint fields')
            row=dict(row)
            kind=row.get('type','revolute')
            if kind not in ('revolute','prismatic'): raise ValueError('DH joint type must be revolute or prismatic')
            if any(type(value) not in (int,float) for key,value in row.items() if key!='type'): raise ValueError('DH numeric fields require numbers')
            values={name:float(row.get(name,0.)) for name in ('a','alpha','d','theta','offset')}
            original=dh[len(self.rows)]
            bounds=(float(original.get('min',-180 if kind=='revolute' else -1000)),float(original.get('max',180 if kind=='revolute' else 1000)))
            if not all(math.isfinite(v) for v in (*values.values(),*bounds)) or bounds[0]>bounds[1]: raise ValueError('DH parameters and limits must be finite and ordered')
            self.rows.append(dict(type=kind,**values)); self.limits.append(bounds)
        if not isinstance(ik_fallback_seeds,(list,tuple)) or len(ik_fallback_seeds)>8:
            raise ValueError('IK fallback seeds require a list of up to eight joint vectors')
        seeds=[]
        for seed in ik_fallback_seeds:
            if (not isinstance(seed,(list,tuple)) or len(seed)!=len(dh)
                    or any(type(value) not in (int,float) for value in seed) or not self.within_limits(seed)):
                raise ValueError('Each IK fallback seed requires a finite joint vector within the model limits')
            seeds.append(tuple(seed))
        self.ik_fallback_seeds=tuple(seeds)
        self.external_axes=len(self._external_joints); self.base=matrix(base) if base is not None else IDENTITY
        self.iterations=iterations; self.position_tolerance=float(position_tolerance); self.orientation_tolerance=math.radians(orientation_tolerance)
        if not all(math.isfinite(v) and v>0 for v in (self.position_tolerance,self.orientation_tolerance)): raise ValueError('Positive finite IK tolerances required')

    @property
    def axes(self): return len(self.rows)

    def chain(self,joints):
        if len(joints)!=self.axes or not all(type(q) in (int,float) and math.isfinite(q) for q in joints): raise ValueError('Joint data does not match the explicit model')
        result=IDENTITY
        for row,q in zip(self.rows,joints):
            a=row['a']; alpha=math.radians(row['alpha'])
            theta=math.radians(row['theta']+(q+row['offset'] if row['type']=='revolute' else 0.))
            d=row['d']+(q+row['offset'] if row['type']=='prismatic' else 0.)
            ct,st,ca,sa=math.cos(theta),math.sin(theta),math.cos(alpha),math.sin(alpha)
            step=((ct,-st*ca,st*sa,a*ct),(st,ct*ca,-ct*sa,a*st),(0.,sa,ca,d),(0.,0.,0.,1.))
            result=multiply(result,step)
        return result

    def within_limits(self,joints): return len(joints)==self.axes and all(lo<=q<=hi for q,(lo,hi) in zip(joints,self.limits))

    def forward(self,joints,uframe,utool,config_ref=0,*,check_limits=True):
        if type(check_limits) is not bool: raise TypeError('check_limits must be BOOLEAN')
        if config_ref!=0: raise ValueError('Portable DH model supports config_ref=0')
        values=rt().joint_values(joints,self.axes)
        if check_limits and not self.within_limits(values): raise ValueError('Joint values exceed model limits')
        result=multiply(inverse(matrix(uframe)),multiply(multiply(self.base,self.chain(values)),matrix(utool)))
        cfg=uframe.values['CONFIG_DATA'].clone()
        axes=[values[index] for index in self._external_joints]
        return pose(result,cfg,extended=axes),cfg,axes+[0.]*(3-len(axes))

    def solve(self,target,seed,*,fixed=None):
        if len(seed)!=self.axes: raise ValueError('IK reference width does not match model')
        q=[min(hi,max(lo,float(value))) for value,(lo,hi) in zip(seed,self.limits)]
        fixed=dict(fixed or {})
        for i,value in fixed.items():
            if not self.limits[i][0]<=value<=self.limits[i][1]: return None
            q[i]=value
        variables=[i for i in range(self.axes) if i not in fixed and self.limits[i][0]<self.limits[i][1]]
        damping=.1; weight=100.
        current=self.chain(q); residual=error(current,target,weight)
        for iteration in range(self.iterations+1):
            if math.hypot(*residual[:3])<=self.position_tolerance and math.hypot(*residual[3:])/weight<=self.orientation_tolerance: return q
            if iteration==self.iterations or not variables: break
            columns=[]
            for axis in variables:
                shifted=q.copy()
                joint=q[axis]; lower,upper=self.limits[axis]
                forward,backward=upper-joint,joint-lower
                bound=upper if forward>=.001 or forward>=backward else lower
                offset=math.copysign(min(.001,abs(bound-joint)),bound-joint)
                neighbor=min(upper,max(lower,joint+offset))
                # A nominal step can round to zero for a large joint value.
                if neighbor==joint: neighbor=math.nextafter(joint,bound)
                shifted[axis]=neighbor
                columns.append([v/(neighbor-joint) for v in error(current,self.chain(shifted),weight)])
            normal=[[sum(x*y for x,y in zip(left,right))+(damping*damping if i==j else 0.) for j,right in enumerate(columns)] for i,left in enumerate(columns)]
            delta=linear_solve(normal,[sum(x*y for x,y in zip(column,residual)) for column in columns])
            if delta is None: break
            scale=min(1.,10./max(10.,max(abs(value) for value in delta)))
            before=sum(value*value for value in residual); improved=False
            for _ in range(12):
                trial=q.copy()
                for axis,increment in zip(variables,delta): trial[axis]=min(self.limits[axis][1],max(self.limits[axis][0],q[axis]+scale*increment))
                trial_pose=self.chain(trial)
                trial_residual=error(trial_pose,target,weight)
                after=sum(value*value for value in trial_residual)
                if after<before:
                    q,current,residual=trial,trial_pose,trial_residual
                    damping=max(1e-5,damping*.7); improved=True; break
                scale*=.5
            if not improved:
                damping*=5
                if damping>1e6: break
        return None

    def inverse(self,reference,position,uframe,utool,config_ref,config,external):
        if config_ref!=0: raise ValueError('Portable DH model supports config_ref=0')
        values=rt().joint_values(reference,self.axes)
        target=multiply(inverse(self.base),multiply(multiply(matrix(uframe),matrix(position)),inverse(matrix(utool))))
        fixed={}
        if self.external_axes:
            with rt()._numeric_scope('pythonic'): axes=[rt().real(value) for value in external.values]
            if len(axes)<self.external_axes: raise ValueError('External-axis input is shorter than the model')
            fixed=dict(zip(self._external_joints,axes))
        for seed in (values,*self.ik_fallback_seeds):
            result=self.solve(target,seed,fixed=fixed)
            if result is not None:
                joints=rt().JointPosition(('JOINTPOS',self.axes)); joints.values[:]=result; return joints
        raise ValueError('No IK solution within the supplied limits and iteration budget')

    def reachable(self,position,uframe=None,utool=None,*,reference=None):
        target=multiply(inverse(self.base),multiply(multiply(matrix(uframe) if uframe is not None else IDENTITY,matrix(position)),inverse(matrix(utool)) if utool is not None else IDENTITY))
        midpoint=[(lo+hi)/2 for lo,hi in self.limits]
        fixed={index:position.values.get('EXT'+str(slot),0.) for slot,index in enumerate(self._external_joints,1)}
        seeds=([0.]*self.axes,midpoint,[lo+(hi-lo)*.25 for lo,hi in self.limits],
               [lo+(hi-lo)*.75 for lo,hi in self.limits],*self.ik_fallback_seeds)
        if reference is not None:
            try:
                current=rt().joint_values(reference,self.axes)
            except rt().KarelRuntimeError:
                pass  # Reachability can still use the configured search seeds.
            else:
                seeds=(current,*seeds)
        for seed in seeds:
            if self.solve(target,seed,fixed=fixed) is not None: return True
        return False


def _indexed_rows(rows,label):
    if type(rows) is not dict: raise ValueError(label+' requires an object')
    result={}
    for key,row in rows.items():
        if type(key) not in (str,int): raise ValueError(label+' requires INTEGER identifiers')
        try: number=int(key)
        except ValueError as error: raise ValueError(label+' requires INTEGER identifiers') from error
        if number in result: raise ValueError(label+' contains duplicate identifiers')
        result[number]=row
    return result


def robot_context_from_config(config):
    from .extended import RobotContext,RobotState
    from .storage import decode_typed
    if type(config) is not dict: raise ValueError('Robot context must be an object')
    allowed={'groups','active_group','dh','external_axes','external_axis_indices','base','iterations','position_tolerance','orientation_tolerance','ik_fallback_seeds','frames','tools','frame','tool','current','joint_limits'}
    if set(config)-allowed: raise ValueError('Unknown robot context fields')
    if 'active_group' in config and (type(config['active_group']) is not int or not 1<=config['active_group']<=2147483646):
        raise ValueError('Active robot group requires a positive portable INTEGER')
    if 'joint_limits' in config and type(config['joint_limits']) is not list: raise ValueError('joint_limits must be a list of explicit bounds')
    if 'groups' in config:
        if set(config)-{'groups','active_group'}: raise ValueError('Grouped model configuration cannot mix flat model fields')
        rows=_indexed_rows(config['groups'],'Robot group table')
        if not rows or any(not 1<=number<=2147483646 for number in rows):
            raise ValueError('Positive explicit robot groups required')
        groups={number:robot_context_from_config(row) for number,row in rows.items()}
        active=config.get('active_group',min(groups))
        if active not in groups: raise ValueError('Active robot group is not configured')
        context=RobotContext(groups=groups,active_group=active); context.model_config=deepcopy(config); return context
    current=RobotState.from_config(config['current']) if 'current' in config else None
    if 'dh' not in config:
        if set(config)-{'current','active_group','joint_limits','frames','tools','frame','tool'}:
            raise ValueError('Model settings require explicit DH parameters')
        tables=[]
        for key,selection in (('frames','frame'),('tools','tool')):
            rows=config.get(key,{})
            if type(rows) is not dict:raise ValueError('Robot frame/tool tables require objects')
            values={}
            for name,row in rows.items():
                if (type(name) is not str or not name.isascii() or not name.isdecimal() or len(name)>5
                        or str(int(name))!=name or not 0<=int(name)<=32767):
                    raise ValueError('Robot table keys require canonical INTEGER IDs in 0..32767')
                spec,value=decode_typed(row)
                if spec not in (('POSITION',),('XYZWPR',),('XYZWPREXT',)):
                    raise ValueError('Robot tables require Cartesian poses')
                with rt()._numeric_scope('pythonic'):value=rt().frame_value(value,expected=spec)
                values[int(name)]=value
            number=config.get(selection,0)
            if type(number) is not int or not 0<=number<=32767:
                raise ValueError('Active robot table ID must be an INTEGER in 0..32767')
            if selection in config and number not in values:
                raise ValueError('Active frame/tool must be supplied')
            tables.append((values,number))
        if current is None and 'joint_limits' not in config and not any(table for table,_ in tables):
            raise ValueError('Robot context requires DH parameters, explicit tables, joint limits or current state')
        context=RobotContext(current=current,joint_limits=config.get('joint_limits'),active_group=config.get('active_group',1),
            frames=tables[0][0],tools=tables[1][0],active_frame=tables[0][1],active_tool=tables[1][1])
        context.model_config=deepcopy(config);return context
    if 'joint_limits' in config: raise ValueError('DH joint limits belong in the DH rows, not joint_limits')
    base=decode_typed(config['base'])[1] if 'base' in config else None
    model=SerialRobotModel(config['dh'],external_axes=config.get('external_axes',0),
        external_axis_indices=config.get('external_axis_indices'),base=base,iterations=config.get('iterations',200),
        position_tolerance=config.get('position_tolerance',.01),orientation_tolerance=config.get('orientation_tolerance',.01),
        ik_fallback_seeds=config.get('ik_fallback_seeds',()))
    frames={number:decode_typed(row)[1] for number,row in _indexed_rows(config.get('frames',{}),'Robot frame table').items()}
    tools={number:decode_typed(row)[1] for number,row in _indexed_rows(config.get('tools',{}),'Robot tool table').items()}
    frames.setdefault(0,pose()); tools.setdefault(0,pose())
    active_frame=config.get('frame',0); active_tool=config.get('tool',0)
    if active_frame not in frames or active_tool not in tools: raise ValueError('Active frame/tool must be supplied')
    for value in (*frames.values(),*tools.values()): matrix(value)
    def check_position(position,frame,tool):
        snapshot=context.current
        reference=snapshot.joints if snapshot is not None else None
        return model.reachable(position,frame,tool,reference=reference)

    context=RobotContext(forward=model.forward,inverse=model.inverse,check_position=check_position,joint_limits=model.limits,frames=frames,tools=tools,current=current,active_frame=active_frame,active_tool=active_tool,active_group=config.get('active_group',1))
    context.model=model; context.model_config=deepcopy(config)
    context.reachable=lambda p:check_position(p,context.frame(context.active_frame),context.tool(context.active_tool))
    for number in context.frames: context.frame(number)
    for number in context.tools: context.tool(number)
    context.frame(active_frame);context.tool(active_tool)
    return context
