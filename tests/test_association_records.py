"""Authored association data, value-only scalar fields and portable ownership."""
import json
import struct
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from karel2py.storage import typed_value,decode_typed
from karel2py.dynamic import creation_cost
from tests.test_extended_services import compile_program
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_variable_archives import context as archive_context

U={'uninitialized':True}
COMMON=dict(SEGTERMTYPE=1,SEGDECELTOL=25,SEGRELACCEL=7,SEGTIMESHFT=9)
GROUP=dict(SEGRELSPEED=50,SEGMOTYPE=7,SEGORIENTYPE=1,SEGBREAK=False)
CMISSING={name:U for name in COMMON}
GMISSING={name:U for name in GROUP}
DECL='c,other:COMMON_ASSOC g,copy:GROUP_ASSOC n,e,s,total,visits:INTEGER flag:BOOLEAN'
TYPES='TYPE node_t=STRUCTURE common:COMMON_ASSOC axes:GROUP_ASSOC ENDSTRUCTURE header_t=STRUCTURE common:COMMON_ASSOC ENDSTRUCTURE'


def seed(name,fields):return ' '.join(name+'.'+key.lower()+'='+('TRUE' if value is True else 'FALSE' if value is False else str(value)) for key,value in fields.items())+' '
SEED=seed('c',COMMON)+seed('g',GROUP)
def build(body='',*,decl=DECL,**options):return compile_program(body,decl=decl,**options)
def execute(body='',**options):return build(body,**options)[0].run()


class AssociationDeclarationTests(unittest.TestCase):
    def test_common_field_order_and_types(self):self.assertEqual(rt.record_fields(('COMMON_ASSOC',)),tuple((name,('INTEGER',)) for name in COMMON))
    def test_group_field_order_and_types(self):self.assertEqual(rt.record_fields(('GROUP_ASSOC',)),tuple((name,('BOOLEAN',) if name=='SEGBREAK' else ('INTEGER',)) for name in GROUP))
    def test_fresh_records_have_missing_fields(self):
        v=execute();self.assertEqual((v['C'],v['G']),(CMISSING,GMISSING))
    def test_common_fields_initialize(self):self.assertEqual(execute(SEED)['C'],COMMON)
    def test_group_fields_initialize(self):self.assertEqual(execute(SEED)['G'],GROUP)
    def test_whole_uninit_true_for_partial(self):self.assertTrue(execute('g.segmotype=7 flag=UNINIT(g)')['FLAG'])
    def test_whole_uninit_false_for_complete(self):self.assertFalse(execute(SEED+'flag=UNINIT(g)')['FLAG'])
    def test_common_uninit_false_for_complete(self):self.assertFalse(execute(SEED+'flag=UNINIT(c)')['FLAG'])
    def test_checked_partial_copy(self):self.assertEqual(execute('c.segtermtype=7 other=c')['OTHER'],dict(CMISSING,SEGTERMTYPE=7))
    def test_group_copy_is_independent(self):
        v=execute(SEED+'copy=g g.segmotype=9');self.assertEqual(v['COPY'],GROUP)
    def test_common_copy_is_independent(self):self.assertEqual(execute(SEED+'other=c c.segtermtype=7')['OTHER'],COMMON)
    def test_aliases_keep_builtin_identity(self):
        p,_=build('a.segtermtype=7',prefix='TYPE common_t=COMMON_ASSOC',decl='a:common_t');self.assertEqual(p.run()['A']['SEGTERMTYPE'],7);self.assertEqual(p._state.types['A'],('COMMON_ASSOC',))
    def test_group_qualifier_metadata(self):
        p,r=build('g.segmotype=7',decl='g:GROUP_ASSOC IN GROUP[2]');self.assertEqual(p.run()['G']['SEGMOTYPE'],7);self.assertEqual([(row['group'],row['type']) for row in r.report['group_declarations']],[(2,'GROUP_ASSOC')])
    def test_default_group_needs_no_robot(self):
        v=execute('g.segmotype=7');self.assertEqual(v['G']['SEGMOTYPE'],7)
    def test_nested_record_fields(self):
        v=execute('item.axes.segmotype=7 item.common.segtermtype=1',prefix=TYPES,decl='item:node_t');self.assertEqual((v['ITEM']['AXES']['SEGMOTYPE'],v['ITEM']['COMMON']['SEGTERMTYPE']),(7,1))
    def test_array_cells_are_independent(self):
        v=execute('items[1].segmotype=7',decl='items:ARRAY[2]OF GROUP_ASSOC');self.assertEqual(v['ITEMS'],[dict(GMISSING,SEGMOTYPE=7),GMISSING])
    def test_named_array_type(self):
        v=execute('items[2].segtermtype=7',prefix='TYPE batch_t=ARRAY[2]OF COMMON_ASSOC',decl='items:batch_t');self.assertEqual(v['ITEMS'][1]['SEGTERMTYPE'],7)
    def test_array_copy_retains_missing_fields(self):
        v=execute('a[1].segmotype=7 b=a a[1].segmotype=9',decl='a,b:ARRAY[2]OF GROUP_ASSOC');self.assertEqual(v['B'][0]['SEGMOTYPE'],7)
    def test_group_alias_qualifier(self):
        p,r=build('',prefix='TYPE axes_t=GROUP_ASSOC IN GROUP[3]',decl='g:axes_t');self.assertEqual(p._state.types['G'],('GROUP_ASSOC',));self.assertEqual(r.report['group_declarations'][0]['group'],3)
    def test_using_fields(self):self.assertEqual(execute('USING g DO segmotype=7 segbreak=TRUE ENDUSING')['G'],dict(GMISSING,SEGMOTYPE=7,SEGBREAK=True))


