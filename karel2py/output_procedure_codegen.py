"""Emit conversion, register, and pose procedures with checked output references."""
from . import runtime as rt
from .compiler_language import BUILTIN_PROCEDURES, CONVERSION_OUTPUT_TYPES


class OutputProcedureLowering:
    """Validate output storage and emit the checked runtime procedure calls."""

    def conversion_procedure(self, expr):
        inputs = BUILTIN_PROCEDURES[expr.value]
        if len(expr.args) != len(inputs) + 1:
            self.error('E_ARGUMENTS', f'{expr.value} requires {len(inputs) + 1} arguments', expr.token)
        if self.mode == 'strict' and any(self.has_routine_call(argument) for argument in expr.args):
            self.error('E_EVALUATION_ORDER', 'Conversion arguments containing user routine calls need evaluation-order validation', expr.token)
        self.check_for_call(expr.token)
        destination = expr.args[-1]
        if destination.kind not in ('name', 'index', 'field') or self.root_name(destination) in self.visible_constants():
            self.error('E_OUTPUT_ARGUMENT', 'Conversion output requires a writable variable, field or array element', destination.token)
        if self.protection_root(destination) in self.active_counters:
            self.error('E_FOR_COUNTER', 'Conversion cannot write an active FOR counter', destination.token)
        if self.is_position_read_only_access(destination):
            self.error('E_POSITION_READ_ONLY', 'POSITION orientation fields cannot be conversion outputs', destination.token)
        reference, actual = self.reference(destination)
        if self.is_value_only_subfield(destination):
            self.error('E_CONFIG_OUTPUT', 'CONFIG/association subfields have value-only routine passing; conversion output aliases remain blocked', destination.token)
        required = CONVERSION_OUTPUT_TYPES[expr.value]
        if actual[0] != required:
            self.error('E_TYPE', f'{expr.value} output requires {required} storage; narrow numeric outputs are not promoted', destination.token)
        codes = [self.require_type(argument, expected) for argument, expected in zip(expr.args[:-1], inputs)]
        self.features.add(expr.value)
        self.features.add('conversion output by reference')
        return f'_rt.conversion_procedure({expr.value!r}, {", ".join(codes)}, {reference}, line={expr.token.line})'

    def config_text_conversion(self, expr):
        parsing = expr.value == 'CNV_STR_CONF'
        count = 3 if parsing else 2
        grouped=parsing and len(expr.args)==4
        if len(expr.args)!=count and not grouped:
            message='CNV_STR_CONF requires three arguments and an optional group' if parsing else f'{expr.value} requires {count} arguments'
            self.error('E_ARGUMENTS',message,expr.token)
        self.check_for_call(expr.token)
        source = self.require_type(expr.args[0], 'STRING' if parsing else 'CONFIG')
        if not parsing: source = f'_rt.positional_value(("CONFIG",), {source}, {expr.args[0].token.line})'
        outputs = []
        for argument, expected in zip(expr.args[1:], ('CONFIG','INTEGER') if parsing else ('STRING',)):
            base = argument
            while base.kind in ('field', 'index'): base = base.args[0]
            if argument.kind not in ('name', 'field', 'index') or base.kind not in ('name','using_ref') or base.value in self.visible_constants():
                self.error('E_OUTPUT_ARGUMENT', 'CONFIG conversion outputs require storage rooted in a variable', argument.token)
            if self.protection_root(base) in self.active_counters: self.error('E_FOR_COUNTER', 'CONFIG conversion cannot write an active FOR counter', argument.token)
            if self.is_position_read_only_access(argument): self.error('E_POSITION_READ_ONLY', 'CONFIG conversion output is read-only', argument.token)
            if self.is_value_only_subfield(argument): self.error('E_CONFIG_OUTPUT', 'CONFIG/association subfields cannot be conversion output aliases', argument.token)
            code, spec = self.reference(argument)
            if spec[0] != expected: self.error('E_TYPE', f'{expr.value} output requires {expected}', argument.token)
            outputs.append(code)
        self.features.add(expr.value)
        order=['source','target','status'] if parsing else ['source','target']
        options=''
        if grouped:
            group=self.require_type(expr.args[3],'INTEGER')
            options=f", group={group}, formats=self._state.execution.require('config_text',{expr.token.line})"
            order.append('group')
        self.config_text_uses.append(dict(name=expr.value, body=self.current_routine.name if self.current_routine else self.program.name,
                                         line=expr.token.line, column=expr.token.column, arguments_evaluated_once=True,
                                         argument_order=order,
                                         outputs=2 if parsing else 1, source_copied=not parsing))
        return f'_rt.config_text_conversion({expr.value!r}, {source}, {", ".join(outputs)}, line={expr.token.line}{options})'

    def numeric_register(self, expr):
        reading = expr.value == 'GET_REG'
        if len(expr.args) != (5 if reading else 3):
            self.error('E_ARGUMENTS', f'{expr.value} requires {5 if reading else 3} arguments',expr.token)
        self.check_for_call(expr.token)
        codes = [self.require_type(expr.args[0],'INTEGER')]
        if not reading: codes.append(self.require_type(expr.args[1],'INTEGER' if expr.value == 'SET_INT_REG' else 'REAL'))
        targets = expr.args[1:] if reading else expr.args[2:]
        specs = ('BOOLEAN','INTEGER','REAL','INTEGER') if reading else ('INTEGER',)
        for target, required in zip(targets,specs):
            base = target
            while base.kind in ('field','index'): base = base.args[0]
            if target.kind not in ('name','field','index') or base.kind not in ('name','using_ref') or base.value in self.visible_constants():
                self.error('E_OUTPUT_ARGUMENT','Numeric register outputs require storage rooted in a variable',target.token)
            if self.protection_root(base) in self.active_counters: self.error('E_FOR_COUNTER','Numeric register output cannot write an active FOR counter',target.token)
            if self.is_position_read_only_access(target): self.error('E_POSITION_READ_ONLY','Numeric register output is read-only',target.token)
            if self.is_value_only_subfield(target): self.error('E_CONFIG_OUTPUT','CONFIG/association subfields cannot be numeric register output aliases',target.token)
            code, spec = self.reference(target)
            if spec != (required,): self.error('E_TYPE',f'{expr.value} output requires exact {required} storage',target.token)
            codes.append(code)
        self.features.add(expr.value)
        self.register_uses.append(dict(procedure=expr.value,body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=expr.token.line,column=expr.token.column,operation='read' if reading else 'write',
                                       argument_order=['register_no','real_flag','int_value','real_value','status'] if reading else ['register_no','value','status'],
                                       arguments_evaluated_once=True,output_parameters=[2,3,4,5] if reading else [3]))
        return f'self._state.numeric_register({expr.value!r}, {", ".join(codes)}, line={expr.token.line})'

    def time_text_conversion(self, expr):
        if len(expr.args) != 2: self.error('E_ARGUMENTS', f'{expr.value} requires two arguments',expr.token)
        self.check_for_call(expr.token)
        parsing = expr.value == 'CNV_STR_TIME'
        source = self.require_type(expr.args[0], 'STRING' if parsing else 'INTEGER')
        destination = expr.args[1]
        base = destination
        while base.kind in ('field','index'): base = base.args[0]
        if destination.kind not in ('name','field','index') or base.kind not in ('name','using_ref') or base.value in self.visible_constants():
            self.error('E_OUTPUT_ARGUMENT','Time conversion output requires storage rooted in a variable',destination.token)
        if self.protection_root(base) in self.active_counters: self.error('E_FOR_COUNTER','Time conversion cannot write an active FOR counter',destination.token)
        if self.is_position_read_only_access(destination): self.error('E_POSITION_READ_ONLY','POSITION orientation cannot be a time conversion output',destination.token)
        if self.is_value_only_subfield(destination): self.error('E_CONFIG_OUTPUT','CONFIG/association subfields cannot be time conversion output aliases',destination.token)
        target, spec = self.reference(destination)
        expected = 'INTEGER' if parsing else 'STRING'
        if spec[0] != expected: self.error('E_TYPE',f'{expr.value} output requires {expected}',destination.token)
        self.features.add(expr.value)
        self.time_text_uses.append(dict(name=expr.value,body=self.current_routine.name if self.current_routine else self.program.name,
                                       line=expr.token.line,column=expr.token.column,argument_order=['source','target'],
                                       arguments_evaluated_once=True,output_type=expected))
        return f'_rt.time_text_conversion({expr.value!r}, {source}, {target}, line={expr.token.line})'

    def joint_conversion(self, expr):
        if len(expr.args) != 3:
            self.error('E_ARGUMENTS', f'{expr.value} requires exactly three arguments', expr.token)
        if self.mode == 'strict' and any(self.has_routine_call(argument) for argument in expr.args):
            self.error('E_EVALUATION_ORDER', 'Joint conversion arguments containing routine calls need order validation', expr.token)
        self.check_for_call(expr.token)
        for argument in expr.args:
            if argument.kind not in ('name', 'index', 'field') or self.root_name(argument) in self.visible_constants():
                self.error('E_JOINT_ARGUMENT', 'Joint conversions require bare variable/field/element arguments', argument.token)
        for output in expr.args[1:]:
            if self.protection_root(output) in self.active_counters:
                self.error('E_FOR_COUNTER', 'Joint conversion cannot write an active FOR counter', output.token)
            if self.is_position_read_only_access(output):
                self.error('E_POSITION_READ_ONLY', 'Joint conversion output is read-only', output.token)
            if self.is_value_only_subfield(output):
                self.error('E_CONFIG_OUTPUT', 'CONFIG/association subfields cannot be joint-conversion output aliases', output.token)
        source, source_type = self.expression(expr.args[0])
        if expr.value == 'CNV_REL_JPOS':
            target, target_type = self.reference(expr.args[1])
            array_type, joint_type = source_type, target_type
        else:
            target, target_type = self.expression(expr.args[1])
            array_type, joint_type = target_type, source_type
        if joint_type[0] != 'JOINTPOS': self.error('E_TYPE', 'Joint conversion requires JOINTPOS storage', expr.token)
        if (array_type[0] != 'ARRAY' or len(rt.array_dimensions(array_type)) != 1
                or rt.array_leaf_spec(array_type) != ('REAL',)):
            self.error('E_TYPE', 'Joint conversion requires one-dimensional ARRAY OF REAL', expr.token)
        status, status_type = self.reference(expr.args[2])
        if status_type != ('INTEGER',): self.error('E_TYPE', 'Joint conversion status requires exact INTEGER storage', expr.args[2].token)
        self.features.add(expr.value)
        self.joint_conversion_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                              line=expr.token.line, column=expr.token.column, procedure=expr.value,
                                              declared_axes=joint_type[1], output_parameters=[2,3],
                                              context='Explicit Program(joint_axes=...) required; declared width must match'))
        return f'self._state.joint_conversion({expr.value!r}, {source}, {target}, {status}, {expr.token.line})'

    def _check_unpos_output(self, argument):
        if self.protection_root(argument) in self.active_counters:
            self.error('E_FOR_COUNTER', 'UNPOS cannot write an active FOR counter', argument.token)
        if self.is_position_read_only_access(argument):
            self.error('E_POSITION_READ_ONLY', 'UNPOS output cannot be a read-only POSITION orientation field', argument.token)
        if self.is_value_only_subfield(argument):
            self.error('E_CONFIG_OUTPUT', 'CONFIG/association scalar subfields cannot be UNPOS outputs', argument.token)

    def unpos_procedure(self, expr):
        if self.mode=='pythonic':
            if len(expr.args) not in (8,11):
                self.error('E_ARGUMENTS','UNPOS requires a pose, six REAL outputs, CONFIG and optionally three REAL axis outputs',expr.token)
            return self.unpos_value_procedure(expr)
        if len(expr.args) != 8:
            self.error('E_ARGUMENTS', 'UNPOS requires XYZWPR input, six REAL outputs and one CONFIG output', expr.token)
        if self.mode == 'strict' and any(self.has_routine_call(argument) for argument in expr.args):
            self.error('E_EVALUATION_ORDER', 'UNPOS arguments containing routine calls need order validation', expr.token)
        self.check_for_call(expr.token)
        codes = []
        expected = [('XYZWPR',), *(('REAL',) for _ in range(6)), ('CONFIG',)]
        for index, (argument, required) in enumerate(zip(expr.args, expected)):
            if argument.kind not in ('name', 'index', 'field') or self.root_name(argument) in self.visible_constants():
                self.error('E_UNPOS_ARGUMENT', 'UNPOS requires bare variable/field/element references', argument.token)
            if index:
                self._check_unpos_output(argument)
            reference, actual = self.reference(argument)
            if actual != required:
                self.error('E_TYPE', f'UNPOS argument {index+1} requires exact {required[0]} storage', argument.token)
            codes.append(reference)
        self.features.add('UNPOS')
        self.features.add('multiple outputs by reference')
        self.unpos_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
                                    line=expr.token.line, column=expr.token.column, output_parameters=list(range(2,9)),
                                    overlap='All eight references checked disjoint at runtime before output writes'))
        return f'_rt.unpos({codes[0]}, [{", ".join(codes[1:])}], line={expr.token.line})'

    def unpos_value_procedure(self,expr):
        self.check_for_call(expr.token)
        source,spec=self.expression(expr.args[0])
        if spec not in (('XYZWPR',),('POSITION',),('XYZWPREXT',)) and spec[0]!='JOINTPOS':
            self.error('E_TYPE','UNPOS input requires a pose value or model-backed JOINTPOS',expr.args[0].token)
        normalized=('XYZWPREXT',) if spec[0]=='JOINTPOS' else spec
        if spec[0]=='JOINTPOS': source=self.geometry_operand(source,spec,expr.args[0].token,'UNPOS')
        with_axes=len(expr.args)==11
        axes_option=',with_axes=True' if with_axes else ''
        source=f'_rt.unpos_source({source},{normalized!r},{expr.token.line}{axes_option})'
        expected=[('REAL',)]*6+[('CONFIG',)]
        if with_axes:
            expected.extend([('REAL',)]*3)
        outputs=[]
        for argument,required in zip(expr.args[1:],expected):
            if argument.kind not in ('name','index','field') or self.root_name(argument) in self.visible_constants():
                self.error('E_UNPOS_ARGUMENT','UNPOS outputs require writable variable/field/element references',argument.token)
            self._check_unpos_output(argument)
            reference,actual=self.reference(argument)
            if actual!=required: self.error('E_TYPE',f'UNPOS output requires exact {required[0]} storage',argument.token)
            outputs.append(reference)
        self.features.update(('UNPOS','multiple outputs by reference','pose value extraction'))
        self.unpos_uses.append(dict(body=self.current_routine.name if self.current_routine else self.program.name,
            line=expr.token.line,column=expr.token.column,output_parameters=list(range(2,len(expr.args)+1)),
            source_type=spec,source_kind=expr.args[0].kind,source_snapshot=True,external_axis_outputs=with_axes,
            overlap='Outputs checked disjoint at runtime; captured source may also be output storage'))
        return f'_rt.unpos_value({source}, [{", ".join(outputs)}], line={expr.token.line})'
