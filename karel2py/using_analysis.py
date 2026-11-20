"""Resolve enclosing USING aliases and record their selector capture plans."""
from . import runtime as rt
from .compiler_language import DATA_RECORD_TYPES, RECORD_TYPES
from .control_flow import counter_text
from .syntax import Expr, Statement


def _selector_text(expr):
    if expr.kind in ('system_pose', 'system_selection'):
        return counter_text(expr)
    if expr.kind == 'using_ref':
        return expr.value[4]
    if expr.kind == 'field':
        return _selector_text(expr.args[0]) + '.' + expr.value
    if expr.kind == 'index':
        indexes = ','.join(_selector_text(arg) for arg in expr.args[1:])
        return _selector_text(expr.args[0]) + '[' + indexes + ']'
    if expr.kind == 'group':
        return '(' + _selector_text(expr.args[0]) + ')'
    if expr.kind == 'call':
        return expr.value + '(' + ','.join(_selector_text(arg) for arg in expr.args) + ')'
    if expr.kind == 'binary':
        return '(' + _selector_text(expr.args[0]) + expr.value + _selector_text(expr.args[1]) + ')'
    if expr.kind == 'unary':
        return expr.value + '(' + _selector_text(expr.args[0]) + ')'
    return str(expr.value)


def _copy_path(expr, token):
    return Expr(expr.kind, token, expr.value, [_copy_path(child, token) for child in expr.args])


def _data_only(spec):
    if spec[0] in ('FILE', 'PATH', 'QUEUE_TYPE'):
        return False
    if spec[0] == 'ARRAY':
        return _data_only(spec[2])
    return spec[0] not in RECORD_TYPES or all(_data_only(field) for _, field in rt.record_fields(spec))


