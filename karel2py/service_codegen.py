"""Lower checked service operands in their original source order."""
from . import extended as ex
from . import runtime as rt
from .call_analysis import check_service_signature
from .call_reporting import record_service_call
from .compiler_language import INTEGRAL_TYPES, NARROW_TYPES, PREDEFINED_CONSTANTS, RECORD_TYPES


class ServiceCallLowering:
    """Emit service references, bounded arrays, and captured values."""

    def _bounded_service_argument(self, expr, limit, *, nullable):
        def locate(value):
            while value.kind == 'group':
                value = value.args[0]
            if not self.is_array_prefix_value(value):
                return self.expression(value, raw=nullable)
            base, spec = locate(value.args[0])
            index, selected = self.index_code(value, spec, allow_prefix=True)
            return f'_rt.service_array_view({base},{index},{spec!r},{value.token.line})', selected

        value, spec = locate(expr)
        line = expr.token.line
        return f'_rt.bounded_service_array({spec!r},{value},{limit},{line},check=lambda:self._state.tick({line}))', spec

    def _service_reference_argument(self, operand, token, kind, *, collection_prefix=False):
        prefix = self.mode == 'pythonic' and kind in ex.ARRAY_REFERENCE_KINDS and self.is_array_prefix_value(operand)
        allows_prefix = prefix or (self.mode == 'pythonic' and collection_prefix)
        code, schema = self.reference(operand, allow_prefix=allows_prefix, collection_prefix=collection_prefix)
        if prefix:
            code = f'_rt.array_prefix_reference({code},{token.line})'
        return code, schema

    def _service_value_argument(self, name, index, operand, ungrouped, passing, kind):
        set_var_value = name == 'SET_VAR' and index == 3
        variable_input = passing == 'v' or set_var_value
        reference_input = (
            variable_input and self.is_bare_storage(ungrouped) and not self.is_system_pose_path(ungrouped)
            and (not self.is_array_prefix_value(ungrouped)
                 or set_var_value and rt.collection_array_type(self.access_type(ungrouped.args[0])))
        )
        if reference_input:
            code, schema = self.reference(ungrouped, allow_prefix=set_var_value, collection_prefix=set_var_value)
        else:
            code, schema = self.expression(operand)
        line = operand.token.line
        if kind == 'GEOMETRY_POSE' and schema[0] == 'JOINTPOS':
            code = self.geometry_operand(code, schema, operand.token, name)
        if kind == 'REAL' and schema[0] in INTEGRAL_TYPES:
            code, schema = f'_rt.real({code},{line})', ('REAL',)
        if passing != 'v' and kind == 'INTEGER' and schema[0] in NARROW_TYPES:
            code, schema = f'_rt.integer({code},{line})', ('INTEGER',)
        check = ''
        if self.mode == 'pythonic' and set_var_value and schema[0] in ('PATH', 'QUEUE_TYPE', 'ARRAY', 'JOINTPOS', *RECORD_TYPES):
            check = f',check=lambda:self._state.tick({line})'
        if reference_input:
            code = f'_rt.variable_reference({code},{line}{check})'
        elif variable_input:
            code = f'_rt.variable_value({schema!r},{code},{line}{check})'
        elif self.mode == 'pythonic' and kind == 'PATH_NODE' and schema[0] == 'STRUCTURE':
            code = f'_rt.path_node_seed(self._state,{schema!r},{code},{line})'
        elif kind == 'ANY' or schema[0] in (*RECORD_TYPES, 'JOINTPOS', 'ARRAY'):
            code = f'_rt.service_value({code},{line})'
        return code, schema

    def _service_literal(self, operand, passing, kind):
        if kind == 'ERROR_CURSOR':
            sentinel = None
            if operand.kind == 'literal':
                sentinel = operand.value
            elif operand.kind == 'predefined':
                sentinel = PREDEFINED_CONSTANTS.get(operand.value)
            elif operand.kind == 'name':
                sentinel = self.visible_constants().get(operand.value)
            if type(sentinel) is int and sentinel == 2147483647:
                return '2147483647'
        if passing == 'm' and operand.kind == 'literal' and type(operand.value) is int and operand.value == 0:
            return '0'
        return None

    def service_call(self, expr):
        name = expr.value
        checked = check_service_signature(name, len(expr.args), expr.token, mode=self.mode, error=self.error)
        self.check_for_call(expr.token)
        if ex.variable_write_call(name, expr.args) and self.named_active_counters():
            self.error('E_FOR_COUNTER', name + ' cannot indirectly write an active FOR counter', expr.token)

        codes = []
        node_schema = None
        for index, (operand, (passing, kind)) in enumerate(zip(expr.args, checked.parameters)):
            ungrouped = operand
            while ungrouped.kind == 'group':
                ungrouped = ungrouped.args[0]
            if kind == 'TABLE_ACTION' and not self.is_bare_storage(ungrouped):
                code, schema = self.expression(operand)
                if schema != ('INTEGER',):
                    self.error('E_TYPE', 'ACT_TBL action requires INTEGER', operand.token)
                codes.append(code)
                continue
            literal = self._service_literal(ungrouped, passing, kind)
            if literal is not None:
                codes.append(literal)
                continue
            if passing == 's':
                self.check_static_service_storage(ungrouped, operand.token)
                code, schema = self._service_reference_argument(ungrouped, operand.token, kind)
            elif passing in ('o', 'r', 'm'):
                self.check_service_output_storage(operand)
                code, schema = self._service_reference_argument(
                    operand, operand.token, kind, collection_prefix=name == 'GET_VAR' and index == 3)
            elif self.mode == 'pythonic' and index == 1 and name in ('SEND_DATAPC', 'QUEUE_ATTACH', 'RMCN_SEND'):
                packet = name == 'SEND_DATAPC'
                code, schema = self._bounded_service_argument(ungrouped, 244 if packet else 32, nullable=packet)
            else:
                code, schema = self._service_value_argument(name, index, operand, ungrouped, passing, kind)
            node_schema = checked.check_operand(index, schema, operand.token, node_schema=node_schema, error=self.error)
            codes.append(code)

        record_service_call(self, name, expr.token)
        if name in ex.COOPERATIVE_PROCEDURES:
            return f'(yield from _rt.cooperative_service(self._state,{name!r},[{", ".join(codes)}],{expr.token.line}))'
        return f'self._state.extended_call({name!r},[{", ".join(codes)}],{expr.token.line})'
