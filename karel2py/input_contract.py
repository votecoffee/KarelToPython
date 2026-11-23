"""Literal source-analysis contracts bound to generated Python syntax.

Neither contract extraction nor hashing imports or executes the selected module.
"""
import ast
import hashlib
import json


SCHEMA = 'karel2py.input-plan.v1'
PLAN_FIELD = 'input_analysis'
HASH_FIELD = 'input_analysis_sha256'
MAX_NODES = 50000
MAX_DEPTH = 100


class InputContractError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False).encode('ascii')).hexdigest()


def _class(tree):
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Program']
    if len(classes) != 1:
        raise InputContractError('One generated Program class is required')
    return classes[0]


def _field(node, name):
    return (isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name)


def module_digest(tree):
    """Stable across supported Python minors; ignore only the contract payload."""
    cls = _class(tree)
    plans = [node for node in cls.body if _field(node, PLAN_FIELD)]
    if len(plans) != 1:
        raise InputContractError('Re-translate the target to add its input-analysis contract')

    def encode(value):
        if value is plans[0]:
            return ['input-contract-payload']
        if isinstance(value, ast.AST):
            return [type(value).__name__, {key: encode(member) for key, member in ast.iter_fields(value)
                    if key != 'type_params' or member}]
        if isinstance(value, list):
            return [encode(member) for member in value]
        if type(value) is float:
            return ['float', value.hex()]
        if type(value) is bytes:
            return ['bytes', value.hex()]
        if type(value) is complex:
            return ['complex', value.real.hex(), value.imag.hex()]
        return value

    return digest(encode(tree))


def attach(source, plan):
    checksum = digest(plan)
    lines = source.splitlines()
    for name, value in ((HASH_FIELD, checksum), (PLAN_FIELD, plan)):
        marker = '    ' + name + ' = None'
        if lines.count(marker) != 1:
            raise InputContractError('Missing generated analysis placeholder')
        lines[lines.index(marker)] = '    ' + name + ' = ' + repr(value)
    interim = '\n'.join(lines) + '\n'
    # The payload checksum is included in the module fingerprint. Changing the
    # payload or execution syntax independently therefore invalidates extraction.
    module_hash = module_digest(ast.parse(interim, feature_version=(3, 11)))
    payload = dict(plan=plan, module_sha256=module_hash)
    index = next(i for i, line in enumerate(lines) if line.startswith('    ' + PLAN_FIELD + ' = '))
    lines[index] = '    ' + PLAN_FIELD + ' = ' + repr(payload)
    return '\n'.join(lines) + '\n'


def _entry_checkpoint(tree):
    """Recognize the emitted source checkpoint before the first body action."""
    methods = [node for node in _class(tree).body if isinstance(node, ast.FunctionDef) and node.name == '_execute']
    if len(methods) != 1 or len(methods[0].body) < 2:
        return False
    sentinel, guard = methods[0].body[:2]
    if (not isinstance(sentinel, ast.If) or not isinstance(sentinel.test, ast.Constant)
            or sentinel.test.value is not False or sentinel.orelse or not isinstance(guard, ast.Try)
            or not guard.body):
        return False
    first = guard.body[0]
    if isinstance(first, ast.Expr):
        checkpoint = first.value
        allowed = (set(), {'_source'})
    elif isinstance(first, ast.If) and isinstance(first.test, ast.UnaryOp) and isinstance(first.test.op, ast.Not):
        checkpoint = first.test.operand
        allowed = ({'_source', '_skippable'},)
    else:
        return False
    if not isinstance(checkpoint, ast.YieldFrom):
        return False
    call = checkpoint.value
    if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute)
            or not isinstance(call.func.value, ast.Name) or call.func.value.id != '_rt'
            or call.func.attr != 'checkpoint' or len(call.args) != 2):
        return False
    state, line = call.args
    flags = {keyword.arg for keyword in call.keywords}
    return (isinstance(state, ast.Attribute) and state.attr == '_state'
            and isinstance(state.value, ast.Name) and state.value.id == 'self'
            and isinstance(line, ast.Constant) and type(line.value) is int
            and len(flags) == len(call.keywords) and flags in allowed
            and all(isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in call.keywords))


