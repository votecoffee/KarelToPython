"""Record/joint ARRAY results retain recursive ownership and exact storage rules."""
import ast
import json
import unittest

from karel2py import translate, runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate
from karel2py.lexer import TranslationError
from tests.test_structure_routines import initialized_host
from tests.test_data_records import init_config, init_pose


TYPES = '''TYPE row_t=ARRAY[2] OF INTEGER
item_t=STRUCTURE id: INTEGER label: STRING[3] samples: row_t
payload: ARRAY[2] OF BYTE direction: VECTOR ENDSTRUCTURE
other_t=STRUCTURE id: INTEGER label: STRING[3] samples: row_t
payload: ARRAY[2] OF BYTE direction: VECTOR ENDSTRUCTURE'''


def initialize(path='p[1]', number=1):
    return (f"{path}.id={number} {path}.label='abcde' {path}.samples[1]=7 "
            f'{path}.samples[2]=8 {path}.payload[1]=0 {path}.payload[2]=255 '
            f'{path}.direction.x=1 {path}.direction.y=2 {path}.direction.z=3')


def item(number=1):
    return dict(ID=number, LABEL='abc', SAMPLES=[7, 8], PAYLOAD=[0, 255],
                DIRECTION=dict(X=1., Y=2., Z=3.))


FACTORY = 'ROUTINE make: ARRAY OF item_t VAR p: ARRAY[1] OF item_t BEGIN ' + initialize() + ' RETURN p END make'
VECTOR_FACTORY = 'ROUTINE make: ARRAY OF VECTOR VAR p: ARRAY[1] OF VECTOR BEGIN p[1].x=1 p[1].y=2 p[1].z=3 RETURN p END make'


def compile_program(body='a=make()', *, declarations='a,b: ARRAY[1] OF item_t n: INTEGER',
                    routines=FACTORY, types=TYPES, shapes=None, _translator=translate, **context):
    result = _translator(f'PROGRAM T\n{types}\nVAR {declarations}\n{routines}\nBEGIN\n{body}\nEND T',
                       filename='aggregate_array_results.kl', array_shapes=shapes)
    ast.parse(result.python_source, feature_version=(3, 11))
    json.dumps(result.report)
    namespace = {'__name__': 'aggregate_array_result_test'}
    exec(result.python_source, namespace)
    return namespace['Program'](**context), result


def execute(*args, **kwargs):
    return compile_program(*args, **kwargs)[0].run()


