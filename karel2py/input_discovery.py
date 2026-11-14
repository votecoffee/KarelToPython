"""Bounded read-before-write discovery from checked generated Python contracts."""
from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path
import re

from .input_contract import extract, InputContractError


UNKNOWN = object()
MAX_STEPS = 100000
MAX_INPUTS = 2048
MAX_FACTS = 32767
MAX_BYTES = 16 * 1024 * 1024
SCALARS = {'INTEGER', 'BYTE', 'SHORT', 'REAL', 'BOOLEAN', 'STRING', 'NUMERIC'}
PURE = {'ABS','ROUND','TRUNC','SQRT','SIN','COS','TAN','ASIN','ACOS','ATAN','ATAN2',
        'EXP','LN','LOG','LEN','SUB_STR','INDEX','CHR','ORD','VEC','POS','FRAME','INV',
        'MIRROR','DOT','CROSS','MAG','UNIT','NORMAL','APPROACH','ORIENT'}


class InputDiscoveryError(ValueError):
    pass


class _Limit(Exception):
    pass


@dataclass(frozen=True)
class _Location:
    kind: str
    owner: str
    root: object
    parts: tuple = ()
    spec: object = field(default=None, compare=False, hash=False)

    @property
    def key(self):
        return self.kind, self.owner, self.root, self.parts

    @property
    def path(self):
        text = str(self.root)
        for kind, value in self.parts:
            text += ('.' + value if kind == 'field' else
                     '[group=' + (str(value) if value is not None else 'caller-default') + ']' if kind=='group'
                     else '[' + str(value) + ']')
        return text


@dataclass
class _Value:
    constant: object = UNKNOWN
    complete: bool = True
    spec: object = None


@dataclass
class _Flow:
    defined: set = field(default_factory=set)
    assigned: set = field(default_factory=set)
    maybe: set = field(default_factory=set)
    constants: dict = field(default_factory=dict)
    stopped: bool = False
    opaque: bool = False

    def copy(self):
        return _Flow(self.defined.copy(),self.assigned.copy(),self.maybe.copy(),
                     self.constants.copy(),self.stopped,self.opaque)

    def take(self, other):
        self.defined,self.assigned,self.maybe,self.constants = other.defined,other.assigned,other.maybe,other.constants
        self.stopped,self.opaque = other.stopped,other.opaque


def _merge(flows):
    live = [flow for flow in flows if not flow.stopped]
    if not live:
        result=flows[0].copy();result.stopped=True;return result
    first=live[0]
    constants={key:value for key,value in first.constants.items()
               if all(key in other.constants and type(value) is type(other.constants[key]) and value==other.constants[key] for other in live[1:])}
    return _Flow(set.intersection(*(flow.defined for flow in live)),
                 set.intersection(*(flow.assigned for flow in live)),
                 set.union(*(flow.maybe for flow in live)),constants,False,any(flow.opaque for flow in live))


def _array_dimensions(spec):
    dimensions=[]
    while spec and spec[0]=='ARRAY':
        dimensions.extend(spec[1] if type(spec[1]) is list else [spec[1]])
        spec=spec[2]
    return dimensions,spec


def _array_value_schema(declared,source):
    """Retain checked constraints and inherit only known source dimensions."""
    if not source or source[0]!='ARRAY':return declared
    dimensions,terminal=_array_dimensions(source)
    expected,_=_array_dimensions(declared)
    if len(dimensions)!=len(expected) or any(a is not None and b is not None and a!=b for a,b in zip(expected,dimensions)):
        return None
    axes=iter(dimensions)
    def resolve(spec):
        shape=spec[1] if type(spec[1]) is list else [spec[1]]
        sizes=[]
        for wanted in shape:
            actual=next(axes);sizes.append(actual if wanted is None else wanted)
        element=spec[2]
        if element[0]=='ARRAY':element=resolve(element)
        elif element==['STRING',None] and terminal and terminal[0]=='STRING':element=terminal
        return ['ARRAY',sizes if type(spec[1]) is list else sizes[0],element,*spec[3:]]
    return resolve(declared)


