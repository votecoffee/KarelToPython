"""Lower checked robot system operands to offline runtime operations."""
from .robot_system_analysis import check_system_pose_target, check_system_pose_value, check_system_selection_target


class RobotSystemLowering:
    """Emit system pose and frame/tool reads and staged writes."""

    def _system_body(self):
        return self.current_routine.name if self.current_routine else self.program.name

    def lower_system_selection(self, expr):
        selector = expr.args[0]
        group = self.require_type(selector, 'INTEGER')
        self.system_selection_uses.append(dict(
            operation='READ_' + expr.value, body=self._system_body(), line=expr.token.line,
            column=expr.token.column, evaluated_once=True, private_value=True, result_type='INTEGER'))
        self.features.update(('robot frame/tool selection', 'extended services'))
        return f'self._state.system_selection({expr.value!r},_rt.integer({group},{selector.token.line}),{expr.token.line})', ('INTEGER',)

    def lower_system_pose(self, expr, pose):
        axis = None if pose is expr else expr.value
        result_type = 'POSITION' if axis is None else 'REAL'
        codes = [self.require_type(argument, 'INTEGER') for argument in pose.args]
        codes = [f'_rt.integer({code},{argument.token.line})' for code, argument in zip(codes, pose.args)]
        row = dict(operation=pose.value, body=self._system_body(), line=expr.token.line, column=expr.token.column,
                   evaluated_once=True, independent_value=True, result_type=result_type)
        if axis is not None:
            row['path'] = (axis,)
        if row not in self.system_pose_uses:
            self.system_pose_uses.append(row)
        self.features.update(('robot system pose value', 'extended services'))
        number = codes[1] if len(codes) > 1 else 'None'
        selector = '' if axis is None else f',axis={axis!r}'
        return f'self._state.system_pose({pose.value!r},{codes[0]},{number},{expr.token.line}{selector})', (result_type,)

    def _capture_system_value(self, value, token):
        captured = self.fresh()
        self.line(f'{captured}=_rt.assignment_value({value},{token.line})', token)
        return captured

    def _capture_system_selector(self, selector, source_token):
        code = self.require_type(selector, 'INTEGER')
        captured = self.fresh()
        self.line(f'{captured}=_rt.integer({code},{selector.token.line})', source_token)
        return captured

    def lower_system_selection_write(self, target, operand, token):
        self.check_for_call(token)
        check_system_selection_target(target, error=self.error)
        value = self.require_type(operand, 'INTEGER')
        captured = self._capture_system_value(value, token)
        group = self._capture_system_selector(target.args[0], target.token)
        self.line(f'self._state.system_selection_write({target.value!r},{group},{captured},{token.line})', token)
        self.system_selection_uses.append(dict(
            operation='WRITE_' + target.value, body=self._system_body(), line=token.line, column=token.column,
            evaluated_once=True, rhs_before_selector=True, atomic_selection=True))
        self.features.update(('robot frame/tool selection', 'extended services'))

    def lower_system_pose_write(self, target, operand, token):
        self.check_for_call(token)
        receiver = check_system_pose_target(target, error=self.error)
        value, actual = self.expression(operand)
        expected = self.access_type(target)
        conversion = check_system_pose_value(receiver, expected, actual, operand.token, mode=self.mode,
                                             compatible=self.compatible, error=self.error)
        line = token.line
        if conversion == 'real_integral':
            value = f'_rt.real_integral_value({expected!r},{value},{line})'
            self.features.add('checked REAL to integral system pose field')
        elif conversion == 'kinematic':
            value = f"self._state.kinematic_assignment(('XYZWPREXT',),{value},{line})"
            self.features.add('kinematic assignment')
            if self.current_routine:
                self.current_routine.may_services = True
            self.kinematic_assignment_uses.append(dict(
                body=self._system_body(), line=line, column=token.column, source_type=actual,
                target_type=('XYZWPREXT',), target_kind='system_pose', evaluated_once=True, independent_value=True))

        captured = self._capture_system_value(value, token)
        selectors = [self._capture_system_selector(argument, argument.token) for argument in receiver.pose.args]
        number = selectors[1] if len(selectors) > 1 else 'None'
        operation = receiver.pose.value
        self.line(f'self._state.system_pose_write({operation!r},{selectors[0]},{number},{captured},{receiver.path!r},{line})', token)
        row = dict(operation=operation, body=self._system_body(), line=line, column=token.column,
                   path=receiver.path, source_type=actual, evaluated_once=True,
                   rhs_before_selectors=True, atomic_table_publication=True)
        if conversion == 'kinematic':
            row.update(kinematic_conversion=True, stored_type=('XYZWPREXT',))
        self.system_pose_writes.append(row)
        self.features.update(('robot system pose assignment', 'extended services'))
