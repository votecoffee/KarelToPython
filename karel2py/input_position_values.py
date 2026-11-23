"""Detached, context-free position-register facts for input discovery."""
from . import runtime as rt
from .input_value_conversions import UNKNOWN, Value, convert_value_facts, detached_facts, materialized_value
from .teach import cartesian_value

POSITION_CLEARED = object()
POSITION_MODIFIED = object()
POSITION_GETTERS = {'GET_POS_REG': ('XYZWPREXT',), 'GET_JPOS_REG': ('JOINTPOS', 9)}
POSITION_SETTERS = {'SET_POS_REG', 'SET_EPOS_REG', 'SET_JPOS_REG'}
POSITION_SERVICES = POSITION_GETTERS.keys() | POSITION_SETTERS | {'POS_REG_TYPE', 'CLR_POS_REG'}



def merge_positions(catalogs, merge_values):
    """Retain common facts while distinguishing changes from untouched inputs."""
    merged = {}
    for key in set().union(*catalogs):
        values = [catalog.get(key) for catalog in catalogs]
        first = values[0]
        if all(value is first for value in values[1:]):
            merged[key] = first
        elif all(isinstance(value, Value) for value in values):
            merged[key] = merge_values(values)
        elif all(isinstance(value, Value) or value is POSITION_CLEARED or value is POSITION_MODIFIED
                 for value in values):
            merged[key] = POSITION_MODIFIED
        else:
            merged[key] = UNKNOWN
    return merged


def checked_position_facts(value):
    """Normal bank setters only publish after accepting a complete position."""
    facts = {key: Value(fact.constant, spec=fact.spec) for key, fact in (value.facts or {}).items()
             if fact.complete}
    return Value(spec=value.spec, facts=facts or None)


def position_register_result(target, value, *, tick):
    """Normalize a stored value the way the matching portable getter does."""
    if target == value.spec:
        return value
    if target == ['XYZWPREXT'] and value.spec == ['XYZWPR']:
        fields = dict(value.facts or {})
        for member in ('EXT1', 'EXT2', 'EXT3'):
            fields[(('field', member),)] = Value(0.0, spec=['REAL'])
        return Value(spec=target, facts=fields)
    return convert_value_facts(target, value, tick=tick)[0]


def teach_position_store_facts(kind, value, line, tick):
    if kind == 'JOINTPOS':
        return checked_position_facts(value)
    target = [kind]
    raw = materialized_value(value)
    if raw is not UNKNOWN:
        return detached_facts(cartesian_value(target[0], raw, line))
    if value.spec is None:
        return Value(spec=target)
    if target == ['XYZWPR'] and value.spec == ['XYZWPREXT']:
        external_axes = {(('field', name),) for name in ('EXT1', 'EXT2', 'EXT3')}
        fields = {key: fact for key, fact in (value.facts or {}).items() if key not in external_axes}
        return checked_position_facts(Value(spec=target, facts=fields))
    return checked_position_facts(position_register_result(target, value, tick=tick))
