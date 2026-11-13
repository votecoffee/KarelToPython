"""Headless dictionary/form/table paths share chained indexes and live data rows."""
import json
import unittest

from karel2py import runtime as rt
from tests.test_extended_services import compile_program
from tests.test_dictionaries import LOAD as DICT_LOAD,WINDOW,CLOSE,DECL as DICT_DECL
from tests.test_dictionaries import context as dictionary_context,execute as dictionary
from tests.test_forms import LOAD as FORM_LOAD,SETUP as FORM_SETUP,CALL as FORM_CALL,DECL as FORM_DECL,ftx
from tests.test_forms import context as form_context,execute as form
from tests.test_table_controls import SETUP as TABLE_SETUP,TABLE,INIT,DECL as TABLE_DECL
from tests.test_table_controls import context as table_context,execute as table


class DictionaryChainedPathTests(unittest.TestCase):
    def test_read_and_window_write_accept_chained_flat_indexes(self):
        body=DICT_LOAD+WINDOW+"grid[2,1]=7 paths[1]='GRID[2][1]' READ_DICT_V('USER',1,paths,lines,s) WRITE_DICT_V(f,'USER',1,paths,s)"+CLOSE
        values,ctx,_,result=dictionary(body,'$1 "Count=%d"',decl=DICT_DECL+' grid:ARRAY[2,2]OF INTEGER')
        self.assertEqual((values['LINES'][0],values['S']),('Count=7',0))
        self.assertIn('Count=7',ctx.pendant.windows['W1']['lines'][0])
        self.assertEqual(result.report['display_named_path_policy']['guide'],'docs/display-named-rows.md')
        self.assertFalse(result.report['display_named_path_policy']['controller_validated'])

    def test_named_components_and_joint_axes_keep_scalar_formats(self):
        body=DICT_LOAD+"grid[2,1,2]=9 axes[1][2]=1.5 paths[1]='GRID[2][1][2]' paths[2]='AXES[1][2]' READ_DICT_V('USER',1,paths,lines,s)"
        values,_,_,_=dictionary(body,'$1 "%d %.1f"',decl=DICT_DECL+' grid:ARRAY[2]OF plane_t axes:ARRAY[1]OF JOINTPOS2',prefix='TYPE plane_t=ARRAY[2,2]OF INTEGER')
        self.assertEqual((values['LINES'][0],values['S']),('9 1.5',0))

    def test_foreign_and_explicit_system_arrays_use_chained_paths(self):
        ctx=dictionary_context('$1 "%d %d"');schema=('ARRAY',(2,2),rt.INTEGER)
        for owner,path,value in [('CACHE','GRID',7),('SYSTEM','$GRID',9)]:
            ref=ctx.variables.define(owner,path,schema);ref.raw().values[2]=value
        values,_,_,_=dictionary(DICT_LOAD+"paths[1]='[CACHE]GRID[2][1]' paths[2]='[*SYSTEM*].$GRID[2][1]' READ_DICT_V('USER',1,paths,lines,s)",ctx=ctx)
        self.assertEqual((values['LINES'][0],values['S']),('7 9',0))

    def test_rows_remain_incompatible_with_scalar_dictionary_formats(self):
        values,_,_,_=dictionary(DICT_LOAD+"grid[2,1]=7 grid[2,2]=9 lines[1]='keep' paths[1]='GRID[2]' READ_DICT_V('USER',1,paths,lines,s)",
                                 '$1 "%d"',decl=DICT_DECL+' grid:ARRAY[2,2]OF INTEGER')
        self.assertEqual((values['LINES'][0],values['S']),('keep',4))

    def test_path_bank_node_fields_keep_owned_static_lookup(self):
        body=DICT_LOAD+"APPEND_NODE(routes[2],s) routes[2][1].amount=17 paths[1]='ROUTES[2][1].AMOUNT' READ_DICT_V('USER',1,paths,lines,s)"
        values,_,_,_=dictionary(body,'$1 "%d"',decl=DICT_DECL+' routes:ARRAY[2]OF PATH NODEDATA=node_t',prefix='TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE')
        self.assertEqual((values['LINES'][0],values['S']),('17',0))


CHOICES=" choices[2,2]='Red' choices[2,3]='Blue' choices[2,5]='Hidden'"
CHOICE_DECL=FORM_DECL.replace('choices:ARRAY[5]','choices:ARRAY[2,5]')


