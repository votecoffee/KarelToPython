"""Built-in record XML roots retain typed storage and protected descendants."""
import json
import unittest

from karel2py import runtime as rt,translate_project
from karel2py.kinematics import pose as identity_pose
from tests.test_extended_services import compile_program
from tests.test_project_scheduler import source
from tests.test_xml_input import OPEN,ADD,SCAN,context


DECL='value:{kind} f:FILE s,ident,code:INTEGER tag:STRING[32]'
CALL="XML_SETVAR(f,'','value',s)"
MISSING={'uninitialized':True}


def build(xml,kind='VECTOR',body=CALL,*,labelled=False,cooperative=False):
    return compile_program(OPEN+ADD+SCAN+('apply:: ' if labelled else '')+body,
        decl=DECL.format(kind=kind),context=context(xml),cooperative=cooperative)[0]


class XMLRecordRootTests(unittest.TestCase):
    def test_vector_root_accepts_direct_scalar_attributes(self):
        state=build('<item x="1" y="2.5" z="-3"/>').run()
        self.assertEqual((state['VALUE'],state['S']),({'X':1.,'Y':2.5,'Z':-3.},0))

    def test_config_root_accepts_bounded_turns_and_boolean_flags(self):
        state=build('<item cfg_turn_no1="-8" cfg_turn_no2="7" cfg_flip="on"/>','CONFIG').run()
        self.assertEqual((state['VALUE']['CFG_TURN_NO1'],state['VALUE']['CFG_TURN_NO2'],state['VALUE']['CFG_FLIP'],state['S']),(-8,7,True,0))

    def test_plain_and_extended_pose_root_fields(self):
        for kind,attrs in (('XYZWPR','x="1" w="90"'),('XYZWPREXT','x="2" ext1="10" ext2="20" ext3="30"')):
            state=build('<item '+attrs+'/>',kind).run()
            with self.subTest(kind=kind):self.assertEqual(state['S'],0);self.assertEqual(state['VALUE']['X'],1. if kind=='XYZWPR' else 2.)
            self.assertEqual(state['VALUE']['CONFIG_DATA']['CFG_FLIP'],MISSING)

    def test_nested_pose_config_fields_follow_original_turn_bounds(self):
        state=build('<item x="1" config_data.cfg_turn_no1="7"/>','XYZWPR').run()
        self.assertEqual((state['VALUE']['X'],state['VALUE']['CONFIG_DATA']['CFG_TURN_NO1'],state['S']),(1.,7,0))

    def test_position_location_can_change_without_changing_orientation(self):
        p=build('<item location.x="12" location.y="-3"/>','POSITION');point=identity_pose()
        p._state.values['VALUE']=point;before=p.snapshot()['VALUE'];state=p.run()['VALUE']
        self.assertEqual((state['LOCATION']['X'],state['LOCATION']['Y']),(12.,-3.))
        for field in ('NORMAL','ORIENT','APPROACH','CONFIG_DATA'):self.assertEqual(state[field],before[field])

    def test_uninitialized_position_can_receive_location_without_orientation_defaults(self):
        state=build('<item location.x="12"/>','POSITION').run()['VALUE']
        self.assertEqual(state['LOCATION']['X'],12.);self.assertEqual(state['NORMAL']['X'],MISSING)

    def test_position_orientation_updates_fail_atomically(self):
        for field in ('normal.x','orient.y','approach.z'):
            p=build('<item location.x="99" '+field+'="1"/>','POSITION');p._state.values['VALUE']=identity_pose()
            before=p.snapshot()['VALUE']
            with self.subTest(field=field):self.assertEqual(p.run()['S'],2);self.assertEqual(p.snapshot()['VALUE'],before)

    def test_direct_readonly_vector_roots_are_rejected_before_staging(self):
        for field in ('normal','orient','approach'):
            p=build('<item x="99"/>','POSITION',"XML_SETVAR(f,'','value."+field+"',s)")
            p._state.values['VALUE']=identity_pose();before=p.snapshot()['VALUE']
            with self.subTest(field=field):self.assertEqual(p.run()['S'],2);self.assertEqual(p.snapshot()['VALUE'],before)

    def test_config_overflow_rejects_earlier_field_updates(self):
        p=build('<item cfg_flip="true" cfg_turn_no1="8"/>','CONFIG');before=p.snapshot()['VALUE']
        self.assertEqual(p.run()['S'],2);self.assertEqual(p.snapshot()['VALUE'],before)

    def test_unknown_field_or_nonfinite_later_value_prevents_publication(self):
        for attrs in ('x="1" bad="2"','x="1" y="NaN"','x="1" z="Infinity"'):
            p=build('<item '+attrs+'/>');before=p.snapshot()['VALUE']
            with self.subTest(attrs=attrs):self.assertEqual(p.run()['S'],2);self.assertEqual(p.snapshot()['VALUE'],before)

    def test_case_folded_duplicate_leaf_rejects_whole_vector(self):
        p=build('<item x="1" X="2"/>');before=p.snapshot()['VALUE']
        self.assertEqual(p.run()['S'],2);self.assertEqual(p.snapshot()['VALUE'],before)

    def test_exact_builtin_alias_has_same_root_contract(self):
        p,_=compile_program(OPEN+ADD+SCAN+CALL,prefix='TYPE point_t=VECTOR',decl=DECL.format(kind='point_t'),context=context('<item x="42"/>'))
        self.assertEqual((p.run()['VALUE']['X'],p.snapshot()['S']),(42.,0))

    def test_array_element_can_be_selected_as_builtin_root(self):
        body="XML_SETVAR(f,'','value[2]',s)"
        p=build('<item x="42"/>','ARRAY[2] OF VECTOR',body)
        self.assertEqual((p.run()['VALUE'][1]['X'],p.snapshot()['VALUE'][0]['X']),(42.,MISSING))

    def test_user_record_builtin_field_can_be_selected_as_root(self):
        p,_=compile_program(OPEN+ADD+SCAN+"XML_SETVAR(f,'','item.point',s)",prefix='TYPE packet_t=STRUCTURE point:VECTOR ENDSTRUCTURE',
                            decl='item:packet_t f:FILE s,ident,code:INTEGER tag:STRING[32]',context=context('<item x="42"/>'))
        self.assertEqual(p.run()['ITEM']['POINT']['X'],42.)

    def test_explicit_binding_can_be_updated_without_creating_schema(self):
        ctx=context('<item x="42"/>');value=ctx.variables.define('OTHER','POINT',('VECTOR',))
        p,_=compile_program(OPEN+ADD+SCAN+"XML_SETVAR(f,'OTHER','POINT',s)",decl='f:FILE s,ident,code:INTEGER tag:STRING[32]',context=ctx)
        self.assertEqual(p.run()['S'],0);self.assertEqual(value.raw().values['X'],42.)

    def test_scalar_joint_array_and_resource_roots_remain_rejected(self):
        for kind in ('INTEGER','REAL','BOOLEAN','STRING[8]','BYTE','SHORT','JOINTPOS2','ARRAY[1] OF VECTOR','FILE','PATH','QUEUE_TYPE'):
            p=build('<item x="1"/>',kind);before=p.snapshot()['VALUE']
            with self.subTest(kind=kind):self.assertEqual(p.run()['S'],2);self.assertEqual(p.snapshot()['VALUE'],before)

    def test_malformed_known_builtin_value_fails_before_modification(self):
        p=build('<item x="42"/>');p._state.values['VALUE'].values['Y']=float('nan')
        self.assertEqual(p.run()['S'],2);self.assertEqual(p._state.values['VALUE'].values['X'],rt.UNINITIALIZED)

    def test_success_keeps_root_and_child_reference_identities(self):
        p=build('<item location.x="42"/>','POSITION');root=p._state.values['VALUE'];child=root.values['LOCATION'];ref=rt.field_reference(child,'X')
        p.run();self.assertIs(p._state.values['VALUE'],root);self.assertIs(root.values['LOCATION'],child);self.assertEqual(ref.raw(),42.)

    def test_structured_dispatcher_and_cooperative_engines_agree(self):
        for labelled in (False,True):
            for cooperative in (False,True):
                state=build('<item x="42"/>',labelled=labelled,cooperative=cooperative).run()
                with self.subTest(labelled=labelled,cooperative=cooperative):self.assertEqual((state['VALUE']['X'],state['S']),(42.,0))

    def test_pause_retains_pending_event_before_record_update(self):
        p=build('<item x="42"/>',body='PAUSE '+CALL)
        with self.assertRaises(rt.KarelPause):p.run()
        self.assertEqual(p.resume()['VALUE']['X'],42.)

    def test_json_replay_retains_concrete_record_and_xml_input(self):
        p=build('<item x="42"/>',body=CALL+' CLOSE FILE f');p.run()
        saved=json.loads(json.dumps(p._state.execution.to_config()));ctx=rt.ExecutionContext.from_config(saved)
        again,_=compile_program(OPEN+ADD+SCAN+CALL+' CLOSE FILE f',decl=DECL.format(kind='VECTOR'),context=ctx)
        self.assertEqual((again.run()['VALUE']['X'],again.snapshot()['S']),(42.,0))

    def test_linked_library_can_update_callers_builtin_global(self):
        lib=source('LIB','',decl='f:FILE s,ident,code:INTEGER tag:STRING[32]',routines='ROUTINE update BEGIN '+OPEN+ADD+SCAN+"XML_SETVAR(f,'MAIN','point',s) CLOSE FILE f END update")
        main=source('MAIN','update()',decl='point:VECTOR',routines='ROUTINE update FROM LIB')
        project=translate_project({'lib':lib,'main':main}).instantiate(context=context('<item x="42"/>'));project.run('MAIN')
        self.assertEqual(project.programs['MAIN'].snapshot()['POINT']['X'],42.)

    def test_report_lists_builtin_record_roots_and_protection(self):
        _,result=compile_program(CALL,decl=DECL.format(kind='VECTOR'))
        policy=json.loads(json.dumps(result.report))['xml_record_root_policy']
        self.assertIn('VECTOR',policy['targets']);self.assertIn('orientation',policy['writes']);self.assertIn('No scalar',policy['boundary'])


if __name__=='__main__':unittest.main()
