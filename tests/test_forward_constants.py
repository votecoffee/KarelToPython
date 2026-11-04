"""Forward CONST graphs keep lexical scope and checked scalar semantics."""
import ast
import json
import unittest
from karel2py import translate,translate_project,runtime as rt
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate


def build(prefix='CONST first=later later=7',body='n=first',*,decl='n,m:INTEGER flag:BOOLEAN text:STRING[8] real_value:REAL',routines='',translator=translate,**options):
    result=translator(f'PROGRAM T\n{prefix}\nVAR {decl}\n{routines}\nBEGIN\n{body}\nEND T',**options)
    ast.parse(result.python_source,feature_version=(3,11));json.dumps(result.report)
    namespace={'__name__':'forward_constant_test'};exec(result.python_source,namespace)
    return namespace['Program'](),result


def run(*args,**kwargs):return build(*args,**kwargs)[0].run()


class ForwardConstantScalars(unittest.TestCase):
    def test_integer_alias(self):self.assertEqual(run()['N'],7)
    def test_casefolded_chain(self):self.assertEqual(run('CONST First=NEXT next=LaSt last=7')['N'],7)
    def test_arithmetic_chain(self):self.assertEqual(run('CONST first=later*2+1 later=3')['N'],7)
    def test_parenthesized_dependency(self):self.assertEqual(run('CONST first=((later)) later=7')['N'],7)
    def test_unary_minus(self):self.assertEqual(run('CONST first=-later later=7')['N'],-7)
    def test_real_literal(self):self.assertEqual(run('CONST first=later later=0.1',body='real_value=first')['REAL_VALUE'],.1)
    def test_real_promotion(self):self.assertEqual(run('CONST first=later+0.5 later=7',body='real_value=first')['REAL_VALUE'],7.5)
    def test_negative_mod(self):self.assertEqual(run('CONST first=later MOD 3 later=-7')['N'],2)
    def test_integer_division(self):self.assertEqual(run('CONST first=later DIV 3 later=22')['N'],7)
    def test_boolean_not(self):self.assertTrue(run('CONST first=NOT later later=OFF',body='flag=first')['FLAG'])
    def test_boolean_plus(self):self.assertTrue(run('CONST first=+later later=ON',body='flag=first')['FLAG'])
    def test_boolean_binary(self):self.assertTrue(run('CONST first=later AND ON later=ON',body='flag=first')['FLAG'])
    def test_comparison(self):self.assertTrue(run('CONST first=later<8 later=7',body='flag=first')['FLAG'])
    def test_string_concat(self):self.assertEqual(run("CONST first=later+'cd' later='ab'",body='text=first')['TEXT'],'abcd')
    def test_doubled_apostrophe(self):self.assertEqual(run("CONST first=later later='a''b'",body='text=first')['TEXT'],"a'b")
    def test_empty_string(self):self.assertEqual(run("CONST first=later later=''",body='text=first')['TEXT'],'')
    def test_predefined_minint(self):self.assertEqual(run('CONST first=later later=MININT')['N'],-2147483648)
    def test_predefined_maxint_checked_at_storage(self):
        p,_=build('CONST first=later later=MAXINT')
        with self.assertRaises(rt.KarelRuntimeError):p.run()
    def test_multiple_global_sections(self):self.assertEqual(run('CONST first=later TYPE alias=INTEGER CONST later=7')['N'],7)
    def test_constant_after_global_var(self):self.assertEqual(run('CONST first=later',decl='n:INTEGER CONST later=7')['N'],7)
    def test_diamond_graph(self):self.assertEqual(run('CONST first=left+right left=last+1 right=last+2 last=2')['N'],7)
    def test_repeated_dependency_is_not_cycle(self):self.assertEqual(run('CONST first=later+later later=3')['N'],6)
    def test_long_chain_is_iterative(self):
        prefix='CONST '+' '.join(f'c{i}=c{i+1}' for i in range(1100))+' c1100=7'
        self.assertEqual(run(prefix,body='n=c0')['N'],7)


