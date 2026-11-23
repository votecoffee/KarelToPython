"""Regression coverage for bounded TP handles and bank addresses."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner, translate
from karel2py.project_run import create_project_document
from karel2py.storage import typed_value
from tests.test_extended_services import pose
from tests.test_input_teach_banks import tp_context
from tests.test_input_teach_tolerance import prepared_run
from tests.test_input_template import prepare


def position(number, x, *, group=1, frame=0, tool=0):
    return {'group': group, 'number': number, 'value': typed_value(pose(x)), 'uframe': frame, 'utool': tool}


def two_banks():
    context = tp_context(positions=[position(1, 5, frame=7, tool=8)])
    context['teach_programs']['programs']['OTHER'].update(
        positions=[position(1, 11, frame=7, tool=8)],
        comments={'1': 'other comment'},
    )
    context['teach_programs']['programs']['draftTp']['comments'] = {'1': 'first comment'}
    return context


class BoundedTeachHandleTests(unittest.TestCase):
    def assert_bindings(self, prepared, expected, gaps=()):
        report = prepared['template']['discovery']
        paths = [(row['kind'], row['program'], row['path'], row['certainty']) for row in report['inputs']]
        self.assertCountEqual(paths, expected)
        self.assertEqual([item['code'] for item in report['unresolved']], list(gaps), report['unresolved'])

    def test_open_choice_keeps_both_program_positions_editable(self):
        source = """PROGRAM T
VAR pick:BOOLEAN tp_name:STRING[36] h,after_no,s,f,t:INTEGER
BEGIN
  IF pick THEN tp_name='draftTp' ELSE tp_name='other' ENDIF
  OPEN_TPE(tp_name,TPE_RDACC,TPE_NOREJ,h,s)
  GET_POS_FRM(h,1,1,f,t,s)
  WRITE(GET_POS_TPE(h,1,s).x,':',f,':',t)
  CLOSE_TPE(h,s)
  OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,after_no,s)
