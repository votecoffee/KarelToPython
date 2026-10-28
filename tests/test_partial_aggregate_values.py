"""Authored partial data copies with concrete schemas and checked known leaves."""
import unittest

from karel2py import translate,runtime as rt
from tests.legacy_numeric_support import translate as legacy_translate


U={'uninitialized':True}
B={'unknown_byte':True}
ITEM=('STRUCTURE','ITEM_T',(('COUNT',rt.INTEGER),('LABEL',('STRING',4))))
TYPES='TYPE item_t=STRUCTURE count:INTEGER label:STRING[4] ENDSTRUCTURE'


def build(body,decl='a,b:item_t n:INTEGER flag:BOOLEAN',types=TYPES,routines='',translator=translate,**options):
    result=translator(f'PROGRAM MAIN {types} VAR {decl} {routines} BEGIN {body} END MAIN')
    namespace={'__name__':'partial_aggregate_test'};exec(result.python_source,namespace)
    return namespace['Program'](**options),result


def execute(body,**options):return build(body,**options)[0].run()


def copied(value,spec=None):
    with rt._numeric_scope('pythonic'):return rt.checked(value.spec if spec is None else spec,value,71)


class PartialAggregateSourceTests(unittest.TestCase):
    def test_partial_structure_assignment_is_detached(self):
        data=execute('a.count=7 b=a b.count=9')
        self.assertEqual((data['A'],data['B']),({'COUNT':7,'LABEL':U},{'COUNT':9,'LABEL':U}))

    def test_wholly_uninitialized_structure_copies_concrete_fields(self):
        self.assertEqual(execute('b=a')['B'],{'COUNT':U,'LABEL':U})

    def test_nested_arrays_and_records_preserve_missing_leaves(self):
        types='TYPE row_t=ARRAY[2] OF INTEGER item_t=STRUCTURE rows:ARRAY[2]OF row_t bytes:ARRAY[2]OF BYTE ENDSTRUCTURE'
        data=execute('a.rows[1,1]=7 a.bytes[1]=8 b=a b.rows[1,1]=9',types=types)
        self.assertEqual(data['A'],{'ROWS':[[7,U],[U,U]],'BYTES':[8,B]})
        self.assertEqual(data['B'],{'ROWS':[[9,U],[U,U]],'BYTES':[8,B]})

    def test_partial_scalar_matrix_copy(self):
        data=execute('a[1,2]=7 b=a b[1,2]=9',types='',decl='a,b:ARRAY[2,2]OF INTEGER')
        self.assertEqual((data['A'],data['B']),([[U,7],[U,U]],[[U,9],[U,U]]))

    def test_partial_record_array_assignment(self):
        data=execute('a[2].count=7 b=a b[2].label=\'ok\'',decl='a,b:ARRAY[2]OF item_t')
        self.assertEqual(data['B'],[{'COUNT':U,'LABEL':U},{'COUNT':7,'LABEL':'ok'}])
        self.assertEqual(data['A'][1]['LABEL'],U)

    def test_unknown_byte_and_short_sentinel_remain_missing(self):
        data=execute('a[1]=7 b=a shorta[1]=32767 shortb=shorta',types='',
                     decl='a,b:ARRAY[2]OF BYTE shorta,shortb:ARRAY[2]OF SHORT')
        self.assertEqual((data['B'],data['SHORTB']),([7,B],[U,U]))

    def test_structure_value_parameter_has_private_partial_storage(self):
        routine="ROUTINE consume(p:item_t) BEGIN flag=UNINIT(p.label) p.count=99 p.label='local' END consume"
        data=execute('a.count=7 consume((a))',routines=routine)
        self.assertEqual((data['A'],data['FLAG']),({'COUNT':7,'LABEL':U},True))

    def test_partial_array_value_parameter_is_private(self):
        routine='ROUTINE consume(p:ARRAY OF INTEGER) BEGIN flag=UNINIT(p[2]) p[1]=99 p[2]=42 END consume'
        data=execute('a[1]=7 consume((a))',types='',decl='a:ARRAY[2]OF INTEGER flag:BOOLEAN',routines=routine)
        self.assertEqual((data['A'],data['FLAG']),([7,U],True))

    def test_partial_vector_value_parameter_is_private(self):
        routine='ROUTINE consume(p:VECTOR) BEGIN flag=UNINIT(p.y) p.x=99 p.y=42 END consume'
        data=execute('a.x=7 consume((a))',types='',decl='a:VECTOR flag:BOOLEAN',routines=routine)
        self.assertEqual((data['A'],data['FLAG']),({'X':7.,'Y':U,'Z':U},True))

    def test_structure_function_can_return_partial_local(self):
        routine='ROUTINE make:item_t VAR local:item_t BEGIN local.count=7 RETURN local END make'
        data=execute('b=make() b.label=\'ok\'',routines=routine)
        self.assertEqual(data['B'],{'COUNT':7,'LABEL':'ok'})

    def test_array_function_can_return_partial_local(self):
        routine='ROUTINE make:ARRAY OF INTEGER VAR local:ARRAY[2]OF INTEGER BEGIN local[1]=7 RETURN local END make'
        self.assertEqual(execute('b=make()',types='',decl='b:ARRAY[2]OF INTEGER',routines=routine)['B'],[7,U])

    def test_named_array_function_retains_identity_and_missing_contents(self):
        routine='ROUTINE make:row_t VAR local:row_t BEGIN local[1]=7 RETURN local END make'
        data=execute('b=make()',types='TYPE row_t=ARRAY[2]OF INTEGER',decl='b:row_t',routines=routine)
        self.assertEqual(data['B'],[7,U])

    def test_vector_function_can_return_partial_local(self):
        routine='ROUTINE make:VECTOR VAR local:VECTOR BEGIN local.x=7 RETURN local END make'
        self.assertEqual(execute('b=make()',types='',decl='b:VECTOR',routines=routine)['B'],{'X':7.,'Y':U,'Z':U})

    def test_positional_functions_copy_missing_components_without_geometry(self):
        for kind,field in (('XYZWPR','x'),('XYZWPREXT','ext1'),('POSITION','location.x'),('CONFIG','cfg_turn_no1')):
            with self.subTest(kind=kind):
                routine=f'ROUTINE make:{kind} VAR local:{kind} BEGIN local.{field}=1 RETURN local END make'
                data=execute('b=make()',types='',decl=f'b:{kind}',routines=routine)['B']
                self.assertTrue(any(value==U or isinstance(value,dict) and U in value.values() for value in data.values()))

    def test_joint_function_and_value_parameter_preserve_missing_axes(self):
        routine='ROUTINE consume(p:JOINTPOS3) BEGIN flag=UNINIT(p) p=blank END consume ROUTINE make:JOINTPOS3 BEGIN RETURN a END make'
        program,_=build('b=make() consume((a))',types='',decl='a,b,blank:JOINTPOS3 flag:BOOLEAN',routines=routine)
        program._state.values['A'].values[0]=7.
        data=program.run();self.assertEqual((data['A'],data['B'],data['FLAG']),({'axes':[7.,U,U]},{'axes':[7.,U,U]},True))

    def test_source_scalar_reads_remain_errors(self):
        for body,decl in (('a.count=7 b=a n=b.count text=b.label','a,b:item_t n:INTEGER text:STRING[4]'),
                          ('b=a n=b[1]','a,b:ARRAY[1]OF INTEGER n:INTEGER')):
            with self.subTest(body=body):
                program,_=build(body,decl=decl,types=TYPES if 'item_t' in decl else '')
                with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized'):program.run()

    def test_unknown_byte_scalar_read_still_fails(self):
        program,_=build('b=a n=b[1]',types='',decl='a,b:ARRAY[1]OF BYTE n:INTEGER')
        with self.assertRaisesRegex(rt.KarelRuntimeError,'unknown'):program.run()

    def test_partial_copy_keeps_captured_destination_alias(self):
        routine='ROUTINE consume(p:INTEGER) BEGIN b=a p=9 END consume'
        data=execute('a.count=7 b.count=1 consume(b.count)',routines=routine)
        self.assertEqual(data['B'],{'COUNT':9,'LABEL':U})

    def test_rhs_snapshot_precedes_target_selector_effect(self):
        routine='ROUTINE slot:INTEGER BEGIN n=n+1 a.count=99 RETURN 1 END slot'
        data=execute('n=0 a.count=7 dest[slot()]=a',decl='a:item_t dest:ARRAY[1]OF item_t n:INTEGER',routines=routine)
        self.assertEqual((data['A']['COUNT'],data['DEST'][0],data['N']),(99,{'COUNT':7,'LABEL':U},1))

    def test_partial_result_can_feed_private_value_argument(self):
        routine='ROUTINE make:item_t VAR local:item_t BEGIN local.count=7 RETURN local END make ROUTINE consume(p:item_t) BEGIN n=p.count flag=UNINIT(p.label) p.count=9 END consume'
        data=execute('consume(make())',routines=routine)
        self.assertEqual((data['N'],data['FLAG']),(7,True))

    def test_partial_value_captured_before_later_argument_effect(self):
        routines='ROUTINE later:INTEGER BEGIN a.count=99 RETURN 1 END later ROUTINE consume(p:item_t; q:INTEGER) BEGIN n=p.count flag=UNINIT(p.label) END consume'
        data=execute('a.count=7 consume((a),later())',routines=routines)
        self.assertEqual((data['A']['COUNT'],data['N'],data['FLAG']),(99,7,True))

    def test_invalid_known_leaf_prevents_target_selector_effect(self):
        routine='ROUTINE slot:INTEGER BEGIN n=n+1 RETURN 1 END slot'
        program,_=build('n=0 dest[slot()]=a',decl='a:item_t dest:ARRAY[1]OF item_t n:INTEGER',routines=routine)
        program._state.values['A'].values['COUNT']=True
        with self.assertRaises(rt.KarelRuntimeError):program.run()
        self.assertEqual((program.snapshot()['N'],program.snapshot()['DEST'][0]),(0,{'COUNT':U,'LABEL':U}))

    def test_internal_strict_assignment_still_rejects_partial_structure(self):
        program,_=build('a.count=7 b=a',translator=legacy_translate)
        with self.assertRaisesRegex(rt.KarelRuntimeError,'uninitialized fields'):program.run()


