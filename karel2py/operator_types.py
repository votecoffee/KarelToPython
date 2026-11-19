"""Source operator type rules independent of expression emission."""
from .compiler_language import NARROW_TYPES


INTEGER = ('INTEGER',)
REAL = ('REAL',)
BOOLEAN = ('BOOLEAN',)
VECTOR = ('VECTOR',)
NUMERIC = ('INTEGER', 'REAL')
COMPARISONS = ('=', '<>', '<', '<=', '>', '>=')
POSE_OPERANDS = ('XYZWPR', 'POSITION', 'XYZWPREXT', 'JOINTPOS')


def operand_type(spec):
    """BYTE and SHORT operate on their INTEGER values."""
    return INTEGER if spec[0] in NARROW_TYPES else spec


def unary_result(operator, operand, *, mode):
    """Return the result schema, or None for an invalid operand."""
    operand = operand_type(operand)
    if operator == 'NOT':
        return operand if operand[0] in ('BOOLEAN', 'INTEGER') else None
    allowed = NUMERIC
    if mode == 'pythonic' and operator in ('+', '-'):
        allowed += ('VECTOR', 'BOOLEAN') if operator == '+' else ('VECTOR',)
    return operand if operand[0] in allowed else None


def binary_result(operator, left, right, *, mode):
    """Check normalized operand schemas. Relative poses use scoped geometry rules."""
    left_kind, right_kind = left[0], right[0]
    if operator == '>=<':
        if mode == 'pythonic' and left_kind in POSE_OPERANDS and right_kind in POSE_OPERANDS:
            return BOOLEAN
        return None
    if 'VECTOR' in (left_kind, right_kind):
        if left == right == VECTOR:
            if operator in ('=', '<>'):
                return BOOLEAN
            if operator == '@':
                return REAL
            if operator in ('+', '-', '#'):
                return VECTOR
        if operator in ('*', '/') and (left == VECTOR and right_kind in NUMERIC or
                                       right == VECTOR and left_kind in NUMERIC):
            return VECTOR
        return None

    numeric = left_kind in NUMERIC and right_kind in NUMERIC
    if operator in COMPARISONS:
        if numeric or left_kind == right_kind and left_kind in ('BOOLEAN', 'STRING'):
            return BOOLEAN
    elif operator in ('AND', 'OR'):
        if left_kind == right_kind and left_kind in ('INTEGER', 'BOOLEAN'):
            return left
    elif numeric and operator in ('+', '-', '*', '/'):
        return REAL if operator == '/' or 'REAL' in (left_kind, right_kind) else left
    elif operator in ('DIV', 'MOD') and left_kind == right_kind == 'INTEGER':
        return left
    elif operator == '+' and left_kind == right_kind == 'STRING':
        return left
    return None
