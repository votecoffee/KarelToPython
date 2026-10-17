"""Check public Git contents, Python syntax and relative documentation links."""
import argparse
import ast
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOTS = {'.local', '.venv', 'venv', 'work', 'outputs', 'build', 'dist', '__pycache__'}
PRIVATE_SUFFIXES = {'.pdf', '.pc', '.zip', '.7z', '.log', '.pyc', '.pyo'}
PROFILE_PATH = re.compile(r'(?i)(?:[a-z]:[/\\]+(?:users|documents and settings|~localwork)[/\\]|/(?:users|home)/[^/\s]+/)')
LINK = re.compile(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)')


def public_files(root):
    result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                            cwd=root, capture_output=True, check=True)
    return sorted(set(name.decode('utf-8') for name in result.stdout.split(b'\0') if name))


def anchors(text):
    result, seen = set(), {}
    for match in re.finditer(r'^#{1,6}\s+(.+?)\s*#*$', text, re.MULTILINE):
        slug = re.sub(r'[^\w -]', '', match[1].lower()).replace(' ', '-')
        index = seen.get(slug, 0)
        seen[slug] = index + 1
        result.add(slug + (f'-{index}' if index else ''))
    return result


def check_repository(root=ROOT):
    root = root.resolve()
    files, errors = public_files(root), []
    for relative in files:
        path = root / relative
        parts = Path(relative).parts
        if any(part in LOCAL_ROOTS or part.endswith('.egg-info') for part in parts):
            errors.append(relative + ': local/build artifact is included in Git')
            continue
        if (path.suffix.lower() in PRIVATE_SUFFIXES or relative.endswith('.report.json')
                or '_corpus_audit.json' in relative or '_corpus_baseline_' in relative
                or path.name in {'reference_sources.json', 'implementation_coverage.json', 'manifest.json', 'validation.json'}):
            errors.append(relative + ': private/generated artifact belongs outside public source')
            continue
        if not path.resolve().is_relative_to(root):
            errors.append(relative + ': path resolves outside repository')
            continue
        if not path.is_file():
            errors.append(relative + ': missing file')
            continue
        if path.stat().st_size > 1_000_000:
            errors.append(relative + ': large artifact requires an explicit repository policy')
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeError:
            errors.append(relative + ': unexpected non-UTF-8 file')
            continue
        if PROFILE_PATH.search(text):
            errors.append(relative + ': contains a machine/profile-specific absolute path')
        if path.suffix == '.py':
            try:
                ast.parse(text, filename=relative, feature_version=(3, 11))
            except SyntaxError as error:
                errors.append(relative + ': Python 3.11 syntax: ' + str(error))
        if path.suffix != '.md':
            continue
        for link in LINK.findall(text):
            link = link.strip('<>')
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not destination.is_relative_to(root) or not destination.exists():
                errors.append(relative + ': broken local link ' + link)
            elif parsed.fragment and destination.is_file() and destination.suffix == '.md':
                if unquote(parsed.fragment) not in anchors(destination.read_text(encoding='utf-8')):
                    errors.append(relative + ': broken anchor ' + link)
    return files, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        files, errors = check_repository()
    except (OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Repository check requires a readable Git checkout: {error}\n')
    for error in errors:
        print('FAIL ' + error)
    if errors:
        return 1
    print(f'{len(files)} public files checked: paths, artifacts, Python 3.11 syntax and documentation links passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
