"""Authored explicit-model routine conversions, ownership and failure evidence."""
from copy import deepcopy
import json
import unittest

from karel2py import runtime as rt, translate_project
from karel2py.kinematics import pose as identity_pose
from karel2py.lexer import TranslationError
from tests.legacy_numeric_support import translate as legacy_translate
from tests.test_cartesian_interfaces import value as cartesian_value, snapshot_x, x
from tests.test_extended_services import compile_program
from tests.test_joint_interoperability import joint, model_context
from tests.test_kinematic_assignments import callback_context
from tests.test_project_scheduler import source


CARTESIANS = (('p', 'POSITION'), ('a', 'XYZWPR'), ('e', 'XYZWPREXT'))
DECL = 'j,k,out:JOINTPOS p,q:POSITION a:XYZWPR e:XYZWPREXT n,total,entry,status:INTEGER seen:REAL trace:STRING[32]'
DEFAULT = object()
MISSING = {'uninitialized': True}


def program(body='', *, routines='', decl=DECL, context=DEFAULT, **options):
    ctx = model_context((0., 90.)) if context is DEFAULT else context
    p, result = compile_program(body, decl=decl, routines=routines, context=ctx, **options)
    for name in ('J', 'K', 'OUT'):
        if name not in p._state.values: continue
        width = p._state.types[name][1]
        values = ([0., 90.] + [0.] * 7)[:width] if name == 'J' else [7.] * width
        p._state.values[name] = joint(values)
    for name, kind in (*[(n.upper(), k) for n, k in CARTESIANS], ('Q', 'POSITION')):
        if name in p._state.values:
            p._state.values[name] = cartesian_value(kind, (100., 100., 0.) if name != 'Q' else (70., 80., 90.),
                                                  (0., 0., 90.), (0., 0., 0.))
    return p, result


def operations(p, name):
    return [row for row in p.service_requests if row['operation'] == name]


