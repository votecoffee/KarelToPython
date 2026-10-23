"""Native desktop workbench. Importing this module does not create a window."""
import argparse
from pathlib import Path
import queue
import sys
import threading

from . import __version__
from .workbench import Document, analyze_project, analyze_source


class Workbench:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        self.tk, self.ttk = tk, ttk
        self.dialog, self.message = filedialog, messagebox
        self.root = root
        self.document = Document()
        self.analysis = None
        self.busy = False
        self.closed = False
        self.revision = 0
        self._queue = queue.Queue()
        self._poll = None
        self._diagnostics = {}
        self.shapes = tk.StringVar()
        self.cooperative = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Open a KAREL file or paste source to begin.')
        self.path_label = tk.StringVar(value='Untitled source')
        self.root.geometry('1280x820')
        self.root.minsize(960, 640)
        self.root.configure(background='#edf2f7')
        self._style()
        self._build()
        self._menu()
        self._exports()
        self.shapes.trace_add('write', lambda *_: self.invalidate())
        self.cooperative.trace_add('write', lambda *_: self.invalidate())
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self._title()

    def _style(self):
        style = self.ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#edf2f7', foreground='#17263c')
        style.configure('Header.TFrame', background='#ffffff')
        style.configure('Header.TLabel', background='#ffffff')
        style.configure('Brand.TLabel', background='#ffffff', foreground='#102a43', font=('Segoe UI', 20, 'bold'))
        style.configure('Muted.TLabel', foreground='#52657b')
        style.configure('Build.TLabel', background='#e5f4f1', foreground='#086b60', padding=(10, 6), font=('Segoe UI', 9))
        style.configure('TButton', padding=(12, 8))
        style.configure('Primary.TButton', background='#087f73', foreground='white', font=('Segoe UI', 10, 'bold'))
        style.map('Primary.TButton', background=[('active', '#06685e'), ('disabled', '#b7c8cb')])
        style.configure('TNotebook', background='#edf2f7', borderwidth=0)
        style.configure('TNotebook.Tab', padding=(16, 9))
        style.map('TNotebook.Tab', background=[('selected', '#ffffff')], foreground=[('selected', '#087f73')])
        style.configure('Treeview', rowheight=29, background='#ffffff', fieldbackground='#ffffff')
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), padding=6)

    def _button(self, parent, text, command, **options):
        button = self.ttk.Button(parent, text=text, command=command, **options)
        self.actions.append(button)
        return button

    def _build(self):
        tk, ttk = self.tk, self.ttk
        self.actions = []
        header = ttk.Frame(self.root, style='Header.TFrame', padding=(22, 16))
        header.pack(fill='x')
        ttk.Label(header, text='KarelToPython', style='Brand.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(header, text='A workspace for translating KAREL into Python', style='Header.TLabel').grid(row=1, column=0, sticky='w', pady=(3, 0))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text='Build ' + __version__, style='Build.TLabel').grid(row=0, column=1, rowspan=2, sticky='e')
        toolbar = ttk.Frame(self.root, padding=(20, 14, 20, 8))
        toolbar.pack(fill='x')
        self._button(toolbar, 'Open KAREL…', self.open_file).pack(side='left')
        self._button(toolbar, 'New', self.new).pack(side='left', padx=(6, 0))
        self._button(toolbar, 'Save source as…', self.save_source).pack(side='left', padx=6)
        self._button(toolbar, 'Check project…', self.check_project).pack(side='left')
        self.translate_button = self._button(toolbar, 'Translate to Python', lambda: self.start(True), style='Primary.TButton')
        self.translate_button.pack(side='right')
        self._button(toolbar, 'Validate', lambda: self.start(False)).pack(side='right', padx=8)
        options = ttk.Frame(self.root, padding=(22, 0, 22, 10))
        options.pack(fill='x')
        ttk.Label(options, text='Mode: Pythonic', foreground='#087f73').pack(side='left', padx=(0, 22))
        self.cooperative_check = ttk.Checkbutton(options, text='Enable pause / resume', variable=self.cooperative)
        self.cooperative_check.pack(side='left', padx=(0, 22))
        ttk.Label(options, text='ARRAY sizes').pack(side='left', padx=(0, 8))
        self.shape_entry = ttk.Entry(options, textvariable=self.shapes, width=26)
        self.shape_entry.pack(side='left')
        ttk.Label(options, text=' e.g. DATA=3,4; FLAGS=8', style='Muted.TLabel').pack(side='left')
        panes = ttk.Panedwindow(self.root, orient='horizontal')
        panes.pack(fill='both', expand=True, padx=20, pady=(0, 10))
        left = ttk.Frame(panes)
        panes.add(left, weight=1)
        ttk.Label(left, text='KAREL SOURCE', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 7))
        ttk.Label(left, textvariable=self.path_label, style='Muted.TLabel', wraplength=560).pack(anchor='w', pady=(0, 9))
        self.source = self._text(left, editable=True)
        self.source.bind('<<Modified>>', self._modified)
        self.source.bind('<KeyRelease>', self._cursor, add=True)
        self.source.bind('<ButtonRelease-1>', self._cursor, add=True)
        self.source.tag_configure('diagnostic', background='#783b41')
        right = ttk.Frame(panes)
        panes.add(right, weight=1)
        result_bar = ttk.Frame(right)
        result_bar.pack(fill='x', pady=(0, 7))
        ttk.Label(result_bar, text='RESULTS', font=('Segoe UI', 10, 'bold')).pack(side='left')
        self.python_save = ttk.Button(result_bar, text='Save Python…', command=lambda: self.export('python'))
        self.python_save.pack(side='right')
        self.report_save = ttk.Button(result_bar, text='Save report…', command=lambda: self.export('report'))
        self.report_save.pack(side='right', padx=6)
        self.copy_button = ttk.Button(result_bar, text='Copy Python', command=self.copy_python)
        self.copy_button.pack(side='right')
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill='both', expand=True)
        self.python_page = ttk.Frame(self.tabs)
        self.diagnostic_page = ttk.Frame(self.tabs)
        self.report_page = ttk.Frame(self.tabs)
        self.tabs.add(self.python_page, text='Python')
        self.tabs.add(self.diagnostic_page, text='Diagnostics')
        self.tabs.add(self.report_page, text='Report')
        self.python = self._text(self.python_page)
        self.report = self._text(self.report_page)
        self.diagnostic_summary = tk.StringVar(value='Validate or translate to review diagnostics.')
        ttk.Label(self.diagnostic_page, textvariable=self.diagnostic_summary, wraplength=520, padding=12).pack(fill='x')
        self.diagnostics = ttk.Treeview(self.diagnostic_page, columns=('line', 'code', 'message'), show='headings', selectmode='browse')
        for name, text, width in (('line', 'Line:col', 70), ('code', 'Code', 115), ('message', 'Message', 340)):
            self.diagnostics.heading(name, text=text)
            self.diagnostics.column(name, width=width, minwidth=45, stretch=name == 'message')
        scroll = ttk.Scrollbar(self.diagnostic_page, orient='vertical', command=self.diagnostics.yview)
        scroll.pack(side='right', fill='y')
        self.diagnostics.configure(yscrollcommand=scroll.set)
        self.diagnostics.pack(fill='both', expand=True)
        self.diagnostics.bind('<Double-1>', self.go_to_diagnostic)
        footer = ttk.Frame(self.root, padding=(22, 0, 22, 12))
        footer.pack(fill='x')
        ttk.Label(footer, textvariable=self.status, wraplength=1050).pack(side='left')
        self.progress = ttk.Progressbar(footer, mode='indeterminate', length=130)
        self.progress.pack(side='right')
        self._set_text(self.python, '# Generated Python will appear here after translation.\n')
        self._exports()

    def _text(self, parent, editable=False):
        frame = self.ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        text = self.tk.Text(frame, wrap='none', undo=editable, font=('Consolas', 11),
                            background='#142237', foreground='#dce7f5', insertbackground='#ffffff',
                            selectbackground='#315678', relief='flat', padx=14, pady=12, borderwidth=0,
                            tabs=('4c',), highlightthickness=0)
        vertical = self.ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        horizontal = self.ttk.Scrollbar(frame, orient='horizontal', command=text.xview)
        text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        if not editable: text.configure(state='disabled')
        return text

    def _menu(self):
        menu = self.tk.Menu(self.root)
        file = self.tk.Menu(menu, tearoff=False)
        self.file_menu = file
        for label, command, shortcut in (
            ('New', self.new, 'Ctrl+N'), ('Open KAREL…', self.open_file, 'Ctrl+O'),
            ('Save source as…', self.save_source, 'Ctrl+S'), ('Check linked project…', self.check_project, ''),
            ('Save generated Python…', lambda: self.export('python'), ''), ('Save report…', lambda: self.export('report'), '')):
            file.add_command(label=label, command=command, accelerator=shortcut)
        file.add_separator()
        file.add_command(label='Exit', command=self.close)
        menu.add_cascade(label='File', menu=file)
        edit = self.tk.Menu(menu, tearoff=False)
        for label, event in (('Undo', '<<Undo>>'), ('Redo', '<<Redo>>'), ('Cut', '<<Cut>>'), ('Copy', '<<Copy>>'), ('Paste', '<<Paste>>'), ('Select all', '<<SelectAll>>')):
            edit.add_command(label=label, command=lambda value=event: self._edit(value))
        menu.add_cascade(label='Edit', menu=edit)
        help_menu = self.tk.Menu(menu, tearoff=False)
        help_menu.add_command(label='About KarelToPython', command=self.about)
        menu.add_cascade(label='Help', menu=help_menu)
        self.root.configure(menu=menu)
        for binding, command in (('<Control-o>', self.open_file), ('<Control-n>', self.new), ('<Control-s>', self.save_source), ('<Control-Return>', lambda: self.start(True)), ('<F5>', lambda: self.start(False))):
            self.root.bind(binding, lambda event, action=command: self._shortcut(action))

    def _shortcut(self, command):
        if not self.busy: command()
        return 'break'

    def _edit(self, event):
        widget = self.root.focus_get()
        if widget is not None:
            try: widget.event_generate(event)
            except self.tk.TclError: pass

    def _set_text(self, widget, text):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('1.0', text)
        widget.configure(state='disabled')

    def _title(self):
        name = self.document.path.name if self.document.path else 'Untitled'
        self.root.title(f'KarelToPython {__version__} - {name}' + (' *' if self.document.dirty else ''))

    def _cursor(self, event=None):
        self.source.tag_remove('diagnostic', '1.0', 'end')

    def _modified(self, event=None):
        if not self.source.edit_modified(): return
        self.source.edit_modified(False)
        self.document.text = self.source.get('1.0', 'end-1c')
        self.invalidate()
        self._title()

    def invalidate(self):
        self.revision += 1
        self.analysis = None
        self._set_text(self.python, '# Source or options changed. Translate to refresh this preview.\n')
        self._set_text(self.report, '')
        self.diagnostics.delete(*self.diagnostics.get_children())
        self._diagnostics.clear()
        self.diagnostic_summary.set('Validate or translate to review the current source.')
        self.status.set('Source or options changed. Ready to validate or translate.')
        self._exports()

    def _exports(self):
        python = self.analysis is not None and self.analysis.python_source is not None and not self.busy
        report = self.analysis is not None and not self.busy
        for widget in (self.python_save, self.copy_button): widget.configure(state='normal' if python else 'disabled')
        self.report_save.configure(state='normal' if report else 'disabled')
        if hasattr(self, 'file_menu'):
            self.file_menu.entryconfigure(4, state='normal' if python else 'disabled')
            self.file_menu.entryconfigure(5, state='normal' if report else 'disabled')

    def _discard(self):
        self._sync_document()
        if not self.document.dirty: return True
        choice = self.message.askyesnocancel('Unsaved source', 'Save the source edits before continuing?', parent=self.root)
        if choice is None: return False
        return self.save_source() if choice else True

    def set_document(self, document):
        self.document = document
        self.source.delete('1.0', 'end')
        self.source.insert('1.0', document.text)
        self.source.edit_reset()
        self.source.edit_modified(False)
        self.path_label.set(str(document.path) if document.path else 'Untitled source')
        self.invalidate()
        self._title()

    def new(self):
        if not self.busy and self._discard(): self.set_document(Document())

    def open_file(self, path=None):
        if self.busy or not self._discard(): return
        if path is None:
            path = self.dialog.askopenfilename(title='Open KAREL source', filetypes=[('KAREL source', '*.kl *.KL'), ('All files', '*')], parent=self.root)
        if not path: return
        try: document = Document.open(path)
        except (OSError, UnicodeError, ValueError) as exc:
            self.message.showerror('Unable to open source', str(exc), parent=self.root)
            return
        self.set_document(document)
        self.status.set('Source loaded. Validate or translate when ready.')

    def _save_path(self, title, suffix, initial):
        path = self.dialog.asksaveasfilename(title=title, defaultextension=suffix, initialfile=initial,
                                           filetypes=[(suffix[1:].upper() + ' files', '*' + suffix), ('All files', '*')],
                                           confirmoverwrite=False, parent=self.root)
        if not path: return None
        path = Path(path)
        if path.exists() and not self.message.askyesno('Replace file?', f'Replace this file?\n\n{path}', parent=self.root): return None
        return path

    def save_source(self):
        if self.busy: return False
        self._sync_document()
        path = self._save_path('Save KAREL source', '.kl', self.document.path.name if self.document.path else 'source.kl')
        if path is None: return False
        try: self.document.save(path, overwrite=path.exists())
        except (OSError, UnicodeError, ValueError) as exc:
            self.message.showerror('Unable to save source', str(exc), parent=self.root)
            return False
        self.path_label.set(str(self.document.path))
        self.invalidate()  # Filename/source-map identity changes even without edits.
        self._title()
        self.status.set('KAREL source saved.')
        return True

    def _set_busy(self, value):
        self.busy = value
        for widget in self.actions: widget.configure(state='disabled' if value else 'normal')
        self.source.configure(state='disabled' if value else 'normal')
        self.shape_entry.configure(state='disabled' if value else 'normal')
        self.cooperative_check.configure(state='disabled' if value else 'normal')
        for index in range(4): self.file_menu.entryconfigure(index, state='disabled' if value else 'normal')
        self.progress.start(12) if value else self.progress.stop()
        self._exports()

    def start(self, emit=True):
        if self.busy: return
        self._sync_document()
        source, filename = self.document.text, str(self.document.path) if self.document.path else '<untitled>'
        shapes, cooperative = self.shapes.get(), self.cooperative.get()
        self._start(lambda: analyze_source(source, filename=filename, shapes=shapes, cooperative=cooperative, emit=emit),
                    'Translating source…' if emit else 'Validating source…')

    def _sync_document(self):
        current = self.source.get('1.0', 'end-1c')
        if current != self.document.text:
            self.document.text = current
            self.invalidate()
            self._title()

    def check_project(self):
        if self.busy: return
        directory = self.dialog.askdirectory(title='Select a linked KAREL project folder', parent=self.root)
        if not directory: return
        shapes = self.shapes.get()
        self._start(lambda: analyze_project(directory, shapes=shapes), 'Checking linked project…')

    def _start(self, operation, message):
        self.invalidate()
        revision = self.revision
        self._set_busy(True)
        self.status.set(message)
        def worker():
            try: result = operation()
            except Exception as exc: result = exc
            self._queue.put((revision, result))
        threading.Thread(target=worker, name='karel2py-translation', daemon=True).start()
        self._poll = self.root.after(50, self._receive)

    def _receive(self):
        self._poll = None
        if self.closed: return
        try: revision, result = self._queue.get_nowait()
        except queue.Empty:
            self._poll = self.root.after(50, self._receive)
            return
        self._set_busy(False)
        if revision != self.revision:
            self.status.set('Source or options changed; run the operation again.')
            return
        if isinstance(result, Exception):
            self.invalidate()
            self.status.set('Unable to complete the operation.')
            self.message.showerror('Operation failed', str(result), parent=self.root)
            return
        self.show_analysis(result)

    def show_analysis(self, result):
        if self.document.path is not None: result.protected = (*result.protected, self.document.path)
        self.analysis = result
        self._set_text(self.python, result.python_source or '# No Python output. Translate a single source to generate Python.\n')
        self._set_text(self.report, result.report_text())
        self.diagnostics.delete(*self.diagnostics.get_children())
        self._diagnostics.clear()
        for diagnostic in result.diagnostics:
            location = f'{diagnostic.get("line", "")}:{diagnostic.get("column", "")}'
            message = diagnostic.get('message', '')
            if diagnostic.get('file') not in (str(self.document.path), '<untitled>'):
                message = Path(diagnostic.get('file', '')).name + ': ' + message
            item = self.diagnostics.insert('', 'end', values=(location, diagnostic.get('code', ''), message))
            self._diagnostics[item] = diagnostic
        if result.accepted:
            if 'programs' in result.report: summary = f'Linked project checked: {len(result.report["programs"])} programs. No program bodies executed.'
            else: summary = result.report['program'] + (': translated to Python.' if result.python_source is not None else ': validation passed.')
            self.diagnostic_summary.set('No translation errors. ' + summary)
            self.status.set(summary)
            self.tabs.select(self.python_page if result.python_source is not None else self.report_page)
        else:
            self.diagnostic_summary.set('Translation rejected. Double-click a diagnostic to jump to its source line.')
            self.status.set('Translation rejected. Review diagnostics; no Python output was produced.')
            self.tabs.select(self.diagnostic_page)
        self._exports()

    def go_to_diagnostic(self, event=None):
        selected = self.diagnostics.selection()
        if not selected: return
        diagnostic = self._diagnostics[selected[0]]
        if diagnostic.get('file') not in (str(self.document.path), '<untitled>'):
            path = Path(diagnostic.get('file', ''))
            if not path.is_file() or path.suffix.lower() != '.kl': return
            self.open_file(path)
            if self.document.path != path.resolve(): return
        line, column = diagnostic.get('line', 1), diagnostic.get('column', 1)
        location = f'{line}.{max(column - 1, 0)}'
        self.source.focus_set()
        self.source.mark_set('insert', location)
        self.source.see(location)
        self.source.tag_remove('diagnostic', '1.0', 'end')
        self.source.tag_add('diagnostic', f'{line}.0', f'{line}.end')

    def export(self, kind):
        self._sync_document()
        if self.busy or self.analysis is None: return
        if kind == 'python' and self.analysis.python_source is None: return
        stem = self.document.path.stem if self.document.path else 'converted'
        suffix = '.py' if kind == 'python' else '.json'
        path = self._save_path('Save generated Python' if kind == 'python' else 'Save translation report', suffix, stem + suffix)
        if path is None: return
        try: self.analysis.export(path, kind, overwrite=path.exists())
        except (OSError, UnicodeError, ValueError) as exc:
            self.message.showerror('Unable to export', str(exc), parent=self.root)
            return
        self.status.set('Saved ' + str(path))

    def copy_python(self):
        self._sync_document()
        if self.busy or self.analysis is None or self.analysis.python_source is None: return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.analysis.python_source)
        self.status.set('Generated Python copied to the clipboard.')

    def about(self):
        self.message.showinfo('About KarelToPython', f'KarelToPython {__version__}\n\nKAREL-to-Python offline translator.\nPythonic mode; strict mode is a future milestone.\n\nValidate and translate without running source programs.\nhttps://github.com/votecoffee/KarelToPython', parent=self.root)

    def close(self):
        if self.busy:
            if not self.message.askyesno('Operation in progress', 'An operation is still running. Close the window?', parent=self.root): return
            # Saving is unavailable until a worker finishes, so do not offer it here.
            if self.document.dirty and not self.message.askyesno('Unsaved source', 'Discard unsaved source edits and close?', parent=self.root): return
        elif not self._discard(): return
        self.closed = True
        if self._poll is not None: self.root.after_cancel(self._poll)
        self.progress.stop()
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description=f'KarelToPython {__version__} desktop workbench')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('source', nargs='?', type=Path, help='Optional KAREL source to open')
    args = parser.parse_args(argv)
    try:
        import tkinter as tk
        root = tk.Tk()
    except (ImportError, RuntimeError) as exc:
        print('Unable to start the GUI: ' + str(exc) + '. Install Python with Tcl/Tk support.', file=sys.stderr)
        return 1
    except Exception as exc:
        print('Unable to start the GUI: ' + str(exc), file=sys.stderr)
        return 1
    application = Workbench(root)
    if args.source: root.after(0, lambda: application.open_file(args.source))
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
