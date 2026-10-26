"""Authored XML input, checked outputs, text chunks and dynamic field updates."""
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run


DECL='f: FILE tag,text: STRING[32] ident,code,n,s: INTEGER names,values: ARRAY[2] OF STRING[32] done: BOOLEAN'
OPEN="SET_FILE_ATR(f,ATR_XML) OPEN FILE f('RO','input.xml') "
ADD="XML_ADDTAG(f,'item',254,FALSE,7,s) "
SCAN='XML_SCAN(f,tag,ident,code,s) '
DATA='XML_GETDATA(f,n,names,values,text,done,s) '


def context(text): return rt.ExecutionContext(files=rt.MemoryFiles({'input.xml':text}))


class XMLScanningTests(unittest.TestCase):
    def test_registered_events_ignore_unregistered_tags_and_keep_order(self):
        ctx=context('<root><ignored/><item a="7">hello</item><item/></root>')
        data=run(OPEN+ADD+SCAN+'first=code hit=s '+DATA+' '+SCAN+'second=code '+SCAN+'third=code '+SCAN,decl=DECL+' first,second,third,hit: INTEGER',context=ctx)
        self.assertEqual((data['FIRST'],data['SECOND'],data['THIRD'],data['HIT']),(100,101,101,1001))
        self.assertEqual((data['N'],data['NAMES'][0],data['VALUES'][0],data['TEXT'],data['DONE']),(1,'a','7','hello',True))
        self.assertEqual((data['S'],data['IDENT'],data['TAG'],data['CODE']),(0,0,'',101))

    def test_self_closing_event_retains_attributes_and_end_code(self):
        data=run(OPEN+ADD+SCAN+DATA,decl=DECL,context=context('<item key="value"/>'))
        self.assertEqual((data['CODE'],data['N'],data['NAMES'][0],data['VALUES'][0],data['DONE']),(101,1,'key','value',True))

    def test_comments_declarations_cdata_and_builtin_entities(self):
        data=run(OPEN+ADD+SCAN+DATA,decl=DECL,context=context('<?xml version="1.0"?><!-- note --><item x="&lt;&amp;&quot;">a<![CDATA[<b>]]>&gt;</item>'))
        self.assertEqual((data['TEXT'],data['VALUES'][0]),('a<b>>','<&"'))

    def test_case_flag_and_prefix_registration(self):
        for registered,count,case,ident in (('ITEM',254,'TRUE',0),('ITEM',254,'FALSE',7),('ite',3,'TRUE',7)):
            with self.subTest(case=case,registered=registered):
                data=run(OPEN+f"XML_ADDTAG(f,'{registered}',{count},{case},7,s) "+SCAN,decl=DECL,context=context('<items/>'))
                self.assertEqual(data['IDENT'],ident if count==3 else 0)
        self.assertEqual(run(OPEN+"XML_ADDTAG(f,'ITEM',254,FALSE,7,s) "+SCAN,decl=DECL,context=context('<item/>'))['IDENT'],7)

    def test_text_continuations_with_smaller_output_capacity(self):
        decl=DECL.replace('tag,text: STRING[32]','tag: STRING[32] text: STRING[3]')+' first,second: STRING[3] more: BOOLEAN'
        data=run(OPEN+ADD+SCAN+DATA+' first=text more=done '+SCAN+' n=code '+DATA+' second=text '+DATA,decl=decl,context=context('<item>abcdefg</item>'))
        self.assertEqual((data['FIRST'],data['SECOND'],data['TEXT'],data['MORE'],data['DONE']),('abc','def','g',False,True))
        self.assertEqual((data['CODE'],data['S']),(103,0))

    def test_scan_without_reading_text_advances_to_next_tag(self):
        data=run(OPEN+ADD+SCAN+SCAN,decl=DECL,context=context('<item>long text</item>'))
        self.assertEqual((data['CODE'],data['S']),(101,1001))

    def test_fifty_line_scan_limits_retain_future_registered_event(self):
        ctx=context('<root>'+('\n'*101)+'<item/></root>')
        data=run(OPEN+ADD+SCAN+'a=s '+SCAN+' b=s '+SCAN,decl=DECL+' a,b: INTEGER',context=ctx)
        self.assertEqual((data['A'],data['B'],data['S'],data['IDENT']),(1002,1002,1001,7))

    def test_empty_unregistered_file_hits_limits_then_eof(self):
        data=run(OPEN+SCAN+'n=s '+SCAN,decl=DECL,context=context('<root>'+('\n'*51)+'</root>'))
        self.assertEqual((data['N'],data['S'],data['IDENT']),(1002,0,0))

    def test_scan_destination_capacity_preserves_outputs_and_allows_retry(self):
        data=run(OPEN+ADD+"small='old' ident=8 code=9 XML_SCAN(f,small,ident,code,s) failed=s "+SCAN,decl=DECL+' small: STRING[3] failed: INTEGER',context=context('<item/>'))
        self.assertEqual((data['SMALL'],data['FAILED'],data['TAG'],data['IDENT']),('old',3,'item',7))

    def test_getdata_array_and_element_capacity_fail_without_consuming_text(self):
        for xml in ('<item a="1" b="2" c="3">hello</item>','<item very_long_attribute="1">hello</item>'):
            decl=DECL.replace('OF STRING[32]','OF STRING[4]')
            data=run(OPEN+ADD+SCAN+"n=99 text='old' done=TRUE "+DATA,decl=decl,context=context(xml))
            self.assertEqual((data['N'],data['TEXT'],data['DONE'],data['S']),(99,'old',True,3))

    def test_current_tag_cannot_be_removed_then_eof_allows_removal(self):
        data=run(OPEN+ADD+SCAN+"XML_REMTAG(f,'item',s) n=s "+SCAN+"XML_REMTAG(f,'item',s)",decl=DECL,context=context('<item/>'))
        self.assertEqual((data['N'],data['S']),(1,0))

    def test_registration_duplicates_reserved_identifiers_and_ranges(self):
        for name,count,ident in (('bad name',1,7),('item',0,7),('item',255,7),('item',254,0),('item',254,1001),('item',254,1002)):
            with self.subTest(name=name,count=count,ident=ident):
                self.assertEqual(run(OPEN+f"XML_ADDTAG(f,'{name}',{count},FALSE,{ident},s)",decl=DECL,context=context('<item/>'))['S'],2)
        data=run(OPEN+ADD+ADD+' n=s '+SCAN,decl=DECL,context=context('<item/>'))
        self.assertEqual((data['N'],data['IDENT']),(2,7))

    def test_data_before_scan_preserves_outputs(self):
        data=run(OPEN+"n=99 text='old' done=TRUE "+DATA,decl=DECL,context=context('<item/>'))
        self.assertEqual((data['N'],data['TEXT'],data['DONE'],data['S']),(99,'old',True,1))

    def test_malformed_xml_is_prevalidated_and_returns_diagnostic(self):
        for xml in ('<item><other></item>','<item/><item/>','<item a="1" a="2"/>','<item>','<item>&unknown;</item>'):
            with self.subTest(xml=xml):
                data=run(OPEN+ADD+SCAN,decl=DECL,context=context(xml))
                self.assertEqual((data['S'],data['IDENT'],data['CODE'],data['TAG']),(4,-1,0,''))

    def test_dtd_entities_nonascii_and_depth_are_rejected(self):
        for xml in ('<!DOCTYPE item [<!ENTITY x "bad">]><item>&x;</item>','<!DOCTYPE item SYSTEM "file:///missing"><item/>','<item>&#233;</item>',b'<item>\xff</item>','<a>'*65+'</a>'*65):
            with self.subTest(xml=str(xml)[:60]):
                self.assertEqual(run(OPEN+ADD+SCAN,decl=DECL,context=context(xml))['S'],4)

    def test_large_input_is_bounded_before_scanning(self):
        data=run(OPEN+SCAN,decl=DECL,context=context('<root>'+(' '*1048576)+'</root>'))
        self.assertEqual((data['S'],data['IDENT']),(5,-1))

    def test_file_mode_attribute_and_regular_reads_are_checked(self):
        cases=("OPEN FILE f('RO','input.xml') "+ADD, 'SET_FILE_ATR(f,ATR_XML) '+ADD,
            "SET_FILE_ATR(f,ATR_XML) OPEN FILE f('RW','input.xml')",OPEN+'READ f(n)',OPEN+'SET_FILE_POS(f,0,s)')
        for body in cases:
            with self.subTest(body=body),self.assertRaises(rt.KarelRuntimeError):run(body,decl=DECL,context=context('<item/>'))

    def test_close_reopen_discards_registration_and_scanner(self):
        data=run(OPEN+ADD+SCAN+"CLOSE FILE f OPEN FILE f('RO','input.xml') "+SCAN,decl=DECL,context=context('<item/>'))
        self.assertEqual((data['S'],data['IDENT']),(0,0))

    def test_pause_resume_keeps_pending_text_and_live_position(self):
        ctx=context('<item>hello</item>');p,_=compile_program(OPEN+ADD+SCAN+'PAUSE '+DATA,decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        before=p.snapshot()['F']['position'];data=p.resume()
        self.assertEqual((data['TEXT'],data['S'],data['F']['position']),('hello',0,before))

    def test_rejected_data_capacity_can_be_retried_without_consuming_text(self):
        decl=DECL+' big_names,big_values: ARRAY[4] OF STRING[32] failed: INTEGER'
        data=run(OPEN+ADD+SCAN+DATA+' failed=s XML_GETDATA(f,n,big_names,big_values,text,done,s)',decl=decl,context=context('<item a="1" b="2" c="3">hello</item>'))
        self.assertEqual((data['FAILED'],data['S'],data['N'],data['TEXT']),(3,0,3,'hello'))

    def test_explicit_xml_parse_budget_preserves_scan_outputs(self):
        p,_=compile_program(OPEN+ADD+"tag='old' ident=8 code=9 s=77 "+SCAN,decl=DECL,context=context('<root>'+'<item/>'*20+'</root>'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'budget'):p.run(max_steps=15)
        self.assertEqual((p.snapshot()['TAG'],p.snapshot()['IDENT'],p.snapshot()['CODE'],p.snapshot()['S']),('old',8,9,77))

    def test_changed_backend_input_is_rejected(self):
        ctx=context('<item/>');p,_=compile_program(OPEN+ADD+'PAUSE '+SCAN,decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelPause):p.run()
        ctx.files.files['input.xml'][:]=b'<other/>'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'changed'):p.resume()

    def test_directory_backend_reads_and_closes_without_modifying_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'input.xml';path.write_text('<item/>',encoding='ascii')
            ctx=rt.ExecutionContext(files=rt.DirectoryFiles(temporary))
            data=run(OPEN+ADD+SCAN+'CLOSE FILE f',decl=DECL,context=ctx)
            self.assertEqual((data['IDENT'],path.read_text()),(7,'<item/>'));self.assertFalse(ctx.files.handles)


class XMLVariableTests(unittest.TestCase):
    PREFIX='TYPE item_t=STRUCTURE number: INTEGER value: REAL enabled: BOOLEAN label: STRING[8] spare: INTEGER ENDSTRUCTURE'
    DECL=DECL+' item: item_t'

    def execute(self,xml,tail=''):
        return compile_program(OPEN+ADD+SCAN+"XML_SETVAR(f,'','item',s) "+tail,prefix=self.PREFIX,decl=self.DECL,context=context(xml))[0]

    def test_flat_fields_convert_atomically_and_preserve_unmentioned_values(self):
        data=self.execute('<item NUMBER="42" value="1.25" enabled="1" label="hello"/>').run()
        self.assertEqual(data['ITEM'],{'NUMBER':42,'VALUE':1.25,'ENABLED':True,'LABEL':'hello','SPARE':{'uninitialized':True}})
        self.assertEqual(data['S'],0)

    def test_bad_later_field_unknown_name_duplicates_and_capacity_do_not_partially_write(self):
        for xml,code in (('<item number="42" value="NaN"/>',2),('<item number="42" enabled="bad"/>',2),('<item number="42" missing="1"/>',2),('<item number="42" NUMBER="7"/>',2),('<item number="42" label="too long label"/>',3)):
            with self.subTest(xml=xml):
                data=self.execute(xml).run();self.assertEqual(data['S'],code)
                self.assertEqual(data['ITEM']['NUMBER'],{'uninitialized':True})

    def test_missing_target_wrong_type_and_end_without_attributes(self):
        for target,code in (('absent',1),('n',2)):
            p,_=compile_program(OPEN+ADD+SCAN+f"XML_SETVAR(f,'','{target}',s)",decl=DECL,context=context('<item/>'))
            self.assertEqual(p.run()['S'],code)
        self.assertEqual(self.execute('<item></item>',SCAN+"XML_SETVAR(f,'','item',s)").run()['S'],1)

    def test_target_status_overlap_is_rejected(self):
        p,_=compile_program(OPEN+ADD+SCAN+"item.number=99 XML_SETVAR(f,'','item',item.number)",prefix=self.PREFIX,decl=self.DECL,context=context('<item number="42"/>'))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['ITEM']['NUMBER'],99)

    def test_direct_indirect_and_handler_counter_guards(self):
        call="XML_SETVAR(f,'','item',s)"
        for body,routines in ((f'FOR n=1 TO 2 DO {call} ENDFOR',''),('FOR n=1 TO 2 DO apply_xml() ENDFOR','ROUTINE apply_xml BEGIN '+call+' END apply_xml'),('CONDITION[1]: WHEN TRUE DO '+call+' ENDCONDITION FOR n=1 TO 2 DO ENDFOR','')):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:compile_program(body,decl=self.DECL,prefix=self.PREFIX,routines=routines)
            self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_scan_and_data_outputs_must_be_disjoint(self):
        for call in ('XML_SCAN(f,tag,s,s,s)','XML_GETDATA(f,n,names,names,text,done,s)'):
            p,_=compile_program(OPEN+ADD+'s=99 '+call,decl=DECL,context=context('<item/>'))
            with self.subTest(call=call),self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
            self.assertEqual(p.snapshot()['S'],99)

    def test_types_arities_and_user_routine_precedence(self):
        for call in ('XML_SCAN(f,tag,code,s)','XML_GETDATA(f,n,names,values,text,done)','XML_REMTAG(f,tag,n,s)','XML_ADDTAG(f,tag,n,1,n,s)'):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(call,decl=DECL)
        self.assertEqual(run('XML_SCAN(7)',routines='ROUTINE XML_SCAN(n: INTEGER) BEGIN s=n END XML_SCAN')['S'],7)


if __name__=='__main__':unittest.main()
