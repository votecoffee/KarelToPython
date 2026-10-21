"""Pythonic Cartesian construction, independent CONFIG values and retained bounds."""
import json
import math
from pathlib import Path
import unittest

from karel2py import translate, runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


FIELDS=('X','Y','Z','W','P','R')
CONFIG=dict(CFG_TURN_NO1=0,CFG_TURN_NO2=-1,CFG_TURN_NO3=2,
            CFG_FLIP=False,CFG_LEFT=True,CFG_UP=False,CFG_FRONT=True)
DECLARATIONS='cfg,other: CONFIG pose,copy: XYZWPR x,y,z,w,p,r: REAL i,total: INTEGER trace: STRING[12]'


def initialize(name='cfg'):
    return ' '.join(f'{name}.{field}='+('ON' if value else 'OFF') if type(value) is bool
                    else f'{name}.{field}={value}' for field,value in CONFIG.items())


def pose(*values, config=None): return dict(zip(FIELDS,values),CONFIG_DATA=dict(CONFIG if config is None else config))


def compile_program(body,*,declarations=DECLARATIONS,prefix='',routines='',translator=translate,labelled=False):
    source=f'PROGRAM T\n{prefix}\nVAR {declarations}\n{routines}\nBEGIN\n'
    result=translator(source+('marker::\n' if labelled else '')+body+'\nEND T',filename='pos.kl')
    namespace={'__name__':'pos_test'}; exec(result.python_source,namespace)
    return namespace['Program'](),result


def execute(body,**options):
    p,_=compile_program(initialize()+' '+body,**options)
    return p.run()


def runtime_config():
    cfg=rt.Structure(('CONFIG',)); cfg.values.update(CONFIG)
    return cfg


