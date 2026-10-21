"""XYZWPR extraction, seven output effects, alias guards and no partial updates."""
import unittest
from karel2py import translate,runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError

FIELDS=('X','Y','Z','W','P','R')
CONFIG=dict(CFG_TURN_NO1=0,CFG_TURN_NO2=-1,CFG_TURN_NO3=2,CFG_FLIP=False,CFG_LEFT=True,CFG_UP=False,CFG_FRONT=True)
VALUES=(1.25,-2.5,3.,0.,90.,-180.)

def initialize(name='pose'):
    text=' '.join(f'{name}.{field}={value}' for field,value in zip(FIELDS,VALUES))
    return text+' '+' '.join(f'{name}.config_data.{field}='+(('ON' if value else 'OFF') if type(value)is bool else str(value)) for field,value in CONFIG.items())

def compile_program(body='',*,declarations='pose: XYZWPR\nx,y,z,w,p,r: REAL\ncfg: CONFIG',prefix='',routines='', _translator=translate):
    result=_translator(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',filename='unpos.kl')
    namespace={'__name__':'unpos_test'}
    exec(result.python_source,namespace)
    return namespace['Program'](),result

CALL='UNPOS(pose,x,y,z,w,p,r,cfg)'

def runtime_fixture():
    source=rt.Structure(('XYZWPR',))
    source.values.update(zip(FIELDS,VALUES))
    source.values['CONFIG_DATA'].values.update(CONFIG)
    source_ref=rt.Reference(('XYZWPR',),{'source':source},'source')
    storage={name:99. for name in FIELDS}
    storage['CFG']=rt.Structure(('CONFIG',))
    targets=[rt.Reference(('REAL',),storage,name) for name in FIELDS]+[rt.Reference(('CONFIG',),storage,'CFG')]
    return source_ref,targets,storage


class UnposExtractionTests(unittest.TestCase):
    def test_all_six_components_and_configuration(self):
        program,_=compile_program(initialize()+' '+CALL)
        state=program.run()
        self.assertEqual(tuple(state[field] for field in FIELDS),VALUES)
        self.assertEqual(state['CFG'],CONFIG)
    def test_configuration_is_independent_copy(self):
        program,_=compile_program(initialize()+' '+CALL+' cfg.cfg_flip=ON pose.config_data.cfg_turn_no2=4')
        state=program.run()
        self.assertFalse(state['POSE']['CONFIG_DATA']['CFG_FLIP'])
        self.assertEqual(state['CFG']['CFG_TURN_NO2'],-1)
    def test_source_scalar_is_independent(self):
        program,_=compile_program(initialize()+' '+CALL+' x=99 pose.y=77')
        state=program.run()
        self.assertEqual((state['POSE']['X'],state['Y']),(1.25,-2.5))
    def test_unknown_output_contents_are_overwritten(self):
        source,targets,storage=runtime_fixture()
        for target in targets[:6]: target.clear()
        rt.unpos(source,targets)
        self.assertEqual(tuple(storage[name] for name in FIELDS),VALUES)
        self.assertEqual(storage['CFG'].values,CONFIG)
    def test_captured_config_field_alias_survives_output(self):
        source,targets,storage=runtime_fixture()
        field=rt.field_reference(storage['CFG'],'CFG_TURN_NO2')
        rt.unpos(source,targets)
        self.assertEqual(field.raw(),-1)
        field.set(4)
        self.assertEqual(storage['CFG'].values['CFG_TURN_NO2'],4)
    def test_array_output_elements(self):
        program,_=compile_program(initialize()+' UNPOS(pose,vals[1],vals[2],vals[3],vals[4],vals[5],vals[6],cfg)',declarations='pose: XYZWPR\nvals: ARRAY[6] OF REAL\ncfg: CONFIG')
        self.assertEqual(program.run()['VALS'],list(VALUES))
    def test_array_source_and_config_destination(self):
        program,_=compile_program(initialize('poses[2]')+' UNPOS(poses[2],x,y,z,w,p,r,configs[1])',declarations='poses: ARRAY[2] OF XYZWPR\nx,y,z,w,p,r: REAL\nconfigs: ARRAY[1] OF CONFIG')
        self.assertEqual(program.run()['CONFIGS'][0],CONFIG)
    def test_nested_structure_references(self):
        prefix='TYPE box_t=STRUCTURE pose: XYZWPR vals: ARRAY[6] OF REAL configuration: CONFIG ENDSTRUCTURE'
        outputs=','.join(f'box.vals[{i}]' for i in range(1,7))
        program,_=compile_program(initialize('box.pose')+f' UNPOS(box.pose,{outputs},box.configuration)',prefix=prefix,declarations='box: box_t')
        state=program.run()['BOX']
        self.assertEqual((state['VALS'],state['CONFIGURATION']),(list(VALUES),CONFIG))
    def test_multidimensional_output_elements(self):
        program,_=compile_program(initialize()+' UNPOS(pose,vals[1,1],vals[1,2],vals[1,3],vals[2,1],vals[2,2],vals[2,3],cfg)',declarations='pose: XYZWPR\nvals: ARRAY[2,3] OF REAL\ncfg: CONFIG')
        self.assertEqual(program.run()['VALS'],[list(VALUES[:3]),list(VALUES[3:])])
    def test_generic_array_output_forwarding(self):
        routines='ROUTINE extract(vals: ARRAY OF REAL; dest: CONFIG) BEGIN UNPOS(pose,vals[1],vals[2],vals[3],vals[4],vals[5],vals[6],dest) END extract'
        program,_=compile_program(initialize()+' extract(values,cfg)',declarations='pose: XYZWPR\nvalues: ARRAY[6] OF REAL\ncfg: CONFIG',routines=routines)
        self.assertEqual(program.run()['VALUES'],list(VALUES))
    def test_local_routine_output_storage(self):
        routines='ROUTINE extract: REAL VAR x,y,z,w,p,r: REAL cfg: CONFIG BEGIN '+CALL+' RETURN x+y END extract'
        program,_=compile_program(initialize()+' result=extract()+1',declarations='pose: XYZWPR\nresult: REAL',routines=routines)
        self.assertEqual(program.run()['RESULT'],-.25)
    def test_using_qualification(self):
        prefix='TYPE box_t=STRUCTURE pose: XYZWPR x: REAL y: REAL z: REAL w: REAL p: REAL r: REAL cfg: CONFIG ENDSTRUCTURE'
        program,_=compile_program(initialize('box.pose')+' USING box DO '+CALL+' ENDUSING',prefix=prefix,declarations='box: box_t')
        self.assertEqual(program.run()['BOX']['X'],1.25)
    def test_label_dispatch(self):
        program,_=compile_program(initialize()+' GO TO extract\nextract:: '+CALL)
        self.assertEqual(program.run()['X'],1.25)
    def test_case_insensitivity(self):
        program,_=compile_program(initialize()+' unpos(POSE,X,Y,Z,W,P,R,CFG)')
        self.assertEqual(program.run()['X'],1.25)
    def test_static_report_records_all_outputs(self):
        _,result=compile_program(CALL)
        self.assertIn('UNPOS',result.report['features'])
        self.assertEqual(result.report['unpos_calls'][0]['output_parameters'],list(range(2,9)))
        self.assertFalse(result.report['unpos_policy']['controller_validated'])
    def test_source_line_on_runtime_rejection(self):
        program,result=compile_program(CALL)
        with self.assertRaises(rt.KarelRuntimeError) as caught: program.run()
        self.assertEqual(caught.exception.line,result.report['unpos_calls'][0]['line'])


class UnposAliasAndAtomicityTests(unittest.TestCase):
    def test_duplicate_scalar_output_rejected_before_writes(self):
        source,targets,storage=runtime_fixture()
        targets[1]=targets[0]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlapping'): rt.unpos(source,targets,17)
        self.assertEqual(tuple(storage[name] for name in FIELDS),(99.,)*6)
    def test_source_scalar_output_overlap(self):
        source,targets,storage=runtime_fixture()
        targets[0]=rt.field_reference(source.raw(),'X')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlapping'): rt.unpos(source,targets)
        self.assertEqual(source.raw().values['X'],1.25)
        self.assertEqual(storage['Y'],99.)
    def test_source_configuration_output_overlap(self):
        source,targets,storage=runtime_fixture()
        targets[-1]=rt.field_reference(source.raw(),'CONFIG_DATA')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlapping'): rt.unpos(source,targets)
        self.assertEqual(storage['X'],99.)
    def test_forwarded_duplicate_alias(self):
        routines='ROUTINE extract(first: REAL; second: REAL) BEGIN UNPOS(pose,first,second,z,w,p,r,cfg) END extract'
        program,_=compile_program(initialize()+' x=99 extract(x,x)',routines=routines)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlapping'): program.run()
        self.assertEqual(program.snapshot()['X'],99.)
        self.assertEqual(program._state.local_frames,[])
    def test_dynamic_equal_indices(self):
        program,_=compile_program(initialize()+' i=1 j=1 values[1]=99 UNPOS(pose,values[i],values[j],values[3],values[4],values[5],values[6],cfg)',declarations='pose: XYZWPR\nvalues: ARRAY[6] OF REAL\ncfg: CONFIG\ni,j: INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlapping'): program.run()
        self.assertEqual(program.snapshot()['VALUES'][0],99.)
    def test_equal_scalar_values_are_not_aliases(self):
        source,targets,storage=runtime_fixture()
        rt.unpos(source,targets)
        self.assertEqual(storage['X'],1.25)
    def test_distinct_records_sharing_common_parent_are_allowed(self):
        program,_=compile_program(initialize('poses[1]')+' UNPOS(poses[1],poses[2].x,poses[2].y,poses[2].z,poses[2].w,poses[2].p,poses[2].r,poses[2].config_data)',declarations='poses: ARRAY[2] OF XYZWPR')
        state=program.run()['POSES']
        self.assertEqual(state[0],state[1])
    def test_last_source_component_unknown_preserves_all_outputs(self):
        source,targets,storage=runtime_fixture()
        source.raw().values['R']=rt.UNINITIALIZED
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): rt.unpos(source,targets)
        self.assertEqual(tuple(storage[name] for name in FIELDS),(99.,)*6)
    def test_unknown_configuration_preserves_all_outputs(self):
        source,targets,storage=runtime_fixture()
        source.raw().values['CONFIG_DATA'].values['CFG_FRONT']=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError): rt.unpos(source,targets)
        self.assertEqual(storage['X'],99.)
    def test_invalid_config_turn_preserves_all_outputs(self):
        source,targets,storage=runtime_fixture()
        source.raw().values['CONFIG_DATA'].values['CFG_TURN_NO3']=8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): rt.unpos(source,targets)
        self.assertEqual(storage['X'],99.)
    def test_inexact_source_component_preserves_all_outputs(self):
        source,targets,storage=runtime_fixture()
        source.raw().values['R']=.1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'rounding'): rt.unpos(source,targets)
        self.assertEqual(storage['X'],99.)
    def test_invalid_config_boolean_preserves_all_outputs(self):
        source,targets,storage=runtime_fixture()
        source.raw().values['CONFIG_DATA'].values['CFG_FRONT']=1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'BOOLEAN'): rt.unpos(source,targets)
        self.assertEqual(storage['X'],99.)
    def test_read_only_output_runtime_guard(self):
        source,targets,storage=runtime_fixture()
        targets[0]=rt.ReadOnlyFieldReference(('REAL',),storage,'X')
        with self.assertRaises(rt.KarelRuntimeError): rt.unpos(source,targets)
        self.assertEqual(storage['Y'],99.)
    def test_host_reference_wrong_types_and_arity(self):
        source,targets,storage=runtime_fixture()
        for outputs in (targets[:-1],targets+[targets[0]],None):
            with self.subTest(outputs=outputs),self.assertRaises(rt.KarelRuntimeError): rt.unpos(source,outputs)
        targets[-1]=rt.Reference(('INTEGER',),storage,'CFG')
        with self.assertRaises(rt.KarelRuntimeError): rt.unpos(source,targets)
        self.assertEqual(storage['X'],99.)
    def test_malformed_source_shapes(self):
        for field in ('X','CONFIG_DATA'):
            source,targets,storage=runtime_fixture()
            del source.raw().values[field]
            with self.subTest(field=field),self.assertRaises(rt.KarelRuntimeError): rt.unpos(source,targets)
            self.assertEqual(storage['X'],99.)
    def test_malformed_source_config_shape(self):
        source,targets,storage=runtime_fixture()
        del source.raw().values['CONFIG_DATA'].values['CFG_FRONT']
        with self.assertRaises(rt.KarelRuntimeError): rt.unpos(source,targets)
        self.assertEqual(storage['X'],99.)
    def test_malformed_destination_config_is_guarded_before_writes(self):
        source,targets,storage=runtime_fixture()
        del storage['CFG'].values['CFG_FRONT']
        with self.assertRaisesRegex(rt.KarelRuntimeError,'malformed storage'): rt.unpos(source,targets)
        self.assertEqual(tuple(storage[name] for name in FIELDS),(99.,)*6)