class AssociationRoutineTests(unittest.TestCase):
    def test_whole_common_argument_is_reference(self):self.assertEqual(execute('work(c)',routines='ROUTINE work(x:COMMON_ASSOC) BEGIN x.segtermtype=7 END work')['C']['SEGTERMTYPE'],7)
    def test_whole_group_argument_is_reference(self):self.assertEqual(execute('work(g)',routines='ROUTINE work(x:GROUP_ASSOC) BEGIN x.segmotype=7 END work')['G']['SEGMOTYPE'],7)
    def test_grouped_whole_argument_is_private(self):self.assertEqual(execute('work((g))',routines='ROUTINE work(x:GROUP_ASSOC) BEGIN x.segmotype=7 END work')['G'],GMISSING)
    def test_common_scalar_argument_is_value(self):self.assertEqual(execute('c.segtermtype=7 work(c.segtermtype)',routines='ROUTINE work(x:INTEGER) BEGIN x=9 END work')['C']['SEGTERMTYPE'],7)
    def test_group_scalar_argument_is_value(self):self.assertEqual(execute('g.segmotype=7 work(g.segmotype)',routines='ROUTINE work(x:INTEGER) BEGIN x=9 END work')['G']['SEGMOTYPE'],7)
    def test_boolean_scalar_argument_is_value(self):self.assertFalse(execute('g.segbreak=FALSE work(g.segbreak)',routines='ROUTINE work(x:BOOLEAN) BEGIN x=TRUE END work')['G']['SEGBREAK'])
    def test_using_scalar_argument_is_value(self):self.assertEqual(execute('g.segmotype=7 USING g DO work(segmotype) ENDUSING',routines='ROUTINE work(x:INTEGER) BEGIN x=9 END work')['G']['SEGMOTYPE'],7)
    def test_forwarded_scalar_remains_private(self):self.assertEqual(execute('g.segmotype=7 work(g.segmotype)',routines='ROUTINE inner(x:INTEGER) BEGIN x=9 END inner ROUTINE work(x:INTEGER) BEGIN inner(x) END work')['G']['SEGMOTYPE'],7)
    def test_whole_record_alias_survives_replacement(self):
        v=execute('g.segmotype=7 work(g)',routines='ROUTINE work(x:GROUP_ASSOC) BEGIN copy.segmotype=9 g=copy n=x.segmotype END work');self.assertEqual(v['N'],9)
    def test_common_result_partial(self):self.assertEqual(execute('c=make()',routines='ROUTINE make:COMMON_ASSOC VAR value:COMMON_ASSOC BEGIN value.segtermtype=7 RETURN value END make')['C'],dict(CMISSING,SEGTERMTYPE=7))
    def test_group_result_is_private(self):
        v=execute('g.segmotype=7 copy=make() copy.segmotype=9',routines='ROUTINE make:GROUP_ASSOC BEGIN RETURN g END make');self.assertEqual(v['G']['SEGMOTYPE'],7)
    def test_array_parameter_borrows_cells(self):self.assertEqual(execute('work(items)',decl='items:ARRAY[2]OF GROUP_ASSOC',routines='ROUTINE work(x:ARRAY OF GROUP_ASSOC) BEGIN x[2].segmotype=7 END work')['ITEMS'][1]['SEGMOTYPE'],7)
    def test_array_result(self):
        v=execute('items=make()',decl='items:ARRAY[2]OF GROUP_ASSOC',routines='ROUTINE make:ARRAY[2]OF GROUP_ASSOC VAR x:ARRAY[2]OF GROUP_ASSOC BEGIN x[2].segmotype=7 RETURN x END make');self.assertEqual(v['ITEMS'][1]['SEGMOTYPE'],7)
    def test_private_prefix_argument(self):self.assertEqual(execute('work(items[1])',decl='items:ARRAY[2,2]OF GROUP_ASSOC',routines='ROUTINE work(x:ARRAY OF GROUP_ASSOC) BEGIN x[1].segmotype=7 END work')['ITEMS'][0][0],GMISSING)
    def test_live_byname_prefix(self):
        v=execute("work(BYNAME('','ITEMS[1]',e))",decl='items:ARRAY[2,2]OF GROUP_ASSOC e:INTEGER',routines='ROUTINE work(x:ARRAY OF GROUP_ASSOC) BEGIN x[1].segmotype=7 END work');self.assertEqual(v['ITEMS'][0][0]['SEGMOTYPE'],7)
    def test_pause_retains_borrowed_record(self):
        p,_=build('work(g)',cooperative=True,routines='ROUTINE work(x:GROUP_ASSOC) BEGIN x.segmotype=7 PAUSE x.segrelspeed=50 END work')
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['G']['SEGMOTYPE'],7);self.assertEqual(p.resume()['G']['SEGRELSPEED'],50)
    def test_computed_using_value_is_private(self):
        v=execute('g.segmotype=7 USING make() DO segmotype=9 n=segmotype ENDUSING',routines='ROUTINE make:GROUP_ASSOC BEGIN RETURN g END make');self.assertEqual((v['N'],v['G']['SEGMOTYPE']),(9,7))
    def test_argument_capture_before_later_effect(self):
        v=execute('g.segmotype=7 work((g),later())',routines='ROUTINE later:INTEGER BEGIN g.segmotype=9 RETURN 0 END later ROUTINE work(x:GROUP_ASSOC;y:INTEGER) BEGIN n=x.segmotype END work');self.assertEqual(v['N'],7)
    def test_field_selector_evaluated_once(self):
        v=execute('visits=0 items[1].segmotype=7 work(items[pick()].segmotype)',decl=DECL+' items:ARRAY[1]OF GROUP_ASSOC',routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN 1 END pick ROUTINE work(x:INTEGER) BEGIN x=9 END work');self.assertEqual((v['VISITS'],v['ITEMS'][0]['SEGMOTYPE']),(1,7))
    def test_report_distinguishes_association_field_values(self):
        _,r=build('g.segmotype=7 work(g.segmotype)',routines='ROUTINE work(x:INTEGER) BEGIN END work');self.assertEqual(r.report['config_subfield_arguments'],[]);self.assertEqual(r.report['association_value_arguments'][0]['record_type'],'GROUP_ASSOC')


class AssociationInputTests(unittest.TestCase):
    def test_direct_integer_field_read(self):self.assertEqual(execute('READ(g.segmotype)',read=lambda _: [7])['G']['SEGMOTYPE'],7)
    def test_direct_boolean_field_read(self):self.assertTrue(execute('READ(g.segbreak)',read=lambda _: [True])['G']['SEGBREAK'])
    def test_whole_common_read(self):self.assertEqual(execute('READ(c)',read=lambda _:list(COMMON.values()))['C'],COMMON)
    def test_whole_group_read(self):self.assertEqual(execute('READ(g)',read=lambda _:list(GROUP.values()))['G'],GROUP)
    def test_bad_group_batch_is_atomic(self):
        p,_=build('g.segmotype=9 READ(g)',read=lambda _: [50,7,1,0])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['G'],dict(GMISSING,SEGMOTYPE=9))
    def test_nested_record_read(self):
        v=execute('READ(item)',prefix=TYPES,decl='item:node_t',read=lambda _:list(COMMON.values())+list(GROUP.values()));self.assertEqual(v['ITEM'],dict(COMMON=COMMON,AXES=GROUP))
    def test_array_read(self):
        v=execute('READ(items)',decl='items:ARRAY[2]OF GROUP_ASSOC',read=lambda _:list(GROUP.values())*2);self.assertEqual(v['ITEMS'],[GROUP,GROUP])
    def test_prefix_read(self):
        v=execute('READ(items[2])',decl='items:ARRAY[2,1]OF GROUP_ASSOC',read=lambda _:list(GROUP.values()));self.assertEqual(v['ITEMS'],[[GMISSING],[GROUP]])
    def test_text_file_read(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'input':b'50 7 1 FALSE'}));v=execute("OPEN FILE f('RO','input') READ f(g) CLOSE FILE f",decl=DECL+' f:FILE',context=ctx);self.assertEqual(v['G'],GROUP)
    def test_binary_file_read(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles({'input':struct.pack('<iiiB',50,7,1,0)}));v=execute("OPEN FILE f('RB','input') READ f(g) CLOSE FILE f",decl=DECL+' f:FILE',context=ctx);self.assertEqual(v['G'],GROUP)
    def test_binary_file_write(self):
        ctx=rt.ExecutionContext(files=rt.MemoryFiles());execute(SEED+"OPEN FILE f('WB','output') WRITE f(g) CLOSE FILE f",decl=DECL+' f:FILE',context=ctx);self.assertEqual(ctx.files.snapshot()['output'],struct.pack('<iiiB',50,7,1,0))
    def test_whole_text_output(self):
        p,_=build(SEED+'WRITE(g)');p.run();self.assertEqual(p._state.write_requests[0]['text'],' 50 7 1 FALSE')
    def test_missing_output_fails_before_callback(self):
        calls=[];p,_=build('WRITE(g)',write=calls.append)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])
    def test_malformed_capture_rejected(self):
        p,_=build('READ(g.segmotype)',read=lambda _: [7]);p._state.raw('G').values.pop('SEGBREAK')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_read_after_callback_schema_change_fails(self):
        def callback(_):p._state.raw('G').values.pop('SEGBREAK');return [7]
        p,_=build('READ(g.segmotype)',read=callback)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['G']['SEGMOTYPE'],U)


