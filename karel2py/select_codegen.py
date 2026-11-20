"""Emit checked SELECT cases for structured and label-dispatch bodies."""
from .select_analysis import check_select


class SelectLowering:
    """Capture the selector before evaluating dynamic CASE expressions."""

    def select_code(self, stmt):
        checked = check_select(stmt, mode=self.mode, expression=self.expression, require_type=self.require_type,
                               constant=self.constant, visible_constants=self.visible_constants, error=self.error)
        category, selector, spec = checked.category, checked.selector, checked.schema
        cases = [tuple(case.value for case in row) for row in checked.clauses]
        sites = []
        if category is None:
            table = repr(tuple(cases))
        else:
            expressions = []
            for case_index, row in enumerate(checked.clauses):
                codes = []
                for value_index, case in enumerate(row):
                    expr = case.source
                    code = f'_rt.select_scalar({case.code},{category!r},{expr.token.line})' if case.dynamic else repr(case.value)
                    codes.append(code)
                    sites.append(dict(clause=case_index, value_index=value_index, line=expr.token.line, column=expr.token.column,
                                      expression_kind=expr.kind, type=case.kind, dynamic=case.dynamic, evaluated_once=True))
                expressions.append('(' + ','.join(codes) + ',)')
            # Validate/capture the selector before any case expression effects.
            selector = f'_rt.select_scalar({selector},{category!r},{stmt.token.line})'
            table = '(' + ','.join(expressions) + ',)'
        self.select_scopes.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=stmt.token.line, column=stmt.token.column, case_values=cases,
                                       case_count=len(cases), has_else=stmt.has_else,
                                       empty_else=stmt.has_else and not stmt.alternate,
                                       no_match='else_clause' if stmt.has_else else 'KarelRuntimeError'))
        if category is not None:
            dynamic = any(site['dynamic'] for site in sites)
            case_types = [[case.kind for case in row] for row in checked.clauses]
            self.select_scopes[-1].update(selector_type=spec, comparison_category=category, case_types=case_types,
                dynamic_cases=dynamic, case_expressions=sites, case_evaluation='all_once_left_to_right_before_matching')
            if spec[0] in ('BOOLEAN', 'STRING', 'REAL'): self.features.add('Pythonic scalar SELECT')
            if dynamic: self.features.add('dynamic SELECT case expressions')
        self.features.add('SELECT first matching CASE')
        self.features.add('SELECT no-match guard')
        category_code = f',category={category!r}' if category is not None else ''
        return f'_rt.select_case({selector}, {table}, {stmt.has_else!r}, {stmt.token.line}{category_code})'

    def _emit_select_match(self, stmt, emit_case):
        token = stmt.token
        _, cases = stmt.args
        temporary = self.fresh()
        self.line(f'{temporary} = {self.select_code(stmt)}', token)
        self.line(f'match {temporary}:')
        self.indent += 1
        for index, (case_token, _, body) in enumerate(cases):
            self.line(f'case {index}:', case_token)
            self.indent += 1
            emit_case(index, body)
            self.indent -= 1
        self.line('case _:')
        self.indent += 1
        if stmt.has_else:
            emit_case(len(cases), stmt.alternate)
        else:
            self.line(f'raise _rt.KarelRuntimeError("No match in CASE", {token.line})', token)
        self.indent -= 2

    def emit_structured_select(self, stmt):
        self._emit_select_match(stmt, lambda _, body: self.block(body))

    def emit_dispatch_select(self, stmt, pc, targets):
        self._emit_select_match(stmt, lambda index, _: self.line(f'{pc} = {targets[index]!r}'))
