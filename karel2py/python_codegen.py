"""Generate Python statements, routine bodies, dispatch and module scaffolding."""
import ast
import re
from .compiler_language import (
    BUILTIN_PROCEDURES,
    CONFIG_TEXT_PROCEDURES,
    JOINT_PROCEDURES,
    REGISTER_PROCEDURES,
    SKIPPABLE_STATEMENTS,
    TIME_TEXT_PROCEDURES,
)
from .array_schema_analysis import ArraySchemaAnalysis
from .assignment_codegen import AssignmentLowering
from .constant_analysis import ConstantAnalysis
from .declarations import DeclarationPasses
from .flow_codegen import ControlFlowLowering
from .handler_codegen import HandlerLowering
from .loop_codegen import LoopLowering
from .syntax import Expr, Statement
from .select_codegen import SelectLowering
from .expression_codegen import ExpressionLowering
from .motion_codegen import MotionLowering
from .named_type_analysis import NamedTypeAnalysis
from .program_cli_codegen import ProgramCLILowering
from .program_codegen import ProgramLowering
from .robot_system_codegen import RobotSystemLowering
from .routine_codegen import RoutineLowering
from .routine_declarations import RoutineDeclarations
from .routine_effects import RoutineEffectAnalysis
from .service_codegen import ServiceCallLowering
from .source_normalization import SourceNormalization
from .statement_io_codegen import StatementIOLowering
from .task_codegen import TaskControlLowering
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
              ProgramLowering, ProgramCLILowering):
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
        self.predefined_structure_uses = []
        self.lines, self.source_map, self.features = [], [], set()
        self.source_checkpoints=set()
        self.skippable_checkpoints=set()
        self.indent, self.temporary = 0, 0
        self.current_routine = None
        self.cooperative=mode=='pythonic' and (cooperative or any(isinstance(node,Statement) and node.kind in ('file_read','file_write','write_items','file_cancel','pulse','task_control','condition','condition_control','timer_connect','timer_disconnect','signal_event','signal_semaphore','motion','motion_action','motion_control') or isinstance(node,Expr) and (node.kind in ('event','edge','semaphore') or node.kind=='call' and node.value in {'PAUSE_TASK','CONT_TASK','ABORT_TASK','RUN_TASK'}|ex.COOPERATIVE_PROCEDURES) for body in (program.body,*[r.body for r in program.routines]) for node in self.walk_nodes(body)) or any(r.external for r in program.routines))
        if mode=='pythonic' and any(row['name'] in rt.TASK_DIRECTIVES for row in program.directive_metadata): self.cooperative=True
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
        line = token.line
        if kind == 'motion_control':
            self.lower_motion_control(stmt)
            return
        if kind in ('motion', 'motion_action'):
            self.lower_motion_request(stmt)
            return
        if kind=='pulse':
            if 'DOUT' in self.types or 'DOUT' in self.visible_constants(): self.error('E_PULSE','PULSE requires the unshadowed DOUT port bank',token)
            number=self.require_type(stmt.args[0],'INTEGER');duration=self.require_type(stmt.args[1],'INTEGER')
            self.features.update(('ports','extended services'))
            self.pulse_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,nowait=stmt.args[2],operands_evaluated_once=True))
            self.line(f'yield from _rt.pulse_execution(self._state,{number},{duration},{stmt.args[2]!r},{line})',token);return
        if kind == 'task_control':
            self.lower_task_control(stmt)
            return
        if kind in ('signal_event', 'signal_semaphore'):
            self.lower_task_signal(stmt)
            return
        if kind == 'handler_action':
            self.lower_handler_action(stmt)
            return
        if kind in ('timer_connect', 'timer_disconnect'):
            self.lower_connected_timer(stmt)
            return
        if kind == 'condition_control':
            self.lower_condition_control(stmt)
            return
        if kind == 'condition':
            self.lower_condition(stmt)
            return
        if kind in ('file_read','file_write'):
            file_value=self.require_type(stmt.args[0],'FILE'); captured_file=self.fresh()
            self.line(f'{captured_file}={file_value}',token); self.features.add('memory files')
            self.statement(stmt.args[1],file_code=captured_file); return
        if kind=='file_cancel':
            file_value=self.require_type(stmt.args[0],'FILE') if stmt.args[0] is not None else f'self._state.default_file("READ",{line},required=True)'
            self.features.add('cooperative FILE cancellation')
            self.line(f'_rt.cancel_file(self._state,{file_value},{line})',token);return
        if kind in ('file_open','file_close'):
            if kind=='file_open' and self.is_predefined_file(stmt.args[0]):self.error('E_PREDEFINED_FILE_OPEN','Configure predefined FILE endpoints through ExecutionContext bindings',token)
            file_value=self.require_type(stmt.args[0],'FILE'); self.features.add('memory files')
            if kind=='file_open':
                mode=self.require_type(stmt.args[1],'STRING'); name=self.require_type(stmt.args[2],'STRING')
                self.line(f'self._state.file_open({file_value},{mode},{name},{line})',token)
            else: self.line(f'self._state.file_close({file_value},{line})',token)
            return
        if kind == 'system_selection_assign':
            target, value = stmt.args
            self.lower_system_selection_write(target, value, token)
            return
        if kind == 'system_pose_assign':
            target, value = stmt.args
            self.lower_system_pose_write(target, value, token)
            return
        if kind == 'assign':
            target, value = stmt.args
            self.lower_assignment(target, value, token)
        elif kind == 'using':
            self.emit_using_entry(stmt)
            self.block(stmt.body)
        elif kind == 'abort':
            self.lower_task_abort(token)
        elif kind == 'delay':
            duration = self.require_type(stmt.args[0], 'INTEGER')
            if self.cooperative:
                self.line(f'yield from _rt.delay_execution(self._state,{duration},{line},scan_handlers={self.mode=="pythonic"!r})',token)
            else:
                self.line(f'self._state.delay({duration}, {line})',token)
            self.features.add('DELAY')
            self.delay_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                        line=token.line, column=token.column, duration_type='INTEGER',
                                        evaluated='once; runtime range check'))
        elif kind == 'wait':
            condition = self.require_type(stmt.args[0], 'BOOLEAN')
            self.line(f'while not {self.test_code(condition,line)}:', token)
            self.indent += 1
            self.line(f'self._state.wait_poll({line})', token)
            self.indent -= 1
            self.features.add('WAIT FOR')
            self.wait_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                      line=line, column=token.column, condition_kind=stmt.args[0].kind,
                                      condition_type='BOOLEAN', evaluation='once per check until true',
                                      yield_seconds=0.0, step_budgeted=True))
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
            expr = stmt.args[0]
            if self.mode=='pythonic' and expr.value in ex.PROCEDURES and expr.value not in self.routines:
                self.line(self.service_call(expr),token); return
            if self.mode == 'pythonic' and expr.value in REGISTER_PROCEDURES and expr.value not in self.routines:
                self.line(self.numeric_register(expr), token)
                return
            if self.mode == 'pythonic' and expr.value in TIME_TEXT_PROCEDURES and expr.value not in self.routines:
                self.line(self.time_text_conversion(expr), token)
                return
            if self.mode == 'pythonic' and expr.value in CONFIG_TEXT_PROCEDURES and expr.value not in self.routines:
                self.line(self.config_text_conversion(expr), token)
                return
            if expr.value in JOINT_PROCEDURES:
                self.line(self.joint_conversion(expr), token)
                return
            if expr.value == 'UNPOS':
                self.line(self.unpos_procedure(expr), token)
                return
            if expr.value in BUILTIN_PROCEDURES:
                self.line(self.conversion_procedure(expr), token)
                return
            if expr.value not in self.routines:
                self.error('E_CALL', f'Unknown or unsupported procedure {expr.value}', token)
            if self.routines[expr.value].return_type:
                self.error('E_CALL', 'Statement calls require procedures', token)
            self.check_for_call(token, self.routines[expr.value])
            self.line(self.routine_call(expr), token)
        elif kind == 'return':
            self.routine_return(stmt.args[0], token)
        else: self.error('E_INTERNAL', f'Unexpected statement {kind}', token)

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
