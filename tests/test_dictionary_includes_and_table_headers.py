"""Checked dictionary include products, table header controls and form system paths."""
import unittest

from karel2py import runtime as rt, translate
from karel2py.includes import IncludeLibrary
from tests.test_extended_services import compile_program
from tests.test_forms import CALL, DECL as FORM_DECL, LOAD, SETUP as FORM_SETUP
from tests.test_forms import context as form_context, execute as run_form, ftx
from tests.test_kcl_task_commands import issue
from tests.test_table_controls import ACT, CANCEL, DECL, DISPLAY, INIT, SETUP, TABLE
from tests.test_table_controls import context as table_context, execute as run_table


class DictionaryIncludeTests(unittest.TestCase):
    def context(self, files):
        return rt.ExecutionContext(files=rt.MemoryFiles(files), dictionaries=rt.TextDictionaries(),
                                   kcl=rt.KclCommands(dictionary_commands=True))

    def test_generated_dictionary_constants_compile_and_match_loaded_elements(self):
        ctx = self.context({'text/Menu.UTX': '* heading\r\n.kl Names.KL\r\n$home "Home"\r\n$\r\n"Hidden"\r\n$3, ExitPage, "Exit"\r\n'})
        self.assertEqual(issue(ctx, 'COMPRESS DICT text/Menu', nowait=True), {'S': 0, 'N': 0})
        content = ctx.files.snapshot()['text/Names.KL'].decode('ascii')
        self.assertEqual(content, 'CONST\n  HOME = 0\n  EXITPAGE = 3\n')
        self.assertEqual(issue(ctx, 'LOAD DICT text/Menu MENU')['S'], 0)
        self.assertNotIn('.kl', ctx.dictionaries.loaded['ENGLISH']['MENU']['text'])
        translated = translate(
            "PROGRAM T\n%INCLUDE Names\nVAR n,status:INTEGER\nBEGIN n=ExitPage CHECK_DICT('MENU',HOME,status) END T",
            includes=IncludeLibrary({'Names.KL': content}),
        )
        namespace = {'__name__': 'dictionary_include_test'}
        exec(translated.python_source, namespace)
        self.assertEqual(namespace['Program'](context=ctx).run(), {'N': 3, 'STATUS': 0})

    def test_form_include_collision_keeps_all_products_unpublished(self):
        ftx_source = '.kl Symbols\n' + ftx(extra='$3,exit_label "Exit"')
        ctx = self.context({'FORM.FTX': ftx_source, 'Symbols.KL': 'existing'})
        before = ctx.files.snapshot()
        self.assertEqual(issue(ctx, 'COMPRESS FORM')['S'], 402)
        self.assertEqual(ctx.files.snapshot(), before)
        del ctx.files.files['Symbols.KL']
        self.assertEqual(issue(ctx, 'COMPRESS FORM')['S'], 0)
        self.assertEqual(ctx.files.snapshot()['Symbols.KL'], b'CONST\n  EDITOR = 1\n  EXIT_LABEL = 3\n')
        del ctx.files.files['Symbols.KL']
        self.assertEqual(issue(ctx, 'LOAD FORM')['S'], 0)

    def test_invalid_include_name_or_constants_leave_source_and_targets_intact(self):
        for content in ('.kl ../escape\n$good "value"', '.kl Symbols\n$read "reserved"',
                        '.kl Symbols\n$Label "first"\n$label "second"', '.kl Symbols\n$1 "unnamed"'):
            with self.subTest(content=content):
                ctx = self.context({'ITEM.UTX': content})
                before = ctx.files.snapshot()
                self.assertEqual(issue(ctx, 'COMPRESS DICT ITEM')['S'], 401)
                self.assertEqual(ctx.files.snapshot(), before)


TABLE_TEXT = (
    '$title &home @1,3 &reverse "Title" &standard &new_line "Row" ^1 ?2\n'
    '$keys "Exit" &new_line "" &new_line "" &new_line "" &new_line "HELP"\n'
    '$tips "Tip 1" &new_line "Tip 2" &new_line "Tip 3" &new_line "Tip 4" &new_line "Tip 5"'
)


