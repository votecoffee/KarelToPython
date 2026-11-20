"""Bounded read-before-write discovery from checked generated Python contracts."""
from dataclasses import dataclass, field, replace
import hashlib
import math
from pathlib import Path
import re

from .extended import PREDEFINED_FILE_NAMES, ZERO_BASED_PORTS, path_conversion_layout, path_node_size
from .input_contract import extract, InputContractError
from .storage import tuple_spec
from . import runtime as rt


UNKNOWN = object()
DEFAULT_EMPTY_PATH = object()
MAX_STEPS = 100000
MAX_INPUTS = 2048
MAX_CALL_DEPTH = 32
MAX_FACTS = 32767
MAX_PATH_IO_FIELDS = 1024
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
class _PathNodeSlot:
    path: '_Location'
    position: int
    generation: int

    @property
    def key(self):
        return self.generation, self.position


@dataclass(frozen=True)
class _Location:
    kind: str
    owner: str
    root: object
    parts: tuple = ()
    spec: object = field(default=None, compare=False, hash=False)
    root_spec: object = field(default=None, compare=False, hash=False)
    node_slot: _PathNodeSlot | None = field(default=None, compare=False, hash=False)

    @property
    def key(self):
        return self.kind, self.owner, self.root, self.parts

    @property
    def path(self):
        text = str(self.root)
        for kind, value in self.parts:
            text += ('.' + value if kind == 'field' else
                     '[group=' + (str(value) if value is not None else 'caller-default') + ']' if kind=='group'
                     else '[' + kind.replace('created-', 'source-created ') + ']' if kind in ('created-node', 'created-header')
                     else '[' + str(value) + ']')
        return text


@dataclass
class _Value:
    constant: object = UNKNOWN
    complete: bool = True
    spec: object = None
    facts: object = None
    path_records: tuple | None = None


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


@dataclass(frozen=True)
class _PathOrder:
    """Current record order and the identities kept by detached references."""

    nodes: tuple
    header: int | None = None
    detached: frozenset[int] = frozenset()
    generation: int = 0
    retired_slots: dict = field(default_factory=dict)
    previous_max_size: int = 0

    def retains_slot(self, slot):
        if slot.generation != self.generation:
            return slot.key in self.retired_slots
        # A successfully captured list position can be temporarily vacant.
        return 1 <= slot.position <= max(len(self.nodes), self.previous_max_size)

    def slot_origin(self, slot):
        if slot.generation != self.generation:
            return self.retired_slots.get(slot.key)
        return self.nodes[slot.position - 1] if 1 <= slot.position <= len(self.nodes) else None


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
    path_shape_unknown: bool = False
    # Original node indexes are positive; source-created nodes use negative
    # identities. None marks a receiver with uncertain order.
    path_orders: dict = field(default_factory=dict)

    def copy(self):
        return _Flow(self.defined.copy(),self.assigned.copy(),self.maybe.copy(),
                     self.constants.copy(),self.stopped,self.opaque,self.handlers.copy(),
                     self.requested_tasks.copy(),self.paused_tasks.copy(),self.task_order_unknown,
                     self.path_shape_unknown,self.path_orders.copy())

    def take(self, other):
        self.handlers = other.handlers
        self.requested_tasks, self.paused_tasks = other.requested_tasks, other.paused_tasks
        self.task_order_unknown = other.task_order_unknown
        self.path_shape_unknown, self.path_orders = other.path_shape_unknown, other.path_orders
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
    path_orders = {}
    for key in set().union(*(flow.path_orders for flow in live)):
        order = first.path_orders.get(key)
        path_orders[key] = order if all(flow.path_orders.get(key) == order for flow in live) else None
    return _Flow(set.intersection(*(flow.defined for flow in live)),
                 set.intersection(*(flow.assigned for flow in live)),
                 set.union(*(flow.maybe for flow in live)),constants,False,any(flow.opaque for flow in live),
                 {key: tuple(definitions) for key, definitions in handlers.items()},
                 set.union(*(flow.requested_tasks for flow in live)),
                 pauses,uncertain,any(flow.path_shape_unknown for flow in live),path_orders)


def _path_record_identity(part):
    kind, index = part
    if kind in ('created-node', 'created-header'):
        return -index
    if kind == 'index' and index >= 0:
        return index
    return None


def _path_header_part(part):
    return part[0] == 'created-header' or part == ('index', 0)


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
    path_records = None
    if first.path_records is not None and all(
        item.spec == first.spec and item.path_records is not None
        and len(item.path_records) == len(first.path_records) for item in values
    ):
        path_records = tuple(_merged_value(records) for records in zip(*(item.path_records for item in values)))
    return _Value(constant,all(item.complete for item in values),schema,facts,path_records)