class PartialAggregateHostValidationTests(unittest.TestCase):
    def test_direct_copy_preserves_marker_identity_and_detaches_children(self):
        spec=('STRUCTURE','BOX',(('ITEM',ITEM),('BYTES',('ARRAY',2,rt.BYTE))))
        source=rt.Structure(spec);source.values['ITEM'].values['COUNT']=7
        result=copied(source)
        self.assertIs(result.values['ITEM'].values['LABEL'],rt.UNINITIALIZED)
        self.assertIs(result.values['BYTES'].values[0],rt.UNKNOWN_BYTE)
        self.assertIsNot(result.values['ITEM'],source.values['ITEM'])
        self.assertIsNot(result.values['BYTES'],source.values['BYTES'])

    def test_every_known_scalar_leaf_is_validated(self):
        rows=((rt.INTEGER,True),(rt.INTEGER,2147483647),(rt.INTEGER,2**31),
              (rt.REAL,float('nan')),(rt.REAL,float('inf')),(rt.REAL,True),
              (rt.BOOLEAN,1),(rt.BYTE,-1),(rt.BYTE,256),(rt.SHORT,-32769),(rt.SHORT,32768))
        for spec,value in rows:
            with self.subTest(spec=spec,value=value):
                source=rt.Array(('ARRAY',2,spec));source.values[1]=value
                with self.assertRaisesRegex(rt.KarelRuntimeError,'line 71'):copied(source)

    def test_string_capacity_and_ascii_are_checked_without_truncation(self):
        for value in ('abcde','caf\u00e9',7):
            with self.subTest(value=value):
                source=rt.Structure(ITEM);source.values['LABEL']=value
                with self.assertRaises(rt.KarelRuntimeError):copied(source)
                self.assertEqual(source.values['LABEL'],value)

    def test_unknown_byte_is_allowed_only_in_byte_leaves(self):
        for spec in (rt.INTEGER,rt.REAL,rt.BOOLEAN,rt.SHORT,('STRING',4)):
            with self.subTest(spec=spec):
                source=rt.Array(('ARRAY',1,spec));source.values[0]=rt.UNKNOWN_BYTE
                with self.assertRaisesRegex(rt.KarelRuntimeError,'BYTE'):copied(source)

    def test_short_raw_sentinel_is_normalized_to_missing(self):
        source=rt.Array(('ARRAY',1,rt.SHORT));source.values[0]=32767
        self.assertIs(copied(source).values[0],rt.UNINITIALIZED)
        self.assertEqual(source.values[0],32767)

    def test_missing_aggregate_storage_is_not_a_missing_leaf(self):
        for spec in (('ARRAY',1,rt.INTEGER),ITEM,('JOINTPOS',2)):
            with self.subTest(spec=spec):
                outer=rt.Array(('ARRAY',1,spec if spec[0]!='ARRAY' else (*spec,'ROW_T')))
                outer.values[0]=rt.UNINITIALIZED
                with self.assertRaises(rt.KarelRuntimeError):copied(outer)

    def test_array_storage_length_shape_and_container_are_exact(self):
        for change in ('length','shape','container'):
            with self.subTest(change=change):
                source=rt.Array(('ARRAY',(2,2),rt.INTEGER))
                if change=='length':source.values.pop()
                elif change=='shape':source.shape=(1,4)
                else:source.values=tuple(source.values)
                with self.assertRaisesRegex(rt.KarelRuntimeError,'shape and storage'):copied(source)

    def test_structure_layout_and_field_metadata_are_exact(self):
        for change in ('missing','extra','types','container'):
            with self.subTest(change=change):
                source=rt.Structure(ITEM)
                if change=='missing':del source.values['LABEL']
                elif change=='extra':source.values['EXTRA']=1
                elif change=='types':source.types['COUNT']=rt.REAL
                else:source.values=[]
                with self.assertRaisesRegex(rt.KarelRuntimeError,'nominal type and fields'):copied(source)

    def test_joint_width_storage_and_known_axes_are_exact(self):
        for values in ([1.],(1.,rt.UNINITIALIZED),None,[float('nan'),rt.UNINITIALIZED],[True,rt.UNINITIALIZED]):
            with self.subTest(values=values):
                source=rt.JointPosition(('JOINTPOS',2));source.values=values
                with self.assertRaises(rt.KarelRuntimeError):copied(source)

    def test_nominal_array_and_structure_types_are_not_coerced(self):
        for spec,value in ((('ARRAY',1,rt.INTEGER,'A'),rt.Array(('ARRAY',1,rt.INTEGER,'B'))),
                           (ITEM,rt.Structure(('STRUCTURE','OTHER',ITEM[2])))):
            with self.subTest(spec=spec),self.assertRaises(rt.KarelRuntimeError):copied(value,spec)

    def test_partially_missing_config_rechecks_known_fields(self):
        source=rt.Structure(('CONFIG',));source.values['CFG_TURN_NO1']=7
        self.assertEqual(copied(source).values['CFG_TURN_NO1'],7)
        for field,value in (('CFG_TURN_NO1',8),('CFG_FLIP',1)):
            with self.subTest(field=field):
                invalid=rt.Structure(('CONFIG',));invalid.values[field]=value
                with self.assertRaises(rt.KarelRuntimeError):copied(invalid)

    def test_position_orientation_protection_survives_partial_copy(self):
        source=rt.Structure(('POSITION',));result=copied(source)
        self.assertIsNot(result.values['NORMAL'],source.values['NORMAL'])
        with self.assertRaisesRegex(rt.KarelRuntimeError,'read-only'):rt.field_reference(result.values['NORMAL'],'X').set(1.)

    def test_scalar_missing_reads_are_not_relaxed(self):
        for spec in (rt.INTEGER,rt.REAL,rt.BOOLEAN,rt.BYTE,rt.SHORT,('STRING',4)):
            with self.subTest(spec=spec),rt._numeric_scope('pythonic'),self.assertRaises(rt.KarelRuntimeError):
                rt.checked(spec,rt.UNINITIALIZED,71)

    def test_overlarge_or_bad_schema_rejects_before_copy(self):
        for spec in (('ARRAY',32768,rt.INTEGER),('ARRAY',1,('STRING',None)),
                     ('STRUCTURE','BAD',(('X',rt.INTEGER),('x',rt.REAL))),
                     ('STRUCTURE','EMPTY',()),('VECTOR',1),('ARRAY',1,rt.INTEGER,'')):
            with self.subTest(spec=spec):
                source=rt.Array(('ARRAY',1,rt.INTEGER)) if spec[0]=='ARRAY' else rt.Structure(ITEM)
                source.spec=spec
                with self.assertRaisesRegex(rt.KarelRuntimeError,'line 71'):copied(source)

    def test_structure_and_field_identifiers_are_canonical(self):
        for spec in (('STRUCTURE','bad name',(('X',rt.INTEGER),)),
                     ('STRUCTURE','BAD',(('bad field',rt.INTEGER),)),
                     ('STRUCTURE','BAD',(('caf\u00e9',rt.INTEGER),))):
            with self.subTest(spec=spec):
                source=rt.Structure(ITEM);source.spec=spec
                with self.assertRaises(rt.KarelRuntimeError):copied(source)

    def test_malformed_value_argument_storage_is_an_explicit_error(self):
        for spec in (None,[],(),('ARRAY',),('ARRAY',1,())):
            with self.subTest(spec=spec),rt._numeric_scope('pythonic'):
                source=rt.Array(('ARRAY',1,rt.INTEGER));source.spec=spec
                with self.assertRaisesRegex(rt.KarelRuntimeError,'line 71'):
                    rt.value_argument(('ARRAY',None,rt.INTEGER),source,71)

    def test_schema_depth_bound_is_explicit(self):
        spec=rt.INTEGER
        for number in range(65):spec=('STRUCTURE','N'+str(number),(('CHILD',spec),))
        source=rt.Structure(ITEM);source.spec=spec
        with self.assertRaisesRegex(rt.KarelRuntimeError,'64 levels'):copied(source)

    def test_shared_schema_cache_cannot_bypass_depth_limit(self):
        tail=('STRUCTURE','TAIL',(('LEAF',rt.INTEGER),));deep=tail
        for number in range(62):deep=('STRUCTURE','N'+str(number),(('CHILD',deep),))
        spec=('STRUCTURE','ROOT',(('SHALLOW',tail),('DEEP',deep)))
        source=rt.Structure(ITEM);source.spec=spec
        with self.assertRaisesRegex(rt.KarelRuntimeError,'64 levels'):copied(source)

    def test_cyclic_host_storage_is_rejected(self):
        source=rt.Structure(('STRUCTURE','BOX',(('CHILD',('VECTOR',)),)))
        source.values['CHILD']=source
        with self.assertRaisesRegex(rt.KarelRuntimeError,'cyclic'):copied(source)

    def test_embedded_resources_remain_blocked(self):
        for resource in (('FILE',),('PATH',None,None),('QUEUE_TYPE',)):
            with self.subTest(resource=resource):
                source=rt.Structure(('STRUCTURE','BOX',(('RESOURCE',resource),)))
                with self.assertRaisesRegex(rt.KarelRuntimeError,'without.*resources'):copied(source)

    def test_top_level_resource_copy_contracts_remain_unchanged(self):
        file=rt.FileHandle();path=rt.PathValue(('PATH',None,None));queue=rt.QueueValue()
        with rt._numeric_scope('pythonic'):
            self.assertIs(rt.checked(('FILE',),file),file)
            self.assertIsNot(rt.checked(path.spec,path),path)
            with self.assertRaisesRegex(rt.KarelRuntimeError,'cannot be copied'):rt.checked(queue.spec,queue)

    def test_internal_strict_value_interfaces_still_reject_markers(self):
        for value in (rt.Array(('ARRAY',1,rt.INTEGER)),rt.Structure(ITEM),rt.JointPosition(('JOINTPOS',2))):
            with self.subTest(spec=value.spec),rt._numeric_scope('strict'),self.assertRaises(rt.KarelRuntimeError):
                rt._aggregate_value(value.spec,value,71)


