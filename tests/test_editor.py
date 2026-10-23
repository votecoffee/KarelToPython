"""Authored editor behavior, exact source navigation and native text operations."""
import importlib.util
import unittest
from unittest.mock import patch

from karel2py import translate
from karel2py.editor import MAX_COLOR_CHARS, find_literal, generated_lines, replace_literal, source_location, syntax_spans
from karel2py.workbench import Document, analyze_source


class EditorOperationsTests(unittest.TestCase):
    def spans(self, text, language):
        return [(tag, text[start:end]) for tag, start, end in syntax_spans(text, language)]

    def test_karel_comments_and_strings_do_not_color_embedded_keywords(self):
        text = "IF label='-- RETURN' THEN -- FOR 123\nENDIF"
        self.assertEqual(self.spans(text, 'karel'), [('keyword', 'IF'), ('string', "'-- RETURN'"),
                         ('keyword', 'THEN'), ('comment', '-- FOR 123'), ('keyword', 'ENDIF')])

    def test_karel_directive_numbers_and_case(self):
        self.assertEqual(self.spans('%ENVIRONMENT IOSETUP\nbegin n=1.5e2 END', 'karel'),
                         [('directive', '%ENVIRONMENT IOSETUP'), ('keyword', 'begin'), ('number', '1.5e2'), ('keyword', 'END')])

    def test_python_quoted_hash_and_comment_keywords_are_isolated(self):
        self.assertEqual(self.spans("if label == '# while': # return\n    return 42", 'python'),
                         [('keyword', 'if'), ('string', "'# while'"), ('comment', '# return'), ('keyword', 'return'), ('number', '42')])

    def test_coloring_accepts_incomplete_source_and_bounds_its_work(self):
        syntax_spans("PROGRAM DEMO BEGIN label='unfinished", 'karel')
        self.assertEqual(syntax_spans(' ' * MAX_COLOR_CHARS + 'RETURN', 'karel'), [])
        self.assertEqual(syntax_spans('RETURN', None), [])

    def test_literal_replacement_does_not_interpret_regex_or_backreferences(self):
        self.assertEqual(replace_literal('a.*b A.*B', 'a.*b', r'\1'), (r'\1 \1', 2))
        self.assertEqual(replace_literal('a A a', 'a', 'x', match_case=True), ('x A x', 2))

    def test_literal_search_wraps_and_preserves_case_and_metacharacters(self):
        self.assertEqual(find_literal('one ONE', 'one'), (0, 3, False))
        self.assertEqual(find_literal('one ONE', 'one', 3), (4, 7, False))
        self.assertEqual(find_literal('one ONE', 'one', 7), (0, 3, True))
        self.assertEqual(find_literal('ONE one', 'one', match_case=True), (4, 7, False))
        self.assertEqual(find_literal('a.*b', '.*'), (1, 3, False))

    def test_reverse_literal_search_handles_overlaps_and_multiline_unicode(self):
        self.assertEqual(find_literal('banana', 'ana', 6, backwards=True), (3, 6, False))
        self.assertEqual(find_literal('banana', 'ana', 3, backwards=True), (1, 4, False))
        self.assertEqual(find_literal('banana', 'ana', 0, backwards=True), (3, 6, True))
        self.assertEqual(find_literal('first😀\nsecond', '😀\nsecond'), (5, 13, False))
        self.assertEqual(find_literal('first😀\nsecond', '😀\nsecond', 13, backwards=True), (5, 13, False))

    def test_empty_and_absent_searches_return_no_range(self):
        for query in ('', 'missing'):
            for backwards in (False, True):
                self.assertIsNone(find_literal('source', query, backwards=backwards))

    def test_replacements_are_nonoverlapping_and_preserve_newlines(self):
        self.assertEqual(replace_literal('aaaa\naa', 'aa', 'z'), ('zz\nz', 3))
        self.assertEqual(replace_literal('one\ntwo', '\n', '\n-- '), ('one\n-- two', 1))

    def test_empty_or_absent_query_does_not_change_text(self):
        for query in ('', 'missing'):
            with self.subTest(query=query): self.assertEqual(replace_literal('source', query, 'new'), ('source', 0))

    def test_replacement_budget_counts_utf8_bytes_before_publication(self):
        self.assertEqual(replace_literal('aa', 'a', 'é', limit=4), ('éé', 2))
        with self.assertRaises(ValueError): replace_literal('aa', 'a', 'é', limit=3)

    def test_source_map_uses_only_unambiguous_explicit_positive_locations(self):
        rows = [dict(python_line=10, karel_line=3, karel_column=5), dict(python_line=8, karel_line=3, karel_column=1),
                dict(python_line=10, karel_line=3, karel_column=5), dict(python_line=9, karel_line=2, karel_column=1),
                dict(python_line=9, karel_line=4, karel_column=1), dict(python_line=True, karel_line=1, karel_column=1), {}, None]
        self.assertEqual(generated_lines(rows, 3), [8, 10])
        self.assertEqual(source_location(rows, 10), (3, 5))
        self.assertIsNone(source_location(rows, 9))
        self.assertIsNone(source_location(rows, 11))

    def test_real_translation_map_roundtrips_statement_locations(self):
        result = translate('PROGRAM DEMO\nVAR n: INTEGER\nBEGIN\n  n=42\nEND DEMO')
        lines = generated_lines(result.report['source_map'], 4)
        self.assertTrue(lines)
        for line in lines: self.assertEqual(source_location(result.report['source_map'], line), (4, 3))
        self.assertEqual(generated_lines(result.report['source_map'], 2), [])


