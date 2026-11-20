"""Emit structured control flow and validated label dispatch."""
from .control_flow import FlowGraph, child_blocks, validate_labels
from .syntax import expression_postorder


def repeat_captures(statement):
    return [node for node in expression_postorder(statement.args[0]) if node.kind == 'repeat_eval']


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
            self._emit_label_dispatch(graph, transfers)
        else:
            report = dict(engine='structured_python', labels={})
            self.block(statements)
        report['jumps'] = transfers
        if self.current_routine:
            self.control_flow['routines'][self.current_routine.name] = report
        else:
            self.control_flow['program'] = report

    def _emit_label_dispatch(self, graph, transfers):
        self.features.add('label control-flow dispatcher')
        pc = self.fresh()
        captures = {}
        for index, node in enumerate(graph.nodes):
            if node.kind == 'repeat_test':
                terms = repeat_captures(node.statement)
                if terms:
                    captures[index] = terms
        if captures:
            repeat_cache = self.fresh()
            self.line(f'{repeat_cache} = {{}}')
            exited_repeats = self._repeat_jump_exits(graph, captures, transfers)
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
            if index in captures:
                self._emit_captured_repeat_test(index, node, pc, repeat_cache, captures[index])
            else:
                if captures and node.kind == 'goto':
                    site = (node.statement.token.line, node.statement.token.column)
                    for scope in exited_repeats.get(site, ()):
                        self.line(f'{repeat_cache}.pop({scope}, None)')
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

    @staticmethod
    def _repeat_jump_exits(graph, captures, transfers):
        scopes = {next(child_blocks(graph.nodes[index].statement))[0]: index for index in captures}
        result = {}
        for transfer in transfers:
            source, target = transfer['source'], transfer['target']
            exited = tuple(scopes[block] for block in reversed(source['blocks'])
                           if block in scopes and block not in target['blocks'])
            if exited:
                result[source['line'], source['column']] = exited
        return result

    def _emit_captured_repeat_test(self, index, node, pc, cache, terms):
        stmt = node.statement
        condition = self.emit_repeat_capture_predicate(stmt, terms, cache, index)
        yes, no = node.targets
        self.line(f'if {self.test_code(condition, stmt.token.line)}:', stmt.token)
        self.indent += 1
        self.line(f'{cache}.pop({index}, None)')
        self.line(f'{pc} = {yes!r}')
        self.indent -= 1
        self.line('else:')
        self.indent += 1
        self.line(f'{pc} = {no!r}')
        self.indent -= 1

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

    def emit_repeat_capture_predicate(self, stmt, terms, cache, key):
        self.features.update(('repeat', 'REPEAT UNTIL EVAL capture'))
        predicate = self.fresh()
        self.line(f'def {predicate}():')
        self.indent += 1
        self.line(f'if {key} not in {cache}:')
        self.indent += 1
        originals = []
        try:
            values = ', '.join(self.emit_condition_capture(term, originals) for term in terms)
            self.line(f'{cache}[{key}] = ({values},)')
            self.indent -= 1
            self.line(f'{values}, = {cache}[{key}]')
            condition = self.require_type(stmt.args[0], 'BOOLEAN')
            self.line(f'return {condition}')
        finally:
            self.restore_condition_terms(originals)
        self.indent -= 1
        return f'{predicate}()'

    def emit_structured_repeat(self, stmt):
        terms = repeat_captures(stmt)
        if terms:
            cache = self.fresh()
            self.line(f'{cache} = {{}}')
            condition = self.emit_repeat_capture_predicate(stmt, terms, cache, 0)
        else:
            condition = self.require_type(stmt.args[0], 'BOOLEAN')
        self.line('while True:', stmt.token)
        self.indent += 1
        self.block(stmt.body)
        self.line(f'if {self.test_code(condition, stmt.token.line)}:')
        self.indent += 1
        self.line('break')
        self.indent -= 2
        if terms:
            self.line(f'{cache}.clear()')
