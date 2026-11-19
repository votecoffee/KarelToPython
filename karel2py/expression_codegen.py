"""Type-check and lower expressions, references and call interfaces."""
from .compiler_language import (
    BUILTINS,
    BUILTIN_PROCEDURES,
    BUILTIN_SIGNATURES,
    CONFIG_TEXT_PROCEDURES,
    CONTROLLER_NAMES,
    CONVERSION_OUTPUT_TYPES,
    DATA_RECORD_TYPES,
    INTEGRAL_TYPES,
    MULTI_OUTPUT_PROCEDURES,
    NARROW_TYPES,
    POSITIONAL_VALUE_TYPES,
    PREDEFINED_CONSTANTS,
    PYTHONIC_CONSTRUCTORS,
    RECORD_TYPES,
    REGISTER_PROCEDURES,
    TIMER_FUNCTIONS,
    TIME_TEXT_PROCEDURES,
)
from .call_analysis import array_formal_forward_match, check_service_signature, routine_argument_conversion
from .control_flow import counter_text
from .operator_types import POSE_OPERANDS, binary_result, operand_type, unary_result
from . import extended as ex
from . import runtime as rt


class ExpressionLowering:
    """Lower expressions against the current checked program and emitter scope."""

    def file_prefix_spec(self,argument):
        if not self.is_array_prefix_value(argument):return None
        container=self.access_type(argument.args[0])
        return rt.array_prefix_type(container,len(argument.args)-1) if rt.file_storage_type(container) else None

    def file_prefix_reference_code(self,argument):
        base,container=self.expression(argument.args[0],raw=True)
        codes=[self.require_type(index,'INTEGER') for index in argument.args[1:]]
        return f'_rt.resource_array_prefix_reference({base},({", ".join(codes)},),{container!r},{argument.token.line})',container

    def file_prefix_argument(self,argument,routine,formal):
        code,container=self.file_prefix_reference_code(argument)
        selected=self.file_prefix_spec(argument);line=argument.token.line
        self.file_prefix_argument_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
            routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
            source_selector=counter_text(argument),source_type_spec=container,selected_type_spec=selected,
            supplied_subscripts=len(argument.args)-1,evaluated_once=True,original_cells=True))
        self.features.add('direct FILE prefix reference argument')
        return code,selected

    def argument_is_reference(self,argument,expected):
        if argument.kind not in ('name','field','index') or self.root_name(argument) in self.visible_constants():return False
        if self.is_array_prefix_value(argument):
            actual=self.file_prefix_spec(argument)
            if actual is None:return False
        else:actual=self.access_type(argument)
        guarded_array = self.mode == 'pythonic' and array_formal_forward_match(expected, actual)
        conversion = routine_argument_conversion(expected, actual, mode=self.mode, guarded_array=guarded_array)
        return conversion is None and not self.is_value_only_subfield(argument)

    def check_for_call(self, token, routine=None):
        if self.active_counters:
            if self.mode == 'strict' and not self.has_fresh_active_counters():
                self.error('E_FOR_COUNTER', 'Routine calls inside FOR require every active counter to be a fresh routine-local variable', token)
            if self.mode == 'pythonic' and routine is not None:
                locals_only = {t.value for t, _ in self.current_routine.declarations} if self.current_routine else set()
                conflict = (self.named_active_counters() - locals_only) & routine.global_writes
                if conflict:
                    self.error('E_FOR_COUNTER', 'Routine may write active global FOR counter(s): ' + ', '.join(sorted(conflict)), token)
                aggregate_roots={root for root in self.named_active_counters()-locals_only if self.types[root][0] not in INTEGRAL_TYPES}
                if aggregate_roots and routine.name in self.external_write_routines:
                    self.error('E_FOR_COUNTER','External routine effects cannot prove active aggregate counter roots unchanged',token)
            if self.has_fresh_active_counters(): self.features.add('routine call inside FOR with fresh local counters')
            if self.mode == 'pythonic': self.features.add('routine call inside FOR with checked counter effects')

    def geometry_operand(self,code,spec,token,operation):
        if self.mode=='pythonic' and spec==('VECTOR',) and operation in (':','INV','FRAME'):
            return f'_rt.vector_value({code},{token.line})'
        if self.mode=='pythonic' and spec[0]=='JOINTPOS':
            self.features.update(('extended services','joint geometry'))
            if self.current_routine: self.current_routine.may_services=True
            self.joint_geometry_uses.append(dict(operation=operation,body=self.current_routine.name if self.current_routine else self.program.name,
                line=token.line,column=token.column,source_type=spec,target_type=('XYZWPREXT',),evaluated_once=True,independent_value=True))
            return f'self._state.geometry_value({code},{spec!r},{token.line})'
        return f'_rt.frame_value({code}, {token.line}, expected={spec!r})'

    def reference(self, expr, *, config_read=False, allow_prefix=False, collection_prefix=False, collection_io=False):
        line = expr.token.line
        selection_root=expr
        while selection_root.kind in ('field','index','group'):selection_root=selection_root.args[0]
        if selection_root.kind=='system_selection':
            self.error('E_SYSTEM_SELECTION_REFERENCE','Active frame/tool numbers cannot supply writable references',expr.token)
        if self.is_system_pose_path(expr):
            self.error('E_SYSTEM_POSE_READ_ONLY','Robot system poses cannot supply writable references',expr.token)
        if expr.kind == 'using_ref': return expr.value[0],expr.value[1]
        if expr.kind == 'group': return self.reference(expr.args[0],config_read=config_read,allow_prefix=allow_prefix,collection_prefix=collection_prefix,collection_io=collection_io)
        if expr.kind == 'name':
            if self.is_predefined_file(expr):return f'self._state.predefined_file_reference({expr.value!r},{line})',('FILE',)
            return f'self._state.reference({expr.value!r}, {line})', self.symbol_type(expr)
        base, spec = self.expression(expr.args[0], raw=True)
        if expr.kind == 'field':
            member = self.member_type(spec, expr)
            helper='config_read_reference' if config_read else 'field_reference'
            return f'_rt.{helper}({base}, {expr.value!r}, {line})', member
        if spec[0]=='PATH':
            if len(expr.args)!=2: self.error('E_ARRAY_RANK','PATH requires one node index',expr.token)
            index=self.require_type(expr.args[1],'INTEGER')
            return f'_rt.index_reference({base},{index},{line})',rt.PathValue(spec).node_spec
        if spec[0]!='ARRAY' and not (self.mode=='pythonic' and spec[0]=='JOINTPOS'):self.error('E_TYPE','Indexing requires ARRAY or Pythonic JOINTPOS',expr.token)
        prefix=allow_prefix and self.mode=='pythonic' and rt.array_prefix_type(spec,len(expr.args)-1) is not None
        index, selected = self.index_code(expr, spec, allow_prefix=prefix, prefix_target=prefix, collection_prefix=collection_prefix)
        if prefix:
            helper='resource_array_prefix_reference' if collection_prefix and rt.collection_array_type(spec) else 'array_prefix_target'
            check=',check=self._state.tick' if collection_io and rt.collection_array_type(spec) else ''
            return f'_rt.{helper}({base},{index},{spec!r},{line}{check})',selected
        if self.mode=='pythonic' and rt.collection_array_node_type(spec,len(expr.args)-1) is not None:return f'_rt.collection_path_reference({base},{index},{spec!r},{line})',selected
        if self.mode=='pythonic' and rt.joint_axis_access(spec,len(expr.args)-1):return f'_rt.joint_index_reference({base},{index},{spec!r},{line})',selected
        return f'_rt.index_reference({base}, {index}, {line})', selected

    def path_conversion_value(self,expected,actual,value,token,operation,*,receiver=None):
        array=expected[0]=='ARRAY'
        layout=rt.path_array_conversion_layout(expected,actual) if array else ex.path_conversion_layout(expected,actual,model=True)
        if layout is None:self.error('E_TYPE','Logical collection values require compatible PATH layouts and matching shapes',token)
        if 'kinematic' in layout:
            self.features.add('extended services')
            if self.current_routine:self.current_routine.may_services=True
        self.features.add('source PATH schema conversion')
        self.path_schema_uses.append(dict(operation=operation,body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line,column=token.column,source_type_spec=actual,target_type_spec=expected,
            model_backed='kinematic' in layout,evaluated_once=True,independent_value=True))
        method='path_array_source_value' if array else 'path_source_value'
        receiver=repr(expected) if receiver is None else receiver
        return f'self._state.{method}({receiver},{value},{token.line},source_spec={actual!r})'

    def collection_assignment(self,target,expression,token):
        reference,expected=self.reference(target)
        value,actual=self.expression(expression)
        source=self.fresh();line=token.line
        if expected==actual:
            value=f'_rt.collection_source_value({actual!r},{value},{line},source_spec={actual!r})'
        else:value=self.path_conversion_value(expected,actual,value,token,'ASSIGNMENT')
        self.line(f'{source}={value}',token)
        self.line(f'_rt.collection_assign({reference},{source},{line})',token)
        self.features.add('logical scalar collection source copy')

    def collection_array_assignment(self,target,expression,token):
        reference,expected=self.reference(target,allow_prefix=True,collection_prefix=True)
        value,actual=self.expression(expression,allow_array_result=True)
        source=self.fresh();line=token.line
        if rt.collection_array_source_accepts(expected,actual):
            value=f'_rt.collection_array_source_value({actual!r},{value},{line},source_spec={actual!r})'
        elif (target.kind=='name' and self.current_routine is not None and None in rt.array_shape(expected)
              and any(name.value==target.value for name,_ in self.current_routine.parameters)):
            self.line(f'{source}={value}',token)
            value=self.path_conversion_value(expected,actual,source,token,'ASSIGNMENT',receiver=f'({reference}).spec')
        else:value=self.path_conversion_value(expected,actual,value,token,'ASSIGNMENT')
        self.line(f'{source}={value}',token)
        self.line(f'_rt.collection_array_assign({reference},{source},{line})',token)
        self.features.add('logical collection ARRAY source copy')

    def prefix_assignment(self,target,expression,token):
        reference,expected=self.reference(target,allow_prefix=True)
        value,actual=self.expression(expression,allow_array_result=True)
        context=rt.kinematic_array_kind(expected,actual) or rt.kinematic_record_kind(expected,actual)
        if (actual[0]!='ARRAY' or not (self.compatible(expected,actual) or rt.array_schema_compatible(expected,actual)
                or rt.numeric_array_kind(expected,actual) or rt.positional_array_kind(expected,actual)
                or context or rt.record_schema_kind(expected,actual))):
            self.error('E_TYPE',f'Cannot assign {actual} to ARRAY prefix {expected}',token)
        source=self.fresh();captured=self.fresh();line=token.line
        self.line(f'{source} = _rt.assignment_value({value},{line})',token)
        self.line(f'{captured} = {reference}',token)
        schema=f',source_spec={actual!r}' if rt.record_schema_kind(expected,actual) or rt.kinematic_record_kind(expected,actual) else ''
        self.line(f'{captured}.set(self._state.array_assignment_value({source},{captured}.spec,{line}{schema}),{line})',token)
        if context:
            self.features.add('extended services')
            if self.current_routine:self.current_routine.may_services=True
        self.features.add('statement ARRAY prefix assignment')

    def is_array_prefix_value(self,expr):
        if self.mode!='pythonic' or expr.kind!='index':return False
        base=expr.args[0]
        if base.kind=='name' and base.value in ex.PORT_TYPES and base.value not in self.types:return False
        return rt.array_prefix_type(self.access_type(base),len(expr.args)-1) is not None

    def index_code(self, expr, spec, *, allow_prefix=False, prefix_target=False, collection_prefix=False):
        indexes = expr.args[1:]
        if self.mode!='pythonic' and expr.args[0].kind == 'index':
            self.error('E_ARRAY_RANK', 'Chained ARRAY indexes need grammar validation; use comma-separated subscripts', expr.token)
        axis=self.mode=='pythonic' and rt.joint_axis_access(spec,len(indexes))
        prefix=rt.array_prefix_type(spec,len(indexes)) if allow_prefix and self.mode=='pythonic' else None
        if prefix is not None and not (rt.aggregate_write_type(prefix) or collection_prefix and rt.collection_array_type(prefix)):
            self.error('E_ARRAY_RANK','ARRAY prefix values require resource-free data',expr.token)
        path_node=rt.collection_array_node_type(spec,len(indexes)) if self.mode=='pythonic' else None
        try: selected = ('REAL',) if axis else path_node if path_node is not None else prefix if prefix is not None else rt.indexed_type(spec, len(indexes))
        except rt.KarelRuntimeError as exc: self.error('E_ARRAY_RANK', str(exc), expr.token)
        if self.mode == 'strict' and len(indexes) > 1 and any(self.has_routine_call(index) for index in indexes):
            self.error('E_EVALUATION_ORDER', 'Multiple ARRAY subscripts containing routine calls need evaluation-order validation', expr.token)
        codes = [self.require_type(index, 'INTEGER') for index in indexes]
        if axis:
            self.features.add('checked joint axis access')
            self.joint_axis_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                line=expr.token.line,column=expr.token.column,source_type_spec=spec,joint_type_spec=rt.array_leaf_spec(spec),
                selected_type_spec=('REAL',),subscript_count=len(indexes),evaluated_once=True,declared_schema_checked=True))
        if len(indexes) > 1: self.features.add('multidimensional ARRAY indexing')
        if prefix is not None:
            self.features.add('captured ARRAY prefix targets' if prefix_target else 'independent ARRAY prefix values')
            row=dict(body=self.current_routine.name if self.current_routine else self.program.name,
                line=expr.token.line,column=expr.token.column,source_type_spec=spec,selected_type_spec=selected,
                supplied_subscripts=len(indexes),evaluated_once=True,independent_value=not prefix_target)
            uses=self.array_prefix_target_uses if prefix_target else self.array_prefix_uses
            if row not in uses:uses.append(row)
        elif selected[0] == 'ARRAY':
            self.features.add('named subarray reference')
            self.subarray_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                           line=expr.token.line, column=expr.token.column, supplied_subscripts=len(indexes),
                                           logical_rank=len(rt.array_dimensions(spec)), selected_type=rt.array_identity(selected)))
        code = codes[0] if len(indexes) == 1 else '(' + ', '.join(codes) + ')'
        return code, selected

    def config_word_conversion(self,target,source,value,token,operation):
        self.features.add('portable CONFIG word conversion')
        self.config_word_uses.append(dict(operation=operation,body=self.current_routine.name if self.current_routine else self.program.name,
            line=token.line,column=token.column,source_type_spec=source,target_type_spec=target,
            conversion_kind=rt.config_word_kind(target,source),evaluated_once=True,independent_value=True))
        return f'_rt.config_word_value({target!r},{value},{token.line})'

    def expression(self, expr, raw=False, *, allow_array_result=False, collection_io=False):
        if expr.kind=='system_selection':
            group=self.require_type(expr.args[0],'INTEGER')
            self.system_selection_uses.append(dict(operation='READ_'+expr.value,body=self.current_routine.name if self.current_routine else self.program.name,
                line=expr.token.line,column=expr.token.column,evaluated_once=True,private_value=True,result_type='INTEGER'))
            self.features.update(('robot frame/tool selection','extended services'))
            return f'self._state.system_selection({expr.value!r},_rt.integer({group},{expr.args[0].token.line}),{expr.token.line})',('INTEGER',)
        pose=expr if expr.kind=='system_pose' else self.system_axis_root(expr)
        if pose is not None:
            axis=None if pose is expr else expr.value
            result_type='POSITION' if axis is None else 'REAL'
            codes=[self.require_type(argument,'INTEGER') for argument in pose.args]
            codes=[f'_rt.integer({code},{argument.token.line})' for code,argument in zip(codes,pose.args)]
            row=dict(operation=pose.value,body=self.current_routine.name if self.current_routine else self.program.name,
                line=expr.token.line,column=expr.token.column,evaluated_once=True,independent_value=True,result_type=result_type)
            if axis is not None:row['path']=(axis,)
            if row not in self.system_pose_uses:self.system_pose_uses.append(row)
            self.features.update(('robot system pose value','extended services'))
            number=codes[1] if len(codes)>1 else 'None'
            selector='' if axis is None else f',axis={axis!r}'
            return f'self._state.system_pose({pose.value!r},{codes[0]},{number},{expr.token.line}{selector})',(result_type,)
        if expr.kind=='motion_event':
            return f'self._state.execution.require("motion",{expr.token.line}).condition(self._state,{expr.value},{expr.token.line})',('BOOLEAN',)
        if expr.kind=='captured': return expr.value
        if expr.kind=='using_ref':
            code=f'{expr.value[0]}.raw()'
            return (code if raw else f'_rt.require({code},{expr.token.line})'),expr.value[1]
        if expr.kind=='event':
            number=self.require_type(expr.args[0],'INTEGER'); key=(expr.token.line,expr.token.column)
            return f'_rt.event_condition(self._state,{number},{key!r},{expr.token.line})',('BOOLEAN',)
        if expr.kind=='semaphore':
            number=self.require_type(expr.args[0],'INTEGER'); self.features.add('SEMAPHORE condition')
            return f'(self._state.execution.require("semaphores",{expr.token.line}).value({number},{expr.token.line})>0)',('BOOLEAN',)
        if expr.kind=='error_condition':
            number=self.require_type(expr.args[0],'INTEGER') if expr.args else 'None'
            self.features.add('ERROR condition')
            return f'_rt.error_condition(self._state,{number},{(expr.token.line,expr.token.column)!r},{expr.token.line})',('BOOLEAN',)
        if expr.kind=='edge':
            value=self.require_type(expr.args[0],'BOOLEAN'); key=(expr.token.line,expr.token.column)
            return f'_rt.edge_condition(self._state,{key!r},{value},{expr.value!r},{expr.token.line})',('BOOLEAN',)
        if expr.kind=='task_event':
            if expr.value=='PAUSE': return 'self._state._pause_requested',('BOOLEAN',)
            if expr.value=='ABORT': return 'self._state._abort_requested',('BOOLEAN',)
            return f'_rt.lifecycle_condition(self._state,{expr.value!r},{(expr.token.line,expr.token.column)!r})',('BOOLEAN',)
        line = expr.token.line
        if expr.kind == 'group':
            return self.expression(expr.args[0], raw=raw, collection_io=collection_io)
        if expr.kind == 'real_literal':
            try: rt.real_literal(expr.value, line)
            except rt.KarelRuntimeError as exc: self.error('E_REAL_LITERAL', str(exc), expr.token)
            self.features.add('REAL literal' if self.mode == 'pythonic' else 'exact REAL literal')
            return f'_rt.real_literal({expr.value!r}, {line})', ('REAL',)
        if expr.kind == 'predefined':
            value = PREDEFINED_CONSTANTS[expr.value]
            if type(value) is bool: return repr(value), ('BOOLEAN',)
            if type(value) is str: return repr(value), ('STRING',len(value))
            return f'_rt.integer({value}, {line})', ('INTEGER',)
        if expr.kind == 'literal':
            spec = ('BOOLEAN',) if type(expr.value) is bool else ('INTEGER',) if type(expr.value) is int else ('STRING', len(expr.value))
            code = repr(expr.value)
            # Integer checks happen at every numeric literal except -2**31 handled below.
            if spec[0] == 'INTEGER':
                if not -2147483648 <= expr.value <= 2147483647:
                    self.error('E_LITERAL', 'INTEGER literal outside signed 32-bit range', expr.token)
                code = f'_rt.integer({code}, {line})'
            return code, spec
        if expr.kind == 'name':
            if self.is_predefined_file(expr):
                self.features.add('explicit predefined FILE binding')
                return f'self._state.predefined_file({expr.value!r},{line})',('FILE',)
            spec = self.symbol_type(expr)
            if self.current_routine and expr.value in self.current_routine.local_constants:
                # Immutable scalar values are emitted directly. They never become
                # writable State cells or leak into a caller/callee frame.
                return repr(self.current_routine.local_constants[expr.value]), spec
            method = 'raw' if raw else 'get'
            args = repr(expr.value) if raw else f'{expr.value!r}, {line}'
            return f'self._state.{method}({args})', spec
        if expr.kind == 'index':
            if self.mode=='pythonic' and expr.args[0].kind=='name' and expr.args[0].value in ex.PORT_TYPES and expr.args[0].value not in self.types:
                if len(expr.args)!=2: self.error('E_ARGUMENTS','Ports require one index',expr.token)
                index=self.require_type(expr.args[1],'INTEGER'); kind=expr.args[0].value
                self.features.add('ports'); return f'self._state.port_read({kind!r},{index},{line})',(ex.PORT_TYPES[kind],)
            base, spec = self.expression(expr.args[0], raw=True)
            if spec[0]=='PATH':
                if len(expr.args)!=2: self.error('E_ARRAY_RANK','PATH requires one node index',expr.token)
                index=self.require_type(expr.args[1],'INTEGER')
                return f'{base}.node({index},{line})',rt.PathValue(spec).node_spec
            if spec[0]!='ARRAY' and not (self.mode=='pythonic' and spec[0]=='JOINTPOS'):self.error('E_TYPE','Indexing requires ARRAY or Pythonic JOINTPOS',expr.token)
            index, selected = self.index_code(expr, spec, allow_prefix=True,collection_prefix=self.mode=='pythonic' and rt.collection_array_type(spec))
            if self.mode=='pythonic' and rt.collection_array_node_type(spec,len(expr.args)-1) is not None:
                reference=f'_rt.collection_path_reference({base},{index},{spec!r},{line})'
                return reference+'.raw()' if raw else f'_rt.require({reference}.raw(),{line})',selected
            if self.mode=='pythonic' and rt.array_prefix_type(spec,len(expr.args)-1) is not None:
                if collection_io and rt.collection_array_type(spec):
                    return f'_rt.resource_array_prefix_reference({base},{index},{spec!r},{line},check=self._state.tick).raw()',selected
                helper='collection_array_prefix_value' if rt.collection_array_type(spec) else 'array_prefix_value'
                return f'_rt.{helper}({base},{index},{spec!r},{line})',selected
            if self.mode=='pythonic' and rt.joint_axis_access(spec,len(expr.args)-1):
                code=f'_rt.joint_index_reference({base},{index},{spec!r},{line}).raw()'
                return code if raw else f'_rt.real({code},{line})',selected
            method = 'raw_index' if raw else 'load_index'
            return f'_rt.{method}({base}, {index}, {line})', selected
        if expr.kind == 'field':
            base, spec = self.expression(expr.args[0], raw=True)
            member = self.member_type(spec, expr)
            method = 'raw_field' if raw else 'load_field'
            return f'_rt.{method}({base}, {expr.value!r}, {line})', member
        if expr.kind == 'unary':
            # The source manual requires the named predefined minimum.
            if self.is_minimum_literal(expr):
                self.error('E_MININT_LITERAL', 'The manual requires MININT instead of the INTEGER literal -2147483648', expr.token)
            value, spec = self.expression(expr.args[0])
            result_type = unary_result(expr.value, spec, mode=self.mode)
            if result_type is None: self.error('E_TYPE', 'Invalid unary operand type', expr.token)
            self.features.add('unary ' + expr.value)
            return f'_rt.unary({expr.value!r}, {value}, {line})', result_type
        if expr.kind == 'binary':
            if self.mode == 'strict' and self.has_external_effect_call(expr):
                self.error('E_EVALUATION_ORDER', 'Function calls that may write globals/reference parameters, delay, request output or abort are blocked inside operator expressions', expr.token)
            left, lt = self.expression(expr.args[0])
            right, right_type = self.expression(expr.args[1])
            lt, right_type = operand_type(lt), operand_type(right_type)
            op = expr.value
            if op == ':':
                relative_kinds = (*POSE_OPERANDS, 'VECTOR')
                result_type = None
                if self.mode == 'pythonic' and lt[0] in relative_kinds and right_type[0] in relative_kinds:
                    result_type = self.relative_result_type([lt, right_type], expr.token)
            else:
                result_type = binary_result(op, lt, right_type, mode=self.mode)
            if (op in ('AND', 'OR') and self.mode == 'strict' and lt[0] == 'BOOLEAN'
                    and right_type[0] != 'VECTOR' and any(self.has_routine_call(x) for x in expr.args)):
                self.error('E_EVALUATION_ORDER', 'Boolean expressions containing routine calls are not implemented', expr.token)
            if result_type is None: self.error('E_TYPE', f'Unsupported {lt[0]} {op} {right_type[0]}', expr.token)
            if op == '>=<':
                self.position_comparison_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                          line=line, column=expr.token.column, operand_types=[lt[0],right_type[0]],
                                                          result_type='BOOLEAN', evaluated_once=True, operands_copied=True))
            elif op == ':':
                self.frame_operation_uses.append(dict(operation=':', body=self.current_routine.name if self.current_routine else self.program.name,
                                                      line=line, column=expr.token.column, operand_types=[lt[0],right_type[0]],
                                                      result_type=result_type[0], evaluated_once=True, operands_copied=True))
            elif 'VECTOR' in (lt[0], right_type[0]):
                self.features.add('VECTOR operator ' + op)
            self.features.add('operator ' + op)
            if self.mode == 'pythonic':
                if lt[0] == 'BOOLEAN' and op in ('AND', 'OR'):
                    self.short_circuit_expressions.add(id(expr))
                    return f'(_rt.boolean({left}, {line}) {op.lower()} _rt.boolean({right}, {line}))', result_type
                # Capture mutable values before a later operand can change them.
                if lt == ('VECTOR',): left = f'_rt.vector_value({left}, {line})'
                if right_type == ('VECTOR',): right = f'_rt.vector_value({right}, {line})'
                if op in (':','>=<'):
                    if lt!=('VECTOR',):left = self.geometry_operand(left,lt,expr.args[0].token,op)
                    if right_type!=('VECTOR',):right = self.geometry_operand(right,right_type,expr.args[1].token,op)
                if op == '>=<':
                    return f'_rt.positions_close({left}, {right}, self._state.pose_tolerance, {line}, external_tolerance=self._state.external_tolerance)', result_type
            return f'_rt.binary({op!r}, {left}, {right}, {line})', result_type
        if expr.kind == 'call':
            if self.mode=='pythonic' and expr.value in ex.FUNCTIONS and expr.value not in self.routines:
                return self.service_call(expr),ex.FUNCTIONS[expr.value][1]
            if self.mode=='pythonic' and expr.value in ex.PROCEDURES and expr.value not in self.routines:
                self.error('E_PROCEDURE_RESULT','Service procedures have no expression result',expr.token)
            if self.active_counters and expr.value in self.routines:
                self.check_for_call(expr.token, self.routines[expr.value])
            if self.mode == 'pythonic' and expr.value in TIMER_FUNCTIONS and expr.value not in self.routines:
                return self.microsecond_timer(expr), ('INTEGER',)
            if (expr.value in BUILTIN_PROCEDURES or expr.value in MULTI_OUTPUT_PROCEDURES
                    or self.mode == 'pythonic' and expr.value in CONFIG_TEXT_PROCEDURES | TIME_TEXT_PROCEDURES | REGISTER_PROCEDURES and expr.value not in self.routines):
                self.error('E_PROCEDURE_RESULT', 'Conversion procedures have an output argument, not an expression result', expr.token)
            if expr.value in BUILTINS or (self.mode == 'pythonic' and expr.value in PYTHONIC_CONSTRUCTORS and expr.value not in self.routines):
                return self.builtin_call(expr)
            if expr.value not in self.routines:
                code = 'E_CONTROLLER' if expr.value in CONTROLLER_NAMES else 'E_CALL'
                self.error(code, f'Unknown or unsupported call {expr.value}', expr.token)
            routine = self.routines[expr.value]
            if not routine.return_type: self.error('E_TYPE', 'Procedure cannot be used as an expression', expr.token)
            if self.mode == 'strict' and routine.return_type[0] == 'ARRAY' and not allow_array_result:
                self.error('E_ARRAY_RESULT_CONTEXT', 'An ARRAY-valued function call is supported only as the complete value of a direct assignment', expr.token)
            if routine.return_type[0] == 'ARRAY':
                self.array_function_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                     routine=expr.value, line=line, column=expr.token.column,
                                                     result_spec=routine.return_type, evaluated_once=True, independent_copy=True))
            self.features.add('routine function call')
            return self.routine_call(expr), routine.return_type
        self.error('E_INTERNAL', 'Unexpected expression node', expr.token)

    def builtin_call(self, expr):
        if expr.value in PYTHONIC_CONSTRUCTORS and self.mode == 'strict':
            self.error('E_CALL', f'{expr.value} construction is outside the preserved conservative subset', expr.token)
        if expr.value == 'UNINIT':
            if len(expr.args) != 1:
                self.error('E_ARGUMENTS', 'UNINIT requires exactly one argument', expr.token)
            argument = expr.args[0]
            grouped=argument.kind=='group'
            if self.mode=='pythonic':
                while argument.kind=='group': argument=argument.args[0]
            if argument.kind not in ('name', 'index', 'field'):
                self.error('E_ARGUMENTS', 'UNINIT requires variable, field or array-element storage', expr.token)
            code, spec = self.expression(argument, raw=True)
            if spec[0] == 'BYTE':
                self.error('E_BYTE_UNINIT', 'BYTE initialization queries are not implemented; the manual specifies no uninitialized checking for BYTE', argument.token)
            supported=('INTEGER','SHORT','BOOLEAN','REAL','STRING','JOINTPOS')+((*DATA_RECORD_TYPES,'FILE','QUEUE_TYPE') if self.mode=='pythonic' else ())
            if spec[0] not in supported:
                self.error('E_TYPE', 'Invalid UNINIT argument type', expr.token)
            if self.root_name(argument) in self.visible_constants():
                self.error('E_ARGUMENTS', 'UNINIT requires a variable, not a constant', expr.token)
            codes, result_type = [code], ('BOOLEAN',)
            self.initialization_query_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                line=expr.token.line,column=expr.token.column,operand_type=spec,storage_kind=argument.kind,grouped=grouped,evaluated_once=True))
        elif expr.value == 'ABS':
            if len(expr.args) != 1: self.error('E_ARGUMENTS', 'ABS requires exactly one argument', expr.token)
            code, result_type = self.expression(expr.args[0])
            if result_type[0] in NARROW_TYPES: result_type = ('INTEGER',)
            if result_type[0] not in ('INTEGER', 'REAL'):
                self.error('E_TYPE', 'ABS requires INTEGER or REAL', expr.token)
            codes = [code]
        elif expr.value == 'ARRAY_LEN':
            has_dimension=self.mode=='pythonic' and len(expr.args)==2
            if len(expr.args)!=1 and not has_dimension:
                message='ARRAY_LEN requires an ARRAY and optional dimension' if self.mode=='pythonic' else 'ARRAY_LEN requires exactly one argument'
                self.error('E_ARGUMENTS',message,expr.token)
            array=expr.args[0]
            while array.kind=='group':
                array=array.args[0]
            spec=self.file_prefix_spec(array)
            if spec is None:
                code,spec=self.expression(expr.args[0])
            else:
                reference,_=self.file_prefix_reference_code(array)
                code=reference+'.raw()'
            if spec[0] != 'ARRAY': self.error('E_TYPE', 'ARRAY_LEN requires ARRAY', expr.token)
            if self.mode == 'strict' and len(rt.array_dimensions(spec)) != 1:
                self.error('E_ARRAY_LEN', 'ARRAY_LEN on multidimensional arrays needs dimension-count semantics; use explicit dimensions', expr.token)
            result_type, codes = ('INTEGER',), [code]
            if has_dimension:
                codes.append(self.require_type(expr.args[1],'INTEGER'))
        elif expr.value=='POS':
            result_type=self.pos_call_result_type(expr)
            signature=BUILTIN_SIGNATURES['POS'][0]
            if result_type==('XYZWPREXT',):
                signature+=('REAL',)*3
            codes=[self.require_type(argument,expected) for argument,expected in zip(expr.args,signature)]
            if result_type==('XYZWPREXT',):
                codes[6]=f"_rt.positional_value(('CONFIG',),{codes[6]},{expr.args[6].token.line})"
        elif expr.value in rt.POSITION_AXIS_FUNCTIONS:
            if len(expr.args) != 1: self.error('E_ARGUMENTS', f'{expr.value} requires one pose', expr.token)
            code, axis_spec = self.expression(expr.args[0])
            self.frame_result_type([axis_spec], expr.args[0].token)
            codes = [self.geometry_operand(code,axis_spec,expr.args[0].token,expr.value)]
            result_type = ('VECTOR',)
        elif expr.value in ('INV','FRAME'):
            if (expr.value == 'INV' and len(expr.args) != 1 or expr.value == 'FRAME' and len(expr.args) not in (3,4,5)):
                self.error('E_ARGUMENTS', 'INV requires one operand; FRAME requires three points and optional origin and CONFIG', expr.token)
            codes, frame_specs = [], []
            for index,argument in enumerate(expr.args):
                code,spec=self.expression(argument)
                if index==4 and spec!=('CONFIG',):
                    self.error('E_ARGUMENTS','Five-argument FRAME requires CONFIG as the fifth argument',expr.token)
                if expr.value=='FRAME' and index>=3 and spec==('CONFIG',):
                    code=f'_rt.positional_value({spec!r},{code},{argument.token.line})'
                else:
                    if spec!=('VECTOR',):self.frame_result_type([spec],argument.token)
                    code=self.geometry_operand(code,spec,argument.token,expr.value)
                codes.append(code)
                frame_specs.append(spec)
            result_type=self.frame_call_result_type(expr.value,frame_specs,expr.token)
        else:
            signature, result_type = BUILTIN_SIGNATURES[expr.value]
            if len(expr.args) != len(signature):
                self.error('E_ARGUMENTS', f'{expr.value} requires {len(signature)} arguments', expr.token)
            if self.mode == 'strict' and len(expr.args) > 1 and any(self.has_routine_call(arg) for arg in expr.args):
                self.error('E_EVALUATION_ORDER', 'Multiple built-in arguments containing routine calls need evaluation-order validation', expr.token)
            codes = [self.require_type(argument, expected)
                     for argument, expected in zip(expr.args, signature)]
        self.features.add(expr.value)
        if expr.value in rt.POSITION_AXIS_FUNCTIONS:
            self.position_axis_uses.append(dict(function=expr.value, body=self.current_routine.name if self.current_routine else self.program.name,
                                               line=expr.token.line, column=expr.token.column, operand_type=axis_spec[0],
                                               result_type='VECTOR', axis=expr.value, evaluated_once=True, independent_value=True))
        if expr.value == 'VEC':
            self.vector_constructor_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                    line=expr.token.line, column=expr.token.column,
                                                    arguments_evaluated_once=True, argument_order=['x','y','z'],
                                                    independent_value=True))
        if expr.value == 'POS':
            argument_order=['x','y','z','w','p','r','c']
            if result_type==('XYZWPREXT',):
                argument_order.extend(['ext1','ext2','ext3'])
            self.pos_constructor_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                 line=expr.token.line, column=expr.token.column,
                                                 arguments_evaluated_once=True, argument_order=argument_order,
                                                 result_type=result_type[0], independent_value=True, configuration_copied=True))
        if expr.value == 'INV':
            self.frame_operation_uses.append(dict(operation='INV', body=self.current_routine.name if self.current_routine else self.program.name,
                                                  line=expr.token.line, column=expr.token.column, operand_types=[spec[0] for spec in frame_specs],
                                                  result_type=result_type[0], evaluated_once=True, operands_copied=True))
        if expr.value == 'FRAME':
            explicit_config=frame_specs[-1]==('CONFIG',)
            point_count=len(frame_specs)-int(explicit_config)
            origin=4 if point_count==4 else 1
            self.frame_operation_uses.append(dict(operation='FRAME', body=self.current_routine.name if self.current_routine else self.program.name,
                                                  line=expr.token.line, column=expr.token.column, operand_types=[spec[0] for spec in frame_specs],
                                                  result_type=result_type[0], evaluated_once=True, operands_copied=True,
                                                  origin_argument=origin,
                                                  configuration_argument=len(frame_specs) if explicit_config else origin))
        if expr.value in rt.UNARY_TRIG_FUNCTIONS:
            self.trig_uses.append(dict(function=expr.value, body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=expr.token.line, column=expr.token.column, evaluated_once=True,
                                       runtime_exact_subset_guard=self.mode == 'strict', result_type='REAL'))
        if expr.value == 'ATAN2':
            self.atan2_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=expr.token.line, column=expr.token.column, argument_order=['x','y'],
                                       arguments_evaluated_once=True, runtime_exact_subset_guard=self.mode == 'strict', result_type='REAL'))
        if expr.value=='UNINIT' and spec==('FILE',):
            return f'_rt.file_uninit({codes[0]},{expr.token.line})',result_type
        if expr.value=='UNINIT' and spec==('QUEUE_TYPE',):
            return f'_rt.queue_uninit({codes[0]},{expr.token.line})',result_type
        return f'_rt.builtin({expr.value!r}, [{", ".join(codes)}], {expr.token.line})', result_type

    def conversion_procedure(self, expr):
        inputs = BUILTIN_PROCEDURES[expr.value]
        if len(expr.args) != len(inputs) + 1:
            self.error('E_ARGUMENTS', f'{expr.value} requires {len(inputs) + 1} arguments', expr.token)
        if self.mode == 'strict' and any(self.has_routine_call(argument) for argument in expr.args):
            self.error('E_EVALUATION_ORDER', 'Conversion arguments containing user routine calls need evaluation-order validation', expr.token)
        self.check_for_call(expr.token)
        destination = expr.args[-1]
        if destination.kind not in ('name', 'index', 'field') or self.root_name(destination) in self.visible_constants():
            self.error('E_OUTPUT_ARGUMENT', 'Conversion output requires a writable variable, field or array element', destination.token)
        if self.protection_root(destination) in self.active_counters:
            self.error('E_FOR_COUNTER', 'Conversion cannot write an active FOR counter', destination.token)
        if self.is_position_read_only_access(destination):
            self.error('E_POSITION_READ_ONLY', 'POSITION orientation fields cannot be conversion outputs', destination.token)
        reference, actual = self.reference(destination)
        if self.is_value_only_subfield(destination):
            self.error('E_CONFIG_OUTPUT', 'CONFIG/association subfields have value-only routine passing; conversion output aliases remain blocked', destination.token)
        required = CONVERSION_OUTPUT_TYPES[expr.value]
        if actual[0] != required:
            self.error('E_TYPE', f'{expr.value} output requires {required} storage; narrow numeric outputs are not promoted', destination.token)
        codes = [self.require_type(argument, expected) for argument, expected in zip(expr.args[:-1], inputs)]
        self.features.add(expr.value)
        self.features.add('conversion output by reference')
        return f'_rt.conversion_procedure({expr.value!r}, {", ".join(codes)}, {reference}, line={expr.token.line})'

    def config_text_conversion(self, expr):
        parsing = expr.value == 'CNV_STR_CONF'
        count = 3 if parsing else 2
        grouped=parsing and len(expr.args)==4
        if len(expr.args)!=count and not grouped:
            message='CNV_STR_CONF requires three arguments and an optional group' if parsing else f'{expr.value} requires {count} arguments'
            self.error('E_ARGUMENTS',message,expr.token)
        self.check_for_call(expr.token)
        source = self.require_type(expr.args[0], 'STRING' if parsing else 'CONFIG')
        if not parsing: source = f'_rt.positional_value(("CONFIG",), {source}, {expr.args[0].token.line})'
        outputs = []
        for argument, expected in zip(expr.args[1:], ('CONFIG','INTEGER') if parsing else ('STRING',)):
            base = argument
            while base.kind in ('field', 'index'): base = base.args[0]
            if argument.kind not in ('name', 'field', 'index') or base.kind not in ('name','using_ref') or base.value in self.visible_constants():
                self.error('E_OUTPUT_ARGUMENT', 'CONFIG conversion outputs require storage rooted in a variable', argument.token)
            if self.protection_root(base) in self.active_counters: self.error('E_FOR_COUNTER', 'CONFIG conversion cannot write an active FOR counter', argument.token)
            if self.is_position_read_only_access(argument): self.error('E_POSITION_READ_ONLY', 'CONFIG conversion output is read-only', argument.token)
            if self.is_value_only_subfield(argument): self.error('E_CONFIG_OUTPUT', 'CONFIG/association subfields cannot be conversion output aliases', argument.token)
            code, spec = self.reference(argument)
            if spec[0] != expected: self.error('E_TYPE', f'{expr.value} output requires {expected}', argument.token)
            outputs.append(code)
        self.features.add(expr.value)
        order=['source','target','status'] if parsing else ['source','target']
        options=''
        if grouped:
            group=self.require_type(expr.args[3],'INTEGER')
            options=f", group={group}, formats=self._state.execution.require('config_text',{expr.token.line})"
            order.append('group')
        self.config_text_uses.append(dict(name=expr.value, body=self.current_routine.name if self.current_routine else self.program.name,
                                         line=expr.token.line, column=expr.token.column, arguments_evaluated_once=True,
                                         argument_order=order,
                                         outputs=2 if parsing else 1, source_copied=not parsing))
        return f'_rt.config_text_conversion({expr.value!r}, {source}, {", ".join(outputs)}, line={expr.token.line}{options})'

    def bounded_service_argument(self, expr, limit, *, nullable):
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

    def service_call(self,expr):
        checked = check_service_signature(expr.value, len(expr.args), expr.token, mode=self.mode, error=self.error)
        self.check_for_call(expr.token)
        if ex.variable_write_call(expr.value,expr.args) and self.named_active_counters(): self.error('E_FOR_COUNTER',expr.value+' cannot indirectly write an active FOR counter',expr.token)
        codes=[]
        path_node_spec=None
        for index,(value,(mode,kind)) in enumerate(zip(expr.args,checked.parameters)):
            discarded=value
            while discarded.kind=='group': discarded=discarded.args[0]
            if kind=='TABLE_ACTION' and (discarded.kind not in ('name','field','index') or self.root_name(discarded) in self.visible_constants()):
                code,spec=self.expression(value)
                if spec!=('INTEGER',):self.error('E_TYPE','ACT_TBL action requires INTEGER',value.token)
                codes.append(code);continue
            if kind=='ERROR_CURSOR':
                sentinel=None
                if discarded.kind=='literal': sentinel=discarded.value
                elif discarded.kind=='predefined': sentinel=PREDEFINED_CONSTANTS.get(discarded.value)
                elif discarded.kind=='name': sentinel=self.visible_constants().get(discarded.value)
                if type(sentinel) is int and sentinel==2147483647:
                    codes.append('2147483647'); continue
            if mode=='m' and discarded.kind=='literal' and type(discarded.value) is int and discarded.value==0:
                codes.append('0'); continue
            if mode=='s':
                root=self.root_name(discarded)
                if discarded.kind not in ('name','field','index','using_ref') or root not in self.types or root in self.visible_constants() or self.current_routine and root in self.current_routine.local_types:
                    self.error('E_STATIC_ARGUMENT','Dynamic display requires static global storage',value.token)
                prefix=self.mode=='pythonic' and kind in ex.ARRAY_REFERENCE_KINDS and self.is_array_prefix_value(discarded)
                code,spec=self.reference(discarded,allow_prefix=prefix)
                if prefix:code=f'_rt.array_prefix_reference({code},{value.token.line})'
            elif mode in ('o','r','m'):
                if value.kind not in ('name','field','index') or self.root_name(value) in self.visible_constants(): self.error('E_OUTPUT_ARGUMENT','Service output requires writable storage',value.token)
                if self.protection_root(value) in self.active_counters: self.error('E_FOR_COUNTER','Service output cannot write an active FOR counter',value.token)
                if self.is_position_read_only_access(value): self.error('E_POSITION_READ_ONLY','Service output is protected POSITION storage',value.token)
                if self.is_value_only_subfield(value): self.error('E_CONFIG_OUTPUT','CONFIG/association fields cannot be output aliases',value.token)
                prefix=self.mode=='pythonic' and kind in ex.ARRAY_REFERENCE_KINDS and self.is_array_prefix_value(value)
                code,spec=self.reference(value,allow_prefix=prefix or self.mode=='pythonic' and expr.value=='GET_VAR' and index==3,collection_prefix=expr.value=='GET_VAR' and index==3)
                if prefix:code=f'_rt.array_prefix_reference({code},{value.token.line})'
            elif self.mode=='pythonic' and index==1 and expr.value in ('SEND_DATAPC','QUEUE_ATTACH','RMCN_SEND'):
                packet = expr.value == 'SEND_DATAPC'
                code,spec = self.bounded_service_argument(discarded, 244 if packet else 32, nullable=packet)
            else:
                variable_input=mode=='v' or (expr.value=='SET_VAR' and index==3)
                reference_input=(variable_input and discarded.kind in ('name','field','index') and self.root_name(discarded) not in self.visible_constants()
                                 and not self.is_system_pose_path(discarded)
                                 and (not self.is_array_prefix_value(discarded) or expr.value=='SET_VAR' and index==3 and rt.collection_array_type(self.access_type(discarded.args[0]))))
                if reference_input: code,spec=self.reference(discarded,allow_prefix=expr.value=='SET_VAR' and index==3,collection_prefix=expr.value=='SET_VAR' and index==3)
                else: code,spec=self.expression(value)
                if kind=='GEOMETRY_POSE' and spec[0]=='JOINTPOS': code=self.geometry_operand(code,spec,value.token,expr.value)
                if kind=='REAL' and spec[0] in INTEGRAL_TYPES: code=f'_rt.real({code},{value.token.line})'; spec=('REAL',)
                if mode!='v' and kind=='INTEGER' and spec[0] in NARROW_TYPES: code=f'_rt.integer({code},{value.token.line})'; spec=('INTEGER',)
                check=''
                if (self.mode=='pythonic' and expr.value=='SET_VAR' and index==3
                        and spec[0] in ('PATH','QUEUE_TYPE','ARRAY','JOINTPOS',*RECORD_TYPES)):
                    check=f',check=lambda:self._state.tick({value.token.line})'
                if reference_input: code=f'_rt.variable_reference({code},{value.token.line}{check})'
                elif variable_input: code=f'_rt.variable_value({spec!r},{code},{value.token.line}{check})'
                elif self.mode=='pythonic' and kind=='PATH_NODE' and spec[0]=='STRUCTURE':
                    code=f'_rt.path_node_seed(self._state,{spec!r},{code},{value.token.line})'
                elif kind=='ANY' or spec[0] in (*RECORD_TYPES,'JOINTPOS','ARRAY'): code=f'_rt.service_value({code},{value.token.line})'
            if not ex.matches(spec,kind): self.error('E_TYPE',f'{expr.value} expects {kind}, found {spec[0]}',value.token)
            if index==0 and expr.value in ex.OPTIONAL_PATH_NODE:
                path_node_spec=spec[1] or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']
            if kind=='PATH_NODE' and spec!=path_node_spec and not checked.explicit_node_flag:
                self.error('E_TYPE',f'{expr.value} node input must match the declared NODEDATA',value.token)
            codes.append(code)
        self.features.add(expr.value); self.features.add('extended services')
        self.service_uses.append(dict(operation=expr.value,body=self.current_routine.name if self.current_routine else self.program.name,line=expr.token.line,column=expr.token.column))
        if expr.value in ex.COOPERATIVE_PROCEDURES:
            return f'(yield from _rt.cooperative_service(self._state,{expr.value!r},[{", ".join(codes)}],{expr.token.line}))'
        return f'self._state.extended_call({expr.value!r},[{", ".join(codes)}],{expr.token.line})'

    def numeric_register(self, expr):
        reading = expr.value == 'GET_REG'
        if len(expr.args) != (5 if reading else 3):
            self.error('E_ARGUMENTS', f'{expr.value} requires {5 if reading else 3} arguments',expr.token)
        self.check_for_call(expr.token)
        codes = [self.require_type(expr.args[0],'INTEGER')]
        if not reading: codes.append(self.require_type(expr.args[1],'INTEGER' if expr.value == 'SET_INT_REG' else 'REAL'))
        targets = expr.args[1:] if reading else expr.args[2:]
        specs = ('BOOLEAN','INTEGER','REAL','INTEGER') if reading else ('INTEGER',)
        for target, required in zip(targets,specs):
            base = target
            while base.kind in ('field','index'): base = base.args[0]
            if target.kind not in ('name','field','index') or base.kind not in ('name','using_ref') or base.value in self.visible_constants():
                self.error('E_OUTPUT_ARGUMENT','Numeric register outputs require storage rooted in a variable',target.token)
            if self.protection_root(base) in self.active_counters: self.error('E_FOR_COUNTER','Numeric register output cannot write an active FOR counter',target.token)
            if self.is_position_read_only_access(target): self.error('E_POSITION_READ_ONLY','Numeric register output is read-only',target.token)
            if self.is_value_only_subfield(target): self.error('E_CONFIG_OUTPUT','CONFIG/association subfields cannot be numeric register output aliases',target.token)
            code, spec = self.reference(target)
            if spec != (required,): self.error('E_TYPE',f'{expr.value} output requires exact {required} storage',target.token)
            codes.append(code)
        self.features.add(expr.value)
        self.register_uses.append(dict(procedure=expr.value,body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=expr.token.line,column=expr.token.column,operation='read' if reading else 'write',
                                       argument_order=['register_no','real_flag','int_value','real_value','status'] if reading else ['register_no','value','status'],
                                       arguments_evaluated_once=True,output_parameters=[2,3,4,5] if reading else [3]))
        return f'self._state.numeric_register({expr.value!r}, {", ".join(codes)}, line={expr.token.line})'

    def microsecond_timer(self, expr):
        reading = expr.value == 'GET_USEC_TIM'
        count = 0 if reading else 2
        if len(expr.args) != count: self.error('E_ARGUMENTS', f'{expr.value} requires {count} arguments',expr.token)
        self.check_for_call(expr.token)
        codes = [self.require_type(argument,'INTEGER') for argument in expr.args]
        self.features.add(expr.value)
        self.microsecond_timer_uses.append(dict(function=expr.value,body=self.current_routine.name if self.current_routine else self.program.name,
                                                line=expr.token.line,column=expr.token.column,host_clock_read=reading,
                                                argument_order=[] if reading else ['later','earlier'],arguments_evaluated_once=True,result_type='INTEGER'))
        if reading: return f'self._state.microsecond_time({expr.token.line})'
        return f'_rt.usec_sub({", ".join(codes)}, {expr.token.line})'

    def time_text_conversion(self, expr):
        if len(expr.args) != 2: self.error('E_ARGUMENTS', f'{expr.value} requires two arguments',expr.token)
        self.check_for_call(expr.token)
        parsing = expr.value == 'CNV_STR_TIME'
        source = self.require_type(expr.args[0], 'STRING' if parsing else 'INTEGER')
        destination = expr.args[1]
        base = destination
        while base.kind in ('field','index'): base = base.args[0]
        if destination.kind not in ('name','field','index') or base.kind not in ('name','using_ref') or base.value in self.visible_constants():
            self.error('E_OUTPUT_ARGUMENT','Time conversion output requires storage rooted in a variable',destination.token)
        if self.protection_root(base) in self.active_counters: self.error('E_FOR_COUNTER','Time conversion cannot write an active FOR counter',destination.token)
        if self.is_position_read_only_access(destination): self.error('E_POSITION_READ_ONLY','POSITION orientation cannot be a time conversion output',destination.token)
        if self.is_value_only_subfield(destination): self.error('E_CONFIG_OUTPUT','CONFIG/association subfields cannot be time conversion output aliases',destination.token)
        target, spec = self.reference(destination)
        expected = 'INTEGER' if parsing else 'STRING'
        if spec[0] != expected: self.error('E_TYPE',f'{expr.value} output requires {expected}',destination.token)
        self.features.add(expr.value)
        self.time_text_uses.append(dict(name=expr.value,body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=expr.token.line,column=expr.token.column,argument_order=['source','target'],
                                       arguments_evaluated_once=True,output_type=expected))
        return f'_rt.time_text_conversion({expr.value!r}, {source}, {target}, line={expr.token.line})'

    def joint_conversion(self, expr):
        if len(expr.args) != 3:
            self.error('E_ARGUMENTS', f'{expr.value} requires exactly three arguments', expr.token)
        if self.mode == 'strict' and any(self.has_routine_call(argument) for argument in expr.args):
            self.error('E_EVALUATION_ORDER', 'Joint conversion arguments containing routine calls need order validation', expr.token)
        self.check_for_call(expr.token)
        for argument in expr.args:
            if argument.kind not in ('name', 'index', 'field') or self.root_name(argument) in self.visible_constants():
                self.error('E_JOINT_ARGUMENT', 'Joint conversions require bare variable/field/element arguments', argument.token)
        for output in expr.args[1:]:
            if self.protection_root(output) in self.active_counters:
                self.error('E_FOR_COUNTER', 'Joint conversion cannot write an active FOR counter', output.token)
            if self.is_position_read_only_access(output):
                self.error('E_POSITION_READ_ONLY', 'Joint conversion output is read-only', output.token)
            if self.is_value_only_subfield(output):
                self.error('E_CONFIG_OUTPUT', 'CONFIG/association subfields cannot be joint-conversion output aliases', output.token)
        source, source_type = self.expression(expr.args[0])
        if expr.value == 'CNV_REL_JPOS':
            target, target_type = self.reference(expr.args[1])
            array_type, joint_type = source_type, target_type
        else:
            target, target_type = self.expression(expr.args[1])
            array_type, joint_type = target_type, source_type
        if joint_type[0] != 'JOINTPOS': self.error('E_TYPE', 'Joint conversion requires JOINTPOS storage', expr.token)
        if (array_type[0] != 'ARRAY' or len(rt.array_dimensions(array_type)) != 1
                or rt.array_leaf_spec(array_type) != ('REAL',)):
            self.error('E_TYPE', 'Joint conversion requires one-dimensional ARRAY OF REAL', expr.token)
        status, status_type = self.reference(expr.args[2])
        if status_type != ('INTEGER',): self.error('E_TYPE', 'Joint conversion status requires exact INTEGER storage', expr.args[2].token)
        self.features.add(expr.value)
        self.joint_conversion_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                              line=expr.token.line, column=expr.token.column, procedure=expr.value,
                                              declared_axes=joint_type[1], output_parameters=[2,3],
                                              context='Explicit Program(joint_axes=...) required; declared width must match'))
        return f'self._state.joint_conversion({expr.value!r}, {source}, {target}, {status}, {expr.token.line})'

    def has_routine_call(self, expr):
        return expr.kind == 'call' and expr.value in self.routines or any(self.has_routine_call(x) for x in expr.args)

    def unpos_procedure(self, expr):
        if self.mode=='pythonic':
            if len(expr.args) not in (8,11):
                self.error('E_ARGUMENTS','UNPOS requires a pose, six REAL outputs, CONFIG and optionally three REAL axis outputs',expr.token)
            return self.unpos_value_procedure(expr)
        if len(expr.args) != 8:
            self.error('E_ARGUMENTS', 'UNPOS requires XYZWPR input, six REAL outputs and one CONFIG output', expr.token)
        if self.mode == 'strict' and any(self.has_routine_call(argument) for argument in expr.args):
            self.error('E_EVALUATION_ORDER', 'UNPOS arguments containing routine calls need order validation', expr.token)
        self.check_for_call(expr.token)
        codes = []
        expected = [('XYZWPR',), *(('REAL',) for _ in range(6)), ('CONFIG',)]
        for index, (argument, required) in enumerate(zip(expr.args, expected)):
            if argument.kind not in ('name', 'index', 'field') or self.root_name(argument) in self.visible_constants():
                self.error('E_UNPOS_ARGUMENT', 'UNPOS requires bare variable/field/element references', argument.token)
            if index:
                if self.protection_root(argument) in self.active_counters:
                    self.error('E_FOR_COUNTER', 'UNPOS cannot write an active FOR counter', argument.token)
                if self.is_position_read_only_access(argument):
                    self.error('E_POSITION_READ_ONLY', 'UNPOS output cannot be a read-only POSITION orientation field', argument.token)
                if self.is_value_only_subfield(argument):
                    self.error('E_CONFIG_OUTPUT', 'CONFIG/association scalar subfields cannot be UNPOS outputs', argument.token)
            reference, actual = self.reference(argument)
            if actual != required:
                self.error('E_TYPE', f'UNPOS argument {index+1} requires exact {required[0]} storage', argument.token)
            codes.append(reference)
        self.features.add('UNPOS')
        self.features.add('multiple outputs by reference')
        self.unpos_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                    line=expr.token.line, column=expr.token.column, output_parameters=list(range(2,9)),
                                    overlap='All eight references checked disjoint at runtime before output writes'))
        return f'_rt.unpos({codes[0]}, [{", ".join(codes[1:])}], line={expr.token.line})'

    def unpos_value_procedure(self,expr):
        self.check_for_call(expr.token)
        source,spec=self.expression(expr.args[0])
        if spec not in (('XYZWPR',),('POSITION',),('XYZWPREXT',)) and spec[0]!='JOINTPOS':
            self.error('E_TYPE','UNPOS input requires a pose value or model-backed JOINTPOS',expr.args[0].token)
        normalized=('XYZWPREXT',) if spec[0]=='JOINTPOS' else spec
        if spec[0]=='JOINTPOS': source=self.geometry_operand(source,spec,expr.args[0].token,'UNPOS')
        with_axes=len(expr.args)==11
        axes_option=',with_axes=True' if with_axes else ''
        source=f'_rt.unpos_source({source},{normalized!r},{expr.token.line}{axes_option})'
        expected=[('REAL',)]*6+[('CONFIG',)]
        if with_axes:
            expected.extend([('REAL',)]*3)
        outputs=[]
        for argument,required in zip(expr.args[1:],expected):
            if argument.kind not in ('name','index','field') or self.root_name(argument) in self.visible_constants():
                self.error('E_UNPOS_ARGUMENT','UNPOS outputs require writable variable/field/element references',argument.token)
            if self.protection_root(argument) in self.active_counters:
                self.error('E_FOR_COUNTER','UNPOS cannot write an active FOR counter',argument.token)
            if self.is_position_read_only_access(argument):
                self.error('E_POSITION_READ_ONLY','UNPOS output cannot be a read-only POSITION orientation field',argument.token)
            if self.is_value_only_subfield(argument):
                self.error('E_CONFIG_OUTPUT','CONFIG/association scalar subfields cannot be UNPOS outputs',argument.token)
            reference,actual=self.reference(argument)
            if actual!=required: self.error('E_TYPE',f'UNPOS output requires exact {required[0]} storage',argument.token)
            outputs.append(reference)
        self.features.update(('UNPOS','multiple outputs by reference','pose value extraction'))
        self.unpos_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
            line=expr.token.line,column=expr.token.column,output_parameters=list(range(2,len(expr.args)+1)),
            source_type=spec,source_kind=expr.args[0].kind,source_snapshot=True,external_axis_outputs=with_axes,
            overlap='Outputs checked disjoint at runtime; captured source may also be output storage'))
        return f'_rt.unpos_value({source}, [{", ".join(outputs)}], line={expr.token.line})'

    def routine_call(self, expr):
        routine = self.routines[expr.value]
        if len(expr.args) != len(routine.parameters):
            self.error('E_ARGUMENTS', f'{expr.value} expects {len(routine.parameters)} arguments, received {len(expr.args)}', expr.token)
        if self.mode == 'strict' and len(expr.args) > 1 and any(self.has_routine_call(arg) for arg in expr.args):
            self.error('E_EVALUATION_ORDER', 'Multiple arguments containing routine calls need evaluation-order validation', expr.token)
        arguments = []
        for argument, (formal, expected) in zip(expr.args, routine.parameters):
            line = argument.token.line
            if self.mode=='pythonic' and argument.kind=='call' and argument.value=='BYNAME' and 'BYNAME' not in self.routines:
                if len(argument.args)!=3: self.error('E_ARGUMENTS','BYNAME requires three arguments',argument.token)
                self.check_for_call(argument.token)
                if self.named_active_counters() or self.protection_root(argument.args[2]) in self.active_counters: self.error('E_FOR_COUNTER','BYNAME cannot alias or write an active FOR counter',argument.token)
                program=self.require_type(argument.args[0],'STRING');path=self.require_type(argument.args[1],'STRING')
                entry=argument.args[2]
                if entry.kind not in ('name','field','index') or self.root_name(entry) in self.visible_constants():
                    self.error('E_OUTPUT_ARGUMENT','BYNAME entry requires writable INTEGER storage',entry.token)
                if self.is_position_read_only_access(entry) or self.is_value_only_subfield(entry):
                    self.error('E_OUTPUT_ARGUMENT','BYNAME entry requires ordinary writable INTEGER storage',entry.token)
                code,spec=self.reference(entry)
                if spec!=('INTEGER',): self.error('E_TYPE','BYNAME entry requires exact INTEGER storage',entry.token)
                arguments.append(f'self._state.byname_argument({expected!r},{program},{path},{code},{line})')
                self.features.update(('BYNAME','extended services','parameter by reference'))
                self.service_uses.append(dict(operation='BYNAME',body=self.current_routine.name if self.current_routine else self.program.name,line=line,column=argument.token.column))
                continue
            if self.is_position_read_only_access(argument) and not self.is_system_pose_path(argument):
                self.error('E_POSITION_READ_ONLY_ARG', 'Bare POSITION orientation arguments need read-only passing evidence; use an explicit scalar expression for a value', argument.token)
            # Bare variable and indexed-variable arguments retain their storage.
            # Any grouping node, constant or expression is a temporary value.
            file_prefix=self.file_prefix_spec(argument)
            is_reference = (argument.kind in ('name', 'index', 'field') and self.root_name(argument) not in self.visible_constants()
                            and (not self.is_array_prefix_value(argument) or file_prefix is not None) and not self.is_system_pose_path(argument))
            if is_reference:
                code,actual=(self.file_prefix_argument(argument,routine,formal) if file_prefix is not None else self.reference(argument))
                if self.is_value_only_subfield(argument):
                    value, actual = self.expression(argument)
                    code = f'_rt.value_argument({expected!r}, {value}, {line})'
                    is_reference = False
                    row=dict(body=self.current_routine.name if self.current_routine else self.program.name,
                        routine=routine.name,parameter=formal.value,field=argument.value,
                        line=line,column=argument.token.column,evaluated_once=True)
                    if self.is_association_subfield(argument):
                        self.features.add('association subfield value argument')
                        self.association_value_uses.append(dict(row,record_type=self.access_type(argument.args[0])[0]))
                    else:
                        self.features.add('CONFIG subfield value argument');self.config_value_uses.append(row)
            else:
                value, actual = self.expression(argument)
                if actual[0]=='ARRAY' and rt.file_storage_type(actual):
                    self.error('E_FILE_ARRAY_VALUE','FILE ARRAY arguments require borrowed storage without grouping',argument.token)
                if self.mode=='pythonic' and rt.collection_type(actual):
                    if expected!=actual:
                        value=self.path_conversion_value(expected,actual,value,argument.token,'ARGUMENT')
                        actual=expected
                    code=f'_rt.collection_argument({expected!r},{value},{line},source_spec={actual!r})'
                    self.features.add('private logical scalar collection argument')
                elif self.mode=='pythonic' and rt.collection_array_type(actual):
                    if not rt.collection_array_source_accepts(expected,actual):
                        value=self.path_conversion_value(expected,actual,value,argument.token,'ARGUMENT')
                        actual=expected
                    code=f'_rt.collection_array_argument({expected!r},{value},{line},source_spec={actual!r})'
                    self.features.add('private logical collection ARRAY argument')
                else:code = f'_rt.value_argument({expected!r}, {value}, {line})'
            source_actual=actual;cartesian_conversion=False;conversion_kind='none'
            guarded_shape = self.mode == 'pythonic' and is_reference and array_formal_forward_match(expected, actual)
            conversion = routine_argument_conversion(expected, actual, mode=self.mode, guarded_array=guarded_shape)
            guarded_string=(self.mode=='pythonic' and is_reference and expected[0]==actual[0]=='STRING'
                and expected[1] is not None and actual[1] is None)
            if conversion == 'real_integral':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},_rt.real_integral_value({expected!r},{value},{line}),{line})'
                is_reference,actual=False,expected;conversion_kind='real_integral'
                self.features.add('checked REAL to integral value argument')
            elif conversion == 'config_word':
                value,_=self.expression(argument)
                value=self.config_word_conversion(expected,actual,value,argument.token,'ARGUMENT')
                code=f'_rt.value_argument({expected!r},{value},{line})'
                is_reference,actual=False,expected;conversion_kind='config_word'
            elif conversion == 'numeric_array':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},_rt.convert_numeric_array({expected!r},{value},{line}),{line})'
                is_reference,actual=False,expected
                conversion_kind='numeric_array'
                self.features.add('numeric ARRAY conversion')
                self.numeric_array_uses.append(dict(operation='ARGUMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=source_actual,target_type_spec=expected,evaluated_once=True,independent_value=True))
            elif conversion == 'positional_array':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},_rt.convert_positional_array({expected!r},{value},{line}),{line})'
                is_reference,actual=False,expected
                cartesian_conversion=True;conversion_kind='positional_array'
                self.features.add('positional ARRAY conversion')
                self.positional_array_uses.append(dict(operation='ARGUMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=source_actual,target_type_spec=expected,evaluated_once=True,independent_value=True))
            elif conversion == 'kinematic_array':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},self._state.kinematic_array({expected!r},{value},{line},kind="ARGUMENT"),{line})'
                is_reference,actual=False,expected
                cartesian_conversion=True;conversion_kind='kinematic_array'
                self.features.update(('extended services','kinematic ARRAY conversion'))
                if self.current_routine:self.current_routine.may_services=True
                self.kinematic_array_uses.append(dict(operation='ARGUMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=source_actual,target_type_spec=expected,evaluated_once=True,independent_value=True))
            elif conversion == 'kinematic_record':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},self._state.kinematic_record({expected!r},{value},{line},kind="ARGUMENT",source_spec={actual!r}),{line})'
                is_reference,actual=False,expected;conversion_kind='kinematic_record'
                self.features.update(('extended services','kinematic STRUCTURE conversion'))
                if self.current_routine:self.current_routine.may_services=True
                self.kinematic_record_uses.append(dict(operation='ARGUMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=source_actual,target_type_spec=expected,conversion_kind=rt.kinematic_record_kind(expected,source_actual),
                    evaluated_once=True,independent_value=True,geometry_preflight=True))
            elif conversion == 'record_schema':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},_rt.convert_record_schema({expected!r},{value},{line},source_spec={actual!r}),{line})'
                is_reference,actual=False,expected;conversion_kind='record_schema'
                self.features.add('source STRUCTURE schema conversion')
                self.record_schema_uses.append(dict(operation='ARGUMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=source_actual,target_type_spec=expected,conversion_kind=rt.record_schema_kind(expected,source_actual),
                    evaluated_once=True,independent_value=True))
            elif conversion == 'array_schema':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},_rt.convert_array_schema({expected!r},{value},{line}),{line})'
                is_reference,actual=False,expected;conversion_kind='array_schema'
                self.features.add('source ARRAY schema conversion')
                self.array_schema_uses.append(dict(operation='ARGUMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=source_actual,target_type_spec=expected,schema_change_kind=rt.array_schema_kind(expected,source_actual),
                    evaluated_once=True,independent_value=True))
            elif conversion == 'joint_width':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},_rt.convert_joint_width({expected!r},{value},{line}),{line})'
                is_reference,actual=False,expected
                cartesian_conversion=True;conversion_kind='joint_width'
                self.features.add('checked joint width conversion')
                self.joint_width_uses.append(dict(operation='ARGUMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=source_actual,target_type_spec=expected,evaluated_once=True,independent_value=True))
            elif conversion == 'kinematic':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},self._state.kinematic_interface({expected!r},{value},{line}),{line})'
                is_reference,actual=False,expected
                cartesian_conversion=True;conversion_kind='kinematic'
                self.features.update(('extended services','kinematic interface conversion'))
                if self.current_routine:self.current_routine.may_services=True
                self.kinematic_interface_uses.append(dict(operation='KINEMATIC_ARGUMENT',body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=source_actual,target_type_spec=expected,evaluated_once=True,independent_value=True))
            elif conversion == 'cartesian':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},{value},{line})'
                is_reference,actual=False,expected
                cartesian_conversion=True;conversion_kind='cartesian'
                self.features.add('Cartesian interface value conversion')
            elif conversion == 'integral_narrow':
                value,_=self.expression(argument)
                code=f'_rt.value_argument({expected!r},{value},{line})'
                is_reference,actual=False,expected
                self.features.add('checked integral to '+expected[0]+' value argument')
            elif conversion == 'narrow_promotion':
                narrow_type = actual[0]
                value, _ = self.expression(argument)
                code = f'_rt.value_argument({expected!r}, {value}, {line})'
                is_reference, actual = False, expected
                self.features.add(narrow_type + ' to ' + expected[0] + ' value argument')
            elif conversion == 'integer_to_real':
                value, _ = self.expression(argument)
                code = f'_rt.value_argument({expected!r}, {value}, {line})'
                is_reference, actual = False, expected
                self.features.add('INTEGER to REAL value argument')
            bounded_string_value = (not is_reference and expected[0] == actual[0] == 'STRING' and expected[1] is not None)
            if not rt.parameter_accepts(expected, actual) and not bounded_string_value and not guarded_shape and not guarded_string:
                self.error('E_TYPE', f'{expr.value} parameter expects {expected[0]}, found {actual[0]}', argument.token)
            if is_reference and self.protection_root(argument) in self.active_counters:
                if self.mode == 'strict' or formal.value in routine.parameter_writes:
                    self.error('E_FOR_COUNTER', 'An active FOR counter cannot be passed to a potentially writable formal; use parentheses for a value argument', argument.token)
                self.features.add('read-only active FOR counter reference')
            if not is_reference and expected[0] == 'ARRAY':
                if self.mode == 'strict':
                    self.error('E_ARRAY_VALUE', 'Whole ARRAY arguments cannot be passed by value', argument.token)
                self.features.add('writable ARRAY value argument')
                self.array_value_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                  routine=routine.name, parameter=formal.value, formal_spec=expected,
                                                  source_spec=actual, line=line, column=argument.token.column,
                                                  expression_kind=argument.kind, evaluated_once=True,
                                                  independent_writable_copy=True, initialized_elements_required=True))
                if conversion_kind in ('positional_array','kinematic_array','numeric_array','array_schema','record_schema','kinematic_record'):self.array_value_uses[-1].update(source_spec=source_actual,converted=True,conversion_kind=conversion_kind)
                if conversion_kind in ('numeric_array','array_schema','record_schema','kinematic_record'):self.array_value_uses[-1].update(initialized_elements_required=False,missing_data_preserved=True)
            if not is_reference and expected[0] == 'STRING':
                if self.mode != 'pythonic' and formal.value in routine.parameter_writes:
                    self.error('E_STRING_VALUE', 'STRING value arguments require a read-only formal; this parameter may be written through assignments or nested calls', argument.token)
                code = (f'_rt.value_argument({expected!r}, {value}, {line})' if bounded_string_value
                        else f'_rt.string_value_argument({value}, {line})')
                self.features.add('writable STRING value argument' if self.mode == 'pythonic' else 'read-only STRING value argument')
                self.string_value_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                   routine=routine.name, parameter=formal.value,
                                                   line=line, column=argument.token.column, expression_kind=argument.kind,
                                                   evaluated_once=True, independent_writable_copy=self.mode == 'pythonic',
                                                   temporary_capacity=(expected[1] if bounded_string_value else 254) if self.mode == 'pythonic' else None))
            if not is_reference and expected[0] == 'STRUCTURE':
                self.features.add('named STRUCTURE value argument')
                self.structure_value_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                      routine=routine.name, parameter=formal.value, type_name=expected[1],
                                                      line=line, column=argument.token.column, expression_kind=argument.kind,
                                                      evaluated_once=True, independent_writable_copy=True))
            if not is_reference and expected == ('VECTOR',):
                self.features.add('VECTOR value argument')
                self.vector_value_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                   routine=routine.name, parameter=formal.value,
                                                   line=line, column=argument.token.column, expression_kind=argument.kind,
                                                   evaluated_once=True, independent_writable_copy=True))
            if not is_reference and expected[0] in POSITIONAL_VALUE_TYPES:
                self.features.add('exact positional value argument')
                self.positional_value_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                       routine=routine.name, parameter=formal.value, type_spec=expected,
                                                       line=line, column=argument.token.column, expression_kind=argument.kind,
                                                       evaluated_once=True, independent_writable_copy=True))
                if self.mode=='pythonic':self.positional_value_uses[-1].update(source_type_spec=source_actual,converted=cartesian_conversion,conversion_kind=conversion_kind)
            if expected[0] in ('STRING', 'ARRAY', *RECORD_TYPES, 'JOINTPOS'):
                self.features.add(expected[0] + (' reference parameter' if is_reference else ' value parameter'))
            self.features.add('parameter by reference' if is_reference else 'parameter by value')
            if guarded_string:
                self.features.add('runtime-checked bounded STRING forwarding')
                self.string_forward_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=actual,target_type_spec=expected,alias_retained=True,
                    validation='Existing routine entry requires matching concrete STRING capacity before callee body/frame allocation'))
            if guarded_shape:
                self.features.add('runtime-checked fixed ARRAY forwarding')
                self.array_forward_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                    routine=routine.name,parameter=formal.value,line=line,column=argument.token.column,
                    source_type_spec=actual,target_type_spec=expected,alias_retained=True,
                    validation='Existing routine entry requires a matching concrete reference before callee body/frame allocation'))
            arguments.append(code)
        result=f'self._routine_{expr.value}({", ".join(arguments)})'
        return f'(yield from {result})' if self.cooperative else result

    def require_type(self, expr, expected):
        code, spec = self.expression(expr)
        if expected == 'INTEGER' and spec[0] in NARROW_TYPES: return f'_rt.integer({code}, {expr.token.line})'
        if expected == 'REAL' and spec[0] in INTEGRAL_TYPES: return f'_rt.real({code}, {expr.token.line})'
        if spec[0] != expected: self.error('E_TYPE', f'Expected {expected}, found {spec[0]}', expr.token)
        return code

    @staticmethod
    def format_literal(expr):
        """Recognize signed/grouped literals without folding runtime expressions."""
        sign = 1
        while expr.kind == 'group' or expr.kind == 'unary' and expr.value in ('+', '-'):
            if expr.kind == 'unary' and expr.value == '-': sign = -sign
            expr = expr.args[0]
        return sign * expr.value if expr.kind == 'literal' and type(expr.value) is int else None
