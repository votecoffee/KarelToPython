"""Bounded read-before-write discovery from checked generated Python contracts."""
from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path
import re

from .input_contract import extract, InputContractError
from . import runtime as rt


UNKNOWN = object()
MAX_STEPS = 100000
MAX_INPUTS = 2048
MAX_CALL_DEPTH = 32
MAX_FACTS = 32767
MAX_BYTES = 16 * 1024 * 1024
SCALARS = {'INTEGER', 'BYTE', 'SHORT', 'REAL', 'BOOLEAN', 'STRING', 'NUMERIC'}
SCALAR_PURE = {'ABS':1,'ROUND':1,'TRUNC':1,'SQRT':1,'SIN':1,'COS':1,'TAN':1,
               'ASIN':1,'ACOS':1,'ATAN2':2,'EXP':1,'LN':1,'STR_LEN':1,
               'SUB_STR':3,'INDEX':2,'CHR':1,'ORD':2}
PURE = set(SCALAR_PURE) | {'ATAN','LOG','LEN','VEC','POS','FRAME','INV',
        'MIRROR','DOT','CROSS','MAG','UNIT','NORMAL','APPROACH','ORIENT'}


class InputDiscoveryError(ValueError):
    pass


class _Limit(Exception):
    pass


class _ActivationUnknown(Exception):
    pass


class _TaskOrderUnknown(Exception):
    pass


@dataclass(frozen=True)
class _Location:
    kind: str
    owner: str
    root: object
    parts: tuple = ()
    spec: object = field(default=None, compare=False, hash=False)
    root_spec: object = field(default=None, compare=False, hash=False)

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
    facts: object = None


@dataclass(eq=False, frozen=True)
class _Handler:
    plan: dict
    frames: tuple
    clauses: list
    captures: dict


@dataclass(eq=False, frozen=True)
class _Suspension:
    next_statement: int
    flow: '_Flow'


@dataclass
class _Flow:
    defined: set = field(default_factory=set)
    assigned: set = field(default_factory=set)
    maybe: set = field(default_factory=set)
    constants: dict = field(default_factory=dict)
    stopped: bool = False
    opaque: bool = False
    handlers: dict = field(default_factory=dict)
    requested_tasks: set = field(default_factory=set)
    paused_tasks: dict = field(default_factory=dict)
    task_order_unknown: bool = False

    def copy(self):
        return _Flow(self.defined.copy(),self.assigned.copy(),self.maybe.copy(),
                     self.constants.copy(),self.stopped,self.opaque,self.handlers.copy(),
                     self.requested_tasks.copy(),self.paused_tasks.copy(),self.task_order_unknown)

    def take(self, other):
        self.handlers = other.handlers
        self.requested_tasks, self.paused_tasks = other.requested_tasks, other.paused_tasks
        self.task_order_unknown = other.task_order_unknown
        self.defined,self.assigned,self.maybe,self.constants = other.defined,other.assigned,other.maybe,other.constants
        self.stopped,self.opaque = other.stopped,other.opaque


def _merge(flows):
    live = [flow for flow in flows if not flow.stopped]
    if not live:
        result=flows[0].copy();result.stopped=True;return result
    first=live[0]
    constants={key:value for key,value in first.constants.items()
               if all(key in other.constants and type(value) is type(other.constants[key]) and value==other.constants[key] for other in live[1:])}
    handlers = {}
    for flow in live:
        for key, definitions in flow.handlers.items():
            handlers.setdefault(key, {}).update(dict.fromkeys(definitions))
    pauses = {}
    uncertain = any(flow.task_order_unknown for flow in live)
    for flow in live:
        for name, cursor in flow.paused_tasks.items():
            if cursor is not None and any(branch.paused_tasks.get(name) is not cursor for branch in live):
                uncertain = True
            pauses[name] = cursor
    return _Flow(set.intersection(*(flow.defined for flow in live)),
                 set.intersection(*(flow.assigned for flow in live)),
                 set.union(*(flow.maybe for flow in live)),constants,False,any(flow.opaque for flow in live),
                 {key: tuple(definitions) for key, definitions in handlers.items()},
                 set.union(*(flow.requested_tasks for flow in live)),
                 pauses,uncertain)


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
    """Availability/schema facts after storage; narrow casts remain conservative."""
    constant=value.constant;complete=value.complete
    if spec==['REAL'] and type(constant) is int:
        constant=float(constant) if constant.bit_length()<=64 else UNKNOWN
    if spec and spec[0]=='STRING' and type(constant) is str:
        capacity=spec[1] if len(spec)>1 else None
        if type(capacity) is not int or len(constant)>capacity:constant=UNKNOWN
    elif spec and spec[0] in ('INTEGER','BYTE','SHORT') and type(constant) is float:
        if spec==['SHORT'] and math.isfinite(constant) and math.trunc(constant)==32767:complete=False
        constant=UNKNOWN
    if spec==['SHORT'] and constant==32767:complete=False
    if spec==['SHORT'] and value.constant is UNKNOWN and value.spec not in (['SHORT'],['BYTE']):complete=False
    if spec and spec[0]=='ARRAY' and value.spec and value.spec[0]=='ARRAY':
        _,target=_array_dimensions(spec);_,source=_array_dimensions(value.spec)
        if target==['SHORT'] and source!=target:complete=False
    return _Value(constant,complete,spec)


