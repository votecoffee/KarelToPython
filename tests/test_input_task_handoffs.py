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

    def prepare(self, sources, *, replay=True, callers=None, predefined_files=None, files=None, variables=None):
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
        if predefined_files is not None:
            context['predefined_files']=predefined_files
        if files is not None:
            context['files']=files
        if variables is not None:
            context['variables']=variables
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
        self.assert_task_gaps(report,['task-scheduling','task-wait'])

    def test_nested_repeat_captures_finish_before_live_test_and_are_reused(self):
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
  WRITE(s,':',text,CR)
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR n,h,s,trace,unused:INTEGER
ROUTINE first_term:INTEGER
BEGIN
  trace=trace*10+1
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
  RETURN 1
END first_term
ROUTINE second_term:INTEGER
BEGIN
  trace=trace*10+2
  CLOSE_TPE(h,s)
  PAUSE
  RETURN 1
END second_term
ROUTINE live_gate:BOOLEAN
BEGIN
  trace=trace*10+3
  PAUSE
  RETURN TRUE
END live_gate
BEGIN
  n=0
  trace=0
  REPEAT
    n=n+1
  UNTIL live_gate() AND (n>=EVAL(EVAL(first_term())+EVAL(second_term())))
  IF trace=1233 THEN WRITE(n) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,ready,output=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,int(next_status),current),(4,'prior',0,'ready'))
        self.assertEqual(int(output),2)
        self.assertEqual(result['programs']['CHILD']['values']['TRACE'],1233)

    def test_repeat_reentry_takes_a_fresh_capture_through_a_linked_routine(self):
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
VAR i,trace:INTEGER
ROUTINE sample(value:INTEGER; trace:INTEGER):BOOLEAN FROM LIBA
BEGIN
  trace=0
  FOR i=1 TO 2 DO
    REPEAT
      WRITE(i)
    UNTIL TRUE OR EVAL(sample((i),trace))
  ENDFOR
END CHILD
"""
        library="""PROGRAM LIBA
ROUTINE sample(value:INTEGER; trace:INTEGER):BOOLEAN
BEGIN
  trace=trace*10+value
  PAUSE
  RETURN FALSE
END sample
BEGIN
END LIBA
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIBA',library)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'].split(),['1','2'])
        self.assertEqual(result['programs']['CHILD']['values']['TRACE'],12)

    def test_invalid_repeat_capture_prevents_a_later_capture_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t
VAR zero,reached:INTEGER routes:ARRAY[1] OF route_t
ROUTINE later_sample:REAL
BEGIN
  reached=1
  PAUSE
  RETURN 1.0
END later_sample
BEGIN
  reached=0
  REPEAT
    {body}
  UNTIL TRUE OR (EVAL({sample})=EVAL(later_sample()))
END CHILD
"""
        cases=(
            ('zero=0','SQRT(zero-1)','SQRT argument must not be negative'),
            ('FOR zero=1 TO 1 DO reached=0 ENDFOR','SQRT(zero)','uninitialized'),
            ('reached=0','PATH_LEN(EVAL(routes[2]))','Array index 2 outside 1..1'),
        )
        for body,sample,error in cases:
            with self.subTest(sample=sample):
                source=child.format(body=body,sample=sample)
                report,result=self.prepare([('MAIN',main),('CHILD',source)])
                self.assert_inputs(report,[])
                self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
                self.assertEqual(result['status'],'failed')
                self.assertIn(error,result['error']['message'])
                self.assertEqual(result['programs']['CHILD']['values']['REACHED'],0)

    def test_repeat_captures_selected_path_before_live_edits_and_reuses_it(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER unused_field:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE limit:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR routes:ARRAY[2] OF route_t iterations,s,unused:INTEGER
ROUTINE choose_route:INTEGER
BEGIN
  PAUSE
  RETURN 1
END choose_route
ROUTINE gate:BOOLEAN
BEGIN
  routes[1].limit=99
  APPEND_NODE(routes[1],s)
  PAUSE
  RETURN TRUE
END gate
BEGIN
  routes[1].limit=2
  APPEND_NODE(routes[1],s)
  routes[1,1].amount=7
  iterations=0
  REPEAT
    iterations=iterations+1
  UNTIL gate() AND (PATH_LEN(EVAL(routes[choose_route()]))=1) AND (iterations>=EVAL(EVAL(routes[1]).limit)) AND (EVAL(routes[1])[1].amount=7)
  IF iterations=2 THEN WRITE(iterations) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*3)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 2')
        route=result['programs']['CHILD']['values']['ROUTES'][0]
        self.assertEqual((route['data']['LIMIT'],len(route['nodes'])),(99,3))

    def test_repeat_captures_path_result_from_pinned_routine_for_pausing_live_selector(self):
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
        path_types="""TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t
"""
        child=f"""PROGRAM CHILD
{path_types}VAR n,unused:INTEGER
ROUTINE route:route_t FROM LIB
ROUTINE choose_node:INTEGER
BEGIN
  PAUSE
  RETURN 1
END choose_node
BEGIN
  REPEAT
    n=7
  UNTIL EVAL(route())[choose_node()].amount=n
  IF n=7 THEN WRITE(n) ELSE WRITE(unused) ENDIF
END CHILD
"""
        library=f"""PROGRAM LIB
{path_types}ROUTINE route:route_t
VAR local_path:route_t s:INTEGER
BEGIN
  APPEND_NODE(local_path,s)
  local_path[1].amount=7
  PAUSE
  RETURN local_path
END route
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*2)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 7')

    def test_path_slot_and_field_arguments_survive_a_later_pausing_path_edit(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=row_t
VAR routes:ARRAY[2] OF route_t s,result,unused:INTEGER
ROUTINE edit(slot:row_t; cell,delta:INTEGER):INTEGER FROM LIB
ROUTINE pick:INTEGER
BEGIN
  PAUSE
  RETURN 2
END pick
ROUTINE discard:INTEGER
BEGIN
  PAUSE
  DELETE_NODE(routes[2],1,s)
  RETURN 3
END discard
BEGIN
  APPEND_NODE(routes[2],s)
  APPEND_NODE(routes[2],s)
  routes[2,1].amount=11
  routes[2,2].amount=22
  result=edit(routes[pick(),1],routes[2][1].amount,discard())
  IF (result=37) AND (PATH_LEN(routes[2])=1) AND (routes[2,1].amount=25) THEN WRITE(result) ELSE WRITE(unused) ENDIF
END CHILD
"""
        library="""PROGRAM LIB
TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
ROUTINE inspect(sample:row_t):INTEGER
BEGIN
  sample.amount=sample.amount+1
  RETURN sample.amount-1
END inspect
ROUTINE edit(slot:row_t; cell,delta:INTEGER):INTEGER
BEGIN
  PAUSE
  slot.amount=slot.amount+delta
  cell=cell+1
  RETURN inspect((slot))+cell
END edit
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*3)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 37')
        self.assertEqual(result['programs']['CHILD']['values']['ROUTES'][1]['nodes'],[{'AMOUNT':25}])

    def test_path_slot_arguments_keep_old_header_and_shifted_node_when_pinned_call_replaces_path(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        types="""TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=row_t PATHHEADER=row_t
"""
        child=f"""PROGRAM CHILD
{types}VAR route,replacement:route_t s,result,unused:INTEGER
ROUTINE edit(live,source:route_t; node,header:row_t; cell:INTEGER):INTEGER FROM LIB
BEGIN
  route.amount=7
  APPEND_NODE(route,s)
  APPEND_NODE(route,s)
  route[1].amount=11
  route[2].amount=22
  replacement.amount=30
  APPEND_NODE(replacement,s)
  replacement[1].amount=40
  result=edit(route,replacement,route[1],route[0],route.amount)
  IF (result=32) AND (route.amount=30) AND (route[1].amount=40) THEN WRITE(result) ELSE WRITE(unused) ENDIF
END CHILD
"""
        library=f"""PROGRAM LIB
{types}ROUTINE edit(live,source:route_t; node,header:row_t; cell:INTEGER):INTEGER
VAR s:INTEGER
BEGIN
  DELETE_NODE(live,1,s)
  PAUSE
  COPY_PATH(source,0,0,live,s)
  header.amount=header.amount+1
  node.amount=node.amount+2
  RETURN node.amount+cell
END edit
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 32')
        self.assertEqual(result['programs']['CHILD']['values']['ROUTE'],
                         {'data':{'AMOUNT':30},'nodes':[{'AMOUNT':40}]})

    def test_vacant_path_slot_forwards_through_pause_and_recovers_only_in_its_own_list(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        types="""TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=row_t
"""
        child=f"""PROGRAM CHILD
{types}VAR route:route_t s,unused:INTEGER
ROUTINE fill(item:route_t; slot:row_t) FROM LIB
ROUTINE drop_first(slot:row_t)
BEGIN
  DELETE_NODE(route,1,s)
  fill(route,slot)
END drop_first
BEGIN
  APPEND_NODE(route,s)
  route[1].amount=17
  drop_first(route[1])
  IF route[1].amount=29 THEN WRITE(route[1].amount) ELSE WRITE(unused) ENDIF
END CHILD
"""
        for replace_list in (False, True):
            with self.subTest(replace_list=replace_list):
                before_append='COPY_PATH(item,0,0,item,s)' if replace_list else ''
                library=f"""PROGRAM LIB
{types}ROUTINE fill(item:route_t; slot:row_t)
VAR s:INTEGER
BEGIN
  PAUSE
  {before_append}
  APPEND_NODE(item,s)
  slot.amount=29
END fill
BEGIN
END LIB
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
                if replace_list:
                    codes=[row['code'] for row in report['unresolved']]
                    self.assertIn('condition-source',codes)
                    self.assertEqual(result['status'],'failed')
                    self.assertEqual(result['text_output'],'')
                else:
                    self.assert_inputs(report,[])
                    self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
                    self.assertEqual(result['status'],'completed',result['error'])
                    self.assertEqual(result['text_output'],' 29')

    def test_argument_subscript_pause_keeps_descendant_of_loaded_path_slot(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_t=STRUCTURE samples:ARRAY[2] OF INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=row_t
VAR route:route_t s,result,unused:INTEGER
ROUTINE select_sample:INTEGER
BEGIN
  PAUSE
  DELETE_NODE(route,1,s)
  RETURN 2
END select_sample
ROUTINE update(cell:INTEGER)
BEGIN
  cell=cell+1
  result=cell
END update
ROUTINE forward(slot:row_t)
BEGIN
  update(slot.samples[select_sample()])
END forward
BEGIN
  APPEND_NODE(route,s)
  APPEND_NODE(route,s)
  route[1].samples[2]=11
  route[2].samples[2]=22
  forward(route[1])
  IF (result=12) AND (route[1].samples[2]=22) THEN WRITE(result) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 12')

    def test_using_path_bank_node_survives_deletion_during_later_selector_and_pinned_call(self):
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
TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=row_t
     option_t=STRUCTURE bonus:INTEGER ENDSTRUCTURE
VAR routes:ARRAY[2] OF route_t options:ARRAY[1] OF option_t
    s,result,unused:INTEGER
ROUTINE bump(cell:INTEGER) FROM LIB
ROUTINE choose_option:INTEGER
BEGIN
  PAUSE
  DELETE_NODE(routes[2],1,s)
  RETURN 1
END choose_option
BEGIN
  APPEND_NODE(routes[2],s)
  APPEND_NODE(routes[2],s)
  routes[2,1].amount=11
  routes[2,2].amount=22
  options[1].bonus=3
  USING routes[2,1],options[choose_option()] DO
    bump(amount)
    result=amount+bonus
  ENDUSING
  IF (result=19) AND (routes[2,1].amount=22) THEN WRITE(result) ELSE WRITE(unused) ENDIF
END CHILD
"""
        library="""PROGRAM LIB
ROUTINE bump(cell:INTEGER)
BEGIN
  PAUSE
  cell=cell+5
END bump
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*2)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 19')
        self.assertEqual(result['programs']['CHILD']['values']['ROUTES'][1]['nodes'],[{'AMOUNT':22}])

    def test_using_path_header_follows_assignment_and_keeps_old_record_after_copy_path(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        for selector in ('route', '(route[0])'):
            with self.subTest(selector=selector):
                child=f"""PROGRAM CHILD
TYPE node_t=STRUCTURE mark:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR route,replacement:route_t observed,total,result,s,unused:INTEGER
BEGIN
  route.amount=11
  replacement.amount=7
  total=0
  USING {selector} DO
    route=replacement
    observed=amount
    FOR amount=1 TO 2 DO
      total=total+amount
      IF amount=1 THEN PAUSE ENDIF
    ENDFOR
    amount=observed
    COPY_PATH(replacement,0,0,route,s)
    amount=amount+1
    result=amount
  ENDUSING
  IF (observed=7) AND (total=3) AND (result=8) AND (route.amount=7) THEN WRITE(result) ELSE WRITE(unused) ENDIF
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)])
                self.assert_inputs(report,[])
                self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
                self.assertEqual(result['status'],'completed',result['error'])
                self.assertEqual(result['text_output'],' 8')
                self.assertEqual(result['programs']['CHILD']['values']['ROUTE']['data'],{'AMOUNT':7})

    def test_using_header_from_pinned_path_bank_result_is_private_across_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        types="""TYPE node_t=STRUCTURE mark:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE amount:INTEGER missing:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
"""
        child=f"""PROGRAM CHILD
{types}VAR total,selected,unused:INTEGER
ROUTINE make_bank:ARRAY OF route_t FROM LIB
ROUTINE pick:INTEGER
BEGIN
  PAUSE
  RETURN 2
END pick
BEGIN
  total=0
  USING make_bank()[pick()] DO
    selected=amount
    FOR amount=1 TO 2 DO
      total=total+amount
      IF amount=1 THEN PAUSE ENDIF
    ENDFOR
  ENDUSING
  IF (selected=55) AND (total=3) THEN WRITE(selected,total) ELSE WRITE(unused) ENDIF
END CHILD
"""
        library=f"""PROGRAM LIB
{types}ROUTINE make_bank:ARRAY OF route_t
VAR routes:ARRAY[2] OF route_t
BEGIN
  routes[2].amount=55
  PAUSE
  RETURN routes
END make_bank
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*3)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 55 3')

    def test_detached_using_path_node_cannot_establish_a_for_bound_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t
VAR route:route_t s,reached:INTEGER
ROUTINE lower_bound:INTEGER
BEGIN
  reached=1
  PAUSE
  RETURN 1
END lower_bound
BEGIN
  reached=0
  APPEND_NODE(route,s)
  USING route[1] DO
    DELETE_NODE(route,1,s)
    FOR amount=lower_bound() TO 2 DO ENDFOR
  ENDUSING
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('current owned root',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['REACHED'],0)

    def test_nested_using_borrows_each_selected_record_once_across_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     wrapper_t=STRUCTURE inner:row_t ENDSTRUCTURE
     options_t=STRUCTURE bonus:INTEGER ENDSTRUCTURE
VAR rows:ARRAY[2] OF wrapper_t options:ARRAY[2] OF options_t
    chosen,total,trace,unused:INTEGER
ROUTINE pick_row:INTEGER
BEGIN
  trace=trace*10+1
  PAUSE
  RETURN chosen
END pick_row
ROUTINE pick_option:INTEGER
BEGIN
  trace=trace*10+2
  chosen=2
  PAUSE
  RETURN chosen
END pick_option
BEGIN
  chosen=1
  total=0
  trace=0
  rows[2].inner.amount=79
  options[2].bonus=3
  USING rows[pick_row()],options[pick_option()] DO
    USING inner DO
      FOR amount=1 TO 2 DO
        total=total+amount+bonus
        IF amount=1 THEN PAUSE ENDIF
      ENDFOR
    ENDUSING
  ENDUSING
  IF (total=9) AND (trace=12) AND (rows[2].inner.amount=79) THEN WRITE(total) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*3)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 9')
        first,second=result['programs']['CHILD']['values']['ROWS']
        self.assertEqual(first['INNER']['AMOUNT'],{'uninitialized':True})
        self.assertEqual(second['INNER']['AMOUNT'],79)

    def test_using_private_pinned_result_survives_return_from_paused_for(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        types="TYPE row_t=STRUCTURE amount:INTEGER bonus:INTEGER unused_field:INTEGER ENDSTRUCTURE"
        child=f"""PROGRAM CHILD
{types}
VAR origin:row_t first,second,unused:INTEGER
ROUTINE snapshot(item:row_t):row_t FROM LIB
ROUTINE evaluate:INTEGER
BEGIN
  USING snapshot((origin)) DO
    FOR amount=1 TO 2 DO
      PAUSE
      RETURN amount+bonus
    ENDFOR
  ENDUSING
  RETURN 0
END evaluate
BEGIN
  origin.amount=77
  origin.bonus=10
  origin.unused_field=1
  first=evaluate()
  origin.bonus=20
  second=evaluate()
  IF (first=11) AND (second=21) AND (origin.amount=77) THEN WRITE(first,second) ELSE WRITE(unused) ENDIF
END CHILD
"""
        library=f"""PROGRAM LIB
{types}
ROUTINE snapshot(item:row_t):row_t
VAR captured:row_t
BEGIN
  USING item DO
    captured.amount=amount
    captured.bonus=bonus
    PAUSE
  ENDUSING
  RETURN captured
END snapshot
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*4)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 11 21')
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['ORIGIN']['AMOUNT'],values['ORIGIN']['BONUS']),(77,20))

    def test_using_computed_vector_follows_the_same_fields_after_a_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR number,unused:INTEGER
BEGIN
  USING VEC(1,2,3) DO
    x=x+5
    PAUSE
    IF (x+y+z)=11 THEN number=11 ELSE WRITE(unused) ENDIF
  ENDUSING
  WRITE(number)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 11')

    def test_for_path_counter_keeps_selected_storage_across_selector_bounds_and_body_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        for selector, first, second, storage in (
                ('routes[pick(),1].amount', 'routes[1,1].amount', 'routes[2,1].amount', 'nodes'),
                ('routes[pick()].amount', 'routes[1].amount', 'routes[2].amount', 'data')):
            with self.subTest(selector=selector):
                child=f"""PROGRAM CHILD
TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=row_t PATHHEADER=row_t
VAR routes:ARRAY[2] OF route_t selected,total,s,unused:INTEGER
ROUTINE pick:INTEGER
BEGIN
  PAUSE
  RETURN selected
END pick
ROUTINE initial_bound:INTEGER
BEGIN
  selected=2
  PAUSE
  RETURN 1
END initial_bound
ROUTINE final_bound:INTEGER
BEGIN
  PAUSE
  RETURN {first}+2
END final_bound
BEGIN
  APPEND_NODE(routes[1],s)
  APPEND_NODE(routes[2],s)
  {second}=79
  selected=1
  total=0
  FOR {selector}=initial_bound() TO final_bound() DO
    total=total+{first}
    IF total=1 THEN PAUSE ENDIF
  ENDFOR
  IF (total=6) AND (selected=2) AND ({second}=79) THEN WRITE(total) ELSE WRITE(unused) ENDIF
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)])
                self.assert_inputs(report,[])
                self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*4)
                self.assertEqual(result['status'],'completed',result['error'])
                self.assertEqual(result['text_output'],' 6')
                first_route,second_route=result['programs']['CHILD']['values']['ROUTES']
                first_record=first_route[storage][0] if storage=='nodes' else first_route[storage]
                second_record=second_route[storage][0] if storage=='nodes' else second_route[storage]
                self.assertEqual(first_record['AMOUNT'],{'uninitialized':True})
                self.assertEqual(second_record['AMOUNT'],79)

    def test_repeat_keeps_record_capture_across_live_test_pauses_and_iterations(self):
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
TYPE row_t=STRUCTURE limit:INTEGER ENDSTRUCTURE
VAR data:row_t n,unused:INTEGER
ROUTINE gate:BOOLEAN
BEGIN
  data.limit=99
  PAUSE
  RETURN TRUE
