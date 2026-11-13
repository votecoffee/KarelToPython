"""Authored captured-data recovery and all-window display publication checks."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from karel2py import runtime as rt
from tests.test_dynamic_display import CHOICES,DECL,SETUP,call,context,execute,line
from tests.test_extended_services import compile_program


def last(ctx):return ctx.dynamic_display.snapshot()['bindings'][0]['last_status']


class CapturedDisplayDataTests(unittest.TestCase):
    def poll(self,ctx,text,status):
        self.assertEqual(ctx.dynamic_display.advance(0,force=True),1)
        self.assertEqual((line(ctx)[:6],last(ctx)),(text,status))

    def test_missing_scalar_cell_is_invalid_until_restored(self):
        _,ctx,p,_=execute(SETUP+'n=7 '+call())
        del p._state.values['N']
        self.poll(ctx,'??????',4)
        p._state.values['N']=9
        self.poll(ctx,'9     ',0)

    def test_removed_indexed_cell_is_invalid_until_restored(self):
        _,ctx,p,_=execute(SETUP+'numbers[2]=7 '+call(variable='numbers[2]'),decl=DECL+' numbers:ARRAY[2]OF INTEGER')
        data=p._state.values['NUMBERS'].values
        self.assertEqual(data.pop(),7)
        self.poll(ctx,'??????',4)
        data.append(8)
        self.poll(ctx,'8     ',0)

    def test_reference_retarget_does_not_redirect_poll(self):
        for attribute,changed in (('storage',{'N':42}),('key','S'),('spec','REAL')):
            with self.subTest(attribute=attribute):
                _,ctx,_,_=execute(SETUP+'n=7 '+call())
                reference=ctx.dynamic_display._bindings[0]['reference']
                original=getattr(reference,attribute);setattr(reference,attribute,changed)
                self.poll(ctx,'??????',4)
                setattr(reference,attribute,original)
                self.poll(ctx,'7     ',0)

    def test_invalid_scalar_values_are_question_marks(self):
        cases=(('I','N',True),('I','N',1.5),('R','R',float('nan')),('S','LABEL','x'*21),('S','LABEL',b'bytes'),('S','LABEL','\x01'))
        for kind,key,value in cases:
            with self.subTest(kind=kind,value=value):
                _,ctx,p,_=execute(SETUP+call(kind))
                p._state.values[key]=value
                self.poll(ctx,'??????',4)

    def test_missing_sentinels_remain_unknown(self):
        for value in (rt.UNINITIALIZED,rt.UNKNOWN_BYTE):
            with self.subTest(value=value):
                _,ctx,p,_=execute(SETUP+'n=7 '+call())
                p._state.values['N']=value
                self.poll(ctx,'******',1)
                p._state.set('N',11)
                self.poll(ctx,'11    ',0)

    def test_oversized_scalar_string_recovers_after_source_assignment(self):
        _,ctx,p,_=execute(SETUP+"label='old' "+call('S'))
        p._state.values['LABEL']='x'*21
        self.poll(ctx,'??????',4)
        p._state.set('LABEL','ready')
        self.poll(ctx,'ready ',0)

    def test_whole_missing_labels_can_register_and_recover(self):
        for kind,assignment in (('B','b=TRUE '),('E','e=1 '),('P','')):
            with self.subTest(kind=kind):
                ctx=context()
                if kind=='P':ctx.ports=rt.PortBank({'DIN':1},{('DIN',1):True},type_codes={1:'DIN'})
                p,_=compile_program(SETUP+assignment+call(kind),decl=DECL,context=ctx)
                labels=p._state.values['CHOICES'];p._state.values['CHOICES']=rt.UNINITIALIZED
                self.assertEqual(p.run()['S'],0)
                self.assertEqual((line(ctx)[:6],last(ctx)),('******',1))
                labels.values[:]=['OFF','ON','OTHER'];p._state.values['CHOICES']=labels
                self.poll(ctx,'ON    ',0)

    def test_boolean_still_requires_two_declared_labels(self):
        ctx=context()
        p,_=compile_program(SETUP+'b=TRUE '+call('B'),decl=DECL.replace('ARRAY[3]','ARRAY[1]'),context=ctx)
        p._state.values['CHOICES']=rt.UNINITIALIZED
        self.assertEqual(p.run()['S'],1)
        self.assertEqual((ctx.dynamic_display.active_count,line(ctx)),(0,' '*20))

    def test_missing_label_binding_is_invalid_until_restored(self):
        _,ctx,p,_=execute(SETUP+CHOICES+'b=TRUE '+call('B'))
        labels=p._state.values.pop('CHOICES')
        self.poll(ctx,'??????',4)
        p._state.values['CHOICES']=labels
        self.poll(ctx,'ON    ',0)

    def test_label_reference_retarget_is_invalid(self):
        for attribute,changed in (('storage',{}),('key','N'),('spec',('ARRAY',3,('STRING',13)))):
            with self.subTest(attribute=attribute):
                _,ctx,_,_=execute(SETUP+CHOICES+'b=TRUE '+call('B'))
                reference=ctx.dynamic_display._bindings[0]['labels'];original=getattr(reference,attribute)
                setattr(reference,attribute,changed)
                self.poll(ctx,'??????',4)
                setattr(reference,attribute,original)
                self.poll(ctx,'ON    ',0)

    def test_malformed_label_array_layouts_are_invalid(self):
        for attribute,value in (('shape',(1,3)),('values',['OFF','ON']),('values',('OFF','ON','OTHER')),('spec',('ARRAY',3,('STRING',13)))):
            with self.subTest(attribute=attribute,value=value):
                _,ctx,p,_=execute(SETUP+CHOICES+'b=TRUE '+call('B'))
                labels=p._state.values['CHOICES'];original=getattr(labels,attribute)
                setattr(labels,attribute,value)
                self.poll(ctx,'??????',4)
                setattr(labels,attribute,original)
                self.poll(ctx,'ON    ',0)

    def test_non_array_label_value_is_invalid(self):
        _,ctx,p,_=execute(SETUP+CHOICES+'b=TRUE '+call('B'))
        p._state.values['CHOICES']=['OFF','ON','OTHER']
        self.poll(ctx,'??????',4)

    def test_invalid_selected_label_and_missing_label_differ(self):
        _,ctx,p,_=execute(SETUP+CHOICES+'b=TRUE '+call('B'))
        labels=p._state.values['CHOICES'].values
        for value in ('x'*13,'\x00',42,rt.UNINITIALIZED):
            with self.subTest(value=value):
                labels[1]=value
                self.poll(ctx,'******' if value is rt.UNINITIALIZED else '??????',1 if value is rt.UNINITIALIZED else 4)
        labels[1]='ON'
        self.poll(ctx,'ON    ',0)

    def test_invalid_enum_index_precedes_whole_missing_labels(self):
        _,ctx,p,_=execute(SETUP+CHOICES+'e=1 '+call('E'))
        p._state.values['CHOICES']=rt.UNINITIALIZED;p._state.set('E',3)
        self.poll(ctx,'??????',2)

    def test_prefix_labels_detect_resize_and_keep_original_cells(self):
        body=SETUP+"labels[2,1]='OFF' labels[2,2]='ON' b=TRUE "+call('B').replace('choices','labels[2]')
        _,ctx,p,_=execute(body,decl=DECL+' labels:ARRAY[2,2]OF STRING[12]')
        labels=p._state.values['LABELS'];original=labels.values
        tail=original.pop();self.poll(ctx,'??????',4)
        original.append(tail);self.poll(ctx,'ON    ',0)
        labels.values=[rt.UNINITIALIZED]*4
        original[-1]='kept';self.poll(ctx,'kept  ',0)

    def test_port_poll_errors_become_invalid_data(self):
        ctx=context();ctx.ports=rt.PortBank({'DIN':1},{('DIN',1):True},type_codes={1:'DIN'})
        execute(SETUP+CHOICES+call('P'),ctx=ctx)
        with patch.object(ctx.ports,'poll_pulses',side_effect=rt.KarelRuntimeError('unavailable clock')):
            self.poll(ctx,'??????',4)
        self.poll(ctx,'ON    ',0)


class DisplayPublicationTests(unittest.TestCase):
    def pair(self,*,pause=False):
        ctx=context(cancel_on_interrupt=pause)
        body=SETUP+"DEF_WINDOW('W2',3,20,0,s) n=7 "+call()+call(window='W2')+('PAUSE' if pause else '')
        p,_=compile_program(body,decl=DECL,context=ctx)
        if pause:
            with self.assertRaises(rt.KarelPause):p.run()
        else:p.run()
        return ctx,p

    def assert_failed_poll_preserves(self,ctx):
        display=ctx.dynamic_display.snapshot();pendant=ctx.pendant.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):ctx.dynamic_display.advance(10,force=True)
        self.assertEqual(ctx.dynamic_display.snapshot(),display)
        self.assertEqual(ctx.pendant.snapshot(),pendant)

    def test_later_window_bounds_failure_does_not_paint_earlier_window(self):
        ctx,p=self.pair();p._state.set('N',9)
        ctx.pendant.windows['W2']['cols']=5;ctx.pendant.windows['W2']['lines']=[' '*5]*3
        self.assert_failed_poll_preserves(ctx)

    def test_malformed_later_window_storage_does_not_paint_earlier_window(self):
        for attribute,value in (('rows',True),('rows',0),('cols','20'),('lines',[]),('lines',[' '*20]*2),('lines',[' '*19]*3),('lines',['\x00'+' '*19]*3),('lines',None)):
            with self.subTest(attribute=attribute,value=value):
                ctx,p=self.pair();p._state.set('N',9)
                ctx.pendant.windows['W2'][attribute]=value
                self.assert_failed_poll_preserves(ctx)

    def test_non_dictionary_later_surface_does_not_paint_earlier_window(self):
        ctx,p=self.pair();p._state.set('N',9)
        ctx.pendant.windows['W2']=None
        self.assert_failed_poll_preserves(ctx)

    def test_missing_later_window_does_not_paint_earlier_window(self):
        ctx,p=self.pair();p._state.set('N',9)
        del ctx.pendant.windows['W2']
        self.assert_failed_poll_preserves(ctx)

    def test_repaired_surface_can_retry_same_due_poll(self):
        ctx,p=self.pair();p._state.set('N',9)
        original=ctx.pendant.windows['W2'];ctx.pendant.windows['W2']=None
        self.assert_failed_poll_preserves(ctx)
        ctx.pendant.windows['W2']=original
        elapsed=ctx.dynamic_display.elapsed_ms
        self.assertEqual(ctx.dynamic_display.advance(10,force=True),2)
        self.assertEqual(ctx.dynamic_display.elapsed_ms,elapsed+10)
        self.assertEqual([ctx.pendant.windows[w]['lines'][0][:6] for w in ('W1','W2')],['9     ']*2)
        self.assertEqual([b['last_status'] for b in ctx.dynamic_display.snapshot()['bindings']],[0,0])

    def test_background_failure_only_advances_clock_and_failure_status(self):
        ctx,p=self.pair();p._state.set('N',9)
        original=ctx.pendant.windows.pop('W2')
        before=ctx.pendant.snapshot();bindings=ctx.dynamic_display.snapshot()['bindings'];elapsed=ctx.dynamic_display.elapsed_ms
        ctx.dynamic_display.checkpoint(p._state)
        self.assertEqual(ctx.pendant.snapshot(),before)
        self.assertEqual(ctx.dynamic_display.elapsed_ms,elapsed+1)
        for binding,previous in zip(ctx.dynamic_display.snapshot()['bindings'],bindings):
            self.assertEqual(binding,dict(previous,last_status=5))
        ctx.pendant.windows['W2']=original
        self.assertEqual(ctx.dynamic_display.close_all(),0)

    def test_ordinary_cancel_preflights_every_window(self):
        ctx,_=self.pair();original=ctx.pendant.windows.pop('W2')
        before=ctx.pendant.snapshot();display=ctx.dynamic_display.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):ctx.dynamic_display.close_all()
        self.assertEqual(ctx.pendant.snapshot(),before)
        self.assertEqual(ctx.dynamic_display.snapshot(),display)
        ctx.pendant.windows['W2']=original
        self.assertEqual(ctx.dynamic_display.close_all(),0)
        self.assertEqual([ctx.pendant.windows[w]['lines'][0][:6] for w in ('W1','W2')],[' '*6]*2)
        restored=rt.ExecutionContext.from_config(json.loads(json.dumps(ctx.to_config())))
        self.assertEqual(restored.to_config(),ctx.to_config())

    def test_interrupted_cleanup_releases_bindings_with_invalid_surface(self):
        ctx,p=self.pair(pause=True)
        ctx.pendant.windows['W2']['lines']=[]
        p.stop()
        self.assertEqual((ctx.dynamic_display.active_count,line(ctx)[:6]),(0,' '*6))

    def test_cleanup_at_sequence_exhaustion_preflights_surface(self):
        ctx,_=self.pair();ctx.pendant.sequence=2147483646
        original=ctx.pendant.windows['W2']['lines'];ctx.pendant.windows['W2']['lines']=[]
        before=ctx.pendant.snapshot()
        with self.assertRaises(rt.KarelRuntimeError):ctx.dynamic_display.close_all()
        self.assertEqual(ctx.pendant.snapshot(),before)
        ctx.pendant.windows['W2']['lines']=original
        history=deepcopy(ctx.pendant.history)
        self.assertEqual(ctx.dynamic_display.close_all(),0)
        self.assertEqual((ctx.pendant.sequence,ctx.pendant.history),(2147483646,history))

    def test_field_preparation_has_no_publication_effects(self):
        _,ctx,_,_=execute(SETUP)
        before=ctx.pendant.snapshot()
        lines,count=ctx.pendant.prepare_fields('W1',[(1,1,'ready'),(1,3,'X')])
        self.assertEqual((lines,count),(['reXdy'+' '*15,' '*20,' '*20],6))
        self.assertEqual(ctx.pendant.snapshot(),before)
        lines[0]='changed'
        self.assertEqual(ctx.pendant.snapshot(),before)

    def test_invalid_preparation_and_field_limit_preserve_surface(self):
        _,ctx,_,_=execute(SETUP)
        before=ctx.pendant.snapshot()
        for fields in ([(1,1,'x')]*513,[(1,1,'ok'),(4,1,'bad')],[(1,1,'\n')],[(1,1,'x'*21)]):
            with self.subTest(fields=fields):
                with self.assertRaises(rt.KarelRuntimeError):ctx.pendant.prepare_fields('W1',fields)
                self.assertEqual(ctx.pendant.snapshot(),before)

    def test_initiation_rejects_status_retarget_before_paint(self):
        for attribute in ('storage','key','spec'):
            with self.subTest(attribute=attribute):
                ctx=context();p,_=compile_program(SETUP+'n=7 s=23 '+call(),decl=DECL,context=ctx)
                sample=ctx.dynamic_display.sample;captured={};foreign={'S':99}
                def retarget(binding,line=None):
                    value=sample(binding,line)
                    # The call's status is captured by the runtime reference factory.
                    reference=captured['status']
                    setattr(reference,attribute,{'storage':foreign,'key':'N','spec':'REAL'}[attribute])
                    captured['pendant']=ctx.pendant.snapshot()
                    return value
                original=rt.Reference.__init__
                def capture(reference,spec,storage,key):
                    original(reference,spec,storage,key)
                    if storage is p._state.values and key=='S':captured['status']=reference
                with patch.object(rt.Reference,'__init__',capture),patch.object(ctx.dynamic_display,'sample',retarget):
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'status binding changed'):p.run()
                self.assertEqual(ctx.pendant.snapshot(),captured['pendant'])
                self.assertEqual((p._state.values['S'],p._state.values['N'],foreign['S']),(23,7,99))
                self.assertEqual((ctx.dynamic_display.active_count,ctx.dynamic_display.sequence),(0,0))

    def test_initiation_rejects_malformed_surface_before_access(self):
        ctx=context();execute(SETUP,ctx=ctx)
        ctx.pendant.windows['W1']=None;before=ctx.pendant.snapshot()
        p,_=compile_program('n=7 '+call(),decl=DECL,context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'window storage'):p.run()
        self.assertEqual((ctx.dynamic_display.active_count,ctx.dynamic_display.sequence),(0,0))
        self.assertEqual(ctx.pendant.snapshot(),before)

    def test_report_describes_recovery_and_all_window_preflight(self):
        _,result=compile_program(SETUP+'n=7 '+call(),decl=DECL)
        policy=result.report['dynamic_display_policy']
        self.assertIn('captured locations',policy['recovery'])
        self.assertIn('all due windows',policy['publication'])
        self.assertEqual(policy['recovery_ledger'],'docs/semantics/dynamic_display_recovery_semantics.json')
        self.assertFalse(policy['controller_validated'])


if __name__=='__main__':unittest.main()