class AggregateArrayReturnTests(unittest.TestCase):
    def test_local_nested_record_result(self):
        self.assertEqual(execute()['A'], [item()])

    def test_vector_factory_result(self):
        state = execute(types='', declarations='a: ARRAY[1] OF VECTOR', routines=VECTOR_FACTORY)
        self.assertEqual(state['A'], [dict(X=1., Y=2., Z=3.)])

    def test_global_result_is_deeply_independent(self):
        routine = 'ROUTINE get: ARRAY OF item_t BEGIN RETURN a END get'
        state = execute(initialize('a[1]') + ' b=get() a[1].samples[1]=99 a[1].direction.x=9 a[1].label=\'z\'', routines=routine)
        self.assertEqual(state['B'], [item()])

    def test_reference_formal_result_retains_concrete_length(self):
        routine = 'ROUTINE copy(p: ARRAY OF VECTOR): ARRAY OF VECTOR BEGIN RETURN p END copy'
        declarations = 'a,c: ARRAY[1] OF VECTOR b,d: ARRAY[2] OF VECTOR'
        body = 'a[1].x=1 a[1].y=2 a[1].z=3 b[1]=a[1] b[2]=a[1] c=copy(a) d=copy(b) a[1].x=9'
        state = execute(body, declarations=declarations, types='', routines=routine)
        self.assertEqual((state['C'], state['D']), ([dict(X=1.,Y=2.,Z=3.)], [dict(X=1.,Y=2.,Z=3.)]*2))

    def test_nested_named_array_identity_is_retained(self):
        program, result = compile_program()
        program.run()
        actual = program._state.raw('A').values[0]
        self.assertEqual(actual.values['SAMPLES'].spec[-1], 'ROW_T')
        self.assertEqual(actual.types['LABEL'], ('STRING',3))
        self.assertEqual(result.report['array_returns'][0]['element_spec'][1], 'ITEM_T')

    def test_grouped_storage_return(self):
        self.assertEqual(execute(routines=FACTORY.replace('RETURN p', 'RETURN ((p))'))['A'], [item()])

    def test_array_field_source_and_destination(self):
        types = TYPES + '\nbox_t=STRUCTURE values: ARRAY[1] OF item_t ENDSTRUCTURE'
        routine = 'ROUTINE get: ARRAY OF item_t BEGIN RETURN first.values END get'
        state = execute(initialize('first.values[1]') + ' second.values=get() first.values[1].samples[1]=99',
                        declarations='first,second: box_t', types=types, routines=routine)
        self.assertEqual(state['SECOND']['VALUES'], [item()])

    def test_captured_nested_field_survives_destination_replacement(self):
        routines = FACTORY + '\nROUTINE replace(p: ARRAY OF item_t; captured: INTEGER) BEGIN p=make() captured=99 END replace'
        state = execute('replace(a,a[1].samples[2])', routines=routines)
        expected = item(); expected['SAMPLES'][1] = 99
        self.assertEqual(state['A'], [expected])

    def test_staged_record_element_can_pass_as_independent_value(self):
        routines = FACTORY + '\nROUTINE touch(p: item_t) BEGIN p.samples[1]=99 n=p.samples[1] END touch'
        state = execute('a=make() touch((a[1]))', routines=routines)
        self.assertEqual((state['A'],state['N']), ([item()],99))

    def test_recursive_results_are_staged_before_return(self):
        routines = FACTORY + '\nROUTINE recurse(k: INTEGER): ARRAY OF item_t VAR p: ARRAY[1] OF item_t BEGIN IF k=0 THEN p=make() ELSE p=recurse(k-1) p[1].id=p[1].id+1 ENDIF RETURN p END recurse'
        program,_ = compile_program('a=recurse(4)', routines=routines)
        self.assertEqual(program.run()['A'], [item(5)])
        self.assertEqual((program._state.call_depth,program._state.local_frames), (0,[]))

    def test_global_shape_context_results_are_concrete(self):
        self.assertEqual(execute(declarations='a: ARRAY[*] OF item_t', shapes={'a':[1]})['A'], [item()])

    def test_config_array_checks_and_subfield_value_passing(self):
        routine = 'ROUTINE make: ARRAY OF CONFIG VAR p: ARRAY[1] OF CONFIG BEGIN ' + init_config('p[1]') + ' RETURN p END make'
        routine += '\nROUTINE touch(value: INTEGER) BEGIN value=7 END touch'
        state = execute('a=make() touch(a[1].cfg_turn_no1)', types='', declarations='a: ARRAY[1] OF CONFIG', routines=routine)
        self.assertEqual(state['A'][0]['CFG_TURN_NO1'], 0)

    def test_cartesian_array_factories(self):
        for kind in ('XYZWPR','XYZWPREXT'):
            with self.subTest(kind=kind):
                init = init_pose('p[1]')
                if kind == 'XYZWPREXT': init += ' p[1].ext1=4 p[1].ext2=5 p[1].ext3=6'
                routine = f'ROUTINE make: ARRAY OF {kind} VAR p: ARRAY[1] OF {kind} BEGIN {init} RETURN p END make'
                state = execute(types='', declarations=f'a: ARRAY[1] OF {kind}', routines=routine)
                self.assertEqual(state['A'][0]['X'],1.)
                if kind == 'XYZWPREXT': self.assertEqual(state['A'][0]['EXT3'],6.)

    def test_exact_joint_width_results_need_no_conversion_context(self):
        for spelling in ('JOINTPOS', *(f'JOINTPOS{n}' for n in range(1,10))):
            with self.subTest(spelling=spelling):
                routine = f'ROUTINE copy(p: ARRAY OF {spelling}): ARRAY OF {spelling} BEGIN RETURN p END copy'
                program,_ = compile_program('b=copy(a)', types='', declarations=f'a,b: ARRAY[1] OF {spelling}', routines=routine)
                source = program._state.raw('A')
                source.values[0] = initialized_host(source.spec[2])
                state = program.run()
                self.assertEqual(state['A'],state['B'])
                self.assertIsNot(source.values[0],program._state.raw('B').values[0])

    def test_position_array_fixture_retains_orientation_protection(self):
        routine = 'ROUTINE copy(p: ARRAY OF POSITION): ARRAY OF POSITION BEGIN RETURN p END copy'
        program,_ = compile_program('b=copy(a) a[1].location.x=9', types='', declarations='a,b: ARRAY[1] OF POSITION', routines=routine)
        source = program._state.raw('A')
        source.values[0] = initialized_host(('POSITION',))  # Synthetic host data, not acquired controller state.
        state = program.run()
        self.assertEqual(state['B'][0]['LOCATION']['X'],1.)
        target = program._state.raw('B').values[0]
        for field in rt.POSITION_READ_ONLY_FIELDS:
            self.assertTrue(target.values[field].read_only)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'):
                rt.field_reference(target.values[field],'X').set(9.)

    def test_report_carries_exact_nominal_element_spec(self):
        _, result = compile_program()
        row = result.report['array_returns'][0]
        self.assertEqual((row['element_type'],row['element_spec'][1]),('STRUCTURE','ITEM_T'))
        self.assertIn('32767 scalar leaves',result.report['aggregate_copy_policy']['limits'])
        self.assertIn('POSITION orientation protection',result.report['array_routine_policy']['aggregate_elements'])
        self.assertFalse(result.report['array_routine_policy']['controller_validated'])


