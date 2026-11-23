"""Read-before-write regressions for portable TP program and comment changes."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner
from karel2py.storage import typed_value
from tests.test_extended_services import pose
from tests.test_input_teach_banks import tp_context
from tests.test_input_teach_tolerance import prepared_run
from tests.test_input_template import prepare


def saved_position(number, *, group=2, x=5):
    return {'group': group, 'number': number, 'value': typed_value(pose(x))}


class TeachCatalogDiscoveryTests(unittest.TestCase):
    def paths(self, prepared, expected, codes=()):
        report = prepared['template']['discovery']
        self.assertCountEqual([row['path'] for row in report['inputs']], expected)
        self.assertEqual([row['code'] for row in report['unresolved']], list(codes), report['unresolved'])
        return report

    def test_create_open_allocate_and_comment_a_new_position(self):
        prepared = prepare(
            "CREATE_TPE('newTp',PT_MNE_JOB,s) LOAD_STATUS('newTp',loaded,initial) "
            "SELECT_TPE('newTp',selected) OPEN_TPE('newTp',TPE_RWACC,TPE_ALLREJ,h,s) "
            "AVL_POS_NUM(h,n,s) CNV_STR_CONF('N',cfg,s) p=POS(9,0,0,0,0,0,cfg) "
            "SET_POS_TPE(h,n,p,s) SET_TPE_CMT(h,n,'12345678901234567',truncated) "
            "GET_TPE_CMT(h,n,text,s) LOAD_STATUS('newTp',loaded,ready) "
            "GET_ATTR_PRG('newTp',AT_PROG_TYPE,kind,label,s) "
            "IF loaded AND (NOT initial) AND ready AND (n=1) AND (selected=0) AND (truncated=7) "
            "AND (text='1234567890123456') AND (kind=PT_MNE_JOB) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            decl=('h,n,s,kind,truncated,selected,good,other:INTEGER loaded,initial,ready:BOOLEAN '
                  'cfg:CONFIG p:XYZWPR text,label:STRING[16]'),
            context=tp_context(),
        )
        self.paths(prepared, ['GOOD'])

    def test_copy_before_source_mutation_preserves_position_and_comment_snapshot(self):
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RWACC,TPE_NOREJ,h,s) "
            "CNV_STR_CONF('N',cfg,s) p=POS(7,0,0,0,0,0,cfg) SET_POS_TPE(h,1,p,s,2) "
            "SET_TPE_CMT(h,1,'first',s) CLOSE_TPE(h,s) COPY_TPE('draftTp','clone',FALSE,s) "
            "OPEN_TPE('draftTp',TPE_RWACC,TPE_NOREJ,h,s) p.x=9 SET_POS_TPE(h,1,p,s,2) "
            "SET_TPE_CMT(h,1,'second',s) CLOSE_TPE(h,s) "
            "OPEN_TPE('clone',TPE_RDACC,TPE_NOREJ,h,s) GET_TPE_CMT(h,1,text,s) "
            "IF (text='first') AND (GET_POS_TPE(h,1,s,2).x=7.0) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            decl='h,s,good,other:INTEGER cfg:CONFIG p:XYZWPR text:STRING[16]',
            context=tp_context(),
        )
        self.paths(prepared, ['GOOD'])

    def test_copy_overwrites_local_bank_facts_but_keeps_its_caller_binding(self):
        context = tp_context(numeric={'1': 9}, registers=[saved_position(2, x=9)])
        context['teach_programs']['programs']['srcTp'] = {
            'numeric_registers': {'1': 2}, 'position_registers': [saved_position(2, x=7)],
        }
        prepared = prepare(
            "SET_INT_TPE_REG(1,99,s) COPY_TPE('srcTp','draftTp',TRUE,s) "
            "GET_TPE_REG(1,is_real,n,r,s) WRITE(n,GET_TPE_POS_REG(2,s,2).x)",
            decl='s,n:INTEGER r:REAL is_real:BOOLEAN', context=context,
        )
        self.paths(prepared, ['1', '2[group=2]'])
        self.assertEqual(
            {row['context_pointer'] for row in prepared['template']['bindings']},
            {'/teach_programs/programs/srcTp/numeric_registers/1',
             '/teach_programs/programs/srcTp/position_registers/0/value'},
        )

    def test_saved_comment_edit_targets_copy_source_without_creating_clone_row(self):
        source = """PROGRAM T
VAR h,s,good,other:INTEGER
    text:STRING[4]
BEGIN
  COPY_TPE('draftTp','clone',FALSE,s)
  OPEN_TPE('clone',TPE_RDACC,TPE_NOREJ,h,s)
  GET_TPE_CMT(h,1,text,s)
  IF s=8 THEN WRITE(other) ELSE WRITE(text,':',good) ENDIF
