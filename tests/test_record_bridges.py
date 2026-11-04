"""Authored builtin/user record bridges, private ownership and geometry guards."""
from copy import deepcopy
import json
import math
import unittest
from karel2py import runtime as rt,translate_project
from karel2py import extended as ex
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program
from tests.legacy_numeric_support import translate as legacy_translate

U={'uninitialized':True}
CFG={'CFG_TURN_NO1':-1,'CFG_TURN_NO2':0,'CFG_TURN_NO3':1,'CFG_FLIP':False,'CFG_LEFT':True,'CFG_UP':False,'CFG_FRONT':True}
XYZ={'X':1.,'Y':2.,'Z':3.}
DATA={
 'VECTOR':XYZ,
 'CONFIG':CFG,
 'XYZWPR':dict(XYZ,W=0.,P=0.,R=90.,CONFIG_DATA=CFG),
 'XYZWPREXT':dict(XYZ,W=0.,P=0.,R=90.,CONFIG_DATA=CFG,EXT1=4.,EXT2=-5.,EXT3=6.),
 'POSITION':{'NORMAL':{'X':1.,'Y':0.,'Z':0.},'ORIENT':{'X':0.,'Y':1.,'Z':0.},'APPROACH':{'X':0.,'Y':0.,'Z':1.},'LOCATION':XYZ,'CONFIG_DATA':CFG},
 'COMMON_ASSOC':dict(SEGTERMTYPE=1,SEGDECELTOL=2,SEGRELACCEL=3,SEGTIMESHFT=4),
 'GROUP_ASSOC':dict(SEGRELSPEED=50,SEGMOTYPE=2,SEGORIENTYPE=1,SEGBREAK=False)}


def definitions(*,integral=False):
    rows=[]
    for kind in ('VECTOR','CONFIG','XYZWPR','XYZWPREXT','POSITION','COMMON_ASSOC','GROUP_ASSOC'):
        fields=[]
        for name,spec in reversed(rt.record_fields((kind,))):
            field=('u_'+spec[0].lower() if spec[0] in rt.DATA_RECORD_TYPES else 'INTEGER' if integral and spec==rt.REAL else spec[0])
            fields.append(name+':'+field)
        rows.append('u_'+kind.lower()+'=STRUCTURE '+' '.join(fields)+' ENDSTRUCTURE')
    return 'TYPE '+' '.join(rows)


def fill(record,values):
    for name,value in values.items():
        if isinstance(value,dict) and 'uninitialized' not in value:fill(record.values[name],value)
        else:record.values[name]=rt.UNINITIALIZED if value==U else value
    return record


def build(kind='VECTOR',body='b=a c=b',routines='',*,integral=False,seed=True,**options):
    p,r=compile_program(body,prefix=definitions(integral=integral),decl=f'a,c:u_{kind.lower()} b:{kind} n,s,e,visits:INTEGER done:BOOLEAN',routines=routines,**options)
    if seed:
        data=deepcopy(DATA[kind])
        def integers(item):return {k:integers(v) if isinstance(v,dict) else int(v) if type(v) is float else v for k,v in item.items()}
        fill(p._state.values['A'],integers(data) if integral else data)
    return p,r


def variables(kind='VECTOR',body="GET_VAR(e,'','A',b,s)",*,seed=True,**options):return build(kind,body,seed=seed,**options)


