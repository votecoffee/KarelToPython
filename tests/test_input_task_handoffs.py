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

    def prepare(self, sources, *, replay=True, callers=None):
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
            'callers':{'MAIN':'Shared', **(callers or {})},
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

    def test_nested_child_procedures_keep_locals_and_captured_arguments_at_pause(self):
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
VAR slot,seed,unused,duration:INTEGER cells:ARRAY[2] OF INTEGER
ROUTINE inner(amount:INTEGER; output:INTEGER)
VAR h,s:INTEGER i:SHORT
BEGIN
  FOR i=1 TO 1 DO
    OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
    slot=2
    seed=90
    PAUSE
    CLOSE_TPE(h,s)
    output=amount+i
    RETURN
  ENDFOR
  DELAY duration
END inner
ROUTINE outer(value:INTEGER; output:INTEGER)
CONST addend=2
VAR local_value:INTEGER
BEGIN
  local_value=value+addend
  inner(local_value+1,output)
  output=output+local_value
  PAUSE
  output=output+1
END outer
BEGIN
  slot=1
  seed=3
  cells[2]=99
  outer((seed),cells[slot])
  IF (cells[1]=13) AND (cells[2]=99) THEN
    WRITE(cells[1],':',cells[2])
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
        blocked,ready,output=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,int(next_status),current),(4,'prior',0,'ready'))
        self.assertEqual(tuple(map(int,output.split(':'))),(13,99))

    def test_procedure_return_clears_a_captured_global_counter_before_caller_resumes(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR i:SHORT unused:INTEGER
ROUTINE work
BEGIN
  FOR i=1 TO 2 DO
    PAUSE
    RETURN
  ENDFOR
END work
BEGIN
  work()
  IF UNINIT(i) THEN WRITE('clear') ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'clear')
        self.assertEqual(result['programs']['CHILD']['values']['I'],{'uninitialized':True})

    def test_recursive_child_procedure_keeps_conditional_inputs_and_wait_gap(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR needed:INTEGER
ROUTINE chain
BEGIN
  WRITE(needed)
  chain()
  PAUSE
END chain
BEGIN
  chain()
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
        self.assert_inputs(report,[('variable','CHILD','NEEDED','conditional')])
        codes=[row['code'] for row in report['unresolved']]
        self.assertIn('routine',codes)
        self.assertIn('condition-source',codes)

    def test_reentered_child_procedure_starts_with_fresh_locals(self):
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
        child="""PROGRAM CHILD
VAR unused:INTEGER
ROUTINE park(label_no:INTEGER)
VAR prior_value:INTEGER
BEGIN
  IF UNINIT(prior_value) THEN WRITE(label_no,CR) ELSE WRITE(unused) ENDIF
  prior_value=label_no
  PAUSE
END park
BEGIN
  park(1)
  park(2)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual([int(line) for line in result['text_output'].splitlines()],[1,2])

    def test_paused_procedure_reports_only_the_reached_input_with_its_routine_location(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR payload,late:INTEGER
ROUTINE take_input
BEGIN
  WRITE(payload)
  PAUSE
  WRITE(late)
END take_input
BEGIN
  take_input()
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
        self.assert_inputs(report,[('variable','CHILD','PAYLOAD','conditional')])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        locations=report['inputs'][0]['locations']
        self.assertEqual([(row['program'],row['routine']) for row in locations],[('CHILD','TAKE_INPUT')])

    def test_linked_child_procedures_resume_in_their_pinned_modules(self):
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
VAR slot,unused:INTEGER cells:ARRAY[2] OF INTEGER
ROUTINE bridge(seed:INTEGER; output:INTEGER; selected:INTEGER) FROM LIBA
BEGIN
  slot=1
  cells[2]=99
  bridge(3,cells[slot],slot)
  IF (cells[1]=13) AND (cells[2]=99) THEN
    WRITE(cells[1],':',cells[2])
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library_a="""PROGRAM LIBA
ROUTINE work(amount:INTEGER; output:INTEGER; selected:INTEGER) FROM LIBB
ROUTINE bridge(seed:INTEGER; output:INTEGER; selected:INTEGER)
CONST offset=2
VAR intermediate:INTEGER
BEGIN
  intermediate=seed+offset
  work(intermediate+1,output,selected)
  output=output+intermediate
  PAUSE
  output=output+1
END bridge
BEGIN
END LIBA
"""
        library_b="""PROGRAM LIBB
ROUTINE bridge(output:INTEGER)
BEGIN
  output=output+1
END bridge
ROUTINE work(amount:INTEGER; output:INTEGER; selected:INTEGER)
VAR h,s:INTEGER text:STRING[8]
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  selected=2
  PAUSE
  GET_TPE_STR_REG(1,text,s)
  WRITE(text,CR)
  CLOSE_TPE(h,s)
  output=amount
  bridge(output)
  RETURN
END work
BEGIN
END LIBB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIBA',library_a),('LIBB',library_b)],
                                   callers={'CHILD':'Shared'})
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        locations=report['inputs'][0]['locations']
        self.assertCountEqual([(row['program'],row['routine']) for row in locations],
                              [('MAIN',None),('LIBB','WORK')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,inside,ready,output=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,inside,int(next_status),current),(4,'prior','ready',0,'ready'))
        self.assertEqual(tuple(map(int,output.split(':'))),(13,99))

    def test_shared_library_globals_only_widen_reached_segments(self):
        main="""PROGRAM MAIN
VAR s:INTEGER text:STRING[8]
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  text='prior'
  GET_TPE_STR_REG(1,text,s)
END MAIN
"""
        child="""PROGRAM CHILD
ROUTINE work FROM LIB
BEGIN
  work()
END CHILD
"""
        for body,reached in (('WRITE(shared_value) PAUSE',True),('PAUSE WRITE(shared_value)',False)):
            with self.subTest(body=body):
                library=f"""PROGRAM LIB
VAR shared_value:INTEGER
ROUTINE work
VAR h,s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  {body}
END work
BEGIN
END LIB
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)],replay=not reached)
                if reached:
                    self.assert_inputs(report,[('variable','LIB','SHARED_VALUE','conditional')])
                    codes=[row['code'] for row in report['unresolved']]
                    self.assertIn('condition-source',codes)
                    self.assertIn('teach-register',codes)
                else:
                    self.assert_inputs(report,[])
                    self.assert_task_gaps(report,['task-scheduling','task-wait'])
                    self.assertEqual(result['status'],'paused')
                    values=result['programs']['MAIN']['values']
                    self.assertEqual((values['S'],values['TEXT']),(4,'prior'))

    def test_missing_or_mismatched_external_procedure_keeps_wait_unresolved(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR payload:INTEGER
ROUTINE work(amount:INTEGER) FROM LIB
BEGIN
  work(payload)
END CHILD
"""
        library="""PROGRAM LIB
ROUTINE work(amount:REAL)
BEGIN
  PAUSE
END work
BEGIN
END LIB
"""
        for additional in ([],[('LIB',library)]):
            with self.subTest(modules=len(additional)):
                report,_=self.prepare([('MAIN',main),('CHILD',child),*additional],replay=False)
                self.assert_inputs(report,[('variable','CHILD','PAYLOAD','conditional')])
                codes=[row['code'] for row in report['unresolved']]
                self.assertIn('routine',codes)
                self.assertIn('condition-source',codes)

    def test_function_resume_assigns_to_the_cell_selected_after_forwarded_return(self):
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
VAR cells:ARRAY[2] OF INTEGER slot,unused:INTEGER
ROUTINE relay(selected:INTEGER):REAL FROM LIB
BEGIN
  slot=1
  cells[1]=99
  cells[2]=88
  cells[slot]=(relay(slot))
  PAUSE
  IF (cells[1]=99) AND (cells[2]=6) THEN
    WRITE(cells[1],':',cells[2])
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIB
ROUTINE work(selected:INTEGER):REAL
VAR h,s:INTEGER i:SHORT
BEGIN
  FOR i=3 TO 3 DO
    OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
    PAUSE
    CLOSE_TPE(h,s)
    selected=2
    RETURN i+3.75
  ENDFOR
  RETURN 0.0
