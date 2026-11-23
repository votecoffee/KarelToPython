"""Regression coverage for partial TP handle allocations."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner
from tests.test_input_teach_banks import tp_context
from tests.test_input_teach_handle_choices import two_banks
from tests.test_input_teach_headers import prepared_paths
from tests.test_input_teach_tolerance import prepared_run
from tests.test_input_template import prepare


class TeachOpenDiscoveryTests(unittest.TestCase):
    def assert_codes(self, prepared, codes=()):
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], list(codes), report['unresolved'])
        return report

    def test_unknown_program_open_keeps_existing_handle_and_metadata(self):
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,first,s) "
            "OPEN_TPE(tp_name,TPE_RDACC,TPE_NOREJ,extra,s) "
            "GET_POS_FRM(first,1,1,f,t,s) "
            "IF (s=0) AND (f=7) AND (t=8) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'first,extra,s,f,t,good,other:INTEGER tp_name:STRING[36]', context=two_banks(),
        )
        self.assert_codes(prepared)
        self.assertEqual(prepared_paths(prepared), {'TP_NAME':'required','GOOD':'required'})

    def test_open_after_possible_failure_still_succeeds_with_a_bounded_number(self):
        source="""PROGRAM T
VAR name_to_open:STRING[36] h,other_h,new_h,s,good,unused:INTEGER
BEGIN
  OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s)
  OPEN_TPE(name_to_open,TPE_RDACC,TPE_NOREJ,other_h,s)
  OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,new_h,s)
  IF s=0 THEN WRITE(good,':',new_h) ELSE WRITE(unused) ENDIF
END T
"""
        context = two_banks()
        context['variables'] = [
            dict(program='T',path='NAME_TO_OPEN',type=['STRING',36],value='OTHER'),
            dict(program='T',path='GOOD',type=['INTEGER'],value=41),
        ]
        with TemporaryDirectory() as folder:
            doc=prepared_run(Path(folder),source,context)
            prepared=json.loads(doc.read_bytes())['inputs']
            self.assert_codes(prepared)
            self.assertEqual(prepared_paths(prepared), {'NAME_TO_OPEN':'required','GOOD':'required'})
            result=runner.run_document(doc)['results']
            good, handle=result['text_output'].split(':')
            self.assertEqual((int(good),int(handle)),(41,3))

    def test_unknown_mode_contributes_a_possible_position_and_access_failure(self):
        prepared = prepare(
            "h=0 OPEN_TPE('draftTp',access_mode,TPE_NOREJ,h,s) x=GET_POS_TPE(h,1,s).x "
            "IF s=0 THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'h,access_mode,s,good,other:INTEGER x:REAL', context=two_banks(),
        )
        self.assert_codes(prepared, ['position-read'])
        self.assertEqual(prepared_paths(prepared), {
            'ACCESS_MODE':'required','1[group=1]':'conditional','GOOD':'required',
        })

    def test_definitely_invalid_mode_preserves_handle_even_with_unknown_name(self):
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) OPEN_TPE(tp_name,99,TPE_NOREJ,h,bad) "
            "GET_POS_FRM(h,1,1,f,t,s) "
            "IF (bad=2) AND (s=0) AND (f=7) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'h,s,bad,f,t,good,other:INTEGER tp_name:STRING[36]', context=two_banks(),
        )
        self.assert_codes(prepared)
        self.assertEqual(prepared_paths(prepared), {'TP_NAME':'required','GOOD':'required'})

    def test_large_catalog_unknown_target_preserves_old_handle_without_guessing_target(self):
        config=two_banks()
        config['teach_programs']['programs'].update({f'JOB{i}':{} for i in range(9)})
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) "
            "OPEN_TPE(tp_name,TPE_RDACC,TPE_NOREJ,extra,s) "
            "GET_POS_FRM(h,1,1,f,t,s) IF (s=0) AND (f=7) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'h,extra,s,f,t,good,other:INTEGER tp_name:STRING[36]', context=config,
        )
        self.assert_codes(prepared, ['teach-handle'])
        self.assertEqual(prepared_paths(prepared), {'TP_NAME':'required','GOOD':'required'})
        self.assertIn('program is unresolved',prepared['template']['discovery']['unresolved'][0]['message'])

    def test_many_conditional_allocations_keep_a_definitely_open_handle(self):
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) "
            "FOR i=1 TO 9 DO OPEN_TPE(tp_name,TPE_RDACC,TPE_NOREJ,extra,s) ENDFOR "
            "GET_POS_FRM(h,1,1,f,t,s) IF (s=0) AND (f=7) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'h,extra,s,f,t,i,good,other:INTEGER tp_name:STRING[36]', context=two_banks(),
        )
        report = self.assert_codes(prepared, ['teach-handle'])
        self.assertIn('allocation number is unresolved', report['unresolved'][0]['message'])
        self.assertEqual(prepared_paths(prepared), {'TP_NAME':'required','GOOD':'required'})

    def test_name_capacity_can_rule_out_any_successful_open(self):
        prepared = prepare(
            "h=77 OPEN_TPE(tp_name,TPE_RDACC,TPE_NOREJ,h,s) "
            "IF h=77 THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'h,s,good,other:INTEGER tp_name:STRING[1]', context=tp_context(),
        )
        self.assert_codes(prepared)
        self.assertEqual(prepared_paths(prepared), {'TP_NAME':'required','GOOD':'required'})
