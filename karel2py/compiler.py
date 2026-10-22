"""Parse KAREL into an AST, check types, then emit Python.

There is no textual substitution or source eval. Unsupported forms stop conversion.
"""
from dataclasses import dataclass, field
import ast
import hashlib
import json
import re

from .lexer import Token, TranslationError, tokenize, directive_content
from . import runtime as rt
from . import extended as ex
from .inspection import TYPE_CODES as VARIABLE_TYPE_CODES
from . import __version__


@dataclass
class Expr:
    kind: str
    token: Token
    value: object = None
    args: list = field(default_factory=list)


@dataclass
class Statement:
    kind: str
    token: Token
    args: list = field(default_factory=list)
    body: list = field(default_factory=list)
    alternate: list = field(default_factory=list)
    has_else: bool = False


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


@dataclass
class Translation:
    python_source: str
    report: dict


@dataclass
class FlowNode:
    kind: str
    statement: Statement
    targets: list = field(default_factory=list)


class FlowGraph:
    """Lower a body to branches while leaving FOR loops as checked atomic blocks."""
    def __init__(self, statements):
        self.nodes, self.labels = [], {}
        self.entry = self.sequence(statements, None)
        for node in self.nodes:
            if node.kind == 'goto': node.targets = [self.labels[node.statement.args[0].value]]

    def add(self, kind, statement, targets):
        index = len(self.nodes)
        self.nodes.append(FlowNode(kind, statement, targets))
        return index

    def sequence(self, statements, continuation):
        entry = continuation
        for stmt in reversed(statements):
            kind = stmt.kind
            if kind == 'label':
                entry = self.add('label', stmt, [entry])
                self.labels[stmt.args[0].value] = entry
            elif kind == 'goto': entry = self.add('goto', stmt, [])
            elif kind == 'abort': entry = self.add('abort', stmt, [])
            elif kind == 'if':
                then = self.sequence(stmt.body, entry)
                otherwise = self.sequence(stmt.alternate, entry)
                entry = self.add('if', stmt, [then, otherwise])
            elif kind in ('while', 'repeat'):
                condition = self.add(kind + '_test', stmt, [])
                body = self.sequence(stmt.body, condition)
                self.nodes[condition].targets = [body, entry] if kind == 'while' else [entry, body]
                entry = self.add('enter', stmt, [condition if kind == 'while' else body])
            elif kind == 'select':
                cases = [self.sequence(body, entry) for _, _, body in stmt.args[1]]
                otherwise = self.sequence(stmt.alternate, entry) if stmt.has_else else None
                entry = self.add('select', stmt, cases + [otherwise])
            elif kind == 'using':
                body = self.sequence(stmt.body, entry)
                entry = self.add('enter', stmt, [body])
            else: entry = self.add('statement', stmt, [entry])
        return entry

    def report(self):
        return dict(engine='label_dispatcher', python_dispatch='match', entry_node=self.entry, labels=self.labels,
                    nodes=[dict(id=i, kind=node.kind, statement_kind=node.statement.kind, karel_line=node.statement.token.line,
                                karel_column=node.statement.token.column, successors=node.targets)
                           for i, node in enumerate(self.nodes)])


PRECEDENCE = {'=': 10, '<>': 10, '<': 10, '<=': 10, '>': 10, '>=': 10,
              '> = <': 10, '>=<': 10, '+': 20, '-': 20, 'OR': 20,
              '*': 30, '/': 30, 'AND': 30, 'DIV': 30, 'MOD': 30, '@': 40, '#': 40, ':': 40}
PREDEFINED_CONSTANTS = {'ON': True, 'OFF': False, 'MAXINT': 2147483647, 'MININT': -2147483648,
                        'ATR_IA':1,'ATR_UF':2,'ATR_REVERSE':3,'ATR_FIELD':4,'ATR_EOL':5,
                        **{name:row[0] for name,row in rt.ERROR_SEVERITIES.items()},**rt.TASK_CONSTANTS}
BLOCK_ENDS = {'ELSE', 'ENDIF', 'ENDWHILE', 'ENDFOR', 'UNTIL', 'CASE', 'ENDSELECT', 'ENDUSING', 'END'}
RESERVED = BLOCK_ENDS | {
    'CONNECT','DISCONNECT','TIMER','WHEN','ENDCONDITION','PURGE','EVENT','WITH',
    'SEMAPHORE','POWERUP','ERROR','NOABORT','NOPAUSE','NOMESSAGE',
    'PROGRAM', 'CONST', 'VAR', 'TYPE', 'BEGIN', 'IF', 'THEN', 'SELECT', 'OF',
    'FOR', 'TO', 'DOWNTO', 'DO', 'WHILE', 'REPEAT', 'RETURN', 'ROUTINE',
    'INTEGER', 'BOOLEAN', 'STRING', 'REAL', 'ARRAY', 'STRUCTURE', 'ENDSTRUCTURE', 'TRUE', 'FALSE',
    'USING', 'ENDUSING',
    'AND', 'OR', 'NOT', 'DIV', 'MOD', 'FROM', 'IN', 'BYTE', 'SHORT',
    'ABORT', 'STOP', 'PAUSE', 'RESUME', 'HOLD', 'UNHOLD', 'UNPAUSE', 'GO',
    'GOTO', 'MOVE', 'CONDITION', 'ENABLE', 'DISABLE', 'DELAY', 'WAIT',
    'OPEN', 'CLOSE', 'READ', 'WRITE', 'CR', 'PULSE', 'SIGNAL', 'CANCEL', 'CONTINUE',
    'FILE', 'PATH', 'VISION', 'VECTOR', 'POSITION', 'XYZWPR', 'XYZWPREXT',
    'CONFIG', 'CAM_SETUP', 'MODEL', 'QUEUE_TYPE', 'JOINTPOS',
    'JOINTPOS1', 'JOINTPOS2', 'JOINTPOS3', 'JOINTPOS4', 'JOINTPOS5',
    'JOINTPOS6', 'JOINTPOS7', 'JOINTPOS8', 'JOINTPOS9',
}
BUILTIN_SIGNATURES = {
    'ABS': (('INTEGER',), ('INTEGER',)),
    'STR_LEN': (('STRING',), ('INTEGER',)),
    'ARRAY_LEN': (('ARRAY',), ('INTEGER',)),
    'SUB_STR': (('STRING', 'INTEGER', 'INTEGER'), ('STRING', None)),
    'INDEX': (('STRING', 'STRING'), ('INTEGER',)),
    'CHR': (('INTEGER',), ('STRING', 1)),
    'ORD': (('STRING', 'INTEGER'), ('INTEGER',)),
    'ROUND': (('REAL',), ('INTEGER',)),
    'TRUNC': (('REAL',), ('INTEGER',)),
    'SQRT': (('REAL',), ('REAL',)),
    'EXP': (('REAL',), ('REAL',)),
    'LN': (('REAL',), ('REAL',)),
    **{name: (('REAL',), ('REAL',)) for name in rt.UNARY_TRIG_FUNCTIONS},
    'ATAN2': (('REAL', 'REAL'), ('REAL',)),
    'VEC': (('REAL', 'REAL', 'REAL'), ('VECTOR',)),
    'POS': (('REAL', 'REAL', 'REAL', 'REAL', 'REAL', 'REAL', 'CONFIG'), ('XYZWPR',)),
    'INV': (('XYZWPR',), ('XYZWPR',)),
    'FRAME': (('XYZWPR', 'XYZWPR', 'XYZWPR'), ('XYZWPR',)),
    'APPROACH': (('POSITION',), ('VECTOR',)),
    'ORIENT': (('POSITION',), ('VECTOR',)),
}
BUILTIN_PROCEDURES = {'CNV_STR_INT': ('STRING',), 'CNV_INT_STR': ('INTEGER', 'INTEGER', 'INTEGER'),
                      'CNV_STR_REAL': ('STRING',), 'CNV_REAL_STR': ('REAL', 'INTEGER', 'INTEGER')}
CONVERSION_OUTPUT_TYPES = {'CNV_STR_INT': 'INTEGER', 'CNV_INT_STR': 'STRING', 'CNV_STR_REAL': 'REAL',
                           'CNV_REAL_STR': 'STRING'}
JOINT_PROCEDURES = {'CNV_REL_JPOS', 'CNV_JPOS_REL'}
CONFIG_TEXT_PROCEDURES = {'CNV_CONF_STR', 'CNV_STR_CONF'}
TIME_TEXT_PROCEDURES = {'CNV_STR_TIME', 'CNV_TIME_STR'}
TIMER_FUNCTIONS = {'GET_USEC_TIM', 'GET_USEC_SUB'}
REGISTER_PROCEDURES = {'GET_REG','SET_INT_REG','SET_REAL_REG'}
MULTI_OUTPUT_PROCEDURES = JOINT_PROCEDURES | {'UNPOS'}
# Constructors, frame helpers and pose queries are Pythonic fallbacks. Preserve internal routines and
# ordinary declarations with these names.
PYTHONIC_CONSTRUCTORS = {'VEC', 'POS', 'INV', 'FRAME', *rt.POSITION_AXIS_FUNCTIONS}
BUILTINS = (set(BUILTIN_SIGNATURES) - PYTHONIC_CONSTRUCTORS) | set(BUILTIN_PROCEDURES) | MULTI_OUTPUT_PROCEDURES | {'UNINIT'}
CONTROLLER_NAMES = {'DIN', 'DOUT', 'GIN', 'GOUT', 'AIN', 'AOUT', 'RDIN', 'RDOUT',
                    'GET_REG', 'SET_INT_REG', 'SET_REAL_REG',
                    'GET_POS_REG', 'SET_POS_REG', 'GET_VAR', 'SET_VAR'}
NARROW_TYPES = ('BYTE', 'SHORT')
INTEGRAL_TYPES = ('INTEGER', *NARROW_TYPES)
ARRAY_SCALARS = (*INTEGRAL_TYPES, 'BOOLEAN', 'REAL', 'STRING')
DATA_RECORD_TYPES = rt.DATA_RECORD_TYPES
POSITIONAL_VALUE_TYPES = rt.POSITIONAL_VALUE_TYPES
RECORD_TYPES = rt.RECORD_TYPES
ARRAY_ELEMENTS = (*ARRAY_SCALARS, *RECORD_TYPES, 'JOINTPOS')


def blocked_controller_names(mode):
    return CONTROLLER_NAMES - REGISTER_PROCEDURES - ex.PROCEDURES.keys() - ex.FUNCTIONS.keys() - ex.PORT_TYPES.keys() if mode == 'pythonic' else CONTROLLER_NAMES


class Parser:
    def __init__(self, source, filename, mode='strict'):
        self.continuations = []
        self.escaped_string_literals = []
        self.predefined_uses = []
        self.directive_metadata = []
        self.tokens = tokenize(source, filename, continuations=self.continuations)
        self.position = 0
        self.filename = filename
        self.mode = mode
        self.in_condition=False
        self.in_handler_actions=False

    @property
    def current(self): return self.tokens[self.position]

    def error(self, code, message, token=None):
        raise TranslationError(code, message, token or self.current, self.filename)

    def take(self):
        token = self.current
        if token.kind != 'EOF': self.position += 1
        return token

    def skip_lines(self):
        while self.current.kind == 'NL' or self.current.value == ';': self.take()

    def skip_newlines(self):
        while self.current.kind == 'NL': self.take()

    def accept(self, value):
        if self.current.value == value: return self.take()
        return None

    def expect(self, value):
        if self.current.value != value:
            self.error('E_SYNTAX', f'Expected {value}, found {self.current.value}')
        return self.take()

    def name(self):
        if self.current.value in PREDEFINED_CONSTANTS:
            self.error('E_PREDEFINED_NAME', 'Redefining predefined constants is blocked pending namespace evidence')
        if self.current.kind != 'NAME' or self.current.value in RESERVED | BUILTINS or self.current.value.startswith('$'):
            self.error('E_NAME', 'Expected a non-reserved identifier')
        return self.take()

    def metadata_directive(self, token, declarations_started):
        content, _ = directive_content(token.value)
        head = re.match(r'%[A-Za-z][A-Za-z_0-9]*', content)
        name = head[0].upper() if head else ''
        argument = None
        disposition = 'Offline metadata only; no task/group ownership'
        if content.upper() == '%NOLOCKGROUP': name = '%NOLOCKGROUP'
        elif self.mode != 'pythonic' or name not in ('%ENVIRONMENT', '%COMMENT', '%ALPHABETIZE'):
            self.error('E_DIRECTIVE', 'Directive has no implemented runtime mapping', token)
        elif name == '%ENVIRONMENT':
            match = re.fullmatch(r'%ENVIRONMENT\s+([A-Za-z][A-Za-z_0-9]{0,35})', content, re.I)
            if not match: self.error('E_DIRECTIVE_SYNTAX', 'ENVIRONMENT requires one bare ASCII name of 1..36 characters; no paths or file loading', token)
            argument = match[1].upper()
            disposition = 'Recorded environment requirement only; no definitions, files, modules or controller facilities loaded'
        elif name == '%COMMENT':
            if declarations_started: self.error('E_DIRECTIVE_POSITION', 'COMMENT must precede CONST/TYPE/VAR sections and routines', token)
            if any(row['name'] == name for row in self.directive_metadata):
                self.error('E_DIRECTIVE_DUPLICATE', 'Multiple COMMENT attributes require a precedence policy', token)
            match = re.fullmatch(r"%COMMENT\s*=\s*'((?:[^']|'')*)'", content, re.I)
            if not match: self.error('E_DIRECTIVE_SYNTAX', 'COMMENT requires one single-quoted literal after =', token)
            argument = match[1].replace("''", "'")
            if not argument.isascii() or len(argument) > 16:
                self.error('E_DIRECTIVE_VALUE', 'COMMENT requires at most 16 decoded ASCII characters', token)
            disposition = 'Recorded program comment only; no controller attribute write'
        elif content.upper() != '%ALPHABETIZE':
            self.error('E_DIRECTIVE_SYNTAX', 'ALPHABETIZE accepts no arguments', token)
        else:
            disposition = 'Recorded display-order request; offline storage and snapshots retain declaration order'
        self.directive_metadata.append(dict(name=name, argument=argument, line=token.line,
                                            column=token.column, disposition=disposition))

    def parse(self):
        self.skip_lines()
        self.expect('PROGRAM')
        name = self.name().value
        constants, declarations, routines, directives, user_types, imports = [], [], [], [], [], []
        declarations_started = False
        while True:
            self.skip_lines()
            token = self.current
            if token.kind == 'DIRECTIVE':
                self.metadata_directive(token, declarations_started)
                directives.append(self.take())
            elif self.accept('CONST'):
                declarations_started = True
                self.skip_lines()
                while self.current.kind == 'NAME' and self.current.value not in RESERVED:
                    key = self.name()
                    self.expect('=')
                    constants.append((key, self.expression()))
                    self.skip_lines()
            elif self.accept('TYPE'):
                declarations_started = True
                self.skip_lines()
                while self.current.kind == 'NAME' and self.current.value not in RESERVED:
                    key = self.name()
                    self.expect('=')
                    if self.current.value == 'ARRAY' or (self.mode == 'pythonic' and self.current.value != 'STRUCTURE'):
                        user_types.append((key, self.type_spec()))
                        self.skip_lines()
                        continue
                    if not self.accept('STRUCTURE'):
                        self.error('E_TYPE_ALIAS', 'Only named STRUCTURE and fixed ARRAY definitions are implemented; scalar aliases and type-to-type aliases remain blocked')
                    fields = []
                    self.skip_lines()
                    while self.current.value != 'ENDSTRUCTURE':
                        field_token = self.name()
                        self.expect(':')
                        fields.append((field_token, self.type_spec()))
                        self.skip_lines()
                    self.expect('ENDSTRUCTURE')
                    if not fields: self.error('E_STRUCTURE', 'A STRUCTURE requires at least one field', key)
                    user_types.append((key, fields))
                    self.skip_lines()
            elif self.accept('VAR'):
                declarations_started = True
                self.skip_lines()
                while self.current.kind == 'NAME' and self.current.value not in RESERVED:
                    names = [self.name()]
                    while self.accept(','): names.append(self.name())
                    owner=None
                    if self.mode=='pythonic' and self.accept('FROM'): owner=self.name().value
                    self.expect(':')
                    spec = self.type_spec()
                    declarations.extend((key, spec) for key in names)
                    if owner: imports.extend((key.value,owner,key.value) for key in names)
                    self.skip_lines()
            elif self.current.value == 'ROUTINE':
                declarations_started = True
                routines.append(self.routine())
            elif self.accept('BEGIN'):
                body = self.block({'END'})
                self.expect('END')
                self.expect(name)
                self.skip_lines()
                self.expect('<EOF>')
                return Program(name, constants, declarations, routines, body, directives, user_types, self.directive_metadata,imports)
            else:
                self.error('E_DECLARATION', 'Expected CONST, TYPE, VAR, ROUTINE or BEGIN; external declarations and controller types are not implemented')

    def type_spec(self):
        token = self.take()
        if self.mode=='pythonic' and token.value in ('FILE','QUEUE_TYPE'): return (token.value,)
        if self.mode=='pythonic' and token.value=='PATH':
            node=data=None
            seen=set()
            while self.current.value in ('NODEDATA','PATHHEADER'):
                key=self.take()
                if key.value in seen: self.error('E_TYPE','Duplicate PATH clause',key)
                seen.add(key.value); self.expect('='); item=self.type_spec()
                if key.value=='NODEDATA': node=item
                else: data=item
                if not self.accept(','): break
                self.skip_lines()
            return ('PATH',node,data,token)
        if token.value in PREDEFINED_CONSTANTS:
            self.error('E_TYPE', 'Predefined constants cannot be used as data types', token)
        if token.value in ('INTEGER', 'BOOLEAN', 'REAL', 'BYTE', 'SHORT'): return (token.value,)
        if token.value in rt.JOINT_TYPE_NAMES:
            return self.group_spec(rt.joint_spec(token.value),token)
        if token.value in DATA_RECORD_TYPES:
            return self.group_spec((token.value,),token)
        if token.value == 'STRING':
            self.expect('[')
            size = self.expression()
            self.expect(']')
            return ('STRING', size)
        if token.value == 'ARRAY':
            self.expect('[')
            sizes = [Expr('array_wildcard', self.take()) if self.current.value == '*' else self.expression()]
            while self.accept(','):
                sizes.append(Expr('array_wildcard', self.take()) if self.current.value == '*' else self.expression())
            self.expect(']')
            if len(sizes) > 3:
                self.error('E_ARRAY_RANK', 'Arrays support at most three dimensions', token)
            self.expect('OF')
            element = self.type_spec()
            if element[0] == 'ARRAY':
                self.error('E_TYPE', 'Nested ARRAY type syntax needs named-array type rules; use comma-separated dimensions', token)
            return ('ARRAY', sizes[0] if len(sizes) == 1 else tuple(sizes), element)
        if token.kind == 'NAME' and token.value not in RESERVED:
            return ('NAMED', token)
        self.error('E_TYPE', f'{token.value} data type is not implemented', token)

    def group_spec(self,spec,token):
        if self.current.value!='IN': return spec
        if self.mode!='pythonic': self.error('E_POSITION_GROUP','Group-qualified data requires Pythonic context',token)
        self.take(); self.expect('GROUP'); self.expect('['); group=self.expression(); self.expect(']')
        return ('GROUPED',spec,group,token)

    def routine(self):
        token = self.expect('ROUTINE')
        name = self.name().value
        parameters = []
        if self.accept('('):
            self.skip_newlines()
            if not self.accept(')'):
                while True:
                    names = [self.name()]
                    while self.accept(','): names.append(self.name())
                    self.expect(':')
                    spec = self.parameter_type()
                    parameters.extend((key, spec) for key in names)
                    self.skip_newlines()
                    if self.accept(')'): break
                    self.expect(';')
                    self.skip_newlines()
        return_type = None
        string_result_defaulted = False
        if self.accept(':'):
            if self.current.value == 'ARRAY':
                array_token = self.take()
                dimensions = None
                if self.current.value == '[':
                    if self.mode == 'strict':
                        self.error('E_RETURN_TYPE', 'ARRAY function results must omit sizes; multidimensional result declarations remain blocked', array_token)
                    self.take()
                    sizes = [Expr('array_wildcard', self.take()) if self.current.value == '*' else self.expression()]
                    while self.accept(','):
                        sizes.append(Expr('array_wildcard', self.take()) if self.current.value == '*' else self.expression())
                    self.expect(']')
                    if len(sizes) > 3:
                        self.error('E_ARRAY_RANK', 'ARRAY results support at most three dimensions', array_token)
                    dimensions = sizes[0] if len(sizes) == 1 else tuple(sizes)
                self.expect('OF')
                element = self.take()
                if element.value in ('INTEGER', 'BOOLEAN', 'REAL', 'BYTE', 'SHORT', *DATA_RECORD_TYPES):
                    element_spec = (element.value,)
                elif element.value == 'STRING':
                    if not self.accept('['):
                        self.error('E_RETURN_TYPE', 'STRING ARRAY results require an explicit element capacity in brackets', element)
                    element_spec = ('STRING', self.expression())
                    self.expect(']')
                elif element.value in rt.JOINT_TYPE_NAMES:
                    element_spec = rt.joint_spec(element.value)
                elif element.kind == 'NAME' and element.value not in RESERVED | BUILTINS:
                    element_spec = ('NAMED', element)
                else:
                    self.error('E_RETURN_TYPE', 'ARRAY results require supported scalars, bounded STRINGs, data records, joints or prior named aggregate elements', element)
                if self.current.value == 'IN':
                    element_spec=self.group_spec(element_spec,element)
                return_type = ('ARRAY', dimensions, element_spec)
            elif self.mode == 'pythonic' and self.current.value == 'STRING':
                string_token = self.take()
                if self.accept('['):
                    capacity = self.expression()
                    self.expect(']')
                else:
                    capacity = Expr('literal', string_token, 254)
                    string_result_defaulted = True
                return_type = ('STRING', capacity)
            else: return_type = self.type_spec()
        allowed_results = ('INTEGER', 'BOOLEAN', 'REAL', *DATA_RECORD_TYPES, 'JOINTPOS', 'NAMED', 'ARRAY')
        if self.mode == 'pythonic': allowed_results += ('STRING','GROUPED')
        if return_type and return_type[0] not in allowed_results:
            self.error('E_RETURN_TYPE', 'Routine results require a supported scalar, exact data record/joint type or named STRUCTURE', token)
        self.skip_lines()
        if self.mode=='pythonic' and self.accept('FROM'):
            owner=self.take()
            if owner.kind not in ('STRING','NAME'): self.error('E_ROUTINE_EXTERNAL','FROM requires a program name',owner)
            external=owner.value[1:-1].replace("''", "'") if owner.kind=='STRING' else owner.value
            return Routine(name,token,return_type,[],parameters=parameters,string_result_defaulted=string_result_defaulted,external=external)
        declarations, local_declarations = [], []
        while self.current.value in ('CONST', 'VAR'):
            section = self.take().value
            self.skip_lines()
            while self.current.kind == 'NAME' and self.current.value not in RESERVED:
                if section == 'CONST':
                    key = self.name()
                    self.expect('=')
                    local_declarations.append(('CONST', key, self.expression()))
                    self.skip_lines()
                    continue
                names = [self.name()]
                while self.accept(','): names.append(self.name())
                self.expect(':')
                spec = self.type_spec()
                declarations.extend((key, spec) for key in names)
                local_declarations.extend(('VAR', key, spec) for key in names)
                self.skip_lines()
        if self.current.value == 'TYPE':
            self.error('E_ROUTINE_LOCALS', 'Routine-local TYPE sections are prohibited by KAREL')
        self.expect('BEGIN')
        body = self.block({'END'})
        self.expect('END')
        self.expect(name)
        return Routine(name, token, return_type, body, declarations, parameters=parameters,
                       local_declarations=local_declarations, string_result_defaulted=string_result_defaulted)

    def parameter_type(self):
        if self.mode=='pythonic' and self.current.value in ('FILE','PATH','QUEUE_TYPE'): return self.type_spec()
        token = self.take()
        if token.value in PREDEFINED_CONSTANTS:
            self.error('E_PARAMETERS', 'Predefined constants cannot be used as parameter types', token)
        if token.value in ('INTEGER', 'BOOLEAN', 'REAL'): return (token.value,)
        if token.value in rt.JOINT_TYPE_NAMES:
            return self.group_spec(rt.joint_spec(token.value),token)
        if token.value in DATA_RECORD_TYPES:
            return self.group_spec((token.value,),token)
        if token.value == 'STRING':
            if self.current.value == '[':
                self.error('E_PARAMETERS', 'STRING formal parameters have no declared capacity', token)
            return ('STRING', None)
        if token.value == 'ARRAY':
            rank = 1
            if self.current.value == '[':
                self.take()
                if not self.accept('*'):
                    self.error('E_PARAMETERS', 'ARRAY formal dimensions must use * rather than fixed lengths', token)
                while self.accept(','):
                    if not self.accept('*'):
                        self.error('E_PARAMETERS', 'ARRAY formal dimensions must use * rather than fixed lengths', token)
                    rank += 1
                self.expect(']')
                if rank > 3:
                    self.error('E_ARRAY_RANK', 'ARRAY formals support at most three dimensions', token)
            shape = None if rank == 1 else (None,) * rank
            self.expect('OF')
            element = self.take()
            if element.value in rt.JOINT_TYPE_NAMES:
                return ('ARRAY', shape, self.group_spec(rt.joint_spec(element.value),element))
            if element.value not in (*ARRAY_SCALARS, *DATA_RECORD_TYPES):
                if element.kind == 'NAME' and element.value not in RESERVED | BUILTINS:
                    return ('ARRAY', shape, ('NAMED', element))
                self.error('E_PARAMETERS', 'ARRAY parameters require supported scalar elements or a named STRUCTURE type', element)
            if element.value == 'STRING':
                if self.current.value == '[':
                    self.error('E_PARAMETERS', 'ARRAY OF STRING formal parameters inherit element capacity', element)
                return ('ARRAY', shape, ('STRING', None))
            return ('ARRAY', shape, self.group_spec((element.value,),element) if element.value in DATA_RECORD_TYPES else (element.value,))
        if token.kind == 'NAME' and token.value not in RESERVED:
            return ('NAMED', token)
        self.error('E_PARAMETERS', 'Parameter type is not implemented', token)

    def block(self, ends):
        result = []
        self.skip_lines()
        while self.current.value not in ends:
            if self.current.kind == 'EOF':
                self.error('E_SYNTAX', f'Unexpected end of source; expected {sorted(ends)}')
            result.append(self.statement())
            self.skip_lines()
        return result

    def statement(self):
        token = self.take()
        name = token.value
        if self.mode=='pythonic' and name=='PULSE':
            self.expect('DOUT');self.expect('[');port=self.expression();self.expect(']');self.expect('FOR')
            duration=self.expression();nowait=bool(self.accept('NOWAIT'))
            if nowait and self.in_handler_actions: self.error('E_CONDITION_ACTION','NOWAIT is not allowed in a PULSE handler action',token)
            return Statement('pulse',token,[port,duration,nowait])
        if self.mode=='pythonic' and name in ('PAUSE','RESUME','UNPAUSE','CONTINUE','STOP'):
            target=[]
            if name!='STOP' and self.accept('PROGRAM'):
                self.expect('['); target=[self.expression()]; self.expect(']')
            return Statement('task_control',token,[name,*target])
        if self.mode=='pythonic' and name=='SIGNAL':
            kind=self.take()
            if kind.value not in ('EVENT','SEMAPHORE'): self.error('E_SYNTAX','SIGNAL requires EVENT or SEMAPHORE',kind)
            self.expect('['); number=self.expression(); self.expect(']')
            return Statement('signal_event' if kind.value=='EVENT' else 'signal_semaphore',token,[number])
        if self.mode=='pythonic' and name in ('NOABORT','NOPAUSE','NOMESSAGE'):
            if not self.in_handler_actions: self.error('E_CONDITION_ACTION',name+' requires a handler action',token)
            return Statement('handler_action',token,[name])
        if self.mode=='pythonic' and name in ('CONNECT','DISCONNECT'):
            self.expect('TIMER')
            if name=='CONNECT': self.expect('TO')
            return Statement('timer_connect' if name=='CONNECT' else 'timer_disconnect',token,[self.storage_selector()])
        if self.mode=='pythonic' and name=='CONDITION':
            self.expect('['); number=self.expression(); self.expect(']'); self.expect(':'); self.skip_lines()
            scan=None
            if self.accept('WITH'):
                self.expect('$SCAN_TIME'); self.expect('='); scan=self.expression(); self.skip_lines()
            clauses=[]
            while self.current.value=='WHEN':
                when=self.take()
                self.in_condition=True
                try: condition=self.expression()
                finally: self.in_condition=False
                self.expect('DO'); self.skip_lines(); actions=[]
                previous_actions=self.in_handler_actions; self.in_handler_actions=True
                try:
                    while self.current.value not in ('WHEN','ENDCONDITION'):
                        actions.append(self.statement()); self.accept(','); self.skip_lines()
                finally: self.in_handler_actions=previous_actions
                clauses.append(Statement('condition_clause',when,[condition],actions))
            if not clauses: self.error('E_SYNTAX','CONDITION requires at least one WHEN clause')
            self.expect('ENDCONDITION')
            return Statement('condition',token,[number,*([scan] if scan else [])],clauses)
        if self.mode=='pythonic' and name in ('ENABLE','DISABLE','PURGE'):
            self.expect('CONDITION'); self.expect('['); number=self.expression(); self.expect(']')
            return Statement('condition_control',token,[name,number])
        if self.accept('::'):
            self.check_label_name(token)
            return Statement('label', token, [token])
        if name in PREDEFINED_CONSTANTS:
            self.error('E_PREDEFINED_TARGET', 'A predefined constant cannot be an assignment target or procedure call', token)
        if name in ('GO', 'GOTO'):
            if name == 'GO': self.expect('TO')
            target = self.take()
            self.check_label_name(target)
            return Statement('goto', token, [target])
        if name == 'IF':
            condition = self.expression()
            self.expect('THEN')
            body = self.block({'ELSE', 'ENDIF'})
            alternate = self.block({'ENDIF'}) if self.accept('ELSE') else []
            self.expect('ENDIF')
            return Statement('if', token, [condition], body, alternate)
        if name == 'WHILE':
            condition = self.expression()
            self.expect('DO')
            body = self.block({'ENDWHILE'})
            self.expect('ENDWHILE')
            return Statement('while', token, [condition], body)
        if name == 'REPEAT':
            body = self.block({'UNTIL'})
            self.expect('UNTIL')
            return Statement('repeat', token, [self.expression()], body)
        if name == 'FOR':
            counter = self.name()
            self.expect('=')
            initial = self.expression()
            direction = self.take()
            if direction.value not in ('TO', 'DOWNTO'):
                self.error('E_SYNTAX', 'Expected TO or DOWNTO', direction)
            final = self.expression()
            self.expect('DO')
            body = self.block({'ENDFOR'})
            self.expect('ENDFOR')
            return Statement('for', token, [counter, initial, final, direction.value], body)
        if name == 'SELECT':
            selector = self.expression()
            self.expect('OF')
            self.skip_lines()
            cases = []
            while self.accept('CASE'):
                case_token = self.tokens[self.position - 1]
                if len(cases) >= 1000:
                    self.error('E_SELECT_LIMIT', 'SELECT supports at most 1000 CASE clauses', case_token)
                self.expect('(')
                values = [self.expression()]
                while self.accept(','): values.append(self.expression())
                self.expect(')')
                self.expect(':')
                cases.append((case_token, values, self.block({'CASE', 'ELSE', 'ENDSELECT'})))
            alternate = []
            has_else = bool(self.accept('ELSE'))
            if has_else:
                self.expect(':')
                alternate = self.block({'ENDSELECT'})
            self.expect('ENDSELECT')
            if not cases:
                self.error('E_SELECT', 'SELECT requires at least one CASE', token)
            return Statement('select', token, [selector, cases], alternate=alternate, has_else=has_else)
        if self.mode=='pythonic' and name in ('OPEN','CLOSE'):
            self.expect('FILE'); destination=self.storage_selector()
            if name=='CLOSE': return Statement('file_close',token,[destination])
            self.expect('('); mode=self.expression(); self.expect(','); path=self.expression(); self.expect(')')
            return Statement('file_open',token,[destination,mode,path])
        if name == 'RETURN':
            result = None if self.current.kind == 'NL' or self.current.value in BLOCK_ENDS | {';'} else self.expression()
            return Statement('return', token, [result])
        if name == 'DELAY':
            return Statement('delay', token, [self.expression()])
        if name == 'WAIT' and self.mode == 'pythonic':
            self.expect('FOR')
            return Statement('wait', token, [self.expression()])
        if name == 'ABORT':
            if self.mode=='pythonic' and self.accept('PROGRAM'):
                self.expect('['); target=self.expression(); self.expect(']')
                return Statement('task_control',token,['ABORT',target])
            if self.current.value in ('PROGRAM', '(', '[', '.', '='):
                self.error('E_ABORT_TARGET', 'Only bare ABORT of the current offline execution is supported; task qualifiers and arguments remain blocked', self.current)
            return Statement('abort', token)
        if name == 'READ' and self.mode == 'pythonic':
            destination=self.storage_selector() if self.current.value!='(' else None
            self.expect('(')
            targets = []
            self.skip_newlines()
            while True:
                self.skip_newlines()
                if self.current.value in (')', ','):
                    self.error('E_READ_ITEM', 'READ requires scalar destinations or CR; empty items are outside the input contract')
                if len(targets) >= 1024:
                    self.error('E_READ_LIMIT', 'READ supports at most 1024 scalar destinations or CR markers')
                if self.current.value == 'CR':
                    targets.append(Expr('read_cr', self.take()))
                    if self.current.value == '::': self.error('E_READ_FORMAT', 'CR does not accept format specifiers')
                else:
                    target = self.expression(allow_relative=False)
                    formats = []
                    while self.accept('::'):
                        if len(formats) == 2: self.error('E_READ_FORMAT', 'READ accepts at most two INTEGER format expressions')
                        formats.append(self.expression(allow_relative=False))
                    targets.append(Expr('read_item', target.token, args=[target, *formats]) if formats else target)
                if self.current.value == ':': self.error('E_READ_FORMAT', 'READ format specifiers use double colons')
                self.skip_newlines()
                if not self.accept(','): break
            self.expect(')')
            result=Statement('read', token, targets)
            return Statement('file_read',token,[destination,result]) if destination else result
        if name == 'WRITE':
            if self.mode == 'pythonic':
                destination=self.storage_selector() if self.current.value!='(' else None
                result=self.pythonic_write(token)
                return Statement('file_write',token,[destination,result]) if destination else result
            if not self.accept('('):
                self.error('E_WRITE_TARGET', 'WRITE currently supports the omitted-file form with one STRING or unformatted BOOLEAN/INTEGER expression', token)
            if self.current.value in (')', 'CR'):
                self.error('E_WRITE_ITEM', 'WRITE requires one STRING, BOOLEAN or INTEGER expression; empty lists and CR are not implemented')
            value = self.expression()
            formats = []
            format_tokens = []
            if self.accept('::'):
                width = self.current
                width_digits = width.value.lstrip('0') or '0'
                if width.kind != 'INT' or len(width_digits) > 10 or int(width_digits) > 2147483647:
                    self.error('E_WRITE_FORMAT', 'WRITE width requires a nonnegative INTEGER literal in 0..2147483647', width)
                formats.append(int(width_digits))
                format_tokens.append(width)
                self.take()
                if self.accept('::'):
                    alignment = self.current
                    alignment_digits = alignment.value.lstrip('0') or '0'
                    if alignment.kind != 'INT' or alignment_digits not in ('0', '1', '2', '3'):
                        self.error('E_WRITE_FORMAT', 'WRITE alignment requires literal 0/1 (unquoted) or 2/3 (quoted)', alignment)
                    formats.append(int(alignment_digits))
                    format_tokens.append(alignment)
                    self.take()
                if self.current.value not in (')', ',', ':'):
                    self.error('E_WRITE_FORMAT', 'WRITE accepts at most two INTEGER literal format specifiers')
            if self.current.value in (',', ':'):
                self.error('E_WRITE_ITEM', 'Multiple WRITE data items and single-colon formats are not implemented')
            self.expect(')')
            return Statement('write', token, [value, formats, format_tokens])
        if name == 'USING':
            variables = []
            while True:
                variable = self.name()
                selector = Expr('name', variable, variable.value)
                if self.mode == 'pythonic':
                    while self.accept('.'):
                        member = self.name()
                        selector = Expr('field', member, member.value, [selector])
                if self.current.value in ('[', '.', '('):
                    self.error('E_USING_TARGET', 'USING supports named STRUCTURE variables and dotted field paths; indexed/call selectors remain blocked'
                               if self.mode == 'pythonic' else 'USING currently requires bare named STRUCTURE variables', variable)
                variables.append(selector if self.mode == 'pythonic' else variable)
                if not self.accept(','): break
            self.expect('DO')
            body = self.block({'ENDUSING'})
            self.expect('ENDUSING')
            return Statement('using', token, variables, body)
        if token.kind != 'NAME' or name in RESERVED:
            self.error('E_UNSUPPORTED', f'{name} has no implemented translation', token)
        target = self.access(Expr('name', token, name))
        if self.accept('='):
            return Statement('assign', token, [target, self.expression()])
        if target.kind != 'name':
            self.error('E_SYNTAX', 'Expected assignment after variable access', token)
        if self.accept('('):
            arguments = self.arguments()
        else:
            arguments = []
        return Statement('call', token, [Expr('call', token, name, arguments)])

    def pythonic_write(self, token):
        if not self.accept('('):
            self.error('E_WRITE_TARGET', 'WRITE supports the omitted-file parenthesized form', token)
        self.skip_newlines()
        items = []
        while True:
            item_token = self.current
            if item_token.value in (')', ','):
                self.error('E_WRITE_ITEM', 'WRITE requires a data expression or CR', item_token)
            if self.accept('CR'):
                item = Expr('write_cr', item_token)
                if self.current.value == '::':
                    self.error('E_WRITE_FORMAT', 'CR does not accept format specifiers')
            else:
                value = self.expression(allow_relative=False)
                formats = []
                while self.accept('::'):
                    if len(formats) == 2:
                        self.error('E_WRITE_FORMAT', 'WRITE accepts at most two INTEGER format expressions')
                    formats.append(self.expression(allow_relative=False))
                # Include formats in the tree traversed by routine-effect analysis.
                item = Expr('write_item', item_token, args=[value, *formats])
            items.append(item)
            if len(items) > 1024:
                self.error('E_WRITE_ITEMS', 'WRITE exceeds the prototype limit of 1024 items', token)
            self.skip_newlines()
            if not self.accept(','): break
            self.skip_newlines()
        if self.current.value == ':':
            self.error('E_WRITE_ITEM', 'WRITE format specifiers use double colons')
        self.expect(')')
        return Statement('write_items', token, items)

    def storage_selector(self):
        token=self.name(); result=Expr('name',token,token.value)
        while self.current.value in ('.','['):
            if self.accept('.'):
                member=self.name(); result=Expr('field',member,member.value,[result])
            else:
                opening=self.take(); indexes=[self.expression()]
                while self.accept(','): indexes.append(self.expression())
                self.expect(']'); result=Expr('index',opening,args=[result,*indexes])
        return result

    def check_label_name(self, token):
        if (token.kind != 'NAME' or token.value in RESERVED | BUILTINS | CONTROLLER_NAMES | ex.PORT_TYPES.keys() | PREDEFINED_CONSTANTS.keys()
                or not token.value[0].isalpha() or len(token.value) > 36):
            self.error('E_LABEL_NAME', 'Labels require a non-reserved letter-starting identifier of at most 36 characters', token)

    def arguments(self):
        self.skip_lines()
        if self.accept(')'): return []
        result = [self.expression()]
        while self.accept(','): result.append(self.expression())
        self.expect(')')
        return result

    def access(self, base):
        while self.current.value in ('[', '.'):
            token = self.take()
            if token.value == '[':
                indexes = [self.expression()]
                while self.accept(','): indexes.append(self.expression())
                self.expect(']')
                base = Expr('index', token, args=[base, *indexes])
            else:
                member = self.name()
                base = Expr('field', member, member.value, [base])
        return base

    def expression(self, minimum=0, *, allow_relative=True):
        self.skip_lines()
        token = self.take()
        if self.mode=='pythonic' and token.value in ('EVENT','SEMAPHORE'):
            self.expect('['); number=self.expression(); self.expect(']'); left=Expr('event' if token.value=='EVENT' else 'semaphore',token,args=[number])
        elif self.in_condition and token.value=='ERROR':
            self.expect('[')
            arguments=[] if self.accept('*') else [self.expression()]
            self.expect(']'); left=Expr('error_condition',token,args=arguments)
        elif self.in_condition and token.value in ('PAUSE','ABORT','CONTINUE','POWERUP'):
            left=Expr('task_event',token,token.value)
        elif token.kind == 'INT':
            digits = token.value.lstrip('0') or '0'
            if len(digits) > 10:
                self.error('E_LITERAL', 'INTEGER literal outside signed 32-bit range', token)
            left = Expr('literal', token, int(digits))
        elif token.kind == 'STRING':
            value = token.value[1:-1].replace("''", "'")
            if not value.isascii():
                self.error('E_ENCODING', 'Only ASCII source string literals are implemented', token)
            if "''" in token.value[1:-1]:
                self.escaped_string_literals.append(dict(line=token.line, column=token.column,
                                                        source_characters=len(token.value), logical_characters=len(value),
                                                        escaped_apostrophes=token.value[1:-1].count("''")))
            left = Expr('literal', token, value)
        elif token.value in ('TRUE', 'FALSE'):
            left = Expr('literal', token, token.value == 'TRUE')
        elif token.value in PREDEFINED_CONSTANTS:
            if self.current.value in ('(', '[', '.'):
                self.error('E_PREDEFINED_CONTEXT', 'A predefined constant is a scalar value, not a call or aggregate', token)
            self.predefined_uses.append(dict(name=token.value, line=token.line, column=token.column))
            left = Expr('predefined', token, token.value)
        elif token.value in ('+', '-', 'NOT'):
            # KAREL unary +/- have the same precedence as addition, below *.
            left = Expr('unary', token, token.value, [self.expression(50 if token.value == 'NOT' else 21, allow_relative=allow_relative)])
        elif token.value == '(':
            child = self.expression()
            self.expect(')')
            # Parentheses around an argument variable change KAREL passing mode.
            left = Expr('group', token, args=[child])
        elif token.kind == 'REAL':
            left = Expr('real_literal', token, token.value)
        elif token.kind == 'NAME' and token.value not in RESERVED:
            if self.accept('('): left = Expr('call', token, token.value, self.arguments())
            else: left = self.access(Expr('name', token, token.value))
            if (self.in_condition or self.in_handler_actions) and left.kind=='call' and left.value=='EVAL':
                if len(left.args)!=1: self.error('E_ARGUMENTS','EVAL requires one captured expression',token)
                left.kind='eval'
        else:
            self.error('E_EXPRESSION', f'Expected expression, found {token.value}', token)
        if self.mode == 'pythonic' and left.kind in ('call', 'group'):
            left = self.access(left)
        if (self.in_condition and left.kind=='index' and left.args[0].kind=='name'
                and ex.PORT_TYPES.get(left.args[0].value)=='BOOLEAN' and self.current.value in ('+','-')
                and self.tokens[self.position+1].value in ('DO','AND','OR',')','=','<>')):
            operator=self.take(); left=Expr('edge',operator,operator.value,[left])
        while (self.current.value in PRECEDENCE and PRECEDENCE[self.current.value] >= minimum
               and (self.current.value != ':' or self.mode == 'pythonic' and allow_relative)):
            operator = self.take()
            if (self.mode == 'strict' and operator.value in ('#', '@') and left.kind == 'binary'
                    and left.value in ('#', '@')):
                self.error('E_VECTOR_ASSOCIATIVITY', 'Parenthesize chained #/@ operations; same-level association needs KAREL validation', operator)
            if self.mode == 'strict' and operator.value == '>=<':
                self.error('E_OPERATOR', f'{operator.value} requires an unimplemented numeric/geometry mapping', operator)
            right = self.expression(PRECEDENCE[operator.value] + 1, allow_relative=allow_relative)
            left = Expr('binary', operator, operator.value, [left, right])
        return left


