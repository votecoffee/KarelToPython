"""Bounded read-before-write discovery from checked generated Python contracts."""
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
import hashlib
import math
from pathlib import Path
import re

from .compiler_language import BUILTIN_SIGNATURES, CONSTANT_BUILTINS, INTEGRAL_TYPES, PREDEFINED_CONSTANTS
from .dynamic import (
    BYNAME_PATH, MAX_LEAVES, UNKNOWN_CREATION_TYPE, creation_cost, creation_type, file_storage_cost, normalized_name,
    rename_names, rename_plan, renamed_key, root_member,
)
from .extended import (
    OUTPUT_PORTS, PORT_TYPES, PREDEFINED_FILE_NAMES, PROGRAM_ATTRIBUTES, PROGRAM_TEXT_ATTRIBUTES, PROGRAM_WRITABLE_ATTRIBUTES,
    ZERO_BASED_PORTS, ProgramAttributes, _parse_system_variable_path, path_conversion_layout, path_node_size, port_value,
)
from .file_io import MAX_PATH_IO_FIELDS, path_io_field_count, path_io_indexes
from .input_contract import extract, InputContractError
from .input_file_output import FileKey, MemoryOutputs
from .input_model_transfers import evaluate_model_paths, evaluate_model_variables
from .input_position_values import (
    POSITION_CLEARED, POSITION_GETTERS, POSITION_MODIFIED, POSITION_SERVICES, POSITION_SETTERS,
    checked_position_facts, merge_positions, position_register_result,
)
from .input_task_segments import (
    FILE_TASK_QUERIES, STRUCTURED_LOOPS, TASK_DATA_AGGREGATES, TASK_ROUTINE_VALUES, bind_repeat_samples, bounded_child,
    explicit_pause, file_task_procedure, file_task_storage, queue_task_call, repeat_capture_parts, resolve_routine,
    scalar_task_operator,
    select_case_labels,
    structured_child, task_handoff_window,
)
from .input_teach_catalog import TEACH_CATALOG_SERVICES, TEACH_EDIT_SERVICES
from .input_teach_discovery import (
    TEACH_HANDLE_SERVICES, TEACH_POSITION_GETTERS, TEACH_POSITION_SECTIONS, TEACH_POSITION_SERVICES,
    TEACH_SCALAR_GETTERS, TEACH_SCALAR_SECTIONS, TEACH_SCALAR_SETTERS, TeachDiscovery, TeachFacts,
)
from .position_register_models import register_description
from .queue_operations import QUEUE_EDIT_INPUTS, plan_queue_copy, plan_queue_edit
from .input_robot_tables import RobotTableFacts
from .input_robot_transfers import inspect_robot_variable, transfer_robot_variable
from .input_robot_values import (
    CONFIG_TEXT_CONVERSIONS, GEOMETRY_FUNCTIONS, POSE_CONSTRUCTORS, ROBOT_CONVERSIONS, ROBOT_RANGE_QUERIES,
    ROBOT_SNAPSHOTS, RobotFactsUnavailable, capture_geometry_value, capture_unpos_value, check_robot_range,
    compare_pose_facts,
    construct_pose, constructor_schema, convert_config_text, convert_known_robot_value, convert_robot_coordinates,
    current_robot_facts,
    evaluate_robot_aggregate, evaluate_robot_assignment, unpos_output_facts,
)
from .inspection import (
    CATALOG_SCAN_LIMIT, catalog_key, catalog_type_matches, describe, effective_list_options,
    effective_program_list_options, merge_program_record, program_attribute_key, program_attribute_value,
    program_list_page, variable_list_page,
)
from .input_value_conversions import (
    MAX_SERVICE_CASES, SCALARS, UNKNOWN, Value as _Value, array_dimensions as _array_dimensions,
    array_prefix_addresses, array_prefix_values, convert_value_facts, detached_facts,
    materialized_value, merge_scalar_choices, operand_cases, scalar_options, stored_value as _stored_value,
    variable_array_prefix_size, variable_transfer_policy,
)
from .schema_conversion import DATA_AGGREGATE_CONVERTERS, MODEL_CONVERSIONS, pythonic_schema_conversion
from .storage import collection_array_cost, list_spec, tuple_spec
from . import runtime as rt


DEFAULT_EMPTY_PATH = object()
INITIAL_BINDING = object()
MAYBE_ATTRIBUTE = object()
MISSING_PATH_RECORD = object()
MAX_STEPS = 100000
MAX_LOOP_ITERATIONS = 32
MAX_INPUTS = 2048
MAX_CALL_DEPTH = 32
MAX_FACTS = 32767
MAX_BYTES = 16 * 1024 * 1024
REGISTER_SERVICES = {
    'GET_REG': ('numeric', 'NUMERIC'), 'SET_INT_REG': ('numeric', 'INTEGER'), 'SET_REAL_REG': ('numeric', 'REAL'),
    'GET_STR_REG': ('strings', 'STRING'), 'SET_STR_REG': ('strings', 'STRING'),
}
INDIRECT_PORT_SERVICES = {'GET_PORT_VAL', 'SET_PORT_VAL', 'GET_PORT_SIM', 'SET_PORT_SIM', 'CLR_PORT_SIM'}
SCALAR_PURE = {name: len(BUILTIN_SIGNATURES[name][0]) for name in CONSTANT_BUILTINS}
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
class _PathRecordSlot:
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
    path_slot: _PathRecordSlot | None = field(default=None, compare=False, hash=False)
    saved_binding: bool = field(default=False, compare=False, hash=False)
    creation_number: int = 0

    @property
    def named_data(self):
        return ((self.saved_binding or self.kind == 'created-variable') and self.root_spec[0] != 'PATH'
                and not _path_array_cell_type(self.root_spec))

    @property
    def key(self):
        identity = (self.root, self.creation_number) if self.creation_number else self.root
        return self.kind, self.owner, identity, self.parts

    @property
    def path(self):
        text = str(self.root)
        for kind, value in self.parts:
            text += ('.' + value if kind == 'field' else
                     '[group=' + (str(value) if value is not None else 'caller-default') + ']' if kind=='group'
                     else '[' + kind.replace('created-', 'source-created ') + ']' if kind in ('created-node', 'created-header')
                     else '[' + str(value) + ']')
        return text


def _known_missing(value):
    return value.uninitialized or any(fact.uninitialized for fact in (value.facts or {}).values())


def _path_conversion_needs_model(layout, node_count):
    return layout[1] == 'kinematic' or (layout[0] == 'kinematic' and node_count > 0)


@dataclass(eq=False, frozen=True)
class _Handler:
    plan: dict
    frames: tuple
    clauses: list
    captures: dict


@dataclass(frozen=True)
class _TaskForHeader:
    node: dict
    counter: _Location
    initializing: bool = True

    @property
    def operand(self):
        return self.node['args'][1 if self.initializing else 2]


@dataclass(frozen=True)
class _TaskLoop:
    node: dict
    iterations: int = 0
    counter: _Location | None = None
    values: range | None = None
    repeat_predicate: dict | None = None
    staged_repeat_test: bool = False


@dataclass(frozen=True)
class _TaskRepeatCapture:
    terms: tuple[dict, ...]
    predicate: dict
    samples: tuple[_Value, ...] = ()


@dataclass(frozen=True)
class _TaskSelect:
    node: dict
    selected: object
    category: str
    labels: tuple[tuple[int, dict], ...]
    index: int = 0
    match: int | None = None


@dataclass(frozen=True)
class _TaskExpression:
    node: dict
    consumer: '_TaskValueConsumer'
    values: tuple[_Value, ...] = ()


@dataclass(frozen=True)
class _TaskArguments:
    """Keep already evaluated arguments while a later argument suspends."""

    call: dict
    consumer: '_TaskValueConsumer | None'
    actuals: tuple[_Location | _Value, ...] = ()


@dataclass(frozen=True)
class _TaskQueueCall:
    call: dict
    actuals: tuple[_Location | _Value, ...] = ()


@dataclass(frozen=True)
class _TaskAssignment:
    node: dict
    spec: list


@dataclass(frozen=True)
class _TaskSelection:
    node: dict
    location: _Location
    selectors: tuple[dict, ...]
    consumer: '_TaskValueConsumer'
    reading: bool = False
    assignment: _Value | None = None
    indices: tuple[object, ...] = ()


@dataclass(frozen=True)
class _TaskResultSelection:
    node: dict
    consumer: '_TaskValueConsumer'
    values: tuple[_Value, ...] = ()


@dataclass(frozen=True)
class _TaskArrayLength:
    node: dict
    consumer: '_TaskValueConsumer'
    values: tuple[_Value, ...] = ()


@dataclass(frozen=True)
class _TaskFile:
    node: dict
    consumer: '_TaskValueConsumer | None' = None
    key: FileKey | None = None
    values: tuple[object, ...] = ()


@dataclass(frozen=True)
class _TaskWrite:
    node: dict
    file_key: FileKey | None = None
    index: int = 0
    values: tuple[_Value, ...] = ()
    aggregate: rt._AggregateWriteValue | None = None
    rendered_pieces: int = 0
    rendered_length: int = 0


@dataclass(frozen=True)
class _TaskRead:
    node: dict
    file_key: FileKey
    index: int = 0
    leaves: tuple[_Location, ...] = ()
    formats: tuple[object, ...] = ()
    fields: tuple[tuple[_Location, tuple[int, ...]], ...] = ()
    line_breaks: tuple[int, ...] = ()


@dataclass(frozen=True)
class _TaskCollectionWrite:
    operand: dict
    schema: list
    bounds: tuple[dict, ...]
    location: _Location | None = None
    generation: int | None = None
    values: tuple[object, ...] = ()


@dataclass(frozen=True)
class _TaskQueue:
    entries: tuple[tuple[int, int], ...] = ()
    sequence: int = 0
    buffer: tuple | None = None


_TaskValueConsumer = (dict | _TaskSelect | _TaskForHeader | _TaskLoop | _TaskExpression |
                      _TaskArguments | _TaskAssignment | _TaskSelection | _TaskResultSelection |
                      _TaskArrayLength | _TaskWrite | _TaskRepeatCapture | _TaskQueueCall | _TaskCollectionWrite |
                      _TaskFile | _TaskRead)


@dataclass(frozen=True)
class _TaskRoutine:
    """Keep bindings alive until the invocation's blocks finish unwinding."""

    frame: dict
    consumer: _TaskValueConsumer | None = None
    result: _Value | None = None


@dataclass(eq=False, frozen=True)
class _Suspension:
    blocks: tuple[tuple[list, int] | _TaskLoop | _TaskRoutine | _TaskSelect |
                  _TaskForHeader | _TaskExpression | _TaskArguments | _TaskSelection | _TaskWrite |
                  _TaskQueueCall | _TaskCollectionWrite | _TaskFile | _TaskRead, ...]
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
    inserted: frozenset[int] = frozenset()
    header_generation: int = 0

    @property
    def header_origin(self):
        return 0 if self.header is None else -self.header

    def slot_generation(self, position):
        return self.header_generation if position == 0 else self.generation

    def retains_slot(self, slot):
        if slot.generation != self.slot_generation(slot.position):
            return slot.key in self.retired_slots
        # A successfully captured list position can be temporarily vacant.
        return 0 <= slot.position <= max(len(self.nodes), self.previous_max_size)

    def slot_origin(self, slot):
        if slot.generation != self.slot_generation(slot.position):
            return self.retired_slots.get(slot.key)
        if slot.position == 0:
            return self.header_origin
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
    uninitialized: set = field(default_factory=set)
    changed_path_aggregates: set = field(default_factory=set)
    # True is a shaped record, False is the whole missing marker, None is an
    # overwritten record with no proof. Missing keys may use the saved layout.
    record_storage: dict = field(default_factory=dict)
    # Layouts of replaced descriptors still held by an evaluated operand.
    retired_paths: dict = field(default_factory=dict)
    # None for a key means predecessor flows disagree on its presence or number.
    variable_entries: dict = field(default_factory=dict)
    next_variable_entry: int | None = 1
    # Current names point to stable storage. None removes a name, while
    # UNKNOWN indicates that predecessor flows disagree.
    named_bindings: dict = field(default_factory=dict)
    creation_counts: dict = field(default_factory=dict)
    allocated_variable_units: int | None = 0
    program_attributes: dict = field(default_factory=dict)
    numeric_kinds: dict = field(default_factory=dict)
    port_simulation: dict = field(default_factory=dict)
    position_cells: dict = field(default_factory=dict)
    position_order_unknown: bool = False
    robot_tables: RobotTableFacts = field(default_factory=RobotTableFacts)
    teach: TeachFacts = field(default_factory=TeachFacts)
    scalar_choices: dict = field(default_factory=dict)
    task_queues: dict = field(default_factory=dict)
    task_file_outputs: MemoryOutputs | None = field(default_factory=MemoryOutputs)

    def copy(self):
        return _Flow(self.defined.copy(),self.assigned.copy(),self.maybe.copy(),
                     self.constants.copy(),self.stopped,self.opaque,self.handlers.copy(),
                     self.requested_tasks.copy(),self.paused_tasks.copy(),self.task_order_unknown,
                     self.path_shape_unknown,self.path_orders.copy(),self.uninitialized.copy(),
                     self.changed_path_aggregates.copy(),self.record_storage.copy(),self.retired_paths.copy(),
                     self.variable_entries.copy(),self.next_variable_entry,
                     self.named_bindings.copy(),self.creation_counts.copy(),self.allocated_variable_units,
                     self.program_attributes.copy(),self.numeric_kinds.copy(),self.port_simulation.copy(),
                     self.position_cells.copy(),self.position_order_unknown,self.robot_tables.copy(),
                     self.teach.copy(), self.scalar_choices.copy(), self.task_queues.copy(), self.task_file_outputs)

    def take(self, other):
        self.handlers = other.handlers
        self.requested_tasks, self.paused_tasks = other.requested_tasks, other.paused_tasks
        self.task_order_unknown = other.task_order_unknown
        self.path_shape_unknown, self.path_orders = other.path_shape_unknown, other.path_orders
        self.defined,self.assigned,self.maybe,self.constants = other.defined,other.assigned,other.maybe,other.constants
        self.stopped,self.opaque = other.stopped,other.opaque
        self.uninitialized = other.uninitialized
        self.changed_path_aggregates = other.changed_path_aggregates
        self.record_storage = other.record_storage
        self.retired_paths = other.retired_paths
        self.variable_entries, self.next_variable_entry = other.variable_entries, other.next_variable_entry
        self.named_bindings = other.named_bindings
        self.creation_counts = other.creation_counts
        self.allocated_variable_units = other.allocated_variable_units
        self.program_attributes = other.program_attributes
        self.numeric_kinds = other.numeric_kinds
        self.port_simulation = other.port_simulation
        self.position_cells = other.position_cells
        self.position_order_unknown = other.position_order_unknown
        self.robot_tables = other.robot_tables
        self.teach = other.teach
        self.scalar_choices = other.scalar_choices
        self.task_queues = other.task_queues
        self.task_file_outputs = other.task_file_outputs


def _merge(flows):
    live = [flow for flow in flows if not flow.stopped]
    if not live:
        result=flows[0].copy();result.stopped=True;return result
    first=live[0]
    constants={key:value for key,value in first.constants.items()
               if all(key in other.constants and type(value) is type(other.constants[key]) and value==other.constants[key] for other in live[1:])}
    choices = {}
    for key in (first.constants.keys() | first.scalar_choices.keys()) - constants.keys():
        groups = []
        for flow in live:
            if key not in flow.defined:
                break
            value = flow.constants.get(key, UNKNOWN)
            groups.append((value,) if type(value) in (bool, int, str) else flow.scalar_choices.get(key, ()))
        else:
            merged = merge_scalar_choices(groups)
            if len(merged) > 1:
                choices[key] = merged
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
    record_storage = {}
    for key in set().union(*(flow.record_storage for flow in live)):
        state = first.record_storage.get(key)
        record_storage[key] = state if all(flow.record_storage.get(key) is state for flow in live) else None
    retired_paths = {key: order for key, order in first.retired_paths.items()
                     if all(other.retired_paths.get(key) == order for other in live[1:])}
    variable_entries = {}
    for key in set().union(*(flow.variable_entries for flow in live)):
        entry = first.variable_entries.get(key)
        variable_entries[key] = entry if all(flow.variable_entries.get(key) == entry for flow in live[1:]) else None
    next_entry = first.next_variable_entry
    if any(flow.next_variable_entry != next_entry for flow in live[1:]):
        next_entry = None
    names = {}
    for key in set().union(*(flow.named_bindings for flow in live)):
        binding = first.named_bindings.get(key, INITIAL_BINDING)
        for flow in live[1:]:
            other = flow.named_bindings.get(key, INITIAL_BINDING)
            if binding != other or isinstance(binding, _Location) and binding.spec != other.spec:
                binding = UNKNOWN
                break
        names[key] = binding
    creation_counts = {}
    for flow in live:
        for key, number in flow.creation_counts.items():
            creation_counts[key] = max(number, creation_counts.get(key, 0))
    units = first.allocated_variable_units
    if any(flow.allocated_variable_units != units for flow in live[1:]):
        units = None
    attributes = {}
    for key in set().union(*(flow.program_attributes for flow in live)):
        values = [flow.program_attributes.get(key) for flow in live]
        if all(value == values[0] for value in values[1:]):
            attributes[key] = values[0]
        elif any(value is None or value is MAYBE_ATTRIBUTE for value in values):
            attributes[key] = MAYBE_ATTRIBUTE
        else:
            attributes[key] = UNKNOWN
    numeric_kinds = {number: kind for number, kind in first.numeric_kinds.items()
                     if all(other.numeric_kinds.get(number) == kind for other in live[1:])}
    simulation = {}
    for key in set().union(*(flow.port_simulation for flow in live)):
        value = first.port_simulation.get(key)
        simulation[key] = value if all(other.port_simulation.get(key) is value for other in live[1:]) else UNKNOWN
    queues = {key: queue for key, queue in first.task_queues.items()
              if all(flow.task_queues.get(key) == queue for flow in live[1:])}
    files = first.task_file_outputs
    if any(other.task_file_outputs != files for other in live[1:]):
        files = None
    return _Flow(set.intersection(*(flow.defined for flow in live)),
                 set.intersection(*(flow.assigned for flow in live)),
                 set.union(*(flow.maybe for flow in live)),constants,False,any(flow.opaque for flow in live),
                 {key: tuple(definitions) for key, definitions in handlers.items()},
                 set.union(*(flow.requested_tasks for flow in live)),
                 pauses,uncertain,any(flow.path_shape_unknown for flow in live),path_orders,
                 set.intersection(*(flow.uninitialized for flow in live)),
                 set.union(*(flow.changed_path_aggregates for flow in live)), record_storage, retired_paths,
                 variable_entries, next_entry, names, creation_counts, units, attributes, numeric_kinds, simulation,
                 merge_positions([flow.position_cells for flow in live], _merged_value),
                 any(flow.position_order_unknown for flow in live),
                 RobotTableFacts.merge([flow.robot_tables for flow in live]),
                 TeachFacts.merge([flow.teach for flow in live], _merged_value), choices, queues, files)


def _path_record_identity(part):
    kind, index = part
    if kind in ('created-node', 'created-header'):
        return -index
    if kind == 'index' and index >= 0:
        return index
    return None


def _path_header_part(part):
    return part[0] == 'created-header' or part == ('index', 0)


def _path_array_cell_type(spec):
    if spec and spec[0] == 'ARRAY':
        _, terminal = _array_dimensions(spec)
        if terminal and terminal[0] == 'PATH':
            return terminal
    return None


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
    choices = ()
    if constant is UNKNOWN and schema and schema[0] in ('INTEGER', 'BOOLEAN', 'STRING'):
        choices = merge_scalar_choices(scalar_options(item) for item in values)
    return _Value(constant, all(item.complete for item in values), schema, facts, path_records,
                  uninitialized=all(item.uninitialized for item in values), scalar_choices=choices)


