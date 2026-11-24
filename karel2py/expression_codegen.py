"""Type-check expressions and dispatch value lowering."""
from .compiler_language import INTEGRAL_TYPES, NARROW_TYPES, PREDEFINED_CONSTANTS
from . import runtime as rt


class ExpressionLowering:
    """Lower expressions against the current checked program and emitter scope."""

    def expression(self, expr, raw=False, *, allow_array_result=False, collection_io=False):
        if expr.kind == 'system_selection':
            return self.lower_system_selection(expr)
        pose = expr if expr.kind == 'system_pose' else self.system_axis_root(expr)
        if pose is not None:
            return self.lower_system_pose(expr, pose)
        if expr.kind=='motion_event':
            return f'self._state.execution.require("motion",{expr.token.line}).condition(self._state,{expr.value},{expr.token.line})',('BOOLEAN',)
        if expr.kind=='captured': return expr.value
        if expr.kind=='event':
            number=self.require_type(expr.args[0],'INTEGER'); key=(expr.token.line,expr.token.column)
            return f'_rt.event_condition(self._state,{number},{key!r},{expr.token.line})',('BOOLEAN',)
        if expr.kind=='semaphore':
            number=self.require_type(expr.args[0],'INTEGER'); self.features.add('SEMAPHORE condition')
            return f'(self._state.execution.require("semaphores",{expr.token.line}).value({number},{expr.token.line})>0)',('BOOLEAN',)
        if expr.kind=='error_condition':
            number=self.require_type(expr.args[0],'INTEGER') if expr.args else 'None'
            self.features.add('ERROR condition')
            return f'_rt.error_condition(self._state,{number},{(expr.token.line,expr.token.column)!r},{expr.token.line})',('BOOLEAN',)
        if expr.kind=='edge':
            value=self.require_type(expr.args[0],'BOOLEAN'); key=(expr.token.line,expr.token.column)
            return f'_rt.edge_condition(self._state,{key!r},{value},{expr.value!r},{expr.token.line})',('BOOLEAN',)
        if expr.kind == 'program_pause':
            number = self.require_type(expr.args[0], 'INTEGER')
            site = (expr.token.line, expr.token.column)
            self.features.add('qualified PAUSE condition')
            return f'_rt.program_pause_condition(self._state,{number},{site!r},{expr.token.line})', ('BOOLEAN',)
        if expr.kind=='task_event':
            if expr.value=='PAUSE': return 'self._state._pause_requested',('BOOLEAN',)
            if expr.value=='ABORT': return 'self._state._abort_requested',('BOOLEAN',)
            return f'_rt.lifecycle_condition(self._state,{expr.value!r},{(expr.token.line,expr.token.column)!r})',('BOOLEAN',)
        line = expr.token.line
        if expr.kind == 'group':
            return self.expression(expr.args[0], raw=raw, collection_io=collection_io)
        if expr.kind == 'real_literal':
            try: rt.real_literal(expr.value, line)
            except rt.KarelRuntimeError as exc: self.error('E_REAL_LITERAL', str(exc), expr.token)
            self.features.add('REAL literal' if self.mode == 'pythonic' else 'exact REAL literal')
            return f'_rt.real_literal({expr.value!r}, {line})', ('REAL',)
        if expr.kind == 'predefined':
            value = PREDEFINED_CONSTANTS[expr.value]
            if type(value) is bool: return repr(value), ('BOOLEAN',)
            if type(value) is str: return repr(value), ('STRING',len(value))
            return f'_rt.integer({value}, {line})', ('INTEGER',)
        if expr.kind == 'literal':
            spec = ('BOOLEAN',) if type(expr.value) is bool else ('INTEGER',) if type(expr.value) is int else ('STRING', len(expr.value))
            code = repr(expr.value)
            # Integer checks happen at every numeric literal except -2**31 handled below.
            if spec[0] == 'INTEGER':
                if not -2147483648 <= expr.value <= 2147483647:
                    self.error('E_LITERAL', 'INTEGER literal outside signed 32-bit range', expr.token)
                code = f'_rt.integer({code}, {line})'
            return code, spec
        if expr.kind in ('name', 'field', 'index', 'using_ref'):
            return self.lower_storage_read(expr, raw=raw, collection_io=collection_io)
        if expr.kind == 'unary':
            return self.lower_unary(expr)
        if expr.kind == 'binary':
            return self.lower_binary(expr)
        if expr.kind == 'call':
            return self.lower_function_call(expr, allow_array_result=allow_array_result)
        self.error('E_INTERNAL', 'Unexpected expression node', expr.token)

    @staticmethod
    def bind_condition_temporary(term, temporary, spec, originals):
        originals.append((term, term.kind, term.value, term.args))
        term.kind, term.value, term.args = 'captured', (temporary, spec), []

    @staticmethod
    def restore_condition_terms(originals):
        # Keep source operands and operator identities for input discovery.
        for term, kind, value, args in originals:
            term.kind, term.value, term.args = kind, value, args

    def emit_condition_capture(self, term, originals):
        code, spec = self.expression(term.args[0])
        if term.kind == 'repeat_eval':
            self.repeat_capture_types[id(term)] = spec[0]
        temporary = self.fresh()
        self.line(f'{temporary} = _rt.assignment_value({code}, {term.token.line})', term.token)
        self.bind_condition_temporary(term, temporary, spec, originals)
        return temporary

    def require_type(self, expr, expected):
        code, spec = self.expression(expr)
        if expected == 'INTEGER' and spec[0] in NARROW_TYPES: return f'_rt.integer({code}, {expr.token.line})'
        if expected == 'REAL' and spec[0] in INTEGRAL_TYPES: return f'_rt.real({code}, {expr.token.line})'
        if spec[0] != expected: self.error('E_TYPE', f'Expected {expected}, found {spec[0]}', expr.token)
        return code
