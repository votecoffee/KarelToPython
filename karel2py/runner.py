"""Explicit Pythonic runs with separate saved inputs and results."""
import argparse
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

from . import __version__, runtime as rt
from .fileio import check_output
from .storage import atomic_bytes, tuple_spec


SCHEMA = 'karel2py.run.v1'
PROJECT_SCHEMA = 'karel2py.project-run.v1'
MAX_BYTES = 16 * 1024 * 1024


class RunDocumentError(ValueError):
    """Preflight or publication failed; selected code was not retried."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RunDocumentError('Duplicate run JSON key: ' + key)
        result[key] = value
    return result


def _finite(text):
    value = float(text)
    if not math.isfinite(value):
        raise RunDocumentError('Nonfinite run JSON number')
    return value


def _decode(raw):
    if len(raw) > MAX_BYTES:
        raise RunDocumentError('Run JSON exceeds 16 MiB')
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique,
                          parse_float=_finite, parse_constant=_finite)
    except (UnicodeError, RecursionError, ValueError) as error:
        raise RunDocumentError('Invalid run JSON: ' + str(error)) from error


def _read(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise RunDocumentError('Run input exceeds 16 MiB')
    return raw


def _encode(value):
    try:
        raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise RunDocumentError('Run result cannot be encoded: ' + str(error)) from error
    if len(raw) > MAX_BYTES:
        raise RunDocumentError('Run result exceeds 16 MiB; previous document preserved')
    return raw


def _target(path):
    path = Path(path).resolve(strict=True)
    raw = _read(path)
    identity, code = _inspect_python(path, raw)
    return path, identity, code


def _inspect_python(path, raw, *, cooperative=False):
    try:
        source = raw.decode('utf-8-sig')
        tree = ast.parse(source, filename=str(path), feature_version=(3, 11))
        code = compile(tree, str(path), 'exec')
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Program']
        if len(classes) != 1:
            raise ValueError('One generated Program class is required')
        metadata = {}
        for node in classes[0].body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in ('source_program', 'translation_mode'):
                    if name in metadata:
                        raise ValueError('Duplicate generated Program identity')
                    metadata[name] = ast.literal_eval(node.value)
        program, mode = metadata.get('source_program'), metadata.get('translation_mode')
        if type(program) is not str or not re.fullmatch(r'[A-Z_][A-Z_0-9]*', program) or mode != 'pythonic':
            raise ValueError('A Pythonic generated Program identity is required')
        if cooperative and not any(isinstance(node, ast.FunctionDef) and node.name == '_execute' for node in classes[0].body):
            raise ValueError('Linked runs require cooperative generated modules. Translate with --cooperative or export the linked project.')
    except (UnicodeError, SyntaxError, ValueError, TypeError, RecursionError) as error:
        raise RunDocumentError('Invalid Python target: ' + str(error)) from error
    return dict(sha256=hashlib.sha256(raw).hexdigest(), program=program, mode=mode), code


def _context(config):
    if type(config) is not dict:
        raise RunDocumentError('inputs.context must be an execution-context object')
    try:
        with rt._numeric_scope('pythonic'):
            return rt.ExecutionContext.from_config(deepcopy(config))
    except (ValueError, TypeError, KeyError, rt.KarelRuntimeError, RecursionError) as error:
        raise RunDocumentError('Invalid input context: ' + str(error)) from error


def make_document(target, *, relative_to=None, context=None, max_steps=100000, max_output_chars=1048576, discover=False):
    """Inspect metadata and supplied context without importing/running the target."""
    path, identity, _ = _target(target)
    config = {} if context is None else _decode(_encode(context))
    _context(config)
    if type(discover) is not bool:
        raise RunDocumentError('discover must be BOOLEAN')
    template = None
    if discover:
        from .input_template import prepare_inputs
        raw = _read(path)
        if hashlib.sha256(raw).hexdigest() != identity['sha256']:
            raise RunDocumentError('Python target changed during input discovery')
        try:
            prepared = prepare_inputs(raw, filename=str(path), context=config)
        except ValueError as error:
            raise RunDocumentError('Input preparation: '+str(error)) from error
        config, template = prepared['context'], prepared['template']
    if type(max_steps) is not int or max_steps < 1:
        raise RunDocumentError('max_steps must be a positive INTEGER')
    if type(max_output_chars) is not int or not 1 <= max_output_chars <= MAX_BYTES:
        raise RunDocumentError('max_output_chars must be an INTEGER in 1..16777216')
    name = str(path)
    if relative_to is not None:
        try:
            name = os.path.relpath(path, Path(relative_to).resolve())
        except ValueError:
            pass  # Different volumes retain an explicit absolute target path.
    inputs = dict(context=config)
    if template is not None:
        inputs['template'] = template
    return dict(schema=SCHEMA, target=dict(path=name, **identity),
                limits=dict(max_steps=max_steps, max_output_chars=max_output_chars),
                inputs=inputs, results=None)


def _store(path, document, *, expected=None, protected=()):
    raw = _encode(document)
    check_output(path, overwrite=expected is not None, protected=protected)
    if expected is not None and _read(path) != expected:
        raise RunDocumentError('Run document changed during the operation; external edits preserved')
    atomic_bytes(path, raw, overwrite=expected is not None)
    return raw


def create_document(target, destination, *, context=None, max_steps=100000, max_output_chars=1048576, protected=(), discover=False):
    """Create a new document; never replace code, input files or old reports."""
    destination = Path(destination).absolute()
    document = make_document(target, relative_to=destination.parent, context=context,
                             max_steps=max_steps, max_output_chars=max_output_chars, discover=discover)
    _store(destination, document, protected=(target, *protected))
    return document


def _document_fields(document, *, inspect_only=False):
    if (type(document) is not dict or set(document) != {'schema', 'target', 'limits', 'inputs', 'results'}
            or document['schema'] != SCHEMA):
        raise RunDocumentError('Expected a karel2py.run.v1 document')
    target, limits, inputs = document['target'], document['limits'], document['inputs']
    if (type(target) is not dict or set(target) != {'path', 'sha256', 'program', 'mode'}
            or type(target['path']) is not str or not target['path']
            or type(target['program']) is not str or not re.fullmatch(r'[A-Z_][A-Z_0-9]*', target['program'])
            or target['mode'] != 'pythonic'
            or type(target['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', target['sha256'])):
        raise RunDocumentError('Malformed target identity')
    if (type(limits) is not dict or set(limits) != {'max_steps', 'max_output_chars'}
            or type(limits['max_steps']) is not int or limits['max_steps'] < 1
            or type(limits['max_output_chars']) is not int or not 1 <= limits['max_output_chars'] <= MAX_BYTES):
        raise RunDocumentError('Malformed execution limits')
    if type(inputs) is not dict or set(inputs) not in ({'context'}, {'context', 'template'}):
        raise RunDocumentError('inputs requires context and optional template annotations')
    if document['results'] is not None and type(document['results']) is not dict:
        raise RunDocumentError('results must be null or an object')
    if not inspect_only and document['results'] is not None and document['results'].get('status') == 'running':
        raise RunDocumentError('Previous run is running or interrupted; resolve it and reset results to null before retrying')
    if 'template' in inputs:
        from .input_template import validate_annotations
        try:
            validate_annotations(inputs['template'], target)
        except ValueError as error:
            raise RunDocumentError(str(error)) from error
    return target, limits, inputs


def _validate(document, path):
    target, _, inputs = _document_fields(document)
    target_path, identity, code = _target(path.parent / target['path'])
    if {key: target[key] for key in ('sha256', 'program', 'mode')} != identity:
        raise RunDocumentError('Python target changed; create a new run document')
    return target_path, code, _context(inputs['context'])


def read_document(path):
    """Read a saved document and the exact file revision used by its editor."""
    raw = _read(path)
    document = _decode(raw)
    if isinstance(document, dict) and document.get('schema') == PROJECT_SCHEMA:
        from .project_run import project_document_fields

        project_document_fields(document, inspect_only=True)
    else:
        _document_fields(document, inspect_only=True)
    return document, raw


def _expected_revision(actual, expected):
    if expected is not None and actual != expected:
        raise RunDocumentError('Run document changed on disk. Reopen it before continuing.')


def _read_revision(path, expected):
    path = Path(path).absolute()
    original = _read(path)
    _expected_revision(original, expected)
    return path, original, _decode(original)


def _standalone_edit_target(path, document):
    target, _, _ = _document_fields(document)
    target_path, identity, _ = _target(path.parent / target['path'])
    if identity != {key: target[key] for key in ('sha256', 'program', 'mode')}:
        raise RunDocumentError('Python target changed. Rediscover into a new run document.')
    return target_path


def _edit_target_paths(path, document):
    if isinstance(document, dict) and document.get('schema') == PROJECT_SCHEMA:
        from .project_run import project_document_fields, verify_project_pins

        target, _ = project_document_fields(document)
        return tuple(row[0] for row in verify_project_pins(path, target).values())
    return (_standalone_edit_target(path, document),)


def _store_edited_inputs(path, document, original, target_paths, protected):
    if document['schema'] == PROJECT_SCHEMA:
        from .project_run import check_project_pin_bytes

        check_project_pin_bytes(path, document['target'])
    return _store(path, document, expected=original, protected=(*target_paths, *protected))


def _prepare_edited_context(document, target_paths, context):
    if document['schema'] == PROJECT_SCHEMA:
        from .project_input_discovery import prepare_project_inputs

        return prepare_project_inputs(document['target'], target_paths, context)
    from .input_template import prepare_inputs

    target_path, = target_paths
    target_bytes = _read(target_path)
    if hashlib.sha256(target_bytes).hexdigest() != document['target']['sha256']:
        raise RunDocumentError('Python target changed during input discovery')
    return prepare_inputs(target_bytes, filename=str(target_path), context=context)


def _replace_prepared_inputs(document, prepared):
    inputs = document['inputs']
    if 'refresh' in inputs.get('template', {}):
        prepared['template']['refresh'] = inputs['template']['refresh']
    inputs.update(prepared)


def prepare_project_document(path, *, context=None, expected=None, protected=()):
    """Prepare a pinned run's inputs and keep any saved results."""
    path, original, document = _read_revision(path, expected)
    if not isinstance(document, dict) or document.get('schema') != PROJECT_SCHEMA:
        raise RunDocumentError('Expected a karel2py.project-run.v1 document.')
    target_paths = _edit_target_paths(path, document)
    inputs = document['inputs']
    prepared = _prepare_edited_context(document, target_paths, inputs['context'] if context is None else context)
    _replace_prepared_inputs(document, prepared)
    revision = _store_edited_inputs(path, document, original, target_paths, protected)
    return document, revision


