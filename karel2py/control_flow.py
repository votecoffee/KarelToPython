"""Validate body-local jumps and lower structured control flow into dispatch nodes."""
from dataclasses import dataclass, field

from .syntax import Expr, Statement


@dataclass
class FlowNode:
    kind: str
    statement: Statement
    targets: list = field(default_factory=list)
    for_scopes: tuple = ()


def counter_text(value):
    """Describe source storage without evaluating a captured counter selector."""
    if not isinstance(value,Expr):return value.value
    if value.kind=='system_selection':
        return ('$MNUFRAMENUM' if value.value=='FRAME' else '$MNUTOOLNUM')+'['+counter_text(value.args[0])+']'
    if value.kind=='system_pose':
        parts=','.join(counter_text(item) for item in value.args)
        if value.value in ('FRAME','TOOL'):
            return ('$MNUFRAME' if value.value=='FRAME' else '$MNUTOOL')+'['+parts+']'
        return '$GROUP['+parts+'].'+('$UFRAME' if value.value=='ACTIVE_FRAME' else '$UTOOL')
    if value.kind=='using_ref':return value.value[4]
    if value.kind=='field':return counter_text(value.args[0])+'.'+value.value
    if value.kind in ('index','motion_range'):
        indexes=[counter_text(item) for item in value.args[1:]]
        if value.kind=='motion_range':indexes[-2:]=['..'.join(indexes[-2:])]
        return counter_text(value.args[0])+'['+','.join(indexes)+']'
    if value.kind=='group':return '('+counter_text(value.args[0])+')'
    if value.kind=='call':return value.value+'('+','.join(counter_text(item) for item in value.args)+')'
    if value.kind=='binary':return '('+counter_text(value.args[0])+value.value+counter_text(value.args[1])+')'
    if value.kind=='unary':return value.value+'('+counter_text(value.args[0])+')'
    return str(value.value)


class FlowGraph:
    """Lower branches and explicit Pythonic FOR lifetime scopes to dispatch nodes."""
    def __init__(self, statements, *, lower_for=False):
        self.nodes, self.labels = [], {}
        self.lower_for=lower_for;self.for_scopes={}
        self.entry = self.sequence(statements, None)
        for node in self.nodes:
            if node.kind == 'goto': node.targets = [self.labels[node.statement.args[0].value]]

    def add(self, kind, statement, targets, for_scopes=()):
        index = len(self.nodes)
        self.nodes.append(FlowNode(kind, statement, targets, for_scopes))
        return index

    def sequence(self, statements, continuation, for_scopes=()):
        entry = continuation
        for stmt in reversed(statements):
            kind = stmt.kind
            if kind == 'label':
                entry = self.add('label', stmt, [entry], for_scopes)
                self.labels[stmt.args[0].value] = entry
            elif kind == 'goto': entry = self.add('goto', stmt, [], for_scopes)
            elif kind in ('abort', 'return'): entry = self.add(kind, stmt, [], for_scopes)
            elif kind == 'if':
                then = self.sequence(stmt.body, entry, for_scopes)
                otherwise = self.sequence(stmt.alternate, entry, for_scopes)
                entry = self.add('if', stmt, [then, otherwise], for_scopes)
            elif kind in ('while', 'repeat'):
                condition = self.add(kind + '_test', stmt, [], for_scopes)
                body = self.sequence(stmt.body, condition, for_scopes)
                self.nodes[condition].targets = [body, entry] if kind == 'while' else [entry, body]
                entry = self.add('enter', stmt, [condition if kind == 'while' else body], for_scopes)
            elif kind == 'for' and self.lower_for:
                scope=self.add('for_enter',stmt,[],for_scopes)
                self.for_scopes[scope]=stmt
                active=(*for_scopes,scope)
                finish=self.add('for_exit',stmt,[entry],active)
                advance=self.add('for_next',stmt,[],active)
                body=self.sequence(stmt.body,advance,active)
                self.nodes[advance].targets=[body,finish]
                self.nodes[scope].targets=[advance]
                entry=scope
            elif kind == 'select':
                cases = [self.sequence(body, entry, for_scopes) for _, _, body in stmt.args[1]]
                otherwise = self.sequence(stmt.alternate, entry, for_scopes) if stmt.has_else else None
                entry = self.add('select', stmt, cases + [otherwise], for_scopes)
            elif kind == 'using':
                body = self.sequence(stmt.body, entry, for_scopes)
                entry = self.add('enter', stmt, [body], for_scopes)
            else: entry = self.add('statement', stmt, [entry], for_scopes)
        return entry

    def report(self):
        report=dict(engine='label_dispatcher', python_dispatch='match', entry_node=self.entry, labels=self.labels,
                    nodes=[dict(id=i, kind=node.kind, statement_kind=node.statement.kind, karel_line=node.statement.token.line,
                                karel_column=node.statement.token.column, successors=node.targets)
                           for i, node in enumerate(self.nodes)])
        if self.for_scopes:
            report['for_scopes']=[dict(id=scope,counter=counter_text(stmt.args[0]),line=stmt.token.line,column=stmt.token.column,
                parents=list(self.nodes[scope].for_scopes)) for scope,stmt in self.for_scopes.items()]
            for node,metadata in zip(self.nodes,report['nodes']):metadata['for_scopes']=list(node.for_scopes)
        return report


