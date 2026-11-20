"""Pin and replay a linked set of already generated Python modules."""
from dataclasses import dataclass
from functools import partial
from hashlib import sha256
import inspect
import os
from pathlib import Path
import re

from . import __version__, runtime as rt
from .runner import (MAX_BYTES, PROJECT_SCHEMA, RunDocumentError, _check_cancelled, _context, _decode,
                     _encode, _error, _inspect_python, _now, _read, _RunOutput, _run_status, _store)


MAX_MODULES = 64
MAX_PROJECT_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class ModulePin:
    program: str
    path: Path
    sha256: str


def _program_name(name):
    return type(name) is str and re.fullmatch(r'[A-Z_][A-Z_0-9]*', name) is not None


def _read_modules(paths):
    if not 1 <= len(paths) <= MAX_MODULES:
        raise RunDocumentError(f'Select 1 through {MAX_MODULES} cooperative Python modules.')
    modules = {}
    size = 0
    for name in paths:
        path = Path(name).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != '.py':
            raise RunDocumentError('Select regular .py files for the linked project.')
        raw = _read(path)
        size += len(raw)
        if size > MAX_PROJECT_BYTES:
            raise RunDocumentError('Linked Python modules exceed 32 MiB in total.')
        try:
            identity, code = _inspect_python(path, raw, cooperative=True)
        except RunDocumentError as error:
            raise RunDocumentError(f'{path}: {error}') from error
        program = identity['program']
        if program in modules:
            raise RunDocumentError(f'Duplicate linked program {program}.')
        modules[program] = (path, identity['sha256'], code)
    return modules


def _module_pins(modules):
    return tuple(ModulePin(program, path, sha256) for program, (path, sha256, _) in modules.items())


def inspect_project_modules(paths):
    """Read declared program names and pins in the selected order without executing code."""
    return _module_pins(_read_modules(tuple(paths)))


def _validate_limits(limits):
    keys = {'max_steps', 'max_cycles', 'max_output_chars'}
    if (type(limits) is not dict or set(limits) != keys or
            any(type(limits[key]) is not int or limits[key] < 1 for key in keys) or
            limits['max_output_chars'] > MAX_BYTES):
        raise RunDocumentError('Linked limits require positive max_steps, max_cycles and max_output_chars up to 16777216.')


def _project_target(paths, destination, entry, expected_modules):
    if type(entry) is not str or not entry.isascii() or not _program_name(entry.upper()):
        raise RunDocumentError('Choose a declared program name for the linked entry.')
    entry = entry.upper()
    modules = _read_modules(tuple(paths))
    pins = _module_pins(modules)
    if expected_modules is not None and pins != tuple(expected_modules):
        raise RunDocumentError('A linked Python module changed after review. Select the modules again.')
    if entry not in modules:
        raise RunDocumentError('The linked entry must be one of the selected modules.')
    rows = []
    for pin in pins:
        try:
            name = os.path.relpath(pin.path, destination.parent.resolve())
        except ValueError:
            name = str(pin.path)
        rows.append(dict(path=name, program=pin.program, sha256=pin.sha256))
    target = dict(program=entry, mode='pythonic', modules=rows)
    module_paths = tuple(pin.path for pin in pins)
    return target, module_paths


def create_project_document(paths, destination, *, entry, context=None, max_steps=100000, max_cycles=100000,
                            max_output_chars=1048576, protected=(), expected_modules=None, discover=False):
    """Inspect and pin each selected module without importing its code."""
    destination = Path(destination).absolute()
    limits = dict(max_steps=max_steps, max_cycles=max_cycles, max_output_chars=max_output_chars)
    _validate_limits(limits)
    target, module_paths = _project_target(paths, destination, entry, expected_modules)
    config = {} if context is None else _decode(_encode(context))
    _context(config)
    if type(discover) is not bool:
        raise RunDocumentError('discover must be BOOLEAN')
    inputs = dict(context=config)
    if discover:
        from .project_input_discovery import prepare_project_inputs

        inputs = prepare_project_inputs(target, module_paths, config)
        check_project_pin_bytes(destination, target)
    document = dict(schema=PROJECT_SCHEMA, target=target, limits=limits, inputs=inputs, results=None)
    _store(destination, document, protected=(*module_paths, *protected))
    return document


