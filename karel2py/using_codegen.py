"""Emit USING bindings at structured and label-dispatch scope entries."""


class UsingLowering:
    """Capture selectors once, in declaration order."""

    def emit_using_entry(self, stmt):
        if self.mode != 'pythonic':
            return
        for name, selector, kind in zip(stmt.using_captures, stmt.args, stmt.using_capture_kinds):
            selected = self.relative_operand_type(selector)
            line = selector.token.line
            if kind == 'computed_value':
                value, spec = self.expression(selector, raw=True)
            else:
                value, spec = self.reference(selector)

            if selected[0] == 'PATH':
                reference = f'_rt.using_path_header({selected!r},{value},{line},reference={kind=="storage_reference"})'
            elif kind == 'computed_value':
                reference = f'_rt.value_argument({spec!r},{value},{line})'
            else:
                record_selector = self.path_record_selector(selector)
                if record_selector is None:
                    reference = value
                else:
                    header = record_selector == 'path_header'
                    option = ',header=True' if header else ''
                    self.features.add('stable PATH header USING capture' if header else 'stable PATH node USING capture')
                    reference = f'_rt.using_path_node_reference({spec!r},{value},{line}{option})'
            self.line(f'{name} = {reference}', selector.token)