class KinematicArgumentTests(unittest.TestCase):
    def test_forward_to_each_cartesian_formal_is_private_and_writable(self):
        for target, kind in CARTESIANS:
            with self.subTest(kind=kind):
                p, _ = program(f'{target}=work(j)', routines=f'ROUTINE work(v:{kind}):{kind} BEGIN {x(kind)}=99 RETURN v END work')
                state = p.run()
                self.assertEqual((state['J']['axes'], snapshot_x(state[target.upper()], kind)), ([0., 90.] + [0.] * 7, 99.))
                self.assertEqual(len(operations(p, 'KINEMATIC_ARGUMENT')), 1)
                self.assertEqual(p._state.execution.robot.current.joints.values, [0., 90.])

    def test_inverse_from_each_cartesian_formal_is_private(self):
        for actual, kind in CARTESIANS:
            for width in (2, 9):
                with self.subTest(kind=kind, width=width):
                    decl = DECL.replace('j,k,out:JOINTPOS', f'j:JOINTPOS k,out:JOINTPOS{width}')
                    p, _ = program(f'out=work({actual})', decl=decl,
                        routines=f'ROUTINE work(v:JOINTPOS{width}):JOINTPOS{width} BEGIN v=k RETURN v END work')
                    before = p.snapshot()[actual.upper()]; state = p.run()
                    self.assertEqual((state['OUT']['axes'], state[actual.upper()]), ([7.] * width, before))
                    self.assertEqual(len(operations(p, 'KINEMATIC_ARGUMENT')), 1)

    def test_grouping_does_not_duplicate_model_conversion(self):
        for expression in ('j', '(j)'):
            with self.subTest(expression=expression):
                p, _ = program('work(' + expression + ')', routines='ROUTINE work(v:POSITION) BEGIN seen=v.location.x END work')
                self.assertAlmostEqual(p.run()['SEEN'], 100.); self.assertEqual(len(operations(p, 'KINEMATIC_ARGUMENT')), 1)

    def test_exact_joint_bare_formal_keeps_aliasing_without_model(self):
        p, _ = program('work(j)', context=None, routines='ROUTINE work(v:JOINTPOS) BEGIN v=k END work')
        state = p.run(); self.assertEqual(state['J']['axes'], [7.] * 9); self.assertEqual(p.service_requests, ())

    def test_exact_joint_grouped_formal_stays_private_without_model(self):
        p, _ = program('work((j))', context=None, routines='ROUTINE work(v:JOINTPOS) BEGIN v=k END work')
        state = p.run(); self.assertEqual(state['J']['axes'], [0., 90.] + [0.] * 7); self.assertEqual(p.service_requests, ())

    def test_source_function_and_model_each_run_once(self):
        p, _ = program('n=0 work(make())', routines='ROUTINE make:JOINTPOS BEGIN n=n+1 RETURN j END make '
            'ROUTINE work(v:POSITION) BEGIN seen=v.location.x END work')
        state = p.run(); self.assertEqual(state['N'], 1); self.assertEqual(len(operations(p, 'KINEMATIC_ARGUMENT')), 1)

    def test_conversion_capture_precedes_later_argument_source_mutation(self):
        p, _ = program('work(j,later())', routines='ROUTINE later:INTEGER BEGIN j=k RETURN 0 END later '
            'ROUTINE work(v:POSITION; scalar:INTEGER) BEGIN seen=v.location.x END work')
        state = p.run(); self.assertAlmostEqual(state['SEEN'], 100.); self.assertEqual(state['J']['axes'], [7.] * 9)

    def test_two_converted_actuals_are_independent(self):
        p, _ = program('work(j,j)', routines='ROUTINE work(v,w:POSITION) BEGIN v.location.x=99 seen=w.location.x END work')
        self.assertAlmostEqual(p.run()['SEEN'], 100.); self.assertEqual(len(operations(p, 'KINEMATIC_ARGUMENT')), 2)

    def test_converted_formal_forwarding_stays_private(self):
        p, _ = program('p=outer(j)', routines='ROUTINE inner(v:POSITION) BEGIN v.location.x=99 END inner '
            'ROUTINE outer(v:POSITION):POSITION BEGIN inner(v) RETURN v END outer')
        state = p.run(); self.assertEqual((state['P']['LOCATION']['X'], state['J']['axes']), (99., [0., 90.] + [0.] * 7))

    def test_transparent_joint_and_pose_aliases_resolve_before_conversion(self):
        p, _ = program('p=work(j)', prefix='TYPE axes=JOINTPOS point=POSITION',
                       routines='ROUTINE work(v:point):point BEGIN RETURN v END work')
        self.assertAlmostEqual(p.run()['P']['LOCATION']['Y'], 100.)

    def test_native_model_width_and_zero_padded_nine_are_accepted(self):
        for width in (2, 9):
            with self.subTest(width=width):
                p, _ = program('work(j)', decl=DECL.replace('j,k,out:JOINTPOS', f'j,k,out:JOINTPOS{width}'),
                               routines='ROUTINE work(v:POSITION) BEGIN seen=v.location.x END work')
                self.assertAlmostEqual(p.run()['SEEN'], 100.)

    def test_other_model_input_widths_and_nonzero_padding_fail(self):
        for values in ([0.], [0., 90., 0.], [0., 90., 1.] + [0.] * 6):
            with self.subTest(values=values):
                width = len(values)
                p, _ = program('n=0 work(j)', decl=DECL.replace('j,k,out:JOINTPOS', f'j,k,out:JOINTPOS{width}'),
                               routines='ROUTINE work(v:POSITION) BEGIN n=1 END work')
                p._state.values['J'] = joint(values)
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual((p.snapshot()['N'], p._state.local_frames), (0, []))

    def test_custom_forward_adapter_accepts_each_explicit_joint_width(self):
        for width in range(1, 10):
            with self.subTest(width=width):
                seen = []
                def forward(joints, frame, tool, selector):
                    seen.append(joints.spec); point = identity_pose(); point.values['LOCATION'].values['X'] = float(width)
                    return point, point.values['CONFIG_DATA'], [0., 0., 0.]
                p, _ = program('work(j)', decl=DECL.replace('j,k,out:JOINTPOS', f'j,k,out:JOINTPOS{width}'),
                               context=callback_context(forward=forward), routines='ROUTINE work(v:POSITION) BEGIN seen=v.location.x END work')
                self.assertEqual((p.run()['SEEN'], seen), (float(width), [('JOINTPOS', width)]))


