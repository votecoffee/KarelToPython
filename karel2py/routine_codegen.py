"""Generate routine frames, checked arguments, calls, and RETURN values."""
from .call_analysis import (
    check_byname_argument,
    check_return_operand,
    check_routine_call,
    check_routine_result,
    check_routine_value_storage,
    plan_routine_argument,
    validate_routine_argument,
)
from .call_reporting import (
    record_file_prefix,
    record_result_conversion,
    record_routine_binding,
    record_routine_conversion,
    record_routine_result,
    record_service_call,
    record_value_subfield,
)
from .compiler_language import INTEGRAL_TYPES, NARROW_TYPES, POSITIONAL_VALUE_TYPES
from .schema_conversion import DATA_AGGREGATE_CONVERTERS, MODEL_CONVERSIONS


class RoutineLowering:
    """Emit routine operations using the current expression and type scope."""

    def emit_routine_definitions(self):
        for routine in self.program.routines:
            self.current_routine = routine
            self.line()
            argument_names = [f'_argument_{i}' for i in range(len(routine.parameters))]
            signature = ', '.join(['self'] + argument_names)
            self.line(f'@_rt._with_numeric_mode({self.mode!r})')
            self.line(f'def _routine_{routine.name}({signature}):', routine.token)
            self.indent = 2
            self.line(f'self._state.tick({routine.token.line})')
            bindings = ', '.join(f'{token.value!r}: {arg}' for (token, _), arg in zip(routine.parameters, argument_names))
            self.line(f'self._state.enter_routine({routine.local_types!r}, {routine.token.line}, {{{bindings}}}, routine={routine.name!r})')
            self.line('try:')
            self.indent = 3
            if routine.external:
                self.line(f'return (yield from self._state.external_call({routine.external!r},{routine.name!r},[{", ".join(argument_names)}],{routine.return_type!r},{routine.token.line}))',routine.token)
            else:
                self.emit_body(routine.body)
            if routine.return_type and not routine.external:
                self.line(f'raise _rt.KarelRuntimeError("Function completed without RETURN", {routine.token.line})')
            self.indent = 2
            self.line('finally:')
            self.indent = 3
            self.line('self._state.leave_routine()')
            self.indent = 1
        self.current_routine = None

    def file_prefix_argument(self, argument, routine, formal, selected):
        code, container = self.file_prefix_reference_code(argument)
        record_file_prefix(self, routine, formal, argument, container, selected)
        return code, selected

    def check_for_call(self, token, routine=None):
        if self.active_counters:
            if self.mode == 'strict' and not self.has_fresh_active_counters():
                self.error('E_FOR_COUNTER', 'Routine calls inside FOR require every active counter to be a fresh routine-local variable', token)
            if self.mode == 'pythonic' and routine is not None:
                locals_only = {t.value for t, _ in self.current_routine.declarations} if self.current_routine else set()
                conflict = (self.named_active_counters() - locals_only) & routine.global_writes
                if conflict:
                    self.error('E_FOR_COUNTER', 'Routine may write active global FOR counter(s): ' + ', '.join(sorted(conflict)), token)
                aggregate_roots={root for root in self.named_active_counters()-locals_only if self.types[root][0] not in INTEGRAL_TYPES}
                if aggregate_roots and routine.name in self.external_write_routines:
                    self.error('E_FOR_COUNTER','External routine effects cannot prove active aggregate counter roots unchanged',token)
            if self.has_fresh_active_counters(): self.features.add('routine call inside FOR with fresh local counters')
            if self.mode == 'pythonic': self.features.add('routine call inside FOR with checked counter effects')

    def has_routine_call(self, expr):
        return expr.kind == 'call' and expr.value in self.routines or any(self.has_routine_call(x) for x in expr.args)

    def lower_byname_argument(self, operand, expected):
        self.check_for_call(operand.token)
        self.check_byname_counter(operand)
        program = self.require_type(operand.program, 'STRING')
        path = self.require_type(operand.path, 'STRING')
        self.check_byname_entry(operand.entry)
        reference, spec = self.reference(operand.entry)
        operand.check_entry_schema(spec, error=self.error)

        self.features.add('parameter by reference')
        record_service_call(self, 'BYNAME', operand.token)
        return f'self._state.byname_argument({expected!r},{program},{path},{reference},{operand.token.line})'

    def routine_call(self, expr):
        routine = self.routines[expr.value]
        pairs = check_routine_call(expr, routine, mode=self.mode, has_routine_call=self.has_routine_call, error=self.error)
        arguments = []
        for index, (argument, (formal, expected)) in enumerate(pairs):
            line = argument.token.line
            byname = check_byname_argument(argument, mode=self.mode, routines=self.routines, error=self.error)
            if byname is not None:
                arguments.append(self.lower_byname_argument(byname, expected))
                continue
            if self.is_position_read_only_access(argument) and not self.is_system_pose_path(argument):
                self.error('E_POSITION_READ_ONLY_ARG', 'Bare POSITION orientation arguments need read-only passing evidence; use an explicit scalar expression for a value', argument.token)
            is_reference, file_prefix = self.routine_argument_storage(argument)
            if is_reference:
                if file_prefix is None:
                    code, actual = self.reference(argument)
                else:
                    code, actual = self.file_prefix_argument(argument, routine, formal, file_prefix)
                if self.is_value_only_subfield(argument):
                    value, actual = self.expression(argument)
                    code = f'_rt.value_argument({expected!r}, {value}, {line})'
                    is_reference = False
                    association_type = self.access_type(argument.args[0])[0] if self.is_association_subfield(argument) else None
                    record_value_subfield(self, routine, formal, argument, association_type=association_type)
            else:
                value, actual = self.expression(argument)
                capture = check_routine_value_storage(expected, actual, argument.token, mode=self.mode, error=self.error)
                if capture is None:
                    code = f'_rt.value_argument({expected!r}, {value}, {line})'
                else:
                    if capture.needs_conversion:
                        value = self.path_conversion_value(expected, actual, value, argument.token, 'ARGUMENT')
                    actual = capture.value_schema
                    if capture.is_array:
                        code = f'_rt.collection_array_argument({expected!r},{value},{line},source_spec={actual!r})'
                        self.features.add('private logical collection ARRAY argument')
                    else:
                        code = f'_rt.collection_argument({expected!r},{value},{line},source_spec={actual!r})'
                        self.features.add('private logical scalar collection argument')
            source_schema = actual
            plan = plan_routine_argument(expected, actual, mode=self.mode, reference=is_reference)
            conversion = plan.conversion
            if conversion:
                value, _ = self.expression(argument)
                value = self.lower_interface_conversion('ARGUMENT', conversion, expected, actual, value, argument.token)
                if conversion in ('narrow_promotion', 'integer_to_real'):
                    code = f'_rt.value_argument({expected!r}, {value}, {line})'
                else:
                    code = f'_rt.value_argument({expected!r},{value},{line})'
            if conversion in MODEL_CONVERSIONS and self.current_routine:
                self.current_routine.may_services = True
            if conversion in MODEL_CONVERSIONS or conversion == 'cartesian':
                self.geometry_argument_conversions.setdefault(id(expr), {})[index] = conversion
            if conversion in DATA_AGGREGATE_CONVERTERS:
                declared = source_schema if conversion == 'record_schema' else None
                self.data_argument_conversions.setdefault(id(expr), {})[index] = (conversion, declared)
            record_routine_conversion(self, routine, formal, argument, plan, source_schema)
            active_counter = plan.by_reference and self.protection_root(argument) in self.active_counters
            validate_routine_argument(plan, expr.value, argument.token, mode=self.mode, active_counter=active_counter,
                                      writable_formal=formal.value in routine.parameter_writes, error=self.error)
            if not plan.by_reference and expected[0] == 'STRING':
                code = (f'_rt.value_argument({expected!r}, {value}, {line})' if plan.bounded_string_value
                        else f'_rt.string_value_argument({value}, {line})')
            record_routine_binding(self, routine, formal, argument, plan, source_schema, active_counter=active_counter)
            arguments.append(code)
        result=f'self._routine_{expr.value}({", ".join(arguments)})'
        return f'(yield from {result})' if self.cooperative else result

    def routine_return(self, operand, token):
        if self.active_counters:
            fresh = self.has_fresh_active_counters()
            if self.mode == 'strict' and not fresh:
                self.error('E_FOR_COUNTER', 'RETURN inside FOR requires every active counter to be a fresh routine-local variable', token)
            if fresh:
                self.features.add('RETURN from FOR with fresh local counters')
            if self.mode == 'pythonic':
                self.features.add('RETURN from FOR with counter cleanup')

        spec = self.current_routine.return_type
        check_return_operand(spec, operand, token, error=self.error)
        if spec is None:
            self.line('return', token)
            return

        value, source = self.expression(operand)
        plan = check_routine_result(spec, source, operand, token, mode=self.mode,
                                   compatible=self.compatible, error=self.error)
        if plan.collection is not None:
            self._lower_collection_return(value, plan, operand, token)
            return
        value = self.lower_interface_conversion('RETURN', plan.conversion, spec, source, value, token)
        if plan.conversion in MODEL_CONVERSIONS:
            self.current_routine.may_services = True
        if plan.conversion in MODEL_CONVERSIONS or plan.conversion == 'cartesian':
            self.geometry_return_conversions[id(operand)] = plan.conversion
        if plan.conversion in DATA_AGGREGATE_CONVERTERS:
            declared = source if plan.conversion == 'record_schema' else None
            self.data_return_conversions[id(operand)] = (plan.conversion, declared)
        record_result_conversion(self, token, plan)
        record_routine_result(self, token, operand, plan)
        self.line(f'return {self._checked_result_value(spec, value, token.line)}', token)

    def _lower_collection_return(self, value, plan, operand, token):
        spec, source, line = plan.declared_schema, plan.source_schema, token.line
        if plan.conversion:
            value = self.path_conversion_value(spec, source, value, operand.token, 'RETURN')
        if plan.collection == 'array':
            result = f'_rt.collection_array_result({spec!r},{value},{line},source_spec={plan.value_schema!r})'
            self.line(f'return {result}', token)
            self.features.add('logical collection ARRAY function result')
        else:
            if not plan.conversion:
                value = f'_rt.collection_source_value({spec!r},{value},{line},source_spec={source!r})'
            self.line(f'return {value}', token)
            self.features.add('logical scalar collection function result')

    def _checked_result_value(self, spec, value, line):
        if spec[0] == 'ARRAY':
            return f'_rt.array_result({spec!r}, {value}, {line})'
        if spec[0] == 'STRUCTURE':
            return f'_rt.structure_value({spec!r}, {value}, {line})'
        if self.mode != 'pythonic':
            if spec == ('VECTOR',):
                return f'_rt.vector_value({value}, {line})'
            if spec[0] in POSITIONAL_VALUE_TYPES:
                return f'_rt.positional_value({spec!r}, {value}, {line})'
        checked = f'_rt.checked({spec!r}, {value}, {line})'
        if self.mode == 'pythonic' and spec[0] in NARROW_TYPES:
            return f'_rt.require({checked}, {line})'
        return checked
