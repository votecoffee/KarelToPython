"""Preserve compatible edited inputs while rediscovering a selected target."""
from copy import deepcopy
import re

from . import runtime as rt
from .input_discovery import MAX_INPUTS
from .input_template import (
    InputTemplateError, _context_state, _discover_with_context, _prepare, _supplied, validate_annotations,
)
from .storage import tuple_spec


SCHEMA = 'karel2py.input-refresh.v1'


def _migrate(before, payload, after, missing):
    """Copy bounded, same-meaning leaves into a separately prepared new shape."""
    kind = after[0]
    if before[0] != kind:
        return missing, 0
    if kind == 'STRUCTURE' and before[1] != after[1]:
        return missing, 0
    if kind in rt.RECORD_TYPES:
        if type(payload) is not dict:
            return missing, 0
        fields = dict(rt.record_fields(before)); count = 0
        for name, spec in rt.record_fields(after):
            if name in fields and name in payload:
                missing[name], copied = _migrate(fields[name], payload[name], spec, missing[name])
                count += copied
        return missing, count
    if kind == 'ARRAY':
        old_shape, new_shape = rt.array_shape(before), rt.array_shape(after)
        if len(old_shape) != len(new_shape) or rt.array_identity(before) != rt.array_identity(after):
            return missing, 0
        def cells(old, new, depth):
            if type(old) is not list:
                return 0
            count = 0
            for index in range(min(len(old), len(new))):
                if depth + 1 < len(new_shape):
                    count += cells(old[index], new[index], depth + 1)
                else:
                    new[index], copied = _migrate(before[2], old[index], after[2], new[index])
                    count += copied
            return count
        return missing, cells(payload, missing, 0)
    if kind == 'JOINTPOS':
        values = payload.get('axes') if type(payload) is dict else None
        count = 0
        if type(values) is list:
            for index, value in enumerate(values[:len(missing['axes'])]):
                missing['axes'][index] = deepcopy(value)
                count += int(_supplied(value))
        return missing, count
    if before == after or kind == 'STRING' and type(payload) is str and len(payload) <= after[1]:
        return deepcopy(payload), int(_supplied(payload))
    return missing, 0


def _catalog(report):
    rows = report.get('inputs')
    if type(rows) is not list or len(rows) > MAX_INPUTS:
        raise InputTemplateError('Invalid previous input catalog')
    result = {}
    for row in rows:
        if (type(row) is not dict or any(key not in row for key in ('kind', 'program', 'path', 'type', 'certainty'))
                or type(row['kind']) is not str or type(row['path']) is not str
                or row['program'] is not None and type(row['program']) is not str):
            raise InputTemplateError('Invalid previous input catalog entry')
        key = row['kind'], row['program'] or '', row['path']
        if key in result:
            raise InputTemplateError('Duplicate previous input catalog entry')
        result[key] = {name: deepcopy(row[name]) for name in
                       ('kind', 'program', 'path', 'type', 'certainty', 'root_type', 'type_options') if name in row}
    return result


def _previous_template(inputs, *, linked_target=None):
    if type(inputs) is not dict or set(inputs) not in ({'context'}, {'context', 'template'}):
        raise InputTemplateError('Refresh requires context and optional template annotations')
    previous = inputs.get('template')
    if 'template' in inputs:
        identity = linked_target
        if identity is None:
            identity = previous.get('target', {}) if type(previous) is dict else {}
            if type(identity) is not dict or 'modules' in identity:
                raise InputTemplateError('Malformed or stale input-template annotations')
        validate_annotations(previous, identity)
    return previous


def refresh_inputs(python_source, inputs, *, filename='<python>'):
    """Return fresh context and annotations for standalone Python."""
    previous = _previous_template(inputs)
    original, execution = _context_state(inputs['context'])
    report = _discover_with_context(python_source, filename, execution)
    old_target = {key: previous['target'][key] for key in ('sha256', 'program')} if previous is not None else None
    return _refresh_report(report, original, previous, old_target, execution=execution)


def refresh_linked_inputs(report, inputs, previous_target, execution=None):
    """Carry saved variable values with proved storage in the new linked input catalog."""
    previous = _previous_template(inputs, linked_target=previous_target)
    return _refresh_report(report, inputs['context'], previous, previous_target, linked=True, execution=execution)


def _compare_catalogs(previous, report):
    before = _catalog(previous['discovery']) if previous is not None else {}
    after = _catalog(report)
    old_complete = previous is not None and previous['discovery'].get('complete') is True
    new_complete = report.get('complete') is True
    changes = dict(added=[], removed=[], changed=[], retained=[], unresolved=[])
    for key in sorted(before.keys() | after.keys()):
        if key not in before:
            if old_complete:
                changes['added'].append(after[key])
            else:
                changes['unresolved'].append(dict(after=after[key], reason='Previous catalog is unavailable or incomplete; addition is unproven'))
        elif key not in after:
            if new_complete:
                changes['removed'].append(before[key])
            else:
                changes['unresolved'].append(dict(before=before[key], reason='Current discovery is incomplete; removal is unproven'))
        elif before[key] != after[key]:
            changes['changed'].append(dict(before=before[key], after=after[key]))
        else:
            changes['retained'].append(after[key])
    return changes, old_complete and new_complete


