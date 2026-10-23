"""Native Tk interaction checks; require a display, otherwise skip explicitly."""
import importlib.util
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from karel2py import __version__
from karel2py.workbench import Document, analyze_source


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
