"""Captured ordinary reference locations for cooperative publication checks."""


def capture_location(reference):
    return type(reference),reference.spec,reference.storage,reference.key


def same_location(reference,location):
    kind,spec,storage,key=location
    try:
        return (type(reference) is kind and reference.spec==spec and reference.storage is storage
                and type(reference.key) is type(key) and reference.key==key
                and (type(storage) is dict and key in storage
                     or type(storage) is list and type(key) is int and 0<=key<len(storage)))
    except (AttributeError,TypeError,KeyError,IndexError):return False


def capture_model_value(reference,line=None):
    """Hold bounded INTEGER/pose/joint data, containers and original addresses."""
    from . import runtime as rt
    if (type(reference.spec) is not tuple or not reference.spec
            or reference.spec[0] not in ('INTEGER','POSITION','XYZWPR','XYZWPREXT','JOINTPOS')):
        raise rt.KarelRuntimeError('Model publication requires INTEGER, pose or joint data',line)
    raw=reference.raw();copy=rt._aggregate_value(reference.spec,raw,line,allow_partial=True)
    held=[];cells=rt._reference_cells(reference)
    def containers(value):
        if type(value) in (rt.Structure,rt.JointPosition):
            held.extend((value,value.values))
            if type(value) is rt.Structure:
                for member in value.values.values():containers(member)
            else:cells.update((id(value.values),index) for index in range(len(value.values)))
    containers(raw)
    return raw,rt.snapshot_value(copy),cells,tuple(held)


def same_model_value(reference,captured,line=None):
    original,snapshot,cells,held=captured
    current,values,locations,objects=capture_model_value(reference,line)
    return (current is original and values==snapshot and locations==cells
            and len(objects)==len(held) and all(a is b for a,b in zip(objects,held)))
