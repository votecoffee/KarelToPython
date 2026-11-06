"""Portable table choices and shared, explicit system value paths."""
import unittest

from karel2py import runtime as rt
from tests.test_dictionaries import CLOSE, LOAD, WINDOW, context as dictionary_context, execute as run_dictionary
from tests.test_extended_services import compile_program
from tests.test_forms import SETUP as FORM_SETUP
from tests.test_forms import context as form_context, execute as run_form
from tests.test_kcl_debug_commands import context as debug_context
from tests.test_kcl_inspection_commands import listing
from tests.test_kcl_task_commands import issue
from tests.test_table_controls import ACT, CANCEL, DECL, DISPLAY, INIT, SETUP, TABLE
from tests.test_table_controls import context as table_context, execute as run_table
from tests.test_task_control_broadcasts import worker


FUNCTION="cols[1].item_type=TPX_FKY_ITEM cols[1].enum_dict='HEAD' cols[1].enum_ele=3 "
SUBMENU="cols[1].item_type=TPX_SUB_ITEM cols[1].enum_dict='HEAD' cols[1].enum_ele=4 "


class TableChoiceTests(unittest.TestCase):
    def test_function_choice_uses_the_cell_labels_before_header_and_mask(self):
        ctx = table_context(('F1', 'F10', 'SELECT'))
        text = '$1 "Heading" ^2\n$2 "Header"\n$3 ""' + ' &new_line ""'*8 + ' &new_line "Tenth"'
        ctx.dictionaries = rt.TextDictionaries(sources={'header': text})
        values, _, _, _ = run_table(FUNCTION + TABLE, ctx=ctx)
        self.assertEqual((values['DATA'], values['KEY'], values['S']), ([10,2],1008,0))
        self.assertTrue(values['CHANGED'][0][0])
        self.assertIn('Tenth', ctx.pendant.windows['TABL']['lines'][1])
        self.assertEqual(ctx.keyboard.events, [])

    def test_submenu_cancel_then_page_and_select_thirty_fifth_value(self):
        ctx = table_context(('F4', 'DOWN', 'PREV', 'F4', 'PAGE_DOWN', 'END', 'SELECT', 'SELECT'))
        text = '$1 "Options"\n' + '\n'.join(f'${index+3} "Item {index}"' for index in range(1,36)) + '\n$ "\\a"'
        ctx.dictionaries = rt.TextDictionaries(sources={'header': text})
        values, _, _, _ = run_table(SUBMENU + TABLE, ctx=ctx)
        self.assertEqual((values['DATA'],values['ROW'],values['KEY'],values['S']), ([35,2],1,1008,0))
        self.assertEqual(values['CHANGED'], [[True,False],[False,False]])
        self.assertIn('Item 35', ctx.pendant.windows['TABL']['lines'][1])

    def test_split_table_submenu_retires_choice_if_caller_moves_row(self):
        ctx = table_context(('F4','DOWN','SELECT'))
        observed = []

        def observe(_text):
            observed.append(ctx.table_controls.snapshot()['active'][0])

        reissue = ' action=KY_REISSUE ' + ACT
        body = (SETUP + ' ' + SUBMENU + INIT + ' ' + DISPLAY + reissue + reissue
                + " WRITE('choice') row=2 " + reissue + " WRITE('after') " + CANCEL)
        task, _ = compile_program(body, decl=DECL, context=ctx, write=observe, sleep=lambda _:None)
        values = task.run()
        self.assertEqual(observed[0]['choice'], {'index':2,'labels':['Small','Large']})
        self.assertNotIn('choice',observed[1])
        self.assertEqual((values['DATA'],values['ACTION'],values['S']), ([1,2],1008,0))
        self.assertEqual(values['CHANGED'], [[False,False],[False,False]])

    def test_boolean_keys_and_unsimulated_input_follow_cell_writability(self):
        values, _, _, _ = run_table("cols[1].item_type=TPX_KBL_ITEM paths[1]='FLAGS' "+TABLE,
                                   keys=('F4','DOWN','F5','SELECT'))
        self.assertEqual(values['FLAGS'], [True,False])
        self.assertEqual(values['CHANGED'], [[True,False],[True,False]])
        bank = rt.PortBank({'DIN':2},{('DIN',1):False,('DIN',2):True})
        ctx = table_context(('RIGHT','F4'),ports=bank)
        values, _, _, _ = run_table("cols[2].item_type=TPX_PBL_ITEM words[1]='DIN[1]' words[2]='DIN[2]' "+TABLE,ctx=ctx)
        self.assertEqual((values['KEY'],bank.values['DIN',1],values['CHANGED'][0][1]), (1008,False,False))

    def test_descriptor_range_rejects_function_or_submenu_choice_before_commit(self):
        for setup,keys in ((FUNCTION,('F2',)),(SUBMENU,('F4','DOWN','ENTER'))):
            with self.subTest(setup=setup):
                values, ctx, _, _ = run_table(setup+' cols[1].max_integer=1 '+TABLE,keys=keys)
                self.assertEqual((values['DATA'],values['S']), ([1,2],1))
                self.assertEqual(values['CHANGED'], [[False,False],[False,False]])
                self.assertEqual(ctx.table_controls.active_count,0)


