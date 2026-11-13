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
