"""Authored named/component ARRAY conversions and checked ownership boundaries."""
import copy
import json
import unittest
from karel2py import runtime as rt,translate_project
from karel2py.lexer import TranslationError
from karel2py.kinematics import pose as identity_pose
from tests.test_extended_services import compile_program
from tests.test_cartesian_interfaces import value as pose
from tests.test_joint_interoperability import joint,model_context
from tests.test_kinematic_assignments import callback_context
from tests.legacy_numeric_support import translate as legacy_translate

U={'uninitialized':True}


def declarations(first,second,layout='nested'):
    if layout=='flat':return f'TYPE in_t=ARRAY[2]OF {first} out_t=ARRAY[2]OF {second}'
    if layout=='matrix':return f'TYPE in_t=ARRAY[1,2]OF {first} out_t=ARRAY[1,2]OF {second}'
    rows=f'TYPE in_row=ARRAY[2]OF {first} out_row=ARRAY[2]OF {second} '
    if layout=='deep':return rows+'in_plane=ARRAY[1]OF in_row out_plane=ARRAY[1]OF out_row in_t=ARRAY[1]OF in_plane out_t=ARRAY[1]OF out_plane'
    return rows+'in_t=ARRAY[2]OF in_row out_t=ARRAY[2]OF out_row'


def build(body='b=a',first='INTEGER',second='REAL',layout='nested',routines='',**options):
    return compile_program(body,prefix=declarations(first,second,layout),decl='a:in_t b:out_t n,s,e,visits:INTEGER done:BOOLEAN',routines=routines,**options)


def cells(value):
    for i,child in enumerate(value.values):
        if isinstance(child,rt.Array):yield from cells(child)
        else:yield value.values,i


def leaves(value):return [storage[key] for storage,key in cells(value)]


def initialize(task,values=None):
    array=task._state.values['A'];spec=rt.array_leaf_spec(array.spec);pairs=list(cells(array))
    for index,(storage,key) in enumerate(pairs):
        if values is not None:storage[key]=copy.deepcopy(values[index]);continue
        if spec[0]=='JOINTPOS':storage[key]=joint([0.,90.]+[0.]*(spec[1]-2))
        elif spec[0] in ('POSITION','XYZWPR','XYZWPREXT'):storage[key]=pose(spec[0],(float(index+1),2.,3.),(0.,0.,90.))
        else:storage[key]=index+1
    return task


def outputs(task):return leaves(task._state.values['B'])