def save_context(path, text, *, expected, protected=()):
    """Validate and save edited inputs against the revision shown by the editor."""
    context = _decode(text.encode('utf-8'))
    path, original, document = _read_revision(path, expected)
    target_paths = _edit_target_paths(path, document)
    inputs = document['inputs']
    if 'template' in inputs:
        _replace_prepared_inputs(document, _prepare_edited_context(document, target_paths, context))
    else:
        _context(context)
        inputs['context'] = context
    revision = _store_edited_inputs(path, document, original, target_paths, protected)
    return document, revision


def _save_discovered_value(path, selected, update, *, expected, protected):
    from .input_template import _prepare
    from .runner_values import input_key

    path, original, document = _read_revision(path, expected)
    target_paths = _edit_target_paths(path, document)
    if 'template' not in document['inputs']:
        raise RunDocumentError('Discover inputs before editing a selected value.')
    prepared = _prepare_edited_context(document, target_paths, document['inputs']['context'])
    template, context = prepared['template'], prepared['context']
    report = template['discovery']
    for candidate, binding in zip(report['inputs'], template['bindings']):
        if input_key(candidate) == selected:
            refresh_layout = update(context, candidate, binding)
            break
    else:
        raise RunDocumentError('This input is no longer in the discovery report.')
    updated = (_prepare_edited_context(document, target_paths, context) if refresh_layout
               else _prepare(report, context, materialize=False))
    _replace_prepared_inputs(document, updated)
    revision = _store_edited_inputs(path, document, original, target_paths, protected)
    return document, revision