class _Analyzer(TeachDiscovery):
    def __init__(self, plan, *, linked_plans=None, track_handlers=False, track_tasks=False,
                 saved_path_count=None, saved_bindings=None):
        self.plan = plan
        # A linked fallback can still supply approximate candidates.
        stable_context = linked_plans is None or track_handlers and track_tasks
        self.saved_path_count = saved_path_count if stable_context else None
        self.saved_bindings = saved_bindings if stable_context else None
        self.named_storage_revision = 0
        self.path_storage = {}
        self.binding_storage = {}
        self.steps = 0
        self.serial = 0
        self.inputs = {}
        self.unresolved = {}
        self.frames = []
        self.pending_references = []
        self.pending_path_values = []
        self.exits = []
        self.contexts = {}
        self.linked_plans = linked_plans
        self.task_roots = (plan['program'],)
        self.suspended_depth = 0
        self.checked_child_segment = False
        self.capture_values = {}
        self.track_handlers = track_handlers
        self.saw_handler = False
        self.activation_unknown = False
        self.scanning_handler = False
        self.repeat_depth = 0
        self.callback_depth = 0
        self.track_tasks = track_tasks
        self.task_numbers = tuple(linked_plans) if linked_plans is not None else ()
        self.segmentable = {}
        self.task_handoff = None
        self.open_guard = None
        self.required_input_observer = None
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
        flow.task_file_outputs = None

    def opaque(self, flow, *, activation=True, task_order=True):
        if activation:
            self.lose_activation_order()
        if task_order:
            self.lose_task_order(flow)
        flow.opaque=True;flow.defined.clear();flow.assigned.clear();flow.constants.clear()
        flow.scalar_choices.clear()
        flow.task_queues.clear()
        flow.task_file_outputs = None
        flow.uninitialized.clear()
        flow.changed_path_aggregates.clear()
        flow.record_storage.clear()
        flow.path_orders = dict.fromkeys(flow.path_orders)
        flow.retired_paths.clear()
        flow.variable_entries.clear()
        flow.next_variable_entry = None
        flow.named_bindings.clear()
        flow.creation_counts.clear()
        flow.allocated_variable_units = None
        flow.program_attributes.clear()
        flow.numeric_kinds.clear()
        flow.port_simulation.clear()
        flow.position_cells.clear()
        flow.position_order_unknown = True
        flow.robot_tables.invalidate_all()
        flow.teach = TeachFacts()

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

    def global_slot(self, name, node, *, program=None):
        owner, root = program or self.program, name
        plan = self.plan if owner == self.program else (self.linked_plans or {}).get(owner, {})
        if plan.get('status') != 'available' or name not in plan['types']:
            return None
        if self.checked_child_segment and owner != self.task_roots[-1]:
            # A linked module's globals can be shared with another invocation.
            # The child slice only retains its own globals and captured slots.
            raise _TaskOrderUnknown()
        spec = plan['types'][name]
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
        return loc if capture_node else self.resolve_path_slot(loc, node, flow)

    def resolve_path_slot(self, loc, node, flow):
        slot = loc.path_slot
        if slot is None:
            return loc
        if not (flow.opaque or flow.path_shape_unknown or self.lost_path_reference(loc, flow)):
            order = flow.path_orders.get(slot.path.key)
            if order is None:
                return loc
            origin = order.slot_origin(slot)
            if origin is not None:
                kind = 'created-header' if slot.position == 0 else 'created-node'
                part = (kind, -origin) if origin < 0 else ('index', origin)
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

    def record_fields(self, loc):
        spec = loc.spec
        if not spec:
            return None
        if spec[0] == 'STRUCTURE':
            return dict(spec[2])
        fields = self.plan.get('record_fields', {}).get(spec[0])
        if fields is None:
            fields = rt.DATA_RECORD_FIELDS.get(spec[0])
            if fields is not None:
                return {name: list_spec(schema) for name, schema in fields}
        return fields

    def path_node_schema(self, loc):
        node = loc.spec[1] or self.plan.get('default_path_node')
        if node is None and (loc.saved_binding or loc.kind == 'created-variable'):
            return list_spec(rt.PREDEFINED_STRUCTURES['STD_PTH_NODE'])
        return node

    def child(self, loc, kind, value, node):
        spec=loc.spec
        if spec and spec[0] == 'PATH':
            if value == 0 or kind == 'created-header':
                selected = spec[2]
            else:
                node_type = self.path_node_schema(loc)
                selected = node_type if kind == 'created-node' or 1 <= value <= 32767 else None
        elif kind=='field':
            selected=(self.record_fields(loc) or {}).get(value)
        else:
            selected=None
            if spec and spec[0]=='ARRAY':
                shape=spec[1] if type(spec[1]) is list else [spec[1]]
                if type(shape[0]) is int and 1<=value<=shape[0]:
                    remaining = shape[1:]
                    if remaining:
                        selected = ['ARRAY', remaining[0] if len(remaining) == 1 else remaining, spec[2]]
                    else:
                        selected = spec[2]
            elif spec and spec[0]=='JOINTPOS' and type(spec[1]) is int and 1<=value<=spec[1]:selected=['REAL']
        if selected is None:
            self.unresolved_at('selection','Unsupported or unbounded selected schema for '+loc.path,node)
            return None
        return replace(loc, parts=(*loc.parts, (kind, value)), spec=selected, path_slot=None)

    def path_io_locations(self, expr, flow, conditional, *, reading=False):
        """Resolve a bounded transfer's ordered records before publishing any writes."""
        while expr['kind'] == 'group':
            expr = expr['args'][0]
        if expr['kind'] != 'path_io_range':
            location = self.locate(expr, flow, conditional, path_io=True, reading=reading)
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
        if flow.stopped and not flow.opaque:
            return []
        spec = path.spec if path is not None else None
        path_operand = spec is not None and spec[0] == 'PATH'
        generation = self.path_descriptor_generation(path, flow) if path_operand else None
        stable_shape = not (flow.opaque or flow.path_shape_unknown)
        with self.capture_operands():
            # WRITE holds the raw descriptor. READ holds a reference and
            # resolves its current descriptor after both bounds have run.
            if not reading and generation is not None:
                self.pending_path_values.append((path.key, generation))
            bounds = self.path_io_bounds(first_arg, last_arg, flow, conditional, argument_path_edits=path_operand)
        if bounds is None:
            return []
        first, last = bounds
        if not self.valid_path_range(spec, first, last, expr):
            return [None]

        current = self.path_descriptor_generation(path, flow)
        replaced = generation != current
        archived = self.retired_path_order(path, generation, flow, conditional) if replaced and not reading else None
        lost_shape = stable_shape and (flow.opaque or flow.path_shape_unknown)
        if current is None or lost_shape or (replaced and not reading and archived is None):
            self.unresolved_at('path-topology', 'PATH range descriptor is unresolved after bound evaluation: '+path.path, expr)
            return [None]
        count = len(archived.nodes) if archived is not None else self.known_path_count(path, flow, conditional)
        indexes = self.path_range_indexes(spec, 32767 if count is None else count, first, last, expr)
        if indexes is None:
            return [None]

        locations = []
        for index in indexes:
            location = (self.index_child(path, index, expr, flow) if archived is None
                        else self.retired_path_child(path, index, expr, flow, archived))
            if location is None:
                return [None]
            if replaced and self.variable_path_storage(location, flow, conditional, archived=archived) is not True:
                self.unresolved_at('path-topology', 'Selected PATH range storage is unresolved: '+location.path, expr)
                return [None]
            locations.append(location)
        for location in locations:
            self.retain_selected_path_storage(location, flow, conditional)
        return locations

    def path_io_bounds(self, first, last, flow, conditional, *, argument_path_edits=False):
        values = []
        for bound in (first, last):
            value = self.expr(bound, flow, conditional, argument_path_edits=argument_path_edits)
            if flow.stopped and not flow.opaque:
                return None
            values.append(value.constant)
        return tuple(values)

    def valid_path_range(self, spec, first, last, node):
        if (spec and spec[0] == 'PATH' and type(first) is int and type(last) is int
                and 0 <= first <= 32767 and 0 <= last <= 32767):
            return True
        self.unresolved_at('selection', 'PATH range requires known bounds and a declared PATH receiver', node)
        return False

    def path_range_indexes(self, spec, count, first, last, node):
        if count is None:
            self.unresolved_at('path-topology', 'PATH result has no proven node count', node)
            return None
        try:
            indexes = path_io_indexes(count, spec[2] is not None, (first, last))
            node_spec = tuple_spec(spec[1]) if spec[1] else rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']
            header = tuple_spec(spec[2]) if spec[2] is not None else None
            fields = path_io_field_count(node_spec, header, indexes)
        except rt.KarelRuntimeError as error:
            self.unresolved_at('path-topology', str(error), node)
            return None
        if fields > MAX_PATH_IO_FIELDS:
            self.unresolved_at('selection', 'PATH range exceeds the bounded FILE transfer limit', node)
            return None
        return indexes

    def stable_path_context(self, loc, flow, conditional):
        return (self.saved_path_count is not None and loc is not None and loc.kind == 'variable'
                and not (flow.opaque or flow.path_shape_unknown or conditional))

    def definite_path_effect(self, flow, conditional):
        return not (flow.opaque or flow.path_shape_unknown or conditional or self.repeat_depth)

    def can_publish_path(self, loc, flow, conditional, *, argument_edit=False):
        if loc is None or not self.definite_path_effect(flow, conditional):
            return False
        if not self.frames:
            return loc.kind in ('variable', 'created-variable')
        current = self.frames[-1]
        return ((loc.kind == 'local' and loc.owner == current['owner'])
                or current['borrowed_path_edits'] or argument_edit and current['argument_path_edits'])

    @contextmanager
    def capture_operands(self):
        """Keep references and raw PATH descriptors alive during evaluation."""
        first = len(self.pending_references)
        first_path = len(self.pending_path_values)
        try:
            yield self.pending_references
        finally:
            del self.pending_references[first:]
            del self.pending_path_values[first_path:]

    def active_path_borrows(self, path):
        depth = len(path.parts)
        for ref in self.pending_references:
            if ref is None or (len(ref.parts) > depth and self.path_contains_reference(path, ref)):
                yield ref
        if self.frames and path.kind == 'local' and path.owner == self.frames[-1]['owner']:
            return
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
            slot = ref.path_slot
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

    def replaced_path_borrows(self, path, flow, conditional, *, keep_header=False, complete_header=False,
                              argument_edit=False):
        """Validate borrowed records and retain the last contents of replaced slots."""
        if not self.can_publish_path(path, flow, conditional, argument_edit=argument_edit):
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
            slot = ref.path_slot
            if slot is not None:
                if slot.key in retired_slots or slot.position == 0 and keep_header:
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
                header = order.header_origin if order is not None else 0
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

    def path_descriptor_generation(self, loc, flow):
        order = flow.path_orders.get(loc.key)
        if order is not None:
            return order.header_generation
        return None if loc.key in flow.path_orders else 0

    def retain_path_descriptor(self, path, flow, conditional, history):
        generation = self.path_descriptor_generation(path, flow)
        key = path.key, generation
        if generation is None or key not in self.pending_path_values:
            return history
        order = flow.path_orders.get(path.key)
        if order is None:
            count = self.known_path_count(path, flow, conditional)
            if count is None:
                return history
            self.tick(count)
            order = _PathOrder(tuple(range(1, count + 1)))
        flow.retired_paths[key] = order
        detached, slots = history
        self.tick(len(detached) + len(order.nodes))
        detached = detached.union(order.nodes)
        if path.spec[2] is not None:
            detached |= {order.header_origin}
        return detached, slots

    def retired_path_order(self, loc, generation, flow, conditional):
        if (generation is not None and flow.path_orders.get(loc.key) is not None
                and self.definite_path_effect(flow, conditional)):
            return flow.retired_paths.get((loc.key, generation))
        return None

    def retired_path_child(self, loc, index, node, flow, order):
        """Select from the old descriptor, including writes through a retired slot."""
        if not 0 <= index <= len(order.nodes):
            self.unresolved_at('path-topology', f'PATH node {index} is outside the captured shape of {loc.path}', node)
            return None
        current = flow.path_orders[loc.key]
        key = order.slot_generation(index), index
        origin = current.retired_slots.get(key, order.header_origin if index == 0 else order.nodes[index - 1])
        if origin is None:
            self.unresolved_at('path-topology', f'Captured PATH slot is out of bounds: {loc.path}[{index}]', node)
            return None
        kind = 'created-header' if index == 0 else 'created-node'
        return self.child(loc, kind, -origin, node) if origin < 0 else self.child(loc, 'index', origin, node)

    def known_path_count(self, loc, flow, conditional):
        if loc is None or flow.opaque or flow.path_shape_unknown or conditional or None in flow.path_orders:
            return None
        if loc.key in flow.path_orders:
            order = flow.path_orders[loc.key]
            return len(order.nodes) if order is not None else None
        if loc.kind == 'created-variable':
            return 0
        if loc.kind == 'local' and any(
            frame['owner'] == loc.owner and loc.root in frame['fresh_path_banks'] for frame in self.frames
        ):
            return 0
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

    def borrow_path_record(self, path, index, record, flow, *, archived=None):
        order = archived if archived is not None else flow.path_orders.get(path.key)
        generation = order.slot_generation(index) if order is not None else 0
        slot = _PathRecordSlot(path, index, generation)
        if archived is not None:
            current = flow.path_orders[path.key]
            origin = _path_record_identity(record.parts[len(path.parts)])
            self.tick(len(current.retired_slots))
            slots = current.retired_slots | {slot.key: origin}
            flow.path_orders[path.key] = replace(current, retired_slots=slots)
        return replace(record, path_slot=slot)

    def named_container_present(self, loc, flow):
        if flow.opaque or flow.task_order_unknown:
            return None
        for end in range(len(loc.parts), -1, -1):
            key = (*loc.key[:3], loc.parts[:end])
            if key in flow.record_storage:
                return flow.record_storage[key]
        if loc.kind == 'created-variable':
            return True
        return self.saved_bindings.container_present(loc.owner, loc.root, loc.parts)

    def check_named_container(self, loc, node, flow):
        present = self.named_container_present(loc, flow)
        if present is True:
            return True
        self.unresolved_at('variable-storage', 'Named variable container is missing or unresolved: '+loc.path, node)
        if present is False:
            flow.stopped = True
        else:
            self.opaque(flow)
        return False

    def checked_task_selection(self, loc):
        # An unresolved cell can hide effects or prevent reaching the pause.
        if loc is None and self.checked_child_segment:
            raise _TaskOrderUnknown()
        return loc

    def locate(self, expr, flow, conditional, *, path_io=False, capture_node=False,
               selector_path_edits=False, reading=False):
        if not isinstance(expr,dict):return None
        kind=expr.get('kind');args=expr.get('args',[])
        if 'token' in expr:return self.slot(expr['token'],expr,flow,capture_node=capture_node)
        if kind=='name':return self.slot(expr['value'],expr,flow,capture_node=capture_node)
        if kind=='group':
            return self.locate(args[0], flow, conditional, path_io=path_io, capture_node=capture_node,
                               selector_path_edits=selector_path_edits, reading=reading)
        if kind=='field':
            base=self.locate(args[0],flow,conditional)
            if base is not None and base.named_data and not self.check_named_container(base, expr, flow):
                return None
            selected = self.field_child(base, expr['value'], expr, flow) if base else None
            return self.checked_task_selection(selected)
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
            saved_parents = []
            saved_revision = self.named_storage_revision
            # A plain scalar array's subscript does not hold an untracked PATH receiver.
            safe_selector = False
            if selector_path_edits and loc is not None and not loc.parts and loc.spec[0] == 'ARRAY':
                _, element = _array_dimensions(loc.spec)
                safe_selector = element[0] in SCALARS
            for position, argument in enumerate(args[1:], 1):
                if loc is not None and loc.named_data:
                    saved_parents.append(loc)
                path_base = loc is not None and loc.spec[0] == 'PATH'
                generation = self.path_descriptor_generation(loc, flow) if path_base else None
                stable_shape = path_base and not (flow.opaque or flow.path_shape_unknown)
                # Flattened indexes look up the PATH after all subscripts.
                # Aggregate transfers with a header lower to a separate PATH
                # operand: WRITE loads it, while READ passes a reference.
                separate_transfer = path_base and path_io and loc.spec[2] is not None
                captures_path = path_base and (not reading if separate_transfer else position == 1)
                with self.capture_operands():
                    if captures_path and generation is not None:
                        self.pending_path_values.append((loc.key, generation))
                    index=self.expr(argument,flow,conditional,argument_path_edits=safe_selector or path_base).constant
                archived = None
                current_generation = self.path_descriptor_generation(loc, flow) if path_base else None
                replaced = generation != current_generation
                if stable_shape and (flow.opaque or flow.path_shape_unknown):
                    self.unresolved_at('path-topology', 'PATH descriptor became unresolved during index evaluation: '+loc.path, expr)
                    loc = None
                elif replaced:
                    if captures_path:
                        archived = self.retired_path_order(loc, generation, flow, conditional)
                    if current_generation is None or (captures_path and archived is None):
                        self.unresolved_at('path-topology', 'PATH descriptor changed or became unresolved during index evaluation: '+loc.path, expr)
                        loc = None
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
                        if archived is None:
                            selected = self.index_child(loc, index, expr, flow)
                        else:
                            selected = self.retired_path_child(loc, index, expr, flow, archived)
                        if replaced and selected is not None and self.variable_path_storage(
                                selected, flow, conditional, archived=archived) is not True:
                            self.unresolved_at('path-topology', 'Selected PATH record storage is unresolved: '+selected.path, expr)
                            selected = None
                        if (selected is not None and capture_node and position == len(args) - 1
                                and loc.spec[0] == 'PATH' and index >= 0):
                            selected = self.borrow_path_record(loc, index, selected, flow, archived=archived)
                        loc = selected
            if saved_parents and saved_revision != self.named_storage_revision:
                self.unresolved_at('variable-storage', 'Saved aggregate storage may change during index evaluation', expr)
                self.opaque(flow)
                return None
            if any(not self.check_named_container(parent, expr, flow) for parent in saved_parents):
                return None
            return self.checked_task_selection(loc)
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
            fields = self.record_fields(current)
            if fields is None:return False
            return all(visit(self.child(current,'field',name,{})) for name in fields)
        return leaves if visit(loc) else None

    def leaf_uninitialized(self, loc, flow):
        key = loc.key
        if (key in flow.defined or flow.opaque or flow.task_order_unknown or self.callback_depth
                or loc.spec == ['BYTE']):
            return False
        if key in flow.uninitialized:
            return True
        return key not in flow.maybe and (loc.kind in ('local', 'created-variable') or any(
            kind in ('created-node', 'created-header') for kind, _ in loc.parts
        ))

    def read(self, loc, node, flow, conditional, *, partial=False, path_io=False, raw_scalar=False):
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
        if partial and _path_array_cell_type(loc.spec):
            return self.capture_path_array(loc, node, flow, conditional)
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
        scalar = loc.spec and loc.spec[0] in SCALARS
        partial_copy = raw_scalar or partial and loc.spec and not scalar
        if missing:
            initial=missing-flow.assigned
            if any(kind in ('created-node', 'created-header') for kind, _ in loc.parts):
                if not partial_copy:
                    self.unresolved_at('derived-value', 'Source-created PATH data may be uninitialized: '+loc.path, node)
            elif not initial:
                if not partial_copy:self.unresolved_at('derived-value','Read follows a write whose complete value is not proven: '+loc.path,node)
            elif loc.kind == 'created-variable':
                if not partial_copy:
                    self.unresolved_at('derived-value', 'Source-created variable is read before initialization: '+loc.path, node)
            elif loc.kind=='local':
                if not partial_copy:self.unresolved_at('local-value','Fresh routine-local value is read before initialization: '+loc.path,node)
            else:
                uncertain=conditional or self.checked_child_segment or flow.opaque or bool(missing & flow.maybe)
                key=loc.key;certainty='conditional' if uncertain else 'required'
                if key not in self.inputs:
                    if len(self.inputs)>=MAX_INPUTS:raise _Limit('Analysis input limit reached')
                    spec=None if loc.spec==['NUMERIC'] else loc.spec
                    initial_certainty = certainty if self.required_input_observer is None else 'conditional'
                    self.inputs[key]=dict(kind=loc.kind,program=loc.owner or None,path=loc.path,type=spec,
                                          certainty=initial_certainty,locations=[],reason='Read before a definite source write')
                    if loc.kind=='variable':
                        self.inputs[key].update(program=loc.owner, root_path=str(loc.root),
                                                root_type=loc.root_spec, selectors=list(loc.parts))
                    elif loc.kind=='port':
                        self.inputs[key].update(port=loc.root,index=dict(loc.parts).get('index'))
                    elif loc.kind.endswith('_register') or loc.kind in TEACH_POSITION_SECTIONS or loc.kind in TEACH_SCALAR_SECTIONS:
                        self.inputs[key]['index']=loc.root
                        if loc.kind == 'position_register' or loc.kind in TEACH_POSITION_SECTIONS:
                            self.inputs[key]['group'] = dict(loc.parts).get('group')
                        if loc.spec==['NUMERIC']:self.inputs[key]['type_options']=[['INTEGER'],['REAL']]
                row=self.inputs[key]
                if certainty=='required':
                    if self.required_input_observer is None:
                        row['certainty']='required'
                    else:
                        self.required_input_observer.add(key)
                location=self.where(node)
                if location not in row['locations']:row['locations'].append(location)
        # Saved binding values remain editable inputs. Only their initial
        # availability participates in proving the receiver of a copy.
        initialized = flow.defined
        if loc.saved_binding and missing and not (flow.opaque or flow.task_order_unknown or self.callback_depth):
            supplied = {leaf.key for leaf in leaves if leaf.key in missing and leaf.key not in flow.maybe
                        and self.saved_bindings.leaf_initialized(leaf.owner, leaf.root, leaf.parts)}
            initialized = initialized | supplied
        # A scalar read has a value if execution continues. Aggregate copies can
        # preserve missing leaves, so they do not establish complete receivers.
        complete = keys <= initialized or bool(scalar and not raw_scalar)
        facts=None
        if loc.spec and loc.spec[0] not in SCALARS:
            facts = {
                leaf.parts[len(loc.parts):]: _Value(
                    flow.constants.get(leaf.key, UNKNOWN) if leaf.key in flow.defined else UNKNOWN,
                    leaf.key in initialized, leaf.spec, uninitialized=self.leaf_uninitialized(leaf, flow),
                    scalar_choices=flow.scalar_choices.get(leaf.key, ()) if leaf.key in flow.defined else (),
                )
                for leaf in leaves
            }
        uninitialized = bool(scalar and raw_scalar and self.leaf_uninitialized(loc, flow))
        return _Value(flow.constants.get(loc.key, UNKNOWN) if loc.key in flow.defined else UNKNOWN,
                      complete, loc.spec, facts, uninitialized=uninitialized,
                      scalar_choices=flow.scalar_choices.get(loc.key, ()) if loc.key in flow.defined else ())

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
            if value.spec != loc.spec:
                fact.constant = UNKNOWN
                fact.scalar_choices = ()
            facts[key]=fact
        return _Value(stored.constant,all(fact.complete for fact in facts.values()),loc.spec,facts)

    def update_record_storage(self, loc, value, flow, definite, shaped_record):
        """Forget overwritten shapes and publish current whole-record markers."""
        if flow.opaque or loc.spec[0] in SCALARS:
            return
        saved_data = loc.named_data
        if saved_data:
            self.named_storage_revision += 1
        shaped = definite and (value.complete or shaped_record and not saved_data)
        key = loc.key
        tracked = key in flow.record_storage
        self.tick(len(flow.record_storage))
        for prior in tuple(flow.record_storage):
            if prior[:3] != key[:3]:
                continue
            if prior[3][:len(loc.parts)] == loc.parts:
                del flow.record_storage[prior]
            elif not shaped and loc.parts[:len(prior[3])] == prior[3]:
                flow.record_storage[prior] = None
        if saved_data or (loc.spec[0] == 'STRUCTURE' and (tracked or shaped_record or value.whole_record_missing
                                                         or self.whole_path_record(loc))):
            state = True if shaped else False if definite and value.whole_record_missing else None
            flow.record_storage[key] = state
            if len(flow.record_storage) > MAX_FACTS:
                raise _Limit('Analysis storage limit reached')
            if state is True and flow.changed_path_aggregates:
                self.tick(len(flow.changed_path_aggregates))
                flow.changed_path_aggregates = {old for old in flow.changed_path_aggregates
                                                if old[:3] != key[:3] or old[3][:len(loc.parts)] != loc.parts}

    def write(self, loc, value, flow, node, *, definite=True, track_path_storage=True, shaped_record=False):
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
        if (loc.named_data and loc.spec[0] not in SCALARS and not (definite and value.complete)
                and any(True for _ in self.active_path_borrows(loc))):
            self.unresolved_at('variable-storage', 'Named aggregate write may detach borrowed fields: '+loc.path, node)
            self.opaque(flow)
            return
        self.update_record_storage(loc, value, flow, definite, shaped_record)
        if loc.spec[0] not in SCALARS and track_path_storage and not (definite and (value.complete or shaped_record)):
            dimensions, terminal = _array_dimensions(loc.root_spec)
            if terminal and terminal[0] == 'PATH' and len(loc.parts) > len(dimensions):
                record = loc.parts[len(dimensions)]
                # Indexed PATH ARRAY nodes validate the entire record at lookup.
                parts = loc.parts[:len(dimensions) + 1] if dimensions and not _path_header_part(record) else loc.parts
                flow.changed_path_aggregates.add((*loc.key[:3], parts))
                if len(flow.changed_path_aggregates) > MAX_FACTS:
                    raise _Limit('Analysis storage limit reached')
        stored=self.stored(loc,value,leaves,node)
        for leaf in leaves:
            key=leaf.key;flow.maybe.add(key);flow.constants.pop(key,None)
            flow.scalar_choices.pop(key, None)
            fact=stored.facts.get(leaf.parts[len(loc.parts):],_Value(complete=False)) if stored.facts is not None else stored
            if not fact.complete:flow.defined.discard(key)
            if definite or not fact.uninitialized:
                flow.uninitialized.discard(key)
            if definite:
                if not flow.opaque:flow.assigned.add(key)
                flow.defined.discard(key)
                if fact.complete and not flow.opaque:flow.defined.add(key)
                if fact.uninitialized and not flow.opaque:flow.uninitialized.add(key)
                if not flow.opaque:
                    if fact.constant is not UNKNOWN:
                        flow.constants[key] = fact.constant
                    elif fact.complete and fact.scalar_choices:
                        flow.scalar_choices[key] = fact.scalar_choices
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

    def result_value(self,value,node,partial,*,path_io=False):
        if path_io:
            self.check_path_array_output(value, node)
        if not partial and value.spec and value.spec[0] not in SCALARS and not value.complete:
            self.unresolved_at('derived-value','Aggregate result consumed without proven complete data',node)
        return value

    def selects_routine_result(self, receiver):
        """Recognize selectors on detached results without probing live storage."""
        while receiver['kind'] in ('group', 'field', 'index'):
            receiver = receiver['args'][0]
        kind = receiver['kind']
        if kind == 'wait_sample':
            sample = receiver['value']
            return isinstance(sample, _Value) and sample.spec and sample.spec[0] in TASK_DATA_AGGREGATES
        if kind == 'binary' and receiver['value'] == ':':
            return True
        if kind not in ('call', 'name'):
            return False
        name = receiver['value']
        if kind == 'name' and (name in self.plan['types'] or name in self.plan['constants']
                               or self.frames and (name in self.frames[-1]['slots']
                                                   or name in self.frames[-1]['constants'])):
            return False
        result = self.plan['routines'].get(name, {}).get('result')
        if kind == 'call' and name not in self.plan['routines']:
            result = POSITION_GETTERS.get(name) or TEACH_POSITION_GETTERS.get(name) or ROBOT_SNAPSHOTS.get(name)
            if name in POSE_CONSTRUCTORS:
                return True
        return bool(result and result[0] in (*rt.RECORD_TYPES, 'ARRAY', 'JOINTPOS', 'PATH'))

    def select_result_member(self, value, kind, key, node):
        if value.spec is None:
            return _Value(complete=False)
        location = _Location('local', self.program, 'routine result', spec=value.spec)
        member = self.child(location, kind, key, node)
        if member is None:
            return _Value(complete=False)
        facts = value.facts or {}
        if member.spec[0] == 'PATH':
            return facts.get(member.parts, _Value(complete=False, spec=member.spec))
        if member.spec[0] in SCALARS:
            return facts.get(member.parts, _Value(complete=value.complete, spec=member.spec))
        selected = {path[1:]: fact for path, fact in facts.items() if path[:1] == member.parts}
        complete = all(fact.complete for fact in selected.values()) if selected else value.complete
        return _Value(complete=complete, spec=member.spec, facts=selected or None,
                      uninitialized=any(fact.uninitialized for fact in selected.values()))

    def select_result_record(self, value, index, node):
        if value.path_records is None:
            self.unresolved_at('path-topology', 'PATH result has no proven node count', node)
            return _Value(complete=False)
        has_header = value.spec[2] is not None
        count = len(value.path_records) - has_header
        try:
            path_io_indexes(count, has_header, (index, None))
        except rt.KarelRuntimeError as error:
            self.unresolved_at('path-topology', str(error), node)
            return _Value(complete=False)
        return value.path_records[index if has_header else index - 1]

    def routine_result_selection(self, node, flow, conditional, *, path_io=False):
        kind = node['kind']
        receiver, *arguments = node['args']
        value = self.expr(receiver, flow, conditional, partial=True)
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        if kind == 'field':
            if value.spec and value.spec[0] == 'PATH':
                value = self.select_result_record(value, 0, node)
            value = self.select_result_member(value, 'field', node['value'], node)
        else:
            indexes = []
            for argument in arguments:
                indexes.append(self.expr(argument, flow, conditional).constant)
                if flow.stopped and not flow.opaque:
                    return _Value(complete=False)
            for position, index in enumerate(indexes, 1):
                if type(index) is not int:
                    self.unresolved_at('dynamic-address', 'Routine result index is not statically known', node)
                    return _Value(complete=False)
                if value.spec and value.spec[0] == 'PATH':
                    header_allowed = position == len(arguments) and (
                        node.get('static_zero_subscript') or path_io and self.plan.get('path_index_io')
                    )
                    if index == 0 and not header_allowed:
                        self.unresolved_at('selection', 'PATH header requires a statically selected zero subscript', node)
                        return _Value(complete=False)
                    value = self.select_result_record(value, index, node)
                else:
                    value = self.select_result_member(value, 'index', index, node)
        return value

    def path_result_range(self, node, flow, conditional):
        receiver, first_arg, last_arg = node['args']
        value = self.expr(receiver, flow, conditional, partial=True)
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        bounds = self.path_io_bounds(first_arg, last_arg, flow, conditional,
                                     argument_path_edits=value.path_records is not None)
        if bounds is None or not self.valid_path_range(value.spec, *bounds, node):
            return _Value(complete=False)
        first, last = bounds
        has_header = value.spec[2] is not None
        count = len(value.path_records) - has_header if value.path_records is not None else None
        indexes = self.path_range_indexes(value.spec, count, first, last, node)
        if indexes is None:
            return _Value(complete=False)
        complete = all(value.path_records[index if has_header else index - 1].complete for index in indexes)
        if not complete:
            self.unresolved_at('derived-value', 'Selected PATH result range has unproven data', node)
        return _Value(complete=complete)

    def expr(self, node, flow, conditional=False, *, partial=False, path_io=False,
             statement_call=False, raw_scalar=False, argument_path_edits=False):
        self.tick()
        if not isinstance(node,dict):return _Value()
        kind=node.get('kind');args=node.get('args',[]);value=node.get('value')
        if kind=='literal':return _Value(value)
        if kind=='wait_sample':return value
        if kind=='real_literal':
            try:return _Value(float(value))
            except ValueError:return _Value()
        if kind=='predefined':return _Value(PREDEFINED_CONSTANTS.get(value,UNKNOWN))
        if kind=='name':
            loc=self.slot(value,node,flow)
            if loc:
                return self.read(loc, node, flow, conditional, partial=partial, path_io=path_io,
                                 raw_scalar=raw_scalar)
            constant=self.constant(value)
            if constant is not UNKNOWN:return _Value(constant)
            if value in self.plan['routines']:
                result = self.call(dict(node, kind='call', args=[]), flow, conditional, statement_call=statement_call,
                                   argument_path_edits=argument_path_edits)
                return self.result_value(result, node, partial, path_io=path_io)
        if kind == 'path_io_range':
            if self.selects_routine_result(args[0]):
                return self.path_result_range(node, flow, conditional)
            for location in self.path_io_locations(node, flow, conditional):
                if location is not None:
                    self.read(location, node, flow, conditional)
            return _Value(complete=False)
        if kind in ('system_pose', 'system_selection', 'field'):
            root, fields = self.robot_table_path(node)
            if root['kind'] in ('system_pose', 'system_selection'):
                return self.robot_table_expression(root, fields, node, flow, conditional)
        if kind in ('field','index'):
            if self.selects_routine_result(args[0]):
                selected = self.routine_result_selection(node, flow, conditional, path_io=path_io)
                if path_io:
                    self.check_path_array_output(selected, node)
                if selected.spec and not selected.complete and (not partial or selected.spec[0] in SCALARS):
                    self.unresolved_at('derived-value', 'Selected routine result has unproven data', node)
                return selected
            loc=self.locate(node,flow,conditional,path_io=path_io)
            if loc:
                return self.read(loc, node, flow, conditional, partial=partial, path_io=path_io,
                                 raw_scalar=raw_scalar)
            self.unresolved_at('selection','Computed or dynamic data read is unresolved',node);return _Value(complete=False)
        if kind == 'group':
            return self.expr(args[0], flow, conditional, partial=partial, path_io=path_io,
                             statement_call=statement_call, raw_scalar=raw_scalar,
                             argument_path_edits=argument_path_edits)
        if kind == 'binary' and value in (':', '>=<'):
            return self.pose_constructor_call(node, flow, conditional)
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
            result = self.call(node, flow, conditional, statement_call=statement_call,
                               argument_path_edits=argument_path_edits)
            return self.result_value(result, node, partial, path_io=path_io)
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
        values=[]
        for item in node['args']:
            if flow.stopped and not flow.opaque:return _Value(complete=False)
            values.append(self.expr(item,flow,conditional))
        return self.scalar_builtin_result(node, values, complete=not flow.stopped)

    def scalar_builtin_result(self, node, values, *, complete=True):
        """Fold only bounded known scalars through the translator's pure helpers."""
        name = node['value']
        if len(values) != SCALAR_PURE[name]:
            self.unresolved_at('scalar-call','Invalid checked scalar builtin arity: '+name,node)
            return _Value(complete=False)
        complete=complete and all(value.complete for value in values)
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

    def metadata_operand(self, target, flow, conditional):
        while target['kind'] == 'group':
            target = target['args'][0]
        kind = target['kind']
        if self.selects_routine_result(target):
            value = (self.routine_result_selection(target, flow, conditional)
                     if kind in ('field', 'index') else self.expr(target, flow, conditional, partial=True))
            return None, value
        if kind in ('name', 'field', 'index'):
            return self.locate(target, flow, conditional), None
        return None, self.expr(target, flow, conditional, partial=True)

    def data_metadata_call(self, node, flow, conditional):
        name = node['value']
        target, *arguments = node['args']
        loc, value = self.metadata_operand(target, flow, conditional)
        spec = loc.spec if loc is not None else value.spec if value is not None else None
        result = _Value(spec=['BOOLEAN'] if name == 'UNINIT' else ['INTEGER'])
        if flow.stopped and not flow.opaque:
            return result
        if name == 'ARRAY_LEN':
            dimension = self.expr(arguments[0], flow, conditional).constant if arguments else 1
            if spec and spec[0] == 'ARRAY' and not (flow.stopped and not flow.opaque):
                dimensions, _ = _array_dimensions(spec)
                if type(dimension) is int and 1 <= dimension <= len(dimensions):
                    size = dimensions[dimension - 1]
                    if type(size) is int:
                        result.constant = size
            return result
        # One abstract visit cannot determine the state at every loop or scan.
        if flow.opaque or flow.task_order_unknown or self.callback_depth or self.repeat_depth:
            return result
        if value is not None:
            if _known_missing(value):
                result.constant = True
            elif value.complete and value.spec:
                result.constant = False
        elif (loc is not None and loc.kind in ('variable', 'local', 'created-variable') and spec[0] not in ('FILE', 'QUEUE_TYPE')
              and not self.lost_path_reference(loc, flow)):
            leaves = self.leaves(loc)
            if leaves is not None:
                if flow.record_storage.get(loc.key) is False or any(self.leaf_uninitialized(leaf, flow) for leaf in leaves):
                    result.constant = True
                elif all(leaf.key in flow.defined for leaf in leaves):
                    result.constant = False
        return result

    def path_metadata_call(self, node, flow, conditional):
        name = node['value']
        target, = node['args']
        loc, value = self.metadata_operand(target, flow, conditional)
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

    def path_service_overlap(self, path, status, flow, conditional):
        """Check the receiver's live cells against an already captured status."""
        if path is None or path.spec[0] != 'PATH' or status is None:
            return None
        if not self.path_contains_reference(path, status):
            return False
        depth = len(path.parts)
        if len(status.parts) <= depth + 1 or not self.definite_path_effect(flow, conditional):
            return None
        part = status.parts[depth]
        origin = _path_record_identity(part)
        order = flow.path_orders.get(path.key)
        if order is None:
            if _path_header_part(part):
                live = path.spec[2] is not None and origin == 0
            else:
                count = self.known_path_count(path, flow, conditional)
                live = count is not None and origin is not None and 1 <= origin <= count
        else:
            self.tick(len(order.nodes))
            live = origin == order.header_origin if _path_header_part(part) else origin in order.nodes
            if not live:
                self.tick(len(order.retired_slots))
                if origin in order.detached or origin in order.retired_slots.values():
                    return False
        if live and self.variable_path_storage(status, flow, conditional) is True:
            return True
        return None

    def path_seed_layout(self, path, seed, convert):
        if seed is None:
            return 'exact'
        target = self.path_node_schema(path)
        if not target or not seed.spec:
            return None
        target, source = tuple_spec(target), tuple_spec(seed.spec)
        if source == target:
            return 'exact'
        if convert is True:
            if rt.record_schema_kind(target, source) == 'structure':
                return 'structure'
            if rt.kinematic_record_kind(target, source) == 'structure':
                return 'kinematic'
            return 'rejected'
        return 'rejected' if convert is False else None

    def convert_path_seed(self, target, seed, node, flow, layout):
        # Continuing past the source capture requires every source field.
        seed = self.complete_path_record(seed)
        try:
            if layout == 'kinematic':
                operation = node['value']+' seed conversion'
                robot = self.selected_robot_for_discovery(operation, node, flow)
                raw = materialized_value(seed)
                if raw is UNKNOWN:
                    raise RobotFactsUnavailable(operation+' needs known source data at run time')
                converted = detached_facts(evaluate_robot_aggregate(
                    robot, 'kinematic_record', tuple_spec(target), raw, node.get('line'), self.tick,
                    operation=operation,
                ))
            else:
                converted = self.convert_path_record(target, seed, node)
        except RobotFactsUnavailable as error:
            self.unresolved_at('path-conversion', str(error), node)
            return None
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('path-conversion', str(error), node)
            flow.stopped = True
            return None
        if _known_missing(converted):
            self.unresolved_at('path-conversion', 'Converted PATH seed has an uninitialized field', node)
            flow.stopped = True
            return None
        return self.complete_path_record(converted)

    def path_edit(self, node, flow, conditional, *, task_segment=False):
        name = node['value']
        path_arg, *operands = node['args']
        path = self.locate(path_arg, flow, conditional)
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        known_receiver = (path is not None and path.spec[0] == 'PATH'
                          and self.path_descriptor_generation(path, flow) is not None)
        index = None
        if name != 'APPEND_NODE':
            index_arg, *operands = operands
            index = self.expr(index_arg, flow, conditional, argument_path_edits=known_receiver).constant
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        seed = None
        flags = []
        if len(operands) > 1:
            seed_arg, status_arg, *flags = operands
            seed = self.expr(seed_arg, flow, conditional, partial=True, argument_path_edits=known_receiver)
            if _known_missing(seed):
                self.unresolved_at('path-seed', 'PATH node seed requires all source fields initialized', seed_arg)
                flow.stopped = True
        else:
            status_arg = operands[-1]
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        with self.capture_operands() as pending:
            status = self.locate(status_arg, flow, conditional, selector_path_edits=known_receiver)
            if flow.stopped and not flow.opaque:
                return _Value(complete=False)
            pending.append(status)
            convert = self.expr(flags[0], flow, conditional, argument_path_edits=known_receiver).constant if flags else None
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)

        conditional_effect = conditional and not task_segment
        overlap = self.path_service_overlap(path, status, flow, conditional_effect)
        if overlap is True:
            return self.reject_service_overlap(node, flow)
        count = self.known_path_count(path, flow, conditional_effect) if path is not None and path.spec[0] == 'PATH' else None
        if count is not None and overlap is False and not self.repeat_depth:
            removing = name == 'DELETE_NODE'
            last = count if removing else count + 1
            if name == 'APPEND_NODE':
                index = last
            layout = self.path_seed_layout(path, seed, convert)
            if layout == 'rejected':
                self.write(status, _Value(3, spec=['INTEGER']), flow, node)
                return _Value()
            if layout is not None and type(index) is int and (removing or count < 32767):
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
                if layout == 'kinematic':
                    self.context('robot', None)
                owned_child_path = (task_segment and path.kind == 'variable' and path.owner == self.task_roots[-1]
                                    and self.definite_path_effect(flow, conditional_effect))
                if ((owned_child_path or self.can_publish_path(path, flow, conditional_effect, argument_edit=True))
                        and self.node_edit_preserves_borrows(path, order, prefix, shifted, removed)):
                    detached = order.detached
                    inserted = order.inserted
                    if removing:
                        depth = len(path.parts)
                        if any(ref is not None and len(ref.parts) > depth + 1
                               and _path_record_identity(ref.parts[depth]) == removed
                               for ref in self.active_path_borrows(path)):
                            self.tick(len(detached))
                            detached = detached | {removed}
                        nodes = prefix + shifted
                        if removed in inserted and removed not in detached:
                            self.tick(len(inserted))
                            inserted = inserted - {removed}
                    else:
                        node_type = self.path_node_schema(path)
                        value = (_Value(complete=False, spec=node_type, uninitialized=True) if seed is None
                                 else self.convert_path_seed(node_type, seed, node, flow, layout))
                        if value is None:
                            if flow.stopped:
                                return _Value(complete=False)
                            return self.unknown_path_edit(path, status, node, flow)
                        self.serial += 1
                        nodes = prefix + (-self.serial,) + shifted
                        self.tick(len(inserted))
                        inserted = inserted | {-self.serial}
                        record = self.child(path, 'created-node', self.serial, node)
                        self.write(record, value, flow, node, track_path_storage=False, shaped_record=True)
                    flow.path_orders[path.key] = replace(
                        order, nodes=nodes, detached=detached,
                        previous_max_size=max(order.previous_max_size, count), inserted=inserted,
                    )
                    self.write(status, _Value(0, spec=['INTEGER']), flow, node)
                    return _Value()

        return self.unknown_path_edit(path, status, node, flow)

    def unknown_path_edit(self, path, status, node, flow):
        flow.path_orders[path.key if path is not None else None] = None
        self.unresolved_at('path-topology', node['value']+' may change PATH topology or captured node references', node)
        self.opaque(flow)
        self.write(status, _Value(), flow, node)
        return _Value()

    def reject_service_overlap(self, node, flow, message='Service output/resource references must not overlap'):
        self.unresolved_at('service-output', message, node)
        flow.stopped = True
        return _Value(complete=False)

    def path_copy(self, node, flow, conditional):
        operands = []
        source_generation = None
        known_source = False
        with self.capture_operands() as pending:
            for index, argument in enumerate(node['args']):
                if flow.stopped and not flow.opaque:
                    return _Value(complete=False)
                if index == 0:
                    loc, value = self.metadata_operand(argument, flow, conditional)
                    operands.append(loc if loc is not None else value)
                    if loc is not None and loc.spec[0] == 'PATH':
                        source_generation = self.path_descriptor_generation(loc, flow)
                        if source_generation is not None:
                            self.pending_path_values.append((loc.key, source_generation))
                    known_source = source_generation is not None or value is not None and value.path_records is not None
                elif index in (3, 4):
                    loc = self.locate(argument, flow, conditional, selector_path_edits=index == 4 and known_source)
                    pending.append(loc)
                    operands.append(loc)
                else:
                    value = self.expr(argument, flow, conditional, argument_path_edits=known_source)
                    operands.append(value.constant)
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        source, first, last, target, status, *flags = operands
        convert = flags[0] if flags else False
        overlap = self.path_service_overlap(target, status, flow, conditional)
        if overlap is True:
            return self.reject_service_overlap(node, flow)
        archived = None
        if (isinstance(source, _Location) and source.spec[0] == 'PATH'
                and source_generation != self.path_descriptor_generation(source, flow)):
            archived = self.retired_path_order(source, source_generation, flow, conditional)
            if archived is None:
                self.unresolved_at('path-topology', 'COPY_PATH source descriptor changed or became unresolved during argument evaluation', node)
                self.opaque(flow)
                return _Value()
        if (source is not None and source.spec and source.spec[0] == 'PATH'
                and overlap is False and self.definite_path_effect(flow, conditional)):
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

            if isinstance(source, _Location):
                count = len(archived.nodes) if archived is not None else self.known_path_count(source, flow, conditional)
            else:
                count = (len(source.path_records) - (source.spec[2] is not None)
                         if source.path_records is not None else None)
            if layout and count is not None and type(first) is int and type(last) is int:
                if first == last == 0:
                    indexes = range(1, count + 1)
                elif 1 <= first <= count and 1 <= last <= count:
                    step = 1 if first <= last else -1
                    indexes = range(first, last + step, step)
                else:
                    self.write(status, _Value(2, spec=['INTEGER']), flow, node)
                    return _Value()
                history = self.replaced_path_borrows(target, flow, conditional, argument_edit=True)
                if history is not None:
                    argument_copy = not self.can_publish_path(target, flow, conditional)
                    captured = self.capture_path_copy(source, indexes, node, flow, conditional,
                                                      require_storage=argument_copy, archived=archived)
                    if captured is not None and (target.spec[1] or self.plan.get('default_path_node')
                                                 or not len(indexes) or target.spec == source.spec):
                        snapshot = _Value(spec=source.spec, path_records=tuple(captured),
                                          complete=all(record.complete for record in captured))
                        try:
                            value, = self.convert_captured_paths(
                                target.spec, [snapshot], layout, len(indexes), node, flow,
                                operation='COPY_PATH conversion', allow_missing=False,
                            )
                        except RobotFactsUnavailable as error:
                            self.unresolved_at('path-conversion', str(error), node)
                        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
                            self.unresolved_at('path-conversion', str(error), node)
                            flow.stopped = True
                            return _Value(complete=False)
                        else:
                            history = self.retain_path_descriptor(target, flow, conditional, history)
                            self.publish_path_records(target, value.path_records, node, flow, history=history)
                            self.write(status, _Value(0, spec=['INTEGER']), flow, node)
                            return _Value()

        flow.path_orders[target.key if target is not None else None] = None
        self.unresolved_at('path-topology', 'COPY_PATH layout, bounds or destination effects require review', node)
        self.opaque(flow)
        self.write(status, _Value(), flow, node)
        return _Value()

    def path_array_cells(self, loc, node):
        self.tick()
        if loc.spec[0] == 'PATH':
            yield loc
            return
        size = loc.spec[1][0] if type(loc.spec[1]) is list else loc.spec[1]
        for index in range(1, size + 1):
            yield from self.path_array_cells(self.child(loc, 'index', index, node), node)

    def path_array_prefix_owner(self, loc):
        depth = len(loc.parts)
        spec = loc.root_spec
        first = 0
        while spec and spec[0] == 'ARRAY' and first < depth:
            rank = len(spec[1]) if type(spec[1]) is list else 1
            if first < depth < first + rank:
                return replace(loc, parts=loc.parts[:first], spec=spec)
            first += rank
            spec = spec[2]
        return loc

    def path_array_layout(self, loc, node, flow, conditional):
        """Check the snapshot budget, including the owner of a row or plane."""
        owner = self.path_array_prefix_owner(loc)
        try:
            units = collection_array_cost(tuple_spec(owner.spec))
        except ValueError as error:
            self.unresolved_at('path-schema', 'PATH ARRAY snapshot requires a proven concrete shape: '+str(error), node)
            return None
        terminal = tuple_spec(_path_array_cell_type(loc.spec))
        width = rt.scalar_leaf_count(terminal[1] or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE'])
        selected = []
        for cell in self.path_array_cells(owner, node):
            count = self.known_path_count(cell, flow, conditional)
            if count is None and owner is not loc:
                self.unresolved_at('path-topology', 'PATH ARRAY prefix has an unproven containing bank shape', node)
                return None
            if count is not None:
                units += count * width
                if units > MAX_FACTS:
                    self.unresolved_at('limit', 'PATH ARRAY value exceeds the scalar snapshot limit', node)
                    return None
            if cell.parts[:len(loc.parts)] == loc.parts:
                selected.append((cell, count))
        return selected

    def capture_path_array(self, loc, node, flow, conditional):
        """Capture detached cells only after checking the snapshot budget."""
        selected = self.path_array_layout(loc, node, flow, conditional)
        if selected is None:
            return _Value(complete=False, spec=loc.spec)
        cells = {}
        for cell, count in selected:
            records = self.capture_path_copy(cell, range(1, count + 1), node, flow, conditional) if count is not None else None
            cells[cell.parts[len(loc.parts):]] = _Value(
                complete=records is not None and all(record.complete for record in records),
                spec=cell.spec,
                path_records=tuple(records) if records is not None else None,
            )
        return _Value(complete=all(cell.complete for cell in cells.values()), spec=loc.spec, facts=cells)

    def check_path_array_output(self, value, node):
        if not _path_array_cell_type(value.spec):
            return
        if value.facts is None or any(cell.path_records is None for cell in value.facts.values()):
            self.unresolved_at('path-topology', 'PATH ARRAY result has unproven cell topology', node)
            return
        count = 0
        for cell in value.facts.values():
            for record in cell.path_records:
                count += rt.scalar_leaf_count(tuple_spec(record.spec), MAX_PATH_IO_FIELDS)
                if count > MAX_PATH_IO_FIELDS:
                    self.unresolved_at('selection', 'PATH ARRAY result exceeds the bounded FILE transfer limit', node)
                    return

    def convert_path_array_value(self, target, value, node, flow):
        resolved = _array_value_schema(target, value.spec)
        if resolved and _path_array_cell_type(value.spec):
            actual = tuple_spec(value.spec)
            if rt.collection_array_source_accepts(tuple_spec(target), actual):
                return replace(value, spec=resolved)
            layout = rt.path_array_conversion_layout(tuple_spec(resolved), actual)
            if layout is not None and value.facts and all(cell.path_records is not None for cell in value.facts.values()):
                return self.convert_path_array_cells(resolved, value, layout, node, flow)
        self.unresolved_at('path-schema', 'PATH ARRAY value requires compatible cell layouts and proven dimensions', node)
        self.opaque(flow)
        return _Value(complete=False, spec=target)

    def convert_path_array_cells(self, target, value, layout, node, flow):
        cell_type = _path_array_cell_type(target)
        has_header = cell_type[2] is not None
        count = sum(len(cell.path_records) - has_header for cell in value.facts.values())
        node_type = tuple_spec(cell_type[1]) if cell_type[1] else rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']
        try:
            units = collection_array_cost(tuple_spec(target))
        except ValueError as error:
            self.unresolved_at('path-schema', str(error), node)
            self.opaque(flow)
            return _Value(complete=False, spec=target)
        if units + count * rt.scalar_leaf_count(node_type) > MAX_FACTS:
            self.unresolved_at('limit', 'PATH ARRAY conversion target exceeds the scalar snapshot limit', node)
            flow.stopped = True
            return _Value(complete=False, spec=target)
        if count and cell_type[1] is None and not self.plan.get('default_path_node'):
            self.unresolved_at('path-schema', 'Retranslate to include default NODEDATA for PATH ARRAY conversion', node)
            self.opaque(flow)
            return _Value(complete=False, spec=target)
        try:
            converted = self.convert_captured_paths(
                cell_type, value.facts.values(), layout, count, node, flow, operation='PATH ARRAY conversion',
            )
        except RobotFactsUnavailable as error:
            self.unresolved_at('path-conversion', str(error), node)
            self.opaque(flow)
            return _Value(complete=False, spec=target)
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('path-conversion', str(error), node)
            flow.stopped = True
            return _Value(complete=False, spec=target)
        cells = dict(zip(value.facts, converted, strict=True))
        return _Value(complete=all(cell.complete for cell in cells.values()), spec=target, facts=cells)

    def publish_private_path_array(self, target, value, node, flow):
        if not isinstance(value, _Value) or not value.facts or flow.opaque:
            return
        for cell in self.path_array_cells(target, node):
            captured = value.facts.get(cell.parts[len(target.parts):])
            if captured is not None and captured.path_records is not None:
                self.publish_path_records(cell, captured.path_records, node, flow)

    def path_array_assignment(self, target, value, node, flow, conditional):
        value = self.convert_path_array_value(target.spec, value, node, flow)
        if flow.stopped and not flow.opaque:
            return
        if not self.publish_path_array_value(target, value, node, flow, conditional):
            self.unresolved_at('path-topology', 'PATH ARRAY assignment source or destination effects require review', node)
            self.opaque(flow)

    def publish_path_array_value(self, target, value, node, flow, conditional, *, layout=None):
        if not value.facts or not self.can_publish_path(target, flow, conditional):
            return False
        if layout is None:
            layout = self.path_array_layout(target, node, flow, conditional)
        if layout is None:
            return False
        prepared = []
        for cell, count in layout:
            captured = value.facts.get(cell.parts[len(target.parts):])
            if count is None or captured is None or captured.path_records is None:
                return False
            records = captured.path_records
            complete_header = cell.spec[2] is not None and records[0].complete
            history = self.replaced_path_borrows(cell, flow, conditional, keep_header=True,
                                                 complete_header=complete_header)
            if history is None:
                return False
            prepared.append((cell, records, history))
        for cell, records, history in prepared:
            self.publish_path_records(cell, records, node, flow, keep_header=True, history=history)
        return True

    def convert_path_record(self, target, value, node):
        converted, unproven = convert_value_facts(target, value, tick=self.tick)
        if unproven:
            self.unresolved_at('conversion-value', 'Converted PATH field requires complete source data', node)
        return converted

    def convert_path_records(self, target, value, node):
        self.tick(len(value.path_records))
        if target == value.spec:
            return value
        node_type = target[1] or self.plan.get('default_path_node')
        records = tuple(
            self.convert_path_record(target[2] if index == 0 and target[2] is not None else node_type, item, node)
            for index, item in enumerate(value.path_records)
        )
        return _Value(complete=all(item.complete for item in records), spec=target, path_records=records)

    def convert_captured_paths(self, target, snapshots, layout, count, node, flow, *, operation, allow_missing=True):
        if not _path_conversion_needs_model(layout, count):
            return [self.convert_path_records(target, value, node) for value in snapshots]
        try:
            robot = self.selected_robot_for_discovery(operation, node, flow)
        except RobotFactsUnavailable as error:
            raise RobotFactsUnavailable(operation+' requires robot model results. '+str(error)) from error
        return evaluate_model_paths(robot, target, snapshots, layout, node.get('line'), self.tick,
                                    operation=operation, allow_missing=allow_missing)

    def convert_path_value(self, target, value, node, flow):
        """Convert a captured private PATH before evaluating later operands."""
        if value.path_records is not None:
            if target == value.spec:
                return value
            target_type = tuple_spec(target)
            layout = path_conversion_layout(target_type, tuple_spec(value.spec), model=True)
            count = len(value.path_records) - int(value.spec[2] is not None)
            node_type = target[1] or self.plan.get('default_path_node')
            if layout:
                if not self.path_snapshot_fits(target_type, count):
                    self.unresolved_at('limit', 'PATH conversion target exceeds the scalar snapshot limit', node)
                    flow.stopped = True
                    return _Value(complete=False, spec=target)
                if node_type or not count:
                    try:
                        converted, = self.convert_captured_paths(
                            target, [value], layout, count, node, flow, operation='PATH conversion',
                        )
                        return converted
                    except RobotFactsUnavailable as error:
                        self.unresolved_at('path-conversion', str(error), node)
                    except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
                        self.unresolved_at('path-conversion', str(error), node)
                        flow.stopped = True
                        return _Value(complete=False, spec=target)
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
        if flow.stopped and not flow.opaque:
            return
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

    def capture_path_copy(self, source, indexes, node, flow, conditional, *, require_storage=False, archived=None):
        """Read the selected records and header before publishing any copy."""
        selected = (0, *indexes) if source.spec[2] is not None else indexes
        self.tick(len(selected))
        if isinstance(source, _Value):
            has_header = source.spec[2] is not None
            records = [source.path_records[index if has_header else index - 1] for index in selected]
            return records if not require_storage or all(record.complete for record in records) else None
        values = []
        for index in selected:
            loc = (self.retired_path_child(source, index, node, flow, archived) if archived is not None
                   else self.index_child(source, index, node, flow))
            if loc is None:
                return None
            if (require_storage or archived is not None) and self.variable_path_storage(
                    loc, flow, conditional, archived=archived) is not True:
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
            self.write(self.child(target, *part, node), value, flow, node, track_path_storage=False)
        self.serial += 1
        detached, retired_slots = history if history is not None else (frozenset(), {})
        header_generation = previous.header_generation if previous is not None else 0
        if not keep_header:
            header_generation = self.serial
        flow.path_orders[target.key] = _PathOrder(tuple(nodes), header, detached, self.serial, retired_slots,
                                                 header_generation=header_generation)

    def named_indexes_valid(self, spec, numbers, *, ending):
        """Use the runtime's ARRAY boundaries before following physical storage."""
        dims, terminal = _array_dimensions(spec)
        if terminal[0] == 'JOINTPOS':
            dims = (*dims, terminal[1])
        if any(index < 1 or type(size) is int and index > size for index, size in zip(numbers, dims)):
            return False
        schema = tuple_spec(spec)
        count = len(numbers)
        if spec[0] == 'PATH':
            return count == 1
        if rt.collection_array_node_type(schema, count) is not None or rt.joint_axis_access(schema, count):
            return True
        if ending and rt.array_prefix_type(schema, count) is not None:
            return True
        try:
            rt.indexed_type(schema, count)
        except rt.KarelRuntimeError:
            return False
        return True

    def named_binding(self, key, flow):
        if key in flow.named_bindings:
            return flow.named_bindings[key]
        if self.saved_bindings is not None:
            spec = self.saved_bindings.spec(*key)
            if spec is not None:
                return _Location('variable', *key, spec=spec, root_spec=spec, saved_binding=True)
        return INITIAL_BINDING

    def retain_named_bindings(self, bindings):
        for loc in bindings:
            if loc.saved_binding:
                self.binding_storage[loc.owner, loc.root] = loc.root_spec

    def named_root_binding(self, owner, selected, path, root, flow, *, reject_missing=False):
        if flow.opaque or flow.task_order_unknown:
            return None, len(root), False
        # Exact rows win over navigation inside a root. Declared globals have
        # already been checked. Selection follows the current spelling while
        # the location keeps the original context row or allocation identity.
        removed = False
        for key in dict.fromkeys(((selected, path), (owner, path), (selected, root), (owner, root))):
            loc = self.named_binding(key, flow)
            if loc is UNKNOWN:
                return None, len(root), False
            if loc is None:
                removed = True
            elif loc is not INITIAL_BINDING:
                self.retain_named_bindings((loc,))
                return loc, len(key[1]), False
        return None, len(root), removed or reject_missing and self.saved_bindings is not None

    def saved_system_location(self, owner, selected, path, flow):
        if self.saved_bindings is None or flow.opaque or flow.task_order_unknown:
            return None, 0
        loc, consumed, _ = self.named_root_binding(owner, selected, path, path, flow)
        if loc is not None:
            return loc, consumed
        key = self.saved_bindings.system_path({owner, selected, 'SYSTEM', '*SYSTEM*', ''}, path, tick=self.tick)
        if key is None:
            return None, 0
        loc = self.named_binding(key, flow)
        if not isinstance(loc, _Location):
            return None, 0
        self.retain_named_bindings((loc,))
        return loc, len(key[1])

    def named_variable_location(self, owner, path, node, flow, conditional, *, capture_node=False, reject_missing=False):
        """Distinguish a rejected selection from an unproved root or storage layout."""
        if not all(type(value) is str and value.isascii() for value in (owner, path)):
            return None, False
        owner, path = owner.upper(), path.upper()
        selected = owner or self.program
        if path.startswith('$'):
            loc, consumed = self.saved_system_location(owner, selected, path, flow)
            if loc is None:
                return None, False
        else:
            root = re.match(r'[A-Z_][A-Z_0-9]*', path)
            if root is None:
                if reject_missing:
                    loc, _, rejected = self.named_root_binding(owner, selected, path, path, flow, reject_missing=True)
                    return loc, rejected
                return None, False
            root_name = root[0]
            loc = self.global_slot(root_name, node, program=selected)
            consumed = root.end()
            if loc is None:
                plan = self.binding_plan(selected)
                if plan is not None and (plan.get('status') != 'available' or root_name in plan.get('types', {})):
                    return None, False
                loc, consumed, rejected = self.named_root_binding(owner, selected, path, root_name, flow,
                                                                  reject_missing=reject_missing)
                if loc is None:
                    return None, rejected
        rest = path[consumed:]
        while rest and loc:
            if loc.named_data:
                present = self.named_container_present(loc, flow)
                if present is not True:
                    return None, present is False
            field = re.match(r'\.([A-Za-z_][A-Za-z_0-9]*)', rest)
            indexes = re.match(r'(?:\[[0-9]+(?:,[0-9]+)*\])+', rest)
            if field:
                record = loc.spec[2] if loc.spec[0] == 'PATH' else loc.spec
                if record is None:
                    return None, True
                member = field[1].upper()
                try:
                    fields = dict(rt.record_fields(tuple_spec(record)))
                except rt.KarelRuntimeError:
                    return None, True
                if member not in fields:
                    return None, True
                loc = self.field_child(loc, member, node, flow)
                rest = rest[field.end():]
            elif indexes:
                # Runtime treats adjacent brackets as one logical subscript.
                numbers = [int(item) for item in re.findall(r'[0-9]+', indexes[0])]
                ending = indexes.end() == len(rest)
                if not self.named_indexes_valid(loc.spec, numbers, ending=ending):
                    return None, True
                for position, index in enumerate(numbers, 1):
                    if loc is None:
                        return None, False
                    if loc.spec[0] == 'PATH':
                        count = self.known_path_count(loc, flow, conditional) if index > 0 else None
                        if ((index == 0 and loc.spec[2] is None) or index > 32767
                                or count is not None and index > count):
                            return None, True
                    selected = self.index_child(loc, index, node, flow)
                    if (selected is not None and capture_node and ending and loc.spec[0] == 'PATH'
                            and position == len(numbers)):
                        selected = self.borrow_path_record(loc, index, selected, flow)
                    loc = selected
                rest = rest[indexes.end():]
            else:
                return None, True
        return loc, False

    def whole_path_record(self, loc):
        dimensions, path_spec = _array_dimensions(loc.root_spec)
        return bool(path_spec and path_spec[0] == 'PATH' and len(loc.parts) == len(dimensions) + 1)

    def variable_path_storage(self, loc, flow, conditional, *, named_lookup=False, archived=None):
        """Check the modeled containers required for a named PATH selection."""
        dimensions, path_spec = _array_dimensions(loc.root_spec)
        _, terminal = _array_dimensions(loc.spec)
        if not path_spec or path_spec[0] != 'PATH' or terminal[0] == 'PATH':
            return True
        depth = len(dimensions)
        whole_record = len(loc.parts) == depth + 1
        if (len(loc.parts) <= depth or flow.opaque or flow.path_shape_unknown
                or self.lost_path_reference(loc, flow)):
            return None
        path = replace(loc, parts=loc.parts[:depth], spec=path_spec, path_slot=None)
        part = loc.parts[depth]
        origin = _path_record_identity(part)
        order = flow.path_orders.get(path.key)
        inserted = False
        if order is not None and not _path_header_part(part):
            self.tick(len(order.nodes))
            if origin not in order.nodes and origin not in order.detached:
                self.tick(len(order.retired_slots))
                if origin not in order.retired_slots.values():
                    return None
            inserted = origin in (archived.inserted if archived is not None else order.inserted)
        bank_node = bool(dimensions) and not _path_header_part(part)
        record_key = (*loc.key[:3], loc.parts[:depth + 1])
        if record_key in flow.record_storage:
            current = flow.record_storage[record_key]
            if current is False:
                if bank_node:
                    return False if named_lookup else None
                return MISSING_PATH_RECORD if whole_record else False
            if current is True:
                return True
        aggregate = loc.spec[0] not in SCALARS
        changed = any((*loc.key[:3], loc.parts[:end]) in flow.changed_path_aggregates
                      for end in range(depth + 1, len(loc.parts) + aggregate))
        if changed:
            return None
        if loc.key in flow.defined and not bank_node:
            return True
        if record_key in flow.record_storage:
            return None
        if inserted:
            return True
        # Whole PATH copies can introduce missing aggregate containers. Known
        # initialized leaves prove a replacement record's complete shape.
        layout = archived if archived is not None else order
        if origin < 0 or origin == 0 and layout is not None and layout.generation:
            if whole_record:
                leaves = self.leaves(loc)
                if leaves and all(leaf.key in flow.defined for leaf in leaves):
                    return True
            return None
        if loc.kind == 'created-variable' and origin == 0:
            return True
        if loc.kind == 'local' and origin == 0 and order is not None:
            return True
        if not self.stable_path_context(path, flow, conditional):
            return None
        present = self.saved_path_count(loc.owner, loc.root, loc.root_spec, path.parts, record_index=origin,
                                        record_selectors=loc.parts[depth + 1:], require_value=aggregate,
                                        validate_record=bank_node, whole_record=whole_record)
        if present is DEFAULT_EMPTY_PATH:
            return True if origin == 0 else None
        if present is not None:
            self.path_storage[loc.owner, loc.root] = loc.root_spec
        if present is False and bank_node:
            if not named_lookup:
                return None
            # A direct write through an alias can repair the saved record.
            # A source-flow write is not enough to prove the entire record.
            record_prefix = loc.parts[:depth + 1]
            self.tick(len(flow.maybe))
            if any(key[:3] == loc.key[:3] and key[3][:depth + 1] == record_prefix for key in flow.maybe):
                return None
        return present

    def variable_transfer_status(self, value):
        if value.uninitialized:
            return 12311
        if value.complete:
            return 0
        members = value.path_records if value.path_records is not None else (value.facts or {}).values()
        return 12311 if any(self.variable_transfer_status(member) == 12311 for member in members) else UNKNOWN

    def variable_path_layout(self, target, source):
        target, source = tuple_spec(target), tuple_spec(source)
        if target == source:
            return 'exact', 'exact'
        if target[0] == source[0] == 'PATH':
            return path_conversion_layout(target, source, model=True)
        return rt.path_array_conversion_layout(target, source)

    def variable_path_source_known(self, source, node, flow, conditional):
        """Validate the source topology without adding unused payload inputs."""
        if source.spec[0] == 'PATH':
            count = self.known_path_count(source, flow, conditional)
            return count is not None and self.path_snapshot_fits(tuple_spec(source.spec), count)
        cells = self.path_array_layout(source, node, flow, conditional)
        return cells is not None and all(count is not None for _, count in cells)

    def write_variable_entry(self, entry, key, node, flow):
        """Publish the offline cache entry for a successful named operation."""
        number = None
        if not (flow.opaque or flow.task_order_unknown or self.callback_depth or self.repeat_depth):
            if key in flow.variable_entries:
                number = flow.variable_entries[key]
            elif flow.next_variable_entry is not None:
                number = flow.next_variable_entry
                self.tick()
                flow.variable_entries[key] = number
                if len(flow.variable_entries) > MAX_FACTS:
                    raise _Limit('Analysis storage limit reached')
                flow.next_variable_entry = number + 1
        if number is None:
            # A branch-dependent key could have just allocated another number.
            flow.next_variable_entry = None
        self.write(entry, _Value(number if number is not None else UNKNOWN, spec=['INTEGER']), flow, node)

    def publish_variable_result(self, entry, status, result, key, node, flow):
        self.write_variable_entry(entry, key, node, flow)
        self.write(status, _Value(result, spec=['INTEGER']), flow, node)

    def variable_path_copy(self, target, value, entry, status, node, flow, conditional, *, layout, entry_key):
        """Follow a whole PATH or bank transfer using its captured data."""
        if not self.can_publish_path(target, flow, conditional):
            return False
        target_spec = tuple_spec(target.spec)
        conversion = layout if target_spec != tuple_spec(value.spec) else None
        if conversion is not None and 'kinematic' in conversion:
            self.context('robot', None)
            if self.saved_bindings is not None and self.saved_bindings.robot is None:
                self.write(status, _Value(3, spec=['INTEGER']), flow, node)
                return True

        if target.spec[0] == 'PATH':
            count = self.known_path_count(target, flow, conditional)
            if count is None or not self.path_snapshot_fits(target_spec, count):
                return False
            value = self.convert_path_value(target.spec, value, node, flow)
            if flow.stopped and not flow.opaque:
                return True
            if value.path_records is None:
                return False
            complete_header = target.spec[2] is not None and value.path_records[0].complete
            history = self.replaced_path_borrows(target, flow, conditional, keep_header=True,
                                                 complete_header=complete_header)
            if history is None:
                return False
            self.publish_path_records(target, value.path_records, node, flow, keep_header=True, history=history)
        else:
            layout = self.path_array_layout(target, node, flow, conditional)
            if layout is None or any(count is None for _, count in layout):
                return False
            if conversion is not None:
                value = self.convert_path_array_cells(target.spec, value, conversion, node, flow)
                if flow.stopped and not flow.opaque:
                    return True
            if not self.publish_path_array_value(target, value, node, flow, conditional, layout=layout):
                return False

        self.publish_variable_result(entry, status, self.variable_transfer_status(value), entry_key, node, flow)
        return True

    def ordinary_variable_output(self, loc, node, *, alias=False):
        if loc.kind not in ('variable', 'local', 'created-variable') or not loc.root_spec:
            return False
        current = replace(loc, parts=(), spec=loc.root_spec)
        for kind, key in loc.parts:
            if (current.spec[0] == 'CONFIG'
                    or current.spec[0] == 'POSITION' and key in rt.POSITION_READ_ONLY_FIELDS
                    or alias and current.spec[0] in rt.ASSOCIATION_TYPES):
                return False
            current = self.child(current, kind, key, node)
            if current is None:
                return False
        return True

    def variable_array_locations(self, loc, count, node):
        for address in array_prefix_addresses(loc.spec, count):
            self.tick()
            current = loc
            for kind, index in address:
                current = self.child(current, kind, index, node)
            yield current

    def variable_array_source(self, loc, count, node, flow, conditional):
        for cell in self.variable_array_locations(loc, count, node):
            yield self.read(cell, node, flow, conditional, partial=True, raw_scalar=True)

    def read_variable_data(self, loc, node, flow, conditional, storage=None):
        value = self.read(loc, node, flow, conditional, partial=True, raw_scalar=True)
        if storage is MISSING_PATH_RECORD or flow.record_storage.get(loc.key) is False:
            return _Value(complete=False, spec=loc.spec, uninitialized=True, whole_record_missing=True)
        return value

    def capture_variable_operand(self, expression, flow, conditional):
        while expression['kind'] == 'group':
            expression = expression['args'][0]
        kind = expression['kind']
        robot_value = kind == 'field' and self.robot_table_path(expression)[0]['kind'] == 'system_pose'
        if kind in ('name', 'field', 'index') and not robot_value and not self.selects_routine_result(expression):
            location = self.locate(expression, flow, conditional)
            if location is not None:
                whole_record = self.whole_path_record(location)
                storage = self.variable_path_storage(location, flow, conditional)
                if storage is False:
                    self.unresolved_at('path-topology', 'SET_VAR operand has missing PATH storage: '+location.path, expression)
                    flow.stopped = True
                    return _Value(complete=False), None, False
                if storage is None and (not whole_record or flow.record_storage.get(location.key) is False):
                    self.unresolved_at('path-topology', 'SET_VAR operand requires proven PATH storage: '+location.path, expression)
                    value = self.read(location, expression, flow, conditional, partial=True, raw_scalar=True)
                    return replace(value, spec=None), None, False
                _, element = _array_dimensions(location.spec)
                if (location.spec[0] == 'ARRAY' and location.kind in ('variable', 'local', 'created-variable')
                        and element[0] in (*SCALARS, *rt.RECORD_TYPES, 'JOINTPOS')):
                    return _Value(spec=location.spec), (location, flow.copy()), False
                value = self.read_variable_data(location, expression, flow, conditional, storage)
                shaped = whole_record and storage is True or flow.record_storage.get(location.key) is True
                return value, None, shaped
            if kind != 'name':
                self.unresolved_at('selection', 'Computed or dynamic data read is unresolved', expression)
                return _Value(complete=False), None, False
        value = self.expr(expression, flow, conditional, partial=True, raw_scalar=True)
        if value.spec is None and kind in ('literal', 'real_literal'):
            schemas = {bool: ['BOOLEAN'], int: ['INTEGER'], float: ['REAL'], str: ['STRING', 254]}
            value = replace(value, spec=schemas.get(type(value.constant)))
        return value, None, False

    def clear_record_destination(self, loc, flow, conditional):
        """Give a cleared PATH slot a new record identity if old fields are still borrowed."""
        frames = (*self.frames, *(frame for handlers in flow.handlers.values()
                                 for handler in handlers for frame in handler.frames))
        references = (*self.pending_references, *(ref for frame in frames for ref in frame['references']))
        self.tick(len(references))
        if any(ref is None for ref in references):
            return None
        if not any(len(ref.parts) > len(loc.parts) and self.path_contains_reference(loc, ref) for ref in references):
            return loc
        if not self.whole_path_record(loc) or self.variable_path_storage(loc, flow, conditional) is not True:
            return None

        dimensions, path_spec = _array_dimensions(loc.root_spec)
        depth = len(dimensions)
        path = replace(loc, parts=loc.parts[:depth], spec=path_spec, path_slot=None)
        order = flow.path_orders.get(path.key)
        if order is None:
            count = self.known_path_count(path, flow, conditional)
            if count is None:
                return None
            self.tick(count)
            order = _PathOrder(tuple(range(1, count + 1)))
        old = _path_record_identity(loc.parts[depth])
        header = _path_header_part(loc.parts[depth])
        slot = loc.path_slot
        self.serial += 1
        replacement = -self.serial
        if slot is not None and slot.key in order.retired_slots:
            if order.retired_slots[slot.key] != old:
                return None
            self.tick(len(order.retired_slots))
            order = replace(order, retired_slots=order.retired_slots | {slot.key: replacement})
        elif header and old == order.header_origin:
            order = replace(order, header=self.serial)
        elif not header and old in order.nodes:
            self.tick(len(order.nodes))
            order = replace(order, nodes=tuple(replacement if item == old else item for item in order.nodes))
        else:
            return None
        self.tick(len(order.detached))
        flow.path_orders[path.key] = replace(order, detached=order.detached | {old})
        part = ('created-header' if header else 'created-node', self.serial)
        return replace(loc, parts=(*path.parts, part))

    def variable_data_copy(self, target, value, entry, status, policy, node, flow, conditional, *, entry_key,
                           prefix=None, source_array_storage=False, shaped_source_record=False):
        if policy == 'rejected':
            self.write(status, _Value(3, spec=['INTEGER']), flow, node)
            return
        modeled = policy == 'model'
        if modeled:
            self.context('robot', None)
            if self.saved_bindings is not None and self.saved_bindings.robot is None:
                self.write(status, _Value(3, spec=['INTEGER']), flow, node)
                return
        if prefix is None:
            pairs = ((target, value),)
        else:
            count, values = prefix
            pairs = zip(self.variable_array_locations(target, count, node), values, strict=True)
        if modeled:
            converted_batch = self.model_variable_data_copy(tuple(pairs), prefix is not None, entry, status, node, flow)
            if converted_batch is None:
                return
            prepared, result = converted_batch
        else:
            prepared = self.convert_variable_pairs(pairs, node, flow)
            if prepared is None:
                return
        if target.spec[0] == 'ARRAY' and not source_array_storage:
            _, terminal = _array_dimensions(target.root_spec)
            if terminal and terminal[0] == 'PATH' and any(not converted.complete for _, converted in prepared):
                self.unresolved_at('path-topology', 'Variable ARRAY source may replace PATH storage with a missing value', node)
                flow.next_variable_entry = None
                self.write(target, _Value(complete=False), flow, node, definite=False)
                self.write(entry, _Value(), flow, node, definite=False)
                self.write(status, _Value(), flow, node)
                return
        codes = []
        for destination, converted in prepared:
            if converted.whole_record_missing:
                destination = self.clear_record_destination(destination, flow, conditional)
                if destination is None:
                    self.unresolved_at('path-topology', 'Clearing a record may detach captured field references', node)
                    self.opaque(flow)
                    return
            self.write(destination, converted, flow, node, shaped_record=shaped_source_record)
            if not modeled:
                codes.append(self.variable_transfer_status(converted))
        if not modeled:
            result = 12311 if 12311 in codes else 0 if all(code == 0 for code in codes) else UNKNOWN
        self.publish_variable_result(entry, status, result, entry_key, node, flow)

    def convert_variable_pairs(self, pairs, node, flow):
        prepared = []
        try:
            for destination, source in pairs:
                if source.whole_record_missing:
                    # An admitted record conversion preserves the whole marker.
                    converted = _Value(complete=False, spec=destination.spec, uninitialized=True,
                                       whole_record_missing=True)
                else:
                    converted, unproven = convert_value_facts(destination.spec, source, tick=self.tick)
                    if unproven:
                        self.unresolved_at('conversion-value', 'Variable conversion requires complete source data', node)
                prepared.append((destination, converted))
        except rt.KarelRuntimeError as error:
            self.unresolved_at('variable-conversion', str(error), node)
            flow.stopped = True
            return None
        return prepared

    def model_variable_data_copy(self, pairs, prefix, entry, status, node, flow):
        operation = node['value']+' conversion'
        try:
            robot = self.selected_robot_for_discovery(operation, node, flow)
            values, result = evaluate_model_variables(
                robot, [(destination.spec, source) for destination, source in pairs], node.get('line'), self.tick,
                prefix=prefix, operation=operation,
            )
        except RobotFactsUnavailable as error:
            self.unresolved_at('variable-model', str(error), node)
            flow.next_variable_entry = None
            for destination, _ in pairs:
                self.write(destination, _Value(complete=False, spec=destination.spec), flow, node, definite=False)
            self.write(entry, _Value(), flow, node, definite=False)
            self.write(status, _Value(), flow, node)
            return None
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('variable-model', str(error), node)
            flow.stopped = True
            return None
        if result == 3:
            self.write(status, _Value(result, spec=['INTEGER']), flow, node)
            return None
        return [(pair[0], value) for pair, value in zip(pairs, values, strict=True)], result

    def variable_target_overlap(self, target, outputs, flow, conditional):
        """Compare captured scalar outputs with the receiver's live storage."""
        if target is None or any(output is None for output in outputs) or flow.opaque:
            return None
        dimensions, terminal = _array_dimensions(target.spec)
        depth = len(target.parts) + len(dimensions)
        unknown = False
        for output in outputs:
            if not self.path_contains_reference(target, output):
                continue
            if terminal[0] != 'PATH' or target.key == output.key:
                return True
            cell = replace(target, parts=output.parts[:depth], spec=terminal)
            overlap = self.path_service_overlap(cell, output, flow, conditional)
            if overlap is True:
                return True
            unknown |= overlap is None
        return None if unknown else False

    def can_lookup_robot_variable(self, owner, path, flow):
        if (not all(type(item) is str and item.isascii() for item in (owner, path))
                or owner.upper() not in ('', 'SYSTEM', '*SYSTEM*')
                or not path.upper().startswith(('$MNUFRAME', '$MNUTOOL', '$GROUP['))
                or flow.opaque or flow.task_order_unknown):
            return False
        owners = {owner.upper() or self.program, 'SYSTEM', '*SYSTEM*', ''}
        path = path.upper()
        # An explicit row or longer binding prefix outranks the robot endpoint.
        # The caller already tried resolution, so a remaining potential shadow
        # means the binding or its descendant storage could not be proven.
        if self.saved_bindings is not None and self.saved_bindings.system_path(owners, path, tick=self.tick) is not None:
            return False
        self.tick(len(flow.named_bindings))
        return not any(program in owners and root_member(path, root) and binding is not None
                       for (program, root), binding in flow.named_bindings.items())

    def robot_variable_transfer(self, owner, path, target, source, entry, status, node, flow):
        getting = node['value'] == 'GET_VAR'
        address = _parse_system_variable_path(path.upper())
        robot = None
        line = node.get('line')

        def model_robot():
            return self.selected_robot_for_discovery(node['value'], node, flow)

        try:
            if address is None:
                result, value = 1, None
            else:
                group = address[1]
                try:
                    robot = self.query_robot_group(node['value'], group, node, flow)
                except rt.KarelRuntimeError:
                    result, value = 1, None
                else:
                    result, value = transfer_robot_variable(
                        flow.robot_tables, robot, address, getting=getting,
                        target_spec=target.spec if getting else None, source=source,
                        model_robot=model_robot, line=line, tick=self.tick,
                    )
        except RobotFactsUnavailable as error:
            self.unresolved_at('robot-tables', str(error), node)
            if not getting:
                flow.robot_tables.invalidate_named(robot, address)
            flow.next_variable_entry = None
            self.write(entry, _Value(), flow, node, definite=False)
            if getting:
                self.write(target, _Value(complete=False, spec=target.spec), flow, node, definite=False)
            self.write(status, _Value(), flow, node)
            return
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('robot-tables', str(error), node)
            flow.stopped = True
            return

        if result in (0, 12311):
            if getting:
                self.write(target, value, flow, node)
            self.publish_variable_result(entry, status, result, (owner.upper() or self.program, path.upper()), node, flow)
        else:
            self.write(status, _Value(result, spec=['INTEGER']), flow, node)

    def variable_call(self, node, flow, conditional):
        name = node['value']
        args = node['args']
        with self.capture_operands() as pending:
            entry = self.locate(args[0], flow, conditional)
            pending.append(entry)
            if flow.stopped and not flow.opaque:
                return _Value(complete=False)
            owner = self.expr(args[1], flow, conditional, argument_path_edits=entry is not None).constant
            if flow.stopped and not flow.opaque:
                return _Value(complete=False)
            path = self.expr(args[2], flow, conditional, argument_path_edits=entry is not None).constant
            if flow.stopped and not flow.opaque:
                return _Value(complete=False)
            getting = name == 'GET_VAR'
            target = self.locate(args[3], flow, conditional, capture_node=True) if getting else None
            receiver = self.resolve_path_slot(target, args[3], flow) if target is not None else None
            target_storage = self.variable_path_storage(receiver, flow, conditional) if receiver is not None else None
            if target_storage is False:
                self.unresolved_at('path-topology', 'GET_VAR receiver has missing PATH storage: '+receiver.path, node)
                flow.stopped = True
                return _Value(complete=False)
            if getting:
                pending.append(target)
            value, captured_array, shaped_source_record = (
                (None, None, False) if getting else self.capture_variable_operand(args[3], flow, conditional)
            )
            if flow.stopped and not flow.opaque:
                return _Value(complete=False)
            status = self.locate(args[4], flow, conditional,
                                 selector_path_edits=receiver is not None if getting else value.spec is not None)
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        outputs = entry, status
        if entry is not None and status is not None and entry.key == status.key and not flow.opaque:
            return self.reject_service_overlap(node, flow)
        if target is not None and target.path_slot is not None:
            target = self.resolve_path_slot(target, node, flow)
            if target is None:
                target_storage = None
        # GET_VAR's receiver participates in the service output check,
        # before lookup. SET_VAR checks the named destination after lookup.
        overlap = self.variable_target_overlap(target, outputs, flow, conditional) if getting else None
        if overlap is True:
            return self.reject_service_overlap(node, flow)
        named, rejected = self.named_variable_location(owner, path, node, flow, conditional)
        named_storage = (self.variable_path_storage(named, flow, conditional, named_lookup=True)
                         if named is not None else None)
        if (rejected or named_storage is False) and status is not None and not flow.opaque:
            self.write(status, _Value(1, spec=['INTEGER']), flow, node)
            return _Value()
        if (named is None and not rejected and self.can_lookup_robot_variable(owner, path, flow)
                and all(loc is not None and self.ordinary_variable_output(loc, node) for loc in outputs)
                and (not getting or overlap is False and target is not None
                     and target_storage is True and self.ordinary_variable_output(target, node))):
            self.robot_variable_transfer(owner, path, target, value, entry, status, node, flow)
            return _Value()
        destination = target if getting else named
        if not getting:
            overlap = self.variable_target_overlap(destination, outputs, flow, conditional)
            if overlap is True:
                return self.reject_service_overlap(node, flow, 'SET_VAR target overlaps entry/status')
        # The runtime uses the requested spelling, even for linked aliases
        # and equivalent PATH or ARRAY subscript spellings.
        entry_key = (owner.upper() or self.program, path.upper()) if named is not None else None
        source_spec = (named.spec if named is not None else None) if getting else value.spec
        if source_spec and destination is not None:
            target_spec = destination.spec
            source_path = source_spec[0] == 'PATH' or _path_array_cell_type(source_spec)
            target_path = target_spec[0] == 'PATH' or _path_array_cell_type(target_spec)
            ordinary = target_spec if source_path else source_spec
            if (source_path or target_path) and (
                    source_path and target_path or variable_transfer_policy(ordinary, ordinary) is not None):
                layout = self.variable_path_layout(target_spec, source_spec) if source_path and target_path else None
                if getting and layout is None:
                    captured = (self.variable_path_source_known(named, node, flow, conditional) if source_path
                                else named_storage in (True, MISSING_PATH_RECORD))
                else:
                    if getting:
                        value = self.read(named, node, flow, conditional, partial=True)
                    captured = not source_path or value.path_records is not None or (
                        value.facts and all(cell.path_records is not None for cell in value.facts.values())
                    )
                if overlap is False and captured:
                    if layout is None:
                        self.write(status, _Value(3, spec=['INTEGER']), flow, node)
                        return _Value()
                    if self.variable_path_copy(destination, value, entry, status, node, flow, conditional,
                                               layout=layout, entry_key=entry_key):
                        return _Value()
                self.unresolved_at('path-topology', name+' PATH source or receiver effects require review', node)
                self.opaque(flow)
                return _Value()

        destination_storage = named_storage if not getting else target_storage
        if getting and target_storage in (True, MISSING_PATH_RECORD):
            destination_storage = self.variable_path_storage(target, flow, conditional)
        if (named is not None and destination is not None and source_spec and not flow.opaque
                and overlap is False and named_storage in (True, MISSING_PATH_RECORD)
                and destination_storage in (True, MISSING_PATH_RECORD)
                and self.ordinary_variable_output(destination, node)):
            policy = variable_transfer_policy(destination.spec, source_spec)
            if policy is not None:
                capture, captured_flow = (named, flow) if getting else captured_array or (None, None)
                count = (variable_array_prefix_size(destination.spec, source_spec, include_equal=policy == 'model')
                         if policy in ('data', 'model') else None)
                prefix = None
                if count is not None:
                    values = (self.variable_array_source(capture, count, args[3] if not getting else node,
                                                         captured_flow, conditional) if capture is not None
                              else array_prefix_values(value, count, tick=self.tick))
                    prefix = count, values
                elif capture is not None and policy != 'rejected':
                    value = self.read_variable_data(capture, args[3] if not getting else node, captured_flow,
                                                    conditional, named_storage if getting else None)
                source_array_storage = False
                if capture is not None:
                    _, source_root = _array_dimensions(capture.root_spec)
                    source_array_storage = source_root and source_root[0] == 'PATH'
                if getting:
                    shaped_source_record = (self.whole_path_record(named) and named_storage is True
                                            or flow.record_storage.get(named.key) is True)
                self.variable_data_copy(destination, value, entry, status, policy, node, flow, conditional,
                                        entry_key=entry_key, prefix=prefix,
                                        source_array_storage=source_array_storage,
                                        shaped_source_record=shaped_source_record)
                return _Value()

        # An unresolved named transfer may allocate a new entry on success.
        flow.next_variable_entry = None
        if captured_array is not None:
            capture, captured_flow = captured_array
            self.read(capture, args[3], captured_flow, conditional, partial=True, raw_scalar=True)
        complete = False
        if named is not None:
            if named_storage is None:
                self.unresolved_at('path-topology', name+' requires proven PATH storage for '+named.path, node)
            if getting:
                leaves = self.leaves(named)
                complete = leaves is not None and all(leaf.key in flow.defined for leaf in leaves)
                self.read(named, node, flow, conditional)
            else:
                self.write(named, _Value(complete=False), flow, node, definite=False)
        else:
            self.unresolved_at('variable-path', 'GET_VAR/SET_VAR requires a known static data path', node)
            if not getting:
                flow.path_shape_unknown = True
                if type(path) is not str or path.startswith('$'):
                    flow.robot_tables.invalidate_all()
                self.lose_task_order(flow)
        self.write(entry, _Value(), flow, node, definite=False)
        if getting:
            if target is not None and destination_storage is not True:
                self.unresolved_at('path-topology', 'GET_VAR requires proven PATH receiver storage for '+target.path, node)
            self.write(target, _Value(complete=complete), flow, node, definite=False)
        self.write(status, _Value(), flow, node)
        return _Value()

    def binding_plan(self, owner):
        return self.plan if owner == self.program else (self.linked_plans or {}).get(owner)

    def active_named_bindings(self, owner, flow, *, roots=()):
        paths = set(self.saved_bindings.paths(owner))
        paths.update(path for program, path in flow.named_bindings if program == owner)
        self.tick(len(paths) + len(flow.named_bindings))
        bindings = {}
        for path in paths:
            if roots and not any(root_member(path, root) for root in roots):
                continue
            loc = self.named_binding((owner, path), flow)
            if loc is UNKNOWN:
                return None
            if loc is not None and loc is not INITIAL_BINDING:
                bindings[path] = loc
        return bindings

    def creation_outcome(self, values, flow):
        owner, root, type_owner, text, group, inner, middle, outer, pool = values
        if (flow.opaque or flow.task_order_unknown or self.callback_depth or self.repeat_depth
                or any(type(name) is not str or not name.isascii() for name in (owner, root, type_owner))):
            return None
        owner = normalized_name(owner, self.program)
        root = normalized_name(root)
        type_owner = normalized_name(type_owner, self.program)
        if None in (owner, root, type_owner):
            return 2
        key = owner, root
        owner_plan = self.binding_plan(owner)
        if owner_plan is not None:
            if owner_plan.get('status') != 'available':
                return None
            if root in owner_plan.get('types', {}):
                return 3
        if self.saved_bindings is None:
            return None
        conflicts = self.active_named_bindings(owner, flow, roots=(root,))
        if conflicts is None:
            return None
        if conflicts:
            self.retain_named_bindings(conflicts.values())
            return 3
        if pool is UNKNOWN:
            return None
        if type(pool) is not int or pool not in (-1, 0):
            return 2
        if any(value is UNKNOWN for value in (text, group, inner, middle, outer)):
            return None
        type_plan = self.binding_plan(type_owner)
        aliases = type_plan.get('variable_types', {}) if type_plan and type_plan.get('status') == 'available' else None
        with rt._numeric_scope('pythonic'):
            try:
                schema = creation_type(text, group, (inner, middle, outer), aliases)
            except rt.KarelRuntimeError:
                return None
            if schema is UNKNOWN_CREATION_TYPE:
                return None
            if schema is None:
                return 5
            cost = creation_cost(schema)
        units = flow.allocated_variable_units
        if units is None or flow.handlers:
            return None
        reserved, bindings = self.saved_bindings.reservation()
        self.binding_storage.update(bindings)
        if reserved + units + cost > MAX_LEAVES:
            return 6
        flow.allocated_variable_units = units + cost
        number = flow.creation_counts.get(key, 0) + 1
        flow.creation_counts[key] = number
        spec = list_spec(schema)
        flow.named_bindings[key] = _Location('created-variable', *key, spec=spec, root_spec=spec,
                                              creation_number=number)
        if len(flow.named_bindings) > MAX_FACTS:
            raise _Limit('Analysis storage limit reached')
        return 0

    def create_variable(self, node, flow, conditional):
        args = node['args']
        with self.capture_operands() as pending:
            values = []
            for arg in args[:8]:
                values.append(self.expr(arg, flow, conditional).constant)
                if flow.stopped and not flow.opaque:
                    return _Value(complete=False)
            status = self.locate(args[8], flow, conditional, capture_node=True, selector_path_edits=True)
            if flow.stopped and not flow.opaque:
                return _Value(complete=False)
            pending.append(status)
            pool = self.expr(args[9], flow, conditional, argument_path_edits=status is not None).constant if len(args) == 10 else 0
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        status = self.resolve_path_slot(status, node, flow) if status is not None else None
        result = self.creation_outcome([*values, pool], flow) if status is not None else None
        if result is None:
            self.unresolved_at('variable-creation', 'CREATE_VAR name, schema, capacity or execution order requires review', node)
            self.opaque(flow)
        else:
            self.write(status, _Value(result, spec=['INTEGER']), flow, node)
        return _Value()

    def rename_outcome(self, operation, values, flow):
        if (flow.opaque or flow.task_order_unknown or self.callback_depth or self.repeat_depth
                or any(type(name) is not str or not name.isascii() for name in values)):
            return None
        names = rename_names(values, self.program)
        if None in names:
            return 2
        if self.saved_bindings is None:
            return None
        namespaces = {}
        if operation == 'RENAME_VAR':
            owner, old, new = names
            plan = self.binding_plan(owner)
            if plan is not None and plan.get('status') != 'available':
                return None
            namespaces[owner] = self.active_named_bindings(owner, flow, roots=(old, new))
        else:
            for owner in dict.fromkeys(names):
                namespaces[owner] = self.active_named_bindings(owner, flow)
        if any(bindings is None for bindings in namespaces.values()):
            return None
        status, changes = rename_plan(
            operation, names, namespaces.__getitem__,
            lambda owner: (self.binding_plan(owner) or {}).get('types', {}),
            lambda owner: self.binding_plan(owner) is not None,
        )
        for bindings in namespaces.values():
            self.retain_named_bindings(bindings.values())
        if not changes:
            return status
        if flow.handlers:
            return None
        for old, new in changes.items():
            flow.named_bindings[old] = None
            flow.named_bindings[new] = namespaces[old[0]][old[1]]
        if len(flow.named_bindings) > MAX_FACTS:
            raise _Limit('Analysis storage limit reached')
        self.rename_variable_entries(operation, names, flow)
        return status

    def rename_variable_entries(self, operation, names, flow):
        self.tick(len(flow.variable_entries))
        entries = {}
        for key, number in flow.variable_entries.items():
            moved = renamed_key(operation, names, key)
            if moved in entries and entries[moved] != number:
                number = None
                flow.next_variable_entry = None
            entries[moved] = number
        flow.variable_entries = entries

    def rename_variable(self, node, flow, conditional):
        args = node['args']
        values = []
        for arg in args[:-1]:
            values.append(self.expr(arg, flow, conditional).constant)
            if flow.stopped and not flow.opaque:
                return _Value(complete=False)
        status = self.locate(args[-1], flow, conditional, capture_node=True, selector_path_edits=True)
        if flow.stopped and not flow.opaque:
            return _Value(complete=False)
        status = self.resolve_path_slot(status, node, flow) if status is not None else None
        result = self.rename_outcome(node['value'], values, flow) if status is not None else None
        if result is None:
            self.unresolved_at('variable-rename', node['value']+' names, bindings or execution order require review', node)
            self.opaque(flow)
        else:
            self.write(status, _Value(result, spec=['INTEGER']), flow, node)
        return _Value()

    def catalog_rows(self, options, flow):
        """Collect visible metadata while preserving saved input provenance."""
        if self.saved_bindings is None:
            return None
        program, pattern, kind, _, _ = options
        programs = self.linked_plans if self.linked_plans is not None else {self.program: self.plan}
        initial = self.saved_bindings.namespace_paths()
        keys = set(flow.named_bindings)
        keys.update((owner, path) for owner, paths in initial.items() for path in paths)
        scan_limit = len(keys) + sum(1 + len(plan.get('types', {})) for plan in programs.values())
        if scan_limit > CATALOG_SCAN_LIMIT:
            return None
        self.tick(scan_limit)
        declared = {}
        for owner, plan in programs.items():
            if not fnmatchcase(owner, program):
                continue
            if plan.get('status') != 'available':
                return None
            declared.update({(owner, name): tuple_spec(spec) for name, spec in plan['types'].items()})
        rows = declared.copy()
        retained = []
        for owner, path in keys:
            key = catalog_key(self.program, owner, path)
            if key is None or key in declared or not fnmatchcase(key[0], program):
                continue
            loc = self.named_binding((owner, path), flow)
            if loc is UNKNOWN:
                return None
            if loc is INITIAL_BINDING or loc is None:
                continue
            spec = tuple_spec(loc.spec)
            previous = rows.setdefault(key, spec)
            if (kind and fnmatchcase(key[1], pattern)
                    and catalog_type_matches(previous, kind) != catalog_type_matches(spec, kind)):
                # Both a blank owner and the current owner can canonicalize to
                # the same root. Name changes may obscure their storage order.
                return None
            retained.append(loc)
        self.retain_named_bindings(retained)
        return sorted(rows.items()), program in programs

    def catalog_array_value(self, target, values):
        self.tick(len(values))
        element = target.spec[2]
        facts = {(('index', index),): _Value(value, spec=element)
                 for index, value in enumerate(values, 1)}
        return _Value(spec=target.spec, facts=facts)

    def catalog_buffer(self, loc):
        dims, leaf = _array_dimensions(loc.spec)
        if (len(dims) == 1 and type(dims[0]) is int and 1 <= dims[0] <= MAX_FACTS
                and leaf[0] == 'STRING' and type(leaf[1]) is int):
            return dims[0], leaf[1]
        return None

    def catalog_page_outputs(self, names, capacity, text):
        values = text + [''] * (capacity - len(text))
        return self.catalog_array_value(names, values), _Value(len(text), spec=['INTEGER']), _Value(0, spec=['INTEGER'])

    def variable_list_values(self, known, output, flow):
        owner, pattern, kind, skip, form = known
        if (not all(type(value) is str and value.isascii() for value in (owner, pattern))
                or not all(type(value) is int for value in (kind, skip, form))):
            return None
        options = effective_list_options(self.program, owner, pattern, kind, skip, form)
        if options is None:
            return (None, None, _Value(2, spec=['INTEGER']))
        names = output[0]
        buffer = self.catalog_buffer(names)
        if buffer is None:
            return None
        catalog = self.catalog_rows(options, flow)
        if catalog is None:
            return None
        rows, known_program = catalog
        capacity, width = buffer
        status, text = variable_list_page(rows, options, capacity, width, known_program=known_program)
        if status:
            return (None, None, _Value(status, spec=['INTEGER']))
        return self.catalog_page_outputs(names, capacity, text)

    def inspected_missing(self, loc, node, flow, conditional):
        """Inspect availability without turning the payload into an input."""
        self.tick()
        if self.lost_path_reference(loc, flow):
            return UNKNOWN
        if flow.record_storage.get(loc.key) is False:
            return True
        if loc.spec[0] == 'PATH':
            count = self.known_path_count(loc, flow, conditional)
            if count is None:
                return UNKNOWN
            records = range(0 if loc.spec[2] is not None else 1, count + 1)
            flags = (self.inspected_missing_child(self.index_child(loc, index, node, flow),
                                                  node, flow, conditional) for index in records)
        elif _path_array_cell_type(loc.spec):
            count = _array_dimensions(loc.spec)[0][0]
            if type(count) is not int or not 1 <= count <= MAX_FACTS:
                return UNKNOWN
            flags = (self.inspected_missing(self.child(loc, 'index', index, node), node, flow, conditional)
                     for index in range(1, count + 1))
        else:
            leaves = self.leaves(loc)
            if leaves is None:
                return UNKNOWN
            flags = (self.inspected_leaf_missing(leaf, flow) for leaf in leaves)
        uncertain = False
        for flag in flags:
            if flag is True:
                return True
            uncertain |= flag is UNKNOWN
        return UNKNOWN if uncertain else False

    def inspected_missing_child(self, loc, node, flow, conditional):
        if loc is None:
            return UNKNOWN
        storage = self.variable_path_storage(loc, flow, conditional)
        if storage is MISSING_PATH_RECORD:
            return True
        if storage is not True:
            return UNKNOWN
        return self.inspected_missing(loc, node, flow, conditional)

    def inspected_leaf_missing(self, loc, flow):
        if loc.key in flow.defined:
            return False
        if self.leaf_uninitialized(loc, flow):
            return True
        if loc.key not in flow.maybe:
            if loc.spec == ['BYTE']:
                if loc.kind in ('local', 'created-variable'):
                    return False
            elif loc.saved_binding:
                return not self.saved_bindings.leaf_initialized(loc.owner, loc.root, loc.parts)
        return UNKNOWN

    def variable_info_values(self, known, output, node, flow, conditional):
        owner, path = known
        if not all(type(value) is str and value.isascii() for value in (owner, path)):
            return None
        dims, dim_leaf = _array_dimensions(output[3].spec)
        if dims != [3] or dim_leaf != ['INTEGER']:
            return None
        loc, rejected = self.named_variable_location(owner, path, node, flow, conditional, reject_missing=True)
        if rejected:
            return (None,)*5 + (_Value(1, spec=['INTEGER']),)
        if loc is None:
            if self.can_lookup_robot_variable(owner, path, flow):
                return self.robot_variable_info(path, output, node, flow)
            return None
        storage = self.variable_path_storage(loc, flow, conditional, named_lookup=True)
        if storage is False:
            return (None,)*5 + (_Value(1, spec=['INTEGER']),)
        if storage is None:
            return None
        try:
            name, code, shape, length = describe(tuple_spec(loc.spec))
        except NotImplementedError:
            return (None,)*5 + (_Value(4, spec=['INTEGER']),)
        if any(type(size) is not int for size in shape) or type(length) is not int:
            return None
        missing = True if storage is MISSING_PATH_RECORD else self.inspected_missing(loc, node, flow, conditional)
        return self.variable_info_output(output, name, code, shape, length, missing)

    def robot_variable_info(self, path, output, node, flow):
        address = _parse_system_variable_path(path.upper())
        status, description = 1, None
        if address is not None:
            try:
                robot = self.query_robot_group('VAR_INFO', address[1], node, flow)
                status, description = inspect_robot_variable(flow.robot_tables, robot, address, node.get('line'), self.tick)
            except RobotFactsUnavailable as error:
                self.unresolved_at('robot-tables', str(error), node)
                for loc in output[:5]:
                    self.write(loc, _Value(complete=False, spec=loc.spec), flow, node, definite=False)
                status = UNKNOWN
            except rt.KarelRuntimeError:
                pass
        if description is not None:
            return self.variable_info_output(output, *description)
        return (None,) * 5 + (_Value(status, spec=['INTEGER']),)

    def variable_info_output(self, output, name, code, shape, length, missing):
        width = output[1].spec[1]
        text = name[:width] if type(width) is int else UNKNOWN
        return (_Value(missing, spec=['BOOLEAN']), _Value(text, spec=output[1].spec), _Value(code, spec=['INTEGER']),
                self.catalog_array_value(output[3], shape), _Value(length, spec=['INTEGER']),
                _Value(0, spec=['INTEGER']))

    def program_list_values(self, known, output, node, flow, conditional):
        pattern, kind, skip, form = known
        cursor = output[3] if len(output) == 4 else None
        offset = self.read(cursor, node, flow, conditional).constant if cursor is not None else 0
        if (type(pattern) is not str or not pattern.isascii()
                or not all(type(value) is int for value in (kind, skip, form, offset))):
            return None
        options = effective_program_list_options(pattern, kind, skip, form, offset)
        if options is None:
            return None, None, _Value(2, spec=['INTEGER'])
        buffer = self.catalog_buffer(output[0])
        if buffer is None or self.saved_bindings is None:
            return None
        owners = self.linked_plans if self.linked_plans is not None else (self.program,)
        bank = self.saved_bindings.teach_programs
        teach_entries = self.teach_listing_entries(bank, flow, options[0], kind) if bank is not None else ()
        if teach_entries is None:
            return None
        saved = self.saved_bindings.program_catalog()
        # The runtime scans all entries even when the pattern selects one.
        size = len(owners) * (2 if self.linked_plans is not None else 1) + len(saved) + 1
        teach_bound = self.teach_listing_bound(bank, flow) if bank is not None else 0
        if size + teach_bound > CATALOG_SCAN_LIMIT:
            return None
        self.tick(size + len(teach_entries))
        catalog = {(name, 'PC') for name in owners}
        catalog.update(saved)
        catalog.update(teach_entries)
        capacity, width = buffer
        status, text = program_list_page(catalog, options, capacity, width)
        if status:
            return None, None, _Value(status, spec=['INTEGER'])
        values = self.catalog_page_outputs(output[0], capacity, text)
        return values if cursor is None else (*values, _Value(offset+len(text), spec=['INTEGER']))

    def attached_initialization(self, plan, node, flow, conditional):
        if plan.get('status') != 'available':
            return UNKNOWN
        for root in plan['types']:
            location = self.global_slot(root, node, program=plan['program'])
            if location is None:
                continue
            if location.spec[0] == 'PATH':
                if self.known_path_count(location, flow, conditional):
                    return True
            else:
                leaves = self.leaves(location)
                if leaves is not None and any(leaf.key in flow.defined for leaf in leaves):
                    return True
        return UNKNOWN if plan['types'] else False

    def update_program_attribute(self, name, key, value, record, attached, teach_header, flow):
        if key not in PROGRAM_WRITABLE_ATTRIBUTES:
            return 2
        active_call = name == self.program or name in self.task_roots or any(
            frame['key'][0] == name for frame in self.frames
        )
        active = record.get('active', False) if record is not None else False
        if active_call or active is True:
            return 4
        if self.saved_bindings is None or name in flow.requested_tasks:
            return None
        if attached and self.saved_bindings.program_attributes is None:
            return None
        if value is not UNKNOWN:
            try:
                with rt._numeric_scope('pythonic'):
                    value = ProgramAttributes._value(key, value)
            except rt.KarelRuntimeError:
                return None
        if teach_header:
            if active is UNKNOWN:
                flow.teach.catalog.maybe_write_header(name, key, value)
            else:
                flow.teach.catalog.write_header(name, key, value)
        else:
            if active is UNKNOWN:
                previous = flow.program_attributes.get((name, key))
                value = MAYBE_ATTRIBUTE if previous is None or previous is MAYBE_ATTRIBUTE else UNKNOWN
            flow.program_attributes[name, key] = value
            if len(flow.program_attributes) > MAX_FACTS:
                raise _Limit('Analysis storage limit reached')
        return UNKNOWN if active is UNKNOWN else 0

    def program_metadata_values(self, operation, known, outputs, node, flow, conditional):
        writing = operation == 'SET_ATTR_PRG'
        payload = () if writing else (None, None)
        key = None
        if operation != 'LOAD_STATUS':
            selector = known[1]
            if type(selector) is not int:
                return None
            key = program_attribute_key(selector)
            if key is None:
                return (*payload, _Value(2, spec=['INTEGER']))

        name = known[0]
        if type(name) is not str or not name.isascii():
            return None
        name = name.upper()
        valid = re.fullmatch(r'[A-Z_][A-Z_0-9]{0,35}', name) is not None
        plan = self.binding_plan(name) if valid else None
        attached = plan is not None
        external = None
        record = None
        entry = None
        bank = getattr(self.saved_bindings, 'teach_programs', None)
        if valid and self.saved_bindings is not None:
            teach = None
            if bank is not None and not attached:
                entry = flow.teach.catalog.entry(bank, name)
                if entry is UNKNOWN:
                    return None
                if entry is not None:
                    teach = self.teach_inspection_metadata(bank, name, entry, flow)
            external = self.saved_bindings.program_attribute_record(name)
            record = merge_program_record(external, teach, attached=attached)
        known_context = self.saved_bindings is not None or not valid
        if operation == 'LOAD_STATUS':
            if attached:
                initialized = self.attached_initialization(plan, node, flow, conditional)
                return _Value(True, spec=['BOOLEAN']), _Value(initialized, spec=['BOOLEAN'])
            if known_context:
                loaded, initialized = (record.get('loaded', False), record.get('initialized', False)) if record is not None else (False, False)
                return _Value(loaded, spec=['BOOLEAN']), _Value(initialized, spec=['BOOLEAN'])
            return None

        if not attached and record is None:
            return (*payload, _Value(1, spec=['INTEGER'])) if known_context else None
        if writing:
            value = known[3] if key in PROGRAM_TEXT_ATTRIBUTES else known[2]
            teach_header = entry is not None and external is None
            status = self.update_program_attribute(name, key, value, record, attached, teach_header, flow)
            return (_Value(status, spec=['INTEGER']),) if status is not None else None
        if not known_context and key not in ('AT_PROG_NAME', 'AT_PROG_TYPE'):
            return None
        if attached and key == 'AT_COMMENT' and 'source_comment' not in plan and (
                record is None or key not in record['attributes']):
            return None
        comment = plan.get('source_comment') if attached else None
        value = program_attribute_value(name, key, record, attached=attached, comment=comment)
        updated = flow.program_attributes.get((name, key))
        if updated is None or updated is MAYBE_ATTRIBUTE:
            self.teach_header_input(entry, name, key, external, updated is MAYBE_ATTRIBUTE, node, flow, conditional)
        if updated is MAYBE_ATTRIBUTE:
            if value is None:
                target = outputs[1] if key in PROGRAM_TEXT_ATTRIBUTES else outputs[0]
                self.write(target, _Value(spec=target.spec), flow, node, definite=False)
                return None, None, _Value(spec=['INTEGER'])
            value = UNKNOWN
        elif updated is not None:
            value = updated
        if value is None:
            return None, None, _Value(3, spec=['INTEGER'])
        status = _Value(0, spec=['INTEGER'])
        if key in PROGRAM_TEXT_ATTRIBUTES:
            spec = outputs[1].spec
            value = value[:spec[1]] if type(value) is str and type(spec[1]) is int else UNKNOWN
            return None, _Value(value, spec=spec), status
        return _Value(value, spec=['INTEGER']), None, status

    def program_metadata_cases(self, operation, inputs):
        if operation == 'LOAD_STATUS':
            cases = operand_cases(inputs, (0,))
            return cases if all(type(case[0]) is str for case in cases) else ()
        cases = operand_cases(inputs, (0, 1))
        if not cases and inputs[1].constant is not UNKNOWN:
            return ()
        bases = cases or [[value.constant for value in inputs]]
        if any(type(case[0]) is not str for case in bases):
            return ()
        if operation == 'SET_ATTR_PRG':
            # Every read-only selector has the same effect as AT_PROG_TYPE.
            keys = (*sorted(PROGRAM_WRITABLE_ATTRIBUTES), 'AT_PROG_TYPE')
        else:
            keys = PROGRAM_ATTRIBUTES
        selectors = (0, *(PROGRAM_ATTRIBUTES[key] for key in keys))
        expanded = []
        for name, selector, *rest in bases:
            if selector is UNKNOWN:
                expanded.extend([name, item, *rest] for item in selectors)
            else:
                expanded.append([name, selector, *rest])
            if len(expanded) > MAX_SERVICE_CASES:
                return ()
        return expanded

    def program_metadata_case(self, operation, known, outputs, node, flow):
        values = self.program_metadata_values(operation, known, outputs, node, flow, True)
        if values is not None:
            for loc, value in zip(outputs, values):
                if value is not None:
                    self.write(loc, value, flow, node)
            return
        self.unresolved_at('program-catalog', operation+' has an unresolved program or header value', node)
        if operation == 'SET_ATTR_PRG':
            self.uncertain_program_attribute_write(known, outputs[-1], node, flow)
        else:
            self.uncertain_program_receive(operation, known, outputs, node, flow)

    def uncertain_program_attribute_write(self, known, status, node, flow):
        """An unresolved write to a known name can affect only its selected field."""
        name, selector = known[:2]
        key = program_attribute_key(selector) if type(selector) is int else None
        if (key in PROGRAM_WRITABLE_ATTRIBUTES and name.isascii()
                and re.fullmatch(r'[A-Z_][A-Z_0-9]{0,35}', name.upper())):
            name = name.upper()
            external = self.saved_bindings.program_attribute_record(name) if self.saved_bindings is not None else None
            attached = self.binding_plan(name) is not None
            if attached or external is not None:
                previous = flow.program_attributes.get((name, key))
                flow.program_attributes[name, key] = MAYBE_ATTRIBUTE if previous is None or previous is MAYBE_ATTRIBUTE else UNKNOWN
                if len(flow.program_attributes) > MAX_FACTS:
                    raise _Limit('Analysis storage limit reached')
            elif getattr(self.saved_bindings, 'teach_programs', None) is not None:
                flow.teach.catalog.maybe_write_header(name, key, UNKNOWN)
        self.bank_status(status, UNKNOWN, flow, node)

    def uncertain_program_receive(self, operation, known, outputs, node, flow):
        if operation == 'LOAD_STATUS':
            for loc in outputs:
                self.write(loc, _Value(spec=loc.spec), flow, node)
        elif operation == 'GET_ATTR_PRG':
            key = program_attribute_key(known[1]) if type(known[1]) is int else None
            receivers = (outputs[int(key in PROGRAM_TEXT_ATTRIBUTES)],) if key is not None else outputs[:-1]
            self.uncertain_bank_read(receivers, outputs[-1], flow, node)
        else:
            self.uncertain_bank_read(outputs[:2] + outputs[3:], outputs[2], flow, node)

    def service_operands(self, node, input_count, flow, conditional, *, trailing=0, complete_input=None,
                         unused_array_input=None):
        values = []
        with self.capture_operands() as pending:
            for index, arg in enumerate(node['args'][:input_count]):
                if index == unused_array_input:
                    value = self.capture_unused_service_array(arg, flow, conditional)
                else:
                    value = self.expr(arg, flow, conditional)
                if flow.stopped and not flow.opaque:
                    return None
                if index == complete_input and _known_missing(value):
                    self.unresolved_at('position-data', node['value']+' reads a known uninitialized position field', arg)
                    flow.stopped = True
                    return None
                values.append(value)
            output_end = len(node['args']) - trailing
            for arg in node['args'][input_count:output_end]:
                pending.append(self.locate(arg, flow, conditional, capture_node=True,
                                           selector_path_edits=bool(pending)))
                if flow.stopped and not flow.opaque:
                    return None
            for arg in node['args'][output_end:]:
                values.append(self.expr(arg, flow, conditional, argument_path_edits=all(loc is not None for loc in pending)))
                if flow.stopped and not flow.opaque:
                    return None
            outputs = [self.resolve_path_slot(loc, node, flow) if loc is not None else None for loc in pending]
        return values, outputs

    def address_service_cases(self, inputs, indices, flow, conditional, transfer, *, handle=False, result=False):
        """Use captured operands and refine only the selected slot for each case."""
        if not self.teach_stable(flow):
            return transfer(inputs, flow, conditional)
        constants = [item.constant for item in inputs]
        addressed = operand_cases(inputs, indices) or [constants]
        state = flow.teach
        tracked_numbers = ()
        if handle and state.handles is not None and not state.untracked_handles and len(state.handles) < MAX_SERVICE_CASES:
            # A dynamic number can select a tracked slot or fail to address any slot.
            tracked_numbers = (0, *state.handles)
        cases = []
        for original in addressed:
            first = original[0]
            numbers = tracked_numbers if first is UNKNOWN and tracked_numbers else (first,)
            for number in numbers:
                values = original if number is first else [number, *original[1:]]
                options = self.teach_resolved_handle_choices(number, flow) if handle and type(number) is int else ()
                if len(options) > 1:
                    cases.extend((values, (number, choice)) for choice in options)
                else:
                    cases.append((values, None))
                if len(cases) > MAX_SERVICE_CASES:
                    return transfer(inputs, flow, conditional)
        if len(cases) == 1 and cases[0][1] is None and cases[0][0] is constants:
            return transfer(inputs, flow, conditional)

        def evaluate(case, branch):
            values, selected = case
            resolved = list(inputs)
            for index in indices:
                if values[index] is not constants[index]:
                    resolved[index] = replace(inputs[index], constant=values[index], scalar_choices=())
            if selected is not None:
                number, choice = selected
                branch.teach.set_handle_choices(number, (choice,))
            return transfer(resolved, branch, True)

        return self.apply_service_cases(flow, cases, evaluate, merge_results=result)

    def apply_service_cases(self, flow, cases, evaluate, *, merge_results=False):
        """Apply alternative service outcomes without carrying unbounded snapshots."""
        combined = None
        values = []
        first = None
        for index, case in enumerate(cases):
            self.tick()
            branch = flow.copy()
            value = evaluate(case, branch)
            if merge_results:
                if index == 0:
                    first = value
                if not branch.stopped:
                    values.append(value)
            combined = branch if combined is None else _merge([combined, branch])
        flow.take(combined)
        if merge_results:
            return _merged_value(values) if values else first
        return None

    def service_outputs_overlap(self, outputs):
        return any(self.path_contains_reference(loc, old) or self.path_contains_reference(old, loc)
                   for index, loc in enumerate(outputs) for old in outputs[:index])

    def inspection_call(self, node, flow, conditional):
        operation = node['value']
        inputs = {'VAR_INFO': 2, 'VAR_LIST': 5, 'PROG_LIST': 4, 'LOAD_STATUS': 1,
                  'GET_ATTR_PRG': 2, 'SET_ATTR_PRG': 4}[operation]
        operands = self.service_operands(node, inputs, flow, conditional)
        if operands is None:
            return _Value(complete=False)
        inputs, outputs = operands
        known = [value.constant for value in inputs]
        values = None
        ordinary_outputs = False
        if not (flow.opaque or flow.task_order_unknown or self.repeat_depth or self.callback_depth or flow.handlers
                or any(loc is None for loc in outputs)):
            if self.service_outputs_overlap(outputs):
                return self.reject_service_overlap(node, flow)
            if operation == 'VAR_INFO':
                dims, leaf = _array_dimensions(outputs[3].spec)
                if None not in dims and (dims != [3] or leaf != ['INTEGER']):
                    return self.reject_service_overlap(node, flow, 'VAR_INFO dimensions require ARRAY[3] OF INTEGER')
            ordinary_outputs = all(self.ordinary_variable_output(loc, node) for loc in outputs)
            if ordinary_outputs:
                if operation == 'VAR_LIST':
                    values = self.variable_list_values(known, outputs, flow)
                elif operation == 'VAR_INFO':
                    values = self.variable_info_values(known, outputs, node, flow, conditional)
                elif operation == 'PROG_LIST':
                    values = self.program_list_values(known, outputs, node, flow, conditional)
                else:
                    cases = self.program_metadata_cases(operation, inputs)
                    if cases:
                        self.apply_service_cases(
                            flow, cases, lambda case, branch: self.program_metadata_case(operation, case, outputs, node, branch),
                        )
                        return _Value()
                    values = self.program_metadata_values(operation, known, outputs, node, flow, conditional)
        if values is None:
            code = 'variable-catalog' if operation in ('VAR_INFO', 'VAR_LIST') else 'program-catalog'
            self.unresolved_at(code, operation+' requires a known catalog, lookup and output storage', node)
            if ordinary_outputs and operation in ('LOAD_STATUS', 'GET_ATTR_PRG', 'PROG_LIST'):
                self.uncertain_program_receive(operation, known, outputs, node, flow)
            elif ordinary_outputs and operation == 'SET_ATTR_PRG' and type(known[0]) is str and type(known[1]) is int:
                self.uncertain_program_attribute_write(known, outputs[-1], node, flow)
            else:
                self.opaque(flow)
            return _Value(complete=False)
        for loc, value in zip(outputs, values):
            if value is not None:
                self.write(loc, value, flow, node)
        return _Value()

    def bank_call(self, node, flow, conditional):
        operation = node['value']
        register = operation in REGISTER_SERVICES
        input_count = (1 if register else 2) + int(operation.startswith('SET_'))
        operands = self.service_operands(node, input_count, flow, conditional)
        if operands is None:
            return _Value(complete=False)
        inputs, outputs = operands
        if all(loc is not None for loc in outputs) and not flow.opaque and self.service_outputs_overlap(outputs):
            return self.reject_service_overlap(node, flow)
        if not all(loc is not None and self.ordinary_variable_output(loc, node) for loc in outputs):
            self.unresolved_at('service-output', operation+' requires known ordinary output storage', node)
            self.opaque(flow)
            return _Value(complete=False)
        stable = self.teach_stable(flow)
        transfer = self.register_transfer if register else self.indirect_ports
        self.address_service_cases(
            inputs, (0,) if register else (0, 1), flow, conditional,
            lambda values, branch, possible: transfer(operation, values, outputs, node, branch, possible, stable),
        )
        return _Value()

    def bank_status(self, status, code, flow, node):
        self.write(status, _Value(code, spec=['INTEGER']), flow, node)

    def uncertain_bank_read(self, outputs, status, flow, node, *, code=UNKNOWN):
        for output in outputs:
            self.write(output, _Value(spec=output.spec), flow, node, definite=False)
        self.bank_status(status, code, flow, node)

    def invalidate_bank_constants(self, kind, flow):
        self.tick(len(flow.constants) + len(flow.scalar_choices))
        flow.constants = {key: value for key, value in flow.constants.items() if key[0] != kind}
        flow.scalar_choices = {key: values for key, values in flow.scalar_choices.items() if key[0] != kind}

    def register_transfer(self, operation, inputs, outputs, node, flow, conditional, stable):
        service, kind = REGISTER_SERVICES[operation]
        numeric = service == 'numeric'
        location_kind = 'numeric_register' if numeric else 'string_register'
        number = inputs[0].constant
        reading = operation.startswith('GET_')
        *receivers, status = outputs
        adapter = getattr(self.saved_bindings, service, None)
        if type(number) is not int or adapter is None and number < 1:
            self.unresolved_at('dynamic-address', 'Register address requires an explicit runtime mapping', node)
            if not reading:
                self.invalidate_bank_constants(location_kind, flow)
                if numeric:
                    flow.numeric_kinds.clear()
            self.uncertain_bank_read(receivers, status, flow, node)
            return
        storage = [kind] if numeric else ['STRING', None if reading or adapter is None else adapter.capacity]
        if not reading:
            value = inputs[1].constant
            if value is not UNKNOWN and (numeric or adapter is not None):
                try:
                    with rt._numeric_scope('pythonic'):
                        value = rt.checked(tuple_spec(storage), value)
                except rt.KarelRuntimeError:
                    self.unresolved_at('register-value', operation+' cannot store the resolved value', node)
                    flow.stopped = True
                    return
            else:
                value = UNKNOWN
        if adapter is not None and not 1 <= number <= adapter.count:
            self.bank_status(status, rt.REGISTER_OUT_OF_RANGE, flow, node)
            return
        loc = _Location(location_kind, '', number, spec=storage)
        self.context(service, loc.path)
        if not reading:
            self.write(loc, _Value(value, spec=storage), flow, node)
            if numeric:
                flow.numeric_kinds[number] = kind
            self.bank_status(status, 0 if stable and adapter is not None else UNKNOWN, flow, node)
            return
        value = self.read(loc, node, flow, conditional)
        present = stable and adapter is not None and (loc.key in flow.defined or adapter.read(number)[0] == 0)
        if not present:
            self.uncertain_bank_read(receivers, status, flow, node)
            return
        if not numeric:
            target = receivers[0]
            text = value.constant[:target.spec[1]] if type(value.constant) is str and type(target.spec[1]) is int else UNKNOWN
            self.write(target, _Value(text, spec=target.spec), flow, node)
            self.bank_status(status, 0, flow, node)
            return
        stored_kind = flow.numeric_kinds.get(number)
        flag, integer, real = receivers
        is_real = stored_kind == 'REAL' if stored_kind is not None else UNKNOWN
        self.write(flag, _Value(is_real, spec=['BOOLEAN']), flow, node)
        if is_real is UNKNOWN:
            self.uncertain_bank_read((integer, real), status, flow, node, code=0)
        else:
            target = real if is_real else integer
            self.write(target, _Value(value.constant, spec=target.spec), flow, node)
            self.bank_status(status, 0, flow, node)

    def indirect_ports(self, operation, inputs, outputs, node, flow, conditional, stable):
        adapter = getattr(self.saved_bindings, 'ports', None)
        code, number = [value.constant for value in inputs[:2]]
        *receivers, status = outputs
        if adapter is None or not adapter.type_codes or type(code) is not int or type(number) is not int:
            self.context('ports', None)
            self.unresolved_at('dynamic-address', operation+' requires a known index and explicit port type-code mapping', node)
            if operation in ('SET_PORT_VAL', 'SET_PORT_SIM'):
                self.invalidate_bank_constants('port', flow)
            if operation in ('SET_PORT_SIM', 'CLR_PORT_SIM'):
                # An unknown selection can change the simulation state of any input.
                flow.port_simulation = {None: UNKNOWN}
            self.uncertain_bank_read(receivers, status, flow, node)
            return
        kind = adapter.type_codes.get(code)
        if not adapter.contains(kind, number):
            self.bank_status(status, 2, flow, node)
            return
        loc = _Location('port', '', kind, (('index', number),), [PORT_TYPES[kind]])
        self.context('ports', loc.path)
        address = kind, number
        default = UNKNOWN if None in flow.port_simulation else address in adapter.simulated
        simulated = flow.port_simulation.get(address, default) if stable else UNKNOWN
        if operation == 'CLR_PORT_SIM':
            flow.port_simulation[address] = False if stable else UNKNOWN
            self.bank_status(status, 0 if stable else UNKNOWN, flow, node)
        elif operation == 'GET_PORT_SIM':
            target = receivers[0]
            value = int(simulated) if target.spec == ['INTEGER'] and type(simulated) is bool else simulated
            self.write(target, _Value(value, spec=target.spec), flow, node)
            self.bank_status(status, 0 if stable else UNKNOWN, flow, node)
        elif operation == 'GET_PORT_VAL':
            self.read_indirect_port(loc, receivers[0], status, node, flow, conditional, stable,
                                    supplied=address in adapter.values)
        else:
            self.write_indirect_port(loc, address, inputs[2], status, operation == 'SET_PORT_SIM',
                                     simulated, node, flow, stable)

    def converted_port_value(self, value, spec):
        with rt._numeric_scope('pythonic'):
            converted = port_value(value, spec[0])
            if spec[0] == 'STRING' and spec[1] is None:
                return UNKNOWN
            return rt.checked(tuple_spec(spec), converted)

    def read_indirect_port(self, loc, output, status, node, flow, conditional, stable, *, supplied):
        value = self.read(loc, node, flow, conditional)
        if not stable or not (supplied or loc.key in flow.defined):
            self.uncertain_bank_read((output,), status, flow, node)
            return
        constant = value.constant
        if constant is UNKNOWN:
            source_kind, target_kind = loc.spec[0], output.spec[0]
            if target_kind not in ('STRING', 'REAL', source_kind) and source_kind != 'BOOLEAN':
                self.uncertain_bank_read((output,), status, flow, node)
                return
        else:
            try:
                constant = self.converted_port_value(constant, output.spec)
            except (ValueError, OverflowError, rt.KarelRuntimeError):
                self.bank_status(status, 3, flow, node)
                return
        self.write(output, _Value(constant, spec=output.spec), flow, node)
        self.bank_status(status, 0, flow, node)

    def write_indirect_port(self, loc, address, value, status, simulate, simulated, node, flow, stable):
        eligible = simulate or address[0] in OUTPUT_PORTS or simulated
        if eligible is False:
            self.bank_status(status, 4, flow, node)
            return
        constant = value.constant
        code = UNKNOWN
        if constant is not UNKNOWN:
            try:
                constant = self.converted_port_value(constant, loc.spec)
                if loc.spec == ['INTEGER'] and constant < 0:
                    raise ValueError('Group ports require nonnegative INTEGER values')
            except (ValueError, OverflowError, rt.KarelRuntimeError):
                self.bank_status(status, 3 if eligible is True else UNKNOWN, flow, node)
                return
            if eligible is True and stable:
                code = 0
        elif (eligible is True and stable and value.spec
              and (value.spec == ['BOOLEAN'] or loc.spec == ['REAL'] and value.spec[0] in ('REAL', 'INTEGER'))):
            code = 0
        self.write(loc, _Value(constant, spec=loc.spec), flow, node, definite=code == 0)
        if simulate:
            flow.port_simulation[address] = True if code == 0 or simulated is True else UNKNOWN
        self.bank_status(status, code, flow, node)

    def default_position_group(self, adapter):
        root = self.binding_plan(self.task_roots[-1])
        explicit = root.get('default_group') if root is not None else None
        if explicit is not None:
            return explicit
        robot = getattr(self.saved_bindings, 'robot', None)
        if robot is not None:
            return robot.active_group or 1
        return 1 if adapter is not None else None

    def position_register_call(self, node, flow, conditional):
        operation = node['value']
        target = POSITION_GETTERS.get(operation)
        setter = operation in POSITION_SETTERS
        clear = operation == 'CLR_POS_REG'
        argc = len(node['args'])
        if target or setter:
            count = 2 if setter else 1
            trailing = int(argc > count + 1)
            explicit = trailing != 0
        else:
            count = argc - (1 if clear else 3)
            trailing = 0
            explicit = count == 2
        operands = self.service_operands(node, count, flow, conditional, trailing=trailing,
                                         complete_input=1 if setter else None)
        if operands is None:
            return _Value(complete=False)
        inputs, outputs = operands
        if all(loc is not None for loc in outputs) and self.service_outputs_overlap(outputs):
            return self.reject_service_overlap(node, flow)
        if not all(loc is not None and self.ordinary_variable_output(loc, node) for loc in outputs):
            self.unresolved_at('service-output', operation+' requires known ordinary output storage', node)
            self.opaque(flow)
            return _Value(complete=False)

        value = self.address_service_cases(
            inputs, (0, len(inputs) - 1) if explicit else (0,), flow, conditional,
            lambda values, branch, possible: self.position_register_transfer(
                values, outputs, node, branch, possible, explicit=explicit,
            ), result=bool(target),
        )
        return value if target else _Value()

    def position_register_transfer(self, inputs, outputs, node, flow, conditional, *, explicit):
        operation = node['value']
        target = POSITION_GETTERS.get(operation)
        setter = operation in POSITION_SETTERS
        clear = operation == 'CLR_POS_REG'
        adapter = getattr(self.saved_bindings, 'positions', None)
        stable = self.teach_stable(flow)
        group = inputs[-1].constant if explicit else self.default_position_group(adapter)
        number = inputs[0].constant
        *receivers, status = outputs
        result = _Value(spec=list(target)) if target else _Value()
        if type(number) is not int or explicit and type(group) is not int or adapter is None and (
                number < 1 or group is not None and group < (0 if clear else 1)):
            self.unresolved_at('dynamic-address', 'Position register address requires a known number and group', node)
            if clear or setter:
                flow.position_cells.clear()
                flow.position_order_unknown = True
            self.uncertain_bank_read(receivers, status, flow, node, code=0 if target else UNKNOWN)
            return result
        address = group, number
        if adapter is not None and (not 1 <= number <= adapter.count
                                    or group not in adapter.groups and not (clear and group == 0)):
            if target:
                self.position_read_failed(operation, status, 2, node, flow, 'address is outside the configured bank')
            else:
                self.bank_status(status, 2, flow, node)
            return result
        loc = _Location('position_register', '', number, (('group', group),), result.spec)
        self.context('positions', None if clear and group == 0 else loc.path)
        if clear:
            self.clear_position(address, adapter, status, node, flow, stable)
        elif setter:
            self.set_position(operation, address, inputs[1], adapter, status, node, flow, stable)
        else:
            stored = flow.position_cells.get(address, UNKNOWN if flow.position_order_unknown else None) if stable else UNKNOWN
            initial = adapter.values.get(address) if adapter is not None and stored is None else None
            if target:
                return self.get_position(operation, loc, stored, initial, status, node, flow, conditional)
            self.inspect_position(stored, initial, receivers, status, node, flow, stable and adapter is not None)
        return result

    def clear_position(self, address, adapter, status, node, flow, stable):
        group, number = address
        if group == 0 and adapter is None:
            flow.position_cells.clear()
            flow.position_order_unknown = True
        else:
            groups = adapter.groups if group == 0 else (group,)
            self.tick(len(groups))
            for member in groups:
                flow.position_cells[member, number] = POSITION_CLEARED if stable and adapter is not None else UNKNOWN
        self.bank_status(status, 0 if stable and adapter is not None else UNKNOWN, flow, node)

    def set_position(self, operation, address, source, adapter, status, node, flow, stable):
        kind = source.spec[0] if source.spec else None
        if kind not in ('POSITION', 'XYZWPR', 'XYZWPREXT', 'JOINTPOS'):
            self.unresolved_at('position-data', operation+' requires a known source pose or joint schema', node)
            flow.position_cells[address] = UNKNOWN
            self.bank_status(status, UNKNOWN, flow, node)
            return
        cross_model = (kind == 'JOINTPOS') != (operation == 'SET_JPOS_REG')
        if cross_model:
            self.context('robot', None)
            if adapter is not None and self.saved_bindings.robot is None and stable:
                self.bank_status(status, 3, flow, node)
                return
            target = ['JOINTPOS', 9] if operation == 'SET_JPOS_REG' else ['XYZWPREXT']
            converted = self.position_model_value(operation, address[0], target, source, node, flow)
            if flow.stopped and not flow.opaque:
                return
            flow.position_cells[address] = (converted or _Value(spec=target)) if stable else UNKNOWN
            code = 0 if converted is not None and stable and adapter is not None else UNKNOWN
        else:
            flow.position_cells[address] = checked_position_facts(source) if stable else UNKNOWN
            code = 0 if stable and adapter is not None else UNKNOWN
        self.bank_status(status, code, flow, node)

    def position_model_value(self, operation, group, target, value, node, flow):
        try:
            selected = self.selected_robot_for_discovery(operation, node, flow, group=group)
            return convert_known_robot_value(selected, target, value, node.get('line'), self.tick, operation=operation)
        except RobotFactsUnavailable as error:
            self.unresolved_at('position-model', str(error), node)
        except (rt.KarelRuntimeError, TypeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('position-model', str(error), node)
            flow.stopped = True
        return None

    def inspect_position(self, stored, initial, receivers, status, node, flow, configured):
        if stored is POSITION_CLEARED:
            self.bank_status(status, 1, flow, node)
            return
        spec = tuple_spec(stored.spec) if isinstance(stored, _Value) and stored.spec else getattr(initial, 'spec', None)
        if configured and spec is not None:
            kind, axes = register_description(spec)
            for output, value in zip(receivers, (kind, axes)):
                self.write(output, _Value(value, spec=['INTEGER']), flow, node)
            self.bank_status(status, 0, flow, node)
            return
        present = configured and isinstance(stored, _Value)
        if present:
            for output in receivers:
                self.write(output, _Value(spec=['INTEGER']), flow, node)
            self.bank_status(status, 0, flow, node)
        else:
            self.uncertain_bank_read(receivers, status, flow, node)

    def position_read_failed(self, operation, status, code, node, flow, reason):
        self.bank_status(status, code, flow, node)
        self.unresolved_at('position-read', operation+' cannot return a value because the '+reason, node)
        flow.stopped = True

    def get_position(self, operation, loc, stored, initial, status, node, flow, conditional):
        result = _Value(spec=loc.spec)
        if stored is POSITION_CLEARED:
            self.position_read_failed(operation, status, 1, node, flow, 'source cleared the register')
            return result
        if not isinstance(stored, _Value) and stored is not POSITION_MODIFIED:
            self.read(loc, node, flow, conditional or stored is UNKNOWN, partial=True)
        spec = stored.spec if isinstance(stored, _Value) else initial.spec if initial is not None else None
        if spec and (spec[0] == 'JOINTPOS') != (loc.spec[0] == 'JOINTPOS'):
            self.context('robot', None)
            if (isinstance(stored, _Value) and self.saved_bindings is not None
                    and self.saved_bindings.positions is not None and self.saved_bindings.robot is None):
                self.position_read_failed(operation, status, 3, node, flow, 'stored representation requires a robot model')
                return result
            if isinstance(stored, _Value):
                converted = self.position_model_value(operation, loc.parts[0][1], loc.spec, stored, node, flow)
                if flow.stopped and not flow.opaque:
                    return result
                if converted is not None:
                    result = converted
            else:
                self.unresolved_at('position-model', operation+' needs the editable saved register value at run time', node)
        elif isinstance(stored, _Value) and spec:
            try:
                result = position_register_result(loc.spec, stored, tick=self.tick)
            except (rt.KarelRuntimeError, TypeError, ValueError) as error:
                self.unresolved_at('position-data', 'Position register conversion failed: '+str(error), node)
                flow.stopped = True
                return result
        self.bank_status(status, 0, flow, node)
        return result

    def teach_input(self, kind, program, number, spec, node, flow, conditional, *, group=None):
        parts = (('group', group),) if group is not None else ()
        loc = _Location(kind, program, number, parts, spec)
        self.read(loc, node, flow, conditional, partial=group is not None)

    @staticmethod
    def robot_table_path(node):
        fields = []
        while node['kind'] in ('field', 'group'):
            if node['kind'] == 'field':
                fields.append(node['value'])
            node = node['args'][0]
        return node, tuple(reversed(fields))

    def robot_table_selectors(self, root, flow, conditional):
        selectors = []
        for arg in root['args']:
            if flow.stopped and not flow.opaque:
                return UNKNOWN, UNKNOWN
            selectors.append(self.expr(arg, flow, conditional).constant)
        return selectors[0], selectors[1] if len(selectors) == 2 else None

    def robot_table_expression(self, root, fields, node, flow, conditional):
        operation = root['value']
        selection = root['kind'] == 'system_selection'
        group, number = self.robot_table_selectors(root, flow, conditional)
        if not flow.stopped or flow.opaque:
            try:
                robot = self.query_robot_group(operation, group, node, flow)
                return flow.robot_tables.read(robot, group, operation, number, fields,
                                              selection=selection, line=node.get('line'))
            except RobotFactsUnavailable as error:
                self.unresolved_at('robot-tables', str(error), node)
            except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
                self.unresolved_at('robot-tables', str(error), node)
                flow.stopped = True
        return _Value(complete=False, spec=['INTEGER'] if selection else ['POSITION'] if not fields else None)

    def robot_table_assignment(self, target, operand, node, flow, conditional):
        root, fields = self.robot_table_path(target)
        operation = root['value']
        selection = root['kind'] == 'system_selection'
        value = self.expr(operand, flow, conditional, partial=True)
        if flow.stopped and not flow.opaque:
            return
        source = materialized_value(value)
        line = node.get('line')
        if isinstance(source, rt.JointPosition):
            try:
                group = self.default_position_group(None)
                robot = self.query_robot_group(operation, group, node, flow)
                selected = flow.robot_tables.selected_robot(robot, group)
                source = evaluate_robot_assignment(selected, ('XYZWPREXT',), source, line, self.tick,
                                                   operation='JOINTPOS table write')
            except RobotFactsUnavailable as error:
                self.unresolved_at('robot-tables', str(error), node)
                source = UNKNOWN
            except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
                self.unresolved_at('robot-tables', str(error), node)
                flow.stopped = True
                return
        group, number = self.robot_table_selectors(root, flow, conditional)
        if flow.stopped and not flow.opaque:
            return
        try:
            try:
                robot = self.query_robot_group(operation, group, node, flow)
            except RobotFactsUnavailable:
                robot = None
            flow.robot_tables.write(robot, None if group is UNKNOWN else group, operation, number, fields,
                                    source, selection=selection, line=line)
        except RobotFactsUnavailable as error:
            self.unresolved_at('robot-tables', str(error), node)
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('robot-tables', str(error), node)
            flow.stopped = True

    def selected_robot_for_discovery(self, operation, node, flow, *, group=None):
        if group is None:
            group = self.default_position_group(None)
        robot = self.query_robot_group(operation, group, node, flow)
        return flow.robot_tables.selected_robot(robot, group)

    def query_robot_group(self, operation, group, node, flow):
        self.context('robot', None)
        if group is UNKNOWN or flow.opaque or flow.task_order_unknown or self.callback_depth or self.repeat_depth:
            raise RobotFactsUnavailable(operation+' depends on the group or execution order')
        root = getattr(self.saved_bindings, 'robot', None)
        if root is None:
            raise RobotFactsUnavailable(operation+' requires a saved robot context')
        return root.for_group(group, node.get('line'))

    def robot_snapshot_call(self, node, flow, conditional):
        operation = node['value']
        args = node['args']
        result = _Value(spec=list(ROBOT_SNAPSHOTS[operation]))
        with self.capture_operands() as pending:
            for arg in args[:2]:
                while arg['kind'] == 'group':
                    arg = arg['args'][0]
                if arg['kind'] == 'literal' and type(arg['value']) is int and arg['value'] == 0:
                    pending.append(None)
                else:
                    loc = self.locate(arg, flow, conditional, capture_node=True, selector_path_edits=bool(pending))
                    if loc is None:
                        self.unresolved_at('service-output', operation+' requires a known mask output or literal zero', arg)
                        self.opaque(flow)
                        return result
                    pending.append(loc)
                if flow.stopped and not flow.opaque:
                    return result
            group = (self.expr(args[2], flow, conditional, argument_path_edits=any(loc is not None for loc in pending)).constant
                     if len(args) == 3 else self.default_position_group(None))
            if flow.stopped and not flow.opaque:
                return result
            outputs = [self.resolve_path_slot(loc, node, flow) if loc is not None else None for loc in pending]
        active_outputs = [loc for loc in outputs if loc is not None]
        if self.service_outputs_overlap(active_outputs):
            return self.reject_service_overlap(node, flow)
        if not all(self.ordinary_variable_output(loc, node) for loc in active_outputs):
            self.unresolved_at('service-output', operation+' requires ordinary writable mask outputs', node)
            self.opaque(flow)
            return result
        masks = UNKNOWN, UNKNOWN
        try:
            robot = self.query_robot_group(operation, group, node, flow)
            result = current_robot_facts(robot, operation, node.get('line'),
                                         select=lambda: flow.robot_tables.selected_robot(robot, group))
            masks = robot.current.axis_limit_mask, robot.current.overtravel_mask
        except (RobotFactsUnavailable, rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('robot-state', str(error), node)
        for loc, mask in zip(outputs, masks):
            if loc is not None:
                self.write(loc, _Value(mask, spec=['INTEGER']), flow, node)
        return result

    def robot_range_call(self, node, flow, conditional):
        operation = node['value']
        framed = operation == 'CHECK_EPOS'
        status = None
        result = _Value(spec=['BOOLEAN']) if not framed else _Value()
        if framed:
            operands = self.service_operands(node, 3, flow, conditional, trailing=len(node['args']) - 4)
            if operands is None:
                return result
            inputs, (status,) = operands
            if status is None or not self.ordinary_variable_output(status, node):
                self.unresolved_at('service-output', operation+' requires a known ordinary status output', node)
                self.opaque(flow)
                return result
            group = inputs[3].constant if len(inputs) == 4 else self.default_position_group(None)
            values = inputs[:3]
        else:
            values = [self.expr(node['args'][0], flow, conditional)]
            group = self.default_position_group(None)
        if flow.stopped and not flow.opaque:
            return result
        answer = UNKNOWN
        try:
            robot = self.query_robot_group(operation, group, node, flow)
            answer = check_robot_range(robot, operation, values, node.get('line'),
                                       select=lambda: flow.robot_tables.selected_robot(robot, group), tick=self.tick)
        except (RobotFactsUnavailable, rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('robot-range', str(error), node)
        if framed:
            self.bank_status(status, 0 if answer is True else 1 if answer is False else UNKNOWN, flow, node)
        else:
            result.constant = answer
        return result

    def capture_unused_service_array(self, node, flow, conditional):
        """Evaluate an ARRAY's selector even when its cells cannot affect the model."""
        while node['kind'] == 'group':
            node = node['args'][0]
        if node['kind'] in ('name', 'field', 'index') and not self.selects_routine_result(node):
            location = self.locate(node, flow, conditional, reading=True)
            if location is not None:
                return _Value(spec=location.spec)
            if node['kind'] != 'name':
                return _Value(complete=False)
        return self.expr(node, flow, conditional)

    def checked_robot_service_outputs(self, outputs, node, flow):
        if all(loc is not None and self.ordinary_variable_output(loc, node) for loc in outputs):
            if self.service_outputs_overlap(outputs):
                self.reject_service_overlap(node, flow)
                return False
            return True
        self.unresolved_at('service-output', node['value']+' requires known ordinary writable outputs', node)
        self.opaque(flow)
        return False

    def robot_coordinate_call(self, node, flow, conditional):
        operation = node['value']
        group = self.default_position_group(None)
        unused = None
        if operation == 'POS2JOINT':
            root = getattr(self.saved_bindings, 'robot', None)
            if root is not None and not (flow.opaque or flow.task_order_unknown):
                try:
                    model = root.for_group(group).model
                except rt.KarelRuntimeError:
                    model = None
                if model is not None and model.external_axes == 0:
                    unused = 6
        operands = self.service_operands(node, ROBOT_CONVERSIONS[operation], flow, conditional,
                                         unused_array_input=unused)
        if operands is None:
            return _Value()
        inputs, outputs = operands
        if not self.checked_robot_service_outputs(outputs, node, flow):
            return _Value()
        try:
            robot = self.query_robot_group(operation, group, node, flow)
            values = convert_robot_coordinates(robot, operation, inputs, [loc.spec for loc in outputs],
                                                node.get('line'), self.tick)
        except RobotFactsUnavailable as error:
            self.unresolved_at('robot-conversion', str(error), node)
            # Every output is initialized when the procedure returns normally.
            values = [_Value(spec=loc.spec) for loc in outputs]
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('robot-conversion', str(error), node)
            flow.stopped = True
            return _Value()
        for loc, value in zip(outputs, values):
            self.write(loc, value, flow, node)
        return _Value()

    def config_text_call(self, node, flow, conditional):
        operation = node['value']
        grouped = operation == 'CNV_CNF_STRG' or len(node['args']) == 4
        operands = self.service_operands(node, 1, flow, conditional, trailing=int(len(node['args']) == 4))
        if operands is None:
            return _Value()
        inputs, outputs = operands
        if not self.checked_robot_service_outputs(outputs, node, flow):
            return _Value()
        group, formats = None, None
        if grouped:
            group = inputs[1].constant if len(inputs) == 2 else self.default_position_group(None) or 1
            self.context('config_text', None)
            formats = getattr(self.saved_bindings, 'config_text', None)
        try:
            if group is UNKNOWN or grouped and (formats is None or flow.opaque or flow.task_order_unknown):
                raise RobotFactsUnavailable(operation+' needs a known group and saved CONFIG text profile')
            values = convert_config_text(operation, inputs[0], [loc.spec for loc in outputs],
                                         node.get('line'), group=group, formats=formats)
        except RobotFactsUnavailable as error:
            self.unresolved_at('config-text', str(error), node)
            for position, loc in enumerate(outputs):
                definite = operation == 'CNV_CONF_STR' or position == 1
                self.write(loc, _Value(complete=definite, spec=loc.spec), flow, node, definite=definite)
            return _Value()
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('config-text', str(error), node)
            flow.stopped = True
            return _Value()
        for loc, value in zip(outputs, values):
            if value is not None:
                self.write(loc, value, flow, node)
        return _Value()

    def cartesian_assignment_value(self, target, value, node, flow):
        if value.spec is None:
            return _Value(spec=target)
        try:
            converted, unproven = convert_value_facts(target, value, tick=self.tick)
            if unproven:
                self.unresolved_at('conversion-value', 'Cartesian assignment requires complete source data', node)
            return converted
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('conversion-value', str(error), node)
            flow.stopped = True
            return _Value(spec=target)

    def geometry_value(self, conversion, target, value, node, flow, *, boundary):
        if conversion == 'cartesian':
            return self.cartesian_assignment_value(target, value, node, flow)
        kinds = {'kinematic': 'Kinematic', 'kinematic_array': 'Kinematic ARRAY',
                 'kinematic_record': 'Kinematic STRUCTURE'}
        operation = kinds[conversion]+' '+boundary
        group = self.default_position_group(None)
        try:
            robot = self.query_robot_group(operation, group, node, flow)
            if value.facts is not None:
                self.tick(len(value.facts))
            source = materialized_value(value, allow_missing=conversion != 'kinematic')
            if source is UNKNOWN:
                raise RobotFactsUnavailable(operation+' needs its source value at run time')
            selected = flow.robot_tables.selected_robot(robot, group)
            schema, line = tuple_spec(target), node.get('line')
            if conversion == 'kinematic':
                converted = evaluate_robot_assignment(selected, schema, source, line, self.tick, operation=operation)
            else:
                converted = evaluate_robot_aggregate(selected, conversion, schema, source, line, self.tick,
                                                      operation=operation)
            return detached_facts(converted)
        except RobotFactsUnavailable as error:
            self.unresolved_at('robot-conversion', str(error), node)
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('robot-conversion', str(error), node)
            flow.stopped = True
        spec = (_array_value_schema(target, value.spec) or target) if target[0] == 'ARRAY' else target
        return _Value(complete=conversion != 'kinematic_record', spec=spec)

    def geometry_operand_facts(self, operation, value, node, flow):
        joint = value.spec and value.spec[0] == 'JOINTPOS'
        line = node.get('line')
        try:
            if joint:
                selected = self.selected_robot_for_discovery(operation, node, flow)
                return convert_known_robot_value(selected, ['XYZWPREXT'], value, line, self.tick, operation=operation)
            if operation != 'UNPOS':
                return capture_geometry_value(value, operation, line)
            return value
        except RobotFactsUnavailable as error:
            self.unresolved_at('geometry', str(error), node)
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('geometry', str(error), node)
            flow.stopped = True
        return _Value(spec=['XYZWPREXT'] if joint else value.spec)

    def pose_constructor_call(self, node, flow, conditional):
        name = node['value']
        schema = node.get('geometry_result_type') or constructor_schema(name, len(node['args']))
        result = _Value(spec=['BOOLEAN'] if name == '>=<' else schema)
        inputs = []
        for index, operand in enumerate(node['args']):
            value = self.expr(operand, flow, conditional)
            if flow.stopped and not flow.opaque:
                return result
            if (name in GEOMETRY_FUNCTIONS or name in (':', '>=<')) and not (name == 'MIRROR' and index == 2):
                value = self.geometry_operand_facts(name, value, operand, flow)
                if flow.stopped and not flow.opaque:
                    return result
            inputs.append(value)
        try:
            line = node.get('line')
            if name == '>=<':
                self.context('pose_tolerance', None)
                if any(value.spec == ['XYZWPREXT'] for value in inputs):
                    self.context('external_tolerance', None)
                return compare_pose_facts(inputs, getattr(self.saved_bindings, 'pose_tolerance', None),
                                          getattr(self.saved_bindings, 'external_tolerance', None), line)
            return construct_pose(name, inputs, line) or result
        except RobotFactsUnavailable as error:
            self.unresolved_at('geometry', str(error), node)
            return result
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('geometry', str(error), node)
            flow.stopped = True
            return result

    def unpos_call(self, node, flow, conditional):
        source, *outputs = node['args']
        value = self.expr(source, flow, conditional)
        if flow.stopped and not flow.opaque:
            return _Value()
        value = self.geometry_operand_facts('UNPOS', value, source, flow)
        if flow.stopped and not flow.opaque:
            return _Value()
        line = node.get('line')
        try:
            captured = capture_unpos_value(value, line, with_axes=len(outputs) == 10)
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('geometry', str(error), source)
            flow.stopped = True
            return _Value()
        operands = self.service_operands(dict(node, args=outputs), 0, flow, conditional)
        if operands is None or not self.checked_robot_service_outputs(operands[1], node, flow):
            return _Value()
        locations = operands[1]
        try:
            values = (unpos_output_facts(captured, [loc.spec for loc in locations], line) if captured is not None
                      else [_Value(spec=loc.spec) for loc in locations])
        except (rt.KarelRuntimeError, ValueError, ArithmeticError) as error:
            self.unresolved_at('geometry', str(error), node)
            flow.stopped = True
            return _Value()
        for loc, output in zip(locations, values):
            self.write(loc, output, flow, node)
        return _Value()

    def call(self, node, flow, conditional, *, statement_call=False, argument_path_edits=False):
        name=node['value'];args=node['args']
        if name in self.plan['routines']:
            return self.routine(name, args, node, flow, conditional, statement_call=statement_call,
                                argument_path_edits=argument_path_edits)
        if name in ('PATH_LEN', 'NODE_SIZE'):
            return self.path_metadata_call(node, flow, conditional)
        if name in ('APPEND_NODE', 'INSERT_NODE', 'DELETE_NODE'):
            return self.path_edit(node, flow, conditional)
        if name == 'COPY_PATH':
            return self.path_copy(node, flow, conditional)
        if name in ('GET_VAR', 'SET_VAR'):
            return self.variable_call(node, flow, conditional)
        if name == 'CREATE_VAR':
            return self.create_variable(node, flow, conditional)
        if name in ('RENAME_VAR', 'RENAME_VARS'):
            return self.rename_variable(node, flow, conditional)
        if name in ('VAR_INFO', 'VAR_LIST', 'PROG_LIST', 'LOAD_STATUS', 'GET_ATTR_PRG', 'SET_ATTR_PRG'):
            return self.inspection_call(node, flow, conditional)
        if name in REGISTER_SERVICES or name in INDIRECT_PORT_SERVICES:
            return self.bank_call(node, flow, conditional)
        if name in POSITION_SERVICES:
            return self.position_register_call(node, flow, conditional)
        if name in TEACH_SCALAR_GETTERS or name in TEACH_SCALAR_SETTERS:
            return self.teach_scalar_call(node, flow, conditional)
        if name in TEACH_CATALOG_SERVICES:
            return self.teach_catalog_call(node, flow, conditional)
        if name in TEACH_EDIT_SERVICES:
            return self.teach_edit_call(node, flow, conditional)
        if name in TEACH_HANDLE_SERVICES:
            return self.teach_handle_call(node, flow, conditional)
        if name in TEACH_POSITION_SERVICES:
            return self.teach_position_call(node, flow, conditional)
        if name == 'AVL_POS_NUM':
            return self.teach_available_position(node, flow, conditional)
        if name in ROBOT_SNAPSHOTS:
            return self.robot_snapshot_call(node, flow, conditional)
        if name in ROBOT_RANGE_QUERIES:
            return self.robot_range_call(node, flow, conditional)
        if name in ROBOT_CONVERSIONS:
            return self.robot_coordinate_call(node, flow, conditional)
        if name in CONFIG_TEXT_CONVERSIONS:
            return self.config_text_call(node, flow, conditional)
        if name in POSE_CONSTRUCTORS:
            return self.pose_constructor_call(node, flow, conditional)
        if name == 'UNPOS':
            return self.unpos_call(node, flow, conditional)
        if name in ('UNINIT', 'ARRAY_LEN'):
            return self.data_metadata_call(node, flow, conditional)
        if name in SCALAR_PURE:return self.scalar_call(node,flow,conditional)
        if name in PURE:
            for item in args:self.expr(item,flow,conditional)
            return _Value()
        signature=node.get('signature')
        if name=='CNV_STR_INT':signature=[['i','STRING'],['o','INTEGER']]
        values=[];outputs=[]
        with self.capture_operands() as pending:
            for index,item in enumerate(args):
                mode=signature[index][0] if signature and index<len(signature) else 'i'
                if mode in ('o','m','r'):
                    loc=self.locate(item,flow,conditional)
                    pending.append(loc)
                    outputs.append((index,loc))
                    if mode=='r':
                        values.append(self.read(loc,item,flow,conditional) if loc else self.expr(item,flow,conditional))
                    else:
                        values.append(_Value())
                else:
                    values.append(self.expr(item,flow,conditional))
        known=[value.constant for value in values]
        if self.linked_plans is not None and name in ('RUN_TASK', 'CONT_TASK'):
            status = outputs[-1][1] if outputs else None
            parked = self.task_request(name, known, node, flow, status=status)
            for _, loc in outputs:
                self.write(loc, _Value(), flow, node, definite=parked)
            return _Value()
        self.unresolved_at('service','Service or external input effects require explicit review: '+name,node)
        self.opaque(flow)
        for _,loc in outputs:
            self.write(loc,_Value(),flow,node,definite=False)
        return _Value(complete=not signature)

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

    def task_handoff_slot(self, node):
        name = node['value']
        frame = self.frames[-1] if self.frames else None
        if frame is not None and name in frame['slots']:
            loc = frame['slots'][name]
            if loc.kind not in ('variable', 'local') or loc.parts or loc.path_slot is not None:
                return None
            if loc.kind == 'variable' and loc.owner not in (self.program, self.task_roots[-1]):
                return None
        else:
            if name in self.imports.get(self.program, {}):
                return None
            loc = self.global_slot(name, node)
        return loc if loc is not None and loc.spec[0] in SCALARS else None

    def task_handoff_value(self, node, flow, assigned):
        kind, value = node['kind'], node['value']
        if kind == 'literal':
            return True, value
        if kind == 'real_literal':
            try:
                return True, float(value)
            except ValueError:
                return False, UNKNOWN
        if kind == 'predefined':
            return value in PREDEFINED_CONSTANTS, PREDEFINED_CONSTANTS.get(value, UNKNOWN)
        loc = self.task_handoff_slot(node)
        if loc is not None:
            previous = flow.constants.get(loc.key, UNKNOWN) if loc.key in flow.defined else UNKNOWN
            return True, assigned.get(loc.key, previous)
        if value in self.plan['types'] or self.frames and value in self.frames[-1]['slots']:
            return False, UNKNOWN
        value = self.constant(value)
        return value is not UNKNOWN, value

    def task_handoff_number(self, handoff, flow, status):
        # The task request captures its inputs before it writes the status.
        assigned = {status.key: UNKNOWN} if status is not None else {}
        for target, source in handoff.assignments:
            self.tick()
            output = self.task_handoff_slot(target)
            safe, value = self.task_handoff_value(source, flow, assigned)
            if output is None or not safe:
                return UNKNOWN
            if value is not UNKNOWN:
                try:
                    with rt._numeric_scope('pythonic'):
                        value = rt.checked(tuple_spec(output.spec), value)
                except rt.KarelRuntimeError:
                    return UNKNOWN
            assigned[output.key] = UNKNOWN if value is rt.UNINITIALIZED else value
        safe, number = self.task_handoff_value(handoff.selector, flow, assigned)
        return number if safe else UNKNOWN

    def matching_task_handoff(self, node, name, flow, status):
        handoff = self.task_handoff
        if (handoff is None or handoff.request is not node or not self.teach_stable(flow) or flow.handlers
                or node['kind'] == 'call' and (status is None or status.path_slot is not None
                                               or status.kind not in ('variable', 'local', 'created-variable'))):
            return None
        if handoff.waiter is None:
            return handoff
        number = self.task_handoff_number(handoff, flow, status)
        if type(number) is int and 1 <= number <= len(self.task_numbers) and self.task_numbers[number - 1] == name:
            return handoff
        return None

    def task_request(self, operation, values, node, flow, *, status=None):
        plan = self.task_target(operation, values[0], node)
        if plan is None:
            self.opaque(flow)
            return False
        name = plan['program']
        handoff = self.matching_task_handoff(node, name, flow, status)
        if operation != 'RUN_TASK':
            return self.continue_task(operation, plan, node, flow, handoff=handoff)

        hint, pause, motion, mask = values[1:5]
        checked_request = (self.track_tasks and not flow.task_order_unknown and type(hint) is int and hint >= 0
                           and type(pause) is bool and motion is False and type(mask) is int and mask == 0)
        fresh = checked_request and name not in flow.requested_tasks
        flow.requested_tasks.add(name)
        if fresh and pause and plan.get('entry_checkpoint') is True:
            flow.paused_tasks[name] = None
            if handoff is not None and handoff.waiter is not None:
                handoff.reached = True
            self.unresolved_at('task-scheduling', 'Paused entry for '+name+' depends on scheduler admission', node)
            return True
        if name in flow.paused_tasks:
            return self.continue_task(operation, plan, node, flow, segment=checked_request, handoff=handoff)

        self.unresolved_at('task-scheduling', 'RUN_TASK timing, admission and shared effects require review: '+name, node)
        return self.start_task_body(plan, flow, segment=fresh and pause is False, handoff=handoff)

    def continue_task(self, operation, plan, node, flow, *, segment=True, handoff=None):
        name = plan['program']
        if name not in flow.paused_tasks or flow.task_order_unknown:
            self.unresolved_at('task-continuation', operation+' depends on a live suspended frame: '+name, node)
            self.opaque(flow)
            return False

        suspension = flow.paused_tasks.pop(name)
        point = 'a paused entry' if suspension is None else 'an explicit in-body pause'
        self.unresolved_at('task-continuation', operation+' may resume '+point+' after scheduler admission: '+name, node)
        return self.start_task_body(plan, flow, suspension, segment=segment, handoff=handoff)

    def bounded_task_segment(self, plan, segment=None):
        key = plan['program'], segment
        if key not in self.segmentable:
            self.segmentable[key] = bounded_child(
                plan, self.linked_plans, self.tick, segment=segment,
                predefined_files=getattr(self.saved_bindings, 'predefined_files', ()))
        return self.segmentable[key]

    def terminal_task_handoff(self, flow):
        # Entry cleanup may run before or during this last child slice.
        owners = flow.teach.handle_owners()
        return None not in owners and self.task_roots[-1] not in owners

    def synchronized_task_segment(self, plan, suspension, handoff, flow):
        if suspension is not None and len(suspension.blocks) != 1:
            return None
        start = suspension.blocks[0][1] if suspension is not None else 0
        end = len(plan['body'])
        for index in range(start, end):
            self.tick()
            if explicit_pause(plan['body'][index]):
                return (start, index + 1) if handoff.waiter is not None else None
        return (start, end) if handoff.waiter is None and self.terminal_task_handoff(flow) else None

    def start_task_body(self, plan, flow, suspension=None, *, segment, handoff):
        name = plan['program']
        synchronized = False
        rules = None
        nested = suspension is not None and len(suspension.blocks) > 1
        if segment and handoff is not None:
            target = self.synchronized_task_segment(plan, suspension, handoff, flow)
            synchronized = target is not None and self.bounded_task_segment(plan, target) is not None
            if not synchronized and (handoff.waiter is not None
                                     or suspension is not None and self.terminal_task_handoff(flow)):
                rules = structured_child(
                    plan, self.linked_plans, self.tick, predefined_files=getattr(self.saved_bindings, 'predefined_files', ()))
                synchronized = rules is not None
        if synchronized or segment and not nested and self.bounded_task_segment(plan) == 'scalar':
            caller = flow if synchronized else None
            cursor, child = self.scheduled_body(plan, segment=True, suspension=suspension, shared=caller, rules=rules)
            if synchronized:
                expected_pause = handoff.waiter is not None
                if (child.opaque or child.task_order_unknown
                        or rules is not None and (cursor is not None) != expected_pause):
                    raise _TaskOrderUnknown()
                flow.teach = child.teach
                flow.program_attributes = child.program_attributes
                flow.task_file_outputs = child.task_file_outputs
                if cursor is None:
                    self.tick(len(flow.teach.handles or ()))
                    flow.teach.release_owner(name)
                    flow.stopped = child.stopped
                else:
                    handoff.reached = True
            if cursor is not None:
                flow.paused_tasks[name] = cursor
            return True
        if suspension is not None:
            # Revisit previous slices as well when the original cursor no
            # longer establishes which portion may run.
            raise _TaskOrderUnknown()
        self.opaque(flow)
        self.scheduled_body(plan, path_orders=flow.path_orders)
        return False

    def scheduled_body(self, plan, *, segment=False, suspension=None, path_orders=None, shared=None, rules=None):
        depth = self.suspended_depth + len(self.frames) + 1
        caller_plan, caller_roots, caller_depth = self.plan, self.task_roots, self.suspended_depth
        caller_frames, caller_exits, caller_values = self.frames, self.exits, self.capture_values
        caller_checked_segment = self.checked_child_segment
        self.checked_child_segment = rules is not None
        self.plan, self.task_roots, self.suspended_depth = plan, (*caller_roots, plan['program']), depth
        self.frames, self.exits, self.capture_values = [], [], {}
        try:
            if not segment:
                self.block(plan['body'], _Flow(task_order_unknown=True, path_orders=dict.fromkeys(path_orders or ())), True)
                return None, None
            child = suspension.flow.copy() if suspension is not None else _Flow()
            if shared is not None:
                child.teach = shared.teach.copy()
                child.program_attributes = shared.program_attributes.copy()
                child.requested_tasks = shared.requested_tasks.copy()
                child.task_file_outputs = shared.task_file_outputs
            blocks = list(suspension.blocks) if suspension is not None else [(plan['body'], 0)]
            self.frames = [block.frame for block in blocks if isinstance(block, _TaskRoutine)]
            self.plan = self.task_frame_plan()
            cursor = self.scheduled_segment(blocks, child, rules)
            return cursor, child
        finally:
            self.plan, self.task_roots, self.suspended_depth = caller_plan, caller_roots, caller_depth
            self.frames, self.exits, self.capture_values = caller_frames, caller_exits, caller_values
            self.checked_child_segment = caller_checked_segment

    def task_frame_plan(self):
        owner = self.frames[-1]['key'][0] if self.frames else self.task_roots[-1]
        return self.linked_plans[owner]

    def scheduled_segment(self, blocks, child, rules):
        while blocks and not (child.stopped and not child.opaque):
            frame = blocks[-1]
            if isinstance(frame, _TaskRoutine):
                self.finish_task_routine(blocks, child)
                continue
            scope = rules.routine_scope(self.plan, self.frames[-1]['name']) if rules and self.frames else rules
            if isinstance(frame, _TaskWrite):
                self.next_task_write_item(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskRead):
                self.next_task_read_item(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskFile):
                self.next_task_file(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskCollectionWrite):
                self.next_task_collection_write(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskSelection):
                self.next_task_selection(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskResultSelection):
                self.next_task_result_selection(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskArrayLength):
                self.next_task_array_length(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskArguments):
                self.next_task_argument(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskQueueCall):
                self.next_task_queue_call(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskExpression):
                self.next_task_expression(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskSelect):
                self.next_task_case(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskRepeatCapture):
                self.next_task_repeat_capture(blocks, child, scope, frame)
                continue
            if isinstance(frame, _TaskForHeader):
                self.tick()
                value = self.task_operand(frame.operand, child, scope, blocks, frame)
                if value is not None:
                    self.capture_task_for_bound(blocks, child, frame, value)
                continue
            if isinstance(frame, _TaskLoop):
                self.next_task_iteration(blocks, child, scope, frame)
                continue
            body, index = frame
            if index == len(body):
                blocks.pop()
                continue
            blocks[-1] = (body, index + 1)
            node = body[index]
            if explicit_pause(node):
                self.tick()
                return _Suspension(tuple(blocks), child.copy())
            if scope is None or scope.statement(node):
                self.statement(node, child, True)
                continue
            self.start_task_statement(blocks, child, scope, node)
        return None

    def start_task_statement(self, blocks, flow, scope, node):
        self.tick()
        kind, args = node['kind'], node['args']
        if kind == 'call':
            builtin = args[0]
            if builtin['kind'] == 'call' and scope.path_edit_call(builtin):
                self.path_edit(builtin, flow, True, task_segment=True)
                if flow.opaque or flow.stopped:
                    raise _TaskOrderUnknown()
                return
            if queue_task_call(self.plan, builtin):
                blocks.append(_TaskQueueCall(builtin))
                return
            if file_task_procedure(self.plan, builtin):
                self.start_task_file(blocks, flow, scope, builtin)
                return
            call = scope.procedure_call(builtin)
            if call is None:
                raise _TaskOrderUnknown()
            blocks.append(_TaskArguments(call, None))
            return
        if kind == 'write_items':
            self.start_task_write(blocks, flow, node)
            return
        if kind == 'read':
            alias = self.plan.get('default_write_file')
            if alias == 'OUTPUT':
                alias = 'INPUT'
            if alias is None:
                raise _TaskOrderUnknown()
            flow.task_file_outputs = self.capture_task_file(flow, alias, node)
            blocks.append(_TaskRead(node, alias))
            return
        if kind in ('file_open', 'file_read', 'file_write', 'file_close') and args[0] is not None:
            self.start_task_file(blocks, flow, scope, node)
            return
        if kind in STRUCTURED_LOOPS and scope.loop(node):
            if kind == 'for':
                self.start_task_selection(blocks, flow, args[0], node)
            else:
                blocks.append(_TaskLoop(node))
            return
        consumer = node
        spec = None
        if kind == 'assign':
            spec = scope.reference_schema(args[0], staged=True)
            if (not spec or spec[0] not in TASK_ROUTINE_VALUES
                    or spec[0] in TASK_DATA_AGGREGATES and node.get('data_assignment') is not True):
                raise _TaskOrderUnknown()
            consumer = _TaskAssignment(node, spec)
            operand = args[1]
        elif kind in ('if', 'select'):
            operand = args[0]
        elif kind == 'return' and self.frames:
            operand = args[0]
            if operand is None:
                self.return_from_task_routine(blocks, flow, node, None)
                return
            spec = self.frames[-1]['result']
        else:
            raise _TaskOrderUnknown()
        if spec and spec[0] in TASK_DATA_AGGREGATES:
            if node.get('geometry_return') and not node.get('data_return'):
                raise _TaskOrderUnknown()
            value = self.task_data_operand(operand, flow, scope, blocks, consumer)
        else:
            value = self.task_operand(operand, flow, scope, blocks, consumer)
        if value is not None:
            self.consume_task_value(blocks, flow, consumer, value)

    def capture_task_file(self, flow, alias, node):
        self.context('predefined_files', alias)
        bindings = getattr(self.saved_bindings, 'predefined_files', ())
        outputs = flow.task_file_outputs
        if outputs is None or alias not in bindings:
            raise _TaskOrderUnknown()
        self.tick(len(outputs.handles) + len(outputs.sizes))
        try:
            captured = outputs.capture(alias, self.saved_bindings.memory_files, bindings[alias], node.get('line'))
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None
        if captured is None:
            raise _TaskOrderUnknown()
        return captured

    def start_task_file(self, blocks, flow, scope, node, consumer=None):
        selector = node['args'][0]
        while selector['kind'] == 'group':
            selector = selector['args'][0]
        alias = scope.predefined_file_alias(selector)
        file = _TaskFile(node, consumer)
        if alias is not None:
            if node['kind'] == 'file_open':
                raise _TaskOrderUnknown()
            flow.task_file_outputs = self.capture_task_file(flow, alias, node)
            blocks.append(replace(file, key=alias))
            return
        if scope.reference_schema(selector, staged=True) != ['FILE']:
            raise _TaskOrderUnknown()
        blocks.append(file)
        self.start_task_selection(blocks, flow, selector, file)

    def next_task_file(self, blocks, flow, scope, pending):
        self.tick()
        node, key = pending.node, pending.key
        kind, args = node['kind'], node['args']
        if kind == 'file_write':
            blocks[-1] = _TaskWrite(args[1], file_key=key)
            return
        if kind == 'file_read':
            blocks[-1] = _TaskRead(args[1], file_key=key)
            return
        service = kind == 'call' and pending.consumer is None
        index = len(pending.values) + 1
        if (kind == 'file_open' or service) and index < len(args):
            operand = args[index]
            if service and node['signature'][index][0] == 'o':
                self.start_task_selection(blocks, flow, operand, pending)
            else:
                value = self.task_operand(operand, flow, scope, blocks, pending)
                if value is not None:
                    self.consume_task_value(blocks, flow, pending, value)
            return
        outputs = flow.task_file_outputs
        if outputs is None:
            raise _TaskOrderUnknown()
        blocks.pop()
        if service:
            self.apply_task_file_procedure(flow, pending, outputs)
            return
        if kind == 'call':
            if node['value'] == 'UNINIT':
                result = _Value(outputs.descriptor(key).closed, spec=['BOOLEAN'])
            else:
                value = outputs.query(key, node['value'])
                if value is None:
                    raise _TaskOrderUnknown()
                result = _Value(value, spec=['INTEGER'])
            self.consume_task_value(blocks, flow, pending.consumer, result)
            return

        self.tick(len(outputs.handles) + len(outputs.sizes))
        if kind == 'file_open':
            mode, name = pending.values
            backend = getattr(self.saved_bindings, 'memory_files', None)
            try:
                outputs = outputs.open(key, backend, name, mode, node.get('line'))
            except rt.KarelRuntimeError:
                raise _TaskOrderUnknown() from None
        else:
            outputs = outputs.close(key)
        if outputs is None:
            raise _TaskOrderUnknown()
        flow.task_file_outputs = outputs

    def apply_task_file_procedure(self, flow, pending, outputs):
        node, key, values = pending.node, pending.key, pending.values
        name, line = node['value'], node.get('line')
        if name == 'CLR_IO_STAT':
            # Checked memory operations leave IO_STATUS at zero.
            return
        if name == 'BYTES_AHEAD':
            available, status = values
            count = outputs.query(key, 'BYTES_LEFT')
            if available.key == status.key or count is None:
                raise _TaskOrderUnknown()
            self.write(available, _Value(count, spec=['INTEGER']), flow, node)
            self.write(status, _Value(0, spec=['INTEGER']), flow, node)
            return

        self.tick(len(outputs.handles))
        try:
            if name == 'SET_FILE_ATR':
                attribute, *argument = values
                value = rt.integer(argument[0], line) if argument else 0
                updated = outputs.set_attribute(key, rt.integer(attribute, line), value, line)
                if updated is None:
                    raise _TaskOrderUnknown()
                flow.task_file_outputs = updated
            else:
                position, status = values
                result = outputs.seek(key, rt.integer(position, line))
                if result is None:
                    raise _TaskOrderUnknown()
                flow.task_file_outputs, code = result
                self.write(status, _Value(code, spec=['INTEGER']), flow, node)
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None

    def start_task_write(self, blocks, flow, node):
        alias = self.plan.get('default_write_file')
        bindings = getattr(self.saved_bindings, 'predefined_files', None)
        if alias is None or bindings is None:
            raise _TaskOrderUnknown()
        if alias in bindings:
            flow.task_file_outputs = self.capture_task_file(flow, alias, node)
        else:
            alias = None
        blocks.append(_TaskWrite(node, file_key=alias))

    def next_task_read_item(self, blocks, flow, scope, read):
        self.tick()
        items = read.node['args']
        if read.index == len(items):
            self.finish_task_read(read, flow)
            blocks.pop()
            return
        item = items[read.index]
        if item['kind'] == 'read_cr':
            blocks[-1] = replace(read, index=read.index + 1, line_breaks=(*read.line_breaks, len(read.fields)))
            return
        target, formats = (item['args'][0], item['args'][1:]) if item['kind'] == 'read_item' else (item, ())
        if not read.leaves:
            self.start_task_selection(blocks, flow, target, read)
            return
        if len(read.formats) < len(formats):
            value = self.task_operand(formats[len(read.formats)], flow, scope, blocks, read)
            if value is not None:
                self.consume_task_value(blocks, flow, read, value)
            return
        line = read.node.get('line')
        try:
            fields = tuple((loc, rt.read_formats(tuple_spec(loc.spec), read.formats, line)) for loc in read.leaves)
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None
        blocks[-1] = replace(read, index=read.index + 1, leaves=(), formats=(), fields=(*read.fields, *fields))

    def plain_task_read_storage(self, spec):
        kind = spec[0]
        if kind == 'ARRAY':
            return self.plain_task_read_storage(spec[2])
        if kind == 'STRUCTURE':
            return all(self.plain_task_read_storage(field) for _, field in spec[2])
        return kind in SCALARS

    def finish_task_read(self, read, flow):
        outputs = flow.task_file_outputs
        if outputs is None:
            raise _TaskOrderUnknown()
        backend = getattr(self.saved_bindings, 'memory_files', None)
        specs = [tuple_spec(loc.spec) for loc, _ in read.fields]
        formats = [controls for _, controls in read.fields]
        try:
            with rt._numeric_scope('pythonic'):
                prepared = outputs.read_saved(read.file_key, backend, specs, formats, read.line_breaks,
                                              read.node.get('line'), tick=self.tick)
        except (rt.KarelRuntimeError, UnicodeError):
            raise _TaskOrderUnknown() from None
        if prepared is None:
            raise _TaskOrderUnknown()
        flow.task_file_outputs, missing = prepared
        self.context('files', outputs.descriptor(read.file_key).name)
        # Keep saved FILE values editable. Only initialization and cursor facts
        # participate after the complete batch has been validated.
        for (loc, _), uninitialized in zip(read.fields, missing):
            self.write(loc, _Value(spec=loc.spec, complete=not uninitialized, uninitialized=uninitialized), flow, read.node)

    def next_task_write_item(self, blocks, flow, scope, write):
        self.tick()
        outputs, output = flow.task_file_outputs, None
        if write.file_key is not None:
            if outputs is None:
                raise _TaskOrderUnknown()
            output = outputs.descriptor(write.file_key)
        items = write.node['args']
        if write.index == len(items):
            if not 1 <= write.rendered_pieces <= 1024:
                raise _TaskOrderUnknown()
            if output is not None:
                self.tick(len(outputs.handles) + len(outputs.sizes))
                backend = getattr(self.saved_bindings, 'memory_files', None)
                try:
                    updated = outputs.write(write.file_key, backend, write.rendered_length, write.node.get('line'))
                except rt.KarelRuntimeError:
                    raise _TaskOrderUnknown() from None
                if updated is None:
                    raise _TaskOrderUnknown()
                flow.task_file_outputs = updated
            elif write.rendered_length > 254:
                raise _TaskOrderUnknown()
            blocks.pop()
            return

        item = items[write.index]
        if item['kind'] == 'write_cr':
            count = length = 1
        else:
            kind = item.get('write_type')
            collection = item.get('write_collection')
            aggregate = kind in TASK_DATA_AGGREGATES or collection is not None
            if not aggregate and kind not in ('INTEGER', 'REAL', 'BYTE', 'SHORT', 'BOOLEAN', 'STRING'):
                raise _TaskOrderUnknown()
            operands = item['args']
            if aggregate and write.aggregate is None:
                if collection is not None:
                    self.start_task_collection_write(blocks, flow, scope, operands[0], collection)
                else:
                    value = self.task_data_operand(operands[0], flow, scope, blocks, write)
                    if value is not None:
                        self.consume_task_value(blocks, flow, write, value)
                return
            index = len(write.values) + int(aggregate)
            if index < len(operands):
                value = self.task_operand(operands[index], flow, scope, blocks, write)
                if value is not None:
                    self.consume_task_value(blocks, flow, write, value)
                return

            count, length = self.render_task_write_item(item, write, output)
        # Runtime checks the expanded batch only after rendering every item.
        blocks[-1] = replace(write, index=write.index + 1, values=(), aggregate=None,
                             rendered_pieces=write.rendered_pieces + count, rendered_length=write.rendered_length + length)

    def next_task_queue_call(self, blocks, flow, scope, pending):
        self.tick()
        call, actuals = pending.call, pending.actuals
        index = len(actuals)
        if index == len(call['args']):
            blocks.pop()
            self.apply_task_queue_call(call, actuals, flow)
            return
        operand = call['args'][index]
        if call['signature'][index][0] == 'i':
            value = self.task_operand(operand, flow, scope, blocks, pending)
            if value is not None:
                self.consume_task_value(blocks, flow, pending, value)
        else:
            schema = scope.reference_schema(operand, staged=True)
            if not schema or schema[0] not in ('QUEUE_TYPE', 'ARRAY', 'INTEGER'):
                raise _TaskOrderUnknown()
            self.start_task_selection(blocks, flow, operand, pending)

    def task_queue_array_capacity(self, loc):
        shape, member = _array_dimensions(loc.spec)
        if len(shape) != 1 or type(shape[0]) is not int or not 1 <= shape[0] <= MAX_FACTS or member != ['INTEGER']:
            raise _TaskOrderUnknown()
        return shape[0]

    def write_task_queue_array(self, loc, values, flow, node):
        self.tick(len(values))
        for index, value in enumerate(values, 1):
            cell = self.child(loc, 'index', index, node)
            self.write(cell, _Value(value, spec=cell.spec), flow, node)

    def apply_task_queue_call(self, node, actuals, flow):
        name = node['value']
        offset = QUEUE_EDIT_INPUTS.get(name, 0)
        queue = actuals[offset]
        if flow.opaque or flow.stopped or queue.spec != ['QUEUE_TYPE']:
            raise _TaskOrderUnknown()
        if name == 'INIT_QUEUE':
            flow.task_queues[queue.key] = _TaskQueue()
            return

        locations = [loc for loc in actuals if isinstance(loc, _Location)]
        if any(self.path_contains_reference(first, second) or self.path_contains_reference(second, first)
               for index, first in enumerate(locations) for second in locations[index + 1:]):
            raise _TaskOrderUnknown()
        buffer = actuals[offset + 1]
        capacity = self.task_queue_array_capacity(buffer)
        previous = flow.task_queues.get(queue.key)
        if previous is None or previous.buffer not in (None, buffer.key) or len(previous.entries) > capacity:
            raise _TaskOrderUnknown()

        entries, sequence = previous.entries, previous.sequence
        line = node.get('line')
        try:
            with rt._numeric_scope('pythonic'):
                if name == 'COPY_QUEUE':
                    entry_id, skip = (rt.integer(value.constant, line) for value in actuals[2:4])
                    if entry_id < 0 or skip < 0:
                        raise _TaskOrderUnknown()
                    target, *outputs = actuals[4:]
                    copied, status = plan_queue_copy(entries, entry_id, skip, self.task_queue_array_capacity(target))
                    writes = [(0, len(copied)), (1, status)]
                else:
                    inputs = [rt.integer(value.constant, line) for value in actuals[:offset]]
                    outputs = actuals[offset + 2:]
                    entries, sequence, writes = plan_queue_edit(name, entries, sequence, capacity, inputs, line)
                if any(loc.spec != ['INTEGER'] for loc in outputs):
                    raise _TaskOrderUnknown()
                self.tick(len(entries))
                values = [rt.checked(('INTEGER',), value, line) for _, value in entries]
                prepared = [(outputs[index], rt.checked(('INTEGER',), value, line)) for index, value in writes]
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None

        self.write_task_queue_array(buffer, values + [0] * (capacity - len(values)), flow, node)
        if name == 'COPY_QUEUE':
            self.write_task_queue_array(target, copied, flow, node)
        for loc, value in prepared:
            self.write(loc, _Value(value, spec=loc.spec), flow, node)
        flow.task_queues[queue.key] = _TaskQueue(entries, sequence, buffer.key)

    def start_task_collection_write(self, blocks, flow, scope, operand, schema):
        while operand['kind'] == 'group':
            operand = operand['args'][0]
        receiver, bounds = operand, ()
        if operand['kind'] == 'path_io_range':
            receiver, *bounds = operand['args']
        elif schema[0] == 'PATH' and operand['kind'] == 'index':
            root, *indices = operand['args']
            shape, terminal = _array_dimensions(scope.reference_schema(root, staged=True))
            if terminal and terminal[0] == 'PATH' and terminal[2] is not None and len(indices) == len(shape) + 1:
                # A single dynamic PATH index may select the header. The emitter
                # captures the PATH receiver before evaluating that final index.
                bounds = (indices[-1],)
                receiver = dict(operand, args=[root, *indices[:-1]]) if shape else root
        pending = _TaskCollectionWrite(operand, schema, tuple(bounds))
        blocks.append(pending)
        self.start_task_selection(blocks, flow, receiver, pending)

    def next_task_collection_write(self, blocks, flow, scope, pending):
        self.tick()
        if len(pending.values) < len(pending.bounds):
            operand = pending.bounds[len(pending.values)]
            value = self.task_operand(operand, flow, scope, blocks, pending)
            if value is not None:
                self.consume_task_value(blocks, flow, pending, value)
            return

        spec = tuple_spec(pending.schema)
        operand, location = pending.operand, pending.location
        fields = []
        try:
            with rt._numeric_scope('pythonic'):
                if rt.queue_io_type(spec):
                    self.collect_task_queue_fields(location, operand, flow, fields)
                else:
                    records = self.task_collection_path_records(pending, flow)
                    for loc in records:
                        if loc is None or self.variable_path_storage(loc, flow, False) is not True:
                            raise _TaskOrderUnknown()
                        self.retain_selected_path_storage(loc, flow, False)
                        schema = self.task_data_schema(loc.spec, max_leaves=1024 - len(fields))
                        raw = materialized_value(self.read(loc, operand, flow, True))
                        if raw is UNKNOWN:
                            raise _TaskOrderUnknown()
                        fields.extend(rt.capture_aggregate_write(schema, raw, operand.get('line')).fields)
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None
        if flow.opaque or flow.stopped:
            raise _TaskOrderUnknown()
        blocks.pop()
        blocks[-1] = replace(blocks[-1], aggregate=rt._AggregateWriteValue(spec, fields))

    def task_collection_path_records(self, pending, flow):
        location, node = pending.location, pending.operand
        if not pending.bounds:
            records = self.path_transfer_records(location, node, flow, False)
            if records is None:
                raise _TaskOrderUnknown()
            return records
        if (pending.generation != self.path_descriptor_generation(location, flow)
                or any(type(value) is not int for value in pending.values)):
            raise _TaskOrderUnknown()
        first, *tail = pending.values
        last = tail[0] if tail else None
        count = self.known_path_count(location, flow, False)
        indexes = self.path_range_indexes(location.spec, count, first, last, node)
        if indexes is None:
            raise _TaskOrderUnknown()
        return [self.index_child(location, index, node, flow) for index in indexes]

    def collect_task_queue_fields(self, loc, node, flow, fields):
        self.tick()
        if loc is None:
            raise _TaskOrderUnknown()
        if loc.spec[0] == 'ARRAY':
            size = loc.spec[1][0] if type(loc.spec[1]) is list else loc.spec[1]
            if type(size) is not int or not 1 <= size <= MAX_FACTS:
                raise _TaskOrderUnknown()
            for index in range(1, size + 1):
                self.collect_task_queue_fields(self.child(loc, 'index', index, node), node, flow, fields)
        else:
            queue = flow.task_queues.get(loc.key) if loc.spec == ['QUEUE_TYPE'] else None
            if queue is None or len(fields) + len(queue.entries) > 1024:
                raise _TaskOrderUnknown()
            self.tick(len(queue.entries))
            fields.extend((('INTEGER',), value) for _, value in queue.entries)

    def task_data_schema(self, schema, *, max_leaves=MAX_FACTS):
        if not schema or schema[0] not in TASK_DATA_AGGREGATES:
            raise _TaskOrderUnknown()
        spec = tuple_spec(schema)
        try:
            if rt._validate_data_schema(spec) > max_leaves:
                raise _TaskOrderUnknown()
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None
        return spec

    def capture_task_write_aggregate(self, blocks, write, value):
        item = write.node['args'][write.index]
        spec = self.task_data_schema(value.spec, max_leaves=1024)
        if spec[0] != item['write_type']:
            raise _TaskOrderUnknown()
        try:
            with rt._numeric_scope('pythonic'):
                raw = materialized_value(value)
                if raw is UNKNOWN:
                    raise _TaskOrderUnknown()
                captured = rt.capture_aggregate_write(spec, raw, item.get('line'))
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None
        blocks[-1] = replace(write, aggregate=captured)

    def render_task_write_item(self, item, write, output):
        if any(value.constant is UNKNOWN or value.uninitialized for value in write.values):
            raise _TaskOrderUnknown()
        values = [slot.constant for slot in write.values]
        line = item.get('line')
        try:
            with rt._numeric_scope('pythonic'):
                if write.aggregate is not None:
                    pieces = rt.format_aggregate_write(write.aggregate, values, line, file=output)
                    return len(pieces), sum(map(len, pieces))
                value, *formats = values
                kind = item['write_type']
                piece = rt.optional_file_piece(output, kind, value, formats, line)
                return 1, len(piece)
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None

    def start_task_branch(self, blocks, flow, node, value):
        selected = value.constant
        if flow.stopped or flow.opaque or selected is UNKNOWN:
            raise _TaskOrderUnknown()
        if node['kind'] == 'if':
            if type(selected) is not bool:
                raise _TaskOrderUnknown()
            blocks.append((node['body'] if selected else node['alternate'], 0))
            return
        category = {bool: 'BOOLEAN', str: 'STRING'}.get(type(selected), 'NUMERIC')
        selected = self.checked_select_value(selected, category, node)
        blocks.append(_TaskSelect(node, selected, category, tuple(select_case_labels(node))))

    def next_task_case(self, blocks, flow, scope, selection):
        self.tick()
        if selection.index == len(selection.labels):
            node = selection.node
            blocks.pop()
            if selection.match is not None:
                blocks.append((node['args'][1][selection.match][2], 0))
            elif node['has_else']:
                blocks.append((node['alternate'], 0))
            else:
                raise _TaskOrderUnknown()
            return
        _, label = selection.labels[selection.index]
        value = self.task_operand(label, flow, scope, blocks, selection)
        if value is not None:
            self.capture_task_case(blocks, flow, selection, value)

    def capture_task_case(self, blocks, flow, selection, value):
        if flow.stopped or flow.opaque or value.constant is UNKNOWN:
            raise _TaskOrderUnknown()
        index, label = selection.labels[selection.index]
        label_value = self.checked_select_value(value.constant, selection.category, label)
        match = selection.match
        if match is None and selection.selected == label_value:
            match = index
        # Later labels still run after a match, before entering the selected arm.
        blocks[-1] = replace(selection, index=selection.index + 1, match=match)

    def checked_select_value(self, value, category, node):
        try:
            with rt._numeric_scope('pythonic'):
                return rt.select_scalar(value, category, node.get('line'))
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None

    def task_operand(self, node, flow, scope, blocks, consumer):
        if node['kind'] == 'call' and node['value'] not in self.plan['routines']:
            name, args = node['value'], node['args']
            file_uninit = (name == 'UNINIT' and len(args) == 1
                           and scope.reference_schema(args[0], staged=True) == ['FILE'])
            if name in FILE_TASK_QUERIES or file_uninit:
                if len(args) != 1:
                    raise _TaskOrderUnknown()
                self.start_task_file(blocks, flow, scope, node, consumer)
                return None
        if node['kind'] == 'call' and node['value'] == 'ARRAY_LEN':
            if len(node['args']) not in (1, 2):
                raise _TaskOrderUnknown()
            blocks.append(_TaskArrayLength(node, consumer))
            return None
        if node['kind'] == 'call' and node['value'] in SCALAR_PURE:
            if len(node['args']) != SCALAR_PURE[node['value']]:
                raise _TaskOrderUnknown()
            blocks.append(_TaskExpression(node, consumer))
            return None
        call = scope.scalar_routine_call(node)
        if call is not None:
            blocks.append(_TaskArguments(call, consumer))
            return None
        if scalar_task_operator(node):
            blocks.append(_TaskExpression(node, consumer))
            return None
        if node['kind'] in ('index', 'field'):
            if self.selects_routine_result(node):
                blocks.append(_TaskResultSelection(node, consumer))
                return None
            spec = scope.reference_schema(node, staged=True)
            if spec and spec[0] in SCALARS:
                self.start_task_selection(blocks, flow, node, consumer, reading=True)
                return None
        if node['kind'] == 'repeat_eval' or not scope.operand(node):
            raise _TaskOrderUnknown()
        if node['kind'] == 'name' and scope.types.get(node['value'], [None])[0] in SCALARS:
            loc = self.slot(node['value'], node, flow)
            if loc is not None:
                return self.read_task_scalar(loc, node, flow)
        return self.expr(node, flow, True)

    def task_data_operand(self, node, flow, scope, blocks, consumer):
        while node['kind'] == 'group':
            node = node['args'][0]
        call = scope.data_routine_call(node)
        if call is not None:
            blocks.append(_TaskArguments(call, consumer))
            return None
        if node['kind'] in ('field', 'index') and self.selects_routine_result(node):
            blocks.append(_TaskResultSelection(node, consumer))
            return None
        schema = scope.reference_schema(node, staged=True)
        if schema and schema[0] in TASK_DATA_AGGREGATES:
            self.start_task_selection(blocks, flow, node, consumer, reading=True)
            return None
        if scope.operand(node):
            return self.expr(node, flow, True, partial=not isinstance(consumer, _TaskWrite))
        raise _TaskOrderUnknown()

    def read_task_scalar(self, loc, node, flow):
        if self.leaf_uninitialized(loc, flow):
            raise _TaskOrderUnknown()
        return self.read(loc, node, flow, True)

    def start_task_selection(self, blocks, flow, node, consumer, *, reading=False, assignment=None):
        root, selectors = node, []
        while root['kind'] in ('field', 'index', 'group'):
            if root['kind'] != 'group':
                selectors.append(root)
            root = root['args'][0]
        loc = self.locate(root, flow, True)
        if (loc is None or loc.kind not in ('variable', 'local', 'predefined-file') or loc.named_data
                or loc.path_slot is not None or flow.stopped or flow.opaque):
            raise _TaskOrderUnknown()
        _, root_type = _array_dimensions(loc.root_spec)
        if (root_type and root_type[0] == 'PATH' and not reading and assignment is None
                and not isinstance(consumer, _TaskCollectionWrite)):
            raise _TaskOrderUnknown()
        blocks.append(_TaskSelection(node, loc, tuple(reversed(selectors)), consumer,
                                     reading=reading, assignment=assignment))

    def next_task_selection(self, blocks, flow, scope, selection):
        self.tick()
        if not selection.selectors:
            blocks.pop()
            self.finish_task_selection(blocks, flow, selection)
            return

        node, *tail = selection.selectors
        location = selection.location
        if node['kind'] == 'field':
            if location.spec[0] == 'PATH' and self.known_path_count(location, flow, False) is None:
                raise _TaskOrderUnknown()
            location = self.checked_task_selection(self.field_child(location, node['value'], node, flow))
        else:
            operands = node['args'][1:]
            if len(selection.indices) < len(operands):
                operand = operands[len(selection.indices)]
                value = self.task_operand(operand, flow, scope, blocks, selection)
                if value is not None:
                    self.consume_task_value(blocks, flow, selection, value)
                return
            # A flat subscript list evaluates all indices before checking any bounds.
            for index in selection.indices:
                if type(index) is not int:
                    raise _TaskOrderUnknown()
                if location.spec[0] == 'PATH':
                    count = self.known_path_count(location, flow, False)
                    minimum = 0 if node.get('static_zero_subscript') and location.spec[2] is not None else 1
                    if count is None or not minimum <= index <= count:
                        raise _TaskOrderUnknown()
                location = self.checked_task_selection(self.index_child(location, index, node, flow))
        blocks[-1] = replace(selection, location=location, selectors=tuple(tail), indices=())

    def finish_task_selection(self, blocks, flow, selection):
        loc, consumer = selection.location, selection.consumer
        if self.variable_path_storage(loc, flow, False) is not True:
            raise _TaskOrderUnknown()
        if selection.reading:
            if isinstance(consumer, _TaskArrayLength):
                if file_task_storage(loc.spec):
                    self.checked_task_file_schema(loc.spec)
                value = _Value(spec=loc.spec)
            elif loc.spec[0] in TASK_DATA_AGGREGATES:
                writing = isinstance(consumer, _TaskWrite)
                self.task_data_schema(loc.spec, max_leaves=1024 if writing else MAX_FACTS)
                value = self.read(loc, selection.node, flow, True, partial=not writing)
            else:
                value = self.read_task_scalar(loc, selection.node, flow)
            self.consume_task_value(blocks, flow, consumer, value)
        elif isinstance(consumer, (_TaskArguments, _TaskQueueCall)):
            if isinstance(consumer, _TaskArguments) and file_task_storage(loc.spec):
                self.checked_task_file_schema(loc.spec)
            blocks[-1] = replace(consumer, actuals=(*consumer.actuals, loc))
        elif isinstance(consumer, _TaskFile):
            if consumer.key is None and loc.spec == ['FILE']:
                key = loc.root if loc.kind == 'predefined-file' else loc.key
                blocks[-1] = replace(consumer, key=key)
            elif consumer.key is not None and loc.spec == ['INTEGER']:
                blocks[-1] = replace(consumer, values=(*consumer.values, loc))
            else:
                raise _TaskOrderUnknown()
        elif isinstance(consumer, _TaskRead):
            if not self.plain_task_read_storage(loc.root_spec):
                raise _TaskOrderUnknown()
            if loc.spec[0] not in SCALARS:
                self.task_data_schema(loc.spec, max_leaves=1024)
            leaves = self.leaves(loc)
            if not leaves:
                raise _TaskOrderUnknown()
            blocks[-1] = replace(consumer, leaves=tuple(leaves))
        elif isinstance(consumer, _TaskCollectionWrite):
            expected, terminal = _array_dimensions(consumer.schema)
            actual, member = _array_dimensions(loc.spec)
            if (terminal != member or len(expected) != len(actual)
                    or any(size is not None and size != extent for size, extent in zip(expected, actual))):
                raise _TaskOrderUnknown()
            generation = self.path_descriptor_generation(loc, flow) if consumer.bounds else None
            if consumer.bounds and (loc.spec[0] != 'PATH' or generation is None):
                raise _TaskOrderUnknown()
            blocks[-1] = replace(consumer, location=loc, generation=generation)
        elif isinstance(consumer, _TaskAssignment):
            value = selection.assignment
            if consumer.spec[0] in TASK_DATA_AGGREGATES:
                conversion = consumer.node.get('data_assignment_conversion')
                if conversion and conversion[0] == 'receiver':
                    value = self.convert_task_data(conversion[0], loc.spec, value, consumer.node, conversion[2])
                if self.task_data_schema(loc.spec) != tuple_spec(value.spec):
                    raise _TaskOrderUnknown()
            else:
                value = self.checked_task_scalar(loc.spec, value, consumer.node)
            self.write(loc, value, flow, consumer.node)
        else:
            local_owner = self.frames[-1]['owner'] if self.frames else None
            owned = (('variable', self.program), ('local', local_owner))
            if (loc.kind, loc.owner) not in owned or loc.spec[0] not in INTEGRAL_TYPES:
                raise _TaskOrderUnknown()
            blocks.append(_TaskForHeader(consumer, loc))

    def next_task_result_selection(self, blocks, flow, scope, selection):
        self.tick()
        node, values = selection.node, selection.values
        operands = node['args']
        index = len(values)
        if not values:
            value = self.task_data_operand(operands[0], flow, scope, blocks, selection)
        elif index < len(operands):
            value = self.task_operand(operands[index], flow, scope, blocks, selection)
        else:
            value = values[0]
            if node['kind'] == 'field':
                value = self.checked_task_result_member(value, 'field', node['value'], node)
            else:
                # Each flat subscript is evaluated before any bounds are checked.
                for subscript in values[1:]:
                    if type(subscript.constant) is not int:
                        raise _TaskOrderUnknown()
                    value = self.checked_task_result_member(value, 'index', subscript.constant, node)
            if value.spec[0] in SCALARS and value.uninitialized:
                raise _TaskOrderUnknown()
            blocks.pop()
            self.consume_task_value(blocks, flow, selection.consumer, value)
            return
        if value is not None:
            self.consume_task_value(blocks, flow, selection, value)

    def checked_task_result_member(self, value, kind, selector, node):
        self.tick(len(value.facts or ()))
        result = self.select_result_member(value, kind, selector, node)
        if not result.spec or result.spec[0] not in TASK_ROUTINE_VALUES:
            raise _TaskOrderUnknown()
        return result

    def next_task_array_length(self, blocks, flow, scope, length):
        self.tick()
        operands, values = length.node['args'], length.values
        if not values:
            array = operands[0]
            schema = scope.reference_schema(array, staged=True)
            if schema and schema[0] == 'ARRAY':
                self.start_task_selection(blocks, flow, array, length, reading=True)
                return
            value = self.task_data_operand(array, flow, scope, blocks, length)
        elif len(values) < len(operands):
            value = self.task_operand(operands[1], flow, scope, blocks, length)
        else:
            actual = values[0].spec
            spec = tuple_spec(actual) if file_task_storage(actual) else self.task_data_schema(actual)
            if spec[0] != 'ARRAY':
                raise _TaskOrderUnknown()
            dimensions = rt.array_dimensions(spec) if len(values) == 2 else rt.array_shape(spec)
            axis = values[1].constant if len(values) == 2 else 1
            if type(axis) is not int or not 1 <= axis <= len(dimensions):
                raise _TaskOrderUnknown()
            blocks.pop()
            self.consume_task_value(blocks, flow, length.consumer, _Value(dimensions[axis - 1], spec=['INTEGER']))
            return
        if value is not None:
            self.consume_task_value(blocks, flow, length, value)

    def next_task_expression(self, blocks, flow, scope, expression):
        self.tick()
        node, values = expression.node, expression.values
        kind, operator, operands = node['kind'], node['value'], node['args']
        if kind == 'binary' and operator in ('AND', 'OR'):
            evaluation = node.get('evaluation')
            if evaluation not in ('short-circuit', 'eager'):
                raise _TaskOrderUnknown()
            if values and evaluation == 'short-circuit':
                left = values[0].constant
                if type(left) is not bool:
                    raise _TaskOrderUnknown()
                if left == (operator == 'OR'):
                    blocks.pop()
                    self.consume_task_value(blocks, flow, expression.consumer, values[0])
                    return
        if len(values) < len(operands):
            value = self.task_operand(operands[len(values)], flow, scope, blocks, expression)
            if value is not None:
                self.consume_task_value(blocks, flow, expression, value)
            return
        if kind == 'call':
            value = self.scalar_builtin_result(node, values)
            if not value.complete or value.constant is UNKNOWN and all(slot.constant is not UNKNOWN for slot in values):
                raise _TaskOrderUnknown()
        else:
            value = values[0] if kind == 'group' else self.checked_task_operator(node, values)
        blocks.pop()
        self.consume_task_value(blocks, flow, expression.consumer, value)

    def capture_task_expression_value(self, blocks, expression, value):
        node = expression.node
        if node['kind'] == 'call':
            if not value.complete or value.uninitialized or value.spec and value.spec[0] not in SCALARS:
                raise _TaskOrderUnknown()
            index = len(expression.values)
            expected = BUILTIN_SIGNATURES[node['value']][0][index]
            # The compiler widens INTEGER operands to REAL before evaluating the next argument.
            if expected == 'REAL' and type(value.constant) is int:
                try:
                    with rt._numeric_scope('pythonic'):
                        widened = rt.real(value.constant, node['args'][index].get('line'))
                except rt.KarelRuntimeError:
                    raise _TaskOrderUnknown() from None
                value = _Value(widened, spec=['REAL'])
        blocks[-1] = replace(expression, values=(*expression.values, value))

    def checked_task_operator(self, node, values):
        if any(value.uninitialized or value.spec and value.spec[0] not in SCALARS for value in values):
            raise _TaskOrderUnknown()
        operands = tuple(value.constant for value in values)
        if any(value is UNKNOWN for value in operands):
            return _Value(complete=all(value.complete for value in values))
        if any(type(value) not in (bool, int, float, str) for value in operands):
            raise _TaskOrderUnknown()
        operation = rt.unary if node['kind'] == 'unary' else rt.binary
        try:
            with rt._numeric_scope('pythonic'):
                result = operation(node['value'], *operands, node.get('line'))
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None
        if type(result) is str and len(result) > 254:
            raise _TaskOrderUnknown()
        return _Value(result)

    def next_task_argument(self, blocks, flow, scope, arguments):
        self.tick()
        call, actuals = arguments.call, arguments.actuals
        index = len(actuals)
        if index == len(call['args']):
            blocks.pop()
            references = [item for item in actuals if isinstance(item, _Location)]
            prepared = self.bind_routine(call['value'], call, actuals, references, flow,
                                         statement_call=arguments.consumer is None, staged=True)
            if prepared is None:
                raise _TaskOrderUnknown()
            self.plan, routine, frame = prepared
            self.frames.append(frame)
            blocks.extend((_TaskRoutine(frame, arguments.consumer), (routine['body'], 0)))
            return

        operand = call['args'][index]
        _, expected = self.plan['routines'][call['value']]['parameters'][index]
        if (str(index) in call.get('geometry_arguments', {})
                and str(index) not in call.get('data_arguments', {})):
            raise _TaskOrderUnknown()
        if call['passing'][index] == 'reference':
            if expected == ['FILE']:
                alias = scope.predefined_file_alias(operand)
                if alias is not None:
                    flow.task_file_outputs = self.capture_task_file(flow, alias, operand)
                    location = _Location('predefined-file', '', alias, spec=['FILE'], root_spec=['FILE'])
                    blocks[-1] = replace(arguments, actuals=(*actuals, location))
                    return
            schema = scope.reference_schema(operand, staged=True)
            if file_task_storage(expected):
                if not file_task_storage(schema):
                    raise _TaskOrderUnknown()
            elif not schema or schema[0] not in TASK_ROUTINE_VALUES or file_task_storage(schema):
                raise _TaskOrderUnknown()
            self.start_task_selection(blocks, flow, operand, arguments)
            return
        if expected[0] in TASK_DATA_AGGREGATES:
            value = self.task_data_operand(operand, flow, scope, blocks, arguments)
        else:
            value = self.task_operand(operand, flow, scope, blocks, arguments)
        if value is not None:
            self.consume_task_value(blocks, flow, arguments, value)

    def capture_task_argument(self, blocks, arguments, value):
        index = len(arguments.actuals)
        call = arguments.call
        _, spec = self.plan['routines'][call['value']]['parameters'][index]
        if spec[0] in TASK_DATA_AGGREGATES:
            conversion = call.get('data_arguments', {}).get(str(index))
            if conversion is not None:
                value = self.convert_task_data(conversion[0], spec, value, call['args'][index], conversion[1])
            checked = self.checked_task_data_value(spec, value)
        else:
            if spec[0] == 'STRING':
                if type(value.constant) is str and len(value.constant) > 254:
                    raise _TaskOrderUnknown()
                if spec[1] is None:
                    spec = ['STRING', 254]
            checked = self.checked_task_scalar(spec, value, call['args'][index])
        blocks[-1] = replace(arguments, actuals=(*arguments.actuals, checked))

    def return_from_task_routine(self, blocks, flow, node, value):
        spec = self.frames[-1]['result']
        if (value is None) != (spec is None) or flow.stopped or flow.opaque:
            raise _TaskOrderUnknown()
        # The return expression is evaluated and checked before loop cleanup.
        if spec is not None:
            if spec[0] in TASK_DATA_AGGREGATES:
                conversion = node.get('data_return')
                if conversion is not None:
                    value = self.convert_task_data(conversion[0], spec, value, node, conversion[1])
                value = self.checked_task_data_value(spec, value, result=True)
            else:
                value = self.checked_task_scalar(spec, value, node, result=True)
        while not isinstance(blocks[-1], _TaskRoutine):
            self.tick()
            frame = blocks.pop()
            if isinstance(frame, _TaskLoop) and frame.counter is not None:
                self.clear_task_counter(frame.counter, frame.node, flow)
        blocks[-1] = replace(blocks[-1], result=value)

    def finish_task_routine(self, blocks, flow):
        boundary = blocks.pop()
        self.clear_routine_storage(flow, self.frames.pop()['owner'])
        self.plan = self.task_frame_plan()
        consumer = boundary.consumer
        if consumer is None:
            return
        value = boundary.result
        if value is None:
            raise _TaskOrderUnknown()
        self.consume_task_value(blocks, flow, consumer, value)

    def consume_task_value(self, blocks, flow, consumer, value):
        if flow.stopped or flow.opaque:
            raise _TaskOrderUnknown()
        if isinstance(consumer, _TaskWrite):
            kind = consumer.node['args'][consumer.index].get('write_type')
            if kind in TASK_DATA_AGGREGATES and consumer.aggregate is None:
                self.capture_task_write_aggregate(blocks, consumer, value)
            else:
                blocks[-1] = replace(consumer, values=(*consumer.values, value))
        elif isinstance(consumer, _TaskRepeatCapture):
            if value.spec and value.spec[0] in TASK_DATA_AGGREGATES:
                self.checked_task_data_capture(value)
            elif (not value.complete or value.uninitialized or value.spec and value.spec[0] not in SCALARS
                  or value.constant is not UNKNOWN and type(value.constant) not in (bool, int, float, str)):
                raise _TaskOrderUnknown()
            blocks[-1] = replace(consumer, samples=(*consumer.samples, value))
        elif isinstance(consumer, _TaskSelection):
            blocks[-1] = replace(consumer, indices=(*consumer.indices, value.constant))
        elif isinstance(consumer, _TaskResultSelection):
            if not consumer.values:
                self.checked_task_data_capture(value)
            blocks[-1] = replace(consumer, values=(*consumer.values, value))
        elif isinstance(consumer, _TaskArrayLength):
            blocks[-1] = replace(consumer, values=(*consumer.values, value))
        elif isinstance(consumer, (_TaskCollectionWrite, _TaskFile)):
            blocks[-1] = replace(consumer, values=(*consumer.values, value.constant))
        elif isinstance(consumer, _TaskRead):
            blocks[-1] = replace(consumer, formats=(*consumer.formats, value.constant))
        elif isinstance(consumer, _TaskQueueCall):
            blocks[-1] = replace(consumer, actuals=(*consumer.actuals, value))
        elif isinstance(consumer, _TaskArguments):
            self.capture_task_argument(blocks, consumer, value)
        elif isinstance(consumer, _TaskExpression):
            self.capture_task_expression_value(blocks, consumer, value)
        elif isinstance(consumer, _TaskSelect):
            self.capture_task_case(blocks, flow, consumer, value)
        elif isinstance(consumer, _TaskForHeader):
            self.capture_task_for_bound(blocks, flow, consumer, value)
        elif isinstance(consumer, _TaskLoop):
            self.finish_task_loop_test(blocks, flow, consumer, value)
        elif isinstance(consumer, _TaskAssignment):
            node, spec = consumer.node, consumer.spec
            if spec[0] in TASK_DATA_AGGREGATES:
                conversion = node.get('data_assignment_conversion')
                if conversion and conversion[0] != 'receiver':
                    value = self.convert_task_data(conversion[0], conversion[1], value, node, conversion[2])
                else:
                    self.checked_task_data_capture(value)
            elif value.uninitialized:
                raise _TaskOrderUnknown()
            elif type(value.constant) is float and rt.real_integral_kind(tuple(spec), ('REAL',)):
                try:
                    with rt._numeric_scope('pythonic'):
                        raw = rt.real_integral_value(tuple(spec), value.constant, node.get('line'))
                except rt.KarelRuntimeError:
                    raise _TaskOrderUnknown() from None
                value = _Value(raw, spec=['INTEGER'])
            self.start_task_selection(blocks, flow, node['args'][0], consumer, assignment=value)
        elif consumer['kind'] == 'return':
            self.return_from_task_routine(blocks, flow, consumer, value)
        else:
            self.start_task_branch(blocks, flow, consumer, value)

    def checked_task_data_capture(self, value):
        source = self.task_data_schema(value.spec)
        if value.facts is None or value.whole_record_missing:
            raise _TaskOrderUnknown()
        return source

    def convert_task_data(self, conversion, target, value, node, declared_source):
        source = self.checked_task_data_capture(value)
        expected = tuple_spec(target)
        try:
            with rt._numeric_scope('pythonic'):
                declaration = tuple_spec(declared_source) if declared_source is not None else None
                if declaration is not None and not rt.parameter_accepts(declaration, source):
                    raise _TaskOrderUnknown()
                if conversion == 'receiver':
                    if expected == source:
                        return value
                    conversion = pythonic_schema_conversion(expected, source, array_conversion=rt.array_schema_compatible)
                converter = DATA_AGGREGATE_CONVERTERS.get(conversion)
                if converter is None:
                    raise _TaskOrderUnknown()
                if (conversion == 'array_schema' and rt.array_schema_compatible(expected, source)
                        and rt._array_conversion_spec(expected, source) == source):
                    return value
                self.tick(len(value.facts))
                captured = materialized_value(value, allow_missing=True)
                if captured is UNKNOWN:
                    raise _TaskOrderUnknown()
                line = node.get('line')
                if conversion == 'record_schema':
                    converted = converter(expected, captured, line, source_spec=declaration)
                else:
                    converted = converter(expected, captured, line)
                return detached_facts(converted)
        except (rt.KarelRuntimeError, ArithmeticError, TypeError, ValueError):
            raise _TaskOrderUnknown() from None

    def checked_task_file_schema(self, schema):
        spec = tuple_spec(schema)
        try:
            if file_storage_cost(spec) is None:
                raise _TaskOrderUnknown()
        except ValueError:
            raise _TaskOrderUnknown() from None

    def checked_task_data_value(self, spec, value, *, result=False):
        source = self.checked_task_data_capture(value)
        expected = tuple_spec(spec)
        if not rt.parameter_accepts(expected, source):
            raise _TaskOrderUnknown()
        if result and expected[0] == 'ARRAY':
            # ARRAY results require matching nominal outer storage and exact elements.
            if (rt.array_identity(expected) != rt.array_identity(source)
                    or expected[2] not in (source[2], ('STRING', None))):
                raise _TaskOrderUnknown()
        return value

    def checked_task_scalar(self, spec, value, node, *, result=False):
        if value.uninitialized:
            raise _TaskOrderUnknown()
        if value.constant is UNKNOWN:
            return _stored_value(spec, value)
        target, raw, line = tuple(spec), value.constant, node.get('line')
        try:
            with rt._numeric_scope('pythonic'):
                if type(raw) is float and rt.real_integral_kind(target, ('REAL',)):
                    raw = rt.real_integral_value(target, raw, line)
                raw = rt.checked(target, raw, line)
                if result:
                    rt.require(raw, line)
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None
        if raw is rt.UNINITIALIZED:
            return _Value(complete=False, spec=spec, uninitialized=True)
        return _Value(raw, spec=spec)

    def capture_task_for_bound(self, blocks, flow, header, value):
        if flow.stopped or flow.opaque:
            raise _TaskOrderUnknown()
        node, counter = header.node, header.counter
        try:
            bound = rt.for_bound(tuple(counter.spec), value.constant, header.operand.get('line'))
        except rt.KarelRuntimeError:
            raise _TaskOrderUnknown() from None
        if header.initializing:
            initial = self.checked_task_scalar(counter.spec, value, node)
            self.write(counter, initial, flow, node)
            blocks[-1] = replace(header, initializing=False)
            return
        start, step, count = self.for_range_bounds(node, flow, counter, bound)
        if count is None:
            raise _TaskOrderUnknown()
        blocks[-1] = _TaskLoop(node, counter=counter, values=range(start, start + step * count, step))

    def next_task_iteration(self, blocks, flow, scope, loop):
        self.tick()
        node, iterations = loop.node, loop.iterations
        kind = node['kind']
        if kind == 'for':
            try:
                value = loop.values[iterations]
            except IndexError:
                self.clear_task_counter(loop.counter, node, flow)
                blocks.pop()
                return
            self.enter_task_loop_body(blocks, loop)
            value = self.checked_task_scalar(loop.counter.spec, _Value(value), node)
            self.write(loop.counter, value, flow, node)
            return
        if kind == 'repeat' and not iterations:
            self.enter_task_loop_body(blocks, loop)
            return

        predicate = node['args'][0]
        if kind == 'repeat' and iterations == 1 and loop.repeat_predicate is None:
            if scope.operand(predicate):
                cached = self.sample_condition_inputs(predicate, flow, True, ('repeat_eval',))
                loop = replace(loop, repeat_predicate=cached)
                blocks[-1] = loop
            else:
                terms, live = repeat_capture_parts(predicate, self.tick)
                if terms:
                    blocks.append(_TaskRepeatCapture(terms, live))
                    return
        predicate = loop.repeat_predicate or predicate
        if loop.repeat_predicate is not None and not loop.staged_repeat_test:
            value = self.expr(predicate, flow, True)
        else:
            value = self.task_operand(predicate, flow, scope, blocks, loop)
        if value is not None:
            self.finish_task_loop_test(blocks, flow, loop, value)

    def next_task_repeat_capture(self, blocks, flow, scope, capture):
        self.tick()
        index = len(capture.samples)
        if index == len(capture.terms):
            live = bind_repeat_samples(capture.predicate, capture.samples, self.tick)
            blocks.pop()
            blocks[-1] = replace(blocks[-1], repeat_predicate=live, staged_repeat_test=True)
            return
        term = capture.terms[index]
        operand, = term['args']
        operand = bind_repeat_samples(operand, capture.samples, self.tick)
        if term.get('capture_type') in TASK_DATA_AGGREGATES:
            value = self.task_data_operand(operand, flow, scope, blocks, capture)
        else:
            value = self.task_operand(operand, flow, scope, blocks, capture)
        if value is not None:
            self.consume_task_value(blocks, flow, capture, value)

    def finish_task_loop_test(self, blocks, flow, loop, value):
        if flow.stopped or flow.opaque or type(value.constant) is not bool:
            raise _TaskOrderUnknown()
        if value.constant == (loop.node['kind'] == 'repeat'):
            blocks.pop()
        else:
            self.enter_task_loop_body(blocks, loop)

    def enter_task_loop_body(self, blocks, loop):
        if loop.iterations == MAX_LOOP_ITERATIONS:
            raise _TaskOrderUnknown()
        blocks[-1] = replace(loop, iterations=loop.iterations + 1)
        blocks.append((loop.node['body'], 0))

    def clear_task_counter(self, counter, node, flow):
        spec = counter.spec
        self.write(counter, _Value(complete=False, spec=spec, uninitialized=spec != ['BYTE']), flow, node)

    def byname_gap(self, node, flow, message, *, rejected=False):
        self.unresolved_at('byname', message, node)
        if rejected:
            flow.stopped = True
        else:
            self.opaque(flow)

    def byname_reference(self, node, expected, flow, conditional):
        program_arg, path_arg, entry_arg = node['args']
        program = self.expr(program_arg, flow, conditional, argument_path_edits=True).constant
        if flow.stopped and not flow.opaque:
            return None
        path = self.expr(path_arg, flow, conditional, argument_path_edits=True).constant
        if flow.stopped and not flow.opaque:
            return None
        entry = self.locate(entry_arg, flow, conditional, selector_path_edits=True)
        if flow.stopped and not flow.opaque:
            return None
        if type(program) is not str or type(path) is not str or entry is None or flow.opaque:
            return self.byname_gap(node, flow, 'BYNAME requires a statically resolved name and entry output')
        owner = program.strip().upper() or self.task_roots[-1]
        path = path.upper()
        if not BYNAME_PATH.fullmatch(path):
            return self.byname_gap(node, flow, 'BYNAME requires an ordinary static variable path', rejected=True)
        target, rejected = self.named_variable_location(owner, path, node, flow, conditional, capture_node=True)
        if rejected:
            return self.byname_gap(node, flow, 'BYNAME variable selection is invalid: '+path, rejected=True)
        if target is None:
            return self.byname_gap(node, flow, 'BYNAME target needs proven named storage: '+owner+'.'+path)
        _, terminal = _array_dimensions(target.spec)
        if terminal[0] != 'PATH':
            try:
                rt._validate_data_schema(tuple_spec(target.spec))
            except rt.KarelRuntimeError:
                return self.byname_gap(node, flow, 'BYNAME requires proven data storage: '+path)
        if not self.ordinary_variable_output(target, node, alias=True):
            return self.byname_gap(node, flow, 'BYNAME requires ordinary writable storage: '+path, rejected=True)
        if not rt.parameter_accepts(tuple_spec(expected), tuple_spec(target.spec)):
            return self.byname_gap(node, flow, 'BYNAME variable type does not match the routine parameter: '+path,
                                   rejected=True)
        storage = self.variable_path_storage(target, flow, conditional, named_lookup=True)
        if storage not in (True, MISSING_PATH_RECORD):
            return self.byname_gap(node, flow, 'BYNAME target storage is unresolved: '+path, rejected=storage is False)
        overlap = self.variable_target_overlap(target, (entry,), flow, conditional)
        if overlap is True:
            return self.byname_gap(node, flow, 'BYNAME variable overlaps entry output: '+path, rejected=True)
        if overlap is None:
            return self.byname_gap(node, flow, 'BYNAME entry output overlap is unresolved: '+path)
        self.write_variable_entry(entry, (owner, path), node, flow)
        return target

    def prepare_routine(self, name, args, node, flow, conditional, *, statement_call=False, argument_path_edits=False):
        """Evaluate arguments and bind one routine frame before visiting its body."""
        routine=self.plan['routines'][name]
        modes=node.get('passing',[]);actual=[]
        conversions = node.get('geometry_arguments', {})
        references = []
        with self.capture_operands() as pending:
            start = len(pending)
            for index,item in enumerate(args):
                if flow.stopped and not flow.opaque:
                    return None
                conversion = conversions.get(str(index))
                mode = 'value' if conversion else modes[index] if index<len(modes) else 'unknown'
                # The plan keeps the BYNAME call expression. Its lowering
                # supplies an ordinary reference to the formal.
                byname = (item['kind'] == 'call' and item['value'] == 'BYNAME' and len(item['args']) == 3
                          and 'BYNAME' not in self.plan['routines'])
                if byname or mode == 'reference':
                    ref = (self.byname_reference(item, routine['parameters'][index][1], flow, conditional)
                           if byname else self.locate(item, flow, conditional, capture_node=True))
                    pending.append(ref)
                    references.append(ref)
                    actual.append(ref)
                elif mode=='value':
                    value = self.expr(item, flow, conditional, partial=True,
                                      argument_path_edits=len(pending) > start)
                    expected = routine['parameters'][index][1]
                    if not (flow.stopped and not flow.opaque):
                        if conversion:
                            value = self.geometry_value(conversion, expected, value, item, flow, boundary='argument')
                        elif expected[0] == 'PATH':
                            value = self.convert_path_value(expected, value, item, flow)
                        elif _path_array_cell_type(expected):
                            value = self.convert_path_array_value(expected, value, item, flow)
                    actual.append(value)
                else:
                    self.unresolved_at('argument','Routine passing mode is unresolved: '+name,node)
                    references.append(None)
                    actual.append(self.expr(item,flow,conditional))
        return self.bind_routine(name, node, actual, references, flow, statement_call=statement_call,
                                 argument_path_edits=argument_path_edits)

    def bind_routine(self, name, node, actual, references, flow, *, statement_call=False,
                     argument_path_edits=False, staged=False):
        if flow.stopped and not flow.opaque:
            return None
        routine = self.plan['routines'][name]
        target_plan, target_routine = resolve_routine(self.plan, self.linked_plans, name, routine)
        routine_key = (target_plan['program'], name) if target_plan else None
        if (target_routine is None or any(frame['key'] == routine_key for frame in self.frames)
                or self.suspended_depth + len(self.frames) >= MAX_CALL_DEPTH):
            qualified = (routine['external'] or self.program) + '.' + name
            self.unresolved_at('routine', 'External or recursive routine effects are unresolved: '+qualified, node)
            for item in actual:
                if isinstance(item, _Location):
                    location = self.resolve_path_slot(item, node, flow)
                    if location is not None:
                        self.read(location, node, flow, True)
            self.opaque(flow);return None
        routine = target_routine
        self.serial+=1;owner='@'+name+':'+str(self.serial)
        bindings=[]
        for (formal,spec),item in zip(routine['parameters'],actual):
            source=item.spec if isinstance(item,(_Value,_Location)) else None
            if (isinstance(item,_Location) and spec[0]=='STRING' and source and source[0]=='STRING'
                    and spec[1] is not None and source[1] is not None and spec[1]!=source[1]):
                self.unresolved_at('parameter-capacity','Concrete STRING capacity conflicts with routine constraint: '+name+'.'+formal,node)
                self.opaque(flow);return None
            if staged and file_task_storage(spec):
                if not isinstance(item, _Location) or not rt.parameter_accepts(tuple_spec(spec), tuple_spec(source)):
                    raise _TaskOrderUnknown()
                resolved = source
            elif staged and spec[0] in TASK_DATA_AGGREGATES:
                # Reference constraints are checked on frame entry, after all operands finish.
                if not rt.parameter_accepts(tuple_spec(spec), self.task_data_schema(source)):
                    raise _TaskOrderUnknown()
                resolved = source
            else:
                resolved=_array_value_schema(spec,source) if spec[0]=='ARRAY' else spec
            if resolved is None:
                self.unresolved_at('parameter-shape','Concrete ARRAY shape conflicts with routine constraint: '+name+'.'+formal,node)
                self.opaque(flow);return None
            bindings.append((formal,spec,item,resolved))
        # Direct procedures can replace a PATH after operand capture.
        # A checked argument routine can edit the node list or use COPY_PATH
        # while earlier reference arguments remain tracked by the caller.
        caller = self.frames[-1] if self.frames else None
        procedure = statement_call and routine['result'] is None
        direct = procedure and (caller is None or caller['borrowed_path_edits'])
        argument_edits = (argument_path_edits or procedure) and (
            caller is None or caller['borrowed_path_edits'] or caller['argument_path_edits']
        )
        frame = dict(name=name, key=routine_key, owner=owner, result=routine['result'],
                     slots={key:_Location('local',owner,key,spec=spec,root_spec=spec)
                            for key,spec in routine['types'].items()},
                     constants=routine['constants'], borrowed_path_edits=direct,
                     argument_path_edits=argument_edits, references=tuple(references))
        formals = {formal for formal, _, _, _ in bindings}
        frame['fresh_path_banks'] = {
            key for key, slot in frame['slots'].items() if key not in formals and _path_array_cell_type(slot.spec)
        }
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
                elif _path_array_cell_type(resolved):
                    self.publish_private_path_array(loc, item, node, flow)
                else:
                    self.write(loc,item or _Value(complete=False),flow,node)
        return target_plan, target_routine, frame

    def clear_routine_storage(self, flow, owner):
        for field_name in ('defined','assigned','maybe','uninitialized'):
            setattr(flow,field_name,{key for key in getattr(flow,field_name) if key[1]!=owner})
        flow.constants={key:value for key,value in flow.constants.items() if key[1]!=owner}
        flow.scalar_choices = {key: values for key, values in flow.scalar_choices.items() if key[1] != owner}
        flow.path_orders = {key: order for key, order in flow.path_orders.items() if key is None or key[1] != owner}
        flow.retired_paths = {key: order for key, order in flow.retired_paths.items() if key[0][1] != owner}
        flow.task_queues = {key: queue for key, queue in flow.task_queues.items() if key[1] != owner}

    def routine(self, name, args, node, flow, conditional, *, statement_call=False, argument_path_edits=False):
        external = bool(self.plan['routines'][name]['external'])
        prepared = self.prepare_routine(name, args, node, flow, conditional, statement_call=statement_call,
                                        argument_path_edits=argument_path_edits)
        if prepared is None:
            return _Value(complete=False)
        target_plan, routine, frame = prepared
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
        self.clear_routine_storage(merged, frame['owner'])
        flow.take(merged)
        values=[item[1] for item in exits];result=routine['result']
        if result and result[0] != 'PATH' and not _path_array_cell_type(result):
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
        self.callback_depth += 1
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
            self.callback_depth -= 1
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
        skip_wait = None
        projected_through = -1
        for index, node in enumerate(body):
            if flow.stopped and not flow.opaque:
                break
            if index <= projected_through:
                continue
            if node is skip_wait:
                self.tick()
                self.unresolved_at('task-wait', 'The child pause depends on scheduler admission', node)
                skip_wait = None
                continue
            after_program_return = not self.frames and len(self.exits) > exits_before_block
            branch_conditional = conditional or after_program_return
            handoff = None
            if self.track_tasks and len(self.task_roots) == 1:
                terminal_entry = not self.frames and body is self.plan['body']
                handoff = task_handoff_window(body, index, terminal_entry=terminal_entry, tick=self.tick)
            guard = self.find_open_guard(body, index, flow)
            previous_handoff, previous_guard = self.task_handoff, self.open_guard
            self.task_handoff, self.open_guard = handoff, guard
            try:
                self.statement(node, flow, branch_conditional)
            finally:
                self.task_handoff, self.open_guard = previous_handoff, previous_guard
            if handoff is not None and handoff.reached:
                skip_wait = handoff.waiter
            if guard is not None and guard.projects:
                projected_through = guard.end
                self.project_open_guard(body[index + 1:projected_through + 1], guard, flow, branch_conditional)

    def project_open_guard(self, body, guard, flow, conditional):
        # Replay the assignments and guard from the captured outcomes.
        # OPEN and its input expressions were already analyzed in source order.
        prior_observer = self.required_input_observer
        common_required = None
        branches = []
        try:
            for _, branch in guard.cases:
                required = set()
                self.required_input_observer = required
                self.block(body, branch, conditional)
                common_required = required if common_required is None else common_required & required
                branches.append(branch)
        finally:
            self.required_input_observer = prior_observer
        flow.take(_merge(branches))
        if prior_observer is None:
            for key in common_required or ():
                self.inputs[key]['certainty'] = 'required'
        else:
            prior_observer.update(common_required or ())

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

    def lose_unchecked_default_file(self, flow, *, reading=False):
        bindings = getattr(self.saved_bindings, 'predefined_files', ())
        alias = self.plan.get('default_write_file')
        if reading and alias == 'OUTPUT':
            alias = 'INPUT'
        if alias in bindings or alias is None and bindings:
            flow.task_file_outputs = None

    def read_statement(self, node, flow, conditional):
        """Capture PATH fields before later selectors or format controls can edit them."""
        destinations = []
        captured_path_fields = False
        with self.capture_operands() as pending:
            for argument in node['args']:
                if flow.stopped and not flow.opaque:
                    return
                if argument['kind'] == 'read_cr':
                    continue
                formatted = argument['kind'] == 'read_item'
                target = argument['args'][0] if formatted else argument
                for location in self.path_io_locations(target, flow, conditional, reading=True):
                    fields = self.path_read_fields(location, flow, conditional)
                    if fields is not None:
                        destinations.extend(fields)
                        pending.extend(fields)
                        captured_path_fields = True
                    else:
                        destinations.append(location)
                        pending.append(location)
                if formatted:
                    for control in argument['args'][1:]:
                        if flow.stopped and not flow.opaque:
                            return
                        self.expr(control, flow, conditional, argument_path_edits=captured_path_fields)
        if flow.stopped and not flow.opaque:
            return
        self.unresolved_at('input-stream','READ requires explicitly supplied input data',node)
        if any(location is None for location in destinations):
            self.opaque(flow)
        for location in destinations:
            self.write(location, _Value(), flow, node, definite=False)

    def path_read_fields(self, location, flow, conditional):
        if location is None:
            return None
        dimensions, terminal = _array_dimensions(location.root_spec)
        if terminal and terminal[0] == 'PATH' and len(location.parts) > len(dimensions):
            if self.variable_path_storage(location, flow, conditional) is True:
                return self.leaves(location)
        return None

    def select_branch(self, node, flow, conditional):
        selector, clauses = node['args']
        selected = self.expr(selector, flow, conditional).constant
        cases = [([self.expr(label, flow, conditional).constant for label in labels], body)
                 for _, labels, body in clauses]
        if selected is UNKNOWN or any(value is UNKNOWN for values, _ in cases for value in values):
            return UNKNOWN, [body for _, body in cases] + ([node['alternate']] if node['has_else'] else [])
        default = node['alternate'] if node['has_else'] else None
        return next((body for values, body in cases if selected in values), default), ()

    def for_bounds(self, node, flow, conditional):
        counter, first, last, _ = node['args']
        loc = self.locate(counter, flow, conditional)
        initial = self.expr(first, flow, conditional)
        self.write(loc, initial, flow, node)
        final = self.expr(last, flow, conditional).constant
        return loc, *self.for_range_bounds(node, flow, loc, final)

    def for_range_bounds(self, node, flow, loc, final):
        # The emitted iterator reads the captured counter after final-bound effects.
        start = UNKNOWN
        if loc and not flow.stopped:
            if loc.key in flow.defined:
                start = flow.constants.get(loc.key, UNKNOWN)
            else:
                self.unresolved_at('for-start',
                                   'Captured counter is not proven initialized after final-bound evaluation: '+loc.path,
                                   node)
        step = -1 if node['args'][3] == 'DOWNTO' else 1
        count = max(0, (final - start) * step + 1) if type(start) is int and type(final) is int else None
        return start, step, count

    def statement(self, node, flow, conditional):
        self.tick();kind=node['kind'];args=node['args']
        if flow.task_order_unknown and flow.paused_tasks:
            self.lose_task_order(flow)
        if kind=='assign':
            if 'path_assignment_type' in node:
                self.path_assignment(node, flow, conditional)
                return
            value=self.expr(args[1],flow,conditional,partial=True)
            if flow.stopped and not flow.opaque:
                return
            geometry = node.get('geometry_assignment', ())
            if len(geometry) == 2:
                conversion, schema = geometry
                value = self.geometry_value(conversion, schema, value, node, flow, boundary='assignment')
                if flow.stopped and not flow.opaque:
                    return
            if 'path_array_conversion_type' in node:
                value = self.convert_path_array_value(node['path_array_conversion_type'], value, args[1], flow)
                if flow.stopped and not flow.opaque:
                    return
            target = self.locate(args[0], flow, conditional)
            if flow.stopped and not flow.opaque:
                return
            if len(geometry) == 3 and target is not None:
                conversion = geometry[0]
                if conversion in MODEL_CONVERSIONS:
                    value = self.geometry_value(conversion, target.spec, value, node, flow, boundary='assignment')
                    if flow.stopped and not flow.opaque:
                        return
            if target is not None and _path_array_cell_type(target.spec):
                self.path_array_assignment(target, value, node, flow, conditional)
            else:
                self.write(target, value, flow, node)
            return
        if kind in ('system_selection_assign', 'system_pose_assign'):
            self.robot_table_assignment(*args, node, flow, conditional)
            return
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
            body.scalar_choices.clear()
            self.block(node['body'],body,True)
            if not body.stopped:self.expr(args[0],body,True)
            flow.take(_merge([before,body]));return
        if kind=='repeat':
            self.lose_activation_order()
            self.lose_task_order(flow)
            exits_before_body = len(self.exits)
            flow.constants.clear()
            flow.scalar_choices.clear()
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
            body, possible_bodies = self.select_branch(node, flow, conditional)
            if body is UNKNOWN:
                branches = [flow.copy() for _ in possible_bodies]
                for branch, possible in zip(branches, possible_bodies):
                    self.block(possible, branch, True)
                flow.take(_merge(branches))
            elif body is None:
                flow.stopped = True
            else:
                self.block(body, flow, conditional)
            return
        if kind=='for':
            exit_start=len(self.exits)
            loc, start, step, count = self.for_bounds(node, flow, conditional)
            if count is not None and count <= MAX_LOOP_ITERATIONS:
                for index in range(count):
                    if flow.stopped:break
                    self.write(loc,_Value(start+step*index),flow,node)
                    after_program_return = not self.frames and len(self.exits) > exit_start
                    self.block(node['body'], flow, conditional or after_program_return)
            else:
                self.lose_activation_order()
                self.lose_task_order(flow)
                before=flow.copy();body=flow.copy();body.constants.clear()
                body.scalar_choices.clear()
                self.block(node['body'],body,True);flow.take(_merge([before,body]))
            if loc:
                self.write(loc,_Value(complete=False),flow,node)
                for exited,_ in self.exits[exit_start:]:self.write(loc,_Value(complete=False),exited,node)
            return
        if kind=='return':
            value=self.expr(args[0],flow,conditional,partial=True) if args and args[0] is not None else _Value()
            result = self.frames[-1]['result'] if self.frames else None
            if result and not (flow.stopped and not flow.opaque):
                conversion = node.get('geometry_return')
                if conversion:
                    value = self.geometry_value(conversion, result, value, node, flow, boundary='return')
                elif result[0] == 'PATH':
                    value = self.convert_path_value(result, value, node, flow)
                elif _path_array_cell_type(result):
                    value = self.convert_path_array_value(result, value, node, flow)
            if not flow.stopped or flow.opaque:
                self.exits.append((flow.copy(),value))
            flow.stopped=True;return
        if kind=='write_items':
            self.lose_unchecked_default_file(flow)
            for argument in args:
                if flow.stopped and not flow.opaque:
                    return
                self.expr(argument,flow,conditional)
            return
        if kind=='read':
            self.lose_unchecked_default_file(flow, reading=True)
            self.read_statement(node, flow, conditional)
            return
        if kind=='abort' or kind=='task_control' and args[0] in ('ABORT','STOP') and len(args)==1:
            flow.stopped=True;return
        self.unresolved_at('statement','Control or resource statement requires further analysis: '+kind,node)
        self.opaque(flow)
        for argument in args:
            if isinstance(argument,dict):self.expr(argument,flow,True)
        self.block(node.get('body',[]),flow,True);self.block(node.get('alternate',[]),flow,True)


def analyze_plan(plan, target, *, linked_plans=None, saved_path_count=None, saved_bindings=None):
    track_handlers = track_tasks = linked_plans is not None
    # Restart from the checked entry when control uncertainty could hide
    # callbacks or child bodies that a precise pass had left dormant.
    while True:
        try:
            return _analyze_plan(plan, target, linked_plans=linked_plans,
                                 track_handlers=track_handlers, track_tasks=track_tasks,
                                 saved_path_count=saved_path_count, saved_bindings=saved_bindings)
        except _ActivationUnknown:
            track_handlers = False
        except _TaskOrderUnknown:
            track_tasks = False


def _analyze_plan(plan, target, *, linked_plans, track_handlers, track_tasks, saved_path_count, saved_bindings):
    analyzer = _Analyzer(plan, linked_plans=linked_plans, track_handlers=track_handlers, track_tasks=track_tasks,
                         saved_path_count=saved_path_count, saved_bindings=saved_bindings)
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
    if analyzer.binding_storage:
        report['binding_storage'] = [dict(program=owner, path=root, type=spec)
                                     for (owner, root), spec in sorted(analyzer.binding_storage.items())]
    return report


def discover_inputs(python_source, *, filename='<python>'):
    """Return candidates and explicit gaps; never execute the selected Python."""
    return _discover_inputs(python_source, filename=filename)


def _discover_inputs(python_source, *, filename, saved_path_count=None, saved_bindings=None):
    raw=python_source.encode('utf-8') if type(python_source) is str else python_source
    if type(raw) is not bytes or len(raw)>MAX_BYTES:raise InputDiscoveryError('Python input requires at most 16 MiB')
    try:
        plan=extract(raw.decode('utf-8-sig'))
        target=dict(file=str(filename),sha256=hashlib.sha256(raw).hexdigest(),program=plan['program'])
        return analyze_plan(plan, target, saved_path_count=saved_path_count, saved_bindings=saved_bindings)
    except (InputContractError,UnicodeError,KeyError,IndexError,TypeError,ValueError,AttributeError,RecursionError) as error:
        raise InputDiscoveryError(str(error)) from error


def discover_file(path):
    with Path(path).open('rb') as stream:raw=stream.read(MAX_BYTES+1)
    return discover_inputs(raw,filename=str(path))