class NamedNumericConversionTests(unittest.TestCase):
    def test_numeric_pairs_preserve_all_component_schemas(self):
        for layout in ('flat','matrix','nested','deep'):
            for first in ('INTEGER','BYTE','SHORT'):
                for second in ('INTEGER','BYTE','SHORT','REAL'):
                    if first==second:continue
                    with self.subTest(layout=layout,first=first,second=second):
                        p,_=build(first=first,second=second,layout=layout);initialize(p);source=p._state.values['A'].spec;p.run()
                        self.assertEqual(outputs(p),[float(i+1) if second=='REAL' else i+1 for i in range(len(outputs(p)))])
                        self.assertEqual(p._state.values['B'].spec,p._state.types['B']);self.assertEqual(p._state.values['A'].spec,source)

    def test_nested_destination_objects_keep_their_identities(self):
        p,_=build();initialize(p);array=p._state.values['B'];row=array.values[0];p.run()
        self.assertIs(p._state.values['B'],array);self.assertIs(array.values[0],row)
        self.assertEqual((rt.array_identity(array.spec),rt.array_identity(row.spec)),('OUT_T','OUT_ROW'))

    def test_multidimensional_named_components_keep_coordinate_order(self):
        prefix='TYPE in_row=ARRAY[1,2]OF INTEGER out_row=ARRAY[1,2]OF REAL in_t=ARRAY[2]OF in_row out_t=ARRAY[2]OF out_row'
        p,_=compile_program('b=a',prefix=prefix,decl='a:in_t b:out_t');initialize(p);p.run()
        self.assertEqual(p.snapshot()['B'],[[[1.,2.]],[[3.,4.]]]);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_missing_nested_numeric_leaves_remain_missing(self):
        p,_=build();initialize(p,(1,rt.UNINITIALIZED,3,rt.UNINITIALIZED));p.run()
        self.assertEqual(p.snapshot()['B'],[[1.,U],[3.,U]])

    def test_late_malformed_source_preserves_complete_receiver(self):
        p,_=build(first='BYTE');initialize(p,(1,2,3,256));old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_late_narrowing_overflow_preserves_complete_receiver(self):
        p,_=build(second='BYTE');initialize(p,(1,2,3,256));old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_short_sentinel_normalizes_only_the_converted_copy(self):
        p,_=build(first='SHORT');initialize(p,(1,2,3,32767));p.run()
        self.assertEqual(p.snapshot()['B'],[[1.,2.],[3.,U]]);self.assertEqual(leaves(p._state.values['A'])[-1],32767)

    def test_unknown_byte_cannot_be_promoted(self):
        p,_=build(first='BYTE');initialize(p,(1,2,3,rt.UNKNOWN_BYTE))
        with self.assertRaisesRegex(rt.KarelRuntimeError,'unknown'):p.run()
        self.assertIs(leaves(p._state.values['B'])[0],rt.UNINITIALIZED)

    def test_failed_conversion_skips_target_selector(self):
        prefix=declarations('INTEGER','BYTE')+' boxes_t=STRUCTURE data:out_t ENDSTRUCTURE'
        p,_=compile_program('visits=0 boxes[pick()].data=a',prefix=prefix,decl='a:in_t boxes:ARRAY[1]OF boxes_t visits:INTEGER',routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN 1 END pick')
        initialize(p,(1,2,3,256))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['VISITS'],0)

    def test_successful_rhs_capture_precedes_target_selector(self):
        prefix=declarations('INTEGER','REAL')+' boxes_t=STRUCTURE data:out_t ENDSTRUCTURE'
        p,_=compile_program('boxes[pick()].data=a',prefix=prefix,decl='a:in_t boxes:ARRAY[1]OF boxes_t',routines='ROUTINE pick:INTEGER BEGIN a[1,1]=99 RETURN 1 END pick');initialize(p)
        v=p.run();self.assertEqual((v['BOXES'][0]['DATA'][0][0],v['A'][0][0]),(1.,99))

    def test_named_bare_actual_is_private_on_conversion(self):
        p,_=build('work(a)',routines='ROUTINE work(v:out_t) BEGIN v[1,1]=99 n=TRUNC(v[1,1]) END work');initialize(p);v=p.run()
        self.assertEqual((v['A'][0][0],v['N']),(1,99))

    def test_named_grouped_actual_is_private_on_conversion(self):
        p,_=build('work((a))',routines='ROUTINE work(v:out_t) BEGIN v[1,1]=99 END work');initialize(p);self.assertEqual(p.run()['A'][0][0],1)

    def test_converted_argument_finishes_before_later_argument(self):
        routines='ROUTINE change:INTEGER BEGIN a[1,1]=99 RETURN 0 END change ROUTINE work(v:out_t;ignored:INTEGER) BEGIN n=TRUNC(v[1,1]) END work'
        p,_=build('work(a,change())',routines=routines);initialize(p);v=p.run();self.assertEqual((v['N'],v['A'][0][0]),(1,99))

    def test_failed_argument_skips_later_argument_and_callee(self):
        routines='ROUTINE later:INTEGER BEGIN n=1 RETURN 0 END later ROUTINE work(v:out_t;ignored:INTEGER) BEGIN n=2 END work'
        p,_=build('n=0 work(a,later())',second='BYTE',routines=routines);initialize(p,(1,2,3,256))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['N'],p._state.local_frames),(0,[]))

    def test_forwarding_aliases_only_the_private_copy(self):
        routines='ROUTINE inner(v:out_t) BEGIN v[1,1]=99 END inner ROUTINE work(v:out_t) BEGIN inner(v) n=TRUNC(v[1,1]) END work'
        p,_=build('work(a)',routines=routines);initialize(p);v=p.run();self.assertEqual((v['N'],v['A'][0][0]),(99,1))

    def test_exact_named_actual_retains_reference_contract(self):
        p,_=build('work(a)',routines='ROUTINE work(v:in_t) BEGIN v[1,1]=99 END work');initialize(p);self.assertEqual(p.run()['A'][0][0],99)

    def test_retained_handler_owns_only_the_converted_array(self):
        routines='ROUTINE retain(v:out_t) BEGIN CONDITION[1]: WHEN EVENT[1] DO v[1,1]=99 n=TRUNC(v[1,1]) ENDCONDITION END retain'
        p,_=build('retain(a) ENABLE CONDITION[1] SIGNAL EVENT[1]',routines=routines);initialize(p);v=p.run()
        self.assertEqual((v['A'][0][0],v['N']),(1,99))

    def test_converted_named_array_does_not_alias_active_counter(self):
        routines='ROUTINE work(v:out_t) BEGIN v[1,1]=99 END work'
        p,_=build('n=0 FOR a[1,1]=1 TO 2 DO work(a) n=n+a[1,1] ENDFOR',routines=routines);initialize(p)
        self.assertEqual((p.run()['N'],p.snapshot()['A'][0][0]),(3,U))

    def test_integer_timer_owns_private_promoted_formal(self):
        routines='ROUTINE work(v:out_t) BEGIN CONNECT TIMER TO v[1,1] v[1,1]=99 END work'
        p,_=build('n=0 FOR a[1,1]=1 TO 2 DO work(a) n=n+a[1,1] ENDFOR',first='SHORT',second='INTEGER',routines=routines,clock_us=lambda:0);initialize(p)
        self.assertEqual((p.run()['N'],p._state.execution._timer_claims),(3,{}))

    def test_pause_resume_and_stop_do_not_copy_back(self):
        for action in ('resume','stop'):
            with self.subTest(action=action):
                p,_=build('work(a)',routines='ROUTINE work(v:out_t) BEGIN v[1,1]=77 PAUSE v[1,1]=99 n=TRUNC(v[1,1]) END work');initialize(p)
                with self.assertRaises(rt.KarelPause):p.run()
                getattr(p,action)();self.assertEqual(p.snapshot()['A'][0][0],1);self.assertEqual(p._state.local_frames,[])

    def test_named_return_captures_before_counter_cleanup(self):
        routines='ROUTINE make:out_t BEGIN FOR a[1,1]=1 TO 2 DO RETURN a ENDFOR RETURN a END make'
        p,_=build('b=make()',routines=routines);initialize(p);v=p.run();self.assertEqual((v['A'][0][0],v['B'][0][0]),(U,1.))

    def test_named_return_conversion_failure_unwinds_frame(self):
        p,_=build('b=make()',second='BYTE',routines='ROUTINE make:out_t BEGIN RETURN a END make');initialize(p,(1,2,3,256))
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p._state.local_frames,[]);self.assertIs(outputs(p)[0],rt.UNKNOWN_BYTE)

    def test_json_roundtrip_preserves_receiver_named_components(self):
        p,_=build('IF UNINIT(done) THEN b=a done=TRUE ENDIF');initialize(p);p.run();config=json.loads(json.dumps(p._state.execution.to_config()))
        restored,_=build('IF UNINIT(done) THEN b=a done=TRUE ENDIF',context=rt.ExecutionContext.from_config(config));restored.run()
        self.assertEqual(restored.snapshot(),p.snapshot());self.assertEqual(restored._state.values['B'].spec,p._state.values['B'].spec)

    def test_anonymous_result_can_receive_converted_named_source(self):
        prefix=declarations('INTEGER','REAL','nested')
        p,_=compile_program('b=make()',prefix=prefix,decl='a:in_t b:ARRAY[2]OF out_row',routines='ROUTINE make:ARRAY OF out_row BEGIN RETURN a END make');initialize(p);p.run()
        self.assertEqual(outputs(p),[1.,2.,3.,4.]);self.assertIsNone(rt.array_identity(p._state.values['B'].spec))

    def test_named_target_receives_anonymous_numeric_source(self):
        p,_=compile_program('b=a',prefix='TYPE out_t=ARRAY[2]OF REAL',decl='a:ARRAY[2]OF INTEGER b:out_t');initialize(p);p.run()
        self.assertEqual(outputs(p),[1.,2.]);self.assertEqual(rt.array_identity(p._state.values['B'].spec),'OUT_T')


