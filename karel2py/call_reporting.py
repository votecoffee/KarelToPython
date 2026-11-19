"""Collect routine argument and service call evidence for translation reports."""
from . import runtime as rt
from .compiler_language import POSITIONAL_VALUE_TYPES, RECORD_TYPES
from .control_flow import counter_text


_CONVERSION_FEATURES = {
    'real_integral': 'checked REAL to integral value argument',
    'numeric_array': 'numeric ARRAY conversion',
    'positional_array': 'positional ARRAY conversion',
    'kinematic_array': 'kinematic ARRAY conversion',
    'kinematic_record': 'kinematic STRUCTURE conversion',
    'record_schema': 'source STRUCTURE schema conversion',
    'array_schema': 'source ARRAY schema conversion',
    'joint_width': 'checked joint width conversion',
    'kinematic': 'kinematic interface conversion',
    'cartesian': 'Cartesian interface value conversion',
    'integer_to_real': 'INTEGER to REAL value argument',
}
_RESULT_CONVERSION_FEATURES = {
    'real_integral': 'checked REAL to integral result',
    'record_schema': 'source STRUCTURE schema result',
    'array_schema': 'source ARRAY schema result',
    'kinematic': 'kinematic interface result conversion',
    'cartesian': 'Cartesian interface result conversion',
}
_CONVERSION_REPORTS = {
    'numeric_array': 'numeric_array_uses',
    'positional_array': 'positional_array_uses',
    'kinematic_array': 'kinematic_array_uses',
    'kinematic_record': 'kinematic_record_uses',
    'record_schema': 'record_schema_uses',
    'array_schema': 'array_schema_uses',
    'joint_width': 'joint_width_uses',
    'kinematic': 'kinematic_interface_uses',
}
_ARRAY_CONVERSIONS = ('positional_array', 'kinematic_array', 'numeric_array', 'array_schema', 'record_schema', 'kinematic_record')
_PRESERVES_MISSING = ('numeric_array', 'array_schema', 'record_schema', 'kinematic_record')
_POSITION_CONVERSIONS = ('positional_array', 'kinematic_array', 'joint_width', 'kinematic', 'cartesian')


def _body_name(emitter):
    return emitter.current_routine.name if emitter.current_routine else emitter.program.name


def _argument_site(emitter, routine, formal):
    return dict(body=_body_name(emitter), routine=routine.name, parameter=formal.value)


def _position(argument):
    return dict(line=argument.token.line, column=argument.token.column)


def record_service_call(emitter, name, token):
    emitter.features.update((name, 'extended services'))
    emitter.service_uses.append(dict(operation=name, body=_body_name(emitter), line=token.line, column=token.column))


def record_file_prefix(emitter, routine, formal, argument, container, selected):
    emitter.file_prefix_argument_uses.append(dict(
        **_argument_site(emitter, routine, formal), **_position(argument),
        source_selector=counter_text(argument), source_type_spec=container, selected_type_spec=selected,
        supplied_subscripts=len(argument.args) - 1, evaluated_once=True, original_cells=True))
    emitter.features.add('direct FILE prefix reference argument')


def record_value_subfield(emitter, routine, formal, argument, *, association_type=None):
    row = dict(**_argument_site(emitter, routine, formal), field=argument.value, **_position(argument),
               evaluated_once=True)
    if association_type is None:
        emitter.features.add('CONFIG subfield value argument')
        emitter.config_value_uses.append(row)
    else:
        emitter.features.add('association subfield value argument')
        emitter.association_value_uses.append(dict(row, record_type=association_type))


