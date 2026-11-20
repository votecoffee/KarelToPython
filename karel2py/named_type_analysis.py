"""Resolve named TYPE declarations and bound expanded data schemas."""
from . import runtime as rt
from .declaration_dependencies import resolve_dependencies


def _named_references(definition):
    pending = [definition] if isinstance(definition, tuple) else [spec for _, spec in reversed(definition)]
    references = []
    while pending:
        spec = pending.pop()
        if spec[0] == 'NAMED':
            references.append(spec[1])
        elif spec[0] == 'ARRAY':
            pending.append(spec[2])
        elif spec[0] == 'GROUPED':
            pending.append(spec[1])
        elif spec[0] == 'PATH':
            pending.extend(item for item in reversed(spec[1:3]) if item is not None)
    return references


class NamedTypeAnalysis:
    """Keep nominal ARRAY and record identity while checking TYPE declarations."""

    def initialize_named_type_analysis(self):
        self.type_aliases = []
        self.type_dependency_uses = []
        self.type_resolution_order = []
        self._type_schema_costs = {}

    def resolve_type_definition(self, token, definition):
        name = token.value
        if isinstance(definition, tuple):
            resolved = self.resolve_spec(definition)
            if definition[0] == 'ARRAY':
                self.user_types[name] = (*resolved, name)
                self.features.add('named ARRAY definition')
            else:
                self.user_types[name] = resolved
                self.type_aliases.append(dict(
                    name=name, line=token.line, column=token.column,
                    target=definition[1].value if definition[0] == 'NAMED' else definition[0],
                    resolved_spec=resolved))
                self.features.add('transparent TYPE alias')
            return

        fields = {}
        for member, spec in definition:
            if member.value in fields:
                self.error('E_DUPLICATE', 'Duplicate STRUCTURE field', member)
            resolved = self.resolve_spec(spec)
            if resolved[0] in ('FILE', 'PATH', 'QUEUE_TYPE') or rt.resource_array_type(resolved):
                self.error('E_TYPE', 'Resource fields in STRUCTURE are not supported', member)
            fields[member.value] = resolved
        self.user_types[name] = ('STRUCTURE', name, tuple(fields.items()))
        self.features.add('named STRUCTURE definition')

    def check_type_schema(self, spec, token):
        """Count expanded leaves and levels while reusing costs for shared types."""
        costs = self._type_schema_costs
        pending = [(spec, False)]
        while pending:
            current, ready = pending.pop()
            identity = id(current)
            if identity in costs:
                continue
            kind = current[0]
            if kind == 'STRUCTURE':
                children = [field for _, field in current[2]]
            elif kind == 'ARRAY':
                children = [current[2]]
            else:
                children = []
            if children and not ready:
                pending.append((current, True))
                pending.extend((child, False) for child in reversed(children))
                continue
            if kind == 'STRUCTURE':
                count = sum(costs[id(child)][0] for child in children)
            elif kind == 'ARRAY':
                count = costs[id(current[2])][0]
                for dimension in rt.array_shape(current):
                    count *= dimension
            else:
                count = rt.scalar_leaf_count(current)
            depth = 1 + max((costs[id(child)][1] for child in children), default=0)
            if count > 32767:
                self.error('E_TYPE_CAPACITY', 'Resolved TYPE data exceeds 32767 scalar leaves', token)
            if depth > 64:
                self.error('E_TYPE_DEPTH', 'Resolved TYPE data exceeds 64 schema levels', token)
            costs[identity] = (count, depth)

    def resolve_type_definitions(self, names):
        definitions = {}
        for token, definition in self.program.user_types:
            if token.value in names:
                self.error('E_DUPLICATE', 'Duplicate declaration', token)
            names.add(token.value)
            definitions[token.value] = (token, definition)
            if self.mode != 'pythonic':
                self.resolve_type_definition(token, definition)
        if self.mode != 'pythonic':
            return

        references = {name: _named_references(definition) for name, (_, definition) in definitions.items()}

        def dependency_for(name, reference):
            dependency = reference.value
            if dependency in rt.PREDEFINED_STRUCTURES:
                return None
            if dependency not in definitions:
                self.error('E_TYPE', dependency + ' is not a declared supported type', reference)
            target = definitions[dependency][0]
            self.type_dependency_uses.append(dict(
                name=name, dependency=dependency, line=reference.line, column=reference.column,
                forward=(target.line, target.column) > (reference.line, reference.column)))
            return dependency

        def resolve(name):
            token, definition = definitions[name]
            self.resolve_type_definition(token, definition)
            self.check_type_schema(self.user_types[name], token)
            self.type_resolution_order.append(name)

        def on_cycle(reference, path):
            self.error('E_TYPE', 'Cyclic TYPE dependency: ' + path, reference)

        resolve_dependencies(references, dependency_for=dependency_for, resolve=resolve, on_cycle=on_cycle)
        self.user_types = {name: self.user_types[name] for name in definitions}
        self.type_aliases.sort(key=lambda row: (row['line'], row['column']))
        self.type_dependency_uses.sort(key=lambda row: (row['line'], row['column']))
        if any(row['forward'] for row in self.type_dependency_uses):
            self.features.add('forward TYPE dependency resolution')
