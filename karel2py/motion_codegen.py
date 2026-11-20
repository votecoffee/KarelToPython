"""Generate offline motion requests and their local condition callbacks."""
from . import runtime as rt
from .motion_analysis import MOTION_OPERANDS, check_motion_operand, check_motion_pose_setting, split_motion_path


class MotionLowering:
    """Capture motion settings and operands in source order."""

    def motion_position_expression(self, expr, operation):
        selected = expr
        while selected.kind == 'group':
            selected = selected.args[0]
        if selected.kind == 'index':
            receiver = selected.args[0]
            base = self.access_type(receiver)
            node = rt.collection_array_node_type(base, len(selected.args) - 1)
            if base[0] == 'PATH' or node is not None:
                code, _ = self.expression(receiver, raw=True)
                if node is None:
                    if len(selected.args) != 2:
                        self.error('E_ARRAY_RANK', 'PATH requires one node index', selected.token)
                    index = self.require_type(selected.args[1], 'INTEGER')
                    node = base[1] or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']
                else:
                    index, _ = self.index_code(selected, base)
                position = dict(rt.record_fields(node)).get('NODE_POS')
                if position is None:
                    self.error('E_MOTION_TYPE', operation + ' PATH node requires NODE_POS', expr.token)
                return f'_rt.motion_path_node_operand({code},{index},{base!r},{expr.token.line})', position
        return self.expression(expr)

    def lower_motion_control(self, stmt):
        operation, selectors = stmt.args
        token, line = stmt.token, stmt.token.line
        captured = []
        for expr in selectors or ():
            code = self.require_type(expr, 'INTEGER')
            temporary = self.fresh()
            self.line(f'{temporary}=_rt.integer({code},{expr.token.line})', expr.token)
            captured.append(temporary)
        groups = 'None' if selectors is None else '[' + ','.join(captured) + ']'
        self.features.add('offline motion requests')
        self.motion_uses.append(dict(
            body=self.current_routine.name if self.current_routine else self.program.name,
            line=line, column=token.column, operation=operation, nowait=False,
            operands_evaluated_once=True, groups='owned at action time' if selectors is None else len(captured)))
        self.line(f'self._state.execution.require("motion",{line}).invoke(self._state,{operation!r},{{"groups":{groups}}},False,{line})', token)

    def _capture_motion_settings(self, settings):
        captured = []
        for key, group, value in settings:
            group_code = 'None'
            if group is not None:
                code = self.require_type(group, 'INTEGER')
                group_code = self.fresh()
                self.line(f'{group_code}=_rt.integer({code},{group.token.line})', group.token)
            expected = rt.MOTION_SETTINGS[key.value]
            if expected == 'POSE':
                code, spec = self.expression(value)
                check_motion_pose_setting(spec, value.token, error=self.error)
            else:
                code = self.require_type(value, expected)
                spec = (expected,)
            temporary = self.fresh()
            self.line(f'{temporary}=_rt.motion_setting({key.value!r},{code},{spec!r},{value.token.line})', value.token)
            captured.append('{' + f'"name":{key.value!r},"group":{group_code},"value":{temporary}' + '}')
        return captured

    def _capture_motion_operands(self, operation, arguments, names, line):
        captured = []
        for index, expr in enumerate(arguments):
            name = names[index]
            if expr is None:
                captured.append(repr(name) + ':None')
                continue
            if name in ('hand', 'axis', 'start', 'end'):
                code, spec = self.require_type(expr, 'INTEGER'), ('INTEGER',)
            elif name in ('distance', 'angle'):
                code, spec = self.require_type(expr, 'REAL'), ('REAL',)
            else:
                if name in ('target', 'via'):
                    code, spec = self.motion_position_expression(expr, operation)
                else:
                    code, spec = self.expression(expr)
                check_motion_operand(operation, name, spec, expr.token, error=self.error)
            temporary = self.fresh()
            if name == 'path':
                self.line(f'{temporary}=_rt.motion_path_operand(self._state,{code},{spec!r},{line})', expr.token)
            else:
                self.line(f'{temporary}=_rt.motion_operand({code},{spec!r},{line})', expr.token)
            captured.append(repr(name) + ':' + temporary)
        return captured

    def lower_motion_request(self, stmt):
        operation = stmt.args[0]
        token, line = stmt.token, stmt.token.line
        if stmt.kind == 'motion':
            arguments, nowait, source_settings = stmt.args[1:]
            settings = self._capture_motion_settings(source_settings)
            if operation == 'MOVE ALONG':
                arguments = split_motion_path(arguments[0], access_type=self.access_type, error=self.error)
            names = MOTION_OPERANDS[operation]
        else:
            arguments = stmt.args[1:]
            names = ('hand',)
            nowait = False
            source_settings, settings = (), []
        captured = self._capture_motion_operands(operation, arguments, names, line)
        self.features.add('offline motion requests')
        request_use = dict(body=self.current_routine.name if self.current_routine else self.program.name,
                           line=line, column=token.column, operation=operation, nowait=nowait,
                           operands_evaluated_once=True)
        self.motion_uses.append(request_use)
        if settings:
            request_use['settings'] = [
                dict(name=key.value, line=key.line, column=key.column, group_qualified=group is not None)
                for key, group, _ in source_settings
            ]
        data = '{' + ','.join(captured) + '}'
        extra = ',settings=[' + ','.join(settings) + ']' if settings else ''
        if stmt.kind == 'motion':
            terms = []
            pairs = self.condition_callbacks(stmt.body, motion_terms=terms)
            if pairs:
                callbacks = ','.join(f'({clause.token.value!r},{predicate},{action},{clause.token.line})'
                                     for clause, (predicate, action) in zip(stmt.body, pairs))
                extra += ',clauses=[' + callbacks + ']'
                request_use['local_handlers'] = [
                    dict(kind=clause.token.value, line=clause.token.line, column=clause.token.column)
                    for clause in stmt.body
                ]
                if nowait:
                    request_use.update(callback_observation='owner_checkpoints',
                                       callback_lifetime='defining_frame_or_invocation')
                    self.features.add('NOWAIT local motion clauses')
            if terms:
                extra += ',conditions=[' + ','.join(name for name, _ in terms) + ']'
                request_use['conditions'] = [info for _, info in terms]
            self.line(f'yield from self._state.execution.require("motion",{line}).execute(self._state,{operation!r},{data},{nowait!r},{line}{extra})', token)
        else:
            self.line(f'self._state.execution.require("motion",{line}).invoke(self._state,{operation!r},{data},{nowait!r},{line}{extra})', token)
