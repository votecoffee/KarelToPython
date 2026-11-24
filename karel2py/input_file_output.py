"""Plan checked memory FILE output without opening or writing a backend."""
from dataclasses import dataclass, field, replace

from .communications import message_address
from .extended import MemoryFiles
from .file_io import FileHandle
from .serial_io import serial_address


@dataclass(frozen=True)
class _MemoryOutput:
    name: str
    mode: str
    binary: bool
    reverse: bool
    position: int
    closed: bool = False

    @property
    def appends_at_end(self):
        return self.mode in ('A', 'AP')


@dataclass(frozen=True)
class MemoryOutputs:
    """Keep alias lifetimes and byte sizes across synchronized task slices."""

    aliases: dict[str, _MemoryOutput] = field(default_factory=dict)
    sizes: dict[str, int] = field(default_factory=dict)

    def capture(self, alias, backend, binding, line):
        if alias in self.aliases:
            return self
        name = binding['name']
        attrs = binding.get('attributes', {})
        if (type(backend) is not MemoryFiles
                or any(output.name == name and not output.closed for output in self.aliases.values())
                or name.upper().startswith(('PIP:', 'KB:', 'WD:'))
                or serial_address(name) or message_address(name)
                or attrs.get('pipe_wait') is not None or attrs.get('pipe_overflow') is not None
                or attrs.get('read_timeout_ms')):
            return None
        handle = FileHandle()
        for attribute in ('binary', 'reverse', 'xml'):
            setattr(handle, attribute, attrs.get(attribute, False))
        mode, binary = backend._access_mode(handle, binding['mode'], line)
        size = self.sizes.get(name)
        if size is None:
            initial = backend.files.get(name)
            if initial is None and mode in ('R', 'UD'):
                return None
            size = len(initial) if initial is not None else 0
        if mode == 'W':
            size = 0
        position = size if mode in ('A', 'AP') else 0
        output = _MemoryOutput(name, mode, binary, handle.reverse, position)
        return MemoryOutputs(self.aliases | {alias: output}, self.sizes | {name: size})

    def close(self, alias):
        output = self.aliases[alias]
        if output.closed:
            return None
        return replace(self, aliases=self.aliases | {alias: replace(output, closed=True)})

    def write(self, alias, backend, size, line):
        output = self.aliases[alias]
        if output.closed:
            return None
        prior_size = self.sizes[output.name]
        start = backend._write_start(output, prior_size, size, line)
        end = start + size
        return MemoryOutputs(self.aliases | {alias: replace(output, position=end)},
                             self.sizes | {output.name: max(prior_size, end)})
