"""Emit structured control flow and validated label dispatch."""
from .control_flow import FlowGraph, validate_labels


class ControlFlowLowering:
    """Generate body control flow and track active FOR scopes at each node."""

    def _check_body_labels(self, statements):
        conflicts = set(self.types) | set(self.visible_constants()) | set(self.user_types) | set(self.routines) | {self.program.name}
        if self.current_routine:
            conflicts.update(self.current_routine.local_types)
        return validate_labels(statements, conflicts=conflicts, mode=self.mode, error=self.error)

    def emit_body(self, statements):
        labelled, transfers = self._check_body_labels(statements)
        if labelled:
            graph = FlowGraph(statements, lower_for=self.mode == 'pythonic')
            report = graph.report()
            self._emit_label_dispatch(graph)
        else:
            report = dict(engine='structured_python', labels={})
            self.block(statements)
        report['jumps'] = transfers
        if self.current_routine:
            self.control_flow['routines'][self.current_routine.name] = report
        else:
            self.control_flow['program'] = report

    def _emit_label_dispatch(self, graph):
        self.features.add('label control-flow dispatcher')
        pc = self.fresh()
        frames = done = None
        if graph.for_scopes:
            self.features.add('FOR dispatcher scopes and checked jumps')
            frames, done = self.fresh(), self.fresh()
            self.line(f'{frames} = []')
            self.line(f'{done} = object()')
            self.line('try:')
            self.indent += 1
        self.line(f'{pc} = {graph.entry!r}')
        self.line(f'while {pc} is not None:')
        self.indent += 1
        self.line(f'match {pc}:')
        self.indent += 1
        for index, node in enumerate(graph.nodes):
            self.line(f'case {index}:', node.statement.token)
            self.indent += 1
            previous_counters = self.active_counters
            if frames is not None:
                self._sync_dispatch_for_scopes(graph, node, frames)
            self._emit_dispatch_node(index, node, pc, frames, done)
            self.active_counters = previous_counters
            self.indent -= 1
        self.line('case _:')
        self.indent += 1
        self.line('raise _rt.KarelRuntimeError("Invalid generated control-flow state")')
        self.indent -= 3
        if frames is not None:
            self.indent -= 1
            self.line('finally:')
            self.indent += 1
            self.line(f'while {frames}:')
            self.indent += 1
            self.line(f'{frames}.pop()[1].clear()')
            self.indent -= 2

    def _sync_dispatch_for_scopes(self, graph, node, frames):
        scopes = node.for_scopes
        self.active_counters = {self.protection_root(graph.for_scopes[scope].args[0]) for scope in scopes}
        self.line(f'while {frames} and {frames}[-1][0] not in {scopes!r}:')
        self.indent += 1
        self.line(f'{frames}.pop()[1].clear()')
        self.indent -= 1
        self.line(f'if tuple(_frame[0] for _frame in {frames}) != {scopes!r}:')
        self.indent += 1
        self.line(f'raise _rt.KarelRuntimeError("Invalid generated FOR scope state", {node.statement.token.line})')
        self.indent -= 1

    def _emit_dispatch_node(self, index, node, pc, frames, done):
        stmt, kind = node.statement, node.kind
        token, line = stmt.token, stmt.token.line
        if kind in ('label', 'goto', 'enter'):
            self.features.add(stmt.kind)
            if kind != 'label':
                self.line(f'self._state.tick({line})', token)
            if kind == 'enter' and stmt.kind == 'using':
                self.emit_using_entry(stmt)
            self.line(f'{pc} = {node.targets[0]!r}')
        elif kind == 'for_enter':
            self._emit_dispatch_for_entry(index, node, pc, frames)
        elif kind == 'for_next':
            self._emit_dispatch_for_next(node, pc, frames, done)
        elif kind == 'for_exit':
            self.line(f'{frames}.pop()[1].clear()')
            self.line(f'{pc} = {node.targets[0]!r}')
        elif kind in ('if', 'while_test', 'repeat_test'):
            self.features.add(stmt.kind)
            if kind == 'if':
                self.line(f'self._state.tick({line})', token)
            condition = self.require_type(stmt.args[0], 'BOOLEAN')
            yes, no = node.targets
            self.line(f'{pc} = {yes!r} if {self.test_code(condition, line)} else {no!r}', token)
        elif kind == 'select':
            self.features.add('select')
            self.line(f'self._state.tick({line})', token)
            self.emit_dispatch_select(stmt, pc, node.targets)
        elif kind in ('abort', 'return'):
            self.statement(stmt)  # Terminal node has no successor.
        else:
            self.statement(stmt)
            self.line(f'{pc} = {node.targets[0]!r}')

    def _emit_dispatch_for_entry(self, index, node, pc, frames):
        stmt = node.statement
        token, line = stmt.token, stmt.token.line
        self.features.add('for')
        self.line(f'self._state.tick({line})', token)
        operands = self.for_operands(stmt)
        stop, captured = self.fresh(), self.fresh()
        self.capture_for_counter(operands, captured, line)
        # A failing final bound still unwinds the initialized reference.
        self.line(f'{frames}.append([{index}, {captured}, None])')
        self.line(f'{stop} = {operands.final}')
        start = f'_rt.require({captured}.raw(), {line})'
        self.line(f'{frames}[-1][2] = iter({operands.range_code(start, stop)})')
        self.line(f'{pc} = {node.targets[0]!r}')

    def _emit_dispatch_for_next(self, node, pc, frames, done):
        token = node.statement.token
        item = self.fresh()
        self.line(f'{item} = next({frames}[-1][2], {done})')
        self.line(f'if {item} is {done}:')
        self.indent += 1
        self.line(f'{pc} = {node.targets[1]!r}')
        self.indent -= 1
        self.line('else:')
        self.indent += 1
        self.line(f'self._state.tick({token.line})', token)
        self.line(f'{frames}[-1][1].set({item}, {token.line})')
        self.line(f'{pc} = {node.targets[0]!r}')
        self.indent -= 1

    def test_code(self, code, line):
        if self.cooperative:
            return f'(yield from _rt.cooperative_test(self._state,lambda: {code},{line}))'
        return f'self._state.test({code},{line})'

    def emit_structured_condition(self, stmt):
        token = stmt.token
        condition = self.require_type(stmt.args[0], 'BOOLEAN')
        self.line(f'{stmt.kind} {self.test_code(condition, token.line)}:', token)
        self.indent += 1
        self.block(stmt.body)
        self.indent -= 1
        if stmt.kind == 'if' and stmt.alternate:
            self.line('else:')
            self.indent += 1
            self.block(stmt.alternate)
            self.indent -= 1

    def emit_structured_repeat(self, stmt):
        condition = self.require_type(stmt.args[0], 'BOOLEAN')
        self.line('while True:', stmt.token)
        self.indent += 1
        self.block(stmt.body)
        self.line(f'if {self.test_code(condition, stmt.token.line)}:')
        self.indent += 1
        self.line('break')
        self.indent -= 2
