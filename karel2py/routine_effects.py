"""Collect direct routine effects and propagate them through the checked call graph."""
from . import extended as ex
from . import runtime as rt
from .compiler_language import (
    BUILTIN_PROCEDURES,
    CONFIG_TEXT_PROCEDURES,
    MULTI_OUTPUT_PROCEDURES,
    REGISTER_PROCEDURES,
    TIME_TEXT_PROCEDURES,
)
from .retained_aliases import RetainedAliasAnalysis
from .syntax import Expr, Statement


ROUTINE_EFFECT_FLAGS = (
    'side_effecting', 'may_delay', 'may_write', 'may_read', 'may_abort', 'may_clock',
    'may_read_registers', 'may_write_registers', 'may_services',
)


def _callers_reaching(edges, seeds):
    reached = set(seeds)
    while True:
        callers = {name for name, targets in edges.items() if targets & reached}
        if callers <= reached:
            return reached
        reached.update(callers)


class RoutineEffectAnalysis(RetainedAliasAnalysis):
    """Record write effects used by routine binding, loop checks, and reports."""

    def analyze_routine_effects(self):
        calls = {routine.name: self._collect_direct_effects(routine) for routine in self.program.routines}
        edges = {name: {call.value for call in call_sites} for name, call_sites in calls.items()}
        self._propagate_routine_effects(edges, calls)

        external = {routine.name for routine in self.program.routines if routine.external}
        self.external_write_routines = _callers_reaching(edges, external)
        handlers, timers = set(), set()
        for routine in self.program.routines:
            for node in self.walk_nodes(routine.body):
                if isinstance(node, Statement):
                    if node.kind == 'condition':
                        handlers.add(routine.name)
                    elif node.kind == 'timer_connect':
                        timers.add(routine.name)
        private_retainers = _callers_reaching(edges, handlers | timers | external)
        handler_retainers = _callers_reaching(edges, handlers)
        path_retainers = _callers_reaching(edges, handler_retainers | external)
        self.analyze_retained_aliases(private_retainers, handler_retainers, path_retainers)
        self.current_routine = None

    def _record_routine_write(self, routine, root, local_names, parameter_names):
        if root is not None and root not in local_names:
            routine.side_effecting = True
        if root in parameter_names:
            routine.parameter_writes.add(root)
        if root in self.types and root not in local_names and root not in parameter_names:
            routine.global_writes.add(root)

    def _collect_procedure_effects(self, routine, call, local_names, parameter_names):
        name = call.value
        outputs = []
        if name in MULTI_OUTPUT_PROCEDURES:
            outputs.extend(call.args[1:])
        if self.mode == 'pythonic' and name not in self.routines:
            if name in CONFIG_TEXT_PROCEDURES | TIME_TEXT_PROCEDURES:
                outputs.extend(call.args[1:3] if name == 'CNV_STR_CONF' else call.args[1:])
            if name in REGISTER_PROCEDURES:
                if name == 'GET_REG':
                    routine.may_read_registers = True
                    outputs.extend(call.args[1:])
                else:
                    routine.may_write_registers = True
                    outputs.extend(call.args[2:])
        if name in BUILTIN_PROCEDURES and call.args:
            outputs.append(call.args[-1])
        for output in outputs:
            self._record_routine_write(routine, self.root_name(output), local_names, parameter_names)

    def _collect_statement_effects(self, routine, node, local_names, parameter_names):
        kind = node.kind
        if kind in ('motion', 'motion_action', 'motion_control', 'file_cancel', 'system_pose_assign', 'system_selection_assign'):
            routine.may_services = True
        if kind == 'pulse':
            routine.may_services = True
            routine.may_delay |= not node.args[2]
        if kind in ('delay', 'wait'):
            routine.may_delay = True
        if kind in ('write', 'write_items'):
            routine.may_write = True
        if kind == 'read':
            routine.may_read = True
            for target in node.args:
                if target.kind != 'read_cr':
                    destination = target.args[0] if target.kind == 'read_item' else target
                    self._record_routine_write(routine, self.root_name(destination), local_names, parameter_names)
        if kind == 'abort':
            routine.may_abort = True
        if kind in ('assign', 'for', 'timer_connect', 'timer_disconnect'):
            root = self.root_name(node.args[0])
            if kind in ('timer_connect', 'timer_disconnect') and root in parameter_names:
                routine.timer_parameter_writes.add(root)
            self._record_routine_write(routine, root, local_names, parameter_names)
        if kind == 'call':
            self._collect_procedure_effects(routine, node.args[0], local_names, parameter_names)

    def _collect_expression_effects(self, routine, node, local_names, parameter_names):
        if node.kind in ('system_pose', 'system_selection'):
            routine.may_services = True
        if self.mode != 'pythonic':
            return
        if (node.kind == 'name' and node.value in ex.PREDEFINED_FILE_NAMES
                and node.value not in self.types.keys() | self.constants.keys() | self.routines.keys()
                | self.user_types.keys() | routine.local_types.keys() | routine.local_constants.keys()):
            routine.may_services = True
        if node.kind != 'call' or node.value in self.routines:
            return
        name = node.value
        if name == 'GET_USEC_TIM':
            routine.may_clock = True
        if name not in ex.PROCEDURES.keys() | ex.FUNCTIONS.keys():
            return
        routine.may_services = True
        if name == 'PRINT_FILE':
            routine.may_write = True
        for argument, (mode, _) in zip(node.args, ex.signature_for(name, len(node.args))):
            if mode in ('o', 'r', 'm'):
                self._record_routine_write(routine, self.root_name(argument), local_names, parameter_names)
        if ex.variable_write_call(name, node.args):
            routine.global_writes.update(self.types)

    def _collect_direct_effects(self, routine):
        local_names = {token.value for token, _ in routine.declarations}
        parameter_names = {token.value for token, _ in routine.parameters}
        if routine.external:
            routine.parameter_writes.update(parameter_names)
            routine.may_services = True
        calls = []
        for node in self.walk_nodes(routine.body):
            if isinstance(node, Statement):
                self._collect_statement_effects(routine, node, local_names, parameter_names)
            else:
                self._collect_expression_effects(routine, node, local_names, parameter_names)
                if node.kind == 'call' and node.value in self.routines:
                    calls.append(node)
        return calls

    def _uses_kinematic_prefix_conversion(self, routine):
        if self.mode != 'pythonic' or routine.may_services:
            return False
        for node in self.walk_nodes(routine.body):
            if not isinstance(node, Statement) or node.kind != 'assign':
                continue
            target = node.args[0]
            while target.kind == 'group':
                target = target.args[0]
            if not self.is_array_prefix_value(target):
                continue
            expected = self.access_type(target)
            actual = self.access_type(node.args[1])
            if rt.kinematic_array_kind(expected, actual) or rt.kinematic_record_kind(expected, actual):
                return True
        return False

    def _inherit_effect_flags(self, routine, callees):
        changed = False
        for effect in ROUTINE_EFFECT_FLAGS:
            if not getattr(routine, effect) and any(getattr(self.routines[name], effect) for name in callees):
                setattr(routine, effect, True)
                changed = True
        return changed

    def _inherit_write_effects(self, routine, calls):
        changed = False
        parameter_names = {token.value for token, _ in routine.parameters}
        local_names = {token.value for token, _ in routine.declarations}
        for call in calls:
            callee = self.routines[call.value]
            inherited = callee.global_writes - routine.global_writes
            if inherited:
                routine.global_writes.update(inherited)
                changed = True
            for argument, (formal, expected) in zip(call.args, callee.parameters):
                # Grouped and converted arguments use independent temporary storage.
                if formal.value not in callee.parameter_writes or argument.kind not in ('name', 'index', 'field'):
                    continue
                root = self.root_name(argument)
                if not self.argument_is_reference(argument, expected):
                    continue
                if root in parameter_names:
                    if formal.value in callee.timer_parameter_writes and root not in routine.timer_parameter_writes:
                        routine.timer_parameter_writes.add(root)
                        changed = True
                    if root not in routine.parameter_writes:
                        routine.parameter_writes.add(root)
                        changed = True
                if (root in self.types and root not in local_names and root not in parameter_names
                        and root not in routine.global_writes):
                    routine.global_writes.add(root)
                    changed = True
        return changed

    def _propagate_routine_effects(self, edges, calls):
        changed = True
        while changed:
            changed = False
            for routine in self.program.routines:
                self.current_routine = routine
                if self._uses_kinematic_prefix_conversion(routine):
                    routine.may_services = True
                    changed = True
                changed |= self._inherit_effect_flags(routine, edges[routine.name])
                changed |= self._inherit_write_effects(routine, calls[routine.name])

    def has_external_effect_call(self, expr):
        return any(isinstance(node, Expr) and node.kind == 'call' and node.value in self.routines
                   and any(getattr(self.routines[node.value], effect) for effect in ROUTINE_EFFECT_FLAGS)
                   for node in self.walk_nodes(expr))
