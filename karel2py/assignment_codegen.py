"""Generate scalar, ARRAY, and logical collection writes in source order."""
from . import extended as ex
from . import runtime as rt
from .assignment_analysis import (
    array_result_routine,
    check_assignment,
    check_prefix_assignment,
    collection_array_capture,
)
from .compiler_language import DATA_RECORD_TYPES
from .conversion_codegen import direct_schema_value
from .schema_conversion import MODEL_CONVERSIONS


class AssignmentLowering:
    """Emit RHS capture and receiver publication using checked schemas."""

    def lower_assignment(self, target, expr, token):
        line = token.line
        if (self.mode == 'pythonic' and target.kind == 'index' and target.args[0].kind == 'name'
                and target.args[0].value in ex.PORT_TYPES and target.args[0].value not in self.types):
            port = target.args[0].value
            if port not in ex.OUTPUT_PORTS:
                self.error('E_PORT_DIRECTION', 'Cannot assign an input port', target.token)
            value = self.require_type(expr, ex.PORT_TYPES[port])
            temp = self.fresh()
            self.line(f'{temp}={value}', token)
            if len(target.args) != 2:
                self.error('E_ARGUMENTS', 'Ports require one index', target.token)
            index = self.require_type(target.args[1], 'INTEGER')
            self.features.add('ports')
            self.line(f'self._state.port_write({port!r},{index},{temp},{line})', token)
            return

        self.check_assignment_target(target, expr)
        selected_target = target
        while selected_target.kind == 'group':
            selected_target = selected_target.args[0]
        if self.is_array_prefix_value(selected_target):
            if rt.collection_array_type(self.access_type(selected_target.args[0])):
                self.collection_array_assignment(target, expr, token)
            else:
                self.prefix_assignment(target, expr, token)
            return

        reference, target_type = self.reference(target)
        if target_type[0] == 'ARRAY' and rt.file_storage_type(target_type):
            self.error('E_FILE_ARRAY_VALUE', 'FILE ARRAY storage cannot be assigned; pass its reference', target.token)
        if self.mode == 'pythonic' and rt.collection_type(target_type):
            self.collection_assignment(target, expr, token)
            return
        if self.mode == 'pythonic' and rt.collection_array_type(target_type):
            self.collection_array_assignment(target, expr, token)
            return

        value, value_type = self.expression(expr, allow_array_result=True)
        formal_receiver = target_type[0] == 'ARRAY' and self.is_routine_formal(target)
        plan = check_assignment(target_type, value_type, token, mode=self.mode,
                                formal_receiver=formal_receiver, compatible=self.compatible, error=self.error)
        value = self._lower_assignment_conversion(plan, target, reference, value, token)
        result_routine = array_result_routine(expr, value_type, mode=self.mode)
        if result_routine is not None:
            self.features.add('direct ARRAY result assignment')
            self.array_result_assignments.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                      routine=result_routine, line=line, column=token.column,
                                                      target_kind=target.kind, target_type=target_type,
                                                      evaluated_once=True, runtime_exact_type_and_size=True))
        if target_type[0] == 'STRUCTURE':
            self.features.add('whole STRUCTURE assignment')
        if target_type[0] in DATA_RECORD_TYPES:
            self.features.add('whole ' + target_type[0] + ' data copy')
        if self.mode == 'pythonic':
            temporary = self.fresh()
            self.line(f'{temporary} = _rt.assignment_value({value}, {line})', token)
            value = temporary
        self.line(f'{reference}.set({value}, {line})', token)

    def _lower_assignment_conversion(self, plan, target, reference, value, token):
        target_type, value_type = plan.target_schema, plan.source_schema
        line = token.line
        if plan.conversion in MODEL_CONVERSIONS or plan.conversion == 'cartesian':
            self.geometry_assignment_conversions[id(target)] = (plan.conversion, target_type)
        if (receiver := plan.array_receiver) is not None:
            self._note_geometry_receiver(target, target_type, receiver)
            source_schema = f',source_spec={value_type!r}' if receiver.needs_source_schema else ''
            value=f'self._state.array_assignment_value({value},({reference}).spec,{line}{source_schema})'
            self.features.add('runtime ARRAY receiver schema')
            self.array_schema_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name,line=line,column=token.column,
                source_type_spec=value_type,target_type_spec=target_type,schema_change_kind='dynamic_receiver',
                evaluated_once=True,independent_value=True,actual_receiver_schema=True))
            if receiver.kinematic_array:
                self.current_routine.may_services=True;self.features.update(('extended services','kinematic ARRAY conversion'))
                self.kinematic_array_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name,line=line,column=token.column,
                    source_type_spec=value_type,target_type_spec=target_type,evaluated_once=True,independent_value=True,actual_receiver_schema=True))
            if receiver.kinematic_record:
                self.current_routine.may_services=True;self.features.update(('extended services','kinematic STRUCTURE conversion'))
                self.kinematic_record_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name,line=line,column=token.column,
                    source_type_spec=value_type,target_type_spec=target_type,conversion_kind='record_array',
                    evaluated_once=True,independent_value=True,actual_receiver_schema=True,geometry_preflight=True))
            if receiver.record_schema:
                self.record_schema_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name,line=line,column=token.column,
                    source_type_spec=value_type,target_type_spec=target_type,conversion_kind='record_array',
                    evaluated_once=True,independent_value=True,actual_receiver_schema=True))
        elif plan.conversion == 'real_integral':
            value = direct_schema_value(plan.conversion, target_type, value, line)
            self.features.add('checked REAL to integral assignment')
        elif plan.conversion == 'config_word':
            value=self.config_word_conversion(target_type,value_type,value,token,'ASSIGNMENT')
        elif plan.conversion == 'numeric_array':
            value = direct_schema_value(plan.conversion, target_type, value, line)
            self.features.add('numeric ARRAY conversion')
            self.numeric_array_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,source_type_spec=value_type,target_type_spec=target_type,
                evaluated_once=True,independent_value=True))
        elif plan.conversion == 'positional_array':
            value = direct_schema_value(plan.conversion, target_type, value, line)
            self.features.add('positional ARRAY conversion')
            self.positional_array_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,source_type_spec=value_type,target_type_spec=target_type,
                evaluated_once=True,independent_value=True))
        elif plan.conversion == 'kinematic_array':
            value=f'self._state.kinematic_array({target_type!r},{value},{line})'
            self.features.update(('extended services','kinematic ARRAY conversion'))
            if self.current_routine:self.current_routine.may_services=True
            self.kinematic_array_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,source_type_spec=value_type,target_type_spec=target_type,
                evaluated_once=True,independent_value=True))
        elif plan.conversion == 'kinematic_record':
            value=f'self._state.kinematic_record({target_type!r},{value},{line},source_spec={value_type!r})'
            self.features.update(('extended services','kinematic STRUCTURE conversion'))
            if self.current_routine:self.current_routine.may_services=True
            self.kinematic_record_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,source_type_spec=value_type,target_type_spec=target_type,
                conversion_kind=rt.kinematic_record_kind(target_type,value_type),evaluated_once=True,independent_value=True,geometry_preflight=True))
        elif plan.conversion == 'record_schema':
            value=f'_rt.convert_record_schema({target_type!r},{value},{line},source_spec={value_type!r})'
            self.features.add('source STRUCTURE schema conversion')
            self.record_schema_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,source_type_spec=value_type,target_type_spec=target_type,
                conversion_kind=rt.record_schema_kind(target_type,value_type),evaluated_once=True,independent_value=True))
        elif plan.conversion == 'array_schema':
            value = direct_schema_value(plan.conversion, target_type, value, line)
            self.features.add('source ARRAY schema conversion')
            self.array_schema_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,source_type_spec=value_type,target_type_spec=target_type,
                schema_change_kind=rt.array_schema_kind(target_type,value_type),evaluated_once=True,independent_value=True))
        elif plan.conversion == 'joint_width':
            value = direct_schema_value(plan.conversion, target_type, value, line)
            self.features.add('checked joint width conversion')
            self.joint_width_uses.append(dict(operation='ASSIGNMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,source_type_spec=value_type,target_type_spec=target_type,
                evaluated_once=True,independent_value=True))
        elif plan.conversion == 'kinematic':
            value=f'self._state.kinematic_assignment({target_type!r},{value},{line})'
            self.features.update(('extended services','kinematic assignment'))
            if self.current_routine: self.current_routine.may_services=True
            self.kinematic_assignment_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,source_type=value_type,target_type=target_type,target_kind=target.kind,
                evaluated_once=True,independent_value=True))
        elif plan.conversion == 'cartesian':
            value = f'_rt.convert_position({target_type!r}, {value}, {line})'
            self.features.add('POSITION/XYZWPR assignment conversion')
            self.position_conversion_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                      line=line, column=token.column, source_type=value_type[0], target_type=target_type[0],
                                                      target_kind=target.kind, evaluated_once=True, independent_value=True))
        return value

    def collection_assignment(self,target,expression,token):
        reference,expected=self.reference(target)
        value,actual=self.expression(expression)
        if expected[0] == 'PATH':
            self.path_assignment_schemas[id(target)] = expected
        source=self.fresh();line=token.line
        if expected==actual:
            value=f'_rt.collection_source_value({actual!r},{value},{line},source_spec={actual!r})'
        else:value=self.path_conversion_value(expected,actual,value,token,'ASSIGNMENT')
        self.line(f'{source}={value}',token)
        self.line(f'_rt.collection_assign({reference},{source},{line})',token)
        self.features.add('logical scalar collection source copy')

    def collection_array_assignment(self,target,expression,token):
        reference,expected=self.reference(target,allow_prefix=True,collection_prefix=True)
        value,actual=self.expression(expression,allow_array_result=True)
        source=self.fresh();line=token.line
        capture = collection_array_capture(expected, actual, formal_receiver=self.is_routine_formal(target))
        if capture == 'copy':
            value=f'_rt.collection_array_source_value({actual!r},{value},{line},source_spec={actual!r})'
        elif capture == 'receiver_conversion':
            self.line(f'{source}={value}',token)
            value=self.path_conversion_value(expected,actual,source,token,'ASSIGNMENT',receiver=f'({reference}).spec')
        else:
            self.path_array_conversion_schemas[id(target)] = expected
            value=self.path_conversion_value(expected,actual,value,token,'ASSIGNMENT')
        self.line(f'{source}={value}',token)
        self.line(f'_rt.collection_array_assign({reference},{source},{line})',token)
        self.features.add('logical collection ARRAY source copy')

    def _note_geometry_receiver(self, target, schema, receiver):
        if receiver.needs_geometry:
            conversion = 'kinematic_record' if receiver.kinematic_record else 'kinematic_array'
            self.geometry_assignment_conversions[id(target)] = (conversion, schema, True)

    def prefix_assignment(self,target,expression,token):
        reference,expected=self.reference(target,allow_prefix=True)
        value,actual=self.expression(expression,allow_array_result=True)
        receiver = check_prefix_assignment(expected, actual, token, compatible=self.compatible, error=self.error)
        self._note_geometry_receiver(target, expected, receiver)
        source=self.fresh();captured=self.fresh();line=token.line
        self.line(f'{source} = _rt.assignment_value({value},{line})',token)
        self.line(f'{captured} = {reference}',token)
        schema = f',source_spec={actual!r}' if receiver.needs_source_schema else ''
        self.line(f'{captured}.set(self._state.array_assignment_value({source},{captured}.spec,{line}{schema}),{line})',token)
        if receiver.needs_geometry:
            self.features.add('extended services')
            if self.current_routine:self.current_routine.may_services=True
        self.features.add('statement ARRAY prefix assignment')
