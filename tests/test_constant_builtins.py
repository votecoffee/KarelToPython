"""Authored compile-time scalar calls, scope, domains and nonexecution checks."""
import ast
import json
from pathlib import Path
import unittest
from unittest import mock

from karel2py import translate,translate_project,load_project,runtime as rt
from karel2py.compiler import CONSTANT_BUILTINS
from karel2py.input_discovery import discover_inputs
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


ROOT=Path(__file__).resolve().parents[1]


def build(prefix='',body='n=result',decl='n,m:INTEGER r:REAL text:STRING[16]',routines='',**options):
    result=translate(f'PROGRAM T\n{prefix}\nVAR {decl}\n{routines}\nBEGIN {body} END T',**options)
    ast.parse(result.python_source,feature_version=(3,11));json.dumps(result.report,allow_nan=False)
    namespace={'__name__':'constant_builtin_test'};exec(result.python_source,namespace)
    return namespace['Program'](),result


class ConstantBuiltinValues(unittest.TestCase):
    def test_supported_math_and_text_values_match_independent_expectations(self):
        cases=[('ABS(-7)',7),('ABS(-7.25)',7.25),('ROUND(2.5)',2),('ROUND(3.5)',4),
            ('TRUNC(-7.9)',-7),('SQRT(9)',3.0),('SQRT(2)',1.4142135623730951),
            ('EXP(0)',1.0),('LN(1)',0.0),('SIN(30)',0.5),('COS(60)',0.5),('TAN(45)',1.0),
            ('ASIN(0.5)',30.0),('ACOS(0.5)',60.0),('ATAN2(1,1)',45.0),('ATAN2(0,1)',90.0),
            ("STR_LEN('a''b')",3),("SUB_STR('abc',2,99)",'bc'),("INDEX('abc','b')",2),
            ("INDEX('abc','')",1),('CHR(65)','A'),("ORD('AZ',2)",90),('CHR(0)','\x00')]
        for expression,expected in cases:
            with self.subTest(expression=expression):
                target='text' if type(expected) is str else 'r' if type(expected) is float else 'n'
                program,result=build('CONST result='+expression,body=target+'=result')
                # The generated program must use resolved constants rather than
                # defer even these pure calls until module load or execution.
                with mock.patch.object(rt,'builtin',side_effect=AssertionError('runtime call')):actual=program.run()[target.upper()]
                if type(expected) is float:self.assertAlmostEqual(actual,expected)
                else:self.assertEqual(actual,expected)
                self.assertTrue(result.report['constant_builtin_uses'])

    def test_nested_calls_with_forward_dependencies(self):
        program,result=build("CONST result=ROUND(SQRT(square))+STR_LEN(label) square=9 label=SUB_STR(word,2,3) word='abcde'")
        self.assertEqual(program.run()['N'],6)
        self.assertEqual([row['name'] for row in result.report['constant_resolution_order']],['SQUARE','WORD','LABEL','RESULT'])
        self.assertTrue(any(row['dependency']=='SQUARE' and row['forward'] for row in result.report['constant_dependencies']))

    def test_empty_and_clipped_substrings(self):
        for expression in ("SUB_STR('abc',4,99)","SUB_STR('abc',2,0)"):
            with self.subTest(expression=expression):self.assertEqual(build('CONST result='+expression,body='text=result')[0].run()['TEXT'],'')

    def test_constants_are_private_values_when_passed_to_writable_formals(self):
        routine='ROUTINE edit(value:INTEGER) BEGIN value=99 END edit'
        program,_=build('CONST result=ROUND(7.2)',body='edit(result) n=result',routines=routine)
        self.assertEqual(program.run()['N'],7)

    def test_no_constant_call_is_an_execution_input(self):
        _,result=build('CONST result=ROUND(SQRT(9))')
        report=discover_inputs(result.python_source)
        self.assertTrue(report['complete']);self.assertEqual(report['inputs'],[])


