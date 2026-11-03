"""Typed service ARRAY rows/planes retain original cells and service contracts."""
import json
import struct
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.test_dictionaries import context as dictionary_context,LOAD
from tests.test_dynamic_display import context as display_context,SETUP as DISPLAY_SETUP,line
from tests.test_xml_input import context as xml_context,OPEN,ADD,SCAN
from tests.test_pc_exchange import context as pc_context
from tests.test_joint_interoperability import model_context,FRAME
from tests.test_table_controls import context as table_context,DECL as TABLE_DECL,SETUP as TABLE_SETUP,TABLE,INIT,CANCEL
from tests.legacy_numeric_support import translate as legacy_translate

U={'uninitialized':True};UNKNOWN={'unknown_byte':True}
QDECL='q:QUEUE_TYPE buffers:ARRAY[2,3]OF INTEGER out:ARRAY[2,2]OF INTEGER n,seq,count,s,visits:INTEGER'
SEED='INIT_QUEUE(q) APPEND_QUEUE(7,q,buffers[2],seq,s) APPEND_QUEUE(9,q,buffers[2],seq,s) '


def queue(body=SEED,**options):return compile_program(body,decl=QDECL,**options)
def listing(body="FILE_LIST('*',0,0,names[2],n,s)",*,decl='names:ARRAY[2,3]OF STRING[20] n,s,visits:INTEGER',routines='',files=None,**options):
    return compile_program(body,decl=decl,routines=routines,context=rt.ExecutionContext(files=rt.MemoryFiles({'a.kl':b'a','b.kl':b'bb'} if files is None else files)),**options)


class ServicePrefixQueueTests(unittest.TestCase):
    def test_append_binds_selected_original_row(self):
        p,_=queue();v=p.run();self.assertEqual(v['BUFFERS'],[[U,U,U],[7,9,0]]);self.assertEqual(p._state.values['Q'].entries,[(1,7),(2,9)])
    def test_repeat_row_capture_preserves_buffer_identity(self):
        p,_=queue(SEED+'APPEND_QUEUE(11,q,buffers[2],seq,s)');self.assertEqual(p.run()['BUFFERS'][1],[7,9,11])
    def test_get_updates_original_row(self):
        p,_=queue(SEED+'GET_QUEUE(q,buffers[2],n,seq,s)');v=p.run();self.assertEqual((v['N'],v['BUFFERS'][1]),(7,[9,0,0]))
    def test_insert_updates_original_row(self):
        p,_=queue(SEED+'INSERT_QUEUE(8,2,q,buffers[2],s)');self.assertEqual(p.run()['BUFFERS'][1],[7,8,9])
    def test_modify_updates_original_row(self):
        p,_=queue(SEED+'MODIFY_QUEUE(17,1,q,buffers[2],s)');self.assertEqual(p.run()['BUFFERS'][1],[17,9,0])
    def test_delete_updates_original_row(self):
        p,_=queue(SEED+'DELETE_QUEUE(1,q,buffers[2],s)');self.assertEqual(p.run()['BUFFERS'][1],[9,0,0])
    def test_copy_queue_uses_disjoint_destination_row(self):
        p,_=queue(SEED+'COPY_QUEUE(q,buffers[2],0,0,out[2],count,s)');v=p.run();self.assertEqual((v['OUT'],v['COUNT']),([[U,U],[7,9]],2))
    def test_copy_queue_leaves_unused_target_tail(self):
        p,_=queue('out[2,2]=99 INIT_QUEUE(q) APPEND_QUEUE(7,q,buffers[2],seq,s) COPY_QUEUE(q,buffers[2],0,0,out[2],count,s)');self.assertEqual(p.run()['OUT'][1],[7,99])
    def test_different_row_cannot_rebind_existing_queue(self):
        p,_=queue(SEED+'APPEND_QUEUE(11,q,buffers[1],seq,s)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'original backing'):p.run()
        self.assertEqual(p.snapshot()['BUFFERS'][1],[7,9,0])
    def test_row_output_and_status_overlap_is_rejected(self):
        p,_=queue('INIT_QUEUE(q) APPEND_QUEUE(7,q,buffers[2],seq,buffers[2,1])')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p._state.values['Q'].entries,[])
    def test_copy_source_and_output_overlap_is_rejected(self):
        p,_=queue(SEED+'COPY_QUEUE(q,buffers[2],0,0,buffers[2],count,s)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['BUFFERS'][1],[7,9,0])
    def test_reference_from_prior_byname_row_is_the_same_buffer(self):
        body="INIT_QUEUE(q) work(BYNAME('','BUFFERS[2]',n)) APPEND_QUEUE(9,q,buffers[2],seq,s)"
        p,_=queue(body,routines='ROUTINE work(row:ARRAY OF INTEGER) BEGIN APPEND_QUEUE(7,q,row,seq,s) END work');self.assertEqual(p.run()['BUFFERS'][1],[7,9,0])
    def test_row_selector_is_evaluated_once(self):
        p,_=queue('visits=0 INIT_QUEUE(q) APPEND_QUEUE(7,q,buffers[pick()],seq,s)',routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN(2) END pick');self.assertEqual(p.run()['VISITS'],1)
    def test_containing_data_is_validated_before_queue_mutation(self):
        p,_=queue('s=77 INIT_QUEUE(q) APPEND_QUEUE(7,q,buffers[2],seq,s)');p._state.values['BUFFERS'].values[0]='bad'
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],77);self.assertEqual(p._state.values['Q'].entries,[])