class SharedSystemValuePathTests(unittest.TestCase):
    def test_dictionary_read_and_write_render_only_explicit_system_binding(self):
        body = (LOAD+WINDOW+"paths[1]='[*system*].$TEST.$LIMIT' READ_DICT_V('USER',1,paths,lines,s) "
                +"WRITE_DICT_V(f,'USER',1,paths,s)"+CLOSE)
        ctx=dictionary_context('$1 "Limit=%d"')
        ctx.variables.define('SYSTEM','$TEST.$LIMIT',('INTEGER',),37)
        ctx.variables.define('T','$TEST.$LIMIT',('INTEGER',),99)
        values, ctx, _, _ = run_dictionary(body,'$1 "Limit=%d"',ctx=ctx)
        self.assertEqual((values['LINES'][0],values['S']),('Limit=37',0))
        self.assertIn('Limit=37',ctx.pendant.windows['W1']['lines'][0])

    def test_dictionary_missing_system_path_keeps_preexisting_output(self):
        body = LOAD+"lines[1]='prior' paths[1]='[*SYSTEM*].$UNSUPPLIED' READ_DICT_V('USER',1,paths,lines,s)"
        values, _, _, _ = run_dictionary(body,'$1 "%d"')
        self.assertEqual((values['LINES'][0],values['S']),('prior',4))

    def test_forms_and_tables_share_the_documented_optional_dot(self):
        ctx=form_context(keys=('5','ENTER','F3'))
        value=ctx.variables.define('SYSTEM','$RATE',('INTEGER',),2)
        values, _, _, _ = run_form(ctx=ctx,setup=FORM_SETUP+" values[1]='[*SYSTEM*].$RATE'")
        self.assertEqual((values['STATUS'],value.raw()),(0,5))

        ctx=table_context(('7','ENTER','SELECT'))
        array=rt.Array(('ARRAY',2,('INTEGER',)))
        array.values[:]=[4,8]
        value=ctx.variables.define('SYSTEM','$COUNTS',array.spec,array)
        values, _, _, _ = run_table("paths[1]='[*SYSTEM*].$COUNTS' "+TABLE,ctx=ctx)
        self.assertEqual((values['S'],value.raw().values,values['DATA']),(0,[7,8],[1,2]))


class KclConditionBreakpointListingTests(unittest.TestCase):
    def test_condition_listing_tracks_arm_and_clear_with_debug_enabled(self):
        ctx=debug_context()
        task=worker(ctx,'WORKER','CONDITION[1]: WHEN n=1 DO s=1 ENDCONDITION\nPAUSE')
        with self.assertRaises(rt.KarelPause):task.run()
        for command,expected in ((None,False),('SET BREAK COND WORKER 1',True),('CLEAR BREAK COND WORKER 1',False)):
            if command is not None:self.assertEqual(issue(ctx,command)['S'],0)
            code,rows=listing(ctx,'SHOW CONDITION WORKER 1')
            self.assertEqual((code,rows[0]['breakpoint']),(0,expected))
        task.stop()


if __name__ == '__main__':
    unittest.main()
