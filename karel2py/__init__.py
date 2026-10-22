"""KAREL source conversion prototype; no robot connection is created."""

__version__ = "0.87.0"


def translate(source, *, filename="<input>", array_shapes=None, mode="pythonic", cooperative=False):
    """Return a Translation; raise TranslationError for unsupported source."""
    from .compiler import translate as compile_source
    return compile_source(source, filename=filename, array_shapes=array_shapes, mode=mode, cooperative=cooperative)


def translate_project(sources, *, array_shapes=None):
    """Translate a mapping of source filenames to text and expose explicit linkage."""
    from .project import translate_project as compile_project
    return compile_project(sources,array_shapes=array_shapes)


def load_project(directory, *, array_shapes=None):
    """Read and translate regular .kl sources from one explicitly selected directory."""
    from .project import load_project as read_project
    return read_project(directory,array_shapes=array_shapes)