END gate
BEGIN
  n=0
  data.limit=2
  REPEAT
    n=n+1
  UNTIL gate() AND (n>=EVAL(data).limit)
  IF n=2 THEN WRITE(n) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],' 2')
        self.assertEqual(result['programs']['CHILD']['values']['DATA'],{'LIMIT':99})

    def test_nested_array_capture_and_length_survive_pauses_without_reading_missing_leaves(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR n,calls,unused:INTEGER
ROUTINE make:ARRAY[1,2] OF INTEGER
VAR row:ARRAY[1,2] OF INTEGER
BEGIN
  row[1,1]=2
  calls=calls+1
  PAUSE
  RETURN row
END make
ROUTINE pick:INTEGER
BEGIN
  PAUSE
  RETURN 1
END pick
BEGIN
  n=0
  calls=0
  REPEAT
    n=n+1
  UNTIL (n>=EVAL(EVAL(make())[1,pick()])) AND (ARRAY_LEN(EVAL(make()),2)=2)
  IF (n=2) AND (calls=2) THEN WRITE(n,':',calls) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(tuple(map(int,result['text_output'].split(':'))),(2,2))

    def test_array_length_resumes_its_selector_and_dimension_without_array_cell_reads(self):
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
VAR grid:ARRAY[2,3,4] OF INTEGER n,unused:INTEGER
ROUTINE pick:INTEGER
BEGIN
  PAUSE
  RETURN 1
END pick
ROUTINE axis:INTEGER
BEGIN
  PAUSE
  RETURN 2
END axis
BEGIN
  n=ARRAY_LEN(grid[pick()],axis())
  IF n=4 THEN WRITE(n) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],' 4')
        invalid_main=main.replace('END MAIN','  WAIT FOR PAUSE PROGRAM[2]\nEND MAIN')
        invalid_child=child.replace('RETURN 2','RETURN 3')
        report,result=self.prepare([('MAIN',invalid_main),('CHILD',invalid_child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('ARRAY_LEN dimension 3 outside 1..2',result['error']['message'])

    def test_missing_leaf_in_a_captured_array_fails_after_the_live_subscript_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  WRITE('waiting')
END MAIN
"""
        child="""PROGRAM CHILD
VAR attempts,selected:INTEGER
ROUTINE make:ARRAY OF INTEGER
VAR row:ARRAY[2] OF INTEGER
BEGIN
  row[1]=7
  RETURN row
END make
ROUTINE choose:INTEGER
BEGIN
  selected=1
  PAUSE
  RETURN 2
END choose
BEGIN
  selected=0
  attempts=0
  REPEAT attempts=attempts+1 UNTIL EVAL(make())[choose()]=7
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'waiting')

        main=main.replace("  WRITE('waiting')", """  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]""")
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('uninitialized',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['SELECTED'],1)

    def test_builtin_keeps_earlier_arguments_across_two_pauses(self):
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
VAR source,result:STRING[8] origin,unused:INTEGER
ROUTINE start_at:INTEGER
BEGIN
  source='wxyz'
  PAUSE
  RETURN origin
END start_at
ROUTINE count_for:INTEGER
BEGIN
  origin=4
  PAUSE
  RETURN 2
END count_for
BEGIN
  source='abcd'
  origin=2
  result=SUB_STR(source,start_at(),count_for())
  IF result='bc' THEN WRITE(result) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'bc')
        self.assertEqual(result['programs']['CHILD']['values']['ORIGIN'],4)

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

    def test_linked_aggregate_arguments_keep_private_data_and_the_original_reference(self):
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
  WRITE(s,':',text,CR)
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_t=STRUCTURE amount:INTEGER done:INTEGER ENDSTRUCTURE
VAR source:ARRAY[2] OF INTEGER rows:ARRAY[2] OF row_t
    slot,h,s,unused:INTEGER
ROUTINE work(snapshot:ARRAY OF INTEGER; target:row_t; increment:INTEGER) FROM LIBA
ROUTINE advance:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  source[1]=99
  slot=2
  PAUSE
  CLOSE_TPE(h,s)
  RETURN 5
END advance
BEGIN
  source[1]=7
  rows[2].amount=22
  slot=1
  work((source),rows[slot],advance())
  IF (rows[1].amount=12) AND (rows[1].done=5) AND (rows[2].amount=22) THEN
    WRITE(rows[1].amount,':',rows[1].done,':',source[1],CR)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIBA
TYPE row_t=STRUCTURE amount:INTEGER done:INTEGER ENDSTRUCTURE
ROUTINE work(snapshot:ARRAY OF INTEGER; target:row_t; increment:INTEGER)
BEGIN
  target.amount=snapshot[1]+increment
  snapshot[2]=increment
  PAUSE
  target.done=snapshot[2]
END work
BEGIN
END LIBA
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIBA',library)])
        self.assert_inputs(report,[('variable','CHILD','SOURCE','conditional'),
                                   ('teach_string_register','SHARED','1','required')])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        blocked,ready,output=result['text_output'].splitlines()
        first_status,previous=blocked.split(':')
        next_status,current=ready.split(':')
        self.assertEqual((int(first_status),previous,int(next_status),current),(4,'prior',0,'ready'))
        self.assertEqual(tuple(map(int,output.split(':'))),(12,5,99))
        self.assertEqual(result['programs']['CHILD']['values']['SOURCE'],[99,{'uninitialized':True}])

    def test_pausing_array_prefix_is_a_private_argument_with_concrete_shape(self):
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
VAR grid:ARRAY[2,2] OF STRING[4] unused:INTEGER
ROUTINE choose_row:INTEGER
BEGIN
  PAUSE
  RETURN 2
END choose_row
ROUTINE use(row:ARRAY OF STRING)
BEGIN
  row[1]='private'
  PAUSE
  IF row[2]='read' THEN WRITE(row[1],row[2]) ELSE WRITE(unused) ENDIF
END use
BEGIN
  grid[2,1]='keep'
  grid[2,2]='read'
  use(grid[choose_row()])
  WRITE(grid[2,1])
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'privreadkeep')

    def test_pausing_array_result_flows_into_a_private_argument_and_write(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
ROUTINE make:ARRAY OF INTEGER
VAR values:ARRAY[2] OF INTEGER
BEGIN
  values[1]=7
  PAUSE
  RETURN values
END make
ROUTINE complete(snapshot:ARRAY OF INTEGER):ARRAY OF INTEGER
BEGIN
  snapshot[2]=9
  PAUSE
  RETURN snapshot
END complete
ROUTINE width_value:INTEGER
BEGIN
  PAUSE
  RETURN 3
END width_value
BEGIN
  WRITE(complete(make())::width_value())
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'  7  9')

    def test_bad_forwarded_array_shape_rejects_entry_after_later_argument_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  WRITE('waiting')
END MAIN
"""
        child="""PROGRAM CHILD
VAR data:ARRAY[3] OF INTEGER entered:INTEGER
ROUTINE gate:INTEGER
BEGIN
  PAUSE
  RETURN 1
END gate
ROUTINE take(values:ARRAY[2] OF INTEGER; step:INTEGER)
BEGIN
  entered=step
  PAUSE
END take
ROUTINE forward(values:ARRAY OF INTEGER)
BEGIN
  take(values,gate())
END forward
BEGIN
  entered=0
  forward(data)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'waiting')
        main=main.replace("  WRITE('waiting')", """  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]""")
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('Parameter binding type mismatch',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)

    def test_aggregate_result_assignment_captures_rhs_before_a_pausing_prefix_target(self):
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
  WRITE(s,':',text,CR)
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR grid:ARRAY[2,2] OF INTEGER source:ARRAY[2] OF INTEGER
    h,s,unused:INTEGER
ROUTINE make:ARRAY OF INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  PAUSE
  RETURN source
END make
ROUTINE pick:INTEGER
BEGIN
  CLOSE_TPE(h,s)
  source[1]=98
  PAUSE
  RETURN 1
END pick
ROUTINE change(saved:INTEGER)
BEGIN
  grid[pick()]=make()
  saved=99
END change
BEGIN
  source[1]=7
  source[2]=9
  grid[2,1]=11
  change(grid[1,2])
  IF (grid[1,1]=7) AND (grid[1,2]=99) THEN
    WRITE(grid[1,1],':',grid[1,2],':',source[1],CR)
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
        self.assertEqual(tuple(map(int,output.split(':'))),(7,99,98))
        self.assertEqual(result['programs']['CHILD']['values']['GRID'][0],[7,99])

    def test_record_result_assignment_preserves_known_and_missing_fields(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_t=STRUCTURE amount:INTEGER pending:INTEGER ENDSTRUCTURE
VAR target:row_t unused:INTEGER
ROUTINE make:row_t
VAR local:row_t
BEGIN
  local.amount=7
  PAUSE
  RETURN local
END make
BEGIN
  target.pending=9
  target=make()
  IF target.amount=7 THEN WRITE(target.amount) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],' 7')
        self.assertEqual(result['programs']['CHILD']['values']['TARGET'],
                         {'AMOUNT':7,'PENDING':{'uninitialized':True}})

    def test_computed_array_keeps_its_fields_and_earlier_indices_across_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
