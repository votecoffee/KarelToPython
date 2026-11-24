"""Prepare editable context shapes without executing generated Python."""
from copy import deepcopy
import re

from . import runtime as rt
from .dynamic import reserved as variable_reservation, root_member
from .input_discovery import DEFAULT_EMPTY_PATH, MISSING_PATH_RECORD, _discover_inputs
from .input_teach_discovery import (
    TEACH_POSITION_SECTIONS, TEACH_SCALAR_SECTIONS, teach_position_config_address, teach_program_config_key,
)
from .storage import collection_array_cost, collection_data_spec, list_spec, restore_value, tuple_spec


SCHEMA = 'karel2py.input-template.v1'
MAX_LEAVES = 32767


class InputTemplateError(ValueError):
    pass


def _pointer(*parts):
    return '/' + '/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in parts)


def _missing(spec):
    kind = spec[0]
    if kind == 'ARRAY':
        def shape(dimensions):
            return [shape(dimensions[1:]) if len(dimensions) > 1 else _missing(spec[2])
                    for _ in range(dimensions[0])]
        return shape(rt.array_shape(spec))
    if kind == 'PATH':
        return {'nodes': [], 'data': _missing(spec[2]) if spec[2] is not None else None}
    if kind == 'JOINTPOS':
        return {'axes': [{'uninitialized': True} for _ in range(rt.joint_width(spec))]}
    if kind in rt.RECORD_TYPES:
        return {name: _missing(member) for name, member in rt.record_fields(spec)}
    return {'unknown_byte': True} if kind == 'BYTE' else {'uninitialized': True}


def _path_header_template_cost(spec, selectors):
    """Count an empty PATH root only when the selected input is in its header."""
    path = rt.array_leaf_spec(spec)
    header = path[2]
    depth = len(rt.array_dimensions(spec))
    if header is None or len(selectors) <= depth or tuple(selectors[depth]) != ('index', 0):
        return None
    if spec[0] == 'ARRAY':
        return collection_array_cost(spec)
    if path[1] is not None:
        collection_data_spec(path[1])
    collection_data_spec(header)
    return 1 + rt._validate_data_schema(header)


def _supplied(value):
    if type(value) is dict:
        if value in ({'uninitialized': True}, {'unknown_byte': True}):
            return False
        return all(_supplied(member) for member in value.values())
    if type(value) is list:
        return all(_supplied(member) for member in value)
    return value is not None


def _path_record_slot(payload, spec, index):
    """Locate a supplied PATH record in a context snapshot."""
    if type(payload) is not dict or type(index) is not int:
        raise InputTemplateError('PATH input needs an existing saved receiver.')
    if index == 0 and spec[2] is not None:
        return payload, 'data', spec[2]
    nodes = payload.get('nodes')
    if type(nodes) is not list or not 1 <= index <= len(nodes):
        raise InputTemplateError('The PATH node is outside its saved shape.')
    return nodes, index - 1, spec[1] or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']


def _selected(spec, payload, selectors):
    """Walk canonical snapshots; retain a whole-root edit pointer separately."""
    for kind, value in selectors:
        if kind == 'field':
            spec = dict(rt.record_fields(spec))[value]
            payload = payload[value]
        elif kind == 'index' and spec[0] == 'ARRAY':
            dimensions = rt.array_shape(spec)
            spec = ('ARRAY', dimensions[1:], spec[2]) if len(dimensions) > 1 else spec[2]
            payload = payload[value - 1]
        elif kind == 'index' and spec[0] == 'JOINTPOS':
            spec = rt.REAL
            payload = payload['axes'][value - 1]
        elif kind == 'index' and spec[0] == 'PATH':
            container, key, spec = _path_record_slot(payload, spec, value)
            payload = container[key]
        else:
            raise InputTemplateError('Unsupported input selector')
    return payload


