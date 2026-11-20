"""Validate declaration scopes and resolve source schemas."""
from .compiler_language import (
    DATA_RECORD_TYPES,
    NARROW_TYPES,
    blocked_controller_names,
)
from .lexer import Token
from . import extended as ex
from . import runtime as rt


class DeclarationPasses:
    """Resolve source schemas and validate module declarations."""

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

    def validate_module_declarations(self):
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
        return names
