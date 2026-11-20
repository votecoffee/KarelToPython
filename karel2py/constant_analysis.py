"""Evaluate scoped constants and order their dependencies before type resolution."""
from . import runtime as rt
from .compiler_language import (
    BUILTIN_SIGNATURES,
    CONSTANT_BUILTINS,
    MAX_CONSTANT_BUILTIN_CALLS,
    MAX_CONSTANT_BUILTIN_DEPTH,
    PREDEFINED_CONSTANTS,
)


SCALAR_CONSTANT_TYPES = {bool: 'BOOLEAN', int: 'INTEGER', float: 'REAL', str: 'STRING'}


class ConstantAnalysis:
    """Resolve pure scalar constants and record how each value was evaluated."""

    def initialize_constant_analysis(self):
        self.constant_dependency_uses = []
        self.constant_resolution_order = []
        self.constant_builtin_uses = []
        self._constant_builtin_cache = {}
        self._constant_builtin_depth = 0
        self._constant_declaration = None

    def visible_constants(self):
        """Return the constants available in the current source scope."""
        if self.current_routine:
            return self.constants | self.current_routine.local_constants
        return self.constants

    @staticmethod
    def is_minimum_literal(expr):
        if expr.kind != 'unary' or expr.value != '-':
            return False
        child = expr.args[0]
        while child.kind == 'group':
            child = child.args[0]
        return child.kind == 'literal' and type(child.value) is int and child.value == 2147483648

    def constant(self, expr):
        kind = expr.kind
        try:
            if kind == 'literal':
                return expr.value
            if kind == 'predefined':
                return PREDEFINED_CONSTANTS[expr.value]
            if kind == 'real_literal':
                return rt.real_literal(expr.value)
            if kind == 'group':
                return self.constant(expr.args[0])
            if kind == 'name':
                visible = self.visible_constants()
                if expr.value in visible:
                    return visible[expr.value]
            if self.mode == 'pythonic' and kind == 'call' and expr.value in CONSTANT_BUILTINS:
                return self.constant_builtin(expr)
            if self.is_minimum_literal(expr):
                self.error('E_MININT_LITERAL', 'The manual requires MININT instead of the INTEGER literal -2147483648', expr.token)
            if kind == 'unary':
                return rt.unary(expr.value, self.constant(expr.args[0]))
            if kind == 'binary':
                return rt.binary(expr.value, *(self.constant(argument) for argument in expr.args))
        except rt.KarelRuntimeError as exc:
            self.error('E_CONSTANT', str(exc), expr.token)
        self.error('E_CONSTANT', 'Expected a literal or previously declared constant expression', expr.token)

    def constant_builtin(self, expr):
        """Evaluate scalar calls from the bounded pure built-in allowlist."""
        name, token = expr.value, expr.token
        signature, _ = BUILTIN_SIGNATURES[name]
        if len(expr.args) != len(signature):
            self.error('E_CONSTANT', f'{name} requires {len(signature)} constant arguments', token)
        if self._constant_builtin_depth >= MAX_CONSTANT_BUILTIN_DEPTH:
            self.error('E_CONSTANT', 'Compile-time built-in call nesting limit reached', token)
        self._constant_builtin_depth += 1
        try:
            values = [self.constant(argument) for argument in expr.args]
        finally:
            self._constant_builtin_depth -= 1
        if any(type(value) not in SCALAR_CONSTANT_TYPES for value in values):
            self.error('E_CONSTANT', 'Compile-time built-ins require scalar constant arguments', token)
        routine = self.current_routine.name if self.current_routine else None
        key = (routine, token.line, token.column, name, tuple((type(value), value) for value in values))
        if key in self._constant_builtin_cache:
            return self._constant_builtin_cache[key]
        if len(self._constant_builtin_cache) >= MAX_CONSTANT_BUILTIN_CALLS:
            self.error('E_CONSTANT', 'Compile-time built-in evaluation limit reached', token)
        value = rt.builtin(name, values, token.line)
        if type(value) not in SCALAR_CONSTANT_TYPES:
            self.error('E_CONSTANT', 'Compile-time built-ins must return scalar data', token)
        self._constant_builtin_cache[key] = value
        self.constant_builtin_uses.append(dict(
            function=name, scope='routine' if routine else 'module', routine=routine,
            constant=self._constant_declaration, line=token.line, column=token.column,
            argument_types=[SCALAR_CONSTANT_TYPES[type(argument)] for argument in values],
            result_type=SCALAR_CONSTANT_TYPES[type(value)], evaluated_at_translation=True, runtime_call=False))
        self.features.update(('pure scalar compile-time built-in calls', name))
        return value

    def checked_constant_declaration(self, token, expr):
        value = self.constant(expr)
        if type(value) is int:
            try:
                rt.integer(value)
            except rt.KarelRuntimeError as exc:
                self.error('E_CONSTANT', str(exc), token)
        return value

    def _constant_references(self, expr):
        references = []
        pending = [expr]
        while pending:
            node = pending.pop()
            if node.kind == 'name':
                references.append(node)
            elif node.kind in ('group', 'unary', 'binary') or node.kind == 'call' and node.value in CONSTANT_BUILTINS:
                pending.extend(reversed(node.args))
            elif node.kind not in ('literal', 'real_literal', 'predefined'):
                self.error('E_CONSTANT', 'CONST permits only scalar operators and whitelisted pure built-ins over visible constants', node.token)
        return references

    def _record_constant_dependency(self, name, reference, definitions, global_tokens, scope, routine):
        dependency, token = reference.value, reference.token
        local = dependency in definitions
        if not local and dependency not in self.constants:
            self.error('E_CONSTANT', dependency + ' is not a visible declared constant', token)
        dependency_token = definitions[dependency][0] if local else global_tokens[dependency]
        forward = (dependency_token.line, dependency_token.column) > (token.line, token.column)
        self.constant_dependency_uses.append(dict(
            scope=scope, routine=routine, name=name, dependency=dependency,
            dependency_scope=scope if local else 'module', line=token.line, column=token.column, forward=forward))

    def _fold_named_constant(self, name, token, expr):
        previous = self._constant_declaration
        self._constant_declaration = name
        try:
            return self.checked_constant_declaration(token, expr)
        finally:
            self._constant_declaration = previous

    def resolve_constants(self, declarations, target, routine=None):
        """Fold each declaration after visiting its local dependencies."""
        definitions = {token.value: (token, expr) for token, expr in declarations}
        references = {name: self._constant_references(expr) for name, (_, expr) in definitions.items()}
        global_tokens = {token.value: token for token, _ in self.program.constants}
        scope = 'routine' if routine else 'module'
        complete = set()
        for start in definitions:
            if start in complete:
                continue
            stack = [(start, iter(references[start]))]
            positions = {start: 0}
            while stack:
                name, children = stack[-1]
                reference = next(children, None)
                if reference is None:
                    token, expr = definitions[name]
                    target[name] = self._fold_named_constant(name, token, expr)
                    self.constant_resolution_order.append(dict(scope=scope, routine=routine, name=name))
                    complete.add(name)
                    stack.pop()
                    del positions[name]
                    continue
                dependency = reference.value
                self._record_constant_dependency(name, reference, definitions, global_tokens, scope, routine)
                if dependency not in definitions or dependency in complete:
                    continue
                if dependency in positions:
                    cycle = [item for item, _ in stack[positions[dependency]:]] + [dependency]
                    shown = cycle if len(cycle) <= 32 else cycle[:31] + ['...', dependency]
                    self.error('E_CONSTANT', 'Cyclic CONST dependency: ' + ' -> '.join(shown), reference.token)
                positions[dependency] = len(stack)
                stack.append((dependency, iter(references[dependency])))
        # Keep declaration order in the generated module and report fold order separately.
        ordered = {name: target[name] for name in definitions}
        target.clear()
        target.update(ordered)
        if any(row['forward'] for row in self.constant_dependency_uses):
            self.features.add('forward CONST dependency resolution')