class Emitter:
    def __init__(self, program, filename, array_shapes=None, mode='strict', cooperative=False):
        self.program, self.filename = program, filename
        self.mode = mode
        self.constants, self.types, self.routines, self.user_types = {}, {}, {}, {}
        self.type_aliases = []
        self.lines, self.source_map, self.features = [], [], set()
        self.indent, self.temporary = 0, 0
        self.current_routine = None
        self.cooperative=mode=='pythonic' and (cooperative or any(isinstance(node,Statement) and node.kind in ('pulse','task_control','condition','condition_control','timer_connect','timer_disconnect','signal_event','signal_semaphore') or isinstance(node,Expr) and (node.kind in ('event','edge','semaphore') or node.kind=='call' and node.value in {'PAUSE_TASK','CONT_TASK','ABORT_TASK','RUN_TASK'}|ex.COOPERATIVE_PROCEDURES) for body in (program.body,*[r.body for r in program.routines]) for node in self.walk_nodes(body)) or any(r.external for r in program.routines))
        self.group_uses=[]
        self.using_scopes = []
        self.active_counters = set()
        self.control_flow = dict(program=None, routines={}, jump_policy='same_block_or_ancestor_no_for', controller_validated=False)
        self.select_scopes = []
        self.subarray_uses = []
        self.delay_uses = []
        self.wait_uses = []
        self.string_value_uses = []
        self.string_return_uses = []
        self.write_uses = []
        self.read_uses = []
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
        self.joint_geometry_uses = []
        self.pulse_uses = []
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
        if self.cooperative: text=re.sub(r'self\._state\.tick\(([^()]*)\)',r'(yield from _rt.checkpoint(self._state,\1))',text)
        self.lines.append('    ' * self.indent + text)
        if token:
            self.source_map.append(dict(python_line=len(self.lines), karel_line=token.line,
                                        karel_column=token.column))

    def fresh(self):
        self.temporary += 1
        return f'_temporary_{self.temporary}'

    def visible_constants(self):
        """Constants have lexical scope; a callee never sees its caller's names."""
        if self.current_routine:
            return self.constants | self.current_routine.local_constants
        return self.constants

    def constant(self, expr):
        try:
            if expr.kind == 'literal': return expr.value
            if expr.kind == 'predefined': return PREDEFINED_CONSTANTS[expr.value]
            if expr.kind == 'real_literal': return rt.real_literal(expr.value)
            if expr.kind == 'group': return self.constant(expr.args[0])
            if expr.kind == 'name' and expr.value in self.visible_constants():
                return self.visible_constants()[expr.value]
            if self.is_minimum_literal(expr):
                self.error('E_MININT_LITERAL', 'The manual requires MININT instead of the INTEGER literal -2147483648', expr.token)
            if expr.kind == 'unary': return rt.unary(expr.value, self.constant(expr.args[0]))
            if expr.kind == 'binary': return rt.binary(expr.value, *(self.constant(x) for x in expr.args))
        except rt.KarelRuntimeError as exc:
            self.error('E_CONSTANT', str(exc), expr.token)
        self.error('E_CONSTANT', 'Expected a literal or previously declared constant expression', expr.token)

    @staticmethod
    def is_minimum_literal(expr):
        if expr.kind != 'unary' or expr.value != '-': return False
        child = expr.args[0]
        while child.kind == 'group': child = child.args[0]
        return child.kind == 'literal' and type(child.value) is int and child.value == 2147483648

    def resolve_spec(self, spec):
        if spec[0]=='GROUPED':
            group=self.constant(spec[2])
            if type(group) is not int or not 1<=group<=32: self.error('E_POSITION_GROUP','Group must be an INTEGER in 1..32',spec[3])
            resolved=self.resolve_spec(spec[1])
            self.group_uses.append(dict(group=group,type=resolved[0],line=spec[3].line,column=spec[3].column))
            self.features.add('explicit group metadata'); return resolved
        if spec[0] in ('FILE','QUEUE_TYPE'): return spec
        if spec[0]=='PATH':
            resolved=('PATH',self.resolve_spec(spec[1]) if spec[1] else None,self.resolve_spec(spec[2]) if spec[2] else None)
            if any(item and item[0]!='STRUCTURE' for item in resolved[1:]):
                self.error('E_TYPE','PATH NODEDATA and PATHHEADER require named STRUCTURE types',spec[3] if len(spec)>3 else Token('NAME','PATH',1,1))
            return resolved
        if spec[0] == 'JOINTPOS':
            rt.joint_width(spec)
            self.features.add('JOINTPOS data')
            return spec
        if spec[0] in ('INTEGER', 'BOOLEAN', 'REAL', 'BYTE', 'SHORT'):
            if spec[0] in NARROW_TYPES: self.features.add(spec[0] + ' storage')
            return spec
        if spec[0] == 'NAMED':
            token = spec[1]
            if token.value not in self.user_types:
                self.error('E_TYPE', f'{token.value} is not a previously defined supported type', token)
            return self.user_types[token.value]
        if spec[0] in DATA_RECORD_TYPES:
            self.features.add(spec[0] + ' data record')
            return spec
        if spec[0] == 'STRUCTURE': return spec
        if spec[0] == 'ARRAY':
            dimensions = spec[1] if isinstance(spec[1], tuple) else (spec[1],)
            wildcard = next((size for size in dimensions if isinstance(size, Expr) and size.kind == 'array_wildcard'), None)
            if wildcard is not None:
                self.error('E_VARIABLE_ARRAY_SCOPE', 'Variable-sized ARRAYs are supported only as direct global VAR declarations with explicit translation context; TYPE/fields/routine locals remain blocked', wildcard.token)
            element = self.resolve_spec(spec[2])
            if element[0] == 'ARRAY':
                if rt.array_identity(element) is None:
                    self.error('E_NESTED_NAMED_ARRAY', 'Nested ARRAY elements require a separately named type', spec[2][1])
                self.features.add('ARRAY OF named ARRAY')
            if len(rt.array_dimensions(('ARRAY', spec[1], element))) > 3:
                self.error('E_ARRAY_RANK', 'Nested arrays support at most three logical dimensions', spec[2][1])
            if element[0] == 'STRUCTURE': self.features.add('ARRAY OF named STRUCTURE')
            if spec[1] is None or isinstance(spec[1], tuple) and all(size is None for size in spec[1]):
                return ('ARRAY', spec[1], element)  # Formal shape comes from caller storage.
        if spec[1] is None: return spec  # Formal capacity is supplied by the reference.
        if spec[0] == 'ARRAY' and isinstance(spec[1], tuple):
            if all(size is None for size in spec[1]): return spec  # Rank-specific formal.
            sizes = []
            for dimension in spec[1]:
                size = self.constant(dimension)
                if type(size) is not int or not 1 <= size <= 32767:
                    self.error('E_SIZE', 'ARRAY dimension size must be INTEGER in 1..32767', dimension.token)
                sizes.append(size)
            total = 1
            for size in sizes: total *= size
            if total > 32767:
                self.error('E_ARRAY_CAPACITY', 'Prototype arrays are limited to 32767 scalar elements in total', spec[1][0].token)
            if element[0] not in (*ARRAY_ELEMENTS, 'ARRAY'):
                self.error('E_TYPE', 'ARRAY elements require supported scalars or named STRUCTURE types', spec[1][0].token)
            if rt.scalar_leaf_count(('ARRAY', tuple(sizes), element)) > 32767:
                self.error('E_ARRAY_CAPACITY', 'Prototype arrays are limited to 32767 scalar leaves including STRUCTURE fields', spec[1][0].token)
            self.features.add('multidimensional STRUCTURE ARRAY' if element[0] == 'STRUCTURE' else 'multidimensional scalar ARRAY')
            return ('ARRAY', tuple(sizes), element)
        size = self.constant(spec[1])
        limit = 254 if spec[0] == 'STRING' else 32767
        if type(size) is not int or not 1 <= size <= limit:
            self.error('E_SIZE', f'{spec[0]} size must be INTEGER in 1..{limit}', spec[1].token)
        if spec[0] == 'STRING': return (spec[0], size)
        if element[0] not in (*ARRAY_ELEMENTS, 'ARRAY'):
            self.error('E_TYPE', 'ARRAY elements require supported scalars or named STRUCTURE types; nested arrays are blocked', spec[1].token)
        if rt.scalar_leaf_count(('ARRAY', size, element)) > 32767:
            self.error('E_ARRAY_CAPACITY', 'Prototype arrays are limited to 32767 scalar leaves including STRUCTURE fields', spec[1].token)
        return ('ARRAY', size, element)

    def resolve_array_result_spec(self, spec, token):
        """Resolve Pythonic result dimensions in the global interface scope."""
        if rt.array_identity(spec) is not None: return spec
        element = self.resolve_spec(spec[2])
        dimensions = []
        for size in rt.array_shape(('ARRAY',spec[1],element)):
            if size is None or isinstance(size, Expr) and size.kind == 'array_wildcard':
                dimensions.append(None)
            else:
                value = self.constant(size)
                if type(value) is not int or not 1 <= value <= 32767:
                    self.error('E_SIZE', 'ARRAY result dimensions require INTEGER in 1..32767 or *', size.token)
                dimensions.append(value)
        if element[0] == 'ARRAY' and rt.array_identity(element) is None:
            self.error('E_NESTED_NAMED_ARRAY', 'ARRAY result components require a prior named ARRAY type', token)
        shape = dimensions[0] if len(dimensions) == 1 else tuple(dimensions)
        result = ('ARRAY', shape, element)
        if len(rt.array_dimensions(result)) > 3:
            self.error('E_ARRAY_RANK', 'ARRAY results support at most three logical dimensions', token)
        minimum = tuple(1 if size is None else size for size in dimensions)
        if rt.scalar_leaf_count(('ARRAY', minimum, element)) > 32767:
            self.error('E_ARRAY_CAPACITY', 'ARRAY results are limited to 32767 scalar leaves', token)
        return result

    def resolve_global_spec(self, token, spec):
        """Specialize only direct static declarations; never guess loaded storage."""
        if spec[0] != 'ARRAY': return self.resolve_spec(spec)
        dimensions = spec[1] if isinstance(spec[1], tuple) else (spec[1],)
        wildcards = [n for n, size in enumerate(dimensions) if size.kind == 'array_wildcard']
        if not wildcards: return self.resolve_spec(spec)
        if token.value not in self.array_shapes:
            self.error('E_ARRAY_SIZE', f'{token.value} requires explicit translate(array_shapes={{...}}) dimensions; preexisting/VR/KCL storage is not inferred', token)
        shape = self.array_shapes[token.value]
        if len(shape) != len(dimensions):
            self.error('E_ARRAY_CONTEXT', f'{token.value} external shape must match its {len(dimensions)} declared outer dimensions', token)
        resolved_dimensions = []
        declared = []
        for n, dimension in enumerate(dimensions):
            if n in wildcards:
                declared.append('*')
                resolved_dimensions.append(Expr('literal', dimension.token, shape[n]))
            else:
                value = self.constant(dimension)
                if type(value) is not int or not 1 <= value <= 32767:
                    self.error('E_SIZE', 'ARRAY dimension size must be INTEGER in 1..32767', dimension.token)
                if value != shape[n]:
                    self.error('E_ARRAY_CONTEXT', f'{token.value} dimension {n+1} is declared {value}, but external shape specifies {shape[n]}', dimension.token)
                declared.append(value)
                resolved_dimensions.append(dimension)
        specialized = resolved_dimensions[0] if len(dimensions) == 1 else tuple(resolved_dimensions)
        resolved = self.resolve_spec(('ARRAY', specialized, spec[2]))
        self.variable_array_uses.append(dict(name=token.value, line=token.line, column=token.column,
                                            declared_dimensions=declared, resolved_outer_dimensions=list(shape),
                                            wildcard_dimensions=[n+1 for n in wildcards],
                                            logical_dimensions=list(rt.array_dimensions(resolved))))
        self.features.add('externally sized static ARRAY')
        return resolved

    def validate_symbols(self):
        names = set()
        for token, expr in self.program.constants:
            if token.value in ex.PORT_TYPES: self.error('E_DUPLICATE','Port identifiers cannot be constants',token)
            if token.value in names: self.error('E_DUPLICATE', 'Duplicate declaration', token)
            names.add(token.value)
            value = self.constant(expr)
            if type(value) is int:
                try: rt.integer(value)
                except rt.KarelRuntimeError as exc: self.error('E_CONSTANT', str(exc), token)
            self.constants[token.value] = value
        for token, definition in self.program.user_types:
            if token.value in names: self.error('E_DUPLICATE', 'Duplicate declaration', token)
            names.add(token.value)
            if isinstance(definition, tuple):
                resolved = self.resolve_spec(definition)
                if definition[0] == 'ARRAY':
                    self.user_types[token.value] = (*resolved, token.value)
                    self.features.add('named ARRAY definition')
                else:
                    self.user_types[token.value] = resolved
                    self.type_aliases.append(dict(name=token.value, line=token.line, column=token.column,
                                                  target=definition[1].value if definition[0] == 'NAMED' else definition[0],
                                                  resolved_spec=resolved))
                    self.features.add('transparent TYPE alias')
                continue
            resolved = {}
            for member, spec in definition:
                if member.value in resolved: self.error('E_DUPLICATE', 'Duplicate STRUCTURE field', member)
                resolved[member.value] = self.resolve_spec(spec)
                if resolved[member.value][0] in ('FILE','PATH','QUEUE_TYPE'):
                    self.error('E_TYPE','Resource fields in STRUCTURE are not supported',member)
            self.user_types[token.value] = ('STRUCTURE', token.value, tuple(resolved.items()))
            self.features.add('named STRUCTURE definition')
        for token, spec in self.program.declarations:
            if token.value in names: self.error('E_DUPLICATE', 'Duplicate declaration', token)
            if token.value in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys():
                self.error('E_CONTROLLER', 'Controller identifiers are not supported', token)
            names.add(token.value)
            resolved = self.resolve_global_spec(token, spec)
            if resolved[0] in NARROW_TYPES:
                self.error('E_TYPE', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
            self.types[token.value] = resolved
        used_shapes = {row['name'] for row in self.variable_array_uses}
        unused = set(self.array_shapes) - used_shapes
        if unused:
            self.error('E_ARRAY_CONTEXT', 'External shapes may name only direct global variable-sized ARRAYs; unused names: ' + ', '.join(sorted(unused)), Token('NAME', '<array_shapes>', 1, 1))
        for routine in self.program.routines:
            if routine.name in names: self.error('E_DUPLICATE', 'Duplicate declaration', routine.token)
            names.add(routine.name)
            self.routines[routine.name] = routine
            if routine.return_type and routine.return_type[0]=='GROUPED':
                routine.return_type=self.resolve_spec(routine.return_type)
            if routine.return_type and routine.return_type[0] == 'STRING':
                routine.return_type = self.resolve_spec(routine.return_type)
                self.features.add('STRING function result')
            if routine.return_type and routine.return_type[0] == 'NAMED':
                result_token = routine.return_type[1]
                definition_token = next((token for token, _ in self.program.user_types if token.value == result_token.value), None)
                if definition_token and (definition_token.line, definition_token.column) > (routine.token.line, routine.token.column):
                    self.error('E_TYPE', 'Named result types must be declared before the routine', result_token)
                routine.return_type = self.resolve_spec(routine.return_type)
                allowed_named_results = ('STRUCTURE',)
                if self.mode == 'pythonic':
                    allowed_named_results += ('ARRAY', 'STRING', 'INTEGER', 'BOOLEAN', 'REAL', *DATA_RECORD_TYPES, 'JOINTPOS')
                if routine.return_type[0] not in allowed_named_results:
                    message = ('BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields' if self.mode == 'pythonic'
                               else 'Named ARRAY function results remain blocked; a named result type must be a STRUCTURE')
                    self.error('E_RETURN_TYPE', message, routine.token)
                self.features.add('named ' + routine.return_type[0] + ' function result')
                if routine.return_type[0] == 'STRING': self.features.add('STRING function result')
            if routine.return_type == ('VECTOR',): self.features.add('VECTOR function result')
            if routine.return_type and routine.return_type[0] == 'ARRAY':
                element = routine.return_type[2]
                if element[0] == 'NAMED':
                    result_token = element[1]
                    definition_token = next((token for token, _ in self.program.user_types if token.value == result_token.value), None)
                    if definition_token and (definition_token.line, definition_token.column) > (routine.token.line, routine.token.column):
                        self.error('E_TYPE', 'Named result element types must be declared before the routine', result_token)
                routine.return_type = (self.resolve_array_result_spec(routine.return_type, routine.token)
                                       if self.mode == 'pythonic' else self.resolve_spec(routine.return_type))
                element = routine.return_type[2]
                leaf = rt.array_leaf_spec(element) if element[0] == 'ARRAY' else element
                if leaf[0] not in (*ARRAY_SCALARS, *RECORD_TYPES, 'JOINTPOS'):
                    self.error('E_RETURN_TYPE', 'ARRAY result terminal elements require supported scalars, bounded STRINGs, records or exact-width joints', routine.token)
                if leaf[0] == 'STRING':
                    self.features.add('bounded STRING ARRAY function result')
                if len(rt.array_shape(routine.return_type)) > 1:
                    self.features.add('multidimensional ARRAY function result')
                if element[0] == 'ARRAY':
                    self.features.add('named-component ARRAY function result')
                elif len(rt.array_shape(routine.return_type)) == 1:
                    self.features.add('1D aggregate ARRAY function result' if element[0] in (*RECORD_TYPES, 'JOINTPOS') else '1D scalar ARRAY function result')
            if routine.return_type and routine.return_type[0] in POSITIONAL_VALUE_TYPES:
                self.features.add('exact positional function result')
        for routine in self.program.routines:
            # Parameters are resolved before local declarations: local constants
            # cannot alter the routine's interface or a global type definition.
            for token, spec in routine.parameters:
                if token.value in routine.local_types or token.value in self.constants or token.value in self.user_types or token.value in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys():
                    self.error('E_DUPLICATE', 'Duplicate, constant-shadowing or controller local identifier', token)
                resolved = self.resolve_spec(spec)
                if resolved[0] in NARROW_TYPES:
                    self.error('E_PARAMETERS', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
                routine.local_types[token.value] = resolved
            routine.parameters = [(token, routine.local_types[token.value]) for token, _ in routine.parameters]
            self.current_routine = routine
            for kind, token, definition in routine.local_declarations:
                if (token.value in routine.local_types or token.value in routine.local_constants
                        or token.value in self.constants or token.value in self.user_types
                        or token.value in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys()):
                    self.error('E_DUPLICATE', 'Duplicate, constant-shadowing or controller local identifier', token)
                if kind == 'CONST':
                    if token.value in names or token.value == self.program.name:
                        self.error('E_LOCAL_CONST_SHADOW', 'Local constants that shadow global declarations need namespace evidence', token)
                    value = self.constant(definition)
                    if type(value) is int:
                        try: rt.integer(value)
                        except rt.KarelRuntimeError as exc: self.error('E_CONSTANT', str(exc), token)
                    routine.local_constants[token.value] = value
                    self.features.add('routine-local CONST')
                else:
                    resolved = self.resolve_spec(definition)
                    if resolved[0] in NARROW_TYPES:
                        self.error('E_TYPE', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
                    routine.local_types[token.value] = resolved
            self.current_routine = None
        self.resolve_using_fields()
        self.resolve_bare_function_calls()
        self.analyze_routine_effects()

    def resolve_bare_function_calls(self):
        """Resolve value names before call/effect checks, preserving storage roots."""
        def resolve(node, storage=False):
            if isinstance(node, Expr):
                if node.kind == 'name' and not storage and node.value in self.routines:
                    shadowed = (self.current_routine and
                                node.value in (self.current_routine.local_types.keys()
                                               | self.current_routine.local_constants.keys()))
                    if not shadowed:
                        routine = self.routines[node.value]
                        if routine.parameters:
                            self.error('E_ARGUMENTS', 'A bare routine name requires a function with no parameters; supply the declared arguments', node.token)
                        if routine.return_type is None:
                            self.error('E_TYPE', 'Procedure cannot be used as an expression', node.token)
                        self.bare_function_uses.append(dict(
                            body=self.current_routine.name if self.current_routine else self.program.name,
                            name=node.value, line=node.token.line, column=node.token.column,
                            result_spec=routine.return_type))
                        self.features.add('bare zero-argument function call')
                        return Expr('call', node.token, node.value, [])
                if node.kind == 'name' and not storage and self.mode == 'pythonic' and node.value in ('GET_USEC_TIM','CURR_PROG') and node.value not in self.routines:
                    local_names = (self.current_routine.local_types.keys() | self.current_routine.local_constants.keys()) if self.current_routine else set()
                    if node.value not in self.types.keys() | self.constants.keys() | local_names:
                        self.bare_function_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                            name=node.value,line=node.token.line,column=node.token.column,result_spec=('INTEGER',) if node.value=='GET_USEC_TIM' else ('STRING',12)))
                        self.features.add('bare zero-argument function call')
                        return Expr('call',node.token,node.value,[])
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

    def resolve_using_fields(self):
        """Resolve lexical field aliases before effect and control-flow analysis."""
        def path_text(expr):
            return path_text(expr.args[0]) + '.' + expr.value if expr.kind == 'field' else expr.value

        def copy_path(expr, token):
            # Insert absolute paths without revisiting their roots as aliases.
            return Expr(expr.kind, token, expr.value, [copy_path(child, token) for child in expr.args])

        def resolve(node, bindings=None, scope=None):
            if isinstance(node, Expr):
                if bindings and node.kind == 'name' and node.value in bindings:
                    if self.mode == 'strict' and node.value in self.visible_constants():
                        self.error('E_USING_CONST_SHADOW', 'Constants whose names coincide with USING fields need namespace validation', node.token)
                    variable = bindings[node.value]
                    scope['resolved_uses'].append(dict(field=node.value, variable=path_text(variable),
                                                      line=node.token.line, column=node.token.column))
                    # Do not revisit this newly qualified root: its spelling can
                    # itself coincide with a field in another listed structure.
                    return Expr('field', node.token, node.value,
                                [copy_path(variable, node.token)])
                if self.mode == 'strict' and bindings and node.kind == 'call' and node.value in bindings:
                    self.error('E_USING_CALL_SHADOW', 'Calls whose names coincide with USING fields need namespace validation', node.token)
                node.args = [resolve(argument, bindings, scope) for argument in node.args]
            elif isinstance(node, Statement):
                if node.kind == 'using':
                    if self.mode == 'strict' and scope is not None:
                        self.error('E_USING_NESTED', 'Nested USING field priority needs additional evidence', node.token)
                    fields = dict(bindings or {})
                    selectors, source_selectors = [], []
                    for variable in node.args:
                        selector = variable if isinstance(variable, Expr) else Expr('name', variable, variable.value)
                        source_selectors.append(path_text(selector))
                        # A selector list uses enclosing aliases only, never the
                        # fields introduced by earlier selectors in this list.
                        selector = resolve(selector, bindings, scope)
                        spec = self.access_type(selector)
                        if spec[0] != 'STRUCTURE':
                            self.error('E_USING_TYPE', 'USING requires a named STRUCTURE variable or field path', selector.token)
                        for name, _ in spec[2]: fields[name] = selector
                        selectors.append(selector)
                    parent = scope
                    scope = dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                 line=node.token.line, column=node.token.column,
                                 variables=[path_text(selector) for selector in selectors],
                                 field_bindings={name:path_text(selector) for name,selector in fields.items()}, resolved_uses=[])
                    if self.mode == 'pythonic':
                        scope.update(id=len(self.using_scopes), parent=parent['id'] if parent else None,
                                     depth=parent['depth']+1 if parent else 0, source_selectors=source_selectors)
                    self.using_scopes.append(scope)
                    self.features.add('USING explicit field resolution')
                    if parent: self.features.add('nested USING lexical scope')
                    if any(selector.kind == 'field' for selector in selectors): self.features.add('qualified USING selector')
                    node.args = selectors
                    node.body = resolve(node.body, fields, scope)
                    return node
                if bindings and node.kind == 'for' and node.args[0].value in bindings:
                    self.error('E_USING_FOR_COUNTER', 'FOR counters shadowed by USING fields need field-counter semantics', node.args[0])
                node.args = [resolve(argument, bindings, scope) for argument in node.args]
                node.body = resolve(node.body, bindings, scope)
                node.alternate = resolve(node.alternate, bindings, scope)
            elif isinstance(node, list):
                return [resolve(child, bindings, scope) for child in node]
            elif isinstance(node, tuple):
                return tuple(resolve(child, bindings, scope) for child in node)
            return node

        self.program.body = resolve(self.program.body)
        for routine in self.program.routines:
            self.current_routine = routine
            routine.body = resolve(routine.body)
        self.current_routine = None

    @staticmethod
    def walk_nodes(node):
        if isinstance(node, (Expr, Statement)):
            yield node
            for argument in node.args:
                yield from Emitter.walk_nodes(argument)
            if isinstance(node, Statement):
                yield from Emitter.walk_nodes(node.body)
                yield from Emitter.walk_nodes(node.alternate)
        elif isinstance(node, (list, tuple)):
            for child in node: yield from Emitter.walk_nodes(child)

    def analyze_routine_effects(self):
        edges, calls_by_routine = {}, {}
        for routine in self.program.routines:
            if routine.external:
                routine.parameter_writes.update(token.value for token,_ in routine.parameters)
                routine.may_services=True
            local_names = {token.value for token, _ in routine.declarations}
            parameter_names = {token.value for token, _ in routine.parameters}
            calls, call_nodes = set(), []
            for node in self.walk_nodes(routine.body):
                if isinstance(node,Statement) and node.kind=='pulse':
                    routine.may_services=True;routine.may_delay|=not node.args[2]
                if isinstance(node, Statement) and node.kind in ('delay','wait'):
                    routine.may_delay = True
                if isinstance(node, Statement) and node.kind in ('write', 'write_items'):
                    routine.may_write = True
                if isinstance(node, Statement) and node.kind == 'read':
                    routine.may_read = True
                    for target in node.args:
                        if target.kind == 'read_cr': continue
                        if target.kind == 'read_item': target = target.args[0]
                        name = self.root_name(target)
                        if name not in local_names: routine.side_effecting = True
                        if name in parameter_names: routine.parameter_writes.add(name)
                        if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                if isinstance(node, Statement) and node.kind == 'abort':
                    routine.may_abort = True
                if isinstance(node, Expr) and node.kind == 'call' and self.mode == 'pythonic' and node.value == 'GET_USEC_TIM' and node.value not in self.routines:
                    routine.may_clock = True
                if isinstance(node,Expr) and node.kind=='call' and self.mode=='pythonic' and node.value in ex.PROCEDURES.keys()|ex.FUNCTIONS.keys() and node.value not in self.routines:
                    routine.may_services=True
                    if node.value=='PRINT_FILE': routine.may_write=True
                    signature=ex.signature_for(node.value,len(node.args))
                    for argument,(mode,_) in zip(node.args,signature):
                        if mode not in ('o','r','m'): continue
                        name=self.root_name(argument)
                        if name not in local_names: routine.side_effecting=True
                        if name in parameter_names: routine.parameter_writes.add(name)
                        if name in self.types and name not in local_names|parameter_names: routine.global_writes.add(name)
                    if node.value=='SET_VAR': routine.global_writes.update(self.types)
                if isinstance(node, Statement) and node.kind in ('assign', 'for'):
                    name = node.args[0].value if node.kind == 'for' else self.root_name(node.args[0])
                    if name not in local_names: routine.side_effecting = True
                    if name in parameter_names: routine.parameter_writes.add(name)
                    if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                if isinstance(node, Statement) and node.kind == 'call':
                    call = node.args[0]
                    if call.value in MULTI_OUTPUT_PROCEDURES:
                        for output in call.args[1:]:
                            name = self.root_name(output)
                            if name not in local_names: routine.side_effecting = True
                            if name in parameter_names: routine.parameter_writes.add(name)
                            if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                    if self.mode == 'pythonic' and call.value in CONFIG_TEXT_PROCEDURES | TIME_TEXT_PROCEDURES and call.value not in self.routines:
                        for output in call.args[1:]:
                            name = self.root_name(output)
                            if name not in local_names: routine.side_effecting = True
                            if name in parameter_names: routine.parameter_writes.add(name)
                            if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                    if self.mode == 'pythonic' and call.value in REGISTER_PROCEDURES and call.value not in self.routines:
                        if call.value == 'GET_REG': routine.may_read_registers = True
                        else: routine.may_write_registers = True
                        for output in call.args[1:] if call.value == 'GET_REG' else call.args[2:]:
                            name = self.root_name(output)
                            if name not in local_names: routine.side_effecting = True
                            if name in parameter_names: routine.parameter_writes.add(name)
                            if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                    if call.value in BUILTIN_PROCEDURES and call.args:
                        name = self.root_name(call.args[-1])
                        if name not in local_names:
                            routine.side_effecting = True
                        if name in parameter_names: routine.parameter_writes.add(name)
                        if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                if isinstance(node, Expr) and node.kind == 'call' and node.value in self.routines:
                    calls.add(node.value)
                    call_nodes.append(node)
            edges[routine.name] = calls
            calls_by_routine[routine.name] = call_nodes
        changed = True
        while changed:
            changed = False
            for routine in self.program.routines:
                if not routine.side_effecting and any(self.routines[name].side_effecting for name in edges[routine.name]):
                    routine.side_effecting = True
                    changed = True
                if not routine.may_delay and any(self.routines[name].may_delay for name in edges[routine.name]):
                    routine.may_delay = True
                    changed = True
                if not routine.may_write and any(self.routines[name].may_write for name in edges[routine.name]):
                    routine.may_write = True
                    changed = True
                if not routine.may_read and any(self.routines[name].may_read for name in edges[routine.name]):
                    routine.may_read = True
                    changed = True
                if not routine.may_abort and any(self.routines[name].may_abort for name in edges[routine.name]):
                    routine.may_abort = True
                    changed = True
                if not routine.may_clock and any(self.routines[name].may_clock for name in edges[routine.name]):
                    routine.may_clock = True
                    changed = True
                for effect in ('may_read_registers','may_write_registers'):
                    if not getattr(routine,effect) and any(getattr(self.routines[name],effect) for name in edges[routine.name]):
                        setattr(routine,effect,True)
                        changed = True
                if not routine.may_services and any(self.routines[name].may_services for name in edges[routine.name]):
                    routine.may_services=True; changed=True
                parameter_names = {token.value for token, _ in routine.parameters}
                local_names = {token.value for token, _ in routine.declarations}
                for call in calls_by_routine[routine.name]:
                    callee = self.routines[call.value]
                    inherited = callee.global_writes - routine.global_writes
                    if inherited:
                        routine.global_writes.update(inherited)
                        changed = True
                    for argument, (formal, expected) in zip(call.args, callee.parameters):
                        # Only bare storage lets a callee write back to a formal.
                        # Grouping makes a temporary copy instead.
                        if formal.value not in callee.parameter_writes or argument.kind not in ('name', 'index', 'field'):
                            continue
                        name = self.root_name(argument)
                        actual = routine.local_types.get(name, self.types.get(name))
                        if (self.mode == 'pythonic' and argument.kind == 'name' and expected == ('REAL',)
                                and actual == ('INTEGER',)):
                            continue  # INTEGER-to-REAL actuals are independent values.
                        if name in parameter_names and name not in routine.parameter_writes:
                            routine.parameter_writes.add(name)
                            changed = True
                        if (name in self.types and name not in local_names | parameter_names
                                and name not in routine.global_writes):
                            routine.global_writes.add(name)
                            changed = True

    def has_external_effect_call(self, expr):
        return any(isinstance(node, Expr) and node.kind == 'call' and node.value in self.routines
                   and (self.routines[node.value].side_effecting or self.routines[node.value].may_delay
                        or self.routines[node.value].may_write or self.routines[node.value].may_read or self.routines[node.value].may_abort
                        or self.routines[node.value].may_clock or self.routines[node.value].may_read_registers
                        or self.routines[node.value].may_write_registers or self.routines[node.value].may_services)
                   for node in self.walk_nodes(expr))

    def has_fresh_active_counters(self):
        if not self.current_routine: return False
        locals_only = {token.value for token, _ in self.current_routine.declarations}
        return self.active_counters <= locals_only

    def check_for_call(self, token, routine=None):
        if self.active_counters:
            if self.mode == 'strict' and not self.has_fresh_active_counters():
                self.error('E_FOR_COUNTER', 'Routine calls inside FOR require every active counter to be a fresh routine-local variable', token)
            if self.mode == 'pythonic' and routine is not None:
                locals_only = {t.value for t, _ in self.current_routine.declarations} if self.current_routine else set()
                conflict = (self.active_counters - locals_only) & routine.global_writes
                if conflict:
                    self.error('E_FOR_COUNTER', 'Routine may write active global FOR counter(s): ' + ', '.join(sorted(conflict)), token)
            if self.has_fresh_active_counters(): self.features.add('routine call inside FOR with fresh local counters')
            if self.mode == 'pythonic': self.features.add('routine call inside FOR with checked counter effects')

    def symbol_type(self, expr):
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
        while expr.kind in ('index', 'field', 'group'): expr = expr.args[0]
        return expr.value

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

    def access_type(self, expr):
        """Inspect receiver types without emitting calls or duplicate call-site reports."""
        if expr.kind == 'group': return self.access_type(expr.args[0])
        if self.mode=='pythonic' and expr.kind=='call' and expr.value in ex.FUNCTIONS and expr.value not in self.routines:
            return ex.FUNCTIONS[expr.value][1]
        if expr.kind == 'call' and expr.value in self.routines and self.routines[expr.value].return_type:
            return self.routines[expr.value].return_type
        if self.mode == 'pythonic' and expr.kind == 'call' and expr.value in PYTHONIC_CONSTRUCTORS and expr.value not in self.routines:
            if expr.value in ('INV','FRAME'):
                if (expr.value == 'INV' and len(expr.args) != 1 or expr.value == 'FRAME' and len(expr.args) not in (3,4)):
                    self.error('E_ARGUMENTS', 'INV requires one pose; FRAME requires three or four poses', expr.token)
                return self.frame_result_type([self.access_type(argument) for argument in expr.args], expr.token)
            if expr.value in rt.POSITION_AXIS_FUNCTIONS:
                if len(expr.args) != 1: self.error('E_ARGUMENTS', f'{expr.value} requires one pose', expr.token)
                self.frame_result_type([self.access_type(expr.args[0])], expr.token)
                return ('VECTOR',)
            return BUILTIN_SIGNATURES[expr.value][1]
        if self.mode == 'pythonic' and expr.kind == 'binary' and expr.value == ':':
            return self.frame_result_type([self.access_type(argument) for argument in expr.args], expr.token)
        if expr.kind == 'name': return self.symbol_type(expr)
        if expr.kind == 'field': return self.member_type(self.access_type(expr.args[0]), expr)
        if expr.kind == 'index':
            spec = self.access_type(expr.args[0])
            if spec[0]=='PATH': return rt.PathValue(spec).node_spec
            if spec[0] != 'ARRAY': self.error('E_TYPE', 'Indexing requires ARRAY', expr.token)
            try: return rt.indexed_type(spec, len(expr.args) - 1)
            except rt.KarelRuntimeError as exc: self.error('E_ARRAY_RANK', str(exc), expr.token)
        self.error('E_TYPE', 'Expected a variable receiver path', expr.token)

    def frame_result_type(self, specs, token):
        if self.mode=='pythonic': specs=[('XYZWPREXT',) if spec[0]=='JOINTPOS' else spec for spec in specs]
        if not specs or any(spec not in (('XYZWPR',), ('POSITION',),('XYZWPREXT',)) for spec in specs):
            self.error('E_TYPE', 'Frame operations require POSITION or XYZWPR operands', token)
        return ('XYZWPREXT',) if ('XYZWPREXT',) in specs else ('POSITION',) if ('POSITION',) in specs else ('XYZWPR',)

    def geometry_operand(self,code,spec,token,operation):
        if self.mode=='pythonic' and spec[0]=='JOINTPOS':
            self.features.update(('extended services','joint geometry'))
            if self.current_routine: self.current_routine.may_services=True
            self.joint_geometry_uses.append(dict(operation=operation,body=self.current_routine.name if self.current_routine else self.program.name,
                line=token.line,column=token.column,source_type=spec,target_type=('XYZWPREXT',),evaluated_once=True,independent_value=True))
            return f'self._state.geometry_value({code},{spec!r},{token.line})'
        return f'_rt.frame_value({code}, {token.line}, expected={spec!r})'

    def is_position_read_only_access(self, expr):
        """Check receiver paths, without mistaking an index expression for a target."""
        while expr.kind in ('field', 'index'):
            if expr.kind == 'field':
                parent_type = self.access_type(expr.args[0])
                if parent_type[0] == 'POSITION' and expr.value in rt.POSITION_READ_ONLY_FIELDS:
                    return True
            expr = expr.args[0]
            while expr.kind == 'group': expr = expr.args[0]
        return False

    def reference(self, expr):
        line = expr.token.line
        if expr.kind == 'name':
            return f'self._state.reference({expr.value!r}, {line})', self.symbol_type(expr)
        base, spec = self.expression(expr.args[0], raw=True)
        if expr.kind == 'field':
            member = self.member_type(spec, expr)
            return f'_rt.field_reference({base}, {expr.value!r}, {line})', member
        if spec[0]=='PATH':
            if len(expr.args)!=2: self.error('E_ARRAY_RANK','PATH requires one node index',expr.token)
            index=self.require_type(expr.args[1],'INTEGER')
            return f'_rt.index_reference({base},{index},{line})',rt.PathValue(spec).node_spec
        if spec[0] != 'ARRAY': self.error('E_TYPE', 'Indexing requires ARRAY', expr.token)
        index, selected = self.index_code(expr, spec)
        return f'_rt.index_reference({base}, {index}, {line})', selected

    def index_code(self, expr, spec):
        indexes = expr.args[1:]
        if expr.args[0].kind == 'index':
            self.error('E_ARRAY_RANK', 'Chained ARRAY indexes need grammar validation; use comma-separated subscripts', expr.token)
        try: selected = rt.indexed_type(spec, len(indexes))
        except rt.KarelRuntimeError as exc: self.error('E_ARRAY_RANK', str(exc), expr.token)
        if self.mode == 'strict' and len(indexes) > 1 and any(self.has_routine_call(index) for index in indexes):
            self.error('E_EVALUATION_ORDER', 'Multiple ARRAY subscripts containing routine calls need evaluation-order validation', expr.token)
        codes = [self.require_type(index, 'INTEGER') for index in indexes]
        if len(indexes) > 1: self.features.add('multidimensional ARRAY indexing')
        if selected[0] == 'ARRAY':
            self.features.add('named subarray reference')
            self.subarray_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                           line=expr.token.line, column=expr.token.column, supplied_subscripts=len(indexes),
                                           logical_rank=len(rt.array_dimensions(spec)), selected_type=rt.array_identity(selected)))
        code = codes[0] if len(indexes) == 1 else '(' + ', '.join(codes) + ')'
        return code, selected

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
        if None not in target_shape and None not in source_shape: return False
        target_leaf, source_leaf = rt.array_leaf_spec(target), rt.array_leaf_spec(source)
        elements_match = (target_leaf == source_leaf or
                          target_leaf[0] == source_leaf[0] == 'STRING'
                          and (target_leaf[1] is None or source_leaf[1] is None))
        return (elements_match and len(target_shape) == len(source_shape) and
                all(a == b or a is None or b is None for a, b in zip(target_shape, source_shape)))

    def expression(self, expr, raw=False, *, allow_array_result=False):
        if expr.kind=='captured': return expr.value
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
            return self.expression(expr.args[0], raw=raw)
        if expr.kind == 'real_literal':
            try: rt.real_literal(expr.value, line)
            except rt.KarelRuntimeError as exc: self.error('E_REAL_LITERAL', str(exc), expr.token)
            self.features.add('REAL literal' if self.mode == 'pythonic' else 'exact REAL literal')
            return f'_rt.real_literal({expr.value!r}, {line})', ('REAL',)
        if expr.kind == 'predefined':
            value = PREDEFINED_CONSTANTS[expr.value]
            if type(value) is bool: return repr(value), ('BOOLEAN',)
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
            if spec[0] != 'ARRAY': self.error('E_TYPE', 'Indexing requires ARRAY', expr.token)
            index, selected = self.index_code(expr, spec)
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
            if spec[0] in NARROW_TYPES: spec = ('INTEGER',)
            allowed = ('BOOLEAN', 'INTEGER') if expr.value == 'NOT' else ('INTEGER', 'REAL')
            if self.mode == 'pythonic' and expr.value in ('+', '-'):
                allowed += ('VECTOR',)
            if spec[0] not in allowed: self.error('E_TYPE', 'Invalid unary operand type', expr.token)
            self.features.add('unary ' + expr.value)
            return f'_rt.unary({expr.value!r}, {value}, {line})', spec
        if expr.kind == 'binary':
            if self.mode == 'strict' and self.has_external_effect_call(expr):
                self.error('E_EVALUATION_ORDER', 'Function calls that may write globals/reference parameters, delay, request output or abort are blocked inside operator expressions', expr.token)
            left, lt = self.expression(expr.args[0])
            right, right_type = self.expression(expr.args[1])
            if lt[0] in NARROW_TYPES: lt = ('INTEGER',)
            if right_type[0] in NARROW_TYPES: right_type = ('INTEGER',)
            op = expr.value
            if op == '>=<':
                valid = self.mode == 'pythonic' and all(spec[0] in ('XYZWPR','POSITION','XYZWPREXT','JOINTPOS') for spec in (lt,right_type))
                result_type = ('BOOLEAN',)
                if valid:
                    self.position_comparison_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                              line=line, column=expr.token.column, operand_types=[lt[0],right_type[0]],
                                                              result_type='BOOLEAN', evaluated_once=True, operands_copied=True))
            elif op == ':':
                valid = self.mode == 'pythonic' and all(spec[0] in ('XYZWPR','POSITION','XYZWPREXT','JOINTPOS') for spec in (lt,right_type))
                result_type = self.frame_result_type([lt,right_type], expr.token) if valid else ('XYZWPR',)
                if valid:
                    self.frame_operation_uses.append(dict(operation=':', body=self.current_routine.name if self.current_routine else self.program.name,
                                                          line=line, column=expr.token.column, operand_types=[lt[0],right_type[0]],
                                                          result_type=result_type[0], evaluated_once=True, operands_copied=True))
            elif 'VECTOR' in (lt[0], right_type[0]):
                both_vectors = lt == right_type == ('VECTOR',)
                scaled = (lt == ('VECTOR',) and right_type[0] in ('INTEGER', 'REAL')
                          or right_type == ('VECTOR',) and lt[0] in ('INTEGER', 'REAL'))
                valid = (both_vectors and op in ('+', '-', '#', '@', '=', '<>')
                         or scaled and op in ('*', '/'))
                result_type = ('BOOLEAN',) if op in ('=', '<>') else ('REAL',) if op == '@' else ('VECTOR',)
                if valid: self.features.add('VECTOR operator ' + op)
            elif op in ('=', '<>', '<', '<=', '>', '>='):
                valid = (lt[0] == right_type[0] and lt[0] in ('INTEGER', 'REAL', 'BOOLEAN', 'STRING')
                         or lt[0] in ('INTEGER', 'REAL') and right_type[0] in ('INTEGER', 'REAL'))
                result_type = ('BOOLEAN',)
            elif op in ('AND', 'OR'):
                valid = lt[0] == right_type[0] and lt[0] in ('INTEGER', 'BOOLEAN')
                result_type = lt
                if self.mode == 'strict' and lt[0] == 'BOOLEAN' and any(self.has_routine_call(x) for x in expr.args):
                    self.error('E_EVALUATION_ORDER', 'Boolean expressions containing routine calls are not implemented', expr.token)
            else:
                numeric = lt[0] in ('INTEGER', 'REAL') and right_type[0] in ('INTEGER', 'REAL')
                valid = (numeric and op in ('+', '-', '*', '/')
                         or lt[0] == right_type[0] == 'INTEGER' and op in ('DIV', 'MOD')
                         or op == '+' and lt[0] == right_type[0] == 'STRING')
                result_type = ('REAL',) if numeric and (op == '/' or 'REAL' in (lt[0], right_type[0])) else lt
            if not valid: self.error('E_TYPE', f'Unsupported {lt[0]} {op} {right_type[0]}', expr.token)
            self.features.add('operator ' + op)
            if self.mode == 'pythonic':
                if lt[0] == 'BOOLEAN' and op in ('AND', 'OR'):
                    return f'(_rt.boolean({left}, {line}) {op.lower()} _rt.boolean({right}, {line}))', result_type
                # Capture mutable values before a later operand can change them.
                if lt == ('VECTOR',): left = f'_rt.vector_value({left}, {line})'
                if right_type == ('VECTOR',): right = f'_rt.vector_value({right}, {line})'
                if op in (':','>=<'):
                    left = self.geometry_operand(left,lt,expr.args[0].token,op)
                    right = self.geometry_operand(right,right_type,expr.args[1].token,op)
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
            supported=('INTEGER','SHORT','BOOLEAN','REAL','STRING','JOINTPOS')+(DATA_RECORD_TYPES if self.mode=='pythonic' else ())
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
            if len(expr.args) != 1: self.error('E_ARGUMENTS', 'ARRAY_LEN requires exactly one argument', expr.token)
            code, spec = self.expression(expr.args[0])
            if spec[0] != 'ARRAY': self.error('E_TYPE', 'ARRAY_LEN requires ARRAY', expr.token)
            if self.mode == 'strict' and len(rt.array_dimensions(spec)) != 1:
                self.error('E_ARRAY_LEN', 'ARRAY_LEN on multidimensional arrays needs dimension-count semantics; use explicit dimensions', expr.token)
            result_type, codes = ('INTEGER',), [code]
        elif expr.value in rt.POSITION_AXIS_FUNCTIONS:
            if len(expr.args) != 1: self.error('E_ARGUMENTS', f'{expr.value} requires one pose', expr.token)
            code, axis_spec = self.expression(expr.args[0])
            self.frame_result_type([axis_spec], expr.args[0].token)
            codes = [self.geometry_operand(code,axis_spec,expr.args[0].token,expr.value)]
            result_type = ('VECTOR',)
        elif expr.value in ('INV','FRAME'):
            if (expr.value == 'INV' and len(expr.args) != 1 or expr.value == 'FRAME' and len(expr.args) not in (3,4)):
                self.error('E_ARGUMENTS', 'INV requires one pose; FRAME requires three or four poses', expr.token)
            codes, frame_specs = [], []
            for argument in expr.args:
                code, spec = self.expression(argument)
                self.frame_result_type([spec], argument.token)
                codes.append(self.geometry_operand(code,spec,argument.token,expr.value)); frame_specs.append(spec)
            result_type = self.frame_result_type(frame_specs, expr.token)
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
            self.pos_constructor_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                 line=expr.token.line, column=expr.token.column,
                                                 arguments_evaluated_once=True, argument_order=['x','y','z','w','p','r','c'],
                                                 result_type='XYZWPR', independent_value=True, configuration_copied=True))
        if expr.value == 'INV':
            self.frame_operation_uses.append(dict(operation='INV', body=self.current_routine.name if self.current_routine else self.program.name,
                                                  line=expr.token.line, column=expr.token.column, operand_types=[spec[0] for spec in frame_specs],
                                                  result_type=result_type[0], evaluated_once=True, operands_copied=True))
        if expr.value == 'FRAME':
            self.frame_operation_uses.append(dict(operation='FRAME', body=self.current_routine.name if self.current_routine else self.program.name,
                                                  line=expr.token.line, column=expr.token.column, operand_types=[spec[0] for spec in frame_specs],
                                                  result_type=result_type[0], evaluated_once=True, operands_copied=True,
                                                  origin_argument=4 if len(expr.args) == 4 else 1))
        if expr.value in rt.UNARY_TRIG_FUNCTIONS:
            self.trig_uses.append(dict(function=expr.value, body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=expr.token.line, column=expr.token.column, evaluated_once=True,
                                       runtime_exact_subset_guard=self.mode == 'strict', result_type='REAL'))
        if expr.value == 'ATAN2':
            self.atan2_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=expr.token.line, column=expr.token.column, argument_order=['x','y'],
                                       arguments_evaluated_once=True, runtime_exact_subset_guard=self.mode == 'strict', result_type='REAL'))
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
        if self.root_name(destination) in self.active_counters:
            self.error('E_FOR_COUNTER', 'Conversion cannot write an active FOR counter', destination.token)
        if self.is_position_read_only_access(destination):
            self.error('E_POSITION_READ_ONLY', 'POSITION orientation fields cannot be conversion outputs', destination.token)
        reference, actual = self.reference(destination)
        if self.is_config_subfield(destination):
            self.error('E_CONFIG_OUTPUT', 'CONFIG subfields have value-only routine passing; conversion output aliases remain blocked', destination.token)
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
        if len(expr.args) != count: self.error('E_ARGUMENTS', f'{expr.value} requires {count} arguments', expr.token)
        self.check_for_call(expr.token)
        source = self.require_type(expr.args[0], 'STRING' if parsing else 'CONFIG')
        if not parsing: source = f'_rt.positional_value(("CONFIG",), {source}, {expr.args[0].token.line})'
        outputs = []
        for argument, expected in zip(expr.args[1:], ('CONFIG','INTEGER') if parsing else ('STRING',)):
            base = argument
            while base.kind in ('field', 'index'): base = base.args[0]
            if argument.kind not in ('name', 'field', 'index') or base.kind != 'name' or base.value in self.visible_constants():
                self.error('E_OUTPUT_ARGUMENT', 'CONFIG conversion outputs require storage rooted in a variable', argument.token)
            if base.value in self.active_counters: self.error('E_FOR_COUNTER', 'CONFIG conversion cannot write an active FOR counter', argument.token)
            if self.is_position_read_only_access(argument): self.error('E_POSITION_READ_ONLY', 'CONFIG conversion output is read-only', argument.token)
            if self.is_config_subfield(argument): self.error('E_CONFIG_OUTPUT', 'CONFIG subfields cannot be conversion output aliases', argument.token)
            code, spec = self.reference(argument)
            if spec[0] != expected: self.error('E_TYPE', f'{expr.value} output requires {expected}', argument.token)
            outputs.append(code)
        self.features.add(expr.value)
        self.config_text_uses.append(dict(name=expr.value, body=self.current_routine.name if self.current_routine else self.program.name,
                                         line=expr.token.line, column=expr.token.column, arguments_evaluated_once=True,
                                         argument_order=['source','target','status'] if parsing else ['source','target'],
                                         outputs=2 if parsing else 1, source_copied=not parsing))
        return f'_rt.config_text_conversion({expr.value!r}, {source}, {", ".join(outputs)}, line={expr.token.line})'

    def service_call(self,expr):
        signature=ex.PROCEDURES.get(expr.value,ex.FUNCTIONS.get(expr.value,((),None))[0])
        minimum=len(signature)-(expr.value in ex.OPTIONAL_LAST or expr.value in ex.OPTIONAL_GROUP)
        if not minimum<=len(expr.args)<=len(signature): self.error('E_ARGUMENTS',f'{expr.value} requires {minimum}..{len(signature)} arguments',expr.token)
        signature=ex.signature_for(expr.value,len(expr.args))
        self.check_for_call(expr.token)
        if expr.value=='SET_VAR' and self.active_counters: self.error('E_FOR_COUNTER','SET_VAR cannot indirectly write an active FOR counter',expr.token)
        codes=[]
        for value,(mode,kind) in zip(expr.args,signature):
            discarded=value
            while discarded.kind=='group': discarded=discarded.args[0]
            if mode=='m' and discarded.kind=='literal' and type(discarded.value) is int and discarded.value==0:
                codes.append('0'); continue
            if mode in ('o','r','m'):
                if value.kind not in ('name','field','index') or self.root_name(value) in self.visible_constants(): self.error('E_OUTPUT_ARGUMENT','Service output requires writable storage',value.token)
                if self.root_name(value) in self.active_counters: self.error('E_FOR_COUNTER','Service output cannot write an active FOR counter',value.token)
                if self.is_position_read_only_access(value): self.error('E_POSITION_READ_ONLY','Service output is protected POSITION storage',value.token)
                if self.is_config_subfield(value): self.error('E_CONFIG_OUTPUT','CONFIG fields cannot be output aliases',value.token)
                code,spec=self.reference(value)
            else:
                code,spec=self.expression(value)
                if kind=='GEOMETRY_POSE' and spec[0]=='JOINTPOS': code=self.geometry_operand(code,spec,value.token,expr.value)
                if kind=='REAL' and spec[0] in INTEGRAL_TYPES: code=f'_rt.real({code},{value.token.line})'; spec=('REAL',)
                if kind=='INTEGER' and spec[0] in NARROW_TYPES: code=f'_rt.integer({code},{value.token.line})'; spec=('INTEGER',)
                if kind=='ANY' or spec[0] in (*RECORD_TYPES,'JOINTPOS','ARRAY'): code=f'_rt.assignment_value({code},{value.token.line})'
            if not ex.matches(spec,kind): self.error('E_TYPE',f'{expr.value} expects {kind}, found {spec[0]}',value.token)
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
            if target.kind not in ('name','field','index') or base.kind != 'name' or base.value in self.visible_constants():
                self.error('E_OUTPUT_ARGUMENT','Numeric register outputs require storage rooted in a variable',target.token)
            if base.value in self.active_counters: self.error('E_FOR_COUNTER','Numeric register output cannot write an active FOR counter',target.token)
            if self.is_position_read_only_access(target): self.error('E_POSITION_READ_ONLY','Numeric register output is read-only',target.token)
            if self.is_config_subfield(target): self.error('E_CONFIG_OUTPUT','CONFIG subfields cannot be numeric register output aliases',target.token)
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
        if destination.kind not in ('name','field','index') or base.kind != 'name' or base.value in self.visible_constants():
            self.error('E_OUTPUT_ARGUMENT','Time conversion output requires storage rooted in a variable',destination.token)
        if base.value in self.active_counters: self.error('E_FOR_COUNTER','Time conversion cannot write an active FOR counter',destination.token)
        if self.is_position_read_only_access(destination): self.error('E_POSITION_READ_ONLY','POSITION orientation cannot be a time conversion output',destination.token)
        if self.is_config_subfield(destination): self.error('E_CONFIG_OUTPUT','CONFIG subfields cannot be time conversion output aliases',destination.token)
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
            if self.root_name(output) in self.active_counters:
                self.error('E_FOR_COUNTER', 'Joint conversion cannot write an active FOR counter', output.token)
            if self.is_position_read_only_access(output):
                self.error('E_POSITION_READ_ONLY', 'Joint conversion output is read-only', output.token)
            if self.is_config_subfield(output):
                self.error('E_CONFIG_OUTPUT', 'CONFIG subfields cannot be joint-conversion output aliases', output.token)
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
                if self.root_name(argument) in self.active_counters:
                    self.error('E_FOR_COUNTER', 'UNPOS cannot write an active FOR counter', argument.token)
                if self.is_position_read_only_access(argument):
                    self.error('E_POSITION_READ_ONLY', 'UNPOS output cannot be a read-only POSITION orientation field', argument.token)
                if self.is_config_subfield(argument):
                    self.error('E_CONFIG_OUTPUT', 'CONFIG scalar subfields cannot be UNPOS outputs', argument.token)
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

    def routine_call(self, expr):
        routine = self.routines[expr.value]
        if len(expr.args) != len(routine.parameters):
            self.error('E_ARGUMENTS', f'{expr.value} expects {len(routine.parameters)} arguments, received {len(expr.args)}', expr.token)
        if self.mode == 'strict' and len(expr.args) > 1 and any(self.has_routine_call(arg) for arg in expr.args):
            self.error('E_EVALUATION_ORDER', 'Multiple arguments containing routine calls need evaluation-order validation', expr.token)
        arguments = []
        for argument, (formal, expected) in zip(expr.args, routine.parameters):
            line = argument.token.line
            if self.is_position_read_only_access(argument):
                self.error('E_POSITION_READ_ONLY_ARG', 'Bare POSITION orientation arguments need read-only passing evidence; use an explicit scalar expression for a value', argument.token)
            # Bare variable and indexed-variable arguments retain their storage.
            # Any grouping node, constant or expression is a temporary value.
            is_reference = argument.kind in ('name', 'index', 'field') and self.root_name(argument) not in self.visible_constants()
            if is_reference:
                code, actual = self.reference(argument)
                if self.is_config_subfield(argument):
                    value, actual = self.expression(argument)
                    code = f'_rt.value_argument({expected!r}, {value}, {line})'
                    is_reference = False
                    self.features.add('CONFIG subfield value argument')
                    self.config_value_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                       routine=routine.name, parameter=formal.value, field=argument.value,
                                                       line=line, column=argument.token.column, evaluated_once=True))
            else:
                value, actual = self.expression(argument)
                code = f'_rt.value_argument({expected!r}, {value}, {line})'
            if expected[0] in ('INTEGER', 'REAL') and actual[0] in NARROW_TYPES:
                narrow_type = actual[0]
                value, _ = self.expression(argument)
                code = f'_rt.value_argument({expected!r}, {value}, {line})'
                is_reference, actual = False, expected
                self.features.add(narrow_type + ' to ' + expected[0] + ' value argument')
            elif expected[0] == 'REAL' and actual[0] == 'INTEGER':
                value, _ = self.expression(argument)
                code = f'_rt.value_argument({expected!r}, {value}, {line})'
                is_reference, actual = False, expected
                self.features.add('INTEGER to REAL value argument')
            bounded_string_value = (not is_reference and expected[0] == actual[0] == 'STRING' and expected[1] is not None)
            if not rt.parameter_accepts(expected, actual) and not bounded_string_value:
                self.error('E_TYPE', f'{expr.value} parameter expects {expected[0]}, found {actual[0]}', argument.token)
            if is_reference and argument.kind == 'name' and argument.value in self.active_counters:
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
            if expected[0] in ('STRING', 'ARRAY', *RECORD_TYPES, 'JOINTPOS'):
                self.features.add(expected[0] + (' reference parameter' if is_reference else ' value parameter'))
            self.features.add('parameter by reference' if is_reference else 'parameter by value')
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

    def block(self, statements):
        if not statements: self.line('pass')
        for statement in statements: self.statement(statement)

    @staticmethod
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

    def validate_labels(self, statements):
        labels, jumps = {}, []
        conflicts = set(self.types) | set(self.visible_constants()) | set(self.user_types) | set(self.routines) | {self.program.name}
        if self.current_routine: conflicts.update(self.current_routine.local_types)

        def visit(body, path=(), inside_for=False):
            for stmt in body:
                if stmt.kind in ('label', 'goto'):
                    if inside_for:
                        self.error('E_GOTO_FOR', 'Labels and GO TO/GOTO inside FOR bodies are blocked by the documented FOR restrictions', stmt.token)
                    name = stmt.args[0].value
                    if stmt.kind == 'label':
                        if name in labels: self.error('E_DUPLICATE_LABEL', 'Duplicate label in the same body', stmt.token)
                        if name in conflicts: self.error('E_LABEL_CONFLICT', 'Label conflicts with a declared or predefined identifier', stmt.token)
                        labels[name] = (stmt.token, path)
                    else: jumps.append((stmt, path))
                for block_name, child in self.child_blocks(stmt):
                    visit(child, path + (block_name,), inside_for or stmt.kind == 'for')

        visit(statements)
        for stmt, source_path in jumps:
            name = stmt.args[0].value
            if name not in labels:
                self.error('E_LABEL', f'Label {name} is not defined in this program/routine body', stmt.args[0])
            target_path = labels[name][1]
            if source_path[:len(target_path)] != target_path:
                self.error('E_GOTO_ENTRY', 'Jumps into nested or sibling structured blocks need entry-state validation', stmt.token)
        return bool(labels or jumps)

    def case_values(self, stmt):
        result = []
        for _, values, _ in stmt.args[1]:
            resolved = []
            for expr in values:
                value = self.constant(expr)
                if type(value) is not int or not -2147483648 <= value <= 2147483647:
                    self.error('E_CASE', 'CASE values must be INTEGER constants', expr.token)
                resolved.append(value)
            result.append(tuple(resolved))
        return result

    def select_code(self, stmt):
        selector = self.require_type(stmt.args[0], 'INTEGER')
        cases = self.case_values(stmt)
        self.select_scopes.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=stmt.token.line, column=stmt.token.column, case_values=cases,
                                       case_count=len(cases), has_else=stmt.has_else,
                                       empty_else=stmt.has_else and not stmt.alternate,
                                       no_match='else_clause' if stmt.has_else else 'KarelRuntimeError'))
        self.features.add('SELECT first matching CASE')
        self.features.add('SELECT no-match guard')
        return f'_rt.select_case({selector}, {tuple(cases)!r}, {stmt.has_else!r}, {stmt.token.line})'

    def emit_body(self, statements):
        if not self.validate_labels(statements):
            report = dict(engine='structured_python', labels={})
            self.block(statements)
        else:
            graph = FlowGraph(statements)
            report = graph.report()
            self.features.add('label control-flow dispatcher')
            pc = self.fresh()
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
                if kind in ('label', 'goto', 'enter'):
                    self.features.add(stmt.kind)
                    if kind != 'label': self.line(f'self._state.tick({line})', token)
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
            self.line('case _:')
            self.indent += 1
            self.line('raise _rt.KarelRuntimeError("Invalid generated control-flow state")')
            self.indent -= 3
        if self.current_routine: self.control_flow['routines'][self.current_routine.name] = report
        else: self.control_flow['program'] = report

    def test_code(self,code,line):
        return f'(yield from _rt.cooperative_test(self._state,lambda: {code},{line}))' if self.cooperative else f'self._state.test({code},{line})'

    def implicit_counter_write(self, name):
        """Handlers and timers can run between ordinary source statements."""
        for body in (self.program.body, *[routine.body for routine in self.program.routines]):
            for node in self.walk_nodes(body):
                if not isinstance(node, Statement): continue
                if node.kind == 'timer_connect' and self.root_name(node.args[0]) == name: return True
                if node.kind != 'condition': continue
                for action in self.walk_nodes(node.body):
                    if isinstance(action, Statement) and action.kind == 'assign' and self.root_name(action.args[0]) == name: return True
                    if isinstance(action, Statement) and action.kind == 'read':
                        if any(self.root_name(item.args[0] if item.kind == 'read_item' else item) == name for item in action.args if item.kind != 'read_cr'): return True
                    if not isinstance(action, Expr) or action.kind != 'call': continue
                    if action.value == 'SET_VAR': return True
                    routine = self.routines.get(action.value)
                    if routine:
                        if name in routine.global_writes: return True
                        if any(token.value in routine.parameter_writes and self.root_name(value) == name for (token, _), value in zip(routine.parameters, action.args)): return True
                    signature = ex.signature_for(action.value,len(action.args))
                    if any(mode in ('o', 'r','m') and self.root_name(value) == name for value, (mode, _) in zip(action.args, signature)): return True
        return False

    def statement(self, stmt, file_code=None):
        token, kind = stmt.token, stmt.kind
        line = token.line
        self.features.add(kind)
        self.line(f'self._state.tick({line})', token)
        if kind=='pulse':
            if 'DOUT' in self.types or 'DOUT' in self.visible_constants(): self.error('E_PULSE','PULSE requires the unshadowed DOUT port bank',token)
            number=self.require_type(stmt.args[0],'INTEGER');duration=self.require_type(stmt.args[1],'INTEGER')
            self.features.update(('ports','extended services'))
            self.pulse_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                line=line,column=token.column,nowait=stmt.args[2],operands_evaluated_once=True))
            self.line(f'yield from _rt.pulse_execution(self._state,{number},{duration},{stmt.args[2]!r},{line})',token);return
        if kind=='task_control':
            action=stmt.args[0]
            if len(stmt.args)>1:
                number=self.require_type(stmt.args[1],'INTEGER')
                self.line(f'yield from _rt.control_task(self._state,{action!r},{number},{line})',token); return
            if action=='PAUSE': self.line(f'yield from _rt.pause_execution(self._state,{line})',token)
            elif action=='STOP': self.line('raise _rt.KarelStop("Task stopped")',token)
            else:
                self.line('self._state._pause_requested=False',token)
                if action=='CONTINUE':
                    self.line("self._state._lifecycle['CONTINUE']+=1",token)
                    self.line(f'yield from _rt.checkpoint(self._state,{line})',token)
            return
        if kind=='signal_event':
            number=self.require_type(stmt.args[0],'INTEGER')
            self.line(f'_rt.signal_event(self._state,{number},{line})',token)
            self.line(f'yield from _rt.checkpoint(self._state,{line})',token); return
        if kind=='signal_semaphore':
            number=self.require_type(stmt.args[0],'INTEGER'); self.features.add('extended services')
            self.line(f'self._state.extended_call("POST_SEMA",[{number}],{line})',token)
            self.line(f'yield from _rt.checkpoint(self._state,{line})',token); return
        if kind=='handler_action':
            self.line(f'_rt.handler_action(self._state,{stmt.args[0]!r},{line})',token); return
        if kind in ('timer_connect','timer_disconnect'):
            target=stmt.args[0]
            if self.current_routine and self.root_name(target) in self.current_routine.local_types: self.error('E_TIMER_SCOPE','Connected timer storage must be global',target.token)
            if self.root_name(target) in self.active_counters: self.error('E_FOR_COUNTER','Timer cannot modify active FOR counter',target.token)
            reference,spec=self.reference(target)
            if spec!=('INTEGER',) or self.is_config_subfield(target): self.error('E_TYPE','Timer requires ordinary INTEGER storage',target.token)
            method='connect_timer' if kind=='timer_connect' else 'disconnect_timer'
            self.line(f'_rt.{method}(self._state,{reference},{line})',token); return
        if kind=='condition_control':
            number=self.require_type(stmt.args[1],'INTEGER')
            self.line(f'_rt.condition_control(self._state,{stmt.args[0]!r},{number},{line})',token); return
        if kind=='condition':
            number=self.require_type(stmt.args[0],'INTEGER'); pairs=[]
            for clause in stmt.body:
                for item in reversed(list(self.walk_nodes([*clause.args,*clause.body]))):
                    if isinstance(item,Expr) and item.kind=='eval':
                        code,spec=self.expression(item.args[0]); temporary=self.fresh()
                        self.line(f'{temporary}=_rt.assignment_value({code},{item.token.line})',item.token)
                        item.kind='captured'; item.value=(temporary,spec); item.args=[]
                for action_node in self.walk_nodes(clause.body):
                    if isinstance(action_node,Statement) and action_node.kind in ('label','goto','return','condition'):
                        self.error('E_CONDITION_ACTION','Handler actions cannot define handlers, jump or RETURN',action_node.token)
                predicate=self.fresh(); action=self.fresh()
                condition=self.require_type(clause.args[0],'BOOLEAN')
                self.line(f'def {predicate}():'); self.indent+=1; self.line(f'return {condition}'); self.indent-=1
                self.line(f'def {action}():'); self.indent+=1; self.line('if False: yield None')
                self.block(clause.body); self.indent-=1; pairs.append(f'({predicate},{action})')
            scan=self.require_type(stmt.args[1],'INTEGER') if len(stmt.args)>1 else '0'
            self.line(f'_rt.define_condition(self._state,{number},[{", ".join(pairs)}],{line},scan_ms={scan})',token); return
        if kind in ('file_read','file_write'):
            file_value=self.require_type(stmt.args[0],'FILE'); captured_file=self.fresh()
            self.line(f'{captured_file}={file_value}',token); self.features.add('memory files')
            self.statement(stmt.args[1],file_code=captured_file); return
        if kind in ('file_open','file_close'):
            file_value=self.require_type(stmt.args[0],'FILE'); self.features.add('memory files')
            if kind=='file_open':
                mode=self.require_type(stmt.args[1],'STRING'); name=self.require_type(stmt.args[2],'STRING')
                self.line(f'self._state.file_open({file_value},{mode},{name},{line})',token)
            else: self.line(f'self._state.file_close({file_value},{line})',token)
            return
        if kind == 'assign':
            target, expr = stmt.args
            if self.mode=='pythonic' and target.kind=='index' and target.args[0].kind=='name' and target.args[0].value in ex.PORT_TYPES and target.args[0].value not in self.types:
                kind=target.args[0].value
                if kind not in ex.OUTPUT_PORTS: self.error('E_PORT_DIRECTION','Cannot assign an input port',target.token)
                value=self.require_type(expr,ex.PORT_TYPES[kind]); temp=self.fresh(); self.line(f'{temp}={value}',token)
                if len(target.args)!=2: self.error('E_ARGUMENTS','Ports require one index',target.token)
                index=self.require_type(target.args[1],'INTEGER'); self.features.add('ports')
                self.line(f'self._state.port_write({kind!r},{index},{temp},{line})',token); return
            root = self.root_name(target)
            if root in self.visible_constants(): self.error('E_CONST_ASSIGN', 'Cannot assign to CONST', target.token)
            if root in self.active_counters: self.error('E_FOR_COUNTER', 'FOR counter writes inside its loop are blocked', target.token)
            if self.mode == 'strict' and self.has_routine_call(target):
                self.error('E_EVALUATION_ORDER', 'Routine calls in assignment target indexes need evaluation-order validation', target.token)
            if self.mode == 'strict' and any(isinstance(node, Expr) and node.kind == 'index' for node in self.walk_nodes(target)) and self.has_external_effect_call(expr):
                self.error('E_EVALUATION_ORDER', 'Effectful function results assigned to indexed targets need target/value evaluation-order validation', target.token)
            if self.is_position_read_only_access(target):
                self.error('E_POSITION_READ_ONLY', 'POSITION NORMAL, ORIENT and APPROACH fields and their components are read-only', target.token)
            reference, target_type = self.reference(target)
            value, value_type = self.expression(expr, allow_array_result=True)
            if (self.mode=='pythonic' and ((target_type[0]=='JOINTPOS' and value_type[0] in ('POSITION','XYZWPR','XYZWPREXT')) or (value_type[0]=='JOINTPOS' and target_type[0] in ('POSITION','XYZWPR','XYZWPREXT')))):
                value=f'self._state.kinematic_assignment({target_type!r},{value},{line})'
                self.features.update(('extended services','kinematic assignment'))
                if self.current_routine: self.current_routine.may_services=True
                self.kinematic_assignment_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                    line=line,column=token.column,source_type=value_type,target_type=target_type,target_kind=target.kind,
                    evaluated_once=True,independent_value=True))
            elif (self.mode == 'pythonic' and target_type!=value_type and target_type[0] in ('POSITION','XYZWPR','XYZWPREXT') and value_type[0] in ('POSITION','XYZWPR','XYZWPREXT')):
                value = f'_rt.convert_position({target_type!r}, {value}, {line})'
                self.features.add('POSITION/XYZWPR assignment conversion')
                self.position_conversion_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                          line=line, column=token.column, source_type=value_type[0], target_type=target_type[0],
                                                          target_kind=target.kind, evaluated_once=True, independent_value=True))
            elif not self.compatible(target_type, value_type):
                self.error('E_TYPE', f'Cannot assign {value_type} to {target_type}', token)
            result_expr = expr
            if self.mode == 'pythonic':
                while result_expr.kind == 'group': result_expr = result_expr.args[0]
            if result_expr.kind == 'call' and value_type[0] == 'ARRAY':
                self.features.add('direct ARRAY result assignment')
                self.array_result_assignments.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                                          routine=result_expr.value, line=line, column=token.column,
                                                          target_kind=target.kind, target_type=target_type,
                                                          evaluated_once=True, runtime_exact_type_and_size=True))
            if target_type[0] == 'STRUCTURE': self.features.add('whole STRUCTURE assignment')
            if target_type[0] in DATA_RECORD_TYPES: self.features.add('whole ' + target_type[0] + ' data copy')
            if self.mode == 'pythonic':
                temporary = self.fresh()
                self.line(f'{temporary} = _rt.assignment_value({value}, {line})', token)
                value = temporary
            self.line(f'{reference}.set({value}, {line})', token)
        elif kind == 'using':
            self.block(stmt.body)  # Qualified fields need no dynamic runtime scope.
        elif kind == 'abort':
            if self.mode == 'strict' and self.active_counters and not self.has_fresh_active_counters():
                self.error('E_FOR_COUNTER', 'ABORT inside FOR requires fresh routine-local counters; observable counter state on abort is unvalidated', token)
            self.line(f'yield from _rt.abort_execution(self._state,{line})' if self.cooperative else f'self._state.abort({line})', token)
            self.features.add('ABORT')
            self.abort_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=line, column=token.column, scope='current offline execution'))
        elif kind == 'delay':
            duration = self.require_type(stmt.args[0], 'INTEGER')
            self.line(f'yield from _rt.delay_execution(self._state,{duration},{line})' if self.cooperative else f'self._state.delay({duration}, {line})', token)
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
            pieces, items = [], []
            for item in stmt.args:
                if item.kind == 'write_cr':
                    pieces.append(repr('\n'))
                    items.append(dict(data_type='CR', line=item.token.line, column=item.token.column,
                                      format_specifiers=[]))
                    continue
                value, spec = self.expression(item.args[0])
                data_type = spec[0]
                if data_type not in ('STRING', 'BOOLEAN', 'INTEGER', 'REAL', *NARROW_TYPES):
                    self.error('E_TYPE', f'WRITE requires scalar data, found {data_type}', item.token)
                format_exprs = item.args[1:]
                format_codes = [self.require_type(expr, 'INTEGER') for expr in format_exprs]
                literals = [self.format_literal(expr) for expr in format_exprs]
                formats = [literal if literal is not None else dict(expression=True, line=expr.token.line,
                            column=expr.token.column) for literal, expr in zip(literals, format_exprs)]
                width = literals[0] if literals else None
                second = literals[1] if len(literals) == 2 else None
                if width is not None and (width < 0 or data_type != 'STRING' and width > 254):
                    self.error('E_WRITE_FORMAT', 'WRITE width must be nonnegative; numeric/BOOLEAN widths are limited to 254', format_exprs[0].token)
                if data_type == 'BOOLEAN' and len(format_exprs) == 2:
                    self.error('E_WRITE_FORMAT', 'BOOLEAN WRITE accepts only a width', format_exprs[1].token)
                if second is not None:
                    valid = (data_type == 'STRING' and second in (0, 1, 2, 3)
                             or data_type == 'REAL' and -254 <= second <= 254
                             or data_type in INTEGRAL_TYPES and second in (0, *range(2, 17)))
                    if not valid:
                        self.error('E_WRITE_FORMAT', f'Invalid {data_type} WRITE second format specifier', format_exprs[1].token)
                pieces.append(f'_rt.file_piece({file_code},{data_type!r},{value},[{", ".join(format_codes)}],{item.token.line})' if file_code else f'_rt.format_write_item({data_type!r}, {value}, [{", ".join(format_codes)}], {item.token.line})')
                items.append(dict(data_type=data_type, line=item.token.line, column=item.token.column,
                                  format_specifiers=formats, dynamic_formats=any(x is None for x in literals)))
                self.features.add(f'WRITE {data_type} output request')
                if formats: self.features.add(f'WRITE {data_type} formatting')
            file_option=f',file={file_code}' if file_code else ''
            self.line(f'self._state.write_items([{", ".join(pieces)}], {line}{file_option})', token)
            self.features.add('WRITE output request')
            if any(item['data_type'] == 'CR' for item in items): self.features.add('WRITE CR newline')
            if len(items) > 1: self.features.add('WRITE multiple data items')
            self.write_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                        line=token.line, column=token.column,
                                        data_type=items[0]['data_type'] if len(items) == 1 else 'MIXED',
                                        data_items=len(items), items=items, evaluated='Left to right, once per expression: value, width, second format; validate/render each item before the next; one request after complete rendering',
                                        format_specifiers=items[0]['format_specifiers'] if len(items) == 1 else []))
            if len(items) == 1 and items[0]['data_type'] != 'CR':
                formats = items[0]['format_specifiers']
                width = formats[0] if formats else None
                is_string = items[0]['data_type'] == 'STRING'
                alignment = formats[1] if is_string and len(formats) == 2 else 0
                dynamic_width = isinstance(width, dict)
                dynamic_alignment = isinstance(alignment, dict)
                self.write_uses[-1].update(
                    format_width=width, alignment='dynamic' if dynamic_alignment else 'right' if not is_string or alignment in (1, 3) else 'left',
                    quoted='dynamic' if dynamic_alignment else is_string and alignment in (2, 3),
                    width_policy=('dynamic' if dynamic_width or dynamic_alignment else
                                  'contents_length' if is_string and width is not None and (width == 0 or width > 254)
                                  else 'fixed' if is_string and formats else 'minimum' if formats else 'unformatted'))
        elif kind == 'write':
            value, spec = self.expression(stmt.args[0])
            data_type = spec[0]
            if data_type not in ('STRING', 'BOOLEAN', 'INTEGER'):
                self.error('E_TYPE', f'WRITE requires STRING or unformatted BOOLEAN/INTEGER, found {data_type}', stmt.args[0].token)
            formats = stmt.args[1]
            width = formats[0] if formats else None
            alignment = formats[1] if len(formats) == 2 else 0
            if data_type in ('BOOLEAN', 'INTEGER'):
                if formats:
                    self.error('E_WRITE_FORMAT', f'{data_type} WRITE formatting is not implemented; use the unformatted default', stmt.args[2][0])
                self.line(f'self._state.write_{data_type.lower()}({value}, {line})', token)
                evaluated = ('once; initialization/INTEGER/nonnegative guard before request' if data_type == 'INTEGER'
                             else 'once; initialization/BOOLEAN guard before request')
            else:
                if alignment in (2, 3) and not 1 <= width <= 254:
                    self.error('E_WRITE_FORMAT', 'Quoted WRITE requires literal width 1..254; quoted width fallback is not implemented', stmt.args[2][0])
                options = f', width={width}, alignment={alignment}' if formats else ''
                self.line(f'self._state.write_string({value}, {line}{options})', token)
                evaluated = 'once; ASCII/length guard before formatting/request'
                if formats: self.features.add('WRITE STRING formatting')
            self.features.add(f'WRITE {data_type} output request')
            self.write_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                        line=token.line, column=token.column, data_type=data_type,
                                        data_items=1, evaluated=evaluated,
                                        format_specifiers=formats, format_width=width,
                                        alignment='right' if alignment in (1, 3) else 'left',
                                        quoted=alignment in (2, 3),
                                        width_policy=('contents_length' if width == 0 or (width is not None and width > 254)
                                                      else 'fixed' if formats else 'unformatted')))
        elif kind == 'read':
            references, destinations, line_breaks = [], [], []
            formatted = any(item.kind == 'read_item' for item in stmt.args)
            for item in stmt.args:
                if item.kind == 'read_cr':
                    line_breaks.append(len(references))
                    continue
                target = item.args[0] if item.kind == 'read_item' else item
                format_exprs = item.args[1:] if item.kind == 'read_item' else []
                base = target
                while base.kind in ('field', 'index'): base = base.args[0]
                if target.kind not in ('name', 'field', 'index') or base.kind != 'name':
                    self.error('E_READ_ITEM', 'READ requires scalar storage rooted in a variable', target.token)
                root = self.root_name(target)
                if root in self.visible_constants(): self.error('E_CONST_ASSIGN', 'READ cannot write CONST', target.token)
                if root in self.active_counters: self.error('E_FOR_COUNTER', 'READ cannot write an active FOR counter', target.token)
                if self.is_position_read_only_access(target):
                    self.error('E_POSITION_READ_ONLY', 'READ cannot write POSITION orientation fields', target.token)
                if self.is_config_subfield(target):
                    self.error('E_CONFIG_OUTPUT', 'READ into CONFIG subfields needs a separate bounded output policy', target.token)
                reference, spec = self.reference(target)
                if spec[0] not in (*INTEGRAL_TYPES, 'BOOLEAN', 'REAL', 'STRING'):
                    self.error('E_READ_TYPE', 'READ supports INTEGER/BOOLEAN/REAL/STRING and narrow scalar elements/fields', target.token)
                format_codes = [self.require_type(expr, 'INTEGER') for expr in format_exprs]
                literals = [self.format_literal(expr) for expr in format_exprs]
                if literals and literals[0] is not None and not 0 <= literals[0] <= 254:
                    self.error('E_READ_FORMAT', 'READ width must be in 0..254', format_exprs[0].token)
                if len(literals) == 2 and literals[1] is not None:
                    second = literals[1]
                    valid = (spec[0] in ('BOOLEAN', 'REAL') or spec[0] == 'STRING' and second in (0, 2)
                             or spec[0] in INTEGRAL_TYPES and second in (0, *range(2, 17)))
                    if not valid: self.error('E_READ_FORMAT', f'Invalid {spec[0]} READ second format specifier', format_exprs[1].token)
                references.append(f'_rt.capture_read_target({reference}, [{", ".join(format_codes)}], {line})'
                                  if formatted else reference)
                destinations.append(dict(root=root, expression_kind=target.kind, type_spec=spec,
                                         line=target.token.line, column=target.token.column))
                if format_exprs:
                    destinations[-1].update(format_specifiers=[literal if literal is not None else dict(expression=True,
                        line=expr.token.line, column=expr.token.column) for literal, expr in zip(literals, format_exprs)],
                        dynamic_formats=any(value is None for value in literals))
                    self.features.add(f'READ {spec[0]} formatting')
            controls = f', line_breaks={tuple(line_breaks)!r}' if line_breaks else ''
            reader=f'self._state.file_read({file_code},' if file_code else 'self._state.read_items('
            if formatted:
                captured = self.fresh()
                self.line(f'{captured} = [{", ".join(references)}]', token)
                self.line(f'{reader}[item[0] for item in {captured}], {line}{controls}, formats=[item[1] for item in {captured}])', token)
            else:
                self.line(f'{reader}[{", ".join(references)}], {line}{controls})', token)
            self.read_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=line, column=token.column, destinations=destinations,
                                       targets_evaluated_once=True, response_validated_before_assignment=True))
            if line_breaks: self.read_uses[-1]['line_breaks'] = line_breaks
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
            counter, initial, final, direction = stmt.args
            if self.cooperative and self.implicit_counter_write(counter.value):
                self.error('E_FOR_COUNTER', 'Condition action or connected timer may modify this FOR counter', counter)
            counter_types = self.types | (self.current_routine.local_types if self.current_routine else {})
            if counter.value not in counter_types or counter_types[counter.value][0] != 'INTEGER':
                self.error('E_FOR_COUNTER', 'FOR counter must be an INTEGER variable', counter)
            if self.current_routine and self.current_routine.parameters and counter.value not in {t.value for t, _ in self.current_routine.declarations}:
                self.error('E_FOR_COUNTER', 'Parameterized routines require a fresh local FOR counter until alias effects are validated', counter)
            if counter.value in self.active_counters:
                self.error('E_FOR_COUNTER', 'Nested loops cannot share the same FOR counter', counter)
            first = self.require_type(initial, 'INTEGER')
            last = self.require_type(final, 'INTEGER')
            if self.mode == 'strict' and (self.has_routine_call(initial) or self.has_routine_call(final)):
                self.error('E_EVALUATION_ORDER', 'FOR bounds with routine calls are blocked', token)
            stop, item = self.fresh(), self.fresh()
            # Manual: initialize count before final is evaluated (final may read count).
            self.line(f'self._state.set({counter.value!r}, {first}, {line})')
            if self.mode == 'pythonic':
                self.line('try:')
                self.indent += 1
            self.line(f'{stop} = {last}')
            adjustment, step = (1, 1) if direction == 'TO' else (-1, -1)
            self.line(f'for {item} in range(self._state.get({counter.value!r}), {stop} + ({adjustment}), {step}):')
            self.indent += 1
            self.line(f'self._state.tick({line})')
            self.line(f'self._state.set({counter.value!r}, {item}, {line})')
            self.active_counters.add(counter.value)
            self.block(stmt.body)
            self.active_counters.remove(counter.value)
            self.indent -= 1
            if self.mode == 'pythonic':
                self.indent -= 1
                self.line('finally:')
                self.indent += 1
                self.line(f'self._state.clear({counter.value!r})')
                self.indent -= 1
            else:
                self.line(f'self._state.clear({counter.value!r})')
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
            expr = stmt.args[0]
            if self.current_routine is None:
                self.error('E_RETURN', 'RETURN is only implemented inside routines', token)
            if self.active_counters:
                if self.mode == 'strict' and not self.has_fresh_active_counters():
                    self.error('E_FOR_COUNTER', 'RETURN inside FOR requires every active counter to be a fresh routine-local variable', token)
                if self.has_fresh_active_counters(): self.features.add('RETURN from FOR with fresh local counters')
                if self.mode == 'pythonic': self.features.add('RETURN from FOR with counter cleanup')
            spec = self.current_routine.return_type
            if spec is None:
                if expr: self.error('E_RETURN', 'Procedure RETURN cannot return a value', token)
                self.line('return', token)
            else:
                if not expr: self.error('E_RETURN', 'Function RETURN requires a value', token)
                value, value_type = self.expression(expr)
                if not self.compatible(spec, value_type): self.error('E_RETURN', 'Wrong function return type', token)
                if spec[0] == 'ARRAY':
                    source = expr
                    while source.kind == 'group': source = source.args[0]
                    sources = ('name', 'field', 'index', 'call') if self.mode == 'pythonic' else ('name', 'field', 'index')
                    wrong_identity = (rt.array_identity(value_type) is not None and
                                      (self.mode == 'strict' or rt.array_identity(value_type) != rt.array_identity(spec)))
                    expected_outer_rank = len(rt.array_shape(spec)) if self.mode == 'pythonic' else 1
                    if (source.kind not in sources or value_type[0] != 'ARRAY'
                            or wrong_identity or len(rt.array_shape(value_type)) != expected_outer_rank
                            or (value_type[2] != spec[2] and not
                                (spec[2][0] == 'STRING' and value_type[2] == ('STRING', None)))):
                        self.error('E_ARRAY_RETURN_SOURCE', 'ARRAY RETURN requires matching outer representation, nominal identity and exact element type', expr.token)
                    self.array_return_uses.append(dict(routine=self.current_routine.name, element_type=spec[2][0], element_spec=spec[2], line=line,
                                                       column=token.column, expression_kind=expr.kind,
                                                       logical_rank=len(rt.array_dimensions(spec)),
                                                       result_spec=spec, declared_dimensions=rt.array_shape(spec), nominal_identity=rt.array_identity(spec),
                                                       independent_copy=True, initialized_elements_required=True))
                    self.line(f'return _rt.array_result({spec!r}, {value}, {line})', token)
                elif spec[0] == 'STRING':
                    self.string_return_uses.append(dict(routine=self.current_routine.name, capacity=spec[1],
                                                       capacity_defaulted=self.current_routine.string_result_defaulted,
                                                       line=line, column=token.column, expression_kind=expr.kind,
                                                       evaluated_once=True, right_truncation=True))
                    self.line(f'return _rt.checked({spec!r}, {value}, {line})', token)
                elif spec == ('VECTOR',):
                    self.vector_return_uses.append(dict(routine=self.current_routine.name, line=line, column=token.column,
                                                       expression_kind=expr.kind, independent_writable_copy=True))
                    self.line(f'return _rt.vector_value({value}, {line})', token)
                elif spec[0] == 'STRUCTURE':
                    self.structure_return_uses.append(dict(routine=self.current_routine.name, type_name=spec[1], line=line,
                                                          column=token.column, expression_kind=expr.kind, independent_writable_copy=True))
                    self.line(f'return _rt.structure_value({spec!r}, {value}, {line})', token)
                elif spec[0] in POSITIONAL_VALUE_TYPES:
                    self.positional_return_uses.append(dict(routine=self.current_routine.name, type_spec=spec, line=line,
                                                           column=token.column, expression_kind=expr.kind, independent_writable_copy=True))
                    self.line(f'return _rt.positional_value({spec!r}, {value}, {line})', token)
                else:
                    self.line(f'return _rt.checked({spec!r}, {value}, {line})', token)
        else: self.error('E_INTERNAL', f'Unexpected statement {kind}', token)

    def emit(self):
        self.validate_symbols()
        self.line(f'# Generated by karel2py {__version__}; offline prototype, not controller-equivalence proof.')
        self.line('from karel2py import runtime as _rt')
        self.line()
        self.line('class Program:')
        self.indent = 1
        self.line(f'source_program = {self.program.name!r}')
        self.line(f'translation_mode = {self.mode!r}')
        self.line(f'source_directives = {tuple((row["name"], row["argument"]) for row in self.program.directive_metadata)!r}')
        self.line(f'source_groups = {tuple(sorted(set(row["group"] for row in self.group_uses)))!r}')
        self.line(f'imported_variables = {tuple(self.program.imported_variables)!r}')
        self.line(f'routine_interfaces = { {r.name:dict(parameters=tuple(spec for _,spec in r.parameters),result=r.return_type,external=r.external) for r in self.program.routines}!r}')
        self.line(f'external_array_shapes = {tuple(self.array_shapes.items())!r}')
        self.line(f'@_rt._with_numeric_mode({self.mode!r})')
        self.line('def __init__(self, *, sleep=None, write=None, read=None, joint_axes=None, pose_tolerance=None, external_tolerance=None, clock_us=None, registers=None, context=None):')
        self.indent = 2
        self.line(f'self._state = _rt.State({self.types!r}, {self.constants!r}, sleep=sleep, write=write, read=read, joint_axes=joint_axes, pose_tolerance=pose_tolerance, external_tolerance=external_tolerance, clock_us=clock_us, registers=registers, context=context)')
        self.line(f'self._state.program_name={self.program.name!r}')
        self.line('self._state.program=self')
        self.line('if len(self.source_groups)==1: self._state.robot_group=self.source_groups[0]')
        self.line('self._state.execution.variables.attach(self.source_program,self._state)')
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
            self.line('def pause(self):'); self.indent=2; self.line('self._state._pause_requested=True'); self.indent=1
            self.line('def stop(self):'); self.indent=2; self.line('return _rt.stop_cooperative(self)'); self.indent=1
            self.line('@property'); self.line('def task_state(self):'); self.indent=2; self.line('return self._state.task_state'); self.indent=1
        self.line(f'@_rt._with_numeric_mode({self.mode!r})')
        self.line('def _execute(self):' if self.cooperative else 'def run(self, *, max_steps=100000):')
        self.indent = 2
        if self.cooperative: self.line('if False: yield None')
        if not self.cooperative: self.line('self._state.begin(max_steps)')
        if self.cooperative: self.line('try:'); self.indent+=1
        self.emit_body(self.program.body)
        if self.cooperative:
            self.indent-=1; self.line('except _rt.KarelRuntimeError as _failure:'); self.indent+=1
            self.line('yield from _rt.runtime_failure(self._state,_failure)'); self.line('raise'); self.indent-=1
        self.line('return self._state.snapshot()')
        self.indent = 0
        self.line()
        self.line('if __name__ == "__main__":')
        self.indent = 1
        if self.features & (JOINT_PROCEDURES | REGISTER_PROCEDURES) or self.features & {'read','operator >=<','extended services','ports','memory files'}:
            self.line('import argparse as _argparse')
            self.line('_parser = _argparse.ArgumentParser(description="Explicit offline execution context; no controller connection")')
            if self.features & JOINT_PROCEDURES:
                self.line('_parser.add_argument("--joint-axes", type=int, choices=range(1, 10), required=True)')
            if self.features & REGISTER_PROCEDURES:
                self.line('_parser.add_argument("--registers", required=True, help="UTF-8 JSON with explicit count and initial numeric register values")')
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
            self.line('_parser.add_argument("--filesystem-root", help="Explicit directory for FILE operations")')
            self.line('_parser.add_argument("--state-out", help="Save offline banks and global values as JSON")')
            if 'operator >=<' in self.features:
                self.line('_parser.add_argument("--external-axis-tolerances", type=float, nargs=3, help="Explicit tolerances for EXT1, EXT2, EXT3")')
            self.line('_args = _parser.parse_args()')
            self.line('import json as _json')
            self.line('_context = None')
            self.line('if _args.context is not None:')
            self.indent += 1
            self.line('try:')
            self.indent += 1
            self.line('with open(_args.context, encoding="utf-8-sig") as _stream: _context = _rt.ExecutionContext.from_config(_json.load(_stream))')
            self.indent -= 1
            self.line('except (OSError, KeyError, TypeError, ValueError, _rt.KarelRuntimeError) as _error:')
            self.indent += 1
            self.line('_parser.error("Invalid service context: "+str(_error))')
            self.indent -= 2
            self.line('if _args.filesystem_root is not None or _args.state_out is not None:')
            self.indent += 1
            self.line('if _context is None: _context = _rt.ExecutionContext()')
            self.line('if _args.filesystem_root is not None: _context.files = _rt.DirectoryFiles(_args.filesystem_root)')
            self.indent -= 1
            if self.features & REGISTER_PROCEDURES:
                self.line('import json as _json')
                self.line('try:')
                self.indent += 1
                self.line('with open(_args.registers, encoding="utf-8-sig") as _stream:')
                self.indent += 1
                self.line('_registers = _rt.NumericRegisters.from_config(_json.load(_stream))')
                self.indent -= 2
                self.line('except (OSError, TypeError, ValueError, _rt.KarelRuntimeError) as _error:')
                self.indent += 1
                self.line('_parser.error("Unable to load numeric registers: " + str(_error))')
                self.indent -= 1
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
            self.line('print(_program.run())')
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


