"""Normalize source ARRAY accesses, lexical fields, and bare routine calls."""
from . import extended as ex
from .control_flow import counter_text
from .syntax import Expr, Statement, walk_nodes
from .using_analysis import UsingNormalization


BARE_SERVICE_FUNCTIONS = frozenset(('GET_USEC_TIM', 'CURR_PROG', 'CURPOS', 'CURJPOS', 'KCL_STATUS', 'MOTION_CTL'))


class SourceNormalization(UsingNormalization):
    """Rewrite source references at the stages where their schemas are available."""

    walk_nodes = staticmethod(walk_nodes)

    def _flatten_array_chain(self, node, body):
        source = counter_text(node)
        segments = []
        current = node
        end = node.args[-1:] if node.kind == 'motion_range' else []
        while True:
            segments.append(current.args[1:-1] if current.kind == 'motion_range' else current.args[1:])
            base = current.args[0]
            receiver = base
            while receiver.kind == 'group':
                receiver = receiver.args[0]
            if receiver.kind != 'index':
                break
            current = receiver
        if len(segments) == 1:
            return
        segments.reverse()
        node.args = [base, *[item for segment in segments for item in segment], *end]
        self.array_index_chains.append(dict(body=body, line=current.token.line, column=current.token.column,
                                            source_selector=source, normalized_selector=counter_text(node),
                                            segment_lengths=[len(segment) for segment in segments],
                                            subscript_count=sum(map(len, segments))))
        self.features.add('chained ARRAY subscript normalization')

    def normalize_array_chains(self):
        """Join adjacent subscript groups before a partial receiver can be typed."""
        def resolve(node, body):
            if isinstance(node, Expr):
                if node.kind in ('index', 'motion_range'):
                    self._flatten_array_chain(node, body)
                node.args = [resolve(argument, body) for argument in node.args]
            elif isinstance(node, Statement):
                node.args = [resolve(argument, body) for argument in node.args]
                node.body = resolve(node.body, body)
                node.alternate = resolve(node.alternate, body)
            elif isinstance(node, list):
                return [resolve(child, body) for child in node]
            elif isinstance(node, tuple):
                return tuple(resolve(child, body) for child in node)
            return node

        self.program.body = resolve(self.program.body, self.program.name)
        for routine in self.program.routines:
            routine.body = resolve(routine.body, routine.name)

    def resolve_bare_function_name(self, node):
        """Resolve a bare value name, including when typing a USING selector."""
        if node.kind != 'name':
            return node
        name = node.value
        routine = self.routines.get(name)
        if routine is None and (self.mode != 'pythonic' or name not in BARE_SERVICE_FUNCTIONS):
            return node
        local = self.current_routine
        local_names = local.local_types.keys() | local.local_constants.keys() if local else set()
        if routine is not None:
            if name in local_names:
                return node
            if routine.parameters:
                self.error('E_ARGUMENTS', 'A bare routine name requires a function with no parameters; supply the declared arguments', node.token)
            if routine.return_type is None:
                self.error('E_TYPE', 'Procedure cannot be used as an expression', node.token)
            result = routine.return_type
        elif name not in self.types.keys() | self.constants.keys() | local_names:
            result = ('INTEGER',) if name == 'GET_USEC_TIM' else ex.FUNCTIONS[name][1]
        else:
            return node
        self.bare_function_uses.append(dict(body=local.name if local else self.program.name,
                                            name=name, line=node.token.line, column=node.token.column,
                                            result_spec=result))
        self.features.add('bare zero-argument function call')
        return Expr('call', node.token, name, [])

    def resolve_bare_function_calls(self):
        """Resolve value names before call/effect checks while preserving storage roots."""
        def resolve(node, storage=False):
            if isinstance(node, Expr):
                if not storage:
                    node = self.resolve_bare_function_name(node)
                if node.kind in ('index', 'field', 'read_item'):
                    node.args = [resolve(node.args[0], storage=True),
                                 *[resolve(argument) for argument in node.args[1:]]]
                else:
                    node.args = [resolve(argument) for argument in node.args]
            elif isinstance(node, Statement):
                if node.kind == 'assign':
                    node.args = [resolve(node.args[0], storage=True), resolve(node.args[1])]
                elif node.kind in ('using', 'read'):
                    node.args = [resolve(argument, storage=True) for argument in node.args]
                else:
                    node.args = [resolve(argument) for argument in node.args]
                node.body = resolve(node.body)
                node.alternate = resolve(node.alternate)
            elif isinstance(node, list):
                return [resolve(child) for child in node]
            elif isinstance(node, tuple):
                return tuple(resolve(child) for child in node)
            return node

        self.program.body = resolve(self.program.body)
        for routine in self.program.routines:
            self.current_routine = routine
            routine.body = resolve(routine.body)
        self.current_routine = None

    def normalize_wait_captures(self, bodies):
        """Bind the WAIT EVAL clause after resolving ordinary routine names."""
        if 'EVAL' in self.routines:
            return
        for body in bodies:
            for stmt in self.walk_nodes(body):
                if not isinstance(stmt, Statement) or stmt.kind != 'wait':
                    continue
                for node in self.walk_nodes(stmt.args[0]):
                    if isinstance(node, Expr) and node.kind == 'call' and node.value == 'EVAL':
                        if len(node.args) != 1:
                            self.error('E_ARGUMENTS', 'EVAL requires one captured expression', node.token)
                        node.kind = 'wait_eval'

    def normalize_body_references(self):
        self.resolve_using_fields()
        self.resolve_bare_function_calls()
        if self.mode == 'pythonic':
            bodies = (self.program.body, *(routine.body for routine in self.program.routines))
            self.normalize_wait_captures(bodies)
            if any(isinstance(node, Expr) and node.kind == 'call' and node.value in ex.COOPERATIVE_PROCEDURES
                   for body in bodies for node in self.walk_nodes(body)):
                self.cooperative = True
