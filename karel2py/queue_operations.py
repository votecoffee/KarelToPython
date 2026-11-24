"""Plan queue content changes before the caller publishes to storage."""

QUEUE_EDIT_INPUTS = {
    'APPEND_QUEUE': 1,
    'INSERT_QUEUE': 2,
    'MODIFY_QUEUE': 2,
    'DELETE_QUEUE': 1,
    'GET_QUEUE': 0,
}


def _entry_index(entries, entry_id):
    return next((index for index, (number, _) in enumerate(entries) if number == entry_id), None)


def plan_queue_edit(name, snapshot, sequence, capacity, inputs, line=None):
    """Return entries, sequence, and writes relative to the output arguments."""
    from . import runtime as rt

    entries = list(snapshot)
    outputs = []
    status = 0
    if name in ('APPEND_QUEUE', 'INSERT_QUEUE'):
        if len(entries) >= capacity:
            status = 2
        else:
            index = len(entries) if name == 'APPEND_QUEUE' else _entry_index(entries, inputs[1])
            if index is None:
                status = 1
            else:
                sequence = rt.checked(('INTEGER',), sequence + 1, line)
                entries.insert(index, (sequence, rt.integer(inputs[0], line)))
                if name == 'APPEND_QUEUE':
                    outputs.append((0, sequence))
    elif name == 'GET_QUEUE':
        if entries:
            entry_id, value = entries.pop(0)
            outputs.extend(((0, value), (1, entry_id)))
        else:
            status = 61002
    else:
        entry_id = inputs[0] if name == 'DELETE_QUEUE' else inputs[1]
        index = _entry_index(entries, entry_id)
        if index is None:
            status = 1
        elif name == 'DELETE_QUEUE':
            del entries[index]
        else:
            entries[index] = (entry_id, rt.integer(inputs[0], line))
    outputs.append((-1, status))
    return tuple(entries), sequence, outputs


def plan_queue_copy(entries, entry_id, skip, capacity):
    """Return the prefix to write and the status for a validated copy request."""
    first = 0 if entry_id == 0 else _entry_index(entries, entry_id)
    if first is None:
        return (), 1
    start = first + skip
    return tuple(value for _, value in entries[start:start + capacity]), 0
