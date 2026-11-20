"""Check callback capture, connected timer storage, and asynchronous counter effects."""
from dataclasses import dataclass

from . import extended as ex
from .compiler_language import (
    BUILTIN_PROCEDURES,
    CONFIG_TEXT_PROCEDURES,
    INTEGRAL_TYPES,
    MULTI_OUTPUT_PROCEDURES,
    REGISTER_PROCEDURES,
    TIME_TEXT_PROCEDURES,
)
from .syntax import Expr, Statement


def callback_defaults(nodes):
    """Freeze enclosing USING references while leaving local captures to the callback."""
    nodes = list(nodes)
    local = {name for node in nodes if isinstance(node, Statement) and node.kind == 'using'
             for name in getattr(node, 'using_captures', ())}
    captured = {node.value[0] for node in nodes if isinstance(node, Expr) and node.kind == 'using_ref'}
    return ','.join(name + '=' + name for name in sorted(captured - local))


def check_handler_actions(nodes, *, error):
    for node in nodes:
        if isinstance(node, Statement) and node.kind in ('label', 'goto', 'return', 'condition'):
            error('E_CONDITION_ACTION', 'Handler actions cannot define handlers, jump or RETURN', node.token)


@dataclass(frozen=True)
class TimerBinding:
    root: str | None
    protection_root: str | None
    private: bool
    local: bool
    formal: bool

    @property
    def scoped(self):
        return self.local or self.formal

    @property
    def provenance(self):
        if self.private:
            return 'private_temporary'
        if self.formal:
            return 'borrowed_formal'
        if self.local:
            return 'routine_local'
        return 'declared_storage'


class HandlerAnalysis:
    """Check timer and handler effects against the current compiler scope."""

    def check_connected_timer_target(self, target):
        root = self.root_name(target)
        protection = self.protection_root(target)
        private = protection in self.private_using_roots
        routine = self.current_routine if not private else None
        local = routine is not None and any(token.value == root for token, _ in routine.declarations)
        formal = routine is not None and any(token.value == root for token, _ in routine.parameters)
        if not private and not local and not formal and root is None:
            self.error('E_TIMER_SCOPE',
                       'Connected timer storage requires a declared global/local/formal root or captured private USING record',
                       target.token)
        if protection in self.active_counters:
            self.error('E_FOR_COUNTER', 'Timer cannot modify active FOR counter', target.token)
        return TimerBinding(root, protection, private, local, formal)

    def check_connected_timer_schema(self, target, spec):
        if spec != ('INTEGER',) or self.is_value_only_subfield(target):
            self.error('E_TYPE', 'Timer requires ordinary INTEGER storage', target.token)

    def _timer_owner_matches_counter(self, owner, name, current_local):
        if owner is not None and any(token.value == name for token, _ in owner.parameters):
            return False
        local = owner is not None and any(token.value == name for token, _ in owner.declarations)
        return current_local == local and (not current_local or owner is self.current_routine)

    def _service_writes_counter(self, call, name):
        outputs = ()
        if call.value in BUILTIN_PROCEDURES:
            outputs = call.args[-1:]
        elif call.value == 'CNV_STR_CONF':
            outputs = call.args[1:3]
        elif call.value in MULTI_OUTPUT_PROCEDURES | CONFIG_TEXT_PROCEDURES | TIME_TEXT_PROCEDURES:
            outputs = call.args[1:]
        elif call.value in REGISTER_PROCEDURES:
            outputs = call.args[1:] if call.value == 'GET_REG' else call.args[2:]
        if any(self.protection_root(value) == name for value in outputs):
            return True
        signature = ex.signature_for(call.value, len(call.args))
        return any(mode in ('o', 'r', 'm') and self.protection_root(value) == name
                   for value, (mode, _) in zip(call.args, signature))

    def _handler_call_writes_counter(self, call, name):
        if name not in self.private_using_roots and ex.variable_write_call(call.value, call.args):
            return True
        routine = self.routines.get(call.value)
        if routine is None:
            return self._service_writes_counter(call, name)
        if name in routine.global_writes:
            return True
        if name in self.types and self.types[name][0] not in INTEGRAL_TYPES and routine.name in self.external_write_routines:
            return True
        return any(formal.value in routine.parameter_writes and self.protection_root(value) == name
                   and self.argument_is_reference(value, expected)
                   for (formal, expected), value in zip(routine.parameters, call.args))

    def _handler_action_writes_counter(self, action, name):
        if isinstance(action, Statement):
            if action.kind in ('assign', 'for'):
                return self.protection_root(action.args[0]) == name
            if action.kind == 'read':
                return any(self.protection_root(item.args[0] if item.kind == 'read_item' else item) == name
                           for item in action.args if item.kind != 'read_cr')
        if isinstance(action, Expr) and action.kind == 'call':
            return self._handler_call_writes_counter(action, name)
        return False

    def implicit_counter_write(self, name):
        """Find timer or handler effects that may run while a FOR counter is active."""
        current_local = self.current_routine is not None and any(
            token.value == name for token, _ in self.current_routine.declarations)
        for owner in (None, *self.program.routines):
            body = self.program.body if owner is None else owner.body
            for node in self.walk_nodes(body):
                if not isinstance(node, Statement):
                    continue
                if node.kind == 'timer_connect' and self.protection_root(node.args[0]) == name:
                    if self._timer_owner_matches_counter(owner, name, current_local):
                        return True
                elif node.kind == 'condition' or (node.kind == 'motion' and node.args[2] and node.body):
                    if any(self._handler_action_writes_counter(action, name) for action in self.walk_nodes(node.body)):
                        return True
        return False
