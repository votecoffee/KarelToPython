"""Generate FOR counter capture and inclusive bounds for both control-flow engines."""
from dataclasses import dataclass

from .compiler_language import NARROW_TYPES
from .control_flow import counter_text
from .lexer import Token
from .loop_analysis import LoopAnalysis
from .syntax import Expr


@dataclass(frozen=True)
class ForOperands:
    counter: Expr | Token
    root: str
    reference: str | None
    initial: str
    final: str
    step: int

    def range_code(self, start, stop):
        return f'range({start}, {stop} + ({self.step}), {self.step})'


class LoopLowering(LoopAnalysis):
    """Keep reference initialization ahead of the final-bound snapshot."""

    def _for_reference(self, counter, binding):
        token = counter.token
        reference, spec = self.reference(counter)
        self.check_for_reference_schema(spec, token)
        if binding.path_root:
            reference = (f'_rt.path_for_reference(self._state.reference({binding.root!r},{token.line}),'
                         f'{binding.schema!r},{reference},{token.line})')
            self.features.add('captured PATH integral FOR counter')
        usage = dict(body=self.current_routine.name if self.current_routine else self.program.name,
                     line=token.line, column=token.column, selector=counter_text(counter), root=binding.root,
                     kind=counter.kind, captured_once=True, cleanup='selected_scalar', write_protection='whole_root')
        self.reference_for_uses.append(usage)
        if binding.path_root:
            usage.update(path_counter=True, root_type_spec=binding.schema, root_ownership='owned_declared_storage')
        if binding.private:
            usage.update(root=None, protection_root=binding.root, provenance='private_temporary')
            self.features.add('private USING '+spec[0]+' FOR counter')
        self.features.add('captured '+spec[0]+' FOR counter reference')
        return reference, spec

    def for_operands(self, stmt):
        counter, initial, final, direction = stmt.args
        binding = self.check_for_counter(counter)
        reference, spec = self._for_reference(counter, binding) if self.mode == 'pythonic' else (None, binding.schema)
        first = self.require_type(initial, 'INTEGER')
        last = self.require_type(final, 'INTEGER')
        if self.mode == 'pythonic' and spec[0] in NARROW_TYPES:
            reference = f'_rt.NarrowForCounter({reference},{counter.token.line})'
            last = f'_rt.for_bound({spec!r},{last},{final.token.line})'
            byte = spec[0] == 'BYTE'
            self.reference_for_uses[-1].update(counter_type=spec, bound_domain=[0,255] if byte else [-32768,32766],
                                               cleanup_marker='unknown_byte' if byte else 'uninitialized')
        self.check_for_bound_effects(initial, final, stmt.token)
        return ForOperands(counter, binding.root, reference, first, last, 1 if direction == 'TO' else -1)

    def capture_for_counter(self, operands, captured, line):
        self.line(f'{captured} = {operands.reference}')
        self.line(f'{captured}.set({operands.initial}, {line})')

    def emit_structured_for(self, stmt):
        operands = self.for_operands(stmt)
        line = stmt.token.line
        name = operands.counter.value
        stop, item = self.fresh(), self.fresh()
        if self.mode == 'pythonic':
            captured = self.fresh()
            self.capture_for_counter(operands, captured, line)
            self.line('try:')
            self.indent += 1
            start = f'_rt.require({captured}.raw(), {line})'
        else:
            self.line(f'self._state.set({name!r}, {operands.initial}, {line})')
            start = f'self._state.get({name!r})'
        self.line(f'{stop} = {operands.final}')
        self.line(f'for {item} in {operands.range_code(start, stop)}:')
        self.indent += 1
        self.line(f'self._state.tick({line})')
        if self.mode == 'pythonic':
            self.line(f'{captured}.set({item}, {line})')
        else:
            self.line(f'self._state.set({name!r}, {item}, {line})')
        self.active_counters.add(operands.root)
        self.block(stmt.body)
        self.active_counters.remove(operands.root)
        self.indent -= 1
        if self.mode == 'pythonic':
            self.indent -= 1
            self.line('finally:')
            self.indent += 1
            self.line(f'{captured}.clear()')
            self.indent -= 1
        else:
            self.line(f'self._state.clear({name!r})')