VAR source:ARRAY[2,2] OF row_t selected,seen,unused:INTEGER
ROUTINE make:ARRAY[2,2] OF row_t
BEGIN
  PAUSE
  RETURN source
END make
ROUTINE first_index:INTEGER
BEGIN
  PAUSE
  RETURN selected
END first_index
ROUTINE second_index:INTEGER
BEGIN
  selected=2
  source[1,2].amount=99
  PAUSE
  RETURN 2
END second_index
BEGIN
  selected=1
  source[1,1].amount=1
  source[1,2].amount=7
  source[2,1].amount=2
  source[2,2].amount=15
  seen=make()[first_index(),second_index()].amount
  IF seen=7 THEN WRITE(seen) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],' 7')
        self.assertEqual(result['programs']['CHILD']['values']['SOURCE'][0][1]['AMOUNT'],99)

    def test_bad_flat_result_index_is_checked_after_the_later_subscript_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  WRITE('waiting')
END MAIN
"""
        child="""PROGRAM CHILD
VAR bad,seen,entered:INTEGER
ROUTINE make:ARRAY[1,2] OF INTEGER
VAR source:ARRAY[1,2] OF INTEGER
BEGIN
  source[1,1]=7
  RETURN source
END make
ROUTINE later:INTEGER
BEGIN
  entered=1
  PAUSE
  RETURN 1
END later
BEGIN
  bad=0
  entered=0
  seen=make()[bad,later()]
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'waiting')
        main=main.replace("  WRITE('waiting')", """  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]""")
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('outside',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],1)

    def test_incompatible_result_shape_leaves_the_selected_target_unchanged(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  WRITE('waiting')
END MAIN
"""
        child="""PROGRAM CHILD
VAR target:ARRAY[2,2] OF INTEGER
ROUTINE make:ARRAY OF INTEGER
VAR source:ARRAY[3] OF INTEGER
BEGIN
  source[1]=7
  RETURN source
END make
ROUTINE pick:INTEGER
BEGIN
  PAUSE
  RETURN 1
END pick
BEGIN
  target[1,1]=50
  target[1,2]=60
  target[pick()]=make()
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'waiting')
        main=main.replace("  WRITE('waiting')", """  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]""")
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('matching logical dimensions',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['TARGET'][0],[50,60])

    def test_receiver_conversion_uses_the_array_prefix_selected_after_a_pause(self):
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
VAR grid:ARRAY[2,2] OF STRING[3] source:ARRAY[2] OF STRING[6] unused:INTEGER
ROUTINE make:ARRAY OF STRING[6]
BEGIN
  PAUSE
  RETURN source
END make
ROUTINE pick:INTEGER
BEGIN
  source[1]='new'
  PAUSE
  RETURN 2
END pick
BEGIN
  source[1]='apple'
  source[2]='plum'
  grid[1,1]='old'
  grid[pick()]=make()
  IF grid[2,1]='app' THEN WRITE(grid[2,1],grid[2,2]) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'appplu')
        self.assertEqual(result['programs']['CHILD']['values']['GRID'][0][0],'old')

    def test_static_array_conversion_precedes_the_pausing_destination_selector(self):
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
TYPE box_t=STRUCTURE cells:ARRAY[2] OF BYTE ENDSTRUCTURE
VAR boxes:ARRAY[1] OF box_t entered:INTEGER
ROUTINE make:ARRAY OF INTEGER
VAR source:ARRAY[2] OF INTEGER
BEGIN
  source[1]=7
  source[2]=256
  PAUSE
  RETURN source
END make
ROUTINE pick:INTEGER
BEGIN
  entered=1
  PAUSE
  RETURN 1
END pick
BEGIN
  boxes[1].cells[1]=10
  boxes[1].cells[2]=20
  entered=0
  boxes[pick()].cells=make()
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('BYTE value outside',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)
        self.assertEqual(result['programs']['CHILD']['values']['BOXES'][0]['CELLS'],[10,20])

        good_main=main.replace('END MAIN','  CONT_TASK(\'CHILD\',s)\nEND MAIN')
        good_child=child.replace('source[2]=256','source[2]=255')
        report,result=self.prepare([('MAIN',good_main),('CHILD',good_child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],1)
        self.assertEqual(result['programs']['CHILD']['values']['BOXES'][0]['CELLS'],[7,255])

    def test_converted_argument_is_private_before_a_later_argument_pauses(self):
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
VAR source:ARRAY[2] OF INTEGER unused:INTEGER
ROUTINE advance:INTEGER
BEGIN
  source[1]=99
  PAUSE
  RETURN 5
END advance
ROUTINE take(snapshot:ARRAY OF REAL; step:INTEGER)
BEGIN
  snapshot[1]=snapshot[1]+step
  PAUSE
  IF snapshot[1]=12.0 THEN WRITE(snapshot[1]::0::1) ELSE WRITE(unused) ENDIF
END take
BEGIN
  source[1]=7
  source[2]=9
  take(source,advance())
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],' 12.0')
        self.assertEqual(result['programs']['CHILD']['values']['SOURCE'],[99,9])

    def test_converted_record_return_preserves_a_known_field_and_partial_storage(self):
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
TYPE source_t=STRUCTURE amount:INTEGER note:STRING[8] ENDSTRUCTURE
     target_t=STRUCTURE amount:REAL note:STRING[4] ENDSTRUCTURE
VAR result:target_t unused:INTEGER
ROUTINE make:target_t
VAR local:source_t
BEGIN
  local.amount=7
  PAUSE
  RETURN local
END make
ROUTINE width_value:INTEGER
BEGIN
  PAUSE
  RETURN 0
END width_value
BEGIN
  result=make()
  IF result.amount=7.0 THEN WRITE(result.amount::width_value()::1) ELSE WRITE(unused) ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],' 7.0')
        self.assertEqual(result['programs']['CHILD']['values']['RESULT'],
                         {'AMOUNT':7.0,'NOTE':{'uninitialized':True}})

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

    def test_scalar_write_retains_the_value_across_width_and_base_pauses(self):
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
VAR n,h,s,trace:INTEGER
ROUTINE width_value:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  n=32
  trace=trace*10+1
  PAUSE
  RETURN 4
END width_value
ROUTINE base_value:INTEGER
BEGIN
  CLOSE_TPE(h,s)
  n=99
  trace=trace*10+2
  PAUSE
  RETURN 16
END base_value
BEGIN
  n=10
  trace=0
  WRITE('V=',n::width_value()::base_value(),'/',n,CR)
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
        self.assertEqual(output,'V= 00A/ 99')
        self.assertEqual(result['programs']['CHILD']['values']['TRACE'],12)

    def test_failed_write_item_format_does_not_reach_the_following_item(self):
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
VAR reached:INTEGER
ROUTINE invalid_width:INTEGER
BEGIN
  PAUSE
  RETURN 255
END invalid_width
ROUTINE later_item:INTEGER
BEGIN
  reached=1
  PAUSE
  RETURN 42
END later_item
BEGIN
  reached=0
  WRITE('earlier',7::invalid_width(),later_item())
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('WRITE width',result['error']['message'])
        self.assertEqual(result['text_output'],'')
        self.assertEqual(result['programs']['CHILD']['values']['REACHED'],0)

    def test_aggregate_write_captures_nested_record_fields_before_two_pausing_formats(self):
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
  WRITE(s,':',text,CR)
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE pair_t=STRUCTURE first:INTEGER second:ARRAY[1] OF INTEGER ENDSTRUCTURE
VAR numbers:pair_t h,s:INTEGER
ROUTINE width_value:INTEGER
BEGIN
  OPEN_TPE('Shared',TPE_RDACC,TPE_ALLREJ,h,s)
  numbers.first=88
  PAUSE
  RETURN 4
END width_value
ROUTINE base_value:INTEGER
BEGIN
  CLOSE_TPE(h,s)
  numbers.second[1]=99
  PAUSE
  RETURN 16
END base_value
BEGIN
  numbers.first=10
  numbers.second[1]=15
  WRITE('V=',numbers::width_value()::base_value(),'/',numbers.second[1],CR)
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
        self.assertEqual(output,'V= 00A 00F/ 99')
        self.assertEqual(result['programs']['CHILD']['values']['NUMBERS'],{'FIRST':88,'SECOND':[99]})

    def test_pausing_aggregate_selector_finishes_before_the_fields_are_captured(self):
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
VAR grid:ARRAY[2,2] OF INTEGER
ROUTINE choose_row:INTEGER
BEGIN
  PAUSE
  grid[1,1]=7
  RETURN 1
END choose_row
ROUTINE width_value:INTEGER
BEGIN
  grid[1,1]=55
  grid[1,2]=66
  PAUSE
  RETURN 3
END width_value
BEGIN
  grid[1,1]=1
  grid[1,2]=9
  WRITE(grid[choose_row()]::width_value(),'|',VEC(1,2,3)::0::1)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                     'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'  7  9| 1.0 2.0 3.0')

    def test_missing_aggregate_field_prevents_a_pause_in_the_format(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_t=STRUCTURE number:INTEGER label:STRING[8] ENDSTRUCTURE
VAR row:row_t entered:INTEGER
ROUTINE width_value:INTEGER
BEGIN
  entered=1
  PAUSE
  RETURN 4
END width_value
BEGIN
  entered=0
  row.number=7
  WRITE(row::width_value())
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[('variable','CHILD','ROW','conditional')])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('uninitialized',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)

    def test_plain_aggregate_write_can_precede_a_top_level_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR row:ARRAY[2] OF INTEGER
BEGIN
  row[1]=7
  row[2]=9
  WRITE(row)
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],' 7 9')

    def test_aggregate_write_checks_expanded_batch_count_after_the_last_item(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  WRITE('waiting')
END MAIN
"""
        items=','.join(['letters']*32+['last_item()'])
        child=f"""PROGRAM CHILD
VAR letters:ARRAY[32] OF STRING[1] i:INTEGER
ROUTINE last_item:STRING[1]
BEGIN
  PAUSE
  RETURN ''
END last_item
BEGIN
  FOR i=1 TO 32 DO letters[i]='' ENDFOR
  WRITE({items})
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'waiting')

        main=main.replace("  WRITE('waiting')", """  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]""")
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('1024 expanded scalar items',result['error']['message'])
        self.assertEqual(result['text_output'],'')

    def test_write_batch_length_is_checked_after_pausing_in_a_later_item(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  WRITE('waiting')
END MAIN
"""
        child=f"""PROGRAM CHILD
ROUTINE last_item:INTEGER
BEGIN
  PAUSE
  RETURN 1
END last_item
BEGIN
  WRITE('{'a'*130}','{'b'*130}',last_item())
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'waiting')

        main=main.replace("  WRITE('waiting')", """  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]""")
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('WRITE combined output',result['error']['message'])
        self.assertEqual(result['text_output'],'')

    def test_path_range_write_captures_reverse_nodes_and_header_before_a_pausing_edit(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     header_t=STRUCTURE total:INTEGER ENDSTRUCTURE
VAR route:PATH NODEDATA=node_t PATHHEADER=header_t seed:node_t s:INTEGER
ROUTINE width_value:INTEGER
BEGIN
  route[1].amount=44
  DELETE_NODE(route,2,s)
  PAUSE
  RETURN 3
END width_value
BEGIN
  route.total=2
  seed.amount=7
  APPEND_NODE(route,seed,s)
  seed.amount=9
  APPEND_NODE(route,seed,s)
  WRITE(route[2..0]::width_value(),'|',route)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'  9  7  2| 2 44')
        route=result['programs']['CHILD']['values']['ROUTE']
        self.assertEqual(route,{'data':{'TOTAL':2},'nodes':[{'AMOUNT':44}]})

    def test_path_range_retains_selected_bank_cell_across_pausing_bounds(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     header_t=STRUCTURE total:INTEGER ENDSTRUCTURE
VAR routes:ARRAY[2] OF PATH NODEDATA=node_t PATHHEADER=header_t
    seed:node_t bank,upper,s,unused:INTEGER
ROUTINE first_bound:INTEGER
BEGIN
  bank=2
  seed.amount=9
  APPEND_NODE(routes[1],seed,s)
  PAUSE
  RETURN upper
END first_bound
ROUTINE last_bound:INTEGER
BEGIN
  upper=1
  routes[1,1].amount=8
  PAUSE
  RETURN 0
END last_bound
ROUTINE width_value:INTEGER
BEGIN
  DELETE_NODE(routes[1],2,s)
  PAUSE
  RETURN 3
END width_value
BEGIN
  bank=1
  upper=2
  routes[1].total=4
  routes[2].total=88
  seed.amount=7
  APPEND_NODE(routes[1],seed,s)
  WRITE(routes[bank,first_bound()..last_bound()]::width_value(),'|',routes[bank])
  IF s<>0 THEN
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'  9  8  4| 88')
        self.assertEqual(result['programs']['CHILD']['values']['ROUTES'][0],
                         {'data':{'TOTAL':4},'nodes':[{'AMOUNT':8}]})

    def test_dynamic_path_header_index_can_pause_after_bank_selection(self):
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
TYPE header_t=STRUCTURE total:INTEGER ENDSTRUCTURE
VAR routes:ARRAY[2] OF PATH PATHHEADER=header_t selected:INTEGER
ROUTINE pick_bank:INTEGER
BEGIN
  PAUSE
  RETURN selected
END pick_bank
ROUTINE pick_record:INTEGER
BEGIN
  selected=2
  routes[1].total=13
  PAUSE
  RETURN 0