class RecordBridgeValueTests(unittest.TestCase):
    def check_round_trip(self,kind):
        p,_=build(kind);self.assertEqual(p.run()['B'],DATA[kind]);self.assertEqual(p.snapshot()['C'],DATA[kind]);self.assertEqual(p.snapshot()['A'],DATA[kind])
        self.assertIsNot(p._state.values['A'],p._state.values['B']);self.assertEqual(p._state.values['B'].spec,(kind,))
    def test_vector_round_trip(self):self.check_round_trip('VECTOR')
    def test_config_round_trip(self):self.check_round_trip('CONFIG')
    def test_xyzwpr_round_trip(self):self.check_round_trip('XYZWPR')
    def test_xyzwprext_round_trip(self):self.check_round_trip('XYZWPREXT')
    def test_position_round_trip(self):self.check_round_trip('POSITION')
    def test_common_association_round_trip(self):self.check_round_trip('COMMON_ASSOC')
    def test_group_association_round_trip(self):self.check_round_trip('GROUP_ASSOC')
    def test_integral_fields_promote_into_vector(self):
        p,_=build(integral=True,body='b=a');self.assertEqual(p.run()['B'],XYZ);self.assertIs(type(p._state.values['B'].values['X']),float)
    def test_receiver_field_order_and_names_are_retained(self):
        p,_=build();p.run();self.assertEqual(list(p._state.values['C'].values),['Z','Y','X']);self.assertEqual(list(p._state.values['B'].values),['X','Y','Z'])
    def test_missing_vector_fields_remain_missing(self):
        p,_=build(seed=False);self.assertEqual(p.run()['B'],dict.fromkeys(('X','Y','Z'),U))
    def test_missing_config_turns_remain_missing(self):
        p,_=build('CONFIG',seed=False);p._state.values['A'].values['CFG_FLIP']=False;self.assertEqual(p.run()['B']['CFG_TURN_NO1'],U)
    def test_partial_position_can_be_read_into_private_user_data(self):
        p,_=build('POSITION',body='c=b',seed=False);self.assertEqual(p.run()['C']['NORMAL']['X'],U)
    def test_nested_receiver_aliases_are_preserved(self):
        p,_=build('POSITION');root=p._state.values['B'];normal=root.values['NORMAL'];config=root.values['CONFIG_DATA'];p.run();self.assertIs(p._state.values['B'],root);self.assertIs(root.values['NORMAL'],normal);self.assertIs(root.values['CONFIG_DATA'],config)
    def test_converted_data_does_not_share_nested_source_storage(self):
        p,_=build('XYZWPREXT',body='b=a c=b c.config_data.cfg_turn_no1=7');p.run();self.assertEqual(p.snapshot()['B']['CONFIG_DATA']['CFG_TURN_NO1'],-1);self.assertEqual(p.snapshot()['A']['CONFIG_DATA']['CFG_TURN_NO1'],-1)
    def test_complete_source_domain_is_checked_before_target(self):
        p,_=build('CONFIG');p._state.values['A'].values['CFG_FRONT']=1;before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],before)
    def test_assignment_target_selector_runs_after_conversion(self):
        p,_=compile_program('visits=0 out[pick()]=source',prefix=definitions(),decl='source:u_config out:ARRAY[2]OF CONFIG visits:INTEGER',routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN(1) END pick');fill(p._state.values['SOURCE'],dict(CFG,CFG_TURN_NO1=8))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)


class RecordBridgeRoutineTests(unittest.TestCase):
    def test_builtin_formal_is_private_for_user_source(self):
        p,_=build(body='change(a)',routines='ROUTINE change(v:VECTOR) BEGIN v.x=99 END change');p.run();self.assertEqual(p.snapshot()['A'],XYZ)
    def test_user_formal_is_private_for_builtin_source(self):
        p,_=build(body='b=a change(b)',routines='ROUTINE change(v:u_vector) BEGIN v.x=99 END change');p.run();self.assertEqual(p.snapshot()['B'],XYZ)
    def test_same_builtin_formal_retains_reference_semantics(self):
        p,_=build(body='b=a change(b)',routines='ROUTINE change(v:VECTOR) BEGIN v.x=99 END change');self.assertEqual(p.run()['B']['X'],99.)
    def test_same_user_formal_retains_reference_semantics(self):
        p,_=build(body='change(a)',routines='ROUTINE change(v:u_vector) BEGIN v.x=99 END change');self.assertEqual(p.run()['A']['X'],99.)
    def test_builtin_return_copies_user_data(self):
        p,_=build(body='b=make',routines='ROUTINE make:VECTOR BEGIN RETURN(a) END make');self.assertEqual(p.run()['B'],XYZ)
    def test_user_return_copies_builtin_data(self):
        p,_=build(body='b=a c=make',routines='ROUTINE make:u_vector BEGIN RETURN(b) END make');self.assertEqual(p.run()['C'],XYZ)
    def test_builtin_function_result_can_bridge_into_user_argument(self):
        p,_=build(body='b=a change(make)',routines='ROUTINE make:VECTOR BEGIN RETURN(b) END make ROUTINE change(v:u_vector) BEGIN v.x=99 END change');p.run();self.assertEqual(p.snapshot()['B'],XYZ)
    def test_cooperative_pause_retains_private_converted_formal(self):
        p,_=build(body='change(a)',routines='ROUTINE change(v:VECTOR) BEGIN v.x=99 PAUSE v.y=88 END change',cooperative=True)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.snapshot()['A'],XYZ);p.resume();self.assertEqual(p.snapshot()['A'],XYZ)
    def test_invalid_argument_prevents_later_selector_effects(self):
        p,_=build('CONFIG',body='visits=0 use(a,later())',routines='ROUTINE use(v:CONFIG;n:INTEGER) BEGIN END use ROUTINE later:INTEGER BEGIN visits=visits+1 RETURN(1) END later');p._state.values['A'].values['CFG_TURN_NO1']=8
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)
    def test_converted_position_formal_retains_orientation_protection(self):
        with self.assertRaises(TranslationError):build('POSITION',body='change(a)',routines='ROUTINE change(v:POSITION) BEGIN v.normal.x=99 END change')
    def test_cross_type_byname_remains_rejected_without_entry_write(self):
        p,_=build(body="e=77 change(BYNAME('','A',e))",routines='ROUTINE change(v:VECTOR) BEGIN END change')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['E'],77)
    def test_linked_signature_remains_exact(self):
        with self.assertRaisesRegex(ValueError,'type mismatch'):translate_project({'main':'PROGRAM MAIN ROUTINE use(v:VECTOR) FROM LIB BEGIN END MAIN','lib':'PROGRAM LIB TYPE item=STRUCTURE x:REAL y:REAL z:REAL ENDSTRUCTURE ROUTINE use(v:item) BEGIN END use BEGIN END LIB'}).instantiate()


