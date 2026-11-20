"""Generate task lifecycle and signaling statements for the offline scheduler."""


class TaskControlLowering:
    def lower_task_control(self, stmt):
        action = stmt.args[0]
        token, line = stmt.token, stmt.token.line
        if len(stmt.args) > 1:
            number = self.require_type(stmt.args[1], 'INTEGER')
            self.line(f'yield from _rt.control_task(self._state,{action!r},{number},{line})', token)
        elif action == 'PAUSE':
            self.line(f'yield from _rt.pause_execution(self._state,{line})', token)
        elif action == 'STOP':
            self.line('raise _rt.KarelStop("Task stopped")', token)
        else:
            self.line('self._state._pause_requested=False', token)
            if action == 'CONTINUE':
                self.line("self._state._lifecycle['CONTINUE']+=1", token)
                self.line(f'yield from _rt.checkpoint(self._state,{line})', token)

    def lower_task_signal(self, stmt):
        token, line = stmt.token, stmt.token.line
        number = self.require_type(stmt.args[0], 'INTEGER')
        if stmt.kind == 'signal_event':
            self.line(f'_rt.signal_event(self._state,{number},{line})', token)
        else:
            self.features.add('extended services')
            self.line(f'self._state.extended_call("POST_SEMA",[{number}],{line})', token)
        self.line(f'yield from _rt.checkpoint(self._state,{line})', token)

    def lower_task_abort(self, token):
        if self.mode == 'strict' and self.active_counters and not self.has_fresh_active_counters():
            self.error('E_FOR_COUNTER', 'ABORT inside FOR requires fresh routine-local counters; observable counter state on abort is unvalidated', token)
        line = token.line
        code = (f'yield from _rt.abort_execution(self._state,{line})' if self.cooperative
                else f'self._state.abort({line})')
        self.line(code, token)
        self.features.add('ABORT')
        self.abort_uses.append(dict(
            body=self.current_routine.name if self.current_routine else self.program.name,
            line=line, column=token.column, scope='current offline execution'))