def _merged_value(values,spec=None):
    first=values[0]
    constant=first.constant if all(item.constant is not UNKNOWN and type(item.constant) is type(first.constant) and item.constant==first.constant for item in values) else UNKNOWN
    schema=first.spec if all(item.spec==first.spec for item in values) else spec
    facts=None
    if first.facts is not None and all(item.facts is not None and item.spec==first.spec for item in values):
        facts={key:_merged_value([item.facts.get(key,_Value(complete=False)) for item in values]) for key in first.facts}
    return _Value(constant,all(item.complete for item in values),schema,facts)


class _Analyzer:
    def __init__(self, plan, *, linked_plans=None, track_handlers=False, track_tasks=False):
        self.plan = plan
        self.steps = 0
        self.serial = 0
        self.inputs = {}
        self.unresolved = {}
        self.frames = []
        self.exits = []
        self.contexts = {}
        self.linked_plans = linked_plans
        self.task_roots = (plan['program'],)
        self.suspended_depth = 0
        self.capture_values = {}
        self.track_handlers = track_handlers
        self.saw_handler = False
        self.activation_unknown = False
        self.scanning_handler = False
        self.track_tasks = track_tasks
        self.task_numbers = tuple(linked_plans) if linked_plans is not None else ()
        self.segmentable = {}
        plans = linked_plans if linked_plans is not None else {plan['program']: plan}
        self.imports = {
            name: {local: (owner.upper(), foreign) for local, owner, foreign in item.get('imports', [])}
            for name, item in plans.items()
        }

    @property
    def program(self):
        return self.plan['program']

    def tick(self):
        self.steps+=1
        if self.steps>MAX_STEPS:raise _Limit('Analysis step limit reached')

    def lose_activation_order(self):
        if self.track_handlers:
            if self.saw_handler:
                raise _ActivationUnknown()
            self.activation_unknown = True

    def lose_task_order(self, flow):
        if self.track_tasks and flow.paused_tasks:
            raise _TaskOrderUnknown()
        flow.task_order_unknown = True

    def opaque(self, flow, *, activation=True, task_order=True):
        if activation:
            self.lose_activation_order()
        if task_order:
            self.lose_task_order(flow)
        flow.opaque=True;flow.defined.clear();flow.assigned.clear();flow.constants.clear()

    def context(self, service, address):
        self.contexts.setdefault((service,str(address)),dict(service=service,address=address))

    def where(self, node):
        line=node.get('line',1);file=self.plan.get('filename','<input>');physical=line
        for span in self.plan.get('origins',[]):
            if span['expanded_start']<=line<=span['expanded_end']:
                file=span['file'];physical=span['source_start']+line-span['expanded_start'];break
        location=dict(file=file,line=physical,column=node.get('column',1),
                      routine=self.frames[-1]['name'] if self.frames else None,
                      python_lines=sorted({row['python_line'] for row in self.plan.get('source_map',[]) if row['karel_line']==line}))
        if self.linked_plans is not None:
            location['program']=self.program
        return location

    def unresolved_at(self, code, message, node):
        location=self.where(node);key=(code,message,location.get('program'),location['file'],location['line'],location['column'],location['routine'])
        self.unresolved.setdefault(key,dict(code=code,message=message,location=location))

    def global_slot(self, name, node):
        if name not in self.plan['types']:
            return None
        spec = self.plan['types'][name]
        owner, root = self.program, name
        visited = set()
        while root in self.imports.get(owner, {}):
            self.tick()
            key = owner, root
            if key in visited:
                self.unresolved_at('linked-variable', f'Cyclic imported variable linkage: {owner}.{root}', node)
                return None
            visited.add(key)
            owner, root = self.imports[owner][root]
            if self.linked_plans is None:
                self.unresolved_at('linked-variable', f'Imported variable owner has not been checked: {owner}.{root}', node)
                break
            target = self.linked_plans.get(owner, {})
            if target.get('status') != 'available' or target.get('types', {}).get(root) != spec:
                self.unresolved_at('linked-variable', f'Missing or incompatible imported variable: {owner}.{root}', node)
                return None
        return _Location('variable', owner, root, spec=spec, root_spec=spec)

    def slot(self, name, node):
        if self.frames and name in self.frames[-1]['slots']:
            return self.frames[-1]['slots'][name]
        return self.global_slot(name,node)

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
        return _Location(loc.kind,loc.owner,loc.root,(*loc.parts,(kind,value)),selected,loc.root_spec)

    def locate(self, expr, flow, conditional):
        if not isinstance(expr,dict):return None
        kind=expr.get('kind');args=expr.get('args',[])
        if 'token' in expr:return self.slot(expr['token'],expr)
        if kind=='name':return self.slot(expr['value'],expr)
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

    def read(self, loc, node, flow, conditional, *, partial=False):
        leaves=self.leaves(loc)
        if leaves is None:
            self.unresolved_at('schema','Resource or unsupported value read: '+loc.path,node)
            return _Value(complete=False,spec=loc.spec)
        keys={leaf.key for leaf in leaves}
        missing=keys-flow.defined
        partial_copy=partial and loc.spec and loc.spec[0] not in SCALARS
        if missing:
            initial=missing-flow.assigned
            if not initial:
                if not partial_copy:self.unresolved_at('derived-value','Read follows a write whose complete value is not proven: '+loc.path,node)
            elif loc.kind=='local':
                if not partial_copy:self.unresolved_at('local-value','Fresh routine-local value is read before initialization: '+loc.path,node)
            else:
                uncertain=conditional or flow.opaque or bool(missing & flow.maybe)
                key=loc.key;certainty='conditional' if uncertain else 'required'
                if key not in self.inputs:
                    if len(self.inputs)>=MAX_INPUTS:raise _Limit('Analysis input limit reached')
                    spec=None if loc.spec==['NUMERIC'] else loc.spec
                    self.inputs[key]=dict(kind=loc.kind,program=loc.owner or None,path=loc.path,type=spec,
                                          certainty=certainty,locations=[],reason='Read before a definite source write')
                    if loc.kind=='variable':
                        self.inputs[key].update(root_path=str(loc.root),root_type=loc.root_spec,selectors=list(loc.parts))
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
        facts=None
        if loc.spec and loc.spec[0] not in SCALARS:
            facts={leaf.parts[len(loc.parts):]:_Value(flow.constants.get(leaf.key,UNKNOWN) if leaf.key in flow.defined else UNKNOWN,
                leaf.key in flow.defined,leaf.spec) for leaf in leaves}
        return _Value(flow.constants.get(loc.key,UNKNOWN) if loc.key in flow.defined else UNKNOWN,complete,loc.spec,facts)

    def copy_requires_complete(self,target,source):
        self.tick()
        if not source or target==source:return False
        if target[0]=='ARRAY' and source[0]=='ARRAY':
            return self.copy_requires_complete(_array_dimensions(target)[1],_array_dimensions(source)[1])
        if target[0] in SCALARS or source[0] in SCALARS:return not (target[0] in SCALARS and source[0] in SCALARS)
        if target[0] in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS') or source[0] in ('POSITION','XYZWPR','XYZWPREXT','JOINTPOS'):return True
        fields=lambda spec:dict(spec[2]) if spec[0]=='STRUCTURE' else self.plan.get('record_fields',{}).get(spec[0])
        first,second=fields(target),fields(source)
        if first is None or second is None or first.keys()!=second.keys():return True
        return any(self.copy_requires_complete(spec,second[name]) for name,spec in first.items())

    def stored(self,loc,value,leaves,node):
        stored=_stored_value(loc.spec,value)
        if not value.complete and self.copy_requires_complete(loc.spec,value.spec):
            self.unresolved_at('conversion-value','Converted value requires complete source data: '+loc.path,node)
            return _Value(complete=False,spec=loc.spec)
        if value.facts is None or loc.spec[0] in SCALARS or leaves is None:return stored
        facts={}
        for leaf in leaves:
            key=leaf.parts[len(loc.parts):]
            fact=_stored_value(leaf.spec,value.facts.get(key,_Value(complete=value.complete)))
            if value.spec!=loc.spec:fact.constant=UNKNOWN
            facts[key]=fact
        return _Value(stored.constant,all(fact.complete for fact in facts.values()),loc.spec,facts)

    def write(self, loc, value, flow, node, *, definite=True):
        if loc is None:
            self.unresolved_at('write-target','Writable target is not statically resolved',node);return
        leaves=self.leaves(loc)
        if leaves is None:
            self.unresolved_at('schema','Resource or unsupported write: '+loc.path,node);return
        stored=self.stored(loc,value,leaves,node)
        for leaf in leaves:
            key=leaf.key;flow.maybe.add(key);flow.constants.pop(key,None)
            fact=stored.facts.get(leaf.parts[len(loc.parts):],_Value(complete=False)) if stored.facts is not None else stored
            if not fact.complete:flow.defined.discard(key)
            if definite:
                if not flow.opaque:flow.assigned.add(key)
                flow.defined.discard(key)
                if fact.complete and not flow.opaque:flow.defined.add(key)
                if fact.constant is not UNKNOWN and not flow.opaque:flow.constants[key]=fact.constant
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

    def result_value(self,value,node,partial):
        if not partial and value.spec and value.spec[0] not in SCALARS and not value.complete:
            self.unresolved_at('derived-value','Aggregate result consumed without proven complete data',node)
        return value

    def expr(self, node, flow, conditional=False, *, partial=False):
        self.tick()
        if not isinstance(node,dict):return _Value()
        kind=node.get('kind');args=node.get('args',[]);value=node.get('value')
        if kind=='literal':return _Value(value)
        if kind=='wait_sample':return value
        if kind=='real_literal':
            try:return _Value(float(value))
            except ValueError:return _Value()
        if kind=='predefined':return _Value({'ON':True,'OFF':False,'MININT':-2147483648,'MAXINT':2147483647}.get(value,UNKNOWN))
        if kind=='name':
            loc=self.slot(value,node)
            if loc:return self.read(loc,node,flow,conditional,partial=partial)
            constant=self.constant(value)
            if constant is not UNKNOWN:return _Value(constant)
            if value in self.plan['routines']:return self.result_value(self.call(dict(node,kind='call',args=[]),flow,conditional),node,partial)
        if kind in ('field','index'):
            loc=self.locate(node,flow,conditional)
            if loc:return self.read(loc,node,flow,conditional,partial=partial)
            self.unresolved_at('selection','Computed or dynamic data read is unresolved',node);return _Value(complete=False)
        if kind=='group':return self.expr(args[0],flow,conditional,partial=partial)
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
        if kind=='call':return self.result_value(self.call(node,flow,conditional),node,partial)
        if self.linked_plans is not None and kind=='captured':
            name, spec = value
            captured = self.capture_values.get((self.program, name))
            if captured is not None:
                return _Value(captured.constant, captured.complete, spec, captured.facts)
            self.unresolved_at('condition-capture', 'EVAL source is unavailable; re-translate for capture discovery', node)
            return _Value(complete=False, spec=spec)
        if self.linked_plans is not None and kind=='motion_event':
            return _Value(spec=['BOOLEAN'])
        if kind == 'program_pause':
            self.expr(args[0], flow, conditional)
            self.context('tasks', None)
            self.unresolved_at('condition-source', 'Pause delivery depends on registered task execution', node)
            return _Value(spec=['BOOLEAN'])
        if self.linked_plans is not None and kind in ('event', 'semaphore', 'edge', 'error_condition', 'task_event'):
            for item in args:
                self.expr(item, flow, conditional)
            self.unresolved_at('condition-source', 'Runtime condition state requires review: '+kind, node)
            return _Value(spec=['BOOLEAN'])
        if kind in ('write_item','read_item','eval'):
            values=[self.expr(item,flow,conditional) for item in args]
            return values[0] if values else _Value()
        if kind=='write_cr':return _Value()
        self.unresolved_at('expression','Expression form requires further analysis: '+str(kind),node)
        for item in args:
            if isinstance(item,dict):self.expr(item,flow,True)
        return _Value(complete=False)

    def scalar_call(self, node, flow, conditional):
        """Fold only bounded known scalars through the translator's pure helpers."""
        name=node['value'];values=[]
        for item in node['args']:
            if flow.stopped and not flow.opaque:return _Value(complete=False)
            values.append(self.expr(item,flow,conditional))
        if len(values)!=SCALAR_PURE[name]:
            self.unresolved_at('scalar-call','Invalid checked scalar builtin arity: '+name,node)
            return _Value(complete=False)
        complete=all(value.complete for value in values) and not flow.stopped
        known=[value.constant for value in values]
        if not complete or any(value is UNKNOWN for value in known):return _Value(complete=complete)
        if any(type(value) not in (bool,int,float,str) or type(value) is int and value.bit_length()>64
               or type(value) is str and len(value)>254 for value in known):return _Value()
        try:
            with rt._numeric_scope('pythonic'):result=rt.builtin(name,known,node.get('line'))
            if type(result) not in (int,float,str) or type(result) is float and not math.isfinite(result):
                raise ValueError('Expected a finite scalar result')
        except (rt.KarelRuntimeError,ArithmeticError,ValueError,TypeError) as error:
            self.unresolved_at('scalar-call','Checked scalar builtin cannot be evaluated: '+name+': '+str(error),node)
            return _Value(complete=False)
        spec=['STRING',254] if type(result) is str else ['REAL'] if type(result) is float else ['INTEGER']
        return _Value(result,spec=spec)

    def call(self, node, flow, conditional):
        name=node['value'];args=node['args']
        if name in self.plan['routines']:return self.routine(name,args,node,flow,conditional)
        if name in ('UNINIT','ARRAY_LEN'):
            target=args[0] if args else {};spec=None
            while target.get('kind')=='group':target=target['args'][0]
            if target.get('kind') in ('name','field','index'):
                loc=self.locate(target,flow,conditional);spec=loc.spec if loc else None
            elif args:spec=self.expr(target,flow,conditional,partial=True).spec
            values=[self.expr(item,flow,conditional) for item in args[1:]]
            if name=='ARRAY_LEN' and spec and spec[0]=='ARRAY':
                dimensions,_=_array_dimensions(spec)
                dimension=values[0].constant if values else 1
                if type(dimension) is int and 1<=dimension<=len(dimensions):
                    size=dimensions[dimension-1]
                    if type(size) is int:return _Value(size,spec=['INTEGER'])
            return _Value(spec=['BOOLEAN'] if name=='UNINIT' else ['INTEGER'])
        if name in SCALAR_PURE:return self.scalar_call(node,flow,conditional)
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
        if self.linked_plans is not None and name in ('RUN_TASK', 'CONT_TASK'):
            parked = self.task_request(name, known, node, flow)
            for _, loc in outputs:
                self.write(loc, _Value(), flow, node, definite=parked)
            return _Value()
        if name in ('GET_VAR','SET_VAR'):
            owner,path=known[1:3]
            loc=None
            if type(owner) is str and owner.upper() in ('',self.program) and type(path) is str:
                match=re.match(r'[A-Za-z_][A-Za-z_0-9]*',path)
                if match and match[0].upper() in self.plan['types']:
                    loc=self.global_slot(match[0].upper(),node)
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
            else:
                self.unresolved_at('variable-path','GET_VAR/SET_VAR requires a known own-program static data path',node)
                if name=='SET_VAR':
                    self.lose_task_order(flow)
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

    def task_target(self, operation, target, node):
        if type(target) is not str:
            self.unresolved_at('task-target', operation+' target is dynamic', node)
            return None
        name = target.upper()
        plan = self.linked_plans.get(name) if target.isascii() else None
        if plan is None or plan.get('status') != 'available':
            self.unresolved_at('task-target', operation+' target has no checked pinned body: '+name, node)
            return None
        if name in self.task_roots or self.suspended_depth + len(self.frames) + 1 >= MAX_CALL_DEPTH:
            self.unresolved_at('task-target', 'Recursive or deeply nested '+operation+' target: '+name, node)
            return None
        return plan

    def task_request(self, operation, values, node, flow):
        plan = self.task_target(operation, values[0], node)
        if plan is None:
            self.opaque(flow)
            return False
        name = plan['program']
        if operation != 'RUN_TASK':
            return self.continue_task(operation, plan, node, flow)

        hint, pause, motion, mask = values[1:5]
        checked_request = (self.track_tasks and not flow.task_order_unknown and type(hint) is int and hint >= 0
                           and type(pause) is bool and motion is False and type(mask) is int and mask == 0)
        fresh = checked_request and name not in flow.requested_tasks
        flow.requested_tasks.add(name)
        if fresh and pause and plan.get('entry_checkpoint') is True:
            flow.paused_tasks[name] = None
            self.unresolved_at('task-scheduling', 'Paused entry for '+name+' depends on scheduler admission', node)
            return True
        if name in flow.paused_tasks:
            return self.continue_task(operation, plan, node, flow, segment=checked_request)

        self.unresolved_at('task-scheduling', 'RUN_TASK timing, admission and shared effects require review: '+name, node)
        return self.start_task_body(plan, flow, segment=fresh and pause is False)

    def continue_task(self, operation, plan, node, flow, *, segment=True):
        name = plan['program']
        if name not in flow.paused_tasks or flow.task_order_unknown:
            self.unresolved_at('task-continuation', operation+' depends on a live suspended frame: '+name, node)
            self.opaque(flow)
            return False

        suspension = flow.paused_tasks.pop(name)
        point = 'a paused entry' if suspension is None else 'an explicit in-body pause'
        self.unresolved_at('task-continuation', operation+' may resume '+point+' after scheduler admission: '+name, node)
        return self.start_task_body(plan, flow, suspension, segment=segment)

    def segmentable_body(self, plan):
        """Check for a top-level pause and operations confined to private scalar storage."""
        name = plan['program']
        if name in self.segmentable:
            return self.segmentable[name]
        self.segmentable[name] = False
        if plan.get('imports') != [] or not any(node['kind'] == 'task_control' and node['args'] == ['PAUSE'] for node in plan['body']):
            return False
        for other in self.linked_plans.values():
            self.tick()
            imports, routines = other.get('imports'), other.get('routines')
            if (other.get('status') != 'available' or type(imports) is not list or type(routines) is not dict
                    or any(owner.upper() == name for _, owner, _ in imports)
                    or any((routine['external'] or '').upper() == name for routine in routines.values())):
                return False

        def scalar(node):
            self.tick()
            kind = node['kind']
            if kind == 'name':
                variable = node['value']
                schema = plan['types'].get(variable)
                return schema[0] in SCALARS if schema else variable in plan['constants']
            if kind in ('literal', 'real_literal', 'predefined', 'write_cr'):
                return True
            return kind in ('group', 'unary', 'binary', 'write_item') and all(scalar(arg) for arg in node['args'])

        def safe(node, *, top=False):
            self.tick()
            kind, args = node['kind'], node['args']
            if kind == 'task_control':
                return top and args == ['PAUSE']
            if kind == 'assign':
                target, value = args
                return target['kind'] == 'name' and scalar(target) and scalar(value)
            if kind == 'if':
                return scalar(args[0]) and all(safe(row) for row in (*node['body'], *node['alternate']))
            return kind in ('write_items', 'signal_event') and all(scalar(arg) for arg in args)

        self.segmentable[name] = all(safe(node, top=True) for node in plan['body'])
        return self.segmentable[name]

    def start_task_body(self, plan, flow, suspension=None, *, segment):
        if segment and self.segmentable_body(plan):
            cursor = self.scheduled_body(plan, segment=True, suspension=suspension)
            if cursor is not None:
                flow.paused_tasks[plan['program']] = cursor
            return True
        if suspension is not None:
            # Revisit previous slices as well when the original cursor no
            # longer establishes which portion may run.
            raise _TaskOrderUnknown()
        self.opaque(flow)
        self.scheduled_body(plan)
        return False

    def scheduled_body(self, plan, *, segment=False, suspension=None):
        depth = self.suspended_depth + len(self.frames) + 1
        caller_plan, caller_roots, caller_depth = self.plan, self.task_roots, self.suspended_depth
        caller_frames, caller_exits, caller_values = self.frames, self.exits, self.capture_values
        self.plan, self.task_roots, self.suspended_depth = plan, (*caller_roots, plan['program']), depth
        self.frames, self.exits, self.capture_values = [], [], {}
        try:
            if not segment:
                self.block(plan['body'], _Flow(task_order_unknown=True), True)
                return None
            child = suspension.flow.copy() if suspension is not None else _Flow()
            start = suspension.next_statement if suspension is not None else 0
            for index in range(start, len(plan['body'])):
                node = plan['body'][index]
                if node['kind'] == 'task_control' and node['args'] == ['PAUSE']:
                    self.tick()
                    return _Suspension(index + 1, child)
                self.statement(node, child, True)
            return None
        finally:
            self.plan, self.task_roots, self.suspended_depth = caller_plan, caller_roots, caller_depth
            self.frames, self.exits, self.capture_values = caller_frames, caller_exits, caller_values

    def routine_target(self, name, interface):
        owner = interface['external']
        if not owner:
            return self.plan, interface
        if self.linked_plans is None:
            return None, None
        target = self.linked_plans.get(owner.upper(), {})
        routine = target.get('routines', {}).get(name)
        if (target.get('status') != 'available' or routine is None or routine['external'] or
                routine['result'] != interface['result'] or
                [spec for _, spec in routine['parameters']] != [spec for _, spec in interface['parameters']]):
            return None, None
        return target, routine

    def routine(self, name, args, node, flow, conditional):
        routine=self.plan['routines'][name]
        modes=node.get('passing',[]);actual=[]
        for index,item in enumerate(args):
            mode=modes[index] if index<len(modes) else 'unknown'
            if mode=='reference':actual.append(self.locate(item,flow,conditional))
            elif mode=='value':actual.append(self.expr(item,flow,conditional,partial=True))
            else:
                self.unresolved_at('argument','Routine passing mode is unresolved: '+name,node)
                actual.append(self.expr(item,flow,conditional))
        target_plan, target_routine = self.routine_target(name, routine)
        routine_key = (target_plan['program'], name) if target_plan else None
        if (target_routine is None or any(frame['key'] == routine_key for frame in self.frames)
                or self.suspended_depth + len(self.frames) >= MAX_CALL_DEPTH):
            qualified = (routine['external'] or self.program) + '.' + name
            self.unresolved_at('routine', 'External or recursive routine effects are unresolved: '+qualified, node)
            for item in actual:
                if isinstance(item,_Location):self.read(item,node,flow,True)
            self.opaque(flow);return _Value(complete=False)
        external = bool(routine['external'])
        routine = target_routine
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
        frame=dict(name=name,key=routine_key,slots={key:_Location('local',owner,key,spec=spec) for key,spec in routine['types'].items()},
                   constants=routine['constants'])
        for formal,spec,item,resolved in bindings:
            if isinstance(item,_Location):frame['slots'][formal]=item
            else:
                if spec==['STRING',None]:resolved=['STRING',254]
                loc=_Location('local',owner,formal,spec=resolved);frame['slots'][formal]=loc
                self.write(loc,item or _Value(complete=False),flow,node)
        old_exits, self.exits = self.exits, []
        caller_plan, self.plan = self.plan, target_plan
        caller_handlers = flow.handlers if external else None
        if external:
            # A linked invocation borrows module globals, but gets a new
            # runtime state and its own condition registrations.
            flow.handlers = {}
        self.frames.append(frame)
        try:
            self.block(routine['body'],flow,conditional)
            exits=self.exits[:]
            if not flow.stopped and routine['result'] is None:exits.append((flow.copy(),_Value()))
        finally:
            self.frames.pop()
            self.exits = old_exits
            self.plan = caller_plan
            if caller_handlers is not None:
                flow.handlers = caller_handlers
        if not exits:
            flow.stopped=True;return _Value(complete=False)
        merged=_merge([item[0] for item in exits])
        if caller_handlers is not None:
            merged.handlers = caller_handlers
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
                else:
                    loc=_Location('local','@result',name,spec=schema)
                    converted.append(self.stored(loc,value,self.leaves(loc) if value.facts is not None else None,node))
            values=converted
        return _merged_value(values,result)

    def legacy_capture(self, value, kind):
        self.tick()
        if isinstance(value, dict):
            if value.get('kind') == kind:
                return value
            if value.get('kind') != 'motion':
                return self.legacy_capture(list(value.values()), kind)
        if isinstance(value, list):
            for item in value:
                captured = self.legacy_capture(item, kind)
                if captured is not None:
                    return captured
        return None

    def capture_gap(self, clause, flow, kind, code, message):
        missing = self.legacy_capture(clause, kind)
        if missing is not None:
            self.unresolved_at(code, message, missing)
            self.opaque(flow)

    def capture_callbacks(self, clauses, flow, conditional, *, motion=False):
        previous, self.capture_values = self.capture_values, {}
        try:
            for clause in clauses:
                if 'captures' in clause:
                    for name, operand in clause['captures']:
                        self.capture_values[self.program, name] = self.expr(operand, flow, conditional)
                else:
                    self.capture_gap(clause, flow, 'captured', 'condition-capture',
                                     'EVAL source is unavailable; re-translate for capture discovery')
                if motion:
                    if 'selectors' in clause:
                        for operand in clause['selectors']:
                            self.expr(operand, flow, conditional)
                    else:
                        self.capture_gap(clause, flow, 'motion_event', 'motion-selector',
                                         'Motion selector operands are unavailable; re-translate for capture discovery')
            return self.capture_values
        finally:
            self.capture_values = previous

    def scan_callbacks(self, clauses, captures, scan, *, motion=False):
        previous, self.capture_values = self.capture_values, captures
        try:
            # Later motion scans may see changes from other clauses. Analyze
            # each clause independently without borrowing mutable constants.
            for clause in clauses:
                active = scan.copy() if motion else scan
                matched = self.expr(clause['args'][0], active, True).constant
                if active.stopped:
                    if motion:
                        continue
                    break
                if matched is not False:
                    self.block(clause['body'], active.copy(), True)
                if matched is True and (not motion or clause.get('trigger') == 'UNTIL'):
                    break
        finally:
            self.capture_values = previous

    def condition(self, node, flow, conditional):
        number, options = node['args']
        identifier = self.expr(number, flow, conditional).constant
        for _, option in options:
            self.expr(option, flow, conditional)
        clauses = node['body']
        captures = self.capture_callbacks(clauses, flow, conditional)
        if not self.track_handlers:
            self.unresolved_at('condition-scan', 'Condition activation order and scan effects require review', node)
            self.scan_callbacks(clauses, captures, _Flow())
            return
        if (self.activation_unknown or self.scanning_handler or type(identifier) is not int
                or not 1 <= identifier <= 1000 or identifier in flow.handlers):
            raise _ActivationUnknown()
        self.saw_handler = True
        flow.handlers[identifier] = (_Handler(self.plan, tuple(self.frames), clauses, captures),)

    def condition_control(self, node, flow, conditional):
        action, number = node['args']
        identifier = self.expr(number, flow, conditional).constant
        if not self.track_handlers:
            if action == 'ENABLE':
                self.unresolved_at('condition-scan', 'Enabling a condition may run its callbacks at later checkpoints', node)
                self.opaque(flow)
            return
        if self.scanning_handler or type(identifier) is not int:
            self.lose_activation_order()
            return
        if action == 'PURGE':
            flow.handlers.pop(identifier, None)
            return
        if action != 'ENABLE' or identifier not in flow.handlers:
            return
        self.unresolved_at('condition-scan', 'Enabled condition may run at later checkpoints: '+str(identifier), node)
        caller_plan, caller_frames = self.plan, self.frames
        self.scanning_handler = True
        try:
            for definition in flow.handlers[identifier]:
                self.tick()
                self.plan, self.frames = definition.plan, list(definition.frames)
                scan = _Flow(defined=flow.defined.copy(), assigned=flow.assigned.copy())
                self.scan_callbacks(definition.clauses, definition.captures, scan)
        finally:
            self.scanning_handler = False
            self.plan, self.frames = caller_plan, caller_frames
        # The checkpoint may run later, so a handler write cannot become
        # a definite write in its caller's continuing flow.
        self.opaque(flow, activation=False)

    def motion(self, node, flow, conditional):
        args = node['args']
        self.context('motion', None)
        self.context('group_locks', None)
        if node['kind'] == 'motion':
            operation, operands, _, settings = args
            for _, group, value in settings:
                if group is not None:
                    self.expr(group, flow, conditional)
                self.expr(value, flow, conditional)
            for operand in operands:
                if operand['kind'] == 'motion_range':
                    for part in operand['args']:
                        self.expr(part, flow, conditional)
                else:
                    self.expr(operand, flow, conditional)
            if node['body']:
                clauses = node['body']
                captures = self.capture_callbacks(clauses, flow, conditional, motion=True)
                scan = _Flow(defined=flow.defined.copy(), assigned=flow.assigned.copy())
                self.scan_callbacks(clauses, captures, scan, motion=True)
            self.unresolved_at('motion-progress',
                               'Motion admission, progress and local callback effects require review: '+operation, node)
            self.opaque(flow)
        else:
            operands = (args[1] or ()) if node['kind'] == 'motion_control' else args[1:]
            for operand in operands:
                self.expr(operand, flow, conditional)
            self.unresolved_at('motion-control', 'Motion control depends on offline group state: '+args[0], node)

    def block(self, body, flow, conditional=False):
        exits_before_block = len(self.exits)
        for node in body:
            if flow.stopped and not flow.opaque:break
            after_program_return = not self.frames and len(self.exits) > exits_before_block
            self.statement(node, flow, conditional or after_program_return)

    def sample_wait_inputs(self, node, flow, conditional, kinds):
        if not isinstance(node, dict):
            return node
        original = node.get('args', ())
        args = [self.sample_wait_inputs(arg, flow, conditional, kinds) for arg in original]
        kind = node.get('kind')
        if kind not in kinds:
            return dict(node, args=args) if any(a is not b for a, b in zip(args, original)) else node
        value = self.expr(args[0], flow, conditional, partial=kind == 'wait_eval') if args else _Value()
        if kind == 'wait_edge':
            self.context('ports', None)
            self.unresolved_at('condition-source', 'Port transitions require offline samples', node)
            value = _Value(spec=['BOOLEAN'])
        elif kind == 'wait_pause':
            if args[0] is not None:
                self.context('tasks', None)
            self.unresolved_at('condition-source', 'Pause delivery depends on task execution', node)
            value = _Value(spec=['BOOLEAN'])
        elif kind in ('wait_error', 'wait_lifecycle'):
            if kind == 'wait_error':
                self.context('errors', None)
            self.unresolved_at('condition-source', 'WAIT notification delivery depends on task execution', node)
            value = _Value(spec=['BOOLEAN'])
        return dict(node, kind='wait_sample', value=value, args=[])

    def statement(self, node, flow, conditional):
        self.tick();kind=node['kind'];args=node['args']
        if flow.task_order_unknown and flow.paused_tasks:
            self.lose_task_order(flow)
        if kind=='assign':
            value=self.expr(args[1],flow,conditional,partial=True)
            self.write(self.locate(args[0],flow,conditional),value,flow,node);return
        if kind=='call':self.expr(args[0],flow,conditional);return
        if kind == 'wait':
            captured = self.sample_wait_inputs(args[0], flow, conditional, ('wait_eval',))
            predicate = self.sample_wait_inputs(captured, flow, conditional,
                                                ('wait_edge', 'wait_pause', 'wait_error', 'wait_lifecycle'))
            if predicate is not args[0]:
                self.expr(predicate, flow, conditional)
                self.unresolved_at('task-wait', 'Waiting and possible task effects require an execution order', node)
                self.opaque(flow)
                return
        if self.linked_plans is not None:
            if kind in ('motion', 'motion_action', 'motion_control'):
                self.motion(node, flow, conditional)
                return
            if kind == 'condition':
                self.condition(node, flow, conditional)
                return
            if kind == 'condition_control':
                self.condition_control(node, flow, conditional)
                return
            if kind == 'task_control' and len(args) > 1 and args[0] in ('CONTINUE', 'RESUME', 'UNPAUSE'):
                number = self.expr(args[1], flow, conditional).constant
                static = not flow.task_order_unknown and type(number) is int and 1 <= number <= len(self.task_numbers)
                target = self.task_numbers[number - 1] if static else None
                self.task_request(args[0]+' PROGRAM', [target], node, flow)
                return
            if kind in ('signal_event', 'signal_semaphore'):
                self.expr(args[0], flow, conditional)
                self.unresolved_at('task-signal', 'Signal delivery and consuming tasks require execution order', node)
                return
            if kind in ('wait', 'delay'):
                self.expr(args[0], flow, conditional)
                self.unresolved_at('task-wait', 'Waiting and possible task effects require an execution order', node)
                independent = kind == 'delay' or (args[0]['kind'] == 'event'
                               and args[0]['args'][0]['kind'] in ('literal', 'name'))
                if not (independent and flow.paused_tasks and not flow.task_order_unknown):
                    self.opaque(flow, activation=False, task_order=not independent)
                return
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
            self.lose_activation_order()
            self.lose_task_order(flow)
            before=flow.copy();body=flow.copy();body.constants.clear()
            self.block(node['body'],body,True)
            if not body.stopped:self.expr(args[0],body,True)
            flow.take(_merge([before,body]));return
        if kind=='repeat':
            self.lose_activation_order()
            self.lose_task_order(flow)
            exits_before_body = len(self.exits)
            flow.constants.clear();self.block(node['body'],flow,conditional)
            if not flow.stopped:
                after_program_return = not self.frames and len(self.exits) > exits_before_body
                self.expr(args[0], flow, conditional or after_program_return)
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
            # The emitted iterator reads the captured counter after final-bound effects.
            start=UNKNOWN
            if loc and not flow.stopped:
                if loc.key in flow.defined:start=flow.constants.get(loc.key,UNKNOWN)
                else:self.unresolved_at('for-start','Captured counter is not proven initialized after final-bound evaluation: '+loc.path,node)
            step=-1 if args[3]=='DOWNTO' else 1
            if type(start) is int and type(final.constant) is int:
                count=max(0,(final.constant-start)*step+1)
            else:count=None
            if count is not None and count<=32:
                for index in range(count):
                    if flow.stopped:break
                    self.write(loc,_Value(start+step*index),flow,node)
                    after_program_return = not self.frames and len(self.exits) > exit_start
                    self.block(node['body'], flow, conditional or after_program_return)
            else:
                self.lose_activation_order()
                self.lose_task_order(flow)
                before=flow.copy();body=flow.copy();body.constants.clear()
                self.block(node['body'],body,True);flow.take(_merge([before,body]))
            if loc:
                self.write(loc,_Value(complete=False),flow,node)
                for exited,_ in self.exits[exit_start:]:self.write(loc,_Value(complete=False),exited,node)
            return
        if kind=='return':
            value=self.expr(args[0],flow,conditional,partial=True) if args and args[0] is not None else _Value()
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


