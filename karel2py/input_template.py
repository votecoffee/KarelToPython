"""Prepare editable context shapes without executing generated Python."""
from copy import deepcopy
import re

from . import runtime as rt
from .input_discovery import discover_inputs
from .storage import tuple_spec


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
    if kind == 'JOINTPOS':
        return {'axes': [{'uninitialized': True} for _ in range(rt.joint_width(spec))]}
    if kind in rt.RECORD_TYPES:
        return {name: _missing(member) for name, member in rt.record_fields(spec)}
    return {'unknown_byte': True} if kind == 'BYTE' else {'uninitialized': True}


def _supplied(value):
    if type(value) is dict:
        if value in ({'uninitialized': True}, {'unknown_byte': True}):
            return False
        return all(_supplied(member) for member in value.values())
    if type(value) is list:
        return all(_supplied(member) for member in value)
    return value is not None


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
        else:
            raise InputTemplateError('Unsupported input selector')
    return payload


def _service_address(context, service, address):
    bank = getattr(context, service, None)
    if bank is None:
        return False
    if service in ('numeric', 'strings'):
        return bool(re.fullmatch(r'[1-9][0-9]*', str(address)) and 1 <= int(address) <= bank.count)
    if service == 'ports':
        match = re.fullmatch(r'([A-Z]+)\[([0-9]+)\]', str(address))
        return bool(match and 1 <= int(match[2]) <= bank.counts.get(match[1], 0))
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
    report = discover_inputs(python_source, filename=filename)
    try:
        config = deepcopy({} if context is None else context)
        with rt._numeric_scope('pythonic'):
            execution = rt.ExecutionContext.from_config(config)
        roots = {(row['program'].upper(), row['path'].upper()): index
                 for index, row in enumerate(config.get('variables', []))}
        bindings, requirements, failures = [], [], {}
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
                binding['selectors'] = [list(item) for item in candidate['selectors']]
                try:
                    spec = tuple_spec(candidate['root_type'])
                    count = rt._validate_data_schema(spec)
                except (rt.KarelRuntimeError, TypeError, ValueError, IndexError) as error:
                    if key not in failures:
                        failures[key] = str(error)
                        require('schema', 'Cannot construct root '+key[1]+': '+str(error), program=key[0], path=key[1])
                    continue
                if key in roots:
                    reference = execution.variables.bindings.get(key)
                    # Newly added roots do not belong to the original context.
                    existing_spec = reference.spec if reference is not None else tuple_spec(config['variables'][roots[key]]['type'])
                    if existing_spec != spec:
                        raise InputTemplateError('Existing context type differs from discovered root '+key[0]+'.'+key[1])
                elif key not in failures:
                    if allocated + count > MAX_LEAVES:
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
                    if bank is not None and 1 <= number <= bank.counts.get(port, 0):
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
                require('service', 'Configure the service and address explicitly', **item)
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


def validate_annotations(template, identity):
    """Check the optional source-bound annotation envelope, never its readiness."""
    if (type(template) is not dict or set(template) != {'schema', 'target', 'discovery', 'bindings', 'requirements', 'boundary'}
            or template['schema'] != SCHEMA or type(template['target']) is not dict
            or set(template['target']) != {'file', 'sha256', 'program'}
            or type(template['target']['file']) is not str
            or any(template['target'].get(key) != identity[key] for key in ('sha256', 'program'))
            or type(template['discovery']) is not dict or template['discovery'].get('schema') != 'karel2py.inputs.v1'
            or template['discovery'].get('target') != template['target']
            or type(template['bindings']) is not list or type(template['requirements']) is not list
            or any(type(row) is not dict for row in template['bindings'] + template['requirements'])
            or type(template['boundary']) is not str):
        raise InputTemplateError('Malformed or stale input-template annotations')
