"""Desktop editor for the standalone Pythonic run-document workflow."""
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from . import runner


class RunWindow:
    def __init__(self, parent, *, protected=()):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.dialog = filedialog
        self.message = messagebox
        self.window = tk.Toplevel(parent)
        self.window.title('Run generated Python')
        self.window.transient(parent)
        self.window.minsize(750, 480)
        self.window.geometry('920x660')
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.protected = protected
        self.path = self.document = self.revision = None
        self.busy = False
        self.closed = False
        self.cancel_event = None
        self.status = tk.StringVar(self.window, value='Create a run from generated Python or open a saved run.')
        self.location = tk.StringVar(self.window)
        self.detail = tk.StringVar(self.window)

        toolbar = ttk.Frame(self.window, padding=8)
        toolbar.pack(fill='x')
        self.buttons = {}
        for label, command in (('New from Python…', self.new), ('Open run…', self.open),
                               ('Rediscover…', self.refresh), ('Save inputs', self.save),
                               ('Run', self.run), ('Cancel run', self.cancel)):
            button = ttk.Button(toolbar, text=label, command=command, style='Compact.TButton')
            button.pack(side='left', padx=(0, 5))
            self.buttons[label] = button
        ttk.Label(self.window, textvariable=self.location, padding=(10, 0, 10, 6), wraplength=735).pack(anchor='w')
        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill='both', expand=True, padx=8)
        inputs = ttk.Frame(self.tabs, padding=8)
        edits = ttk.Frame(self.tabs, padding=8)
        discovery = ttk.Frame(self.tabs, padding=8)
        self.results_page = ttk.Frame(self.tabs, padding=8)
        output_page = ttk.Frame(self.tabs, padding=8)
        for label, page in (('Discovered inputs', inputs), ('Edit context', edits),
                            ('Requirements', discovery), ('Last result', self.results_page), ('WRITE output', output_page)):
            self.tabs.add(page, text=label)
        columns = ('kind', 'path', 'certainty', 'status')
        self.inputs = ttk.Treeview(inputs, columns=columns, show='headings', selectmode='browse')
        for column, width in zip(columns, (125, 265, 95, 90)):
            self.inputs.heading(column, text=column.capitalize())
            self.inputs.column(column, width=width, stretch=column == 'path')
        scroll = ttk.Scrollbar(inputs, command=self.inputs.yview)
        scroll.pack(side='right', fill='y')
        self.inputs.configure(yscrollcommand=scroll.set)
        self.inputs.pack(fill='both', expand=True)
        self.inputs.bind('<<TreeviewSelect>>', self._select_input)
        ttk.Label(inputs, textvariable=self.detail, wraplength=700, padding=(0, 8)).pack(fill='x')
        ttk.Label(edits, text='Edit initial values and offline service configuration as JSON, then save inputs.').pack(anchor='w')
        self.context = self._text(edits, tk, ttk)
        self.requirements = self._text(discovery, tk, ttk)
        self.result = self._text(self.results_page, tk, ttk)
        self.output = self._text(output_page, tk, ttk)
        ttk.Label(self.window, textvariable=self.status, padding=8, wraplength=735).pack(anchor='w')
        self._configure()

    @staticmethod
    def _text(parent, tk, ttk):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        box = tk.Text(frame, wrap='word', font='TkFixedFont', undo=True)
        scroll = ttk.Scrollbar(frame, command=box.yview)
        scroll.pack(side='right', fill='y')
        box.configure(yscrollcommand=scroll.set)
        box.pack(fill='both', expand=True)
        return box

    @staticmethod
    def _display(widget, value, *, editable=False):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('1.0', value)
        widget.edit_reset()
        widget.edit_modified(False)
        if not editable:
            widget.configure(state='disabled')

    @staticmethod
    def _json(value):
        return json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + '\n'

    def _configure(self):
        loaded = self.document is not None
        interrupted = loaded and (self.document['results'] or {}).get('status') == 'running'
        editable = loaded and not interrupted and not self.busy
        for label in ('New from Python…', 'Open run…'):
            self.buttons[label].configure(state='disabled' if self.busy else 'normal')
        for label in ('Rediscover…', 'Save inputs', 'Run'):
            self.buttons[label].configure(state='normal' if editable else 'disabled')
        can_cancel = self.cancel_event is not None and not self.cancel_event.is_set()
        self.buttons['Cancel run'].configure(state='normal' if can_cancel else 'disabled')
        self.context.configure(state='normal' if editable else 'disabled')

    def _select_input(self, _event=None):
        selection = self.inputs.selection()
        if not selection or self.document is None:
            self.detail.set('')
            return
        template = self.document['inputs']['template']
        binding = template['bindings'][int(selection[0])]
        candidates = template['discovery'].get('inputs')
        candidate = next((row for row in candidates if isinstance(row, dict) and
                          all(row.get(key) == binding.get(key) for key in ('kind', 'program', 'path'))), {}) if isinstance(candidates, list) else {}
        locations = candidate.get('locations')
        sources = [f"{row.get('file')}:{row.get('line')}:{row.get('column')}"
                   for row in locations[:5] if isinstance(row, dict)] if isinstance(locations, list) else []
        type_text = self._json(candidate.get('type') or candidate.get('type_options')).strip()
        pointer = str(binding.get('context_pointer') or 'unmapped')
        parts = binding.get('selectors')
        selectors = ', '.join(str(part[1]) for part in parts if isinstance(part, list) and len(part) == 2) if isinstance(parts, list) else ''
        if selectors:
            pointer += f' (selected field or index: {selectors})'
        self.detail.set(f"{candidate.get('reason', '')}\nType {type_text}\nContext {pointer}\n" + '\n'.join(sources))

    def _show(self, path, document, revision):
        self.path, self.document, self.revision = path, document, revision
        self.location.set(f"{document['target']['program']}  ·  {path}\nPython  {document['target']['path']}")
        inputs = document['inputs']
        template = inputs.get('template', {})
        self.inputs.delete(*self.inputs.get_children())
        self.detail.set('')
        for index, row in enumerate(template.get('bindings', ())):
            self.inputs.insert('', 'end', iid=str(index), values=tuple(str(row.get(key, '')) for key in ('kind', 'path', 'certainty', 'status')))
        self._display(self.context, self._json(inputs['context']), editable=True)
        self._display(self.requirements, self._json({
            'requirements': template.get('requirements', []),
            'unresolved': template.get('discovery', {}).get('unresolved', []),
            **({'refresh': template['refresh']} if 'refresh' in template else {}),
        }) if template else 'Use Rediscover to prepare input annotations for this document.')
        result = document['results']
        self._display(self.result, 'Run the program to see its results.' if result is None else self._json(result))
        self._display(self.output, str((result or {}).get('text_output') or 'No WRITE output.'))
        self._configure()
        if result and result.get('status') == 'running':
            self.status.set('This document contains an active or interrupted run. Reopen it after resolving that run.')

    def _discard_edits(self):
        return not self.context.edit_modified() or self.message.askyesno(
            'Discard input edits?', 'The context has unsaved edits.', parent=self.window)

    def _pick_python(self):
        value = self.dialog.askopenfilename(parent=self.window, title='Select generated Python', filetypes=[('Python', '*.py')])
        return Path(value).absolute() if value else None

    def _destination(self, stem):
        value = self.dialog.asksaveasfilename(parent=self.window, title='Save new run document',
            initialfile=stem + '.run.json', defaultextension='.json', filetypes=[('Run JSON', '*.json')])
        return Path(value).absolute() if value else None

    def _start(self, message, action, *, cancel_event=None, show_results=False):
        if self.busy:
            return
        queue = Queue()
        self.busy = True
        self.cancel_event = cancel_event
        self.status.set(message)
        self._configure()

        def worker():
            try:
                queue.put(action())
            except Exception as error:
                queue.put(error)

        def receive():
            try:
                outcome = queue.get_nowait()
            except Empty:
                self.window.after(50, receive)
                return
            self.busy = False
            self.cancel_event = None
            self._configure()
            if isinstance(outcome, Exception):
                self.status.set(str(outcome))
                self.message.showerror('Run document operation failed', str(outcome), parent=self.window)
                return
            self.status.set('Run document ready.')
            self._show(*outcome)
            if show_results:
                self.tabs.select(self.results_page)
                self.status.set('Run ' + self.document['results']['status'] + '.')

        Thread(target=worker, name='karel2py-run-document').start()
        self.window.after(50, receive)

    def new(self):
        if self.busy or not self._discard_edits():
            return
        target = self._pick_python()
        if target is None:
            return
        path = self._destination(target.stem)
        if path is None:
            return
        protected = self.protected

        def create():
            runner.create_document(target, path, discover=True, protected=protected)
            return path, *runner.read_document(path)

        self._start('Discovering inputs…', create)

    def open(self):
        if self.busy or not self._discard_edits():
            return
        value = self.dialog.askopenfilename(parent=self.window, title='Open saved run', filetypes=[('Run JSON', '*.json')])
        if value:
            path = Path(value).absolute()
            self._start('Opening run…', lambda: (path, *runner.read_document(path)))

    def refresh(self):
        if self.busy or self.path is None or not self._discard_edits():
            return
        target = self._pick_python()
        if target is None:
            return
        path = self._destination(target.stem)
        if path is None:
            return
        source, revision, protected = self.path, self.revision, self.protected

        def refresh():
            runner.refresh_document(source, path, target=target, expected=revision, protected=protected)
            return path, *runner.read_document(path)

        self._start('Rediscovering into a new document…', refresh)

    def save(self):
        if self.busy or self.path is None:
            return
        path, revision, protected = self.path, self.revision, self.protected
        text = self.context.get('1.0', 'end-1c')
        self._start('Validating and saving inputs…',
                    lambda: (path, *runner.save_context(path, text, expected=revision, protected=protected)))

    def run(self):
        if self.busy or self.path is None:
            return
        if self.context.edit_modified():
            self.status.set('Save your input edits before running.')
            return
        if not self.message.askyesno('Run generated Python?', 'Run only Python you trust. Continue with the saved inputs?', parent=self.window):
            return
        path, revision, protected = self.path, self.revision, self.protected
        cancel_event = Event()

        def execute():
            runner.run_document(path, expected=revision, cancel_event=cancel_event, protected=protected)
            return path, *runner.read_document(path)

        self._start('Running Python…', execute, cancel_event=cancel_event, show_results=True)

    def cancel(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.status.set('Cancelling at the next execution checkpoint…')
            self._configure()

    def close(self):
        if self.busy:
            self.cancel()
            return False
        if not self._discard_edits():
            return False
        self.closed = True
        self.window.destroy()
        return True
