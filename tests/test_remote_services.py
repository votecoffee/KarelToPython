"""Authored remote spellings over isolated, explicitly supplied offline banks."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from karel2py import runtime as rt, translate_project
from karel2py.extended import REMOTE_SERVICES
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run

ROOT=Path(__file__).resolve().parents[1]
DECL='n,s,i:INTEGER x:REAL flag,simulated:BOOLEAN text:STRING[32]'


def banks():
    return dict(numeric=rt.NumericRegisters(3,{1:42,2:1.25}),
                strings=rt.StringRegisters(2,{1:'ready'},capacity=8),
                positions=rt.PositionRegisters(2),
                ports=rt.PortBank({'DIN':1,'DOUT':1,'GOUT':1,'AOUT':1},
                    {('DIN',1):False,('DOUT',1):True,('AOUT',1):1.25},
                    type_codes={10:'DIN',20:'DOUT',30:'GOUT',40:'AOUT'}))


def context(first=None,**local):
    return rt.ExecutionContext(peers=rt.PeerBanks({'RC1':banks() if first is None else first}),**local)


def execute(body,ctx=None,**options):
    return run(body,decl=DECL,context=context() if ctx is None else ctx,**options)


class PeerBanksTests(unittest.TestCase):
    def test_binding_copies_mappings_and_shares_explicit_banks(self):
        data=banks();peers={'rc1':dict(data)};service=rt.PeerBanks(peers)
        peers.clear();row=service.lookup('rC1');row.pop('strings')
        self.assertIs(service.lookup('RC1')['numeric'],data['numeric'])
        self.assertIn('strings',service.lookup('RC1'))
        self.assertIsNone(service.lookup('missing'))

    def test_distinct_peers_have_independent_banks(self):
        a,b=banks(),banks();service=rt.PeerBanks({'rc1':a,'rc2':b})
        a['numeric'].write(1,9)
        self.assertEqual(service.lookup('rc2')['numeric'].read(1),(0,42))

    def test_invalid_host_names(self):
        for name in ('','name with space','../host','é','a'*255,1,True):
            with self.subTest(name=name),self.assertRaises(ValueError): rt.PeerBanks({name:{}})

    def test_duplicate_hosts_and_invalid_service_schema(self):
        for value in ([],{'rc1':None},{'rc1':{'files':rt.MemoryFiles()}},
                      {'rc1':{'peers':{}}},{'rc1':{},'RC1':{}}):
            with self.subTest(value=value),self.assertRaises(ValueError): rt.PeerBanks(value)
        with self.assertRaises(TypeError): rt.PeerBanks({'rc1':{'numeric':{'count':2}}})
        with self.assertRaises(TypeError): rt.ExecutionContext(peers={})

    def test_empty_service_and_absent_service_remain_distinct(self):
        self.assertEqual(rt.ExecutionContext().to_config(),{})
        self.assertEqual(rt.ExecutionContext(peers=rt.PeerBanks()).to_config(),{'peers':{}})

    def test_named_hosts_accept_ip_and_configured_alias_spelling(self):
        self.assertEqual(set(rt.PeerBanks({'192.0.2.1':{},'cell-a.example':{},'C1:':{}}).to_config()),
                         {'192.0.2.1','CELL-A.EXAMPLE','C1:'})

    def test_json_roundtrip_preserves_values_kinds_comments_and_simulation(self):
        ctx=context();peer=ctx.peers.lookup('rc1')
        peer['numeric'].comments.write(1,'count');peer['positions'].comments.write(1,'point')
        peer['ports'].simulated.add(('DIN',1))
        saved=ctx.to_config();restored=rt.ExecutionContext.from_config(json.loads(json.dumps(saved)))
        self.assertEqual(restored.to_config(),saved)
        self.assertIs(type(restored.peers.lookup('rc1')['numeric'].read(2)[1]),float)
        saved['peers']['RC1']['numeric']['values']['1']=9
        self.assertEqual(peer['numeric'].read(1),(0,42))

    def test_json_rejects_nested_contexts_and_bad_bank_values(self):
        for value in (None,[],{'rc1':{'peers':{}}},{'rc1':{'variables':[]}},
                      {'rc1':{'numeric':{'count':1,'values':{'01':7}}}},
                      {'rc1':{'ports':{'counts':{'DIN':1},'type_codes':{'01':'DIN'}}}}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                rt.ExecutionContext.from_config({'peers':value})

    def test_save_load_keeps_empty_peer_and_mutated_bank(self):
        ctx=context();ctx.peers.lookup('RC1')['strings'].write(2,'saved')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'context.json';ctx.save(path)
            self.assertEqual(rt.ExecutionContext.load(path).to_config(),ctx.to_config())


class RemoteNumericTests(unittest.TestCase):
    def test_integer_read_sets_boolean_flag_and_selected_value_only(self):
        state=execute("x=9 RGET_REG('rc1',1,flag,n,x,s)")
        self.assertEqual((state['FLAG'],state['N'],state['X'],state['S']),(False,42,9.,0))

    def test_real_read_leaves_integer_output_uninitialized(self):
        state=execute("RGET_REG('RC1',2,flag,n,x,s)")
        self.assertEqual((state['FLAG'],state['N'],state['X'],state['S']),(True,{'uninitialized':True},1.25,0))

    def test_integer_and_real_writes_change_kind_and_read_back(self):
        ctx=context()
        state=execute("RSET_REALREG('RC1',1,2,s) RGET_REG('RC1',1,flag,n,x,s)",ctx)
        self.assertEqual((state['FLAG'],state['X']),(True,2.))
        state=execute("RSET_INT_REG('RC1',1,-8,s) RGET_REG('RC1',1,flag,n,x,s)",ctx)
        self.assertEqual((state['FLAG'],state['N']),(False,-8))

    def test_missing_and_range_statuses_preserve_read_outputs(self):
        for number,status in ((3,1),(0,2),(4,2)):
            with self.subTest(number=number):
                state=execute(f"flag=ON n=7 x=8 RGET_REG('RC1',{number},flag,n,x,s)")
                self.assertEqual((state['FLAG'],state['N'],state['X'],state['S']),(True,7,8.,status))

    def test_remote_bank_never_falls_back_to_local_numeric_bank(self):
        local=rt.NumericRegisters(3,{1:99});ctx=context(numeric=local)
        state=execute("RSET_INT_REG('RC1',1,8,s) GET_REG(1,flag,n,x,s)",ctx)
        self.assertEqual((state['N'],local.read(1),ctx.peers.lookup('rc1')['numeric'].read(1)),(99,(0,99),(0,8)))

    def test_unknown_peer_preserves_bank_and_outputs(self):
        ctx=context();before=ctx.peers.to_config()
        state=execute("flag=ON n=7 x=8 RGET_REG('absent',1,flag,n,x,s)",ctx)
        self.assertEqual((state['FLAG'],state['N'],state['X'],state['S']),(True,7,8.,rt.PEER_UNAVAILABLE))
        self.assertEqual(ctx.peers.to_config(),before)

    def test_missing_service_raises_without_status_change(self):
        for ctx in (rt.ExecutionContext(),context({})):
            with self.subTest(ctx=ctx):
                p,_=compile_program("s=7 RSET_INT_REG('RC1',1,8,s)",decl=DECL,context=ctx)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual(p.snapshot()['S'],7)

    def test_invalid_numeric_value_does_not_mutate_bank(self):
        ctx=context();p,_=compile_program("s=7 RSET_INT_REG('RC1',1,MAXINT,s)",decl=DECL,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['S'],ctx.peers.lookup('rc1')['numeric'].read(1)),(7,(0,42)))

    def test_output_alias_is_rejected_before_read_changes_outputs(self):
        p,_=compile_program("n=7 RGET_REG('RC1',1,flag,n,x,n)",decl=DECL,context=context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'): p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['FLAG']),(7,{'uninitialized':True}))


class RemoteStringCommentTests(unittest.TestCase):
    def test_string_roundtrip_uses_peer_and_target_capacities(self):
        ctx=context();state=execute("RSET_STR_REG('RC1',2,'123456789',s) RGET_STR_REG('RC1',2,text,s)",ctx)
        self.assertEqual((state['TEXT'],ctx.peers.lookup('rc1')['strings'].read(2)),('12345678',(0,'12345678')))
        state=run("RGET_STR_REG('RC1',2,text,s)",decl='text:STRING[3] s:INTEGER',context=ctx)
        self.assertEqual(state['TEXT'],'123')

    def test_missing_string_and_range_preserve_text(self):
        for number,status in ((2,1),(3,2)):
            with self.subTest(number=number):
                state=execute(f"text='prior' RGET_STR_REG('RC1',{number},text,s)")
                self.assertEqual((state['TEXT'],state['S']),('prior',status))

    def test_three_comment_families_roundtrip_independent_of_register_values(self):
        for suffix,kind in (('REG_CMT','numeric'),('PREGCMT','positions'),('SREGCMT','strings')):
            with self.subTest(suffix=suffix):
                ctx=context();state=execute(f"RSET_{suffix}('RC1',2,'comment',s) RGET_{suffix}('RC1',2,text,s)",ctx)
                self.assertEqual((state['TEXT'],state['S']),('comment',0))
                self.assertEqual(ctx.peers.lookup('rc1')[kind].comments.read(2),(0,'comment'))

    def test_all_comment_writes_truncate_to_sixteen(self):
        for suffix in ('REG_CMT','PREGCMT','SREGCMT','PORTCMT'):
            with self.subTest(suffix=suffix):
                address='20,1' if suffix=='PORTCMT' else '1'
                state=execute(f"RSET_{suffix}('RC1',{address},'12345678901234567890',s) RGET_{suffix}('RC1',{address},text,s)")
                self.assertEqual((state['TEXT'],state['S']),('1234567890123456',0))

    def test_get_limits_host_supplied_long_register_comments_to_sixteen(self):
        data=banks();data['numeric'].comments=rt.RegisterComments(3,{1:'12345678901234567890'},capacity=32)
        state=execute("RGET_REG_CMT('RC1',1,text,s)",context(data))
        self.assertEqual(state['TEXT'],'1234567890123456')

    def test_empty_comment_succeeds_without_initializing_position_value(self):
        ctx=context();state=execute("RGET_PREGCMT('RC1',1,text,s)",ctx)
        self.assertEqual((state['TEXT'],state['S']),('',0))
        self.assertEqual(ctx.peers.lookup('RC1')['positions'].snapshot(),{})

    def test_invalid_comment_register_preserves_text(self):
        state=execute("text='prior' RGET_PREGCMT('RC1',3,text,s)")
        self.assertEqual((state['TEXT'],state['S']),('prior',2))


class RemotePortTests(unittest.TestCase):
    def test_boolean_output_integer_roundtrip(self):
        ctx=context();state=execute("RSET_PORTVAL('RC1',20,1,0,s) RGET_PORTVAL('RC1',20,1,n,s)",ctx)
        self.assertEqual((state['N'],state['S'],ctx.peers.lookup('RC1')['ports'].read('DOUT',1)),(0,0,False))

    def test_simulated_input_write_and_boolean_simulation_query(self):
        ctx=context();state=execute("RSET_PORTSIM('RC1',10,1,1,s) RGET_PORTSIM('RC1',10,1,simulated,s) RSET_PORTVAL('RC1',10,1,0,s) RGET_PORTVAL('RC1',10,1,n,s)",ctx)
        self.assertEqual((state['SIMULATED'],state['N'],state['S']),(True,0,0))
        self.assertIn(('DIN',1),ctx.peers.lookup('RC1')['ports'].simulated)

    def test_unsimulated_input_write_preserves_input(self):
        ctx=context();state=execute("RSET_PORTVAL('RC1',10,1,1,s)",ctx)
        self.assertEqual((state['S'],ctx.peers.lookup('RC1')['ports'].read('DIN',1)),(4,False))

    def test_unsimulated_query_is_false_even_when_no_value_supplied(self):
        state=execute("RGET_PORTSIM('RC1',30,1,simulated,s)")
        self.assertEqual((state['SIMULATED'],state['S']),(False,0))

    def test_fractional_analog_value_does_not_truncate_to_integer(self):
        state=execute("n=7 RGET_PORTVAL('RC1',40,1,n,s)")
        self.assertEqual((state['N'],state['S']),(7,3))

    def test_analog_and_group_integer_writes(self):
        ctx=context();state=execute("RSET_PORTVAL('RC1',40,1,2,s) RSET_PORTVAL('RC1',30,1,7,s) RGET_PORTVAL('RC1',30,1,n,s)",ctx)
        self.assertEqual((state['N'],ctx.peers.lookup('RC1')['ports'].read('AOUT',1)),(7,2.))

    def test_invalid_value_or_address_has_no_write_effect(self):
        ctx=context();before=ctx.peers.to_config()
        for call,status in (("RSET_PORTSIM('RC1',10,1,2,s)",3),
                            ("RSET_PORTVAL('RC1',30,1,-1,s)",3),
                            ("RSET_PORTVAL('RC1',999,1,1,s)",2)):
            with self.subTest(call=call): self.assertEqual(execute(call,ctx)['S'],status)
        self.assertEqual(ctx.peers.to_config(),before)

    def test_failed_simulation_query_keeps_boolean_output(self):
        state=execute("simulated=ON RGET_PORTSIM('RC1',999,1,simulated,s)")
        self.assertEqual((state['SIMULATED'],state['S']),(True,2))

    def test_missing_type_codes_raise_without_mutation(self):
        ctx=context({'ports':rt.PortBank({'DOUT':1})})
        p,_=compile_program("s=7 RSET_PORTVAL('RC1',20,1,1,s)",decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type_codes'): p.run()
        self.assertEqual((p.snapshot()['S'],ctx.peers.lookup('rc1')['ports'].snapshot()),(7,{}))


class RemoteIntegrationTests(unittest.TestCase):
    def test_all_seventeen_operations_are_reported_with_source_locations(self):
        source=(ROOT/'examples/remote_banks.kl').read_text()
        from karel2py import translate
        report=translate(source).report
        self.assertEqual({row['operation'] for row in report['service_operations']},set(REMOTE_SERVICES))
        self.assertTrue(all(row['line']>0 for row in report['service_operations']))
        self.assertFalse(report['remote_bank_policy']['controller_validated'])

    def test_arguments_run_once_in_source_order(self):
        routines="""ROUTINE host:STRING BEGIN i=i*10+1 RETURN 'RC1' END host
