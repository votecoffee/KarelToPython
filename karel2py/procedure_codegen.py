"""Dispatch procedure statements to the appropriate call generator."""
from . import extended as ex
from .compiler_language import (
    BUILTIN_PROCEDURES,
    CONFIG_TEXT_PROCEDURES,
    JOINT_PROCEDURES,
    REGISTER_PROCEDURES,
    TIME_TEXT_PROCEDURES,
)


class ProcedureLowering:
    """Select a procedure using the source mode and routine namespace."""

    def lower_procedure_statement(self, stmt):
        self.line(self._procedure_code(stmt.args[0], stmt.token), stmt.token)

    def _procedure_code(self, expr, token):
        name = expr.value
        routine = self.routines.get(name)
        if self.mode == 'pythonic' and routine is None:
            if name in ex.PROCEDURES:
                return self.service_call(expr)
            if name in REGISTER_PROCEDURES:
                return self.numeric_register(expr)
            if name in TIME_TEXT_PROCEDURES:
                return self.time_text_conversion(expr)
            if name in CONFIG_TEXT_PROCEDURES:
                return self.config_text_conversion(expr)
        if name in JOINT_PROCEDURES:
            return self.joint_conversion(expr)
        if name == 'UNPOS':
            return self.unpos_procedure(expr)
        if name in BUILTIN_PROCEDURES:
            return self.conversion_procedure(expr)
        if routine is None:
            self.error('E_CALL', f'Unknown or unsupported procedure {name}', token)
        if routine.return_type:
            self.error('E_CALL', 'Statement calls require procedures', token)
        self.check_for_call(token, routine)
        return self.routine_call(expr)
