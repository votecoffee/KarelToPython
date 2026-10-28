"""Cross-service loop, suspension and scoped ownership behavior."""
import unittest

from karel2py import translate, translate_project, runtime as rt
from karel2py.lexer import TranslationError


SOURCES = {
    'main.kl': '''PROGRAM MAIN
%LOCKGROUP=1
VAR i,total:INTEGER
ROUTINE work:INTEGER FROM LIB
BEGIN
  total=0
  FOR i=1 TO 2 DO total=total+work() ENDFOR
END MAIN''',
    'lib.kl': '''PROGRAM LIB
%LOCKGROUP=2
ROUTINE work:INTEGER
VAR j,total:INTEGER
BEGIN
  total=0
  FOR j=1 TO 3 DO
    total=total+j
    PAUSE
    GOTO finished
  ENDFOR
  finished:: RETURN total
END work
BEGIN END LIB''',
}
U = {'uninitialized': True}


def project(groups=(1, 2)):
    locks = rt.GroupLocks(list(groups), apply_directives=True, callee_scopes=True)
    context = rt.ExecutionContext(group_locks=locks)
    return translate_project(SOURCES).instantiate(context=context), locks


class ConversionScopeIntegrationTests(unittest.TestCase):
    def test_resume_releases_callee_scope_and_reenters_next_loop_iteration(self):
        instance, locks = project()
        instance.run('MAIN')
        main = instance.programs['MAIN']
        owner = main._state
        self.assertEqual(main.snapshot(), {'I': 1, 'TOTAL': 0})
        self.assertEqual(locks.owners, {1: owner, 2: owner})
        instance.scheduler.continue_task('MAIN'); instance.scheduler.run()
        self.assertEqual(main.snapshot(), {'I': 2, 'TOTAL': 1})
        self.assertEqual(locks.owners, {1: owner, 2: owner})
        instance.scheduler.continue_task('MAIN'); instance.scheduler.run()
        self.assertEqual(main.snapshot(), {'I': U, 'TOTAL': 2})
        self.assertEqual(locks.owners, {})
        self.assertEqual(owner._task_frames, [])

    def test_stop_unwinds_both_dispatcher_counters_and_scoped_locks(self):
        instance, locks = project()
        instance.run('MAIN')
        main = instance.programs['MAIN']
        library = main._state._task_frames[-1][0]
        inner_counter = library.reference('J')
        self.assertEqual(inner_counter.raw(), 1)
        instance.scheduler.stop('MAIN')
        self.assertEqual(main.snapshot(), {'I': U, 'TOTAL': 0})
        self.assertIs(inner_counter.raw(), rt.UNINITIALIZED)
        self.assertEqual(locks.owners, {})
        self.assertEqual(main._state._task_frames, [])

    def test_callee_start_failure_unwinds_caller_counter_and_root_lock(self):
        instance, locks = project(groups=(1,))
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'unconfigured'):
            instance.run('MAIN')
        self.assertEqual(instance.programs['MAIN'].snapshot(), {'I': U, 'TOTAL': 0})
        self.assertEqual(locks.owners, {})
        self.assertEqual(instance.programs['MAIN']._state._task_frames, [])

    def test_labeled_pipe_batch_cannot_write_an_active_counter(self):
        source = '''PROGRAM T VAR i:INTEGER BEGIN
FOR i=1 TO 2 DO mark:: COPY_FILE('PIP:*','saved_*.DAT',TRUE,FALSE,i) ENDFOR
END T'''
        with self.assertRaises(TranslationError) as caught:
            translate(source)
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')
        self.assertIn('active FOR counter', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
