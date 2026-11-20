"""Resolve value-producing calls before delegating operand generation."""
from . import extended as ex
from .compiler_language import (
    BUILTINS,
    BUILTIN_PROCEDURES,
    CONFIG_TEXT_PROCEDURES,
    CONTROLLER_NAMES,
    MULTI_OUTPUT_PROCEDURES,
    PYTHONIC_CONSTRUCTORS,
    REGISTER_PROCEDURES,
    TIMER_FUNCTIONS,
    TIME_TEXT_PROCEDURES,
)


class FunctionCallLowering:
    """Select a function using the active source mode and routine namespace."""

    def lower_function_call(self, expr, *, allow_array_result=False):
        name, token = expr.value, expr.token
        routine = self.routines.get(name)
        unshadowed_pythonic = self.mode == 'pythonic' and routine is None
        if unshadowed_pythonic:
            if name in ex.FUNCTIONS:
                return self.service_call(expr), ex.FUNCTIONS[name][1]
            if name in ex.PROCEDURES:
                self.error('E_PROCEDURE_RESULT', 'Service procedures have no expression result', token)
        if self.active_counters and routine is not None:
            self.check_for_call(token, routine)
        if unshadowed_pythonic and name in TIMER_FUNCTIONS:
            return self.microsecond_timer(expr), ('INTEGER',)
        if (name in BUILTIN_PROCEDURES or name in MULTI_OUTPUT_PROCEDURES
                or unshadowed_pythonic and name in CONFIG_TEXT_PROCEDURES | TIME_TEXT_PROCEDURES | REGISTER_PROCEDURES):
            self.error('E_PROCEDURE_RESULT', 'Conversion procedures have an output argument, not an expression result', token)
        if name in BUILTINS or (unshadowed_pythonic and name in PYTHONIC_CONSTRUCTORS):
            return self.builtin_call(expr)
        if routine is None:
            code = 'E_CONTROLLER' if name in CONTROLLER_NAMES else 'E_CALL'
            self.error(code, f'Unknown or unsupported call {name}', token)
        result = routine.return_type
        if not result:
            self.error('E_TYPE', 'Procedure cannot be used as an expression', token)
        if result[0] == 'ARRAY':
            if self.mode == 'strict' and not allow_array_result:
                self.error('E_ARRAY_RESULT_CONTEXT', 'An ARRAY-valued function call is supported only as the complete value of a direct assignment', token)
            self.array_function_uses.append(dict(
                body=self.current_routine.name if self.current_routine else self.program.name,
                routine=name, line=token.line, column=token.column, result_spec=result,
                evaluated_once=True, independent_copy=True))
        self.features.add('routine function call')
        return self.routine_call(expr), result