class ForwardConstantSchemas(unittest.TestCase):
    def test_global_array_dimension(self):self.assertEqual(run('CONST count=later later=2',body='items[2]=7 n=items[2]',decl='n:INTEGER items:ARRAY[count]OF INTEGER')['N'],7)
    def test_global_string_capacity(self):self.assertEqual(run('CONST width=later later=3',body="text='abcdef'",decl='text:STRING[width]')['TEXT'],'abc')
    def test_named_array_with_forward_types(self):self.assertEqual(run('TYPE row_t=ARRAY[count]OF item_t item_t=INTEGER CONST count=later later=2',body='items[2]=7 n=items[2]',decl='n:INTEGER items:row_t')['N'],7)
    def test_structure_field_shape(self):self.assertEqual(run('TYPE item_t=STRUCTURE row:ARRAY[count]OF INTEGER ENDSTRUCTURE CONST count=later later=2',body='item.row[2]=7 n=item.row[2]',decl='n:INTEGER item:item_t')['N'],7)
    def test_result_shape_uses_global_chain(self):
        p,_=build('CONST count=later later=2',body='a=make n=a[2]',decl='n:INTEGER a:ARRAY[2]OF INTEGER',routines='ROUTINE make:ARRAY[count]OF INTEGER VAR local:ARRAY[count]OF INTEGER BEGIN local[2]=7 RETURN local END make');self.assertEqual(p.run()['N'],7)
    def test_result_capacity_uses_global_chain(self):self.assertEqual(run('CONST width=later later=3',body='text=make',routines="ROUTINE make:STRING[width] BEGIN RETURN 'abcdef' END make")['TEXT'],'abc')
    def test_group_annotation_uses_global_chain(self):
        _,r=build('CONST group_id=later later=2',body='',decl='pose:XYZWPR IN GROUP[group_id]');self.assertEqual(r.report['group_declarations'][0]['group'],2)
    def test_local_array_before_constants(self):self.assertEqual(run('',body='work',routines='ROUTINE work VAR row:ARRAY[count]OF INTEGER CONST count=later later=2 BEGIN row[2]=7 n=row[2] END work')['N'],7)
    def test_local_string_before_constants(self):self.assertEqual(run('',body='work',routines="ROUTINE work VAR word:STRING[width] CONST width=later later=3 BEGIN word='abcdef' text=word END work")['TEXT'],'abc')
    def test_local_group_before_constants(self):
        _,r=build('',body='work',routines='ROUTINE work VAR pose:XYZWPR IN GROUP[group_id] CONST group_id=later later=2 BEGIN END work');self.assertEqual(r.report['group_declarations'][0]['group'],2)
    def test_global_shape_cannot_use_routine_constant(self):
        with self.assertRaises(TranslationError) as e:build('',decl='items:ARRAY[count]OF INTEGER',body='',routines='ROUTINE work CONST count=2 BEGIN END work')
        self.assertEqual(e.exception.code,'E_CONSTANT')
    def test_result_shape_cannot_use_local_constant(self):
        with self.assertRaises(TranslationError) as e:build('',body='',routines='ROUTINE make:ARRAY[count]OF INTEGER CONST count=2 BEGIN END make')
        self.assertEqual(e.exception.code,'E_CONSTANT')
    def test_result_capacity_cannot_use_local_constant(self):
        with self.assertRaises(TranslationError) as e:build('',body='',routines='ROUTINE make:STRING[width] CONST width=3 BEGIN END make')
        self.assertEqual(e.exception.code,'E_CONSTANT')
    def test_boolean_size_remains_invalid(self):
        with self.assertRaises(TranslationError) as e:build('CONST count=later later=ON',decl='a:ARRAY[count]OF INTEGER',body='')
        self.assertEqual(e.exception.code,'E_SIZE')
    def test_array_capacity_guard_remains(self):
        with self.assertRaises(TranslationError) as e:build('CONST count=later later=200',decl='a:ARRAY[count,count]OF INTEGER',body='')
        self.assertEqual(e.exception.code,'E_ARRAY_CAPACITY')