END pick_record
BEGIN
  selected=1
  routes[1].total=11
  routes[2].total=22
  WRITE(routes[pick_bank(),pick_record()]::3,'|',routes[selected])
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],' 13| 22')

    def test_path_range_checks_bounds_after_the_second_bound_resumes(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  WRITE('waiting')
END MAIN
"""
        child="""PROGRAM CHILD
TYPE header_t=STRUCTURE total:INTEGER ENDSTRUCTURE
VAR route:PATH PATHHEADER=header_t
ROUTINE invalid_first:INTEGER
BEGIN
  RETURN -1
END invalid_first
ROUTINE last_bound:INTEGER
BEGIN
  PAUSE
  RETURN 0
END last_bound
BEGIN
  route.total=4
  WRITE(route[invalid_first()..last_bound()])
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'waiting')

        main=main.replace("WRITE('waiting')", "CONT_TASK('CHILD',s) WAIT FOR PAUSE PROGRAM[2]")
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('PATH I/O range',result['error']['message'])
        self.assertEqual(result['text_output'],'')

    def test_pausing_queue_row_selector_captures_current_values_before_formats(self):
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
VAR queues:ARRAY[2,2] OF QUEUE_TYPE backing:ARRAY[2] OF INTEGER
    first,last,s,unused:INTEGER
ROUTINE bank_row:INTEGER
BEGIN
  APPEND_QUEUE(9,queues[2,1],backing,last,s)
  PAUSE
  RETURN 2
END bank_row
ROUTINE width_value:INTEGER
BEGIN
  MODIFY_QUEUE(77,first,queues[2,1],backing,s)
  PAUSE
  RETURN 3
END width_value
BEGIN
  INIT_QUEUE(queues[2,1])
  INIT_QUEUE(queues[2,2])
  APPEND_QUEUE(7,queues[2,1],backing,first,s)
  WRITE(queues[bank_row()]::width_value(),'|',queues[2,1])
  IF s<>0 THEN
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'  7  9| 77 9')
        self.assertEqual(result['programs']['CHILD']['values']['BACKING'],[77,9])

    def test_missing_path_leaf_prevents_the_format_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
VAR route:PATH NODEDATA=node_t s,entered:INTEGER
ROUTINE width_value:INTEGER
BEGIN
  entered=1
  PAUSE
  RETURN 3
END width_value
BEGIN
  entered=0
  APPEND_NODE(route,s)
  WRITE(route::width_value())
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('uninitialized',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)

    def test_queue_array_capture_preserves_entry_order_across_a_pausing_append(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR queues:ARRAY[2] OF QUEUE_TYPE left_buf,right_buf:ARRAY[2] OF INTEGER
    entry,s,unused:INTEGER
ROUTINE width_value:INTEGER
BEGIN
  APPEND_QUEUE(11,queues[2],right_buf,entry,s)
  PAUSE
  RETURN 3
END width_value
BEGIN
  INIT_QUEUE(queues[1])
  INIT_QUEUE(queues[2])
  APPEND_QUEUE(7,queues[1],left_buf,entry,s)
  APPEND_QUEUE(9,queues[1],left_buf,entry,s)
  APPEND_QUEUE(88,queues[1],left_buf,entry,s)
  IF (s=2) AND (entry=2) THEN
    WRITE(queues::width_value(),'|',queues[2])
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'  7  9| 11')
        self.assertEqual(result['programs']['CHILD']['values']['LEFT_BUF'],[7,9])
        self.assertEqual(result['programs']['CHILD']['values']['RIGHT_BUF'],[11,0])

    def test_queue_write_captures_entries_before_pausing_edits(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR q:QUEUE_TYPE backing:ARRAY[3] OF INTEGER
    first,second,last,item,removed,s,unused:INTEGER
ROUTINE edit_queue:INTEGER
BEGIN
  INSERT_QUEUE(11,second,q,backing,s)
  MODIFY_QUEUE(77,first,q,backing,s)
  DELETE_QUEUE(second,q,backing,s)
  GET_QUEUE(q,backing,item,removed,s)
  PAUSE
  APPEND_QUEUE(23,q,backing,last,s)
  RETURN 3
END edit_queue
BEGIN
  INIT_QUEUE(q)
  APPEND_QUEUE(7,q,backing,first,s)
  APPEND_QUEUE(9,q,backing,second,s)
  WRITE(q::edit_queue(),'|',q)
  IF (item=77) AND (removed=1) AND (last=4) AND (s=0) THEN
    WRITE('|',backing)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'  7  9| 11 23| 11 23 0')
        self.assertEqual(result['programs']['CHILD']['values']['BACKING'],[11,23,0])

    def test_queue_call_retains_scalar_arguments_before_a_pausing_reference(self):
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
VAR queues:ARRAY[2] OF QUEUE_TYPE backing:ARRAY[2] OF INTEGER
    stored,handle,s,unused:INTEGER
ROUTINE anchor:INTEGER
BEGIN
  stored=99
  PAUSE
  RETURN handle
END anchor
ROUTINE target_queue:INTEGER
BEGIN
  PAUSE
  RETURN 2
END target_queue
BEGIN
  INIT_QUEUE(queues[2])
  APPEND_QUEUE(8,queues[2],backing,handle,s)
  stored=5
  INSERT_QUEUE(stored,anchor(),queues[target_queue()],backing,s)
  IF (stored=99) AND (backing[1]=5) AND (backing[2]=8) AND (s=0) THEN
    WRITE(queues[2])
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
        self.assertEqual(result['text_output'],' 5 8')

    def test_queue_copy_and_empty_get_preserve_unwritten_outputs(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR q:QUEUE_TYPE backing,dest:ARRAY[3] OF INTEGER
    first,last,count,s,item,removed,unused:INTEGER
ROUTINE skip_one:INTEGER
BEGIN
  PAUSE
  RETURN 1
END skip_one
BEGIN
  INIT_QUEUE(q)
  APPEND_QUEUE(31,q,backing,first,s)
  APPEND_QUEUE(32,q,backing,last,s)
  dest[2]=55
  dest[3]=66
  COPY_QUEUE(q,backing,first,skip_one(),dest,count,s)
  IF (count=1) AND (s=0) THEN
    COPY_QUEUE(q,backing,99,0,dest,count,s)
    IF (count=0) AND (s=1) THEN
      DELETE_QUEUE(first,q,backing,s)
      GET_QUEUE(q,backing,item,removed,s)
      GET_QUEUE(q,backing,item,removed,s)
      IF (item=32) AND (removed=2) AND (s=61002) THEN
        WRITE(dest,'|',backing)
      ELSE
        WRITE(unused)
      ENDIF
    ELSE
      WRITE(unused)
    ENDIF
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],' 32 55 66| 0 0 0')
        self.assertEqual(result['programs']['CHILD']['values']['DEST'],[32,55,66])

    def test_resumed_queue_call_declines_a_different_backing_array(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR q:QUEUE_TYPE backing,other:ARRAY[2] OF INTEGER
    entry,s:INTEGER item:ARRAY[1] OF INTEGER
ROUTINE target:INTEGER
BEGIN
  PAUSE
  RETURN 1
END target
BEGIN
  INIT_QUEUE(q)
  APPEND_QUEUE(7,q,backing,entry,s)
  GET_QUEUE(q,other,item[target()],entry,s)
  WRITE(item[1])
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('original backing ARRAY',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['BACKING'],[7,0])
        self.assertEqual(result['programs']['CHILD']['values']['ENTRY'],1)

    def test_empty_queue_validates_its_format_before_the_later_item(self):
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
VAR data:QUEUE_TYPE entered:INTEGER
ROUTINE width_value:INTEGER
BEGIN
  PAUSE
  RETURN 255
END width_value
ROUTINE later:INTEGER
BEGIN
  entered=1
  PAUSE
  RETURN 7
END later
BEGIN
  entered=0
  INIT_QUEUE(data)
  WRITE(data::width_value(),later())
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('WRITE width',result['error']['message'])
        self.assertEqual(result['text_output'],'')
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)

    def test_pausing_write_uses_the_default_route_from_its_own_module(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
%CRTDEVICE
ROUTINE value_now:INTEGER
BEGIN
  PAUSE
  RETURN 1
END value_now
BEGIN
  WRITE(value_now())
END CHILD
"""
        for alias in ('TPDISPLAY','OUTPUT'):
            with self.subTest(alias=alias):
                report,_=self.prepare([('MAIN',main),('CHILD',child)],replay=False,
                                      predefined_files={alias:{'name':'out','mode':'WO'}})
                if alias=='OUTPUT':
                    self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
                else:
                    self.assert_task_gaps(report,['task-scheduling','task-wait'])

    def test_pausing_default_memory_file_write_can_exceed_the_console_limit(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child=f"""PROGRAM CHILD
%CRTDEVICE
ROUTINE value_now:INTEGER
BEGIN
  PAUSE
  RETURN 7
END value_now
BEGIN
  WRITE('{'a'*130}','{'b'*130}',value_now(),CR)
  CLOSE FILE OUTPUT
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],
                                   predefined_files={'OUTPUT':{'name':'out','mode':'WO',
                                                               'attributes':{'eol':13}}},
                                   files={'out':'old'})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertIn({'service':'predefined_files','address':'OUTPUT'},report['context_requirements'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'')
        self.assertEqual(result['context']['files']['out']['hex'],(b'a'*130+b'b'*130+b' 7\r').hex())

    def test_explicit_binary_file_preserves_queue_capture_across_format_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR q:QUEUE_TYPE backing:ARRAY[2] OF INTEGER first,last,s,unused:INTEGER
ROUTINE word_width:INTEGER
BEGIN
  MODIFY_QUEUE(42,first,q,backing,s)
  PAUSE
  RETURN 2
END word_width
BEGIN
  INIT_QUEUE(q)
  APPEND_QUEUE(258,q,backing,first,s)
  APPEND_QUEUE(-2,q,backing,last,s)
  WRITE OUTPUT(q::word_width(),CR)
  WRITE OUTPUT(q::2)
  CLOSE FILE OUTPUT
  WRITE TPDISPLAY(9::1)
  CLOSE FILE TPDISPLAY
  IF s<>0 THEN
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],
                                   predefined_files={'OUTPUT':{'name':'out','mode':'WB',
                                                               'attributes':{'reverse':True}},
                                                     'TPDISPLAY':{'name':'out','mode':'APB'}},files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'')
        self.assertEqual(result['context']['files']['out']['hex'],'0102fffe0a002afffe09')

    def test_invalid_binary_format_prevents_later_item_from_reaching_pause(self):
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
VAR entered:INTEGER
ROUTINE bad_width:INTEGER
BEGIN
  PAUSE
  RETURN 3
END bad_width
ROUTINE later:INTEGER
BEGIN
  entered=1
  PAUSE
  RETURN 7
END later
BEGIN
  entered=0
  WRITE OUTPUT(9::bad_width(),later())
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],
                                   predefined_files={'OUTPUT':{'name':'out','mode':'WB'}},files={})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('binary field type/width',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)
        self.assertIn('Close predefined FILE handles',result['capture_errors']['context']['message'])

    def test_competing_predefined_file_alias_cannot_open_during_a_write_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  RUN_TASK('PEER',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[3]
END MAIN
"""
        child="""PROGRAM CHILD
ROUTINE value_now:INTEGER
BEGIN
  PAUSE
  RETURN 17
END value_now
BEGIN
  WRITE OUTPUT(value_now())
END CHILD
"""
        peer="""PROGRAM PEER
VAR entered:INTEGER
ROUTINE value_now:INTEGER
BEGIN
  entered=1
  PAUSE
  RETURN 19
END value_now
BEGIN
  entered=0
  WRITE TPDISPLAY(value_now())
END PEER
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('PEER',peer)],
                                   predefined_files={'OUTPUT':{'name':'out','mode':'WO'},
                                                     'TPDISPLAY':{'name':'out','mode':'WO'}},files={})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('already open',result['error']['message'])
        self.assertEqual(result['programs']['PEER']['values']['ENTERED'],0)
        self.assertIn('Close predefined FILE handles',result['capture_errors']['context']['message'])

    def test_pending_memory_write_rechecks_shared_update_cursor_on_resume(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  RUN_TASK('PEER',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[3]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR entered:INTEGER
ROUTINE value_now:INTEGER
BEGIN
  PAUSE
  RETURN 17
END value_now
BEGIN
  entered=0
  WRITE OUTPUT(value_now()::2)
  entered=1
  PAUSE
END CHILD
"""
        peer="""PROGRAM PEER
BEGIN
  WRITE OUTPUT(9::2,11::1)
  PAUSE
END PEER
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('PEER',peer)],
                                   predefined_files={'OUTPUT':{'name':'out','mode':'UDB'}},
                                   files={'out':'0000'})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('UD FILE WRITE must replace bytes',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)

    def test_declared_file_array_retains_open_selector_through_pausing_operands(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR streams:ARRAY[2] OF FILE chosen,unused:INTEGER
ROUTINE select_cell:INTEGER
BEGIN
  PAUSE
  RETURN chosen
END select_cell
ROUTINE file_mode:STRING[4]
BEGIN
  chosen=2
  PAUSE
  RETURN 'WB'
END file_mode
ROUTINE file_name:STRING[8]
BEGIN
  PAUSE
  RETURN 'first'
END file_name
BEGIN
  chosen=1
  OPEN FILE streams[select_cell()](file_mode(),file_name())
  WRITE streams[1](258::2,CR)
  IF (GET_FILE_POS(streams[1])=3) AND (BYTES_LEFT(streams[1])=0) THEN
    chosen=1
    CLOSE FILE streams[select_cell()]
  ELSE
    WRITE(unused)
  ENDIF
  OPEN FILE streams[2]('WO','second')
  WRITE streams[2]('text')
  CLOSE FILE streams[2]
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation','task-wait','task-continuation',
                                      'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['context']['files'],{'first':{'hex':'02010a'},
                                                    'second':{'hex':'74657874'}})

    def test_write_captures_declared_handle_before_the_operand_opens_it(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR stream:FILE unused:INTEGER
ROUTINE open_now:INTEGER
BEGIN
  OPEN FILE stream('WB','out')
  PAUSE
  RETURN 258
END open_now
BEGIN
  WRITE stream(open_now()::2)
  CLOSE FILE stream
  OPEN FILE stream('AP','out')
  WRITE stream(9)
  CLOSE FILE stream
  IF IO_STATUS(stream)<>0 THEN
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['text_output'],'')
        self.assertEqual(result['context']['files']['out']['hex'],'020109000000')

    def test_unclosed_routine_file_stays_busy_after_return(self):
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
VAR other:FILE entered:INTEGER
ROUTINE open_local
VAR stream:FILE
BEGIN
  OPEN FILE stream('WO','out')
  PAUSE