class ServicePrefixListingTests(unittest.TestCase):
    def test_file_list_updates_only_selected_row(self):
        p,_=listing();self.assertEqual(p.run()['NAMES'],[[U,U,U],['a.kl','b.kl',U]])
    def test_unused_selected_cells_are_preserved(self):
        p,_=listing("names[2,3]='keep' FILE_LIST('*',0,0,names[2],n,s)");self.assertEqual(p.run()['NAMES'][1],['a.kl','b.kl','keep'])
    def test_file_list_formats_remain_available(self):
        p,_=listing("FILE_LIST('*',0,1,names[2],n,s)");self.assertEqual(p.run()['NAMES'][1][:2],['a','b'])
    def test_three_dimensional_row_coordinates(self):
        p,_=listing("FILE_LIST('*',0,0,names[2][1],n,s)",decl='names:ARRAY[2,2,3]OF STRING[20] n,s:INTEGER');self.assertEqual(p.run()['NAMES'][1][0][:2],['a.kl','b.kl'])
    def test_named_inner_components_keep_their_schema(self):
        p,_=listing("FILE_LIST('*',0,0,names[2,1],n,s)",decl='names:ARRAY[2]OF bank_t n,s:INTEGER',prefix='TYPE bank_t=ARRAY[2,3]OF STRING[20]');self.assertEqual(p.run()['NAMES'][1][0][:2],['a.kl','b.kl'])
    def test_short_string_capacity_preserves_atomic_page(self):
        p,_=listing(decl='names:ARRAY[2,3]OF STRING[2] n,s:INTEGER');v=p.run();self.assertNotEqual(v['S'],0);self.assertEqual(v['NAMES'][1],[U,U,U])
    def test_later_status_selector_does_not_retarget_row(self):
        p,_=listing("visits=0 FILE_LIST('*',0,0,names[choose()],n,states[later()])",decl='names:ARRAY[2,3]OF STRING[20] states:ARRAY[2]OF INTEGER n,visits:INTEGER',routines='ROUTINE choose:INTEGER BEGIN visits=visits+1 RETURN(2) END choose ROUTINE later:INTEGER BEGIN visits=visits+1 RETURN(1) END later');v=p.run();self.assertEqual(v['VISITS'],2);self.assertEqual(v['NAMES'][1][:2],['a.kl','b.kl'])
    def test_malformed_unselected_data_prevents_status_selector(self):
        p,_=listing("visits=0 FILE_LIST('*',0,0,names[2],n,states[later()])",decl='names:ARRAY[2,3]OF STRING[20] states:ARRAY[2]OF INTEGER n,visits:INTEGER',routines='ROUTINE later:INTEGER BEGIN visits=visits+1 RETURN(1) END later');p._state.values['NAMES'].values[0]=17
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)
    def test_program_list_can_publish_into_string_row(self):
        p,_=compile_program("next=0 PROG_LIST('*',7,0,1,names[2],count,s,next)",decl='names:ARRAY[2,3]OF STRING[20] count,s,next:INTEGER');v=p.run();self.assertEqual(v['NAMES'][1][0],'T')
    def test_variable_list_can_publish_into_string_row(self):
        p,_=compile_program("VAR_LIST('','value*',0,0,3,names[2],count,s)",decl='value_a,value_b:INTEGER names:ARRAY[2,3]OF STRING[20] count,s:INTEGER');v=p.run();self.assertEqual(v['NAMES'][1][:2],['[T]VALUE_A','[T]VALUE_B'])
    def test_var_info_dimensions_use_original_int_row(self):
        p,_=compile_program("VAR_INFO('','value',missing,label,code,dims[2],length,s)",decl='value:ARRAY[2,3]OF INTEGER missing:BOOLEAN label:STRING[32] code,length,s:INTEGER dims:ARRAY[2,3]OF INTEGER');v=p.run();self.assertEqual(v['DIMS'],[[U,U,U],[2,3,0]])
    def test_var_info_row_and_status_overlap_is_rejected(self):
        p,_=compile_program("VAR_INFO('','value',missing,label,code,dims[2],length,dims[2,1])",decl='value:INTEGER missing:BOOLEAN label:STRING[32] code,length:INTEGER dims:ARRAY[2,3]OF INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()


class ServicePrefixDictionaryTests(unittest.TestCase):
    def task(self,body="READ_DICT('USER',1,lines[2],1,last,s)",text='$1 "one" &new_line "two"',**options):return compile_program(LOAD+body,decl='lines,paths:ARRAY[2,3]OF STRING[80] last,s,n:INTEGER label:STRING[10]',context=dictionary_context(text),**options)[0]
    def test_read_dict_writes_selected_string_row(self):
        p=self.task();self.assertEqual(p.run()['LINES'][1][:2],['one','two'])
    def test_read_dict_retains_unselected_row(self):
        p=self.task();self.assertEqual(p.run()['LINES'][0],[U,U,U])
    def test_read_dict_variable_input_row_and_output_row(self):
        p=self.task("n=7 label='ok' paths[2,1]='n' paths[2,2]='label' READ_DICT_V('USER',1,paths[2],lines[2],s)",text='$1 "%d/%s"');self.assertEqual(p.run()['LINES'][1][0],'7/ok')
    def test_dictionary_page_is_bounded_by_selected_row(self):
        p=self.task("READ_DICT('USER',1,lines[2],1,last,s)",text='$1 "a" &new_line "b" &new_line "c" &new_line "d"');v=p.run();self.assertNotEqual(v['S'],0);self.assertEqual(v['LINES'][1],['a','b','c'])
    def test_output_row_inside_formal_keeps_original_cells(self):
        p=self.task("work(lines)",routines="ROUTINE work(table:ARRAY[*,*]OF STRING) BEGIN READ_DICT('USER',1,table[2],1,last,s) END work");self.assertEqual(p.run()['LINES'][1][:2],['one','two'])


class ServicePrefixXmlTests(unittest.TestCase):
    def task(self,xml='<item a="7" b="9">hello</item>',statement='XML_GETDATA(f,n,names[2],values[2],text,done,s)'):
        return compile_program(OPEN+ADD+SCAN+statement+' CLOSE FILE f',decl='f:FILE tag,text:STRING[32] ident,code,n,s:INTEGER names,values:ARRAY[2,2]OF STRING[32] done:BOOLEAN',context=xml_context(xml))[0]
    def test_xml_outputs_publish_to_both_original_rows(self):
        p=self.task();v=p.run();self.assertEqual((v['NAMES'][1],v['VALUES'][1]),(['a','b'],['7','9']));self.assertEqual(v['TEXT'],'hello')
    def test_xml_unused_rows_stay_missing(self):
        p=self.task();v=p.run();self.assertEqual((v['NAMES'][0],v['VALUES'][0]),([U,U],[U,U]))
    def test_xml_overlapping_rows_reject_before_consuming_data(self):
        p=self.task(statement='XML_GETDATA(f,n,names[2],names[2],text,done,s)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
    def test_xml_no_attribute_output_does_not_clear_row(self):
        p=self.task(xml='<item>hello</item>');self.assertEqual(p.run()['NAMES'][1],[U,U])


class ServicePrefixPcTests(unittest.TestCase):
    def task(self,body='cursor=1 ADD_INTPC(buffers[2],cursor,17,s)',*,size=8,ctx=None,routines=''):
        return compile_program(body,decl=f'buffers:ARRAY[2,{size}]OF BYTE cursor,s,visits:INTEGER',context=ctx or pc_context(),routines=routines)[0]
    def test_integer_builder_updates_original_byte_row(self):
        p=self.task();v=p.run();self.assertEqual(v['BUFFERS'][1],list(b'\0\x10'+struct.pack('>i',17)+b'\0\0'));self.assertEqual(v['BUFFERS'][0],[UNKNOWN]*8)
    def test_real_builder_updates_original_byte_row(self):
        p=self.task('cursor=1 ADD_REALPC(buffers[2],cursor,1.5,s)');self.assertEqual(p.run()['BUFFERS'][1],list(b'\0\x11'+struct.pack('>f',1.5)+b'\0\0'))
    def test_string_builder_updates_original_byte_row(self):
        p=self.task("cursor=1 ADD_STRINGPC(buffers[2],cursor,'go',s)");self.assertEqual(p.run()['BUFFERS'][1],list(b'\0\xd1\x02go\0\0\0'))
    def test_byname_builder_can_write_a_row(self):
        p,_=compile_program("n=17 cursor=1 ADD_BYNAMEPC(buffers[2],cursor,'','N',s)",decl='buffers:ARRAY[2,8]OF BYTE n,cursor,s:INTEGER');self.assertEqual(p.run()['BUFFERS'][1],list(b'\0\x10'+struct.pack('>i',17)+b'\0\0'))
    def test_send_captures_selected_byte_row(self):
        ctx=pc_context();p=self.task('cursor=1 ADD_INTPC(buffers[2],cursor,17,s) SEND_DATAPC(12,buffers[2],s)',ctx=ctx);p.run();self.assertEqual(ctx.pc_exchange.snapshot(),[{'sequence':1,'event':12,'data':'0010000000110000'}])
    def test_typed_send_keeps_unknown_unused_tail_policy(self):
        ctx=pc_context();p=self.task('cursor=1 ADD_INTPC(buffers[2],cursor,17,s) SEND_DATAPC(12,buffers[2],s)',size=12,ctx=ctx);p.run();self.assertEqual(ctx.pc_exchange.snapshot()[0]['data'],'0010000000110000');self.assertEqual(p.snapshot()['BUFFERS'][1][-1],UNKNOWN)
    def test_builder_row_selector_runs_once(self):
        p=self.task('visits=0 cursor=1 ADD_INTPC(buffers[pick()],cursor,17,s)',routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN(2) END pick');self.assertEqual(p.run()['VISITS'],1)
    def test_cursor_failure_retains_byte_row(self):
        p=self.task('cursor=99 ADD_INTPC(buffers[2],cursor,17,s)');v=p.run();self.assertNotEqual(v['S'],0);self.assertEqual(v['BUFFERS'][1],[UNKNOWN]*8)


class ServicePrefixDisplayTests(unittest.TestCase):
    def task(self,body='',routines='',decl=''):
        ctx=display_context();source=DISPLAY_SETUP+"labels[2,1]='off' labels[2,2]='on' b=FALSE INI_DYN_DISB(b,'W1',6,0,0,1,1,1,labels[2],s) "+body
        p,_=compile_program(source,decl='b:BOOLEAN labels:ARRAY[2,2]OF STRING[12] s,visits:INTEGER '+decl,routines=routines,context=ctx);return p,ctx
    def test_static_label_row_is_retained_for_updates(self):
        p,ctx=self.task();p.run();self.assertEqual(line(ctx)[:6],'off   ');p._state.set('B',True);ctx.dynamic_display.advance(1);self.assertEqual(line(ctx)[:6],'on    ');ctx.dynamic_display.close_all()
    def test_edits_to_original_label_row_are_observed(self):
        p,ctx=self.task();p.run();p._state.values['LABELS'].set((2,1),'ready');ctx.dynamic_display.advance(1);self.assertEqual(line(ctx)[:6],'ready ');ctx.dynamic_display.close_all()
    def test_readonly_static_prefix_does_not_initialize_other_row(self):
        p,ctx=self.task();self.assertEqual(p.run()['LABELS'][0],[U,U]);ctx.dynamic_display.close_all()
    def test_static_local_prefix_remains_rejected(self):
        with self.assertRaises(TranslationError):compile_program("work",decl='b:BOOLEAN s:INTEGER',routines="ROUTINE work VAR labels:ARRAY[2,2]OF STRING[12] BEGIN INI_DYN_DISB(b,'W1',6,0,0,1,1,1,labels[2],s) END work")


class ServicePrefixGeometryTests(unittest.TestCase):
    def test_joint2pos_writes_selected_external_axes_row(self):
        p,_=compile_program(FRAME+'j=CURJPOS(0,0) JOINT2POS(j,f,f,0,p,c,axes[2],s)',decl='j:JOINTPOS f,p:POSITION c:CONFIG axes:ARRAY[2,3]OF REAL s:INTEGER',context=model_context());v=p.run();self.assertEqual(v['S'],0);self.assertEqual(v['AXES'],[[U,U,U],[0.,0.,0.]])
    def test_pos2joint_accepts_value_prefix_without_borrowing(self):
        p,_=compile_program(FRAME+'j=CURJPOS(0,0) JOINT2POS(j,f,f,0,p,c,axes[2],s) POS2JOINT(j,p,f,f,0,c,axes[2],out,s)',decl='j,out:JOINTPOS f,p:POSITION c:CONFIG axes:ARRAY[2,3]OF REAL s:INTEGER',context=model_context());v=p.run();self.assertEqual(v['S'],0);self.assertEqual(v['OUT']['axes'][:2],[30.,45.])


class ServicePrefixTableTests(unittest.TestCase):
    def task(self,statement=TABLE,keys=('SELECT',)):
        decl=TABLE_DECL.replace('cols:ARRAY[2]','cols:ARRAY[2,2]').replace('inactive:ARRAY[2]','inactive:ARRAY[2,2]').replace('changed:ARRAY[2,2]','changed:ARRAY[2,2,2]').replace('ptrs:ARRAY[2,2]','ptrs:ARRAY[2,2,2]')
        setup=TABLE_SETUP.replace('cols[','cols[2,')
        for name in ('cols','inactive','changed','ptrs'):statement=statement.replace(','+name+',',','+name+'[2],')
        ctx=table_context(keys);p,_=compile_program(setup+' '+statement,decl=decl,context=ctx,sleep=lambda _:None);return p,ctx
    def test_table_columns_flags_and_change_plane_use_original_cells(self):
        p,ctx=self.task(keys=('5','ENTER','SELECT'));v=p.run();self.assertEqual(v['S'],0);self.assertEqual(v['DATA'][0],5);self.assertTrue(v['CHANGED'][1][0][0]);self.assertEqual(v['CHANGED'][0],[[U,U],[U,U]]);self.assertEqual(ctx.table_controls.active_count,0)
    def test_init_table_pointer_plane_is_written_in_original_storage(self):
        p,_=self.task(INIT+' '+CANCEL);v=p.run();self.assertEqual(v['S'],0);self.assertEqual(v['PTRS'][0],[[U,U],[U,U]]);self.assertTrue(all(type(x) is int for row in v['PTRS'][1] for x in row))


class ServicePrefixGuardTests(unittest.TestCase):
    def test_numeric_reference_types_are_not_promoted(self):
        with self.assertRaises(TranslationError):listing(decl='names:ARRAY[2,3]OF INTEGER n,s:INTEGER')
    def test_wrong_result_rank_is_rejected(self):
        with self.assertRaises(TranslationError):listing("FILE_LIST('*',0,0,names[2],n,s)",decl='names:ARRAY[2,2,3]OF STRING[20] n,s:INTEGER')
    def test_resource_prefixes_are_not_data_service_outputs(self):
        with self.assertRaises(TranslationError):listing(decl='names:ARRAY[2,3]OF FILE n,s:INTEGER')
    def test_scalar_conversion_outputs_do_not_accept_array_prefixes(self):
        with self.assertRaises(TranslationError):compile_program("CNV_STR_INT('7',numbers[2])",decl='numbers:ARRAY[2,3]OF INTEGER')
    def test_grouped_mutable_prefix_is_not_a_writable_reference(self):
        with self.assertRaises(TranslationError):listing("FILE_LIST('*',0,0,(names[2]),n,s)")
    def test_out_of_range_selection_has_no_service_effect(self):
        p,_=listing("n=77 s=88 FILE_LIST('*',0,0,names[3],n,s)")
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(77,88))
    def test_active_counter_root_remains_protected(self):
        with self.assertRaises(TranslationError):compile_program("FOR dims[1,1]=1 TO 2 DO VAR_INFO('','value',missing,label,code,dims[2],length,s) ENDFOR",decl='dims:ARRAY[2,3]OF INTEGER value,code,length,s:INTEGER missing:BOOLEAN label:STRING[32]')
    def test_legacy_service_prefix_stays_rejected(self):
        with self.assertRaises(TranslationError):legacy_translate("PROGRAM T VAR names:ARRAY[2,2]OF STRING[20] n,s:INTEGER BEGIN FILE_LIST('*',0,0,names[2],n,s) END T")
    def test_plain_routine_prefix_argument_remains_private(self):
        p,_=compile_program('work(numbers[2])',decl='numbers:ARRAY[2,3]OF INTEGER',routines='ROUTINE work(row:ARRAY OF INTEGER) BEGIN row[1]=99 END work');self.assertEqual(p.run()['NUMBERS'][1],[U,U,U])
    def test_get_var_retains_its_existing_prefix_target_contract(self):
        p,_=compile_program("source[1]=7 GET_VAR(entry,'','SOURCE',numbers[2],s)",decl='source:ARRAY[3]OF INTEGER numbers:ARRAY[2,3]OF INTEGER entry,s:INTEGER');self.assertEqual(p.run()['NUMBERS'][1],[7,U,U])


class ServicePrefixFormTests(unittest.TestCase):
    def test_form_flags_publish_into_selected_boolean_rows(self):
        from tests.test_forms import context,LOAD as FLOAD,SETUP as FSETUP,CALL,DECL
        decl=DECL.replace('inactive,changed:ARRAY[10]','inactive,changed:ARRAY[2,10]');call=CALL.replace(',inactive,changed,',',inactive[2],changed[2],');ctx=context(keys=('5','ENTER','DOWN','ENTER'));p,_=compile_program(FLOAD+FSETUP+' '+call,decl=decl,context=ctx,sleep=lambda _:None);v=p.run();self.assertEqual((v['N'],v['STATUS']),(5,0));self.assertTrue(v['CHANGED'][1][0]);self.assertEqual(v['CHANGED'][0],[U]*10);self.assertEqual(ctx.forms.active_count,0)
    def test_form_values_can_be_supplied_as_private_string_row(self):
        from tests.test_forms import context,LOAD as FLOAD,SETUP as FSETUP,CALL,DECL
        decl=DECL.replace('values:ARRAY[10]','values:ARRAY[2,10]');setup=FSETUP.replace('values[','values[2,');ctx=context(keys=('5','ENTER','DOWN','ENTER'));p,_=compile_program(FLOAD+setup+' '+CALL.replace(',values,',',values[2],'),decl=decl,context=ctx,sleep=lambda _:None);v=p.run();self.assertEqual(v['N'],5);self.assertEqual(v['VALUES'][1][:3],['N','TEXT','FLAG'])


class ServicePrefixVisionTests(unittest.TestCase):
    def task(self,tracking=False):
        from tests.test_vision_results import context,found,batch
        name='VT_GET_FOUND' if tracking else 'V_GET_FOUND';args="'scan',model_no,encoder,p,points[2],measures[2],s" if tracking else "'scan',frame_no,model_no,encoder,p,points[2],measures[2],s"
        ctx=context(batch(found()));p,_=compile_program("V_RUN_FIND('scan',-1,s) "+name+'('+args+')',decl='s,frame_no,model_no,encoder:INTEGER p:XYZWPR points:ARRAY[2,4]OF XYZWPR measures:ARRAY[2,10]OF REAL',context=ctx);return p,ctx
    def test_vision_positions_and_measurements_write_original_rows(self):
        p,_=self.task();v=p.run();self.assertEqual(v['S'],0);self.assertEqual(v['POINTS'][1][0]['X'],3.);self.assertEqual(v['MEASURES'][1][:2],[1.25,2.5]);self.assertEqual(v['MEASURES'][0],[U]*10)
    def test_tracking_fixed_size_prefixes_keep_existing_domains(self):
        p,_=self.task(True);v=p.run();self.assertEqual(v['S'],0);self.assertEqual(v['POINTS'][1][0]['X'],3.);self.assertEqual(v['MEASURES'][1][:2],[1.25,2.5])
    def test_wrong_tracking_suffix_size_is_rejected(self):
        with self.assertRaises(TranslationError):compile_program("VT_GET_FOUND('scan',model_no,encoder,p,points[2],measures[2],s)",decl='s,model_no,encoder:INTEGER p:XYZWPR points:ARRAY[2,3]OF XYZWPR measures:ARRAY[2,10]OF REAL')


class ServicePrefixLifetimeTests(unittest.TestCase):
    def test_row_selected_in_formal_uses_actual_concrete_schema(self):
        p,_=queue('INIT_QUEUE(q) fill(buffers) APPEND_QUEUE(9,q,buffers[2],seq,s)',routines='ROUTINE fill(matrix:ARRAY[*,*]OF INTEGER) BEGIN APPEND_QUEUE(7,q,matrix[2],seq,s) END fill');self.assertEqual(p.run()['BUFFERS'][1],[7,9,0])
    def test_local_queue_buffer_retains_its_captured_row_after_return(self):
        p,_=compile_program('fill',decl='q:QUEUE_TYPE seq,s:INTEGER',routines='ROUTINE fill VAR matrix:ARRAY[2,3]OF INTEGER BEGIN INIT_QUEUE(q) APPEND_QUEUE(7,q,matrix[2],seq,s) END fill');p.run();buffer=p._state.values['Q'].buffer
        with rt._numeric_scope('pythonic'):self.assertEqual(list(buffer.values),[7,0,0])
        self.assertIs(type(buffer.values),rt._ArrayWindow)
    def test_global_queue_buffer_survives_pause_resume(self):
        p,_=queue(SEED+'PAUSE GET_QUEUE(q,buffers[2],n,seq,s)',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['BUFFERS'][1],[7,9,0]);self.assertEqual(p.resume()['N'],7)
    def test_static_readonly_label_capture_ignores_root_list_replacement(self):
        p,ctx=ServicePrefixDisplayTests().task();p.run();original=p._state.values['LABELS'].values;p._state.values['LABELS'].values=['new']*4;original[2]='old';ctx.dynamic_display.advance(1);self.assertEqual(line(ctx)[:6],'old   ');ctx.dynamic_display.close_all()
    def test_mutable_service_row_capture_ignores_later_root_replacement(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'a.kl':b'a'}));p,_=compile_program("FILE_LIST('*',0,0,names[2],counts[later()],s)",decl='names:ARRAY[2,2]OF STRING[20] counts:ARRAY[1]OF INTEGER s:INTEGER',routines='ROUTINE later:INTEGER FROM HOST',context=ctx);old=p._state.values['NAMES'].values;ctx.externals[('HOST','LATER')]=lambda:(setattr(p._state.values['NAMES'],'values',[rt.UNINITIALIZED]*4) or 1);p.run();self.assertEqual(old[2],'a.kl');self.assertEqual(p.snapshot()['NAMES'][1],[U,U])
    def test_later_storage_resize_fails_without_list_publication(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'a.kl':b'a'}));p,_=compile_program("n=77 s=88 FILE_LIST('*',0,0,names[2],counts[later()],s)",decl='names:ARRAY[2,2]OF STRING[20] counts:ARRAY[1]OF INTEGER n,s:INTEGER',routines='ROUTINE later:INTEGER FROM HOST',context=ctx);ctx.externals[('HOST','LATER')]=lambda:(p._state.values['NAMES'].values.pop() and 1)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['S'],88)
    def test_static_global_prefix_index_is_captured_once(self):
        ctx=display_context();p,_=compile_program(DISPLAY_SETUP+"visits=0 labels[2,1]='off' labels[2,2]='on' b=FALSE INI_DYN_DISB(b,'W1',6,0,0,1,1,1,labels[pick()],s)",decl='labels:ARRAY[2,2]OF STRING[12] b:BOOLEAN visits,s:INTEGER',routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN(2) END pick',context=ctx);self.assertEqual(p.run()['VISITS'],1);ctx.dynamic_display.close_all()
    def test_static_formal_label_row_remains_rejected(self):
        with self.assertRaises(TranslationError):compile_program('',decl='b:BOOLEAN s:INTEGER',routines="ROUTINE fill(labels:ARRAY[*,*]OF STRING) BEGIN INI_DYN_DISB(b,'W1',6,0,0,1,1,1,labels[2],s) END fill")


class ServicePrefixLinkageTests(unittest.TestCase):
    def test_linked_service_writes_calling_roots_row(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'a.kl':b'a'}));project=translate_project({'main':'PROGRAM MAIN VAR names:ARRAY[2,2]OF STRING[20] ROUTINE fill FROM LIB BEGIN fill END MAIN','lib':"PROGRAM LIB VAR names FROM MAIN:ARRAY[2,2]OF STRING[20] n,s:INTEGER ROUTINE fill BEGIN FILE_LIST('*',0,0,names[2],n,s) END fill BEGIN END LIB"}).instantiate(context=ctx);project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['NAMES'][1][0],'a.kl')
    def test_linked_generic_matrix_formal_preserves_original_cells(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'a.kl':b'a'}));project=translate_project({'main':'PROGRAM MAIN VAR names:ARRAY[2,2]OF STRING[20] ROUTINE fill(matrix:ARRAY[*,*]OF STRING) FROM LIB BEGIN fill(names) END MAIN','lib':"PROGRAM LIB VAR n,s:INTEGER ROUTINE fill(matrix:ARRAY[*,*]OF STRING) BEGIN FILE_LIST('*',0,0,matrix[2],n,s) END fill BEGIN END LIB"}).instantiate(context=ctx);project.run('MAIN');self.assertEqual(project.programs['MAIN'].snapshot()['NAMES'][1][0],'a.kl')
    def test_saved_rows_remain_ordinary_independent_values(self):
        p,_=listing();p.run();data=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(data).to_config(),data)
    def test_service_row_window_is_not_a_new_variable_binding(self):
        p,_=listing();before=dict(p._state.execution.variables.bindings);p.run();self.assertEqual(p._state.execution.variables.bindings,before);self.assertEqual(set(p.snapshot()),{'NAMES','N','S','VISITS'})


