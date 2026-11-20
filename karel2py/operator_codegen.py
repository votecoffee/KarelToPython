"""Emit checked unary, binary, and relative pose expressions."""
from .operator_types import POSE_OPERANDS, binary_result, operand_type, unary_result


class OperatorLowering:
    """Apply source operand rules before emitting runtime evaluation."""

    def geometry_operand(self, code, spec, token, operation):
        if self.mode == 'pythonic' and spec == ('VECTOR',) and operation in (':', 'INV', 'FRAME'):
            return f'_rt.vector_value({code},{token.line})'
        if self.mode == 'pythonic' and spec[0] == 'JOINTPOS':
            self.features.update(('extended services', 'joint geometry'))
            if self.current_routine:
                self.current_routine.may_services = True
            self.joint_geometry_uses.append(dict(
                operation=operation, body=self.current_routine.name if self.current_routine else self.program.name,
                line=token.line, column=token.column, source_type=spec, target_type=('XYZWPREXT',),
                evaluated_once=True, independent_value=True))
            return f'self._state.geometry_value({code},{spec!r},{token.line})'
        return f'_rt.frame_value({code}, {token.line}, expected={spec!r})'

    def lower_unary(self, expr):
        token = expr.token
        if self.is_minimum_literal(expr):
            self.error('E_MININT_LITERAL', 'The manual requires MININT instead of the INTEGER literal -2147483648', token)
        value, spec = self.expression(expr.args[0])
        result_type = unary_result(expr.value, spec, mode=self.mode)
        if result_type is None:
            self.error('E_TYPE', 'Invalid unary operand type', token)
        self.features.add('unary ' + expr.value)
        return f'_rt.unary({expr.value!r}, {value}, {token.line})', result_type

    def _binary_result_type(self, expr, left, right):
        operator = expr.value
        if operator != ':':
            return binary_result(operator, left, right, mode=self.mode)
        relative_kinds = (*POSE_OPERANDS, 'VECTOR')
        if self.mode == 'pythonic' and left[0] in relative_kinds and right[0] in relative_kinds:
            return self.relative_result_type([left, right], expr.token)
        return None

    def _record_binary_operator(self, expr, left, right, result_type):
        operator = expr.value
        if operator in (':', '>=<'):
            use = dict(body=self.current_routine.name if self.current_routine else self.program.name,
                       line=expr.token.line, column=expr.token.column, operand_types=[left[0], right[0]],
                       result_type=result_type[0], evaluated_once=True, operands_copied=True)
            if operator == ':':
                self.frame_operation_uses.append(dict(operation=operator, **use))
            else:
                self.position_comparison_uses.append(use)
        elif 'VECTOR' in (left[0], right[0]):
            self.features.add('VECTOR operator ' + operator)
        self.features.add('operator ' + operator)

    def _capture_binary_operand(self, code, spec, token, operand_token, operator):
        if spec == ('VECTOR',):
            return f'_rt.vector_value({code}, {token.line})'
        if operator in (':', '>=<'):
            return self.geometry_operand(code, spec, operand_token, operator)
        return code

    def lower_binary(self, expr):
        token, operator = expr.token, expr.value
        if self.mode == 'strict' and self.has_external_effect_call(expr):
            self.error('E_EVALUATION_ORDER', 'Function calls that may write globals/reference parameters, delay, request output or abort are blocked inside operator expressions', token)
        left_expr, right_expr = expr.args
        left, left_type = self.expression(left_expr)
        right, right_type = self.expression(right_expr)
        left_type, right_type = operand_type(left_type), operand_type(right_type)
        result_type = self._binary_result_type(expr, left_type, right_type)
        boolean_branch = operator in ('AND', 'OR') and left_type[0] == 'BOOLEAN'
        if (boolean_branch and self.mode == 'strict' and right_type[0] != 'VECTOR'
                and any(self.has_routine_call(argument) for argument in expr.args)):
            self.error('E_EVALUATION_ORDER', 'Boolean expressions containing routine calls are not implemented', token)
        if result_type is None:
            self.error('E_TYPE', f'Unsupported {left_type[0]} {operator} {right_type[0]}', token)
        self._record_binary_operator(expr, left_type, right_type, result_type)

        if self.mode == 'pythonic':
            if boolean_branch:
                self.short_circuit_expressions.add(id(expr))
                return f'(_rt.boolean({left}, {token.line}) {operator.lower()} _rt.boolean({right}, {token.line}))', result_type
            # Capture mutable values at their operand sites before later arguments run.
            left = self._capture_binary_operand(left, left_type, token, left_expr.token, operator)
            right = self._capture_binary_operand(right, right_type, token, right_expr.token, operator)
            if operator == '>=<':
                return (f'_rt.positions_close({left}, {right}, self._state.pose_tolerance, {token.line}, '
                        'external_tolerance=self._state.external_tolerance)'), result_type
        return f'_rt.binary({operator!r}, {left}, {right}, {token.line})', result_type