def choice_form(path='CHOICES[2]'):
    return ftx('"-%6v(options)"',extra='$2,options "T" &new_line "'+path+'"')


class FormNamedRowTests(unittest.TestCase):
    def test_chained_scalar_field_edits_original_cells(self):
        values,_,_,_=form(ftx('"-%4d"'),keys=('5','ENTER','F3'),
                          setup=FORM_SETUP+" grid[2,1]=7 values[1]='GRID[2][1]'",decl=FORM_DECL+' grid:ARRAY[2,2]OF INTEGER')
        self.assertEqual((values['GRID'][1][0],values['STATUS']),(5,0));self.assertTrue(values['CHANGED'][0])

    def test_variable_enum_row_skips_first_and_stops_at_missing_entry(self):
        values,ctx,_,_=form(choice_form(),keys=('F4','DOWN','ENTER','F3'),setup=FORM_SETUP+CHOICES,decl=CHOICE_DECL)
        self.assertEqual((values['N'],values['STATUS']),(2,0))
        self.assertIn('Blue',ctx.pendant.windows['FORM']['lines'][2]);self.assertNotIn('Hidden',ctx.pendant.windows['FORM']['lines'][2])

    def test_named_component_row_and_three_dimensional_chained_row(self):
        decl=FORM_DECL.replace('choices:ARRAY[5] OF STRING[12]','choices:ARRAY[2,2,5] OF STRING[12]')
        for path in ('CHOICES[2,1]','CHOICES[2][1]'):
            values,_,_,_=form(choice_form(path),keys=('F4','DOWN','ENTER','F3'),
                             setup=FORM_SETUP+" choices[2,1,2]='Red' choices[2,1,3]='Blue'",decl=decl)
            self.assertEqual((values['N'],values['STATUS']),(2,0))

    def test_function_key_labels_can_be_a_selected_row(self):
        text=ftx('"-%4d" ^keys',extra='$2,keys "*T" &new_line "*FKEYS[2]"')
        values,ctx,_,_=form(text,keys=('F3',),setup=FORM_SETUP+" fkeys[2,3]='Done'",decl=FORM_DECL.replace('fkeys:ARRAY[5]','fkeys:ARRAY[2,5]'))
        self.assertEqual((values['KEY'],values['STATUS']),(1103,0));self.assertEqual(ctx.forms.active_count,0)

    def test_choice_row_data_cannot_overlap_a_string_field(self):
        text=ftx('"-%6v(options)" &new_line "-%8k"',extra='$2,options "T" &new_line "CHOICES[2]"')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps service outputs/resources'):
            form(text,setup=FORM_SETUP+CHOICES+" values[2]='CHOICES[2][2]'",decl=CHOICE_DECL)

    def test_choice_refresh_uses_original_cells_after_root_list_replacement(self):
        ctx=form_context(choice_form(),keys=({'key':'F3','at_ms':25},));old=[]
        def change(_):
            if old:return
            array=p._state.raw('CHOICES');old.append(array.values);old[0][6]='Gold'
            array.values=[rt.UNINITIALIZED]*10;array.values[6]='Other'
        p,_=compile_program(FORM_LOAD+FORM_SETUP+CHOICES+' '+FORM_CALL,decl=CHOICE_DECL,context=ctx,sleep=change)
        values=p.run();self.assertEqual((values['STATUS'],values['CHOICES'][1][1]),(0,'Other'))
        self.assertIn('Gold',ctx.pendant.windows['FORM']['lines'][2]);self.assertEqual(ctx.forms.active_count,0)

    def test_resizing_live_choice_row_fails_and_releases_session(self):
        ctx=form_context(choice_form(),keys=({'key':'F3','at_ms':25},))
        def resize(_):p._state.raw('CHOICES').values.pop()
        p,_=compile_program(FORM_LOAD+FORM_SETUP+CHOICES+' '+FORM_CALL,decl=CHOICE_DECL,context=ctx,
                            sleep=resize)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'prefix storage'):p.run()
        self.assertEqual(ctx.forms.active_count,0);self.assertEqual(ctx.pendant.screens['SYS']['attachments'],[])