def child_blocks(stmt):
    location = f'{stmt.kind}@{stmt.token.line}:{stmt.token.column}'
    if stmt.kind == 'if':
        yield location + '/then', stmt.body
        yield location + '/else', stmt.alternate
    elif stmt.kind in ('while', 'repeat', 'for', 'using'):
        yield location + '/body', stmt.body
    elif stmt.kind == 'select':
        for index, (_, _, body) in enumerate(stmt.args[1]):
            yield location + f'/case:{index}', body
        yield location + '/else', stmt.alternate


def validate_labels(statements, *, conflicts, mode, error):
    """Check label visibility and scope entry before building a dispatch graph."""
    labels, jumps = {}, []

    def visit(body, path=(), inside_for=False):
        for stmt in body:
            if stmt.kind in ('label', 'goto'):
                if inside_for and mode!='pythonic':
                    error('E_GOTO_FOR', 'Labels and GO TO/GOTO inside FOR bodies are blocked by the documented FOR restrictions', stmt.token)
                name = stmt.args[0].value
                if stmt.kind == 'label':
                    if name in labels: error('E_DUPLICATE_LABEL', 'Duplicate label in the same body', stmt.token)
                    if name in conflicts: error('E_LABEL_CONFLICT', 'Label conflicts with a declared or predefined identifier', stmt.token)
                    labels[name] = (stmt.token, path)
                else: jumps.append((stmt, path))
            for block_name, child in child_blocks(stmt):
                visit(child, path + (block_name,), inside_for or stmt.kind == 'for')

    visit(statements)
    transfers=[]
    for stmt, source_path in jumps:
        name = stmt.args[0].value
        if name not in labels:
            error('E_LABEL', f'Label {name} is not defined in this program/routine body', stmt.args[0])
        target_token,target_path = labels[name]
        if mode=='pythonic':
            source_for=tuple(scope for scope in source_path if scope.startswith('for@'))
            target_for=tuple(scope for scope in target_path if scope.startswith('for@'))
            if source_for[:len(target_for)]!=target_for:
                error('E_GOTO_FOR','Jump would bypass FOR initialization and captured iteration bounds',stmt.token)
            # Every path to a USING body must pass its capture node. Retain
            # that invariant even when state-free structured entry is allowed.
            source_using=tuple(scope for scope in source_path if scope.startswith('using@'))
            target_using=tuple(scope for scope in target_path if scope.startswith('using@'))
            if source_using[:len(target_using)]!=target_using:
                error('E_GOTO_ENTRY','Jump would bypass a USING reference capture',stmt.token)
            common=0
            while common<min(len(source_path),len(target_path)) and source_path[common]==target_path[common]:common+=1
            if any(scope.split('@',1)[0] not in ('if','while','repeat','select') for scope in target_path[common:]):
                error('E_GOTO_ENTRY','Jump enters a block without a supported entry contract',stmt.token)
        elif source_path[:len(target_path)] != target_path:
            error('E_GOTO_ENTRY', 'Jumps into nested or sibling structured blocks need entry-state validation', stmt.token)
        entry=('same_block' if source_path==target_path else 'ancestor' if source_path[:len(target_path)]==target_path
            else 'nested' if target_path[:len(source_path)]==source_path else 'sibling')
        transfer=dict(label=name,source=dict(line=stmt.token.line,column=stmt.token.column,blocks=list(source_path)),
            target=dict(line=target_token.line,column=target_token.column,blocks=list(target_path)),entry_kind=entry)
        if mode=='pythonic':
            transfer['retained_for_scopes']=list(target_for)
            transfer['exited_for_scopes']=list(reversed(source_for[len(target_for):]))
        transfers.append(transfer)
    return bool(labels or jumps),transfers
