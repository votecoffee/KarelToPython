"""Regression coverage for linked pause handoffs and checked child segments."""

from pathlib import Path
from tempfile import TemporaryDirectory, mkdtemp
import unittest

from karel2py import runner, translate
from karel2py.project_run import create_project_document


class TaskHandoffTests(unittest.TestCase):
    def setUp(self):
        folder=TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)

    def prepare(self, sources, *, replay=True):
        case_folder=Path(mkdtemp(dir=self.root))
        paths=[]
        for name, source in sources:
            path=case_folder/(name.lower()+'.py')
            result=translate(source,cooperative=True)
            path.write_bytes(result.python_source.encode('utf-8'))
            paths.append(path)
        document=case_folder/'linked.run.json'
        context={'teach_programs':{
            'programs':{'Shared':{'string_registers':{'1':'ready'}}},
            'callers':{'MAIN':'Shared'},
        }}
        saved=create_project_document(paths,document,entry='MAIN',context=context,max_cycles=100,discover=True)
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

    def test_resume_leaves_if_arm_and_reaches_next_top_level_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  text='prior'
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text,CR)
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text)
END MAIN
"""
        child="""PROGRAM CHILD
VAR h,s,skipped,late:INTEGER take_arm:BOOLEAN
BEGIN
  take_arm=TRUE
  IF take_arm THEN
    OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
    take_arm=FALSE
    PAUSE
    CLOSE_TPE(h,s)
  ELSE
    DELAY skipped
  ENDIF
  PAUSE
  WRITE(late)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation','task-wait'])
        self.assertEqual(result['status'],'paused')
        values=[line.split(':') for line in result['text_output'].splitlines()]
        self.assertEqual([(int(status),text) for status,text in values],[(4,'prior'),(0,'ready')])

    def test_selected_case_and_else_resume_inside_nested_if_to_completion(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  text='prior'
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text,CR)
  CONTINUE PROGRAM[2]
  WAIT FOR PAUSE PROGRAM[2]
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text,CR)
  CONT_TASK('CHILD',s)
END MAIN
"""
        for selector, selected in ((11,'case'),(99,'else')):
            with self.subTest(selector=selector):
                child=f"""PROGRAM CHILD
