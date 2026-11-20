"""Resolve source constants, types, and declaration scopes."""
from .compiler_language import (
    ARRAY_ELEMENTS,
    ARRAY_SCALARS,
    BUILTIN_SIGNATURES,
    CONSTANT_BUILTINS,
    DATA_RECORD_TYPES,
    MAX_CONSTANT_BUILTIN_CALLS,
    MAX_CONSTANT_BUILTIN_DEPTH,
    NARROW_TYPES,
    POSITIONAL_VALUE_TYPES,
    PREDEFINED_CONSTANTS,
    RECORD_TYPES,
    blocked_controller_names,
)
from .syntax import Expr
from .lexer import Token
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
