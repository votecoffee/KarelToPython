"""Generate condition callbacks, handler controls, and connected timers."""
from .control_flow import counter_text
from .handler_analysis import HandlerAnalysis, callback_defaults, check_handler_actions
from .syntax import Expr


class HandlerLowering(HandlerAnalysis):
    """Emit checked callback captures in their source evaluation order."""

    def _capture_handler_evaluations(self, clause):
        for item in reversed(list(self.walk_nodes([*clause.args, *clause.body]))):
            if not isinstance(item, Expr) or item.kind != 'eval':
                continue
            code, spec = self.expression(item.args[0])
            temporary = self.fresh()
            self.line(f'{temporary}=_rt.assignment_value({code},{item.token.line})', item.token)
            item.kind = 'captured'
            item.value = (temporary, spec)
            item.args = []

    def _capture_handler_integer(self, expr):
        code = self.require_type(expr, 'INTEGER')
        temporary = self.fresh()
        self.line(f'{temporary}=_rt.integer({code},{expr.token.line})', expr.token)
        return temporary

    def _capture_motion_selectors(self, clause, motion_terms):
        for item in list(self.walk_nodes(clause.args)):
            if not isinstance(item, Expr) or item.kind != 'motion_condition':
                continue
            if motion_terms is None:
                self.error('E_MOTION_CONDITION', 'AT NODE/TIME requires a motion-local predicate', item.token)
            if len(motion_terms) >= 64:
                self.error('E_MOTION_CONDITION', 'MOVE supports at most 64 temporal selectors', item.token)
            offset, node = item.args
            offset_code = '0' if offset is None else self._capture_handler_integer(offset)
            node_code = repr('*') if node is None else self._capture_handler_integer(node)
            temporary = self.fresh()
            self.line(f'{temporary}=_rt.motion_selector({item.value!r},{offset_code},{node_code},{item.token.line})',
                      item.token)
            motion_terms.append((temporary, dict(
                kind=item.value, line=item.token.line, column=item.token.column,
                wildcard=node is None, evaluated_once=True)))
            item.kind = 'motion_event'
            item.value = temporary
            item.args = []

    def condition_callbacks(self, clauses, *, motion_terms=None):
        pairs = []
        for clause in clauses:
            self._capture_handler_evaluations(clause)
            self._capture_motion_selectors(clause, motion_terms)
            check_handler_actions(self.walk_nodes(clause.body), error=self.error)
            predicate, action = self.fresh(), self.fresh()
            condition = self.require_type(clause.args[0], 'BOOLEAN')
            defaults = callback_defaults(self.walk_nodes([clause.args, clause.body]))

            self.line(f'def {predicate}({defaults}):')
            self.indent += 1
            self.line(f'return {condition}')
            self.indent -= 1
            self.line(f'def {action}({defaults}):')
            self.indent += 1
            self.line('if False: yield None')
            self.block(clause.body)
            self.indent -= 1
            pairs.append((predicate, action))
        return pairs

    def lower_handler_action(self, stmt):
        token = stmt.token
        self.line(f'_rt.handler_action(self._state,{stmt.args[0]!r},{token.line})', token)

    def lower_condition_control(self, stmt):
        action, expr = stmt.args
        number = self.require_type(expr, 'INTEGER')
        self.line(f'_rt.condition_control(self._state,{action!r},{number},{stmt.token.line})', stmt.token)

    def lower_condition(self, stmt):
        token, line = stmt.token, stmt.token.line
        expr, source_options = stmt.args
        number = self.require_type(expr, 'INTEGER')
        captured = self.fresh()
        self.line(f'{captured}=_rt.integer({number},{expr.token.line})', token)
        options = {'$SCAN_TIME': '0', '$PRIORITY': '50'}
        for key, value in source_options:
            options[key.value] = self._capture_handler_integer(value)
        pairs = [f'({predicate},{action})' for predicate, action in self.condition_callbacks(stmt.body)]
        self.handler_uses.append(dict(
            body=self.current_routine.name if self.current_routine else self.program.name, line=line, column=token.column,
            option_order=[key.value for key, _ in source_options], clauses=len(stmt.body), evaluated_once=True))
        self.line(f'_rt.define_condition(self._state,{captured},[{", ".join(pairs)}],{line},scan_ms={options["$SCAN_TIME"]},priority={options["$PRIORITY"]})',
                  token)

    def lower_connected_timer(self, stmt):
        token, line = stmt.token, stmt.token.line
        target = stmt.args[0]
        binding = self.check_connected_timer_target(target)
        reference, spec = self.reference(target)
        self.check_connected_timer_schema(target, spec)
        connecting = stmt.kind == 'timer_connect'
        method = 'connect_timer' if connecting else 'disconnect_timer'
        self.connected_timer_uses.append(dict(
            operation='CONNECT' if connecting else 'DISCONNECT',
            body=self.current_routine.name if self.current_routine else self.program.name,
            line=line, column=token.column, selector=counter_text(target), root=binding.root,
            provenance=binding.provenance, protection_root=binding.protection_root, evaluated_once=True,
            lifetime='routine_frame' if binding.scoped else 'invocation',
            control_scope='defining_connection' if connecting else 'same_task_existing_claim'))
        self.features.add('connected INTEGER timer')
        if binding.private:
            self.features.add('private USING connected timer')
        if binding.local:
            self.features.add('routine-local connected timer')
        if binding.formal:
            self.features.add('borrowed formal connected timer')
        scope = ',scoped=True' if binding.scoped else ''
        self.line(f'_rt.{method}(self._state,{reference},{line}{scope})', token)
