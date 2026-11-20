"""Lower storage reads, writable references, and checked subscript paths."""
from . import extended as ex
from . import runtime as rt


class ReferenceLowering:
    """Keep borrowable references and loaded values on their respective paths."""

    def reference(self, expr, *, config_read=False, allow_prefix=False, collection_prefix=False, collection_io=False):
        line = expr.token.line
        selection_root = expr
        while selection_root.kind in ('field', 'index', 'group'):
            selection_root = selection_root.args[0]
        if selection_root.kind == 'system_selection':
            self.error('E_SYSTEM_SELECTION_REFERENCE', 'Active frame/tool numbers cannot supply writable references', expr.token)
        if self.is_system_pose_path(expr):
            self.error('E_SYSTEM_POSE_READ_ONLY', 'Robot system poses cannot supply writable references', expr.token)
        if expr.kind == 'using_ref':
            return expr.value[0], expr.value[1]
        if expr.kind == 'group':
            return self.reference(expr.args[0], config_read=config_read, allow_prefix=allow_prefix,
                                  collection_prefix=collection_prefix, collection_io=collection_io)
        if expr.kind == 'name':
            if self.is_predefined_file(expr):
                return f'self._state.predefined_file_reference({expr.value!r},{line})', ('FILE',)
            return f'self._state.reference({expr.value!r}, {line})', self.symbol_type(expr)
        base, spec = self.expression(expr.args[0], raw=True)
        if expr.kind == 'field':
            member = self.member_type(spec, expr)
            helper = 'config_read_reference' if config_read else 'field_reference'
            return f'_rt.{helper}({base}, {expr.value!r}, {line})', member
        if spec[0] == 'PATH':
            index, selected = self._path_node_index(expr, spec)
            if self.path_header_index(expr.args[1]):
                return f'_rt.path_header_reference({base},{spec!r},{line})', selected
            return f'_rt.index_reference({base},{index},{line})', selected

        self._check_indexable_schema(expr, spec)
        count = len(expr.args) - 1
        prefix = allow_prefix and self.mode == 'pythonic' and rt.array_prefix_type(spec, count) is not None
        index, selected = self.index_code(expr, spec, allow_prefix=prefix, prefix_target=prefix,
                                          collection_prefix=collection_prefix)
        if prefix:
            resource = (collection_prefix or collection_io) and rt.collection_array_type(spec)
            helper = 'resource_array_prefix_reference' if collection_prefix and resource else 'array_prefix_target'
            check = ',check=self._state.tick' if collection_io and resource else ''
            return f'_rt.{helper}({base},{index},{spec!r},{line}{check})', selected
        if self.mode == 'pythonic' and rt.collection_array_node_type(spec, count) is not None:
            header = ',allow_header=True' if self.path_header_index(expr.args[-1]) else ''
            return f'_rt.collection_path_reference({base},{index},{spec!r},{line}{header})', selected
        if self.mode == 'pythonic' and rt.joint_axis_access(spec, count):
            return f'_rt.joint_index_reference({base},{index},{spec!r},{line})', selected
        return f'_rt.index_reference({base}, {index}, {line})', selected

    def _check_indexable_schema(self, expr, spec):
        if spec[0] != 'ARRAY' and not (self.mode == 'pythonic' and spec[0] == 'JOINTPOS'):
            self.error('E_TYPE', 'Indexing requires ARRAY or Pythonic JOINTPOS', expr.token)

    def _path_node_index(self, expr, spec):
        if len(expr.args) != 2:
            self.error('E_ARRAY_RANK', 'PATH requires one node index', expr.token)
        index = self.require_type(expr.args[1], 'INTEGER')
        return index, self.path_index_type(spec, expr.args[1])

    def index_code(self, expr, spec, *, allow_prefix=False, prefix_target=False, collection_prefix=False):
        indexes = expr.args[1:]
        if self.mode != 'pythonic' and expr.args[0].kind == 'index':
            self.error('E_ARRAY_RANK', 'Chained ARRAY indexes need grammar validation; use comma-separated subscripts', expr.token)
        count = len(indexes)
        pythonic = self.mode == 'pythonic'
        axis = pythonic and rt.joint_axis_access(spec, count)
        prefix = rt.array_prefix_type(spec, count) if allow_prefix and pythonic else None
        if prefix is not None and not (rt.aggregate_write_type(prefix) or collection_prefix and rt.collection_array_type(prefix)):
            self.error('E_ARRAY_RANK', 'ARRAY prefix values require resource-free data', expr.token)
        path_record = None
        if pythonic and rt.collection_array_node_type(spec, count) is not None:
            path_record = self.path_index_type(rt.array_leaf_spec(spec), indexes[-1])
        selected = ('REAL',) if axis else path_record
        if selected is None:
            selected = prefix
        if selected is None:
            try:
                selected = rt.indexed_type(spec, count)
            except rt.KarelRuntimeError as exc:
                self.error('E_ARRAY_RANK', str(exc), expr.token)
        if self.mode == 'strict' and count > 1 and any(self.has_routine_call(index) for index in indexes):
            self.error('E_EVALUATION_ORDER', 'Multiple ARRAY subscripts containing routine calls need evaluation-order validation', expr.token)
        codes = [self.require_type(index, 'INTEGER') for index in indexes]
        token = expr.token
        body = self.current_routine.name if self.current_routine else self.program.name
        if axis:
            self.features.add('checked joint axis access')
            self.joint_axis_uses.append(dict(
                body=body, line=token.line, column=token.column, source_type_spec=spec,
                joint_type_spec=rt.array_leaf_spec(spec), selected_type_spec=('REAL',),
                subscript_count=count, evaluated_once=True, declared_schema_checked=True))
        if count > 1:
            self.features.add('multidimensional ARRAY indexing')
        if prefix is not None:
            self.features.add('captured ARRAY prefix targets' if prefix_target else 'independent ARRAY prefix values')
            row = dict(body=body, line=token.line, column=token.column, source_type_spec=spec,
                       selected_type_spec=selected, supplied_subscripts=count, evaluated_once=True,
                       independent_value=not prefix_target)
            uses = self.array_prefix_target_uses if prefix_target else self.array_prefix_uses
            if row not in uses:
                uses.append(row)
        elif selected[0] == 'ARRAY':
            self.features.add('named subarray reference')
            self.subarray_uses.append(dict(body=body, line=token.line, column=token.column,
                                           supplied_subscripts=count, logical_rank=len(rt.array_dimensions(spec)),
                                           selected_type=rt.array_identity(selected)))
        code = codes[0] if count == 1 else '(' + ', '.join(codes) + ')'
        return code, selected

    def file_prefix_reference_code(self, argument):
        base, container = self.expression(argument.args[0], raw=True)
        codes = [self.require_type(index, 'INTEGER') for index in argument.args[1:]]
        return f'_rt.resource_array_prefix_reference({base},({", ".join(codes)},),{container!r},{argument.token.line})', container

    def lower_storage_read(self, expr, *, raw=False, collection_io=False):
        line = expr.token.line
        if expr.kind == 'using_ref':
            code = f'{expr.value[0]}.raw()'
            return (code if raw else f'_rt.require({code},{line})'), expr.value[1]
        if expr.kind == 'name':
            if self.is_predefined_file(expr):
                self.features.add('explicit predefined FILE binding')
                return f'self._state.predefined_file({expr.value!r},{line})', ('FILE',)
            spec = self.symbol_type(expr)
            if self.current_routine and expr.value in self.current_routine.local_constants:
                return repr(self.current_routine.local_constants[expr.value]), spec
            method = 'raw' if raw else 'get'
            args = repr(expr.value) if raw else f'{expr.value!r}, {line}'
            return f'self._state.{method}({args})', spec
        if expr.kind == 'field':
            base, spec = self.expression(expr.args[0], raw=True)
            member = self.member_type(spec, expr)
            method = 'raw_field' if raw else 'load_field'
            return f'_rt.{method}({base}, {expr.value!r}, {line})', member
        return self._lower_index_read(expr, raw=raw, collection_io=collection_io)

    def _lower_index_read(self, expr, *, raw, collection_io):
        line = expr.token.line
        receiver = expr.args[0]
        pythonic = self.mode == 'pythonic'
        if pythonic and receiver.kind == 'name' and receiver.value in ex.PORT_TYPES and receiver.value not in self.types:
            if len(expr.args) != 2:
                self.error('E_ARGUMENTS', 'Ports require one index', expr.token)
            index = self.require_type(expr.args[1], 'INTEGER')
            self.features.add('ports')
            return f'self._state.port_read({receiver.value!r},{index},{line})', (ex.PORT_TYPES[receiver.value],)
        base, spec = self.expression(receiver, raw=True)
        if spec[0] == 'PATH':
            index, selected = self._path_node_index(expr, spec)
            if self.path_header_index(expr.args[1]):
                value = f'_rt.path_header_reference({base},{spec!r},{line}).raw()'
                return (value if raw else f'_rt.require({value},{line})'), selected
            return f'{base}.node({index},{line})', selected
        self._check_indexable_schema(expr, spec)
        resource = pythonic and rt.collection_array_type(spec)
        index, selected = self.index_code(expr, spec, allow_prefix=True, collection_prefix=resource)
        count = len(expr.args) - 1
        if pythonic and rt.collection_array_node_type(spec, count) is not None:
            header = ',allow_header=True' if self.path_header_index(expr.args[-1]) else ''
            reference = f'_rt.collection_path_reference({base},{index},{spec!r},{line}{header})'
            return (reference + '.raw()' if raw else f'_rt.require({reference}.raw(),{line})'), selected
        if pythonic and rt.array_prefix_type(spec, count) is not None:
            if collection_io and resource:
                return f'_rt.resource_array_prefix_reference({base},{index},{spec!r},{line},check=self._state.tick).raw()', selected
            helper = 'collection_array_prefix_value' if resource else 'array_prefix_value'
            return f'_rt.{helper}({base},{index},{spec!r},{line})', selected
        if pythonic and rt.joint_axis_access(spec, count):
            code = f'_rt.joint_index_reference({base},{index},{spec!r},{line}).raw()'
            return (code if raw else f'_rt.real({code},{line})'), selected
        method = 'raw_index' if raw else 'load_index'
        return f'_rt.{method}({base}, {index}, {line})', selected