def _translate(source, *, filename='<input>', array_shapes=None, mode='strict', cooperative=False):
    parser = Parser(source, filename, mode)
    program = parser.parse()
    emitter = Emitter(program, filename, array_shapes, mode, cooperative)
    if parser.continuations:
        emitter.features.add('physical line continuation')
    if parser.escaped_string_literals:
        emitter.features.add('doubled apostrophe STRING literal')
    emitter.features.update('predefined ' + use['name'] for use in parser.predefined_uses)
    generated = emitter.emit()
    if emitter.kinematic_assignment_uses or emitter.joint_geometry_uses: emitter.analyze_routine_effects()
    return Translation(generated, dict(
        status='translated', translator_version=__version__, filename=filename,
        cooperative_execution=emitter.cooperative,
        group_declarations=emitter.group_uses,
        program=program.name, source_sha256=hashlib.sha256(source.encode('utf-8')).hexdigest(),
        translation_context=dict(mode=mode, array_shapes={key: list(shape) for key, shape in emitter.array_shapes.items()}),
        translation_context_sha256=hashlib.sha256(json.dumps(dict(mode=mode, array_shapes={key: list(shape) for key, shape in emitter.array_shapes.items()}), sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest(),
        variable_array_policy=dict(declarations='Direct global VAR ARRAY dimensions containing *; one to three outer/logical dimensions, each positive and explicit',
                                   context='translate(array_shapes={name: dimensions}) supplies all outer dimensions, including fixed ones which must agree; case-insensitive names, no unused entries',
                                   specialization='Validated dimensions are embedded as concrete generated storage and immutable Program.external_array_shapes metadata; a different shape requires retranslation',
                                   initialization='Fresh offline storage retains existing uninitialized/unknown markers; dimensions do not provide values or persistent controller state',
                                   boundary='No inference from existing variables, VR files or KCL; no zero/unresolved dimensions, TYPE/field/local wildcards, resizing, dynamic allocation or controller load behavior',
                                   controller_validated=False),
        variable_array_declarations=emitter.variable_array_uses,
        vector_routine_policy=dict(results='Exact VECTOR expressions only; initialized X/Y/Z checked and copied before local frames unwind',
                                   values='Grouped VECTOR variables/fields/elements, operator expressions and VECTOR function results use independent writable temporary storage',
                                   references='Bare ordinary VECTOR storage retains references; bare protected POSITION orientation arguments remain blocked',
                                   effects='Existing transitive potential writes/delay/output/abort, operator, indexed-target, argument-order, FOR and call-depth guards remain',
                                   boundary='ARRAY results follow array_routine_policy; whole ARRAY values, direct STRING results, VECTOR constructor, positional conversion, orientation initialization, frame transforms and native runtime equivalence remain unsupported',
                                   controller_validated=False),
        vector_returns=emitter.vector_return_uses, vector_value_arguments=emitter.vector_value_uses,
        structure_routine_policy=dict(results='Previously declared exact named STRUCTURE types; recursive initialized copies before local frames unwind',
                                      values='Grouped records/fields/elements and named STRUCTURE function results receive independent writable temporary storage',
                                      fields='All supported fixed field types retain concrete sizes, nominal identities, scalar checks, CONFIG limits, joint widths and POSITION protection; every leaf must be initialized/known',
                                      limits='At most 32767 scalar leaves per copied value; no partial/unknown BYTE copies, resizing, shape coercion or type aliases',
                                      effects='Existing reference forwarding, potential writes/delay/output/abort, indexed-target/operator/argument-order and FOR/call-depth guards remain',
                                      boundary='ARRAY results follow array_routine_policy; whole ARRAY value arguments, direct STRING results, external types/routines, persistent storage and controller ABI/runtime equality remain unsupported',
                                      controller_validated=False),
        structure_returns=emitter.structure_return_uses, structure_value_arguments=emitter.structure_value_uses,
        positional_routine_policy=dict(types=['CONFIG','XYZWPR','XYZWPREXT','POSITION','JOINTPOS1..9'],
                                       results='Internal exact-type results; all known/initialized fields or axes checked and independently copied before frame cleanup',
                                       values='Grouped ordinary storage/fields/elements and same-type function results use independent writable temporaries; bare storage keeps references',
                                       identity='No cross-type, cross-width, group/frame or joint/Cartesian conversion; unsuffixed JOINTPOS remains nine axes',
                                       protection='POSITION orientation descendants stay read-only in copied values; bare protected orientation arguments remain blocked',
                                       context='Copying existing data supplies no axis units/frame metadata or POSITION initializer; REAL/joint conversions retain their explicit joint_axes requirement',
                                       effects='Existing potential-write/delay/output/abort, operator, indexed-target, multiple-argument, FOR and call-depth guards remain',
                                       boundary='ARRAY results follow array_routine_policy; no controller ABI, geometry/kinematics, orientation defaults, whole ARRAY values or direct STRING results',
                                       controller_validated=False),
        positional_returns=emitter.positional_return_uses, positional_value_arguments=emitter.positional_value_uses,
        trig_policy=dict(functions=list(rt.UNARY_TRIG_FUNCTIONS),angle_units='degrees',
                         angle_range_inclusive=[-18000,18000],range_before_period_reduction=True,
                         sin_angles_mod_360=[0,30,90,150,180,210,270,330],cos_angles_mod_360=[0,60,90,120,180,240,270,300],
                         tan_angles_mod_180=[0,45,135],tan_odd_right_angles='Explicit domain rejection',
                         inverse_inputs=[-1,-.5,0,.5,1],asin_outputs=[-90,-30,0,30,90],acos_outputs=[180,120,90,60,0],
                         input_policy='Existing exact normal-or-zero REAL checks, including INTEGER/narrow promotion',
                         runtime='Finite exact tables and rational period reduction; no host trig/libm or tolerance snapping',
                         boundary='Other valid mathematical inputs fail at runtime pending rounding evidence. ATAN2 uses its separate restricted policy; no EXP/LN or controller numeric/alarm equivalence.',
                         controller_validated=False),
        trig_uses=emitter.trig_uses,
        atan2_policy=dict(argument_order=['x','y'],result='REAL counterclockwise angle in degrees from positive x-axis',
                          coordinates='Initialized checked REAL values or exact INTEGER/narrow promotions; existing normal-or-zero input policy',
                          supported='Nonnegative coordinates outside origin: positive x-axis 0, positive y-axis 90, positive x=y diagonal 45',
                          exact_results=[0,45,90],origin='Explicit undefined-domain error after both coordinate checks',
                          negative_coordinates='Rejected pending native quadrant/return-range evidence, including negative-axis branch cut',
                          other_bearings='Rejected pending rounding evidence; no tolerance snapping',
                          runtime='Comparisons only; no ratio, squares, host atan2, radian conversion or inferred coordinate limit',
                          effects='Existing two-argument routine-call order, indexed-target, operator, FOR, ABORT and cleanup guards remain',
                          boundary='No general ATAN2 range/rounding, signed-zero quadrant inference, frame/pose construction, robot context or controller numeric/alarm equivalence',
                          controller_validated=False),
        atan2_uses=emitter.atan2_uses,
        array_routine_policy=dict(results='Internal unsized anonymous outer ARRAY with INTEGER/BOOLEAN/REAL/BYTE/SHORT, explicitly bounded STRING, prior named STRUCTURE, data record, exact-width JOINTPOS or prior named ARRAY elements; one outer dimension and at most three logical dimensions',
                                   returns='Every scalar leaf initialized/checked; independent recursive copy before frame cleanup; 32767 prototype scalar-leaf limit',
                                   narrow_elements='BYTE 0..255 must be known; SHORT -32768..32766 must be initialized; 32767 remains the SHORT uninitialized marker; no whole-array element coercion',
                                   aggregate_elements='Exact named STRUCTURE identity, concrete nested shapes/STRING capacities, CONFIG checks and joint widths retained; POSITION orientation protection retained; no acquired/default robot state',
                                   named_components='Every inner ARRAY component is a prior named fixed type; exact identity, shape and terminal type retained without flattening, including bounded STRING terminals',
                                   string_elements='Explicit exact element capacity in 1..254; inherited formal capacities checked against the declared result at runtime; known initialized ASCII leaves copied without RETURN truncation or capacity inference',
                                   use='Function call only as the complete right side of direct assignment; zero-parameter names and existing explicit calls accepted; no grouping of a call, passing to another routine, built-in consumption or direct RETURN forwarding',
                                   destinations='Existing exact concrete array type/length checks; no resizing, conversion, flattening or copy-back; stable captured element references',
                                   references='Whole ARRAY reference arguments remain supported; whole ARRAY value arguments remain prohibited',
                                   boundary='Named outer ARRAY types, flat multidimensional result sources/declarations, unspecified STRING result-element capacities, direct STRING results, unknown leaves, external routines and native runtime/ABI behavior remain unsupported',
                                   controller_validated=False),
        array_returns=emitter.array_return_uses, array_result_assignments=emitter.array_result_assignments,
        array_function_uses=emitter.array_function_uses, array_value_arguments=emitter.array_value_uses,
        array_result_declarations=[dict(routine=r.name, result_spec=r.return_type,
                                       declared_dimensions=rt.array_shape(r.return_type),
                                       nominal_identity=rt.array_identity(r.return_type),
                                       logical_rank=len(rt.array_dimensions(r.return_type)), line=r.token.line)
                                   for r in program.routines if r.return_type and r.return_type[0] == 'ARRAY'],
        bare_function_calls=emitter.bare_function_uses,
        bare_function_policy=dict(resolution='Unshadowed internal zero-parameter function names in value expressions resolve after USING fields and before call/effect analysis',
                                  storage='Assignment targets and field/array receiver roots remain storage; local variables, parameters and constants keep their existing binding',
                                  effects='Same argument passing, potential effects, indexed targets, operators, SELECT, FOR, ABORT and depth/cleanup checks as explicit calls',
                                  arrays='Complete direct-assignment RHS only; grouped calls, argument consumption and direct RETURN forwarding remain blocked',
                                  boundary='No external linkage, first-class function values, bare built-in invocation or new namespace/storage-selector rules; existing explicit empty-parenthesis spelling remains accepted',
                                  controller_validated=False),
        literal_policy=dict(apostrophes='A doubled source apostrophe inside one quoted STRING decodes to one logical apostrophe',
                            source_positions='Raw tokens and physical columns retained; logical lengths/capacities use decoded contents',
                            boundary='ASCII only, one physical token; no backslash escapes or multiline token splicing; quoted WRITE embedded-apostrophe formatting remains blocked',
                            controller_validated=False),
        escaped_string_literals=parser.escaped_string_literals,
        python_sha256=hashlib.sha256(generated.encode('utf-8')).hexdigest(),
        features=sorted(emitter.features), source_map=emitter.source_map,
        local_constant_policy=dict(scope='Declaring routine only; lexical resolution, not caller inheritance',
                                   declarations='Source order; existing literal/previous-constant expression subset',
                                   storage='Immutable scalar values emitted directly; no writable runtime cells',
                                   arguments='INTEGER/BOOLEAN/REAL constants pass as independent value temporaries; STRING values require read-only formals',
                                   namespace='Duplicates and global-declaration shadowing blocked; local TYPE prohibited',
                                   controller_validated=False),
        local_constants={r.name: [dict(name=t.value, value=r.local_constants[t.value], line=t.line, column=t.column)
                                  for kind, t, _ in r.local_declarations if kind == 'CONST']
                         for r in program.routines if r.local_constants},
        string_value_policy=dict(arguments='ASCII STRING literals, constants, expressions and grouped scalar storage; logical length at most 254',
                                 storage='Independent initialized read-only temporary; physical capacity is unspecified and never used for writes',
                                 effects='Flow-insensitive per-formal potential writes propagate through reference arguments and recursive calls',
                                 rejection='E_STRING_VALUE when the target formal may be written; STRING function results remain blocked',
                                 controller_validated=False),
        string_value_arguments=emitter.string_value_uses,
        string_returns=emitter.string_return_uses,
        string_routine_declarations=[dict(routine=r.name, capacity=r.return_type[1],
                                          capacity_defaulted=r.string_result_defaulted, line=r.token.line)
                                    for r in program.routines if r.return_type and r.return_type[0] == 'STRING'],
        delay_policy=dict(duration='INTEGER milliseconds evaluated once; checked range 0..86400000',
                          zero='No host sleeper call',
                          host='Default time.sleep(milliseconds / 1000.0); Program(sleep=...) injects a synchronous sleeper accepting seconds and returning None',
                          effects='May-delay propagation through routine calls; ambiguous operator/indexed-target ordering remains blocked',
                          boundary='Host process/thread timing only; no controller scheduling, motion, pause, abort or RMI wait semantics',
                          controller_validated=False),
        delays=emitter.delay_uses,
        abort_policy=dict(source='Bare ABORT statement only; current offline execution',
                          outcome='Raises distinct source-located KarelAbort; propagates through routine frames without successful completion',
                          restart='Aborted instances cannot run again; construct a new Program for a cold offline restart',
                          observations='Program.abort_info is copied; Program.snapshot() returns defensive offline globals; prior writes/delays are not rolled back',
                          for_boundary='Direct ABORT inside FOR requires fresh routine-local counters; observable aborted counters are unvalidated',
                          boundary='No PROGRAM[n], ABORT actions/conditions, ABORT_TASK, handler/NOABORT behavior, controller task/motion cancellation, native persistence or resume',
                          controller_validated=False),
        aborts=emitter.abort_uses,
        write_policy=dict(source='Omitted-file WRITE with one STRING or unformatted BOOLEAN/INTEGER expression',
                          input='STRING: initialized ASCII contents of at most 254 characters; BOOLEAN: initialized strict bool; INTEGER: initialized strict int in 0..2147483647; evaluated once',
                          formatting='STRING only: nonnegative literal width; unquoted 0/1 use contents length for width 0 or above 254; quoted 2/3 require width 1..254, no apostrophes and room for contents, leading blank and both quotes',
                          boolean='Unformatted TRUE or FALSE with exactly one leading blank; all BOOLEAN format specifiers remain blocked',
                          integer='Unformatted nonnegative decimal digits with exactly one leading blank; negative INTEGER values fail before request, and all INTEGER format specifiers remain blocked because manual examples contain spacing conflicts',
                          adapter='Default per-run request recorder; Program(write=...) supplies a synchronous text callback returning None',
                          trace='Program.write_requests returns copied text/line/adapter_outcome records; callback failures/interruption may retain external effects',
                          effects='Potential output requests propagate through routine calls; ambiguous operator/indexed-target order remains blocked',
                          boundary='Source default is TPDISPLAY; BOOLEAN/INTEGER formatting, negative INTEGER output, REAL output, quoted truncation/fallback/apostrophes, signed widths, file/device/buffering/transmission, CR and IO_STATUS remain unmodeled',
                          controller_validated=False),
        writes=emitter.write_uses,
        reads=emitter.read_uses,
        data_record_policy=dict(types=list(DATA_RECORD_TYPES),
                                fields={name: dict(rt.record_fields((name,))) for name in DATA_RECORD_TYPES},
                                values='REAL components use the existing exact binary32 checks; CONFIG has three INTEGER turns and four BOOLEAN fields',
                                config_turn_range=[-8,7],
                                config_turn_boundary='Conservative prototype guard based on Chapter 8 turn table; not authentication of compact field layout or robot-specific configuration validity',
                                parameters='Exact-type whole records by reference only; CONFIG scalar subfields are always passed by value to user routines',
                                copies='Exact-type fully initialized independent copies; destination storage and captured field aliases preserved',
                                initialization='Scalar leaves start uninitialized; whole-record UNINIT and partial copies remain blocked',
                                position='NORMAL/ORIENT/APPROACH are read-only recursively; LOCATION/CONFIG_DATA are writable. Bare orientation arguments are blocked, while explicit scalar value expressions can read initialized components',
                                position_initialization='No orientation defaults or constructor are synthesized; new orientation leaves remain uninitialized. Whole copies require all leaves initialized',
                                extended='XYZWPREXT adds read-write EXT1/EXT2/EXT3 REAL fields to the XYZWPR layout',
                                boundary='No group/frame context, cross-type positional conversions, builtin USING, POSITION operators, record I/O, registers or motion',
                                controller_validated=False),
        config_subfield_arguments=emitter.config_value_uses,
        joint_policy=dict(types=list(rt.JOINT_TYPE_NAMES),default_declared_axes=9,
                          representation='Opaque joint values; no source field/index syntax; snapshot axes list is offline presentation',
                          passing='Exact declared width by reference only; same-width initialized copies preserve destination storage',
                          conversions='CNV_REL_JPOS/CNV_JPOS_REL require explicit degree-valued Program(joint_axes=1..9) context and matching declared width',
                          arrays='One-dimensional ARRAY OF REAL; input must fit active axes, output may be a prefix; excess elements ignored/preserved',
                          status='Set to zero after offline success; guards raise source-located exceptions before output mutation; no controller error-status mapping',
                          boundary='No implicit system joint count, group metadata, units/robot mapping, kinematics, cross-width/positional conversions or motion',
                          controller_validated=False),
        joint_conversions=emitter.joint_conversion_uses,
        unpos_policy=dict(input='Exact XYZWPR storage; six initialized exact REAL components and initialized bounded CONFIG',
                          outputs='Six exact REAL references and one CONFIG reference; aliases captured once and destination aggregate storage preserved',
                          overlap='Source and all output storage footprints must be pairwise disjoint; runtime guards precede mutation',
                          effects='All seven outputs participate in direct/transitive reference-write analysis',
                          boundary='No POSITION/XYZWPREXT/JOINTPOS coercion, POS constructor, frame/kinematic conversion, controller config-validity, status or alarm mapping',
                          controller_validated=False),
        unpos_calls=emitter.unpos_uses,
        vector_policy=dict(operators=['+', '-', '*', '/', '#', '@', '=', '<>'],
                           precedence='Cross/dot above multiplication; unparenthesized same-level #/@ chains blocked pending associativity evidence',
                           scaling='INTEGER/REAL and VECTOR in either order; scalar divided by VECTOR requires exact normal-or-zero components and exact non-underflowing reciprocals',
                           products='Cross product rejects zero/parallel operands; dot product requires every pairwise partial sum exact, independent of association',
                           numeric='All components initialized; existing exact binary32 checks on inputs/results; compound-product intermediates must also be exact and must not underflow',
                           ownership='Fresh result vectors; assignment preserves existing destination field aliases',
                           boundary='No VEC constructor, unary VECTOR signs, ordered relations, POSITION transforms, frame context or controller validation',
                           controller_validated=False),
        vector_constructors=emitter.vector_constructor_uses,
        pos_constructors=emitter.pos_constructor_uses,
        config_text_conversions=emitter.config_text_uses,
        time_text_conversions=emitter.time_text_uses,
        microsecond_timers=emitter.microsecond_timer_uses,
        register_operations=emitter.register_uses,
        service_operations=emitter.service_uses,
        frame_operations=emitter.frame_operation_uses,
        position_axis_queries=emitter.position_axis_uses,
        position_comparisons=emitter.position_comparison_uses,
        waits=emitter.wait_uses,
        position_conversions=emitter.position_conversion_uses,
        kinematic_assignments=emitter.kinematic_assignment_uses,
        joint_geometry=emitter.joint_geometry_uses,
        pulses=emitter.pulse_uses,
        initialization_queries=emitter.initialization_query_uses,
        user_types=emitter.user_types,
        type_aliases=emitter.type_aliases,
        named_array_policy=dict(definitions='Fixed ARRAY with supported scalar, prior STRUCTURE or prior named ARRAY elements; total logical rank at most three',
                                identity='The declared type name is retained in storage, references and whole-copy checks',
                                parameters='Same named type by reference; anonymous rank-matched ARRAY formals retain concrete caller identity',
                                assignment='Same named type; unknown generic formal identities are checked before copying at runtime',
                                aliases='Scalar aliases, aliases to existing type names and inline anonymous nested ARRAY syntax remain blocked',
                                results='Named outer ARRAY function result types remain blocked; named inner ARRAY elements are supported in unsized anonymous results', controller_validated=False),
        named_array_types={name: spec for name, spec in emitter.user_types.items() if spec[0] == 'ARRAY'},
        subarray_policy=dict(selection='Comma-separated prefix ending at a separately named ARRAY type boundary',
                             total_logical_rank=3, ownership='Captured references into stable existing storage; copies are independent',
                             generics='Logical-rank scalar interfaces or interfaces retaining explicit named components',
                             runtime_layout='Nested prototype objects; no controller storage-layout claim', controller_validated=False),
        subarray_uses=emitter.subarray_uses,
        select_policy=dict(selector='INTEGER expression evaluated once', duplicate_values='First matching clause wins',
                           max_case_clauses=1000, no_match_without_else='Source-located KarelRuntimeError',
                           empty_else='Explicit presence preserved; an empty clause permits continuation',
                           python_dispatch='Checked clause index and flat Python match cases', controller_validated=False),
        selects=emitter.select_scopes,
        conversion_policy=dict(procedures=['CNV_STR_INT', 'CNV_INT_STR', 'CNV_STR_REAL', 'CNV_REAL_STR'],
                               output='Writable exact INTEGER/STRING/REAL variable, field or element; reference captured once',
                               parse='Canonical ASCII signed decimal; alphabetic-only invalid text clears output',
                               real_parse='Complete ASCII signed digits.digits, optionally E followed by signed exponent; existing exact REAL guard; alphabetic-only invalid text clears output',
                               real_format='Exactly representable fixed decimal with 0..254 fractional digits; positive minimum length no greater than the natural result; one leading blank; caller-capacity asterisks',
                               real_format_guard='Rounding, scientific notation, precision outside the explicit 0..254 prototype bound and additional padding remain blocked; invalid-format outcome not inferred',
                               format='Decimal bases 0/10 for signed values and bases 2..9 for nonnegative values, length 1; one leading blank, capacity overflow becomes blank plus asterisks',
                               nondecimal_format='Minimal positional numeric digits without prefixes or padding; negative nondecimal values and bases 11..16 remain blocked pending representation/digit-case evidence',
                               invalid_base='Outside 0 or 2..16 clears output when length is 1',
                               other_formats='blocked; whitespace, prefixes, fractional and mixed text remain unverified',
                               numeric_range='Existing INTEGER storage guard; out-of-range or MAXINT parse preserves destination',
                               user_routine_arguments='blocked', controller_validated=False),
        predefined_constants={name: dict(value=value, type='BOOLEAN' if type(value) is bool else 'INTEGER')
                              for name, value in PREDEFINED_CONSTANTS.items()},
        predefined_uses=parser.predefined_uses,
        integer_policy=dict(expression_range=[-2147483648, 2147483647],
                            storage_range=[-2147483648, 2147483646],
                            minimum_integer_literal='Use MININT; -2147483648 INTEGER source literals are rejected',
                            maxint_storage='blocked; special-state behavior is not inferred',
                            checked_function_results='Use the same conservative storage guard',
                            predefined_shadowing='blocked', controller_validated=False),
        source_policy=dict(continuation='Trailing & joins complete tokens across one physical newline',
                           trailing_comments=True, physical_locations_preserved=True,
                           newline_forms=['LF', 'CRLF', 'CR', 'form feed'],
                           continued_line_limit=252, line_truncation='not modeled',
                           split_tokens='blocked', empty_target_lines='blocked',
                           continued_directives='blocked', controller_validated=False),
        continuations=parser.continuations,
        using_policy=dict(selectors='Bare named STRUCTURE variables',
                          priority='Fields shadow variables; right-most listed structure wins',
                          resolution='Lexical explicit field paths before type/effect/flow analysis',
                          nested_scopes='blocked', call_name_collisions='blocked', constant_name_collisions='blocked',
                          shadowed_for_counters='blocked', controller_validated=False),
        using_scopes=emitter.using_scopes,
        control_flow=emitter.control_flow,
        array_policy=dict(ranks=[1, 2, 3], declarations='Fixed comma-separated dimensions, or direct global wildcard dimensions specialized with explicit array_shapes translation context',
                          formals='Rank-matched wildcard dimensions; reference only',
                          subscripts='One-based full elements or prefixes ending at separately named ARRAY boundaries',
                          max_scalar_elements=32767, max_scalar_leaves=32767,
                          capacity_limit='Prototype allocation guard; includes all nested STRUCTURE fields',
                          whole_copy='Identical concrete shape/type; captured element and field storage preserved; STRUCTURE elements require initialized known leaves',
                          structure_elements='Named types; independent contents and rank-matched reference formals',
                          subarrays='Separately named components only; stable reference storage', array_len='One logical dimension only', controller_validated=False),
        for_policy=dict(routine_calls='Fresh routine-local counters only',
                        counter_arguments='Reference passing blocked; scalar value arguments allowed',
                        return_from_for='Fresh routine-local counters only; the routine frame is destroyed',
                        global_or_formal_counter_calls_and_returns='blocked',
                        jumps_and_labels_inside_for='blocked', controller_validated=False),
        numeric_policy=dict(real_model='exact_binary32_normal_or_zero',
                            arithmetic='Exact rational intermediates, checked after each operation',
                            sqrt='Nonnegative input; exact rational roots only, checked for binary32 representability',
                            rounding_dependent_values='blocked',
                            underflow_threshold='1.175494E-38 from manual; nearby subnormal boundary blocked',
                            signed_zero='not modeled', controller_validated=False),
        narrow_integer_policy=dict(storage='ARRAY elements and STRUCTURE fields only',
                                   byte_range=[0, 255], unwritten_byte='Unknown contents; reads blocked',
                                   byte_uninit='blocked', short_range=[-32768, 32766],
                                   short_uninitialized_assignment=32767,
                                   scalar_arguments='Always value copies to INTEGER/REAL formals',
                                   controller_validated=False),
        routine_effects={r.name: dict(potential_external_writes=r.side_effecting,
                                     potential_global_writes=sorted(r.global_writes),
                                     potential_host_delays=r.may_delay,
                                     potential_host_clock_reads=r.may_clock,
                                     potential_register_reads=r.may_read_registers,
                                     potential_register_writes=r.may_write_registers,
                                     potential_service_requests=r.may_services,
                                     potential_output_requests=r.may_write,
                                     potential_input_requests=r.may_read,
                                     potential_aborts=r.may_abort,
                                     potential_parameter_writes=sorted(r.parameter_writes),
                                     parameters=[dict(name=t.value, type=spec[0], type_spec=spec,
                                                      passing_modes=(['reference', 'value'] if spec[0] in ('STRING', 'ARRAY') and mode == 'pythonic'
                                                                     else ['reference', 'value_read_only'] if spec[0] == 'STRING' and t.value not in r.parameter_writes
                                                                     else ['reference', 'value'] if spec[0] in (*RECORD_TYPES, 'JOINTPOS')
                                                                     else ['reference'] if spec[0] in ('STRING', 'ARRAY', *RECORD_TYPES, 'JOINTPOS') else ['reference', 'value']))
                                                 for t, spec in r.parameters])
                         for r in program.routines},
        directives=[dict(text=t.value, line=t.line, disposition=metadata['disposition'])
                    for t, metadata in zip(program.directives, program.directive_metadata)],
        directive_metadata=[dict(row) for row in program.directive_metadata],
        limitations=['Offline subset; no controller behavior validation',
                     'WRITE accepts one STRING with checked literal formats or one unformatted BOOLEAN/nonnegative INTEGER with exactly one leading blank; BOOLEAN/INTEGER formats, negative INTEGER/REAL output, direct BYTE/SHORT items, quoted truncation/fallback/apostrophes, signed widths, device/stdout mapping, buffering, CR and IO_STATUS remain blocked',
                     'DELAY uses checked host time.sleep or an injected synchronous sleeper; controller timing, motion, pause and abort behavior remain unverified; step budget is not a wall-clock limit',
                     'Named arrays/subarrays retain nominal identity and at most three logical dimensions, including named inner ARRAY result elements; scalar/type aliases, anonymous inline nested ARRAY syntax and named outer ARRAY function results remain blocked',
                     'CNV_STR_INT accepts canonical signed decimal or alphabetic-only invalid text; other grammar/range cases are blocked',
                     'CNV_INT_STR accepts decimal base 0/10 with length 1; valid other bases/widths are blocked and invalid bases clear output',
                     'Conversion outputs require exact writable INTEGER/STRING storage; argument user calls and active counter writes are blocked',
                     'ON/OFF/MININT/MAXINT are scalar constants; redefinition and field-name collisions are blocked pending namespace evidence',
                     'INTEGER source minimum requires MININT; INTEGER storage/value parameters/checked function results exclude MAXINT without inferring its special-state behavior',
                     'Continuation joins complete tokens only; split/fused tokens, empty target lines and continued directives are blocked',
                     'Continued physical lines are limited to 252 characters; general source-line truncation is not modeled',
                     'Labels and GO TO/GOTO stay in the same program/routine body; FOR-body jumps and labels are blocked',
                     'Jumps may stay in one structured block or exit to an ancestor; entry into nested or sibling blocks is blocked',
                     'Labels use non-reserved letter-starting identifiers of at most 36 characters; release-specific compiler limits remain unverified',
                     'Signed MOD with negative operands is blocked at runtime',
                     'Boolean operands evaluated eagerly; side-effecting routine operands blocked',
                     'Dynamic routine variables and immutable lexically scoped local constants; INTEGER/BOOLEAN/REAL reference and value parameters',
                     'REAL uses exact binary32 representability guards; rounding-dependent results are blocked',
                     'Underflow follows the manual decimal threshold; the nearby subnormal boundary is blocked',
                     'STRING reference parameters retain caller capacity; ASCII value arguments of at most 254 characters require read-only formals; temporary physical capacity and writable STRING values remain unmodeled',
                     'Whole ARRAY reference parameters support INTEGER/BOOLEAN/REAL/STRING/BYTE/SHORT and named STRUCTURE elements; value passing is prohibited',
                     'BYTE/SHORT storage is limited to ARRAY elements and STRUCTURE fields; scalar INTEGER/REAL arguments are value copies',
                     'Unwritten BYTE contents remain unknown and cannot be read; BYTE UNINIT queries remain blocked',
                     'SHORT assignment of 32767 stores the uninitialized marker; initialized values are -32768..32766',
                     'Whole-array assignment requires identical concrete types and sizes at runtime',
                     'Scalar/STRUCTURE ARRAYs support up to three logical dimensions; direct global wildcard declarations require explicit positive array_shapes specialization; scalar leaf count including nested fields is capped at 32767 by the prototype',
                     'Generic ARRAY formals check logical rank and terminal element type while retaining actual caller storage; explicit named components require matching identity',
                     'ARRAY_LEN on multidimensional arrays and routine calls in multiple subscripts remain blocked pending count/evaluation-order evidence',
                     'Named STRUCTUREs use nominal identity; nested previously defined structures and supported arrays are accepted',
                     'USING qualifies fields lexically for bare STRUCTURE variables; right-most field wins; nested scopes, complex selectors, call/constant-name collisions and shadowed FOR counters are blocked',
                     'Arrays of STRUCTUREs copy independently and preserve captured field references; copying requires initialized known scalar leaves',
                     'Named STRUCTURE results and value arguments require exact identity, fully initialized known leaves and bounded independent copies; aggregate UNINIT remains blocked',
                     'Whole-structure copying requires every scalar leaf initialized; partial initialization semantics remain unverified',
                     'INDEX with an empty search string is blocked pending source/runtime evidence',
                     'SUB_STR beyond the source end or producing more than 254 characters is blocked; starts past the source return empty',
                     'CHR and ORD support ASCII only; errors use Python exceptions, not controller task/alarm behavior',
                     'Side-effecting routine calls in multi-argument calls remain blocked',
                     'Execution has a finite configurable step budget',
                     'Routine call depth is limited to 64; a prototype guard, not KAREL task-stack modeling',
                     'FOR-body routine calls and RETURN require fresh routine-local counters; active-counter reference arguments remain blocked',
                     'Uninitialized variables, checked signed 32-bit integers, ASCII-only strings'],
    ))


def translate(source, *, filename='<input>', array_shapes=None, mode='pythonic', cooperative=False):
    """Translate using the public Pythonic contract; strict is a future milestone."""
    if type(mode) is not str or mode != 'pythonic':
        message = ('Strict mode is a future milestone; use mode="pythonic"'
                   if mode == 'strict' else 'Supported translation mode: pythonic')
        raise TranslationError('E_MODE', message, Token('NAME', '', 1, 1), filename)
    if type(cooperative) is not bool: raise ValueError('cooperative must be BOOLEAN')
    with rt._numeric_scope(mode):
        result = _translate(source, filename=filename, array_shapes=array_shapes, mode=mode, cooperative=cooperative)
    report = result.report
    report['service_policy'] = dict(
        procedures=sorted(ex.PROCEDURES), functions=sorted(ex.FUNCTIONS), ports=dict(ex.PORT_TYPES),
        context='Explicit ExecutionContext with bounded banks, typed JSON persistence and attached program namespaces; optional caller-rooted DirectoryFiles and configured DH model',
        values='Checked exact output references, disjoint resources, ordered input/selector capture; prior completed effects retained on error',
        files='MemoryFiles or explicit DirectoryFiles root; ASCII text, ATR_FIELD capacity-sized STRING reads, byte-accurate EOL cursors, ATR_UF binary, selectable byte order and interactive flush; bounded copy/delete/rename/list',
        collections='Typed one-based PATH nodes/header, full/reversed range copies and initialized fixed-capacity FIFO queues',
        robot='JOINT2POS/POS2JOINT/IN_RANGE use supplied callbacks or loadable standard-DH models; group/frame/tool data explicit; bounded numerical IK is not certified reachability',
        observations='Defensive value-free Program.service_requests operation/line/outcome records, reset at new run',
        guide='docs/offline-services.md',controller_validated=False)
    report['program_listing_policy']=dict(
        procedure='PROG_LIST(pattern,type,skip,format,names,count,status[,cursor])',
        context='Current/attached KAREL programs and explicitly registered task Program identities are PC; optional immutable ProgramCatalog supplies VR/JB/PR/MR/TP/PC metadata without loading code',
        listing='Case-insensitive star-only patterns, documented type filters 1..8, distinct name/type pairs sorted lexically and paged to ARRAY capacity; no discovery from files, bindings or callbacks',
        pagination='Skip is allowed only for pattern * and type 7; optional initialized nonnegative INTEGER cursor indexes matching rows after skip and advances by returned count; reset when query/catalog changes',
        formats='1 name; 2 name padded to 12 or 36 columns plus space and two-letter type; over-capacity rows fail without truncation; successful unused slots cleared',
        status='Portable 0 success, 2 invalid options, 3 text capacity/format overflow; errors preserve all outputs except status; no matches succeeds',
        outputs='Capture inputs/selectors once left-to-right; disjoint exact writable references; validate complete output batch including cursor before writes',
        persistence='Only explicit catalog metadata persists in context programs; attached code and tasks require host/project attachment after reload',
        boundary='Reviewed manual syntax omits status despite its parameter table; use seven required arguments and optional eighth cursor; no native directory order/cursor encoding/status mapping, program loading or controller execution; strict deferred',
        guide='docs/program-listing.md',controller_validated=False)
    report['variable_inspection_policy']=dict(
        procedures=['VAR_INFO','VAR_LIST'],type_codes=dict(VARIABLE_TYPE_CODES),
        lookup='Current/attached declared globals and explicit VariableStore roots; static fields, ARRAY subscripts and PATH nodes; no local-frame or controller discovery',
        metadata='Canonical resolved leaf type and code, three logical ARRAY dimensions and STRING element capacity; no source-value copies or initialization',
        initialization='Content-based missing leaves for data aggregates; unknown BYTE is not initialization-tracked; FILE tracks open state; PATH inspects supplied header/nodes; unsupported QUEUE_TYPE code returns status 4',
        listing='Case-insensitive star patterns, sorted program/name roots, zero-based skip and caller ARRAY capacity; four formats; clear unused slots only on success',
        status='Portable 0 success, 1 lookup/program missing, 2 invalid list options, 3 list text capacity/format overflow, 4 unsupported metadata type; failure writes status only',
        outputs='Capture arguments once left-to-right; disjoint exact writable references; validate complete output batches before writes; inspected source may also be an output',
        boundary='No native variable-table order, cache IDs, system discovery, controller initialization flags or native status mapping; strict remains future work',
        guide='docs/variable-inspection.md',controller_validated=False)
    report['io_parameter_policy']=dict(
        ports='GET/SET_PORT_VAL, GET/SET_PORT_CMT and GET/SET_PORT_SIM share PortBank values; indirect IDs require caller-supplied type_codes mapping, without inferred native enums',
        simulation='SET_PORT_SIM initializes the value and marks the logical port simulated; SET_PORT_VAL writes outputs or simulated inputs; direct input assignment remains rejected',
        conversions='Checked INTEGER/REAL/BOOLEAN/ASCII STRING scalar values; Boolean 0/1, exact integral conversion, finite analog values; GET_PORT_SIM returns INTEGER 0/1',
        status='Portable port codes: 0 success, 1 missing value, 2 unmapped type/range, 3 invalid representation, 4 input not simulated; failed requests preserve other outputs and bank state',
        comments='Independent numeric/position/string-register comments, empty by default; capacities 16/16/254; port comments 16; setters and output destinations truncate; serialized with their banks',
        parameters='Explicit CallParameters map root program names to argument numbers 1..10; GET_TPE_PRM writes type 1 INTEGER, 2 REAL or 3 STRING and only the selected value output; absent argument writes status 17042 only',
        persistence='Optional bank comments, port type_codes/simulated flags and per-task arguments survive context JSON save/load; legacy context shape retained when absent',
        boundary='No controller discovery, native port enums, physical simulation/mode/assignment, teach-pendant acquisition or controller acceptance; strict mode deferred',
        guide='docs/io-and-call-parameters.md',controller_validated=False)
    report['file_comparison_policy']=dict(
        procedures=['COMPARE_FILE','PRINT_FILE'],
        inputs='Closed named input files from explicit MemoryFiles or rooted DirectoryFiles; bounded detached byte reads; busy/missing inputs preserve comparison count and report',
        ascii='Compare same-numbered ASCII records; normalize CR/LF/CRLF and ignore final-terminator presence; count unequal or missing records without line alignment',
        binary='Return one-based first unequal byte or prefix EOF position; zero for identical inputs',
        report='ASCII JSON Lines summary and per-record differences written once at the captured writable FILE cursor, respecting append, ATR_EOL, size bounds and interactive flush; result must belong to input backend',
        printing='Validate entire ASCII file before output; preserve original bytes in <=254-character WRITE recorder/callback chunks; both nowait values execute synchronously',
        budget='Charge each ASCII record, each 4096-byte binary block and each print chunk to the ordinary step budget; handlers do not scan within these synchronous operations',
        status='Portable 0 success, 1 missing input, 3 open/busy input; invalid context/path/ASCII/report capacity or callback errors raise; prior completed print callbacks remain effective',
        boundary='No native comparison/report/alignment/offset encoding, printer/device discovery, asynchronous execution or controller acceptance; strict remains future work',
        guide='docs/file-comparison.md',controller_validated=False)
    report['task_inspection_policy']=dict(
        procedure='GET_TSK_INFO(task_name,task_no,attribute,value_int,value_str,status)',
        constants=dict(rt.TASK_CONSTANTS),
        selection='Name lookup when task_no is uninitialized or zero; otherwise one-based registry insertion order, shared with numeric task controls; only selected identity/value outputs change on success',
        live='Program/routine names from active caller-rooted frames, latest source checkpoint line, logical routine-frame count, execution/program state and scheduler quantum',
        metadata='Other documented TSK_* INTEGER attributes require explicit bind(name,program,attributes={...}); metadata is informational and does not change task behavior',
        status='Portable 0 success, 1 unknown task, 2 invalid attribute/negative number, 3 unsupplied metadata; failure preserves identity and value outputs',
        boundary='Portable constants and additional completed/stopped/failed/waiting states; no native enum, stack byte size, priority/interrupt/motion behavior or controller acceptance; task bindings and continuations are not serialized',
        guide='docs/task-inspection.md',controller_validated=False)
    report['calendar_clock_policy']=dict(
        procedures=['GET_TIME','SET_TIME'],
        context='Explicit CalendarClock in ExecutionContext.calendar; supplied naive calendar value in 1980..2107; frozen unless a synchronous elapsed-microsecond adapter is supplied',
        packing='Same checked signed 32-bit year/month/day/hour/minute/two-second fields as CNV_STR_TIME/CNV_TIME_STR; odd seconds floor at read; internal fractions retained',
        set='SET_TIME updates only the supplied offline clock; zero is a no-op without sampling; other values validate before sampling or replacing the anchor',
        elapsed='Adapter sampled once at clock construction, then once per read/set/snapshot; nonnegative integer microseconds, no backward observations; range and callback failures preserve prior clock state and pending GET output',
        persistence='calendar.value is a complete naive ISO datetime; saves preserve full microseconds; restores are frozen snapshots without callbacks or elapsed origins',
        boundary='No operating-system/controller clock changes, implicit host date acquisition, timezone, locale discovery, native timing or controller acceptance; strict remains future work',
        guide='docs/calendar-clock.md',controller_validated=False)
    report['register_lifecycle_policy']=dict(
        procedures=['POS_REG_TYPE','CLR_POS_REG','CLR_PORT_SIM'],
        representation='Stored position representation codes: POSITION 1, XYZWPR 2, XYZWPREXT 6, JOINTPOS 9; axes are stored joint width, three extended slots, or portable zero for plain Cartesian types',
        group='POS_REG_TYPE accepts explicit group or omits the second argument; omission uses the root caller group, with group 1 when no robot/source group exists',
        clear='CLR_POS_REG removes one group or every configured group when group=0; valid absent entries succeed; other registers, comments and existing copies remain unchanged',
        simulation='CLR_PORT_SIM removes the mapped address simulation flag, preserving values and comments; unsimulated inputs reject subsequent indirect source writes until simulated again',
        status='Portable 0 success, 1 absent register, 2 invalid address/group; failed introspection preserves representation outputs; checked disjoint exact INTEGER outputs and source-order evaluation',
        boundary='Explicit offline banks and flags only; stored widths and three external slots do not infer physical axes; no live acquisition, hardware mode change, native alarms or controller acceptance',
        guide='docs/register-lifecycle.md',controller_validated=False)
    report['current_robot_policy']=dict(
        functions=['CURPOS','CURJPOS','CURR_PROG'],
        context='Explicit RobotState position and/or complete joints per robot group; caller updates atomically; no pose/joints or live acquisition defaults',
        position='CURPOS returns an independent XYZWPREXT; supplied pose takes precedence; otherwise configured DH forward math uses current joints, active frame/tool and base without rejecting outside-limit observations',
        joints='CURJPOS returns independent JOINTPOS9 with zero-padded unused slots; supplied joint width remains unchanged; no inverse conversion inferred from a pose',
        masks='Exact disjoint INTEGER output references or literal zero to discard; explicit metadata 0..511, default zero; validate query before writing either mask',
        group='Optional explicit group or calling root task group; unconfigured groups reject, including flat contexts; linked calls inherit caller query group',
        program='CURR_PROG or CURR_PROG() returns executing module name as STRING[12], including library module during linked calls; ordinary declarations/internal functions retain precedence',
        persistence='State-only and model-backed contexts serialize latest snapshots and grouped state; no call stacks, motion or time evolution restored',
        boundary='Supplied/model-derived offline state only; no encoders, measured consistency, motion execution, mask authentication, calibrated geometry, native unused-axis encoding or controller acceptance',
        guide='docs/current-robot-state.md',controller_validated=False)
    report['joint_interoperability_policy']=dict(
        input='Model conversions and explicit joint-range contexts accept their exact axis width or complete JOINTPOS9 with zero-only unused slots; other widths and nonzero padding reject',
        output='Model POS2JOINT can write the model width or JOINTPOS9; GET_JPOS_REG and CURJPOS return independent padded nine-slot values without changing stored widths',
        values='Finite complete axes checked before conversion/range output; fractional Pythonic values retained; no discarded nonzero axes or global implicit JOINTPOS assignment conversion',
        groups='Current-state, JOINT2POS/POS2JOINT, IN_RANGE and J_IN_RANGE use the calling root task group across linked routines',
        frames='Loaded-model reachability reads current active frame/tool; latest valid frame/tool values and selections persist, preserving unchanged input representations and omitted default identity entries',
        limits='Standalone explicit joint_limits contexts can be serialized with or without current snapshots; DH models retain limits in their rows, not a second joint_limits field',
        boundary='Offline model/limit interoperability only; custom callbacks without a model keep exact output width; no physical axes inferred, native padding encoding, collision checking or controller acceptance',
        guide='docs/joint-interoperability.md',controller_validated=False)
    report['cooperative_policy'] = dict(
        enabled=report['cooperative_execution'],
        generation='Automatic for PULSE, task control, handlers, connected timers or external routines; optional cooperative=True for host-controlled ordinary source',
        execution='Generator-based run/resume retains routine/FOR frames; optional deterministic TaskScheduler interleaves checkpoints with virtual time; terminal stop closes generators',
        handlers='Ordered checkpoint scans with optional WITH $SCAN_TIME, multiple WHEN clauses, EVENT broadcasts, port edges, EVAL capture and lifecycle conditions; one-shot rearm and optional routine-local lifetime',
        timers='Global INTEGER references updated by monotonic elapsed milliseconds at checkpoints; fractional carry and backward-clock checks',
        linkage='Explicit callbacks and TaskRegistry retained; translate_project/load_project links typed FROM routines and imported globals among supplied KAREL sources; no native ABI or motion semantics',
        requests='Named/numeric remote pause/abort delivered at target checkpoints, including paused-task ABORT handlers; self identity follows linked caller; synchronous child ABORT/STOP does not terminate caller',
        guide='docs/offline-services.md',controller_validated=False)
    report['control_notification_policy']=dict(
        semaphores='Explicit SemaphoreBank count and FIFO tickets; non-consuming conditions, negative queued counts, timed/indefinite waits, grant refund and cancellation cleanup',
        persistence='Quiescent semaphore counters and bounded scoped error history; outstanding wait tickets cannot be saved',
        errors='POST_ERR 0 warning, 1 pause, 2 abort within shared context; POST_ERR_L portable ERSEV_* IDs 0..10 with local/global scope and normalized offline effects; ERROR[n]/ERROR[*] consume scoped retained notifications; runtime code 1 is an offline category',
        severity_constants={name:dict(identifier=row[0],effect=('warning','pause','abort')[row[1]],local=row[2]) for name,row in rt.ERROR_SEVERITIES.items()},
        failure='Cooperative KarelRuntimeError notifies after frame unwinding then remains a failure; budget exhaustion skips additional actions; no retry',
        actions='NOPAUSE/NOABORT clear pending requests; NOMESSAGE marks retained history; EVAL predicates/actions capture at definition',
        lifecycle='Explicit Program.powerup/scheduler.powerup resumes a live paused instance with POWERUP plus CONTINUE; ordinary resume signals CONTINUE only',
        signals='EVENT/SEMAPHORE signals and self CONTINUE scan at their trailing checkpoint, including final statements',
        boundary='Portable ERSEV IDs are independent of native encodings; STOP/SERVO variants request offline pause and SYSTEM requests global abort; no native priorities, motion UNTIL handlers, alarm dictionaries, process restoration or controller acceptance',
        guide='docs/control-notifications.md',controller_validated=False)
    if cooperative:
        report['translation_context']['cooperative'] = True
        report['translation_context_sha256'] = hashlib.sha256(json.dumps(report['translation_context'], sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest()
    report['register_policy'] = dict(
        procedures=sorted(REGISTER_PROCEDURES),
        context='Explicit Program(registers=NumericRegisters(count, initial)) memory bank, count 1..32767 and optional INTEGER/REAL values; no default register count, implicit zeros or controller backend; optional ExecutionContext numeric bank and explicit JSON save/load',
        status='Portable codes: 0 success, REGISTER_UNINITIALIZED=1 for absent value, REGISTER_OUT_OF_RANGE=2 outside explicit count; type/storage/initialization/overlap/context failures raise before operation writes; no native alarm mapping',
        read='GET_REG writes real_flag, only the selected exact INTEGER/REAL value output and status; preserve unused numeric output; missing/out-of-range reads write status only',
        write='SET_INT_REG stores INTEGER, SET_REAL_REG stores Python float with ordinary numeric promotion; successful writes persist in the explicit bank across runs/shared programs; out-of-range writes preserve the bank',
        evaluation='Inputs then exact writable outputs once left-to-right; outputs disjoint before bank access; prior effects retained on error; normal FOR/CONFIG/POSITION guards and frame cleanup',
        observations='Program.register_requests returns defensive procedure/register number/line/operation/status/outcome records reset at run start; values omitted',
        names='Pythonic fallback procedures preserve internal routines and ordinary declarations; other controller identifiers remain blocked; strict future work',
        boundary='Explicit offline memory model only, no robot communication, remote/group registers, R[] syntax, native count/error/persistence/initial-value or controller acceptance claim; comments use the separate offline comment API',
        controller_validated=False)
    report['bare_function_policy']['microsecond_clock'] = 'In Pythonic mode an unshadowed GET_USEC_TIM value name resolves as a zero-argument clock function; internal routines and local/global variables/constants retain precedence'
    report['bare_function_policy']['current_program'] = 'An unshadowed CURR_PROG value name resolves as a zero-argument STRING[12] function reporting the executing module; internal routines and local/global declarations retain precedence'
    report['microsecond_timer_policy'] = dict(
        functions=sorted(TIMER_FUNCTIONS),
        counter='Portable two-minute ring: nonnegative host microseconds modulo 120000000; default time.monotonic_ns() // 1000; no calendar clock or controller epoch',
        adapter='Program(clock_us=...) optionally supplies synchronous nonnegative Python integer microseconds; no sampling at construction/run start; booleans, negative, floating and asynchronous responses rejected',
        subtraction='GET_USEC_SUB(later,earlier): INTEGER counters each in 0..119999999; result (later-earlier) modulo 120000000; valid elapsed interpretation requires one clock and intervals shorter than two minutes',
        evaluation='Once in source order, ordinary short circuiting, step/FOR/frame protections and prior effects retained; timer errors preserve pending assignment target; sticky ABORT takes precedence',
        observations='Program.clock_reads returns defensive line/adapter/outcome/counter records, reset at run start; failed reads have no counter; no raw unbounded clock samples retained',
        names='Pythonic fallback functions preserve internal routines and ordinary declarations; GET_USEC_TIM also supports unshadowed bare value syntax',
        boundary='Host elapsed-time approximation only; two-minute period and encoding are explicit portable choices, no native tick/overflow/precision/scheduling or controller acceptance claim; GET_TIME/SET_TIME use the separate explicit calendar service; strict future work',
        controller_validated=False)
    report['time_text_policy'] = dict(
        procedures=sorted(TIME_TEXT_PROCEDURES),
        grammar='ASCII DD-MMM-YYYY HH:MM[:SS], fixed English months case-insensitive, outer whitespace allowed; omitted seconds zero; Gregorian dates in 1980..2107; invalid text writes INTEGER zero',
        packing='GET_TIME table: year since 1980 in bits 31..25, month 24..21, day 20..16, hour 15..11, minute 10..5, two-second increments 4..0; floor odd seconds; signed 32-bit bit-pattern representation',
        formatting='Canonical 20-character DD-MMM-YYYY HH:MM:SS, uppercase English months independent of locale; reject invalid packed fields and output capacity below 20 before writing',
        evaluation='Capture source then writable target once left-to-right; convert after argument capture; retain prior effects on errors; ordinary initialization, FOR, CONFIG/POSITION and frame protections',
        names='Pythonic fallback procedures; explicit internal routines retain signatures/effects and ordinary variables remain usable',
        boundary='These conversions are pure data; GET_TIME/SET_TIME use the separate explicit calendar service; no timezone, implicit host/controller clock access, native odd-second/format/invalid-packed equivalence or controller acceptance; strict remains future work',
        controller_validated=False)
    report['wait_policy'] = dict(
        syntax='WAIT FOR one supported BOOLEAN expression; existing AND/OR short-circuit rules and ordinary expression/routine effects',
        evaluation='Evaluate once per check until true; no yield after a true check; after each false check call the existing synchronous sleep callback with 0.0 seconds',
        execution='Every condition test uses the normal execution step budget, including repeated false checks; function statements also count; this is not a wall-clock timeout',
        effects='WAIT propagates potential host-delay effects through routines; retain condition/callback effects and ordinary FOR protections, ABORT and frame cleanup; callback failures are source-located and not retried',
        boundary='Pythonic polling and optional cooperative EVENT checks; no acquired hardware I/O, motion conditions, native controller scheduling or timing acceptance; strict remains future work',
        controller_validated=False)
    report['position_comparison_policy'] = dict(
        operator='>=< on complete POSITION, XYZWPR or XYZWPREXT, including mixed operands; BOOLEAN result',
        context='Explicit Program(pose_tolerance=(location_mm, orientation_deg, check_config)) required when executed; finite nonnegative location bound, orientation in 0..180 and exact BOOLEAN; immutable per-instance copy, no defaults or controller discovery',
        metric='Inclusive Euclidean location distance and shortest rotation angle in degrees; relative matrix transpose(Ra)*Rb, atan2 of half skew norm and clamped half(trace-1); no relative tolerance; rounded Python floats',
        configuration='If check_config is true, require every CONFIG field to match; otherwise ignore differences after complete validation',
        external_axes='XYZWPREXT requires explicit external_tolerance scalar or three-axis tuple; inclusive absolute differences, missing plain-pose axes equal zero',
        evaluation='Evaluate and validate each operand once left-to-right before later effects; check both complete proper poses even when another comparison would be false; preserve prior effects and destination on failure',
        boundary='No scalar/VECTOR/JOINTPOS comparisons, implicit tolerances or native tolerance/configuration metric equivalence; strict remains future work',
        controller_validated=False)
    report['position_axis_policy'] = dict(
        functions='APPROACH returns positive Z; ORIENT returns positive Y; exact POSITION and Pythonic XYZWPR operands; internal routines and ordinary names retain precedence',
        mapping='POSITION APPROACH/ORIENT columns; XYZWPR uses frame_policy Z-Y-X rotation; return independent writable VECTOR without normalizing or repairing input',
        validation='Require a complete finite structurally exact pose and CONFIG; POSITION uses frame_policy proper-matrix checks with absolute tolerance 1e-9',
        evaluation='Evaluate once and detach result before later expressions or target effects; unchanged assignment on failure, earlier effects retained; ordinary FOR and frame cleanup',
        boundary='No XYZWPREXT/JOINTPOS/VECTOR operands, missing/default orientation, controller context, native XYZWPR overload or configuration validity claim; strict remains future work',
        controller_validated=False)
    report['position_conversion_policy'] = dict(
        scope='Whole-value assignments between exact POSITION and XYZWPR only; variables, fields, elements and compatible explicit RHS results; not automatic parameter/RETURN or whole-array coercion',
        mapping='NORMAL/ORIENT/APPROACH are X/Y/Z rotation columns; LOCATION is XYZ; copy CONFIG independently; use frame_policy Z-Y-X and canonical Euler choices',
        matrix='Require complete finite POSITION with unit column norms, pairwise orthogonal columns and determinant +1, each within absolute tolerance 1e-9; no inferred axes or matrix repair',
        ownership='Compute/copy complete conversion before target evaluation; stable destination storage and recursively read-only POSITION orientation; prior effects retained and no assignment on conversion failure',
        boundary='No POSITION/XYZWPR constructor cast syntax, other positional conversions, external axes, joint kinematics, native tolerance/angle/configuration equivalence or controller context; strict remains future work',
        controller_validated=False)
    report['frame_policy'] = dict(
        operands='Explicit complete POSITION or XYZWPR values; relative : composes left frame with right local pose; INV reverses a pose; FRAME constructs a frame from three or four points as a Pythonic fallback',
        result_type='INV preserves operand type; colon and FRAME return POSITION if any operand is POSITION, otherwise XYZWPR; infer exact types without implicit interface coercion',
        position_matrix='NORMAL/ORIENT/APPROACH are rotation columns; LOCATION is XYZ; validate complete finite proper matrices within absolute 1e-9 norm/dot/determinant tolerance; direct matrix calculation and checked POSITION results, without Euler round trip or matrix repair',
        rotation='Column vectors with Rz(r) Ry(p) Rx(w), degree angles reduced modulo 360 before trig; rounded Python float arithmetic',
        orientation='XYZWPR results: canonical P in -90..90 and W/R in [-180,180); hypot(R00,R10)<=1e-12 chooses W=0 and places remaining rotation in R; POSITION results retain recursively read-only rotation columns',
        configuration='Composition copies right CONFIG; INV copies input CONFIG; FRAME copies first or optional fourth CONFIG as data, without recalculating robot turns or reachability',
        constructor='FRAME: X points from first to second point; third sets positive XY half-plane and right-handed Z; origin is first or optional fourth point; first/second separation and third distance from their line must each be >=10 mm; derived differences/distances finite; ignore input orientations after complete operand validation',
        evaluation='Left-to-right once; snapshot each complete operand before later operand effects; independent result; existing assignment/argument/FOR protections',
        boundary='No XYZWPREXT/JOINTPOS/VECTOR transform operands, automatic parameter/RETURN coercion, external axes, UFRAME/UTOOL discovery, kinematics or native type/Euler/configuration equivalence; strict remains future work',
        controller_validated=False)
    report['directive_policy'] = dict(
        allowed=['%ALPHABETIZE','%COMMENT','%ENVIRONMENT','%NOLOCKGROUP'],
        scope='Syntax-checked top-level metadata only; preserve source order, raw text and decoded values; generated Program.source_directives contains immutable normalized pairs',
        environment='One bare ASCII letter-starting name, 1..36 characters, normalized uppercase; record requirements without loading definitions, files, modules or controller facilities; source symbols/calls still checked individually',
        comment='One decoded ASCII literal of at most 16 characters before CONST/TYPE/VAR/routines; preserve literal comment/ampersand characters and doubled apostrophes; duplicate attributes rejected',
        alphabetize='Record display-order request; offline storage/snapshot order remains declaration order',
        required_environments=list(dict.fromkeys(row['argument'] for row in report['directive_metadata'] if row['name'] == '%ENVIRONMENT')),
        boundary='No unknown/runtime directives, includes, binary environment loading, implicit built-ins, task/group ownership, persistence, scheduler or device-default mapping; strict remains future work',
        controller_validated=False)
    report['mode_policy'] = dict(selected=mode, strict='Future milestone; not publicly available',
                               scope='Practical Python numeric, typed input, text output, STRING and evaluation behavior; checked source forms, types, initialization and ownership')
    report['read_policy'] = dict(
        destinations='Omitted-file READ with 1..1024 scalar destinations or CR markers; INTEGER/BOOLEAN/REAL/STRING variables, fields/elements and BYTE/SHORT leaves',
        capture='Resolve writable destinations once left to right before one input callback; retain concrete capacities and captured storage',
        callback='Explicit synchronous Program(read=...) receives defensive line/type metadata; returns an exact list/tuple with one typed value per target; no automatic retry',
        validation='Validate the entire response before assigning in destination order; repeated aliases use the last value; STRING input at most 254 ASCII characters before destination truncation',
        failures='No response assignment on callback/result failure; earlier target/callback effects remain; callback interruptions propagate; ordinary routine and FOR cleanup applies',
        observations='Program.read_requests returns defensive metadata/outcome copies, reset at run start; input values are not retained in these observations',
        line_control='CR positions are optional line_breaks offsets in callback metadata and translation reads; repeated/leading/CR-only requests supported; markers consume no response values',
        formatting='At most two INTEGER expressions per scalar: width 0..254 (zero default), integral base 0 or 2..16, STRING quote mode 0/2; REAL/BOOLEAN second format evaluated and ignored; concrete optional per-target format_specifiers metadata',
        format_order='Capture each destination, then its width and second format once; validate formats before the next destination; callback runs after all captures; typed responses are already decoded',
        text_adapter='runtime.TextInput: explicit ASCII text, Python int/float fields, case-insensitive BOOLEAN tokens, STRING remainders or quoted fields with doubled-apostrophe escapes; exact positive widths stay on one physical line; persistent defensive cursor; CR discards current remainder',
        scripts='Choose --read-values JSON batches or --read-text UTF-8 ASCII text, with optional BOM; explicit paths and mutually exclusive adapters',
        boundary='No implicit stdin, controller file/device access, binary transfer, native EOF/alarm/status mapping, aggregate destinations, CONFIG subfields or POSITION orientation writes',
        controller_validated=False)
    report['evaluation_policy'] = dict(
        operands='Evaluate once left to right; VECTOR values captured before the next operand',
        boolean='BOOLEAN AND/OR short circuit using Python; INTEGER AND/OR remain eager bitwise operations',
        arguments='Evaluate actuals once left to right; bare storage captures a live reference, grouped/expression actuals capture independent values',
        subscripts='Evaluate the array base, then subscripts once left to right; bounds/storage checks follow subscript evaluation',
        assignment='Evaluate and capture RHS first, then resolve target base/subscripts and assign; aggregates captured by checked independent copy',
        conversions='Evaluate inputs and output references in source order before conversion; bare aggregate inputs remain live storage; existing overlap/type/context checks remain',
        for_bounds='Evaluate initial once and assign counter, then evaluate final once; capture resulting counter and inclusive stop for iteration',
        failure='Stop on the first runtime error or ABORT; retain earlier effects, skip later evaluations and unwind routine frames',
        controller_validated=False)
    report['for_policy'] = dict(
        counters='INTEGER globals in the program or parameter-free routines; fresh routine-local INTEGER variables; parameterized routines still require fresh local counters',
        routine_calls='Allowed when transitive potential global writes exclude active global counters; fresh local counters are separate storage',
        counter_arguments='Bare references allowed only to transitively read-only formals; expressions/grouping and INTEGER-to-REAL promotion pass independent values',
        write_proof='Flow-insensitive fixed point over recursive calls, direct assignments, FOR initialization and built-in outputs; map writable formal actuals back to caller globals/formals; do not infer dead branches',
        return_from_for='Evaluate and check RETURN value before clearing counters and leaving the routine frame; parameter-free routines may use global counters',
        bounds='Evaluate initial and assign counter, then final once; capture resulting counter/start and inclusive final; existing chosen Pythonic bound order',
        cleanup='After successful initial assignment, finally clear each counter on normal/empty completion, RETURN, ABORT, final-bound failure, body error, callback failure/interruption and step/call-depth exhaustion',
        initial_failure='If the initial expression or checked initial assignment fails, do not clear that counter; previous storage and earlier effects remain',
        global_or_formal_counter_calls_and_returns='Global counters follow write proof and cleanup; formal counters and nonlocal counters in parameterized routines remain blocked',
        jumps_and_labels_inside_for='blocked', controller_validated=False)
    report['abort_policy']['for_boundary'] = 'Pythonic FOR scopes clear initialized counters during ABORT unwinding; prior non-counter effects remain'
    report['using_policy'] = dict(
        selectors='Named STRUCTURE variables or dotted STRUCTURE field paths; resolve against enclosing aliases only; selectors in the same list do not affect one another',
        priority='Inner fields override outer fields; right-most matching selector wins within one list; unmatched outer fields remain available; restore outer bindings after the block',
        resolution='Expand bare aliases to copied absolute field paths before type, call, effect and control-flow checks; inserted roots are not resolved again; no dynamic caller scope',
        nested_scopes='Lexical scopes; depth zero at the outermost USING; scope id, parent id, source selectors and resolved paths in using_scopes',
        call_name_collisions='Explicit expression calls and procedure call statements resolve routines; a bare expression resolves a matching field before a zero-argument function',
        constant_name_collisions='Matching fields shadow global/local constants only inside the scope; CASE labels still require compile-time constants',
        shadowed_for_counters='blocked; fields cannot own FOR counters',
        boundary='Named user STRUCTURE types only; no indexed, grouped or function-result selectors, implicit nested-field search or native namespace/alias-lifetime claim',
        controller_validated=False)
    report['numeric_policy'] = dict(
        mode=mode, real_model='python_float', arithmetic='Python float +, -, *, /; finite results required',
        sqrt='math.sqrt for nonnegative finite inputs', exp='math.exp', ln='math.log for positive finite inputs',
        round='Python round to INTEGER; ties to even', trunc='math.trunc toward zero',
        mod='Python remainder; result has divisor sign', integer='Existing checked signed-32-bit storage, excluding MAXINT',
        rounding_dependent_values='Accepted using Python floating-point rounding',
        underflow_threshold='Host float underflow and subnormals', signed_zero='Preserved by scalar float operations',
        controller_validated=False)
    report['trig_policy'] = dict(
        functions=list(rt.UNARY_TRIG_FUNCTIONS), angle_units='degrees',
        input_policy='Finite Python floats; inverse arguments in -1..1',
        runtime='Exact identity tables where available; otherwise Python math with degree/radian conversion; forward angles reduced by period',
        tan_odd_right_angles='Explicit domain rejection', controller_validated=False)
    report['atan2_policy'] = dict(
        argument_order=['x', 'y'], result='math.degrees(math.atan2(y, x)), in -180..180',
        coordinates='Finite floats in all quadrants', origin='Explicit undefined-domain error', controller_validated=False)
    report['data_record_policy']['values'] = 'Finite Python float REAL components; existing CONFIG turn/BOOLEAN checks'
    report['data_record_policy']['position_initialization'] = 'No orientation defaults; initialize POSITION through explicit XYZWPR assignments under position_conversion_policy or complete geometry results under frame_policy'
    report['data_record_policy']['boundary'] = 'POSITION/XYZWPR assignments follow position_conversion_policy and explicit geometry follows frame_policy; no other positional coercion, implicit group/frame context, builtin USING, record I/O, registers or motion'
    report['positional_routine_policy']['boundary'] = 'Exact parameter/RETURN types; whole assignments follow position_conversion_policy; no controller ABI, native kinematics or orientation defaults; explicit POSITION/XYZWPR transforms follow frame_policy'
    report['vector_routine_policy']['boundary'] = 'VECTOR copying supplies no frame context; VECTOR transforms, implicit positional conversion and native runtime equivalence remain unsupported'
    report['vector_policy'].update(
        scaling='Finite Python floats; division requires nonzero denominators',
        products='Cross/dot products allow rounded intermediates and zero/parallel cross products',
        numeric='Initialized finite float components; rounded products and finite results',
        constructor='VEC(x,y,z): three INTEGER/REAL numeric values, promoted and checked as finite Python floats in a fresh VECTOR',
        constructor_name='VEC is a fallback expression constructor; an explicitly declared internal VEC routine keeps precedence and ordinary signature/effect checks',
        unary='Unary + and - on VECTOR return independent checked component copies',
        precedence='Cross/dot above multiplication/division, above unary signs and addition; same-level products associate left to right; parentheses override',
        boundary='No ordered VECTOR relations, VECTOR transform operands, kinematics or controller validation')
    report['pos_policy'] = dict(
        constructor='POS(x,y,z,w,p,r,c) returns a fresh XYZWPR with independent CONFIG data; explicit internal POS routines keep precedence',
        coordinates='Six finite Python numeric values; INTEGER/BYTE/SHORT promoted to REAL; x/y/z in -10000000..10000000 mm, w/p/r in -180..180 degrees',
        configuration='Exact complete CONFIG shape, initialized checked fields and existing turn range -8..7; copied without robot-specific validity inference',
        evaluation='Evaluate arguments once left to right before constructor-specific bounds/config checks; ordinary expression failures stop later expressions; no destination write on failure',
        boundary='POS returns exact XYZWPR; subsequent whole assignments follow position_conversion_policy; no implicit CONFIG, group/frame/robot context, XYZWPREXT coercion, kinematics, native pause/status or controller validity claim',
        controller_validated=False)
    report['config_text_policy'] = dict(
        procedures=sorted(CONFIG_TEXT_PROCEDURES),
        grammar='ASCII case-insensitive N/F, R/L, D/U, B/T flag pairs, at most one per pair in any order; optional three comma-separated decimal turns -8..7; omitted flags false and omitted turns zero as portable values',
        canonical='Wrist, shoulder, elbow, front flags separated by spaces, followed by three comma-separated turns; include every field',
        status='CNV_STR_CONF: 0 success; portable 1 invalid text/range, retaining CONFIG; not a native controller code; malformed storage/type/ASCII/length raises without output writes',
        formatting='CNV_CONF_STR snapshots complete initialized CONFIG before target capture; insufficient STRING capacity raises without truncation or mutation',
        evaluation='Source then target then status once; preflight output types/shape/disjointness before writes; preserve captured aggregate storage, prior effects and ordinary cleanup',
        names='Fallback procedures; explicit internal routines of the same name retain their signatures and effects',
        boundary='No robot validity, group masks/defaults, CNV_CNF_STRG, native status/alarm mapping or controller contact; strict remains future work',
        controller_validated=False)
    report['unpos_policy']['input'] = 'XYZWPR storage; initialized finite REAL components and bounded CONFIG'
    report['unpos_policy']['boundary'] = 'No POSITION/XYZWPREXT/JOINTPOS coercion, frame/kinematic conversion, controller config-validity, status or alarm mapping; UNPOS still requires captured source storage'
    report['conversion_policy'].update(
        parse='Python int(text, 10); invalid numeric text clears output; checked INTEGER storage',
        real_parse='Python float(text), including whitespace and lowercase exponents; finite result required; invalid numeric text clears output',
        real_format='Python float formatting; nonnegative precision fixed, negative precision uppercase scientific using absolute digits; -254..254; leading blank; minimum width 1..254; capacity overflow marker',
        real_format_guard='Python decimal rounding allowed; precision/width outside prototype bounds remain blocked',
        format='Signed bases 2..16, with base 0 selecting decimal; leading blank; minimum width 1..254; capacity overflow marker',
        nondecimal_format='Minimal digits 0..9/A..F, optional minus, no prefix; Pythonic formatting convention',
        invalid_base='Outside 0 or 2..16 clears output after width/input checks',
        other_formats='Input follows Python int/float grammar; output fixed/scientific or integer bases')
    report['literal_policy']['boundary'] = 'ASCII only, one physical token; no backslash escapes or multiline token splicing; Pythonic quoted WRITE doubles embedded apostrophes'
    report['write_policy'] = dict(
        source='Omitted-file WRITE with 1..1024 scalar expressions or CR items',
        input='Initialized ASCII STRING, BOOLEAN, signed INTEGER/BYTE/SHORT or finite REAL; combined rendered output at most 254 characters',
        evaluation='Items left to right; each value then width then second format evaluated once; validate/render item before the next; combined length checked after all items; one outer request after successful rendering',
        formatting='INTEGER format expressions; STRING width/alignment; numeric/BOOLEAN widths 0..254; zero selects natural width; static literal ranges checked during translation, others at runtime',
        string='Modes 0/1 unquoted left/right; 2/3 quoted left/right with leading blank, paired quotes and doubled apostrophes; truncate complete escaped characters to fit; quoted widths 1/2 promote to 3; width 0 or >254 selects natural rendered length',
        integer='Signed decimal or bases 2..16 (0 selects decimal); one leading blank; uppercase A..F; nondecimal widths zero-fill after the minus sign',
        real='Python float formatting; default five fractional digits in uppercase scientific notation; signed precision -254..254 selects scientific when negative, fixed otherwise',
        boolean='TRUE/FALSE with one leading blank and optional minimum width; no second specifier',
        newline='CR renders one LF character; no automatic newline appended',
        adapter='Default per-run request recorder; Program(write=...) receives one complete statement as a synchronous text callback returning None',
        trace='Copied text/line/adapter_outcome records; failures retain prior expression/output effects and unwind routine frames',
        boundary='No explicit file/device access, binary transfer, aggregate output or controller IO_STATUS; existing type, initialization, ASCII and bounded output checks remain',
        controller_validated=False)
    report['string_result_policy'] = dict(
        source='Internal STRING or STRING[capacity] function results; explicit calls and bare zero-argument function names',
        capacity='STRING defaults to 254; explicit global constant capacity in 1..254',
        returned_value='Initialized ASCII Python string; evaluate once and right-truncate to the result capacity before routine cleanup',
        use='Assignments, string expressions/comparisons, built-ins, WRITE, RETURN forwarding and STRING value arguments',
        boundary='Existing type, FOR and call-depth guards remain; chosen Pythonic evaluation order; no native controller STRING ABI claim',
        controller_validated=False)
    report['string_operation_policy'] = dict(
        substring='SUB_STR(source,start,count) uses source[start-1:start-1+min(count,254)]; positive one-based start, nonnegative count; clip at source end; zero count or start past end returns empty',
        substring_capacity='At most 254 characters before consumption; destination or routine result may truncate further; source expressions may be longer',
        search='INDEX(source,search) uses source.find(search)+1; first exact case-sensitive match, zero when absent, one for an empty search including an empty source',
        characters='STR_LEN counts ASCII characters; CHR accepts codes 0..127; ORD requires a one-based index inside current contents',
        evaluation='Evaluate actuals once left to right before validating the operation; capture immutable STRING values before later argument effects; skip later expressions after an evaluation error',
        failures='Type, initialization, ASCII and INTEGER range checks remain; no destination assignment on operation error; earlier argument effects remain, including destination mutations; unwind routine frames',
        controller_validated=False)
    report['string_value_policy'] = dict(
        arguments='Initialized ASCII literals, constants, expressions, function results and grouped scalar storage; input length at most 254',
        storage='Independent writable temporary with capacity 254 for plain STRING formals or the declared bounded alias capacity; assignment right-truncates and clear sets UNINITIALIZED',
        references='Bare ordinary STRING variables/fields/elements preserve caller storage and actual capacity',
        effects='Potential formal writes remain reported; grouping/value passing creates no writeback alias',
        boundary='Chosen Pythonic temporary capacity and evaluation order; existing type and ownership checks remain',
        controller_validated=False)
    for key in ('delay_policy', 'write_policy', 'vector_routine_policy', 'structure_routine_policy', 'positional_routine_policy'):
        report[key]['effects'] = 'Potential effects propagate through routine calls; Pythonic evaluation order determines when they occur'
    report['local_constant_policy']['arguments'] = 'Scalar constants pass as independent value temporaries; STRING temporaries are writable with capacity 254'
    report['data_record_policy']['parameters'] = 'Bare exact-type records keep references; grouped storage and function results use checked independent value copies; CONFIG scalar subfields pass by value'
    report['array_routine_policy'].update(
        results='Internal named ARRAY types or anonymous ARRAY with omitted, fixed, wildcard or mixed dimensions; up to three logical dimensions; INTEGER/BOOLEAN/REAL/BYTE/SHORT, bounded STRING, record, joint and prior named ARRAY elements',
        declarations='Named results require exact nominal identity; anonymous results require anonymous outer storage and matching component layout; global constant sizes or runtime wildcard dimensions; no resizing or flattening',
        use='ARRAY results compose in grouped assignments, compatible routine value arguments, RETURN forwarding, ARRAY_LEN returning the first dimension, and explicit result subscript/field reads',
        references='Bare ARRAY storage keeps caller references; grouped storage and function results create checked independent writable copies with concrete shape, identity and element capacities')
    report['array_value_policy'] = dict(
        source='Grouped whole arrays/subarrays/array fields and compatible ARRAY function results',
        storage='Checked deep copy with every scalar leaf known and initialized; preserve concrete shape, nominal identities and STRING capacities',
        binding='Ordinary writable private reference; bare forwarding shares the private storage, grouping again copies it; no copy-back on completion, error or ABORT',
        evaluation='Capture once at the actual argument position in left-to-right evaluation; later actuals cannot mutate an earlier private copy',
        limits='Existing prototype bound of 32767 scalar leaves; exact formal rank/type checks; no resizing, coercion, partial copies or acquired robot context',
        controller_validated=False)
    report['aggregate_access_policy'] = dict(
        source='Subscripts and fields after explicit function calls or grouped aggregate expressions',
        evaluation='Evaluate the aggregate once before subscripts; existing comma-separated subscript and field type checks apply',
        ownership='Returned aggregates remain detached; references into a returned temporary keep only its private storage alive',
        protection='Existing POSITION read-only descendants and CONFIG field passing rules remain',
        boundary='Bare function names used directly as receiver roots remain storage; use an explicit call or group; chained ARRAY subscripts remain blocked',
        controller_validated=False)
    report['bare_function_policy']['arrays'] = 'ARRAY values compose in compatible value contexts, grouping, RETURN and ARRAY_LEN returning the first dimension; explicit calls or grouping allow aggregate access'
    report['array_length_policy'] = dict(result='First concrete dimension, like Python len; flat matrices and named nested arrays supported',
                                       evaluation='Evaluate the array once; no scalar-leaf initialization required',
                                       boundary='No total-element count, dimension argument, reshape or flattening', controller_validated=False)
    report['array_routine_policy']['boundary'] = 'No unspecified STRING result-element capacities, anonymous nested ARRAY components, representation/identity erasure, external routines or native ABI/runtime claim'
    report['type_alias_policy'] = dict(
        resolution='Transparent aliases to supported scalar, bounded STRING, data record, joint and previously defined named types; alias chains resolve eagerly in declaration order',
        identity='Aliases retain the original ARRAY/STRUCTURE identity; a fresh ARRAY or STRUCTURE definition still creates a distinct nominal type',
        capacity='Keep declared STRING capacities, ARRAY shapes and joint widths; bounded STRING alias formals require matching reference capacity and use private truncating value temporaries of that capacity',
        boundary='No forward/self/cyclic aliases, external FROM types, local TYPE sections, wildcard TYPE dimensions or standalone BYTE/SHORT storage/formals/results',
        controller_validated=False)
    report['named_array_policy'].update(
        parameters='Same named type by reference or checked value copy; generic rank-matched ARRAY formals preserve the concrete actual identity',
        aliases='Transparent aliases preserve the original nominal identity; inline anonymous nested ARRAY syntax remains blocked',
        results='Named outer ARRAY results preserve exact nominal identity, shape and initialized independent copies')
    for key in ('vector_routine_policy', 'structure_routine_policy', 'positional_routine_policy', 'array_routine_policy'):
        report[key]['boundary'] = (report[key]['boundary'].replace('direct STRING results, ', '').replace(' or direct STRING results', '')
                                   .replace('whole ARRAY value arguments, ', '').replace('whole ARRAY values, ', '').replace(', whole ARRAY values', ''))
    strict_only = ('REAL uses exact binary32', 'Underflow follows the manual', 'Signed MOD with negative',
                   'SQRT accepts', 'SIN/COS/TAN', 'ATAN2 accepts', 'CNV_REAL_STR accepts',
                   'CNV_STR_INT accepts', 'CNV_INT_STR accepts', 'WRITE accepts', 'STRING reference parameters retain',
                   'Boolean operands evaluated eagerly', 'Side-effecting routine calls in multi-argument',
                   'Whole ARRAY reference parameters support', 'ARRAY_LEN on multidimensional arrays',
                   'INDEX with an empty search', 'SUB_STR beyond the source end',
                   'FOR-body routine calls and RETURN require', 'USING qualifies fields lexically',
                   'Named arrays/subarrays retain nominal identity')
    report['limitations'] = [item for item in report['limitations'] if not item.startswith(strict_only)]
    report['limitations'].append('Pythonic numerical results use Python floating-point and math conventions; strict mode is a future milestone')
    report['limitations'].append('ARRAY value arguments require every scalar leaf known and initialized; concrete type, shape, nominal identity and capacity are preserved without resizing')
    report['limitations'].append('Pythonic SUB_STR keeps positive one-based starts and nonnegative counts; clips at source end and 254 characters; INDEX empty search returns one')
    report['limitations'].append('FOR calls must exclude active-global-counter writes; active references require read-only formals; direct writes, formal counters, nonlocal counters in parameterized routines and in-loop jumps remain blocked')
    report['limitations'].append('USING supports lexical nesting and dotted named STRUCTURE selectors; indexed/call/grouped selectors, builtin record selectors and field FOR counters remain blocked')
    report['limitations'].append('TYPE aliases resolve prior definitions transparently; aggregate identity and capacities remain checked; inline anonymous nested ARRAY syntax, local TYPE sections and external FROM types remain blocked')
    report['frame_policy']['boundary'] = 'POSITION/XYZWPR/XYZWPREXT operands; no JOINTPOS/VECTOR frames, automatic interface coercion, group/frame discovery or native kinematics; see extended_geometry_policy'
    report['position_axis_policy']['boundary'] = 'POSITION/XYZWPR/XYZWPREXT only; complete checked poses, no robot acquisition or orientation defaults'
    report['position_conversion_policy']['boundary'] = 'Whole POSITION/XYZWPR/XYZWPREXT assignments only; exact routine/array interfaces, checked proper matrices; widening zeros axes and narrowing drops axes'
    report['extended_geometry_policy'] = dict(
        types=['POSITION','XYZWPR','XYZWPREXT'],
        external_axes='Three REAL metadata fields; INV and MIRROR preserve; colon selects right extended operand else left; FRAME selects origin axes else zero',
        mirror='Frame XZ plane reflection; orientation=True reverses local Y after reflection to retain a proper rotation; CONFIG preserved',
        model='Explicit callbacks or configured standard-DH models; FK, bounded numerical IK, reachability search, joint limits, groups/frames/tools and tail external joints',
        boundary='Generic configured models only; no calibrated native robot configuration branches, collisions, motion or controller acceptance claim',
        guide='docs/portable-projects.md',controller_validated=False)
    report['abort_policy']['source']='Bare ABORT, handler action or explicitly registered task target; sticky offline termination'
    report['abort_policy']['boundary']='NOABORT can cancel pending cooperative requests, but cannot undo sticky termination; no controller motion cancellation, native persistence or restart acceptance'
    report['data_record_policy']['boundary'] = 'Checked positional data and whole pose conversions; registers and geometry use explicit services; no builtin USING, record I/O, motion or inferred group/frame context'
    report['pos_policy']['boundary'] = 'POS returns exact XYZWPR; whole assignments can convert poses under position_conversion_policy; no implicit routine/array conversion, robot context, native configuration validity or native pause/status'
    report['frame_policy']['operands'] = 'Explicit complete POSITION/XYZWPR/XYZWPREXT; colon composition, INV and three/four-point FRAME use checked frame math and explicit external metadata'
    report['frame_policy']['result_type'] = 'INV preserves representation; colon/FRAME prefer XYZWPREXT, then POSITION, then XYZWPR; external metadata follows extended_geometry_policy'
    report['position_conversion_policy']['scope'] = 'Whole assignments among POSITION, XYZWPR and XYZWPREXT; no automatic routine/RETURN or whole-array conversion'
    report['kinematic_assignment_policy']=dict(
        scope='Whole JOINTPOS to/from POSITION/XYZWPR/XYZWPREXT assignments, including individual fields/elements and function results; routine, RETURN and whole-array interfaces remain exact',
        context='Explicit robot model/adapters in the calling root task group with selected frame/tool maps; no model or frame/tool discovery',
        forward='Reuse JOINT2POS checks and supplied forward adapter; config_ref=0; independent CONFIG and external-axis outputs become Cartesian fields',
        inverse='Reuse POS2JOINT checks and supplied inverse adapter; require complete current joints as seed; source CONFIG and three external axes, with zero for absent plain-pose axes; config_ref=0',
        widths='Configured model width or JOINTPOS9 with zero unused axes; model inverse writes either width or padded nine slots; callbacks retain exact output width',
        ownership='Complete conversion and detached RHS precede target selector evaluation; failure preserves destination, earlier source/host effects remain; value-free KINEMATIC_ASSIGNMENT records',
        boundary='No implicit motion, current-state update, native branch selection, collision or certified reachability; no automatic JOINTPOS frame operators or whole-array/interface conversions; strict deferred',
        guide='docs/kinematic-assignments.md',controller_validated=False)
    report['pulse_policy']=dict(
        syntax='PULSE DOUT[port] FOR milliseconds [NOWAIT]; INTEGER operands captured once in source order; NOWAIT prohibited in handler actions',
        duration='Range 0..86400000 ms; zero does not change output or existing pulse; positive values round upward to multiples of 8 ms with deterministic modeled expiry',
        context='Explicit PortBank DOUT address; no physical output adapter; overlapping pulses reject; successful direct/indirect/host writes cancel the previous deadline',
        waiting='Blocking uses existing DELAY driver; synchronous sleep callback completion completes the logical pulse; scheduler parks the task and uses virtual time regardless of injected program clock',
        nowait='Nonblocking start; standalone clocks use captured clock_us or monotonic microseconds; checkpoints, port reads/snapshots and explicit poll_pulses service expirations without background threads',
        lifecycle='Pause permits expiration; normal completion retains pending pulse; abort/stop/failure freeze last modeled value and discard pending work on polling; linked calls belong to root caller',
        scheduler='Polls shared banks and drains its pending pulses even when owners complete or pause; idle jumps to waiting/pulse deadlines; cycle limits remain',
        persistence='JSON stores observed values and existing port metadata only; pending clocks/owners/deadlines are not serialized; service records are value-free PULSE start/wait outcomes',
        boundary='No controller scan jitter, polarity/complement modes, physical timing, automatic background expiry or native acceptance; strict remains future work',
        guide='docs/pulses.md',controller_validated=False)
    report['initialization_query_policy']=dict(
        builtin_records=['CONFIG','VECTOR','POSITION','XYZWPR','XYZWPREXT'],
        meaning='Whole builtin record is uninitialized when any nested leaf or complete nested record is uninitialized; inspect without initializing, copying or changing source storage',
        validation='Validate record schema and known scalar types/domains; inspect all fields even when another is uninitialized; no proper-rotation or robot/configuration validity query',
        operands='Variable, field or individual ARRAY-element storage; Pythonic parentheses unwrap storage; computed selectors evaluate once; constants and direct function/literal/constructor results rejected; existing temporary-field/element selectors retained',
        exclusions='Whole ARRAY, PATH, user STRUCTURE, FILE and QUEUE_TYPE remain blocked; BYTE unknown contents remain distinct from uninitialized state',
        boundary='Portable partial-record rule rather than native allocation flags; existing scalar/joint behavior and exact interfaces retained; strict remains future work',
        guide='docs/initialization-queries.md',controller_validated=False)
    report['data_record_policy']['initialization']='Scalar leaves start uninitialized; whole builtin-record UNINIT follows initialization_query_policy; copies still require complete values'
    report['limitations']=[item.replace('aggregate UNINIT remains blocked','whole user STRUCTURE and ARRAY UNINIT remain blocked') for item in report['limitations']]
    report['position_conversion_policy']['boundary']='Context-free Cartesian representation changes only; model-backed joint assignments follow kinematic_assignment_policy; exact routine/array interfaces and checked proper matrices remain'
    report['data_record_policy']['boundary']='Cartesian whole assignments follow position_conversion_policy; joint/Cartesian whole assignments require kinematic_assignment_policy; no automatic routine/array conversion or physical motion'
    report['positional_routine_policy']['boundary']='Exact parameter/RETURN types; whole assignments follow position_conversion_policy and kinematic_assignment_policy; no controller ABI, native branch selection or orientation defaults'
    report['position_axis_policy']['functions'] = 'APPROACH returns positive Z and ORIENT positive Y from complete POSITION/XYZWPR/XYZWPREXT; internal routines retain precedence'
    report['joint_geometry_policy']=dict(
        operations=[':', 'INV','FRAME','MIRROR','APPROACH','ORIENT','>=<'],
        conversion='Complete exact-width JOINTPOS operand snapshot becomes independent XYZWPREXT through the existing forward model/adapters, root task group and selected frame/tool; config_ref zero',
        result='Joint participation makes colon/INV/FRAME Cartesian XYZWPREXT; MIRROR remains XYZWPREXT, axes VECTOR and comparisons BOOLEAN; no implicit joint-space inverse solve',
        evaluation='Evaluate, snapshot and convert each joint once before later operands/arguments and assignment target selectors; preserve prior effects and sticky root abort; Cartesian-only behavior retained',
        context='Require supplied robot model/forward adapter and configured group/frame/tool; complete joints need no current-joint inverse seed; geometry does not change supplied current state',
        external_axes='Retain three forward metadata axes under existing INV/MIRROR/colon/FRAME rules; comparisons require explicit pose and external tolerances',
        observations='joint_geometry source sites include operation, body, line/column and source/result specs; runtime JOINT_GEOMETRY operation/line/outcome records are value-free; routine service effects propagate',
        boundary='Portable Cartesian interpretation, no raw joint algebra, implicit routine/RETURN/whole-array conversion, orientation defaults, calibration or native/controller equivalence; strict remains future work',
        guide='docs/joint-geometry.md',controller_validated=False)
    report['frame_policy']['operands']+='; JOINTPOS converts through joint_geometry_policy'
    report['frame_policy']['result_type']+='; JOINTPOS first becomes XYZWPREXT'
    report['frame_policy']['boundary']='Joint operands require explicit joint_geometry_policy context; VECTOR frames, automatic routine/RETURN/whole-array conversion and native kinematic equivalence remain blocked'
    report['extended_geometry_policy']['types'].append('JOINTPOS')
    report['position_axis_policy']['functions']+='; JOINTPOS uses explicit joint_geometry_policy conversion'
    report['position_axis_policy']['boundary']='Complete proper Cartesian inputs or model-backed JOINTPOS; no VECTOR/scalar inputs, inferred context or orientation defaults'
    report['position_comparison_policy']['operands']='POSITION/XYZWPR/XYZWPREXT and model-backed JOINTPOS under joint_geometry_policy'
    report['position_comparison_policy']['boundary']='Explicit pose and external tolerances, Cartesian metrics after joint conversion; no scalar/VECTOR or raw joint-coordinate comparisons, defaults or native equivalence'
    for key in ('vector_routine_policy','structure_routine_policy','positional_routine_policy','array_routine_policy'):
        report[key]['boundary'] = report[key]['boundary'].replace('external routines or ', '').replace('external routines, ', '')
    report['limitations'].append('New services follow explicit offline context and cooperative policies; binary file layout, task scheduling, handler timing, MIRROR orientation and external axes use documented portable conventions')
    return result
