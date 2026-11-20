"""Generate checked timing and polling statements for the offline runtime."""


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
        condition = self.require_type(stmt.args[0], 'BOOLEAN')
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

    def lower_pulse(self, stmt):
        token = stmt.token
        if 'DOUT' in self.types or 'DOUT' in self.visible_constants():
            self.error('E_PULSE', 'PULSE requires the unshadowed DOUT port bank', token)
        number = self.require_type(stmt.args[0], 'INTEGER')
        duration = self.require_type(stmt.args[1], 'INTEGER')
        nowait = stmt.args[2]
        self.features.update(('ports', 'extended services'))
        self.pulse_uses.append(dict(
            body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line, column=token.column, nowait=nowait, operands_evaluated_once=True))
        self.line(f'yield from _rt.pulse_execution(self._state,{number},{duration},{nowait!r},{token.line})', token)
