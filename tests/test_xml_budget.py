"""Budget and publication checks for offline XML FILE operations."""
import unittest
from unittest.mock import patch

from karel2py import fileops, runtime as rt, xmlio
from tests.test_extended_services import compile_program
from tests.test_xml_input import ADD, DATA, DECL, OPEN, SCAN, context


LARGE_XML = b'<item>' + b' ' * 8193 + b'</item>'


class XMLBudgetTests(unittest.TestCase):
    def test_oversized_xml_rejects_without_snapshot_or_parser(self):
        ctx = context(b' ' * (xmlio.XML_BYTE_LIMIT + 1))
        task, _ = compile_program(OPEN + SCAN, decl=DECL, context=ctx)
        with patch.object(xmlio.expat, 'ParserCreate') as parser:
            result = task.run(max_steps=3)
        parser.assert_not_called()
        self.assertEqual((result['S'], result['IDENT']), (5, -1))
        session = task._state.values['F'].xml_session
        self.assertIsNone(session.raw)
        self.assertIsNone(session.events)
        self.assertEqual(list(session.line_starts), [0])

    def test_snapshot_budget_failure_preserves_registration_and_status(self):
        ctx = context(LARGE_XML)
        task, _ = compile_program(OPEN + 's=77 ' + ADD, decl=DECL, context=ctx)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'):
            task.run(max_steps=5)
        handle = task._state.values['F']
        self.assertIsNone(handle.xml_session)
        self.assertEqual((task.snapshot()['S'], handle.position, handle.status), (77, 0, 0))
        self.assertEqual(ctx.files.files['input.xml'], LARGE_XML)

    def test_existing_session_charges_comparison_before_getdata(self):
        ctx = context(LARGE_XML)
        task, _ = compile_program(
            OPEN + ADD + SCAN + "n=99 text='old' done=TRUE s=77 PAUSE " + DATA,
            decl=DECL, context=ctx,
        )
        with self.assertRaises(rt.KarelPause):
            task.run()
        handle = task._state.values['F']
        session = handle.xml_session
        position = handle.position
        charge = fileops.charge_file_bytes

        def limit(size, check):
            self.assertEqual(size, len(LARGE_XML))
            task._state.max_steps = task._state.steps + 1
            charge(size, check)

        with patch.object(fileops, 'charge_file_bytes', side_effect=limit):
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'step budget'):
                task.resume()
        result = task.snapshot()
        self.assertEqual((result['N'], result['TEXT'], result['DONE'], result['S']), (99, 'old', True, 77))
        self.assertEqual((handle.position, session.current['offset']), (position, 0))
        self.assertFalse(session.active)

    def test_scan_checks_same_size_edits_and_replaced_buffers_before_publication(self):
        for replacement in (False, True):
            with self.subTest(replacement=replacement):
                ctx = context(b'<item n="42"/>')
                task, _ = compile_program(
                    OPEN + ADD + "tag='old' ident=8 code=9 s=77 " + SCAN, decl=DECL, context=ctx,
                )
                tick = task._state.tick
                active_ticks = []

                def change(*args, **kwargs):
                    tick(*args, **kwargs)
                    session = task._state.values['F'].xml_session
                    if session is not None and session.active:
                        active_ticks.append(1)
                        if len(active_ticks) == 3:
                            if replacement:
                                ctx.files.files['input.xml'] = bytearray(session.raw)
                            else:
                                ctx.files.files['input.xml'][:] = b'<item n="99"/>'

                with patch.object(task._state, 'tick', side_effect=change):
                    with self.assertRaisesRegex(rt.KarelRuntimeError, 'XML input changed'):
                        task.run()
                result = task.snapshot()
                self.assertEqual((result['TAG'], result['IDENT'], result['CODE'], result['S']), ('old', 8, 9, 77))
                handle = task._state.values['F']
                self.assertEqual(handle.position, 0)
                self.assertIsNone(handle.xml_session.events)
                self.assertIsNone(handle.xml_session.current)
                self.assertFalse(handle.xml_session.active)

    def test_setvar_checks_source_after_staging_before_status_and_record_writes(self):
        ctx = context(b'<item number="42"/>')
        task, _ = compile_program(
            OPEN + ADD + SCAN + "item.number=99 s=77 PAUSE XML_SETVAR(f,'','item',s)",
            prefix='TYPE item_t=STRUCTURE number:INTEGER ENDSTRUCTURE',
            decl=DECL + ' item:item_t', context=ctx,
        )
        with self.assertRaises(rt.KarelPause):
            task.run()
        session = task._state.values['F'].xml_session
        tick = task._state.tick
        active_ticks = []

        def change(*args, **kwargs):
            tick(*args, **kwargs)
            if session.active:
                active_ticks.append(1)
                if len(active_ticks) == 3:
                    ctx.files.files['input.xml'][:] = b'<item number="43"/>'

        with patch.object(task._state, 'tick', side_effect=change):
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'XML input changed'):
                task.resume()
        self.assertEqual((task.snapshot()['ITEM']['NUMBER'], task.snapshot()['S']), (99, 77))
        self.assertFalse(session.active)


if __name__ == '__main__':
    unittest.main()