def _service_address(context, service, address):
    bank = getattr(context, service, None)
    if bank is None:
        return False
    if address is None:
        return service in ('motion', 'group_locks', 'teach_programs', 'pose_tolerance', 'external_tolerance',
                           'ports', 'positions', 'robot')
    if service == 'predefined_files':
        return type(address) is str and address in bank
    if service in ('numeric', 'strings'):
        return bool(re.fullmatch(r'[1-9][0-9]*', str(address)) and 1 <= int(address) <= bank.count)
    if service == 'ports':
        match = re.fullmatch(r'([A-Z]+)\[([0-9]+)\]', str(address))
        return bool(match and bank.contains(match[1], int(match[2])))
    if service == 'positions':
        match = re.fullmatch(r'([0-9]+)\[group=([0-9]+)\]', str(address))
        return bool(match and 1 <= int(match[1]) <= bank.count and int(match[2]) in bank.groups)
    return False


def prepare_inputs(python_source, *, filename='<python>', context=None):
    """Return independent context plus source-bound preparation annotations.

    Missing data roots get shaped markers. Banks/counts and initial values are
    never guessed. Annotations describe preparation, not subsequent edits or
    successful execution; the runtime remains responsible for actual reads.
    """
    config, execution = _context_state(context)
    report = _discover_with_context(python_source, filename, execution)
    return _prepare(report, config, execution=execution)


def _context_state(context):
    try:
        config = deepcopy({} if context is None else context)
        with rt._numeric_scope('pythonic'):
            return config, rt.ExecutionContext.from_config(config)
    except (rt.KarelRuntimeError, TypeError, ValueError, KeyError, IndexError, AttributeError, RecursionError) as error:
        raise InputTemplateError('Invalid input template context: '+str(error)) from error


class _SavedBindings:
    """Expose saved schemas and initialization without folding payload values."""

    def __init__(self, execution):
        self.references = execution.variables.bindings
        self.snapshots = {}
        self.store = execution.variables
        self.catalog = execution.programs
        self.program_attributes = execution.program_attributes
        self.numeric = execution.numeric
        self.strings = execution.strings
        self.ports = execution.ports
        self.positions = execution.positions
        self.robot = execution.robot
        self.pose_tolerance = execution.pose_tolerance
        self.external_tolerance = execution.external_tolerance
        self.config_text = execution.config_text
        self.predefined_files = execution.predefined_files
        self.memory_files = execution.files if type(execution.files) is rt.MemoryFiles else None
        self.teach_programs = execution.teach_programs
        self.creation_storage = None
        self.namespaces = None

    def program_catalog(self):
        return self.catalog.entries if self.catalog is not None else ()

    def program_attribute_record(self, name):
        return self.program_attributes.record(name) if self.program_attributes is not None else None

    def system_path(self, owners, path, *, tick):
        tick(len(self.references))
        candidates = (key for key in self.references if key[0] in owners and root_member(path, key[1]))
        return max(candidates, key=lambda key: len(key[1]), default=None)

    def reservation(self):
        if self.creation_storage is None:
            with rt._numeric_scope('pythonic'):
                units = variable_reservation(self.store)
            self.creation_storage = units, {key: self.spec(*key) for key in self.store.metadata}
        return self.creation_storage

    def namespace_paths(self):
        if self.namespaces is None:
            self.namespaces = {}
            for program, path in self.references:
                self.namespaces.setdefault(program, []).append(path)
        return self.namespaces

    def paths(self, owner):
        return self.namespace_paths().get(owner, ())

    def spec(self, owner, path):
        reference = self.references.get((owner, path))
        if reference is None:
            return None

        return list_spec(reference.spec)

    def _selected_value(self, owner, root, selectors):
        key = owner, root
        reference = self.references.get(key)
        if reference is None:
            return None
        if key not in self.snapshots:
            self.snapshots[key] = rt.snapshot_value(reference.raw())
        try:
            return _selected(reference.spec, self.snapshots[key], selectors)
        except (InputTemplateError, KeyError, IndexError, TypeError, rt.KarelRuntimeError):
            return {'uninitialized': True}

    def container_present(self, owner, root, selectors):
        value = self._selected_value(owner, root, selectors)
        return value != {'uninitialized': True} if value is not None else None

    def leaf_initialized(self, owner, root, selectors):
        return _supplied(self._selected_value(owner, root, selectors))


