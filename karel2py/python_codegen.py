"""Generate Python statements, routine bodies, dispatch and module scaffolding."""
import ast
import re
from .compiler_language import SKIPPABLE_STATEMENTS
from .array_schema_analysis import ArraySchemaAnalysis
from .assignment_codegen import AssignmentLowering
from .builtin_codegen import BuiltinFunctionLowering
from .constant_analysis import ConstantAnalysis
from .conversion_codegen import SchemaConversionLowering
from .declarations import DeclarationPasses
from .flow_codegen import ControlFlowLowering
from .function_codegen import FunctionCallLowering
from .handler_codegen import HandlerLowering
from .loop_codegen import LoopLowering
from .syntax import Expr, Statement
from .select_codegen import SelectLowering
from .expression_codegen import ExpressionLowering
from .motion_codegen import MotionLowering
from .named_type_analysis import NamedTypeAnalysis
from .operator_codegen import OperatorLowering
from .output_procedure_codegen import OutputProcedureLowering
from .procedure_codegen import ProcedureLowering
from .program_cli_codegen import ProgramCLILowering
from .program_codegen import ProgramLowering
from .reference_codegen import ReferenceLowering
from .robot_system_codegen import RobotSystemLowering
from .routine_codegen import RoutineLowering
from .routine_declarations import RoutineDeclarations
from .routine_effects import RoutineEffectAnalysis
from .service_codegen import ServiceCallLowering
from .source_normalization import SourceNormalization
from .statement_io_codegen import StatementIOLowering
from .task_codegen import TaskControlLowering
from .timing_codegen import TimingLowering
from .type_checking import TypeQueries
from .using_codegen import UsingLowering
from .lexer import Token, TranslationError
from . import extended as ex
from . import runtime as rt


