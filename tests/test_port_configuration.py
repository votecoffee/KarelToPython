"""Authored topology, staged I/O settings and logical-value independence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from karel2py import runtime as rt,translate,translate_project
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run
from tests.test_project_scheduler import source as module_source


COUNTS={'DIN':8,'DOUT':8,'GIN':2,'GOUT':2,'AIN':2,'AOUT':2,'RDI':2,'RDO':2,'RDIN':2,'RDOUT':2}
CODES={10:'DIN',20:'DOUT',30:'GIN',40:'GOUT',50:'AIN',60:'AOUT',70:'RDI',80:'RDO',90:'RDIN',100:'RDOUT'}
DECL='rack,slot,code,first,width,mode,modtype,s: INTEGER'
GET='GET_PORT_ASG(20,1,rack,slot,code,first,width,s)'


def topology():
    return {'physical':[
        dict(rack=0,slot=1,type_code=10,kind='DIN',count=64),
        dict(rack=0,slot=1,type_code=20,kind='DOUT',count=64),
        dict(rack=2,slot=3,type_code=50,kind='AIN',count=8),
        dict(rack=2,slot=3,type_code=60,kind='AOUT',count=8)],
        'modules':[dict(rack=0,slot=1,type=7)],
        'assignments':[dict(kind='DOUT',number=1,rack=0,slot=1,type_code=20,start=9,count=1)]}


def context(config=None,**options):
    return rt.ExecutionContext(ports=rt.PortBank(COUNTS,type_codes=CODES,configuration=topology() if config is None else config,**options))


class PortAssignmentTests(unittest.TestCase):
    def test_read_supplied_assignment(self):
        state=run(GET,decl=DECL,context=context())
        self.assertEqual([state[key] for key in ('RACK','SLOT','CODE','FIRST','WIDTH','S')],[0,1,20,9,1,0])

    def test_missing_assignment_preserves_all_outputs(self):
        state=run('rack=8 slot=8 code=8 first=8 width=8 '+GET.replace('20,1','20,2'),decl=DECL,context=context())
        self.assertEqual([state[key] for key in ('RACK','SLOT','CODE','FIRST','WIDTH','S')],[8,8,8,8,8,1])

    def test_invalid_logical_addresses_preserve_outputs(self):
        for code,number in ((999,1),(20,0),(20,9),(20,-1)):
            with self.subTest(code=code,number=number):
                state=run(f'first=8 GET_PORT_ASG({code},{number},rack,slot,code,first,width,s)',decl=DECL,context=context())
                self.assertEqual((state['FIRST'],state['S']),(8,2))

    def test_setting_assignment_is_staged_until_host_applies(self):
        ctx=context();state=run('SET_PORT_ASG(20,1,0,1,20,17,1,s) '+GET,decl=DECL,context=ctx)
        self.assertEqual((state['FIRST'],state['S']),(9,0))
        self.assertEqual(ctx.ports.configuration['pending_assignments'][0]['start'],17)
        self.assertEqual(ctx.ports.apply_configuration(),1)
        self.assertEqual(run(GET,decl=DECL,context=ctx)['FIRST'],17)
        self.assertNotIn('pending_assignments',ctx.ports.configuration)
        self.assertEqual(ctx.ports.apply_configuration(),0)

    def test_digital_batch_expands_individual_points(self):
        ctx=context();self.assertEqual(run('SET_PORT_ASG(20,1,0,1,20,17,8,s)',context=ctx)['S'],0)
        self.assertEqual(ctx.ports.apply_configuration(),8)
        state=run(GET.replace('20,1','20,8'),decl=DECL,context=ctx)
        self.assertEqual((state['FIRST'],state['WIDTH']),(24,1))

    def test_group_assignment_retains_bit_width(self):
        ctx=context();run('SET_PORT_ASG(40,2,0,1,20,16,32,s)',context=ctx);ctx.ports.apply_configuration()
        state=run(GET.replace('20,1','40,2'),decl=DECL,context=ctx)
        self.assertEqual((state['CODE'],state['FIRST'],state['WIDTH'],state['S']),(20,16,32,0))

    def test_analog_single_point_assignment(self):
        ctx=context();run('SET_PORT_ASG(60,2,2,3,60,8,1,s)',context=ctx);ctx.ports.apply_configuration()
        state=run(GET.replace('20,1','60,2'),decl=DECL,context=ctx)
        self.assertEqual((state['RACK'],state['SLOT'],state['FIRST'],state['WIDTH']),(2,3,8,1))

    def test_robot_input_and_output_alias_kinds_use_direction_family(self):
        for code,physical in ((70,10),(80,20),(90,10),(100,20)):
            with self.subTest(code=code):
                ctx=context();self.assertEqual(run(f'SET_PORT_ASG({code},1,0,1,{physical},2,2,s)',context=ctx)['S'],0)
                ctx.ports.apply_configuration()
                state=run(GET.replace('20,1',f'{code},2'),decl=DECL,context=ctx)
                self.assertEqual((state['FIRST'],state['WIDTH'],state['S']),(3,1,0))

    def test_explicit_dummy_code_can_differ_from_logical_code(self):
        config=topology();config['physical'].append(dict(rack=0,slot=0,type_code=901,kind='DOUT',count=64))
        ctx=context(config);run('SET_PORT_ASG(20,1,0,0,901,60,1,s)',context=ctx);ctx.ports.apply_configuration()
        state=run(GET,decl=DECL,context=ctx)
        self.assertEqual((state['CODE'],state['FIRST'],state['S']),(901,60,0))

    def test_invalid_topology_and_ranges_keep_pending_batch(self):
        for kind,number,rack,slot,code,start,count in (
                (20,1,-1,1,20,1,1),(20,1,0,2,20,1,1),(20,1,0,1,99,1,1),
                (20,1,0,1,10,1,1),(30,1,0,1,20,1,8),(20,1,0,1,20,0,1),
                (20,1,0,1,20,64,2),(20,8,0,1,20,1,2),(20,1,0,1,20,1,9),
                (20,1,0,1,20,1,0),(40,1,0,1,20,1,33),(60,1,2,3,60,1,2)):
            with self.subTest(arguments=(kind,number,rack,slot,code,start,count)):
                ctx=context();run('SET_PORT_ASG(20,1,0,1,20,17,1,s)',context=ctx);before=ctx.ports.configuration
                state=run(f'SET_PORT_ASG({kind},{number},{rack},{slot},{code},{start},{count},s)',context=ctx)
                self.assertEqual(state['S'],3);self.assertEqual(ctx.ports.configuration,before)

    def test_later_valid_batch_overwrites_only_selected_pending_points(self):
        ctx=context();run('SET_PORT_ASG(20,1,0,1,20,1,8,s) SET_PORT_ASG(20,3,0,1,20,40,2,s)',context=ctx)
        ctx.ports.apply_configuration();rows=ctx.ports.configuration['assignments']
        self.assertEqual([row['start'] for row in rows],[1,2,40,41,5,6,7,8])

    def test_metadata_does_not_initialize_or_remove_logical_values(self):
        ctx=context(initial={('DOUT',1):True},comments={('DOUT',1):'ready'},simulated=[('DIN',1)])
        before=ctx.ports.snapshot();run('SET_PORT_ASG(20,1,0,1,20,1,8,s)',context=ctx);ctx.ports.apply_configuration()
        self.assertEqual(ctx.ports.snapshot(),before);self.assertEqual(ctx.ports.comments,{('DOUT',1):'ready'})
        self.assertEqual(ctx.ports.simulated,{('DIN',1)})


class PortModeModuleTests(unittest.TestCase):
    def test_unspecified_mode_is_zero(self):
        state=run('GET_PORT_MOD(20,1,mode,s)',decl=DECL,context=context())
        self.assertEqual((state['MODE'],state['S']),(0,0))

    def test_modes_wait_for_host_apply_then_can_be_reset(self):
        ctx=context();state=run('SET_PORT_MOD(20,1,3,s) GET_PORT_MOD(20,1,mode,s)',decl=DECL,context=ctx)
        self.assertEqual(state['MODE'],0);self.assertEqual(ctx.ports.apply_configuration(),1)
        self.assertEqual(run('GET_PORT_MOD(20,1,mode,s)',decl=DECL,context=ctx)['MODE'],3)
        run('SET_PORT_MOD(20,1,0,s)',context=ctx);ctx.ports.apply_configuration()
        self.assertEqual(run('GET_PORT_MOD(20,1,mode,s)',decl=DECL,context=ctx)['MODE'],0)

    def test_invalid_mode_mask_direction_and_pair_leave_pending_unchanged(self):
        for code,number,mask in ((20,1,-1),(20,1,4),(20,2,2),(10,1,2),(40,1,2),(60,1,2),(80,2,2)):
            with self.subTest(arguments=(code,number,mask)):
                ctx=context();before=ctx.ports.configuration
                self.assertEqual(run(f'SET_PORT_MOD({code},{number},{mask},s)',context=ctx)['S'],3)
                self.assertEqual(ctx.ports.configuration,before)

    def test_complementary_last_unpaired_output_is_rejected(self):
        ctx=rt.ExecutionContext(ports=rt.PortBank({'DOUT':3},type_codes={20:'DOUT'},configuration={}))
        self.assertEqual(run('SET_PORT_MOD(20,3,2,s)',context=ctx)['S'],3)

    def test_input_reverse_mode_is_metadata_without_inverting_logical_input(self):
        ctx=context(initial={('DIN',1):True});run('SET_PORT_MOD(10,1,1,s)',context=ctx);ctx.ports.apply_configuration()
        self.assertTrue(run('flag=DIN[1]',decl='flag: BOOLEAN',context=ctx)['FLAG'])

    def test_modes_do_not_drive_complementary_physical_or_logical_ports(self):
        ctx=context(initial={('DOUT',1):False,('DOUT',2):False})
        run('SET_PORT_MOD(20,1,3,s)',context=ctx);ctx.ports.apply_configuration()
        run('DOUT[1]=TRUE',context=ctx)
        self.assertEqual(ctx.ports.snapshot(),{('DOUT',1):True,('DOUT',2):False})

    def test_assignment_and_mode_apply_together(self):
        ctx=context();run('SET_PORT_ASG(20,1,0,1,20,50,1,s) SET_PORT_MOD(20,1,1,s)',context=ctx)
        self.assertEqual(ctx.ports.apply_configuration(),2)
        state=run(GET+' GET_PORT_MOD(20,1,mode,s)',decl=DECL,context=ctx)
        self.assertEqual((state['FIRST'],state['MODE']),(50,1))

    def test_module_type_comes_only_from_explicit_catalog(self):
        state=run('IO_MOD_TYPE(0,1,modtype,s)',decl=DECL,context=context())
        self.assertEqual((state['MODTYPE'],state['S']),(7,0))

    def test_physical_capacity_does_not_invent_module_type(self):
        state=run('modtype=99 IO_MOD_TYPE(2,3,modtype,s)',decl=DECL,context=context())
        self.assertEqual((state['MODTYPE'],state['S']),(99,1))

    def test_module_queries_need_no_logical_type_map(self):
        ctx=rt.ExecutionContext(ports=rt.PortBank({},configuration={'modules':[dict(rack=0,slot=0,type=0)]}))
        state=run('IO_MOD_TYPE(0,0,modtype,s)',decl=DECL,context=ctx)
        self.assertEqual((state['MODTYPE'],state['S']),(0,0))

    def test_module_invalid_coordinate_differs_from_absence(self):
        for rack,slot in ((-1,0),(0,-1),(32768,0),(0,32768)):
            with self.subTest(rack=rack,slot=slot):
                state=run(f'modtype=99 IO_MOD_TYPE({rack},{slot},modtype,s)',decl=DECL,context=context())
                self.assertEqual((state['MODTYPE'],state['S']),(99,2))


class PortConfigurationContractTests(unittest.TestCase):
    def test_missing_service_keeps_status_and_has_source_line(self):
        program,_=compile_program('s=99 SET_PORT_MOD(20,1,1,s)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'ports') as caught: program.run()
        self.assertIsNotNone(caught.exception.line);self.assertEqual(program.snapshot()['S'],99)

    def test_missing_configuration_does_not_create_topology(self):
        ctx=rt.ExecutionContext(ports=rt.PortBank({'DOUT':8},type_codes={20:'DOUT'}))
        program,_=compile_program('s=99 SET_PORT_ASG(20,1,0,1,20,1,1,s)',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'configuration'): program.run()
        self.assertIsNone(ctx.ports.configuration);self.assertEqual(program.snapshot()['S'],99)

    def test_missing_logical_type_map_retains_status(self):
        ctx=rt.ExecutionContext(ports=rt.PortBank({'DOUT':8},configuration={}))
        program,_=compile_program('s=99 SET_PORT_MOD(20,1,1,s)',context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type_codes'): program.run()
        self.assertEqual(program.snapshot()['S'],99)

    def test_empty_explicit_configuration_can_stage_modes(self):
        ctx=context({});self.assertEqual(run('SET_PORT_MOD(20,1,1,s)',context=ctx)['S'],0)
        self.assertEqual(ctx.ports.apply_configuration(),1)

    def test_outputs_must_be_writable_exact_integer(self):
        for body,decl in (('GET_PORT_MOD(20,1,n,s)','n: REAL s: INTEGER'),
                          ('GET_PORT_MOD(20,1,1,s)','s: INTEGER'),
                          ('IO_MOD_TYPE(0,1,n,s)','n: SHORT s: INTEGER'),
                          ('SET_PORT_MOD(20,1,1,s)','s: REAL')):
            with self.subTest(body=body,decl=decl),self.assertRaises(TranslationError): compile_program(body,decl=decl)

    def test_repeated_get_outputs_fail_before_any_write(self):
        ctx=context();program,_=compile_program('rack=99 s=99 '+GET.replace('rack,slot','rack,rack'),decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): program.run()
        self.assertEqual((program.snapshot()['RACK'],program.snapshot()['S']),(99,99))

    def test_value_output_and_status_cannot_alias(self):
        for body in ('GET_PORT_MOD(20,1,s,s)','IO_MOD_TYPE(0,1,s,s)'):
            with self.subTest(body=body):
                program,_=compile_program('s=99 '+body,context=context())
                with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): program.run()
                self.assertEqual(program.snapshot()['S'],99)

    def test_for_control_variable_is_protected(self):
        with self.assertRaises(TranslationError): compile_program('FOR n=1 TO 2 DO GET_PORT_MOD(20,1,n,s) ENDFOR')

    def test_earlier_input_is_captured_before_status_selector_changes_it(self):
        ctx=context();routines='ROUTINE at: INTEGER BEGIN mask=0 RETURN 1 END at'
        state=run('mask=1 SET_PORT_MOD(20,1,mask,codes[at()])',decl='mask: INTEGER codes: ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        self.assertEqual((state['MASK'],state['CODES']),(0,[0]))
        self.assertEqual(ctx.ports.configuration['pending_modes'][0]['mask'],1)

    def test_missing_input_prevents_later_selector_and_mutation(self):
        ctx=context();before=ctx.ports.configuration;routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN 1 END at'
        program,_=compile_program('n=0 SET_PORT_MOD(20,1,mask,codes[at()])',decl='n,mask: INTEGER codes: ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(program.snapshot()['N'],0);self.assertEqual(ctx.ports.configuration,before)

    def test_ordered_selectors_are_evaluated_once(self):
        routines='ROUTINE at: INTEGER BEGIN n=n+1 RETURN n END at'
        state=run('n=0 GET_PORT_ASG(20,1,a[at()],a[at()],a[at()],a[at()],a[at()],a[at()])',decl='n: INTEGER a: ARRAY[6] OF INTEGER',routines=routines,context=context())
        self.assertEqual((state['N'],state['A']),(6,[0,1,20,9,1,0]))

    def test_failed_late_selector_does_not_stage_partial_configuration(self):
        ctx=context();before=ctx.ports.configuration;program,_=compile_program('SET_PORT_ASG(20,1,0,1,20,1,8,a[2])',decl='a: ARRAY[1] OF INTEGER',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): program.run()
        self.assertEqual(ctx.ports.configuration,before)

    def test_budget_failure_preserves_completed_staging(self):
        ctx=context();program,_=compile_program('SET_PORT_MOD(20,1,1,s) WHILE TRUE DO n=1 ENDWHILE',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): program.run(max_steps=30)
        self.assertEqual(ctx.ports.configuration['pending_modes'][0]['mask'],1)
        self.assertEqual(program._state.call_depth,0);self.assertEqual(program._state.local_frames,[])

    def test_linked_routine_uses_shared_context(self):
        main=module_source('MAIN','configure(s)',decl='s: INTEGER',routines='ROUTINE configure(s: INTEGER) FROM LIB')
        library=module_source('LIB','',routines='ROUTINE configure(s: INTEGER) BEGIN SET_PORT_MOD(20,1,1,s) END configure')
        ctx=context();instance=translate_project({'main.kl':main,'lib.kl':library}).instantiate(context=ctx)
        self.assertEqual(instance.run('MAIN')['MAIN']['values']['S'],0)
        self.assertEqual(ctx.ports.configuration['pending_modes'][0]['mask'],1)

    def test_source_routine_can_shadow_builtin(self):
        state=run('SET_PORT_MOD(7)',routines='ROUTINE SET_PORT_MOD(value: INTEGER) BEGIN n=value END SET_PORT_MOD')
        self.assertEqual(state['N'],7)

    def test_observations_have_no_configuration_values(self):
        program,result=compile_program('SET_PORT_MOD(20,1,1,s) GET_PORT_MOD(20,1,n,s) IO_MOD_TYPE(0,1,n,s)',context=context())
        program.run();self.assertFalse(result.report['port_configuration_policy']['controller_validated'])
        self.assertEqual([row['operation'] for row in program.service_requests],['SET_PORT_MOD','GET_PORT_MOD','IO_MOD_TYPE'])
        self.assertTrue(all(set(row)=={'operation','line','outcome'} and row['outcome']=='completed' for row in program.service_requests))

    def test_task_powerup_does_not_apply_shared_port_configuration(self):
        ctx=context();program,_=compile_program('SET_PORT_MOD(20,1,1,s) PAUSE GET_PORT_MOD(20,1,n,s)',cooperative=True,context=ctx)
        with self.assertRaises(rt.KarelPause): program.run()
        self.assertEqual(program.powerup()['N'],0)
        self.assertEqual(ctx.ports.configuration['pending_modes'][0]['mask'],1)

    def test_pending_pulse_survives_configuration_apply(self):
        ctx=context(initial={('DOUT',1):False});clock={'us':0}
        program,_=compile_program('PULSE DOUT[1] FOR 9 NOWAIT SET_PORT_MOD(20,1,1,s) PAUSE',cooperative=True,context=ctx,clock_us=lambda:clock['us'])
        with self.assertRaises(rt.KarelPause): program.run()
        ctx.ports.apply_configuration();self.assertEqual(ctx.ports.pending_pulses,1)
        self.assertTrue(ctx.ports.read('DOUT',1));clock['us']=16000
        self.assertFalse(ctx.ports.read('DOUT',1));self.assertEqual(ctx.ports.pending_pulses,0)

    def test_active_settings_survive_new_program_and_pending_settings_are_shared(self):
        ctx=context();run('SET_PORT_MOD(20,1,1,s)',context=ctx)
        self.assertEqual(run('GET_PORT_MOD(20,1,n,s)',context=ctx)['N'],0)
        ctx.ports.apply_configuration()
        self.assertEqual(run('GET_PORT_MOD(20,1,n,s)',context=ctx)['N'],1)


class PortConfigurationPersistenceTests(unittest.TestCase):
    def test_authored_examples_check_pending_metadata_and_independent_restore(self):
        examples=Path(__file__).resolve().parents[1]/'examples'
        for name in ('port_configuration','port_configuration_guards'):
            with self.subTest(name=name):
                namespace={'__name__':'port_example'};exec(translate((examples/(name+'.kl')).read_text()).python_source,namespace)
                ctx=rt.ExecutionContext.load(examples/(name+'.services.initial.json'))
                self.assertEqual(namespace['Program'](context=ctx).run(),json.loads((examples/(name+'.expected.json')).read_text()))
                restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
                self.assertEqual(restored.to_config(),ctx.to_config())
                self.assertEqual(restored.ports.apply_configuration(),2 if name=='port_configuration' else 0)
                if name=='port_configuration':
                    self.assertEqual(restored.ports.configuration['assignments'][0]['start'],17)
                    self.assertEqual(ctx.ports.configuration['assignments'][0]['start'],1)
                    self.assertEqual(ctx.ports.configuration['pending_modes'][0]['mask'],3)

    def test_json_roundtrip_retains_active_and_pending_settings(self):
        ctx=context();run('SET_PORT_ASG(20,1,0,1,20,32,1,s) SET_PORT_MOD(20,1,1,s)',context=ctx)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.to_config(),ctx.to_config());self.assertEqual(restored.ports.apply_configuration(),2)
        state=run(GET+' GET_PORT_MOD(20,1,mode,s)',decl=DECL,context=restored)
        self.assertEqual((state['FIRST'],state['MODE']),(32,1));self.assertEqual(run(GET,decl=DECL,context=ctx)['FIRST'],9)

    def test_save_load_file_and_empty_configuration(self):
        ctx=context({})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';ctx.save(path);restored=rt.ExecutionContext.load(path)
        self.assertEqual(restored.ports.configuration,{});self.assertEqual(restored.ports.apply_configuration(),0)

    def test_snapshots_and_constructor_input_are_detached(self):
        config=topology();ctx=context(config);config['assignments'][0]['start']=50
        snapshot=ctx.ports.configuration;snapshot['assignments'][0]['start']=60;snapshot['physical'].clear()
        self.assertEqual(run(GET,decl=DECL,context=ctx)['FIRST'],9);self.assertEqual(len(ctx.ports.configuration['physical']),4)

    def test_existing_value_snapshot_and_plain_context_shapes_are_unchanged(self):
        bank=rt.PortBank({'DIN':1},{('DIN',1):True});ctx=rt.ExecutionContext(ports=bank)
        self.assertEqual(bank.snapshot(),{('DIN',1):True})
        self.assertEqual(ctx.to_config()['ports'],{'counts':{'DIN':1},'values':{'DIN':{'1':True}}})
        with self.assertRaisesRegex(rt.KarelRuntimeError,'configuration'): bank.apply_configuration()

    def test_configuration_validation_rejects_unknown_fields_and_shapes(self):
        for config in ([],True,{'extra':[]},{'modules':{}},{'modes':None},{'physical':[{}]},
                       {'modules':[dict(rack=0,slot=1,type=7,extra=1)]}):
            with self.subTest(config=config),self.assertRaises(ValueError): context(config)

    def test_context_null_configuration_is_invalid(self):
        with self.assertRaises(ValueError): rt.ExecutionContext.from_config({'ports':{'counts':{},'configuration':None}})

    def test_catalog_numeric_domains_are_exact(self):
        for field,value in (('rack',True),('rack',-1),('rack',32768),('slot',-1),('type_code',-1),('type_code',2147483647),('count',0),('count',32768),('count',1.0)):
            with self.subTest(field=field,value=value):
                config=topology();config['physical'][0][field]=value
                with self.assertRaises(ValueError): context(config)

    def test_catalog_kind_and_code_conflicts_are_rejected(self):
        for kind in ('GIN','SOPIN',False,['DIN']):
            with self.subTest(kind=kind):
                config=topology();config['physical'][0]['kind']=kind
                with self.assertRaises(ValueError): context(config)
        config=topology();config['physical'][0]['kind']='DOUT'
        with self.assertRaises(ValueError): context(config)
        config=topology();config['physical'].append(dict(rack=1,slot=1,type_code=10,kind='DOUT',count=4))
        with self.assertRaises(ValueError): context(config)

    def test_duplicate_catalog_rows_and_settings_are_rejected(self):
        for field in ('physical','modules','assignments','pending_assignments','modes','pending_modes'):
            with self.subTest(field=field):
                config=topology()
                if field=='pending_assignments': config[field]=deepcopy(config['assignments'])
                if field in ('modes','pending_modes'): config[field]=[dict(kind='DOUT',number=1,mask=1)]
                config[field].append(deepcopy(config[field][0]))
                with self.assertRaises(ValueError): context(config)

    def test_invalid_active_and_pending_assignments_are_rejected(self):
        for field in ('assignments','pending_assignments'):
            for key,value in (('kind','SOPIN'),('number',9),('type_code',10),('start',65),('count',0),('count',True)):
                with self.subTest(field=field,key=key,value=value):
                    config=topology();config[field]=[dict(kind='DOUT',number=1,rack=0,slot=1,type_code=20,start=1,count=1)]
                    config[field][0][key]=value
                    with self.assertRaises(ValueError): context(config)

    def test_invalid_active_and_pending_modes_are_rejected(self):
        for field in ('modes','pending_modes'):
            for kind,number,mask in (('DIN',1,2),('DOUT',2,2),('DOUT',1,4),('DOUT',1,True),('DOUT',9,1)):
                with self.subTest(field=field,values=(kind,number,mask)):
                    config=topology();config[field]=[dict(kind=kind,number=number,mask=mask)]
                    with self.assertRaises(ValueError): context(config)

    def test_seeded_digital_batch_normalizes_to_single_point_rows(self):
        config=topology();config['assignments'][0]['count']=8;ctx=context(config)
        self.assertEqual(len(ctx.ports.configuration['assignments']),8)
        self.assertEqual(rt.ExecutionContext.from_config(ctx.to_config()).to_config(),ctx.to_config())


if __name__=='__main__': unittest.main()