class AggregateArrayRejectionTests(unittest.TestCase):
    def reject(self, code, **kwargs):
        with self.assertRaises(TranslationError) as caught: compile_program(**kwargs)
        self.assertEqual(caught.exception.code,code)

    def test_compatible_record_array_return_owns_declared_terminal(self):
        routine='ROUTINE make:ARRAY OF item_t VAR p:ARRAY[1]OF other_t BEGIN '+initialize()+' RETURN p END make'
        p,_=compile_program(routines=routine);self.assertEqual(p.run()['A'],[item()])
        self.assertEqual(p._state.values['A'].values[0].spec[1],'ITEM_T')

    def test_compatible_record_array_result_assignment_owns_receiver_terminal(self):
        p,_=compile_program(declarations='a:ARRAY[1]OF other_t');self.assertEqual(p.run()['A'],[item()])
        self.assertEqual(p._state.values['A'].values[0].spec[1],'OTHER_T')

    def test_unknown_element_type_rejected(self):
        self.reject('E_TYPE',routines='ROUTINE make: ARRAY OF missing_t BEGIN END make')

    def test_structure_element_must_precede_routine(self):
        with self.assertRaises(TranslationError) as caught:
            translate('PROGRAM T ROUTINE make: ARRAY OF later_t BEGIN END make TYPE later_t=STRUCTURE n: INTEGER ENDSTRUCTURE BEGIN END T')
        self.assertEqual(caught.exception.code,'E_TYPE')

    def test_named_array_result_type_remains_blocked(self):
        self.reject('E_RETURN_TYPE',routines='ROUTINE make: row_t BEGIN END make', _translator=legacy_translate)

    def test_fixed_and_wildcard_result_sizes_remain_blocked(self):
        for dimensions in ('[1]','[*]','[*,*]'):
            with self.subTest(dimensions=dimensions):
                self.reject('E_RETURN_TYPE',routines=f'ROUTINE make: ARRAY{dimensions} OF item_t BEGIN END make', _translator=legacy_translate)

    def test_group_qualified_result_elements_remain_blocked(self):
        for kind in ('VECTOR','XYZWPR','JOINTPOS3'):
            with self.subTest(kind=kind):
                self.reject('E_POSITION_GROUP',routines=f'ROUTINE make: ARRAY OF {kind} IN GROUP[1] BEGIN END make', _translator=legacy_translate)

    def test_multidimensional_record_source_remains_blocked(self):
        self.reject('E_RETURN',routines='ROUTINE make: ARRAY OF item_t VAR p: ARRAY[1,1] OF item_t BEGIN RETURN p END make')

    def test_named_joint_array_result_converts_width_privately(self):
        p,_=compile_program(types='TYPE row_t=ARRAY[1]OF JOINTPOS2',declarations='seed:row_t a:ARRAY[1]OF JOINTPOS3',routines='ROUTINE make:ARRAY OF JOINTPOS3 BEGIN RETURN seed END make')
        p._state.values['SEED'].values[0].values[:]=[1.,2.];self.assertEqual(p.run()['A'][0]['axes'],[1.,2.,0.])
        self.assertEqual(p.snapshot()['SEED'][0]['axes'],[1.,2.])

    def test_named_joint_array_destination_checks_discarded_axes(self):
        for last in (0.,1.):
            p,_=compile_program(types='TYPE row_t=ARRAY[1]OF JOINTPOS2',declarations='seed:ARRAY[1]OF JOINTPOS3 a:row_t',routines='ROUTINE make:ARRAY OF JOINTPOS3 BEGIN RETURN seed END make')
            p._state.values['SEED'].values[0].values[:]=[1.,2.,last]
            if last:
                with self.assertRaises(rt.KarelRuntimeError):p.run()
                self.assertIs(p._state.values['A'].values[0].values[0],rt.UNINITIALIZED)
            else:self.assertEqual(p.run()['A'][0]['axes'],[1.,2.])

    def test_array_results_still_require_direct_assignment(self):
        for body in ('a=(make())','use(make())','n=ARRAY_LEN(make())'):
            with self.subTest(body=body):
                self.reject('E_ARRAY_RESULT_CONTEXT',body=body,routines=FACTORY+'\nROUTINE use(p: ARRAY OF item_t) BEGIN END use', _translator=legacy_translate)

    def test_result_cannot_be_forwarded_directly_by_return(self):
        self.reject('E_ARRAY_RESULT_CONTEXT',routines=FACTORY+'\nROUTINE outer: ARRAY OF item_t BEGIN RETURN make() END outer', _translator=legacy_translate)

    def test_effectful_call_to_indexed_destination_remains_blocked(self):
        self.reject('E_EVALUATION_ORDER',body='boxes[1].values=make()',types=TYPES+'\nbox_t=STRUCTURE values: ARRAY[1] OF item_t ENDSTRUCTURE',declarations='boxes: ARRAY[1] OF box_t n: INTEGER',routines=FACTORY.replace('BEGIN p[1].id','BEGIN n=7 p[1].id'), _translator=legacy_translate)