END work
ROUTINE relay(selected:INTEGER):REAL
BEGIN
  RETURN (work(selected))
END relay
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,ready,output=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,int(next_status),current),(4,'prior',0,'ready'))
        self.assertEqual(tuple(map(int,output.split(':'))),(99,6))

    def test_invalid_narrow_function_return_cannot_establish_a_later_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR n:SHORT
ROUTINE work:SHORT
BEGIN
  PAUSE
  RETURN 32767
END work
BEGIN
  n=17
  n=work()
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('uninitialized',result['error']['message'].lower())
        self.assertEqual(result['programs']['CHILD']['values']['N'],17)

    def test_compound_assignment_stops_before_the_unreached_function_suffix(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR before_pause,after_pause,n:INTEGER
ROUTINE work:INTEGER
BEGIN
  WRITE(before_pause)
  PAUSE
  RETURN after_pause
END work
BEGIN
  n=1+work()
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
        self.assert_inputs(report,[('variable','CHILD','BEFORE_PAUSE','conditional')])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])

    def test_if_uses_the_completed_function_value_then_resumes_in_the_selected_arm(self):
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
VAR h,s,unused:INTEGER chosen:BOOLEAN
ROUTINE check_handle(opened:INTEGER):BOOLEAN FROM LIB
BEGIN
  IF (check_handle(h)) THEN
    CLOSE_TPE(h,s)
    chosen=FALSE
    PAUSE
    IF NOT chosen THEN WRITE('branch') ELSE WRITE(unused) ENDIF
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIB
ROUTINE check_handle(opened:INTEGER):BOOLEAN
VAR s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,opened,s)
  PAUSE
  RETURN s=0
