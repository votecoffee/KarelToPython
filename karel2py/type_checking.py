"""Source type and reference queries for checking declarations and generating Python."""
from . import extended as ex
from . import runtime as rt
from .call_analysis import plan_routine_argument
from .statement_io_analysis import format_literal
from .syntax import Expr
from .compiler_language import (
    BUILTIN_SIGNATURES,
    CONTROLLER_NAMES,
    INTEGRAL_TYPES,
    NARROW_TYPES,
    PYTHONIC_CONSTRUCTORS,
    RECORD_TYPES,
)


class TypeQueries:
    """Inspect source schemas and reference paths in the current scope."""

    def is_predefined_file(self,expr):
        if self.mode!='pythonic' or expr.kind!='name' or expr.value not in ex.PREDEFINED_FILE_NAMES:return False
        local=(self.current_routine.local_types.keys() | self.current_routine.local_constants.keys()) if self.current_routine else set()
        return expr.value not in self.types.keys() | self.constants.keys() | self.routines.keys() | self.user_types.keys() | local

    def symbol_type(self, expr):
        if self.is_predefined_file(expr):return ('FILE',)
        if self.current_routine and expr.value in self.current_routine.local_types:
            return self.current_routine.local_types[expr.value]
        if expr.value in self.visible_constants():
            value = self.visible_constants()[expr.value]
            return ('BOOLEAN',) if type(value) is bool else ('INTEGER',) if type(value) is int else ('REAL',) if type(value) is float else ('STRING', len(value))
        if expr.value not in self.types:
            code = 'E_CONTROLLER' if expr.value in CONTROLLER_NAMES else 'E_SYMBOL'
            self.error(code, f'Unknown or unsupported identifier {expr.value}', expr.token)
        return self.types[expr.value]

    @staticmethod
    def root_name(expr):
        while expr.kind in ('index', 'field', 'group', 'path_io_range'): expr = expr.args[0]
        return expr.value[2] if expr.kind == 'using_ref' else expr.value

    @staticmethod
    def protection_root(expr):
        """Track private aliases without inventing public storage provenance."""
        while expr.kind in ('index','field','group'):expr=expr.args[0]
        return expr.value[7] if expr.kind=='using_ref' else expr.value

    def path_header_index(self, operand):
        return self.mode == 'pythonic' and format_literal(operand, constants=self.visible_constants()) == 0

    def path_index_type(self, spec, operand):
        if self.path_header_index(operand):
            if spec[2] is None:
                self.error('E_PATH_HEADER', 'PATH index 0 requires a declared PATHHEADER', operand.token)
            return spec[2]
        return spec[1] or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']

    def path_record_selector(self, selector):
        """Identify an indexed PATH record that needs a stable USING binding."""
        while selector.kind == 'group':
            selector = selector.args[0]
        if selector.kind != 'index':
            return None
        spec = self.relative_operand_type(selector.args[0])
        if spec[0] == 'PATH' or rt.collection_array_node_type(spec, len(selector.args) - 1) is not None:
            return 'path_header' if self.path_header_index(selector.args[-1]) else 'path_node'
        return None

    def member_type(self, spec, expr):
        if spec[0]=='PATH':
            if not spec[2]: self.error('E_FIELD','PATH has no PATHHEADER',expr.token)
            return self.member_type(spec[2],expr)
        if spec[0] not in RECORD_TYPES: self.error('E_TYPE', 'Field access requires STRUCTURE or a supported data record', expr.token)
        fields = dict(rt.record_fields(spec))
        if expr.value not in fields:
            self.error('E_FIELD', f'{spec[1] if spec[0] == "STRUCTURE" else spec[0]} has no field {expr.value}', expr.token)
        self.features.add(spec[0] + ' field access')
        return fields[expr.value]

    def is_config_subfield(self, expr):
        if expr.kind != 'field': return False
        return self.access_type(expr.args[0])[0] == 'CONFIG'

    def is_association_subfield(self,expr):
        return expr.kind=='field' and self.access_type(expr.args[0])[0] in rt.ASSOCIATION_TYPES

    def is_value_only_subfield(self,expr):
        return self.is_config_subfield(expr) or self.is_association_subfield(expr)

    def array_prefix_spec(self, expr):
        """Inspect an incomplete flat ARRAY selection without evaluating its indexes."""
        if self.mode != 'pythonic' or expr.kind != 'index':
            return None
        base = expr.args[0]
        if base.kind == 'name' and base.value in ex.PORT_TYPES and base.value not in self.types:
            return None
        return rt.array_prefix_type(self.access_type(base), len(expr.args) - 1)

    def is_array_prefix_value(self, expr):
        return self.array_prefix_spec(expr) is not None

    def is_bare_storage(self, expr):
        return expr.kind in ('name', 'field', 'index') and self.root_name(expr) not in self.visible_constants()

    def file_prefix_spec(self, expr):
        prefix = self.array_prefix_spec(expr)
        return prefix if prefix is not None and rt.file_storage_type(prefix) else None

    def routine_argument_storage(self, expr):
        """Select ordinary or borrowable FILE references, leaving other operands by value."""
        prefix = self.array_prefix_spec(expr)
        file_prefix = prefix if prefix is not None and rt.file_storage_type(prefix) else None
        reference = (self.is_bare_storage(expr) and (prefix is None or file_prefix is not None)
                     and not self.is_system_pose_path(expr))
        return reference, file_prefix

    def argument_is_reference(self, argument, expected):
        """Classify source storage for routine-effect and input-contract analysis."""
        if not self.is_bare_storage(argument):
            return False
        prefix = self.array_prefix_spec(argument)
        if prefix is not None and not rt.file_storage_type(prefix):
            return False
        actual = prefix if prefix is not None else self.access_type(argument)
        plan = plan_routine_argument(expected, actual, mode=self.mode, reference=True)
        return plan.by_reference and not self.is_value_only_subfield(argument)

    def is_routine_formal(self, expr):
        return (expr.kind == 'name' and self.current_routine is not None
                and any(formal.value == expr.value for formal, _ in self.current_routine.parameters))

    def check_assignment_target(self, target, value):
        if self.root_name(target) in self.visible_constants():
            self.error('E_CONST_ASSIGN', 'Cannot assign to CONST', target.token)
        if self.protection_root(target) in self.active_counters:
            self.error('E_FOR_COUNTER', 'FOR counter writes inside its loop are blocked', target.token)
        if self.mode == 'strict' and self.has_routine_call(target):
            self.error('E_EVALUATION_ORDER', 'Routine calls in assignment target indexes need evaluation-order validation', target.token)
        if (self.mode == 'strict' and any(isinstance(node, Expr) and node.kind == 'index' for node in self.walk_nodes(target))
                and self.has_external_effect_call(value)):
            self.error('E_EVALUATION_ORDER',
                       'Effectful function results assigned to indexed targets need target/value evaluation-order validation', target.token)
        if self.is_position_read_only_access(target):
            self.error('E_POSITION_READ_ONLY',
                       'POSITION NORMAL, ORIENT and APPROACH fields and their components are read-only', target.token)

    def check_read_target(self, target):
        base = target
        while base.kind in ('field', 'index'):
            base = base.args[0]
        if target.kind not in ('name', 'field', 'index') or base.kind not in ('name', 'using_ref'):
            self.error('E_READ_ITEM', 'READ requires scalar storage rooted in a variable', target.token)
        root = self.root_name(target)
        if root in self.visible_constants():
            self.error('E_CONST_ASSIGN', 'READ cannot write CONST', target.token)
        if self.protection_root(target) in self.active_counters:
            self.error('E_FOR_COUNTER', 'READ cannot write an active FOR counter', target.token)
        if self.is_position_read_only_access(target):
            self.error('E_POSITION_READ_ONLY', 'READ cannot write POSITION orientation fields', target.token)
        if self.is_value_only_subfield(target) and self.mode != 'pythonic':
            self.error('E_CONFIG_OUTPUT', 'READ into CONFIG subfields needs a separate bounded output policy', target.token)
        return root

    def check_byname_counter(self, operand):
        if self.named_active_counters() or self.protection_root(operand.entry) in self.active_counters:
            self.error('E_FOR_COUNTER', 'BYNAME cannot alias or write an active FOR counter', operand.token)

    def check_byname_entry(self, entry):
        if not self.is_bare_storage(entry):
            self.error('E_OUTPUT_ARGUMENT', 'BYNAME entry requires writable INTEGER storage', entry.token)
        if self.is_position_read_only_access(entry) or self.is_value_only_subfield(entry):
            self.error('E_OUTPUT_ARGUMENT', 'BYNAME entry requires ordinary writable INTEGER storage', entry.token)

    def check_static_service_storage(self, expr, token):
        root = self.root_name(expr)
        if (expr.kind not in ('name', 'field', 'index', 'using_ref') or root not in self.types
                or root in self.visible_constants()
                or self.current_routine and root in self.current_routine.local_types):
            self.error('E_STATIC_ARGUMENT', 'Dynamic display requires static global storage', token)

    def check_service_output_storage(self, expr):
        if not self.is_bare_storage(expr):
            self.error('E_OUTPUT_ARGUMENT', 'Service output requires writable storage', expr.token)
        if self.protection_root(expr) in self.active_counters:
            self.error('E_FOR_COUNTER', 'Service output cannot write an active FOR counter', expr.token)
        if self.is_position_read_only_access(expr):
            self.error('E_POSITION_READ_ONLY', 'Service output is protected POSITION storage', expr.token)
        if self.is_value_only_subfield(expr):
            self.error('E_CONFIG_OUTPUT', 'CONFIG/association fields cannot be output aliases', expr.token)

    def access_type(self, expr):
        """Inspect receiver types without emitting calls or duplicate call-site reports."""
        if expr.kind=='system_selection':return ('INTEGER',)
        if expr.kind=='system_pose':return ('POSITION',)
        if self.system_axis_root(expr) is not None:return ('REAL',)
        if expr.kind == 'group': return self.access_type(expr.args[0])
        if expr.kind == 'using_ref': return expr.value[1]
        if self.mode=='pythonic' and expr.kind=='call' and expr.value in ex.FUNCTIONS and expr.value not in self.routines:
            return ex.FUNCTIONS[expr.value][1]
        if expr.kind == 'call' and expr.value in self.routines and self.routines[expr.value].return_type:
            return self.routines[expr.value].return_type
        if self.mode == 'pythonic' and expr.kind == 'call' and expr.value in PYTHONIC_CONSTRUCTORS and expr.value not in self.routines:
            if expr.value=='POS':
                return self.pos_call_result_type(expr)
            if expr.value in ('INV','FRAME'):
                if (expr.value == 'INV' and len(expr.args) != 1 or expr.value == 'FRAME' and len(expr.args) not in (3,4,5)):
                    self.error('E_ARGUMENTS', 'INV requires one operand; FRAME requires three points and optional origin and CONFIG', expr.token)
                return self.frame_call_result_type(expr.value,[self.relative_operand_type(argument) for argument in expr.args],expr.token)
            if expr.value in rt.POSITION_AXIS_FUNCTIONS:
                if len(expr.args) != 1: self.error('E_ARGUMENTS', f'{expr.value} requires one pose', expr.token)
                self.frame_result_type([self.access_type(expr.args[0])], expr.token)
                return ('VECTOR',)
            return BUILTIN_SIGNATURES[expr.value][1]
        if self.mode == 'pythonic' and expr.kind == 'binary' and expr.value == ':':
            return self.relative_result_type([self.relative_operand_type(argument) for argument in expr.args], expr.token)
        if expr.kind == 'name': return self.symbol_type(expr)
        if expr.kind == 'field': return self.member_type(self.access_type(expr.args[0]), expr)
        if expr.kind == 'index':
            spec = self.access_type(expr.args[0])
            if spec[0]=='PATH': return self.path_index_type(spec, expr.args[-1])
            if self.mode=='pythonic' and rt.joint_axis_access(spec,len(expr.args)-1):return ('REAL',)
            if self.mode=='pythonic' and rt.collection_array_node_type(spec,len(expr.args)-1) is not None:
                return self.path_index_type(rt.array_leaf_spec(spec), expr.args[-1])
            if spec[0] != 'ARRAY': self.error('E_TYPE', 'Indexing requires ARRAY', expr.token)
            prefix=rt.array_prefix_type(spec,len(expr.args)-1) if self.mode=='pythonic' else None
            if prefix is not None and rt.aggregate_write_type(prefix):return prefix
            try: return rt.indexed_type(spec, len(expr.args) - 1)
            except rt.KarelRuntimeError as exc: self.error('E_ARRAY_RANK', str(exc), expr.token)
        self.error('E_TYPE', 'Expected a variable receiver path', expr.token)

    def pos_call_result_type(self,expr):
        if len(expr.args) not in (7,10):
            self.error('E_ARGUMENTS','POS requires seven arguments and optionally three external axes',expr.token)
        return ('XYZWPREXT',) if len(expr.args)==10 else ('XYZWPR',)

    def frame_result_type(self, specs, token):
        if self.mode=='pythonic': specs=[('XYZWPREXT',) if spec[0]=='JOINTPOS' else spec for spec in specs]
        if not specs or any(spec not in (('XYZWPR',), ('POSITION',),('XYZWPREXT',)) for spec in specs):
            self.error('E_TYPE', 'Frame operations require POSITION or XYZWPR operands', token)
        return ('XYZWPREXT',) if ('XYZWPREXT',) in specs else ('POSITION',) if ('POSITION',) in specs else ('XYZWPR',)

    def relative_operand_type(self,expr):
        """Inspect frame-point arithmetic without emitting calls or report sites."""
        if expr.kind=='group':return self.relative_operand_type(expr.args[0])
        if expr.kind=='literal' and type(expr.value) in (int,float):return ('REAL',) if type(expr.value) is float else ('INTEGER',)
        if expr.kind=='field':return self.member_type(self.relative_operand_type(expr.args[0]),expr)
        if expr.kind=='unary' and expr.value in ('+','-'):
            spec=self.relative_operand_type(expr.args[0])
            if spec[0] in ('VECTOR','REAL','INTEGER',*NARROW_TYPES):return ('INTEGER',) if spec[0] in NARROW_TYPES else spec
        if expr.kind=='binary' and expr.value in ('+','-','*','/','DIV','MOD','#','@'):
            left,right=[self.relative_operand_type(value) for value in expr.args]
            left=('INTEGER',) if left[0] in NARROW_TYPES else left
            right=('INTEGER',) if right[0] in NARROW_TYPES else right
            op=expr.value
            if left==right==('VECTOR',) and op in ('+','-','#','@'):return ('REAL',) if op=='@' else ('VECTOR',)
            numeric=lambda spec:spec[0] in ('INTEGER','REAL')
            if op in ('*','/') and (left==('VECTOR',) and numeric(right) or right==('VECTOR',) and numeric(left)):return ('VECTOR',)
            if numeric(left) and numeric(right):
                if op in ('+','-','*','/'):return ('REAL',) if op=='/' or 'REAL' in (left[0],right[0]) else ('INTEGER',)
                if op in ('DIV','MOD') and left==right==('INTEGER',):return ('INTEGER',)
        return self.access_type(expr)

    def relative_result_type(self,specs,token):
        if len(specs)==2 and specs[0]==('VECTOR',):
            return ('VECTOR',) if specs[1]==('VECTOR',) else self.frame_result_type(specs[1:],token)
        if len(specs)==2 and specs[1]==('VECTOR',):
            self.frame_result_type(specs[:1],token)
            return ('VECTOR',)
        return self.frame_result_type(specs,token)

    def frame_call_result_type(self,operation,specs,token):
        if operation=='INV' and specs==[('VECTOR',)]:return ('VECTOR',)
        if operation=='FRAME':
            if len(specs)==5 and specs[-1]!=('CONFIG',):
                self.error('E_ARGUMENTS','Five-argument FRAME requires CONFIG as the fifth argument',token)
            if len(specs)>3 and specs[-1]==('CONFIG',):
                origin=specs[3] if len(specs)==5 else specs[0]
                if origin!=('VECTOR',):
                    self.error('E_TYPE','FRAME with explicit CONFIG requires a VECTOR origin',token)
                poses=[spec for spec in specs[:-1] if spec!=('VECTOR',)]
                return self.frame_result_type(poses or [('XYZWPR',)],token)
            if specs[0 if len(specs)==3 else 3]==('VECTOR',):
                self.error('E_TYPE','FRAME origin requires a pose or supplied joint frame with CONFIG',token)
            return self.frame_result_type([spec for spec in specs if spec!=('VECTOR',)],token)
        return self.frame_result_type(specs,token)

    def is_position_read_only_access(self, expr):
        """Check receiver paths, without mistaking an index expression for a target."""
        while expr.kind in ('field', 'index'):
            if expr.kind == 'field':
                parent_type = self.access_type(expr.args[0])
                if parent_type[0] == 'POSITION' and expr.value in rt.POSITION_READ_ONLY_FIELDS:
                    return True
            expr = expr.args[0]
            while expr.kind == 'group': expr = expr.args[0]
        return expr.kind == 'using_ref' and expr.value[3]

    @staticmethod
    def is_system_pose_path(expr):
        while expr.kind in ('field','index','group'):expr=expr.args[0]
        return expr.kind=='system_pose'

    @staticmethod
    def system_axis_root(expr):
        if expr.kind!='field' or expr.value not in ex.SYSTEM_POSE_AXES:return None
        root=expr.args[0]
        while root.kind=='group':root=root.args[0]
        return root if root.kind=='system_pose' else None

    @staticmethod
    def compatible(target, source):
        if target == source or target[0] == source[0] == 'STRING': return True
        if target[0] in INTEGRAL_TYPES and source[0] in INTEGRAL_TYPES: return True
        if target[0] == 'REAL' and source[0] in INTEGRAL_TYPES: return True
        # Unknown formal lengths defer the concrete size check to the runtime.
        if target[0] != 'ARRAY' or source[0] != 'ARRAY': return False
        target_name, source_name = rt.array_identity(target), rt.array_identity(source)
        target_shape, source_shape = rt.array_dimensions(target), rt.array_dimensions(source)
        if target_name != source_name:
            if target_name is not None and source_name is not None: return False
            if None not in target_shape and None not in source_shape: return False
        if target[2][0] == source[2][0] == 'ARRAY' and rt.array_identity(target[2]) != rt.array_identity(source[2]):
            return False
        target_leaf, source_leaf = rt.array_leaf_spec(target), rt.array_leaf_spec(source)
        inherited_string=target_leaf[0]==source_leaf[0]=='STRING' and (target_leaf[1] is None or source_leaf[1] is None)
        if None not in target_shape and None not in source_shape and not inherited_string:return False
        elements_match = (target_leaf == source_leaf or
                          target_leaf[0] == source_leaf[0] == 'STRING'
                          and (target_leaf[1] is None or source_leaf[1] is None))
        return (elements_match and len(target_shape) == len(source_shape) and
                all(a == b or a is None or b is None for a, b in zip(target_shape, source_shape)))