class PosValueTests(unittest.TestCase):
    def test_all_components_and_config(self): self.assertEqual(execute('pose=POS(1,-2,.25,10,-45,30,cfg)')['POSE'],pose(1,-2,.25,10,-45,30))
    def test_nonexact_pythonic_values(self): self.assertEqual(execute('pose=POS(.1,.2,.3,1.1,2.2,3.3,cfg)')['POSE'],pose(.1,.2,.3,1.1,2.2,3.3))
    def test_integer_promotion(self):
        value=execute('pose=POS(1,2,3,4,5,6,cfg)')['POSE']
        self.assertTrue(all(type(value[field]) is float for field in FIELDS))
    def test_narrow_coordinate_values(self):
        state=execute('a[1]=25 b[1]=-12 pose=POS(a[1],b[1],0,0,0,0,cfg)',declarations=DECLARATIONS+' a: ARRAY[1] OF BYTE b: ARRAY[1] OF SHORT')
        self.assertEqual(state['POSE'],pose(25,-12,0,0,0,0))
    def test_inclusive_coordinate_and_angle_bounds(self):
        self.assertEqual(execute('pose=POS(-10000000,10000000,0,-180,180,0,cfg)')['POSE'],pose(-10000000,10000000,0,-180,180,0))
    def test_config_source_copy_is_independent(self):
        state=execute('pose=POS(1,2,3,4,5,6,cfg) cfg.cfg_turn_no2=4 cfg.cfg_flip=ON')
        self.assertEqual(state['POSE']['CONFIG_DATA'],CONFIG)
    def test_config_destination_copy_is_independent(self):
        state=execute('pose=POS(1,2,3,4,5,6,cfg) pose.config_data.cfg_flip=ON')
        self.assertFalse(state['CFG']['CFG_FLIP'])
    def test_each_result_is_independent(self):
        state=execute('pose=POS(1,2,3,4,5,6,cfg) copy=POS(1,2,3,4,5,6,cfg) pose.config_data.cfg_flip=ON pose.x=9')
        self.assertEqual(state['COPY'],pose(1,2,3,4,5,6))
    def test_alias_types(self):
        state=execute('value=POS(1,2,3,4,5,6,cfg)',prefix='TYPE cart_t=XYZWPR config_t=CONFIG',declarations='cfg: config_t value: cart_t')
        self.assertEqual(state['VALUE'],pose(1,2,3,4,5,6))
    def test_array_and_structure_storage(self):
        state=execute('items[1]=POS(1,2,3,4,5,6,cfg) box.value=POS(6,5,4,3,2,1,cfg)',
                      prefix='TYPE packet=STRUCTURE value: XYZWPR ENDSTRUCTURE',declarations=DECLARATIONS+' items: ARRAY[1] OF XYZWPR box: packet')
        self.assertEqual((state['ITEMS'],state['BOX']),([pose(1,2,3,4,5,6)],{'VALUE':pose(6,5,4,3,2,1)}))
    def test_constructor_field_access(self): self.assertEqual(execute('x=POS(1,2,3,4,5,6,cfg).y')['X'],2)
    def test_constructor_config_field_access(self): self.assertEqual(execute('total=POS(1,2,3,4,5,6,cfg).config_data.cfg_turn_no2')['TOTAL'],-1)
    def test_constructor_function_return(self):
        self.assertEqual(execute('pose=build',routines='ROUTINE build: XYZWPR BEGIN RETURN POS(1,2,3,4,5,6,cfg) END build')['POSE'],pose(1,2,3,4,5,6))
    def test_constructor_value_argument_is_writable_copy(self):
        state=execute('change(POS(1,2,3,4,5,6,cfg))',routines='ROUTINE change(v: XYZWPR) BEGIN v.x=9 v.config_data.cfg_flip=ON pose=v END change')
        self.assertEqual(state['POSE']['X'],9); self.assertFalse(state['CFG']['CFG_FLIP'])
    def test_constructor_field_value_argument(self):
        self.assertEqual(execute('change(POS(1,2,3,4,5,6,cfg).x)',routines='ROUTINE change(v: REAL) BEGIN v=9 x=v END change')['X'],9)
    def test_config_function_result(self):
        self.assertEqual(execute('pose=POS(1,2,3,4,5,6,config_value)',routines='ROUTINE config_value: CONFIG BEGIN RETURN cfg END config_value')['POSE'],pose(1,2,3,4,5,6))
    def test_using_config_field(self):
        body=initialize('box.cdata')+' USING box DO value=POS(1,2,3,4,5,6,cdata) ENDUSING'
        self.assertEqual(execute(body,prefix='TYPE packet=STRUCTURE cdata: CONFIG value: XYZWPR ENDSTRUCTURE',declarations=DECLARATIONS+' box: packet')['BOX']['VALUE'],pose(1,2,3,4,5,6))
    def test_label_dispatcher(self): self.assertEqual(execute('pose=POS(1,2,3,4,5,6,cfg)',labelled=True)['POSE'],pose(1,2,3,4,5,6))
    def test_for_body(self): self.assertEqual(execute('FOR i=1 TO 2 DO pose=POS(i,0,0,0,0,0,cfg) ENDFOR')['POSE'],pose(2,0,0,0,0,0))
    def test_unpos_roundtrip(self):
        state=execute('pose=POS(1,-2,.25,10,-45,30,cfg) UNPOS(pose,x,y,z,w,p,r,other)')
        self.assertEqual(tuple(state[field] for field in FIELDS),(1,-2,.25,10,-45,30)); self.assertEqual(state['OTHER'],CONFIG)
    def test_replacement_preserves_existing_field_reference(self):
        state=execute('pose=POS(1,2,3,4,5,6,cfg) replace(pose,pose.x)',routines='ROUTINE replace(v: XYZWPR; a: REAL) BEGIN v=POS(6,5,4,3,2,1,cfg) a=9 END replace')
        self.assertEqual(state['POSE'],pose(9,5,4,3,2,1))