class RecordBridgeArrayTests(unittest.TestCase):
    def task(self,body='b=a c=b',routines='',**options):
        p,r=compile_program(body,prefix=definitions(),decl='a,c:ARRAY[2]OF u_vector b:ARRAY[2]OF VECTOR',routines=routines,**options)
        fill(p._state.values['A'].values[0],XYZ);fill(p._state.values['A'].values[1],dict(XYZ,X=4.));return p,r
    def test_array_round_trip(self):
        p,_=self.task();self.assertEqual(p.run()['C'],[XYZ,dict(XYZ,X=4.)])
    def test_receiver_array_and_elements_keep_identity(self):
        p,_=self.task();array=p._state.values['B'];child=array.values[0];p.run();self.assertIs(p._state.values['B'],array);self.assertIs(array.values[0],child)
    def test_bare_generic_argument_receives_private_bridge(self):
        p,_=self.task('change(a)',routines='ROUTINE change(v:ARRAY OF VECTOR) BEGIN v[1].x=99 END change');p.run();self.assertEqual(p.snapshot()['A'][0],XYZ)
    def test_generic_receiver_uses_actual_builtin_schema(self):
        p,_=self.task('change(a,b)',routines='ROUTINE change(v:ARRAY OF u_vector;out:ARRAY OF VECTOR) BEGIN out=v END change');self.assertEqual(p.run()['B'][0],XYZ)
    def test_named_array_return_uses_receiver_leaf_schema(self):
        p,_=compile_program('source[1].x=1 source[1].y=2 source[1].z=3 result=make',prefix=definitions()+' TYPE vec_array=ARRAY[1]OF VECTOR',decl='source:ARRAY[1]OF u_vector result:vec_array',routines='ROUTINE make:vec_array BEGIN RETURN(source) END make');self.assertEqual(p.run()['RESULT'],[XYZ])
    def test_nested_user_record_fields_can_bridge_builtins(self):
        p,_=compile_program('b=a',prefix=definitions()+' TYPE in_t=STRUCTURE value:u_vector label:STRING[8] ENDSTRUCTURE out_t=STRUCTURE label:STRING[3] value:VECTOR ENDSTRUCTURE',decl='a:in_t b:out_t');fill(p._state.values['A'],{'VALUE':XYZ,'LABEL':'abcdefgh'});self.assertEqual(p.run()['B'],{'LABEL':'abc','VALUE':XYZ})
    def test_late_array_config_failure_preserves_all_receiver_elements(self):
        p,_=compile_program('b=a',prefix=definitions(),decl='a:ARRAY[2]OF u_config b:ARRAY[2]OF CONFIG');fill(p._state.values['A'].values[0],CFG);fill(p._state.values['A'].values[1],dict(CFG,CFG_TURN_NO3=8));before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],before)
    def test_array_shape_changes_remain_rejected(self):
        with self.assertRaises(TranslationError):compile_program('b=a',prefix=definitions(),decl='a:ARRAY[2]OF u_vector b:ARRAY[3]OF VECTOR')
    def test_boolean_user_fields_cannot_enter_integral_association(self):
        prefix='TYPE item=STRUCTURE segrelSpeed:BOOLEAN segmotype:INTEGER segorientype:INTEGER segbreak:BOOLEAN ENDSTRUCTURE'
        with self.assertRaises(TranslationError):compile_program('b=a',prefix=prefix,decl='a:item b:GROUP_ASSOC')


