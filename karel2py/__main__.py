"""CLI: validate or compile KL without executing source or connecting to a robot."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

from . import __version__, translate
from .lexer import TranslationError
from .fileio import check_output, same_file, write_bytes
from .includes import IncludeLibrary,device_option


def write_new(path, text, force, *, protected=()):
    write_bytes(path, text.encode('utf-8'), overwrite=force, protected=protected)


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
    parser = argparse.ArgumentParser(prog='karel2py',
                                     description=f'KarelToPython {__version__} - KAREL-to-Python offline subset translator')
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
    parser.add_argument('-I','--include-dir',type=Path,action='append',default=[],help='Additional include root, searched after the source directory')
    parser.add_argument('--include-device',type=device_option,action='append',default=[],metavar='DEVICE=DIRECTORY',help='Explicit include device mapping; never discovers controller files')
    args = parser.parse_args(argv)
    print(f'KarelToPython {__version__}', file=sys.stderr)
    array_shapes = {}
    for name, shape in args.array_shape:
        if name in array_shapes: parser.error(f'Duplicate case-insensitive --array-shape name {name}')
        array_shapes[name] = shape
    if args.check and args.output:
        parser.error('--check cannot be combined with --output')
    if not args.check and args.output is None:
        parser.error('Use --output or --check')
    devices={}
    for device,directory in args.include_device:
        if device in devices:parser.error('Duplicate include device '+device)
        devices[device]=directory
    paths = [p for p in (args.output, args.report) if p is not None]
    try:
        if any(same_file(path, args.source) for path in paths):
            parser.error('Output/report must differ from source, including file aliases')
        if len(paths) == 2 and same_file(*paths):
            parser.error('Output and report must differ, including file aliases')
        for path in paths:
            check_output(path, overwrite=args.force, protected=(args.source,))
        source_bytes = args.source.read_bytes()
        source = source_bytes.decode('utf-8-sig')
        library=IncludeLibrary.from_directories([args.source.parent,*args.include_dir],devices=devices)
        def protected():return (args.source,*library.paths)
        try:
            result = translate(source, filename=str(args.source), array_shapes=array_shapes, mode=args.mode, cooperative=args.cooperative,includes=library)
        except TranslationError as exc:
            report = dict(status='rejected', translator_version=__version__,
                          source_file_sha256=hashlib.sha256(source_bytes).hexdigest(), diagnostics=[exc.as_dict()],
                          translation_context=dict(mode=args.mode, array_shapes={key: list(shape) for key, shape in sorted(array_shapes.items())}))
            if args.report: write_new(args.report, json.dumps(report, indent=2) + '\n', args.force, protected=protected())
            print(str(exc), file=sys.stderr)
            return 2
        for path in paths:check_output(path,overwrite=args.force,protected=protected())
        result.report['source_file_sha256'] = hashlib.sha256(source_bytes).hexdigest()
        if args.output: write_new(args.output, result.python_source, args.force, protected=protected())
        if args.report: write_new(args.report, json.dumps(result.report, indent=2) + '\n', args.force, protected=protected())
        print(f'{result.report["program"]}: {"validated" if args.check else "translated"}; '
              f'{len(result.report["features"])} feature categories')
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'karel2py: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
