"""Emit checked conversions for assignments and routine value interfaces."""
from . import extended as ex
from . import runtime as rt


_DIRECT_CONVERSIONS = {
    'real_integral': 'real_integral_value',
    'numeric_array': 'convert_numeric_array',
    'positional_array': 'convert_positional_array',
    'array_schema': 'convert_array_schema',
    'joint_width': 'convert_joint_width',
}


def direct_schema_value(conversion, target, value, line):
    helper = _DIRECT_CONVERSIONS[conversion]
    return f'_rt.{helper}({target!r},{value},{line})'


class SchemaConversionLowering:
    """Emit conversion calls after the caller has checked source and target schemas."""

    def path_conversion_value(self, expected, actual, value, token, operation, *, receiver=None):
        array = expected[0] == 'ARRAY'
        layout = (rt.path_array_conversion_layout(expected, actual) if array
                  else ex.path_conversion_layout(expected, actual, model=True))
        if layout is None:
            self.error('E_TYPE', 'Logical collection values require compatible PATH layouts and matching shapes', token)
        model_backed = 'kinematic' in layout
        if model_backed:
            self.features.add('extended services')
            if self.current_routine:
                self.current_routine.may_services = True
        self.features.add('source PATH schema conversion')
        self.path_schema_uses.append(dict(
            operation=operation, body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line, column=token.column, source_type_spec=actual, target_type_spec=expected,
            model_backed=model_backed, evaluated_once=True, independent_value=True))
        method = 'path_array_source_value' if array else 'path_source_value'
        receiver = repr(expected) if receiver is None else receiver
        return f'self._state.{method}({receiver},{value},{token.line},source_spec={actual!r})'

    def config_word_conversion(self, target, source, value, token, operation):
        self.features.add('portable CONFIG word conversion')
        self.config_word_uses.append(dict(
            operation=operation, body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line, column=token.column, source_type_spec=source, target_type_spec=target,
            conversion_kind=rt.config_word_kind(target, source), evaluated_once=True, independent_value=True))
        return f'_rt.config_word_value({target!r},{value},{token.line})'

    def lower_interface_conversion(self, operation, conversion, target, source, value, token):
        line = token.line
        if conversion in _DIRECT_CONVERSIONS:
            return direct_schema_value(conversion, target, value, line)
        if conversion == 'config_word':
            return self.config_word_conversion(target, source, value, token, operation)
        if conversion == 'kinematic_array':
            return f'self._state.kinematic_array({target!r},{value},{line},kind="{operation}")'
        if conversion == 'kinematic_record':
            return f'self._state.kinematic_record({target!r},{value},{line},kind="{operation}",source_spec={source!r})'
        if conversion == 'record_schema':
            return f'_rt.convert_record_schema({target!r},{value},{line},source_spec={source!r})'
        if conversion == 'kinematic':
            result = ',result=True' if operation == 'RETURN' else ''
            return f'self._state.kinematic_interface({target!r},{value},{line}{result})'
        if conversion == 'cartesian' and operation == 'RETURN':
            return f'_rt.convert_position({target!r},{value},{line})'
        return value
