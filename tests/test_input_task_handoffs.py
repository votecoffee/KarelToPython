"""Regression coverage for linked pause handoffs and checked child segments."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from karel2py import runner, translate
from karel2py.project_run import create_project_document


class TaskHandoffTests(unittest.TestCase):
    def setUp(self):
        folder=TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)

    def prepare(self, sources, *, replay=True):
        paths=[]
        for name, source in sources:
            path=self.root/(name.lower()+'.py')
            result=translate(source,cooperative=True)
            path.write_bytes(result.python_source.encode('utf-8'))
            paths.append(path)
        document=self.root/'linked.run.json'
        context={'teach_programs':{
            'programs':{'Shared':{'string_registers':{'1':'ready'}}},
            'callers':{'MAIN':'Shared'},
        }}
        saved=create_project_document(paths,document,entry='MAIN',context=context,discover=True)
        result=runner.run_document(document)['results'] if replay else None
        return saved['inputs']['template']['discovery'],result

    def assert_inputs(self, report, expected):
        values=[(row['kind'],row['program'],row['path'],row['certainty']) for row in report['inputs']]
        self.assertCountEqual(values,expected)

    def assert_task_gaps(self, report, expected):
        self.assertEqual([row['code'] for row in report['unresolved']],list(expected),report['unresolved'])

    def test_paused_prefix_is_checked_without_scanning_unreached_tail(self):
        main="""PROGRAM MAIN
VAR s,selected,number:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  selected=2
  number=selected
  WAIT FOR PAUSE PROGRAM[number]
  text='prior'
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text)
END MAIN
"""
        child="""PROGRAM CHILD
VAR s,h,duration,late:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
  DELAY duration
  WRITE(late)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        status,text=result['text_output'].split(':')
        self.assertEqual((int(status),text),(4,'prior'))

    def test_external_synchronous_routine_can_launch_and_wait_with_local_selector(self):
        main="""PROGRAM MAIN
ROUTINE check_child(who:INTEGER) FROM LIB
BEGIN
  check_child(3)
END MAIN
"""
        library="""PROGRAM LIB
ROUTINE check_child(who:INTEGER)
VAR s,number:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  number=who
  WAIT FOR PAUSE PROGRAM[number]
  text='prior'
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text)
END check_child
BEGIN
END LIB
"""
        child="""PROGRAM CHILD
VAR h,s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('LIB',library),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        status,text=result['text_output'].split(':')
        self.assertEqual((int(status),text),(4,'prior'))

    def test_numbered_resume_checks_the_next_pause_before_the_unsupported_tail(self):
        main="""PROGRAM MAIN
CONST child_id=2
VAR s,wait_for_child:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[child_id]
  CONTINUE PROGRAM[child_id]
  wait_for_child=child_id
  WAIT FOR PAUSE PROGRAM[wait_for_child]
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text)
END MAIN
"""
        child="""PROGRAM CHILD
VAR h,s,duration,late:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
  CLOSE_TPE(h,s)
  PAUSE
  DELAY duration
  WRITE(late)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation','task-wait'])
        self.assertEqual(result['status'],'paused')
        status,text=result['text_output'].split(':')
        self.assertEqual((int(status),text),(0,'ready'))

    def test_request_status_is_not_reused_as_prelaunch_task_number(self):
        main="""PROGRAM MAIN
VAR task_no,s:INTEGER text:STRING[8]
BEGIN
  task_no=2
  RUN_TASK('CHILD',0,FALSE,FALSE,0,task_no)
  WAIT FOR PAUSE PROGRAM[task_no]
  GET_TPE_STR_REG(1,text,s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR h,s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
        codes=[row['code'] for row in report['unresolved']]
        self.assertIn('condition-source',codes)
        self.assertIn('teach-handle',codes)

    def test_shared_service_between_launch_and_wait_stays_conservative(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  GET_TPE_STR_REG(1,text,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR h,s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
        codes=[row['code'] for row in report['unresolved']]
        self.assertIn('condition-source',codes)
        self.assertIn('teach-register',codes)
