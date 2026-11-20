"""Generate checked timing and polling statements for the offline runtime."""
from .syntax import Expr


def wait_terms(operand):
    """Visit capture and edge operands before their dependents, in source order."""
    if isinstance(operand, Expr):
        for child in operand.args:
            yield from wait_terms(child)
        if operand.kind in ('wait_eval', 'wait_edge'):
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
        terms = list(wait_terms(operand))
        captures = [term for term in terms if term.kind == 'wait_eval']
        edges = [term for term in terms if term.kind == 'wait_edge']
        originals = []
        try:
            for term in captures:
                self.emit_wait_capture(term, originals)
            condition = (self.emit_wait_edge_predicate(operand, edges, originals) if edges
                         else self.require_type(operand, 'BOOLEAN'))
        finally:
            # Preserve source operands and operator identities for input discovery.
            for term, kind, value, args in originals:
                term.kind, term.value, term.args = kind, value, args
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
        if captures:
            self.features.add('WAIT FOR EVAL capture')
            self.wait_uses[-1]['entry_captures'] = len(captures)
        if edges:
            self.features.update(('ports', 'WAIT FOR port edges'))
            self.wait_uses[-1]['port_edges'] = len(edges)

    @staticmethod
    def bind_wait_temporary(term, temporary, spec, originals):
        originals.append((term, term.kind, term.value, term.args))
        term.kind, term.value, term.args = 'captured', (temporary, spec), []

    def emit_wait_capture(self, term, originals):
        operand = term.args[0]
        if any(child.kind == 'wait_edge' for child in wait_terms(operand)):
            self.error('E_EVAL', 'EVAL in WAIT FOR cannot capture a port transition', term.token)
        code, spec = self.expression(operand)
        temporary = self.fresh()
        self.line(f'{temporary} = _rt.assignment_value({code}, {term.token.line})', term.token)
        self.bind_wait_temporary(term, temporary, spec, originals)

    def emit_wait_edge_predicate(self, operand, edges, originals):
        history, predicate = self.fresh(), self.fresh()
        self.line(f'{history} = {{}}')
        self.line(f'def {predicate}():')
        self.indent += 1
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
            self.bind_wait_temporary(edge, sample, ('BOOLEAN',), originals)
        self.line(f'return {self.require_type(operand, "BOOLEAN")}', operand.token)
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