END check_handle
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,ready,branch=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,int(next_status),current,branch),(4,'prior',0,'ready','branch'))

    def test_select_retains_selector_and_first_match_across_later_label_pauses(self):
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
  WAIT FOR PAUSE PROGRAM[2]
  GET_TPE_STR_REG(1,text,s)
  WRITE(s,':',text,CR)
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR h,s,choice,trace,unused:INTEGER
ROUTINE pick:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
  RETURN choice
END pick
ROUTINE first_label:INTEGER
BEGIN
  trace=trace*10+1
  choice=99
  PAUSE
  RETURN 7
END first_label
ROUTINE later_label:INTEGER
BEGIN
  trace=trace*10+2
  CLOSE_TPE(h,s)
  PAUSE
  RETURN 7
END later_label
BEGIN
  trace=0
  choice=7
  SELECT (pick()) OF
    CASE((first_label()),choice):
      IF (trace=12) AND (choice=99) THEN WRITE('first') ELSE WRITE(unused) ENDIF
    CASE(later_label()): WRITE(unused)
    ELSE: WRITE(unused)
  ENDSELECT
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation','task-wait',
                                     'task-continuation','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        first,second,third,branch=result['text_output'].splitlines()
        pairs=[line.split(':') for line in (first,second,third)]
        self.assertEqual([(int(status),text) for status,text in pairs],[(4,'prior'),(4,'prior'),(0,'ready')])
        self.assertEqual(branch,'first')

    def test_select_still_pauses_in_later_label_after_earlier_match(self):
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
        child="""PROGRAM CHILD
VAR late,skipped:INTEGER
ROUTINE hold_label:INTEGER
VAR h,s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
  RETURN 2
END hold_label
ROUTINE later_label:INTEGER
BEGIN
  RETURN late
END later_label
BEGIN
  SELECT 1 OF
    CASE(1): WRITE(skipped)
    CASE(hold_label()): WRITE(skipped)
    CASE(1+later_label()): WRITE(skipped)
  ENDSELECT
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        status,text=result['text_output'].split(':')
        self.assertEqual((int(status),text),(4,'prior'))

    def test_unresolved_case_value_keeps_possible_arm_reads_and_wait_gap(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR supplied,chosen,otherwise:INTEGER
ROUTINE dynamic_label:INTEGER
BEGIN
  PAUSE
  RETURN supplied
END dynamic_label
BEGIN
  SELECT 7 OF
    CASE(dynamic_label()): WRITE(chosen) PAUSE
    ELSE: WRITE(otherwise)
  ENDSELECT
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
        self.assert_inputs(report,[('variable','CHILD',name,'conditional')
                                   for name in ('SUPPLIED','CHOSEN','OTHERWISE')])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])

    def test_paused_for_bounds_keep_the_original_counter_and_use_its_post_bound_value(self):
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
VAR cells:ARRAY[2] OF INTEGER slot,h,s,trace,unused:INTEGER
ROUTINE seed_value(selected:INTEGER):INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  selected=2
  PAUSE
  RETURN 2
END seed_value
ROUTINE end_value(counter:INTEGER):INTEGER
VAR initialized:INTEGER
BEGIN
  initialized=counter
  counter=1
  CLOSE_TPE(h,s)
  PAUSE
  RETURN initialized
END end_value
BEGIN
  slot=1
  cells[1]=77
  cells[2]=99
  trace=0
  FOR cells[slot]=(seed_value(slot)) TO end_value(cells[1]) DO
    trace=trace*10+cells[1]
  ENDFOR
  IF UNINIT(cells[1]) AND (trace=12) AND (cells[2]=99) THEN
    WRITE(trace,':',cells[2])
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
        blocked,ready,output=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,int(next_status),current),(4,'prior',0,'ready'))
        self.assertEqual(tuple(map(int,output.split(':'))),(12,99))
        self.assertEqual(result['programs']['CHILD']['values']['CELLS'],[{'uninitialized':True},99])

    def test_pausing_while_and_repeat_functions_run_on_their_respective_sides_of_the_body(self):
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
        cases=(('WHILE (check_test(n)) DO n=n+1 ENDWHILE','value<1',12,1),
               ('REPEAT n=n+1 UNTIL check_test(n)','value>=2',23,2))
        for loop,predicate,trace,count in cases:
            with self.subTest(loop=loop):
                child=f"""PROGRAM CHILD
