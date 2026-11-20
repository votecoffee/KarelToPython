"""Desktop editor for standalone and linked Pythonic run documents."""
from copy import deepcopy
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

from . import runner
from .gui_project_run import select_linked_modules
from .gui_structured_inputs import prompt_structure
from .runner_values import input_key, scalar_options, scalar_slot
from .structured_inputs import structured_slot, supports_structure


def _prompt_value(parent, path, slot):
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk

    class ValueDialog(simpledialog.Dialog):
        def body(self, frame):
            value = slot.value
            default = 'REAL' if type(value) is float and 'REAL' in slot.options else slot.options[0]
            self.kind = tk.StringVar(frame, value=default)
            self.text = tk.StringVar(frame, value='' if value is None else value if isinstance(value, str) else json.dumps(value))
            ttk.Label(frame, text=path).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))
            if len(slot.options) > 1:
                kind_widget = ttk.Combobox(frame, textvariable=self.kind, values=slot.options, width=12, state='readonly')
            else:
                kind_widget = ttk.Label(frame, text=default)
            kind_widget.grid(row=1, column=0, sticky='w', padx=(0, 8))
            if default == 'BOOLEAN':
                field = ttk.Combobox(frame, textvariable=self.text, values=('false', 'true'), width=38, state='readonly')
            else:
                field = ttk.Entry(frame, textvariable=self.text, width=40)
            field.grid(row=1, column=1, sticky='ew')
            if slot.capacity is not None:
                ttk.Label(frame, text=f'Up to {slot.capacity} ASCII characters').grid(row=2, column=1, sticky='w')
            return field

        def validate(self):
            try:
                slot.set_text(self.kind.get(), self.text.get())
            except ValueError as error:
                messagebox.showerror('Invalid value', str(error), parent=self)
                return False
            return True

        def apply(self):
            self.result = self.kind.get(), self.text.get()

    return ValueDialog(parent, title='Edit input value').result


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
        for label, command in (('New from Python…', self.new), ('New linked…', self.new_linked),
                               ('Open run…', self.open),
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
        self.inputs_page, self.edits_page, self.requirements_page = inputs, edits, discovery
        self.linked_discovery_page = ttk.Frame(self.tabs, padding=8)
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
        self.inputs.bind('<Double-1>', self._activate_input)
        self.inputs.bind('<Return>', self._activate_input)
        self.edit_value = ttk.Button(inputs, text='Edit value…', command=self.edit_selected, style='Compact.TButton')
        self.edit_value.pack(anchor='w', pady=(8, 0))
        ttk.Label(inputs, textvariable=self.detail, wraplength=700, padding=(0, 8)).pack(fill='x')
        self.context_help = ttk.Label(edits, wraplength=700)
        self.context_help.pack(anchor='w', pady=(0, 6))
        self.context = self._text(edits, tk, ttk)
        self.requirements = self._text(discovery, tk, ttk)
        self.linked_discovery = self._text(self.linked_discovery_page, tk, ttk)
        self.result_filter = ttk.Frame(self.results_page)
        ttk.Label(self.result_filter, text='Program').pack(side='left', padx=(0, 6))
        self.result_program = ttk.Combobox(self.result_filter, state='readonly', width=24)
        self.result_program.pack(side='left')
        self.result_program.bind('<<ComboboxSelected>>', self._show_result)
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

    def _linked(self):
        return self.document is not None and self.document['schema'] == runner.PROJECT_SCHEMA

    def _configure(self):
        loaded = self.document is not None
        interrupted = loaded and (self.document['results'] or {}).get('status') == 'running'
        editable = loaded and not interrupted and not self.busy
        for label in ('New from Python…', 'New linked…', 'Open run…'):
            self.buttons[label].configure(state='disabled' if self.busy else 'normal')
        linked = self._linked()
        refresh_label = 'Rediscover…'
        if linked:
            refresh_label = 'Discover inputs…' if interrupted else 'Prepare inputs…'
        self.buttons['Rediscover…'].configure(
            text=refresh_label,
            state='normal' if editable or (linked and not self.busy) else 'disabled')
        for label in ('Save inputs', 'Run'):
            self.buttons[label].configure(state='normal' if editable else 'disabled')
        can_cancel = self.cancel_event is not None and not self.cancel_event.is_set()
        self.buttons['Cancel run'].configure(state='normal' if can_cancel else 'disabled')
        self.context.configure(state='normal' if editable else 'disabled')
        self._configure_value_editor(editable)

    def _selected_rows(self):
        selection = self.inputs.selection()
        if not selection or self.document is None or 'template' not in self.document['inputs']:
            return {}, {}
        template = self.document['inputs']['template']
        binding = template['bindings'][int(selection[0])]
        candidates = template['discovery'].get('inputs')
        candidate = next((row for row in candidates if isinstance(row, dict) and
                          input_key(row) == input_key(binding)), {}) if isinstance(candidates, list) else {}
        return candidate, binding

    def _configure_value_editor(self, editable):
        candidate, binding = self._selected_rows()
        structure = supports_structure(candidate)
        available = (editable and (scalar_options(candidate) or structure) and binding.get('context_pointer')
                     and binding.get('status') != 'unmapped')
        self.edit_value.configure(text='Edit fields…' if structure else 'Edit value…',
                                  state='normal' if available else 'disabled')

    def _select_input(self, _event=None):
        self._configure()
        candidate, binding = self._selected_rows()
        if not binding:
            self.detail.set('')
            return
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

    def _activate_input(self, event):
        if event.keysym != 'Return':
            row = self.inputs.identify_row(event.y)
            if not row:
                return
            self.inputs.selection_set(row)
            self._select_input()
        self.edit_selected()

    def _input_label(self, binding):
        path = str(binding.get('path', ''))
        program = binding.get('program')
        return f'{program}.{path}' if self._linked() and program else path

    def edit_selected(self):
        if str(self.edit_value['state']) != 'normal':
            return
        if self.context.edit_modified():
            self.status.set('Save your context edits before changing a selected value.')
            return
        candidate, binding = self._selected_rows()
        try:
            context = deepcopy(self.document['inputs']['context'])
            label = self._input_label(binding)
            if supports_structure(candidate):
                draft = structured_slot(context, candidate, binding).draft(label)
                payload = prompt_structure(self.window, label, draft, _prompt_value)
                changes = (payload,) if payload is not None else None
                save = runner.save_input_structure
            else:
                slot = scalar_slot(context, candidate, binding)
                changes = _prompt_value(self.window, label, slot)
                save = runner.save_input_value
        except (ValueError, OSError) as error:
            self.message.showerror('Unable to edit input', str(error), parent=self.window)
            return
        if changes is None:
            return
        path, revision, protected = self.path, self.revision, self.protected
        selected = input_key(candidate)
        self._start('Validating and saving the selected input…', lambda: (path, *save(
            path, selected, *changes, expected=revision, protected=protected)))

    def _show_inputs(self, target, path, template):
        self.inputs.delete(*self.inputs.get_children())
        self.detail.set('')
        requirements = {}
        if self._linked():
            modules = target['modules']
            self.location.set(f"Entry {target['program']}  ·  {len(modules)} pinned modules\n{path}")
            if not template:
                self.tabs.hide(self.inputs_page)
                self.tabs.tab(self.requirements_page, text='Pinned modules')
                self._display(self.requirements, self._json(modules))
                return
            requirements['modules'] = modules
            self.tabs.add(self.linked_discovery_page, text='Discovery report')
            self._display(self.linked_discovery, self._json(template['discovery']))
        else:
            self.location.set(f"{target['program']}  ·  {path}\nPython  {target['path']}")

        self.tabs.add(self.inputs_page)
        self.tabs.tab(self.requirements_page, text='Requirements')
        for index, row in enumerate(template.get('bindings', ())):
            self.inputs.insert('', 'end', iid=str(index),
                               values=(str(row.get('kind', '')), self._input_label(row),
                                       str(row.get('certainty', '')), str(row.get('status', ''))))
        requirements.update(
            requirements=template.get('requirements', []),
            unresolved=template.get('discovery', {}).get('unresolved', []),
        )
        if 'refresh' in template:
            requirements['refresh'] = template['refresh']
        self._display(self.requirements, self._json(requirements) if template else
                      'Use Rediscover to prepare input annotations for this document.')

    def _show_result(self, _event=None):
        result = self.document['results']
        if result is None:
            text = 'Run the program to see its results.'
        elif self._linked() and self.result_program.current() > 0:
            text = self._json(result['programs'][self.result_program.get()])
        else:
            text = self._json(result)
        self._display(self.result, text)

    def _show(self, path, document, revision):
        same_document = (self.document is not None and self.path == path and
                         self.document['schema'] == document['schema'])
        previous_program = self.result_program.get() if same_document else ''
        if (not same_document or self.revision != revision) and str(self.linked_discovery_page) in self.tabs.tabs():
            self.tabs.forget(self.linked_discovery_page)
        self.path, self.document, self.revision = path, document, revision
        inputs = document['inputs']
        self._show_inputs(document['target'], path, inputs.get('template', {}))
        help_text = 'Edit initial values and offline service configuration as JSON, then save inputs.'
        if self._linked():
            help_text += ' Set program on variable entries to identify the owning module.'
        self.context_help.configure(text=help_text)
        self._display(self.context, self._json(inputs['context']), editable=True)
        if not same_document:
            page = self.edits_page if self._linked() and 'template' not in inputs else self.inputs_page
            self.tabs.select(page)
        result = document['results']
        snapshots = (result or {}).get('programs')
        programs = ()
        if self._linked() and isinstance(snapshots, dict):
            programs = tuple(row['program'] for row in document['target']['modules'] if row['program'] in snapshots)
        if programs:
            choices = ('All results', *programs)
            self.result_program.configure(values=choices)
            self.result_program.current(choices.index(previous_program) if previous_program in choices else 0)
            self.result_filter.pack(fill='x', pady=(0, 6), before=self.result.master)
        else:
            self.result_program.set('')
            self.result_filter.pack_forget()
        self._show_result()
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

    def _start(self, message, action, *, cancel_event=None, show_results=False, on_success=None):
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

        Thread(target=worker, name='karel2py-run-document').start()
        self.window.after(50, self._receive, queue, show_results, on_success)

    def _receive(self, queue, show_results, on_success):
        try:
            outcome = queue.get_nowait()
        except Empty:
            self.window.after(50, self._receive, queue, show_results, on_success)
            return
        self.busy = False
        self.cancel_event = None
        self._configure()
        if isinstance(outcome, Exception):
            self.status.set(str(outcome))
            self.message.showerror('Run document operation failed', str(outcome), parent=self.window)
            return
        if on_success is not None:
            on_success(outcome)
            return
        self.status.set('Run document ready.')
        self._show(*outcome)
        if show_results:
            self.tabs.select(self.results_page)
            self.status.set('Run ' + self.document['results']['status'] + '.')

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

    def new_linked(self):
        from .project_run import inspect_project_modules

        if self.busy or not self._discard_edits():
            return
        paths = self.dialog.askopenfilenames(
            parent=self.window, title='Select cooperative generated Python', filetypes=[('Python', '*.py')])
        if paths:
            self._start('Inspecting linked modules…', lambda: inspect_project_modules(paths),
                        on_success=self._save_new_linked)

    def _save_new_linked(self, modules):
        from .project_run import create_project_document

        selection = select_linked_modules(self.window, modules)
        if selection is None:
            self.status.set('Linked run creation cancelled.')
            return
        entry, ordered = selection
        path = self._destination(entry.lower() + '.linked')
        if path is None:
            self.status.set('Linked run creation cancelled.')
            return
        protected = self.protected

        def create():
            create_project_document([pin.path for pin in ordered], path, entry=entry, expected_modules=ordered,
                                    protected=protected, discover=True)
            return path, *runner.read_document(path)

        self._start('Preparing linked inputs…', create)

    def open(self):
        if self.busy or not self._discard_edits():
            return
        value = self.dialog.askopenfilename(parent=self.window, title='Open saved run', filetypes=[('Run JSON', '*.json')])
        if value:
            path = Path(value).absolute()
            self._start('Opening run…', lambda: (path, *runner.read_document(path)))

    def _discover_linked(self):
        from .project_input_discovery import discover_project_document

        path, revision = self.path, self.revision

        def show(report):
            self.tabs.add(self.linked_discovery_page, text='Linked inputs')
            self._display(self.linked_discovery, self._json(report))
            self.tabs.select(self.linked_discovery_page)
            self.status.set(f"Found {len(report['inputs'])} input candidates and {len(report['unresolved'])} analysis gaps.")

        self._start('Discovering linked inputs…', lambda: discover_project_document(path, expected=revision), on_success=show)

    def _prepare_linked(self):
        if self.context.edit_modified():
            self.status.set('Save your context edits before preparing linked inputs.')
            return
        path, revision, protected = self.path, self.revision, self.protected

        def show(outcome):
            self._show(*outcome)
            self.tabs.select(self.inputs_page)
            self.status.set('Linked inputs prepared.')

        self._start('Preparing linked inputs…', lambda: (path, *runner.prepare_project_document(
            path, expected=revision, protected=protected)), on_success=show)

    def refresh(self):
        if self.busy or self.path is None:
            return
        if self._linked():
            if (self.document['results'] or {}).get('status') == 'running':
                self._discover_linked()
            else:
                self._prepare_linked()
            return
        if not self._discard_edits():
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
