"""Check public Git contents, Python syntax and relative documentation links."""
import argparse
import ast
import hashlib
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOTS = {'.local', '.venv', 'venv', 'work', 'outputs', 'build', 'dist', '__pycache__'}
PRIVATE_SUFFIXES = {'.pdf', '.pc', '.zip', '.7z', '.log', '.pyc', '.pyo'}
PROFILE_PATH = re.compile(r'(?i)(?:[a-z]:[/\\]+(?:users|documents and settings|~localwork)[/\\]|/(?:users|home)/[^/\s]+/)')
LINK = re.compile(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)')

# The supplied application artwork is the only approved binary source content.
APP_ICON_HASHES={f'karel2py/assets/icons/karel_to_python_icon_{size}x{size}.png':digest for size,digest in (
    (16,'b3178ba6af12fe91416de8a76e9a841ee92eb2d26c38b5e9cf43a8db56ac30eb'),
    (20,'06a75a956a543009077137aed72fc6bedfde2115f7d061390c596a1f1e95c077'),
    (24,'15da02169e1de7d1df47ccb959278d321bb854a1adb5e5860da5c3e096b5dd19'),
    (32,'b790c20f9bb9830a3d42a433ce73a79477250752f95faa8b108a5611465d433f'),
    (48,'04c023e9d5557c4a01905c0795b179f6c8a91a43f3af56f0f40939aee61740b5'),
    (64,'a76f5780ab26aea5da31118617e57d7b7a38052cb048f65d1a8e2008084feb33'),
    (128,'0c53482a295f1b13f9574f628cd5bc3a7d7f0555884b03820ae8bdfc8fa07737'),
    (256,'08f0ece9d4a24d76839e5446a42470837d8d45cd53f1d04a0019e83dd0b1c921'))}


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
        if relative in APP_ICON_HASHES:
            if hashlib.sha256(path.read_bytes()).hexdigest()!=APP_ICON_HASHES[relative]:
                errors.append(relative + ': application icon differs from approved original artwork')
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