def save_input_value(path, selected, kind, text, *, expected, protected=()):
    """Save one discovered scalar using a freshly validated target binding."""
    from .runner_values import scalar_slot

    def update(context, candidate, binding):
        scalar_slot(context, candidate, binding).set_text(kind, text)

    return _save_discovered_value(path, selected, update, expected=expected, protected=protected)


def save_input_structure(path, selected, payload, *, expected, protected=()):
    """Save a checked aggregate or position draft with one file publication."""
    from .structured_inputs import structured_slot

    def update(context, candidate, binding):
        slot = structured_slot(context, candidate, binding)
        previously_missing = (candidate['kind'] == 'variable'
                              and slot.container[slot.key] == {'uninitialized': True})
        slot.replace(payload)
        # Materializing this record may change the status of a named lookup
        # or transfer, which can change the branches that read other inputs.
        if previously_missing:
            root = tuple_spec(candidate['root_type'])
            return rt.array_leaf_spec(root)[0] == 'PATH'
        return False

    return _save_discovered_value(path, selected, update, expected=expected, protected=protected)


def refresh_document(source, destination, *, target=None, expected=None, protected=()):
    """Rediscover into a new document, retaining the original and its results."""
    source, destination = Path(source).absolute(), Path(destination).absolute()
    original = _read(source)
    _expected_revision(original, expected)
    previous = _decode(original)
    old_target, limits, inputs = _document_fields(previous)
    selected = Path(target) if target is not None else source.parent / old_target['path']
    selected = selected.resolve(strict=True)
    raw = _read(selected)
    from .input_refresh import refresh_inputs
    try:
        prepared = refresh_inputs(raw, inputs, filename=str(selected))
    except ValueError as error:
        raise RunDocumentError('Input refresh: '+str(error)) from error
    document = make_document(selected, relative_to=destination.parent, context=prepared['context'], **limits)
    template = prepared['template']
    if template['target']['sha256'] != document['target']['sha256'] or template['target']['program'] != document['target']['program']:
        raise RunDocumentError('Python target changed during input refresh')
    template['refresh']['previous_target'] = {key: old_target[key] for key in ('sha256', 'program')}
    document['inputs']['template'] = template
    return _publish_refreshed_document(source, destination, original, document, (selected, *protected))