class KinematicReturnTests(unittest.TestCase):
    def test_forward_return_to_each_cartesian_type_is_detached(self):
        for target, kind in CARTESIANS:
            with self.subTest(kind=kind):
                p, _ = program(f'{target}=make() j=k', routines=f'ROUTINE make:{kind} BEGIN RETURN j END make')
                state = p.run(); self.assertAlmostEqual(snapshot_x(state[target.upper()], kind), 100.)
                self.assertEqual(state['J']['axes'], [7.] * 9); self.assertEqual(len(operations(p, 'KINEMATIC_RETURN')), 1)

    def test_inverse_return_from_each_cartesian_type_uses_current_seed(self):
        for actual, kind in CARTESIANS:
            for width in (2, 9):
                with self.subTest(kind=kind, width=width):
                    decl = DECL.replace('j,k,out:JOINTPOS', f'j,k:JOINTPOS out:JOINTPOS{width}')
                    p, _ = program('out=make()', decl=decl, routines=f'ROUTINE make:JOINTPOS{width} BEGIN RETURN {actual} END make')
                    self.assertEqual(p.run()['OUT']['axes'], [0., 90.] + [0.] * (width - 2))
                    self.assertEqual(p._state.execution.robot.current.joints.values, [0., 90.])
                    self.assertEqual(len(operations(p, 'KINEMATIC_RETURN')), 1)

    def test_local_joint_return_converts_before_frame_cleanup(self):
        p, _ = program('p=make()', routines='ROUTINE make:POSITION VAR local:JOINTPOS BEGIN local=j RETURN local END make')
        self.assertAlmostEqual(p.run()['P']['LOCATION']['Y'], 100.); self.assertEqual((p._state.local_frames, p._state.call_depth), ([], 0))

    def test_roundtrip_forwarding_uses_two_explicit_interface_conversions(self):
        p, _ = program('out=outer()', routines='ROUTINE first:POSITION BEGIN RETURN j END first '
            'ROUTINE outer:JOINTPOS BEGIN RETURN first END outer')
        self.assertEqual(p.run()['OUT']['axes'], [0., 90.] + [0.] * 7)
        self.assertEqual(len(operations(p, 'KINEMATIC_RETURN')), 2)

    def test_argument_conversion_then_opposite_return_is_independent(self):
        p, _ = program('out=roundtrip(j)', routines='ROUTINE roundtrip(v:POSITION):JOINTPOS BEGIN RETURN v END roundtrip')
        state = p.run(); self.assertEqual((state['OUT']['axes'], state['J']['axes']), ([0., 90.] + [0.] * 7, [0., 90.] + [0.] * 7))
        self.assertEqual((len(operations(p, 'KINEMATIC_ARGUMENT')), len(operations(p, 'KINEMATIC_RETURN'))), (1, 1))

    def test_return_conversion_failure_skips_destination_selector(self):
        p, _ = program('n=0 points[pick()]=make()', context=None, decl=DECL + ' points:ARRAY[1] OF POSITION',
            routines='ROUTINE make:POSITION BEGIN RETURN j END make ROUTINE pick:INTEGER BEGIN n=n+1 RETURN 1 END pick')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'robot'): p.run()
        self.assertEqual((p.snapshot()['N'], p._state.local_frames, p._state.call_depth), (0, [], 0))

    def test_return_capture_precedes_destination_selector_mutation(self):
        p, _ = program('points[pick()]=make()', decl=DECL + ' points:ARRAY[1] OF POSITION',
            routines='ROUTINE make:POSITION BEGIN RETURN j END make ROUTINE pick:INTEGER BEGIN j=k RETURN 1 END pick')
        state = p.run(); self.assertAlmostEqual(state['POINTS'][0]['LOCATION']['X'], 100.); self.assertEqual(state['J']['axes'], [7.] * 9)

    def test_recursive_forwarded_returns_do_not_repeat_conversion(self):
        p, _ = program('p=recurse(3)', routines='ROUTINE recurse(depth:INTEGER):POSITION BEGIN IF depth=0 THEN RETURN j ENDIF RETURN recurse(depth-1) END recurse')
        self.assertAlmostEqual(p.run()['P']['LOCATION']['X'], 100.)
        self.assertEqual((len(operations(p, 'KINEMATIC_RETURN')), p._state.call_depth, p._state.local_frames), (1, 0, []))