class RecordBridgeVariableTests(unittest.TestCase):
    def test_get_var_user_to_builtin(self):
        p,_=variables();self.assertEqual(p.run()['B'],XYZ);self.assertEqual(p.snapshot()['S'],0)
    def test_get_var_builtin_to_user(self):
        p,_=variables(body="b=a GET_VAR(e,'','B',c,s)");self.assertEqual(p.run()['C'],XYZ);self.assertEqual(p.snapshot()['S'],0)
    def test_set_var_user_to_builtin(self):
        p,_=variables(body="SET_VAR(e,'','B',a,s)");self.assertEqual(p.run()['B'],XYZ);self.assertEqual(p.snapshot()['S'],0)
    def test_set_var_builtin_to_user(self):
        p,_=variables(body="b=a SET_VAR(e,'','C',b,s)");self.assertEqual(p.run()['C'],XYZ)
    def test_get_var_config_turn_bounds_preserve_output_cache_and_status(self):
        p,_=variables('CONFIG',body="e=77 s=88 GET_VAR(e,'','A',b,s)");p._state.values['A'].values['CFG_TURN_NO1']=8;before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['E'],p.snapshot()['S'],p.snapshot()['B']),(77,88,before))
    def test_malformed_source_builtin_config_is_rejected_before_erasing_domain(self):
        p,_=variables('CONFIG',body="GET_VAR(e,'','B',c,s)");fill(p._state.values['B'],dict(CFG,CFG_TURN_NO1=8));before=p.snapshot()['C']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['C'],before)
    def test_partial_data_reports_existing_missing_status(self):
        p,_=variables(seed=False);self.assertEqual(p.run()['S'],12311);self.assertEqual(p.snapshot()['B']['X'],U)
    def test_get_var_array_prefix_bridges_selected_cells_and_preserves_tail(self):
        p,_=compile_program("GET_VAR(e,'','A',b,s)",prefix=definitions(),decl='a:ARRAY[1]OF u_vector b:ARRAY[2]OF VECTOR e,s:INTEGER');fill(p._state.values['A'].values[0],XYZ);fill(p._state.values['B'].values[1],dict(XYZ,X=99.));self.assertEqual(p.run()['B'],[XYZ,dict(XYZ,X=99.)])
    def test_set_var_array_prefix_preserves_unselected_tail(self):
        p,_=compile_program("SET_VAR(e,'','B',a,s)",prefix=definitions(),decl='a:ARRAY[1]OF u_vector b:ARRAY[2]OF VECTOR e,s:INTEGER');fill(p._state.values['A'].values[0],XYZ);fill(p._state.values['B'].values[1],dict(XYZ,X=99.));self.assertEqual(p.run()['B'],[XYZ,dict(XYZ,X=99.)])
    def test_variable_transfer_does_not_share_source_children(self):
        p,_=variables('XYZWPREXT',body="GET_VAR(e,'','A',b,s) b.config_data.cfg_turn_no1=7");p.run();self.assertEqual(p.snapshot()['A']['CONFIG_DATA']['CFG_TURN_NO1'],-1)
    def test_get_var_receiver_child_identity_is_preserved(self):
        p,_=variables('XYZWPREXT');root=p._state.values['B'];child=root.values['CONFIG_DATA'];p.run();self.assertIs(p._state.values['B'],root);self.assertIs(root.values['CONFIG_DATA'],child)
    def test_variable_position_bridge_checks_complete_geometry(self):
        p,_=variables('POSITION');p._state.values['A'].values['NORMAL'].values['X']=2.;before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],before)
    def test_variable_missing_whole_record_retains_missing_status(self):
        p,_=variables();p._state.values['A']=rt.UNINITIALIZED;self.assertEqual(p.run()['S'],12311)
    def test_variable_bridge_helper_is_pythonic_only(self):
        p,_=build();target=p._state.types['B'];source=p._state.values['A']
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):ex._variable_record_copy(target,source.spec,source)


