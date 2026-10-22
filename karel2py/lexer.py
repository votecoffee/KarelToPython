"""Tokenize a bounded KAREL subset, retaining source positions."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


class TranslationError(Exception):
    def __init__(self, code, message, token, filename="<input>"):
        self.code, self.message, self.token, self.filename = code, message, token, filename
        super().__init__(f"{filename}:{token.line}:{token.column}: {code}: {message}")

    def as_dict(self):
        return dict(code=self.code, message=self.message, file=self.filename,
                    line=self.token.line, column=self.token.column)


PATTERN = re.compile(
    r"(?P<WS>[ \t]+)|(?P<NL>\r\n|[\r\n\f])|(?P<COMMENT>--[^\r\n\f]*)|"
    r"(?P<DIRECTIVE>%[^\r\n\f]*)|"
    r"(?P<STRING>'(?:[^'\r\n\f]|'')*')|"
    r"(?P<REAL>(?:\d+\.\d*|\.\d+)(?:[Ee][+-]?\d+)?|\d+[Ee][+-]?\d+)|"
    r"(?P<INT>\d+)|(?P<NAME>\$(?i:SCAN_TIME)|[A-Za-z_][A-Za-z_0-9]*)|"
    r"(?P<OP>>=<|<=|>=|<>|::|[.+*/=<>(),;:@#\[\]-])|(?P<CONT>&)|(?P<BAD>.)"
)


def directive_content(value):
    """Find a directive's real trailing comment and unquoted continuation marker."""
    quoted, continued, index = False, False, 0
    while index < len(value):
        char = value[index]
        if char == "'":
            if quoted and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif not quoted:
            if value.startswith('--', index): return value[:index].strip(), continued
            if char == '&': continued = True
        index += 1
    return value.strip(), continued


def tokenize(source, filename, *, continuations=None):
    raw, line, column = [], 1, 1
    # utf-8-sig is used by the CLI; support direct API callers too.
    source = source.removeprefix('\ufeff')
    for match in PATTERN.finditer(source):
        kind, value = match.lastgroup, match.group()
        token = Token(kind, value.upper() if kind == 'NAME' else value, line, column)
        if kind == 'BAD':
            raise TranslationError('E_LEX', f"Unsupported character {value!r}", token, filename)
        if kind == 'DIRECTIVE' and directive_content(value)[1]:
            raise TranslationError('E_CONTINUATION_DIRECTIVE',
                                   'Continued translator directives are not supported', token, filename)
        raw.append(token)
        if kind == 'NL':
            line, column = line + 1, 1
        else:
            column += len(value)
    raw.append(Token('EOF', '<EOF>', line, column))
    removed = set()
    physical_lines = re.split(r'\r\n|[\r\n\f]', source)
    for index, token in enumerate(raw):
        if token.kind != 'CONT':
            continue

        def reject(code, message):
            raise TranslationError(code, message, token, filename)

        left = index - 1
        while left >= 0 and raw[left].kind == 'WS':
            left -= 1
        if left < 0 or raw[left].line != token.line or raw[left].kind in ('NL', 'CONT'):
            reject('E_CONTINUATION_POSITION', 'Continuation requires source tokens before & on the same physical line')
        end = index + 1
        while raw[end].kind in ('WS', 'COMMENT'):
            end += 1
        if raw[end].kind == 'EOF':
            reject('E_CONTINUATION_END', 'Continuation requires a following physical newline and source line')
        if raw[end].kind != 'NL':
            reject('E_CONTINUATION_POSITION', 'Only whitespace or a trailing comment may follow & before the newline')
        right = end + 1
        while raw[right].kind == 'WS':
            right += 1
        if raw[right].kind in ('NL', 'COMMENT', 'EOF'):
            reject('E_CONTINUATION_EMPTY', 'The immediately following physical line must contain source tokens')
        if raw[right].kind == 'CONT':
            reject('E_CONTINUATION_POSITION', 'A continued line cannot begin with &')
        if raw[right].kind == 'DIRECTIVE':
            reject('E_CONTINUATION_DIRECTIVE', 'Continuation into a translator directive is not supported')
        if any(len(physical_lines[n - 1]) > 252 for n in (token.line, raw[right].line)):
            reject('E_CONTINUATION_LINE_LENGTH', 'Each continued physical line must fit the manual 252-character limit; truncation is not modeled')
        if raw[left].kind == 'NAME' and raw[left].value == 'BEGIN':
            reject('E_CONTINUATION_SEPARATOR', 'BEGIN requires a statement separator; & cannot remove its newline')
        # Keep complete physical tokens. If removing the marker/newline could
        # fuse adjacent tokens, require explicit whitespace rather than guessing.
        separated = any(t.kind == 'WS' for t in raw[left + 1:right])
        if not separated:
            joined = PATTERN.match(raw[left].value + raw[right].value)
            if joined and joined.end() > len(raw[left].value):
                reject('E_CONTINUATION_TOKEN', 'Continuation cannot split or fuse lexical tokens; add explicit whitespace between complete tokens')
        removed.update((index, end))
        if continuations is not None:
            continuations.append(dict(line=token.line, column=token.column,
                                      next_line=raw[right].line, next_column=raw[right].column,
                                      trailing_comment=any(t.kind == 'COMMENT' for t in raw[index + 1:end])))
    return [token for index, token in enumerate(raw)
            if index not in removed and token.kind not in ('WS', 'COMMENT')]