def _stored_value(spec,value):
    """Availability/schema facts after storage; do not evaluate runtime casts."""
    constant=value.constant;complete=value.complete
    if spec and spec[0]=='STRING' and type(constant) is str:
        capacity=spec[1] if len(spec)>1 else None
        if type(capacity) is not int or len(constant)>capacity:constant=UNKNOWN
    elif spec and spec[0] in ('INTEGER','BYTE','SHORT') and type(constant) is float:
        if spec==['SHORT'] and math.isfinite(constant) and math.trunc(constant)==32767:complete=False
        constant=UNKNOWN
    if spec==['SHORT'] and constant==32767:complete=False
    if spec and spec[0]=='ARRAY' and value.spec and value.spec[0]=='ARRAY':
        _,target=_array_dimensions(spec);_,source=_array_dimensions(value.spec)
        if target==['SHORT'] and source!=target:complete=False
    return _Value(constant,complete,spec)


class _Analyzer:
    def __init__(self, plan):
        self.plan=plan;self.program=plan['program'];self.steps=0;self.serial=0
        self.inputs={};self.unresolved={};self.frames=[];self.exits=[];self.contexts={}
        self.imports={row['name']:row['owner'] for row in plan.get('imports',[])}

    def tick(self):
        self.steps+=1
        if self.steps>MAX_STEPS:raise _Limit('Analysis step limit reached')

    def opaque(self, flow):
        flow.opaque=True;flow.defined.clear();flow.assigned.clear();flow.constants.clear()

    def context(self, service, address):
        self.contexts.setdefault((service,str(address)),dict(service=service,address=address))

    def where(self, node):
        line=node.get('line',1);file=self.plan.get('filename','<input>');physical=line
        for span in self.plan.get('origins',[]):
            if span['expanded_start']<=line<=span['expanded_end']:
                file=span['file'];physical=span['source_start']+line-span['expanded_start'];break
        return dict(file=file,line=physical,column=node.get('column',1),
                    routine=self.frames[-1]['name'] if self.frames else None,
                    python_lines=sorted({row['python_line'] for row in self.plan.get('source_map',[]) if row['karel_line']==line}))

    def unresolved_at(self, code, message, node):
        location=self.where(node);key=(code,message,location['file'],location['line'],location['column'],location['routine'])
        self.unresolved.setdefault(key,dict(code=code,message=message,location=location))

    def slot(self, name):
        if self.frames and name in self.frames[-1]['slots']:return self.frames[-1]['slots'][name]
        if name in self.plan['types']:
            return _Location('variable',self.imports.get(name,self.program),name,spec=self.plan['types'][name])
        return None

    def constant(self, name):
        if self.frames and name in self.frames[-1]['constants']:return self.frames[-1]['constants'][name]
        return self.plan['constants'].get(name,UNKNOWN)

    def child(self, loc, kind, value, node):
        spec=loc.spec
        if kind=='field':
            fields=dict(spec[2]) if spec and spec[0]=='STRUCTURE' else self.plan.get('record_fields',{}).get(spec[0],{}) if spec else {}
            selected=fields.get(value)
        else:
            selected=None
            if spec and spec[0]=='ARRAY':
                shape=spec[1] if type(spec[1]) is list else [spec[1]]
                if type(shape[0]) is int and 1<=value<=shape[0]:
                    selected=['ARRAY',shape[1:],spec[2]] if len(shape)>1 else spec[2]
            elif spec and spec[0]=='JOINTPOS' and type(spec[1]) is int and 1<=value<=spec[1]:selected=['REAL']
        if selected is None:
            self.unresolved_at('selection','Unsupported or unbounded selected schema for '+loc.path,node)
            return None
        return _Location(loc.kind,loc.owner,loc.root,(*loc.parts,(kind,value)),selected)

    def locate(self, expr, flow, conditional):
        if not isinstance(expr,dict):return None
        kind=expr.get('kind');args=expr.get('args',[])
        if 'token' in expr:return self.slot(expr['token'])
        if kind=='name':return self.slot(expr['value'])
        if kind=='group':return self.locate(args[0],flow,conditional)
        if kind=='field':
            base=self.locate(args[0],flow,conditional)
            return self.child(base,'field',expr['value'],expr) if base else None
        if kind=='index':
            base=args[0]
            if base.get('kind')=='name' and base['value'] in self.plan.get('port_types',{}):
                index=self.expr(args[1],flow,conditional).constant
                if type(index) is int and index>0:
                    self.context('ports',base['value']+'['+str(index)+']')
                    return _Location('port','',base['value'],(('index',index),),[self.plan['port_types'][base['value']]])
                self.unresolved_at('dynamic-address','Port index requires an explicit runtime mapping',expr);return None
            loc=self.locate(base,flow,conditional)
            for argument in args[1:]:
                index=self.expr(argument,flow,conditional).constant
                if type(index) is not int:
                    self.unresolved_at('dynamic-address','ARRAY/joint index is not statically known for '+(loc.path if loc else '<computed>'),expr);loc=None
                elif loc:loc=self.child(loc,'index',index,expr)
            return loc
        if kind in ('call','binary','unary','literal','real_literal','predefined'):
            self.expr(expr,flow,conditional)
        return None

    def leaves(self, loc):
        leaves=[]
        def visit(current):
            self.tick()
            spec=current.spec
            if not spec:return False
            if spec[0] in SCALARS:
                leaves.append(current)
                if len(leaves)>MAX_FACTS:raise _Limit('Analysis storage limit reached')
                return True
            if spec[0]=='ARRAY':
                shape=spec[1] if type(spec[1]) is list else [spec[1]]
                if type(shape[0]) is not int or not 1<=shape[0]<=MAX_FACTS:return False
                return all(visit(self.child(current,'index',index,{})) for index in range(1,shape[0]+1))
            if spec[0]=='JOINTPOS':
                return all(visit(self.child(current,'index',index,{})) for index in range(1,spec[1]+1))
            fields=dict(spec[2]) if spec[0]=='STRUCTURE' else self.plan.get('record_fields',{}).get(spec[0])
            if fields is None:return False
            return all(visit(self.child(current,'field',name,{})) for name in fields)
        return leaves if visit(loc) else None

    def read(self, loc, node, flow, conditional):
        leaves=self.leaves(loc)
        if leaves is None:
            self.unresolved_at('schema','Resource or unsupported value read: '+loc.path,node)
            return _Value(complete=False,spec=loc.spec)
        keys={leaf.key for leaf in leaves}
        missing=keys-flow.defined
        if missing:
            initial=missing-flow.assigned
            if not initial:
                self.unresolved_at('derived-value','Read follows a write whose complete value is not proven: '+loc.path,node)
            elif loc.kind=='local':
                self.unresolved_at('local-value','Fresh routine-local value is read before initialization: '+loc.path,node)
            else:
                uncertain=conditional or flow.opaque or bool(missing & flow.maybe)
                key=loc.key;certainty='conditional' if uncertain else 'required'
                if key not in self.inputs:
                    if len(self.inputs)>=MAX_INPUTS:raise _Limit('Analysis input limit reached')
                    spec=None if loc.spec==['NUMERIC'] else loc.spec
                    self.inputs[key]=dict(kind=loc.kind,program=loc.owner or None,path=loc.path,type=spec,
                                          certainty=certainty,locations=[],reason='Read before a definite source write')
                    if loc.kind=='variable':
                        self.inputs[key].update(root_path=str(loc.root),root_type=self.plan['types'].get(loc.root),selectors=list(loc.parts))
                    elif loc.kind=='port':
                        self.inputs[key].update(port=loc.root,index=dict(loc.parts).get('index'))
                    elif loc.kind.endswith('_register'):
                        self.inputs[key]['index']=loc.root
                        if loc.kind=='position_register':self.inputs[key]['group']=dict(loc.parts).get('group')
                        if loc.spec==['NUMERIC']:self.inputs[key]['type_options']=[['INTEGER'],['REAL']]
                row=self.inputs[key]
                if certainty=='required':row['certainty']='required'
                location=self.where(node)
                if location not in row['locations']:row['locations'].append(location)
        # A scalar read has a value if execution continues. Aggregate copies can
        # preserve missing leaves, so they do not establish complete receivers.
        complete=not missing or bool(loc.spec and loc.spec[0] in SCALARS)
        return _Value(flow.constants.get(loc.key,UNKNOWN),complete,loc.spec)

    def write(self, loc, value, flow, node, *, definite=True):
        if loc is None:
            self.unresolved_at('write-target','Writable target is not statically resolved',node);return
        leaves=self.leaves(loc)
        if leaves is None:
            self.unresolved_at('schema','Resource or unsupported write: '+loc.path,node);return
        stored=_stored_value(loc.spec,value);constant=stored.constant;complete=stored.complete
        keys={leaf.key for leaf in leaves};flow.maybe.update(keys)
        for key in keys:flow.constants.pop(key,None)
        if not complete:flow.defined.difference_update(keys)
        if definite:
            if not flow.opaque:flow.assigned.update(keys)
            flow.defined.difference_update(keys)
            if complete and not flow.opaque:
                if not (loc.spec==['SHORT'] and constant==32767):flow.defined.update(keys)
            if len(keys)==1 and constant is not UNKNOWN and not flow.opaque:
                flow.constants[loc.key]=constant
        if len(flow.maybe)>MAX_FACTS:raise _Limit('Analysis storage limit reached')

    def logical(self,node,left,flow,conditional,*,typed=True):
        """Follow the emitted Boolean branch; optional RHS effects never dominate."""
        skip=node['value']=='OR';spec=['BOOLEAN'] if typed else None
        if typed and type(left.constant) is bool:
            if left.constant==skip:return _Value(skip,left.complete,spec)
            right=self.expr(node['args'][1],flow,conditional)
            return _Value(right.constant if type(right.constant) is bool else UNKNOWN,left.complete and right.complete,spec)
        before=flow.copy();taken=flow.copy()
        right=self.expr(node['args'][1],taken,True)
        flow.take(_merge([before,taken]))
        constant=(skip if taken.stopped or type(right.constant) is bool and right.constant==skip else UNKNOWN) if typed else UNKNOWN
        complete=left.complete and (taken.stopped or right.complete) if typed else False
        return _Value(constant,complete,spec)

    def expr(self, node, flow, conditional=False):
        self.tick()
        if not isinstance(node,dict):return _Value()
        kind=node.get('kind');args=node.get('args',[]);value=node.get('value')
        if kind=='literal':return _Value(value)
        if kind=='real_literal':
            try:return _Value(float(value))
            except ValueError:return _Value()
        if kind=='predefined':return _Value({'ON':True,'OFF':False,'MININT':-2147483648,'MAXINT':2147483647}.get(value,UNKNOWN))
        if kind=='name':
            loc=self.slot(value)
            if loc:return self.read(loc,node,flow,conditional)
            constant=self.constant(value)
            if constant is not UNKNOWN:return _Value(constant)
            if value in self.plan['routines']:return self.call(dict(node,kind='call',args=[]),flow,conditional)
        if kind in ('field','index'):
            loc=self.locate(node,flow,conditional)
            if loc:return self.read(loc,node,flow,conditional)
            self.unresolved_at('selection','Computed or dynamic data read is unresolved',node);return _Value(complete=False)
        if kind=='group':return self.expr(args[0],flow,conditional)
        if kind in ('unary','binary'):
            if kind=='binary' and value in ('AND','OR'):
                left=self.expr(args[0],flow,conditional);evaluation=node.get('evaluation')
                if evaluation=='short-circuit' or evaluation is None and (type(left.constant) is bool or left.spec==['BOOLEAN']):
                    return self.logical(node,left,flow,conditional)
                if evaluation!='eager' and not (evaluation is None and (type(left.constant) is int or left.spec in (['INTEGER'],['BYTE'],['SHORT']))):
                    self.unresolved_at('operator-mode','AND/OR evaluation category is unresolved; retranslate the target',node)
                    return self.logical(node,left,flow,conditional,typed=False)
                values=[left,self.expr(args[1],flow,conditional)]
            else:values=[self.expr(item,flow,conditional) for item in args]
            known=[item.constant for item in values]
            if all(item is not UNKNOWN for item in known):
                try:
                    if any(type(item) is int and item.bit_length()>64 or type(item) is str and len(item)>254 for item in known):return _Value()
                    if kind=='binary' and value=='*' and any(type(item) is str for item in known):return _Value()
                    if kind=='unary':
                        if value=='NOT':result=not known[0] if type(known[0]) is bool else ~known[0]
                        else:result=-known[0] if value=='-' else +known[0]
                    else:
                        a,b=known
                        if value=='+':result=a+b
                        elif value=='-':result=a-b
                        elif value=='*':result=a*b
                        elif value=='/':result=a/b
                        elif value=='=':result=a==b
                        elif value=='<>':result=a!=b
                        elif value=='<':result=a<b
                        elif value=='<=':result=a<=b
                        elif value=='>':result=a>b
                        elif value=='>=':result=a>=b
                        elif value=='AND':result=(a and b) if type(a) is bool and type(b) is bool else a & b
                        elif value=='OR':result=(a or b) if type(a) is bool and type(b) is bool else a | b
                        else:return _Value()
                    if (type(result) in (bool,int,float,str) and (type(result) is not str or len(result)<=254)
                            and (type(result) is not int or result.bit_length()<=64)
                            and (type(result) is not float or math.isfinite(result))):return _Value(result)
                except (ArithmeticError,TypeError,ValueError):pass
            return _Value(spec=['BOOLEAN'] if kind=='binary' and value in ('=','<>','<','<=','>','>=') else None)
        if kind=='call':return self.call(node,flow,conditional)
        if kind in ('write_item','read_item','eval'):
            values=[self.expr(item,flow,conditional) for item in args]
            return values[0] if values else _Value()
        if kind=='write_cr':return _Value()
        self.unresolved_at('expression','Expression form requires further analysis: '+str(kind),node)
        for item in args:
            if isinstance(item,dict):self.expr(item,flow,True)
        return _Value(complete=False)

    def call(self, node, flow, conditional):
        name=node['value'];args=node['args']
        if name in self.plan['routines']:return self.routine(name,args,node,flow,conditional)
        if name in ('UNINIT','ARRAY_LEN'):
            target=args[0] if args else {};spec=None
            while target.get('kind')=='group':target=target['args'][0]
            if target.get('kind') in ('name','field','index'):
                loc=self.locate(target,flow,conditional);spec=loc.spec if loc else None
            elif args:spec=self.expr(target,flow,conditional).spec
            values=[self.expr(item,flow,conditional) for item in args[1:]]
            if name=='ARRAY_LEN' and spec and spec[0]=='ARRAY':
                dimensions,_=_array_dimensions(spec)
                dimension=values[0].constant if values else 1
                if type(dimension) is int and 1<=dimension<=len(dimensions):
                    size=dimensions[dimension-1]
                    if type(size) is int:return _Value(size,spec=['INTEGER'])
            return _Value(spec=['BOOLEAN'] if name=='UNINIT' else ['INTEGER'])
        if name in PURE:
            for item in args:self.expr(item,flow,conditional)
            return _Value()
        signature=node.get('signature')
        if name=='GET_REG':signature=[['i','INTEGER'],['o','BOOLEAN'],['o','INTEGER'],['o','REAL'],['o','INTEGER']]
        elif name in ('SET_INT_REG','SET_REAL_REG'):signature=[['i','INTEGER'],['i','INTEGER'],['o','INTEGER']]
        elif name=='CNV_STR_INT':signature=[['i','STRING'],['o','INTEGER']]
        values=[];outputs=[]
        for index,item in enumerate(args):
            mode=signature[index][0] if signature and index<len(signature) else 'i'
            if mode in ('o','m'):
                loc=self.locate(item,flow,conditional);values.append(_Value());outputs.append((index,loc))
            elif mode=='r':
                loc=self.locate(item,flow,conditional)
                values.append(self.read(loc,item,flow,conditional) if loc else self.expr(item,flow,conditional));outputs.append((index,loc))
            else:values.append(self.expr(item,flow,conditional))
        known=[value.constant for value in values]
        if name in ('GET_VAR','SET_VAR'):
            owner,path=known[1:3]
            loc=None
            if type(owner) is str and owner.upper() in ('',self.program) and type(path) is str:
                match=re.match(r'[A-Za-z_][A-Za-z_0-9]*',path)
                if match and match[0].upper() in self.plan['types']:
                    root=match[0].upper();loc=_Location('variable',self.imports.get(root,self.program),root,spec=self.plan['types'][root])
                    rest=path[match.end():]
                    while rest and loc:
                        field=re.match(r'\.([A-Za-z_][A-Za-z_0-9]*)',rest)
                        index=re.match(r'\[([0-9]+(?:,[0-9]+)*)\]',rest)
                        if field:loc=self.child(loc,'field',field[1].upper(),node);rest=rest[field.end():]
                        elif index:
                            for item in index[1].split(','):
                                if loc:loc=self.child(loc,'index',int(item),node)
                            rest=rest[index.end():]
                        else:loc=None
            complete=False
            if loc:
                if name=='GET_VAR':
                    leaves=self.leaves(loc);complete=leaves is not None and all(leaf.key in flow.defined for leaf in leaves)
                    self.read(loc,node,flow,conditional)
                else:self.write(loc,_Value(complete=False),flow,node,definite=False)
            else:self.unresolved_at('variable-path','GET_VAR/SET_VAR requires a known own-program static data path',node)
            for index,target in outputs:self.write(target,_Value(complete=complete if index==3 else True),flow,node,definite=index==4)
            return _Value()
        bank=None;reading=False;writing=False;bank_type=None
        if name in ('GET_REG','SET_INT_REG','SET_REAL_REG'):
            bank_type=['REAL'] if name=='SET_REAL_REG' else ['INTEGER'] if name=='SET_INT_REG' else None
            if known and type(known[0]) is int and known[0]>0:bank=_Location('numeric_register','',known[0],spec=bank_type or ['NUMERIC'])
            reading=name=='GET_REG';writing=not reading
        elif name in ('GET_STR_REG','SET_STR_REG'):
            if known and type(known[0]) is int and known[0]>0:bank=_Location('string_register','',known[0],spec=['STRING',None])
            reading=name=='GET_STR_REG';writing=not reading
        elif name in ('GET_POS_REG','GET_JPOS_REG','GET_EPOS_REG','SET_POS_REG','SET_JPOS_REG','SET_EPOS_REG'):
            group=known[-1] if len(args)>(2 if name.startswith('GET_') else 3) else self.plan.get('default_group')
            if (known and type(known[0]) is int and known[0]>0
                    and (group is None or type(group) is int and group>0)):
                bank=_Location('position_register','',known[0],(('group',group),),['JOINTPOS',9] if 'JPOS' in name else ['XYZWPREXT'])
            reading=name.startswith('GET_');writing=not reading
        handled=reading or writing
        if handled:
            if bank:
                self.context('numeric' if bank.kind=='numeric_register' else 'strings' if bank.kind=='string_register' else 'positions',bank.path)
                if reading:self.read(bank,node,flow,conditional)
                else:self.write(bank,_Value(),flow,node)
            else:self.unresolved_at('dynamic-address','Register address requires an explicit runtime mapping',node)
        else:
            self.unresolved_at('service','Service or external input effects require explicit review: '+name,node)
            self.opaque(flow)
        for index,loc in outputs:
            status=handled and index==len(args)-1
            if name in ('GET_POS_REG','GET_JPOS_REG','GET_EPOS_REG'):status=index==1
            if name in ('SET_POS_REG','SET_JPOS_REG','SET_EPOS_REG'):status=index==2
            self.write(loc,_Value(),flow,node,definite=status)
        return _Value(complete=reading or not signature)

    def routine(self, name, args, node, flow, conditional):
        routine=self.plan['routines'][name]
        modes=node.get('passing',[]);actual=[]
        for index,item in enumerate(args):
            mode=modes[index] if index<len(modes) else 'unknown'
            if mode=='reference':actual.append(self.locate(item,flow,conditional))
            elif mode=='value':actual.append(self.expr(item,flow,conditional))
            else:
                self.unresolved_at('argument','Routine passing mode is unresolved: '+name,node)
                actual.append(self.expr(item,flow,conditional))
        if routine['external'] or name in [frame['name'] for frame in self.frames] or len(self.frames)>=32:
            self.unresolved_at('routine','External or recursive routine effects are unresolved: '+name,node)
            for item in actual:
                if isinstance(item,_Location):self.read(item,node,flow,True)
            self.opaque(flow);return _Value(complete=False)
        self.serial+=1;owner='@'+name+':'+str(self.serial)
        bindings=[]
        for (formal,spec),item in zip(routine['parameters'],actual):
            source=item.spec if isinstance(item,(_Value,_Location)) else None
            if (isinstance(item,_Location) and spec[0]=='STRING' and source and source[0]=='STRING'
                    and spec[1] is not None and source[1] is not None and spec[1]!=source[1]):
                self.unresolved_at('parameter-capacity','Concrete STRING capacity conflicts with routine constraint: '+name+'.'+formal,node)
                self.opaque(flow);return _Value(complete=False)
            resolved=_array_value_schema(spec,source) if spec[0]=='ARRAY' else spec
            if resolved is None:
                self.unresolved_at('parameter-shape','Concrete ARRAY shape conflicts with routine constraint: '+name+'.'+formal,node)
                self.opaque(flow);return _Value(complete=False)
            bindings.append((formal,spec,item,resolved))
        frame=dict(name=name,slots={key:_Location('local',owner,key,spec=spec) for key,spec in routine['types'].items()},
                   constants=routine['constants'])
        for formal,spec,item,resolved in bindings:
            if isinstance(item,_Location):frame['slots'][formal]=item
            else:
                if spec==['STRING',None]:resolved=['STRING',254]
                loc=_Location('local',owner,formal,spec=resolved);frame['slots'][formal]=loc
                self.write(loc,item or _Value(complete=False),flow,node)
        old_exits=self.exits;self.exits=[];self.frames.append(frame)
        try:
            self.block(routine['body'],flow,conditional)
            exits=self.exits[:]
            if not flow.stopped and routine['result'] is None:exits.append((flow.copy(),_Value()))
        finally:
            self.frames.pop();self.exits=old_exits
        if not exits:
            flow.stopped=True;return _Value(complete=False)
        merged=_merge([item[0] for item in exits])
        for field_name in ('defined','assigned','maybe'):
            setattr(merged,field_name,{key for key in getattr(merged,field_name) if key[1]!=owner})
        merged.constants={key:value for key,value in merged.constants.items() if key[1]!=owner}
        flow.take(merged)
        values=[item[1] for item in exits];result=routine['result']
        if result:
            converted=[]
            for value in values:
                schema=_array_value_schema(result,value.spec) if result[0]=='ARRAY' else result
                if schema is None:
                    self.unresolved_at('result-shape','Concrete ARRAY shape conflicts with result constraint: '+name,node)
                    converted.append(_Value(complete=False,spec=result))
                else:converted.append(_stored_value(schema,value))
            values=converted
        constant=values[0].constant if all(item.constant is not UNKNOWN and type(item.constant) is type(values[0].constant) and item.constant==values[0].constant for item in values) else UNKNOWN
        schema=values[0].spec if all(item.spec==values[0].spec for item in values) else result
        return _Value(constant,all(item.complete for item in values),schema)

    def block(self, body, flow, conditional=False):
        for node in body:
            if flow.stopped and not flow.opaque:break
            self.statement(node,flow,conditional)

    def statement(self, node, flow, conditional):
        self.tick();kind=node['kind'];args=node['args']
        if kind=='assign':
            value=self.expr(args[1],flow,conditional)
            self.write(self.locate(args[0],flow,conditional),value,flow,node);return
        if kind=='call':self.expr(args[0],flow,conditional);return
        if kind=='if':
            condition=self.expr(args[0],flow,conditional).constant
            if type(condition) is bool:
                self.block(node['body'] if condition else node['alternate'],flow,conditional);return
            left,right=flow.copy(),flow.copy()
            self.block(node['body'],left,True);self.block(node['alternate'],right,True)
            flow.take(_merge([left,right]));return
        if kind=='while':
            condition=self.expr(args[0],flow,conditional).constant
            if condition is False:return
            before=flow.copy();body=flow.copy();body.constants.clear()
            self.block(node['body'],body,True)
            if not body.stopped:self.expr(args[0],body,True)
            flow.take(_merge([before,body]));return
        if kind=='repeat':
            flow.constants.clear();self.block(node['body'],flow,conditional)
            if not flow.stopped:self.expr(args[0],flow,conditional)
            return
        if kind=='select':
            selected=self.expr(args[0],flow,conditional).constant
            cases=[]
            for _,labels,body in args[1]:
                values=[self.expr(label,flow,conditional).constant for label in labels]
                cases.append((values,body))
            if selected is not UNKNOWN and all(value is not UNKNOWN for values,_ in cases for value in values):
                body=next((body for values,body in cases if selected in values),node['alternate'] if node['has_else'] else None)
                if body is None:flow.stopped=True
                else:self.block(body,flow,conditional)
            else:
                branches=[flow.copy() for _ in range(len(cases)+int(node['has_else']))]
                bodies=[body for _,body in cases]+([node['alternate']] if node['has_else'] else [])
                for branch,body in zip(branches,bodies):self.block(body,branch,True)
                flow.take(_merge(branches))
            return
        if kind=='for':
            exit_start=len(self.exits)
            loc=self.locate(args[0],flow,conditional);initial=self.expr(args[1],flow,conditional)
            self.write(loc,initial,flow,node);final=self.expr(args[2],flow,conditional)
            step=-1 if args[3]=='DOWNTO' else 1
            if type(initial.constant) is int and type(final.constant) is int:
                count=max(0,(final.constant-initial.constant)*step+1)
            else:count=None
            if count is not None and count<=32:
                for index in range(count):
                    if flow.stopped:break
                    self.write(loc,_Value(initial.constant+step*index),flow,node)
                    self.block(node['body'],flow,conditional)
            else:
                before=flow.copy();body=flow.copy();body.constants.clear()
                self.block(node['body'],body,True);flow.take(_merge([before,body]))
            if loc:
                self.write(loc,_Value(complete=False),flow,node)
                for exited,_ in self.exits[exit_start:]:self.write(loc,_Value(complete=False),exited,node)
            return
        if kind=='return':
            value=self.expr(args[0],flow,conditional) if args and args[0] is not None else _Value()
            self.exits.append((flow.copy(),value));flow.stopped=True;return
        if kind=='write_items':
            for argument in args:self.expr(argument,flow,conditional)
            return
        if kind=='read':
            self.unresolved_at('input-stream','READ requires explicitly supplied input data',node)
            for argument in args:
                if argument.get('kind')=='read_cr':continue
                target=argument['args'][0] if argument.get('kind')=='read_item' else argument
                loc=self.locate(target,flow,conditional)
                if argument.get('kind')=='read_item':
                    for control in argument['args'][1:]:self.expr(control,flow,conditional)
                self.write(loc,_Value(),flow,node,definite=False)
            return
        if kind=='abort' or kind=='task_control' and args[0] in ('ABORT','STOP') and len(args)==1:
            flow.stopped=True;return
        self.unresolved_at('statement','Control or resource statement requires further analysis: '+kind,node)
        self.opaque(flow)
        for argument in args:
            if isinstance(argument,dict):self.expr(argument,flow,True)
        self.block(node.get('body',[]),flow,True);self.block(node.get('alternate',[]),flow,True)


