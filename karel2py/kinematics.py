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
    def __init__(self,dh,*,external_axes=0,base=None,iterations=200,position_tolerance=.01,orientation_tolerance=.01):
        if not isinstance(dh,(list,tuple)) or not 1<=len(dh)<=9: raise ValueError('DH model requires 1..9 joints')
        if type(external_axes) is not int or not 0<=external_axes<=min(3,len(dh)-1): raise ValueError('External-axis count must leave at least one main joint')
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
        self.external_axes=external_axes; self.base=matrix(base) if base is not None else IDENTITY
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
        axes=values[-self.external_axes:] if self.external_axes else []
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
        for _ in range(self.iterations):
            current=self.chain(q); residual=error(current,target,weight)
            if math.hypot(*residual[:3])<=self.position_tolerance and math.hypot(*residual[3:])/weight<=self.orientation_tolerance: return q
            if not variables: break
            columns=[]
            for axis in variables:
                shifted=q.copy(); amount=.001
                if q[axis]+amount>self.limits[axis][1]: amount=-amount
                shifted[axis]+=amount
                columns.append([v/amount for v in error(current,self.chain(shifted),weight)])
            normal=[[sum(x*y for x,y in zip(left,right))+(damping*damping if i==j else 0.) for j,right in enumerate(columns)] for i,left in enumerate(columns)]
            delta=linear_solve(normal,[sum(x*y for x,y in zip(column,residual)) for column in columns])
            if delta is None: break
            scale=min(1.,10./max(10.,max(abs(value) for value in delta)))
            before=sum(value*value for value in residual); improved=False
            for _ in range(12):
                trial=q.copy()
                for axis,increment in zip(variables,delta): trial[axis]=min(self.limits[axis][1],max(self.limits[axis][0],q[axis]+scale*increment))
                after=sum(value*value for value in error(self.chain(trial),target,weight))
                if after<before:
                    q=trial; damping=max(1e-5,damping*.7); improved=True; break
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
            fixed={self.axes-self.external_axes+i:axes[i] for i in range(self.external_axes)}
        result=self.solve(target,values,fixed=fixed)
        if result is None: raise ValueError('No IK solution within the supplied limits and iteration budget')
        joints=rt().JointPosition(('JOINTPOS',self.axes)); joints.values[:]=result; return joints

    def reachable(self,position,uframe=None,utool=None):
        target=multiply(inverse(self.base),multiply(multiply(matrix(uframe) if uframe is not None else IDENTITY,matrix(position)),inverse(matrix(utool)) if utool is not None else IDENTITY))
        midpoint=[(lo+hi)/2 for lo,hi in self.limits]
        fixed={self.axes-self.external_axes+i:position.values.get('EXT'+str(i+1),0.) for i in range(self.external_axes)}
        for seed in ([0.]*self.axes,midpoint,[lo+(hi-lo)*.25 for lo,hi in self.limits],[lo+(hi-lo)*.75 for lo,hi in self.limits]):
            if self.solve(target,seed,fixed=fixed) is not None: return True
        return False


def robot_context_from_config(config):
    from .extended import RobotContext,RobotState
    from .storage import decode_typed
    if type(config) is not dict: raise ValueError('Robot context must be an object')
    allowed={'groups','active_group','dh','external_axes','base','iterations','position_tolerance','orientation_tolerance','frames','tools','frame','tool','current','joint_limits'}
    if set(config)-allowed: raise ValueError('Unknown robot context fields')
    if 'joint_limits' in config and type(config['joint_limits']) is not list: raise ValueError('joint_limits must be a list of explicit bounds')
    if 'groups' in config:
        if set(config)-{'groups','active_group'}: raise ValueError('Grouped model configuration cannot mix flat model fields')
        groups={int(k):robot_context_from_config(v) for k,v in config['groups'].items()}
        if not groups or any(g<1 for g in groups): raise ValueError('Positive explicit robot groups required')
        active=config.get('active_group',min(groups))
        if active not in groups: raise ValueError('Active robot group is not configured')
        context=RobotContext(groups=groups,active_group=active); context.model_config=deepcopy(config); return context
    current=RobotState.from_config(config['current']) if 'current' in config else None
    if 'dh' not in config:
        if (current is None and 'joint_limits' not in config) or set(config)-{'current','active_group','joint_limits'}: raise ValueError('Robot context requires DH parameters, explicit joint limits or current state')
        context=RobotContext(current=current,joint_limits=config.get('joint_limits'),active_group=config.get('active_group',1));context.model_config=deepcopy(config);return context
    if 'joint_limits' in config: raise ValueError('DH joint limits belong in the DH rows, not joint_limits')
    base=decode_typed(config['base'])[1] if 'base' in config else None
    model=SerialRobotModel(config['dh'],external_axes=config.get('external_axes',0),base=base,iterations=config.get('iterations',200),position_tolerance=config.get('position_tolerance',.01),orientation_tolerance=config.get('orientation_tolerance',.01))
    frames={int(k):decode_typed(v)[1] for k,v in config.get('frames',{}).items()}; tools={int(k):decode_typed(v)[1] for k,v in config.get('tools',{}).items()}
    frames.setdefault(0,pose()); tools.setdefault(0,pose())
    active_frame=config.get('frame',0); active_tool=config.get('tool',0)
    if active_frame not in frames or active_tool not in tools: raise ValueError('Active frame/tool must be supplied')
    for value in (*frames.values(),*tools.values()): matrix(value)
    context=RobotContext(forward=model.forward,inverse=model.inverse,joint_limits=model.limits,frames=frames,tools=tools,current=current,active_frame=active_frame,active_tool=active_tool,active_group=config.get('active_group',1))
    context.model=model; context.model_config=deepcopy(config)
    context.reachable=lambda p:model.reachable(p,context.frame(context.active_frame),context.tool(context.active_tool))
    for number in context.frames: context.frame(number)
    for number in context.tools: context.tool(number)
    context.frame(active_frame);context.tool(active_tool)
    return context