VAR h,s,choice,wanted,skipped:INTEGER label:STRING[8]
BEGIN
  choice={selector}
  wanted=11
  SELECT choice OF
    CASE(10,wanted): label='case'
                 IF choice=11 THEN
                   OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
                   choice=99
                   PAUSE
                   CLOSE_TPE(h,s)
                   PAUSE
                 ENDIF
    CASE(0): DELAY skipped
    ELSE: label='else'
          IF choice=99 THEN
            OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
            choice=11
            PAUSE
            CLOSE_TPE(h,s)
            PAUSE
          ENDIF
  ENDSELECT
  WRITE(label)
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)])
                self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
                self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                             'task-wait','task-continuation'])
                self.assertEqual(result['status'],'completed')
                blocked,opened,text=result['text_output'].splitlines()
                first_status,previous=blocked.split(':')
                next_status,current=opened.split(':')
                self.assertEqual((int(first_status),previous,int(next_status),current,text),
                                 (4,'prior',0,'ready',selected))

    def test_unknown_branch_preserves_conditional_reads_and_unresolved_wait(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  GET_TPE_STR_REG(1,text,s)
END MAIN
"""
        branches=(
            'IF choice=1 THEN WRITE(early) PAUSE WRITE(late) ELSE WRITE(other) ENDIF',
            'SELECT choice OF CASE(1): WRITE(early) PAUSE WRITE(late) ELSE: WRITE(other) ENDSELECT',
        )
        for branch in branches:
            with self.subTest(branch=branch):
                child=f"""PROGRAM CHILD
VAR choice,early,late,other:INTEGER
BEGIN
  {branch}
END CHILD
"""
                report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
                variables=[(row['path'],row['certainty']) for row in report['inputs'] if row['program']=='CHILD']
                self.assertCountEqual(variables,[(name,'conditional') for name in ('CHOICE','EARLY','LATE','OTHER')])
                codes=[row['code'] for row in report['unresolved']]
                self.assertIn('condition-source',codes)
                self.assertIn('teach-register',codes)

    def test_unselected_pause_does_not_satisfy_parent_wait(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  GET_TPE_STR_REG(1,text,s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR h,s:INTEGER
BEGIN
  IF FALSE THEN
    PAUSE
  ELSE
    OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        codes=[row['code'] for row in report['unresolved']]
        self.assertIn('condition-source',codes)
        self.assertEqual(result['status'],'failed')
        self.assertIn('Scheduler cycle budget exceeded',result['error']['message'])
        self.assertEqual(result['text_output'],'')

    def test_downward_for_keeps_captured_bounds_and_clears_counter_after_two_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  text='prior'
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text,CR)
  CONTINUE PROGRAM[2]
  WAIT FOR PAUSE PROGRAM[2]
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text,CR)
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR h,s,i,last,unused:INTEGER
BEGIN
  last=2
  FOR i=3 DOWNTO last DO
    IF i=3 THEN
      OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
      last=1
    ELSE
      CLOSE_TPE(h,s)
    ENDIF
    PAUSE
    WRITE(i,CR)
  ENDFOR
  IF UNINIT(i) THEN WRITE('clear') ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,first,opened,second,cleanup=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=opened.split(':')
        self.assertEqual((int(first_status),previous,int(first),int(next_status),current,int(second),cleanup),
                         (4,'prior',3,0,'ready',2,'clear'))

    def test_while_retests_and_repeat_reuses_eval_sample_after_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        cases=(
            ('WHILE n<2 DO n=n+1 PAUSE ENDWHILE',2),
            ('REPEAT n=n+1 IF n<3 THEN PAUSE ENDIF UNTIL (n=3) OR (EVAL(n)=2)',3),
        )
        for loop,final in cases:
            with self.subTest(loop=loop):
                child=f"""PROGRAM CHILD
VAR n,unused:INTEGER
BEGIN
  n=0
  {loop}
  IF n={final} THEN WRITE(n) ELSE WRITE(unused) ENDIF
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)])
                self.assert_inputs(report,[])
                self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                             'task-wait','task-continuation'])
                self.assertEqual(result['status'],'completed')
                self.assertEqual(int(result['text_output']),final)

    def test_empty_loops_skip_unreached_pauses_and_reads(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  GET_TPE_STR_REG(1,text,s)
  WRITE(text)
END MAIN
"""
        child="""PROGRAM CHILD
VAR i,unused,late:INTEGER
BEGIN
  FOR i=3 TO 2 DO
    WRITE(unused)
    PAUSE
  ENDFOR
  WHILE FALSE DO
    WRITE(unused)
    PAUSE
  ENDWHILE
  PAUSE
  WRITE(late)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'ready')

    def test_paused_loop_prefix_does_not_require_all_iterations_or_later_repeat_test(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  text='prior'
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text)
END MAIN
"""
        body="OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s) PAUSE WRITE(late)"
        loops=(f'FOR i=1 TO 1000000 DO {body} ENDFOR', f'REPEAT {body} UNTIL later()')
        for loop in loops:
            with self.subTest(loop=loop):
                child=f"""PROGRAM CHILD
VAR i,h,s,late:INTEGER
ROUTINE later:BOOLEAN
BEGIN
  RETURN late=0
