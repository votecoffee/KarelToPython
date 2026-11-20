"""Type-check expressions and dispatch value lowering."""
from .compiler_language import (
    BUILTINS,
    BUILTIN_PROCEDURES,
    CONFIG_TEXT_PROCEDURES,
    CONTROLLER_NAMES,
    INTEGRAL_TYPES,
    MULTI_OUTPUT_PROCEDURES,
    NARROW_TYPES,
    PREDEFINED_CONSTANTS,
    PYTHONIC_CONSTRUCTORS,
    REGISTER_PROCEDURES,
    TIMER_FUNCTIONS,
    TIME_TEXT_PROCEDURES,
)
from .operator_types import POSE_OPERANDS, binary_result, operand_type, unary_result
from . import extended as ex
from . import runtime as rt


class ExpressionLowering:
    """Lower expressions against the current checked program and emitter scope."""

    def geometry_operand(self,code,spec,token,operation):
        if self.mode=='pythonic' and spec==('VECTOR',) and operation in (':','INV','FRAME'):
            return f'_rt.vector_value({code},{token.line})'
        if self.mode=='pythonic' and spec[0]=='JOINTPOS':
            self.features.update(('extended services','joint geometry'))
            if self.current_routine: self.current_routine.may_services=True
            self.joint_geometry_uses.append(dict(operation=operation,body=self.current_routine.name if self.current_routine else self.program.name,
                line=token.line,column=token.column,source_type=spec,target_type=('XYZWPREXT',),evaluated_once=True,independent_value=True))
            return f'self._state.geometry_value({code},{spec!r},{token.line})'
        return f'_rt.frame_value({code}, {token.line}, expected={spec!r})'

    def path_conversion_value(self,expected,actual,value,token,operation,*,receiver=None):
        array=expected[0]=='ARRAY'
        layout=rt.path_array_conversion_layout(expected,actual) if array else ex.path_conversion_layout(expected,actual,model=True)
        if layout is None:self.error('E_TYPE','Logical collection values require compatible PATH layouts and matching shapes',token)
        if 'kinematic' in layout:
            self.features.add('extended services')
            if self.current_routine:self.current_routine.may_services=True
        self.features.add('source PATH schema conversion')
        self.path_schema_uses.append(dict(operation=operation,body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line,column=token.column,source_type_spec=actual,target_type_spec=expected,
            model_backed='kinematic' in layout,evaluated_once=True,independent_value=True))
        method='path_array_source_value' if array else 'path_source_value'
        receiver=repr(expected) if receiver is None else receiver
        return f'self._state.{method}({receiver},{value},{token.line},source_spec={actual!r})'

    def config_word_conversion(self,target,source,value,token,operation):
        self.features.add('portable CONFIG word conversion')
        self.config_word_uses.append(dict(operation=operation,body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line,column=token.column,source_type_spec=source,target_type_spec=target,
            conversion_kind=rt.config_word_kind(target,source),evaluated_once=True,independent_value=True))
        return f'_rt.config_word_value({target!r},{value},{token.line})'

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
            # The source manual requires the named predefined minimum.
            if self.is_minimum_literal(expr):
                self.error('E_MININT_LITERAL', 'The manual requires MININT instead of the INTEGER literal -2147483648', expr.token)
            value, spec = self.expression(expr.args[0])
            result_type = unary_result(expr.value, spec, mode=self.mode)
            if result_type is None: self.error('E_TYPE', 'Invalid unary operand type', expr.token)
            self.features.add('unary ' + expr.value)
            return f'_rt.unary({expr.value!r}, {value}, {line})', result_type
        if expr.kind == 'binary':
            if self.mode == 'strict' and self.has_external_effect_call(expr):
                self.error('E_EVALUATION_ORDER', 'Function calls that may write globals/reference parameters, delay, request output or abort are blocked inside operator expressions', expr.token)
            left, lt = self.expression(expr.args[0])
            right, right_type = self.expression(expr.args[1])
            lt, right_type = operand_type(lt), operand_type(right_type)
            op = expr.value
            if op == ':':
                relative_kinds = (*POSE_OPERANDS, 'VECTOR')
                result_type = None
                if self.mode == 'pythonic' and lt[0] in relative_kinds and right_type[0] in relative_kinds:
                    result_type = self.relative_result_type([lt, right_type], expr.token)
            else:
                result_type = binary_result(op, lt, right_type, mode=self.mode)
            if (op in ('AND', 'OR') and self.mode == 'strict' and lt[0] == 'BOOLEAN'
                    and right_type[0] != 'VECTOR' and any(self.has_routine_call(x) for x in expr.args)):
                self.error('E_EVALUATION_ORDER', 'Boolean expressions containing routine calls are not implemented', expr.token)
            if result_type is None: self.error('E_TYPE', f'Unsupported {lt[0]} {op} {right_type[0]}', expr.token)
            if op == '>=<':
                self.position_comparison_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                          line=line, column=expr.token.column, operand_types=[lt[0],right_type[0]],
                                                          result_type='BOOLEAN', evaluated_once=True, operands_copied=True))
            elif op == ':':
                self.frame_operation_uses.append(dict(operation=':', body=self.current_routine.name if self.current_routine else self.program.name,
                                                      line=line, column=expr.token.column, operand_types=[lt[0],right_type[0]],
                                                      result_type=result_type[0], evaluated_once=True, operands_copied=True))
            elif 'VECTOR' in (lt[0], right_type[0]):
                self.features.add('VECTOR operator ' + op)
            self.features.add('operator ' + op)
            if self.mode == 'pythonic':
                if lt[0] == 'BOOLEAN' and op in ('AND', 'OR'):
                    self.short_circuit_expressions.add(id(expr))
                    return f'(_rt.boolean({left}, {line}) {op.lower()} _rt.boolean({right}, {line}))', result_type
                # Capture mutable values before a later operand can change them.
                if lt == ('VECTOR',): left = f'_rt.vector_value({left}, {line})'
                if right_type == ('VECTOR',): right = f'_rt.vector_value({right}, {line})'
                if op in (':','>=<'):
                    if lt!=('VECTOR',):left = self.geometry_operand(left,lt,expr.args[0].token,op)
                    if right_type!=('VECTOR',):right = self.geometry_operand(right,right_type,expr.args[1].token,op)
                if op == '>=<':
                    return f'_rt.positions_close({left}, {right}, self._state.pose_tolerance, {line}, external_tolerance=self._state.external_tolerance)', result_type
            return f'_rt.binary({op!r}, {left}, {right}, {line})', result_type
        if expr.kind == 'call':
            if self.mode=='pythonic' and expr.value in ex.FUNCTIONS and expr.value not in self.routines:
                return self.service_call(expr),ex.FUNCTIONS[expr.value][1]
            if self.mode=='pythonic' and expr.value in ex.PROCEDURES and expr.value not in self.routines:
                self.error('E_PROCEDURE_RESULT','Service procedures have no expression result',expr.token)
            if self.active_counters and expr.value in self.routines:
                self.check_for_call(expr.token, self.routines[expr.value])
            if self.mode == 'pythonic' and expr.value in TIMER_FUNCTIONS and expr.value not in self.routines:
                return self.microsecond_timer(expr), ('INTEGER',)
            if (expr.value in BUILTIN_PROCEDURES or expr.value in MULTI_OUTPUT_PROCEDURES
                    or self.mode == 'pythonic' and expr.value in CONFIG_TEXT_PROCEDURES | TIME_TEXT_PROCEDURES | REGISTER_PROCEDURES and expr.value not in self.routines):
                self.error('E_PROCEDURE_RESULT', 'Conversion procedures have an output argument, not an expression result', expr.token)
            if expr.value in BUILTINS or (self.mode == 'pythonic' and expr.value in PYTHONIC_CONSTRUCTORS and expr.value not in self.routines):
                return self.builtin_call(expr)
            if expr.value not in self.routines:
                code = 'E_CONTROLLER' if expr.value in CONTROLLER_NAMES else 'E_CALL'
                self.error(code, f'Unknown or unsupported call {expr.value}', expr.token)
            routine = self.routines[expr.value]
            if not routine.return_type: self.error('E_TYPE', 'Procedure cannot be used as an expression', expr.token)
            if self.mode == 'strict' and routine.return_type[0] == 'ARRAY' and not allow_array_result:
                self.error('E_ARRAY_RESULT_CONTEXT', 'An ARRAY-valued function call is supported only as the complete value of a direct assignment', expr.token)
            if routine.return_type[0] == 'ARRAY':
                self.array_function_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                     routine=expr.value, line=line, column=expr.token.column,
                                                     result_spec=routine.return_type, evaluated_once=True, independent_copy=True))
            self.features.add('routine function call')
            return self.routine_call(expr), routine.return_type
        self.error('E_INTERNAL', 'Unexpected expression node', expr.token)

    def require_type(self, expr, expected):
        code, spec = self.expression(expr)
        if expected == 'INTEGER' and spec[0] in NARROW_TYPES: return f'_rt.integer({code}, {expr.token.line})'
        if expected == 'REAL' and spec[0] in INTEGRAL_TYPES: return f'_rt.real({code}, {expr.token.line})'
        if spec[0] != expected: self.error('E_TYPE', f'Expected {expected}, found {spec[0]}', expr.token)
        return code