class ServicePrefixPolicyTests(unittest.TestCase):
    def test_report_lists_exact_typed_reference_kinds_and_modes(self):
        from karel2py.extended import ARRAY_REFERENCE_KINDS
        _,result=listing();policy=result.report['typed_service_array_prefix_policy'];self.assertEqual(policy['kinds'],sorted(ARRAY_REFERENCE_KINDS));self.assertEqual(len(policy['kinds']),13);self.assertEqual(policy['modes'],['o','r','m','s'])
    def test_report_links_guide_and_preserves_offline_scope(self):
        _,result=queue();policy=result.report['typed_service_array_prefix_policy'];self.assertEqual(policy['guide'],'docs/service-array-prefixes.md');self.assertFalse(policy['controller_validated']);self.assertIn('BYNAME only',policy['protection']);self.assertIn('private values',policy['snapshots'])
    def test_report_keeps_service_specific_publication_rules(self):
        _,result=listing();policy=result.report['typed_service_array_prefix_policy'];self.assertIn('pagination',policy['publication']);self.assertIn('no blanket all-or-nothing',policy['publication']);self.assertIn('32767',policy['limits']);self.assertIn('without live windows',policy['persistence'])
    def test_readonly_pc_prefix_snapshot_precedes_later_status_effects(self):
        ctx=pc_context();p,_=compile_program('cursor=1 ADD_INTPC(buffers[2],cursor,17,s) SEND_DATAPC(12,buffers[2],statuses[later()])',decl='buffers:ARRAY[2,8]OF BYTE cursor,s:INTEGER statuses:ARRAY[1]OF INTEGER',routines='ROUTINE later:INTEGER FROM HOST',context=ctx)
        def later():p._state.values['BUFFERS'].values[13]=99;return 1
        ctx.externals[('HOST','LATER')]=later;p.run();self.assertEqual(ctx.pc_exchange.to_config()['messages'][0]['data'],'0010000000110000');self.assertEqual(p.snapshot()['BUFFERS'][1][5],99)


if __name__=='__main__':unittest.main()
