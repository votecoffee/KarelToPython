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


def extract(source):
    try:
        tree = ast.parse(source, feature_version=(3, 11))
        fields = {}
        for name in (PLAN_FIELD, HASH_FIELD):
            matches = [node for node in _class(tree).body if _field(node, name)]
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
        return plan
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
                    if value.value in PROCEDURES or value.value in FUNCTIONS:
                        try:
                            row['signature'] = encode(signature_for(value.value, len(value.args)), depth + 1)
                        except ValueError:
                            pass
            else:
                row.update(body=encode(value.body, depth + 1), alternate=encode(value.alternate, depth + 1), has_else=value.has_else)
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
        from .runtime import DATA_RECORD_FIELDS
        from .extended import PORT_TYPES
        fields = {}
        def collect(spec):
            if type(spec) is not tuple:
                return
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
                    source_map=encode(emitter.source_map),
                    body=body, routines=routines)
    except (InputContractError, RecursionError) as error:
        return dict(schema=SCHEMA, status='unavailable', reason=str(error), program=program.name)
    finally:
        emitter.current_routine = previous