def extract(source, *, inspect_entry=False):
    try:
        tree = ast.parse(source, feature_version=(3, 11))
        fields = {}
        program = _class(tree)
        for name in (PLAN_FIELD, HASH_FIELD):
            matches = [node for node in program.body if _field(node, name)]
            if len(matches) != 1:
                raise InputContractError('Re-translate the target to add its input-analysis contract')
            fields[name] = ast.literal_eval(matches[0].value)
        payload = fields[PLAN_FIELD]
        if type(payload) is not dict or set(payload) != {'plan', 'module_sha256'}:
            raise InputContractError('Malformed input-analysis contract')
        plan = payload['plan']
        if type(plan) is not dict or plan.get('schema') != SCHEMA or digest(plan) != fields[HASH_FIELD]:
            raise InputContractError('Input-analysis payload changed; re-translate the target')
        if module_digest(tree) != payload['module_sha256']:
            raise InputContractError('Python execution syntax changed; re-translate before discovery')
        aliases = [node for node in program.body if _field(node, 'variable_types')]
        if len(aliases) == 1:
            try:
                variable_types = ast.literal_eval(aliases[0].value)
            except ValueError as error:
                raise InputContractError('Invalid declared variable types') from error
            if type(variable_types) is not dict:
                raise InputContractError('Invalid declared variable types')
            plan = dict(plan, variable_types=variable_types)
        directives = [node for node in program.body if _field(node, 'source_directives')]
        if len(directives) == 1:
            try:
                pairs = ast.literal_eval(directives[0].value)
            except ValueError as error:
                raise InputContractError('Invalid source directives') from error
            if (type(pairs) is not tuple or any(type(pair) is not tuple or len(pair) != 2
                                                or type(pair[0]) is not str
                                                or pair[0] == '%COMMENT' and type(pair[1]) is not str for pair in pairs)):
                raise InputContractError('Invalid source directives')
            plan = dict(plan, source_comment=next((argument for directive, argument in pairs
                                                   if directive == '%COMMENT'), None))
        return dict(plan, entry_checkpoint=_entry_checkpoint(tree)) if inspect_entry else plan
    except (SyntaxError, TypeError, RecursionError) as error:
        raise InputContractError('Invalid generated analysis contract: ' + str(error)) from error


