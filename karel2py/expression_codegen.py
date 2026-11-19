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
    PREDEFINED_CONSTANTS,
    PYTHONIC_CONSTRUCTORS,
    REGISTER_PROCEDURES,
    TIMER_FUNCTIONS,
    TIME_TEXT_PROCEDURES,
)
from .operator_types import POSE_OPERANDS, binary_result, operand_type, unary_result
from . import extended as ex
from . import runtime as rt


class ExpressionLowering:
    """Lower expressions against the current checked program and emitter scope."""

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
        if expr.kind == 'system_selection':
            return self.lower_system_selection(expr)
        pose = expr if expr.kind == 'system_pose' else self.system_axis_root(expr)
        if pose is not None:
            return self.lower_system_pose(expr, pose)
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

    def require_type(self, expr, expected):
        code, spec = self.expression(expr)
        if expected == 'INTEGER' and spec[0] in NARROW_TYPES: return f'_rt.integer({code}, {expr.token.line})'
        if expected == 'REAL' and spec[0] in INTEGRAL_TYPES: return f'_rt.real({code}, {expr.token.line})'
        if spec[0] != expected: self.error('E_TYPE', f'Expected {expected}, found {spec[0]}', expr.token)
        return code
