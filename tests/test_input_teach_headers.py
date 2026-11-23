"""Portable TP header provenance and scoped catalog uncertainty."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner, translate
from karel2py.project_run import create_project_document
from tests.test_input_teach_banks import tp_context
from tests.test_input_teach_tolerance import prepared_run
from tests.test_input_template import prepare


def prepared_paths(prepared):
    return {item['path']: item['certainty'] for item in prepared['template']['discovery']['inputs']}


class TeachHeaderDiscoveryTests(unittest.TestCase):
    def assert_gaps(self, prepared, codes=()):
        report = prepared['template']['discovery']
        self.assertEqual([gap['code'] for gap in report['unresolved']], list(codes), report['unresolved'])

    def test_copy_captures_tp_header_edits_and_later_source_edits_are_independent(self):
        context = tp_context()
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_PROTECT': 2}
        prepared = prepare(
            "SET_ATTR_PRG('draftTp',AT_OWNER,0,'Operator9',s) "
            "SET_ATTR_PRG('draftTp',AT_COMMENT,0,'before',s) "
            "SET_ATTR_PRG('draftTp',AT_SRC_NAME,0,'source',s) "
            "SET_ATTR_PRG('draftTp',AT_SRC_VRSN,12,'',s) "
            "COPY_TPE('draftTp','copyTp',FALSE,s) "
            "SET_ATTR_PRG('draftTp',AT_COMMENT,0,'after',s) "
            "GET_ATTR_PRG('copyTp',AT_OWNER,n,owner,s) GET_ATTR_PRG('copyTp',AT_COMMENT,n,comment,s) "
            "GET_ATTR_PRG('copyTp',AT_SRC_NAME,n,source_name,s) GET_ATTR_PRG('copyTp',AT_SRC_VRSN,v,owner,s) "
            "GET_ATTR_PRG('copyTp',AT_PROTECT,protected,owner,s) "
            "GET_ATTR_PRG('copyTp',AT_PROG_SIZE,n,owner,missing) "
            "IF (s=0) AND (missing=3) AND (protected=2) AND (v=12) AND (owner='Operator') "
            "AND (comment='before') AND (source_name='source') THEN WRITE(good) ELSE WRITE(other) ENDIF",
            ('n,v,s,protected,missing,good,other:INTEGER '
             'owner:STRING[8] comment:STRING[16] source_name:STRING[32]'), context=context,
        )
        self.assert_gaps(prepared)
        self.assertEqual(prepared_paths(prepared), {'GOOD': 'required'})

    def test_saved_header_edit_binds_original_before_two_copies_and_refreshes_branch(self):
        source = """PROGRAM T
VAR s,n,yes_value,no_value:INTEGER
    text:STRING[16]
BEGIN
  COPY_TPE('draftTp','first',FALSE,s)
  COPY_TPE('first','second',FALSE,s)
  GET_ATTR_PRG('second',AT_COMMENT,n,text,s)
  IF text='new' THEN WRITE(yes_value) ELSE WRITE(no_value) ENDIF
