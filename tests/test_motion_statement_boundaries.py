"""Motion statements preserve enclosing source boundaries and clause ownership."""
from pathlib import Path
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.compiler import Parser
from karel2py.lexer import TranslationError
from tests.test_motion_requests import context, execute, program


class MotionStatementBoundaryTests(unittest.TestCase):
    def test_authored_example_matches_complete_independent_fixtures(self):
        from tools.run_examples import run_example
        run_example(Path(__file__).resolve().parents[1]/'examples/motion_statement_boundaries.kl')

    def test_every_move_form_can_end_an_inline_repeat(self):
        forms=('MOVE TO p VIA q','MOVE NEAR p BY 3','MOVE AWAY 1',
               'MOVE ABOUT v BY 4','MOVE AXIS 2 BY 5','MOVE RELATIVE v','MOVE ALONG route')
        for move in forms:
            with self.subTest(move=move):
                values,ctx,_,_=execute('APPEND_NODE(route,s) route[1].node_pos=p '
                    'n=0 ATTACH REPEAT n=n+1 '+move+' UNTIL n=2 RELEASE')
                self.assertEqual(values['N'],2)
                self.assertEqual([row['operation'] for row in ctx.motion.history],
                                 ['ATTACH',' '.join(move.split()[:2]),' '.join(move.split()[:2]),'RELEASE'])
                self.assertEqual(ctx.group_locks.owners,{})

    def test_nested_repeat_uses_nearest_terminator(self):
        values,ctx,_,_=execute('n=0 s=0 ATTACH REPEAT s=s+1 REPEAT n=n+1 MOVE AWAY 1 '
                              'UNTIL n>=2*s UNTIL s=2 RELEASE')
        self.assertEqual((values['N'],values['S']),(4,2))
        self.assertEqual(sum(row['operation']=='MOVE AWAY' for row in ctx.motion.history),4)

    def test_loop_condition_is_evaluated_after_each_move(self):
        routines='ROUTINE done:BOOLEAN BEGIN s=s+1 RETURN s=3 END done'
        values,ctx,_,_=execute('n=0 s=0 ATTACH REPEAT n=n+1 MOVE AWAY n UNTIL done() RELEASE',routines=routines)
        self.assertEqual((values['N'],values['S']),(3,3))
        self.assertEqual([row['data']['distance'] for row in ctx.motion.history if row['operation']=='MOVE AWAY'],[1.,2.,3.])

    def test_separators_produce_the_same_request_values(self):
        for separator in (' ',';','\n','\r\n'):
            with self.subTest(separator=repr(separator)):
                values,ctx,_,_=execute('n=0 ATTACH REPEAT n=n+1 MOVE AWAY 1'+separator+'UNTIL n=2 RELEASE')
                self.assertEqual(values['N'],2)
                self.assertEqual([row['data'] for row in ctx.motion.history],
                                 [{'groups':[1]},{'distance':1.},{'distance':1.},{'groups':[1]}])

    def test_following_with_settings_belong_only_to_following_move(self):
        _,ctx,_,_=execute('ATTACH MOVE AWAY 1 WITH $SPEED=20 MOVE AWAY 2 '
                           'WITH $SPEED=30 MOVE AWAY 3 RELEASE')
        rows=[row for row in ctx.motion.history if row['operation']=='MOVE AWAY']
        self.assertEqual([row['data']['distance'] for row in rows],[1.,2.,3.])
        self.assertNotIn('settings',rows[0]['data'])
        self.assertEqual(rows[1]['data']['settings'],[dict(name='$SPEED',group=1,value=20.)])
        self.assertEqual(rows[2]['data']['settings'],[dict(name='$SPEED',group=1,value=30.)])

    def test_with_move_can_end_repeat_and_nowait_keeps_its_own_request(self):
        values,ctx,_,_=execute('n=0 ATTACH REPEAT n=n+1 MOVE AWAY 1 NOWAIT '
            'WITH $SPEED=25 MOVE AWAY 2 UNTIL n=2 RELEASE')
        self.assertEqual(values['N'],2)
        self.assertEqual([row['nowait'] for row in ctx.motion.history if row['operation']=='MOVE AWAY'],[True,False,True,False])

    def test_comma_led_local_clauses_and_enclosing_until_remain_independent(self):
        values,ctx,_,_=execute('n=0 ATTACH REPEAT MOVE AWAY 1, WHEN TRUE DO n=n+1 '
                              'UNTIL FALSE ENDMOVE UNTIL n=2 RELEASE')
        self.assertEqual(values['N'],2)
        rows=[row for row in ctx.motion.history if row['operation']=='MOVE AWAY']
        self.assertEqual(len(rows),2)
        self.assertEqual([row['data']['execution']['triggered'] for row in rows],[[1],[1]])

    def test_pause_resumes_before_terminal_move_and_rechecks_loop(self):
        instance,ctx,_=program('n=0 ATTACH REPEAT n=n+1 PAUSE MOVE AWAY n UNTIL n=2 RELEASE')
        with self.assertRaises(rt.KarelPause):instance.run()
        self.assertEqual(instance.snapshot()['N'],1)
        with self.assertRaises(rt.KarelPause):instance.resume()
        self.assertEqual(instance.snapshot()['N'],2)
        self.assertEqual(instance.resume()['N'],2)
        self.assertEqual([row['data']['distance'] for row in ctx.motion.history if row['operation']=='MOVE AWAY'],[1.,2.])
        self.assertEqual(ctx.group_locks.owners,{})

    def test_linked_routine_loop_and_following_move_keep_source_owner(self):
        sources={'main.kl':'''PROGRAM MAIN VAR n:INTEGER
ROUTINE work:INTEGER FROM LIB BEGIN ATTACH n=work() RELEASE END MAIN''',
                 'lib.kl':'''PROGRAM LIB
ROUTINE work:INTEGER VAR n:INTEGER
BEGIN n=0 REPEAT n=n+1 MOVE AWAY 1 WITH $SPEED=25 MOVE AWAY 2 UNTIL n=2 RETURN n END work
BEGIN END LIB'''}
        ctx=context()
        instance=translate_project(sources).instantiate(context=ctx)
        self.assertEqual(instance.run('MAIN')['MAIN']['values'],{'N':2})
        rows=[row for row in ctx.motion.history if row['operation']=='MOVE AWAY']
        self.assertEqual(len(rows),4)
        self.assertEqual({row['source_program'] for row in rows},{'LIB'})
        self.assertEqual(ctx.group_locks.owners,{})

    def test_unclosed_inner_block_cannot_borrow_outer_repeat_until(self):
        with self.assertRaises(TranslationError) as caught:
            program('REPEAT IF TRUE THEN MOVE AWAY 1 UNTIL TRUE ENDIF UNTIL TRUE')
        self.assertEqual(caught.exception.code,'E_MOTION_CLAUSE')

    def test_parser_unwinds_block_context_after_failure(self):
        parser=Parser('PROGRAM T BEGIN REPEAT IF TRUE THEN MOVE AWAY 1 UNTIL TRUE END T','broken.kl',mode='pythonic')
        with self.assertRaises(TranslationError):parser.parse()
        self.assertEqual(parser._block_end_stack,[])

    def test_report_exposes_statement_scope_and_current_guide(self):
        policy=translate('PROGRAM T BEGIN REPEAT MOVE AWAY 1 UNTIL TRUE END T').report['motion_request_policy']
        self.assertIn('nearest parsed REPEAT',policy['statement_boundaries'])
        self.assertEqual(policy['statement_guide'],'docs/motion-statement-boundaries.md')
        self.assertFalse(policy['controller_validated'])

    def test_missing_comma_or_target_move_stays_rejected(self):
        for body in ('MOVE AWAY 1 UNTIL TRUE','MOVE AWAY 1 WHEN TRUE DO CANCEL',
                     'MOVE AWAY 1\nWHEN TRUE DO CANCEL','MOVE AWAY 1 WITH $SPEED=20',
                     'MOVE AWAY 1 VIA p','MOVE AWAY 1 ENDMOVE'):
            with self.subTest(body=body),self.assertRaises(TranslationError):program(body)

    def test_orphan_until_is_not_an_implicit_local_motion_clause(self):
        for body in ('MOVE AWAY 1\nUNTIL TRUE','UNTIL TRUE','WHILE TRUE DO MOVE AWAY 1 UNTIL TRUE ENDWHILE'):
            with self.subTest(body=body),self.assertRaises(TranslationError) as caught:program(body)
            self.assertEqual(caught.exception.code,'E_MOTION_CLAUSE')
            self.assertIn('comma',caught.exception.message)


