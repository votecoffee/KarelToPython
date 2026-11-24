"""Plan checked memory FILE transfers without opening or writing a backend."""
from dataclasses import dataclass, field, replace
import struct

from . import runtime as rt
from .communications import message_address
from .extended import MemoryFiles
from .file_io import FileHandle, binary_read_fields, set_file_attribute
from .serial_io import serial_address


FileKey = str | tuple
_MAX_IMAGE_BYTES = 64 * 1024
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
    append_ready: bool = False
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
class _MemoryImage:
    data: bytes | None
    depends_on_saved: bool


@dataclass(frozen=True)
class MemoryOutputs:
    """Keep descriptor lifetimes and bounded file images across synchronized slices."""

    handles: dict[FileKey, _MemoryOutput] = field(default_factory=dict)
    sizes: dict[str, int] = field(default_factory=dict)
    # An absent image uses the original saved bytes. A recorded image with
    # absent data has a proven size but exceeded the byte retention limit.
    images: dict[str, _MemoryImage] = field(default_factory=dict)

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
        initial = backend.files.get(name)
        created = size is None and initial is None
        if created and mode in ('R', 'UD'):
            return None
        if size is None:
            size = len(initial) if initial is not None else 0
        images = self.images
        if mode == 'W' or created:
            size = 0
            images = images | {name: _MemoryImage(b'', False)}
        position = size if mode in ('A', 'AP') else 0
        output = replace(prior, name=name, mode=mode, position=position, closed=False,
                         append_ready=False).with_attributes(handle)
        return MemoryOutputs(self.handles | {key: output}, self.sizes | {name: size}, images)

    def descriptor(self, key):
        return self.handles.get(key, _FRESH_HANDLE)

    def close(self, key):
        output = self.descriptor(key)
        if output.closed:
            return None
        return replace(self, handles=self.handles | {key: replace(output, closed=True)})

    def write(self, key, backend, pieces, line, *, tick):
        output = self.descriptor(key)
        if output.closed:
            return None
        payload = rt._FileWritePayload(pieces, line)
        name = output.name
        prior_size = self.sizes[name]
        start = backend._write_start(output, prior_size, payload.size, line)
        end = start + payload.size
        size = max(prior_size, end)
        images = self.images
        if payload.size:
            image = images.get(name)
            retained = sum(len(other.data) for path, other in images.items() if path != name and other.data is not None)
            before = backend.files.get(name) if image is None else image.data
            depends_on_saved = image is None or image.depends_on_saved
            data = None
            if retained + size <= _MAX_IMAGE_BYTES and before is not None and len(before) == prior_size:
                # Charge copies in chunks so larger output-only writes still
                # work when discovery retains only the byte count and cursor.
                tick((size + 255) // 256)
                buffer = bytearray(before)
                backend._store_bytes(buffer, start, payload.to_bytes(output.format_handle()))
                data = bytes(buffer)
            images = images | {name: _MemoryImage(data, depends_on_saved)}
        handle = replace(output, position=end, append_ready=output.append_ready or (output.mode == 'AP' and payload.size > 0))
        return MemoryOutputs(self.handles | {key: handle}, self.sizes | {name: size}, images)

    def read(self, key, backend, targets, formats, breaks, line, *, tick):
        """Validate a batch and retain its values, provenance, and cursor."""
        output = self.descriptor(key)
        if (type(backend) is not MemoryFiles or output.closed or output.mode in ('W', 'A')
                or output.mode == 'AP' and not output.append_ready or dict(output.attributes).get('xml')):
            return None
        image = self.images.get(output.name)
        data = backend.files.get(output.name) if image is None else image.data
        if data is None or len(data) != self.sizes[output.name]:
            return None
        rt._read_line_breaks(len(targets), breaks, line)
        start = output.position
        if output.binary:
            if breaks:
                return None
            fields = binary_read_fields(targets, formats, line)
            end = start + sum(width for width, _ in fields)
            if end > len(data):
                return None
            tick(end - start)
            values = []
            offset = start
            for width, code in fields:
                raw = data[offset:offset + width]
                offset += width
                if code and output.reverse:
                    code = '>' + code[1:]
                values.append(raw.decode('ascii') if code is None else struct.unpack(code, raw)[0])
        else:
            tick(len(data) - start)
            attributes = dict(output.attributes)
            reader = rt.TextInput(data[start:].decode('ascii'), terminator=attributes.get('eol'),
                                  field_mode=attributes.get('field', False))
            fields = [dict(type=target.spec[0], type_spec=target.spec, format_specifiers=controls)
                      for target, controls in zip(targets, formats)]
            values = reader(dict(targets=fields, line_breaks=breaks))
            end = start + reader.offset
        for target, value in zip(targets, values):
            rt._validate_read_value(target, value, line)
        values = rt._prepare_read_values(targets, values, line)
        checked = tuple(rt.checked(target.spec, value, line) for target, value in zip(targets, values))
        updated = replace(self, handles=self.handles | {key: replace(output, position=end)})
        return updated, checked, image is None or image.depends_on_saved

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
