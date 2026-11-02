"""Authored Boolean/integer simulation flags with exact output contracts."""
import json
import unittest

from karel2py import runtime as rt
from karel2py import extended as ex
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program


def context(simulated=False):
    return rt.ExecutionContext(ports=rt.PortBank({'DIN':2},{('DIN',1):False},type_codes={10:'DIN'},simulated=[('DIN',1)] if simulated else []))


def run(body,decl='flag:BOOLEAN n,s:INTEGER',ctx=None,**options):
    p,r=compile_program(body,decl=decl,context=context() if ctx is None else ctx,**options);return p.run(),p,r


class PortSimulationFlagTests(unittest.TestCase):
    def test_boolean_false_is_exact_boolean(self):
        v,_,_=run('GET_PORT_SIM(10,1,flag,s)');self.assertIs(v['FLAG'],False);self.assertEqual(v['S'],0)
    def test_boolean_true_is_exact_boolean(self):
        v,_,_=run('GET_PORT_SIM(10,1,flag,s)',ctx=context(True));self.assertIs(v['FLAG'],True)
    def test_integer_output_remains_compatible(self):
        for simulated in (False,True):
            v,_,_=run('GET_PORT_SIM(10,1,n,s)',ctx=context(simulated));self.assertIs(type(v['N']),int);self.assertEqual(v['N'],int(simulated))
    def test_set_and_clear_share_simulation_state(self):
        v,p,_=run('SET_PORT_SIM(10,1,TRUE,s) GET_PORT_SIM(10,1,flag,s) CLR_PORT_SIM(10,1,s) GET_PORT_SIM(10,1,n,s)');self.assertEqual((v['FLAG'],v['N'],p._state.execution.ports.read('DIN',1)),(True,0,True))
    def test_missing_value_still_has_simulation_flag(self):
        v,_,_=run('GET_PORT_SIM(10,2,flag,s)');self.assertEqual((v['FLAG'],v['S']),(False,0))
    def test_invalid_address_preserves_data(self):
        v,_,_=run('flag=TRUE GET_PORT_SIM(10,9,flag,s)');self.assertEqual((v['FLAG'],v['S']),(True,2))
    def test_unmapped_type_preserves_data(self):
        v,_,_=run('flag=TRUE GET_PORT_SIM(99,1,flag,s)');self.assertEqual((v['FLAG'],v['S']),(True,2))
    def test_boolean_array_and_field_outputs(self):
        v,_,_=run('GET_PORT_SIM(10,1,a[2],s) GET_PORT_SIM(10,1,rec.flag,s)',decl='a:ARRAY[2]OF BOOLEAN rec:item_t s:INTEGER',prefix='TYPE item_t=STRUCTURE flag:BOOLEAN ENDSTRUCTURE');self.assertIs(v['A'][1],False);self.assertIs(v['REC']['FLAG'],False)
    def test_boolean_alias_is_resolved(self):
        v,_,_=run('GET_PORT_SIM(10,1,flag,s)',prefix='TYPE flag_t=BOOLEAN',decl='flag:flag_t s:INTEGER');self.assertIs(v['FLAG'],False)
    def test_selector_effects_run_once_in_source_order(self):
        routines='ROUTINE first:INTEGER BEGIN n=n*10+1 RETURN 10 END first ROUTINE second:INTEGER BEGIN n=n*10+2 RETURN 1 END second ROUTINE target:INTEGER BEGIN n=n*10+3 RETURN 1 END target'
        v,_,_=run('n=0 GET_PORT_SIM(first(),second(),a[target()],s)',decl='n,s:INTEGER a:ARRAY[2]OF BOOLEAN',routines=routines);self.assertEqual((v['N'],v['A'][0]),(123,False))
    def test_integer_output_cannot_overlap_status(self):
        p,_=compile_program('n=7 GET_PORT_SIM(10,1,n,n)',decl='n:INTEGER',context=context())
        with self.assertRaisesRegex(rt.KarelRuntimeError,'overlap'):p.run()
        self.assertEqual(p.snapshot()['N'],7)
    def test_nonexact_output_types_are_rejected(self):
        for kind in ('BYTE','SHORT','REAL','STRING[8]'):
            with self.subTest(kind=kind),self.assertRaises(TranslationError):compile_program('GET_PORT_SIM(10,1,flag,s)',decl='flag:'+kind+' s:INTEGER')
    def test_literal_and_grouped_outputs_are_rejected(self):
        for target in ('TRUE','(flag)'):
            with self.subTest(target=target),self.assertRaises(TranslationError):compile_program('GET_PORT_SIM(10,1,'+target+',s)',decl='flag:BOOLEAN s:INTEGER')
    def test_runtime_readonly_output_is_rejected(self):
        values=dict(flag=True,status=7);flag=rt.ReadOnlyFieldReference(('BOOLEAN',),values,'flag');status=rt.Reference(('INTEGER',),values,'status')
        with self.assertRaises(rt.KarelRuntimeError):ex.outputs_checked(ex.PROCEDURES['GET_PORT_SIM'],[10,1,flag,status])
        self.assertEqual(values,dict(flag=True,status=7))
    def test_context_roundtrip_retains_simulation(self):
        ctx=rt.ExecutionContext.from_config(json.loads(json.dumps(context(True).to_config())));v,_,_=run('GET_PORT_SIM(10,1,flag,s)',ctx=ctx);self.assertIs(v['FLAG'],True)
    def test_bank_is_not_mutated_by_query(self):
        ctx=context(True);before=ctx.to_config();run('GET_PORT_SIM(10,1,flag,s)',ctx=ctx);self.assertEqual(ctx.ports.snapshot(),{('DIN',1):False});self.assertEqual(ctx.to_config()['ports'],before['ports'])
    def test_report_describes_both_output_types(self):
        _,_,r=run('GET_PORT_SIM(10,1,flag,s)');self.assertIn('BOOLEAN or exact INTEGER',r.report['io_parameter_policy']['conversions'])
