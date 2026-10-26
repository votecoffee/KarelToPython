"""KAREL source conversion prototype; no robot connection is created."""

# Fixed UTC release timestamp: YY.MMDD.HHmmss. Never derive it at import time.
__version__ = "26.1026.185812"


def translate(source, *, filename="<input>", array_shapes=None, mode="pythonic", cooperative=False, includes=None):
    """Return a Translation; raise TranslationError for unsupported source."""
    from .compiler import translate as compile_source
    return compile_source(source, filename=filename, array_shapes=array_shapes, mode=mode, cooperative=cooperative, includes=includes)


def translate_project(sources, *, array_shapes=None, includes=None):
    """Translate a mapping of source filenames to text and expose explicit linkage."""
    from .project import translate_project as compile_project
    return compile_project(sources,array_shapes=array_shapes,includes=includes)


def load_project(directory, *, array_shapes=None, include_dirs=(), include_devices=None):
    """Read and translate regular .kl sources from one explicitly selected directory."""
    from .project import load_project as read_project
    return read_project(directory,array_shapes=array_shapes,include_dirs=include_dirs,include_devices=include_devices)
