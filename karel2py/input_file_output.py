"""Plan checked memory FILE output without opening or writing a backend."""
from dataclasses import dataclass, field, replace

from .communications import message_address
from .extended import MemoryFiles
from .file_io import FileHandle, set_file_attribute
from .serial_io import serial_address


FileKey = str | tuple
_FILE_ATTRIBUTES = ('eol', 'xml', 'field', 'passall', 'noecho', 'interactive',
                    'pipe_wait', 'pipe_overflow', 'read_timeout_ms')


@dataclass(frozen=True)
class _MemoryOutput:
    name: str
    mode: str
    binary: bool
    reverse: bool
    position: int
    closed: bool = False
    attributes: tuple[tuple[str, int | bool | None], ...] = ()

    def format_handle(self):
        handle = FileHandle()
        handle.binary, handle.reverse = self.binary, self.reverse
        for name, value in self.attributes:
            setattr(handle, name, value)
        return handle

    def with_attributes(self, handle):
        attributes = tuple((name, getattr(handle, name)) for name in _FILE_ATTRIBUTES)
        return replace(self, binary=handle.binary, reverse=handle.reverse, attributes=attributes)

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
        prior = self.descriptor(key)
        if (type(backend) is not MemoryFiles or not prior.closed or type(name) is not str or type(mode) is not str
                or any(output.name == name and not output.closed for output in self.handles.values())
                or name.upper().startswith(('PIP:', 'KB:', 'WD:'))
                or serial_address(name) or message_address(name)):
            return None
        handle = prior.format_handle()
        for attribute, value in (attributes or {}).items():
            setattr(handle, attribute, value)
        if handle.pipe_wait is not None or handle.pipe_overflow is not None or handle.read_timeout_ms:
            return None
        backend._check(name, b'')
        mode, handle.binary = backend._access_mode(handle, mode, line)
        size = self.sizes.get(name)
        if size is None:
            initial = backend.files.get(name)
            if initial is None and mode in ('R', 'UD'):
                return None
            size = len(initial) if initial is not None else 0
        if mode == 'W':
            size = 0
        position = size if mode in ('A', 'AP') else 0
        output = replace(prior, name=name, mode=mode, position=position, closed=False).with_attributes(handle)
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

    def set_attribute(self, key, attribute, value, line):
        output = self.descriptor(key)
        if not output.closed:
            return None
        handle = output.format_handle()
        set_file_attribute(handle, attribute, value, line=line)
        return replace(self, handles=self.handles | {key: output.with_attributes(handle)})

    def seek(self, key, requested):
        output = self.descriptor(key)
        if output.closed or dict(output.attributes).get('xml'):
            return None
        length = self.sizes[output.name]
        position = length if requested == -1 else requested
        if not 0 <= position <= length:
            return self, 2
        return replace(self, handles=self.handles | {key: replace(output, position=position)}), 0

    def query(self, key, name):
        # The modeled lifecycle and successful writes leave IO_STATUS at zero.
        if name == 'IO_STATUS':
            return 0
        output = self.descriptor(key)
        if output.closed:
            return None
        return output.position if name == 'GET_FILE_POS' else self.sizes[output.name] - output.position
