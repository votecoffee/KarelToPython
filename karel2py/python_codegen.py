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
from .assignment_codegen import AssignmentLowering
from .declarations import DeclarationPasses
from .handler_codegen import HandlerLowering
from .loop_codegen import LoopLowering
from .syntax import Expr, Statement
from .select_analysis import check_select
from .expression_codegen import ExpressionLowering
from .motion_codegen import MotionLowering
from .robot_system_codegen import RobotSystemLowering
from .routine_codegen import RoutineLowering
from .service_codegen import ServiceCallLowering
from .statement_io_codegen import StatementIOLowering
from .task_codegen import TaskControlLowering
from .type_checking import TypeQueries
from .using_codegen import UsingLowering
from .control_flow import FlowGraph, validate_labels
from .lexer import Token, TranslationError
from . import __version__
from . import extended as ex
from . import runtime as rt


class Emitter(DeclarationPasses, TypeQueries, ExpressionLowering, AssignmentLowering,
              RoutineLowering, RobotSystemLowering, ServiceCallLowering, StatementIOLowering,
              MotionLowering, TaskControlLowering, HandlerLowering, LoopLowering, UsingLowering):
    """Emit a Python module from a parsed program and its checked declarations."""

    def __init__(self, program, filename, array_shapes=None, mode='strict', cooperative=False):
        self.program, self.filename = program, filename
        self.mode = mode
        self.constants, self.types, self.routines, self.user_types = {}, {}, {}, {}
        self.type_aliases = []
        self.file_prefix_argument_uses=[]
        self.constant_dependency_uses=[];self.constant_resolution_order=[]
        self.array_formal_uses=[];self.array_forward_uses=[]
        self.string_formal_uses=[];self.string_forward_uses=[]
        self.short_circuit_expressions=set()
        self.constant_builtin_uses=[];self._constant_builtin_cache={};self._constant_builtin_depth=0
        self._constant_declaration=None
        self.type_dependency_uses=[];self.type_resolution_order=[];self._type_schema_costs={}
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

    def validate_labels(self, statements):
        conflicts = set(self.types) | set(self.visible_constants()) | set(self.user_types) | set(self.routines) | {self.program.name}
        if self.current_routine:
            conflicts.update(self.current_routine.local_types)
        return validate_labels(statements, conflicts=conflicts, mode=self.mode, error=self.error)

    def select_code(self, stmt):
        checked = check_select(stmt, mode=self.mode, expression=self.expression, require_type=self.require_type,
                               constant=self.constant, visible_constants=self.visible_constants, error=self.error)
        category, selector, spec = checked.category, checked.selector, checked.schema
        cases = [tuple(case.value for case in row) for row in checked.clauses]
        sites = []
        if category is None:
            table = repr(tuple(cases))
        else:
            expressions = []
            for case_index, row in enumerate(checked.clauses):
                codes = []
                for value_index, case in enumerate(row):
                    expr = case.source
                    code = f'_rt.select_scalar({case.code},{category!r},{expr.token.line})' if case.dynamic else repr(case.value)
                    codes.append(code)
                    sites.append(dict(clause=case_index, value_index=value_index, line=expr.token.line, column=expr.token.column,
                                      expression_kind=expr.kind, type=case.kind, dynamic=case.dynamic, evaluated_once=True))
                expressions.append('(' + ','.join(codes) + ',)')
            # Validate/capture the selector before any case expression effects.
            selector = f'_rt.select_scalar({selector},{category!r},{stmt.token.line})'
            table = '(' + ','.join(expressions) + ',)'
        self.select_scopes.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=stmt.token.line, column=stmt.token.column, case_values=cases,
                                       case_count=len(cases), has_else=stmt.has_else,
                                       empty_else=stmt.has_else and not stmt.alternate,
                                       no_match='else_clause' if stmt.has_else else 'KarelRuntimeError'))
        if category is not None:
            dynamic = any(site['dynamic'] for site in sites)
            case_types = [[case.kind for case in row] for row in checked.clauses]
            self.select_scopes[-1].update(selector_type=spec, comparison_category=category, case_types=case_types,
                dynamic_cases=dynamic, case_expressions=sites, case_evaluation='all_once_left_to_right_before_matching')
            if spec[0] in ('BOOLEAN', 'STRING', 'REAL'): self.features.add('Pythonic scalar SELECT')
            if dynamic: self.features.add('dynamic SELECT case expressions')
        self.features.add('SELECT first matching CASE')
        self.features.add('SELECT no-match guard')
        category_code = f',category={category!r}' if category is not None else ''
        return f'_rt.select_case({selector}, {table}, {stmt.has_else!r}, {stmt.token.line}{category_code})'

    def emit_body(self, statements):
        labelled,transfers=self.validate_labels(statements)
        if not labelled:
            report = dict(engine='structured_python', labels={})
            self.block(statements)
        else:
            graph = FlowGraph(statements,lower_for=self.mode=='pythonic')
            report = graph.report()
            self.features.add('label control-flow dispatcher')
            pc = self.fresh()
            frames=done=None
            if graph.for_scopes:
                self.features.add('FOR dispatcher scopes and checked jumps')
                frames,done=self.fresh(),self.fresh()
                self.line(f'{frames} = []')
                self.line(f'{done} = object()')
                self.line('try:');self.indent+=1
            self.line(f'{pc} = {graph.entry!r}')
            self.line(f'while {pc} is not None:')
            self.indent += 1
            self.line(f'match {pc}:')
            self.indent += 1
            for index, node in enumerate(graph.nodes):
                stmt, kind = node.statement, node.kind
                token, line = stmt.token, stmt.token.line
                self.line(f'case {index}:', token)
                self.indent += 1
                previous_counters=self.active_counters
                if graph.for_scopes:
                    self.active_counters={self.protection_root(graph.for_scopes[scope].args[0]) for scope in node.for_scopes}
                    self.line(f'while {frames} and {frames}[-1][0] not in {node.for_scopes!r}:')
                    self.indent+=1;self.line(f'{frames}.pop()[1].clear()');self.indent-=1
                    self.line(f'if tuple(_frame[0] for _frame in {frames}) != {node.for_scopes!r}:')
                    self.indent+=1;self.line(f'raise _rt.KarelRuntimeError("Invalid generated FOR scope state", {line})');self.indent-=1
                if kind in ('label', 'goto', 'enter'):
                    self.features.add(stmt.kind)
                    if kind != 'label': self.line(f'self._state.tick({line})', token)
                    if kind == 'enter' and stmt.kind == 'using': self.emit_using_entry(stmt)
                    self.line(f'{pc} = {node.targets[0]!r}')
                elif kind=='for_enter':
                    self.features.add('for');self.line(f'self._state.tick({line})',token)
                    operands = self.for_operands(stmt)
                    stop, captured = self.fresh(), self.fresh()
                    self.capture_for_counter(operands, captured, line)
                    self.line(f'{frames}.append([{index}, {captured}, None])')
                    self.line(f'{stop} = {operands.final}')
                    start = f'_rt.require({captured}.raw(), {line})'
                    self.line(f'{frames}[-1][2] = iter({operands.range_code(start, stop)})')
                    self.line(f'{pc} = {node.targets[0]!r}')
                elif kind=='for_next':
                    item=self.fresh()
                    self.line(f'{item} = next({frames}[-1][2], {done})')
                    self.line(f'if {item} is {done}:');self.indent+=1
                    self.line(f'{pc} = {node.targets[1]!r}');self.indent-=1
                    self.line('else:');self.indent+=1
                    self.line(f'self._state.tick({line})',token)
                    self.line(f'{frames}[-1][1].set({item}, {line})')
                    self.line(f'{pc} = {node.targets[0]!r}');self.indent-=1
                elif kind=='for_exit':
                    self.line(f'{frames}.pop()[1].clear()')
                    self.line(f'{pc} = {node.targets[0]!r}')
                elif kind in ('if', 'while_test', 'repeat_test'):
                    self.features.add(stmt.kind)
                    if kind == 'if': self.line(f'self._state.tick({line})', token)
                    condition = self.require_type(stmt.args[0], 'BOOLEAN')
                    yes, no = node.targets
                    self.line(f'{pc} = {yes!r} if {self.test_code(condition,line)} else {no!r}', token)
                elif kind == 'select':
                    self.features.add('select')
                    self.line(f'self._state.tick({line})', token)
                    temporary = self.fresh()
                    self.line(f'{temporary} = {self.select_code(stmt)}', token)
                    self.line(f'match {temporary}:')
                    self.indent += 1
                    for case_index, _ in enumerate(stmt.args[1]):
                        case_token = stmt.args[1][case_index][0]
                        self.line(f'case {case_index}:', case_token)
                        self.indent += 1
                        self.line(f'{pc} = {node.targets[case_index]!r}')
                        self.indent -= 1
                    self.line('case _:')
                    self.indent += 1
                    if stmt.has_else:
                        self.line(f'{pc} = {node.targets[-1]!r}')
                    else:
                        self.line(f'raise _rt.KarelRuntimeError("No match in CASE", {line})', token)
                    self.indent -= 2
                elif kind == 'abort':
                    self.statement(stmt)  # Terminal node: no fall-through successor.
                else:
                    self.statement(stmt)
                    self.line(f'{pc} = {node.targets[0]!r}')
                self.indent -= 1
                self.active_counters=previous_counters
            self.line('case _:')
            self.indent += 1
            self.line('raise _rt.KarelRuntimeError("Invalid generated control-flow state")')
            self.indent -= 3
            if graph.for_scopes:
                self.indent-=1;self.line('finally:');self.indent+=1
                self.line(f'while {frames}:');self.indent+=1
                self.line(f'{frames}.pop()[1].clear()');self.indent-=2
        report['jumps']=transfers
        if self.current_routine: self.control_flow['routines'][self.current_routine.name] = report
        else: self.control_flow['program'] = report

    def test_code(self,code,line):
        return f'(yield from _rt.cooperative_test(self._state,lambda: {code},{line}))' if self.cooperative else f'self._state.test({code},{line})'

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
            condition = self.require_type(stmt.args[0], 'BOOLEAN')
            self.line(f'{kind} {self.test_code(condition,line)}:', token)
            self.indent += 1
            self.block(stmt.body)
            self.indent -= 1
            if kind == 'if' and stmt.alternate:
                self.line('else:')
                self.indent += 1
                self.block(stmt.alternate)
                self.indent -= 1
        elif kind == 'repeat':
            condition = self.require_type(stmt.args[0], 'BOOLEAN')
            self.line('while True:', token)
            self.indent += 1
            self.block(stmt.body)
            self.line(f'if {self.test_code(condition,line)}:')
            self.indent += 1
            self.line('break')
            self.indent -= 2
        elif kind == 'for':
            self.emit_structured_for(stmt)
        elif kind == 'select':
            _, cases = stmt.args
            temporary = self.fresh()
            self.line(f'{temporary} = {self.select_code(stmt)}', token)
            self.line(f'match {temporary}:')
            self.indent += 1
            for index, (case_token, _, body) in enumerate(cases):
                self.line(f'case {index}:', case_token)
                self.indent += 1
                self.block(body)
                self.indent -= 1
            self.line('case _:')
            self.indent += 1
            if stmt.has_else:
                self.block(stmt.alternate)
            else:
                self.line(f'raise _rt.KarelRuntimeError("No match in CASE", {line})', token)
            self.indent -= 2
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
        self.validate_symbols()
        self.line(f'# Generated by karel2py {__version__}; offline prototype, not controller-equivalence proof.')
        self.line('from karel2py import runtime as _rt')
        self.line()
        self.line('class Program:')
        self.indent = 1
        self.line(f'source_program = {self.program.name!r}')
        self.line(f'translation_mode = {self.mode!r}')
        self.line(f'source_directives = {tuple((row["name"], row["argument"]) for row in self.program.directive_metadata)!r}')
        self.line(f'source_storage_declarations = {tuple((row["owner"],row["name"],row["pool"],row["line"],row["column"]) for row in self.program.storage_declarations)!r}')
        if self.program.storage_declarations:self.features.add('VAR storage clause')
        self.line(f'source_groups = {tuple(sorted(set(row["group"] for row in self.group_uses)))!r}')
        self.line(f'imported_variables = {tuple(self.program.imported_variables)!r}')
        self.line(f'imported_types = {tuple((row["name"], row["owner"]) for row in self.program.imported_types)!r}')
        owners = {name:self.program.name for name in self.user_types}
        owners.update((row['name'],row['owner']) for row in self.program.imported_types)
        self.line(f'type_owners = {owners!r}')
        if self.program.imported_types: self.features.add('source-linked TYPE FROM declaration')
        self.line(f'routine_interfaces = { {r.name:dict(parameters=tuple(spec for _,spec in r.parameters),result=r.return_type,external=r.external) for r in self.program.routines}!r}')
        self.line(f'external_array_shapes = {tuple(self.array_shapes.items())!r}')
        self.line(f'variable_types = {self.user_types!r}')
        if self.mode=='pythonic':
            self.line('input_analysis = None')
            self.line('input_analysis_sha256 = None')
        self.line(f'@_rt._with_numeric_mode({self.mode!r})')
        self.line('def __init__(self, *, sleep=None, write=None, read=None, joint_axes=None, pose_tolerance=None, external_tolerance=None, clock_us=None, registers=None, context=None):')
        self.indent = 2
        self.line(f'self._state = _rt.State({self.types!r}, {self.constants!r}, sleep=sleep, write=write, read=read, joint_axes=joint_axes, pose_tolerance=pose_tolerance, external_tolerance=external_tolerance, clock_us=clock_us, registers=registers, context=context)')
        self.line(f'self._state.program_name={self.program.name!r}')
        self.line('self._state.program=self')
        self.line('if len(self.source_groups)==1: self._state.robot_group=self.source_groups[0]')
        if self.mode=='pythonic': self.line('_rt.configure_task(self._state,self.source_directives)')
        self.line('self._state.execution.variables.attach(self.source_program,self._state)')
        self.indent = 1
        self.line()
        self.line('@property')
        self.line('def source_settings(self):')
        self.indent = 2
        self.line('return self._state._source_settings.copy()')
        self.indent = 1
        self.line()
        self.line('@property')
        self.line('def pose_tolerance(self):')
        self.indent = 2
        self.line('return self._state.pose_tolerance')
        self.indent = 1
        self.line()
        self.line('@property')
        self.line('def write_requests(self):')
        self.indent = 2
        self.line('return tuple(request.copy() for request in self._state.write_requests)')
        self.indent = 1
        self.line()
        self.line('@property')
        self.line('def read_requests(self):')
        self.indent = 2
        self.line('return self._state.read_observations()')
        self.indent = 1
        self.line()
        self.line('@property')
        self.line('def clock_reads(self):')
        self.indent = 2
        self.line('return tuple(observation.copy() for observation in self._state.clock_reads)')
        self.indent = 1
        self.line()
        self.line('@property')
        self.line('def register_requests(self):')
        self.indent = 2
        self.line('return tuple(request.copy() for request in self._state.register_requests)')
        self.indent = 1
        self.line('@property')
        self.line('def service_requests(self):')
        self.indent = 2
        self.line('return tuple(request.copy() for request in self._state.service_requests)')
        self.indent = 1
        self.line()
        self.line('@property')
        self.line('def task_settings(self):')
        self.indent = 2
        self.line('return _rt.task_root(self._state)._task_settings.copy()')
        self.indent = 1
        self.line('@property')
        self.line('def task_trace(self):')
        self.indent = 2
        self.line('return tuple(row.copy() for row in _rt.task_root(self._state)._task_trace)')
        self.indent = 1
        self.line()
        self.line('@property')
        self.line('def abort_info(self):')
        self.indent = 2
        self.line('return self._state.abort_info')
        self.indent = 1
        self.line()
        self.line('def snapshot(self):')
        self.indent = 2
        self.line('return self._state.snapshot()')
        self.indent = 1
        for routine in self.program.routines:
            self.current_routine = routine
            self.line()
            argument_names = [f'_argument_{i}' for i in range(len(routine.parameters))]
            signature = ', '.join(['self'] + argument_names)
            self.line(f'@_rt._with_numeric_mode({self.mode!r})')
            self.line(f'def _routine_{routine.name}({signature}):', routine.token)
            self.indent = 2
            self.line(f'self._state.tick({routine.token.line})')
            bindings = ', '.join(f'{token.value!r}: {arg}' for (token, _), arg in zip(routine.parameters, argument_names))
            self.line(f'self._state.enter_routine({routine.local_types!r}, {routine.token.line}, {{{bindings}}}, routine={routine.name!r})')
            self.line('try:')
            self.indent = 3
            if routine.external:
                self.line(f'return (yield from self._state.external_call({routine.external!r},{routine.name!r},[{", ".join(argument_names)}],{routine.return_type!r},{routine.token.line}))',routine.token)
            else: self.emit_body(routine.body)
            if routine.return_type and not routine.external:
                self.line(f'raise _rt.KarelRuntimeError("Function completed without RETURN", {routine.token.line})')
            self.indent = 2
            self.line('finally:')
            self.indent = 3
            self.line('self._state.leave_routine()')
            self.indent = 1
        self.current_routine = None
        self.line()
        if self.cooperative:
            self.line(f'@_rt._with_numeric_mode({self.mode!r})')
            self.line('def run(self, *, max_steps=100000):'); self.indent=2
            self.line('return _rt.run_cooperative(self,max_steps)'); self.indent=1
            self.line(f'@_rt._with_numeric_mode({self.mode!r})')
            self.line('def resume(self):'); self.indent=2
            self.line('return _rt.resume_cooperative(self)'); self.indent=1
            self.line(f'@_rt._with_numeric_mode({self.mode!r})')
            self.line('def powerup(self):'); self.indent=2; self.line('return _rt.powerup_cooperative(self)'); self.indent=1
            self.line('def pause(self):'); self.indent=2; self.line("_rt.request_task_control(self._state,'PAUSE')"); self.indent=1
            self.line('def stop(self):'); self.indent=2; self.line('return _rt.stop_cooperative(self)'); self.indent=1
            self.line('@property'); self.line('def task_state(self):'); self.indent=2; self.line('return self._state.task_state'); self.indent=1
        self.line(f'@_rt._with_numeric_mode({self.mode!r})')
        sync_entry=self.mode=='pythonic' and not self.cooperative
        self.line('def _execute(self):' if self.cooperative else 'def _execute_sync(self):' if sync_entry else 'def run(self, *, max_steps=100000):')
        self.indent = 2
        if self.cooperative: self.line('if False: yield None')
        if not self.cooperative and not sync_entry:
            self.line('self._state.begin(max_steps)')
            self.line('self._state._driving=True')
            self.line('try:'); self.indent+=1
        if self.cooperative: self.line('try:'); self.indent+=1
        self.emit_body(self.program.body)
        if self.cooperative:
            self.indent-=1; self.line('except _rt.KarelRuntimeError as _failure:'); self.indent+=1
            self.line('yield from _rt.runtime_failure(self._state,_failure)'); self.line('raise'); self.indent-=1
        self.line('return self._state.snapshot()')
        if not self.cooperative and not sync_entry:
            self.indent-=1;self.line('finally:');self.indent+=1
            self.line('self._state._driving=False')
            self.line('self._state.finish_teach_programs()')
        if sync_entry:
            self.indent=1;self.line()
            self.line(f'@_rt._with_numeric_mode({self.mode!r})')
            self.line('def run(self, *, max_steps=100000):');self.indent=2
            self.line('self._state.begin(max_steps)');self.line('self._state._driving=True')
            self.line('_completed = False')
            self.line('try:');self.indent=3
            self.line('_result = self._execute_sync()')
            self.line('_completed = True')
            self.line('return _result')
            self.indent=2;self.line('finally:');self.indent=3
            self.line('self._state._driving=False');self.line('self._state.finish_teach_programs(interrupted=not _completed)')
        if self.mode=='pythonic' and self.program.routines:
            counter_roots={routine.name:set() for routine in self.program.routines if not routine.external}
            for use in self.reference_for_uses:
                if use['body'] in counter_roots and use['root'] is not None:
                    counter_roots[use['body']].add(use['root'])
            self.indent=1
            self.line(f'local_for_roots = { {name:tuple(sorted(roots)) for name,roots in counter_roots.items()}!r}')
        if self.mode=='pythonic' and self.cooperative:
            self.indent=1
            self.line(f'source_checkpoints = {tuple(sorted(self.source_checkpoints))!r}')
            self.line(f'skippable_checkpoints = {tuple(sorted(self.skippable_checkpoints))!r}')
        self.indent = 0
        self.line()
        self.line('if __name__ == "__main__":')
        self.indent = 1
        if self.mode=='pythonic' or self.features & (JOINT_PROCEDURES | REGISTER_PROCEDURES) or self.features & {'read','operator >=<','extended services','ports','memory files'}:
            self.line('import argparse as _argparse')
            self.line('_parser = _argparse.ArgumentParser(description="Explicit offline execution context; no controller connection")')
            if self.features & JOINT_PROCEDURES:
                self.line('_parser.add_argument("--joint-axes", type=int, choices=range(1, 10), required=True)')
            if self.features & REGISTER_PROCEDURES:
                self.line('_parser.add_argument("--registers", help="UTF-8 JSON numeric bank; defaults to the numeric bank in --context")')
            if 'operator >=<' in self.features:
                self.line('_parser.add_argument("--location-tolerance-mm", type=float, required=True)')
                self.line('_parser.add_argument("--orientation-tolerance-deg", type=float, required=True)')
                self.line('_config = _parser.add_mutually_exclusive_group(required=True)')
                self.line('_config.add_argument("--check-config", dest="check_config", action="store_true")')
                self.line('_config.add_argument("--ignore-config", dest="check_config", action="store_false")')
            if 'read' in self.features:
                self.line('_input = _parser.add_mutually_exclusive_group(required=False)')
                self.line('_input.add_argument("--read-values", help="UTF-8 JSON list of typed response batches, one per READ")')
                self.line('_input.add_argument("--read-text", help="UTF-8 ASCII text input for Pythonic READ")')
            self.line('_parser.add_argument("--context", help="Explicit offline service configuration JSON")')
            self.line('_rt.directory_files_options(_parser)')
            self.line('_parser.add_argument("--state-out", help="Save offline banks and global values as JSON")')
            self.line('_parser.add_argument("--max-steps", type=int, default=100000, help="Maximum execution steps")')
            if self.mode=='pythonic':
                self.line('_parser.add_argument("--external-collections", help="UTF-8 JSON fixed logical values for explicitly named external collection functions")')
                self.line('_parser.add_argument("--external-values", help="UTF-8 JSON explicit data, procedures, argument cases and staged outputs for external routines")')
            if 'operator >=<' in self.features:
                self.line('_parser.add_argument("--external-axis-tolerances", type=float, nargs=3, help="Explicit tolerances for EXT1, EXT2, EXT3")')
            self.line('_args = _parser.parse_args()')
            self.line('if _args.max_steps < 1: _parser.error("--max-steps must be positive")')
            self.line('_files = _rt.directory_files_from_args(_parser, _args)')
            self.line('import json as _json')
            self.line('_context = None')
            self.line('if _args.context is not None:')
            self.indent += 1
            self.line('try:')
            self.indent += 1
            if self.mode=='pythonic':
                self.line('_context = _rt.ExecutionContext.load(_args.context)')
            else:
                self.line('with open(_args.context, encoding="utf-8-sig") as _stream: _context = _rt.ExecutionContext.from_config(_json.load(_stream))')
            self.indent -= 1
            self.line('except (OSError, KeyError, TypeError, ValueError, _rt.KarelRuntimeError) as _error:')
            self.indent += 1
            self.line('_parser.error("Invalid service context: "+str(_error))')
            self.indent -= 2
            if self.mode=='pythonic':
                self.line('if _args.external_collections is not None or _args.external_values is not None:')
                self.indent+=1;self.line('try:');self.indent+=1
                self.line('_bindings = _rt.load_external_bindings(values=_args.external_values, collections=_args.external_collections, outputs=(_args.state_out,))')
                self.line('if _context is None: _context = _rt.ExecutionContext()')
                self.line('_context.externals.update(_bindings)')
                self.indent-=1;self.line('except (OSError, ValueError, _rt.KarelRuntimeError) as _error:')
                self.indent+=1;self.line('_parser.error(("Invalid external collections: " if _args.external_values is None else "Invalid external bindings: ")+str(_error))');self.indent-=2
            self.line('if _files is not None or _args.state_out is not None:')
            self.indent += 1
            self.line('if _context is None: _context = _rt.ExecutionContext()')
            self.line('if _files is not None: _context.files = _files')
            self.indent -= 1
            if self.features & REGISTER_PROCEDURES:
                self.line('_registers = _context.numeric if _context is not None else None')
                self.line('if _args.registers is not None:')
                self.indent += 1
                self.line('try:')
                self.indent += 1
                self.line('with open(_args.registers, encoding="utf-8-sig") as _stream:')
                self.indent += 1
                self.line('_registers = _rt.NumericRegisters.from_config(_json.load(_stream))')
                self.indent -= 2
                self.line('except (OSError, TypeError, ValueError, _rt.KarelRuntimeError) as _error:')
                self.indent += 1
                self.line('_parser.error("Unable to load numeric registers: " + str(_error))')
                self.indent -= 2
                self.line('if _registers is None: _parser.error("Numeric register calls require --registers or --context with a numeric bank")')
                self.line('if _context is None: _context = _rt.ExecutionContext()')
                self.line('_context.numeric = _registers')
            if 'operator >=<' in self.features:
                self.line('try:')
                self.indent += 1
                self.line('_pose_tolerance = _rt.checked_pose_tolerance((_args.location_tolerance_mm, _args.orientation_tolerance_deg, _args.check_config))')
                self.indent -= 1
                self.line('except ValueError as _error:')
                self.indent += 1
                self.line('_parser.error(str(_error))')
                self.indent -= 1
            if 'read' in self.features:
                self.line('_responses = None')
                self.line('if _args.read_values is not None or _args.read_text is not None:')
                self.indent += 1
                self.line('import json as _json')
                self.line('try:')
                self.indent += 1
                self.line('with open(_args.read_values if _args.read_values is not None else _args.read_text, encoding="utf-8-sig", newline="") as _stream:')
                self.indent += 1
                self.line('_responses = _json.load(_stream) if _args.read_values is not None else _rt.TextInput(_stream.read())')
                self.indent -= 2
                self.line('except (OSError, ValueError) as _error:')
                self.indent += 1
                self.line('_parser.error("Unable to load READ input: " + str(_error))')
                self.indent -= 1
                self.line('if _args.read_values is not None:')
                self.indent += 1
                self.line('if type(_responses) is not list: _parser.error("READ batches must be a JSON list")')
                self.line('_batches = iter(_responses)')
                self.line('_responses = lambda request: next(_batches)')
                self.indent -= 2
            context = ['context=_context']
            if self.features & REGISTER_PROCEDURES: context.append('registers=_registers')
            if self.features & JOINT_PROCEDURES: context.append('joint_axes=_args.joint_axes')
            if 'operator >=<' in self.features: context.extend(('pose_tolerance=_pose_tolerance','external_tolerance=_args.external_axis_tolerances'))
            if 'read' in self.features: context.append('read=_responses')
            self.line(f'_program = Program({", ".join(context)})')
            self.line('print(_program.run(max_steps=_args.max_steps))')
            self.line('if _args.state_out is not None:')
            self.indent += 1
            self.line('if _program._state.registers is not None: _context.numeric = _program._state.registers')
            self.line('_context.save(_args.state_out)')
            self.indent -= 1
        else:
            self.line('print(Program().run())')
        result = '\n'.join(self.lines) + '\n'
        ast.parse(result)
        return result
