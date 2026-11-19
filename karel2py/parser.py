"""Parse tokenized KAREL into source declarations, routines and statements."""
import re
from .compiler_language import (
    ARRAY_SCALARS,
    BLOCK_ENDS,
    BUILTINS,
    CONTROLLER_NAMES,
    DATA_RECORD_TYPES,
    NARROW_TYPES,
    PRECEDENCE,
    PREDEFINED_CONSTANTS,
    RESERVED,
)
from .syntax import Expr, Program, Routine, Statement
from .lexer import TranslationError, directive_content, tokenize
from . import extended as ex
from . import runtime as rt


class Parser:
    def __init__(self, source, filename, mode='strict'):
        self.continuations = []
        self.motion_setting_constants = {}
        self.in_motion_condition = False
        self.escaped_string_literals = []
        self.predefined_uses = []
        self.directive_metadata = []
        self.path_clause_uses = []
        self.inline_array_uses = []
        self.storage_declarations = []
        self.tokens = tokenize(source, filename, continuations=self.continuations)
        self.position = 0
        self.filename = filename
        self.mode = mode
        self.in_condition=False
        self.in_handler_actions=False
        self._block_end_stack=[]

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
        predefined_types = set(rt.PREDEFINED_STRUCTURES)|set(rt.ASSOCIATION_TYPES) if self.mode == 'pythonic' else set()
        if self.current.kind != 'NAME' or self.current.value in RESERVED | BUILTINS | predefined_types or self.current.value.startswith('$'):
            self.error('E_NAME', 'Expected a non-reserved identifier')
        return self.take()

    def metadata_directive(self, token, declarations_started):
        content, _ = directive_content(token.value)
        head = re.match(r'%[A-Za-z][A-Za-z_0-9]*', content)
        name = head[0].upper() if head else ''
        argument = None
        disposition = 'Offline metadata only; no task/group ownership'
        if content.upper() == '%NOLOCKGROUP':
            name = '%NOLOCKGROUP'
            if any(row['name']=='%LOCKGROUP' for row in self.directive_metadata):
                self.error('E_DIRECTIVE_VALUE','LOCKGROUP and NOLOCKGROUP cannot be combined',token)
        elif self.mode != 'pythonic' or name not in ('%ENVIRONMENT', '%COMMENT', '%ALPHABETIZE',*rt.TASK_DIRECTIVES,*rt.SOURCE_DIRECTIVES):
            self.error('E_DIRECTIVE', 'Directive has no implemented runtime mapping', token)
        elif name in rt.SOURCE_DIRECTIVES:
            if declarations_started: self.error('E_DIRECTIVE_POSITION','Source policy directives must precede declarations',token)
            previous={row['name'] for row in self.directive_metadata}
            if name in previous: self.error('E_DIRECTIVE_DUPLICATE','Source policy directives cannot be repeated',token)
            if name in rt.SOURCE_FLAG_DIRECTIVES:
                if content.upper()!=name: self.error('E_DIRECTIVE_SYNTAX','Source flag directive accepts no arguments',token)
            elif name=='%LOCKGROUP':
                match=re.fullmatch(r'%LOCKGROUP\s*=\s*([0-9]{1,2}(?:\s*,\s*[0-9]{1,2}){0,31})',content,re.I)
                if not match: self.error('E_DIRECTIVE_SYNTAX','LOCKGROUP requires a comma-separated group list',token)
                argument=tuple(int(part.strip()) for part in match[1].split(','))
                if any(not 1<=n<=32 for n in argument) or len(argument)!=len(set(argument)):
                    self.error('E_DIRECTIVE_VALUE','LOCKGROUP requires distinct groups in 1..32',token)
                if '%NOLOCKGROUP' in previous: self.error('E_DIRECTIVE_VALUE','LOCKGROUP and NOLOCKGROUP cannot be combined',token)
            else:
                match=re.fullmatch(r'%[A-Za-z]+\s*=\s*([0-9]{1,10})',content)
                if not match: self.error('E_DIRECTIVE_SYNTAX','Source numeric directive requires one unsigned INTEGER literal',token)
                argument=int(match[1]);lo,hi=rt.SOURCE_DIRECTIVE_RANGES[name]
                if not lo<=argument<=hi: self.error('E_DIRECTIVE_VALUE','Source numeric directive exceeds its portable range',token)
            if {name,*previous}>={'%CMOSVARS','%SHADOWVARS'}:
                self.error('E_DIRECTIVE_VALUE','CMOSVARS and SHADOWVARS require distinct default storage policies',token)
            disposition=('Set explicit offline default group' if name=='%DEFGROUP' else
                'Label omitted-file READ/WRITE observations without device I/O' if name=='%CRTDEVICE' else
                'Retain existing uninitialized defaults without clearing saved values' if name=='%UNINITVARS' else
                'Retain source policy metadata only; no native storage, locks, periodic scheduling delay or stack allocation')
        elif name in rt.TASK_DIRECTIVES:
            if declarations_started: self.error('E_DIRECTIVE_POSITION','Task directives must precede declarations',token)
            if any(row['name']==name for row in self.directive_metadata):
                self.error('E_DIRECTIVE_DUPLICATE','Task directives cannot be repeated',token)
            if name in rt.TASK_FLAG_DIRECTIVES:
                if content.upper()!=name: self.error('E_DIRECTIVE_SYNTAX','Task flag directive accepts no arguments',token)
            elif name in ('%NOABORT','%NOPAUSE'):
                match=re.fullmatch(r'%[A-Za-z]+\s*=\s*([A-Za-z]+(?:\s*\+\s*[A-Za-z]+)*)',content)
                if not match: self.error('E_DIRECTIVE_SYNTAX','Task mask requires named flags joined by +',token)
                parts=[part.strip().upper() for part in match[1].split('+')]
                masks={'ERROR':rt.TASK_MASKS['PG_NP_ERROR'],'COMMAND':rt.TASK_MASKS['PG_NP_CMD' if name=='%NOABORT' else 'PG_NP_END']}
                if name=='%NOPAUSE': masks['TPENABLE']=rt.TASK_MASKS['PG_NP_TPENB']
                if len(parts)!=len(set(parts)) or any(part not in masks for part in parts):
                    self.error('E_DIRECTIVE_VALUE','Task mask contains an unknown or repeated flag',token)
                argument=sum(masks[part] for part in parts)
            else:
                match=re.fullmatch(r'%[A-Za-z]+\s*=\s*([0-9]{1,10})',content)
                if not match: self.error('E_DIRECTIVE_SYNTAX','Task numeric directive requires one unsigned INTEGER literal',token)
                argument=int(match[1])
                if not rt.valid_task_setting(rt.TASK_DIRECTIVES[name],argument):
                    self.error('E_DIRECTIVE_VALUE','Task numeric directive exceeds its portable range',token)
            disposition='Configure explicit offline task policy; no native scheduling, lamp or motion control'
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
            if not argument.isascii() or len(argument) > 254:
                self.error('E_DIRECTIVE_VALUE', 'COMMENT requires at most 254 decoded ASCII characters', token)
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
        imported_types = []
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
                    if self.mode == 'pythonic' and self.accept('FROM'):
                        owner = self.name()
                        imported_types.append(dict(name=key.value, owner=owner.value, line=key.line, column=key.column))
                    self.expect('=')
                    if self.mode == 'pythonic': self.skip_newlines()
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
                    self.storage_clause(names,name,imported=owner is not None)
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
                return Program(name, constants, declarations, routines, body, directives, user_types, self.directive_metadata,imports,imported_types,self.storage_declarations)
            else:
                self.error('E_DECLARATION', 'Expected CONST, TYPE, VAR, ROUTINE or BEGIN; external declarations and controller types are not implemented')

    def storage_clause(self,names,owner,*,imported=False):
        """Retain explicit declaration placement without inventing persistence."""
        if self.current.value!='IN':return
        token=self.take()
        if self.mode!='pythonic' or imported:
            self.error('E_STORAGE','Storage clauses require Pythonic owned VAR declarations',token)
        self.skip_newlines();pool=self.take()
        if pool.value not in ('CMOS','DRAM'):
            self.error('E_STORAGE_POOL','VAR storage requires IN CMOS or IN DRAM',pool)
        self.skip_newlines()
        self.storage_declarations.extend(dict(owner=owner,name=key.value,pool=pool.value,
            line=key.line,column=key.column) for key in names)

    def type_spec(self,array_rank=0):
        if self.mode == 'pythonic': self.skip_newlines()
        token = self.take()
        if self.mode=='pythonic' and token.value in ('FILE','QUEUE_TYPE'): return (token.value,)
        if self.mode=='pythonic' and token.value=='PATH':
            node=data=None
            seen=set()
            clauses={'NODEDATA':'NODEDATA','PATHHEADER':'PATHHEADER','PATHDATA':'PATHHEADER'}
            self.skip_newlines()
            while self.current.value in clauses and self.tokens[self.position+1].value=='=':
                key=self.take();canonical=clauses[key.value]
                if canonical in seen: self.error('E_TYPE','Duplicate PATH '+canonical+' clause',key)
                seen.add(canonical);self.expect('=');item=self.type_spec()
                if canonical=='NODEDATA': node=item
                else: data=item
                self.path_clause_uses.append(dict(clause=key.value,canonical=canonical,line=key.line,column=key.column))
                separator=self.accept(',')
                if separator:
                    self.skip_newlines()
                    if self.current.value not in clauses or self.tokens[self.position+1].value!='=':
                        self.error('E_PATH_CLAUSE','A PATH clause comma requires another NODEDATA or PATHHEADER/PATHDATA clause',separator)
                elif self.current.kind=='NL':
                    checkpoint=self.position;self.skip_newlines()
                    if self.current.value not in clauses or self.tokens[self.position+1].value!='=':
                        self.position=checkpoint;break
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
            if array_rank+len(sizes) > 3:
                self.error('E_ARRAY_RANK', 'Arrays support at most three logical dimensions', token)
            self.expect('OF')
            element = self.type_spec(array_rank+len(sizes) if self.mode=='pythonic' else 0)
            if self.mode!='pythonic' and element[0] == 'ARRAY':
                self.error('E_TYPE', 'Nested ARRAY type syntax needs named-array type rules; use comma-separated dimensions', token)
            return self.inline_array_spec(sizes[0] if len(sizes)==1 else tuple(sizes),element,token)
        if token.kind == 'NAME' and token.value not in RESERVED:
            return ('NAMED', token)
        self.error('E_TYPE', f'{token.value} data type is not implemented', token)

    def group_spec(self,spec,token):
        if self.current.value!='IN': return spec
        if self.mode!='pythonic': self.error('E_POSITION_GROUP','Group-qualified data requires Pythonic context',token)
        self.take(); self.expect('GROUP'); self.expect('['); group=self.expression(); self.expect(']')
        return ('GROUPED',spec,group,token)

    def inline_array_spec(self,dimensions,element,token):
        """Normalize directly written ARRAY layers; named components stay opaque."""
        if self.mode=='pythonic' and element[0]=='ARRAY':
            outer=dimensions if isinstance(dimensions,tuple) else (dimensions,)
            inner=element[1] if isinstance(element[1],tuple) else (element[1],)
            dimensions=outer+inner
            if len(dimensions)>3:
                self.error('E_ARRAY_RANK','Inline ARRAYs support at most three logical dimensions',token)
            element=element[2]
            self.inline_array_uses.append(dict(line=token.line,column=token.column,
                normalized_outer_rank=len(dimensions),terminal=element[0]))
        return ('ARRAY',dimensions,element)

    def array_result_type(self,array_rank=0):
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
        rank=len(dimensions) if isinstance(dimensions,tuple) else 1
        if array_rank+rank>3:
            self.error('E_ARRAY_RANK','ARRAY results support at most three logical dimensions',array_token)
        self.expect('OF')
        if self.mode=='pythonic':self.skip_newlines()
        element = self.take()
        if self.mode=='pythonic' and element.value=='ARRAY':
            self.position-=1
            element_spec=self.array_result_type(array_rank+rank)
        elif element.value in ('INTEGER', 'BOOLEAN', 'REAL', 'BYTE', 'SHORT', *DATA_RECORD_TYPES):
            element_spec = (element.value,)
        elif self.mode=='pythonic' and element.value in ('PATH','QUEUE_TYPE'):
            element_spec=('PATH',None,None) if element.value=='PATH' else ('QUEUE_TYPE',)
        elif element.value == 'STRING':
            if self.accept('['):
                element_spec=('STRING',self.expression())
                self.expect(']')
            elif self.mode=='pythonic':element_spec=('STRING',None)
            else:self.error('E_RETURN_TYPE','STRING ARRAY results require an explicit element capacity in brackets',element)
        elif element.value in rt.JOINT_TYPE_NAMES:
            element_spec = rt.joint_spec(element.value)
        elif element.kind == 'NAME' and element.value not in RESERVED | BUILTINS:
            element_spec = ('NAMED', element)
        else:
            self.error('E_RETURN_TYPE', 'ARRAY results require supported scalars, bounded STRINGs, data records, joints or prior named aggregate elements', element)
        if self.current.value == 'IN':
            element_spec=self.group_spec(element_spec,element)
        return self.inline_array_spec(dimensions,element_spec,array_token)

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
                return_type = self.array_result_type()
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
        if self.mode == 'pythonic': allowed_results += ('STRING','GROUPED','PATH','QUEUE_TYPE',*NARROW_TYPES)
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
                self.storage_clause(names,name)
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

    def parameter_string_spec(self,token,*,element=False):
        if self.current.value!='[':return ('STRING',None)
        if self.mode!='pythonic':
            self.error('E_PARAMETERS','ARRAY OF STRING formal parameters inherit element capacity' if element else 'STRING formal parameters have no declared capacity',token)
        self.take();self.skip_newlines();capacity=self.expression();self.skip_newlines();self.expect(']')
        return ('STRING',capacity)

    def parameter_type(self,array_rank=0):
        if self.mode == 'pythonic': self.skip_newlines()
        if self.mode=='pythonic' and self.current.value in ('FILE','PATH','QUEUE_TYPE'): return self.type_spec()
        token = self.take()
        if token.value in PREDEFINED_CONSTANTS:
            self.error('E_PARAMETERS', 'Predefined constants cannot be used as parameter types', token)
        if token.value in ('INTEGER', 'BOOLEAN', 'REAL') or self.mode=='pythonic' and token.value in NARROW_TYPES: return (token.value,)
        if token.value in rt.JOINT_TYPE_NAMES:
            return self.group_spec(rt.joint_spec(token.value),token)
        if token.value in DATA_RECORD_TYPES:
            return self.group_spec((token.value,),token)
        if token.value == 'STRING':
            return self.parameter_string_spec(token)
        if token.value == 'ARRAY':
            dimensions = [None]
            if self.current.value == '[':
                self.take()
                dimensions = []
                while True:
                    if self.mode=='pythonic':self.skip_newlines()
                    if self.accept('*'):dimensions.append(None)
                    elif self.mode=='pythonic':dimensions.append(self.expression())
                    else:
                        self.error('E_PARAMETERS', 'ARRAY formal dimensions must use * rather than fixed lengths', token)
                    if self.mode=='pythonic':self.skip_newlines()
                    if not self.accept(','):break
                self.expect(']')
                if len(dimensions) > 3:
                    self.error('E_ARRAY_RANK', 'ARRAY formals support at most three dimensions', token)
            rank = len(dimensions)
            if array_rank+rank>3:
                self.error('E_ARRAY_RANK','ARRAY formals support at most three logical dimensions',token)
            shape = dimensions[0] if rank == 1 else tuple(dimensions)
            self.expect('OF')
            if self.mode=='pythonic':self.skip_newlines()
            element = self.take()
            if self.mode=='pythonic' and element.value=='ARRAY':
                self.position-=1
                return self.inline_array_spec(shape,self.parameter_type(array_rank+rank),token)
            if self.mode=='pythonic' and element.value in ('PATH','QUEUE_TYPE'):
                self.position-=1
                return ('ARRAY',shape,self.type_spec())
            if element.value in rt.JOINT_TYPE_NAMES:
                return ('ARRAY', shape, self.group_spec(rt.joint_spec(element.value),element))
            if element.value not in (*ARRAY_SCALARS, *DATA_RECORD_TYPES) and not (self.mode=='pythonic' and element.value=='FILE'):
                if element.kind == 'NAME' and element.value not in RESERVED | BUILTINS:
                    return ('ARRAY', shape, ('NAMED', element))
                self.error('E_PARAMETERS', 'ARRAY parameters require supported scalar elements or a named STRUCTURE type', element)
            if element.value == 'STRING':
                return ('ARRAY',shape,self.parameter_string_spec(element,element=True))
            return ('ARRAY', shape, self.group_spec((element.value,),element) if element.value in DATA_RECORD_TYPES else (element.value,))
        if token.kind == 'NAME' and token.value not in RESERVED:
            return ('NAMED', token)
        self.error('E_PARAMETERS', 'Parameter type is not implemented', token)

    def block(self, ends):
        result = []
        self._block_end_stack.append(frozenset(ends))
        try:
            self.skip_lines()
            while self.current.value not in ends:
                if self.current.kind == 'EOF':
                    self.error('E_SYNTAX', f'Unexpected end of source; expected {sorted(ends)}')
                result.append(self.statement())
                self.skip_lines()
        finally:
            self._block_end_stack.pop()
        return result

    def statement(self):
        token = self.take()
        name = token.value
        if self.mode=='pythonic' and name=='WHEN':
            self.error('E_MOTION_CLAUSE','WHEN requires a CONDITION definition or a comma-led MOVE local clause',token)
        if self.mode=='pythonic' and name=='UNTIL':
            self.error('E_MOTION_CLAUSE','UNTIL requires a REPEAT body or a comma-led MOVE local clause',token)
        if self.mode=='pythonic' and name in ('ATTACH','RELEASE') and self.current.value not in ('=','[','.','(','::'):
            if self.in_handler_actions:self.error('E_CONDITION_ACTION','Motion ownership statements are not handler actions',token)
            return Statement('motion_action',token,[name])
        if self.mode=='pythonic' and name in ('OPEN','CLOSE','RELAX') and self.current.value=='HAND':
            self.expect('HAND')
            return Statement('motion_action',token,[name+' HAND',self.expression()])
        if self.mode=='pythonic' and name=='CANCEL' and self.accept('FILE'):
            target=self.storage_selector() if self.current.kind=='NAME' and self.current.value not in RESERVED else None
            return Statement('file_cancel',token,[target])
        if self.mode=='pythonic' and (name in ('HOLD','UNHOLD','CANCEL')
                                     or name in ('STOP','RESUME') and self.current.value=='GROUP'):
            groups=None
            if self.accept('GROUP'):
                self.expect('[');groups=[self.expression()]
                while self.accept(','):
                    if len(groups)>=31:self.error('E_MOTION_GROUP','Motion control supports at most 31 groups',token)
                    groups.append(self.expression())
                self.expect(']')
            elif self.current.value in ('FILE','PROGRAM'):
                self.error('E_MOTION_CLAUSE','Unsupported motion control qualifier',self.current)
            return Statement('motion_control',token,[name,groups])
        if self.mode=='pythonic' and name=='WITH':
            if self.in_handler_actions:self.error('E_CONDITION_ACTION','WITH MOVE is not a global handler action',token)
            settings=[]
            while True:
                key=self.take();group=None
                if key.value=='$GROUP':
                    self.expect('[');group=self.expression();self.expect(']');self.expect('.')
                    key=self.take()
                if key.value not in rt.MOTION_SETTINGS:self.error('E_MOTION_SETTING','Unsupported motion WITH setting',key)
                if self.accept('['):
                    if group is not None:self.error('E_MOTION_GROUP','Motion WITH group can be specified only once',key)
                    group=self.expression();self.expect(']')
                self.expect('=')
                previous=self.motion_setting_constants;self.motion_setting_constants=rt.MOTION_SETTING_CONSTANTS.get(key.value,{})
                try:value=self.expression()
                finally:self.motion_setting_constants=previous
                settings.append((key,group,value))
                if len(settings)>31*len(rt.MOTION_SETTINGS):self.error('E_MOTION_SETTING','Motion WITH supports at most '+str(31*len(rt.MOTION_SETTINGS))+' group-qualified settings',key)
                self.skip_lines()
                if not self.accept(','):break
                self.skip_lines()
            self.expect('MOVE')
            return self.motion_statement(token,settings)
        if self.mode=='pythonic' and name=='MOVE':return self.motion_statement(token)
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
            options=[];seen=set()
            if self.accept('WITH'):
                self.skip_lines()
                while True:
                    key=self.take()
                    if key.value not in ('$SCAN_TIME','$PRIORITY'):
                        self.error('E_CONDITION_OPTION','Handler WITH requires $SCAN_TIME or $PRIORITY',key)
                    if key.value in seen:self.error('E_CONDITION_OPTION','Duplicate handler WITH option',key)
                    seen.add(key.value);self.expect('=');options.append((key,self.expression()));self.skip_lines()
                    if self.accept(',') or self.accept('WITH'):self.skip_lines();continue
                    break
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
                        if self.current.kind=='EOF' or self.current.value in BLOCK_ENDS|{'ENDMOVE'}:
                            self.error('E_SYNTAX','Unterminated CONDITION action block; expected ENDCONDITION',self.current)
                        actions.append(self.statement()); self.accept(','); self.skip_lines()
                finally: self.in_handler_actions=previous_actions
                clauses.append(Statement('condition_clause',when,[condition],actions))
            if not clauses: self.error('E_SYNTAX','CONDITION requires at least one WHEN clause')
            self.expect('ENDCONDITION')
            return Statement('condition',token,[number,options],clauses)
        if self.mode=='pythonic' and name in ('ENABLE','DISABLE','PURGE'):
            self.expect('CONDITION'); self.expect('['); number=self.expression(); self.expect(']')
            return Statement('condition_control',token,[name,number])
        if self.accept('::'):
            self.check_label_name(token)
            return Statement('label', token, [token])
        if self.mode=='pythonic' and name in ('$MNUFRAMENUM','$MNUTOOLNUM'):
            target=self.system_selection(token);self.expect('=')
            return Statement('system_selection_assign',token,[target,self.expression()])
        if self.mode=='pythonic' and name in ('$MNUFRAME','$MNUTOOL','$GROUP'):
            target=self.system_pose(token);self.expect('=')
            return Statement('system_pose_assign',token,[target,self.expression()])
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
            counter = self.storage_selector() if self.mode=='pythonic' else self.name()
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
                if self.mode == 'pythonic':
                    selector = self.expression()
                    variables.append(selector)
                else:
                    variable = self.name()
                    if self.current.value in ('[', '.', '('):
                        self.error('E_USING_TARGET', 'USING currently requires bare named STRUCTURE variables', variable)
                    variables.append(variable)
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

    def motion_statement(self,token,settings=None):
        if self.in_handler_actions:self.error('E_CONDITION_ACTION','MOVE is not a global handler action',token)
        form=self.take()
        if form.value not in ('TO','NEAR','AWAY','ABOUT','AXIS','RELATIVE','ALONG'):
            self.error('E_MOTION','Unsupported MOVE form',form)
        operation='MOVE '+form.value
        if form.value=='ALONG':
            opening=self.accept('(')
            if opening:
                path=Expr('group',opening,args=[self.expression()])
                self.expect(')')
            else:
                name=self.name()
                path=Expr('call',name,name.value,self.arguments()) if self.accept('(') else Expr('name',name,name.value)
            arguments=[self.access(path,motion_path=True)]
        else:
            arguments=[self.expression()]
            if form.value in ('NEAR','ABOUT','AXIS'):
                self.expect('BY');arguments.append(self.expression())
            elif form.value=='TO' and self.accept('VIA'):arguments.append(self.expression())
        nowait=bool(self.accept('NOWAIT'))
        clauses=[]
        if self.accept(','):
            self.skip_lines()
            while self.current.value in ('WHEN','UNTIL'):
                clause=self.take()
                if len(clauses)>=32:self.error('E_MOTION_CLAUSE','MOVE supports at most 32 local clauses',clause)
                previous,previous_motion=self.in_condition,self.in_motion_condition
                self.in_condition=True;self.in_motion_condition=True
                try:condition=self.expression()
                finally:self.in_condition,self.in_motion_condition=previous,previous_motion
                actions=[]
                if clause.value=='WHEN':self.expect('DO');has_actions=True
                else:has_actions=bool(self.accept('THEN'))
                self.skip_lines()
                previous=self.in_handler_actions;self.in_handler_actions=True
                try:
                    if has_actions:
                        while self.current.value not in ('WHEN','UNTIL','ENDMOVE'):
                            if self.current.kind=='EOF' or self.current.value in BLOCK_ENDS|{'ENDCONDITION'}:
                                self.error('E_MOTION_CLAUSE','Unterminated MOVE local handler; expected ENDMOVE',self.current)
                            actions.append(self.statement());self.accept(',');self.skip_lines()
                        if not actions:self.error('E_CONDITION_ACTION','Local DO/THEN requires an action',clause)
                finally:self.in_handler_actions=previous
                clauses.append(Statement('motion_clause',clause,[condition],actions))
            if not clauses:self.error('E_MOTION_CLAUSE','MOVE comma requires local WHEN or UNTIL clauses',token)
            self.expect('ENDMOVE')
        elif self.current.value in ('WHEN','UNTIL'):
            if not (self.current.value=='UNTIL' and self._block_end_stack and 'UNTIL' in self._block_end_stack[-1]):
                self.error('E_MOTION_CLAUSE','MOVE local WHEN/UNTIL clauses require a comma before the first clause',self.current)
        elif self.current.value in ('ENDMOVE','VIA'):
            self.error('E_MOTION_CLAUSE','Unsupported motion clause or unexpected ENDMOVE',self.current)
        return Statement('motion',token,[operation,arguments,nowait,settings or []],clauses)

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

    def system_selection(self,token):
        self.expect('[');group=self.expression();self.expect(']')
        return self.access(Expr('system_selection',token,'FRAME' if token.value=='$MNUFRAMENUM' else 'TOOL',[group]))

    def system_pose(self,token):
        self.expect('[');group=self.expression()
        if token.value in ('$MNUFRAME','$MNUTOOL'):
            self.expect(',');number=self.expression();self.expect(']')
            kind='FRAME' if token.value=='$MNUFRAME' else 'TOOL'
            return self.access(Expr('system_pose',token,kind,[group,number]))
        self.expect(']');self.expect('.');member=self.take()
        if member.value not in ('$UFRAME','$UTOOL'):
            self.error('E_SYSTEM_POSE','Only $GROUP[n].$UFRAME/$UTOOL is supported',member)
        kind='ACTIVE_FRAME' if member.value=='$UFRAME' else 'ACTIVE_TOOL'
        return self.access(Expr('system_pose',token,kind,[group]))

    def access(self, base, *, motion_path=False):
        while self.current.value in ('[', '.'):
            token = self.take()
            if token.value == '[':
                indexes = [self.expression()]
                while self.accept(','): indexes.append(self.expression())
                if motion_path and self.accept('..'):
                    end = self.expression()
                    self.expect(']')
                    return Expr('motion_range', token, args=[base, *indexes, end])
                self.expect(']')
                base = Expr('index', token, args=[base, *indexes])
            else:
                member = self.name()
                base = Expr('field', member, member.value, [base])
        return base

    def motion_time_follows(self):
        # TIME remains an ordinary identifier unless a top-level BEFORE/AFTER
        # NODE marker makes the local-condition grammar unambiguous.
        depth=0
        for index in range(self.position,len(self.tokens)):
            token=self.tokens[index];value=token.value
            if token.kind=='EOF' or depth==0 and value in ('DO','THEN','ENDMOVE',')',']','AND','OR'):
                return False
            if depth==0 and value in ('BEFORE','AFTER') and index+1<len(self.tokens) and self.tokens[index+1].value=='NODE':return True
            if value in ('(','['):depth+=1
            elif value in (')',']'):depth-=1
        return False

    def motion_node_selector(self):
        self.expect('NODE');self.expect('[')
        node=None if self.accept('*') else self.expression()
        self.expect(']');return node

    def expression(self, minimum=0, *, allow_relative=True):
        self.skip_lines()
        token = self.take()
        if self.mode=='pythonic' and token.value in ('EVENT','SEMAPHORE'):
            self.expect('['); number=self.expression(); self.expect(']'); left=Expr('event' if token.value=='EVENT' else 'semaphore',token,args=[number])
        elif self.in_motion_condition and token.value=='AT' and self.current.value=='NODE':
            left=Expr('motion_condition',token,'AT',[None,self.motion_node_selector()])
        elif self.in_motion_condition and token.value=='TIME' and self.motion_time_follows():
            offset=self.expression();self.skip_lines();direction=self.take()
            if direction.value not in ('BEFORE','AFTER'):self.error('E_MOTION_CONDITION','TIME requires BEFORE/AFTER NODE',direction)
            left=Expr('motion_condition',token,direction.value,[offset,self.motion_node_selector()])
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
        elif token.value in self.motion_setting_constants:
            left=Expr('literal',token,self.motion_setting_constants[token.value])
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
        elif self.mode=='pythonic' and token.value in ('$MNUFRAMENUM','$MNUTOOLNUM'):
            left=self.system_selection(token)
        elif self.mode=='pythonic' and token.value in ('$MNUFRAME','$MNUTOOL','$GROUP'):
            left=self.system_pose(token)
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