VAR n,recorded,unused:INTEGER
ROUTINE check_test(value:INTEGER):BOOLEAN
BEGIN
  recorded=recorded*10+value+1
  PAUSE
  RETURN {predicate}
END check_test
BEGIN
  n=0
  recorded=0
  {loop}
  IF (recorded={trace}) AND (n={count}) THEN
    WRITE(recorded,':',n)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)])
                self.assert_inputs(report,[])
                self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                             'task-wait','task-continuation'])
                self.assertEqual(result['status'],'completed')
                self.assertEqual(tuple(map(int,result['text_output'].split(':'))),(trace,count))

    def test_invalid_resumed_narrow_final_bound_keeps_the_next_wait_unresolved(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR count:BYTE
ROUTINE end_value:INTEGER
BEGIN
  PAUSE
  RETURN 256
END end_value
BEGIN
  FOR count=254 TO end_value() DO
    PAUSE
  ENDFOR
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('BYTE FOR bounds',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['COUNT'],{'unknown_byte':True})

    def test_unresolved_resumed_loop_function_preserves_possible_body_reads(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR payload:INTEGER supplied:BOOLEAN
ROUTINE check_test:BOOLEAN
BEGIN
  PAUSE
  RETURN supplied
END check_test
BEGIN
  WHILE check_test() DO
    WRITE(payload)
    PAUSE
  ENDWHILE
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
        self.assert_inputs(report,[('variable','CHILD','PAYLOAD','conditional'),
                                   ('variable','CHILD','SUPPLIED','conditional')])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])

    def test_compound_assignment_captures_left_values_and_keeps_integer_and_eager(self):
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
VAR prior,h,s,answer,unused:INTEGER
ROUTINE first_value:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  prior=70
  PAUSE
  RETURN 2
END first_value
ROUTINE second_value:INTEGER
BEGIN
  CLOSE_TPE(h,s)
  prior=90
  PAUSE
  RETURN 255
END second_value
BEGIN
  prior=4
  answer=(prior+first_value())*10+(0 AND second_value())+(6 DIV 2)
  IF (answer=63) AND (prior=90) THEN WRITE(answer) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,ready,answer=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,int(next_status),current),(4,'prior',0,'ready'))
        self.assertEqual(int(answer),63)

    def test_paused_boolean_short_circuits_a_routine_and_continues_at_the_next_operand(self):
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
        child="""PROGRAM CHILD
VAR trace,unused:INTEGER
ROUTINE gate:BOOLEAN
BEGIN
  trace=trace*10+1
  PAUSE
  RETURN TRUE
END gate
ROUTINE unused_operand:BOOLEAN
BEGIN
  WRITE(unused)
  PAUSE
  RETURN FALSE
END unused_operand
ROUTINE last_test:BOOLEAN
BEGIN
  trace=trace*10+2
  PAUSE
  RETURN FALSE
END last_test
BEGIN
  trace=0
  IF (gate() OR unused_operand()) AND NOT last_test() THEN WRITE(trace) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(int(result['text_output']),12)

    def test_unknown_boolean_keeps_the_possible_pausing_operand_visible(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR supplied:BOOLEAN optional:INTEGER
ROUTINE gate:BOOLEAN
BEGIN
  PAUSE
  RETURN supplied
END gate
ROUTINE alternate:BOOLEAN
BEGIN
  WRITE(optional)
  PAUSE
  RETURN TRUE
END alternate
BEGIN
  IF gate() OR alternate() THEN WRITE('done') ENDIF
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
        self.assert_inputs(report,[('variable','CHILD','SUPPLIED','conditional'),
                                   ('variable','CHILD','OPTIONAL','conditional')])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])

    def test_compound_repeat_test_resumes_at_the_call_each_iteration(self):
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
        child="""PROGRAM CHILD