class AggregateArrayFailureTests(unittest.TestCase):
    def assert_failure(self, program, message):
        before = program.snapshot()['A']
        with self.assertRaisesRegex(rt.KarelRuntimeError,message): program.run()
        self.assertEqual(program.snapshot()['A'],before)
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))

    def test_strict_unknown_nested_byte_preserves_destination_and_prior_effects(self):
        routine = FACTORY.replace('p[1].payload[2]=255','n=9')
        program,_ = compile_program(routines=routine, _translator=legacy_translate)
        self.assert_failure(program,'unknown')
        self.assertEqual(program.snapshot()['N'],9)

    def test_strict_uninitialized_nested_scalar_prevents_exposing_any_result(self):
        program,_ = compile_program(routines=FACTORY.replace('p[1].samples[2]=8','n=9'), _translator=legacy_translate)
        self.assert_failure(program,'uninitialized')

    def test_mismatched_length_retains_destination(self):
        program,_ = compile_program(declarations='a: ARRAY[2] OF item_t')
        self.assert_failure(program,'identical type and size')

    def test_generic_named_array_source_returns_owned_record_array(self):
        routine='ROUTINE copy(p:ARRAY OF item_t):ARRAY OF item_t BEGIN RETURN p END copy'
        program,_=compile_program(initialize('named[1]')+' a=copy(named)',types=TYPES+'\nitems_t=ARRAY[1]OF item_t',declarations='named:items_t a:ARRAY[1]OF item_t',routines=routine)
        self.assertEqual(program.run()['A'],[item()]);self.assertIsNot(program._state.raw('A').values[0],program._state.raw('NAMED').values[0])

    def test_named_outer_destination_identity_is_retained_on_copy(self):
        program,_=compile_program(types=TYPES+'\nitems_t=ARRAY[1]OF item_t',declarations='a:items_t')
        self.assertEqual(program.run()['A'],[item()]);self.assertEqual(program._state.raw('A').spec[3],'ITEMS_T')

    def test_strict_unknown_position_orientation_is_not_filled_in(self):
        routine = 'ROUTINE make: ARRAY OF POSITION BEGIN RETURN b END make'
        program,_ = compile_program(types='',declarations='a,b: ARRAY[1] OF POSITION',routines=routine, _translator=legacy_translate)
        self.assert_failure(program,'uninitialized')

    def test_strict_uninitialized_joint_axes_are_not_inferred(self):
        routine = 'ROUTINE make: ARRAY OF JOINTPOS3 VAR p: ARRAY[1] OF JOINTPOS3 BEGIN RETURN p END make'
        program,_ = compile_program(types='',declarations='a: ARRAY[1] OF JOINTPOS3',routines=routine, _translator=legacy_translate)
        self.assert_failure(program,'initialized')

    def test_abort_stays_distinct_and_unwinds_aggregate_frames(self):
        program,_ = compile_program(routines=FACTORY.replace('RETURN p','ABORT RETURN p'))
        with self.assertRaises(rt.KarelAbort): program.run()
        self.assertEqual((program._state.call_depth,program._state.local_frames),(0,[]))


