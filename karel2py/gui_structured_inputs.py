"""Desktop field editor for a detached structured input draft."""
import json


PAGE_SIZE = 64


def prompt_structure(parent, label, draft, prompt_scalar):
    from tkinter import messagebox, simpledialog, ttk

    class FieldsDialog(simpledialog.Dialog):
        def body(self, frame):
            self.page = 0
            self.changed = False
            self.payload = None
            kind = draft.spec[0]
            schema = f'JOINTPOS{draft.spec[1]}' if kind == 'JOINTPOS' else kind
            ttk.Label(frame, text=f'{label}  ·  {schema}').pack(anchor='w', pady=(0, 4))
            if draft.position_register:
                ttk.Label(frame, text='Fill every field before saving the register.').pack(anchor='w', pady=(0, 4))
            table = ttk.Frame(frame)
            table.pack(fill='both', expand=True)
            self.tree = ttk.Treeview(table, columns=('field', 'type', 'value'), show='headings', selectmode='browse', height=12)
            for column, width in (('field', 315), ('type', 87), ('value', 185)):
                self.tree.heading(column, text=column.capitalize())
                self.tree.column(column, width=width, stretch=column == 'field')
            scroll = ttk.Scrollbar(table, command=self.tree.yview)
            self.tree.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y')
            self.tree.pack(fill='both', expand=True)
            self.tree.bind('<Double-1>', self.activate)
            self.tree.bind('<Return>', self.activate)
            self.tree.bind('<<TreeviewSelect>>', self.enable_edit)
            actions = ttk.Frame(frame)
            actions.pack(fill='x', pady=(8, 0))
            self.edit_button = ttk.Button(actions, text='Edit field…', command=self.edit_field)
            self.edit_button.pack(side='left')
            self.next_button = ttk.Button(actions, text='Next', command=lambda: self.move_page(1))
            self.next_button.pack(side='right')
            self.previous_button = ttk.Button(actions, text='Previous', command=lambda: self.move_page(-1))
            self.previous_button.pack(side='right', padx=5)
            self.page_label = ttk.Label(actions)
            self.page_label.pack(side='right', padx=5)
            self.show_page()
            return self.tree

        def show_page(self):
            first = self.page * PAGE_SIZE
            last = min(first + PAGE_SIZE, len(draft.fields))
            self.tree.delete(*self.tree.get_children())
            for index in range(first, last):
                self.tree.insert('', 'end', iid=str(index), values=self.row_values(index))
            self.previous_button.configure(state='normal' if self.page else 'disabled')
            self.next_button.configure(state='normal' if last < len(draft.fields) else 'disabled')
            self.page_label.configure(text=f'{first + 1}–{last} of {len(draft.fields)}')
            self.enable_edit()

        @staticmethod
        def row_values(index):
            path, slot = draft.fields[index]
            value = 'Missing' if slot.value is None else json.dumps(slot.value, ensure_ascii=True)
            return path, slot.options[0], value

        def move_page(self, step):
            self.page += step
            self.show_page()

        def enable_edit(self, _event=None):
            self.edit_button.configure(state='normal' if self.tree.selection() else 'disabled')

        def activate(self, event):
            if event.keysym != 'Return':
                row = self.tree.identify_row(event.y)
                if not row:
                    return 'break'
                self.tree.selection_set(row)
            self.edit_field()
            return 'break'

        def edit_field(self):
            selection = self.tree.selection()
            if not selection:
                return
            index = int(selection[0])
            path, slot = draft.fields[index]
            try:
                value = prompt_scalar(self, path, slot)
            finally:
                # The nested scalar dialog releases its grab when it closes.
                self.grab_set()
            if value is not None:
                slot.set_text(*value)
                self.changed = True
                self.tree.item(selection[0], values=self.row_values(index))

        def validate(self):
            if self.changed:
                try:
                    self.payload = draft.checked_payload()
                except ValueError as error:
                    messagebox.showerror('Invalid input', str(error), parent=self)
                    return False
            return True

        def apply(self):
            self.result = self.payload

    return FieldsDialog(parent, title='Edit input fields').result
