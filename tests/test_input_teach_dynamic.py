"""Bounded discovery for dynamic TP header and catalog operands."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner
from tests.test_input_teach_banks import tp_context
from tests.test_input_teach_headers import prepared_paths
from tests.test_input_teach_tolerance import prepared_run
from tests.test_input_template import prepare


class DynamicTeachDiscoveryTests(unittest.TestCase):
    def assert_inputs(self, prepared, expected, unresolved=()):
        report = prepared['template']['discovery']
        self.assertEqual([item['code'] for item in report['unresolved']], list(unresolved), report['unresolved'])
        self.assertEqual(prepared_paths(prepared), expected)

    def test_bounded_text_selector_leaves_integer_receiver_unchanged(self):
        context = tp_context()
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_COMMENT': 'comment', 'AT_OWNER': 'owner'}
        prepared = prepare(
            "n=42 IF option THEN key=AT_OWNER ELSE key=AT_COMMENT ENDIF "
            "sel=key GET_ATTR_PRG('draftTp',sel,n,text,s) "
            "IF (s=0) AND (n=42) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'option:BOOLEAN key,sel,n,s,good,other:INTEGER text:STRING[16]', context=context,
        )
        self.assert_inputs(prepared, {
            'OPTION': 'required', 'AT_COMMENT': 'conditional', 'AT_OWNER': 'conditional', 'GOOD': 'required',
        })

    def test_unbounded_selector_lists_possible_writable_headers(self):
        prepared = prepare(
            "GET_ATTR_PRG('draftTp',key,n,text,s) IF s=0 THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'key,n,s,good,other:INTEGER text:STRING[16]', context=tp_context(),
        )
        self.assert_inputs(prepared, {
            'KEY': 'required', 'AT_COMMENT': 'conditional', 'AT_OWNER': 'conditional',
            'AT_SRC_NAME': 'conditional', 'AT_SRC_VRSN': 'conditional', 'GOOD': 'conditional', 'OTHER': 'conditional',
        })

    def test_known_invalid_selector_sets_status_without_resolving_dynamic_program_name(self):
        prepared = prepare(
            "n=18 text='old' GET_ATTR_PRG(dynamic_name,0,n,text,s) "
            "IF (s=2) AND (n=18) AND (text='old') THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'dynamic_name:STRING[36] text:STRING[8] n,s,good,other:INTEGER', context=tp_context(),
        )
        self.assert_inputs(prepared, {'DYNAMIC_NAME': 'required', 'GOOD': 'required'})

    def test_setter_commits_only_possible_headers_before_copy(self):
        context = tp_context()
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_SRC_VRSN': 38}
        prepared = prepare(
            "IF option THEN key=AT_OWNER ELSE key=AT_COMMENT ENDIF "
            "SET_ATTR_PRG('draftTp',key,0,'changed',s) COPY_TPE('draftTp','clone',FALSE,copied) "
            "GET_ATTR_PRG('clone',AT_SRC_VRSN,v,text,checked) "
            "IF (s=0) AND (copied=0) AND (checked=0) AND (v=38) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'option:BOOLEAN key,s,v,copied,checked,good,other:INTEGER text:STRING[16]', context=context,
        )
        self.assert_inputs(prepared, {'OPTION': 'required', 'AT_SRC_VRSN': 'required', 'GOOD': 'required'})

    def test_unbounded_setter_preserves_copy_data_and_reports_possible_prior_header(self):
        context = tp_context(numeric={'1': 31})
        prepared = prepare(
            "SET_ATTR_PRG('draftTp',key,9,'changed',s) "
            "GET_ATTR_PRG('draftTp',AT_OWNER,n,text,s) GET_TPE_REG(1,flag,n,r,s) "
            "IF (s=0) AND (NOT flag) THEN WRITE(n,good) ELSE WRITE(other) ENDIF",
            'key,n,s,good,other:INTEGER flag:BOOLEAN r:REAL text:STRING[8]', context=context,
        )
        self.assert_inputs(prepared, {
            'KEY': 'required', 'AT_OWNER': 'conditional', '1': 'required', 'GOOD': 'required',
        })

    def test_bounded_copy_destinations_prove_success_without_changing_source(self):
        context = tp_context()
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_OWNER': 'source'}
        prepared = prepare(
            "IF option THEN target='one' ELSE target='two' ENDIF "
            "COPY_TPE('draftTp',target,FALSE,copied) GET_ATTR_PRG('draftTp',AT_OWNER,n,text,s) "
            "IF (copied=0) AND (text='source') THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'option:BOOLEAN target:STRING[36] copied,s,n,good,other:INTEGER text:STRING[8]', context=context,
        )
        self.assert_inputs(prepared, {'OPTION': 'required', 'AT_OWNER': 'required', 'GOOD': 'required'})

    def test_finite_program_names_find_each_saved_bank_read(self):
        context = tp_context()
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_OWNER': 'same'}
        context['teach_programs']['programs']['OTHER']['attributes'] = {'AT_OWNER': 'same'}
        prepared = prepare(
            "IF option THEN target='draftTp' ELSE target='other' ENDIF "
            "GET_ATTR_PRG(target,AT_OWNER,n,text,s) "
            "IF (s=0) AND (text='same') THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'option:BOOLEAN target:STRING[36] s,n,good,other:INTEGER text:STRING[8]', context=context,
        )
        self.assert_inputs(prepared, {'OPTION': 'required', 'AT_OWNER': 'conditional', 'GOOD':'required'})
        rows = prepared['template']['bindings']
        self.assertEqual({item['context_pointer'] for item in rows if item['path']=='AT_OWNER'}, {
            '/teach_programs/programs/draftTp/attributes/AT_OWNER',
            '/teach_programs/programs/OTHER/attributes/AT_OWNER',
        })

    def test_dynamic_overwrite_preserves_source_protected_selected_and_open_destinations(self):
        context = tp_context()
        context['teach_programs']['programs'].update(
            Locked={'attributes': {'AT_PROTECT': 2}}, Opened={}, Maybe={},
        )
        prepared = prepare(
            "OPEN_TPE('Opened',TPE_RDACC,TPE_NOREJ,h,s) COPY_TPE('draftTp',target,TRUE,copied) "
            "GET_ATTR_PRG('Maybe',AT_COMMENT,n,text,maybe_status) "
            "GET_ATTR_PRG('Locked',AT_PROTECT,protection,text,protected_status) "
            "GET_ATTR_PRG('Opened',AT_PROG_NAME,n,open_name,open_status) "
            "GET_ATTR_PRG('OTHER',AT_PROG_NAME,n,selected_name,selected_status) "
            "GET_ATTR_PRG('draftTp',AT_PROG_NAME,n,source_name,source_status) CLOSE_TPE(h,s) "
            "IF (s=0) AND (protection=2) AND (protected_status=0) AND (open_status=0) "
            "AND (selected_status=0) AND (source_status=0) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            ('target:STRING[36] text,open_name,selected_name,source_name:STRING[16] '
             'h,n,s,copied,maybe_status,protection,protected_status,open_status,selected_status,source_status,good,other:INTEGER'),
            context=context,
        )
        self.assert_inputs(prepared, {'TARGET': 'required', 'GOOD': 'required'}, ['teach-catalog', 'program-catalog'])

    def test_unbounded_overwrite_in_full_catalog_cannot_add_new_program(self):
        context = tp_context()
        context['teach_programs']['program_limit'] = 2
        prepared = prepare(
            "COPY_TPE('draftTp',target,TRUE,s) OPEN_TPE('missing',TPE_RDACC,TPE_NOREJ,h,missing_status) "
            "IF missing_status=1 THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'target:STRING[36] h,s,missing_status,good,other:INTEGER', context=context,
        )
        self.assert_inputs(prepared, {'TARGET': 'required', 'GOOD': 'required'}, ['teach-catalog'])

    def test_routine_result_choices_feed_header_selector_and_pin_replay(self):
        source = """PROGRAM T
VAR p:BOOLEAN n,s:INTEGER text:STRING[16]
ROUTINE choose(option:BOOLEAN):INTEGER
BEGIN
  IF option THEN RETURN AT_OWNER ELSE RETURN AT_COMMENT ENDIF
END choose
BEGIN
  n=17
  GET_ATTR_PRG('draftTp',choose(p),n,text,s)
  WRITE(text,':',n)
END T
"""
        context = tp_context()
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_COMMENT':'comment', 'AT_OWNER':'owner'}
        context['variables'] = [{'program':'T','path':'P','type':['BOOLEAN'],'value':False}]
        with TemporaryDirectory() as temp:
            document = prepared_run(Path(temp), source, context)
            stored = json.loads(document.read_bytes())
            self.assert_inputs(stored['inputs'], {
                'P': 'required', 'AT_OWNER': 'conditional', 'AT_COMMENT': 'conditional',
            })
            replay = runner.run_document(document)['results']
            selected, number = replay['text_output'].split(':')
            self.assertEqual((selected, int(number)), ('comment', 17))