class NamedPositionalConversionTests(unittest.TestCase):
    def test_all_cartesian_pairs_and_nested_schemas(self):
        for first in ('POSITION','XYZWPR','XYZWPREXT'):
            for second in ('POSITION','XYZWPR','XYZWPREXT'):
                if first==second:continue
                for layout in ('flat','nested','deep'):
                    with self.subTest(first=first,second=second,layout=layout):
                        p,_=build(first=first,second=second,layout=layout);initialize(p);p.run()
                        self.assertEqual([v.values['LOCATION'].values['X'] if second=='POSITION' else v.values['X'] for v in outputs(p)],list(map(float,range(1,len(outputs(p))+1))))
                        self.assertEqual(p._state.values['B'].spec,p._state.types['B']);self.assertEqual(p.service_requests,())

    def test_all_joint_width_changes_keep_named_components(self):
        for first,second in ((2,9),(9,2),(1,3),(3,1)):
            p,_=build(first=f'JOINTPOS{first}',second=f'JOINTPOS{second}');initialize(p,[joint([float(i+1)]+[0.]*(first-1))for i in range(4)]);p.run()
            self.assertEqual([v.values for v in outputs(p)],[[float(i+1)]+[0.]*(second-1)for i in range(4)])

    def test_missing_pose_leaf_preserves_receiver(self):
        p,_=build(first='XYZWPR',second='POSITION');initialize(p);leaves(p._state.values['A'])[-1].values['X']=rt.UNINITIALIZED;old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_nonzero_discarded_joint_axis_fails_atomically(self):
        p,_=build(first='JOINTPOS3',second='JOINTPOS2');initialize(p,[joint([1.,2.,0.])for _ in range(4)]);leaves(p._state.values['A'])[-1].values[-1]=7.
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertTrue(all(v.values[0] is rt.UNINITIALIZED for v in outputs(p)))

    def test_position_orientation_remains_readonly_after_nested_conversion(self):
        with self.assertRaises(TranslationError) as error:build('b=a b[1,1].normal.x=1',first='XYZWPR',second='POSITION')
        self.assertEqual(error.exception.code,'E_POSITION_READ_ONLY')

    def test_private_named_pose_argument_cannot_modify_source(self):
        p,_=build('work(a)',first='XYZWPR',second='POSITION',routines='ROUTINE work(v:out_t) BEGIN v[1,1].location.x=99 END work');initialize(p)
        self.assertEqual(p.run()['A'][0][0]['X'],1.)

    def test_named_cartesian_return_uses_receiver_schema(self):
        p,_=build('b=make()',first='XYZWPR',second='POSITION',routines='ROUTINE make:out_t BEGIN RETURN a END make');initialize(p);p.run()
        self.assertEqual(outputs(p)[0].values['LOCATION'].values['X'],1.);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_late_improper_position_matrix_preserves_receiver(self):
        p,_=build(first='POSITION',second='XYZWPR');initialize(p);leaves(p._state.values['A'])[-1].values['NORMAL'].values['X']=7.;old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)


