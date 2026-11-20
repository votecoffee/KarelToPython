"""Generate checked timing and polling statements for the offline runtime."""
from .syntax import Expr


def wait_edge_nodes(operand):
    """Visit inner edge operands before their dependents, in source order."""
    if isinstance(operand, Expr):
        for child in operand.args:
            yield from wait_edge_nodes(child)
        if operand.kind == 'wait_edge':
            yield operand


class TimingLowering:
    """Preserve one-shot DELAY and PULSE capture and repeated WAIT checks."""

    def lower_delay(self, stmt):
        token = stmt.token
        duration = self.require_type(stmt.args[0], 'INTEGER')
        if self.cooperative:
            scan = self.mode == 'pythonic'
            self.line(f'yield from _rt.delay_execution(self._state,{duration},{token.line},scan_handlers={scan!r})', token)
        else:
            self.line(f'self._state.delay({duration}, {token.line})', token)
        self.features.add('DELAY')
        self.delay_uses.append(dict(
            body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line, column=token.column, duration_type='INTEGER', evaluated='once; runtime range check'))

    def lower_wait(self, stmt):
        token = stmt.token
        operand = stmt.args[0]
        edges = list(wait_edge_nodes(operand))
        condition = (self.emit_wait_edge_predicate(operand, edges) if edges
                     else self.require_type(operand, 'BOOLEAN'))
        self.line(f'while not {self.test_code(condition, token.line)}:', token)
        self.indent += 1
        self.line(f'self._state.wait_poll({token.line})', token)
        self.indent -= 1
        self.features.add('WAIT FOR')
        self.wait_uses.append(dict(
            body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line, column=token.column, condition_kind=stmt.args[0].kind,
            condition_type='BOOLEAN', evaluation='once per check until true',
            yield_seconds=0.0, step_budgeted=True))
        if edges:
            self.features.update(('ports', 'WAIT FOR port edges'))
            self.wait_uses[-1]['port_edges'] = len(edges)

    def emit_wait_edge_predicate(self, operand, edges):
        history, predicate = self.fresh(), self.fresh()
        self.line(f'{history} = {{}}')
        self.line(f'def {predicate}():')
        self.indent += 1
        original = []
        try:
            for key, edge in enumerate(edges):
                port = edge.args[0]
                bank = port.args[0]
                if bank.kind != 'name' or bank.value in self.types or bank.value in self.visible_constants():
                    self.error('E_PORT_EDGE', 'WAIT FOR edge requires an unshadowed digital port bank', edge.token)
                if len(port.args) != 2:
                    self.error('E_ARGUMENTS', 'Ports require one index', port.token)
                address = self.require_type(port.args[1], 'INTEGER')
                sample = self.fresh()
                self.line(f'{sample} = _rt.sample_wait_edge(self._state, {history}, {key}, '
                          f'{bank.value!r}, {address}, {edge.value!r}, {edge.token.line})', edge.token)
                original.append((edge, edge.value, edge.args))
                edge.kind, edge.value, edge.args = 'captured', (sample, ('BOOLEAN',)), []
            self.line(f'return {self.require_type(operand, "BOOLEAN")}', operand.token)
        finally:
            # Input discovery keeps the original source operands and operator identities.
            for edge, value, args in original:
                edge.kind, edge.value, edge.args = 'wait_edge', value, args
        self.indent -= 1
        return f'{predicate}()'

    def lower_pulse(self, stmt):
        token = stmt.token
        target, milliseconds, nowait, bank = stmt.args
        if bank in self.types or bank in self.visible_constants():
            self.error('E_PULSE', f'PULSE requires the unshadowed {bank} port bank', token)
        number = self.require_type(target, 'INTEGER')
        duration = self.require_type(milliseconds, 'INTEGER')
        self.features.update(('ports', 'extended services'))
        self.pulse_uses.append(dict(
            body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line, column=token.column, nowait=nowait, port_bank=bank,
            operands_evaluated_once=True))
        bank_argument = f',port_bank={bank!r}' if bank != 'DOUT' else ''
        self.line(f'yield from _rt.pulse_execution(self._state,{number},{duration},{nowait!r},{token.line}{bank_argument})',
                  token)
