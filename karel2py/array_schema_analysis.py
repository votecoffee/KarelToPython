"""Resolve ARRAY storage and routine interfaces without guessing dimensions."""
from math import prod

from . import runtime as rt
from .compiler_language import ARRAY_ELEMENTS, ARRAY_SCALARS, RECORD_TYPES
from .lexer import Token
from .syntax import Expr


_ARRAY_DIMENSION_ERROR = 'ARRAY dimension size must be INTEGER in 1..32767'
_ARRAY_LEAF_LIMIT = 32767


def _array_wildcard(dimension):
    return isinstance(dimension, Expr) and dimension.kind == 'array_wildcard'


class ArraySchemaAnalysis:
    """Resolve fixed, wildcard, and named ARRAY shapes at their declaration sites."""

    def _array_dimension(self, expression, message):
        size = self.constant(expression)
        if type(size) is not int or not 1 <= size <= 32767:
            self.error('E_SIZE', message, expression.token)
        return size

    def _allows_storage_element(self, element):
        return (element[0] in (*ARRAY_ELEMENTS, 'ARRAY')
                or self.mode == 'pythonic' and element[0] in ('FILE', 'PATH', 'QUEUE_TYPE'))

    def check_collection_array(self, spec, token):
        if self.mode == 'pythonic' and rt.collection_array_type(spec):
            from .storage import collection_array_cost
            try:
                collection_array_cost(spec)
            except (ValueError, rt.KarelRuntimeError) as exc:
                self.error('E_ARRAY_CAPACITY', str(exc), token)

    def resolve_array_storage(self, spec):
        dimensions = rt.array_shape(spec)
        wildcard = next((size for size in dimensions if _array_wildcard(size)), None)
        if wildcard is not None:
            self.error('E_VARIABLE_ARRAY_SCOPE', 'Variable-sized ARRAYs are supported only as direct global VAR declarations with explicit translation context; TYPE/fields/routine locals remain blocked', wildcard.token)
        element = self.resolve_spec(spec[2])
        if self.mode == 'pythonic':
            if element == ('FILE',):
                self.features.add('reference-only FILE ARRAY')
            if element[0] in ('PATH', 'QUEUE_TYPE') or rt.collection_array_type(element):
                self.features.add('reference-only collection ARRAY')
        if element[0] == 'ARRAY':
            if rt.array_identity(element) is None:
                self.error('E_NESTED_NAMED_ARRAY', 'Nested ARRAY elements require a separately named type', spec[2][1])
            self.features.add('ARRAY OF named ARRAY')
        if len(rt.array_dimensions(('ARRAY', spec[1], element))) > 3:
            self.error('E_ARRAY_RANK', 'Nested arrays support at most three logical dimensions', spec[2][1])
        if element[0] == 'STRUCTURE':
            self.features.add('ARRAY OF named STRUCTURE')
        if all(size is None for size in dimensions):
            return ('ARRAY', spec[1], element)

        token = dimensions[0].token
        multidimensional = isinstance(spec[1], tuple)
        if multidimensional:
            shape = tuple(self._array_dimension(dimension, _ARRAY_DIMENSION_ERROR) for dimension in dimensions)
            if prod(shape) > _ARRAY_LEAF_LIMIT:
                self.error('E_ARRAY_CAPACITY', 'Prototype arrays are limited to 32767 scalar elements in total', token)
            element_error = 'ARRAY elements require supported scalars or named STRUCTURE types'
        else:
            shape = self._array_dimension(dimensions[0], 'ARRAY size must be INTEGER in 1..32767')
            element_error = 'ARRAY elements require supported scalars or named STRUCTURE types; nested arrays are blocked'
        if not self._allows_storage_element(element):
            self.error('E_TYPE', element_error, token)
        result = ('ARRAY', shape, element)
        if rt.scalar_leaf_count(result) > _ARRAY_LEAF_LIMIT:
            self.error('E_ARRAY_CAPACITY', 'Prototype arrays are limited to 32767 scalar leaves including STRUCTURE fields', token)
        if multidimensional:
            self.features.add('multidimensional STRUCTURE ARRAY' if element[0] == 'STRUCTURE' else 'multidimensional scalar ARRAY')
        self.check_collection_array(result, token)
        return result

    def resolve_array_result_spec(self, spec, token):
        """Resolve anonymous result dimensions and preserve named ARRAY identity."""
        if rt.array_identity(spec) is not None:
            return spec
        element = self.resolve_spec(spec[2])
        dimensions = tuple(
            None if size is None or _array_wildcard(size)
            else self._array_dimension(size, 'ARRAY result dimensions require INTEGER in 1..32767 or *')
            for size in rt.array_shape(spec))
        if element[0] == 'ARRAY' and rt.array_identity(element) is None:
            self.error('E_NESTED_NAMED_ARRAY', 'ARRAY result components require a prior named ARRAY type', token)
        shape = dimensions[0] if len(dimensions) == 1 else dimensions
        result = ('ARRAY', shape, element)
        if len(rt.array_dimensions(result)) > 3:
            self.error('E_ARRAY_RANK', 'ARRAY results support at most three logical dimensions', token)
        minimum = tuple(1 if size is None else size for size in dimensions)
        if rt.scalar_leaf_count(('ARRAY', minimum, element)) > _ARRAY_LEAF_LIMIT:
            self.error('E_ARRAY_CAPACITY', 'ARRAY results are limited to 32767 scalar leaves', token)
        return result

    def resolve_routine_array_result(self, routine):
        spec = routine.return_type
        if self.mode == 'pythonic':
            resolved = self.resolve_array_result_spec(spec, routine.token)
        else:
            element = spec[2]
            if element[0] == 'NAMED':
                result_token = element[1]
                definition = next((token for token, _ in self.program.user_types if token.value == result_token.value), None)
                if definition and (definition.line, definition.column) > (routine.token.line, routine.token.column):
                    self.error('E_TYPE', 'Named result element types must be declared before the routine', result_token)
            resolved = self.resolve_spec(spec)
        element = resolved[2]
        leaf = rt.array_leaf_spec(element) if element[0] == 'ARRAY' else element
        if (leaf[0] not in (*ARRAY_SCALARS, *RECORD_TYPES, 'JOINTPOS')
                and not (self.mode == 'pythonic' and leaf[0] in ('PATH', 'QUEUE_TYPE'))):
            self.error('E_RETURN_TYPE', 'ARRAY result terminal elements require supported scalars, bounded STRINGs, records or exact-width joints', routine.token)
        if leaf[0] == 'STRING':
            self.features.add('bounded STRING ARRAY function result')
        rank = len(rt.array_shape(resolved))
        if rank > 1:
            self.features.add('multidimensional ARRAY function result')
        if element[0] == 'ARRAY':
            self.features.add('named-component ARRAY function result')
        elif rank == 1:
            self.features.add('1D aggregate ARRAY function result' if element[0] in (*RECORD_TYPES, 'JOINTPOS') else '1D scalar ARRAY function result')
        return resolved

    def resolve_array_parameter_spec(self, spec, token, routine):
        """Check fixed dimensions while leaving caller-supplied dimensions open."""
        if spec[0] != 'ARRAY':
            return self.resolve_spec(spec)
        element = self.resolve_spec(spec[2])
        dimensions = tuple(
            None if size is None
            else self._array_dimension(size, 'ARRAY formal dimensions require INTEGER in 1..32767 or *')
            for size in rt.array_shape(spec))
        if element[0] == 'ARRAY' and rt.array_identity(element) is None:
            self.error('E_NESTED_NAMED_ARRAY', 'ARRAY formal components require a named ARRAY type', token)
        shape = dimensions[0] if len(dimensions) == 1 else dimensions
        result = ('ARRAY', shape, element)
        logical = rt.array_dimensions(result)
        if len(logical) > 3:
            self.error('E_ARRAY_RANK', 'ARRAY formals support at most three logical dimensions', token)
        minimum = tuple(1 if size is None else size for size in dimensions)
        bounded = ('ARRAY', minimum[0] if len(minimum) == 1 else minimum, element)
        if rt.scalar_leaf_count(bounded) > _ARRAY_LEAF_LIMIT:
            self.error('E_ARRAY_CAPACITY', 'ARRAY formal minimum exceeds 32767 scalar leaves/descriptors', token)
        self.check_collection_array(bounded, token)
        if any(size is not None for size in dimensions):
            self.features.add('fixed and mixed ARRAY formal constraints')
            self.array_formal_uses.append(dict(routine=routine, parameter=token.value, line=token.line, column=token.column,
                type_spec=result, logical_dimensions=list(logical),
                fixed_dimensions=[index + 1 for index, size in enumerate(logical) if size is not None],
                wildcard_dimensions=[index + 1 for index, size in enumerate(logical) if size is None],
                interface_scope='module', runtime_shape='checked caller storage; no allocation or resize'))
        return result

    def resolve_global_spec(self, token, spec):
        """Apply explicit dimensions to the wildcards of a direct global ARRAY."""
        if spec[0] != 'ARRAY':
            return self.resolve_spec(spec)
        dimensions = rt.array_shape(spec)
        wildcards = [index for index, size in enumerate(dimensions) if _array_wildcard(size)]
        if not wildcards:
            return self.resolve_array_storage(spec)
        name = token.value
        if name not in self.array_shapes:
            self.error('E_ARRAY_SIZE', f'{name} requires explicit translate(array_shapes={{...}}) dimensions; preexisting/VR/KCL storage is not inferred', token)
        shape = self.array_shapes[name]
        if len(shape) != len(dimensions):
            self.error('E_ARRAY_CONTEXT', f'{name} external shape must match its {len(dimensions)} declared outer dimensions', token)

        resolved_dimensions, declared = [], []
        for index, dimension in enumerate(dimensions):
            if index in wildcards:
                declared.append('*')
                resolved_dimensions.append(Expr('literal', dimension.token, shape[index]))
            else:
                value = self._array_dimension(dimension, _ARRAY_DIMENSION_ERROR)
                if value != shape[index]:
                    self.error('E_ARRAY_CONTEXT', f'{name} dimension {index + 1} is declared {value}, but external shape specifies {shape[index]}', dimension.token)
                declared.append(value)
                resolved_dimensions.append(dimension)
        specialized = resolved_dimensions[0] if len(dimensions) == 1 else tuple(resolved_dimensions)
        resolved = self.resolve_array_storage(('ARRAY', specialized, spec[2]))
        self.variable_array_uses.append(dict(name=name, line=token.line, column=token.column,
                                            declared_dimensions=declared, resolved_outer_dimensions=list(shape),
                                            wildcard_dimensions=[index + 1 for index in wildcards],
                                            logical_dimensions=list(rt.array_dimensions(resolved))))
        self.features.add('externally sized static ARRAY')
        return resolved

    def check_used_array_shapes(self):
        used = {row['name'] for row in self.variable_array_uses}
        unused = set(self.array_shapes) - used
        if unused:
            self.error('E_ARRAY_CONTEXT', 'External shapes may name only direct global variable-sized ARRAYs; unused names: ' + ', '.join(sorted(unused)), Token('NAME', '<array_shapes>', 1, 1))