class NamedModelArrayTests(unittest.TestCase):
    def test_model_forward_walks_named_components_in_row_major_order(self):
        calls=[]
        def forward(joints,frame,tool,selector):
            calls.append(joints.values[:]);point=identity_pose();point.values['LOCATION'].values['X']=float(len(calls));return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward));initialize(p);p.run()
        self.assertEqual([v.values['LOCATION'].values['X']for v in outputs(p)],[1.,2.,3.,4.]);self.assertEqual(len(calls),4)

    def test_inverse_reuses_explicit_current_seed_without_chaining(self):
        calls=[]
        def inverse(seed,point,frame,tool,selector,config,axes):
            calls.append(seed.values[:]);seed.values[0]=99.;return joint([10.,20.])
        p,_=build(first='POSITION',second='JOINTPOS2',context=callback_context(inverse=inverse,values=(1.,2.)));initialize(p);p.run()
        self.assertEqual(calls,[[1.,2.]]*4);self.assertEqual([v.values for v in outputs(p)],[[10.,20.]]*4)

    def test_complete_source_preflight_precedes_first_adapter(self):
        calls=[]
        def forward(*args):calls.append(1);point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward));initialize(p);leaves(p._state.values['A'])[-1].values[0]=rt.UNINITIALIZED
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_late_source_matrix_is_validated_before_any_inverse(self):
        calls=[]
        def inverse(*args):calls.append(1);return joint([0.,0.])
        p,_=build(first='POSITION',second='JOINTPOS2',context=callback_context(inverse=inverse));initialize(p);leaves(p._state.values['A'])[-1].values['NORMAL'].values['X']=7.
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(calls,[])

    def test_late_adapter_failure_keeps_all_destination_objects(self):
        calls=[]
        def forward(*args):
            calls.append(1)
            if len(calls)==4:raise ValueError('authored adapter failure')
            point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward));initialize(p);array=p._state.values['B'];row=array.values[0];old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual((p.snapshot()['B'],len(calls)),(old,4));self.assertIs(array.values[0],row)

    def test_adapter_changes_to_original_do_not_retarget_captured_source(self):
        calls=[]
        def forward(joints,frame,tool,selector):
            calls.append(joints.values[:]);leaves(p._state.values['A'])[-1].values[:]=[9.,9.];point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward));initialize(p);p.run()
        self.assertEqual(calls,[[0.,90.]]*4);self.assertEqual(leaves(p._state.values['A'])[-1].values,[9.,9.])

    def test_sticky_abort_stops_further_adapter_calls(self):
        calls=[]
        def forward(*args):
            calls.append(1);p._state.abort(23)
        p,_=build(first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward));initialize(p)
        with self.assertRaises(rt.KarelAbort):p.run()
        self.assertEqual(len(calls),1);self.assertIs(outputs(p)[0].values['LOCATION'].values['X'],rt.UNINITIALIZED)

    def test_named_model_argument_is_private(self):
        p,_=build('work(a)',first='JOINTPOS2',second='POSITION',context=model_context((0.,90.)),routines='ROUTINE work(v:out_t) BEGIN v[1,1].location.x=99 END work');initialize(p);p.run()
        self.assertEqual(leaves(p._state.values['A'])[0].values,[0.,90.])

    def test_named_model_return_uses_concrete_receiver_components(self):
        p,_=build('b=make()',first='JOINTPOS2',second='XYZWPREXT',context=model_context((0.,90.)),routines='ROUTINE make:out_t BEGIN RETURN a END make');initialize(p);p.run()
        self.assertAlmostEqual(outputs(p)[0].values['X'],100.);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])

    def test_nested_receiver_allocation_bound_precedes_model_adapter(self):
        calls=[]
        def forward(*args):calls.append(1);point=identity_pose();return point,point.values['CONFIG_DATA'],[0.,0.,0.]
        p,_=build(first='JOINTPOS2',second='POSITION',context=callback_context(forward=forward))
        source=rt.Array(('ARRAY',100,('ARRAY',30,('JOINTPOS',2),'JOINT_ROW'),'JOINT_GRID'))
        for storage,key in cells(source):storage[key]=joint([0.,90.])
        target=('ARRAY',100,('ARRAY',30,('POSITION',),'POSE_ROW'),'POSE_GRID')
        with rt._numeric_scope('pythonic'),self.assertRaisesRegex(rt.KarelRuntimeError,'32767'):p._state.kinematic_array(target,source,23)
        self.assertEqual(calls,[])

    def test_model_context_is_never_inferred(self):
        p,_=build(first='JOINTPOS2',second='POSITION');initialize(p)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(outputs(p)[0].values['LOCATION'].values['X'],rt.UNINITIALIZED)