VAR n,unused:INTEGER
ROUTINE endpoint:INTEGER
BEGIN
  PAUSE
  RETURN 3
END endpoint
BEGIN
  n=0
  REPEAT
    n=n+1
  UNTIL (n+1=endpoint()) AND (n>=2)
  IF n=2 THEN WRITE(n) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(int(result['text_output']),2)

    def test_repeat_eval_sample_preceding_a_pausing_operand_stays_visible(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR sampled:INTEGER
ROUTINE gate:BOOLEAN
BEGIN
  PAUSE
  RETURN TRUE
END gate
BEGIN
  REPEAT
    WRITE('begin')
  UNTIL gate() OR (EVAL(sampled)=1)
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False)
        self.assert_inputs(report,[('variable','CHILD','SAMPLED','conditional')])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])

    def test_pausing_arguments_keep_the_original_reference_and_earlier_scalar_value(self):
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
VAR cells:ARRAY[2] OF INTEGER slot,seed,h,s,answer,unused:INTEGER
ROUTINE finish(result_cell:INTEGER; baseline:INTEGER; extra:INTEGER; last:INTEGER):INTEGER FROM LIB
ROUTINE mutate(index_cell:INTEGER; seed_cell:INTEGER):INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  index_cell=2
  seed_cell=55
  PAUSE
  RETURN 3
END mutate
ROUTINE tail_value:INTEGER
BEGIN
  CLOSE_TPE(h,s)
  PAUSE
  RETURN seed
END tail_value
BEGIN
  slot=1
  seed=4
  cells[1]=1
  cells[2]=99
  answer=finish(cells[slot],(seed),2+mutate(slot,seed),tail_value())
  IF (cells[1]=64) AND (cells[2]=99) AND (answer=65) THEN
    WRITE(cells[1],':',cells[2],':',answer)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIB
ROUTINE finish(result_cell:INTEGER; baseline:INTEGER; extra:INTEGER; last:INTEGER):INTEGER
BEGIN
  result_cell=baseline+extra+last
  RETURN result_cell+1
END finish
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,ready,output=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,int(next_status),current),(4,'prior',0,'ready'))
        self.assertEqual(tuple(map(int,output.split(':'))),(64,99,65))

    def test_nested_value_argument_resumes_before_entering_its_callee_and_procedure(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR answer,trace,unused:INTEGER
ROUTINE inner:INTEGER
BEGIN
  trace=trace*10+1
  PAUSE
  RETURN 3
END inner
ROUTINE middle(value:INTEGER):INTEGER
BEGIN
  trace=trace*10+2
  RETURN value+1
END middle
ROUTINE finish(output:INTEGER; value:INTEGER)
BEGIN
  trace=trace*10+3
  output=value
END finish
BEGIN
  trace=0
  finish(answer,middle(inner()))
  IF (trace=123) AND (answer=4) THEN WRITE(answer) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(int(result['text_output']),4)

    def test_paused_argument_leaves_an_unsupported_later_argument_dormant(self):
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
        child="""PROGRAM CHILD
VAR late:INTEGER
ROUTINE park:INTEGER
VAR h,s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
  RETURN 1
END park
ROUTINE finish(first_value:INTEGER; last_value:INTEGER)
BEGIN
  WRITE(first_value,last_value)
END finish
BEGIN
  finish(park(),ABS(late))
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        blocked,text=result['text_output'].split(':')
        self.assertEqual((int(blocked),text),(4,'prior'))

    def test_failed_argument_does_not_establish_a_pause_in_a_later_argument(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        cases=(('seed+2','INTEGER overflow'),('MAXINT','INTEGER storage excludes MAXINT'))
        for argument,message in cases:
            with self.subTest(argument=argument):
                child=f"""PROGRAM CHILD
VAR seed:INTEGER
ROUTINE park:INTEGER
BEGIN
  PAUSE
  RETURN 1
END park
ROUTINE finish(first_value:INTEGER; last_value:INTEGER)
BEGIN
  WRITE(first_value,last_value)
END finish
BEGIN
  seed=2147483646
  finish({argument},park())
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)])
                self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
                self.assertEqual(result['status'],'failed')
                self.assertIn(message,result['error']['message'])
                self.assertEqual(result['text_output'],'')

    def test_multidimensional_read_retains_the_first_subscript_across_the_second(self):
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
TYPE row_type=STRUCTURE amount:INTEGER ENDSTRUCTURE
VAR items:ARRAY[2,2] OF row_type row,answer,unused:INTEGER
ROUTINE select_column(changed:INTEGER):INTEGER
VAR h,s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  changed=2
  PAUSE
  CLOSE_TPE(h,s)
  RETURN 2