def _variable_migration(key, row, index, new_type, status):
    return dict(program=key[0], path=key[1], old_type=deepcopy(row['type']), new_type=deepcopy(new_type),
                preserved_leaves=0, source_pointer='/inputs/context/variables/'+str(index)+'/value',
                context_pointer=None, status=status)


def _refresh_report(report, context, previous, previous_target, *, linked=False, execution=None):
    try:
        original = context
        if execution is None:
            original, execution = _context_state(context)
        new_roots = {(row['program'], row['root_path']): row['root_type']
                     for row in report['inputs'] if row['kind'] == 'variable'}
        if linked:
            # Whole transfers can depend on an exact saved shape without
            # reading any initial field value, for example READ of a PATH.
            new_roots.update({(row['program'], row['path']): row['type']
                              for row in report.get('path_storage', ())})
        config = deepcopy(original)
        changed, rows, migrations = {}, [], []
        for index, row in enumerate(original.get('variables', [])):
            key = row['program'].upper(), row['path'].upper()
            if linked and key not in new_roots:
                status = 'not-discovered' if report.get('complete') is True else 'unresolved'
                migrations.append(_variable_migration(key, row, index, None, status))
                continue
            reference = execution.variables.bindings[key]
            if key in new_roots:
                new_type = new_roots[key]
                new_spec = tuple_spec(new_type) if type(new_type) in (list, tuple) else None
                if reference.spec != new_spec:
                    migration = _variable_migration(key, row, index, new_type, 'unmapped')
                    migrations.append(migration)
                    changed[key] = reference, migration
                    continue
            rows.append(deepcopy(row))
        if 'variables' in config:
            config['variables'] = rows
        prepared = _prepare(report, config)
        roots = {(row['program'].upper(), row['path'].upper()): index
                 for index, row in enumerate(prepared['context'].get('variables', []))}
        for key, (reference, migration) in changed.items():
            new_index = roots.get(key)
            if new_index is None:
                continue
            target = prepared['context']['variables'][new_index]
            spec = tuple_spec(target['type']); count = rt._validate_data_schema(spec)
            migration['context_pointer'] = '/variables/'+str(new_index)+'/value'
            try:
                rt._validate_data_schema(reference.spec)
            except rt.KarelRuntimeError:
                copied = 0
            else:
                target['value'], copied = _migrate(reference.spec, rt.snapshot_value(reference.raw()), spec, target['value'])
            migration.update(preserved_leaves=copied, missing_leaves=count-copied, status='migrated' if copied else 'reset')
        # Recompute edited-value status without materializing any roots that
        # exceeded the first pass's shared storage budget.
        prepared = _prepare(report, prepared['context'], materialize=False)
        changes, comparison_complete = _compare_catalogs(previous, report)
        prepared['template']['refresh'] = dict(schema=SCHEMA, previous_target=deepcopy(previous_target),
            baseline_known=previous is not None, comparison_complete=comparison_complete,
            changes=changes, variables=migrations)
        return prepared
    except (rt.KarelRuntimeError, TypeError, ValueError, KeyError, IndexError, AttributeError, RecursionError) as error:
        if isinstance(error, InputTemplateError):
            raise
        raise InputTemplateError('Invalid refresh inputs: '+str(error)) from error


def validate_refresh(value, *, linked=False):
    fields = {'schema', 'previous_target', 'baseline_known', 'comparison_complete', 'changes', 'variables'}
    if (type(value) is not dict or set(value) not in (fields, fields | {'previous_document'})
            or value['schema'] != SCHEMA or type(value['baseline_known']) is not bool
            or type(value['comparison_complete']) is not bool
            or type(value['changes']) is not dict or set(value['changes']) != {'added', 'removed', 'changed', 'retained', 'unresolved'}
            or any(type(rows) is not list or any(type(row) is not dict for row in rows) for rows in value['changes'].values())
            or type(value['variables']) is not list or any(type(row) is not dict for row in value['variables'])):
        raise InputTemplateError('Malformed input-refresh annotations')
    target = value['previous_target']
    if value['baseline_known'] and target is None:
        raise InputTemplateError('Missing previous refresh target')
    if linked:
        from .project_run import validate_project_target

        try:
            validate_project_target(target)
        except ValueError as error:
            raise InputTemplateError('Malformed previous linked refresh target') from error
    elif target is not None and (type(target) is not dict or set(target) != {'program', 'sha256'}
            or type(target['program']) is not str or type(target['sha256']) is not str
            or not re.fullmatch(r'[0-9a-f]{64}', target['sha256'])):
        raise InputTemplateError('Malformed previous refresh target')
    if 'previous_document' in value:
        document = value['previous_document']
        if (type(document) is not dict or set(document) != {'path', 'sha256'} or type(document['path']) is not str
                or not document['path'] or type(document['sha256']) is not str
                or not re.fullmatch(r'[0-9a-f]{64}', document['sha256'])):
            raise InputTemplateError('Malformed previous refresh document')