TABLE_ROWS="matrix[2,1]=7 matrix[2,2]=9 names[1,1]='old' names[1,2]='next' paths[1]='MATRIX[2]' paths[2]='NAMES[1]' "
ROW_DECL=TABLE_DECL+' matrix:ARRAY[2,2]OF INTEGER names:ARRAY[2,2]OF STRING[20]'


class TableNamedRowTests(unittest.TestCase):
    def test_editing_selected_integer_and_string_rows_writes_original_cells(self):
        values,ctx,_,_=table(TABLE_ROWS+TABLE,keys=('5','ENTER','RIGHT','x','ENTER','SELECT'),decl=ROW_DECL)
        self.assertEqual((values['MATRIX'][1],values['NAMES'][0],values['S']),([5,9],['OLDX','next'],0))
        self.assertEqual(values['DATA'],[1,2]);self.assertEqual(ctx.table_controls.active_count,0)

    def test_cube_chained_row_and_foreign_system_row(self):
        ctx=table_context(('5','ENTER','SELECT'));schema=('ARRAY',(2,2),rt.INTEGER)
        root=ctx.variables.define('SYSTEM','$GRID',schema);root.raw().values[2:]=[7,9]
        values,_,_,_=table("paths[1]='[*SYSTEM*].$GRID[2]' "+TABLE,ctx=ctx)
        self.assertEqual((root.raw().values[2:],values['S']),([5,9],0))
        values,_,_,_=table("cube[2,1,1]=7 cube[2,1,2]=9 paths[1]='CUBE[2][1]' "+TABLE,
                           keys=('5','ENTER','SELECT'),decl=TABLE_DECL+' cube:ARRAY[2,2,2]OF INTEGER')
        self.assertEqual((values['CUBE'][1][0],values['S']),([5,9],0))

    def test_selected_row_still_cannot_overlap_service_outputs(self):
        values,ctx,_,_=table("cols[1].item_type=TPX_KBL_ITEM paths[1]='CHANGED[1]' "+INIT)
        self.assertEqual(values['S'],1);self.assertEqual(values['PTRS'][0][0],{'uninitialized':True})
        self.assertEqual(len(ctx.keyboard.events),1);self.assertEqual(ctx.table_controls.active_count,0)

    def test_invalid_containing_data_fails_before_flags_or_input_change(self):
        ctx=table_context(('SELECT',));p,_=compile_program(TABLE_SETUP+' '+TABLE_ROWS+TABLE,decl=ROW_DECL,context=ctx)
        p._state.raw('MATRIX').values[0]='bad'
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['CHANGED'][0][0],{'uninitialized':True});self.assertEqual(len(ctx.keyboard.events),1)

    def test_root_replacement_keeps_original_table_cells_without_copyback(self):
        ctx=table_context(({'key':'5','at_ms':25},{'key':'ENTER','at_ms':25},{'key':'SELECT','at_ms':25}));old=[]
        def change(_):
            if old:return
            array=p._state.raw('MATRIX');old.append(array.values);array.values=[1,2,99,100]
        p,_=compile_program(TABLE_SETUP+' '+TABLE_ROWS+TABLE,decl=ROW_DECL,context=ctx,sleep=change)
        values=p.run();self.assertEqual((old[0][2:],values['MATRIX'][1],values['S']),([5,9],[99,100],0))
        self.assertEqual(ctx.table_controls.active_count,0)

    def test_resizing_retained_table_row_fails_before_cell_write(self):
        ctx=table_context(({'key':'5','at_ms':25},{'key':'ENTER','at_ms':25}));changed=[]
        def resize(_):
            if changed:return
            changed.append(True);p._state.raw('MATRIX').values.pop()
        p,_=compile_program(TABLE_SETUP+' '+TABLE_ROWS+TABLE,decl=ROW_DECL,context=ctx,sleep=resize)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'prefix storage'):p.run()
        self.assertEqual(p._state.raw('MATRIX').values[2],7);self.assertEqual(ctx.table_controls.active_count,0)

    def test_saved_ordinary_roots_do_not_register_live_row_aliases(self):
        _,ctx,_,_=table(TABLE_ROWS+TABLE,decl=ROW_DECL)
        saved=json.loads(json.dumps(ctx.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
        self.assertTrue(all(row['path'] not in ('MATRIX[2]','NAMES[1]') for row in saved['variables']))


if __name__=='__main__':unittest.main()
