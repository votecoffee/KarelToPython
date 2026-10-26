"""Explicit serial attribute metadata, source functions and JSON persistence."""
import json
import unittest

from karel2py import runtime as rt
from karel2py.lexer import TranslationError
from tests.test_extended_services import compile_program,run


class SerialPortTests(unittest.TestCase):
    def test_all_attributes_read_write_and_keep_separate_from_io(self):
        bank=rt.SerialPorts({1:{}});ctx=rt.ExecutionContext(serial_ports=bank)
        for key,value in (('ATR_READAHD',2),('ATR_BAUD',9600),('ATR_PARITY',2),('ATR_SBITS',15),('ATR_DBITS',8),('ATR_XONOFF',1),('ATR_EOL',10)):
            with self.subTest(key=key):
                data=run(f's=SET_PORT_ATR(PORT_1,{key},{value}) s=GET_PORT_ATR(PORT_1,{key},n)',context=ctx)
                self.assertEqual((data['S'],data['N']),(0,value))

    def test_port_ids_and_constants(self):
        ctx=rt.ExecutionContext(serial_ports=rt.SerialPorts({i:{} for i in range(1,6)}))
        for i in range(1,6):self.assertEqual(run(f's=SET_PORT_ATR(PORT_{i},ATR_BAUD,BAUD_4800)',context=ctx)['S'],0)
        data=run('s=SET_PORT_ATR(PORT_1,ATR_PARITY,PARITY_EVEN) s=SET_PORT_ATR(PORT_1,ATR_SBITS,SBITS_15) s=SET_PORT_ATR(PORT_1,ATR_DBITS,DBITS_7) s=SET_PORT_ATR(PORT_1,ATR_XONOFF,XF_USED)',context=ctx)
        self.assertEqual(data['S'],0)

    def test_missing_value_port_and_attribute_preserve_output(self):
        ctx=rt.ExecutionContext(serial_ports=rt.SerialPorts({1:{}}))
        for port,key,code in ((1,'ATR_BAUD',1),(2,'ATR_BAUD',2),(1,'999',3)):
            with self.subTest(port=port,key=key):
                data=run(f'n=77 s=GET_PORT_ATR({port},{key},n)',context=ctx)
                self.assertEqual((data['N'],data['S']),(77,code))

    def test_invalid_values_do_not_replace_prior_attribute(self):
        bank=rt.SerialPorts({1:{'ATR_BAUD':9600}});ctx=rt.ExecutionContext(serial_ports=bank)
        for key,value in (('ATR_BAUD',123),('ATR_PARITY',3),('ATR_SBITS',0),('ATR_DBITS',9),('ATR_XONOFF',2),('ATR_EOL',128),('ATR_READAHD',-1)):
            with self.subTest(key=key):self.assertEqual(run(f's=SET_PORT_ATR(1,{key},{value})',context=ctx)['S'],3)
        self.assertEqual(bank.to_config(),{'1':{'ATR_BAUD':9600}})

    def test_json_roundtrip_and_detached_config(self):
        ctx=rt.ExecutionContext(serial_ports=rt.SerialPorts({1:{'atr_baud':9600},5:{}}))
        config=ctx.to_config();loaded=rt.ExecutionContext.from_config(json.loads(json.dumps(config)))
        self.assertEqual(loaded.to_config(),config)
        config['serial_ports']['1']['ATR_BAUD']=1200;self.assertEqual(ctx.serial_ports.read(1,102),(0,9600))

    def test_bad_configuration_rejected(self):
        for config in ([],{'01':{}},{'6':{}},{'1':[]},{'1':{'BOGUS':1}},{'1':{'ATR_BAUD':True}},{'1':{'ATR_BAUD':1}},{'1':{'ATR_BAUD':9600,'atr_baud':1200}}):
            with self.subTest(config=config),self.assertRaises(ValueError):rt.SerialPorts.from_config(config)
        with self.assertRaises(TypeError):rt.ExecutionContext(serial_ports={})

    def test_missing_service_does_not_publish_outputs(self):
        p,_=compile_program('n=7 s=99 s=GET_PORT_ATR(1,ATR_BAUD,n)')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'serial_ports'):p.run()
        self.assertEqual((p.snapshot()['N'],p.snapshot()['S']),(7,99))

    def test_types_arity_and_counter_protection(self):
        for call in ('s=SET_PORT_ATR(1,ATR_BAUD,TRUE)','s=GET_PORT_ATR(1,ATR_BAUD,7)','s=GET_PORT_ATR(1,ATR_BAUD)'):
            with self.subTest(call=call),self.assertRaises(TranslationError):compile_program(call)
        with self.assertRaises(TranslationError) as caught:compile_program('FOR n=1 TO 2 DO s=GET_PORT_ATR(1,ATR_BAUD,n) ENDFOR')
        self.assertEqual(caught.exception.code,'E_FOR_COUNTER')

    def test_user_routine_precedence(self):
        self.assertEqual(run('s=GET_PORT_ATR(7)',routines='ROUTINE GET_PORT_ATR(n: INTEGER): INTEGER BEGIN RETURN n END GET_PORT_ATR')['S'],7)


if __name__=='__main__':unittest.main()