def record_routine_conversion(emitter, routine, formal, argument, plan, source):
    conversion = plan.conversion
    if conversion is None:
        return
    target = plan.expected_schema
    feature = _CONVERSION_FEATURES.get(conversion)
    if feature:
        emitter.features.add(feature)
    elif conversion == 'integral_narrow':
        emitter.features.add('checked integral to ' + target[0] + ' value argument')
    elif conversion == 'narrow_promotion':
        emitter.features.add(source[0] + ' to ' + target[0] + ' value argument')
    if conversion in ('kinematic_array', 'kinematic_record', 'kinematic'):
        emitter.features.add('extended services')

    report_name = _CONVERSION_REPORTS.get(conversion)
    if report_name is None:
        return
    operation = 'KINEMATIC_ARGUMENT' if conversion == 'kinematic' else 'ARGUMENT'
    row = dict(operation=operation, **_argument_site(emitter, routine, formal), **_position(argument),
               source_type_spec=source, target_type_spec=target)
    _append_conversion_report(emitter, report_name, conversion, row)


def _append_conversion_report(emitter, report_name, conversion, row, *, returning=False):
    source, target = row['source_type_spec'], row['target_type_spec']
    if conversion == 'kinematic_record':
        row['conversion_kind'] = rt.kinematic_record_kind(target, source)
    elif conversion == 'record_schema':
        row['conversion_kind'] = rt.record_schema_kind(target, source)
    elif conversion == 'array_schema':
        schema_change = rt.array_schema_kind(target, source)
        row['schema_change_kind'] = (schema_change or 'declared_result') if returning else schema_change
    row.update(evaluated_once=True, independent_value=True)
    if returning:
        row['before_cleanup'] = True
    if conversion == 'kinematic_record':
        row['geometry_preflight'] = True
    getattr(emitter, report_name).append(row)


def record_result_conversion(emitter, token, plan):
    conversion = plan.conversion
    if conversion is None:
        return
    feature = _RESULT_CONVERSION_FEATURES.get(conversion, _CONVERSION_FEATURES.get(conversion))
    if feature:
        emitter.features.add(feature)
    if conversion in ('kinematic_array', 'kinematic_record', 'kinematic'):
        emitter.features.add('extended services')
    report_name = _CONVERSION_REPORTS.get(conversion)
    if report_name is not None:
        operation = 'KINEMATIC_RETURN' if conversion == 'kinematic' else 'RETURN'
        name = emitter.current_routine.name
        row = dict(operation=operation, body=name, routine=name, line=token.line, column=token.column,
                   source_type_spec=plan.source_schema, target_type_spec=plan.declared_schema)
        _append_conversion_report(emitter, report_name, conversion, row, returning=True)


def record_routine_result(emitter, token, operand, plan):
    spec, routine = plan.declared_schema, emitter.current_routine
    line, column = token.line, token.column
    if spec[0] == 'ARRAY':
        emitter.array_return_uses.append(dict(
            routine=routine.name, element_type=spec[2][0], element_spec=spec[2], line=line,
            column=column, expression_kind=operand.kind, logical_rank=len(rt.array_dimensions(spec)),
            result_spec=spec, declared_dimensions=rt.array_shape(spec), nominal_identity=rt.array_identity(spec),
            independent_copy=True, initialized_elements_required=emitter.mode != 'pythonic'))
    elif spec[0] == 'STRING':
        emitter.string_return_uses.append(dict(
            routine=routine.name, capacity=spec[1], capacity_defaulted=routine.string_result_defaulted,
            line=line, column=column, expression_kind=operand.kind, evaluated_once=True, right_truncation=True))
    elif spec == ('VECTOR',):
        emitter.vector_return_uses.append(dict(
            routine=routine.name, line=line, column=column, expression_kind=operand.kind,
            independent_writable_copy=True))
    elif spec[0] == 'STRUCTURE':
        emitter.structure_return_uses.append(dict(
            routine=routine.name, type_name=spec[1], line=line, column=column,
            expression_kind=operand.kind, independent_writable_copy=True))
    elif spec[0] in POSITIONAL_VALUE_TYPES:
        row = dict(routine=routine.name, type_spec=spec, line=line, column=column,
                   expression_kind=operand.kind, independent_writable_copy=True)
        if emitter.mode == 'pythonic':
            row.update(source_type_spec=plan.source_schema, converted=plan.conversion in _POSITION_CONVERSIONS,
                       conversion_kind=plan.conversion or 'none')
        emitter.positional_return_uses.append(row)


