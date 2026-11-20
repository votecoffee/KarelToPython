"""Native Tk interaction checks; require a display, otherwise skip explicitly."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from karel2py import __version__
from karel2py.workbench import Document, analyze_source


@unittest.skipUnless(os.environ.get('KAREL2PY_GUI_TESTS')=='1', 'Native GUI tests require KAREL2PY_GUI_TESTS=1')
@unittest.skipUnless(importlib.util.find_spec('tkinter'), 'Python was installed without Tkinter')
class WorkbenchWindowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from karel2py.gui import Workbench
        try: self.root = tk.Tk()
        except tk.TclError as exc: self.skipTest('No graphical display: ' + str(exc))
        self.root.withdraw()
        def destroy():
            try: self.root.destroy()
            except tk.TclError: pass
        self.addCleanup(destroy)
        self.app = Workbench(self.root)
        self.root.update()

    def source(self, text='PROGRAM DEMO VAR n: INTEGER BEGIN n=42 END DEMO'):
        self.app.set_document(Document(text=text))
        self.root.update()

    def wait(self):
        deadline = time.monotonic() + 10
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.app.busy, 'GUI worker did not complete')

    def test_title_and_header_show_version_and_dirty_document(self):
        self.assertIn(__version__, self.root.title())
        self.source()
        self.assertIn('*', self.root.title())
        self.assertTrue(self.app.document.dirty)

    def test_background_translation_populates_output_and_enables_export(self):
        self.source()
        self.app.start()
        self.assertTrue(self.app.busy)
        self.assertEqual(str(self.app.python_save['state']), 'disabled')
        self.wait()
        self.assertTrue(self.app.analysis.accepted)
        self.assertIn('class Program:', self.app.python.get('1.0', 'end'))
        self.assertEqual(str(self.app.python_save['state']), 'normal')
        self.assertEqual(str(self.app.report_save['state']), 'normal')

    def test_source_edit_invalidates_preview_report_and_exports(self):
        self.source()
        self.app.show_analysis(analyze_source(self.app.document.text))
        self.app.source.insert('end', '\n-- changed')
        self.root.update()
        self.assertIsNone(self.app.analysis)
        self.assertEqual(str(self.app.python_save['state']), 'disabled')
        self.assertEqual(self.app.report.get('1.0', 'end-1c'), '')

    def test_option_change_invalidates_analysis(self):
        self.source()
        for change in (lambda: self.app.shapes.set('DATA=3'), lambda: self.app.cooperative.set(True)):
            self.app.show_analysis(analyze_source(self.app.document.text))
            change()
            self.assertIsNone(self.app.analysis)

    def test_validation_only_disables_python_copy_and_export(self):
        self.source()
        self.app.start(False)
        self.wait()
        self.assertTrue(self.app.analysis.accepted)
        self.assertIsNone(self.app.analysis.python_source)
        self.assertEqual(str(self.app.copy_button['state']), 'disabled')

    def test_saved_run_discovers_edits_executes_and_shows_results(self):
        with tempfile.TemporaryDirectory() as directory:
            self.source('PROGRAM DEMO VAR n,x:INTEGER BEGIN n=x+1 WRITE(n,CR) END DEMO')
            analysis = analyze_source(self.app.document.text)
            target = Path(directory) / 'demo.py'
            path = Path(directory) / 'demo.run.json'
            analysis.export(target, 'python')
            self.app.open_runner()
            window = self.app.run_window
            window.window.withdraw()
            self.addCleanup(lambda: None if window.closed else window.window.destroy())

            def wait_for_run_window():
                deadline = time.monotonic() + 10
                while window.busy and time.monotonic() < deadline:
                    self.root.update()
                    time.sleep(.01)
                self.assertFalse(window.busy)

            with patch.object(window, '_pick_python', return_value=target), \
                    patch.object(window, '_destination', return_value=path), \
                    patch.object(window.message, 'showerror', side_effect=AssertionError('runner error')):
                window.new()
                wait_for_run_window()
                self.assertEqual(window.inputs.item('0', 'values'), ('variable', 'X', 'required', 'missing'))
                window.inputs.selection_set('0')
                window._select_input()
                self.assertEqual(str(window.edit_value['state']), 'normal')
                with patch('karel2py.gui_runner._prompt_value', return_value=('INTEGER', '40')) as prompt:
                    window.edit_selected()
                    wait_for_run_window()
                self.assertEqual(prompt.call_args.args[1], 'X')
                self.assertEqual(window.inputs.item('0', 'values')[-1], 'supplied')
                context = json.loads(window.context.get('1.0', 'end-1c'))
                self.assertEqual(context['variables'][0]['value'], 40)
                context['variables'][0]['value'] = 41
                window.context.replace('1.0', 'end-1c', json.dumps(context))
                window.save()
                wait_for_run_window()
                self.assertEqual(window.inputs.item('0', 'values')[-1], 'supplied')
                with patch.object(window.message, 'askyesno', return_value=True):
                    window.run()
                    wait_for_run_window()
                result = json.loads(window.result.get('1.0', 'end-1c'))
                self.assertEqual(result['status'], 'completed')
                self.assertEqual(result['variables']['N'], 42)
                self.assertIn('42', window.output.get('1.0', 'end-1c'))
                self.assertEqual(json.loads(path.read_bytes())['inputs']['context'], context)

    def test_creates_linked_run_with_reviewed_module_order_and_entry(self):
        from tkinter import ttk

        from karel2py import runner, translate
        from karel2py.gui_runner import RunWindow

        case = self

        class EmbeddedDialog(ttk.Frame):
            def __init__(self, parent, *, title):
                super().__init__(parent)
                self.body(self)
                case.assertEqual(tuple(self.entry['values']), ('LIB', 'MAIN'))
                case.assertEqual(self.tree.item('MAIN', 'values'), ('MAIN', 'worker.py'))
                self.tree.selection_set('MAIN')
                self.update_buttons()
                case.assertTrue(self.module_path['text'].endswith('worker.py'))
                self.up.invoke()
                case.assertEqual(self.tree.get_children(), ('MAIN', 'LIB'))
                self.entry.current(0)
                case.assertTrue(self.validate())
                self.apply()
                self.destroy()

        window = RunWindow(self.root)
        window.window.withdraw()
        self.addCleanup(window.window.destroy)

        def wait_for_run_window():
            deadline = time.monotonic() + 10
            while window.busy and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.01)
            self.assertFalse(window.busy)

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = {
                'library.py': 'PROGRAM LIB VAR n:INTEGER BEGIN n=42 WRITE(n,CR) END LIB',
                'worker.py': 'PROGRAM MAIN VAR n:INTEGER BEGIN n=1 END MAIN',
            }
            for name, program in source.items():
                (folder / name).write_bytes(translate(program, cooperative=True).python_source.encode())
            selection = tuple(str(folder / name) for name in source)
            destination = folder / 'selected.linked.run.json'
            with patch.object(window.dialog, 'askopenfilenames', return_value=selection), \
                    patch('tkinter.simpledialog.Dialog', EmbeddedDialog), \
                    patch.object(window, '_destination', side_effect=(None, destination)) as save, \
                    patch.object(window.message, 'showerror', side_effect=AssertionError('runner error')):
                window.buttons['New linked…'].invoke()
                wait_for_run_window()
                self.assertIsNone(window.document)
                self.assertFalse(destination.exists())
                window.buttons['New linked…'].invoke()
                wait_for_run_window()
            save.assert_called_with('lib.linked')
            document, revision = runner.read_document(destination)
            self.assertEqual(window.document, document)
            self.assertEqual(window.path, destination)
            self.assertIsNone(document['results'])
            self.assertEqual(document['target']['program'], 'LIB')
            self.assertEqual([row['program'] for row in document['target']['modules']], ['MAIN', 'LIB'])
            self.assertEqual(window.tabs.select(), str(window.inputs_page))
            self.assertEqual(document['inputs']['template']['target'], document['target'])
            result = runner.run_document(destination, expected=revision)['results']
            self.assertEqual(result['text_output'].strip(), '42')
            self.assertEqual(result['programs']['LIB']['values']['N'], 42)

    def test_linked_run_opens_edits_replays_and_filters_saved_program_results(self):
        from karel2py import runner, translate
        from karel2py.gui_runner import RunWindow
        from karel2py.project_run import create_project_document

        window = RunWindow(self.root)
        window.window.withdraw()
        self.addCleanup(window.window.destroy)

        def wait_for_run_window():
            deadline = time.monotonic() + 10
            while window.busy and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.01)
            self.assertFalse(window.busy)

        def open_run(path):
            with patch.object(window.dialog, 'askopenfilename', return_value=str(path)):
                window.open()
                wait_for_run_window()

        with tempfile.TemporaryDirectory() as directory, patch.object(
            window.message, 'showerror', side_effect=AssertionError('runner error')
        ):
            folder = Path(directory)
            main, lib, solo = (folder / (name + '.py') for name in ('main', 'lib', 'solo'))
            main.write_bytes(translate(
                'PROGRAM MAIN VAR n FROM LIB:INTEGER BEGIN n=n+4 WRITE(n,CR) END MAIN',
                cooperative=True,
            ).python_source.encode())
            lib.write_bytes(translate('PROGRAM LIB VAR n:INTEGER BEGIN END LIB', cooperative=True).python_source.encode())
            solo.write_bytes(translate('PROGRAM SOLO VAR n:INTEGER BEGIN WRITE(n) END SOLO').python_source.encode())
            path = folder / 'linked.run.json'
            standalone = folder / 'solo.run.json'
            context = {'variables': [{'program': 'LIB', 'path': 'N', 'type': 'INTEGER', 'value': 3}]}
            created = create_project_document([lib, main], path, entry='MAIN', context=context)
            runner.create_document(solo, standalone, discover=True)

            open_run(path)
            self.assertIn('Entry MAIN', window.location.get())
            self.assertEqual(window.tabs.select(), str(window.edits_page))
            self.assertEqual(window.tabs.tab(window.inputs_page, 'state'), 'hidden')
            self.assertEqual(window.tabs.tab(window.requirements_page, 'text'), 'Pinned modules')
            self.assertEqual(json.loads(window.requirements.get('1.0', 'end-1c')), created['target']['modules'])
            self.assertEqual(str(window.buttons['Rediscover…']['text']), 'Prepare inputs…')
            self.assertEqual(str(window.buttons['Rediscover…']['state']), 'normal')
            window.buttons['Rediscover…'].invoke()
            wait_for_run_window()
            self.assertEqual(window.tabs.select(), str(window.inputs_page))
            discovered = json.loads(window.linked_discovery.get('1.0', 'end-1c'))
            self.assertEqual([(row['program'], row['path']) for row in discovered['inputs']], [('LIB', 'N')])
            self.assertEqual(discovered['inputs'][0]['locations'][0]['program'], 'MAIN')
            self.assertEqual(json.loads(path.read_bytes())['inputs']['template']['discovery'], discovered)
            self.assertEqual(window.inputs.item('0', 'values'), ('variable', 'LIB.N', 'required', 'supplied'))

            window.inputs.selection_set('0')
            window._select_input()
            self.assertEqual(str(window.edit_value['state']), 'normal')
            with patch('karel2py.gui_runner._prompt_value', return_value=('INTEGER', '5')) as prompt:
                window.edit_selected()
                wait_for_run_window()
            self.assertEqual(prompt.call_args.args[1], 'LIB.N')
            context['variables'][0]['value'] = 5
            with patch.object(window.message, 'askyesno', return_value=True):
                window.run()
                wait_for_run_window()
            self.assertEqual(window.tabs.select(), str(window.results_page))
            report = json.loads(window.result.get('1.0', 'end-1c'))
            self.assertEqual(report['status'], 'completed')
            self.assertEqual(tuple(window.result_program['values']), ('All results', 'LIB', 'MAIN'))
            window.result_program.current(1)
            window.result_program.event_generate('<<ComboboxSelected>>')
            self.root.update()
            lib_result = json.loads(window.result.get('1.0', 'end-1c'))
            self.assertEqual(lib_result, report['programs']['LIB'])
            self.assertEqual(lib_result['values']['N'], 9)
            self.assertEqual(window.output.get('1.0', 'end-1c').strip(), '9')
            self.assertEqual(json.loads(path.read_bytes())['inputs']['context'], context)

            open_run(standalone)
            self.assertEqual(window.tabs.tab(window.inputs_page, 'state'), 'normal')
            self.assertEqual(window.tabs.index(window.inputs_page), 0)
            self.assertEqual(str(window.buttons['Rediscover…']['state']), 'normal')
            self.assertEqual(str(window.buttons['Rediscover…']['text']), 'Rediscover…')
            self.assertNotIn(str(window.linked_discovery_page), window.tabs.tabs())
            self.assertEqual(window.result_filter.winfo_manager(), '')
            self.assertEqual(window.inputs.item('0', 'values'), ('variable', 'N', 'required', 'missing'))
            open_run(path)
            self.assertEqual(json.loads(window.result.get('1.0', 'end-1c')), report)

    def test_saved_run_paged_field_editor_saves_selected_array_value(self):
        from tkinter import ttk

        case = self

        class EmbeddedDialog(ttk.Frame):
            # Exercise the real dialog widgets without showing a modal window.
            def __init__(self, parent, *, title):
                super().__init__(parent)
                self.result = None
                self.body(self)
                case.assertEqual(len(self.tree.get_children()), 64)
                self.move_page(1)
                case.assertEqual(self.tree.get_children(), ('64',))
                self.tree.selection_set('64')
                self.edit_field()
                case.assertTrue(self.validate())
                self.apply()
                self.destroy()

            def grab_set(self):
                pass

        with tempfile.TemporaryDirectory() as directory:
            self.source('PROGRAM DEMO VAR values,copied:ARRAY[65]OF INTEGER n:INTEGER BEGIN copied=values n=copied[65] END DEMO')
            analysis = analyze_source(self.app.document.text)
            target = Path(directory) / 'demo.py'
            path = Path(directory) / 'demo.run.json'
            analysis.export(target, 'python')
            self.app.open_runner()
            window = self.app.run_window
            window.window.withdraw()
            self.addCleanup(lambda: None if window.closed else window.window.destroy())
            from karel2py import runner

            runner.create_document(target, path, discover=True)
            window._show(path, *runner.read_document(path))
            window.inputs.selection_set('0')
            window._select_input()
            self.assertEqual(str(window.edit_value['text']), 'Edit fields…')
            with patch('tkinter.simpledialog.Dialog', EmbeddedDialog), \
                    patch('karel2py.gui_runner._prompt_value', return_value=('INTEGER', '41')) as prompt:
                window.edit_selected()
            deadline = time.monotonic() + 10
            while window.busy and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.01)
            self.assertFalse(window.busy)
            self.assertEqual(prompt.call_args.args[1], 'VALUES[65]')
            saved = runner.read_document(path)[0]
            self.assertEqual(saved['inputs']['context']['variables'][0]['value'], [{'uninitialized': True}] * 64 + [41])
            self.assertEqual(runner.run_document(path)['results']['variables']['N'], 41)

    def test_diagnostic_navigates_to_exact_source_line_and_column(self):
        self.source('PROGRAM DEMO\nBEGIN\n  UNKNOWN\nEND DEMO')
        self.app.start()
        self.wait()
        self.assertFalse(self.app.analysis.accepted)
        item = self.app.diagnostics.get_children()[0]
        self.app.diagnostics.selection_set(item)
        self.app.go_to_diagnostic()
        self.assertEqual(self.app.source.index('insert'), '3.2')
        self.assertTrue(self.app.source.tag_ranges('diagnostic'))

    def test_cancelled_discard_preserves_buffer(self):
        self.source()
        with patch.object(self.app.message, 'askyesnocancel', return_value=None): self.app.new()
        self.assertIn('PROGRAM DEMO', self.app.source.get('1.0', 'end'))

    def test_worker_exception_restores_controls_without_stale_export(self):
        with patch.object(self.app.message, 'showerror') as error:
            self.app._start(lambda: (_ for _ in ()).throw(ValueError('authored failure')), 'Working')
            self.wait()
            error.assert_called_once()
        self.assertIsNone(self.app.analysis)
        self.assertEqual(str(self.app.translate_button['state']), 'normal')
        self.assertEqual(str(self.app.python_save['state']), 'disabled')

    def test_changed_revision_discards_late_worker_result(self):
        self.source()
        self.app.start()
        self.app.invalidate()
        self.wait()
        self.assertIsNone(self.app.analysis)

    def test_save_dialog_cancellation_keeps_unsaved_edits(self):
        self.source()
        with patch.object(self.app.dialog, 'asksaveasfilename', return_value=''):
            self.assertFalse(self.app.save_source())
        self.assertTrue(self.app.document.dirty)

    def test_source_cannot_be_overwritten_by_generated_python(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.kl'
            original = 'PROGRAM DEMO BEGIN END DEMO'
            path.write_text(original)
            self.app.open_file(path)
            self.app.show_analysis(analyze_source(original, filename=path))
            with patch.object(self.app, '_save_path', return_value=path), patch.object(self.app.message, 'showerror') as error:
                self.app.export('python')
                error.assert_called_once()
            self.assertEqual(path.read_text(), original)

    def test_close_cancel_preserves_unsaved_buffer_and_window(self):
        self.source()
        with patch.object(self.app.message, 'askyesnocancel', return_value=None): self.app.close()
        self.assertFalse(self.app.closed)
        self.assertTrue(self.root.winfo_exists())
        self.assertTrue(self.app.document.dirty)

    def test_close_during_worker_cancels_poll_without_calling_tk_from_worker(self):
        release, finished = threading.Event(), threading.Event()
        def operation():
            release.wait(2)
            result = analyze_source('PROGRAM DEMO BEGIN END DEMO')
            finished.set()
            return result
        self.app._start(operation, 'Waiting')
        with patch.object(self.app.message, 'askyesno', return_value=True): self.app.close()
        release.set()
        self.assertTrue(finished.wait(3))
        self.assertTrue(self.app.closed)
        self.assertIsNone(self.app.analysis)

    def test_edit_before_event_delivery_cannot_export_stale_python(self):
        self.source()
        self.app.show_analysis(analyze_source(self.app.document.text))
        self.app.source.insert('end', '\n-- changed before modified callback')
        with patch.object(self.app.dialog, 'asksaveasfilename') as dialog:
            self.app.export('python')
            dialog.assert_not_called()
        self.assertIsNone(self.app.analysis)

    def test_project_report_also_protects_current_source_outside_project(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.kl'
            path.write_text('PROGRAM DEMO BEGIN END DEMO')
            self.app.open_file(path)
            from karel2py.workbench import Analysis
            self.app.show_analysis(Analysis(dict(status='translated', programs={}, diagnostics=[])))
            with patch.object(self.app, '_save_path', return_value=path), patch.object(self.app.message, 'showerror') as error:
                self.app.export('report')
                error.assert_called_once()
            self.assertEqual(path.read_text(), 'PROGRAM DEMO BEGIN END DEMO')


if __name__ == '__main__': unittest.main()
