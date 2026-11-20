"""Migrate bounded PATH roots for both input discovery and saved-run refresh."""

from dataclasses import dataclass

from . import runtime as rt
from .input_template import _missing
from .storage import collection_array_cost, collection_data_spec


@dataclass
class _MigratedPath:
    value: object
    preserved_leaves: int
    missing_leaves: int


def _compatible_path(before, after):
    """Require matching ARRAY boundaries, exact nodes and an unchanged or additive header."""
    while before[0] == after[0] == 'ARRAY':
        if len(rt.array_shape(before)) != len(rt.array_shape(after)):
            return False
        if rt.array_identity(before) != rt.array_identity(after):
            return False
        before, after = before[2], after[2]

    if before[0] != 'PATH' or after[0] != 'PATH' or before[1] != after[1]:
        return False
    old_header, new_header = before[2], after[2]
    if old_header is None or old_header == new_header:
        return True
    if new_header is None or old_header[:2] != new_header[:2]:
        return False
    new_fields = dict(new_header[2])
    return all(new_fields.get(name) == spec for name, spec in old_header[2])


def _supplied_leaves(value):
    if type(value) is dict:
        if value in ({'uninitialized': True}, {'unknown_byte': True}):
            return 0
        return sum(_supplied_leaves(item) for item in value.values())
    if type(value) is list:
        return sum(_supplied_leaves(item) for item in value)
    return int(value is not None)


def _resize_path(reference, spec):
    """Build a canonical, independent value without inventing records or values."""
    if not _compatible_path(reference.spec, spec):
        return None
    if spec[0] == 'ARRAY':
        collection_array_cost(spec)
    _, node, header = rt.array_leaf_spec(spec)
    old_header = rt.array_leaf_spec(reference.spec)[2]
    if header is not None:
        collection_data_spec(header)
    if node is not None:
        collection_data_spec(node)
    node_width = rt.scalar_leaf_count(node or rt.PREDEFINED_STRUCTURES['STD_PTH_NODE'])
    header_width = rt.scalar_leaf_count(header) if header is not None else 0
    dims = rt.array_dimensions(spec)
    descriptors = fields = 0

    def build(level, old):
        nonlocal descriptors, fields
        if level < len(dims):
            return [build(level + 1, old[index] if old is not None and index < len(old) else None)
                    for index in range(dims[level])]

        nodes = old['nodes'] if old is not None else []
        fields += len(nodes) * node_width + header_width
        descriptors += 1
        if fields + descriptors > 32767:
            raise ValueError('Refreshed PATH storage exceeds 32767 units')
        if header == old_header and old is not None:
            data = old['data']
        else:
            data = _missing(header) if header is not None else None
            if data is not None and old is not None and old['data'] is not None:
                data.update({name: value for name, value in old['data'].items() if name in data})
        return {'nodes': nodes, 'data': data}

    payload = build(0, rt.snapshot_value(reference.raw()))
    supplied = _supplied_leaves(payload)
    return _MigratedPath(payload, supplied, fields - supplied)


def path_migrator():
    """Share the exact same migrated values between analysis and publication."""
    cache = {}

    def migrate(key, reference, spec):
        cache_key = key, spec
        if cache_key not in cache:
            try:
                cache[cache_key] = _resize_path(reference, spec)
            except (ValueError, rt.KarelRuntimeError):
                cache[cache_key] = None
        return cache[cache_key]

    return migrate
