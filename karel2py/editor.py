"""Bounded display helpers and native code views; no source execution."""
import io
import keyword
import re

from .lexer import PATTERN
from .workbench import MAX_SOURCE_BYTES


KAREL_KEYWORDS = frozenset('''PROGRAM VAR CONST TYPE BEGIN END ROUTINE RETURN FROM VALUE
IF THEN ELSE ENDIF WHILE DO ENDWHILE REPEAT UNTIL FOR TO DOWNTO ENDFOR SELECT CASE
ENDSELECT GOTO USING ENDUSING ARRAY OF STRUCTURE ENDSTRUCTURE INTEGER REAL BOOLEAN
STRING BYTE SHORT POSITION XYZWPR XYZWPREXT JOINTPOS VECTOR CONFIG PATH QUEUE_TYPE
FILE TRUE FALSE NOT AND OR XOR DIV MOD CONDITION WHEN ENDCONDITION ENABLE DISABLE
PURGE CONNECT DISCONNECT TIMER PAUSE STOP ABORT RESUME UNPAUSE DELAY WAIT WRITE
READ OPEN CLOSE CANCEL PULSE NOWAIT EVAL CR'''.split())
PYTHON_PATTERN = re.compile(r'''(?P<COMMENT>\#[^\n]*)|(?P<STRING>'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*")|(?P<NUMBER>\b(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\b)|(?P<NAME>[A-Za-z_]\w*)''')
MAX_COLOR_CHARS = 30000


def syntax_spans(text, language):
    """Visual hints on a bounded excerpt, independent of parser acceptance."""
    pattern = PATTERN if language == 'karel' else PYTHON_PATTERN if language == 'python' else None
    if pattern is None: return []
    result = []
    for match in pattern.finditer(text[:MAX_COLOR_CHARS]):
        kind, value = match.lastgroup, match.group()
        if kind == 'NAME':
            if not (value.upper() in KAREL_KEYWORDS if language == 'karel' else keyword.iskeyword(value)): continue
            kind = 'KEYWORD'
        elif kind in ('INT', 'REAL'): kind = 'NUMBER'
        if kind in ('COMMENT', 'STRING', 'NUMBER', 'KEYWORD', 'DIRECTIVE'):
            result.append((kind.lower(), match.start(), match.end()))
    return result


def replace_literal(text, query, replacement, *, match_case=False, limit=MAX_SOURCE_BYTES):
    """Prepare a literal nonoverlapping replacement before any editor mutation."""
    if not query: return text, 0
    pattern = re.compile(re.escape(query), 0 if match_case else re.IGNORECASE)
    output, previous, size, count = io.StringIO(), 0, 0, 0
    replacement_size = len(replacement.encode('utf-8'))
    for match in pattern.finditer(text):
        prefix = text[previous:match.start()]
        size += len(prefix.encode('utf-8')) + replacement_size
        if size > limit: raise ValueError('Replacement would exceed the 4 MiB editor limit')
        output.write(prefix)
        output.write(replacement)
        previous, count = match.end(), count + 1
    tail = text[previous:]
    if size + len(tail.encode('utf-8')) > limit: raise ValueError('Replacement would exceed the 4 MiB editor limit')
    output.write(tail)
    return output.getvalue(), count


def _source_map(rows):
    result = {}
    for row in rows:
        if type(row) is not dict: continue
        values = tuple(row.get(key) for key in ('python_line', 'karel_line', 'karel_column'))
        if any(type(value) is not int or value < 1 for value in values): continue
        python_line, line, column = values
        location = line, column
        if python_line in result and result[python_line] != location: result[python_line] = None
        else: result[python_line] = location
    return {line: location for line, location in result.items() if location is not None}


def generated_lines(rows, karel_line):
    return sorted(line for line, location in _source_map(rows).items() if location[0] == karel_line)


def source_location(rows, python_line):
    return _source_map(rows).get(python_line)


def text_index(widget, base, fragment, offset):
    """Convert a Python string offset to Tk's native line/column representation."""
    line, column = map(int, widget.index(base).split('.'))
    pieces = fragment[:offset].split('\n')
    if len(pieces) > 1: line, column = line + len(pieces) - 1, 0
    column += int(widget.tk.call('string', 'length', pieces[-1]))
    return widget.index(f'{line}.{column}')