class NamedArrayBoundaryTests(unittest.TestCase):
    def test_component_partition_changes_keep_logical_dimensions(self):
        for first,second in [('INTEGER','REAL'),('XYZWPR','POSITION'),('JOINTPOS2','POSITION')]:
            prefix=f'TYPE row_t=ARRAY[2]OF {first} source_t=ARRAY[2]OF row_t target_t=ARRAY[2,2]OF {second}'
            with self.subTest(first=first):
                p,_=compile_program('b=a',prefix=prefix,decl='a:source_t b:target_t',context=model_context((0.,90.)));initialize(p);p.run()
                self.assertEqual(p._state.values['B'].shape,(2,2));self.assertEqual(len(outputs(p)),4)

    def test_shape_and_rank_changes_remain_rejected(self):
        for target in ('ARRAY[3]OF out_row','ARRAY[1,2]OF out_row','ARRAY[2]OF wider_row'):
            prefix=declarations('INTEGER','REAL')+' wider_row=ARRAY[3]OF REAL different_t='+target
            with self.subTest(target=target),self.assertRaises(TranslationError):compile_program('b=a',prefix=prefix,decl='a:in_t b:different_t')

    def test_same_terminal_named_retagging_owns_receiver_schema(self):
        p,_=build(first='INTEGER',second='INTEGER');initialize(p);p.run()
        self.assertEqual(outputs(p),[1,2,3,4]);self.assertEqual(p._state.values['B'].spec,p._state.types['B'])
        self.assertIsNot(p._state.values['A'].values[0],p._state.values['B'].values[0])

    def test_generic_checked_value_and_result_helpers_remain_exact(self):
        p,_=build();initialize(p);actual=p._state.values['A'];target=p._state.types['B']
        with rt._numeric_scope('pythonic'):
            for action in (lambda:rt.checked(target,actual),lambda:rt.value_argument(target,actual),lambda:rt.array_result(target,actual)):
                with self.subTest(action=action),self.assertRaises(rt.KarelRuntimeError):action()
        self.assertFalse(rt.parameter_accepts(target,actual.spec))

    def test_byname_keeps_exact_nominal_interface(self):
        p,_=build("e=77 work(BYNAME('','A',e))",routines='ROUTINE work(v:out_t) BEGIN END work');initialize(p)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'type does not match'):p.run()
        self.assertEqual(p.snapshot()['E'],77)

    def test_malformed_nested_source_child_is_checked_before_publication(self):
        p,_=build();initialize(p);p._state.values['A'].values[-1].spec=('ARRAY',2,('INTEGER',),'FOREIGN');old=p.snapshot()['B']
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertEqual(p.snapshot()['B'],old)

    def test_malformed_nominal_dimensions_do_not_classify(self):
        sources=[('ARRAY',None,('INTEGER',),'ROW'),('ARRAY',True,('INTEGER',),'ROW'),('ARRAY',2,('ARRAY',2,('INTEGER',))),('ARRAY',2,('INTEGER',),'')]
        for source in sources:self.assertIsNone(rt.numeric_array_kind(('ARRAY',2,('REAL',),'OUT'),source))

    def test_resource_and_whole_structure_coercion_remain_rejected(self):
        with self.assertRaises(TranslationError):compile_program('b=a',prefix='TYPE a_t=STRUCTURE data:ARRAY[2]OF INTEGER ENDSTRUCTURE b_t=STRUCTURE data:ARRAY[2]OF REAL ENDSTRUCTURE',decl='a:a_t b:b_t')
        with self.assertRaises(TranslationError):compile_program('b=a',prefix='TYPE a_t=ARRAY[2]OF FILE',decl='a:a_t b:ARRAY[2]OF REAL')

    def test_legacy_named_array_conversion_remains_blocked(self):
        prefix=declarations('INTEGER','REAL','flat')
        with self.assertRaises(TranslationError):legacy_translate('PROGRAM T '+prefix+' VAR a:in_t b:out_t BEGIN b=a END T')

    def test_chained_index_subarray_conversion_captures_selector_once(self):
        prefix=declarations('INTEGER','REAL')+' box_t=STRUCTURE data:in_t ENDSTRUCTURE'
        p,_=compile_program('visits=0 b=boxes[pick()].data[1]',prefix=prefix,decl='a:in_t boxes:ARRAY[1]OF box_t b:out_row visits:INTEGER',routines='ROUTINE pick:INTEGER BEGIN visits=visits+1 RETURN 1 END pick')
        p._state.values['BOXES'].values[0].values['DATA'].values[0].values[:]=[1,2];p.run()
        self.assertEqual((outputs(p),p.snapshot()['VISITS']),([1.,2.],1))


