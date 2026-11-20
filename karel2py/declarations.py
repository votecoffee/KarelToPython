"""Validate declaration scopes and resolve source schemas."""
from .compiler_language import (
    DATA_RECORD_TYPES,
    NARROW_TYPES,
    POSITIONAL_VALUE_TYPES,
    blocked_controller_names,
)
from .lexer import Token
from . import extended as ex
from . import runtime as rt


class DeclarationPasses:
    """Declaration passes shared with the checked Python emitter during migration."""

    def resolve_spec(self, spec):
        if spec[0] in rt.ASSOCIATION_TYPES and self.mode!='pythonic':
            self.error('E_TYPE','Association records require Pythonic mode',Token('NAME',spec[0],1,1))
        if spec[0]=='GROUPED':
            group=self.constant(spec[2])
            if type(group) is not int or not 1<=group<=32: self.error('E_POSITION_GROUP','Group must be an INTEGER in 1..32',spec[3])
            resolved=self.resolve_spec(spec[1])
            if resolved[0]=='COMMON_ASSOC':self.error('E_POSITION_GROUP','COMMON_ASSOC does not have a group qualifier',spec[3])
            self.group_uses.append(dict(group=group,type=resolved[0],line=spec[3].line,column=spec[3].column))
            self.features.add('explicit group metadata'); return resolved
        if spec[0] in ('FILE','QUEUE_TYPE'): return spec
        if spec[0]=='PATH':
            resolved=('PATH',self.resolve_spec(spec[1]) if spec[1] else None,self.resolve_spec(spec[2]) if spec[2] else None)
            if resolved[1]==rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']:
                resolved=('PATH',None,resolved[2])
            if any(item and item[0]!='STRUCTURE' for item in resolved[1:]):
                self.error('E_TYPE','PATH NODEDATA and PATHHEADER require named STRUCTURE types',spec[3] if len(spec)>3 else Token('NAME','PATH',1,1))
            return resolved
        if spec[0] == 'JOINTPOS':
            rt.joint_width(spec)
            self.features.add('JOINTPOS data')
            return spec
        if spec[0] in ('INTEGER', 'BOOLEAN', 'REAL', 'BYTE', 'SHORT'):
            if spec[0] in NARROW_TYPES: self.features.add(spec[0] + ' storage')
            return spec
        if spec[0] == 'NAMED':
            token = spec[1]
            if self.mode == 'pythonic' and token.value in rt.PREDEFINED_STRUCTURES:
                row=dict(name=token.value,line=token.line,column=token.column)
                if row not in self.predefined_structure_uses: self.predefined_structure_uses.append(row)
                self.features.add('predefined STRUCTURE data layout')
                return rt.PREDEFINED_STRUCTURES[token.value]
            if token.value not in self.user_types:
                self.error('E_TYPE', f'{token.value} is not a previously defined supported type', token)
            return self.user_types[token.value]
        if spec[0] in DATA_RECORD_TYPES:
            self.features.add(spec[0] + ' data record')
            return spec
        if spec[0] == 'STRUCTURE': return spec
        if spec[0] == 'ARRAY':
            return self.resolve_array_storage(spec)
        # Sized STRING is the remaining schema.
        if spec[1] is None:
            return spec
        size = self.constant(spec[1])
        if type(size) is not int or not 1 <= size <= 254:
            self.error('E_SIZE', 'STRING size must be INTEGER in 1..254', spec[1].token)
        return ('STRING', size)

    def note_string_formal(self,spec,resolved,token,routine):
        terminal=spec[2] if spec[0]=='ARRAY' else spec
        if terminal[0]!='STRING' or terminal[1] is None:return
        capacity=resolved[2][1] if resolved[0]=='ARRAY' else resolved[1]
        self.features.add('direct bounded STRING formal constraints')
        self.string_formal_uses.append(dict(routine=routine,parameter=token.value,line=token.line,column=token.column,
            type_spec=resolved,capacity=capacity,container='ARRAY' if spec[0]=='ARRAY' else 'scalar',interface_scope='module',
            semantics='Existing exact reference/private bounded value contracts; no storage allocation or resize'))

    def validate_symbols(self):
        names = set()
        for token, expr in self.program.constants:
            if token.value in ex.PORT_TYPES: self.error('E_DUPLICATE','Port identifiers cannot be constants',token)
            if token.value in names: self.error('E_DUPLICATE', 'Duplicate declaration', token)
            names.add(token.value)
            if self.mode!='pythonic':
                self.constants[token.value] = self.checked_constant_declaration(token, expr)
        if self.mode=='pythonic':self.resolve_constants(self.program.constants,self.constants)
        self.resolve_type_definitions(names)
        for token, spec in self.program.declarations:
            if token.value in names: self.error('E_DUPLICATE', 'Duplicate declaration', token)
            if token.value in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys():
                self.error('E_CONTROLLER', 'Controller identifiers are not supported', token)
            names.add(token.value)
            resolved = self.resolve_global_spec(token, spec)
            if self.mode!='pythonic' and resolved[0] in NARROW_TYPES:
                self.error('E_TYPE', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
            self.types[token.value] = resolved
        self.check_used_array_shapes()
        for routine in self.program.routines:
            if routine.name in names: self.error('E_DUPLICATE', 'Duplicate declaration', routine.token)
            names.add(routine.name)
            self.routines[routine.name] = routine
            if routine.return_type and routine.return_type[0]=='GROUPED':
                routine.return_type=self.resolve_spec(routine.return_type)
            if routine.return_type and routine.return_type[0] == 'STRING':
                routine.return_type = self.resolve_spec(routine.return_type)
                self.features.add('STRING function result')
            if routine.return_type and routine.return_type[0] == 'NAMED':
                result_token = routine.return_type[1]
                definition_token = next((token for token, _ in self.program.user_types if token.value == result_token.value), None)
                if self.mode!='pythonic' and definition_token and (definition_token.line, definition_token.column) > (routine.token.line, routine.token.column):
                    self.error('E_TYPE', 'Named result types must be declared before the routine', result_token)
                routine.return_type = self.resolve_spec(routine.return_type)
                allowed_named_results = ('STRUCTURE',)
                if self.mode == 'pythonic':
                    allowed_named_results += ('ARRAY', 'STRING', 'INTEGER', 'BOOLEAN', 'REAL', 'PATH', 'QUEUE_TYPE', *NARROW_TYPES, *DATA_RECORD_TYPES, 'JOINTPOS')
                if routine.return_type[0] not in allowed_named_results:
                    message = ('BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields' if self.mode == 'pythonic'
                               else 'Named ARRAY function results remain blocked; a named result type must be a STRUCTURE')
                    self.error('E_RETURN_TYPE', message, routine.token)
                self.features.add('named ' + routine.return_type[0] + ' function result')
                if routine.return_type[0] == 'STRING': self.features.add('STRING function result')
            if self.mode=='pythonic' and routine.return_type and routine.return_type[0] in ('PATH','QUEUE_TYPE'):
                routine.return_type=self.resolve_spec(routine.return_type)
                self.features.add('logical scalar collection function result')
            if routine.return_type == ('VECTOR',): self.features.add('VECTOR function result')
            if routine.return_type and routine.return_type[0] == 'ARRAY':
                routine.return_type = self.resolve_routine_array_result(routine)
            if routine.return_type and routine.return_type[0] in POSITIONAL_VALUE_TYPES:
                self.features.add('exact positional function result')
        for routine in self.program.routines:
            # Parameters are resolved before local declarations: local constants
            # cannot alter the routine's interface or a global type definition.
            for token, spec in routine.parameters:
                if token.value in routine.local_types or token.value in self.constants or token.value in self.user_types or token.value in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys():
                    self.error('E_DUPLICATE', 'Duplicate, constant-shadowing or controller local identifier', token)
                resolved = self.resolve_array_parameter_spec(spec,token,routine.name) if self.mode=='pythonic' else self.resolve_spec(spec)
                if self.mode=='pythonic':self.note_string_formal(spec,resolved,token,routine.name)
                if self.mode!='pythonic' and resolved[0] in NARROW_TYPES:
                    self.error('E_PARAMETERS', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
                routine.local_types[token.value] = resolved
            routine.parameters = [(token, routine.local_types[token.value]) for token, _ in routine.parameters]
            self.current_routine = routine
            if self.mode=='pythonic':
                local_names=set(routine.local_types)
                for kind,token,definition in routine.local_declarations:
                    if (token.value in local_names or token.value in self.constants or token.value in self.user_types
                            or token.value in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys()):
                        self.error('E_DUPLICATE','Duplicate, constant-shadowing or controller local identifier',token)
                    local_names.add(token.value)
                    if kind=='CONST' and (token.value in names or token.value==self.program.name):
                        self.error('E_LOCAL_CONST_SHADOW','Local constants that shadow global declarations need namespace evidence',token)
                self.resolve_constants([(token,definition) for kind,token,definition in routine.local_declarations if kind=='CONST'],routine.local_constants,routine.name)
                if routine.local_constants:self.features.add('routine-local CONST')
            for kind, token, definition in routine.local_declarations:
                if self.mode=='pythonic' and kind=='CONST':continue
                if (token.value in routine.local_types or token.value in routine.local_constants
                        or token.value in self.constants or token.value in self.user_types
                        or token.value in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys()):
                    self.error('E_DUPLICATE', 'Duplicate, constant-shadowing or controller local identifier', token)
                if kind == 'CONST':
                    if token.value in names or token.value == self.program.name:
                        self.error('E_LOCAL_CONST_SHADOW', 'Local constants that shadow global declarations need namespace evidence', token)
                    routine.local_constants[token.value] = self.checked_constant_declaration(token, definition)
                    self.features.add('routine-local CONST')
                else:
                    resolved = self.resolve_spec(definition)
                    if self.mode!='pythonic' and resolved[0] in NARROW_TYPES:
                        self.error('E_TYPE', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
                    routine.local_types[token.value] = resolved
            self.current_routine = None
        self.constant_dependency_uses.sort(key=lambda row:(row['line'],row['column']))
