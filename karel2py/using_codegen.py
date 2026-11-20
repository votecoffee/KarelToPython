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
            elif self.path_node_selector(selector):
                reference = f'_rt.using_path_node_reference({spec!r},{value},{line})'
                self.features.add('stable PATH node USING capture')
            else:
                reference = value
            self.line(f'{name} = {reference}', selector.token)
