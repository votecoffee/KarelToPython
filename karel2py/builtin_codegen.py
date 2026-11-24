"""Emit checked built-in functions and their operand and result metadata."""
from . import runtime as rt
from .compiler_language import BUILTIN_SIGNATURES, DATA_RECORD_TYPES, NARROW_TYPES, PYTHONIC_CONSTRUCTORS


class BuiltinFunctionLowering:
    """Lower built-in operands in source order using the active scope."""

    def builtin_call(self, expr):
        name = expr.value
        if name in PYTHONIC_CONSTRUCTORS and self.mode == 'strict':
            self.error('E_CALL', f'{name} construction is outside the preserved conservative subset', expr.token)
        if name == 'UNINIT':
            return self._builtin_uninit(expr)
        if name == 'ABS':
            return self._builtin_abs(expr)
        if name == 'ARRAY_LEN':
            return self._builtin_array_len(expr)
        if name == 'POS':
            return self._builtin_pos(expr)
        if name in rt.POSITION_AXIS_FUNCTIONS:
            return self._builtin_pose_axis(expr)
        if name in ('INV', 'FRAME'):
            return self._builtin_frame(expr)
        return self._builtin_signature(expr)

    def _builtin_result(self, expr, codes, result_type):
        self.features.add(expr.value)
        return f'_rt.builtin({expr.value!r}, [{", ".join(codes)}], {expr.token.line})', result_type

    def _builtin_uninit(self, expr):
        if len(expr.args) != 1:
            self.error('E_ARGUMENTS', 'UNINIT requires exactly one argument', expr.token)
        argument = expr.args[0]
        grouped = argument.kind == 'group'
        if self.mode == 'pythonic':
            while argument.kind == 'group':
                argument = argument.args[0]
        captured_file = self.mode == 'pythonic' and argument.kind == 'captured' and argument.value[1] == ('FILE',)
        if argument.kind not in ('name', 'index', 'field') and not captured_file:
            self.error('E_ARGUMENTS', 'UNINIT requires variable, field or array-element storage', expr.token)
        code, spec = self.expression(argument, raw=True)
        if spec[0] == 'BYTE':
            self.error('E_BYTE_UNINIT', 'BYTE initialization queries are not implemented; the manual specifies no uninitialized checking for BYTE', argument.token)
        supported = ('INTEGER', 'SHORT', 'BOOLEAN', 'REAL', 'STRING', 'JOINTPOS')
        if self.mode == 'pythonic':
            supported += (*DATA_RECORD_TYPES, 'FILE', 'QUEUE_TYPE')
        if spec[0] not in supported:
            self.error('E_TYPE', 'Invalid UNINIT argument type', expr.token)
        if self.root_name(argument) in self.visible_constants():
            self.error('E_ARGUMENTS', 'UNINIT requires a variable, not a constant', expr.token)
        self.initialization_query_uses.append(dict(
            body=self.current_routine.name if self.current_routine else self.program.name,
            line=expr.token.line, column=expr.token.column, operand_type=spec, storage_kind=argument.kind,
            grouped=grouped, evaluated_once=True))
        if spec in (('FILE',), ('QUEUE_TYPE',)):
            self.features.add('UNINIT')
            method = 'file_uninit' if spec == ('FILE',) else 'queue_uninit'
            return f'_rt.{method}({code},{expr.token.line})', ('BOOLEAN',)
        return self._builtin_result(expr, [code], ('BOOLEAN',))

    def _builtin_abs(self, expr):
        if len(expr.args) != 1:
            self.error('E_ARGUMENTS', 'ABS requires exactly one argument', expr.token)
        code, result_type = self.expression(expr.args[0])
        if result_type[0] in NARROW_TYPES:
            result_type = ('INTEGER',)
        if result_type[0] not in ('INTEGER', 'REAL'):
            self.error('E_TYPE', 'ABS requires INTEGER or REAL', expr.token)
        return self._builtin_result(expr, [code], result_type)

    def _builtin_array_len(self, expr):
        has_dimension = self.mode == 'pythonic' and len(expr.args) == 2
        if len(expr.args) != 1 and not has_dimension:
            message = ('ARRAY_LEN requires an ARRAY and optional dimension' if self.mode == 'pythonic'
                       else 'ARRAY_LEN requires exactly one argument')
            self.error('E_ARGUMENTS', message, expr.token)
        code, spec = self.expression(expr.args[0], borrow_file_prefix=True)
        if spec[0] != 'ARRAY':
            self.error('E_TYPE', 'ARRAY_LEN requires ARRAY', expr.token)
        if self.mode == 'strict' and len(rt.array_dimensions(spec)) != 1:
            self.error('E_ARRAY_LEN', 'ARRAY_LEN on multidimensional arrays needs dimension-count semantics; use explicit dimensions', expr.token)
        codes = [code]
        if has_dimension:
            codes.append(self.require_type(expr.args[1], 'INTEGER'))
        return self._builtin_result(expr, codes, ('INTEGER',))

    def _builtin_pos(self, expr):
        result_type = self.pos_call_result_type(expr)
        extended = result_type == ('XYZWPREXT',)
        signature = BUILTIN_SIGNATURES['POS'][0]
        if extended:
            signature += ('REAL',) * 3
        codes = [self.require_type(argument, expected) for argument, expected in zip(expr.args, signature)]
        order = ['x', 'y', 'z', 'w', 'p', 'r', 'c']
        if extended:
            codes[6] = f"_rt.positional_value(('CONFIG',),{codes[6]},{expr.args[6].token.line})"
            order.extend(['ext1', 'ext2', 'ext3'])
        self.pos_constructor_uses.append(dict(
            body=self.current_routine.name if self.current_routine else self.program.name,
            line=expr.token.line, column=expr.token.column, arguments_evaluated_once=True,
            argument_order=order, result_type=result_type[0], independent_value=True, configuration_copied=True))
        return self._builtin_result(expr, codes, result_type)

    def _builtin_pose_axis(self, expr):
        if len(expr.args) != 1:
            self.error('E_ARGUMENTS', f'{expr.value} requires one pose', expr.token)
        argument = expr.args[0]
        code, spec = self.expression(argument)
        self.frame_result_type([spec], argument.token)
        code = self.geometry_operand(code, spec, argument.token, expr.value)
        self.geometry_expression_types[id(expr)] = ('VECTOR',)
        self.position_axis_uses.append(dict(
            function=expr.value, body=self.current_routine.name if self.current_routine else self.program.name,
            line=expr.token.line, column=expr.token.column, operand_type=spec[0], result_type='VECTOR',
            axis=expr.value, evaluated_once=True, independent_value=True))
        return self._builtin_result(expr, [code], ('VECTOR',))

    def _builtin_frame(self, expr):
        name = expr.value
        if (name == 'INV' and len(expr.args) != 1 or name == 'FRAME' and len(expr.args) not in (3, 4, 5)):
            self.error('E_ARGUMENTS', 'INV requires one operand; FRAME requires three points and optional origin and CONFIG', expr.token)
        codes, specs = [], []
        for index, argument in enumerate(expr.args):
            code, spec = self.expression(argument)
            if index == 4 and spec != ('CONFIG',):
                self.error('E_ARGUMENTS', 'Five-argument FRAME requires CONFIG as the fifth argument', expr.token)
            if name == 'FRAME' and index >= 3 and spec == ('CONFIG',):
                code = f'_rt.positional_value({spec!r},{code},{argument.token.line})'
            else:
                if spec != ('VECTOR',):
                    self.frame_result_type([spec], argument.token)
                code = self.geometry_operand(code, spec, argument.token, name)
            codes.append(code)
            specs.append(spec)
        result_type = self.frame_call_result_type(name, specs, expr.token)
        self.geometry_expression_types[id(expr)] = result_type
        use = dict(operation=name, body=self.current_routine.name if self.current_routine else self.program.name,
                   line=expr.token.line, column=expr.token.column, operand_types=[spec[0] for spec in specs],
                   result_type=result_type[0], evaluated_once=True, operands_copied=True)
        if name == 'FRAME':
            explicit_config = specs[-1] == ('CONFIG',)
            origin = 4 if len(specs) - int(explicit_config) == 4 else 1
            use.update(origin_argument=origin, configuration_argument=len(specs) if explicit_config else origin)
        self.frame_operation_uses.append(use)
        return self._builtin_result(expr, codes, result_type)

    def _builtin_signature(self, expr):
        name = expr.value
        signature, result_type = BUILTIN_SIGNATURES[name]
        if len(expr.args) != len(signature):
            self.error('E_ARGUMENTS', f'{name} requires {len(signature)} arguments', expr.token)
        if self.mode == 'strict' and len(expr.args) > 1 and any(self.has_routine_call(arg) for arg in expr.args):
            self.error('E_EVALUATION_ORDER', 'Multiple built-in arguments containing routine calls need evaluation-order validation', expr.token)
        codes = [self.require_type(argument, expected) for argument, expected in zip(expr.args, signature)]
        body = self.current_routine.name if self.current_routine else self.program.name
        line, column = expr.token.line, expr.token.column
        if name == 'VEC':
            self.vector_constructor_uses.append(dict(
                body=body, line=line, column=column, arguments_evaluated_once=True,
                argument_order=['x', 'y', 'z'], independent_value=True))
        if name in rt.UNARY_TRIG_FUNCTIONS:
            self.trig_uses.append(dict(function=name, body=body, line=line, column=column, evaluated_once=True,
                                       runtime_exact_subset_guard=self.mode == 'strict', result_type='REAL'))
        if name == 'ATAN2':
            self.atan2_uses.append(dict(body=body, line=line, column=column, argument_order=['x', 'y'],
                                       arguments_evaluated_once=True, runtime_exact_subset_guard=self.mode == 'strict',
                                       result_type='REAL'))
        return self._builtin_result(expr, codes, result_type)

    def microsecond_timer(self, expr):
        reading = expr.value == 'GET_USEC_TIM'
        count = 0 if reading else 2
        if len(expr.args) != count:
            self.error('E_ARGUMENTS', f'{expr.value} requires {count} arguments', expr.token)
        self.check_for_call(expr.token)
        codes = [self.require_type(argument, 'INTEGER') for argument in expr.args]
        self.features.add(expr.value)
        self.microsecond_timer_uses.append(dict(
            function=expr.value, body=self.current_routine.name if self.current_routine else self.program.name,
            line=expr.token.line, column=expr.token.column, host_clock_read=reading,
            argument_order=[] if reading else ['later', 'earlier'], arguments_evaluated_once=True, result_type='INTEGER'))
        if reading:
            return f'self._state.microsecond_time({expr.token.line})'
        return f'_rt.usec_sub({", ".join(codes)}, {expr.token.line})'