class AggregateArrayRuntimeTests(unittest.TestCase):
    def source(self, spec):
        result = rt.Array(('ARRAY',1,spec))
        result.values[0] = initialized_host(spec)
        return result

    def test_all_builtin_record_types_copy_without_robot_defaults(self):
        for kind in rt.DATA_RECORD_TYPES:
            with self.subTest(kind=kind):
                source = self.source((kind,))
                copied = rt.array_result(('ARRAY',None,(kind,)),source,57)
                self.assertEqual(copied.snapshot(),source.snapshot())
                self.assertIsNot(copied.values[0],source.values[0])

    def test_record_layout_mismatch_is_rejected(self):
        source = self.source(('VECTOR',)); source.values[0].types = {'X':rt.REAL}
        with self.assertRaisesRegex(rt.KarelRuntimeError,'line 57'): rt.array_result(('ARRAY',None,('VECTOR',)),source,57)

    def test_invalid_real_leaf_is_rejected_before_source_changes(self):
        source = self.source(('VECTOR',)); source.values[0].values['Z'] = .1
        before = source.snapshot()
        with self.assertRaises(rt.KarelRuntimeError): rt.array_result(('ARRAY',None,('VECTOR',)),source,57)
        self.assertEqual(source.snapshot(),before)

    def test_config_range_is_rechecked_recursively(self):
        source = self.source(('XYZWPR',)); source.values[0].values['CONFIG_DATA'].values['CFG_TURN_NO1'] = 8
        with self.assertRaisesRegex(rt.KarelRuntimeError,'-8..7'): rt.array_result(('ARRAY',None,('XYZWPR',)),source,57)

    def test_nested_string_capacity_is_checked_without_truncating_corruption(self):
        spec = ('STRUCTURE','ITEM',(('LABEL',('STRING',3)),))
        source = self.source(spec); source.values[0].values['LABEL'] = 'abcd'
        with self.assertRaisesRegex(rt.KarelRuntimeError,'capacity'): rt.array_result(('ARRAY',None,spec),source,57)
        self.assertEqual(source.values[0].values['LABEL'],'abcd')

    def test_raw_short_marker_is_checked_inside_record_array(self):
        spec = ('STRUCTURE','ITEM',(('COUNT',rt.SHORT),))
        source = self.source(spec); source.values[0].values['COUNT'] = 32767
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'): rt.array_result(('ARRAY',None,spec),source,57)

    def test_joint_axis_count_and_scalar_type_are_checked(self):
        for values in ([1.,2.],[1.,2.,True],[1.,2.,.1]):
            with self.subTest(values=values):
                source = self.source(('JOINTPOS',3)); source.values[0].values[:] = values
                with self.assertRaises(rt.KarelRuntimeError): rt.array_result(('ARRAY',None,('JOINTPOS',3)),source,57)

    def test_aggregate_leaf_limit_precedes_copy(self):
        source = self.source(('VECTOR',)); source.spec = ('ARRAY',10923,('VECTOR',)); source.shape = (10923,)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'32767 scalar leaves'): rt.array_result(('ARRAY',None,('VECTOR',)),source,57)

    def test_bad_element_declarations_remain_explicit_errors(self):
        for element in ((),[],('STRING',3),('ARRAY',1,rt.INTEGER),('VECTOR',1),('JOINTPOS',True),('JOINTPOS',10),('STRUCTURE',)):
            with self.subTest(element=element):
                with self.assertRaises(rt.KarelRuntimeError): rt.array_result(('ARRAY',None,element),self.source(('VECTOR',)),57)


if __name__ == '__main__':
    unittest.main()