class AssociationVariableTests(unittest.TestCase):
    def test_get_whole_record(self):self.assertEqual(execute(SEED+"GET_VAR(e,'','G',copy,s)")['COPY'],GROUP)
    def test_set_whole_record(self):self.assertEqual(execute(SEED+"SET_VAR(e,'','OTHER',c,s)")['OTHER'],COMMON)
    def test_partial_get_status(self):
        v=execute("g.segmotype=7 GET_VAR(e,'','G',copy,s)");self.assertEqual((v['COPY'],v['S']),(dict(GMISSING,SEGMOTYPE=7),12311))
    def test_get_scalar_field_into_ordinary_storage(self):self.assertEqual(execute("g.segmotype=7 GET_VAR(e,'','G.SEGMOTYPE',n,s)")['N'],7)
    def test_set_scalar_named_path(self):self.assertEqual(execute("SET_VAR(e,'','G.SEGMOTYPE',7,s)")['G']['SEGMOTYPE'],7)
    def test_byname_whole_record(self):self.assertEqual(execute("work(BYNAME('','G',e))",routines='ROUTINE work(x:GROUP_ASSOC) BEGIN x.segmotype=7 END work')['G']['SEGMOTYPE'],7)
    def test_byname_scalar_field_rejected(self):
        p,_=build("e=77 work(BYNAME('','G.SEGMOTYPE',e))",routines='ROUTINE work(x:INTEGER) BEGIN x=9 END work')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['E'],p._state.execution.entries),(77,{}))
    def test_create_group_record(self):
        p,_=build("CREATE_VAR('CACHE','ITEM','','GROUP_ASSOC',2,0,0,0,s) GET_VAR(e,'CACHE','ITEM',g,s)");v=p.run();self.assertEqual((v['G'],v['S']),(GMISSING,12311));self.assertEqual(p._state.execution.variables.metadata['CACHE','ITEM']['group'],2)
    def test_create_common_record(self):
        v=execute("CREATE_VAR('CACHE','ITEM','','COMMON_ASSOC',0,0,0,0,s) SET_VAR(e,'CACHE','ITEM.SEGTERMTYPE',7,s) GET_VAR(e,'CACHE','ITEM',c,s)");self.assertEqual(v['C']['SEGTERMTYPE'],7)
    def test_create_array(self):
        p,_=build("CREATE_VAR('CACHE','ITEM','','ARRAY OF GROUP_ASSOC',0,2,0,0,s) SET_VAR(e,'CACHE','ITEM[2].SEGMOTYPE',7,s)");p.run();self.assertEqual(p._state.execution.variables.bindings['CACHE','ITEM'].raw().snapshot()[1]['SEGMOTYPE'],7)
    def test_rename_retains_borrowed_record(self):
        v=execute("CREATE_VAR('CACHE','ITEM','','GROUP_ASSOC',0,0,0,0,s) work(BYNAME('CACHE','ITEM',e)) GET_VAR(e,'CACHE','NEXT',g,s)",routines="ROUTINE work(x:GROUP_ASSOC) BEGIN RENAME_VAR('CACHE','ITEM','NEXT',s) x.segmotype=7 END work");self.assertEqual(v['G']['SEGMOTYPE'],7)
    def test_variable_info_common_type(self):
        v=execute("VAR_INFO('','C',flag,label,code,dims,length,s)",decl=DECL+' label:STRING[40] code,length:INTEGER dims:ARRAY[3]OF INTEGER');self.assertEqual((v['LABEL'],v['CODE'],v['DIMS']),('COMMON_ASSOC',20,[0,0,0]))
    def test_variable_info_group_array(self):
        v=execute("VAR_INFO('','ITEMS',flag,label,code,dims,length,s)",decl=DECL+' items:ARRAY[2]OF GROUP_ASSOC label:STRING[40] code,length:INTEGER dims:ARRAY[3]OF INTEGER');self.assertEqual((v['LABEL'],v['CODE'],v['DIMS']),('GROUP_ASSOC',30,[2,0,0]))
    def test_creation_cost_counts_four_leaves(self):self.assertEqual((creation_cost(('GROUP_ASSOC',)),creation_cost(('ARRAY',2,('COMMON_ASSOC',)))),(4,8))
    def test_json_values_round_trip(self):
        p,_=build(SEED);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_dynamic_json_metadata_round_trip(self):
        p,_=build("CREATE_VAR('CACHE','ITEM','','GROUP_ASSOC',2,0,0,0,s) SET_VAR(e,'CACHE','ITEM.SEGMOTYPE',7,s)");p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_typed_partial_record_round_trip(self):
        with rt._numeric_scope('pythonic'):
            g=rt.Structure(('GROUP_ASSOC',));g.values['SEGMOTYPE']=7;spec,value=decode_typed(json.loads(json.dumps(typed_value(g))));self.assertEqual((spec,rt.snapshot_value(value)),(('GROUP_ASSOC',),dict(GMISSING,SEGMOTYPE=7)))
    def test_vr_save_clear_load(self):
        ctx=archive_context();v=execute("CREATE_VAR('CACHE','ITEM','','GROUP_ASSOC',0,0,0,0,s) SET_VAR(e,'CACHE','ITEM.SEGMOTYPE',7,s) SAVE('CACHE','FR:CACHE.VR',s) CLEAR('CACHE.VR',s) LOAD('FR:CACHE.VR',0,s) GET_VAR(e,'CACHE','ITEM',g,s)",context=ctx);self.assertEqual((v['G']['SEGMOTYPE'],v['S']),(7,12311))