class KinematicContextAndValidationTests(unittest.TestCase):
    def test_missing_model_context_fails_before_later_arguments_and_callee(self):
        p, _ = program('n=0 work(j,later())', context=None, routines='ROUTINE later:INTEGER BEGIN n=1 RETURN 0 END later '
            'ROUTINE work(v:POSITION; scalar:INTEGER) BEGIN n=2 END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'robot'): p.run()
        self.assertEqual((p.snapshot()['N'], p._state.local_frames), (0, []))

    def test_inverse_never_uses_destination_as_a_missing_seed(self):
        ctx = model_context(); ctx.robot.current = None
        p, _ = program('out=make()', context=ctx, routines='ROUTINE make:JOINTPOS BEGIN RETURN p END make')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'current joints'): p.run()
        self.assertEqual(p.snapshot()['OUT']['axes'], [7.] * 9)

    def test_inverse_missing_current_joints_rejects_even_with_current_pose(self):
        ctx = model_context(); ctx.robot.current = rt.RobotState(position=identity_pose())
        p, _ = program('work(p)', context=ctx, routines='ROUTINE work(v:JOINTPOS) BEGIN END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'current joints'): p.run()

    def test_limits_only_configuration_does_not_invent_a_model(self):
        ctx = rt.ExecutionContext(robot=rt.RobotContext(joint_limits=[(-180, 180)] * 2, frames={0:identity_pose()}, tools={0:identity_pose()}))
        p, _ = program('work(j)', context=ctx, routines='ROUTINE work(v:POSITION) BEGIN END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'adapter'): p.run()

    def test_missing_selected_frame_or_tool_rejects_without_callback(self):
        for field in ('frames', 'tools'):
            with self.subTest(field=field):
                called = []; ctx = callback_context(forward=lambda *args: called.append(1)); getattr(ctx.robot, field).clear()
                p, _ = program('work(j)', context=ctx, routines='ROUTINE work(v:POSITION) BEGIN END work')
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual(called, [])

    def test_selected_frame_and_tool_are_used_without_mutating_robot_state(self):
        ctx = model_context((0., 0.)); ctx.robot.frames[2] = identity_pose(); ctx.robot.frames[2].values['LOCATION'].values['X'] = 10.
        ctx.robot.tools[3] = identity_pose(); ctx.robot.tools[3].values['LOCATION'].values['Y'] = 20.
        ctx.robot.active_frame, ctx.robot.active_tool = 2, 3
        p, _ = program('p=make()', context=ctx, routines='ROUTINE make:POSITION BEGIN RETURN j END make')
        p._state.values['J'] = joint([0.] * 9); before = deepcopy(ctx.to_config()['robot']); state = p.run()
        self.assertAlmostEqual(state['P']['LOCATION']['X'], 190.); self.assertAlmostEqual(state['P']['LOCATION']['Y'], 20.)
        self.assertEqual(ctx.to_config()['robot'], before)

    def test_source_group_must_be_explicitly_configured(self):
        p, _ = program('work(j)', decl=DECL + ' grouped:XYZWPREXT IN GROUP[2]', routines='ROUTINE work(v:POSITION) BEGIN END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'group'): p.run()

    def test_partial_nonfinite_or_invalid_joint_input_fails_before_callee(self):
        for bad in (rt.UNINITIALIZED, float('nan'), True):
            with self.subTest(bad=bad):
                p, _ = program('n=0 work(j)', routines='ROUTINE work(v:POSITION) BEGIN n=1 END work')
                p._state.values['J'].values[0] = bad
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual((p.snapshot()['N'], p._state.local_frames), (0, []))

    def test_inverse_partial_cartesian_config_or_extended_axes_fail(self):
        for actual, member in (('P', 'CONFIG_DATA'), ('E', 'EXT2')):
            with self.subTest(actual=actual):
                p, _ = program('n=0 work(' + actual + ')', routines='ROUTINE work(v:JOINTPOS) BEGIN n=1 END work')
                if member == 'CONFIG_DATA': p._state.values[actual].values[member].values['CFG_FLIP'] = rt.UNINITIALIZED
                else: p._state.values[actual].values[member] = rt.UNINITIALIZED
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual(p.snapshot()['N'], 0)

    def test_inverse_invalid_rotation_rejects(self):
        p, _ = program('work(p)', routines='ROUTINE work(v:JOINTPOS) BEGIN END work')
        p._state.values['P'].values['NORMAL'].values.update(X=2.)
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'unit'): p.run()

    def test_inverse_wrong_target_width_fails_before_model_callback(self):
        called = []; ctx = model_context(); ctx.robot.inverse = lambda *args: called.append(1)
        p, _ = program('work(p)', context=ctx, routines='ROUTINE work(v:JOINTPOS3) BEGIN END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'output'): p.run()
        self.assertEqual(called, [])

    def test_model_joint_limits_and_unsolved_inverse_preserve_destinations(self):
        ctx = model_context((0., 90.)); ctx.robot.model.limits[0] = (-5., 5.)
        p, _ = program('p=make()', context=ctx, routines='ROUTINE make:POSITION BEGIN RETURN j END make')
        p._state.values['J'] = joint([90., 0.] + [0.] * 7); before = p.snapshot()['P']
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'limits'): p.run()
        self.assertEqual(p.snapshot()['P'], before)
        p, _ = program('out=make()', routines='ROUTINE make:JOINTPOS BEGIN RETURN p END make')
        p._state.values['P'].values['LOCATION'].values['X'] = 10000.
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'IK solution'): p.run()
        self.assertEqual(p.snapshot()['OUT']['axes'], [7.] * 9)

    def test_model_external_axes_survive_extended_interface_roundtrip(self):
        ctx = rt.ExecutionContext.from_config({'robot': {'dh': [{'a':100}, {'type':'prismatic'}], 'external_axes':1,
            'current': {'joints': {'type':['JOINTPOS',2], 'value':[0.,25.]}}}})
        p, _ = program('e=forward(j) out=inverse(e)', context=ctx,
            routines='ROUTINE forward(v:XYZWPREXT):XYZWPREXT BEGIN RETURN v END forward '
                     'ROUTINE inverse(v:JOINTPOS):JOINTPOS BEGIN RETURN v END inverse')
        p._state.values['J'] = joint([0.,25.] + [0.] * 7); state = p.run()
        self.assertEqual((state['E']['Z'], state['E']['EXT1'], state['OUT']['axes']), (25., 25., [0.,25.] + [0.] * 7))


class KinematicAdapterAndLifecycleTests(unittest.TestCase):
    def test_forward_config_and_external_outputs_are_authoritative(self):
        point = identity_pose(); config = point.values['CONFIG_DATA'].clone(); config.values['CFG_FLIP'] = True
        ctx = callback_context(forward=lambda *args: (point, config, [1.,2.,3.]))
        p, _ = program('e=work(j)', context=ctx, routines='ROUTINE work(v:XYZWPREXT):XYZWPREXT BEGIN RETURN v END work')
        state = p.run(); self.assertTrue(state['E']['CONFIG_DATA']['CFG_FLIP'])
        self.assertEqual([state['E'][key] for key in ('EXT1','EXT2','EXT3')], [1.,2.,3.])
        self.assertFalse(point.values['CONFIG_DATA'].values['CFG_FLIP'])

    def test_inverse_receives_current_seed_config_and_source_external_axes(self):
        seen = []
        def inverse(reference, point, frame, tool, selector, config, axes):
            seen.append((list(reference.values), selector, list(axes.values), config.values.copy())); return joint([3.,4.])
        ctx = callback_context(inverse=inverse, values=(11.,22.))
        p, _ = program('out=work(e)', decl=DECL.replace('j,k,out:JOINTPOS', 'j,k:JOINTPOS out:JOINTPOS2'), context=ctx,
                       routines='ROUTINE work(v:JOINTPOS2):JOINTPOS2 BEGIN RETURN v END work')
        p._state.values['E'].values.update(EXT1=5., EXT2=6., EXT3=7.)
        state = p.run(); self.assertEqual((state['OUT']['axes'], seen[0][:3]), ([3.,4.], ([11.,22.], 0, [5.,6.,7.])))
        self.assertEqual(ctx.robot.current.joints.values, [11.,22.])

    def test_plain_pose_inverse_supplies_zero_external_axes(self):
        for actual in ('p', 'a'):
            with self.subTest(actual=actual):
                captured = []
                def inverse(reference, point, frame, tool, selector, config, axes): captured.append(axes.values[:]); return joint([1.,2.])
                p, _ = program('work(' + actual + ')', context=callback_context(inverse=inverse), routines='ROUTINE work(v:JOINTPOS2) BEGIN END work')
                p.run(); self.assertEqual(captured, [[0.,0.,0.]])

    def test_callback_inputs_are_detached_from_source_seed_and_frame_tool(self):
        point = identity_pose()
        def forward(joints, frame, tool, selector):
            joints.values[0] = 999.; frame.values['LOCATION'].values['X'] = 999.; tool.values['LOCATION'].values['Y'] = 999.
            return point, point.values['CONFIG_DATA'], [0.,0.,0.]
        ctx = callback_context(forward=forward); p, _ = program('p=work(j)', context=ctx,
            routines='ROUTINE work(v:POSITION):POSITION BEGIN v.location.x=5 RETURN v END work')
        state = p.run()
        self.assertEqual((state['J']['axes'][0], ctx.robot.current.joints.values, ctx.robot.frames[0].values['LOCATION'].values['X'],
                          ctx.robot.tools[0].values['LOCATION'].values['Y'], point.values['LOCATION'].values['X']), (0., [10.,20.], 0., 0., 0.))

    def test_inverse_adapter_inputs_are_detached_from_source_seed_and_context(self):
        def inverse(reference, point, frame, tool, selector, config, axes):
            reference.values[0] = 999.; point.values['X'] = 999.
            frame.values['LOCATION'].values['X'] = 999.; tool.values['LOCATION'].values['Y'] = 999.
            config.values['CFG_LEFT'] = False; axes.values[0] = 999.
            return joint([3.,4.])
        ctx = callback_context(inverse=inverse)
        p, _ = program('work(e)', context=ctx, routines='ROUTINE work(v:JOINTPOS2) BEGIN END work')
        before = p.snapshot()['E']; p.run()
        self.assertEqual((p.snapshot()['E'], ctx.robot.current.joints.values), (before, [10.,20.]))
        self.assertEqual((ctx.robot.frames[0].values['LOCATION'].values['X'], ctx.robot.tools[0].values['LOCATION'].values['Y']), (0.,0.))

    def test_malformed_adapter_outputs_fail_before_formal_entry(self):
        point = identity_pose()
        for returned in (None, (point, point.values['CONFIG_DATA'], [0.]), (point, point.values['CONFIG_DATA'], [0.,True,0.])):
            with self.subTest(returned=returned):
                p, _ = program('n=0 work(j)', context=callback_context(forward=lambda *args: returned),
                               routines='ROUTINE work(v:POSITION) BEGIN n=1 END work')
                with self.assertRaises(rt.KarelRuntimeError): p.run()
                self.assertEqual((p.snapshot()['N'], p._state.local_frames, operations(p, 'KINEMATIC_ARGUMENT')[-1]['outcome']), (0, [], 'failed'))

    def test_inverse_callback_requires_exact_declared_width(self):
        p, _ = program('work(p)', context=callback_context(inverse=lambda *args: joint([0.,0.])), routines='ROUTINE work(v:JOINTPOS) BEGIN END work')
        with self.assertRaises(rt.KarelRuntimeError): p.run()

    def test_adapter_failure_keeps_prior_source_effects_without_entering_callee(self):
        def forward(*args): raise ValueError('Authored conversion failure')
        p, _ = program("trace='' work(make())", context=callback_context(forward=forward),
            routines="ROUTINE make:JOINTPOS BEGIN trace=trace+'S' RETURN j END make ROUTINE work(v:POSITION) BEGIN trace=trace+'C' END work")
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'Authored conversion failure') as caught: p.run()
        self.assertIsNotNone(caught.exception.line); self.assertEqual((p.snapshot()['TRACE'], p._state.call_depth, p._state.local_frames), ('S', 0, []))

    def test_swallowed_abort_blocks_argument_publication_and_is_sticky(self):
        p = None
        def forward(*args):
            try: p._state.abort(99)
            except rt.KarelAbort: pass
            point = identity_pose(); return point, point.values['CONFIG_DATA'], [0.,0.,0.]
        p, _ = program('n=0 work(j)', context=callback_context(forward=forward), routines='ROUTINE work(v:POSITION) BEGIN n=1 END work')
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual((p.snapshot()['N'], p._state.local_frames, operations(p, 'KINEMATIC_ARGUMENT')[-1]['outcome']), (0, [], 'failed'))
        with self.assertRaises(rt.KarelAbort): p.run()

    def test_abort_is_authoritative_over_later_return_adapter_error(self):
        p = None
        def inverse(*args):
            try: p._state.abort(99)
            except rt.KarelAbort: pass
            raise ValueError('After abort')
        p, _ = program('out=make()', context=callback_context(inverse=inverse), routines='ROUTINE make:JOINTPOS BEGIN RETURN p END make')
        with self.assertRaises(rt.KarelAbort): p.run()
        self.assertEqual((p.snapshot()['OUT']['axes'], p._state.local_frames), ([7.] * 9, []))

    def test_pause_resume_does_not_repeat_completed_argument_conversion(self):
        p, _ = program('p=work(j)', cooperative=True,
            routines='ROUTINE work(v:POSITION):POSITION BEGIN v.location.x=99 PAUSE RETURN v END work')
        with self.assertRaises(rt.KarelPause): p.run()
        self.assertEqual(len(operations(p, 'KINEMATIC_ARGUMENT')), 1)
        p.resume(); self.assertEqual((p.snapshot()['P']['LOCATION']['X'], len(operations(p, 'KINEMATIC_ARGUMENT'))), (99., 1))

    def test_stop_unwinds_private_converted_cell_without_copyback(self):
        p, _ = program('p=work(j)', cooperative=True,
            routines='ROUTINE work(v:POSITION):POSITION BEGIN v.location.x=99 PAUSE RETURN v END work')
        before = p.snapshot()['P']
        with self.assertRaises(rt.KarelPause): p.run()
        p.stop(); self.assertEqual((p.snapshot()['P'], p.snapshot()['J']['axes'], p._state.local_frames), (before, [0.,90.] + [0.] * 7, []))


