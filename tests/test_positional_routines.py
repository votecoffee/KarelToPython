"""Exact-type positional routine values, protected copies and width guards."""
import ast
import unittest
from karel2py import translate,runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from tests.test_data_records import init_config,init_pose

CONFIG=dict(CFG_TURN_NO1=0,CFG_TURN_NO2=0,CFG_TURN_NO3=0,CFG_FLIP=False,CFG_LEFT=False,CFG_UP=False,CFG_FRONT=False)
POSE=dict(X=1.,Y=2.,Z=3.,W=0.,P=90.,R=180.,CONFIG_DATA=CONFIG)
POSE_FACTORY='ROUTINE make: XYZWPR VAR p: XYZWPR BEGIN '+init_pose()+' RETURN p END make'
NEW_TYPES=('CONFIG','XYZWPR','XYZWPREXT','POSITION','JOINTPOS3')

def compile_program(body='',*,declarations='p,q: XYZWPR c,d: CONFIG n: INTEGER',routines='',prefix='',joint_axes=None,labelled=False, _translator=translate):
    label='entry::\n' if labelled else ''
    result=_translator(f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n{label}{body}\nEND T',filename='positional_routines.kl')
    ast.parse(result.python_source,feature_version=(3,11))
    namespace={'__name__':'positional_routine_test'}; exec(result.python_source,namespace)
    return namespace['Program'](joint_axes=joint_axes),result

def execute(body='',**kwargs): return compile_program(body,**kwargs)[0].run()

def initialized_host(spec):
    """Explicit synthetic data only; no controller position acquisition/default."""
    kind=spec[0]
    if kind=='JOINTPOS':
        value=rt.JointPosition(spec); value.values[:]=[float(n+1) for n in range(rt.joint_width(spec))]; return value
    if kind in rt.RECORD_TYPES:
        value=rt.Structure(spec)
        for name,field in rt.record_fields(spec): value.values[name]=rt.replace_value(value.values[name],initialized_host(field))
        if kind=='POSITION':
            for name,components in zip(rt.POSITION_READ_ONLY_FIELDS,((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))):
                value.values[name].values.update(zip(('X','Y','Z'),components))
        return value
    return 0 if kind=='INTEGER' else False if kind=='BOOLEAN' else 1.0


class CartesianRoutineTests(unittest.TestCase):
    def test_local_xyzwpr_return(self): self.assertEqual(execute('q=make()',routines=POSE_FACTORY)['Q'],POSE)
    def test_global_return_is_independent(self):
        state=execute(init_pose()+' q=get() p.x=99',routines='ROUTINE get: XYZWPR BEGIN RETURN p END get')
        self.assertEqual(state['Q'],POSE)
    def test_reference_formal_result_is_independent(self):
        state=execute(init_pose()+' q=echo(p) p.x=99',routines='ROUTINE echo(v: XYZWPR): XYZWPR BEGIN RETURN v END echo')
        self.assertEqual(state['Q'],POSE)
    def test_grouped_pose_temporary_can_be_written(self):
        state=execute(init_pose()+' change((p))',routines='ROUTINE change(v: XYZWPR) BEGIN v.x=99 v.config_data.cfg_flip=ON END change')
        self.assertEqual(state['P'],POSE)
    def test_bare_pose_reference_still_writes_caller(self):
        self.assertEqual(execute(init_pose()+' change(p)',routines='ROUTINE change(v: XYZWPR) BEGIN v.x=99 END change')['P']['X'],99.)
    def test_pose_function_result_argument(self):
        state=execute('q=change(make())',routines=POSE_FACTORY+'\nROUTINE change(v: XYZWPR): XYZWPR BEGIN v.x=99 RETURN v END change')
        self.assertEqual(state['Q'],{**POSE,'X':99.})
    def test_nested_returns(self): self.assertEqual(execute('q=outer()',routines=POSE_FACTORY+'\nROUTINE outer: XYZWPR BEGIN RETURN make() END outer')['Q'],POSE)
    def test_recursive_frames(self):
        routine=POSE_FACTORY+'\nROUTINE recurse(k: INTEGER): XYZWPR VAR local: XYZWPR BEGIN IF k=0 THEN RETURN make() ENDIF local=recurse(k-1) local.x=local.x+k RETURN local END recurse'
        self.assertEqual(execute('q=recurse(3)',routines=routine)['Q']['X'],7.)
    def test_labelled_return(self): self.assertEqual(execute('q=get()',routines=POSE_FACTORY+'\nROUTINE get: XYZWPR BEGIN GOTO value value:: RETURN make() END get')['Q'],POSE)
    def test_return_from_fresh_local_for(self):
        routine=POSE_FACTORY+'\nROUTINE get: XYZWPR VAR i: INTEGER BEGIN FOR i=1 TO 2 DO RETURN make() ENDFOR END get'
        self.assertEqual(execute('q=get()',routines=routine)['Q'],POSE)
    def test_array_element_result_and_value(self):
        state=execute(init_pose('items[1]')+' items[2]=echo((items[1]))',declarations='items: ARRAY[2] OF XYZWPR',routines='ROUTINE echo(v: XYZWPR): XYZWPR BEGIN RETURN v END echo')
        self.assertEqual(state['ITEMS'],[POSE,POSE])
    def test_structure_field_value(self):
        state=execute(init_pose('box.pose')+' change((box.pose))',prefix='TYPE box_t=STRUCTURE pose: XYZWPR ENDSTRUCTURE',declarations='box: box_t',routines='ROUTINE change(v: XYZWPR) BEGIN v.x=99 END change')
        self.assertEqual(state['BOX']['POSE'],POSE)
    def test_owned_temporary_forwarding_and_captured_field(self):
        routines=POSE_FACTORY+'\nROUTINE inner(v: XYZWPR; x: REAL) BEGIN v=make() x=99 END inner\nROUTINE forward(v: XYZWPR) BEGIN inner(v,v.x) n=ROUND(v.x) END forward'
        state=execute(init_pose()+' forward((p))',routines=routines)
        self.assertEqual((state['P'],state['N']),(POSE,99))
    def test_repeated_and_mixed_pose_values(self):
        routine='ROUTINE work(v,w: XYZWPR) BEGIN v.x=99 n=ROUND(w.x) END work'
        state=execute(init_pose()+' work(p,(p))',routines=routine)
        self.assertEqual((state['P']['X'],state['N']),(99.,1))
    def test_extended_fields_return_and_copy(self):
        init=init_pose('ext')+' ext.ext1=1 ext.ext2=2 ext.ext3=3'
        state=execute(init+' saved=revise((ext))',declarations='ext,saved: XYZWPREXT',routines='ROUTINE revise(v: XYZWPREXT): XYZWPREXT BEGIN v.ext1=99 RETURN v END revise')
        self.assertEqual(state['EXT'],{**POSE,'EXT1':1.,'EXT2':2.,'EXT3':3.})
        self.assertEqual(state['SAVED'],{**POSE,'EXT1':99.,'EXT2':2.,'EXT3':3.})
    def test_config_local_result(self):
        routine='ROUTINE get: CONFIG VAR local: CONFIG BEGIN '+init_config('local')+' RETURN local END get'
        self.assertEqual(execute('d=get()',routines=routine)['D'],CONFIG)
    def test_config_value_and_return_preserve_original(self):
        routine='ROUTINE revise(v: CONFIG): CONFIG BEGIN v.cfg_turn_no1=-1 v.cfg_flip=ON RETURN v END revise'
        state=execute(init_config()+' d=revise((c))',routines=routine)
        self.assertEqual(state['C'],CONFIG); self.assertEqual(state['D'],{**CONFIG,'CFG_TURN_NO1':-1,'CFG_FLIP':True})
    def test_config_subfields_remain_value_only(self):
        routine='ROUTINE change(k: INTEGER) BEGIN k=7 END change\nROUTINE work(v: CONFIG): CONFIG BEGIN change(v.cfg_turn_no1) RETURN v END work'
        self.assertEqual(execute(init_config()+' d=work((c))',routines=routine)['D'],CONFIG)
    def test_pure_record_consumer_in_scalar_expression(self):
        self.assertEqual(execute('n=read_x(make())+1',routines=POSE_FACTORY+'\nROUTINE read_x(v: XYZWPR): INTEGER BEGIN RETURN ROUND(v.x) END read_x')['N'],2)
    def test_single_evaluation_of_value_function_result(self):
        routines=POSE_FACTORY+'\nROUTINE counted: XYZWPR BEGIN n=n+1 RETURN make() END counted\nROUTINE inspect(v: XYZWPR) BEGIN END inspect'
        self.assertEqual(execute('n=0 inspect(counted())',routines=routines)['N'],1)


class PositionRoutineFixtureTests(unittest.TestCase):
    def seeded(self,body='',routines=''):
        program,result=compile_program(body,declarations='p,q: POSITION',routines=routines)
        rt.replace_value(program._state.raw('P'),initialized_host(('POSITION',)))
        return program,result
    def test_position_value_and_result_are_independent(self):
        program,_=self.seeded('q=revise((p)) p.location.x=7','ROUTINE revise(v: POSITION): POSITION BEGIN v.location.x=99 RETURN v END revise')
        state=program.run(); self.assertEqual((state['P']['LOCATION']['X'],state['Q']['LOCATION']['X']),(7.,99.))
    def test_returned_orientation_children_keep_protection(self):
        program,_=self.seeded('q=get()','ROUTINE get: POSITION BEGIN RETURN p END get'); program.run()
        for name in rt.POSITION_READ_ONLY_FIELDS:
            self.assertTrue(program._state.raw('Q').values[name].read_only)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'): rt.field_reference(program._state.raw('Q').values[name],'X').set(9.)
    def test_direct_orientation_write_in_value_formal_blocked(self):
        with self.assertRaises(TranslationError) as caught: self.seeded('change((p))','ROUTINE change(v: POSITION) BEGIN v.normal.x=9 END change')
        self.assertEqual(caught.exception.code,'E_POSITION_READ_ONLY')
    def test_forwarded_temporary_retains_protection(self):
        program,_=self.seeded('q=outer((p))','ROUTINE inner(v: POSITION): POSITION BEGIN v.location.x=99 RETURN v END inner\nROUTINE outer(v: POSITION): POSITION BEGIN RETURN inner(v) END outer')
        self.assertEqual(program.run()['Q']['LOCATION']['X'],99.); self.assertTrue(program._state.raw('Q').values['NORMAL'].read_only)
    def test_strict_no_source_orientation_default_is_introduced(self):
        program,_=compile_program('q=get()',declarations='p,q: POSITION',routines='ROUTINE get: POSITION BEGIN RETURN p END get', _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual(program._state.local_frames,[])
    def test_strict_uninitialized_position_value_fails_before_callee(self):
        program,_=compile_program('n=0 change((p))',declarations='p: POSITION n: INTEGER',routines='ROUTINE change(v: POSITION) BEGIN n=1 END change', _translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): program.run()
        self.assertEqual(program.snapshot()['N'],0)


class JointRoutineValueTests(unittest.TestCase):
    def test_all_exact_width_results_and_value_arguments(self):
        for width in range(1,10):
            with self.subTest(width=width):
                body=' '.join(f'axes[{i}]={i}' for i in range(1,width+1))+' CNV_REL_JPOS(axes,a,s) b=echo((a)) axes[1]=99 CNV_REL_JPOS(axes,a,s)'
                routine=f'ROUTINE echo(v: JOINTPOS{width}): JOINTPOS{width} BEGIN RETURN v END echo'
                state=execute(body,declarations=f'axes: ARRAY[{width}] OF REAL a,b: JOINTPOS{width} s: INTEGER',routines=routine,joint_axes=width)
                self.assertEqual(state['B'],dict(axes=[float(i) for i in range(1,width+1)])); self.assertEqual(state['A']['axes'][0],99.)
    def test_unsuffixed_nine_matches_explicit_nine(self):
        program,_=compile_program('b=echo((a))',declarations='a: JOINTPOS b: JOINTPOS9',routines='ROUTINE echo(v: JOINTPOS9): JOINTPOS BEGIN RETURN v END echo')
        program._state.raw('A').values[:]=[1.]*9
        self.assertEqual(program.run()['B'],dict(axes=[1.]*9))
    def test_copy_only_needs_no_active_axis_context(self):
        program,_=compile_program('b=echo((a))',declarations='a,b: JOINTPOS3',routines='ROUTINE echo(v: JOINTPOS3): JOINTPOS3 BEGIN RETURN v END echo')
        program._state.raw('A').values[:]=[1.,2.,3.]
        self.assertEqual(program.run()['B'],dict(axes=[1.,2.,3.]))
    def test_copy_does_not_infer_width_from_active_context(self):
        program,_=compile_program('b=echo((a))',declarations='a,b: JOINTPOS3',routines='ROUTINE echo(v: JOINTPOS3): JOINTPOS3 BEGIN RETURN v END echo',joint_axes=1)
        program._state.raw('A').values[:]=[1.,2.,3.]; self.assertEqual(program.run()['B'],dict(axes=[1.,2.,3.]))
    def test_strict_uninitialized_joint_result_preserves_destination(self):
        program,_=compile_program('b=get()',declarations='a,b: JOINTPOS3',routines='ROUTINE get: JOINTPOS3 BEGIN RETURN a END get', _translator=legacy_translate)
        program._state.raw('B').values[:]=[7.,8.,9.]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'initialized axes'): program.run()
        self.assertEqual(program.snapshot()['B'],dict(axes=[7.,8.,9.])); self.assertEqual(program._state.local_frames,[])
    def test_existing_conversion_still_requires_explicit_context(self):
        routine='ROUTINE get: JOINTPOS3 VAR axes: ARRAY[3] OF REAL j: JOINTPOS3 s: INTEGER BEGIN axes[1]=1 axes[2]=2 axes[3]=3 CNV_REL_JPOS(axes,j,s) RETURN j END get'
        program,_=compile_program('a=get()',declarations='a: JOINTPOS3',routines=routine)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'explicit Program'): program.run()