class PosEffectTests(unittest.TestCase):
    def test_argument_evaluation_order_and_single_evaluation(self):
        routines='''ROUTINE mark(n: INTEGER): REAL BEGIN trace=trace+CHR(64+n) RETURN n END mark
ROUTINE last: CONFIG BEGIN trace=trace+'G' RETURN cfg END last'''
        state=execute("trace='' pose=POS(mark(1),mark(2),mark(3),mark(4),mark(5),mark(6),last)",routines=routines)
        self.assertEqual((state['TRACE'],state['POSE']),('ABCDEFG',pose(1,2,3,4,5,6)))
    def test_numeric_values_capture_before_later_mutation(self):
        state=execute('x=1 pose=POS(x,touch,0,0,0,0,cfg)',routines='ROUTINE touch: REAL BEGIN x=9 RETURN 2 END touch')
        self.assertEqual(state['POSE'],pose(1,2,0,0,0,0))
    def test_final_config_reads_after_coordinate_effects(self):
        state=execute('pose=POS(touch,0,0,0,0,0,cfg)',routines='ROUTINE touch: REAL BEGIN cfg.cfg_flip=ON RETURN 1 END touch')
        self.assertTrue(state['POSE']['CONFIG_DATA']['CFG_FLIP'])
    def test_expression_failure_skips_later_argument_effects(self):
        p,_=compile_program(initialize()+" total=0 pose=POS(1 DIV 0,touch,0,0,0,0,cfg)",routines='ROUTINE touch: REAL BEGIN total=9 RETURN 2 END touch')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['TOTAL'],0)
    def test_constructor_range_check_follows_argument_evaluation(self):
        p,_=compile_program(initialize()+' total=0 pose=POS(10000001,0,0,0,0,0,last)',routines='ROUTINE last: CONFIG BEGIN total=9 RETURN cfg END last')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'POS X'): p.run()
        self.assertEqual(p.snapshot()['TOTAL'],9)
    def test_failure_leaves_destination_intact(self):
        p,_=compile_program(initialize()+' pose=POS(1,2,3,4,5,6,cfg) pose=POS(1,2,3,4,5,181,cfg)')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['POSE'],pose(1,2,3,4,5,6))
    def test_constructor_failure_unwinds_for_and_routine(self):
        p,_=compile_program(initialize()+' FOR i=1 TO 2 DO build() ENDFOR',routines='ROUTINE build BEGIN pose=POS(0,0,0,181,0,0,cfg) END build')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual(p.snapshot()['I'],{'uninitialized':True})
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
    def test_coordinate_call_effects_protect_for_counter(self):
        with self.assertRaises(TranslationError) as caught:
            compile_program('FOR i=1 TO 2 DO pose=POS(touch,0,0,0,0,0,cfg) ENDFOR',routines='ROUTINE touch: REAL BEGIN i=9 RETURN 1 END touch')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')
    def test_constructor_rhs_precedes_assignment_target_effect(self):
        state=execute('items[target]=POS(1,2,3,4,5,6,cfg)',declarations=DECLARATIONS+' items: ARRAY[1] OF XYZWPR',
                      routines='ROUTINE target: INTEGER BEGIN cfg.cfg_flip=ON RETURN 1 END target')
        self.assertFalse(state['ITEMS'][0]['CONFIG_DATA']['CFG_FLIP']); self.assertTrue(state['CFG']['CFG_FLIP'])


class PosGuardAndNameTests(unittest.TestCase):
    def reject(self,body,code,**options):
        with self.assertRaises(TranslationError) as caught: compile_program(body,**options)
        self.assertEqual(caught.exception.code,code)
    def test_wrong_arity(self):
        for arguments in ('','1,2,3','1,2,3,4,5,6,cfg,8'):
            with self.subTest(arguments=arguments): self.reject(f'pose=POS({arguments})','E_ARGUMENTS')
    def test_wrong_numeric_type(self): self.reject('pose=POS(ON,2,3,4,5,6,cfg)','E_TYPE')
    def test_wrong_config_type(self): self.reject('pose=POS(1,2,3,4,5,6,1)','E_TYPE')
    def test_no_implicit_position_coercion(self): self.reject('value=POS(1,2,3,4,5,6,cfg)','E_TYPE',declarations=DECLARATIONS+' value: POSITION')
    def test_no_implicit_extended_pose_coercion(self): self.reject('value=POS(1,2,3,4,5,6,cfg)','E_TYPE',declarations=DECLARATIONS+' value: XYZWPREXT')
    def test_orientation_protection_retained(self): self.reject('value.normal=POS(1,2,3,4,5,6,cfg)','E_POSITION_READ_ONLY',declarations=DECLARATIONS+' value: POSITION')
    def test_coordinate_and_angle_domains(self):
        for index in range(6):
            values=['0']*6; values[index]='10000001' if index<3 else '181'
            for sign in ('','-'):
                args=values.copy(); args[index]=sign+args[index]
                p,_=compile_program(initialize()+' pose=POS('+','.join(args)+',cfg)')
                with self.subTest(index=index,sign=sign),self.assertRaisesRegex(rt.KarelRuntimeError,'POS '+FIELDS[index]): p.run()
    def test_uninitialized_config(self):
        p,_=compile_program('pose=POS(1,2,3,4,5,6,cfg)')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
    def test_partly_initialized_config(self):
        p,_=compile_program('cfg.cfg_turn_no1=0 pose=POS(1,2,3,4,5,6,cfg)')
        with self.assertRaises(rt.KarelRuntimeError): p.run()
    def test_user_routine_precedes_constructor(self):
        self.assertEqual(execute('total=POS(4)',routines='ROUTINE POS(n: INTEGER): INTEGER BEGIN RETURN n+1 END POS')['TOTAL'],5)
    def test_user_routine_signature_stays_checked(self): self.reject('total=POS(1,2,3)','E_ARGUMENTS',routines='ROUTINE POS(n: INTEGER): INTEGER BEGIN RETURN n END POS')
    def test_ordinary_pos_variable_is_preserved(self): self.assertEqual(execute('pos=7 pose=POS(pos,0,0,0,0,0,cfg)',declarations=DECLARATIONS+' pos: INTEGER')['POSE'],pose(7,0,0,0,0,0))
    def test_legacy_constructor_rejection(self): self.reject('pose=POS(1,2,3,4,5,6,cfg)','E_CALL',translator=legacy_translate)
    def test_legacy_user_routine_preserved(self): self.assertEqual(execute('total=POS(4)',routines='ROUTINE POS(n: INTEGER): INTEGER BEGIN RETURN n END POS',translator=legacy_translate)['TOTAL'],4)
    def test_report_tracks_constructor_sites(self):
        _,result=compile_program(initialize()+' pose=POS(1,2,3,4,5,6,cfg)')
        report=json.loads(json.dumps(result.report)); site=report['pos_constructors'][0]
        self.assertEqual(site['argument_order'],['x','y','z','w','p','r','c'])
        self.assertEqual(site['result_type'],'XYZWPR'); self.assertTrue(site['configuration_copied'])
        self.assertFalse(report['pos_policy']['controller_validated'])
    def test_user_routine_has_no_constructor_site(self):
        _,result=compile_program('total=POS(4)',routines='ROUTINE POS(n: INTEGER): INTEGER BEGIN RETURN n END POS')
        self.assertEqual(result.report['pos_constructors'],[])