def _saved_path_count(execution, *, migrate_path=None):
    """Look up the initial topology or materialized record of a saved PATH."""
    snapshots = {}
    validated_nodes = {}

    def path_count(program, root, root_type, selectors, *, record_index=None, record_selectors=(), require_value=False,
                   validate_record=False, whole_record=False):
        key = program, root
        reference = execution.variables.bindings.get(key)
        if reference is None:
            return DEFAULT_EMPTY_PATH
        spec = tuple_spec(root_type)
        snapshot_key = key, spec
        if snapshot_key not in snapshots:
            if reference.spec == spec:
                snapshots[snapshot_key] = rt.snapshot_value(reference.raw())
            elif migrate_path is not None:
                migrated = migrate_path(key, reference, spec)
                if migrated is not None:
                    snapshots[snapshot_key] = migrated.value
        if snapshot_key not in snapshots:
            return None
        path = _selected(spec, snapshots[snapshot_key], selectors)
        if record_index is None:
            return len(path['nodes'])
        path_spec = rt.array_leaf_spec(spec) if spec[0] == 'ARRAY' else spec
        try:
            container, key, record_spec = _path_record_slot(path, path_spec, record_index)
        except InputTemplateError:
            return None
        record = container[key]
        if whole_record and not validate_record and record == {'uninitialized': True}:
            return MISSING_PATH_RECORD
        if type(record) is not dict or record.keys() != dict(rt.record_fields(record_spec)).keys():
            return None if whole_record and not validate_record else False
        if validate_record or whole_record:
            node_key = snapshot_key, selectors, record_index
            if node_key not in validated_nodes:
                try:
                    with rt._numeric_scope('pythonic'):
                        rt._aggregate_value(record_spec, restore_value(record_spec, record), allow_partial=True)
                except (ValueError, rt.KarelRuntimeError):
                    validated_nodes[node_key] = False
                else:
                    validated_nodes[node_key] = True
            if not validated_nodes[node_key]:
                return False if validate_record else None
        missing = {'uninitialized': True}
        try:
            parent = _selected(record_spec, record, record_selectors[:-1])
        except (KeyError, IndexError, TypeError):
            return False
        if parent == missing:
            return False
        if require_value and _selected(record_spec, record, record_selectors) == missing:
            # A missing value may still be a valid Reference. Its aggregate
            # copy needs facts beyond the presence of its parent.
            return None
        return True

    return path_count


def _discover_with_context(python_source, filename, execution, *, migrate_path=None):
    return _discover_inputs(python_source, filename=filename, saved_bindings=_SavedBindings(execution),
                            saved_path_count=_saved_path_count(execution, migrate_path=migrate_path))


