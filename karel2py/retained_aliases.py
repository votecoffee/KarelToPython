"""Track writable references that may survive routine return."""
from . import runtime as rt
from .syntax import Expr


class RetainedAliasAnalysis:
    """Record private, timer and PATH storage that later FORs cannot borrow."""

    def analyze_retained_aliases(self, private_retainers, handler_retainers, path_retainers):
        self._record_escaped_private_roots(private_retainers)
        self._record_retained_timer_roots(handler_retainers)
        self._record_retained_path_roots(path_retainers)

    def _retaining_calls(self, routine, retainers):
        self.current_routine = routine
        body = self.program.body if routine is None else routine.body
        for node in self.walk_nodes(body):
            if isinstance(node, Expr) and node.kind == 'call' and node.value in retainers:
                yield node, self.routines[node.value]

    def _record_escaped_private_roots(self, retainers):
        for routine in (None, *self.program.routines):
            for call, callee in self._retaining_calls(routine, retainers):
                for argument, (formal, expected) in zip(call.args, callee.parameters):
                    root = self.protection_root(argument)
                    if (root in self.private_using_roots and formal.value in callee.parameter_writes
                            and argument.kind in ('name', 'field', 'index')
                            and self.argument_is_reference(argument, expected)):
                        self.escaped_private_using_roots.add(root)

    def _record_retained_timer_roots(self, retainers):
        for routine in (None, *self.program.routines):
            locals_ = {token.value for token, _ in routine.declarations} if routine else set()
            formals = {token.value for token, _ in routine.parameters} if routine else set()
            for call, callee in self._retaining_calls(routine, retainers):
                for argument, (formal, expected) in zip(call.args, callee.parameters):
                    root = self.protection_root(argument)
                    if (formal.value not in callee.timer_parameter_writes or root in self.private_using_roots
                            or not self.argument_is_reference(argument, expected)):
                        continue
                    if root in locals_:
                        self.retained_timer_alias_roots.add((routine.name, root))
                    elif root in self.types and root not in formals:
                        self.retained_timer_alias_roots.add((None, root))

    def _record_retained_path_roots(self, retainers):
        for routine in (None, *self.program.routines):
            locals_ = {token.value for token, _ in routine.declarations} if routine else set()
            formals = {token.value for token, _ in routine.parameters} if routine else set()
            types = self.types | (routine.local_types if routine else {}) | self.private_using_roots
            for call, callee in self._retaining_calls(routine, retainers):
                for argument, (formal, expected) in zip(call.args, callee.parameters):
                    if formal.value not in callee.parameter_writes:
                        continue
                    if argument.kind == 'call' and argument.value == 'BYNAME':
                        self.unknown_path_counter_alias = True
                        continue
                    if not self.argument_is_reference(argument, expected):
                        continue
                    root = self.protection_root(argument)
                    if root not in types or not rt.path_counter_root(types[root]):
                        continue
                    if root in locals_:
                        self.retained_path_counter_roots.add((routine.name, root))
                    elif root in self.types and root not in formals:
                        self.retained_path_counter_roots.add((None, root))