class UsingNormalization:
    """Bind lexical fields before routine effects and control flow are checked."""

    def resolve_using_fields(self):
        self.program.body = self._resolve_using(self.program.body)
        for routine in self.program.routines:
            self.current_routine = routine
            routine.body = self._resolve_using(routine.body)
        self.current_routine = None

    def _resolve_selector_names(self, expr):
        # USING needs the selector schema before the general bare-call pass.
        expr = self.resolve_bare_function_name(expr)
        expr.args = [self._resolve_selector_names(child) for child in expr.args]
        return expr

    def _resolve_using(self, node, bindings=None, scope=None):
        if isinstance(node, Expr):
            if bindings and node.kind == 'name' and node.value in bindings:
                if self.mode == 'strict' and node.value in self.visible_constants():
                    self.error('E_USING_CONST_SHADOW', 'Constants whose names coincide with USING fields need namespace validation', node.token)
                variable = bindings[node.value]
                scope['resolved_uses'].append(dict(field=node.value, variable=_selector_text(variable),
                                                   line=node.token.line, column=node.token.column))
                # Insert a qualified path without resolving its root as another alias.
                return Expr('field', node.token, node.value, [_copy_path(variable, node.token)])
            if self.mode == 'strict' and bindings and node.kind == 'call' and node.value in bindings:
                self.error('E_USING_CALL_SHADOW', 'Calls whose names coincide with USING fields need namespace validation', node.token)
            node.args = [self._resolve_using(argument, bindings, scope) for argument in node.args]
        elif isinstance(node, Statement):
            if node.kind == 'using':
                return self._resolve_using_block(node, bindings, scope)
            if self.mode != 'pythonic' and bindings and node.kind == 'for' and node.args[0].value in bindings:
                self.error('E_USING_FOR_COUNTER', 'FOR counters shadowed by USING fields need field-counter semantics', node.args[0])
            node.args = [self._resolve_using(argument, bindings, scope) for argument in node.args]
            node.body = self._resolve_using(node.body, bindings, scope)
            node.alternate = self._resolve_using(node.alternate, bindings, scope)
        elif isinstance(node, list):
            return [self._resolve_using(child, bindings, scope) for child in node]
        elif isinstance(node, tuple):
            return tuple(self._resolve_using(child, bindings, scope) for child in node)
        return node

    def _using_record_schema(self, selector, spec):
        if self.mode == 'pythonic' and spec[0] == 'PATH':
            if spec[2] is None:
                self.error('E_USING_TYPE', 'USING PATH requires an explicit PATHHEADER', selector.token)
            record = spec[2]
            self.features.add('PATH header USING selector')
        else:
            record = spec
        if record[0] not in (RECORD_TYPES if self.mode == 'pythonic' else ('STRUCTURE',)):
            self.error('E_USING_TYPE', 'USING requires STRUCTURE, a supported record or explicit PATH header', selector.token)
        return record

    def _capture_using_selector(self, selector, spec, record, name):
        storage = selector
        while storage.kind == 'group':
            storage = storage.args[0]
        root = storage
        while root.kind in ('group', 'field', 'index'):
            root = root.args[0]
        reference = root.kind in ('name', 'using_ref')
        if not reference and not _data_only(record):
            self.error('E_USING_VALUE', 'Computed USING records require data without FILE/PATH/QUEUE resources', selector.token)
        source_root = self.root_name(selector) if reference else None
        protection_root = self.protection_root(selector) if reference else name
        if not reference:
            self.private_using_roots[protection_root] = record
        source_kind = 'storage_reference' if reference else 'computed_value'
        provenance = 'declared_storage' if source_root is not None else 'private_temporary'
        capture = dict(source_kind=source_kind, provenance=provenance, source_root=source_root,
                       expression_kind=selector.kind, independent_copy=not reference, copy_back=False)
        if spec[0] == 'PATH':
            capture.update(path_header=True, path_type_spec=spec, selected_type_spec=record)
        if reference:
            record_selector = self.path_record_selector(selector)
            if record_selector is not None:
                capture[record_selector] = True
        binding = Expr('using_ref', selector.token,
                       (name, record, source_root, self.is_position_read_only_access(storage),
                        _selector_text(selector), source_kind, provenance, protection_root))
        return binding, capture

    def _resolve_using_block(self, node, bindings, parent):
        if self.mode == 'strict' and parent is not None:
            self.error('E_USING_NESTED', 'Nested USING field priority needs additional evidence', node.token)
        fields = dict(bindings or {})
        selectors, source_selectors, captures, capture_names = [], [], [], []
        scope_id = len(self.using_scopes)
        for variable in node.args:
            selector = variable if isinstance(variable, Expr) else Expr('name', variable, variable.value)
            source_selectors.append(_selector_text(selector))
            # Sibling selectors resolve only against the enclosing USING bindings.
            selector = self._resolve_using(selector, bindings, parent)
            if self.mode == 'pythonic':
                selector = self._resolve_selector_names(selector)
                spec = self.relative_operand_type(selector)
            else:
                spec = self.access_type(selector)
            record = self._using_record_schema(selector, spec)
            binding = selector
            if self.mode == 'pythonic':
                name = f'_using_{scope_id}_{len(selectors)}'
                binding, capture = self._capture_using_selector(selector, spec, record, name)
                captures.append(capture)
                capture_names.append(name)
            for name, _ in rt.record_fields(record):
                fields[name] = binding
            selectors.append(selector)

        scope = dict(body=self.current_routine.name if self.current_routine else self.program.name,
                     line=node.token.line, column=node.token.column,
                     variables=[_selector_text(selector) for selector in selectors],
                     field_bindings={name: _selector_text(selector) for name, selector in fields.items()},
                     resolved_uses=[])
        if self.mode == 'pythonic':
            scope.update(id=scope_id, parent=parent['id'] if parent else None,
                         depth=parent['depth'] + 1 if parent else 0, source_selectors=source_selectors)
        self.using_scopes.append(scope)
        self.features.add('USING explicit field resolution')
        if parent:
            self.features.add('nested USING lexical scope')
        if any(selector.kind == 'field' for selector in selectors):
            self.features.add('qualified USING selector')
        node.args = selectors
        if self.mode == 'pythonic':
            node.using_captures = tuple(capture_names)
            node.using_capture_kinds = tuple(capture['source_kind'] for capture in captures)
            scope['capture_once'] = True
            scope['selector_captures'] = captures
            self.features.add('captured USING storage selectors')
            if any(capture['independent_copy'] for capture in captures):
                self.features.add('computed USING record values')
            if any(self.relative_operand_type(selector)[0] in DATA_RECORD_TYPES for selector in selectors):
                self.features.add('built-in record USING')
            scope['selector_types'] = [self.relative_operand_type(selector) for selector in selectors]
        node.body = self._resolve_using(node.body, fields, scope)
        return node