def refresh_project_document(source, destination, modules, *, entry=None, expected=None,
                             expected_modules=None, protected=()):
    """Prepare a new linked run from saved inputs and an ordered replacement module set."""
    from .input_refresh import refresh_linked_inputs
    from .input_template import _context_state
    from .path_refresh import path_migrator
    from .project_input_discovery import _analyze_pins
    from .project_run import _project_target, check_project_pin_bytes, project_document_fields

    destination = Path(destination).absolute()
    source, original, previous = _read_revision(source, expected)
    old_target, inputs = project_document_fields(previous)
    target, module_paths = _project_target(
        modules, destination, old_target['program'] if entry is None else entry, expected_modules)
    try:
        _, execution = _context_state(inputs['context'])
        migrate_path = path_migrator()
        report = _analyze_pins(target, module_paths, execution=execution, migrate_path=migrate_path)
        prepared = refresh_linked_inputs(report, inputs, old_target, execution, migrate_path)
    except ValueError as error:
        raise RunDocumentError('Input refresh: '+str(error)) from error
    document = dict(schema=PROJECT_SCHEMA, target=target, limits=previous['limits'], inputs=prepared, results=None)
    check_project_pin_bytes(destination, target)
    old_paths = tuple(source.parent / row['path'] for row in old_target['modules'])
    return _publish_refreshed_document(source, destination, original, document, (*module_paths, *old_paths, *protected))


def _publish_refreshed_document(source, destination, original, document, protected):
    try:
        old_path = os.path.relpath(source, destination.parent)
    except ValueError:
        old_path = str(source)
    refresh = document['inputs']['template']['refresh']
    refresh['previous_document'] = dict(path=old_path, sha256=hashlib.sha256(original).hexdigest())
    if _read(source) != original:
        raise RunDocumentError('Source run document changed during refresh; external edits preserved')
    _store(destination, document, protected=(source, *protected))
    return document


def _error(error):
    return dict(type=type(error).__name__, message=str(error), line=getattr(error, 'line', None))


def _now():
    return datetime.now(timezone.utc).isoformat()


class _RunCancelled(KeyboardInterrupt):
    """Unwind generated execution and preserve partial results on request."""


def _run_status(error):
    if isinstance(error, KeyboardInterrupt): return 'cancelled'
    if isinstance(error, rt.KarelAbort): return 'aborted'
    if isinstance(error, rt.KarelStop): return 'stopped'
    if isinstance(error, rt.KarelPause): return 'paused'
    return 'failed'


def _check_cancelled(event, line=None):
    if event is not None and event.is_set():
        error = _RunCancelled('Run cancelled by the user')
        error.line = line
        raise error


class _RunOutput:
    def __init__(self, limit):
        self.limit = limit
        self.parts = []
        self.length = 0

    def write(self, text):
        if type(text) is not str or self.length + len(text) > self.limit:
            raise rt.KarelRuntimeError('Runner text output limit exceeded')
        self.length += len(text)
        self.parts.append(text)

    def text(self):
        return ''.join(self.parts)


