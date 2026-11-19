"""Resolve declarations, normalize source references and analyze routine effects."""
from .compiler_language import (
    ARRAY_ELEMENTS,
    ARRAY_SCALARS,
    BUILTIN_PROCEDURES,
    BUILTIN_SIGNATURES,
    CONFIG_TEXT_PROCEDURES,
    CONSTANT_BUILTINS,
    DATA_RECORD_TYPES,
    MAX_CONSTANT_BUILTIN_CALLS,
    MAX_CONSTANT_BUILTIN_DEPTH,
    MULTI_OUTPUT_PROCEDURES,
    NARROW_TYPES,
    POSITIONAL_VALUE_TYPES,
    PREDEFINED_CONSTANTS,
    RECORD_TYPES,
    REGISTER_PROCEDURES,
    TIME_TEXT_PROCEDURES,
    blocked_controller_names,
)
from .syntax import Expr, Statement
from .lexer import Token
from .control_flow import counter_text
from . import extended as ex
from . import runtime as rt


class DeclarationPasses:
    """Declaration passes shared with the checked Python emitter during migration."""

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
            if self.mode=='pythonic' and expr.kind=='call' and expr.value in CONSTANT_BUILTINS:
                return self.constant_builtin(expr)
            if self.is_minimum_literal(expr):
                self.error('E_MININT_LITERAL', 'The manual requires MININT instead of the INTEGER literal -2147483648', expr.token)
            if expr.kind == 'unary': return rt.unary(expr.value, self.constant(expr.args[0]))
            if expr.kind == 'binary': return rt.binary(expr.value, *(self.constant(x) for x in expr.args))
        except rt.KarelRuntimeError as exc:
            self.error('E_CONSTANT', str(exc), expr.token)
        self.error('E_CONSTANT', 'Expected a literal or previously declared constant expression', expr.token)

    def constant_builtin(self,expr):
        """Evaluate an explicit bounded pure whitelist, never user/service code."""
        signature,_=BUILTIN_SIGNATURES[expr.value]
        if len(expr.args)!=len(signature):
            self.error('E_CONSTANT',f'{expr.value} requires {len(signature)} constant arguments',expr.token)
        if self._constant_builtin_depth>=MAX_CONSTANT_BUILTIN_DEPTH:
            self.error('E_CONSTANT','Compile-time built-in call nesting limit reached',expr.token)
        self._constant_builtin_depth+=1
        try:values=[self.constant(argument) for argument in expr.args]
        finally:self._constant_builtin_depth-=1
        if any(type(value) not in (bool,int,float,str) for value in values):
            self.error('E_CONSTANT','Compile-time built-ins require scalar constant arguments',expr.token)
        routine=self.current_routine.name if self.current_routine else None
        key=(routine,expr.token.line,expr.token.column,expr.value,tuple((type(value),value) for value in values))
        if key in self._constant_builtin_cache:return self._constant_builtin_cache[key]
        if len(self._constant_builtin_cache)>=MAX_CONSTANT_BUILTIN_CALLS:
            self.error('E_CONSTANT','Compile-time built-in evaluation limit reached',expr.token)
        value=rt.builtin(expr.value,values,expr.token.line)
        if type(value) not in (bool,int,float,str):
            self.error('E_CONSTANT','Compile-time built-ins must return scalar data',expr.token)
        self._constant_builtin_cache[key]=value
        types={bool:'BOOLEAN',int:'INTEGER',float:'REAL',str:'STRING'}
        self.constant_builtin_uses.append(dict(function=expr.value,scope='routine' if routine else 'module',routine=routine,
            constant=self._constant_declaration,line=expr.token.line,column=expr.token.column,
            argument_types=[types[type(argument)] for argument in values],result_type=types[type(value)],
            evaluated_at_translation=True,runtime_call=False))
        self.features.update(('pure scalar compile-time built-in calls',expr.value))
        return value

    def resolve_constants(self,declarations,target,routine=None):
        """Resolve pure scalar declarations without recursive dependency chasing."""
        definitions={token.value:(token,expr) for token,expr in declarations}
        references={}
        for name,(_,expr) in definitions.items():
            pending=[expr];references[name]=[]
            while pending:
                node=pending.pop()
                if node.kind=='name':references[name].append(node)
                elif node.kind in ('group','unary','binary') or node.kind=='call' and node.value in CONSTANT_BUILTINS:
                    pending.extend(reversed(node.args))
                elif node.kind not in ('literal','real_literal','predefined'):
                    self.error('E_CONSTANT','CONST permits only scalar operators and whitelisted pure built-ins over visible constants',node.token)
        marks={};active=[];positions={}
        global_tokens={token.value:token for token,_ in self.program.constants}
        scope='routine' if routine else 'module'
        for start in definitions:
            if marks.get(start)==2:continue
            marks[start]=1;positions[start]=len(active);active.append(start)
            pending=[(start,iter(references[start]))]
            while pending:
                name,children=pending[-1];reference=next(children,None)
                if reference is None:
                    token,expr=definitions[name];previous=self._constant_declaration;self._constant_declaration=name
                    try:value=self.constant(expr)
                    finally:self._constant_declaration=previous
                    if type(value) is int:
                        try:rt.integer(value)
                        except rt.KarelRuntimeError as exc:self.error('E_CONSTANT',str(exc),token)
                    target[name]=value
                    self.constant_resolution_order.append(dict(scope=scope,routine=routine,name=name))
                    marks[name]=2;pending.pop();positions.pop(name);active.pop();continue
                dependency=reference.value
                if dependency not in definitions and dependency not in self.constants:
                    self.error('E_CONSTANT',dependency+' is not a visible declared constant',reference.token)
                local=dependency in definitions
                dependency_token=definitions[dependency][0] if local else global_tokens[dependency]
                forward=(dependency_token.line,dependency_token.column)>(reference.token.line,reference.token.column)
                self.constant_dependency_uses.append(dict(scope=scope,routine=routine,name=name,dependency=dependency,
                    dependency_scope=scope if local else 'module',line=reference.token.line,column=reference.token.column,forward=forward))
                if not local:continue
                if marks.get(dependency)==1:
                    cycle=active[positions[dependency]:]+[dependency]
                    shown=cycle if len(cycle)<=32 else cycle[:31]+['...',dependency]
                    self.error('E_CONSTANT','Cyclic CONST dependency: '+' -> '.join(shown),reference.token)
                if marks.get(dependency)==2:continue
                marks[dependency]=1;positions[dependency]=len(active);active.append(dependency)
                pending.append((dependency,iter(references[dependency])))
        ordered={name:target[name] for name in definitions};target.clear();target.update(ordered)
        if any(row['forward'] for row in self.constant_dependency_uses):self.features.add('forward CONST dependency resolution')

    @staticmethod
    def is_minimum_literal(expr):
        if expr.kind != 'unary' or expr.value != '-': return False
        child = expr.args[0]
        while child.kind == 'group': child = child.args[0]
        return child.kind == 'literal' and type(child.value) is int and child.value == 2147483648

    def resolve_spec(self, spec):
        if spec[0] in rt.ASSOCIATION_TYPES and self.mode!='pythonic':
            self.error('E_TYPE','Association records require Pythonic mode',Token('NAME',spec[0],1,1))
        if spec[0]=='GROUPED':
            group=self.constant(spec[2])
            if type(group) is not int or not 1<=group<=32: self.error('E_POSITION_GROUP','Group must be an INTEGER in 1..32',spec[3])
            resolved=self.resolve_spec(spec[1])
            if resolved[0]=='COMMON_ASSOC':self.error('E_POSITION_GROUP','COMMON_ASSOC does not have a group qualifier',spec[3])
            self.group_uses.append(dict(group=group,type=resolved[0],line=spec[3].line,column=spec[3].column))
            self.features.add('explicit group metadata'); return resolved
        if spec[0] in ('FILE','QUEUE_TYPE'): return spec
        if spec[0]=='PATH':
            resolved=('PATH',self.resolve_spec(spec[1]) if spec[1] else None,self.resolve_spec(spec[2]) if spec[2] else None)
            if resolved[1]==rt.PREDEFINED_STRUCTURES['STD_PTH_NODE']:
                resolved=('PATH',None,resolved[2])
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
            if self.mode == 'pythonic' and token.value in rt.PREDEFINED_STRUCTURES:
                row=dict(name=token.value,line=token.line,column=token.column)
                if row not in self.predefined_structure_uses: self.predefined_structure_uses.append(row)
                self.features.add('predefined STRUCTURE data layout')
                return rt.PREDEFINED_STRUCTURES[token.value]
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
            if self.mode=='pythonic' and element==('FILE',):self.features.add('reference-only FILE ARRAY')
            if self.mode=='pythonic' and (element[0] in ('PATH','QUEUE_TYPE') or rt.collection_array_type(element)):self.features.add('reference-only collection ARRAY')
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
            if element[0] not in (*ARRAY_ELEMENTS, 'ARRAY') and not (self.mode=='pythonic' and element[0] in ('FILE','PATH','QUEUE_TYPE')):
                self.error('E_TYPE', 'ARRAY elements require supported scalars or named STRUCTURE types', spec[1][0].token)
            if rt.scalar_leaf_count(('ARRAY', tuple(sizes), element)) > 32767:
                self.error('E_ARRAY_CAPACITY', 'Prototype arrays are limited to 32767 scalar leaves including STRUCTURE fields', spec[1][0].token)
            self.features.add('multidimensional STRUCTURE ARRAY' if element[0] == 'STRUCTURE' else 'multidimensional scalar ARRAY')
            result=('ARRAY',tuple(sizes),element)
            self.check_collection_array(result,spec[1][0].token)
            return result
        size = self.constant(spec[1])
        limit = 254 if spec[0] == 'STRING' else 32767
        if type(size) is not int or not 1 <= size <= limit:
            self.error('E_SIZE', f'{spec[0]} size must be INTEGER in 1..{limit}', spec[1].token)
        if spec[0] == 'STRING': return (spec[0], size)
        if element[0] not in (*ARRAY_ELEMENTS, 'ARRAY') and not (self.mode=='pythonic' and element[0] in ('FILE','PATH','QUEUE_TYPE')):
            self.error('E_TYPE', 'ARRAY elements require supported scalars or named STRUCTURE types; nested arrays are blocked', spec[1].token)
        if rt.scalar_leaf_count(('ARRAY', size, element)) > 32767:
            self.error('E_ARRAY_CAPACITY', 'Prototype arrays are limited to 32767 scalar leaves including STRUCTURE fields', spec[1].token)
        result=('ARRAY',size,element)
        self.check_collection_array(result,spec[1].token)
        return result

    def check_collection_array(self,spec,token):
        if self.mode=='pythonic' and rt.collection_array_type(spec):
            from .storage import collection_array_cost
            try:collection_array_cost(spec)
            except (ValueError,rt.KarelRuntimeError) as exc:self.error('E_ARRAY_CAPACITY',str(exc),token)

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

    def resolve_array_parameter_spec(self,spec,token,routine):
        """Resolve fixed constraints without allocating or guessing wildcards."""
        if spec[0]!='ARRAY':return self.resolve_spec(spec)
        element=self.resolve_spec(spec[2]);dimensions=[]
        for size in rt.array_shape(spec):
            if size is None:dimensions.append(None)
            else:
                value=self.constant(size)
                if type(value) is not int or not 1<=value<=32767:
                    self.error('E_SIZE','ARRAY formal dimensions require INTEGER in 1..32767 or *',size.token)
                dimensions.append(value)
        if element[0]=='ARRAY' and rt.array_identity(element) is None:
            self.error('E_NESTED_NAMED_ARRAY','ARRAY formal components require a named ARRAY type',token)
        shape=dimensions[0] if len(dimensions)==1 else tuple(dimensions)
        result=('ARRAY',shape,element)
        logical=rt.array_dimensions(result)
        if len(logical)>3:self.error('E_ARRAY_RANK','ARRAY formals support at most three logical dimensions',token)
        minimum=tuple(1 if size is None else size for size in dimensions)
        bounded=('ARRAY',minimum[0] if len(minimum)==1 else minimum,element)
        if rt.scalar_leaf_count(bounded)>32767:
            self.error('E_ARRAY_CAPACITY','ARRAY formal minimum exceeds 32767 scalar leaves/descriptors',token)
        self.check_collection_array(bounded,token)
        if any(size is not None for size in dimensions):
            self.features.add('fixed and mixed ARRAY formal constraints')
            self.array_formal_uses.append(dict(routine=routine,parameter=token.value,line=token.line,column=token.column,
                type_spec=result,logical_dimensions=list(logical),
                fixed_dimensions=[index+1 for index,size in enumerate(logical) if size is not None],
                wildcard_dimensions=[index+1 for index,size in enumerate(logical) if size is None],
                interface_scope='module',runtime_shape='checked caller storage; no allocation or resize'))
        return result

    def note_string_formal(self,spec,resolved,token,routine):
        terminal=spec[2] if spec[0]=='ARRAY' else spec
        if terminal[0]!='STRING' or terminal[1] is None:return
        capacity=resolved[2][1] if resolved[0]=='ARRAY' else resolved[1]
        self.features.add('direct bounded STRING formal constraints')
        self.string_formal_uses.append(dict(routine=routine,parameter=token.value,line=token.line,column=token.column,
            type_spec=resolved,capacity=capacity,container='ARRAY' if spec[0]=='ARRAY' else 'scalar',interface_scope='module',
            semantics='Existing exact reference/private bounded value contracts; no storage allocation or resize'))

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

    @staticmethod
    def declared_type_references(definition):
        pending=[definition] if isinstance(definition,tuple) else [spec for _,spec in reversed(definition)]
        references=[]
        while pending:
            spec=pending.pop()
            if spec[0]=='NAMED':references.append(spec[1])
            elif spec[0]=='ARRAY':pending.append(spec[2])
            elif spec[0]=='GROUPED':pending.append(spec[1])
            elif spec[0]=='PATH':pending.extend(item for item in reversed(spec[1:3]) if item is not None)
        return references

    def resolve_type_definition(self,token,definition):
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
            return
        resolved = {}
        for member, spec in definition:
            if member.value in resolved: self.error('E_DUPLICATE', 'Duplicate STRUCTURE field', member)
            resolved[member.value] = self.resolve_spec(spec)
            if resolved[member.value][0] in ('FILE','PATH','QUEUE_TYPE') or rt.resource_array_type(resolved[member.value]):
                self.error('E_TYPE','Resource fields in STRUCTURE are not supported',member)
        self.user_types[token.value] = ('STRUCTURE', token.value, tuple(resolved.items()))
        self.features.add('named STRUCTURE definition')

    def check_type_schema(self,spec,token):
        """Memoize shared schemas before code generation can expand their repr."""
        costs=self._type_schema_costs;pending=[(spec,False)]
        while pending:
            current,ready=pending.pop();identity=id(current)
            if identity in costs:continue
            children=([field for _,field in current[2]] if current[0]=='STRUCTURE'
                      else [current[2]] if current[0]=='ARRAY' else [])
            if children and not ready:
                pending.append((current,True));pending.extend((child,False) for child in reversed(children));continue
            if current[0]=='STRUCTURE':count=sum(costs[id(child)][0] for child in children)
            elif current[0]=='ARRAY':
                count=costs[id(current[2])][0]
                for dimension in rt.array_shape(current):count*=dimension
            else:count=rt.scalar_leaf_count(current)
            depth=1+max((costs[id(child)][1] for child in children),default=0)
            if count>32767:self.error('E_TYPE_CAPACITY','Resolved TYPE data exceeds 32767 scalar leaves',token)
            if depth>64:self.error('E_TYPE_DEPTH','Resolved TYPE data exceeds 64 schema levels',token)
            costs[identity]=(count,depth)

    def resolve_type_definitions(self,names):
        """Iterative dependency walk; resolved data schemas retain existing checks."""
        definitions={}
        for token,definition in self.program.user_types:
            if token.value in names:self.error('E_DUPLICATE','Duplicate declaration',token)
            names.add(token.value);definitions[token.value]=(token,definition)
            if self.mode!='pythonic':self.resolve_type_definition(token,definition)
        if self.mode!='pythonic':return
        references={name:self.declared_type_references(definition) for name,(_,definition) in definitions.items()}
        marks={};active=[];positions={}
        for start in definitions:
            if marks.get(start)==2:continue
            marks[start]=1;positions[start]=len(active);active.append(start)
            pending=[(start,iter(references[start]))]
            while pending:
                name,children=pending[-1]
                reference=next(children,None)
                if reference is None:
                    self.resolve_type_definition(*definitions[name])
                    self.check_type_schema(self.user_types[name],definitions[name][0])
                    marks[name]=2;self.type_resolution_order.append(name)
                    pending.pop();positions.pop(name);active.pop();continue
                dependency=reference.value
                if dependency in rt.PREDEFINED_STRUCTURES:continue
                if dependency not in definitions:
                    self.error('E_TYPE',dependency+' is not a declared supported type',reference)
                target=definitions[dependency][0]
                self.type_dependency_uses.append(dict(name=name,dependency=dependency,line=reference.line,column=reference.column,
                    forward=(target.line,target.column)>(reference.line,reference.column)))
                if marks.get(dependency)==1:
                    cycle=active[positions[dependency]:]+[dependency]
                    shown=cycle if len(cycle)<=32 else cycle[:31]+['...',dependency]
                    self.error('E_TYPE','Cyclic TYPE dependency: '+' -> '.join(shown),reference)
                if marks.get(dependency)==2:continue
                marks[dependency]=1;positions[dependency]=len(active);active.append(dependency)
                pending.append((dependency,iter(references[dependency])))
        self.user_types={name:self.user_types[name] for name in definitions}
        self.type_aliases.sort(key=lambda row:(row['line'],row['column']))
        self.type_dependency_uses.sort(key=lambda row:(row['line'],row['column']))
        if any(row['forward'] for row in self.type_dependency_uses):self.features.add('forward TYPE dependency resolution')

    def validate_symbols(self):
        names = set()
        for token, expr in self.program.constants:
            if token.value in ex.PORT_TYPES: self.error('E_DUPLICATE','Port identifiers cannot be constants',token)
            if token.value in names: self.error('E_DUPLICATE', 'Duplicate declaration', token)
            names.add(token.value)
            if self.mode!='pythonic':
                value = self.constant(expr)
                if type(value) is int:
                    try: rt.integer(value)
                    except rt.KarelRuntimeError as exc: self.error('E_CONSTANT', str(exc), token)
                self.constants[token.value] = value
        if self.mode=='pythonic':self.resolve_constants(self.program.constants,self.constants)
        self.resolve_type_definitions(names)
        for token, spec in self.program.declarations:
            if token.value in names: self.error('E_DUPLICATE', 'Duplicate declaration', token)
            if token.value in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys():
                self.error('E_CONTROLLER', 'Controller identifiers are not supported', token)
            names.add(token.value)
            resolved = self.resolve_global_spec(token, spec)
            if self.mode!='pythonic' and resolved[0] in NARROW_TYPES:
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
                if self.mode!='pythonic' and definition_token and (definition_token.line, definition_token.column) > (routine.token.line, routine.token.column):
                    self.error('E_TYPE', 'Named result types must be declared before the routine', result_token)
                routine.return_type = self.resolve_spec(routine.return_type)
                allowed_named_results = ('STRUCTURE',)
                if self.mode == 'pythonic':
                    allowed_named_results += ('ARRAY', 'STRING', 'INTEGER', 'BOOLEAN', 'REAL', 'PATH', 'QUEUE_TYPE', *NARROW_TYPES, *DATA_RECORD_TYPES, 'JOINTPOS')
                if routine.return_type[0] not in allowed_named_results:
                    message = ('BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields' if self.mode == 'pythonic'
                               else 'Named ARRAY function results remain blocked; a named result type must be a STRUCTURE')
                    self.error('E_RETURN_TYPE', message, routine.token)
                self.features.add('named ' + routine.return_type[0] + ' function result')
                if routine.return_type[0] == 'STRING': self.features.add('STRING function result')
            if self.mode=='pythonic' and routine.return_type and routine.return_type[0] in ('PATH','QUEUE_TYPE'):
                routine.return_type=self.resolve_spec(routine.return_type)
                self.features.add('logical scalar collection function result')
            if routine.return_type == ('VECTOR',): self.features.add('VECTOR function result')
            if routine.return_type and routine.return_type[0] == 'ARRAY':
                element = routine.return_type[2]
                if element[0] == 'NAMED':
                    result_token = element[1]
                    definition_token = next((token for token, _ in self.program.user_types if token.value == result_token.value), None)
                    if self.mode!='pythonic' and definition_token and (definition_token.line, definition_token.column) > (routine.token.line, routine.token.column):
                        self.error('E_TYPE', 'Named result element types must be declared before the routine', result_token)
                routine.return_type = (self.resolve_array_result_spec(routine.return_type, routine.token)
                                       if self.mode == 'pythonic' else self.resolve_spec(routine.return_type))
                element = routine.return_type[2]
                leaf = rt.array_leaf_spec(element) if element[0] == 'ARRAY' else element
                if leaf[0] not in (*ARRAY_SCALARS, *RECORD_TYPES, 'JOINTPOS') and not (self.mode=='pythonic' and leaf[0] in ('PATH','QUEUE_TYPE')):
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
                resolved = self.resolve_array_parameter_spec(spec,token,routine.name) if self.mode=='pythonic' else self.resolve_spec(spec)
                if self.mode=='pythonic':self.note_string_formal(spec,resolved,token,routine.name)
                if self.mode!='pythonic' and resolved[0] in NARROW_TYPES:
                    self.error('E_PARAMETERS', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
                routine.local_types[token.value] = resolved
            routine.parameters = [(token, routine.local_types[token.value]) for token, _ in routine.parameters]
            self.current_routine = routine
            if self.mode=='pythonic':
                local_names=set(routine.local_types)
                for kind,token,definition in routine.local_declarations:
                    if (token.value in local_names or token.value in self.constants or token.value in self.user_types
                            or token.value in blocked_controller_names(self.mode) | ex.PORT_TYPES.keys()):
                        self.error('E_DUPLICATE','Duplicate, constant-shadowing or controller local identifier',token)
                    local_names.add(token.value)
                    if kind=='CONST' and (token.value in names or token.value==self.program.name):
                        self.error('E_LOCAL_CONST_SHADOW','Local constants that shadow global declarations need namespace evidence',token)
                self.resolve_constants([(token,definition) for kind,token,definition in routine.local_declarations if kind=='CONST'],routine.local_constants,routine.name)
                if routine.local_constants:self.features.add('routine-local CONST')
            for kind, token, definition in routine.local_declarations:
                if self.mode=='pythonic' and kind=='CONST':continue
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
                    if self.mode!='pythonic' and resolved[0] in NARROW_TYPES:
                        self.error('E_TYPE', 'BYTE and SHORT are permitted only as ARRAY elements or STRUCTURE fields', token)
                    routine.local_types[token.value] = resolved
            self.current_routine = None
        self.constant_dependency_uses.sort(key=lambda row:(row['line'],row['column']))
        self.resolve_using_fields()
        self.resolve_bare_function_calls()
        if self.mode=='pythonic' and any(isinstance(node,Expr) and node.kind=='call' and node.value in ex.COOPERATIVE_PROCEDURES
                for body in (self.program.body,*[routine.body for routine in self.program.routines]) for node in self.walk_nodes(body)):
            self.cooperative=True
        self.analyze_routine_effects()

    def normalize_array_chains(self):
        """Complete adjacent subscript groups use the existing comma path.

        Flatten before any receiver typing, so a partial intermediate flat ARRAY
        is never materialized or mistaken for a valid row view. Grouping around
        an intermediate index does not introduce a separate storage boundary.
        """
        def resolve(node,body):
            if isinstance(node,Expr):
                if node.kind in ('index','motion_range'):
                    source=counter_text(node);segments=[];current=node
                    end=node.args[-1:] if node.kind=='motion_range' else []
                    while True:
                        segments.append(current.args[1:-1] if current.kind=='motion_range' else current.args[1:])
                        base=current.args[0];receiver=base
                        while receiver.kind=='group':receiver=receiver.args[0]
                        if receiver.kind!='index':break
                        current=receiver
                    if len(segments)>1:
                        segments.reverse()
                        node.args=[base,*[value for segment in segments for value in segment],*end]
                        self.array_index_chains.append(dict(body=body,line=current.token.line,column=current.token.column,
                            source_selector=source,normalized_selector=counter_text(node),
                            segment_lengths=[len(segment) for segment in segments],subscript_count=sum(map(len,segments))))
                        self.features.add('chained ARRAY subscript normalization')
                node.args=[resolve(argument,body) for argument in node.args]
            elif isinstance(node,Statement):
                node.args=[resolve(argument,body) for argument in node.args]
                node.body=resolve(node.body,body);node.alternate=resolve(node.alternate,body)
            elif isinstance(node,list):return [resolve(child,body) for child in node]
            elif isinstance(node,tuple):return tuple(resolve(child,body) for child in node)
            return node
        self.program.body=resolve(self.program.body,self.program.name)
        for routine in self.program.routines:routine.body=resolve(routine.body,routine.name)

    def resolve_bare_function_name(self,node):
        """Resolve one value name, also usable before USING receiver inspection."""
        if node.kind == 'name' and node.value in self.routines:
            shadowed = (self.current_routine and node.value in
                        (self.current_routine.local_types.keys() | self.current_routine.local_constants.keys()))
            if not shadowed:
                routine=self.routines[node.value]
                if routine.parameters:
                    self.error('E_ARGUMENTS','A bare routine name requires a function with no parameters; supply the declared arguments',node.token)
                if routine.return_type is None:self.error('E_TYPE','Procedure cannot be used as an expression',node.token)
                self.bare_function_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                    name=node.value,line=node.token.line,column=node.token.column,result_spec=routine.return_type))
                self.features.add('bare zero-argument function call')
                return Expr('call',node.token,node.value,[])
        if node.kind == 'name' and self.mode == 'pythonic' and node.value in ('GET_USEC_TIM','CURR_PROG','CURPOS','CURJPOS','KCL_STATUS','MOTION_CTL') and node.value not in self.routines:
            local_names=(self.current_routine.local_types.keys() | self.current_routine.local_constants.keys()) if self.current_routine else set()
            if node.value not in self.types.keys() | self.constants.keys() | local_names:
                self.bare_function_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                    name=node.value,line=node.token.line,column=node.token.column,result_spec=('INTEGER',) if node.value=='GET_USEC_TIM' else ex.FUNCTIONS[node.value][1]))
                self.features.add('bare zero-argument function call')
                return Expr('call',node.token,node.value,[])
        return node

    def resolve_bare_function_calls(self):
        """Resolve value names before call/effect checks, preserving storage roots."""
        def resolve(node, storage=False):
            if isinstance(node, Expr):
                if not storage: node=self.resolve_bare_function_name(node)
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
            if expr.kind in ('system_pose','system_selection'):return counter_text(expr)
            if expr.kind == 'using_ref': return expr.value[4]
            if expr.kind == 'field': return path_text(expr.args[0])+'.'+expr.value
            if expr.kind == 'index': return path_text(expr.args[0])+'['+','.join(path_text(arg) for arg in expr.args[1:])+']'
            if expr.kind == 'group': return '('+path_text(expr.args[0])+')'
            if expr.kind == 'call': return expr.value+'('+','.join(path_text(arg) for arg in expr.args)+')'
            if expr.kind == 'binary': return '('+path_text(expr.args[0])+expr.value+path_text(expr.args[1])+')'
            if expr.kind == 'unary': return expr.value+'('+path_text(expr.args[0])+')'
            return str(expr.value)

        def copy_path(expr, token):
            # Insert absolute paths without revisiting their roots as aliases.
            return Expr(expr.kind, token, expr.value, [copy_path(child, token) for child in expr.args])

        def selector_names(expr):
            # USING needs its result schema before the later general bare-call
            # pass. Resolve only value names; lexical field aliases already won.
            expr=self.resolve_bare_function_name(expr)
            expr.args=[selector_names(child) for child in expr.args]
            return expr

        def data_only(spec):
            if spec[0] in ('FILE','PATH','QUEUE_TYPE'):return False
            if spec[0]=='ARRAY':return data_only(spec[2])
            return all(data_only(field) for _,field in rt.record_fields(spec)) if spec[0] in RECORD_TYPES else True

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
                    selectors, source_selectors, captures = [], [], []
                    for variable in node.args:
                        selector = variable if isinstance(variable, Expr) else Expr('name', variable, variable.value)
                        source_selectors.append(path_text(selector))
                        # A selector list uses enclosing aliases only, never the
                        # fields introduced by earlier selectors in this list.
                        selector = resolve(selector, bindings, scope)
                        if self.mode=='pythonic':selector=selector_names(selector)
                        spec = self.relative_operand_type(selector) if self.mode=='pythonic' else self.access_type(selector)
                        path_header=self.mode=='pythonic' and spec[0]=='PATH'
                        if path_header:
                            if spec[2] is None:self.error('E_USING_TYPE','USING PATH requires an explicit PATHHEADER',selector.token)
                            selected_spec=spec[2]
                            self.features.add('PATH header USING selector')
                        else:selected_spec=spec
                        if selected_spec[0] not in (RECORD_TYPES if self.mode == 'pythonic' else ('STRUCTURE',)):
                            self.error('E_USING_TYPE', 'USING requires STRUCTURE, a supported record or explicit PATH header', selector.token)
                        binding = selector
                        if self.mode == 'pythonic':
                            storage = selector
                            while storage.kind == 'group': storage = storage.args[0]
                            root=storage
                            while root.kind in ('group','field','index'):root=root.args[0]
                            reference=root.kind in ('name','using_ref')
                            if not reference and not data_only(selected_spec):
                                self.error('E_USING_VALUE','Computed USING records require data without FILE/PATH/QUEUE resources',selector.token)
                            source_root=self.root_name(selector) if reference else None
                            protection_root=self.protection_root(selector) if reference else f'_using_{len(self.using_scopes)}_{len(selectors)}'
                            if not reference:self.private_using_roots[protection_root]=selected_spec
                            source_kind='storage_reference' if reference else 'computed_value'
                            provenance='declared_storage' if source_root is not None else 'private_temporary'
                            captures.append(dict(source_kind=source_kind,provenance=provenance,source_root=source_root,
                                expression_kind=selector.kind,independent_copy=not reference,copy_back=False))
                            if path_header:captures[-1].update(path_header=True,path_type_spec=spec,selected_type_spec=selected_spec)
                            if reference and self.path_node_selector(selector):captures[-1]['path_node']=True
                            binding = Expr('using_ref',selector.token,
                                (f'_using_{len(self.using_scopes)}_{len(selectors)}',selected_spec,source_root,
                                 self.is_position_read_only_access(storage),path_text(selector),source_kind,provenance,protection_root))
                        for name, _ in rt.record_fields(selected_spec): fields[name] = binding
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
                    if self.mode == 'pythonic':
                        node.using_captures = tuple(f'_using_{scope["id"]}_{index}' for index in range(len(selectors)))
                        node.using_capture_kinds=tuple(capture['source_kind'] for capture in captures)
                        scope['capture_once'] = True
                        scope['selector_captures']=captures
                        self.features.add('captured USING storage selectors')
                        if any(capture['independent_copy'] for capture in captures):self.features.add('computed USING record values')
                        if any(self.relative_operand_type(selector)[0] in DATA_RECORD_TYPES for selector in selectors):
                            self.features.add('built-in record USING')
                        scope['selector_types'] = [self.relative_operand_type(selector) for selector in selectors]
                    node.body = resolve(node.body, fields, scope)
                    return node
                if self.mode!='pythonic' and bindings and node.kind == 'for' and node.args[0].value in bindings:
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
                yield from DeclarationPasses.walk_nodes(argument)
            if isinstance(node, Statement):
                yield from DeclarationPasses.walk_nodes(node.body)
                yield from DeclarationPasses.walk_nodes(node.alternate)
        elif isinstance(node, (list, tuple)):
            for child in node: yield from DeclarationPasses.walk_nodes(child)

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
                if (self.mode=='pythonic' and isinstance(node,Expr) and node.kind=='name' and node.value in ex.PREDEFINED_FILE_NAMES
                        and node.value not in self.types.keys() | self.constants.keys() | self.routines.keys() | self.user_types.keys() | routine.local_types.keys() | routine.local_constants.keys()):routine.may_services=True
                if isinstance(node,Statement) and node.kind in ('motion','motion_action','motion_control','file_cancel','system_pose_assign','system_selection_assign'):routine.may_services=True
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
                        if name is not None and name not in local_names: routine.side_effecting = True
                        if name in parameter_names: routine.parameter_writes.add(name)
                        if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                if isinstance(node, Statement) and node.kind == 'abort':
                    routine.may_abort = True
                if isinstance(node, Expr) and node.kind == 'call' and self.mode == 'pythonic' and node.value == 'GET_USEC_TIM' and node.value not in self.routines:
                    routine.may_clock = True
                if isinstance(node,Expr) and node.kind in ('system_pose','system_selection'):routine.may_services=True
                if isinstance(node,Expr) and node.kind=='call' and self.mode=='pythonic' and node.value in ex.PROCEDURES.keys()|ex.FUNCTIONS.keys() and node.value not in self.routines:
                    routine.may_services=True
                    if node.value=='PRINT_FILE': routine.may_write=True
                    signature=ex.signature_for(node.value,len(node.args))
                    for argument,(mode,_) in zip(node.args,signature):
                        if mode not in ('o','r','m'): continue
                        name=self.root_name(argument)
                        if name is not None and name not in local_names: routine.side_effecting=True
                        if name in parameter_names: routine.parameter_writes.add(name)
                        if name in self.types and name not in local_names|parameter_names: routine.global_writes.add(name)
                    if ex.variable_write_call(node.value,node.args): routine.global_writes.update(self.types)
                if isinstance(node, Statement) and node.kind in ('assign', 'for','timer_connect','timer_disconnect'):
                    name = self.root_name(node.args[0])
                    if node.kind in ('timer_connect','timer_disconnect') and name in parameter_names:routine.timer_parameter_writes.add(name)
                    if name is not None and name not in local_names: routine.side_effecting = True
                    if name in parameter_names: routine.parameter_writes.add(name)
                    if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                if isinstance(node, Statement) and node.kind == 'call':
                    call = node.args[0]
                    if call.value in MULTI_OUTPUT_PROCEDURES:
                        for output in call.args[1:]:
                            name = self.root_name(output)
                            if name is not None and name not in local_names: routine.side_effecting = True
                            if name in parameter_names: routine.parameter_writes.add(name)
                            if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                    if self.mode == 'pythonic' and call.value in CONFIG_TEXT_PROCEDURES | TIME_TEXT_PROCEDURES and call.value not in self.routines:
                        outputs=call.args[1:3] if call.value=='CNV_STR_CONF' else call.args[1:]
                        for output in outputs:
                            name = self.root_name(output)
                            if name is not None and name not in local_names: routine.side_effecting = True
                            if name in parameter_names: routine.parameter_writes.add(name)
                            if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                    if self.mode == 'pythonic' and call.value in REGISTER_PROCEDURES and call.value not in self.routines:
                        if call.value == 'GET_REG': routine.may_read_registers = True
                        else: routine.may_write_registers = True
                        for output in call.args[1:] if call.value == 'GET_REG' else call.args[2:]:
                            name = self.root_name(output)
                            if name is not None and name not in local_names: routine.side_effecting = True
                            if name in parameter_names: routine.parameter_writes.add(name)
                            if name in self.types and name not in local_names | parameter_names: routine.global_writes.add(name)
                    if call.value in BUILTIN_PROCEDURES and call.args:
                        name = self.root_name(call.args[-1])
                        if name is not None and name not in local_names:
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
                self.current_routine=routine
                if self.mode=='pythonic' and not routine.may_services:
                    for node in self.walk_nodes(routine.body):
                        if not isinstance(node,Statement) or node.kind!='assign':continue
                        target=node.args[0]
                        while target.kind=='group':target=target.args[0]
                        if not self.is_array_prefix_value(target):continue
                        expected=self.access_type(target);actual=self.access_type(node.args[1])
                        if rt.kinematic_array_kind(expected,actual) or rt.kinematic_record_kind(expected,actual):
                            routine.may_services=True;changed=True;break
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
                        if not self.argument_is_reference(argument,expected):continue
                        if formal.value in callee.timer_parameter_writes and name in parameter_names and name not in routine.timer_parameter_writes:
                            routine.timer_parameter_writes.add(name);changed=True
                        if name in parameter_names and name not in routine.parameter_writes:
                            routine.parameter_writes.add(name)
                            changed = True
                        if (name in self.types and name not in local_names | parameter_names
                                and name not in routine.global_writes):
                            routine.global_writes.add(name)
                            changed = True

        unknown={routine.name for routine in self.program.routines if routine.external}
        while True:
            inherited={name for name,targets in edges.items() if targets&unknown}
            if inherited<=unknown:break
            unknown.update(inherited)
        self.external_write_routines=unknown
        # Only explicitly passed references can expose a private value to a
        # callee. Calls capable of retaining handlers or unknown external links
        # may keep writable aliases after returning, so block later counters on
        # those lexical roots. Detached value arguments have independent roots.
        retaining={routine.name for routine in self.program.routines if routine.external or
                   any(isinstance(node,Statement) and node.kind in ('condition','timer_connect')
                       for node in self.walk_nodes(routine.body))}
        while True:
            inherited={name for name,targets in edges.items() if targets&retaining}
            if inherited<=retaining:break
            retaining.update(inherited)
        for routine in (None,*self.program.routines):
            self.current_routine=routine
            for node in self.walk_nodes(routine.body if routine else self.program.body):
                if not isinstance(node,Expr) or node.kind!='call' or node.value not in retaining:continue
                callee=self.routines[node.value]
                for argument,(formal,expected) in zip(node.args,callee.parameters):
                    identity=self.protection_root(argument)
                    if (identity not in self.private_using_roots or formal.value not in callee.parameter_writes
                            or argument.kind not in ('name','field','index')):continue
                    if not self.argument_is_reference(argument,expected):continue
                    self.escaped_private_using_roots.add(identity)
        handler_retaining={routine.name for routine in self.program.routines if
            any(isinstance(node,Statement) and node.kind=='condition' for node in self.walk_nodes(routine.body))}
        while True:
            inherited={name for name,targets in edges.items() if targets&handler_retaining}
            if inherited<=handler_retaining:break
            handler_retaining.update(inherited)
        for routine in (None,*self.program.routines):
            self.current_routine=routine
            locals_={token.value for token,_ in routine.declarations} if routine else set()
            formals={token.value for token,_ in routine.parameters} if routine else set()
            for node in self.walk_nodes(routine.body if routine else self.program.body):
                if not isinstance(node,Expr) or node.kind!='call' or node.value not in handler_retaining:continue
                callee=self.routines[node.value]
                for argument,(formal,expected) in zip(node.args,callee.parameters):
                    root=self.protection_root(argument)
                    if formal.value not in callee.timer_parameter_writes or root in self.private_using_roots:continue
                    if not self.argument_is_reference(argument,expected):continue
                    if root in locals_:self.retained_timer_alias_roots.add((routine.name,root))
                    elif root in self.types and root not in formals:self.retained_timer_alias_roots.add((None,root))
        # A retained writable reference must not outlive the counter's root proof.
        path_retaining=handler_retaining|{r.name for r in self.program.routines if r.external}
        while True:
            inherited={name for name,targets in edges.items() if targets&path_retaining}
            if inherited<=path_retaining:break
            path_retaining.update(inherited)
        for routine in (None,*self.program.routines):
            self.current_routine=routine
            locals_={token.value for token,_ in routine.declarations} if routine else set()
            formals={token.value for token,_ in routine.parameters} if routine else set()
            types=self.types|(routine.local_types if routine else {})|self.private_using_roots
            for node in self.walk_nodes(routine.body if routine else self.program.body):
                if not isinstance(node,Expr) or node.kind!='call' or node.value not in path_retaining:continue
                callee=self.routines[node.value]
                for argument,(formal,expected) in zip(node.args,callee.parameters):
                    if formal.value not in callee.parameter_writes:continue
                    if argument.kind=='call' and argument.value=='BYNAME':
                        self.unknown_path_counter_alias=True;continue
                    if not self.argument_is_reference(argument,expected):continue
                    root=self.protection_root(argument)
                    if root not in types or not rt.path_counter_root(types[root]):continue
                    if root in locals_:self.retained_path_counter_roots.add((routine.name,root))
                    elif root in self.types and root not in formals:self.retained_path_counter_roots.add((None,root))
        self.current_routine=None

    def has_external_effect_call(self, expr):
        return any(isinstance(node, Expr) and node.kind == 'call' and node.value in self.routines
                   and (self.routines[node.value].side_effecting or self.routines[node.value].may_delay
                        or self.routines[node.value].may_write or self.routines[node.value].may_read or self.routines[node.value].may_abort
                        or self.routines[node.value].may_clock or self.routines[node.value].may_read_registers
                        or self.routines[node.value].may_write_registers or self.routines[node.value].may_services)
                   for node in self.walk_nodes(expr))

    def has_fresh_active_counters(self):
        locals_only=set(self.private_using_roots)
        if self.current_routine:locals_only.update(token.value for token,_ in self.current_routine.declarations)
        return self.active_counters <= locals_only

    def named_active_counters(self):
        return self.active_counters-self.private_using_roots.keys()
