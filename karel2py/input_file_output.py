"""Plan checked memory FILE transfers without opening or writing a backend."""
from dataclasses import dataclass, field, replace
import struct

from . import runtime as rt
from .communications import message_address
from .extended import MemoryFiles
from .file_io import FileHandle, binary_read_fields, set_file_attribute
from .input_file_patterns import memory_wildcard_plan
from .serial_io import serial_address


FileKey = str | tuple
_MAX_IMAGE_BYTES = 64 * 1024
_MAX_IMAGE_SPANS = 256
_FILE_ATTRIBUTES = ('eol', 'xml', 'field', 'passall', 'noecho', 'interactive',
                    'pipe_wait', 'pipe_overflow', 'read_timeout_ms')


def _memory_name(name):
    return (type(name) is str and not name.upper().startswith(('PIP:', 'KB:', 'WD:'))
            and not serial_address(name) and not message_address(name))


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
class _ByteSpan:
    start: int
    end: int
    data: bytes | None

    def clip(self, start, end, *, tick):
        if self.start == start and self.end == end:
            return self
        data = self.data
        if data is not None:
            tick((end - start + 255) // 256)
            data = data[start - self.start:end - self.start]
        return _ByteSpan(start, end, data)

    def join(self, following, *, tick):
        if self.end != following.start or (self.data is None) != (following.data is None):
            return None
        data = None
        if self.data is not None:
            tick((following.end - self.start + 255) // 256)
            data = self.data + following.data
        return _ByteSpan(self.start, following.end, data)


@dataclass(frozen=True)
class _MemoryImage:
    saved_name: str | None = None
    saved_size: int | None = None
    spans: tuple[_ByteSpan, ...] = ()
    saved_available: bool = True

    @property
    def retained_bytes(self):
        return sum(len(span.data) for span in self.spans if span.data is not None)

    def overwrite(self, start, payload, handle, byte_budget, span_budget, *, tick):
        end = start + payload.size
        before, after = [], []
        for span in self.spans:
            if span.start < start:
                before.append(span.clip(span.start, min(span.end, start), tick=tick))
            if span.end > end:
                after.append(span.clip(max(span.start, end), span.end, tick=tick))
        retained = sum(len(span.data) for span in (*before, *after) if span.data is not None)
        data = None
        if retained + payload.size <= byte_budget and span_budget:
            tick((payload.size + 255) // 256)
            data = payload.to_bytes(handle)
        current = _ByteSpan(start, end, data)
        if before and (joined := before[-1].join(current, tick=tick)) is not None:
            before.pop()
            current = joined
        if after and (joined := current.join(after[0], tick=tick)) is not None:
            after.pop(0)
            current = joined
        spans = (*before, current, *after)
        if len(spans) > span_budget:
            # A discarded range can have overwritten saved bytes. Drop the saved
            # fallback for this file so those original bytes cannot resurface.
            recent = (_ByteSpan(start, end, data),) if data is not None and span_budget else ()
            return replace(self, spans=recent, saved_available=False)
        return replace(self, spans=spans)

    def read_range(self, saved, start, end, *, tick):
        if start == end:
            return b""
        length = end - start
        if not self.saved_available or saved is None or len(saved) != self.saved_size:
            saved = None
        tick(len(self.spans))
        chunks = []
        for span in self.spans:
            if span.end <= start:
                continue
            if span.start >= end:
                break
            if span.start > start:
                if saved is None or span.start > len(saved):
                    return None
                chunks.append(memoryview(saved)[start:span.start])
                start = span.start
            if span.data is None:
                return None
            stop = min(end, span.end)
            chunks.append(memoryview(span.data)[start - span.start:stop - span.start])
            start = stop
        if start < end:
            if saved is None or end > len(saved):
                return None
            chunks.append(memoryview(saved)[start:end])
        tick(length)
        return b"".join(chunks)


@dataclass(frozen=True)
class MemoryOutputs:
    """Keep descriptor lifetimes and bounded file images across synchronized slices."""

    handles: dict[FileKey, _MemoryOutput] = field(default_factory=dict)
    sizes: dict[str, int | None] = field(default_factory=dict)  # None masks a deleted saved name.
    # Unchanged offsets can use the saved bytes. An explicit span with no
    # payload shadows those bytes when a write exceeds the retention budget.
    images: dict[str, _MemoryImage] = field(default_factory=dict)

    def capture(self, alias, backend, binding, line):
        if alias in self.handles:
            return self
        return self.open(alias, backend, binding['name'], binding['mode'], line, binding.get('attributes'))

    def open(self, key, backend, name, mode, line, attributes=None):
        prior = self.descriptor(key)
        if (type(backend) is not MemoryFiles or not prior.closed or not _memory_name(name)
                or type(mode) is not str or self.busy(name)):
            return None
        handle = prior.format_handle()
        for attribute, value in (attributes or {}).items():
            setattr(handle, attribute, value)
        if handle.pipe_wait is not None or handle.pipe_overflow is not None or handle.read_timeout_ms:
            return None
        backend._check(name, b'')
        mode, handle.binary = backend._access_mode(handle, mode, line)
        size = self.size_of(backend, name)
        if size is None and mode in ('R', 'UD'):
            return None
        images = self.images
        if mode == 'W' or size is None:
            size = 0
            images = images | {name: _MemoryImage()}
        elif name not in images:
            images = images | {name: _MemoryImage(saved_name=name, saved_size=size)}
        position = size if mode in ('A', 'AP') else 0
        output = replace(prior, name=name, mode=mode, position=position, closed=False,
                         append_ready=False).with_attributes(handle)
        return MemoryOutputs(self.handles | {key: output}, self.sizes | {name: size}, images)

    def size_of(self, backend, name):
        if name in self.sizes:
            return self.sizes[name]
        initial = backend.files.get(name)
        return len(initial) if initial is not None else None

    def busy(self, name):
        return any(output.name == name and not output.closed for output in self.handles.values())

    def image_budget(self, name, *, tick):
        others = [image for path, image in self.images.items() if path != name]
        used_spans = sum(len(image.spans) for image in others)
        tick(used_spans)
        used_bytes = sum(image.retained_bytes for image in others)
        return _MAX_IMAGE_BYTES - used_bytes, _MAX_IMAGE_SPANS - used_spans

    def manage(self, backend, operation, operands, *, tick):
        if type(backend) is not MemoryFiles:
            return None
        deleting = operation == 'DELETE_FILE'
        copying = operation == 'COPY_FILE'
        names = operands[:1] if deleting else operands[:2]
        flags = operands[len(names):]
        if any(not _memory_name(name) for name in names) or any(type(flag) is not bool for flag in flags):
            return None
        if any('*' in name or '?' in name for name in names):
            return self.manage_wildcard(backend, operation, operands, tick=tick)
        source = names[0]
        if not deleting:
            target = names[1]
            if copying:
                backend._check(source, b'')
            backend._check(target, b'')
        if any(self.busy(name) for name in names):
            return self, 3, ()
        source_size = self.size_of(backend, source)
        if source_size is None:
            return self, 1, ()

        dependencies = self.saved_dependencies(backend, names)
        if not deleting and self.size_of(backend, target) is not None and not (copying and flags[0]):
            return self, 2, dependencies
        changes = ((source, None if deleting else target),)
        updated = self.apply_file_changes(backend, changes, copying=copying, tick=tick)
        return updated, 0, dependencies

    def manage_wildcard(self, backend, operation, operands, *, tick):
        tick(len(backend.files) + len(self.sizes) + len(self.handles))
        namespace = {name: len(data) for name, data in backend.files.items()}
        namespace.update(self.sizes)
        namespace = {name: size for name, size in namespace.items() if size is not None}
        busy = {handle.name.casefold() for handle in self.handles.values() if not handle.closed}
        plan = memory_wildcard_plan(operation, operands, namespace, busy, tick=tick)
        if plan is None:
            return None
        status, changes = plan
        # A wildcard status depends on the entire namespace, even with no matches.
        if status:
            return self, status, (None,)
        names = (name for change in changes for name in change if name is not None)
        dependencies = (None, *self.saved_dependencies(backend, names))
        updated = self.apply_file_changes(backend, changes, copying=operation == 'COPY_FILE', tick=tick)
        return updated, 0, dependencies

    def saved_dependencies(self, backend, names):
        # A copy or rename keeps the original saved input address.
        dependencies = set()
        for name in names:
            image = self.images.get(name)
            if image is not None:
                origin = image.saved_name
            else:
                origin = name if name not in self.sizes and name in backend.files else None
            if origin is not None:
                dependencies.add(origin)
        return tuple(sorted(dependencies))

    def apply_file_changes(self, backend, changes, *, copying, tick):
        sizes, images = self.sizes.copy(), self.images.copy()
        if copying:
            byte_budget, span_budget = self.image_budget(None, tick=tick)
        for source, target in changes:
            tick()
            if target is not None:
                source_size = self.size_of(backend, source)
                image = self.images.get(source)
                if image is None:
                    image = _MemoryImage(saved_name=source, saved_size=source_size)
                if copying:
                    previous = images.get(target)
                    if previous is not None:
                        byte_budget += previous.retained_bytes
                        span_budget += len(previous.spans)
                    tick(len(image.spans))
                    retained_bytes = image.retained_bytes
                    if retained_bytes <= byte_budget and len(image.spans) <= span_budget:
                        byte_budget -= retained_bytes
                        span_budget -= len(image.spans)
                    else:
                        image = replace(image, spans=(), saved_available=False)
                images[target] = image
                sizes[target] = source_size
            if not copying:
                sizes[source] = None
                images.pop(source, None)
        return replace(self, sizes=sizes, images=images)

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
            image = images[name]
            byte_budget, span_budget = self.image_budget(name, tick=tick)
            tick(len(image.spans))
            modified = image.overwrite(start, payload, output.format_handle(), byte_budget, span_budget, tick=tick)
            images = images | {name: modified}
        handle = replace(output, position=end, append_ready=output.append_ready or (output.mode == 'AP' and payload.size > 0))
        return MemoryOutputs(self.handles | {key: handle}, self.sizes | {name: size}, images)

    def read(self, key, backend, targets, formats, breaks, line, *, tick):
        """Validate a batch and retain its values, provenance, and cursor."""
        output = self.descriptor(key)
        if (type(backend) is not MemoryFiles or output.closed or output.mode in ('W', 'A')
                or output.mode == 'AP' and not output.append_ready or dict(output.attributes).get('xml')):
            return None
        image = self.images[output.name]
        saved = backend.files.get(image.saved_name)
        size = self.sizes[output.name]
        rt._read_line_breaks(len(targets), breaks, line)
        start = output.position
        if output.binary:
            if breaks:
                return None
            fields = binary_read_fields(targets, formats, line)
            end = start + sum(width for width, _ in fields)
            if end > size:
                return None
            data = image.read_range(saved, start, end, tick=tick)
            if data is None:
                return None
            values = []
            offset = 0
            for width, code in fields:
                raw = data[offset:offset + width]
                offset += width
                if code and output.reverse:
                    code = '>' + code[1:]
                values.append(raw.decode('ascii') if code is None else struct.unpack(code, raw)[0])
        else:
            data = image.read_range(saved, start, size, tick=tick)
            if data is None:
                return None
            attributes = dict(output.attributes)
            reader = rt.TextInput(data.decode('ascii'), terminator=attributes.get('eol'),
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
        # A saved file can also determine where an append or an end-relative
        # seek lands. Keep values from those seeded files editable.
        return updated, checked, image.saved_name

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