END select_column
BEGIN
  row=1
  items[1,2].amount=42
  items[2,2].amount=99
  answer=items[row,select_column(row)].amount
  PAUSE
  IF (answer=42) AND (row=2) THEN WRITE(answer) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,ready,answer=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,int(next_status),current),(4,'prior',0,'ready'))
        self.assertEqual(int(answer),42)

    def test_assignment_captures_rhs_before_pausing_in_the_target_subscript(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR cells:ARRAY[2] OF SHORT source_value:REAL unused:INTEGER
ROUTINE select_target:INTEGER
BEGIN
  source_value=90.5
  PAUSE
  RETURN 2
END select_target
BEGIN
  source_value=7.75
  cells[1]=99
  cells[select_target()]=source_value
  IF (cells[2]=7) AND (cells[1]=99) THEN WRITE(cells[2]) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(int(result['text_output']),7)
        self.assertEqual(result['programs']['CHILD']['values']['CELLS'],[99,7])

    def test_pausing_subscripts_capture_for_and_reference_argument_cells(self):
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
        child="""PROGRAM CHILD
VAR counters,cells:ARRAY[2] OF INTEGER slot,trace,unused:INTEGER
ROUTINE select_cell(selected:INTEGER):INTEGER
VAR captured:INTEGER
BEGIN
  captured=selected
  selected=2
  PAUSE
  RETURN captured
END select_cell
ROUTINE assign_cell(output:INTEGER; value:INTEGER)
BEGIN
  output=value
END assign_cell
BEGIN
  slot=1
  trace=0
  counters[2]=99
  cells[2]=88
  FOR counters[select_cell(slot)]=1 TO 2 DO
    trace=trace*10+counters[1]
  ENDFOR
  slot=1
  assign_cell(cells[select_cell(slot)],trace)
  IF UNINIT(counters[1]) AND (counters[2]=99) AND (cells[1]=12) AND (cells[2]=88) THEN
    WRITE(cells[1])
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(int(result['text_output']),12)

    def test_flat_subscripts_pause_before_bounds_check_and_keep_unknown_addresses_unresolved(self):
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
        child_template="""PROGRAM CHILD
VAR cells:ARRAY[2,2] OF INTEGER n,unknown_index:INTEGER
ROUTINE select_column:INTEGER
VAR h,s:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
  RETURN {column}
END select_column
BEGIN
  n=cells[{row},select_column()]
  PAUSE
END CHILD
"""
        first=child_template.format(row=3,column=1)
        report,result=self.prepare([('MAIN',main),('CHILD',first)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        blocked,text=result['text_output'].split(':')
        self.assertEqual((int(blocked),text),(4,'prior'))

        main=main.replace("  text='prior'", """  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  text='prior'""")
        unknown=child_template.format(row=1,column='unknown_index')
        report,_=self.prepare([('MAIN',main),('CHILD',unknown)],replay=False)
        candidates=[row for row in report['inputs'] if row['program']=='CHILD']
        self.assertEqual([(row['path'],row['certainty']) for row in candidates],
                         [('UNKNOWN_INDEX','conditional')])
        codes=[row['code'] for row in report['unresolved']]
        self.assertIn('condition-source',codes)
        self.assertIn('dynamic-address',codes)

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
