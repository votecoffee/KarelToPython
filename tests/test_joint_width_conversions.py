"""Authored source-level padding, zero-only narrowing and private interfaces."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt, translate, translate_project
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint, model_context
from tests.test_project_scheduler import source


def program(body='b=a', *, widths=(2, 9), routines='', prefix='', cooperative=False, **options):
    first, second=widths
    return compile_program(body, decl=f'a:JOINTPOS{first} b:JOINTPOS{second} n,s:INTEGER',
                           routines=routines, prefix=prefix, cooperative=cooperative, **options)


class JointWidthTests(unittest.TestCase):
    def test_every_declared_width_pair_copies_and_zero_pads_without_context(self):
        for first in range(1, 10):
            for second in range(1, 10):
                with self.subTest(first=first, second=second):
                    p,_=program(widths=(first,second));axes=[4.] + [0.]*(first-1)
                    p._state.values['A']=joint(axes)
                    state=p.run()
                    self.assertEqual(state['B']['axes'],axes[:second]+[0.]*max(0,second-first))
                    self.assertEqual(state['A']['axes'],axes)
                    self.assertIsNot(p._state.values['A'],p._state.values['B'])
                    self.assertFalse(p.service_requests)

    def test_narrowing_nonzero_tail_preserves_destination(self):
        p,_=program(widths=(4,2));p._state.values['A']=joint([1.,2.,0.,3.]);p._state.values['B']=joint([8.,9.])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'zero discarded') as error:p.run()
        self.assertIsNotNone(error.exception.line)
        self.assertEqual(p.snapshot()['B']['axes'],[8.,9.])

    def test_cross_width_requires_all_source_axes_known(self):
        for width in (1,3):
            p,_=program(widths=(2,width));p._state.values['A']=joint([1.,rt.UNINITIALIZED])
            with self.subTest(width=width),self.assertRaises(rt.KarelRuntimeError):p.run()
            self.assertTrue(all(x=={'uninitialized':True} for x in p.snapshot()['B']['axes']))

    def test_same_width_keeps_partial_data_copy(self):
        p,_=program(widths=(2,2));p._state.values['A']=joint([1.,rt.UNINITIALIZED])
        self.assertEqual(p.run()['B']['axes'],[1.,{'uninitialized':True}])

    def test_malformed_nonfinite_boolean_and_unknown_axes_fail(self):
        for axis in (True,float('nan'),float('inf'),rt.UNKNOWN_BYTE,'0'):
            p,_=program();p._state.values['A']=joint([1.,axis])
            with self.subTest(axis=axis),self.assertRaises(rt.KarelRuntimeError):p.run()
        p,_=program();p._state.values['A'].values[:]=[0.]
        with self.assertRaisesRegex(rt.KarelRuntimeError,'Malformed'):p.run()

    def test_negative_zero_tail_is_allowed(self):
        p,_=program(widths=(3,1));p._state.values['A']=joint([7.,-0.,0.])
        self.assertEqual(p.run()['B']['axes'],[7.])

    def test_bare_cross_width_argument_owns_private_writable_storage(self):
        p,_=program('work(a)',routines='ROUTINE work(v:JOINTPOS9) BEGIN v=b END work')
        p._state.values['A']=joint([1.,2.]);p._state.values['B']=joint([9.]*9)
        self.assertEqual(p.run()['A']['axes'],[1.,2.])

    def test_exact_bare_argument_still_aliases(self):
        p,_=program('work(a)',widths=(2,2),routines='ROUTINE work(v:JOINTPOS2) BEGIN v=b END work')
        p._state.values['A']=joint([1.,2.]);p._state.values['B']=joint([8.,9.])
        self.assertEqual(p.run()['A']['axes'],[8.,9.])

    def test_return_widens_then_assignment_narrows(self):
        p,result=program('a=make()',routines='ROUTINE make:JOINTPOS9 BEGIN RETURN a END make')
        p._state.values['A']=joint([1.,2.]);self.assertEqual(p.run()['A']['axes'],[1.,2.])
        self.assertEqual([r['operation'] for r in result.report['joint_width_conversions']],['RETURN','ASSIGNMENT'])
        self.assertTrue(result.report['joint_width_conversions'][0]['before_cleanup'])

    def test_return_failure_unwinds_frames_and_preserves_target(self):
        p,_=program('b=make()',widths=(4,2),routines='ROUTINE make:JOINTPOS2 BEGIN RETURN a END make')
        p._state.values['A']=joint([1.,2.,3.,0.]);p._state.values['B']=joint([8.,9.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B']['axes'],[8.,9.]);self.assertEqual(p._state.local_frames,[])

    def test_argument_is_captured_before_later_argument_effects(self):
        p,_=program('work(a,later())',routines='''ROUTINE later:INTEGER BEGIN a=b RETURN 1 END later
ROUTINE work(v:JOINTPOS9; k:INTEGER) BEGIN b=v END work''')
        p._state.values['A']=joint([1.,2.]);p._state.values['B']=joint([8.,9.]+[0.]*7)
        state=p.run();self.assertEqual(state['A']['axes'],[8.,9.]);self.assertEqual(state['B']['axes'],[1.,2.]+[0.]*7)

    def test_failed_argument_skips_later_effects_and_callee(self):
        p,_=program('n=0 work(a,later())',widths=(4,2),routines='''ROUTINE later:INTEGER BEGIN n=n+1 RETURN 1 END later
ROUTINE work(v:JOINTPOS2; k:INTEGER) BEGIN n=99 END work''')
        p._state.values['A']=joint([1.,2.,3.,0.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_assignment_converts_before_target_index_effect(self):
        p,_=compile_program('n=0 items[at()]=a',decl='a:JOINTPOS4 items:ARRAY[1] OF JOINTPOS2 n:INTEGER',
                            routines='ROUTINE at:INTEGER BEGIN n=n+1 RETURN 1 END at')
        p._state.values['A']=joint([1.,2.,3.,0.])
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['N'],0)

    def test_source_and_target_index_functions_run_once(self):
        p,result=compile_program('n=0 items[at()]=a',decl='a:JOINTPOS2 items:ARRAY[1] OF JOINTPOS9 n:INTEGER',
                                 routines='ROUTINE at:INTEGER BEGIN n=n+1 RETURN 1 END at')
        p._state.values['A']=joint([1.,2.]);state=p.run()
        self.assertEqual(state['N'],1);self.assertEqual(state['ITEMS'][0]['axes'],[1.,2.]+[0.]*7)
        self.assertEqual(result.report['joint_width_conversions'][0]['operation'],'ASSIGNMENT')

    def test_structure_field_and_chained_array_elements(self):
        p,_=compile_program('b[1][1]=a.j',decl='a:item_t b:ARRAY[1,1] OF JOINTPOS9',
                            prefix='TYPE item_t=STRUCTURE j:JOINTPOS2 ENDSTRUCTURE')
        p._state.values['A'].values['J']=joint([3.,4.])
        self.assertEqual(p.run()['B'][0][0]['axes'],[3.,4.]+[0.]*7)

    def test_label_dispatch_and_cooperative_execution(self):
        for labelled in ('','entry:: '):
            for cooperative in (False,True):
                p,_=program(labelled+'b=a',cooperative=cooperative);p._state.values['A']=joint([1.,2.])
                with self.subTest(labelled=labelled,cooperative=cooperative):self.assertEqual(p.run()['B']['axes'],[1.,2.]+[0.]*7)

    def test_pause_and_resume_keep_private_argument(self):
        p,_=program('work(a)',routines='ROUTINE work(v:JOINTPOS9) BEGIN PAUSE b=v END work')
        p._state.values['A']=joint([1.,2.])
        with self.assertRaises(rt.KarelPause):p.run()
        p._state.values['A']=joint([8.,9.]);self.assertEqual(p.resume()['B']['axes'],[1.,2.]+[0.]*7)

    def test_robot_context_is_not_read_or_changed(self):
        ctx=model_context();before=deepcopy(ctx.robot.to_config());p,_=program(context=ctx)
        p._state.values['A']=joint([3.,4.]);p.run();self.assertEqual(ctx.robot.to_config(),before)

    def test_output_context_retains_each_concrete_width(self):
        p,_=program();p._state.values['A']=joint([1.,2.]);p.run()
        config=json.loads(json.dumps(p._state.execution.to_config()))
        self.assertIsInstance(config,dict)
        self.assertEqual(p._state.values['A'].spec,('JOINTPOS',2));self.assertEqual(p._state.values['B'].spec,('JOINTPOS',9))

    def test_source_and_library_use_private_conversion_with_exact_declarations(self):
        result=translate_project({'lib':source('LIB','',routines='ROUTINE work(v:JOINTPOS9):JOINTPOS9 BEGIN RETURN v END work'),
            'main':source('MAIN','b=work(a)',decl='a:JOINTPOS2 b:JOINTPOS9',routines='ROUTINE work(v:JOINTPOS9):JOINTPOS9 FROM LIB')})
        instance=result.instantiate();instance.programs['MAIN']._state.values['A']=joint([3.,4.])
        instance.run('MAIN');self.assertEqual(instance.programs['MAIN'].snapshot()['B']['axes'],[3.,4.]+[0.]*7)

    def test_legacy_rejects_cross_width_assignment_argument_and_return(self):
        for body,routines in (('b=a',''),('work(a)','ROUTINE work(v:JOINTPOS9) BEGIN END work'),
                              ('','ROUTINE make:JOINTPOS9 BEGIN RETURN a END make')):
            with self.subTest(body=body),self.assertRaises(TranslationError):
                legacy_translate('PROGRAM T VAR a:JOINTPOS2 b:JOINTPOS9 '+routines+' BEGIN '+body+' END T')

    def test_whole_arrays_and_byname_remain_exact(self):
        with self.assertRaises(TranslationError):compile_program('b=a',prefix='TYPE a_t=ARRAY[1] OF JOINTPOS2 b_t=ARRAY[1] OF JOINTPOS9',decl='a:a_t b:b_t')
        p,_=program("s=77 work(BYNAME('','a',s))",routines='ROUTINE work(v:JOINTPOS9) BEGIN END work')
        p._state.values['A']=joint([1.,2.])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['S'],77)

    def test_runtime_helper_rejects_legacy_and_malformed_types(self):
        with rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):rt.convert_joint_width(('JOINTPOS',9),joint([0.]))
        with rt._numeric_scope('pythonic'):
            for spec in ((),None,('REAL',),('JOINTPOS',0),('JOINTPOS',True)):
                with self.subTest(spec=spec),self.assertRaises(rt.KarelRuntimeError):rt.convert_joint_width(spec,joint([0.]),17)

    def test_report_is_json_serializable_and_distinguishes_private_conversions(self):
        p,result=program('b=work(a)',routines='ROUTINE work(v:JOINTPOS9):JOINTPOS9 BEGIN RETURN v END work')
        report=json.loads(json.dumps(result.report));site=report['joint_width_conversions'][0]
        self.assertEqual(site['source_type_spec'],['JOINTPOS',2]);self.assertTrue(site['independent_value'])
        self.assertEqual(report['positional_value_arguments'][0]['conversion_kind'],'joint_width')


if __name__=='__main__':unittest.main()