def analyze_plan(plan, target, *, linked_plans=None):
    track_handlers = track_tasks = linked_plans is not None
    # Restart from the checked entry when control uncertainty could hide
    # callbacks or child bodies that a precise pass had left dormant.
    while True:
        try:
            return _analyze_plan(plan, target, linked_plans=linked_plans,
                                 track_handlers=track_handlers, track_tasks=track_tasks)
        except _ActivationUnknown:
            track_handlers = False
        except _TaskOrderUnknown:
            track_tasks = False


def _analyze_plan(plan, target, *, linked_plans, track_handlers, track_tasks):
    analyzer = _Analyzer(plan, linked_plans=linked_plans, track_handlers=track_handlers, track_tasks=track_tasks)
    modules = linked_plans.values() if linked_plans is not None else (plan,)
    for module in modules:
        if module.get('status') != 'available':
            analyzer.plan = module
            analyzer.unresolved_at('contract', module.get('reason', 'Analysis contract unavailable'), {})
    analyzer.plan = plan
    if plan.get('status') == 'available':
        try:
            flow = _Flow()
            analyzer.block(plan['body'], flow)
            if flow.task_order_unknown and flow.paused_tasks:
                analyzer.lose_task_order(flow)
        except _Limit as error:
            analyzer.unresolved_at('limit', str(error), {})
    rows = sorted(analyzer.inputs.values(), key=lambda row: (row['kind'], row['program'] or '', row['path']))
    return dict(schema='karel2py.inputs.v1', target=target, complete=not analyzer.unresolved,
                inputs=rows, unresolved=list(analyzer.unresolved.values()),
                context_requirements=list(analyzer.contexts.values()),
                boundary=('Source-flow candidates from a checked generated contract only; '
                          'no target imports/execution, invented values, host callback guarantees or controller proof.'))


def discover_inputs(python_source, *, filename='<python>'):
    """Return candidates and explicit gaps; never execute the selected Python."""
    raw=python_source.encode('utf-8') if type(python_source) is str else python_source
    if type(raw) is not bytes or len(raw)>MAX_BYTES:raise InputDiscoveryError('Python input requires at most 16 MiB')
    try:
        plan=extract(raw.decode('utf-8-sig'))
        target=dict(file=str(filename),sha256=hashlib.sha256(raw).hexdigest(),program=plan['program'])
        return analyze_plan(plan,target)
    except (InputContractError,UnicodeError,KeyError,IndexError,TypeError,ValueError,AttributeError,RecursionError) as error:
        raise InputDiscoveryError(str(error)) from error


def discover_file(path):
    with Path(path).open('rb') as stream:raw=stream.read(MAX_BYTES+1)
    return discover_inputs(raw,filename=str(path))
