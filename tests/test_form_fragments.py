"""Authored concatenated FTX fragments and sequential tree-group contracts."""
import json
import unittest

from karel2py import runtime as rt
from karel2py.dictionaries import expanded,parse
from tests.test_extended_services import compile_program
from tests.test_forms import CALL,DECL,LOAD,SETUP,context,execute,ftx


def fragment(number,body,attributes=''):
    return '.form '+attributes+'\n$'+str(number)+',part'+str(number)+'\n'+body+'\n.endform\n'


def document(body,*parts,attributes='unnumber'):
    return ftx(body,attributes=attributes,extra=''.join(parts))


TREE_SETUP=SETUP+" values[1]='FLAG' values[2]='N'"


class FormFragmentEditingTests(unittest.TestCase):
    def test_included_complete_form_edits_typed_field(self):
        text=document('+2',fragment(2,'"Amount " "-%4d(0,10)"'))
        values,ctx,_,_=execute(text,keys=('7','ENTER','F3'))
        self.assertEqual((values['N'],values['STATUS']),(7,0))
        self.assertTrue(values['CHANGED'][0]);self.assertIn('   7',ctx.pendant.windows['FORM']['lines'][2])

    def test_multiple_fragments_share_data_and_selection_indices(self):
        text=document('+2 +3',fragment(2,'"-%4d" &new_line'),fragment(3,'"-%10k(clear)"'))
        values,_,_,_=execute(text,keys=('6','ENTER','DOWN','a','b','ENTER','F3'))
        self.assertEqual((values['N'],values['TEXT'],values['CHOSEN'],values['STATUS']),(6,'ab',2,0))
        self.assertEqual(values['CHANGED'][:2],[True,True])

    def test_plain_dictionary_wrapper_can_include_complete_form(self):
        text=document('+4',fragment(2,'"-%4d"'),'$4,wrapper +2\n')
        values,_,_,_=execute(text,keys=('8','ENTER','F3'))
        self.assertEqual((values['N'],values['STATUS']),(8,0))

    def test_repeated_fragment_cannot_alias_service_output(self):
        text=document('+2 &new_line +2',fragment(2,'"-%4d"'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlaps service outputs'):
            execute(text,setup=SETUP+" values[2]='CHOSEN'")

    def test_repeated_fragment_uses_distinct_typed_cells(self):
        text=document('+2 &new_line +2',fragment(2,'"-%4d"'))
        values,_,_,_=execute(text,keys=('4','ENTER','DOWN','8','ENTER','F3'),
            setup=SETUP+" second=2 values[2]='SECOND'",decl=DECL+' second:INTEGER')
        self.assertEqual((values['N'],values['SECOND'],values['STATUS']),(4,8,0))

    def test_nested_dictionary_inclusion_does_not_create_nested_tree(self):
        text=document('"-%t Group" &new_line +2',
            fragment(2,'.tree\n+3'),fragment(3,'.tree\n"-%4d"'))
        values,_,_,_=execute(text,keys=('ENTER','DOWN','9','ENTER','F3'),setup=TREE_SETUP)
        self.assertEqual((values['FLAG'],values['N'],values['STATUS']),(True,9,0))

    def test_fragment_continues_forward_layout_without_implicit_headers(self):
        text=document('"Prefix " +2',fragment(2,'"Suffix" &new_line "- Done"'))
        values,ctx,_,_=execute(text,keys=('ENTER',))
        self.assertEqual(values['STATUS'],0)
        self.assertEqual(ctx.pendant.windows['FORM']['lines'][2].strip(),'Prefix Suffix')

    def test_fragment_can_add_function_labels_and_help(self):
        text=document('+2',fragment(2,'"- Done" ^keys ?help'),
            '$3,keys "" &new_line "" &new_line "Exit" &new_line "" &new_line "HELP"\n$4,help "Fragment help"\n')
        values,ctx,_,_=execute(text,keys=('F5','PREV','ENTER'))
        self.assertEqual((values['KEY'],values['STATUS']),(1008,0))
        self.assertEqual(ctx.pendant.windows['FORM']['lines'][0].strip(),'Editor')

    def test_fragment_preserves_root_numbering_and_inactive_flags(self):
        text=document('@3,4 +2',fragment(2,'"- First" &new_line @4,4 "- Second"'),attributes='')
        values,ctx,_,_=execute(text,keys=('ENTER',),setup=SETUP+' inactive[1]=TRUE')
        self.assertEqual((values['CHOSEN'],values['STATUS']),(2,0))
        self.assertTrue(ctx.pendant.windows['FORM']['lines'][3].startswith(' 2 '))

    def test_fragment_can_edit_an_explicit_output_port(self):
        text=document('+2',fragment(2,'"-%4P"'))
        ctx=context(text,('F4','F3'),ports=rt.PortBank({'DOUT':1},{('DOUT',1):False}))
        values,_,_,_=execute(ctx=ctx,setup=SETUP+" values[1]='DOUT[1]'")
        self.assertEqual(values['STATUS'],0);self.assertTrue(ctx.ports.values['DOUT',1])


class FormFragmentTreeTests(unittest.TestCase):
    def tree_document(self,tail='"- Done"',fragment_body='.tree\n"-%4d" &new_line'):
        return document('"-%t Group" &new_line +2\n'+tail,fragment(2,fragment_body))

    def test_collapsed_inherited_fragment_cannot_be_selected(self):
        text=self.tree_document(tail='.endtree\n"- Done"')
        values,_,_,_=execute(text,keys=('DOWN','ENTER'),setup=TREE_SETUP)
        self.assertEqual((values['CHOSEN'],values['N'],values['STATUS']),(3,1,0))

    def test_expanded_inherited_fragment_can_be_edited(self):
        text=self.tree_document(tail='.endtree\n"- Done"')
        values,_,_,_=execute(text,keys=('ENTER','DOWN','7','ENTER','DOWN','ENTER'),setup=TREE_SETUP)
        self.assertEqual((values['FLAG'],values['N'],values['CHOSEN'],values['STATUS']),(True,7,3,0))
        self.assertEqual(values['CHANGED'][:2],[True,True])

    def test_fragment_without_tree_does_not_inherit_collapsed_group(self):
        text=self.tree_document(tail='',fragment_body='"-%4d"')
        values,_,_,_=execute(text,keys=('DOWN','5','ENTER','F3'),setup=TREE_SETUP)
        self.assertEqual((values['FLAG'],values['N'],values['CHOSEN'],values['STATUS']),(False,5,2,0))

    def test_open_tree_can_continue_across_several_fragments(self):
        text=document('"-%t Group" &new_line +2 +3',
            fragment(2,'.tree\n"-%4d" &new_line'),fragment(3,'.tree\n"-%10k(clear)"'))
        values,_,_,_=execute(text,keys=('ENTER','DOWN','4','ENTER','DOWN','z','ENTER','F3'),
            setup=TREE_SETUP+" values[3]='TEXT'")
        self.assertEqual((values['N'],values['TEXT'],values['CHOSEN'],values['STATUS']),(4,'z',3,0))

    def test_endtree_in_fragment_makes_following_items_independent(self):
        text=self.tree_document(tail='',fragment_body='.tree\n"-%4d" &new_line\n.endtree\n"- Done"')
        values,_,_,_=execute(text,keys=('DOWN','ENTER'),setup=TREE_SETUP)
        self.assertEqual((values['CHOSEN'],values['N'],values['STATUS']),(3,1,0))

    def test_new_tree_replaces_collapsed_predecessor(self):
        text=document('"-%t First" &new_line "-%4d" &new_line +2',
            fragment(2,'"-%t Second" &new_line "-%4d"'))
        values,_,_,_=execute(text,keys=('DOWN','ENTER','DOWN','7','ENTER','F3'),
            setup=TREE_SETUP+" other=FALSE extra=2 values[3]='OTHER' values[4]='EXTRA'",decl=DECL+' other:BOOLEAN extra:INTEGER')
        self.assertEqual((values['FLAG'],values['OTHER'],values['N'],values['EXTRA'],values['CHOSEN'],values['STATUS']),
            (False,True,1,7,4,0))

    def test_new_tree_inside_one_form_is_also_independent(self):
        text=ftx('"-%t First" &new_line "-%4d" &new_line "-%t Second" &new_line "- Done"')
        values,_,_,_=execute(text,keys=('DOWN','ENTER','DOWN','ENTER'),
            setup=TREE_SETUP+" other=FALSE values[3]='OTHER'",decl=DECL+' other:BOOLEAN')
        self.assertEqual((values['FLAG'],values['OTHER'],values['CHOSEN'],values['STATUS']),(False,True,4,0))

    def test_tree_fragment_refresh_uses_live_boolean(self):
        text=self.tree_document(tail='.endtree\n"- Done"')
        ctx=context(text,tuple(dict(key=key,at_ms=25) for key in ('REFRESH','DOWN','8','ENTER','F3')))
        p,_=compile_program(LOAD+TREE_SETUP+' '+CALL,decl=DECL,context=ctx,
            sleep=lambda _:p._state.values.__setitem__('FLAG',True))
        values=p.run();self.assertEqual((values['FLAG'],values['N'],values['STATUS']),(True,8,0))

    def test_editable_tree_latches_before_later_host_value_changes(self):
        text=self.tree_document(tail='.endtree\n"- Done"')
        ctx=context(text,tuple(dict(key=key,at_ms=25) for key in ('DOWN','ENTER')))
        p,_=compile_program(LOAD+TREE_SETUP+' '+CALL,decl=DECL,context=ctx,
            sleep=lambda _:p._state.values.__setitem__('FLAG',True))
        values=p.run()
        self.assertEqual((values['FLAG'],values['N'],values['CHOSEN'],values['STATUS']),(True,1,3,0))

    def test_reentering_fragment_reads_retained_tree_value(self):
        text=self.tree_document(tail='.endtree\n"- Done"')
        values,_,_,_=execute(text,keys=('ENTER','F3','DOWN','6','ENTER','F3'),
            setup=TREE_SETUP,body=CALL+' '+CALL)
        self.assertEqual((values['FLAG'],values['N'],values['CHOSEN'],values['STATUS']),(True,6,2,0))
        self.assertEqual(values['CHANGED'][:2],[False,True])

    def test_display_tree_can_show_included_fragment_on_repaint(self):
        text=document('"%t Group" &new_line +2',fragment(2,'.tree\n"-%4d" &new_line\n.endtree\n"- Done"'))
        ctx=context(text,(dict(key='F3',at_ms=25),))
        p,_=compile_program(LOAD+TREE_SETUP+' '+CALL,decl=DECL,context=ctx,
            sleep=lambda _:p._state.values.__setitem__('FLAG',True))
        values=p.run();self.assertEqual(values['STATUS'],0)
        self.assertTrue(any('   1' in row for row in ctx.pendant.windows['FORM']['lines']))


class FormFragmentGuardTests(unittest.TestCase):
    def assert_rejected(self,text):
        values,ctx,_,_=execute(text,keys=('F3',),setup=TREE_SETUP+' changed[1]=TRUE')
        self.assertEqual(values['STATUS'],1);self.assertTrue(values['CHANGED'][0])
        self.assertNotIn('FORM',ctx.pendant.windows);self.assertEqual(len(ctx.keyboard.events),1)
        self.assertEqual(ctx.forms.active_count,0)

    def test_orphan_tree_marker_is_rejected(self):
        for text in [ftx('.tree\n"- Done"'),document('+2',fragment(2,'.tree\n"- Done"'))]:
            with self.subTest(text=text):self.assert_rejected(text)

    def test_closed_tree_cannot_be_inherited_or_reopened(self):
        for body in ['"-%t Group" &new_line\n.endtree\n+2',
            '"-%t Group" &new_line +3 +2']:
            text=document(body,fragment(2,'.tree\n"- Done"'),fragment(3,'"Unrelated" &new_line'))
            with self.subTest(body=body):self.assert_rejected(text)

    def test_fragment_endtree_prevents_following_inheritance(self):
        text=document('"-%t Group" &new_line +2 +3',
            fragment(2,'.tree\n"-%4d" &new_line\n.endtree'),fragment(3,'.tree\n"- Done"'))
        self.assert_rejected(text)

    def test_conflicting_fragment_attributes_are_rejected(self):
        self.assert_rejected(document('+2',fragment(2,'"- Done"',attributes='noclear')))

    def test_equal_and_subset_fragment_attributes_are_accepted(self):
        for attrs in ('','unnumber','unnumber noclear'):
            values,_,_,_=execute(document('+2',fragment(2,'"- Done"',attrs),attributes='unnumber noclear'),keys=('ENTER',))
            self.assertEqual(values['STATUS'],0)

    def test_fragment_cannot_backtrack_to_replace_root_headers(self):
        self.assert_rejected(document('+2',fragment(2,'&home "Override" &new_line "- Done"')))

    def test_fragment_cannot_add_duplicate_function_declarations(self):
        text=document('^keys +2',fragment(2,'"- Done" ^keys'),'$3,keys "Exit"\n')
        self.assert_rejected(text)

    def test_dictionary_cycles_and_excessive_inclusion_stay_rejected(self):
        docs=[document('+2',fragment(2,'+1')),
            document('+2',*(fragment(i,'+'+str(i+1) if i<6 else '"- Done"') for i in range(2,7)))]
        for text in docs:
            with self.subTest(text=text),self.assertRaises(ValueError):parse(text)

    def test_physical_nested_form_declarations_remain_invalid(self):
        text='.form\n$1,outer\n.form\n$2,inner\n"- Done"\n.endform\n.endform\n'
        with self.assertRaisesRegex(ValueError,'nested form'):parse(text)

    def test_concatenated_rows_still_obey_logical_row_limit(self):
        text=document('+2 +3',fragment(2,'&new_line '*150),fragment(3,'&new_line '*110+'"- Done"'))
        self.assert_rejected(text)

    def test_marker_expansion_retains_fragment_boundaries(self):
        text=document('+2',fragment(2,'.tree\n"- Done"'))
        ops=[token[0] for token in expanded(parse(text),1)]
        self.assertEqual((ops.count('form'),ops.count('endform')),(2,2))

    def test_malformed_expanded_markers_fail_before_mutation(self):
        for tokens in [[('form',()),('form',()),('endform',)],
            [('form',()),('endform',),('text','surprise'),('endform',)]]:
            ctx=context()
            ctx.dictionaries.element=lambda *args,**kwargs:tokens
            values,_,_,_=execute(ctx=ctx,setup=SETUP+' changed[1]=TRUE')
            self.assertEqual(values['STATUS'],1);self.assertTrue(values['CHANGED'][0])
            self.assertNotIn('FORM',ctx.pendant.windows)

    def test_completed_fragment_state_roundtrips_without_live_links(self):
        text=document('+2',fragment(2,'"-%4d"'))
        values,ctx,_,_=execute(text,keys=('7','ENTER','F3'))
        saved=json.loads(json.dumps(ctx.to_config()));restored=rt.ExecutionContext.from_config(saved)
        self.assertEqual(restored.forms.active_count,0)
        self.assertEqual(restored.dictionaries.to_config(),ctx.dictionaries.to_config())
        self.assertEqual(values['N'],7)

    def test_stop_releases_active_fragment_sessions_and_keyboard(self):
        text=document('"-%t Group" &new_line +2',fragment(2,'.tree\n"-%4d"'))
        ctx=context(text,(dict(key='F3',at_ms=25),))
        p,_=compile_program(LOAD+TREE_SETUP+' '+CALL,decl=DECL,context=ctx,
            sleep=lambda _:setattr(p._state,'_pause_requested',True))
        with self.assertRaises(rt.KarelPause):p.run()
        with self.assertRaisesRegex(ValueError,'Finish active forms'):ctx.to_config()
        p.stop();self.assertEqual(ctx.forms.active_count,0)
        self.assertEqual(ctx.keyboard.snapshot()['active'],[]);ctx.to_config()

    def test_missing_keys_cleanup_releases_fragment_links(self):
        text=document('+2',fragment(2,'"- Done"'));ctx=context(text,())
        p,_=compile_program(LOAD+SETUP+' '+CALL,decl=DECL,context=ctx,sleep=lambda _:None)
        with self.assertRaises(rt.KarelRuntimeError):p.run(max_steps=100)
        self.assertEqual(ctx.forms.active_count,0);self.assertEqual(ctx.keyboard.snapshot()['active'],[])
        self.assertEqual(ctx.pendant.screens['SYS']['attachments'],[]);ctx.to_config()


if __name__=='__main__':unittest.main()