class _Analyzer:
    def __init__(self, plan, *, linked_plans=None, track_handlers=False, track_tasks=False,
                 saved_path_count=None):
        self.plan = plan
        # A linked fallback pass has lost handler or task ordering. Its flow
        # still supplies approximate candidates, but cannot prove seed topology.
        self.saved_path_count = saved_path_count if linked_plans is None or track_handlers and track_tasks else None
        self.path_storage = {}
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
        self.repeat_depth = 0
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

    def tick(self, steps=1):
        self.steps += steps
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
        flow.path_orders = dict.fromkeys(flow.path_orders)

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

    def slot(self, name, node, flow, *, capture_node=False):
        if not self.frames or name not in self.frames[-1]['slots']:
            return self.global_slot(name, node)
        loc = self.frames[-1]['slots'][name]
        # Forwarding a named reference passes the slot without reading it.
        return loc if capture_node else self.resolve_node_slot(loc, node, flow)

    def resolve_node_slot(self, loc, node, flow):
        slot = loc.node_slot
        if slot is None:
            return loc
        if not (flow.opaque or flow.path_shape_unknown or self.lost_path_reference(loc, flow)):
            order = flow.path_orders.get(slot.path.key)
            if order is None:
                return loc
            origin = order.slot_origin(slot)
            if origin is not None:
                part = ('created-node', -origin) if origin < 0 else ('index', origin)
                return replace(loc, parts=(*slot.path.parts, part))
            if order.retains_slot(slot):
                self.unresolved_at('path-topology',
                                   f'Captured PATH slot is out of bounds: {slot.path.path}[{slot.position}]', node)
                return None
        self.unresolved_at('path-topology', 'Captured PATH reference has an unresolved origin: '+loc.path, node)
        return None

    def constant(self, name):
        if self.frames and name in self.frames[-1]['constants']:return self.frames[-1]['constants'][name]
        return self.plan['constants'].get(name,UNKNOWN)

    def child(self, loc, kind, value, node):
        spec=loc.spec
        if spec and spec[0] == 'PATH':
            if value == 0 or kind == 'created-header':
                selected = spec[2]
            else:
                node_type = spec[1] or self.plan.get('default_path_node')
                selected = node_type if kind == 'created-node' or 1 <= value <= 32767 else None
        elif kind=='field':
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

    def path_io_locations(self, expr, flow, conditional, *, reading=False):
        """Resolve a bounded transfer's ordered records before publishing any writes."""
        while expr['kind'] == 'group':
            expr = expr['args'][0]
        if expr['kind'] != 'path_io_range':
            location = self.locate(expr, flow, conditional, path_io=True)
            records = self.path_transfer_records(location, expr, flow, conditional)
            if records is not None:
                if reading and not records:
                    self.unresolved_at('path-topology', 'PATH READ requires an existing header or node', expr)
                    return [None]
                return records
            self.retain_selected_path_storage(location, flow, conditional)
            return [location]
        receiver, first_arg, last_arg = expr['args']
        path = self.locate(receiver, flow, conditional)
        first = self.expr(first_arg, flow, conditional).constant
        last = self.expr(last_arg, flow, conditional).constant
        if (path is None or not path.spec or path.spec[0] != 'PATH'
                or type(first) is not int or type(last) is not int
                or not 0 <= first <= 32767 or not 1 <= last <= 32767):
            self.unresolved_at('selection', 'PATH range requires known bounds and a declared PATH receiver', expr)
            return [None]
        if first == 0 and path.spec[2] is None:
            first = 1
        step = 1 if first <= last else -1
        indexes = range(first, last + step, step)
        if len(indexes) > MAX_PATH_IO_FIELDS:
            self.unresolved_at('selection', 'PATH range exceeds the bounded FILE transfer limit', expr)
            return [None]
        locations = [self.index_child(path, index, expr, flow) for index in indexes]
        if any(location is None for location in locations):
            return [None]
        for location in locations:
            self.retain_selected_path_storage(location, flow, conditional)
        return locations

    def stable_path_context(self, loc, flow, conditional):
        return (self.saved_path_count is not None and loc is not None and loc.kind == 'variable'
                and not (flow.opaque or flow.path_shape_unknown or conditional))

    def definite_path_effect(self, flow, conditional):
        return not (flow.opaque or flow.path_shape_unknown or conditional or self.repeat_depth)

    def can_publish_path(self, loc, flow, conditional):
        if loc is None or not self.definite_path_effect(flow, conditional):
            return False
        if not self.frames:
            return loc.kind == 'variable'
        current = self.frames[-1]
        return (loc.kind == 'local' and loc.owner == current['owner']) or current['borrowed_path_edits']

    def active_path_borrows(self, path):
        if self.frames and path.kind == 'local' and path.owner == self.frames[-1]['owner']:
            return
        depth = len(path.parts)
        for frame in self.frames:
            for ref in frame['references']:
                if ref is None or (len(ref.parts) > depth and self.path_contains_reference(path, ref)):
                    yield ref

    def node_edit_preserves_borrows(self, path, order, prefix, suffix, removed):
        borrows = tuple(self.active_path_borrows(path))
        if not borrows:
            return True
        depth = len(path.parts)
        stationary = set(prefix)
        shifted = set(suffix)
        for ref in borrows:
            if ref is None:
                return False
            slot = ref.node_slot
            if slot is not None:
                if not order.retains_slot(slot):
                    return False
                continue
            part = ref.parts[depth]
            origin = _path_record_identity(part)
            if _path_header_part(part) or origin in stationary or origin in order.detached:
                continue
            # A whole-node borrow keeps a list slot. A descendant keeps the
            # record's storage through an in-place move or deletion.
            if len(ref.parts) > depth + 1 and origin is not None and (origin in shifted or origin == removed):
                continue
            return False
        return True

    def replaced_path_borrows(self, path, flow, conditional, *, keep_header=False, complete_header=False):
        """Validate borrowed records and retain the last contents of replaced slots."""
        if not self.can_publish_path(path, flow, conditional):
            return None
        order = flow.path_orders.get(path.key)
        detached = order.detached if order is not None else frozenset()
        retired_slots = order.retired_slots if order is not None else {}
        depth = len(path.parts)
        replaced = set()
        retiring = {}
        available_nodes = None
        for ref in self.active_path_borrows(path):
            if ref is None or (order is None and path.key in flow.path_orders):
                return None
            part = ref.parts[depth]
            slot = ref.node_slot
            if slot is not None:
                if slot.key in retired_slots:
                    continue
                if order is not None:
                    if not order.retains_slot(slot):
                        return None
                    origin = order.slot_origin(slot)
                    retiring[slot.key] = origin
                    if origin is not None:
                        replaced.add(origin)
                    continue
                origin = slot.position
                retiring[slot.key] = origin
            else:
                origin = _path_record_identity(part)
                if origin in detached:
                    continue
            if _path_header_part(part):
                header = -order.header if order is not None and order.header is not None else 0
                if path.spec[2] is None or origin != header:
                    return None
                if keep_header:
                    # Replacing incomplete aggregate data can drop a nested
                    # container. A whole header still borrows its descriptor slot.
                    if len(ref.parts) > depth + 1 and not complete_header:
                        return None
                    continue
            else:
                if available_nodes is None:
                    if order is not None:
                        self.tick(len(order.nodes))
                        available_nodes = set(order.nodes)
                    else:
                        count = self.known_path_count(path, flow, conditional)
                        if count is None:
                            return None
                        available_nodes = range(1, count + 1)
                if origin not in available_nodes:
                    return None
            replaced.add(origin)
        if replaced:
            self.tick(len(detached) + len(replaced))
            detached = detached | replaced
        if retiring:
            self.tick(len(retired_slots) + len(retiring))
            retired_slots = retired_slots | retiring
        return detached, retired_slots

    def lost_path_reference(self, loc, flow):
        if not flow.path_orders or not loc.parts:
            return False
        dimensions, terminal = _array_dimensions(loc.root_spec)
        if not terminal or terminal[0] != 'PATH' or len(loc.parts) <= len(dimensions):
            return False
        path_key = (*loc.key[:3], loc.parts[:len(dimensions)])
        return None in flow.path_orders or (
            path_key in flow.path_orders
            and (flow.path_orders[path_key] is None or flow.opaque or flow.path_shape_unknown)
        )

    def known_path_count(self, loc, flow, conditional):
        if loc is None or flow.opaque or flow.path_shape_unknown or conditional or None in flow.path_orders:
            return None
        if loc.key in flow.path_orders:
            order = flow.path_orders[loc.key]
            return len(order.nodes) if order is not None else None
        if not self.stable_path_context(loc, flow, conditional):
            return None
        count = self.saved_path_count(loc.owner, loc.root, loc.root_spec, loc.parts)
        if count is DEFAULT_EMPTY_PATH:
            return 0
        if count is not None:
            self.path_storage[loc.owner, loc.root] = loc.root_spec
        return count

    def index_child(self, loc, index, node, flow):
        if loc.spec[0] == 'PATH' and index >= 0:
            key = loc.key
            if None in flow.path_orders or key in flow.path_orders:
                order = flow.path_orders.get(key)
                if order is None or flow.opaque or flow.path_shape_unknown:
                    self.unresolved_at('path-topology', f'Saved origin of {loc.path}[{index}] is unresolved', node)
                    return None
                if index > len(order.nodes):
                    self.unresolved_at('path-topology', f'PATH node {index} is outside the modeled shape of {loc.path}', node)
                    return None
                if index == 0:
                    if order.header is not None:
                        return self.child(loc, 'created-header', order.header, node)
                else:
                    origin = order.nodes[index-1]
                    if origin < 0:
                        return self.child(loc, 'created-node', -origin, node)
                    index = origin
        return self.child(loc, 'index', index, node)

    def field_child(self, loc, field, node, flow):
        if loc.spec[0] == 'PATH':
            loc = self.index_child(loc, 0, node, flow)
        return self.child(loc, 'field', field, node) if loc is not None else None

    def retain_selected_path_storage(self, loc, flow, conditional):
        if not self.stable_path_context(loc, flow, conditional):
            return
        dimensions, root = _array_dimensions(loc.root_spec)
        if not root or root[0] != 'PATH' or len(loc.parts) <= len(dimensions):
            return
        prefix = loc.parts[:len(dimensions)]
        kind, index = loc.parts[len(dimensions)]
        if kind != 'index':
            return
        count = self.saved_path_count(loc.owner, loc.root, loc.root_spec, prefix)
        if type(count) is int and 0 <= index <= count:
            self.path_storage[loc.owner, loc.root] = loc.root_spec

    def path_transfer_records(self, loc, node, flow, conditional):
        """Expand a transfer using the proven current header and node layout."""
        if loc is None or flow.opaque or flow.path_shape_unknown or conditional:
            return None
        _, terminal = _array_dimensions(loc.spec)
        if not terminal or terminal[0] != 'PATH':
            return None
        records = []
        remaining = MAX_PATH_IO_FIELDS

        def expand(current):
            nonlocal remaining
            self.tick()
            spec = current.spec
            if spec[0] == 'ARRAY':
                size = spec[1][0] if type(spec[1]) is list else spec[1]
                return type(size) is int and all(
                    expand(self.child(current, 'index', index, node))
                    for index in range(1, size + 1)
                )
            count = self.known_path_count(current, flow, conditional)
            if count is None:
                return False
            for index in range(0 if spec[2] is not None else 1, count + 1):
                if remaining <= 0:
                    return False
                record = self.index_child(current, index, node, flow)
                leaves = self.leaves(record) if record is not None else None
                if leaves is None:
                    return False
                remaining -= len(leaves)
                if remaining < 0:
                    return False
                records.append(record)
            return True

        if not expand(loc):
            return None
        return records

    def locate(self, expr, flow, conditional, *, path_io=False, capture_node=False):
        if not isinstance(expr,dict):return None
        kind=expr.get('kind');args=expr.get('args',[])
        if 'token' in expr:return self.slot(expr['token'],expr,flow,capture_node=capture_node)
        if kind=='name':return self.slot(expr['value'],expr,flow,capture_node=capture_node)
        if kind=='group':
            return self.locate(args[0], flow, conditional, path_io=path_io, capture_node=capture_node)
        if kind=='field':
            base=self.locate(args[0],flow,conditional)
            return self.field_child(base, expr['value'], expr, flow) if base else None
        if kind=='index':
            base=args[0]
            if base.get('kind')=='name' and base['value'] in self.plan.get('port_types',{}):
                port = base['value']
                index = self.expr(args[1],flow,conditional).constant
                minimum = 0 if port in ZERO_BASED_PORTS else 1
                if type(index) is int and minimum <= index:
                    self.context('ports', port+'['+str(index)+']')
                    return _Location('port','',port,(('index',index),),[self.plan['port_types'][port]])
                self.unresolved_at('dynamic-address','Port index requires an explicit runtime mapping',expr);return None
            loc=self.locate(base,flow,conditional)
            for position, argument in enumerate(args[1:], 1):
                index=self.expr(argument,flow,conditional).constant
                if type(index) is not int:
                    self.unresolved_at('dynamic-address','Index is not statically known for '+(loc.path if loc else '<computed>'),expr);loc=None
                elif loc:
                    header_allowed = position == len(args) - 1 and (
                        expr.get('static_zero_subscript') or path_io and self.plan.get('path_index_io')
                    )
                    if loc.spec[0] == 'PATH' and index == 0 and not header_allowed:
                        self.unresolved_at('selection', 'PATH header requires a statically selected zero subscript', expr)
                        loc = None
                    else:
                        selected = self.index_child(loc, index, expr, flow)
                        if (selected is not None and capture_node and position == len(args) - 1
                                and loc.spec[0] == 'PATH' and index > 0):
                            order = flow.path_orders.get(loc.key)
                            slot = _PathNodeSlot(loc, index, order.generation if order is not None else 0)
                            selected = replace(selected, node_slot=slot)
                        loc = selected
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

    def read(self, loc, node, flow, conditional, *, partial=False, path_io=False):
        if self.lost_path_reference(loc, flow):
            self.unresolved_at('path-topology', 'Captured PATH reference has an unresolved origin: '+loc.path, node)
            return _Value(complete=False, spec=loc.spec)
        if partial and loc.spec and loc.spec[0] == 'PATH':
            count = self.known_path_count(loc, flow, conditional)
            if count is not None:
                if self.path_snapshot_fits(tuple_spec(loc.spec), count):
                    records = self.capture_path_copy(loc, range(1, count + 1), node, flow, conditional)
                    if records is not None:
                        return _Value(complete=all(record.complete for record in records),
                                      spec=loc.spec, path_records=tuple(records))
                else:
                    self.unresolved_at('limit', 'PATH value exceeds the scalar snapshot limit', node)
        if path_io:
            records = self.path_transfer_records(loc, node, flow, conditional)
            if records is not None:
                for record in records:
                    self.read(record, node, flow, conditional)
                return _Value(spec=loc.spec)
            self.retain_selected_path_storage(loc, flow, conditional)
        leaves=self.leaves(loc)
        if leaves is None:
            self.unresolved_at('schema','Resource or unsupported value read: '+loc.path,node)
            return _Value(complete=False,spec=loc.spec)
        keys={leaf.key for leaf in leaves}
        missing=keys-flow.defined
        partial_copy=partial and loc.spec and loc.spec[0] not in SCALARS
        if missing:
            initial=missing-flow.assigned
            if any(kind in ('created-node', 'created-header') for kind, _ in loc.parts):
                if not partial_copy:
                    self.unresolved_at('derived-value', 'Source-created PATH data may be uninitialized: '+loc.path, node)
            elif not initial:
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
            flow.path_shape_unknown = True
            self.unresolved_at('write-target','Writable target is not statically resolved',node);return
        if self.lost_path_reference(loc, flow):
            self.unresolved_at('path-topology', 'Captured PATH write has an unresolved origin: '+loc.path, node)
            self.opaque(flow)
            return
        leaves=self.leaves(loc)
        if leaves is None:
            self.unresolved_at('schema','Resource or unsupported write: '+loc.path,node)
            _, terminal = _array_dimensions(loc.spec)
            if terminal and terminal[0] == 'PATH':
                if loc.spec[0] == 'PATH':
                    flow.path_orders[loc.key] = None
                self.opaque(flow)
            return
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

    def expr(self, node, flow, conditional=False, *, partial=False, path_io=False, statement_call=False):
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
            loc=self.slot(value,node,flow)
            if loc:return self.read(loc,node,flow,conditional,partial=partial,path_io=path_io)
            constant=self.constant(value)
            if constant is not UNKNOWN:return _Value(constant)
            if value in self.plan['routines']:
                result = self.call(dict(node, kind='call', args=[]), flow, conditional, statement_call=statement_call)
                return self.result_value(result, node, partial)
        if kind == 'path_io_range':
            for location in self.path_io_locations(node, flow, conditional):
                if location is not None:
                    self.read(location, node, flow, conditional)
            return _Value(complete=False)
        if kind in ('field','index'):
            loc=self.locate(node,flow,conditional,path_io=path_io)
            if loc:return self.read(loc,node,flow,conditional,partial=partial,path_io=path_io)
            self.unresolved_at('selection','Computed or dynamic data read is unresolved',node);return _Value(complete=False)
        if kind == 'group':
            return self.expr(args[0], flow, conditional, partial=partial, path_io=path_io,
                             statement_call=statement_call)
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
        if kind == 'call':
            result = self.call(node, flow, conditional, statement_call=statement_call)
            return self.result_value(result, node, partial)
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
            values = [self.expr(item, flow, conditional, path_io=kind == 'write_item' and index == 0)
                      for index, item in enumerate(args)]
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

    def path_metadata_call(self, node, flow, conditional):
        name = node['value']
        target, = node['args']
        while target['kind'] == 'group':
            target = target['args'][0]
        loc = None
        value = None
        if target['kind'] in ('name', 'field', 'index'):
            loc = self.locate(target, flow, conditional)
            if loc is None and target['kind'] == 'name' and target['value'] in self.plan['routines']:
                value = self.expr(target, flow, conditional, partial=True)
        else:
            value = self.expr(target, flow, conditional, partial=True)
        spec = loc.spec if loc is not None else value.spec if value is not None else None
        if flow.stopped and not flow.opaque:
            return _Value(complete=False, spec=['INTEGER'])
        if name == 'NODE_SIZE':
            node_type = node.get('node_data_type')
            if node_type is None and spec and spec[0] == 'PATH':
                node_type = spec[1] or self.plan.get('default_path_node') or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']
            if node_type is not None:
                try:
                    size = rt.integer(path_node_size(tuple_spec(node_type), node.get('line')), node.get('line'))
                except (rt.KarelRuntimeError, TypeError, ValueError, IndexError, RecursionError) as error:
                    self.unresolved_at('path-schema', 'NODE_SIZE cannot resolve the portable node layout: '+str(error), node)
                else:
                    return _Value(size, spec=['INTEGER'])
            else:
                self.unresolved_at('path-schema', 'NODE_SIZE requires a known NODEDATA schema', node)
        else:
            if value is not None and value.path_records is not None:
                count = len(value.path_records) - int(value.spec[2] is not None)
                return _Value(count, spec=['INTEGER'])
            if loc is not None and spec and spec[0] == 'PATH':
                count = self.known_path_count(loc, flow, conditional)
                if count is not None:
                    return _Value(count, spec=['INTEGER'])
            self.unresolved_at('path-topology', 'PATH_LEN requires a known current node count', node)
        return _Value(spec=['INTEGER'])

    def complete_path_record(self, value):
        """A successful capture has complete leaves, including supplied inputs."""
        facts = (
            {key: _Value(fact.constant, spec=fact.spec) for key, fact in value.facts.items()}
            if value.facts is not None else None
        )
        return _Value(spec=value.spec, facts=facts)

    def path_contains_reference(self, path, ref):
        return ref.key[:3] == path.key[:3] and ref.parts[:len(path.parts)] == path.parts

    def path_status_disjoint(self, path, status, flow):
        if not self.path_contains_reference(path, status):
            return True
        order = flow.path_orders.get(path.key)
        depth = len(path.parts)
        return (order is not None and len(status.parts) > depth + 1
                and _path_record_identity(status.parts[depth]) in order.detached)

    def path_seed_compatible(self, path, seed, convert):
        """Return True for a modeled copy, False for status 3, or None."""
        if seed is None:
            return True
        target = path.spec[1] or self.plan.get('default_path_node')
        if not target or not seed.spec:
            return None
        target, source = tuple_spec(target), tuple_spec(seed.spec)
        if source == target:
            return True
        if convert is False:
            return False
        if convert is True:
            if rt.record_schema_kind(target, source) == 'structure':
                return True
            if rt.kinematic_record_kind(target, source) != 'structure':
                return False
        return None

    def path_edit(self, node, flow, conditional):
        name = node['value']
        path_arg, *operands = node['args']
        path = self.locate(path_arg, flow, conditional)
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        index = None
        if name != 'APPEND_NODE':
            index_arg, *operands = operands
            index = self.expr(index_arg, flow, conditional).constant
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        seed = None
        flags = []
        if len(operands) > 1:
            seed_arg, status_arg, *flags = operands
            seed = self.expr(seed_arg, flow, conditional)
        else:
            status_arg = operands[-1]
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        status = self.locate(status_arg, flow, conditional)
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        convert = self.expr(flags[0], flow, conditional).constant if flags else None
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)

        count = self.known_path_count(path, flow, conditional) if path is not None and path.spec[0] == 'PATH' else None
        if (count is not None and status is not None and not self.repeat_depth
                and self.path_status_disjoint(path, status, flow)):
            removing = name == 'DELETE_NODE'
            last = count if removing else count + 1
            if name == 'APPEND_NODE':
                index = last
            compatible = self.path_seed_compatible(path, seed, convert)
            if compatible is False:
                self.write(status, _Value(3, spec=['INTEGER']), flow, node)
                return _Value()
            if compatible is True and type(index) is int and (removing or count < 32767):
                if not 1 <= index <= last:
                    self.write(status, _Value(2, spec=['INTEGER']), flow, node)
                    return _Value()
                self.tick(count + 1)
                order = flow.path_orders.get(path.key)
                if order is None:
                    order = _PathOrder(tuple(range(1, count + 1)))
                offset = index - 1
                prefix = order.nodes[:offset]
                shifted = order.nodes[index if removing else offset:]
                removed = order.nodes[offset] if removing else None
                if (self.can_publish_path(path, flow, conditional)
                        and self.node_edit_preserves_borrows(path, order, prefix, shifted, removed)):
                    detached = order.detached
                    if removing:
                        depth = len(path.parts)
                        if any(ref is not None and len(ref.parts) > depth + 1
                               and _path_record_identity(ref.parts[depth]) == removed
                               for ref in self.active_path_borrows(path)):
                            self.tick(len(detached))
                            detached = detached | {removed}
                        nodes = prefix + shifted
                    else:
                        self.serial += 1
                        nodes = prefix + (-self.serial,) + shifted
                        record = self.child(path, 'created-node', self.serial, node)
                        value = _Value(complete=False) if seed is None else self.complete_path_record(seed)
                        self.write(record, value, flow, node)
                    flow.path_orders[path.key] = replace(
                        order, nodes=nodes, detached=detached,
                        previous_max_size=max(order.previous_max_size, count),
                    )
                    self.write(status, _Value(0, spec=['INTEGER']), flow, node)
                    return _Value()

        flow.path_orders[path.key if path is not None else None] = None
        self.unresolved_at('path-topology', name+' may change PATH topology or captured node references', node)
        self.opaque(flow)
        self.write(status, _Value(), flow, node)
        return _Value()

    def path_copy(self, node, flow, conditional):
        operands = []
        for index, argument in enumerate(node['args']):
            if flow.stopped and not flow.opaque:
                return _Value(complete=False)
            if index in (0, 3, 4):
                operands.append(self.locate(argument, flow, conditional))
            else:
                operands.append(self.expr(argument, flow, conditional).constant)
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        source, first, last, target, status, *flags = operands
        convert = flags[0] if flags else False
        if (source is not None and source.spec[0] == 'PATH' and target is not None and target.spec[0] == 'PATH'
                and status is not None and self.definite_path_effect(flow, conditional)
                and self.path_status_disjoint(target, status, flow)):
            source_type, target_type = tuple_spec(source.spec), tuple_spec(target.spec)
            if source_type == target_type:
                layout = ('exact', 'exact')
            elif type(convert) is bool:
                layout = path_conversion_layout(target_type, source_type, model=True) if convert else None
            else:
                layout = ()
            if layout is None:
                self.write(status, _Value(3, spec=['INTEGER']), flow, node)
                return _Value()

            count = self.known_path_count(source, flow, conditional)
            if layout and count is not None and type(first) is int and type(last) is int:
                if first == last == 0:
                    indexes = range(1, count + 1)
                elif 1 <= first <= count and 1 <= last <= count:
                    step = 1 if first <= last else -1
                    indexes = range(first, last + step, step)
                else:
                    self.write(status, _Value(2, spec=['INTEGER']), flow, node)
                    return _Value()
                history = self.replaced_path_borrows(target, flow, conditional)
                if history is not None:
                    captured = self.capture_path_copy(source, indexes, node, flow, conditional)
                    if captured is not None and 'kinematic' not in layout:
                        self.publish_path_records(target, captured, node, flow, history=history)
                        self.write(status, _Value(0, spec=['INTEGER']), flow, node)
                        return _Value()

        flow.path_orders[target.key if target is not None else None] = None
        self.unresolved_at('path-topology', 'COPY_PATH layout, bounds or destination effects require review', node)
        self.opaque(flow)
        self.write(status, _Value(), flow, node)
        return _Value()

    def convert_path_value(self, target, value, node, flow):
        """Convert a captured private PATH before evaluating later operands."""
        if value.path_records is not None:
            if target == value.spec:
                return value
            target_type = tuple_spec(target)
            layout = path_conversion_layout(target_type, tuple_spec(value.spec), model=True)
            count = len(value.path_records) - int(value.spec[2] is not None)
            node_type = target[1] or self.plan.get('default_path_node')
            if layout and 'kinematic' not in layout and node_type and self.path_snapshot_fits(target_type, count):
                records = []
                for index, item in enumerate(value.path_records):
                    spec = target[2] if index == 0 and target[2] is not None else node_type
                    slot = _Location('local', '@path-value', 'PATH', spec=spec)
                    records.append(self.stored(slot, item, self.leaves(slot), node))
                return _Value(complete=all(item.complete for item in records), spec=target,
                              path_records=tuple(records))
        self.unresolved_at('path-topology', 'Private PATH value or conversion requires review', node)
        self.opaque(flow)
        return _Value(complete=False, spec=target)

    def path_assignment(self, node, flow, conditional):
        target_arg, source_arg = node['args']
        value = self.expr(source_arg, flow, conditional, partial=True)
        if flow.stopped and not flow.opaque:
            return
        target_type = node['path_assignment_type']
        value = self.convert_path_value(target_type, value, source_arg, flow)
        target = self.locate(target_arg, flow, conditional)
        if flow.stopped and not flow.opaque:
            return
        if value.path_records is not None and target is not None and target.spec == target_type:
            complete_header = target_type[2] is not None and value.path_records[0].complete
            history = self.replaced_path_borrows(target, flow, conditional, keep_header=True,
                                                 complete_header=complete_header)
            if history is not None:
                self.publish_path_records(target, value.path_records, node, flow,
                                          keep_header=True, history=history)
                return

        flow.path_orders[target.key if target is not None else None] = None
        self.unresolved_at('path-topology', 'PATH assignment source or destination effects require review', node)
        self.opaque(flow)

    def path_snapshot_fits(self, spec, count):
        node = spec[1] or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']
        header = rt.scalar_leaf_count(spec[2]) if spec[2] is not None else 0
        return header + count * rt.scalar_leaf_count(node) <= MAX_FACTS

    def capture_path_copy(self, source, indexes, node, flow, conditional):
        """Read the selected records and header before publishing any copy."""
        selected = (0, *indexes) if source.spec[2] is not None else indexes
        self.tick(len(selected))
        values = []
        for index in selected:
            loc = self.index_child(source, index, node, flow)
            if loc is None:
                return None
            values.append(self.read(loc, node, flow, conditional, partial=True))
        return values

    def publish_path_records(self, target, values, node, flow, *, keep_header=False, history=None):
        """Give replacement nodes new identities and write the selected header."""
        previous = flow.path_orders.get(target.key)
        header = previous.header if keep_header and previous is not None else None
        nodes = []
        for index, value in enumerate(values):
            if index == 0 and target.spec[2] is not None:
                if not keep_header:
                    self.serial += 1
                    header = self.serial
                part = ('index', 0) if header is None else ('created-header', header)
            else:
                self.serial += 1
                part = ('created-node', self.serial)
                nodes.append(-self.serial)
            self.write(self.child(target, *part, node), value, flow, node)
        self.serial += 1
        detached, retired_slots = history if history is not None else (frozenset(), {})
        flow.path_orders[target.key] = _PathOrder(tuple(nodes), header, detached, self.serial, retired_slots)

    def call(self, node, flow, conditional, *, statement_call=False):
        name=node['value'];args=node['args']
        if name in self.plan['routines']:
            return self.routine(name, args, node, flow, conditional, statement_call=statement_call)
        if name in ('PATH_LEN', 'NODE_SIZE'):
            return self.path_metadata_call(node, flow, conditional)
        if name in ('APPEND_NODE', 'INSERT_NODE', 'DELETE_NODE'):
            return self.path_edit(node, flow, conditional)
        if name == 'COPY_PATH':
            return self.path_copy(node, flow, conditional)
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
                        if field:loc=self.field_child(loc,field[1].upper(),node,flow);rest=rest[field.end():]
                        elif index:
                            for item in index[1].split(','):
                                if loc:loc=self.index_child(loc,int(item),node,flow)
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
                    flow.path_shape_unknown = True
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
        self.scheduled_body(plan, path_orders=flow.path_orders)
        return False

    def scheduled_body(self, plan, *, segment=False, suspension=None, path_orders=None):
        depth = self.suspended_depth + len(self.frames) + 1
        caller_plan, caller_roots, caller_depth = self.plan, self.task_roots, self.suspended_depth
        caller_frames, caller_exits, caller_values = self.frames, self.exits, self.capture_values
        self.plan, self.task_roots, self.suspended_depth = plan, (*caller_roots, plan['program']), depth
        self.frames, self.exits, self.capture_values = [], [], {}
        try:
            if not segment:
                self.block(plan['body'], _Flow(task_order_unknown=True, path_orders=dict.fromkeys(path_orders or ())), True)
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

    def routine(self, name, args, node, flow, conditional, *, statement_call=False):
        routine=self.plan['routines'][name]
        modes=node.get('passing',[]);actual=[]
        for index,item in enumerate(args):
            if flow.stopped and not flow.opaque:
                return _Value(complete=False)
            mode=modes[index] if index<len(modes) else 'unknown'
            if mode=='reference':actual.append(self.locate(item,flow,conditional,capture_node=True))
            elif mode=='value':
                value = self.expr(item,flow,conditional,partial=True)
                expected = routine['parameters'][index][1]
                if expected[0] == 'PATH' and not (flow.stopped and not flow.opaque):
                    value = self.convert_path_value(expected, value, item, flow)
                actual.append(value)
            else:
                self.unresolved_at('argument','Routine passing mode is unresolved: '+name,node)
                actual.append(self.expr(item,flow,conditional))
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        target_plan, target_routine = self.routine_target(name, routine)
        routine_key = (target_plan['program'], name) if target_plan else None
        if (target_routine is None or any(frame['key'] == routine_key for frame in self.frames)
                or self.suspended_depth + len(self.frames) >= MAX_CALL_DEPTH):
            qualified = (routine['external'] or self.program) + '.' + name
            self.unresolved_at('routine', 'External or recursive routine effects are unresolved: '+qualified, node)
            for item in actual:
                if isinstance(item, _Location):
                    location = self.resolve_node_slot(item, node, flow)
                    if location is not None:
                        self.read(location, node, flow, True)
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
        # Expression calls may run during operand capture. Along a chain
        # of direct procedure statements, each body starts after its
        # arguments have been captured in the active frame.
        direct = statement_call and routine['result'] is None and (
            not self.frames or self.frames[-1]['borrowed_path_edits']
        )
        references = tuple(
            item if isinstance(item, _Location) else None
            for index, item in enumerate(actual) if index >= len(modes) or modes[index] != 'value'
        )
        frame = dict(name=name, key=routine_key, owner=owner, result=routine['result'],
                     slots={key:_Location('local',owner,key,spec=spec,root_spec=spec)
                            for key,spec in routine['types'].items()},
                     constants=routine['constants'], borrowed_path_edits=direct, references=references)
        formals = {formal for formal, _, _, _ in bindings}
        for local in frame['slots'].values():
            if local.root not in formals and local.spec[0] == 'PATH':
                flow.path_orders[local.key] = _PathOrder(())
        for formal,spec,item,resolved in bindings:
            if isinstance(item,_Location):frame['slots'][formal]=item
            else:
                if spec==['STRING',None]:resolved=['STRING',254]
                loc=_Location('local',owner,formal,spec=resolved,root_spec=resolved);frame['slots'][formal]=loc
                if resolved[0] == 'PATH':
                    if isinstance(item, _Value) and item.path_records is not None and not flow.opaque:
                        self.publish_path_records(loc, item.path_records, node, flow)
                    else:
                        flow.path_orders[loc.key] = None
                else:
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
        merged.path_orders = {key: order for key, order in merged.path_orders.items() if key is None or key[1] != owner}
        flow.take(merged)
        values=[item[1] for item in exits];result=routine['result']
        if result and result[0] != 'PATH':
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
            self.scan_callbacks(clauses, captures, _Flow(path_orders=dict.fromkeys(flow.path_orders)))
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
                scan = _Flow(defined=flow.defined.copy(), assigned=flow.assigned.copy(),
                             path_orders=dict.fromkeys(flow.path_orders))
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
                scan = _Flow(defined=flow.defined.copy(), assigned=flow.assigned.copy(),
                             path_orders=dict.fromkeys(flow.path_orders))
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

    def sample_condition_inputs(self, node, flow, conditional, kinds):
        if not isinstance(node, dict):
            return node
        original = node.get('args', ())
        args = [self.sample_condition_inputs(arg, flow, conditional, kinds) for arg in original]
        kind = node.get('kind')
        if kind not in kinds:
            return dict(node, args=args) if any(a is not b for a, b in zip(args, original)) else node
        capture = kind in ('wait_eval', 'repeat_eval')
        value = self.expr(args[0], flow, conditional, partial=capture) if args else _Value()
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

    def file_statement(self, node, flow, conditional):
        """Follow source operands without attempting to open or drive a FILE."""
        kind = node['kind']
        selector, *operands = node['args']
        if selector is not None:
            location = self.locate(selector, flow, conditional)
            if location is None and selector['kind'] == 'name':
                alias = selector['value']
                if alias in PREDEFINED_FILE_NAMES and alias not in self.plan['types']:
                    self.context('predefined_files', alias)
        if flow.stopped and not flow.opaque:
            return

        if kind in ('file_read', 'file_write'):
            self.statement(operands[0], flow, conditional)
            if flow.stopped and not flow.opaque:
                return
            self.unresolved_at('file-transport', 'FILE transfer depends on its open endpoint and transport', node)
            self.opaque(flow)
            return

        if kind == 'file_open':
            for operand in operands:
                self.expr(operand, flow, conditional)
                if flow.stopped and not flow.opaque:
                    return
        self.unresolved_at('file-state', 'FILE operation depends on its configured endpoint and runtime state', node)
        if self.linked_plans is not None:
            self.opaque(flow)

    def statement(self, node, flow, conditional):
        self.tick();kind=node['kind'];args=node['args']
        if flow.task_order_unknown and flow.paused_tasks:
            self.lose_task_order(flow)
        if kind=='assign':
            if 'path_assignment_type' in node:
                self.path_assignment(node, flow, conditional)
                return
            value=self.expr(args[1],flow,conditional,partial=True)
            self.write(self.locate(args[0],flow,conditional),value,flow,node);return
        if kind == 'call':
            self.expr(args[0], flow, conditional, statement_call=True)
            return
        if kind in ('file_read', 'file_write', 'file_open', 'file_close', 'file_cancel'):
            self.file_statement(node, flow, conditional)
            return
        if kind == 'wait':
            captured = self.sample_condition_inputs(args[0], flow, conditional, ('wait_eval',))
            predicate = self.sample_condition_inputs(captured, flow, conditional,
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
            flow.constants.clear()
            self.repeat_depth += 1
            try:
                self.block(node['body'],flow,conditional)
                if not flow.stopped:
                    conditionally_reached = conditional or (not self.frames and len(self.exits) > exits_before_body)
                    predicate = self.sample_condition_inputs(args[0], flow, conditionally_reached, ('repeat_eval',))
                    self.expr(predicate, flow, conditionally_reached)
            finally:
                self.repeat_depth -= 1
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
            result = self.frames[-1]['result'] if self.frames else None
            if result and result[0] == 'PATH' and not (flow.stopped and not flow.opaque):
                value = self.convert_path_value(result, value, node, flow)
            self.exits.append((flow.copy(),value));flow.stopped=True;return
        if kind=='write_items':
            for argument in args:
                if flow.stopped and not flow.opaque:
                    return
                self.expr(argument,flow,conditional)
            return
        if kind=='read':
            destinations = []
            for argument in args:
                if flow.stopped and not flow.opaque:
                    return
                if argument['kind'] == 'read_cr':
                    continue
                formatted = argument['kind'] == 'read_item'
                target = argument['args'][0] if formatted else argument
                destinations.extend(self.path_io_locations(target, flow, conditional, reading=True))
                if formatted:
                    for control in argument['args'][1:]:
                        if flow.stopped and not flow.opaque:
                            return
                        self.expr(control, flow, conditional)
            if flow.stopped and not flow.opaque:
                return
            self.unresolved_at('input-stream','READ requires explicitly supplied input data',node)
            if any(location is None for location in destinations):
                self.opaque(flow)
            for location in destinations:
                self.write(location, _Value(), flow, node, definite=False)
            return
        if kind=='abort' or kind=='task_control' and args[0] in ('ABORT','STOP') and len(args)==1:
            flow.stopped=True;return
        self.unresolved_at('statement','Control or resource statement requires further analysis: '+kind,node)
        self.opaque(flow)
        for argument in args:
            if isinstance(argument,dict):self.expr(argument,flow,True)
        self.block(node.get('body',[]),flow,True);self.block(node.get('alternate',[]),flow,True)


def analyze_plan(plan, target, *, linked_plans=None, saved_path_count=None):
    track_handlers = track_tasks = linked_plans is not None
    # Restart from the checked entry when control uncertainty could hide
    # callbacks or child bodies that a precise pass had left dormant.
    while True:
        try:
            return _analyze_plan(plan, target, linked_plans=linked_plans,
                                 track_handlers=track_handlers, track_tasks=track_tasks,
                                 saved_path_count=saved_path_count)
        except _ActivationUnknown:
            track_handlers = False
        except _TaskOrderUnknown:
            track_tasks = False


def _analyze_plan(plan, target, *, linked_plans, track_handlers, track_tasks, saved_path_count):
    analyzer = _Analyzer(plan, linked_plans=linked_plans, track_handlers=track_handlers, track_tasks=track_tasks,
                         saved_path_count=saved_path_count)
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
    report = dict(schema='karel2py.inputs.v1', target=target, complete=not analyzer.unresolved,
                  inputs=rows, unresolved=list(analyzer.unresolved.values()),
                  context_requirements=list(analyzer.contexts.values()),
                  boundary=('Source-flow candidates from a checked generated contract only; '
                            'no target imports/execution, invented values, host callback guarantees or controller proof.'))
    if analyzer.path_storage:
        report['path_storage'] = [dict(program=owner, path=root, type=spec)
                                  for (owner, root), spec in sorted(analyzer.path_storage.items())]
    return report


def discover_inputs(python_source, *, filename='<python>'):
    """Return candidates and explicit gaps; never execute the selected Python."""
    return _discover_inputs(python_source, filename=filename)


def _discover_inputs(python_source, *, filename, saved_path_count=None):
    raw=python_source.encode('utf-8') if type(python_source) is str else python_source
    if type(raw) is not bytes or len(raw)>MAX_BYTES:raise InputDiscoveryError('Python input requires at most 16 MiB')
    try:
        plan=extract(raw.decode('utf-8-sig'))
        target=dict(file=str(filename),sha256=hashlib.sha256(raw).hexdigest(),program=plan['program'])
        return analyze_plan(plan,target,saved_path_count=saved_path_count)
    except (InputContractError,UnicodeError,KeyError,IndexError,TypeError,ValueError,AttributeError,RecursionError) as error:
        raise InputDiscoveryError(str(error)) from error


def discover_file(path):
    with Path(path).open('rb') as stream:raw=stream.read(MAX_BYTES+1)
    return discover_inputs(raw,filename=str(path))