ROUTINE number:INTEGER BEGIN i=i*10+2 RETURN 1 END number
ROUTINE value:INTEGER BEGIN i=i*10+3 RETURN 8 END value
ROUTINE slot:INTEGER BEGIN i=i*10+4 RETURN 1 END slot"""
        ctx=context();state=run('i=0 RSET_INT_REG(host,number,value,codes[slot])',decl=DECL+' codes:ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        self.assertEqual((state['I'],state['CODES'],ctx.peers.lookup('rc1')['numeric'].read(1)),(1234,[0],(0,8)))

    def test_failed_input_skips_later_output_selector_effects(self):
        routines='ROUTINE slot:INTEGER BEGIN i=9 RETURN 1 END slot'
        ctx=context();p,_=compile_program("i=0 RSET_INT_REG('RC1',1,n,codes[slot])",decl=DECL+' codes:ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['I'],ctx.peers.lookup('rc1')['numeric'].read(1)),(0,(0,42)))

    def test_active_counter_and_transitive_output_guards(self):
        for body,routines in (("FOR i=1 TO 2 DO RSET_INT_REG('RC1',1,8,i) ENDFOR",''),
                ('FOR i=1 TO 2 DO query ENDFOR',"ROUTINE query BEGIN RGET_PORTVAL('RC1',20,1,i,s) END query")):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,decl=DECL,routines=routines)

    def test_exact_output_types_and_readonly_fields_are_retained(self):
        for body,decl in (("RGET_REG('RC1',1,n,i,x,s)",DECL),
                ("RGET_PORTSIM('RC1',20,1,n,s)",DECL),
                ("RGET_PORTCMT('RC1',20,1,n,s)",DECL),
                ("RGET_PORTVAL('RC1',20,1,x,s)",DECL),
                ("RGET_PORTSIM('RC1',20,1,c.cfg_flip,s)",DECL+' c:CONFIG'),
                ("RGET_PORTVAL('RC1',20,1,s,MAXINT)",DECL)):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,decl=decl)

    def test_internal_routine_precedence(self):
        state=run('RGET_REG(n)',routines='ROUTINE RGET_REG(x:INTEGER) BEGIN x=9 END RGET_REG')
        self.assertEqual(state['N'],9)

    def test_linked_routine_shares_peer_updates(self):
        sources={'lib':"PROGRAM LIB ROUTINE put(code:INTEGER) BEGIN RSET_INT_REG('RC1',1,99,code) END put BEGIN END LIB",
                 'main':"PROGRAM MAIN VAR n,s:INTEGER x:REAL flag:BOOLEAN ROUTINE put(code:INTEGER) FROM LIB BEGIN put(s) RGET_REG('RC1',1,flag,n,x,s) END MAIN"}
        instance=translate_project(sources).instantiate(context=context());instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].snapshot()['N'],99)

    def test_service_observations_are_value_free_and_detached(self):
        p,_=compile_program("RSET_STR_REG('RC1',1,'secret',s)",decl=DECL,context=context());p.run()
        rows=p.service_requests
        self.assertEqual(rows[0]['operation'],'RSET_STR_REG');self.assertNotIn('secret',repr(rows))
        rows[0]['operation']='changed';self.assertEqual(p.service_requests[0]['operation'],'RSET_STR_REG')
        self.assertEqual(p.register_requests,())

    def test_queries_never_use_sockets_or_dns(self):
        with patch('socket.socket',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('dns')):
            self.assertEqual(execute("RGET_REG('RC1',1,flag,n,x,s)")['N'],42)
            self.assertEqual(execute("RSET_INT_REG('unbound.example',1,9,s)")['S'],rt.PEER_UNAVAILABLE)

    def test_fresh_cli_translation_execution_and_persisted_peer_state(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'converted.py';report=Path(folder)/'report.json';state=Path(folder)/'state.json'
            env={**os.environ,'PYTHONPATH':str(ROOT)}
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(ROOT/'examples/remote_banks.kl'),'-o',str(output),'--report',str(report)],cwd=folder,capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([sys.executable,'-X','utf8',str(output),'--context',str(ROOT/'examples/remote_banks.services.initial.json'),'--state-out',str(state)],cwd=folder,capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(ast.literal_eval(result.stdout),json.loads((ROOT/'examples/remote_banks.expected.json').read_text()))
            self.assertEqual(json.loads(state.read_text())['peers'],json.loads((ROOT/'examples/remote_banks.services.expected.json').read_text())['peers'])
            self.assertIn('remote_bank_policy',json.loads(report.read_text()))