class ForwardConstantScopes(unittest.TestCase):
    def test_local_chain(self):self.assertEqual(run('',body='work',routines='ROUTINE work CONST first=later later=7 BEGIN n=first END work')['N'],7)
    def test_local_multiple_sections(self):self.assertEqual(run('',body='work',routines='ROUTINE work CONST first=later VAR unused:INTEGER CONST later=7 BEGIN n=first END work')['N'],7)
    def test_local_depends_on_global_chain(self):self.assertEqual(run(body='work',routines='ROUTINE work CONST local=later_local later_local=first BEGIN n=local END work')['N'],7)
    def test_siblings_keep_independent_names(self):
        v=run('',body='one two',routines='ROUTINE one CONST first=later later=7 BEGIN n=first END one ROUTINE two CONST first=later later=8 BEGIN m=first END two');self.assertEqual((v['N'],v['M']),(7,8))
    def test_value_argument_cannot_mutate_constant(self):self.assertEqual(run('',body='work',routines='ROUTINE change(p:INTEGER) BEGIN p=9 END change ROUTINE work CONST first=later later=7 BEGIN change(first) n=first END work')['N'],7)
    def test_string_argument_owns_private_storage(self):self.assertEqual(run('',body='work',routines="ROUTINE change(p:STRING) BEGIN p='changed' END change ROUTINE work CONST first=later later='abc' BEGIN change(first) text=first END work")['TEXT'],'abc')
    def test_recursion_keeps_resolved_local_constant(self):self.assertEqual(run('',body='n=factorial(5)',routines='ROUTINE factorial(p:INTEGER):INTEGER CONST one=later later=1 BEGIN IF p=0 THEN RETURN one ENDIF RETURN p*factorial((p-one)) END factorial')['N'],120)
    def test_caller_constants_do_not_leak(self):
        with self.assertRaises(TranslationError) as e:build('',body='parent',routines='ROUTINE child CONST first=later BEGIN END child ROUTINE parent CONST later=7 BEGIN child END parent')
        self.assertEqual(e.exception.code,'E_CONSTANT')
    def test_constant_cannot_escape_routine(self):
        with self.assertRaises(TranslationError) as e:build('',body='n=first',routines='ROUTINE work CONST first=later later=7 BEGIN END work')
        self.assertEqual(e.exception.code,'E_SYMBOL')
    def test_constants_are_not_saved_variables(self):
        p,_=build();p.run();self.assertNotIn('FIRST',p.snapshot());self.assertFalse(any(row['path']=='FIRST' for row in p._state.execution.to_config()['variables']))
    def test_using_fields_keep_lexical_priority(self):self.assertEqual(run('TYPE item_t=STRUCTURE count:INTEGER ENDSTRUCTURE',body='work',routines='ROUTINE work CONST count=later later=7 VAR item:item_t BEGIN item.count=3 USING item DO n=count ENDUSING m=count END work')['N'],3)
    def test_forward_case_and_for_bound(self):self.assertEqual(run('CONST first=later later=3',body='n=0 FOR m=1 TO first DO n=n+m ENDFOR SELECT n OF CASE(first*2): n=7 ENDSELECT')['N'],7)