class NamedArrayReportTests(unittest.TestCase):
    def test_report_retains_source_and_receiver_component_names(self):
        p,result=build();initialize(p);p.run();report=result.report
        rows=report['named_array_conversions'];self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['conversion_kind'],rows[0]['source_component_names'],rows[0]['target_component_names']),('numeric_array',['IN_T','IN_ROW'],['OUT_T','OUT_ROW']))
        self.assertFalse(report['named_array_policy']['controller_validated']);self.assertIn('named/component ARRAY conversion',report['features'])

    def test_report_distinguishes_private_argument_and_return(self):
        p,result=build('b=work(a)',first='SHORT',second='INTEGER',routines='ROUTINE work(v:out_t):in_t BEGIN RETURN v END work');initialize(p);p.run()
        rows=result.report['named_array_conversions'];self.assertEqual({row['operation'] for row in rows},{'ARGUMENT','RETURN','ASSIGNMENT'})
        self.assertTrue(all(row['independent_value'] for row in rows))


class NamedArrayLinkageTests(unittest.TestCase):
    def test_linked_declared_formal_gets_private_converted_named_array(self):
        prefix=declarations('INTEGER','REAL','flat')
        lib='PROGRAM LIB '+prefix+' VAR n:INTEGER ROUTINE work(v:out_t) BEGIN v[1]=99 n=TRUNC(v[1]) END work BEGIN END LIB'
        main='PROGRAM MAIN '+prefix+' VAR a:in_t ROUTINE work(v:out_t) FROM LIB BEGIN a[1]=1 a[2]=2 work(a) END MAIN'
        project=translate_project({'lib':lib,'main':main}).instantiate();project.run('MAIN')
        self.assertEqual((project.programs['MAIN'].snapshot()['A'],project.programs['LIB'].snapshot()['N']),([1,2],99))

    def test_linked_declaration_definition_mismatch_stays_rejected(self):
        prefix=declarations('INTEGER','REAL','flat')
        lib='PROGRAM LIB '+prefix+' VAR n:INTEGER ROUTINE work(v:in_t) BEGIN END work BEGIN END LIB'
        main='PROGRAM MAIN '+prefix+' VAR a:in_t ROUTINE work(v:out_t) FROM LIB BEGIN work(a) END MAIN'
        with self.assertRaises(ValueError):translate_project({'lib':lib,'main':main}).instantiate()

    def test_raw_callback_result_requires_declared_named_schema(self):
        actual=rt.Array(('ARRAY',2,('INTEGER',),'IN_T'));actual.values[:]=[1,2]
        ctx=rt.ExecutionContext(externals={('LIB','MAKE'):lambda:actual})
        p,_=build('b=make()',layout='flat',routines='ROUTINE make:out_t FROM LIB',context=ctx)
        with self.assertRaises(rt.KarelRuntimeError):p.run()
        self.assertIs(outputs(p)[0],rt.UNINITIALIZED)

    def test_external_callback_receives_named_target_cells(self):
        seen=[]
        def work(ref):seen.append(ref.spec);ref.raw().values[0].values[0]=99.
        p,_=build('work(a)',routines='ROUTINE work(v:out_t) FROM LIB',context=rt.ExecutionContext(externals={('LIB','WORK'):work}));initialize(p);p.run()
        self.assertEqual(seen,[p._state.types['B']]);self.assertEqual(leaves(p._state.values['A'])[0],1)


if __name__=='__main__':unittest.main()
