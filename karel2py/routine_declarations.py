"""Check routine signatures and resolve their lexical declarations."""
from . import extended as ex
from .compiler_language import DATA_RECORD_TYPES, NARROW_TYPES, POSITIONAL_VALUE_TYPES, blocked_controller_names


class RoutineDeclarations:
    """Register module-scope interfaces before resolving routine-local schemas."""

    def validate_routine_declarations(self, module_names):
        for routine in self.program.routines:
            if routine.name in module_names:
                self.error('E_DUPLICATE', 'Duplicate declaration', routine.token)
            module_names.add(routine.name)
            self.routines[routine.name] = routine
            self._resolve_routine_result(routine)

        for routine in self.program.routines:
            # The routine's local constants are visible only after its interface is resolved.
            self._resolve_routine_parameters(routine)
            self.current_routine = routine
            self._resolve_routine_locals(routine, module_names)
            self.current_routine = None
        self.constant_dependency_uses.sort(key=lambda row: (row['line'], row['column']))

    def _resolve_named_result(self, routine):
        token = routine.return_type[1]
        definition = next((key for key, _ in self.program.user_types if key.value == token.value), None)
        if (self.mode != 'pythonic' and definition
                and (definition.line, definition.column) > (routine.token.line, routine.token.column)):
            self.error('E_TYPE', 'Named result types must be declared before the routine', token)
        resolved = self.resolve_spec(routine.return_type)
        allowed = ('STRUCTURE',)
        if self.mode == 'pythonic':
            allowed += ('ARRAY', 'STRING', 'INTEGER', 'BOOLEAN', 'REAL', 'PATH', 'QUEUE_TYPE',
                        *NARROW_TYPES, *DATA_RECORD_TYPES, 'JOINTPOS')
        if resolved[0] not in allowed:
            message = ('BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields' if self.mode == 'pythonic'
                       else 'Named ARRAY function results remain blocked; a named result type must be a STRUCTURE')
            self.error('E_RETURN_TYPE', message, routine.token)
        self.features.add('named ' + resolved[0] + ' function result')
        if resolved[0] == 'STRING':
            self.features.add('STRING function result')
        return resolved

    def _resolve_routine_result(self, routine):
        if routine.return_type is None:
            return
        if routine.return_type[0] == 'GROUPED':
            routine.return_type = self.resolve_spec(routine.return_type)
        if routine.return_type[0] == 'STRING':
            routine.return_type = self.resolve_spec(routine.return_type)
            self.features.add('STRING function result')
        if routine.return_type[0] == 'NAMED':
            routine.return_type = self._resolve_named_result(routine)
        if self.mode == 'pythonic' and routine.return_type[0] in ('PATH', 'QUEUE_TYPE'):
            routine.return_type = self.resolve_spec(routine.return_type)
            self.features.add('logical scalar collection function result')
        if routine.return_type == ('VECTOR',):
            self.features.add('VECTOR function result')
        if routine.return_type[0] == 'ARRAY':
            routine.return_type = self.resolve_routine_array_result(routine)
        if routine.return_type[0] in POSITIONAL_VALUE_TYPES:
            self.features.add('exact positional function result')

    def _check_local_name(self, token, occupied, local_constants=()):
        name = token.value
        if (name in occupied or name in local_constants or name in self.constants or name in self.user_types
                or name in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys()):
            self.error('E_DUPLICATE', 'Duplicate, constant-shadowing or controller local identifier', token)

    def _check_local_constant_name(self, token, module_names):
        if token.value in module_names or token.value == self.program.name:
            self.error('E_LOCAL_CONST_SHADOW', 'Local constants that shadow global declarations need namespace evidence', token)

    def _note_string_formal(self, spec, resolved, token, routine):
        terminal = spec[2] if spec[0] == 'ARRAY' else spec
        if terminal[0] != 'STRING' or terminal[1] is None:
            return
        capacity = resolved[2][1] if resolved[0] == 'ARRAY' else resolved[1]
        self.features.add('direct bounded STRING formal constraints')
        self.string_formal_uses.append(dict(
            routine=routine, parameter=token.value, line=token.line, column=token.column,
            type_spec=resolved, capacity=capacity, container='ARRAY' if spec[0] == 'ARRAY' else 'scalar',
            interface_scope='module', semantics='Existing exact reference/private bounded value contracts; no storage allocation or resize'))

    def _resolve_routine_parameters(self, routine):
        for token, spec in routine.parameters:
            self._check_local_name(token, routine.local_types)
            if self.mode == 'pythonic':
                resolved = self.resolve_array_parameter_spec(spec, token, routine.name)
                self._note_string_formal(spec, resolved, token, routine.name)
            else:
                resolved = self.resolve_spec(spec)
                if resolved[0] in NARROW_TYPES:
                    self.error('E_PARAMETERS', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
            routine.local_types[token.value] = resolved
        routine.parameters = [(token, routine.local_types[token.value]) for token, _ in routine.parameters]

    def _resolve_forward_local_constants(self, routine, module_names):
        local_names = set(routine.local_types)
        constants = []
        for kind, token, definition in routine.local_declarations:
            self._check_local_name(token, local_names)
            local_names.add(token.value)
            if kind == 'CONST':
                self._check_local_constant_name(token, module_names)
                constants.append((token, definition))
        self.resolve_constants(constants, routine.local_constants, routine.name)
        if routine.local_constants:
            self.features.add('routine-local CONST')

    def _resolve_routine_locals(self, routine, module_names):
        if self.mode == 'pythonic':
            self._resolve_forward_local_constants(routine, module_names)
        for kind, token, definition in routine.local_declarations:
            if self.mode == 'pythonic' and kind == 'CONST':
                continue
            self._check_local_name(token, routine.local_types, routine.local_constants)
            if kind == 'CONST':
                self._check_local_constant_name(token, module_names)
                routine.local_constants[token.value] = self.checked_constant_declaration(token, definition)
                self.features.add('routine-local CONST')
            else:
                resolved = self.resolve_spec(definition)
                if self.mode != 'pythonic' and resolved[0] in NARROW_TYPES:
                    self.error('E_TYPE', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
                routine.local_types[token.value] = resolved
