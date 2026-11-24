"""Plan wildcard changes to a saved memory FILE namespace without reading bytes."""

from fnmatch import fnmatchcase

from .fileops import (
    WILDCARD_COPY_BYTES, WILDCARD_FILE_LIMIT, _WildcardCaptureError, _file_name_separators,
    _wildcard_destination, _wildcard_parts, _wildcard_path_match, _wildcard_relative,
    _wildcard_source, _wildcard_target_prefix, _wildcard_target_root, _wildcard_template,
)


def _scope_names(names, folder, *, recursive, tick):
    for name in names:
        tick()
        if recursive:
            if _wildcard_relative(name, folder) is not None:
                _wildcard_parts(name, pattern=False)
                yield name
        else:
            try:
                parent, _ = _wildcard_parts(name, pattern=False)
            except ValueError:
                continue
            if parent.casefold() == folder.casefold():
                yield name


def _source_names(names, folder, pattern, *, tick):
    recursive = '/' in pattern
    selected = []
    for name in _scope_names(names, folder, recursive=recursive, tick=tick):
        if recursive:
            relative = _wildcard_relative(name, folder)
            matches = _wildcard_path_match(relative, pattern, check=tick)
        else:
            basename = name.rsplit('/', 1)[-1].rsplit(':', 1)[-1]
            matches = fnmatchcase(basename.casefold(), pattern.casefold())
        if matches:
            selected.append(name)
    return selected


def memory_wildcard_plan(operation, operands, namespace, busy, *, tick):
    """Return the portable status and a complete set of source/destination pairs."""
    try:
        return _plan(operation, operands, namespace, busy, tick=tick)
    except _WildcardCaptureError:
        return 2, ()
    except ValueError:
        return None


def _plan(operation, operands, namespace, busy, *, tick):
    folder, pattern = _wildcard_source(_file_name_separators(operands[0]))
    _wildcard_parts(folder + '__wildcard_probe__', pattern=False)
    deleting = operation == 'DELETE_FILE'
    copying = operation == 'COPY_FILE'
    filename_pattern = pattern.rsplit('/', 1)[-1]
    if not deleting:
        prefix, template = _wildcard_destination(_file_name_separators(operands[1]))
        destination_folder = _wildcard_target_root(prefix)
        _wildcard_parts(destination_folder + '__wildcard_probe__', pattern=False)
        if '?' in template and ('*' in filename_pattern or template.count('?') != filename_pattern.count('?')):
            return 2, ()
    if len(namespace) > WILDCARD_FILE_LIMIT:
        return None
    names = sorted(namespace)
    selected = _source_names(names, folder, pattern, tick=tick)
    if not selected:
        return 1, ()
    source_keys = {name.casefold() for name in selected}
    if len(source_keys) != len(selected):
        return 2, ()
    if source_keys & busy:
        return 3, ()
    if deleting:
        return 0, tuple((name, None) for name in selected)

    recursive = '*' in prefix or '?' in prefix
    aliases = {}
    for name in _scope_names(names, destination_folder, recursive=recursive, tick=tick):
        aliases.setdefault(name.casefold(), []).append(name)
    overwrite = copying and operands[2]
    destinations = set()
    changes = []
    total = 0
    for name in selected:
        tick()
        basename = name.rsplit('/', 1)[-1].rsplit(':', 1)[-1]
        try:
            target_base = _wildcard_template(template, basename, filename_pattern)
        except ValueError:
            return 2, ()
        target_prefix = _wildcard_target_prefix(prefix, name, folder, source_pattern=pattern, check=tick)
        target = target_prefix + target_base
        if recursive and _wildcard_relative(target, destination_folder) is None:
            return None
        _wildcard_parts(target, pattern=False)
        key = target.casefold()
        matches = aliases.get(key, ())
        if len(matches) > 1 or key in source_keys or key in destinations:
            return 2, ()
        if key in busy:
            return 3, ()
        if matches and not overwrite:
            return 2, ()
        destinations.add(key)
        if copying:
            total += namespace[name]
            if total > WILDCARD_COPY_BYTES:
                return None
        changes.append((name, matches[0] if matches else target))
    return 0, tuple(changes)