END T
"""
        config = two_banks()
        config['variables'] = [{'program':'T','path':'PICK','type':['BOOLEAN'],'value':False}]
        with TemporaryDirectory() as folder:
            document = prepared_run(Path(folder), source, config)
            prepared = json.loads(document.read_bytes())['inputs']
            self.assert_bindings(prepared, [
                ('variable', 'T', 'PICK', 'required'),
                ('teach_program_position', 'DRAFTTP', '1[group=1]', 'conditional'),
                ('teach_program_position', 'OTHER', '1[group=1]', 'conditional'),
            ])
            pointers = {row['context_pointer'] for row in prepared['template']['bindings']
                        if row['kind']=='teach_program_position'}
            self.assertEqual(pointers, {'/teach_programs/programs/draftTp/positions/0/value',
                                        '/teach_programs/programs/OTHER/positions/0/value'})
            result = runner.run_document(document)['results']
            x, f, t = result['text_output'].split(':')
            self.assertEqual((float(x), int(f), int(t)), (11.0, 7, 8))
            self.assertEqual(result['variables']['AFTER_NO'], 2)

    def test_selectable_close_preserves_an_unrelated_handle(self):
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,a,s) OPEN_TPE('other',TPE_RDACC,TPE_NOREJ,b,s) "
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,keep,s) "
            "IF pick THEN h=a ELSE h=b ENDIF CLOSE_TPE(h,closed) "
            "GET_POS_FRM(keep,1,1,f,t,s) "
            "IF (s=0) AND (closed=0) AND (f=7) AND (t=8) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'a,b,keep,h,closed,s,f,t,good,other:INTEGER pick:BOOLEAN', context=two_banks(),
        )
        self.assert_bindings(prepared, [('variable','T','PICK','required'), ('variable','T','GOOD','required')])

    def test_read_only_or_no_access_metadata_failure_keeps_the_output(self):
        prepared = prepare(
            "IF pick THEN mode=TPE_RDACC ELSE mode=0 ENDIF "
            "OPEN_TPE('draftTp',mode,TPE_NOREJ,h,s) f=7 t=8 "
            "GET_POS_FRM(h,1,1,f,t,s) "
            "IF (f=7) AND (t=8) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'mode,h,s,f,t,good,other:INTEGER pick:BOOLEAN', context=two_banks(),
        )
        self.assert_bindings(prepared, [('variable','T','PICK','required'), ('variable','T','GOOD','required')])

    def test_getter_failure_branch_stops_before_later_inputs(self):
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) "
            "IF pick THEN selected=h ELSE selected=0 ENDIF z=GET_POS_TPE(selected,1,s).x "
            "IF s=0 THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'h,selected,s,good,other:INTEGER z:REAL pick:BOOLEAN', context=two_banks(),
        )
        self.assert_bindings(prepared, [
            ('variable','T','PICK','required'),
            ('variable','T','GOOD','required'),
            ('teach_program_position','DRAFTTP','1[group=1]','conditional'),
        ], ['position-read'])

    def test_bounded_group_addresses_report_two_physical_rows(self):
        context = tp_context(registers=[position(1, 5), position(1, 11, group=2)])
        prepared = prepare(
            "IF pick THEN gp=1 ELSE gp=2 ENDIF WRITE(GET_TPE_POS_REG(1,s,gp).x)",
            'gp,s:INTEGER pick:BOOLEAN', context=context,
        )
        self.assert_bindings(prepared, [
            ('variable','T','PICK','required'),
            ('teach_position_register','DRAFTTP','1[group=1]','conditional'),
            ('teach_position_register','DRAFTTP','1[group=2]','conditional'),
        ])

    def test_bounded_register_numbers_keep_each_read_candidate(self):
        prepared = prepare(
            "IF pick THEN addr=1 ELSE addr=2 ENDIF "
            "GET_TPE_REG(addr,flag,n,r,s) IF s=0 THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'addr,n,s,good,other:INTEGER r:REAL pick,flag:BOOLEAN',
            context=tp_context(numeric={'1':4,'2':5.5}),
        )
        self.assert_bindings(prepared, [
            ('variable','T','PICK','required'),
            ('teach_numeric_register','DRAFTTP','1','conditional'),
            ('teach_numeric_register','DRAFTTP','2','conditional'),
            ('variable','T','GOOD','required'),
        ])

    def test_comment_and_allocation_follow_alternate_handles(self):
        prepared = prepare(
            "IF pick THEN tp_name='draftTp' ELSE tp_name='other' ENDIF "
            "OPEN_TPE(tp_name,TPE_RDACC,TPE_NOREJ,h,s) "
            "GET_TPE_CMT(h,1,text,s) AVL_POS_NUM(h,n,s) "
            "IF (s=0) AND (n=2) THEN WRITE(text,good) ELSE WRITE(other) ENDIF",
            'h,n,s,good,other:INTEGER pick:BOOLEAN text:STRING[16] tp_name:STRING[36]', context=two_banks(),
        )
        self.assert_bindings(prepared, [
            ('variable','T','PICK','required'),
            ('teach_position_comment','DRAFTTP','1','conditional'),
            ('teach_position_comment','OTHER','1','conditional'),
            ('variable','T','GOOD','required'),
        ])

    def test_unknown_close_preserves_next_allocation_number(self):
        prepared = prepare(
            "OPEN_TPE('draftTp',TPE_RDACC,TPE_NOREJ,h,s) "
            "CLOSE_TPE(dynamic_h,s) OPEN_TPE('other',TPE_RDACC,TPE_NOREJ,after_no,s) "
            "IF (s=0) AND (after_no=2) THEN WRITE(good) ELSE WRITE(other) ENDIF",
            'h,s,dynamic_h,after_no,good,other:INTEGER', context=two_banks(),
        )
        self.assert_bindings(prepared, [
            ('variable','T','DYNAMIC_H','required'), ('variable','T','GOOD','required'),
        ], ['teach-handle'])

    def test_bounded_ordinary_string_and_position_registers(self):
        config = {
            'strings': {'count':2,'values':{'1':'one','2':'two'}},
            'positions': {'count':2,'groups':[1],'values':{
                '1':typed_value(pose(5)), '2':typed_value(pose(11)),
            }},
        }
        prepared = prepare(
            "IF pick THEN a=1 ELSE a=2 ENDIF GET_STR_REG(a,text,s) "
            "WRITE(text,GET_POS_REG(a,s).x)",
            'a,s:INTEGER pick:BOOLEAN text:STRING[16]', context=config,
        )
        self.assert_bindings(prepared, [
            ('variable','T','PICK','required'),
            ('string_register',None,'1','conditional'),
            ('string_register',None,'2','conditional'),
            ('position_register',None,'1[group=1]','conditional'),
            ('position_register',None,'2[group=1]','conditional'),
        ])

    def test_indirect_port_address_choices_keep_both_input_addresses(self):
        prepared = prepare(
            "IF pick THEN port_code=10 ELSE port_code=20 ENDIF GET_PORT_VAL(port_code,1,text,s)",
            'port_code,s:INTEGER pick:BOOLEAN text:STRING[16]',
            context={'ports': {'counts': {'DIN':1,'AIN':1}, 'type_codes': {'10':'DIN','20':'AIN'}}},
        )
        self.assert_bindings(prepared, [
            ('variable','T','PICK','required'), ('port',None,'DIN[1]','conditional'),
            ('port',None,'AIN[1]','conditional'),
        ])

    def test_possible_busy_handle_does_not_prove_catalog_copy_fails(self):
        prepared = prepare(
            "IF pick THEN tp_name='draftTp' ELSE tp_name='other' ENDIF "
            "OPEN_TPE(tp_name,TPE_RDACC,TPE_NOREJ,h,s) COPY_TPE('draftTp','clone',FALSE,copy_status) "
            "IF copy_status=4 THEN WRITE(busy) ELSE WRITE(unlocked) ENDIF",
            'h,s,copy_status,busy,unlocked:INTEGER pick:BOOLEAN tp_name:STRING[36]', context=two_banks(),
        )
        self.assert_bindings(prepared, [
            ('variable','T','PICK','required'), ('variable','T','BUSY','conditional'),
            ('variable','T','UNLOCKED','conditional'),
        ], ['teach-catalog'])

    def test_linked_child_alternate_reject_banks_keep_possible_parent_register_read(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            main, child = root/'main.py', root/'child.py'
            main.write_bytes(translate("""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  text='prior'
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text)
END MAIN
""",cooperative=True).python_source.encode('utf-8'))
            child.write_bytes(translate("""PROGRAM CHILD
VAR h,s:INTEGER pick:BOOLEAN tp_name:STRING[36]
BEGIN
  IF pick THEN tp_name='draftTp' ELSE tp_name='other' ENDIF
  OPEN_TPE(tp_name,TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
END CHILD
""",cooperative=True).python_source.encode('utf-8'))
            config = tp_context(strings={'1':'ready'})
            config['teach_programs']['callers']['MAIN'] = 'draftTp'
            config['variables'] = [{'program':'CHILD','path':'PICK','type':['BOOLEAN'],'value':False}]
            document = root/'linked.run.json'
            prepared = create_project_document([main,child], document, entry='MAIN', context=config, discover=True)
            self.assert_bindings(prepared['inputs'], [
                ('variable','CHILD','PICK','conditional'),
                ('teach_string_register','DRAFTTP','1','conditional'),
            ], ['task-scheduling','task-wait'])
            result = runner.run_document(document)['results']
            status, text = result['text_output'].split(':')
            self.assertEqual((int(status),text), (0,'ready'))