class HandlerBoundaryDiagnosticTests(unittest.TestCase):
    def test_included_orphan_when_reports_its_original_file(self):
        with self.assertRaises(TranslationError) as caught:
            translate('PROGRAM T BEGIN\n%INCLUDE actions.inc\nEND T',filename='main.kl',
                      includes={'actions.inc':'MOVE AWAY 1\n  WHEN TRUE DO CANCEL'})
        self.assertEqual(caught.exception.code,'E_MOTION_CLAUSE')
        self.assertEqual((caught.exception.filename,caught.exception.token.line,caught.exception.token.column),('actions.inc',2,3))

    def test_orphan_when_is_a_clause_error_with_physical_location(self):
        source='PROGRAM T\nBEGIN\n  MOVE AWAY 1\n  WHEN TRUE DO CANCEL\nEND T'
        with self.assertRaises(TranslationError) as caught:translate(source,filename='authored.kl')
        self.assertEqual(caught.exception.code,'E_MOTION_CLAUSE')
        self.assertEqual((caught.exception.filename,caught.exception.token.line,caught.exception.token.column),('authored.kl',4,3))
        self.assertIn('comma',caught.exception.message)

    def test_missing_motion_terminator_names_expected_endmove(self):
        for ending in ('END T','ENDCONDITION','ENDWHILE',''):
            with self.subTest(ending=ending),self.assertRaises(TranslationError) as caught:
                translate('PROGRAM T VAR n:INTEGER BEGIN MOVE AWAY 1, WHEN TRUE DO n=1 '+ending)
            self.assertEqual(caught.exception.code,'E_MOTION_CLAUSE')
            self.assertIn('expected ENDMOVE',caught.exception.message)

    def test_missing_condition_terminator_names_expected_endcondition(self):
        for ending in ('END T','ENDMOVE','ENDWHILE',''):
            with self.subTest(ending=ending),self.assertRaises(TranslationError) as caught:
                translate('PROGRAM T VAR n:INTEGER BEGIN CONDITION[1]: WHEN TRUE DO n=1 '+ending)
            self.assertEqual(caught.exception.code,'E_SYNTAX')
            self.assertIn('expected ENDCONDITION',caught.exception.message)

    def test_valid_nested_action_blocks_retain_their_own_terminators(self):
        result=translate('''PROGRAM T VAR n:INTEGER BEGIN n=0
CONDITION[1]: WHEN n=1 DO IF TRUE THEN REPEAT n=n+1 UNTIL n=2 ENDIF ENDCONDITION
ENABLE CONDITION[1] n=1 n=n+10 END T''')
        namespace={'__name__':'boundary_handler_test'};exec(result.python_source,namespace)
        self.assertEqual(namespace['Program']().run(),{'N':12})


if __name__=='__main__':unittest.main()