def run_document(path, *, expected=None, cancel_event=None, protected=()):
    """Execute pinned trusted Python once; publish terminal/partial results."""
    path = Path(path).absolute()
    original = _read(path)
    _expected_revision(original, expected)
    document = _decode(original)
    if type(document) is dict and document.get('schema') == PROJECT_SCHEMA:
        from .project_run import run_project_document
        return run_project_document(path, document, original, cancel_event=cancel_event, protected=protected)
    target, code, context = _validate(document, path)
    started = _now()
    document['results'] = dict(status='running', runner_version=__version__, started_utc=started)
    protected = (target, *protected)
    pending = _store(path, document, expected=original, protected=protected)
    output = _RunOutput(document['limits']['max_output_chars'])
    program = None
    failure = None
    status = 'completed'
    capture_errors = {}

    def check_cancelled(line=None):
        _check_cancelled(cancel_event, line)

    def sleep(seconds):
        if cancel_event.wait(seconds):
            check_cancelled()

    with rt._numeric_scope('pythonic'):
        try:
            if cancel_event is not None:
                check_cancelled()
            namespace = dict(__name__='_karel2py_run_target', __file__=str(target))
            exec(code, namespace)
            cls = namespace.get('Program')
            if not isinstance(cls, type) or cls.source_program != document['target']['program'] or cls.translation_mode != 'pythonic':
                raise RunDocumentError('Loaded target identity differs from inspected metadata')
            program = cls(context=context, write=output.write)
            if cancel_event is not None:
                program._state._run_cancel_check = check_cancelled
                program._state._sleep = sleep
            program.run(max_steps=document['limits']['max_steps'])
        except BaseException as error:
            failure = _error(error)
            status = _run_status(error)
            if cancel_event is not None and program is not None:
                program._state._run_cancel_check = None
            if program is not None and callable(getattr(program, 'stop', None)):
                try:
                    program.stop()
                except Exception as cleanup_error:
                    capture_errors['cleanup'] = _error(cleanup_error)
        snapshot = None
        if program is not None:
            try:
                snapshot = program.snapshot()
                if program._state.registers is not None:
                    context.numeric = program._state.registers
            except Exception as error:
                capture_errors['variables'] = _error(error)
        state = None
        try:
            state = context.to_config()
        except Exception as error:
            capture_errors['context'] = _error(error)
    document['results'] = dict(status=status, runner_version=__version__, started_utc=started,
                               finished_utc=_now(), variables=snapshot, context=state,
                               text_output=output.text(), error=failure, capture_errors=capture_errors)
    _store(path, document, expected=pending, protected=protected)
    return document