END T
"""
        context = tp_context(positions=[saved_position(1)])
        context['teach_programs']['programs']['draftTp']['comments'] = {'1': 'long comment'}
        context['variables'] = [
            {'program': 'T', 'path': 'GOOD', 'type': ['INTEGER'], 'value': 87},
            {'program': 'T', 'path': 'OTHER', 'type': ['INTEGER'], 'value': 98},
        ]
        with TemporaryDirectory() as temp:
            path = prepared_run(Path(temp), source, context)
            before = path.read_bytes()
            inputs = json.loads(before)['inputs']
            self.paths(inputs, ['1', 'OTHER'])
            binding = next(item for item in inputs['template']['bindings'] if item['kind'] == 'teach_position_comment')
            self.assertEqual(binding['context_pointer'], '/teach_programs/programs/draftTp/comments/1')
            saved, revision = runner.save_input_value(
                path, ('teach_position_comment', 'DRAFTTP', '1'), 'STRING', 'edit', expected=before)
            self.paths(saved['inputs'], ['1', 'GOOD'])
            self.assertNotIn('CLONE', saved['inputs']['context']['teach_programs']['programs'])
            result = runner.run_document(path, expected=revision)
            text, value = result['results']['text_output'].split(':')
            self.assertEqual((text, int(value)), ('edit', 87))
            self.assertEqual(result['results']['context']['teach_programs']['programs']['CLONE']['comments']['1'], 'edit')

    def test_missing_saved_comment_can_be_supplied_before_the_first_run(self):
        source = ('PROGRAM T VAR h,s:INTEGER text:STRING[16] BEGIN '
                  "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) GET_TPE_CMT(h,1,text,s) WRITE(text) END T")
        with TemporaryDirectory() as temp:
            path = prepared_run(Path(temp), source, tp_context(positions=[saved_position(1)]))
            before = path.read_bytes()
            binding = json.loads(before)['inputs']['template']['bindings'][0]
            self.assertEqual((binding['status'], binding['context_pointer']),
                             ('missing', '/teach_programs/programs/draftTp/comments/1'))
            saved, revision = runner.save_input_value(
                path, ('teach_position_comment', 'DRAFTTP', '1'), 'STRING', 'new comment', expected=before)
            self.assertEqual(saved['inputs']['template']['bindings'][0]['status'], 'supplied')
            self.assertEqual(runner.run_document(path, expected=revision)['results']['text_output'], 'new comment')

    def test_create_and_copy_failures_leave_the_saved_catalog_unchanged(self):
        context = tp_context()
        teach = context['teach_programs']
        teach.update(program_limit=3, selected='other')
        teach['programs']['guarded'] = {'attributes': {'AT_PROTECT': 2}}
        prepared = prepare(
            "CREATE_TPE('draftTp',PT_MNE_JOB,duplicate) CREATE_TPE('later',PT_MNE_JOB,full) "
            "COPY_TPE('missing','later',FALSE,absent) COPY_TPE('draftTp','other',TRUE,selected) "
            "COPY_TPE('draftTp','guarded',TRUE,protected) "
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) COPY_TPE('draftTp','later',FALSE,busy) "
            "IF (duplicate=5) AND (full=6) AND (absent=1) AND (selected=4) AND (protected=4) "
            "AND (busy=4) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            decl='duplicate,full,absent,selected,protected,busy,h,s,good,other:INTEGER', context=context,
        )
        self.paths(prepared, ['GOOD'])

    def test_copy_dependency_capacity_is_checked_before_publication(self):
        context = tp_context()
        context['teach_programs'].update(program_limit=3, calls={'DraftTp': ['A'], 'x': ['B'], 'y': ['C']})
        prepared = prepare(
            "COPY_TPE('draftTp','clone',FALSE,s) OPEN_TPE('clone',TPE_RDACC,TPE_NOREJ,h,check) "
            "IF (s=6) AND (check=1) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            decl='s,h,check,good,other:INTEGER', context=context,
        )
        self.paths(prepared, ['GOOD'])

    def test_instruction_deletion_changes_count_and_preserves_copy_snapshot(self):
        context = tp_context()
        context['teach_programs']['programs']['draftTp']['instructions'] = ['one', 'two', 'three']
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RWACC,TPE_NOREJ,h,s) DEL_INST_TPE(h,1,s) CLOSE_TPE(h,s) "
            "COPY_TPE('draftTp','clone',FALSE,s) OPEN_TPE('clone',TPE_RWACC,TPE_NOREJ,h,s) "
            "DEL_INST_TPE(h,1,s) DEL_INST_TPE(h,9,invalid) "
            "GET_ATTR_PRG('draftTp',AT_NUM_LINE,original_count,label,s) "
            "GET_ATTR_PRG('clone',AT_NUM_LINE,cloned_count,label,s) "
            "IF (original_count=2) AND (cloned_count=1) AND (invalid=2) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            decl='h,s,original_count,cloned_count,invalid,good,other:INTEGER label:STRING[16]', context=context,
        )
        self.paths(prepared, ['GOOD'])

    def test_created_program_missing_row_cannot_be_seeded_as_saved_input(self):
        prepared = prepare(
            "CREATE_TPE('clone',PT_MNE_JOB,s) OPEN_TPE('clone',TPE_RDACC,TPE_NOREJ,h,s) "
            "WRITE(GET_POS_TPE(h,1,s).x,unreachable)",
            decl='h,s,unreachable:INTEGER', context=tp_context(),
        )
        self.paths(prepared, [], ['position-read'])

    def test_dynamic_copy_target_keeps_open_and_getter_unresolved(self):
        prepared = prepare(
            "COPY_TPE('draftTp',target,FALSE,s) OPEN_TPE('clone',TPE_RDACC,TPE_NOREJ,h,s) WRITE(GET_POS_TPE(h,1,s).x)",
            decl='target:STRING[36] s,h:INTEGER', context=tp_context(),
        )
        self.paths(prepared, ['TARGET', 'H'], ['teach-catalog', 'position-read', 'teach-position'])

    def test_static_catalog_listing_includes_new_programs(self):
        prepared = prepare(
            "CREATE_TPE('made',PT_MNE_JOB,s) PROG_LIST('made',3,0,1,names,count,s) "
            "IF (s=0) AND (count=1) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            decl='names:ARRAY[4] OF STRING[32] count,s,good,other:INTEGER', context=tp_context(),
        )
        self.paths(prepared, ['GOOD'])
