"""Generate staged READ and WRITE operations for the offline runtime."""
from typing import NamedTuple

from . import extended as ex, runtime as rt
from .compiler_language import INTEGRAL_TYPES, NARROW_TYPES
from .statement_io_analysis import check_format_options, check_read_format, check_write_format, format_literal
from .syntax import Expr


class _PathIOSelection(NamedTuple):
    receiver: Expr
    formats: tuple[set[str], ...]
    bounds: str
    kind: str


class StatementIOLowering:
    """Capture operands before the runtime publishes input or output."""

    def lower_explicit_file_io(self, stmt):
        selector, operation = stmt.args
        file_value = self.require_type(selector, 'FILE')
        captured = self.fresh()
        self.line(f'{captured}={file_value}', stmt.token)
        self.features.add('memory files')
        self.statement(operation, file_code=captured)

    def lower_file_cancel(self, stmt):
        token = stmt.token
        selector = stmt.args[0]
        if selector is None:
            file_value = f'self._state.default_file("READ",{token.line},required=True)'
        else:
            file_value = self.require_type(selector, 'FILE')
        self.features.add('cooperative FILE cancellation')
        self.line(f'_rt.cancel_file(self._state,{file_value},{token.line})', token)

    def lower_file_lifecycle(self, stmt):
        token = stmt.token
        selector = stmt.args[0]
        opening = stmt.kind == 'file_open'
        if opening and self.is_predefined_file(selector):
            self.error('E_PREDEFINED_FILE_OPEN', 'Configure predefined FILE endpoints through ExecutionContext bindings', token)
        file_value = self.require_type(selector, 'FILE')
        self.features.add('memory files')
        if opening:
            mode = self.require_type(stmt.args[1], 'STRING')
            name = self.require_type(stmt.args[2], 'STRING')
            self.line(f'self._state.file_open({file_value},{mode},{name},{token.line})', token)
        else:
            self.line(f'self._state.file_close({file_value},{token.line})', token)

    def _bind_statement_file(self, operation, token, file_code):
        if self.mode != 'pythonic' or file_code is not None:
            return file_code, False
        file_code = self.fresh()
        self.line(f'{file_code}=self._state.default_file({operation!r},{token.line})', token)
        return file_code, True

    def _read_call(self, file_code, optional):
        if not file_code:
            return 'self._state.read_items('
        if self.cooperative:
            method = 'cooperative_optional_file_read' if optional else 'cooperative_file_read'
            return f'yield from _rt.{method}(self._state,{file_code},'
        method = 'optional_file_read' if optional else 'file_read'
        return f'self._state.{method}({file_code},'

    def _path_io_selection(self, operand):
        """Resolve a range or a single PATH index that can select the header."""
        while operand.kind == 'group':
            operand = operand.args[0]
        if operand.kind == 'path_io_range':
            receiver, start, end = operand.args
        elif operand.kind == 'index':
            receiver, *indexes = operand.args
            start = indexes[-1]
            index = format_literal(start, constants=self.visible_constants())
            if index is not None and index != 0:
                return None
            if receiver.kind == 'name' and receiver.value in ex.PORT_TYPES and receiver.value not in self.types:
                return None
            spec = self.access_type(receiver)
            if rt.collection_array_node_type(spec, len(indexes)) is not None:
                receiver = Expr('index', operand.token, args=[receiver, *indexes[:-1]])
            elif spec[0] != 'PATH' or len(indexes) != 1:
                return None
            end = None
        else:
            return None

        spec = self.access_type(receiver)
        if spec[0] != 'PATH':
            self.error('E_PATH_IO', 'READ/WRITE range requires a PATH receiver', operand.token)
        node, header = rt.path_io_components(spec, operand.token.line)
        if end is None:
            if index == 0:
                if header is None:
                    self.error('E_PATH_IO', 'READ/WRITE index 0 requires a declared PATHHEADER', operand.token)
                return _PathIOSelection(receiver, (rt.aggregate_format_kinds(header),), '(0, None)', 'header')
            if header is None:
                return None
            first = self.require_type(start, 'INTEGER')
            options = (rt.aggregate_format_kinds(node), rt.aggregate_format_kinds(header))
            return _PathIOSelection(receiver, options, f'({first}, None)', 'index')

        first = self.require_type(start, 'INTEGER')
        last = self.require_type(end, 'INTEGER')
        node_formats = rt.aggregate_format_kinds(node)
        options = (node_formats,)
        leading_index = format_literal(start, constants=self.visible_constants())
        trailing_index = format_literal(end, constants=self.visible_constants())
        if header is not None and (leading_index in (0, None) or trailing_index in (0, None)):
            header_formats = rt.aggregate_format_kinds(header)
            options = ()
            if leading_index != 0 and trailing_index != 0:
                options += (node_formats,)
            if leading_index in (0, None) and trailing_index in (0, None):
                options += (header_formats,)
            if leading_index != 0 or trailing_index != 0:
                options += (node_formats | header_formats,)
        return _PathIOSelection(receiver, options, f'({first}, {last})', 'range')

    def lower_write_items(self, stmt, file_code):
        token, line = stmt.token, stmt.token.line
        file_code, optional_file = self._bind_statement_file('WRITE', token, file_code)
        pieces, items = [], []
        write_groups=[];aggregate_output=False
        for item in stmt.args:
            if item.kind == 'write_cr':
                pieces.append(repr('\n'));write_groups.append('['+repr('\n')+']')
                items.append(dict(data_type='CR', line=item.token.line, column=item.token.column,
                                  format_specifiers=[]))
                continue
            selection = self._path_io_selection(item.args[0])
            operand = selection.receiver if selection else item.args[0]
            value, spec = self.expression(operand, collection_io=True)
            data_type = spec[0]
            self.write_item_types[id(item)] = data_type
            aggregate=data_type not in ('STRING','BOOLEAN','INTEGER','REAL',*NARROW_TYPES)
            if aggregate and (self.mode!='pythonic' or not rt.aggregate_write_type(spec)):
                self.error('E_TYPE',f'WRITE requires scalar or resource-free aggregate data, found {data_type}',item.token)
            aggregate_output=aggregate_output or aggregate
            format_exprs = item.args[1:]
            format_options = selection.formats if selection else (
                rt.aggregate_format_kinds(spec) if aggregate else {data_type},
            )
            format_codes = [self.require_type(expr, 'INTEGER') for expr in format_exprs]
            literals = [format_literal(expr) for expr in format_exprs]
            formats = [literal if literal is not None else dict(expression=True, line=expr.token.line,
                        column=expr.token.column) for literal, expr in zip(literals, format_exprs)]
            check_format_options(check_write_format, data_type, format_options,
                                 format_exprs, literals, error=self.error)
            if aggregate:
                options=f',file={file_code}' if file_code else ''
                check=',check=self._state.tick' if rt.collection_type(spec) or rt.collection_array_type(spec) else ''
                bounds = f',bounds={selection.bounds}' if selection else ''
                rendered=(f'_rt.format_aggregate_write(_rt.capture_aggregate_write({spec!r},{value},{item.token.line}{check}{bounds}),[{", ".join(format_codes)}],{item.token.line}{options})'
                          if format_exprs else f'_rt.aggregate_write_pieces({spec!r},{value},{item.token.line}{options}{check}{bounds})')
                write_groups.append(rendered);pieces.append(rendered)
            else:
                rendered=f'_rt.{"optional_file_piece" if optional_file else "file_piece"}({file_code},{data_type!r},{value},[{", ".join(format_codes)}],{item.token.line})' if file_code else f'_rt.format_write_item({data_type!r}, {value}, [{", ".join(format_codes)}], {item.token.line})'
                pieces.append(rendered);write_groups.append('['+rendered+']')
            items.append(dict(data_type=data_type, line=item.token.line, column=item.token.column,
                              format_specifiers=formats, dynamic_formats=any(x is None for x in literals)))
            if aggregate:
                items[-1].update(aggregate=True,type_spec=spec,scalar_order='ARRAY-row-major/QUEUE-entry-order/INTEGER-values' if rt.queue_io_type(spec) else 'ARRAY-row-major/PATH-header/nodes/declaration/row-major/joint-axis' if rt.path_array_io_type(spec) else 'PATH-header/nodes/declaration/row-major/joint-axis' if data_type=='PATH' else 'declaration/row-major/joint-axis',formats='uniform scalar formats' if format_exprs else 'scalar defaults',capture_before_formats=True)
                self.features.add('whole data aggregate WRITE')
                if selection:
                    items[-1].update(path_selection=selection.kind,
                                     scalar_order='selected PATH records in index order, then declaration/row-major/joint-axis')
                    self.features.add('selected PATH WRITE')
            self.features.add(f'WRITE {data_type} output request')
            if formats: self.features.add(f'WRITE {data_type} formatting')
        file_option=f',file={file_code}' if file_code else ''
        if self.cooperative:
            method='cooperative_write_groups' if aggregate_output else 'cooperative_write_items'
            values=write_groups if aggregate_output else pieces
            self.line(f'yield from _rt.{method}(self._state,[{", ".join(values)}],{line}{file_option})',token)
        elif aggregate_output:self.line(f'self._state.write_groups([{", ".join(write_groups)}], {line}{file_option})',token)
        else:self.line(f'self._state.write_items([{", ".join(pieces)}], {line}{file_option})', token)
        self.features.add('WRITE output request')
        if any(item['data_type'] == 'CR' for item in items): self.features.add('WRITE CR newline')
        if len(items) > 1: self.features.add('WRITE multiple data items')
        self.write_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                    line=token.line, column=token.column,
                                    data_type=items[0]['data_type'] if len(items) == 1 else 'MIXED',
                                    data_items=len(items), items=items, evaluated='Left to right, once per expression: value, width, second format; validate/render each item before the next; one request after complete rendering',
                                    format_specifiers=items[0]['format_specifiers'] if len(items) == 1 else []))
        if len(items) == 1 and items[0]['data_type'] != 'CR' and not items[0].get('aggregate'):
            formats = items[0]['format_specifiers']
            width = formats[0] if formats else None
            is_string = items[0]['data_type'] == 'STRING'
            alignment = formats[1] if is_string and len(formats) == 2 else 0
            dynamic_width = isinstance(width, dict)
            dynamic_alignment = isinstance(alignment, dict)
            self.write_uses[-1].update(
                format_width=width, alignment='dynamic' if dynamic_alignment else 'right' if not is_string or alignment in (1, 3) else 'left',
                quoted='dynamic' if dynamic_alignment else is_string and alignment in (2, 3),
                width_policy=('dynamic' if dynamic_width or dynamic_alignment else
                              'contents_length' if is_string and width is not None and (width == 0 or width > 254)
                              else 'fixed' if is_string and formats else 'minimum' if formats else 'unformatted'))

    def lower_legacy_write(self, stmt):
        token, line = stmt.token, stmt.token.line
        value, spec = self.expression(stmt.args[0])
        data_type = spec[0]
        if data_type not in ('STRING', 'BOOLEAN', 'INTEGER'):
            self.error('E_TYPE', f'WRITE requires STRING or unformatted BOOLEAN/INTEGER, found {data_type}', stmt.args[0].token)
        formats = stmt.args[1]
        width = formats[0] if formats else None
        alignment = formats[1] if len(formats) == 2 else 0
        if data_type in ('BOOLEAN', 'INTEGER'):
            if formats:
                self.error('E_WRITE_FORMAT', f'{data_type} WRITE formatting is not implemented; use the unformatted default', stmt.args[2][0])
            self.line(f'self._state.write_{data_type.lower()}({value}, {line})', token)
            evaluated = ('once; initialization/INTEGER/nonnegative guard before request' if data_type == 'INTEGER'
                         else 'once; initialization/BOOLEAN guard before request')
        else:
            if alignment in (2, 3) and not 1 <= width <= 254:
                self.error('E_WRITE_FORMAT', 'Quoted WRITE requires literal width 1..254; quoted width fallback is not implemented', stmt.args[2][0])
            options = f', width={width}, alignment={alignment}' if formats else ''
            self.line(f'self._state.write_string({value}, {line}{options})', token)
            evaluated = 'once; ASCII/length guard before formatting/request'
            if formats: self.features.add('WRITE STRING formatting')
        self.features.add(f'WRITE {data_type} output request')
        self.write_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                    line=token.line, column=token.column, data_type=data_type,
                                    data_items=1, evaluated=evaluated,
                                    format_specifiers=formats, format_width=width,
                                    alignment='right' if alignment in (1, 3) else 'left',
                                    quoted=alignment in (2, 3),
                                    width_policy=('contents_length' if width == 0 or (width is not None and width > 254)
                                                  else 'fixed' if formats else 'unformatted')))

    def lower_read(self, stmt, file_code):
        token, line = stmt.token, stmt.token.line
        file_code, optional_file = self._bind_statement_file('READ', token, file_code)
        references, destinations, line_breaks = [], [], []
        read_groups=[];aggregate_input=False
        formatted = any(item.kind == 'read_item' for item in stmt.args)
        for item in stmt.args:
            if item.kind == 'read_cr':
                line_breaks.append(len(references))
                continue
            target = item.args[0] if item.kind == 'read_item' else item
            format_exprs = item.args[1:] if item.kind == 'read_item' else []
            selection = self._path_io_selection(target)
            receiver = selection.receiver if selection else target
            root = self.check_read_target(receiver)
            reference, spec = self.reference(receiver,config_read=self.mode=='pythonic' and self.is_config_subfield(receiver),allow_prefix=self.mode=='pythonic',collection_prefix=self.mode=='pythonic' and rt.collection_array_type(self.access_type(receiver)),collection_io=True)
            aggregate=spec[0] not in (*INTEGRAL_TYPES,'BOOLEAN','REAL','STRING')
            if aggregate and (self.mode!='pythonic' or not rt.aggregate_read_type(spec)):
                self.error('E_READ_TYPE','READ requires scalar or Pythonic resource-free aggregate data',target.token)
            format_options = selection.formats if selection else (
                rt.aggregate_format_kinds(spec) if aggregate else {spec[0]},
            )
            aggregate_input=aggregate_input or aggregate
            format_codes = [self.require_type(expr, 'INTEGER') for expr in format_exprs]
            literals = [format_literal(expr) for expr in format_exprs]
            check_format_options(check_read_format, spec[0], format_options,
                                 format_exprs, literals, error=self.error)
            if aggregate:
                check=',check=self._state.tick' if rt.collection_type(spec) or rt.collection_array_type(spec) else ''
                bounds = f',bounds={selection.bounds}' if selection else ''
                captured_group=f'_rt.capture_aggregate_read_target({reference}, [], {line}{check}{bounds})'
                read_groups.append(f'_rt.format_aggregate_read_group({captured_group},[{", ".join(format_codes)}],{line})' if format_exprs else captured_group)
            else:read_groups.append(f'[_rt.capture_read_target({reference}, [{", ".join(format_codes)}], {line})]')
            references.append(f'_rt.capture_read_target({reference}, [{", ".join(format_codes)}], {line})'
                              if formatted else reference)
            destinations.append(dict(root=root, expression_kind=target.kind, type_spec=spec,
                                     line=target.token.line, column=target.token.column))
            if aggregate:
                destinations[-1].update(aggregate=True,scalar_order='ARRAY-row-major/QUEUE-entry-order/INTEGER-values' if rt.queue_io_type(spec) else 'ARRAY-row-major/PATH-header/nodes/declaration/row-major/joint-axis' if rt.path_array_io_type(spec) else 'PATH-header/nodes/declaration/row-major/joint-axis' if spec[0]=='PATH' else 'declaration/row-major/joint-axis',formats='uniform scalar formats' if format_exprs else 'scalar defaults',capture_before_formats=True)
                self.features.add('whole data aggregate READ')
                if selection:
                    destinations[-1].update(path_selection=selection.kind,
                                            scalar_order='selected PATH records in index order, then declaration/row-major/joint-axis')
                    self.features.add('selected PATH READ')
            if self.mode=='pythonic' and self.is_config_subfield(receiver):
                self.features.add('bounded CONFIG field READ')
                destination=dict(body=self.current_routine.name if self.current_routine else self.program.name,
                    root=root,field=target.value,type_spec=spec,line=target.token.line,column=target.token.column,
                    file_input=bool(file_code) and not optional_file,target_evaluated_once=True,validated_before_publication=True)
                if spec==('INTEGER',):destination['integer_range']=[-8,7]
                self.config_field_read_uses.append(destination)
                destinations[-1]['config_field']=target.value
                if spec==('INTEGER',):destinations[-1]['integer_range']=[-8,7]
            if format_exprs:
                destinations[-1].update(format_specifiers=[literal if literal is not None else dict(expression=True,
                    line=expr.token.line, column=expr.token.column) for literal, expr in zip(literals, format_exprs)],
                    dynamic_formats=any(value is None for value in literals))
                self.features.add(f'READ {spec[0]} formatting')
        controls = f', line_breaks={tuple(line_breaks)!r}' if line_breaks else ''
        reader = self._read_call(file_code, optional_file)
        if aggregate_input:
            captured=self.fresh();flat_targets=self.fresh();flat_formats=self.fresh();flat_breaks=self.fresh()
            self.line(f'{captured} = [{", ".join(read_groups)}]',token)
            self.line(f'{flat_targets}, {flat_formats}, {flat_breaks} = _rt.flatten_read_groups({captured}, {tuple(line_breaks)!r}, {line})',token)
            self.line(f'{reader}{flat_targets}, {line}, line_breaks={flat_breaks}, formats={flat_formats})',token)
        elif formatted:
            captured = self.fresh()
            self.line(f'{captured} = [{", ".join(references)}]', token)
            self.line(f'{reader}[item[0] for item in {captured}], {line}{controls}, formats=[item[1] for item in {captured}])', token)
        else:
            self.line(f'{reader}[{", ".join(references)}], {line}{controls})', token)
        self.read_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                   line=line, column=token.column, destinations=destinations,
                                   targets_evaluated_once=True, response_validated_before_assignment=True))
        if line_breaks: self.read_uses[-1]['line_breaks'] = line_breaks