END open_local
BEGIN
  entered=0
  open_local
  OPEN FILE other('WO','out')
  entered=1
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('already open',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)

    def test_closed_declared_file_query_respects_a_pausing_selector(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR streams:ARRAY[2] OF FILE unused:INTEGER
ROUTINE pick_cell:INTEGER
BEGIN
  PAUSE
  RETURN 2
END pick_cell
BEGIN
  OPEN FILE streams[2]('WO','out')
  CLOSE FILE streams[2]
  IF IO_STATUS(streams[pick_cell()])=0 THEN
    OPEN FILE streams[2]('WO','out')
    WRITE streams[2](17)
    CLOSE FILE streams[2]
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['context']['files']['out']['hex'],'203137')

    def test_file_attributes_keep_the_selected_handle_across_a_pause_and_reopen(self):
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
VAR streams:ARRAY[2] OF FILE selected:INTEGER
ROUTINE pick_stream:INTEGER
BEGIN
  PAUSE
  RETURN selected
END pick_stream
ROUTINE end_code:INTEGER
BEGIN
  selected=2
  PAUSE
  RETURN 124
END end_code
BEGIN
  selected=1
  SET_FILE_ATR(streams[pick_stream()],ATR_EOL,end_code())
  OPEN FILE streams[1]('WO','text')
  WRITE streams[1]('A',CR)
  CLOSE FILE streams[1]
  SET_FILE_ATR(streams[2],ATR_UF)
  SET_FILE_ATR(streams[2],ATR_REVERSE)
  OPEN FILE streams[2]('WO','binary')
  WRITE streams[2](258::2)
  CLOSE FILE streams[2]
  OPEN FILE streams[1]('A','text')
  WRITE streams[1]('B',CR)
  CLOSE FILE streams[1]
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['context']['files'],{'text':{'hex':'417c427c'},'binary':{'hex':'0102'}})

    def test_file_seek_and_availability_keep_captured_outputs_across_pauses(self):
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
VAR stream:FILE statuses:ARRAY[2] OF INTEGER
    inner,remaining,s,unused:INTEGER accepted:BOOLEAN
ROUTINE target_pos:INTEGER
BEGIN
  PAUSE
  RETURN 2
END target_pos
ROUTINE status_cell:INTEGER
BEGIN
  SET_FILE_POS(stream,5,inner)
  PAUSE
  RETURN 2
END status_cell
BEGIN
  statuses[1]=77
  OPEN FILE stream('UD','out')
  SET_FILE_POS(stream,target_pos(),statuses[status_cell()])
  BYTES_AHEAD(stream,remaining,s)
  accepted=(statuses[1]=77) AND (statuses[2]=0) AND (inner=0) AND (s=0) AND (remaining=4)
  WRITE stream('xy')
  SET_FILE_POS(stream,7,s)
  accepted=accepted AND (s=2) AND (GET_FILE_POS(stream)=4)
  SET_FILE_POS(stream,-1,s)
  accepted=accepted AND (s=0) AND (BYTES_LEFT(stream)=0)
  CLR_IO_STAT(stream)
  IF accepted AND (IO_STATUS(stream)=0) THEN
    CLOSE FILE stream
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'out':'ABCDEF'})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['context']['files']['out']['hex'],'414278794546')

    def test_file_availability_validates_output_overlap_after_selector_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  WRITE('waiting')
END MAIN
"""
        child="""PROGRAM CHILD
VAR stream:FILE cells:ARRAY[1] OF INTEGER
ROUTINE same_cell:INTEGER
BEGIN
  PAUSE
  RETURN 1
END same_cell
BEGIN
  cells[1]=77
  OPEN FILE stream('RO','out')
  BYTES_AHEAD(stream,cells[1],cells[same_cell()])
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'out':'ABC'})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'waiting')

        main=main.replace("WRITE('waiting')", "CONT_TASK('CHILD',s) WAIT FOR PAUSE PROGRAM[2]")
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'out':'ABC'})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('references must not overlap',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['CELLS'],[77])

    def test_file_attribute_change_can_pause_before_rejecting_an_open_handle(self):
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
VAR stream:FILE entered:INTEGER
ROUTINE ending:INTEGER
BEGIN
  PAUSE
  RETURN 124
END ending
BEGIN
  entered=0
  OPEN FILE stream('WO','out')
  SET_FILE_ATR(stream,ATR_EOL,ending())
  entered=1
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('attributes must be set before OPEN',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)

    def test_borrowed_file_plane_survives_pause_and_forwarding_into_a_pinned_module(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR bank:ARRAY[2,2,3] OF FILE selected,unused:INTEGER
ROUTINE relay(plane:ARRAY[*,*] OF FILE; amount:INTEGER) FROM LIB
ROUTINE choose_plane:INTEGER
BEGIN
  PAUSE
  RETURN selected
END choose_plane
ROUTINE next_amount:INTEGER
BEGIN
  selected=2
  PAUSE
  RETURN 17
END next_amount
BEGIN
  selected=1
  relay(bank[choose_plane()],next_amount())
  IF (NOT UNINIT(bank[1,2,3])) OR (NOT UNINIT(bank[2,2,3])) THEN
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIB
ROUTINE emit(stream:FILE; amount:INTEGER)
BEGIN
  IF UNINIT(stream) THEN
    OPEN FILE stream('WO','out')
    PAUSE
    IF NOT UNINIT(stream) THEN
      WRITE stream(amount)
      CLOSE FILE stream
    ENDIF
  ENDIF
END emit
ROUTINE write_row(row:ARRAY OF FILE; amount:INTEGER)
BEGIN
  IF ARRAY_LEN(row)=3 THEN
    emit(row[3],amount)
  ENDIF
END write_row
ROUTINE relay(plane:ARRAY[*,*] OF FILE; amount:INTEGER)
BEGIN
  IF (ARRAY_LEN(plane)=2) AND (ARRAY_LEN(plane,2)=3) THEN
    write_row(plane[2],amount)
  ENDIF
END relay
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['context']['files']['out']['hex'],'203137')
        bank=result['programs']['CHILD']['values']['BANK']
        self.assertEqual(bank[0][1][2]['file'],'out')
        self.assertIsNone(bank[1][1][2]['file'])
        self.assertFalse(bank[0][1][2]['open'])

    def test_whole_file_bank_retains_named_row_identity_through_forwarding(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_t=ARRAY[2] OF FILE bank_t=ARRAY[2] OF row_t
VAR streams:bank_t
ROUTINE work(row:row_t)
BEGIN
  OPEN FILE row[1]('WO','out')
  PAUSE
  WRITE row[1]('named row')
  CLOSE FILE row[1]
END work
ROUTINE forward(whole:bank_t)
BEGIN
  work(whole[2])
END forward
BEGIN
  forward(streams)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['context']['files']['out']['hex'],b'named row'.hex())
        streams=result['programs']['CHILD']['values']['STREAMS']
        self.assertIsNone(streams[0][0]['file'])
        self.assertEqual(streams[1][0]['file'],'out')

    def test_predefined_file_reference_keeps_its_alias_through_a_linked_function(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR length_now,unused:INTEGER
ROUTINE send(stream:FILE):INTEGER FROM LIB
BEGIN
  length_now=send(OUTPUT)
  IF UNINIT(OUTPUT) AND (length_now=3) THEN
    WRITE(length_now)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIB
ROUTINE emit(stream:FILE)
BEGIN
  WRITE stream(42)
END emit
ROUTINE send(stream:FILE):INTEGER
VAR pos:INTEGER
BEGIN
  emit(stream)
  PAUSE
  pos=GET_FILE_POS(stream)
  CLOSE FILE stream
  RETURN pos
END send
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)],files={},
                                   predefined_files={'OUTPUT':{'name':'out','mode':'WO'}})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertIn({'service':'predefined_files','address':'OUTPUT'},report['context_requirements'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['context']['files']['out']['hex'],'203432')
        self.assertEqual(result['text_output'],' 3')

    def test_borrowed_file_formal_checks_concrete_shape_after_later_operand_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  WRITE('waiting')
END MAIN
"""
        child="""PROGRAM CHILD
VAR streams:ARRAY[3] OF FILE entered:INTEGER
ROUTINE later:INTEGER
BEGIN
  PAUSE
  RETURN 17
END later
ROUTINE fixed(row:ARRAY[2] OF FILE; amount:INTEGER)
BEGIN
  entered=1
  OPEN FILE row[1]('WO','out')
  WRITE row[1](amount)
  CLOSE FILE row[1]
  PAUSE
END fixed
ROUTINE forward(generic:ARRAY OF FILE)
BEGIN
  fixed(generic,later())
END forward
BEGIN
  entered=0
  forward(streams)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused')
        self.assertEqual(result['text_output'],'waiting')

        main=main.replace("WRITE('waiting')", "CONT_TASK('CHILD',s) WAIT FOR PAUSE PROGRAM[2]")
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('Parameter binding type mismatch',result['error']['message'])
        self.assertEqual(result['programs']['CHILD']['values']['ENTERED'],0)
        self.assertEqual(result['context']['files'],{})

    def test_file_prefix_length_keeps_its_shape_across_a_pausing_axis(self):
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
VAR streams:ARRAY[2,3,4] OF FILE count_now,unused:INTEGER
ROUTINE pick_plane:INTEGER
BEGIN
  PAUSE
  RETURN 1
END pick_plane
ROUTINE pick_axis:INTEGER
BEGIN
  PAUSE
  RETURN 2
END pick_axis
BEGIN
  count_now=ARRAY_LEN(streams[pick_plane()],pick_axis())
  IF UNINIT(streams[1,1,1]) AND (count_now=4) THEN
    WRITE(count_now)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 4')
        self.assertNotIn('files',result['context'])

    def test_binary_file_read_retains_original_destination_through_format_pause(self):
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
VAR stream:FILE cells:ARRAY[2] OF INTEGER selected,last,unused:INTEGER
ROUTINE pick_cell:INTEGER
BEGIN
  PAUSE
  RETURN selected
END pick_cell
ROUTINE byte_width:INTEGER
BEGIN
  selected=2
  PAUSE
  RETURN 1
END byte_width
BEGIN
  selected=1
  cells[2]=77
  OPEN FILE stream('RB','in')
  READ stream(cells[pick_cell()]::byte_width(),last::2)
  IF (NOT UNINIT(cells[1])) AND (cells[2]=77) AND (GET_FILE_POS(stream)=3) THEN
    CLOSE FILE stream
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'in':{'hex':'070901'}})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation'])
        self.assertIn({'service':'files','address':'in'},report['context_requirements'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['CELLS'],[7,77])
        self.assertEqual(values['LAST'],265)
        self.assertEqual(result['context']['files'],{'in':{'hex':'070901'}})

    def test_default_text_file_read_captures_record_and_selects_saved_cursor(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
%CRTDEVICE
TYPE record_t=STRUCTURE amount:INTEGER tag:STRING[4] ENDSTRUCTURE
VAR row:record_t last,unused:INTEGER
ROUTINE field_width:INTEGER
BEGIN
  PAUSE
  RETURN 2
END field_width
BEGIN
  READ(row,CR,last::field_width())
  IF (NOT UNINIT(row.amount)) AND (NOT UNINIT(row.tag)) AND (GET_FILE_POS(INPUT)=8) THEN
    CLOSE FILE INPUT
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'in':'7 tag|42'},
                                   predefined_files={'INPUT':{'name':'in','mode':'RO','attributes':{'eol':124}}})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['ROW'],{'AMOUNT':7,'TAG':' tag'})
        self.assertEqual(values['LAST'],42)
        self.assertEqual(result['context']['files'],{'in':{'hex':b'7 tag|42'.hex()}})

    def test_short_binary_read_batch_does_not_publish_the_first_destination(self):
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
VAR stream:FILE first,last,entered:INTEGER
ROUTINE word_width:INTEGER
BEGIN
  PAUSE
  RETURN 2
END word_width
BEGIN
  entered=0
  first=77
  last=88
  OPEN FILE stream('RB','in')
  READ stream(first::1,last::word_width())
  entered=1
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'in':{'hex':'07'}})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('End of memory file',result['error']['message'])
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['FIRST'],values['LAST'],values['ENTERED']),(77,88,0))
        self.assertEqual(values['STREAM']['position'],0)

    def test_saved_file_value_does_not_prove_a_branch_after_read(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR stream:FILE value,chosen,other:INTEGER
BEGIN
  OPEN FILE stream('RB','in')
  READ stream(value::1)
  IF value=7 THEN
    WRITE(chosen)
  ELSE
    WRITE(other)
  ENDIF
  PAUSE
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],files={'in':{'hex':'07'}},replay=False)
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assert_inputs(report,[('variable','CHILD','CHOSEN','conditional'),
                                   ('variable','CHILD','OTHER','conditional')])

    def test_read_of_malformed_written_file_keeps_the_pause_unresolved(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR stream:FILE value,s,entered:INTEGER
BEGIN
  entered=0
  value=77
  OPEN FILE stream('RW','out')
  WRITE stream('bad')
  SET_FILE_POS(stream,0,s)
  READ stream(value)
  entered=1
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'out':'007'})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('invalid INTEGER',result['error']['message'])
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['VALUE'],values['ENTERED']),(77,0))
        self.assertEqual(result['context']['files'],{'out':{'hex':b'bad'.hex()}})

    def test_text_file_round_trip_keeps_written_value_across_pausing_formats(self):
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
VAR stream:FILE value,s,unused:INTEGER
ROUTINE field_width(width:INTEGER):INTEGER
BEGIN
  PAUSE
  RETURN width