class ConstantBuiltinScopesAndShapes(unittest.TestCase):
    def test_array_and_string_dimensions_from_resolved_constants(self):
        program,_=build("CONST count=ROUND(SQRT(later)) later=9 width=STR_LEN('ready') TYPE row_t=ARRAY[count]OF INTEGER",
            decl='a:row_t text:STRING[width] n:INTEGER',body="a[3]=7 text='abcdef' n=a[3]")
        self.assertEqual(program.run(),dict(A=[{'uninitialized':True},{'uninitialized':True},7],TEXT='abcde',N=7))

    def test_direct_static_schema_expressions(self):
        program,result=build(decl="a:ARRAY[ABS(-2)]OF INTEGER text:STRING[STR_LEN('abc')] n:INTEGER",
                             body="a[2]=7 text='abcdef' n=a[2]")
        values=program.run();self.assertEqual((values['N'],values['TEXT']),(7,'abc'))
        self.assertTrue(all(row['constant'] is None for row in result.report['constant_builtin_uses']))

    def test_group_annotations_from_pure_calls(self):
        _,result=build(decl='p:XYZWPR IN GROUP[ROUND(2.1)]',body='')
        self.assertEqual(result.report['group_declarations'][0]['group'],2)

    def test_routine_local_forward_calls_precede_local_array_shapes(self):
        routine="ROUTINE work VAR a:ARRAY[count]OF INTEGER CONST count=STR_LEN(token) token=SUB_STR('abcd',2,2) BEGIN a[2]=7 n=a[2] END work"
        program,result=build(body='work',routines=routine)
        self.assertEqual(program.run()['N'],7)
        self.assertTrue(all(row['routine']=='WORK' for row in result.report['constant_builtin_uses']))

    def test_local_and_global_constant_dependencies_stay_lexical(self):
        routines='ROUTINE one CONST step=ROUND(base+0.2) BEGIN n=step END one ROUTINE two CONST step=ABS(-9) BEGIN m=step END two'
        program,_=build('CONST base=SQRT(49)',body='one two',routines=routines)
        values=program.run();self.assertEqual((values['N'],values['M']),(7,9))

    def test_routine_array_results_use_global_folded_schema(self):
        routine='ROUTINE make:ARRAY[count]OF INTEGER VAR local:ARRAY[count]OF INTEGER BEGIN local[1]=4 local[2]=7 RETURN local END make'
        program,_=build('CONST count=ROUND(2.5)',body='a=make n=a[2]',decl='a:ARRAY[2]OF INTEGER n:INTEGER',routines=routine)
        self.assertEqual(program.run()['N'],7)

    def test_linked_modules_resolve_calls_before_exact_interfaces(self):
        main='PROGRAM MAIN CONST count=STR_LEN(\'ab\') TYPE row_t=ARRAY[count]OF INTEGER VAR a:row_t ROUTINE fill(p:row_t) FROM LIB BEGIN fill(a) END MAIN'
        lib='PROGRAM LIB CONST count=ROUND(2.5) TYPE row_t=ARRAY[count]OF INTEGER ROUTINE fill(p:row_t) CONST value=ABS(-7) BEGIN p[1]=value p[2]=value+1 END fill BEGIN END LIB'
        project=translate_project({'main.kl':main,'lib.kl':lib}).instantiate()
        self.assertEqual(project.run('MAIN')['MAIN']['values']['A'],[7,8])

    def test_stored_source_translation_folds_calls_without_running_child_body(self):
        from tests.test_source_translations import context,run,artifact
        child='PROGRAM CHILD CONST amount=ROUND(SQRT(49)) VAR value,status:INTEGER BEGIN value=amount SET_INT_REG(1,99,status) END CHILD'
        ctx=context(child);ctx.numeric=rt.NumericRegisters(1,{1:7})
        values,_,_,_=run(ctx=ctx)
        self.assertEqual(values['STATUS'],0)
        self.assertEqual(ctx.numeric.snapshot(),{1:7})
        self.assertNotIn('CHILD',ctx.variables.programs)
        self.assertEqual(artifact(ctx,'child.kl'),child.encode())
        namespace={'__name__':'authored_child'};exec(artifact(ctx,'child.py'),namespace)
        runtime_context=rt.ExecutionContext(numeric=rt.NumericRegisters(1,{1:7}))
        self.assertEqual(namespace['Program'](context=runtime_context).run(),dict(VALUE=7,STATUS=0))
        self.assertEqual(runtime_context.numeric.snapshot(),{1:99})