class PartialGeometryUseTests(unittest.TestCase):
    def complete(self,kind='XYZWPR'):
        with rt._numeric_scope('pythonic'):
            config=rt.Structure(('CONFIG',))
            config.values.update({name:0 if field==rt.INTEGER else False for name,field in rt.record_fields(config.spec)})
            point=rt.builtin('POS',[0.,0.,0.,0.,0.,0.,config])
            return rt.convert_position((kind,),point) if kind!='XYZWPR' else point

    def test_inv_frame_transform_and_comparison_require_complete_pose(self):
        partial=rt.Structure(('XYZWPR',));complete=self.complete()
        operations=(lambda:rt.frame_inverse(partial,71),lambda:rt.frame_from_points([complete,partial,complete],71),
                    lambda:rt.frame_transform(partial,complete,71),lambda:rt.frame_transform(complete,partial,71),
                    lambda:rt.positions_close(partial,complete,(1.,1.,False),71))
        with rt._numeric_scope('pythonic'):
            for operation in operations:
                with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()

    def test_position_orientation_and_external_axes_remain_checked_on_use(self):
        for kind in ('POSITION','XYZWPREXT'):
            with self.subTest(kind=kind),rt._numeric_scope('pythonic'):
                source=rt.Structure((kind,));result=copied(source)
                with self.assertRaises(rt.KarelRuntimeError):rt.frame_value(result,71)

    def test_vector_operators_read_all_components(self):
        partial=rt.Structure(('VECTOR',));partial.values['X']=1.
        with rt._numeric_scope('pythonic'):
            for operation in (lambda:rt.vector_value(partial,71),lambda:rt.vector_binary('+',partial,partial,71),
                              lambda:rt.vector_binary('@',partial,partial,71),lambda:rt.unary('-',partial,71),
                              lambda:rt.frame_transform(self.complete(),partial,71)):
                with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()

    def test_joint_geometry_and_positional_consumers_require_complete_axes(self):
        source=rt.JointPosition(('JOINTPOS',2));source.values[0]=1.
        with rt._numeric_scope('pythonic'):
            value=copied(source)
            for operation in (lambda:rt.joint_values(value,2,71),lambda:rt.padded_joints(value,71),
                              lambda:rt.positional_value(value.spec,value,71)):
                with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()

    def test_source_joint_conversion_preserves_outputs_when_axes_missing(self):
        program,_=build('b=a CNV_JPOS_REL(b,axes,s)',types='',
                        decl='a,b:JOINTPOS2 axes:ARRAY[2]OF REAL s:INTEGER',joint_axes=2)
        program._state.values['A'].values[0]=1.
        with self.assertRaisesRegex(rt.KarelRuntimeError,'initialized axes'):program.run()
        self.assertEqual(program.snapshot()['AXES'],[U,U])

    def test_config_formatting_and_pose_construction_require_complete_config(self):
        source=rt.Structure(('CONFIG',));source.values['CFG_TURN_NO1']=1
        with rt._numeric_scope('pythonic'):
            for operation in (lambda:rt.positional_value(('CONFIG',),source,71),
                              lambda:rt.builtin('POS',[0.,0.,0.,0.,0.,0.,source],71)):
                with self.subTest(operation=operation),self.assertRaises(rt.KarelRuntimeError):operation()


if __name__=='__main__':unittest.main()
