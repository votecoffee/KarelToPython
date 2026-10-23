"""Authored desktop operations: source preservation, exports and compile-only analysis."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from karel2py import __version__
from karel2py.workbench import Analysis, Document, MAX_SOURCE_BYTES, analyze_project, analyze_source, parse_shapes, write_bytes


SOURCE = 'PROGRAM DEMO VAR n: INTEGER BEGIN n=42 END DEMO\n'


class DocumentTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_open_keeps_original_bytes_and_tracks_edits(self):
        path = self.root / 'source.kl'
        original = b'\xef\xbb\xbf' + SOURCE.replace('\n', '\r\n').encode()
        path.write_bytes(original)
        doc = Document.open(path)
        self.assertEqual(doc.original_bytes, original)
        self.assertEqual(doc.text, SOURCE)
        self.assertFalse(doc.dirty)
        doc.text = SOURCE.replace('42', '43')
        self.assertTrue(doc.dirty)
        self.assertEqual(path.read_bytes(), original)

    def test_explicit_save_retains_bom_and_homogeneous_newlines(self):
        for newline in ('\r\n', '\r', '\n'):
            with self.subTest(newline=newline):
                path = self.root / 'source.kl'
                path.write_bytes(b'\xef\xbb\xbf' + SOURCE.replace('\n', newline).encode())
                doc = Document.open(path)
                doc.text = SOURCE.replace('42', '43')
                doc.save(path, overwrite=True)
                self.assertEqual(path.read_bytes(), b'\xef\xbb\xbf' + doc.text.replace('\n', newline).encode())
                self.assertFalse(doc.dirty)

    def test_unchanged_save_does_not_rewrite_file(self):
        path = self.root / 'source.kl'
        data = b'PROGRAM DEMO\r\nBEGIN\nEND DEMO\r'
        path.write_bytes(data)
        doc = Document.open(path)
        with patch('karel2py.workbench.write_bytes', side_effect=AssertionError('rewrote unchanged input')): doc.save(path)
        self.assertEqual(path.read_bytes(), data)

    def test_save_as_keeps_original_and_updates_identity(self):
        path, other = self.root / 'source.kl', self.root / 'copy.kl'
        path.write_text(SOURCE)
        doc = Document.open(path)
        doc.text = SOURCE.replace('42', '43')
        doc.save(other)
        self.assertEqual(path.read_text(), SOURCE)
        self.assertEqual(other.read_text(), doc.text)
        self.assertEqual(doc.path, other.resolve())

    def test_external_disk_edit_is_not_overwritten(self):
        path = self.root / 'source.kl'
        path.write_text(SOURCE)
        doc = Document.open(path)
        doc.text = SOURCE.replace('42', '43')
        path.write_text('external edit')
        with self.assertRaisesRegex(ValueError, 'changed on disk'): doc.save(path, overwrite=True)
        self.assertEqual(path.read_text(), 'external edit')
        self.assertTrue(doc.dirty)

    def test_deleted_source_is_not_silently_recreated(self):
        path = self.root / 'source.kl'
        path.write_text(SOURCE)
        doc = Document.open(path)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'changed on disk'): doc.save(path, overwrite=True)
        self.assertFalse(path.exists())

    def test_save_requires_permission_to_replace_another_file(self):
        path = self.root / 'existing.kl'
        path.write_text('keep')
        with self.assertRaises(FileExistsError): Document(text=SOURCE).save(path)
        self.assertEqual(path.read_text(), 'keep')

    def test_failed_save_keeps_document_identity(self):
        doc = Document(text=SOURCE)
        with patch('karel2py.workbench.write_bytes', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): doc.save(self.root / 'new.kl')
        self.assertIsNone(doc.path)
        self.assertTrue(doc.dirty)

    def test_open_rejects_invalid_encoding_directory_and_oversized_input(self):
        path = self.root / 'source.kl'
        path.write_bytes(b'\xff')
        with self.assertRaises(UnicodeError): Document.open(path)
        with self.assertRaises(ValueError): Document.open(self.root)
        path.write_bytes(b'x' * (MAX_SOURCE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, '4 MiB'): Document.open(path)


class ExportTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = self.root / 'source.kl'
        self.source.write_text(SOURCE)
        self.result = analyze_source(SOURCE, filename=self.source)

    def test_exports_emit_checked_python_and_json(self):
        python, report = self.root / 'result.py', self.root / 'result.json'
        self.result.export(python, 'python')
        self.result.export(report, 'report')
        namespace = {'__name__': 'authored_workbench_test'}
        exec(python.read_text(), namespace)
        self.assertEqual(namespace['Program']().run()['N'], 42)
        self.assertEqual(json.loads(report.read_text())['translator_version'], __version__)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_direct_and_relative_source_aliases_are_protected(self):
        for path in (self.source, self.root / 'other' / '..' / 'source.kl'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'protected'):
                self.result.export(path, 'python', overwrite=True)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_hardlinked_source_is_protected(self):
        alias = self.root / 'alias.py'
        try: os.link(self.source, alias)
        except OSError as exc: self.skipTest(str(exc))
        with self.assertRaisesRegex(ValueError, 'protected'): self.result.export(alias, 'python', overwrite=True)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_existing_output_requires_explicit_overwrite(self):
        output = self.root / 'result.py'
        output.write_text('keep')
        with self.assertRaises(FileExistsError): self.result.export(output, 'python')
        self.assertEqual(output.read_text(), 'keep')
        self.result.export(output, 'python', overwrite=True)
        self.assertEqual(output.read_text(), self.result.python_source)

    def test_failed_atomic_replace_keeps_old_output_and_cleans_temporary(self):
        output = self.root / 'result.py'
        output.write_text('keep')
        with patch('karel2py.fileio.os.replace', side_effect=OSError('locked')):
            with self.assertRaises(OSError): self.result.export(output, 'python', overwrite=True)
        self.assertEqual(output.read_text(), 'keep')
        self.assertEqual(list(self.root.glob('.*.tmp')), [])

    def test_directory_and_symlink_are_not_export_targets(self):
        with self.assertRaises(ValueError): self.result.export(self.root, 'python', overwrite=True)
        alias = self.root / 'alias.py'
        try: alias.symlink_to(self.source)
        except OSError as exc: self.skipTest(str(exc))
        with self.assertRaises(ValueError): self.result.export(alias, 'python', overwrite=True)

    def test_rejected_and_validation_only_results_have_no_python_export(self):
        for result in (analyze_source('PROGRAM BAD BEGIN UNKNOWN END BAD'), analyze_source(SOURCE, emit=False)):
            with self.subTest(accepted=result.accepted), self.assertRaises(ValueError): result.export(self.root / 'result.py', 'python')
        self.assertFalse((self.root / 'result.py').exists())

    def test_unknown_export_kind_is_rejected(self):
        with self.assertRaises(ValueError): self.result.export(self.root / 'result', 'source')


class WorkbenchAnalysisTests(unittest.TestCase):
    def test_translation_report_tracks_editor_text_hash(self):
        result = analyze_source(SOURCE)
        self.assertTrue(result.accepted)
        self.assertEqual(result.report['source_text_sha256'], hashlib.sha256(SOURCE.encode()).hexdigest())
        self.assertNotIn('source_file_sha256', result.report)

    def test_rejected_source_has_located_diagnostic_without_python(self):
        result = analyze_source('PROGRAM BAD\nBEGIN\nUNKNOWN\nEND BAD', filename='bad.kl')
        self.assertFalse(result.accepted)
        self.assertIsNone(result.python_source)
        self.assertEqual((result.diagnostics[0]['file'], result.diagnostics[0]['line']), ('bad.kl', 3))
        self.assertEqual(result.report['translator_version'], __version__)

    def test_validation_does_not_expose_generated_python(self):
        result = analyze_source(SOURCE, emit=False)
        self.assertTrue(result.accepted)
        self.assertIsNone(result.python_source)

    def test_source_analysis_never_executes_source_body(self):
        result = analyze_source('PROGRAM DEMO VAR f: FILE BEGIN OPEN FILE f (\'W\',\'unexpected.txt\') WRITE f (\'bad\') END DEMO')
        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.python_source)

    def test_explicit_shapes_and_cooperative_option_reach_translator(self):
        result = analyze_source('PROGRAM DEMO VAR data: ARRAY[*] OF INTEGER BEGIN data[1]=42 END DEMO', shapes='data=2', cooperative=True)
        self.assertTrue(result.accepted)
        self.assertTrue(result.report['cooperative_execution'])
        namespace = {'__name__': 'authored_workbench_shapes'}
        exec(result.python_source, namespace)
        self.assertEqual(namespace['Program'].external_array_shapes, (('DATA', (2,)),))
        self.assertEqual(namespace['Program']().run()['DATA'][0], 42)

    def test_shapes_use_literal_parser_and_reject_duplicates(self):
        self.assertEqual(parse_shapes('data=2,3; FLAGS=8;'), {'DATA': (2, 3), 'FLAGS': (8,)})
        for value in ('data=2;DATA=3', 'data=1+2', 'data=0', 'data=__import__(x)'):
            with self.subTest(value=value), self.assertRaises((ValueError, argparse.ArgumentTypeError)): parse_shapes(value)

    def test_oversized_editor_text_is_bounded(self):
        with self.assertRaises(ValueError): analyze_source('x' * (MAX_SOURCE_BYTES + 1))

    def test_project_checks_linkage_without_executing_bodies(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'main.kl').write_text('PROGRAM MAIN ROUTINE helper FROM LIB BEGIN helper() END MAIN')
            (root / 'lib.kl').write_text('PROGRAM LIB ROUTINE helper BEGIN ABORT END helper BEGIN ABORT END LIB')
            result = analyze_project(root)
            self.assertTrue(result.accepted)
            self.assertTrue(result.report['linked'])
            self.assertEqual(set(result.report['programs']), {'MAIN', 'LIB'})
            self.assertIsNone(result.python_source)
            with self.assertRaises(ValueError): result.export(root / 'lib.kl', 'report', overwrite=True)

    def test_project_parse_error_has_real_file_location(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'bad.kl'
            path.write_text('PROGRAM BAD BEGIN UNKNOWN END BAD')
            result = analyze_project(root)
            self.assertFalse(result.accepted)
            self.assertTrue(Path(result.diagnostics[0]['file']).samefile(path))
            self.assertEqual(result.diagnostics[0]['code'], 'E_CALL')

    def test_unresolved_project_link_is_a_reported_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'main.kl'
            path.write_text('PROGRAM MAIN ROUTINE helper FROM MISSING BEGIN helper() END MAIN')
            result = analyze_project(folder)
            self.assertFalse(result.accepted)
            self.assertEqual(result.diagnostics[0]['code'], 'E_PROJECT_LINK')
            self.assertIn('MISSING', result.diagnostics[0]['message'])


if __name__ == '__main__': unittest.main()
