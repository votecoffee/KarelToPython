"""KAREL source conversion prototype; no robot connection is created."""

__version__ = "0.56.0"


def translate(source, *, filename="<input>", array_shapes=None, mode="pythonic"):
    """Return a Translation; raise TranslationError for unsupported source."""
    from .compiler import translate as compile_source
    return compile_source(source, filename=filename, array_shapes=array_shapes, mode=mode)