class PosRuntimeTests(unittest.TestCase):
    def test_arity_guard(self):
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'seven arguments'): rt.builtin('POS',[1,2,3],17)
    def test_bad_numeric_data(self):
        for value in (True,'1',math.nan,math.inf,rt.UNINITIALIZED,rt.UNKNOWN_BYTE):
            with self.subTest(value=value),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'):
                rt.builtin('POS',[value,0,0,0,0,0,runtime_config()],17)
    def test_bad_config_shape(self):
        for change in ('missing','extra','type','spec'):
            cfg=runtime_config()
            if change=='missing': del cfg.values['CFG_FLIP']
            elif change=='extra': cfg.values['EXTRA']=1
            elif change=='type': cfg.types['CFG_FLIP']=('INTEGER',)
            else: cfg.spec=('XYZWPR',)
            with self.subTest(change=change),rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'line 17'):
                rt.builtin('POS',[0,0,0,0,0,0,cfg],17)
    def test_bad_config_contents(self):
        for field,value in [('CFG_TURN_NO1',8),('CFG_TURN_NO2',-9),('CFG_TURN_NO3',True),('CFG_FLIP',1),('CFG_FRONT',rt.UNINITIALIZED)]:
            cfg=runtime_config(); cfg.values[field]=value
            with self.subTest(field=field),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.builtin('POS',[0,0,0,0,0,0,cfg])
    def test_config_shape_and_contents_are_unchanged_after_failure(self):
        cfg=runtime_config(); before=rt.snapshot_value(cfg)
        with rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError): rt.builtin('POS',[0,0,0,181,0,0,cfg])
        self.assertEqual(rt.snapshot_value(cfg),before)
    def test_config_and_result_objects_are_detached(self):
        cfg=runtime_config()
        with rt._numeric_scope('pythonic'): result=rt.builtin('POS',[1,2,3,4,5,6,cfg])
        self.assertIsNot(result.values['CONFIG_DATA'],cfg)
        cfg.values['CFG_FLIP']=True; self.assertFalse(result.values['CONFIG_DATA'].values['CFG_FLIP'])
    def test_strict_runtime_guard(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError): rt.builtin('POS',[1,2,3,4,5,6,runtime_config()],17)


class AuthoredPosTests(unittest.TestCase):
    def test_complete_fixture_and_source_reports(self):
        source=Path(__file__).resolve().parents[1]/'examples/pythonic_pos.kl'
        result=translate(source.read_text(),filename=source.name); namespace={'__name__':'pos_fixture'}
        exec(result.python_source,namespace); output=[]; p=namespace['Program'](write=output.append)
        self.assertEqual(p.run(),json.loads(source.with_suffix('.expected.json').read_text()))
        self.assertEqual(output,json.loads(source.with_suffix('.write.expected.json').read_text()))
        self.assertEqual(len(result.report['pos_constructors']),2)
        self.assertEqual((p._state.local_frames,p._state.call_depth),([],0))
