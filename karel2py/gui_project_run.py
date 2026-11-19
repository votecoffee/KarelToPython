"""Select the entry and scheduling order for a new linked run."""


def select_linked_modules(parent, modules):
    from tkinter import messagebox, simpledialog, ttk

    by_name = {pin.program: pin for pin in modules}

    class LinkedModulesDialog(simpledialog.Dialog):
        def body(self, frame):
            ttk.Label(frame, text='Entry program').grid(row=0, column=0, sticky='w', pady=(0, 8))
            self.entry = ttk.Combobox(frame, values=tuple(by_name), state='readonly', width=22)
            self.entry.grid(row=0, column=1, sticky='w', pady=(0, 8))
            if len(by_name) == 1:
                self.entry.current(0)

            ttk.Label(frame, text='Module order breaks ties between tasks of equal priority.').grid(
                row=1, column=0, columnspan=2, sticky='w')
            self.tree = ttk.Treeview(frame, columns=('program', 'file'), show='headings',
                                     selectmode='browse', height=min(len(by_name), 8))
            self.tree.heading('program', text='Program')
            self.tree.heading('file', text='Python module')
            self.tree.column('program', width=130, stretch=False)
            self.tree.column('file', width=400, stretch=True)
            self.tree.grid(row=2, column=0, columnspan=2, sticky='nsew')
            vertical = ttk.Scrollbar(frame, command=self.tree.yview)
            vertical.grid(row=2, column=2, sticky='ns')
            self.tree.configure(yscrollcommand=vertical.set)
            for program, pin in by_name.items():
                self.tree.insert('', 'end', iid=program, values=(program, pin.path.name))

            self.module_path = ttk.Label(frame, wraplength=520)
            self.module_path.grid(row=3, column=0, columnspan=2, sticky='w', pady=(6, 0))
            actions = ttk.Frame(frame)
            actions.grid(row=4, column=0, columnspan=2, sticky='w', pady=(6, 0))
            self.up = ttk.Button(actions, text='Move up', command=lambda: self.move(-1))
            self.down = ttk.Button(actions, text='Move down', command=lambda: self.move(1))
            self.up.pack(side='left', padx=(0, 6))
            self.down.pack(side='left')
            self.tree.bind('<<TreeviewSelect>>', self.update_buttons)
            self.tree.selection_set(next(iter(by_name)))
            self.update_buttons()
            return self.entry

        def update_buttons(self, _event=None):
            selected = self.tree.selection()
            index = self.tree.index(selected[0]) if selected else -1
            self.module_path.configure(text=str(by_name[selected[0]].path) if selected else '')
            self.up.configure(state='normal' if index > 0 else 'disabled')
            self.down.configure(state='normal' if 0 <= index < len(by_name) - 1 else 'disabled')

        def move(self, offset):
            selected = self.tree.selection()
            if selected:
                name = selected[0]
                destination = self.tree.index(name) + offset
                if 0 <= destination < len(by_name):
                    self.tree.move(name, '', destination)
                    self.tree.see(name)
                    self.update_buttons()

        def validate(self):
            if self.entry.get() in by_name:
                return True
            messagebox.showerror('Choose an entry program', 'Select the program to start.', parent=self)
            return False

        def apply(self):
            self.result = self.entry.get(), tuple(by_name[name] for name in self.tree.get_children())

    return LinkedModulesDialog(parent, title='New linked run').result
