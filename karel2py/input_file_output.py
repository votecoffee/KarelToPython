"""Plan checked memory FILE output without opening or writing a backend."""
from dataclasses import dataclass, field, replace

from .communications import message_address
from .extended import MemoryFiles
from .file_io import FileHandle
from .serial_io import serial_address


FileKey = str | tuple


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


_FRESH_HANDLE = _MemoryOutput('', '', False, False, 0, closed=True)


@dataclass(frozen=True)
class MemoryOutputs:
    """Keep descriptor lifetimes and byte sizes across synchronized task slices."""

    handles: dict[FileKey, _MemoryOutput] = field(default_factory=dict)
    sizes: dict[str, int] = field(default_factory=dict)

    def capture(self, alias, backend, binding, line):
        if alias in self.handles:
            return self
        return self.open(alias, backend, binding['name'], binding['mode'], line, binding.get('attributes'))

    def open(self, key, backend, name, mode, line, attributes=None):
        attrs = attributes or {}
        prior = self.handles.get(key, _FRESH_HANDLE)
        if (type(backend) is not MemoryFiles or not prior.closed or type(name) is not str or type(mode) is not str
                or any(output.name == name and not output.closed for output in self.handles.values())
                or name.upper().startswith(('PIP:', 'KB:', 'WD:'))
                or serial_address(name) or message_address(name)
                or attrs.get('pipe_wait') is not None or attrs.get('pipe_overflow') is not None
                or attrs.get('read_timeout_ms')):
            return None
        backend._check(name, b'')
        handle = FileHandle()
        handle.binary = attrs.get('binary', prior.binary)
        handle.reverse = attrs.get('reverse', prior.reverse)
        handle.xml = attrs.get('xml', False)
        mode, binary = backend._access_mode(handle, mode, line)
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
        return MemoryOutputs(self.handles | {key: output}, self.sizes | {name: size})

    def descriptor(self, key):
        return self.handles.get(key, _FRESH_HANDLE)

    def close(self, key):
        output = self.descriptor(key)
        if output.closed:
            return None
        return replace(self, handles=self.handles | {key: replace(output, closed=True)})

    def write(self, key, backend, size, line):
        output = self.descriptor(key)
        if output.closed:
            return None
        prior_size = self.sizes[output.name]
        start = backend._write_start(output, prior_size, size, line)
        end = start + size
        return MemoryOutputs(self.handles | {key: replace(output, position=end)},
                             self.sizes | {output.name: max(prior_size, end)})

    def query(self, key, name):
        # The modeled lifecycle and successful writes leave IO_STATUS at zero.
        if name == 'IO_STATUS':
            return 0
        output = self.descriptor(key)
        if output.closed:
            return None
        return output.position if name == 'GET_FILE_POS' else self.sizes[output.name] - output.position
