"""Check source format literals for staged READ and WRITE."""
from .compiler_language import INTEGRAL_TYPES
from .lexer import TranslationError


def format_literal(expr, *, constants=None):
    """Recognize signed/grouped literals and optional named constants."""
    sign = 1
    while expr.kind == 'group' or expr.kind == 'unary' and expr.value in ('+', '-'):
        if expr.kind == 'unary' and expr.value == '-': sign = -sign
        expr = expr.args[0]
    if expr.kind == 'literal':
        value = expr.value
    elif expr.kind == 'name' and constants is not None:
        value = constants.get(expr.value)
    else:
        return None
    return sign * value if type(value) is int else None


def check_format_options(checker, data_type, options, operands, literals, *, error):
    """Accept a literal format if at least one possible selection supports it."""
    first_error = None
    for kinds in options:
        try:
            checker(data_type, kinds, operands, literals, error=error)
        except TranslationError as diagnostic:
            if first_error is None:
                first_error = diagnostic
        else:
            return
    raise first_error


def check_write_format(data_type, kinds, operands, literals, *, error):
    width = literals[0] if literals else None
    second = literals[1] if len(literals) == 2 else None
    if width is not None and (width < 0 or kinds != {'STRING'} and width > 254):
        error('E_WRITE_FORMAT', 'WRITE width must be nonnegative; numeric/BOOLEAN widths are limited to 254',
              operands[0].token)
    if 'BOOLEAN' in kinds and len(operands) == 2:
        error('E_WRITE_FORMAT', 'BOOLEAN WRITE accepts only a width', operands[1].token)
    if second is not None:
        valid = all(kind == 'STRING' and second in (0, 1, 2, 3)
                    or kind == 'REAL' and -254 <= second <= 254
                    or kind in INTEGRAL_TYPES and second in (0, *range(2, 17)) for kind in kinds)
        if not valid:
            error('E_WRITE_FORMAT', f'Invalid {data_type} WRITE second format specifier', operands[1].token)


def check_read_format(data_type, kinds, operands, literals, *, error):
    if literals and literals[0] is not None and not 0 <= literals[0] <= 254:
        error('E_READ_FORMAT', 'READ width must be in 0..254', operands[0].token)
    if len(literals) == 2 and literals[1] is not None:
        second = literals[1]
        valid = all(kind in ('BOOLEAN', 'REAL') or kind == 'STRING' and second in (0, 2)
                    or kind in INTEGRAL_TYPES and second in (0, *range(2, 17)) for kind in kinds)
        if not valid:
            error('E_READ_FORMAT', f'Invalid {data_type} READ second format specifier', operands[1].token)
