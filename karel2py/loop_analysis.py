"""Check FOR counter storage and effects in the enclosing source scope."""
from dataclasses import dataclass

from . import runtime as rt
from .compiler_language import INTEGRAL_TYPES
from .syntax import Expr


@dataclass(frozen=True)
class ForCounterBinding:
    root: str
    schema: tuple
    path_root: bool
    private: bool


class LoopAnalysis:
    """Check counter ownership before lowering its selector and bounds."""

    def check_for_counter(self, counter):
        token = counter.token if isinstance(counter, Expr) else counter
        root = self.protection_root(counter)
        private = root in self.private_using_roots
        routine = self.current_routine
        declared_local = routine is not None and any(item.value == root for item, _ in routine.declarations)
        local_owner = routine.name if declared_local else None

        if (local_owner, root) in self.retained_timer_alias_roots:
            self.error('E_FOR_COUNTER', 'Counter root may be retained by a handler that can borrow it for a timer', token)
        if private and root in self.escaped_private_using_roots:
            self.error('E_FOR_COUNTER', 'Private USING counter root may have escaped through a potentially retained writable routine alias', token)
        if self.cooperative and self.implicit_counter_write(root):
            self.error('E_FOR_COUNTER', 'Condition action or connected timer may modify this FOR counter root', token)

        counter_types = self.types | (routine.local_types if routine else {}) | self.private_using_roots
        if root not in counter_types or root in self.visible_constants():
            self.error('E_FOR_COUNTER', 'FOR counter requires declared writable integral scalar storage', token)
        schema = counter_types[root]
        path_root = self.mode == 'pythonic' and rt.path_counter_root(schema)
        if path_root:
            if (local_owner, root) in self.retained_path_counter_roots or local_owner is None and self.unknown_path_counter_alias:
                self.error('E_FOR_COUNTER', 'PATH counter root may have a retained writable routine or dynamic alias', token)
            if local_owner is None and any(row[0] == root for row in self.program.imported_variables):
                self.error('E_FOR_COUNTER', 'PATH counters require an owned declared root; imported roots remain excluded', token)
        if not private and routine and routine.parameters and not declared_local:
            self.error('E_FOR_COUNTER', 'Parameterized routines require fresh local FOR counter roots until alias effects are validated', token)
        if root in self.active_counters:
            self.error('E_FOR_COUNTER', 'Nested loops cannot reuse an active FOR counter root', token)

        if self.mode == 'pythonic':
            if (schema[0] in ('FILE', 'QUEUE_TYPE') or rt.resource_array_type(schema) and not path_root
                    or self.is_value_only_subfield(counter)):
                self.error('E_FOR_COUNTER', 'FOR counters require ordinary integral leaves outside FILE/queue roots and CONFIG domains', token)
            if self.is_position_read_only_access(counter):
                self.error('E_POSITION_READ_ONLY', 'FOR counter storage is read-only', token)
        elif schema[0] != 'INTEGER':
            self.error('E_FOR_COUNTER', 'FOR counter must be an INTEGER variable', token)
        return ForCounterBinding(root, schema, path_root, private)

    def check_for_reference_schema(self, spec, token):
        if spec[0] not in INTEGRAL_TYPES:
            self.error('E_FOR_COUNTER', 'FOR counter requires an INTEGER, BYTE or SHORT scalar reference', token)

    def check_for_bound_effects(self, initial: Expr, final: Expr, token):
        if self.mode == 'strict' and (self.has_routine_call(initial) or self.has_routine_call(final)):
            self.error('E_EVALUATION_ORDER', 'FOR bounds with routine calls are blocked', token)

    def has_fresh_active_counters(self):
        local_roots = set(self.private_using_roots)
        if self.current_routine:
            local_roots.update(token.value for token, _ in self.current_routine.declarations)
        return self.active_counters <= local_roots

    def named_active_counters(self):
        return self.active_counters - self.private_using_roots.keys()
