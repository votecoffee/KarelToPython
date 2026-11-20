"""Emit the standalone CLI and its explicit offline runtime bindings."""
from .compiler_language import JOINT_PROCEDURES, REGISTER_PROCEDURES


class ProgramCLILowering:
    """Emit command-line options for the features used by the generated program."""

    def emit_program_cli(self):
        self.indent = 0
        self.line()
        self.line('if __name__ == "__main__":')
        self.indent = 1
        joints = bool(self.features & JOINT_PROCEDURES)
        registers = bool(self.features & REGISTER_PROCEDURES)
        comparison = 'operator >=<' in self.features
        read = 'read' in self.features
        service_context = self.features & {'extended services', 'ports', 'memory files'}
        if self.mode != 'pythonic' and not (joints or registers or comparison or read or service_context):
            self.line('print(Program().run())')
            return

        self._emit_cli_arguments(joints=joints, registers=registers, comparison=comparison, read=read)
        self._emit_cli_context()
        bindings = ['context=_context']
        if registers:
            self._emit_cli_registers()
            bindings.append('registers=_registers')
        if joints:
            bindings.append('joint_axes=_args.joint_axes')
        if comparison:
            self._emit_cli_tolerance()
            bindings.extend(('pose_tolerance=_pose_tolerance', 'external_tolerance=_args.external_axis_tolerances'))
        if read:
            self._emit_cli_read()
            bindings.append('read=_responses')
        self.line(f'_program = Program({", ".join(bindings)})')
        self.line('print(_program.run(max_steps=_args.max_steps))')
        self.line('if _args.state_out is not None:')
        self.indent += 1
        self.line('if _program._state.registers is not None: _context.numeric = _program._state.registers')
        self.line('_context.save(_args.state_out)')
        self.indent -= 1

    def _emit_cli_arguments(self, *, joints, registers, comparison, read):
        self.line('import argparse as _argparse')
        self.line('_parser = _argparse.ArgumentParser(description="Explicit offline execution context; no controller connection")')
        if joints:
            self.line('_parser.add_argument("--joint-axes", type=int, choices=range(1, 10), required=True)')
        if registers:
            self.line('_parser.add_argument("--registers", help="UTF-8 JSON numeric bank; defaults to the numeric bank in --context")')
        if comparison:
            self.line('_parser.add_argument("--location-tolerance-mm", type=float, required=True)')
            self.line('_parser.add_argument("--orientation-tolerance-deg", type=float, required=True)')
            self.line('_config = _parser.add_mutually_exclusive_group(required=True)')
            self.line('_config.add_argument("--check-config", dest="check_config", action="store_true")')
            self.line('_config.add_argument("--ignore-config", dest="check_config", action="store_false")')
        if read:
            self.line('_input = _parser.add_mutually_exclusive_group(required=False)')
            self.line('_input.add_argument("--read-values", help="UTF-8 JSON list of typed response batches, one per READ")')
            self.line('_input.add_argument("--read-text", help="UTF-8 ASCII text input for Pythonic READ")')
        self.line('_parser.add_argument("--context", help="Explicit offline service configuration JSON")')
        self.line('_rt.directory_files_options(_parser)')
        self.line('_parser.add_argument("--state-out", help="Save offline banks and global values as JSON")')
        self.line('_parser.add_argument("--max-steps", type=int, default=100000, help="Maximum execution steps")')
        if self.mode == 'pythonic':
            self.line('_parser.add_argument("--external-collections", help="UTF-8 JSON fixed logical values for explicitly named external collection functions")')
            self.line('_parser.add_argument("--external-values", help="UTF-8 JSON explicit data, procedures, argument cases and staged outputs for external routines")')
        if comparison:
            self.line('_parser.add_argument("--external-axis-tolerances", type=float, nargs=3, help="Explicit tolerances for EXT1, EXT2, EXT3")')
        self.line('_args = _parser.parse_args()')
        self.line('if _args.max_steps < 1: _parser.error("--max-steps must be positive")')
        self.line('_files = _rt.directory_files_from_args(_parser, _args)')

    def _emit_cli_context(self):
        self.line('import json as _json')
        self.line('_context = None')
        self.line('if _args.context is not None:')
        self.indent += 1
        self.line('try:')
        self.indent += 1
        if self.mode == 'pythonic':
            self.line('_context = _rt.ExecutionContext.load(_args.context)')
        else:
            self.line('with open(_args.context, encoding="utf-8-sig") as _stream: _context = _rt.ExecutionContext.from_config(_json.load(_stream))')
        self.indent -= 1
        self.line('except (OSError, KeyError, TypeError, ValueError, _rt.KarelRuntimeError) as _error:')
        self.indent += 1
        self.line('_parser.error("Invalid service context: "+str(_error))')
        self.indent -= 2
        if self.mode == 'pythonic':
            self.line('if _args.external_collections is not None or _args.external_values is not None:')
            self.indent += 1
            self.line('try:')
            self.indent += 1
            self.line('_bindings = _rt.load_external_bindings(values=_args.external_values, collections=_args.external_collections, outputs=(_args.state_out,))')
            self.line('if _context is None: _context = _rt.ExecutionContext()')
            self.line('_context.externals.update(_bindings)')
            self.indent -= 1
            self.line('except (OSError, ValueError, _rt.KarelRuntimeError) as _error:')
            self.indent += 1
            self.line('_parser.error(("Invalid external collections: " if _args.external_values is None else "Invalid external bindings: ")+str(_error))')
            self.indent -= 2
        self.line('if _files is not None or _args.state_out is not None:')
        self.indent += 1
        self.line('if _context is None: _context = _rt.ExecutionContext()')
        self.line('if _files is not None: _context.files = _files')
        self.indent -= 1

    def _emit_cli_registers(self):
        self.line('_registers = _context.numeric if _context is not None else None')
        self.line('if _args.registers is not None:')
        self.indent += 1
        self.line('try:')
        self.indent += 1
        self.line('with open(_args.registers, encoding="utf-8-sig") as _stream:')
        self.indent += 1
        self.line('_registers = _rt.NumericRegisters.from_config(_json.load(_stream))')
        self.indent -= 2
        self.line('except (OSError, TypeError, ValueError, _rt.KarelRuntimeError) as _error:')
        self.indent += 1
        self.line('_parser.error("Unable to load numeric registers: " + str(_error))')
        self.indent -= 2
        self.line('if _registers is None: _parser.error("Numeric register calls require --registers or --context with a numeric bank")')
        self.line('if _context is None: _context = _rt.ExecutionContext()')
        self.line('_context.numeric = _registers')

    def _emit_cli_tolerance(self):
        self.line('try:')
        self.indent += 1
        self.line('_pose_tolerance = _rt.checked_pose_tolerance((_args.location_tolerance_mm, _args.orientation_tolerance_deg, _args.check_config))')
        self.indent -= 1
        self.line('except ValueError as _error:')
        self.indent += 1
        self.line('_parser.error(str(_error))')
        self.indent -= 1

    def _emit_cli_read(self):
        self.line('_responses = None')
        self.line('if _args.read_values is not None or _args.read_text is not None:')
        self.indent += 1
        self.line('import json as _json')
        self.line('try:')
        self.indent += 1
        self.line('with open(_args.read_values if _args.read_values is not None else _args.read_text, encoding="utf-8-sig", newline="") as _stream:')
        self.indent += 1
        self.line('_responses = _json.load(_stream) if _args.read_values is not None else _rt.TextInput(_stream.read())')
        self.indent -= 2
        self.line('except (OSError, ValueError) as _error:')
        self.indent += 1
        self.line('_parser.error("Unable to load READ input: " + str(_error))')
        self.indent -= 1
        self.line('if _args.read_values is not None:')
        self.indent += 1
        self.line('if type(_responses) is not list: _parser.error("READ batches must be a JSON list")')
        self.line('_batches = iter(_responses)')
        self.line('_responses = lambda request: next(_batches)')
        self.indent -= 2
