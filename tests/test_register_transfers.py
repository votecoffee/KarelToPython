"""Authored register-to-register peer transfers, preflight and CLI execution."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.extended import REMOTE_TRANSFERS
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run

ROOT=Path(__file__).resolve().parents[1]
CALLS={
    'RNUMREG_RECV':"RNUMREG_RECV('RC1',1,2,0,s)",
    'RNUMREG_SEND':"RNUMREG_SEND('RC1',2,1,0,s)",
    'RPOSREG_RECV':"RPOSREG_RECV('RC1',1,2,2,1,0,s)",
    'RPOSREG_SEND':"RPOSREG_SEND('RC1',2,2,1,1,0,s)"}


def joint(width=3,offset=0.):
    value=rt.JointPosition(('JOINTPOS',width));value.values[:]=[offset+float(n) for n in range(width)]
    return value


def context():
    local=rt.NumericRegisters(3,{1:9,2:8.5},comments={1:'local',2:'retained'})
    peer=rt.NumericRegisters(3,{1:42,2:1.25},comments={1:'peer',2:'previous'})
    positions=rt.PositionRegisters(3,{(1,1):joint(offset=10.)},groups=(1,3),comments={1:'local point',2:'retained'})
    remote=rt.PositionRegisters(3,{(2,1):joint(offset=20.)},groups=(2,4),comments={1:'peer point',2:'previous'})
    return rt.ExecutionContext(numeric=local,positions=positions,
        peers=rt.PeerBanks({'RC1':{'numeric':peer,'positions':remote}}))


def execute(body,ctx=None,**options):
    return run(body,context=context() if ctx is None else ctx,**options)


class NumericTransferTests(unittest.TestCase):
    def test_receive_value_and_comment(self):
        ctx=context();state=execute(CALLS['RNUMREG_RECV'],ctx)
        self.assertEqual((state['S'],ctx.numeric.read(2),ctx.numeric.comments.read(2)),(0,(0,42),(0,'peer')))

    def test_send_orders_destination_before_source(self):
        ctx=context();peer=ctx.peers.lookup('RC1')['numeric'];state=execute(CALLS['RNUMREG_SEND'],ctx)
        self.assertEqual((state['S'],peer.read(2),peer.comments.read(2)),(0,(0,9),(0,'local')))

    def test_real_kind_is_preserved_on_receive(self):
        ctx=context();execute("RNUMREG_RECV('RC1',2,1,1,s)",ctx)
        self.assertEqual(ctx.numeric.read(1),(0,1.25));self.assertIs(type(ctx.numeric.read(1)[1]),float)

    def test_real_kind_is_preserved_on_send(self):
        ctx=context();execute("RNUMREG_SEND('RC1',1,2,1,s)",ctx)
        self.assertEqual(ctx.peers.lookup('RC1')['numeric'].read(1),(0,8.5))

    def test_value_only_preserves_destination_comment(self):
        for name in ('RNUMREG_RECV','RNUMREG_SEND'):
            with self.subTest(name=name):
                ctx=context();execute(CALLS[name].replace(',0,s)',',1,s)'),ctx)
                destination=ctx.numeric if name.endswith('RECV') else ctx.peers.lookup('RC1')['numeric']
                self.assertEqual(destination.comments.read(2),(0,'retained' if name.endswith('RECV') else 'previous'))

    def test_comment_only_does_not_require_source_value(self):
        for direction in ('RECV','SEND'):
            with self.subTest(direction=direction):
                ctx=context();peer=ctx.peers.lookup('RC1')['numeric']
                source,destination=(peer,ctx.numeric) if direction=='RECV' else (ctx.numeric,peer)
                source.comments.write(3,'annotation')
                call=f"RNUMREG_RECV('RC1',3,2,2,s)" if direction=='RECV' else "RNUMREG_SEND('RC1',2,3,2,s)"
                before=destination.read(2);state=execute(call,ctx)
                self.assertEqual((state['S'],destination.read(2),destination.comments.read(2)),(0,before,(0,'annotation')))

    def test_empty_source_comment_clears_destination_comment_only(self):
        ctx=context();execute("RNUMREG_RECV('RC1',3,2,2,s)",ctx)
        self.assertEqual((ctx.numeric.read(2),ctx.numeric.comments.read(2)),((0,8.5),(0,'')))

    def test_missing_source_value_preserves_destination_and_comment(self):
        ctx=context();before=ctx.to_config();state=execute("RNUMREG_RECV('RC1',3,2,0,s)",ctx)
        self.assertEqual(state['S'],1);self.assertEqual(ctx.numeric.to_config(),before['numeric'])

    def test_invalid_addresses_and_options_do_not_mutate_banks(self):
        for call,status in (("RNUMREG_RECV('RC1',0,2,0,s)",2),
                            ("RNUMREG_SEND('RC1',4,1,0,s)",2),
                            ("RNUMREG_RECV('RC1',1,2,3,s)",3)):
            with self.subTest(call=call):
                ctx=context();before=ctx.peers.to_config(),ctx.numeric.to_config()
                self.assertEqual(execute(call,ctx)['S'],status)
                self.assertEqual((ctx.peers.to_config(),ctx.numeric.to_config()),before)

    def test_explicit_program_registers_override_context_numeric(self):
        ctx=context();override=rt.NumericRegisters(3)
        execute(CALLS['RNUMREG_RECV'],ctx,registers=override)
        self.assertEqual((override.read(2),ctx.numeric.read(2)),((0,42),(0,8.5)))

    def test_both_directions_allow_explicitly_shared_bank(self):
        ctx=context();ctx.peers=rt.PeerBanks({'RC1':{'numeric':ctx.numeric}})
        execute("RNUMREG_SEND('RC1',2,1,0,s) RNUMREG_RECV('RC1',2,2,0,s)",ctx)
        self.assertEqual((ctx.numeric.read(2),ctx.numeric.comments.read(2)),((0,9),(0,'local')))

    def test_bad_source_numeric_value_raises_before_destination_changes(self):
        ctx=context();ctx.peers.lookup('RC1')['numeric']._values[1]=True
        p,_=compile_program('s=7 '+CALLS['RNUMREG_RECV'],context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['S'],ctx.numeric.read(2),ctx.numeric.comments.read(2)),(7,(0,8.5),(0,'retained')))


class PositionTransferTests(unittest.TestCase):
    def test_manual_heading_spellings_are_supported_as_aliases(self):
        for name in ('RPOSREG_RECV','RPOSREG_SEND'):
            with self.subTest(name=name):
                ctx=context();self.assertEqual(execute(CALLS[name].replace('RPOSREG','RPREG'),ctx)['S'],0)
                bank=ctx.positions if name.endswith('RECV') else ctx.peers.lookup('RC1')['positions']
                self.assertEqual(bank.read(2,1 if name.endswith('RECV') else 2)[0],0)

    def test_receive_uses_both_explicit_groups(self):
        ctx=context();state=execute(CALLS['RPOSREG_RECV'],ctx)
        self.assertEqual((state['S'],ctx.positions.read(2,1)[1].values,ctx.positions.comments.read(2)),(0,[20.,21.,22.],(0,'peer point')))
        self.assertEqual(ctx.positions.read(2,3),(1,None))

    def test_send_orders_destination_group_before_source_group(self):
        ctx=context();state=execute(CALLS['RPOSREG_SEND'],ctx);peer=ctx.peers.lookup('RC1')['positions']
        self.assertEqual((state['S'],peer.read(2,2)[1].values,peer.comments.read(2)),(0,[10.,11.,12.],(0,'local point')))

    def test_value_only_preserves_comment(self):
        ctx=context();execute(CALLS['RPOSREG_RECV'].replace(',0,s)',',1,s)'),ctx)
        self.assertEqual(ctx.positions.comments.read(2),(0,'retained'))

    def test_position_has_no_comment_only_option(self):
        ctx=context();before=ctx.positions.snapshot();state=execute(CALLS['RPOSREG_RECV'].replace(',0,s)',',2,s)'),ctx)
        self.assertEqual(state['S'],3);self.assertEqual(set(ctx.positions.snapshot()),set(before))

    def test_group_and_index_errors_preserve_value_and_comment(self):
        for call in ("RPOSREG_RECV('RC1',1,1,2,1,0,s)",
                     "RPOSREG_RECV('RC1',1,2,2,2,0,s)",
                     "RPOSREG_SEND('RC1',4,2,1,1,0,s)"):
            with self.subTest(call=call):
                ctx=context();before=ctx.peers.to_config(),ctx.positions.comments.snapshot()
                self.assertEqual(execute(call,ctx)['S'],2)
                self.assertEqual((ctx.peers.to_config(),ctx.positions.comments.snapshot()),before)

    def test_missing_source_preserves_destination_comment(self):
        ctx=context();state=execute("RPOSREG_RECV('RC1',3,2,2,1,0,s)",ctx)
        self.assertEqual((state['S'],ctx.positions.read(2,1),ctx.positions.comments.read(2)),(1,(1,None),(0,'retained')))

    def test_joint_width_and_external_axes_are_not_padded_or_reinterpreted(self):
        ctx=context();value=joint(9,10.);ctx.peers.lookup('RC1')['positions'].write(1,value,2)
        execute(CALLS['RPOSREG_RECV'],ctx);copy=ctx.positions.read(2,1)[1]
        self.assertEqual((copy.spec,copy.values),(('JOINTPOS',9),[10.+n for n in range(9)]))

    def test_cartesian_representations_and_external_metadata_are_preserved(self):
        for kind in ('POSITION','XYZWPR','XYZWPREXT'):
            with self.subTest(kind=kind):
                p,_=compile_program("CNV_STR_CONF('F L U T,-1,2,3',c,s) p=POS(1,2,3,10,20,30,c)",decl=f'c:CONFIG p:{kind} s:INTEGER')
                p.run();value=p._state.values['P']
                if kind=='XYZWPREXT': value.values.update(EXT1=12.,EXT2=-3.,EXT3=4.)
                ctx=context();ctx.peers.lookup('RC1')['positions'].write(1,value,2)
                execute(CALLS['RPOSREG_RECV'],ctx);copied=ctx.positions.read(2,1)[1]
                self.assertEqual((copied.spec,rt.snapshot_value(copied)),(value.spec,rt.snapshot_value(value)))

    def test_copied_values_are_detached(self):
        ctx=context();execute(CALLS['RPOSREG_RECV'],ctx)
        ctx.positions.values[1,2].values[0]=99.
        self.assertEqual(ctx.peers.lookup('RC1')['positions'].read(1,2)[1].values[0],20.)

    def test_partial_source_raises_before_any_transfer_write(self):
        ctx=context();ctx.peers.lookup('RC1')['positions'].values[2,1].values[0]=rt.UNINITIALIZED
        p,_=compile_program('s=7 '+CALLS['RPOSREG_RECV'],context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['S'],ctx.positions.read(2,1),ctx.positions.comments.read(2)),(7,(1,None),(0,'retained')))


class TransferGuardTests(unittest.TestCase):
    def test_comment_destination_is_preflighted_before_numeric_value_write(self):
        ctx=context();ctx.numeric.comments=rt.RegisterComments(1)
        state=execute(CALLS['RNUMREG_RECV'],ctx)
        self.assertEqual((state['S'],ctx.numeric.read(2)),(2,(0,8.5)))

    def test_comment_destination_is_preflighted_before_position_write(self):
        ctx=context();ctx.positions.comments=rt.RegisterComments(1)
        state=execute(CALLS['RPOSREG_RECV'],ctx)
        self.assertEqual((state['S'],ctx.positions.read(2,1)),(2,(1,None)))

    def test_invalid_comment_does_not_publish_valid_numeric_value(self):
        ctx=context();ctx.peers.lookup('RC1')['numeric'].comments.values[1]='é'
        p,_=compile_program('s=7 '+CALLS['RNUMREG_RECV'],context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['S'],ctx.numeric.read(2),ctx.numeric.comments.read(2)),(7,(0,8.5),(0,'retained')))

    def test_comments_follow_remote_sixteen_character_limit_and_destination_capacity(self):
        ctx=context();ctx.peers.lookup('RC1')['numeric'].comments=rt.RegisterComments(3,{1:'12345678901234567890'},capacity=32)
        execute(CALLS['RNUMREG_RECV'],ctx);self.assertEqual(ctx.numeric.comments.read(2),(0,'1234567890123456'))
        ctx.numeric.comments=rt.RegisterComments(3,capacity=4)
        execute(CALLS['RNUMREG_RECV'],ctx);self.assertEqual(ctx.numeric.comments.read(2),(0,'1234'))

    def test_unknown_peer_uses_status_five_without_local_mutation(self):
        for name,call in CALLS.items():
            with self.subTest(name=name):
                ctx=context();before=ctx.numeric.to_config(),ctx.positions.comments.snapshot()
                self.assertEqual(execute(call.replace("'RC1'","'missing'"),ctx)['S'],5)
                self.assertEqual((ctx.numeric.to_config(),ctx.positions.comments.snapshot()),before)

    def test_missing_peer_service_raises(self):
        for call in CALLS.values():
            with self.subTest(call=call):
                ctx=context();ctx.peers=rt.PeerBanks({'RC1':{}})
                p,_=compile_program('s=7 '+call,context=ctx)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual(p.snapshot()['S'],7)

    def test_missing_local_bank_never_falls_back_to_peer_bank(self):
        for call in CALLS.values():
            with self.subTest(call=call):
                ctx=context();ctx.numeric=None;ctx.positions=None
                p,_=compile_program('s=7 '+call,context=ctx)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual(p.snapshot()['S'],7)

    def test_value_only_ignores_comment_storage(self):
        ctx=context();ctx.peers.lookup('RC1')['numeric'].comments.values[1]='é'
        state=execute(CALLS['RNUMREG_RECV'].replace(',0,s)',',1,s)'),ctx)
        self.assertEqual((state['S'],ctx.numeric.read(2),ctx.numeric.comments.read(2)),(0,(0,42),(0,'retained')))


class TransferIntegrationTests(unittest.TestCase):
    def test_all_arguments_run_once_in_source_order(self):
        routines="""ROUTINE host:STRING BEGIN n=n*10+1 RETURN 'RC1' END host