END later
BEGIN
  {loop}
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)])
                self.assert_inputs(report,[])
                self.assert_task_gaps(report,['task-scheduling','task-wait'])
                self.assertEqual(result['status'],'paused')
                blocked,text=result['text_output'].split(':')
                self.assertEqual((int(blocked),text),(4,'prior'))

    def test_dynamic_and_over_budget_loop_keep_reads_and_wait_unresolved(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        for bound, has_input in (('limit',True),('33',False)):
            with self.subTest(bound=bound):
                child=f"""PROGRAM CHILD
VAR i,limit,payload:INTEGER
BEGIN
  FOR i=1 TO {bound} DO
    IF i=33 THEN
      WRITE(payload)
      PAUSE
    ENDIF
  ENDFOR
END CHILD
"""
                report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
                required=[('variable','CHILD','PAYLOAD','conditional')]
                if has_input:
                    required.append(('variable','CHILD','LIMIT','conditional'))
                self.assert_inputs(report,required)
                self.assertIn('condition-source',[row['code'] for row in report['unresolved']])

    def test_narrow_counters_reach_domain_endpoints_and_restore_their_cleanup_markers(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        cases=(('BYTE','254 TO 255',[254,255],{'unknown_byte':True}),
               ('SHORT','-32767 DOWNTO -32768',[-32767,-32768],{'uninitialized':True}))
        for kind,bounds,expected,marker in cases:
            with self.subTest(kind=kind):
                child=f"""PROGRAM CHILD
VAR i:{kind}
BEGIN
  FOR i={bounds} DO
    PAUSE
    WRITE(i,CR)
  ENDFOR
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)])
                self.assert_inputs(report,[])
                self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                             'task-wait','task-continuation'])
                self.assertEqual(result['status'],'completed')
                self.assertEqual([int(line) for line in result['text_output'].splitlines()],expected)
                self.assertEqual(result['programs']['CHILD']['values']['I'],marker)

    def test_indexed_record_counter_preserves_captured_leaf_across_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  text='prior'
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text,CR)
  CONTINUE PROGRAM[2]
  WAIT FOR PAUSE PROGRAM[2]
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text,CR)
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_type=STRUCTURE tally:SHORT ENDSTRUCTURE
VAR items:ARRAY[2,2] OF row_type slot,h,s,unused:INTEGER
BEGIN
  slot=1
  items[2,2].tally=55
  FOR items[slot,1].tally=1 TO items[slot,1].tally+1 DO
    IF items[1,1].tally=1 THEN
      OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
      slot=2
    ELSE
      CLOSE_TPE(h,s)
    ENDIF
    PAUSE
    WRITE(items[1,1].tally,CR)
  ENDFOR
  IF UNINIT(items[1,1].tally) AND (items[2,2].tally=55) THEN
    WRITE('clear')
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,first,ready,second,cleanup=result['text_output'].splitlines()
        blocked_status,previous=blocked.split(':')
        ready_status,current=ready.split(':')
        self.assertEqual((int(blocked_status),previous,int(first),int(ready_status),current,int(second),cleanup),
                         (4,'prior',1,0,'ready',2,'clear'))

    def test_out_of_domain_narrow_bounds_do_not_establish_a_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        cases=(('BYTE','256 DOWNTO 254',7),('BYTE','254 TO 256',{'unknown_byte':True}),
               ('SHORT','32767 DOWNTO 32765',7),('SHORT','32765 TO 32767',{'uninitialized':True}))
        for kind,bounds,value_after_error in cases:
            with self.subTest(kind=kind,bounds=bounds):
                child=f"""PROGRAM CHILD
VAR i:{kind}
BEGIN
  i=7
  FOR i={bounds} DO
    PAUSE
  ENDFOR
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)])
                self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
                self.assertEqual(result['status'],'failed')
                self.assertIn('FOR bounds require initialized values',result['error']['message'])
                self.assertEqual(result['programs']['CHILD']['values']['I'],value_after_error)

    def test_unknown_composite_selection_keeps_the_parent_wait_unresolved(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  GET_TPE_STR_REG(1,text,s)
END MAIN
"""
        loops=(
            ('FOR cells[slot]=1 TO 1 DO PAUSE ENDFOR','dynamic-address'),
            ('FOR i=1 TO 1 DO cells[slot]=i PAUSE ENDFOR','dynamic-address'),
            ('FOR i=1 TO 1 DO WRITE(cells[3]) PAUSE ENDFOR','selection'),
        )
        for loop,problem in loops:
            with self.subTest(loop=loop):
                child=f"""PROGRAM CHILD
VAR cells:ARRAY[2] OF INTEGER slot,i,h,s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  {loop}
END CHILD
"""
                report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
                inputs=[('variable','CHILD','SLOT','conditional')] if problem=='dynamic-address' else []
                self.assert_inputs(report,inputs)
                codes=[row['code'] for row in report['unresolved']]
                self.assertIn(problem,codes)
                self.assertIn('condition-source',codes)
                self.assertIn('teach-register',codes)

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