class ConstantBuiltinGuards(unittest.TestCase):
    def reject(self,prefix,**options):
        with self.assertRaises(TranslationError) as caught:build(prefix,**options)
        self.assertEqual(caught.exception.code,'E_CONSTANT',str(caught.exception))

    def test_invalid_domains_types_and_arity_fail_during_translation(self):
        cases=['ABS()','ABS(1,2)','ABS(TRUE)','SQRT(-1)','LN(0)','EXP(1000)','SIN(TRUE)','ASIN(2)',
            'ACOS(-2)','TAN(90)','ATAN2(0,0)','ROUND(2147483647.0)',"STR_LEN(1)",
            "SUB_STR('a',0,1)","SUB_STR('a',1,-1)","INDEX('a',1)",'CHR(128)',"ORD('',1)",
            "ORD('a',0)","ORD('a',2)",'ABS(MININT)']
        for expression in cases:
            with self.subTest(expression=expression):self.reject('CONST result='+expression,body='')

    def test_stateful_resource_geometry_and_user_calls_stay_blocked(self):
        for expression in ('GET_USEC_TIM()','CURJPOS()','UNINIT(n)','ARRAY_LEN(a)','VEC(1,2,3)','answer()'):
            with self.subTest(expression=expression):self.reject('CONST result='+expression,body='',decl='n:INTEGER a:ARRAY[2]OF INTEGER',routines='ROUTINE answer:INTEGER BEGIN RETURN 7 END answer')

    def test_hidden_invalid_arguments_and_unused_declarations_are_checked(self):
        self.reject('CONST result=FALSE AND (SQRT(-1)>0)',body='')
        self.reject('',body='',routines='ROUTINE unused CONST value=SQRT(-1) BEGIN END unused')

    def test_runtime_and_unknown_names_are_not_folded(self):
        self.reject('CONST result=ABS(n)')
        self.reject('CONST result=STR_LEN(missing)')

    def test_calls_do_not_hide_cycles(self):
        self.reject('CONST result=ROUND(next) next=ABS(result)')

    def test_local_scope_does_not_leak_into_global_interfaces(self):
        self.reject('',body='',routines="ROUTINE make:STRING[STR_LEN(local)] CONST local='abc' BEGIN RETURN local END make")

    def test_old_strict_constant_calls_remain_rejected(self):
        with self.assertRaises(TranslationError) as caught:legacy_translate('PROGRAM T CONST value=SQRT(4.0) BEGIN END T')
        self.assertEqual(caught.exception.code,'E_CONSTANT')

    def test_bounded_evaluation_count(self):
        with mock.patch('karel2py.compiler.MAX_CONSTANT_BUILTIN_CALLS',1):self.reject('CONST a=ABS(-1) b=ABS(-2)',body='')

    def test_nested_call_limit(self):
        valid='ABS('*64+'1'+')'*64
        self.assertEqual(build('CONST result='+valid)[0].run()['N'],1)
        self.reject('CONST result=ABS('+valid+')',body='')

    def test_translation_does_not_execute_source_or_arbitrary_python(self):
        with mock.patch('builtins.exec',side_effect=AssertionError('executed')):
            with mock.patch('builtins.eval',side_effect=AssertionError('evaluated')):
                with mock.patch.object(rt.State,'__init__',side_effect=AssertionError('program state created')):
                    result=translate("PROGRAM T CONST count=STR_LEN('abc') BEGIN END T")
        self.assertEqual(result.report['global_constants'][0]['value'],3)


class ConstantBuiltinMetadata(unittest.TestCase):
    def test_authored_examples_match_independent_fixtures(self):
        from tools.run_examples import run_example
        for name in ('constant_builtin_values','constant_builtin_shapes','constant_builtin_locals'):
            with self.subTest(name=name):run_example(ROOT/'examples'/(name+'.kl'))
        folder=ROOT/'examples/constant_builtins_linked'
        instance=load_project(folder).instantiate()
        self.assertEqual(instance.run('MAIN'),json.loads((folder/'expected.json').read_bytes()))

    def test_policy_and_source_positions(self):
        _,result=build('CONST result=ROUND(SQRT(9))')
        self.assertEqual(set(result.report['constant_builtin_policy']['functions']),CONSTANT_BUILTINS)
        self.assertEqual(len(CONSTANT_BUILTINS),17)
        self.assertEqual([row['function'] for row in result.report['constant_builtin_uses']],['SQRT','ROUND'])
        self.assertTrue(all(row['constant']=='RESULT' and row['source_file']=='<input>' and row['runtime_call'] is False for row in result.report['constant_builtin_uses']))

    def test_include_calls_and_errors_retain_physical_origins(self):
        source='PROGRAM T\n%INCLUDE defs.inc\nVAR n:INTEGER BEGIN n=result END T'
        result=translate(source,filename='main.kl',includes={'defs.inc':'CONST result=ROUND(SQRT(9))'})
        self.assertTrue(all(row['source_file']=='defs.inc' and row['source_line']==1 for row in result.report['constant_builtin_uses']))
        with self.assertRaises(TranslationError) as caught:translate(source,filename='main.kl',includes={'defs.inc':'CONST result=SQRT(-1)'})
        self.assertEqual((caught.exception.filename,caught.exception.token.line),('defs.inc',1))


if __name__=='__main__':unittest.main()