class KinematicLinkAndEvidenceTests(unittest.TestCase):
    def test_linked_formal_conversion_and_linked_return_use_root_group(self):
        sources = {
            'main': 'PROGRAM MAIN VAR j:JOINTPOS p,q:POSITION grouped:XYZWPREXT IN GROUP[2] '
                    'ROUTINE echo(v:POSITION):POSITION FROM LIB ROUTINE point(v:JOINTPOS):POSITION FROM LIB '
                    'BEGIN j=CURJPOS(0,0) p=echo(j) q=point(j) END MAIN',
            'lib': 'PROGRAM LIB VAR grouped:XYZWPREXT IN GROUP[1] '
                   'ROUTINE echo(v:POSITION):POSITION BEGIN RETURN v END echo '
                   'ROUTINE point(v:JOINTPOS):POSITION BEGIN RETURN v END point BEGIN END LIB'}
        second = model_context((0.,90.)).robot; second.model = rt.SerialRobotModel([{'a':30}, {'a':40}]); second.forward = second.model.forward
        ctx = rt.ExecutionContext(robot=rt.RobotContext(groups={1:model_context((0.,0.)).robot, 2:second}, active_group=1))
        instance = translate_project(sources).instantiate(context=ctx); instance.run('MAIN'); state = instance.programs['MAIN'].snapshot()
        self.assertAlmostEqual(state['P']['LOCATION']['X'], 30.); self.assertAlmostEqual(state['Q']['LOCATION']['Y'], 40.)
        self.assertEqual(second.current.joints.values, [0.,90.])

    def test_explicit_routine_callback_receives_private_declared_cartesian_reference(self):
        captured = []
        def external(reference):
            captured.append(reference.spec); rt.field_reference(reference.raw().values['LOCATION'], 'X').set(99.)
        ctx = model_context((0.,90.)); ctx.externals['LIB', 'WORK'] = external
        p, _ = program('work(j)', context=ctx, routines='ROUTINE work(v:POSITION) FROM LIB')
        state = p.run(); self.assertEqual((captured, state['J']['axes']), ([('POSITION',)], [0.,90.] + [0.] * 7))

    def test_raw_external_result_stays_exact_while_outer_return_can_convert(self):
        ctx = model_context((0.,90.)); ctx.externals['LIB', 'VALUE'] = lambda: joint([0.,90.] + [0.] * 7)
        p, _ = program('p=outer()', context=ctx, routines='ROUTINE value:JOINTPOS FROM LIB ROUTINE outer:POSITION BEGIN RETURN value() END outer')
        self.assertAlmostEqual(p.run()['P']['LOCATION']['X'], 100.)
        p, _ = program('p=wrong()', context=ctx, routines='ROUTINE wrong:POSITION FROM LIB')
        ctx.externals['LIB', 'WRONG'] = lambda: joint([0.,90.] + [0.] * 7)
        with self.assertRaises(rt.KarelRuntimeError): p.run()

    def test_standard_model_context_json_replay_keeps_robot_state_unchanged(self):
        p, result = program('p=work(j) out=back(p)', routines='ROUTINE work(v:POSITION):POSITION BEGIN RETURN v END work '
                            'ROUTINE back(v:JOINTPOS):JOINTPOS BEGIN RETURN v END back')
        expected = p.run(); saved = json.loads(json.dumps(p._state.execution.to_config()))
        ns = {'__name__':'kinematic_replay'}; exec(result.python_source, ns)
        restored = ns['Program'](context=rt.ExecutionContext.from_config(saved))
        self.assertEqual(restored.snapshot(), expected); self.assertEqual(restored.run(), expected)
        self.assertEqual(restored._state.execution.to_config()['robot'], saved['robot'])

    def test_runtime_operations_are_value_free_and_distinguish_arguments_and_returns(self):
        p, _ = program('out=work(j)', routines='ROUTINE work(v:POSITION):JOINTPOS BEGIN RETURN v END work')
        p.run(); rows = p.service_requests
        self.assertEqual([row['operation'] for row in rows], ['KINEMATIC_ARGUMENT', 'KINEMATIC_RETURN'])
        self.assertTrue(all(set(row) == {'operation','line','outcome'} and row['outcome'] == 'completed' for row in rows))

    def test_conversion_service_effects_propagate_through_source_calls(self):
        _, result = program('n=outer()', routines='ROUTINE consume(v:POSITION):INTEGER BEGIN RETURN 1 END consume '
            'ROUTINE inner:INTEGER BEGIN RETURN consume(j) END inner ROUTINE outer:INTEGER BEGIN RETURN inner() END outer')
        for name in ('INNER', 'OUTER'):
            self.assertTrue(result.report['routine_effects'][name]['potential_service_requests'])

    def test_source_report_records_exact_specs_and_conversion_kind(self):
        _, result = program('out=work(j)', routines='ROUTINE work(v:POSITION):JOINTPOS BEGIN RETURN v END work')
        report = json.loads(json.dumps(result.report)); rows = report['kinematic_interfaces']
        self.assertEqual([row['operation'] for row in rows], ['KINEMATIC_RETURN', 'KINEMATIC_ARGUMENT'])
        by_operation = {row['operation']: row for row in rows}
        self.assertEqual((by_operation['KINEMATIC_ARGUMENT']['source_type_spec'], by_operation['KINEMATIC_ARGUMENT']['target_type_spec']),
                         (['JOINTPOS',9], ['POSITION']))
        self.assertEqual((by_operation['KINEMATIC_RETURN']['source_type_spec'], by_operation['KINEMATIC_RETURN']['target_type_spec']),
                         (['POSITION'], ['JOINTPOS',9]))
        self.assertTrue(all(row['evaluated_once'] and row['independent_value'] and row['line'] > 0 and row['column'] > 0 for row in rows))
        self.assertTrue(by_operation['KINEMATIC_RETURN']['before_cleanup'])
        for row in report['positional_value_arguments'] + report['positional_returns']:
            self.assertTrue(row['converted']); self.assertEqual(row['conversion_kind'], 'kinematic')

    def test_declared_routine_callback_failure_does_not_copy_private_joint_writes_back(self):
        def external(reference): reference.raw().values[0] = 999.; raise ValueError('Authored external failure')
        ctx = model_context((0.,90.)); ctx.externals['LIB', 'WORK'] = external
        p, _ = program('work(p)', context=ctx, routines='ROUTINE work(v:JOINTPOS) FROM LIB')
        before = p.snapshot()['P']
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'Authored external failure'): p.run()
        self.assertEqual((p.snapshot()['P'], ctx.robot.current.joints.values, p._state.local_frames), (before, [0.,90.], []))


