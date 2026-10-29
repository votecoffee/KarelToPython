"""Atomic XML scalar updates through declared record and ARRAY paths."""
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt, translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_xml_input import OPEN,ADD,SCAN,context


PREFIX='''TYPE row_t=ARRAY[2] OF SHORT
child_t=STRUCTURE speed:REAL count:INTEGER label:STRING[4] ENDSTRUCTURE
item_t=STRUCTURE child:child_t bytes:ARRAY[2] OF BYTE grid:ARRAY[2,2] OF INTEGER
 rows:ARRAY[2] OF row_t small:SHORT flag:BOOLEAN point:XYZWPR matrix:POSITION ENDSTRUCTURE'''
DECL='item:item_t f:FILE s,ident,code,n:INTEGER tag:STRING[32]'
CALL="XML_SETVAR(f,'','item',s)"


def program(xml,body=CALL,*,cooperative=False,**options):
    return compile_program(OPEN+ADD+SCAN+body,prefix=PREFIX,decl=DECL,
                           context=context(xml),cooperative=cooperative,**options)[0]


class XMLAggregatePathTests(unittest.TestCase):
    def test_nested_fields_and_all_scalar_categories(self):
        p=program('<item child.speed="1.25" child.count="-7" child.label="test" bytes.1="255" small="-32768" flag="on"/>')
        state=p.run();item=state['ITEM']
        self.assertEqual(item['CHILD'],{'SPEED':1.25,'COUNT':-7,'LABEL':'test'})
        self.assertEqual((item['BYTES'][0],item['SMALL'],item['FLAG'],state['S']),(255,-32768,True,0))
        self.assertEqual(item['BYTES'][1],{'unknown_byte':True})

    def test_complete_flat_array_paths_and_named_subarrays(self):
        state=program('<item grid.1.2="42" rows.2.1="-9"/>').run()
        self.assertEqual((state['ITEM']['GRID'][0][1],state['ITEM']['ROWS'][1][0],state['S']),(42,-9,0))

    def test_case_insensitivity_in_nested_field_paths(self):
        state=program('<item ChIlD.CoUnT="7"/>').run();self.assertEqual(state['ITEM']['CHILD']['COUNT'],7)

    def test_duplicate_canonical_leaf_rejects_entire_update(self):
        for attrs in ('child.count="1" CHILD.COUNT="2"','bytes.1="1" bytes.01="2"',
                      'grid.1.2="1" grid.01.02="2"'):
            p=program('<item '+attrs+'/>');before=p.snapshot()['ITEM'];self.assertEqual(p.run()['S'],2)
            self.assertEqual(p.snapshot()['ITEM'],before)

    def test_late_invalid_path_preserves_every_prior_field(self):
        for key in ('child.missing','child.count.extra','bytes','grid.1','grid.1.1.1','rows.1','grid.0.1','grid.3.1',
                    'grid.-1.1','child..count','child:count','bytes.one','__class__','child.__dict__'):
            p=program(f'<item child.count="7" {key}="1"/>');before=p.snapshot()['ITEM']
            with self.subTest(key=key):
                # '-' is legal XML name content, but none of these are declared leaf paths.
                self.assertIn(p.run()['S'],(2,4));self.assertEqual(p.snapshot()['ITEM'],before)

    def test_late_domain_failure_preserves_narrow_unknown_and_missing_values(self):
        for attrs in ('bytes.1="1" bytes.2="256"','bytes.1="1" small="-32769"',
                      'bytes.1="1" child.count="2147483647"','bytes.1="1" child.speed="NaN"',
                      'bytes.1="1" flag="maybe"','bytes.1="1" child.count="1.0"'):
            p=program('<item '+attrs+'/>');before=p.snapshot()['ITEM']
            with self.subTest(attrs=attrs):self.assertEqual(p.run()['S'],2);self.assertEqual(p.snapshot()['ITEM'],before)

    def test_short_sentinel_retains_ordinary_initialization_contract(self):
        p=program('<item small="32767"/>','item.small=5 '+CALL)
        self.assertEqual(p.run()['ITEM']['SMALL'],{'uninitialized':True})

    def test_nested_string_capacity_returns_capacity_without_partial_updates(self):
        p=program('<item child.count="7" child.label="large"/>');before=p.snapshot()['ITEM']
        self.assertEqual(p.run()['S'],3);self.assertEqual(p.snapshot()['ITEM'],before)

    def test_config_and_position_location_fields_use_existing_guards(self):
        state=program('<item point.config_data.cfg_turn_no1="7" matrix.location.x="12.5"/>').run()
        self.assertEqual((state['S'],state['ITEM']['POINT']['CONFIG_DATA']['CFG_TURN_NO1'],state['ITEM']['MATRIX']['LOCATION']['X']),(0,7,12.5))

    def test_config_turn_limit_and_position_orientation_are_atomic(self):
        for attr in ('point.config_data.cfg_turn_no1="8"','matrix.normal.x="1"','matrix.orient.y="1"','matrix.approach.z="1"'):
            p=program('<item child.count="7" '+attr+'/>');before=p.snapshot()['ITEM']
            with self.subTest(attr=attr):self.assertEqual(p.run()['S'],2);self.assertEqual(p.snapshot()['ITEM'],before)

    def test_success_preserves_retained_reference_storage_identities(self):
        p=program('<item child.count="7" grid.1.2="42"/>')
        item=p._state.values['ITEM'];child=item.values['CHILD'];grid=item.values['GRID']
        count=rt.field_reference(child,'COUNT');cell=rt.index_reference(grid,(1,2))
        p.run();self.assertIs(p._state.values['ITEM'],item);self.assertIs(item.values['CHILD'],child)
        self.assertIs(item.values['GRID'],grid);self.assertEqual((count.raw(),cell.raw()),(7,42))

    def test_empty_element_attributes_are_successful_noop(self):
        p=program('<item/>');before=p.snapshot()['ITEM'];self.assertEqual(p.run()['S'],0);self.assertEqual(p.snapshot()['ITEM'],before)

    def test_budget_failure_retains_entire_target_and_status(self):
        attrs=' '.join(f'grid.{i}.{j}="{i+j}"' for i in (1,2) for j in (1,2))
        # Find a budget boundary inside staging, without assuming parser checkpoint counts.
        found=False
        for budget in range(1,40):
            p=program('<item '+attrs+'/>','s=77 '+CALL);before=p.snapshot()['ITEM']
            try:p.run(max_steps=budget)
            except rt.KarelRuntimeError as error:
                self.assertIn('budget',str(error));self.assertEqual(p.snapshot()['ITEM'],before)
                if p.snapshot()['S']==77:found=True
        self.assertTrue(found)

    def test_nested_status_output_overlap_fails_before_update(self):
        p=program('<item child.count="7"/>',"item.child.count=99 XML_SETVAR(f,'','item',item.child.count)")
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['ITEM']['CHILD']['COUNT'],99)

    def test_user_counter_effect_guards_cover_nested_updates(self):
        with self.assertRaises(TranslationError) as error:
            compile_program('FOR item.child.count=1 TO 2 DO '+CALL+' ENDFOR',prefix=PREFIX,decl=DECL)
        self.assertEqual(error.exception.code,'E_FOR_COUNTER')

    def test_pause_then_apply_resolves_retained_xml_event(self):
        p=program('<item bytes.2="255"/>','PAUSE '+CALL)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['ITEM']['BYTES'][1],255)

    def test_label_dispatch_and_cooperative_paths(self):
        for cooperative in (False,True):
            state=program('<item bytes.1="7"/>','apply:: '+CALL,cooperative=cooperative).run()
            self.assertEqual((state['ITEM']['BYTES'][0],state['S']),(7,0))

    def test_context_roundtrip_retains_xml_bytes_and_narrow_values(self):
        p=program('<item bytes.1="7"/>',CALL+' CLOSE FILE f');p.run()
        config=rt.ExecutionContext.from_config(json.loads(json.dumps(p._state.execution.to_config()))).to_config()
        self.assertEqual(config['files'],p._state.execution.to_config()['files'])

    def test_rooted_directory_xml_input_remains_unchanged(self):
        raw=b'<item grid.2.2="9"/>'
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.xml';path.write_bytes(raw)
            p,_=compile_program(OPEN+ADD+SCAN+CALL+' CLOSE FILE f',prefix=PREFIX,decl=DECL,
                                context=rt.ExecutionContext(files=rt.DirectoryFiles(folder)))
            self.assertEqual(p.run()['ITEM']['GRID'][1][1],9);self.assertEqual(path.read_bytes(),raw)

    def test_linked_library_updates_explicit_owner_struct(self):
        lib=source('LIB','',decl='f:FILE s,ident,code:INTEGER tag:STRING[32]',routines='''ROUTINE apply
BEGIN '''+OPEN+ADD+SCAN+"XML_SETVAR(f,'MAIN','item',s) CLOSE FILE f END apply")
        main=source('MAIN','apply()',decl='item:item_t',routines='ROUTINE apply FROM LIB')
        main=main.replace('VAR item:item_t',PREFIX+' VAR item:item_t')
        project=translate_project({'lib':lib,'main':main}).instantiate(context=context('<item child.count="9"/>'))
        project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['ITEM']['CHILD']['COUNT'],9)


if __name__=='__main__':unittest.main()
