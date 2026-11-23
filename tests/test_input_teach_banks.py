"""Regression coverage for editable TP register and program-position inputs."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner
from karel2py.storage import typed_value
from tests.test_extended_services import pose
from tests.test_input_teach_tolerance import prepared_run, teach_context
from tests.test_input_template import prepare


OPEN = "OPEN_TPE('DRAFTTP',TPE_RWACC,TPE_NOREJ,h,s) "
NUMERIC_DECL = 'n,s,good,other:INTEGER r:REAL is_real:BOOLEAN'


def tp_context(*, numeric=None, strings=None, positions=(), registers=()):
    result = teach_context(rows=registers)
    bank = result['teach_programs']
    bank.update(register_limit=3, string_register_limit=3, string_capacity=5, position_limit=6)
    row = bank['programs']['draftTp']
    row.update(numeric_registers=numeric or {}, string_registers=strings or {}, positions=list(positions))
    return result


class TeachBankDiscoveryTests(unittest.TestCase):
    def assert_paths(self, prepared, paths, codes=()):
        discovery = prepared['template']['discovery']
        self.assertEqual([item['code'] for item in discovery['unresolved']], list(codes), discovery['unresolved'])
        self.assertCountEqual([item['path'] for item in discovery['inputs']], paths)

    def test_scalar_setters_leave_the_inactive_numeric_output_and_clip_strings(self):
        prepared = prepare(
            "r=99.0 SET_INT_TPE_REG(1,5,s) GET_TPE_REG(1,is_real,n,r,s) "
            "IF (NOT is_real) AND (s=0) AND (n=5) AND (r=99.0) THEN "
            "SET_REAL_TPE_REG(1,8,s) GET_TPE_REG(1,is_real,n,r,s) ENDIF "
            "SET_TPE_STR_REG(1,'abcdefgh',s) GET_TPE_STR_REG(1,text,s) "
            "GET_TPE_STR_REG(1,short_text,overflow) "
            "IF is_real AND (n=5) AND (r=8.0) AND (text='abcde') AND (overflow=8) "
            "THEN WRITE(good) ELSE WRITE(other) ENDIF",
            decl=NUMERIC_DECL+' overflow:INTEGER text:STRING[5] short_text:STRING[4]',
            context=tp_context(),
        )
        self.assert_paths(prepared, ['GOOD'])

    def test_editing_numeric_kind_rediscovers_the_active_branch(self):
        source = ("PROGRAM T VAR "+NUMERIC_DECL+" BEGIN GET_TPE_REG(1,is_real,n,r,s) "
                  "IF is_real THEN WRITE(r,':',other) ELSE WRITE(n,':',good) ENDIF END T")
        initial = tp_context(numeric={'1': 7})
        initial['variables'] = [
            {'program': 'T', 'path': 'GOOD', 'type': ['INTEGER'], 'value': 11},
            {'program': 'T', 'path': 'OTHER', 'type': ['INTEGER'], 'value': 22},
        ]
        with TemporaryDirectory() as temp:
            path = prepared_run(Path(temp), source, initial)
            before = path.read_bytes()
            inputs = json.loads(before)['inputs']
            self.assert_paths(inputs, ['1', 'GOOD'])
            binding = next(row for row in inputs['template']['bindings'] if row['path'] == '1')
            self.assertEqual(binding['context_pointer'], '/teach_programs/programs/draftTp/numeric_registers/1')
            updated, revision = runner.save_input_value(
                path, ('teach_numeric_register', 'DRAFTTP', '1'), 'REAL', '3.5', expected=before)
            self.assert_paths(updated['inputs'], ['1', 'OTHER'])
            result = runner.run_document(path, expected=revision)
            real, other = result['results']['text_output'].split(':')
            self.assertEqual((float(real), int(other)), (3.5, 22))

    def test_editing_saved_string_rediscovery_recovers_a_capacity_failure(self):
        source = (
            "PROGRAM T VAR text:STRING[3] s,good,other:INTEGER BEGIN text='old' GET_TPE_STR_REG(1,text,s) "
            "IF s=8 THEN WRITE(text,':',other) ELSE WRITE(text,':',good) ENDIF END T"
        )
        context = tp_context(strings={'1': 'large'})
        context['variables'] = [
            {'program': 'T', 'path': 'GOOD', 'type': ['INTEGER'], 'value': 55},
            {'program': 'T', 'path': 'OTHER', 'type': ['INTEGER'], 'value': 66},
        ]
        with TemporaryDirectory() as temp:
            path = prepared_run(Path(temp), source, context)
            before = path.read_bytes()
            self.assert_paths(json.loads(before)['inputs'], ['1', 'OTHER'])
            updated, revision = runner.save_input_value(
                path, ('teach_string_register', 'DRAFTTP', '1'), 'STRING', 'new', expected=before)
            self.assert_paths(updated['inputs'], ['1', 'GOOD'])
            result = runner.run_document(path, expected=revision)
            text, good = result['results']['text_output'].split(':')
            self.assertEqual((text, int(good)), ('new', 55))

    def test_missing_register_can_be_created_at_the_physical_tp_address(self):
        source = 'PROGRAM T VAR n,s:INTEGER r:REAL is_real:BOOLEAN BEGIN GET_TPE_REG(3,is_real,n,r,s) WRITE(n) END T'
        with TemporaryDirectory() as temp:
            path = prepared_run(Path(temp), source, tp_context())
            before = path.read_bytes()
            bound = json.loads(before)['inputs']['template']['bindings'][0]
            self.assertEqual((bound['status'], bound['context_pointer']),
                             ('missing', '/teach_programs/programs/draftTp/numeric_registers/3'))
            updated, revision = runner.save_input_value(
                path, ('teach_numeric_register', 'DRAFTTP', '3'), 'INTEGER', '86', expected=before)
            self.assert_paths(updated['inputs'], ['3'])
            self.assertEqual(runner.run_document(path, expected=revision)['results']['text_output'].strip(), '86')

    def test_failed_numeric_read_preserves_outputs_when_address_is_invalid(self):
        prepared = prepare(
            'n=7 r=8.0 is_real=FALSE GET_TPE_REG(4,is_real,n,r,s) '
            'IF (s=2) AND (n=7) AND (r=8.0) AND (NOT is_real) THEN WRITE(good) ELSE WRITE(other) ENDIF',
            decl=NUMERIC_DECL, context=tp_context(),
        )
        self.assert_paths(prepared, ['GOOD'])

    def test_merged_numeric_types_keep_both_preexisting_receivers_possible(self):
        prepared = prepare(
            'n=7 r=8.0 IF pick THEN SET_INT_TPE_REG(1,7,s) ELSE SET_REAL_TPE_REG(1,8.0,s) ENDIF '
            'GET_TPE_REG(1,is_real,n,r,s) IF (s=0) AND is_real THEN WRITE(good) ELSE WRITE(other) ENDIF',
            decl=NUMERIC_DECL+' pick:BOOLEAN', context=tp_context(),
        )
        self.assert_paths(prepared, ['PICK', 'GOOD', 'OTHER'])

    def test_position_writes_preserve_frames_and_separate_the_two_tp_banks(self):
        saved = {'group': 2, 'number': 1, 'uframe': 7, 'utool': 8, 'value': typed_value(pose(3))}
        prepared = prepare(
            OPEN+
            "CNV_STR_CONF('N',cfg,s) p=POS(40,0,0,0,0,0,cfg,1,2,3) "
            "SET_POS_TPE(h,1,p,s) SET_EPOS_TPE(h,2,p,s,2) SET_TRNS_TPE(h,3,p,s) "
            "j[1]=7.0 j[2]=8.0 SET_JPOS_TPE(h,4,j,s) SET_TPE_EPOS_REG(1,p,s) "
            "GET_POS_FRM(h,1,2,f,t,s) GET_POS_TYP(h,3,2,k,a,s) "
            "IF (s=0) AND (f=7) AND (t=8) AND (k=1) AND (a=0) "
            "AND (GET_POS_TPE(h,1,s).ext1=0.0) AND (GET_POS_TPE(h,2,s,2).ext3=3.0) "
            "AND (GET_JPOS_TPE(h,4,s)[9]=0.0) AND (GET_TPE_POS_REG(1,s).ext1=1.0) "
            "THEN WRITE(good) ELSE WRITE(other) ENDIF",
            prefix='%DEFGROUP=2\n',
            decl='cfg:CONFIG p:XYZWPREXT j:JOINTPOS2 h,s,f,t,k,a,good,other:INTEGER',
            context=tp_context(positions=[saved]),
        )
        self.assert_paths(prepared, ['GOOD'])

    def test_closed_and_read_only_handles_preserve_failed_outputs(self):
        prepared = prepare(
            "OPEN_TPE('does_not_exist',TPE_RDACC,TPE_NOREJ,h,missing) "
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) "
            "CNV_STR_CONF('N',cfg,s) p=POS(4,0,0,0,0,0,cfg) SET_POS_TPE(h,1,p,readonly) "
            "CLOSE_TPE(h,s) OPEN_TPE('draftTp',0,TPE_NOREJ,second,s) "
            "f=7 t=8 GET_POS_FRM(h,1,1,f,t,closed) GET_POS_FRM(second,1,1,f,t,inactive) "
            "IF (h=1) AND (second=2) AND (missing=1) AND (readonly=3) AND (closed=3) "
            "AND (inactive=3) AND (f=7) AND (t=8) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            decl='cfg:CONFIG p:XYZWPR h,s,f,t,missing,readonly,closed,inactive,second,good,other:INTEGER',
            context=tp_context(),
        )
        self.assert_paths(prepared, ['GOOD'])

    def test_position_allocation_uses_every_group_and_preserves_the_receiver_when_full(self):
        row = {'group': 2, 'number': 1, 'value': typed_value(pose(5))}
        context = tp_context(positions=[row])
        context['teach_programs']['position_limit'] = 2
        prepared = prepare(
            OPEN+
            "AVL_POS_NUM(h,n,s) CNV_STR_CONF('N',cfg,s) p=POS(4,0,0,0,0,0,cfg) SET_POS_TPE(h,n,p,s) "
            "AVL_POS_NUM(h,n,s) IF (n=2) AND (s=6) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            decl='h,n,s,good,other:INTEGER cfg:CONFIG p:XYZWPR', context=context,
        )
        self.assert_paths(prepared, ['GOOD'])

    def test_unknown_name_lists_only_saved_programs_as_possible_open_targets(self):
        prepared = prepare(
            'OPEN_TPE(program_name,TPE_RDACC,TPE_NOREJ,h,s) WRITE(GET_POS_TPE(h,1,s).x)',
            decl='program_name:STRING[36] h,s:INTEGER', context=tp_context(),
        )
        report = prepared['template']['discovery']
        self.assertEqual([row['code'] for row in report['unresolved']], ['position-read'])
        self.assertCountEqual([(row['program'], row['path']) for row in report['inputs']], [
            ('T','PROGRAM_NAME'), ('T','H'), ('DRAFTTP','1[group=1]'), ('OTHER','1[group=1]'),
        ])
        self.assertTrue(all(row['certainty'] == 'conditional' for row in report['inputs']
                            if row['kind'] == 'teach_program_position'))

    def test_definite_handle_failure_stops_a_function_read(self):
        prepared = prepare(OPEN+'CLOSE_TPE(h,s) WRITE(GET_POS_TPE(h,1,s).x,unreachable)',
                           decl='h,s,unreachable:INTEGER', context=tp_context())
        self.assert_paths(prepared, [], ['position-read'])

    def test_missing_program_position_is_editable_even_with_same_number_in_caller_bank(self):
        source = ('PROGRAM T VAR h,s:INTEGER BEGIN '+OPEN+
                  'WRITE(GET_JPOS_TPE(h,1,s,2)[2]) CLOSE_TPE(h,s) END T')
        local = {'group': 2, 'number': 1, 'value': typed_value(pose(5))}
        with TemporaryDirectory() as temp:
            path = prepared_run(Path(temp), source, tp_context(registers=[local]))
            before = path.read_bytes()
            inputs = json.loads(before)['inputs']
            bound = inputs['template']['bindings'][0]
            self.assertEqual((bound['status'], bound['context_pointer']),
                             ('missing', '/teach_programs/programs/draftTp/positions/0/value'))
            updated, revision = runner.save_input_structure(
                path, ('teach_program_position', 'DRAFTTP', '1[group=2]'),
                {'axes': [0.0, 44.0]+[0.0]*7}, expected=before,
            )
            saved = updated['inputs']['context']['teach_programs']['programs']['draftTp']
            self.assertEqual(saved['position_registers'], [local])
            result = runner.run_document(path, expected=revision)
            self.assertEqual(float(result['results']['text_output'].strip()), 44.0)