class PositionalRoutineGuardTests(unittest.TestCase):
    def reject(self,code,body='',**kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**kwargs)
        self.assertEqual(caught.exception.code,code,str(caught.exception))
    def test_cross_cartesian_return_is_pythonic_with_legacy_guard(self):
        state=execute(init_pose('ext')+' ext.ext1=7 ext.ext2=8 ext.ext3=9 p=get()',declarations='ext: XYZWPREXT p: XYZWPR',
                      routines='ROUTINE get: XYZWPR BEGIN RETURN ext END get')
        self.assertEqual(state['P']['X'],1.)
        self.assertNotIn('EXT1',state['P'])
        self.reject('E_RETURN',declarations='ext: XYZWPREXT',routines='ROUTINE get: XYZWPR BEGIN RETURN ext END get',_translator=legacy_translate)

    def test_cross_cartesian_value_is_private_with_legacy_guard(self):
        routine='ROUTINE work(v: POSITION) BEGIN v.location.x=99 n=ROUND(v.location.x) END work'
        state=execute(init_pose()+' work((p))',routines=routine)
        self.assertEqual((state['P'],state['N']),(POSE,99))
        self.reject('E_TYPE','work((p))',routines=routine,_translator=legacy_translate)
    def test_cross_width_joint_return_blocked(self): self.reject('E_RETURN',declarations='a: JOINTPOS4',routines='ROUTINE get: JOINTPOS3 BEGIN RETURN a END get')
    def test_cross_width_joint_value_blocked(self): self.reject('E_TYPE','work((a))',declarations='a: JOINTPOS4',routines='ROUTINE work(v: JOINTPOS3) BEGIN END work')
    def test_missing_return_values_blocked(self):
        for kind in NEW_TYPES:
            with self.subTest(kind=kind): self.reject('E_RETURN',routines=f'ROUTINE get: {kind} BEGIN RETURN END get')
    def test_group_qualified_result_blocked(self): self.reject('E_POSITION_GROUP',routines='ROUTINE get: XYZWPR IN GROUP[1] BEGIN END get', _translator=legacy_translate)
    def test_bare_orientation_argument_stays_blocked(self): self.reject('E_POSITION_READ_ONLY_ARG','work(pose.normal)',declarations='pose: POSITION',routines='ROUTINE work(v: VECTOR) BEGIN END work')
    def test_position_geometry_stays_blocked(self): self.reject('E_TYPE','flag=p=q',declarations='p,q: POSITION flag: BOOLEAN')
    def test_named_array_result_and_whole_array_value_stay_blocked(self):
        self.reject('E_RETURN_TYPE',prefix='TYPE row_t=ARRAY[2] OF REAL',routines='ROUTINE get: row_t BEGIN END get', _translator=legacy_translate)
        self.reject('E_ARRAY_VALUE','work((a))',declarations='a: ARRAY[2] OF XYZWPR',routines='ROUTINE work(v: ARRAY OF XYZWPR) BEGIN END work', _translator=legacy_translate)
    def test_multiple_arguments_containing_result_call_stay_blocked(self): self.reject('E_EVALUATION_ORDER','work(make(),p)',routines=POSE_FACTORY+'\nROUTINE work(v,w: XYZWPR) BEGIN END work', _translator=legacy_translate)
    def test_effectful_indexed_result_stays_blocked(self): self.reject('E_EVALUATION_ORDER','items[1]=get()',declarations='p: XYZWPR items: ARRAY[1] OF XYZWPR n: INTEGER',routines='ROUTINE get: XYZWPR BEGIN n=7 RETURN p END get', _translator=legacy_translate)
    def test_delay_output_abort_effects_stay_transitive(self):
        for effect in ('DELAY 0',"WRITE('pose')",'IF FALSE THEN ABORT ENDIF'):
            with self.subTest(effect=effect): self.reject('E_EVALUATION_ORDER','items[1]=outer()',declarations='p: XYZWPR items: ARRAY[1] OF XYZWPR',routines=f'ROUTINE inner: XYZWPR BEGIN {effect} RETURN p END inner\nROUTINE outer: XYZWPR BEGIN RETURN inner() END outer', _translator=legacy_translate)
    def test_fallthrough_and_frame_cleanup(self):
        program,_=compile_program('q=get()',routines='ROUTINE get: XYZWPR BEGIN END get')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'without RETURN'): program.run()
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_strict_uninitialized_copy_before_callee_effects(self):
        for kind in NEW_TYPES:
            with self.subTest(kind=kind):
                program,_=compile_program('n=0 work((a))',declarations=f'a: {kind} n: INTEGER',routines=f'ROUTINE work(v: {kind}) BEGIN n=1 END work', _translator=legacy_translate)
                with self.assertRaises(rt.KarelRuntimeError): program.run()
                self.assertEqual(program.snapshot()['N'],0); self.assertEqual(program._state.call_depth,0)
    def test_bad_config_value_before_destination_mutation(self):
        program,_=compile_program(init_config('d')+' d=get()',routines='ROUTINE get: CONFIG BEGIN RETURN c END get')
        rt.replace_value(program._state.raw('C'),initialized_host(('CONFIG',))); program._state.raw('C').values['CFG_TURN_NO1']=8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): program.run()
        self.assertEqual(program.snapshot()['D'],CONFIG)
    def test_recursive_depth_guard_and_cleanup(self):
        program,_=compile_program('q=get()',routines='ROUTINE get: XYZWPR BEGIN RETURN get() END get')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'depth'): program.run()
        self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))
    def test_abort_unwinds_and_retains_prior_effect(self):
        program,_=compile_program('q=get()',routines='ROUTINE get: XYZWPR BEGIN n=7 ABORT RETURN p END get')
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual(program.snapshot()['N'],7); self.assertEqual((program._state.local_frames,program._state.call_depth),([],0))