def build(program, emitter):
    """Serialize compiler-owned data only; unsupported/big plans stay explicit."""
    remaining = MAX_NODES
    used_records = set()

    def encode(value, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            raise InputContractError('Input-analysis plan exceeds its node/depth budget')
        if type(value) in (str, int, float, bool) or value is None:
            return value
        if type(value) in (list, tuple):
            return [encode(item, depth + 1) for item in value]
        if type(value) is dict:
            return {str(key): encode(item, depth + 1) for key, item in value.items()}
        kind = type(value).__name__
        if kind == 'Token':
            return dict(token=value.value, line=value.line, column=value.column)
        if kind in ('Expr', 'Statement'):
            row = dict(kind=value.kind, line=value.token.line, column=value.token.column)
            row['args'] = encode(value.args, depth + 1)
            if kind == 'Expr':
                row['value'] = encode(value.value, depth + 1)
                if value.kind == 'index' and emitter.path_header_index(value.args[-1]):
                    row['static_zero_subscript'] = True
                if value.kind=='binary' and value.value in ('AND','OR'):
                    row['evaluation']=encode('short-circuit' if id(value) in emitter.short_circuit_expressions else 'eager',depth+1)
                if value.kind == 'call' and value.value in emitter.routines:
                    routine = emitter.routines[value.value]
                    modes = []
                    for argument, (_, expected) in zip(value.args, routine.parameters):
                        try:
                            modes.append('reference' if emitter.argument_is_reference(argument, expected) else 'value')
                        except Exception:
                            modes.append('unknown')
                    row['passing'] = modes
                elif value.kind == 'call':
                    from .extended import PROCEDURES, FUNCTIONS, signature_for
                    if value.value in ('GET_POS_REG','GET_EPOS_REG','GET_JPOS_REG','SET_POS_REG','SET_EPOS_REG','SET_JPOS_REG'):
                        used_records.add('XYZWPREXT')
                    if value.value == 'NODE_SIZE' and id(value) in emitter.node_size_schemas:
                        row['node_data_type'] = encode(emitter.node_size_schemas[id(value)], depth + 1)
                    if value.value in PROCEDURES or value.value in FUNCTIONS:
                        try:
                            row['signature'] = encode(signature_for(value.value, len(value.args)), depth + 1)
                        except ValueError:
                            pass
            else:
                row.update(body=encode(value.body, depth + 1), alternate=encode(value.alternate, depth + 1), has_else=value.has_else)
                if value.kind == 'assign':
                    conversion = emitter.geometry_assignment_conversions.get(id(value.args[0]))
                    if conversion is not None:
                        row['geometry_assignment'] = encode(conversion, depth + 1)
                    schema = emitter.path_assignment_schemas.get(id(value.args[0]))
                    if schema is not None:
                        row['path_assignment_type'] = encode(schema, depth + 1)
                    schema = emitter.path_array_conversion_schemas.get(id(value.args[0]))
                    if schema is not None:
                        row['path_array_conversion_type'] = encode(schema, depth + 1)
                callback = emitter.callback_input_plans.get(id(value))
                if callback is not None:
                    row.update(encode(callback, depth + 1))
            return row
        return dict(unsupported_type=kind)

    previous = emitter.current_routine
    try:
        emitter.current_routine = None
        body = encode(program.body)
        routines = {}
        for routine in program.routines:
            emitter.current_routine = routine
            routines[routine.name] = dict(parameters=[[token.value, encode(spec)] for token, spec in routine.parameters],
                types=encode(routine.local_types), constants=encode(routine.local_constants),
                result=encode(routine.return_type), external=routine.external, body=encode(routine.body))
        group = next((row['argument'] for row in program.directive_metadata if row['name'] == '%DEFGROUP'), None)
        groups = set(row['group'] for row in emitter.group_uses)
        if group is None and len(groups) == 1:
            group = next(iter(groups))
        from .runtime import DATA_RECORD_FIELDS, PREDEFINED_STRUCTURES
        from .extended import PORT_TYPES
        fields = {}
        default_path_node = None

        def collect(spec):
            nonlocal default_path_node
            if type(spec) is not tuple:
                return
            if len(spec) == 3 and spec[0] == 'PATH' and spec[1] is None:
                if default_path_node is None:
                    default_path_node = PREDEFINED_STRUCTURES['STD_PTH_NODE']
                    collect(default_path_node)
            if spec and type(spec[0]) is str and spec[0] in DATA_RECORD_FIELDS and spec[0] not in fields:
                fields[spec[0]] = dict(DATA_RECORD_FIELDS[spec[0]])
                for member in fields[spec[0]].values():
                    collect(member)
            for member in spec:
                if type(member) is tuple:
                    collect(member)
        for spec in (*emitter.types.values(), *(spec for routine in program.routines for spec in routine.local_types.values())):
            collect(spec)
        for name in used_records:
            collect((name,))
        return dict(schema=SCHEMA, status='available', program=program.name,
                    types=encode(emitter.types), constants=encode(emitter.constants),
                    imports=encode(program.imported_variables), default_group=group,
                    record_fields=encode(fields), port_types=encode(PORT_TYPES),
                    path_index_io=True, default_path_node=encode(default_path_node),
                    source_map=encode(emitter.source_map),
                    body=body, routines=routines)
    except (InputContractError, RecursionError) as error:
        return dict(schema=SCHEMA, status='unavailable', reason=str(error), program=program.name)
    finally:
        emitter.current_routine = previous