class AssociationPathTests(unittest.TestCase):
    DECL=DECL+' track,other_path:PATH NODEDATA=node_t PATHHEADER=header_t'
    def test_custom_node_and_header_fields(self):
        v=execute('APPEND_NODE(track,s) track[1].axes.segmotype=7 track.common.segtermtype=1',prefix=TYPES,decl=self.DECL);self.assertEqual((v['TRACK']['nodes'][0]['AXES']['SEGMOTYPE'],v['TRACK']['data']['COMMON']['SEGTERMTYPE']),(7,1))
    def test_path_copy_detaches_association_records(self):
        v=execute('APPEND_NODE(track,s) track[1].axes.segmotype=7 other_path=track track[1].axes.segmotype=9',prefix=TYPES,decl=self.DECL);self.assertEqual(v['OTHER_PATH']['nodes'][0]['AXES']['SEGMOTYPE'],7)
    def test_whole_path_variable_transfer(self):
        v=execute("APPEND_NODE(track,s) track[1].axes.segmotype=7 GET_VAR(e,'','TRACK',other_path,s)",prefix=TYPES,decl=self.DECL);self.assertEqual(v['OTHER_PATH']['nodes'][0]['AXES']['SEGMOTYPE'],7)
    def test_path_input_expands_header_and_node_records(self):
        v=execute('APPEND_NODE(track,s) READ(track)',prefix=TYPES,decl=self.DECL,read=lambda _:list(COMMON.values())*2+list(GROUP.values()));self.assertEqual(v['TRACK']['nodes'][0],dict(COMMON=COMMON,AXES=GROUP))
    def test_path_node_size_is_portable_fields(self):
        v=execute('n=NODE_SIZE(track)',prefix=TYPES,decl=self.DECL);self.assertEqual(v['N'],29)
    def test_path_json_round_trip(self):
        p,_=build('APPEND_NODE(track,s) track[1].axes.segmotype=7',prefix=TYPES,decl=self.DECL);p.run();saved=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(saved).to_config(),saved)
    def test_default_path_schema_is_unchanged(self):
        p,_=build('APPEND_NODE(track,s)',decl=DECL+' track:PATH');self.assertEqual(set(p.run()['TRACK']['nodes'][0]),{'NODE_POS'})
    def test_explicit_standard_node_stays_compatible(self):
        p,_=build('APPEND_NODE(track,s)',decl=DECL+' track:PATH NODEDATA=STD_PTH_NODE');self.assertEqual(set(p.run()['TRACK']['nodes'][0]),{'NODE_POS'})