def validate_project_target(target):
    """Validate an entry and its ordered linked pins without reading files."""
    if (type(target) is not dict or set(target) != {'program', 'mode', 'modules'} or
            target['mode'] != 'pythonic' or not _program_name(target['program']) or
            type(target['modules']) is not list or not 1 <= len(target['modules']) <= MAX_MODULES):
        raise RunDocumentError('Malformed linked target identity.')
    rows = target['modules']
    names = set()
    for row in rows:
        if (type(row) is not dict or set(row) != {'path', 'program', 'sha256'} or
                type(row['path']) is not str or not row['path'] or '\0' in row['path'] or
                not _program_name(row['program']) or row['program'] in names or
                type(row['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', row['sha256'])):
            raise RunDocumentError('Malformed or duplicate linked module identity.')
        names.add(row['program'])
    if target['program'] not in names:
        raise RunDocumentError('The linked entry must be one of the pinned modules.')


def project_document_fields(document, *, inspect_only=False):
    """Validate the saved envelope without reading or executing its modules."""
    if (type(document) is not dict or set(document) != {'schema', 'target', 'limits', 'inputs', 'results'} or
            document['schema'] != PROJECT_SCHEMA):
        raise RunDocumentError('Expected a karel2py.project-run.v1 document.')
    target, inputs, results = document['target'], document['inputs'], document['results']
    validate_project_target(target)
    _validate_limits(document['limits'])
    if type(inputs) is not dict or set(inputs) not in ({'context'}, {'context', 'template'}):
        raise RunDocumentError('Linked run inputs require context and may include template annotations.')
    if 'template' in inputs:
        from .input_template import validate_annotations

        try:
            validate_annotations(inputs['template'], target)
        except ValueError as error:
            raise RunDocumentError(str(error)) from error
    if results is not None:
        if type(results) is not dict:
            raise RunDocumentError('results must be null or an object')
        if not inspect_only and results.get('status') == 'running':
            raise RunDocumentError('Previous run is running or interrupted; resolve it and reset results to null before retrying')
    return target, inputs


def verify_project_pins(path, target):
    """Read checked module bytes and verify their declared order and identity."""
    rows = target['modules']
    modules = _read_modules([path.parent / row['path'] for row in rows])
    if [(name, sha256) for name, (_, sha256, _) in modules.items()] != [(row['program'], row['sha256']) for row in rows]:
        raise RunDocumentError('A linked Python module changed. Create a new run document.')
    return modules


def check_project_pin_bytes(path, target):
    """Recheck the pinned source bytes before publishing prepared inputs."""
    for row in target['modules']:
        if sha256(_read(path.parent / row['path'])).hexdigest() != row['sha256']:
            raise RunDocumentError('A linked Python module changed during input preparation.')


def _preflight(path, document):
    target, inputs = project_document_fields(document)
    return verify_project_pins(path, target), _context(inputs['context'])


def _load_classes(modules):
    classes = {}
    for name, (path, _, code) in modules.items():
        namespace = {'__name__': '_karel2py_project_' + name, '__file__': str(path)}
        exec(code, namespace)
        program = namespace.get('Program')
        if (not isinstance(program, type) or getattr(program, 'source_program', None) != name or
                getattr(program, 'translation_mode', None) != 'pythonic' or
                not inspect.isgeneratorfunction(inspect.unwrap(getattr(program, '_execute', None)))):
            raise RunDocumentError(f'Loaded linked Program differs from inspected metadata: {name}')
        classes[name] = program
    return classes


def _capture_programs(scheduler, errors):
    programs = dict(scheduler.tasks)
    states = {name: program.task_state for name, program in programs.items()}
    for program in dict.fromkeys(programs.values()):
        program._state._run_cancel_check = None
        if getattr(program, '_execution', None) is not None:
            try:
                program.stop()
            except Exception as error:
                errors[f'cleanup:{program.source_program}'] = _error(error)
    results = {}
    for name, program in programs.items():
        try:
            values = program.snapshot()
        except Exception as error:
            values = None
            errors[f'variables:{name}'] = _error(error)
        results[name] = dict(state=states[name], values=values)
    return results


def run_project_document(path, document, original, *, cancel_event=None, protected=()):
    """Replay the inspected module snapshots with one fresh scheduler and context."""
    from .project import Project

    modules, context = _preflight(path, document)
    limits, entry = document['limits'], document['target']['program']
    paths = {name: row[0] for name, row in modules.items()}
    protected = (*paths.values(), *protected)
    started = _now()
    document['results'] = dict(status='running', runner_version=__version__, started_utc=started)
    pending = _store(path, document, expected=original, protected=protected)
    output = _RunOutput(limits['max_output_chars'])
    context.tasks = scheduler = rt.TaskScheduler(max_steps=limits['max_steps'])
    cancelled = partial(_check_cancelled, cancel_event)
    failure = None
    errors = {}
    status = 'completed'

    with rt._numeric_scope('pythonic'):
        try:
            cancelled()
            project = Project.from_generated(_load_classes(modules), paths)
            instance = project.instantiate(context=context, options={'write': output.write})
            if cancel_event is not None:
                for program in instance.programs.values():
                    program._state._run_cancel_check = cancelled
            scheduler.run(entry=entry, max_cycles=limits['max_cycles'],
                          check_cancelled=cancelled if cancel_event is not None else None)
            entry_state = instance.programs[entry].task_state
            if entry_state in ('stopped', 'aborted'):
                status = entry_state
            else:
                states = {program.task_state for program in scheduler.tasks.values()}
                if 'waiting' in states:
                    status = 'waiting'
                elif 'paused' in states:
                    status = 'paused'
        except BaseException as error:
            status, failure = _run_status(error), _error(error)
        programs = _capture_programs(scheduler, errors)
        try:
            state = context.to_config()
        except Exception as error:
            state = None
            errors['context'] = _error(error)
    document['results'] = dict(status=status, runner_version=__version__, started_utc=started, finished_utc=_now(),
                               programs=programs, context=state, text_output=output.text(), error=failure, capture_errors=errors)
    _store(path, document, expected=pending, protected=protected)
    return document