class RecordBridgeGuardTests(unittest.TestCase):
    def test_partial_user_position_cannot_forge_protected_orientation(self):
        p,_=build('POSITION',seed=False);before=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],before)
    def test_nonunit_position_is_rejected(self):
        p,_=build('POSITION');p._state.values['A'].values['NORMAL'].values['X']=2.
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_left_handed_position_is_rejected(self):
        p,_=build('POSITION');p._state.values['A'].values['APPROACH'].values['Z']=-1.
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_position_config_turn_bounds_are_checked(self):
        p,_=build('POSITION');p._state.values['A'].values['CONFIG_DATA'].values['CFG_TURN_NO1']=8
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_unknown_byte_cannot_be_promoted_into_vector(self):
        p,_=compile_program('b=a',prefix='TYPE item=STRUCTURE x:BYTE y:BYTE z:BYTE ENDSTRUCTURE',decl='a:item b:VECTOR')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_nonfinite_user_fields_are_rejected(self):
        for value in (math.inf,math.nan):
            p,_=build();p._state.values['A'].values['X']=value
            with self.subTest(value=value),self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_missing_and_extra_field_names_are_rejected(self):
        for fields in ('x:REAL y:REAL','x:REAL y:REAL z:REAL extra:INTEGER'):
            with self.assertRaises(TranslationError):compile_program('b=a',prefix='TYPE item=STRUCTURE '+fields+' ENDSTRUCTURE',decl='a:item b:VECTOR')
    def test_field_renaming_is_not_inferred(self):
        with self.assertRaises(TranslationError):compile_program('b=a',prefix='TYPE item=STRUCTURE a:REAL b:REAL c:REAL ENDSTRUCTURE',decl='a:item b:VECTOR')
    def test_wrong_scalar_categories_are_rejected(self):
        with self.assertRaises(TranslationError):compile_program('b=a',prefix='TYPE item=STRUCTURE x:BOOLEAN y:REAL z:REAL ENDSTRUCTURE',decl='a:item b:VECTOR')
    def test_generic_helpers_do_not_gain_structural_coercion(self):
        p,_=build();source=p._state.values['A']
        with rt._numeric_scope('pythonic'):
            for call in (lambda:rt.checked(('VECTOR',),source),lambda:rt.value_argument(('VECTOR',),source)):
                with self.assertRaises(rt.KarelRuntimeError):call()
    def test_internal_strict_mode_remains_exact(self):
        p,_=build();source=p._state.values['A']
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.convert_record_schema(('VECTOR',),source)
    def test_legacy_source_remains_exact(self):
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T TYPE item=STRUCTURE x:REAL y:REAL z:REAL ENDSTRUCTURE VAR a:item b:VECTOR BEGIN b=a END T')
    def test_malformed_builtin_source_layout_is_rejected(self):
        p,_=build(body='c=b');p._state.values['B'].values.pop('X')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_malformed_user_source_schema_is_rejected(self):
        p,_=build();p._state.values['A'].types['X']=('INTEGER',)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_user_arrays_cannot_bridge_to_resources(self):
        for kind in ('FILE','QUEUE_TYPE','PATH'):
            with self.assertRaises(TranslationError):compile_program('b=a',prefix='TYPE item=STRUCTURE x:REAL y:REAL z:REAL ENDSTRUCTURE',decl=f'a:item b:{kind}')


