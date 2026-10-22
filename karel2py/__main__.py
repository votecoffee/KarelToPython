"""CLI: validate or compile KL without executing source or connecting to a robot."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

from . import __version__, translate
from .lexer import TranslationError


def write_new(path, text, force):
    # An explicit exclusive open avoids silently replacing user files.
    with path.open('w' if force else 'x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)


def array_shape_option(value):
    """Parse a bounded literal shape; source expressions are never evaluated."""
    match = re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)=([0-9]+(?:,[0-9]+){0,2})', value)
    if match is None:
        raise argparse.ArgumentTypeError('Use NAME=SIZE[,SIZE[,SIZE]] with an ASCII name and positive INTEGER dimensions')
    try:
        shape = tuple(int(size) for size in match[2].split(','))
    except ValueError:
        raise argparse.ArgumentTypeError('ARRAY dimensions must be bounded INTEGER literals') from None
    if any(not 1 <= size <= 32767 for size in shape):
        raise argparse.ArgumentTypeError('ARRAY dimensions must be INTEGER in 1..32767')
    return match[1].upper(), shape


def main(argv=None):
    parser = argparse.ArgumentParser(description='KAREL-to-Python offline subset translator')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('source', type=Path, help='Input .kl source (UTF-8)')
    parser.add_argument('-o', '--output', type=Path, help='Generated Python module')
    parser.add_argument('--report', type=Path, help='JSON diagnostics, hashes and source map')
    parser.add_argument('--check', action='store_true', help='Validate without generating a module')
    parser.add_argument('--force', action='store_true', help='Allow overwriting explicitly named output/report')
    parser.add_argument('--mode', default='pythonic', metavar='pythonic',
                        help='Translation policy (default: pythonic); strict is a future milestone')
    parser.add_argument('--cooperative', action='store_true', help='Enable host pause/resume even without source task-control statements')
    parser.add_argument('--array-shape', action='append', type=array_shape_option, default=[], metavar='NAME=DIM[,DIM]',
                        help='Explicit outer dimensions for a global ARRAY containing *; repeated for each variable, embedded during translation')
    args = parser.parse_args(argv)
    array_shapes = {}
    for name, shape in args.array_shape:
        if name in array_shapes: parser.error(f'Duplicate case-insensitive --array-shape name {name}')
        array_shapes[name] = shape
    if args.check and args.output:
        parser.error('--check cannot be combined with --output')
    if not args.check and args.output is None:
        parser.error('Use --output or --check')
    paths = [p for p in (args.output, args.report) if p is not None]
    if any(p.resolve() == args.source.resolve() for p in paths):
        parser.error('Output/report must differ from source')
    if len(paths) == 2 and paths[0].resolve() == paths[1].resolve():
        parser.error('Output and report must differ')
    try:
        for path in paths:
            if path.exists() and not args.force:
                raise FileExistsError(f'{path} exists; use --force to replace it')
            if not path.parent.is_dir():
                raise FileNotFoundError(f'Output directory {path.parent} does not exist')
        source_bytes = args.source.read_bytes()
        source = source_bytes.decode('utf-8-sig')
        try:
            result = translate(source, filename=str(args.source), array_shapes=array_shapes, mode=args.mode, cooperative=args.cooperative)
        except TranslationError as exc:
            report = dict(status='rejected', translator_version=__version__,
                          source_file_sha256=hashlib.sha256(source_bytes).hexdigest(), diagnostics=[exc.as_dict()],
                          translation_context=dict(mode=args.mode, array_shapes={key: list(shape) for key, shape in sorted(array_shapes.items())}))
            if args.report: write_new(args.report, json.dumps(report, indent=2) + '\n', args.force)
            print(str(exc), file=sys.stderr)
            return 2
        result.report['source_file_sha256'] = hashlib.sha256(source_bytes).hexdigest()
        if args.output: write_new(args.output, result.python_source, args.force)
        if args.report: write_new(args.report, json.dumps(result.report, indent=2) + '\n', args.force)
        print(f'{result.report["program"]}: {"validated" if args.check else "translated"}; '
              f'{len(result.report["features"])} feature categories')
        return 0
    except (OSError, UnicodeError) as exc:
        print(f'karel2py: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