@unittest.skipUnless(importlib.util.find_spec('tkinter'), 'Python was installed without Tkinter')
class NativeEditorTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from karel2py.gui import Workbench
        try: self.root = tk.Tk()
        except tk.TclError as exc: self.skipTest('No graphical display: ' + str(exc))
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = Workbench(self.root)
        self.root.update()

    def source(self, text):
        self.app.set_document(Document(text=text, saved_text=text))
        self.root.update()

    def test_find_moves_forward_backward_and_wraps(self):
        self.source('one ONE one')
        self.app.source.mark_set('insert', '1.0')
        self.app.query.set('one')
        self.assertEqual(self.app.find_next(), ('1.0', '1.3'))
        self.assertEqual(self.app.find_next(), ('1.4', '1.7'))
        self.assertEqual(self.app.find_next(True), ('1.0', '1.3'))
        self.assertEqual(self.app.find_next(True), ('1.8', '1.11'))
        self.assertIn('wrapped', self.app.search_status.get())

    def test_case_toggle_and_literal_search(self):
        self.source('ONE .* one')
        self.app.source.mark_set('insert', '1.0')
        self.app.query.set('one')
        self.app.match_case.set(True)
        self.assertEqual(self.app.find_next(), ('1.7', '1.10'))
        self.app.query.set('.*')
        self.assertEqual(self.app.find_next(), ('1.4', '1.6'))

    def test_replace_one_is_one_undo_and_invalidates_results(self):
        self.source('one one')
        self.app.show_analysis(analyze_source('PROGRAM DEMO BEGIN END DEMO'))
        self.app.source.mark_set('insert', '1.0')
        self.app.query.set('one')
        self.app.replacement.set('two')
        self.assertEqual(self.app.replace_current(), 1)
        self.root.update()
        self.assertEqual(self.app.source.get('1.0', 'end-1c'), 'two one')
        self.assertIsNone(self.app.analysis)
        self.app.source.edit_undo()
        self.root.update()
        self.assertEqual(self.app.source.get('1.0', 'end-1c'), 'one one')
        self.assertFalse(self.app.document.dirty)

    def test_replace_all_is_one_undo_and_redo_group(self):
        self.source('one ONE\none')
        self.app.query.set('one')
        self.app.replacement.set('two')
        self.assertEqual(self.app.replace_all(), 3)
        self.assertEqual(self.app.source.get('1.0', 'end-1c'), 'two two\ntwo')
        self.app.source.edit_undo()
        self.root.update()
        self.assertEqual(self.app.source.get('1.0', 'end-1c'), 'one ONE\none')
        self.assertEqual(self.app.document.text, 'one ONE\none')
        self.assertFalse(self.app.document.dirty)
        self.app.source.edit_redo()
        self.root.update()
        self.assertEqual(self.app.source.get('1.0', 'end-1c'), 'two two\ntwo')
        self.assertEqual(self.app.document.text, 'two two\ntwo')
        self.assertTrue(self.app.document.dirty)

    def test_readonly_preview_can_be_searched_but_never_replaced(self):
        self.source('PROGRAM DEMO BEGIN END DEMO')
        result = analyze_source(self.app.document.text)
        self.app.show_analysis(result)
        self.app.search_target.set('Python')
        self.app.query.set('class Program')
        self.assertIsNotNone(self.app.find_next())
        self.app.replacement.set('changed')
        self.assertEqual(self.app.replace_current(), 0)
        self.assertEqual(self.app.replace_all(), 0)
        self.assertEqual(self.app.python.get('1.0', 'end-1c'), result.python_source)
        self.assertIs(self.app.analysis, result)

    def test_no_match_does_not_invalidate_valid_translation(self):
        self.source('PROGRAM DEMO BEGIN END DEMO')
        result = analyze_source(self.app.document.text)
        self.app.show_analysis(result)
        self.app.query.set('missing')
        self.assertIsNone(self.app.find_next())
        self.assertEqual(self.app.replace_all(), 0)
        self.assertIs(self.app.analysis, result)

    def test_replacement_budget_failure_keeps_source_and_undo_unchanged(self):
        self.source('one one')
        self.app.query.set('one')
        self.app.replacement.set('long')
        with patch('karel2py.gui.replace_literal', side_effect=ValueError('too large')), patch.object(self.app.message, 'showerror'):
            self.assertEqual(self.app.replace_all(), 0)
        self.assertEqual(self.app.source.get('1.0', 'end-1c'), 'one one')
        self.assertFalse(self.app.document.dirty)

    def test_unicode_search_and_single_replace_use_tk_character_boundaries(self):
        self.source('a😀b😀c')
        self.app.source.mark_set('insert', '1.0')
        self.app.query.set('😀')
        match = self.app.find_next()
        self.assertEqual(self.app.source.get(*match), '😀')
        self.app.replacement.set('x')
        self.assertEqual(self.app.replace_current(), 1)
        self.assertEqual(self.app.source.get('1.0', 'end-1c'), 'axb😀c')

    def test_multiline_literal_search_retains_exact_range(self):
        self.source('first😀\nsecond\nthird')
        self.app.source.mark_set('insert', '1.0')
        self.app.query.set('😀\nsecond')
        match = self.app.find_next()
        self.assertEqual(self.app.source.get(*match), '😀\nsecond')
        self.app.replacement.set('joined')
        self.assertEqual(self.app.replace_current(), 1)
        self.assertEqual(self.app.source.get('1.0', 'end-1c'), 'firstjoined\nthird')

    def test_coloring_after_astral_characters_uses_exact_native_indices(self):
        self.source("label='😀' -- comment")
        self.root.deiconify()
        self.root.update()
        ranges = self.app.source.tag_ranges('syntax_comment')
        self.assertEqual(self.app.source.get(*ranges), '-- comment')

    def test_application_find_shortcut_does_not_apply_native_text_movement(self):
        self.source('first second')
        self.root.deiconify()
        self.app.source.focus_force()
        self.root.update()
        self.app.source.mark_set('insert', '1.0')
        self.app.source.event_generate('<Control-f>')
        self.root.update()
        self.assertTrue(self.app.search_visible)
        self.assertEqual(self.app.source.index('insert'), '1.0')

    def test_goto_line_and_zoom_do_not_change_source(self):
        self.source('first\nsecond\nthird')
        self.app.go_to_line(2)
        self.assertEqual(self.app.source.index('insert'), '2.0')
        self.assertEqual(self.app.position.get(), 'Ln 2, Col 1')
        self.app.go_to_line(99)
        self.assertEqual(self.app.source.index('insert'), '2.0')
        self.app.zoom(100)
        self.assertTrue(all(editor.font.cget('size') == 24 for editor in self.app.editors.values()))
        self.app.zoom(-100)
        self.assertTrue(all(editor.font.cget('size') == 8 for editor in self.app.editors.values()))
        self.assertFalse(self.app.document.dirty)

    def test_source_mapping_roundtrip_and_unmapped_scaffolding(self):
        self.source('PROGRAM DEMO\nVAR n: INTEGER\nBEGIN\n  n=42\nEND DEMO')
        result = analyze_source(self.app.document.text)
        self.app.show_analysis(result)
        self.app.go_to_line(4)
        self.app.show_python()
        python_line = int(self.app.python.index('insert').split('.')[0])
        self.assertIn(python_line, generated_lines(result.report['source_map'], 4))
        self.assertTrue(self.app.python.tag_ranges('mapped'))
        self.app.show_source()
        self.assertEqual(self.app.source.index('insert'), '4.2')
        self.assertFalse(self.app.document.dirty)
        self.assertIs(self.app.analysis, result)
        self.app.python.mark_set('insert', '1.0')
        self.app.show_source()
        self.assertEqual(self.app.source.index('insert'), '4.2')
        self.assertIn('No KAREL location', self.app.status.get())

    def test_mapping_buttons_disable_when_source_changes(self):
        self.source('PROGRAM DEMO BEGIN END DEMO')
        self.app.show_analysis(analyze_source(self.app.document.text))
        self.assertEqual(str(self.app.to_python['state']), 'normal')
        self.app.source.insert('end', ' ')
        self.app.show_python()
        self.assertIsNone(self.app.analysis)
        self.assertEqual(str(self.app.to_python['state']), 'disabled')

    def test_visible_gutter_tracks_scrolling_and_syntax_tags(self):
        self.source('\n'.join(f'n={number}' for number in range(200)))
        self.root.deiconify()
        self.root.update()
        self.app.go_to_line(150)
        self.root.update()
        editor = self.app.editors[self.app.source]
        visible = [editor.gutter.itemcget(item, 'text') for item in editor.gutter.find_all()]
        self.assertIn('150', visible)
        self.assertTrue(self.app.source.tag_ranges('syntax_number'))
        self.assertLess(len(visible), 100)

    def test_find_bar_visibility_and_busy_replacement_guard(self):
        self.source('one one')
        self.app.show_find()
        self.assertTrue(self.app.search_visible)
        self.app.query.set('one')
        self.app._set_busy(True)
        self.assertEqual(str(self.app.replace_button['state']), 'disabled')
        self.assertEqual(self.app.replace_all(), 0)
        self.app._set_busy(False)
        self.app.hide_find()
        self.assertFalse(self.app.search_visible)
        self.assertEqual(self.app.source.get('1.0', 'end-1c'), 'one one')

    def test_small_window_reserves_status_bar_when_find_is_open(self):
        self.root.geometry('960x640')
        self.root.deiconify()
        self.app.show_find()
        self.root.update()
        footer = self.app.progress.master
        self.assertGreater(footer.winfo_height(), 20)
        self.assertLessEqual(footer.winfo_y() + footer.winfo_height(), self.root.winfo_height())
        self.assertLessEqual(self.app.panes.winfo_y() + self.app.panes.winfo_height(), footer.winfo_y())
        self.assertGreater(self.app.source.winfo_height(), 100)


if __name__ == '__main__': unittest.main()
