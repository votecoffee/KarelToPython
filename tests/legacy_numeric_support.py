"""Preserve the pre-Pythonic conservative contract without publishing strict mode.

These tests exercise frozen numeric and WRITE guards for the future strict milestone.
Public API/CLI behavior is exercised separately through karel2py.translate.
"""
from karel2py import runtime
from karel2py.compiler import _translate


def translate(source, *, filename='<input>', array_shapes=None):
    with runtime._numeric_scope('strict'):
        return _translate(source, filename=filename, array_shapes=array_shapes)
