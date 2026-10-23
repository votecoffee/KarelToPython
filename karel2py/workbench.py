"""Headless operations for the desktop workbench; no source execution or GUI imports."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from . import __version__, translate
from .__main__ import array_shape_option
from .lexer import TranslationError
from .fileio import same_file, write_bytes


MAX_SOURCE_BYTES = 4 * 1024 * 1024


@dataclass
class Document:
    text: str = ''
    path: Path | None = None
    saved_text: str = ''
    original_bytes: bytes | None = None
    newline: str = '\n'
    bom: bool = False

    @property
    def dirty(self):
        return self.text != self.saved_text

    @classmethod
    def open(cls, path):
        path = Path(path).resolve(strict=True)
        if not path.is_file(): raise ValueError('Select a regular KAREL source file')
        if path.stat().st_size > MAX_SOURCE_BYTES: raise ValueError('GUI source files must be at most 4 MiB')
        with path.open('rb') as stream: data = stream.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES: raise ValueError('GUI source files must be at most 4 MiB')
        source = data.decode('utf-8-sig')
        newline = '\r\n' if '\r\n' in source and '\n' not in source.replace('\r\n', '') and '\r' not in source.replace('\r\n', '') else '\r' if '\r' in source and '\n' not in source else '\n'
        source = source.replace('\r\n', '\n').replace('\r', '\n')
        return cls(source, path, source, data, newline, data.startswith(b'\xef\xbb\xbf'))

    def save(self, path, *, overwrite=False):
        path = Path(path).absolute()
        same = self.path is not None and same_file(path, self.path)
        if same:
            if (not path.is_file() or self.original_bytes is None or path.stat().st_size != len(self.original_bytes)
                    or path.read_bytes() != self.original_bytes):
                raise ValueError('Source changed on disk; reopen it or save to a different file')
            if not self.dirty: return
        data = self.text.replace('\n', self.newline).encode('utf-8')
        if self.bom: data = b'\xef\xbb\xbf' + data
        if len(data) > MAX_SOURCE_BYTES: raise ValueError('GUI source files must be at most 4 MiB')
        write_bytes(path, data, overwrite=overwrite)
        self.path = path.resolve()
        self.saved_text, self.original_bytes = self.text, data


@dataclass
class Analysis:
    report: dict
    python_source: str | None = None
    protected: tuple = ()

    @property
    def accepted(self):
        return self.report['status'] == 'translated'

    @property
    def diagnostics(self):
        return self.report.get('diagnostics', [])

    def report_text(self):
        return json.dumps(self.report, indent=2, ensure_ascii=True) + '\n'

    def export(self, path, kind, *, overwrite=False):
        if kind == 'python':
            if self.python_source is None: raise ValueError('Translate a source before saving generated Python')
            text = self.python_source
        elif kind == 'report': text = self.report_text()
        else: raise ValueError('Unknown export kind')
        write_bytes(path, text.encode('utf-8'), overwrite=overwrite, protected=self.protected)


def parse_shapes(text):
    result = {}
    for item in text.split(';'):
        if not item.strip(): continue
        name, shape = array_shape_option(item.strip())
        if name in result: raise ValueError('Duplicate case-insensitive ARRAY name: ' + name)
        result[name] = shape
    return result


def analyze_source(text, *, filename='<untitled>', shapes='', cooperative=False, emit=True):
    if len(text.encode('utf-8')) > MAX_SOURCE_BYTES: raise ValueError('GUI source files must be at most 4 MiB')
    arrays = parse_shapes(shapes)
    protected = () if filename == '<untitled>' else (Path(filename),)
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    try:
        result = translate(text, filename=str(filename), array_shapes=arrays, cooperative=cooperative)
    except TranslationError as exc:
        report = dict(status='rejected', translator_version=__version__, source_text_sha256=digest,
                      diagnostics=[exc.as_dict()], translation_context=dict(mode='pythonic', array_shapes={key: list(shape) for key, shape in arrays.items()}))
        return Analysis(report, protected=protected)
    result.report['source_text_sha256'] = digest
    return Analysis(result.report, result.python_source if emit else None, protected)


def analyze_project(directory, *, shapes=''):
    from .project import load_project
    arrays = parse_shapes(shapes)
    root = Path(directory).resolve(strict=True)
    protected = tuple(path for path in root.iterdir() if path.suffix.lower() == '.kl')
    try:
        project = load_project(root, array_shapes=arrays)
        project.instantiate()  # Check linkage and construction; never run program bodies.
    except TranslationError as exc:
        diagnostic = exc.as_dict()
        diagnostic['file'] = str(root / exc.filename)
        return Analysis(dict(status='rejected', translator_version=__version__, project_directory=str(root), diagnostics=[diagnostic]), protected=protected)
    except ValueError as exc:
        diagnostic = dict(code='E_PROJECT_LINK', message=str(exc), file=str(root), line=0, column=0)
        return Analysis(dict(status='rejected', translator_version=__version__, project_directory=str(root), diagnostics=[diagnostic]), protected=protected)
    reports = {name: translation.report for name, translation in project.translations.items()}
    return Analysis(dict(status='translated', translator_version=__version__, project_directory=str(root),
                         linked=True, programs=reports, diagnostics=[]), protected=protected)
