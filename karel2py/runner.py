"""Explicit standalone Pythonic runs with separate saved inputs and results."""
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
from .storage import atomic_bytes


SCHEMA = 'karel2py.run.v1'
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
            raise ValueError('A standalone Pythonic generated Program identity is required')
    except (UnicodeError, SyntaxError, ValueError, TypeError, RecursionError) as error:
        raise RunDocumentError('Invalid Python target: ' + str(error)) from error
    return path, dict(sha256=hashlib.sha256(raw).hexdigest(), program=program, mode=mode), code


def _context(config):
    if type(config) is not dict:
        raise RunDocumentError('inputs.context must be an execution-context object')
    try:
        with rt._numeric_scope('pythonic'):
            return rt.ExecutionContext.from_config(deepcopy(config))
    except (ValueError, TypeError, KeyError, rt.KarelRuntimeError, RecursionError) as error:
        raise RunDocumentError('Invalid input context: ' + str(error)) from error


def make_document(target, *, relative_to=None, context=None, max_steps=100000, max_output_chars=1048576):
    """Inspect metadata and supplied context without importing/running the target."""
    path, identity, _ = _target(target)
    config = {} if context is None else _decode(_encode(context))
    _context(config)
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
    return dict(schema=SCHEMA, target=dict(path=name, **identity),
                limits=dict(max_steps=max_steps, max_output_chars=max_output_chars),
                inputs=dict(context=config), results=None)


def _store(path, document, *, expected=None, protected=()):
    raw = _encode(document)
    check_output(path, overwrite=expected is not None, protected=protected)
    if expected is not None and _read(path) != expected:
        raise RunDocumentError('Run document changed during execution; external edits preserved')
    atomic_bytes(path, raw, overwrite=expected is not None)
    return raw


def create_document(target, destination, *, context=None, max_steps=100000, max_output_chars=1048576, protected=()):
    """Create a new document; never replace code, input files or old reports."""
    destination = Path(destination).absolute()
    document = make_document(target, relative_to=destination.parent, context=context,
                             max_steps=max_steps, max_output_chars=max_output_chars)
    _store(destination, document, protected=(target, *protected))
    return document


def _validate(document, path):
    if (type(document) is not dict or set(document) != {'schema', 'target', 'limits', 'inputs', 'results'}
            or document['schema'] != SCHEMA):
        raise RunDocumentError('Expected a karel2py.run.v1 document')
    target, limits, inputs = document['target'], document['limits'], document['inputs']
    if (type(target) is not dict or set(target) != {'path', 'sha256', 'program', 'mode'}
            or type(target['path']) is not str or not target['path']
            or type(target['sha256']) is not str or not re.fullmatch(r'[0-9a-f]{64}', target['sha256'])):
        raise RunDocumentError('Malformed target identity')
    if (type(limits) is not dict or set(limits) != {'max_steps', 'max_output_chars'}
            or type(limits['max_steps']) is not int or limits['max_steps'] < 1
            or type(limits['max_output_chars']) is not int or not 1 <= limits['max_output_chars'] <= MAX_BYTES):
        raise RunDocumentError('Malformed execution limits')
    if type(inputs) is not dict or set(inputs) != {'context'}:
        raise RunDocumentError('inputs requires exactly context')
    if document['results'] is not None and type(document['results']) is not dict:
        raise RunDocumentError('results must be null or an object')
    if document['results'] is not None and document['results'].get('status') == 'running':
        raise RunDocumentError('Previous run is running or interrupted; resolve it and reset results to null before retrying')
    target_path, identity, code = _target(path.parent / target['path'])
    if {key: target[key] for key in ('sha256', 'program', 'mode')} != identity:
        raise RunDocumentError('Python target changed; create a new run document')
    return target_path, code, _context(inputs['context'])


def _error(error):
    return dict(type=type(error).__name__, message=str(error), line=getattr(error, 'line', None))


def _now():
    return datetime.now(timezone.utc).isoformat()


def run_document(path):
    """Execute pinned trusted Python once; publish terminal/partial results."""
    path = Path(path).absolute()
    original = _read(path)
    document = _decode(original)
    target, code, context = _validate(document, path)
    started = _now()
    document['results'] = dict(status='running', runner_version=__version__, started_utc=started)
    pending = _store(path, document, expected=original, protected=(target,))
    output, length = [], 0
    program = None
    failure = None
    status = 'completed'
    capture_errors = {}

    def write(text):
        nonlocal length
        if type(text) is not str or length + len(text) > document['limits']['max_output_chars']:
            raise rt.KarelRuntimeError('Runner text output limit exceeded')
        output.append(text)
        length += len(text)

    with rt._numeric_scope('pythonic'):
        try:
            namespace = dict(__name__='_karel2py_run_target', __file__=str(target))
            exec(code, namespace)
            cls = namespace.get('Program')
            if not isinstance(cls, type) or cls.source_program != document['target']['program'] or cls.translation_mode != 'pythonic':
                raise RunDocumentError('Loaded target identity differs from inspected metadata')
            program = cls(context=context, write=write)
            program.run(max_steps=document['limits']['max_steps'])
        except BaseException as error:
            failure = _error(error)
            status = ('cancelled' if isinstance(error, KeyboardInterrupt) else
                      'aborted' if isinstance(error, rt.KarelAbort) else
                      'stopped' if isinstance(error, rt.KarelStop) else
                      'paused' if isinstance(error, rt.KarelPause) else 'failed')
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
                               text_output=''.join(output), error=failure, capture_errors=capture_errors)
    _store(path, document, expected=pending, protected=(target,))
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=f'KarelToPython {__version__} - explicit offline run documents')
    parser.add_argument('--version', action='version', version=__version__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    create = subparsers.add_parser('create', help='Inspect Python and save supplied inputs without execution')
    create.add_argument('target', type=Path)
    create.add_argument('document', type=Path)
    create.add_argument('--context', type=Path, help='Existing execution-context JSON copied into inputs')
    create.add_argument('--max-steps', type=int, default=100000)
    create.add_argument('--max-output-chars', type=int, default=1048576)
    discover = subparsers.add_parser('discover', help='Inspect read-before-write inputs without importing or executing Python')
    discover.add_argument('target', type=Path)
    discover.add_argument('--output', type=Path, help='New private JSON report; otherwise print the full report')
    run = subparsers.add_parser('run', help='Explicitly execute the pinned trusted Python target')
    run.add_argument('document', type=Path)
    args = parser.parse_args(argv)
    print(f'KarelToPython {__version__}', file=sys.stderr)
    try:
        if args.command == 'discover':
            from .input_discovery import discover_file
            report = discover_file(args.target)
            if args.output:
                _store(args.output, report, protected=(args.target,))
                print(json.dumps(dict(complete=report['complete'], inputs=len(report['inputs']), unresolved=len(report['unresolved']))))
            else:
                print(json.dumps(report, indent=2, allow_nan=False))
            return 0
        if args.command == 'create':
            context = _decode(_read(args.context)) if args.context else None
            document = create_document(args.target, args.document, context=context,
                                       max_steps=args.max_steps, max_output_chars=args.max_output_chars,
                                       protected=(args.context,) if args.context else ())
            print(json.dumps(dict(status='prepared', program=document['target']['program'])))
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