END field_width
BEGIN
  SET_FILE_ATR(stream,ATR_EOL,124)
  OPEN FILE stream('RW','out')
  WRITE stream(17::field_width(2),CR)
  SET_FILE_POS(stream,0,s)
  READ stream(value::field_width(3),CR)
  IF (value=17) AND (s=0) AND (GET_FILE_POS(stream)=4) THEN
    CLOSE FILE stream
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation'])
        self.assertNotIn({'service':'files','address':'out'},report['context_requirements'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['programs']['CHILD']['values']['VALUE'],17)
        self.assertEqual(result['context']['files'],{'out':{'hex':b' 17|'.hex()}})

    def test_binary_file_round_trip_follows_truncate_reopen_and_append(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR original,appender:FILE first,last,s,unused:INTEGER
BEGIN
  SET_FILE_ATR(original,ATR_REVERSE)
  OPEN FILE original('WB','out')
  WRITE original(258::2)
  CLOSE FILE original
  SET_FILE_ATR(appender,ATR_REVERSE)
  OPEN FILE appender('APB','out')
  WRITE appender(-3::2)
  PAUSE
  SET_FILE_POS(appender,0,s)
  READ appender(first::2,last::2)
  IF (first=258) AND (last=-3) AND (BYTES_LEFT(appender)=0) THEN
    CLOSE FILE appender
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'out':'obsolete'})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertNotIn({'service':'files','address':'out'},report['context_requirements'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['FIRST'],values['LAST']),(258,-3))
        self.assertEqual(result['context']['files'],{'out':{'hex':'0102fffd'}})

    def test_partial_overwrite_preserves_saved_bytes_without_folding_the_value(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR stream:FILE value,s,chosen,other:INTEGER
BEGIN
  OPEN FILE stream('RW','out')
  WRITE stream('09')
  SET_FILE_POS(stream,0,s)
  READ stream(value::4)
  IF value=934 THEN
    WRITE(chosen)
  ELSE
    WRITE(other)
  ENDIF
  CLOSE FILE stream
  PAUSE
END CHILD
"""
        report,_=self.prepare([('MAIN',main),('CHILD',child)],files={'out':'1234'},replay=False)
        self.assert_inputs(report,[('variable','CHILD','CHOSEN','conditional'),
                                   ('variable','CHILD','OTHER','conditional')])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertIn({'service':'files','address':'out'},report['context_requirements'])

    def test_path_range_file_read_uses_live_bounds_then_keeps_captured_fields(self):
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
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     header_t=STRUCTURE total:INTEGER ENDSTRUCTURE
VAR routes:ARRAY[2] OF PATH NODEDATA=node_t PATHHEADER=header_t
    stream:FILE seed:node_t bank,tail,s,unused:INTEGER valid:BOOLEAN
ROUTINE first_bound:INTEGER
BEGIN
  bank=2
  APPEND_NODE(routes[1],seed,s)
  PAUSE
  RETURN 2
END first_bound
ROUTINE field_width:INTEGER
BEGIN
  DELETE_NODE(routes[1],2,s)
  PAUSE
  RETURN 3
END field_width
BEGIN
  bank=1
  routes[1].total=4
  routes[2].total=88
  seed.amount=7
  APPEND_NODE(routes[1],seed,s)
  OPEN FILE stream('RW','out')
  WRITE stream(' 19 17 14',CR,'23')
  SET_FILE_POS(stream,0,s)
  READ stream(routes[bank,first_bound()..0]::field_width(),CR,tail)
  valid=(routes[1,1].amount=17) AND (routes[1].total=14) AND (routes[2].total=88)
  IF valid AND (tail=23) AND (BYTES_LEFT(stream)=0) THEN
    CLOSE FILE stream
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation',
                                      'task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['ROUTES'],[
            {'data':{'TOTAL':14},'nodes':[{'AMOUNT':17}]},
            {'data':{'TOTAL':88},'nodes':[]},
        ])
        self.assertEqual(values['TAIL'],23)

    def test_path_bank_binary_file_read_keeps_selected_row_and_dynamic_header(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     header_t=STRUCTURE total:INTEGER ENDSTRUCTURE
VAR routes:ARRAY[2,2] OF PATH NODEDATA=node_t PATHHEADER=header_t
    stream:FILE s,which,unused:INTEGER valid:BOOLEAN
ROUTINE row_index:INTEGER
BEGIN
  PAUSE
  RETURN 2
END row_index
BEGIN
  which=0
  routes[1,1].total=99
  APPEND_NODE(routes[2,2],s)
  OPEN FILE stream('RWB','out')
  WRITE stream(11,12,13,14)
  SET_FILE_POS(stream,0,s)
  READ stream(routes[row_index()],routes[2,1,which])
  valid=(routes[1,1].total=99) AND (routes[2,1].total=14) AND (routes[2,2].total=12)
  IF valid AND (routes[2,2,1].amount=13) AND (GET_FILE_POS(stream)=16) THEN
    CLOSE FILE stream
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        second=result['programs']['CHILD']['values']['ROUTES'][1]
        self.assertEqual(second,[{'data':{'TOTAL':14},'nodes':[]},
                                 {'data':{'TOTAL':12},'nodes':[{'AMOUNT':13}]}])

    def test_incomplete_path_file_read_keeps_batch_unpublished(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     header_t=STRUCTURE total:INTEGER ENDSTRUCTURE
VAR route:PATH NODEDATA=node_t PATHHEADER=header_t
    stream:FILE seed:node_t s,entered:INTEGER
BEGIN
  entered=0
  route.total=4
  seed.amount=7
  APPEND_NODE(route,seed,s)
  OPEN FILE stream('RB','in')
  READ stream(route)
  entered=1
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'in':{'hex':'09000000'}})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('End of memory file',result['error']['message'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['ROUTE'],{'data':{'TOTAL':4},'nodes':[{'AMOUNT':7}]})
        self.assertEqual(values['ENTERED'],0)

    def test_default_file_read_initializes_whole_path_from_saved_text(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
%CRTDEVICE
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     header_t=STRUCTURE total:INTEGER ENDSTRUCTURE
VAR route:PATH NODEDATA=node_t PATHHEADER=header_t s,total,amount,unused:INTEGER
BEGIN
  APPEND_NODE(route,s)
  READ(route)
  PAUSE
  total=route.total
  amount=route[1].amount
  IF GET_FILE_POS(INPUT)=5 THEN
    CLOSE FILE INPUT
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'in':'17 29'},
                                   predefined_files={'INPUT':{'name':'in','mode':'RO'}})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertIn({'service':'files','address':'in'},report['context_requirements'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['ROUTE'],{'data':{'TOTAL':17},'nodes':[{'AMOUNT':29}]})
        self.assertEqual((values['TOTAL'],values['AMOUNT']),(17,29))

    def test_output_keeps_cursor_facts_when_the_modified_image_is_large(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR stream:FILE unused:INTEGER
BEGIN
  OPEN FILE stream('UD','out')
  WRITE stream('B')
  IF (GET_FILE_POS(stream)=1) AND (BYTES_LEFT(stream)=65536) THEN
    CLOSE FILE stream
    PAUSE
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'out':'A'*65537})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertEqual(result['status'],'paused',result['error'])
        self.assertEqual(result['context']['files']['out']['hex'],(b'B'+b'A'*65536).hex())

    def test_queue_file_read_keeps_ids_and_allows_rebinding_after_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR q:QUEUE_TYPE original,rebound:ARRAY[3] OF INTEGER
    stream:FILE first,last,entry,item,tail,next_id,s,unused:INTEGER valid:BOOLEAN
ROUTINE field_width:INTEGER
BEGIN
  PAUSE
  RETURN 3
END field_width
BEGIN
  INIT_QUEUE(q)
  APPEND_QUEUE(7,q,original,first,s)
  APPEND_QUEUE(9,q,original,last,s)
  OPEN FILE stream('RW','out')
  WRITE stream(' 42 43',CR,'99')
  SET_FILE_POS(stream,0,s)
  READ stream(q::field_width(),CR,tail)
  GET_QUEUE(q,rebound,item,entry,s)
  valid=(item=42) AND (entry=first) AND (tail=99) AND (s=0)
  APPEND_QUEUE(51,q,rebound,next_id,s)
  IF valid AND (next_id=last+1) AND (original[2]=9) AND (rebound[1]=43) AND (BYTES_LEFT(stream)=0) THEN
    CLOSE FILE stream
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['ITEM'],values['ENTRY'],values['TAIL']),(42,1,99))
        self.assertEqual((values['ORIGINAL'],values['REBOUND']),([7,9,0],[43,51,0]))
        self.assertEqual(values['Q'],{'initialized':True,'entries':[[2,43],[3,51]]})

    def test_queue_bank_binary_read_keeps_order_and_explicit_backing_write(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR bank:ARRAY[2,3] OF QUEUE_TYPE left_buf,right_buf:ARRAY[2] OF INTEGER
    stream:FILE entry,s,unused:INTEGER
ROUTINE pick_row:INTEGER
BEGIN
  PAUSE
  RETURN 2
END pick_row
BEGIN
  INIT_QUEUE(bank[2,1])
  INIT_QUEUE(bank[2,2])
  INIT_QUEUE(bank[2,3])
  APPEND_QUEUE(7,bank[2,1],left_buf,entry,s)
  APPEND_QUEUE(8,bank[2,3],right_buf,entry,s)
  OPEN FILE stream('RWB','out')
  WRITE stream(17,19,23)
  SET_FILE_POS(stream,0,s)
  READ stream(bank[pick_row()],left_buf[1])
  IF (left_buf[1]=23) AND (right_buf[1]=8) AND (GET_FILE_POS(stream)=12) THEN
    CLOSE FILE stream
    WRITE(bank[2])
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual([queue['entries'] for queue in values['BANK'][1]],[[[1,17]],[],[[1,19]]])
        self.assertEqual((values['LEFT_BUF'],values['RIGHT_BUF']),([23,0],[8,0]))
        self.assertEqual(result['text_output'],' 17 19')

    def test_queue_format_reinitialization_invalidates_batch_even_with_equal_entries(self):
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
VAR q:QUEUE_TYPE backing:ARRAY[2] OF INTEGER stream:FILE entry,s,value,entered:INTEGER
ROUTINE changing_width:INTEGER
BEGIN
  PAUSE
  INIT_QUEUE(q)
  APPEND_QUEUE(7,q,backing,entry,s)
  RETURN 4
END changing_width
BEGIN
  entered=0
  value=77
  INIT_QUEUE(q)
  APPEND_QUEUE(7,q,backing,entry,s)
  OPEN FILE stream('RB','in')
  READ stream(value,q::changing_width())
  entered=1
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'in':{'hex':'090000002a000000'}})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('Queue READ capture changed',result['error']['message'])
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['VALUE'],values['ENTERED'],values['STREAM']['position']),(77,0,0))
        self.assertEqual(values['Q']['entries'],[[1,7]])

    def test_saved_file_queue_values_stay_editable_through_copy_and_get(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR q:QUEUE_TYPE original,rebound,copy_buf:ARRAY[2] OF INTEGER
    stream:FILE first,last,entry,item,copied,count,s,unused:INTEGER valid:BOOLEAN
BEGIN
  INIT_QUEUE(q)
  APPEND_QUEUE(7,q,original,first,s)
  APPEND_QUEUE(9,q,original,last,s)
  OPEN FILE stream('RO','in')
  READ stream(q)
  CLOSE FILE stream
  PAUSE
  COPY_QUEUE(q,rebound,first,1,copy_buf,count,s)
  copied=copy_buf[1]
  GET_QUEUE(q,rebound,item,entry,s)
  valid=(entry=first) AND (count=1) AND (s=0)
  IF NOT valid THEN
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'in':'42 43'})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertIn({'service':'files','address':'in'},report['context_requirements'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['ITEM'],values['COPIED'],values['ENTRY']),(42,43,1))
        self.assertEqual((values['ORIGINAL'],values['REBOUND']),([7,9],[43,0]))

        child=child.replace('s,unused:INTEGER','s,unused,other:INTEGER').replace(
            'IF NOT valid THEN\n    WRITE(unused)\n  ENDIF',
            'IF item=42 THEN\n    WRITE(unused)\n  ELSE\n    WRITE(other)\n  ENDIF')
        report,_=self.prepare([('MAIN',main),('CHILD',child)],files={'in':'42 43'},replay=False)
        self.assert_inputs(report,[('variable','CHILD','UNUSED','conditional'),
                                   ('variable','CHILD','OTHER','conditional')])

    def test_queue_read_rejects_duplicate_and_truncated_destinations_atomically(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        for operands, message in (('value,q,q','must be disjoint'),('value,q','End of memory file')):
            with self.subTest(operands=operands):
                child=f"""PROGRAM CHILD
VAR q:QUEUE_TYPE backing:ARRAY[2] OF INTEGER stream:FILE entry,s,value:INTEGER
BEGIN
  value=77
  INIT_QUEUE(q)
  APPEND_QUEUE(7,q,backing,entry,s)
  OPEN FILE stream('RB','in')
  READ stream({operands})
  PAUSE
END CHILD
"""
                report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'in':{'hex':'09000000'}})
                self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
                self.assertEqual(result['status'],'failed')
                self.assertIn(message,result['error']['message'])
                values=result['programs']['CHILD']['values']
                self.assertEqual((values['VALUE'],values['STREAM']['position']),(77,0))
                self.assertEqual((values['Q']['entries'],values['BACKING']),([[1,7]],[7,0]))

    def test_restored_queue_keeps_entry_order_and_sequence_through_linked_edits(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR q:QUEUE_TYPE backing,output_values:ARRAY[3] OF INTEGER
    item,entry,next_id,count,copied,s,unused:INTEGER
BEGIN
  output_values[2]=55
  COPY_QUEUE(q,backing,7,1,output_values,count,s)
  PAUSE
  copied=output_values[1]
  GET_QUEUE(q,backing,item,entry,s)
  APPEND_QUEUE(88,q,backing,next_id,s)
  IF (entry=7) AND (next_id=10) AND (count=1) AND (s=0) AND (output_values[2]=55) THEN
    WRITE(next_id)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        queue=dict(initialized=True,sequence=9,entries=[[7,41],[2,53]])
        seed=dict(program='CHILD',path='Q',type=['QUEUE_TYPE'],value=queue)
        report,result=self.prepare([('MAIN',main),('CHILD',child)],variables=[seed])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(report['binding_storage'],[dict(program='CHILD',path='Q',type=['QUEUE_TYPE'])])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['ITEM'],values['COPIED'],values['ENTRY'],values['NEXT_ID']),(41,53,7,10))
        self.assertEqual(values['Q']['entries'],[[2,53],[10,88]])
        self.assertEqual(values['BACKING'],[53,88,0])

        child=child.replace('s,unused:INTEGER','s,unused,other:INTEGER').replace(
            "IF (entry=7) AND (next_id=10) AND (count=1) AND (s=0) AND (output_values[2]=55) THEN\n    WRITE(next_id)",
            'IF item=41 THEN\n    WRITE(other)')
        report,_=self.prepare([('MAIN',main),('CHILD',child)],variables=[seed],replay=False)
        self.assert_inputs(report,[('variable','CHILD','OTHER','conditional'),
                                   ('variable','CHILD','UNUSED','conditional')])

    def test_restored_queue_bank_file_read_tracks_selected_row_only(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR bank:ARRAY[2,2] OF QUEUE_TYPE backing:ARRAY[2] OF INTEGER
    stream:FILE entry,item,s,unused:INTEGER
ROUTINE pick_row:INTEGER
BEGIN
  PAUSE
  RETURN 2
END pick_row
BEGIN
  OPEN FILE stream('RWB','out')
  WRITE stream(23,29)
  SET_FILE_POS(stream,0,s)
  READ stream(bank[pick_row()])
  GET_QUEUE(bank[2,1],backing,item,entry,s)
  IF (entry=2) AND (item=23) AND (backing[1]=29) AND (BYTES_LEFT(stream)=0) THEN
    CLOSE FILE stream
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        uninitialized=dict(initialized=False,sequence=0,entries=[])
        occupied=dict(initialized=True,sequence=4,entries=[[2,9],[4,8]])
        empty=dict(initialized=True,sequence=3,entries=[])
        schema=['ARRAY',[2,2],['QUEUE_TYPE']]
        seed=dict(program='CHILD',path='BANK',type=schema,value=[[uninitialized,uninitialized],[occupied,empty]])
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={},variables=[seed])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(report['binding_storage'],[dict(program='CHILD',path='BANK',type=schema)])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['ITEM'],values['ENTRY'],values['BACKING']),(23,2,[29,0]))
        self.assertEqual([queue['entries'] for queue in values['BANK'][1]],[[[4,29]],[]])
        self.assertEqual(result['context']['files'],{'out':{'hex':'170000001d000000'}})

        uninitialized_row=dict(seed,value=[[uninitialized,uninitialized],[occupied,uninitialized]])
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={},variables=[uninitialized_row])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('INIT_QUEUE',result['error']['message'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['BANK'][1][0]['entries'],[[2,9],[4,8]])
        self.assertEqual(values['STREAM']['position'],0)

    def test_init_queue_replaces_saved_topology_before_first_use(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
END MAIN
"""
        child="""PROGRAM CHILD
VAR q:QUEUE_TYPE backing:ARRAY[2] OF INTEGER entry,s,unused:INTEGER
BEGIN
  INIT_QUEUE(q)
  APPEND_QUEUE(3,q,backing,entry,s)
  IF (entry=1) AND (s=0) THEN
    PAUSE
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        queue=dict(initialized=True,sequence=9,entries=[[7,41]])
        seed=dict(program='CHILD',path='Q',type=['QUEUE_TYPE'],value=queue)
        report,result=self.prepare([('MAIN',main),('CHILD',child)],variables=[seed])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait'])
        self.assertNotIn('binding_storage',report)
        self.assertEqual(result['status'],'paused',result['error'])
        self.assertEqual(result['programs']['CHILD']['values']['Q']['entries'],[[1,3]])

    def test_named_queue_components_keep_original_cells_through_pinned_forwarding(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE row_t=ARRAY[2] OF QUEUE_TYPE
     plane_t=ARRAY[2] OF row_t
VAR bank:ARRAY[2] OF plane_t backing:ARRAY[3] OF INTEGER
    selected,entry,item,s,unused:INTEGER
ROUTINE relay(plane:plane_t; backing:ARRAY[3] OF INTEGER; amount,entry:INTEGER) FROM LIB
ROUTINE pick_plane:INTEGER
BEGIN
  PAUSE
  RETURN selected
END pick_plane
ROUTINE next_amount:INTEGER
BEGIN
  selected=2
  PAUSE
  RETURN 23
END next_amount
BEGIN
  selected=1
  relay(bank[pick_plane()],backing,next_amount(),entry)
  GET_QUEUE(bank[1,2,1],backing,item,entry,s)
  IF (item=23) AND (entry=1) AND (backing[1]=19) AND UNINIT(bank[2,2,1]) THEN
    WRITE(item)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIB
TYPE row_t=ARRAY[2] OF QUEUE_TYPE
     plane_t=ARRAY[2] OF row_t
ROUTINE fill(q:QUEUE_TYPE; backing:ARRAY[3] OF INTEGER; amount,entry:INTEGER)
VAR stream:FILE s:INTEGER
BEGIN
  IF UNINIT(q) THEN
    INIT_QUEUE(q)
  ENDIF
  APPEND_QUEUE(0,q,backing,entry,s)
  OPEN FILE stream('RWB','out')
  WRITE stream(amount)
  SET_FILE_POS(stream,0,s)
  PAUSE
  IF NOT UNINIT(q) THEN
    READ stream(q)
    APPEND_QUEUE(19,q,backing,entry,s)
    CLOSE FILE stream
  ENDIF
END fill
ROUTINE forward(row:ARRAY OF QUEUE_TYPE; backing:ARRAY[3] OF INTEGER; amount,entry:INTEGER)
BEGIN
  IF ARRAY_LEN(row)=2 THEN
    fill(row[1],backing,amount,entry)
  ENDIF
END forward
ROUTINE relay(plane:plane_t; backing:ARRAY[3] OF INTEGER; amount,entry:INTEGER)
BEGIN
  IF (ARRAY_LEN(plane)=2) AND (ARRAY_LEN(plane,2)=2) THEN
    forward(plane[2],backing,amount,entry)
  ENDIF
END relay
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*3)
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['BANK'][0][1][0]['entries'],[[2,19]])
        self.assertFalse(values['BANK'][1][1][0]['initialized'])
        self.assertEqual(values['BACKING'],[19,0,0])
        self.assertEqual(result['text_output'],' 23')
        self.assertEqual(result['context']['files'],{'out':{'hex':'17000000'}})

    def test_queue_prefix_and_grouped_scalar_snapshot_before_later_arguments(self):
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
VAR bank:ARRAY[2,2] OF QUEUE_TYPE backing:ARRAY[2] OF INTEGER
    first,s,found,unused:INTEGER
ROUTINE change_original:INTEGER
BEGIN
  MODIFY_QUEUE(41,first,bank[1,1],backing,s)
  PAUSE
  RETURN 1
END change_original
ROUTINE take_private(q:QUEUE_TYPE; found:INTEGER)
VAR other:ARRAY[2] OF INTEGER entry,status:INTEGER
BEGIN
  PAUSE
  GET_QUEUE(q,other,found,entry,status)
END take_private
ROUTINE inspect(row:ARRAY OF QUEUE_TYPE; changed,found:INTEGER)
BEGIN
  IF UNINIT(row[2]) AND (ARRAY_LEN(row)=2) AND (changed=1) THEN
    INIT_QUEUE(row[2])
    take_private((row[1]),found)
  ENDIF
END inspect
BEGIN
  INIT_QUEUE(bank[1,1])
  APPEND_QUEUE(7,bank[1,1],backing,first,s)
  inspect(bank[1],change_original(),found)
  IF (found=7) AND (backing[1]=41) AND UNINIT(bank[1,2]) THEN
    WRITE(found)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*2)
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['BANK'][0][0]['entries'],[[1,41]])
        self.assertFalse(values['BANK'][0][1]['initialized'])
        self.assertEqual(values['FOUND'],7)
        self.assertEqual(result['text_output'],' 7')

    def test_borrowed_queue_shape_is_checked_after_pausing_later_argument(self):
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
VAR bank:ARRAY[2] OF QUEUE_TYPE entered:INTEGER
ROUTINE later_argument:INTEGER
BEGIN
  PAUSE
  RETURN 1
END later_argument
ROUTINE fixed(q:ARRAY[3] OF QUEUE_TYPE; flag:INTEGER)
BEGIN
  entered=flag
  INIT_QUEUE(q[1])
  PAUSE
END fixed
ROUTINE relay(q:ARRAY OF QUEUE_TYPE)
BEGIN
  fixed(q,later_argument())
END relay
BEGIN
  entered=0
  relay(bank)
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('parameter binding type mismatch',result['error']['message'].lower())
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['ENTERED'],0)
        self.assertFalse(values['BANK'][0]['initialized'])

    def test_borrowed_path_bank_component_survives_pinned_forwarding_and_file_read(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
     row_t=ARRAY[2] OF route_t
VAR bank:ARRAY[2] OF row_t selected,unused:INTEGER valid:BOOLEAN
ROUTINE relay(row:row_t; amount:INTEGER) FROM LIB
ROUTINE pick_row:INTEGER
BEGIN
  PAUSE
  RETURN selected
END pick_row
ROUTINE next_amount:INTEGER
BEGIN
  selected=2
  PAUSE
  RETURN 23
END next_amount
BEGIN
  selected=1
  relay(bank[pick_row()],next_amount())
  valid=(PATH_LEN(bank[1,2])=1) AND (PATH_LEN(bank[2,2])=0) AND (bank[1,2].total=9)
  IF valid AND (bank[1,2,1].amount=23) THEN
    WRITE(bank[1,2,1].amount)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIB
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
     row_t=ARRAY[2] OF route_t
ROUTINE fill(route:route_t; amount:INTEGER)
VAR stream:FILE s:INTEGER
BEGIN
  IF PATH_LEN(route)=0 THEN
    route.total=9
    APPEND_NODE(route,s)
  ENDIF
  OPEN FILE stream('RWB','out')
  WRITE stream(amount)
  SET_FILE_POS(stream,0,s)
  PAUSE
  READ stream(route[1])
  CLOSE FILE stream
END fill
ROUTINE relay(row:row_t; amount:INTEGER)
BEGIN
  IF ARRAY_LEN(row)=2 THEN
    fill(row[2],amount)
  ENDIF
END relay
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*3)
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['BANK'][0][1],{'data':{'TOTAL':9},'nodes':[{'AMOUNT':23}]})
        self.assertEqual(values['BANK'][1][1]['nodes'],[])
        self.assertEqual(result['context']['files'],{'out':{'hex':'17000000'}})

    def test_path_prefix_and_grouped_scalar_keep_private_partial_records(self):
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
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR bank:ARRAY[2,2] OF route_t s,found,unused:INTEGER valid:BOOLEAN
ROUTINE change_original:INTEGER
BEGIN
  bank[1,1].total=41
  bank[1,1,1].amount=42
  PAUSE
  RETURN 1
END change_original
ROUTINE fill_private(route:route_t; found:INTEGER)
VAR stream:FILE s:INTEGER
BEGIN
  OPEN FILE stream('RWB','out')
  WRITE stream(23)
  SET_FILE_POS(stream,0,s)
  PAUSE
  READ stream(route[1])
  found=route[1].amount+route.total
  route.total=99
  CLOSE FILE stream
END fill_private
ROUTINE inspect(row:ARRAY OF route_t; changed,found:INTEGER)
BEGIN
  IF (PATH_LEN(row[1])=1) AND (ARRAY_LEN(row)=2) AND (changed=1) THEN
    fill_private((row[1]),found)
    IF row[1].total<>7 THEN
      found=0
    ENDIF
  ENDIF
END inspect
BEGIN
  bank[1,1].total=7
  bank[1,2].total=0
  APPEND_NODE(bank[1,1],s)
  inspect(bank[1],change_original(),found)
  valid=(found=30) AND (bank[1,1].total=41) AND (bank[1,1,1].amount=42)
  IF valid THEN
    WRITE(found)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*2)
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['BANK'][0][0],{'data':{'TOTAL':41},'nodes':[{'AMOUNT':42}]})
        self.assertEqual(values['FOUND'],30)
        self.assertEqual(result['text_output'],' 30')

    def test_path_len_retains_pausing_selector_and_checks_current_count(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t
VAR bank:ARRAY[2] OF route_t count,s,unused:INTEGER
ROUTINE pick:INTEGER
BEGIN
  APPEND_NODE(bank[2],s)
  PAUSE
  RETURN 2
END pick
BEGIN
  APPEND_NODE(bank[2],s)
  count=PATH_LEN(bank[pick()])
  IF count=2 THEN
    WRITE(count)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['COUNT'],2)
        self.assertEqual(result['text_output'],' 2')

    def test_path_assignment_snapshots_source_before_pausing_destination_selector(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR source:route_t dest:ARRAY[2] OF route_t seed:node_t s,unused:INTEGER valid:BOOLEAN
ROUTINE choose_dest:INTEGER
BEGIN
  source.total=77
  source[1].amount=88
  PAUSE
  RETURN 2
END choose_dest
BEGIN
  source.total=3
  seed.amount=17
  APPEND_NODE(source,seed,s)
  dest[choose_dest()]=source
  valid=(PATH_LEN(dest[1])=0) AND (PATH_LEN(dest[2])=1) AND (dest[2].total=3)
  IF valid AND (dest[2,1].amount=17) AND (source[1].amount=88) THEN
    WRITE(dest[2,1].amount)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['DEST'][1],{'data':{'TOTAL':3},'nodes':[{'AMOUNT':17}]})
        self.assertEqual(values['SOURCE'],{'data':{'TOTAL':77},'nodes':[{'AMOUNT':88}]})

    def test_path_array_assignment_keeps_private_row_across_pause(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t
VAR bank:ARRAY[2,2] OF route_t seed:node_t s,unused:INTEGER
ROUTINE choose_row:INTEGER
BEGIN
  seed.amount=94
  APPEND_NODE(bank[2,1],seed,s)
  PAUSE
  RETURN 1
END choose_row
BEGIN
  seed.amount=43
  APPEND_NODE(bank[2,1],seed,s)
  bank[choose_row()]=bank[2]
  IF (PATH_LEN(bank[1,1])=1) AND (PATH_LEN(bank[2,1])=2) AND (bank[1,1,1].amount=43) THEN
    WRITE(bank[1,1,1].amount)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['BANK'][0][0]['nodes'],[{'AMOUNT':43}])
        self.assertEqual(values['BANK'][1][0]['nodes'],[{'AMOUNT':43},{'AMOUNT':94}])

    def test_copy_path_keeps_replaced_descriptor_and_reverse_bounds_across_pauses(self):
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
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR source,replacement,dest:route_t seed:node_t
    codes:ARRAY[2] OF INTEGER s,unused:INTEGER valid:BOOLEAN
ROUTINE first_bound:INTEGER
BEGIN
  COPY_PATH(replacement,0,0,source,s)
  PAUSE
  RETURN 2
END first_bound
ROUTINE pick_status:INTEGER
BEGIN
  PAUSE
  RETURN 2
END pick_status
BEGIN
  source.total=3
  replacement.total=9
  seed.amount=17
  APPEND_NODE(source,seed,s)
  seed.amount=19
  APPEND_NODE(source,seed,s)
  seed.amount=88
  APPEND_NODE(replacement,seed,s)
  COPY_PATH(source,first_bound(),1,dest,codes[pick_status()],FALSE)
  COPY_PATH(source,99,1,dest,codes[1])
  valid=(codes[1]=2) AND (codes[2]=0) AND (PATH_LEN(source)=1) AND (PATH_LEN(dest)=2)
  IF valid AND (dest.total=3) AND (dest[1].amount=19) AND (dest[2].amount=17) THEN
    WRITE(dest[1].amount)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*2)
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['DEST'],{'data':{'TOTAL':3},'nodes':[{'AMOUNT':19},{'AMOUNT':17}]})
        self.assertEqual(values['SOURCE'],{'data':{'TOTAL':9},'nodes':[{'AMOUNT':88}]})
        self.assertEqual(values['CODES'],[2,0])

    def test_path_range_write_keeps_descriptor_replaced_by_pausing_bound(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR source,replacement:route_t seed:node_t s,unused:INTEGER
ROUTINE first_bound:INTEGER
BEGIN
  COPY_PATH(replacement,0,0,source,s)
  PAUSE
  RETURN 2
END first_bound
BEGIN
  source.total=3
  replacement.total=9
  seed.amount=17
  APPEND_NODE(source,seed,s)
  seed.amount=19
  APPEND_NODE(source,seed,s)
  seed.amount=88
  APPEND_NODE(replacement,seed,s)
  WRITE(source[first_bound()..0])
  IF (source.total<>9) OR (PATH_LEN(source)<>1) THEN
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 19 17 3')
        self.assertEqual(result['programs']['CHILD']['values']['SOURCE'],
                         {'data':{'TOTAL':9},'nodes':[{'AMOUNT':88}]})

    def test_scalar_path_selector_stays_conservative_when_descriptor_is_replaced(self):
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
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t
VAR source,replacement:route_t seed:node_t s:INTEGER
ROUTINE replace_source:INTEGER
BEGIN
  COPY_PATH(replacement,0,0,source,s)
  PAUSE
  RETURN 1
END replace_source
BEGIN
  seed.amount=17
  APPEND_NODE(source,seed,s)
  seed.amount=88
  APPEND_NODE(replacement,seed,s)
  WRITE(source[replace_source()].amount)
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'paused',result['error'])
        self.assertEqual(result['text_output'],' 17')
        self.assertEqual(result['programs']['CHILD']['values']['SOURCE']['nodes'],[{'AMOUNT':88}])

    def test_copy_path_accepts_pausing_pinned_path_result(self):
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
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR target:route_t s,unused:INTEGER
ROUTINE make_route:route_t FROM LIB
ROUTINE first_bound:INTEGER
BEGIN
  PAUSE
  RETURN 2
END first_bound
BEGIN
  COPY_PATH(make_route(),first_bound(),1,target,s)
  IF (s=0) AND (PATH_LEN(target)=2) AND (target.total=7) AND (target[1].amount=19) THEN
    WRITE(target[2].amount)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIB
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
ROUTINE make_route:route_t
VAR route:route_t seed:node_t s:INTEGER
BEGIN
  route.total=7
  seed.amount=17
  APPEND_NODE(route,seed,s)
  PAUSE
  seed.amount=19
  APPEND_NODE(route,seed,s)
  RETURN route
END make_route
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*2)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 17')
        self.assertEqual(result['programs']['CHILD']['values']['TARGET'],
                         {'data':{'TOTAL':7},'nodes':[{'AMOUNT':19},{'AMOUNT':17}]})

    def test_returned_path_bank_flows_through_call_assignment_and_pausing_selection(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR target:ARRAY[2] OF route_t picked,unused:INTEGER valid:BOOLEAN
ROUTINE make_bank:ARRAY OF route_t
VAR local_bank:ARRAY[2] OF route_t seed:node_t s:INTEGER
BEGIN
  seed.amount=23
  local_bank[1].total=7
  local_bank[2].total=9
  APPEND_NODE(local_bank[2],seed,s)
  PAUSE
  RETURN local_bank
END make_bank
ROUTINE forward(bank:ARRAY OF route_t):ARRAY OF route_t
BEGIN
  RETURN bank
END forward
ROUTINE choose_cell:INTEGER
BEGIN
  PAUSE
  RETURN 2
END choose_cell
BEGIN
  target=forward(make_bank())
  picked=make_bank()[choose_cell(),1].amount
  valid=(ARRAY_LEN(forward(target))=2) AND (PATH_LEN(forward(target)[2])=1)
  IF valid AND (target[2].total=9) AND (picked=23) THEN
    WRITE(picked)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*3)
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['TARGET'],[{'data':{'TOTAL':7},'nodes':[]},
                                          {'data':{'TOTAL':9},'nodes':[{'AMOUNT':23}]}])
        self.assertEqual(values['PICKED'],23)

    def test_path_return_assignment_preserves_partial_record_for_binary_read(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR target:route_t stream:FILE s,unused:INTEGER
ROUTINE make_route:route_t
VAR route:route_t status:INTEGER
BEGIN
  route.total=7
  APPEND_NODE(route,status)
  PAUSE
  RETURN route
END make_route
BEGIN
  target=make_route()
  OPEN FILE stream('RWB','out')
  WRITE stream(31)
  SET_FILE_POS(stream,0,s)
  READ stream(target[1])
  CLOSE FILE stream
  IF (PATH_LEN(target)=1) AND (target.total=7) AND (target[1].amount=31) THEN
    WRITE(target[1].amount)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['programs']['CHILD']['values']['TARGET'],
                         {'data':{'TOTAL':7},'nodes':[{'AMOUNT':31}]})
        self.assertEqual(result['context']['files'],{'out':{'hex':'1f000000'}})

    def test_write_path_result_range_and_bank_keep_detached_values_across_pauses(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
TYPE node_t=STRUCTURE amount:INTEGER ENDSTRUCTURE
     head_t=STRUCTURE total:INTEGER ENDSTRUCTURE
     route_t=PATH NODEDATA=node_t PATHHEADER=head_t
VAR visits,unused:INTEGER
ROUTINE make_route:route_t
VAR route:route_t seed:node_t s:INTEGER
BEGIN
  route.total=3
  seed.amount=17
  APPEND_NODE(route,seed,s)
  seed.amount=19
  APPEND_NODE(route,seed,s)
  PAUSE
  RETURN route
END make_route
ROUTINE first_bound:INTEGER
BEGIN
  visits=visits+1
  PAUSE
  RETURN 2
END first_bound
ROUTINE make_bank:ARRAY OF route_t
VAR bank:ARRAY[2] OF route_t s:INTEGER
BEGIN
  bank[1].total=8
  bank[2].total=9
  APPEND_NODE(bank[2],s)
  bank[2,1].amount=42
  PAUSE
  RETURN bank
END make_bank
BEGIN
  visits=0
  WRITE(make_route()[first_bound()..0],'|',make_bank())
  IF visits<>1 THEN
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*3)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['text_output'],' 19 17 3| 8 9 42')
        self.assertEqual(result['programs']['CHILD']['values']['VISITS'],1)

    def test_pinned_queue_result_releases_buffer_and_keeps_entry_sequence(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR target:QUEUE_TYPE old_buf,new_buf:ARRAY[3] OF INTEGER
    entry,copied,next_id,s,unused:INTEGER valid:BOOLEAN
ROUTINE make_queue:QUEUE_TYPE FROM LIB
BEGIN
  INIT_QUEUE(target)
  APPEND_QUEUE(7,target,old_buf,entry,s)
  target=make_queue()
  GET_QUEUE(target,new_buf,copied,entry,s)
  valid=(copied=17) AND (entry=1) AND (s=0)
  APPEND_QUEUE(29,target,new_buf,next_id,s)
  IF valid AND (next_id=3) AND (old_buf[1]=7) AND (new_buf[1]=19) THEN
    WRITE(copied)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        library="""PROGRAM LIB
ROUTINE make_queue:QUEUE_TYPE
VAR local_queue:QUEUE_TYPE backing:ARRAY[2] OF INTEGER entry,s:INTEGER
BEGIN
  INIT_QUEUE(local_queue)
  APPEND_QUEUE(17,local_queue,backing,entry,s)
  PAUSE
  APPEND_QUEUE(19,local_queue,backing,entry,s)
  RETURN local_queue
END make_queue
BEGIN
END LIB
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child),('LIB',library)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertEqual(values['TARGET']['entries'],[[2,19],[3,29]])
        self.assertEqual((values['OLD_BUF'],values['NEW_BUF']),([7,0,0],[19,29,0]))
        self.assertEqual(result['text_output'],' 17')

    def test_returned_queue_bank_flows_through_value_call_row_assignment_and_query(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR target:ARRAY[2,2] OF QUEUE_TYPE backing:ARRAY[3] OF INTEGER
    entry,item,s,unused:INTEGER valid:BOOLEAN
ROUTINE make_bank:ARRAY OF QUEUE_TYPE
VAR bank:ARRAY[2] OF QUEUE_TYPE scratch:ARRAY[2] OF INTEGER entry,s:INTEGER
BEGIN
  INIT_QUEUE(bank[1])
  APPEND_QUEUE(23,bank[1],scratch,entry,s)
  PAUSE
  RETURN bank
END make_bank
ROUTINE forward(bank:ARRAY OF QUEUE_TYPE):ARRAY OF QUEUE_TYPE
BEGIN
  RETURN bank
END forward
ROUTINE pick:INTEGER
BEGIN
  PAUSE
  RETURN 2
END pick
BEGIN
  target[pick()]=forward(make_bank())
  valid=UNINIT(make_bank()[pick()])
  valid=valid AND (ARRAY_LEN(forward(target[2]))=2) AND UNINIT(target[2,2])
  GET_QUEUE(target[2,1],backing,item,entry,s)
  IF valid AND (item=23) AND (entry=1) AND (s=0) THEN
    WRITE(item)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*4)
        self.assertEqual(result['status'],'completed',result['error'])
        values=result['programs']['CHILD']['values']
        self.assertTrue(values['VALID'])
        self.assertEqual(values['TARGET'][1][0],{'initialized':True,'entries':[]})
        self.assertFalse(values['TARGET'][1][1]['initialized'])
        self.assertEqual(result['text_output'],' 23')

    def test_returned_queue_and_bank_write_binary_after_pausing_format(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR stream:FILE unused:INTEGER
ROUTINE make_queue:QUEUE_TYPE
VAR q:QUEUE_TYPE backing:ARRAY[2] OF INTEGER entry,s:INTEGER
BEGIN
  INIT_QUEUE(q)
  APPEND_QUEUE(23,q,backing,entry,s)
  PAUSE
  RETURN q
END make_queue
ROUTINE make_bank:ARRAY OF QUEUE_TYPE
VAR bank:ARRAY[2] OF QUEUE_TYPE backing:ARRAY[2] OF INTEGER entry,s:INTEGER
BEGIN
  INIT_QUEUE(bank[1])
  INIT_QUEUE(bank[2])
  APPEND_QUEUE(42,bank[2],backing,entry,s)
  PAUSE
  RETURN bank
END make_bank
ROUTINE byte_width:INTEGER
BEGIN
  PAUSE
  RETURN 2
END byte_width
BEGIN
  OPEN FILE stream('WB','out')
  WRITE stream(make_queue()::byte_width(),make_bank())
  IF GET_FILE_POS(stream)=6 THEN
    CLOSE FILE stream
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={})
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling']+['task-wait','task-continuation']*3)
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['context']['files'],{'out':{'hex':'17002a000000'}})

    def test_uninitialized_queue_result_overrides_saved_entries(self):
        main="""PROGRAM MAIN
VAR s:INTEGER
BEGIN
  RUN_TASK('CHILD',0,FALSE,FALSE,0,s)
  WAIT FOR PAUSE PROGRAM[2]
  CONT_TASK('CHILD',s)
END MAIN
"""
        child="""PROGRAM CHILD
VAR target:QUEUE_TYPE backing:ARRAY[2] OF INTEGER entry,s,unused:INTEGER
ROUTINE empty_queue:QUEUE_TYPE
VAR local_queue:QUEUE_TYPE
BEGIN
  PAUSE
  RETURN local_queue
END empty_queue
BEGIN
  target=empty_queue()
  IF UNINIT(target) THEN
    INIT_QUEUE(target)
    APPEND_QUEUE(31,target,backing,entry,s)
    WRITE(entry)
  ELSE
    WRITE(unused)
  ENDIF
END CHILD
"""
        seed=dict(program='CHILD',path='TARGET',type=['QUEUE_TYPE'],
                  value=dict(initialized=True,sequence=7,entries=[[7,42]]))
        report,result=self.prepare([('MAIN',main),('CHILD',child)],variables=[seed])
        self.assert_inputs(report,[])
        self.assert_task_gaps(report,['task-scheduling','task-wait','task-continuation'])
        self.assertEqual(result['status'],'completed',result['error'])
        self.assertEqual(result['programs']['CHILD']['values']['TARGET']['entries'],[[1,31]])
        self.assertEqual(result['text_output'],' 1')

    def test_queue_assignment_replaces_entry_storage_held_by_pending_read(self):
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
VAR target,replacement:QUEUE_TYPE old_buf,new_buf:ARRAY[2] OF INTEGER
    stream:FILE first,entry,s:INTEGER
ROUTINE width:INTEGER
BEGIN
  target=replacement
  PAUSE
  RETURN 4
END width
BEGIN
  first=77
  INIT_QUEUE(target)
  APPEND_QUEUE(7,target,old_buf,entry,s)
  INIT_QUEUE(replacement)
  APPEND_QUEUE(7,replacement,new_buf,entry,s)
  OPEN FILE stream('RB','in')
  READ stream(first,target::width())
  PAUSE
END CHILD
"""
        report,result=self.prepare([('MAIN',main),('CHILD',child)],files={'in':{'hex':'090000002a000000'}})
        self.assertIn('condition-source',[row['code'] for row in report['unresolved']])
        self.assertEqual(result['status'],'failed')
        self.assertIn('Queue READ capture changed',result['error']['message'])
        values=result['programs']['CHILD']['values']
        self.assertEqual((values['FIRST'],values['STREAM']['position']),(77,0))
        self.assertEqual(values['TARGET']['entries'],[[1,7]])

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