class TableHeaderTests(unittest.TestCase):
    def context(self, keys=(), text=TABLE_TEXT):
        ctx = table_context(keys)
        ctx.dictionaries = rt.TextDictionaries(sources={'header': text})
        return ctx

    def test_blocking_table_uses_header_controls_and_consumes_help_keys(self):
        ctx = self.context(('F2', 'F5', 'DOWN', 'PREV', 'F1'))
        values, _, _, _ = run_table(TABLE.replace("'HEAD',1", "'HEAD',0"), ctx=ctx)
        self.assertEqual((values['ROW'], values['KEY'], values['S']), (1, 1101, 0))
        self.assertEqual(values['DATA'], [1, 2])
        self.assertEqual([line.rstrip() for line in ctx.pendant.windows['TABL']['lines'][:2]],
                         ['  Title', 'Row'])
        self.assertEqual(ctx.keyboard.events, [])
        self.assertEqual(ctx.table_controls.active_count, 0)

    def test_split_table_help_is_visible_and_restores_body_after_prev(self):
        ctx = self.context(('PAGE_DOWN', 'PREV'))
        views = []

        def observe(_text):
            views.append((list(ctx.pendant.windows['TABL']['lines']), ctx.table_controls.snapshot()['active'][0]))

        initialize = INIT.replace("'HEAD',1", "'HEAD',0")
        body = (SETUP + ' ' + initialize + ' ' + DISPLAY
                + " ACT_TBL(KY_HELP,row,work,key,attach,s) WRITE('help') "
                + ' action=KY_REISSUE ' + ACT + " WRITE('down') "
                + ' action=KY_REISSUE ' + ACT + " WRITE('back') " + CANCEL)
        task, _ = compile_program(body, decl=DECL, context=ctx, sleep=lambda _: None, write=observe)
        self.assertEqual(task.run()['S'], 0)
        self.assertEqual([view[0][0].rstrip() for view in views], ['Tip 1', 'Tip 2', '  Title'])
        self.assertEqual([view[1]['help'] for view in views], [True, True, False])
        self.assertEqual(views[0][1]['function_keys'], ['Exit', '', '', '', 'HELP'])
        self.assertEqual(ctx.table_controls.active_count, 0)

    def test_header_errors_precede_attachment_and_key_consumption(self):
        for text in ('$0 @1,2 "X" @1,1 "Y"', '$0 "X" ^1 ^1\n$1 "F1"',
                     '$0 "X" ?1\n$1 "Text that is longer than the window"'):
            with self.subTest(text=text):
                ctx = self.context(('SELECT',), text)
                values, _, _, _ = run_table(TABLE.replace("'HEAD',1", "'HEAD',0"), ctx=ctx)
                self.assertEqual((values['S'], ctx.keyboard.request_sequence), (1, 0))
                self.assertEqual(ctx.table_controls.active_count, 0)
                self.assertEqual(ctx.pendant.screens['SYS']['attachments'], [])


class FormSystemPathTests(unittest.TestCase):
    def test_documented_system_qualifier_edits_an_explicit_binding(self):
        ctx = form_context(keys=('5', 'ENTER', 'F3'))
        selected = ctx.variables.define('SYSTEM', '$RATE', ('INTEGER',), 2)
        other = ctx.variables.define('T', '$RATE', ('INTEGER',), 3)
        values, _, _, _ = run_form(ctx=ctx, setup=FORM_SETUP + " values[1]='[*system*]$RATE'")
        self.assertEqual((values['STATUS'], values['CHANGED'][0], selected.raw(), other.raw()), (0, True, 5, 3))

    def test_system_paths_retain_exact_overlap_guards(self):
        ctx = form_context(keys=('5', 'ENTER', 'F3'))
        task, _ = compile_program(LOAD + FORM_SETUP + " values[1]='[*SYSTEM*]$RATE' " + CALL,
                                 decl=FORM_DECL, context=ctx)
        ctx.variables.bind('SYSTEM', '$RATE', task._state.reference('STATUS'))
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'overlaps service outputs'):
            task.run()
        self.assertEqual(ctx.keyboard.request_sequence, 0)
        self.assertEqual(ctx.forms.active_count, 0)


if __name__ == '__main__':
    unittest.main()
