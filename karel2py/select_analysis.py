"""Check the selector and CASE expressions before assembling a dispatch call."""
from dataclasses import dataclass

from . import runtime as rt
from .compiler_language import INTEGRAL_TYPES
from .syntax import Expr


@dataclass(frozen=True)
class CheckedCase:
    source: Expr
    kind: str
    value: object = None
    code: str | None = None

    @property
    def dynamic(self):
        return self.code is not None


@dataclass(frozen=True)
class CheckedSelect:
    selector: str
    schema: tuple
    category: str | None
    clauses: tuple


def _category(kind):
    if kind in (*INTEGRAL_TYPES, 'REAL'):
        return 'NUMERIC'
    return kind if kind in ('BOOLEAN', 'STRING') else None


def _constant_form(expr, names):
    if expr.kind in ('literal', 'real_literal', 'predefined'):
        return True
    if expr.kind == 'name':
        return expr.value in names()
    return expr.kind in ('group', 'unary', 'binary') and all(_constant_form(child, names) for child in expr.args)


def check_select(statement, *, mode, expression, require_type, constant, visible_constants, error):
    """Return typed CASE rows in source order with their original locations."""
    source, cases = statement.args
    pythonic = mode == 'pythonic'
    category = None
    if pythonic:
        selector, schema = expression(source)
        category = _category(schema[0])
        if category is None:
            error('E_TYPE', 'SELECT requires BOOLEAN, ASCII STRING or finite numeric scalar values', source.token)
    else:
        selector = require_type(source, 'INTEGER')
        schema = ('INTEGER',)

    clauses = []
    scalar_types = {bool: 'BOOLEAN', int: 'INTEGER', float: 'REAL', str: 'STRING'}
    for _, values, _ in cases:
        row = []
        for expr in values:
            if pythonic and not _constant_form(expr, visible_constants):
                code, spec = expression(expr)
                if _category(spec[0]) != category:
                    error('E_CASE', f'CASE expression does not match SELECT {category} category', expr.token)
                row.append(CheckedCase(expr, spec[0], code=code))
                continue
            value = constant(expr)
            if pythonic:
                try:
                    rt.select_scalar(value, category, expr.token.line)
                except rt.KarelRuntimeError as exc:
                    error('E_CASE', f'CASE constant does not match SELECT {category} category: {exc}', expr.token)
            elif type(value) is not int or not -2147483648 <= value <= 2147483647:
                error('E_CASE', 'CASE values must be INTEGER constants', expr.token)
            row.append(CheckedCase(expr, scalar_types[type(value)], value=value))
        clauses.append(tuple(row))
    return CheckedSelect(selector, schema, category, tuple(clauses))
