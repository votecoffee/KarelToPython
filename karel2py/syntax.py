"""Source AST nodes and the public translation result."""
from .lexer import Token
from dataclasses import dataclass, field


@dataclass
class Expr:
    kind: str
    token: Token
    value: object = None
    args: list = field(default_factory=list)
    relative_in_write: bool = False


@dataclass
class Statement:
    kind: str
    token: Token
    args: list = field(default_factory=list)
    body: list = field(default_factory=list)
    alternate: list = field(default_factory=list)
    has_else: bool = False


def walk_nodes(node):
    """Visit source expressions and statements in argument and body order."""
    if isinstance(node, (Expr, Statement)):
        yield node
        for argument in node.args:
            yield from walk_nodes(argument)
        if isinstance(node, Statement):
            yield from walk_nodes(node.body)
            yield from walk_nodes(node.alternate)
    elif isinstance(node, (list, tuple)):
        for child in node:
            yield from walk_nodes(child)


@dataclass
class Routine:
    name: str
    token: Token
    return_type: tuple | None
    body: list
    declarations: list = field(default_factory=list)
    local_types: dict = field(default_factory=dict)
    parameters: list = field(default_factory=list)
    side_effecting: bool = False
    local_declarations: list = field(default_factory=list)
    local_constants: dict = field(default_factory=dict)
    may_delay: bool = False
    parameter_writes: set = field(default_factory=set)
    timer_parameter_writes: set = field(default_factory=set)
    global_writes: set = field(default_factory=set)
    may_write: bool = False
    may_read: bool = False
    may_abort: bool = False
    may_clock: bool = False
    may_read_registers: bool = False
    may_write_registers: bool = False
    may_services: bool = False
    external: str | None = None
    string_result_defaulted: bool = False


@dataclass
class Program:
    name: str
    constants: list
    declarations: list
    routines: list
    body: list
    directives: list
    user_types: list = field(default_factory=list)
    directive_metadata: list = field(default_factory=list)
    imported_variables: list = field(default_factory=list)
    imported_types: list = field(default_factory=list)
    storage_declarations: list = field(default_factory=list)


@dataclass
class Translation:
    python_source: str
    report: dict