class PositionalValueRuntimeTests(unittest.TestCase):
    def test_every_supported_record_returns_fresh_storage(self):
        for name in ('CONFIG','XYZWPR','XYZWPREXT','POSITION'):
            with self.subTest(name=name):
                value=initialized_host((name,)); copied=rt.positional_value((name,),value,17)
                self.assertIsNot(value,copied); self.assertEqual(rt.snapshot_value(value),rt.snapshot_value(copied))
    def test_wrong_type_and_field_shape_rejected(self):
        for expected,value in ((('XYZWPR',),initialized_host(('XYZWPREXT',))),(('CONFIG',),initialized_host(('XYZWPR',)))):
            with self.subTest(expected=expected),self.assertRaises(rt.KarelRuntimeError): rt.positional_value(expected,value,17)
        value=initialized_host(('XYZWPR',)); value.values.pop('R')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'nominal'): rt.positional_value(('XYZWPR',),value,17)
    def test_invalid_real_and_config_contents_rejected(self):
        value=initialized_host(('XYZWPR',)); value.values['X']=0.1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'rounding'): rt.positional_value(('XYZWPR',),value,17)
        value=initialized_host(('CONFIG',)); value.values['CFG_FLIP']=1
        with self.assertRaisesRegex(rt.KarelRuntimeError,'BOOLEAN'): rt.positional_value(('CONFIG',),value,17)
    def test_invalid_joint_axis_count_and_contents_rejected(self):
        value=initialized_host(('JOINTPOS',3)); value.values.pop()
        with self.assertRaises(rt.KarelRuntimeError): rt.positional_value(('JOINTPOS',3),value,17)
        for axis in (True,float('nan'),0.1,rt.UNINITIALIZED):
            value=initialized_host(('JOINTPOS',3)); value.values[1]=axis
            with self.subTest(axis=axis),self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'): rt.positional_value(('JOINTPOS',3),value,17)
    def test_value_reference_is_independent_and_writable(self):
        value=initialized_host(('XYZWPR',)); reference=rt.value_argument(('XYZWPR',),value,17)
        rt.field_reference(reference.raw(),'X',17).set(9.,17)
        self.assertEqual(value.values['X'],1.); self.assertEqual(reference.raw().values['X'],9.)
    def test_unsupported_value_root_rejected(self):
        with self.assertRaises(rt.KarelRuntimeError): rt.positional_value(('VECTOR',),initialized_host(('VECTOR',)),17)


class PositionalRoutineEvidenceTests(unittest.TestCase):
    def test_reports_and_passing_modes(self):
        _,result=compile_program('q=echo((p))',routines='ROUTINE echo(v: XYZWPR): XYZWPR BEGIN RETURN v END echo')
        self.assertEqual(len(result.report['positional_returns']),1); self.assertEqual(len(result.report['positional_value_arguments']),1)
        self.assertEqual(result.report['positional_returns'][0]['type_spec'],('XYZWPR',))
        self.assertEqual(result.report['routine_effects']['ECHO']['parameters'][0]['passing_modes'],['reference','value'])
        self.assertFalse(result.report['positional_routine_policy']['controller_validated'])
    def test_labelled_and_structured_callers_agree(self):
        states=[]
        for labelled in (False,True):
            program,_=compile_program('q=make()',routines=POSE_FACTORY,labelled=labelled); states.append((program.run(),program._state.steps))
        self.assertEqual(states[0],states[1])


if __name__=='__main__': unittest.main()
