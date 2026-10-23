"""Shared source protection and complete-file publication for CLI and GUI."""
import os
from pathlib import Path
import tempfile


def same_file(left, right):
    left, right = Path(left), Path(right)
    return left.resolve() == right.resolve() or (left.exists() and right.exists() and os.path.samefile(left, right))


def check_output(path, *, overwrite=False, protected=()):
    path = Path(path)
    if any(same_file(path, source) for source in protected):
        raise ValueError('Choose a different output file; KAREL source files are protected')
    if path.is_symlink(): raise ValueError('Choose a regular output file, not a symbolic link')
    if path.exists():
        if not path.is_file(): raise ValueError('Output must be a regular file')
        if not overwrite: raise FileExistsError(f'{path} exists; use --force to replace it')
    if not path.parent.is_dir(): raise FileNotFoundError(f'Output directory {path.parent} does not exist')


def write_bytes(path, data, *, overwrite=False, protected=()):
    """Protect source aliases and publish replacements only after a complete write."""
    path = Path(path)
    check_output(path, overwrite=overwrite, protected=protected)
    if not overwrite:
        with path.open('xb') as stream: stream.write(data)
        return
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream: stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