class AssociationBoundaryTests(unittest.TestCase):
    def reject(self,body='',**options):
        with self.assertRaises(TranslationError):build(body,**options)
    def test_boolean_field_rejects_integer(self):self.reject('g.segbreak=1')
    def test_cross_record_assignment_rejected(self):self.reject('c=g')
    def test_integer_record_cast_rejected(self):self.reject('g=0')
    def test_record_integer_cast_rejected(self):self.reject('n=g')
    def test_config_word_codec_does_not_accept_association(self):self.reject('cfg=g',decl=DECL+' cfg:CONFIG')
    def test_common_group_qualifier_rejected(self):self.reject(decl='c:COMMON_ASSOC IN GROUP[2]')
    def test_common_alias_group_qualifier_rejected(self):self.reject(prefix='TYPE common_t=COMMON_ASSOC',decl='c:common_t IN GROUP[2]')
    def test_group_zero_rejected(self):self.reject(decl='g:GROUP_ASSOC IN GROUP[0]')
    def test_group_33_rejected(self):self.reject(decl='g:GROUP_ASSOC IN GROUP[33]')
    def test_group_boolean_rejected(self):self.reject(decl='g:GROUP_ASSOC IN GROUP[TRUE]')
    def test_reserved_type_cannot_be_redeclared(self):self.reject(prefix='TYPE GROUP_ASSOC=STRUCTURE n:INTEGER ENDSTRUCTURE')
    def test_generic_conversion_output_field_rejected(self):self.reject("CNV_STR_INT('7',g.segmotype)")
    def test_register_output_field_rejected(self):self.reject('GET_INT_REG(1,g.segmotype,s)')
    def test_variable_output_field_rejected(self):self.reject("GET_VAR(e,'','N',g.segmotype,s)")
    def test_byname_entry_field_rejected(self):self.reject("work(BYNAME('','N',g.segmotype))",routines='ROUTINE work(x:INTEGER) BEGIN END work')
    def test_association_field_timer_rejected(self):self.reject('CONNECT TIMER TO g.segmotype')
    def test_association_field_counter_rejected(self):self.reject('FOR g.segmotype=1 TO 2 DO n=1 ENDFOR')
    def test_array_whole_uninit_remains_rejected(self):self.reject('flag=UNINIT(items)',decl=DECL+' items:ARRAY[2]OF GROUP_ASSOC')
    def test_non_positional_motion_operand_rejected(self):self.reject('MOVE TO g')
    def test_record_arithmetic_rejected(self):self.reject('g=g+g')
    def test_data_record_array_leaf_limit(self):self.reject(decl='items:ARRAY[8192]OF GROUP_ASSOC')
    def test_legacy_source_remains_rejected(self):
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T VAR g:GROUP_ASSOC BEGIN END T')
    def test_report_marks_data_only_behavior(self):
        _,r=build();p=r.report['association_record_policy'];self.assertFalse(p['controller_validated']);self.assertIn('STD_PTH_NODE',p['boundary']);self.assertEqual(p['guide'],'docs/association-records.md')
    def test_data_fields_do_not_guess_native_option_limits(self):self.assertEqual(execute('g.segrelspeed=500 c.segrelaccel=-100')['G']['SEGRELSPEED'],500)