def _prepare(report, context, *, materialize=True, execution=None):
    try:
        config = context
        if execution is None:
            config, execution = _context_state(context)
        roots = {(row['program'].upper(), row['path'].upper()): index
                 for index, row in enumerate(config.get('variables', []))}
        bindings, requirements, failures = [], [], {}
        missing_path_roots = set()
        snapshots, bank_values = {}, {}
        allocated = 0

        def require(code, message, **details):
            requirements.append(dict(code=code, message=message, **details))

        for candidate in report['inputs']:
            binding = {key: deepcopy(candidate[key]) for key in ('kind', 'program', 'path', 'certainty')}
            binding.update(status='unmapped', context_pointer=None)
            bindings.append(binding)
            if candidate['kind'] == 'variable':
                key = candidate['program'], candidate['root_path']
                binding.update(root_path=candidate['root_path'],
                               selectors=[list(item) for item in candidate['selectors']])
                try:
                    spec = tuple_spec(candidate['root_type'])
                    path_storage = spec[0] == 'PATH' or rt.path_array_io_type(spec)
                    if path_storage:
                        count = _path_header_template_cost(spec, candidate['selectors']) if key not in roots else None
                    else:
                        count = rt._validate_data_schema(spec)
                except (rt.KarelRuntimeError, TypeError, ValueError, IndexError) as error:
                    if key not in failures:
                        failures[key] = str(error)
                        require('schema', 'Cannot construct root '+key[1]+': '+str(error), program=key[0], path=key[1])
                    continue
                if path_storage and key not in roots and count is None:
                    if key not in missing_path_roots:
                        missing_path_roots.add(key)
                        require('path-storage', 'Supply the typed PATH root with its existing records',
                                program=key[0], path=key[1])
                    continue
                if key in roots:
                    reference = execution.variables.bindings.get(key)
                    # Newly added roots do not belong to the original context.
                    existing_spec = reference.spec if reference is not None else tuple_spec(config['variables'][roots[key]]['type'])
                    if existing_spec != spec:
                        raise InputTemplateError('Existing context type differs from discovered root '+key[0]+'.'+key[1])
                elif key not in failures:
                    if not materialize or allocated + count > MAX_LEAVES:
                        failures[key] = 'Template storage limit reached'
                        require('limit', failures[key], program=key[0], path=key[1])
                        continue
                    allocated += count
                    rows = config.setdefault('variables', [])
                    roots[key] = len(rows)
                    rows.append(dict(program=key[0], path=key[1], type=deepcopy(candidate['root_type']), value=_missing(spec)))
                else:
                    continue
                index = roots[key]
                binding['context_pointer'] = _pointer('variables', index, 'value')
                reference = execution.variables.bindings.get(key)
                if key not in snapshots:
                    snapshots[key] = rt.snapshot_value(reference.raw()) if reference is not None else config['variables'][index]['value']
                payload = snapshots[key]
                try:
                    selected = _selected(spec, payload, candidate['selectors'])
                    binding['status'] = 'supplied' if _supplied(selected) else 'missing'
                except (KeyError, TypeError, IndexError, rt.KarelRuntimeError, InputTemplateError):
                    if path_storage:
                        binding['context_pointer'] = None
                        require('path-storage', 'Supply the selected PATH storage in the saved context',
                                program=key[0], path=candidate['path'])
                        continue
                    binding['status'] = 'missing'
            else:
                kind = candidate['kind']
                service = {'port': 'ports', 'numeric_register': 'numeric', 'string_register': 'strings',
                           'position_register': 'positions'}.get(kind)
                bank = getattr(execution, service, None) if service else None
                number = candidate.get('index')
                if kind == 'port':
                    port = candidate['port']
                    values = config.get('ports', {}).get('values', {})
                    port_key = next((key for key in values if key.upper() == port), port)
                    number_key = next((key for key in values.get(port_key, {}) if int(key) == number), str(number))
                    binding['context_pointer'] = _pointer('ports', 'values', port_key, number_key)
                    if bank is not None and bank.contains(port, number):
                        binding['status'] = 'supplied' if (port, number) in bank.values else 'missing'
                elif kind == 'position_register':
                    group = candidate.get('group')
                    if group is None:
                        require('group', 'Position input needs an explicit caller-group mapping', path=candidate['path'])
                    else:
                        values = config.get('positions', {}).get('values', {})
                        def address(key):
                            parts = tuple(int(item) for item in key.split(':'))
                            return parts if len(parts) == 2 else (bank.groups[0], parts[0])
                        number_key = next((key for key in values if address(key) == (group, number)), str(group)+':'+str(number))
                        binding['context_pointer'] = _pointer('positions', 'values', number_key)
                        if bank is not None and group in bank.groups and 1 <= number <= bank.count:
                            binding['status'] = 'supplied' if (group, number) in bank.values else 'missing'
                elif kind in TEACH_POSITION_SECTIONS:
                    address = teach_position_config_address(config, candidate['program'], candidate['group'], number, kind)
                    if address is not None:
                        owner, index, row = address
                        binding['context_pointer'] = _pointer('teach_programs', 'programs', owner,
                                                              TEACH_POSITION_SECTIONS[kind], index, 'value')
                        binding['status'] = 'supplied' if row is not None else 'missing'
                elif kind in TEACH_SCALAR_SECTIONS:
                    owner = teach_program_config_key(config, candidate['program'])
                    if owner is not None:
                        section = TEACH_SCALAR_SECTIONS[kind]
                        key = str(number)
                        binding['context_pointer'] = _pointer('teach_programs', 'programs', owner, section, key)
                        values = config['teach_programs']['programs'][owner].get(section, {})
                        binding['status'] = 'supplied' if key in values else 'missing'
                elif service in ('numeric', 'strings'):
                    values = config.get(service, {}).get('values', {})
                    number_key = next((key for key in values if int(key) == number), str(number))
                    binding['context_pointer'] = _pointer(service, 'values', number_key)
                    if bank is not None and 1 <= number <= bank.count:
                        if service not in bank_values:
                            bank_values[service] = bank.snapshot()
                        binding['status'] = 'supplied' if number in bank_values[service] else 'missing'
            if binding['status'] != 'supplied':
                require('value', 'Review and supply this '+candidate['certainty']+' input',
                        kind=candidate['kind'], program=candidate['program'], path=candidate['path'],
                        context_pointer=binding['context_pointer'])
        for item in report['context_requirements']:
            if not _service_address(execution, item['service'], item['address']):
                message = ('Configure this offline service explicitly' if item['address'] is None else
                           'Configure the service and address explicitly')
                require('service', message, **item)
        # Validate generated shapes with the real context consumer, without
        # normalizing or replacing any caller-supplied values/configuration.
        with rt._numeric_scope('pythonic'):
            rt.ExecutionContext.from_config(deepcopy(config))
        annotations = dict(schema=SCHEMA, target=deepcopy(report['target']), discovery=report,
                           bindings=bindings, requirements=requirements,
                           boundary='Preparation snapshot only; edit inputs.context. No invented initial values, bank capacities, readiness guarantee or target execution.')
        return dict(context=config, template=annotations)
    except (rt.KarelRuntimeError, TypeError, ValueError, KeyError, IndexError, AttributeError, RecursionError) as error:
        if isinstance(error, InputTemplateError):
            raise
        raise InputTemplateError('Invalid input template context: '+str(error)) from error