class RecordBridgePersistenceTests(unittest.TestCase):
    def test_saved_typed_values_round_trip_with_concrete_receiver_types(self):
        p,_=build('XYZWPREXT',body='IF UNINIT(done) THEN b=a c=b done=TRUE ENDIF');p.run();data=json.loads(json.dumps(p._state.execution.to_config()));self.assertEqual(rt.ExecutionContext.from_config(data).to_config(),data)
    def test_json_replay_does_not_repeat_bridge_effects(self):
        body='IF UNINIT(done) THEN b=a c=b done=TRUE ENDIF';p,_=build(body=body);expected=p.run();context=rt.ExecutionContext.from_config(json.loads(json.dumps(p._state.execution.to_config())));again,_=build(body=body,seed=False,context=context);self.assertEqual(again.run(),expected)
    def test_vr_archive_retains_builtin_receiver(self):
        ctx=rt.ExecutionContext(variable_archives=rt.VariableArchives(),files=rt.MemoryFiles());p,_=build(body='b=a transact',routines="ROUTINE transact VAR status:INTEGER BEGIN SAVE('T','bridge.VR',status) b.x=99 LOAD('bridge.VR',0,status) END transact",context=ctx);p.run();self.assertEqual(p.snapshot()['B'],XYZ)
        archive=json.loads(ctx.files.files['BRIDGE.VR']);self.assertEqual(archive['variables']['B'],dict(type=['VECTOR'],value=XYZ))
    def test_array_observation_records_the_receiver_schema(self):
        p,r=RecordBridgeArrayTests().task();self.assertTrue(r.report['record_schema_conversions']);self.assertEqual(r.report['record_schema_conversions'][0]['conversion_kind'],'record_array')


class RecordBridgeModelTests(unittest.TestCase):
    def task(self,action='assign',*,kind='CONFIG',outgoing=False):
        from tests.test_kinematic_assignments import callback_context
        from tests.test_kinematic_arrays import forward_adapter
        from tests.test_joint_interoperability import joint
        calls=[];ctx=callback_context(forward=forward_adapter(calls))
        first=kind if outgoing else 'u_'+kind.lower();second='u_'+kind.lower() if outgoing else kind
        prefix=definitions()+f' TYPE first_t=STRUCTURE joints:JOINTPOS2 payload:{first} ENDSTRUCTURE second_t=STRUCTURE joints:POSITION payload:{second} ENDSTRUCTURE'
        body={'assign':'b=a','get':"GET_VAR(e,'','A',b,s)",'set':"SET_VAR(e,'','B',a,s)"}[action]
        p,_=compile_program(body,prefix=prefix,decl='a:first_t b:second_t e,s:INTEGER',context=ctx)
        p._state.values['A'].values['JOINTS']=joint([0.,90.]);fill(p._state.values['A'].values['PAYLOAD'],DATA[kind]);return p,calls
    def check_success(self,action):
        p,calls=self.task(action);self.assertEqual(p.run()['B']['PAYLOAD'],CFG);self.assertEqual(len(calls),1)
    def test_source_assignment_combines_model_and_builtin_bridge(self):self.check_success('assign')
    def test_get_var_combines_model_and_builtin_bridge(self):self.check_success('get')
    def test_set_var_combines_model_and_builtin_bridge(self):self.check_success('set')
    def check_failure(self,action,*,kind='CONFIG',outgoing=False):
        p,calls=self.task(action,kind=kind,outgoing=outgoing);source=p._state.values['A'].values['PAYLOAD'];before=p.snapshot()['B']
        if kind=='CONFIG':source.values['CFG_TURN_NO1']=8
        else:source.values['NORMAL'].values['X']=2.
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[]);self.assertEqual(p.snapshot()['B'],before)
    def test_source_bad_config_prevents_model_callback(self):self.check_failure('assign')
    def test_get_var_bad_config_prevents_model_callback(self):self.check_failure('get')
    def test_set_var_bad_config_prevents_model_callback(self):self.check_failure('set')
    def test_get_var_outgoing_builtin_retains_config_domain_validation(self):self.check_failure('get',outgoing=True)
    def test_set_var_outgoing_builtin_retains_config_domain_validation(self):self.check_failure('set',outgoing=True)
    def test_source_bad_position_prevents_model_callback(self):self.check_failure('assign',kind='POSITION')
    def test_get_var_bad_position_prevents_model_callback(self):self.check_failure('get',kind='POSITION')
    def test_set_var_bad_position_prevents_model_callback(self):self.check_failure('set',kind='POSITION')
    def test_valid_position_bridge_can_share_model_conversion_plan(self):
        p,calls=self.task(kind='POSITION');self.assertEqual(p.run()['B']['PAYLOAD'],DATA['POSITION']);self.assertEqual(len(calls),1)