class AssociationIntegrationTests(unittest.TestCase):
    def test_linked_whole_record_borrows_storage(self):
        p=translate_project({'lib':'PROGRAM LIB ROUTINE work(x:GROUP_ASSOC) BEGIN x.segmotype=7 END work BEGIN END LIB','main':'PROGRAM MAIN VAR g:GROUP_ASSOC ROUTINE work(x:GROUP_ASSOC) FROM LIB BEGIN work(g) END MAIN'}).instantiate();p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['G']['SEGMOTYPE'],7)
    def test_linked_scalar_field_is_value(self):
        p=translate_project({'lib':'PROGRAM LIB ROUTINE work(x:INTEGER) BEGIN x=9 END work BEGIN END LIB','main':'PROGRAM MAIN VAR g:GROUP_ASSOC ROUTINE work(x:INTEGER) FROM LIB BEGIN g.segmotype=7 work(g.segmotype) END MAIN'}).instantiate();p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['G']['SEGMOTYPE'],7)
    def test_linked_partial_record_result(self):
        p=translate_project({'lib':'PROGRAM LIB ROUTINE make:COMMON_ASSOC VAR x:COMMON_ASSOC BEGIN x.segtermtype=7 RETURN x END make BEGIN END LIB','main':'PROGRAM MAIN VAR c:COMMON_ASSOC ROUTINE make:COMMON_ASSOC FROM LIB BEGIN c=make() END MAIN'}).instantiate();p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['C'],dict(CMISSING,SEGTERMTYPE=7))
    def test_linked_array_borrows_storage(self):
        p=translate_project({'lib':'PROGRAM LIB ROUTINE work(x:ARRAY OF GROUP_ASSOC) BEGIN x[2].segmotype=7 END work BEGIN END LIB','main':'PROGRAM MAIN VAR g:ARRAY[2]OF GROUP_ASSOC ROUTINE work(x:ARRAY OF GROUP_ASSOC) FROM LIB BEGIN work(g) END MAIN'}).instantiate();p.run('MAIN');self.assertEqual(p.programs['MAIN'].snapshot()['G'][1]['SEGMOTYPE'],7)
    def test_user_record_alias_survives_whole_replacement(self):
        v=execute('a.axes.segmotype=7 b.axes.segmotype=9 work(a.axes)',prefix=TYPES,decl=DECL+' a,b:node_t',routines='ROUTINE work(x:GROUP_ASSOC) BEGIN a=b n=x.segmotype END work');self.assertEqual(v['N'],9)
    def test_scalar_value_survives_pause_without_copyback(self):
        p,_=build('g.segmotype=7 work(g.segmotype)',cooperative=True,routines='ROUTINE work(x:INTEGER) BEGIN PAUSE n=x x=1 END work')
        with self.assertRaises(rt.KarelPause):p.run()
        p._state.raw('G').values['SEGMOTYPE']=9;self.assertEqual((p.resume()['N'],p.snapshot()['G']['SEGMOTYPE']),(7,9))
    def test_custom_path_vr_round_trip(self):
        ctx=archive_context();v=execute("APPEND_NODE(track,s) track[1].axes.segmotype=7 SAVE('T','FR:T.VR',s) CLEAR('T.VR',s) LOAD('FR:T.VR',0,s)",prefix=TYPES,decl=AssociationPathTests.DECL,context=ctx);self.assertEqual(v['TRACK']['nodes'][0]['AXES']['SEGMOTYPE'],7)
    def test_dynamic_path_array_embeds_records(self):
        v=execute("CREATE_VAR('CACHE','ITEMS','','ARRAY OF route_t',0,2,0,0,s) work(BYNAME('CACHE','ITEMS',e)) GET_VAR(e,'CACHE','ITEMS[2]',track,s)",prefix=TYPES+' TYPE route_t=PATH NODEDATA=node_t',decl=DECL+' track:PATH NODEDATA=node_t',routines='ROUTINE work(x:ARRAY OF route_t) BEGIN APPEND_NODE(x[2],s) x[2][1].axes.segmotype=7 END work');self.assertEqual(v['TRACK']['nodes'][0]['AXES']['SEGMOTYPE'],7)
    def test_xml_common_record_root(self):
        from tests.test_xml_record_roots import build as xml
        v=xml('<item segtermtype="1" segdeceltol="25"/>','COMMON_ASSOC').run();self.assertEqual(v['VALUE'],dict(CMISSING,SEGTERMTYPE=1,SEGDECELTOL=25))
    def test_xml_group_record_root(self):
        from tests.test_xml_record_roots import build as xml
        v=xml('<item segrelspeed="50" segmotype="7" segbreak="off"/>','GROUP_ASSOC').run();self.assertEqual(v['VALUE'],dict(GMISSING,SEGRELSPEED=50,SEGMOTYPE=7,SEGBREAK=False))
    def test_xml_bad_boolean_preserves_record(self):
        from tests.test_xml_record_roots import build as xml
        p=xml('<item segmotype="7" segbreak="wrong"/>','GROUP_ASSOC');v=p.run();self.assertEqual(v['VALUE'],GMISSING);self.assertNotEqual(v['S'],0)
    def test_runtime_field_capture_checks_declared_schema(self):
        with rt._numeric_scope('pythonic'):
            reference=rt.AssociationFieldReference(('INTEGER',),{'SEGMOTYPE':7},'SEGMOTYPE',('GROUP_ASSOC',))
            with self.assertRaises(rt.KarelRuntimeError):reference.set(9)
            self.assertEqual(reference.storage['SEGMOTYPE'],7)
    def test_maxint_storage_boundary_is_retained(self):
        p,_=build('g.segrelspeed=7 g.segrelspeed=MAXINT')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['G']['SEGRELSPEED'],7)
    def test_missing_fields_do_not_hide_malformed_known_flag(self):
        p,_=build('flag=UNINIT(g)');p._state.raw('G').values['SEGBREAK']=1
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_leaf_limit_is_checked_before_records_are_allocated(self):
        from unittest.mock import patch
        with rt._numeric_scope('pythonic'),patch.object(rt,'Structure') as factory,self.assertRaises(rt.KarelRuntimeError):rt.Array(('ARRAY',8192,('GROUP_ASSOC',)))
        factory.assert_not_called()


if __name__=='__main__':unittest.main()