END T
"""
        context = tp_context()
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_COMMENT': 'old'}
        context['variables'] = [
            {'program': 'T', 'path': 'YES_VALUE', 'type': ['INTEGER'], 'value': 15},
            {'program': 'T', 'path': 'NO_VALUE', 'type': ['INTEGER'], 'value': 91},
        ]
        with TemporaryDirectory() as folder:
            target = prepared_run(Path(folder), source, context)
            original = target.read_bytes()
            inputs = json.loads(original)['inputs']
            self.assert_gaps(inputs)
            self.assertEqual(prepared_paths(inputs), {'AT_COMMENT': 'required', 'NO_VALUE': 'required'})
            binding = next(row for row in inputs['template']['bindings'] if row['kind'] == 'teach_program_attribute')
            self.assertEqual(binding['context_pointer'], '/teach_programs/programs/draftTp/attributes/AT_COMMENT')
            updated, rev = runner.save_input_value(
                target, ('teach_program_attribute', 'DRAFTTP', 'AT_COMMENT'), 'STRING', 'new', expected=original)
            self.assertEqual(prepared_paths(updated['inputs']), {'AT_COMMENT': 'required', 'YES_VALUE': 'required'})
            replay = runner.run_document(target, expected=rev)['results']
            self.assertEqual(int(replay['text_output']), 15)
            self.assertEqual(replay['context']['teach_programs']['programs']['SECOND']['attributes']['AT_COMMENT'], 'new')

    def test_metadata_overlay_stays_with_external_record_and_takes_precedence_at_destination(self):
        context = tp_context()
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_OWNER': 'physical', 'AT_COMMENT': 'from bank'}
        context['program_attributes'] = {
            'DRAFTTP': {'attributes': {'AT_OWNER': 'overlay'}},
            'CLONE': {'attributes': {'AT_COMMENT': 'target overlay'}},
        }
        prepared = prepare(
            "SET_ATTR_PRG('draftTp',AT_OWNER,0,'edited',s) "
            "COPY_TPE('draftTp','clone',FALSE,s) "
            "GET_ATTR_PRG('draftTp',AT_OWNER,n,old_owner,s) "
            "GET_ATTR_PRG('clone',AT_OWNER,n,copied_owner,s) "
            "GET_ATTR_PRG('clone',AT_COMMENT,n,comment,s) "
            "IF (old_owner='edited') AND (copied_owner='physical') AND (comment='target overlay') "
            "THEN WRITE(good) ELSE WRITE(other) ENDIF",
            's,n,good,other:INTEGER old_owner,copied_owner:STRING[8] comment:STRING[16]', context=context,
        )
        self.assert_gaps(prepared)
        self.assertEqual(prepared_paths(prepared), {'AT_OWNER': 'required', 'GOOD': 'required'})
        binding = next(row for row in prepared['template']['bindings'] if row['kind']=='teach_program_attribute')
        self.assertEqual(binding['context_pointer'], '/teach_programs/programs/draftTp/attributes/AT_OWNER')

    def test_maybe_written_header_remains_a_conditional_input_after_copy(self):
        context = tp_context()
        prepared = prepare(
            "IF option THEN SET_ATTR_PRG('draftTp',AT_SRC_VRSN,8,'',s) ENDIF "
            "COPY_TPE('draftTp','second',FALSE,s) "
            "GET_ATTR_PRG('second',AT_SRC_VRSN,n,text,s) "
            "IF n=8 THEN WRITE(good) ELSE WRITE(other) ENDIF",
            's,n,good,other:INTEGER text:STRING[16] option:BOOLEAN', context=context,
        )
        self.assert_gaps(prepared)
        self.assertEqual(prepared_paths(prepared), {
            'OPTION': 'required', 'AT_SRC_VRSN': 'conditional', 'GOOD': 'conditional', 'OTHER': 'conditional',
        })

    def test_unknown_source_taints_only_the_named_copy_destination(self):
        context = tp_context(numeric={'1': 31})
        context['teach_programs'].pop('selected')
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_COMMENT':'saved'}
        prepared = prepare(
            "COPY_TPE(dynamic_name,'OTHER',TRUE,s) GET_ATTR_PRG('OTHER',AT_COMMENT,n,maybe,s) "
            "GET_ATTR_PRG('draftTp',AT_COMMENT,n,label,s) GET_TPE_REG(1,flag,n,r,s) "
            "IF (s=0) AND (label='saved') AND (NOT flag) THEN WRITE(n,good) ELSE WRITE(other) ENDIF",
            ('s,n,good,other:INTEGER flag:BOOLEAN r:REAL '
             'label,maybe:STRING[16] dynamic_name:STRING[36]'), context=context,
        )
        self.assert_gaps(prepared, ['teach-catalog', 'program-catalog'])
        self.assertEqual(prepared_paths(prepared), {
            'DYNAMIC_NAME':'required', 'AT_COMMENT':'required', '1':'required', 'GOOD':'required',
        })

    def test_unknown_create_name_preserves_existing_records_and_open_handles(self):
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) "
            "CREATE_TPE(dynamic_name,PT_MNE_JOB,s) "
            "cursor=0 PROG_LIST('*',2,0,1,names,count,list_status,cursor) "
            "CLOSE_TPE(h,s) IF s=0 THEN WRITE(good) ELSE WRITE(other) ENDIF",
            ('s,h,count,list_status,cursor,good,other:INTEGER '
             'names:ARRAY[4] OF STRING[32] dynamic_name:STRING[36]'), context=tp_context(),
        )
        self.assert_gaps(prepared, ['teach-catalog', 'program-catalog'])
        self.assertEqual(prepared_paths(prepared), {'DYNAMIC_NAME':'required', 'GOOD':'required'})

    def test_dynamic_non_overwrite_does_not_discard_original_programs(self):
        prepared = prepare(
            "COPY_TPE('draftTp',unknown_target,FALSE,s) "
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) "
            "IF (s=0) AND (h=1) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'unknown_target:STRING[36] h,s,good,other:INTEGER', context=tp_context(),
        )
        self.assert_gaps(prepared, ['teach-catalog'])
        self.assertEqual(prepared_paths(prepared), {'UNKNOWN_TARGET':'required', 'GOOD':'required'})

    def test_exact_listing_ignores_unknown_additions_and_preserves_cursor(self):
        prepared = prepare(
            "CREATE_TPE(unknown_target,PT_MNE_JOB,s) cursor=0 "
            "PROG_LIST('draftTp',2,0,1,names,count,s,cursor) "
            "IF (s=0) AND (cursor=1) AND (count=1) AND (names[1]='DRAFTTP') "
            "THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'unknown_target:STRING[36] names:ARRAY[4] OF STRING[32] s,cursor,count,good,other:INTEGER',
            context=tp_context(),
        )
        self.assert_gaps(prepared, ['teach-catalog'])
        self.assertEqual(prepared_paths(prepared), {'UNKNOWN_TARGET':'required', 'GOOD':'required'})

    def test_dynamic_selection_keeps_possible_header_edit_local_to_that_field(self):
        context = tp_context(numeric={'1': 31})
        context['teach_programs']['programs']['draftTp']['attributes'] = {'AT_OWNER': 'saved'}
        prepared = prepare(
            "SELECT_TPE(unknown_target,s) SET_ATTR_PRG('draftTp',AT_COMMENT,0,'edited',s) "
            "GET_ATTR_PRG('draftTp',AT_COMMENT,n,comment,s) GET_ATTR_PRG('draftTp',AT_OWNER,n,owner,s) "
            "IF owner='saved' THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'unknown_target:STRING[36] s,n,good,other:INTEGER comment:STRING[16] owner:STRING[8]',
            context=context,
        )
        self.assert_gaps(prepared, ['teach-catalog'])
        self.assertEqual(prepared_paths(prepared), {
            'UNKNOWN_TARGET':'required', 'AT_COMMENT':'conditional', 'AT_OWNER':'required','GOOD':'required',
        })

    def test_linked_child_header_write_is_copied_after_its_pause(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            main, child = root/'main.py', root/'child.py'
            main.write_bytes(translate("""PROGRAM MAIN
VAR s,n,good,other:INTEGER label:STRING[16]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  COPY_TPE('draftTp','clone',FALSE,s)
  GET_ATTR_PRG('clone',AT_COMMENT,n,label,s)
  IF label='child wrote' THEN WRITE(good) ELSE WRITE(other) ENDIF
END MAIN
""",cooperative=True).python_source.encode('utf-8'))
            child.write_bytes(translate("""PROGRAM CHILD
VAR s:INTEGER
BEGIN
  SET_ATTR_PRG('draftTp',AT_COMMENT,0,'child wrote',s)
  PAUSE
END CHILD
""",cooperative=True).python_source.encode('utf-8'))
            context=tp_context()
            context['variables']=[dict(program='MAIN',path='GOOD',type=['INTEGER'],value=33)]
            document=root/'linked.run.json'
            prepared=create_project_document([main,child],document,entry='MAIN',context=context,discover=True)
            self.assert_gaps(prepared['inputs'], ['task-scheduling', 'task-wait'])
            self.assertEqual(prepared_paths(prepared['inputs']), {'GOOD':'required'})
            self.assertEqual(int(runner.run_document(document)['results']['text_output']),33)