class KinematicExactBoundaryTests(unittest.TestCase):
    def test_runtime_helper_is_pythonic_and_rejects_nonkinematic_pairs_before_requests(self):
        p, _ = program()
        with rt._numeric_scope('strict'), self.assertRaisesRegex(rt.KarelRuntimeError, 'Pythonic'):
            p._state.kinematic_interface(('POSITION',), p._state.values['J'], 17)
        with rt._numeric_scope('pythonic'):
            for target, value in ((('JOINTPOS',9), p._state.values['J']), (('POSITION',), p._state.values['P'])):
                with self.subTest(target=target), self.assertRaisesRegex(rt.KarelRuntimeError, 'one joint and one Cartesian'):
                    p._state.kinematic_interface(target, value, 17)
            with self.assertRaisesRegex(rt.KarelRuntimeError, 'BOOLEAN'):
                p._state.kinematic_interface(('POSITION',), p._state.values['J'], 17, result=1)
        self.assertEqual(p.service_requests, ())

    def test_joint_width_conversion_has_separate_source_policy(self):
        for body, routines in (('work(j)', 'ROUTINE work(v:JOINTPOS3) BEGIN END work'),
                               ('', 'ROUTINE make:JOINTPOS3 BEGIN RETURN j END make')):
            with self.subTest(body=body):
                p,result=program(body,routines=routines)
                self.assertTrue(result.report['joint_width_conversions'])
                self.assertEqual(result.report['kinematic_interfaces'],[])
                if body:p.run()

    def test_byname_and_linked_declared_interfaces_stay_exact(self):
        p, _ = program("entry=77 work(BYNAME('','J',entry))", routines='ROUTINE work(v:POSITION) BEGIN END work')
        with self.assertRaisesRegex(rt.KarelRuntimeError, 'type does not match'): p.run()
        self.assertEqual(p.snapshot()['ENTRY'], 77)
        project = translate_project({'lib': source('LIB','',routines='ROUTINE work(v:JOINTPOS) BEGIN END work'),
                                     'main': source('MAIN','',routines='ROUTINE work(v:POSITION) FROM LIB')})
        with self.assertRaises(ValueError): project.instantiate()

    def test_named_arrays_and_aggregates_do_not_convert_elements(self):
        with self.assertRaises(TranslationError): compile_program('work(j)', prefix='TYPE joints_t=ARRAY[1]OF JOINTPOS', decl='j:joints_t', routines='ROUTINE work(v:ARRAY OF POSITION) BEGIN END work')
        with self.assertRaises(TranslationError): compile_program('', prefix='TYPE joints_t=ARRAY[1]OF JOINTPOS', decl='j:joints_t', routines='ROUTINE make:ARRAY OF POSITION BEGIN RETURN j END make')
        with self.assertRaises(TranslationError): compile_program('work(box)', decl='box:packet', prefix='TYPE packet=STRUCTURE j:JOINTPOS ENDSTRUCTURE', routines='ROUTINE work(v:POSITION) BEGIN END work')

    def test_orientation_outputs_and_explicit_global_counter_effects_stay_guarded(self):
        with self.assertRaises(TranslationError) as caught: program('work(j)', routines='ROUTINE work(v:POSITION) BEGIN v.normal.x=9 END work')
        self.assertEqual(caught.exception.code, 'E_POSITION_READ_ONLY')
        with self.assertRaises(TranslationError) as caught: program('FOR n=1 TO 2 DO work(j) ENDFOR', routines='ROUTINE work(v:POSITION) BEGIN n=7 END work')
        self.assertEqual(caught.exception.code, 'E_FOR_COUNTER')

    def test_legacy_source_rejects_argument_and_return_conversions(self):
        for _, kind in CARTESIANS:
            for body, routines in (('work(j)', f'ROUTINE work(v:{kind}) BEGIN END work'),
                                   ('work(p)', 'ROUTINE work(v:JOINTPOS) BEGIN END work'),
                                   ('', f'ROUTINE make:{kind} BEGIN RETURN j END make'),
                                   ('', 'ROUTINE make:JOINTPOS BEGIN RETURN p END make')):
                with self.subTest(kind=kind, body=body), self.assertRaises(TranslationError):
                    legacy_translate(f'PROGRAM T VAR j:JOINTPOS p:POSITION {routines} BEGIN {body} END T')


if __name__ == '__main__': unittest.main()