class Emitter(DeclarationPasses, TypeQueries, ExpressionLowering, AssignmentLowering,
              RoutineLowering, RobotSystemLowering, ServiceCallLowering, StatementIOLowering,
              MotionLowering, TaskControlLowering, HandlerLowering, LoopLowering, UsingLowering,
              ControlFlowLowering, SelectLowering, SourceNormalization, RoutineEffectAnalysis,
              ConstantAnalysis, NamedTypeAnalysis, ArraySchemaAnalysis, RoutineDeclarations,
              ProgramLowering, ProgramCLILowering, ProcedureLowering, TimingLowering,
              BuiltinFunctionLowering, OutputProcedureLowering, ReferenceLowering, OperatorLowering,
              FunctionCallLowering, SchemaConversionLowering):
    """Emit a Python module from a parsed program and its checked declarations."""

    def __init__(self, program, filename, array_shapes=None, mode='strict', cooperative=False):
        self.program, self.filename = program, filename
        self.mode = mode
        self.constants, self.types, self.routines, self.user_types = {}, {}, {}, {}
        self.initialize_named_type_analysis()
        self.file_prefix_argument_uses=[]
        self.initialize_constant_analysis()
        self.array_formal_uses=[];self.array_forward_uses=[]
        self.string_formal_uses=[];self.string_forward_uses=[]
        self.short_circuit_expressions=set()
        self.node_size_schemas = {}
        self.path_assignment_schemas = {}
        self.staged_data_assignments = {}
        self.data_argument_conversions = {}
        self.data_return_conversions = {}
        self.geometry_assignment_conversions = {}
        self.geometry_argument_conversions = {}
        self.geometry_expression_types = {}
        self.write_item_types = {}
        self.write_collection_types = {}
        self.repeat_capture_types = {}
        self.geometry_return_conversions = {}
        self.path_array_conversion_schemas = {}
        self.predefined_structure_uses = []
        self.lines, self.source_map, self.features = [], [], set()
        self.source_checkpoints=set()
        self.skippable_checkpoints=set()
        self.indent, self.temporary = 0, 0
        self.current_routine = None
        self.cooperative = mode == 'pythonic' and (
            cooperative
            or any(
                (isinstance(node, Statement) and node.kind in (
                    'read', 'file_read', 'file_write', 'write_items', 'file_cancel', 'pulse',
                    'task_control', 'condition', 'condition_control', 'timer_connect',
                    'timer_disconnect', 'signal_event', 'signal_semaphore', 'motion',
                    'motion_action', 'motion_control',
                ))
                or (isinstance(node, Expr) and (
                    node.kind in ('event', 'edge', 'semaphore', 'wait_pause', 'wait_error', 'wait_lifecycle')
                    or (node.kind == 'call' and node.value in (
                        {'PAUSE_TASK', 'CONT_TASK', 'ABORT_TASK', 'RUN_TASK'} | ex.COOPERATIVE_PROCEDURES
                    ))
                ))
                for body in (program.body, *[routine.body for routine in program.routines])
                for node in self.walk_nodes(body)
            )
            or any(routine.external for routine in program.routines)
            or any(row['name'] in rt.TASK_DIRECTIVES for row in program.directive_metadata)
        )
        self.group_uses=[]
        self.using_scopes = []
        self.active_counters = set()
        self.private_using_roots = {}
        self.escaped_private_using_roots = set()
        self.retained_timer_alias_roots=set()
        self.retained_path_counter_roots=set()
        self.unknown_path_counter_alias=False
        self.reference_for_uses=[]
        self.connected_timer_uses=[]
        self.handler_uses=[]
        self.callback_input_plans = {}
        self.system_pose_uses=[]
        self.system_pose_writes=[]
        self.system_selection_uses=[]
        self.external_write_routines=set()
        self.control_flow = dict(program=None, routines={}, jump_policy='body_labels_no_new_for_or_using' if mode=='pythonic' else 'same_block_or_ancestor_no_for', controller_validated=False)
        self.select_scopes = []
        self.subarray_uses = []
        self.array_index_chains = []
        self.array_prefix_uses = []
        self.array_prefix_target_uses = []
        self.delay_uses = []
        self.wait_uses = []
        self.string_value_uses = []
        self.string_return_uses = []
        self.write_uses = []
        self.read_uses = []
        self.config_field_read_uses=[]
        self.config_value_uses = []
        self.joint_conversion_uses = []
        self.abort_uses = []
        self.unpos_uses = []
        self.variable_array_uses = []
        self.vector_return_uses = []
        self.vector_value_uses = []
        self.vector_constructor_uses = []
        self.pos_constructor_uses = []
        self.config_text_uses = []
        self.time_text_uses = []
        self.microsecond_timer_uses = []
        self.register_uses = []
        self.service_uses = []
        self.frame_operation_uses = []
        self.position_axis_uses = []
        self.position_comparison_uses = []
        self.position_conversion_uses = []
        self.kinematic_assignment_uses = []
        self.kinematic_interface_uses=[]
        self.kinematic_array_uses=[]
        self.kinematic_record_uses=[]
        self.path_schema_uses=[]
        self.joint_width_uses=[]
        self.positional_array_uses=[]
        self.numeric_array_uses=[]
        self.config_word_uses=[]
        self.association_value_uses=[]
        self.joint_axis_uses=[]
        self.array_schema_uses=[]
        self.record_schema_uses=[]
        self.joint_geometry_uses = []
        self.pulse_uses = []
        self.motion_uses = []
        self.initialization_query_uses = []
        self.structure_return_uses = []
        self.structure_value_uses = []
        self.positional_return_uses = []
        self.positional_value_uses = []
        self.trig_uses = []
        self.atan2_uses = []
        self.array_return_uses = []
        self.array_result_assignments = []
        self.array_function_uses = []
        self.array_value_uses = []
        self.bare_function_uses = []
        self.array_shapes = {}
        context_token = Token('NAME', '<array_shapes>', 1, 1)
        if array_shapes is not None:
            if type(array_shapes) is not dict:
                self.error('E_ARRAY_CONTEXT', 'array_shapes must be a dict of global variable names to dimension lists/tuples', context_token)
            for name, shape in array_shapes.items():
                if type(name) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name) is None:
                    self.error('E_ARRAY_CONTEXT', 'External ARRAY names must be ASCII KAREL identifiers', context_token)
                key = name.upper()
                if key in self.array_shapes:
                    self.error('E_ARRAY_CONTEXT', f'Duplicate case-insensitive external ARRAY name {key}', context_token)
                if type(shape) not in (tuple, list) or not 1 <= len(shape) <= 3:
                    self.error('E_ARRAY_CONTEXT', f'{key} requires one to three explicit outer dimensions', context_token)
                if any(type(size) is not int or not 1 <= size <= 32767 for size in shape):
                    self.error('E_ARRAY_CONTEXT', f'{key} external dimensions must be INTEGER in 1..32767', context_token)
                self.array_shapes[key] = tuple(shape)
        self.array_shapes = dict(sorted(self.array_shapes.items()))

    def error(self, code, message, token):
        raise TranslationError(code, message, token, self.filename)

    def line(self, text='', token=None):
        if self.cooperative:
            def checkpoint(match):
                argument=match[1]
                if self.mode=='pythonic' and token is not None and argument.isdecimal():
                    self.source_checkpoints.add(int(argument))
                    return f'(yield from _rt.checkpoint(self._state,{argument},_source=True))'
                return f'(yield from _rt.checkpoint(self._state,{argument}))'
            text=re.sub(r'^self\._state\.tick\(([^()]*)\)$',checkpoint,text)
        self.lines.append('    ' * self.indent + text)
        if token:
            self.source_map.append(dict(python_line=len(self.lines), karel_line=token.line,
                                        karel_column=token.column))

    def fresh(self):
        self.temporary += 1
        return f'_temporary_{self.temporary}'

    def block(self, statements):
        if not statements: self.line('pass')
        for statement in statements: self.statement(statement)

    def statement(self, stmt, file_code=None):
        token, kind = stmt.token, stmt.kind
        line = token.line
        self.features.add(kind)
        skippable=self.cooperative and file_code is None and kind in SKIPPABLE_STATEMENTS
        if skippable:
            self.source_checkpoints.add(line)
            self.skippable_checkpoints.add(line)
            self.line(f'if not (yield from _rt.checkpoint(self._state,{line},_source=True,_skippable=True)):',token)
            self.indent+=1
        elif self.cooperative and file_code is not None:
            self.line(f'yield from _rt.checkpoint(self._state,{line})',token)
        else:
            self.line(f'self._state.tick({line})', token)
        self.statement_body(stmt,file_code)
        if skippable:self.indent-=1

    def statement_body(self, stmt, file_code=None):
        token, kind = stmt.token, stmt.kind
        if kind == 'motion_control':
            self.lower_motion_control(stmt)
        elif kind in ('motion', 'motion_action'):
            self.lower_motion_request(stmt)
        elif kind == 'pulse':
            self.lower_pulse(stmt)
        elif kind == 'task_control':
            self.lower_task_control(stmt)
        elif kind in ('signal_event', 'signal_semaphore'):
            self.lower_task_signal(stmt)
        elif kind == 'handler_action':
            self.lower_handler_action(stmt)
        elif kind in ('timer_connect', 'timer_disconnect'):
            self.lower_connected_timer(stmt)
        elif kind == 'condition_control':
            self.lower_condition_control(stmt)
        elif kind == 'condition':
            self.lower_condition(stmt)
        elif kind in ('file_read', 'file_write'):
            self.lower_explicit_file_io(stmt)
        elif kind == 'file_cancel':
            self.lower_file_cancel(stmt)
        elif kind in ('file_open', 'file_close'):
            self.lower_file_lifecycle(stmt)
        elif kind == 'system_selection_assign':
            target, value = stmt.args
            self.lower_system_selection_write(target, value, token)
        elif kind == 'system_pose_assign':
            target, value = stmt.args
            self.lower_system_pose_write(target, value, token)
        elif kind == 'assign':
            target, value = stmt.args
            self.lower_assignment(target, value, token)
        elif kind == 'using':
            self.emit_using_entry(stmt)
            self.block(stmt.body)
        elif kind == 'abort':
            self.lower_task_abort(token)
        elif kind == 'delay':
            self.lower_delay(stmt)
        elif kind == 'wait':
            self.lower_wait(stmt)
        elif kind == 'write_items':
            self.lower_write_items(stmt, file_code)
        elif kind == 'write':
            self.lower_legacy_write(stmt)
        elif kind == 'read':
            self.lower_read(stmt, file_code)
        elif kind in ('if', 'while'):
            self.emit_structured_condition(stmt)
        elif kind == 'repeat':
            self.emit_structured_repeat(stmt)
        elif kind == 'for':
            self.emit_structured_for(stmt)
        elif kind == 'select':
            self.emit_structured_select(stmt)
        elif kind == 'call':
            self.lower_procedure_statement(stmt)
        elif kind == 'return':
            if self.current_routine is None:
                self.emit_program_return(stmt.args[0], token)
            else:
                self.routine_return(stmt.args[0], token)
        else:
            self.error('E_INTERNAL', f'Unexpected statement {kind}', token)

    def emit(self):
        if self.mode=='pythonic':self.normalize_array_chains()
        module_names = self.validate_module_declarations()
        self.validate_routine_declarations(module_names)
        self.normalize_body_references()
        self.analyze_routine_effects()
        self.emit_program_class()
        self.emit_routine_definitions()
        self.emit_program_entry()
        self.emit_program_runtime_metadata()
        self.emit_program_cli()
        result = '\n'.join(self.lines) + '\n'
        ast.parse(result)
        return result