class RecordBridgeAdditionalGuards(unittest.TestCase):
    def test_converted_argument_does_not_alias_an_active_integral_counter(self):
        p,_=build(integral=True,body='visits=0 FOR a.x=1 TO 2 DO change(a) visits=visits+1 ENDFOR',routines='ROUTINE change(v:VECTOR) BEGIN v.y=99 END change');self.assertEqual(p.run()['VISITS'],2);self.assertEqual(p.snapshot()['A']['Y'],2)
    def test_raw_callback_result_remains_exact(self):
        ctx=rt.ExecutionContext();p,_=build(body='b=make()',routines='ROUTINE make:VECTOR FROM LIB',context=ctx);ctx.externals[('LIB','MAKE')]=lambda:p._state.values['A']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_source_nominal_schema_is_validated_before_bridge(self):
        p,_=build();source=p._state.values['A'];other=('STRUCTURE','OTHER',source.spec[2])
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):rt.convert_record_schema(('VECTOR',),source,23,source_spec=other)
    def test_leaf_budget_is_enforced_before_array_bridge_allocation(self):
        spec=('STRUCTURE','ITEM',tuple((k,rt.REAL) for k in ('X','Y','Z')));source=rt.Array(('ARRAY',1,spec));source.spec=('ARRAY',11000,spec);source.shape=(11000,)
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):rt.convert_record_schema(('ARRAY',11000,('VECTOR',)),source,23)
    def test_source_config_cannot_erase_invalid_turn_domain(self):
        p,_=build('CONFIG',body='c=b');fill(p._state.values['B'],dict(CFG,CFG_TURN_NO1=8));before=p.snapshot()['C']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['C'],before)


class RecordBridgeReportTests(unittest.TestCase):
    def test_report_lists_every_supported_builtin_and_explicit_extension(self):
        _,r=build();policy=r.report['record_bridge_policy'];self.assertEqual(set(policy['types']),set(DATA));self.assertFalse(policy['controller_validated']);self.assertEqual(policy['guide'],'docs/record-bridges.md');self.assertIn('Pythonic',policy['forms'])
    def test_report_preserves_geometry_alias_and_model_boundaries(self):
        _,r=build();policy=r.report['record_bridge_policy'];self.assertIn('before any model callback',policy['validation']);self.assertIn('BYNAME',policy['exact']);self.assertIn('read-only',policy['exact']);self.assertIn('64 schema levels',policy['limits'])
    def test_report_does_not_retain_blanket_builtin_user_exclusion(self):
        _,r=build();self.assertNotIn('builtin-record/user-STRUCTURE interchange',r.report['record_schema_policy']['limits'])


if __name__=='__main__':unittest.main()