class UnposTranslationGuardTests(unittest.TestCase):
    def reject(self,body,**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        return caught.exception.code
    def test_wrong_arity(self): self.assertEqual(self.reject('UNPOS(pose,x,y,z,w,p,cfg)'),'E_ARGUMENTS')
    def test_wrong_source_types(self):
        for source_type in ('POSITION','XYZWPREXT','JOINTPOS3','VECTOR','CONFIG'):
            with self.subTest(source_type=source_type):
                self.assertEqual(self.reject(CALL,declarations=f'pose: {source_type}\nx,y,z,w,p,r: REAL\ncfg: CONFIG'),'E_TYPE')
    def test_no_scalar_output_promotion(self): self.assertEqual(self.reject(CALL,declarations='pose: XYZWPR\nx: INTEGER\ny,z,w,p,r: REAL\ncfg: CONFIG'),'E_TYPE')
    def test_output_expression_blocked(self): self.assertEqual(self.reject(CALL.replace(',x,',',x+1,')),'E_UNPOS_ARGUMENT')
    def test_grouped_input_blocked(self): self.assertEqual(self.reject(CALL.replace('(pose,','((pose),')),'E_UNPOS_ARGUMENT')
    def test_grouped_output_blocked(self): self.assertEqual(self.reject(CALL.replace(',x,',',(x),')),'E_UNPOS_ARGUMENT')
    def test_read_only_orientation_output_blocked(self):
        self.assertEqual(self.reject(CALL.replace(',x,',',frame.normal.x,'),declarations='pose: XYZWPR\nframe: POSITION\nx,y,z,w,p,r: REAL\ncfg: CONFIG'),'E_POSITION_READ_ONLY')
    def test_config_scalar_output_blocked(self): self.assertEqual(self.reject(CALL.replace(',x,',',cfg.cfg_turn_no1,')),'E_CONFIG_OUTPUT')
    def test_function_argument_blocked(self):
        self.assertEqual(self.reject(CALL.replace(',x,',',values[index_fn()],'),declarations='pose: XYZWPR\nvalues: ARRAY[6] OF REAL\ny,z,w,p,r: REAL\ncfg: CONFIG',routines='ROUTINE index_fn: INTEGER BEGIN RETURN 1 END index_fn', _translator=legacy_translate),'E_EVALUATION_ORDER')
    def test_procedure_result_blocked(self): self.assertEqual(self.reject('x='+CALL),'E_PROCEDURE_RESULT')
    def test_global_for_call_blocked(self):
        self.assertEqual(self.reject('FOR i=1 TO 2 DO '+CALL+' ENDFOR',declarations='pose: XYZWPR\nx,y,z,w,p,r: REAL\ncfg: CONFIG\ni: INTEGER', _translator=legacy_translate),'E_FOR_COUNTER')
    def test_all_seven_output_effects(self):
        routines='ROUTINE extract(src: XYZWPR; a,b,c,d,e,f: REAL; cfg_out: CONFIG) BEGIN UNPOS(src,a,b,c,d,e,f,cfg_out) END extract'
        _,result=compile_program('',routines=routines)
        self.assertEqual(result.report['routine_effects']['EXTRACT']['potential_parameter_writes'],['A','B','C','CFG_OUT','D','E','F'])
    def test_effects_forward_transitively(self):
        routines='ROUTINE extract(src: XYZWPR; a,b,c,d,e,f: REAL; cfg_out: CONFIG) BEGIN UNPOS(src,a,b,c,d,e,f,cfg_out) END extract\nROUTINE relay(src: XYZWPR; a,b,c,d,e,f: REAL; cfg_out: CONFIG) BEGIN extract(src,a,b,c,d,e,f,cfg_out) END relay'
        _,result=compile_program('',routines=routines)
        self.assertEqual(result.report['routine_effects']['RELAY']['potential_parameter_writes'],['A','B','C','CFG_OUT','D','E','F'])
    def test_effectful_function_in_operator_blocked(self):
        routines='ROUTINE extract: REAL BEGIN '+CALL+' RETURN x END extract'
        self.assertEqual(self.reject('x=extract()+1',routines=routines, _translator=legacy_translate),'E_EVALUATION_ORDER')
    def test_legacy_pos_constructor_remains_blocked(self): self.reject('pose=POS(1,2,3,0,90,180,cfg)',_translator=legacy_translate)


if __name__=='__main__': unittest.main()