ROUTINE src:INTEGER BEGIN n=n*10+2 RETURN 1 END src
ROUTINE dest:INTEGER BEGIN n=n*10+3 RETURN 2 END dest
ROUTINE option:INTEGER BEGIN n=n*10+4 RETURN 0 END option
ROUTINE slot:INTEGER BEGIN n=n*10+5 RETURN 1 END slot"""
        state=run('n=0 RNUMREG_RECV(host,src,dest,option,codes[slot])',decl='n:INTEGER codes:ARRAY[1] OF INTEGER',routines=routines,context=context())
        self.assertEqual((state['N'],state['CODES']),(12345,[0]))

    def test_output_cannot_be_an_active_counter_even_through_routines(self):
        for body,routines in (("FOR n=1 TO 2 DO RNUMREG_RECV('RC1',1,2,0,n) ENDFOR",''),
                ('FOR n=1 TO 2 DO transfer ENDFOR',"ROUTINE transfer BEGIN RPOSREG_RECV('RC1',1,2,2,1,0,n) END transfer")):
            with self.subTest(body=body),self.assertRaises(TranslationError): compile_program(body,routines=routines)

    def test_uninitialized_input_skips_status_selector_effects(self):
        routines='ROUTINE slot:INTEGER BEGIN n=9 RETURN 1 END slot'
        ctx=context();p,_=compile_program("n=0 RNUMREG_RECV('RC1',s,2,0,codes[slot])",decl='n,s:INTEGER codes:ARRAY[1] OF INTEGER',routines=routines,context=ctx)
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['N'],ctx.numeric.read(2)),(0,(0,8.5)))

    def test_internal_routine_precedence(self):
        state=run('RNUMREG_RECV(n)',routines='ROUTINE RNUMREG_RECV(x:INTEGER) BEGIN x=42 END RNUMREG_RECV')
        self.assertEqual(state['N'],42)

    def test_linked_routines_use_callers_local_and_peer_banks(self):
        sources={'lib':"PROGRAM LIB ROUTINE copy(code:INTEGER) BEGIN RNUMREG_RECV('RC1',1,2,0,code) END copy BEGIN END LIB",
                 'main':"PROGRAM MAIN VAR s:INTEGER ROUTINE copy(code:INTEGER) FROM LIB BEGIN copy(s) END MAIN"}
        ctx=context();instance=translate_project(sources).instantiate(context=ctx);instance.run('MAIN')
        self.assertEqual((instance.programs['MAIN'].snapshot()['S'],ctx.numeric.read(2)),(0,(0,42)))

    def test_saved_context_retains_local_and_peer_transfers(self):
        ctx=context();execute(' '.join(CALLS.values()),ctx)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';ctx.save(path);restored=rt.ExecutionContext.load(path)
        self.assertEqual(restored.numeric.to_config(),ctx.numeric.to_config())
        self.assertEqual(restored.peers.to_config(),ctx.peers.to_config())
        self.assertEqual(rt.snapshot_value(restored.positions.read(2,1)[1]),rt.snapshot_value(ctx.positions.read(2,1)[1]))

    def test_report_and_value_free_observations(self):
        ctx=context();p,result=compile_program(' '.join(CALLS.values()),context=ctx);p.run()
        self.assertEqual({row['operation'] for row in result.report['service_operations']},set(CALLS))
        self.assertFalse(result.report['remote_transfer_policy']['controller_validated'])
        self.assertEqual(set(result.report['remote_transfer_policy']['procedures']),set(REMOTE_TRANSFERS))
        self.assertEqual({row['operation'] for row in p.service_requests},set(CALLS))
        self.assertNotIn('peer point',repr(p.service_requests))

    def test_fresh_cli_execution_and_saved_banks(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'converted.py';report=Path(folder)/'report.json';state=Path(folder)/'state.json'
            env={**os.environ,'PYTHONPATH':str(ROOT),'KAREL2PY_GUI_TESTS':'0'}
            result=subprocess.run([sys.executable,'-X','utf8','-m','karel2py',str(ROOT/'examples/register_transfers.kl'),'-o',str(output),'--report',str(report)],cwd=folder,capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([sys.executable,'-X','utf8',str(output),'--context',str(ROOT/'examples/register_transfers.services.initial.json'),'--state-out',str(state)],cwd=folder,capture_output=True,text=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(ast.literal_eval(result.stdout),{'STATUS':0})
            saved=json.loads(state.read_text())
            self.assertEqual(saved['numeric']['values']['1'],2.5)
            self.assertEqual(saved['peers']['CELL_A']['numeric']['values']['2'],2.5)
            self.assertEqual(saved['positions']['values']['1:1']['value']['axes'],[1.,2.,3.])
            self.assertIn('remote_transfer_policy',json.loads(report.read_text()))