def _template_counts(document):
    template = document['inputs']['template']
    return dict(inputs=len(template['bindings']), requirements=len(template['requirements']),
                unresolved=len(template['discovery']['unresolved']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=f'KarelToPython {__version__} - explicit offline run documents')
    parser.add_argument('--version', action='version', version=__version__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    create = subparsers.add_parser('create', help='Inspect Python and save supplied inputs without execution')
    create.add_argument('target', type=Path)
    create.add_argument('document', type=Path)
    create.add_argument('--context', type=Path, help='Existing execution-context JSON copied into inputs')
    create.add_argument('--discover', action='store_true', help='Prepare missing variable shapes and input requirements without target execution')
    create.add_argument('--max-steps', type=int, default=100000)
    create.add_argument('--max-output-chars', type=int, default=1048576)
    project = subparsers.add_parser('create-project', help='Pin a set of cooperative generated Python modules')
    project.add_argument('document', type=Path)
    project.add_argument('modules', type=Path, nargs='+')
    project.add_argument('--entry', required=True, help='Declared KAREL program to start')
    project.add_argument('--context', type=Path, help='Explicit execution-context JSON copied into inputs')
    project.add_argument('--discover', action='store_true', help='Prepare owner-qualified inputs without executing the linked modules')
    project.add_argument('--max-steps', type=int, default=100000, help='Execution step limit per task')
    project.add_argument('--max-cycles', type=int, default=100000, help='Scheduler cycle limit')
    project.add_argument('--max-output-chars', type=int, default=1048576, help='Combined WRITE output limit')
    discover = subparsers.add_parser('discover', help='Inspect read-before-write inputs without importing or executing Python')
    discover.add_argument('target', type=Path)
    discover.add_argument('--output', type=Path, help='New private JSON report; otherwise print the full report')
    discover_project = subparsers.add_parser('discover-project', help='Discover inputs from a pinned linked run without executing it')
    discover_project.add_argument('document', type=Path)
    discover_project.add_argument('--output', type=Path, help='New private JSON report; otherwise print the full report')
    prepare_project = subparsers.add_parser('prepare-project', help='Prepare inputs in an existing pinned linked run')
    prepare_project.add_argument('document', type=Path)
    prepare_project.add_argument('--context', type=Path, help='Replace input context from an explicit JSON file before preparation')
    refresh = subparsers.add_parser('refresh', help='Rediscover into a new run document, retaining compatible edited inputs')
    refresh.add_argument('source', type=Path)
    refresh.add_argument('document', type=Path)
    refresh.add_argument('--target', type=Path, help='New generated Python; otherwise use the source document target path')
    refresh_project = subparsers.add_parser('refresh-project', help='Carry compatible inputs to a new linked module set')
    refresh_project.add_argument('source', type=Path)
    refresh_project.add_argument('document', type=Path)
    refresh_project.add_argument('modules', type=Path, nargs='+', help='Replacement modules in scheduling order')
    refresh_project.add_argument('--entry', help='Declared KAREL entry program; defaults to the saved entry')
    run = subparsers.add_parser('run', help='Explicitly execute the pinned trusted Python target')
    run.add_argument('document', type=Path)
    args = parser.parse_args(argv)
    print(f'KarelToPython {__version__}', file=sys.stderr)
    try:
        if args.command == 'create-project':
            from .project_run import create_project_document

            context = _decode(_read(args.context)) if args.context else None
            document = create_project_document(args.modules, args.document, entry=args.entry, context=context,
                max_steps=args.max_steps, max_cycles=args.max_cycles, max_output_chars=args.max_output_chars,
                protected=(args.context,) if args.context else (), discover=args.discover)
            summary = dict(status='prepared', program=document['target']['program'], modules=len(args.modules))
            if args.discover:
                summary.update(_template_counts(document))
            print(json.dumps(summary))
            return 0
        if args.command == 'prepare-project':
            context = _decode(_read(args.context)) if args.context else None
            if args.context:
                _context(context)
            document, _ = prepare_project_document(args.document, context=context,
                                                   protected=(args.context,) if args.context else ())
            print(json.dumps(dict(status='prepared', program=document['target']['program'], **_template_counts(document))))
            return 0
        if args.command in ('refresh', 'refresh-project'):
            if args.command == 'refresh-project':
                document = refresh_project_document(args.source, args.document, args.modules, entry=args.entry)
            else:
                document = refresh_document(args.source, args.document, target=args.target)
            template = document['inputs']['template']
            print(json.dumps(dict(status='refreshed', program=document['target']['program'],
                changes={name: len(rows) for name, rows in template['refresh']['changes'].items()},
                requirements=len(template['requirements']), unresolved=len(template['discovery']['unresolved']))))
            return 0
        if args.command in ('discover', 'discover-project'):
            if args.command == 'discover-project':
                from .project_input_discovery import discover_project_document

                report = discover_project_document(args.document)
                module_paths = (args.document.absolute().parent / row['path'] for row in report['target']['modules'])
                protected = (args.document, *module_paths)
            else:
                from .input_discovery import discover_file

                report = discover_file(args.target)
                protected = (args.target,)
            if args.output:
                _store(args.output, report, protected=protected)
                print(json.dumps(dict(complete=report['complete'], inputs=len(report['inputs']), unresolved=len(report['unresolved']))))
            else:
                print(json.dumps(report, indent=2, allow_nan=False))
            return 0
        if args.command == 'create':
            context = _decode(_read(args.context)) if args.context else None
            document = create_document(args.target, args.document, context=context,
                                       max_steps=args.max_steps, max_output_chars=args.max_output_chars,
                                       protected=(args.context,) if args.context else (), discover=args.discover)
            summary = dict(status='prepared', program=document['target']['program'])
            if args.discover:
                summary.update(_template_counts(document))
            print(json.dumps(summary))
            return 0
        document = run_document(args.document)
        result = document['results']
        print(json.dumps(dict(status=result['status'], program=document['target']['program'],
                              error=result['error'], capture_errors=result['capture_errors'])))
        return int(result['status'] != 'completed' or bool(result['capture_errors']))
    except (OSError, ValueError, TypeError, rt.KarelRuntimeError) as error:
        parser.exit(2, f'karel2py.runner: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
