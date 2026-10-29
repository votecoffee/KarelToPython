"""Authored Cartesian routine conversions, private storage and boundary guards."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt, translate_project
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_extended_services import compile_program
from tests.test_frame_transforms import CONFIG, quaternion, rotate, runtime_pose
from tests.test_position_conversions import runtime_position
from tests.test_project_scheduler import source


KINDS = ('POSITION', 'XYZWPR', 'XYZWPREXT')
PAIRS = tuple((a, b) for a in KINDS for b in KINDS if a != b)
MISSING = {'uninitialized': True}
LOCATION = (1., 2., 3.)
ANGLES = (15., 25., 35.)


def value(kind, location=LOCATION, angles=ANGLES, axes=(7., 8., 9.)):
    if kind == 'POSITION': return runtime_position(angles, location)
    pose = runtime_pose((*location, *angles))
    if kind == 'XYZWPR': return pose
    result = rt.Structure(('XYZWPREXT',))
    result.values.update(pose.values)
    result.values.update(zip(('EXT1', 'EXT2', 'EXT3'), axes))
    return result


def x(kind, name='v'):
    return name + ('.location.x' if kind == 'POSITION' else '.x')


def snapshot_x(snapshot, kind):
    return snapshot['LOCATION']['X'] if kind == 'POSITION' else snapshot['X']


def program(body='', *, source_kind='XYZWPR', target_kind='POSITION', routines='', decl=None, **options):
    decl = decl or f'a:{source_kind} q:{target_kind} n,total,entry,status:INTEGER seen:REAL trace:STRING[32]'
    p, report = compile_program(body, decl=decl, routines=routines, **options)
    if 'A' in p._state.values: p._state.values['A'] = value(source_kind)
    if 'Q' in p._state.values: p._state.values['Q'] = value(target_kind, (70., 80., 90.))
    return p, report


class CartesianAssertions(unittest.TestCase):
    def assert_pose(self, actual, kind, location=LOCATION, angles=ANGLES, axes=(0., 0., 0.)):
        coords = actual['LOCATION'] if kind == 'POSITION' else actual
        for axis, expected in zip(('X', 'Y', 'Z'), location): self.assertAlmostEqual(coords[axis], expected, places=11)
        expected_q = quaternion(angles)
        if kind == 'POSITION':
            for name, basis in zip(('NORMAL', 'ORIENT', 'APPROACH'), ((1, 0, 0), (0, 1, 0), (0, 0, 1))):
                for axis, expected in zip(('X', 'Y', 'Z'), rotate(expected_q, basis)):
                    self.assertAlmostEqual(actual[name][axis], expected, places=11)
        else:
            actual_q = quaternion(tuple(actual[field] for field in ('W', 'P', 'R')))
            self.assertAlmostEqual(abs(sum(a*b for a, b in zip(actual_q, expected_q))), 1., places=11)
        self.assertEqual(actual['CONFIG_DATA'], CONFIG)
        if kind == 'XYZWPREXT': self.assertEqual(tuple(actual[field] for field in ('EXT1', 'EXT2', 'EXT3')), axes)


class CartesianArgumentTests(CartesianAssertions):
    def test_all_six_bare_conversions_are_private_writable_values(self):
        for source_kind, target_kind in PAIRS:
            with self.subTest(source=source_kind, target=target_kind):
                p, _ = program('q=change(a)', source_kind=source_kind, target_kind=target_kind,
                    routines=f'ROUTINE change(v:{target_kind}):{target_kind} BEGIN {x(target_kind)}=99 RETURN v END change')
                original = deepcopy(p.snapshot()['A']); state = p.run()
                self.assertEqual(state['A'], original)
                self.assert_pose(state['Q'], target_kind, (99., 2., 3.))

    def test_all_six_grouped_conversions_are_private(self):
        for source_kind, target_kind in PAIRS:
            with self.subTest(source=source_kind, target=target_kind):
                p, _ = program('q=change((a))', source_kind=source_kind, target_kind=target_kind,
                    routines=f'ROUTINE change(v:{target_kind}):{target_kind} BEGIN {x(target_kind)}=99 RETURN v END change')
                before = p.snapshot()['A']; state = p.run()
                self.assertEqual(state['A'], before); self.assertEqual(snapshot_x(state['Q'], target_kind), 99.)

    def test_same_type_bare_references_keep_aliasing(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                p, _ = program('change(a)', source_kind=kind, target_kind=kind,
                    routines=f'ROUTINE change(v:{kind}) BEGIN {x(kind)}=99 END change')
                self.assertEqual(snapshot_x(p.run()['A'], kind), 99.)

    def test_same_type_grouped_values_stay_private(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                p, _ = program('change((a))', source_kind=kind, target_kind=kind,
                    routines=f'ROUTINE change(v:{kind}) BEGIN {x(kind)}=99 END change')
                before = p.snapshot()['A']; self.assertEqual(p.run()['A'], before)

    def test_each_repeated_converted_argument_owns_its_cell(self):
        p, _ = program('work(a,a)', routines='ROUTINE work(v,w:POSITION) BEGIN v.location.x=99 seen=w.location.x END work')
        state = p.run(); self.assertEqual((state['SEEN'], state['A']['X']), (1., 1.))

    def test_converted_configuration_is_not_shared_with_source(self):
        p, _ = program('q=work(a)', routines='ROUTINE work(v:POSITION):POSITION BEGIN v.config_data.cfg_left=FALSE RETURN v END work')
        state = p.run()
        self.assertTrue(state['A']['CONFIG_DATA']['CFG_LEFT']); self.assertFalse(state['Q']['CONFIG_DATA']['CFG_LEFT'])

    def test_converted_argument_capture_precedes_later_argument_mutation(self):
        p, _ = program('work(a,later())', routines='ROUTINE later:INTEGER BEGIN a.x=99 RETURN 0 END later '
            'ROUTINE work(v:POSITION; k:INTEGER) BEGIN seen=v.location.x END work')
        state = p.run(); self.assertEqual((state['SEEN'], state['A']['X']), (1., 99.))

    def test_converted_pose_and_explicit_source_field_reference_are_independent(self):
        p, _ = program('work(a,a.x)', routines='ROUTINE work(v:POSITION; scalar:REAL) BEGIN v.location.x=99 seen=v.location.x scalar=7 END work')
        state = p.run(); self.assertEqual((state['A']['X'], state['SEEN']), (7., 99.))

    def test_indexed_source_selector_runs_once(self):
        p, _ = program('n=0 work(items[pick()])', decl='items:ARRAY[1] OF XYZWPR a:XYZWPR q:POSITION n:INTEGER seen:REAL',
            routines='ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 1 END pick '
                     'ROUTINE work(v:POSITION) BEGIN seen=v.location.x v.location.x=99 END work')
        p._state.values['ITEMS'].values[0] = value('XYZWPR')
        state = p.run(); self.assertEqual((state['N'], state['SEEN'], state['ITEMS'][0]['X']), (1, 1., 1.))

    def test_function_argument_is_evaluated_once(self):
        p, _ = program('n=0 work(make())', routines='ROUTINE make:XYZWPR BEGIN n=n+1 RETURN a END make '
                     'ROUTINE work(v:POSITION) BEGIN v.location.x=99 END work')
        state = p.run(); self.assertEqual((state['N'], state['A']['X']), (1, 1.))

    def test_bare_function_argument_retains_single_evaluation(self):
        p, _ = program('n=0 work(make)', routines='ROUTINE make:XYZWPR BEGIN n=n+1 RETURN a END make '
                     'ROUTINE work(v:POSITION) BEGIN seen=v.location.x END work')
        state = p.run(); self.assertEqual((state['N'], state['SEEN']), (1, 1.))

    def test_transparent_cartesian_aliases_keep_conversion_rules(self):
        p, _ = program('q=work(a)', prefix='TYPE matrix=POSITION euler=XYZWPR',
            routines='ROUTINE work(v:matrix):matrix BEGIN RETURN v END work')
        self.assert_pose(p.run()['Q'], 'POSITION')

    def test_convert_then_forward_as_exact_reference_mutates_only_private_cell(self):
        p, _ = program('q=outer(a)', routines='ROUTINE inner(v:POSITION) BEGIN v.location.x=99 END inner '
            'ROUTINE outer(v:POSITION):POSITION BEGIN inner(v) RETURN v END outer')
        state = p.run(); self.assertEqual((state['A']['X'], state['Q']['LOCATION']['X']), (1., 99.))

    def test_pause_keeps_converted_cell_private_until_resume(self):
        p, _ = program('q=work(a)', cooperative=True,
            routines='ROUTINE work(v:POSITION):POSITION BEGIN v.location.x=99 PAUSE v.location.y=88 RETURN v END work')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual((p.snapshot()['A']['X'], p.snapshot()['Q']['LOCATION']['X']), (1., 70.))
        p.resume(); state = p.snapshot()
        self.assertEqual(state['A']['X'], 1.); self.assert_pose(state['Q'], 'POSITION', (99., 88., 3.))

    def test_stop_discards_converted_cell_without_copyback(self):
        p, _ = program('q=work(a)', cooperative=True,
            routines='ROUTINE work(v:POSITION):POSITION BEGIN v.location.x=99 PAUSE RETURN v END work')
        with self.assertRaises(rt.KarelPause): p.run()
        p.stop()
        self.assertEqual((p.snapshot()['A']['X'], p.snapshot()['Q']['LOCATION']['X'], p._state.local_frames), (1., 70., []))


class CartesianReturnTests(CartesianAssertions):
    def test_all_six_return_conversions_are_independent(self):
        for source_kind, target_kind in PAIRS:
            with self.subTest(source=source_kind, target=target_kind):
                p, _ = program(f'q=make() {x(source_kind, "a")}=99', source_kind=source_kind, target_kind=target_kind,
                    routines=f'ROUTINE make:{target_kind} BEGIN RETURN a END make')
                state = p.run(); self.assert_pose(state['Q'], target_kind)
                self.assertEqual(snapshot_x(state['A'], source_kind), 99.)

    def test_local_return_is_converted_before_frame_cleanup(self):
        p, _ = program('q=make()', routines='ROUTINE make:POSITION VAR local:XYZWPR BEGIN local=a RETURN local END make')
        self.assert_pose(p.run()['Q'], 'POSITION'); self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_forwarded_return_can_convert_through_all_three_types(self):
        p, _ = program('q=outer()', target_kind='XYZWPREXT', routines='ROUTINE first:XYZWPR BEGIN RETURN a END first '
            'ROUTINE middle:POSITION BEGIN RETURN first() END middle ROUTINE outer:XYZWPREXT BEGIN RETURN middle() END outer')
        self.assert_pose(p.run()['Q'], 'XYZWPREXT')

    def test_converted_formal_may_return_as_another_cartesian_type(self):
        p, _ = program('q=work(a)', target_kind='XYZWPREXT', routines='ROUTINE work(v:POSITION):XYZWPREXT BEGIN v.location.x=9 RETURN v END work')
        state = p.run(); self.assert_pose(state['Q'], 'XYZWPREXT', (9., 2., 3.)); self.assertEqual(state['A']['X'], 1.)

    def test_bare_function_return_forwarding_retains_declared_conversion(self):
        p, _ = program('q=outer', routines='ROUTINE first:XYZWPR BEGIN RETURN a END first '
            'ROUTINE outer:POSITION BEGIN RETURN first END outer')
        self.assert_pose(p.run()['Q'], 'POSITION')

    def test_return_failure_preserves_destination_and_prior_effects(self):
        for source_kind, target_kind in PAIRS:
            with self.subTest(source=source_kind, target=target_kind):
                p, _ = program('n=0 q=make()', source_kind=source_kind, target_kind=target_kind,
                    routines=f'ROUTINE make:{target_kind} BEGIN n=1 RETURN a END make')
                p._state.values['A'].values['CONFIG_DATA'].values['CFG_TURN_NO1'] = 8
                before = p.snapshot()['Q']
                with self.assertRaisesRegex(rt.KarelRuntimeError, '-8..7'): p.run()
                self.assertEqual((p.snapshot()['Q'], p.snapshot()['N'], p._state.local_frames, p._state.call_depth), (before, 1, [], 0))

    def test_bad_return_conversion_skips_destination_index(self):
        p, _ = program('n=0 items[pick()]=make()', decl='a:XYZWPR q:POSITION n:INTEGER items:ARRAY[1] OF POSITION',
            routines='ROUTINE make:POSITION BEGIN RETURN a END make ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 1 END pick')
        p._state.values['A'].values['W'] = rt.UNINITIALIZED
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): p.run()
        self.assertEqual((p.snapshot()['N'], p._state.local_frames), (0, []))

    def test_successful_return_snapshot_precedes_destination_index_mutation(self):
        p, _ = program('items[pick()]=make()', decl='a:XYZWPR q:POSITION items:ARRAY[1] OF POSITION',
            routines='ROUTINE make:POSITION BEGIN RETURN a END make ROUTINE pick:INTEGER BEGIN a.x=99 RETURN 1 END pick')
        state = p.run(); self.assertEqual((state['ITEMS'][0]['LOCATION']['X'], state['A']['X']), (1., 99.))

    def test_converted_position_result_retains_readonly_orientation_children(self):
        p, _ = program('q=make()', routines='ROUTINE make:POSITION BEGIN RETURN a END make')
        p.run()
        for field in rt.POSITION_READ_ONLY_FIELDS:
            child = p._state.values['Q'].values[field]
            self.assertTrue(child.read_only)
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'read-only'): rt.field_reference(child, 'X').set(9.)

    def test_recursion_converts_at_each_declared_return_boundary(self):
        p, _ = program('q=recurse(3)', routines='ROUTINE recurse(k:INTEGER):POSITION VAR local:XYZWPR BEGIN '
            'IF k=0 THEN RETURN a ENDIF local=recurse(k-1) local.x=local.x+k RETURN local END recurse')
        state = p.run(); self.assert_pose(state['Q'], 'POSITION', (7., 2., 3.)); self.assertEqual(p._state.call_depth, 0)


class CartesianValidationTests(CartesianAssertions):
    def test_partial_source_conversion_fails_before_callee_and_later_arguments(self):
        for source_kind, target_kind in PAIRS:
            with self.subTest(source=source_kind, target=target_kind):
                p, _ = program('n=0 work(a,later())', source_kind=source_kind, target_kind=target_kind,
                    routines='ROUTINE later:INTEGER BEGIN n=1 RETURN 0 END later '
                             f'ROUTINE work(v:{target_kind}; k:INTEGER) BEGIN n=2 END work')
                p._state.values['A'].values['CONFIG_DATA'].values['CFG_FLIP'] = rt.UNINITIALIZED
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): p.run()
                self.assertEqual((p.snapshot()['N'], p._state.local_frames, p._state.call_depth), (0, [], 0))

    def test_partial_external_axes_fail_even_when_target_discards_axes(self):
        for target_kind in ('POSITION', 'XYZWPR'):
            with self.subTest(target=target_kind):
                p, _ = program('work(a)', source_kind='XYZWPREXT', target_kind=target_kind,
                    routines=f'ROUTINE work(v:{target_kind}) BEGIN END work')
                p._state.values['A'].values['EXT2'] = rt.UNINITIALIZED
                with self.assertRaisesRegex(rt.KarelRuntimeError, 'uninitialized'): p.run()

    def test_improper_position_matrix_rejected_before_callee(self):
        for edit, message in ((lambda a: a.values['NORMAL'].values.update(X=2.), 'unit'),
                              (lambda a: a.values['NORMAL'].values.update(X=-1.), 'right-handed')):
            p, _ = program('n=0 work(a)', source_kind='POSITION', target_kind='XYZWPR',
                           routines='ROUTINE work(v:XYZWPR) BEGIN n=1 END work')
            p._state.values['A'] = value('POSITION', angles=(0., 0., 0.)); edit(p._state.values['A'])
            with self.assertRaisesRegex(rt.KarelRuntimeError, message): p.run()
            self.assertEqual(p.snapshot()['N'], 0)

    def test_nonfinite_and_malformed_source_fields_reject(self):
        for edit in (lambda a: a.values.update(X=float('nan')), lambda a: a.values.pop('R'),
                     lambda a: a.values['CONFIG_DATA'].values.update(CFG_LEFT=1)):
            p, _ = program('n=0 work(a)', routines='ROUTINE work(v:POSITION) BEGIN n=1 END work')
            edit(p._state.values['A'])
            with self.assertRaises(rt.KarelRuntimeError): p.run()
            self.assertEqual((p.snapshot()['N'], p._state.local_frames), (0, []))

    def test_same_type_partial_data_copies_keep_existing_semantics(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                p, _ = program('q=echo((a))', source_kind=kind, target_kind=kind,
                               routines=f'ROUTINE echo(v:{kind}):{kind} BEGIN RETURN v END echo')
                p._state.values['A'].values['CONFIG_DATA'].values['CFG_FLIP'] = rt.UNINITIALIZED
                self.assertEqual(p.run()['Q']['CONFIG_DATA']['CFG_FLIP'], MISSING)

    def test_orientation_write_guard_applies_to_converted_position_formal(self):
        with self.assertRaises(TranslationError) as caught:
            program('work(a)', routines='ROUTINE work(v:POSITION) BEGIN v.normal.x=9 END work')
        self.assertEqual(caught.exception.code, 'E_POSITION_READ_ONLY')

    def test_conversions_do_not_require_or_invoke_robot_models(self):
        robot = rt.RobotContext(forward=lambda *args: self.fail('Unexpected forward model'),
                               inverse=lambda *args: self.fail('Unexpected inverse model'))
        p, _ = program('q=echo(a)', context=rt.ExecutionContext(robot=robot),
                       routines='ROUTINE echo(v:POSITION):POSITION BEGIN RETURN v END echo')
        self.assert_pose(p.run()['Q'], 'POSITION')

    def test_runtime_private_cells_convert_only_in_pythonic_mode(self):
        for source_kind, target_kind in PAIRS:
            with self.subTest(source=source_kind, target=target_kind):
                original = value(source_kind)
                with rt._numeric_scope('pythonic'):
                    reference = rt.value_argument((target_kind,), original, 17)
                    self.assertEqual(reference.spec, (target_kind,))
                    self.assert_pose(rt.snapshot_value(reference.raw()), target_kind)
                with rt._numeric_scope('strict'), self.assertRaises(rt.KarelRuntimeError):
                    rt.value_argument((target_kind,), original, 17)

    def test_canonical_euler_and_added_or_discarded_axes_follow_assignment_policy(self):
        p, _ = program('q=echo(a)', target_kind='XYZWPREXT', routines='ROUTINE echo(v:XYZWPREXT):XYZWPREXT BEGIN RETURN v END echo')
        p._state.values['A'] = value('XYZWPR', angles=(0., 0., 450.))
        state = p.run(); self.assertEqual((state['Q']['R'], state['Q']['EXT1'], state['Q']['EXT2'], state['Q']['EXT3']), (90., 0., 0., 0.))


class CartesianExternalAndPersistenceTests(CartesianAssertions):
    def test_all_six_linked_call_arguments_convert_before_exact_interface(self):
        for source_kind, target_kind in PAIRS:
            with self.subTest(source=source_kind, target=target_kind):
                project = translate_project({
                    'lib': source('LIB', '', decl='n:INTEGER', routines=f'ROUTINE echo(v:{target_kind}):{target_kind} BEGIN {x(target_kind)}=9 RETURN v END echo'),
                    'main': source('MAIN', 'q=echo(a)', decl=f'a:{source_kind} q:{target_kind}', routines=f'ROUTINE echo(v:{target_kind}):{target_kind} FROM LIB')})
                instance = project.instantiate(); main = instance.programs['MAIN']; main._state.values['A'] = value(source_kind)
                instance.run('MAIN'); state = main.snapshot()
                self.assert_pose(state['Q'], target_kind, (9., 2., 3.)); self.assertEqual(snapshot_x(state['A'], source_kind), 1.)

    def test_mismatched_linked_declared_interfaces_still_reject(self):
        project = translate_project({'lib': source('LIB', '', routines='ROUTINE work(v:XYZWPR) BEGIN END work'),
                                     'main': source('MAIN', '', routines='ROUTINE work(v:POSITION) FROM LIB')})
        with self.assertRaises(ValueError): project.instantiate()

    def test_callback_receives_declared_private_reference_for_converted_actual(self):
        captured = []
        def adapter(reference):
            captured.append(reference)
            self.assertEqual(reference.spec, ('POSITION',))
            rt.field_reference(reference.raw().values['LOCATION'], 'X').set(9.)
        p, _ = program('work(a)', routines='ROUTINE work(v:POSITION) FROM LIB',
                       context=rt.ExecutionContext(externals={('LIB', 'WORK'): adapter}))
        state = p.run(); self.assertEqual((len(captured), state['A']['X'], captured[0].raw().values['LOCATION'].values['X']), (1, 1., 9.))

    def test_callback_matching_bare_reference_still_mutates_caller(self):
        def adapter(reference): rt.field_reference(reference.raw().values['LOCATION'], 'X').set(9.)
        p, _ = program('work(a)', source_kind='POSITION', routines='ROUTINE work(v:POSITION) FROM LIB',
                       context=rt.ExecutionContext(externals={('LIB', 'WORK'): adapter}))
        self.assertEqual(p.run()['A']['LOCATION']['X'], 9.)

    def test_callback_failure_does_not_copy_converted_writes_back(self):
        def adapter(reference):
            rt.field_reference(reference.raw().values['LOCATION'], 'X').set(99.)
            raise ValueError('Authored callback failure')
        p, _ = program('work(a)', routines='ROUTINE work(v:POSITION) FROM LIB',
                       context=rt.ExecutionContext(externals={('LIB', 'WORK'): adapter}))
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'Authored callback failure'): p.run()
        self.assertEqual((p.snapshot()['A']['X'], p._state.local_frames, p._state.call_depth), (1., [], 0))

    def test_declared_callback_return_can_be_converted_by_outer_return(self):
        returned = value('XYZWPR')
        p, _ = program('q=outer()', routines='ROUTINE adapter:XYZWPR FROM LIB ROUTINE outer:POSITION BEGIN RETURN adapter() END outer',
                       context=rt.ExecutionContext(externals={('LIB', 'ADAPTER'): lambda: returned}))
        state = p.run(); self.assert_pose(state['Q'], 'POSITION')
        returned.values['X'] = 99.; self.assertEqual(p.snapshot()['Q']['LOCATION']['X'], 1.)

    def test_raw_callback_result_must_match_its_declared_return_type(self):
        p, _ = program('q=adapter()', routines='ROUTINE adapter:POSITION FROM LIB',
                       context=rt.ExecutionContext(externals={('LIB', 'ADAPTER'): lambda: value('XYZWPR')}))
        before = p.snapshot()['Q']
        with self.assertRaises(rt.KarelRuntimeError): p.run()
        self.assertEqual((p.snapshot()['Q'], p._state.local_frames, p._state.call_depth), (before, [], 0))

    def test_context_json_retains_converted_type_and_orientation_protection(self):
        p, result = program('q=make()', routines='ROUTINE make:POSITION BEGIN RETURN a END make')
        expected = p.run(); saved = json.loads(json.dumps(p._state.execution.to_config()))
        ns = {'__name__': 'cartesian_restored'}; exec(result.python_source, ns)
        restored = ns['Program'](context=rt.ExecutionContext.from_config(saved))
        self.assertEqual(restored.snapshot(), expected)
        self.assertTrue(restored._state.values['Q'].values['NORMAL'].read_only)

    def test_report_json_distinguishes_original_source_and_target_specs(self):
        _, result = program('q=echo(a) exact((a)) q=make()', routines='ROUTINE echo(v:POSITION):POSITION BEGIN RETURN v END echo '
            'ROUTINE exact(v:XYZWPR) BEGIN END exact ROUTINE make:POSITION BEGIN RETURN a END make')
        report = json.loads(json.dumps(result.report))
        arguments = {row['routine']: row for row in report['positional_value_arguments']}
        self.assertEqual((arguments['ECHO']['source_type_spec'], arguments['ECHO']['type_spec'], arguments['ECHO']['converted']),
                         (['XYZWPR'], ['POSITION'], True))
        self.assertEqual((arguments['EXACT']['source_type_spec'], arguments['EXACT']['type_spec'], arguments['EXACT']['converted']),
                         (['XYZWPR'], ['XYZWPR'], False))
        returns = {row['routine']: row for row in report['positional_returns']}
        self.assertTrue(returns['MAKE']['converted']); self.assertFalse(returns['ECHO']['converted'])


class CartesianExactBoundaryTests(unittest.TestCase):
    def test_joint_interfaces_require_explicit_context_and_legacy_guard(self):
        for body, routines, decl in (
            ('work(a)', 'ROUTINE work(v:POSITION) BEGIN END work', 'a:JOINTPOS3'),
            ('work(a)', 'ROUTINE work(v:JOINTPOS3) BEGIN END work', 'a:POSITION'),
            ('', 'ROUTINE make:POSITION BEGIN RETURN a END make', 'a:JOINTPOS3'),
            ('', 'ROUTINE make:JOINTPOS3 BEGIN RETURN a END make', 'a:XYZWPR')):
            with self.subTest(body=body, routines=routines):
                p,_=compile_program(body, decl=decl, routines=routines)
                if body:
                    with self.assertRaisesRegex(rt.KarelRuntimeError,'robot'): p.run()
                with self.assertRaises(TranslationError): legacy_translate(f'PROGRAM T VAR {decl} {routines} BEGIN {body} END T')

    def test_config_vector_and_named_aggregate_interfaces_stay_exact(self):
        for kind in ('VECTOR', 'CONFIG', 'packet'):
            with self.subTest(kind=kind), self.assertRaises(TranslationError):
                compile_program('work(a)', decl=f'a:{kind}', prefix='TYPE packet=STRUCTURE pose:XYZWPR ENDSTRUCTURE',
                                routines='ROUTINE work(v:POSITION) BEGIN END work')

    def test_whole_arrays_do_not_convert_cartesian_leaf_types(self):
        with self.assertRaises(TranslationError):
            compile_program('work(a)', decl='a:ARRAY[1] OF XYZWPR', routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN END work')
        with self.assertRaises(TranslationError):
            compile_program('', decl='a:ARRAY[1] OF XYZWPR', routines='ROUTINE make:ARRAY OF POSITION BEGIN RETURN a END make')

    def test_byname_requires_exact_declared_cartesian_type(self):
        p, _ = program("entry=77 n=0 work(BYNAME('','A',entry))", routines='ROUTINE work(v:POSITION) BEGIN n=1 END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'type does not match'): p.run()
        self.assertEqual((p.snapshot()['ENTRY'], p.snapshot()['N']), (77, 0))

    def test_legacy_argument_and_return_conversion_guards_remain(self):
        for source_kind, target_kind in PAIRS:
            for body, routines in (('work(a)', f'ROUTINE work(v:{target_kind}) BEGIN END work'),
                                   ('', f'ROUTINE make:{target_kind} BEGIN RETURN a END make')):
                with self.subTest(source=source_kind, target=target_kind, body=body), self.assertRaises(TranslationError):
                    legacy_translate(f'PROGRAM T VAR a:{source_kind} {routines} BEGIN {body} END T')

    def test_global_counter_effects_are_not_hidden_by_private_pose_conversion(self):
        with self.assertRaises(TranslationError) as caught:
            program('FOR n=1 TO 2 DO work(a) ENDFOR', routines='ROUTINE work(v:POSITION) BEGIN n=7 END work')
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')

    def test_safe_formal_pose_writes_do_not_modify_integer_counter(self):
        p, _ = program('total=0 FOR n=1 TO 2 DO work(a) total=total+n ENDFOR',
                       routines='ROUTINE work(v:POSITION) BEGIN v.location.x=99 END work')
        state = p.run(); self.assertEqual((state['TOTAL'], state['A']['X'], state['N']), (3, 1., MISSING))


if __name__ == '__main__': unittest.main()