class CodeView:
    """A Tk Text with a viewport-sized gutter and bounded syntax coloring."""
    def __init__(self, parent, *, editable=False, language=None):
        import tkinter as tk
        from tkinter import font, ttk
        self.tk, self.language, self.pending, self.closed = tk, language, None, False
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill='both', expand=True)
        self.font = font.Font(root=parent, family='Consolas', size=11)
        self.gutter = tk.Canvas(self.frame, width=40, background='#101c2d', highlightthickness=0)
        self.text = tk.Text(self.frame, wrap='none', undo=editable, font=self.font,
                            background='#142237', foreground='#dce7f5', insertbackground='#ffffff',
                            selectbackground='#315678', relief='flat', padx=12, pady=12,
                            borderwidth=0, tabs=(self.font.measure('    '),), highlightthickness=0)
        # Application shortcuts must run before Text's platform-specific bindings.
        tags = self.text.bindtags()
        top = str(self.text.winfo_toplevel())
        self.text.bindtags((tags[0], top, *(tag for tag in tags[1:] if tag != top)))
        self.vertical = ttk.Scrollbar(self.frame, orient='vertical', command=self.text.yview)
        horizontal = ttk.Scrollbar(self.frame, orient='horizontal', command=self.text.xview)
        self.text.configure(yscrollcommand=self._scrolled, xscrollcommand=horizontal.set)
        self.frame.rowconfigure(0, weight=1)
        self.frame.columnconfigure(1, weight=1)
        self.gutter.grid(row=0, column=0, sticky='ns')
        self.text.grid(row=0, column=1, sticky='nsew')
        self.vertical.grid(row=0, column=2, sticky='ns')
        horizontal.grid(row=1, column=1, sticky='ew')
        for tag, color in (('keyword', '#7dd3fc'), ('string', '#a7e5aa'), ('comment', '#899cb5'), ('number', '#f0c584'), ('directive', '#d1b5f2')):
            self.text.tag_configure('syntax_' + tag, foreground=color)
        self.text.tag_configure('current_line', background='#1b3048')
        self.text.tag_lower('current_line')
        for event in ('<Configure>', '<KeyRelease>', '<ButtonRelease-1>', '<<Modified>>'):
            self.text.bind(event, self.refresh, add=True)
        self.text.bind('<Destroy>', self._destroy, add=True)
        if not editable: self.text.configure(state='disabled')
        self.refresh()

    def _scrolled(self, first, last):
        self.vertical.set(first, last)
        self.refresh()

    def refresh(self, event=None):
        if not self.closed and self.pending is None:
            self.pending = self.text.after_idle(self._draw)

    def _draw(self):
        self.pending = None
        if self.closed: return
        try:
            text = self.text
            self.gutter.delete('all')
            end_line = int(text.index('end-1c').split('.')[0])
            width = self.font.measure(str(end_line)) + 20
            self.gutter.configure(width=width)
            first_line = int(text.index('@0,0').split('.')[0])
            last_line = int(text.index(f'@0,{text.winfo_height()}').split('.')[0])
            current = int(text.index('insert').split('.')[0])
            for line in range(first_line, min(last_line + 1, first_line + 1000)):
                position = text.dlineinfo(f'{line}.0')
                if position is None: continue
                self.gutter.create_text(width - 9, position[1], text=str(line), anchor='ne', font=self.font,
                                        fill='#62d9c2' if line == current else '#7890ad')
            text.tag_remove('current_line', '1.0', 'end')
            text.tag_add('current_line', f'{current}.0', f'{current}.end+1c')
            for tag in ('keyword', 'string', 'comment', 'number', 'directive'):
                text.tag_remove('syntax_' + tag, '1.0', 'end')
            start = f'{first_line}.0'
            stop = min(last_line + 1, first_line + 1000)
            finish = f'{start}+{MAX_COLOR_CHARS}c'
            if text.compare(finish, '>', f'{stop}.end'): finish = f'{stop}.end'
            excerpt = text.get(start, finish)
            for tag, begin, end in syntax_spans(excerpt, self.language):
                text.tag_add('syntax_' + tag, text_index(text, start, excerpt, begin), text_index(text, start, excerpt, end))
            text.tag_raise('sel')
        except self.tk.TclError:
            if not self.closed: raise

    def zoom(self, delta):
        size = max(8, min(24, self.font.cget('size') + delta))
        self.font.configure(size=size)
        self.text.configure(tabs=(self.font.measure('    '),))
        self.refresh()

    def _destroy(self, event):
        if event.widget is not self.text: return
        self.closed = True
        if self.pending is not None:
            self.text.after_cancel(self.pending)
            self.pending = None
