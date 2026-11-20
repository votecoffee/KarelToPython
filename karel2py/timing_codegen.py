"""Generate checked timing and polling statements for the offline runtime."""
from collections import Counter

from .syntax import expression_postorder


WAIT_SAMPLE_REPORTS = {
    'wait_edge': ('port_edges', ('ports', 'WAIT FOR port edges')),
    'wait_pause': ('task_pause_conditions', ('WAIT FOR PAUSE',)),
    'wait_error': ('error_conditions', ('WAIT FOR ERROR',)),
    'wait_lifecycle': ('lifecycle_conditions', ('WAIT FOR lifecycle notifications',)),
}


def wait_terms(operand):
    return (node for node in expression_postorder(operand)
            if node.kind == 'wait_eval' or node.kind in WAIT_SAMPLE_REPORTS)


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
        samples = [term for term in terms if term.kind != 'wait_eval']
        counts = Counter(term.kind for term in samples)
        originals = []
        try:
            for term in captures:
                self.emit_wait_capture(term, originals)
            condition = (self.emit_sampled_wait(operand, samples, originals, counts)
                         if samples else self.require_type(operand, 'BOOLEAN'))
        finally:
            self.restore_condition_terms(originals)
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
        for kind, count in counts.items():
            field, features = WAIT_SAMPLE_REPORTS[kind]
            self.features.update(features)
            self.wait_uses[-1][field] = count

    def emit_wait_capture(self, term, originals):
        operand = term.args[0]
        if any(child.kind in WAIT_SAMPLE_REPORTS for child in wait_terms(operand)):
            self.error('E_EVAL', 'EVAL in WAIT FOR cannot capture a live condition event', term.token)
        self.emit_condition_capture(term, originals)

    def emit_sampled_wait(self, operand, samples, originals, counts):
        predicate = self.fresh()
        contexts = {}
        if counts['wait_edge']:
            contexts['wait_edge'] = self.fresh()
            self.line(f"{contexts['wait_edge']} = {{}}")
        if counts['wait_pause']:
            contexts['wait_pause'] = self.fresh()
            self.line(f"{contexts['wait_pause']} = _rt.PauseSamples(self._state, include_current=True)")
        if counts['wait_error'] or counts['wait_lifecycle']:
            notifications = self.fresh()
            contexts['wait_error'] = contexts['wait_lifecycle'] = notifications
            self.line(f'{notifications} = _rt.WaitNotifications(self._state, watch_errors={bool(counts["wait_error"])!r})')
        self.line(f'def {predicate}():')
        self.indent += 1
        for key, term in enumerate(samples):
            evaluation = self.wait_sample_expression(term, contexts[term.kind], key)
            temporary = self.fresh()
            self.line(f'{temporary} = {evaluation}', term.token)
            self.bind_condition_temporary(term, temporary, ('BOOLEAN',), originals)
        self.line(f'return {self.require_type(operand, "BOOLEAN")}', operand.token)
        self.indent -= 1
        return f'{predicate}()'

    def wait_sample_expression(self, term, context, key):
        if term.kind == 'wait_edge':
            return self.wait_edge_sample(term, context, key)
        if term.kind == 'wait_lifecycle':
            return f'{context}.lifecycle({term.value!r}, {key})'
        selector = term.args[0] if term.args else None
        number = self.require_type(selector, 'INTEGER') if selector is not None else 'None'
        if term.kind == 'wait_error':
            return f'{context}.error({number}, {key}, {term.token.line})'
        return f'_rt.sample_wait_pause(self._state, {context}, {number}, {key}, {term.token.line})'

    def wait_edge_sample(self, term, history, key):
        port = term.args[0]
        bank = port.args[0]
        if bank.kind != 'name' or bank.value in self.types or bank.value in self.visible_constants():
            self.error('E_PORT_EDGE', 'WAIT FOR edge requires an unshadowed digital port bank', term.token)
        if len(port.args) != 2:
            self.error('E_ARGUMENTS', 'Ports require one index', port.token)
        address = self.require_type(port.args[1], 'INTEGER')
        return (f'_rt.sample_wait_edge(self._state, {history}, {key}, '
                f'{bank.value!r}, {address}, {term.value!r}, {term.token.line})')

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