class ForwardConstantGuards(unittest.TestCase):
    def reject(self,prefix,code='E_CONSTANT',**options):
        with self.assertRaises(TranslationError) as e:build(prefix,body='',**options)
        self.assertEqual(e.exception.code,code);return e.exception
    def test_self_cycle(self):self.assertIn('FIRST -> FIRST',str(self.reject('CONST first=first')))
    def test_mutual_cycle(self):self.assertIn('FIRST -> LATER -> FIRST',str(self.reject('CONST first=later later=first')))
    def test_long_cycle_message_is_bounded(self):
        error=self.reject('CONST '+' '.join(f'c{i}=c{i+1}' for i in range(80))+' c80=c0');self.assertIn('...',str(error));self.assertLess(len(str(error)),500)
    def test_unknown(self):self.assertIn('MISSING',str(self.reject('CONST first=missing')))
    def test_unused_invalid_chain(self):self.reject('CONST first=7 unused=missing')
    def test_unused_cycle(self):self.reject('CONST first=7 a=b b=a')
    def test_builtin_call_rejected(self):self.reject('CONST first=SQRT(4.0)')
    def test_user_call_rejected(self):self.reject('CONST first=answer()',routines='ROUTINE answer:INTEGER BEGIN RETURN 7 END answer')
    def test_variable_read_rejected(self):self.reject('CONST first=n')
    def test_index_read_rejected(self):self.reject('CONST first=items[1]',decl='items:ARRAY[1]OF INTEGER')
    def test_duplicate(self):self.reject('CONST first=7 first=8','E_DUPLICATE')
    def test_global_variable_collision(self):self.reject('CONST n=later later=7','E_DUPLICATE')
    def test_local_parameter_collision(self):self.reject('',routines='ROUTINE work(p:INTEGER) CONST first=p p=7 BEGIN END work',code='E_DUPLICATE')
    def test_local_variable_collision(self):self.reject('',routines='ROUTINE work VAR first:INTEGER CONST first=later later=7 BEGIN END work',code='E_DUPLICATE')
    def test_local_global_shadow(self):self.reject('',routines='ROUTINE work CONST n=later later=7 BEGIN END work',code='E_LOCAL_CONST_SHADOW')
    def test_divide_by_zero(self):self.reject('CONST first=1 DIV later later=0')
    def test_overflow(self):self.reject('CONST first=later+1 later=MAXINT')
    def test_minimum_literal(self):self.reject('CONST first=later later=-2147483648','E_MININT_LITERAL')
    def test_boolean_arithmetic(self):self.reject('CONST first=later+1 later=ON')
    def test_constant_output_is_still_rejected(self):
        with self.assertRaises(TranslationError) as e:build(body="CNV_STR_INT('9',first)")
        self.assertEqual(e.exception.code,'E_OUTPUT_ARGUMENT')
    def test_legacy_global_order_retained(self):self.reject('CONST first=later later=7',translator=legacy_translate)
    def test_legacy_local_order_retained(self):self.reject('',routines='ROUTINE work CONST first=later later=7 BEGIN END work',translator=legacy_translate)