def _record_value_argument(emitter, argument, site, plan, source):
    expected = plan.expected_schema
    kind = expected[0]
    position = _position(argument)
    pythonic = emitter.mode == 'pythonic'
    conversion = plan.conversion or 'none'
    if kind == 'ARRAY':
        emitter.features.add('writable ARRAY value argument')
        row = dict(**site, formal_spec=expected, source_spec=plan.bound_schema, **position,
                   expression_kind=argument.kind, evaluated_once=True, independent_writable_copy=True,
                   initialized_elements_required=True)
        if conversion in _ARRAY_CONVERSIONS:
            row.update(source_spec=source, converted=True, conversion_kind=conversion)
        if conversion in _PRESERVES_MISSING:
            row.update(initialized_elements_required=False, missing_data_preserved=True)
        emitter.array_value_uses.append(row)
    elif kind == 'STRING':
        emitter.features.add('writable STRING value argument' if pythonic else 'read-only STRING value argument')
        capacity = expected[1] if plan.bounded_string_value else 254
        emitter.string_value_uses.append(dict(
            **site, **position, expression_kind=argument.kind, evaluated_once=True,
            independent_writable_copy=pythonic, temporary_capacity=capacity if pythonic else None))
    elif kind == 'STRUCTURE':
        emitter.features.add('named STRUCTURE value argument')
        emitter.structure_value_uses.append(dict(
            **site, type_name=expected[1], **position, expression_kind=argument.kind, evaluated_once=True,
            independent_writable_copy=True))
    elif expected == ('VECTOR',):
        emitter.features.add('VECTOR value argument')
        emitter.vector_value_uses.append(dict(
            **site, **position, expression_kind=argument.kind, evaluated_once=True, independent_writable_copy=True))
    elif kind in POSITIONAL_VALUE_TYPES:
        emitter.features.add('exact positional value argument')
        row = dict(**site, type_spec=expected, **position, expression_kind=argument.kind, evaluated_once=True,
                   independent_writable_copy=True)
        if pythonic:
            row.update(source_type_spec=source, converted=conversion in _POSITION_CONVERSIONS,
                       conversion_kind=conversion)
        emitter.positional_value_uses.append(row)


def record_routine_binding(emitter, routine, formal, argument, plan, source, *, active_counter):
    if active_counter:
        emitter.features.add('read-only active FOR counter reference')
    site = _argument_site(emitter, routine, formal)
    if not plan.by_reference:
        _record_value_argument(emitter, argument, site, plan, source)
    kind = plan.expected_schema[0]
    if kind in ('STRING', 'ARRAY', *RECORD_TYPES, 'JOINTPOS'):
        emitter.features.add(kind + (' reference parameter' if plan.by_reference else ' value parameter'))
    emitter.features.add('parameter by reference' if plan.by_reference else 'parameter by value')
    if plan.guarded_string:
        emitter.features.add('runtime-checked bounded STRING forwarding')
        emitter.string_forward_uses.append(dict(
            **site, **_position(argument), source_type_spec=plan.bound_schema, target_type_spec=plan.expected_schema,
            alias_retained=True,
            validation='Existing routine entry requires matching concrete STRING capacity before callee body/frame allocation'))
    if plan.guarded_array:
        emitter.features.add('runtime-checked fixed ARRAY forwarding')
        emitter.array_forward_uses.append(dict(
            **site, **_position(argument), source_type_spec=plan.bound_schema, target_type_spec=plan.expected_schema,
            alias_retained=True,
            validation='Existing routine entry requires a matching concrete reference before callee body/frame allocation'))