def _matches_target(target, identity):
    if 'modules' in identity:
        # Run results and edits change the document hash. Module pins remain stable.
        return type(target) is dict and target == identity
    return (type(target) is dict and set(target) == {'file', 'sha256', 'program'}
            and type(target['file']) is str
            and type(target['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}', target['sha256'])
            and type(target['program']) is str and re.fullmatch(r'[A-Z_][A-Z_0-9]*', target['program'])
            and target['sha256'] == identity['sha256'] and target['program'] == identity['program'])


def validate_annotations(template, identity):
    """Check the optional source-bound annotation envelope, never its readiness."""
    fields = {'schema', 'target', 'discovery', 'bindings', 'requirements', 'boundary'}
    if (type(template) is not dict or set(template) not in (fields, fields | {'refresh'}) or template['schema'] != SCHEMA
            or not _matches_target(template['target'], identity)
            or type(template['discovery']) is not dict or template['discovery'].get('schema') != 'karel2py.inputs.v1'
            or template['discovery'].get('target') != template['target']
            or type(template['bindings']) is not list or type(template['requirements']) is not list
            or any(type(row) is not dict for row in template['bindings'] + template['requirements'])
            or type(template['boundary']) is not str):
        raise InputTemplateError('Malformed or stale input-template annotations')
    if 'refresh' in template:
        from .input_refresh import validate_refresh
        validate_refresh(template['refresh'], linked='modules' in identity)