class ForwardConstantMetadata(unittest.TestCase):
    def test_global_source_order(self):self.assertEqual([row['name'] for row in build()[1].report['global_constants']],['FIRST','LATER'])
    def test_dependency_order(self):self.assertEqual([row['name'] for row in build()[1].report['constant_resolution_order']],['LATER','FIRST'])
    def test_forward_edge(self):
        row=build()[1].report['constant_dependencies'][0];self.assertEqual((row['name'],row['dependency'],row['scope'],row['forward']),('FIRST','LATER','module',True))
    def test_backward_edge(self):self.assertFalse(build('CONST later=7 first=later')[1].report['constant_dependencies'][0]['forward'])
    def test_local_source_order(self):self.assertEqual([row['name'] for row in build('',body='work',routines='ROUTINE work CONST first=later later=7 BEGIN n=first END work')[1].report['local_constants']['WORK']],['FIRST','LATER'])
    def test_lexical_dependency_scope(self):
        row=build(body='work',routines='ROUTINE work CONST local=first BEGIN n=local END work')[1].report['constant_dependencies'][-1];self.assertEqual((row['scope'],row['routine'],row['dependency_scope']),('routine','WORK','module'))
    def test_guide_and_offline_policy(self):
        policy=build()[1].report['forward_constant_policy'];self.assertEqual(policy['guide'],'docs/forward-constants.md');self.assertFalse(policy['controller_validated'])
    def test_include_dependency_origin(self):
        result=translate("PROGRAM T\n%INCLUDE defs\nVAR n:INTEGER BEGIN n=first END T",filename='main.kl',includes={'defs':'CONST first=later\n later=7'})
        row=result.report['constant_dependencies'][0];self.assertEqual((row['source_file'],row['source_line'],row['source_column']),('defs',1,13))
    def test_include_cycle_origin(self):
        with self.assertRaises(TranslationError) as e:translate("PROGRAM T\n%INCLUDE defs\nBEGIN END T",filename='main.kl',includes={'defs':'CONST first=later\n later=first'})
        self.assertEqual((e.exception.filename,e.exception.token.line),('defs',2))
    def test_linked_modules_keep_local_constant_graphs(self):
        main='PROGRAM MAIN CONST first=later later=7 VAR n:INTEGER ROUTINE work(x:INTEGER) FROM LIB BEGIN n=first work(n) END MAIN'
        lib='PROGRAM LIB CONST first=later later=1 ROUTINE work(x:INTEGER) CONST step=next_step next_step=first BEGIN x=x+step END work BEGIN END LIB'
        project=translate_project({'main':main,'lib':lib}).instantiate();self.assertEqual(project.run('MAIN')['MAIN']['values']['N'],8)

    def test_routine_dependency_on_later_module_constant(self):
        result=translate('PROGRAM T ROUTINE work CONST local=later BEGIN END work CONST later=7 BEGIN END T')
        row=result.report['constant_dependencies'][0];self.assertEqual((row['dependency_scope'],row['forward']),('module',True))
    def test_global_constant_after_routine_defines_interface(self):
        result=translate('PROGRAM T ROUTINE work:STRING[width] BEGIN RETURN \'abcdef\' END work CONST width=next_width next_width=3 VAR output:STRING[8] BEGIN output=work END T')
        ns={};exec(result.python_source,ns);self.assertEqual(ns['Program']().run()['OUTPUT'],'abc')
    def test_local_resolution_order_is_independent_of_global_order(self):
        _,result=build(body='work',routines='ROUTINE work CONST step=next_step next_step=first BEGIN n=step END work')
        self.assertEqual([(row['scope'],row['name']) for row in result.report['constant_resolution_order']],[('module','LATER'),('module','FIRST'),('routine','NEXT_STEP'),('routine','STEP')])
    def test_long_local_chain_is_iterative(self):
        constants=' '.join(f'c{i}=c{i+1}' for i in range(1100))+' c1100=7'
        self.assertEqual(run('',body='work',routines='ROUTINE work CONST '+constants+' BEGIN n=c0 END work')['N'],7)
    def test_unused_invalid_local_still_fails(self):
        with self.assertRaises(TranslationError) as e:build('',body='',routines='ROUTINE work CONST first=later later=1 DIV 0 BEGIN END work')
        self.assertEqual(e.exception.code,'E_CONSTANT')
    def test_global_constants_do_not_inherit_routine_values(self):
        with self.assertRaises(TranslationError) as e:build('CONST first=later',routines='ROUTINE work CONST later=7 BEGIN END work')
        self.assertEqual(e.exception.code,'E_CONSTANT')
    def test_boolean_operators_validate_unvisited_dependency(self):
        with self.assertRaises(TranslationError) as e:build('CONST first=OFF AND later later=missing')
        self.assertEqual(e.exception.code,'E_CONSTANT')
    def test_legacy_local_var_cannot_precede_its_size(self):
        with self.assertRaises(TranslationError) as e:build('',body='',routines='ROUTINE work VAR a:ARRAY[count]OF INTEGER CONST count=2 BEGIN END work',translator=legacy_translate)
        self.assertEqual(e.exception.code,'E_CONSTANT')