def discover_inputs(python_source, *, filename='<python>'):
    """Return candidates and explicit gaps; never execute the selected Python."""
    raw=python_source.encode('utf-8') if type(python_source) is str else python_source
    if type(raw) is not bytes or len(raw)>MAX_BYTES:raise InputDiscoveryError('Python input requires at most 16 MiB')
    try:
        plan=extract(raw.decode('utf-8-sig'))
        analyzer=_Analyzer(plan)
        if plan.get('status')!='available':
            analyzer.unresolved_at('contract',plan.get('reason','Analysis contract unavailable'),{})
        else:
            try:analyzer.block(plan['body'],_Flow())
            except _Limit as error:analyzer.unresolved_at('limit',str(error),{})
        rows=sorted(analyzer.inputs.values(),key=lambda row:(row['kind'],row['program'] or '',row['path']))
        return dict(schema='karel2py.inputs.v1',target=dict(file=str(filename),sha256=hashlib.sha256(raw).hexdigest(),program=plan['program']),
                    complete=not analyzer.unresolved,inputs=rows,unresolved=list(analyzer.unresolved.values()),
                    context_requirements=list(analyzer.contexts.values()),
                    boundary='Source-flow candidates from a checked generated contract only; no target imports/execution, invented values, host callback guarantees or controller proof.')
    except (InputContractError,UnicodeError,KeyError,IndexError,TypeError,ValueError,AttributeError,RecursionError) as error:
        raise InputDiscoveryError(str(error)) from error


def discover_file(path):
    with Path(path).open('rb') as stream:raw=stream.read(MAX_BYTES+1)
    return discover_inputs(raw,filename=str(path))
